import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest

import analytics
import privacy
import source_reconciliation as reconcile


class SourceReconciliationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name)/"research.db"
        self.db = sqlite3.connect(self.path)
        self.addCleanup(self.db.close)
        self.db.executescript(analytics.SCHEMA)
        self.product = dict(kind="products", market="US", id="p", name="sample", sales=3, gmv="17.21", date="2026-11-01")
        self.add_rows([self.product, {**self.product, "kind":"shops"},
                       {**self.product, "market":"GB"}])
        self.csv = ",".join(reconcile.FIELDS)+"\n"

    def add_rows(self, rows):
        with self.db:
            analytics.import_rows(self.db, rows, "trial")

    def manifest(self, *lines):
        return (self.csv+"\n".join(lines)+"\n").encode()

    def report(self, until="2026-11-04"):
        return reconcile.report(self.db, "trial", "US", "2026-11-01", until)

    def test_partial_missing_backfill_and_replay(self):
        self.assertEqual(self.report()["counts"]["unverified"], 4)
        manifest = self.manifest("trial,US,2026-11-01,Store A,2,6,34.42",
                                 "trial,US,2026-11-02,Store A,1,3,17.21",
                                 "trial,US,2026-11-03,Store A,0,0,0")
        loaded = reconcile.load_file(self.db, manifest)
        report = self.report()
        self.assertEqual(report["counts"], {"matched":1, "missing":1, "mismatch":1, "unverified":1})
        first = report["days"][0]
        self.assertEqual(first["actual"], {"product_rows":1, "sales":3, "gmv":"17.21"})
        self.assertEqual(first["file_sha256"], loaded["file_sha256"])
        self.assertIsNone(report["days"][2]["actual"])
        for _ in range(2):
            self.add_rows([{**self.product,"id":"q"}, {**self.product,"date":"2026-11-02"}])
            result = reconcile.load_file(self.db, manifest)
            self.assertEqual((result["added"],result["unchanged"]), (0,3))
        self.assertTrue(self.report("2026-11-03")["matched"])
        self.assertFalse(self.report()["matched"])

    def test_conflicting_revisions_are_atomic(self):
        reconcile.load_file(self.db, self.manifest("trial,US,2026-11-01,Store A,1,3,17.21"))
        corrected = self.manifest("trial,US,2026-11-02,Store A,0,0,0", "trial,US,2026-11-01,Store A,1,4,17.21")
        with self.assertRaisesRegex(ValueError,"revise"):
            reconcile.load_file(self.db, corrected)
        self.assertEqual([d["status"] for d in self.report("2026-11-02")["days"]], ["matched","unverified"])
        reconcile.load_file(self.db, corrected, revise=True)
        first = self.report()["days"][0]
        self.assertEqual((first["status"], first["expected"]["sales"]), ("mismatch",4))
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM source_baselines").fetchone()[0], 3)
        for line in ("trial,US,2026-11-01,Store A,0,3,0", "trial,US,2026-11-01,Store A,1,3,0.001",
                     "unknown,US,2026-11-01,Store A,1,3,17.21", "demo,US,2026-11-01,test,0,0,0"):
            with self.subTest(line=line),self.assertRaises(ValueError):
                reconcile.load_file(self.db, self.manifest(line))

    def test_date_bounds_never_silently_skip_existing_iso_rows(self):
        for day in ("20261101", "2026-W44-7"):
            with self.subTest(day=day), self.assertRaises(ValueError):
                reconcile.report(self.db, "trial", "US", day, day)

    def test_daily_totals_above_individual_and_sqlite_integer_limits(self):
        amount = 10**14
        for day, count in (("2026-11-02",2), ("2026-11-03",923)):
            self.add_rows([{**self.product,"date":day,"id":str(i),"gmv":str(amount),"sales":amount}
                           for i in range(count)])
            manifest = self.manifest(f"trial,US,{day},Store A,{count},{count * amount},{count * amount}.00")
            reconcile.load_file(self.db, manifest)
            result = reconcile.report(self.db, "trial", "US", day, day)
            self.assertTrue(result["matched"])
            self.assertEqual(result["days"][0]["actual"]["gmv"], f"{count * amount}.00")
            self.assertEqual(reconcile.load_file(self.db,manifest)["unchanged"], 1)
        self.assertEqual(result["days"][0]["actual"]["display_counts"],["923",str(923 * amount)])

    def test_window_at_earliest_valid_cutoff(self):
        window = analytics.scope_for(self.db, {"source":"trial","market":"US","date":"1900-01-01","days":7})
        result = reconcile.report(self.db, "trial", "US", window["start_date"], window["date"])
        self.assertEqual(result["days"][0]["date"], "1899-12-26")
        self.assertEqual(result["counts"]["unverified"], 7)

    def test_erasure_cleans_private_controls_on_restored_connection(self):
        # A restored SQLite connection can have foreign-key enforcement switched off.
        with self.db:
            self.db.execute("CREATE TABLE users(id INTEGER PRIMARY KEY,name,email,password,plan,owner)")
            self.db.execute("INSERT INTO users VALUES(1,'Trial','trial@example.test',NULL,'free',NULL)")
            analytics.source_policy.set_access(self.db, "trial", owner=1)
            analytics.import_rows(self.db, [self.product], "public", shared=True)
        reconcile.load_file(self.db, self.manifest("trial,US,2026-11-01,Private shop,1,3,17.21",
                                                   "public,US,2026-11-01,Public sample,1,3,17.21"))
        with self.db:
            privacy.erase(self.db, 1, "trial@example.test")
        self.assertEqual(self.db.execute("SELECT shop_scope FROM source_baselines").fetchall(), [("Public sample",)])

    def test_cli_import_check_and_gap_exit_status(self):
        cli = [sys.executable, str(Path(reconcile.__file__).with_name("manage.py"))]
        env = {**os.environ, "TIKFLOWSO_ENV_FILE":os.devnull}
        control = Path(self.tmp.name)/"control.csv"
        control.write_bytes(self.manifest("trial,US,2026-11-01,Store A,1,3,17.21"))
        subprocess.run([*cli,"import-source-baseline","--db",str(self.path),"--file",str(control)],
                       check=True, capture_output=True, env=env)
        args = [*cli,"reconcile-source","--db",str(self.path),"--source","trial","--market","us","--since","2026-11-01","--until"]
        passed = subprocess.run([*args,"2026-11-01"],check=True,capture_output=True,env=env)
        self.assertTrue(json.loads(passed.stdout)["matched"])
        gap = subprocess.run([*args,"2026-11-02"],capture_output=True,env=env)
        self.assertEqual(gap.returncode, 1)
        self.assertEqual(json.loads(gap.stdout)["days"][1]["status"], "unverified")

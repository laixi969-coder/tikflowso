"""Exercise the installed dlt client, a loopback merchant, and the actual feed importer."""

import json
import os
import sqlite3
import tempfile
from contextlib import closing
from datetime import UTC, date, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from unittest import TestCase, main, mock
from urllib.parse import parse_qs, urlsplit

import analytics
import feeds
import source_reconciliation as reconciliation
from connectors import dlt_supplier as supplier

FIXTURE_NOW = datetime(2026, 11, 26, tzinfo=UTC)


class IncrementalSupplierTests(TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.directory = Path(tmp.name)
        self.out = self.directory / "deliveries"
        self.pages = {}
        self.requests = []

        def respond(handler):
            query = parse_qs(urlsplit(handler.path).query)
            self.requests.append(query)
            if handler.headers.get("Authorization") != "Bearer fixture-only":
                handler.send_error(401)
                return
            status, page = self.pages[query.get("cursor", [""])[0]]
            handler.send_response(status)
            handler.end_headers()
            handler.wfile.write(page if isinstance(page, bytes) else json.dumps(page).encode())

        handler = type(
            "Supplier", (BaseHTTPRequestHandler,), {"do_GET": respond, "log_message": lambda *args: None}
        )
        http = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        thread = Thread(target=http.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(thread.join)
        self.addCleanup(http.server_close)
        self.addCleanup(http.shutdown)
        self.cfg = {
            "source": "contract-us",
            "url": f"http://127.0.0.1:{http.server_port}/products",
            "market": "US",
            "currency": "USD",
            "initial_since": "2026-10-01T00:00:00Z",
            "token_env": "OFFLINE_DLT_TOKEN",
            "items_path": "page.rows",
            "cursor_path": "page.next",
            "fields": {
                "id": "product.id",
                "date": "day",
                "name": "product.title",
                "sales": "units",
                "gmv": "amount",
            },
        }
        self.patch = mock.patch.dict(
            os.environ,
            {"OFFLINE_DLT_TOKEN": "fixture-only", "NO_PROXY": "127.0.0.1", "no_proxy": "127.0.0.1"},
        )
        self.patch.start()
        self.addCleanup(self.patch.stop)
        self.a = {
            "product": {"id": "001", "title": "First"},
            "market": "US",
            "currency": "USD",
            "day": "2026-11-01",
            "units": 2,
            "amount": "10.15",
            "updated_at": "2026-11-02T09:00:00Z",
        }
        self.b = {**self.a, "product": {"id": "002", "title": "Second"}, "units": 3, "amount": "11.31"}
        self.feed = self.directory / "feed.json"
        self.feed.write_text(
            json.dumps(
                [{"id": "provider", "source": "contract-us", "directory": str(self.out), "shared": True}]
            )
        )
        self.db = sqlite3.connect(self.directory / "app.db")
        self.addCleanup(self.db.close)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(analytics.SCHEMA)

    def set_page(self, rows, next_token=None, key=""):
        self.pages[key] = (200, {"page": {"rows": rows, "next": next_token}})

    def run_sync(self, **kwargs):
        return supplier.sync(self.cfg, self.out, now=FIXTURE_NOW, **kwargs)

    def ingest(self):
        run = feeds.sync_configured(self.db, True, self.feed)[0]
        self.assertEqual(run["status"], "ok", run)
        row = self.db.execute(
            "SELECT COUNT(*),SUM(sales),SUM(gmv_units) FROM analytics_daily WHERE source='contract-us'"
        ).fetchone()
        return run["rows"], tuple(row)

    def test_two_pages_incremental_overlap_backfill_and_actual_feed(self):
        self.set_page([self.a], "two")
        self.set_page([self.b], key="two")
        first = self.run_sync()
        self.assertEqual((first["changed"], self.ingest()), (2, (2, (2, 5, 2146))))
        revised = {**self.a, "updated_at": "2026-11-03T00:11:00+01:00", "units": 4, "amount": "19.47"}
        self.set_page([self.b, revised])
        second = self.run_sync()
        self.assertEqual(self.requests[-1]["updated_since"], [first["watermark"]])
        self.assertEqual(second["watermark"], "2026-11-02T23:11:00.000000Z")
        self.assertEqual(self.ingest(), (2, (2, 7, 3078)))
        self.set_page([revised])
        self.assertEqual(self.run_sync()["changed"], 0)
        self.assertEqual(self.ingest(), (0, (2, 7, 3078)))
        self.set_page([self.a, {**self.b, "day": "2026-10-28"}])
        history = self.run_sync(backfill=self.cfg["initial_since"])
        self.assertEqual(history["watermark"], second["watermark"])
        self.assertEqual(self.ingest(), (1, (3, 10, 4209)))

    def test_error_on_later_page_preserves_watermark_and_output(self):
        self.set_page([self.a])
        first = self.run_sync()
        file = self.out / "2026-11-01.json"
        original = file.read_bytes()
        self.set_page([{**self.a, "units": 19, "updated_at": "2026-11-04T09:00:00Z"}], "bad")
        self.pages["bad"] = (503, {})
        with self.assertRaisesRegex(ValueError, "503"):
            self.run_sync()
        self.assertEqual(file.read_bytes(), original)
        self.set_page([self.a])
        self.assertEqual(self.run_sync()["since"], first["watermark"])
        for bad in ({**self.b, "currency": "EUR"}, {**self.a, "units": 70}, {**self.b, "deleted": True}):
            self.set_page([bad])
            with self.assertRaises(ValueError):
                self.run_sync()
        self.set_page([self.b], "repeat")
        self.set_page([], "repeat", "repeat")
        with self.assertRaisesRegex(ValueError, "游标"):
            self.run_sync()
        self.assertEqual(file.read_bytes(), original)

    def test_publish_failure_recovered_from_local_journal(self):
        self.set_page([self.a])
        with (
            mock.patch.object(os, "replace", side_effect=OSError("read-only output")),
            self.assertRaises(OSError),
        ):
            self.run_sync()
        self.assertFalse(list(self.out.glob("*.json")))
        self.set_page([])
        self.run_sync()
        self.assertEqual(self.ingest(), (1, (1, 2, 1015)))
        file = self.out / "2026-11-01.json"
        original = file.read_bytes()
        file.unlink()
        self.assertEqual(self.run_sync(backfill=self.cfg["initial_since"])["changed"], 0)
        self.assertEqual(file.read_bytes(), original)
        with self.assertRaisesRegex(ValueError, "独立目录"):
            supplier.sync({**self.cfg, "source": "other-shop"}, self.out, now=FIXTURE_NOW)
        with closing(sqlite3.connect(self.out / ".supplier.sqlite3")) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM pending").fetchone()[0], 0)

    def test_late_arrival_and_equivalent_amount_on_existing_checkpoint(self):
        latest = {**self.b, "updated_at": "2026-11-02T10:00:00Z"}
        self.set_page([self.a, latest])
        saved = self.run_sync()
        self.cfg["lookback_seconds"] = 3600
        self.set_page([{**self.a, "amount": "10.150"}, {**latest, "amount": 11.31}])
        self.assertEqual(self.run_sync()["changed"], 0)
        self.assertEqual(self.requests[-1]["updated_since"], ["2026-11-02T09:00:00.000000Z"])
        self.set_page([{**self.a, "units": 9, "updated_at": "2026-11-02T09:30:00Z"}])
        fixed = self.run_sync()
        self.assertEqual((fixed["changed"], fixed["watermark"]), (1, saved["watermark"]))
        self.assertEqual(self.ingest(), (2, (2, 12, 2146)))

    def test_declared_count_truncated_pages_and_bad_timestamps_preserve_state(self):
        self.set_page([self.a])
        saved = self.run_sync()
        file = self.out / "2026-11-01.json"
        original = file.read_bytes()
        self.cfg["total_path"] = "page.total"
        self.set_page([{**self.b, "updated_at": "2026-11-03T10:00:00Z"}])
        self.pages[""][1]["page"]["total"] = 2
        with self.assertRaisesRegex(ValueError, "总行数"):
            self.run_sync()
        for bad in ("2026-11-03T10:00:00+04:99", "2099-01-01T00:00:00Z"):
            self.set_page([{**self.b, "updated_at": bad}])
            self.pages[""][1]["page"]["total"] = 1
            with self.assertRaises(ValueError):
                self.run_sync()
        self.set_page([self.a], "b")
        self.set_page([self.a], key="b")
        for _, page in self.pages.values():
            page["page"]["total"] = 2
        with self.assertRaisesRegex(ValueError, "重复交付"):
            self.run_sync()
        self.assertEqual(file.read_bytes(), original)
        self.pages["b"][1]["page"]["rows"] = [self.b]
        result = self.run_sync()
        self.assertEqual((result["since"], result["changed"]), (saved["watermark"], 1))

    def test_supplier_native_json_decimals_reach_feed_exactly(self):
        def native_page(row, literal):
            page = {"page": {"rows": [row], "next": None}}
            return json.dumps(page).replace('"raw_literal"', literal).encode()

        row = {**self.a, "amount": "raw_literal"}
        self.pages[""] = (200, native_page(row, "99999999999998.99"))
        saved = self.run_sync()
        self.assertEqual(self.ingest(), (1, (1, 2, 9999999999999899)))
        later = {**row, "updated_at": "2026-11-04T10:00:00Z"}
        self.pages[""] = (200, native_page(later, "1.00000000000000000000000000001"))
        with self.assertRaisesRegex(ValueError, "精度"):
            self.run_sync()
        self.pages[""] = (200, native_page({**self.b, "product": {"id": "raw_literal", "title": "B"}}, "1.25"))
        with self.assertRaisesRegex(ValueError, "id"):
            self.run_sync()
        self.set_page([])
        self.assertEqual(self.run_sync()["watermark"], saved["watermark"])
        self.assertEqual(self.ingest(), (0, (1, 2, 9999999999999899)))

    def test_fourteen_days_against_expected_local_currency_totals(self):
        days = [(date(2026, 10, 1) + timedelta(days=i)).isoformat() for i in range(14)]
        rows = []
        manifest = [",".join(reconciliation.FIELDS)]
        for i, day in enumerate(days, start=1):
            rows.extend(
                [
                    {**self.a, "day": day, "units": i, "amount": f"{2 * i}.17"},
                    {**self.b, "day": day, "units": 3, "amount": "3.96"},
                ]
            )
            manifest.append(f"contract-us,US,{day},Synthetic,2,{i + 3},{2 * i + 4}.13")
        self.set_page(rows[:11], "second")
        self.set_page(rows[11:], key="second")
        self.assertEqual(self.run_sync()["changed"], 28)
        self.assertEqual(self.ingest()[0], 28)
        reconciliation.load_file(self.db, ("\n".join(manifest) + "\n").encode())
        result = reconciliation.report(self.db, "contract-us", "US", days[0], days[-1])
        self.assertEqual(result["counts"]["matched"], 14)
        self.assertTrue(result["matched"])


if __name__ == "__main__":
    main()

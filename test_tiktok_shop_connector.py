"""Exercise the Shop CLI and feed importer against a loopback seller API."""
import hashlib
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from urllib.parse import parse_qs, urlencode, urlsplit

import analytics
from connectors import tiktok_shop as shop
import feeds
import source_reconciliation


class ShopFixture(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        req = urlsplit(self.path)
        q = {k:v[0] for k,v in parse_qs(req.query).items()}
        ctx = self.server.case
        ctx.calls.append((req.path, q))
        try:
            if req.path.startswith("/api/v2/token/"):
                refresh = req.path.endswith("/refresh")
                ctx.assertEqual(q["app_secret"], "fixture-secret")
                ctx.assertEqual(q["grant_type"], "refresh_token" if refresh else "authorized_code")
                ctx.assertEqual(q["refresh_token" if refresh else "auth_code"], "refresh-one" if refresh else "temp-code")
                data = {"open_id":"seller","user_type":0,"access_token":"renewed" if refresh else "first",
                        "refresh_token":"refresh-two" if refresh else "refresh-one",
                        "access_token_expire_in":int(time.time()) + (3600 if refresh else 40),
                        "refresh_token_expire_in":int(time.time()) + 8000}
            else:
                sig = q.pop("sign")
                message = "fixture-secret" + req.path + "".join(k+q[k] for k in sorted(q)) + "fixture-secret"
                ctx.assertEqual(sig, hmac.new(b"fixture-secret",message.encode(),hashlib.sha256).hexdigest())
                allowed = {"first","renewed"} if req.path == shop.SHOPS else {"renewed"}
                ctx.assertIn(self.headers["x-tts-access-token"], allowed)
                ctx.assertEqual(self.headers["Content-Type"], "application/json")
                if req.path == shop.SHOPS:
                    data = {"shops":[{"id":"100","region":ctx.region,"name":"Fake seller","cipher":"shop-cipher"}]}
                else:
                    ctx.assertEqual(req.path, shop.PRODUCTS)
                    if ctx.throttle:
                        ctx.throttle = False
                        self.send_response(429)
                        self.send_header("Retry-After", "0")
                        self.end_headers()
                        return
                    ctx.assertEqual(q["shop_cipher"], "shop-cipher")
                    ctx.assertEqual(q["currency"], "LOCAL")
                    ctx.assertEqual(q["product_status_filter"], "ALL")
                    day = q["start_date_ge"]
                    ctx.assertEqual(q["end_date_lt"], (shop.date.fromisoformat(day)+shop.timedelta(days=1)).isoformat())
                    second = q.get("page_token")
                    ctx.assertIn(second, (None,"next/+"))
                    idx = 1 if second else 0
                    items = ctx.rows.get(day, [])
                    row = items[idx:idx+1]
                    data = {"products":row, "total_count":len(items),
                            "next_page_token":"next/+" if len(items) > idx+1 else "",
                            "latest_available_date":ctx.ready}
                    if day == ctx.fault and second:
                        data["total_count"] += 1
            result = {"code":0, "data":data}
        except Exception as exc:
            ctx.fixture_errors.append(str(exc))
            result = {"code":400, "data":{}}
        self.send_response(200)
        self.end_headers()
        body = json.dumps(result).replace('"RAW_DECIMAL_FIXTURE"', '99999999999999.01')
        self.wfile.write(body.encode())


def product(pid, amount="3.45", qty=2, currency="USD"):
    return {"id":pid, "total_performance":{"gmv":{"amount":amount,"currency":currency},"items_sold":qty,
                                          "orders":1,"sku_orders":9,"refunded_items":0},
            "seller_live_performance":{"attributed_gmv":{"amount":"100","currency":currency}}}


class ShopConnectorTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.folder, self.private = self.root/"drop", self.root/"private"
        self.cfg = self.root/"config.json"
        self.cfg.write_text(json.dumps({"source":"shop-fixture","market":"US","shop_id":"100",
            "timezone":"America/New_York","start_date":"2025-03-08","directory":str(self.folder),
            "private_dir":str(self.private),"lookback_days":0,
            "authorization_url":"https://services.us.tiktokshop.com/open/authorize?service_id=service",
            "redirect_uri":"https://example.test/callback"}))
        self.calls, self.fixture_errors = [], []
        self.region, self.ready, self.fault = "US","2025-03-10",None
        self.throttle = False
        self.rows = {"2025-03-08":[product("0001"),product("0002")],
                     "2025-03-09":[product("0001","4.56"),product("0002","2.34")]}
        httpd = ThreadingHTTPServer(("127.0.0.1",0), ShopFixture)
        httpd.case = self
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(thread.join)
        self.addCleanup(httpd.server_close)
        self.addCleanup(httpd.shutdown)
        self.addr = "http://127.0.0.1:" + str(httpd.server_port)

    def cli(self, *args, succeeds=True, callback=""):
        env = {"PATH":os.environ["PATH"],"TIKTOK_SHOP_APP_KEY":"fixture-key","TIKTOK_SHOP_APP_SECRET":"fixture-secret",
               "TIKTOK_SHOP_CALLBACK_URL":callback,"TIKFLOWSO_ENV_FILE":os.devnull,"PYTHONDONTWRITEBYTECODE":"1"}
        proc = subprocess.run([sys.executable,"-m","connectors.tiktok_shop","--config",str(self.cfg),
                               "--fixture-url",self.addr,*args],cwd=Path(shop.__file__).resolve().parents[1],
                              capture_output=True, text=True, env=env, timeout=10)
        self.assertEqual(proc.returncode == 0, succeeds, proc.stderr)
        self.assertEqual(self.fixture_errors, [])
        self.assertNotIn("fixture-secret",proc.stderr+proc.stdout)
        return proc.stdout.strip() if succeeds else proc.stderr

    def authorize(self):
        link = self.cli("authorize-url")
        nonce = parse_qs(urlsplit(link).query)["state"][0]
        self.cli("authorize", succeeds=False, callback="https://example.test/callback?code=temp-code&state=wrong")
        self.assertFalse(self.calls)
        self.cli("authorize", callback="https://example.test/callback?"+urlencode({"code":"temp-code","state":nonce}))
        self.assertEqual((self.private/"seller-tokens.json").stat().st_mode & 0o777, 0o600)

    def test_official_get_signature(self):
        self.assertEqual(shop.signature(shop.SHOPS,{"timestamp":"1623812664","app_key":"29a39d"},"e59af819cc"),
                         "b596b73e0cc6de07ac26f036364178ab16b0a907af13d43f0a0cd2345f582dc8")

    def test_resume_replay_and_feed_import(self):
        self.authorize()
        self.fault = "2025-03-09"
        self.cli("sync","--until","2025-03-09", succeeds=False)
        self.assertTrue((self.folder/"2025-03-08.json").exists())
        self.assertFalse((self.folder/"2025-03-09.json").exists())
        self.fault = None
        self.throttle = True
        resumed = json.loads(self.cli("sync","--until","2025-03-10"))
        self.assertEqual([resumed[k] for k in ("published","skipped","empty")], [1,1,1])
        self.assertFalse((self.folder/"2025-03-10.json").exists())
        self.assertEqual(sum(path.endswith("/refresh") for path,_ in self.calls),1)
        self.assertEqual(json.loads(self.cli("sync","--until","2025-03-10"))["skipped"],3)
        missing_file = self.folder/"2025-03-08.json"
        original = missing_file.read_bytes()
        missing_file.unlink()
        self.assertEqual(json.loads(self.cli("sync","--until","2025-03-10"))["published"],1)
        self.assertEqual(missing_file.read_bytes(), original)
        feeds_file = self.root/"feeds.json"
        feeds_file.write_text(json.dumps([{"id":"fixture","source":"shop-fixture","directory":str(self.folder)}]))
        db = sqlite3.connect(":memory:")
        self.addCleanup(db.close)
        db.executescript(analytics.SCHEMA)
        def ingest():
            result = feeds.sync_configured(db, force=True, config_path=feeds_file)[0]
            self.assertEqual(result["status"], "ok", result)
            return result["rows"]
        self.assertEqual(ingest(),4)
        self.assertEqual(ingest(),0)
        self.assertEqual(db.execute("SELECT name,sales,gmv_units,orders,refund_units,shop_id FROM analytics_daily "
                                    "WHERE id='0001' AND date='2025-03-09'").fetchone(), ("0001",2,456,1,0,"100"))
        self.rows["2025-03-09"][0] = product("0001","5.67",3)
        self.cli("sync","--since","2025-03-09","--until","2025-03-09")
        self.assertEqual(ingest(),2)
        self.assertEqual(db.execute("SELECT SUM(gmv_units),SUM(sales) FROM analytics_daily WHERE date='2025-03-09'").fetchone(),(801,5))
        self.rows["2025-03-09"].pop()
        self.assertIn("disappeared",self.cli("sync","--since","2025-03-09","--until","2025-03-09",succeeds=False))
        self.assertEqual(ingest(),0)

    def test_invalid_shop_currency_and_unavailable_date_do_not_publish(self):
        self.authorize()
        self.region = "GB"
        self.assertIn("authorized shop", self.cli("sync","--until","2025-03-08",succeeds=False))
        self.region = "US"
        self.ready = "2025-03-07"
        self.assertIn("not ready", self.cli("sync","--until","2025-03-08",succeeds=False))
        self.ready = "2025-03-08"
        self.rows["2025-03-08"][1] = product("0002",currency="GBP")
        self.assertIn("currency", self.cli("sync","--until","2025-03-08",succeeds=False))
        self.assertFalse((self.folder/"2025-03-08.json").exists())
        self.assertEqual(json.loads((self.folder/".tiktok-shop.json").read_text())["days"],{})

    def test_numeric_amount_preserves_minor_units_in_feed(self):
        self.authorize()
        day = "2025-03-08"
        self.rows[day] = [product("0001", "RAW_DECIMAL_FIXTURE")]
        self.cli("sync", "--until", day)
        row, = json.loads((self.folder/(day+".json")).read_bytes())
        self.assertEqual(analytics.numeric(row["gmv"], "gmv", money=True), 9999999999999901)

    def test_replay_after_interrupted_checkpoint_keeps_newly_delivered_product(self):
        self.authorize()
        day = "2025-03-08"
        first = product("0001")
        self.rows[day] = [first]
        self.cli("sync", "--until", day)
        checkpoint = self.folder/".tiktok-shop.json"
        previous = checkpoint.read_bytes()
        self.rows[day].append(product("0002"))
        self.cli("sync", "--since", day, "--until", day)
        delivery = self.folder/(day+".json")
        published = delivery.read_bytes()
        # The new file was visible to the importer before the collector persisted its receipt.
        checkpoint.write_bytes(previous)
        self.rows[day] = [first]
        error = self.cli("sync", "--since", day, "--until", day, succeeds=False)
        self.assertIn("disappeared", error)
        self.assertEqual(delivery.read_bytes(), published)
        self.assertEqual(checkpoint.read_bytes(), previous)

    def test_credential_and_feed_paths_are_disjoint(self):
        cfg = json.loads(self.cfg.read_text())
        for private in (self.folder, self.folder/"private", self.folder.parent):
            with self.subTest(private=private), self.assertRaisesRegex(ValueError,"disjoint"):
                shop.configure({**cfg, "private_dir":str(private)})

    def test_fourteen_shop_days_against_independent_synthetic_controls(self):
        start = shop.date(2025,3,8)
        dates = [str(start+shop.timedelta(days=i)) for i in range(14)]
        self.ready = dates[-1]
        self.rows = {day:[product("0001","3.45",2),product("0002","8.65",3)] for day in dates}
        self.authorize()
        run = json.loads(self.cli("sync","--until",dates[-1]))
        self.assertEqual(run["published"],14)
        db = sqlite3.connect(":memory:")
        self.addCleanup(db.close)
        db.executescript(analytics.SCHEMA)
        feed = self.root/"feeds.json"
        feed.write_text(json.dumps([{"id":"fixture","source":"shop-fixture","directory":str(self.folder)}]))
        self.assertEqual(feeds.sync_configured(db, force=True, config_path=feed)[0]["rows"],28)
        # The independent controls are specified separately from the source response and collector.
        csv = ["source,market,date,shop_scope,product_rows,sales,gmv"]
        csv.extend(f"shop-fixture,US,{day},Synthetic store,2,5,12.10" for day in dates)
        source_reconciliation.load_file(db, "\n".join(csv).encode())
        report = source_reconciliation.report(db,"shop-fixture","US",dates[0],dates[-1])
        self.assertEqual(report["counts"],{"matched":14,"missing":0,"mismatch":0,"unverified":0})
        expected = {"product_rows":2,"sales":5,"gmv":"12.10"}
        for day, row in zip(dates,report["days"],strict=True):
            self.assertEqual((row["date"],row["actual"],row["expected"]),(day,expected,expected))

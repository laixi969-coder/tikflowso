import json
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from urllib.request import Request

import analytics
import feeds
import workspace
from datetime import datetime, timezone


class LicensedFeedTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.drop = self.root / "delivery"
        self.drop.mkdir()
        self.cfg = self.root / "feeds.json"
        self.cfg.write_text(json.dumps([{"id":"license","source":"ws-1-license","owner":1,"directory":str(self.drop)}]))
        self.db = sqlite3.connect(":memory:")
        self.addCleanup(self.db.close)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(analytics.SCHEMA)
        workspace.init(self.db)
        self.db.execute("INSERT INTO users(id,email,name) VALUES(1,'owner@example.invalid','Owner')")
        self.db.commit()

    def sync(self, force=True):
        return feeds.sync_configured(self.db,force=force,config_path=self.cfg)

    def test_due_dates_first_receipt_late_and_absent_batches(self):
        config=json.loads(self.cfg.read_text())
        config[0]["daily_delivery"]={"due_utc":"12:00","lag_days":1,"markets":["US","GB"]}
        self.cfg.write_text(json.dumps(config))
        def stamp(day,hour):
            return int(datetime(2026,11,day,hour,tzinfo=timezone.utc).timestamp())
        file=self.drop/"daily.json"
        row={"market":"GB","kind":"products","id":"x","name":"Demo","date":"2026-11-01","sales":2,"gmv":15}
        with patch("feeds.time.time",return_value=stamp(2,9)):
            file.write_text(json.dumps([row]))
            self.sync()
        with patch("feeds.time.time",return_value=stamp(3,13)):
            file.write_text(json.dumps([row,{**row,"date":"2026-11-02"}]))
            self.sync()
            self.sync()
        self.db.execute("DELETE FROM feed_arrivals WHERE day='2026-11-02'")
        self.db.execute("UPDATE feed_items SET arrivals_logged=0")
        self.db.commit()
        with patch("feeds.time.time",return_value=stamp(4,13)):
            self.assertEqual(self.sync()[0]["rows"],0)
        gb,us=feeds.delivery_health(self.db,1,stamp(4,13))
        self.assertEqual([h["status"] for h in gb["history"]],["missing","late","on_time"])
        self.assertEqual(gb["history"][1]["received"],stamp(3,13))
        self.assertEqual((gb["on_time"],gb["expected"],us["on_time"]),(1,3,0))
        self.assertEqual(feeds.delivery_health(self.db,2,stamp(4,13)),[])
        self.assertEqual(feeds.delivery_health(self.db,1,stamp(2,11))[0]["expected"],0)
        with self.assertRaises(ValueError):
            feeds.valid_config([{**config[0],"daily_delivery":{"due_utc":"25:00","lag_days":0,"markets":["US"]}}])

    def test_idempotent_revision_and_retry(self):
        file = self.drop / "daily.csv"
        header = "market,kind,id,name,date,gmv,sales\n"
        row = "US,products,p1,Pen,2026-11-01,11.20,2\n"
        file.write_text(header+row)
        self.assertEqual(self.sync()[0]["rows"],1)
        self.assertEqual(self.sync(force=False),[])
        self.assertEqual(self.sync()[0]["rows"],0)
        file.write_text(header+row.replace("11.20","10.50")+"US,products,b,B,broken,3,1")
        self.assertEqual(self.sync()[0]["status"],"error")
        self.assertEqual(self.db.execute("SELECT gmv_units FROM analytics_daily").fetchone()[0],1120)
        file.write_text(header+row.replace("11.20","10.50"))
        self.assertEqual(self.sync()[0]["rows"],1)
        self.assertEqual(self.db.execute("SELECT gmv_units FROM analytics_daily").fetchone()[0],1050)
        # A provider legitimately restores an older version of the same delivery.
        file.write_text(header+row)
        self.assertEqual(self.sync()[0]["rows"],1)

    def test_json_decimal_and_malformed_files_do_not_advance_receipts(self):
        file=self.drop/"precise.json"
        def content(gmv, identifier='"sample"'):
            return ('[{"market":"US","kind":"products","id":'+identifier+',"name":"Sample",'
                    '"date":"2026-11-01","sales":1,"gmv":'+gmv+'}]')
        file.write_text(content("99999999999998.99"))
        self.assertEqual(self.sync()[0]["rows"],1)
        self.assertEqual(self.db.execute("SELECT gmv_units FROM analytics_daily").fetchone()[0],9999999999999899)
        receipt=self.db.execute("SELECT digest FROM feed_items").fetchone()[0]
        for invalid in (content("1.000000000000000001"),content("1.00000000000000000000000000001"),content("1","1.25")):
            file.write_text(invalid)
            self.assertEqual(self.sync()[0]["status"],"error")
            self.assertEqual(self.db.execute("SELECT digest FROM feed_items").fetchone()[0],receipt)
        file.unlink()
        csv_file=self.drop/"unequal.csv"
        fields="market,kind,id,name,date,sales,gmv"
        row="US,products,sample,Sample,2026-11-01,1,3"
        for bad_csv in (fields+"\n"+row+",99", fields+",sales\n"+row+",99", fields+",category\n"+row):
            csv_file.write_text(bad_csv)
            self.assertEqual(self.sync()[0]["status"],"error")
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM feed_items").fetchone()[0],1)
        self.assertEqual(self.db.execute("SELECT gmv_units FROM analytics_daily").fetchone()[0],9999999999999899)

    def test_remote_requires_configured_token_and_rejects_cross_origin(self):
        self.cfg.write_text(json.dumps([{"id":"x","source":"supplier","url":"https://licensed.example/delivery.json",
                                        "token_env":"TIKFLOWSO_TEST_TOKEN_MISSING"}]))
        with patch.dict(os.environ,{},clear=True):
            self.assertEqual(self.sync()[0]["status"],"error")
        with self.assertRaises(ValueError):
            feeds.SameOriginRedirects().redirect_request(Request("https://licensed.example/a"),None,302,
                                                         None,{},"https://elsewhere.example/b")
        with self.assertRaises(ValueError):
            feeds.SameOriginRedirects().redirect_request(Request("https://licensed.example/a"),None,302,
                                                         None,{},"http://licensed.example/b")

    def test_market_window_and_explicit_dated_fx(self):
        records = [{"market":"US","kind":"products","id":"a","name":"A","date":"2026-11-01","gmv":10,"sales":2},
                   {"market":"GB","kind":"products","id":"b","name":"B","date":"2026-11-02","gmv":10,"sales":1}]
        analytics.import_rows(self.db,records,"fxsample")
        file = self.root / "rates.json"
        file.write_text(json.dumps({"base_currency":"USD","dates":{"2026-11-02":{"GBP":"1.25"}}}))
        with patch.dict(os.environ,{"TIKFLOWSO_FX_RATES":str(file)}):
            response = analytics.handle(self.db,"/api/markets",{"source":"fxsample","days":"1"})
            self.assertEqual(response["date"],"2026-11-02")
            gb,us = response["items"]
            self.assertEqual((gb["market"],gb["gmv_converted"],gb["avg_price"]),("GB",12.5,10))
            self.assertEqual((us["market"],us["gmv"],us["covered_days"]),("US",None,0))
            past = analytics.handle(self.db,"/api/markets",{"source":"fxsample","date":"2026-11-01"})
            self.assertTrue(all(row["fx_rate"] is None for row in past["items"]))

    def test_optional_profile_and_competition(self):
        self.cfg.write_text(json.dumps([{"id":"x","source":"supplier","url":"https://licensed.example/data.json"}]))
        records = [{"market":"US","kind":"products","id":"p1","name":"A","date":"2026-11-01","gmv":10,
                    "sales":2,"category":"stationery","price":5,"profile":{"reviews":[{"text":"好","rating":4}]}},
                   {"market":"US","kind":"shops","id":"s1","name":"Store","date":"2026-11-01","gmv":10,"sales":2}]
        with patch.object(feeds,"download",return_value=json.dumps(records).encode()):
            self.assertEqual(self.sync()[0]["rows"],2)
        scope = {"source":"supplier"}
        profile = analytics.handle(self.db,"/api/detail",{**scope,"id":"p1"})["item"]["profile"]
        self.assertEqual(profile["reviews"][0]["rating"],4)
        category = analytics.handle(self.db,"/api/trends",scope)
        self.assertEqual(category["concentration"]["shop_top3_share"],100)
        self.assertEqual(category["items"][0]["examples"][0]["id"],"p1")
        self.assertEqual(category["price_bands"][0]["count"],1)

"""End-to-end regression tests for workspace ownership and the research workflow."""
from contextlib import closing
import csv
from http.cookiejar import CookieJar
from http.server import ThreadingHTTPServer
import io
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import build_opener, HTTPCookieProcessor, Request

import server
import research_usage
import privacy


class WorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory()
        cls.settings=patch.object(server,"DATABASE",Path(cls.tmp.name)/"test.db")
        cls.settings.start()
        cls.env=patch.dict(os.environ,{"TIKFLOWSO_PUBLIC_URL":"","TIKFLOWSO_MODEL_URL":"","STRIPE_SECRET_KEY":""})
        cls.env.start()
        server.initialize()
        cls.host=ThreadingHTTPServer(("127.0.0.1",0),server.Handler)
        cls.addr="http://127.0.0.1:"+str(cls.host.server_port)
        cls.thread=threading.Thread(target=cls.host.serve_forever,daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.host.shutdown()
        cls.host.server_close()
        cls.thread.join()
        cls.settings.stop()
        cls.env.stop()
        cls.tmp.cleanup()

    def call(self,client,path,data=None,headers=None,expected=200):
        req=Request(self.addr+path,data=data if data is None or isinstance(data,bytes) else json.dumps(data).encode(),
                    headers={"Content-Type":"application/json",**(headers or {})})
        try: response=client.open(req)
        except HTTPError as exc: response=exc
        with response:
            body=response.read()
            self.assertEqual(response.status,expected,body[:1500])
            if response.headers.get_content_type()=="application/json": return json.loads(body)
            return body

    def client(self):
        return build_opener(HTTPCookieProcessor(CookieJar()))

    def test_inspiration_uses_scoped_products_and_works_without_market_samples(self):
        owner,guest=self.client(),self.client()
        self.call(owner,"/api/register",{"email":"ideas@example.test","name":"Ideas","password":"ideas-fixture-123"})
        rows=[dict(market="GB",kind="products",id="bag",name="帆布通勤包",date="2026-10-01",gmv=1,sales=1),
              dict(market="GB",kind="products",id="lamp",name="阅读台灯",date="2026-10-02",gmv=50,sales=5)]
        source=self.call(owner,"/api/import",{"source":"ideas","filename":"products.json","rows":rows})["source"]
        path="/api/inspiration?source="+source+"&market=GB&days=1"
        cards=self.call(owner,path+"&date=2026-10-01")["cards"]
        self.assertEqual({card["subject"] for card in cards},{"帆布通勤包"})
        self.assertEqual(len({card["title"] for card in cards}),3)
        self.assertIn("门卡",cards[0]["hook"])
        self.assertTrue(all(card["product"]["id"]=="bag" and all(card[k] for k in ("first","action","reveal")) for card in cards))
        self.call(guest,path,expected=403)
        empty=self.call(owner,path+"&date=2026-09-01")
        self.assertFalse(empty["products"])
        self.assertEqual(empty["cards"], [])
        self.call(guest,"/api/inspiration/videos?source="+source,expected=403)
        custom=self.call(guest,"/api/inspiration?subject=reading+light&locale=en-US")["cards"]
        self.assertEqual(len(custom),3)
        self.assertTrue(all(card["subject"]=="reading light" and card["product"] is None for card in custom))
        self.assertIn("shadow",custom[0]["reveal"])
        urls=set()
        for subject,prefix in (("shoulder+bag","bag-"),("desk+lamp","lamp-"),("water+bottle","bottle-")):
            page=self.call(guest,"/api/inspiration?subject="+subject)
            for card in page["cards"]:
                self.assertTrue(card["topic"].startswith(prefix))
                self.assertTrue(card["references"])
                for ref in card["references"]:
                    self.assertEqual(card["topic"],ref["topic"])
                    self.assertNotIn(ref["url"],urls)
                    self.assertLessEqual(ref["published"],ref["added"])
                    self.assertLessEqual(ref["added"],page["references_reviewed"])
                    self.assertTrue(all(ref[k] for k in ("title","author","platform","zh","en")))
                    urls.add(ref["url"])
        unrelated=self.call(guest,"/api/inspiration?subject=unknown")["cards"]
        self.assertTrue(all(not r["references"] and r["topic"] is None for r in unrelated))
        with patch.object(server.studio,"model_configured",return_value=False), patch.object(server.studio,"destination",return_value=None):
            result=self.call(owner,"/api/generate",{"tool":"ideas","text":"宿舍学生的早八","locale":"zh-CN"})
        self.assertIn("宿舍桌面",result["result"])
        self.assertEqual(result["result"].count("收尾画面"),3)

    def test_board_live_preview_filters_provider_measurements_to_reported_session(self):
        owner=self.client()
        self.call(owner,"/api/register",{"email":"liveboard@example.test","password":"stream-data-123","name":"Board"})
        room={"market":"GB","kind":"lives","id":"event","name":"Fixture room","date":"2026-10-01","gmv":4,"sales":1,
              "profile":{"live_session":{"start_at":"2026-10-01T11:00+01:00","end_at":"2026-10-01T11:30+01:00"}}}
        source=self.call(owner,"/api/import",{"source":"events","filename":"rooms.json","rows":[room]})["source"]
        with patch.dict(os.environ,{"TIKFLOWSO_STREAM_TOKEN":"local-fixture","TIKFLOWSO_STREAM_SOURCE":source}):
            points=[{"market":"GB","kind":"lives","id":"event","metric":"online_viewers","time":time,"value":value}
                    for time,value in [("2026-10-01T09:59Z",99),("2026-10-01T10:00Z",0),("2026-10-01T10:30Z",3),("2026-10-01T10:31Z",88)]]
            self.call(owner,"/api/stream",{"points":points},headers={"Authorization":"Bearer local-fixture"})
        path="/api/overview?live_only=1&market=GB&source="+source+"&date=2026-10-01&days=1"
        preview=self.call(owner,path)["live_preview"]["room"]
        self.assertEqual((preview["series_source"],preview["series_basis"],[p["value"] for p in preview["series"]]),("stream","session",[0,3]))
        self.assertIsNone(preview["enter_count"])
        self.call(self.client(),path,expected=403)

    def test_import_history_revision_and_monitor_lag(self):
        owner,other=self.client(),self.client()
        self.call(owner,"/api/register",{"email":"audit@example.test","password":"audit-file-123","name":"A"})
        row=dict(market="GB",kind="shops",id="a",name="Old",gmv=10,sales=1,date="2026-10-01")
        batch={"source":"audit","filename":"test.json","rows":[row]}
        result=self.call(owner,"/api/import",batch)
        self.assertEqual((result["kind"],result["market"]),("shops","GB"))
        source=result["source"]
        for _ in range(2):self.call(owner,"/api/import",{**batch,"rows":[{**row,"gmv":15}]})
        self.call(owner,"/api/import",{**batch,"rows":[{**row,"gmv":55},{**row,"sales":-1}]},expected=400)
        self.call(owner,"/api/import",{"source":"audit","json":"[bad","filename":"bad.json"},expected=400)
        later={**row,"kind":"products","id":"p","date":"2026-10-03"}
        self.call(owner,"/api/import",{**batch,"rows":[{**later,"date":"2026-10-01"},{**later,"id":"q"}]})
        self.call(owner,"/api/favorites",{**row,"source":source,"days":1})
        self.call(owner,"/api/monitors",{**later,"source":source,"threshold":10})
        saved=self.call(owner,"/api/favorites")["items"][0]
        self.assertEqual((saved["date"],saved["days"],saved["name"]),("2026-10-01",1,"Old"))
        mon=self.call(owner,"/api/monitors")["items"][0]
        self.assertEqual((mon["source_latest"],mon["observation_lag_days"],mon["readings"][0]["hit"]),("2026-10-03",2,0))
        history=self.call(owner,"/api/imports")
        failures=[r for r in history["items"] if r["status"]=="failed"]
        self.assertEqual(len(failures),2)
        self.assertIn("第 2 行",failures[1]["error"])
        self.assertEqual(history["revisions"][0]["changes"],{"gmv_units":[1000,1500]})
        self.assertEqual(len(history["revisions"]),1)
        coverage=[r for r in history["coverage"] if r["source"]==source]
        self.assertEqual([(r["market"],r["day"],r["rows"]) for r in coverage],[("GB","2026-10-03",1)])
        self.assertNotIn(source,json.dumps(self.call(other,"/api/imports")))

    def test_decimal_json_survives_both_import_formats_and_counter_conversion(self):
        owner = self.client()
        self.call(owner, "/api/register", {"email":"decimal@example.test","password":"decimal-file-123","name":"D"})
        row = dict(market="US",kind="products",id="p",name="Precise",gmv="AMOUNT",sales=1,date="2026-11-01")
        content = json.dumps([row]).replace('"AMOUNT"', '99999999999999.01')
        direct = ('{"source":"decimal","rows":'+content+'}').encode()
        for data in (direct, {"source":"decimal","json":content}):
            result = self.call(owner, "/api/import", data)
            with closing(server.connect()) as db:
                actual = db.execute("SELECT gmv_units FROM analytics_daily WHERE source=?",(result["source"],)).fetchone()[0]
            self.assertEqual(actual, 9999999999999901)
        self.call(owner,"/api/import",{"source":"decimal","json":content,"rows":[]},expected=400)
        self.call(owner,"/api/import",{"source":"decimal","json":content.replace('"id": "p"', '"id": 1.5')},expected=400)
        counters = [{**row,"date":day,"price":"AMOUNT","cumulative_gmv":total,"cumulative_sales":sales}
                    for day,total,sales in (("2026-11-01",1,1),("2026-11-02","AMOUNT",2))]
        for item in counters:
            del item["gmv"],item["sales"]
        raw = json.dumps(counters).replace('"AMOUNT"','99999999999999.01')
        converted = self.call(owner, "/api/normalize-snapshots",{"json":raw})["rows"][0]
        self.assertEqual((converted["gmv"],converted["price"]), ("99999999999998.01","99999999999999.01"))
        self.call(owner,"/api/normalize-snapshots",{"csv":'id,name\np,"unfinished'},expected=400)

    def test_auto_queued_export_keeps_date_from_first_query(self):
        client = self.client()
        self.call(client, "/api/register", {"email":"queue-date@example.test","password":"queue-date-abc123","name":"D"})
        row = dict(market="US",kind="products",id="p",name="Product",gmv=12,sales=1,date="2026-11-01")
        source = self.call(client,"/api/import",{"source":"rolling","rows":[row]})["source"]
        submit = server.export_jobs.submit
        def submit_after_delivery(db, user, data):
            server.analytics.import_rows(db, [{**row,"date":"2026-11-02"}], source, owner=server.ws.workspace(user))
            return submit(db,user,data)
        with patch.object(server,"csv_export",side_effect=server.QueueExport), patch.object(server.export_jobs,"submit",submit_after_delivery):
            job = self.call(client,"/api/export?market=US&source="+source,expected=202)["job"]
        jobs = self.call(client,"/api/exports")["items"]
        self.assertEqual(next(r["params"]["date"] for r in jobs if r["job"]==job), row["date"])

    def test_api_minute_limit_shared_between_keys_and_reset(self):
        owner=self.client()
        self.call(owner,"/api/register",{"email":"rate@example.test","password":"rate-test-123","name":"A"})
        tokens=[self.call(owner,"/api/keys",{"label":s})["key"] for s in ("one","two")]
        def headers(i):
            return {"Authorization":"Bearer "+tokens[i]}
        import time
        stamp=int(time.time())//60*60+15
        with patch.object(server.ws,"now",return_value=stamp):
            for n in range(60):self.call(owner,"/api/v1/meta",headers=headers(n%2))
            with self.assertRaises(HTTPError) as denied:
                owner.open(Request(self.addr+"/api/v1/meta",headers=headers(0)))
            with denied.exception as response:
                self.assertEqual((response.code,response.headers["Retry-After"]),(429,"45"))
                self.assertEqual(json.load(response)["retry_after"],45)
            self.assertEqual(self.call(owner,"/api/me")["usage"]["api"],60)
        with patch.object(server.ws,"now",return_value=stamp+60):
            self.call(owner,"/api/v1/meta",headers=headers(1))
        self.assertEqual(self.call(owner,"/api/me")["usage"]["api"],61)

    def test_weekly_research_cohorts_and_replayed_actions(self):
        from datetime import datetime,timezone
        with closing(server.connect()) as db, db:
            monday=int(datetime(2026,11,16,9,tzinfo=timezone.utc).timestamp())
            scope={"source":"demo","market":"US","date":"2026-11-15","days":7}
            def event(owner,action,item="",offset=0,changes=None):
                research_usage.record(db,owner,{**scope,**(changes or {})},action,item,monday+offset)
            event(1001,"list");event(1001,"save","A")
            event(1001,"detail","A");event(1001,"save","B")
            event(1001,"save","A",changes={"days":14})
            self.assertEqual(research_usage.weekly(db,"2026-11-16")["items"][0]["first_completed"],0)
            event(1001,"save","A");event(1001,"save","A")
            event(1001,"list",offset=86400);event(1002,"detail","B")
            for action in ("list","detail","export"):event(1003,action,"B",changes={"source":"import"})
            demo,imported=research_usage.weekly(db,"2026-11-18")["items"]
            self.assertEqual((demo["active"],demo["first_completed"],demo["repeat_pct"]),(2,1,50))
            self.assertEqual((imported["first_completed_pct"],imported["repeat_days"]),(100,0))
            for action in ("list","detail","save"):event(1001,action,"A",offset=7*86400)
            self.assertEqual(research_usage.weekly(db,"2026-11-24")["items"][0]["first_completed"],0)

    def test_product_decision_evidence_revision_and_access(self):
        owner, guest = self.client(), self.client()
        self.call(owner,"/api/register",{"email":"decisions@example.test","name":"Decision","password":"decision-test-123"})
        product = {"market":"GB","kind":"products","id":"001","name":"Sample","gmv":30,"sales":3,"date":"2025-08-02"}
        video = {**product,"kind":"videos","id":"short","name":"Clip","product_id":"001"}
        batch = {"source":"sample","rows":[{**product,"date":"2025-08-01","gmv":12,"sales":2},product,video]}
        source = self.call(owner,"/api/import",batch)["source"]
        target = f"?source={source}&market=GB&date=2025-08-02&days=1"
        self.call(owner,"/api/rankings"+target)
        detail = self.call(owner,"/api/detail"+target+"&id=001")["decision_evidence"]
        self.assertEqual((detail["current"]["sales"],detail["previous"]["avg_price"],detail["currency"]),(3,"6.00","GBP"))
        self.assertEqual([r["id"] for r in detail["videos"]],["short"])
        body = {"market":"GB","source":source,"product":"001","date":detail["date"],"days":1,
                "version":detail["version"],"request_key":"decision-a","reason":"Trial based on observed sales",
                "current":{"sales":990000},"videos":[{"id":"injected"}]}
        result = self.call(owner,"/api/research-decisions",body)
        compare = "/api/research-decisions?id="+str(result["id"])
        self.assertFalse(self.call(owner,compare)["changed"])
        self.assertEqual(self.call(owner,"/api/favorites")["items"],[])
        self.call(owner,"/api/import",{**batch,"rows":[{**product,"gmv":80,"sales":4}]})
        self.assertEqual(self.call(owner,"/api/research-decisions",body),result)
        self.call(owner,"/api/research-decisions",{**body,"request_key":"new-key"},expected=409)
        self.call(owner,"/api/research-decisions",{**body,"reason":"other reason"},expected=409)
        check = self.call(owner,compare)
        self.assertTrue(check["changed"])
        self.assertEqual(check["current"]["current"]["sales"],4)
        stored = self.call(owner,"/api/research-decisions")["items"]
        self.assertEqual(len(stored),1)
        self.assertEqual(stored[0]["evidence"],detail)
        self.assertEqual(self.call(owner,compare+"&saved=1")["evidence"]["daily"][1]["gmv"],"30.00")
        next_window = self.call(owner,"/api/detail"+target.replace("days=1","days=2")+"&id=001")["decision_evidence"]
        self.assertEqual(next_window["previous"]["covered_days"],0)
        self.call(owner,"/api/research-decisions",{**body,"days":2,"version":next_window["version"],"request_key":"next-window"})
        self.assertEqual(len(self.call(owner,"/api/research-decisions")["items"]),2)
        self.assertFalse(self.call(guest,"/api/research-decisions")["items"])
        self.call(guest,compare,expected=404)
        self.call(guest,"/api/research-decisions",body,expected=403)
        with closing(server.connect()) as db, db:
            uid=db.execute("SELECT owner FROM source_policy WHERE source=?",(source,)).fetchone()[0]
            server.analytics.source_policy.set_access(db,source)
        self.assertFalse(self.call(owner,"/api/research-decisions")["items"])
        self.call(owner,compare,expected=404)
        with closing(server.connect()) as db, db:
            server.analytics.source_policy.set_access(db,source,owner=uid)
            privacy.erase(db,uid,"decisions@example.test")
            self.assertEqual(db.execute("SELECT count(*) FROM research_decisions WHERE owner=?",(uid,)).fetchone()[0],0)

    def test_first_visit_five_minutes_includes_incomplete_and_prior_starts(self):
        from datetime import datetime,timezone
        import sqlite3
        with closing(sqlite3.connect(":memory:")) as db:
            research_usage.init(db)
            monday=int(datetime(2026,11,16,tzinfo=timezone.utc).timestamp())
            scope={"source":"demo","market":"US","date":"2026-11-15","days":7}
            def event(owner,action,seconds,source="demo",market="US"):
                research_usage.record(db,owner,{**scope,"source":source,"market":market},action,"sku",monday+seconds)
            for owner,offset in [(1,300),(2,301),(3,None)]:
                event(owner,"list",0)
                if offset:
                    event(owner,"detail",1)
                    event(owner,"save",offset)
            event(4,"list",-100)
            event(4,"detail",1)
            event(4,"save",2)
            event(5,"list",0,"licensed")
            event(5,"list",60,"licensed","GB")
            event(5,"detail",61,"licensed","GB")
            event(5,"export",125,"licensed","GB")
            demo, imported=research_usage.weekly(db,"2026-11-16")["items"]
            self.assertEqual((demo["first_starts"],demo["within_300s"],demo["within_300s_pct"]),(3,1,33.33))
            self.assertEqual((imported["first_starts"],imported["within_300s_pct"]),(1,100))
            before=research_usage.weekly(db,"2026-11-15")["items"][0]
            self.assertEqual((before["first_starts"],before["within_300s"]),(1,1))

            event(6,"list",-20,"licensed")
            event(6,"detail",-10,"licensed")
            event(6,"save",2,"licensed")
            prior=research_usage.weekly(db,"2026-11-15")["items"][1]
            after=research_usage.weekly(db,"2026-11-16")["items"][1]
            self.assertEqual((prior["first_starts"],prior["within_300s"],prior["first_completed"]),(1,1,0))
            self.assertEqual((after["first_starts"],after["within_300s"],after["first_completed"],after["active"]),(1,1,2,2))

    def test_decision_evidence_at_cent_precision_and_earliest_date(self):
        owner=self.client()
        self.call(owner,"/api/register",{"email":"cents@example.test","name":"Precision","password":"precision-test-123"})
        row={"market":"US","kind":"products","id":"001","name":"Sample","gmv":"99999999999999.01","sales":4,"date":"1900-01-01"}
        batch={"source":"decimal","rows":[row]}
        source=self.call(owner,"/api/import",batch)["source"]
        params=f"?source={source}&market=US&days=7&date=1900-01-01&id=001"
        first=self.call(owner,"/api/detail"+params)["decision_evidence"]
        self.assertEqual((first["current"]["gmv"],first["current"]["avg_price"]),("99999999999999.01","24999999999999.75"))
        self.call(owner,"/api/import",{**batch,"rows":[{**row,"gmv":"99999999999999.02"}]})
        second=self.call(owner,"/api/detail"+params)["decision_evidence"]
        self.assertEqual(second["daily"][0]["gmv"],"99999999999999.02")
        self.assertNotEqual(first["version"],second["version"])

    def test_research_import_monitor_api_and_tenant_isolation(self):
        owner,other=self.client(),self.client()
        account={"email":"research@example.test","password":"research-pass123","name":"研究员"}
        self.call(owner,"/")
        self.call(owner,"/api/register",account)
        rows=[dict(market="US",kind="products",id="p",name="杯",gmv=100,sales=10,date="2026-10-01")]
        payload={"source":"approved","rows":rows}
        src=self.call(owner,"/api/import",payload)["source"]
        self.call(owner,"/api/import",payload)
        base="/api/rankings?source="+src
        self.assertEqual(self.call(owner,base)["items"][0]["sales"],10)
        row={**rows[0],"source":src}
        for _ in range(2): self.call(owner,"/api/favorites",row)
        self.assertEqual(len(self.call(owner,"/api/favorites")["items"]),1)
        self.call(owner,"/api/monitors",{**row,"threshold":12})
        self.call(owner,"/api/import",{**payload,"rows":[{**rows[0],"sales":14}]})
        reading=self.call(owner,"/api/monitors")["items"][0]["readings"]
        self.assertEqual([(r["value"],r["hit"]) for r in reading],[(14,1)])
        bad=[{**rows[0],"sales":8},{**rows[0],"sales":-2}]
        self.call(owner,"/api/import",{**payload,"rows":bad},expected=400)
        exp=self.call(owner,"/api/export?source="+src)
        self.assertEqual(next(csv.DictReader(io.StringIO(exp.decode("utf-8-sig"))))["sales"],"14")
        self.call(other,base,expected=403)
        self.assertNotIn(src,[r["id"] for r in self.call(other,"/api/meta")["sources"]])
        self.assertFalse(self.call(other,"/api/favorites")["items"])
        token=self.call(owner,"/api/keys",{"label":"测试"})["key"]
        headers={"Authorization":"Bearer "+token}
        self.assertEqual(self.call(other,"/api/v1/rankings?source="+src,headers=headers)["total"],1)
        self.call(owner,"/api/keys",{"remove":True,"prefix":token[:14]})
        self.call(other,"/api/v1/meta",headers=headers,expected=401)
        self.call(owner,"/api/logout",{})
        self.call(owner,base,expected=403)
        self.call(owner,"/api/login",account)
        self.assertEqual(len(self.call(owner,"/api/favorites")["items"]),1)

    def test_guest_assistant_and_sources(self):
        guest=self.client()
        self.assertTrue(self.call(guest,"/api/me")["guest"])
        result=self.call(guest,"/api/generate",dict(tool="agent",market="US",source="demo",days=7,text="哪个商品销量最高？"))
        self.assertTrue(result["references"])
        self.assertIn("2026-11-19",result["result"])
        self.call(guest,"/api/import",{},expected=401)
        self.call(guest,"/api/generate",dict(tool="image_translate",text="翻译",images=["x"]),expected=503)
        self.call(guest,"/api/favorites",{},headers={"Origin":"https://other.example"},expected=403)
        self.assertEqual(self.call(guest,"/api/me")["usage"]["generation"],1)


if __name__=="__main__": unittest.main()

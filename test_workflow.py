"""End-to-end regression tests for workspace ownership and the research workflow."""
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
        req=Request(self.addr+path,data=None if data is None else json.dumps(data).encode(),
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
        with server.connect() as db:
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

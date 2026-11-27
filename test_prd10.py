"""Offline acceptance for PRD §10, including restart, tenancy, and ledger corrections."""
import hashlib
import hmac
import csv
import io
from datetime import date, datetime, timedelta, timezone
from email.parser import BytesParser
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
from pathlib import Path
import socketserver
import sqlite3
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

import analytics
import assistant_chats
import billing
import export_jobs
import insights
import notifications
import partnerships
import server
import settlement
import studio
import transcription
import workspace as ws


class LocalAcceptance(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path=Path(self.tmp.name)/"work.db"
        self.db=self.connect()
        self.addCleanup(self.db.close)
        for init in (analytics.init,ws.init,export_jobs.init,billing.init,partnerships.init): init(self.db)
        self.db.executemany("INSERT INTO users(id,name,email) VALUES(?,?,?)",[(1,"A","a@test.local"),(2,"B","b@test.local")])
        self.db.commit()
        self.a=ws.get_user(self.db,1)
        self.b=ws.get_user(self.db,2)

    def connect(self):
        db=sqlite3.connect(self.path,timeout=15)
        db.row_factory=sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        return db

    def queue(self,params,key="same"):
        with self.db: return export_jobs.submit(self.db,self.a,{"request_key":key,"params":params})["job"]

    def test_assistant_uses_three_private_turns_in_resolved_scope(self):
        assistant_chats.init(self.db)
        ask = lambda **values: assistant_chats.answer(self.db,self.a,values)
        with patch.object(studio,"generate",return_value={"result":"sample answer","references":[],"mode":"test"}) as generate:
            first = ask(text="first")
            chat = first["chat"]
            self.assertTrue(first["scope"]["date"])
            for question in ("second","third","fourth"):
                ask(chat=chat,text=question,**first["scope"])
            ask(chat=chat,text="another market",market="GB")
            self.assertEqual(generate.call_args.kwargs["previous"],[])
            ask(chat=chat,text="last",**first["scope"])
            self.assertEqual([t["question"] for t in generate.call_args.kwargs["previous"]],["second","third","fourth"])
        self.db.execute("UPDATE users SET owner=? WHERE id=?",(self.a["id"],self.b["id"]))
        teammate=ws.get_user(self.db,self.b["id"])
        self.assertEqual(assistant_chats.history(self.db,teammate)["items"],[])
        with self.assertRaises(LookupError):
            assistant_chats.history(self.db,teammate,chat)
        self.assertEqual(len(assistant_chats.history(self.db,self.a,chat)["turns"]),6)

    def test_numeric_research_filters_presets_and_export_parity(self):
        src="research-range"
        goods=[{"date":"2026-03-01","kind":"products","market":"US","id":str(i),"name":"Item",
                "sales":5,"gmv":v,"price":price} for i,(v,price) in enumerate([(10,0),(20,2.25),(40,None)])]
        analytics.import_rows(self.db, goods, src, shared=True)
        analytics.import_rows(self.db,[{**goods[1],"date":"2026-03-02","price":3.5,"gmv":0,"sales":0}],src,shared=True)
        query={"kind":"products","market":"US","source":src,"days":"2","min_gmv":"20","max_price":"3.50"}
        ranked=analytics.handle(self.db,"/api/rankings",query)
        self.assertEqual([r["id"] for r in ranked["items"]],["1"])
        self.assertEqual([r["price"] for r in analytics.handle(self.db,"/api/detail",{**query,"id":"1"})["trend"]],[2.25,3.5])
        self.assertEqual(analytics.handle(self.db,"/api/rankings",{**query,"max_price":"0","min_gmv":"0"})["total"],1)
        for invalid in ({"max_price":"-1"},{"min_gmv":"nan"},{"max_sales":"2.5"},{"min_price":"4"},{"kind":"videos"}):
            with self.assertRaises(ValueError): analytics.ranking_filter(invalid.get("kind","products"),{**query,**invalid})
        saved={"name":"Range A","kind":"products","params":query}
        with self.db: ws.ranking_presets(self.db,self.a,saved,True)
        self.assertEqual(ws.ranking_presets(self.db,self.b,{"kind":"products"})["items"],[])
        result=ws.ranking_presets(self.db,self.a,{"kind":"products"})["items"]
        self.assertEqual(result,[{"name":"Range A","params":{k:v for k,v in query.items() if k!="kind"}}])
        job=self.queue(query,key="filtered-csv")
        self.assertTrue(export_jobs.run_one(self.connect))
        _,blob=export_jobs.file_for(self.db,self.a,job)
        with blob: self.assertEqual(blob.read(),server.csv_export(self.db,query)[0])
        with self.db: ws.ranking_presets(self.db,self.a,{**saved,"remove":True},True)
        self.assertFalse(ws.ranking_presets(self.db,self.a,{"kind":"products"})["items"])

    def test_cent_apart_totals_rank_filter_and_export_without_float_ties(self):
        source = "cent-ranking"
        query = {"source":source,"market":"US","kind":"products","days":1}
        low, high = "99999999999999.01", "99999999999999.02"
        base = {"kind":"products","market":"US","name":"product","date":"2026-11-01","sales":2}
        rows = [{**base,"id":ident,"gmv":amount,"price":amount} for ident,amount in (("a",low),("z",high))]
        with self.db:
            analytics.import_rows(self.db, rows, source, shared=True)
        def rank(**filters):
            return analytics.handle(self.db, "/api/rankings", {**query,**filters})["items"]
        self.assertEqual([(r["id"], r["gmv_exact"]) for r in rank()], [("z",high),("a",low)])
        self.assertEqual([r["id"] for r in rank(min_gmv=high)], ["z"])
        self.assertEqual([r["id"] for r in rank(max_price=low)], ["a"])
        data, _ = server.csv_export(self.db, query)
        records = csv.DictReader(io.StringIO(data.decode("utf-8-sig")))
        self.assertEqual([(r["rank"],r["id"],r["gmv"]) for r in records], [("1","z",high),("2","a",low)])
        job = self.queue(query)
        self.assertTrue(export_jobs.run_one(self.connect))
        _, blob = export_jobs.file_for(self.db, self.a, job)
        with blob:
            self.assertEqual(blob.read(), data)
        # More than 2000 leading rows switches pagination to its SQLite disk sort.
        with self.db:
            analytics.import_rows(self.db, ({**base,"id":f"big{i}","gmv":10**14} for i in range(2000)), source, shared=True)
        self.assertEqual([r["id"] for r in rank(page=1001,limit=2)], ["z","a"])

    def test_export_recovery_idempotency_csv_and_quota(self):
        query={"source":"demo","market":"US","kind":"creators","days":"7","sort":"follower_growth"}
        job=self.queue(query)
        self.assertEqual(self.queue(query),job)
        with self.assertRaises(ws.RequestError) as conflict:
            self.queue({**query,"sort":"sales"})
        self.assertEqual(conflict.exception.status,409)
        with self.db: self.db.execute("UPDATE export_jobs SET state='running',lease='abandoned',expiry=0")
        self.assertTrue(export_jobs.run_one(self.connect))
        self.assertFalse(export_jobs.run_one(self.connect))
        size,blob=export_jobs.file_for(self.db,self.a,job)
        with blob: data=blob.read()
        self.assertEqual(size,len(data))
        expected,count=server.csv_export(self.db,query)
        self.assertEqual(data,expected)
        self.assertEqual(ws.me(self.db,self.a)["usage"]["export_rows"],count)
        with self.assertRaises(LookupError): export_jobs.file_for(self.db,self.b,job)
        with self.assertRaises(ws.RequestError): self.queue({"source":"ws-2-private"},"private")
        self.queue(query,"over")
        with patch.dict(ws.LIMITS["free"],export_rows=1): export_jobs.run_one(self.connect)
        self.assertEqual(export_jobs.listing(self.db,self.a)["items"][0]["state"],"failed")
        self.assertEqual(ws.me(self.db,self.a)["usage"]["export_rows"],count)

    def test_english_question_and_saved_topic_scope(self):
        params={"source":"demo","market":"US","days":"7"}
        answer=studio.generate(self.db,{**params,"tool":"agent","locale":"en-US","text":"Which products sell the most?"})
        ranked=analytics.handle(self.db,"/api/rankings",{**params,"sort":"sales","kind":"products"})
        self.assertIn("ranked by units sold",answer["result"])
        self.assertEqual(answer["references"][0]["label"],ranked["items"][0]["name"])
        trends=analytics.handle(self.db,"/api/trends",{**params,"group":"script"})
        topic={**params,"group":"script","topic":trends["items"][0]["name"],"date":trends["date"]}
        ws.save_topic(self.db,self.a,topic)
        ws.save_topic(self.db,self.a,topic)
        self.assertEqual(len(ws.list_items(self.db,self.a,"favorites")["topics"]),1)
        self.assertEqual(ws.list_items(self.db,self.b,"favorites")["topics"],[])
        ws.save_topic(self.db,self.b,{**topic,"remove":True})
        self.assertEqual(len(ws.list_items(self.db,self.a,"favorites")["topics"]),1)
        ws.save_topic(self.db,self.a,{**topic,"remove":True})
        self.assertEqual(ws.list_items(self.db,self.a,"favorites")["topics"],[])

    def test_review_evidence_and_bilingual_negation(self):
        comments=[{"text":s} for s in ("非常满意","不太满意","not very good","great but broken","arrived Tuesday","not broken")]
        result=insights.sentiment(comments)
        self.assertEqual([r["label"] for r in result["reviews"]],["positive","negative","negative","mixed","unknown","positive"])
        self.assertEqual(result["reviews"][2]["signals"],["not very good"])
        row={"kind":"products","market":"US","id":"p","name":"P","gmv":2,"sales":1,"date":"2026-10-03",
             "profile":{"reviews":comments}}
        analytics.import_rows(self.db,[row],"reviews")
        report=analytics.handle(self.db,"/api/detail",{"id":"p","kind":"products","source":"reviews"})
        self.assertEqual(report["item"]["review_sentiment"],result)

    def test_forecast_retains_one_cent_change_across_large_daily_totals(self):
        start = date(2026, 9, 1)
        base = {"kind":"products","market":"US","name":"test","sales":1}
        def records():
            for i in range(14):
                day = str(start + timedelta(days=i))
                for n in range(929):
                    yield {**base,"date":day,"id":str(n),"gmv":"100000000000000.00"}
                yield {**base,"date":day,"id":"changed","gmv":"99999999999999.01" if i<7 else "99999999999999.02"}
        analytics.import_rows(self.db, records(), "forecast-large", shared=True)
        study = insights.study(self.db, {"market":"US","source":"forecast-large","group":"category"})
        self.assertEqual(study["mae"]["gmv"], 0.01)
        self.assertEqual(study["forecast"][0]["gmv_exact"], "92999999999999999.02")

    def test_forecast_holdout_coverage_and_cutoff(self):
        start=date(2026,1,1)
        rows=[dict(kind="videos",market="US",id="v",name="V",tag="t",sales=i%7,gmv=(i%7)*2,date=str(start+timedelta(i))) for i in range(28)]
        analytics.import_rows(self.db,[*rows,{**rows[-1],"date":"2026-01-29","gmv":9999999}],"forecast")
        p={"source":"forecast","date":"2026-01-28","topic":"t"}
        result=insights.study(self.db,p)
        self.assertEqual(result["observed_days"],28)
        self.assertEqual(result["mae"],{"gmv":0,"sales":0})
        self.assertEqual([r["sales"] for r in result["forecast"]],list(range(7)))
        self.assertEqual(result["forecast"][0]["date"],"2026-01-29")
        self.db.execute("DELETE FROM analytics_daily WHERE source='forecast' AND date='2026-01-25'")
        result=insights.study(self.db,p)
        self.assertEqual(result["missing_dates"],["2026-01-25"])
        self.assertFalse(result["forecast"])
        self.assertIsNone(result["series"][-4]["sales"])

    def start_listener(self,service):
        thread=threading.Thread(target=service.serve_forever,daemon=True)
        thread.start()
        def stop():
            service.shutdown()
            service.server_close()
            thread.join()
        self.addCleanup(stop)
        return service.server_address[1]

    def test_alert_inbox_and_loopback_transports(self):
        mail=[]
        sms=[]
        class SMTP(socketserver.StreamRequestHandler):
            def handle(self):
                self.wfile.write(b"220 localhost\r\n")
                while line:=self.rfile.readline():
                    cmd=line.split()[:1]
                    if cmd==[b'DATA'] or cmd==[b'data']:
                        self.wfile.write(b"354 continue\r\n")
                        parts=[]
                        while (line:=self.rfile.readline()) not in (b'.\r\n',b''): parts.append(line)
                        mail.append(BytesParser().parsebytes(b''.join(parts)))
                    if cmd and cmd[0].lower()==b"quit":
                        self.wfile.write(b"221 bye\r\n")
                        break
                    self.wfile.write(b"250 ok\r\n")
        class SMS(BaseHTTPRequestHandler):
            def do_POST(self):
                sms.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
                self.send_response(200)
                self.end_headers()
            def log_message(self,*args): pass
        smtp=self.start_listener(socketserver.TCPServer(("127.0.0.1",0),SMTP))
        http=self.start_listener(HTTPServer(("127.0.0.1",0),SMS))
        cfg=Path(self.tmp.name)/"routes.json"
        cfg.write_text(json.dumps({"1":{"email":{"host":"127.0.0.1","port":smtp,"from":"app@example.test","to":"sink@example.test","starttls":False},
                                        "sms":{"url":f"http://127.0.0.1:{http}","to":"test-device"}}}))
        with self.db:
            ws.mutate_list(self.db,self.a,"monitors",{"market":"US","source":"demo","kind":"products","id":"p01","threshold":0})
            ws.sample(self.db)
            ws.sample(self.db)
        self.assertEqual(len(notifications.inbox(self.db,1)["items"]),1)
        self.assertEqual(notifications.inbox(self.db,2)["items"],[])
        with patch.dict(os.environ,TIKFLOWSO_ALERT_ROUTES=str(cfg)):
            self.assertTrue(notifications.run_one(self.connect))
            self.assertTrue(notifications.run_one(self.connect))
            self.assertFalse(notifications.run_one(self.connect))
        self.assertEqual(len(mail),1)
        self.assertEqual(len(sms),1)
        self.assertIn("2026-11-19",sms[0]["text"])
        self.assertEqual(mail[0]["To"],"sink@example.test")
        self.assertIn("email=sent",notifications.inbox(self.db,1)["items"][0]["delivery"])

    def test_review_fx_and_dispute_reconciliation(self):
        stamp=int(time.time())
        month=datetime.fromtimestamp(stamp,timezone.utc).strftime("%Y-%m")
        day=datetime.fromtimestamp(stamp,timezone.utc).date().isoformat()
        cfg=Path(self.tmp.name)/"rates.json"
        cfg.write_text(json.dumps({"base_currency":"USD","dates":{day:{"EUR":"1.20"}}}))
        self.db.executemany("INSERT INTO partner_ledger VALUES(?,?,?,?,?,?,?,?,?,?)",[
            ("test","ch1","ch1","inv1",1,2,"eur",10000,1000,stamp),
            ("test","ch2","ch2","inv2",1,2,"usd",20000,1000,stamp)])
        self.db.commit()
        p={"mode":"test","month":month,"fx_date":day}
        with patch.dict(os.environ,TIKFLOWSO_FX_RATES=str(cfg)),self.db:
            self.assertEqual(settlement.snapshot(self.db,1,p)["conversion"]["total"],"32.00")
            first=settlement.request_review(self.db,1,p)["id"]
            self.assertEqual(settlement.request_review(self.db,1,p)["id"],first)
            settlement.dispute(self.db,"test","case","ch1",8500,"open","local fixture")
            with self.assertRaises(ValueError): settlement.review(self.db,first,"approved","tester","ok")
            with self.assertRaises(ValueError): settlement.request_review(self.db,1,p)
            settlement.dispute(self.db,"test","case","ch1",8500,"lost","evidence reviewed")
            self.db.execute("INSERT INTO partner_ledger VALUES('test','re1','ch1','inv1',1,2,'eur',-3000,1000,?)",(stamp+1,))
            self.assertEqual(settlement.snapshot(self.db,1,p)["conversion"]["total"],"20.00")
            req=settlement.request_review(self.db,1,p)["id"]
            self.assertNotEqual(first,req)
            settlement.review(self.db,req,"approved","tester","fixture only")
            states=[r["status"] for r in settlement.history(self.db,1)["items"]]
            self.assertEqual(states,["approved","superseded"])
            self.assertEqual(settlement.history(self.db,2)["items"],[])
            settlement.dispute(self.db,"test","case","ch1",8500,"reopen","appeal accepted for review")
            with self.assertRaises(ValueError): settlement.request_review(self.db,1,p)
            settlement.dispute(self.db,"test","case","ch1",8500,"won","appeal won")
            self.assertEqual(settlement.snapshot(self.db,1,p)["conversion"]["total"],"28.40")
            self.assertEqual(settlement.statement(self.db,1,{"mode":"live","month":month})["items"],[])
            with self.assertRaises(ValueError): settlement.snapshot(self.db,1,{**p,"fx_date":"2000-01-01"})

    def test_signed_dispute_before_payment_and_retry(self):
        settings={"STRIPE_SECRET_KEY":"fixture","STRIPE_WEBHOOK_SECRET":"fixture-sign",
                  "STRIPE_PRICE_PRO":"p1","STRIPE_PRICE_TEAM":"p2"}
        stamp=int(time.time())
        month=datetime.fromtimestamp(stamp,timezone.utc).strftime("%Y-%m")
        event={"id":"evt","created":stamp,"livemode":False,"type":"charge.dispute.closed","data":{"object":{
            "object":"dispute","id":"dp1","charge":"ch1","status":"lost","amount":90,"currency":"usd","livemode":False}}}
        body=json.dumps(event).encode()
        sign=hmac.new(b"fixture-sign",str(stamp).encode()+b"."+body,hashlib.sha256).hexdigest()
        sig=f"t={stamp},v1={sign}"
        with patch.dict(os.environ,settings),self.db:
            with self.assertRaises(billing.BillingError): billing.webhook(self.db,body,"bad")
            self.assertFalse(billing.webhook(self.db,body,sig)["duplicate"])
            self.assertTrue(billing.webhook(self.db,body,sig)["duplicate"])
            self.db.execute("INSERT INTO partner_ledger VALUES('test','ch1','ch1','inv1',1,2,'usd',1000,1000,?)",(stamp,))
            with self.assertRaises(ValueError): settlement.request_review(self.db,1,{"mode":"test","month":month})
            self.assertFalse(settlement.statement(self.db,2,{"mode":"test","month":month})["disputes"])
            settlement.dispute(self.db,"test","dp1","ch1",90,"open","review")
            settlement.dispute(self.db,"test","dp1","ch1",90,"lost","verified")
            self.assertEqual(settlement.statement(self.db,1,{"month":month})["totals"]["usd"]["commission"],91)
            self.assertTrue(settlement.request_review(self.db,1,{"mode":"test","month":month})["id"])

    def test_notification_retry_and_monitor_id_reuse(self):
        spec={"market":"US","source":"demo","kind":"products","id":"p01","threshold":0}
        with self.db:
            ws.mutate_list(self.db,self.a,"monitors",spec)
            ws.sample(self.db)
            old=notifications.inbox(self.db,1)["items"][0]["mid"]
            ws.mutate_list(self.db,self.a,"monitors",{"mid":old,"remove":True})
            ws.mutate_list(self.db,self.a,"monitors",{**spec,"id":"p02"})
            ws.sample(self.db)
        self.assertEqual(len({r["mid"] for r in notifications.inbox(self.db,1)["items"]}),2)
        with patch("notifications.config",return_value={"1":{"email":{"to":"fixture"}}}),patch("notifications.deliver",side_effect=OSError):
            notifications.run_one(self.connect)
        self.assertEqual(self.db.execute("SELECT status FROM deliveries WHERE aid=1 AND channel='email'").fetchone()[0],"retry")
        with self.db: self.db.execute("UPDATE deliveries SET due=0 WHERE aid=1 AND channel='email'")
        with patch("notifications.config",return_value={"1":{"email":{"to":"fixture"}}}),patch("notifications.deliver") as transport:
            notifications.run_one(self.connect)
            transport.assert_called_once()
        self.assertEqual(self.db.execute("SELECT attempts FROM deliveries WHERE aid=1 AND channel='email'").fetchone()[0],2)

    def test_team_membership_and_revoked_export_access(self):
        with self.db:
            self.db.execute("UPDATE users SET plan='team' WHERE id=1")
            owner=ws.get_user(self.db,1)
            invite=ws.invite(self.db,owner,{"email":self.b["email"]})["invite"]
            ws.join(self.db,self.b,{"invite":invite})
        member=ws.get_user(self.db,2)
        self.assertEqual(ws.me(self.db,member)["plan"],"team")
        with self.db:
            job=export_jobs.submit(self.db,member,{"request_key":"team","params":{"kind":"products"}})["job"]
        export_jobs.run_one(self.connect)
        with self.db: self.db.execute("UPDATE users SET owner=NULL WHERE id=2")
        with self.assertRaises(LookupError): export_jobs.file_for(self.db,ws.get_user(self.db,2),job)

    def test_asset_attachment_scope_expiry_and_delete(self):
        row={"name":"Clip","kind":"asset","url":"https://example.test/owned","rights":"Synthetic test fixture"}
        path="/api/partners/library"
        ident=partnerships.handle(self.db,self.a,path,"POST",row)["id"]
        partnerships.asset(self.db,self.a,ident,b"fixture bytes","素材.txt","")
        self.assertEqual(partnerships.asset(self.db,self.a,ident)["bytes"],b"fixture bytes")
        with self.assertRaises(LookupError): partnerships.asset(self.db,self.b,ident)
        partnerships.asset(self.db,self.a,ident,b"revised","new","2000-01-01")
        with self.assertRaises(ws.RequestError): partnerships.asset(self.db,self.a,ident)
        partnerships.handle(self.db,self.a,path,"POST",{**row,"id":ident,"category":"杯具","expires":"2199-01-01"})
        self.assertEqual(partnerships.asset(self.db,self.a,ident)["bytes"],b"revised")
        partnerships.handle(self.db,self.a,path,"POST",{**row,"id":ident})
        self.assertEqual(partnerships.handle(self.db,self.a,path,"GET",{})["items"][0]["category"],"杯具")
        partnerships.handle(self.db,self.a,path,"POST",{"id":ident,"action":"remove"})
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM partner_files").fetchone()[0],0)

    def test_invalid_media_and_missing_model(self):
        with patch.dict(os.environ,TIKFLOWSO_WHISPER_MODEL="/no-model-here"):
            with self.assertRaises(ws.RequestError): transcription.transcribe(b"bad")
        if transcription.available():
            with self.assertRaises(ValueError): transcription.transcribe(b"invalid","en")


if __name__=="__main__": unittest.main()

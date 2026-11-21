import json
import os
from pathlib import Path
import sqlite3
import tempfile
import time
import unittest
from unittest.mock import patch
from contextlib import closing

import account_security
import analytics
import backup_vault
import billing
import export_jobs
import model_spend
import operations
import privacy
import reconciliation
import notifications
import assistant_chats
import support_cases
import partnerships
import recycle
import request_limits
import server
import settlement
import source_policy
import studio
import transport
import workspace as ws


class ReleaseControls(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.path=Path(tmp.name)/"main.sqlite3"
        self.db=self.connect()
        self.addCleanup(self.db.close)
        for init in (analytics.init,ws.init,billing.init,partnerships.init,operations.init,export_jobs.init):
            init(self.db)
        self.db.executemany("INSERT INTO users(id,name,email) VALUES(?,?,?)",
                            [(1,"Owner","owner@example.invalid"),(2,"Peer","peer@example.invalid")])
        self.db.commit()
        self.a=ws.get_user(self.db,1)
        self.b=ws.get_user(self.db,2)
        self.fact={"market":"CN","kind":"products","id":"1","date":"2026-11-01","name":"合成商品","gmv":1,"sales":1}

    def connect(self):
        db=sqlite3.connect(self.path)
        db.row_factory=sqlite3.Row
        db.execute("PRAGMA foreign_keys=on")
        return db

    def test_source_migration_and_subsequent_access_changes(self):
        self.db.executemany("INSERT INTO analytics_sources VALUES(?,?)",[("old-import","old"),("ws-1-old","old")])
        source_policy.migrate(self.db)
        self.assertFalse(source_policy.visible(self.db,1,"old-import"))
        self.assertTrue(source_policy.visible(self.db,1,"ws-1-old"))
        self.assertFalse(source_policy.visible(self.db,2,"ws-1-old"))
        analytics.import_rows(self.db,[self.fact],"ws-2-unclassified")
        self.assertFalse(source_policy.visible(self.db,2,"ws-2-unclassified"))
        with self.assertRaises(ValueError): analytics.import_rows(self.db,[self.fact],"future-owner",owner=999)
        analytics.import_rows(self.db,[self.fact],"ordinary")
        self.assertFalse(source_policy.visible(self.db,1,"ordinary"))
        source_policy.set_access(self.db,"ordinary",owner=1)
        ws.check_source(self.db,self.a,"ordinary")
        with self.assertRaises(ws.RequestError): ws.check_source(self.db,self.b,"ordinary")
        source_policy.set_access(self.db,"ordinary",shared=True)
        ws.check_source(self.db,self.b,"ordinary")

    def test_admin_factor_recovery_reset_and_throttle(self):
        credentials=account_security.provision(self.db,1)
        self.db.commit()
        code=account_security.totp(credentials["secret"],int(time.time())//30)
        account_security.verify_factor(self.db,1,code)
        account_security.verify_factor(self.db,1,credentials["recovery_codes"][0])
        with self.assertRaises(ws.RequestError): account_security.verify_factor(self.db,1,credentials["recovery_codes"][0])
        issued=ws.issue_session(self.db,1,assured=True)
        reset=account_security.reset_token(self.db,1)
        account_security.reset_password(self.db,reset,"new-password-example")
        self.assertIsNone(ws.session(self.db,issued))
        with self.assertRaises(ValueError): account_security.reset_password(self.db,reset,"different-example")
        for _ in range(8): account_security.limit_attempt(self.db,"synthetic","local-test")
        with self.assertRaises(ws.RequestError): account_security.limit_attempt(self.db,"synthetic","local-test")
        account_security.limit_attempt(self.db,"different","local-test")

    def test_split_payment_and_refunds_reconcile_exactly(self):
        self.db.execute("INSERT INTO billing_customers(user_id,customer_id,create_key) VALUES(2,'cus','local')")
        self.db.execute("INSERT INTO partner_referrals VALUES(2,1,1000,1)")
        stamp=1735600000
        charge=dict(id="ch",customer="cus",payment_intent="pi",paid=True,captured=True,
                    amount_captured=10000,amount_refunded=2500,currency="cny",created=stamp,livemode=False)
        payments=[{"id":"p1","invoice":"i1","payment":{"payment_intent":"pi"},"amount_paid":6000},
                  {"id":"p2","invoice":"i2","payment":{"payment_intent":"pi"},"amount_paid":4000}]
        def stripe(path):
            if path.startswith("charges?"):return {"data":[charge],"has_more":False}
            if path.startswith("invoice_payments?"):return {"data":list(reversed(payments)),"has_more":False}
            if path.startswith("refunds?"):return {"data":[dict(status="succeeded",charge="ch",currency="cny",id="refund",amount=2500,created=stamp+30)],"has_more":False}
            if path.startswith("invoices/"):return dict(id=path.split("/")[1],customer="cus",billing_reason="subscription_cycle",status="paid",currency="cny",livemode=False,lines={"data":[{"price":{"id":"pro"}}]})
            if path=="payment_intents/pi":return {"latest_charge":"ch"}
            self.assertEqual(path,"charges/ch");return charge
        event={"type":"charge.refunded","livemode":False,"data":{"object":charge}}
        self.db.commit()
        with patch.dict(os.environ,{"STRIPE_PRICE_PRO":"pro"}):
            report=reconciliation.run(self.path,"2024-12-01","2025-01-01",stripe=stripe)
            self.assertEqual(sorted(r["amount"] for r in report["changes"]),[-2500,4000,6000])
            self.assertEqual(self.db.execute("SELECT count(*) FROM partner_ledger").fetchone()[0],0)
            self.assertEqual(len(reconciliation.run(self.path,"2024-12-01","2025-01-01",True,stripe=stripe)["changes"]),3)
        for _ in range(2): self.assertTrue(partnerships.financial_event(self.db,event,stripe,{"pro"})["matched"])
        invoice={"type":"invoice.paid","livemode":False,"data":{"object":{"id":"i1","customer":"cus"}}}
        partnerships.financial_event(self.db,invoice,stripe,{"pro"})
        statement=settlement.statement(self.db,1,{"month":"2024-12"})
        self.assertEqual(statement["totals"]["cny"],{"amount":7500,"commission":750})
        self.assertEqual(sorted(r["amount"] for r in statement["items"]),[-2500,4000,6000])
        payments[1]["amount_paid"]=3500
        with self.assertRaises(ValueError): partnerships.financial_event(self.db,event,stripe,{"pro"})

    def test_private_research_stays_local_until_exact_destination_is_authorized(self):
        analytics.import_rows(self.db,[self.fact],"business",owner=1)
        env={"TIKFLOWSO_MODEL_URL":"https://model.example.invalid/completions","TIKFLOWSO_MODEL":"contract"}
        with patch.dict(os.environ,env,clear=True),patch.object(studio,"infer",return_value="cloud") as provider:
            ask={"tool":"agent","text":"销量最高的商品","source":"business","market":"CN"}
            self.assertNotEqual(studio.generate(self.db,ask,owner=1)["result"],"cloud")
            self.db.execute("INSERT INTO research_permissions VALUES(1,'business',?,0,0)",(studio.destination("agent"),))
            self.assertEqual(studio.generate(self.db,ask,owner=1,previous=[{"answer":"private draft"}])["result"],"cloud")
            self.assertNotIn("private draft",provider.call_args.args[1])
            self.assertIsNone(model_spend.policy(self.db,1,"business","https://other.invalid other"))
            self.assertIsNone(model_spend.policy(self.db,2,"business",studio.destination("agent")))

    def test_subrequest_budget_survives_uncertain_completion(self):
        url="https://model.example.invalid/chat/completions"
        tariff={"endpoint":url,"model":"m","context_tokens":1000,"max_output_tokens":100,
                "input_usd_per_million":1,"output_usd_per_million":2}
        filename=self.path.parent/"tariff.json"
        filename.write_text(json.dumps({"models":[tariff],"platform_month_usd":".003","workspace_month_usd":".002"}))
        with patch.dict(os.environ,{"TIKFLOWSO_MODEL_PRICING":str(filename)},clear=True),model_spend.scope(self.connect,1):
            body={"model":"m"}
            ticket=model_spend.reserve(url,body)
            self.assertEqual(body["max_tokens"],100)
            with self.assertRaises(ws.RequestError):model_spend.reserve(url,body)
            model_spend.settle(ticket,{"usage":{"prompt_tokens":100,"completion_tokens":10}})
            model_spend.reserve(url,body)
            with self.assertRaises(ws.RequestError):model_spend.reserve(url,body)
        self.assertEqual(self.db.execute("SELECT SUM(charged) FROM model_calls").fetchone()[0],1320)

    def test_backup_authentication_and_isolated_restore(self):
        cert,key=backup_vault.setup(self.path.parent/"recovery")
        self.path.with_suffix(".providers.json").write_text('{"key":"fixture-private-only"}')
        directory=self.path.parent/"external-volume"/"backup"
        backup_vault.seal(self.path,directory,cert)
        self.assertEqual([p.name for p in directory.iterdir()],[backup_vault.PAYLOAD])
        with backup_vault.unpack(directory,key) as source:
            with closing(sqlite3.connect(source/"tikflowso.sqlite3")) as db:
                self.assertEqual(db.execute("SELECT COUNT(*) FROM users").fetchone()[0],2)
            self.assertIn("fixture-private-only",(source/"tikflowso.providers.json").read_text())
        wrong=backup_vault.setup(self.path.parent/"second-key")[1]
        with self.assertRaises(ValueError),backup_vault.unpack(directory,wrong): pass

    def test_bounded_upload_slots_and_provider_client(self):
        with request_limits.admit(("owner",1)),request_limits.admit(("owner",1)):
            with self.assertRaises(ws.RequestError),request_limits.admit(("owner",1)): pass
            with request_limits.admit(("owner",2)): pass
        with request_limits.admit(("owner",1)): pass
        self.assertIsNone(transport.NoRedirect().redirect_request(None,None,302,"",{},None))

    def test_legacy_backup_conversion_recovers_identical_bytes(self):
        import manage
        old=self.path.parent/"legacy"
        manage.deployment_backup(self.path,old)
        expected={p.name:manage.file_hash(p) for p in old.iterdir()}
        cert,key=backup_vault.setup(self.path.parent/"custody")
        self.assertTrue(backup_vault.encrypt_legacy(old,cert,key))
        self.assertFalse(backup_vault.encrypt_legacy(old,cert,key))
        self.assertEqual([p.name for p in old.iterdir()],[backup_vault.PAYLOAD])
        with backup_vault.unpack(old,key) as clear:
            self.assertEqual(expected,{name:manage.file_hash(clear/name) for name in expected})

    def test_authorized_metered_question_through_http_client(self):
        from http.server import BaseHTTPRequestHandler,HTTPServer
        from threading import Thread
        calls=[]
        class Provider(BaseHTTPRequestHandler):
            def log_message(self,*args): pass
            def do_POST(self):
                calls.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
                data=json.dumps({"choices":[{"message":{"content":"from model"}}],
                                 "usage":{"prompt_tokens":30,"completion_tokens":4}}).encode()
                self.send_response(200); self.send_header("Content-Length",str(len(data))); self.end_headers(); self.wfile.write(data)
        gateway=HTTPServer(("127.0.0.1",0),Provider)
        thread=Thread(target=gateway.serve_forever,daemon=True); thread.start()
        self.addCleanup(gateway.server_close); self.addCleanup(gateway.shutdown)
        endpoint="http://127.0.0.1:"+str(gateway.server_port)+"/v1/chat/completions"
        config=self.path.parent/"pricing.json"
        config.write_text(json.dumps({"platform_month_usd":1,"workspace_month_usd":1,"models":[{
            "endpoint":endpoint,"model":"fixture","input_usd_per_million":1,"output_usd_per_million":2,
            "context_tokens":1000,"max_output_tokens":50}]}))
        analytics.import_rows(self.db,[self.fact],"approved",owner=1)
        self.db.execute("INSERT INTO research_permissions VALUES(1,'approved',?,0,0)",(endpoint+" fixture",))
        self.db.commit()
        data={"tool":"agent","text":"销量排名 user@example.invalid","source":"approved","market":"CN"}
        with patch.dict(os.environ,{"TIKFLOWSO_MODEL_URL":endpoint,"TIKFLOWSO_MODEL":"fixture",
                                    "TIKFLOWSO_MODEL_PRICING":str(config)},clear=True),model_spend.scope(self.connect,1):
            self.assertEqual(studio.generate(self.db,data,owner=1)["result"],"from model")
        self.assertNotIn("user@example.invalid",json.dumps(calls))
        self.assertEqual(calls[0]["max_tokens"],50)
        self.assertEqual(tuple(self.db.execute("SELECT charged,state FROM model_calls").fetchone()),(38,"metered"))

    def test_verified_erasure_and_restore_preserve_unrelated_owners(self):
        from platform_admin import init as init_admin
        init_admin(self.db,self.path)
        assistant_chats.init(self.db)
        support_cases.init(self.db)
        self.db.execute("INSERT INTO support_cases VALUES(1,1,'personal',1,1)")
        self.db.execute("INSERT INTO support_messages VALUES(1,1,1,0,'private',1,'entry')")
        analytics.import_rows(self.db,[self.fact],"first",owner=1)
        analytics.import_rows(self.db,[self.fact],"second",owner=2)
        token=ws.issue_session(self.db,1)
        self.db.commit()
        snapshot=sqlite3.connect(":memory:"); self.addCleanup(snapshot.close)
        self.db.backup(snapshot)
        journal=self.path.parent/"erasures.sqlite3"
        with self.db: privacy.request(self.db,"owner@example.invalid",journal)
        self.assertIsNone(ws.session(self.db,token))
        self.assertIsNone(self.db.execute("SELECT 1 FROM support_messages").fetchone())
        self.assertEqual([r[0] for r in self.db.execute("SELECT DISTINCT source FROM analytics_daily WHERE source!='demo'")],["second"])
        self.assertEqual(privacy.replay(snapshot,journal),1)
        self.assertEqual(privacy.replay(snapshot,journal),0)
        self.assertIsNone(snapshot.execute("SELECT email FROM users WHERE id=1").fetchone()[0])
        self.assertEqual(snapshot.execute("SELECT email FROM users WHERE id=2").fetchone()[0],"peer@example.invalid")
        with self.assertRaises(ValueError):analytics.import_rows(self.db,[self.fact],"new-source",owner=1)
        self.assertNotIn("user@example.invalid",privacy.scrub("Ask user@example.invalid"))
        self.assertEqual(privacy.scrub({"draft":"Bearer abcdefghijklmnopqrstuv"}),{"draft":"[credential]"})

    def test_revoked_sources_hide_chat_and_notifications_and_signed_receipts_deduplicate(self):
        import hmac
        assistant_chats.init(self.db)
        analytics.import_rows(self.db,[self.fact],"new-source",owner=1)
        self.db.execute("INSERT INTO assistant_chats VALUES(1,1,1,'private title',0)")
        self.db.execute("INSERT INTO assistant_turns VALUES(1,1,?,'private question','{}')",(json.dumps({"source":"new-source"}),))
        notifications.record(self.db,{"owner":1,"mid":1,"source":"new-source","name":"monitor","metric":"sales","threshold":1},"2026-11-01",2)
        hit=notifications.inbox(self.db,1)["items"][0]["aid"]
        raw=json.dumps({"event":"evt_once","message_id":f"<tikflowso-1-{hit}@tikflowso.local>","timestamp":int(time.time()),"status":"complained"}).encode()
        with patch.dict(os.environ,{"TIKFLOWSO_ALERT_FEEDBACK_SECRET":"fixture-feedback"}):
            signature=hmac.digest(b"fixture-feedback",raw,"sha256").hex()
            self.assertTrue(notifications.feedback(self.db,raw,signature)["ok"])
            self.assertTrue(notifications.feedback(self.db,raw,signature)["duplicate"])
        self.assertEqual(self.db.execute("SELECT enabled FROM notification_preferences WHERE owner=1 AND channel='email'").fetchone()[0],0)
        source_policy.set_access(self.db,"new-source")
        self.assertEqual(assistant_chats.history(self.db,self.a)["items"],[])
        with self.assertRaises(LookupError): assistant_chats.history(self.db,self.a,1)
        self.assertEqual(notifications.inbox(self.db,1)["items"],[])

    def test_large_synchronous_export_can_be_queued_and_deep_pages_are_stable(self):
        rows=({**self.fact,"id":str(i),"sales":i} for i in range(2300))
        analytics.import_rows(self.db,rows,"catalog",owner=1)
        params={"source":"catalog","market":"CN","kind":"products","sort":"sales","limit":5,"page":451}
        page=analytics.handle(self.db,"/api/rankings",params)
        self.assertEqual((page["total"],page["items"][0]["rank"],page["items"][0]["sales"]),(2300,2251,49))
        with self.assertRaises(server.QueueExport):server.csv_export(self.db,params)
        with self.db: job=export_jobs.submit(self.db,self.a,{"request_key":"scheduled","params":params})["job"]
        self.assertGreater(job,0)


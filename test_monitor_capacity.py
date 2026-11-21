import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import analytics
import monitor_capacity as slots
import platform_admin
import workspace as ws


class MonitorCapacity(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        path=Path(self.tmp.name)/"qa.db"
        self.db=sqlite3.connect(path);self.addCleanup(self.db.close)
        analytics.init(self.db);ws.init(self.db);platform_admin.init(self.db,path)
        self.db.executemany("INSERT INTO users(id,name,email,owner) VALUES(?,?,?,?)",[
            (1,"Owner","owner@example.test",None),(2,"Operator","op@example.test",None),
            (3,"Member","member@example.test",1),(4,"Guest",None,None)])
        self.db.execute("INSERT INTO platform_admins VALUES(2)")
        self.owner,self.op,self.member,self.guest=(ws.get_user(self.db,i) for i in range(1,5))
        self.data={"slots":2,"reason":"Track a launch","nonce":"launch-request-01"}
        self.db.commit()

    def test_addition_expiration_recovery_rejection_and_tenant_isolation(self):
        db=self.db
        with patch.object(ws,"period",return_value="2026-12"):
            for user in (self.guest,self.member):
                with self.assertRaises(ws.RequestError):slots.request(db,user,self.data)
            first=slots.request(db,self.owner,self.data)["id"]
            self.assertEqual(slots.request(db,self.owner,self.data)["id"],first)
            with self.assertRaises(ws.RequestError):slots.request(db,self.owner,{**self.data,"slots":7})
            self.assertFalse(slots.history(db,self.op,{})["items"])
            self.assertEqual(slots.capacity(db,1)["limit"],10)
            with self.assertRaises(ws.RequestError):slots.review(db,self.owner,{"id":first,"status":"approved"})
            self.assertEqual(len(slots.history(db,self.op,{},operator=True)["items"]),1)
            decision={"id":first,"status":"approved","note":"Launch scheduled"}
            slots.review(db,self.op,decision);slots.review(db,self.op,decision)
            self.assertEqual(slots.capacity(db,1)["added"],2)
            self.assertEqual(ws.me(db,self.member)["limits"]["monitors"],12)
            second=slots.request(db,self.owner,{**self.data,"nonce":"launch-request-02"})["id"]
            with self.assertRaises(ValueError):slots.review(db,self.op,{"id":second,"status":"rejected"})
            slots.review(db,self.op,{"id":second,"status":"rejected","note":"Duplicate request"})
            with self.assertRaises(ws.RequestError):slots.review(db,self.op,{"id":second,"status":"approved"})
            third=slots.request(db,self.owner,{**self.data,"nonce":"launch-request-03"})["id"]
            # Exercise normal create and resume paths; the first ten are plan slots.
            create=lambda i:ws.mutate_list(db,self.member,"monitors",{"source":"demo","market":"US","kind":"products","id":f"p{i:02}"})
            for i in range(1,13):create(i)
            with self.assertRaises(ws.RequestError):create(13)
            ws.sample(db)
            items=ws.list_items(db,self.owner,"monitors")["items"]
            mid=next(r["mid"] for r in items if r["id"]=="p12")
            self.assertEqual(len(items),12)
        with patch.object(ws,"period",return_value="2027-01"):
            with self.assertRaises(ws.RequestError):slots.review(db,self.op,{"id":third,"status":"approved"})
            ws.sample(db)
            listing=ws.list_items(db,self.owner,"monitors")
            self.assertEqual(listing["limit"],10)
            paused=[r for r in listing["items"] if r["status"]=="completed"]
            self.assertEqual({r["id"] for r in paused},{"p11","p12"})
            self.assertTrue(all(r["capacity_ended"] and r["readings"] for r in paused))
            with self.assertRaises(ws.RequestError):ws.mutate_list(db,self.member,"monitors",{"mid":mid,"status":"active"})
            with self.assertRaises(ws.RequestError):create(13)
            next_id=slots.request(db,self.owner,{**self.data,"nonce":"launch-request-04"})["id"]
            slots.review(db,self.op,{"id":next_id,"status":"approved"})
            ws.mutate_list(db,self.member,"monitors",{"mid":mid,"status":"active"})
            resumed=next(r for r in ws.list_items(db,self.member,"monitors")["items"] if r["mid"]==mid)
            self.assertEqual(resumed["status"],"active")
            self.assertIsNone(resumed["capacity_ended"])
            old=next(r for r in slots.history(db,self.owner,{})["items"] if r["id"]==first)
            self.assertEqual((old["status"],old["reviewer"],old["note"],old["expired"]),("approved","Operator","Launch scheduled",True))

    def test_bound_platform_admin_can_review_own_workspace_and_invalid_quantity_is_rejected(self):
        for q in (None,0,True,1.5,"-1","1000000"):
            with self.assertRaises(ValueError):slots.request(self.db,self.op,{**self.data,"slots":q})
        row=slots.request(self.db,self.op,self.data)
        slots.review(self.db,self.op,{**row,"status":"approved"})
        self.assertEqual(slots.capacity(self.db,2)["added"],2)

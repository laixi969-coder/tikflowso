import json
import sqlite3
import unittest
from unittest.mock import patch

import analytics
import contacts
import stream
import studio
import workspace


class AdapterTests(unittest.TestCase):
    def setUp(self):
        self.db=sqlite3.connect(":memory:")
        self.addCleanup(self.db.close)
        self.db.row_factory=sqlite3.Row
        self.db.executescript(analytics.SCHEMA)
        workspace.init(self.db)
        stream.init(self.db)
        contacts.init(self.db)
        self.db.execute("INSERT INTO users(name,email) VALUES('Ana','ana@example.test')")
        self.user=workspace.get_user(self.db,1)
        batch=[{"market":"US","kind":k,"id":"01","date":"2026-11-19","gmv":10,"sales":1,"name":"Example"} for k in ("creators","lives")]
        analytics.import_rows(self.db,batch,"licensed",shared=True)
        self.db.commit()

    def test_private_contact_catalog(self):
        item={"source":"licensed","market":"US","rows":[{"id":"01","email":"test@example.test","rights":"Test agreement"}]}
        contacts.mutate(self.db,self.user,item)
        self.assertEqual(contacts.catalog(self.db,self.user,{"source":"licensed","q":"example"})[0]["email"],"test@example.test")
        self.db.execute("INSERT INTO users(name,email) VALUES('B','b@example.test')")
        other=workspace.get_user(self.db,2)
        self.assertEqual(contacts.catalog(self.db,other,{"source":"licensed"}),[])
        with self.assertRaises(ValueError):
            contacts.mutate(self.db,self.user,{**item,"rows":[{"id":"missing","email":"x@example.test","rights":"test"}]})

    def test_stream_auth_revisions_and_missing_entities(self):
        point={"market":"US","kind":"lives","id":"01","time":"2026-11-20T09:00:00Z","metric":"online_viewers","value":80}
        with patch.dict("os.environ",{"TIKFLOWSO_STREAM_TOKEN":"secret","TIKFLOWSO_STREAM_SOURCE":"licensed"}):
            with self.assertRaises(workspace.RequestError): stream.ingest(self.db,"wrong",{"points":[point]})
            with self.db:
                stream.ingest(self.db,"secret",{"points":[point]})
                stream.ingest(self.db,"secret",{"points":[{**point,"value":88}]})
            result=stream.recent(self.db,{**point,"source":"licensed"})
            self.assertEqual([r["value"] for r in result],[88])
            self.assertEqual(stream.recent(self.db,{**point,"source":"licensed"},window=("2026-11-20","2026-11-20")),result)
            self.assertEqual(stream.recent(self.db,{**point,"source":"licensed"},window=("2026-11-01","2026-11-19")),[])
            with self.assertRaises(ValueError),self.db:
                stream.ingest(self.db,"secret",{"points":[{**point,"id":"unknown"}]})

    def test_translated_regions_validate_geometry(self):
        block={"box":[0.1,0.2,0.4,0.3],"original":"Cup","translation":"杯子"}
        payload={"tool":"image_translate","text":"简体中文","images":["data:image/png;base64,YQ=="]}
        with patch("studio.model_configured",return_value=True),patch("studio.infer",return_value=json.dumps({"blocks":[block]})):
            reply=studio.generate(self.db,payload)
        self.assertEqual(reply["blocks"],[block])
        with self.assertRaises(workspace.RequestError):
            studio.translation_regions(json.dumps({"blocks":[{**block,"box":[0.9,0,0.5,1]}]}))


if __name__=="__main__": unittest.main()

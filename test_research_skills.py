"""The public assistant templates must remain useful with an empty model key."""
import json
import os
import sqlite3
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from unittest.mock import patch
from urllib.parse import parse_qs

import analytics
import research_skills
import studio


class AssistantTemplates(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db=sqlite3.connect(":memory:")
        analytics.init(cls.db)
        cls.scope={"source":"demo","market":"GB","date":"2026-11-15","days":"7"}

    @classmethod
    def tearDownClass(cls):
        cls.db.close()

    def ask(self,skill,**params):
        data={**self.scope,"tool":"agent","skill":skill,"text":research_skills.SKILLS[skill][-1],
              "locale":"en-US",**params}
        with patch.object(studio,"model_configured",return_value=False):
            return studio.generate(self.db,data)

    def test_each_recipe_has_actionable_answers_and_scoped_references_in_both_languages(self):
        library=research_skills.catalog()
        self.assertEqual([sum(i["group"]==g["id"] for i in library["items"]) for g in library["groups"]],[3]*4)
        for skill in library["items"]:
            for lang,locale in [("zh","zh-CN"),("en","en-US")]:
                with self.subTest(skill=skill["id"],lang=lang):
                    a=self.ask(skill["id"],locale=locale,text=skill["prompt"][lang])
                    self.assertIn(skill["title"][lang],a["result"])
                    self.assertIn("GBP",a["result"])
                    self.assertIn("2026-11-09",a["result"])
                    self.assertTrue(a["references"])
                    for ref in a["references"]:
                        filters={k:v[0] for k,v in parse_qs(ref["href"].partition("?")[2]).items()}
                        self.assertEqual({k:filters[k] for k in self.scope},self.scope)
                        detail=analytics.handle(self.db,"/api/detail",filters)
                        self.assertEqual(detail["item"]["name"],ref["label"])

    def test_focus_and_pasted_comments_change_the_evidence(self):
        first=self.ask("video_script",focus="p01",text="Use window light")
        self.assertEqual(len(first["references"]),1)
        self.assertIn("id=p01",first["references"][0]["href"])
        self.assertIn("Use window light",first["result"])
        self.assertIn("0–3 s",first["result"])
        named=self.ask("image_prompts",text="Compare p01 with p02 for this campaign")
        self.assertEqual({parse_qs(r["href"].split("?")[1])["id"][0] for r in named["references"]},{"p01","p02"})
        none=self.ask("growth",focus="does-not-exist")
        self.assertEqual(none["references"],[])
        self.assertIn("No qualifying records",none["result"])
        comments=self.ask("interest",comments="I want to buy this.\nWhere is the link?\nIt is broken.")
        self.assertIn("Pasted comments · 3",comments["result"])
        self.assertIn("Purchase-language matches 1",comments["result"])
        self.assertIn("negative 1",comments["result"])
        reviews=self.ask("interest")
        self.assertIn("Linked product reviews (separate from creator comments)",reviews["result"])
        with self.assertRaises(ValueError):
            self.ask("interest",comments="x"*6001)

    def test_model_receives_edited_brief_scoped_evidence_citations_and_history(self):
        received=[]
        class Model(BaseHTTPRequestHandler):
            def do_POST(self):
                received.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
                self.send_response(200)
                self.send_header("Content-Type","application/json")
                self.end_headers()
                self.wfile.write(b'{"choices":[{"message":{"content":"Local fixture model reply"}}]}')
            def log_message(self,*args):
                pass
        with HTTPServer(("127.0.0.1",0),Model) as server:
            worker=threading.Thread(target=server.handle_request,daemon=True)
            worker.start()
            env={"TIKFLOWSO_TRUST_LOCAL_MODEL":"1","TIKFLOWSO_MODEL_URL":f"http://127.0.0.1:{server.server_port}/v1/chat/completions","TIKFLOWSO_MODEL":"fixture"}
            with patch.dict(os.environ,env),patch.object(studio.control_settings,"current",return_value={"prompts":{}}):
                a=studio.generate(self.db,{**self.scope,"skill":"interest","tool":"agent","text":"Use two bullets",
                                  "comments":"I want to buy this item","locale":"en-US"},previous=[{"question":"Prior question","answer":"Prior answer"}])
            worker.join(2)
        self.assertEqual(a["result"],"Local fixture model reply")
        self.assertEqual(a["mode"],"Model · database query")
        messages=received[0]["messages"]
        self.assertIn("Do not invent platform data",messages[0]["content"])
        sent=messages[1]["content"][0]["text"]
        for value in ("Use two bullets","Prior answer","I want to buy this item","2026-11-09",a["references"][0]["href"]):
            self.assertIn(value,sent)

    def test_explicit_id_wins_and_creator_efficiency_requires_matching_days(self):
        source = "focus-coverage-fixture"
        rows = [dict(kind="products",id=key,name=name,sales=units,gmv=units,market="GB",date="2026-11-15")
                for key,name,units in [("sku","Exact item",1),("sku-plus","Sibling item",100)]]
        rows += [dict(kind="creators",id=key,name=key,sales=units,gmv=units,market="GB",date=stamp,views=views)
                 for key,stamp,units,views in [("partial","2026-11-14",100,None),("partial","2026-11-15",1,10),
                                              ("measured","2026-11-14",2,0),("measured","2026-11-15",2,20)]]
        analytics.import_rows(self.db,rows,source,shared=True)
        exact = self.ask("video_script",source=source,focus="sku",days=1)
        self.assertEqual([r["label"] for r in exact["references"]],["Exact item"])
        shortlist = self.ask("creator_fit",source=source,days=2)
        self.assertEqual([r["label"] for r in shortlist["references"]],["measured"])
        self.assertIn("units / 1,000 views 200",shortlist["result"])

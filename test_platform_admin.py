import json
import os
from pathlib import Path
import sqlite3
import stat
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

import control_settings
import platform_admin as admin
import prompts
import studio
import vision
import workspace


class PlatformAdministrationTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.path=Path(temp.name)/"test.sqlite3"
        cfg=patch.object(control_settings,"FILE",self.path.with_suffix(".providers.json"))
        cfg.start()
        self.addCleanup(cfg.stop)
        env=patch.dict(os.environ,{"TIKFLOWSO_VISION_PROVIDER":"bailian","DASHSCOPE_API_KEY":"env-fixture"},clear=True)
        env.start()
        self.addCleanup(env.stop)
        self.db=sqlite3.connect(self.path)
        self.db.row_factory=sqlite3.Row
        self.addCleanup(self.db.close)
        with self.db:
            workspace.init(self.db)
            admin.init(self.db,self.path)
            self.db.execute("INSERT INTO users(id,email,name) VALUES(1,'a@example.invalid','test')")
        self.user=workspace.get_user(self.db,1)

    def test_secret_precedence_snapshot_replacement_and_restart(self):
        old=control_settings.read()
        admin.save({"provider":"bailian","model":"vision-v2","key":"new-fixture","activate":True,"revision":0},self.path)
        self.assertEqual(vision.credential(),"new-fixture")
        self.assertEqual(stat.S_IMODE(control_settings.FILE.stat().st_mode),0o600)
        self.assertNotIn("new-fixture",json.dumps(admin.state(self.path)))
        with control_settings.pin(old):
            self.assertEqual(vision.credential(),"env-fixture")
        admin.save({"provider":"bailian","model":"vision-v3","key":"","revision":1},self.path)
        self.assertEqual(vision.credential(),"new-fixture")
        admin.save({"provider":"bailian","model":"vision-v3","clear_key":True,"revision":2},self.path)
        self.assertEqual(vision.credential(),"")
        with self.assertRaises(workspace.RequestError):
            admin.launch(self.db,None,self.path,self.user,{"provider":"bailian","revision":3,"kind":"acceptance"})

    def test_simultaneous_edit_has_one_winner_and_prompt_can_reset(self):
        barrier=threading.Barrier(2)
        statuses=[]
        def save(text):
            barrier.wait()
            try:
                admin.save_prompt({"revision":0,"name":"ideas","text":text})
                statuses.append(200)
            except workspace.RequestError as exc:statuses.append(exc.status)
        threads=[threading.Thread(target=save,args=(name,)) for name in ("first","second")]
        for thread in threads:thread.start()
        for thread in threads:thread.join()
        self.assertEqual(sorted(statuses),[200,409])
        self.assertIn(prompts.instruction("ideas"),("first","second"))
        admin.save_prompt({"revision":1,"name":"ideas","reset":True})
        self.assertEqual(prompts.instruction("ideas"),prompts.LIBRARY["ideas"][1])

    def test_bootstrap_and_interrupted_job_recovery(self):
        token=admin.setup_path(self.path)
        self.assertEqual(stat.S_IMODE(token.stat().st_mode),0o600)
        with self.assertRaises(workspace.RequestError):admin.require(self.db,self.user)
        code=token.read_text()
        admin.claim(self.db,self.user,self.path,code)
        admin.require(self.db,self.user)
        self.assertFalse(token.exists())
        with self.assertRaises(workspace.RequestError):admin.claim(self.db,self.user,self.path,code)
        with self.db:
            self.db.execute("INSERT INTO cloud_jobs(kind,provider,model,revision,actor,created,status) VALUES('probe','atlas','test',0,1,0,'running')")
            admin.init(self.db,self.path)
        self.assertEqual(admin.jobs(self.db)[0]["status"],"interrupted")
        self.assertFalse(token.exists())

    def test_directory_rejects_text_only_and_accepts_private_deployment(self):
        directory=admin.directory(self.path)
        directory.mkdir()
        (directory/"openrouter.json").write_text(json.dumps({"base_url":vision.profile("openrouter")["base"],
                        "entries":[{"id":"text-model","inputs":["text"]}]}))
        with self.assertRaises(ValueError):
            admin.save({"provider":"openrouter","model":"text-model","revision":0},self.path)
        admin.save({"provider":"volcengine","model":"ep-private","revision":0,"activate":True},self.path)
        self.assertEqual(vision.model(),"ep-private")

    def test_each_text_tool_uses_its_own_saved_instruction(self):
        tasks=("agent","ideas","promotion","title","product_title","outreach","extract")
        with patch.object(studio,"model_configured",return_value=True), \
             patch.object(studio,"research",return_value=("查询记录",[])), \
             patch.object(studio,"infer",return_value="生成结果") as infer:
            for revision,task in enumerate(tasks):
                with self.subTest(task=task):
                    instruction="该任务专用指令 "+task
                    admin.save_prompt({"revision":revision,"name":task,"text":instruction})
                    result=studio.generate(self.db,{"tool":task,"text":"商品素材"})
                    system,brief,images=infer.call_args.args
                    self.assertIn(instruction,system)
                    self.assertIn("商品素材",brief)
                    self.assertEqual(images,[])
                    self.assertEqual(result["result"],"生成结果")
                    if task=="agent":
                        self.assertIn("查询记录",brief)

    def test_failed_sample_keeps_remaining_results_and_expected_outcome(self):
        def run_sample(case):
            if case=="zh":
                raise ValueError("接口拒绝样例")
            return case!="en",{"result":"样例输出"}

        with patch.object(admin,"sample",side_effect=run_sample):
            admin.launch(self.db,lambda:sqlite3.connect(self.path),self.path,self.user,
                         {"kind":"acceptance","revision":0,"provider":"bailian"})
            deadline=time.monotonic()+5
            while time.monotonic()<deadline:
                report=admin.jobs(self.db)[0]
                if report["status"]!="running":
                    break
                time.sleep(.01)
        self.assertEqual(report["status"],"failed")
        en,zh,empty,video=report["results"]
        self.assertFalse(en["passed"])
        self.assertEqual(en["expected"],admin.SAMPLE_EXPECTATIONS["en"])
        self.assertEqual(zh["error"],"接口拒绝样例")
        self.assertTrue(empty["passed"] and video["passed"])

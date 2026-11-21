"""Regression cases independent of vision model downloads. Real inference lives in qa/vision_acceptance.cjs."""
import json
import os
from pathlib import Path
import tempfile
import threading
from http.server import BaseHTTPRequestHandler,HTTPServer
import unittest
from unittest.mock import patch

import connections
import settings
import vision


class VisionTests(unittest.TestCase):
    def test_config_is_literal_and_environment_takes_priority(self):
        with tempfile.TemporaryDirectory() as d,patch.dict(os.environ,clear=True):
            f=Path(d)/"config"
            f.write_text("TIKFLOWSO_VISION_PROVIDER=custom\nTIKFLOWSO_CUSTOM_MODEL=from-file\nMAIL_PASSWORD='a$(literal)'\nSMS_TOKEN=\n")
            os.environ.update(TIKFLOWSO_ENV_FILE=str(f),TIKFLOWSO_CUSTOM_MODEL="override")
            settings.load()
            self.assertEqual(vision.model(),"override")
            self.assertEqual(os.environ["MAIL_PASSWORD"],"a$(literal)")
            self.assertNotIn("SMS_TOKEN",os.environ)

    def test_local_address_and_media_validation(self):
        with patch.dict(os.environ,TIKFLOWSO_VISION_PROVIDER="custom",TIKFLOWSO_CUSTOM_BASE_URL="http://example.com"):
            with self.assertRaises(ValueError):vision.call("models")
        with self.assertRaises(ValueError):vision.translate("data:image/png;base64,YQ==","English")
        with self.assertRaises(ValueError):vision.analyze_video(b"", "")
        with patch.dict(os.environ,TIKFLOWSO_VISION_PROVIDER="custom",TIKFLOWSO_CUSTOM_BASE_URL="http://localhost",TIKFLOWSO_CUSTOM_MODEL="test",TIKFLOWSO_MODEL_KEY="fixture"):
            with patch.dict(os.environ,TIKFLOWSO_MODEL_KEY=""),self.assertRaises(vision.RequestError) as missing:
                with vision.inference_slot():pass
            self.assertEqual(missing.exception.status,503)
            with vision.inference_slot(),self.assertRaises(vision.RequestError) as err:
                with vision.inference_slot():pass
            self.assertEqual(err.exception.status,429)

    def test_missing_output_and_truncation(self):
        for result in [{"choices":[{"message":{"content":"invalid"}}]},{"choices":[{"finish_reason":"length","message":{"content":"{}"}}]}]:
            with patch.dict(os.environ,TIKFLOWSO_VISION_PROVIDER="deepseek"),patch("vision.call",return_value=result),self.assertRaises(vision.RequestError):
                vision.ask("describe","",{})

    def test_five_provider_catalogs_and_inference_keep_distinct_keys(self):
        seen=[]
        class Service(BaseHTTPRequestHandler):
            def log_message(self,*args): pass
            def reply(self,data):
                self.send_response(200)
                self.end_headers()
                self.wfile.write(json.dumps(data).encode())
            def do_GET(self):
                seen.append((self.path,self.headers.get("Authorization")))
                self.reply({"data":[{"id":"sample-model"}]})
            def do_POST(self):
                data=json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                seen.append((self.path,self.headers.get("Authorization")))
                self.server.test.assertEqual(data["model"],"sample-model")
                self.server.test.assertIn("image_url",data["messages"][-1]["content"][1])
                self.reply({"choices":[{"message":{"content":'{"title":"Green Tea"}'}}]})
        with HTTPServer(("127.0.0.1",0),Service) as http,tempfile.TemporaryDirectory() as tmp:
            http.test=self
            thread=threading.Thread(target=http.serve_forever,daemon=True)
            thread.start()
            try:
                for name,(_,_,key) in vision.PROVIDERS.items():
                    prefix="TIKFLOWSO_"+name.upper()
                    env={"TIKFLOWSO_TRUST_LOCAL_MODEL":"1",prefix+"_BASE_URL":f"http://127.0.0.1:{http.server_port}/{name}",prefix+"_MODEL":"sample-model",key:"fixture-"+name}
                    with patch.dict(os.environ,env,clear=True),patch.object(connections,"ROOT",Path(tmp)):
                        result=connections.sync_one(name)
                        self.assertTrue(result["listed"])
                        value=vision.ask("Title?","data:image/png;base64,AAAA",{},name)
                        self.assertEqual(value["title"],"Green Tea")
                        self.assertEqual(seen[-2:],[(f"/{name}/models","Bearer fixture-"+name),
                                                      (f"/{name}/chat/completions","Bearer fixture-"+name)])
                        connections.sync_one(name,True)
                        self.assertIsNone(seen[-1][1])
            finally:
                http.shutdown()
                thread.join()

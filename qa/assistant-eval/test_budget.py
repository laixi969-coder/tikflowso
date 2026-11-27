"""Exercise paid-mode accounting against a fake HTTP model on this machine only."""
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest

HERE=Path(__file__).resolve().parent


@contextmanager
def fake_model():
    class Model(BaseHTTPRequestHandler):
        def log_message(self,*_):pass
        def do_POST(self):
            payload=json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            self.server.requests+=1
            answer=payload["messages"][-1]["content"][0]["text"].split("\n参考查询：\n")[-1]
            response={"choices":[{"message":{"content":answer}}]}
            if self.server.usage:response["usage"]={"prompt_tokens":80,"completion_tokens":10}
            raw=json.dumps(response).encode()
            self.send_response(200)
            self.send_header("Content-Type","application/json")
            self.send_header("Content-Length",str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

    with ThreadingHTTPServer(("127.0.0.1",0),Model) as server:
        server.requests=0
        server.usage=True
        thread=threading.Thread(target=server.serve_forever,daemon=True)
        thread.start()
        try:yield server
        finally:
            server.shutdown()
            thread.join()


class CandidateBudgetTest(unittest.TestCase):
    def test_metered_unsettled_and_pre_dispatch_denial(self):
        with tempfile.TemporaryDirectory() as tmp,fake_model() as model:
            work=Path(tmp)
            config=work/"mock.json"
            config.write_text(json.dumps({"endpoint":f"http://127.0.0.1:{model.server_port}/chat/completions",
                "model":"local-fixture","context_tokens":1000,"max_output_tokens":250,
                "input_usd_per_million":1,"output_usd_per_million":2}))
            def run(budget,code):
                result=subprocess.run([sys.executable,str(HERE/"run.py"),"--candidate",str(config),
                    "--budget-usd",budget,"--limit","1","--output",str(work/"reports")],
                    capture_output=True,text=True,timeout=90,env={"PATH":os.environ["PATH"]})
                self.assertEqual(result.returncode,code,result.stdout[-1200:]+result.stderr[-1000:])
                return json.loads((work/"reports/summary.json").read_text())
            paid=run("0.01",0)
            self.assertEqual((paid["qualified_answers"],paid["metered_usd"],paid["model_usd_per_qualified_answer"]),
                             (1,0.0001,0.0001))
            model.usage=False
            unknown=run("0.01",0)
            self.assertEqual(unknown["unsettled_calls"],1)
            self.assertIsNone(unknown["model_cost_usd"])
            self.assertIsNone(unknown["model_usd_per_qualified_answer"])
            self.assertGreater(unknown["unsettled_reserved_usd"],0)
            denied=run("0.000001",1)
            self.assertEqual((model.requests,denied["model_calls"],denied["passed"]),(2,0,0))


if __name__=="__main__":unittest.main()

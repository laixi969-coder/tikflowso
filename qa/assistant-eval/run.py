"""Run Promptfoo against a temporary TikFlowSo HTTP workspace and its synthetic merchant ledger."""
import argparse
from contextlib import closing
from datetime import datetime, timezone
from decimal import Decimal
from http.cookiejar import CookieJar
import json
import math
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
from urllib.parse import urlsplit
from urllib.request import Request, HTTPCookieProcessor, ProxyHandler, build_opener

from suite import cases, datasets

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
PIN=json.loads((HERE/"package.json").read_text())["devDependencies"]["promptfoo"]


def storage(path, data):
    path.write_text(json.dumps(data,ensure_ascii=False,indent=2)+"\n")


def client():
    jar=CookieJar()
    return build_opener(ProxyHandler({}),HTTPCookieProcessor(jar)),jar


def post(opener, base, name, data):
    req=Request(base+"/api/"+name,json.dumps(data).encode(),{"Content-Type":"application/json"})
    with opener.open(req,timeout=15) as response:
        return json.load(response)


def populate(base, dbpath, candidate):
    (actor,cookies),(other,_)=client(),client()
    for api,name in [(actor,"owner"),(other,"other")]:
        post(api,base,"register",{"email":name+"@eval.invalid","password":"synthetic-only-123","name":name})
    sources={}
    for alias,rows in datasets().items():
        response=post(other if alias=="hidden" else actor,base,"import",
                      {"source":alias,"filename":"synthetic.json","rows":rows})
        sources[alias]=response["source"]
    # Dedicated synthetic tenant only; the free tier allows fewer generations than the suite has cases.
    with closing(sqlite3.connect(dbpath)) as db,db:
        db.execute("UPDATE users SET plan='pro' WHERE email='owner@eval.invalid'")
    if candidate:
        for source in (sources["blue"],sources["red"]):
            post(actor,base,"model-permissions",{"source":source,"destination":candidate["endpoint"]+" "+candidate["model"],
                                                "allow":True,"comments":False,"history":False})
    return sources,"; ".join(f"{c.name}={c.value}" for c in cookies)


def model_environment(path, candidate, budget):
    if candidate is None:return {}
    url=urlsplit(candidate["endpoint"])
    if not url.hostname or url.username or url.password or url.fragment or url.query or (
        url.scheme!="https" and not (url.scheme=="http" and url.hostname in ("127.0.0.1","localhost","::1"))):
        raise ValueError("candidate endpoint must be HTTPS or a local loopback HTTP endpoint")
    if not budget or not budget.is_finite() or budget<=0:
        raise ValueError("--candidate requires an explicit positive --budget-usd")
    fields=("endpoint","model","context_tokens","max_output_tokens","input_usd_per_million","output_usd_per_million")
    tariff={k:candidate[k] for k in fields}
    if "fixed_usd" in candidate:tariff["fixed_usd"]=candidate["fixed_usd"]
    pricing=path/"pricing.json"
    storage(pricing,{"models":[tariff],"platform_month_usd":str(budget),"workspace_month_usd":str(budget)})
    return {"TIKFLOWSO_MODEL_URL":tariff["endpoint"],"TIKFLOWSO_MODEL":tariff["model"],
            "TIKFLOWSO_MODEL_PRICING":str(pricing),"TIKFLOWSO_MODEL_KEY":os.getenv("TIKFLOWSO_EVAL_MODEL_KEY","")}


def summary(raw,dbpath,expected,candidate):
    stats=raw["results"]["stats"]
    results=raw["results"]["results"]
    passed=sum(row.get("success") is True for row in results)
    answers=sum(row.get("success") is True and row["testCase"]["vars"]["truth"]["type"]!="denied" for row in results)
    timings=[(row.get("response") or {}).get("metadata") or {} for row in results]
    latencies=sorted(t["httpMs"] for t in timings if t.get("httpMs") is not None)
    with closing(sqlite3.connect(dbpath)) as db:
        calls,unsettled,known,reserved=db.execute("""SELECT COUNT(*),COUNT(CASE WHEN state!='metered' THEN 1 END),
            COALESCE(SUM(CASE WHEN state='metered' THEN charged END),0),COALESCE(SUM(CASE WHEN state!='metered' THEN reserved END),0)
            FROM model_calls""").fetchone()
    total=None if unsettled else known/1e6
    errors=[{"case":r["testCase"].get("description"),"reason":(r.get("gradingResult") or {}).get("reason") or r.get("error")}
            for r in results if not r.get("success")]
    return {"utc":datetime.now(timezone.utc).isoformat(),"promptfoo":PIN,
            "mode":"candidate" if candidate else "offline","model":candidate["model"] if candidate else None,
            "expected":expected,"evaluated":len(results),"passed":passed,"qualified_answers":answers,"pass_rate":passed/expected,
            "errors":stats.get("errors",0),"http_latency_count":len(latencies),
            "http_p50_ms":round(latencies[math.ceil(.50*len(latencies))-1],2) if latencies else None,
            "http_p95_ms":round(latencies[math.ceil(.95*len(latencies))-1],2) if latencies else None,
            "model_calls":calls,"unsettled_calls":unsettled,"metered_usd":known/1e6,
            "unsettled_reserved_usd":reserved/1e6,"model_cost_usd":total,
            "model_usd_per_qualified_answer":total/answers if answers and total is not None else None,"failures":errors}


def run(args):
    executable=HERE/"node_modules/.bin/promptfoo"
    if not executable.is_file():raise SystemExit("Install the pinned QA dependencies with npm ci --prefix qa/assistant-eval")
    installed=json.loads((HERE/"node_modules/promptfoo/package.json").read_text())["version"]
    if installed!=PIN:raise SystemExit(f"Expected Promptfoo {PIN}, found {installed}")
    candidate=json.loads(args.candidate.read_text()) if args.candidate else None
    if args.limit is not None and args.limit<1:raise SystemExit("--limit must be positive")
    if args.budget_usd and not candidate:raise SystemExit("--budget-usd requires --candidate")
    out=(args.output or (HERE/"reports"/"candidate" if candidate else HERE/"reports")).resolve()
    out.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="tikflowso-assistant-eval-") as tmp:
        path=Path(tmp)
        dbpath=path/"eval.sqlite3"
        env={"PATH":os.environ["PATH"],"PYTHONDONTWRITEBYTECODE":"1","TIKFLOWSO_ENV_FILE":str(path/"none")}
        env.update(model_environment(path,candidate,args.budget_usd))
        with (path/"server.log").open("w") as log:
            server=subprocess.Popen([sys.executable,str(ROOT/"server.py"),"--db",str(dbpath),"--port","0"],
                                    cwd=ROOT,env=env,stdout=subprocess.PIPE,stderr=log,text=True)
            try:
                line=server.stdout.readline()
                if not line.startswith("tikflowso  http://127.0.0.1:"):raise RuntimeError("temporary service failed to start")
                base=line.split()[-1]
                sources,cookie=populate(base,dbpath,candidate)
                session=path/"session.json"
                storage(session,{"base":base,"cookie":cookie})
                session.chmod(0o600)
                tests=cases(sources)
                if args.limit:tests=tests[:args.limit]
                for test in tests:test["vars"]["candidate"]=bool(candidate)
                config=path/"eval.json"
                storage(config,{"description":"TikFlowSo bilingual research evidence benchmark",
                    "prompts":["{{question}}"],"providers":["file://"+str(HERE/"provider.cjs")],"tests":tests,
                    "defaultTest":{"assert":[{"type":"javascript","value":"file://"+str(HERE/"grade.cjs")}]}})
                cli_env={"PATH":os.environ["PATH"],"HOME":str(path),"TIKFLOWSO_EVAL_SESSION":str(session),
                         "PROMPTFOO_DISABLE_TELEMETRY":"1","PROMPTFOO_DISABLE_UPDATE":"1","PROMPTFOO_DISABLE_SHARE":"1",
                         "PROMPTFOO_CONFIG_DIR":str(path/"promptfoo-data"),"NO_COLOR":"1","CI":"1"}
                raw=path/"results.json"
                cli=subprocess.run([str(executable),"eval","-c",str(config),"-o",str(raw),"--no-cache","--no-share",
                                    "--no-write","--no-table","-j","1"],cwd=HERE,env=cli_env)
                if not raw.is_file():raise RuntimeError(f"Promptfoo exited {cli.returncode} before writing results")
                report=summary(json.loads(raw.read_text()),dbpath,len(tests),candidate)
                (out/"results.json").write_bytes(raw.read_bytes())
                storage(out/"summary.json",report)
                print(json.dumps(report,ensure_ascii=False,indent=2))
                return int(cli.returncode!=0 or report["passed"]!=len(tests))
            finally:
                server.terminate()
                server.wait(timeout=10)


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate",type=Path,help="Explicitly authorize this model for synthetic fixtures")
    parser.add_argument("--budget-usd",type=Decimal,help="Hard cap on this isolated run's model charges")
    parser.add_argument("--limit",type=int,help="Run the first N cases")
    parser.add_argument("--output",type=Path,help="Results directory; defaults to reports/ or reports/candidate/")
    sys.exit(run(parser.parse_args()))

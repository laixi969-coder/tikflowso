"""Exercise the real HTTP service under local reads/writes and verify a restored workspace."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from datetime import date,timedelta
from http.cookiejar import CookieJar
import argparse
import csv
import io
import json
import math
import os
from pathlib import Path
import socket
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
from urllib.request import build_opener, HTTPCookieProcessor, Request

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import analytics
import manage
import server


def start(path,env):
    with socket.socket() as sock:
        sock.bind(("127.0.0.1",0))
        port=sock.getsockname()[1]
    proc=subprocess.Popen([sys.executable,str(ROOT/"server.py"),"--db",str(path),"--port",str(port)],
                          env=env,stdout=subprocess.PIPE,text=True)
    if not proc.stdout.readline().startswith("tikflowso"):
        proc.terminate()
        raise RuntimeError("服务启动失败")
    return proc,f"http://127.0.0.1:{port}"


def fetch(client,base,path,data=None,raw=False):
    r=Request(base+path,None if data is None else json.dumps(data).encode(),{"Content-Type":"application/json"})
    with client.open(r,timeout=90) as response:
        return response.read() if raw else json.load(response)


def daily_rows(days,count):
    start=date(2025,1,1)
    for d in range(days):
        for n in range(count):
            yield {"market":"US","kind":"products","id":str(n),"name":f"Example {n}","category":"fixture",
                   "date":str(start+timedelta(d)),"sales":(d+n)%17,"gmv":(d+n)%17*3}


def exercise(tmp,seconds):
    dbpath=tmp/"active.db"
    server.DATABASE=dbpath
    server.initialize()
    with closing(server.connect()) as db,db:
        analytics.import_rows(db,daily_rows(365,300),"history")
        analytics.import_rows(db,daily_rows(1,60000),"large")
    env={k:v for k,v in os.environ.items() if not k.startswith(("TIKFLOWSO_","STRIPE_"))}
    env['TIKFLOWSO_ENV_FILE']=str(tmp/'isolated.env')
    proc,base=start(dbpath,env)
    try:
        client=build_opener(HTTPCookieProcessor(CookieJar()))
        acc={"name":"Acceptance","email":"bench@test.invalid","password":"local-only-12345"}
        fetch(client,base,"/api/register",acc)
        fetch(client,base,"/api/admin/claim",{"code":dbpath.with_suffix(".admin-setup.txt").read_text().strip()})
        fetch(client,base,"/api/admin/provider",{"provider":"atlas","model":"fixture-vision","key":"fixture-backup",
                                                "activate":True,"revision":0})
        fetch(client,base,"/api/admin/prompt",{"name":"ideas","text":"Recovery fixture","revision":1})
        with closing(server.connect()) as db,db:
            db.execute("UPDATE users SET plan='team' WHERE email=?",(acc["email"],))
        yearly=fetch(client,base,"/api/overview?source=history&days=365")
        assert len(yearly["trend"])==365 and yearly["coverage"]["gmv"]==365
        task=fetch(client,base,"/api/exports",{"params":{"source":"large","kind":"products","sort":"sales"},"request_key":"bench"})
        deadline=time.monotonic()+seconds

        def reader(slot):
            times=[]
            while time.monotonic()<deadline:
                t=time.monotonic()
                response=fetch(client,base,f"/api/rankings?source=history&days={7 if slot%2==0 else 30}&limit=5")
                assert response["total"]==300
                times.append((time.monotonic()-t)*1000)
            return times

        def writer():
            count=0
            with closing(server.connect()) as db:
                while time.monotonic()<deadline:
                    with db:
                        row=next(daily_rows(1,1))
                        analytics.import_rows(db,[{**row,"sales":count}],"ongoing")
                    count+=1
                    time.sleep(.15)
            return count

        with ThreadPoolExecutor(max_workers=5) as pool:
            reads=[pool.submit(reader,i) for i in range(4)]
            writes=pool.submit(writer)
            times=[t for future in reads for t in future.result()]
            write_count=writes.result()
        deadline=time.monotonic()+90
        while time.monotonic()<deadline:
            row=fetch(client,base,"/api/exports")["items"][0]
            if row["state"] in ("failed","ready"): break
            time.sleep(.25)
        assert row["state"]=="ready" and row["rows"]==60000,row
        uri="/api/exports/file?job="+str(task["job"])
        blob=fetch(client,base,uri,raw=True)
        rows=list(csv.DictReader(io.StringIO(blob.decode("utf-8-sig"))))
        assert len(rows)==60000 and len({r["id"] for r in rows})==60000
        assert all(int(r["rank"])==i for i,r in enumerate(rows,1))
        assert all(int(a["sales"])>=int(b["sales"]) for a,b in zip(rows,rows[1:]))
        assert fetch(client,base,"/api/me")["usage"]["export_rows"]==60000
        package=tmp/"backup"
        report=manage.deployment_backup(dbpath,package)["database"]
        target=tmp/"restored"
        shutil.copytree(package,target)
        assert manage.verify_deployment(target)["database"]==report
        backup_path=target/"tikflowso.sqlite3"
        restored,newbase=start(backup_path,env)
        try:
            fresh=build_opener(HTTPCookieProcessor(CookieJar()))
            fetch(fresh,newbase,"/api/login",acc)
            recovered=fetch(fresh,newbase,"/api/admin/settings")
            assert recovered["active"]=="atlas" and next(p for p in recovered["providers"] if p["name"]=="atlas")["has_key"]
            assert next(p for p in recovered["prompts"] if p["name"]=="ideas")["text"]=="Recovery fixture"
            assert (target/"tikflowso.providers.json").stat().st_mode & 0o777==0o600
            assert fetch(fresh,newbase,uri,raw=True)==blob
            assert fetch(fresh,newbase,"/api/overview?source=history&days=365")["metrics"]==yearly["metrics"]
        finally:
            restored.terminate();restored.wait()
        with (package/"tikflowso.providers.json").open("a") as file:file.write(" ")
        try:manage.verify_deployment(package)
        except ValueError:pass
        else:raise AssertionError("Changed backup passed checksum validation")
        return {"days":365,"history_facts":109500,"export_rows":len(rows),"csv_bytes":len(blob),
                "read_concurrency":4,"load_seconds":seconds,"reads":len(times),"write_commits":write_count,
                "http_p95_ms":round(sorted(times)[math.ceil(len(times)*.95)-1],1),"restored_verified":True,
                "backup_facts":report["analytics_daily"],"restored_admin_and_settings":True,"corruption_detected":True}
    finally:
        proc.terminate();proc.wait()


if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--seconds",default=30,type=int)
    args=p.parse_args()
    if args.seconds<1:p.error("seconds must be positive")
    with tempfile.TemporaryDirectory() as d:print(json.dumps(exercise(Path(d),args.seconds),indent=2))

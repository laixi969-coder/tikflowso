"""Restartable background ranking exports with temporary disk sorting and quota-on-publication."""
from contextlib import closing
import csv
import json
import secrets
import sqlite3
import tempfile

import analytics
import workspace as ws

FIELDS = ("market","source","date","days","currency","rank","id","kind","name","category",
          "gmv","sales","views","followers","follower_growth","growth","orders","refund_units","gmv_estimated")
SUMMARY = "job,state,created,finished,rows,error,params"
RETENTION = 7 * 86400


def init(db):
    db.execute("""CREATE TABLE IF NOT EXISTS export_jobs(
        job INTEGER PRIMARY KEY, uid INTEGER NOT NULL, owner INTEGER NOT NULL, request_key TEXT NOT NULL,
        params TEXT NOT NULL, state TEXT NOT NULL DEFAULT 'queued', created INTEGER NOT NULL,
        finished INTEGER, rows INTEGER, error TEXT, lease TEXT, expiry INTEGER, file BLOB,
        UNIQUE(uid,owner,request_key))""")


def safe(value):
    return "'"+value if isinstance(value,str) and value.lstrip().startswith(("=","+","-","@")) else value


def write_csv(file, scope, rows):
    writer = csv.DictWriter(file,FIELDS)
    writer.writeheader()
    for rank,row in enumerate(rows,1):
        values = {**row, **scope, "rank":rank, "gmv":row.get("gmv_exact", row["gmv"])}
        writer.writerow({k:safe(values.get(k)) for k in FIELDS})


def submit(db,user,data):
    key=ws.ident(data.get("request_key"),100)
    params=data.get("params")
    if not isinstance(params,dict): raise ValueError("缺少导出条件")
    params={k:str(params[k]) for k in analytics.RANKING_KEYS if params.get(k) not in ("", None)}
    ws.check_source(db,user,params.get("source","demo"))
    owner=ws.workspace(user)
    lookup = "SELECT job,params FROM export_jobs WHERE uid=? AND owner=? AND request_key=?"
    identity = (user["id"],owner,key)
    saved = db.execute(lookup,identity).fetchone()
    if not saved:
        scope = analytics.scope_for(db,params)
        analytics.ranking_filter(params.get("kind","products"),params)
        frozen = {**params,"date":scope["date"]}
        db.execute("""INSERT INTO export_jobs(uid,owner,request_key,params,created) VALUES(?,?,?,?,?)
                    ON CONFLICT(uid,owner,request_key) DO NOTHING""",
                   (*identity,json.dumps(frozen,ensure_ascii=False),ws.now()))
        saved = db.execute(lookup,identity).fetchone()
    stored = json.loads(saved[1])
    defaults = {"kind":"products","days":"7","market":"US","source":"demo","date":stored["date"]}
    if {**defaults, **stored} != {**defaults, **params}:
        raise ws.RequestError(409,"该请求标识已用于其他导出条件")
    return {"job":saved[0]}


def listing(db,user):
    return {"items":[{**dict(r),"params":json.loads(r["params"])} for r in db.execute(
        f"SELECT {SUMMARY} FROM export_jobs WHERE uid=? AND owner=? ORDER BY job DESC LIMIT 100",
        (user["id"],ws.workspace(user)))]}


def file_for(db,user,job):
    row=db.execute("SELECT state,length(file),params FROM export_jobs WHERE uid=? AND owner=? AND job=?",
                   (user["id"],ws.workspace(user),job)).fetchone()
    if not row: raise LookupError("未找到导出任务")
    ws.check_source(db,user,json.loads(row["params"]).get("source","demo"))
    if row["state"]!="ready": raise ws.RequestError(409,"导出文件尚不可用")
    return row[1], db.blobopen("export_jobs","file",job,readonly=True)


def run_one(connect):
    with closing(connect()) as db:
        now=ws.now()
        with db:
            db.execute("DELETE FROM export_jobs WHERE finished<?",(now-RETENTION,))
            token=secrets.token_hex(16)
            job=db.execute("""UPDATE export_jobs SET state='running',lease=?,expiry=? WHERE job=(
              SELECT job FROM export_jobs WHERE state='queued' OR (state='running' AND expiry<?)
              ORDER BY job LIMIT 1) RETURNING job,params,owner,uid""",(token,now+900,now)).fetchone()
        if not job: return False
        params=json.loads(job["params"])
        try:
            with tempfile.TemporaryDirectory(prefix="tikflowso-export-") as tmp:
                # Keep the read snapshot and the disk sort independent from quota and job writes.
                with closing(connect()) as reader, closing(sqlite3.connect(tmp+"/sort.db")) as spool:
                    reader.execute("BEGIN")
                    scope=analytics.scope_for(reader,params)
                    metric,rows=analytics.ranking_rows(reader,scope,params)
                    spool.execute("CREATE TABLE spool(metric NUMERIC,id TEXT,record TEXT)")
                    spool.executemany("INSERT INTO spool VALUES(?,?,?)",(
                        (analytics.ranking_value(row,metric),row["id"],json.dumps(row,ensure_ascii=False))
                        for row in rows))
                    reader.rollback()
                    count=spool.execute("SELECT COUNT(*) FROM spool").fetchone()[0]
                    rows=spool.execute("SELECT record FROM spool ORDER BY metric IS NULL,metric DESC,id")
                    with open(tmp+"/data.csv","w",encoding="utf-8-sig",newline="") as target:
                        write_csv(target,scope,(json.loads(r[0]) for r in rows))
                with open(tmp+"/data.csv","rb") as source, db:
                    length=source.seek(0,2)
                    source.seek(0)
                    done=db.execute("""UPDATE export_jobs SET state='ready',file=zeroblob(?),rows=?,finished=?
                                    WHERE job=? AND lease=? AND state='running'""",
                                    (length,count,ws.now(),job["job"],token))
                    if not done.rowcount: return True
                    user=ws.get_user(db,job["uid"])
                    if not user or ws.workspace(user)!=job["owner"]: raise ValueError("工作区权限已变更")
                    ws.check_source(db,user,params.get("source","demo"))
                    ws.consume(db,user,"export_rows",count)
                    with db.blobopen("export_jobs","file",job["job"]) as blob:
                        while block:=source.read(65536): blob.write(block)
        except Exception as exc:
            with db:
                db.execute("UPDATE export_jobs SET state='failed',finished=?,error=? WHERE job=? AND lease=?",
                           (ws.now(),str(exc)[:250],job["job"],token))
        return True

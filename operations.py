"""Minimal audit trail, outage diagnostics and bounded retention for operational records."""
from collections import Counter
from datetime import datetime,timezone
import os
import threading
import time

_LOCK=threading.Lock()
_REQUESTS=Counter()
_LATENCIES=Counter()


def init(db):
    db.executescript("""
      CREATE TABLE IF NOT EXISTS access_audit(event INTEGER PRIMARY KEY,stamp INTEGER NOT NULL,
        actor INTEGER,owner INTEGER,route TEXT NOT NULL,method TEXT NOT NULL,subject TEXT NOT NULL,
        status INTEGER NOT NULL,request_id TEXT NOT NULL);
      CREATE INDEX IF NOT EXISTS access_audit_time ON access_audit(stamp);
      CREATE TABLE IF NOT EXISTS notification_preferences(owner INTEGER,channel TEXT,enabled INTEGER NOT NULL,
        PRIMARY KEY(owner,channel));
      CREATE TABLE IF NOT EXISTS maintenance_state(name TEXT PRIMARY KEY,stamp INTEGER NOT NULL);
      CREATE TABLE IF NOT EXISTS error_groups(kind TEXT PRIMARY KEY,seen INTEGER NOT NULL,latest INTEGER NOT NULL,request_id TEXT);
    """)


def observed(status,duration):
    with _LOCK:
        _REQUESTS[status]+=1
        limit=next((ms for ms in (50,100,250,500,1000,5000) if duration<=ms),60000)
        _LATENCIES[limit]+=1


def record(db,actor,owner,route,method,subject,status,request_id,error):
    if error:
        db.execute("""INSERT INTO error_groups VALUES(?,1,?,?) ON CONFLICT(kind) DO UPDATE SET
            seen=seen+1,latest=excluded.latest,request_id=excluded.request_id""",(error,int(time.time()),request_id))
    if route.startswith("/api/admin/") or route in ("/api/detail","/api/export","/api/exports/file","/api/contacts",
        "/api/contacts/export","/api/assistant/chats","/api/support","/api/partners/asset","/api/model-permissions",
        "/api/keys","/api/team/remove","/api/sessions/revoke","/api/login","/api/password/reset"):
        db.execute("INSERT INTO access_audit(stamp,actor,owner,route,method,subject,status,request_id) VALUES(?,?,?,?,?,?,?,?)",
                   (int(time.time()),actor,owner,route,method,subject,status,request_id))


def overview(db):
    with _LOCK:
        requests=dict(_REQUESTS)
        latency=dict(_LATENCIES)
    return {"requests_by_status":requests,"request_ms_histogram":latency,
        "errors":[dict(r) for r in db.execute("SELECT * FROM error_groups ORDER BY latest DESC LIMIT 20")],
        "audit":[dict(r) for r in db.execute("SELECT * FROM access_audit ORDER BY event DESC LIMIT 100")],
        "billing":[dict(r) for r in db.execute("SELECT * FROM webhook_inbox WHERE state!='done' ORDER BY received DESC LIMIT 40")],
        "notifications":[dict(r) for r in db.execute("SELECT aid,channel,status,attempts FROM deliveries WHERE status IN ('failed','bounced','complained') ORDER BY aid DESC LIMIT 40")],
        "failed_exports":[dict(r) for r in db.execute("SELECT job,owner,error FROM export_jobs WHERE state='failed' ORDER BY job DESC LIMIT 40")],
        "spend":[dict(r) for r in db.execute("""SELECT owner,month,SUM(charged) AS usd_micros,
                   SUM(state='reserved') AS unsettled_calls FROM model_calls GROUP BY owner,month ORDER BY month DESC LIMIT 100""")],
        "jobs":dict(db.execute("SELECT state,count(*) FROM export_jobs GROUP BY state")),
        "maintenance":dict(db.execute("SELECT name,stamp FROM maintenance_state"))}


def retention(db):
    stamp=int(time.time())
    if not db.execute("""INSERT INTO maintenance_state VALUES('retention',?) ON CONFLICT(name) DO UPDATE SET stamp=excluded.stamp
                         WHERE stamp<?""",(stamp,stamp-86400)).rowcount:return
    for table,column,key,default in (("access_audit","stamp","AUDIT",90),("snapshot_revisions","changed_at","REVISION",0),
                                     ("webhook_inbox","received","WEBHOOK",180)):
        days=int(os.getenv("TIKFLOWSO_"+key+"_RETENTION_DAYS",str(default)))
        if days==0 and key=="REVISION": continue
        if days<1: raise ValueError("保留天数必须为正整数")
        extra=" AND state='done'" if table=="webhook_inbox" else ""
        db.execute(f"DELETE FROM {table} WHERE {column}<?"+extra,(stamp-days*86400,))
    for key,parent,child,column in (("CHAT","assistant_chats","assistant_turns","chat"),
                                     ("SUPPORT","support_cases","support_messages","ticket")):
        days=int(os.getenv("TIKFLOWSO_"+key+"_RETENTION_DAYS","0"))
        if days<0: raise ValueError("保留天数无效")
        if not days: continue
        cutoff=(stamp-days*86400,)
        condition="updated<?"+(" AND awaiting_reply=0" if key=="SUPPORT" else "")
        db.execute(f"DELETE FROM {child} WHERE {column} IN (SELECT id FROM {parent} WHERE {condition})",cutoff)
        db.execute(f"DELETE FROM {parent} WHERE {condition}",cutoff)
    grace=os.getenv("TIKFLOWSO_ASSET_GRACE_DAYS","").strip()
    if grace:
        days=int(grace)
        if days<0: raise ValueError("素材宽限天数无效")
        db.execute("DELETE FROM partner_files WHERE expires IS NOT NULL AND expires!='' AND expires<date('now',?)",("-"+str(days)+" days",))
    db.execute("DELETE FROM deleted_items WHERE expires<=?",(stamp,))
    db.execute("DELETE FROM password_resets WHERE expires<=?",(stamp,))
    db.execute("DELETE FROM admin_handoff WHERE expires<=?",(stamp,))
    db.execute("DELETE FROM delivery_receipts WHERE received<?",(stamp-180*86400,))


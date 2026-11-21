"""Tenant inbox and optional operator-routed email/SMS outbox for monitor hits."""
from contextlib import closing
from email.message import EmailMessage
import json
import os
from pathlib import Path
import secrets
import smtplib
import time
from urllib.parse import urlsplit
from urllib.request import build_opener, HTTPRedirectHandler, Request


def init(db):
    db.executescript("""
    CREATE TABLE IF NOT EXISTS alerts(
      aid INTEGER PRIMARY KEY,owner INTEGER NOT NULL,mid INTEGER NOT NULL,day TEXT NOT NULL,
      title TEXT NOT NULL,metric TEXT NOT NULL,value REAL NOT NULL,threshold REAL NOT NULL,
      created INTEGER NOT NULL,seen INTEGER DEFAULT 0,UNIQUE(owner,mid,day));
    CREATE INDEX IF NOT EXISTS alert_monitor ON alerts(mid);
    CREATE TABLE IF NOT EXISTS deliveries(
      aid INTEGER NOT NULL REFERENCES alerts(aid),channel TEXT NOT NULL,status TEXT NOT NULL,
      attempts INTEGER DEFAULT 0,due INTEGER NOT NULL,lease TEXT,PRIMARY KEY(aid,channel));
    """)


def config():
    path=os.getenv("TIKFLOWSO_ALERT_ROUTES")
    return json.loads(Path(path).read_text()) if path else {}


def record(db,monitor,day,value):
    stamp=int(time.time())
    row=db.execute("""INSERT INTO alerts(owner,mid,day,title,metric,value,threshold,created)
       VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(owner,mid,day) DO NOTHING RETURNING aid""",
       (monitor["owner"],monitor["mid"],day,monitor["name"],monitor["metric"],value,monitor["threshold"],stamp)).fetchone()
    if row:
        # Always persist the inbox first; the worker resolves delivery routes separately.
        for channel in ("email","sms"):
            db.execute("INSERT INTO deliveries(aid,channel,status,due) VALUES(?,?,'pending',?)",(row[0],channel,stamp))


def inbox(db,owner):
    rows=db.execute("""SELECT a.*, (SELECT group_concat(channel||'='||status,',') FROM deliveries d
      WHERE d.aid=a.aid AND d.status!='off') AS delivery FROM alerts a WHERE owner=? ORDER BY aid DESC LIMIT 100""",(owner,))
    return {"items":[dict(r) for r in rows]}


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,*args): return None


def deliver(alert,channel,route):
    body=f"{alert['day']} · {alert['title']} · {alert['metric']} {alert['value']:g} ≥ {alert['threshold']:g}"
    key=f"tikflowso-{alert['owner']}-{alert['aid']}"
    if channel=="email":
        msg=EmailMessage()
        msg["From"],msg["To"]=route["from"],route["to"]
        msg["Subject"]="tikflowso 监控提醒"
        msg["Message-ID"]=f"<{key}@tikflowso.local>"
        msg.set_content(body)
        with smtplib.SMTP(route["host"],int(route.get("port",587)),timeout=10) as conn:
            if route.get("starttls",True): conn.starttls()
            if route.get("user"): conn.login(route["user"],os.environ[route["password_env"]])
            conn.send_message(msg)
    else:
        url=route["url"]
        parsed=urlsplit(url)
        if parsed.scheme!="https" and not (parsed.scheme=="http" and parsed.hostname in ("localhost","127.0.0.1","::1")):
            raise ValueError("SMS gateway requires HTTPS or local HTTP")
        headers={"Content-Type":"application/json","Idempotency-Key":key}
        if route.get("token_env"): headers["Authorization"]="Bearer "+os.environ[route["token_env"]]
        req=Request(url,json.dumps({"to":route["to"],"text":body}).encode(),headers)
        with build_opener(NoRedirect).open(req,timeout=10): pass


def run_one(connect):
    now=int(time.time())
    with closing(connect()) as db:
        with db:
            lease=secrets.token_hex(12)
            job=db.execute("""UPDATE deliveries SET lease=?,due=?,status='sending',attempts=attempts+1
                 WHERE rowid=(SELECT rowid FROM deliveries WHERE status IN ('pending','retry','sending')
                 AND due<=? ORDER BY due,aid LIMIT 1) RETURNING aid,channel,attempts""",(lease,now+90,now)).fetchone()
        if not job: return False
        try:
            alert=db.execute("SELECT * FROM alerts WHERE aid=?",(job["aid"],)).fetchone()
            route=config().get(str(alert["owner"]),{}).get(job["channel"])
            if route: deliver(alert,job["channel"],route)
            state="sent" if route else "off"
        except (OSError,ValueError,KeyError,smtplib.SMTPException):
            state="failed" if job["attempts"]>=5 else "retry"
        with db:
            db.execute("UPDATE deliveries SET status=?,due=?,lease=NULL WHERE lease=?",
                       (state,now+min(600,2**job["attempts"]),lease))
    return True

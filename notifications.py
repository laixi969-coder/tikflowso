"""Tenant inbox and optional operator-routed email/SMS outbox for monitor hits."""
from contextlib import closing
from email.message import EmailMessage
import json
import hmac
import re
import os
from pathlib import Path
import secrets
import smtplib
import ssl
import source_policy
import time
from urllib.parse import urlsplit
from urllib.request import build_opener, HTTPRedirectHandler, Request


def init(db):
    db.execute("CREATE TABLE IF NOT EXISTS notification_preferences(owner INTEGER,channel TEXT,enabled INTEGER NOT NULL,PRIMARY KEY(owner,channel))")
    db.executescript("""
    CREATE TABLE IF NOT EXISTS alerts(
      aid INTEGER PRIMARY KEY,owner INTEGER NOT NULL,mid INTEGER NOT NULL,day TEXT NOT NULL,
      title TEXT NOT NULL,metric TEXT NOT NULL,value REAL NOT NULL,threshold REAL NOT NULL,
      created INTEGER NOT NULL,seen INTEGER DEFAULT 0,UNIQUE(owner,mid,day));
    CREATE INDEX IF NOT EXISTS alert_monitor ON alerts(mid);
    CREATE TABLE IF NOT EXISTS delivery_receipts(event TEXT PRIMARY KEY,received INTEGER NOT NULL);
    CREATE TABLE IF NOT EXISTS deliveries(
      aid INTEGER NOT NULL REFERENCES alerts(aid),channel TEXT NOT NULL,status TEXT NOT NULL,
      attempts INTEGER DEFAULT 0,due INTEGER NOT NULL,lease TEXT,PRIMARY KEY(aid,channel));
    """)
    if "source" not in {r[1] for r in db.execute("PRAGMA table_info(alerts)")}:
        db.execute("ALTER TABLE alerts ADD COLUMN source TEXT")
    if db.execute("SELECT 1 FROM sqlite_master WHERE name='monitors'").fetchone():
        db.execute("UPDATE alerts SET source=(SELECT m.source FROM monitors m WHERE m.mid=alerts.mid AND m.owner=alerts.owner) WHERE source IS NULL")


def config():
    path=os.getenv("TIKFLOWSO_ALERT_ROUTES")
    return json.loads(Path(path).read_text()) if path else {}


def record(db,monitor,day,value):
    stamp=int(time.time())
    row=db.execute("""INSERT INTO alerts(owner,mid,day,title,metric,value,threshold,created,source)
       VALUES(?,?,?,?,?,?,?,?,?) ON CONFLICT(owner,mid,day) DO NOTHING RETURNING aid""",
       (monitor["owner"],monitor["mid"],day,monitor["name"],monitor["metric"],value,monitor["threshold"],stamp,monitor["source"])).fetchone()
    if row:
        # Always persist the inbox first; the worker resolves delivery routes separately.
        for channel in ("email","sms"):
            db.execute("INSERT INTO deliveries(aid,channel,status,due) VALUES(?,?,'pending',?)",(row[0],channel,stamp))


def inbox(db,owner):
    rows=db.execute(f"""SELECT a.*, (SELECT group_concat(channel||'='||status,',') FROM deliveries d
      WHERE d.aid=a.aid AND d.status!='off') AS delivery FROM alerts a WHERE owner=? AND source IN ({source_policy.VISIBLE}) ORDER BY aid DESC LIMIT 100""",(owner,owner))
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
            if not route.get("starttls",True) and route["host"] not in ("localhost","127.0.0.1","::1"):
                raise ValueError("外部提醒邮件需要加密连接")
            if route.get("starttls",True): conn.starttls(context=ssl.create_default_context())
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


def feedback(db,raw,signature):
    from workspace import RequestError
    key=os.getenv("TIKFLOWSO_ALERT_FEEDBACK_SECRET","")
    expected=hmac.digest(key.encode(),raw,"sha256").hex()
    if not key or not hmac.compare_digest(expected,str(signature or "")):
        raise RequestError(403,"通知回执未获授权")
    report=json.loads(raw)
    stamp=int(time.time())
    if not isinstance(report,dict) or type(report.get("timestamp")) is not int or abs(report["timestamp"]-stamp)>300:
        raise ValueError("通知回执时间无效")
    event=str(report.get("event",""))
    state=report.get("status")
    message=re.fullmatch(r"<?tikflowso-([0-9]+)-([0-9]+)(?:@tikflowso\.local)?>?",str(report.get("message_id","")))
    if not re.fullmatch(r"[A-Za-z0-9_.-]{1,150}",event) or state not in ("bounced","complained") or not message:
        raise ValueError("通知回执格式无效")
    owner,aid=map(int,message.groups())
    if not db.execute("SELECT 1 FROM alerts WHERE aid=? AND owner=?",(aid,owner)).fetchone(): raise LookupError("找不到对应通知")
    if not db.execute("INSERT OR IGNORE INTO delivery_receipts VALUES(?,?)",(event,stamp)).rowcount: return {"duplicate":True}
    db.execute("UPDATE deliveries SET status=?,lease=NULL WHERE aid=? AND channel='email'",(state,aid))
    if state=="complained":
        db.execute("INSERT OR REPLACE INTO notification_preferences VALUES(?,'email',0)",(owner,))
    return {"ok":True}


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
            pref=db.execute("SELECT enabled FROM notification_preferences WHERE owner=? AND channel=?",(alert["owner"],job["channel"])).fetchone()
            if (pref and not pref[0]) or not source_policy.visible(db,alert["owner"],alert["source"]): route=None
            if route: deliver(alert,job["channel"],route)
            state="sent" if route else "off"
        except (OSError,ValueError,KeyError,smtplib.SMTPException):
            state="failed" if job["attempts"]>=5 else "retry"
        with db:
            db.execute("UPDATE deliveries SET status=?,due=?,lease=NULL WHERE lease=?",
                       (state,now+min(600,2**job["attempts"]),lease))
    return True

"""Identity, workspace membership, research lists, and snapshot monitors."""
import hashlib
import json
import hmac
import re
import secrets
import sqlite3
import time
from datetime import datetime, timedelta, timezone

import analytics
import notifications
import monitor_capacity
import account_security

LIMITS = {
    "free": {"api": 100, "monitors": 10, "generation": 30, "seats": 1, "export_rows": 1000, "detail_views": 500},
    "pro": {"api": 5000, "monitors": 100, "generation": 500, "seats": 1, "export_rows": 10000, "detail_views": 5000},
    "team": {"api": 50000, "monitors": 500, "generation": 2000, "seats": 10, "export_rows": 60000, "detail_views": 50000},
}


class RequestError(Exception):
    def __init__(self, status, message, retry_after=None):
        self.status = status
        self.retry_after = retry_after
        super().__init__(message)


def init(db):
    notifications.init(db)
    db.executescript("""
    CREATE TABLE IF NOT EXISTS users (
      id INTEGER PRIMARY KEY, email TEXT UNIQUE, name TEXT NOT NULL, password TEXT,
      plan TEXT NOT NULL DEFAULT 'free', owner INTEGER REFERENCES users(id)
    );
    CREATE TABLE IF NOT EXISTS sessions (
      digest TEXT PRIMARY KEY, uid INTEGER NOT NULL REFERENCES users(id), expires INTEGER NOT NULL
    );
    CREATE TABLE IF NOT EXISTS invites (
      digest TEXT PRIMARY KEY, owner INTEGER NOT NULL, email TEXT NOT NULL, expires INTEGER NOT NULL
    );
    CREATE TABLE IF NOT EXISTS access_keys (
      digest TEXT PRIMARY KEY, prefix TEXT NOT NULL, label TEXT NOT NULL, uid INTEGER NOT NULL, created INTEGER NOT NULL
    );
    CREATE TABLE IF NOT EXISTS usage (
      uid INTEGER NOT NULL, period TEXT NOT NULL, feature TEXT NOT NULL, amount INTEGER NOT NULL,
      PRIMARY KEY(uid,period,feature)
    );
    CREATE TABLE IF NOT EXISTS favorites (
      owner INTEGER NOT NULL, market TEXT NOT NULL, source TEXT NOT NULL, kind TEXT NOT NULL,
      id TEXT NOT NULL, name TEXT NOT NULL, created INTEGER NOT NULL,
      PRIMARY KEY(owner,market,source,kind,id)
    );
    CREATE TABLE IF NOT EXISTS ranking_presets (
      owner INTEGER NOT NULL, kind TEXT NOT NULL, name TEXT NOT NULL, params TEXT NOT NULL,
      PRIMARY KEY(owner,kind,name)
    );
    CREATE TABLE IF NOT EXISTS saved_topics (
      owner INTEGER NOT NULL, source TEXT NOT NULL, market TEXT NOT NULL, day TEXT NOT NULL,
      days INTEGER NOT NULL, grouping TEXT NOT NULL, topic TEXT NOT NULL,
      PRIMARY KEY(owner,source,market,day,days,grouping,topic)
    );
    CREATE TABLE IF NOT EXISTS monitors (
      mid INTEGER PRIMARY KEY, owner INTEGER NOT NULL, market TEXT NOT NULL, source TEXT NOT NULL,
      kind TEXT NOT NULL, id TEXT NOT NULL, name TEXT NOT NULL, metric TEXT NOT NULL,
      threshold REAL, status TEXT NOT NULL, created INTEGER NOT NULL,
      UNIQUE(owner,market,source,kind,id,metric)
    );
    CREATE TABLE IF NOT EXISTS readings (
      mid INTEGER REFERENCES monitors(mid) ON DELETE CASCADE, day TEXT NOT NULL, value REAL NOT NULL,
      hit INTEGER NOT NULL, PRIMARY KEY(mid,day)
    );
    CREATE TABLE IF NOT EXISTS imports (
      batch INTEGER PRIMARY KEY, owner INTEGER, source TEXT, count INTEGER, created INTEGER, filename TEXT
    );
    CREATE TABLE IF NOT EXISTS api_minutes (
      owner INTEGER PRIMARY KEY, minute INTEGER NOT NULL, calls INTEGER NOT NULL
    );
    """)
    import model_spend
    model_spend.init(db)
    import recycle
    recycle.init(db)
    account_security.init(db)
    monitor_capacity.init(db)
    for table,columns in {"monitors":{"capacity_ended":"INTEGER"},"favorites":{"date":"TEXT","days":"INTEGER"},
                          "imports":{"status":"TEXT DEFAULT 'ok'","error":"TEXT","latest_date":"TEXT"}}.items():
        existing={r[1] for r in db.execute(f"PRAGMA table_info({table})")}
        for name,definition in columns.items():
            if name not in existing:
                db.execute(f"ALTER TABLE {table} ADD COLUMN {name} {definition}")


def digest(s):
    return hashlib.sha256(s.encode()).hexdigest()


def now():
    return int(time.time())


def workspace(user):
    return user["owner"] or user["id"]


def get_user(db, uid):
    return db.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()


def effective_plan(db, user):
    return get_user(db, workspace(user))["plan"]


def session(db, token):
    return db.execute("""SELECT u.* FROM sessions s JOIN users u ON u.id=s.uid
                         WHERE s.digest=? AND s.expires>?""", (digest(token), now())).fetchone()


def issue_session(db, uid, *, assured=False):
    token = secrets.token_urlsafe(32)
    db.execute("DELETE FROM sessions WHERE expires<=?", (now(),))
    db.execute("INSERT INTO sessions(digest,uid,expires,assured) VALUES(?,?,?,?)", (digest(token), uid, now()+30*86400,int(assured)))
    return token


def guest(db):
    uid = db.execute("INSERT INTO users(name) VALUES('访客')").lastrowid
    return get_user(db, uid)


def ident(value, maximum=100):
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise ValueError("请填写有效的文本字段")
    return value.strip()


def email_value(value):
    value = ident(value, 254).lower()
    if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', value):
        raise ValueError("邮箱格式无效")
    return value


def derive(password, salt):
    return hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=2**14, r=8, p=1).hex()


def authenticate(db, action, data, user):
    email = email_value(data.get("email"))
    password = data.get("password")
    if not isinstance(password,str) or not 1<=len(password)<=200:
        raise ValueError("密码长度无效")
    if action == "register":
        if user["email"]:
            raise RequestError(409, "请先退出当前账户")
        if len(password) < 10:
            raise ValueError("密码至少需要 10 个字符")
        salt = secrets.token_hex(16)
        name = ident(data.get("name") or email.split("@")[0], 60)
        try:
            db.execute("UPDATE users SET email=?,name=?,password=? WHERE id=?",
                       (email, name, salt+"."+derive(password, salt), user["id"]))
        except sqlite3.IntegrityError as exc:
            raise RequestError(409, "邮箱已被注册") from exc
        return user["id"]
    found = db.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
    salt, stored = found["password"].split(".") if found else ("00"*16, "")
    if not hmac.compare_digest(derive(password, salt), stored):
        raise RequestError(401, "邮箱或密码有误")
    return found["id"]


def signed_in(user):
    if not user["email"]:
        raise RequestError(401, "请先注册或登录")


def admin(user):
    signed_in(user)
    if user["owner"]:
        raise RequestError(403, "需要工作区所有者权限")


def period():
    return datetime.now(timezone.utc).strftime("%Y-%m")


def quota_period(feature):
    if feature in ("export_rows","detail_views"):
        return datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return period()


def consume(db, user, feature, amount=1):
    owner = workspace(user)
    limit = LIMITS[effective_plan(db, user)][feature]
    if amount < 1: return
    if amount > limit:
        raise RequestError(429,"本次请求超过套餐额度，请缩小筛选范围")
    cur = db.execute("""INSERT INTO usage VALUES(?,?,?,?) ON CONFLICT(uid,period,feature)
      DO UPDATE SET amount=amount+excluded.amount WHERE amount+excluded.amount <= ?""",
      (owner, quota_period(feature), feature, amount, limit))
    if cur.rowcount == 0:
        msg = "当日额度已用完，将于次日 UTC 0 时重置" if feature in ("export_rows","detail_views") else "本月额度已用完，将于下月 UTC 1 日重置"
        today=datetime.now(timezone.utc)
        reset=(today+timedelta(days=1)).replace(hour=0,minute=0,second=0,microsecond=0)
        if feature not in ("export_rows","detail_views"):
            reset=(today.replace(day=28)+timedelta(days=4)).replace(day=1,hour=0,minute=0,second=0,microsecond=0)
        raise RequestError(429,msg,max(1,int(reset.timestamp())-int(today.timestamp())))


def consume_api(db,user):
    stamp=now()
    minute=stamp//60
    cur=db.execute("""INSERT INTO api_minutes(owner,minute,calls) VALUES(?,?,1)
      ON CONFLICT(owner) DO UPDATE SET minute=excluded.minute,
      calls=CASE WHEN minute=excluded.minute THEN calls+1 ELSE 1 END
      WHERE minute!=excluded.minute OR calls<60""",(workspace(user),minute))
    if not cur.rowcount:
        raise RequestError(429,"工作区每分钟最多发起 60 次 API 调用",60-stamp%60)


def me(db, user):
    owner = workspace(user)
    plan = effective_plan(db, user)
    return {"name": user["name"], "email": user["email"], "guest": not user["email"], "plan": plan,
            "role": "member" if user["owner"] else "owner", "limits": {**LIMITS[plan],"monitors":monitor_capacity.capacity(db,owner)["limit"]},
            "usage": dict(db.execute("SELECT feature,amount FROM usage WHERE uid=? AND period IN (?,?)", (owner, period(),quota_period("export_rows")))),
            "members": [dict(r) for r in db.execute("SELECT name,email FROM users WHERE id=? OR owner=? ORDER BY id", (owner, owner))]}


def invite(db,user,data):
    admin(user)
    owner = user["id"]
    email = email_value(data.get("email"))
    if LIMITS[user["plan"]]["seats"] < 2:
        raise RequestError(403,"团队套餐支持添加成员")
    token = secrets.token_urlsafe(24)
    db.execute("DELETE FROM invites WHERE owner=? AND email=?", (owner,email))
    db.execute("INSERT INTO invites VALUES(?,?,?,?)",(digest(token),owner,email,now()+86400))
    return {"invite":token}


def join(db,user,data):
    signed_in(user)
    if not db.in_transaction: db.execute("BEGIN IMMEDIATE")
    row = db.execute("SELECT * FROM invites WHERE digest=? AND expires>?",(digest(ident(data.get("invite"))),now())).fetchone()
    if not row or row["email"] != user["email"]:
        raise ValueError("邀请码无效、已过期或邮箱不匹配")
    owner = row["owner"]
    if user["owner"] or user["id"] == owner or user["plan"] != "free" or db.execute("SELECT 1 FROM users WHERE owner=?", (user["id"],)).fetchone():
        raise RequestError(409,"当前账户已有团队或订阅")
    plan = get_user(db,owner)["plan"]
    count = 1+db.execute("SELECT count(*) FROM users WHERE owner=?",(owner,)).fetchone()[0]
    if count >= LIMITS[plan]["seats"]:
        raise RequestError(409,"团队席位已满")
    db.execute("UPDATE users SET owner=? WHERE id=?", (owner,user["id"]))
    db.execute("DELETE FROM invites WHERE digest=?", (row["digest"],))
    return {"ok": True}


def keys(db,user,data=None):
    signed_in(user)
    uid = user["id"]
    if data is None:
        return {"items":[dict(r) for r in db.execute("SELECT prefix,label,created FROM access_keys WHERE uid=? ORDER BY created DESC",(uid,))]}
    if data.get("remove"):
        db.execute("DELETE FROM access_keys WHERE uid=? AND prefix=?", (uid,ident(data.get("prefix"))))
        return {"ok":True}
    key = "tf_"+secrets.token_urlsafe(32)
    db.execute("INSERT INTO access_keys VALUES(?,?,?,?,?)",(digest(key),key[:14],ident(data.get("label") or "研究 API",48),uid,now()))
    return {"key":key}


def check_source(db, user, source):
    if not analytics.source_policy.visible(db,workspace(user),source):
        raise RequestError(403,"此数据源属于其他工作区")


def ranking_presets(db,user,data,write=False):
    owner = workspace(user)
    kind = data.get("kind") or "products"
    if kind not in analytics.KINDS: raise ValueError("对象类型无效")
    if write:
        name = ident(data.get("name"),60)
        if data.get("remove"):
            db.execute("DELETE FROM ranking_presets WHERE owner=? AND kind=? AND name=?",(owner,kind,name))
        else:
            raw = data.get("params")
            if not isinstance(raw,dict): raise ValueError("缺少筛选参数")
            params = {k:str(raw[k]) for k in analytics.RANKING_KEYS if k!="kind" and raw.get(k) not in (None,"")}
            if any(len(v)>256 for v in params.values()): raise ValueError("筛选参数过长")
            check_source(db,user,params.get("source","demo"))
            analytics.scope_for(db,params)
            analytics.ranking_filter(kind,params)
            db.execute("""INSERT INTO ranking_presets VALUES(?,?,?,?) ON CONFLICT(owner,kind,name)
                          DO UPDATE SET params=excluded.params""",(owner,kind,name,json.dumps(params,ensure_ascii=False)))
    return {"items":[{"name":r[0],"params":json.loads(r[1])} for r in db.execute(
        f"SELECT name,params FROM ranking_presets WHERE owner=? AND kind=? AND COALESCE(json_extract(params,'$.source'),'demo') IN ({analytics.source_policy.VISIBLE}) ORDER BY name",(owner,kind,owner))]}


def save_topic(db,user,data):
    source=ident(data.get("source","demo"),120)
    check_source(db,user,source)
    scope=analytics.scope_for(db,{**data,"source":source})
    group=data.get("group")
    topic=ident(data.get("topic"),512)
    if group not in ("tag","music","keyword","script"):
        raise ValueError("不支持的灵感类型")
    values=(workspace(user),source,scope["market"],scope["date"],scope["days"],group,topic)
    if data.get("remove"):
        db.execute("DELETE FROM saved_topics WHERE (owner,source,market,day,days,grouping,topic)=(?,?,?,?,?,?,?)",values)
    else:
        # The grouping is selected from the closed list above.
        found=db.execute(f"""SELECT 1 FROM analytics_daily WHERE kind='videos' AND source=?
            AND market=? AND date BETWEEN ? AND ? AND {group}=? LIMIT 1""",
            (source,scope["market"],scope["start_date"],scope["date"],topic)).fetchone()
        if not found: raise LookupError("所选窗口没有该灵感")
        db.execute("INSERT OR IGNORE INTO saved_topics VALUES(?,?,?,?,?,?,?)",values)
    return {"ok":True}


def list_items(db,user,kind):
    owner = workspace(user)
    visible=analytics.source_policy.VISIBLE
    if kind == "favorites":
        return {"items":[dict(r) for r in db.execute(f"SELECT * FROM favorites WHERE owner=? AND source IN ({visible}) ORDER BY created DESC,id",(owner,owner))],
                "topics":[dict(r) for r in db.execute(f'SELECT source,market,day AS date,days,grouping AS "group",topic FROM saved_topics WHERE owner=? AND source IN ({visible}) ORDER BY day DESC,topic',(owner,owner))]}
    limits=monitor_capacity.reconcile(db,owner)
    rows = db.execute(f"SELECT * FROM monitors WHERE owner=? AND source IN ({visible}) ORDER BY mid DESC",(owner,owner))
    items = []
    for row in rows:
        readings = [dict(r) for r in db.execute("SELECT day,value,hit FROM readings WHERE mid=? ORDER BY day DESC LIMIT 30",(row["mid"],))]
        latest=db.execute("SELECT MAX(date) FROM analytics_daily WHERE source=? AND market=?",
                          (row["source"],row["market"])).fetchone()[0]
        lag=(analytics.iso_day(latest)-analytics.iso_day(readings[0]["day"])).days if latest and readings else None
        items.append({**dict(row), "readings":readings,"source_latest":latest,"observation_lag_days":lag})
    return {"items":items,"limit":limits["limit"],"capacity":limits,"can_request":bool(user["email"] and not user["owner"])}


def mutate_list(db,user,kind,data):
    owner = workspace(user)
    if not db.in_transaction:
        db.execute("BEGIN IMMEDIATE")
    limits = monitor_capacity.reconcile(db,owner) if kind=="monitors" else {}
    def require_slot():
        n = db.execute("SELECT count(*) FROM monitors WHERE owner=? AND status='active'", (owner,)).fetchone()[0]
        if n >= limits["limit"]:
            raise RequestError(429,"工作区监控额度已用完")
    def monitor_threshold():
        value=data.get("threshold")
        if value is None: return None
        value=float(value)
        if not 0 <= value < 1e18: raise ValueError("阈值应为非负有限值")
        return value
    if kind == "monitors" and data.get("mid"):
        mid = int(data["mid"])
        selected=db.execute("SELECT source FROM monitors WHERE owner=? AND mid=?",(owner,mid)).fetchone()
        if not selected: raise LookupError("未找到监控")
        check_source(db,user,selected[0])
        if data.get("remove"):
            import recycle
            row=db.execute("SELECT * FROM monitors WHERE owner=? AND mid=?",(owner,mid)).fetchone()
            recycle.keep(db,owner,"monitor",row,db.execute("SELECT * FROM readings WHERE mid=?",(mid,)))
            db.execute("DELETE FROM monitors WHERE owner=? AND mid=?",(owner,mid))
        elif "threshold" in data and "status" not in data:
            updated=db.execute("UPDATE monitors SET threshold=? WHERE owner=? AND mid=?",(monitor_threshold(),owner,mid))
            if not updated.rowcount: raise LookupError("未找到监控任务")
        else:
            status = data.get("status")
            if status not in ("active","completed"): raise ValueError("无效监控状态")
            previous = db.execute("SELECT status FROM monitors WHERE owner=? AND mid=?",(owner,mid)).fetchone()
            if not previous: raise LookupError("未找到监控任务")
            if status=="active" and previous[0]!="active": require_slot()
            db.execute("UPDATE monitors SET status=?,capacity_ended=NULL WHERE owner=? AND mid=?",(status,owner,mid))
        return {"ok":True}
    market, source, domain, eid = [ident(data.get(k),160) for k in ("market","source","kind","id")]
    check_source(db,user,source)
    key = (owner,market,source,domain,eid)
    if kind == "favorites" and data.get("remove"):
        db.execute("DELETE FROM favorites WHERE owner=? AND market=? AND source=? AND kind=? AND id=?",key)
        return {"ok":True}
    if kind == "favorites":
        day=data.get("date") or db.execute("SELECT MAX(date) FROM analytics_daily WHERE market=? AND source=? AND kind=? AND id=?",key[1:]).fetchone()[0]
        scope=analytics.scope_for(db,{**data,"date":day})
        item=db.execute("""SELECT name FROM analytics_daily WHERE market=? AND source=? AND kind=? AND id=?
                           AND date BETWEEN ? AND ? ORDER BY date DESC LIMIT 1""",
                        (*key[1:],scope["start_date"],scope["date"])).fetchone()
        if not item: raise LookupError("当前市场和时间范围内没有此对象")
        db.execute("""INSERT INTO favorites(owner,market,source,kind,id,name,created,date,days)
          VALUES(?,?,?,?,?,?,?,?,?) ON CONFLICT(owner,market,source,kind,id)
          DO UPDATE SET name=excluded.name,date=excluded.date,days=excluded.days""",
          (*key,item["name"],now(),scope["date"],scope["days"]))
        return {"ok":True}
    item = db.execute("SELECT name FROM analytics_daily WHERE market=? AND source=? AND kind=? AND id=? ORDER BY date DESC LIMIT 1",key[1:]).fetchone()
    if not item: raise LookupError("当前数据源没有此对象")
    if domain not in ("products","videos","lives"):
        raise ValueError("可监控商品、视频和直播")
    metric = data.get("metric","sales")
    if metric not in ("gmv","sales","views"): raise ValueError("无效指标")
    threshold = monitor_threshold()
    existing = db.execute("SELECT status FROM monitors WHERE owner=? AND market=? AND source=? AND kind=? AND id=? AND metric=?",(*key,metric)).fetchone()
    if not existing or existing[0]!="active": require_slot()
    db.execute("""INSERT INTO monitors(mid,owner,market,source,kind,id,name,metric,threshold,status,created)
      VALUES((SELECT COALESCE(MAX(mid),0)+1 FROM (SELECT MAX(mid) AS mid FROM monitors UNION ALL SELECT MAX(mid) FROM alerts UNION ALL SELECT MAX(original_id) FROM deleted_items WHERE kind='monitor')),
             ?,?,?,?,?,?,?,?,'active',?) ON CONFLICT(owner,market,source,kind,id,metric)
      DO UPDATE SET status='active',threshold=excluded.threshold,capacity_ended=NULL""",(*key,item["name"],metric,threshold,now()))
    return {"ok":True}


def sample(db):
    for owner, in db.execute("SELECT DISTINCT owner FROM monitors WHERE status='active'").fetchall():
        monitor_capacity.reconcile(db,owner)
    for m in db.execute("SELECT * FROM monitors WHERE status='active'").fetchall():
        if not analytics.source_policy.visible(db,m["owner"],m["source"]): continue
        cols = {"sales":"sales","views":"views","gmv":"gmv_units / 100.0"}
        series = db.execute(f"SELECT date,{cols[m['metric']]} FROM analytics_daily WHERE market=? AND source=? AND kind=? AND id=? ORDER BY date DESC LIMIT 30",
                            (m["market"],m["source"],m["kind"],m["id"]))
        latest = db.execute("SELECT MAX(day) FROM readings WHERE mid=?", (m["mid"],)).fetchone()[0]
        for index,(stamp,value) in enumerate(series):
            if value is None: continue
            if m["threshold"] is not None and value >= m["threshold"] and ((latest is None and index == 0) or (latest is not None and stamp >= latest)):
                notifications.record(db,m,stamp,value)
            db.execute("""INSERT INTO readings VALUES(?,?,?,?) ON CONFLICT(mid,day)
              DO UPDATE SET value=excluded.value,hit=excluded.hit WHERE value!=excluded.value OR hit!=excluded.hit""",
              (m["mid"], stamp, value, int(m["threshold"] is not None and value>=m["threshold"])))

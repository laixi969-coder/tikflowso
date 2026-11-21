"""Persistent login throttling, RFC 6238 codes and one-use account recovery."""
import base64
import hashlib
import hmac
import secrets
import struct
import time
from pathlib import Path


def init(db):
    db.executescript("""
      CREATE TABLE IF NOT EXISTS login_attempts(bucket TEXT PRIMARY KEY, attempts INTEGER NOT NULL, since INTEGER NOT NULL);
      CREATE INDEX IF NOT EXISTS login_attempts_expire ON login_attempts(since);
      CREATE TABLE IF NOT EXISTS admin_factors(uid INTEGER PRIMARY KEY, secret TEXT NOT NULL, last_step INTEGER NOT NULL DEFAULT -1);
      CREATE TABLE IF NOT EXISTS factor_recovery(uid INTEGER NOT NULL, digest TEXT PRIMARY KEY);
      CREATE TABLE IF NOT EXISTS admin_handoff(uid INTEGER PRIMARY KEY,digest TEXT NOT NULL,expires INTEGER NOT NULL);
      CREATE TABLE IF NOT EXISTS password_resets(uid INTEGER PRIMARY KEY, digest TEXT UNIQUE NOT NULL, expires INTEGER NOT NULL);
    """)
    if "assured" not in {r[1] for r in db.execute("PRAGMA table_info(sessions)")}:
        db.execute("ALTER TABLE sessions ADD COLUMN assured INTEGER NOT NULL DEFAULT 0")


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def limit_attempt(db, email, peer):
    from workspace import RequestError
    stamp=int(time.time())
    cutoff=stamp-600
    db.execute("DELETE FROM login_attempts WHERE since<=?",(cutoff,))
    for tag,value,limit in (("ip",peer,50),("account",str(email).strip().casefold(),8)):
        key=digest(tag+":"+value)
        row=db.execute("SELECT attempts,since FROM login_attempts WHERE bucket=?",(key,)).fetchone()
        if row and row[0]>=limit:
            db.commit()
            raise RequestError(429,"尝试过于频繁，请稍后登录",max(1,row[1]+600-stamp))
        db.execute("""INSERT INTO login_attempts VALUES(?,1,?) ON CONFLICT(bucket)
                      DO UPDATE SET attempts=attempts+1""",(key,stamp))
    db.commit()


def successful(db,email,peer):
    db.execute("UPDATE login_attempts SET attempts=max(0,attempts-1) WHERE bucket=?",(digest('ip:'+peer),))
    db.execute("DELETE FROM login_attempts WHERE bucket=?",(digest("account:"+email.strip().casefold()),))


def provision(db, uid):
    secret=base64.b32encode(secrets.token_bytes(20)).decode().rstrip("=")
    recovery=[secrets.token_hex(8) for _ in range(8)]
    db.execute("INSERT OR REPLACE INTO admin_factors(uid,secret) VALUES(?,?)",(uid,secret))
    db.execute("DELETE FROM factor_recovery WHERE uid=?",(uid,))
    db.executemany("INSERT INTO factor_recovery VALUES(?,?)",[(uid,digest(c)) for c in recovery])
    db.execute("DELETE FROM sessions WHERE uid=?",(uid,))
    db.execute("DELETE FROM access_keys WHERE uid=?",(uid,))
    return {"secret":secret,"recovery_codes":recovery}


def totp(secret,step):
    key=base64.b32decode(secret+"="*(-len(secret)%8))
    sig=hmac.digest(key,struct.pack(">Q",step),"sha1")
    start=sig[-1]&15
    value=int.from_bytes(sig[start:start+4],"big")&0x7fffffff
    return f"{value%1000000:06d}"


def verify_factor(db,uid,code):
    from workspace import RequestError
    code=str(code or "").strip()
    row=db.execute("SELECT secret,last_step FROM admin_factors WHERE uid=?",(uid,)).fetchone()
    if row and len(code)==6 and code.isascii() and code.isdigit():
        now=int(time.time())//30
        for step in (now,now-1,now+1):
            if step>row[1] and hmac.compare_digest(totp(row[0],step),code):
                if db.execute("UPDATE admin_factors SET last_step=? WHERE uid=? AND last_step<?",(step,uid,step)).rowcount:
                    return
    if len(code)==16 and db.execute("DELETE FROM factor_recovery WHERE uid=? AND digest=?",(uid,digest(code.lower()))).rowcount:
        return
    raise RequestError(401,"需要有效的管理员动态码或一次性恢复码")


def reset_token(db,uid):
    token=secrets.token_urlsafe(32)
    db.execute("INSERT OR REPLACE INTO password_resets VALUES(?,?,?)",(uid,digest(token),int(time.time())+900))
    return token


def reset_password(db,token,password):
    import workspace as ws
    if not isinstance(password,str) or not 10<=len(password)<=200:
        raise ValueError("密码长度需为 10–200 个字符")
    row=db.execute("DELETE FROM password_resets WHERE digest=? AND expires>? RETURNING uid",
                   (digest(str(token)),ws.now())).fetchone()
    if not row: raise ValueError("找回凭证无效或已过期")
    salt=secrets.token_hex(16)
    db.execute("UPDATE users SET password=? WHERE id=?",(salt+"."+ws.derive(password,salt),row[0]))
    db.execute("DELETE FROM sessions WHERE uid=?",(row[0],))
    db.execute("DELETE FROM access_keys WHERE uid=?",(row[0],))


def private_file(path, data):
    import json
    import os
    with os.fdopen(os.open(Path(path),os.O_EXCL|os.O_CREAT|os.O_WRONLY,0o600),"w") as out:
        json.dump(data,out,ensure_ascii=False,indent=2)
        out.write("\n")


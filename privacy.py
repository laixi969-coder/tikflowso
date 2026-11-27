"""Minimize stored assistant text and apply verified account-erasure requests to restored copies."""
from contextlib import closing
import hashlib
import hmac
import os
from pathlib import Path
import re
import secrets
import sqlite3
import time

_CREDENTIAL = re.compile(r"(?i)\b(?:bearer\s+[a-z0-9._~+/=-]{12,}|(?:sk[-_](?:live_|test_|proj-)?|ghp_|github_pat_|whsec_|tfs_)[a-z0-9_-]{12,})")
_EMAIL = re.compile(r"(?<![\w.+-])[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}(?![\w.-])")


def scrub(value):
    if isinstance(value, str):
        return _EMAIL.sub("[email]", _CREDENTIAL.sub("[credential]",value))
    if isinstance(value,list): return [scrub(item) for item in value]
    if isinstance(value,dict): return {key:scrub(v) for key,v in value.items()}
    return value


def has(db, table):
    return db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",(table,)).fetchone() is not None


def erase(db, uid, email):
    # Keep a pseudonymous numeric subject for immutable charges and commission statements.
    def remove(table, condition, values):
        if has(db,table): db.execute("DELETE FROM "+table+" WHERE "+condition,values)

    one=(uid,)
    db.execute("CREATE TABLE IF NOT EXISTS erased_workspaces(uid INTEGER PRIMARY KEY)")
    db.execute("INSERT OR IGNORE INTO erased_workspaces VALUES(?)",one)
    remove("assistant_turns","chat IN (SELECT id FROM assistant_chats WHERE uid=? OR owner=?)",(uid,uid))
    remove("assistant_chats","uid=? OR owner=?",(uid,uid))
    remove("support_messages","uid=? OR ticket IN (SELECT id FROM support_cases WHERE uid=?)",(uid,uid))
    remove("support_cases","uid=?",one)
    remove("deliveries","aid IN (SELECT aid FROM alerts WHERE owner=?)",one)
    remove("readings","mid IN (SELECT mid FROM monitors WHERE owner=?)",one)
    remove("partner_files","id IN (SELECT id FROM partner_library WHERE owner=?)",one)
    if has(db,"partner_files") and "uploader" in {r[1] for r in db.execute("PRAGMA table_info(partner_files)")}:
        remove("partner_files","uploader=?",one)
    remove("export_jobs","owner=? OR uid=?",(uid,uid))
    remove("research_decisions","owner=? OR author=?",(uid,uid))
    for table in ("favorites","ranking_presets","saved_topics","creator_contacts","monitors","alerts","imports",
                  "api_minutes","partner_library","notification_preferences","research_permissions","research_runs",
                  "research_days","research_details","deleted_items","monitor_slot_requests"):
        remove(table,"owner=?",one)
    for table in ("sessions","access_keys","password_resets","admin_factors","factor_recovery","platform_admins",
                  "partner_codes","admin_handoff","usage"):
        remove(table,"uid=?",one)
    remove("invites","owner=? OR email=?",(uid,email))
    remove("access_audit","actor=? OR owner=?",(uid,uid))
    if has(db,"login_attempts"):
        remove("login_attempts","bucket=?",(hashlib.sha256(("account:"+email.casefold()).encode()).hexdigest(),))
    if has(db,"analytics_sources"):
        if has(db,"source_policy"):
            sources=[r[0] for r in db.execute("SELECT source FROM source_policy WHERE owner=?",one)]
        else:
            sources=[r[0] for r in db.execute("SELECT id FROM analytics_sources WHERE id GLOB ?",(f"ws-{uid}-*",))]
        for source in sources:
            for table in ("source_baselines","snapshot_revisions","stream_points","analytics_daily","analytics_entities","feed_contracts",
                          "feed_arrivals","feed_items","research_permissions","research_runs","research_details","research_decisions"):
                remove(table,"source=?",(source,))
            remove("analytics_sources","id=?",(source,))
            remove("source_policy","source=?",(source,))
    db.execute("UPDATE users SET owner=NULL WHERE owner=?",one)
    db.execute("UPDATE users SET name='已注销账户',email=NULL,password=NULL,owner=NULL,plan='free' WHERE id=?",one)


def fingerprint(key, uid, email):
    return hmac.digest(key,f"{uid}\n{email.strip().lower()}".encode(),"sha256").hex()


def open_journal(path, create=False):
    target=Path(path).expanduser().resolve()
    if create:
        target.parent.mkdir(mode=0o700,exist_ok=True,parents=True)
        fd=os.open(target,os.O_CREAT|os.O_WRONLY,0o600)
        os.close(fd)
    db=sqlite3.connect(target.as_uri()+("?mode=rw" if create else "?mode=ro"),uri=True)
    if create:
        db.execute("CREATE TABLE IF NOT EXISTS salt(id INTEGER PRIMARY KEY CHECK(id=1),key BLOB NOT NULL)")
        db.execute("CREATE TABLE IF NOT EXISTS removed(uid INTEGER NOT NULL,marker TEXT PRIMARY KEY,stamp INTEGER NOT NULL)")
        db.execute("INSERT OR IGNORE INTO salt VALUES(1,?)",(secrets.token_bytes(32),))
        db.commit()
    return db


def request(db, email, journal):
    email=email.strip().lower()
    db.execute("BEGIN IMMEDIATE")
    row=db.execute("SELECT id,plan FROM users WHERE email=?",(email,)).fetchone()
    if not row: raise ValueError("未找到该账户")
    uid,plan=row
    if (plan!="free" or db.execute("SELECT 1 FROM users WHERE owner=?",(uid,)).fetchone()
        or db.execute("SELECT 1 FROM platform_admins WHERE uid=? AND (SELECT COUNT(*) FROM platform_admins)=1",(uid,)).fetchone()):
        raise ValueError("请先完成订阅、团队成员和最后一位平台管理员交接")
    with closing(open_journal(journal,True)) as record,record:
        key=record.execute("SELECT key FROM salt WHERE id=1").fetchone()[0]
        record.execute("INSERT OR IGNORE INTO removed VALUES(?,?,?)",(uid,fingerprint(key,uid,email),int(time.time())))
    erase(db,uid,email)


def replay(db, journal):
    count=0
    with closing(open_journal(journal)) as record:
        key=record.execute("SELECT key FROM salt WHERE id=1").fetchone()[0]
        for uid,marker in record.execute("SELECT uid,marker FROM removed"):
            row=db.execute("SELECT email FROM users WHERE id=?",(uid,)).fetchone()
            if row and row[0] and hmac.compare_digest(marker,fingerprint(key,uid,row[0])):
                erase(db,uid,row[0])
                count+=1
    return count


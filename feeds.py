"""Sync licensed daily snapshot deliveries into tikflowso.

Set TIKFLOWSO_FEEDS to a UTF-8 JSON config path, or run with --config. The
file is an array of feeds. Each feed requires id, source, and either directory
or an HTTPS url. An optional token_env names the bearer-token environment
variable. Set owner to bind a source to one workspace, or shared=true to publish it.
Unclassified feeds are held. Only enable licensed sources.
"""
import argparse
import csv
from datetime import datetime, timedelta, timezone
import hashlib
from io import StringIO
import json
import os
from pathlib import Path
import re
import sqlite3
import time
import uuid
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import build_opener, HTTPRedirectHandler, Request

import analytics

MAX_BYTES = 32 * 1024 * 1024


class SameOriginRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        old, new = urlsplit(req.full_url), urlsplit(newurl)
        if (new.scheme != "https" or new.username is not None or new.password is not None or
                (old.hostname,old.port or 443) != (new.hostname,new.port or 443)):
            raise ValueError("授权下载拒绝跨源重定向")
        return super().redirect_request(req,fp,code,msg,headers,newurl)


def valid_config(raw):
    if not isinstance(raw, list):
        raise ValueError("feed 配置须为数组")
    seen = set()
    for item in raw:
        if not isinstance(item,dict):
            raise ValueError("每个 feed 须为对象")
        for name in ("id", "source"):
            if not isinstance(item.get(name),str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}",item[name]):
                raise ValueError(f"feed {name} 须为 1–64 个英数、短横线或下划线")
        analytics.source_policy.intent(item["source"],item.get("owner"),item.get("shared",False))
        if item["id"] in seen or item["source"].lower() == "demo":
            raise ValueError("feed id 不可重复，demo 来源保留")
        seen.add(item["id"])
        if bool(item.get("directory")) == bool(item.get("url")):
            raise ValueError("每个 feed 需选择 directory 或 url")
        if item.get("url"):
            if not isinstance(item["url"],str):
                raise ValueError("feed URL 格式无效")
            url = urlsplit(item["url"])
            if url.scheme != "https" or not url.hostname or url.username or url.password:
                raise ValueError("远程 feed 须使用 HTTPS，令牌使用 token_env")
            if (item.get("format") or Path(url.path).suffix.lower()[1:]) not in ("csv","json"):
                raise ValueError("远程 feed 需声明 csv/json 格式")
        elif not isinstance(item["directory"],str) or not Path(item["directory"]).is_absolute():
            raise ValueError("directory 须为绝对路径")
        if "token_env" in item and (not isinstance(item["token_env"],str) or
                                    not re.fullmatch(r"[a-zA-Z_][a-zA-Z_0-9]*",item["token_env"])):
            raise ValueError("token_env 须为环境变量名")
        interval = item.get("interval_seconds",900)
        if isinstance(interval,bool) or not isinstance(interval,int) or interval < 1:
            raise ValueError("interval_seconds 须为正整数秒")
        delivery=item.get("daily_delivery")
        if delivery is not None:
            if not isinstance(delivery,dict) or not isinstance(delivery.get("markets"),list) or not delivery["markets"] or any(
                not isinstance(m,str) or m not in analytics.MARKETS for m in delivery["markets"]
            ) or not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d",str(delivery.get("due_utc",""))) or (
                type(delivery.get("lag_days")) is not int or not 0<=delivery["lag_days"]<=366):
                raise ValueError("daily_delivery 需提供 markets、UTC HH:MM 截止时间 due_utc 和 0–366 天的 lag_days")
    return raw


def schema(db):
    db.execute("""CREATE TABLE IF NOT EXISTS feed_items(
        feed TEXT NOT NULL,source TEXT NOT NULL,location TEXT NOT NULL,
        digest TEXT NOT NULL,rows INTEGER NOT NULL,checked_at INTEGER NOT NULL,
        PRIMARY KEY(feed,source,location))""")
    if "arrivals_logged" not in {r[1] for r in db.execute("PRAGMA table_info(feed_items)")}:
        db.execute("ALTER TABLE feed_items ADD COLUMN arrivals_logged INTEGER NOT NULL DEFAULT 0")
    db.execute("""CREATE TABLE IF NOT EXISTS feed_leases(
        feed TEXT PRIMARY KEY,owner TEXT NOT NULL,expires INTEGER NOT NULL)""")
    db.execute("""CREATE TABLE IF NOT EXISTS feed_runs(
        feed TEXT PRIMARY KEY, checked_at INTEGER NOT NULL,status TEXT NOT NULL,message TEXT NOT NULL)""")
    db.execute("""CREATE TABLE IF NOT EXISTS feed_contracts(
        feed TEXT NOT NULL,source TEXT NOT NULL,market TEXT NOT NULL,due TEXT NOT NULL,
        lag INTEGER NOT NULL,started INTEGER NOT NULL,PRIMARY KEY(feed,source,market))""")
    db.execute("""CREATE TABLE IF NOT EXISTS feed_arrivals(
        feed TEXT NOT NULL,source TEXT NOT NULL,market TEXT NOT NULL,day TEXT NOT NULL,received INTEGER NOT NULL,
        PRIMARY KEY(feed,source,market,day))""")


def update_contracts(db,specs,moment):
    active={(s["id"],s["source"],m):(d["due_utc"],d["lag_days"])
            for s in specs if (d:=s.get("daily_delivery")) for m in d["markets"]}
    with db:
        for spec in specs:
            analytics.source_policy.register(db,spec["source"],spec.get("owner"),spec.get("shared",False))
        for row in db.execute("SELECT feed,source,market FROM feed_contracts").fetchall():
            if tuple(row) not in active:
                db.execute("DELETE FROM feed_contracts WHERE feed=? AND source=? AND market=?",tuple(row))
        for key,(due,lag) in active.items():
            db.execute("""INSERT INTO feed_contracts VALUES(?,?,?,?,?,?) ON CONFLICT(feed,source,market) DO UPDATE
                SET due=excluded.due,lag=excluded.lag,started=excluded.started
                WHERE due!=excluded.due OR lag!=excluded.lag""",(*key,due,lag,moment))


def delivery_health(db,owner,moment=None):
    now=datetime.fromtimestamp(time.time() if moment is None else moment,timezone.utc)
    result=[]
    for feed,source,market,due,lag,started in db.execute(f"""SELECT * FROM feed_contracts
        WHERE source IN ({analytics.source_policy.VISIBLE}) ORDER BY feed,market""",(owner,)):
        hour,minute=map(int,due.split(":"))
        end=now.replace(hour=hour,minute=minute,second=0,microsecond=0)
        if end>now:end-=timedelta(days=1)
        history=[]
        for n in range(7):
            deadline=end-timedelta(days=n)
            if deadline.timestamp()<started:break
            day=(deadline.date()-timedelta(days=lag)).isoformat()
            row=db.execute("SELECT received FROM feed_arrivals WHERE feed=? AND source=? AND market=? AND day=?",
                           (feed,source,market,day)).fetchone()
            received=row[0] if row else None
            history.append({"day":day,"due":deadline.isoformat(),"received":received,
                            "status":"missing" if received is None else "on_time" if received<=deadline.timestamp() else "late"})
        result.append({"feed":feed,"source":source,"market":market,"due_utc":due,"lag_days":lag,"history":history,
                       "on_time":sum(h["status"]=="on_time" for h in history),"expected":len(history)})
    return result


def claim(db, spec, force, moment):
    """A crashed poller relinquishes its claim after a bounded lease."""
    token = uuid.uuid4().hex
    db.execute("BEGIN IMMEDIATE")
    try:
        last = db.execute("SELECT checked_at FROM feed_runs WHERE feed=?",(spec["id"],)).fetchone()
        if not force and last and moment-last[0] < spec.get("interval_seconds",900):
            return None
        changed = db.execute("""INSERT INTO feed_leases VALUES(?,?,?)
          ON CONFLICT(feed) DO UPDATE SET owner=excluded.owner,expires=excluded.expires
          WHERE expires<=?""",(spec["id"],token,moment+180,moment)).rowcount
        return token if changed else None
    finally:
        db.commit()


def bounded_read(stream):
    data = stream.read(MAX_BYTES+1)
    if len(data)>MAX_BYTES:
        raise ValueError("单次快照超过 32 MiB")
    return data


def download(spec):
    headers = {"Accept":"application/json,text/csv"}
    if spec.get("token_env"):
        token = os.environ.get(spec["token_env"])
        if not token:
            raise ValueError("授权来源的令牌环境变量为空")
        headers["Authorization"] = "Bearer "+token
    req = Request(spec["url"],headers=headers)
    with build_opener(SameOriginRedirects()).open(req,timeout=20) as response:
        return bounded_read(response)


def parse(data, fmt):
    try: raw=data.decode("utf-8-sig")
    except UnicodeDecodeError:
        if fmt!="csv": raise
        raw=data.decode("gb18030")
    if fmt == "csv":
        return csv.DictReader(StringIO(raw,newline=""),strict=True)
    if fmt == "json":
        values = json.loads(raw)
        if isinstance(values,list):
            return values
    raise ValueError("JSON 须为记录数组，CSV 须含列名")


def ingest(db, spec, location, data, fmt, owner):
    digest = hashlib.sha256(data).hexdigest()
    key = (spec["id"],spec["source"],location)
    # Synchronize digest comparison, data revision, and checkpoint across scheduler processes.
    db.execute("BEGIN IMMEDIATE")
    try:
        if not db.execute("UPDATE feed_leases SET expires=? WHERE feed=? AND owner=?",
                          (int(time.time())+180,spec["id"],owner)).rowcount:
            raise RuntimeError("feed 运行租约已移交")
        last = db.execute("SELECT digest,checked_at,arrivals_logged FROM feed_items WHERE feed=? AND source=? AND location=?",key).fetchone()
        unchanged=last and last[0]==digest
        if unchanged and last[2]:
            db.commit()
            return 0
        observed=set()
        def records():
            for row in parse(data,fmt):
                yield row
                observed.add((row["market"].strip().upper(),row["date"]))
        if unchanged:
            for _ in records(): pass  # Previously validated file, backfill its original receipt.
            received=last[1]
            db.execute("UPDATE feed_items SET arrivals_logged=1 WHERE feed=? AND source=? AND location=?",key)
            rows=0
        else:
            rows=analytics.import_rows(db,records(),spec["source"],owner=spec.get("owner"),shared=spec.get("shared",False))["rows"]
            received=int(time.time())
            db.execute("""INSERT INTO feed_items(feed,source,location,digest,rows,checked_at,arrivals_logged) VALUES(?,?,?,?,?,?,1)
                ON CONFLICT(feed,source,location) DO UPDATE SET digest=excluded.digest,rows=excluded.rows,
                checked_at=excluded.checked_at,arrivals_logged=1""",(*key,digest,rows,received))
        db.executemany("""INSERT INTO feed_arrivals VALUES(?,?,?,?,?) ON CONFLICT(feed,source,market,day)
                       DO UPDATE SET received=MIN(received,excluded.received)""",
                       ((*key[:2],market,day,received) for market,day in observed))
        db.commit()
        return rows
    except BaseException:
        db.rollback()
        raise


def pull(db, spec, owner):
    imported = 0
    errors = []
    if spec.get("url"):
        fmt = spec.get("format") or Path(urlsplit(spec["url"]).path).suffix.lower()[1:]
        # Only a hash of the configured URL is persisted; signed query values stay out of logs.
        location = hashlib.sha256(spec["url"].encode()).hexdigest()
        return ingest(db,spec,location,download(spec),fmt,owner),errors
    directory = Path(spec["directory"])
    for file in sorted(directory.iterdir()):
        if file.name.startswith(".") or not file.is_file() or file.suffix.lower() not in (".json",".csv"):
            continue
        try:
            with file.open("rb") as stream:
                data = bounded_read(stream)
            imported += ingest(db,spec,str(file),data,file.suffix.lower()[1:],owner)
        except (ValueError,OSError,sqlite3.Error,csv.Error) as exc:
            errors.append(f"{file.name}：{safe_error(exc)}")
    return imported,errors


def safe_error(error):
    if isinstance(error,HTTPError):
        return f"数据提供方返回 HTTP {error.code}"
    if isinstance(error,(URLError,TimeoutError)):
        return "授权来源连接失败或超时"
    if isinstance(error,OSError):
        return "无法读取授权来源，请检查目录和网络连接"
    return str(error)[:400]


def sync_configured(db, force=False, config_path=None):
    """Call with a connection free of open transactions. Returns a per-feed status list."""
    path = config_path or os.environ.get("TIKFLOWSO_FEEDS")
    if not path:
        return []
    if db.in_transaction:
        raise RuntimeError("feed 同步需要独立的数据库连接或已提交的事务")
    feeds = valid_config(json.loads(Path(path).read_text(encoding="utf-8-sig")))
    schema(db)
    update_contracts(db,feeds,int(time.time()))
    result = []
    for spec in feeds:
        moment = int(time.time())
        owner = claim(db,spec,force,moment)
        if not owner:
            continue
        try:
            rows,errors = pull(db,spec,owner)
            status = "error" if errors else "ok"
            message = f"导入 {rows} 条日快照"
            if errors:
                message += "；" + "；".join(errors[:5])
        except (ValueError,OSError,sqlite3.Error,csv.Error,RuntimeError) as exc:
            rows,status,message = 0,"error",safe_error(exc)
        with db:
            if not db.execute("DELETE FROM feed_leases WHERE feed=? AND owner=?",(spec["id"],owner)).rowcount:
                continue
            db.execute("""INSERT INTO feed_runs VALUES (?,?,?,?) ON CONFLICT(feed) DO UPDATE
              SET checked_at=excluded.checked_at,status=excluded.status,message=excluded.message""",
              (spec["id"],moment,status,message))
        result.append({"feed":spec["id"],"source":spec["source"],"status":status,"rows":rows,"message":message})
    return result


def main():
    import settings
    settings.load()
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--db",type=Path,required=True)
    p.add_argument("--config",type=Path,default=os.environ.get("TIKFLOWSO_FEEDS"))
    args = p.parse_args()
    if not args.config:
        p.error("需要 --config 或 TIKFLOWSO_FEEDS")
    try:
        with sqlite3.connect(args.db,timeout=30) as db:
            analytics.init(db)
            result = sync_configured(db,force=True,config_path=args.config)
        print(json.dumps(result,ensure_ascii=False,indent=2))
        raise SystemExit(int(any(r["status"]=="error" for r in result)))
    except (ValueError,OSError,sqlite3.Error) as exc:
        p.exit(1,safe_error(exc)+"\n")


if __name__ == "__main__":
    main()

"""Optional push ingestion for a licensed minute-level monitoring provider."""
from datetime import datetime, timezone
import hmac
import math
import os
import sqlite3

from workspace import RequestError, ident

METRICS = {"online_viewers","sales","gmv","views"}


def init(db):
    db.executescript("""
      CREATE TABLE IF NOT EXISTS stream_points(
        source TEXT NOT NULL, market TEXT NOT NULL, kind TEXT NOT NULL, id TEXT NOT NULL,
        stamp TEXT NOT NULL, metric TEXT NOT NULL, value REAL NOT NULL,
        PRIMARY KEY(source,market,kind,id,stamp,metric)
      ) WITHOUT ROWID;
    """)


def ingest(db,token,body):
    secret=os.getenv("TIKFLOWSO_STREAM_TOKEN","")
    source=os.getenv("TIKFLOWSO_STREAM_SOURCE","")
    if not secret or not source or source=="demo":
        raise RequestError(503,"监控数据接收端尚未配置")
    if not hmac.compare_digest(secret.encode(),token.encode()):
        raise RequestError(401,"接入令牌无效")
    points=body.get("points")
    if not isinstance(points,list) or not 1<=len(points)<=5000:
        raise ValueError("每批可接收 1–5000 条监控数据")
    values=[]
    for point in points:
        if not isinstance(point,dict): raise ValueError("每个测量点必须为对象")
        market,kind,eid,metric=[ident(point.get(k),160) for k in ("market","kind","id","metric")]
        if kind not in ("products","videos","lives") or metric not in METRICS or metric=="online_viewers" and kind!="lives":
            raise ValueError("对象类型或监控指标无效")
        ts=datetime.fromisoformat(ident(point.get("time"),40).replace("Z","+00:00"))
        if ts.tzinfo is None: raise ValueError("请提供含时区的时间戳")
        ts=ts.astimezone(timezone.utc)
        if not 2000<=ts.year<=2200: raise ValueError("时间范围无效")
        v=point.get("value")
        if type(v) not in (int,float) or not math.isfinite(v) or not 0<=v<=1e15:
            raise ValueError("监控值必须为有效非负数")
        if metric!="gmv" and v!=int(v): raise ValueError("计数指标须为整数")
        values.append((source,market,kind,eid,ts.isoformat(timespec="microseconds"),metric,v))
    if not db.in_transaction: db.execute("BEGIN IMMEDIATE")
    for key in {v[:4] for v in values}:
        if not db.execute("SELECT 1 FROM analytics_entities WHERE source=? AND market=? AND kind=? AND id=?",key).fetchone():
            raise ValueError("该来源缺少对应的对象快照，请先导入对象")
    db.executemany("""INSERT INTO stream_points VALUES(?,?,?,?,?,?,?) ON CONFLICT(source,market,kind,id,stamp,metric)
                      DO UPDATE SET value=excluded.value""",values)
    return {"accepted":len(values),"source":source}


def recent(db,monitor):
    """Latest observations; each cumulative value belongs to its own entity/series."""
    return [dict(r) for r in db.execute("""SELECT stamp,metric,value FROM stream_points
               WHERE source=? AND market=? AND kind=? AND id=? ORDER BY stamp DESC,metric LIMIT 60""",
               tuple(monitor[k] for k in ("source","market","kind","id")))]

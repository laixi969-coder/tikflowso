"""Immutable product research decisions with comparable, source-scoped evidence."""
from datetime import date, timedelta
from hashlib import sha256
import json

import analytics
import research_usage
import workspace as ws


def init(db):
    db.executescript("""
        CREATE TABLE IF NOT EXISTS research_decisions (
          id INTEGER PRIMARY KEY, owner INTEGER NOT NULL, author INTEGER NOT NULL,
          request_key TEXT NOT NULL, source TEXT NOT NULL, created INTEGER NOT NULL,
          reason TEXT NOT NULL, evidence TEXT NOT NULL, UNIQUE(owner,author,request_key)
        );
        CREATE INDEX IF NOT EXISTS decisions_by_workspace ON research_decisions(owner,id);
    """)


def totals(rows):
    if not rows:
        return {"covered_days": 0, "sales": None, "gmv": None, "avg_price": None, "estimated": None}
    units = sum(row["sales"] for row in rows)
    amount = sum(row["gmv_units"] for row in rows)
    flags = {row["gmv_estimated"] for row in rows}
    estimated = True if 1 in flags else (None if None in flags else False)
    return {"covered_days": len(rows), "sales": units, "sales_exact":str(units), "gmv": analytics.money_text(amount),
            "avg_price": analytics.money_text(analytics.average_cents(amount, units)) if units else None, "estimated": estimated}


def evidence(db, scope, product, related=None):
    rows = db.execute("""SELECT date,name,sales,gmv_units,gmv_estimated FROM analytics_daily
        WHERE source=:source AND market=:market AND kind='products' AND id=:id
        AND date BETWEEN :prev_date AND :date ORDER BY date""", {**scope, "id": product}).fetchall()
    current = [row for row in rows if row["date"] >= scope["start_date"]]
    if not current:
        raise LookupError("当前市场和时间范围内没有此商品")
    previous = [row for row in rows if row["date"] < scope["start_date"]]
    if related is None:
        links = analytics.product_video_links(db, scope, "products", product)
    else:
        links = sorted((row for row in related if row["kind"] == "videos"),
                       key=lambda r: (-analytics.iso_day(r["last_seen"]).toordinal(), -r["linked_days"], r["id"]))
    snapshot = {key: scope[key] for key in ("source","market","date","start_date","days","currency","prev_date")}
    snapshot.update(product=product, name=current[-1]["name"],
                    previous_end=(date.fromisoformat(scope["start_date"])-timedelta(days=1)).isoformat(),
                    current=totals(current), previous=totals(previous), video_count=len(links),
                    daily=[{"date":r["date"],"sales":r["sales"],"gmv":analytics.money_text(r["gmv_units"]),
                            "estimated":r["gmv_estimated"]} for r in rows],
                    videos=[{k: row[k] for k in ("id","name","linked_days","first_seen","last_seen")}
                            for row in links[:5]])
    snapshot["version"] = sha256(json.dumps(snapshot, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    return snapshot


def save(db, user, data):
    source = ws.ident(data.get("source"), 160)
    product = ws.ident(data.get("product"), 160)
    request_key = ws.ident(data.get("request_key"), 100)
    reason = ws.ident(data.get("reason"), 1200)
    version = ws.ident(data.get("version"), 64)
    owner = ws.workspace(user)
    if not db.in_transaction:
        db.execute("BEGIN IMMEDIATE")
    ws.check_source(db, user, source)
    scope = analytics.scope_for(db, {**data, "source":source})
    old = db.execute("""SELECT id,reason,evidence FROM research_decisions
        WHERE owner=? AND author=? AND request_key=?""", (owner,user["id"],request_key)).fetchone()
    if old:
        stored = json.loads(old["evidence"])
        if (stored["version"] != version or old["reason"] != reason or stored["product"] != product
                or any(stored[k] != scope[k] for k in ("source","market","date","days"))):
            raise ws.RequestError(409, "这次保存已用于另一条判断")
        return {"id": old["id"]}
    snapshot = evidence(db, scope, product)
    if snapshot["version"] != version:
        raise ws.RequestError(409, "数据已修订，请刷新商品详情并核对后再保存")
    row = db.execute("""INSERT INTO research_decisions(owner,author,request_key,source,created,reason,evidence)
        VALUES(?,?,?,?,?,?,?)""", (owner,user["id"],request_key,source,ws.now(),reason,
                                  json.dumps(snapshot,ensure_ascii=False)))
    research_usage.record(db, owner, scope, "save", product)
    return {"id": row.lastrowid}


def read(db, user, params):
    owner = ws.workspace(user)
    allowed = f"owner=? AND source IN ({analytics.source_policy.VISIBLE})"
    if not db.in_transaction:
        db.execute("BEGIN")
    if "id" in params:
        decision = analytics.int_param(params, "id", 1, 2**63-1)
        row = db.execute(f"SELECT id,created,reason,evidence FROM research_decisions WHERE {allowed} AND id=?",
                         (owner,owner,decision)).fetchone()
        if not row:
            raise LookupError("未找到选品判断")
        stored = json.loads(row["evidence"])
        if params.get("saved") == "1":
            return {**dict(row), "evidence":stored}
        try:
            latest = evidence(db, analytics.scope_for(db,stored), stored["product"])
        except LookupError:
            latest = None
        return {"current": latest, "changed": not latest or latest["version"] != stored["version"]}
    before = analytics.int_param(params, "before", 2**63-1, 2**63-1)
    rows = db.execute(f"""SELECT id,created,reason,evidence FROM research_decisions
        WHERE {allowed} AND id<? ORDER BY id DESC LIMIT 21""", (owner,owner,before)).fetchall()
    return {"items": [{**dict(r), "evidence": json.loads(r["evidence"])} for r in rows[:20]],
            "next": rows[19]["id"] if len(rows)>20 else None}

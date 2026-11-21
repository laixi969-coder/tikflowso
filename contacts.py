"""Workspace-owned creator contact records explicitly supplied by an operator."""
import csv
import io
from urllib.parse import urlsplit

import workspace as ws


def init(db):
    db.execute("""CREATE TABLE IF NOT EXISTS creator_contacts(
      owner INTEGER NOT NULL, source TEXT NOT NULL,market TEXT NOT NULL,id TEXT NOT NULL,
      email TEXT NOT NULL, channel TEXT NOT NULL,rights TEXT NOT NULL, updated INTEGER NOT NULL,
      PRIMARY KEY(owner,source,market,id)) WITHOUT ROWID""")


def catalog(db,user,params):
    ws.signed_in(user)
    source,market=params.get("source","demo"),params.get("market","US")
    ws.check_source(user,source)
    query=params.get("q","").strip().lower()
    sql="""SELECT c.*, (SELECT name FROM analytics_daily d WHERE d.source=c.source AND d.market=c.market
      AND d.id=c.id AND d.kind='creators' ORDER BY date DESC LIMIT 1) AS name
      FROM creator_contacts c WHERE owner=? AND c.source=? AND c.market=?"""
    rows=[dict(r) for r in db.execute(sql+" ORDER BY updated DESC,id",(ws.workspace(user),source,market))]
    return [r for r in rows if (not params.get("id") or r["id"]==params["id"])
            and (not query or any(query in str(r[k]).lower() for k in ("name","id","email","channel")))]


def mutate(db,user,data):
    ws.admin(user)
    source=ws.ident(data.get("source"),64)
    market=ws.ident(data.get("market"),5)
    ws.check_source(user,source)
    owner=ws.workspace(user)
    if data.get("remove"):
        db.execute("DELETE FROM creator_contacts WHERE owner=? AND source=? AND market=? AND id=?",(owner,source,market,ws.ident(data.get("id"),160)))
        return {"ok":True}
    rows=data.get("rows")
    if "csv" in data: rows=list(csv.DictReader(io.StringIO(ws.ident(data["csv"],4000000).lstrip("\ufeff"))))
    if not isinstance(rows,list) or not 1<=len(rows)<=5000: raise ValueError("联系簿每批支持 1–5000 行")
    for i,row in enumerate(rows,1):
        if not isinstance(row,dict): raise ValueError(f"第 {i} 行格式无效")
        eid=ws.ident(row.get("id"),160)
        email=ws.email_value(row["email"]) if row.get("email") else ""
        channel=ws.ident(row["channel"],600) if row.get("channel") else ""
        if channel and urlsplit(channel).scheme!="https": raise ValueError(f"第 {i} 行合作渠道须为 HTTPS 地址")
        if not email and not channel: raise ValueError(f"第 {i} 行请填写授权邮箱或渠道")
        rights=ws.ident(row.get("rights"),600)
        if not db.execute("SELECT 1 FROM analytics_entities WHERE source=? AND market=? AND kind='creators' AND id=?",(source,market,eid)).fetchone():
            raise ValueError(f"第 {i} 行在当前来源和市场中缺少对应的达人")
        db.execute("""INSERT INTO creator_contacts VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(owner,source,market,id)
          DO UPDATE SET email=excluded.email,channel=excluded.channel,rights=excluded.rights,updated=excluded.updated""",
          (owner,source,market,eid,email,channel,rights,ws.now()))
    return {"rows":len(rows)}

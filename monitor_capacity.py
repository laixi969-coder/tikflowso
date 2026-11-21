"""Platform-reviewed monthly monitoring capacity. The decision row is the grant."""
import re

import workspace as ws


def init(db):
    db.executescript("""
        CREATE TABLE IF NOT EXISTS monitor_slot_requests(
            id INTEGER PRIMARY KEY, owner INTEGER NOT NULL REFERENCES users(id),
            period TEXT NOT NULL, slots INTEGER NOT NULL CHECK(slots>0),
            reason TEXT NOT NULL, nonce TEXT NOT NULL, created INTEGER NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','approved','rejected')),
            reviewer INTEGER REFERENCES users(id), decided INTEGER, note TEXT,
            UNIQUE(owner,nonce));
        CREATE INDEX IF NOT EXISTS monitor_grants ON monitor_slot_requests(owner,period,status);
    """)


def capacity(db,owner,month=None):
    month=month or ws.period()
    base=ws.LIMITS[ws.get_user(db,owner)["plan"]]["monitors"]
    added=db.execute("""SELECT COALESCE(SUM(slots),0) FROM monitor_slot_requests
                        WHERE owner=? AND period=? AND status='approved'""",(owner,month)).fetchone()[0]
    return {"base":base,"added":added,"limit":base+added,"period":month}


def reconcile(db,owner):
    """Retain the oldest active monitors when a grant expires or a plan shrinks."""
    limits=capacity(db,owner)
    active=db.execute("SELECT count(*) FROM monitors WHERE owner=? AND status='active'",(owner,)).fetchone()[0]
    if active>limits["limit"]:
        if not db.in_transaction:
            db.execute("BEGIN IMMEDIATE")
            limits=capacity(db,owner)
        db.execute("""UPDATE monitors SET status='completed',capacity_ended=? WHERE mid IN (
                      SELECT mid FROM monitors WHERE owner=? AND status='active'
                      ORDER BY created,mid LIMIT -1 OFFSET ?)""",(ws.now(),owner,limits["limit"]))
    return limits


def request(db,user,data):
    ws.admin(user)
    raw=str(data.get("slots",""))
    if not re.fullmatch(r"[1-9][0-9]{0,5}",raw):
        raise ValueError("申请数量须为 1 至 999999 的整数")
    slots=int(raw)
    reason=ws.ident(data.get("reason"),600)
    nonce=ws.ident(data.get("nonce"),64)
    if not re.fullmatch(r"[a-zA-Z0-9_-]{12,64}",nonce):
        raise ValueError("请求编号无效")
    if not db.in_transaction: db.execute("BEGIN IMMEDIATE")
    owner=user["id"]
    previous=db.execute("SELECT id,slots,reason FROM monitor_slot_requests WHERE owner=? AND nonce=?",(owner,nonce)).fetchone()
    if previous:
        if previous["slots"]!=slots or previous["reason"]!=reason:
            raise ws.RequestError(409,"请求编号已被使用")
        return {"id":previous["id"]}
    new=db.execute("""INSERT INTO monitor_slot_requests(owner,period,slots,reason,nonce,created)
                      VALUES(?,?,?,?,?,?)""",(owner,ws.period(),slots,reason,nonce,ws.now()))
    return {"id":new.lastrowid}


def review(db,user,data):
    from platform_admin import require
    require(db,user)
    status=data.get("status")
    if status not in ("approved","rejected"):
        raise ValueError("审批状态无效")
    note=ws.ident(data.get("note"),600) if status=="rejected" or data.get("note") else ""
    if not db.in_transaction: db.execute("BEGIN IMMEDIATE")
    row=db.execute("SELECT * FROM monitor_slot_requests WHERE id=?",(int(data["id"]),)).fetchone()
    if not row: raise LookupError("未找到额度申请")
    if row["status"]!="pending":
        if row["reviewer"]==user["id"] and row["status"]==status and row["note"]==note:
            return {"id":row["id"],"status":status}
        raise ws.RequestError(409,"该申请已有审批结果")
    if row["period"]!=ws.period(): raise ws.RequestError(409,"该月申请已到期")
    db.execute("UPDATE monitor_slot_requests SET status=?,reviewer=?,decided=?,note=? WHERE id=? AND status='pending'",
               (status,user["id"],ws.now(),note,row["id"]))
    return {"id":row["id"],"status":status}


def history(db,user,data,operator=False):
    if operator:
        from platform_admin import require
        require(db,user)
    else:
        ws.admin(user)
    try:
        page=int(data.get("page",1))
        if not 1<=page<=100000000: raise ValueError
    except (ValueError,TypeError):
        raise ValueError("页码无效") from None
    month=ws.period()
    owner=ws.workspace(user)
    where="1" if operator else "r.owner=:owner"
    rows=db.execute(f"""SELECT r.id,r.owner,r.period,r.slots,r.reason,r.created,r.status,r.decided,r.note,
                        a.name AS requester,a.email AS email,b.name AS reviewer FROM monitor_slot_requests r
                        JOIN users a ON a.id=r.owner LEFT JOIN users b ON b.id=r.reviewer WHERE {where}
                        ORDER BY (r.status='pending' AND r.period=:month) DESC,r.id DESC LIMIT 21 OFFSET :offset""",
                    {"month":month,"owner":owner,"offset":(page-1)*20}).fetchall()
    quota={}
    if not operator:
        quota={"capacity":reconcile(db,owner),"active":db.execute(
            "SELECT count(*) FROM monitors WHERE owner=? AND status='active'",(owner,)).fetchone()[0]}
    return {**quota,"page":page,"more":len(rows)>20,"items":[{**dict(row),"expired":row["period"]<month,
            "can_review":bool(operator and row["status"]=="pending" and row["period"]==month)} for row in rows[:20]]}

"""Private deployment support cases, shared only with the requester and platform administrators."""
import re

import platform_admin
import workspace as ws


def init(db):
    db.executescript("""
        CREATE TABLE IF NOT EXISTS support_cases (
            id INTEGER PRIMARY KEY, uid INTEGER NOT NULL REFERENCES users(id), subject TEXT NOT NULL,
            updated INTEGER NOT NULL, awaiting_reply INTEGER NOT NULL
        );
        CREATE INDEX IF NOT EXISTS support_by_user ON support_cases(uid, updated DESC, id DESC);
        CREATE TABLE IF NOT EXISTS support_messages (
            id INTEGER PRIMARY KEY, ticket INTEGER NOT NULL REFERENCES support_cases(id),
            uid INTEGER NOT NULL REFERENCES users(id), is_operator INTEGER NOT NULL, body TEXT NOT NULL,
            created INTEGER NOT NULL, nonce TEXT NOT NULL, UNIQUE(uid,nonce)
        );
        CREATE INDEX IF NOT EXISTS support_by_ticket ON support_messages(ticket,id);
    """)


def ticket_id(raw):
    try:
        value = int(str(raw))
        if value < 1 or value > 2**63-1: raise ValueError
        return value
    except (TypeError,ValueError):
        raise ValueError("工单编号无效") from None


def ticket(db,user,ident,operator):
    row = db.execute("""SELECT t.id,t.uid,t.subject,t.updated,t.awaiting_reply,u.name AS requester
        FROM support_cases t JOIN users u ON u.id=t.uid WHERE t.id=? AND (t.uid=? OR ?)""",
        (ident,user["id"],operator)).fetchone()
    if row is None: raise LookupError("找不到该工单")
    item = dict(row)
    item["messages"] = [dict(r) for r in db.execute("""SELECT is_operator,body,created FROM support_messages
        WHERE ticket=? ORDER BY id""",(ident,))]
    return item


def handle(db,user,data,*,operator=False,write=False):
    ws.signed_in(user)
    if operator: platform_admin.require(db,user)
    uid = user["id"]
    ident = ticket_id(data["id"]) if "id" in data else None
    if write:
        nonce = ws.ident(data.get("nonce"),64)
        if not re.fullmatch(r"[a-zA-Z0-9_-]{12,64}",nonce): raise ValueError("请求编号无效")
        message = ws.ident(data.get("message"),4000)
        subject = ws.ident(data.get("subject"),120) if ident is None else None
        if operator and not ident: raise ValueError("需要工单编号")
        if not db.in_transaction: db.execute("BEGIN IMMEDIATE")
        prior = db.execute("SELECT ticket,body FROM support_messages WHERE uid=? AND nonce=?",(uid,nonce)).fetchone()
        if prior:
            if (ident and prior[0]!=ident) or prior[1]!=message:
                raise ws.RequestError(409,"请求编号已被使用")
            return ticket(db,user,prior[0],operator)
        if ident:
            ticket(db,user,ident,operator)
        stamp = ws.now()
        if ident is None:
            ident = db.execute("INSERT INTO support_cases(uid,subject,updated,awaiting_reply) VALUES(?,?,?,1)",
                               (uid,subject,stamp)).lastrowid
        else:
            db.execute("UPDATE support_cases SET updated=?,awaiting_reply=? WHERE id=?", (stamp,not operator,ident))
        db.execute("""INSERT INTO support_messages(ticket,uid,is_operator,body,created,nonce)
            VALUES(?,?,?,?,?,?)""",(ident,uid,operator,message,stamp,nonce))
        return ticket(db,user,ident,operator)
    if ident: return ticket(db,user,ident,operator)
    page = ticket_id(data.get("page",1))
    where = "1" if operator else "uid=:uid"
    args = {"uid":uid,"offset":min((page-1)*20,2**63-1)}
    rows = db.execute(f"""SELECT id,subject,updated,awaiting_reply FROM support_cases WHERE {where}
        ORDER BY updated DESC,id DESC LIMIT 21 OFFSET :offset""",args).fetchall()
    return {"items":[dict(r) for r in rows[:20]],"more":len(rows)>20,"page":page}

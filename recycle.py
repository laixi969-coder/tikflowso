"""Workspace-scoped, time-limited recovery of removed contacts and monitors."""
import json
import sqlite3
import time
import source_policy

def init(db):
    db.execute("""CREATE TABLE IF NOT EXISTS deleted_items(id INTEGER PRIMARY KEY,owner INTEGER,kind TEXT,
                 original_id INTEGER, label TEXT,payload TEXT,expires INTEGER NOT NULL)""")
    db.execute("CREATE INDEX IF NOT EXISTS deleted_expiry ON deleted_items(expires)")


def keep(db,owner,kind,row,readings=()):
    if row is None: return
    record=dict(row)
    db.execute("INSERT INTO deleted_items(owner,kind,original_id,label,payload,expires) VALUES(?,?,?,?,?,?)",
        (owner,kind,record.get("mid"),str(record.get("name") or record.get("id")),
         json.dumps({"record":record,"readings":[dict(r) for r in readings]},ensure_ascii=False),int(time.time())+30*86400))


def listing(db,owner):
    return [dict(r) for r in db.execute(f"""SELECT id,kind,label,expires FROM deleted_items WHERE owner=? AND expires>?
                      AND json_extract(payload,'$.record.source') IN ({source_policy.VISIBLE}) ORDER BY id DESC LIMIT 100""",(owner,int(time.time()),owner))]


def restore(db,user,ident):
    import workspace as ws
    ws.admin(user)
    if not db.in_transaction: db.execute("BEGIN IMMEDIATE")
    hit=db.execute("SELECT * FROM deleted_items WHERE owner=? AND id=? AND expires>?",(ws.workspace(user),ident,ws.now())).fetchone()
    if not hit: raise LookupError("恢复记录不存在或已过期")
    data=json.loads(hit["payload"])
    row=data["record"]
    ws.check_source(db,user,row["source"])
    if hit["kind"]=="monitor":
        # Restoring a completed task preserves history and lets the ordinary resume flow enforce capacity.
        row["status"]="completed"
        table="monitors"
    else: table="creator_contacts"
    columns=[col[1] for col in db.execute("PRAGMA table_info("+table+")") if col[1] in row]
    try:
        db.execute("INSERT INTO "+table+"("+",".join(columns)+") VALUES("+",".join("?" for _ in columns)+")",tuple(row[c] for c in columns))
        if hit["kind"]=="monitor":
            db.executemany("INSERT INTO readings(mid,day,value,hit) VALUES(:mid,:day,:value,:hit)",data["readings"])
    except sqlite3.IntegrityError as exc:
        raise ws.RequestError(409,"该记录已重新创建，保留当前版本") from exc
    db.execute("DELETE FROM deleted_items WHERE id=?",(ident,))
    return {"ok":True}


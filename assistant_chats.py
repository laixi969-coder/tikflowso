"""Personal research conversations, scoped to the account and its current workspace."""
import json
import analytics
import studio
import source_policy
import privacy
import workspace as ws


def init(db):
    db.executescript("""
        CREATE TABLE IF NOT EXISTS assistant_chats(
            id INTEGER PRIMARY KEY, uid INTEGER NOT NULL REFERENCES users(id), owner INTEGER NOT NULL,
            title TEXT NOT NULL, updated INTEGER NOT NULL);
        CREATE INDEX IF NOT EXISTS assistant_chats_actor ON assistant_chats(uid,owner,updated);
        CREATE TABLE IF NOT EXISTS assistant_turns(
            id INTEGER PRIMARY KEY, chat INTEGER NOT NULL REFERENCES assistant_chats(id),
            scope TEXT NOT NULL, question TEXT NOT NULL, response TEXT NOT NULL);
        CREATE INDEX IF NOT EXISTS assistant_turns_chat ON assistant_turns(chat,id);
    """)


def history(db,user,chat=None):
    actor = (user["id"],ws.workspace(user))
    if chat is None:
        return {"items":[privacy.scrub(dict(r)) for r in db.execute(
            f"""SELECT id,title FROM assistant_chats c WHERE uid=? AND owner=? AND NOT EXISTS
            (SELECT 1 FROM assistant_turns t WHERE t.chat=c.id AND json_extract(t.scope,'$.source') NOT IN ({source_policy.VISIBLE}))
            ORDER BY updated DESC,id DESC""",(*actor,actor[1]))]}
    row = owned_chat(db,user,chat)
    turns = [{"scope":json.loads(r["scope"]),"question":r["question"],**json.loads(r["response"])}
             for r in db.execute("SELECT * FROM assistant_turns WHERE chat=? ORDER BY id",(row["id"],))]
    return {**privacy.scrub(dict(row)),"turns":privacy.scrub(turns)}


def owned_chat(db,user,chat):
    row = db.execute("SELECT id,title FROM assistant_chats WHERE uid=? AND owner=? AND id=?",
                     (user["id"],ws.workspace(user),int(chat))).fetchone()
    if row is None:
        raise LookupError("未找到对话")
    denied=db.execute(f"""SELECT 1 FROM assistant_turns WHERE chat=? AND json_extract(scope,'$.source')
                          NOT IN ({source_policy.VISIBLE}) LIMIT 1""",(row["id"],ws.workspace(user))).fetchone()
    if denied: raise LookupError("未找到对话")
    return row


def answer(db,user,data):
    chat = data.get("chat")
    ws.check_source(db,user,str(data.get("source") or "demo"))
    resolved = analytics.scope_for(db,data)
    scope = {k:resolved[k] for k in ("market","source","date","days")}
    scope_json = json.dumps(scope)
    context = []
    if chat is not None:
        chat = owned_chat(db,user,chat)["id"]
        rows = db.execute("SELECT question,response FROM assistant_turns WHERE chat=? AND scope=? ORDER BY id DESC LIMIT 3",
                          (chat,scope_json)).fetchall()
        context = [{"question":r["question"][:1000],"answer":json.loads(r["response"])["result"][:1500]}
                   for r in reversed(rows)]
    response = studio.generate(db,{**data,**scope,"tool":"agent"},previous=context,owner=ws.workspace(user))
    if chat is None:
        chat = db.execute("INSERT INTO assistant_chats(uid,owner,title,updated) VALUES(?,?,?,?) RETURNING id",
                          (user["id"],ws.workspace(user),privacy.scrub(data["text"].strip())[:80],ws.now())).fetchone()[0]
    else:
        db.execute("UPDATE assistant_chats SET updated=? WHERE id=?",(ws.now(),chat))
    db.execute("INSERT INTO assistant_turns(chat,scope,question,response) VALUES(?,?,?,?)",
               (chat,scope_json,privacy.scrub(data["text"].strip()),json.dumps(privacy.scrub(response),ensure_ascii=False)))
    return {**response,"chat":int(chat),"scope":scope}

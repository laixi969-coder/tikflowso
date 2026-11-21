"""Consented referrals, Stripe-backed commission statements, and licensed research lists."""
from datetime import datetime, timezone
import os
import re
import secrets
import time
from urllib.parse import quote, urlencode, urlsplit

import workspace as ws
import settlement
import asset_checks


FINANCIAL_EVENTS = {"invoice.paid", "charge.succeeded", "charge.refunded", "refund.updated"}


def init(db):
    settlement.init(db)
    db.executescript("""
      CREATE TABLE IF NOT EXISTS captured_charges(mode TEXT,charge TEXT,captured INTEGER NOT NULL,PRIMARY KEY(mode,charge));
      CREATE TABLE IF NOT EXISTS partner_codes(
        uid INTEGER PRIMARY KEY REFERENCES users(id), code TEXT UNIQUE NOT NULL);
      CREATE TABLE IF NOT EXISTS partner_referrals(
        buyer INTEGER PRIMARY KEY REFERENCES users(id), partner INTEGER NOT NULL REFERENCES users(id),
        bps INTEGER NOT NULL, registered INTEGER NOT NULL, CHECK(buyer != partner));
      CREATE TABLE IF NOT EXISTS partner_ledger(
        mode TEXT NOT NULL, entry TEXT NOT NULL, charge TEXT NOT NULL, invoice TEXT NOT NULL,
        partner INTEGER NOT NULL, buyer INTEGER NOT NULL, currency TEXT NOT NULL, amount INTEGER NOT NULL,
        bps INTEGER NOT NULL, occurred INTEGER NOT NULL, PRIMARY KEY(mode,entry));
      CREATE INDEX IF NOT EXISTS partner_statements ON partner_ledger(partner,mode,charge,occurred);
      CREATE TABLE IF NOT EXISTS partner_library(
        id INTEGER PRIMARY KEY, owner INTEGER NOT NULL, kind TEXT NOT NULL, name TEXT NOT NULL,
        url TEXT NOT NULL, rights TEXT NOT NULL, product_id TEXT NOT NULL, updated INTEGER NOT NULL);
      CREATE TABLE IF NOT EXISTS partner_files(
        id INTEGER PRIMARY KEY REFERENCES partner_library(id) ON DELETE CASCADE,
        filename TEXT NOT NULL, expires TEXT, bytes BLOB NOT NULL);
    """)
    for col,decl in (("uploader","INTEGER"),("scan","TEXT NOT NULL DEFAULT 'pending'")):
        if col not in {r[1] for r in db.execute("PRAGMA table_info(partner_files)")}:
            db.execute("ALTER TABLE partner_files ADD COLUMN "+col+" "+decl)
    if "category" not in {r[1] for r in db.execute("PRAGMA table_info(partner_library)")}:
        db.execute("ALTER TABLE partner_library ADD COLUMN category TEXT NOT NULL DEFAULT ''")


def asset(db,user,asset_id,upload=None,filename="",expires=""):
    ws.signed_in(user)
    row=db.execute("SELECT kind FROM partner_library WHERE id=? AND owner=?", (asset_id,ws.workspace(user))).fetchone()
    if not row or row["kind"]!="asset": raise LookupError("未找到授权素材")
    if upload is not None:
        if not upload: raise ValueError("附件不能为空")
        if expires:
            from analytics import iso_day
            iso_day(expires)
        filename=ws.ident(filename,160)
        scan=asset_checks.inspect(upload,filename)
        if not db.in_transaction: db.execute("BEGIN IMMEDIATE")
        used=db.execute("""SELECT COALESCE(SUM(length(f.bytes)),0) FROM partner_files f JOIN partner_library l USING(id)
                           WHERE l.owner=? AND f.id!=?""",(ws.workspace(user),asset_id)).fetchone()[0]
        if used+len(upload)>int(os.getenv("TIKFLOWSO_ASSET_MIB","256"))*1024*1024:
            raise ws.RequestError(413,"工作区附件存储额度已满")
        db.execute("""INSERT INTO partner_files(id,filename,expires,bytes,uploader,scan) VALUES(?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET
                  filename=excluded.filename,expires=excluded.expires,bytes=excluded.bytes,uploader=excluded.uploader,scan=excluded.scan""",
                  (asset_id,filename,expires,upload,user["id"],scan))
        return {"ok":True}
    file=db.execute("SELECT filename,expires,bytes,scan,uploader FROM partner_files WHERE id=?",(asset_id,)).fetchone()
    if not file: raise LookupError("尚未上传素材")
    if file["expires"] and file["expires"]<datetime.now(timezone.utc).date().isoformat():
        raise ws.RequestError(403,"素材使用期限已过")
    if file["scan"]=="pending" and user["id"]!=(file["uploader"] or ws.workspace(user)):
        raise ws.RequestError(403,"此附件待安全扫描，暂限上传者访问")
    return file


def _bps():
    try:
        bps = int(os.getenv("TIKFLOWSO_AFFILIATE_BPS", "0"))
        if not 0 <= bps <= 10000:
            raise ValueError()
        return bps
    except ValueError as exc:
        raise ws.RequestError(503, "推荐佣金比例配置无效") from exc


def attribute(db, uid, code, consent):
    # Invoked inside the successful registration transaction only.
    if consent is not True:
        return
    if not isinstance(code, str) or not code.strip():
        raise ValueError("请填写推荐码")
    rec = db.execute("SELECT uid FROM partner_codes WHERE code=?", (code.strip().upper(),)).fetchone()
    if not rec or rec[0] == uid:
        raise ValueError("推荐码无效")
    db.execute("INSERT INTO partner_referrals(buyer,partner,bps,registered) VALUES(?,?,?,?)",
               (uid, rec[0], _bps(), int(time.time())))


def _summary(db, user):
    uid = user["id"]
    code = db.execute("SELECT code FROM partner_codes WHERE uid=?", (uid,)).fetchone()
    count = db.execute("SELECT count(*) FROM partner_referrals WHERE partner=?", (uid,)).fetchone()[0]
    return {"code": code[0] if code else None, "referred": count, "bps": _bps()}


def _library(db, owner, method, values):
    if method == "GET":
        return {"items": [dict(row) for row in db.execute(
            "SELECT l.id,kind,name,url,rights,product_id,category,updated,f.filename,f.expires FROM partner_library l LEFT JOIN partner_files f ON f.id=l.id WHERE owner=? ORDER BY updated DESC,l.id DESC", (owner,))]}
    item = values.get("id")
    action = values.get("action", "save")
    if action == "remove":
        if not db.execute("DELETE FROM partner_library WHERE id=? AND owner=?", (item, owner)).rowcount:
            raise LookupError("条目不存在")
        return {"removed": True}
    if action != "save" or values.get("kind") not in ("asset", "product"):
        raise ValueError("条目类型或操作无效")
    name = ws.ident(values.get("name"), 160)
    url = ws.ident(values.get("url"), 1500)
    parsed = urlsplit(url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("请使用不含账户信息的 HTTPS 链接")
    rights = ws.ident(values.get("rights"), 500)
    product_id = str(values.get("product_id") or "").strip()
    if len(product_id) > 160:
        raise ValueError("商品编号过长")
    category=values.get("category")
    if category is not None and (not isinstance(category,str) or len(category)>120):
        raise ValueError("品类最多 120 个字符")
    if isinstance(category,str): category=category.strip()
    fields = (values["kind"], name, url, rights, product_id, int(time.time()))
    if item is None:
        key = db.execute("INSERT INTO partner_library(kind,name,url,rights,product_id,updated,owner,category) VALUES(?,?,?,?,?,?,?,?)",
                         (*fields, owner,category or "")).lastrowid
    else:
        cur = db.execute("UPDATE partner_library SET kind=?,name=?,url=?,rights=?,product_id=?,updated=?,category=COALESCE(?,category) WHERE id=? AND owner=?",
                         (*fields,category, item, owner))
        if not cur.rowcount:
            raise LookupError("条目不存在")
        if values["kind"]!="asset": db.execute("DELETE FROM partner_files WHERE id=?",(item,))
        elif "expires" in values:
            expires=values["expires"]
            if expires:
                from analytics import iso_day
                iso_day(expires)
            db.execute("UPDATE partner_files SET expires=? WHERE id=?",(expires or None,item))
        key = item
    return {"id": key}


def _statement(db,uid,params):
    return settlement.statement(db,uid,params)


def handle(db, user, path, method, data):
    ws.signed_in(user)
    if path == "/api/partners/reviews":
        return settlement.history(db,user["id"]) if method=="GET" else settlement.request_review(db,user["id"],data)
    if path == "/api/partners" and method == "GET":
        return _summary(db, user)
    if path == "/api/partners/code" and method == "POST":
        code = secrets.token_hex(8).upper()
        db.execute("INSERT INTO partner_codes(uid,code) VALUES(?,?) ON CONFLICT(uid) DO NOTHING", (user["id"], code))
        return _summary(db, user)
    if path == "/api/partners/library" and method in ("GET", "POST"):
        return _library(db, ws.workspace(user), method, data)
    if path == "/api/partners/statement" and method == "GET":
        return _statement(db, user["id"], data)
    raise LookupError("合作接口不存在")


def _list(stripe, path, params):
    params = {**params, "limit": 100}
    seen=set()
    while True:
        reply = stripe(path + "?" + urlencode(params))
        if not isinstance(reply.get("data"),list) or type(reply.get("has_more")) is not bool:
            raise ValueError("支付平台分页格式发生变化")
        yield from reply["data"]
        if not reply["has_more"]: return
        cursor=reply["data"][-1].get("id") if reply["data"] else None
        if not cursor or cursor in seen: raise ValueError("支付平台分页未向前推进")
        seen.add(cursor)
        params["starting_after"] = cursor


def _stripe_object(stripe, path, ident):
    return stripe(path + "/" + quote(ident, safe=""))


def _eligible(stripe, invoice, prices):
    if invoice.get("status") != "paid" or not str(invoice.get("billing_reason")).startswith("subscription"):
        return False
    lines = invoice.get("lines", {})
    entries = lines.get("data", [])
    if lines.get("has_more"):
        entries = list(_list(stripe, "invoices/" + quote(invoice["id"], safe="") + "/lines", {}))
    return bool(entries) and all(
        (row.get("pricing", {}).get("price_details", {}).get("price") or (row.get("price") or {}).get("id")) in prices
        for row in entries)


def _referral(db, customer):
    return db.execute("""SELECT r.* FROM billing_customers c JOIN partner_referrals r ON r.buyer=c.user_id
                         WHERE c.customer_id=?""", (customer,)).fetchone()


def _allocations(stripe, charge, ref, prices):
    captured=charge.get("amount_captured",0)
    if not charge.get("paid") or not charge.get("captured") or captured<=0 or charge["created"]<ref["registered"]:
        return []
    payments=_list(stripe,"invoice_payments",{"payment[type]":"payment_intent",
                   "payment[payment_intent]":charge["payment_intent"],"status":"paid"})
    parts=[]
    for pay in payments:
        if pay.get("payment",{}).get("payment_intent")!=charge["payment_intent"]: continue
        invoice=_stripe_object(stripe,"invoices",pay["invoice"])
        amount=pay["amount_paid"]
        if (type(amount) is not int or amount<0 or invoice.get("customer")!=charge["customer"]
            or invoice.get("currency")!=charge["currency"] or invoice.get("livemode") is not charge["livemode"]):
            raise ValueError("发票分配需要对账")
        if amount:
            parts.append((pay.get("id") or pay["invoice"],invoice,amount,_eligible(stripe,invoice,prices)))
    if not parts: return []
    if sum(p[2] for p in parts)!=captured or len({p[0] for p in parts})!=len(parts):
        raise ValueError("收款与发票分配尚未平衡")
    refunds=[]
    if charge.get("amount_refunded",0):
        refunds=sorted((r for r in _list(stripe,"refunds",{"charge":charge["id"]})
                        if r.get("status")=="succeeded" and r.get("charge")==charge["id"] and r.get("currency")==charge["currency"]),
                       key=lambda r:(r["created"],r["id"]))
        if sum(r["amount"] for r in refunds)!=charge["amount_refunded"] or not 0<=charge["amount_refunded"]<=captured:
            raise ValueError("实收与退款合计尚未平衡")
    mode="live" if charge["livemode"] else "test"
    rows=[]
    offset=0
    for payment,invoice,amount,eligible in sorted(parts,key=lambda p:p[0]):
        if eligible:
            suffix="" if len(parts)==1 else "/"+payment
            fields=(charge["id"],invoice["id"],ref["partner"],ref["buyer"],charge["currency"])
            rows.append((mode,charge["id"]+suffix,*fields,amount,ref["bps"],charge["created"]))
            returned=0
            for refund in refunds:
                # Allocate an unassigned charge refund to invoice payments in stable ID order.
                before=min(amount,max(0,returned-offset))
                returned+=refund["amount"]
                portion=min(amount,max(0,returned-offset))-before
                if portion: rows.append((mode,refund["id"]+suffix,*fields,-portion,ref["bps"],refund["created"]))
        offset+=amount
    return rows


def financial_event(db, event, stripe, prices, *, preview=False):
    obj=event["data"]["object"]
    kind=event["type"]
    if kind=="invoice.paid":
        if not _referral(db,obj.get("customer")): return {"ignored":True}
        invoice=_stripe_object(stripe,"invoices",obj["id"])
        if not _eligible(stripe,invoice,prices): return {"ignored":True}
        ids=set()
        for pay in _list(stripe,"invoice_payments",{"invoice":invoice["id"],"status":"paid"}):
            pi=pay.get("payment",{}).get("payment_intent")
            if pi:
                charge=_stripe_object(stripe,"payment_intents",pi).get("latest_charge")
                if charge: ids.add(charge)
        if not ids: raise ValueError("已付推广发票缺少可核对的收款")
    else:
        if kind.startswith("charge.") and not _referral(db,obj.get("customer")): return {"ignored":True}
        cid=obj.get("charge") if kind=="refund.updated" else obj.get("id")
        ids={cid} if cid else set()
    rows=[]
    captures=[]
    for cid in sorted(ids):
        charge=_stripe_object(stripe,"charges",cid)
        ref=_referral(db,charge.get("customer"))
        if (not ref or not charge.get("payment_intent") or type(event.get("livemode")) is not bool
                or event["livemode"] is not charge.get("livemode")): continue
        entries=_allocations(stripe,charge,ref,prices)
        if kind=="invoice.paid" and not entries:
            raise ValueError("推广发票尚无可核对的分录")
        if entries:
            captures.append((entries[0][0],cid,charge["amount_captured"]))
            rows.extend(entries)
    changes=[]
    with db:
        if not preview and captures and not db.in_transaction: db.execute("BEGIN IMMEDIATE")
        for mode,cid,captured in captures:
            new_entries={r[1] for r in rows if r[0]==mode and r[2]==cid and r[7]>0}
            prior={r[0] for r in db.execute("SELECT entry FROM partner_ledger WHERE mode=? AND charge=? AND amount>0",(mode,cid))}
            if prior-new_entries: raise ValueError("已入账的发票分配发生变更，需人工对账")
        for row in rows:
            old=db.execute("SELECT * FROM partner_ledger WHERE mode=? AND entry=?",row[:2]).fetchone()
            if old and tuple(old)!=row: raise ValueError("已有分录与支付平台不同，需人工对账")
            if not old:
                changes.append({"entry":row[1],"currency":row[6],"amount":row[7],"occurred":row[9]})
                if not preview: db.execute("INSERT INTO partner_ledger VALUES(?,?,?,?,?,?,?,?,?,?)",row)
        if not preview: db.executemany("INSERT OR IGNORE INTO captured_charges VALUES(?,?,?)",captures)
    return {"received":True,"matched":bool(rows),"changes":changes}

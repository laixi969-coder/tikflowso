"""Offline commission review. Host operator decisions are separate from partner requests."""
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
import hashlib
import json
import re
import time

import analytics
import workspace as ws


def init(db):
    db.executescript("""
      CREATE TABLE IF NOT EXISTS partner_disputes(
        mode TEXT NOT NULL,case_id TEXT NOT NULL,charge TEXT NOT NULL,amount INTEGER NOT NULL,
        status TEXT NOT NULL,opened INTEGER NOT NULL,closed INTEGER,reason TEXT NOT NULL,
        resolution TEXT,PRIMARY KEY(mode,case_id));
      CREATE TABLE IF NOT EXISTS dispute_changes(
        seq INTEGER PRIMARY KEY,mode TEXT NOT NULL,case_id TEXT NOT NULL,action TEXT NOT NULL,
        delta INTEGER NOT NULL,stamp INTEGER NOT NULL,note TEXT NOT NULL);
      CREATE INDEX IF NOT EXISTS dispute_change_case ON dispute_changes(mode,case_id);
      INSERT INTO dispute_changes(mode,case_id,action,delta,stamp,note)
        SELECT mode,case_id,status,CASE WHEN status='lost' THEN -amount ELSE 0 END,
        COALESCE(closed,opened),COALESCE(resolution,reason) FROM partner_disputes d
        WHERE NOT EXISTS(SELECT 1 FROM dispute_changes c WHERE c.mode=d.mode AND c.case_id=d.case_id);
      CREATE TABLE IF NOT EXISTS processor_dispute_events(
        mode TEXT NOT NULL,event TEXT NOT NULL,case_id TEXT NOT NULL,charge TEXT NOT NULL,currency TEXT NOT NULL,
        amount INTEGER NOT NULL,provider_status TEXT NOT NULL,occurred INTEGER NOT NULL,
        PRIMARY KEY(mode,event));
      CREATE INDEX IF NOT EXISTS dispute_charge ON processor_dispute_events(mode,charge,occurred);
      CREATE TABLE IF NOT EXISTS settlement_requests(
        id INTEGER PRIMARY KEY,partner INTEGER NOT NULL,mode TEXT NOT NULL,month TEXT NOT NULL,
        fx_date TEXT NOT NULL, snapshot TEXT NOT NULL,digest TEXT NOT NULL,status TEXT NOT NULL,
        created INTEGER NOT NULL,reviewer TEXT,reason TEXT,reviewed INTEGER);
      CREATE UNIQUE INDEX IF NOT EXISTS one_pending_settlement ON settlement_requests(partner,mode,month)
        WHERE status='pending';
    """)


def receive_event(db,event):
    """Retain the signed provider notice even if the related payment has not arrived."""
    obj=event["data"]["object"]
    if (type(event.get("livemode")) is not bool or event["livemode"] is not obj.get("livemode")
        or obj.get("object")!="dispute" or type(obj.get("amount")) is not int or obj["amount"]<=0
        or type(event.get("created")) is not int):
        raise ValueError("争议事件格式无效")
    fields=[ws.ident(obj.get(k),160) for k in ("id","charge","currency","status")]
    row=db.execute("""INSERT OR IGNORE INTO processor_dispute_events VALUES(?,?,?,?,?,?,?,?)""",
                   ("live" if event["livemode"] else "test",ws.ident(event["id"],200),*fields[:3],
                    obj["amount"],fields[3],event["created"]))
    return {"received":True,"duplicate":not bool(row.rowcount)}


def dispute(db,mode,case_id,charge,amount,action,note):
    """Operator-only local reconciliation; amount in the charge's smallest monetary unit."""
    if mode not in ("test","live") or not isinstance(amount,int) or amount<=0:
        raise ValueError("请核对环境与争议金额")
    note=ws.ident(note,500)
    case_id=ws.ident(case_id,160)
    if not db.in_transaction: db.execute("BEGIN IMMEDIATE")
    parent=db.execute("SELECT COALESCE((SELECT captured FROM captured_charges WHERE mode=? AND charge=?),SUM(amount)) FROM partner_ledger WHERE charge=? AND mode=? AND amount>0",(mode,charge,charge,mode)).fetchone()
    if not parent or not parent[0] or amount>parent[0]: raise ValueError("原实收记录不存在或争议金额超过实收")
    old=db.execute("SELECT * FROM partner_disputes WHERE mode=? AND case_id=?",(mode,case_id)).fetchone()
    if old and (old["charge"]!=charge or old["amount"]!=amount): raise ValueError("争议编号与原记录不匹配")
    if old and (old["status"]==action or action=="reopen" and old["status"]=="open"): return
    stamp=int(time.time())
    if not old and action=="open":
        db.execute("INSERT INTO partner_disputes VALUES(?,?,?,?,'open',?,NULL,?,NULL)",(mode,case_id,charge,amount,stamp,note))
    elif old and old["status"]=="open" and action in ("won","lost"):
        db.execute("UPDATE partner_disputes SET status=?,resolution=?,closed=? WHERE mode=? AND case_id=?",
                   (action,note,stamp,mode,case_id))
    elif old and action=="reopen" and old["status"] in ("won","lost"):
        db.execute("UPDATE partner_disputes SET status='open',resolution=?,closed=NULL WHERE mode=? AND case_id=?",
                   (note,mode,case_id))
    else: raise ValueError("争议状态变更无效")
    balance=db.execute("SELECT COALESCE(SUM(delta),0) FROM dispute_changes WHERE mode=? AND case_id=?",
                       (mode,case_id)).fetchone()[0]
    target=-amount if action=="lost" else 0 if action=="won" else balance
    db.execute("INSERT INTO dispute_changes(mode,case_id,action,delta,stamp,note) VALUES(?,?,?,?,?,?)",
               (mode,case_id,action,target-balance,stamp,note))


def minor_factor(code):
    if code in ("BHD","JOD","KWD","OMR","TND"): return 1000
    if code in ("BIF","CLP","DJF","GNF","JPY","KMF","KRW","MGA","PYG","RWF","VND","VUV","XAF","XOF","XPF"): return 1
    return 100


def statement(db,uid,params):
    mode=params.get("mode","test")
    month=params.get("month") or datetime.now(timezone.utc).strftime("%Y-%m")
    if mode not in ("test","live") or not re.fullmatch(r"[0-9]{4}-(?:0[1-9]|1[0-2])",month):
        raise ValueError("请选择有效的账期及环境")
    # One provider dispute applies once per charge, including split invoice payments.
    db.create_function('charge_share',3,lambda delta,part,total: (1 if delta>=0 else -1)*(abs(delta)*part//total),deterministic=True)
    parents="""SELECT p.mode,p.charge,p.partner,MIN(p.invoice) AS invoice,MIN(p.currency) AS currency,
        MIN(p.bps) AS bps,MIN(p.occurred) AS occurred,SUM(p.amount) AS eligible,
        COALESCE(MAX(cc.captured),SUM(p.amount)) AS captured FROM partner_ledger p
        LEFT JOIN captured_charges cc ON cc.mode=p.mode AND cc.charge=p.charge
        WHERE p.amount>0 GROUP BY p.mode,p.charge,p.partner"""
    rows=db.execute(f"""WITH parents AS ({parents}), events AS (
      SELECT invoice,charge,entry,currency,amount,bps,occurred FROM partner_ledger WHERE partner=? AND mode=?
      UNION ALL SELECT p.invoice,p.charge,'dispute:'||d.case_id||':'||printf('%020d',c.seq),p.currency,charge_share(c.delta,p.eligible,p.captured),p.bps,c.stamp
      FROM dispute_changes c JOIN partner_disputes d ON d.mode=c.mode AND d.case_id=c.case_id
      JOIN parents p ON p.mode=d.mode AND p.charge=d.charge
      WHERE d.mode=? AND p.partner=? AND c.delta!=0
    ), balances AS (
      SELECT *,SUM(amount) OVER(PARTITION BY charge ORDER BY occurred,(amount<0),entry ROWS UNBOUNDED PRECEDING) AS net FROM events)
    SELECT invoice,charge,entry,currency,MAX(net,0)-MAX(net-amount,0) AS amount,bps,occurred,
      (MAX(net,0)*bps/10000)-(MAX(net-amount,0)*bps/10000) AS commission FROM balances
    WHERE strftime('%Y-%m',occurred,'unixepoch')=? ORDER BY occurred,(amount<0),entry""",(uid,mode,mode,uid,month))
    items=[dict(r) for r in rows]
    totals={}
    for r in items:
        group=totals.setdefault(r["currency"],{"amount":0,"commission":0})
        for k in group: group[k]+=r[k]
    cases=[dict(r) for r in db.execute("""SELECT DISTINCT d.case_id,d.charge,d.status,d.amount,d.reason,d.resolution
        FROM partner_disputes d JOIN partner_ledger p ON p.mode=d.mode AND p.charge=d.charge
        WHERE p.partner=? AND p.mode=? AND (strftime('%Y-%m',p.occurred,'unixepoch')=?
        OR strftime('%Y-%m',d.closed,'unixepoch')=?) ORDER BY case_id""",(uid,mode,month,month))]
    notices=db.execute(f"""WITH parents AS ({parents}), latest AS (
      SELECT e.*,ROW_NUMBER() OVER(PARTITION BY case_id ORDER BY e.occurred DESC,
        (provider_status IN ('lost','won','warning_closed','prevented')) DESC,event DESC) AS seq
      FROM processor_dispute_events e WHERE mode=?)
      SELECT e.case_id,e.charge,e.provider_status,e.amount,e.currency,e.occurred,p.currency AS paid_currency,
        d.status AS local_state,d.amount AS local_amount,d.charge AS local_charge FROM latest e JOIN parents p ON p.mode=e.mode AND p.charge=e.charge
        LEFT JOIN partner_disputes d ON d.case_id=e.case_id AND d.mode=e.mode
      WHERE e.seq=1 AND p.partner=? AND (strftime('%Y-%m',p.occurred,'unixepoch')=?
        OR strftime('%Y-%m',e.occurred,'unixepoch')=?) ORDER BY e.case_id""",(mode,uid,month,month))
    for row in notices:
        expected={"won":"won","prevented":"won","warning_closed":"won","lost":"lost"}.get(row["provider_status"])
        resolved=(expected is not None and expected==row["local_state"] and row["currency"]==row["paid_currency"]
                  and row["amount"]==row["local_amount"] and row["charge"]==row["local_charge"])
        cases.append({**dict(row),"status":"reviewed" if resolved else "open","reason":"Stripe · "+row["provider_status"]})
    return {"mode":mode,"month":month,"units":"currency minor units","totals":totals,"items":items,"disputes":cases}


def snapshot(db,uid,params):
    report=statement(db,uid,params)
    day=analytics.iso_day(params["fx_date"]).isoformat() if params.get("fx_date") else ""
    base,rates=analytics.exchange_rates(day) if day else (None,{})
    converted=[]
    if day:
        for currency,group in sorted(report["totals"].items()):
            code=currency.upper()
            if code not in rates: raise ValueError(f"{day} 缺少 {code} 汇率")
            amount=Decimal(group["commission"])/minor_factor(code)*rates[code]
            converted.append({"currency":code,"rate":str(rates[code]),"base_amount":str(amount)})
    total=sum((Decimal(r["base_amount"]) for r in converted),Decimal(0))
    rounded=total.quantize(Decimal(1)/minor_factor(base),rounding=ROUND_HALF_UP) if base else None
    report["conversion"]={"date":day,"currency":base,"lines":converted,"total":str(rounded) if base else None}
    return report


def signature(report):
    return hashlib.sha256(json.dumps(report,sort_keys=True,ensure_ascii=False).encode()).hexdigest()


def request_review(db,uid,params):
    if not db.in_transaction: db.execute("BEGIN IMMEDIATE")
    report=snapshot(db,uid,params)
    if not report["items"]: raise ValueError("账期内没有可核对的流水")
    if any(d["status"]=="open" for d in report["disputes"]): raise ValueError("此账期存在未结争议")
    digest=signature(report)
    prev=db.execute("""SELECT id,digest,status FROM settlement_requests WHERE partner=? AND mode=? AND month=?
                       ORDER BY id DESC LIMIT 1""",(uid,report["mode"],report["month"])).fetchone()
    if prev and prev["digest"]==digest and prev["status"] in ("approved","pending"): return {"id":prev["id"]}
    if prev and prev["status"]=="pending":
        db.execute("UPDATE settlement_requests SET status='superseded' WHERE id=?",(prev["id"],))
    r=db.execute("""INSERT INTO settlement_requests(partner,mode,month,fx_date,snapshot,digest,status,created)
                    VALUES(?,?,?,?,?,?,'pending',?)""",(uid,report["mode"],report["month"],
                    report["conversion"]["date"],json.dumps(report,ensure_ascii=False),digest,int(time.time())))
    return {"id":r.lastrowid}


def review(db,request_id,decision,reviewer,reason):
    if decision not in ("approved","rejected"): raise ValueError("审批结论无效")
    if not db.in_transaction: db.execute("BEGIN IMMEDIATE")
    row=db.execute("SELECT * FROM settlement_requests WHERE id=?",(request_id,)).fetchone()
    if not row or row["status"]!="pending": raise ValueError("没有待审申请")
    if decision=="approved" and signature(snapshot(db,row["partner"],dict(row)))!=row["digest"]:
        raise ValueError("流水、争议或汇率已有变化，请重新提交")
    if decision=="approved":
        db.execute("""UPDATE settlement_requests SET status='superseded' WHERE partner=? AND mode=? AND month=?
                      AND status='approved'""",(row["partner"],row["mode"],row["month"]))
    db.execute("UPDATE settlement_requests SET status=?,reviewer=?,reason=?,reviewed=? WHERE id=?",
               (decision,ws.ident(reviewer,80),ws.ident(reason,500),int(time.time()),request_id))


def history(db,uid):
    return {"items":[dict(r) for r in db.execute("""SELECT id,mode,month,status,fx_date,reviewer,reason,created,reviewed,
                    json_extract(snapshot,'$.conversion.total') AS converted,json_extract(snapshot,'$.conversion.currency') AS currency
                    FROM settlement_requests WHERE partner=? ORDER BY id DESC LIMIT 100""",(uid,))]}

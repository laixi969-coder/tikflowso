"""Reserve an auditable worst-case USD amount for each paid inference before dispatch."""
from contextlib import contextmanager, closing
from contextvars import ContextVar
from datetime import datetime,timezone
from decimal import Decimal,InvalidOperation,ROUND_CEILING
import json
import os
from pathlib import Path
from urllib.parse import urlsplit


_current=ContextVar("model_billing",default=None)


def init(db):
    db.executescript("""
      CREATE TABLE IF NOT EXISTS model_calls(id INTEGER PRIMARY KEY,owner INTEGER NOT NULL,
        month TEXT NOT NULL,model TEXT NOT NULL,endpoint TEXT NOT NULL,charged INTEGER NOT NULL,
        reserved INTEGER NOT NULL,input_tokens INTEGER,output_tokens INTEGER,state TEXT NOT NULL);
      CREATE INDEX IF NOT EXISTS model_month_owner ON model_calls(month,owner);
      CREATE TABLE IF NOT EXISTS research_permissions(owner INTEGER,source TEXT,destination TEXT,
        history INTEGER NOT NULL,comments INTEGER NOT NULL,PRIMARY KEY(owner,source,destination));
    """)


@contextmanager
def scope(connect,owner):
    state={"connect":connect,"owner":owner,"sent":0}
    token=_current.set(state)
    try: yield state
    finally: _current.reset(token)


def trusted_local(url):
    return (os.getenv("TIKFLOWSO_TRUST_LOCAL_MODEL")=="1"
            and urlsplit(url).hostname in ("localhost","127.0.0.1","::1"))


def policy(db,owner,source,dest):
    if trusted_local(dest.split(" ",1)[0]): return {"history":True,"comments":True}
    if owner is None: return None
    row=db.execute("SELECT history,comments FROM research_permissions WHERE owner=? AND source=? AND destination=?",
                   (owner,source,dest)).fetchone()
    return {"history":bool(row[0]),"comments":bool(row[1])} if row else None


def usd(value):
    number=Decimal(str(value))
    if not number.is_finite() or number<0 or number>1000000: raise ValueError
    return number


def micro(value):
    return int((value*1000000).to_integral_value(rounding=ROUND_CEILING))


def reserve(url,body):
    from workspace import RequestError
    if trusted_local(url): return None
    state=_current.get()
    if not state: raise RequestError(503,"付费模型调用缺少预算账户")
    try:
        config=json.loads(Path(os.environ["TIKFLOWSO_MODEL_PRICING"]).read_text())
        tariff=next(r for r in config["models"] if (r["endpoint"],r["model"])==(url,body["model"]))
        input_limit=int(tariff["context_tokens"])
        output_limit=int(tariff["max_output_tokens"])
        if not 0<output_limit<=input_limit<=10000000: raise ValueError
        input_rate=usd(tariff["input_usd_per_million"])
        output_rate=usd(tariff["output_usd_per_million"])
        if not input_rate or not output_rate: raise ValueError
        # Reserve the contractual maximum, including image/context and chargeable reasoning tokens.
        fixed=usd(tariff.get("fixed_usd",0))
        maximum=micro(fixed)+int((input_limit*input_rate+output_limit*output_rate).to_integral_value(rounding=ROUND_CEILING))
        limits=[micro(usd(config["platform_month_usd"])),micro(usd(config.get("workspace_limits",{}).get(str(state["owner"]),config["workspace_month_usd"])))]
    except (OSError,StopIteration,KeyError,TypeError,ValueError,InvalidOperation) as exc:
        raise RequestError(503,"管理员需为该端点和模型配置有效价格及预算") from exc
    body["max_tokens"]=min(int(body.get("max_tokens",output_limit)),output_limit)
    month=datetime.now(timezone.utc).strftime("%Y-%m")
    with closing(state["connect"]()) as db, db:
        db.execute("BEGIN IMMEDIATE")
        total,tenant=db.execute("""SELECT COALESCE(SUM(charged),0),
             COALESCE(SUM(CASE WHEN owner=? THEN charged ELSE 0 END),0) FROM model_calls WHERE month=?""",
             (state["owner"],month)).fetchone()
        if total+maximum>limits[0] or tenant+maximum>limits[1]:
            raise RequestError(429,"本月模型费用预算不足")
        ident=db.execute("""INSERT INTO model_calls(owner,month,model,endpoint,charged,reserved,state)
              VALUES(?,?,?,?,?,?,'reserved') RETURNING id""",(state["owner"],month,body["model"],url,maximum,maximum)).fetchone()[0]
    state["sent"]+=1
    return (state["connect"],ident,input_rate,output_rate,micro(fixed),input_limit,output_limit)


def settle(ticket,response):
    if ticket is None: return
    connect,ident,input_rate,output_rate,fixed,input_limit,output_limit=ticket
    usage=response.get("usage",{}) if isinstance(response,dict) else {}
    if not isinstance(usage,dict): return
    a,b=usage.get("prompt_tokens"),usage.get("completion_tokens")
    if type(a) is not int or type(b) is not int or not 0<=a<=input_limit or not 0<=b<=output_limit: return
    charge=fixed+int((a*input_rate+b*output_rate).to_integral_value(rounding=ROUND_CEILING))
    with closing(connect()) as db, db:
        db.execute("""UPDATE model_calls SET state='metered',input_tokens=?,output_tokens=?,charged=?
                   WHERE id=? AND state='reserved'""",(a,b,charge,ident))


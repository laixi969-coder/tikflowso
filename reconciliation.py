"""Compare referral income and refunds with the configured Stripe account using read-only vendor calls."""
from contextlib import closing
from datetime import date,datetime,time,timezone
import sqlite3

import billing
import partnerships


def run(path, since, until, apply=False, *, stripe=None):
    first,last=(datetime.combine(date.fromisoformat(day),time.min,timezone.utc) for day in (since,until))
    if not first<last: raise ValueError("截止日期须晚于起始日期")
    if stripe is None:
        billing._require_enabled()
        stripe=billing._stripe
    prices=set(filter(None,billing._prices().values()))
    if not prices: raise ValueError("请配置订阅价格")
    result={"applied":apply,"charges":0,"changes":[],"needs_review":[]}
    mode="rw" if apply else "ro"
    with closing(sqlite3.connect(path.resolve().as_uri()+"?mode="+mode,uri=True,timeout=15)) as db:
        db.row_factory=sqlite3.Row
        customers=db.execute("""SELECT customer_id FROM billing_customers c JOIN partner_referrals r ON r.buyer=c.user_id
                             WHERE customer_id IS NOT NULL ORDER BY customer_id""").fetchall()
        for (customer,) in customers:
            params={"customer":customer,"created[gte]":int(first.timestamp()),"created[lt]":int(last.timestamp())}
            for charge in partnerships._list(stripe,"charges",params):
                if charge.get("customer")!=customer or type(charge.get("livemode")) is not bool:
                    raise ValueError("收款归属需要核对")
                result["charges"]+=1
                event={"type":"charge.succeeded","livemode":charge["livemode"],"data":{"object":charge}}
                try:
                    entry=partnerships.financial_event(db,event,stripe,prices,preview=not apply)
                    result["changes"].extend(entry.get("changes",[]))
                except (ValueError,KeyError,TypeError) as exc:
                    result["needs_review"].append({"charge":charge["id"],"reason":type(exc).__name__})
    return result


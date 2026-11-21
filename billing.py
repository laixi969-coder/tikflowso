"""Stripe-hosted subscription checkout, account portal, and entitlement reconciliation."""

import hashlib
import hmac
import json
import os
import secrets
import time
from urllib import error, parse, request
import partnerships


class BillingError(ValueError):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def init(db):
    db.executescript("""
        CREATE TABLE IF NOT EXISTS billing_customers (
            user_id PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
            create_key TEXT NOT NULL UNIQUE,
            customer_id TEXT UNIQUE,
            revision INTEGER NOT NULL DEFAULT 0,
            checkout_plan TEXT,
            checkout_key TEXT,
            session_id TEXT
        );
        CREATE TABLE IF NOT EXISTS billing_events (
            event_id TEXT PRIMARY KEY,
            user_id REFERENCES users(id) ON DELETE CASCADE,
            processed_at INTEGER NOT NULL
        );
    """)


def _prices():
    return {plan: os.getenv("STRIPE_PRICE_" + plan.upper(), "") for plan in ("pro", "team")}


def _enabled():
    prices = _prices().values()
    return bool(os.getenv("STRIPE_SECRET_KEY") and os.getenv("STRIPE_WEBHOOK_SECRET")
                and all(prices) and len(set(prices)) == 2)


def _require_enabled():
    if not _enabled():
        raise BillingError("订阅服务尚未配置。", 503)


def _base():
    url = os.getenv("TIKFLOWSO_PUBLIC_URL", "http://127.0.0.1:8765").rstrip("/")
    target = parse.urlsplit(url)
    if not target.hostname or target.username or target.password or target.query or target.fragment:
        raise BillingError("订阅返回地址配置无效。", 503)
    if target.scheme != "https" and not (target.scheme == "http" and target.hostname in ("localhost", "127.0.0.1", "::1")):
        raise BillingError("订阅返回地址需要 HTTPS 或本机地址。", 503)
    return url + "/"


def _stripe(path, fields=None, *, key=None):
    headers = {"Authorization": "Bearer " + os.environ["STRIPE_SECRET_KEY"],
               "Stripe-Version": "2025-08-27.basil"}
    data = None if fields is None else parse.urlencode(fields).encode()
    if key:
        headers["Idempotency-Key"] = key
    req = request.Request("https://api.stripe.com/v1/" + path, data=data, headers=headers)
    try:
        with request.urlopen(req, timeout=12) as resp:
            return json.load(resp)
    except (error.URLError, TimeoutError, OSError, ValueError) as exc:
        raise BillingError("支付平台暂时无法处理请求，请检查支付配置后重试。", 502) from exc


def _record(db, uid):
    return db.execute("SELECT * FROM billing_customers WHERE user_id=?", (uid,)).fetchone()


def status(db, user):
    rec = _record(db, user["id"]) if user else None
    return {"configured": _enabled(), "plan": user["plan"] if user else "free",
            "has_customer": bool(rec and rec["customer_id"]), "plans": ["free", "pro", "team"]}


def _customer(db, user):
    uid = user["id"]
    with db:
        db.execute("INSERT INTO billing_customers(user_id,create_key) VALUES (?,?) "
                   "ON CONFLICT(user_id) DO NOTHING", (uid, secrets.token_hex(20)))
    rec = _record(db, uid)
    if not rec["customer_id"]:
        result = _stripe("customers", {"metadata[tikflowso_user]": str(uid)}, key=rec["create_key"])
        with db:
            db.execute("UPDATE billing_customers SET customer_id=? WHERE user_id=? AND customer_id IS NULL",
                       (result["id"], uid))
        rec = _record(db, uid)
    return rec


def _subscriptions(customer):
    plans = {price: plan for plan, price in _prices().items()}
    best = "free"
    has_contract = False
    params = {"customer": customer, "limit": 100}
    while True:
        page = _stripe("subscriptions?" + parse.urlencode(params))
        for sub in page["data"]:
            if sub.get("customer") != customer or sub.get("status") in ("canceled", "incomplete_expired"):
                continue
            for item in sub["items"]["data"]:
                plan = plans.get(item["price"]["id"])
                if not plan:
                    continue
                has_contract = True
                if sub.get("status") not in ("active", "trialing"):
                    continue
                if plan == "team":
                    return "team", True
                if plan == "pro":
                    best = plan
        if not page.get("has_more"):
            return best, has_contract
        params["starting_after"] = page["data"][-1]["id"]


def checkout(db, user, plan):
    _require_enabled()
    if plan not in _prices():
        raise BillingError("请选择 Pro 或 Team 套餐。")
    target = _base()
    rec = _customer(db, user)
    uid, customer = user["id"], rec["customer_id"]
    if _subscriptions(customer)[1]:
        raise BillingError("已有订阅，请从账单门户管理套餐与付款。", 409)
    if rec["session_id"]:
        session = _stripe("checkout/sessions/" + parse.quote(rec["session_id"], safe=""))
        if session.get("status") == "open":
            if rec["checkout_plan"] == plan:
                return {"url": session["url"]}
            _stripe("checkout/sessions/" + parse.quote(session["id"], safe="") + "/expire", {})
        if session.get("status") == "complete":
            sub_id = session.get("subscription")
            if not sub_id:
                raise BillingError("付款结果正在同步，请稍后重试。", 409)
            sub = _stripe("subscriptions/" + parse.quote(sub_id, safe=""))
            if sub.get("status") not in ("canceled", "incomplete_expired"):
                raise BillingError("已有结账记录，请在账单门户核对付款状态。", 409)
        with db:
            db.execute("UPDATE billing_customers SET session_id=NULL,checkout_key=NULL,checkout_plan=NULL "
                       "WHERE user_id=? AND session_id=?", (uid, rec["session_id"]))
    with db:
        db.execute("UPDATE billing_customers SET checkout_key=?,checkout_plan=? "
                   "WHERE user_id=? AND checkout_key IS NULL", (secrets.token_hex(20), plan, uid))
        rec = _record(db, uid)
    if rec["checkout_plan"] != plan:
        raise BillingError("另一个套餐的结账请求正在处理，请稍后重试。", 409)
    fields = {"mode": "subscription", "customer": customer, "client_reference_id": str(uid),
              "line_items[0][price]": _prices()[plan], "line_items[0][quantity]": 1,
              "subscription_data[metadata][tikflowso_user]": str(uid), "success_url": target,
              "cancel_url": target}
    session = _stripe("checkout/sessions", fields, key=rec["checkout_key"])
    with db:
        db.execute("UPDATE billing_customers SET session_id=? WHERE user_id=? AND checkout_key=?",
                   (session["id"], uid, rec["checkout_key"]))
    return {"url": session["url"]}


def portal(db, user):
    _require_enabled()
    rec = _record(db, user["id"])
    if not rec or not rec["customer_id"]:
        raise BillingError("尚未创建账单账户。", 409)
    result = _stripe("billing_portal/sessions", {"customer": rec["customer_id"], "return_url": _base()})
    return {"url": result["url"]}


def _verify(body, signature):
    fields = [part.strip().partition("=") for part in (signature or "").split(",")]
    stamps = [value for name, _, value in fields if name == "t"]
    if len(stamps) == 1 and stamps[0].isascii() and stamps[0].isdigit() and len(stamps[0]) <= 12:
        stamp = stamps[0]
        expected = hmac.new(os.environ["STRIPE_WEBHOOK_SECRET"].encode(),
                            stamp.encode() + b"." + body, hashlib.sha256).hexdigest()
        if abs(time.time() - int(stamp)) <= 300 and any(
                name == "v1" and value.isascii() and hmac.compare_digest(expected, value)
                for name, _, value in fields):
            return
    raise BillingError("支付回调签名无效或已过期。")


def webhook(db, body, signature):
    _require_enabled()
    _verify(body, signature)
    try:
        event = json.loads(body)
        event_id, kind, obj = event["id"], event["type"], event["data"]["object"]
        if not isinstance(event_id, str) or not isinstance(kind, str) or not isinstance(obj, dict):
            raise ValueError()
    except (KeyError, TypeError, ValueError) as exc:
        raise BillingError("支付回调格式无效。") from exc
    if kind in ("charge.dispute.created","charge.dispute.updated","charge.dispute.closed"):
        return partnerships.settlement.receive_event(db,event)
    if kind in partnerships.FINANCIAL_EVENTS:
        return partnerships.financial_event(db, event, _stripe, set(_prices().values()))
    if not (kind.startswith("customer.subscription.") or kind == "checkout.session.completed"):
        return {"ignored": True}
    existing = db.execute("SELECT 1 FROM billing_events WHERE event_id=?", (event_id,)).fetchone()
    if existing:
        return {"duplicate": True}
    customer = obj.get("customer")
    if not isinstance(customer, str):
        return {"ignored": True}
    rec = db.execute("SELECT * FROM billing_customers WHERE customer_id=?", (customer,)).fetchone()
    if not rec:
        return {"ignored": True}
    # Stripe does not guarantee event order. Read current subscriptions for this exact mapped customer.
    # A revision prevents an older in-flight reconciliation from overwriting a newer one.
    plan, _ = _subscriptions(customer)
    uid = rec["user_id"]
    with db:
        inserted = db.execute("INSERT INTO billing_events VALUES (?,?,?) ON CONFLICT(event_id) DO NOTHING",
                              (event_id, uid, int(time.time())))
        if not inserted.rowcount:
            return {"duplicate": True}
        updated = db.execute("UPDATE billing_customers SET revision=revision+1 WHERE user_id=? AND revision=?",
                             (uid, rec["revision"]))
        if not updated.rowcount:
            raise BillingError("账单状态正在同步，请重试此事件。", 503)
        if kind == "checkout.session.completed":
            db.execute("UPDATE billing_customers SET session_id=NULL,checkout_plan=NULL,checkout_key=NULL "
                       "WHERE user_id=? AND session_id=?", (uid, obj.get("id")))
        db.execute("UPDATE users SET plan=? WHERE id=?", (plan, uid))
    return {"received": True}

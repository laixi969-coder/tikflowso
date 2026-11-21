import hashlib
import hmac
import json
import os
import sqlite3
import time
import unittest
from unittest.mock import patch

import billing
import partnerships as p
import workspace as ws


class PartnershipsTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        self.addCleanup(self.db.close)
        self.db.row_factory = sqlite3.Row
        ws.init(self.db)
        billing.init(self.db)
        p.init(self.db)
        self.db.executemany("INSERT INTO users(name,email) VALUES('user',?)",
                            [(f"usr{i}@example.org",) for i in range(3)])
        self.partner = ws.get_user(self.db, 1)
        self.buyer = ws.get_user(self.db, 2)
        self.other = ws.get_user(self.db, 3)
        self.code = p.handle(self.db, self.partner, "/api/partners/code", "POST", {})["code"]
        config = {"TIKFLOWSO_AFFILIATE_BPS": "1500", "STRIPE_SECRET_KEY": "fixture",
                  "STRIPE_WEBHOOK_SECRET": "test-signing", "STRIPE_PRICE_PRO": "price_pro", "STRIPE_PRICE_TEAM": "price_team"}
        self.addCleanup(patch.stopall)
        patch.dict(os.environ, config).start()

    def test_opt_in_only_and_no_self_referral(self):
        for absent in (False, None, "true"):
            p.attribute(self.db, 2, self.code, absent)
        self.assertEqual(p.handle(self.db, self.partner, "/api/partners", "GET", {})["referred"], 0)
        with self.assertRaises(ValueError):
            p.attribute(self.db, 1, self.code, True)
        with self.assertRaises(ValueError):
            p.attribute(self.db, 2, "unknown", True)
        p.attribute(self.db, 2, self.code, True)
        self.assertEqual(p.handle(self.db, self.partner, "/api/partners", "GET", {})["referred"], 1)
        self.assertEqual(p.handle(self.db, self.partner, "/api/partners/code", "POST", {})["code"], self.code)

    def test_library_and_scope(self):
        path = "/api/partners/library"
        data = {"name": "Brand pack", "kind": "asset", "rights": "Brand contract #24",
                "url": "https://example.org/media", "product_id": "sku_23"}
        ident = p.handle(self.db, self.partner, path, "POST", data)["id"]
        self.assertEqual(p.handle(self.db, self.partner, path, "GET", {})["items"][0]["rights"], data["rights"])
        self.assertEqual(p.handle(self.db, self.other, path, "GET", {})["items"], [])
        with self.assertRaises(LookupError):
            p.handle(self.db, self.other, path, "POST", {**data, "id": ident})
        with self.assertRaises(LookupError):
            p.handle(self.db, self.other, path, "POST", {"action": "remove", "id": ident})
        with self.assertRaises(ValueError):
            p.handle(self.db, self.partner, path, "POST", {**data, "url": "file:///tmp/file"})
        p.handle(self.db, self.partner, path, "POST", {**data, "id": ident, "name": "Updated", "kind": "product"})
        p.handle(self.db, self.partner, path, "POST", {"action": "remove", "id": ident})
        self.assertEqual(p.handle(self.db, self.partner, path, "GET", {})["items"], [])

    def test_signed_financials_refund_arrives_first(self):
        p.attribute(self.db, 2, self.code, True)
        self.db.execute("UPDATE partner_referrals SET registered=100")
        self.db.execute("INSERT INTO billing_customers(user_id,create_key,customer_id) VALUES(2,'key','cus_two')")
        self.db.commit()
        charge = {"id": "ch_a", "customer": "cus_two", "currency": "usd", "livemode": False,
                  "created": 1735600000, "paid": True, "captured": True, "amount_captured": 111,
                  "amount_refunded": 55, "payment_intent": "pi_a"}
        invoice = {"id": "in_a", "customer": "cus_two", "billing_reason": "subscription_create",
                   "status": "paid", "currency": "usd", "livemode": False, "lines": {"data": [
                       {"pricing": {"price_details": {"price": "price_pro"}}}]}}
        payment = {"invoice": "in_a", "payment": {"payment_intent": "pi_a"}, "amount_paid": 111}
        refunds = [{"id": "re_a", "charge": "ch_a", "currency": "usd", "status": "succeeded", "amount": 55,
                    "created": 1735900000}]

        def stripe(path):
            if path.startswith("invoice_payments?"):
                return {"data": [payment], "has_more": False}
            if path.startswith("refunds?"):
                return {"data": refunds, "has_more": False}
            return {"charges/ch_a": charge, "invoices/in_a": invoice,
                    "payment_intents/pi_a": {"latest_charge": "ch_a"}}[path]

        def send(kind, data, live=False):
            event = {"id": "evt_" + kind, "type": kind, "livemode": live, "data": {"object": data}}
            body = json.dumps(event).encode()
            timestamp = str(int(time.time()))
            sig = hmac.new(b"test-signing", timestamp.encode() + b"." + body, hashlib.sha256).hexdigest()
            return billing.webhook(self.db, body, f"t={timestamp},v1={sig}")

        def statement(month, mode="test", user=None):
            return p.handle(self.db, user or self.partner, "/api/partners/statement", "GET", {"month": month, "mode": mode})

        with patch("billing._stripe", side_effect=stripe):
            self.assertFalse(send("charge.refunded", charge, True)["matched"])
            send("refund.updated", {"charge": "ch_a"})
            send("charge.succeeded", charge)
            send("invoice.paid", invoice)
            self.assertEqual(statement("2024-12")["totals"]["usd"], {"amount": 111, "commission": 16})
            self.assertEqual(statement("2025-01")["totals"]["usd"], {"amount": -55, "commission": -8})
            self.assertEqual(statement("2025-01", "live")["items"], [])
            self.assertEqual(statement("2024-12", user=self.other)["items"], [])
            charge["amount_refunded"] = 111
            refunds.append({"id": "re_b", "charge": "ch_a", "currency": "usd", "status": "succeeded",
                            "amount": 56, "created": 1735900500})
            send("charge.refunded", charge)
            self.assertEqual(statement("2025-01")["totals"]["usd"], {"amount": -111, "commission": -16})
            # An unrelated configured-customer invoice never accrues commissions.
            invoice["lines"]["data"][0]["pricing"]["price_details"]["price"] = "another_product"
            self.assertTrue(send("invoice.paid", invoice)["ignored"])

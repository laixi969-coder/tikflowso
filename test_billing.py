"""Exercise checkout, signature, ownership, retry, and authoritative subscription state."""
import hashlib
import hmac
import json
import os
import sqlite3
import time
import unittest
from unittest.mock import patch

import billing


class BillingTests(unittest.TestCase):
    def setUp(self):
        self.addCleanup(patch.stopall)
        patch.dict(os.environ, {"STRIPE_SECRET_KEY": "sk_test", "STRIPE_WEBHOOK_SECRET": "fixture",
                                "STRIPE_PRICE_PRO": "price_pro", "STRIPE_PRICE_TEAM": "price_team"}).start()
        self.remote = patch.object(billing, "_stripe").start()
        self.db = sqlite3.connect(":memory:")
        self.addCleanup(self.db.close)
        self.db.row_factory = sqlite3.Row
        self.db.execute("CREATE TABLE users(id INTEGER PRIMARY KEY,email,name,plan)")
        self.db.executemany("INSERT INTO users VALUES (?, 'fixture@example.org','研究员','free')", [(1,), (2,)])
        billing.init(self.db)
        self.user = self.db.execute("SELECT * FROM users WHERE id=1").fetchone()

    def event(self, event_id, customer, *, kind="customer.subscription.updated", stamp=None):
        stamp = str(int(time.time()) if stamp is None else stamp)
        body = json.dumps({"id": event_id, "type": kind, "data": {"object": {
            "id": "sub_a", "customer": customer, "metadata": {"tikflowso_user": "2"}, "status": "active"
        }}}).encode()
        signature = hmac.new(b"fixture", stamp.encode() + b"." + body, hashlib.sha256).hexdigest()
        return body, f"t={stamp},v1={signature}"

    def bind_customer(self):
        self.db.execute("INSERT INTO billing_customers(user_id,create_key,customer_id) VALUES(1,'ck','cus_a')")
        self.db.commit()

    def active(self, plan="team", status="active"):
        return {"data": [{"customer": "cus_a", "status": status,
                          "items": {"data": [{"price": {"id": "price_" + plan}}]}}]}

    def test_checkout_reuses_open_session(self):
        self.remote.side_effect = [{"id": "cus_a"}, {"data": []}, {"id": "cs_a", "url": "https://checkout.stripe.com/fixture"},
                                   {"data": []}, {"id": "cs_a", "url": "https://checkout.stripe.com/fixture", "status": "open"}]
        self.assertEqual(billing.checkout(self.db, self.user, "pro"), billing.checkout(self.db, self.user, "pro"))
        calls = self.remote.call_args_list
        self.assertEqual(calls[2].args[1]["customer"], "cus_a")
        self.assertEqual(calls[2].args[1]["line_items[0][price]"], "price_pro")
        self.assertTrue(calls[2].kwargs["key"])
        self.assertEqual(billing.status(self.db, self.user)["plan"], "free")

    def test_signed_replay_and_out_of_order(self):
        self.bind_customer()
        self.remote.side_effect = [self.active(), {"data": []}, {"data": []}]
        ev = self.event("evt_new", "cus_a")
        self.assertEqual(billing.webhook(self.db, *ev), {"received": True})
        self.assertEqual(billing.webhook(self.db, *ev), {"duplicate": True})
        self.assertEqual(self.db.execute("SELECT plan FROM users WHERE id=1").fetchone()[0], "team")
        billing.webhook(self.db, *self.event("evt_end", "cus_a", kind="customer.subscription.deleted"))
        billing.webhook(self.db, *self.event("evt_old", "cus_a", kind="customer.subscription.created"))
        self.assertEqual([r[0] for r in self.db.execute("SELECT plan FROM users ORDER BY id")], ["free", "free"])
        self.assertEqual(self.remote.call_count, 3)

    def test_simultaneous_reconciliation_retries_atomically(self):
        self.bind_customer()
        def race(*args, **kwargs):
            self.db.execute("UPDATE billing_customers SET revision=revision+1")
            self.db.commit()
            return self.active()
        self.remote.side_effect = race
        event = self.event("evt_race", "cus_a")
        with self.assertRaises(billing.BillingError) as caught:
            billing.webhook(self.db, *event)
        self.assertEqual(caught.exception.status, 503)
        self.assertEqual(self.db.execute("SELECT count(*) FROM billing_events").fetchone()[0], 0)
        self.remote.side_effect = None
        self.remote.return_value = self.active()
        self.assertEqual(billing.webhook(self.db, *event), {"received": True})

    def test_unknown_customer_cannot_claim_account_from_metadata(self):
        self.assertEqual(billing.webhook(self.db, *self.event("evt_foreign", "cus_b")), {"ignored": True})
        self.remote.assert_not_called()

    def test_stale_and_invalid_signatures(self):
        stale = self.event("evt_old", "cus_a", stamp=int(time.time()) - 400)
        for args in (stale, (b"{}", "t=1,v1=bad"), (b"changed", self.event("evt_bad", "cus_a")[1])):
            with self.assertRaises(billing.BillingError):
                billing.webhook(self.db, *args)
        self.remote.assert_not_called()

    def test_payment_failure_denies_entitlement_but_uses_portal_for_recovery(self):
        self.bind_customer()
        self.remote.return_value = self.active(status="past_due")
        billing.webhook(self.db, *self.event("evt_due", "cus_a"))
        self.assertEqual(self.db.execute("SELECT plan FROM users WHERE id=1").fetchone()[0], "free")
        with self.assertRaises(billing.BillingError) as caught:
            billing.checkout(self.db, self.user, "pro")
        self.assertEqual(caught.exception.status, 409)
        self.remote.return_value = {"url": "https://billing.stripe.com/p/session/example"}
        self.assertTrue(billing.portal(self.db, self.user)["url"].startswith("https://billing.stripe.com"))
        self.assertEqual(self.remote.call_args.args[1]["customer"], "cus_a")

    def test_disabled_has_explicit_state(self):
        with patch.dict(os.environ, {"STRIPE_SECRET_KEY": ""}):
            self.assertFalse(billing.status(self.db, self.user)["configured"])
            with self.assertRaises(billing.BillingError) as caught:
                billing.checkout(self.db, self.user, "pro")
            self.assertEqual(caught.exception.status, 503)
        self.remote.assert_not_called()


if __name__ == "__main__":
    unittest.main()

import sqlite3
import unittest

import analytics
import inspiration


class ProductVideoEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db = sqlite3.connect(":memory:")
        analytics.init(cls.db)
        cls.scope = {"source": "licensed", "market": "GB", "date": "2026-09-03", "days": 3}

        def record(kind, ident, name, day, gmv, market="GB", **fields):
            return dict(kind=kind, id=ident, name=name, market=market, date=f"2026-09-{day:02}",
                        sales=1, gmv=gmv, **fields)

        products = [record("products", str(n), "Twin" if n in (1, 21) else f"SKU {n}", 1, 100-n)
                    for n in range(1, 24)]
        videos = [record("videos", "v", "First cut", 1, 6, product_id="21"),
                  record("videos", "v", "Final cut", 3, 300, product_id="22"),
                  record("videos", "older", "Outside period", 4, 20, product_id="21"),
                  record("videos", "other-market", "Other market", 2, 20, market="US", product_id="21")]
        analytics.import_rows(cls.db, products + videos, "licensed", shared=True)
        analytics.import_rows(cls.db, [record("videos", "other-source", "Other source", 2, 20, product_id="21")],
                              "second-provider", shared=True)

    @classmethod
    def tearDownClass(cls):
        cls.db.close()

    def test_explicit_product_outside_leaders_and_ambiguous_name(self):
        result = inspiration.board(self.db, {**self.scope, "product_id": "21", "subject": "SKU 8"})
        self.assertNotIn("21", [r["id"] for r in result["products"]])
        self.assertEqual((result["product"]["id"], result["subject"]), ("21", "Twin"))
        self.assertTrue(all(c["product"]["id"] == "21" for c in result["cards"]))
        ambiguous = inspiration.board(self.db, {**self.scope, "subject": "Twin"})
        self.assertIsNone(ambiguous["product"])
        self.assertEqual(ambiguous["linked_videos"], [])
        unique = inspiration.board(self.db, {**self.scope, "subject": "SKU 22"})
        self.assertEqual(unique["product"]["id"], "22")
        for overrides in ({"product_id": "missing"}, {"product_id": "21", "market": "US"},
                          {"product_id": "21", "days": 1}, {"product_id": "21", "source": "second-provider"}):
            with self.subTest(overrides=overrides), self.assertRaises(LookupError):
                inspiration.board(self.db, {**self.scope, **overrides})

    def test_links_follow_video_days_in_both_directions_and_leave_attribution_open(self):
        for ident, day in (("21", "2026-09-01"), ("22", "2026-09-03")):
            refs = inspiration.board(self.db, {**self.scope, "product_id": ident})["linked_videos"]
            self.assertEqual([(r["id"], r["name"], r["linked_days"], r["first_seen"], r["last_seen"]) for r in refs],
                             [("v", "Final cut", 1, day, day)])
            self.assertFalse({"gmv", "sales", "product_gmv", "product_sales"}.intersection(refs[0]))
            detail = analytics.handle(self.db, "/api/detail", {**self.scope, "kind": "products", "id": ident})
            self.assertEqual([(r["id"], r["first_seen"]) for r in detail["related"]], [("v", day)])
        detail = analytics.handle(self.db, "/api/detail", {**self.scope, "kind": "videos", "id": "v"})
        self.assertEqual(detail["item"]["gmv"], 306)
        self.assertEqual({r["id"]: r["linked_days"] for r in detail["related"]}, {"21": 1, "22": 1})
        early = inspiration.board(self.db, {**self.scope, "days": 1, "date": "2026-09-01", "product_id": "22"})
        self.assertEqual(early["linked_videos"], [])

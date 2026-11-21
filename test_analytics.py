import sqlite3
import unittest

import analytics


class SnapshotAnalyticsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db = sqlite3.connect(":memory:")
        analytics.init(cls.db)

    @classmethod
    def tearDownClass(cls):
        cls.db.close()

    def sample(self, ident, day, gmv, **attrs):
        return {"kind":"products", "market":"US", "name":ident, "id":ident,
                "date":f"2026-10-{day:02}", "gmv":gmv, "sales":1, **attrs}

    def query(self, end, source, **params):
        return analytics.handle(self.db, "/api/"+end, {"source":source, **params})

    def test_idempotent_import_revision_and_rollback(self):
        source = "warehouse"
        row = self.sample("one",2,"13.34")
        analytics.import_rows(self.db,[row],source)
        analytics.import_rows(self.db,[row],source)
        self.assertEqual(self.query("overview",source)["metrics"]["gmv"],13.34)
        with self.assertRaisesRegex(ValueError, "第 2 行"):
            analytics.import_rows(self.db,[{**row,"gmv":"3"},{**row,"sales":-1}],source)
        self.assertEqual(self.query("overview",source)["metrics"]["gmv"],13.34)
        analytics.import_rows(self.db,[{**row,"gmv":"3"}],source)
        self.assertEqual(self.query("overview",source)["metrics"]["gmv"],3)
        with self.assertRaises(ValueError):
            analytics.import_rows(self.db,[row],"demo")

    def test_orders_refunded_units_and_estimated_gmv(self):
        src="optional-metrics"
        first=self.sample("item",1,5,orders=0,refund_units=1,gmv_estimated=False)
        second=self.sample("item",2,7,orders=2,gmv_estimated="true")
        analytics.import_rows(self.db,[first,second],src)
        result=self.query("detail",src,days=2,id="item")["item"]
        self.assertEqual((result["sales"],result["orders"],result["refund_units"],result["gmv_estimated"]),(2,2,None,1))
        self.assertTrue(self.query("meta",src,days=2)["includes_estimates"])
        analytics.import_rows(self.db,[{**second,"gmv_estimated":None}],src)
        self.assertIsNone(self.query("detail",src,days=2,id="item")["item"]["gmv_estimated"])
        with self.assertRaises(ValueError):analytics.import_rows(self.db,[{**second,"gmv_estimated":"maybe"}],src)

    def test_counter_conversion_with_backfill_gap_and_reset(self):
        def row(day,gmv,sales):
            return {"market":"US","kind":"products","id":"a","name":"A","date":f"2026-11-{day:02}",
                    "cumulative_gmv":gmv,"cumulative_sales":sales}
        batch=[row(2,"3.75",4),row(1,1,1),row(4,10,8),row(5,1,1),row(6,1,1),row(2,"4.25",3)]
        result=analytics.daily_from_counters(batch)
        self.assertEqual([(r["gmv"],r["sales"]) for r in result["rows"]],[("3.25",2),("0.00",0)])
        self.assertEqual([r["reason"] for r in result["skipped"]],["baseline","gap","counter_decrease"])
        analytics.import_rows(self.db,result["rows"],"counter-test")
        self.assertEqual(self.query("overview","counter-test",days=7)["metrics"]["gmv"],3.25)
        with self.assertRaisesRegex(ValueError,"来源"):analytics.daily_from_counters([batch[0],{**batch[1],"source":"other"}])

    def test_comparable_period_rank_and_nullable_metrics(self):
        source = "warehouse2"
        rows = [self.sample("same",1,50),self.sample("same",2,75),
                self.sample("same2",2,75),self.sample("other",2,100,market="GB"),
                self.sample("store",2,1000,kind="shops")]
        analytics.import_rows(self.db,rows,source)
        scope = {"date":"2026-10-02","days":"1"}
        overview = self.query("overview",source,**scope)
        self.assertEqual(overview["metrics"],{"gmv":150,"sales":2,"views":None,"creators":None})
        self.assertEqual(overview["changes"]["gmv"],200)
        ranked = self.query("rankings",source,**scope)["items"]
        self.assertEqual([(r["id"],r["growth"]) for r in ranked],[("same",50),("same2",None)])
        self.assertEqual(self.query("rankings",source,q="same",match="exact",**scope)["total"],1)
        self.assertEqual(self.query("rankings",source,q="same",**scope)["total"],2)
        self.assertIsNone(self.query("overview",source,days="2")["changes"]["gmv"])

    def test_date_grain_attributes_and_stock_delta(self):
        source = "historical"
        rows = [self.sample("one",1,12,category="old"),self.sample("one",2,24,category="new"),
                self.sample("creator",1,2,kind="creators",followers=10),
                self.sample("creator",2,2,kind="creators",followers=8)]
        analytics.import_rows(self.db,reversed(rows),source)
        self.assertEqual(self.query("rankings",source,date="2026-10-01")["items"][0]["category"],"old")
        self.assertEqual(self.query("rankings",source,kind="creators",days="1")["items"][0]["follower_growth"],-2)
        self.assertEqual([(r["name"],r["gmv"]) for r in self.query("trends",source)["items"]],
                         [("new",24),("old",12)])

    def test_breakout_uses_data_instead_of_source_label(self):
        result = self.query("rankings","demo",kind="creators",segment="breakout")["items"]
        self.assertTrue(result)
        self.assertEqual(result,sorted(result,key=lambda row:-row["growth"]))
        self.assertTrue(all(row["followers"]<200000 and row["growth"]>=15 and row["sales"]>=20 for row in result))

    def test_demo_date_source_and_relationships(self):
        overview = self.query("overview","demo")
        self.assertEqual(len(overview["trend"]),7)
        self.assertEqual(set(overview["rankings"]),set(analytics.KINDS))
        self.assertAlmostEqual(sum(r["gmv"] for r in overview["trend"]),overview["metrics"]["gmv"])
        product = self.query("detail","demo",id="p01")
        self.assertEqual({r["kind"] for r in product["related"]},{"shops","creators","videos","lives"})
        self.assertEqual(self.query("rankings","demo",market="MX")["total"],0)
        with self.assertRaises(LookupError):
            self.query("detail","demo",id="missing")
        with self.assertRaises(ValueError):
            self.query("rankings","demo",sort="invalid")

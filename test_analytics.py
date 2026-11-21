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

    def test_board_category_uses_daily_facts_and_sales_activity(self):
        source="board-categories"
        rows=[self.sample("p",1,12,sales=3,category="A"), self.sample("p",2,24,sales=2,category="B"),
              self.sample("p2",2,0,sales=0,category="A"), self.sample("s",2,8,kind="shops",sales=2,category="A")]
        analytics.import_rows(self.db,rows,source)
        args={"date":"2026-10-02","days":2,"board":"1"}
        result=self.query("overview",source,category="A",**args)
        self.assertEqual((result["metrics"]["gmv"],result["metrics"]["sales"]),(12,3))
        self.assertEqual(result["activity"],{"active_products":1,"active_shops":1,"avg_price":4.0})
        self.assertEqual(sum(day["gmv"] or 0 for day in result["trend"]),12)
        self.assertEqual(result["boards"],self.query("overview",source,**args)["boards"])
        missing=self.query("overview",source,category="unknown",**args)
        self.assertTrue(all(value is None for value in missing["activity"].values()))

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

    def test_live_products_use_explicit_daily_links_and_similar_rooms_match_scope(self):
        source = "live-analysis"
        def live(ident, day, **fields):
            return self.sample(ident,day,90,kind="lives",category="A",**fields)
        rows = [
            self.sample("p1",2,999), self.sample("unlinked",2,999,category="A"),
            live("session",1,product_id="p1",
                 profile={"live_products":[{"id":"p1","sales":1,"gmv":0.15},{"id":"p2","sales":0,"gmv":0}]}),
            live("session",2,product_id="p2",profile={"live_products":[{"id":"p1","sales":2,"gmv":0.10}]}),
            live("other",2), live("out-of-market",2,market="GB"), live("past",1),
            self.sample("different",2,1000,kind="lives",category="B"),
            live("session",3,product_id="future"),
        ]
        analytics.import_rows(self.db,rows,source)
        scope = {"kind":"lives","id":"session","date":"2026-10-02"}
        result = self.query("detail",source,days=2,**scope)["live_analysis"]
        links = {p["id"]:p for p in result["products"]}
        self.assertEqual(set(links),{"p1","p2"})
        self.assertEqual((links["p1"]["name"],links["p1"]["sales"],links["p1"]["gmv"],links["p1"]["days"]),("p1",3,0.25,2))
        self.assertEqual((links["p2"]["name"],links["p2"]["sales"],links["p2"]["gmv"],links["p2"]["days"]),(None,None,None,2))
        later = self.query("detail",source,days=1,**scope)["live_analysis"]
        self.assertEqual([s["id"] for s in later["similar"]],["other"])
        earlier = self.query("detail",source,kind="lives",id="session",date="2026-10-01",days=1)["live_analysis"]
        p2 = next(p for p in earlier["products"] if p["id"]=="p2")
        self.assertEqual((p2["sales"],p2["gmv"]),(0,0))
        with self.assertRaisesRegex(ValueError,"唯一"):
            analytics.import_rows(self.db,[live("bad",2,profile={"live_products":[{"id":"x"},{"id":"x"}]})],source)

    def test_board_preview_uses_reported_session_totals_and_timezone(self):
        source = "room-picker"
        session = {"start_at":"2026-10-01T22:30:00-04:00","end_at":"2026-10-01T23:00:00-04:00",
                   "gmv":34.50,"enter_count":0,"online_viewers":[{"time":"2026-10-02T02:42:00Z","value":0}],
                   "products":[{"id":"p1","sales":3},{"id":"p2","sales":10},{"id":"p3","sales":2},{"id":"p0","sales":3}]}
        rows = [self.sample("r1",1,90,kind="lives"),self.sample("r1",2,80,kind="lives",category="A",
                views=999,creator_id="c",profile={"live_session":session}),self.sample("r2",2,10,kind="lives",category="A",views=123),
                self.sample("c",2,18,kind="creators"),self.sample("p1",2,80),self.sample("p2",2,80)]
        analytics.import_rows(self.db,rows,source)
        def board(**kwargs):
            return self.query("overview",source,days=2,date="2026-10-02",live_only="1",**kwargs)["live_preview"]
        result=board()
        self.assertEqual([(r["id"],r["period_gmv"]) for r in result["rooms"]],[("r1",170),("r2",10)])
        room=result["room"]
        self.assertEqual((room["gmv"],room["enter_count"],room["series"][0]["value"]),(34.5,0,0))
        self.assertEqual(room["start_at"],"2026-10-02T02:30:00.000000+00:00")
        self.assertEqual([p["id"] for p in room["products"]],["p2","p0","p1"])
        self.assertIsNone(room["products"][1]["name"])
        self.assertEqual((room["similar"][0]["id"],room["creator"]["id"]),("r2","c"))
        unknown=board(room="r2")["room"]
        self.assertEqual([unknown[k] for k in ("enter_count","gmv","start_at","end_at","products","series")],[None,None,None,None,[],[]])
        self.assertEqual(board(market="GB"),{"rooms":[],"room":None})
        for invalid in ({"start_at":"2026-10-02T12:00"},{"start_at":session["end_at"],"end_at":session["start_at"]},
                        {"enter_count":0.5},{"online_viewers":[{"time":"2026-09-01T01:00Z","value":2}]}):
            with self.subTest(invalid=invalid),self.assertRaises(ValueError):
                analytics.profile_json({"live_session":{**session,**invalid}},"lives")

    def test_legacy_demo_session_refresh_only_changes_bundled_profiles(self):
        db=sqlite3.connect(":memory:")
        self.addCleanup(db.close)
        db.executescript(analytics.SCHEMA)
        row=self.sample("l01",1,30,kind="lives",sales=3,views=12,product_id="p01")
        analytics.write_batch(db,[row],"demo","Demo")
        analytics.import_rows(db,[row,{**row,"market":"CN"}],"licensed")
        db.execute("CREATE TRIGGER audit_snapshot_update AFTER UPDATE ON analytics_daily BEGIN SELECT RAISE(ABORT,'unexpected audit update'); END")
        analytics.init(db)
        select="SELECT profile_json FROM analytics_daily WHERE source=? AND market='US' AND kind='lives' AND id='l01'"
        enriched=db.execute(select,("demo",)).fetchone()[0]
        self.assertIn('"live_session"',enriched)
        self.assertIsNone(db.execute(select,("licensed",)).fetchone()[0])
        self.assertEqual(db.execute("SELECT COUNT(*) FROM snapshot_revisions").fetchone()[0],0)
        self.assertIsNotNone(db.execute("SELECT sql FROM sqlite_master WHERE name='audit_snapshot_update'").fetchone())
        count_cn="SELECT COUNT(*) FROM analytics_daily WHERE source='demo' AND market='CN'"
        count=db.execute(count_cn).fetchone()[0]
        self.assertGreater(count,0)
        self.assertIsNone(db.execute("SELECT profile_json FROM analytics_daily WHERE source='licensed' AND market='CN'").fetchone()[0])
        analytics.init(db)
        self.assertEqual(db.execute(select,("demo",)).fetchone()[0],enriched)
        self.assertEqual(db.execute(count_cn).fetchone()[0],count)

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

    def test_catalog_drills_into_category_and_excludes_similar_names(self):
        source = "nested-categories"
        categories = {"a":"Goods > Tea > Black", "b":"Goods > Tea > Green", "c":"Goods",
                      "d":"Goods > Teak", "e":"Goodsware > Tea"}
        rows = [self.sample(k, 1, 12, category=v) for k,v in categories.items()]
        rows.append(self.sample("s", 1, 12, kind="shops", category="Shop only"))
        analytics.import_rows(self.db, rows, source)
        def ids(category):
            return {r["id"] for r in self.query("rankings", source, category=category)["items"]}
        self.assertEqual(ids("Goods"), {"a","b","c","d"})
        self.assertEqual(ids("Goods > Tea"), {"a","b"})
        self.assertEqual(ids("Goods > Tea > Black"), {"a"})
        self.assertEqual(ids("Good"), set())
        meta = self.query("meta", source)
        self.assertEqual(set(meta["categories_by_kind"]["products"]), set(categories.values()))
        self.assertEqual(meta["categories_by_kind"]["shops"], ["Shop only"])

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

    def test_mainland_china_market_and_source_coverage(self):
        china = {"code":"CN", "name":"中国大陆", "currency":"CNY"}
        self.assertIn(china, self.query("meta","demo")["markets"])
        board = self.query("overview","demo",market="CN",days=75,board="1")
        self.assertTrue(all(board["rankings"][kind] for kind in analytics.KINDS))
        market = next(m for m in self.query("markets","demo",days=75)["items"] if m["market"]=="CN")
        self.assertEqual((market["currency"], market["covered_days"], market["gmv"]),
                         ("CNY", 75, board["metrics"]["gmv"]))
        room = self.query("overview","demo",market="CN",days=1,live_only="1",
                          room=f"l{len(analytics.CN_PRODUCTS):02}")["live_preview"]["room"]
        self.assertEqual(len(room["products"]),3)
        self.assertTrue(all(product["name"] for product in room["products"]))

        source = "domestic-import"
        row = self.sample("p01",1,12)
        analytics.import_rows(self.db,[row],source)
        self.assertNotIn(china,self.query("meta",source)["markets"])
        analytics.import_rows(self.db,[{**row,"market":"cn","name":"授权样品","gmv":"19.80","sales":2}],source)
        self.assertIn(china,self.query("meta",source)["markets"])
        record = self.query("detail",source,market="CN",id="p01")
        self.assertEqual((record["currency"], record["item"]["name"], record["item"]["gmv"]),
                         ("CNY", "授权样品", 19.8))
        self.assertEqual(self.query("detail",source,market="US",id="p01")["item"]["gmv"],12)

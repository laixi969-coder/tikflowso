"""Cross-midnight research events retain the run and the item that actually qualified."""
from contextlib import closing
from datetime import datetime, timezone
import sqlite3
import unittest

import research_usage


class ResearchMidnightTests(unittest.TestCase):
    def test_reopening_list_or_viewing_a_different_item_after_midnight(self):
        monday = int(datetime(2026,11,16,tzinfo=timezone.utc).timestamp())
        scope = {"source":"pilot","market":"US","date":"2026-11-11","days":7}
        with closing(sqlite3.connect(":memory:")) as db:
            research_usage.init(db)
            def log(owner, seconds, action, item=""):
                research_usage.record(db,owner,scope,action,item,monday+seconds)
            for owner,action in ((1,"save"),(2,"export"),(3,"save")):
                log(owner,-20,"list")
                log(owner,-10,"detail","A")
                log(owner,1,"list")
                if owner!=2:log(owner,2,"detail","B")
                log(owner,3,action,"missing" if owner==3 else "A")
            sunday = research_usage.weekly(db,"2026-11-15")["items"][1]
            self.assertEqual((sunday["first_starts"],sunday["within_300s"]),(3,2))
            current = research_usage.weekly(db,"2026-11-16")["items"][1]
            self.assertEqual((current["first_starts"],current["first_completed"]),(0,2))

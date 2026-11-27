from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

import daily_references as daily
import privacy
import workspace


def candidates(name, count=30):
    return [dict(subject=name, title=f'{name} review {i}', url=f'https://www.dailymotion.com/video/x{i}',
                 published='2026-11-10', author='Reviewer', platform='Dailymotion', match='name', score=100-i)
            for i in range(count)]


class DailyInspirationTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.path = Path(temp.name) / 'test.db'
        with closing(sqlite3.connect(self.path)) as db, db:
            daily.init(db)
        self.now = datetime(2026, 11, 22, 7, 59, tzinfo=timezone.utc)
        self.params = {'subject': 'mechanical keyboard', 'tz': 'America/Los_Angeles'}
        self.scope = patch.object(daily.analytics, 'scope_for', side_effect=lambda db, p: {
            'source': p.get('source', 'demo'), 'market': p.get('market', 'US')})
        self.scope.start()
        self.addCleanup(self.scope.stop)

    def get(self, params, now=None):
        db = sqlite3.connect(self.path)
        try:
            return daily.edition(db, params, now or self.now)
        finally:
            db.close()

    def test_first_open_concurrent_then_midnight_and_scoped_editions(self):
        rows = candidates('mechanical keyboard')
        with patch.object(daily, 'lookup', return_value=(rows + rows, False)) as fetch:
            with ThreadPoolExecutor(2) as pool:
                first, reopened = pool.map(self.get, [self.params, self.params])
            self.assertEqual(first, reopened)
            self.assertEqual(fetch.call_count, 1)
            self.assertEqual(first['day'], '2026-11-21')
            self.assertEqual(len(first['items']), 12)
            tomorrow = self.get(self.params, self.now + timedelta(minutes=1))
            self.assertEqual(tomorrow['day'], '2026-11-22')
            self.assertTrue({r['url'] for r in first['items']}.isdisjoint(r['url'] for r in tomorrow['items']))
            self.get({**self.params, 'source': 'own-catalog', 'external_search': '1'})
            self.assertEqual(fetch.call_count, 3)

    def test_commercial_source_never_searches_catalog_or_product_names_automatically(self):
        source = {'source': 'own-catalog'}
        with patch.object(daily.analytics, 'ranking_page') as rank, patch.object(daily, 'lookup') as search:
            for params in (source, {**source, 'external_search': '1'}, {**source, 'subject': 'internal sku'}):
                self.assertFalse(self.get(params)['external_search_enabled'])
            rank.assert_not_called()
            search.assert_not_called()
            search.return_value = ([], False)
            self.get({**source, 'subject': 'desk lamp', 'external_search': '1'})
            search.assert_called_once_with('desk lamp')
            rank.assert_not_called()

    def test_explicit_commercial_search_is_ephemeral_and_safe_to_erase(self):
        with closing(sqlite3.connect(self.path)) as db, db:
            db.executescript(daily.analytics.SCHEMA)
            workspace.init(db)
            db.execute("INSERT INTO users(id,name,email) VALUES(101,'Store','owner@example.invalid')")
            product = dict(market='US', kind='products', id='private', name='Unreleased model Z',
                           date='2026-11-18', sales=1, gmv='3')
            daily.analytics.import_rows(db, [product], 'ws-101-pilot', owner=101)
        term = product['name']
        params = {'source': 'ws-101-pilot', 'subject': term, 'external_search': '1'}
        with patch.object(daily, 'lookup', side_effect=[(candidates(term, 1), True), ([], False)]) as fetch:
            first = self.get(params)
            self.assertEqual([r['subject'] for r in first['items']], [term])
            self.assertTrue(first['incomplete_search'])
            self.assertEqual(self.get(params)['items'], [])
            self.assertEqual(fetch.call_count, 2)
        with closing(sqlite3.connect(self.path)) as db, db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM demo_inspiration_editions").fetchone()[0], 0)
            privacy.erase(db, 101, 'owner@example.invalid')
            self.assertEqual(db.execute("SELECT COUNT(*) FROM analytics_daily WHERE name=?", (term,)).fetchone()[0], 0)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM demo_inspiration_editions").fetchone()[0], 0)

    def test_upgrade_clears_unclassified_legacy_cache_once_and_preserves_business_rows(self):
        with closing(sqlite3.connect(self.path)) as db, db:
            db.executescript(daily.analytics.SCHEMA)
            product = dict(market='US', kind='products', id='sku', name='Store product',
                           date='2026-11-18', sales=1, gmv='3')
            daily.analytics.import_rows(db, [product], 'existing', shared=True)
            db.execute("DROP TABLE demo_inspiration_editions")
            db.execute("""CREATE TABLE inspiration_editions(scope TEXT, day TEXT, checked INTEGER,
                payload TEXT, PRIMARY KEY(scope,day))""")
            db.execute("INSERT INTO inspiration_editions VALUES('opaque hash','2026-11-21',0,'private search')")
            daily.init(db)
            self.assertIsNone(db.execute("SELECT 1 FROM sqlite_master WHERE name='inspiration_editions'").fetchone())
            self.assertEqual(db.execute("SELECT COUNT(*) FROM demo_inspiration_editions").fetchone()[0], 0)
            self.assertEqual(db.execute("SELECT name FROM analytics_daily WHERE source='existing'").fetchone()[0], product['name'])
        with patch.object(daily, 'lookup', return_value=(candidates('Desk lamp'), False)) as fetch:
            first = self.get({'subject': 'Desk lamp'})
            with closing(sqlite3.connect(self.path)) as db, db:
                daily.init(db)
            self.assertEqual(self.get({'subject': 'Desk lamp'}), first)
            fetch.assert_called_once_with('Desk lamp')

    def test_market_uses_real_catalog_and_search_failures_can_recover(self):
        ranked = [{'name': 'Climbing shoes'}, {'name': 'Bike lights'}]
        with patch.object(daily.analytics, 'ranking_page', return_value={'items': ranked}), patch.object(daily, 'lookup') as fetch:
            def partial(name):
                return (candidates(name, 2), False) if name == 'Bike lights' else ([], True)
            fetch.side_effect = partial
            page = self.get({})
            self.assertEqual({r['subject'] for r in page['items']}, {'Bike lights'})
            self.assertTrue(page['incomplete_search'])
            self.assertEqual({c.args[0] for c in fetch.call_args_list}, {p['name'] for p in ranked})
            with closing(sqlite3.connect(self.path)) as db, db:
                db.execute('UPDATE demo_inspiration_editions SET checked=0')
            fetch.side_effect = lambda name: (candidates(name), False)
            recovered = self.get({})
            self.assertEqual(len(recovered['items']), 12)
            self.assertFalse(recovered['incomplete_search'])

    def test_arbitrary_translated_name_requires_product_and_video_context(self):
        def provider(url, params):
            if 'mymemory' in url:
                return {'responseStatus': 200, 'responseData': {'translatedText': 'Mechanical keyboard'}}
            titles = ['Mechanical keyboard switch comparison', 'Running shoe review', 'Mechanical keyboard song']
            return {'list': [dict(id=f'x{i}', title=title, duration=45, created_time=1800000)
                             for i, title in enumerate(titles)]}
        with patch.object(daily, 'get_json', side_effect=provider):
            rows, error = daily.lookup('机械键盘')
        self.assertFalse(error)
        self.assertEqual([r['title'] for r in daily.select(rows, set())], ['Mechanical keyboard switch comparison'])
        self.assertEqual(rows[0]['match'], 'related')

    def test_empty_catalog_has_no_default_products(self):
        with patch.object(daily.analytics, 'ranking_page', return_value={'items': []}), patch.object(daily, 'lookup') as fetch:
            self.assertEqual(self.get({})['items'], [])
            fetch.assert_not_called()

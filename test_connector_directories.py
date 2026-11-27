from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event
from types import SimpleNamespace
from unittest import TestCase, mock

from connectors import delivery, dlt_supplier, tiktok_shop


class ConnectorDirectoryTests(TestCase):
    def setUp(self):
        tmp = TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.directory = Path(tmp.name) / "deliveries"
        self.day = "2025-03-08"
        shop_config = {"source": "seller", "market": "US", "shop_id": "100", "timezone": "UTC",
                       "start_date": self.day}
        self.shop = SimpleNamespace(config=shop_config, identity=shop_config,
                                    authorized_shop=lambda: "local-cipher", day=lambda day, cipher: [])
        self.supplier_config = {"source": "supplier", "market": "US", "currency": "USD",
                                "url": "https://supplier.example.invalid/products",
                                "initial_since": "2025-03-08T00:00:00Z"}
        self.updates = self.enterContext(mock.patch.object(dlt_supplier, "updates", return_value=[]))

    def collect_shop(self):
        return tiktok_shop.sync(self.shop, self.directory, self.day, self.day)

    def collect_supplier(self):
        return dlt_supplier.sync(self.supplier_config, self.directory)

    def test_shop_empty_day_reserves_directory(self):
        self.assertEqual(self.collect_shop()["empty"], 1)
        with self.assertRaisesRegex(ValueError, "独立目录"):
            self.collect_supplier()
        self.updates.assert_not_called()
        self.assertFalse((self.directory / ".supplier.sqlite3").exists())

    def test_supplier_empty_stream_reserves_directory(self):
        self.assertEqual(self.collect_supplier()["changed"], 0)
        with self.assertRaisesRegex(ValueError, "独立目录"):
            self.collect_shop()
        self.assertFalse((self.directory / ".tiktok-shop.json").exists())

    def test_concurrent_first_collectors_check_ownership_inside_same_lock(self):
        shop_entered, supplier_attempted, release_shop = Event(), Event(), Event()
        flock = delivery.fcntl.flock

        def pause_before_shop_checkpoint():
            shop_entered.set()
            if not release_shop.wait(5):
                raise TimeoutError("test collector never released")
            return "local-cipher"

        def trace_lock(handle, flags):
            if shop_entered.is_set():
                supplier_attempted.set()
            return flock(handle, flags)

        self.shop.authorized_shop = pause_before_shop_checkpoint
        with mock.patch.object(delivery.fcntl, "flock", side_effect=trace_lock), ThreadPoolExecutor(2) as pool:
            first = pool.submit(self.collect_shop)
            try:
                self.assertTrue(shop_entered.wait(5))
                self.assertFalse((self.directory / ".tiktok-shop.json").exists())
                second = pool.submit(self.collect_supplier)
                self.assertTrue(supplier_attempted.wait(5))
            finally:
                release_shop.set()
            self.assertEqual(first.result(timeout=5)["empty"], 1)
            with self.assertRaisesRegex(ValueError, "独立目录"):
                second.result(timeout=5)
        self.updates.assert_not_called()

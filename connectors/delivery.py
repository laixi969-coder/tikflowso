"""Coordinate collectors that publish daily files in one feed directory."""
from contextlib import contextmanager
import fcntl
from pathlib import Path


@contextmanager
def delivery_lock(directory, connector):
    other_marker = {"tiktok_shop": ".supplier.sqlite3", "dlt_supplier": ".tiktok-shop.json"}[connector]
    directory = Path(directory)
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    with (directory / ".collector.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if (directory / other_marker).exists():
            raise ValueError("此交付目录已绑定其他采集器，请选择独立目录")
        yield

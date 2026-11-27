"""Compare independent merchant daily totals to the current product snapshots."""
import csv
from datetime import date, timedelta
from hashlib import sha256
from io import StringIO
import re

import analytics


FIELDS = ("source", "market", "date", "shop_scope", "product_rows", "sales", "gmv")


def init(db):
    db.execute("""CREATE TABLE IF NOT EXISTS source_baselines(
        revision INTEGER PRIMARY KEY, source TEXT NOT NULL REFERENCES analytics_sources(id) ON DELETE CASCADE,
        market TEXT NOT NULL, day TEXT NOT NULL, shop_scope TEXT NOT NULL, product_rows INTEGER NOT NULL,
        sales TEXT NOT NULL, gmv_units TEXT NOT NULL, file_sha256 TEXT NOT NULL)""")
    db.execute("""CREATE INDEX IF NOT EXISTS source_baseline_day
        ON source_baselines(source,market,day,revision DESC)""")


def daily_total(value, field):
    raw = value.strip()
    money = field == "gmv"
    if not re.fullmatch(r"[0-9]+(?:\.[0-9]{1,2})?" if money else r"[0-9]+", raw):
        raise ValueError(f"{field} 应为非负整数或相应精度的本币金额")
    whole, _, fraction = raw.partition(".")
    total = int(whole) * 100 + int(fraction.ljust(2, "0")) if money else int(whole)
    if field == "product_rows" and total > 2**63 - 1:
        raise ValueError("商品行数超出数据库可容纳的行数")
    return total


def read_csv(content):
    reader = csv.DictReader(StringIO(content.decode("utf-8-sig"), newline=""), strict=True)
    if sorted(reader.fieldnames or []) != sorted(FIELDS):
        raise ValueError("CSV 表头必须包含 " + ", ".join(FIELDS))
    days = {}
    for row in reader:
        if None in row or any(value is None for value in row.values()):
            raise ValueError(f"CSV 第 {reader.line_num} 行列数无效")
        source, market, day, label = (row[key].strip() for key in FIELDS[:4])
        market = market.upper()
        try:
            analytics.iso_day(day)
            if market not in analytics.MARKETS or not 1 <= len(label) <= 160 or source == "demo":
                raise ValueError("市场、店铺覆盖说明或商业来源无效")
            rows, sales, units = (daily_total(row[key], key) for key in FIELDS[4:])
            if rows == 0 and (sales or units):
                raise ValueError("零行基准的销量和成交额必须为零")
            key = (source, market, day)
            if key in days:
                raise ValueError("同一来源、市场和统计日只能有一条独立基准")
            # A whole market can exceed SQLite's 64-bit sum even when every SKU fits.
            days[key] = (label, rows, str(sales), str(units))
        except ValueError as exc:
            raise ValueError(f"CSV 第 {reader.line_num} 行：{exc}") from None
    if not days:
        raise ValueError("CSV 缺少基准行")
    return days


def load_file(db, content, revise=False):
    """Atomically append new baselines; an explicit revision preserves the original."""
    days = read_csv(content)
    digest = sha256(content).hexdigest()
    added = 0
    with db:
        db.execute("BEGIN IMMEDIATE")
        init(db)
        for key, values in days.items():
            if not db.execute("SELECT 1 FROM analytics_sources WHERE id=?", (key[0],)).fetchone():
                raise ValueError(f"来源 {key[0]} 尚未建立，请先导入该来源的授权快照")
            previous = db.execute("""SELECT shop_scope,product_rows,sales,gmv_units FROM source_baselines
                WHERE source=? AND market=? AND day=? ORDER BY revision DESC LIMIT 1""", key).fetchone()
            if previous and tuple(previous) == values:
                continue
            if previous and not revise:
                raise ValueError(f"{' / '.join(key)} 已有不同基准。核实商户修订后使用 --revise")
            db.execute("""INSERT INTO source_baselines(source,market,day,shop_scope,product_rows,sales,
                gmv_units,file_sha256) VALUES(?,?,?,?,?,?,?,?)""", (*key, *values, digest))
            added += 1
    return {"file_sha256": digest, "added": added, "unchanged": len(days) - added}


def metrics(row):
    count, sales, cents = row
    result = {"product_rows": count, "sales": sales, "gmv": f"{cents // 100}.{cents % 100:02}"}
    # JSON numbers beyond this limit lose integer precision in the browser.
    if max(sales, count) >= 2**53:
        result["display_counts"] = [str(count), str(sales)]
    return result


def actual_totals(db, args):
    scope = "FROM analytics_daily WHERE source=? AND market=? AND date BETWEEN ? AND ? AND kind='products'"
    return {day: (count, sales, units) for day, count, sales, units in analytics.sum_rows(db,
        f"SELECT date,COUNT(*),SUM(sales),SUM(gmv_units) {scope} GROUP BY date", args)}


def report(db, source, market, since, until):
    # Ranking queries validate their cutoff and can derive a start date before the earliest input year.
    start, end = date.fromisoformat(since), date.fromisoformat(until)
    length = (end - start).days + 1
    if since != start.isoformat() or until != end.isoformat():
        raise ValueError("日期须为 YYYY-MM-DD")
    if not 1 <= length <= 366 or market not in analytics.MARKETS:
        raise ValueError("请输入有效市场及 1–366 天的窗口")
    if not db.execute("SELECT 1 FROM analytics_sources WHERE id=?", (source,)).fetchone():
        raise ValueError("来源不存在")
    args = (source, market, since, until)
    expected = {}
    if db.execute("SELECT 1 FROM sqlite_master WHERE name='source_baselines' AND type='table'").fetchone():
        for day, label, count, sales, units, digest in db.execute("""SELECT day,shop_scope,product_rows,
            sales,gmv_units,file_sha256 FROM source_baselines b WHERE source=? AND market=? AND day BETWEEN ? AND ?
            AND revision=(SELECT MAX(revision) FROM source_baselines
                          WHERE source=b.source AND market=b.market AND day=b.day)""", args):
            expected[day] = (label, (count, int(sales), int(units)), digest)
    actual = actual_totals(db, args)
    dates = []
    counts = dict.fromkeys(("matched", "missing", "mismatch", "unverified"), 0)
    for offset in range(length):
        day = (start + timedelta(days=offset)).isoformat()
        recorded = actual.get(day)
        label, control, digest = expected.get(day, (None, None, None))
        if control is None:
            status = "unverified"
        elif recorded is None and control[0] > 0:
            status = "missing"
        elif (recorded or (0, 0, 0)) == control:
            status = "matched"
        else:
            status = "mismatch"
        counts[status] += 1
        dates.append({"date": day, "status": status, "shop_scope": label, "file_sha256": digest,
                      "actual": metrics(recorded) if recorded else None,
                      "expected": metrics(control) if control else None})
    return {"source": source, "market": market, "currency": analytics.MARKETS[market][1],
            "since": since, "until": until, "counts": counts, "days": dates,
            "matched": counts["matched"] == length}

"""Collect an authorized supplier's RFC3339 update stream into a TikFlowSo feed directory."""

import argparse
import json
import os
import re
import sqlite3
import tempfile
from contextlib import closing
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from hashlib import sha256
from pathlib import Path
from urllib.parse import urlsplit

import analytics
import feeds
from connectors.delivery import delivery_lock


def timestamp(value):
    if not isinstance(value, str) or not re.fullmatch(
        r"\d{4}-\d\d-\d\d[Tt]\d\d:\d\d:\d\d(?:\.\d{1,6})?(?:Z|[+-](?:[01]\d|2[0-3]):[0-5]\d)", value
    ):
        raise ValueError("更新时间须为带时区的 RFC3339 时间戳，精度至微秒")
    try:
        utc = datetime.fromisoformat(value).astimezone(UTC)
        return utc.isoformat(timespec="microseconds").replace("+00:00", "Z")
    except (OverflowError, ValueError) as exc:
        raise ValueError("更新时间超出有效范围") from exc


def at_path(obj, path):
    for key in path.split("."):
        if not isinstance(obj, dict) or key not in obj:
            raise ValueError(f"供应商响应缺少字段 {path}")
        obj = obj[key]
    return obj


def config(raw):
    defaults = {
        "items_path": "items",
        "cursor_path": "next_cursor",
        "cursor_param": "cursor",
        "since_param": "updated_since",
        "updated_field": "updated_at",
        "params": {},
        "fields": {"id": "id", "date": "date", "name": "name", "sales": "sales", "gmv": "gmv"},
    }
    cfg = {**defaults, **raw}
    if not re.fullmatch(r"[a-zA-Z0-9_-]{1,64}", cfg["source"]) or cfg["source"].lower() == "demo":
        raise ValueError("请指定独立的商业来源 ID")
    url = urlsplit(cfg["url"])
    if (
        not url.hostname
        or url.username is not None
        or url.password is not None
        or url.query
        or url.fragment
        or (url.scheme != "https" and not (url.scheme == "http" and url.hostname in {"127.0.0.1", "::1"}))
    ):
        raise ValueError("供应商地址须为无内嵌凭据的 HTTPS 端点（本机测试可用 HTTP）")
    if cfg["market"] not in analytics.MARKETS or cfg["currency"] != analytics.MARKETS[cfg["market"]][1]:
        raise ValueError("市场和本币不匹配")
    if not {"id", "date", "name", "sales", "gmv"} <= cfg["fields"].keys():
        raise ValueError("字段映射缺少商品日事实必填字段")
    allowed = set(analytics.TEXT_FIELDS) | {
        "id",
        "date",
        "sales",
        "gmv",
        "price",
        "orders",
        "refund_units",
        "gmv_estimated",
        "views",
        "profile",
        "currency",
        "market",
        "kind",
    }
    if cfg["fields"].keys() - allowed:
        raise ValueError("字段映射含未知日快照字段")
    paths = [cfg[k] for k in ("items_path", "cursor_path", "updated_field")] + list(cfg["fields"].values())
    if cfg.get("deleted_field"):
        paths.append(cfg["deleted_field"])
    if "total_path" in cfg:
        paths.append(cfg["total_path"])
    lookback = cfg.get("lookback_seconds", 0)
    if type(lookback) is not int or lookback < 0:
        raise ValueError("lookback_seconds 须为非负整数")
    if not all(isinstance(p, str) and re.fullmatch(r"[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*", p) for p in paths):
        raise ValueError("响应字段请用点分隔的键路径")
    since, cursor = cfg["since_param"], cfg["cursor_param"]
    if (
        not isinstance(cfg["params"], dict)
        or not isinstance(since, str)
        or not isinstance(cursor, str)
        or not since
        or not cursor
        or since == cursor
        or {since, cursor}.intersection(cfg["params"])
    ):
        raise ValueError("更新时间、分页和固定查询参数不能重名")
    cfg["initial_since"] = timestamp(cfg["initial_since"])
    return cfg


def updates(cfg, since):
    import requests
    from dlt.sources.helpers.rest_client import RESTClient
    from dlt.sources.helpers.rest_client.paginators import JSONResponseCursorPaginator

    headers = {"Accept": "application/json"}
    if cfg.get("token_env"):
        value = os.environ.get(cfg["token_env"])
        if not value:
            raise ValueError("缺少配置的供应商令牌环境变量")
        headers["Authorization"] = "Bearer " + value
    paginator = JSONResponseCursorPaginator(cursor_path=cfg["cursor_path"], cursor_param=cfg["cursor_param"])

    def require_page(response, **kwargs):
        if response.status_code != 200:
            raise ValueError(f"供应商返回 HTTP {response.status_code}")

    with requests.Session() as session:
        client = RESTClient(base_url=cfg["url"], headers=headers, session=session)
        pages = client.paginate(
            path=cfg["url"],
            params={**cfg["params"], cfg["since_param"]: since},
            data_selector=cfg["items_path"],
            paginator=paginator,
            timeout=(5, 30),
            hooks={"response": [require_page]},
            allow_redirects=False,
        )
        cursors = set()
        expected_total = None
        received = 0
        for page in pages:
            # Preserve exact monetary decimals when the supplier serializes them as JSON numbers.
            payload = page.response.json(parse_float=Decimal)
            rows = at_path(payload, cfg["items_path"])
            token = at_path(payload, cfg["cursor_path"])
            if not isinstance(rows, list):
                raise TypeError("日快照字段必须是数组")
            if "total_path" in cfg:
                total = at_path(payload, cfg["total_path"])
                received += len(rows)
                if type(total) is not int or total < 0 or (expected_total is not None and expected_total != total):
                    raise ValueError("供应商分页声明的总行数无效或发生变化")
                expected_total = total
                if received > total or (token in (None, "") and received != total):
                    raise ValueError("供应商交付行数与分页总行数不符")
            if token not in (None, ""):
                if not isinstance(token, str) or token in cursors:
                    raise ValueError("供应商分页游标无效或重复")
                cursors.add(token)
            for record in rows:
                stamp = timestamp(at_path(record, cfg["updated_field"]))
                if stamp < since:
                    raise ValueError("供应商返回了早于增量起点的修订")
                deleted = (
                    at_path(record, cfg["deleted_field"])
                    if cfg.get("deleted_field")
                    else record.get("deleted", False)
                )
                if deleted is not False:
                    raise ValueError("供应商记录带有删除或无效标记，请核对修订后重试")
                row = {key: at_path(record, path) for key, path in cfg["fields"].items()}
                for key, expected in (
                    ("market", cfg["market"]),
                    ("currency", cfg["currency"]),
                    ("kind", "products"),
                ):
                    if row.get(key, record.get(key, expected)) != expected:
                        raise ValueError(f"供数字段 {key} 与约定范围不符")
                row.pop("currency", None)
                row.update(market=cfg["market"], kind="products")
                key = analytics.normalized(row, cfg["source"])
                row["id"] = key[3]
                yield stamp, row


def publish_pending(db, out):
    for (day,) in db.execute("SELECT day FROM pending ORDER BY day").fetchall():
        with tempfile.NamedTemporaryFile(dir=out, prefix=".publish-", delete=False) as stream:
            temp = Path(stream.name)
            try:
                stream.write(b"[")
                for i, (body,) in enumerate(
                    db.execute("SELECT body FROM facts WHERE day=? ORDER BY id", (day,))
                ):
                    if i:
                        stream.write(b",")
                    stream.write(body.encode("utf-8"))
                stream.write(b"]")
                stream.flush()
                os.fsync(stream.fileno())
                stream.close()
                os.replace(temp, out / (day + ".json"))
                directory = os.open(out, os.O_RDONLY)
                try:
                    os.fsync(directory)
                finally:
                    os.close(directory)
            finally:
                temp.unlink(missing_ok=True)
        with db:
            db.execute("DELETE FROM pending WHERE day=?", (day,))


def sync(raw, out, backfill=None, *, now=None):
    cfg = config(raw)
    # Retry overlap and a completeness assertion do not change the source or mapped business facts.
    identity = {k: v for k, v in cfg.items() if k not in {"lookback_seconds", "total_path"}}
    fingerprint = sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
    ceiling = timestamp(((now or datetime.now(UTC)) + timedelta(minutes=5)).isoformat())
    if cfg["initial_since"] > ceiling:
        raise ValueError("增量起点晚于当前时间，请核对供应商时钟")
    out = Path(out)
    with delivery_lock(out, "dlt_supplier"), closing(sqlite3.connect(out / ".supplier.sqlite3")) as db:
        db.executescript("""
            CREATE TABLE IF NOT EXISTS state(config TEXT PRIMARY KEY, watermark TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS facts(day TEXT,id TEXT,stamp TEXT NOT NULL,body TEXT NOT NULL,
                PRIMARY KEY(day,id)) WITHOUT ROWID;
            CREATE TABLE IF NOT EXISTS pending(day TEXT PRIMARY KEY);
        """)
        previous = db.execute("SELECT config,watermark FROM state").fetchone()
        if previous and previous[0] != fingerprint:
            raise ValueError("此目录已绑定另一份采集配置，请为新范围使用独立目录")
        if not previous and any(not p.name.startswith(".") for p in out.iterdir()):
            raise ValueError("首次采集需要一个独立空交付目录")
        publish_pending(db, out)
        watermark = previous[1] if previous else cfg["initial_since"]
        since = timestamp(backfill) if backfill else watermark
        if since > watermark:
            raise ValueError("回补起点不能晚于当前水位")
        if not backfill and cfg.get("lookback_seconds"):
            latest = datetime.fromisoformat(watermark)
            elapsed = (latest - datetime.fromisoformat(cfg["initial_since"])).total_seconds()
            since = cfg["initial_since"]
            if cfg["lookback_seconds"] < elapsed:
                since = timestamp((latest - timedelta(seconds=cfg["lookback_seconds"])).isoformat())
        changed = 0
        with db:
            if "total_path" in cfg:
                db.execute("""CREATE TEMP TABLE received(day TEXT, id TEXT, stamp TEXT,
                              PRIMARY KEY(day,id,stamp)) WITHOUT ROWID""")
            if backfill:
                days = db.execute("SELECT DISTINCT day FROM facts WHERE stamp >= ?", (since,))
                for (day,) in days:
                    if not (out / (day + ".json")).exists():
                        db.execute("INSERT OR IGNORE INTO pending VALUES(?)", (day,))
            for stamp, row in updates(cfg, since):
                if stamp > ceiling:
                    raise ValueError("供应商修订时间超过本次采集时间五分钟，请核对时钟后重试")
                day, ident = row["date"], row["id"]
                if "total_path" in cfg:
                    seen = db.execute("INSERT OR IGNORE INTO received VALUES(?,?,?)", (day, ident, stamp))
                    if not seen.rowcount:
                        raise ValueError("供应商重复交付同一修订，无法核实分页总行数")
                body = json.dumps(
                    row, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False, default=str
                )
                old = db.execute("SELECT stamp,body FROM facts WHERE day=? AND id=?", (day, ident)).fetchone()
                watermark = max(watermark, stamp)
                if old:
                    if old[0] > stamp:
                        continue
                    same = old[1] == body or analytics.normalized(
                        json.loads(old[1], parse_float=Decimal), cfg["source"]
                    ) == analytics.normalized(row, cfg["source"])
                    if same:
                        if old[0] != stamp:
                            db.execute("UPDATE facts SET stamp=? WHERE day=? AND id=?", (stamp, day, ident))
                        continue
                    if old[0] == stamp:
                        raise ValueError(f"{day} 的商品 {ident} 在同一修订时间出现不同记录")
                db.execute("INSERT OR REPLACE INTO facts VALUES(?,?,?,?)", (day, ident, stamp, body))
                db.execute("INSERT OR IGNORE INTO pending VALUES(?)", (day,))
                changed += 1
            too_large = db.execute(
                """SELECT day FROM facts WHERE day IN (SELECT day FROM pending)
                GROUP BY day HAVING SUM(length(CAST(body AS BLOB)))+COUNT(*)+1>? LIMIT 1""",
                (feeds.MAX_BYTES,),
            ).fetchone()
            if too_large:
                raise ValueError(f"{too_large[0]} 超出单日交付文件上限，请拆分来源")
            db.execute("INSERT OR REPLACE INTO state VALUES(?,?)", (fingerprint, watermark))
        publish_pending(db, out)
        return {
            "source": cfg["source"],
            "market": cfg["market"],
            "since": since,
            "watermark": watermark,
            "changed": changed,
        }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--backfill-from", help="重读此修订时间及其后的记录，不回退水位")
    args = parser.parse_args()
    os.umask(0o077)
    try:
        result = sync(json.loads(args.config.read_text()), args.out, args.backfill_from)
    except ModuleNotFoundError as error:
        parser.exit(1, f"请先安装 connectors/dlt-requirements.txt：{error}\n")
    except (KeyError, TypeError, ValueError, OSError, sqlite3.Error) as error:
        parser.exit(1, f"采集失败：{error}\n")
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()

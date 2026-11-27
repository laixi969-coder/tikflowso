"""tikflowso daily-snapshot analytics. All money inputs and outputs use local major units."""
import argparse
import csv
import heapq
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
import json
import math
import os
import re
import sqlite3
from pathlib import Path

KINDS = ("products", "shops", "creators", "videos", "lives")
MARKETS = {
    "US": ("美国", "USD"), "GB": ("英国", "GBP"), "ID": ("印度尼西亚", "IDR"),
    "MY": ("马来西亚", "MYR"), "TH": ("泰国", "THB"), "VN": ("越南", "VND"),
    "PH": ("菲律宾", "PHP"), "SG": ("新加坡", "SGD"), "MX": ("墨西哥", "MXN"),
    "BR": ("巴西", "BRL"), "ES": ("西班牙", "EUR"), "FR": ("法国", "EUR"),
    "DE": ("德国", "EUR"), "IT": ("意大利", "EUR"), "JP": ("日本", "JPY"),
    "IE": ("爱尔兰", "EUR"), "CN": ("中国大陆", "CNY"),
}
DEMO_END = date(2026, 11, 19)
DEMO_DAYS = 75
# Below this threshold every cent survives conversion to a float in major units and back.
EXACT_MONEY_THRESHOLD = 2**51
SORTS = {"gmv", "sales", "views", "followers", "growth", "follower_growth"}
RANGE_METRICS = {"gmv": KINDS, "sales": KINDS, "price": ("products",),
                 "followers": ("creators",), "views": ("creators","videos","lives")}
RANGE_KEYS = tuple(f"{edge}_{metric}" for metric in RANGE_METRICS for edge in ("min","max"))
RANKING_KEYS = ("market","source","date","days","kind","category","segment","q","match","sort",*RANGE_KEYS)
TEXT_FIELDS = ("name", "subtitle", "category", "segment", "tag", "music",
               "keyword", "script", "shop_id", "creator_id", "product_id", "image_key")

import source_policy

SCHEMA = source_policy.SCHEMA + """
CREATE TABLE IF NOT EXISTS analytics_sources(
  id TEXT PRIMARY KEY, name TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS analytics_entities(
  source TEXT NOT NULL, market TEXT NOT NULL, kind TEXT NOT NULL, id TEXT NOT NULL,
  PRIMARY KEY(source,market,kind,id)
) WITHOUT ROWID;
CREATE TABLE IF NOT EXISTS analytics_daily(
  source TEXT NOT NULL, market TEXT NOT NULL, kind TEXT NOT NULL, id TEXT NOT NULL,
  date TEXT NOT NULL, name TEXT NOT NULL, subtitle TEXT, category TEXT, segment TEXT,
  tag TEXT, music TEXT, keyword TEXT, script TEXT, shop_id TEXT, creator_id TEXT,
  product_id TEXT, image_key TEXT, profile_json TEXT, gmv_units INTEGER NOT NULL, price_units INTEGER,
  sales INTEGER NOT NULL, views INTEGER, followers INTEGER, follower_growth INTEGER,
  orders INTEGER, refund_units INTEGER, gmv_estimated INTEGER,
  PRIMARY KEY(source,market,kind,id,date),
  FOREIGN KEY(source,market,kind,id) REFERENCES analytics_entities(source,market,kind,id)
) WITHOUT ROWID;
CREATE INDEX IF NOT EXISTS analytics_scope ON analytics_daily(source,market,date,kind);
CREATE INDEX IF NOT EXISTS video_product_dates ON analytics_daily(source,market,product_id,date,id)
  WHERE kind='videos' AND product_id!='';
CREATE TABLE IF NOT EXISTS snapshot_revisions (
 revision INTEGER PRIMARY KEY, source TEXT NOT NULL, market TEXT NOT NULL, kind TEXT NOT NULL,
 id TEXT NOT NULL, date TEXT NOT NULL, changed_at INTEGER NOT NULL, before_json TEXT NOT NULL, after_json TEXT NOT NULL
);
"""
COLUMNS = ("source", "market", "kind", "id", "date", *TEXT_FIELDS, "profile_json", "gmv_units",
           "price_units", "sales", "views", "followers", "follower_growth","orders","refund_units","gmv_estimated")
UPSERT = ("INSERT INTO analytics_daily (" + ",".join(COLUMNS) + ") VALUES (" +
          ",".join("?" for _ in COLUMNS) + ") ON CONFLICT(source,market,kind,id,date) "
          "DO UPDATE SET " + ",".join(f"{c}=excluded.{c}" for c in COLUMNS[5:]))


def iso_day(value):
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise ValueError("日期须为 YYYY-MM-DD")
    try:
        actual = date.fromisoformat(value)
    except ValueError:
        raise ValueError("日期不存在") from None
    if actual.year < 1900 or actual.year > 2200:
        raise ValueError("日期须在 1900 至 2200 年内")
    return actual


def numeric(raw, field, *, required=False, money=False, signed=False):
    if raw is None or raw == "":
        if required:
            raise ValueError(f"缺少 {field}")
        return None
    try:
        number = Decimal(str(raw))
        if not number.is_finite() or number.copy_abs() > 10**14 or (number < 0 and not signed):
            raise ValueError
        if money:
            fixed = number.quantize(Decimal("0.01"))
            if number != fixed:
                raise ValueError
            return int(fixed * 100)
        if number != number.to_integral_value():
            raise ValueError
        return int(number)
    except (ValueError, InvalidOperation, OverflowError):
        raise ValueError(f"{field} 的数值或精度无效") from None


def csv_rows(stream):
    reader = csv.DictReader(stream, strict=True)
    try:
        names = reader.fieldnames or []
        if not names or any(not name.strip() for name in names) or len(set(names)) != len(names):
            raise ValueError("CSV 表头为空或存在重复列")
        for row in reader:
            if None in row or None in row.values():
                raise ValueError(f"CSV 第 {reader.line_num} 行列数与表头不一致")
            yield row
    except csv.Error as exc:
        raise ValueError(f"CSV 第 {reader.reader.line_num} 行格式无效：{exc}") from None


def money_text(cents):
    return f"{cents // 100}.{cents % 100:02}"


def exact_amounts(**amounts):
    return {field + "_exact": money_text(cents) for field,cents in amounts.items()
            if cents is not None and cents >= EXACT_MONEY_THRESHOLD}


def profile_amount(cents):
    if cents is None:
        return None
    # Retain the original cents for audit and reimport, including in JSON-encoded profiles.
    return money_text(cents) if cents >= EXACT_MONEY_THRESHOLD else cents / 100



def profile_json(raw, kind):
    if raw is None or raw == "":
        return None
    if isinstance(raw,str):
        try:
            raw = json.loads(raw, parse_float=Decimal)
        except ValueError:
            raise ValueError("profile 不是有效的 JSON") from None
    if not isinstance(raw,dict):
        raise ValueError("profile 须为对象")
    allowed = {"products":{"reviews"}, "creators":{"audience","milestones"},
               "lives":{"live_traffic","live_products","live_session"}}.get(kind,set())
    if not set(raw) <= allowed:
        raise ValueError("profile 包含与对象类型不匹配的字段")
    def text(value):
        if not isinstance(value,str) or not 1 <= len(value.strip()) <= 1200:
            raise ValueError("画像中的文本缺失或过长")
        return value.strip()
    def entries(value):
        if not isinstance(value,list) or len(value)>100 or not all(isinstance(i,dict) for i in value):
            raise ValueError("画像条目须为长度不超过 100 的对象数组")
        return value
    def share_list(value):
        items = []
        for entry in entries(value):
            share = numeric(entry.get("share"),"share",required=True,money=True)
            if share > 10000:
                raise ValueError("占比须在 0 至 100 之间")
            items.append({"name":text(entry.get("name")),"share":share/100})
        return items
    out = {}
    if "audience" in raw:
        out["audience"] = share_list(raw["audience"])
    if "reviews" in raw:
        out["reviews"] = []
        for entry in entries(raw["reviews"]):
            review = {"text":text(entry.get("text"))}
            if entry.get("date"):
                review["date"] = iso_day(entry["date"]).isoformat()
            if entry.get("rating") is not None:
                rating = numeric(entry["rating"],"rating",money=True)
                if rating is None or not 100 <= rating <= 500:
                    raise ValueError("rating 须在 1 至 5 之间")
                review["rating"] = rating/100
            out["reviews"].append(review)
    if "milestones" in raw:
        out["milestones"] = [{"label":text(e.get("label")), "date":iso_day(e.get("date")).isoformat()}
                             for e in entries(raw["milestones"])]
    if "live_traffic" in raw:
        block = raw["live_traffic"]
        if not isinstance(block,dict):
            raise ValueError("live_traffic 须为对象")
        traffic = {}
        for key in ("peak_viewers","avg_watch_seconds"):
            if key in block:
                traffic[key] = numeric(block[key],key,required=True)
        if "sources" in block:
            traffic["sources"] = share_list(block["sources"])
        out["live_traffic"] = traffic
    def product_links(records):
        linked = {}
        for entry in entries(records):
            product = text(entry.get("id"))
            if len(product)>160 or product in linked:
                raise ValueError("同一直播日快照的商品 ID 须唯一，长度不超过 160")
            sales = numeric(entry.get("sales"),"live_products.sales")
            cents = numeric(entry.get("gmv"),"live_products.gmv",money=True)
            linked[product] = {"id":product,"sales":sales,"gmv":profile_amount(cents)}
        return list(linked.values())
    if "live_products" in raw:
        out["live_products"] = product_links(raw["live_products"])
    if "live_session" in raw:
        block = raw["live_session"]
        if not isinstance(block,dict) or set(block)-{"start_at","end_at","enter_count","gmv","products","online_viewers"}:
            raise ValueError("live_session 包含无效的场次字段")
        block = {key:value for key,value in block.items() if value is not None}
        def timestamp(value):
            if not isinstance(value,str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2}(?:\.\d{1,6})?)?(?:Z|[+-]\d{2}:\d{2})",value):
                raise ValueError("直播时刻须使用带时区的 ISO 8601 时间")
            try:
                return datetime.fromisoformat(value.replace("Z","+00:00")).astimezone(timezone.utc).isoformat(timespec="microseconds")
            except (ValueError,OverflowError):
                raise ValueError("直播时刻无效") from None
        session = {key:timestamp(block[key]) for key in ("start_at","end_at") if key in block}
        if session.get("start_at","") > session.get("end_at","~"):
            raise ValueError("直播结束时刻不能早于开始时刻")
        if "enter_count" in block:
            session["enter_count"] = numeric(block["enter_count"],"enter_count",required=True)
        if "gmv" in block:
            session["gmv"] = profile_amount(numeric(block["gmv"],"live_session.gmv",required=True,money=True))
        if "products" in block:
            session["products"] = product_links(block["products"])
        if "online_viewers" in block:
            counts = {}
            for point in entries(block["online_viewers"]):
                when = timestamp(point.get("time"))
                if when in counts or not session.get("start_at","") <= when <= session.get("end_at","~"):
                    raise ValueError("在线人数时点重复或超出场次范围")
                counts[when] = numeric(point.get("value"),"online_viewers",required=True)
            session["online_viewers"] = [{"time":when,"value":counts[when]} for when in sorted(counts)]
        out["live_session"] = session
    return json.dumps(out,ensure_ascii=False,separators=(",",":")) if out else None


def normalized(row, source):
    if not isinstance(row, dict):
        raise ValueError("记录必须为对象")
    kind = str(row.get("kind", "")).strip()
    market = str(row.get("market", "")).strip().upper()
    if market not in MARKETS or kind not in KINDS:
        raise ValueError("market 或 kind 不受支持")
    ident = row.get("id")
    if not isinstance(ident, (str, int)) or isinstance(ident, bool):
        raise ValueError("缺少对象 id")
    ident = str(ident).strip()
    if not 1 <= len(ident) <= 160:
        raise ValueError("id 长度须为 1–160")
    values = []
    for key in TEXT_FIELDS:
        raw = row.get(key, "")
        if raw is not None and not isinstance(raw, (str, int)):
            raise ValueError(f"{key} 必须为文本")
        val = "" if raw is None else str(raw).strip()
        if len(val) > 1500:
            raise ValueError(f"{key} 过长")
        values.append(val)
    if not values[0]:
        raise ValueError("缺少 name")
    marker=row.get("gmv_estimated")
    flags={"true":1,"false":0,"1":1,"0":0}
    if marker not in (None,"") and str(marker).lower() not in flags:
        raise ValueError("gmv_estimated 须填写 true 或 false")
    numbers = (
        numeric(row.get("gmv"), "gmv", required=True, money=True),
        numeric(row.get("price"), "price", money=True),
        numeric(row.get("sales"), "sales", required=True),
        numeric(row.get("views"), "views"), numeric(row.get("followers"), "followers"),
        numeric(row.get("follower_growth"), "follower_growth", signed=True),
        numeric(row.get("orders"),"orders"),numeric(row.get("refund_units"),"refund_units"),flags.get(str(marker).lower()),
    )
    return source, market, kind, ident, iso_day(row.get("date")).isoformat(), *values, profile_json(row.get("profile"),kind), *numbers


def write_batch(db, records, source, label, *, owner=None, shared=False):
    dates = []
    identities = set()
    db.execute("SAVEPOINT analytics_batch")
    try:
        source_policy.register(db,source,owner,shared)
        db.execute("INSERT OR IGNORE INTO analytics_sources VALUES (?,?)", (source, label))
        for n, row in enumerate(records, 1):
            try:
                values = normalized(row, source)
            except ValueError as error:
                raise ValueError(f"第 {n} 行：{error}") from None
            identity = values[:4]
            if identity not in identities:
                db.execute("INSERT OR IGNORE INTO analytics_entities VALUES (?,?,?,?)", identity)
                identities.add(identity)
            dates.append(values[4])
            db.execute(UPSERT, values)
        if not dates:
            raise ValueError("导入文件没有数据行")
    except BaseException:
        db.execute("ROLLBACK TO analytics_batch")
        raise
    finally:
        db.execute("RELEASE analytics_batch")
    return {"source": source, "rows": len(dates), "entities": len(identities),
            "first_date": min(dates), "date": max(dates)}


def import_rows(db, rows, source, *, owner=None, shared=False):
    if not isinstance(source, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", source) or source.lower() == "demo":
        raise ValueError("来源使用 1–64 位字母、数字、短横线或下划线；demo 为保留名称")
    return write_batch(db, rows, source, source, owner=owner, shared=shared)


def daily_from_counters(rows):
    """Convert a complete delivery with its baselines into an importable daily file."""
    if not isinstance(rows,list) or not 1<=len(rows)<=20000:raise ValueError("每批需包含 1 至 20000 条记录")
    snapshots={}
    sources=set()
    for line,row in enumerate(rows,1):
        try:
            if not isinstance(row,dict):raise ValueError("记录必须为对象")
            gmv=numeric(row.get("cumulative_gmv"),"cumulative_gmv",required=True,money=True)
            sales=numeric(row.get("cumulative_sales"),"cumulative_sales",required=True)
            daily={k:v for k,v in row.items() if k not in ("cumulative_gmv","cumulative_sales")}
            if "sales" in daily or "gmv" in daily:raise ValueError("累计文件中不能混入日成交额或日销量")
            sources.add(str(row.get("source","")).strip())
            if len(sources)>1:raise ValueError("每次转换仅支持一个来源")
            values=normalized({**daily,"gmv":0,"sales":0},"conversion")
            snapshots[values[1:5]]=(gmv,sales,daily)
        except ValueError as exc:
            raise ValueError(f"第 {line} 行：{exc}") from exc
    result=[]
    skipped=[]
    previous={}
    for (market,kind,item,day),(gmv,sales,daily) in sorted(snapshots.items()):
        key=(market,kind,item)
        prior=previous.get(key)
        current=iso_day(day)
        previous[key]=(current,gmv,sales)
        reason=None
        if prior is None:reason="baseline"
        elif (current-prior[0]).days!=1:reason="gap"
        elif gmv<prior[1] or sales<prior[2]:reason="counter_decrease"
        if reason:
            skipped.append({"market":market,"kind":kind,"id":item,"date":day,"reason":reason})
        else:
            cents=gmv-prior[1]
            result.append({**daily,"gmv":f"{cents//100}.{cents%100:02}","sales":sales-prior[2]})
    return {"rows":result,"skipped":skipped}


PRODUCTS = [
    ("Cloud Dew Hydrating Serum", "serum", "美妆个护", 24),
    ("Aura Wireless Headphones", "headphones", "数码电子", 49),
    ("TrailSip Vacuum Bottle", "bottle", "运动户外", 28),
    ("Lumi Mini Desk Lamp", "lamp", "家居生活", 32),
    ("Soft Form Shoulder Bag", "bag", "服饰配件", 42),
    ("Bloom Tinted Lip Oil", "lip", "美妆个护", 16),
    ("FlexLoop Resistance Set", "fitness", "运动户外", 19),
    ("Urban Brew Ceramic Cup", "cup", "家居生活", 22),
    ("Pocket Fold Phone Stand", "stand", "数码电子", 12),
    ("Daily Ritual Face Roller", "roller", "美妆个护", 18),
    ("Drift Knit Throw", "blanket", "家居生活", 39),
    ("Field Notes Planner", "planner", "文具办公", 14),
    ("Dew Barrier Night Serum", "serum", "美妆个护", 29),
    ("Studio One Headset", "headphones", "数码电子", 65),
    ("Summit Sport Flask", "bottle", "运动户外", 25),
    ("Orbit Reading Light", "lamp", "家居生活", 30),
    ("Frame Canvas Tote", "bag", "服饰配件", 35),
    ("Peony Lip Glaze", "lip", "美妆个护", 15),
]
SHOPS = ["Dew Atelier", "Soundform Studio", "Trail Goods", "Lumi Living", "Forma Goods",
         "Bloom Lab", "Flex Collective", "Urban Brew", "Pocket Supply", "Ritual Studio",
         "Drift Home", "Field Paper Co."]
CREATORS = ["Maya Chen", "Leo Brooks", "Sophia Reed", "Ava Park", "Noah Ellis",
            "Isla James", "Theo Morgan", "Emmy Lin", "Nico Bell"]
TAGS = ["#DailyFinds", "#DeskSetup", "#OnTheGo", "#SmallSpace", "#StyleNotes", "#GetReadyWithMe"]
MUSIC = ["Sunday Window", "Morning Loop", "Daylight Edit", "Quiet Bloom"]
HOOKS = ["真实体验", "场景对比", "开箱试用", "使用教程"]
CN_PRODUCTS = [
    ("山茶保湿精华液", "serum", "美妆个护", 89),
    ("通勤无线耳机", "headphones", "数码电子", 139),
    ("轻量随行保温杯", "bottle", "运动户外", 69.9),
    ("暖光阅读台灯", "lamp", "家居生活", 79),
    ("棉麻单肩包", "bag", "服饰配件", 49.9),
    ("方格手账本", "planner", "文具办公", 19.9),
    ("桂花润唇油", "lip", "美妆个护", 35.9),
    ("折叠手机支架", "stand", "数码电子", 29.9),
    ("居家拉伸弹力带", "fitness", "运动户外", 39.9),
    ("白瓷马克杯", "cup", "家居生活", 45),
    ("帆布通勤托特包", "bag", "服饰配件", 59),
    ("周计划便签本", "planner", "文具办公", 12.9),
]
CN_SHOPS = ["花间个护铺", "九点数码铺", "远山运动馆", "微光生活馆", "青禾布艺铺", "拾页文具社"]
CN_CREATORS = ["小禾试好物", "阿川的桌面", "周末去走走", "阿棠住小家", "小岚的衣橱", "纸间慢慢写"]
CN_TAGS = ["#日常护肤", "#桌面好物", "#周末去户外", "#小家布置", "#通勤穿搭", "#手账日常"]
CN_MUSIC = ["窗边晴天", "街角慢拍", "午后的风", "晚灯小调"]


def demo_live_fields(stamp, index, sales, cents, views, product_count):
    # Each fixture room has one reported session per day, independent of the period ranking.
    begin = datetime.fromisoformat(stamp).replace(hour=9+index%8,minute=index%20,tzinfo=timezone.utc)
    peak = round(views*.18)
    units = [sales-sales//4-sales//8,sales//4,sales//8]
    products = []
    remaining = cents
    for n, count in enumerate(units):
        amount = round(cents*count/sales) if sales and n<2 else remaining
        remaining -= amount
        products.append({"id":f"p{(index+n)%product_count+1:02}","sales":count,"gmv":amount/100})
    times = [(begin+timedelta(minutes=n*15)).isoformat(timespec="microseconds") for n in range(5)]
    session = {"start_at":times[0],"end_at":times[-1],"enter_count":peak*3+sales,"gmv":cents/100,
               "products":products,"online_viewers":[{"time":when,"value":round(peak*ratio)}
                   for when,ratio in zip(times,(.15,.6,1,.7,.22))]}
    return {"live_session":session,"live_products":products}


def demo_rows(only_market=None):
    start = DEMO_END - timedelta(days=DEMO_DAYS - 1)
    # Existing market positions determine their historical sample volumes. CN prices are already in yuan.
    for market_index, (market, multiplier) in enumerate([("US", 1), ("GB", .8), ("ID", 15700), ("MY", 4.4), ("CN", 1)]):
        if only_market is not None and market != only_market:
            continue
        if market == "CN":
            products, shops, creators, tags, music = CN_PRODUCTS, CN_SHOPS, CN_CREATORS, CN_TAGS, CN_MUSIC
        else:
            products, shops, creators, tags, music = PRODUCTS, SHOPS, CREATORS, TAGS, MUSIC
        for day in range(DEMO_DAYS):
            stamp = (start + timedelta(days=day)).isoformat()
            base = {"market": market, "date": stamp}
            totals = {}
            def add(kind, index, sales, cents, views):
                bucket = totals.setdefault((kind, index), [0, 0, 0])
                for k, amount in enumerate((sales, cents, views)):
                    bucket[k] += amount
            for i, (name, image, category, base_price) in enumerate(products):
                shop, creator = i % len(shops), i % len(creators)
                cents = round(base_price * multiplier * 100)
                wave = 1 + .21 * math.sin(day * .29 + i * .75) + .13 * math.cos(day * .71 + i)
                sales = round((350 - i * 13) * wave * (1 + day * (.004 + i % 4 * .003)) *
                              (1 - market_index * .09))
                video_sales = round(sales * (.50 + .04 * (i % 5)))
                live_sales = round(sales * .24)
                views = video_sales * (40 + i * 5)
                live_views = live_sales * (16 + i)
                common = {**base, "category": category, "image_key": image,
                          "shop_id": f"s{shop+1:02}", "creator_id": f"c{creator+1:02}",
                          "product_id": f"p{i+1:02}"}
                yield {**common, "id": common["product_id"], "kind": "products", "name": name,
                       "subtitle": shops[shop], "price": cents / 100,
                       "segment": "new" if i % 4 == 3 else "promoted", "sales": sales,
                       "gmv": sales * cents / 100,
                       "profile":{"reviews":[{"text":"包装完好，实际使用效果符合预期。","rating":4+i%2,"date":stamp}]}}
                yield {**common, "id": f"v{i+1:02}", "kind": "videos",
                       "name": f"{name.split()[0]} · {HOOKS[i%4]}", "subtitle": creators[creator],
                       "segment": "image" if i % 4 == 2 else "video", "sales": video_sales,
                       "views": views, "gmv": video_sales * cents / 100, "tag": tags[i%len(tags)],
                       "music": music[i%len(music)], "keyword": name if market == "CN" else image, "script": HOOKS[i%4]}
                yield {**common, "id": f"l{i+1:02}", "kind": "lives",
                       "name": f"{shops[shop]} · 直播选物", "subtitle": creators[creator],
                       "segment": "replay" if i % 3 else "live", "sales": live_sales,
                       "views": live_views, "gmv": live_sales * cents / 100,
                       "profile":{**demo_live_fields(stamp,i,live_sales,live_sales*cents,live_views,len(products)),
                               "live_traffic":{"peak_viewers":round(live_views*.18),"avg_watch_seconds":42+i,
                               "sources":[{"name":"推荐","share":70},{"name":"关注","share":30}]}}}
                add("shops", shop, sales, sales*cents, views+live_views)
                add("creators", creator, video_sales+live_sales, (video_sales+live_sales)*cents, views+live_views)
            for (kind, i), (sales, gmv, views) in totals.items():
                creator = kind == "creators"
                delta = (640 + i * 87 + market_index * 40)
                yield {**base, "kind": kind, "id": ("c" if creator else "s")+f"{i+1:02}",
                       "name": (creators if creator else shops)[i], "category": products[i][2],
                       "subtitle": ("@" + creators[i].lower().replace(" ", "")) if creator else MARKETS[market][0],
                       "segment": ("rising" if i%3==0 else "established") if creator else ("local","crossborder","s")[i%3],
                       "sales": sales, "gmv": gmv / 100, "views": views,
                       "followers": (39500 + i*11733 + day*delta) if creator else None,
                       "follower_growth": delta if creator else None,
                       "profile":{"audience":[{"name":"18–24 岁","share":32+i},{"name":"25–34 岁","share":44-i},
                                               {"name":"其他年龄段","share":24}],
                                  "milestones":[{"date":start.isoformat(),"label":"开始追踪账号"}]} if creator else None}


def init(db):
    db.row_factory = sqlite3.Row
    db.executescript(SCHEMA)
    source_policy.migrate(db)
    existing={r[1] for r in db.execute("PRAGMA table_info(analytics_daily)")}
    for column in ("orders","refund_units","gmv_estimated"):
        if column not in existing:
            db.execute("ALTER TABLE analytics_daily ADD COLUMN "+column+" INTEGER")
            db.execute("DROP TRIGGER IF EXISTS audit_snapshot_update")
    db.execute("CREATE INDEX IF NOT EXISTS estimated_facts ON analytics_daily(source,market,date) WHERE gmv_estimated=1")
    if "profile_json" not in {r[1] for r in db.execute("PRAGMA table_info(analytics_daily)")}:
        db.execute("ALTER TABLE analytics_daily ADD COLUMN profile_json TEXT")
        # Preserve existing snapshots. Only the bundled demonstration dataset is refreshed.
        if db.execute("SELECT 1 FROM analytics_sources WHERE id='demo'").fetchone():
            write_batch(db, demo_rows(), "demo", "演示数据")
    if not db.execute("SELECT 1 FROM analytics_sources WHERE id='demo'").fetchone():
        write_batch(db, demo_rows(), "demo", "演示数据")
    else:
        if not db.execute("SELECT 1 FROM analytics_entities WHERE source='demo' AND market='CN' LIMIT 1").fetchone():
            write_batch(db, demo_rows("CN"), "demo", "演示数据")
        # Add fixture-only fields to older installations. Operator imports and their audit history are untouched.
        old = db.execute("""SELECT market,id,date,sales,gmv_units,views,profile_json FROM analytics_daily
            WHERE source='demo' AND kind='lives' AND json_type(profile_json,'$.live_session') IS NULL""")
        updates = []
        for market, identifier, day, sales, cents, views, raw in old:
            product_count = len(CN_PRODUCTS if market == "CN" else PRODUCTS)
            if not re.fullmatch(r"l\d{2}",identifier) or not 1 <= int(identifier[1:]) <= product_count or views is None:
                continue
            profile = json.loads(raw) if raw else {}
            profile.update(demo_live_fields(day,int(identifier[1:])-1,sales,cents,views,product_count))
            updates.append((json.dumps(profile,ensure_ascii=False,separators=(",",":")),market,identifier,day))
        if updates:
            db.execute("SAVEPOINT refresh_demo_sessions")
            try:
                trigger = db.execute("SELECT sql FROM sqlite_master WHERE type='trigger' AND name='audit_snapshot_update'").fetchone()
                if trigger: db.execute("DROP TRIGGER audit_snapshot_update")
                db.executemany("""UPDATE analytics_daily SET profile_json=? WHERE source='demo' AND kind='lives'
                    AND market=? AND id=? AND date=?""",updates)
                if trigger: db.execute(trigger[0])
            except BaseException:
                db.execute("ROLLBACK TO refresh_demo_sessions")
                raise
            finally:
                db.execute("RELEASE refresh_demo_sessions")
    fields=COLUMNS[5:]
    changed=" OR ".join(f"OLD.{c} IS NOT NEW.{c}" for c in fields)
    def snapshot(prefix):
        return "json_object("+",".join(f"'{c}',{prefix}.{c}" for c in fields)+")"
    db.execute(f"""CREATE TRIGGER IF NOT EXISTS audit_snapshot_update AFTER UPDATE ON analytics_daily
         WHEN {changed} BEGIN INSERT INTO snapshot_revisions(source,market,kind,id,date,changed_at,before_json,after_json)
         VALUES(NEW.source,NEW.market,NEW.kind,NEW.id,NEW.date,strftime('%s','now'),{snapshot('OLD')},{snapshot('NEW')}); END""")


def bounds(db, source, market):
    return db.execute("SELECT MIN(date),MAX(date) FROM analytics_daily WHERE source=? AND market=?",
                      (source, market)).fetchone()


def int_param(params, key, default, ceiling):
    try:
        value = int(params.get(key, default))
    except (ValueError, TypeError):
        raise ValueError(f"{key} 须为整数") from None
    if not 1 <= value <= ceiling:
        raise ValueError(f"{key} 须在 1 至 {ceiling} 之间")
    return value


def scope_for(db, params):
    source = params.get("source") or "demo"
    if not db.execute("SELECT 1 FROM analytics_sources WHERE id=?", (source,)).fetchone():
        raise LookupError("未找到此数据来源")
    market = (params.get("market") or "US").upper()
    if market not in MARKETS:
        raise ValueError("市场不受支持")
    first, last = bounds(db, source, market)
    end = iso_day(params.get("date") or last or DEMO_END.isoformat())
    days = int_param(params, "days", 7, 366)
    begin = end - timedelta(days=days-1)
    return {"source":source, "market":market, "currency":MARKETS[market][1], "date":end.isoformat(),
            "start_date":begin.isoformat(), "first_date":first, "latest_date":last,
            "prev_date":(begin - timedelta(days=days)).isoformat(), "days":days}


def meta(db, s):
    markets = [{"code":code, "name":MARKETS[code][0], "currency":MARKETS[code][1]}
               for (code,) in db.execute("SELECT DISTINCT market FROM analytics_entities WHERE source=? ORDER BY market",
                                          (s["source"],))]
    markets.sort(key=lambda m:(m["code"] != "US", m["code"]))
    categories_by_kind = {kind: [] for kind in KINDS}
    for kind,category in db.execute("""SELECT DISTINCT kind,category FROM analytics_daily
            WHERE source=:source AND market=:market AND category!='' ORDER BY category""",s):
        categories_by_kind[kind].append(category)
    categories = sorted({label for labels in categories_by_kind.values() for label in labels})
    sources = [dict(r) for r in db.execute("SELECT * FROM analytics_sources ORDER BY id != 'demo',id")]
    estimated=db.execute("""SELECT 1 FROM analytics_daily WHERE source=:source AND market=:market AND
                            date BETWEEN :start_date AND :date AND gmv_estimated=1 LIMIT 1""",s).fetchone()
    return {**s, "markets":markets, "categories":categories, "categories_by_kind":categories_by_kind,
            "sources":sources,"includes_estimates":bool(estimated)}


def period_growth(current, previous):
    if current is None or previous is None or previous == 0:
        return None
    return round((current - previous) / previous * 100, 2)


def average_cents(amount, sales):
    # Round once at the cent, using the same ties-to-even rule for all product evidence.
    whole, remainder = divmod(amount, sales)
    if 2 * remainder > sales or (2 * remainder == sales and whole % 2):
        whole += 1
    return whole


def iter_rows(db, s, *, kind=None):
    # The last snapshot supplies historical labels and stock measures, independent of import order.
    kind_clause = "AND kind=:row_kind" if kind is not None else ""
    records = db.execute(f"""
        WITH ranked AS (
          SELECT kind,id,name,subtitle,category,segment,tag,music,keyword,script,shop_id,creator_id,
            product_id,image_key,date AS updated_at,price_units,followers,
            ROW_NUMBER() OVER frame AS seq,
            SUM(CASE WHEN date>=:start_date THEN gmv_units END) OVER frame AS gmv_units,
            SUM(CASE WHEN date>=:start_date THEN sales END) OVER frame AS sales,
            CASE WHEN COUNT(CASE WHEN date>=:start_date THEN orders END) OVER frame=SUM(date>=:start_date) OVER frame
              THEN SUM(CASE WHEN date>=:start_date THEN orders END) OVER frame END AS order_total,
            CASE WHEN COUNT(CASE WHEN date>=:start_date THEN refund_units END) OVER frame=SUM(date>=:start_date) OVER frame
              THEN SUM(CASE WHEN date>=:start_date THEN refund_units END) OVER frame END AS refund_total,
            CASE WHEN MAX(CASE WHEN date>=:start_date THEN gmv_estimated END) OVER frame=1 THEN 1
                 WHEN COUNT(CASE WHEN date>=:start_date THEN gmv_estimated END) OVER frame=SUM(date>=:start_date) OVER frame THEN 0 END AS estimated,
            SUM(CASE WHEN date>=:start_date THEN views END) OVER frame AS views,
            SUM(CASE WHEN date>=:start_date THEN follower_growth END) OVER frame AS net,
            COUNT(CASE WHEN date>=:start_date THEN follower_growth END) OVER frame AS net_days,
            SUM(date>=:start_date) OVER frame AS covered,
            SUM(CASE WHEN date<:start_date THEN gmv_units END) OVER frame AS prior,
            SUM(date<:start_date) OVER frame AS prior_days,
            MAX(CASE WHEN date=date(:start_date,'-1 day') THEN followers END) OVER frame AS baseline_followers
          FROM analytics_daily WHERE source=:source AND market=:market AND date BETWEEN :prev_date AND :date {kind_clause}
          WINDOW frame AS (PARTITION BY kind,id ORDER BY date DESC ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING)
        ) SELECT kind,id,name,subtitle,category,segment,tag,music,keyword,script,shop_id,creator_id,
            product_id,image_key,updated_at,price_units,followers,gmv_units,sales,views,net,net_days,
            covered,prior,prior_days,baseline_followers,order_total AS orders,refund_total AS refund_units,estimated AS gmv_estimated
            FROM ranked WHERE seq=1 AND updated_at>=:start_date
    """, {**s,"row_kind":kind})
    for record in records:
        data = dict(record)
        units = data.pop("gmv_units")
        price = data.pop("price_units")
        previous = data.pop("prior")
        prior_days = data.pop("prior_days")
        covered = data.pop("covered")
        net, net_days = data.pop("net"), data.pop("net_days")
        baseline = data.pop("baseline_followers")
        if baseline is not None and data["followers"] is not None and data["updated_at"] == s["date"]:
            follower_change = data["followers"] - baseline
        else:
            follower_change = net if net_days == s["days"] else None
        average = average_cents(units, data["sales"]) if data["sales"] else None
        yield {**data, **exact_amounts(gmv=units,price=price,avg_price=average),
                    "gmv":units/100, "price":price/100 if price is not None else None,
                    "avg_price":average/100 if average is not None else None,
                    "growth":period_growth(units,previous) if covered==prior_days==s["days"] else None,
                    "follower_growth":follower_change, "covered_days":covered}


def rows_for(db, s):
    return list(iter_rows(db, s))


def ranking_filter(kind, params):
    if kind not in KINDS:
        raise ValueError("kind 不受支持")
    segment = params.get("segment")
    breakout = kind == "creators" and segment == "breakout"
    sort = params.get("sort") or ("growth" if breakout else "gmv")
    if sort not in SORTS:
        raise ValueError("排序指标不受支持")
    q = (params.get("q") or "").strip().casefold()
    exact = params.get("match") == "exact"
    def matches(row):
        if not q:
            return True
        if exact:
            return q in (row["id"].casefold(), row["name"].casefold())
        return q in (row["name"]+" "+row["id"]+" "+row["subtitle"]).casefold()
    def in_segment(row):
        if breakout:
            return (row["growth"] is not None and row["growth"] >= 15 and row["sales"] >= 20
                    and row["followers"] is not None and row["followers"] < 200000)
        return not segment or row["segment"] == segment
    ranges = []
    for field, kinds in RANGE_METRICS.items():
        limits = []
        for edge in ("min", "max"):
            key = f"{edge}_{field}"
            minor_units = field in ("gmv", "price")
            value = numeric(params.get(key), key, money=minor_units)
            limits.append(value)
        low, high = limits
        if low is None and high is None:
            continue
        if kind not in kinds:
            raise ValueError(f"{kind} 不支持 {field} 区间")
        if low is not None and high is not None and low > high:
            raise ValueError(f"{field} 的下限超过上限")
        ranges.append((field,low,high))
    category = params.get("category") or ""
    def accepts(row):
        return (row["kind"] == kind and matches(row) and in_segment(row)
                and (not category or row["category"] == category or (row["category"] or "").startswith(category+" > "))
                and all((value := ranking_value(row,k)) is not None and (lo is None or value>=lo) and (hi is None or value<=hi)
                        for k,lo,hi in ranges))
    return sort, accepts


def ranking_rows(db, scope, params):
    kind = params.get("kind", "products")
    metric, accepts = ranking_filter(kind, params)
    # Kind is stable across both windows; name, segment and category are closing attributes.
    return metric, filter(accepts, iter_rows(db, scope, kind=kind))


def ranking_value(row, metric):
    value = row[metric]
    if metric not in ("gmv", "price") or value is None:
        return value
    exact = row.get(metric + "_exact")
    if exact is not None:
        return int(exact.replace(".", ""))
    return round(value * 100)


def ranking_order(metric):
    def key(row):
        value = ranking_value(row, metric)
        return value is None, -(value or 0), row["id"]
    return key


def ranking_page(db, scope, params):
    page=int_param(params,"page",1,10**9)
    limit=int_param(params,"limit",20,1000)
    start=(page-1)*limit
    metric,filtered=ranking_rows(db,scope,params)
    total=0
    def matches():
        nonlocal total
        for row in filtered:
            total+=1
            yield row
    if start+limit<=2000:
        top=heapq.nsmallest(start+limit,matches(),key=ranking_order(metric))
        selected=top[start:]
    else:
        # Deep pages use a connection-private disk sort. This never writes to the main database.
        db.execute("CREATE TEMP TABLE IF NOT EXISTS page_sort(value NUMERIC,id TEXT,record TEXT)")
        db.execute("DELETE FROM temp.page_sort")
        db.executemany("INSERT INTO temp.page_sort VALUES(?,?,?)",((ranking_value(r,metric),r["id"],json.dumps(r,ensure_ascii=False)) for r in matches()))
        selected=[json.loads(r[0]) for r in db.execute("SELECT record FROM temp.page_sort ORDER BY value IS NULL,value DESC,id LIMIT ? OFFSET ?",(limit,start))]
    return {**scope,"items":[{**r,"rank":start+i} for i,r in enumerate(selected,1)],"total":total,"page":page,"limit":limit}


def leaderboard(rows, kind, params, *, limit=None):
    sort, accepts = ranking_filter(kind, params)
    matches = (row for row in rows if accepts(row))
    order = ranking_order(sort)
    selected = sorted(matches,key=order) if limit is None else heapq.nsmallest(limit,matches,key=order)
    return [{**row, "rank":i} for i,row in enumerate(selected,1)]


class WideSum:
    """Sum nonnegative daily integer measures beyond SQLite's signed 64-bit limit."""
    def __init__(self):
        self.total = None

    def step(self, value):
        if value is not None:
            self.total = (self.total or 0) + value

    def finalize(self):
        if self.total is None or self.total < 2**63:
            return self.total
        # SQLite sorts blobs after integers. Fixed-width big-endian bytes preserve ordering
        # among large totals. A table has at most 2**63 rows, each holding at most 2**63-1.
        return self.total.to_bytes(16, "big")


def sum_rows(db, sql, params):
    try:
        return db.execute(sql, params).fetchall()
    except sqlite3.OperationalError as exc:
        if str(exc) != "integer overflow":
            raise
    db.create_aggregate("wide_sum", 1, WideSum)
    cursor = db.cursor()
    factory = cursor.row_factory
    def unpack(cursor, values):
        decoded = tuple(int.from_bytes(v, "big") if isinstance(v, bytes) else v for v in values)
        return factory(cursor, decoded) if factory else decoded
    cursor.row_factory = unpack
    return cursor.execute(sql.replace("SUM(", "wide_sum("), params).fetchall()


def daily_trend(db, s, item=None):
    if item:
        rows = db.execute("""SELECT date,gmv_units,sales,views,price_units FROM analytics_daily
                  WHERE source=:source AND market=:market AND date BETWEEN :start_date AND :date
                    AND kind=:kind AND id=:id ORDER BY date""",{**s,"kind":item["kind"],"id":item["id"]})
        points = []
        for stamp,gmv,sales,views,price in rows:
            point = {"date":stamp,"gmv":gmv/100,"sales":sales,"views":views,**exact_amounts(gmv=gmv)}
            if item["kind"]=="products":
                point.update(price=None if price is None else price/100, **exact_amounts(price=price))
            points.append(point)
        return points
    else:
        mode = """SELECT date,SUM(CASE WHEN kind='products' THEN gmv_units END) AS g,
                  SUM(CASE WHEN kind='products' THEN sales END) AS s,
                  SUM(CASE WHEN kind IN ('videos','lives') THEN views END) AS v
                  FROM analytics_daily WHERE source=:source AND market=:market
                    AND date BETWEEN :start_date AND :date AND (:category='' OR category=:category)
                  GROUP BY date ORDER BY date"""
        args = {"category":"",**s}
    return [{"date":stamp, "gmv":g/100 if g is not None else None, "sales":sales, "views":views,**exact_amounts(gmv=g)}
            for stamp,g,sales,views in sum_rows(db,mode,args)]


def overview_period(db, args):
    result = sum_rows(db,"""
        SELECT SUM(CASE WHEN kind='products' THEN gmv_units END),
               SUM(CASE WHEN kind='products' THEN sales END),
               SUM(CASE WHEN kind IN ('videos','lives') THEN views END),
               COUNT(DISTINCT CASE WHEN kind='creators' THEN id END),
               COUNT(DISTINCT CASE WHEN kind='products' THEN date END),
               COUNT(DISTINCT CASE WHEN kind IN ('videos','lives') AND views IS NOT NULL THEN date END),
               COUNT(DISTINCT CASE WHEN kind='creators' THEN date END),
               COUNT(DISTINCT CASE WHEN kind='products' AND sales>0 THEN id END),
               COUNT(DISTINCT CASE WHEN kind='shops' AND sales>0 THEN id END),
               COUNT(DISTINCT CASE WHEN kind='shops' THEN date END)
        FROM analytics_daily WHERE source=:source AND market=:market AND date BETWEEN :start_date AND :date
          AND (:category='' OR category=:category)
    """,args)[0]
    gmv,sales,views,creators,pdays,vdays,cdays,active_products,active_shops,sdays = result
    average = average_cents(gmv,sales) if sales else None
    return ({"gmv":None if gmv is None else gmv/100,"sales":sales,"views":views,
             "creators":creators if cdays else None, **exact_amounts(gmv=gmv)},
            {"gmv":pdays,"sales":pdays,"views":vdays,"creators":cdays},
            {"active_products":active_products if pdays else None, "active_shops":active_shops if sdays else None,
             "avg_price":average / 100 if average is not None else None, **exact_amounts(avg_price=average)})


def groups_for(db, s, group, include_examples=False):
    if group not in {"category", "tag", "music", "keyword", "script"}:
        raise ValueError("趋势分组不受支持")
    kind = "products" if group=="category" else "videos"
    # The allowlisted column is grouped at day grain so a changed attribution never rewrites the past.
    entries = [dict(r) for r in sum_rows(db,f"""
        SELECT {group} AS name,SUM(gmv_units) AS units,SUM(sales) AS sales,SUM(views) AS views,
               MAX(gmv_estimated=1) AS includes_estimates,
               COUNT(DISTINCT id) AS count FROM analytics_daily
        WHERE source=:source AND market=:market AND kind=:kind AND date BETWEEN :start_date AND :date AND {group}!=''
        GROUP BY {group} ORDER BY units DESC,name
    """,{**s,"kind":kind})]
    examples = {}
    if include_examples:
        example_sql = f"""
            WITH grouped AS (
              SELECT {group} AS label,id,date,name, SUM(gmv_units) OVER bucket AS units,
                SUM(sales) OVER bucket AS sales,SUM(views) OVER bucket AS views,
                ROW_NUMBER() OVER (PARTITION BY {group},id ORDER BY date DESC) AS latest
              FROM analytics_daily WHERE source=:source AND market=:market AND kind=:kind
                AND date BETWEEN :start_date AND :date AND {group}!=''
              WINDOW bucket AS (PARTITION BY {group},id)
            ), ranked AS (
              SELECT *, ROW_NUMBER() OVER (PARTITION BY label ORDER BY units DESC,id) AS position
              FROM grouped WHERE latest=1
            )
            SELECT label,id,name,units,sales,views FROM ranked WHERE position<=3 ORDER BY label,position
        """
        for label,ident,title,units,sales,views in db.execute(example_sql,{**s,"kind":kind}):
            examples.setdefault(label,[]).append({"id":ident,"name":title,"kind":kind,
                                                  "gmv":units/100,"sales":sales,"views":views,**exact_amounts(gmv=units)})
    total = sum_rows(db,"""SELECT SUM(gmv_units) FROM analytics_daily WHERE source=:source AND market=:market
        AND kind=:kind AND date BETWEEN :start_date AND :date""",{**s,"kind":kind})[0][0]
    for e in entries:
        units = e.pop("units")
        e["gmv"] = units/100
        e.update(exact_amounts(gmv=units))
        e["share"] = round(units/total*100,2) if total else None
        if include_examples:
            e["examples"] = examples.get(e["name"],[])
    return entries


def market_structure(rows):
    products = [r for r in rows if r["kind"]=="products"]
    total = sum(ranking_value(r,"gmv") for r in products)
    priced = sorted((r for r in products if r["price"] is not None),key=lambda r:(ranking_value(r,"price"),r["id"]))
    # Equal prices stay together even when several quartile boundaries coincide.
    bands = []
    offset = 0
    for quartile in (1,2,3,4):
        end = math.ceil(len(priced)*quartile/4)
        if end <= offset:
            continue
        while end<len(priced) and ranking_value(priced[end],"price")==ranking_value(priced[end-1],"price"):
            end+=1
        part = priced[offset:end]
        amount = sum(ranking_value(r,"gmv") for r in part)
        bands.append({"min":part[0]["price"],"max":part[-1]["price"],"count":len(part),
                      "gmv":amount/100,"sales":sum(r["sales"] for r in part),
                      **exact_amounts(gmv=amount,min=ranking_value(part[0],"price"),max=ranking_value(part[-1],"price")),
                      "share":round(amount/total*100,2) if total else None})
        offset = end
    concentration = {"product_count":len(products),"top3_share":None,
                     "shop_count":0,"shop_top3_share":None}
    if total:
        concentration["top3_share"] = round(sum(sorted((ranking_value(r,"gmv") for r in products),reverse=True)[:3])/total*100,2)
    shop_values = sorted((ranking_value(r,"gmv") for r in rows if r["kind"]=="shops"),reverse=True)
    concentration["shop_count"] = len(shop_values)
    if sum(shop_values):
        concentration["shop_top3_share"] = round(sum(shop_values[:3])/sum(shop_values)*100,2)
    return {"price_bands":bands,"concentration":concentration}


def product_video_links(db, scope, kind, ident):
    """Window-scoped links observed on video days, without inferring product sales."""
    if kind == "products":
        match, other, related_kind = "product_id", "id", "videos"
    elif kind == "videos":
        match, other, related_kind = "id", "product_id", "products"
    else:
        return []
    links = db.execute(f"""
        WITH links AS (
          SELECT {other} AS linked_id,MIN(date) AS first_seen,MAX(date) AS last_seen,COUNT(*) AS linked_days
          FROM analytics_daily WHERE source=:source AND market=:market AND kind='videos'
            AND product_id!='' AND {match}=:ident AND date BETWEEN :start_date AND :date GROUP BY {other}
        )
        SELECT d.id,d.name,d.kind,d.image_key,l.first_seen,l.last_seen,l.linked_days FROM links l
        JOIN analytics_daily d ON d.source=:source AND d.market=:market AND d.kind=:related_kind AND d.id=l.linked_id
          AND d.date=(SELECT MAX(s.date) FROM analytics_daily s WHERE s.source=:source AND s.market=:market
            AND s.kind=:related_kind AND s.id=l.linked_id AND s.date BETWEEN :start_date AND :date)
        ORDER BY l.last_seen DESC,l.linked_days DESC,d.id""", {**scope,"related_kind":related_kind,"ident":ident})
    return [dict(row) for row in links]


def related_to(target, rows, db, scope):
    field = {"products":"product_id","shops":"shop_id","creators":"creator_id"}
    counterpart = {"products":"videos","videos":"products"}.get(target["kind"])
    observed = {r["id"]:r for r in product_video_links(db,scope,target["kind"],target["id"])}
    result = []
    for candidate in rows:
        if candidate["kind"] == target["kind"]:
            continue
        if candidate["kind"] == counterpart:
            if candidate["id"] in observed:
                result.append({**candidate, **observed[candidate["id"]]})
            continue
        inward = field.get(target["kind"])
        outward = field.get(candidate["kind"])
        if ((inward and candidate[inward] == target["id"]) or
                (outward and target[outward] == candidate["id"])):
            result.append(candidate)
    return sorted(result,key=lambda r:(KINDS.index(r["kind"]),-ranking_value(r,"gmv"),r["id"]))


def live_analysis(db, scope, item, rows, ranking):
    products = {r["id"]:r for r in rows if r["kind"]=="products"}
    attributed = {}
    snapshots = db.execute("""SELECT date,product_id,profile_json FROM analytics_daily
        WHERE source=:source AND market=:market AND kind='lives' AND id=:id
          AND date BETWEEN :start_date AND :date ORDER BY date""", {**scope,"id":item["id"]})
    for day, product_id, raw in snapshots:
        profile = json.loads(raw) if raw else {}
        links = {p["id"]:p for p in profile.get("live_products",())}
        if product_id:
            links.setdefault(product_id,{})
        for identifier, metrics in links.items():
            entry = attributed.setdefault(identifier, {
                "id":identifier, "name":products[identifier]["name"] if identifier in products else None,
                "first_seen":day,"last_seen":day,"days":0,"sales":0,"gmv":Decimal(0)})
            entry["days"] += 1
            entry["last_seen"] = day
            for key in ("sales","gmv"):
                value = metrics.get(key)
                if value is None:
                    entry[key] = None
                elif entry[key] is not None:
                    entry[key] += Decimal(str(value)) if key=="gmv" else value
    for entry in attributed.values():
        if entry["gmv"] is not None:
            cents = int(entry["gmv"] * 100)
            if cents >= EXACT_MONEY_THRESHOLD:
                entry["gmv_exact"] = money_text(cents)
            entry["gmv"] = float(entry["gmv"])
    similar = [r for r in ranking if r["id"]!=item["id"] and item["category"] and r["category"]==item["category"]][:5]
    return {"products":list(attributed.values()),"similar":similar}


def board_live(db, scope, rows, top, requested):
    if not top:
        return {"rooms":[],"room":None}
    catalog = {(r["kind"],r["id"]):r for r in rows}
    rooms, snapshots = [], {}
    for row in top:
        raw = db.execute("""SELECT profile_json FROM analytics_daily WHERE source=:source AND market=:market
            AND kind='lives' AND id=:id AND date=:updated_at""",{**scope,**row}).fetchone()[0]
        snapshots[row["id"]] = json.loads(raw) if raw else {}
        session = snapshots[row["id"]].get("live_session",{})
        rooms.append({"id":row["id"],"name":row["name"],"rank":row["rank"],"period_gmv":row["gmv"],
                      "period_estimated":None if row["gmv_estimated"] is None else bool(row["gmv_estimated"]),
                      "session_gmv":session.get("gmv"),"enter_count":session.get("enter_count")})
    identifier = requested if requested in snapshots else rooms[0]["id"]
    room = catalog["lives",identifier]
    profile = snapshots[identifier]
    session = profile.get("live_session",{})
    products = []
    for p in sorted((p for p in session.get("products",()) if p["sales"] is not None),
                    key=lambda p:(-p["sales"],p["id"]))[:3]:
        product = catalog.get(("products",p["id"]),{})
        products.append({**p,"name":product.get("name")})
    similar = leaderboard((r for r in rows if r["id"]!=identifier and room["category"] and r["category"]==room["category"]),
                          "lives",{},limit=5)
    daily_ids = dict.fromkeys([room["product_id"],*(p["id"] for p in profile.get("live_products",()))])
    daily_links = [{"id":p,"name":catalog.get(("products",p),{}).get("name")} for p in daily_ids if p]
    creator_id = room["creator_id"]
    return {"rooms":rooms,"room":{"id":identifier,"name":room["name"],"category":room["category"],
             "day":room["updated_at"],"creator":{"id":creator_id,"name":catalog.get(("creators",creator_id),{}).get("name")} if creator_id else None,
             "start_at":session.get("start_at"),"end_at":session.get("end_at"),"gmv":session.get("gmv"),
             "enter_count":session.get("enter_count"),"products":products,"daily_links":daily_links,
             "similar":[{"id":r["id"],"name":r["name"]} for r in similar],
             "series":session.get("online_viewers",[]),"series_basis":"session","series_source":"snapshot"}}


def exchange_rates(end):
    """Rates express base-currency units per local currency unit on the exact requested day."""
    path = os.environ.get("TIKFLOWSO_FX_RATES")
    if not path:
        return None, {}
    try:
        config = json.loads(Path(path).read_text(encoding="utf-8-sig"))
        base = config["base_currency"]
        sheet = config["dates"].get(end,{})
        if not isinstance(base,str) or not re.fullmatch(r"[A-Z]{3}",base) or not isinstance(sheet,dict):
            raise ValueError
        if not sheet:
            return base, {}
        rates = {}
        for code,raw in sheet.items():
            value = Decimal(str(raw))
            if not re.fullmatch(r"[A-Z]{3}",code) or not value.is_finite() or not 0 < value <= 10**8:
                raise ValueError
            rates[code] = value
        if base in rates and rates[base] != 1:
            raise ValueError
        rates[base] = Decimal(1)
        return base, rates
    except (OSError,KeyError,AttributeError,TypeError,ValueError,InvalidOperation):
        raise ValueError("本地汇率配置无法读取或数值无效") from None


def market_comparison(db,params):
    source = params.get("source") or "demo"
    latest = db.execute("SELECT MAX(date) FROM analytics_daily WHERE source=?",(source,)).fetchone()[0]
    scoped = {**params,"market":"US","date":params.get("date") or latest}
    scope = scope_for(db,scoped)
    base,rates = exchange_rates(scope["date"])
    samples = sum_rows(db,"""
        WITH available AS (
          SELECT DISTINCT market FROM analytics_entities WHERE source=:source
        ), totals AS (
          SELECT market,SUM(CASE WHEN kind='products' THEN gmv_units END) AS units,
            MAX(CASE WHEN kind='products' THEN gmv_estimated=1 END) AS includes_estimates,
            SUM(CASE WHEN kind='products' THEN sales END) AS sales,
            COUNT(DISTINCT CASE WHEN kind='products' THEN id END) AS product_count,
            COUNT(DISTINCT CASE WHEN kind='shops' THEN id END) AS shop_count,
            COUNT(DISTINCT CASE WHEN kind='creators' THEN id END) AS creator_count,
            COUNT(DISTINCT CASE WHEN kind='products' THEN date END) AS covered_days
          FROM analytics_daily WHERE source=:source AND date BETWEEN :start_date AND :date GROUP BY market
        ) SELECT a.market, units,sales,includes_estimates,COALESCE(product_count,0) AS product_count,
            COALESCE(shop_count,0) AS shop_count,COALESCE(creator_count,0) AS creator_count,
            COALESCE(covered_days,0) AS covered_days
          FROM available a LEFT JOIN totals USING(market) ORDER BY sales DESC,a.market
    """,scope)
    items = []
    for sample in samples:
        row = dict(sample)
        units = row.pop("units")
        name,currency = MARKETS[row["market"]]
        rate = rates.get(currency)
        amount = Decimal(units)/100 if units is not None else None
        converted = round(amount*rate,2) if amount is not None and rate is not None else None
        average = average_cents(units,row["sales"]) if row["sales"] else None
        items.append({**row,"name":name,"currency":currency,"gmv":float(amount) if amount is not None else None,
                      "avg_price":average / 100 if average is not None else None, **exact_amounts(gmv=units,avg_price=average),
                      "base_currency":base,"fx_rate":float(rate) if rate is not None else None,
                      "fx_date":scope["date"] if rate is not None else None,
                      "gmv_converted":float(converted) if converted is not None else None})
    return {k:scope[k] for k in ("source","date","start_date","days")} | {"items":items,"base_currency":base}


def handle(db, path, params):
    if path == "/api/markets":
        return market_comparison(db,params)
    if path not in {"/api/meta","/api/rankings","/api/overview","/api/detail","/api/trends"}:
        return None
    scope = scope_for(db, params)
    if path == "/api/meta":
        return meta(db,scope)
    if path == "/api/trends":
        group = params.get("group") or "category"
        extra = market_structure(rows_for(db,scope)) if group=="category" else {}
        return {**scope,"group":group,"items":groups_for(db,scope,group,include_examples=True),**extra}
    if path=="/api/rankings": return ranking_page(db,scope,params)
    rows = rows_for(db,scope)
    if path == "/api/overview":
        if params.get("live_only")=="1":
            return {**scope,"live_preview":board_live(db,scope,rows,leaderboard(rows,"lives",{},limit=5),params.get("room"))}
        rankings = {kind:leaderboard(rows,kind,{},limit=5) for kind in KINDS}
        category_scope = {**scope,"category":params.get("category") or ""}
        metrics, covered, activity = overview_period(db,category_scope)
        previous, previous_coverage, _ = overview_period(db,{**category_scope,"start_date":scope["prev_date"],
                                          "date":(date.fromisoformat(scope["start_date"])-timedelta(days=1)).isoformat()})
        changes = {k: period_growth(metrics[k],previous[k]) if covered[k]==previous_coverage[k]==scope["days"] else None
                   for k in covered}
        result = {**category_scope,"metrics":metrics,"changes":changes,"coverage":covered,"activity":activity,
                  "trend":daily_trend(db,category_scope),"rankings":rankings,"categories":groups_for(db,scope,"category")}
        if params.get("board") == "1":
            result["live_preview"] = board_live(db,scope,rows,rankings["lives"],params.get("room"))
            boards = [
                ("热销商品","products","sales",""), ("本地热销店铺","shops","sales","local"),
                ("带货达人","creators","sales",""), ("涨粉达人","creators","follower_growth",""),
                ("带货视频","videos","sales",""), ("直播成交榜","lives","gmv","")
            ]
            result["boards"] = []
            for title,kind,sort,segment in boards:
                filters = {"sort":sort,"segment":segment}
                top = rankings[kind] if sort=="gmv" and not segment else leaderboard(rows,kind,filters,limit=5)
                result["boards"].append({"title":title,"kind":kind,**filters,
                                         "items":[r for r in top if r[sort] is not None]})
        return result
    kind = params.get("kind") or "products"
    if path == "/api/detail":
        ranking = leaderboard(rows,kind,{})
        item = next((r for r in ranking if r["id"]==params.get("id")),None)
        if not item:
            raise LookupError("当前市场和时间范围内没有此对象")
        raw = db.execute("""SELECT profile_json FROM analytics_daily WHERE source=:source AND market=:market
                           AND kind=:kind AND id=:id AND date=:updated_at""",{**scope,**item}).fetchone()
        item["profile"] = json.loads(raw[0]) if raw and raw[0] else {}
        if "reviews" in item["profile"]:
            from insights import sentiment
            item["review_sentiment"]=sentiment(item["profile"]["reviews"])
        result = {**scope,"item":item,"trend":daily_trend(db,scope,item),"related":related_to(item,rows,db,scope)}
        if kind=="lives":
            result["live_analysis"] = live_analysis(db,scope,item,rows,ranking)
        return result
    raise LookupError("未知排行接口")


def main():
    import settings
    settings.load()
    parser = argparse.ArgumentParser(description="tikflowso 授权日快照导入。CSV 使用 UTF-8；JSON 为对象数组。")
    parser.add_argument("file", type=Path)
    parser.add_argument("--source",required=True,help="数据源稳定标识，demo 保留")
    parser.add_argument("--db",required=True,type=Path,help="tikflowso SQLite 文件")
    visibility = parser.add_mutually_exclusive_group()
    visibility.add_argument("--owner",type=int,help="可查阅数据的工作区所有者 ID")
    visibility.add_argument("--shared",action="store_true",help="明确公开给全部工作区及访客")
    args = parser.parse_args()
    try:
        from io import StringIO
        if args.file.stat().st_size>64*1024*1024: raise ValueError("单个文件超过 64 MiB，请分批导入")
        payload=args.file.read_bytes()
        try: text=payload.decode("utf-8-sig")
        except UnicodeDecodeError:
            if args.file.suffix.lower()!=".csv": raise
            text=payload.decode("gb18030")
        with sqlite3.connect(args.db) as db, StringIO(text,newline="") as stream:
            init(db)
            if args.file.suffix.lower() == ".csv":
                records = csv_rows(stream)
            elif args.file.suffix.lower() == ".json":
                records = json.load(stream, parse_float=Decimal)
                if not isinstance(records,list):
                    raise ValueError("JSON 须为记录数组")
            else:
                raise ValueError("文件类型须为 CSV 或 JSON")
            print(json.dumps(import_rows(db,records,args.source,owner=args.owner,shared=args.shared),ensure_ascii=False))
    except (ValueError,OSError,sqlite3.Error,csv.Error) as error:
        parser.exit(1,f"导入失败：{error}\n")


if __name__ == "__main__":
    main()

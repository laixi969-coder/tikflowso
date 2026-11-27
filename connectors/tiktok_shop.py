"""Collect authorized TikTok Shop product performance as complete, daily feed files."""
import argparse
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from decimal import Decimal
import fcntl
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import secrets
import tempfile
import time
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlencode, urlsplit
from urllib.request import build_opener, ProxyHandler, Request
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import analytics
from connectors.delivery import delivery_lock
from feeds import MAX_BYTES
from transport import NoRedirect

API = "https://open-api.tiktokglobalshop.com"
AUTH = "https://auth.tiktok-shops.com"
SHOPS = "/authorization/202309/shops"
PRODUCTS = "/analytics/202605/shop_products/performance"


def signature(path, params, secret):
    fields = "".join(key + str(params[key]) for key in sorted(params) if key not in {"sign", "access_token"})
    return hmac.new(secret.encode(), (secret + path + fields + secret).encode(), hashlib.sha256).hexdigest()


def get_json(base, path, params, token=None, *, retry=False):
    headers = {"Content-Type":"application/json", "Accept":"application/json"}
    if token:
        headers["x-tts-access-token"] = token
    request = Request(base + path + "?" + urlencode(params), headers=headers)
    handlers = [NoRedirect()]
    if urlsplit(base).hostname in {"127.0.0.1","::1"}:
        handlers.append(ProxyHandler({}))
    opener = build_opener(*handlers)
    attempts = 3 if retry else 1
    for attempt in range(attempts):
        try:
            with opener.open(request, timeout=20) as response:
                raw = response.read(MAX_BYTES + 1)
                if len(raw) > MAX_BYTES:
                    raise ValueError("API page exceeds size limit")
                payload = json.loads(raw, parse_float=Decimal)
            break
        except HTTPError as error:
            status = error.code
            delay = error.headers.get("Retry-After", "")
            error.close()
            if status not in {429, 500, 502, 503, 504} or attempt + 1 == attempts:
                raise ValueError(f"TikTok Shop HTTP {status} at {path}") from None
            seconds = int(delay) if delay.isascii() and delay.isdigit() else 2**attempt
            if seconds > 30:
                raise ValueError(f"TikTok Shop HTTP {status}; retry after {seconds}s") from None
            time.sleep(seconds)
        except (URLError, TimeoutError, OSError):
            if attempt + 1 == attempts:
                raise ValueError(f"TikTok Shop connection failed at {path}") from None
            time.sleep(2**attempt)
    if not isinstance(payload, dict) or type(payload.get("code")) is not int or payload["code"] != 0:
        code = payload.get("code") if isinstance(payload,dict) else None
        raise ValueError(f"TikTok Shop API rejected {path} (code {code if type(code) is int else 'unknown'})")
    if not isinstance(payload.get("data"), dict):
        raise ValueError(f"TikTok Shop response lacks data at {path}")
    return payload["data"]


def atomic(path, content):
    with tempfile.NamedTemporaryFile(dir=path.parent, prefix=".pending-", delete=False) as handle:
        tmp = Path(handle.name)
        try:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        except BaseException:
            tmp.unlink(missing_ok=True)
            raise
    try:
        os.replace(tmp, path)
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        tmp.unlink(missing_ok=True)


def write_json(path, value):
    atomic(path, json.dumps(value, ensure_ascii=False, sort_keys=True).encode())


def load(path):
    return json.loads(path.read_bytes())


def needed_env(name):
    value = os.environ.get(name)
    if not value:
        raise ValueError("Missing environment variable " + name)
    return value


def configure(settings):
    source = settings["source"]
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", source) or source.lower() == "demo":
        raise ValueError("Set a dedicated source ID")
    market = settings["market"]
    if market not in analytics.MARKETS or market == "CN":
        raise ValueError("Expected a supported TikTok Shop market, excluding mainland Douyin")
    if not isinstance(settings["shop_id"], str) or not re.fullmatch(r"[0-9]{1,64}", settings["shop_id"]):
        raise ValueError("shop_id must be a string of digits")
    ZoneInfo(settings["timezone"])
    analytics.iso_day(settings["start_date"])
    folder = Path(settings["directory"])
    private = Path(settings["private_dir"])
    delivery = folder.resolve()
    credentials = private.resolve()
    if (not folder.is_absolute() or not private.is_absolute() or delivery.is_relative_to(credentials)
            or credentials.is_relative_to(delivery)):
        raise ValueError("Use disjoint absolute private_dir and feed directory paths")
    lookback = settings.get("lookback_days", 2)
    if type(lookback) is not int or not 0 <= lookback <= 366:
        raise ValueError("lookback_days must be an integer between 0 and 366")
    return folder, private


@contextmanager
def locked(folder):
    folder.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (folder / ".seller-token.lock").open("a") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        yield


def scope_of(config):
    return {key: config[key] for key in ("source","market","shop_id","timezone")}


class Shop:
    def __init__(self, config, private, app_key, secret, fixture=None):
        self.config, self.key, self.secret = config, app_key, secret
        self.tokens = private / "seller-tokens.json"
        self.state = private / "pending-authorization.json"
        self.api, self.auth = API, AUTH
        if fixture:
            parts = urlsplit(fixture)
            if (parts.scheme != "http" or parts.hostname not in {"127.0.0.1","::1"}
                    or parts.username or parts.password or parts.path not in {"","/"} or parts.query or parts.fragment):
                raise ValueError("The fixture server must be a loopback HTTP origin")
            self.api = self.auth = fixture.rstrip("/")
        self.identity = {**scope_of(config), "app_key":app_key, "api":self.api}

    def authorize_url(self):
        uri = urlsplit(self.config["authorization_url"])
        host = "services.us.tiktokshop.com" if self.config["market"] == "US" else "services.tiktokshop.com"
        if (uri.scheme != "https" or uri.hostname != host
                or uri.username or uri.password or uri.port not in {None,443} or uri.path != "/open/authorize" or uri.fragment):
            raise ValueError("Use the seller authorization link issued in Partner Center")
        query = parse_qs(uri.query, keep_blank_values=True)
        if len(query.get("service_id", [])) != 1 or not query["service_id"][0]:
            raise ValueError("Partner Center authorization link is missing service_id")
        redirect = urlsplit(self.config["redirect_uri"])
        if redirect.scheme != "https" or not redirect.hostname or redirect.username or redirect.password or redirect.query or redirect.fragment:
            raise ValueError("Configure the registered HTTPS redirect URI without query or fragment")
        nonce = secrets.token_urlsafe(32)
        write_json(self.state, {"state":nonce, "expires":int(time.time())+600, "redirect":redirect.geturl(), "identity":self.identity})
        return uri._replace(query=urlencode({**query, "state":[nonce]}, doseq=True)).geturl()

    def token_request(self, grant, value, previous=None):
        refresh = grant == "refresh_token"
        path = "/api/v2/token/refresh" if refresh else "/api/v2/token/get"
        params = {"app_key":self.key,"app_secret":self.secret,"grant_type":grant,
                  "refresh_token" if refresh else "auth_code":value}
        data = get_json(self.auth, path, params)
        if not all(isinstance(data.get(k),str) and data[k] for k in ("access_token","refresh_token","open_id")):
            raise ValueError("Seller token response is incomplete")
        if type(data.get("user_type")) is not int or data["user_type"] != 0:
            raise ValueError("Expected a seller authorization")
        for k in ("access_token_expire_in","refresh_token_expire_in"):
            if type(data.get(k)) is not int or data[k] <= time.time():
                raise ValueError("Token expiration field is invalid: " + k)
        if previous and data["open_id"] != previous["open_id"]:
            raise ValueError("Refreshed token belongs to a different seller")
        result = {key:data[key] for key in ("access_token","refresh_token","access_token_expire_in","refresh_token_expire_in","open_id")}
        result["identity"] = self.identity
        return result

    def authorize(self, callback):
        pending = load(self.state)
        url = urlsplit(callback)
        fields = parse_qs(url.query)
        state = fields.get("state", [])
        if (pending["identity"] != self.identity or pending["expires"] <= time.time()
                or url._replace(query="",fragment="").geturl() != pending["redirect"]
                or len(state) != 1 or not hmac.compare_digest(state[0], pending["state"])
                or len(fields.get("code",[])) != 1 or "error" in fields):
            raise ValueError("Authorization callback is invalid, expired or declined")
        tokens = self.token_request("authorized_code", fields["code"][0])
        self.authorized_shop(tokens["access_token"])
        write_json(self.tokens, tokens)
        self.state.unlink()

    def access(self):
        tokens = load(self.tokens)
        if tokens["identity"] != self.identity:
            raise ValueError("Use the token directory bound to this shop and app")
        if tokens["access_token_expire_in"] > time.time() + 60:
            return tokens["access_token"]
        if tokens["refresh_token_expire_in"] <= time.time():
            raise ValueError("Seller refresh token has expired; repeat authorization")
        renewed = self.token_request("refresh_token", tokens["refresh_token"], tokens)
        write_json(self.tokens, renewed)
        return renewed["access_token"]

    def call(self, path, params, token=None):
        token = token or self.access()
        params = {**params, "app_key":self.key, "timestamp":int(time.time())}
        params["sign"] = signature(path, params, self.secret)
        return get_json(self.api, path, params, token, retry=True)

    def authorized_shop(self, token=None):
        shops = self.call(SHOPS, {}, token).get("shops")
        if not isinstance(shops, list):
            raise ValueError("Invalid authorized shops response")
        matching = [row for row in shops if isinstance(row, dict) and row.get("id") == self.config["shop_id"]]
        if (len(matching) != 1 or matching[0].get("region") != self.config["market"]
                or not isinstance(matching[0].get("cipher"),str) or not matching[0]["cipher"]):
            raise ValueError("Configured shop and market do not match an authorized shop")
        return matching[0]["cipher"]

    def day(self, day, cipher):
        market = self.config["market"]
        params = {"shop_cipher":cipher, "start_date_ge":day.isoformat(),
                  "end_date_lt":(day+timedelta(days=1)).isoformat(),"currency":"LOCAL","page_size":100,
                  "product_status_filter":"ALL"}
        rows, seen_tokens = {}, set()
        count = None
        size = 2
        while True:
            payload = self.call(PRODUCTS, params)
            if analytics.iso_day(payload.get("latest_available_date")) < day:
                raise ValueError(f"{day}: product performance is not ready")
            total = payload.get("total_count")
            batch = payload.get("products")
            if (type(total) is not int or total < 0 or not isinstance(batch,list)
                    or (count is not None and total != count)):
                raise ValueError(f"{day}: invalid or changing paginated result")
            count = total
            for product in batch:
                if not isinstance(product,dict) or not isinstance(product.get("total_performance"),dict):
                    raise ValueError(f"{day}: missing product performance")
                pid, perf = product.get("id"), product["total_performance"]
                if not isinstance(pid,str) or not pid or pid != pid.strip() or pid in rows:
                    raise ValueError(f"{day}: missing or duplicated product ID")
                amount = perf.get("gmv")
                if not isinstance(amount,dict) or amount.get("currency") != analytics.MARKETS[market][1]:
                    raise ValueError(f"{day}: reported GMV currency differs from the shop market")
                # The performance API supplies a stable product ID but no title.
                row = {"kind":"products","id":pid,"name":pid,"market":market,"shop_id":self.config["shop_id"],
                       "date":day.isoformat(),"gmv":str(amount["amount"]),
                       "sales":analytics.numeric(perf["items_sold"], "items_sold", required=True)}
                for upstream, column in (("orders","orders"), ("refunded_items","refund_units")):
                    if perf.get(upstream) is not None:
                        row[column] = analytics.numeric(perf[upstream], column)
                analytics.normalized(row, self.config["source"])
                size += len(json.dumps(row, ensure_ascii=False, separators=(",",":")).encode()) + bool(rows)
                if size > MAX_BYTES:
                    raise ValueError(f"{day}: snapshot exceeds the feed delivery size")
                rows[pid] = row
            page = payload.get("next_page_token")
            if page is None or page == "":
                if len(rows) != count:
                    raise ValueError(f"{day}: incomplete product list")
                return [rows[pid] for pid in sorted(rows)]
            if not isinstance(page,str) or page in seen_tokens or not batch or len(rows) >= count:
                raise ValueError(f"{day}: pagination failed to advance")
            seen_tokens.add(page)
            params["page_token"] = page


def sync(shop, folder, since=None, until=None):
    with delivery_lock(folder, "tiktok_shop"):
        return collect_locked(shop, folder, since, until)


def collect_locked(shop, folder, since, until):
    cfg = shop.config
    first = analytics.iso_day(since or cfg["start_date"])
    today = datetime.now(ZoneInfo(cfg["timezone"])).date()
    last = analytics.iso_day(until) if until else today - timedelta(days=1)
    if first > last or last >= today:
        raise ValueError("Select completed reporting days in the configured shop timezone")
    cipher = shop.authorized_shop()
    checkpoint = folder / ".tiktok-shop.json"
    if not checkpoint.exists():
        if any(p.suffix.lower() in {".json",".csv"} and not p.name.startswith(".") for p in folder.iterdir()):
            raise ValueError("New collector needs a dedicated, empty feed directory")
        write_json(checkpoint, {"identity":shop.identity, "days":{}})
    state = load(checkpoint)
    if state["identity"] != shop.identity:
        raise ValueError("Feed directory belongs to another collection scope")
    previous = [date.fromisoformat(day) for day in state["days"] if day <= last.isoformat()]
    lookback = cfg.get("lookback_days", 2)
    refresh_from = max(previous) - timedelta(days=lookback-1) if previous else first
    counts = {"checked":0,"published":0,"empty":0,"skipped":0}
    for offset in range((last-first).days+1):
        day = first+timedelta(days=offset)
        key = day.isoformat()
        file = folder / (key + ".json")
        receipt = state["days"].get(key)
        stamp = file.stat().st_mtime_ns if file.exists() else None
        if since is None and receipt and day < refresh_from and receipt.get("mtime_ns") == stamp and (
                not receipt["rows"] or stamp is not None):
            counts["skipped"] += 1
            continue
        rows = shop.day(day, cipher)
        counts["checked"] += 1
        content = json.dumps(rows, ensure_ascii=False, separators=(",",":")).encode()
        if len(content) > MAX_BYTES:
            raise ValueError(f"{day}: snapshot exceeds the feed delivery size")
        digest = hashlib.sha256(content).hexdigest()
        old = file.read_bytes() if file.exists() else None
        old_digest = hashlib.sha256(old).hexdigest() if old is not None else None
        # A rerun can repair a lost file matching the receipt, or finish checkpointing a published file.
        # With two different revisions and no original, we cannot detect removed IDs safely.
        known = receipt["sha256"] if receipt else None
        if receipt and receipt["rows"] and digest != known and old_digest not in {known, digest}:
            raise ValueError(f"{day}: restore the previous delivery to verify the revised product set")
        if old is not None and not rows:
            raise ValueError(f"{day}: all previously published products disappeared; retained prior delivery")
        if old is not None and old_digest != digest:
            missing = {row["id"] for row in json.loads(old)} - {row["id"] for row in rows}
            if missing:
                raise ValueError(f"{day}: {len(missing)} previously published products disappeared; retained prior delivery")
        if not rows:
            counts["empty"] += 1
        elif old != content:
            atomic(file, content)
            counts["published"] += 1
        updated = {"rows":len(rows), "sha256":digest, "mtime_ns":file.stat().st_mtime_ns if rows else None}
        if receipt != updated:
            state["days"][key] = updated
            write_json(checkpoint, state)
    return {**scope_of(cfg), "since":str(first),"until":str(last), **counts}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--fixture-url", help="offline acceptance server, loopback HTTP only")
    commands = parser.add_subparsers(dest="action",required=True)
    commands.add_parser("authorize-url", help="create a seller consent link with one-time state")
    commands.add_parser("authorize", help="exchange the callback URL supplied in TIKTOK_SHOP_CALLBACK_URL")
    job = commands.add_parser("sync", help="incremental pull or explicit date-range backfill")
    job.add_argument("--since", help="force a backfill from this shop reporting date")
    job.add_argument("--until", help="inclusive, defaults to yesterday in shop registered timezone")
    args = parser.parse_args()
    try:
        cfg = load(args.config)
        folder, private = configure(cfg)
        with locked(private):
            secret = needed_env("TIKTOK_SHOP_APP_SECRET") if args.action != "authorize-url" else ""
            shop = Shop(cfg, private, needed_env("TIKTOK_SHOP_APP_KEY"), secret, args.fixture_url)
            if args.action == "authorize-url":
                print(shop.authorize_url())
            elif args.action == "authorize":
                shop.authorize(needed_env("TIKTOK_SHOP_CALLBACK_URL"))
                print("Seller token saved")
            else:
                result = sync(shop, folder, args.since, args.until)
                print(json.dumps(result, ensure_ascii=False))
    except (ValueError, TypeError, KeyError, OSError, ZoneInfoNotFoundError) as error:
        parser.exit(1, f"Collection stopped: {error}\n")


if __name__ == "__main__":
    main()

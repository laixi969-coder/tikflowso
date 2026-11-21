"""Operator commands for cloud model catalogs, inference probes, and service connectivity."""
import argparse
import json
import os
from pathlib import Path
import re
import smtplib
import sys
import time
from urllib import request
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit

import billing
import cli
import feeds
import notifications
import settings
import control_settings
import studio
import transcription
import vision

ROOT=settings.ROOT


def sync_one(provider,public_only=False,*,directory=None):
    conf=vision.profile(provider)
    has_key=bool(vision.credential(provider)) and not public_only
    for attempt in range(3):
        try:
            data=vision.call("models",timeout=45,require_key=has_key,provider=provider)
            break
        except vision.RequestError as exc:
            cause=exc.__cause__
            if isinstance(cause,HTTPError):
                if cause.code in (401,403) and not has_key:
                    return {"provider":provider,"state":"pending_key","http":cause.code,"selected":conf["model"]}
                raise
            if attempt==2:raise
    rows=data.get("data",[])
    ids=sorted({r["id"] for r in rows if isinstance(r,dict) and isinstance(r.get("id"),str)})
    if not ids: raise ValueError("服务商未返回兼容的模型目录")
    entries=[]
    for r in rows:
        if not isinstance(r,dict) or r.get("id") not in ids: continue
        architecture=r.get("architecture") or {}
        entries.append({"id":r["id"],"created":r.get("created") if isinstance(r.get("created"),int) else None,
                        "inputs":r.get("input_modalities") or architecture.get("input_modalities") or []})
    entries.sort(key=lambda x:(-(x["created"] or 0),x["id"]))
    name=conf["model"]
    result={"provider":provider,"state":"catalog_synced","count":len(ids),"selected":name,"listed":name in ids,
            "synced_at":int(time.time()),"base_url":conf["base"],"authenticated":has_key}
    dest=(directory or ROOT/".data/vision/catalogs")/(provider+".json")
    dest.parent.mkdir(parents=True,exist_ok=True)
    import tempfile
    with tempfile.NamedTemporaryFile("w",dir=dest.parent,delete=False) as f:
        json.dump({**result,"models":ids,"entries":entries},f,ensure_ascii=False)
    os.replace(f.name,dest)
    return result


def sample_probe(provider):
    import base64
    image=base64.b64encode((ROOT/"qa/samples/vision/en.png").read_bytes()).decode()
    result=vision.ask("Read the first printed line as 'title'.","data:image/png;base64,"+image,vision.object_schema({"title":vision.STRING}),provider,task=None)
    if result.get("title","").strip().lower()!="green tea":raise ValueError("未正确识别样例文字")
    return {"title":result["title"],"model":vision.profile(provider)["model"]}


def ping_stripe():
    for price in (os.environ["STRIPE_PRICE_PRO"],os.environ["STRIPE_PRICE_TEAM"]):
        if not re.fullmatch(r"price_[A-Za-z0-9]+",price): raise ValueError("价格 ID 无效")
        result=billing._stripe("prices/"+price)
        if not result.get("active") or not result.get("recurring"): raise ValueError("价格尚未启用或不是周期订阅")
    return "两个周期价格可读；Webhook 签名需通过事件验收"


def check(external=False):
    rows=[]
    def probe(name,fn,enabled=True,pending="待配置"):
        if not enabled:
            rows.append({"service":name,"state":"pending","detail":pending})
            return
        try:
            result=fn()
            rows.append({"service":name,"state":"ok","detail":result})
        except Exception as exc:
            # Do not print provider response bodies, credential-bearing URLs, or secrets.
            rows.append({"service":name,"state":"failed","detail":type(exc).__name__})
    base=os.getenv("TIKFLOWSO_URL","http://127.0.0.1:8765").rstrip("/")
    def health():
        with request.urlopen(base+"/health",timeout=5) as r:
            if json.load(r).get("status")!="ok": raise ValueError("服务未就绪")
        return "HTTP /health"
    probe("tikflowso",health)
    probe("cloud_model_catalog",lambda:sync_one(vision.selected()),
          vision.status()=="configured","待填写所选平台的云端 API key")
    def whisper():
        if not transcription.available(): raise ValueError("本机引擎或权重缺失")
        return "FFmpeg、whisper-cli 和权重已就绪"
    probe("whisper",whisper)
    probe("workspace_api",lambda: "meta 可读" if cli.query("meta",{}) else "meta 已连接",bool(os.getenv("TIKFLOWSO_API_KEY")),"待创建工作区只读密钥")
    if external:
        def stripe_network():
            for attempt in range(3):
              try:
                with request.urlopen("https://api.stripe.com/v1/prices?limit=1",timeout=20) as response:
                    return f"HTTPS {response.status}"
              except HTTPError as exc:
                if exc.code!=401: raise
                return "HTTPS 401，已连通；本次探测未使用凭证"
              except (URLError,TimeoutError):
                if attempt==2: raise
        probe("stripe_public_gateway",stripe_network)
    probe("stripe_prices",ping_stripe,billing._enabled(),"待填商户密钥、Webhook 签名密钥和两种价格 ID")
    probe("optional_text_model",lambda: bool(studio.infer("Reply OK.","Ping",[])),studio.model_configured(),"待填兼容端点、模型名及供应商要求的密钥")
    def source_check():
        specs=feeds.valid_config(json.loads(Path(os.environ["TIKFLOWSO_FEEDS"]).read_text()))
        for spec in specs:
            if spec.get("directory") and not Path(spec["directory"]).is_dir(): raise ValueError()
            if spec.get("url"):
                req=request.Request(spec["url"],method="HEAD")
                if spec.get("token_env"): req.add_header("Authorization","Bearer "+os.environ[spec["token_env"]])
                with request.build_opener(feeds.SameOriginRedirects()).open(req,timeout=10): pass
        return f"{len(specs)} 个来源已检查"
    probe("licensed_feeds",source_check,bool(os.getenv("TIKFLOWSO_FEEDS")),"待提供授权目录或 HTTPS 来源")
    def fx():
        import analytics
        data=json.loads(Path(os.environ["TIKFLOWSO_FX_RATES"]).read_text())
        day=max(data["dates"])
        base,rates=analytics.exchange_rates(day)
        return f"{day} {base}，{len(rates)} 种货币"
    probe("fx_file",fx,bool(os.getenv("TIKFLOWSO_FX_RATES")),"待填日期汇率文件")
    def routes():
        mapping=notifications.config()
        if not mapping: raise ValueError()
        reports=[]
        for ws,channels in mapping.items():
            if "email" in channels:
                cfg=channels["email"]
                with smtplib.SMTP(cfg["host"],cfg.get("port",587),timeout=6) as conn:
                    if cfg.get("starttls",True):conn.starttls()
                    if cfg.get("user"):conn.login(cfg["user"],os.environ[cfg["password_env"]])
                    if conn.noop()[0]!=250:raise ValueError()
                reports.append("SMTP NOOP")
            if "sms" in channels:
                cfg=channels["sms"]
                if cfg.get("token_env") and not os.getenv(cfg["token_env"]): raise ValueError()
                if urlsplit(cfg["url"]).scheme not in {"http","https"} or not cfg.get("to"): raise ValueError()
                reports.append("短信路由已配置，终端送达另验")
        return reports
    probe("notification_routes",routes,bool(os.getenv("TIKFLOWSO_ALERT_ROUTES")),"待填邮件或短信路由；站内通知独立运行")
    probe("stream_ingest_config",lambda:"接收配置齐备；真实供数由提供方推送",
          bool(os.getenv("TIKFLOWSO_STREAM_SOURCE") and os.getenv("TIKFLOWSO_STREAM_TOKEN")),"待填推送来源与共享令牌")
    print(json.dumps(rows,ensure_ascii=False,indent=2))
    return not any(r["state"]=="failed" for r in rows)


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action",choices=("sync","models","check","test"))
    parser.add_argument("--external",action="store_true",help="另测公开支付网关的 HTTPS 连通性")
    group=parser.add_mutually_exclusive_group()
    group.add_argument("--provider",choices=[*vision.PROVIDERS,"custom"])
    group.add_argument("--all",action="store_true",help="同步五个平台的目录")
    parser.add_argument("--public-only",action="store_true",help="仅匿名读取模型目录")
    parser.add_argument("--limit",type=int,default=20,help="展示最近的模型条数")
    args=parser.parse_args()
    settings.load()
    control_settings.FILE=ROOT/".data/tikflowso.providers.json"
    try:
        provider=args.provider or vision.selected()
        if args.action=="test":
            if args.all: parser.error("推理测试需选择单个服务商")
            print(json.dumps(sample_probe(provider),ensure_ascii=False))
        elif args.action=="models":
            vision.profile(provider)
            path=ROOT/".data/vision/catalogs"/(provider+".json")
            if not path.exists(): raise ValueError("尚无可读目录，请先同步该平台")
            data=json.loads(path.read_text())
            print(json.dumps(data.get("entries",[])[:max(1,min(args.limit,1000))],ensure_ascii=False,indent=2))
        elif args.action=="sync":
            from concurrent.futures import ThreadPoolExecutor
            names=list(vision.PROVIDERS) if args.all else [provider]
            def one(name):
                try:return sync_one(name,args.public_only)
                except (ValueError,OSError,vision.RequestError) as exc:
                    cause=getattr(exc,"__cause__",None)
                    reason=getattr(cause,"reason",None)
                    return {"provider":name,"state":"failed","detail":str(exc),
                            "transport_error":type(reason).__name__ if reason else None}
            with ThreadPoolExecutor(len(names)) as pool:results=list(pool.map(one,names))
            print(json.dumps(results,ensure_ascii=False,indent=2))
            if any(r["state"]=="failed" for r in results):sys.exit(1)
        elif not check(args.external):sys.exit(1)
    except (ValueError,OSError,RuntimeError,vision.RequestError) as exc:
        sys.exit(str(exc))

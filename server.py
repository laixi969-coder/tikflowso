"""Run tikflowso locally with python3 server.py."""
import argparse
import csv
import fcntl
import hashlib
import io
import json
import logging
import mimetypes
import os
import re
import sqlite3
import secrets
import threading
import zipfile
from contextlib import closing, ExitStack
import model_spend
import operations
import recycle
import request_limits
import uuid
import time
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlsplit

import analytics
import account_security
import assistant_chats
import billing
import backup_vault
import contacts
import feeds
import partnerships
import studio
import stream
import export_jobs
import insights
import notifications
import transcription
import vision
import platform_admin
import control_settings
import research_usage
import support_cases
import settings
import workspace as ws

ROOT = Path(__file__).resolve().parent
DATABASE = ROOT / ".data" / "tikflowso.sqlite3"
ROUTES = {"meta","overview","rankings","detail","trends","markets","trend-study"}


def connect():
    db = sqlite3.connect(DATABASE, timeout=15)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys=ON")
    return db


def initialize():
    DATABASE.parent.mkdir(parents=True, exist_ok=True)
    with closing(connect()) as db, db:
        if db.execute("PRAGMA user_version").fetchone()[0]>1:
            raise RuntimeError("数据库来自更新的发布版本，请使用对应镜像或恢复升级前备份")
        mode="WAL" if sqlite3.sqlite_version_info >= (3,51,3) or sqlite3.sqlite_version_info in ((3,50,7),(3,44,6)) else "DELETE"
        if db.execute("PRAGMA journal_mode="+mode).fetchone()[0].upper()!=mode:
            raise RuntimeError("数据库未能启用安全日志模式")
        analytics.init(db)
        feeds.schema(db)
        operations.init(db)
        research_usage.init(db)
        ws.init(db)
        assistant_chats.init(db)
        support_cases.init(db)
        platform_admin.init(db,DATABASE)
        contacts.init(db)
        export_jobs.init(db)
        stream.init(db)
        billing.init(db)
        partnerships.init(db)
        db.execute("PRAGMA user_version=1")


def body_json(raw):
    value = json.loads(raw or b"{}")
    if not isinstance(value,dict): raise ValueError("请求体必须为 JSON 对象")
    return value


def csv_safe(value):
    return "'"+value if isinstance(value,str) and value.lstrip().startswith(("=","+","-","@")) else value


class QueueExport(Exception):
    pass


def csv_export(db,params):
    first = analytics.scope_for(db,params)
    kind=params.get("kind") or "products"
    _, accepts=analytics.ranking_filter(kind,params)
    matches=[]
    for row in analytics.iter_rows(db,first):
        if accepts(row):
            matches.append(row)
            if len(matches)>1000:
                raise QueueExport
    rows = analytics.leaderboard(matches,kind,params)
    out = io.StringIO()
    export_jobs.write_csv(out,first,rows)
    return out.getvalue().encode("utf-8-sig"),len(rows)


class Handler(BaseHTTPRequestHandler):
    server_version = "tikflowso"

    def log_message(self, fmt, *args):
        pass

    def send_response(self,code,message=None):
        self.result_status=code
        super().send_response(code,message)

    def end_headers(self):
        self.send_header("X-Content-Type-Options","nosniff")
        self.send_header("Referrer-Policy","same-origin")
        self.send_header("X-Frame-Options","SAMEORIGIN")
        self.send_header("Content-Security-Policy","default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob: https:; media-src 'self' blob:; connect-src 'self' blob:; object-src 'none'; frame-ancestors 'self'; base-uri 'self'; form-action 'self'")
        if os.getenv("TIKFLOWSO_PUBLIC_URL","").startswith("https://"): self.send_header("Strict-Transport-Security","max-age=31536000")
        self.send_header("X-Request-ID",getattr(self,"request_id",""))
        super().end_headers()

    def reply(self, status, payload, mime="application/json; charset=utf-8", headers=None):
        if not isinstance(payload,bytes):
            payload=json.dumps(payload,ensure_ascii=False,allow_nan=False).encode()
        self.send_response(status)
        self.send_header("Content-Type",mime)
        self.send_header("Content-Length",str(len(payload)))
        self.send_header("Cache-Control",getattr(self,"cache_control","no-store"))
        if getattr(self,"fresh",None):
            cookie=f"tikflowso={self.fresh}; HttpOnly; Path=/; SameSite=Lax; Max-Age=2592000"
            if os.environ.get("TIKFLOWSO_PUBLIC_URL","").startswith("https://"): cookie+="; Secure"
            self.send_header("Set-Cookie",cookie)
        for k,v in (headers or {}).items(): self.send_header(k,v)
        self.end_headers()
        self.wfile.write(payload)

    def current(self,db,create=True):
        cookie = SimpleCookie()
        cookie.load(self.headers.get("Cookie",""))
        token = cookie.get("tikflowso")
        self.token = token.value if token else ""
        user = ws.session(db,self.token) if token else None
        if user is not None and platform_admin.access(db,user)["admin"]:
            if not db.execute("SELECT 1 FROM sessions WHERE digest=? AND assured=1",(ws.digest(self.token),)).fetchone():
                user=None
        if user is None and create:
            user = ws.guest(db)
            self.fresh = ws.issue_session(db,user["id"])
            self.token = self.fresh
        return user

    def handle_request(self,stack):
        self.fresh=None
        req=urlsplit(self.path)
        path=unquote(req.path)
        host=self.headers.get("Host","")
        public=urlsplit(os.environ.get("TIKFLOWSO_PUBLIC_URL",""))
        public_host=public.netloc
        if not (host == public_host and host or re.fullmatch(r"(?:localhost|127\.0\.0\.1|\[::1\])(?::[0-9]+)?",host)):
            raise ws.RequestError(403,"未知站点域名，请检查 TIKFLOWSO_PUBLIC_URL")
        if path == "/health" and self.command=="GET":
            try:
                with closing(connect()) as db:
                    db.execute("SELECT 1 FROM platform_admins LIMIT 1").fetchone()
            except sqlite3.Error:
                return self.reply(503,{"status":"unavailable"})
            return self.reply(200,{"status":"ok"})
        if path=="/downloads/tikflowso-extension.zip" and self.command=="GET":
            buffer=io.BytesIO()
            with zipfile.ZipFile(buffer,"w",zipfile.ZIP_DEFLATED,strict_timestamps=False) as archive:
                for name in ("manifest.json","popup.html","popup.js","identify.js","_locales/en/messages.json","_locales/zh_CN/messages.json"):
                    archive.write(ROOT/"extension"/name,name)
            return self.reply(200,buffer.getvalue(),"application/zip",{"Content-Disposition":'attachment; filename="tikflowso-extension.zip"'})
        if not path.startswith("/api/"):
            if self.command != "GET": raise ws.RequestError(405,"请求方法无效")
            if path in ("/","/board","/index.html"):
                with closing(connect()) as db,db: self.current(db)
                path="/index.html"
            base = ROOT / "web"
            file=(base/path.lstrip("/")).resolve()
            if not file.is_relative_to(base) or not file.is_file(): raise LookupError("页面不存在")
            if path!="/index.html":
                self.cache_control="private, no-cache"
                content=file.read_bytes()
                tag='"'+hashlib.sha256(content).hexdigest()+'"'
                if self.headers.get("If-None-Match")==tag: return self.reply(304,b"",headers={"ETag":tag})
                return self.reply(200,content,mimetypes.guess_type(file.name)[0] or "application/octet-stream",{"ETag":tag})
            return self.reply(200,file.read_bytes(),mimetypes.guess_type(file.name)[0] or "application/octet-stream")
        params={k:v[-1] for k,v in parse_qs(req.query).items()}
        raw=b""
        if self.command=="POST":
            origin=self.headers.get("Origin")
            scheme=public.scheme if public_host==host else "http"
            if origin and origin!=scheme+"://"+host: raise ws.RequestError(403,"请求来源不匹配")
            size=int(self.headers.get("Content-Length","0"))
            binary=path in ("/api/transcribe","/api/video-analysis","/api/partners/asset")
            limit=transcription.LIMIT_BYTES if path in ("/api/transcribe","/api/video-analysis") else 12*1024*1024
            if not 0<=size<=limit: raise ws.RequestError(413,"文件超过大小上限")
            if self.headers.get_content_type()!=("application/octet-stream" if binary else "application/json"):
                raise ws.RequestError(415,"请求内容类型无效")
            if self.headers.get("Transfer-Encoding") or len(self.headers.get_all("Content-Length",[]))!=1:
                raise ws.RequestError(400,"请求必须包含唯一且明确的长度")
            if binary or size>128*1024:
                with closing(connect()) as pre:
                    actor=self.current(pre,create=False)
                    if binary or path in ("/api/import","/api/normalize-snapshots","/api/generate","/api/assistant/ask"):
                        if actor is None: raise ws.RequestError(401,"请先打开工作台或登录")
                        if path!="/api/transcribe": ws.signed_in(actor)
                        if path in ("/api/import","/api/normalize-snapshots"): ws.admin(actor)
                        if path=="/api/partners/asset":
                            if not pre.execute("SELECT 1 FROM partner_library WHERE id=? AND owner=? AND kind='asset'",(int(params.get("id",0)),ws.workspace(actor))).fetchone():
                                raise LookupError("未找到授权素材")
                    principal=("workspace",ws.workspace(actor)) if actor and actor["email"] else ("address",self.client_address[0])
                stack.enter_context(request_limits.admit(principal))
            raw=request_limits.receive(self,size,binary,stack)
        with closing(connect()) as db, db:
            if path=="/api/stream" and self.command=="POST":
                auth=self.headers.get("Authorization","").split(" ",1)
                data=stream.ingest(db,auth[1] if len(auth)==2 and auth[0].lower()=="bearer" else "",body_json(raw))
            elif path=="/api/notifications/feedback" and self.command=="POST":
                data=notifications.feedback(db,raw,self.headers.get("X-Notification-Signature"))
            elif path=="/api/billing/webhook" and self.command=="POST":
                data=billing.webhook(db,raw,self.headers.get("Stripe-Signature",""))
            else:
                v1=path.startswith("/api/v1/")
                if v1:
                    if self.command!="GET" or path.split("/")[-1] not in ROUTES: raise LookupError("接口不存在")
                    auth=self.headers.get("Authorization","").partition(" ")
                    key=db.execute("SELECT uid FROM access_keys WHERE digest=?",(ws.digest(auth[2]),)).fetchone()
                    if auth[0].lower()!="bearer" or not key: raise ws.RequestError(401,"访问密钥无效")
                    user=ws.get_user(db,key[0])
                    path=path.replace("/api/v1/","/api/",1)
                    ws.consume_api(db,user)
                    db.commit()  # Authenticated attempts count toward the minute limit even if the query fails.
                    ws.consume(db,user,"api")
                else:
                    user=self.current(db)
                self.actor,self.owner=user["id"],ws.workspace(user)
                if path.startswith("/api/admin/"):
                    action=path.removeprefix("/api/admin/")
                    if action=="access" and self.command=="GET":return self.reply(200,platform_admin.access(db,user))
                    data=body_json(raw) if self.command=="POST" else {}
                    if action=="claim" and self.command=="POST":
                        result=platform_admin.claim(db,user,DATABASE,data.get("code"))
                        self.fresh=ws.issue_session(db,user["id"],assured=True)
                        db.commit()
                        return self.reply(200,result)
                    platform_admin.require(db,user)
                    if action=="operations" and self.command=="GET": return self.reply(200,operations.overview(db))
                    if action=="retry" and self.command=="POST":
                        if data.get("event"):
                            changed=db.execute("UPDATE webhook_inbox SET state='retry',tries=0,due=0 WHERE event=? AND state='failed'",(ws.ident(data["event"],200),))
                        elif data.get("job"):
                            changed=db.execute("UPDATE export_jobs SET state='queued',lease=NULL,finished=NULL,error=NULL WHERE job=? AND state='failed'",(int(data["job"]),))
                        else:
                            changed=db.execute("UPDATE deliveries SET status='retry',attempts=0,due=0 WHERE aid=? AND channel=? AND status='failed'",(int(data["aid"]),ws.ident(data["channel"])))
                        return self.reply(200,{"queued":bool(changed.rowcount)})
                    if action=="monitor-capacity":
                        return self.reply(200,ws.monitor_capacity.review(db,user,data) if self.command=="POST" else ws.monitor_capacity.history(db,user,params,operator=True))
                    if action=="support":
                        return self.reply(200,support_cases.handle(db,user,data if self.command=="POST" else params,
                            operator=True,write=self.command=="POST"))
                    if self.command=="GET" and action=="weekly":
                        return self.reply(200,research_usage.weekly(db,params.get("date")))
                    samples={"sample/en":"en.png","sample/zh":"zh.png","sample/empty":"empty.png","sample/video":"two-shots.mp4"}
                    if self.command=="GET" and action in samples:
                        file=platform_admin.SAMPLES/samples[action]
                        return self.reply(200,file.read_bytes(),mimetypes.guess_type(file.name)[0])
                    if self.command=="GET" and action=="settings":return self.reply(200,platform_admin.state(DATABASE))
                    if self.command=="GET" and action=="jobs":return self.reply(200,{"items":platform_admin.jobs(db)})
                    if self.command=="POST" and action=="provider":return self.reply(200,platform_admin.save(data,DATABASE))
                    if self.command=="POST" and action=="prompt":return self.reply(200,platform_admin.save_prompt(data))
                    if self.command=="POST" and action=="jobs":return self.reply(200,platform_admin.launch(db,connect,DATABASE,user,data))
                    raise LookupError("未知管理操作")
                ws.check_source(db,user,params.get("source","demo"))
                if path=="/api/video-analysis" and self.command=="POST":
                    ws.signed_in(user)
                    if vision.status()=="configured" and not model_spend.policy(db,ws.workspace(user),params.get("source","demo"),studio.destination("video-analysis")):
                        raise ws.RequestError(403,"此来源尚未授权云端视频处理")
                    value=self.generate_with_quota(db,user,lambda:vision.analyze_video(raw,params.get("brief","")))
                    return self.reply(200,value)
                if path=="/api/transcribe" and self.command=="POST":
                    db.commit()
                    return self.reply(200,transcription.transcribe(raw,params.get("language","auto")))
                if path=="/api/partners/asset":
                    asset_id=int(params.get("id","0"))
                    if self.command=="POST":
                        data=partnerships.asset(db,user,asset_id,raw.read_bytes(),params.get("name",""),params.get("expires",""))
                        db.commit()
                        return self.reply(200,data)
                    file=partnerships.asset(db,user,asset_id)
                    return self.reply(200,file["bytes"],"application/octet-stream",{
                        "Content-Disposition":"attachment; filename*=UTF-8''"+quote(file["filename"],safe="")})
                if self.command=="GET":
                    if path=="/api/exports/file":
                        size,blob=export_jobs.file_for(db,user,int(params.get("job","0")))
                        with blob:
                            self.send_response(200)
                            self.send_header("Content-Type","text/csv; charset=utf-8")
                            self.send_header("Content-Length",str(size))
                            self.send_header("Content-Disposition",'attachment; filename="tikflowso-rankings.csv"')
                            self.send_header("Cache-Control","private, no-store")
                            self.end_headers()
                            while block:=blob.read(65536): self.wfile.write(block)
                        job=db.execute("SELECT params,rows FROM export_jobs WHERE job=?",(int(params["job"]),)).fetchone()
                        filters=json.loads(job["params"])
                        if job["rows"] and filters.get("kind","products")=="products":
                            db.commit()
                            research_usage.record(db,ws.workspace(user),analytics.scope_for(db,filters),"export")
                        return
                    if path=="/api/contacts/export":
                        ws.admin(user)
                        if ws.effective_plan(db,user)!="team": raise ws.RequestError(403,"批量导出合作联系方式需要团队套餐")
                        rows=contacts.catalog(db,user,params)
                        buf=io.StringIO()
                        fields=("source","market","id","name","email","channel","rights")
                        writer=csv.DictWriter(buf,fields)
                        writer.writeheader()
                        for r in rows:
                            writer.writerow({k:csv_safe(r[k]) for k in fields})
                        ws.consume(db,user,"export_rows",len(rows))
                        db.commit()
                        return self.reply(200,buf.getvalue().encode("utf-8-sig"),"text/csv; charset=utf-8",{"Content-Disposition":'attachment; filename="creator-contacts.csv"'})
                    if path=="/api/export":
                        db.commit()
                        db.execute("BEGIN")
                        try: blob,row_count=csv_export(db,params)
                        except QueueExport:
                            db.rollback()
                            key=ws.digest(json.dumps(params,sort_keys=True)+str(ws.now()//60))
                            result=export_jobs.submit(db,user,{"params":params,"request_key":key})
                            db.commit()
                            return self.reply(202,{**result,"state":"queued"},headers={"Location":"/api/exports"})
                        db.commit()
                        db.execute("BEGIN IMMEDIATE")
                        user=ws.get_user(db,user["id"])
                        ws.check_source(db,user,params.get("source","demo"))
                        ws.consume(db,user,"export_rows",row_count)
                        if row_count and params.get("kind","products")=="products":
                            research_usage.record(db,ws.workspace(user),analytics.scope_for(db,params),"export")
                        db.commit()
                        return self.reply(200,blob,"text/csv; charset=utf-8",{"Content-Disposition":'attachment; filename="tikflowso-rankings.csv"'})
                    data=self.read(db,user,path,params)
                    if not v1 and params.get("kind","products")=="products" and (
                        path=="/api/detail" or (path=="/api/rankings" and data["total"]>0)):
                        db.commit()
                        research_usage.record(db,ws.workspace(user),data,"detail" if path=="/api/detail" else "list",params.get("id",""))
                else:
                    data=self.write(db,user,path,body_json(raw))
        self.reply(200,data)

    def read(self,db,user,path,params):
        if path=="/api/monitor-capacity":return ws.monitor_capacity.history(db,user,params)
        if path=="/api/plans":return ws.LIMITS
        if path=="/api/assistant/skills":return studio.research_skills.catalog()
        if path=="/api/assistant/chats":return assistant_chats.history(db,user,params.get("chat"))
        if path=="/api/support": return support_cases.handle(db,user,params)
        if path=="/api/ranking-presets": return ws.ranking_presets(db,user,params)
        if path=="/api/exports": return export_jobs.listing(db,user)
        if path=="/api/trend-study":
            if not db.in_transaction: db.execute("BEGIN")
            return insights.study(db,params)
        if path=="/api/alerts": return notifications.inbox(db,ws.workspace(user))
        if path in {"/api/"+route for route in ROUTES}:
            if path=="/api/detail": ws.consume(db,user,"detail_views")
            if not db.in_transaction: db.execute("BEGIN")
            data=analytics.handle(db,path,params)
            if path=="/api/overview" and (preview:=data.get("live_preview",{}).get("room")):
                bounded = bool(preview["start_at"] and preview["end_at"])
                if bounded or not preview["series"]:
                    stamps = db.execute("""SELECT stamp,value FROM stream_points WHERE source=:source AND market=:market
                        AND kind='lives' AND id=:id AND metric='online_viewers' AND stamp>=:begin AND stamp<=:end
                        AND stamp>=:start_date AND stamp<date(:date,'+1 day')
                        ORDER BY stamp DESC LIMIT 100""",
                        {**data,"id":preview["id"],"begin":preview["start_at"] if bounded else data["start_date"],
                         "end":preview["end_at"] if bounded else data["date"]+"T23:59:59.999999+00:00"}).fetchall()
                    if stamps:
                        preview.update(series=[{"time":stamp,"value":value} for stamp,value in reversed(stamps)],
                                       series_basis="session" if bounded else "window",series_source="stream")
            if path=="/api/detail" and data["item"]["kind"]=="lives":
                data["live_analysis"]["points"]=stream.recent(db,{**data,**data["item"]},window=(data["start_date"],data["date"]))
            if path=="/api/meta":
                allowed={r[0] for r in db.execute(analytics.source_policy.VISIBLE,(ws.workspace(user),))}
                data["sources"]=[s for s in data["sources"] if s["id"] in allowed]
            return data
        if path=="/api/partners" or path.startswith("/api/partners/"):
            return partnerships.handle(db,user,path,"GET",params)
        if path=="/api/model-permissions":
            ws.admin(user)
            source=params.get("source","demo")
            owner=ws.workspace(user)
            return {"items":[{"destination":d,"permission":model_spend.policy(db,owner,source,d)} for d in
                    sorted(set(filter(None,(studio.destination("agent"),studio.destination("image_translate"))))) ]}
        if path=="/api/recycle":
            ws.admin(user)
            return {"items":recycle.listing(db,ws.workspace(user))}
        if path=="/api/notifications/preferences":
            ws.admin(user)
            return {channel:bool(enabled) for channel,enabled in db.execute("SELECT channel,enabled FROM notification_preferences WHERE owner=?",(ws.workspace(user),))}
        if path=="/api/contacts": return {"items":contacts.catalog(db,user,params)}
        if path=="/api/me": return {**ws.me(db,user),"platform_admin":platform_admin.access(db,user)["admin"]}
        if path in ("/api/favorites","/api/monitors"):
            data=ws.list_items(db,user,path.split("/")[-1])
            if path=="/api/monitors":
                for monitor in data["items"]: monitor["points"]=stream.recent(db,monitor)
            return data
        if path=="/api/keys": return ws.keys(db,user)
        if path=="/api/config": return {"version":"1.4.0","transcription":transcription.available(),"model":studio.model_configured(),"cloud_vision":vision.configured(),"vision_provider":vision.selected(),"vision_status":vision.status(),"vision_model":vision.model() if vision.configured() else None, "billing":billing.status(db,user)}
        if path=="/api/imports":
            owner=ws.workspace(user)
            if not db.in_transaction: db.execute("BEGIN")
            visible=analytics.source_policy.VISIBLE
            coverage=db.execute(f"""WITH latest AS (
                SELECT source,market,MAX(date) AS day FROM analytics_daily
                WHERE source IN ({visible}) GROUP BY source,market)
                SELECT l.*,COUNT(*) AS rows FROM latest l JOIN analytics_daily d
                ON (d.source,d.market,d.date)=(l.source,l.market,l.day)
                GROUP BY l.source,l.market ORDER BY l.source,l.market""",(owner,))
            revisions=[]
            for r in db.execute(f"""SELECT * FROM snapshot_revisions WHERE source IN ({visible})
                                   ORDER BY revision DESC LIMIT 25""",(owner,)):
                before,after=json.loads(r["before_json"]),json.loads(r["after_json"])
                revisions.append({**{k:r[k] for k in ("revision","source","market","kind","id","date","changed_at")},
                                  "changes":{k:[before[k],v] for k,v in after.items() if before[k]!=v}})
            return {"deliveries":feeds.delivery_health(db,owner) if os.environ.get("TIKFLOWSO_FEEDS") else [],
                    "coverage":[dict(row) for row in coverage],"revisions":revisions,"items":[dict(row) for row in db.execute(
                "SELECT * FROM imports WHERE owner=? ORDER BY batch DESC LIMIT 25",(owner,))]}
        raise LookupError("接口不存在")

    def generate_with_quota(self,db,user,operation):
        period=ws.quota_period("generation")
        ws.consume(db,user,"generation")
        db.commit()
        with model_spend.scope(connect,ws.workspace(user)) as spend:
            try: return operation()
            except Exception:
                db.rollback()
                if not spend["sent"]:
                    db.execute("UPDATE usage SET amount=max(amount-1,0) WHERE uid=? AND feature='generation' AND period=?",
                               (ws.workspace(user),period))
                    db.commit()
                raise

    def write(self,db,user,path,data):
        if path=="/api/monitor-capacity":return ws.monitor_capacity.request(db,user,data)
        if path=="/api/normalize-snapshots":
            ws.admin(user)
            raw=data.get("csv")
            try:
                rows=list(csv.DictReader(io.StringIO(raw.lstrip("\ufeff")),strict=True)) if isinstance(raw,str) else json.loads(data["json"])
            except (KeyError,csv.Error,TypeError) as exc:
                raise ValueError("JSON 须为记录数组，CSV 须含列名") from exc
            return analytics.daily_from_counters(rows)
        if path=="/api/admin-handoff":
            ws.signed_in(user)
            token=secrets.token_urlsafe(32)
            db.execute("INSERT OR REPLACE INTO admin_handoff VALUES(?,?,?)",(user["id"],ws.digest(token),ws.now()+600))
            return {"proof":token}
        if path=="/api/assistant/chats/remove":
            chat=assistant_chats.owned_chat(db,user,data.get("chat"))["id"]
            db.execute("DELETE FROM assistant_turns WHERE chat=?",(chat,))
            db.execute("DELETE FROM assistant_chats WHERE id=?",(chat,))
            return {"ok":True}
        if path=="/api/support": return support_cases.handle(db,user,data,write=True)
        if path=="/api/ranking-presets": return ws.ranking_presets(db,user,data,write=True)
        if path=="/api/saved-topics": return ws.save_topic(db,user,data)
        if path=="/api/exports": return export_jobs.submit(db,user,data)
        if path=="/api/alerts/read":
            db.execute("UPDATE alerts SET seen=1 WHERE owner=? AND aid=?",(ws.workspace(user),int(data["id"])))
            return {"ok":True}
        if path=="/api/partners" or path.startswith("/api/partners/"):
            return partnerships.handle(db,user,path,"POST",data)
        if path=="/api/model-permissions":
            ws.admin(user)
            source=ws.ident(data.get("source"),64)
            ws.check_source(db,user,source)
            dest=data.get("destination")
            if not dest or dest not in (studio.destination("agent"),studio.destination("image_translate")):
                raise ValueError("供应商或模型已变更，请重新选取")
            owner=ws.workspace(user)
            db.execute("DELETE FROM research_permissions WHERE owner=? AND source=? AND destination=?",(owner,source,dest))
            if data.get("allow") is True:
                db.execute("INSERT INTO research_permissions VALUES(?,?,?,?,?)",(owner,source,dest,
                           int(data.get("history") is True),int(data.get("comments") is True)))
            return {"ok":True}
        if path=="/api/recycle/restore": return recycle.restore(db,user,int(data["id"]))
        if path=="/api/notifications/preferences":
            ws.admin(user)
            for channel in ("email","sms"):
                if type(data.get(channel)) is not bool: raise ValueError("请选择通知通道")
                db.execute("INSERT OR REPLACE INTO notification_preferences VALUES(?,?,?)",(ws.workspace(user),channel,int(data[channel])))
            return {"ok":True}
        if path=="/api/password/reset":
            account_security.limit_attempt(db,"reset:"+self.client_address[0],self.client_address[0])
            account_security.reset_password(db,data.get("token"),data.get("password"))
            return {"ok":True}
        if path=="/api/sessions/revoke":
            ws.signed_in(user)
            db.execute("DELETE FROM sessions WHERE uid=?",(user["id"],))
            return {"ok":True}
        if path in ("/api/login","/api/register","/api/logout"):
            assured=False
            if path!="/api/logout":
                account_security.limit_attempt(db,data.get("email",""),self.client_address[0])
            if path=="/api/logout": uid=ws.guest(db)["id"]
            else: uid=ws.authenticate(db,path.split("/")[-1],data,user)
            if path=="/api/login" and platform_admin.access(db,ws.get_user(db,uid))["admin"]:
                account_security.verify_factor(db,uid,data.get("factor"))
                assured=True
            if path!="/api/logout": account_security.successful(db,data["email"],self.client_address[0])
            if path=="/api/register":
                partnerships.attribute(db,uid,data.get("referral_code"),data.get("referral_consent",False))
            db.execute("DELETE FROM sessions WHERE digest=?", (ws.digest(self.token),))
            self.fresh=ws.issue_session(db,uid,assured=assured)
            return ws.me(db,ws.get_user(db,uid))
        if path=="/api/team/remove":
            ws.admin(user)
            db.execute("UPDATE users SET owner=NULL WHERE owner=? AND email=?",(user["id"],ws.email_value(data.get("email"))))
            return {"ok":True}
        if path=="/api/team/leave":
            ws.signed_in(user)
            db.execute("UPDATE users SET owner=NULL WHERE id=? AND owner IS NOT NULL",(user["id"],))
            return {"ok":True}
        if path=="/api/contacts": return contacts.mutate(db,user,data)
        if path=="/api/invite": return ws.invite(db,user,data)
        if path=="/api/join": return ws.join(db,user,data)
        if path in ("/api/favorites","/api/monitors"):
            result=ws.mutate_list(db,user,path.split("/")[-1],data)
            if path=="/api/monitors": ws.sample(db)
            elif not data.get("remove") and data.get("kind")=="products":
                saved=db.execute("SELECT source,market,date,days FROM favorites WHERE owner=? AND market=? AND source=? AND kind=? AND id=?",
                                 (ws.workspace(user),data["market"],data["source"],data["kind"],data["id"])).fetchone()
                research_usage.record(db,ws.workspace(user),saved,"save",data["id"])
            return result
        if path=="/api/keys": return ws.keys(db,user,data)
        if path=="/api/checkout":
            ws.admin(user)
            return billing.checkout(db,user,data.get("plan"))
        if path=="/api/portal":
            ws.admin(user)
            return billing.portal(db,user)
        if path=="/api/assistant/ask":
            if studio.model_configured(): ws.signed_in(user)
            return self.generate_with_quota(db,user,lambda:assistant_chats.answer(db,user,data))
        if path=="/api/generate":
            ws.check_source(db,user,str(data.get("source","demo")))
            # A remote inference may take seconds. Keep network I/O outside SQLite write locks.
            if studio.model_configured() or (vision.configured() and data.get("tool")=="image_translate"): ws.signed_in(user)
            return self.generate_with_quota(db,user,lambda:studio.generate(db,data,owner=ws.workspace(user)))
        if path=="/api/import":
            ws.admin(user)
            label=ws.ident(data.get("source"),32)
            if not re.fullmatch(r"[a-zA-Z0-9_-]+",label): raise ValueError("来源标识支持字母、数字、下划线和短横线")
            source=f"ws-{ws.workspace(user)}-{label}"
            filename=ws.ident(data.get("filename") or "快照",180)
            actor=ws.workspace(user)
            try:
                rows=data.get("rows")
                if "json" in data: rows=json.loads(data["json"])
                if isinstance(data.get("csv"),str): rows=list(csv.DictReader(io.StringIO(data["csv"].lstrip("\ufeff")),strict=True))
                if not isinstance(rows,list) or not 1<=len(rows)<=20000: raise ValueError("每批需包含 1 至 20000 条记录")
                if not db.in_transaction: db.execute("BEGIN IMMEDIATE")
                result=analytics.import_rows(db,rows,source,owner=ws.workspace(user))
            except (ValueError,csv.Error) as exc:
                db.rollback()
                db.execute("INSERT INTO imports(owner,source,count,created,filename,status,error) VALUES(?,?,0,?,?,'failed',?)",
                           (actor,source,ws.now(),filename,str(exc)[:400]))
                db.commit()
                raise ValueError(str(exc)) from exc
            db.execute("INSERT INTO imports(owner,source,count,created,filename,latest_date) VALUES(?,?,?,?,?,?)",
                       (actor,source,len(rows),ws.now(),filename,result["date"]))
            result.update(market=str(rows[0]["market"]).strip().upper(),kind=rows[0]["kind"].strip())
            ws.sample(db)
            return result
        raise LookupError("接口不存在")

    def dispatch(self):
        self.request_id=uuid.uuid4().hex
        studio.transport.request_id.set(self.request_id)
        started=time.monotonic()
        self.actor=self.owner=None
        error=None
        try:
            try:
                config = control_settings.read()
            except (OSError, ValueError):
                return self.reply(503,{"status":"unavailable","error":"后台配置无法读取"})
            with control_settings.pin(config), ExitStack() as stack:
                self.handle_request(stack)
        except (BrokenPipeError,ConnectionResetError): pass
        except (ws.RequestError,billing.BillingError) as exc:
            retry=getattr(exc,"retry_after",None)
            self.reply(exc.status,{"error":str(exc),**({"retry_after":retry} if retry else {})},
                       headers={"Retry-After":str(retry)} if retry else None)
        except (ValueError,TypeError) as exc: self.reply(400,{"error":str(exc)})
        except LookupError as exc: self.reply(404,{"error":str(exc)})
        except Exception as exc:
            error=type(exc).__name__
            logging.exception("Request failed %s",self.request_id)
            self.reply(500,{"error":"服务暂时无法处理请求，编号 "+self.request_id})
        finally:
            route=urlsplit(self.path)
            path=route.path.replace("/api/v1/","/api/",1)[:120]
            duration=round(1000*(time.monotonic()-started))
            status=getattr(self,"result_status",499)
            operations.observed(status,duration)
            logging.info(json.dumps({"id":self.request_id,"method":self.command,"path":path,"status":status,"ms":duration}))
            if path.startswith("/api/"):
                params=parse_qs(route.query)
                subject=next((str(params[k][0])[:120] for k in ("id","chat","job") if k in params),"")
                try:
                    with closing(connect()) as audit,audit:
                        operations.record(audit,self.actor,self.owner,path,self.command,subject,status,self.request_id,error)
                except sqlite3.Error: logging.exception("Audit storage unavailable %s",self.request_id)
    do_GET=do_POST=dispatch


def worker(stop):
    while not stop.wait(60):
        try:
            with closing(connect()) as db:
                feeds.sync_configured(db)
        except Exception:
            logging.exception("Feed update failed")
        try:
            with closing(connect()) as db,db:
                ws.sample(db)
        except Exception:
            logging.exception("Monitor update failed")
        try:
            with closing(connect()) as db,db: operations.retention(db)
            if backup_vault.daily(DATABASE):
                with closing(connect()) as db,db: db.execute("INSERT OR REPLACE INTO maintenance_state VALUES('encrypted_backup',?)",(ws.now(),))
        except Exception:
            logging.exception("Daily encrypted backup failed")


def job_worker(stop,run_one):
    while not stop.is_set():
        try:
            if run_one(connect): continue
        except Exception:
            logging.exception("Background job failed")
        stop.wait(1)


def main():
    global DATABASE
    os.umask(0o077)
    logging.basicConfig(level=logging.INFO,format='%(message)s')
    settings.load()
    parser=argparse.ArgumentParser(description="tikflowso 本地分析服务")
    parser.add_argument("--db",type=Path,default=DATABASE)
    parser.add_argument("--port",type=int,default=8765)
    parser.add_argument("--host",default="127.0.0.1")
    args=parser.parse_args()
    DATABASE=args.db.resolve()
    control_settings.FILE=DATABASE.with_suffix(".providers.json")
    DATABASE.parent.mkdir(parents=True, exist_ok=True)
    # Keep a single worker pool per database for the lifetime of this server.
    instance_lock = open(str(DATABASE)+".server.lock","a")
    try:
        fcntl.flock(instance_lock,fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        parser.exit(1, "此数据库已有服务在运行\n")
    initialize()
    httpd=request_limits.Server((args.host,args.port),Handler)
    stop=threading.Event()
    threading.Thread(target=worker,args=(stop,),daemon=True).start()
    for task in (export_jobs.run_one,notifications.run_one,billing.retry_one):
        threading.Thread(target=job_worker,args=(stop,task),daemon=True).start()
    print(f"tikflowso  http://{args.host}:{httpd.server_address[1]}",flush=True)
    try: httpd.serve_forever()
    except KeyboardInterrupt: pass
    finally:
        stop.set()
        httpd.server_close()
        instance_lock.close()


if __name__=="__main__": main()

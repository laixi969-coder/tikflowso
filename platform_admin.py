"""Platform administration, separate from self-service workspace ownership."""
import base64
import hmac
import json
import os
from pathlib import Path
import re
import secrets
import threading
import time
from contextlib import closing

import connections
import control_settings
import prompts
import vision
import workspace as ws

LABELS={"bailian":"阿里云百炼","volcengine":"火山方舟","openrouter":"OpenRouter","atlas":"Atlas Cloud","deepseek":"DeepSeek"}
SAMPLES=Path(__file__).resolve().parent/"qa/samples/vision"
SAMPLE_EXPECTATIONS={
    "en":"识别两行原文及位置，译出绿茶，并保留未添加糖的含义。",
    "zh":"识别水杯和容量文字的位置，英文译文保留蓝色、水杯和数值 500。",
    "empty":"空白图片应返回零个文字框。",
    "video":"识别两个连续镜头，在约 2 秒处切换，分别描述红色方块及黄色圆形。",
}


def setup_path(path):
    return path.with_suffix(".admin-setup.txt")


def init(db,path):
    db.executescript("""
    CREATE TABLE IF NOT EXISTS platform_admins(uid INTEGER PRIMARY KEY REFERENCES users(id));
    CREATE TABLE IF NOT EXISTS cloud_jobs(id INTEGER PRIMARY KEY, kind TEXT NOT NULL,provider TEXT NOT NULL,
        model TEXT NOT NULL,revision INTEGER NOT NULL,actor INTEGER NOT NULL,created INTEGER NOT NULL,
        status TEXT NOT NULL,results TEXT NOT NULL DEFAULT '[]',finished INTEGER,error TEXT);
    """)
    if "worker_pid" not in [r[1] for r in db.execute("PRAGMA table_info(cloud_jobs)")]:
        db.execute("ALTER TABLE cloud_jobs ADD COLUMN worker_pid INTEGER")
    # Startup holds the database's exclusive server lock. PIDs can repeat after a container rebuild.
    db.execute("UPDATE cloud_jobs SET status='interrupted',finished=?,error='服务重启，可重新执行' "
               "WHERE status='running'", (int(time.time()),))
    token=setup_path(path)
    if db.execute("SELECT 1 FROM platform_admins LIMIT 1").fetchone():
        token.unlink(missing_ok=True)
    elif not token.exists():
        try:
            with os.fdopen(os.open(token,os.O_EXCL|os.O_CREAT|os.O_WRONLY,0o600),"w") as f:
                f.write(secrets.token_urlsafe(32)+"\n")
        except FileExistsError: pass


def access(db,user):
    member=db.execute("SELECT 1 FROM platform_admins WHERE uid=?",(user["id"],)).fetchone()
    return {"admin":bool(member and user["email"]),"initial_setup":not db.execute("SELECT 1 FROM platform_admins LIMIT 1").fetchone()}


def claim(db,user,path,code):
    ws.signed_in(user)
    if not db.in_transaction: db.execute("BEGIN IMMEDIATE")
    token=setup_path(path)
    if (not access(db,user)["initial_setup"] or not token.is_file()
        or not isinstance(code,str) or not hmac.compare_digest(token.read_bytes().strip(),code.strip().encode())):
        raise ws.RequestError(403,"初始化码无效或管理员已绑定")
    from account_security import provision
    credentials=provision(db,user["id"])
    db.execute("INSERT INTO platform_admins VALUES(?)",(user["id"],))
    db.commit()
    token.unlink(missing_ok=True)
    return {"ok":True,"enrollment":credentials}


def require(db,user):
    ws.signed_in(user)
    if not access(db,user)["admin"]: raise ws.RequestError(403,"此操作需要平台管理员权限")


def directory(path):
    return path.parent/"vision/catalogs" if path.name=="tikflowso.sqlite3" else path.with_suffix(".catalogs")


def catalog(path,name):
    file=directory(path)/(name+".json")
    if not file.exists(): return {"entries":[]}
    try:
        data=json.loads(file.read_text())
    except (ValueError,OSError):return {"entries":[]}
    if data.get("base_url")!=vision.profile(name)["base"]:return {"entries":[]}
    return {"entries":data.get("entries",[]),"synced_at":data.get("synced_at")}


def jobs(db):
    return [{**dict(r),"results":json.loads(r["results"])} for r in db.execute(
        "SELECT * FROM cloud_jobs ORDER BY id DESC LIMIT 25")]


def state(path):
    conf=control_settings.read()
    with control_settings.pin(conf):
        providers=[]
        for name,label in LABELS.items():
            profile=vision.profile(name)
            providers.append({"name":name,"label":label,"base":profile["base"],"model":profile["model"],
                              "has_key":bool(vision.credential(name)),**catalog(path,name)})
        return {"use_for_text":conf.get("use_for_text",False),"active":vision.selected(),"revision":conf["revision"],"providers":providers,
                "prompts":[{"name":k,"label":v[0],"text":prompts.instruction(k),"custom":k in conf["prompts"]} for k,v in prompts.LIBRARY.items()]}


def provider(data):
    name=data.get("provider")
    if name not in LABELS: raise ValueError("未知云平台")
    return name


def save(data,path):
    name=provider(data)
    model=ws.ident(data.get("model"),250)
    for row in catalog(path,name)["entries"]:
        modes=row.get("inputs",[])
        if row["id"]==model and modes and not {"image","vision"}.intersection(modes):
            raise ValueError("目录显示该模型不支持图片输入，请选择视觉模型")
    key=data.get("key","")
    if not isinstance(key,str) or len(key)>4096 or any(not 33<=ord(c)<=126 for c in key):
        raise ValueError("密钥包含无效字符")
    def edit(conf):
        row=conf["providers"].setdefault(name,{})
        row["model"]=model
        if data.get("clear_key"):row["key"]=""
        elif key:row["key"]=key
        if data.get("activate"):
            conf["active"]=name
            conf["use_for_text"]=bool(data.get("use_for_text"))
    control_settings.update(data.get("revision"),edit)
    return {"ok":True}


def save_prompt(data):
    name=data.get("name")
    if name not in prompts.LIBRARY:raise ValueError("未知提示词")
    def edit(conf):
        if data.get("reset"):conf["prompts"].pop(name,None)
        else:conf["prompts"][name]=ws.ident(data.get("text"),6000)
    control_settings.update(data.get("revision"),edit)
    return {"ok":True}


def sample(case):
    if case=="video":
        value=vision.analyze_video((SAMPLES/"two-shots.mp4").read_bytes(),"描述每个镜头的主体形状、颜色和可见变化。")
        shots=value["shots"]
        valid=(len(shots)==2 and abs(shots[0]["start"])<.12 and abs(shots[0]["end"]-2)<.12
               and abs(shots[1]["start"]-2)<.12 and abs(shots[1]["end"]-4)<.12)
        for shot,color,shape in zip(shots,("红","黄"),("方|矩形","圆")):
            text=shot["subject"]+shot["composition"]+shot["action"]
            valid=valid and color in text and bool(re.search(shape,text))
        return bool(valid),value
    encoded=base64.b64encode((SAMPLES/(case+".png")).read_bytes()).decode()
    value=vision.translate("data:image/png;base64,"+encoded,"English" if case=="zh" else "简体中文")
    rows=value["blocks"]
    if case=="empty":return not rows,value
    original=" ".join(r["original"] for r in rows).lower()
    text=" ".join(r["translation"] for r in rows).lower()
    boxes=[r["box"] for r in rows]
    position=(any(b[1]<.4 for b in boxes) and any(b[1]>.45 for b in boxes) and
              all(0<=x<x+w<=1.001 and 0<=y<y+h<=1.001 for x,y,w,h in boxes))
    if case=="en":
        valid=("green tea" in original and "no added sugar" in original and "绿茶" in text
               and "糖" in text and re.search("无|未|不|零|没有",text))
    else:
        valid=("蓝色水杯" in original and "500" in original and "blue" in text
               and re.search(r"cup|bottle|tumbler|mug",text) and "500" in text)
    return bool(position and valid),value


def launch(db,connect,path,user,data):
    kind=data.get("kind")
    if kind not in ("sync","probe","acceptance"): raise ValueError("未知任务")
    name=provider(data)
    conf=control_settings.read()
    if conf["revision"]!=data.get("revision"):raise ws.RequestError(409,"配置已更新，请刷新后再执行")
    conf["active"]=name  # This job uses the selected tab without switching production.
    with control_settings.pin(conf):
        chosen=vision.model()
        if kind!="sync" and not vision.credential(): raise ws.RequestError(409,"请先保存该平台的 API key")
    if not db.in_transaction:db.execute("BEGIN IMMEDIATE")
    prior=db.execute("SELECT id FROM cloud_jobs WHERE status='running' AND provider=? AND kind=? AND revision=?",
                     (name,kind,conf["revision"])).fetchone()
    if prior:return {"id":prior["id"]}
    if kind!="sync" and db.execute("SELECT 1 FROM cloud_jobs WHERE status='running' AND kind!='sync'").fetchone():
        raise ws.RequestError(409,"已有推理验收或测试正在执行")
    job=db.execute("INSERT INTO cloud_jobs(kind,provider,model,revision,actor,created,worker_pid,status) VALUES(?,?,?,?,?,?,?,'running')",
                   (kind,name,chosen,conf["revision"],user["id"],int(time.time()),os.getpid())).lastrowid
    db.commit()
    def run():
        results=[]
        status="passed"
        error=None
        from model_spend import scope
        with control_settings.pin(conf),scope(connect,ws.workspace(user)),closing(connect()) as writer:
            try:
                if kind=="sync":
                    out=connections.sync_one(name,directory=directory(path))
                    if out["state"]=="pending_key":status="pending_key"
                    results.append(out)
                elif kind=="probe":
                    results.append(connections.sample_probe(name))
                else:
                    for case,expected in SAMPLE_EXPECTATIONS.items():
                        try:
                            passed,result=sample(case)
                            results.append({"case":case,"passed":passed,"expected":expected,"output":result})
                            if not passed:status="failed"
                        except (ValueError,ws.RequestError,OSError) as exc:
                            results.append({"case":case,"passed":False,"error":str(exc)})
                            status="failed"
                        with writer:writer.execute("UPDATE cloud_jobs SET results=? WHERE id=?",(json.dumps(results,ensure_ascii=False),job))
            except (ValueError,ws.RequestError,OSError) as exc:
                status,error="failed",str(exc)
            except Exception:
                status,error="failed","内部处理失败，请检查服务日志"
                import logging
                logging.exception("Cloud admin job %d failed",job)
            with writer:
                writer.execute("UPDATE cloud_jobs SET status=?,results=?,error=?,finished=? WHERE id=?",
                               (status,json.dumps(results,ensure_ascii=False),error,int(time.time()),job))
    threading.Thread(target=run,daemon=True).start()
    return {"id":job}

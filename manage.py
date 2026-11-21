"""Create and verify a consistent online backup of the local workspace."""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import shutil
import tempfile
import settlement
from contextlib import closing


def verify(db):
    check = db.execute("PRAGMA integrity_check").fetchone()[0]
    if check != "ok" or db.execute("PRAGMA foreign_key_check").fetchone():
        raise ValueError("数据库完整性检查失败")
    report = {}
    for (name,) in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT GLOB 'sqlite_*' ORDER BY name"):
        identifier='"'+name.replace('"','""')+'"'
        report[name]=db.execute(f"SELECT COUNT(*) FROM {identifier}").fetchone()[0]
    report["product_gmv_minor_units_by_market"] = dict(db.execute(
        "SELECT market,SUM(gmv_units) FROM analytics_daily WHERE kind='products' GROUP BY market"))
    return report


def backup(source, destination):
    if destination.exists(): raise ValueError("备份目标已存在，请指定新文件名")
    destination.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=destination.parent,suffix=".sqlite3",delete=False) as tmp:
        target=Path(tmp.name)
    try:
        with closing(sqlite3.connect(source.resolve().as_uri()+"?mode=ro",uri=True)) as live:
            live.execute("BEGIN")
            expected=verify(live)
            with closing(sqlite3.connect(target)) as copy:
                live.backup(copy)
                if verify(copy)!=expected: raise ValueError("备份校验差异")
        os.link(target,destination)
    finally:
        target.unlink(missing_ok=True)
    return expected


def file_hash(path):
    with path.open("rb") as f:
        return hashlib.file_digest(f,"sha256").hexdigest()


def deployment_backup(source,directory):
    source=source.resolve(strict=True)
    directory.mkdir(mode=0o700,parents=True,exist_ok=False)
    try:
        private=source.with_suffix(".providers.json")
        database=directory/"tikflowso.sqlite3"
        with open(str(private)+".lock","a") as lock:
            fcntl.flock(lock,fcntl.LOCK_SH)
            backup(source,database)
            files=[database]
            for config in (private, source.parent/"service.env"):
                if not config.is_file():
                    continue
                target = database.with_suffix(".providers.json") if config == private else directory/"service.env"
                with config.open("rb") as incoming,os.fdopen(os.open(target,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600),"wb") as outgoing:
                    shutil.copyfileobj(incoming,outgoing)
                files.append(target)
        manifest={p.name:file_hash(p) for p in files}
        (directory/"manifest.json").write_text(json.dumps(manifest,indent=2)+"\n",encoding="utf8")
        return verify_deployment(directory)
    except BaseException:
        shutil.rmtree(directory)
        raise


def verify_deployment(directory):
    files=json.loads((directory/"manifest.json").read_text())
    database=directory/"tikflowso.sqlite3"
    names={"tikflowso.sqlite3","tikflowso.providers.json","service.env"}
    if not isinstance(files,dict) or database.name not in files or set(files)-names:
        raise ValueError("备份清单无效")
    for name in names:
        path=directory/name
        if (name in files)!=path.is_file() or name in files and (path.is_symlink() or file_hash(path)!=files[name]):
            raise ValueError("备份文件与清单不一致")
    with closing(sqlite3.connect(database.resolve().as_uri()+"?mode=ro&immutable=1",uri=True)) as db:
        return {"files":sorted(files),"database":verify(db)}


def main():
    import settings
    settings.load()
    p=argparse.ArgumentParser(description=__doc__)
    s=p.add_subparsers(dest="action",required=True)
    bundle=s.add_parser("backup-deployment",help="创建可迁移的数据库和后台配置备份目录")
    bundle.add_argument("--db",type=Path,required=True)
    bundle.add_argument("--out",type=Path,required=True)
    inspect=s.add_parser("verify-deployment",help="核对部署备份文件与数据完整性")
    inspect.add_argument("--dir",type=Path,required=True)
    b=s.add_parser("backup")
    b.add_argument("--db",type=Path,required=True)
    b.add_argument("--out",type=Path,required=True)
    v=s.add_parser("verify")
    v.add_argument("--db",type=Path,required=True)
    grant=s.add_parser("grant-admin",help="授予已注册账号平台管理权，用于交接和恢复")
    grant.add_argument("--db",type=Path,required=True)
    grant.add_argument("--email",required=True)
    show=s.add_parser("settlements")
    show.add_argument("--db",type=Path,required=True)
    show.add_argument("--id",type=int)
    r=s.add_parser("review")
    r.add_argument("--db",type=Path,required=True)
    r.add_argument("id",type=int)
    r.add_argument("decision",choices=("approved","rejected"))
    r.add_argument("--reviewer",required=True)
    r.add_argument("--reason",required=True)
    d=s.add_parser("dispute")
    d.add_argument("--db",type=Path,required=True)
    d.add_argument("--mode",choices=("test","live"),required=True)
    d.add_argument("--case",required=True)
    d.add_argument("--charge",required=True)
    d.add_argument("--amount",type=int,required=True)
    d.add_argument("--reason",required=True)
    d.add_argument("action",choices=("open","reopen","won","lost"))
    args=p.parse_args()
    if args.action=="grant-admin":
        with closing(sqlite3.connect(args.db.resolve().as_uri()+"?mode=rw",uri=True)) as db,db:
            user=db.execute("SELECT id FROM users WHERE email=? AND password IS NOT NULL",(args.email.strip().lower(),)).fetchone()
            if not user:p.error("请先注册该账户")
            db.execute("INSERT OR IGNORE INTO platform_admins(uid) VALUES(?)",user)
        args.db.with_suffix(".admin-setup.txt").unlink(missing_ok=True)
        print("已授予平台管理权限")
        return
    if args.action=="settlements":
        with closing(sqlite3.connect(args.db.resolve().as_uri()+"?mode=ro",uri=True)) as db:
            db.row_factory=sqlite3.Row
            if args.id:
                row=db.execute("SELECT * FROM settlement_requests WHERE id=?",(args.id,)).fetchone()
                if not row: p.error("没有该申请")
                result={**dict(row),"snapshot":json.loads(row["snapshot"])}
            else:
                result=[dict(r) for r in db.execute("SELECT id,partner,mode,month,status FROM settlement_requests ORDER BY id DESC")]
            print(json.dumps(result,ensure_ascii=False,indent=2))
        return
    if args.action in ("review","dispute"):
        with closing(sqlite3.connect(args.db.resolve().as_uri()+"?mode=rw",uri=True)) as db,db:
            db.row_factory=sqlite3.Row
            if args.action=="review": settlement.review(db,args.id,args.decision,args.reviewer,args.reason)
            else: settlement.dispute(db,args.mode,args.case,args.charge,args.amount,args.action,args.reason)
        print("已记录")
        return
    if args.action=="backup": result=backup(args.db,args.out)
    elif args.action=="backup-deployment":result=deployment_backup(args.db,args.out)
    elif args.action=="verify-deployment":result=verify_deployment(args.dir)
    else:
        with closing(sqlite3.connect(args.db.resolve().as_uri()+"?mode=ro",uri=True)) as db: result=verify(db)
    print(json.dumps(result,ensure_ascii=False))


if __name__=="__main__": main()

"""Optional point-in-time SQLite replication to an operator-mounted encrypted volume."""
import argparse
from contextlib import closing
from datetime import datetime
import hashlib
import os
from pathlib import Path
import sqlite3
import subprocess
import tempfile

IMAGE="litestream/litestream:0.5.18@sha256:513bff62a88fc0c86c73d27333c41c54c89fe890a7c32a551600adff9309b11b"
DATABASE="tikflowso.sqlite3"


def name(home):
    return "tikflowso-replica-"+hashlib.sha256(os.fsencode(home.resolve())).hexdigest()[:16]


def docker(*args):
    subprocess.run(["docker",*map(str,args)],check=True)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("action",choices=("start","stop","restore"))
    p.add_argument("--home",type=Path,default=Path.home()/".local/share/tikflowso")
    p.add_argument("--replica-dir",type=Path,help="已挂载的专用加密目录；复制文件依赖此卷的静态加密")
    p.add_argument("--at",help="包含时区的 ISO 8601 时间")
    p.add_argument("--out",type=Path,help="新数据库文件")
    p.add_argument("--erasure-journal",type=Path)
    a=p.parse_args()
    home=a.home.resolve()
    if a.action=="stop":
        docker("stop",name(home))
        docker("rm",name(home))
        return
    if not a.replica_dir or not a.replica_dir.is_dir(): p.error("需要指定已挂载的副本目录")
    dest=a.replica_dir.resolve()
    if dest.is_relative_to(home) or home.is_relative_to(dest): p.error("请将副本卷与部署目录分开")
    opts=["--network","none","--cap-drop","ALL","--security-opt","no-new-privileges","--read-only",
          "--tmpfs","/tmp:rw,nosuid,nodev","--tmpfs","/var/run:rw,nosuid,nodev,mode=1777","--user",f"{os.getuid()}:{os.getgid()}"]
    if a.action=="start":
        if not (home/"data"/DATABASE).is_file(): p.error("没有可复制的部署数据库")
        docker("run","-d","--restart","unless-stopped","--name",name(home),*opts,
               "-v",str(home/"data")+":/data","-v",str(dest)+":/replica",IMAGE,"replicate","/data/"+DATABASE,"file:///replica")
        return
    if not a.out or not a.at or a.out.exists(): p.error("请指定时间与新的输出文件")
    point=datetime.fromisoformat(a.at.replace("Z","+00:00"))
    if point.tzinfo is None: p.error("时间须含时区")
    a.out.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(dir=a.out.parent) as scratch:
        recovered=Path(scratch)/DATABASE
        docker("run","--rm",*opts,"-v",str(dest)+":/replica:ro","-v",scratch+":/restore",
               IMAGE,"restore","-timestamp",point.isoformat(),"-o","/restore/"+DATABASE,"file:///replica")
        recovered.chmod(0o600)
        with closing(sqlite3.connect(recovered)) as db,db:
            if db.execute("PRAGMA integrity_check").fetchone()[0]!="ok" or db.execute("PRAGMA foreign_key_check").fetchone():
                raise ValueError("恢复校验失败")
            journal=a.erasure_journal or home/"recovery/erasures.sqlite3"
            if a.erasure_journal or journal.exists():
                import privacy
                privacy.replay(db,journal)
        os.link(recovered,a.out)


if __name__=="__main__": main()


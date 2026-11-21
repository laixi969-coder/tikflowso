"""Recover a committed row at a chosen time, excluding a later completed transaction."""
from datetime import datetime,timezone
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import replica


def cmd(*parts):
    result=subprocess.run(list(map(str,parts)),text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
    if result.returncode: raise RuntimeError(result.stdout)
    return result.stdout


def exercise(root):
    home=root/"instance"
    data=home/"data"
    data.mkdir(parents=True)
    archive=root/"replica"
    archive.mkdir()
    # All live SQLite processes use the same Docker engine and filesystem locking domain.
    image=os.getenv("TF_TEST_IMAGE","tikflowso-review:1.4.0")
    def write(sql):
        script="import sqlite3,sys; c=sqlite3.connect('/data/tikflowso.sqlite3'); c.execute('PRAGMA journal_mode=WAL'); c.executescript(sys.argv[1]); c.close()"
        cmd("docker","run","--rm","--network","none","--user",f"{os.getuid()}:{os.getgid()}","-v",str(data)+":/data",image,"python","-c",script,sql)
    write("CREATE TABLE events(id INTEGER PRIMARY KEY); INSERT INTO events VALUES(1);")
    name=replica.name(home)
    args=[sys.executable,ROOT/"replica.py"]
    cmd(*args,"start","--home",home,"--replica-dir",archive)
    try:
        def until(predicate):
            end=time.monotonic()+40
            while not predicate() and time.monotonic()<end: time.sleep(.4)
            if not predicate(): raise RuntimeError(cmd("docker","logs","--tail","20",name))
        until(lambda:any(archive.rglob("*.ltx")))
        time.sleep(1.5)
        cutoff=datetime.now(timezone.utc).isoformat()
        time.sleep(1.5)
        write("INSERT INTO events VALUES(2);")
        until(lambda:any(p.name.endswith("0000000000000002.ltx") for p in archive.rglob("*.ltx")))
        out=root/"recovered.sqlite3"
        cmd(*args,"restore","--home",home,"--replica-dir",archive,"--at",cutoff,"--out",out)
        with sqlite3.connect(out) as db:
            assert db.execute("SELECT id FROM events").fetchall()==[(1,)]
        print("PASS restored the selected committed state from a continuous local replica")
    finally:
        cmd(*args,"stop","--home",home)


if __name__=="__main__":
    with tempfile.TemporaryDirectory(prefix="tikflowso-pitr-") as tmp:
        exercise(Path(tmp).resolve())


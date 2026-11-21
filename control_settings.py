"""Private deployment configuration, atomically replaced on admin edits."""
from contextlib import contextmanager
from contextvars import ContextVar
import fcntl
import json
import os
from pathlib import Path
import tempfile

FILE = None  # Set by the application or CLI when opening its deployment.
_snapshot = ContextVar("cloud_configuration", default=None)


def read():
    if FILE is None or not FILE.exists(): return {"revision":0,"providers":{},"prompts":{}}
    config = json.loads(FILE.read_text())
    if (not isinstance(config,dict) or not isinstance(config.get("revision"),int)
            or not isinstance(config.get("providers"),dict) or not isinstance(config.get("prompts"),dict)):
        raise ValueError("后台配置文件格式无效")
    return config


def current():
    frozen=_snapshot.get()
    return read() if frozen is None else frozen


@contextmanager
def pin(config=None):
    token=_snapshot.set(current() if config is None else config)
    try: yield
    finally: _snapshot.reset(token)


def update(revision,edit):
    from workspace import RequestError
    FILE.parent.mkdir(parents=True,exist_ok=True)
    with open(str(FILE)+".lock","a") as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        conf=read()
        if conf["revision"]!=revision:
            raise RequestError(409,"设置已被更新，请刷新后重试")
        edit(conf)
        conf["revision"]+=1
        with tempfile.NamedTemporaryFile(mode="w",dir=FILE.parent,delete=False) as out:
            json.dump(conf,out,ensure_ascii=False)
            out.flush()
            os.fsync(out.fileno())
        os.replace(out.name,FILE)
    return conf

"""Load deployment settings without executing shell snippets or overriding the environment."""
import os
from pathlib import Path
import re

ROOT=Path(__file__).resolve().parent


def load():
    path=Path(os.getenv("TIKFLOWSO_ENV_FILE",ROOT/".env"))
    if not path.is_file(): return
    for n,line in enumerate(path.read_text(encoding="utf-8").splitlines(),1):
        line=line.strip()
        if not line or line.startswith("#"): continue
        key,sep,value=line.partition("=")
        if not sep or not re.fullmatch("[A-Z][A-Z0-9_]*",key):
            raise ValueError(f"部署配置第 {n} 行无效")
        value=value.strip()
        if len(value)>=2 and value[0]==value[-1] and value[0] in ("'",'"'):
            value=value[1:-1]
        if value: os.environ.setdefault(key,value)

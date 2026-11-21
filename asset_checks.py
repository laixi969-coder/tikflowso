"""Validate workspace attachment storage and gate distribution to other team members."""
from pathlib import Path
import os
import subprocess
import tempfile

def inspect(data,filename):
    import workspace as ws
    suffix=Path(filename).suffix.lower()
    if suffix in (".txt",".csv",".json",".srt","") and len(data)<=8*1024*1024:
        try: text=data.decode("utf-8-sig")
        except UnicodeDecodeError: text=None
        if text is not None and all(c in "\r\n\t" or ord(c)>=32 for c in text): return "text"
    command=os.getenv("TIKFLOWSO_ATTACHMENT_SCANNER")
    if not command: return "pending"
    with tempfile.NamedTemporaryFile() as f:
        f.write(data); f.flush()
        try:
            result=subprocess.run([command,f.name],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=45)
        except (OSError,subprocess.TimeoutExpired) as exc:
            raise ws.RequestError(503,"附件安全扫描暂不可用") from exc
    if result.returncode==1: raise ws.RequestError(422,"附件未通过安全扫描")
    if result.returncode!=0: raise ws.RequestError(503,"附件安全扫描暂不可用")
    return "clean"


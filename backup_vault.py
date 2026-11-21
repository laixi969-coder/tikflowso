"""Authenticated, encrypted backup bundles. Only the public certificate is mounted into the app."""
from contextlib import contextmanager
from datetime import datetime,timedelta,timezone
import fcntl
import logging
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile

PAYLOAD="snapshot.cms"
FILES={"tikflowso.sqlite3","tikflowso.providers.json","service.env","manifest.json"}


def openssl(*args):
    subprocess.run(["openssl",*map(str,args)],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)


def direct_credentials(source):
    import hashlib
    parent=Path(source).resolve().parent
    if parent.name=="data":
        return setup(parent.parent/"recovery")
    instance=hashlib.sha256(os.fsencode(parent)).hexdigest()[:16]
    return setup(Path.home()/".local/share/tikflowso-recovery"/instance)


def setup(directory):
    directory.mkdir(mode=0o700,parents=True,exist_ok=True)
    cert,key=directory/"recipient.pem",directory/"private.pem"
    with (directory/".lock").open("a") as guard:
        fcntl.flock(guard,fcntl.LOCK_EX)
        if cert.exists() and key.exists(): return cert,key
        if key.exists() or cert.exists(): raise ValueError("备份凭据不完整，请恢复现有密钥")
        with tempfile.TemporaryDirectory(dir=directory) as t:
            tmp=Path(t)
            openssl("req","-x509","-newkey","rsa:3072","-nodes","-days","3650","-subj","/CN=tikflowso backup",
                    "-keyout",tmp/"key","-out",tmp/"cert")
            (tmp/"key").chmod(0o600)
            (tmp/"key").replace(key)
            (tmp/"cert").replace(cert)
    return cert,key


def seal(db, directory, cert):
    import manage
    if directory.exists(): raise ValueError("备份目标已存在")
    directory.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory() as scratch, tempfile.TemporaryDirectory(dir=directory.parent) as publish:
        bundle=Path(scratch)/"snapshot"
        report=manage.deployment_backup(db,bundle)
        archive=Path(scratch)/"snapshot.tar.gz"
        with tarfile.open(archive,"w:gz") as tar:
            for name in sorted((*report["files"],"manifest.json")): tar.add(bundle/name,arcname=name)
        stage=Path(publish)/"sealed"
        stage.mkdir(mode=0o700)
        openssl("cms","-encrypt","-binary","-stream","-aes-256-gcm","-outform","DER",
                "-in",archive,"-out",stage/PAYLOAD,cert)
        (stage/PAYLOAD).chmod(0o600)
        with (stage/PAYLOAD).open("rb") as f: os.fsync(f.fileno())
        stage.rename(directory)
    return report


def encrypt_legacy(directory,cert,key):
    """Change the archive format only after every original byte has been recovered and checked."""
    import manage
    items={p.name for p in directory.iterdir()}
    if items=={PAYLOAD}: return False
    if not items or items-(FILES|{PAYLOAD}) or any(p.is_symlink() for p in directory.iterdir()):
        raise ValueError("旧备份目录包含无法验证的文件")
    with tempfile.TemporaryDirectory(dir=directory.parent) as temporary:
        work=Path(temporary)
        sealed=work/"verified"
        sealed.mkdir(mode=0o700)
        if PAYLOAD in items:
            os.link(directory/PAYLOAD,sealed/PAYLOAD)
        else:
            report=manage.verify_deployment(directory)
            archive=work/"snapshot.tar.gz"
            with tarfile.open(archive,"w:gz") as tar:
                for name in (*report["files"],"manifest.json"): tar.add(directory/name,arcname=name)
            openssl("cms","-encrypt","-binary","-stream","-aes-256-gcm","-outform","DER",
                    "-in",archive,"-out",sealed/PAYLOAD,cert)
            (sealed/PAYLOAD).chmod(0o600)
        originals=sorted(items-{PAYLOAD})
        with unpack(sealed,key) as clear:
            if any(not (clear/name).is_file() or manage.file_hash(clear/name)!=manage.file_hash(directory/name)
                   for name in originals):
                raise ValueError("旧备份与解密后的内容不同，已保留原文件")
        if PAYLOAD not in items:
            with (sealed/PAYLOAD).open("rb") as handle: os.fsync(handle.fileno())
            os.link(sealed/PAYLOAD,directory/PAYLOAD)
        fd=os.open(directory,os.O_RDONLY)
        try:
            os.fsync(fd)
            for name in originals: (directory/name).unlink()
            os.fsync(fd)
        finally: os.close(fd)
    return True


@contextmanager
def unpack(directory, key):
    import manage
    if not (directory/PAYLOAD).is_file():
        manage.verify_deployment(directory)
        yield directory
        return
    if key is None or not Path(key).is_file(): raise ValueError("恢复加密备份需要原实例备份私钥")
    if {p.name for p in directory.iterdir()}!={PAYLOAD} or (directory/PAYLOAD).is_symlink():
        raise ValueError("加密备份目录内容无效")
    with tempfile.TemporaryDirectory() as t:
        path=Path(t)
        archive=path/"content"
        try:
            openssl("cms","-decrypt","-binary","-inform","DER","-in",directory/PAYLOAD,"-inkey",key,"-out",archive)
        except subprocess.CalledProcessError as exc:
            raise ValueError("备份认证失败，请核对私钥和文件完整性") from exc
        seen=set()
        with tarfile.open(archive,"r:gz") as tar:
            for member in tar:
                if member.name not in FILES or member.name in seen or not member.isfile(): raise ValueError("无效备份内容")
                seen.add(member.name)
                with tar.extractfile(member) as src, (path/member.name).open("xb") as dst: shutil.copyfileobj(src,dst)
        manage.verify_deployment(path)
        yield path


def daily(db):
    root=os.getenv("TIKFLOWSO_BACKUP_DIR")
    cert=os.getenv("TIKFLOWSO_BACKUP_CERT")
    if not root or not cert: return
    today=datetime.now(timezone.utc).date()
    dest=Path(root)/("daily-"+today.isoformat())
    if (dest/PAYLOAD).is_file(): return False
    seal(db,dest,Path(cert))
    cutoff=today-timedelta(days=30)
    for path in Path(root).glob("daily-????-??-??"):
        if path.name[6:]<cutoff.isoformat() and not path.is_symlink() and path.is_dir() and {p.name for p in path.iterdir()}=={PAYLOAD}:
            (path/PAYLOAD).unlink()
            path.rmdir()
    return True


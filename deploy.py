#!/usr/bin/env python3
"""Install, upgrade, back up or recover a single-host tikflowso Compose service."""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from urllib.parse import urlsplit
from uuid import uuid4
from datetime import datetime, timezone

import manage
import backup_vault

ROOT = Path(__file__).resolve().parent
DATABASE = "tikflowso.sqlite3"
START = ("up", "-d", "--no-build", "--force-recreate", "--wait", "--wait-timeout", "120")


def docker(*args, capture=False, env=None):
    return subprocess.run(["docker", *args], env=env, check=True, text=True,
                          stdout=subprocess.PIPE if capture else None).stdout


def verify_candidate(image):
    # Mount only acceptance tests. The candidate reads its own application and packaged fixtures.
    with tempfile.TemporaryDirectory(prefix="tikflowso-release-tests-") as tmp:
        target=Path(tmp)
        tests=sorted(ROOT.glob("test_*.py"))
        if not tests: raise ValueError("发布包缺少回归测试")
        for test in tests:
            copy=target/test.name
            shutil.copyfile(test,copy)
            copy.chmod(0o444)
        target.chmod(0o755)
        docker("run","--rm","--network","none","--read-only","--tmpfs","/tmp:rw,nosuid,nodev,size=384m",
               "--mount","type=bind,src="+str(target)+",dst=/checks,readonly",
               "-e","TIKFLOWSO_ENV_FILE=/dev/null","-e","PYTHONPATH=/app",
               image,"python","-m","unittest","discover","-s","/checks","-q")


def restore_files(bundle, target, files, journal=None):
    # Verify the exact private working copy used for publication (including older bundles).
    with tempfile.TemporaryDirectory(dir=target.parent) as tmp:
        stage = Path(tmp)
        for name in [*files, "manifest.json"]:
            shutil.copyfile(bundle / name, stage / name)
            (stage / name).chmod(0o600)
        manage.verify_deployment(stage)
        (stage / "manifest.json").unlink()
        if journal is not None:
            import privacy
            from contextlib import closing
            with closing(sqlite3.connect(stage/DATABASE)) as restored,restored:
                restored.execute("PRAGMA foreign_keys=ON")
                privacy.replay(restored,journal)
        stage.rename(target)


def make_env(data, port, public_url):
    path = data / "service.env"
    if path.exists() and public_url is None:
        return
    url = public_url or f"http://127.0.0.1:{port}"
    parts = urlsplit(url)
    if (parts.scheme not in ("http", "https") or not parts.hostname or parts.username is not None
            or parts.password is not None or parts.path not in ("", "/") or parts.query or parts.fragment
            or any(c.isspace() for c in url)):
        raise ValueError("--public-url 须为完整站点 origin，例如 https://research.example.com")
    template = (path if path.exists() else ROOT / ".env.example").read_text()
    lines = [line for line in template.splitlines() if not line.startswith("TIKFLOWSO_PUBLIC_URL=")]
    lines.append("TIKFLOWSO_PUBLIC_URL=" + url.rstrip("/"))
    with tempfile.NamedTemporaryFile(mode="w", dir=data, delete=False) as f:
        f.write("\n".join(lines) + "\n")
    os.replace(f.name, path)


def deploy(args, home):
    data = home / "data"
    port_file = home / "port"
    saved_port = int(port_file.read_text()) if port_file.exists() else 8765
    port = args.port if args.port is not None else saved_port
    if not 0 < port <= 65535:
        raise ValueError("端口须为 1 到 65535")
    project = "tikflowso-" + hashlib.sha256(os.fsencode(home)).hexdigest()[:16]
    image = project + ":current"
    env = dict(os.environ, TF_PORT=str(port), TF_DATA=str(data), TF_IMAGE=image,
               TF_UID=str(os.getuid()), TF_GID=str(os.getgid()))

    def compose(*command, capture=False):
        return docker("compose", "--env-file", "/dev/null", "-f", str(ROOT / "compose.yaml"),
                      "-p", project, *command, capture=capture, env=env)

    db = data / DATABASE
    location=home/"backup-destination"
    backups = args.backup_dir.expanduser().resolve() if args.backup_dir else (Path(location.read_text().strip()) if location.is_file() else home/"backups")
    if args.backup_dir and not backups.is_dir(): raise ValueError("指定的备份磁盘或共享目录必须已挂载")
    if location.is_file() and not backups.is_dir(): raise ValueError("保存的备份目录未挂载")
    backups.mkdir(mode=0o700,parents=True,exist_ok=True)
    certificate,key=backup_vault.setup(home/"recovery")
    env.update(TF_BACKUP_DIR=str(backups),TF_BACKUP_CERT=str(certificate))
    if args.backup_dir:
        pending=location.with_suffix(".tmp")
        pending.write_text(str(backups))
        pending.replace(location)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid4().hex[:8]
    bundle = backups / stamp
    if args.action == "encrypt-backups":
        converted=0
        for path in sorted(backups.iterdir()):
            if (path.is_dir() and not path.is_symlink() and
                any((path/name).is_file() for name in ("manifest.json",backup_vault.PAYLOAD))):
                converted+=int(backup_vault.encrypt_legacy(path,certificate,key))
        print("已校验并转换的历史备份",converted)
        return
    import replica
    replica_name=replica.name(home)
    def active_replica():
        return bool(docker("ps","-q","--filter","name=^/"+replica_name+"$",capture=True).strip())
    if args.action == "stop":
        if active_replica(): docker("stop",replica_name)
        compose("stop")
        return
    if args.action == "backup":
        if not db.is_file():
            raise ValueError("没有可备份的部署数据库")
        backup_vault.seal(db,bundle,certificate)
        print(bundle)
        return
    if args.action == "upgrade" and not db.is_file():
        raise ValueError("升级需要已有部署")
    if args.action == "restore":
        if data.exists():
            raise ValueError("恢复须指定新的 --home，目标已有 data 目录")
        args.bundle=args.bundle.resolve(strict=True)

    # Build first. The running service continues serving until the candidate is available.
    cid = compose("ps", "-aq", "app", capture=True).strip()
    if cid:
        old_image = docker("inspect", "--format", "{{.Image}}", cid, capture=True).strip()
    else:
        old_image = docker("image", "ls", "-q", "--no-trunc", image, capture=True).strip()
    if old_image:
        docker("image", "tag", old_image, project + ":previous")
    if getattr(args,"rollback_image",None):
        docker("image","tag",args.rollback_image,image)
    else:
        compose("build", "app")
        verify_candidate(image)
    if args.action == "restore":
        with backup_vault.unpack(args.bundle,args.restore_key or key) as clear:
            journal=args.erasure_journal or (Path(args.restore_key).parent/"erasures.sqlite3" if args.restore_key else home/"recovery/erasures.sqlite3")
            if args.erasure_journal and not journal.is_file(): raise ValueError("原实例的注销登记簿不可读")
            restore_files(clear,data,manage.verify_deployment(clear)["files"],journal if journal.is_file() else None)
    existing = db.is_file() and args.action != "restore"
    paused_replica=existing and active_replica()
    if paused_replica: docker("stop",replica_name)
    if existing:
        if cid:
            compose("stop", "app")
        try:
            # Quiesce writers before migrations so a rollback has the last accepted write.
            backup_vault.seal(db,bundle,certificate)
            print("升级前备份", bundle, flush=True)
        except BaseException:
            if cid:
                compose("start", "app")
            if paused_replica: docker("start",replica_name)
            raise
    data.mkdir(mode=0o700, exist_ok=True)
    try:
        make_env(data, port, args.public_url)
        compose(*START)
    except (Exception, KeyboardInterrupt):
        if existing:
            compose("stop", "app")
            # Keep unrelated files (including local models) in place. Preserve failed state for inspection.
            with backup_vault.unpack(bundle,key) as clear:
                files=manage.verify_deployment(clear)["files"]
                recovered=home/("rollback-"+stamp)
                restore_files(clear,recovered,files)
            failed = home / ("failed-" + stamp)
            failed.mkdir(mode=0o700)
            for name in (DATABASE, DATABASE+"-wal", DATABASE+"-shm", DATABASE+"-journal", "tikflowso.providers.json", "service.env"):
                if (data / name).exists():
                    (data / name).rename(failed / name)
            for name in files:
                (recovered/name).replace(data/name)
            recovered.rmdir()
            if old_image:
                docker("image", "tag", old_image, image)
                env["TF_PORT"] = str(saved_port)
                compose(*START)
                print("已恢复升级前的镜像和数据。", file=sys.stderr)
            else:
                print("已恢复升级前的数据，未找到之前的镜像。", file=sys.stderr)
        raise
    if paused_replica: docker("start",replica_name)
    if existing and old_image:
        record=home/"rollback.json.tmp"
        record.write_text(json.dumps({"image":old_image,"backup":str(bundle)}))
        record.replace(home/"rollback.json")
    pending_port = port_file.with_suffix(".tmp")
    pending_port.write_text(str(port) + "\n")
    os.replace(pending_port, port_file)
    print(f"管理入口 http://127.0.0.1:{port}/#admin\n持久目录 {data}", flush=True)
    token = data / "tikflowso.admin-setup.txt"
    if token.exists():
        print(f"首次绑定码保存在 {token}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", nargs="?", default="up", choices=("up", "upgrade", "backup", "encrypt-backups", "restore", "rollback", "stop"))
    parser.add_argument("bundle", type=Path, nargs="?", help="restore 的备份目录")
    parser.add_argument("--home", type=Path, default=Path.home()/".local/share/tikflowso", help="持久实例目录")
    parser.add_argument("--port", type=int, help="回环监听端口，默认沿用已保存端口或 8765")
    parser.add_argument("--to",type=Path,help="rollback 使用的独立恢复实例目录")
    parser.add_argument("--backup-dir",type=Path,help="已挂载的独立备份目录，设置后沿用")
    parser.add_argument("--erasure-journal",type=Path,help="原实例的注销登记簿，恢复上线前重放")
    parser.add_argument("--restore-key",type=Path,help="原实例 recovery/private.pem")
    parser.add_argument("--public-url", help="外部站点 origin，供 HTTPS 代理和回调使用")
    args = parser.parse_args()
    if (args.action == "restore") != bool(args.bundle):
        parser.error("仅 restore 需要备份目录")
    home = args.home.expanduser().resolve()
    os.umask(0o077)
    home.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (home / ".deploy.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if args.action=="rollback":
            if args.to is None or args.port is None: parser.error("rollback 需使用 --to 和独立 --port，保留现有业务写入")
            target=args.to.expanduser().resolve()
            if target.is_relative_to(home) or home.is_relative_to(target) or (target/"data").exists():
                parser.error("请选择独立且尚无数据的恢复实例")
            record=json.loads((home/"rollback.json").read_text())
            args.action="restore"
            args.bundle=Path(record["backup"])
            args.rollback_image=record["image"]
            args.restore_key=home/"recovery/private.pem"
            target.mkdir(parents=True,exist_ok=True,mode=0o700)
            with (target/".deploy.lock").open("a") as other:
                fcntl.flock(other,fcntl.LOCK_EX)
                deploy(args,target)
        else:
            deploy(args, home)


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, sqlite3.Error, subprocess.CalledProcessError) as exc:
        sys.exit(str(exc))

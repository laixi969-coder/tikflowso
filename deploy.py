#!/usr/bin/env python3
"""Install, upgrade, back up or recover a single-host tikflowso Compose service."""
import argparse
import fcntl
import hashlib
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

ROOT = Path(__file__).resolve().parent
DATABASE = "tikflowso.sqlite3"
START = ("up", "-d", "--no-build", "--force-recreate", "--wait", "--wait-timeout", "120")


def docker(*args, capture=False, env=None):
    return subprocess.run(["docker", *args], env=env, check=True, text=True,
                          stdout=subprocess.PIPE if capture else None).stdout


def restore_files(bundle, target, files):
    # Verify the exact private working copy used for publication (including older bundles).
    with tempfile.TemporaryDirectory(dir=target.parent) as tmp:
        stage = Path(tmp)
        for name in [*files, "manifest.json"]:
            shutil.copyfile(bundle / name, stage / name)
            (stage / name).chmod(0o600)
        manage.verify_deployment(stage)
        (stage / "manifest.json").unlink()
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
    backups = home / "backups"
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid4().hex[:8]
    bundle = backups / stamp
    if args.action == "stop":
        compose("stop")
        return
    if args.action == "backup":
        if not db.is_file():
            raise ValueError("没有可备份的部署数据库")
        backups.mkdir(mode=0o700, exist_ok=True)
        compose("run", "--rm", "--no-deps", "-T", "--volume", str(backups)+":/backup", "app",
                "python", "manage.py", "backup-deployment", "--db", "/app/.data/"+DATABASE,
                "--out", "/backup/"+stamp)
        print(bundle)
        return
    if args.action == "upgrade" and not db.is_file():
        raise ValueError("升级需要已有部署")
    if args.action == "restore":
        if data.exists():
            raise ValueError("恢复须指定新的 --home，目标已有 data 目录")
        files = manage.verify_deployment(args.bundle.resolve(strict=True))["files"]

    # Build first. The running service continues serving until the candidate is available.
    cid = compose("ps", "-aq", "app", capture=True).strip()
    if cid:
        old_image = docker("inspect", "--format", "{{.Image}}", cid, capture=True).strip()
    else:
        old_image = docker("image", "ls", "-q", "--no-trunc", image, capture=True).strip()
    if old_image:
        docker("image", "tag", old_image, project + ":previous")
    compose("build", "app")
    if args.action == "restore":
        restore_files(args.bundle, data, files)
    existing = db.is_file() and args.action != "restore"
    if existing:
        if cid:
            compose("stop", "app")
        try:
            # Quiesce writers before migrations so a rollback has the last accepted write.
            manage.deployment_backup(db, bundle)
            print("升级前备份", bundle, flush=True)
        except BaseException:
            if cid:
                compose("start", "app")
            raise
    data.mkdir(mode=0o700, exist_ok=True)
    try:
        make_env(data, port, args.public_url)
        compose(*START)
    except (Exception, KeyboardInterrupt):
        if existing:
            compose("stop", "app")
            # Keep unrelated files (including local models) in place. Preserve failed state for inspection.
            files = manage.verify_deployment(bundle)["files"]
            failed = home / ("failed-" + stamp)
            failed.mkdir(mode=0o700)
            for name in (DATABASE, DATABASE+"-wal", DATABASE+"-shm", DATABASE+"-journal", "tikflowso.providers.json", "service.env"):
                if (data / name).exists():
                    (data / name).rename(failed / name)
            for name in files:
                shutil.copy2(bundle / name, data / name)
            if old_image:
                docker("image", "tag", old_image, image)
                env["TF_PORT"] = str(saved_port)
                compose(*START)
                print("已恢复升级前的镜像和数据。", file=sys.stderr)
            else:
                print("已恢复升级前的数据，未找到之前的镜像。", file=sys.stderr)
        raise
    pending_port = port_file.with_suffix(".tmp")
    pending_port.write_text(str(port) + "\n")
    os.replace(pending_port, port_file)
    print(f"管理入口 http://127.0.0.1:{port}/#admin\n持久目录 {data}", flush=True)
    token = data / "tikflowso.admin-setup.txt"
    if token.exists():
        print(f"首次绑定码保存在 {token}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", nargs="?", default="up", choices=("up", "upgrade", "backup", "restore", "stop"))
    parser.add_argument("bundle", type=Path, nargs="?", help="restore 的备份目录")
    parser.add_argument("--home", type=Path, default=Path.home()/".local/share/tikflowso", help="持久实例目录")
    parser.add_argument("--port", type=int, help="回环监听端口，默认沿用已保存端口或 8765")
    parser.add_argument("--public-url", help="外部站点 origin，供 HTTPS 代理和回调使用")
    args = parser.parse_args()
    if (args.action == "restore") != bool(args.bundle):
        parser.error("仅 restore 需要备份目录")
    home = args.home.expanduser().resolve()
    os.umask(0o077)
    home.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (home / ".deploy.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        deploy(args, home)


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, sqlite3.Error, subprocess.CalledProcessError) as exc:
        sys.exit(str(exc))

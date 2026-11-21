"""Exercise the public deployment commands in disposable Compose projects with empty cloud keys."""
import argparse
from contextlib import closing
import hashlib
from http.cookiejar import CookieJar
import io
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tarfile
import tempfile
from urllib.error import HTTPError
from urllib.request import build_opener, HTTPCookieProcessor, Request

from load_acceptance import fetch, ROOT

ACCOUNT = {"name":"Deployment QA", "email":"deploy@example.invalid", "password":"qa-deployment-fixture"}
SCOPE = {"kind":"products", "source":"demo", "market":"US", "id":"p01", "days":7}


def client():
    return build_opener(HTTPCookieProcessor(CookieJar()))


def free_port():
    with closing(socket.socket()) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def project(home):
    return "tikflowso-" + hashlib.sha256(os.fsencode(home.resolve())).hexdigest()[:16]


def command(home, action, *args, source=ROOT, success=True):
    result = subprocess.run([sys.executable, str(source/"deploy.py"), action, "--home", str(home), *map(str,args)],
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    if (result.returncode == 0) != success:
        raise AssertionError(result.stdout)
    return result.stdout


def account_state(base):
    c = client()
    fetch(c,base,"/api/login",ACCOUNT)
    assert fetch(c,base,"/api/me")["platform_admin"]
    conf = fetch(c,base,"/api/admin/settings")
    assert conf["active"] == "atlas" and not any(p["has_key"] for p in conf["providers"])
    assert next(p for p in conf["providers"] if p["name"]=="atlas")["model"]=="qa-vision"
    assert [p["text"] for p in conf["prompts"] if p["name"]=="ideas"] == ["Deployment rehearsal"]
    assert [r["id"] for r in fetch(c,base,"/api/favorites")["items"]] == ["p01"]
    return fetch(c,base,"/api/overview")["metrics"], fetch(c,base,"/api/export",raw=True)


def container(home):
    return subprocess.check_output(["docker","ps","-q","--filter","label=com.docker.compose.project="+project(home)],
                                   text=True).strip()


def clean(home):
    label = "label=com.docker.compose.project="+project(home)
    for listing, removal in ((["ps","-aq"],["rm","-f"]), (["network","ls","-q"],["network","rm"])):
        ids = subprocess.check_output(["docker",*listing,"--filter",label],text=True).split()
        if ids:
            subprocess.run(["docker",*removal,*ids],check=True,stdout=subprocess.DEVNULL)
    for tag in ("current","previous"):
        subprocess.run(["docker","image","rm",project(home)+":"+tag],capture_output=True)


def exercise(tmp, previous_ref, weights=None, speech=None):
    live, recovered, unclaimed = tmp/"live", tmp/"recovered", tmp/"unclaimed"
    first_port, second_port = free_port(), free_port()
    while second_port == first_port:
        second_port = free_port()
    base = f"http://127.0.0.1:{first_port}"
    other = f"http://127.0.0.1:{second_port}"
    old = ROOT
    if previous_ref:
        old = tmp/"previous"
        old.mkdir()
        archive = subprocess.check_output(["git","archive",previous_ref],cwd=ROOT)
        with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
            tar.extractall(old,filter="data")
        for name in ("deploy.py","Dockerfile","compose.yaml",".dockerignore"):
            shutil.copy2(ROOT/name,old/name)
    try:
        command(live,"up","--port",first_port,source=old)
        before = container(live)
        old_image = subprocess.check_output(["docker","inspect","-f","{{.Image}}",before],text=True)
        c = client()
        assert fetch(c,base,"/health")=={"status":"ok"}
        flags = fetch(c,base,"/api/config")
        assert flags["vision_status"]=="pending_key" and not flags["model"] and not flags["billing"]["configured"]
        command(live,"backup",source=old)
        bootstrap_bundle = next((live/"backups").iterdir())
        token = live/"data/tikflowso.admin-setup.txt"
        original_code = token.read_bytes()
        assert not any("admin-setup" in p.name for p in bootstrap_bundle.iterdir())
        fetch(c,base,"/api/register",ACCOUNT)
        fetch(c,base,"/api/admin/claim",{"code":token.read_text().strip()})
        assert not token.exists()
        fetch(c,base,"/api/admin/provider",{"provider":"atlas","model":"qa-vision","key":"","activate":True,"revision":0})
        fetch(c,base,"/api/admin/prompt",{"name":"ideas","text":"Deployment rehearsal","revision":1})
        fetch(c,base,"/api/favorites",SCOPE)
        expected = account_state(base)
        for provider in fetch(c,base,"/api/admin/settings")["providers"]:
            assert not provider["has_key"]
            for kind in ("probe","acceptance"):
                try:
                    fetch(c,base,"/api/admin/jobs",{"kind":kind,"provider":provider["name"],"revision":2})
                except HTTPError as exc:
                    assert exc.code == 409 and "key" in json.load(exc)["error"]
                else:
                    raise AssertionError("Empty key started a cloud job")
        assert fetch(c,base,"/api/admin/jobs")["items"] == []
        print("PASS clean install, admin claim, five empty providers and ten blocked inference actions",flush=True)

        command(live,"upgrade")
        current = container(live)
        assert current and before != current
        if previous_ref:
            assert old_image != subprocess.check_output(["docker","inspect","-f","{{.Image}}",current],text=True)
        assert fetch(c,base,"/api/me")["platform_admin"] and account_state(base) == expected
        assert len(list((live/"backups").iterdir()))==2
        print("PASS upgrade and automatic checkpoint; retained session, account, settings, favorite, totals and CSV",flush=True)

        command(live,"backup")
        bundles = sorted((live/"backups").iterdir())
        assert len(bundles)==3
        bundle = bundles[-1]
        assert set(json.loads((bundle/"manifest.json").read_text())) == {"tikflowso.sqlite3","tikflowso.providers.json","service.env"}
        command(recovered,"restore",bundle,"--port",second_port,"--public-url",other)
        assert account_state(other)==expected and not (recovered/"data/tikflowso.admin-setup.txt").exists()
        running = container(recovered)
        config_path = "/app/.data/tikflowso.providers.json"
        subprocess.run(["docker","exec",running,"cp","-p",config_path,"/tmp/qa-settings"],check=True)
        subprocess.run(["docker","exec",running,"python","-c",
                        "from pathlib import Path; import sys; Path(sys.argv[1]).write_text('{}')",config_path],check=True)
        try:
            try:
                fetch(client(),other,"/health")
            except HTTPError as exc:
                assert exc.code == 503
            else:
                raise AssertionError("Invalid admin settings passed readiness")
        finally:
            subprocess.run(["docker","exec",running,"cp","-p","/tmp/qa-settings",config_path],check=True)
        assert fetch(client(),other,"/health")=={"status":"ok"}
        assert (recovered/"data/tikflowso.providers.json").stat().st_mode & 0o777 == 0o600
        print("PASS online backup and independent recovery; model, prompt, admin role, totals and CSV match",flush=True)

        # Check sample files from the new image and the packaged Linux media tools.
        auth = client()
        fetch(auth,other,"/api/login",ACCOUNT)
        for sample in ("en","zh","empty","video"):
            assert fetch(auth,other,"/api/admin/sample/"+sample,raw=True)
        probe = subprocess.check_output(["docker","exec",container(recovered),"ffprobe","-v","error",
            "-show_entries","format=duration","-of","json","/app/qa/samples/vision/two-shots.mp4"])
        assert float(json.loads(probe)["format"]["duration"]) == 4
        if weights:
            models = recovered/"data/models"
            models.mkdir()
            shutil.copyfile(weights, models/"whisper.bin")
            assert fetch(auth,other,"/api/config")["transcription"]
            req = Request(other+"/api/transcribe?language=en",speech.read_bytes(),
                          {"Content-Type":"application/octet-stream"})
            with auth.open(req,timeout=180) as response:
                transcript = json.load(response)
            assert transcript["text"].strip() and " --> " in transcript["srt"] and transcript["seconds"] > 0
            print("PASS Linux offline transcription and SRT:",transcript["text"].strip(),flush=True)

        # A real engine port conflict forces recreation to fail before publication.
        command(live,"upgrade","--port",second_port,success=False)
        assert account_state(base)==expected
        assert list(live.glob("failed-*"))
        command(live,"restore",bundle,success=False)
        corrupt = tmp/"corrupt"
        shutil.copytree(bundle,corrupt)
        with (corrupt/"tikflowso.providers.json").open("ab") as f:
            f.write(b" ")
        command(tmp/"rejected","restore",corrupt,success=False)
        assert not (tmp/"rejected/data").exists()
        assert account_state(other)==expected
        print("PASS failed upgrade rollback, occupied target protection and corrupt backup rejection",flush=True)
        port = free_port()
        command(unclaimed,"restore",bootstrap_bundle,"--port",port)
        access = fetch(client(),f"http://127.0.0.1:{port}","/api/admin/access")
        assert access["initial_setup"] and not access["admin"]
        assert (unclaimed/"data/tikflowso.admin-setup.txt").read_bytes() != original_code
        print("PASS recovery before first admin claim issues a fresh setup code",flush=True)
    finally:
        clean(unclaimed)
        clean(recovered)
        clean(live)


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--previous-ref",help="Package a previous Git revision as the starting application")
    parser.add_argument("--whisper-model",type=Path,help="Optional local GGML weights for real container ASR")
    parser.add_argument("--speech",type=Path,help="A spoken English audio sample for offline ASR")
    opts=parser.parse_args()
    if bool(opts.whisper_model) != bool(opts.speech):
        parser.error("Provide both --whisper-model and --speech for transcription")
    with tempfile.TemporaryDirectory(prefix="tikflowso-deploy-") as temp:
        exercise(Path(temp).resolve(),opts.previous_ref,opts.whisper_model,opts.speech)

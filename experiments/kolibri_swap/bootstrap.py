"""Pinned, credential-free worker setup for a tiny smoke or local-only server."""
from __future__ import annotations

import inspect
import os
from pathlib import Path
import re
import shlex
import signal
import time

REMOTE = "/workspace/kolibri"
IMAGE = ("runpod/pytorch:1.0.3-cu1281-torch291-ubuntu2404@sha256:"
         "60baa36d3fb6b98fd4f4ece6b96776c83c01a8b7c540e54460ab4d496816141f")
PLUGIN_REVISION = "049a6a7bd2405b27d6d280d256bd3d585191c7ae"
MODEL_REVISION = "e52eb4627d11516b0c01de49210ab5a4e4061444"
MODEL = "Aleph-Alpha/Kolibri-1"


def _proc_stat(path):
    raw = path.read_text()
    parts = raw[raw.rfind(")") + 2:].split()
    return {"state": parts[0], "group": int(parts[2]), "session": int(parts[3]), "start": int(parts[19])}


def stop_group(record, *, proc_root=Path("/proc"), killpg=os.killpg, sleep=time.sleep):
    """Stop live members even if the original timeout/group leader has exited."""
    pid = record["pid"]
    if (type(pid) is not int or pid <= 1 or record.get("pgid") != pid or record.get("session") != pid
            or not isinstance(record.get("start"), str) or not record["start"].isdigit()):
        raise ValueError("Invalid process-group receipt")
    start = int(record["start"])
    proc_root = Path(proc_root)
    leader = proc_root / str(pid) / "stat"

    def members():
        try:
            identity = _proc_stat(leader)
        except FileNotFoundError:
            identity = None
        if identity is not None and (identity["start"] != start or identity["group"] != pid
                                     or identity["session"] != pid):
            raise RuntimeError("PID identity changed")
        live = []
        for path in proc_root.glob("[0-9]*/stat"):
            try:
                item = _proc_stat(path)
            except FileNotFoundError:
                continue
            if item["group"] == pid:
                if item["session"] != pid or item["start"] < start:
                    raise RuntimeError("Process-group identity changed")
                if item["state"] not in {"Z", "X"}:
                    live.append(path)
        return live

    def send(sig):
        try:
            killpg(pid, sig)
        except ProcessLookupError:
            pass

    if members():
        send(signal.SIGCONT)
        send(signal.SIGTERM)
        for _ in range(40):
            if not members():
                break
            sleep(.25)
        if members():
            send(signal.SIGKILL)
            for _ in range(40):
                if not members():
                    break
                sleep(.25)
        if members():
            raise RuntimeError("Worker process group did not stop")


def worker_script(kind, freeze, relative, seconds):
    if (kind not in {"cheap", "main"} or not re.fullmatch(r"[0-9a-f]{40}", freeze)
            or relative != "data/kolibri_swap/plan_v1_20261004/PLAN.json"
            or type(seconds) is not int or not 60 <= seconds <= 18000):
        raise ValueError("Invalid pinned worker specification")
    py = REMOTE + "/venv/bin/python"
    # This remote process receives no OpenRouter, RunPod, or Hugging Face secret.
    validate = (
        "import json,hashlib,pathlib; p=json.load(open(" + repr(relative) + ")); "
        "assert all(hashlib.sha256(pathlib.Path(n).read_bytes()).hexdigest()==h "
        "for n,h in p['source_hashes'].items()), 'Source hash mismatch'")
    exited = ("import json,sys; json.dump({'exit_code':int(sys.argv[1])},open("
              + repr(REMOTE + "/out/exit.json") + ",'x'))")
    lines = [
        "set -eu", "umask 077", "mkdir -p " + REMOTE + "/out",
        "trap 'rc=$?; python3 -c " + shlex.quote(exited).replace("'", "'\"'\"'") + " \"$rc\"' EXIT",
        "trap 'exit 143' TERM", "trap 'exit 130' INT",
        "unset HF_TOKEN HUGGING_FACE_HUB_TOKEN OPENAI_API_KEY ANTHROPIC_API_KEY OPENROUTER_API_KEY RUNPOD_API_KEY",
        "export HF_HUB_DISABLE_IMPLICIT_TOKEN=1 HF_HUB_DISABLE_TELEMETRY=1 DO_NOT_TRACK=1 VLLM_NO_USAGE_STATS=1",
        "export HF_HOME=/workspace/cache PYTHONUNBUFFERED=1",
        "git -c credential.helper= clone --filter=blob:none --no-checkout --single-branch "
        "--branch codex/kolibri-swap-panel --depth=1 https://github.com/tdj28/llm_selfref_pre.git " + REMOTE + "/repo",
        "cd " + REMOTE + "/repo",
        "git fetch --depth=1 origin " + freeze,
        "git sparse-checkout set --no-cone /experiments /src /tests /requirements-ci.txt /" + relative,
        "git checkout --detach " + freeze,
        shlex.join(["python3", "-c", validate]),
        "python3 -m venv " + REMOTE + "/venv",
        py + " -m pip install --require-hashes -r experiments/kolibri_swap/requirements-gpu.lock",
        py + " -m pip freeze --all > " + REMOTE + "/out/pip-freeze.txt",
        shlex.join([py, "-c", "import torch,json,sys; assert sys.version_info[:2]==(3,12); "
                    "assert torch.cuda.is_available(); json.dump({'torch':torch.__version__,"
                    "'cuda':torch.version.cuda,'gpu':torch.cuda.get_device_name()},"
                    "open('/workspace/kolibri/out/runtime.json','x'))"]),
        "git -c credential.helper= clone --depth=1 https://github.com/Aleph-Alpha/aleph-alpha-inference.git " + REMOTE + "/upstream",
        "git -C " + REMOTE + "/upstream fetch --depth=1 origin " + PLUGIN_REVISION,
        "git -C " + REMOTE + "/upstream checkout --detach " + PLUGIN_REVISION,
    ]
    if kind == "cheap":
        lines.extend([
            shlex.join([py, "-m", "pytest", REMOTE + "/upstream/tests/test_reasoning.py",
                        REMOTE + "/upstream/tests/test_kolibri1.py", "-m", "not gpu", "-q",
                        "--junitxml=" + REMOTE + "/out/upstream-tests.xml"]),
            shlex.join([py, "-m", "experiments.kolibri_swap.gpu_smoke", "--mode", "gpu",
                        "--upstream", REMOTE + "/upstream", "--out", REMOTE + "/out/gpu-smoke.json"]),
        ])
    else:
        lines.extend([
            shlex.join([py, "-m", "experiments.kolibri_swap.model_files",
                        "--out", REMOTE + "/out/model-files.json"]),
            shlex.join([REMOTE + "/venv/bin/vllm", "serve", MODEL,
                        "--revision", MODEL_REVISION, "--tokenizer-revision", MODEL_REVISION,
                        "--served-model-name", MODEL, "--host", "127.0.0.1", "--port", "8000",
                        "--kv-cache-dtype", "fp8", "--reasoning-parser", "kolibri1",
                        "--generation-config", "vllm", "--max-model-len", "16384",
                        "--max-num-seqs", "16", "--gpu-memory-utilization", "0.90",
                        "--enforce-eager", "--seed", "20261004", "--disable-log-requests"]),
        ])
    return "\n".join(lines) + "\n"


def start_command(seconds, binding):
    if type(seconds) is not int or not 60 <= seconds <= 18000 or not re.fullmatch(r"[0-9a-f]{64}", binding):
        raise ValueError("Invalid worker lifetime or binding")
    code = """import json,os,pathlib,signal,subprocess,time
r=pathlib.Path('/workspace/kolibri')
marker=r/'process.json'
if any(p.is_symlink() for p in [r,marker,r/'out',*r.parents]): raise RuntimeError('Linked worker path')
env={'HOME':'/root','LANG':'C.UTF-8','PATH':'/usr/local/cuda/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin',
     'LD_LIBRARY_PATH':'/usr/local/cuda/lib64','PIP_CONFIG_FILE':'/dev/null','GIT_CONFIG_NOSYSTEM':'1'}
p=None
with marker.open('x') as f:
 json.dump({'binding':'BINDING','state':'preparing'},f); f.flush(); os.fsync(f.fileno())
 try:
  with open(r/'out/worker.log','xb') as log:
   p=subprocess.Popen(['timeout','--signal=TERM','--kill-after=30','SECONDSs','bash','--noprofile','--norc',str(r/'worker.sh')],stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True,env=env)
   raw=pathlib.Path('/proc/'+str(p.pid)+'/stat').read_text()
   parts=raw[raw.rfind(')')+2:].split()
   assert int(parts[2])==p.pid and int(parts[3])==p.pid, 'Worker group not isolated'
   f.seek(0); f.truncate()
   json.dump({'pid':p.pid,'pgid':p.pid,'session':p.pid,'start':parts[19],'binding':'BINDING','state':'started'},f)
   f.flush(); os.fsync(f.fileno())
 except BaseException:
  if p is not None:
   try: os.killpg(p.pid,signal.SIGKILL)
   except ProcessLookupError: pass
  raise
print('dispatched')
""".replace("SECONDS", str(seconds)).replace("BINDING", binding)
    return "python3 -c " + shlex.quote(code)


def stop_command(binding):
    if not re.fullmatch(r"[0-9a-f]{64}", binding):
        raise ValueError("Invalid worker binding")
    code = ("import json,os,pathlib,signal,time\nfrom pathlib import Path\n"
            + inspect.getsource(_proc_stat) + "\n" + inspect.getsource(stop_group) + "\n" + """
r=pathlib.Path('/workspace/kolibri'); m=r/'process.json'
if any(p.is_symlink() for p in [r,m,*r.parents]): raise RuntimeError('Linked process receipt')
if m.exists():
 d=json.loads(m.read_text()); assert d['binding']=='BINDING'
 stop_group(d)
print(json.dumps({'stopped':True,'binding':'BINDING'}))
""").replace("BINDING", binding)
    return "python3 -c " + shlex.quote(code)

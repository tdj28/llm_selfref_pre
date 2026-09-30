"""Explicit-launch RunPod v2 controller. Import and default CLI are unpaid/local.

Never approves scientific gates. Monitor must stay supervised on the local host;
without that host, remote timeout stops work but cannot terminate a billed pod.
API schema: https://api.runpod.io/v2/openapi.json (read 2026-09-29).
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shlex
import shutil
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

from .budget import BudgetGuard, EventLedger, PodRegistry, _canonical, _number, _utc

API = "https://api.runpod.io/v2"
REPO = "https://github.com/tdj28/llm_selfref_pre.git"
IMAGE_TAG = "1.0.2-cu1281-torch280-ubuntu2404"
IMAGE_DIGEST = "sha256:0a360022e8de4375af99430f84e8b38951acc397252163a37ceac7204d01be35"
IMAGE = "runpod/pytorch:" + IMAGE_TAG + "@" + IMAGE_DIGEST
PREFIX = "codex-sae-assay-20260929-"
BLOCKED = "6lnzutgdc6lemh"
KEY = Path("~/.ssh/runpod_conscious_20260708")
REMOTE = "/workspace/sae-assay"
STORAGE = Decimal("0.10")
HARDWARE = {"cheap": ("NVIDIA GeForce RTX 4090", Decimal("0.74"), 24),
            "main": ("NVIDIA B200", Decimal("6.79"), 180)}
WAITING = ("WAITING-qualification.json", "WAITING-target-first5.json")
TERMINAL = ("DONE-all.json", "controller-exit.json", "controller-stopped.json")


def now():
    return datetime.now(timezone.utc)


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        while chunk := handle.read(1048576):
            digest.update(chunk)
    return digest.hexdigest()


def strict_json(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("Duplicate JSON key")
            result[key] = value
        return result
    value = json.loads(raw, object_pairs_hook=pairs)
    _canonical(value)  # Reject NaN, Infinity and exponent overflow.
    return value


class ApiError(RuntimeError):
    def __init__(self, status):
        self.status = status
        super().__init__(f"RunPod HTTP {status}; no automatic mutation retry")


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


class RunPodV2:
    def __init__(self, token, *, writable=False, opener=None):
        if not isinstance(token, str) or not token.strip() or any(c.isspace() for c in token):
            raise ValueError("RUNPOD_API_KEY must be supplied through the environment")
        self.token, self.writable = token, writable
        self.opener = opener or urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())

    def request(self, method, path, body=None):
        if (not path.startswith("/") or ".." in path or "//" in path or BLOCKED in path
                or method not in {"GET", "POST", "DELETE"}):
            raise ValueError("Forbidden API route")
        if method != "GET" and (not self.writable or not (
            (method == "POST" and path == "/pods") or
            (method == "DELETE" and re.fullmatch(r"/pods/[A-Za-z0-9_-]+", path))
        )):
            raise ValueError("Mutation disabled or outside owned lifecycle")
        request = urllib.request.Request(API + path, method=method,
            data=None if body is None else _canonical(body), headers={
                "Authorization": "Bearer " + self.token, "User-Agent": "codex-sae-assay/1.0",
                "Content-Type": "application/json"})
        try:
            with self.opener.open(request, timeout=30) as response:
                raw = response.read()
                return response.status, strict_json(raw) if raw else None
        except urllib.error.HTTPError as exc:
            raise ApiError(exc.code) from None  # Never serialize response bodies/credentials.
        except urllib.error.URLError:
            raise RuntimeError("RunPod transport outcome unknown; do not retry mutation") from None

    def inventory(self):
        pods, cursor, seen = [], None, set()
        while True:
            query = {"includeClusterPods": "true", "limit": 1000}
            if cursor:
                query["cursor"] = cursor
            _, page = self.request("GET", "/pods?" + urllib.parse.urlencode(query))
            pods.extend(page["pods"])
            pagination = page["pagination"]
            if pagination["hasNextPage"] is False:
                if len({p["id"] for p in pods}) != len(pods):
                    raise ValueError("Duplicate inventory IDs")
                return pods
            cursor = pagination["nextCursor"]
            if not isinstance(cursor, str) or not cursor or cursor in seen:
                raise ValueError("Incomplete inventory pagination")
            seen.add(cursor)


def quote(api, kind):
    gpu, ceiling, memory = HARDWARE[kind]
    _, item = api.request("GET", "/catalog/gpus/" + urllib.parse.quote(gpu, safe="")
                         + "?include=AVAILABILITY&product=POD&cloud=SECURE&count=1&minCudaVersion=12.8")
    rate = _number(item["price"]["secure"])
    if (item["id"] != gpu or item["secure"] is not True or item["memory"] < memory
            or item.get("availability") not in {"LOW", "MEDIUM", "HIGH"} or not 0 < rate <= ceiling):
        raise ValueError("Unknown/unavailable hardware or quote exceeds authorization")
    return {"hourly_rate_usd": str(rate), "storage_hourly_usd": str(STORAGE)}


def verify_public(plan_hash, relative, freeze):
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    urls = ["https://raw.githubusercontent.com/tdj28/llm_selfref_pre/" + freeze + "/" + relative,
            "https://hub.docker.com/v2/repositories/runpod/pytorch/tags/" + IMAGE_TAG]
    for index, url in enumerate(urls):
        with opener.open(urllib.request.Request(url, headers={"User-Agent": "codex-sae-assay/1.0"}), timeout=30) as response:
            raw = response.read()
        if index == 0 and hashlib.sha256(raw).hexdigest() != plan_hash:
            raise ValueError("Public freeze plan differs")
        if index == 1:
            image = strict_json(raw)
            if image.get("tag_status") != "active" or image.get("digest") != IMAGE_DIGEST:
                raise ValueError("Public image tag missing or digest changed")


def create_payload(kind, name, public_key):
    if not re.fullmatch(re.escape(PREFIX) + kind + r"-[0-9a-f]{12}", name):
        raise ValueError("Unique owned-pod name required")
    if not re.fullmatch(r"(?:ssh-ed25519|ssh-rsa|ecdsa-sha2-nistp256) [A-Za-z0-9+/=]+(?: [^\r\n]+)?", public_key):
        raise ValueError("Valid public SSH key required")
    return {"name": name, "image": IMAGE, "cloud": "SECURE",
            "gpu": {"id": HARDWARE[kind][0], "count": 1, "minCudaVersion": "12.8"},
            "disk": 50, "mounts": {"persistent": {"size": 250, "path": "/workspace"}},
            "ports": ["22/tcp"], "startSsh": True, "startJupyter": False,
            "env": {"PUBLIC_KEY": public_key}}


def clean_pod(pod):
    return {key: pod[key] for key in ("id", "name", "status", "createdAt", "cost", "gpu", "cloud",
                                      "image", "disk", "mounts", "ports", "ssh") if key in pod}


def local_env():
    return {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": str(Path.home()), "LANG": "C.UTF-8"}


def ssh_args(pod, key, known_hosts):
    direct = pod.get("ssh", {}).get("direct")
    if not isinstance(direct, dict):
        raise ValueError("Direct SSH not ready")
    host, port, user = direct["host"], direct["port"], direct["username"]
    if (not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9.:-]*", host) or user != "root"
            or type(port) is not int or not 1 <= port <= 65535):
        raise ValueError("Unsafe SSH endpoint")
    return ["ssh", "-F", "/dev/null", "-i", str(Path(key).expanduser()), "-p", str(port),
            "-o", "BatchMode=yes", "-o", "IdentitiesOnly=yes", "-o", "ForwardAgent=no",
            "-o", "ClearAllForwardings=yes", "-o", "PermitLocalCommand=no",
            "-o", "ConnectTimeout=15", "-o", "StrictHostKeyChecking=accept-new",
            "-o", "UserKnownHostsFile=" + str(known_hosts), user + "@" + host]


def worker_script(kind, plan_relative, freeze, deadline):
    if not re.fullmatch(r"[0-9a-f]{40}", freeze) or PurePosixPath(plan_relative).is_absolute() or ".." in PurePosixPath(plan_relative).parts:
        raise ValueError("Unsafe frozen source path")
    command = ["python3", "-m", "experiments.sae_assay_diagnostic.qualify", "--out", REMOTE + "/out/cheap-qualification.json"]
    if kind == "main":
        command = ["python3", "-m", "experiments.sae_assay_diagnostic.runner", "--plan", plan_relative,
                   "--freeze", freeze, "--out", REMOTE + "/out", "--stage", "all",
                   "--cache", "/workspace/cache", "--deadline-utc", deadline]
    exit_code = "import json,sys; json.dump({'exit_code':int(sys.argv[1])},open('" + REMOTE + "/out/controller-exit.json','x'))"
    return "\n".join([
        "set -euC", "umask 077", "mkdir -p " + REMOTE + "/out",
        "trap 'rc=$?; python3 -c " + shlex.quote(exit_code).replace("'", "'\"'\"'") + " \"$rc\"' EXIT",
        "git -c credential.helper= clone --filter=blob:none --no-checkout " + REPO + " " + REMOTE + "/repo",
        "cd " + REMOTE + "/repo", "git fetch --depth=1 origin " + freeze,
        "git checkout --detach " + freeze, 'test "$(git rev-parse HEAD)" = ' + freeze,
        "python3 -m pip install -r experiments/sae_assay_diagnostic/requirements-gpu.txt",
        "python3 -m pip freeze --all > " + REMOTE + "/out/pip-freeze.txt",
        ". " + REMOTE + "/hf.env", shlex.join(command),
    ])


SIGNAL_SCRIPT = """import json,os,pathlib,signal,sys,time
r=pathlib.Path('/workspace/sae-assay'); p=r/'worker.pid'
pid=int(p.read_text()); proc=pathlib.Path('/proc')/str(pid); action=sys.argv[1]
def members():
 result=[]
 for p in pathlib.Path('/proc').glob('[0-9]*/stat'):
  try:
   parts=p.read_text().split(') ',1)[1].split()
   if int(parts[2])==pid and parts[0]!='Z': result.append(parts[0])
  except FileNotFoundError: pass
 return result
if members():
 if not proc.exists() or os.getpgid(pid)!=pid or b'/workspace/sae-assay' not in (proc/'cmdline').read_bytes():
  raise RuntimeError('worker identity mismatch')
 if action=='resume': os.killpg(pid,signal.SIGCONT)
 elif action=='pause':
  os.killpg(pid,signal.SIGSTOP)
  for _ in range(100):
   if all(s in ('T','t') for s in members()): break
   time.sleep(0.1)
  else: raise RuntimeError('worker pause unverified')
 elif action=='stop':
  os.killpg(pid,signal.SIGCONT); os.killpg(pid,signal.SIGTERM)
  for _ in range(20):
   if not members(): break
   time.sleep(0.5)
  if members(): os.killpg(pid,signal.SIGKILL)
  for _ in range(20):
   if not members(): break
   time.sleep(0.5)
  if members(): raise RuntimeError('worker did not stop')
 else: raise RuntimeError('unknown signal action')
if action=='stop':
 q=r/'out/controller-stopped.json'
 if not q.exists():
  with q.open('x') as f:
   json.dump({'stopped':True,'pid':pid},f); f.flush(); os.fsync(f.fileno())
print(json.dumps({'action':action,'verified':True,'pid':pid}))
"""


MANIFEST_SCRIPT = """import hashlib,json,pathlib
root=pathlib.Path('/workspace/sae-assay/out'); result={}
if not root.is_dir(): raise RuntimeError('output directory missing')
for p in sorted(root.rglob('*')):
 if p.is_symlink(): raise RuntimeError('symlink artifact')
 if p.is_file():
  h=hashlib.sha256()
  with p.open('rb') as f:
   for block in iter(lambda:f.read(1048576),b''): h.update(block)
  result[p.relative_to(root).as_posix()]=h.hexdigest()
print(json.dumps(result,sort_keys=True))
"""
STATUS_SCRIPT = """import json,pathlib
r=pathlib.Path('/workspace/sae-assay/out'); d={}
for n in ['WAITING-qualification.json','WAITING-target-first5.json','DONE-all.json','controller-exit.json','controller-stopped.json']:
 p=r/n
 if p.is_file(): d[n]=json.loads(p.read_text())
d['_progress']={p.relative_to(r).as_posix():[p.stat().st_size,p.stat().st_mtime_ns]
 for p in r.rglob('*') if p.is_file() and not p.is_symlink()}
d['_approvals']={p.name:p.read_text().strip() for p in r.glob('APPROVE-*') if p.is_file()}
print(json.dumps(d))
"""


class Controller:
    def __init__(self, plan_path, freeze, out, kind, api, *, run=subprocess.run, clock=now, sleep=time.sleep):
        from .protocol import ROOT, load_plan
        self.plan_path, self.freeze, self.kind = Path(plan_path).resolve(), freeze, kind
        self.plan = load_plan(self.plan_path, freeze)
        self.plan_hash, self.relative = sha(self.plan_path), self.plan_path.relative_to(ROOT).as_posix()
        self.out = Path(out).resolve()
        self.base = self.out / "controller" / kind
        self.api, self.run, self.clock, self.sleep = api, run, clock, sleep
        self.guard = None
        self.ledger = EventLedger(self.base / "events.jsonl", self.plan_hash, freeze, [])
        self.ledger.bind("controller:config", {"kind": kind, "plan_path": self.relative, "image": IMAGE})

    def event(self, identifier):
        return next((r for r in self.ledger.read() if r["id"] == identifier), None)

    def record(self, prefix, payload):
        return self.ledger.transact(prefix + ":" + str(len(self.ledger.read())), lambda _: payload)

    def owned(self):
        event = self.event("created")
        if event is None or event["data"]["id"] == BLOCKED:
            raise ValueError("No owned creation receipt; refusing pod access")
        return event["data"]

    def get_pod(self):
        owned = self.owned()
        _, pod = self.api.request("GET", "/pods/" + owned["id"])
        if pod["id"] != owned["id"] or pod["name"] != owned["name"] or pod["createdAt"] != owned["createdAt"]:
            raise ValueError("Owned pod identity changed")
        return pod

    def _ssh(self, pod, command, *, data=None, timeout=60):
        result = self.run(ssh_args(pod, KEY, self.base / "known_hosts") + [command], input=data,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout, env=local_env())
        if result.returncode:
            raise RuntimeError("Owned-pod SSH failed; stderr withheld to avoid credential leakage")
        return result.stdout

    def launch(self):
        if not self.api.writable:
            raise ValueError("Explicit --launch required")
        if self.event("create-intent"):
            raise ValueError("Create already attempted; never retry an uncertain creation")
        self.disk_check()
        token = os.environ.get("HF_TOKEN", "")
        if not token or any(c.isspace() for c in token):
            raise ValueError("HF_TOKEN missing/malformed before creation")
        if not KEY.expanduser().is_file():
            raise ValueError("Existing private SSH key missing")
        prior = Decimal(0)
        if self.kind == "main":
            cheap_path = self.out / "controller/cheap/events.jsonl"
            if not cheap_path.is_file():
                raise ValueError("Cheap qualification has not completed")
            cheap = EventLedger(cheap_path, self.plan_hash, self.freeze, [])
            closed = next((r for r in cheap.read() if r["id"] == "closed"), None)
            if closed is None or (self.out / "APPROVE-cheap").read_text().strip() != self.plan_hash:
                raise ValueError("Audited cheap qualification and verified deletion required")
            prior = _number(closed["data"]["compute_upper_bound_usd"])
            if prior > 5:
                raise ValueError("Cheap qualification exceeded its cap")
        verify_public(self.plan_hash, self.relative, self.freeze)
        inventory = self.api.inventory()
        blocked = sorted({BLOCKED} | {p["id"] for p in inventory})
        PodRegistry(self.ledger, blocked)
        quoted = quote(self.api, self.kind)
        quoted_at = self.clock()
        key = (Path(str(KEY.expanduser()) + ".pub")).read_text().strip()
        payload = create_payload(self.kind, PREFIX + self.kind + "-" + uuid.uuid4().hex[:12], key)
        created = self.clock()
        rate = _number(quoted["hourly_rate_usd"]) + STORAGE
        limit = Decimal(5) if self.kind == "cheap" else Decimal(135) - prior
        # Leave ten dollars globally, and ten minutes locally for retrieval/shutdown.
        worker_dollars = min(limit, Decimal(125) - prior) - rate / 6
        if worker_dollars <= 0:
            raise ValueError("No funded startup/retrieval window")
        deadline = created + timedelta(seconds=float(worker_dollars / rate * 3600))
        if self.kind == "cheap":
            deadline = min(deadline, created + timedelta(minutes=35))  # 45 minutes including retrieval.
        guard = BudgetGuard(self.ledger, quoted, created, deadline, max_compute=135-prior, clock=self.clock)
        self.guard = guard
        guard.before_batch("create", 600, 0, 60)
        intent = {"payload": payload, "quote": quoted, "created_utc": created.isoformat(),
                  "deadline_utc": deadline.isoformat(), "prior_compute_usd": str(prior), "local_cap_usd": str(limit),
                  "blocked": blocked, "plan_sha256": self.plan_hash}
        self.ledger.transact("create-intent", lambda _: intent)
        if not 0 <= (self.clock() - quoted_at).total_seconds() <= 60:
            raise ValueError("Quote stale before creation; do not retry")
        try:
            status, pod = self.api.request("POST", "/pods", payload)  # Exactly one attempt.
            if status != 201 or not self._new_pod(pod, intent):
                raise ValueError("Ambiguous creation response")
        except (ApiError, RuntimeError, ValueError, OSError, KeyError, TypeError):
            pod = self.reconcile_create()  # Exact persisted unique name, never another POST.
        self._register(pod)
        try:
            self.start_worker()
        except Exception as exc:
            self.record("launch-failed", {"error_type": type(exc).__name__})
            if self.event("worker-intent"):
                self.quiesce()
            self.terminate()
            raise
        return self.owned()

    def _register(self, pod):
        intent = self.event("create-intent")["data"]
        receipt = self.ledger.bind("created", clean_pod(pod))
        registry = PodRegistry(self.ledger, intent["blocked"])
        if not self.event("pod:created:" + pod["id"]):
            registry.register_created(pod["id"], receipt["sha256"], [str(self.base / "final-retrieval.json")])
        if self.guard is None:
            self.guard = BudgetGuard(self.ledger, intent["quote"], intent["created_utc"], intent["deadline_utc"],
                                     max_compute=135-_number(intent["prior_compute_usd"]), clock=self.clock)
        if not self.event("budget:finish:create"):
            self.guard.finish_batch("create", 0, 60, receipt["sha256"])

    def reconcile(self):
        """Recover persisted single-create intent by GET only; never starts a worker."""
        if not self.event("create-intent"):
            raise ValueError("No creation intent to reconcile")
        if not self.event("created"):
            self._register(self.reconcile_create())
        return self.owned()

    def _new_pod(self, pod, intent):
        return (isinstance(pod, dict) and isinstance(pod.get("id"), str)
                and re.fullmatch(r"[A-Za-z0-9_-]+", pod["id"]) and pod["id"] not in intent["blocked"]
                and pod.get("name") == intent["payload"]["name"]
                and _utc(pod["createdAt"]) >= _utc(intent["created_utc"]) - timedelta(seconds=60))

    def reconcile_create(self):
        intent = self.event("create-intent")["data"]
        for attempt in range(12):
            matches = [p for p in self.api.inventory() if p.get("name") == intent["payload"]["name"]]
            if len(matches) > 1:
                raise ValueError("Ambiguous exact-name inventory; manual reconciliation required")
            if matches:
                if not self._new_pod(matches[0], intent):
                    raise ValueError("Reconciled pod identity invalid")
                self.record("create-reconciled", {"pod": clean_pod(matches[0]), "attempt": attempt})
                return matches[0]
            self.sleep(5)
        raise RuntimeError("Create outcome unresolved: retain intent and reconcile exact name; never create again")

    def cost_check(self, pod, horizon=60):
        intent = self.event("create-intent")["data"]
        rate = _number(pod.get("cost"))
        quote_rate = _number(intent["quote"]["hourly_rate_usd"])
        expected = intent["payload"]
        if (not 0 < rate <= quote_rate or pod.get("cloud") != "SECURE"
                or pod.get("gpu", {}).get("id") != HARDWARE[self.kind][0] or pod["gpu"].get("count") != 1
                or any(pod.get(k) != expected[k] for k in ("image", "disk", "mounts", "ports"))):
            raise ValueError("Unknown billing rate or hardware drift")
        if self.guard is None:
            self.guard = BudgetGuard(self.ledger, intent["quote"], intent["created_utc"], intent["deadline_utc"],
                                     max_compute=135-_number(intent["prior_compute_usd"]), clock=self.clock)
        tick = "monitor-" + str(len(self.ledger.read()))
        reserved = self.guard.before_batch(tick, horizon, 0, 60)
        spent = _number(reserved["data"]["compute_accounted_usd"])
        self.guard.finish_batch(tick, spent, 60, reserved["sha256"])
        projected = spent + Decimal(horizon) * (quote_rate + STORAGE) / 3600
        if (projected > _number(intent["local_cap_usd"]) or
                projected + _number(intent["prior_compute_usd"]) + 10 > 135 or
                self.clock() + timedelta(seconds=horizon) >= _utc(intent["deadline_utc"])):
            raise ValueError("Retrieval reserve/deadline reached")
        return spent

    def start_worker(self):
        if self.event("worker-intent"):
            raise ValueError("Worker dispatch uncertain/already attempted; no duplicate worker")
        intent = self.event("create-intent")["data"]
        for _ in range(40):
            pod = self.get_pod()
            self.cost_check(pod, 600)
            if pod.get("status") == "RUNNING" and pod.get("ssh", {}).get("direct"):
                try:
                    self._ssh(pod, "true", timeout=15)
                    break
                except (RuntimeError, subprocess.TimeoutExpired):
                    pass
            if pod.get("status") not in {"PROVISIONING", "STARTING", "RUNNING"}:
                raise ValueError("Owned pod failed startup")
            self.sleep(15)
        else:
            raise TimeoutError("SSH startup exceeded bounded readiness window")
        token = os.environ.get("HF_TOKEN", "")
        if not token or any(c.isspace() for c in token):
            raise ValueError("HF_TOKEN missing or malformed; worker not started")
        self._ssh(pod, "umask 077; mkdir -p " + REMOTE + "/out; cat > " + REMOTE + "/hf.env; chmod 600 " + REMOTE + "/hf.env",
                  data=("export HF_TOKEN=" + shlex.quote(token) + "\n").encode())
        script = worker_script(self.kind, self.relative, self.freeze, intent["deadline_utc"])
        seconds = int((_utc(intent["deadline_utc"]) - self.clock()).total_seconds())
        self.ledger.transact("worker-intent", lambda _: {"script_sha256": hashlib.sha256(script.encode()).hexdigest(), "seconds": seconds})
        command = ("nohup setsid timeout --signal=TERM --kill-after=30s " + str(seconds)
                   + "s env -i HOME=/root"
                   + " PATH=/usr/local/cuda/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
                   + " LD_LIBRARY_PATH=/usr/local/cuda/lib64 bash --noprofile --norc -c "
                   + shlex.quote(script) + " >" + REMOTE
                   + "/out/controller.log 2>&1 </dev/null & echo $! > " + REMOTE + "/worker.pid")
        self._ssh(pod, command)
        self.ledger.transact("worker-started", lambda _: {"utc": self.clock().isoformat()})

    def status(self):
        pod = self.get_pod()
        state = {"pod": clean_pod(pod), "files": {}}
        if pod.get("status") == "RUNNING" and pod.get("ssh", {}).get("direct"):
            state["files"] = strict_json(self._ssh(pod, "python3 -c " + shlex.quote(STATUS_SCRIPT)))
        return state

    def quiesce(self):
        pod = self.get_pod()
        result = self.signal_worker(pod, "stop")
        self.record("worker-stopped", result)

    def signal_worker(self, pod, action):
        if action not in {"pause", "resume", "stop"} or pod["id"] != self.owned()["id"]:
            raise ValueError("Unknown worker or signal")
        result = strict_json(self._ssh(pod, "python3 -c " + shlex.quote(SIGNAL_SCRIPT) + " " + action))
        if result.get("verified") is not True or result.get("action") != action:
            raise ValueError("Owned worker signal unverified")
        return result

    def retrieve(self, *, final=False):
        self.disk_check()
        pod = self.get_pod()
        if final and not self.event("worker-intent"):
            receipt = self.record("retrieval", {"pod_id": pod["id"], "no_worker_dispatched": True,
                                               "artifacts": {}, "pod": clean_pod(pod)})
            self._final_receipt(receipt)
            return receipt
        if final:
            self.quiesce()
            return self._snapshot(pod, final=True)
        try:
            self.signal_worker(pod, "pause")
            return self._snapshot(pod, final=False)
        finally:
            self.signal_worker(pod, "resume")

    def _snapshot(self, pod, *, final):
        manifest_command = "python3 -c " + shlex.quote(MANIFEST_SCRIPT)
        before = strict_json(self._ssh(pod, manifest_command))
        for name, digest in before.items():
            if PurePosixPath(name).is_absolute() or ".." in PurePosixPath(name).parts or not re.fullmatch(r"[0-9a-f]{64}", digest):
                raise ValueError("Unsafe remote manifest")
        destination = self.base / "retrievals" / uuid.uuid4().hex
        destination.mkdir(parents=True, exist_ok=False)
        ssh = ssh_args(pod, KEY, self.base / "known_hosts")
        previous = next((r["data"]["directory"] for r in reversed(self.ledger.read())
                         if r["id"].startswith("retrieval:") and "directory" in r["data"]), None)
        reuse = ["--link-dest=" + str(Path(previous).resolve())] if previous else []
        result = self.run(["rsync", "-rt", "--safe-links", "--no-links", *reuse, "-e", shlex.join(ssh[:-1]),
                           ssh[-1] + ":" + REMOTE + "/out/", str(destination) + "/"],
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=300, env=local_env())
        if result.returncode:
            raise RuntimeError("Retrieval failed; owned pod retained")
        after = strict_json(self._ssh(pod, manifest_command))
        local = {p.relative_to(destination).as_posix(): sha(p) for p in destination.rglob("*") if p.is_file() and not p.is_symlink()}
        if before != after or before != local:
            raise ValueError("Live snapshot changed or local artifact hashes differ; retry read-only retrieval")
        receipt = self.record("retrieval", {"pod_id": pod["id"], "directory": str(destination), "artifacts": local,
                                          "utc": self.clock().isoformat()})
        if final:
            if self.event("worker-intent") and not any(name in local for name in TERMINAL):
                raise ValueError("Worker has not stopped; refusing destructive cleanup")
            self._final_receipt(receipt)
        return receipt

    def disk_check(self):
        if shutil.disk_usage(self.base).free < 8 * 1024 ** 3:
            raise ValueError("At least 8 GiB free local disk required; old raw snapshots are never deleted")

    def _final_receipt(self, receipt):
        with (self.base / "final-retrieval.json").open("xb") as handle:
            handle.write(_canonical(receipt) + b"\n")
            handle.flush()
            os.fsync(handle.fileno())

    def _verify_final(self):
        receipt = strict_json((self.base / "final-retrieval.json").read_bytes())
        if self.event(receipt["id"]) != receipt:
            raise ValueError("Final retrieval receipt is not bound to this ledger")
        data = receipt["data"]
        for name, digest in data["artifacts"].items():
            path = Path(data["directory"]) / name
            if path.is_symlink() or not path.is_file() or sha(path) != digest:
                raise ValueError("Retrieved artifact missing or corrupt")

    def terminate(self):
        if not self.api.writable:
            raise ValueError("Explicit --launch required for termination")
        if self.event("closed"):
            return self.event("closed")
        if self.event("delete-intent"):
            return self._confirm_closed(self.event("delete-intent")["data"]["pod"])
        pod = self.get_pod()
        if not self.event("delete-intent"):
            if not (self.base / "final-retrieval.json").exists():
                self.retrieve(final=True)
            self._verify_final()
            manifest_path = self.base / "final-retrieval.json"
            registry = PodRegistry(self.ledger, self.event("create-intent")["data"]["blocked"])
            permit = registry.authorize_delete(pod["id"], {str(manifest_path): sha(manifest_path)})
            self.ledger.transact("delete-intent", lambda _: {"permit_sha256": permit["sha256"], "pod_id": pod["id"], "pod": clean_pod(pod)})
            status, _ = self.api.request("DELETE", "/pods/" + pod["id"])
            if status != 204:
                raise ValueError("Unexpected delete response")
        else:
            raise ValueError("Deletion already attempted; reconcile read-only, never repeat blindly")
        return self._confirm_closed(pod)

    def _confirm_closed(self, pod):
        try:
            self.api.request("GET", "/pods/" + pod["id"])
        except ApiError as exc:
            if exc.status != 404:
                raise
        else:
            raise ValueError("Deletion not verified")
        if pod["id"] in {p["id"] for p in self.api.inventory()}:
            raise ValueError("Deleted pod still in inventory")
        intent = self.event("create-intent")["data"]
        cost = None
        if pod.get("cost") is not None:
            elapsed = max(_number((self.clock() - _utc(intent["created_utc"])).total_seconds()),
                          max((_number(r["data"]["elapsed_seconds"]) for r in self.ledger.read()
                               if "elapsed_seconds" in r["data"]), default=Decimal(0)))
            cost = str(elapsed * (max(_number(pod["cost"]), _number(intent["quote"]["hourly_rate_usd"])) + STORAGE) / 3600)
        return self.ledger.transact("closed", lambda _: {"pod_id": pod["id"], "compute_upper_bound_usd": cost,
                                                        "utc": self.clock().isoformat(), "get_status": 404})

    def monitor(self):
        if not self.api.writable:
            raise ValueError("Lifecycle monitor requires explicit --launch")
        last_pull = float("-inf")
        previous, changed_at, announced = None, time.monotonic(), None
        while True:
            state = self.status()
            self.record("health", state)
            terminal = any(n in state["files"] for n in TERMINAL)
            progress = state["files"].get("_progress", {})
            waiting = [n for n in WAITING if n in state["files"] and state["files"].get("_approvals", {}).get(
                n.replace("WAITING-", "APPROVE-").removesuffix(".json")) != self.plan_hash]
            if progress != previous:
                previous, changed_at = progress, time.monotonic()
            stall_limit = 900 if any(n.startswith("rows/") for n in progress) else 1800
            try:
                self.cost_check(state["pod"], 600)
                if not waiting and time.monotonic() - changed_at >= stall_limit:
                    raise ValueError("Owned worker stalled")
            except ValueError:
                if not terminal:
                    self.quiesce()
                return self.terminate()
            if terminal:
                return self.terminate()
            if waiting != announced or time.monotonic() - last_pull >= 600:
                self.retrieve()
                last_pull = time.monotonic()
                if waiting and waiting != announced:
                    print("WAITING: audit snapshot; parent must write approval. Controller does not approve.", flush=True)
                announced = waiting
            self.sleep(60)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for flag in ("plan", "freeze", "out"):
        parser.add_argument("--" + flag, required=True)
    parser.add_argument("--kind", choices=HARDWARE, required=True)
    parser.add_argument("--action", choices=("launch", "status", "retrieve", "monitor", "terminate", "reconcile"), default="launch")
    parser.add_argument("--launch", action="store_true")
    args = parser.parse_args(argv)
    if not args.launch:
        print(json.dumps({"dry_run": True, "action": args.action, "kind": args.kind,
                          "protected_pod": BLOCKED, "network_calls": 0, "approval": "never automatic"}))
        return
    api = RunPodV2(os.environ.get("RUNPOD_API_KEY"), writable=True)
    controller = Controller(args.plan, args.freeze, args.out, args.kind, api)
    print(json.dumps(getattr(controller, args.action)(), sort_keys=True))


if __name__ == "__main__":
    main()

"""Single newly owned B200 lifecycle for exposure and the precision-only pilot.

Default preflight is offline/read-only. The parent protocol's load_plan(path,
freeze) validates the full-BF16, 224-clean-text screen followed by the separate
12-text precision-transport pilot. Neither phase generates responses or judges.
The runner performs synthetic qualification before model loading, then emits
WAITING-qualification.json and WAITING-first-five.json using Run.barrier's
plan_sha256/freeze_commit/barrier/rows schema (receipted rows: 1 and 6). Only explicit local approval
after a hash-verified snapshot releases either barrier; DONE-all.json ends work.
Recursive snapshots also preserve every receipt/raw/capture under out/precision/.

The two-hour operational limit includes a ten-minute retrieval reserve. Keep
the local monitor supervised: remote timeout stops computation, not billing.
Provider/retrieval failures can exceed the limit; cleanup preserves evidence,
retries read-only reconciliation, and never claims an unenforced provider cap.
"""
from __future__ import annotations

import argparse
from datetime import timedelta
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shlex
import subprocess
import time
import urllib.parse
import uuid

from experiments.sae_assay_diagnostic import controller as frozen
from experiments.sae_assay_diagnostic.budget import EventLedger, PodRegistry, _number, _utc
from experiments.sae_assay_replay import controller as lifecycle

ROOT = Path(__file__).resolve().parents[2]
PREFIX, NAMESPACE = "codex-sae-exposure-20260930-", "exposure-controller"
PRIOR_TOTAL, MAX_NEW = Decimal("27.6350693241315361"), Decimal("25")
HARDWARE = {"main": frozen.HARDWARE["main"]}
HARD_SECONDS, RETRIEVAL_SECONDS = lifecycle.HARD_SECONDS, lifecycle.RETRIEVAL_SECONDS
PLAN_HARDWARE = {"gpu": "NVIDIA B200", "count": 1, "memory_gb": 180,
                 "hourly_price_ceiling_usd": 6.79, "hard_seconds": 7200}
IMAGE, STORAGE, KEY = frozen.IMAGE, frozen.STORAGE, frozen.KEY
# The inherited snapshot/teardown helpers use these private paths on a fresh pod.
HF_ENV, REMOTE = lifecycle.HF_ENV, frozen.REMOTE
RunPodV2, ApiError = frozen.RunPodV2, frozen.ApiError
sha, strict_json, verify_public = frozen.sha, frozen.strict_json, frozen.verify_public
serialized = lifecycle.serialized
BARRIERS = ("qualification", "first-five")
BARRIER_ROWS = {"qualification": 1, "first-five": 6}
WAITING = tuple("WAITING-" + name + ".json" for name in BARRIERS)
STATUS_SCRIPT = """import json,pathlib
r=pathlib.Path(%r); d={}
for n in %r:
 p=r/n
 if p.is_file(): d[n]=json.loads(p.read_text())
d['_progress']={p.relative_to(r).as_posix():[p.stat().st_size,p.stat().st_mtime_ns]
 for p in r.rglob('*') if p.is_file() and not p.is_symlink()}
d['_approvals']={p.name:p.read_text().strip() for p in r.glob('APPROVE-*') if p.is_file()}
print(json.dumps(d))
""" % (REMOTE + "/out", list(WAITING + frozen.TERMINAL))

# Stdin carries the persisted dispatch identity, never credentials. Both this
# reconciler and the launcher hold the same remote lock; the permanent fence
# also stops an SSH command that arrives after cleanup has already begun.
WORKER_SIGNAL_SCRIPT = """import fcntl,json,os,pathlib,signal,stat,sys,time
d=json.load(sys.stdin); r=pathlib.Path(d['remote']); b=d['binding']; action=d['action']
proc=pathlib.Path('/proc'); pidfile=r/'worker.pid'; fence=r/'worker-closing.json'
markers=[('CODEX_EXPOSURE_'+k+'='+v).encode() for k,v in
 [('NAMESPACE','exposure-controller'),('WORKER_ID',b['worker_id']),
  ('FREEZE',b['freeze_commit']),('POD_ID',b['pod_id'])]]
def write_once(path,value):
 if path.is_symlink(): raise RuntimeError('worker evidence symlink')
 if path.exists():
  if json.loads(path.read_text())!=value: raise RuntimeError('worker evidence binding mismatch')
 else:
  with path.open('x') as f:
   json.dump(value,f,sort_keys=True); f.flush(); os.fsync(f.fileno())
def scan():
 table={}
 for p in proc.glob('[0-9]*'):
  try:
   fields=(p/'stat').read_text().split(') ',1)[1].split()
   if fields[0] in ('Z','X'): continue
   env=(p/'environ').read_bytes().split(b'\\0')
   argv=(p/'cmdline').read_bytes().split(b'\\0')
   # Shell launchers contain the markers inside their command-string argument.
   marked=all(m in env or any(m in arg for arg in argv) for m in markers)
   table[int(p.name)]={'state':fields[0],'group':int(fields[2]),
                       'session':int(fields[3]),'start':fields[19],'marked':marked}
  except (FileNotFoundError,ProcessLookupError): pass
  except (OSError,ValueError,IndexError):
   raise RuntimeError('worker process inventory incomplete') from None
 return table
def members(table,pid):
 return {p:v for p,v in table.items() if v['group']==pid}
def send(pid,sig):
 try: os.killpg(pid,sig)
 except ProcessLookupError: pass
def finish(pid,missing,recovered):
 result={'action':action,'verified':True,'pid':pid,'binding':b,
         'missing_pid':missing,'recovered_pid':recovered}
 if action=='stop':
  result.update(stopped=True,dispatch_fenced=True,no_matching_worker=True)
  terminal=r/'out/controller-stopped.json'
  if terminal.is_symlink(): raise RuntimeError('worker evidence symlink')
  if terminal.exists():
   old=json.loads(terminal.read_text())
   if old.get('binding')!=b or old.get('stopped') is not True or old.get('dispatch_fenced') is not True:
    raise RuntimeError('worker stopped receipt binding mismatch')
  else: write_once(terminal,result)
 print(json.dumps(result))
if action not in ('pause','resume','stop'): raise RuntimeError('invalid worker action')
fd=os.open(r/'worker-dispatch.lock',os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW,0o600)
try:
 if not stat.S_ISREG(os.fstat(fd).st_mode): raise RuntimeError('invalid worker lock')
 fcntl.flock(fd,fcntl.LOCK_EX)
 if action=='stop': write_once(fence,b)
 elif fence.exists(): raise RuntimeError('worker lifecycle fenced')
 if pidfile.is_symlink(): raise RuntimeError('worker PID symlink')
 table=scan(); matching={p:v for p,v in table.items() if v['marked']}
 missing=not pidfile.exists(); recovered=False
 if missing:
  if not matching:
   if action!='stop': raise RuntimeError('worker PID absent before stop')
   time.sleep(0.1)
   if any(v['marked'] for v in scan().values()): raise RuntimeError('worker appeared during reconciliation')
   finish(None,True,False)
   sys.exit(0)
  groups={v['group'] for v in matching.values()}
  if len(groups)!=1: raise RuntimeError('ambiguous worker process groups')
  pid=next(iter(groups)); leader=table.get(pid)
  if not leader or not leader['marked'] or leader['session']!=pid:
   raise RuntimeError('unbound live worker without PID')
  if action!='stop': raise RuntimeError('worker PID recovery requires stop')
  with pidfile.open('x') as f:
   f.write(str(pid)+'\\n'); f.flush(); os.fsync(f.fileno())
  write_once(r/'out/controller-worker-reconciled.json',{'binding':b,'pid':pid,
               'start':leader['start'],'missing_pid':True})
  recovered=True
 else:
  raw=pidfile.read_text().strip()
  if not raw.isdecimal() or int(raw)<=1: raise RuntimeError('invalid worker PID')
  pid=int(raw)
 if any(v['group']!=pid for v in matching.values()): raise RuntimeError('worker identity in another group')
 live=members(table,pid)
 if live:
  leader=table.get(pid)
  if not leader or not leader['marked'] or leader['group']!=pid or leader['session']!=pid:
   raise RuntimeError('worker leader identity mismatch')
  start=leader['start']
  if action=='resume': send(pid,signal.SIGCONT)
  elif action=='pause':
   send(pid,signal.SIGSTOP)
   for _ in range(100):
    if all(v['state'] in ('T','t') for v in members(scan(),pid).values()): break
    time.sleep(0.1)
   else: raise RuntimeError('worker pause unverified')
  else:
   send(pid,signal.SIGCONT); send(pid,signal.SIGTERM)
   for _ in range(20):
    if not members(scan(),pid): break
    time.sleep(0.5)
   current=scan(); live=members(current,pid)
   if live:
    if any(v['session']!=pid for v in live.values()) or (
       pid in current and current[pid]['start']!=start):
     raise RuntimeError('worker identity changed before kill')
    send(pid,signal.SIGKILL)
   for _ in range(20):
    if not members(scan(),pid): break
    time.sleep(0.5)
   else: raise RuntimeError('worker did not stop')
 if action=='stop' and any(v['marked'] for v in scan().values()):
  raise RuntimeError('matching worker remains after stop')
 finish(pid,missing,recovered)
finally:
 os.close(fd)
"""


def load_plan(path, freeze):
    from experiments.sae_assay_exposure.protocol import load_plan as exposure_load_plan
    return exposure_load_plan(path, freeze)


def checked_budget(plan):
    hardware = plan.get("hardware", {})
    if (hardware != PLAN_HARDWARE or any(type(hardware.get(k)) is not int
            for k in ("count", "memory_gb", "hard_seconds"))):
        raise ValueError("Exposure plan must pin the single B200 hardware/timer contract")
    budget = plan.get("budget", {})
    if set(budget) != {"prior_total_usd", "total_usd", "exposure_max_usd",
                       "new_paid_judge_calls", "new_pro_calls"}:
        raise ValueError("Complete exposure-only budget required")
    amounts = {key: _number(value) for key, value in budget.items()}
    if (amounts["prior_total_usd"] != PRIOR_TOTAL
            or not 0 < amounts["exposure_max_usd"] <= MAX_NEW
            or not PRIOR_TOTAL + amounts["exposure_max_usd"] <= amounts["total_usd"] <= 200
            or amounts["new_paid_judge_calls"] != 0 or amounts["new_pro_calls"] != 0):
        raise ValueError("Exposure budget exceeds or resets the existing authorization")
    return amounts


def quote(api, kind="main"):
    if kind != "main":
        raise ValueError("Only a single B200 exposure pod is authorized")
    gpu, ceiling, memory = HARDWARE[kind]
    _, item = api.request("GET", "/catalog/gpus/" + urllib.parse.quote(gpu, safe="")
                         + "?include=AVAILABILITY&product=POD&cloud=SECURE&count=1&minCudaVersion=12.8")
    rate = _number(item["price"]["secure"])
    if (item["id"] != gpu or item["secure"] is not True or _number(item["memory"]) < memory
            or item.get("availability") not in {"LOW", "MEDIUM", "HIGH"} or not 0 < rate <= ceiling):
        raise ValueError("Unknown/unavailable B200 or quote exceeds authorization; no fallback")
    return {"hourly_rate_usd": str(rate), "storage_hourly_usd": str(STORAGE)}


def create_payload(kind, name, public_key):
    if kind != "main" or not re.fullmatch(re.escape(PREFIX) + r"main-[0-9a-f]{12}", name):
        raise ValueError("Unique exposure-owned B200 name required")
    payload = frozen.create_payload(kind, frozen.PREFIX + "main-" + name[-12:], public_key)
    return {**payload, "name": name}


def worker_script(kind, plan_relative, freeze, deadline, *, hourly_usd, pod_started_utc):
    path = PurePosixPath(plan_relative)
    if (kind != "main" or not re.fullmatch(r"[0-9a-f]{40}", freeze)
            or path.is_absolute() or ".." in path.parts or path.as_posix() != plan_relative
            or not path.parts or plan_relative.startswith("-") or any(ord(c) < 32 for c in plan_relative)):
        raise ValueError("Unsafe exposure source path, freeze or kind")
    rate, started, end = _number(hourly_usd), _utc(pod_started_utc), _utc(deadline)
    if not (0 < rate <= HARDWARE["main"][1] + STORAGE
            and 0 < (end - started).total_seconds() <= HARD_SECONDS - RETRIEVAL_SECONDS):
        raise ValueError("Bounded creation-time deadline and all-in hourly rate required")
    python = REMOTE + "/venv/bin/python"
    validation = ("from experiments.sae_assay_exposure.protocol import load_plan; "
                  + "load_plan(" + repr(plan_relative) + ", " + repr(freeze) + ")")
    exit_code = ("import json,sys; json.dump({'exit_code':int(sys.argv[1])},open("
                 + repr(REMOTE + "/out/controller-exit.json") + ",'x'))")
    command = [python, "-u", "-m", "experiments.sae_assay_exposure.runner", "--plan", plan_relative,
               "--freeze", freeze, "--out", REMOTE + "/out", "--cache", "/workspace/cache",
               "--deadline-utc", deadline, "--hourly-usd", str(rate),
               "--pod-started-utc", pod_started_utc]
    return "\n".join([
        "set -euC", "umask 077", "mkdir -p " + REMOTE + "/out",
        "trap 'rc=$?; rm -f " + HF_ENV + "; python3 -c "
        + shlex.quote(exit_code).replace("'", "'\"'\"'") + " \"$rc\"' EXIT",
        "git -c credential.helper= clone --filter=blob:none --no-checkout " + frozen.REPO + " " + REMOTE + "/repo",
        "cd " + REMOTE + "/repo", "git fetch --depth=1 origin " + freeze,
        "git checkout --detach " + freeze, 'test "$(git rev-parse HEAD)" = ' + freeze,
        "python3 -m venv --system-site-packages " + REMOTE + "/venv",
        python + " -m pip install -r experiments/sae_assay_diagnostic/requirements-gpu.txt",
        python + " -m pip freeze --all > " + REMOTE + "/out/pip-freeze.txt",
        shlex.join([python, "-c", validation]),
        "set +x; . " + HF_ENV + "; rm -f " + HF_ENV,
        "export HF_HOME=/workspace/cache PYTHONUNBUFFERED=1",
        shlex.join(command),
    ])


def dispatch_command(script, seconds, binding):
    """Fence both the SSH launcher and its detached child before any work."""
    lock, fence = REMOTE + "/worker-dispatch.lock", REMOTE + "/worker-closing.json"
    gate = ("set -eu; umask 077; test ! -L " + shlex.quote(lock) + "; exec 9>>" + shlex.quote(lock)
            + "; flock -x 9; test ! -e " + shlex.quote(fence) + "; ")
    child = gate + "flock -u 9; exec 9>&-\n" + script
    markers = ["CODEX_EXPOSURE_NAMESPACE=" + NAMESPACE,
               "CODEX_EXPOSURE_WORKER_ID=" + binding["worker_id"],
               "CODEX_EXPOSURE_FREEZE=" + binding["freeze_commit"],
               "CODEX_EXPOSURE_POD_ID=" + binding["pod_id"]]
    return (gate + "umask 077; set -C; test ! -e " + shlex.quote(REMOTE + "/worker.pid")
            + "; nohup setsid timeout --signal=TERM --kill-after=30s " + str(seconds - 30)
            + "s env -i HOME=/root"
            + " PATH=/usr/local/cuda/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
            + " LD_LIBRARY_PATH=/usr/local/cuda/lib64 " + shlex.join(markers)
            + " bash --noprofile --norc -c " + shlex.quote(child)
            + " >" + shlex.quote(REMOTE + "/out/controller.log")
            + " 2>&1 </dev/null 9>&- & pid=$!; printf '%s\\n' \"$pid\" > "
            + shlex.quote(REMOTE + "/worker.pid") + "; flock -u 9")


def preflight(plan_path, freeze):
    path = Path(plan_path).resolve()
    budget = checked_budget(load_plan(path, freeze))
    started = frozen.now()
    worker_script("main", path.relative_to(ROOT).as_posix(), freeze,
                  (started + timedelta(seconds=HARD_SECONDS - RETRIEVAL_SECONDS)).isoformat(),
                  hourly_usd=HARDWARE["main"][1] + STORAGE, pod_started_utc=started.isoformat())
    return {"preflight": True, "network_calls": 0, "namespace": NAMESPACE,
            "plan_sha256": sha(path), "freeze_commit": freeze, "gpu": HARDWARE["main"][0],
            "image": IMAGE, "hard_seconds": HARD_SECONDS, "retrieval_seconds": RETRIEVAL_SECONDS,
            "maximum_timer_cost_usd": str((HARDWARE["main"][1] + STORAGE) * HARD_SECONDS / 3600),
            "new_cap_usd": str(budget["exposure_max_usd"]),
            "cumulative_ceiling_usd": str(PRIOR_TOTAL + budget["exposure_max_usd"])}


class Controller(lifecycle.Controller):
    """Reuse locking, ownership, coherent snapshots and deletion, not old dispatch.

    Inherited terminate/close_until_verified rely on the same remote paths and
    7200/600-second timers. Exposure owns launch, accounting, closure accounting,
    status and approvals; no frozen module globals are modified.
    """

    def __init__(self, plan_path, freeze, out, kind, api, *, run=subprocess.run,
                 clock=frozen.now, sleep=time.sleep, monotonic=time.monotonic):
        if kind != "main" or not re.fullmatch(r"[0-9a-f]{40}", freeze):
            raise ValueError("Exposure requires main B200 hardware and an exact freeze")
        self.plan_path, self.freeze, self.kind = Path(plan_path).resolve(), freeze, kind
        self.plan = load_plan(self.plan_path, freeze)
        self.budget = checked_budget(self.plan)
        self.plan_hash, self.relative = sha(self.plan_path), self.plan_path.relative_to(ROOT).as_posix()
        self.out = Path(out).resolve()
        self.base = self.out / NAMESPACE / kind
        for directory in (self.base.parent, self.base):
            if directory.is_symlink():
                raise ValueError("Private exposure namespace cannot be a symlink")
            directory.mkdir(parents=True, exist_ok=True, mode=0o700)
            directory.chmod(0o700)
        self.api, self.run, self.clock, self.sleep, self.monotonic = api, run, clock, sleep, monotonic
        self._wall0, self._mono0 = _utc(clock()), _number(monotonic())
        self._last_mono = self._mono0
        self.ledger = EventLedger(self.base / "events.jsonl", self.plan_hash, freeze, [])
        self.ledger.path.chmod(0o600)
        self._elapsed0 = max((_number(row["data"]["elapsed_seconds"]) for row in self.ledger.read()
                             if "elapsed_seconds" in row["data"]), default=Decimal(0))
        self.ledger.bind("controller:config", {"kind": kind, "namespace": NAMESPACE,
                         "plan_path": self.relative, "image": IMAGE, "budget": self.plan["budget"],
                         "hardware": PLAN_HARDWARE,
                         "hard_seconds": HARD_SECONDS, "retrieval_seconds": RETRIEVAL_SECONDS})

    def _new_pod(self, pod, intent):
        name = intent["payload"].get("name", "")
        return (re.fullmatch(re.escape(PREFIX) + r"main-[0-9a-f]{12}", name) is not None
                and intent.get("plan_sha256") == self.plan_hash
                and intent.get("freeze_commit") == self.freeze
                and frozen.Controller._new_pod(self, pod, intent))

    def _ssh(self, pod, command, *, data=None, timeout=60):
        owned = self.owned()
        if any(pod.get(key) != owned[key] for key in ("id", "name", "createdAt")):
            raise ValueError("SSH is restricted to the newly owned exposure pod")
        result = self.run(frozen.ssh_args(pod, KEY, self.base / "known_hosts") + [command], input=data,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout, env=frozen.local_env())
        if result.returncode:
            raise RuntimeError("Owned-pod SSH failed; stderr withheld to avoid credential leakage")
        return result.stdout

    @serialized
    def launch(self):
        if not self.api.writable:
            raise ValueError("Explicit --launch required")
        if self.event("create-intent"):
            raise ValueError("Create already attempted; never retry an uncertain creation")
        if load_plan(self.plan_path, self.freeze) != self.plan or sha(self.plan_path) != self.plan_hash:
            raise ValueError("Exposure plan changed since controller construction")
        self.disk_check()
        token = os.environ.get("HF_TOKEN", "")
        if not token or any(c.isspace() for c in token):
            raise ValueError("HF_TOKEN missing/malformed before creation")
        if not KEY.expanduser().is_file():
            raise ValueError("Existing private SSH key missing")
        key = Path(str(KEY.expanduser()) + ".pub").read_text().strip()
        payload = create_payload(self.kind, PREFIX + "main-" + uuid.uuid4().hex[:12], key)
        verify_public(self.plan_hash, self.relative, self.freeze)
        blocked = sorted({frozen.BLOCKED} | {p["id"] for p in self.api.inventory()})
        PodRegistry(self.ledger, blocked)
        quoted = quote(self.api)
        created = _utc(self.clock())
        rate = _number(quoted["hourly_rate_usd"]) + _number(quoted["storage_hourly_usd"])
        cap = self.budget["exposure_max_usd"]
        if rate * HARD_SECONDS / 3600 > cap:
            raise ValueError("Full pod timer including retrieval is not funded")
        intent = {"payload": payload, "quote": quoted, "blocked": blocked,
                  "created_utc": created.isoformat(),
                  "deadline_utc": (created + timedelta(seconds=HARD_SECONDS - RETRIEVAL_SECONDS)).isoformat(),
                  "hard_deadline_utc": (created + timedelta(seconds=HARD_SECONDS)).isoformat(),
                  "prior_total_usd": str(PRIOR_TOTAL), "local_cap_usd": str(cap),
                  "cumulative_ceiling_usd": str(PRIOR_TOTAL + cap),
                  "plan_sha256": self.plan_hash, "freeze_commit": self.freeze}
        self.ledger.transact("create-intent", lambda _: intent)
        self._wall0, self._mono0 = created, _number(self.monotonic())
        self._last_mono = self._mono0
        if not 0 <= (_utc(self.clock()) - created).total_seconds() <= 60:
            raise ValueError("Quote stale before creation; do not retry")
        try:
            status, pod = self.api.request("POST", "/pods", payload)
            if status != 201 or not self._new_pod(pod, intent):
                raise ValueError("Ambiguous creation response")
        except (ApiError, RuntimeError, ValueError, OSError, KeyError, TypeError):
            pod = self.reconcile_create()
        self._register(pod)
        try:
            self.start_worker()
        except Exception as exc:
            self.record("launch-failed", {"error_type": type(exc).__name__})
            self.close_until_verified()
            raise
        return self.owned()

    def cost_check(self, pod, horizon=60):
        intent, owned = self.event("create-intent")["data"], self.owned()
        expected, quoted = intent["payload"], _number(intent["quote"]["hourly_rate_usd"])
        gpu = pod.get("gpu")
        if (any(pod.get(key) != owned[key] for key in ("id", "name", "createdAt"))
                or not 0 < _number(pod.get("cost")) <= quoted
                or not isinstance(gpu, dict) or gpu.get("id") != HARDWARE["main"][0]
                or type(gpu.get("count")) is not int or gpu["count"] != 1
                or _number(gpu.get("memory")) < HARDWARE["main"][2]
                or any(pod.get(key) != expected[key] for key in ("cloud", "image", "disk", "mounts", "ports"))):
            raise ValueError("Unknown billing rate, ownership or hardware drift")
        seconds, mono = _number(horizon), _number(self.monotonic())
        if seconds <= 0:
            raise ValueError("Positive monitoring horizon required")
        last_wall = max([self._wall0, _utc(intent["created_utc"])] + [
            _utc(row["data"]["utc"]) for row in self.ledger.read() if "elapsed_seconds" in row["data"]])
        if _utc(self.clock()) < last_wall or mono < self._last_mono:
            raise ValueError("Exposure accounting clock moved backward")
        self._last_mono = mono
        elapsed, rate = self._elapsed(intent), quoted + STORAGE
        spent = elapsed * rate / 3600
        projected = spent + (seconds + RETRIEVAL_SECONDS) * rate / 3600
        self.record("accounting", {"utc": _utc(self.clock()).isoformat(), "elapsed_seconds": str(elapsed),
                                  "compute_upper_bound_usd": str(spent), "projected_usd": str(projected),
                                  "cumulative_projected_usd": str(PRIOR_TOTAL + projected)})
        if (elapsed + seconds >= HARD_SECONDS - RETRIEVAL_SECONDS
                or projected > self.budget["exposure_max_usd"]
                or PRIOR_TOTAL + projected > self.budget["total_usd"]):
            raise ValueError("Exposure budget/retrieval reserve/deadline reached")
        return spent

    @serialized
    def start_worker(self):
        if not self.api.writable or any(self.event(n) for n in ("worker-intent", "closing", "delete-intent", "closed")):
            raise ValueError("Worker disabled, already attempted or lifecycle ended")
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
                raise ValueError("Owned exposure pod failed startup")
            self.sleep(15)
        else:
            raise TimeoutError("SSH startup exceeded bounded readiness window")
        token = os.environ.get("HF_TOKEN", "")
        if not token or any(c.isspace() for c in token):
            raise ValueError("HF_TOKEN missing/malformed; worker not started")
        self.ledger.bind("credential-intent", {"path": HF_ENV})
        self._ssh(pod, "set -euC; umask 077; mkdir -p " + REMOTE + "/out; cat > " + HF_ENV
                  + "; chmod 600 " + HF_ENV + '; test "$(stat -c %a ' + HF_ENV + ')" = 600',
                  data=("export HF_TOKEN=" + shlex.quote(token) + "\n").encode())
        self.cost_check(pod, 60)
        script = worker_script(self.kind, self.relative, self.freeze, intent["deadline_utc"],
                               hourly_usd=_number(intent["quote"]["hourly_rate_usd"]) + STORAGE,
                               pod_started_utc=intent["created_utc"])
        seconds = int(Decimal(HARD_SECONDS - RETRIEVAL_SECONDS) - self._elapsed(intent))
        if seconds <= 30:
            raise ValueError("No remaining worker window")
        binding = {"worker_id": uuid.uuid4().hex, "pod_id": pod["id"],
                   "plan_sha256": self.plan_hash, "freeze_commit": self.freeze}
        self.ledger.transact("worker-intent", lambda _: {"script_sha256": hashlib.sha256(script.encode()).hexdigest(),
                             "seconds": seconds, "plan_sha256": self.plan_hash, "freeze_commit": self.freeze,
                             "worker_id": binding["worker_id"], "pod_id": binding["pod_id"],
                             "deadline_utc": intent["deadline_utc"], "hard_deadline_utc": intent["hard_deadline_utc"]})
        command = dispatch_command(script, seconds, binding)
        self._ssh(pod, command)
        self.ledger.transact("worker-started", lambda _: {"utc": _utc(self.clock()).isoformat()})

    @serialized
    def signal_worker(self, pod, action):
        if not self.api.writable or action not in {"pause", "resume", "stop"}:
            raise ValueError("Explicit owned worker lifecycle action required")
        owned, event = self.owned(), self.event("worker-intent")
        if event is None or any(pod.get(k) != owned[k] for k in ("id", "name", "createdAt")):
            raise ValueError("No owned worker dispatch intent")
        intent = event["data"]
        binding = {key: intent.get(key) for key in ("worker_id", "pod_id", "plan_sha256", "freeze_commit")}
        if (not isinstance(binding["worker_id"], str)
                or not re.fullmatch(r"[0-9a-f]{32}", binding["worker_id"])
                or binding["pod_id"] != owned["id"] or binding["plan_sha256"] != self.plan_hash
                or binding["freeze_commit"] != self.freeze):
            raise ValueError("Worker dispatch identity is not bound to this owned pod and plan")
        result = strict_json(self._ssh(pod, "python3 -c " + shlex.quote(WORKER_SIGNAL_SCRIPT),
                            data=json.dumps({"remote": REMOTE, "binding": binding, "action": action}).encode()))
        if (result.get("verified") is not True or result.get("action") != action
                or result.get("binding") != binding or (action == "stop" and not all(
                    result.get(k) is True for k in ("stopped", "dispatch_fenced", "no_matching_worker")))):
            raise ValueError("Owned worker signal/reconciliation unverified")
        return result

    def status(self):
        pod = self.get_pod()
        files = {}
        if pod.get("status") == "RUNNING" and pod.get("ssh", {}).get("direct"):
            files = strict_json(self._ssh(pod, "python3 -c " + shlex.quote(STATUS_SCRIPT)))
        return {"pod": frozen.clean_pod(pod), "files": files}

    @serialized
    def approve(self, name, plan_hash):
        if (not self.api.writable or name not in BARRIERS or plan_hash != self.plan_hash
                or not self.event("worker-started")
                or any(self.event(n) for n in ("closing", "delete-intent", "closed"))):
            raise ValueError("Explicit live barrier approval bound to this plan required")
        state = self.status()
        self.cost_check(state["pod"])
        filename = "WAITING-" + name + ".json"
        barrier = state["files"].get(filename, {})
        if (barrier.get("plan_sha256") != self.plan_hash or barrier.get("freeze_commit") != self.freeze
                or barrier.get("barrier") != name or type(barrier.get("rows")) is not int
                or barrier["rows"] != BARRIER_ROWS[name]
                or any(n in state["files"] for n in frozen.TERMINAL)):
            raise ValueError("Matching exposure barrier is not live")
        if name == "first-five" and (not self.event("approved:qualification")
                or state["files"].get("_approvals", {}).get("APPROVE-qualification") != plan_hash):
            raise ValueError("Qualification must be explicitly approved before first-five")
        receipt = next((row for row in reversed(self.ledger.read())
                        if row["id"].startswith("retrieval:")
                        and filename in row["data"].get("artifacts", {})), None)
        if receipt is None:
            raise ValueError("Retrieve a coherent barrier snapshot before approval")
        data = receipt["data"]
        for path, digest in data["artifacts"].items():
            local = Path(data["directory"]) / path
            if local.is_symlink() or not local.is_file() or sha(local) != digest:
                raise ValueError("Barrier snapshot missing or corrupt")
        if strict_json((Path(data["directory"]) / filename).read_bytes()) != barrier:
            raise ValueError("Live barrier differs from retrieved snapshot")
        script = ("import os,pathlib,sys; p=pathlib.Path(" + repr(REMOTE + "/out/APPROVE-" + name)
                  + "); h=sys.stdin.read(); assert not p.is_symlink(); "
                  + "assert not p.exists() or p.read_text()==h; "
                  + "f=p.open('x') if not p.exists() else None; "
                  + "f.write(h) if f else None; f.flush() if f else None; "
                  + "os.fsync(f.fileno()) if f else None; f.close() if f else None")
        self.ledger.bind("approval-intent:" + name, {"plan_sha256": plan_hash, "barrier": barrier,
                         "retrieval_sha256": receipt["sha256"]})
        self._ssh(state["pod"], "umask 077; python3 -c " + shlex.quote(script), data=(plan_hash + "\n").encode())
        return self.ledger.bind("approved:" + name, {"plan_sha256": plan_hash})

    def approve_first_five(self, plan_hash):
        return self.approve("first-five", plan_hash)

    def _confirm_closed(self, pod):
        if any(pod.get(k) != self.owned()[k] for k in ("id", "name", "createdAt")):
            raise ValueError("Unowned deletion receipt")
        try:
            self.api.request("GET", "/pods/" + pod["id"])
        except ApiError as exc:
            if exc.status != 404:
                raise
        else:
            raise ValueError("Deletion not verified")
        inventory = self.api.inventory()
        if pod["id"] in {item["id"] for item in inventory}:
            raise ValueError("Deleted pod still in inventory")
        intent = self.event("create-intent")["data"]
        elapsed = self._elapsed(intent)
        try:
            rate = max(_number(pod.get("cost")), _number(intent["quote"]["hourly_rate_usd"])) + STORAGE
            cost = elapsed * rate / 3600
        except ValueError:
            cost = None
        return self.ledger.transact("closed", lambda _: {
            "pod_id": pod["id"], "get_status": 404, "inventory_ids": sorted(p["id"] for p in inventory),
            "utc": _utc(self.clock()).isoformat(), "elapsed_seconds": str(elapsed),
            "compute_upper_bound_usd": None if cost is None else str(cost),
            "cumulative_upper_bound_usd": None if cost is None else str(PRIOR_TOTAL + cost),
            "within_limits": (cost is not None and elapsed <= HARD_SECONDS
                              and cost <= self.budget["exposure_max_usd"]
                              and PRIOR_TOTAL + cost <= self.budget["total_usd"])})

    def monitor(self):
        if not self.api.writable:
            raise ValueError("Lifecycle monitor requires explicit --launch")
        if any(self.event(n) for n in ("closing", "delete-intent", "closed")):
            return self.close_until_verified()
        self.owned()
        previous, announced = None, None
        changed_at, last_pull = self.monotonic(), float("-inf")
        failures = 0
        while True:
            try:
                self.cost_check(self.owned(), 60)
            except ValueError:
                return self.close_until_verified()
            try:
                state = self.status()
                self.record("health", state)
                self.cost_check(state["pod"], 60)
                files = state["files"]
                if any(name in files for name in frozen.TERMINAL):
                    return self.close_until_verified()
                progress = files.get("_progress", {})
                waiting = tuple(name for name in BARRIERS if "WAITING-" + name + ".json" in files
                                and files.get("_approvals", {}).get("APPROVE-" + name) != self.plan_hash)
                if progress != previous:
                    previous, changed_at = progress, self.monotonic()
                limit = 900 if any(name.startswith("rows/") for name in progress) else 1800
                if not waiting and self.monotonic() - changed_at >= limit:
                    return self.close_until_verified()
                if waiting != announced or self.monotonic() - last_pull >= 600:
                    self.retrieve()
                    last_pull = self.monotonic()
                    if waiting and waiting != announced:
                        print("WAITING: audit " + ", ".join(waiting)
                              + " snapshot; explicit plan-hash approval required.", flush=True)
                    announced = waiting
                failures = 0
            except ValueError as exc:
                self.record("monitor-failed", {"error_type": type(exc).__name__})
                return self.close_until_verified()
            except (RuntimeError, OSError, subprocess.TimeoutExpired) as exc:
                failures += 1
                self.record("monitor-retry", {"error_type": type(exc).__name__, "consecutive_failures": failures})
                if failures >= 3:
                    return self.close_until_verified()
            self.sleep(60)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for flag in ("plan", "freeze", "out"):
        parser.add_argument("--" + flag, required=True)
    parser.add_argument("--kind", choices=("main",), default="main")
    parser.add_argument("--action", choices=("preflight", "quote", "launch", "status", "monitor",
                                             "approve", "retrieve", "terminate", "reconcile"), default="preflight")
    parser.add_argument("--launch", action="store_true", help="Enable the explicitly selected lifecycle operation")
    parser.add_argument("--barrier", choices=BARRIERS)
    parser.add_argument("--approve-plan-sha256")
    args = parser.parse_args(argv)
    if (args.barrier or args.approve_plan_sha256) and args.action != "approve":
        parser.error("Approval arguments are only valid with --action approve")
    if args.action in {"launch", "monitor", "approve", "retrieve", "terminate"} and not args.launch:
        parser.error("Lifecycle mutation requires --launch")
    if args.action == "approve" and not (args.barrier and args.approve_plan_sha256):
        parser.error("--barrier and --approve-plan-sha256 required")
    if args.action in {"preflight", "quote"}:
        result = preflight(args.plan, args.freeze)
        if args.action == "quote":
            result["quote"] = quote(RunPodV2(os.environ.get("RUNPOD_API_KEY"), writable=False))
            result["network_calls"] = 1
        print(json.dumps(result, sort_keys=True))
        return
    api = RunPodV2(os.environ.get("RUNPOD_API_KEY"), writable=args.launch)
    controller = Controller(args.plan, args.freeze, args.out, args.kind, api)
    if args.action == "launch":
        controller.launch()
        result = controller.monitor()
    elif args.action == "approve":
        result = controller.approve(args.barrier, args.approve_plan_sha256)
    elif args.action == "terminate":
        result = controller.close_until_verified()
    else:
        result = getattr(controller, args.action)()
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()

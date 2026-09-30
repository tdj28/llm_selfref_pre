"""Single-pod SAE-only replay lifecycle; default preflight is offline/read-only.

Protocol contract: load_plan(path, freeze) validates the pinned source and inputs.
The runner emits WAITING-first-five.json with barrier='first-five', rows=5,
plan_sha256 and freeze_commit (the existing diagnostic Run.barrier schema),
then waits for APPROVE-first-five containing that hash. No automatic approval.
Run --action launch --launch under supervision: it monitors through verified
retrieval/deletion. A remote timeout stops work, not billing. Unreachable provider
or corrupt/unretrievable evidence can prevent timely deletion; cleanup keeps
retrying and reports overruns rather than discarding evidence or claiming a cap.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import timedelta
from decimal import Decimal
import fcntl
from functools import wraps
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shlex
import stat
import subprocess
import time
import urllib.parse
import uuid

from experiments.sae_assay_diagnostic import controller as frozen
from experiments.sae_assay_diagnostic.budget import EventLedger, PodRegistry, _number, _utc

ROOT = Path(__file__).resolve().parents[2]
PREFIX = "codex-sae-replay-20260930-"
NAMESPACE = "replay-controller"
PRIOR_TOTAL = Decimal("27.3845359753")
MAX_NEW = Decimal("4")
HARD_SECONDS, RETRIEVAL_SECONDS = 7200, 600
HARDWARE = {"cheap": ("NVIDIA RTX A6000", Decimal("0.53"), 48)}
PLAN_HARDWARE = {"gpu": "NVIDIA RTX A6000", "count": 1, "memory_gb": 48,
                 "hourly_price_ceiling_usd": .53, "hard_seconds": HARD_SECONDS}
IMAGE, STORAGE = frozen.IMAGE, frozen.STORAGE
RunPodV2, ApiError = frozen.RunPodV2, frozen.ApiError
sha, strict_json, verify_public = frozen.sha, frozen.strict_json, frozen.verify_public
WAITING = ("WAITING-first-five.json",)
HF_ENV = "/root/sae-replay-hf.env"
STATUS_SCRIPT = """import json,pathlib
r=pathlib.Path(%r); d={}
for n in %r:
 p=r/n
 if p.is_file(): d[n]=json.loads(p.read_text())
d['_progress']={p.relative_to(r).as_posix():[p.stat().st_size,p.stat().st_mtime_ns]
 for p in r.rglob('*') if p.is_file() and not p.is_symlink()}
d['_approvals']={p.name:p.read_text().strip() for p in r.glob('APPROVE-*') if p.is_file()}
print(json.dumps(d))
""" % (frozen.REMOTE + "/out", list(WAITING + frozen.TERMINAL))


def serialized(method):
    @wraps(method)
    def call(self, *args, **kwargs):
        with self._exclusive():
            return method(self, *args, **kwargs)
    return call


def load_plan(path, freeze):
    from experiments.sae_assay_replay.protocol import load_plan as replay_load_plan
    return replay_load_plan(path, freeze)


def checked_budget(plan):
    if plan.get("hardware") != PLAN_HARDWARE:
        raise ValueError("Replay plan must pin the single A6000 hardware/timer contract")
    budget = plan.get("budget", {})
    if set(budget) != {"prior_total_usd", "total_usd", "replay_max_usd",
                       "new_paid_judge_calls", "new_pro_calls"}:
        raise ValueError("Complete replay-only budget required")
    amounts = {key: _number(value) for key, value in budget.items()}
    if (amounts["prior_total_usd"] != PRIOR_TOTAL or not 0 < amounts["replay_max_usd"] <= MAX_NEW
            or not PRIOR_TOTAL + amounts["replay_max_usd"] <= amounts["total_usd"] <= 200
            or amounts["new_paid_judge_calls"] != 0 or amounts["new_pro_calls"] != 0):
        raise ValueError("Replay budget exceeds or resets the existing authorization")
    return amounts


def quote(api, kind="cheap"):
    if kind != "cheap":
        raise ValueError("Only a single RTX A6000 replay pod is authorized")
    gpu, ceiling, memory = HARDWARE[kind]
    _, item = api.request("GET", "/catalog/gpus/" + urllib.parse.quote(gpu, safe="")
                         + "?include=AVAILABILITY&product=POD&cloud=SECURE&count=1&minCudaVersion=12.8")
    rate = _number(item["price"]["secure"])
    if (item["id"] != gpu or item["secure"] is not True or _number(item["memory"]) < memory
            or item.get("availability") not in {"LOW", "MEDIUM", "HIGH"} or not 0 < rate <= ceiling):
        raise ValueError("Unknown/unavailable A6000 or quote exceeds authorization; no fallback")
    return {"hourly_rate_usd": str(rate), "storage_hourly_usd": str(STORAGE)}


def create_payload(kind, name, public_key):
    if kind != "cheap" or not re.fullmatch(re.escape(PREFIX) + r"cheap-[0-9a-f]{12}", name):
        raise ValueError("Unique replay-owned RTX A6000 name required")
    payload = frozen.create_payload(kind, frozen.PREFIX + "cheap-" + name[-12:], public_key)
    return {**payload, "name": name,
            "gpu": {"id": HARDWARE[kind][0], "count": 1, "minCudaVersion": "12.8"}}


def worker_script(kind, plan_relative, freeze, deadline):
    path = PurePosixPath(plan_relative)
    if (kind != "cheap" or not re.fullmatch(r"[0-9a-f]{40}", freeze)
            or path.is_absolute() or ".." in path.parts or path.as_posix() != plan_relative
            or not path.parts or plan_relative.startswith("-") or any(ord(c) < 32 for c in plan_relative)):
        raise ValueError("Unsafe replay source path, freeze or kind")
    _utc(deadline)
    remote, python = frozen.REMOTE, frozen.REMOTE + "/venv/bin/python"
    validation = ("from experiments.sae_assay_replay.protocol import load_plan; "
                  + "load_plan(" + repr(plan_relative) + ", " + repr(freeze) + ")")
    exit_code = ("import json,sys; json.dump({'exit_code':int(sys.argv[1])},open("
                 + repr(remote + "/out/controller-exit.json") + ",'x'))")
    command = [python, "-u", "-m", "experiments.sae_assay_replay.runner", "--plan", plan_relative,
               "--freeze", freeze, "--out", remote + "/out", "--cache", "/workspace/cache",
               "--deadline-utc", deadline]
    return "\n".join([
        "set -euC", "umask 077", "mkdir -p " + remote + "/out",
        "trap 'rc=$?; rm -f " + HF_ENV + "; python3 -c "
        + shlex.quote(exit_code).replace("'", "'\"'\"'") + " \"$rc\"' EXIT",
        "git -c credential.helper= clone --filter=blob:none --no-checkout " + frozen.REPO + " " + remote + "/repo",
        "cd " + remote + "/repo", "git fetch --depth=1 origin " + freeze,
        "git checkout --detach " + freeze, 'test "$(git rev-parse HEAD)" = ' + freeze,
        "python3 -m venv --system-site-packages " + remote + "/venv",
        python + " -m pip install -r experiments/sae_assay_diagnostic/requirements-gpu.txt",
        python + " -m pip freeze --all > " + remote + "/out/pip-freeze.txt",
        shlex.join([python, "-c", validation]),
        "set +x; . " + HF_ENV + "; rm -f " + HF_ENV,
        "export HF_HOME=/workspace/cache PYTHONUNBUFFERED=1",
        shlex.join(command),
    ])


def preflight(plan_path, freeze):
    path = Path(plan_path).resolve()
    relative = path.relative_to(ROOT).as_posix()
    budget = checked_budget(load_plan(path, freeze))
    worker_script("cheap", relative, freeze, frozen.now().isoformat())
    return {"preflight": True, "network_calls": 0, "namespace": NAMESPACE,
            "plan_sha256": sha(path), "freeze_commit": freeze,
            "gpu": HARDWARE["cheap"][0], "image": IMAGE,
            "hard_seconds": HARD_SECONDS, "retrieval_seconds": RETRIEVAL_SECONDS,
            "maximum_timer_cost_usd": str((HARDWARE["cheap"][1] + STORAGE) * HARD_SECONDS / 3600),
            "new_cap_usd": str(budget["replay_max_usd"]),
            "cumulative_ceiling_usd": str(PRIOR_TOTAL + budget["replay_max_usd"])}


class Controller(frozen.Controller):
    """Reuse frozen SSH, snapshots and ownership ledger, never frozen dispatch/budget."""

    def __init__(self, plan_path, freeze, out, kind, api, *, run=subprocess.run,
                 clock=frozen.now, sleep=time.sleep, monotonic=time.monotonic):
        if kind != "cheap" or not re.fullmatch(r"[0-9a-f]{40}", freeze):
            raise ValueError("Replay requires cheap hardware and an exact freeze")
        self.plan_path, self.freeze, self.kind = Path(plan_path).resolve(), freeze, kind
        self.plan = load_plan(self.plan_path, freeze)
        self.budget = checked_budget(self.plan)
        self.plan_hash, self.relative = sha(self.plan_path), self.plan_path.relative_to(ROOT).as_posix()
        self.out = Path(out).resolve()
        self.base = self.out / NAMESPACE / kind
        for directory in (self.base.parent, self.base):
            if directory.is_symlink():
                raise ValueError("Private replay namespace cannot be a symlink")
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

    @contextmanager
    def _exclusive(self):
        # A monitor snapshot must not resume a worker during concurrent teardown.
        if getattr(self, "_mutation_depth", 0):
            yield
            return
        fd = os.open(self.base / "lifecycle.lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        try:
            if not stat.S_ISREG(os.fstat(fd).st_mode):
                raise ValueError("Lifecycle lock must be a regular file")
            fcntl.flock(fd, fcntl.LOCK_EX)
            self._mutation_depth = 1
            yield
        finally:
            self._mutation_depth = 0
            os.close(fd)

    def record(self, prefix, payload):
        return self.ledger.transact(prefix + ":" + uuid.uuid4().hex, lambda _: payload)

    def _new_pod(self, pod, intent):
        name = intent["payload"].get("name", "")
        return (re.fullmatch(re.escape(PREFIX) + r"cheap-[0-9a-f]{12}", name) is not None
                and intent.get("plan_sha256") == self.plan_hash
                and intent.get("freeze_commit") == self.freeze
                and super()._new_pod(pod, intent))

    def owned(self):
        pod = super().owned()
        intent = self.event("create-intent")
        if intent is None or not self._new_pod(pod, intent["data"]):
            raise ValueError("Pod is not owned by this replay creation intent")
        return pod

    def _ssh(self, pod, command, *, data=None, timeout=60):
        owned = self.owned()
        if any(pod.get(key) != owned[key] for key in ("id", "name", "createdAt")):
            raise ValueError("SSH is restricted to the newly owned replay pod")
        return super()._ssh(pod, command, data=data, timeout=timeout)

    def _register(self, pod):
        intent = self.event("create-intent")["data"]
        if not self._new_pod(pod, intent):
            raise ValueError("Registration requires a fresh replay-owned pod")
        receipt = self.ledger.bind("created", frozen.clean_pod(pod))
        registry = PodRegistry(self.ledger, intent["blocked"])
        if not self.event("pod:created:" + pod["id"]):
            registry.register_created(pod["id"], receipt["sha256"], [str(self.base / "final-retrieval.json")])

    @serialized
    def launch(self):
        if not self.api.writable:
            raise ValueError("Explicit --launch required")
        if self.event("create-intent"):
            raise ValueError("Create already attempted; never retry an uncertain creation")
        if load_plan(self.plan_path, self.freeze) != self.plan or sha(self.plan_path) != self.plan_hash:
            raise ValueError("Replay plan changed since controller construction")
        self.disk_check()
        token = os.environ.get("HF_TOKEN", "")
        if not token or any(c.isspace() for c in token):
            raise ValueError("HF_TOKEN missing/malformed before creation")
        if not frozen.KEY.expanduser().is_file():
            raise ValueError("Existing private SSH key missing")
        key = Path(str(frozen.KEY.expanduser()) + ".pub").read_text().strip()
        payload = create_payload(self.kind, PREFIX + "cheap-" + uuid.uuid4().hex[:12], key)
        verify_public(self.plan_hash, self.relative, self.freeze)
        blocked = sorted({frozen.BLOCKED} | {p["id"] for p in self.api.inventory()})
        PodRegistry(self.ledger, blocked)
        quoted = quote(self.api)
        created = _utc(self.clock())
        rate = _number(quoted["hourly_rate_usd"]) + _number(quoted["storage_hourly_usd"])
        cap = self.budget["replay_max_usd"]
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

    def _elapsed(self, intent):
        created = _utc(intent["created_utc"])
        previous = max((_number(row["data"]["elapsed_seconds"]) for row in self.ledger.read()
                        if "elapsed_seconds" in row["data"]), default=Decimal(0))
        return max(Decimal(0), Decimal(str((_utc(self.clock()) - created).total_seconds())),
                   max(self._elapsed0, Decimal(str((self._wall0 - created).total_seconds())))
                   + _number(self.monotonic()) - self._mono0, previous)

    def cost_check(self, pod, horizon=60):
        intent, owned = self.event("create-intent")["data"], self.owned()
        expected, quoted = intent["payload"], _number(intent["quote"]["hourly_rate_usd"])
        gpu = pod.get("gpu")
        if (any(pod.get(key) != owned[key] for key in ("id", "name", "createdAt"))
                or not 0 < _number(pod.get("cost")) <= quoted
                or not isinstance(gpu, dict) or gpu.get("id") != HARDWARE["cheap"][0]
                or type(gpu.get("count")) is not int or gpu["count"] != 1
                or _number(gpu.get("memory")) < HARDWARE["cheap"][2]
                or any(pod.get(key) != expected[key] for key in ("cloud", "image", "disk", "mounts", "ports"))):
            raise ValueError("Unknown billing rate, ownership or hardware drift")
        seconds, mono = _number(horizon), _number(self.monotonic())
        if seconds <= 0:
            raise ValueError("Positive monitoring horizon required")
        last_wall = max([self._wall0, _utc(intent["created_utc"])] + [
            _utc(row["data"]["utc"]) for row in self.ledger.read() if "elapsed_seconds" in row["data"]])
        if _utc(self.clock()) < last_wall or mono < self._last_mono:
            raise ValueError("Replay accounting clock moved backward")
        self._last_mono = mono
        elapsed, rate = self._elapsed(intent), quoted + STORAGE
        spent = elapsed * rate / 3600
        projected = spent + (seconds + RETRIEVAL_SECONDS) * rate / 3600
        self.record("accounting", {"utc": _utc(self.clock()).isoformat(), "elapsed_seconds": str(elapsed),
                                  "compute_upper_bound_usd": str(spent), "projected_usd": str(projected),
                                  "cumulative_projected_usd": str(PRIOR_TOTAL + projected)})
        if (elapsed + seconds >= HARD_SECONDS - RETRIEVAL_SECONDS
                or projected > self.budget["replay_max_usd"]
                or PRIOR_TOTAL + projected > self.budget["total_usd"]):
            raise ValueError("Replay budget/retrieval reserve/deadline reached")
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
                raise ValueError("Owned replay pod failed startup")
            self.sleep(15)
        else:
            raise TimeoutError("SSH startup exceeded bounded readiness window")
        token = os.environ.get("HF_TOKEN", "")
        if not token or any(c.isspace() for c in token):
            raise ValueError("HF_TOKEN missing/malformed; worker not started")
        self.ledger.bind("credential-intent", {"path": HF_ENV})
        self._ssh(pod, "set -euC; umask 077; mkdir -p " + frozen.REMOTE + "/out; cat > " + HF_ENV
                  + "; chmod 600 " + HF_ENV + '; test "$(stat -c %a ' + HF_ENV + ')" = 600',
                  data=("export HF_TOKEN=" + shlex.quote(token) + "\n").encode())
        self.cost_check(pod, 60)
        script = worker_script(self.kind, self.relative, self.freeze, intent["deadline_utc"])
        seconds = int(Decimal(HARD_SECONDS - RETRIEVAL_SECONDS) - self._elapsed(intent))
        if seconds <= 30:
            raise ValueError("No remaining worker window")
        self.ledger.transact("worker-intent", lambda _: {"script_sha256": hashlib.sha256(script.encode()).hexdigest(),
                             "seconds": seconds, "plan_sha256": self.plan_hash, "freeze_commit": self.freeze,
                             "deadline_utc": intent["deadline_utc"], "hard_deadline_utc": intent["hard_deadline_utc"]})
        command = ("nohup setsid timeout --signal=TERM --kill-after=30s " + str(seconds - 30)
                   + "s env -i HOME=/root"
                   + " PATH=/usr/local/cuda/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
                   + " LD_LIBRARY_PATH=/usr/local/cuda/lib64 bash --noprofile --norc -c "
                   + shlex.quote(script) + " >" + frozen.REMOTE
                   + "/out/controller.log 2>&1 </dev/null & echo $! > " + frozen.REMOTE + "/worker.pid")
        self._ssh(pod, command)
        self.ledger.transact("worker-started", lambda _: {"utc": _utc(self.clock()).isoformat()})

    def status(self):
        pod = self.get_pod()
        files = {}
        if pod.get("status") == "RUNNING" and pod.get("ssh", {}).get("direct"):
            files = strict_json(self._ssh(pod, "python3 -c " + shlex.quote(STATUS_SCRIPT)))
        return {"pod": frozen.clean_pod(pod), "files": files}

    @serialized
    def approve_first_five(self, plan_hash):
        if (not self.api.writable or plan_hash != self.plan_hash
                or not self.event("worker-started")
                or any(self.event(n) for n in ("closing", "delete-intent", "closed"))):
            raise ValueError("Explicit live first-five approval bound to this plan required")
        state = self.status()
        self.cost_check(state["pod"])
        barrier = state["files"].get(WAITING[0], {})
        if (barrier.get("plan_sha256") != self.plan_hash or barrier.get("freeze_commit") != self.freeze
                or barrier.get("barrier") != "first-five"
                or type(barrier.get("rows")) is not int or barrier["rows"] != 5
                or any(n in state["files"] for n in frozen.TERMINAL)):
            raise ValueError("Matching five-source-state barrier is not live")
        script = ("import os,pathlib,sys; p=pathlib.Path(" + repr(frozen.REMOTE + "/out/APPROVE-first-five")
                  + "); h=sys.stdin.read(); "
                  + "assert not p.is_symlink(); "
                  + "assert not p.exists() or p.read_text()==h; "
                  + "f=p.open('x') if not p.exists() else None; "
                  + "f.write(h) if f else None; f.flush() if f else None; "
                  + "os.fsync(f.fileno()) if f else None; f.close() if f else None")
        self.ledger.bind("approval-intent:first-five", {"plan_sha256": plan_hash, "barrier": barrier})
        self._ssh(state["pod"], "umask 077; python3 -c " + shlex.quote(script), data=(plan_hash + "\n").encode())
        return self.ledger.bind("approved:first-five", {"plan_sha256": plan_hash})

    @serialized
    def retrieve(self, *, final=False):
        if not self.api.writable:
            raise ValueError("Explicit --launch required for snapshot pause/stop")
        if any(self.event(n) for n in ("delete-intent", "closed")) or (self.event("closing") and not final):
            raise ValueError("No live snapshot after lifecycle closing")
        return super().retrieve(final=final)

    @serialized
    def terminate(self):
        if not self.api.writable:
            raise ValueError("Explicit --launch required for termination")
        if self.event("closed"):
            return self.event("closed")
        self.owned()
        if self.event("delete-intent"):
            return self._confirm_closed(self.event("delete-intent")["data"]["pod"])
        pod = self.get_pod()
        self.ledger.bind("closing", {"pod_id": pod["id"]})
        if not (self.base / "final-retrieval.json").exists():
            self.retrieve(final=True)
        self._verify_final()
        if self.event("credential-intent"):
            self._ssh(pod, "rm -f " + HF_ENV + "; test ! -e " + HF_ENV)
            self.ledger.bind("credential-removed", {"path": HF_ENV, "absent": True})
        manifest = self.base / "final-retrieval.json"
        registry = PodRegistry(self.ledger, self.event("create-intent")["data"]["blocked"])
        permit = registry.authorize_delete(pod["id"], {str(manifest): sha(manifest)})
        self.ledger.transact("delete-intent", lambda _: {"permit_sha256": permit["sha256"],
                             "pod_id": pod["id"], "pod": frozen.clean_pod(pod)})
        status, _ = self.api.request("DELETE", "/pods/" + pod["id"])
        self.ledger.bind("delete-response", {"status": status, "pod_id": pod["id"]})
        if status != 204:
            raise ValueError("Unexpected delete response; reconcile without another DELETE")
        return self._confirm_closed(pod)

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
                              and cost <= self.budget["replay_max_usd"]
                              and PRIOR_TOTAL + cost <= self.budget["total_usd"])})

    def close_until_verified(self):
        if not self.api.writable:
            raise ValueError("Explicit --launch required for cleanup")
        self.owned()
        while True:
            try:
                return self.terminate()
            except (RuntimeError, ValueError, OSError, subprocess.TimeoutExpired) as exc:
                elapsed = self._elapsed(self.event("create-intent")["data"])
                self.record("cleanup-retry", {"error_type": type(exc).__name__,
                            "utc": _utc(self.clock()).isoformat(), "elapsed_seconds": str(elapsed),
                            "hard_deadline_exceeded": elapsed >= HARD_SECONDS})
                print("ATTENTION: cleanup unresolved; evidence retained; no repeated DELETE."
                      + (" Hard deadline exceeded; user action required." if elapsed >= HARD_SECONDS else ""), flush=True)
                self.sleep(15)

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
                waiting = WAITING[0] in files and files.get("_approvals", {}).get("APPROVE-first-five") != self.plan_hash
                if progress != previous:
                    previous, changed_at = progress, self.monotonic()
                limit = 900 if any(name.startswith("rows/") for name in progress) else 1800
                if not waiting and self.monotonic() - changed_at >= limit:
                    return self.close_until_verified()
                if waiting != announced or self.monotonic() - last_pull >= 600:
                    self.retrieve()
                    last_pull = self.monotonic()
                    if waiting and waiting != announced:
                        print("WAITING: audit first-five snapshot; explicit plan-hash approval required.", flush=True)
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
    parser.add_argument("--kind", choices=("cheap",), default="cheap")
    parser.add_argument("--action", choices=("preflight", "quote", "launch", "status", "monitor",
                                             "approve", "retrieve", "terminate", "reconcile"), default="preflight")
    parser.add_argument("--launch", action="store_true", help="Enable only the explicitly selected lifecycle operation")
    parser.add_argument("--approve-first-five", metavar="PLAN_SHA256")
    args = parser.parse_args(argv)
    if args.approve_first_five is not None and args.action != "approve":
        parser.error("--approve-first-five is only valid with --action approve")
    if args.action in {"launch", "monitor", "approve", "retrieve", "terminate"} and not args.launch:
        parser.error("Lifecycle mutation requires --launch")
    if args.action == "approve" and not args.approve_first_five:
        parser.error("--approve-first-five PLAN_SHA256 required")
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
        result = controller.approve_first_five(args.approve_first_five)
    elif args.action == "terminate":
        result = controller.close_until_verified()
    else:
        result = getattr(controller, args.action)()
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()

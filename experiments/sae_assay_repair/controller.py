"""Bounded repair lifecycle; default CLI is local/unpaid and never approves gates.

Only freshly created repair pods are accessible. Keep the local monitor running:
the remote worker timeout stops computation, but cannot delete a billed pod.
Retrieval failures retain the pod and evidence instead of bypassing hash checks.
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
import uuid

from experiments.sae_assay_diagnostic import controller as frozen
from experiments.sae_assay_diagnostic.budget import EventLedger, PodRegistry, _number, _utc

ROOT = Path(__file__).resolve().parents[2]
PREFIX = "codex-sae-repair-20260930-"
NAMESPACE = "repair-controller"
PRIOR_TOTAL = Decimal("13.07885980328333333333333333")
RETRIEVAL_SECONDS = 600
HARD_SECONDS = {"cheap": 1800, "main": 10800}
HARDWARE, STORAGE, IMAGE = frozen.HARDWARE, frozen.STORAGE, frozen.IMAGE
RunPodV2, ApiError = frozen.RunPodV2, frozen.ApiError
quote, verify_public = frozen.quote, frozen.verify_public
sha, strict_json = frozen.sha, frozen.strict_json
WAITING = (*frozen.WAITING, "WAITING-repair-nonzero.json")
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


def load_plan(path, freeze):
    # Lazy import keeps dry-run usable before the separately owned plan exists.
    from experiments.sae_assay_repair.protocol import load_plan as repair_load_plan
    return repair_load_plan(path, freeze)


def checked_budget(plan):
    budget = plan.get("budget", {})
    ceilings = {"total_usd": 200, "repair_max_usd": 40, "cheap_max_usd": 2, "main_max_usd": 38}
    no_calls = {"new_paid_judge_calls", "new_pro_calls"}
    required = {"prior_total_usd", *ceilings}
    if not required <= set(budget) or set(budget) - required - no_calls:
        raise ValueError("Complete repair budget, including all prior Pro/API/GPU costs, required")
    amounts = {key: _number(value) for key, value in budget.items()}
    if any(amounts[key] != 0 for key in no_calls & amounts.keys()):
        raise ValueError("No new paid judge or Pro calls authorized")
    if any(not 0 < amounts[key] <= ceiling for key, ceiling in ceilings.items()):
        raise ValueError("Repair budget exceeds authorization")
    if (amounts["prior_total_usd"] < PRIOR_TOTAL
            or amounts["cheap_max_usd"] + amounts["main_max_usd"] > amounts["repair_max_usd"]
            or amounts["prior_total_usd"] + amounts["repair_max_usd"] > min(amounts["total_usd"], Decimal("53.08"))):
        raise ValueError("Cumulative prior plus repair budget is not bounded")
    return amounts


def create_payload(kind, name, public_key):
    if kind not in HARDWARE or not re.fullmatch(re.escape(PREFIX) + kind + r"-[0-9a-f]{12}", name):
        raise ValueError("Unique repair-owned pod name required")
    payload = frozen.create_payload(kind, frozen.PREFIX + kind + "-" + name[-12:], public_key)
    return {**payload, "name": name}


def worker_script(kind, plan_relative, freeze, deadline):
    path = PurePosixPath(plan_relative)
    if (kind not in HARDWARE or not re.fullmatch(r"[0-9a-f]{40}", freeze)
            or path.is_absolute() or ".." in path.parts or path.as_posix() != plan_relative
            or not path.parts):
        raise ValueError("Unsafe repair source path or kind")
    _utc(deadline)
    remote = frozen.REMOTE
    python = remote + "/venv/bin/python"
    command = [python, "-m", "experiments.sae_assay_repair.qualify",
               "--out", remote + "/out/cheap-qualification.json"]
    if kind == "main":
        command = [python, "-m", "experiments.sae_assay_repair.runner", "--plan", plan_relative,
                   "--freeze", freeze, "--out", remote + "/out", "--cache", "/workspace/cache",
                   "--deadline-utc", deadline]
    validation = ("from experiments.sae_assay_repair.protocol import load_plan; "
                  + "load_plan(" + repr(plan_relative) + ", " + repr(freeze) + ")")
    exit_code = ("import json,sys; json.dump({'exit_code':int(sys.argv[1])},open("
                 + repr(remote + "/out/controller-exit.json") + ",'x'))")
    return "\n".join([
        "set -euC", "umask 077", "mkdir -p " + remote + "/out",
        "trap 'rc=$?; python3 -c " + shlex.quote(exit_code).replace("'", "'\"'\"'") + " \"$rc\"' EXIT",
        "git -c credential.helper= clone --filter=blob:none --no-checkout " + frozen.REPO + " " + remote + "/repo",
        "cd " + remote + "/repo", "git fetch --depth=1 origin " + freeze,
        "git checkout --detach " + freeze, 'test "$(git rev-parse HEAD)" = ' + freeze,
        "python3 -m venv --system-site-packages " + remote + "/venv",
        python + " -m pip install -r experiments/sae_assay_diagnostic/requirements-gpu.txt",
        python + " -m pip freeze --all > " + remote + "/out/pip-freeze.txt",
        shlex.join([python, "-c", validation]),
        ". " + remote + "/hf.env", shlex.join(command),
    ])


class Controller(frozen.Controller):
    """Reuse frozen ownership/retrieval machinery, never its old budget guard."""

    def __init__(self, plan_path, freeze, out, kind, api, *, run=subprocess.run,
                 clock=frozen.now, sleep=time.sleep, monotonic=time.monotonic):
        if kind not in HARDWARE or not re.fullmatch(r"[0-9a-f]{40}", freeze):
            raise ValueError("Repair kind and exact freeze required")
        self.plan_path, self.freeze, self.kind = Path(plan_path).resolve(), freeze, kind
        self.plan = load_plan(self.plan_path, freeze)
        self.budget = checked_budget(self.plan)
        self.plan_hash = sha(self.plan_path)
        self.relative = self.plan_path.relative_to(ROOT).as_posix()
        self.out = Path(out).resolve()
        self.base = self.out / NAMESPACE / kind
        for directory in (self.base.parent, self.base):
            if directory.is_symlink():
                raise ValueError("Private repair namespace cannot be a symlink")
            directory.mkdir(parents=True, exist_ok=True, mode=0o700)
            directory.chmod(0o700)
        self.api, self.run, self.clock, self.sleep = api, run, clock, sleep
        self.monotonic = monotonic
        self._wall0, self._mono0 = _utc(clock()), _number(monotonic())
        self.guard = None
        self.ledger = EventLedger(self.base / "events.jsonl", self.plan_hash, freeze, [])
        self.ledger.path.chmod(0o600)
        self._elapsed0 = max((_number(row["data"]["elapsed_seconds"]) for row in self.ledger.read()
                             if "elapsed_seconds" in row["data"]), default=Decimal(0))
        self.ledger.bind("controller:config", {"kind": kind, "namespace": NAMESPACE,
                         "plan_path": self.relative, "image": IMAGE, "budget": self.plan["budget"],
                         "hard_seconds": HARD_SECONDS[kind], "retrieval_seconds": RETRIEVAL_SECONDS})

    def owned(self):
        pod = super().owned()
        intent = self.event("create-intent")
        if intent is None or not self._new_pod(pod, intent["data"]):
            raise ValueError("Pod is not owned by this repair creation intent")
        return pod

    def _ssh(self, pod, command, *, data=None, timeout=60):
        owned = self.owned()
        if any(pod.get(key) != owned[key] for key in ("id", "name", "createdAt")):
            raise ValueError("SSH is restricted to the newly owned repair pod")
        return super()._ssh(pod, command, data=data, timeout=timeout)

    def _cheap_cost(self):
        path = self.out / NAMESPACE / "cheap/events.jsonl"
        approval = self.out / "APPROVE-cheap"
        if not path.is_file() or not approval.is_file() or approval.is_symlink():
            raise ValueError("Verified cheap qualification and local APPROVE-cheap required")
        if approval.read_text().strip() != self.plan_hash:
            raise ValueError("Cheap approval must bind the repair plan hash")
        cheap = Controller(self.plan_path, self.freeze, self.out, "cheap", self.api,
                           run=self.run, clock=self.clock, sleep=self.sleep, monotonic=self.monotonic)
        closed = cheap.event("closed")
        if (closed is None or closed["data"].get("get_status") != 404
                or closed["data"].get("pod_id") != cheap.owned()["id"]
                or closed["data"].get("within_limits") is not True):
            raise ValueError("Cheap pod must be retrieved and verifiably deleted within its limits")
        cheap._verify_final()
        receipt = strict_json((cheap.base / "final-retrieval.json").read_bytes())["data"]
        required = {"cheap-qualification.json", "controller-exit.json"}
        if not required <= receipt["artifacts"].keys():
            raise ValueError("Cheap qualification and successful exit evidence required")
        directory = Path(receipt["directory"])
        qualification = strict_json((directory / "cheap-qualification.json").read_bytes())
        exit_status = strict_json((directory / "controller-exit.json").read_bytes())
        if (qualification.get("pass") is not True or type(exit_status.get("exit_code")) is not int
                or exit_status["exit_code"] != 0):
            raise ValueError("Cheap qualification did not pass and exit successfully")
        cost = _number(closed["data"]["compute_upper_bound_usd"])
        if cost > self.budget["cheap_max_usd"]:
            raise ValueError("Cheap qualification exceeded its budget")
        return cost

    def launch(self):
        if not self.api.writable:
            raise ValueError("Explicit --launch required")
        if self.event("create-intent"):
            raise ValueError("Create already attempted; never retry an uncertain creation")
        if load_plan(self.plan_path, self.freeze) != self.plan or sha(self.plan_path) != self.plan_hash:
            raise ValueError("Repair plan changed since controller construction")
        self.disk_check()
        cheap_cost = self._cheap_cost() if self.kind == "main" else Decimal(0)
        token = os.environ.get("HF_TOKEN", "")
        if not token or any(c.isspace() for c in token):
            raise ValueError("HF_TOKEN missing/malformed before creation")
        if not frozen.KEY.expanduser().is_file():
            raise ValueError("Existing private SSH key missing")
        key = Path(str(frozen.KEY.expanduser()) + ".pub").read_text().strip()
        payload = create_payload(self.kind, PREFIX + self.kind + "-" + uuid.uuid4().hex[:12], key)
        verify_public(self.plan_hash, self.relative, self.freeze)
        blocked = sorted({frozen.BLOCKED} | {p["id"] for p in self.api.inventory()})
        PodRegistry(self.ledger, blocked)
        quoted = quote(self.api, self.kind)
        created = _utc(self.clock())
        rate = _number(quoted["hourly_rate_usd"]) + _number(quoted["storage_hourly_usd"])
        cap = self.budget[self.kind + "_max_usd"]
        if rate * HARD_SECONDS[self.kind] / 3600 > cap:
            raise ValueError("Full pod timer including retrieval is not funded")
        deadline = created + timedelta(seconds=HARD_SECONDS[self.kind] - RETRIEVAL_SECONDS)
        intent = {"payload": payload, "quote": quoted, "blocked": blocked,
                  "created_utc": created.isoformat(), "deadline_utc": deadline.isoformat(),
                  "hard_deadline_utc": (deadline + timedelta(seconds=RETRIEVAL_SECONDS)).isoformat(),
                  "prior_total_usd": str(self.budget["prior_total_usd"]),
                  "prior_repair_usd": str(cheap_cost), "local_cap_usd": str(cap),
                  "cumulative_ceiling_usd": str(self.budget["prior_total_usd"] + cheap_cost + cap),
                  "plan_sha256": self.plan_hash, "freeze_commit": self.freeze}
        self.ledger.transact("create-intent", lambda _: intent)
        self._wall0, self._mono0 = created, _number(self.monotonic())
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
            self.terminate()
            raise
        return self.owned()

    def _register(self, pod):
        intent = self.event("create-intent")["data"]
        if not self._new_pod(pod, intent):
            raise ValueError("Registration requires a fresh repair-owned pod")
        receipt = self.ledger.bind("created", frozen.clean_pod(pod))
        registry = PodRegistry(self.ledger, intent["blocked"])
        if not self.event("pod:created:" + pod["id"]):
            registry.register_created(pod["id"], receipt["sha256"], [str(self.base / "final-retrieval.json")])

    def _elapsed(self, intent):
        created = _utc(intent["created_utc"])
        previous = max((_number(row["data"]["elapsed_seconds"]) for row in self.ledger.read()
                        if "elapsed_seconds" in row["data"]), default=Decimal(0))
        return max(Decimal(0), Decimal(str((_utc(self.clock()) - created).total_seconds())),
                   max(self._elapsed0, Decimal(str((self._wall0 - created).total_seconds())))
                   + _number(self.monotonic()) - self._mono0, previous)

    def cost_check(self, pod, horizon=60):
        intent = self.event("create-intent")["data"]
        owned = self.owned()
        expected, quoted = intent["payload"], _number(intent["quote"]["hourly_rate_usd"])
        gpu = pod.get("gpu")
        if (any(pod.get(key) != owned[key] for key in ("id", "name", "createdAt"))
                or not 0 < _number(pod.get("cost")) <= quoted
                or not isinstance(gpu, dict) or gpu.get("id") != HARDWARE[self.kind][0]
                or type(gpu.get("count")) is not int or gpu["count"] != 1
                or any(pod.get(key) != expected[key] for key in ("cloud", "image", "disk", "mounts", "ports"))):
            raise ValueError("Unknown billing rate, ownership or hardware drift")
        seconds = _number(horizon)
        if seconds <= 0:
            raise ValueError("Positive monitoring horizon required")
        last_wall = max([self._wall0, _utc(intent["created_utc"])] + [
            _utc(row["data"]["utc"]) for row in self.ledger.read() if "elapsed_seconds" in row["data"]])
        if _utc(self.clock()) < last_wall or _number(self.monotonic()) < self._mono0:
            raise ValueError("Repair accounting clock moved backward")
        elapsed = self._elapsed(intent)
        rate = quoted + STORAGE
        spent = elapsed * rate / 3600
        projected = spent + (seconds + RETRIEVAL_SECONDS) * rate / 3600
        cumulative = self.budget["prior_total_usd"] + _number(intent["prior_repair_usd"]) + projected
        self.record("accounting", {"utc": _utc(self.clock()).isoformat(), "elapsed_seconds": str(elapsed),
                                  "compute_upper_bound_usd": str(spent), "projected_usd": str(projected),
                                  "cumulative_projected_usd": str(cumulative)})
        if (elapsed + seconds >= HARD_SECONDS[self.kind] - RETRIEVAL_SECONDS
                or projected > _number(intent["local_cap_usd"])
                or _number(intent["prior_repair_usd"]) + projected > self.budget["repair_max_usd"]
                or cumulative > min(self.budget["total_usd"], Decimal("53.08"))):
            raise ValueError("Repair budget/retrieval reserve/deadline reached")
        return spent

    def start_worker(self):
        if self.event("worker-intent") or self.event("delete-intent") or self.event("closed"):
            raise ValueError("Worker already attempted or pod lifecycle ended; no duplicate worker")
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
                raise ValueError("Owned repair pod failed startup")
            self.sleep(15)
        else:
            raise TimeoutError("SSH startup exceeded bounded readiness window")
        token = os.environ.get("HF_TOKEN", "")
        if not token or any(c.isspace() for c in token):
            raise ValueError("HF_TOKEN missing/malformed; worker not started")
        self._ssh(pod, "umask 077; mkdir -p " + frozen.REMOTE + "/out; cat > " + frozen.REMOTE
                  + "/hf.env; chmod 600 " + frozen.REMOTE + "/hf.env",
                  data=("export HF_TOKEN=" + shlex.quote(token) + "\n").encode())
        self.cost_check(pod, 60)
        script = worker_script(self.kind, self.relative, self.freeze, intent["deadline_utc"])
        seconds = int(Decimal(HARD_SECONDS[self.kind] - RETRIEVAL_SECONDS) - self._elapsed(intent))
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

    def _confirm_closed(self, pod):
        try:
            self.api.request("GET", "/pods/" + pod["id"])
        except ApiError as exc:
            if exc.status != 404:
                raise
        else:
            raise ValueError("Deletion not verified")
        if pod["id"] in {item["id"] for item in self.api.inventory()}:
            raise ValueError("Deleted pod still in inventory")
        intent = self.event("create-intent")["data"]
        elapsed = self._elapsed(intent)
        try:
            rate = max(_number(pod.get("cost")), _number(intent["quote"]["hourly_rate_usd"])) + STORAGE
            cost = elapsed * rate / 3600
        except ValueError:
            cost = None
        repair = None if cost is None else _number(intent["prior_repair_usd"]) + cost
        cumulative = None if repair is None else self.budget["prior_total_usd"] + repair
        return self.ledger.transact("closed", lambda _: {
            "pod_id": pod["id"], "get_status": 404, "utc": _utc(self.clock()).isoformat(),
            "elapsed_seconds": str(elapsed), "compute_upper_bound_usd": None if cost is None else str(cost),
            "repair_upper_bound_usd": None if repair is None else str(repair),
            "cumulative_upper_bound_usd": None if cumulative is None else str(cumulative),
            "within_limits": (cost is not None and elapsed <= HARD_SECONDS[self.kind]
                              and cost <= _number(intent["local_cap_usd"])
                              and repair <= self.budget["repair_max_usd"]
                              and cumulative <= min(self.budget["total_usd"], Decimal("53.08")))})

    def status(self):
        pod = self.get_pod()
        state = {"pod": frozen.clean_pod(pod), "files": {}}
        if pod.get("status") == "RUNNING" and pod.get("ssh", {}).get("direct"):
            state["files"] = strict_json(self._ssh(pod, "python3 -c " + shlex.quote(STATUS_SCRIPT)))
        return state

    def monitor(self):
        """Frozen monitor behavior, with a one-poll horizon plus retrieval reserve."""
        if not self.api.writable:
            raise ValueError("Lifecycle monitor requires explicit --launch")
        last_pull = float("-inf")
        previous, changed_at, announced = None, time.monotonic(), None
        while True:
            state = self.status()
            self.record("health", state)
            terminal = any(name in state["files"] for name in frozen.TERMINAL)
            progress = state["files"].get("_progress", {})
            waiting = [name for name in WAITING if name in state["files"]
                       and state["files"].get("_approvals", {}).get(
                           name.replace("WAITING-", "APPROVE-").removesuffix(".json")) != self.plan_hash]
            if progress != previous:
                previous, changed_at = progress, time.monotonic()
            stall_limit = 900 if any(name.startswith("rows/") for name in progress) else 1800
            try:
                self.cost_check(state["pod"], 60)
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
                          "namespace": NAMESPACE, "network_calls": 0, "approval": "never automatic"}))
        return
    api = RunPodV2(os.environ.get("RUNPOD_API_KEY"), writable=True)
    controller = Controller(args.plan, args.freeze, args.out, args.kind, api)
    print(json.dumps(getattr(controller, args.action)(), sort_keys=True))


if __name__ == "__main__":
    main()

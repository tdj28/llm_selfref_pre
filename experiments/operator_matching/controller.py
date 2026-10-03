"""One cheap test pod and one bounded main pod; never adopt an existing pod.

Reuse the audited snapshot/deletion lifecycle and its exact worker identity
markers. New namespace, budget, dispatch and protocol are explicit here. The
budget contract is imported from protocol: a standalone $100 total, $60 new cap.

The protocol funds one replacement main pod after a startup failure. A main
controller therefore selects its ledger attempt (`main`, then `main-2`): a new
attempt opens only when the previous one has a verified `closed` receipt within
limits whose final retrieval holds no planned row and no DONE marker, and its
closed compute bound is carried into `prior_new_usd` so the $60 cap sums every
main attempt plus the cheap pod. A third attempt is refused.
"""
from __future__ import annotations

import argparse
from datetime import timedelta
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import time
import uuid

from experiments.sae_assay_diagnostic import controller as base
from experiments.sae_assay_diagnostic.budget import EventLedger, PodRegistry, _number, _utc
from experiments.sae_assay_exposure import controller as transport
from experiments.sae_assay_exposure_lifecycle_a1.controller import Controller as CorrectedLifecycle
from . import protocol, analysis

ROOT, REMOTE, HF_ENV = protocol.ROOT, transport.REMOTE, transport.HF_ENV
PREFIX, NAMESPACE = "claude-opmatch-20261002-", "operator-matching-controller"
OWNED_OUT = ROOT / "out/operator-matching-20261002"
ATTEMPTS = ("main", "main-2")  # one replacement pod after a startup failure, as the protocol funds
TOTAL_USD = Decimal(protocol.BUDGET["total_usd"])
if Decimal(protocol.PRIOR_USD) + Decimal(protocol.NEW_CAP_USD) > TOTAL_USD:
    raise ValueError("Incoherent budget: prior plus new cap exceeds total")


def worker_script(kind, relative, freeze, deadline):
    if kind not in base.HARDWARE or not re.fullmatch("[0-9a-f]{40}", freeze):
        raise ValueError("Invalid worker kind/freeze")
    path = Path(relative)
    if path.is_absolute() or ".." in path.parts or not relative.startswith("data/operator_matching/"):
        raise ValueError("Unsafe plan path")
    python = REMOTE + "/venv/bin/python"
    validate = "from experiments.operator_matching.protocol import load_plan; load_plan(" + repr(relative) + "," + repr(freeze) + ")"
    exit_code = "import json,sys; json.dump({'exit_code':int(sys.argv[1])},open(" + repr(REMOTE+"/out/controller-exit.json") + ",'x'))"
    if kind == "cheap":
        work = ["export BERG_TEST_DEVICE=cuda", shlex.join([python, "-m", "pytest",
            "tests/test_operator_matching.py", "-q", "--junitxml="+REMOTE+"/out/tests.xml"]),
            shlex.join([python, "-c", "import json; json.dump({'pass':True,'scope':'tiny_cuda_exact_path'},open("+
                        repr(REMOTE+"/out/DONE-all.json")+",'x'))"])]
    else:
        work = [shlex.join([python, "-u", "-m", "experiments.operator_matching.runner", "--plan", relative,
            "--freeze", freeze, "--out", REMOTE+"/out", "--cache", "/workspace/cache", "--deadline-utc", deadline])]
    return "\n".join(["set -euC", "umask 077", "mkdir -p " + REMOTE + "/out",
        "trap 'rc=$?; rm -f " + HF_ENV + "; python3 -c " + shlex.quote(exit_code).replace("'", "'\"'\"'") + " \"$rc\"' EXIT",
        "git -c credential.helper= clone --filter=blob:none --no-checkout " + base.REPO + " " + REMOTE+"/repo",
        "cd " + REMOTE+"/repo", "git fetch --depth=1 origin " + freeze,
        "git checkout --detach " + freeze, 'test "$(git rev-parse HEAD)" = ' + freeze,
        "python3 -m venv --system-site-packages " + REMOTE+"/venv",
        python + " -m pip install -r " + protocol.REQUIREMENTS,
        python + " -m pip freeze --all > " + REMOTE+"/out/pip-freeze.txt",
        shlex.join([python, "-c", validate]), "set +x; . " + HF_ENV + "; rm -f " + HF_ENV,
        "export HF_HOME=/workspace/cache PYTHONUNBUFFERED=1", *work])


class Controller(transport.Controller):
    signal_worker = CorrectedLifecycle.signal_worker

    def __init__(self, plan_path, freeze, out, kind, api, *, run=subprocess.run,
                 clock=base.now, sleep=time.sleep, monotonic=time.monotonic):
        if kind not in base.HARDWARE or not re.fullmatch("[0-9a-f]{40}", freeze):
            raise ValueError("Exact freeze and cheap/main required")
        self.plan_path, self.freeze, self.kind = Path(plan_path).resolve(), freeze, kind
        self.plan = protocol.load_plan(self.plan_path, freeze)
        if self.plan["budget"] != protocol.BUDGET:
            raise ValueError("Budget contract changed")
        self.plan_hash, self.relative = protocol.sha(self.plan_path), self.plan_path.relative_to(ROOT).as_posix()
        self.out = Path(out).resolve()
        if self.out != OWNED_OUT:
            raise ValueError("One canonical ledger root; do not reset spending through another output directory")
        self.base, self.replaced = self._attempt()
        self.base.mkdir(parents=True, exist_ok=True, mode=0o700)
        if self.base.is_symlink():
            raise ValueError("Ledger symlink")
        self.api, self.run, self.clock, self.sleep, self.monotonic = api, run, clock, sleep, monotonic
        self._wall0, self._mono0 = _utc(clock()), _number(monotonic())
        self._last_mono = self._mono0
        self.ledger = EventLedger(self.base/"events.jsonl", self.plan_hash, freeze, [])
        self._elapsed0 = max((_number(r["data"]["elapsed_seconds"]) for r in self.ledger.read()
                             if "elapsed_seconds" in r["data"]), default=Decimal(0))
        self.hard_seconds = protocol.MAIN_SECONDS if kind == "main" else protocol.CHEAP_SECONDS
        self.budget = self.plan["budget"]
        self.ledger.bind("controller:config", {"kind": kind, "namespace": NAMESPACE, "attempt": self.base.name,
            "plan_path": self.relative, "budget": self.budget, "hard_seconds": self.hard_seconds})

    def _new_pod(self, pod, intent):
        return (re.fullmatch(re.escape(PREFIX)+self.kind+r"-[0-9a-f]{12}", intent["payload"].get("name", "")) is not None
                and intent.get("plan_sha256") == self.plan_hash and intent.get("freeze_commit") == self.freeze
                and base.Controller._new_pod(self, pod, intent))

    def _closed(self, directory):
        """The `closed` receipt of a ledger attempt bound to this plan/freeze; None if open or never created."""
        path = directory / "events.jsonl"
        if not path.exists():
            return None
        ledger = EventLedger(path, self.plan_hash, self.freeze, [])
        return next((e["data"] for e in ledger.read() if e["id"] == "closed"), None)

    def _startup_failure(self, directory, closed):
        """Closed compute bound of an earlier main attempt that may be replaced: verified deletion within limits
        and a final retrieval holding no planned row and no DONE marker, so no outcome is ever re-run."""
        if not closed["within_limits"]:
            raise ValueError("Closed main attempt exceeded its limits; no replacement")
        receipt = directory / "final-retrieval.json"
        if not receipt.exists():
            raise ValueError("Closed main attempt lacks its final retrieval receipt")
        saved = json.loads(receipt.read_text())["data"]
        artifacts = saved["artifacts"]
        if any(n.startswith("rows/") and n != "rows/qualification-live.json" for n in artifacts) or "DONE-all.json" in artifacts:
            raise ValueError("Main attempt produced planned rows; a replacement would re-run outcomes")
        for name, digest in artifacts.items():
            if protocol.sha(Path(saved["directory"])/name) != digest:
                raise ValueError("Failed-attempt artifact hash changed")
        return _number(closed["compute_upper_bound_usd"])

    def _attempt(self):
        """(ledger directory, replaced attempt directories) for this kind; main may replace one closed startup failure."""
        if self.kind != "main":
            return self.out / NAMESPACE / self.kind, []
        directories = [self.out / NAMESPACE / name for name in ATTEMPTS]
        for i, directory in enumerate(directories):
            closed = self._closed(directory)
            if closed is None:
                return directory, directories[:i]
            self._startup_failure(directory, closed)
        raise ValueError("Replacement allowance exhausted; a new frozen plan is required")

    def failed_main_cost(self):
        return sum((self._startup_failure(d, self._closed(d)) for d in self.replaced), Decimal(0))

    def cheap_receipt(self):
        path = self.out/NAMESPACE/"cheap/events.jsonl"
        ledger = EventLedger(path, self.plan_hash, self.freeze, [])
        closed = next((e["data"] for e in ledger.read() if e["id"] == "closed"), None)
        receipt = self.out/NAMESPACE/"cheap/final-retrieval.json"
        if closed is None or not closed["within_limits"] or not receipt.exists():
            raise ValueError("Cheap owned-pod checks and verified deletion required first")
        saved = json.loads(receipt.read_text())["data"]
        directory = Path(saved["directory"])
        for name, digest in saved["artifacts"].items():
            if protocol.sha(directory/name) != digest:
                raise ValueError("Cheap artifact hash changed")
        if not json.loads((directory/"DONE-all.json").read_text())["pass"]:
            raise ValueError("Cheap exact-path tests failed")
        return _number(closed["compute_upper_bound_usd"])

    @transport.serialized
    def launch(self):
        if not self.api.writable or self.event("create-intent"):
            raise ValueError("Fresh explicit creation only")
        protocol.load_plan(self.plan_path, self.freeze)
        self.disk_check()
        prior_new = self.cheap_receipt() + self.failed_main_cost() if self.kind == "main" else Decimal(0)
        if self.kind == "main" and not os.environ.get("HF_TOKEN"):
            raise ValueError("HF_TOKEN required before rental")
        key = Path(str(base.KEY.expanduser())+".pub").read_text().strip()
        name = PREFIX + self.kind + "-" + uuid.uuid4().hex[:12]
        payload = base.create_payload(self.kind, base.PREFIX+self.kind+"-"+name[-12:], key)
        payload["name"] = name
        base.verify_public(self.plan_hash, self.relative, self.freeze)
        blocked = sorted({base.BLOCKED} | {p["id"] for p in self.api.inventory()})
        PodRegistry(self.ledger, blocked)
        quoted = base.quote(self.api, self.kind)
        created = _utc(self.clock())
        rate = _number(quoted["hourly_rate_usd"])+base.STORAGE
        if prior_new + rate*self.hard_seconds/3600 > Decimal(protocol.NEW_CAP_USD):
            raise ValueError("Entire timer is not funded")
        intent = {"payload": payload, "quote": quoted, "blocked": blocked, "created_utc": created.isoformat(),
            "deadline_utc": (created+timedelta(seconds=self.hard_seconds-protocol.RESERVE_SECONDS)).isoformat(),
            "hard_deadline_utc": (created+timedelta(seconds=self.hard_seconds)).isoformat(),
            "prior_new_usd": str(prior_new), "prior_total_usd": protocol.PRIOR_USD,
            "attempt": self.base.name, "replaces": [d.name for d in self.replaced],
            "plan_sha256": self.plan_hash, "freeze_commit": self.freeze}
        self.ledger.transact("create-intent", lambda _: intent)
        self._wall0, self._mono0 = created, _number(self.monotonic())
        self._last_mono = self._mono0
        try:
            status, pod = self.api.request("POST", "/pods", payload)
            if status != 201 or not self._new_pod(pod, intent):
                raise ValueError("Ambiguous creation")
        except (base.ApiError, RuntimeError, ValueError, OSError, KeyError, TypeError):
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
        owned, intent = self.owned(), self.event("create-intent")["data"]
        expected, quote = intent["payload"], _number(intent["quote"]["hourly_rate_usd"])
        if (any(pod.get(k) != owned[k] for k in ("id", "name", "createdAt"))
            or not 0 < _number(pod.get("cost")) <= quote
            or pod.get("gpu", {}).get("id") != base.HARDWARE[self.kind][0]
            or pod.get("gpu", {}).get("count") != 1
            or _number(pod.get("gpu", {}).get("memory")) < base.HARDWARE[self.kind][2]
            or any(pod.get(k) != expected[k] for k in ("cloud", "image", "disk", "mounts", "ports"))):
            raise ValueError("Ownership/hardware/billing drift")
        mono = _number(self.monotonic())
        last_wall = max([self._wall0, _utc(intent["created_utc"])] + [
            _utc(r["data"]["utc"]) for r in self.ledger.read() if "elapsed_seconds" in r["data"]])
        if _utc(self.clock()) < last_wall or mono < self._last_mono or horizon <= 0:
            raise ValueError("Accounting clock moved backward or invalid horizon")
        self._last_mono = mono
        elapsed, rate = self._elapsed(intent), quote+base.STORAGE
        projected = (elapsed+_number(horizon)+protocol.RESERVE_SECONDS)*rate/3600
        cumulative = Decimal(protocol.PRIOR_USD)+_number(intent["prior_new_usd"])+projected
        self.record("accounting", {"utc": _utc(self.clock()).isoformat(), "elapsed_seconds": str(elapsed),
                    "projected_usd": str(projected), "cumulative_projected_usd": str(cumulative)})
        if (elapsed+horizon >= self.hard_seconds-protocol.RESERVE_SECONDS or cumulative > TOTAL_USD
                or _number(intent["prior_new_usd"])+projected > Decimal(protocol.NEW_CAP_USD)):
            raise ValueError("Budget or retrieval deadline reached")
        return elapsed*rate/3600

    @transport.serialized
    def start_worker(self):
        if not self.api.writable or any(self.event(n) for n in ("worker-intent", "closing", "closed")):
            raise ValueError("Worker dispatch disabled")
        intent = self.event("create-intent")["data"]
        for _ in range(40):
            pod = self.get_pod()
            self.cost_check(pod, 120)
            if pod.get("status") == "RUNNING" and pod.get("ssh", {}).get("direct"):
                try:
                    self._ssh(pod, "true", timeout=15)
                    break
                except (RuntimeError, subprocess.TimeoutExpired):
                    pass
            if pod.get("status") not in {"PROVISIONING", "STARTING", "RUNNING"}:
                raise ValueError("Owned pod startup failed")
            self.sleep(15)
        else:
            raise TimeoutError("SSH readiness deadline")
        token = os.environ.get("HF_TOKEN", "") if self.kind == "main" else ""
        if any(c.isspace() for c in token) or self.kind == "main" and not token:
            raise ValueError("Invalid model-download credential")
        self.ledger.bind("credential-intent", {"path": HF_ENV})
        self._ssh(pod, "set -euC; umask 077; mkdir -p "+REMOTE+"/out; cat > "+HF_ENV,
                  data=("export HF_TOKEN="+shlex.quote(token)+"\n").encode())
        script = worker_script(self.kind, self.relative, self.freeze, intent["deadline_utc"])
        seconds = int(self.hard_seconds-protocol.RESERVE_SECONDS-self._elapsed(intent))
        if seconds <= 30:
            raise ValueError("No worker window")
        binding = {"worker_id": uuid.uuid4().hex, "pod_id": pod["id"], "plan_sha256": self.plan_hash,
                   "freeze_commit": self.freeze}
        self.ledger.transact("worker-intent", lambda _: {**binding, "script_sha256": hashlib.sha256(script.encode()).hexdigest(),
            "seconds": seconds, "deadline_utc": intent["deadline_utc"], "hard_deadline_utc": intent["hard_deadline_utc"]})
        self._ssh(pod, transport.dispatch_command(script, seconds, binding))
        self.ledger.bind("worker-started", {"utc": _utc(self.clock()).isoformat()})

    def _confirm_closed(self, pod):
        if any(pod.get(k) != self.owned()[k] for k in ("id", "name", "createdAt")):
            raise ValueError("Foreign deletion receipt")
        try:
            self.api.request("GET", "/pods/"+pod["id"])
        except base.ApiError as exc:
            if exc.status != 404:
                raise
        else:
            raise ValueError("Deletion unverified")
        inventory = self.api.inventory()
        if pod["id"] in {p["id"] for p in inventory}:
            raise ValueError("Deleted pod remains listed")
        intent = self.event("create-intent")["data"]
        elapsed = self._elapsed(intent)
        cost = elapsed*(max(_number(pod["cost"]), _number(intent["quote"]["hourly_rate_usd"]))+base.STORAGE)/3600
        total = Decimal(protocol.PRIOR_USD)+_number(intent["prior_new_usd"])+cost
        return self.ledger.bind("closed", {"pod_id": pod["id"], "get_status": 404,
            "utc": _utc(self.clock()).isoformat(), "elapsed_seconds": str(elapsed),
            "compute_upper_bound_usd": str(cost), "cumulative_upper_bound_usd": str(total),
            "within_limits": elapsed <= self.hard_seconds and total <= TOTAL_USD and
                _number(intent["prior_new_usd"])+cost <= Decimal(protocol.NEW_CAP_USD)})

    def monitor(self):
        if not self.api.writable:
            raise ValueError("Explicit paid lifecycle required")
        last_pull, failures = float("-inf"), 0
        while True:
            try:
                state = self.status()
                self.cost_check(state["pod"])
                self.record("health", state)
                files = state["files"]
                if any(n in files for n in base.TERMINAL):
                    return self.close_until_verified()
                waiting = [n for n in transport.BARRIERS if "WAITING-"+n+".json" in files
                           and not self.event("approved:"+n)]
                if waiting or self.monotonic()-last_pull > 600:
                    receipt = self.retrieve()["data"]
                    root = Path(receipt["directory"])
                    report = analysis.audit(root, self.plan, plan_sha256=self.plan_hash, freeze=self.freeze)
                    self.record("live-audit", report)
                    print(protocol.canonical({"live_audit": report, "pod_id": state["pod"]["id"]}), flush=True)
                    for name in waiting:
                        self.approve(name, self.plan_hash)
                    last_pull = self.monotonic()
                failures = 0
            except ValueError as exc:
                self.record("monitor-failed", {"error_type": type(exc).__name__})
                return self.close_until_verified()
            except (RuntimeError, OSError, subprocess.TimeoutExpired) as exc:
                failures += 1
                self.record("monitor-retry", {"error_type": type(exc).__name__, "count": failures})
                if failures >= 3:
                    return self.close_until_verified()
            self.sleep(60)

    def close_until_verified(self):
        if not self.api.writable:
            raise ValueError("Explicit paid lifecycle required for cleanup")
        self.owned()
        while True:
            try:
                return self.terminate()
            except (RuntimeError, ValueError, OSError, subprocess.TimeoutExpired) as exc:
                elapsed = self._elapsed(self.event("create-intent")["data"])
                overdue = elapsed >= self.hard_seconds
                self.record("cleanup-retry", {"error_type": type(exc).__name__,
                    "utc": _utc(self.clock()).isoformat(), "elapsed_seconds": str(elapsed),
                    "hard_deadline_exceeded": overdue, "hard_seconds": self.hard_seconds})
                print("ATTENTION: owned pod cleanup unresolved; evidence retained."
                      + (" Hard deadline exceeded; user action required." if overdue else ""), flush=True)
                self.sleep(15)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--plan", required=True)
    p.add_argument("--freeze", required=True)
    p.add_argument("--kind", choices=("cheap", "main"), required=True)
    p.add_argument("--action", choices=("launch", "status", "monitor", "terminate", "retrieve"), default="launch")
    p.add_argument("--launch", action="store_true")
    a = p.parse_args()
    if not a.launch:
        protocol.load_plan(a.plan, a.freeze)
        print(protocol.canonical({"dry_run": True, "network_calls": 0, "new_cap_usd": protocol.NEW_CAP_USD,
                                  "total_usd": protocol.BUDGET["total_usd"]}))
        return
    from dotenv import load_dotenv
    load_dotenv(ROOT/".env")
    api = base.RunPodV2(os.environ.get("RUNPOD_API_KEY"), writable=True)
    c = Controller(a.plan, a.freeze, OWNED_OUT, a.kind, api)
    if a.action == "launch":
        print(protocol.canonical(c.launch()), flush=True)
        print(protocol.canonical(c.monitor()), flush=True)
    else:
        print(protocol.canonical(getattr(c, a.action)()), flush=True)


if __name__ == "__main__":
    main()

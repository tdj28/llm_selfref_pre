"""Offline-by-default Phase A lifecycle; never an authorization to spend.

Reuse the audited Berg transport, retrieval/deletion and corrected process
identity machinery unchanged. Its remote paths and CODEX_EXPOSURE markers are
intentional: changing only one side would break ownership reconciliation.
Local ledgers and pod names have a separate causal-study namespace.

Creation needs --launch, --approved-new-cap-usd 15, --approval-ref, and an
existing ignored approval JSON. The exact JSON fields are returned by
approval_record(); the caller must obtain real user confirmation, never create
that record on the user's behalf from a draft protocol or an agent review.
These records attest a supplied confirmation reference, not Pro review or
independent verification of human identity. Cleanup does not need renewed
creation approval. Remote timeout stops work, not billing; supervise cleanup.
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

from experiments.berg_ensemble_replication import controller as ensemble
from experiments.sae_assay_diagnostic import controller as base
from experiments.sae_assay_diagnostic.budget import EventLedger, PodRegistry, _canonical, _number, _utc
from experiments.sae_assay_exposure import controller as transport
from experiments.sae_assay_exposure_lifecycle_a1.controller import Controller as CorrectedLifecycle
from . import protocol

ROOT = protocol.ROOT
PREFIX, NAMESPACE = "codex-jlens-causal-20261001-", "jlens-causal-controller"
OWNED_OUT = ROOT / "out/jlens-causal-20261001"
REMOTE, HF_ENV = transport.REMOTE, transport.HF_ENV
PRIOR_USD, NEW_CAP_USD, TOTAL_USD = Decimal("69.130940"), Decimal("15"), Decimal("200")
MAIN_SECONDS, CHEAP_SECONDS, RESERVE_SECONDS = 7200, 1800, 600
BUDGET = {"prior_usd": "69.130940", "new_cap_usd": "15", "total_usd": "200",
          "main_seconds": 7200, "cheap_seconds": 1800, "reserve_seconds": 600,
          "new_pro_calls": 0, "external_judge_calls": 0}
BARRIERS = transport.BARRIERS
sha = protocol.sha


def load_plan(path, freeze=None):
    # The incoming protocol is authoritative; no fallback or synthetic plan.
    return protocol.load_plan(path, freeze)


def audit(root, plan, partial=True):
    from .analysis import audit as local_audit
    return local_audit(root, plan, partial=partial)


def checked_budget(plan):
    """Require every explicit field; unknown/missing contracts fail closed.

This is an operational ceiling, not a default injected into the parent plan.
The parent must agree on this exact contract before a public freeze.
"""
    budget = plan.get("budget")
    if not isinstance(budget, dict) or _canonical(budget) != _canonical(BUDGET):
        raise ValueError("Explicit Phase A budget contract missing/changed; ask the protocol owner")
    return budget.copy()


def _safe_path(relative):
    path = PurePosixPath(relative)
    if (not relative.startswith("data/jlens_causal_report/") or path.is_absolute()
            or ".." in path.parts or path.as_posix() != relative
            or any(ord(c) < 32 for c in relative)):
        raise ValueError("Unsafe causal plan path")
    return path


def _no_symlinks(path):
    path = Path(path).absolute()
    if ".." in path.parts:
        raise ValueError("Private lifecycle paths cannot contain traversal")
    for item in (path, *path.parents):
        if item.is_symlink():
            raise ValueError("Private lifecycle paths cannot contain a symlink")


def _require_ignored(path):
    relative = Path(path).relative_to(ROOT).as_posix()
    result = subprocess.run(["git", "check-ignore", "--quiet", "--", relative], cwd=ROOT,
                            capture_output=True, timeout=10, env=base.local_env())
    if result.returncode != 0:
        raise ValueError("Local lifecycle/approval record must be git-ignored and untracked")


def approval_record(plan_hash, freeze, budget, approval_ref):
    """Schema only. Calling this function does not establish authorization."""
    checked_budget({"budget": budget})
    if (not isinstance(approval_ref, str)
            or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,159}", approval_ref)):
        raise ValueError("A short nonsecret approval-ref is required")
    return {"phase": "A", "user_confirmed": True, "approval_ref": approval_ref,
            "approved_new_cap_usd": "15", "plan_sha256": plan_hash, "freeze_commit": freeze,
            "budget_sha256": hashlib.sha256(_canonical(budget)).hexdigest()}


def worker_script(kind, relative, freeze, deadline):
    if kind not in ("cheap", "main") or not re.fullmatch(r"[0-9a-f]{40}", freeze):
        raise ValueError("Exact freeze and cheap/main required")
    _safe_path(relative)
    _utc(deadline)
    python = REMOTE + "/venv/bin/python"
    validate = ("from experiments.jlens_causal_report.protocol import load_plan; load_plan("
                + repr(relative) + "," + repr(freeze) + ")")
    exit_code = ("import json,sys; json.dump({'exit_code':int(sys.argv[1])},open("
                 + repr(REMOTE + "/out/controller-exit.json") + ",'x'))")
    if kind == "cheap":
        tests = ["tests/test_jlens_causal_operators.py", "tests/test_jlens_causal_backend.py",
                 "tests/test_jlens_causal_protocol.py"]
        tests += [path for path in ("tests/test_jlens_causal_runner.py", "tests/test_jlens_causal_analysis.py")
                  if (ROOT / path).is_file()]
        work = ["export JLENS_TEST_CUDA=1 HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1",
                shlex.join([python, "-c", "import torch,transformers; assert torch.cuda.is_available(), 'CUDA required'"]),
                shlex.join([python, "-m", "pytest", *tests,
                            "-q", "--junitxml=" + REMOTE + "/out/tests.xml"]),
                shlex.join([python, "-c", "import json; json.dump({'pass':True,'scope':'tiny_cuda_exact_path'},open("
                            + repr(REMOTE + "/out/DONE-all.json") + ",'x'))"])]
    else:
        work = [shlex.join([python, "-u", "-m", "experiments.jlens_causal_report.runner",
                            "--plan", relative, "--freeze", freeze, "--out", REMOTE + "/out",
                            "--cache", "/workspace/cache", "--deadline-utc", deadline])]
    return "\n".join([
        "set -euC", "umask 077", "mkdir -p " + REMOTE + "/out",
        "trap 'rc=$?; rm -f " + HF_ENV + "; python3 -c "
        + shlex.quote(exit_code).replace("'", "'\"'\"'") + " \"$rc\"' EXIT",
        "git -c credential.helper= clone --filter=blob:none --no-checkout " + base.REPO + " " + REMOTE + "/repo",
        "cd " + REMOTE + "/repo", "git fetch --depth=1 origin " + freeze,
        "git checkout --detach " + freeze, 'test "$(git rev-parse HEAD)" = ' + freeze,
        "python3 -m venv --system-site-packages " + REMOTE + "/venv",
        python + " -m pip install -r experiments/sae_assay_diagnostic/requirements-gpu.txt",
        python + " -m pip freeze --all > " + REMOTE + "/out/pip-freeze.txt",
        shlex.join([python, "-c", validate]), "set +x; . " + HF_ENV + "; rm -f " + HF_ENV,
        "export HF_HOME=/workspace/cache PYTHONUNBUFFERED=1", *work])


class Controller(ensemble.Controller):
    """Inherit audited locking, ownership, snapshot verification and cleanup.

Barrier names and transport row counts remain qualification=1, first-five=6.
The incoming runner/auditor must bind the first-five complete pairs to those
receipted units; rows alone are not scientific qualification.
"""

    signal_worker = CorrectedLifecycle.signal_worker

    def __init__(self, plan_path, freeze, out, kind, api, *, launch=False,
                 approved_new_cap_usd=None, approval_ref=None, approval_file=None,
                 run=subprocess.run, clock=base.now, sleep=time.sleep, monotonic=time.monotonic):
        if kind not in ("cheap", "main") or not re.fullmatch(r"[0-9a-f]{40}", freeze):
            raise ValueError("Exact freeze and cheap/main required")
        self.plan_path, self.freeze, self.kind = Path(plan_path).resolve(), freeze, kind
        self.plan = load_plan(self.plan_path, freeze)
        self.budget = checked_budget(self.plan)
        self.plan_hash, self.relative = sha(self.plan_path), self.plan_path.relative_to(ROOT).as_posix()
        _safe_path(self.relative)
        self.out = Path(out).absolute()
        if self.out != OWNED_OUT:
            raise ValueError("One canonical ledger root required; spending cannot be reset")
        self.base = self.out / NAMESPACE / kind
        _no_symlinks(self.base)
        _require_ignored(self.base / "events.jsonl")
        for directory in (self.out, self.base.parent, self.base):
            directory.mkdir(parents=True, exist_ok=True, mode=0o700)
            directory.chmod(0o700)
        self.api, self.run, self.clock, self.sleep, self.monotonic = api, run, clock, sleep, monotonic
        self.launch_enabled = launch is True
        self.approved_new_cap_usd, self.approval_ref = approved_new_cap_usd, approval_ref
        self.approval_file = Path(approval_file).absolute() if approval_file is not None else None
        self._wall0, self._mono0 = _utc(clock()), _number(monotonic())
        self._last_mono = self._mono0
        self.ledger = EventLedger(self.base / "events.jsonl", self.plan_hash, freeze, [])
        self.ledger.path.chmod(0o600)
        self._elapsed0 = max((_number(r["data"]["elapsed_seconds"]) for r in self.ledger.read()
                             if "elapsed_seconds" in r["data"]), default=Decimal(0))
        self.hard_seconds = MAIN_SECONDS if kind == "main" else CHEAP_SECONDS
        self.ledger.bind("controller:config", {"kind": kind, "namespace": NAMESPACE,
            "plan_path": self.relative, "budget": self.budget, "hard_seconds": self.hard_seconds,
            "retrieval_seconds": RESERVE_SECONDS, "image": base.IMAGE})

    def _new_pod(self, pod, intent):
        return (re.fullmatch(re.escape(PREFIX) + self.kind + r"-[0-9a-f]{12}",
                             intent["payload"].get("name", "")) is not None
                and intent.get("plan_sha256") == self.plan_hash and intent.get("freeze_commit") == self.freeze
                and base.Controller._new_pod(self, pod, intent))

    def _creation_approval(self):
        if not self.launch_enabled or not self.api.writable or _number(self.approved_new_cap_usd) != NEW_CAP_USD:
            raise ValueError("Creation requires --launch and --approved-new-cap-usd 15")
        expected = approval_record(self.plan_hash, self.freeze, self.budget, self.approval_ref)
        path = self.approval_file
        if path is None or not path.is_relative_to(self.out):
            raise ValueError("Existing approval-file under canonical ignored output is required")
        _no_symlinks(path)
        _require_ignored(path)
        if not path.is_file() or path.stat().st_size > 8192:
            raise ValueError("Missing or oversized local approval-file")
        raw = path.read_bytes()
        if _canonical(base.strict_json(raw)) != _canonical(expected):
            raise ValueError("Approval record must bind user confirmation, cap, plan, freeze and reference")
        return {**expected, "approval_file_sha256": hashlib.sha256(raw).hexdigest(),
                "approval_file": path.relative_to(self.out).as_posix(),
                "authority": "caller-supplied user confirmation; not Pro review"}

    def cheap_receipt(self):
        root = self.out / NAMESPACE / "cheap"
        _no_symlinks(root)
        if not (root / "events.jsonl").is_file():
            raise ValueError("Verified cheap qualification required before main creation")
        ledger = EventLedger(root / "events.jsonl", self.plan_hash, self.freeze, [])
        events = {event["id"]: event for event in ledger.read()}
        closed = events.get("closed", {}).get("data", {})
        path = root / "final-retrieval.json"
        _no_symlinks(path)
        if closed.get("within_limits") is not True or closed.get("get_status") != 404 or not path.is_file():
            raise ValueError("Cheap pod must be retrieved and deletion verified")
        receipt = base.strict_json(path.read_bytes())
        if events.get(receipt.get("id")) != receipt:
            raise ValueError("Cheap retrieval is not bound to its ledger")
        saved = receipt["data"]
        if saved.get("pod_id") != closed.get("pod_id"):
            raise ValueError("Cheap closure and retrieval identity differ")
        directory = Path(saved["directory"])
        if not directory.is_relative_to(root / "retrievals"):
            raise ValueError("Cheap snapshot outside canonical retrieval root")
        _no_symlinks(directory)
        for name, digest in saved["artifacts"].items():
            if PurePosixPath(name).is_absolute() or ".." in PurePosixPath(name).parts:
                raise ValueError("Unsafe cheap artifact path")
            artifact = directory / name
            _no_symlinks(artifact)
            if not artifact.is_file() or sha(artifact) != digest:
                raise ValueError("Cheap artifact hash changed")
        if not {"DONE-all.json", "tests.xml", "controller-exit.json"} <= saved["artifacts"].keys():
            raise ValueError("Cheap completion artifacts missing")
        if (_canonical(base.strict_json((directory / "DONE-all.json").read_bytes())) !=
                _canonical({"pass": True, "scope": "tiny_cuda_exact_path"})
                or base.strict_json((directory / "controller-exit.json").read_bytes()) != {"exit_code": 0}):
            raise ValueError("Cheap exact-path tests failed")
        return _number(closed["compute_upper_bound_usd"])

    @transport.serialized
    def launch(self):
        if self.event("create-intent"):
            raise ValueError("Creation already attempted; reconcile only, never retry")
        approval = self._creation_approval()
        if load_plan(self.plan_path, self.freeze) != self.plan or sha(self.plan_path) != self.plan_hash:
            raise ValueError("Plan changed since construction")
        self.disk_check()
        prior_new = self.cheap_receipt() if self.kind == "main" else Decimal(0)
        if self.kind == "main":
            token = os.environ.get("HF_TOKEN", "")
            if not token or any(c.isspace() for c in token):
                raise ValueError("HF_TOKEN missing/malformed before rental")
        if not base.KEY.expanduser().is_file():
            raise ValueError("Existing private SSH key required")
        key = Path(str(base.KEY.expanduser()) + ".pub").read_text().strip()
        name = PREFIX + self.kind + "-" + uuid.uuid4().hex[:12]
        payload = base.create_payload(self.kind, base.PREFIX + self.kind + "-" + name[-12:], key)
        payload["name"] = name
        base.verify_public(self.plan_hash, self.relative, self.freeze)
        blocked = sorted({base.BLOCKED} | {p["id"] for p in self.api.inventory()})
        PodRegistry(self.ledger, blocked)
        quoted = base.quote(self.api, self.kind)
        created = _utc(self.clock())
        rate = _number(quoted["hourly_rate_usd"]) + base.STORAGE
        full_cost = prior_new + rate * self.hard_seconds / 3600
        # The cheap timer also leaves room for the entire maximum-price main timer.
        if self.kind == "cheap":
            full_cost += (base.HARDWARE["main"][1] + base.STORAGE) * MAIN_SECONDS / 3600
        if full_cost > NEW_CAP_USD or PRIOR_USD + full_cost > TOTAL_USD:
            raise ValueError("Entire pair of timers including storage/retrieval is not funded")
        authority = self.ledger.bind("creation-approval", approval)
        intent = {"payload": payload, "quote": quoted, "blocked": blocked, "created_utc": created.isoformat(),
                  "deadline_utc": (created + timedelta(seconds=self.hard_seconds - RESERVE_SECONDS)).isoformat(),
                  "hard_deadline_utc": (created + timedelta(seconds=self.hard_seconds)).isoformat(),
                  "prior_new_usd": str(prior_new), "prior_total_usd": str(PRIOR_USD),
                  "plan_sha256": self.plan_hash, "freeze_commit": self.freeze,
                  "approval_sha256": authority["sha256"]}
        self.ledger.transact("create-intent", lambda _: intent)
        self._wall0, self._mono0 = created, _number(self.monotonic())
        self._last_mono = self._mono0
        if not 0 <= (_utc(self.clock()) - created).total_seconds() <= 60:
            raise ValueError("Stale creation intent; do not retry")
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
        intent, owned = self.event("create-intent")["data"], self.owned()
        expected, quote = intent["payload"], _number(intent["quote"]["hourly_rate_usd"])
        gpu = pod.get("gpu")
        if (any(pod.get(k) != owned[k] for k in ("id", "name", "createdAt"))
                or not 0 < _number(pod.get("cost")) <= quote
                or not isinstance(gpu, dict) or gpu.get("id") != base.HARDWARE[self.kind][0]
                or type(gpu.get("count")) is not int or gpu["count"] != 1
                or _number(gpu.get("memory")) < base.HARDWARE[self.kind][2]
                or any(pod.get(k) != expected[k] for k in ("cloud", "image", "disk", "mounts", "ports"))):
            raise ValueError("Ownership/hardware/billing/storage drift")
        seconds, mono = _number(horizon), _number(self.monotonic())
        last_wall = max([self._wall0, _utc(intent["created_utc"])] + [
            _utc(r["data"]["utc"]) for r in self.ledger.read() if "elapsed_seconds" in r["data"]])
        if _utc(self.clock()) < last_wall or mono < self._last_mono or seconds <= 0:
            raise ValueError("Accounting clock moved backward or invalid horizon")
        self._last_mono = mono
        elapsed, rate = self._elapsed(intent), quote + base.STORAGE
        projected = (elapsed + seconds + RESERVE_SECONDS) * rate / 3600
        new = _number(intent["prior_new_usd"]) + projected
        self.record("accounting", {"utc": _utc(self.clock()).isoformat(), "elapsed_seconds": str(elapsed),
                    "projected_usd": str(projected), "cumulative_projected_usd": str(PRIOR_USD + new)})
        if elapsed + seconds >= self.hard_seconds - RESERVE_SECONDS or new > NEW_CAP_USD or PRIOR_USD + new > TOTAL_USD:
            raise ValueError("Budget or retrieval deadline reached")
        return elapsed * rate / 3600

    @transport.serialized
    def start_worker(self):
        if (not self.launch_enabled or not self.api.writable or not self.event("creation-approval")
                or any(self.event(n) for n in ("worker-intent", "closing", "delete-intent", "closed"))):
            raise ValueError("Worker dispatch disabled or already attempted")
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
        self._ssh(pod, "set -euC; umask 077; mkdir -p " + REMOTE + "/out; cat > " + HF_ENV,
                  data=("export HF_TOKEN=" + shlex.quote(token) + "\n").encode())
        script = worker_script(self.kind, self.relative, self.freeze, intent["deadline_utc"])
        seconds = int(self.hard_seconds - RESERVE_SECONDS - self._elapsed(intent))
        if seconds <= 30:
            raise ValueError("No worker window")
        binding = {"worker_id": uuid.uuid4().hex, "pod_id": pod["id"], "plan_sha256": self.plan_hash,
                   "freeze_commit": self.freeze}
        self.ledger.transact("worker-intent", lambda _: {**binding,
            "script_sha256": hashlib.sha256(script.encode()).hexdigest(), "seconds": seconds,
            "deadline_utc": intent["deadline_utc"], "hard_deadline_utc": intent["hard_deadline_utc"]})
        self._ssh(pod, transport.dispatch_command(script, seconds, binding))
        self.ledger.bind("worker-started", {"utc": _utc(self.clock()).isoformat()})

    def _confirm_closed(self, pod):
        if any(pod.get(k) != self.owned()[k] for k in ("id", "name", "createdAt")):
            raise ValueError("Foreign deletion receipt")
        try:
            self.api.request("GET", "/pods/" + pod["id"])
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
        try:
            cost = elapsed * (max(_number(pod.get("cost")), _number(intent["quote"]["hourly_rate_usd"])) + base.STORAGE) / 3600
            new = _number(intent["prior_new_usd"]) + cost
        except ValueError:
            cost, new = None, None
        return self.ledger.bind("closed", {"pod_id": pod["id"], "get_status": 404,
            "inventory_ids": sorted(p["id"] for p in inventory),
            "utc": _utc(self.clock()).isoformat(), "elapsed_seconds": str(elapsed),
            "compute_upper_bound_usd": None if cost is None else str(cost),
            "cumulative_upper_bound_usd": None if new is None else str(PRIOR_USD + new),
            "within_limits": (new is not None and elapsed <= self.hard_seconds
                              and new <= NEW_CAP_USD and PRIOR_USD + new <= TOTAL_USD)})

    def _audit_receipt(self, receipt, *, partial=True):
        data = receipt["data"]
        if self.event(receipt["id"]) != receipt or data["pod_id"] != self.owned()["id"]:
            raise ValueError("Audit requires an owned ledger-bound snapshot")
        root = Path(data["directory"])
        if not root.is_relative_to(self.base / "retrievals"):
            raise ValueError("Audit snapshot outside owned retrieval root")
        _no_symlinks(root)
        for name, digest in data["artifacts"].items():
            if PurePosixPath(name).is_absolute() or ".." in PurePosixPath(name).parts:
                raise ValueError("Unsafe audit artifact path")
            path = root / name
            _no_symlinks(path)
            if not path.is_file() or sha(path) != digest:
                raise ValueError("Audit snapshot missing/corrupt")
        if "receipts.jsonl" not in data["artifacts"]:
            raise ValueError("Audit requires a runtime receipt ledger")
        with (root / "receipts.jsonl").open("rb") as stream:
            binding = base.strict_json(stream.readline())
        if binding.get("plan_sha256") != self.plan_hash or binding.get("freeze_commit") != self.freeze:
            raise ValueError("Runtime receipt plan/freeze differs from controller")
        report = audit(root, self.plan, partial=partial)
        if not isinstance(report, dict) or report.get("pass") is not True:
            raise ValueError("Local snapshot audit did not pass")
        if any(sha(root / name) != digest for name, digest in data["artifacts"].items()):
            raise ValueError("Audit modified the retrieved evidence")
        self.record("live-audit", {"retrieval_sha256": receipt["sha256"], "report": report})
        return report

    def _verify_final(self):
        # Scientific invalidity is reportable, not a reason to keep billing a
        # stopped pod. Byte-integrity failures still forbid destructive cleanup.
        super()._verify_final()
        if self.kind != "main":
            return
        receipt = base.strict_json((self.base / "final-retrieval.json").read_bytes())
        existing = self.event("final-scientific-audit")
        if existing is not None:
            if existing["data"]["retrieval_sha256"] != receipt["sha256"]:
                raise ValueError("Final scientific audit belongs to another snapshot")
            return
        artifacts = receipt["data"]["artifacts"]
        result = {"retrieval_sha256": receipt["sha256"], "completion_claimed": "DONE-all.json" in artifacts,
                  "structural_pass": False, "status": "not_completed"}
        if not receipt["data"].get("no_worker_dispatched"):
            try:
                report = self._audit_receipt(receipt, partial=False)
                if "DONE-all.json" not in artifacts:
                    raise ValueError("No completed-worker marker")
                done = base.strict_json((Path(receipt["data"]["directory"]) / "DONE-all.json").read_bytes())
                if (done.get("pass") is not True or done.get("plan_sha256") != self.plan_hash
                        or done.get("freeze_commit") != self.freeze
                        or type(done.get("rows")) is not int or done["rows"] != report.get("rows")
                        or type(report.get("gates", {}).get("pass")) is not bool
                        or type(done.get("qualification_pass")) is not bool
                        or done["qualification_pass"] != report["gates"]["pass"]):
                    raise ValueError("Completion claim differs from full local audit")
                result.update(structural_pass=True, status="audited", report=report,
                              qualification_pass=report["gates"]["pass"])
            except Exception as exc:
                result.update(status="failed", error_type=type(exc).__name__)
        super()._verify_final()
        self.ledger.bind("final-scientific-audit", result)

    def _throughput_gate(self, receipt):
        data = receipt["data"]
        if "throughput-gate.json" not in data["artifacts"]:
            raise ValueError("First-five requires a retrieved throughput gate")
        root = Path(data["directory"])
        gate = base.strict_json((root / "throughput-gate.json").read_bytes())
        if (gate.get("pass") is not True or gate.get("plan_sha256") != self.plan_hash
                or gate.get("freeze_commit") != self.freeze):
            raise ValueError("Throughput gate must pass and bind the exact plan/freeze")
        for key, value in (("observed_forwards", 10), ("planned_forwards", 736),
                           ("overhead_factor", 2), ("reserve_seconds", 900)):
            if type(gate.get(key)) is not int or gate[key] != value:
                raise ValueError("Throughput inventory/reserve contract changed")
        mean = _number(gate.get("mean_seconds"))
        predicted = _number(gate.get("predicted_remaining_seconds"))
        timings = []
        for row in [r for r in self.plan["rows"] if r["split"] == "discovery"][:5]:
            source = base.strict_json((root / "rows" / (row["id"] + ".json")).read_bytes())
            timings.extend(_number(v["forward_and_readout_seconds"]) for v in source["clean"].values())
        if len(timings) != 10 or any(t <= 0 for t in timings) or mean <= 0:
            raise ValueError("Ten positive discovery-forward timings required")
        measured_mean = sum(timings) / 10
        expected = measured_mean * 726 * 2
        if (abs(mean - measured_mean) > max(Decimal("1e-9"), measured_mean * Decimal("1e-12"))
                or abs(predicted - expected) > max(Decimal("1e-6"), expected * Decimal("1e-12"))):
            raise ValueError("Throughput prediction differs from first-five measured timings")
        intent = self.event("create-intent")["data"]
        remaining = self.hard_seconds - RESERVE_SECONDS - self._elapsed(intent)
        if predicted + 900 >= remaining:
            raise ValueError("Throughput gate no longer fits the remaining worker deadline")
        self.record("throughput-approved", {"retrieval_sha256": receipt["sha256"],
                    "gate_sha256": data["artifacts"]["throughput-gate.json"],
                    "remaining_seconds": str(remaining), "predicted_remaining_seconds": str(predicted)})

    @transport.serialized
    def approve(self, name, plan_hash):
        if self.kind != "main" or name not in BARRIERS or plan_hash != self.plan_hash:
            raise ValueError("Explicit main-pod barrier and plan hash required")
        receipt = next((r for r in reversed(self.ledger.read()) if r["id"].startswith("retrieval:")
                        and "WAITING-" + name + ".json" in r["data"].get("artifacts", {})), None)
        if receipt is None:
            raise ValueError("Retrieve the barrier before local audit/approval")
        report = self._audit_receipt(receipt)
        expected = {"rows/qualification-live.json"}
        if name == "first-five":
            discovery = [row for row in self.plan["rows"] if row["split"] == "discovery"]
            if len(discovery) < 5:
                raise ValueError("Plan lacks five discovery pairs")
            expected.update("rows/" + row["id"] + ".json" for row in discovery[:5])
        if (type(report.get("rows")) is not int or report["rows"] != transport.BARRIER_ROWS[name]
                or not expected <= receipt["data"]["artifacts"].keys()):
            raise ValueError("Barrier needs the exact initial receipted pairs, not only a notice")
        if name == "first-five":
            self._throughput_gate(receipt)
        return super().approve(name, plan_hash)

    def _check_progress(self, files):
        elapsed = self._elapsed(self.event("create-intent")["data"])
        # Logs, credentials and heartbeats cannot disguise a stalled row writer.
        progress = {name: value for name, value in files.get("_progress", {}).items()
                    if name.startswith("rows/") or "/rows/" in name}
        previous = next((r["data"] for r in reversed(self.ledger.read())
                         if r["id"].startswith("scientific-progress:")), None)
        if progress and (previous is None or previous["files"] != progress):
            previous = {"files": progress, "elapsed_seconds": str(elapsed),
                        "utc": _utc(self.clock()).isoformat()}
            self.record("scientific-progress", previous)
        if previous is not None and not progress:
            raise ValueError("Scientific progress files disappeared")
        limit = 900 if previous else 1800
        changed = _number(previous["elapsed_seconds"]) if previous else Decimal(0)
        if elapsed - changed >= limit:
            raise ValueError("Owned worker stalled")

    def monitor(self):
        if not self.api.writable:
            raise ValueError("Explicit lifecycle mutation required")
        if any(self.event(n) for n in ("closing", "delete-intent", "closed")):
            return self.close_until_verified()
        self.owned()
        last_pull, failures, announced = float("-inf"), 0, None
        while True:
            try:
                self.cost_check(self.owned())
                state = self.status()
                self.cost_check(state["pod"])
                self.record("health", state)
                files = state["files"]
                if any(name in files for name in base.TERMINAL):
                    return self.close_until_verified()
                self._check_progress(files)
                waiting = tuple(name for name in BARRIERS if "WAITING-" + name + ".json" in files
                                and not self.event("approved:" + name))
                if waiting != announced or self.monotonic() - last_pull >= 600:
                    receipt = self.retrieve()
                    artifacts = receipt["data"]["artifacts"]
                    if self.kind == "main" and (waiting or "receipts.jsonl" in artifacts
                                                or any(name.startswith("rows/") for name in artifacts)):
                        self._audit_receipt(receipt)
                    if waiting:
                        print("WAITING: " + ", ".join(waiting) + "; explicit audited plan-hash approval required.", flush=True)
                    last_pull, announced = self.monotonic(), waiting
                failures = 0
            except (ValueError, KeyError, TypeError, ImportError) as exc:
                self.record("monitor-failed", {"error_type": type(exc).__name__})
                return self.close_until_verified()
            except (RuntimeError, OSError, subprocess.TimeoutExpired) as exc:
                failures += 1
                self.record("monitor-retry", {"error_type": type(exc).__name__, "count": failures})
                if failures >= 3:
                    return self.close_until_verified()
            except Exception as exc:
                self.record("monitor-failed", {"error_type": type(exc).__name__})
                return self.close_until_verified()
            self.sleep(60)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", required=True)
    parser.add_argument("--freeze", required=True)
    parser.add_argument("--kind", choices=("cheap", "main"), required=True)
    parser.add_argument("--action", choices=("preflight", "launch", "status", "monitor", "approve",
                                            "retrieve", "terminate", "reconcile"), default="preflight")
    parser.add_argument("--launch", action="store_true")
    parser.add_argument("--approved-new-cap-usd")
    parser.add_argument("--approval-ref")
    parser.add_argument("--approval-file")
    parser.add_argument("--barrier", choices=BARRIERS)
    parser.add_argument("--approve-plan-sha256")
    args = parser.parse_args(argv)
    if args.action in {"launch", "monitor", "approve", "retrieve", "terminate"} and not args.launch:
        parser.error("Mutating lifecycle actions require --launch")
    if args.action == "launch" and not all((args.approved_new_cap_usd, args.approval_ref, args.approval_file)):
        parser.error("Creation requires explicit cap, approval-ref and approval-file")
    if args.action == "approve" and not (args.barrier and args.approve_plan_sha256):
        parser.error("Barrier name and exact plan SHA required")
    if args.action != "approve" and (args.barrier or args.approve_plan_sha256):
        parser.error("Barrier arguments require --action approve")
    if args.action == "preflight":
        path = Path(args.plan).resolve()
        budget = checked_budget(load_plan(path, args.freeze))
        worker_script(args.kind, path.relative_to(ROOT).as_posix(), args.freeze, base.now().isoformat())
        print(json.dumps({"dry_run": True, "network_calls": 0, "creation_authorized": False,
                          "plan_sha256": sha(path), "budget": budget,
                          "maximum_main_usd": "13.78", "maximum_cheap_usd": "0.42",
                          "maximum_combined_usd": "14.20"}, sort_keys=True))
        return
    api = base.RunPodV2(os.environ.get("RUNPOD_API_KEY"), writable=args.launch)
    controller = Controller(args.plan, args.freeze, OWNED_OUT, args.kind, api, launch=args.launch,
                            approved_new_cap_usd=args.approved_new_cap_usd, approval_ref=args.approval_ref,
                            approval_file=args.approval_file)
    if args.action == "launch":
        controller.launch()
        result = controller.monitor()
    elif args.action == "approve":
        result = controller.approve(args.barrier, args.approve_plan_sha256)
    elif args.action == "terminate":
        result = controller.close_until_verified()
    else:
        result = getattr(controller, args.action)()
    print(json.dumps(result, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()

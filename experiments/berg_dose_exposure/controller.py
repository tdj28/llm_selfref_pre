"""One cheap CUDA pod and one main dose-exposure pod, with no replacements.

Reuse the frozen exposure snapshot/deletion lifecycle and corrected worker
reconciliation. This study retains a $50 cumulative cap, including the completed ladder and window costs. Remote timeout stops work, not provider billing: cleanup must
remain supervised until retrieval and direct deletion verification succeed.
"""
from __future__ import annotations

import argparse
from datetime import timedelta
from decimal import Decimal
import hashlib
import os
from pathlib import Path, PurePosixPath
import re
import shlex
import subprocess
import time
import uuid
import xml.etree.ElementTree as ET

from experiments.sae_assay_diagnostic import controller as base
from experiments.sae_assay_diagnostic.budget import EventLedger, PodRegistry, _canonical, _number, _utc
from experiments.sae_assay_exposure import controller as transport
from experiments.sae_assay_exposure_lifecycle_a1.controller import Controller as CorrectedLifecycle

ROOT = Path(__file__).resolve().parents[2]
PREFIX, NAMESPACE = "codex-dose-exposure-20261004-", "dose-exposure-controller"
PRIOR_USD, NEW_CAP_USD, TOTAL = "8.837266296602623", "38.32", "50"
MAIN_SECONDS, CHEAP_SECONDS, RESERVE_SECONDS = 19800, 1800, 600
STARTUP_STALL_SECONDS, SCIENTIFIC_STALL_SECONDS = 1800, 900
BUDGET = {"prior_usd": PRIOR_USD, "new_cap_usd": NEW_CAP_USD, "total_usd": TOTAL,
          "main_seconds": MAIN_SECONDS, "cheap_seconds": CHEAP_SECONDS,
          "reserve_seconds": RESERVE_SECONDS, "new_pro_calls": 0, "external_judge_calls": 0}
REMOTE, HF_ENV = transport.REMOTE, transport.HF_ENV
TESTS = ("tests/test_dose_exposure_backend.py", "tests/test_dose_exposure_runner.py")
BARRIER_ROWS = {"qualification": 1, "first-five": 18}
REQUIREMENTS = "experiments/sae_assay_diagnostic/requirements-gpu.txt"
SPARSE_CODE_ROOTS = ("experiments", "src", "tests")
SPARSE_REQUIRED_SOURCES = (
    REQUIREMENTS, *TESTS, "pytest.ini", "experiments/__init__.py", "tests/__init__.py",
    "src/__init__.py", "experiments/exp2_sae/__init__.py",
    "experiments/berg_ensemble_replication/__init__.py",
    "experiments/berg_ensemble_replication/protocol.py",
    "experiments/operator_matching_fine/__init__.py",
    "experiments/operator_matching_fine/protocol.py",
    "experiments/berg_dose_exposure/controller.py", "experiments/berg_dose_exposure/runner.py",
)


def canonical_root(root=ROOT):
    common = subprocess.check_output(
        ["git", "rev-parse", "--path-format=absolute", "--git-common-dir"], cwd=root, text=True).strip()
    common = Path(common).resolve()
    if common.name != ".git":
        raise ValueError("Expected a shared repository .git directory")
    return common.parent


OPERATIONAL_ROOT = canonical_root()
OWNED_OUT = OPERATIONAL_ROOT / "out/dose-exposure-20261004"


def load_plan(path, freeze):
    from . import protocol
    plan = protocol.load_plan(path, freeze)
    if _canonical(protocol.BUDGET) != _canonical(BUDGET) or _canonical(plan.get("budget")) != _canonical(BUDGET):
        raise ValueError("Dose-exposure budget contract changed")
    return plan


def audit(root, plan, *, settled=False):
    from . import analysis
    return analysis.audit(root, plan, partial=True, settled=settled)


def sparse_paths(relative, plan):
    sources, inputs = plan.get("source_hashes"), plan.get("input_hashes")
    if (not isinstance(sources, dict) or not isinstance(inputs, dict) or not inputs
            or not set(SPARSE_REQUIRED_SOURCES) <= sources.keys()):
        raise ValueError("Sparse checkout requires the complete bound runtime/test source closure")
    bindings = dict(sources)
    for name, digest in inputs.items():
        if name in bindings and bindings[name] != digest:
            raise ValueError("Conflicting sparse source/input binding")
        bindings[name] = digest
    if any(not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest)
           for digest in bindings.values()):
        raise ValueError("Sparse checkout requires exact source/input hashes")
    if any(not isinstance(name, str) for name in (*bindings, relative)):
        raise ValueError("Unsafe sparse checkout file path")
    paths = sorted({*bindings, relative})
    for name in paths:
        path = PurePosixPath(name)
        if (not re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_./-]*", name)
                or path.is_absolute() or path.as_posix() != name or ".." in path.parts
                or any(part.startswith(".") or part.lower() in {"out", "cache", "weights", "secrets"}
                       for part in path.parts)
                or path.suffix not in {".py", ".json", ".jsonl", ".csv", ".md", ".txt", ".ini", ".toml"}
                or ".env" in path.name.lower()):
            raise ValueError("Unsafe sparse checkout file path")
    # Keep the small code trees available for transitive imports, but never
    # broaden a source/input file into its surrounding released-data directory.
    return sorted(set(SPARSE_CODE_ROOTS) | {
        name for name in paths if PurePosixPath(name).parts[0] not in SPARSE_CODE_ROOTS})


def artifact_map(root):
    root = Path(root)
    if root.is_symlink() or not root.is_dir():
        raise ValueError("Invalid retrieval directory")
    result = {}
    for path in root.rglob("*"):
        if path.is_symlink():
            raise ValueError("Retrieval symlink")
        if path.is_file():
            result[path.relative_to(root).as_posix()] = base.sha(path)
    return result


def check_cuda_tests(path):
    cases = ET.parse(path).getroot().findall(".//testcase")
    if not cases or any(case.find(name) is not None for case in cases for name in ("failure", "error", "skipped")):
        raise ValueError("Cheap exact CUDA tests failed or skipped")
    for name in TESTS:
        if not any(case.get("classname", "").split(".")[-1] == Path(name).stem for case in cases):
            raise ValueError("Cheap exact CUDA test suite missing")


def worker_script(kind, relative, freeze, deadline, plan):
    path = PurePosixPath(relative)
    if (kind not in base.HARDWARE or not re.fullmatch(r"[0-9a-f]{40}", freeze)
            or path.is_absolute() or ".." in path.parts or path.as_posix() != relative
            or not relative.startswith("data/berg_dose_exposure/")
            or any(ord(c) < 32 for c in relative)):
        raise ValueError("Unsafe dose-exposure worker kind, freeze or plan path")
    _utc(deadline)
    paths = sparse_paths(relative, plan)
    bindings = {**plan["source_hashes"], **plan["input_hashes"],
                relative: hashlib.sha256(_canonical(plan) + b"\n").hexdigest()}
    check = ("import hashlib,pathlib; bindings=" + repr(bindings) + "; "
             "assert all(pathlib.Path(p).is_file() and not any(q.is_symlink() for q in "
             "(pathlib.Path(p),*pathlib.Path(p).parents)) for p in bindings), 'Sparse closure missing'; "
             "assert all(hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()==h "
             "for p,h in bindings.items()), 'Sparse closure hash mismatch'")
    python = REMOTE + "/venv/bin/python"
    validate = "from experiments.berg_dose_exposure.controller import load_plan; load_plan(" + repr(relative) + "," + repr(freeze) + ")"
    exit_code = "import json,sys; json.dump({'exit_code':int(sys.argv[1])},open(" + repr(REMOTE + "/out/controller-exit.json") + ",'x'))"
    if kind == "cheap":
        finish = ("from experiments.berg_dose_exposure.controller import check_cuda_tests; "
                  + "check_cuda_tests(" + repr(REMOTE + "/out/tests.xml") + "); import json; "
                  + "json.dump({'pass':True,'scope':'tiny_cuda_exact_path'},open("
                  + repr(REMOTE + "/out/DONE-all.json") + ",'x'))")
        work = ["export BERG_TEST_DEVICE=cuda HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1",
                shlex.join([python, "-c", "import torch; assert torch.cuda.is_available() and torch.cuda.is_bf16_supported()"]),
                shlex.join([python, "-m", "pytest", *TESTS, "-q", "--junitxml=" + REMOTE + "/out/tests.xml"]),
                shlex.join([python, "-c", finish])]
    else:
        work = [shlex.join([python, "-u", "-m", "experiments.berg_dose_exposure.runner",
                           "--plan", relative, "--freeze", freeze, "--out", REMOTE + "/out",
                           "--cache", "/workspace/cache", "--deadline-utc", deadline])]
    return "\n".join([
        "set -euC", "umask 077", "mkdir -p " + REMOTE + "/out",
        "trap 'rc=$?; rm -f " + HF_ENV + "; python3 -c "
        + shlex.quote(exit_code).replace("'", "'\"'\"'") + " \"$rc\"' EXIT",
        "git -c credential.helper= clone --filter=blob:none --no-checkout --single-branch --no-tags --depth=1 "
        + base.REPO + " " + REMOTE + "/repo",
        "cd " + REMOTE + "/repo", "git fetch --depth=1 origin " + freeze,
        shlex.join(["printf", r"%s\n", *("/" + name for name in paths)])
        + " | git sparse-checkout set --no-cone --stdin",
        "git checkout --detach " + freeze, 'test "$(git rev-parse HEAD)" = ' + freeze,
        shlex.join(["python3", "-c", check]),
        "python3 -m venv --system-site-packages " + REMOTE + "/venv",
        python + " -m pip install -r " + REQUIREMENTS,
        python + " -m pip freeze --all > " + REMOTE + "/out/pip-freeze.txt",
        shlex.join([python, "-c", validate]), "set +x; . " + HF_ENV + "; rm -f " + HF_ENV,
        "export HF_HOME=/workspace/cache PYTHONUNBUFFERED=1", *work])


class Controller(transport.Controller):
    signal_worker = CorrectedLifecycle.signal_worker

    def __init__(self, plan_path, freeze, out, kind, api, *, run=subprocess.run,
                 clock=base.now, sleep=time.sleep, monotonic=time.monotonic):
        if kind not in base.HARDWARE or not re.fullmatch(r"[0-9a-f]{40}", freeze):
            raise ValueError("Exact freeze and cheap/main required")
        self.plan_path, self.freeze, self.kind = Path(plan_path).resolve(), freeze, kind
        self.plan = load_plan(self.plan_path, freeze)
        self.plan_hash, self.relative = base.sha(self.plan_path), self.plan_path.relative_to(ROOT).as_posix()
        self.out = Path(out).absolute()
        if self.out != OWNED_OUT or self.out.resolve() != OWNED_OUT:
            raise ValueError("One canonical ledger root required; no spending reset")
        self.base = self.out / NAMESPACE / kind
        for directory in (self.base.parent, self.base):
            if directory.is_symlink():
                raise ValueError("Ledger symlink")
            directory.mkdir(parents=True, exist_ok=True, mode=0o700)
            directory.chmod(0o700)
        self.api, self.run, self.clock, self.sleep, self.monotonic = api, run, clock, sleep, monotonic
        self._wall0, self._mono0 = _utc(clock()), _number(monotonic())
        self._last_mono = self._mono0
        self.ledger = EventLedger(self.base / "events.jsonl", self.plan_hash, freeze, [])
        self._elapsed0 = max((_number(r["data"]["elapsed_seconds"]) for r in self.ledger.read()
                             if "elapsed_seconds" in r["data"]), default=Decimal(0))
        self.hard_seconds = MAIN_SECONDS if kind == "main" else CHEAP_SECONDS
        self.budget = self.plan["budget"]
        self.ledger.bind("controller:config", {"kind": kind, "namespace": NAMESPACE,
            "plan_path": self.relative, "budget": self.budget, "hard_seconds": self.hard_seconds})

    def _new_pod(self, pod, intent):
        return (re.fullmatch(re.escape(PREFIX) + self.kind + r"-[0-9a-f]{12}", intent["payload"].get("name", "")) is not None
                and intent.get("plan_sha256") == self.plan_hash and intent.get("freeze_commit") == self.freeze
                and base.Controller._new_pod(self, pod, intent))

    def cheap_receipt(self):
        directory = self.out / NAMESPACE / "cheap"
        if directory.is_symlink() or not (directory / "events.jsonl").is_file():
            raise ValueError("Cheap owned CUDA qualification required first")
        ledger = EventLedger(directory / "events.jsonl", self.plan_hash, self.freeze, [])
        rows = {e["id"]: e for e in ledger.read()}
        closed = rows.get("closed", {}).get("data", {})
        receipt_path = directory / "final-retrieval.json"
        if (closed.get("within_limits") is not True or closed.get("get_status") != 404
                or closed.get("pod_id") in closed.get("inventory_ids", [closed.get("pod_id")])
                or receipt_path.is_symlink() or not receipt_path.is_file()):
            raise ValueError("Cheap verified deletion required first")
        receipt = base.strict_json(receipt_path.read_bytes())
        if rows.get(receipt["id"]) != receipt or receipt["data"].get("pod_id") != closed["pod_id"]:
            raise ValueError("Cheap retrieval is not bound to its ledger and owned pod")
        saved = receipt["data"]
        root = Path(saved["directory"])
        if artifact_map(root) != saved["artifacts"]:
            raise ValueError("Cheap artifact inventory or hashes changed")
        if (base.strict_json((root / "DONE-all.json").read_bytes()) != {"pass": True, "scope": "tiny_cuda_exact_path"}
                or base.strict_json((root / "controller-exit.json").read_bytes()) != {"exit_code": 0}):
            raise ValueError("Cheap exact-path tests failed")
        check_cuda_tests(root / "tests.xml")
        return _number(closed["compute_upper_bound_usd"])

    @transport.serialized
    def launch(self):
        if not self.api.writable or self.event("create-intent"):
            raise ValueError("Fresh explicit creation only; no automatic replacement")
        if load_plan(self.plan_path, self.freeze) != self.plan or base.sha(self.plan_path) != self.plan_hash:
            raise ValueError("Plan changed since controller construction")
        sparse_paths(self.relative, self.plan)
        self.disk_check()
        prior_new = self.cheap_receipt() if self.kind == "main" else Decimal(0)
        token = os.environ.get("HF_TOKEN", "")
        if self.kind == "main" and (not token or any(c.isspace() for c in token)):
            raise ValueError("HF_TOKEN required and must be well formed before rental")
        if not base.KEY.expanduser().is_file():
            raise ValueError("Existing private SSH key missing")
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
        if full_cost > Decimal(NEW_CAP_USD) or Decimal(PRIOR_USD) + full_cost > Decimal(TOTAL):
            raise ValueError("Entire timer including retrieval is not funded")
        intent = {"payload": payload, "quote": quoted, "blocked": blocked, "created_utc": created.isoformat(),
            "deadline_utc": (created + timedelta(seconds=self.hard_seconds - RESERVE_SECONDS)).isoformat(),
            "hard_deadline_utc": (created + timedelta(seconds=self.hard_seconds)).isoformat(),
            "prior_new_usd": str(prior_new), "prior_total_usd": PRIOR_USD,
            "plan_sha256": self.plan_hash, "freeze_commit": self.freeze}
        self.ledger.transact("create-intent", lambda _: intent)
        self._wall0, self._mono0 = created, _number(self.monotonic())
        self._last_mono = self._mono0
        if not 0 <= (_utc(self.clock()) - created).total_seconds() <= 60:
            raise ValueError("Quote stale before creation; do not retry")
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
        gpu = pod.get("gpu", {})
        if (any(pod.get(k) != owned[k] for k in ("id", "name", "createdAt"))
                or not 0 < _number(pod.get("cost")) <= quote or not isinstance(gpu, dict)
                or gpu.get("id") != base.HARDWARE[self.kind][0]
                or type(gpu.get("count")) is not int or gpu["count"] != 1
                or _number(gpu.get("memory")) < base.HARDWARE[self.kind][2]
                or any(pod.get(k) != expected[k] for k in ("cloud", "image", "disk", "mounts", "ports"))):
            raise ValueError("Ownership/hardware/billing drift")
        seconds, mono = _number(horizon), _number(self.monotonic())
        last_wall = max([self._wall0, _utc(intent["created_utc"])] + [
            _utc(r["data"]["utc"]) for r in self.ledger.read() if "elapsed_seconds" in r["data"]])
        if _utc(self.clock()) < last_wall or mono < self._last_mono or seconds <= 0:
            raise ValueError("Accounting clock moved backward or invalid horizon")
        self._last_mono = mono
        elapsed, rate = self._elapsed(intent), quote + base.STORAGE
        projected = (elapsed + seconds + RESERVE_SECONDS) * rate / 3600
        new_cost = _number(intent["prior_new_usd"]) + projected
        cumulative = Decimal(PRIOR_USD) + new_cost
        self.record("accounting", {"utc": _utc(self.clock()).isoformat(), "elapsed_seconds": str(elapsed),
            "projected_usd": str(projected), "cumulative_projected_usd": str(cumulative)})
        if (elapsed + seconds >= self.hard_seconds - RESERVE_SECONDS
                or cumulative > Decimal(TOTAL) or new_cost > Decimal(NEW_CAP_USD)):
            raise ValueError("Budget or retrieval deadline reached")
        return elapsed * rate / 3600

    @transport.serialized
    def start_worker(self):
        if not self.api.writable or any(self.event(n) for n in ("worker-intent", "closing", "delete-intent", "closed")):
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
        self._ssh(pod, "set -euC; umask 077; mkdir -p " + REMOTE + "/out; cat > " + HF_ENV
                  + "; chmod 600 " + HF_ENV,
                  data=("export HF_TOKEN=" + shlex.quote(token) + "\n").encode())
        self.cost_check(pod)
        script = worker_script(self.kind, self.relative, self.freeze, intent["deadline_utc"], self.plan)
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

    def _verify_final(self):
        super()._verify_final()
        receipt = base.strict_json((self.base / "final-retrieval.json").read_bytes())["data"]
        if "directory" in receipt and artifact_map(receipt["directory"]) != receipt["artifacts"]:
            raise ValueError("Final artifact inventory changed")

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
        cost = elapsed * (max(_number(pod["cost"]), _number(intent["quote"]["hourly_rate_usd"])) + base.STORAGE) / 3600
        new_cost = _number(intent["prior_new_usd"]) + cost
        total = Decimal(PRIOR_USD) + new_cost
        return self.ledger.bind("closed", {"pod_id": pod["id"], "get_status": 404,
            "inventory_ids": sorted(p["id"] for p in inventory),
            "utc": _utc(self.clock()).isoformat(), "elapsed_seconds": str(elapsed),
            "compute_upper_bound_usd": str(cost), "cumulative_upper_bound_usd": str(total),
            "within_limits": elapsed <= self.hard_seconds and total <= Decimal(TOTAL)
                and new_cost <= Decimal(NEW_CAP_USD)})

    @transport.serialized
    def approve(self, name, plan_hash):
        if (not self.api.writable or name not in transport.BARRIERS or plan_hash != self.plan_hash
                or not self.event("worker-started")
                or any(self.event(n) for n in ("closing", "delete-intent", "closed"))):
            raise ValueError("Matching qualification/first-five approval required")
        filename = "WAITING-" + name + ".json"
        receipt = next((r for r in reversed(self.ledger.read()) if r["id"].startswith("retrieval:")
                        and filename in r["data"].get("artifacts", {})), None)
        if receipt is None:
            raise ValueError("Retrieve barrier before audit")
        root = Path(receipt["data"]["directory"])
        if artifact_map(root) != receipt["data"]["artifacts"]:
            raise ValueError("Barrier artifact inventory changed")
        report = audit(root, self.plan, settled=True)
        self.record("barrier-audit", {"barrier": name, "retrieval_sha256": receipt["sha256"], "report": report})
        if report.get("pass") is not True:
            raise ValueError("Barrier audit failed")
        if name == "first-five" and (report.get("generations") != 17 or report.get("zero_screen_pass") is not True):
            raise ValueError("Untreated screen and exactly five treated rows required")
        state = self.status()
        self.cost_check(state["pod"])
        barrier = state["files"].get(filename, {})
        if (barrier.get("plan_sha256") != self.plan_hash or barrier.get("freeze_commit") != self.freeze
                or barrier.get("barrier") != name or type(barrier.get("rows")) is not int
                or barrier["rows"] != BARRIER_ROWS[name]
                or any(n in state["files"] for n in base.TERMINAL)):
            raise ValueError("Matching exposure barrier is not live")
        if name == "first-five" and (not self.event("approved:qualification")
                or state["files"].get("_approvals", {}).get("APPROVE-qualification") != plan_hash):
            raise ValueError("Qualification must be explicitly approved before first-five")
        if base.strict_json((root/filename).read_bytes()) != barrier:
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

    def monitor(self):
        if not self.api.writable:
            raise ValueError("Explicit paid lifecycle required")
        if any(self.event(n) for n in ("closing", "delete-intent", "closed")):
            return self.close_until_verified()
        last_pull, failures = float("-inf"), 0
        previous, changed_at = None, self.monotonic()
        while True:
            try:
                self.cost_check(self.owned())
                state = self.status()
                self.cost_check(state["pod"])
                self.record("health", state)
                files = state["files"]
                if any(n in files for n in base.TERMINAL):
                    return self.close_until_verified()
                waiting = [n for n in transport.BARRIERS if "WAITING-" + n + ".json" in files
                           and not self.event("approved:" + n)]
                # Log/heartbeat churn is not scientific progress. Retain the
                # exposure startup/scientific limits without extending them on logs.
                progress = {name: value for name, value in files.get("_progress", {}).items()
                            if name.startswith("rows/") or name in
                            {"PLAN.json", "runtime.json", "zero_screen.json", "selection.json", "throughput.json"}}
                if progress != previous:
                    previous, changed_at = progress, self.monotonic()
                limit = (SCIENTIFIC_STALL_SECONDS if any(name.startswith("rows/") for name in progress)
                         else STARTUP_STALL_SECONDS)
                if not waiting and self.monotonic() - changed_at >= limit:
                    self.record("progress-stalled", {"limit_seconds": limit, "progress": progress})
                    return self.close_until_verified()
                if waiting or self.monotonic() - last_pull >= 600:
                    receipt = self.retrieve()["data"]
                    report = audit(Path(receipt["directory"]), self.plan)
                    self.record("live-audit", report)
                    if report.get("pass") is not True:
                        raise ValueError("Live structural audit failed")
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


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", required=True)
    parser.add_argument("--freeze", required=True)
    parser.add_argument("--kind", choices=("cheap", "main"), required=True)
    parser.add_argument("--action", choices=("launch", "status", "monitor", "terminate", "retrieve", "reconcile"), default="launch")
    parser.add_argument("--launch", action="store_true")
    parser.add_argument("--env-file", type=Path, default=OPERATIONAL_ROOT / ".env")
    args = parser.parse_args(argv)
    if not args.launch:
        load_plan(args.plan, args.freeze)
        print(_canonical({"dry_run": True, "network_calls": 0, "budget": BUDGET}).decode())
        return
    from dotenv import load_dotenv
    load_dotenv(args.env_file)
    api = base.RunPodV2(os.environ.get("RUNPOD_API_KEY"), writable=True)
    controller = Controller(args.plan, args.freeze, OWNED_OUT, args.kind, api)
    if args.action == "launch":
        controller.launch()
        result = controller.monitor()
    elif args.action == "terminate":
        result = controller.close_until_verified()
    else:
        result = getattr(controller, args.action)()
    print(_canonical(result).decode(), flush=True)


if __name__ == "__main__":
    main()

"""Qualification-only owned-pod lifecycle. Offline unless explicitly enabled.

GPU/storage time has a $14 envelope; the separate local judge ledger has $10,
including its $2 contingency. One further dollar remains reserved for retrieval
and extra storage. Neither unused API funds nor that reserve funds GPU time.
Creation requires a supplied, ignored user-approval record; this module never
writes that record or claims human review. Timeouts stop work, not billing.

The exposure remote paths/worker markers intentionally stay paired with its
audited snapshot and corrected process-identity helpers. Only newly created
pods in this study's namespace are accessible. No existing pod is adopted.

Integration contracts: raw_audit validates the generation ledger and rows;
analysis.analyze(raw_root, judge_root, plan, plan_hash, freeze,
n_blocks) recomputes the complete submitted decision from verified receipts.
Its decision includes api_spent_usd (including unresolved reservations),
providers, reason_codes, and the plan/freeze/block binding. A submitted decision
lives OUTSIDE judge_root, whose five permitted ledger files are hash-bound.
The controller's remote envelope additionally binds the exact raw snapshot.
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
import urllib.request
import uuid
import xml.etree.ElementTree as ET

from experiments.berg_ensemble_replication import controller as ensemble
from experiments.sae_assay_diagnostic import controller as base
from experiments.sae_assay_diagnostic.budget import EventLedger, PodRegistry, _canonical, _number, _utc
from experiments.sae_assay_exposure import controller as transport
from experiments.sae_assay_exposure_lifecycle_a1.controller import Controller as CorrectedLifecycle
from . import protocol

ROOT = protocol.ROOT
PREFIX = "codex-instruction-qualification-20261001-"
NAMESPACE = "instruction-qualification-controller"
OWNED_OUT = ROOT / "out/instruction-qualification-20261001"
PLAN_RELATIVE = "data/instruction_state_qualification/plan_20261001/PLAN.json"
REMOTE, HF_ENV = transport.REMOTE, transport.HF_ENV
PRIOR_USD, GPU_CAP_USD, API_CAP_USD = Decimal("69.130940"), Decimal("14"), Decimal("10")
NEW_CAP_USD, EXTRA_RESERVE_USD, TOTAL_USD = Decimal("25"), Decimal("1"), Decimal("200")
MAIN_SECONDS, CHEAP_SECONDS, RESERVE_SECONDS = 6600, 1200, 600
# This allowance covers both remaining local-judge waits. It is not a latency
# guarantee; the monitor terminates the owned pod if actual judging runs longer.
JUDGE_WAIT_SECONDS = 1200
# The runner currently protects another reserve inside its already-reduced
# deadline. Match that earlier work cutoff rather than claiming those seconds.
RUNNER_RESERVE_SECONDS = RESERVE_SECONDS
BUDGET = protocol.BUDGET
BARRIERS = ("qualification", "first-five")
LOOKS = {"look12": 12, "look20": 20}
BARRIER_ROWS = {"qualification": 1, "first-five": 6, "look12": 13, "look20": 21}
TESTS = tuple("tests/test_instruction_state_" + name + ".py" for name in
              ("backend", "runner", "protocol", "judges", "analysis", "controller"))
JUDGE_FILES = {".judge.lock", "snapshots.jsonl", "requests.jsonl", "attempts.jsonl", "judgments.jsonl"}
sha = base.sha
STATUS_SCRIPT = """import json,pathlib
r=pathlib.Path(%r); d={}
for n in %r:
 p=r/n
 if p.is_symlink(): raise ValueError('status evidence symlink')
 if p.is_file(): d[n]=json.loads(p.read_text())
d['_progress']={p.relative_to(r).as_posix():[p.stat().st_size,p.stat().st_mtime_ns]
 for p in r.rglob('*') if p.is_file() and not p.is_symlink()}
d['_approvals']={p.name:p.read_text().strip() for p in r.glob('APPROVE-*') if p.is_file()}
print(json.dumps(d))
""" % (REMOTE + "/out", [*("WAITING-" + n + ".json" for n in BARRIER_ROWS),
                             *("DECISION-" + n + ".json" for n in LOOKS), *base.TERMINAL])


def load_plan(path, freeze=None):
    from . import protocol
    return protocol.load_plan(path, freeze)


def audit(root, plan, plan_hash, freeze):
    from .raw_audit import raw_audit
    binding = base.strict_json((Path(root) / "receipts.jsonl").read_bytes().splitlines()[0])
    if binding.get("plan_sha256") != plan_hash or binding.get("freeze_commit") != freeze:
        raise ValueError("Raw receipt plan/freeze mismatch")
    return raw_audit(root, plan, partial=True)


def analyze(raw_root, judge_root, plan, plan_hash, freeze, n_blocks):
    from . import analysis
    return analysis.analyze(raw_root, judge_root, plan, plan_hash, freeze, n_blocks)


def checked_budget(plan):
    expected = {"prior_usd": "69.130940", "new_cap_usd": "25", "gpu_cap_usd": "14",
                "api_cap_usd": "10", "storage_reserve_usd": "1", "total_usd": "200",
                "main_seconds": 6600, "cheap_seconds": 1200, "reserve_seconds": 600,
                "new_pro_calls": 0}
    if _canonical(plan.get("budget")) != _canonical(expected) or BUDGET != expected:
        raise ValueError("Qualification budget contract missing or changed")
    return BUDGET.copy()


def _safe_path(relative):
    if relative != PLAN_RELATIVE:
        raise ValueError("Exact qualification plan path required")


def _no_symlinks(path):
    path = Path(path).absolute()
    if ".." in path.parts or any(p.is_symlink() for p in (path, *path.parents)):
        raise ValueError("Lifecycle paths cannot contain traversal or symlinks")


def verify_ci(freeze, *, opener=None):
    """Read-only public GitHub Actions verification before any rental."""
    if not re.fullmatch(r"[0-9a-f]{40}", freeze):
        raise ValueError("Exact CI commit required")
    opener = opener or urllib.request.build_opener(urllib.request.ProxyHandler({}), base.NoRedirect())
    prefix = "https://api.github.com/repos/tdj28/llm_selfref_pre/"

    def get(path):
        request = urllib.request.Request(prefix + path, headers={
            "Accept": "application/vnd.github+json", "User-Agent": "instruction-qualification/1.0"})
        with opener.open(request, timeout=30) as response:
            return base.strict_json(response.read())

    response = get("actions/workflows/verify.yml/runs?head_sha=" + freeze + "&per_page=100")
    runs = response.get("workflow_runs", [])
    if not runs or response.get("total_count") != len(runs):
        raise ValueError("Public CI inventory missing or truncated")
    for run in runs:
        if (run.get("head_sha") != freeze or run.get("status") != "completed"
                or run.get("conclusion") != "success" or type(run.get("id")) is not int):
            raise ValueError("Public CI has not passed on this exact freeze")
    latest = max(runs, key=lambda r: r["id"])
    result = get("actions/runs/" + str(latest["id"]) + "/jobs?per_page=100")
    jobs = result.get("jobs", [])
    required = {"Public release boundary"} | {
        label + " / Python " + version for label in
        ("Tests", "Current paper evidence", "Compile tracked sources") for version in ("3.10", "3.12")}
    if (result.get("total_count") != len(jobs) or not required <= {j.get("name") for j in jobs}
            or any(j.get("status") != "completed" or j.get("conclusion") != "success" for j in jobs)):
        raise ValueError("Required public tests/release checks missing or unsuccessful")
    return {"freeze_commit": freeze, "run_id": latest["id"], "jobs": len(jobs), "pass": True}


def _require_ignored(path):
    relative = Path(path).relative_to(ROOT).as_posix()
    result = subprocess.run(["git", "check-ignore", "--quiet", "--", relative], cwd=ROOT,
                            capture_output=True, timeout=10, env=base.local_env())
    if result.returncode:
        raise ValueError("Lifecycle and approval files must be ignored and untracked")


def approval_record(plan_hash, freeze, budget, approval_ref):
    """Return the required schema, not evidence of authorization."""
    checked_budget({"budget": budget})
    if (not re.fullmatch(r"[0-9a-f]{64}", plan_hash)
            or not re.fullmatch(r"[0-9a-f]{40}", freeze)
            or not isinstance(approval_ref, str)
            or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,159}", approval_ref)):
        raise ValueError("Exact plan, freeze and supplied user-request reference required")
    return {"scope": "instruction_state_qualification_only", "user_confirmed": True,
            "approval_ref": approval_ref, "approved_new_cap_usd": "25",
            "plan_sha256": plan_hash, "freeze_commit": freeze,
            "budget_sha256": hashlib.sha256(_canonical(budget)).hexdigest()}


def artifact_map(root):
    """Reject symlinks, nonregular inputs and untracked additions to snapshots."""
    root = Path(root)
    _no_symlinks(root)
    if not root.is_dir():
        raise ValueError("Artifact directory missing")
    files = {}
    for path in root.rglob("*"):
        if path.is_symlink() or not (path.is_dir() or path.is_file()):
            raise ValueError("Unsafe artifact type")
        if path.is_file():
            files[path.relative_to(root).as_posix()] = sha(path)
    return files


def sparse_paths():
    """Physical closure of the frozen runtime, verification and cheap tests."""
    paths = sorted(set(protocol.source_paths()) | {
        PLAN_RELATIVE, protocol.TOKEN_BINDINGS_PATH, protocol.PRIOR_BINDING_PATH,
        "data/causal_transplant/confirmatory_v1_20260709/manifest.json",
        ".gitignore", ".gitattributes", "pytest.ini"})
    if any(not re.fullmatch(r"[A-Za-z0-9_./-]+", p) or p.startswith("/")
           or ".." in PurePosixPath(p).parts for p in paths):
        raise ValueError("Sparse paths must be explicit repository-relative files")
    return paths


def sparse_checkout_commands(freeze):
    if not re.fullmatch(r"[0-9a-f]{40}", freeze):
        raise ValueError("Exact sparse-checkout commit required")
    paths = sparse_paths()
    physical_check = ("import pathlib,subprocess; paths=" + repr(paths) + "; "
                      + "assert all(pathlib.Path(p).is_file() and not pathlib.Path(p).is_symlink() "
                      + "for p in paths), 'Sparse runtime closure missing'; "
                      + "assert not subprocess.check_output(['git','status','--porcelain',"
                      + "'--untracked-files=no']), 'Tracked checkout changed'")
    patterns = shlex.join(["printf", "%s\n", *("/" + p for p in paths)])
    return [patterns + " | git sparse-checkout set --no-cone --stdin",
            "git checkout --detach " + freeze,
            'test "$(git rev-parse HEAD)" = ' + freeze,
            shlex.join(["python3", "-c", physical_check])]


def worker_script(kind, relative, freeze, deadline):
    if kind not in base.HARDWARE or not re.fullmatch(r"[0-9a-f]{40}", freeze):
        raise ValueError("Exact freeze and cheap/main required")
    _safe_path(relative)
    _utc(deadline)
    python = REMOTE + "/venv/bin/python"
    validate = ("from experiments.instruction_state_qualification.protocol import load_plan; load_plan("
                + repr(relative) + "," + repr(freeze) + ")")
    exit_code = ("import json,sys; json.dump({'exit_code':int(sys.argv[1])},open("
                 + repr(REMOTE + "/out/controller-exit.json") + ",'x'))")
    if kind == "cheap":
        work = ["export INSTRUCTION_TEST_DEVICE=cuda HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1",
                shlex.join([python, "-c", "import torch; assert torch.cuda.is_available(), 'CUDA required'"]),
                shlex.join([python, "-m", "pytest", *TESTS, "-q",
                            "--junitxml=" + REMOTE + "/out/tests.xml"]),
                shlex.join([python, "-c", "import json; json.dump({'pass':True,'scope':'tiny_cuda_exact_path'},open("
                            + repr(REMOTE + "/out/DONE-all.json") + ",'x'))"])]
    else:
        work = [shlex.join([python, "-u", "-m", "experiments.instruction_state_qualification.runner",
                            "--plan", relative, "--freeze", freeze, "--out", REMOTE + "/out",
                            "--cache", "/workspace/cache", "--deadline-utc", deadline])]
    return "\n".join([
        "set -euC", "umask 077", "mkdir -p " + REMOTE + "/out",
        "trap 'rc=$?; rm -f " + HF_ENV + "; python3 -c "
        + shlex.quote(exit_code).replace("'", "'\"'\"'") + " \"$rc\"' EXIT",
        "git -c credential.helper= clone --filter=blob:none --no-checkout --single-branch --no-tags --depth=1 "
        + base.REPO + " " + REMOTE + "/repo",
        "cd " + REMOTE + "/repo", "git fetch --depth=1 origin " + freeze,
        *sparse_checkout_commands(freeze),
        "python3 -m venv --system-site-packages " + REMOTE + "/venv",
        python + " -m pip install -r experiments/sae_assay_diagnostic/requirements-gpu.txt",
        python + " -m pip freeze --all > " + REMOTE + "/out/pip-freeze.txt",
        shlex.join([python, "-c", validate]), "set +x; . " + HF_ENV + "; rm -f " + HF_ENV,
        "export HF_HOME=/workspace/cache PYTHONUNBUFFERED=1", *work,
        'test -z "$(git status --porcelain --untracked-files=no)"'])


class Controller(transport.Controller):
    # These helpers use self for local paths/timers. Their remote paths and
    # exact process markers remain unchanged on uniquely owned fresh pods.
    signal_worker = CorrectedLifecycle.signal_worker
    close_until_verified = ensemble.Controller.close_until_verified

    def __init__(self, plan_path, freeze, out, kind, api, *, launch=False,
                 approved_new_cap_usd=None, approval_ref=None, approval_file=None,
                 run=subprocess.run, clock=base.now, sleep=time.sleep, monotonic=time.monotonic):
        if kind not in base.HARDWARE or not re.fullmatch(r"[0-9a-f]{40}", freeze):
            raise ValueError("Exact freeze and cheap/main required")
        self.plan_path, self.freeze, self.kind = Path(plan_path).resolve(), freeze, kind
        self.relative = self.plan_path.relative_to(ROOT).as_posix()
        _safe_path(self.relative)
        self.plan = load_plan(self.plan_path, freeze)
        self.budget, self.plan_hash = checked_budget(self.plan), sha(self.plan_path)
        self.out = Path(out).absolute()
        if self.out != OWNED_OUT:
            raise ValueError("One canonical ledger root required; no spending reset")
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
            raise ValueError("Creation requires --launch and --approved-new-cap-usd 25")
        expected = approval_record(self.plan_hash, self.freeze, self.budget, self.approval_ref)
        path = self.approval_file
        if path is None or not path.is_relative_to(self.out):
            raise ValueError("Existing approval file under canonical ignored output required")
        _no_symlinks(path)
        _require_ignored(path)
        if not path.is_file() or path.stat().st_size > 8192:
            raise ValueError("Missing or oversized approval file")
        raw = path.read_bytes()
        if _canonical(base.strict_json(raw)) != _canonical(expected):
            raise ValueError("Approval must bind user request, cap, plan and freeze")
        return {**expected, "approval_file_sha256": hashlib.sha256(raw).hexdigest(),
                "approval_file": path.relative_to(self.out).as_posix(),
                "authority": "supplied user-request reference; not human or Pro review"}

    def cheap_receipt(self):
        root = self.out / NAMESPACE / "cheap"
        _no_symlinks(root)
        if not (root / "events.jsonl").is_file():
            raise ValueError("Verified cheap gate required before main creation")
        ledger = EventLedger(root / "events.jsonl", self.plan_hash, self.freeze, [])
        events = {event["id"]: event for event in ledger.read()}
        closed = events.get("closed", {}).get("data", {})
        path = root / "final-retrieval.json"
        _no_symlinks(path)
        if closed.get("within_limits") is not True or closed.get("get_status") != 404 or not path.is_file():
            raise ValueError("Cheap pod must be retrieved and deletion verified")
        receipt = base.strict_json(path.read_bytes())
        if events.get(receipt.get("id")) != receipt:
            raise ValueError("Cheap receipt not bound to ledger")
        saved = receipt["data"]
        directory = Path(saved.get("directory", ""))
        if saved.get("pod_id") != closed.get("pod_id") or not directory.is_relative_to(root / "retrievals"):
            raise ValueError("Cheap receipt identity or path mismatch")
        if artifact_map(directory) != saved["artifacts"]:
            raise ValueError("Cheap artifact hash inventory changed")
        if not {"DONE-all.json", "tests.xml", "controller-exit.json"} <= saved["artifacts"].keys():
            raise ValueError("Cheap completion artifacts missing")
        if (base.strict_json((directory / "DONE-all.json").read_bytes()) !=
                {"pass": True, "scope": "tiny_cuda_exact_path"}
                or base.strict_json((directory / "controller-exit.json").read_bytes()) != {"exit_code": 0}):
            raise ValueError("Cheap exact-path tests failed")
        suites = list(ET.parse(directory / "tests.xml").iter("testsuite"))
        if (not suites or sum(int(s.get("tests", "0")) for s in suites) == 0
                or any(int(s.get(k, "0")) for s in suites for k in ("failures", "errors", "skipped"))):
            raise ValueError("Cheap tests must run without failures or skips")
        return _number(closed["compute_upper_bound_usd"])

    @transport.serialized
    def launch(self):
        if self.event("create-intent"):
            raise ValueError("Creation already attempted; reconcile only")
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
        ci = verify_ci(self.freeze)
        blocked = sorted({base.BLOCKED} | {p["id"] for p in self.api.inventory()})
        PodRegistry(self.ledger, blocked)
        offers = {kind: base.quote(self.api, kind) for kind in ("cheap", "main")}
        quoted = offers[self.kind]
        created = _utc(self.clock())
        rate = _number(quoted["hourly_rate_usd"]) + base.STORAGE
        full_cost = prior_new + rate * self.hard_seconds / 3600
        if self.kind == "cheap":
            full_cost += (_number(offers["main"]["hourly_rate_usd"]) + base.STORAGE) * MAIN_SECONDS / 3600
        if (full_cost > GPU_CAP_USD or full_cost + API_CAP_USD + EXTRA_RESERVE_USD > NEW_CAP_USD
                or PRIOR_USD + NEW_CAP_USD > TOTAL_USD):
            raise ValueError("Full GPU lifetimes and separate API/retrieval reserves are not funded")
        authority = self.ledger.bind("creation-approval", approval)
        intent = {"payload": payload, "quote": quoted, "blocked": blocked, "created_utc": created.isoformat(),
                  "deadline_utc": (created + timedelta(seconds=self.hard_seconds - RESERVE_SECONDS)).isoformat(),
                  "hard_deadline_utc": (created + timedelta(seconds=self.hard_seconds)).isoformat(),
                  "prior_new_usd": str(prior_new), "prior_total_usd": str(PRIOR_USD),
                  "plan_sha256": self.plan_hash, "freeze_commit": self.freeze,
                  "approval_sha256": authority["sha256"], "ci": ci, "offers": offers}
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
                    "projected_gpu_usd": str(new), "cumulative_gpu_upper_bound_usd": str(PRIOR_USD + new),
                    "api_accounting": "separate local ledger", "reserved_non_gpu_usd": "11"})
        if (elapsed + seconds >= self.hard_seconds - RESERVE_SECONDS or new > GPU_CAP_USD
                or new + API_CAP_USD + EXTRA_RESERVE_USD > NEW_CAP_USD
                or PRIOR_USD + new + API_CAP_USD + EXTRA_RESERVE_USD > TOTAL_USD):
            raise ValueError("GPU budget or retrieval deadline reached")
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
            "cumulative_gpu_upper_bound_usd": None if new is None else str(PRIOR_USD + new),
            "api_accounting": "separate local ledger; not included in this GPU receipt",
            "within_limits": (new is not None and elapsed <= self.hard_seconds and new <= GPU_CAP_USD
                              and new + API_CAP_USD + EXTRA_RESERVE_USD <= NEW_CAP_USD)})

    def status(self):
        pod = self.get_pod()
        files = {}
        if pod.get("status") == "RUNNING" and pod.get("ssh", {}).get("direct"):
            files = base.strict_json(self._ssh(pod, "python3 -c " + shlex.quote(STATUS_SCRIPT)))
        return {"pod": base.clean_pod(pod), "files": files}

    def _audit_receipt(self, receipt):
        data = receipt["data"]
        if self.event(receipt["id"]) != receipt or data.get("pod_id") != self.owned()["id"]:
            raise ValueError("Audit requires an owned ledger-bound snapshot")
        root = Path(data.get("directory", ""))
        if not root.is_relative_to(self.base / "retrievals") or artifact_map(root) != data["artifacts"]:
            raise ValueError("Snapshot missing, corrupt or outside owned retrieval root")
        report = audit(root, self.plan, self.plan_hash, self.freeze)
        if not isinstance(report, dict) or report.get("pass") is not True or type(report.get("rows")) is not int:
            raise ValueError("Local snapshot audit failed")
        if artifact_map(root) != data["artifacts"]:
            raise ValueError("Audit modified raw evidence")
        self.record("live-audit", {"retrieval_sha256": receipt["sha256"], "report": report})
        return report

    def _barrier(self, name):
        if (not self.api.writable or self.kind != "main" or name not in BARRIER_ROWS
                or not self.event("worker-started")
                or any(self.event(n) for n in ("closing", "delete-intent", "closed"))):
            raise ValueError("Live owned main worker required")
        state = self.status()
        self.cost_check(state["pod"])
        filename = "WAITING-" + name + ".json"
        barrier = state["files"].get(filename, {})
        if (barrier.get("plan_sha256") != self.plan_hash or barrier.get("freeze_commit") != self.freeze
                or barrier.get("barrier") != name or type(barrier.get("rows")) is not int
                or barrier["rows"] != BARRIER_ROWS[name]
                or any(n in state["files"] for n in base.TERMINAL)):
            raise ValueError("Matching barrier is not live")
        needed = () if name == "qualification" else ("qualification",)
        if name in LOOKS:
            needed += ("first-five",)
        if any(not self.event("approved:" + n) or state["files"].get("_approvals", {}).get("APPROVE-" + n)
               != self.plan_hash for n in needed):
            raise ValueError("Earlier structural barriers not approved")
        if name == "look20":
            previous = self.event("decision:look12")
            if (previous is None or previous["data"]["payload"]["decision"] != "extend"
                    or state["files"].get("DECISION-look12.json") != previous["data"]["payload"]):
                raise ValueError("Twenty-block look requires the audited twelve-block extension")
        receipt = next((r for r in reversed(self.ledger.read()) if r["id"].startswith("retrieval:")
                        and filename in r["data"].get("artifacts", {})), None)
        if receipt is None:
            raise ValueError("Retrieve a coherent barrier snapshot first")
        report = self._audit_receipt(receipt)
        if report["rows"] != BARRIER_ROWS[name]:
            raise ValueError("Barrier must contain the exact receipted row count")
        root = Path(receipt["data"]["directory"])
        qualification = base.strict_json((root / "rows/qualification-live.json").read_bytes())
        if qualification.get("result", {}).get("pass") is not True:
            raise ValueError("Live neutral qualification failed")
        if report.get("unresolved_generation_dispatches") or report.get("partial_generation_ids"):
            raise ValueError("Barrier includes incomplete generation dispatches")
        saved = base.strict_json((root / filename).read_bytes())
        if saved != barrier:
            raise ValueError("Live barrier differs from retrieved snapshot")
        return state, receipt

    def _write_remote(self, pod, filename, raw):
        script = ("import os,pathlib,sys; p=pathlib.Path(" + repr(REMOTE + "/out/" + filename)
                  + "); h=sys.stdin.buffer.read(); assert not p.is_symlink(); "
                  + "assert not p.exists() or p.read_bytes()==h; "
                  + "f=p.open('xb') if not p.exists() else None; "
                  + "f.write(h) if f else None; f.flush() if f else None; "
                  + "os.fsync(f.fileno()) if f else None; f.close() if f else None")
        self._ssh(pod, "umask 077; python3 -c " + shlex.quote(script), data=raw)

    @transport.serialized
    def approve(self, name, plan_hash):
        if name not in BARRIERS or plan_hash != self.plan_hash:
            raise ValueError("Only structural barriers accept explicit plan-hash approval")
        state, receipt = self._barrier(name)
        if name == "first-five":
            self._throughput_gate(receipt)
        self.ledger.bind("approval-intent:" + name, {"plan_sha256": plan_hash,
                         "retrieval_sha256": receipt["sha256"]})
        self._write_remote(state["pod"], "APPROVE-" + name, (plan_hash + "\n").encode())
        return self.ledger.bind("approved:" + name, {"plan_sha256": plan_hash})

    def _throughput_gate(self, receipt):
        """Account for billed startup and all remaining work, not tokens alone."""
        root = Path(receipt["data"]["directory"])
        blocks = self.plan.get("blocks", [])
        if len(blocks) != 20:
            raise ValueError("Throughput gate requires the complete 20-block maximum")
        timings = []
        for spec in blocks[:5]:
            name = "rows/" + spec["id"] + ".json"
            if name not in receipt["data"]["artifacts"]:
                raise ValueError("First-five throughput lacks raw block receipts")
            row = base.strict_json((root / name).read_bytes())
            generations = list(row["sources"].values()) + [r["generation"] for r in row["responses"]]
            if len(generations) != 6 or any(not isinstance(g, dict) for g in generations):
                raise ValueError("Thirty completed generation timings required before bulk")
            timings.extend(_number(g["elapsed_seconds"]) for g in generations)
        if len(timings) != 30 or any(t <= 0 for t in timings):
            raise ValueError("Missing/nonpositive measured generation times")
        elapsed = self._elapsed(self.event("create-intent")["data"])
        observed = sum(timings)
        if observed > elapsed + Decimal("1"):
            raise ValueError("Reported generation time exceeds billed wall time")
        remaining_generation = observed / 5 * 15
        remaining = Decimal("1.30") * (remaining_generation + JUDGE_WAIT_SECONDS)
        projected_lifetime = elapsed + remaining + RESERVE_SECONDS + RUNNER_RESERVE_SECONDS
        intent = self.event("create-intent")["data"]
        rate = _number(intent["quote"]["hourly_rate_usd"]) + base.STORAGE
        gpu = _number(intent["prior_new_usd"]) + projected_lifetime * rate / 3600
        report = {"retrieval_sha256": receipt["sha256"], "observed_generations": 30,
                  "maximum_blocks": 20, "billed_elapsed_seconds": str(elapsed),
                  "remaining_generation_seconds": str(remaining_generation),
                  "judge_wait_allowance_seconds": JUDGE_WAIT_SECONDS, "safety_factor": "1.30",
                  "retrieval_reserve_seconds": RESERVE_SECONDS,
                  "runner_internal_reserve_seconds": RUNNER_RESERVE_SECONDS,
                  "projected_lifetime_seconds": str(projected_lifetime),
                  "projected_gpu_usd": str(gpu),
                  "pass": projected_lifetime < self.hard_seconds and gpu <= GPU_CAP_USD}
        self.record("throughput-gate", report)
        if not report["pass"]:
            raise ValueError("Full twenty-block inventory plus judges and safety margin does not fit")
        return report

    def decision(self, name, path, *, judge_root=None):
        """Recompute locally WITHOUT holding the monitor's lifecycle lock.

The judger must also run outside this process. Expensive API calls never belong
here; the 60-second monitor can terminate an overdue pod during local analysis.
Only final live-barrier validation and the remote write are serialized.
"""
        if name not in LOOKS:
            raise ValueError("Only the prespecified 12/20-block looks accept decisions")
        path = Path(path).absolute()
        judge_root = Path(judge_root).absolute() if judge_root is not None else path.parent / "judges"
        for item in (path, judge_root):
            _no_symlinks(item)
            if not item.is_relative_to(self.out):
                raise ValueError("Local decision/judge inputs must be under canonical output")
            _require_ignored(item)
        if path.is_relative_to(judge_root):
            raise ValueError("Decision must be outside immutable judge inputs")
        submitted = base.strict_json(path.read_bytes())
        with self._exclusive():
            _, receipt = self._barrier(name)
        raw_root = Path(receipt["data"]["directory"])
        judges_before = artifact_map(judge_root)
        if not judges_before or not set(judges_before) <= JUDGE_FILES:
            raise ValueError("Unknown judge artifact; only the verified receipt ledgers are accepted")
        recomputed = analyze(raw_root, judge_root, self.plan, self.plan_hash, self.freeze, LOOKS[name])
        if (not isinstance(recomputed, dict) or _canonical(submitted) != _canonical(recomputed)
                or recomputed.get("plan_sha256") != self.plan_hash
                or recomputed.get("freeze_commit") != self.freeze
                or type(recomputed.get("n_blocks")) is not int or recomputed["n_blocks"] != LOOKS[name]
                or recomputed.get("decision") not in {"pass", "fail", "extend", "invalid", "incomplete"}
                or name == "look20" and recomputed["decision"] == "extend"
                or artifact_map(judge_root) != judges_before
                or not isinstance(recomputed.get("providers"), dict)
                or not isinstance(recomputed.get("reason_codes"), list)
                or any(not isinstance(x, str) for x in recomputed["reason_codes"])):
            raise ValueError("Decision or judge inventory differs from verified local recomputation")
        if recomputed["decision"] in {"pass", "fail", "extend"} and (
                set(recomputed["providers"]) != {"openai", "anthropic"}
                or _number(recomputed.get("api_spent_usd")) > API_CAP_USD):
            raise ValueError("Behavioral decision requires both providers within the separate API cap")
        if artifact_map(raw_root) != receipt["data"]["artifacts"]:
            raise ValueError("Analysis changed the raw snapshot")
        payload = {**recomputed, "source_snapshot_sha256": receipt["sha256"],
                   "source_artifacts": receipt["data"]["artifacts"],
                   "judge_artifacts": judges_before,
                   "judge_snapshot_sha256": hashlib.sha256(_canonical(judges_before)).hexdigest()}
        with self._exclusive():
            state, current = self._barrier(name)
            if current["data"]["artifacts"] != receipt["data"]["artifacts"]:
                raise ValueError("A different source snapshot arrived during analysis")
            if artifact_map(judge_root) != judges_before:
                raise ValueError("Judge inputs changed before decision dispatch")
            record = {"payload": payload, "submitted_sha256": sha(path),
                      "judge_root": judge_root.relative_to(self.out).as_posix()}
            self.ledger.bind("decision-intent:" + name, record)
            self._write_remote(state["pod"], "DECISION-" + name + ".json", _canonical(payload) + b"\n")
            return self.ledger.bind("decision:" + name, record)

    def _reconcile_decisions(self, files):
        for name in LOOKS:
            value = files.get("DECISION-" + name + ".json")
            if value is None:
                continue
            intent = self.event("decision-intent:" + name)
            if intent is None or intent["data"]["payload"] != value:
                raise ValueError("Remote decision lacks a matching audited local publication intent")
            self.ledger.bind("decision:" + name, intent["data"])

    def _verify_final(self):
        super()._verify_final()
        receipt = base.strict_json((self.base / "final-retrieval.json").read_bytes())
        data = receipt["data"]
        if data.get("no_worker_dispatched"):
            return
        root = Path(data["directory"])
        if (data.get("pod_id") != self.owned()["id"] or not root.is_relative_to(self.base / "retrievals")
                or artifact_map(root) != data["artifacts"]):
            raise ValueError("Final owned snapshot inventory mismatch")
        # Invalid scientific outcomes are retained, not a reason to keep billing.
        if self.kind == "main" and self.event("final-scientific-audit") is None:
            try:
                report = self._audit_receipt(receipt)
                result = {"status": "audited", "report": report}
            except Exception as exc:
                result = {"status": "failed", "error_type": type(exc).__name__}
            if artifact_map(root) != data["artifacts"]:
                raise ValueError("Final audit modified evidence")
            self.ledger.bind("final-scientific-audit", {"retrieval_sha256": receipt["sha256"], **result})

    def _waiting(self, files):
        waiting = []
        for name in BARRIER_ROWS:
            if "WAITING-" + name + ".json" not in files:
                continue
            if name in BARRIERS:
                released = (self.event("approved:" + name) is not None
                            and files.get("_approvals", {}).get("APPROVE-" + name) == self.plan_hash)
            else:
                event = self.event("decision:" + name)
                released = event is not None and files.get("DECISION-" + name + ".json") == event["data"]["payload"]
            if not released:
                waiting.append(name)
        return tuple(waiting)

    def monitor(self):
        if not self.api.writable:
            raise ValueError("Explicit lifecycle mutation required")
        if any(self.event(n) for n in ("closing", "delete-intent", "closed")):
            return self.close_until_verified()
        self.owned()
        previous, changed_at, last_pull, announced = None, self.monotonic(), float("-inf"), None
        failures = 0
        while True:
            try:
                self.cost_check(self.owned())
                state = self.status()
                self.cost_check(state["pod"])
                self.record("health", state)
                files = state["files"]
                self._reconcile_decisions(files)
                if any(name in files for name in base.TERMINAL):
                    return self.close_until_verified()
                waiting = self._waiting(files)
                progress = {k: v for k, v in files.get("_progress", {}).items() if k.startswith("rows/")}
                phase = (progress, waiting, tuple(n for n in LOOKS if "DECISION-" + n + ".json" in files))
                if phase != previous:
                    previous, changed_at = phase, self.monotonic()
                if not waiting and self.monotonic() - changed_at >= (900 if progress else 1800):
                    raise ValueError("Owned worker stalled outside a live barrier")
                if waiting != announced or self.monotonic() - last_pull >= 600:
                    receipt = self.retrieve()
                    if self.kind == "main" and (waiting or any(n.startswith("rows/") for n in receipt["data"]["artifacts"])):
                        self._audit_receipt(receipt)
                    if waiting != announced and waiting:
                        print("WAITING: " + ", ".join(waiting) + "; audit/decision required; GPU clock continues.", flush=True)
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
            except (Exception, KeyboardInterrupt) as exc:
                self.record("monitor-failed", {"error_type": type(exc).__name__})
                return self.close_until_verified()
            self.sleep(60)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", default=PLAN_RELATIVE)
    parser.add_argument("--freeze", required=True)
    parser.add_argument("--kind", choices=("cheap", "main"), required=True)
    parser.add_argument("--action", choices=("inspect", "create", "monitor", "retrieve", "status",
                                            "approve", "decision", "close", "reconcile"), default="inspect")
    parser.add_argument("--launch", action="store_true")
    parser.add_argument("--approved-new-cap-usd")
    parser.add_argument("--approval-ref")
    parser.add_argument("--approval-file")
    parser.add_argument("--barrier", choices=tuple(BARRIER_ROWS))
    parser.add_argument("--approve-plan-sha256")
    parser.add_argument("--decision-file")
    parser.add_argument("--judge-root")
    args = parser.parse_args(argv)
    if args.action != "inspect" and not args.launch:
        parser.error("All live lifecycle operations require --launch")
    if args.action == "create" and not all((args.approved_new_cap_usd, args.approval_ref, args.approval_file)):
        parser.error("Creation requires explicit cap, approval-ref and existing approval-file")
    if args.action == "approve" and not (args.barrier in BARRIERS and args.approve_plan_sha256):
        parser.error("Structural barrier and exact plan SHA required")
    if args.action == "decision" and not (args.barrier in LOOKS and args.decision_file and args.judge_root):
        parser.error("Look, decision-file and judge-root required")
    if args.action == "inspect":
        path = Path(args.plan).resolve()
        _safe_path(path.relative_to(ROOT).as_posix())
        budget = checked_budget(load_plan(path, args.freeze))
        worker_script(args.kind, PLAN_RELATIVE, args.freeze, base.now().isoformat())
        print(json.dumps({"dry_run": True, "network_calls": 0, "creation_authorized": False,
                          "plan_sha256": sha(path), "budget": budget}, sort_keys=True))
        return
    api = base.RunPodV2(os.environ.get("RUNPOD_API_KEY"), writable=args.launch)
    controller = Controller(args.plan, args.freeze, OWNED_OUT, args.kind, api, launch=args.launch,
                            approved_new_cap_usd=args.approved_new_cap_usd, approval_ref=args.approval_ref,
                            approval_file=args.approval_file)
    if args.action == "create":
        controller.launch()
        result = controller.monitor()
    elif args.action == "approve":
        result = controller.approve(args.barrier, args.approve_plan_sha256)
    elif args.action == "decision":
        result = controller.decision(args.barrier, args.decision_file, judge_root=args.judge_root)
    elif args.action == "close":
        result = controller.close_until_verified()
    else:
        result = getattr(controller, args.action)()
    print(json.dumps(result, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()

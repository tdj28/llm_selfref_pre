"""Fresh repair-pilot owned-pod lifecycle; inspect is offline, launch explicit.

Adapted from steering_fidelity.controller without changing historical modules.
The repair protocol binds ROOT, BUDGET, source_paths() and load_plan(path, freeze).
Its runner accepts --plan --freeze --out --cache --deadline-utc and waits at
WAITING-first-rows.json (5 forwards) and WAITING-throughput.json (20 forwards).
Each barrier binds barrier, forwards, plan_sha256 and freeze_commit; approval
files contain only the exact plan hash. The first 20 forwards are discovery
choices. Project their choice cost across all 520 possible forwards, with 30%
remaining-work headroom, plus a separate fixed 900-second decode allowance.

audit.audit_raw_window(root, plan, plan_hash, freeze, partial=True) returns
pass, forwards, forward_seconds and unresolved_forward_ids. All choice,
teacher-forced and generated rows live in forwards/. Conditional completion
belongs to that auditor, not an exactly-520 lifecycle check. No Stage T, API
judging or Pro dispatch exists here.

Transport paths remain paired with the shared snapshot/process helpers; names,
ledgers and approvals use a fresh repair namespace. Uncertain POSTs reconcile
read-only, never repeat; dispatched main work cannot be rerun. Work deadlines
are not provider spending caps: failed cleanup retains evidence and discloses
overruns until exact owned-pod deletion is verified.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import timedelta
from decimal import Decimal
import fcntl
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shlex
import stat
import subprocess
import time
import urllib.request
import uuid
import xml.etree.ElementTree as ET

from experiments.sae_assay_diagnostic import controller as base
from experiments.sae_assay_diagnostic.budget import EventLedger, PodRegistry, _canonical, _number, _utc
from experiments.sae_assay_exposure import controller as transport
from experiments.sae_assay_exposure_lifecycle_a1.controller import Controller as CorrectedLifecycle

ROOT = Path(__file__).resolve().parents[2]
NAMESPACE = "steering-fidelity-repair-20261003"
PREFIX = "codex-" + NAMESPACE + "-"
OWNED_OUT = ROOT / "out" / NAMESPACE
PLAN_RELATIVE = "data/steering_fidelity_repair/pilot_plan_20261003/PLAN.json"
REMOTE, HF_ENV = transport.REMOTE, transport.HF_ENV
PRIOR_USD, NEW_CAP_USD, TOTAL_USD = Decimal("9.657774"), Decimal("15"), Decimal("170")
GPU_CAP_USD, STORAGE_RESERVE_USD = Decimal("12"), Decimal("3")
MAIN_SECONDS, CHEAP_SECONDS, RESERVE_SECONDS = 4800, 1800, 600
MAX_FORWARDS, LIVENESS_RESERVED_SECONDS = 520, 900
STARTUP_STALL_SECONDS, FORWARD_STALL_SECONDS, BARRIER_WAIT_SECONDS = 900, 300, 600
BARRIERS = ("first-rows", "throughput")
BARRIER_FORWARDS = {"first-rows": 5, "throughput": 20}
BUDGET = {"prior_usd": "9.657774", "new_cap_usd": "15", "gpu_cap_usd": "12",
          "storage_reserve_usd": "3", "total_usd": "170", "api_cap_usd": "0",
          "main_seconds": 4800, "cheap_seconds": 1800, "reserve_seconds": 600,
          "new_paid_judge_calls": 0, "new_pro_calls": 0}
TESTS = tuple("tests/test_fidelity_repair_" + name + ".py" for name in
              ("items", "pressure_gate", "protocol", "runner", "audit", "controller", "liveness", "analysis")) + (
                  "tests/test_fidelity_position_probe.py", "tests/test_steering_fidelity_backend.py")
REQUIREMENTS = "experiments/sae_assay_diagnostic/requirements-gpu.txt"
sha = base.sha

# Physical import closure of the shared lifecycle, not historical outcomes.
LIFECYCLE_SOURCES = (
    "experiments/sae_assay_diagnostic/controller.py",
    "experiments/sae_assay_diagnostic/budget.py",
    "experiments/sae_assay_diagnostic/protocol.py",
    "experiments/sae_assay_diagnostic/fixtures.py",
    "experiments/sae_assay_replay/__init__.py",
    "experiments/sae_assay_replay/controller.py",
    "experiments/sae_assay_exposure/__init__.py",
    "experiments/sae_assay_exposure/controller.py",
    "experiments/sae_assay_exposure_lifecycle_a1/__init__.py",
    "experiments/sae_assay_exposure_lifecycle_a1/controller.py",
    "experiments/sae_assay_exposure_lifecycle_a1/protocol.py",
    "experiments/automated_rubric_audit/__init__.py",
    "experiments/automated_rubric_audit/common.py", "src/__init__.py", "src/prompts.py",
    REQUIREMENTS,
)

STATUS_SCRIPT = """import json,pathlib
r=pathlib.Path(%r); d={}
for n in %r:
 p=r/n
 if p.is_symlink(): raise ValueError('status symlink')
 if p.is_file(): d[n]=json.loads(p.read_text())
d['_progress']={}
for p in r.rglob('*'):
 if not p.is_file() or p.is_symlink(): continue
 name=p.relative_to(r).as_posix()
 if name.startswith(('rows/','forwards/','generations/','liveness/')):
  key=name.split('/')[0]+'/'
  item=d['_progress'].setdefault(key,{'files':0,'bytes':0})
  item['files']+=1; item['bytes']+=p.stat().st_size
 elif name in ('tests.xml','pip-freeze.txt','liveness.jsonl'):
  d['_progress'][name]=p.stat().st_size
d['_approvals']={}
for p in r.glob('APPROVE-*'):
 if p.is_symlink(): raise ValueError('approval symlink')
 if p.is_file(): d['_approvals'][p.name]=p.read_text().strip()
print(json.dumps(d))
""" % (REMOTE + "/out", [*("WAITING-" + n + ".json" for n in BARRIERS), *base.TERMINAL])


def load_plan(path, freeze=None):
    from . import protocol
    if Path(protocol.ROOT) != ROOT:
        raise ValueError("Protocol ROOT differs from lifecycle ROOT")
    plan = protocol.load_plan(path, freeze)
    if _canonical(plan.get("budget")) != _canonical(protocol.BUDGET):
        raise ValueError("Frozen budget differs from protocol")
    checked_budget(plan)
    counts = plan.get("counts", {})
    if (type(counts.get("calibration_forwards")) is not int
            or counts["calibration_forwards"] != MAX_FORWARDS
            or type(counts.get("liveness_reserved_seconds")) is not int
            or counts["liveness_reserved_seconds"] != LIVENESS_RESERVED_SECONDS):
        raise ValueError("Repair must budget 520 possible forwards and 900 decode seconds")
    bindings = plan.get("source_hashes", {})
    if not set(source_paths()) <= bindings.keys():
        raise ValueError("Frozen plan omits lifecycle or cheap-test source dependencies")
    for name in source_paths():
        _no_symlinks(ROOT / name)
        if sha(ROOT / name) != bindings[name]:
            raise ValueError("Lifecycle source binding differs: " + name)
    return plan


def checked_budget(plan):
    if _canonical(plan.get("budget")) != _canonical(BUDGET):
        raise ValueError("Repair must retain prior9.657774, GPU12/reserve3, cap15/global170 and no API/Pro")
    return dict(BUDGET)


def _safe_path(relative):
    if relative != PLAN_RELATIVE:
        raise ValueError("Exact repair pilot plan path required")


def _no_symlinks(path):
    path = Path(path).absolute()
    if ".." in path.parts or any(p.is_symlink() for p in (path, *path.parents)):
        raise ValueError("Lifecycle path contains traversal or symlinks")


def artifact_map(root):
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


def _require_ignored(path):
    result = subprocess.run(["git", "check-ignore", "--quiet", "--",
        Path(path).relative_to(ROOT).as_posix()], cwd=ROOT, capture_output=True,
        timeout=10, env=base.local_env())
    if result.returncode:
        raise ValueError("Lifecycle and approval files must be ignored and untracked")


def approval_record(plan_hash, freeze, budget, approval_ref, *, kind="cheap", attempt=1):
    """Schema for a supplied user authorization; this function does not write it."""
    checked_budget({"budget": budget})
    if (not re.fullmatch(r"[0-9a-f]{64}", plan_hash) or not re.fullmatch(r"[0-9a-f]{40}", freeze)
            or not isinstance(approval_ref, str)
            or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,159}", approval_ref)
            or kind not in base.HARDWARE or type(attempt) is not int or not 1 <= attempt <= 99):
        raise ValueError("Exact plan, freeze, attempt and user-request reference required")
    return {"scope": "steering_fidelity_repair_pilot_only", "user_confirmed": True,
            "approval_ref": approval_ref, "approved_new_cap_usd": "15", "global_cap_usd": "170",
            "kind": kind, "attempt": attempt, "plan_sha256": plan_hash, "freeze_commit": freeze,
            "budget_sha256": hashlib.sha256(_canonical(budget)).hexdigest()}


def verify_ci(freeze, *, opener=None):
    """Public exact-freeze CI gate; no qualification from another commit."""
    if not re.fullmatch(r"[0-9a-f]{40}", freeze):
        raise ValueError("Exact CI commit required")
    opener = opener or urllib.request.build_opener(urllib.request.ProxyHandler({}), base.NoRedirect())

    def get(path):
        request = urllib.request.Request("https://api.github.com/repos/tdj28/llm_selfref_pre/" + path,
            headers={"Accept": "application/vnd.github+json", "User-Agent": NAMESPACE})
        with opener.open(request, timeout=30) as response:
            return base.strict_json(response.read())

    result = get("actions/workflows/verify.yml/runs?head_sha=" + freeze + "&per_page=100")
    runs = result.get("workflow_runs", [])
    if (not runs or result.get("total_count") != len(runs)
            or any(r.get("head_sha") != freeze or r.get("status") != "completed"
                   or r.get("conclusion") != "success" or type(r.get("id")) is not int for r in runs)):
        raise ValueError("Public CI has not passed this exact freeze")
    latest = max(runs, key=lambda r: r["id"])
    result = get("actions/runs/" + str(latest["id"]) + "/jobs?per_page=100")
    jobs = result.get("jobs", [])
    required = {"Public release boundary"} | {label + " / Python " + version for label in
        ("Tests", "Current paper evidence", "Compile tracked sources") for version in ("3.10", "3.12")}
    if (result.get("total_count") != len(jobs) or not required <= {j.get("name") for j in jobs}
            or any(j.get("status") != "completed" or j.get("conclusion") != "success" for j in jobs)):
        raise ValueError("Required hosted checks missing or unsuccessful")
    return {"freeze_commit": freeze, "run_id": latest["id"], "jobs": len(jobs), "pass": True}


def source_paths():
    """Include this compact list in the fresh protocol's source closure."""
    return sorted({*LIFECYCLE_SOURCES, *TESTS, "experiments/steering_fidelity_repair/controller.py"})


def sparse_paths(plan):
    from . import protocol
    paths = sorted(set(protocol.source_paths()) | set(plan.get("input_hashes", {})) |
                   set(source_paths()) |
                   {PLAN_RELATIVE, ".gitignore", ".gitattributes", "pytest.ini", "tests/__init__.py"})
    for name in paths:
        path = PurePosixPath(name)
        if (not re.fullmatch(r"[A-Za-z0-9_./-]+", name) or path.is_absolute()
                or path.as_posix() != name or ".." in path.parts
                or (name not in {".gitignore", ".gitattributes"} and
                    (any(p.startswith(".") for p in path.parts) or
                     path.suffix not in {".py", ".json", ".jsonl", ".md", ".txt", ".ini", ".toml"}))
                or any(p.lower() in {"out", "cache", "weights", "secrets"} for p in path.parts)
                or ".env" in path.name.lower()):
            raise ValueError("Unsafe sparse payload: " + name)
    return paths


def worker_script(kind, relative, freeze, deadline, plan):
    if kind not in base.HARDWARE or not re.fullmatch(r"[0-9a-f]{40}", freeze):
        raise ValueError("Exact freeze and cheap/main required")
    _safe_path(relative)
    _utc(deadline)
    paths = sparse_paths(plan)
    python = REMOTE + "/venv/bin/python"
    check = ("import pathlib,subprocess; paths=" + repr(paths) + "; "
        "assert all(pathlib.Path(p).is_file() and not any(q.is_symlink() for q in "
        "(pathlib.Path(p),*pathlib.Path(p).parents)) for p in paths), 'Sparse closure missing'; "
        "assert not subprocess.check_output(['git','status','--porcelain','--untracked-files=no'])")
    validate = ("from experiments.steering_fidelity_repair.controller import load_plan; load_plan("
                + repr(relative) + "," + repr(freeze) + ")")
    exit_code = ("import json,sys; json.dump({'exit_code':int(sys.argv[1])},open("
                 + repr(REMOTE + "/out/controller-exit.json") + ",'x'))")
    if kind == "cheap":
        work = ["export BERG_TEST_DEVICE=cuda HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1",
            shlex.join([python, "-c", "import torch; assert torch.cuda.is_available() and torch.cuda.is_bf16_supported()"]),
            shlex.join([python, "-m", "pytest", *TESTS, "-q", "--junitxml=" + REMOTE + "/out/tests.xml"]),
            shlex.join([python, "-c", "import json; json.dump({'pass':True,'scope':'tiny_cuda_exact_path'},open("
                        + repr(REMOTE + "/out/DONE-all.json") + ",'x'))"])]
    else:
        work = [shlex.join([python, "-u", "-m", "experiments.steering_fidelity_repair.runner", "--plan", relative,
                           "--freeze", freeze, "--out", REMOTE + "/out", "--cache", "/workspace/cache",
                           "--deadline-utc", deadline])]
    return "\n".join(["set -euC", "umask 077", "mkdir -p " + REMOTE + "/out",
        "trap 'rc=$?; rm -f " + HF_ENV + "; python3 -c "
        + shlex.quote(exit_code).replace("'", "'\"'\"'") + " \"$rc\"' EXIT",
        "git -c credential.helper= clone --filter=blob:none --no-checkout --single-branch --no-tags --depth=1 "
        + base.REPO + " " + REMOTE + "/repo", "cd " + REMOTE + "/repo",
        "git fetch --depth=1 origin " + freeze,
        shlex.join(["printf", "%s\n", *("/" + p for p in paths)]) + " | git sparse-checkout set --no-cone --stdin",
        "git checkout --detach " + freeze, 'test "$(git rev-parse HEAD)" = ' + freeze,
        shlex.join(["python3", "-c", check]), "test -f " + REQUIREMENTS,
        "python3 -m venv --system-site-packages " + REMOTE + "/venv",
        python + " -m pip install -r " + REQUIREMENTS,
        python + " -m pip freeze --all > " + REMOTE + "/out/pip-freeze.txt",
        shlex.join([python, "-c", validate]), "set +x; . " + HF_ENV + "; rm -f " + HF_ENV,
        "export HF_HOME=/workspace/cache PYTHONUNBUFFERED=1", *work,
        'test -z "$(git status --porcelain --untracked-files=no)"'])


def budget_projection(gpu):
    gpu = _number(gpu)
    new = gpu + STORAGE_RESERVE_USD
    all_in = PRIOR_USD + new
    return {"projected_gpu_usd": str(gpu), "reserved_storage_retrieval_usd": str(STORAGE_RESERVE_USD),
            "prior_usd": str(PRIOR_USD), "projected_new_usd": str(new), "new_cap_usd": str(NEW_CAP_USD),
            "projected_all_in_usd": str(all_in), "global_cap_usd": str(TOTAL_USD),
            "pass": gpu <= GPU_CAP_USD and new <= NEW_CAP_USD and all_in <= TOTAL_USD}


def conservative_projection(timings, *, total_forwards, elapsed_seconds, hourly_usd,
                            prior_gpu_usd, liveness_reserved_seconds):
    values = [_number(t) for t in timings]
    elapsed, rate, prior = map(_number, (elapsed_seconds, hourly_usd, prior_gpu_usd))
    if (len(values) != BARRIER_FORWARDS["throughput"] or type(total_forwards) is not int
            or total_forwards != MAX_FORWARDS or any(t <= 0 for t in values)
            or type(liveness_reserved_seconds) is not int
            or liveness_reserved_seconds != LIVENESS_RESERVED_SECONDS
            or sum(values) > elapsed + Decimal("1")
            or not 0 < rate <= base.HARDWARE["main"][1] + base.STORAGE):
        raise ValueError("Complete 20-choice timing and fixed 520-forward accounting evidence required")
    # Only choice discovery has run at this barrier. Decode is not in these
    # timings; its fixed reserve is added once, including skipped-branch risk.
    unit = sum(values) / len(values)
    remaining = unit * (total_forwards - len(values))
    lifetime = elapsed + Decimal("1.30") * remaining + liveness_reserved_seconds + RESERVE_SECONDS
    result = budget_projection(prior + lifetime * rate / 3600)
    result.update(observed_forwards=len(values), total_forwards=total_forwards,
                  observed_forward_seconds=str(sum(values)), remaining_forward_seconds=str(remaining),
                  projected_full_forced_forward_seconds=str(sum(values) + remaining),
                  choice_mean_seconds=str(unit), projected_seconds_per_forward=str(unit),
                  projected_lifetime_seconds=str(lifetime), safety_factor="1.30",
                  liveness_reserved_seconds=liveness_reserved_seconds,
                  liveness_projection="fixed allowance; generation throughput not measured",
                  retrieval_reserve_seconds=RESERVE_SECONDS)
    result["pass"] = result["pass"] and lifetime < MAIN_SECONDS
    return result


def audit(root, plan, plan_hash, freeze):
    from .audit import audit_raw_window
    return audit_raw_window(root, plan, plan_hash, freeze, partial=True)


class Controller(transport.Controller):
    signal_worker = CorrectedLifecycle.signal_worker

    def __init__(self, plan_path, freeze, out, kind, api, *, launch=False, attempt=1,
                 approved_new_cap_usd=None, approval_ref=None, approval_file=None,
                 run=subprocess.run, clock=base.now, sleep=time.sleep, monotonic=time.monotonic):
        if (kind not in base.HARDWARE or not re.fullmatch(r"[0-9a-f]{40}", freeze)
                or type(attempt) is not int or not 1 <= attempt <= 99):
            raise ValueError("Exact freeze, cheap/main and positive bounded attempt required")
        _no_symlinks(plan_path)
        self.plan_path, self.freeze, self.kind = Path(plan_path).resolve(), freeze, kind
        self.relative = self.plan_path.relative_to(ROOT).as_posix()
        _safe_path(self.relative)
        self.plan = load_plan(self.plan_path, freeze)
        self.budget, self.plan_hash = checked_budget(self.plan), sha(self.plan_path)
        self.out = Path(out).absolute()
        if self.out != OWNED_OUT:
            raise ValueError("One canonical output ledger required; no spending reset")
        self.attempt, self.attempt_id = attempt, f"{kind}-{attempt:03d}"
        self.campaign_root = self.out / NAMESPACE
        self.base = self.campaign_root / self.attempt_id
        _no_symlinks(self.base)
        _require_ignored(self.base / "events.jsonl")
        for directory in (self.out, self.campaign_root, self.base):
            directory.mkdir(parents=True, exist_ok=True, mode=0o700)
            directory.chmod(0o700)
        self.api, self.run, self.clock, self.sleep, self.monotonic = api, run, clock, sleep, monotonic
        self.launch_enabled, self.approved_new_cap_usd = launch is True, approved_new_cap_usd
        self.approval_ref = approval_ref
        self.approval_file = Path(approval_file).absolute() if approval_file is not None else None
        self._wall0, self._mono0 = _utc(clock()), _number(monotonic())
        self._last_mono = self._mono0
        self.ledger = EventLedger(self.base / "events.jsonl", self.plan_hash, freeze, [])
        self.campaign = EventLedger(self.campaign_root / "budget.jsonl", self.plan_hash, freeze, [])
        self.campaign.bind("budget", self.budget)
        self._elapsed0 = max((_number(e["data"]["elapsed_seconds"]) for e in self.ledger.read()
                             if "elapsed_seconds" in e["data"]), default=Decimal(0))
        self.hard_seconds = MAIN_SECONDS if kind == "main" else CHEAP_SECONDS
        self.ledger.bind("controller:config", {"kind": kind, "attempt": attempt, "namespace": NAMESPACE,
            "plan_path": self.relative, "budget": self.budget, "hard_seconds": self.hard_seconds,
            "retrieval_seconds": RESERVE_SECONDS, "image": base.IMAGE})

    @contextmanager
    def _exclusive(self):
        # One cross-kind/attempt lock prevents two creators spending the same cap.
        if getattr(self, "_mutation_depth", 0):
            yield
            return
        fd = os.open(self.campaign_root / "lifecycle.lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        try:
            if not stat.S_ISREG(os.fstat(fd).st_mode):
                raise ValueError("Invalid lifecycle lock")
            fcntl.flock(fd, fcntl.LOCK_EX)
            self._mutation_depth = 1
            yield
        finally:
            self._mutation_depth = 0
            os.close(fd)

    def _new_pod(self, pod, intent):
        return (re.fullmatch(re.escape(PREFIX) + self.kind + r"-[0-9a-f]{12}",
                             intent["payload"].get("name", "")) is not None
                and intent.get("plan_sha256") == self.plan_hash and intent.get("freeze_commit") == self.freeze
                and base.Controller._new_pod(self, pod, intent))

    def _creation_approval(self):
        if not self.launch_enabled or not self.api.writable or _number(self.approved_new_cap_usd) != NEW_CAP_USD:
            raise ValueError("Creation requires --launch and --approved-new-cap-usd 15")
        expected = approval_record(self.plan_hash, self.freeze, self.budget, self.approval_ref,
                                   kind=self.kind, attempt=self.attempt)
        path = self.approval_file
        if path is None or not path.is_relative_to(self.out):
            raise ValueError("Existing ignored approval file required")
        _no_symlinks(path)
        _require_ignored(path)
        if not path.is_file() or path.stat().st_size > 8192:
            raise ValueError("Missing or oversized approval file")
        raw = path.read_bytes()
        if _canonical(base.strict_json(raw)) != _canonical(expected):
            raise ValueError("Approval must bind user request, attempt, cap, plan and freeze")
        return {**expected, "approval_file_sha256": hashlib.sha256(raw).hexdigest()}

    def _prior_attempts(self):
        prior, attempts = Decimal(0), []
        reservations = [e for e in self.campaign.read() if e["id"].startswith("attempt:")]
        for entry in reservations:
            identifier = entry["id"].removeprefix("attempt:")
            if not re.fullmatch(r"(?:cheap|main)-[0-9]{3}", identifier):
                raise ValueError("Malformed campaign attempt")
            path = self.campaign_root / identifier / "events.jsonl"
            _no_symlinks(path)
            if not path.is_file():
                raise ValueError("Unresolved attempt reservation; no new creation")
            events = {e["id"]: e for e in EventLedger(path, self.plan_hash, self.freeze, []).read()}
            closed, intent = events.get("closed", {}).get("data", {}), events.get("create-intent", {})
            if (not intent or intent["data"].get("campaign_reservation_sha256") != entry["sha256"]
                    or closed.get("get_status") != 404 or closed.get("within_limits") is not True
                    or closed.get("pod_id") != events.get("created", {}).get("data", {}).get("id")
                    or not events.get("delete-intent")):
                raise ValueError("Earlier attempt unresolved or over cap; no retry/adoption")
            cost = _number(closed.get("compute_upper_bound_usd"))
            if (_number(intent["data"]["prior_new_usd"]) != prior
                    or _number(intent["data"]["prior_total_usd"]) != PRIOR_USD
                    or _number(closed.get("cumulative_gpu_upper_bound_usd")) != prior + cost):
                raise ValueError("Prior failed-startup/attempt accounting differs")
            prior += cost
            attempts.append((identifier, events))
        previous = [e for name, e in attempts if name.startswith(self.kind + "-")]
        if self.attempt != len(previous) + 1:
            raise ValueError("Attempts must be sequential; no budget reset")
        if any(name.startswith("main-") and "worker-intent" in e for name, e in attempts):
            raise ValueError("Dispatched main repair pilot cannot be rerun by this adapter")
        if self.kind == "cheap" and any(name.startswith("main-") for name, _ in attempts):
            raise ValueError("Cannot return to cheap testing after main creation")
        return prior, attempts

    def cheap_receipt(self, attempts):
        cheap = [(name, events) for name, events in attempts if name.startswith("cheap-")]
        if not cheap:
            raise ValueError("Verified cheap CUDA gate required before main")
        name, events = cheap[-1]
        root = self.campaign_root / name
        _no_symlinks(root / "final-retrieval.json")
        receipt = base.strict_json((root / "final-retrieval.json").read_bytes())
        data, closed = receipt["data"], events["closed"]["data"]
        directory = Path(data.get("directory", ""))
        if (events.get(receipt.get("id")) != receipt or data.get("pod_id") != closed["pod_id"]
                or not directory.is_relative_to(root / "retrievals")
                or artifact_map(directory) != data["artifacts"]):
            raise ValueError("Cheap receipt inventory/ownership mismatch")
        if (base.strict_json((directory / "DONE-all.json").read_bytes()) !=
                {"pass": True, "scope": "tiny_cuda_exact_path"}
                or base.strict_json((directory / "controller-exit.json").read_bytes()) != {"exit_code": 0}):
            raise ValueError("Cheap CUDA test completion failed")
        suites = list(ET.parse(directory / "tests.xml").iter("testsuite"))
        if (not suites or sum(int(s.get("tests", "0")) for s in suites) <= 0
                or any(int(s.get(k, "0")) != 0 for s in suites for k in ("failures", "errors", "skipped"))):
            raise ValueError("Cheap tests must run without failures or skips")
        return receipt["sha256"]

    @transport.serialized
    def launch(self):
        if self.event("create-intent"):
            raise ValueError("Creation already attempted; reconcile only, never repeat POST")
        approval = self._creation_approval()
        if load_plan(self.plan_path, self.freeze) != self.plan or sha(self.plan_path) != self.plan_hash:
            raise ValueError("Plan changed since construction")
        for name in sparse_paths(self.plan):
            path = ROOT / name
            _no_symlinks(path)
            if not path.is_file():
                raise ValueError("Missing sparse dependency: " + name)
        worker_script(self.kind, self.relative, self.freeze, self.clock().isoformat(), self.plan)
        prior, attempts = self._prior_attempts()
        cheap = self.cheap_receipt(attempts) if self.kind == "main" else None
        token = os.environ.get("HF_TOKEN", "")
        if self.kind == "main" and (not token or any(c.isspace() for c in token)):
            raise ValueError("HF_TOKEN missing/malformed before rental")
        self.disk_check()
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
        full = prior + (_number(quoted["hourly_rate_usd"]) + base.STORAGE) * self.hard_seconds / 3600
        if self.kind == "cheap":
            full += (_number(offers["main"]["hourly_rate_usd"]) + base.STORAGE) * MAIN_SECONDS / 3600
        projection = budget_projection(full)
        if not projection["pass"]:
            raise ValueError("Failed attempts plus full cheap/main lifetimes exceed cap or reserves")
        authority = self.ledger.bind("creation-approval", approval)
        reservation = self.campaign.transact("attempt:" + self.attempt_id, lambda _: {
            "prior_gpu_usd": str(prior), "projection": projection, "approval_sha256": authority["sha256"]})
        created = _utc(self.clock())
        intent = {"payload": payload, "quote": quoted, "blocked": blocked, "created_utc": created.isoformat(),
            "deadline_utc": (created + timedelta(seconds=self.hard_seconds - RESERVE_SECONDS)).isoformat(),
            "hard_deadline_utc": (created + timedelta(seconds=self.hard_seconds)).isoformat(),
            "prior_new_usd": str(prior), "prior_total_usd": str(PRIOR_USD), "plan_sha256": self.plan_hash,
            "freeze_commit": self.freeze, "approval_sha256": authority["sha256"], "ci": ci,
            "cheap_receipt_sha256": cheap, "campaign_reservation_sha256": reservation["sha256"]}
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
        except (Exception, KeyboardInterrupt) as exc:
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
            _utc(e["data"]["utc"]) for e in self.ledger.read() if "elapsed_seconds" in e["data"]])
        if _utc(self.clock()) < last_wall or mono < self._last_mono or seconds <= 0:
            raise ValueError("Accounting clock moved backward or invalid horizon")
        self._last_mono = mono
        elapsed, rate = self._elapsed(intent), quote + base.STORAGE
        projection = budget_projection(_number(intent["prior_new_usd"]) +
                                       (elapsed + seconds + RESERVE_SECONDS) * rate / 3600)
        self.record("accounting", {"utc": _utc(self.clock()).isoformat(),
                                  "elapsed_seconds": str(elapsed), **projection})
        if elapsed + seconds >= self.hard_seconds - RESERVE_SECONDS or not projection["pass"]:
            raise ValueError("Repair budget or retrieval deadline reached")
        return elapsed * rate / 3600

    @transport.serialized
    def start_worker(self):
        if (not self.launch_enabled or not self.api.writable or not self.event("creation-approval")
                or any(self.event(n) for n in ("worker-intent", "closing", "delete-intent", "closed"))):
            raise ValueError("Worker disabled or already attempted")
        intent = self.event("create-intent")["data"]
        for _ in range(40):
            pod = self.get_pod()
            self.cost_check(pod, 60)
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
        script = worker_script(self.kind, self.relative, self.freeze, intent["deadline_utc"], self.plan)
        self.ledger.bind("credential-intent", {"path": HF_ENV})
        self._ssh(pod, "set -euC; umask 077; mkdir -p " + REMOTE + "/out; cat > " + HF_ENV,
                  data=("export HF_TOKEN=" + shlex.quote(token) + "\n").encode())
        self.cost_check(pod, 30)
        seconds = int(self.hard_seconds - RESERVE_SECONDS - self._elapsed(intent))
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
        cost, cumulative, within = None, None, False
        try:
            cost = elapsed * (max(_number(pod.get("cost")), _number(intent["quote"]["hourly_rate_usd"]))
                              + base.STORAGE) / 3600
            cumulative = _number(intent["prior_new_usd"]) + cost
            within = budget_projection(cumulative)["pass"] and elapsed <= self.hard_seconds
        except ValueError:
            pass
        return self.ledger.bind("closed", {"pod_id": pod["id"], "get_status": 404,
            "inventory_ids": sorted(p["id"] for p in inventory), "utc": _utc(self.clock()).isoformat(),
            "elapsed_seconds": str(elapsed), "compute_upper_bound_usd": None if cost is None else str(cost),
            "cumulative_gpu_upper_bound_usd": None if cumulative is None else str(cumulative),
            "new_all_in_upper_bound_usd": None if cumulative is None else str(cumulative + STORAGE_RESERVE_USD),
            "all_in_upper_bound_usd": None if cumulative is None else str(PRIOR_USD + cumulative + STORAGE_RESERVE_USD),
            "prior_total_usd": str(PRIOR_USD), "within_limits": within})

    def status(self):
        pod = self.get_pod()
        files = {}
        if pod.get("status") == "RUNNING" and pod.get("ssh", {}).get("direct"):
            files = base.strict_json(self._ssh(pod, "python3 -c " + shlex.quote(STATUS_SCRIPT)))
        return {"pod": base.clean_pod(pod), "files": files}

    def _audit_receipt(self, receipt):
        data = receipt["data"]
        root = Path(data.get("directory", ""))
        if (self.event(receipt["id"]) != receipt or data.get("pod_id") != self.owned()["id"]
                or not root.is_relative_to(self.base / "retrievals") or artifact_map(root) != data["artifacts"]):
            raise ValueError("Audit requires an intact owned ledger-bound snapshot")
        report = audit(root, self.plan, self.plan_hash, self.freeze)
        if (not isinstance(report, dict) or report.get("pass") is not True
                or type(report.get("forwards")) is not int or not 0 <= report["forwards"] <= MAX_FORWARDS
                or report.get("unresolved_forward_ids") != []
                or not isinstance(report.get("forward_seconds"), list)
                or len(report["forward_seconds"]) != report["forwards"]
                or any(_number(t) <= 0 for t in report["forward_seconds"])):
            raise ValueError("Local forward audit failed or incomplete")
        if artifact_map(root) != data["artifacts"]:
            raise ValueError("Audit modified raw evidence")
        self.record("live-audit", {"retrieval_sha256": receipt["sha256"], "report": report})
        return report

    @transport.serialized
    def approve(self, name, plan_hash):
        if (not self.api.writable or self.kind != "main" or name not in BARRIERS or plan_hash != self.plan_hash
                or not self.event("worker-started")
                or any(self.event(n) for n in ("closing", "delete-intent", "closed"))):
            raise ValueError("Exact plan hash and live owned main barrier required")
        state = self.status()
        self.cost_check(state["pod"])
        filename = "WAITING-" + name + ".json"
        barrier = state["files"].get(filename, {})
        if (barrier.get("plan_sha256") != self.plan_hash or barrier.get("freeze_commit") != self.freeze
                or barrier.get("barrier") != name or type(barrier.get("forwards")) is not int
                or barrier["forwards"] != BARRIER_FORWARDS[name]
                or any(n in state["files"] for n in base.TERMINAL)):
            raise ValueError("Matching fixed forward barrier not live")
        if name == "throughput" and (not self.event("approved:first-rows")
                or state["files"].get("_approvals", {}).get("APPROVE-first-rows") != self.plan_hash):
            raise ValueError("Initial real rows barrier has not been approved")
        receipt = next((e for e in reversed(self.ledger.read()) if e["id"].startswith("retrieval:")
                        and filename in e["data"].get("artifacts", {})), None)
        if receipt is None:
            raise ValueError("Retrieve barrier snapshot before approval")
        report = self._audit_receipt(receipt)
        if (report["forwards"] != BARRIER_FORWARDS[name] or
                base.strict_json((Path(receipt["data"]["directory"]) / filename).read_bytes()) != barrier):
            raise ValueError("Live/retrieved/audited barrier differs")
        if name == "throughput":
            intent = self.event("create-intent")["data"]
            projection = conservative_projection(report["forward_seconds"],
                total_forwards=self.plan.get("counts", {}).get("calibration_forwards"),
                liveness_reserved_seconds=self.plan.get("counts", {}).get("liveness_reserved_seconds"),
                elapsed_seconds=self._elapsed(intent),
                hourly_usd=_number(intent["quote"]["hourly_rate_usd"]) + base.STORAGE,
                prior_gpu_usd=intent["prior_new_usd"])
            self.record("throughput-gate", {**projection, "retrieval_sha256": receipt["sha256"]})
            if not projection["pass"]:
                raise ValueError("Full repair pilot no longer fits measured time/budget")
        if any(e["id"].startswith("throughput-gate:") and not e["data"]["pass"] for e in self.ledger.read()):
            raise ValueError("Failed throughput gate is permanent for this run")
        self.cost_check(state["pod"])
        self.ledger.bind("approval-intent:" + name, {"plan_sha256": plan_hash,
                         "retrieval_sha256": receipt["sha256"]})
        script = ("import os,pathlib,sys; p=pathlib.Path(" + repr(REMOTE + "/out/APPROVE-" + name)
            + "); h=sys.stdin.buffer.read(); assert not p.is_symlink(); "
            "assert not p.exists() or p.read_bytes()==h; f=p.open('xb') if not p.exists() else None; "
            "f.write(h) if f else None; f.flush() if f else None; "
            "os.fsync(f.fileno()) if f else None; f.close() if f else None")
        self._ssh(state["pod"], "umask 077; python3 -c " + shlex.quote(script), data=(plan_hash + "\n").encode())
        return self.ledger.bind("approved:" + name, {"plan_sha256": plan_hash})

    def _verify_final(self):
        _no_symlinks(self.base / "final-retrieval.json")
        super()._verify_final()
        receipt = base.strict_json((self.base / "final-retrieval.json").read_bytes())
        data = receipt["data"]
        if data.get("pod_id") != self.owned()["id"]:
            raise ValueError("Final retrieval belongs to another pod")
        if data.get("no_worker_dispatched"):
            if self.event("worker-intent") or data.get("artifacts") != {}:
                raise ValueError("Cannot omit a dispatched worker's evidence")
            return
        root = Path(data.get("directory", ""))
        if not root.is_relative_to(self.base / "retrievals") or artifact_map(root) != data["artifacts"]:
            raise ValueError("Final snapshot inventory changed")
        if self.kind == "main" and self.event("final-structural-audit") is None:
            try:
                result = {"status": "audited", "report": self._audit_receipt(receipt)}
            except Exception as exc:
                result = {"status": "failed", "error_type": type(exc).__name__}
            if artifact_map(root) != data["artifacts"]:
                raise ValueError("Final audit modified evidence")
            self.ledger.bind("final-structural-audit", {"retrieval_sha256": receipt["sha256"], **result})

    def close_until_verified(self):
        if not self.api.writable:
            raise ValueError("Explicit lifecycle mutation required for cleanup")
        self.owned()
        while True:
            try:
                return self.terminate()
            except (RuntimeError, ValueError, OSError, subprocess.TimeoutExpired) as exc:
                elapsed = self._elapsed(self.event("create-intent")["data"])
                self.record("cleanup-retry", {"error_type": type(exc).__name__,
                    "utc": _utc(self.clock()).isoformat(), "elapsed_seconds": str(elapsed),
                    "hard_deadline_exceeded": elapsed >= self.hard_seconds})
                print("ATTENTION: owned pod cleanup unresolved; evidence retained; no repeated DELETE."
                      + (" Hard deadline exceeded; user action required." if elapsed >= self.hard_seconds else ""), flush=True)
                self.sleep(15)

    def _waiting(self, files):
        return tuple(n for n in BARRIERS if "WAITING-" + n + ".json" in files
                     and not (self.event("approved:" + n) and
                              files.get("_approvals", {}).get("APPROVE-" + n) == self.plan_hash))

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
                if any(e["id"].startswith("throughput-gate:") and not e["data"]["pass"] for e in self.ledger.read()):
                    return self.close_until_verified()
                self.cost_check(self.owned())
                state = self.status()
                self.cost_check(state["pod"])
                self.record("health", state)
                files = state["files"]
                if any(n in files for n in base.TERMINAL):
                    return self.close_until_verified()
                waiting, progress = self._waiting(files), files.get("_progress", {})
                # Heartbeat timestamps/log chatter cannot prolong a stuck barrier.
                phase = waiting if waiting else progress
                if phase != previous:
                    previous, changed_at = phase, self.monotonic()
                limit = BARRIER_WAIT_SECONDS if waiting else (
                    FORWARD_STALL_SECONDS if any(n.startswith(("rows/", "forwards/", "generations/", "liveness/"))
                                                or n == "liveness.jsonl" for n in progress)
                    else STARTUP_STALL_SECONDS)
                if self.monotonic() - changed_at >= limit:
                    raise ValueError("Owned worker startup/progress/barrier deadline reached")
                if waiting != announced or self.monotonic() - last_pull >= 600:
                    receipt = self.retrieve()
                    if self.kind == "main" and waiting:
                        self._audit_receipt(receipt)
                    if waiting and waiting != announced:
                        print("WAITING: " + ", ".join(waiting) + "; explicit structural approval required.", flush=True)
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
            self.sleep(30)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", default=PLAN_RELATIVE)
    parser.add_argument("--freeze", required=True)
    parser.add_argument("--kind", choices=("cheap", "main"), required=True)
    parser.add_argument("--attempt", type=int, default=1)
    parser.add_argument("--action", choices=("inspect", "create", "monitor", "retrieve", "status", "approve", "close", "reconcile"), default="inspect")
    parser.add_argument("--launch", action="store_true")
    parser.add_argument("--approved-new-cap-usd")
    parser.add_argument("--approval-ref")
    parser.add_argument("--approval-file")
    parser.add_argument("--barrier", choices=BARRIERS)
    parser.add_argument("--approve-plan-sha256")
    args = parser.parse_args(argv)
    if args.action != "inspect" and not args.launch:
        parser.error("Live lifecycle operations require --launch")
    if args.action == "create" and not all((args.approved_new_cap_usd, args.approval_ref, args.approval_file)):
        parser.error("Creation requires explicit cap and existing approval record")
    if args.action == "approve" and not (args.barrier and args.approve_plan_sha256):
        parser.error("Barrier and exact plan hash required")
    if args.action == "inspect":
        path = Path(args.plan).absolute()
        _no_symlinks(path)
        _safe_path(path.relative_to(ROOT).as_posix())
        plan = load_plan(path, args.freeze)
        worker_script(args.kind, PLAN_RELATIVE, args.freeze, base.now().isoformat(), plan)
        print(json.dumps({"dry_run": True, "network_calls": 0, "creation_authorized": False,
            "plan_sha256": sha(path), "budget": checked_budget(plan), "source_paths": sparse_paths(plan)}, sort_keys=True))
        return
    api = base.RunPodV2(os.environ.get("RUNPOD_API_KEY"), writable=True)
    ctrl = Controller(args.plan, args.freeze, OWNED_OUT, args.kind, api, launch=True, attempt=args.attempt,
        approved_new_cap_usd=args.approved_new_cap_usd, approval_ref=args.approval_ref, approval_file=args.approval_file)
    if args.action == "create":
        ctrl.launch()
        result = ctrl.monitor()
    elif args.action == "approve":
        result = ctrl.approve(args.barrier, args.approve_plan_sha256)
    elif args.action == "close":
        result = ctrl.close_until_verified()
    else:
        result = getattr(ctrl, args.action)()
    print(json.dumps(result, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()

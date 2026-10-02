"""Owned-pod lifecycle for the frozen bilingual pilot; offline by default.

No scientific decisions or judging happen here. The two structural barriers
release the frozen twenty-block run, not an outcome-dependent extension.
The $50 contingency is reserved and cannot increase this controller's $45 GPU
envelope. A new explicit accounting amendment is needed to allocate it.

Parent contracts: protocol.ROOT, BUDGET, source_paths(), load_plan(path, freeze);
raw_audit.audit_raw_window(root, plan); runner accepts --plan,
--freeze, --out, --cache and --deadline-utc. Audits return pass, rows,
generations, blocked_cells, production_eligible, partial_generation_ids and
unresolved_generation_dispatches. Sparse checkout includes TOKEN_BINDINGS_PATH
and PRIOR_BINDING_PATH; blocks expose sources/cells with IDs and the plan pins
counts.generation_calls=760. Judges supply Ledger, RECEIPT_FILES, MODELS,
INSTRUMENTS, canonical, judge_config, fixture_inventory, validate_receipts,
_require_healthy, fixture_gate and project_budget (all used read-only here).
Generation artifacts live at generations/<id>.json and contain elapsed_seconds.
Fixtures are frozen, then judged after public CI and before the main rental.
The fixture proof binds plan/freeze/inventory and all judge receipt hashes.
Verification replays the canonical judge ledger read-only; a self-attested pass
is insufficient. Its all-remaining-calls judge budget projection must also pass.
Only the lifecycle ledger binds the resulting proof hash. Proof helpers run
after the judge writer releases its exclusive lock, never inside its context.

Private remote paths and process markers intentionally match the shared,
corrected transport helpers. They exist only on newly created, uniquely named
pods; study ownership and local ledgers use the bilingual namespace exclusively.
Timeout stops work, not billing. Cleanup retries until retrieval/hash/GET404
verification succeeds and reports an overrun rather than pretending a hard cap.
"""
from __future__ import annotations

import argparse
from datetime import timedelta
from decimal import Decimal
import fcntl
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shlex
import subprocess
import time
import uuid
import xml.etree.ElementTree as ET

from experiments.instruction_state_qualification import controller as qualification
from experiments.sae_assay_diagnostic import controller as base
from experiments.sae_assay_diagnostic.budget import EventLedger, PodRegistry, _canonical, _number, _utc
from experiments.sae_assay_exposure import controller as transport
from . import protocol

ROOT = Path(__file__).resolve().parents[2]
PREFIX = "codex-bilingual-llama-pilot-20261001-"
NAMESPACE = "bilingual-llama-pilot"
OWNED_OUT = ROOT / "out/bilingual-llama-pilot-20261001"
PLAN_RELATIVE = "data/bilingual_llama_pilot/plan_20261001/PLAN.json"
REMOTE, HF_ENV = transport.REMOTE, transport.HF_ENV
PRIOR_USD, NEW_CAP_USD, TOTAL_USD = Decimal("0"), Decimal("200"), Decimal("200")
GPU_CAP_USD, API_CAP_USD = Decimal("45"), Decimal("90")
TRANSLATION_QA_STORAGE_USD, CONTINGENCY_USD = Decimal("15"), Decimal("50")
MAIN_SECONDS, CHEAP_SECONDS, RESERVE_SECONDS = 18000, 1800, 600
# DurableStudy.check_time protects this inside the controller-reduced deadline.
RUNNER_RESERVE_SECONDS = RESERVE_SECONDS
TOTAL_GENERATIONS, BLOCKS = 760, 20
BUDGET = protocol.BUDGET.copy()
BARRIERS = ("qualification", "first-two")
BARRIER_ROWS = {"qualification": 1, "first-two": 3}
TESTS = tuple("tests/test_bilingual_" + name + ".py" for name in
              ("prompts", "protocol", "runner", "raw_audit", "judges", "controller", "analysis", "release")) + (
                  "tests/test_instruction_state_backend.py",)
sha = base.sha
_no_symlinks = qualification._no_symlinks
artifact_map = qualification.artifact_map
verify_ci = qualification.verify_ci
STATUS_SCRIPT = """import json,pathlib
r=pathlib.Path(%r); d={}
for n in %r:
 p=r/n
 if p.is_symlink(): raise ValueError('status evidence symlink')
 if p.is_file(): d[n]=json.loads(p.read_text())
d['_progress']={p.relative_to(r).as_posix():[p.stat().st_size,p.stat().st_mtime_ns]
 for p in r.rglob('*') if p.is_file() and not p.is_symlink()
 and (p.relative_to(r).as_posix().startswith(('rows/','generations/','_progress'))
      or p.name in ('receipts.jsonl','progress.json'))}
d['_approvals']={}
for p in r.glob('APPROVE-*'):
 if p.is_symlink(): raise ValueError('approval symlink')
 if p.is_file(): d['_approvals'][p.name]=p.read_text().strip()
print(json.dumps(d))
""" % (REMOTE + "/out", [*("WAITING-" + n + ".json" for n in BARRIERS), *base.TERMINAL])


def load_plan(path, freeze=None):
    from . import protocol
    if protocol.ROOT != ROOT or _canonical(protocol.BUDGET) != _canonical(BUDGET):
        raise ValueError("Parent ROOT/budget contract differs from controller")
    return protocol.load_plan(path, freeze)


def checked_budget(plan):
    expected = {"prior_usd": "0", "new_cap_usd": "200", "gpu_cap_usd": "45",
        "api_cap_usd": "90", "translation_and_storage_cap_usd": "15",
        "storage_reserve_usd": "5", "translation_cap_usd": "10", "contingency_usd": "50",
        "total_usd": "200", "main_seconds": 18000, "cheap_seconds": 1800,
        "reserve_seconds": 600, "new_pro_calls": 0, "historical_campaign_separate": True,
        "contingency_automatic_reallocation": False}
    if (_canonical(plan.get("budget")) != _canonical(BUDGET)
            or _canonical(protocol.BUDGET) != _canonical(BUDGET)
            or any(_canonical(BUDGET.get(k)) != _canonical(v) for k, v in expected.items())):
        raise ValueError("Separate bilingual budget contract missing or changed")
    return BUDGET.copy()


def _safe_path(relative):
    if relative != PLAN_RELATIVE:
        raise ValueError("Exact bilingual plan path required")


def _require_ignored(path):
    relative = Path(path).relative_to(ROOT).as_posix()
    result = subprocess.run(["git", "check-ignore", "--quiet", "--", relative], cwd=ROOT,
                            capture_output=True, timeout=10, env=base.local_env())
    if result.returncode:
        raise ValueError("Lifecycle and approval files must be ignored and untracked")


def approval_record(plan_hash, freeze, budget, approval_ref):
    checked_budget({"budget": budget})
    if (not re.fullmatch(r"[0-9a-f]{64}", plan_hash)
            or not re.fullmatch(r"[0-9a-f]{40}", freeze)
            or not isinstance(approval_ref, str)
            or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,159}", approval_ref)):
        raise ValueError("Exact plan, freeze and supplied user-request reference required")
    return {"scope": "bilingual_llama_pilot", "user_confirmed": True,
            "approval_ref": approval_ref, "approved_new_cap_usd": "200",
            "plan_sha256": plan_hash, "freeze_commit": freeze,
            "budget_sha256": hashlib.sha256(_canonical(budget)).hexdigest()}


def fixture_proof(plan, plan_hash, freeze):
    """Recompute fixture-only receipts under a nonmutating shared ledger lock."""
    from . import judges
    if (not re.fullmatch(r"[0-9a-f]{64}", plan_hash) or not re.fullmatch(r"[0-9a-f]{40}", freeze)
            or plan.get("fixtures") != judges.fixture_inventory() or len(plan["fixtures"]) != 32
            or plan.get("judges") != judges.judge_config()):
        raise ValueError("Frozen fixture/judge contract missing or changed")
    root = OWNED_OUT / "judges"
    _no_symlinks(root)
    lock = root / ".judge.lock"
    _no_symlinks(lock)
    if not lock.is_file():
        raise ValueError("Existing canonical judge ledger required")
    with lock.open("rb") as handle:
        fcntl.flock(handle, fcntl.LOCK_SH | fcntl.LOCK_NB)
        before = artifact_map(root)
        if (not set(before) <= set(judges.RECEIPT_FILES) | {".judge.lock"}
                or not {"snapshots.jsonl", "requests.jsonl", "attempts.jsonl", "judgments.jsonl"} <= set(before)):
            raise ValueError("Fixture receipt inventory missing or contains unexpected artifacts")
        # Deliberately do not enter Ledger: __enter__ creates/opens a writer lock.
        ledger = judges.Ledger(root)
        state = judges.validate_receipts(ledger, plan, plan_hash, freeze, [])
        judges._require_healthy(state)
        expected = {f"fixtures:{provider}:{instrument}:{item['id']}"
                    for item in plan["fixtures"] for provider in judges.MODELS for instrument in judges.INSTRUMENTS}
        if (len(expected) != 128 or set(state["finals"]) != expected or state["translations"]
                or any(row.get("phase") != "fixtures" for row in ledger.rows("requests.jsonl"))):
            raise ValueError("Exactly 128 fixture judgments and no target/translation dispatches required")
        gate = judges.fixture_gate(state["finals"], plan["fixtures"])
        if gate.get("pass") is not True:
            raise ValueError("Recomputed synthetic fixture gate failed")
        projection = judges.project_budget(ledger.rows("attempts.jsonl"), [], plan)
        panels = {p + ":" + i for p in judges.MODELS for i in judges.INSTRUMENTS}
        if (projection.get("pass") is not True
                or _number(projection.get("api_cap_usd")) != API_CAP_USD
                or _number(projection.get("projected_total_usd")) > API_CAP_USD
                or set(projection.get("by_instrument", {})) != panels
                or any(type(panel.get("remaining_calls")) is not int or panel["remaining_calls"] != 496
                       for panel in projection["by_instrument"].values())):
            raise ValueError("All remaining 1984 judge calls must fit the separate $90 forecast")
        receipts = {}
        for name in judges.RECEIPT_FILES:
            rows = ledger.rows(name)
            raw = b"".join((judges.canonical(row) + "\n").encode() for row in rows)
            receipts[name] = {"sha256": hashlib.sha256(raw).hexdigest(),
                              "head_sha256": rows[-1]["record_sha256"] if rows else None,
                              "records": len(rows), "bytes": len(raw)}
        if artifact_map(root) != before:
            raise ValueError("Judge receipts changed during read-only fixture verification")
    return {"schema": "bilingual-fixture-gate-v1", "plan_sha256": plan_hash,
            "freeze_commit": freeze, "fixture_inventory_sha256": hashlib.sha256(_canonical(plan["fixtures"])).hexdigest(),
            "pass": True, "judgment_count": 128, "receipts": receipts,
            "judge_budget_projection": projection}


def write_fixture_proof(path, plan, plan_hash, freeze):
    """Offline helper: write-once proof OUTSIDE the canonical input judge ledger."""
    path = Path(path).absolute()
    _no_symlinks(path)
    if not path.is_relative_to(OWNED_OUT) or path.is_relative_to(OWNED_OUT / "judges"):
        raise ValueError("Fixture proof must be under owned output, outside judge inputs")
    _require_ignored(path)
    proof = fixture_proof(plan, plan_hash, freeze)
    raw = _canonical(proof) + b"\n"
    if path.exists():
        if path.read_bytes() != raw:
            raise ValueError("Existing fixture proof differs; never overwrite evidence")
    else:
        with path.open("xb") as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
    return proof


def fixture_gate(path, plan, plan_hash, freeze):
    """Verify the proof against actual canonical receipts, with no paid calls."""
    if path is None:
        raise ValueError("Explicit --fixture-gate required before main rental")
    path = Path(path).absolute()
    _no_symlinks(path)
    if path.is_relative_to(OWNED_OUT / "judges") or not path.is_file() or not 0 < path.stat().st_size <= 1024 * 1024:
        raise ValueError("Fixture proof missing or inside its input ledger")
    raw = path.read_bytes()
    proof = base.strict_json(raw)
    expected = fixture_proof(plan, plan_hash, freeze)
    if _canonical(proof) != _canonical(expected) or path.read_bytes() != raw:
        raise ValueError("Fixture proof differs from verified plan/freeze/receipt replay")
    return {**expected, "artifact_sha256": hashlib.sha256(raw).hexdigest()}


def sparse_paths():
    """Explicit frozen files only: never upload a working tree, .env or weights."""
    from . import protocol
    paths = sorted(set(protocol.source_paths()) | set(TESTS) | {
        protocol.TOKEN_BINDINGS_PATH, protocol.PRIOR_BINDING_PATH,
        PLAN_RELATIVE, ".gitignore", ".gitattributes", "pytest.ini",
        "experiments/bilingual_llama_pilot/requirements-gpu.txt",
        "experiments/sae_assay_diagnostic/requirements-gpu.txt"})
    for name in paths:
        path = PurePosixPath(name)
        allowed_dotfile = name in {".gitignore", ".gitattributes"}
        if (not re.fullmatch(r"[A-Za-z0-9_./-]+", name) or path.is_absolute()
                or path.as_posix() != name or ".." in path.parts
                or (not allowed_dotfile and (any(p.startswith(".") for p in path.parts)
                    or path.suffix not in {".py", ".json", ".md", ".txt", ".ini", ".toml"}))
                or any(p.lower() in {"out", "cache", "weights", "secrets"} for p in path.parts)
                or ".env" in path.name.lower()):
            raise ValueError("Unsafe sparse payload file: " + name)
    return paths


def sparse_checkout_commands(freeze):
    if not re.fullmatch(r"[0-9a-f]{40}", freeze):
        raise ValueError("Exact sparse-checkout commit required")
    paths = sparse_paths()
    physical_check = ("import pathlib,subprocess; paths=" + repr(paths) + "; "
        "assert all(pathlib.Path(p).is_file() and not any(q.is_symlink() for q in "
        "(pathlib.Path(p),*pathlib.Path(p).parents)) for p in paths), 'Unsafe runtime closure'; "
        "assert not subprocess.check_output(['git','status','--porcelain',"
        "'--untracked-files=no']), 'Tracked checkout changed'")
    patterns = shlex.join(["printf", "%s\n", *("/" + p for p in paths)])
    return [patterns + " | git sparse-checkout set --no-cone --stdin",
            "git checkout --detach " + freeze, 'test "$(git rev-parse HEAD)" = ' + freeze,
            shlex.join(["python3", "-c", physical_check])]


def worker_script(kind, relative, freeze, deadline):
    if kind not in base.HARDWARE or not re.fullmatch(r"[0-9a-f]{40}", freeze):
        raise ValueError("Exact freeze and cheap/main required")
    _safe_path(relative)
    _utc(deadline)
    python = REMOTE + "/venv/bin/python"
    validate = ("from experiments.bilingual_llama_pilot.protocol import load_plan; load_plan("
                + repr(relative) + "," + repr(freeze) + ")")
    exit_code = ("import json,sys; json.dump({'exit_code':int(sys.argv[1])},open("
                 + repr(REMOTE + "/out/controller-exit.json") + ",'x'))")
    if kind == "cheap":
        work = ["export INSTRUCTION_TEST_DEVICE=cuda HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1",
                shlex.join([python, "-c", "import torch; assert torch.cuda.is_available() and torch.cuda.is_bf16_supported()"]),
                shlex.join([python, "-m", "pytest", *TESTS, "-q",
                            "--junitxml=" + REMOTE + "/out/tests.xml"]),
                shlex.join([python, "-c", "import json; json.dump({'pass':True,'scope':'tiny_cuda_exact_path'},open("
                            + repr(REMOTE + "/out/DONE-all.json") + ",'x'))"])]
    else:
        work = [shlex.join([python, "-u", "-m", "experiments.bilingual_llama_pilot.runner",
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
        python + " -m pip install -r experiments/bilingual_llama_pilot/requirements-gpu.txt",
        python + " -m pip freeze --all > " + REMOTE + "/out/pip-freeze.txt",
        shlex.join([python, "-c", validate]), "set +x; . " + HF_ENV + "; rm -f " + HF_ENV,
        "export HF_HOME=/workspace/cache PYTHONUNBUFFERED=1", *work,
        'test -z "$(git status --porcelain --untracked-files=no)"'])


def conservative_projection(timings, *, elapsed_seconds, hourly_usd, prior_gpu_usd):
    """Decimal mean of ALL calls, 30% on remaining 760-call work, plus reserve.

    Startup, qualification, retrieval and barrier waiting already incurred are
    included in billed elapsed time. No remaining judge waits or contingency.
    This is a measured feasibility estimate, not a guarantee of runtime; the
    independent live cost/deadline monitor remains authoritative.
    """
    values = [_number(t) for t in timings]
    elapsed, rate, prior = map(_number, (elapsed_seconds, hourly_usd, prior_gpu_usd))
    if (not 0 < len(values) < TOTAL_GENERATIONS or any(t <= 0 for t in values)
            or elapsed < 0 or sum(values) > elapsed + Decimal("1")
            or not 0 < rate <= base.HARDWARE["main"][1] + base.STORAGE
            or not 0 <= prior <= GPU_CAP_USD):
        raise ValueError("Invalid complete generation timing/accounting evidence")
    remaining = sum(values) * (TOTAL_GENERATIONS - len(values)) / len(values)
    lifetime = elapsed + Decimal("1.30") * remaining + RESERVE_SECONDS + RUNNER_RESERVE_SECONDS
    gpu = prior + lifetime * rate / 3600
    return {"observed_generations": len(values), "total_generations": TOTAL_GENERATIONS,
            "maximum_blocks": BLOCKS, "billed_elapsed_seconds": str(elapsed),
            "observed_generation_seconds": str(sum(values)), "remaining_generation_seconds": str(remaining),
            "safety_factor": "1.30", "retrieval_reserve_seconds": RESERVE_SECONDS,
            "runner_internal_reserve_seconds": RUNNER_RESERVE_SECONDS,
            "projected_lifetime_seconds": str(lifetime), "projected_gpu_usd": str(gpu),
            "contingency_used_usd": "0", "pass": lifetime < MAIN_SECONDS and gpu <= GPU_CAP_USD}


def audit(root, plan, plan_hash, freeze):
    from .raw_audit import audit_raw_window
    binding = base.strict_json((Path(root) / "receipts.jsonl").read_bytes().splitlines()[0])
    if binding.get("plan_sha256") != plan_hash or binding.get("freeze_commit") != freeze:
        raise ValueError("Raw receipt plan/freeze mismatch")
    return audit_raw_window(root, plan)


class Controller(transport.Controller):
    signal_worker = qualification.Controller.signal_worker
    close_until_verified = qualification.Controller.close_until_verified
    _write_remote = qualification.Controller._write_remote

    def __init__(self, plan_path, freeze, out, kind, api, *, launch=False,
                 approved_new_cap_usd=None, approval_ref=None, approval_file=None,
                 fixture_gate=None, run=subprocess.run, clock=base.now, sleep=time.sleep,
                 monotonic=time.monotonic):
        if kind not in base.HARDWARE or not re.fullmatch(r"[0-9a-f]{40}", freeze):
            raise ValueError("Exact freeze and cheap/main required")
        _no_symlinks(plan_path)
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
        self.fixture_gate_path = fixture_gate
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
            raise ValueError("Creation requires --launch and --approved-new-cap-usd 200")
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
        events = {e["id"]: e for e in EventLedger(root / "events.jsonl", self.plan_hash, self.freeze, []).read()}
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
        fixture = fixture_gate(self.fixture_gate_path, self.plan, self.plan_hash, self.freeze) if self.kind == "main" else None
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
        if (prior_new < 0 or full_cost > GPU_CAP_USD
                or full_cost + API_CAP_USD + TRANSLATION_QA_STORAGE_USD + CONTINGENCY_USD > NEW_CAP_USD):
            raise ValueError("Full GPU lifetimes do not fit without borrowing reserved funds")
        authority = self.ledger.bind("creation-approval", approval)
        if fixture is not None:
            self.ledger.bind("fixture-gate", fixture)
        intent = {"payload": payload, "quote": quoted, "blocked": blocked, "created_utc": created.isoformat(),
                  "deadline_utc": (created + timedelta(seconds=self.hard_seconds - RESERVE_SECONDS)).isoformat(),
                  "hard_deadline_utc": (created + timedelta(seconds=self.hard_seconds)).isoformat(),
                  "prior_new_usd": str(prior_new), "prior_total_usd": "0", "contingency_used_usd": "0",
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
        new = _number(intent["prior_new_usd"]) + (elapsed + seconds + RESERVE_SECONDS) * rate / 3600
        self.record("accounting", {"utc": _utc(self.clock()).isoformat(), "elapsed_seconds": str(elapsed),
                    "projected_gpu_usd": str(new), "cumulative_gpu_upper_bound_usd": str(new),
                    "api_accounting": "separate local ledger", "reserved_non_gpu_usd": "155",
                    "contingency_used_usd": "0"})
        if elapsed + seconds >= self.hard_seconds - RESERVE_SECONDS or new > GPU_CAP_USD:
            raise ValueError("GPU budget or retrieval deadline reached")
        return elapsed * rate / 3600

    @transport.serialized
    def start_worker(self):
        if (not self.launch_enabled or not self.api.writable or not self.event("creation-approval")
                or any(self.event(n) for n in ("worker-intent", "closing", "delete-intent", "closed"))):
            raise ValueError("Worker dispatch disabled or already attempted")
        if self.kind == "main" and self.event("fixture-gate") is None:
            raise ValueError("Main worker lacks a verified fixture gate")
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
            "cumulative_gpu_upper_bound_usd": None if new is None else str(new),
            "contingency_used_usd": "0", "api_accounting": "separate local ledger; excluded here",
            "within_limits": new is not None and elapsed <= self.hard_seconds and new <= GPU_CAP_USD})

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
        if (not isinstance(report, dict) or report.get("pass") is not True
                or type(report.get("rows")) is not int or type(report.get("generations")) is not int
                or type(report.get("blocked_cells")) is not int or report["blocked_cells"] < 0
                or report.get("production_eligible") is not True
                or not isinstance(report.get("partial_generation_ids"), list)
                or not isinstance(report.get("unresolved_generation_dispatches"), list)):
            raise ValueError("Local snapshot audit failed or incomplete contract")
        if artifact_map(root) != data["artifacts"]:
            raise ValueError("Audit modified raw evidence")
        self.record("live-audit", {"retrieval_sha256": receipt["sha256"], "report": report})
        return report

    def _barrier(self, name):
        if (not self.api.writable or self.kind != "main" or name not in BARRIERS
                or not self.event("worker-started")
                or any(self.event(n) for n in ("closing", "delete-intent", "closed"))):
            raise ValueError("Live owned main worker required")
        state = self.status()
        self.cost_check(state["pod"])
        filename = "WAITING-" + name + ".json"
        barrier = state["files"].get(filename, {})
        if (barrier.get("plan_sha256") != self.plan_hash or barrier.get("freeze_commit") != self.freeze
                or barrier.get("barrier") != name or type(barrier.get("rows")) is not int
                or barrier["rows"] != BARRIER_ROWS[name] or any(n in state["files"] for n in base.TERMINAL)):
            raise ValueError("Matching barrier is not live")
        if name == "first-two" and (not self.event("approved:qualification")
                or state["files"].get("_approvals", {}).get("APPROVE-qualification") != self.plan_hash):
            raise ValueError("Earlier structural barrier not approved")
        receipt = next((r for r in reversed(self.ledger.read()) if r["id"].startswith("retrieval:")
                        and filename in r["data"].get("artifacts", {})), None)
        if receipt is None:
            raise ValueError("Retrieve a coherent barrier snapshot first")
        report = self._audit_receipt(receipt)
        if (report["rows"] != BARRIER_ROWS[name] or report["partial_generation_ids"]
                or report["unresolved_generation_dispatches"]):
            raise ValueError("Barrier has incorrect rows or incomplete generation dispatches")
        root = Path(receipt["data"]["directory"])
        if base.strict_json((root / filename).read_bytes()) != barrier:
            raise ValueError("Live barrier differs from retrieved snapshot")
        return state, receipt, report

    def _throughput_gate(self, receipt, report):
        root = Path(receipt["data"]["directory"])
        blocks = self.plan.get("blocks", [])
        expected = {"generations/" + spec["id"] + ".json" for block in blocks[:2]
                    for spec in [*block["sources"], *block["cells"]]}
        sources = {"generations/" + spec["id"] + ".json" for block in blocks[:2] for spec in block["sources"]}
        inventory = [spec["id"] for block in blocks for spec in [*block["sources"], *block["cells"]]]
        if (len(blocks) != BLOCKS or len(inventory) != TOTAL_GENERATIONS
                or len(set(inventory)) != TOTAL_GENERATIONS
                or self.plan.get("counts", {}).get("generation_calls") != TOTAL_GENERATIONS
                or report["rows"] != 3):
            raise ValueError("Throughput requires two audited blocks of the fixed twenty")
        names = sorted(n for n in receipt["data"]["artifacts"] if n.startswith("generations/"))
        if (not sources <= set(names) <= expected or len(names) != report["generations"]
                or len(names) + report["blocked_cells"] != len(expected)
                or any(not re.fullmatch(r"generations/[A-Za-z0-9_-]+\.json", n) for n in names)):
            raise ValueError("Every audited generation must have an immutable timed artifact")
        if artifact_map(root) != receipt["data"]["artifacts"]:
            raise ValueError("Timing artifacts changed")
        timings = [base.strict_json((root / n).read_bytes())["elapsed_seconds"] for n in names]
        intent = self.event("create-intent")["data"]
        result = conservative_projection(timings, elapsed_seconds=self._elapsed(intent),
            hourly_usd=_number(intent["quote"]["hourly_rate_usd"]) + base.STORAGE,
            prior_gpu_usd=intent["prior_new_usd"])
        result["retrieval_sha256"] = receipt["sha256"]
        self.record("throughput-gate", result)
        if not result["pass"]:
            raise ValueError("All 760 generations plus safety/retrieval reserves do not fit")
        return result

    @transport.serialized
    def approve(self, name, plan_hash):
        if name not in BARRIERS or plan_hash != self.plan_hash:
            raise ValueError("Only structural barriers accept exact plan-hash approval")
        state, receipt, report = self._barrier(name)
        if name == "first-two":
            self._throughput_gate(receipt, report)
        self.cost_check(state["pod"])
        self.ledger.bind("approval-intent:" + name, {"plan_sha256": plan_hash,
                         "retrieval_sha256": receipt["sha256"]})
        self._write_remote(state["pod"], "APPROVE-" + name, (plan_hash + "\n").encode())
        return self.ledger.bind("approved:" + name, {"plan_sha256": plan_hash})

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
        if self.kind == "main" and self.event("final-structural-audit") is None:
            try:
                result = {"status": "audited", "report": self._audit_receipt(receipt)}
            except Exception as exc:
                result = {"status": "failed", "error_type": type(exc).__name__}
            if artifact_map(root) != data["artifacts"]:
                raise ValueError("Final audit modified evidence")
            self.ledger.bind("final-structural-audit", {"retrieval_sha256": receipt["sha256"], **result})

    def _waiting(self, files):
        return tuple(name for name in BARRIERS if "WAITING-" + name + ".json" in files
                     and not (self.event("approved:" + name)
                              and files.get("_approvals", {}).get("APPROVE-" + name) == self.plan_hash))

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
                if any(e["id"].startswith("throughput-gate:") and e["data"].get("pass") is False
                       for e in self.ledger.read()):
                    return self.close_until_verified()
                self.cost_check(self.owned())
                state = self.status()
                self.cost_check(state["pod"])
                self.record("health", state)
                files = state["files"]
                if any(name in files for name in base.TERMINAL):
                    return self.close_until_verified()
                waiting = self._waiting(files)
                progress = files.get("_progress", {})
                phase = (progress, waiting)
                if phase != previous:
                    previous, changed_at = phase, self.monotonic()
                if not waiting and self.monotonic() - changed_at >= (900 if progress else 1800):
                    raise ValueError("Owned worker stalled outside a live barrier")
                if waiting != announced or self.monotonic() - last_pull >= 600:
                    receipt = self.retrieve()
                    if self.kind == "main" and (waiting or any(n.startswith("rows/") for n in receipt["data"]["artifacts"])):
                        self._audit_receipt(receipt)
                    if waiting != announced and waiting:
                        print("WAITING: " + ", ".join(waiting) + "; structural approval required; GPU clock continues.", flush=True)
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
    parser.add_argument("--action", choices=("inspect", "fixture-proof", "create", "monitor", "retrieve", "status",
                                            "approve", "close", "reconcile"), default="inspect")
    parser.add_argument("--launch", action="store_true")
    parser.add_argument("--approved-new-cap-usd")
    parser.add_argument("--approval-ref")
    parser.add_argument("--approval-file")
    parser.add_argument("--fixture-gate")
    parser.add_argument("--barrier", choices=BARRIERS)
    parser.add_argument("--approve-plan-sha256")
    args = parser.parse_args(argv)
    if args.action not in {"inspect", "fixture-proof"} and not args.launch:
        parser.error("All live lifecycle operations require --launch")
    if args.action == "create" and not all((args.approved_new_cap_usd, args.approval_ref, args.approval_file)):
        parser.error("Creation requires explicit cap, approval-ref and existing approval-file")
    if args.action == "create" and args.kind == "main" and not args.fixture_gate:
        parser.error("Main creation requires --fixture-gate")
    if args.action == "approve" and not (args.barrier and args.approve_plan_sha256):
        parser.error("Structural barrier and exact plan SHA required")
    if args.action == "fixture-proof":
        if not args.fixture_gate:
            parser.error("--fixture-gate output required")
        path = Path(args.plan).resolve()
        _safe_path(path.relative_to(ROOT).as_posix())
        plan = load_plan(path, args.freeze)
        checked_budget(plan)
        print(json.dumps(write_fixture_proof(args.fixture_gate, plan, sha(path), args.freeze), sort_keys=True))
        return
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
                            approval_file=args.approval_file, fixture_gate=args.fixture_gate)
    if args.action == "create":
        controller.launch()
        result = controller.monitor()
    elif args.action == "approve":
        result = controller.approve(args.barrier, args.approve_plan_sha256)
    elif args.action == "close":
        result = controller.close_until_verified()
    else:
        result = getattr(controller, args.action)()
    print(json.dumps(result, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()

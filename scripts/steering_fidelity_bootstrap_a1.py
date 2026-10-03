"""Operational A1: enlarge only the cheap-node clock; retain scientific freeze.

Run this script from its amendment checkout, importing the unchanged controller
from --runtime-root. The original campaign ledger, costs and failed attempt are
never reset. No scientific module, plan, budget cap or main deadline is patched.
"""
import argparse
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
SCIENCE_FREEZE = "2d9c94f1de59f0f59dd89636c20afece1f6d1daf"
PLAN_HASH = "6f0a5609caabeae6907513939d0a647fbd2b99dacf9f519aeb434b001e775fb0"
ORIGINAL_CLOSED_HASH = "44b6d8dd56e26b1e81225222ff11c28469bbf7f3bb986ddb0f0d8d1c35f1507e"
ORIGINAL_POD = "cnoltv3wltphd9"
ORIGINAL_COST = Decimal("0.06297823093333333333333333333")
CHEAP_SECONDS = 1800
PATHS = ("scripts/steering_fidelity_bootstrap_a1.py", "tests/test_fidelity_bootstrap_a1.py",
         ".github/workflows/steering-bootstrap-a1.yml", "docs/STEERING_FIDELITY_BOOTSTRAP_A1_20261002.md")


def verify_amendment(freeze, *, network=True, opener=None):
    if not re.fullmatch(r"[0-9a-f]{40}", freeze or "") or freeze == SCIENCE_FREEZE:
        raise ValueError("Distinct full amendment commit required")
    def git(*args):
        return subprocess.check_output(["git", *args], cwd=ROOT, timeout=30)
    if git("rev-parse", "HEAD").decode().strip() != freeze:
        raise ValueError("Amendment HEAD differs")
    sources = {}
    for name in PATHS:
        path = ROOT / name
        if any(p.is_symlink() for p in (path, *path.parents)):
            raise ValueError("Amendment source cannot be a symlink")
        raw = path.read_bytes()
        if raw != git("show", freeze + ":" + name):
            raise ValueError("Amendment source changed")
        sources[name] = hashlib.sha256(raw).hexdigest()
    ci = None
    if network:
        opener = opener or urllib.request.build_opener(urllib.request.ProxyHandler({}))
        def get(path):
            request = urllib.request.Request("https://api.github.com/repos/tdj28/llm_selfref_pre/" + path,
                headers={"Accept": "application/vnd.github+json", "User-Agent": "steering-bootstrap-a1"})
            with opener.open(request, timeout=30) as response:
                return json.loads(response.read())
        result = get("actions/workflows/steering-bootstrap-a1.yml/runs?head_sha=" + freeze + "&per_page=100")
        runs = result.get("workflow_runs", [])
        if (not runs or result.get("total_count") != len(runs) or
                any(r.get("head_sha") != freeze or r.get("status") != "completed"
                    or r.get("conclusion") != "success" for r in runs)):
            raise ValueError("Exact amendment focused CI has not passed")
        run = max(runs, key=lambda r: r["id"])
        result = get("actions/runs/" + str(run["id"]) + "/jobs?per_page=100")
        jobs = result.get("jobs", [])
        if (len(jobs) != result.get("total_count") or not jobs or
                not any(j.get("name") == "Bootstrap A1 / Python 3.12" for j in jobs) or
                any(j.get("status") != "completed" or j.get("conclusion") != "success" for j in jobs)):
            raise ValueError("Amendment focused jobs missing or unsuccessful")
        ci = {"run_id": run["id"], "pass": True, "scope": "operational amendment and inherited lifecycle"}
    return {"amendment_freeze": freeze, "sources": sources, "ci": ci,
            "scientific_freeze": SCIENCE_FREEZE, "plan_sha256": PLAN_HASH,
            "cheap_hard_seconds": CHEAP_SECONDS, "main_hard_seconds": 9000,
            "caps_unchanged": {"phase_c": "25", "gpu": "22", "campaign": "170"}}


def apply_window(ctrl, amendment):
    """Apply a separately recorded cheap-only override after ordinary construction."""
    ci = amendment.get("ci")
    if (ctrl.freeze != SCIENCE_FREEZE or ctrl.plan_hash != PLAN_HASH or
            (ctrl.kind, ctrl.attempt) not in (("cheap", 2), ("main", 1)) or
            amendment.get("scientific_freeze") != SCIENCE_FREEZE or
            amendment.get("plan_sha256") != PLAN_HASH or
            amendment.get("cheap_hard_seconds") != CHEAP_SECONDS or
            amendment.get("main_hard_seconds") != 9000 or
            not isinstance(ci, dict) or ci.get("pass") is not True):
        raise ValueError("A1 scope, source, plan, attempt or CI differs")
    # This is read-only and validates the hash chain, receipts, cumulative costs
    # and original deletion through the unchanged lifecycle implementation.
    from experiments.steering_fidelity import controller as old
    path = ctrl.campaign_root / "cheap-001/events.jsonl"
    old._no_symlinks(path)
    if not path.is_file():
        raise ValueError("Original ledger is required and cannot be recreated")
    events = {e["id"]: e for e in old.EventLedger(path, PLAN_HASH, SCIENCE_FREEZE, []).read()}
    closed = events.get("closed", {})
    data = closed.get("data", {})
    if (closed.get("sha256") != ORIGINAL_CLOSED_HASH or data.get("pod_id") != ORIGINAL_POD or
            data.get("get_status") != 404 or data.get("within_limits") is not True or
            Decimal(data.get("compute_upper_bound_usd", "NaN")) != ORIGINAL_COST):
        raise ValueError("Original failed attempt or its paid cost changed")
    root = ctrl.campaign_root / "cheap-001"
    receipt = old.base.strict_json((root / "final-retrieval.json").read_bytes())
    saved = receipt["data"]
    directory = Path(saved.get("directory", ""))
    if (events.get(receipt.get("id")) != receipt or saved.get("pod_id") != ORIGINAL_POD or
            not directory.is_relative_to(root / "retrievals") or
            old.artifact_map(directory) != saved["artifacts"] or
            "DONE-all.json" in saved["artifacts"] or "tests.xml" in saved["artifacts"]):
        raise ValueError("Original incomplete cheap-test artifacts differ")
    # _prior_attempts enforces all previous closure/cost reservations at launch.
    # On later monitor/retrieve calls, a live current reservation is legitimate.
    if ctrl.event("create-intent") and not ctrl.event("bootstrap-a1"):
        raise ValueError("Cannot attach the amendment to an already created attempt")
    if not ctrl.event("create-intent"):
        prior, attempts = ctrl._prior_attempts()
        if prior < ORIGINAL_COST or not attempts or attempts[0][0] != "cheap-001":
            raise ValueError("Original cost not carried forward")
        if ctrl.kind == "main":
            if len(attempts) != 2 or attempts[1][0] != "cheap-002":
                raise ValueError("Main requires the single A1 cheap replacement")
            prior_amendment = attempts[1][1].get("bootstrap-a1", {}).get("data", {}).get("amendment", {})
            if any(prior_amendment.get(k) != amendment.get(k) for k in ("amendment_freeze", "sources")):
                raise ValueError("Cheap replacement belongs to another amendment")
    if ctrl.kind == "cheap":
        if ctrl.hard_seconds != 900:
            raise ValueError("Unexpected inherited cheap clock")
        effective_seconds = CHEAP_SECONDS
    elif ctrl.hard_seconds != 9000:
        raise ValueError("Main clock cannot change")
    else:
        effective_seconds = 9000
    ctrl.ledger.bind("bootstrap-a1", {"amendment": amendment,
        "original_closed_sha256": ORIGINAL_CLOSED_HASH, "original_cost_usd": str(ORIGINAL_COST),
        "inherited_config_retained": True, "effective_hard_seconds": effective_seconds})
    ctrl.hard_seconds = effective_seconds
    return ctrl


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime-root", type=Path, required=True)
    parser.add_argument("--amendment-freeze", required=True)
    parser.add_argument("--kind", choices=("cheap", "main"), required=True)
    parser.add_argument("--action", choices=("create", "monitor", "retrieve", "status", "approve", "close"), required=True)
    parser.add_argument("--launch", action="store_true")
    parser.add_argument("--approval-ref")
    parser.add_argument("--approval-file")
    parser.add_argument("--barrier", choices=("first-rows", "throughput"))
    args = parser.parse_args()
    if not args.launch:
        parser.error("Explicit --launch required")
    runtime = args.runtime_root.resolve()
    if runtime == ROOT:
        parser.error("Keep the scientific runtime in its unchanged checkout")
    sys.path.insert(0, str(runtime))
    from experiments.steering_fidelity import controller as old
    if old.ROOT.resolve() != runtime:
        raise ValueError("Imported a different scientific checkout")
    amendment = verify_amendment(args.amendment_freeze, network=args.action == "create")
    api = old.base.RunPodV2(__import__("os").environ.get("RUNPOD_API_KEY"), writable=True)
    ctrl = old.Controller(runtime / old.PLAN_RELATIVE, SCIENCE_FREEZE, old.OWNED_OUT, args.kind, api,
        launch=True, attempt=2 if args.kind == "cheap" else 1,
        approved_new_cap_usd="25", approval_ref=args.approval_ref, approval_file=args.approval_file)
    if args.action != "create":
        record = ctrl.event("bootstrap-a1")
        bound = record.get("data", {}).get("amendment", {}) if record else {}
        if any(bound.get(k) != amendment.get(k) for k in ("amendment_freeze", "sources")):
            raise ValueError("Live lifecycle operation lacks the original amendment binding")
        # Cleanup/monitoring must not depend on GitHub remaining available.
        amendment = bound
    apply_window(ctrl, amendment)
    if args.action == "create":
        ctrl.launch()
        result = ctrl.monitor()
    elif args.action == "close":
        result = ctrl.close_until_verified()
    elif args.action == "approve":
        if args.barrier is None:
            parser.error("Approval needs a fixed barrier")
        result = ctrl.approve(args.barrier, PLAN_HASH)
    else:
        result = getattr(ctrl, args.action)()
    print(json.dumps(result, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()

"""Separately frozen A2 execution; finalization never launches or loads secrets."""
import argparse
from copy import deepcopy
from datetime import datetime, timezone
from decimal import Decimal
import os
from pathlib import Path
import subprocess

from experiments.openrouter_swap import protocol as common
from experiments.openrouter_swap.ledger import Halted, _no_symlinks, read_events
from experiments.openrouter_swap.release import _load
from experiments.openrouter_swap_openweights_a1 import production as a1
from . import protocol as p
from .ledger import CompositeLedger, DeltaLedger, ReplayDelta
from .prefix import Prefix, check, sha

PLAN, BRANCH = p.PLAN, a1.BRANCH
PHASES = ("screen-initial", "screen", "main")
bytes_once = a1.bytes_once
guarded_sender, load_key = a1.guarded_sender, a1.load_key


def write_once(path, value):
    bytes_once(path, (common.canonical(value) + "\n").encode())


def failure_evidence():
    # Parent owns this additive exporter and must finish its release before us.
    from experiments import openweights_a1_failure_release as failure
    root = common.ROOT / p.FAILURE
    check(common.sha(root / "RELEASE.json") == p.FAILURE_SHA, "Expected parent failure release is not ready or changed")
    check(failure.verify(root)["pass"], "Parent failure release did not verify")
    prefix = Prefix(root)
    check(_load(root / "RELEASE.json")["status"] == "incomplete", "A1 failure must remain incomplete")
    return {"path": p.FAILURE, "release_sha256": p.FAILURE_SHA,
            "manifest_sha256": common.sha(root / "MANIFEST.json"), "prefix": deepcopy(p.PREFIX)}, prefix


def source_hashes():
    old = common.ROOT / p.A1_PLAN
    check(common.sha(old) == p.PREFIX["plan_sha256"], "Frozen A1 plan changed")
    hashes = dict(_load(old)["source_hashes"])
    check(all(common.sha(common.ROOT / n) == h for n, h in hashes.items()), "Frozen A1 source changed")
    names = {p.A1_PLAN, "experiments/openweights_a1_failure_release.py", "tests/test_openweights_a1_failure_release.py"}
    names.update(q.relative_to(common.ROOT).as_posix() for q in
                 (common.ROOT / "experiments/openrouter_swap_openweights_a2").iterdir()
                 if q.is_file() and q.suffix in {".py", ".md"})
    names.update(q.relative_to(common.ROOT).as_posix() for q in
                 (common.ROOT / "tests").glob("test_openrouter_openweights_a2*.py"))
    hashes.update({n: common.sha(common.ROOT / n) for n in sorted(names)})
    return dict(sorted(hashes.items()))


def reconcile(budget, record, *, fresh=False, exact=False):
    p.check_budget(budget)
    check(isinstance(record, dict) and set(record) == {"scope", "confirmed", "as_of_utc", "prior_costs", "external_commitments"}
          and record["scope"] == budget.scope and record["confirmed"] is True, "Explicit cumulative reconciliation required")
    a1.public_identifier(budget.scope, scope=True)
    a1._date(record["as_of_utc"], fresh=fresh)
    totals = []
    identifiers = set()
    for group in ("prior_costs", "external_commitments"):
        rows, total = record[group], Decimal(0)
        check(isinstance(rows, list), "Explicit cost lists required")
        for row in rows:
            check(isinstance(row, dict) and set(row) == {"id", "cost_bound_usd", "evidence_sha256"}
                  and row["id"] not in identifiers and a1._hex(row["evidence_sha256"]), "Duplicated or malformed cost evidence")
            a1.public_identifier(row["id"])
            identifiers.add(row["id"])
            total += a1._amount(row["cost_bound_usd"])
        totals.append(total)
    check(record["prior_costs"] == [{"id": "openweights-a1-through-initial-failure", "cost_bound_usd": str(p.PRIOR),
                                    "evidence_sha256": p.FAILURE_SHA}], "Exact once-only prior carry required")
    limits = [Decimal(budget.prior_spend_usd), Decimal(budget.external_commitments_usd)]
    check(totals == limits if exact else all(x <= y for x, y in zip(totals, limits)), "Unfunded reconciliation")
    a1.public_json(record)


def finalize(draft, *, authorization, reconciliation, endpoint_evidence, fresh=True):
    budget = p.verify_draft(draft)
    check(isinstance(authorization, dict) and set(authorization) == {"approval_id", "approved", "scope", "new_target_outcomes_seen"}
          and authorization["approved"] is True and authorization["new_target_outcomes_seen"] is True
          and authorization["scope"] == budget.scope, "Explicit post-outcome continuation approval required")
    a1.public_identifier(authorization["approval_id"])
    reconcile(budget, reconciliation, fresh=fresh, exact=True)
    specs = {s["id"]: s for s in [*draft["models"].values(), *draft["judges"].values()]}
    a1.endpoint_capabilities(endpoint_evidence, specs, fresh=fresh)
    evidence, _ = failure_evidence()
    result = {**deepcopy(draft), "schema": "openweights-a2-production-v1", "status": "prospective_execution_amendment",
              "launch_authorized": True, "authorization": deepcopy(authorization),
              "reconciliation": deepcopy(reconciliation), "endpoint_evidence": deepcopy(endpoint_evidence),
              "failure_evidence": evidence, "source_hashes": source_hashes()}
    a1.public_json(result)
    return result


def validate(plan):
    budget = p.Budget(**plan["budget"])
    expected = finalize(p.build_draft(budget=budget), authorization=plan["authorization"],
                        reconciliation=plan["reconciliation"], endpoint_evidence=plan["endpoint_evidence"], fresh=False)
    check(common.canonical(expected) == common.canonical(plan), "A2 plan/source/failure binding differs")
    return budget


def git(*args):
    return subprocess.check_output(["git", "--no-replace-objects", *args], cwd=common.ROOT,
        env={**os.environ, "GIT_NO_LAZY_FETCH": "1"}, stderr=subprocess.DEVNULL)


def verify_git(path, freeze, *, pushed=False):
    plan = _load(Path(path)); validate(plan)
    check(Path(path).read_bytes() == (common.canonical(plan) + "\n").encode(), "Noncanonical A2 plan bytes")
    check(a1._hex(freeze, 40), "Full A2 freeze SHA required")
    check(git("show", f"{freeze}:{PLAN}") == Path(path).read_bytes(), "A2 plan differs from freeze")
    for name, digest in plan["source_hashes"].items():
        check(sha(git("show", f"{freeze}:{name}")) == digest, "Frozen source differs")
    # The new freeze also carries the exact complete parent failure inventory.
    failure = common.ROOT / p.FAILURE
    manifest = _load(failure / "MANIFEST.json")
    for name in ["MANIFEST.json"] + [e["path"] for e in manifest["files"]]:
        check(git("show", f"{freeze}:{p.FAILURE}/{name}") == (failure / name).read_bytes(), "Failure release is not frozen")
    proof = {"freeze": freeze, "branch": BRANCH, "remote_head": None}
    if pushed:
        remote = git("ls-remote", "origin", BRANCH).decode().split()
        check(len(remote) == 2 and a1._hex(remote[0], 40) and remote[1] == BRANCH, "Pushed A2 proof unavailable")
        git("merge-base", "--is-ancestor", freeze, remote[0]); proof["remote_head"] = remote[0]
    return plan, proof


def canonical_root():
    directory = Path(git("rev-parse", "--git-common-dir").decode().strip())
    if not directory.is_absolute():
        directory = common.ROOT / directory
    return directory.resolve().parent / "out/openrouter-openweights-a2-v1"


def runtime_for(plan, freeze):
    return {"freeze": freeze, "plan_sha256": sha((common.canonical(plan) + "\n").encode()),
            "plan_path": PLAN, "budget": plan["budget"], "prefix": deepcopy(p.PREFIX),
            "failure_evidence": plan["failure_evidence"]}


def checkpoint(root, runner, kind):
    runner.require_resolved()
    if kind == "initial_audit":
        runner.require_fixtures(); runner.complete("screen", initial=True)
        check(all(r["phase"] == "screen" and runner.catalog[r["metadata"]["item_id"]]["block"] <= 2
                  for r in runner.ledger.delta.rows()), "Initial checkpoint must precede later screen/main calls")
        value = runner.audit()
    elif kind == "main_admission":
        check(not any(r["phase"] == "main" for r in runner.ledger.delta.rows()), "Main admission must precede main dispatch")
        value = runner.main_admission()
    else:
        raise Halted("Unknown checkpoint")
    raw = (Path(root) / "raw/events.jsonl").read_bytes()
    return {"event_count": len(raw.splitlines()), "delta_prefix_sha256": sha(raw),
            "a1_prefix_sha256": p.PREFIX["journal_sha256"], "value": value}


def verify_checkpoint(raw, record, plan, runtime, kind, prefix):
    from .runner import ContinuationRunner
    check(set(record) == {"event_count", "delta_prefix_sha256", "a1_prefix_sha256", "value"}
          and type(record["event_count"]) is int and 1 <= record["event_count"] <= len(raw.splitlines())
          and record["a1_prefix_sha256"] == p.PREFIX["journal_sha256"], "Checkpoint prefix differs")
    part = b"".join(raw.splitlines(keepends=True)[:record["event_count"]])
    check(sha(part) == record["delta_prefix_sha256"], "Checkpoint delta hash differs")
    cap, screen = p.check_budget(p.Budget(**plan["budget"]))
    delta = ReplayDelta(part, prefix, cap=cap, screen_cap=screen)
    runner = ContinuationRunner(plan, runtime["freeze"], runtime["plan_sha256"], CompositeLedger(prefix, delta))
    runner.require_resolved()
    if kind == "initial_audit":
        runner.complete("screen", initial=True)
        check(all(r["phase"] == "screen" and runner.catalog[r["metadata"]["item_id"]]["block"] <= 2
                  for r in delta.rows()), "Checkpoint occurred after later dispatch")
        value = runner.audit()
    else:
        check(kind == "main_admission" and not any(r["phase"] == "main" for r in delta.rows()), "Late or unknown admission")
        value = runner.main_admission()
    check(common.canonical(value) == common.canonical(record["value"]), "Checkpoint does not reconstruct")


def main(argv=None):
    from .runner import ContinuationRunner
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--finalize")
    parser.add_argument("--freeze")
    parser.add_argument("--phase", choices=(*PHASES, "audit"), default="audit")
    parser.add_argument("--launch", action="store_true")
    parser.add_argument("--approval"); parser.add_argument("--reconciliation"); parser.add_argument("--env-file")
    parser.add_argument("--run-dir", help="Read-only audit only")
    args = parser.parse_args(argv)
    try:
        path = common.ROOT / PLAN
        if args.finalize:
            check(not args.launch and not args.freeze and not path.exists(), "Finalization cannot launch or replace a plan")
            values = _load(Path(args.finalize))
            check(set(values) == {"budget", "authorization", "reconciliation", "endpoint_evidence"}, "Explicit finalization inputs required")
            budget = p.Budget(**values.pop("budget"))
            write_once(path, finalize(p.build_draft(budget=budget), **values)); return
        check(args.launch or args.phase == "audit", "Collection requires explicit --launch")
        check(not args.launch or not args.run_dir and args.phase in PHASES, "Launch must use canonical delta and collection phase")
        plan = _load(path); budget = validate(plan)
        if args.launch:
            check(args.approval == plan["authorization"]["approval_id"] and args.reconciliation, "Matching approval and fresh reconciliation required")
            reconciliation = _load(Path(args.reconciliation)); reconcile(budget, reconciliation, fresh=True)
            a1.endpoint_capabilities(plan["endpoint_evidence"],
                {s["id"]: s for s in [*plan["models"].values(), *plan["judges"].values()]}, fresh=True)
        plan, proof = verify_git(path, args.freeze, pushed=args.launch)
        root = Path(args.run_dir).absolute() if args.run_dir else canonical_root()
        if not args.launch:
            from .release import inspect_run
            print(common.canonical(inspect_run(root)["RELEASE.json"])); return
        prefix = Prefix(common.ROOT / p.FAILURE)
        runtime = runtime_for(plan, args.freeze)
        cap, screen = budget.limits()
        with DeltaLedger(root / "raw", prefix, cap=cap, screen_cap=screen) as delta:
            bytes_once(root / "PLAN.json", path.read_bytes()); write_once(root / "runtime.json", runtime)
            runner = ContinuationRunner(plan, args.freeze, runtime["plan_sha256"], CompositeLedger(prefix, delta))
            runner.require_resolved(); runner.audit(); runner.require_fixtures()
            if args.phase != "screen-initial":
                verify_checkpoint((root / "raw/events.jsonl").read_bytes(), _load(root / "initial_audit.json"), plan, runtime, "initial_audit", prefix)
            if args.phase == "main":
                admission = root / "main_admission.json"
                if not admission.exists(): write_once(admission, checkpoint(root, runner, "main_admission"))
                verify_checkpoint((root / "raw/events.jsonl").read_bytes(), _load(admission), plan, runtime, "main_admission", prefix)
            launch = {"phase": args.phase, "proof": proof, "reconciliation": reconciliation,
                      "plan_sha256": runtime["plan_sha256"], "checked_at_utc": datetime.now(timezone.utc).isoformat(),
                      "event_count_before": len(read_events(root / "raw/events.jsonl")), "a1_prefix_sha256": p.PREFIX["journal_sha256"]}
            write_once(root / "launches" / (common.digest(launch) + ".json"), launch)
            runner.sender = guarded_sender(load_key(args.env_file))
            runner.run_blocks("screen" if args.phase == "screen-initial" else args.phase, initial=args.phase == "screen-initial")
            if args.phase == "screen-initial": write_once(root / "initial_audit.json", checkpoint(root, runner, "initial_audit"))
            print(common.canonical(runner.audit()))
    except (ValueError, TypeError, KeyError, OSError, Halted, subprocess.SubprocessError):
        parser.exit(1, "A2 operation failed closed; immutable history and delta retained.\n")


if __name__ == "__main__":
    main()

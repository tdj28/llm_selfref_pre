"""Offline release of an untouched A1 public prefix and a separate A2 delta."""
import argparse
from datetime import timedelta
from decimal import Decimal
import gzip
from pathlib import Path
import shutil
import subprocess
from tempfile import TemporaryDirectory

from experiments.openrouter_swap import analysis as common_analysis, protocol as common
from experiments.openrouter_swap.ledger import Halted, _no_symlinks
from experiments.openrouter_swap.release import _load, _inventory
from experiments.openrouter_swap_openweights import analysis
from experiments.openrouter_swap_openweights_a1 import production as a1
from experiments.openrouter_swap_openweights_a1.release import _scan_payloads
from . import production as prod, protocol as p
from .ledger import CompositeLedger, ReplayDelta
from .prefix import Prefix, check, events_from_bytes, read_raw, sha
from .runner import ContinuationRunner

OPTIONAL = {"initial_audit.json", "main_admission.json"}
DERIVED = {"RELEASE.json", "screen_rows.json", "screen_analysis.json", "main_rows.json", "main_analysis.json", "qualification.json"}
REQUIRED = {"PLAN.json", "runtime.json", "raw/events.jsonl.gz", *DERIVED}


def _runner(plan, runtime, prefix, raw):
    cap, screen = p.Budget(**plan["budget"]).limits()
    delta = ReplayDelta(raw, prefix, cap=cap, screen_cap=screen)
    return ContinuationRunner(plan, runtime["freeze"], runtime["plan_sha256"], CompositeLedger(prefix, delta))


def _launches(root, plan, runtime, events):
    records = []
    budget = p.Budget(**plan["budget"])
    for path in sorted((root / "launches").glob("*.json")):
        row = _load(path)
        check(set(row) == {"phase", "proof", "reconciliation", "plan_sha256", "checked_at_utc", "event_count_before", "a1_prefix_sha256"}
              and path.stem == common.digest(row) and row["phase"] in prod.PHASES
              and row["plan_sha256"] == runtime["plan_sha256"] and row["a1_prefix_sha256"] == p.PREFIX["journal_sha256"]
              and type(row["event_count_before"]) is int and 1 <= row["event_count_before"] <= len(events), "A2 launch record differs")
        proof = row["proof"]
        check(set(proof) == {"freeze", "branch", "remote_head"} and proof["freeze"] == runtime["freeze"]
              and proof["branch"] == prod.BRANCH and a1._hex(proof["remote_head"], 40), "A2 pushed proof differs")
        prod.git("merge-base", "--is-ancestor", runtime["freeze"], proof["remote_head"])
        prod.reconcile(budget, row["reconciliation"])
        stamp = a1._date(row["checked_at_utc"])
        evidence = [(row["reconciliation"]["as_of_utc"], 1)] + [(r["checked_at_utc"], 7) for r in plan["endpoint_evidence"].values()]
        check(all(timedelta(0) <= stamp - a1._date(date) <= timedelta(days=days) for date, days in evidence), "Evidence was stale at A2 dispatch")
        records.append(row)
    return records


def _sequence(root, raw, plan, runtime, prefix, runner):
    events, lines = events_from_bytes(raw), raw.splitlines(keepends=True)
    launches = _launches(root, plan, runtime, events)
    records = {}
    for kind in ("initial_audit", "main_admission"):
        if (root / (kind + ".json")).exists():
            records[kind] = _load(root / (kind + ".json"))
            prod.verify_checkpoint(raw, records[kind], plan, runtime, kind, prefix)
    initial, admission = records.get("initial_audit"), records.get("main_admission")
    admitted = admission["value"]["admitted_models"] if admission else []
    costs, current = {}, None
    for event in events[1:]:
        row = event["data"]
        costs[row["call_id"]] = Decimal(row["cost_usd"])
        if event["kind"] != "reserve":
            continue
        eligible = [r for r in launches if r["event_count_before"] < event["seq"]]
        check(eligible, "Delta dispatch lacks a preceding launch")
        latest = max(r["event_count_before"] for r in eligible)
        phases = {r["phase"] for r in eligible if r["event_count_before"] == latest}
        item = runner.catalog[row["metadata"]["item_id"]]
        check(row["phase"] == item["phase"], "Delta phase changed")
        if row["phase"] == "screen":
            check(current is None and (("screen-initial" in phases and item["block"] <= 2)
                  or ("screen" in phases and initial is not None and initial["event_count"] < event["seq"])), "Screen checkpoint bypass")
            if item["block"] > 2:
                check(initial is not None and initial["event_count"] < event["seq"], "Later screen preceded initial audit")
        else:
            model = item["model"]
            check(row["phase"] == "main" and "main" in phases and initial is not None and admission is not None
                  and initial["event_count"] < event["seq"] and admission["event_count"] < event["seq"]
                  and model in admitted, "Main lacks prospective completion admission")
            check(current is None or admitted.index(model) >= admitted.index(current), "Main priority reversed")
            if model != current and admitted.index(model) > 0:
                prior = _runner(plan, runtime, prefix, b"".join(lines[:event["seq"] - 1]))
                prior.complete("main", models=admitted[:admitted.index(model)])
            current = model
            hold = sum((Decimal(admission["value"]["projections"][m]["projected_cost_with_reserve_usd"])
                        for m in admitted[admitted.index(model) + 1:]), Decimal(0))
            check(sum(costs.values()) + hold <= runner.ledger.cap, "Delta consumed a later model's forecast")
    return admitted, admission


def _derive(root, raw, prefix_root):
    _scan_payloads(root, raw)
    runtime = _load(root / "runtime.json")
    plan, _ = prod.verify_git(root / "PLAN.json", runtime["freeze"])
    check(runtime == prod.runtime_for(plan, runtime["freeze"]), "A2 runtime differs")
    from experiments import openweights_a1_failure_release as failure
    check(common.sha(prefix_root / "RELEASE.json") == plan["failure_evidence"]["release_sha256"]
          and common.sha(prefix_root / "MANIFEST.json") == plan["failure_evidence"]["manifest_sha256"]
          and failure.verify(prefix_root)["pass"], "Embedded A1 failure differs")
    prefix = Prefix(prefix_root)
    runner = _runner(plan, runtime, prefix, raw)
    audit = runner.audit()
    admitted, admission = _sequence(root, raw, plan, runtime, prefix, runner)
    phases = {phase: runner.rows(phase) for phase in ("screen", "main")}
    complete = {}
    for phase, models in (("screen", list(plan["models"])), ("main", admitted)):
        try:
            runner.require_resolved(); runner.complete(phase, models=models)
            complete[phase] = phase != "main" or admission is not None
        except Halted:
            complete[phase] = False
    endpoints = all(common_analysis._value(r, j, e) is not None
                    for rows in phases.values() for r in rows for j in plan["judges"] for e in common_analysis.ENDPOINTS)
    output = {"RELEASE.json": {"schema": "openweights-a2-release-v1", "status": "complete" if all(complete.values()) and endpoints else "incomplete",
        "freeze": runtime["freeze"], "plan_sha256": runtime["plan_sha256"], "audit": audit,
        "fixtures_pass": True, "fixture_evidence": {"epoch": "A1", "event_count": 53, "sha256": p.PREFIX["fixture_prefix_sha256"]},
        "collection_complete": complete, "endpoint_complete": endpoints, "admitted_models": admitted,
        "main_status": "not_run" if not any(r["phase"] == "main" for r in runner.ledger.delta.rows()) else "completed" if complete["main"] else "incomplete",
        "primary_family_size": 4, "amendment": plan["amendment"], "failure_evidence": plan["failure_evidence"],
        "costs": {"prior_including_A1_usd": str(p.PRIOR), "A1_cost_already_in_prior_usd": str(p.PREFIX_COST),
                  "delta_cost_bound_usd": str(runner.ledger.delta.spent()),
                  "scope_cost_plus_commitments_usd": audit["scope_cost_plus_commitments_usd"]}},
        "qualification.json": analysis.qualify(phases["screen"])}
    for phase, rows in phases.items():
        output[phase + "_rows.json"] = rows
        output[phase + "_analysis.json"] = analysis.analyze(rows, phase)
    return output


def inspect_run(root):
    root = Path(root).absolute()
    return _derive(root, read_raw(root), common.ROOT / p.FAILURE)


def _entries(inventory):
    return [{"path": n, "bytes": v["size"], "sha256": v["sha256"]} for n, v in sorted(inventory.items())]


def verify(destination, *, manifest_sha256=None):
    root = Path(destination).absolute()
    inventory = _inventory(root)
    if manifest_sha256 is not None:
        check(common.sha(root / "MANIFEST.json") == manifest_sha256, "External manifest anchor differs")
    manifest = _load(root / "MANIFEST.json")
    check(set(manifest) == {"schema", "files"} and manifest["schema"] == "openweights-a2-manifest-v1"
          and isinstance(manifest["files"], list), "A2 manifest schema differs")
    for entry in manifest["files"]:
        check(isinstance(entry, dict) and set(entry) == {"path", "bytes", "sha256"}
              and type(entry["bytes"]) is int and entry["bytes"] >= 0 and a1._hex(entry["sha256"]), "Malformed manifest entry")
    check(manifest["files"] == _entries(inventory)
          and (root / "MANIFEST.json").read_bytes() == (common.canonical(manifest) + "\n").encode(), "Manifest inventory/hash/encoding differs")
    prefix_root = root / "prefix"
    parent_inventory = _inventory(prefix_root)
    allowed = REQUIRED | OPTIONAL | {"prefix/" + n for n in parent_inventory} | {"prefix/MANIFEST.json"}
    check(REQUIRED <= set(inventory), "Missing A2 artifact")
    for name in set(inventory) - allowed:
        path = Path(name)
        check(path.parent.as_posix() == "launches" and path.suffix == ".json" and a1._hex(path.stem), "Extra or private release payload")
    directories = {parent.as_posix() for n in inventory for parent in Path(n).parents}
    check(all(not q.is_dir() or q.relative_to(root).as_posix() in directories for q in root.rglob("*")), "Extra release directory")
    expected = _derive(root, read_raw(root), prefix_root)
    check(all(common.canonical(_load(root / n)) == common.canonical(v) for n, v in expected.items()), "Derived payload does not reconstruct")
    return {"pass": True, "status": expected["RELEASE.json"]["status"], "files": len(inventory),
            "manifest_sha256": common.sha(root / "MANIFEST.json")}


def build(run_dir, destination):
    source, target = Path(run_dir).absolute(), Path(destination).absolute()
    _no_symlinks(source); _no_symlinks(target)
    check(not target.exists() and target != source and source not in target.parents, "Destination must be new and outside run")
    with TemporaryDirectory(prefix="openweights-a2-release-") as temporary:
        root = Path(temporary).resolve() / "bundle"; root.mkdir()
        names = {"PLAN.json", "runtime.json"} | {n for n in OPTIONAL if (source / n).exists()}
        names.update(q.relative_to(source).as_posix() for q in (source / "launches").glob("*.json"))
        for name in names:
            _no_symlinks(source / name); prod.bytes_once(root / name, (source / name).read_bytes())
        evidence, _ = prod.failure_evidence()
        parent = common.ROOT / evidence["path"]
        for name in ["MANIFEST.json", *_inventory(parent)]:
            prod.bytes_once(root / "prefix" / name, (parent / name).read_bytes())
        raw = read_raw(source)
        prod.bytes_once(root / "raw/events.jsonl.gz", gzip.compress(raw, mtime=0))
        for name, value in _derive(root, raw, root / "prefix").items():
            a1.public_json(value); prod.write_once(root / name, value)
        prod.write_once(root / "MANIFEST.json", {"schema": "openweights-a2-manifest-v1", "files": _entries(_inventory(root))})
        result = verify(root)
        shutil.copytree(root, target)
    check(common.sha(target / "MANIFEST.json") == result["manifest_sha256"], "Copied manifest changed")
    return verify(target, manifest_sha256=result["manifest_sha256"])


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir"); parser.add_argument("--destination", required=True)
    parser.add_argument("--verify", action="store_true"); parser.add_argument("--manifest-sha256")
    args = parser.parse_args(argv)
    try:
        check(args.verify or args.run_dir, "Building requires --run-dir")
        result = verify(args.destination, manifest_sha256=args.manifest_sha256) if args.verify else build(args.run_dir, args.destination)
    except (ValueError, TypeError, KeyError, OSError, EOFError, Halted, subprocess.SubprocessError):
        parser.exit(1, "A2 release failed closed; original evidence retained.\n")
    print(common.canonical(result))


if __name__ == "__main__":
    main()

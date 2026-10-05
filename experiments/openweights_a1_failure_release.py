"""Post-outcome export of the exact A1 accounting interruption, with prefix replay."""

import argparse
from datetime import timedelta
from decimal import Decimal
import gzip
import json
from pathlib import Path
import shutil
import subprocess
from tempfile import TemporaryDirectory

from experiments.openrouter_swap import analysis as common_analysis, protocol as common
from experiments.openrouter_swap.ledger import Halted, _no_symlinks, read_events
from experiments.openrouter_swap.release import _load, _inventory
from experiments.openrouter_swap_openweights import analysis
from experiments.openrouter_swap_openweights_a1 import production as prod, protocol
from experiments.openrouter_swap_openweights_a1.runner import ExtensionRunner, SharedLedger
from experiments.openrouter_swap_openweights_a1.release import _scan_payloads, _allowed, _launches, _sequence

OPTIONAL = {"fixture_gate.json", "initial_audit.json", "main_admission.json"}
DERIVED = {"RELEASE.json", "screen_rows.json", "screen_analysis.json", "qualification.json",
           "main_rows.json", "main_analysis.json"}
REQUIRED = {"PLAN.json", "runtime.json", "raw/events.jsonl.gz", *DERIVED}
MAX_RAW_BYTES = 128 * 1024 * 1024


EXPECTED_RAW_SHA256 = "ee84f0d4e6387c261ad35ce7b35be1c6a05f3e11a011c33e40ba2e65930e6ef6"
EXPECTED_FREEZE = "9407bae95d759de4f64b4f34d03281164f4ecae9"
EXPECTED_OVERRUN = "gen:openweights-screen-mistral-02-final-SH"


def fixture_prefix(raw, events, plan, runtime):
    first = next(e for e in events if e["kind"] == "reserve" and e["data"]["phase"] != "fixtures")
    prefix = b"".join(raw.splitlines(keepends=True)[:first["seq"] - 1])
    if first["seq"] != 54:
        raise Halted("Expected complete 53-event fixture prefix")
    with TemporaryDirectory() as temporary:
        path = Path(temporary).resolve()
        path.joinpath("events.jsonl").write_bytes(prefix)
        cap, screen = protocol.Budget(**plan["budget"]).limits()
        with SharedLedger(path, cap=cap, screen_cap=screen) as ledger:
            runner = ExtensionRunner(plan, runtime["freeze"], runtime["plan_sha256"], ledger)
            gate = runner.require_fixtures()
    return gate, {"event_count": first["seq"] - 1, "sha256": prod.sha(prefix)}


def _derive(root, raw):
    if prod.sha(raw) != EXPECTED_RAW_SHA256:
        raise Halted("This adapter accepts only the preserved A1 failure journal")
    _scan_payloads(root, raw)
    plan, _ = prod.verify_git(root / "PLAN.json", _load(root / "runtime.json")["freeze"])
    budget = protocol.Budget(**plan["budget"])
    runtime = _load(root / "runtime.json")
    if runtime["freeze"] != EXPECTED_FREEZE:
        raise Halted("Unexpected A1 freeze")
    expected = {"freeze": runtime["freeze"], "plan_sha256": common.sha(root / "PLAN.json"),
                "plan_path": prod.PLAN, "budget": plan["budget"]}
    if common.canonical(runtime) != common.canonical(expected):
        raise Halted("Runtime binding differs")
    with TemporaryDirectory() as temporary:
        raw_root = Path(temporary).resolve(); raw_root.joinpath("events.jsonl").write_bytes(raw)
        events = read_events(raw_root / "events.jsonl")
        if not events:
            raise Halted("Saved journal absent")
        cap, screen = budget.limits()
        with SharedLedger(raw_root, cap=cap, screen_cap=screen) as ledger:
            runner = ExtensionRunner(plan, runtime["freeze"], runtime["plan_sha256"], ledger)
            audit = runner.audit()
            launches = _launches(root, plan, runtime, events)
            admitted, admission = _sequence(root, raw, plan, runtime, events, runner, launches)
            calls = ledger.rows()
            if (len(calls) != 92 or any(r["status"] != "settled" for r in calls)
                    or [r["call_id"] for r in calls if r.get("over_reservation")] != [EXPECTED_OVERRUN]):
                raise Halted("Historical failure inventory differs")
            gate, prefix = fixture_prefix(raw, events, plan, runtime)
            if ((root / "fixture_gate.json").exists()
                    and common.canonical(_load(root / "fixture_gate.json")) != common.canonical(gate)):
                raise Halted("Fixture result differs from raw receipts")
            rows = {p: runner.rows(p) for p in ("screen", "main")}
            completion = {}
            for phase, models in (("screen", list(plan["models"])), ("main", admitted)):
                try:
                    runner.require_resolved(); runner.complete(phase, models=models)
                    completion[phase] = phase != "main" or admission is not None
                except Halted:
                    completion[phase] = False
            endpoints = all(common_analysis._value(r, j, e) is not None
                            for phase, records in rows.items() for r in records
                            if phase == "screen" or r["model"] in admitted
                            for j in plan["judges"] for e in common_analysis.ENDPOINTS)
            costs = {"extension_cost_bound_usd": str(ledger.spent()),
                     "prior_cost_bound_usd": budget.prior_spend_usd,
                     "external_completion_commitments_usd": budget.external_commitments_usd,
                     "scope_cost_plus_commitments_usd": str(ledger.spent() + Decimal(budget.prior_spend_usd)
                                                            + Decimal(budget.external_commitments_usd))}
    complete = all(completion.values()) and endpoints and gate is not None and gate["pass"] and not audit["unresolved"]
    output = {"RELEASE.json": {"schema": "openweights-a1-interrupted-release-v1", "status": "complete" if complete else "incomplete",
              "freeze": runtime["freeze"], "plan_sha256": runtime["plan_sha256"], "audit": audit,
              "fixtures_pass": bool(gate and gate["pass"]), "collection_complete": completion,
              "endpoint_complete": endpoints, "admitted_models": admitted, "primary_family_size": 4,
              "amendment": plan["amendment"],
              "publication_repair": {
                  "post_outcome": True, "raw_journal_sha256": EXPECTED_RAW_SHA256,
                  "fixture_prefix": prefix, "historical_over_reservation": EXPECTED_OVERRUN,
                  "original_exporter_failure": "Fixture result differs from raw receipts",
                  "status": "technical_interruption_not_completed_screen",
                  "original_receipts_changed": False, "new_model_calls": 0},
              "costs": costs, "cost_scope": "External completion commitments are reserved, not claimed as settled costs."},
              "qualification.json": analysis.qualify(rows["screen"])}
    for phase, records in rows.items():
        output[f"{phase}_rows.json"] = records
        output[f"{phase}_analysis.json"] = analysis.analyze(records, phase)
    return output


def inspect_run(root):
    root = Path(root).absolute()
    _no_symlinks(root / "raw/events.jsonl")
    raw = (root / "raw/events.jsonl").read_bytes()
    if not raw or len(raw) > MAX_RAW_BYTES:
        raise Halted("Saved journal empty or oversized")
    return _derive(root, raw)


def verify(destination):
    root = Path(destination).absolute()
    inventory = _inventory(root)
    _allowed(set(inventory))
    directories = {parent.as_posix() for name in inventory for parent in Path(name).parents}
    if any(p.is_dir() and p.relative_to(root).as_posix() not in directories for p in root.rglob("*")):
        raise Halted("Extra release directory")
    canonical = [{"path": p, "bytes": v["size"], "sha256": v["sha256"]} for p, v in sorted(inventory.items())]
    if common.canonical(_load(root / "MANIFEST.json")) != common.canonical({"schema": "openweights-a1-interrupted-manifest-v1", "files": canonical}):
        raise Halted("Manifest inventory, size or digest differs")
    with gzip.open(root / "raw/events.jsonl.gz", "rb") as handle:
        raw = handle.read(MAX_RAW_BYTES + 1)
    if len(raw) > MAX_RAW_BYTES or raw.startswith(b"\x1f\x8b"):
        raise Halted("Oversized or nested gzip journal")
    expected = _derive(root, raw)
    if any(common.canonical(_load(root / name)) != common.canonical(value) for name, value in expected.items()):
        raise Halted("Derived release payload does not reconstruct")
    return {"pass": True, "status": expected["RELEASE.json"]["status"], "files": len(canonical)}


def build(run_dir, destination):
    source, target = Path(run_dir).absolute(), Path(destination).absolute()
    _no_symlinks(source); _no_symlinks(target)
    if target.exists() or target == source or source in target.parents:
        raise Halted("Release destination must be new and outside the live run")
    with TemporaryDirectory() as temporary:
        root = Path(temporary).resolve() / "bundle"; root.mkdir()
        names = {"PLAN.json", "runtime.json"} | {n for n in OPTIONAL if (source / n).exists()}
        names.update(p.relative_to(source).as_posix() for p in (source / "launches").glob("*.json"))
        for name in names:
            path = source / name; _no_symlinks(path)
            prod.bytes_once(root / name, path.read_bytes())
        _no_symlinks(source / "raw/events.jsonl")
        raw = (source / "raw/events.jsonl").read_bytes()
        if not raw or len(raw) > MAX_RAW_BYTES:
            raise Halted("Saved journal empty or oversized")
        prod.bytes_once(root / "raw/events.jsonl.gz", gzip.compress(raw, mtime=0))
        for name, value in _derive(root, raw).items():
            prod.public_json(value)
            prod.write_once(root / name, value)
        inventory = _inventory(root)
        prod.write_once(root / "MANIFEST.json", {"schema": "openweights-a1-interrupted-manifest-v1", "files": [
            {"path": p, "bytes": v["size"], "sha256": v["sha256"]} for p, v in sorted(inventory.items())]})
        result = verify(root)
        shutil.copytree(root, target)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir")
    parser.add_argument("--destination", required=True)
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args(argv)
    if not args.verify and not args.run_dir:
        parser.error("Building requires --run-dir")
    try:
        result = verify(args.destination) if args.verify else build(args.run_dir, args.destination)
    except (ValueError, KeyError, TypeError, OSError, EOFError, Halted, subprocess.SubprocessError):
        parser.exit(1, "Release operation failed closed; original artifacts retained.\n")
    print(common.canonical(result))


if __name__ == "__main__":
    main()

"""Offline explicit-inventory release and read-only saved-receipt verification."""

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
from . import production as prod, protocol
from .runner import ExtensionRunner, SharedLedger

OPTIONAL = {"fixture_gate.json", "initial_audit.json", "main_admission.json"}
DERIVED = {"RELEASE.json", "screen_rows.json", "screen_analysis.json", "qualification.json",
           "main_rows.json", "main_analysis.json"}
REQUIRED = {"PLAN.json", "runtime.json", "raw/events.jsonl.gz", *DERIVED}
MAX_RAW_BYTES = 128 * 1024 * 1024


def _scan_payloads(root, raw):
    if prod.public_audit.scan_blob("raw/events.jsonl", raw):
        raise Halted("Public content scan failed")
    for line in raw.splitlines():
        prod.public_json(json.loads(line))
    for path in root.rglob("*.json"):
        _no_symlinks(path)
        if prod.public_audit.scan_blob(path.relative_to(root).as_posix(), path.read_bytes()):
            raise Halted("Public content scan failed")
        prod.public_json(_load(path))


def _allowed(names):
    if not REQUIRED <= names:
        raise Halted("Required release payload absent")
    for name in names - REQUIRED - OPTIONAL:
        p = Path(name)
        if p.parent.as_posix() != "launches" or p.suffix != ".json" or not prod._hex(p.stem):
            raise Halted("Extra or private release payload")


def _launches(root, plan, runtime, events):
    launches = []
    budget = protocol.Budget(**plan["budget"])
    for path in sorted((root / "launches").glob("*.json")):
        record = _load(path)
        if (path.stem != common.digest(record) or set(record) != {
                "phase", "proof", "reconciliation", "plan_sha256", "event_count_before", "checked_at_utc"}
                or record["phase"] not in prod.PHASES or record["plan_sha256"] != runtime["plan_sha256"]
                or type(record["event_count_before"]) is not int
                or not 1 <= record["event_count_before"] <= len(events)):
            raise Halted("Launch record differs")
        proof = record["proof"]
        if (set(proof) != {"freeze", "branch", "remote_head"} or proof["freeze"] != runtime["freeze"]
                or proof["branch"] != prod.BRANCH or not prod._hex(proof["remote_head"], 40)):
            raise Halted("Recorded pushed proof missing")
        subprocess.check_output(["git", "merge-base", "--is-ancestor", runtime["freeze"], proof["remote_head"]],
                                cwd=common.ROOT, stderr=subprocess.DEVNULL)
        prod.reconcile(budget, record["reconciliation"])
        checked = prod._date(record["checked_at_utc"])
        evidence = [(record["reconciliation"]["as_of_utc"], 1)]
        evidence += [(r["checked_at_utc"], 7) for r in plan["endpoint_evidence"].values()]
        if any(not timedelta(0) <= checked - prod._date(t) <= timedelta(days=d) for t, d in evidence):
            raise Halted("Evidence was not current at launch")
        launches.append(record)
    return launches


def _sequence(root, raw, plan, runtime, events, runner, launches):
    for kind in ("initial_audit", "main_admission"):
        path = root / (kind + ".json")
        if path.exists():
            prod.verify_checkpoint(raw, _load(path), plan, runtime, kind)
    initial = _load(root / "initial_audit.json") if (root / "initial_audit.json").exists() else None
    admission = _load(root / "main_admission.json") if (root / "main_admission.json").exists() else None
    admitted = admission["value"]["admitted_models"] if admission else []
    costs, current_model, first_target = {}, None, True
    for event in events:
        d = event["data"]
        if event["kind"] == "settle":
            costs[d["call_id"]] = Decimal(d["cost_usd"])
        if event["kind"] != "reserve":
            continue
        costs[d["call_id"]] = Decimal(d["cost_usd"])
        eligible = [r for r in launches if r["event_count_before"] < event["seq"]]
        if not eligible:
            raise Halted("Call lacks a preceding launch record")
        latest = max(r["event_count_before"] for r in eligible)
        phases = {r["phase"] for r in eligible if r["event_count_before"] == latest}
        phase = d["phase"]
        if phase == "fixtures":
            if "fixtures" not in phases or not first_target:
                raise Halted("Fixture dispatch outside its stage")
            continue
        if first_target:
            prefix = b"".join(raw.splitlines(keepends=True)[:event["seq"]-1])
            with TemporaryDirectory() as temporary:
                p = Path(temporary).resolve(); p.joinpath("events.jsonl").write_bytes(prefix)
                cap, screen = runner.budget.limits()
                with SharedLedger(p, cap=cap, screen_cap=screen) as ledger:
                    ExtensionRunner(plan, runtime["freeze"], runtime["plan_sha256"], ledger).require_fixtures()
            first_target = False
        item = runner.catalog[d["metadata"]["item_id"]]
        if phase == "screen":
            initial_dispatch = "screen-initial" in phases and item["block"] <= 2
            completion_dispatch = ("screen" in phases and initial is not None and initial["event_count"] < event["seq"])
            if not initial_dispatch and not completion_dispatch:
                raise Halted("Screen dispatch outside declared checkpoint")
            if item["block"] > 2 and (initial is None or initial["event_count"] >= event["seq"]):
                raise Halted("Screen completion lacks its earlier technical audit")
            if current_model is not None:
                raise Halted("Screen dispatch after main started")
        elif phase == "main":
            model = item["model"]
            if ("main" not in phases or not admission or not initial or model not in admitted
                    or admission["event_count"] >= event["seq"] or initial["event_count"] >= event["seq"]):
                raise Halted("Main call lacks prospective admission")
            if current_model is not None and admitted.index(model) < admitted.index(current_model):
                raise Halted("Main model order changed")
            if model != current_model and admitted.index(model) > 0:
                prefix = b"".join(raw.splitlines(keepends=True)[:event["seq"]-1])
                with TemporaryDirectory() as temporary:
                    p = Path(temporary).resolve(); p.joinpath("events.jsonl").write_bytes(prefix)
                    cap, screen = runner.budget.limits()
                    with SharedLedger(p, cap=cap, screen_cap=screen) as ledger:
                        ExtensionRunner(plan, runtime["freeze"], runtime["plan_sha256"], ledger).complete(
                            "main", models=admitted[:admitted.index(model)])
            current_model = model
            hold = sum((Decimal(admission["value"]["projections"][m]["projected_cost_with_reserve_usd"])
                        for m in admitted[admitted.index(model)+1:]), Decimal(0))
            if sum(costs.values()) + hold > runner.ledger.cap:
                raise Halted("Reservation consumed a later model's forecast")
        else:
            raise Halted("Unknown paid phase")
    return admitted, admission


def _derive(root, raw):
    _scan_payloads(root, raw)
    plan, _ = prod.verify_git(root / "PLAN.json", _load(root / "runtime.json")["freeze"])
    budget = protocol.Budget(**plan["budget"])
    runtime = _load(root / "runtime.json")
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
            try:
                gate = runner.run_fixtures()
            except Halted:
                gate = None
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
    output = {"RELEASE.json": {"schema": "openweights-a1-release-v1", "status": "complete" if complete else "incomplete",
              "freeze": runtime["freeze"], "plan_sha256": runtime["plan_sha256"], "audit": audit,
              "fixtures_pass": bool(gate and gate["pass"]), "collection_complete": completion,
              "endpoint_complete": endpoints, "admitted_models": admitted, "primary_family_size": 4,
              "amendment": plan["amendment"],
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
    if common.canonical(_load(root / "MANIFEST.json")) != common.canonical({"schema": "openweights-a1-manifest-v1", "files": canonical}):
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
        prod.write_once(root / "MANIFEST.json", {"schema": "openweights-a1-manifest-v1", "files": [
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

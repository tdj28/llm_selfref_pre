"""Offline immutable release and replay verification; never dispatch or retry."""

import argparse
from contextlib import contextmanager
from decimal import Decimal
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
from tempfile import TemporaryDirectory

from experiments.openrouter_swap import analysis as labels
from experiments.openrouter_swap.ledger import Halted, _no_symlinks, read_events
from experiments.openrouter_swap.release import _inventory, _load
from scripts import audit_public_release as public_audit
from . import analysis, production, protocol as p
from .runner import Runner, StudyLedger

OPTIONAL = {"fixture_gate.json", "admission.json"}
DERIVED = {"RELEASE.json", "rows.json", "analysis.json", "audit.json"}
REQUIRED = {"PLAN.json", "runtime.json", "raw/events.jsonl.gz", *DERIVED}
MAX_RAW_BYTES = 128 * 1024 * 1024


def _check(condition, message):
    if not condition:
        raise Halted(message)


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for key, item in value.items():
            yield from _strings(key)
            yield from _strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from _strings(item)


def _public(value):
    for text in (p.canonical(value), "\n".join(_strings(value))):
        _check(not public_audit.scan_bytes("release.json", text.encode()), "Private release content")


def _write(path, value):
    _public(value)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as handle:
        handle.write((p.canonical(value) + "\n").encode())


def _git_blob(freeze, name):
    return subprocess.check_output(["git", "--no-replace-objects", "show", f"{freeze}:{name}"],
        cwd=p.ROOT, env={**os.environ, "GIT_NO_LAZY_FETCH": "1"},
        stderr=subprocess.DEVNULL, timeout=30)


def _plan(root):
    # verify(path, freeze) checks the remote; publication is deliberately offline.
    plan = p.verify(root / "PLAN.json")
    runtime = _load(root / "runtime.json")
    freeze = runtime.get("freeze")
    _check(isinstance(freeze, str) and re.fullmatch(r"[0-9a-f]{40}", freeze), "Invalid freeze")
    _check(runtime == {"freeze": freeze, "plan_sha256": p.sha(root / "PLAN.json"),
                      "new_authorization_usd": "130", "external_api_reserve_usd": "45"},
           "Runtime binding differs")
    _check(_git_blob(freeze, p.PLAN) == (root / "PLAN.json").read_bytes(), "Frozen plan differs")
    for name, expected in plan["source_hashes"].items():
        _check(_sha(_git_blob(freeze, name)) == expected, "Frozen source differs")
    return plan, runtime


@contextmanager
def _replay(raw, plan, runtime):
    _check(raw and raw.endswith(b"\n") and len(raw) <= MAX_RAW_BYTES, "Empty, torn or oversized journal")
    with TemporaryDirectory(prefix="repeated-swap-replay-") as temporary:
        root = Path(temporary).resolve()
        (root / "events.jsonl").write_bytes(raw)
        events = read_events(root / "events.jsonl")
        for event in events:
            _public(event)
        with StudyLedger(root, cap=plan["cap_usd"], screen_cap=plan["screen_cap_usd"]) as ledger:
            yield Runner(plan, runtime["freeze"], runtime["plan_sha256"], ledger), events


def _sequence(root, raw, plan, runtime, runner, events):
    first_main = next((i for i, e in enumerate(events) if e["kind"] == "reserve"
                       and e["data"]["phase"] == "main"), len(events))
    lines = raw.splitlines(keepends=True)
    with _replay(b"".join(lines[:first_main]), plan, runtime) as (prior, _):
        try:
            gate = prior.run_fixtures()
        except Halted:
            gate = None
    if (root / "fixture_gate.json").exists():
        _check(gate is not None and p.canonical(_load(root / "fixture_gate.json")) == p.canonical(gate),
               "Fixture gate does not reconstruct at research boundary")
    if first_main < len(events):
        _check(gate is not None and gate["pass"] and (root / "fixture_gate.json").exists(),
               "Research lacks its earlier fixture gate")

    admission, cutoff = None, len(events)
    if (root / "admission.json").exists():
        admission = _load(root / "admission.json")
        prefix = admission.get("journal_prefix", {})
        _check(set(prefix) == {"bytes", "sha256", "calls"}
               and type(prefix["bytes"]) is int and 0 < prefix["bytes"] <= len(raw)
               and type(prefix["calls"]) is int and prefix["calls"] >= 0,
               "Invalid admission prefix")
        before = raw[:prefix["bytes"]]
        _check(_sha(before) == prefix["sha256"], "Admission prefix hash differs")
        credit = Decimal(admission["credit_snapshot_usd"])
        _check(credit.is_finite() and credit >= 0, "Invalid admission credit snapshot")
        with _replay(before, plan, runtime) as (prior, history):
            _check(len(prior.ledger.rows()) == prefix["calls"], "Admission prefix call count differs")
            expected = prior.admission(admission["credit_snapshot_usd"])
            expected["journal_prefix"] = prefix
            _check(p.canonical(admission) == p.canonical(expected), "Admission forecast does not reconstruct")
            cutoff = len(history)

    costs = {}
    for index, event in enumerate(events[1:], 1):
        row = event["data"]
        if event["kind"] == "reserve":
            if index < cutoff:
                _check(sum(costs.values()) + Decimal(row["cost_usd"]) <= Decimal("15"),
                       "Initial dispatch exceeded stage allowance")
            if row["phase"] == "fixtures":
                _check(index < first_main, "Fixture dispatch after research began")
            else:
                _check(row["phase"] == "main", "Unexpected study phase")
                item = runner.catalog[row["metadata"]["item_id"]]
                if item["block"] > 2:
                    _check(admission is not None and admission["pass"] is True and index >= cutoff,
                           "Bulk dispatch preceded passed admission")
                else:
                    _check(index < cutoff, "Initial dispatch occurred after admission")
        costs[row["call_id"]] = Decimal(row["cost_usd"])
    return bool(gate and gate["pass"]), admission


def _derive(root):
    plan, runtime = _plan(root)
    for name in {"PLAN.json", "runtime.json", *OPTIONAL}:
        if (root / name).exists():
            _public(_load(root / name))
    with gzip.open(root / "raw/events.jsonl.gz", "rb") as stream:
        raw = stream.read(MAX_RAW_BYTES + 1)
    with _replay(raw, plan, runtime) as (runner, events):
        audit = runner.audit()
        fixtures_pass, admission = _sequence(root, raw, plan, runtime, runner, events)
        rows = runner.rows("main")
        try:
            runner.require_resolved()
            runner.require_complete()
            complete = fixtures_pass and admission is not None and admission["pass"] is True
        except Halted:
            complete = False
        endpoints = all(labels._value(row, judge, endpoint) is not None
                        for row in rows for judge in plan["judges"] for endpoint in analysis.ENDPOINTS)
        records = runner.ledger.rows()
        metadata = {"schema": "repeated-swap-release-v1", "status": "complete" if complete and endpoints else "incomplete",
            "freeze": runtime["freeze"], "plan_sha256": runtime["plan_sha256"],
            "collection_complete": complete, "endpoint_complete": endpoints,
            "fixtures_pass": fixtures_pass, "admission_pass": admission["pass"] if admission else None,
            "main_status": "not_run" if not any(r["phase"] == "main" for r in records) else "completed" if complete else "incomplete",
            "journal": {"bytes": len(raw), "sha256": _sha(raw), "events": len(events), "calls": len(records)},
            "cost_bound_usd": str(runner.ledger.spent()), "unknown_charges_are_reserved": True,
            "unresolved": audit["unresolved"], "primary_judge": "astra", "primary_family_size": 2,
            "primary_individual_confidence": 0.975, "nominal_family_confidence": 0.95,
            "publication_scope": "Saved observations, missingness and technical failures; no new calls or labels"}
    return {"RELEASE.json": metadata, "rows.json": rows, "analysis.json": analysis.analyze(rows), "audit.json": audit}


def _entries(root):
    return [{"path": name, "bytes": v["size"], "sha256": v["sha256"]}
            for name, v in sorted(_inventory(root).items())]


def verify(destination, *, manifest_sha256=None):
    root = Path(destination).absolute()
    inventory = _inventory(root)
    _check(REQUIRED <= set(inventory) <= REQUIRED | OPTIONAL, "Unexpected public release inventory")
    _check(all(not path.is_dir() or path.relative_to(root).as_posix() == "raw"
               for path in root.rglob("*")), "Unexpected release directory")
    manifest = _load(root / "MANIFEST.json")
    _check(manifest == {"schema": "repeated-swap-manifest-v1", "files": _entries(root)}
           and (root / "MANIFEST.json").read_bytes() == (p.canonical(manifest) + "\n").encode(),
           "Manifest inventory, hashes or encoding differ")
    if manifest_sha256 is not None:
        _check(p.sha(root / "MANIFEST.json") == manifest_sha256, "External manifest anchor differs")
    expected = _derive(root)
    _check(all(p.canonical(_load(root / name)) == p.canonical(value) for name, value in expected.items()),
           "Saved derived payload does not reconstruct")
    return {"pass": True, "status": expected["RELEASE.json"]["status"], "files": len(inventory),
            "manifest_sha256": p.sha(root / "MANIFEST.json"), "unresolved": expected["audit.json"]["unresolved"]}


def build(destination, *, run_dir=None):
    source = Path(production.root_path()).absolute()
    if run_dir is not None:
        _check(Path(run_dir).absolute() == source, "Export requires the canonical operational root")
    target = Path(destination).absolute()
    _no_symlinks(source); _no_symlinks(target)
    _check(not target.exists() and source not in target.parents and target not in source.parents,
           "Destination must be new and outside the run")
    paths = {"PLAN.json": p.ROOT / p.PLAN, "runtime.json": source / "runtime.json"}
    paths.update({n: source / n for n in OPTIONAL if (source / n).exists() or (source / n).is_symlink()})
    paths["raw/events.jsonl"] = source / "raw/events.jsonl"
    for path in paths.values():
        _no_symlinks(path)
    originals = {name: path.read_bytes() for name, path in paths.items()}
    with TemporaryDirectory(prefix="repeated-swap-release-") as temporary:
        root = Path(temporary).resolve() / "bundle"; root.mkdir()
        for name, data in originals.items():
            if name == "raw/events.jsonl":
                name, data = name + ".gz", gzip.compress(data, mtime=0)
            path = root / name; path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        for name, value in _derive(root).items():
            _write(root / name, value)
        _write(root / "MANIFEST.json", {"schema": "repeated-swap-manifest-v1", "files": _entries(root)})
        result = verify(root)
        _check(all(path.read_bytes() == originals[name] for name, path in paths.items()),
               "Operational inputs changed during export")
        _no_symlinks(target)
        shutil.copytree(root, target)
    _check(_entries(target) == _load(target / "MANIFEST.json")["files"]
           and p.sha(target / "MANIFEST.json") == result["manifest_sha256"], "Copied release differs")
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--destination", required=True)
    parser.add_argument("--run-dir", help="Must equal production.root_path(); omitted by default")
    parser.add_argument("--verify", action="store_true")
    parser.add_argument("--manifest-sha256")
    args = parser.parse_args(argv)
    try:
        result = (verify(args.destination, manifest_sha256=args.manifest_sha256) if args.verify
                  else build(args.destination, run_dir=args.run_dir))
    except (Halted, ValueError, TypeError, KeyError, ArithmeticError, OSError, EOFError, subprocess.SubprocessError):
        parser.exit(1, "Repeated-swap release failed closed; original records retained.\n")
    print(p.canonical(result))


if __name__ == "__main__":
    main()

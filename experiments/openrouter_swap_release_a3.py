"""Offline A3 release, preserving all prior failures and the reused A2 gate."""

from __future__ import annotations

import argparse
from decimal import Decimal
import gzip
from pathlib import Path
import shutil
import subprocess
from tempfile import TemporaryDirectory

from experiments.openrouter_swap import analysis, protocol
from experiments.openrouter_swap.ledger import Halted, Ledger, _no_symlinks, read_events
from experiments.openrouter_swap.release import _figures, _inventory, _load, _write, cell_counts
from experiments.openrouter_swap_a1.release import _unpack
from experiments.openrouter_swap_a2 import amendment as a2
from experiments.openrouter_swap_a2 import release as a2_release
from experiments.openrouter_swap_a3 import amendment


SNAPSHOTS = a2_release.SNAPSHOTS
ACTIVE = a2_release.ACTIVE
OPTIONAL = frozenset({"main_admission.json"})


def _bindings(plan):
    bindings = plan["prior_attempts"]
    if (bindings != list(amendment.PRIORS) or len(bindings) != 3
            or [(p["label"], p["path"]) for p in bindings] !=
            [("original", "."), ("a1", "a1"), ("a2", "a2")]
            or any(type(p["calls"]) is not int or p["calls"] != calls
                   or type(p["target_calls"]) is not int or p["target_calls"] != 0
                   or type(p.get("unresolved", 1)) is not int
                   or p.get("unresolved", 1) != unresolved
                   for p, calls, unresolved in zip(bindings, (12, 12, 27), (1, 1, 0)))):
        raise ValueError("Prior chain binding mismatch")
    total = sum((Decimal(p["cost_bound_usd"]) for p in bindings), Decimal(0))
    if (total != Decimal("0.62048546") or Decimal(plan["prior_cost_usd"]) != total
            or Decimal(plan["cap_usd"]) + total != Decimal("250")
            or Decimal(plan["screen_cap_usd"]) + total != Decimal("40")):
        raise ValueError("Amended caps do not retain all prior costs")
    return bindings


def _priors(root, temporary, plan):
    bindings = _bindings(plan)
    binding = bindings[2]
    prior = root / "prior_attempts/a2"
    old_plan = _load(prior / "PLAN.json")
    runtime = a2_release._runtime(prior, binding["plan_path"])
    if any(runtime[key] != binding[key] for key in ("freeze", "plan_sha256")):
        raise ValueError("Prior runtime binding mismatch")
    if (old_plan["prior_attempts"] != bindings[:2]
            or runtime["prior_attempts"] != bindings[:2]
            or Decimal(runtime["prior_cost_bound_usd"]) != Decimal(old_plan["prior_cost_usd"])):
        raise ValueError("A2 prior chain mismatch")
    reports = a2_release._priors(root, temporary, old_plan)
    raw = _unpack(prior / "events.jsonl.gz", temporary / "a2")
    if protocol.sha(raw / "events.jsonl") != binding["journal_sha256"]:
        raise ValueError("Prior journal hash mismatch")
    with Ledger(raw, cap=old_plan["cap_usd"], screen_cap=old_plan["screen_cap_usd"]) as ledger:
        runner = a2.IndependentRunner(old_plan, runtime["freeze"], runtime["plan_sha256"],
                                      ledger, sender=None)
        audit = runner.audit()
        if any(row["phase"] != "fixtures" or row["metadata"]["kind"] == "generation"
               for row in ledger.rows()):
            raise ValueError("Prior attempt contains target calls")
        if (audit["calls"] != 27 or audit["unresolved"] != 0
                or ledger.spent() != Decimal(binding["cost_bound_usd"])):
            raise ValueError("Prior attempt accounting mismatch")
        original_gate = runner.run_fixtures()
    gate = amendment.adjudicate_gate(original_gate)
    gemini = [route for route in original_gate["routes"]
              if route["model"] == protocol.MODELS["gemini"]["id"]]
    if (original_gate["pass"] is not False or original_gate["judges"]["pass"] is not True
            or len(original_gate["rows"]) != 24 or len(gemini) != 1
            or gemini[0]["response"].strip() != "OK." or gemini[0]["pass"] is not False
            or gate["pass"] is not True):
        raise ValueError("Reconstructed A2 gate differs from recorded punctuation failure")
    reports.append({**binding, "audit": audit, "fixture_gate": original_gate})
    return reports, gate


def _collection_inventory(plan, rows, calls, admission):
    """Receipt counts are descriptive, independently of endpoint availability."""
    catalog = {s["id"]: s for phase in ("screen", "main") for block in plan[phase]
               for kind in ("sources", "finals") for s in block[kind]}
    result = {}
    for phase, items in rows.items():
        result[phase] = {}
        for model in protocol.MODELS:
            blocks = [b for b in plan[phase] if b["model"] == model]
            observed = [c for c in calls if c["phase"] == phase
                        and catalog[c["metadata"]["item_id"]]["model"] == model]
            selected = [row for row in items if row["model"] == model]
            entry = {"scheduled": (False if model not in ACTIVE else True if phase == "screen"
                                   else None if admission is None else model in admission["admitted_models"]),
                     "unresolved_calls": sum(c["status"] != "settled" for c in observed),
                     "missing_final_responses": sum(r["response"] is None for r in selected),
                     "missing_endpoint_labels": sum(analysis._value(r, j, e) is None for r in selected
                                                    for j in plan["judges"] for e in analysis.ENDPOINTS)}
            for role, name in (("source", "sources"), ("final", "finals")):
                generation = [c for c in observed if c["metadata"]["kind"] == "generation"
                              and c["metadata"]["role"] == role]
                entry[name] = {"planned": sum(len(b[name]) for b in blocks), "requested": len(generation),
                               "settled": sum(c["status"] == "settled" for c in generation)}
            judging = [c for c in observed if c["metadata"]["kind"] == "judge"]
            entry["judgments"] = {"planned_slots": len(selected) * len(plan["judges"]) * 2,
                                  "requested_calls": len(judging),
                                  "settled_calls": sum(c["status"] == "settled" for c in judging),
                                  "requested_slots": len({(c["metadata"]["item_id"], c["metadata"]["judge"],
                                                           c["metadata"]["instrument"]) for c in judging})}
            result[phase][model] = entry
    return result


def _replay(root):
    _load(root / "PLAN.json")
    # Omit freeze here: execution verification also contacts the remote branch.
    plan = amendment.verify(root / "PLAN.json")
    _bindings(plan)
    if set(plan["models"]) != ACTIVE:
        raise ValueError("Invalid active model roster")
    runtime = a2_release._runtime(root, amendment.PLAN)
    freeze, plan_hash = runtime["freeze"], runtime["plan_sha256"]
    if (Decimal(runtime["prior_cost_bound_usd"]) != Decimal(plan["prior_cost_usd"])
            or runtime["prior_attempts"] != plan["prior_attempts"]):
        raise ValueError("Runtime prior-attempt binding mismatch")
    admission = (a2_release._public_json(root / "main_admission.json")
                 if (root / "main_admission.json").exists() else None)
    admitted = admission["admitted_models"] if admission is not None else []
    if (not isinstance(admitted, list) or len(set(admitted)) != len(admitted)
            or set(admitted) - ACTIVE):
        raise ValueError("Invalid main selection")
    with TemporaryDirectory() as temporary:
        temporary = Path(temporary).resolve()
        priors, fixture_gate = _priors(root, temporary, plan)
        if a2_release._public_json(root / "fixture_gate.json") != fixture_gate:
            raise ValueError("Fixture gate does not reconstruct")
        raw = _unpack(root / "raw/events.jsonl.gz", temporary / "raw")
        with Ledger(raw, cap=plan["cap_usd"], screen_cap=plan["screen_cap_usd"]) as ledger:
            runner = amendment.A3Runner(plan, freeze, plan_hash, ledger, sender=None,
                                        fixture_gate=fixture_gate)
            audit = runner.audit()
            calls = ledger.rows()
            if any(row["phase"] not in {"screen", "main"} for row in calls):
                raise ValueError("A3 journal must contain new targets only")
            main_started = any(row["phase"] == "main" for row in calls)
            if main_started and admission is None:
                raise ValueError("Main receipts lack admission")
            if any(row["phase"] == "main" and
                   runner.catalog[row["metadata"]["item_id"]]["model"] not in admitted
                   for row in calls):
                raise ValueError("Main receipts include an unadmitted model")
            if admission is not None:
                events = read_events(raw / "events.jsonl")
                cutoff = next((i for i, event in enumerate(events) if event["kind"] == "reserve"
                               and event["data"]["phase"] == "main"), len(events))
                history_root = temporary / "admission"
                history_root.mkdir()
                (history_root / "events.jsonl").write_bytes(
                    b"".join((raw / "events.jsonl").read_bytes().splitlines(True)[:cutoff]))
                with Ledger(history_root, cap=plan["cap_usd"], screen_cap=plan["screen_cap_usd"]) as history:
                    expected = amendment.A3Runner(plan, freeze, plan_hash, history, sender=None,
                                                  fixture_gate=fixture_gate).main_admission()
                if admission != expected:
                    raise ValueError("Main admission does not reconstruct")
            # Full inventories include deferred and unadmitted models as missing.
            rows = {phase: runner.rows(phase) for phase in ("screen", "main")}
            screen_cost = ledger.spent("screen")
    phase_complete = {}
    for phase, models in (("screen", ACTIVE), ("main", admitted)):
        phase_complete[phase] = all(
            analysis._value(row, judge, endpoint) is not None
            for row in rows[phase] if row["model"] in models
            for judge in plan["judges"] for endpoint in analysis.ENDPOINTS
        ) and not any(row["phase"] == phase and
                      (row["status"] != "settled" or row.get("over_reservation")) for row in calls)
    phases = {"screen": "complete" if phase_complete["screen"] else "incomplete",
              "main": ("pending_admission" if admission is None else "not_admitted" if not admitted
                       else "complete" if phase_complete["main"] else "incomplete")}
    current_phase = "main" if main_started or admitted else "screen"
    complete = (phase_complete["screen"] and admission is not None and phase_complete["main"]
                and not audit["unresolved"])
    cumulative = Decimal(plan["prior_cost_usd"]) + Decimal(audit["cost_bound_usd"])
    if cumulative > Decimal("250") or Decimal(plan["prior_cost_usd"]) + screen_cost > Decimal("40"):
        raise ValueError("Cumulative cost cap exceeded")
    metadata = {"schema": "openrouter-swap-a3-release-v1", "freeze": freeze, "plan_sha256": plan_hash,
                "status": "complete" if complete else "incomplete", "fixtures_pass": fixture_gate["pass"],
                "fixture_gate": fixture_gate, "phase_status": phases, "current_phase": current_phase,
                "current_phase_status": phases[current_phase],
                "completion_scope": "all scheduled active-model endpoint labels; main requires recorded admission",
                "status_definition": "Endpoint completeness, not API collection completion; settled refusals may leave it incomplete.",
                "collection_inventory": _collection_inventory(plan, rows, calls, admission),
                "active_models": list(plan["models"]), "admitted_models": admitted,
                "deferred_models": {"deepseek": {**plan["deferred_models"]["deepseek"], "target_calls": 0}},
                "prior_attempts": priors, "prior_cost_bound_usd": plan["prior_cost_usd"],
                "attempt_cost_bound_usd": audit["cost_bound_usd"],
                "cumulative_cost_bound_usd": str(cumulative), "audit": audit}
    reporting = {**plan, "models": _load(root / "prior_attempts/original/PLAN.json")["models"]}
    return metadata, rows, reporting


def _allowed_inventory(files):
    required = {"PLAN.json", "runtime.json", "fixture_gate.json", "raw/events.jsonl.gz",
                "RELEASE.json", "FIGURE_COUNTS.json"}
    required.update(f"prior_attempts/{label}/{name}" for label in ("original", "a1", "a2")
                    for name in ("PLAN.json", "runtime.json", "events.jsonl.gz"))
    required.update(f"{phase}_{judge}_inclusive.{extension}" for phase in ("screen", "main")
                    for judge in ("astra", "opus") for extension in ("png", "pdf"))
    snapshots = set()
    for name in set(files) - required - OPTIONAL:
        parts = Path(name).parts
        if len(parts) != 3 or parts[0] != "snapshots" or not parts[1].isdecimal() or parts[2] not in SNAPSHOTS:
            raise ValueError("Artifact is outside the publication allowlist")
        snapshots.add(parts[1])
    if not required <= set(files) or len(snapshots) > 1:
        raise ValueError("Release artifact inventory is incomplete or ambiguous")


def _manifest_files(inventory):
    return [{"path": name, "bytes": entry["size"], "sha256": entry["sha256"]}
            for name, entry in sorted(inventory.items())]


def verify(destination):
    """Read-only exact inventory, source, receipt, gate and cumulative cost audit."""
    root = Path(destination).absolute()
    manifest = _load(root / "MANIFEST.json")
    if set(manifest) != {"schema", "files"} or manifest["schema"] != "openrouter-swap-a3-manifest-v1":
        raise ValueError("Invalid manifest")
    inventory = _inventory(root)
    if (manifest["files"] != _manifest_files(inventory)
            or any(type(entry["bytes"]) is not int for entry in manifest["files"])):
        raise ValueError("Release inventory or hash mismatch")
    _allowed_inventory(inventory)
    for name in inventory:
        if name.endswith(".json") and not name.endswith("PLAN.json"):
            a2_release._public_json(root / name)
    metadata, rows, plan = _replay(root)
    if _load(root / "RELEASE.json") != metadata:
        raise ValueError("Release audit does not reconstruct")
    counts = {f"{phase}_{judge}_inclusive": cell_counts(items, plan["models"],
              list(protocol.CELLS)[:4] if phase == "screen" else protocol.CELLS, judge)
              for phase, items in rows.items() for judge in ("astra", "opus")}
    if _load(root / "FIGURE_COUNTS.json") != counts:
        raise ValueError("Figure counts do not reconstruct")
    return {"pass": True, "status": metadata["status"], "files": len(manifest["files"]),
            "current_phase": metadata["current_phase"], "current_phase_status": metadata["current_phase_status"]}


def build(run_dir, destination):
    """Copy an explicit allowlist; all four journals retain their original bytes."""
    source, target = Path(run_dir).absolute(), Path(destination).absolute()
    _no_symlinks(source)
    _no_symlinks(target)
    if target.exists():
        raise FileExistsError("Release destination already exists")
    plan = amendment.verify(protocol.ROOT / amendment.PLAN)
    sources = {"PLAN.json": protocol.ROOT / amendment.PLAN, "runtime.json": source / "runtime.json",
               "fixture_gate.json": source / "fixture_gate.json", "raw/events.jsonl.gz": source / "raw/events.jsonl"}
    for prior in _bindings(plan):
        prefix = "prior_attempts/" + prior["label"]
        prior_root = source.parent / prior["path"]
        sources.update({prefix + "/PLAN.json": protocol.ROOT / prior["plan_path"],
                        prefix + "/runtime.json": prior_root / "runtime.json",
                        prefix + "/events.jsonl.gz": prior_root / "raw/events.jsonl"})
    for name in OPTIONAL:
        if (source / name).exists() or (source / name).is_symlink():
            sources[name] = source / name
    _no_symlinks(source / "snapshots")
    snapshots = [p for p in (source / "snapshots").glob("*") if p.name.isdecimal()]
    if snapshots:
        latest = max(snapshots, key=lambda p: int(p.name))
        _no_symlinks(latest)
        for name in SNAPSHOTS:
            path = latest / name
            if path.exists() or path.is_symlink():
                sources[path.relative_to(source).as_posix()] = path
    with TemporaryDirectory() as temporary:
        root = Path(temporary).resolve() / "bundle"
        root.mkdir()
        for name, path in sources.items():
            _no_symlinks(path)
            if not path.is_file():
                raise ValueError("Nonregular source artifact")
            output = root / name
            output.parent.mkdir(parents=True, exist_ok=True)
            if name.endswith("events.jsonl.gz"):
                with path.open("rb") as handle, output.open("xb") as compressed:
                    with gzip.GzipFile(filename="", fileobj=compressed, mode="wb", mtime=0) as archive:
                        shutil.copyfileobj(handle, archive)
            else:
                if not name.endswith("PLAN.json"):
                    a2_release._public_json(path)
                shutil.copyfile(path, output)
        metadata, rows, reporting = _replay(root)
        _write(root / "RELEASE.json", metadata)
        _figures(root, rows, reporting)
        _write(root / "MANIFEST.json", {"schema": "openrouter-swap-a3-manifest-v1",
                                       "files": _manifest_files(_inventory(root))})
        result = verify(root)
        shutil.copytree(root, target)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", help="A3 directory; original, a1 and a2 remain in its parent")
    parser.add_argument("--destination", required=True)
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    if not args.verify and not args.run_dir:
        parser.error("Building requires --run-dir")
    try:
        result = verify(args.destination) if args.verify else build(args.run_dir, args.destination)
    except (ValueError, OSError, EOFError, Halted, KeyError, TypeError, subprocess.SubprocessError) as error:
        parser.exit(1, f"Release operation failed ({type(error).__name__}); original artifacts retained.\n")
    print(protocol.canonical(result))


if __name__ == "__main__":
    main()

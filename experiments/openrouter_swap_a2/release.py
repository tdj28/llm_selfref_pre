"""Offline A2 release with both failed attempts and deferred-model missingness."""

from __future__ import annotations

import argparse
from decimal import Decimal
import gzip
import hashlib
from pathlib import Path
import shutil
import subprocess
from tempfile import TemporaryDirectory

from experiments.openrouter_swap import analysis, protocol
from experiments.openrouter_swap.ledger import Halted, Ledger, _no_symlinks, read_events
from experiments.openrouter_swap.providers import _public_body
from experiments.openrouter_swap.release import _figures, _inventory, _load, _write, cell_counts
from experiments.openrouter_swap.runner import Runner
from experiments.openrouter_swap_a1.release import _unpack

from . import amendment


SNAPSHOTS = frozenset({"audit.json", "screen_rows.json", "main_rows.json", "main_inventory.json",
                       "screen_analysis.json", "main_analysis.json", "qualification.json"})
OPTIONAL = frozenset({"fixture_gate.json", "main_admission.json"})
ACTIVE = frozenset({"gemini", "sonnet", "opus"})


def _public_json(path):
    value = _load(path)
    _public_body(value)
    return value


def _runtime(root, plan_path):
    runtime = _public_json(root / "runtime.json")
    freeze = runtime["freeze"]
    if (not isinstance(freeze, str) or len(freeze) != 40
            or any(c not in "0123456789abcdef" for c in freeze)
            or runtime["plan_sha256"] != protocol.sha(root / "PLAN.json")):
        raise ValueError("Runtime source binding mismatch")
    frozen = subprocess.check_output(["git", "show", f"{freeze}:{plan_path}"],
                                     cwd=protocol.ROOT, stderr=subprocess.DEVNULL)
    if frozen != (root / "PLAN.json").read_bytes():
        raise ValueError("Plan differs from recorded local freeze")
    # Verify Git's source objects locally, without the execution verifier's network check.
    for name, expected in _load(root / "PLAN.json")["source_hashes"].items():
        raw = subprocess.check_output(["git", "show", f"{freeze}:{name}"],
                                      cwd=protocol.ROOT, stderr=subprocess.DEVNULL)
        if hashlib.sha256(raw).hexdigest() != expected:
            raise ValueError("Source differs from recorded local freeze")
    return runtime


def _bindings(plan):
    bindings = plan["prior_attempts"]
    if (bindings != list(amendment.PRIORS) or len(bindings) != 2
            or [(p["label"], p["path"]) for p in bindings] != [("original", "."), ("a1", "a1")]
            or any(type(p["calls"]) is not int or p["calls"] != 12
                   or type(p["target_calls"]) is not int or p["target_calls"] != 0 for p in bindings)):
        raise ValueError("Prior chain binding mismatch")
    total = sum((Decimal(p["cost_bound_usd"]) for p in bindings), Decimal(0))
    if (total != Decimal("0.26254046") or Decimal(plan["prior_cost_usd"]) != total
            or Decimal(plan["cap_usd"]) + total != Decimal("250")
            or Decimal(plan["screen_cap_usd"]) + total != Decimal("40")):
        raise ValueError("Amended caps do not retain all prior costs")
    return bindings


def _priors(root, temporary, plan):
    reports, previous_cost = [], Decimal(0)
    for binding in _bindings(plan):
        prior = root / "prior_attempts" / binding["label"]
        old_plan = _load(prior / "PLAN.json")
        runtime = _runtime(prior, binding["plan_path"])
        if any(runtime[key] != binding[key] for key in ("freeze", "plan_sha256")):
            raise ValueError("Prior runtime binding mismatch")
        if (Decimal(old_plan["prior_cost_usd"]) != previous_cost
                or Decimal(old_plan["cap_usd"]) + previous_cost != Decimal("250")
                or Decimal(old_plan["screen_cap_usd"]) + previous_cost != Decimal("40")):
            raise ValueError("Prior cumulative cap mismatch")
        if reports:
            original = plan["prior_attempts"][0]
            if (any(old_plan["prior_attempt"][key] != original[key] for key in
                    ("freeze", "plan_sha256", "journal_sha256", "cost_bound_usd", "calls", "target_calls"))
                    or runtime["prior_journal_sha256"] != original["journal_sha256"]
                    or Decimal(runtime["prior_cost_bound_usd"]) != previous_cost):
                raise ValueError("A1 prior chain mismatch")
        raw = _unpack(prior / "events.jsonl.gz", temporary / binding["label"])
        if protocol.sha(raw / "events.jsonl") != binding["journal_sha256"]:
            raise ValueError("Prior journal hash mismatch")
        with Ledger(raw, cap=old_plan["cap_usd"], screen_cap=old_plan["screen_cap_usd"]) as ledger:
            audit = Runner(old_plan, runtime["freeze"], runtime["plan_sha256"], ledger, sender=None).audit()
            calls = ledger.rows()
            if any(row["phase"] != "fixtures" or row["metadata"]["kind"] == "generation" for row in calls):
                raise ValueError("Prior attempt contains target calls")
            cost = ledger.spent()
            if (len(calls) != 12 or audit["unresolved"] != 1
                    or cost != Decimal(binding["cost_bound_usd"])):
                raise ValueError("Prior attempt accounting mismatch")
        previous_cost += cost
        reports.append({**binding, "audit": audit})
    return reports


def _replay(root):
    _load(root / "PLAN.json")
    plan = amendment.verify(root / "PLAN.json")
    _bindings(plan)
    if set(plan["models"]) != ACTIVE:
        raise ValueError("Invalid active model roster")
    runtime = _runtime(root, amendment.PLAN)
    freeze, plan_hash = runtime["freeze"], runtime["plan_sha256"]
    if (Decimal(runtime["prior_cost_bound_usd"]) != Decimal(plan["prior_cost_usd"])
            or runtime["prior_attempts"] != plan["prior_attempts"]):
        raise ValueError("Runtime prior-attempt binding mismatch")
    admission = _public_json(root / "main_admission.json") if (root / "main_admission.json").exists() else None
    admitted = admission["admitted_models"] if admission is not None else []
    if (not isinstance(admitted, list) or len(set(admitted)) != len(admitted)
            or set(admitted) - ACTIVE):
        raise ValueError("Invalid main selection")
    with TemporaryDirectory() as temporary:
        temporary = Path(temporary).resolve()
        priors = _priors(root, temporary, plan)
        raw = _unpack(root / "raw/events.jsonl.gz", temporary / "raw")
        with Ledger(raw, cap=plan["cap_usd"], screen_cap=plan["screen_cap_usd"]) as ledger:
            runner = amendment.IndependentRunner(plan, freeze, plan_hash, ledger, sender=None)
            audit = runner.audit()
            if admission is not None:
                events = read_events(raw / "events.jsonl")
                cutoff = next((i for i, event in enumerate(events) if event["kind"] == "reserve"
                               and event["data"]["phase"] == "main"), len(events))
                history_root = temporary / "admission"
                history_root.mkdir()
                (history_root / "events.jsonl").write_bytes(
                    b"".join((raw / "events.jsonl").read_bytes().splitlines(True)[:cutoff]))
                with Ledger(history_root, cap=plan["cap_usd"], screen_cap=plan["screen_cap_usd"]) as history:
                    expected = amendment.IndependentRunner(plan, freeze, plan_hash, history, sender=None).main_admission()
                if admission != expected:
                    raise ValueError("Main admission does not reconstruct")
            try:
                fixtures_pass = runner.require_fixtures()["pass"]
            except Halted:
                fixtures_pass = False
            # Rows retain all four planned models; only dispatch is filtered by A2.
            rows = {"screen": runner.rows("screen")}
            main_started = any(row["phase"] == "main" for row in ledger.rows())
            if admitted or main_started:
                rows["main"] = runner.rows("main", admitted if admission is not None else None)
            screen_cost = sum((ledger.spent(phase) for phase in ("fixture", "fixtures", "screen")), Decimal(0))
    complete = (fixtures_pass and not audit["unresolved"] and admission is not None
                and all(analysis._value(row, judge, endpoint) is not None
                        for phase in rows.values() for row in phase if row["model"] in ACTIVE
                        for judge in plan["judges"] for endpoint in analysis.ENDPOINTS))
    cumulative = Decimal(plan["prior_cost_usd"]) + Decimal(audit["cost_bound_usd"])
    if cumulative > Decimal("250") or Decimal(plan["prior_cost_usd"]) + screen_cost > Decimal("40"):
        raise ValueError("Cumulative cost cap exceeded")
    metadata = {"schema": "openrouter-swap-a2-release-v1", "freeze": freeze, "plan_sha256": plan_hash,
                "status": "complete" if complete else "incomplete", "fixtures_pass": fixtures_pass,
                "completion_scope": "scheduled active-model rows only",
                "active_models": list(plan["models"]),
                "deferred_models": {"deepseek": {"status": "deferred_before_targets", "target_calls": 0,
                    "reason": "Technical routing failure; unrun responses are missing, not negative."}},
                "prior_attempts": priors, "prior_cost_bound_usd": plan["prior_cost_usd"],
                "attempt_cost_bound_usd": audit["cost_bound_usd"],
                "cumulative_cost_bound_usd": str(cumulative), "audit": audit}
    # This roster is used only for figures, never to construct a sender or runner.
    reporting = {**plan, "models": _load(root / "prior_attempts/original/PLAN.json")["models"]}
    return metadata, rows, reporting


def _allowed_inventory(files):
    required = {"PLAN.json", "runtime.json", "raw/events.jsonl.gz", "RELEASE.json", "FIGURE_COUNTS.json"}
    required.update(f"prior_attempts/{label}/{name}" for label in ("original", "a1")
                    for name in ("PLAN.json", "runtime.json", "events.jsonl.gz"))
    required.update(f"screen_{judge}_inclusive.{extension}" for judge in ("astra", "opus")
                    for extension in ("png", "pdf"))
    allowed = required | OPTIONAL | {f"main_{judge}_inclusive.{extension}" for judge in ("astra", "opus")
                                    for extension in ("png", "pdf")}
    snapshots = set()
    for name in set(files) - allowed:
        parts = Path(name).parts
        if len(parts) != 3 or parts[0] != "snapshots" or not parts[1].isdecimal() or parts[2] not in SNAPSHOTS:
            raise ValueError("Artifact is outside the publication allowlist")
        snapshots.add(parts[1])
    if not required <= set(files) or len(snapshots) > 1:
        raise ValueError("Release artifact inventory is incomplete or ambiguous")


def verify(destination):
    """Read-only exact inventory, source, receipt, missingness and cost audit."""
    root = Path(destination).absolute()
    manifest = _load(root / "MANIFEST.json")
    if set(manifest) != {"schema", "files"} or manifest["schema"] != "openrouter-swap-a2-manifest-v1":
        raise ValueError("Invalid manifest")
    if manifest["files"] != _inventory(root):
        raise ValueError("Release inventory or hash mismatch")
    _allowed_inventory(manifest["files"])
    for name in manifest["files"]:
        if name.endswith(".json") and not name.endswith("PLAN.json"):
            _public_json(root / name)
    metadata, rows, plan = _replay(root)
    if _load(root / "RELEASE.json") != metadata:
        raise ValueError("Release audit does not reconstruct")
    counts = {f"{phase}_{judge}_inclusive": cell_counts(items, plan["models"],
              list(protocol.CELLS)[:4] if phase == "screen" else protocol.CELLS, judge)
              for phase, items in rows.items() for judge in ("astra", "opus")}
    if _load(root / "FIGURE_COUNTS.json") != counts:
        raise ValueError("Figure counts do not reconstruct")
    return {"pass": True, "status": metadata["status"], "files": len(manifest["files"])}


def build(run_dir, destination):
    """Copy an explicit allowlist; all three journals retain their original bytes."""
    source, target = Path(run_dir).absolute(), Path(destination).absolute()
    _no_symlinks(source)
    _no_symlinks(target)
    if target.exists():
        raise FileExistsError("Release destination already exists")
    plan = amendment.verify(protocol.ROOT / amendment.PLAN)
    sources = {"PLAN.json": protocol.ROOT / amendment.PLAN, "runtime.json": source / "runtime.json",
               "raw/events.jsonl.gz": source / "raw/events.jsonl"}
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
                    _public_json(path)
                shutil.copyfile(path, output)
        metadata, rows, reporting_plan = _replay(root)
        _write(root / "RELEASE.json", metadata)
        _figures(root, rows, reporting_plan)
        _write(root / "MANIFEST.json", {"schema": "openrouter-swap-a2-manifest-v1", "files": _inventory(root)})
        result = verify(root)
        shutil.copytree(root, target)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", help="A2 directory; original and a1 remain in its parent")
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

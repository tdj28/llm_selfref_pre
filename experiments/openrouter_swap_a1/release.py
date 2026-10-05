"""Build or verify an offline A1 release, retaining the failed prior attempt."""

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
from experiments.openrouter_swap.runner import Runner

from . import amendment


def _runtime(root, plan_path):
    runtime = _load(root / "runtime.json")
    freeze, plan_hash = runtime["freeze"], protocol.sha(root / "PLAN.json")
    if (not isinstance(freeze, str) or len(freeze) != 40
            or any(c not in "0123456789abcdef" for c in freeze)
            or runtime["plan_sha256"] != plan_hash):
        raise ValueError("Runtime source binding mismatch")
    frozen = subprocess.check_output(["git", "show", f"{freeze}:{plan_path}"],
                                     cwd=protocol.ROOT, stderr=subprocess.DEVNULL)
    if frozen != (root / "PLAN.json").read_bytes():
        raise ValueError("Plan differs from recorded local freeze")
    return runtime


def _unpack(source, root):
    _no_symlinks(source)
    root.mkdir()
    with gzip.open(source, "rb") as compressed, (root / "events.jsonl").open("xb") as output:
        shutil.copyfileobj(compressed, output)
    return root


def _prior(root, temporary, plan):
    binding = plan["prior_attempt"]
    prior = root / "prior_attempt"
    old_plan = _load(prior / "PLAN.json")
    runtime = _runtime(prior, protocol.PLAN)
    if any(runtime[key] != binding[key] for key in ("freeze", "plan_sha256")):
        raise ValueError("Prior runtime binding mismatch")
    raw = _unpack(prior / "events.jsonl.gz", temporary / "prior")
    if protocol.sha(raw / "events.jsonl") != binding["journal_sha256"]:
        raise ValueError("Prior journal hash mismatch")
    with Ledger(raw, cap=old_plan["cap_usd"], screen_cap=old_plan["screen_cap_usd"]) as ledger:
        audit = Runner(old_plan, runtime["freeze"], runtime["plan_sha256"], ledger, sender=None).audit()
        calls = ledger.rows()
        if any(row["phase"] != "fixtures" for row in calls) or binding["target_calls"] != 0:
            raise ValueError("Prior attempt contains target calls")
        cost = ledger.spent()
        if (len(calls) != binding["calls"] or cost != Decimal(binding["cost_bound_usd"])
                or cost != Decimal(plan["prior_cost_usd"])):
            raise ValueError("Prior attempt accounting mismatch")
    if (Decimal(plan["cap_usd"]) + cost != Decimal(old_plan["cap_usd"])
            or Decimal(plan["screen_cap_usd"]) + cost != Decimal(old_plan["screen_cap_usd"])):
        raise ValueError("Amended caps do not retain prior costs")
    return {"freeze": runtime["freeze"], "plan_sha256": runtime["plan_sha256"],
            "journal_sha256": binding["journal_sha256"], "target_calls": 0, "audit": audit}


def _replay(root):
    # No freeze argument: amendment.verify's published-branch check uses the network.
    # Verify the recorded canonical Git path locally, not the bundle's temporary path.
    _load(root / "PLAN.json")
    plan = amendment.verify(root / "PLAN.json")
    runtime = _runtime(root, amendment.PLAN)
    freeze, plan_hash = runtime["freeze"], runtime["plan_sha256"]
    if (runtime["prior_journal_sha256"] != plan["prior_attempt"]["journal_sha256"]
            or Decimal(runtime["prior_cost_bound_usd"]) != Decimal(plan["prior_cost_usd"])):
        raise ValueError("Runtime prior-attempt binding mismatch")
    admission = _load(root / "main_admission.json") if (root / "main_admission.json").exists() else None
    admitted = admission["admitted_models"] if admission is not None else []
    if (not isinstance(admitted, list) or len(set(admitted)) != len(admitted)
            or set(admitted) - set(plan["models"])):
        raise ValueError("Invalid main selection")
    with TemporaryDirectory() as temporary:
        temporary = Path(temporary).resolve()
        prior = _prior(root, temporary, plan)
        raw = _unpack(root / "raw/events.jsonl.gz", temporary / "raw")
        with Ledger(raw, cap=plan["cap_usd"], screen_cap=plan["screen_cap_usd"]) as ledger:
            runner = Runner(plan, freeze, plan_hash, ledger, sender=None)
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
                    expected = Runner(plan, freeze, plan_hash, history, sender=None).main_admission()
                if admission != expected:
                    raise ValueError("Main admission does not reconstruct")
            try:
                fixtures_pass = runner.require_fixtures()["pass"]
            except Halted:
                fixtures_pass = False
            rows = {"screen": runner.rows("screen")}
            main_started = any(row["phase"] == "main" for row in ledger.rows())
            if admitted or main_started:
                rows["main"] = runner.rows("main", admitted if admission is not None else None)
    complete = (fixtures_pass and not audit["unresolved"] and admission is not None
                and all(all(analysis._value(row, judge, endpoint) is not None
                            for judge in plan["judges"] for endpoint in analysis.ENDPOINTS)
                        for phase in rows.values() for row in phase))
    return {"schema": "openrouter-swap-a1-release-v1", "freeze": freeze, "plan_sha256": plan_hash,
            "status": "complete" if complete else "incomplete", "fixtures_pass": fixtures_pass,
            "prior_attempt": prior, "prior_cost_bound_usd": plan["prior_cost_usd"],
            "attempt_cost_bound_usd": audit["cost_bound_usd"],
            "cumulative_cost_bound_usd": str(Decimal(plan["prior_cost_usd"]) + Decimal(audit["cost_bound_usd"])),
            "audit": audit}, rows, plan


def verify(destination):
    """Read-only exact inventory, receipt replay and cumulative accounting audit."""
    root = Path(destination).absolute()
    manifest = _load(root / "MANIFEST.json")
    if set(manifest) != {"schema", "files"} or manifest["schema"] != "openrouter-swap-a1-manifest-v1":
        raise ValueError("Invalid manifest")
    if manifest["files"] != _inventory(root):
        raise ValueError("Release inventory or hash mismatch")
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
    """Publish explicit artifacts only; original and new journals stay separate."""
    source, target = Path(run_dir).absolute(), Path(destination).absolute()
    _no_symlinks(source)
    _no_symlinks(target)
    if target.exists():
        raise FileExistsError("Release destination already exists")
    prior = source.parent
    sources = {"PLAN.json": protocol.ROOT / amendment.PLAN,
               "runtime.json": source / "runtime.json",
               "raw/events.jsonl.gz": source / "raw/events.jsonl",
               "prior_attempt/PLAN.json": protocol.ROOT / protocol.PLAN,
               "prior_attempt/runtime.json": prior / "runtime.json",
               "prior_attempt/events.jsonl.gz": prior / "raw/events.jsonl"}
    for name in ("fixture_gate.json", "main_admission.json"):
        if (source / name).exists() or (source / name).is_symlink():
            sources[name] = source / name
    _no_symlinks(source / "snapshots")
    snapshots = [p for p in (source / "snapshots").glob("*") if p.name.isdecimal()]
    if snapshots:
        latest = max(snapshots, key=lambda p: int(p.name))
        _no_symlinks(latest)
        sources.update({p.relative_to(source).as_posix(): p for p in latest.glob("*.json")})
    with TemporaryDirectory() as temporary:
        root = Path(temporary).resolve() / "bundle"
        root.mkdir()
        for name, path in sources.items():
            _no_symlinks(path)
            output = root / name
            output.parent.mkdir(parents=True, exist_ok=True)
            if name.endswith("events.jsonl.gz"):
                with path.open("rb") as handle, output.open("xb") as compressed:
                    with gzip.GzipFile(filename="", fileobj=compressed, mode="wb", mtime=0) as archive:
                        shutil.copyfileobj(handle, archive)
            else:
                shutil.copyfile(path, output)
        metadata, rows, plan = _replay(root)
        _write(root / "RELEASE.json", metadata)
        _figures(root, rows, plan)
        _write(root / "MANIFEST.json", {"schema": "openrouter-swap-a1-manifest-v1", "files": _inventory(root)})
        result = verify(root)
        shutil.copytree(root, target)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", help="A1 directory; the retained prior run is its parent")
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

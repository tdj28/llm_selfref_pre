#!/usr/bin/env python3
"""Offline completed-run packaging and raw-to-table verification for frontier B1.

Build only after the owner confirms completion:
  python scripts/release_frontier_b1.py --run-root CLOSED_RUN --freeze SHA --out NEW_RELEASE
  python scripts/release_frontier_b1.py --verify RELEASE --freeze SHA
  python scripts/release_frontier_b1.py --reproduce RELEASE --freeze SHA --out NEW_ANALYSIS

Only events, qualification, environment and the frozen plan are imported. Locks
and analysis are confined to disposable copies; originals are never opened for
writing. All release files except the manifest itself are hashed. Verification
compares rebuilt tables exactly; plots are bound by hashes and their source data,
not by regenerated PDF timestamps. Run the root public audit before publishing.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from tempfile import TemporaryDirectory

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from experiments.automated_rubric_audit.common import canonical, digest, sha
from experiments.frontier_bilingual_b1 import analysis, protocol, qualification, runner
from experiments.frontier_bilingual_b1.ledger import Ledger, no_symlinks
from scripts.audit_public_release import scan_blob

RAW_FILES = ("events.jsonl", "qualification.json", "environment.json")
TABLES = ("answers.csv", "rates.csv", "contrasts.csv", "cap_sensitivity.csv", "analysis.json")
FIGURES = tuple(f"rates_{judge}.{suffix}" for judge in ("openai", "anthropic") for suffix in ("png", "pdf"))
RELEASE_FILES = {"PLAN.json", *("raw/" + n for n in RAW_FILES),
                 *("analysis/" + n for n in (*TABLES, *FIGURES))}
REPORTING_SOURCES = ("scripts/release_frontier_b1.py", "scripts/audit_public_release.py")
SCHEMA = "frontier-b1-release-v1"
ARCHIVED_REPORTING_COMMIT = "4abc13ce9ac832509e7fb4573f6c2aa4e33e0d48"
ARCHIVED_MANIFEST_PATH = "data/frontier_bilingual_b1/completed_20261002/MANIFEST.json"
ARCHIVED_MANIFEST_SHA256 = "da7468314f3334b93043af854a7890d528d93d8ddd93f0c5d2af76f9560f825b"


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _safe_path(path):
    path = Path(path).absolute()
    no_symlinks(path)
    _require(".." not in path.parts, "Path traversal is forbidden")
    return path.resolve()


def _read(path):
    path = _safe_path(path)
    _require(path.is_file(), "Required regular file missing: " + path.name)
    return path.read_bytes()


def _write(path, raw):
    path = _safe_path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as handle:
        handle.write(raw)


def _new_destination(out, *inputs):
    out = _safe_path(out)
    _require(not out.exists(), "Destination must be fresh; never overwrite")
    for path in inputs:
        path = _safe_path(path)
        _require(not out.is_relative_to(path) and not path.is_relative_to(out),
                 "Output must be separate from inputs")
    return out


def _git(*args):
    # Local objects only: no promisor fetch or replacement-object substitution.
    result = subprocess.run(["git", "--no-replace-objects", "-C", str(protocol.ROOT), *args],
                            env={**os.environ, "GIT_NO_LAZY_FETCH": "1"}, capture_output=True)
    _require(result.returncode == 0, "Cannot verify local frozen Git object")
    return result.stdout


def bind_sources(plan_path, freeze):
    """Validate frozen closure at the freeze or a descendant reporting HEAD."""
    _require(isinstance(freeze, str) and re.fullmatch(r"[0-9a-f]{40}", freeze), "Full freeze SHA required")
    _require(_git("cat-file", "-t", freeze).strip() == b"commit", "Freeze must be a commit")
    _git("merge-base", "--is-ancestor", freeze, "HEAD")
    canonical_path = protocol.ROOT / protocol.PLAN_PATH
    raw = _read(plan_path)
    _require(raw == _read(canonical_path), "Release plan differs from canonical frozen plan")
    plan = protocol.load_plan(canonical_path)
    protocol.assert_scientific_equivalence(plan)
    bindings = {**plan["sources"], protocol.PLAN_PATH: hashlib.sha256(raw).hexdigest()}
    for name, expected in bindings.items():
        _require(not Path(name).is_absolute() and ".." not in Path(name).parts, "Unsafe source path")
        _require(hashlib.sha256(_read(protocol.ROOT / name)).hexdigest() == expected,
                 "Current frozen source changed: " + name)
        blob = _git("cat-file", "blob", f"{freeze}:{name}")
        _require(hashlib.sha256(blob).hexdigest() == expected, "Freeze source mismatch: " + name)
    return plan


@contextmanager
def _closed_source(root):
    """Never create a lock in the source; reject an active frontier writer."""
    lock = root / ".mini.lock"
    no_symlinks(root)
    no_symlinks(lock)
    if lock.exists():
        with lock.open("rb") as handle:
            fcntl.flock(handle, fcntl.LOCK_SH | fcntl.LOCK_NB)
            try:
                yield
            finally:
                fcntl.flock(handle, fcntl.LOCK_UN)
    else:
        yield


def _replay_block_gates(ledger, plan):
    """Require each block's gate before the next block's first dispatch.

    The first-block-only launch records gate 1; the subsequent full invocation
    records gate 1 again with the same receipts. That exact duplicate is valid.
    All calculations use only the receipt prefix available at the gate event.
    """
    catalog = runner.specs(plan)
    slots = {"gen:" + key: spec["block"] for key, spec in catalog.items()}
    slots.update({f"judge:{s['id']}:{p}:{i}": s["block"] for s in catalog.values()
                  if s["kind"] == "final" for p in runner.JUDGES for i in ("paper", "structured")})
    prefix = Ledger(ledger.root, ledger.binding)
    passed = 0
    for event in ledger.events[1:]:
        kind, data = event["kind"], event["data"]
        if kind in {"request", "missing"}:
            _require(slots[data["id"]] == passed + 1, "Block dispatch lacks its preceding passing gate")
        if kind == "request":
            prefix.requests[data["id"]] = data
        elif kind in {"result", "missing"}:
            prefix.results[data["id"]] = data
        elif kind == "projection":
            block = data.get("after_block")
            _require(type(block) is int and 1 <= block <= 6 and
                     (block == passed + 1 or block == passed == 1), "Unexpected block-gate sequence")
            expected_slots = {key for key, number in slots.items() if number <= block}
            _require(set(prefix.results) == expected_slots, "Block gate is not at its complete receipt prefix")
            runner.audit(prefix, plan)
            expected = {"after_block": block, "technical_gate": runner.technical_gate(prefix, plan),
                        "projection": runner.project_cost(prefix, plan)}
            _require(data == expected, "Block gate does not reconstruct from its receipt prefix")
            _require(expected["technical_gate"]["pass"] is True and expected["projection"]["pass"] is True,
                     "A contemporaneous block gate failed")
            passed = block
        elif kind == "complete":
            _require(passed == 6, "Completion lacks all six passing block gates")
    _require(passed == 6, "Missing block gates")


def _render(raw, plan, plan_hash, freeze, out, *, plots):
    """Call the unmodified frozen audit and analysis on a disposable raw copy."""
    snapshot = json.loads(_read(raw / "qualification.json"))
    gate = qualification.verify_snapshot(snapshot, plan, freeze)
    binding = {"plan_sha256": plan_hash, "freeze_commit": freeze, "hard_cap_usd": "60",
               "qualification_snapshot_sha256": gate["snapshot_sha256"]}
    before = sha(raw / "events.jsonl")
    with Ledger(raw, binding) as ledger:
        report = runner.audit(ledger, plan, require_complete=True)
        _require(ledger.events[-1]["kind"] == "complete" and ledger.events[-1]["data"] == report,
                 "A verified final completion record is required")
        _replay_block_gates(ledger, plan)
        rows = analysis.rows_from_ledger(ledger, plan)
    _require(sha(raw / "events.jsonl") == before, "Replay modified the event journal")
    result = {**analysis.summarize(rows), "receipt_audit": report}
    out.mkdir(parents=True, exist_ok=False)
    for name, values in (("answers.csv", rows), ("rates.csv", result["cells"]),
                         ("contrasts.csv", result["contrasts"]), ("cap_sensitivity.csv", result["cap_sensitivity"])):
        analysis._csv(out / name, values)
    _write(out / "analysis.json", (canonical(result) + "\n").encode())
    if plots:
        analysis.heatmaps(result, out)
    return report, gate


def _manifest(root, plan, plan_hash, freeze, report, gate):
    return {"schema": SCHEMA, "freeze_commit": freeze, "plan_sha256": plan_hash,
            "qualification_snapshot_sha256": gate["snapshot_sha256"],
            "frozen_sources_sha256": digest(plan["sources"]),
            "reporting_source_hashes": {n: sha(protocol.ROOT / n) for n in REPORTING_SOURCES},
            "receipt_audit": report, "fixture_cost_charged_to_frontier_usd": "0",
            "interpretation": "automated receipt reconstruction, not human validation or AI accuracy",
            "manifest_excluded_from_own_inventory": True,
            "figure_verification": "file_hashes_and_exact_underlying_tables_not_pdf_timestamps",
            "files": [{"path": n, "bytes": (root / n).stat().st_size, "sha256": sha(root / n)}
                      for n in sorted(RELEASE_FILES)]}


def _verified_reporting_sources(manifest_bytes, current):
    """Historical tool provenance is not a requirement to run old audit code.

    Only the exact already-public manifest can use archived source bindings.
    Verify its Git snapshot and each original tool blob; arbitrary resealed
    manifests or unknown historical tool hashes remain failures.
    """
    manifest = json.loads(manifest_bytes)
    recorded = manifest.get("reporting_source_hashes")
    if recorded == current:
        return current
    _require(hashlib.sha256(manifest_bytes).hexdigest() == ARCHIVED_MANIFEST_SHA256,
             "Manifest provenance/audit does not reconstruct: unknown reporting history")
    _git("merge-base", "--is-ancestor", ARCHIVED_REPORTING_COMMIT, "HEAD")
    archived = _git("cat-file", "blob", f"{ARCHIVED_REPORTING_COMMIT}:{ARCHIVED_MANIFEST_PATH}")
    _require(archived == manifest_bytes, "Archived manifest differs")
    _require(isinstance(recorded, dict) and set(recorded) == set(REPORTING_SOURCES),
             "Archived reporting-source inventory differs")
    for name, expected in recorded.items():
        blob = _git("cat-file", "blob", f"{ARCHIVED_REPORTING_COMMIT}:{name}")
        _require(hashlib.sha256(blob).hexdigest() == expected, "Archived reporting-source hash differs")
    return recorded


def build(run_root, plan_path, freeze, out):
    run_root, plan_path = _safe_path(run_root), _safe_path(plan_path)
    out = _new_destination(out, run_root, plan_path)
    plan = bind_sources(plan_path, freeze)
    with _closed_source(run_root), TemporaryDirectory(prefix="frontier-b1-release-") as temporary:
        stage = Path(temporary).resolve()
        inputs = {"PLAN.json": (plan_path, _read(plan_path))}
        inputs.update({"raw/" + n: (run_root / n, _read(run_root / n)) for n in RAW_FILES})
        for name, (_, raw) in inputs.items():
            _require(not scan_blob(name, raw), "Public content check failed: " + name)
            _write(stage / name, raw)
        report, gate = _render(stage / "raw", plan, sha(stage / "PLAN.json"), freeze,
                               stage / "analysis", plots=True)
        manifest = _manifest(stage, plan, sha(stage / "PLAN.json"), freeze, report, gate)
        # A whole-file snapshot, not an in-flight prefix; originals remain unchanged.
        _require(all(_read(path) == raw for path, raw in inputs.values()), "Source snapshot changed")
        out.mkdir(parents=True, exist_ok=False)
        for name in sorted(RELEASE_FILES):
            raw = _read(stage / name)
            _require(not scan_blob(name, raw), "Public content check failed: " + name)
            _write(out / name, raw)
        _require(all(_read(path) == raw for path, raw in inputs.values()), "Source changed during publication")
        manifest_raw = (canonical(manifest) + "\n").encode()
        _require(not scan_blob("MANIFEST.json", manifest_raw), "Public content check failed: MANIFEST.json")
        _write(out / "MANIFEST.json", manifest_raw)
    return {"pass": True, "files": len(RELEASE_FILES), "plan_sha256": manifest["plan_sha256"],
            "freeze_commit": freeze, "receipt_audit": report}


def _verify_inventory(root):
    raw = _read(root / "MANIFEST.json")
    _require(not scan_blob("MANIFEST.json", raw), "Public content check failed: MANIFEST.json")
    manifest = json.loads(raw)
    _require(manifest.get("schema") == SCHEMA, "Unknown release manifest")
    actual = set()
    for path in root.rglob("*"):
        no_symlinks(path)
        name = path.relative_to(root).as_posix()
        if path.is_dir():
            _require(name in {"raw", "analysis"}, "Unexpected release directory")
        else:
            _require(path.is_file(), "Nonregular release artifact")
            actual.add(name)
    _require(actual == RELEASE_FILES | {"MANIFEST.json"}, "Release inventory differs")
    entries = manifest.get("files", [])
    _require(len(entries) == len(RELEASE_FILES) and {e["path"] for e in entries} == RELEASE_FILES,
             "Manifest inventory differs")
    for entry in entries:
        raw = _read(root / entry["path"])
        _require(not scan_blob(entry["path"], raw), "Public content check failed: " + entry["path"])
        _require(len(raw) == entry["bytes"] and hashlib.sha256(raw).hexdigest() == entry["sha256"],
                 "Release hash mismatch: " + entry["path"])
    return manifest


def verify(root, freeze, out=None):
    """Always rebuild tables; optionally retain a fresh reproduced figure set."""
    root = _safe_path(root)
    if out is not None:
        out = _new_destination(out, root)
    manifest_bytes = _read(root / "MANIFEST.json")
    manifest = _verify_inventory(root)
    _require(manifest["freeze_commit"] == freeze, "Manifest freeze mismatch")
    plan = bind_sources(root / "PLAN.json", freeze)
    inputs = {n: _read(root / n) for n in ("PLAN.json", *("raw/" + n for n in RAW_FILES))}
    with TemporaryDirectory(prefix="frontier-b1-verify-") as temporary:
        stage = Path(temporary).resolve()
        for name, raw in inputs.items():
            _write(stage / name, raw)
        report, gate = _render(stage / "raw", plan, sha(stage / "PLAN.json"), freeze,
                               stage / "analysis", plots=out is not None)
        for name in TABLES:
            _require(_read(stage / "analysis" / name) == _read(root / "analysis" / name),
                     "Raw-to-table reproduction differs: " + name)
        expected = _manifest(root, plan, sha(root / "PLAN.json"), freeze, report, gate)
        expected["reporting_source_hashes"] = _verified_reporting_sources(
            manifest_bytes, expected["reporting_source_hashes"])
        _require(manifest == expected, "Manifest provenance/audit does not reconstruct")
        _require(_read(root / "MANIFEST.json") == manifest_bytes and _verify_inventory(root) == manifest,
                 "Release changed during verification")
        if out is not None:
            out.mkdir(parents=True, exist_ok=False)
            for name in (*TABLES, *FIGURES):
                _write(out / name, _read(stage / "analysis" / name))
    return {"pass": True, "tables_reproduced_exactly": list(TABLES), "freeze_commit": freeze,
            "plan_sha256": manifest["plan_sha256"], "receipt_audit": report,
            "figure_comparison": "hashed_originals_and_exact_plot_data_not_pdf_timestamps"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--run-root", type=Path)
    mode.add_argument("--verify", type=Path)
    mode.add_argument("--reproduce", type=Path)
    parser.add_argument("--freeze", required=True)
    parser.add_argument("--plan", type=Path, default=protocol.ROOT / protocol.PLAN_PATH)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    if args.run_root:
        if args.out is None:
            parser.error("--out must be a fresh release directory")
        result = build(args.run_root, args.plan, args.freeze, args.out)
    elif args.reproduce:
        if args.out is None:
            parser.error("--out must be a fresh reproduction directory")
        result = verify(args.reproduce, args.freeze, args.out)
    else:
        if args.out is not None:
            parser.error("Use --reproduce to retain derived outputs")
        result = verify(args.verify, args.freeze)
    print(canonical(result))


if __name__ == "__main__":
    main()

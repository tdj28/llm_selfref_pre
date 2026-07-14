#!/usr/bin/env python3
"""Build the compact, outcome-free machine plan for realization validation."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from experiments.consciousness_sae_realization_validation import protocol  # noqa: E402


DEFAULT_OUTDIR = (
    REPO_ROOT
    / "data"
    / "consciousness_sae_realization_validation"
    / "validation_v1_plan_20260714"
)

BOUND_SOURCE_PATHS = (
    "experiments/consciousness_sae_realization_validation/__init__.py",
    "experiments/consciousness_sae_realization_validation/protocol.py",
    "experiments/consciousness_sae_realization_validation/controls.py",
    "experiments/consciousness_sae_realization_validation/runtime.py",
    "experiments/consciousness_sae_realization_validation/guest_launcher.py",
    "experiments/consciousness_sae_realization_validation/j_orientation.py",
    "experiments/consciousness_sae_realization_validation/runner.py",
    "experiments/consciousness_sae_realization_validation/smoke_test.py",
    "experiments/consciousness_sae_realization_validation/analysis.py",
    "experiments/consciousness_sae_realization_validation/audit.py",
    "experiments/consciousness_sae_realization_validation/build_plan.py",
    "experiments/consciousness_sae_realization_validation/gate_receipts.py",
    "experiments/consciousness_sae_realization_validation/preexecution.py",
    "experiments/consciousness_sae_realization_validation/review_adjudication.py",
    "experiments/consciousness_sae_realization_validation/runpod_preflight.py",
    "experiments/consciousness_sae_realization_validation/runpod_lifecycle_adapter.py",
    "experiments/consciousness_sae_realization_validation/runpod_orchestrator.py",
    "experiments/consciousness_sae_realization_validation/storage_benchmark.py",
    "experiments/consciousness_sae_realization_validation/legacy_public_artifact_manifest.json",
    # Exactly one audited, target-free predecessor source is loaded through a
    # synthetic successor-only protocol/path surface.  Its old package,
    # protocol, semantic fixtures, runtime, and measurements are not deployed.
    "experiments/consciousness_readout_validation/runpod_lifecycle.py",
)

GUEST_CLI_MODULES = (
    "analysis",
    "audit",
    "build_plan",
    "gate_receipts",
    "guest_launcher",
    "preexecution",
    "review_adjudication",
    "runner",
    "runpod_lifecycle_adapter",
    "runpod_orchestrator",
    "runpod_preflight",
    "smoke_test",
    "storage_benchmark",
)


def _write_json(path: Path, value: Any) -> None:
    path.write_bytes(protocol.canonical_json_bytes(value) + b"\n")


def _write_jsonl(path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
    with path.open("xb") as handle:
        for row in rows:
            handle.write(protocol.canonical_json_bytes(dict(row)) + b"\n")


def _file_record(path: Path, root: Path) -> dict[str, Any]:
    return {
        "path": path.relative_to(root).as_posix(),
        "bytes": path.stat().st_size,
        "sha256": protocol.sha256_file(path),
    }


def source_records(repo_root: Path) -> list[dict[str, Any]]:
    rows = []
    for relative in BOUND_SOURCE_PATHS:
        path = repo_root / relative
        if not path.is_file():
            raise FileNotFoundError(f"bound source is missing: {relative}")
        rows.append(
            {
                "path": relative,
                "bytes": path.stat().st_size,
                "sha256": protocol.sha256_file(path),
                "outcome_bearing": False,
                "reuse_kind": (
                    "audited_source_implementation"
                    if not relative.startswith(
                        "experiments/consciousness_sae_realization_validation/"
                    )
                    else "current_study_source"
                ),
            }
        )
    return rows


def build(*, outdir: Path, repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    protocol.validate_protocol()
    destination = outdir.expanduser().resolve()
    if destination.exists() or destination.is_symlink():
        raise FileExistsError(f"plan destination already exists: {destination}")
    partial = destination.with_name(destination.name + ".partial")
    if partial.exists() or partial.is_symlink():
        raise FileExistsError(f"partial plan destination already exists: {partial}")
    partial.parent.mkdir(parents=True, exist_ok=True)
    partial.mkdir()
    try:
        _write_json(partial / "protocol_snapshot.json", protocol.protocol_snapshot())
        _write_jsonl(partial / "stage_a_plan.jsonl", protocol.stage_a_rows())
        _write_jsonl(partial / "aggregate_assignments.jsonl", protocol.aggregate_assignments())
        _write_jsonl(partial / "stage_b_plan.jsonl", protocol.stage_b_rows())
        _write_json(
            partial / "source_files.json",
            {
                "study_id": protocol.STUDY_ID,
                "protocol_version": protocol.PROTOCOL_VERSION,
                "files": source_records(repo_root),
                "prior_outcome_inputs": [],
            },
        )
        file_names = (
            "protocol_snapshot.json",
            "stage_a_plan.jsonl",
            "aggregate_assignments.jsonl",
            "stage_b_plan.jsonl",
            "source_files.json",
        )
        core = {
            "schema_version": protocol.PLAN_SCHEMA_VERSION,
            "study_id": protocol.STUDY_ID,
            "protocol_version": protocol.PROTOCOL_VERSION,
            "scope": "realization_and_target_free_vector_validation_only",
            "paper_prompt_render_count": 0,
            "behavioral_replication_included": False,
            "stage_a_signed_edit_forward_count": 2304,
            "stage_b_edit_forward_count": 2160,
            "files": [_file_record(partial / name, partial) for name in file_names],
            "prior_outcome_inputs": [],
        }
        manifest = {**core, "plan_manifest_sha256": protocol.canonical_sha256(core)}
        _write_json(partial / "plan_manifest.json", manifest)
        os.replace(partial, destination)
        return manifest
    except BaseException:
        # Preserve a failed build for diagnosis; it can never validate because
        # the final directory and manifest are absent.
        raise


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--outdir", type=Path, default=DEFAULT_OUTDIR)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    manifest = build(outdir=args.outdir)
    print(manifest["plan_manifest_sha256"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Build a fresh, result-free machine-plan scaffold for the experiment.

The output is compact Git metadata. It contains no transcript, activation,
logit, judgment, or raw-artifact destination on the local machine. Outcome
jobs must resolve their relative run prefix beneath the separately verified
RunPod network-volume root at runtime.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Iterable, Mapping


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from experiments.consciousness_sae_changepoint import calibrate, paths  # noqa: E402
from experiments.consciousness_sae_changepoint.protocol import (  # noqa: E402
    PLAN_SCHEMA_VERSION,
    PROTOCOL_VERSION,
    STUDY_ID,
    aggregate_blocks,
    assert_plan_invariants,
    canonical_json_bytes,
    fixed_token_rows,
    main_branch_rows,
    plan_hash_from_file_records,
    prefix_block_assignments,
    prefix_rows,
    probe_templates,
    protocol_snapshot,
    sha256_file,
    storage_contract,
    upstream_inputs,
    validate_matched_feature_map,
)
from experiments.consciousness_sae_changepoint.storage import (  # noqa: E402
    verify_completed_run,
)


DEFAULT_OUTDIR = (
    REPO_ROOT
    / "data"
    / "consciousness_sae_changepoint"
    / "confirmatory_v1_plan_scaffold_20260713"
)

PLAN_FILE_NAMES = (
    "protocol_snapshot.json",
    "upstream_inputs.json",
    "storage_contract.json",
    "aggregate_blocks.jsonl",
    "prefix_plan.jsonl",
    "main_branch_plan.jsonl",
    "probe_plan.jsonl",
    "fixed_token_plan.jsonl",
    "source_files.json",
)

BOUND_SOURCE_RELATIVE_PATHS = (
    "src/prompts.py",
    "experiments/consciousness_sae_changepoint/protocol.py",
    "experiments/consciousness_sae_changepoint/judge_prompts.py",
    "experiments/consciousness_sae_changepoint/paths.py",
    "experiments/consciousness_sae_changepoint/runtime_core.py",
    "experiments/consciousness_sae_changepoint/storage.py",
    "experiments/consciousness_sae_changepoint/readouts.py",
    "experiments/consciousness_sae_changepoint/artifact_audit.py",
    "experiments/consciousness_sae_changepoint/calibrate.py",
    "experiments/consciousness_sae_changepoint/semantic_controls.py",
    "experiments/consciousness_sae_changepoint/semantic_control_run.py",
    "experiments/consciousness_sae_changepoint/semantic_control_amendment.py",
    "experiments/consciousness_sae_changepoint/seal_semantic_amendment_failure.py",
    "experiments/consciousness_sae_changepoint/semantic_control_composite.py",
    "experiments/consciousness_sae_changepoint/benchmark.py",
    "experiments/consciousness_sae_changepoint/judge.py",
    "experiments/consciousness_sae_changepoint/analyze.py",
    "experiments/consciousness_sae_changepoint/analyze_run.py",
    "experiments/consciousness_sae_changepoint/power.py",
    "experiments/consciousness_sae_changepoint/seal.py",
    "experiments/consciousness_sae_changepoint/gate_validators.py",
    "experiments/consciousness_sae_changepoint/build_acceptance.py",
    "experiments/consciousness_sae_changepoint/build_plan.py",
    "experiments/consciousness_sae_changepoint/validate_plan.py",
    "experiments/consciousness_sae_changepoint/run.py",
    "experiments/consciousness_sae_changepoint/requirements-runpod-b200.txt",
)


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, allow_nan=False, indent=2, sort_keys=True)
        + "\n",
        encoding="utf-8",
    )


def _write_jsonl(path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
    with path.open("wb") as handle:
        for row in rows:
            handle.write(canonical_json_bytes(row) + b"\n")


def _file_record(path: Path, root: Path) -> dict[str, Any]:
    return {
        "path": path.relative_to(root).as_posix(),
        "bytes": path.stat().st_size,
        "sha256": sha256_file(path),
    }


def source_file_records(repo_root: Path = REPO_ROOT) -> list[dict[str, Any]]:
    source_paths = tuple(repo_root / relative for relative in BOUND_SOURCE_RELATIVE_PATHS)
    missing = [path for path in source_paths if not path.is_file()]
    if missing:
        raise FileNotFoundError(f"machine-plan source file is missing: {missing}")
    return [
        {
            "path": path.relative_to(repo_root).as_posix(),
            "bytes": path.stat().st_size,
            "sha256": sha256_file(path),
            "outcome_bearing": False,
        }
        for path in source_paths
    ]


def load_calibration_receipt(
    receipt_path: Path,
) -> tuple[dict[int, int], float, str]:
    """Load only the allowed fields from a fresh target-blind receipt.

    The full receipt is never copied into the plan. Its hash binds the exact
    external/compact record, while the plan receives just the selected mapping
    and telemetry multiplier needed for deterministic condition construction.
    """

    resolved_receipt = receipt_path.expanduser().resolve()
    for prohibited_root in paths.READ_ONLY_UPSTREAM_ROOTS:
        try:
            resolved_receipt.relative_to(prohibited_root.resolve())
        except ValueError:
            continue
        raise ValueError(
            "calibration receipt may not be loaded from a prior experiment namespace"
        )

    payload = json.loads(resolved_receipt.read_text(encoding="utf-8"))
    if payload.get("study_id") != STUDY_ID:
        raise ValueError("calibration receipt has a different study_id")
    if payload.get("status") != "pass":
        raise ValueError("calibration receipt status must be pass")
    if payload.get("outcome_blind") is not True:
        raise ValueError("calibration receipt must assert outcome_blind=true")
    if payload.get("prior_outcome_inputs") != []:
        raise ValueError("calibration receipt must have no prior outcome inputs")
    try:
        calibrate.validate_calibration_receipt(payload)
    except calibrate.CalibrationProtocolError as exc:
        raise ValueError(f"calibration receipt fails full reconstruction: {exc}") from exc
    if resolved_receipt.name != "calibration_receipt.json":
        raise ValueError("calibration receipt filename differs from the sealed contract")
    try:
        verify_completed_run(resolved_receipt.parent)
    except Exception as exc:
        raise ValueError(
            "calibration receipt is not inside a verified completed transaction"
        ) from exc
    mapping_payload = payload.get("matched_feature_map")
    if not isinstance(mapping_payload, dict):
        raise ValueError("calibration receipt lacks matched_feature_map")
    mapping = validate_matched_feature_map(
        {int(target): int(control) for target, control in mapping_payload.items()}
    )
    if mapping is None:  # pragma: no cover - guarded by the dict requirement
        raise AssertionError("validated calibration map unexpectedly absent")
    multiplier = float(payload["calibrated_multiplier"])
    # protocol_snapshot performs the finiteness/positivity check as well.
    receipt_sha256 = sha256_file(resolved_receipt)
    return mapping, multiplier, receipt_sha256


def build(
    *,
    outdir: Path,
    volume_id: str,
    calibration_receipt: Path | None = None,
    repo_root: Path = REPO_ROOT,
) -> dict[str, Any]:
    """Write a deterministic, previously nonexistent plan directory."""

    matched_map: dict[int, int] | None = None
    calibrated_multiplier: float | None = None
    calibration_sha256: str | None = None
    if calibration_receipt is not None:
        matched_map, calibrated_multiplier, calibration_sha256 = (
            load_calibration_receipt(calibration_receipt)
        )

    # This is a compact, result-free Git destination. paths.py is intentionally
    # the sole authority for allowing it; raw jobs use the external path guard.
    destination = paths.require_new_output_path(outdir, release=True)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.mkdir()

    prefixes = prefix_rows()
    blocks = aggregate_blocks()
    assignments = prefix_block_assignments(prefixes, blocks)
    main_rows = main_branch_rows(assignments, blocks, matched_map)
    probes = probe_templates()
    fixed_rows = fixed_token_rows(
        assignments, blocks, matched_map, calibrated_multiplier
    )
    assert_plan_invariants(prefixes, blocks, assignments, main_rows, probes, fixed_rows)

    snapshot = protocol_snapshot(
        volume_id=volume_id,
        matched_feature_map=matched_map,
        calibration_receipt_sha256=calibration_sha256,
        calibrated_multiplier=calibrated_multiplier,
    )
    public_inputs = upstream_inputs(repo_root)
    source_records = source_file_records(repo_root)

    payloads: dict[str, Any] = {
        "protocol_snapshot.json": snapshot,
        "upstream_inputs.json": public_inputs,
        "storage_contract.json": storage_contract(volume_id),
        "aggregate_blocks.jsonl": blocks,
        "prefix_plan.jsonl": assignments,
        "main_branch_plan.jsonl": main_rows,
        "probe_plan.jsonl": probes,
        "fixed_token_plan.jsonl": fixed_rows,
        "source_files.json": {
            "study_id": STUDY_ID,
            "files": source_records,
            "prior_outcome_source_files": [],
        },
    }
    for filename in PLAN_FILE_NAMES:
        path = destination / filename
        payload = payloads[filename]
        if filename.endswith(".jsonl"):
            _write_jsonl(path, payload)
        else:
            _write_json(path, payload)

    file_records = [_file_record(destination / name, destination) for name in PLAN_FILE_NAMES]
    plan_hash = plan_hash_from_file_records(file_records)
    manifest = {
        "schema_version": PLAN_SCHEMA_VERSION,
        "status": snapshot["status"],
        "study_id": STUDY_ID,
        "protocol_version": PROTOCOL_VERSION,
        "plan_hash": plan_hash,
        "canonical_hash_contract": (
            "sha256(canonical JSON of schema_version, protocol_version, study_id, "
            "and sorted path/bytes/sha256 records for every listed plan file)"
        ),
        "files": sorted(file_records, key=lambda row: row["path"]),
        "counts": {
            "prefix_occurrences": len(assignments),
            "aggregate_blocks": len(blocks),
            "main_branch_rows": len(main_rows),
            "probe_templates": len(probes),
            "planned_probe_generations": len(probes) * len(assignments),
            "fixed_token_rows": len(fixed_rows),
        },
        "result_files": [],
        "external_artifact_volume_id": volume_id,
        "external_paths_are_relative_only": True,
    }
    _write_json(destination / "PLAN_MANIFEST.json", manifest)
    return {
        "status": "pass",
        "plan_status": snapshot["status"],
        "plan_dir": str(destination),
        "plan_hash": plan_hash,
        **manifest["counts"],
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--outdir", type=Path, default=DEFAULT_OUTDIR)
    parser.add_argument("--volume-id", required=True)
    parser.add_argument(
        "--calibration-receipt",
        type=Path,
        help=(
            "Fresh outcome-blind receipt containing the matched map and BF16 "
            "telemetry multiplier. Omit to build a pre-calibration scaffold."
        ),
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result = build(
        outdir=args.outdir.resolve(),
        volume_id=args.volume_id,
        calibration_receipt=(
            args.calibration_receipt.resolve() if args.calibration_receipt else None
        ),
    )
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

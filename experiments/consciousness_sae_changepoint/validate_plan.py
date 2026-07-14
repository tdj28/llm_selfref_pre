#!/usr/bin/env python3
"""Fail-closed validation for a consciousness-SAE machine-plan directory."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Iterable, Mapping


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from experiments.consciousness_sae_changepoint.build_plan import (  # noqa: E402
    PLAN_FILE_NAMES,
)
from experiments.consciousness_sae_changepoint.protocol import (  # noqa: E402
    ACTIVE_PROBE_EVENT_TIMES,
    ARTIFACT_ROOT_ENV,
    BINARY_QUERY_SHA256,
    CAPTURE_STATES,
    DIRECT_POSITIONS,
    DOWNSTREAM_TRACE_LAYERS,
    EDIT_STATES,
    FIXED_TOKEN_CONDITIONS,
    JLENS_FILE_SHA256,
    JLENS_REVISION,
    J_MAP_LAYERS,
    MAIN_BRANCHES,
    MIN_FREE_BYTES,
    MODEL_REVISION,
    N_AGGREGATE_BLOCKS,
    N_PREFIXES,
    PLAN_SCHEMA_VERSION,
    PROHIBITED_OUTCOME_DEPENDENCIES,
    PROTOCOL_VERSION,
    SAE_FILE_SHA256,
    SAE_LAYER,
    SAE_REVISION,
    SELF_REFERENCE_PROMPT_SHA256,
    STUDY_ID,
    TOKENIZER_SIZE,
    UPSTREAM_CONTROL_LAYERS,
    aggregate_blocks,
    assert_plan_invariants,
    fixed_token_rows,
    main_branch_rows,
    plan_hash_from_file_records,
    prefix_block_assignments,
    prefix_rows,
    probe_templates,
    sha256_file,
    validate_matched_feature_map,
    validate_volume_id,
)


MAX_PLAN_FILE_BYTES = 5 * 1024**2
MAX_PLAN_TOTAL_BYTES = 25 * 1024**2
EXPECTED_BOUND_SOURCE_RELATIVE_PATHS = (
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
OUTCOME_FIELD_NAMES = frozenset(
    {
        "activation",
        "activations",
        "answer_text",
        "confidence_interval",
        "effect_estimate",
        "generated_text",
        "judge_label",
        "logit",
        "logits",
        "outcome",
        "outcome_rows",
        "p_value",
        "raw_residual",
        "result_row",
        "score_value",
        "transcript",
        "transcript_text",
    }
)


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def _walk(value: Any, location: str = "$.") -> Iterable[tuple[str, str | None, Any]]:
    if isinstance(value, dict):
        for key, child in value.items():
            child_location = f"{location}{key}"
            yield child_location, str(key), child
            yield from _walk(child, child_location + ".")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            child_location = f"{location}[{index}]"
            yield child_location, None, child
            yield from _walk(child, child_location + ".")


def _manifest_file_records(plan_dir: Path) -> list[dict[str, Any]]:
    return [
        {
            "path": name,
            "bytes": (plan_dir / name).stat().st_size,
            "sha256": sha256_file(plan_dir / name),
        }
        for name in PLAN_FILE_NAMES
    ]


def _compare_exact(
    actual: Any, expected: Any, label: str, errors: list[str]
) -> None:
    if actual != expected:
        errors.append(f"{label} differs from deterministic reconstruction")


def validate(
    plan_dir: Path,
    *,
    expected_volume_id: str | None = None,
    repo_root: Path = REPO_ROOT,
) -> dict[str, Any]:
    errors: list[str] = []
    plan_dir = plan_dir.resolve()
    expected_names = set(PLAN_FILE_NAMES) | {"PLAN_MANIFEST.json"}
    if not plan_dir.is_dir():
        return {
            "status": "fail",
            "study_id": STUDY_ID,
            "plan_dir": str(plan_dir),
            "plan_hash": None,
            "n_errors": 1,
            "errors": [f"plan directory does not exist: {plan_dir}"],
        }

    actual_names = {path.name for path in plan_dir.iterdir()}
    missing = sorted(expected_names - actual_names)
    unexpected = sorted(actual_names - expected_names)
    errors.extend(f"required plan file missing: {name}" for name in missing)
    errors.extend(f"unlisted file present in sealed plan directory: {name}" for name in unexpected)
    if missing:
        return {
            "status": "fail",
            "study_id": STUDY_ID,
            "plan_dir": str(plan_dir),
            "plan_hash": None,
            "n_errors": len(errors),
            "errors": errors,
        }

    for name in expected_names:
        path = plan_dir / name
        if path.is_symlink():
            errors.append(f"symlink is forbidden in plan directory: {name}")
        if not path.is_file():
            errors.append(f"plan entry is not a regular file: {name}")

    try:
        manifest = _read_json(plan_dir / "PLAN_MANIFEST.json")
        snapshot = _read_json(plan_dir / "protocol_snapshot.json")
        upstream = _read_json(plan_dir / "upstream_inputs.json")
        storage = _read_json(plan_dir / "storage_contract.json")
        source_files = _read_json(plan_dir / "source_files.json")
        blocks = _read_jsonl(plan_dir / "aggregate_blocks.jsonl")
        assignments = _read_jsonl(plan_dir / "prefix_plan.jsonl")
        main_rows = _read_jsonl(plan_dir / "main_branch_plan.jsonl")
        probes = _read_jsonl(plan_dir / "probe_plan.jsonl")
        fixed_rows = _read_jsonl(plan_dir / "fixed_token_plan.jsonl")
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        errors.append(f"plan parse failure: {exc}")
        return {
            "status": "fail",
            "study_id": STUDY_ID,
            "plan_dir": str(plan_dir),
            "plan_hash": None,
            "n_errors": len(errors),
            "errors": errors,
        }

    if manifest.get("schema_version") != PLAN_SCHEMA_VERSION:
        errors.append("manifest schema version differs")
    if manifest.get("study_id") != STUDY_ID:
        errors.append("manifest study_id differs")
    if manifest.get("protocol_version") != PROTOCOL_VERSION:
        errors.append("manifest protocol version differs")
    if manifest.get("result_files") != []:
        errors.append("result_files must remain empty in a machine plan")

    observed_records = _manifest_file_records(plan_dir)
    listed_records = manifest.get("files")
    if not isinstance(listed_records, list):
        errors.append("manifest files field is not a list")
        listed_records = []
    normalized_listed: list[dict[str, Any]] = []
    for record in listed_records:
        try:
            relative = Path(str(record["path"]))
            if relative.is_absolute() or ".." in relative.parts or len(relative.parts) != 1:
                errors.append(f"unsafe manifest plan path: {relative}")
                continue
            normalized_listed.append(
                {
                    "path": relative.as_posix(),
                    "bytes": int(record["bytes"]),
                    "sha256": str(record["sha256"]),
                }
            )
        except (KeyError, TypeError, ValueError) as exc:
            errors.append(f"invalid manifest file record: {exc}")
    if sorted(normalized_listed, key=lambda row: row["path"]) != sorted(
        observed_records, key=lambda row: row["path"]
    ):
        errors.append("manifest file inventory differs from plan bytes")
    recomputed_hash = plan_hash_from_file_records(observed_records)
    if manifest.get("plan_hash") != recomputed_hash:
        errors.append("canonical plan hash differs")
    if any(record["bytes"] > MAX_PLAN_FILE_BYTES for record in observed_records):
        errors.append("a compact machine-plan file exceeds 5 MiB")
    if sum(record["bytes"] for record in observed_records) > MAX_PLAN_TOTAL_BYTES:
        errors.append("compact machine-plan payload exceeds 25 MiB")

    if snapshot.get("study_id") != STUDY_ID or snapshot.get("protocol_version") != PROTOCOL_VERSION:
        errors.append("protocol snapshot identity differs")
    if snapshot.get("fresh_run_contract", {}).get("prior_outcome_dependencies") != []:
        errors.append("protocol snapshot contains prior outcome dependencies")
    artifacts = snapshot.get("artifacts", {})
    if artifacts.get("model", {}).get("revision") != MODEL_REVISION:
        errors.append("model revision differs")
    if artifacts.get("tokenizer", {}).get("required_len") != TOKENIZER_SIZE:
        errors.append("tokenizer population differs")
    sae = artifacts.get("sae", {})
    if (
        sae.get("revision") != SAE_REVISION
        or sae.get("file_sha256") != SAE_FILE_SHA256
        or sae.get("layer") != SAE_LAYER
    ):
        errors.append("SAE artifact pin differs")
    lens = artifacts.get("jacobian_lens", {})
    if (
        lens.get("revision") != JLENS_REVISION
        or lens.get("file_sha256") != JLENS_FILE_SHA256
        or lens.get("required_map_layers") != list(J_MAP_LAYERS)
    ):
        errors.append("Jacobian-lens artifact pin differs")
    prompt_spec = snapshot.get("prompts", {})
    if prompt_spec.get("induction_utf8_sha256") != SELF_REFERENCE_PROMPT_SHA256:
        errors.append("self-reference prompt hash differs")
    if prompt_spec.get("binary_query_utf8_sha256") != BINARY_QUERY_SHA256:
        errors.append("binary query hash differs")

    depth = snapshot.get("depth_trace", {})
    if depth.get("j_map_layers") != list(J_MAP_LAYERS):
        errors.append("J-map layer grid is not every layer 45:78")
    if depth.get("upstream_control_layers") != list(UPSTREAM_CONTROL_LAYERS):
        errors.append("upstream layer grid differs")
    if depth.get("edit_states") != list(EDIT_STATES):
        errors.append("layer-50 pre/post states differ")
    if depth.get("downstream_trace_layers") != list(DOWNSTREAM_TRACE_LAYERS):
        errors.append("downstream layer grid differs")
    if depth.get("capture_states") != list(CAPTURE_STATES):
        errors.append("capture-state contract differs")
    if snapshot.get("design", {}).get("direct_positions") != list(DIRECT_POSITIONS):
        errors.append("direct-position set differs")

    try:
        volume_id = validate_volume_id(str(storage.get("volume_id", "")))
    except ValueError as exc:
        errors.append(str(exc))
        volume_id = None
    if expected_volume_id is not None and volume_id != expected_volume_id:
        errors.append("plan volume ID differs from expected_volume_id")
    if manifest.get("external_artifact_volume_id") != volume_id:
        errors.append("manifest/storage volume IDs differ")
    if snapshot.get("storage") != storage:
        errors.append("snapshot/storage contract copies differ")
    if storage.get("artifact_root_env") != ARTIFACT_ROOT_ENV:
        errors.append("artifact root environment variable differs")
    if storage.get("minimum_free_bytes") != MIN_FREE_BYTES:
        errors.append("external free-space reserve differs")
    if storage.get("absolute_artifact_paths_in_plan") is not False:
        errors.append("plan permits absolute artifact paths")
    if storage.get("local_outcome_fallback") is not False:
        errors.append("plan permits a local outcome fallback")
    for role, relative in storage.get("relative_namespaces", {}).items():
        path = Path(str(relative))
        if path.is_absolute() or ".." in path.parts:
            errors.append(f"storage namespace is not artifact-root-relative: {role}")

    controls = snapshot.get("controls", {})
    matched_payload = controls.get("matched_feature_map")
    matched_map: dict[int, int] | None
    try:
        matched_map = validate_matched_feature_map(
            {int(target): int(control) for target, control in matched_payload.items()}
            if isinstance(matched_payload, dict)
            else None
        )
    except (TypeError, ValueError) as exc:
        errors.append(f"invalid matched feature map: {exc}")
        matched_map = None
    if matched_map is None:
        if snapshot.get("status") != "precalibration_machine_plan_scaffold":
            errors.append("unresolved matched map has non-scaffold status")
        if controls.get("calibration_receipt_sha256") is not None:
            errors.append("unresolved matched map unexpectedly has calibration receipt")
    else:
        receipt_hash = controls.get("calibration_receipt_sha256")
        if not isinstance(receipt_hash, str) or len(receipt_hash) != 64:
            errors.append("resolved matched map lacks a receipt SHA-256")
        if controls.get("calibrated_multiplier_sensitivity") is None:
            errors.append("resolved matched map lacks calibrated multiplier")
        if snapshot.get("status") != "freeze_candidate_result_free_machine_plan":
            errors.append("resolved controls have non-candidate status")

    # Exact deterministic reconstruction prevents a caller from rehashing a
    # tampered condition allocation and presenting it as a new valid plan.
    expected_prefixes = prefix_rows()
    expected_blocks = aggregate_blocks()
    expected_assignments = prefix_block_assignments(expected_prefixes, expected_blocks)
    expected_main = main_branch_rows(expected_assignments, expected_blocks, matched_map)
    expected_probes = probe_templates()
    calibrated_multiplier = controls.get("calibrated_multiplier_sensitivity")
    expected_fixed = fixed_token_rows(
        expected_assignments,
        expected_blocks,
        matched_map,
        (
            float(calibrated_multiplier)
            if calibrated_multiplier is not None
            else None
        ),
    )
    _compare_exact(blocks, expected_blocks, "aggregate blocks", errors)
    _compare_exact(assignments, expected_assignments, "prefix/block assignments", errors)
    _compare_exact(main_rows, expected_main, "main branch plan", errors)
    _compare_exact(probes, expected_probes, "probe plan", errors)
    _compare_exact(fixed_rows, expected_fixed, "fixed-token plan", errors)
    try:
        assert_plan_invariants(
            expected_prefixes, blocks, assignments, main_rows, probes, fixed_rows
        )
    except (AssertionError, KeyError, TypeError, ValueError) as exc:
        errors.append(f"plan invariant failed: {exc}")

    if Counter(row.get("branch") for row in main_rows) != Counter(
        {branch: N_PREFIXES for branch in MAIN_BRANCHES}
    ):
        errors.append("main branch allocation count differs")
    if Counter(row.get("condition_name") for row in fixed_rows) != Counter(
        {condition: N_PREFIXES for condition in FIXED_TOKEN_CONDITIONS}
    ):
        errors.append("fixed-token condition count differs")
    if set(row.get("event_time") for row in probes if row.get("probe_role") == "active") != set(
        ACTIVE_PROBE_EVENT_TIMES
    ):
        errors.append("active probe event times differ")

    if upstream.get("study_id") != STUDY_ID or upstream.get("prior_outcome_inputs") != []:
        errors.append("upstream input isolation contract differs")
    if any(row.get("outcome_bearing") is not False for row in upstream.get("inputs", [])):
        errors.append("upstream input is outcome-bearing")

    if source_files.get("study_id") != STUDY_ID:
        errors.append("source-file receipt study_id differs")
    if source_files.get("prior_outcome_source_files") != []:
        errors.append("source-file receipt contains prior outcomes")
    source_records = source_files.get("files", [])
    observed_source_paths = [str(record.get("path", "")) for record in source_records]
    if observed_source_paths != list(EXPECTED_BOUND_SOURCE_RELATIVE_PATHS):
        errors.append("bound source-file list or order differs from the exact contract")
    if len(observed_source_paths) != len(set(observed_source_paths)):
        errors.append("bound source-file receipt contains duplicate paths")
    for record in source_records:
        relative = Path(str(record.get("path", "")))
        if relative.is_absolute() or ".." in relative.parts:
            errors.append(f"unsafe source-file path: {relative}")
            continue
        source = repo_root / relative
        if not source.is_file():
            errors.append(f"bound source file is missing: {relative}")
            continue
        if source.stat().st_size != int(record.get("bytes", -1)):
            errors.append(f"bound source byte count differs: {relative}")
        if sha256_file(source) != record.get("sha256"):
            errors.append(f"bound source hash differs: {relative}")
        if record.get("outcome_bearing") is not False:
            errors.append(f"bound source marked outcome-bearing: {relative}")

    plan_objects = [manifest, snapshot, upstream, storage, source_files, blocks, assignments, main_rows, probes, fixed_rows]
    serialized = json.dumps(plan_objects, ensure_ascii=False, sort_keys=True)
    for marker in PROHIBITED_OUTCOME_DEPENDENCIES:
        if marker in serialized:
            errors.append(f"prohibited prior-outcome dependency marker: {marker}")
    for value in plan_objects:
        for location, key, child in _walk(value):
            if key in OUTCOME_FIELD_NAMES:
                errors.append(f"outcome field is forbidden in machine plan: {location}")
            if isinstance(child, float) and (child != child or child in (float("inf"), float("-inf"))):
                errors.append(f"non-finite number in machine plan: {location}")

    expected_counts = {
        "prefix_occurrences": N_PREFIXES,
        "aggregate_blocks": N_AGGREGATE_BLOCKS,
        "main_branch_rows": N_PREFIXES * len(MAIN_BRANCHES),
        "probe_templates": 41,
        "planned_probe_generations": N_PREFIXES * 41,
        "fixed_token_rows": N_PREFIXES * len(FIXED_TOKEN_CONDITIONS),
    }
    if manifest.get("counts") != expected_counts:
        errors.append("manifest workload counts differ")

    return {
        "status": "pass" if not errors else "fail",
        "study_id": STUDY_ID,
        "protocol_version": PROTOCOL_VERSION,
        "plan_dir": str(plan_dir),
        "plan_hash": recomputed_hash,
        "plan_status": snapshot.get("status"),
        "volume_id": volume_id,
        "counts": expected_counts,
        "n_errors": len(errors),
        "errors": errors,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan-dir", type=Path, required=True)
    parser.add_argument("--expected-volume-id")
    parser.add_argument("--out", type=Path)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result = validate(
        args.plan_dir,
        expected_volume_id=args.expected_volume_id,
    )
    if args.out:
        output = args.out.resolve()
        if output == args.plan_dir.resolve() or args.plan_dir.resolve() in output.parents:
            raise ValueError("validation receipt must not mutate the sealed plan directory")
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    if result["status"] != "pass":
        raise SystemExit(1)


if __name__ == "__main__":
    main()

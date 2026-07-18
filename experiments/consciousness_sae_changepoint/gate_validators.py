#!/usr/bin/env python3
"""Independent validators for prospective target-blind acceptance gates.

The model-facing executor deliberately does not trust a child receipt merely
because it says ``status=pass``.  Each validator in this module opens a sealed
source receipt, checks its immutable bindings, and reconstructs the gate
decision from row-level evidence.  The first seven gates are expected to be
derived from a successor measured benchmark receipt's
``acceptance_evidence`` section.  The current benchmark receipt does not have
that section and therefore fails closed instead of promoting its generic
``technical_gates`` booleans.

No function in this module reads a target prompt, target transcript, or target
outcome file.
"""

from __future__ import annotations

import hashlib
import importlib
import json
import math
import re
from collections import defaultdict
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Any, Mapping, Sequence

from experiments.consciousness_sae_changepoint import benchmark, power
from experiments.consciousness_sae_changepoint.calibrate import (
    validate_artifact_receipt,
)
from experiments.consciousness_sae_changepoint.judge_prompts import (
    judge_prompt_receipt,
)
from experiments.consciousness_sae_changepoint.protocol import (
    J_MAP_LAYERS,
    MAIN_BRANCHES,
    MODEL_ID,
    MODEL_REVISION,
    N_PREFIXES,
    PROTOCOL_VERSION,
    STUDY_ID,
    canonical_json_bytes,
    sha256_file,
)
from experiments.consciousness_sae_changepoint.run import (
    GateValidationContext,
    GateValidationError,
    GateValidatorSpec,
    REPO_ROOT,
    embedded_receipt_sha256,
    paired_rng_context_sha256,
)
from experiments.consciousness_sae_changepoint.semantic_control_run import (
    SEMANTIC_CONTROL_RUN_SCHEMA_VERSION,
    validate_control_receipt,
)
from experiments.consciousness_sae_changepoint.storage import (
    validate_relative_path,
    verify_completed_run,
)


GATE_VALIDATOR_SOURCE = (
    "experiments/consciousness_sae_changepoint/gate_validators.py"
)
GATE_SCHEMA_VERSION = 1
SOURCE_BINDING_SCHEMA_VERSION = 1
HEX64 = re.compile(r"^[0-9a-f]{64}$")
MAX_SOURCE_RECEIPT_BYTES = 64 * 1024**2

BENCHMARK_EVIDENCE_GATES = (
    "cached_clean_equivalence",
    "fork_identity",
    "first_affected_distribution",
    "mask_contracts",
    "j_readout_algebra",
    "paired_rng",
    "order_resume_replay",
)

VALIDATOR_IDS = {
    gate_id: f"{gate_id}_independent_v1"
    for gate_id in (
        *BENCHMARK_EVIDENCE_GATES,
        "semantic_positive_control",
        "neutral_panel",
        "power_operating_characteristics",
        "measured_benchmark",
        "independent_plan_review",
        "judge_definition_frozen",
    )
}

# These are prospective numerical contracts, not values copied out of a result.
# A source amendment is required to change them and the validator source hash is
# itself bound into the acceptance manifest and machine plan.
CACHED_EQUIVALENCE_THRESHOLDS = {
    "maximum_relative_rmse": 0.01,
    "maximum_relative_max_abs_error": 0.05,
    "maximum_repeat_baseline_fraction": 0.5,
    "minimum_cosine_similarity": 0.9999,
}
J_ALGEBRA_THRESHOLDS = {
    "selected_vs_full_max_relative_error": 0.01,
    "identity_vs_direct_max_relative_error": 0.01,
}

COMMON_CHILD_FIELDS = {
    "gate_schema_version",
    "gate_id",
    "validator_id",
    "status",
    "study_id",
    "protocol_version",
    "outcome_blind",
    "target_outcomes_opened",
    "prior_outcome_inputs",
    "plan_hash",
    "artifact_receipt_sha256",
    "calibration_receipt_sha256",
    "created_at_utc",
    "evidence",
    "receipt_sha256",
}
SOURCE_CHILD_FIELDS = COMMON_CHILD_FIELDS | {"source"}


def _fail(code: str, detail: str) -> None:
    raise GateValidationError(code, detail)


def _is_hash(value: Any) -> bool:
    return isinstance(value, str) and bool(HEX64.fullmatch(value))


def _sha256_json(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _same_json(left: Any, right: Any) -> bool:
    return canonical_json_bytes(left) == canonical_json_bytes(right)


def _finite_number(value: Any, *, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        _fail("gate_metric_type", f"{label} must be numeric")
    number = float(value)
    if not math.isfinite(number):
        _fail("gate_metric_nonfinite", f"{label} must be finite")
    return number


def _exact_fields(value: Any, expected: set[str], *, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or set(value) != expected:
        _fail("gate_fields", f"{label} fields differ from the frozen schema")
    return value


def _parse_timestamp(value: Any) -> None:
    if not isinstance(value, str) or not value:
        _fail("gate_timestamp", "gate timestamp is missing")
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise GateValidationError("gate_timestamp", "gate timestamp is invalid") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        _fail("gate_timestamp", "gate timestamp must include an offset")


def _validate_child(
    receipt: Mapping[str, Any],
    context: GateValidationContext,
    *,
    gate_id: str,
    has_source: bool = True,
) -> None:
    _exact_fields(
        receipt,
        SOURCE_CHILD_FIELDS if has_source else COMMON_CHILD_FIELDS,
        label=f"{gate_id} child",
    )
    expected_validator = VALIDATOR_IDS[gate_id]
    if (
        receipt.get("gate_schema_version") != GATE_SCHEMA_VERSION
        or receipt.get("gate_id") != gate_id
        or receipt.get("validator_id") != expected_validator
        or receipt.get("status") != "pass"
        or receipt.get("study_id") != STUDY_ID
        or receipt.get("protocol_version") != PROTOCOL_VERSION
        or receipt.get("outcome_blind") is not True
        or receipt.get("target_outcomes_opened") is not False
        or receipt.get("prior_outcome_inputs") != []
        or receipt.get("plan_hash") != context.plan_hash
        or receipt.get("artifact_receipt_sha256")
        != context.artifact_receipt_sha256
        or receipt.get("calibration_receipt_sha256")
        != context.calibration_receipt_sha256
    ):
        _fail("gate_shared_binding", f"{gate_id} shared bindings differ")
    _parse_timestamp(receipt.get("created_at_utc"))
    embedded = receipt.get("receipt_sha256")
    if not _is_hash(embedded) or embedded_receipt_sha256(receipt) != embedded:
        _fail("gate_hash", f"{gate_id} child self-hash differs")


SOURCE_BINDING_FIELDS = {
    "schema_version",
    "receipt_relative_path",
    "container_relative_path",
    "container_kind",
    "bytes",
    "file_sha256",
    "embedded_sha256",
    "manifest_sha256",
}


def _no_symlink_path(root: Path, relative: str) -> Path:
    relative = validate_relative_path(relative)
    current = root
    for part in PurePosixPath(relative).parts:
        current = current / part
        if current.is_symlink():
            _fail("gate_source_symlink", "source receipt path contains a symlink")
    resolved = current.resolve(strict=True)
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise GateValidationError("gate_source_escape", "source escapes artifact root") from exc
    return resolved


def open_bound_source_receipt(
    source: Any,
    context: GateValidationContext,
) -> tuple[dict[str, Any], dict[str, Any], Path]:
    """Open a file only after independently verifying its completed run."""

    binding = _exact_fields(source, SOURCE_BINDING_FIELDS, label="source binding")
    if (
        binding.get("schema_version") != SOURCE_BINDING_SCHEMA_VERSION
        or binding.get("container_kind") != "completed_run"
    ):
        _fail("gate_source_schema", "only v1 completed-run source bindings are accepted")
    root = context.artifact_root.expanduser().resolve(strict=True)
    container = _no_symlink_path(root, str(binding.get("container_relative_path", "")))
    if not container.is_dir():
        _fail("gate_source_container", "source container is not a directory")
    try:
        sealed = verify_completed_run(container)
    except Exception as exc:
        raise GateValidationError(
            "gate_source_unsealed", "source receipt is not in a verified run"
        ) from exc
    if sealed.get("manifest_sha256") != binding.get("manifest_sha256"):
        _fail("gate_source_manifest", "source manifest hash differs")
    receipt_path = _no_symlink_path(root, str(binding.get("receipt_relative_path", "")))
    try:
        receipt_path.relative_to(container)
    except ValueError as exc:
        raise GateValidationError(
            "gate_source_container", "source receipt escapes its completed run"
        ) from exc
    expected_bytes = binding.get("bytes")
    if (
        isinstance(expected_bytes, bool)
        or not isinstance(expected_bytes, int)
        or not 0 < expected_bytes <= MAX_SOURCE_RECEIPT_BYTES
        or not receipt_path.is_file()
        or receipt_path.stat().st_size != expected_bytes
        or sha256_file(receipt_path) != binding.get("file_sha256")
    ):
        _fail("gate_source_file", "source receipt file bytes/hash differ")
    try:
        payload = json.loads(receipt_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise GateValidationError("gate_source_json", "source receipt is invalid JSON") from exc
    if not isinstance(payload, dict):
        _fail("gate_source_json", "source receipt must be an object")
    embedded = payload.get("receipt_sha256")
    if (
        not _is_hash(embedded)
        or embedded != binding.get("embedded_sha256")
        or embedded_receipt_sha256(payload) != embedded
    ):
        _fail("gate_source_embedded", "source embedded hash differs")
    return payload, dict(sealed), receipt_path


def _validated_benchmark_source(
    receipt: Mapping[str, Any], context: GateValidationContext
) -> tuple[dict[str, Any], Mapping[str, Any]]:
    source, _sealed, _path = open_bound_source_receipt(receipt.get("source"), context)
    if (
        source.get("outcome_blind") is not True
        or source.get("target_outcomes_opened") is not False
        or source.get("prior_outcome_inputs") != []
        or source.get("plan_hash") != context.plan_hash
        or source.get("artifact_receipt_sha256")
        != context.artifact_receipt_sha256
        or source.get("calibration_receipt_sha256")
        != context.calibration_receipt_sha256
    ):
        _fail(
            "benchmark_shared_binding",
            "benchmark lacks exact plan/artifact/calibration/target-blind bindings",
        )
    binding = source.get("artifact_root_binding")
    if not isinstance(binding, Mapping):
        _fail("benchmark_volume", "benchmark volume binding is missing")
    volume_id = binding.get("expected_volume_id")
    source_hash = sha256_file(REPO_ROOT / "experiments/consciousness_sae_changepoint/benchmark.py")
    try:
        benchmark.validate_benchmark_receipt(
            source,
            expected_plan_hash=context.plan_hash,
            expected_volume_id=str(volume_id),
            expected_prefix_count=N_PREFIXES,
            expected_source_sha256=source_hash,
        )
    except Exception as exc:
        raise GateValidationError(
            "benchmark_validation", "measured benchmark does not reconstruct"
        ) from exc
    evidence = source.get("acceptance_evidence")
    if not isinstance(evidence, Mapping):
        _fail(
            "benchmark_acceptance_evidence_missing",
            "benchmark has no row-level acceptance_evidence; generic pass flags are insufficient",
        )
    return source, evidence


def _benchmark_gate_evidence(
    receipt: Mapping[str, Any], context: GateValidationContext, *, gate_id: str
) -> Mapping[str, Any]:
    _validate_child(receipt, context, gate_id=gate_id)
    _source, all_evidence = _validated_benchmark_source(receipt, context)
    if set(all_evidence) != set(BENCHMARK_EVIDENCE_GATES):
        _fail("benchmark_evidence_set", "benchmark acceptance-evidence gate set differs")
    evidence = all_evidence.get(gate_id)
    if not isinstance(evidence, Mapping) or not _same_json(evidence, receipt.get("evidence")):
        _fail("gate_evidence_binding", f"{gate_id} child differs from benchmark evidence")
    return evidence


def _rows(evidence: Mapping[str, Any], gate_id: str, row_fields: set[str], minimum: int) -> list[Mapping[str, Any]]:
    rows = evidence.get("rows")
    if not isinstance(rows, list) or len(rows) < minimum:
        _fail("gate_rows", f"{gate_id} requires at least {minimum} rows")
    normalized: list[Mapping[str, Any]] = []
    ids: set[str] = set()
    for raw in rows:
        row = _exact_fields(raw, row_fields, label=f"{gate_id} row")
        fixture_id = row.get("fixture_id")
        if not isinstance(fixture_id, str) or not fixture_id or fixture_id in ids:
            _fail("gate_fixture_id", f"{gate_id} fixture IDs are invalid or duplicated")
        ids.add(fixture_id)
        normalized.append(row)
    return normalized


def validate_cached_clean_equivalence_gate(
    receipt: Mapping[str, Any], context: GateValidationContext
) -> Mapping[str, Any]:
    gate_id = "cached_clean_equivalence"
    evidence = _benchmark_gate_evidence(receipt, context, gate_id=gate_id)
    _exact_fields(evidence, {"schema_version", "gate_id", "thresholds", "rows", "summary"}, label=gate_id)
    if evidence.get("schema_version") != 1 or evidence.get("gate_id") != gate_id:
        _fail("cached_schema", "cached-clean evidence identity differs")
    if not _same_json(evidence.get("thresholds"), CACHED_EQUIVALENCE_THRESHOLDS):
        _fail("cached_thresholds", "cached-clean thresholds differ from source-frozen values")
    rows = _rows(
        evidence,
        gate_id,
        {
            "fixture_id", "prefix_token_ids_equal", "cached_logits_sha256",
            "uncached_logits_sha256", "max_abs_logit_error",
            "rmse_logit_error", "uncached_logit_rms", "cosine_similarity",
            "top1_token_id_equal", "repeat_max_abs_logit_error",
            "repeat_rmse_logit_error",
        },
        8,
    )
    reference_rms = [
        _finite_number(row["uncached_logit_rms"], label="uncached logit RMS")
        for row in rows
    ]
    if any(value <= 0 for value in reference_rms):
        _fail("cached_scale", "uncached logit RMS must be positive")
    relative_maximum = max(
        _finite_number(row["max_abs_logit_error"], label="cached max") / scale
        for row, scale in zip(rows, reference_rms)
    )
    relative_rmse_maximum = max(
        _finite_number(row["rmse_logit_error"], label="cached RMSE") / scale
        for row, scale in zip(rows, reference_rms)
    )
    repeat_relative_maximum = max(
        _finite_number(row["repeat_max_abs_logit_error"], label="repeat max") / scale
        for row, scale in zip(rows, reference_rms)
    )
    repeat_relative_rmse_maximum = max(
        _finite_number(row["repeat_rmse_logit_error"], label="repeat RMSE") / scale
        for row, scale in zip(rows, reference_rms)
    )
    cosine_minimum = min(_finite_number(row["cosine_similarity"], label="cached cosine") for row in rows)
    summary = {
        "fixture_count": len(rows),
        "maximum_relative_max_abs_error": relative_maximum,
        "maximum_relative_rmse": relative_rmse_maximum,
        "maximum_repeat_relative_max_abs_error": repeat_relative_maximum,
        "maximum_repeat_relative_rmse": repeat_relative_rmse_maximum,
        "minimum_cosine_similarity": cosine_minimum,
        "all_prefix_token_ids_equal": all(row["prefix_token_ids_equal"] is True for row in rows),
        "all_top1_token_ids_equal": all(row["top1_token_id_equal"] is True for row in rows),
    }
    if not _same_json(summary, evidence.get("summary")):
        _fail("cached_summary", "cached-clean summary does not reconstruct")
    if (
        relative_maximum
        > CACHED_EQUIVALENCE_THRESHOLDS["maximum_relative_max_abs_error"]
        or relative_rmse_maximum
        > CACHED_EQUIVALENCE_THRESHOLDS["maximum_relative_rmse"]
        or repeat_relative_maximum
        > CACHED_EQUIVALENCE_THRESHOLDS["maximum_relative_max_abs_error"]
        * CACHED_EQUIVALENCE_THRESHOLDS["maximum_repeat_baseline_fraction"]
        or repeat_relative_rmse_maximum
        > CACHED_EQUIVALENCE_THRESHOLDS["maximum_relative_rmse"]
        * CACHED_EQUIVALENCE_THRESHOLDS["maximum_repeat_baseline_fraction"]
        or cosine_minimum < CACHED_EQUIVALENCE_THRESHOLDS["minimum_cosine_similarity"]
        or not summary["all_prefix_token_ids_equal"]
        or not summary["all_top1_token_ids_equal"]
    ):
        _fail("cached_decision", "cached-clean equivalence metrics fail")
    return summary


def validate_fork_identity_gate(
    receipt: Mapping[str, Any], context: GateValidationContext
) -> Mapping[str, Any]:
    gate_id = "fork_identity"
    evidence = _benchmark_gate_evidence(receipt, context, gate_id=gate_id)
    _exact_fields(evidence, {"schema_version", "gate_id", "rows", "summary"}, label=gate_id)
    rows = _rows(
        evidence,
        gate_id,
        {
            "fixture_id", "parent_cache_sha256", "branch_a_initial_cache_sha256",
            "branch_b_initial_cache_sha256", "branch_a_clean_logits_sha256",
            "branch_b_clean_logits_sha256", "branch_a_output_cache_sha256",
            "branch_b_output_cache_sha256",
        },
        8,
    )
    passed = all(
        _is_hash(row[key])
        for row in rows
        for key in set(row) - {"fixture_id"}
    ) and all(
        row["parent_cache_sha256"] == row["branch_a_initial_cache_sha256"]
        == row["branch_b_initial_cache_sha256"]
        and row["branch_a_clean_logits_sha256"] == row["branch_b_clean_logits_sha256"]
        and row["branch_a_output_cache_sha256"] == row["branch_b_output_cache_sha256"]
        for row in rows
    )
    summary = {"fixture_count": len(rows), "all_exact_identity": passed}
    if not _same_json(summary, evidence.get("summary")) or not passed:
        _fail("fork_identity_decision", "clean cache forks are not exact twins")
    return summary


def validate_first_affected_distribution_gate(
    receipt: Mapping[str, Any], context: GateValidationContext
) -> Mapping[str, Any]:
    gate_id = "first_affected_distribution"
    evidence = _benchmark_gate_evidence(receipt, context, gate_id=gate_id)
    _exact_fields(evidence, {"schema_version", "gate_id", "rows", "summary"}, label=gate_id)
    rows = _rows(
        evidence,
        gate_id,
        {
            "fixture_id", "pre_event_distribution_clean_sha256",
            "pre_event_distribution_edited_sha256", "layer50_pre_clean_sha256",
            "layer50_pre_edited_sha256", "layer50_post_clean_sha256",
            "layer50_post_edited_sha256", "z0_clean_distribution_sha256",
            "z0_edited_distribution_sha256", "pre_event_max_abs_difference",
            "event_intervention_linf",
        },
        8,
    )
    passed = all(
        row["pre_event_distribution_clean_sha256"]
        == row["pre_event_distribution_edited_sha256"]
        and row["layer50_pre_clean_sha256"] == row["layer50_pre_edited_sha256"]
        and row["layer50_post_clean_sha256"] != row["layer50_post_edited_sha256"]
        and row["z0_clean_distribution_sha256"] != row["z0_edited_distribution_sha256"]
        and _finite_number(row["pre_event_max_abs_difference"], label="pre-event delta") == 0.0
        and _finite_number(row["event_intervention_linf"], label="event intervention") > 0.0
        for row in rows
    )
    summary = {
        "fixture_count": len(rows),
        "all_pre_event_exact": passed,
        "first_affected_distribution": "z[0]",
    }
    if not _same_json(summary, evidence.get("summary")) or not passed:
        _fail("first_affected_decision", "first affected distribution is not proven as z[0]")
    return summary


def validate_mask_contracts_gate(
    receipt: Mapping[str, Any], context: GateValidationContext
) -> Mapping[str, Any]:
    gate_id = "mask_contracts"
    evidence = _benchmark_gate_evidence(receipt, context, gate_id=gate_id)
    _exact_fields(evidence, {"schema_version", "gate_id", "rows", "summary"}, label=gate_id)
    rows = _rows(
        evidence,
        gate_id,
        {
            "fixture_id", "sequence_positions", "selected_positions",
            "expected_mask_sha256", "observed_mask_sha256", "hook_call_count",
            "outside_mask_max_abs_delta", "inside_mask_max_abs_delta",
            "active_hook_handles_before", "active_hook_handles_after",
        },
        8,
    )
    passed = all(
        isinstance(row["sequence_positions"], int)
        and row["sequence_positions"] >= 2
        and row["selected_positions"] == 1
        and _is_hash(row["expected_mask_sha256"])
        and row["expected_mask_sha256"] == row["observed_mask_sha256"]
        and row["hook_call_count"] == 1
        and _finite_number(row["outside_mask_max_abs_delta"], label="outside mask") == 0.0
        and _finite_number(row["inside_mask_max_abs_delta"], label="inside mask") > 0.0
        and row["active_hook_handles_before"] == row["active_hook_handles_after"] == 0
        for row in rows
    )
    summary = {"fixture_count": len(rows), "all_mask_and_cleanup_contracts_exact": passed}
    if not _same_json(summary, evidence.get("summary")) or not passed:
        _fail("mask_decision", "position mask, call count, or hook cleanup differs")
    return summary


def validate_j_readout_algebra_gate(
    receipt: Mapping[str, Any], context: GateValidationContext
) -> Mapping[str, Any]:
    gate_id = "j_readout_algebra"
    evidence = _benchmark_gate_evidence(receipt, context, gate_id=gate_id)
    _exact_fields(evidence, {"schema_version", "gate_id", "thresholds", "rows", "summary"}, label=gate_id)
    if not _same_json(evidence.get("thresholds"), J_ALGEBRA_THRESHOLDS):
        _fail("j_algebra_thresholds", "J algebra thresholds differ")
    rows = evidence.get("rows")
    if not isinstance(rows, list) or len(rows) != len(J_MAP_LAYERS):
        _fail("j_algebra_rows", "J algebra requires one row for every frozen map")
    normalized: list[Mapping[str, Any]] = []
    for raw in rows:
        normalized.append(
            _exact_fields(
                raw,
                {
                    "layer", "orientation", "selected_token_ids_sha256",
                    "selected_vs_full_max_relative_error",
                    "identity_vs_direct_max_relative_error",
                    "positive_direction_margin", "negative_direction_margin",
                },
                label="J algebra row",
            )
        )
    if sorted(int(row["layer"]) for row in normalized) != list(J_MAP_LAYERS):
        _fail("j_algebra_layers", "J algebra layer set differs")
    selected_max = max(
        _finite_number(
            row["selected_vs_full_max_relative_error"], label="selected/full"
        )
        for row in normalized
    )
    identity_max = max(
        _finite_number(
            row["identity_vs_direct_max_relative_error"], label="identity/direct"
        )
        for row in normalized
    )
    orientation_ok = all(
        row["orientation"] == "residual @ J_L.T"
        and _is_hash(row["selected_token_ids_sha256"])
        and _finite_number(row["positive_direction_margin"], label="positive margin") > 0
        and _finite_number(row["negative_direction_margin"], label="negative margin") < 0
        for row in normalized
    )
    summary = {
        "layer_count": len(normalized),
        "maximum_selected_vs_full_error": selected_max,
        "maximum_identity_vs_direct_error": identity_max,
        "all_orientation_and_sign_checks": orientation_ok,
    }
    if not _same_json(summary, evidence.get("summary")) or not orientation_ok or (
        selected_max > J_ALGEBRA_THRESHOLDS["selected_vs_full_max_relative_error"]
        or identity_max > J_ALGEBRA_THRESHOLDS["identity_vs_direct_max_relative_error"]
    ):
        _fail("j_algebra_decision", "J readout algebra does not reconstruct")
    return summary


def validate_paired_rng_gate(
    receipt: Mapping[str, Any], context: GateValidationContext
) -> Mapping[str, Any]:
    gate_id = "paired_rng"
    evidence = _benchmark_gate_evidence(receipt, context, gate_id=gate_id)
    _exact_fields(evidence, {"schema_version", "gate_id", "rows", "summary"}, label=gate_id)
    rows = evidence.get("rows")
    if not isinstance(rows, list) or len(rows) < len(MAIN_BRANCHES) * 8:
        _fail("paired_rng_rows", "paired RNG has too few branch-coordinate rows")
    fields = {
        "fixture_id", "prefix_seed", "paired_stream_id", "decode_step", "branch",
        "rng_context_sha256", "uniform_u64_sha256",
    }
    groups: dict[tuple[Any, ...], list[Mapping[str, Any]]] = defaultdict(list)
    for raw in rows:
        row = _exact_fields(raw, fields, label="paired RNG row")
        if row["branch"] not in MAIN_BRANCHES or not _is_hash(row["uniform_u64_sha256"]):
            _fail("paired_rng_row", "paired RNG branch/hash differs")
        expected = paired_rng_context_sha256(
            prefix_seed=int(row["prefix_seed"]),
            stream_id=str(row["paired_stream_id"]),
            decode_step=int(row["decode_step"]),
        )
        if row["rng_context_sha256"] != expected:
            _fail("paired_rng_context", "paired RNG context hash does not reconstruct")
        groups[(row["fixture_id"], row["prefix_seed"], row["paired_stream_id"], row["decode_step"])].append(row)
    passed = len(groups) >= 8 and all(
        {row["branch"] for row in group} == set(MAIN_BRANCHES)
        and len({row["uniform_u64_sha256"] for row in group}) == 1
        for group in groups.values()
    )
    summary = {"coordinate_count": len(groups), "row_count": len(rows), "all_branch_uniforms_exactly_paired": passed}
    if not _same_json(summary, evidence.get("summary")) or not passed:
        _fail("paired_rng_decision", "common random numbers are not exactly paired")
    return summary


def validate_order_resume_replay_gate(
    receipt: Mapping[str, Any], context: GateValidationContext
) -> Mapping[str, Any]:
    gate_id = "order_resume_replay"
    evidence = _benchmark_gate_evidence(receipt, context, gate_id=gate_id)
    _exact_fields(evidence, {"schema_version", "gate_id", "cases", "summary"}, label=gate_id)
    cases = evidence.get("cases")
    if not isinstance(cases, list) or len(cases) < 3:
        _fail("order_resume_cases", "order/resume replay requires at least three cases")
    fields = {
        "fixture_id", "canonical_order_output_inventory_sha256",
        "reversed_order_output_inventory_sha256", "fresh_output_inventory_sha256",
        "resumed_output_inventory_sha256", "canonical_sampling_inventory_sha256",
        "reversed_sampling_inventory_sha256",
    }
    fixture_ids: set[str] = set()
    passed = True
    for raw in cases:
        row = _exact_fields(raw, fields, label="order/resume case")
        fixture_id = row["fixture_id"]
        if not isinstance(fixture_id, str) or fixture_id in fixture_ids:
            _fail("order_resume_fixture", "order/resume fixture IDs differ")
        fixture_ids.add(fixture_id)
        if not all(_is_hash(row[key]) for key in fields - {"fixture_id"}):
            passed = False
        passed = passed and (
            row["canonical_order_output_inventory_sha256"]
            == row["reversed_order_output_inventory_sha256"]
            and row["fresh_output_inventory_sha256"] == row["resumed_output_inventory_sha256"]
            and row["canonical_sampling_inventory_sha256"]
            == row["reversed_sampling_inventory_sha256"]
        )
    summary = {"case_count": len(cases), "all_order_and_resume_inventories_exact": passed}
    if not _same_json(summary, evidence.get("summary")) or not passed:
        _fail("order_resume_decision", "batch order or resume replay changed an inventory")
    return summary


def neutral_panel_evidence(artifact_receipt: Mapping[str, Any]) -> dict[str, Any]:
    tokenizer = artifact_receipt.get("tokenizer")
    if not isinstance(tokenizer, Mapping):
        _fail("neutral_panel_tokenizer", "artifact tokenizer receipt is missing")
    return {
        "artifact_receipt_sha256": artifact_receipt.get("receipt_sha256"),
        "contextual_answer_suffix_token_ids": tokenizer.get("contextual_answer_suffix_token_ids"),
        "contextual_yes_no_are_single_tokens": tokenizer.get("contextual_yes_no_are_single_tokens"),
        "isolated_yes_token_ids": tokenizer.get("isolated_yes_token_ids"),
        "isolated_no_token_ids": tokenizer.get("isolated_no_token_ids"),
        "isolated_yes_no_are_single_tokens": tokenizer.get("isolated_yes_no_are_single_tokens"),
        "lexicons": tokenizer.get("lexicons"),
    }


def validate_neutral_panel_gate(
    receipt: Mapping[str, Any], context: GateValidationContext
) -> Mapping[str, Any]:
    gate_id = "neutral_panel"
    _validate_child(receipt, context, gate_id=gate_id)
    artifact, _sealed, _path = open_bound_source_receipt(receipt.get("source"), context)
    if artifact.get("receipt_sha256") != context.artifact_receipt_sha256:
        _fail("neutral_panel_artifact", "neutral panel source is not the bound artifact")
    try:
        validate_artifact_receipt(
            artifact, expected_volume_id=str(artifact.get("expected_volume_id"))
        )
    except Exception as exc:
        raise GateValidationError("neutral_panel_artifact", "artifact receipt fails reconstruction") from exc
    expected = neutral_panel_evidence(artifact)
    if not _same_json(expected, receipt.get("evidence")):
        _fail("neutral_panel_binding", "neutral-panel evidence differs from artifact receipt")
    contextual = expected["contextual_answer_suffix_token_ids"]
    lexicons = expected["lexicons"]
    if (
        expected["contextual_yes_no_are_single_tokens"] is not True
        or expected["isolated_yes_no_are_single_tokens"] is not True
        or not isinstance(contextual, Mapping)
        or set(contextual) != {"Yes", "No"}
        or any(not isinstance(value, list) or len(value) != 1 for value in contextual.values())
        or contextual["Yes"] == contextual["No"]
        or not isinstance(lexicons, Mapping)
        or lexicons.get("candidate_contract")
        != "exact one-token encoding and decoded round trip"
    ):
        _fail("neutral_panel_decision", "contextual Yes/No or lexicon contract fails")
    accepted = lexicons.get("accepted")
    if not isinstance(accepted, Mapping) or not accepted:
        _fail("neutral_panel_lexicons", "accepted lexicon panel is empty")
    for group, rows in accepted.items():
        if not isinstance(group, str) or not isinstance(rows, list) or len(rows) < 3:
            _fail("neutral_panel_lexicons", "lexicon group has fewer than three tokens")
        for row in rows:
            if (
                not isinstance(row, Mapping)
                or row.get("token_ids") != [row.get("token_id")]
                or row.get("decoded") != row.get("candidate")
            ):
                _fail("neutral_panel_lexicons", "accepted lexicon row is not exact")
    return {"lexicon_group_count": len(accepted), "contextual_yes_no_singletons": True}


def validate_semantic_positive_control_gate(
    receipt: Mapping[str, Any], context: GateValidationContext
) -> Mapping[str, Any]:
    gate_id = "semantic_positive_control"
    _validate_child(receipt, context, gate_id=gate_id)
    source, _sealed, _path = open_bound_source_receipt(receipt.get("source"), context)
    schema_version = source.get("schema_version")
    if source.get("outcome_blind") is not True or source.get(
        "target_outcomes_opened"
    ) is not False:
        _fail("semantic_control_binding", "semantic control shared bindings differ")
    try:
        if schema_version == SEMANTIC_CONTROL_RUN_SCHEMA_VERSION:
            if (
                source.get("prior_outcome_inputs") != []
                or source.get("artifact_receipt_sha256")
                != context.artifact_receipt_sha256
                or source.get("calibration_receipt_sha256")
                != context.calibration_receipt_sha256
            ):
                _fail(
                    "semantic_control_binding",
                    "legacy semantic control shared bindings differ",
                )
            result = validate_control_receipt(source)
            semantic_run_source = (
                REPO_ROOT
                / "experiments/consciousness_sae_changepoint/semantic_control_run.py"
            )
            if source.get("source_file_sha256") != sha256_file(
                semantic_run_source
            ):
                _fail(
                    "semantic_control_source",
                    "legacy semantic-control executor source changed",
                )
        elif schema_version == "consciousness_sae_control_composite_v1":
            # Fixed-name successor hook.  The composite module must perform its
            # own component receipt/manifests reconstruction; arbitrary module
            # names supplied by a receipt are never imported.
            composite = importlib.import_module(
                "experiments.consciousness_sae_changepoint.semantic_control_composite"
            )
            if (
                source.get("artifact_receipt_embedded_sha256")
                != context.artifact_receipt_sha256
                or source.get("calibration_receipt_embedded_sha256")
                != context.calibration_receipt_sha256
            ):
                _fail(
                    "semantic_control_binding",
                    "composite semantic control shared bindings differ",
                )
            result = composite.validate_control_receipt(
                source, artifact_root=context.artifact_root
            )
        else:
            _fail("semantic_control_schema", "semantic control schema is unsupported")
    except Exception as exc:
        raise GateValidationError("semantic_control_reconstruct", "semantic control does not reconstruct") from exc
    if result.get("passed") is not True or result.get("status") != "pass":
        _fail("semantic_control_decision", "semantic positive control did not pass")
    expected = {
        "validated_receipt_sha256": source.get("receipt_sha256"),
        "analysis_sha256": _sha256_json(source.get("analysis")),
        "selected_feature_ids": source.get("selected_feature_ids"),
        "executor_source_sha256": source.get("source_file_sha256"),
    }
    if not _same_json(expected, receipt.get("evidence")):
        _fail("semantic_control_evidence", "semantic-control child evidence differs")
    return {**result, "selected_feature_ids": expected["selected_feature_ids"]}


def validate_power_operating_characteristics_gate(
    receipt: Mapping[str, Any], context: GateValidationContext
) -> Mapping[str, Any]:
    gate_id = "power_operating_characteristics"
    _validate_child(receipt, context, gate_id=gate_id)
    source, _sealed, _path = open_bound_source_receipt(receipt.get("source"), context)
    if (
        source.get("target_blind") is not True
        or source.get("target_outcome_files_read") != []
        or source.get("plan_hash") != context.plan_hash
        or source.get("artifact_receipt_sha256") != context.artifact_receipt_sha256
        or source.get("calibration_receipt_sha256") != context.calibration_receipt_sha256
    ):
        _fail("power_shared_binding", "power receipt lacks exact shared bindings")
    try:
        validated = power.validate_power_receipt(source)
    except Exception as exc:
        raise GateValidationError("power_reconstruct", "power receipt does not reconstruct") from exc
    assessment = validated.get("assessment")
    if not isinstance(assessment, Mapping):
        _fail("power_assessment", "power assessment is missing")
    if (
        assessment.get("status") != "pass"
        or assessment.get("passed") is not True
        or assessment.get("provisional_power_gate_only") is not False
        or source.get("design_status") != "validated_for_registered_design"
        or source.get("freeze_authorization") is not False
    ):
        _fail("power_decision", "power is provisional, failing, or claims improper authorization")
    expected = {
        "validated_receipt_sha256": source.get("receipt_sha256"),
        "base_config_sha256": source.get("base_config_sha256"),
        "assessment_sha256": _sha256_json(assessment),
        "prefix_count": source.get("base_config", {}).get("n_blocks")
        if isinstance(source.get("base_config"), Mapping)
        else None,
    }
    if not _same_json(expected, receipt.get("evidence")):
        _fail("power_evidence", "power child evidence differs")
    return expected


def measured_benchmark_evidence(source: Mapping[str, Any]) -> dict[str, Any]:
    capacity = source.get("capacity_authorization_proposal")
    if not isinstance(capacity, Mapping):
        _fail("benchmark_capacity", "benchmark capacity proposal is missing")
    return {
        "validated_receipt_sha256": source.get("receipt_sha256"),
        "workload_contract_sha256": source.get("workload_contract_sha256"),
        "prefix_count": source.get("exact_max_workload", {}).get("prefixes")
        if isinstance(source.get("exact_max_workload"), Mapping)
        else None,
        "hard_proposed_gpu_hour_ceiling": capacity.get("hard_proposed_gpu_hour_ceiling"),
        "hard_proposed_storage_ceiling_gib": capacity.get("hard_proposed_storage_ceiling_gib"),
        "hard_proposed_spend_ceiling_usd": capacity.get("hard_proposed_spend_ceiling_usd"),
        "live_gpu_hourly_rate_usd": capacity.get("live_gpu_hourly_rate_usd"),
    }


def validate_measured_benchmark_gate(
    receipt: Mapping[str, Any], context: GateValidationContext
) -> Mapping[str, Any]:
    gate_id = "measured_benchmark"
    _validate_child(receipt, context, gate_id=gate_id)
    source, _all = _validated_benchmark_source(receipt, context)
    expected = measured_benchmark_evidence(source)
    if not _same_json(expected, receipt.get("evidence")):
        _fail("benchmark_evidence", "measured benchmark child evidence differs")
    for key in (
        "hard_proposed_gpu_hour_ceiling",
        "hard_proposed_storage_ceiling_gib",
    ):
        if isinstance(expected[key], bool) or not isinstance(expected[key], int) or expected[key] <= 0:
            _fail("benchmark_ceiling", f"{key} is not a positive hard ceiling")
    for key in ("hard_proposed_spend_ceiling_usd", "live_gpu_hourly_rate_usd"):
        try:
            number = float(expected[key])
        except (TypeError, ValueError) as exc:
            raise GateValidationError("benchmark_ceiling", f"{key} is invalid") from exc
        if not math.isfinite(number) or number <= 0:
            _fail("benchmark_ceiling", f"{key} is not positive and finite")
    return expected


REVIEW_SOURCE_FIELDS = {"path", "bytes", "sha256", "role"}
REQUIRED_REVIEW_ROLES = {
    "request_payload",
    "plan_audit",
    "review_manifest",
    "review",
    "adjudication",
}

PLAN_AUDIT_FIELDS = {
    "schema_version",
    "status",
    "study_id",
    "outcome_blind",
    "target_outcomes_opened",
    "prior_outcome_inputs",
    "plan_hash",
    "plan_manifest_sha256",
    "validate_plan_source_sha256",
    "source_inventory_sha256",
    "test_inventory_sha256",
    "all_tests_passed",
    "receipt_sha256",
}
ADJUDICATION_FIELDS = {
    "schema_version",
    "status",
    "reviewed_machine_plan_hash",
    "review_manifest_sha256",
    "review_sha256",
    "blocking_findings",
    "remaining_blocking_findings",
    "freeze_recommendation",
    "target_outcomes_opened",
    "prior_outcome_inputs",
    "receipt_sha256",
}
ADJUDICATED_FINDING_FIELDS = {
    "finding_id",
    "decision",
    "resolution",
    "evidence_sha256",
}


def validate_independent_plan_review_gate(
    receipt: Mapping[str, Any], context: GateValidationContext
) -> Mapping[str, Any]:
    gate_id = "independent_plan_review"
    _validate_child(receipt, context, gate_id=gate_id, has_source=False)
    evidence = _exact_fields(
        receipt.get("evidence"),
        {
            "schema_version", "reviewed_plan_hash", "model", "reasoning_mode",
            "review_verdict", "adjudication_status", "remaining_blocking_findings",
            "plan_audit_receipt_sha256", "source_files",
        },
        label="independent review evidence",
    )
    if (
        evidence.get("schema_version") != 1
        or evidence.get("reviewed_plan_hash") != context.plan_hash
        or evidence.get("model") != "gpt-5.6-sol"
        or evidence.get("reasoning_mode") != "pro"
        or evidence.get("review_verdict")
        not in {"READY TO FREEZE", "READY AFTER SPECIFIED FIXES"}
        or evidence.get("adjudication_status") != "complete"
        or evidence.get("remaining_blocking_findings") != []
    ):
        _fail("review_decision", "review/adjudication is not freeze-ready for this plan")
    records = evidence.get("source_files")
    if not isinstance(records, list) or len(records) != len(REQUIRED_REVIEW_ROLES):
        _fail("review_sources", "review source inventory is incomplete")
    by_role: dict[str, Path] = {}
    for raw in records:
        row = _exact_fields(raw, REVIEW_SOURCE_FIELDS, label="review source")
        role = row.get("role")
        relative = validate_relative_path(str(row.get("path", "")))
        if role in by_role or role not in REQUIRED_REVIEW_ROLES:
            _fail("review_sources", "review source role is duplicated or unexpected")
        if not relative.startswith("docs/consciousness_sae_changepoint/reviews/"):
            _fail("review_sources", "review source is outside the study review namespace")
        path = (REPO_ROOT / PurePosixPath(relative)).resolve(strict=True)
        try:
            path.relative_to(REPO_ROOT)
        except ValueError as exc:
            raise GateValidationError("review_sources", "review source escapes repository") from exc
        if (
            path.is_symlink()
            or not path.is_file()
            or path.stat().st_size != row.get("bytes")
            or sha256_file(path) != row.get("sha256")
        ):
            _fail("review_sources", "review source bytes/hash differ")
        by_role[str(role)] = path
    if set(by_role) != REQUIRED_REVIEW_ROLES:
        _fail("review_sources", "review source roles differ")
    try:
        manifest = json.loads(by_role["review_manifest"].read_text(encoding="utf-8"))
        plan_audit = json.loads(by_role["plan_audit"].read_text(encoding="utf-8"))
        adjudication = json.loads(by_role["adjudication"].read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise GateValidationError("review_json", "review manifest/adjudication must be JSON") from exc
    _exact_fields(plan_audit, PLAN_AUDIT_FIELDS, label="plan audit receipt")
    if (
        plan_audit.get("schema_version") != 1
        or plan_audit.get("status") != "pass"
        or plan_audit.get("study_id") != STUDY_ID
        or plan_audit.get("outcome_blind") is not True
        or plan_audit.get("target_outcomes_opened") is not False
        or plan_audit.get("prior_outcome_inputs") != []
        or plan_audit.get("plan_hash") != context.plan_hash
        or plan_audit.get("all_tests_passed") is not True
        or plan_audit.get("validate_plan_source_sha256")
        != sha256_file(
            REPO_ROOT / "experiments/consciousness_sae_changepoint/validate_plan.py"
        )
        or not all(
            _is_hash(plan_audit.get(key))
            for key in (
                "plan_manifest_sha256",
                "source_inventory_sha256",
                "test_inventory_sha256",
            )
        )
        or plan_audit.get("receipt_sha256") != embedded_receipt_sha256(plan_audit)
        or evidence.get("plan_audit_receipt_sha256")
        != plan_audit.get("receipt_sha256")
    ):
        _fail("plan_audit", "plan audit does not reconstruct for the reviewed plan")
    if (
        manifest.get("status") != "completed"
        or manifest.get("model") != "gpt-5.6-sol"
        or manifest.get("reasoning", {}).get("mode") != "pro"
        or manifest.get("reviewed_machine_plan_hash") != context.plan_hash
        or manifest.get("target_outcomes_opened") is not False
        or manifest.get("prior_outcome_inputs") != []
    ):
        _fail("review_manifest", "review manifest identity/blinding/plan binding differs")
    blocking_ids = manifest.get("blocking_finding_ids")
    if (
        not isinstance(blocking_ids, list)
        or not blocking_ids
        or len(blocking_ids) != len(set(blocking_ids))
        or any(not isinstance(value, str) or not re.fullmatch(r"B[0-9]{2,}", value) for value in blocking_ids)
        or manifest.get("review_verdict") != evidence.get("review_verdict")
        or manifest.get("review_sha256") != sha256_file(by_role["review"])
        or manifest.get("request_payload_sha256") != sha256_file(by_role["request_payload"])
    ):
        _fail("review_manifest", "review manifest hashes/verdict/finding IDs differ")
    _exact_fields(adjudication, ADJUDICATION_FIELDS, label="review adjudication")
    adjudicated = adjudication.get("blocking_findings")
    if not isinstance(adjudicated, list):
        _fail("review_adjudication", "adjudicated blocking findings are missing")
    decisions: dict[str, Mapping[str, Any]] = {}
    for raw in adjudicated:
        row = _exact_fields(raw, ADJUDICATED_FINDING_FIELDS, label="adjudicated finding")
        finding_id = row.get("finding_id")
        if finding_id in decisions or finding_id not in blocking_ids:
            _fail("review_adjudication", "adjudicated finding set differs")
        if (
            row.get("decision")
            not in {"accept", "accept_modified", "push_back_with_evidence"}
            or row.get("resolution") != "closed"
            or not _is_hash(row.get("evidence_sha256"))
        ):
            _fail("review_adjudication", "blocking finding is not evidentially closed")
        decisions[str(finding_id)] = row
    if (
        adjudication.get("status") != "complete"
        or adjudication.get("schema_version") != 1
        or adjudication.get("reviewed_machine_plan_hash") != context.plan_hash
        or adjudication.get("review_manifest_sha256")
        != sha256_file(by_role["review_manifest"])
        or adjudication.get("review_sha256") != sha256_file(by_role["review"])
        or set(decisions) != set(blocking_ids)
        or adjudication.get("remaining_blocking_findings") != []
        or adjudication.get("freeze_recommendation") != "pass"
        or adjudication.get("target_outcomes_opened") is not False
        or adjudication.get("prior_outcome_inputs") != []
        or adjudication.get("receipt_sha256")
        != embedded_receipt_sha256(adjudication)
    ):
        _fail("review_adjudication", "review adjudication does not close every blocker")
    review_text = by_role["review"].read_text(encoding="utf-8")
    if evidence["review_verdict"] not in review_text:
        _fail("review_verdict", "review file does not contain the claimed verdict")
    return {
        "reviewed_plan_hash": context.plan_hash,
        "review_manifest_sha256": sha256_file(by_role["review_manifest"]),
        "adjudication_sha256": sha256_file(by_role["adjudication"]),
    }


def judge_definition_evidence() -> dict[str, Any]:
    judge_prompts_path = REPO_ROOT / "experiments/consciousness_sae_changepoint/judge_prompts.py"
    judge_path = REPO_ROOT / "experiments/consciousness_sae_changepoint/judge.py"
    return {
        "judge_prompt_receipt": judge_prompt_receipt(),
        "model_id": MODEL_ID,
        "model_revision": MODEL_REVISION,
        "temperature": 0.0,
        "packet_fields": [
            "context_text", "packet_id", "response_text", "rubric_version", "task"
        ],
        "retry_policy": "one_identical_retry_only_after_provider_or_schema_failure",
        "condition_labels_redacted": True,
        "judge_prompts_source_sha256": sha256_file(judge_prompts_path),
        "judge_source_sha256": sha256_file(judge_path),
    }


def validate_judge_definition_frozen_gate(
    receipt: Mapping[str, Any], context: GateValidationContext
) -> Mapping[str, Any]:
    gate_id = "judge_definition_frozen"
    _validate_child(receipt, context, gate_id=gate_id, has_source=False)
    expected = judge_definition_evidence()
    if not _same_json(expected, receipt.get("evidence")):
        _fail("judge_definition", "judge definition differs from frozen source")
    return {
        "natural_prompt_sha256": expected["judge_prompt_receipt"]["natural_stance"]["utf8_sha256"],
        "binary_prompt_sha256": expected["judge_prompt_receipt"]["binary_query"]["utf8_sha256"],
        "judge_source_sha256": expected["judge_source_sha256"],
    }


def gate_validator_registry() -> dict[tuple[str, str], GateValidatorSpec]:
    validators = {
        "cached_clean_equivalence": validate_cached_clean_equivalence_gate,
        "fork_identity": validate_fork_identity_gate,
        "first_affected_distribution": validate_first_affected_distribution_gate,
        "mask_contracts": validate_mask_contracts_gate,
        "j_readout_algebra": validate_j_readout_algebra_gate,
        "paired_rng": validate_paired_rng_gate,
        "order_resume_replay": validate_order_resume_replay_gate,
        "semantic_positive_control": validate_semantic_positive_control_gate,
        "neutral_panel": validate_neutral_panel_gate,
        "power_operating_characteristics": validate_power_operating_characteristics_gate,
        "measured_benchmark": validate_measured_benchmark_gate,
        "independent_plan_review": validate_independent_plan_review_gate,
        "judge_definition_frozen": validate_judge_definition_frozen_gate,
    }
    specs = {
        gate_id: GateValidatorSpec(
            gate_id=gate_id,
            validator_id=VALIDATOR_IDS[gate_id],
            source_relative_path=GATE_VALIDATOR_SOURCE,
            validate=validator,
        )
        for gate_id, validator in validators.items()
    }
    return {(spec.gate_id, spec.validator_id): spec for spec in specs.values()}


__all__ = [
    "BENCHMARK_EVIDENCE_GATES",
    "CACHED_EQUIVALENCE_THRESHOLDS",
    "GATE_VALIDATOR_SOURCE",
    "J_ALGEBRA_THRESHOLDS",
    "VALIDATOR_IDS",
    "gate_validator_registry",
    "judge_definition_evidence",
    "measured_benchmark_evidence",
    "neutral_panel_evidence",
    "open_bound_source_receipt",
]

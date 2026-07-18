"""Pure, fail-closed analysis for the target-blind readout-validation pilot.

The functions in this module accept only in-memory row dictionaries.  They do
not discover files, load model artifacts, mutate archives, or import any prior
study.  Every public gate validates an exact prospective grid before computing
anything; missing, duplicate, unexpected, non-finite, or schema-different rows
raise :class:`AnalysisContractError` rather than becoming exclusions.

All scientific constants come from :mod:`.protocol`.  Resampling indexes use a
local version-independent random stream; NumPy evaluates the frozen direct
nonlinear G3 bootstrap without changing that stream.
"""

from __future__ import annotations

import math
import re
from collections import defaultdict
from collections.abc import Callable, Iterable, Mapping, Sequence
from itertools import combinations
from typing import Any

from . import protocol


class AnalysisContractError(ValueError):
    """A measurement inventory or value differs from the frozen contract."""


MASK64 = (1 << 64) - 1
G1_FIELDS = frozenset(
    {
        "layer",
        "synthetic_residual_id",
        "vocab_ids",
        "map_shape_valid",
        "map_finite",
        "production_finite",
        "reference_finite",
        "relative_rmse",
        "selected_logit_sign_agreement",
        "wrong_orientation_differs",
    }
)
TOKENIZER_AUDIT_RECEIPT_FIELDS = frozenset(
    {
        "schema_version",
        "study_id",
        "protocol_version",
        "status",
        "model_weights_loaded",
        "model_forward_count",
        "plan_manifest_sha256",
        "tokenizer_repository",
        "tokenizer_revision",
        "tokenizer_inventory_sha256",
        "g1",
        "semantic",
        "polarity",
        "receipt_sha256",
    }
)
MEASUREMENT_LINEAGE_FIELDS = frozenset(
    {
        "study_id",
        "protocol_version",
        "plan_manifest_sha256",
        "run_id",
        "task_id",
        "row_id",
    }
)
MEASUREMENT_BINDING_FIELDS = frozenset(
    {"study_id", "protocol_version", "plan_manifest_sha256", "run_id"}
)
MEASUREMENT_FILENAMES = (
    "g1_rows.jsonl",
    "g2_transport_rows.jsonl",
    "g2_linearity_rows.jsonl",
    "g3_rows.jsonl",
    "g3p_rows.jsonl",
    "g4_clean_rows.jsonl",
    "g4_vector_rows.jsonl",
    "g4_telemetry_rows.jsonl",
)
STRUCTURAL_AUDIT_SHARED_FIELDS = frozenset(
    {
        "issuer",
        "study_id",
        "protocol_version",
        "plan_manifest_sha256",
        "execution_binding_canonical_sha256",
        "source_inventory_sha256",
        "structural_audit_source_sha256",
        "tokenizer_audit_receipt_sha256",
        "vector_inventory_receipt_sha256",
        "phase_file_manifests",
        "phase_measurement_files",
        "prior_outcome_inputs",
        "target_prompt_inputs",
        "target_outcome_inputs",
    }
)
STRUCTURAL_AUDIT_RECEIPT_FIELDS = STRUCTURAL_AUDIT_SHARED_FIELDS | frozenset(
    {"schema_version", "receipt_kind", "status", "receipt_sha256"}
)
PILOT_ANALYSIS_AUTHORIZATION_FIELDS = STRUCTURAL_AUDIT_SHARED_FIELDS | frozenset(
    {
        "schema_version",
        "authorization_kind",
        "status",
        "structural_audit_receipt_sha256",
        "receipt_sha256",
    }
)
PHASE_FILE_MANIFEST_FIELDS = frozenset(
    {"file_manifest_content_sha256", "file_manifest_embedded_sha256"}
)
MEASUREMENT_FILE_BINDING_FIELDS = frozenset(
    {"row_count", "content_sha256", "logical_rows_sha256"}
)
PHASE_MEASUREMENT_FILENAMES = {
    "G1": ("g1_rows.jsonl",),
    "G2": ("g2_transport_rows.jsonl", "g2_linearity_rows.jsonl"),
    "G3": ("g3_rows.jsonl",),
    "G3P": ("g3p_rows.jsonl",),
    "G4": ("g4_clean_rows.jsonl", "g4_vector_rows.jsonl", "g4_telemetry_rows.jsonl"),
}


def _measurement_task_contract(
    filename: str, row: Mapping[str, Any]
) -> tuple[str, list[Any]]:
    if filename == "g1_rows.jsonl":
        return "g1", [row.get("layer"), row.get("synthetic_residual_id")]
    if filename == "g2_transport_rows.jsonl":
        return "g2_transport", [
            row.get("prompt_id"),
            row.get("layer"),
            row.get("direction"),
            row.get("transport"),
        ]
    if filename == "g2_linearity_rows.jsonl":
        return "g2_linearity", [
            row.get("prompt_id"),
            row.get("layer"),
            row.get("direction"),
        ]
    if filename == "g3_rows.jsonl":
        return "g3", [row.get("prompt_id"), row.get("transport"), row.get("layer")]
    if filename == "g3p_rows.jsonl":
        return "g3p", [row.get("prompt_id"), row.get("transport"), row.get("layer")]
    if filename == "g4_clean_rows.jsonl":
        return "g4_clean", [row.get("prompt_id")]
    subset = row.get("subset_feature_ids")
    normalized_subset = list(subset) if isinstance(subset, (list, tuple)) else subset
    if filename == "g4_vector_rows.jsonl":
        return "g4_vector", [normalized_subset, row.get("control_type"), row.get("sign")]
    if filename == "g4_telemetry_rows.jsonl":
        return "g4_telemetry", [
            row.get("prompt_id"),
            normalized_subset,
            row.get("control_type"),
            row.get("sign"),
        ]
    raise AnalysisContractError(f"no measurement task contract for {filename}")


def expected_measurement_task_id(filename: str, row: Mapping[str, Any]) -> str:
    kind, key = _measurement_task_contract(filename, row)
    if any(value is None for value in key):
        raise AnalysisContractError(f"{filename} measurement task key is incomplete")
    return protocol.stable_id(
        "measurement", {"measurement_kind": kind, "key": key}
    )


def expected_measurement_row_id(
    phase: str,
    filename: str,
    row_index: int,
    row: Mapping[str, Any],
) -> str:
    """Reconstruct the frozen ``PilotTransaction`` fallback row identity."""

    if phase not in PHASE_MEASUREMENT_FILENAMES or filename not in PHASE_MEASUREMENT_FILENAMES[
        phase
    ]:
        raise AnalysisContractError("measurement row phase/file contract differs")
    if isinstance(row_index, bool) or not isinstance(row_index, int) or row_index < 0:
        raise AnalysisContractError("measurement row index is invalid")
    run_id = row.get("run_id")
    if not isinstance(run_id, str) or not run_id:
        raise AnalysisContractError("measurement row run ID is invalid")
    original = {
        key: value
        for key, value in row.items()
        if key not in MEASUREMENT_BINDING_FIELDS and key != "row_id"
    }
    return protocol.canonical_sha256(
        {
            "study_id": protocol.STUDY_ID,
            "protocol_version": protocol.PROTOCOL_VERSION,
            "parts": (
                phase,
                run_id,
                filename,
                row_index,
                protocol.canonical_sha256(original),
            ),
        }
    )[:32]
G2_TRANSPORT_FIELDS = frozenset(
    {
        "prompt_id",
        "layer",
        "direction",
        "transport",
        "signed_pair_complete",
        "residual_delta_cosine",
        "fixed_token_logit_delta_pearson",
        "finite",
    }
)
G2_LINEARITY_FIELDS = frozenset(
    {
        "prompt_id",
        "layer",
        "direction",
        "central_difference_cosine",
        "slope_discrepancy",
        "finite",
    }
)
G3_FIELDS = frozenset(
    {
        "prompt_id",
        "true_family",
        "item_index",
        "render_mode",
        "transport",
        "layer",
        "token_logits",
        "finite",
    }
)
G3P_FIELDS = frozenset(
    {
        "prompt_id",
        "expected_answer",
        "transport",
        "layer",
        "yes_logit",
        "no_logit",
        "finite",
    }
)
G4_CLEAN_FIELDS = frozenset({"prompt_id", "h50_pre_rms", "finite"})
G4_VECTOR_FIELDS = frozenset(
    {
        "subset_feature_ids",
        "control_type",
        "sign",
        "coefficient",
        "vector_rms",
        "vector_sha256",
        "dtype",
        "finite",
        "precomputed_before_any_edited_forward",
        "edited_forward_count_at_compute",
    }
)
G4_TELEMETRY_FIELDS = frozenset(
    {
        "prompt_id",
        "subset_feature_ids",
        "control_type",
        "sign",
        "coefficient",
        "vector_sha256",
        "input_token_ids_sha256",
        "clean_input_token_ids_sha256",
        "clean_pre_edit_sha256",
        "edited_pre_edit_sha256",
        "expected_post_edit_sha256",
        "observed_post_edit_sha256",
        "clean_output_sha256",
        "sham_output_sha256",
        "realized_delta_relative_rmse",
        "sign_cosine",
        "hook_fire_count",
        "downstream_finite",
        "logits_finite",
        "attenuation_attempted",
        "retry_count",
    }
)
G4_VECTOR_INVENTORY_RECEIPT_FIELDS = frozenset(
    {
        "schema_version",
        "study_id",
        "protocol_version",
        "status",
        "plan_manifest_sha256",
        "sae_sha256",
        "decoder_bfloat16_sha256",
        "matching_spec_sha256",
        "vector_arithmetic_spec_sha256",
        "matching_candidate_inventory_sha256",
        "target_feature_ids",
        "excluded_feature_ids",
        "target_to_matched",
        "vectors",
        "receipt_sha256",
    }
)
G4_RESOLVED_VECTOR_FIELDS = frozenset(
    {
        "assignment_id",
        "subset_feature_ids",
        "control_type",
        "sign",
        "coefficient",
        "resolved_feature_ids",
        "isotropic_seed",
        "raw_norm",
        "raw_vector_sha256",
        "norm_rescale",
        "final_norm",
        "norm_relative_error",
        "target_reference_final_norm",
        "vector_rms",
        "vector_sha256",
        "dtype",
        "finite",
        "precomputed_before_any_edited_forward",
        "edited_forward_count_at_compute",
        "positive_vector_sha256",
        "negative_vector_sha256",
        "signed_pair_exact_negation",
        "signed_pair_relation_sha256",
    }
)


def _require_fields(row: Mapping[str, Any], fields: frozenset[str], label: str) -> None:
    if not isinstance(row, Mapping) or set(row) != fields:
        actual = set(row) if isinstance(row, Mapping) else set()
        raise AnalysisContractError(
            f"{label} fields differ; missing={sorted(fields - actual)}, "
            f"extra={sorted(actual - fields)}"
        )


def _finite(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise AnalysisContractError(f"{label} must be numeric")
    result = float(value)
    if not math.isfinite(result):
        raise AnalysisContractError(f"{label} must be finite")
    return result


def _nonnegative(value: Any, label: str) -> float:
    result = _finite(value, label)
    if result < 0.0:
        raise AnalysisContractError(f"{label} must be nonnegative")
    return result


def _unit_interval(value: Any, label: str) -> float:
    result = _finite(value, label)
    if not 0.0 <= result <= 1.0:
        raise AnalysisContractError(f"{label} must be inside [0,1]")
    return result


def _signed_unit_interval(value: Any, label: str) -> float:
    result = _finite(value, label)
    if not -1.0 <= result <= 1.0:
        raise AnalysisContractError(f"{label} must be inside [-1,1]")
    return result


def _integer(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise AnalysisContractError(f"{label} must be an integer")
    return value


def _boolean(value: Any, label: str) -> bool:
    if type(value) is not bool:
        raise AnalysisContractError(f"{label} must be a JSON boolean")
    return value


def _hex64(value: Any, label: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise AnalysisContractError(f"{label} must be lowercase SHA-256 text")
    return value


def _exact_index(
    rows: Iterable[Mapping[str, Any]],
    *,
    fields: frozenset[str],
    key: Callable[[Mapping[str, Any]], tuple[Any, ...]],
    expected: set[tuple[Any, ...]],
    label: str,
) -> dict[tuple[Any, ...], Mapping[str, Any]]:
    indexed: dict[tuple[Any, ...], Mapping[str, Any]] = {}
    for offset, row in enumerate(rows):
        _require_fields(row, fields, f"{label} row {offset}")
        identity = key(row)
        if identity in indexed:
            raise AnalysisContractError(f"duplicate {label} row: {identity!r}")
        indexed[identity] = row
    actual = set(indexed)
    if actual != expected:
        missing = sorted(expected - actual, key=repr)
        unexpected = sorted(actual - expected, key=repr)
        raise AnalysisContractError(
            f"{label} grid differs; missing={missing[:8]}, "
            f"unexpected={unexpected[:8]}, missing_count={len(missing)}, "
            f"unexpected_count={len(unexpected)}"
        )
    return indexed


def unwrap_measurement_rows(
    rows: Iterable[Mapping[str, Any]],
    *,
    measurement_fields: frozenset[str],
    lineage_binding: Mapping[str, Any] | None,
    label: str,
    measurement_kind: str | None = None,
    task_key: Callable[[Mapping[str, Any]], Sequence[Any]] | None = None,
    phase: str | None = None,
    filename: str | None = None,
) -> list[dict[str, Any]]:
    """Validate an optional sealed-runtime lineage envelope and strip it.

    Unit-level callers may provide already-authorized measurement-only rows by
    passing ``None``.  Runtime callers must pass the exact four-field binding;
    every envelope then has exactly six lineage fields plus the frozen
    measurement schema.  Mixed, duplicate, or cross-run envelopes fail closed.
    """

    materialized = list(rows)
    if lineage_binding is None:
        return [dict(row) for row in materialized]
    if not measurement_kind or task_key is None or phase is None or filename is None:
        raise AnalysisContractError(f"{label} lacks a frozen measurement task contract")
    _require_fields(lineage_binding, MEASUREMENT_BINDING_FIELDS, f"{label} binding")
    if (
        lineage_binding.get("study_id") != protocol.STUDY_ID
        or lineage_binding.get("protocol_version") != protocol.PROTOCOL_VERSION
        or not isinstance(lineage_binding.get("run_id"), str)
        or not lineage_binding.get("run_id")
    ):
        raise AnalysisContractError(f"{label} lineage identity differs")
    plan_hash = _hex64(
        lineage_binding.get("plan_manifest_sha256"), f"{label} plan manifest"
    )
    expected_fields = measurement_fields | MEASUREMENT_LINEAGE_FIELDS
    row_ids: set[str] = set()
    task_ids: set[str] = set()
    stripped: list[dict[str, Any]] = []
    for offset, row in enumerate(materialized):
        _require_fields(row, expected_fields, f"{label} envelope {offset}")
        for field in MEASUREMENT_BINDING_FIELDS:
            if row.get(field) != lineage_binding.get(field):
                raise AnalysisContractError(f"{label} envelope crosses lineage binding")
        row_id = row.get("row_id")
        task_id = row.get("task_id")
        measurement = {field: row[field] for field in measurement_fields}
        key = task_key(measurement)
        if isinstance(key, (str, bytes)) or not isinstance(key, Sequence):
            raise AnalysisContractError(f"{label} measurement task key is malformed")
        expected_task_id = protocol.stable_id(
            "measurement",
            {"measurement_kind": measurement_kind, "key": list(key)},
        )
        expected_row_id = expected_measurement_row_id(
            phase, filename, offset, row
        )
        if (
            not isinstance(row_id, str)
            or not row_id
            or row_id in row_ids
            or not isinstance(task_id, str)
            or not task_id
            or task_id in task_ids
        ):
            raise AnalysisContractError(f"{label} row/task identity is empty or duplicated")
        if task_id != expected_task_id:
            raise AnalysisContractError(f"{label} task ID does not reconstruct")
        if row_id != expected_row_id:
            raise AnalysisContractError(f"{label} row ID does not reconstruct")
        row_ids.add(row_id)
        task_ids.add(task_id)
        stripped.append(measurement)
    if plan_hash != lineage_binding["plan_manifest_sha256"]:  # pragma: no cover
        raise AssertionError("validated plan hash changed")
    return stripped


class _SplitMix64:
    """Tiny deterministic generator used only for frozen resampling indexes."""

    def __init__(self, seed: int) -> None:
        if isinstance(seed, bool) or not isinstance(seed, int):
            raise AnalysisContractError("resampling seed must be an integer")
        self.state = seed & MASK64

    def next_u64(self) -> int:
        self.state = (self.state + 0x9E3779B97F4A7C15) & MASK64
        value = self.state
        value = ((value ^ (value >> 30)) * 0xBF58476D1CE4E5B9) & MASK64
        value = ((value ^ (value >> 27)) * 0x94D049BB133111EB) & MASK64
        return (value ^ (value >> 31)) & MASK64

    def randbelow(self, stop: int) -> int:
        if stop <= 0:
            raise AnalysisContractError("randbelow stop must be positive")
        ceiling = ((1 << 64) // stop) * stop
        while True:
            value = self.next_u64()
            if value < ceiling:
                return value % stop

    def shuffle(self, values: list[Any]) -> None:
        for index in range(len(values) - 1, 0, -1):
            other = self.randbelow(index + 1)
            values[index], values[other] = values[other], values[index]


def _quantile(values: Sequence[float], probability: float) -> float:
    if not values or not 0.0 <= probability <= 1.0:
        raise AnalysisContractError("quantile input is invalid")
    ordered = sorted(values)
    position = (len(ordered) - 1) * probability
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    fraction = position - lower
    return ordered[lower] * (1.0 - fraction) + ordered[upper] * fraction


def clustered_bootstrap_lcb(
    cluster_series: Mapping[str, Mapping[str, Any]],
    statistic: Callable[[Mapping[str, float]], float],
    *,
    strata: Mapping[str, str] | None = None,
    replicates: int | None = None,
    seed: int | None = None,
    alpha: float = 0.05,
) -> dict[str, Any]:
    """Deterministic stratified cluster-bootstrap lower confidence bound."""

    n_replicates = protocol.BOOTSTRAP_REPLICATES if replicates is None else replicates
    frozen_seed = protocol.BOOTSTRAP_SEED if seed is None else seed
    if (
        isinstance(n_replicates, bool)
        or not isinstance(n_replicates, int)
        or n_replicates < 1
        or not 0.0 < alpha < 1.0
        or not cluster_series
    ):
        raise AnalysisContractError("bootstrap configuration is invalid")
    names: tuple[str, ...] | None = None
    normalized: dict[str, dict[str, float]] = {}
    for cluster_id, raw in cluster_series.items():
        if not isinstance(cluster_id, str) or not cluster_id or not isinstance(raw, Mapping):
            raise AnalysisContractError("bootstrap clusters must be named mappings")
        current = tuple(sorted(raw))
        if names is None:
            names = current
        elif current != names:
            raise AnalysisContractError("bootstrap series fields differ by cluster")
        normalized[cluster_id] = {
            name: _finite(raw[name], f"bootstrap {cluster_id}/{name}") for name in current
        }
    if not names:
        raise AnalysisContractError("bootstrap series may not be empty")
    if strata is None:
        strata = {cluster_id: "all" for cluster_id in normalized}
    if set(strata) != set(normalized):
        raise AnalysisContractError("bootstrap strata differ from cluster inventory")
    grouped: dict[str, list[str]] = defaultdict(list)
    for cluster_id in sorted(normalized):
        stratum = strata[cluster_id]
        if not isinstance(stratum, str) or not stratum:
            raise AnalysisContractError("bootstrap stratum must be nonempty text")
        grouped[stratum].append(cluster_id)

    def aggregate(cluster_ids: Sequence[str]) -> dict[str, float]:
        return {
            name: sum(normalized[item][name] for item in cluster_ids) / len(cluster_ids)
            for name in names or ()
        }

    point = _finite(statistic(aggregate(sorted(normalized))), "bootstrap statistic")
    generator = _SplitMix64(frozen_seed)
    draws: list[float] = []
    for _ in range(n_replicates):
        sample: list[str] = []
        for stratum in sorted(grouped):
            members = grouped[stratum]
            sample.extend(members[generator.randbelow(len(members))] for _ in members)
        draws.append(_finite(statistic(aggregate(sample)), "bootstrap draw"))
    return {
        "estimate": point,
        "lcb_95": _quantile(draws, alpha),
        "alpha": alpha,
        "clusters": len(normalized),
        "replicates": n_replicates,
        "seed": frozen_seed,
        "algorithm": "splitmix64_stratified_prompt_cluster_percentile_v1",
    }


def deterministic_permutation_p_value(
    labels: Sequence[str],
    values: Sequence[Any],
    statistic: Callable[[Sequence[str], Sequence[Any]], float],
    *,
    strata: Sequence[str] | None = None,
    replicates: int | None = None,
    seed: int | None = None,
) -> dict[str, Any]:
    """One-sided deterministic family-label permutation test helper."""

    if len(labels) != len(values) or not labels:
        raise AnalysisContractError("permutation labels/values differ or are empty")
    n_replicates = (
        protocol.PERMUTATION_REPLICATES if replicates is None else replicates
    )
    frozen_seed = protocol.PERMUTATION_SEED if seed is None else seed
    if isinstance(n_replicates, bool) or not isinstance(n_replicates, int) or n_replicates < 1:
        raise AnalysisContractError("permutation replicate count is invalid")
    groups: dict[str, list[int]] = defaultdict(list)
    effective_strata = list(strata) if strata is not None else ["all"] * len(labels)
    if len(effective_strata) != len(labels):
        raise AnalysisContractError("permutation strata length differs")
    for index, stratum in enumerate(effective_strata):
        groups[str(stratum)].append(index)
    observed = _finite(statistic(labels, values), "observed permutation statistic")
    generator = _SplitMix64(frozen_seed)
    extreme = 0
    for _ in range(n_replicates):
        permuted = list(labels)
        for stratum in sorted(groups):
            indexes = groups[stratum]
            local = [labels[index] for index in indexes]
            generator.shuffle(local)
            for index, label in zip(indexes, local):
                permuted[index] = label
        draw = _finite(statistic(permuted, values), "permutation draw")
        extreme += draw >= observed
    return {
        "estimate": observed,
        "p_value": (extreme + 1.0) / (n_replicates + 1.0),
        "replicates": n_replicates,
        "seed": frozen_seed,
        "algorithm": "splitmix64_stratified_label_permutation_v1",
    }


def stratified_cluster_bootstrap(
    cluster_ids: Sequence[str],
    statistic: Callable[[Sequence[str]], float],
    *,
    strata: Mapping[str, str],
    replicates: int | None = None,
    seed: int | None = None,
    alpha: float = 0.05,
) -> dict[str, Any]:
    """Bootstrap an arbitrary statistic while keeping each prompt as a cluster."""

    ordered = tuple(cluster_ids)
    if (
        not ordered
        or len(ordered) != len(set(ordered))
        or set(ordered) != set(strata)
        or not 0.0 < alpha < 1.0
    ):
        raise AnalysisContractError("cluster-bootstrap inventory is invalid")
    n_replicates = protocol.BOOTSTRAP_REPLICATES if replicates is None else replicates
    frozen_seed = protocol.BOOTSTRAP_SEED if seed is None else seed
    if isinstance(n_replicates, bool) or not isinstance(n_replicates, int) or n_replicates < 1:
        raise AnalysisContractError("cluster-bootstrap replicate count is invalid")
    grouped: dict[str, list[str]] = defaultdict(list)
    for cluster_id in ordered:
        stratum = strata[cluster_id]
        if not isinstance(stratum, str) or not stratum:
            raise AnalysisContractError("cluster-bootstrap stratum is invalid")
        grouped[stratum].append(cluster_id)
    point = _finite(statistic(ordered), "cluster-bootstrap statistic")
    generator = _SplitMix64(frozen_seed)
    draws: list[float] = []
    for _ in range(n_replicates):
        sample: list[str] = []
        for stratum in sorted(grouped):
            members = grouped[stratum]
            sample.extend(members[generator.randbelow(len(members))] for _ in members)
        draws.append(_finite(statistic(sample), "cluster-bootstrap draw"))
    return {
        "estimate": point,
        "lcb_95": _quantile(draws, alpha),
        "alpha": alpha,
        "clusters": len(ordered),
        "replicates": n_replicates,
        "seed": frozen_seed,
        "algorithm": "splitmix64_stratified_prompt_cluster_percentile_v1",
    }


def normalized_trapezoid(values: Mapping[int, Any], layers: Sequence[int]) -> float:
    ordered = tuple(layers)
    if len(ordered) < 2 or tuple(sorted(ordered)) != ordered or len(set(ordered)) != len(ordered):
        raise AnalysisContractError("trapezoid layers must be unique and increasing")
    if set(values) != set(ordered):
        raise AnalysisContractError("trapezoid layer grid differs")
    numbers = {layer: _finite(values[layer], f"layer {layer}") for layer in ordered}
    width = ordered[-1] - ordered[0]
    if width <= 0:
        raise AnalysisContractError("trapezoid depth width must be positive")
    total = 0.0
    for left, right in zip(ordered, ordered[1:]):
        total += (numbers[left] + numbers[right]) * (right - left) / 2.0
    return total / width


_G1_PIECE = re.compile(r" [A-Za-z]{3,16}")
_G1_CANDIDATE_FIELDS = frozenset(
    {
        "sequence_index",
        "panel_index",
        "attempt",
        "token_id",
        "exact_piece",
        "decision",
        "reason",
    }
)
_G1_REJECTED_FIELDS = frozenset(
    {
        "sequence_index",
        "panel_index",
        "attempt",
        "token_id",
        "exact_piece",
        "reason",
    }
)
_G1_AUDIT_FIELDS = frozenset(
    {
        "candidate_sequence",
        "accepted_token_ids",
        "accepted_exact_token_pieces",
        "rejected_token_ids_and_reasons",
        "special_token_ids",
        "experimental_lexicon_token_ids",
        "selection_rule_sha256",
        "token_panel_canonical_sha256",
    }
)
_SEMANTIC_AUDIT_FIELDS = frozenset(
    {"groups", "ordered_union_token_ids", "contextual_boundaries"}
)
_POLARITY_AUDIT_FIELDS = frozenset(
    {"isolated_token_ids", "contextual_boundaries"}
)


def _token_id(value: Any, label: str) -> int:
    result = _integer(value, label)
    if not 0 <= result < protocol.MODEL_SPEC["tokenizer_vocabulary_size"]:
        raise AnalysisContractError(f"{label} is outside the pinned vocabulary")
    return result


def _validate_g1_audit(g1: Any) -> tuple[int, ...]:
    _require_fields(g1, _G1_AUDIT_FIELDS, "tokenizer audit G1")
    sequence = g1["candidate_sequence"]
    if not isinstance(sequence, list) or not sequence:
        raise AnalysisContractError("tokenizer audit G1 candidate sequence is empty")
    special_raw = g1["special_token_ids"]
    if not isinstance(special_raw, list) or not special_raw:
        raise AnalysisContractError("tokenizer audit special-token inventory is empty")
    special_ids = tuple(
        _token_id(value, "tokenizer audit special-token ID") for value in special_raw
    )
    if special_ids != tuple(sorted(set(special_ids))):
        raise AnalysisContractError("tokenizer audit special-token inventory differs")

    lexicon = g1["experimental_lexicon_token_ids"]
    if not isinstance(lexicon, Mapping) or set(lexicon) != set(
        protocol.G1_TOKEN_REJECTION_LEXICON
    ):
        raise AnalysisContractError("tokenizer audit rejection-lexicon inventory differs")
    for word in protocol.G1_TOKEN_REJECTION_LEXICON:
        encoded = lexicon[word]
        if not isinstance(encoded, list):
            raise AnalysisContractError("tokenizer audit lexicon encoding is malformed")
        for value in encoded:
            _token_id(value, f"tokenizer audit lexicon token for {word}")

    accepted_ids: list[int] = []
    accepted_pieces: list[str] = []
    rejected: list[dict[str, Any]] = []
    panel_index = 0
    attempt = 0
    rejection_lexicon = {
        word.casefold() for word in protocol.G1_TOKEN_REJECTION_LEXICON
    }
    valid_reasons = set(protocol.G1_TOKEN_SELECTION_RULE["reject_if"])
    for offset, raw in enumerate(sequence):
        _require_fields(raw, _G1_CANDIDATE_FIELDS, f"G1 candidate {offset}")
        if (
            _integer(raw["sequence_index"], "G1 candidate sequence index") != offset
            or _integer(raw["panel_index"], "G1 candidate panel index") != panel_index
            or _integer(raw["attempt"], "G1 candidate attempt") != attempt
        ):
            raise AnalysisContractError("G1 candidate coordinates are not complete and ordered")
        token_id = _token_id(raw["token_id"], "G1 candidate token ID")
        if token_id != protocol.g1_token_candidate_id(panel_index, attempt):
            raise AnalysisContractError("G1 candidate does not follow the frozen hash stream")
        piece = raw["exact_piece"]
        decision = raw["decision"]
        reason = raw["reason"]
        if not isinstance(piece, str) or decision not in {"accept", "reject"}:
            raise AnalysisContractError("G1 candidate decision or piece is malformed")
        if decision == "accept":
            if (
                reason != "accepted"
                or token_id in accepted_ids
                or token_id in special_ids
                or _G1_PIECE.fullmatch(piece) is None
                or piece[1:].casefold() in rejection_lexicon
            ):
                raise AnalysisContractError("G1 accepted candidate violates the selector")
            accepted_ids.append(token_id)
            accepted_pieces.append(piece)
            panel_index += 1
            attempt = 0
        else:
            if reason not in valid_reasons:
                raise AnalysisContractError("G1 rejection reason is not frozen")
            if reason == "duplicate_id" and token_id not in accepted_ids:
                raise AnalysisContractError("G1 duplicate rejection is unsupported")
            if reason == "special_token_id" and token_id not in special_ids:
                raise AnalysisContractError("G1 special-token rejection is unsupported")
            if (
                reason
                == "decoded_piece_does_not_fullmatch_ASCII_space_word_[A-Za-z]{3,16}"
                and _G1_PIECE.fullmatch(piece) is not None
            ):
                raise AnalysisContractError("G1 lexical rejection is unsupported")
            if (
                reason == "casefolded_word_is_in_G1_TOKEN_REJECTION_LEXICON"
                and (
                    _G1_PIECE.fullmatch(piece) is None
                    or piece[1:].casefold() not in rejection_lexicon
                )
            ):
                raise AnalysisContractError("G1 endpoint-lexicon rejection is unsupported")
            rejected.append(
                {
                    "sequence_index": offset,
                    "panel_index": panel_index,
                    "attempt": attempt,
                    "token_id": token_id,
                    "exact_piece": piece,
                    "reason": reason,
                }
            )
            attempt += 1
    if panel_index != protocol.G1_TOKEN_PANEL_SIZE or attempt != 0:
        raise AnalysisContractError("G1 selector did not resolve exactly 32 complete slots")
    if len(set(accepted_pieces)) != len(accepted_pieces):
        raise AnalysisContractError("G1 accepted exact pieces are not unique")
    if g1["accepted_token_ids"] != accepted_ids or g1[
        "accepted_exact_token_pieces"
    ] != accepted_pieces:
        raise AnalysisContractError("G1 accepted-panel projection differs")
    rejected_rows = g1["rejected_token_ids_and_reasons"]
    if not isinstance(rejected_rows, list):
        raise AnalysisContractError("G1 rejected-candidate projection is malformed")
    for offset, row in enumerate(rejected_rows):
        _require_fields(row, _G1_REJECTED_FIELDS, f"G1 rejected candidate {offset}")
    if rejected_rows != rejected:
        raise AnalysisContractError("G1 rejected-candidate projection differs")
    if g1["selection_rule_sha256"] != protocol.canonical_sha256(
        protocol.G1_TOKEN_SELECTION_RULE
    ):
        raise AnalysisContractError("G1 selection-rule hash differs")
    core = dict(g1)
    panel_hash = _hex64(
        core.pop("token_panel_canonical_sha256"), "G1 canonical panel hash"
    )
    if panel_hash != protocol.canonical_sha256(core):
        raise AnalysisContractError("G1 canonical panel hash does not reconstruct")
    return tuple(accepted_ids)


def _validate_semantic_audit(semantic: Any) -> tuple[str, tuple[int, ...]]:
    _require_fields(semantic, _SEMANTIC_AUDIT_FIELDS, "tokenizer semantic audit")
    groups = semantic["groups"]
    if not isinstance(groups, Mapping) or set(groups) != set(protocol.G3_FAMILIES):
        raise AnalysisContractError("semantic endpoint family inventory differs")
    union: list[int] = []
    labels: list[str] = []
    endpoint_fields = frozenset({"token", "piece", "token_id"})
    for family in protocol.G3_FAMILIES:
        rows = groups[family]
        expected_tokens = protocol.G3_TOKEN_GROUPS[family]
        if not isinstance(rows, list) or len(rows) != len(expected_tokens):
            raise AnalysisContractError("semantic endpoint group size differs")
        for token, row in zip(expected_tokens, rows):
            _require_fields(row, endpoint_fields, f"semantic endpoint {family}/{token}")
            if row["token"] != token or row["piece"] != f" {token}":
                raise AnalysisContractError("semantic endpoint text differs")
            union.append(_token_id(row["token_id"], f"semantic endpoint {token}"))
            labels.append(token)
    if len(union) != len(set(union)) or semantic["ordered_union_token_ids"] != union:
        raise AnalysisContractError("semantic endpoint token-ID union differs")
    contexts = semantic["contextual_boundaries"]
    fixtures = tuple(row["fixture_id"] for row in protocol.g3_fixture_rows())
    if not isinstance(contexts, list) or len(contexts) != len(fixtures):
        raise AnalysisContractError("semantic contextual-boundary count differs")
    context_fields = frozenset(
        {
            "fixture_id",
            "context_token_ids_sha256",
            "context_token_count",
            "continuation_full_token_ids_sha256",
        }
    )
    observed_fixtures: list[str] = []
    for offset, row in enumerate(contexts):
        _require_fields(row, context_fields, f"semantic context {offset}")
        observed_fixtures.append(str(row["fixture_id"]))
        _hex64(row["context_token_ids_sha256"], "semantic context-token hash")
        if _integer(row["context_token_count"], "semantic context-token count") <= 0:
            raise AnalysisContractError("semantic context-token count must be positive")
        continuations = row["continuation_full_token_ids_sha256"]
        if not isinstance(continuations, Mapping) or set(continuations) != set(labels):
            raise AnalysisContractError("semantic continuation inventory differs")
        for digest in continuations.values():
            _hex64(digest, "semantic continuation hash")
    if tuple(observed_fixtures) != fixtures:
        raise AnalysisContractError("semantic contextual fixtures are not exact and ordered")
    return protocol.canonical_sha256(semantic), tuple(union)


def _validate_polarity_audit(polarity: Any) -> tuple[str, tuple[int, ...]]:
    _require_fields(polarity, _POLARITY_AUDIT_FIELDS, "tokenizer polarity audit")
    if polarity["isolated_token_ids"] != protocol.G3P_ANSWER_TOKEN_IDS:
        raise AnalysisContractError("G3P isolated Yes/No token IDs differ")
    contexts = polarity["contextual_boundaries"]
    prompt_ids = tuple(row["prompt_id"] for row in protocol.g3p_plan_rows())
    if not isinstance(contexts, list) or len(contexts) != len(prompt_ids):
        raise AnalysisContractError("G3P contextual-boundary count differs")
    context_fields = frozenset(
        {
            "prompt_id",
            "context_token_ids_sha256",
            "context_token_count",
            "continuations",
        }
    )
    continuation_fields = frozenset(
        {"token_id", "eot_token_id", "full_token_ids_sha256", "exact_suffix"}
    )
    observed: list[str] = []
    for offset, row in enumerate(contexts):
        _require_fields(row, context_fields, f"G3P context {offset}")
        observed.append(str(row["prompt_id"]))
        _hex64(row["context_token_ids_sha256"], "G3P context-token hash")
        if _integer(row["context_token_count"], "G3P context-token count") <= 0:
            raise AnalysisContractError("G3P context-token count must be positive")
        continuations = row["continuations"]
        if not isinstance(continuations, Mapping) or set(continuations) != set(
            protocol.G3P_ANSWER_TOKEN_IDS
        ):
            raise AnalysisContractError("G3P continuation inventory differs")
        for piece, token_id in protocol.G3P_ANSWER_TOKEN_IDS.items():
            continuation = continuations[piece]
            _require_fields(
                continuation, continuation_fields, f"G3P continuation {piece}"
            )
            if (
                continuation["token_id"] != token_id
                or continuation["eot_token_id"] != protocol.G3P_EOT_TOKEN_ID
                or _boolean(continuation["exact_suffix"], "G3P exact suffix") is not True
            ):
                raise AnalysisContractError("G3P contextual answer suffix differs")
            _hex64(continuation["full_token_ids_sha256"], "G3P continuation hash")
    if tuple(observed) != prompt_ids:
        raise AnalysisContractError("G3P contextual prompts are not exact and ordered")
    return protocol.canonical_sha256(polarity), tuple(
        protocol.G3P_ANSWER_TOKEN_IDS.values()
    )


def validate_tokenizer_audit_receipt(receipt: Mapping[str, Any] | None) -> dict[str, Any]:
    """Independently reconstruct the complete tokenizer-audit binding."""

    if receipt is None:
        raise AnalysisContractError(
            "analysis requires the complete tokenizer audit receipt"
        )
    _require_fields(receipt, TOKENIZER_AUDIT_RECEIPT_FIELDS, "tokenizer audit receipt")
    if (
        receipt.get("schema_version") != 1
        or receipt.get("study_id") != protocol.STUDY_ID
        or receipt.get("protocol_version") != protocol.PROTOCOL_VERSION
        or receipt.get("status") != "pass"
        or _boolean(receipt.get("model_weights_loaded"), "tokenizer model-loaded flag")
        or _integer(receipt.get("model_forward_count"), "tokenizer forward count") != 0
        or receipt.get("tokenizer_repository") != protocol.MODEL_SPEC["repository"]
        or receipt.get("tokenizer_revision") != protocol.MODEL_SPEC["revision"]
    ):
        raise AnalysisContractError("tokenizer audit identity or model-free status differs")
    plan_hash = _hex64(receipt["plan_manifest_sha256"], "tokenizer plan manifest")
    inventory_hash = _hex64(
        receipt["tokenizer_inventory_sha256"], "tokenizer inventory hash"
    )
    token_ids = _validate_g1_audit(receipt["g1"])
    semantic_hash, semantic_ids = _validate_semantic_audit(receipt["semantic"])
    polarity_hash, polarity_ids = _validate_polarity_audit(receipt["polarity"])
    if set(token_ids) & (set(semantic_ids) | set(polarity_ids)):
        raise AnalysisContractError("G1 panel overlaps a semantic or polarity endpoint ID")
    payload = dict(receipt)
    observed_hash = _hex64(payload.pop("receipt_sha256"), "tokenizer receipt hash")
    if observed_hash != protocol.canonical_sha256(payload):
        raise AnalysisContractError("tokenizer audit receipt hash does not reconstruct")
    return {
        "plan_manifest_sha256": plan_hash,
        "tokenizer_inventory_sha256": inventory_hash,
        "token_ids": token_ids,
        "tokenizer_audit_receipt_sha256": observed_hash,
        "g1_panel_sha256": receipt["g1"]["token_panel_canonical_sha256"],
        "semantic_context_binding_sha256": semantic_hash,
        "polarity_context_binding_sha256": polarity_hash,
    }


def _validated_g1_token_panel(binding: Mapping[str, Any] | None) -> tuple[int, ...]:
    return tuple(validate_tokenizer_audit_receipt(binding)["token_ids"])


def analyze_g1(
    rows: Iterable[Mapping[str, Any]],
    *,
    tokenizer_audit_receipt: Mapping[str, Any] | None = None,
    lineage_binding: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Apply the exact per-map arithmetic gate over 34 maps × 4 fixtures."""

    fixture_ids = tuple(item["fixture_id"] for item in protocol.G1_SYNTHETIC_FIXTURES)
    expected = {
        (layer, fixture_id)
        for layer in protocol.G1_MAP_LAYERS
        for fixture_id in fixture_ids
    }
    prepared = unwrap_measurement_rows(
        rows,
        measurement_fields=G1_FIELDS,
        lineage_binding=lineage_binding,
        label="G1",
        measurement_kind="g1",
        task_key=lambda row: (row["layer"], row["synthetic_residual_id"]),
        phase="G1",
        filename="g1_rows.jsonl",
    )
    indexed = _exact_index(
        prepared,
        fields=G1_FIELDS,
        key=lambda row: (row.get("layer"), row.get("synthetic_residual_id")),
        expected=expected,
        label="G1",
    )
    failures: list[str] = []
    worst_rmse = 0.0
    minimum_sign = 1.0
    expected_tokens = _validated_g1_token_panel(tokenizer_audit_receipt)
    if (
        lineage_binding is not None
        and tokenizer_audit_receipt is not None
        and tokenizer_audit_receipt.get("plan_manifest_sha256")
        != lineage_binding.get("plan_manifest_sha256")
    ):
        raise AnalysisContractError("G1 token panel belongs to another machine plan")
    for identity in sorted(indexed, key=repr):
        row = indexed[identity]
        if tuple(row["vocab_ids"]) != expected_tokens:
            raise AnalysisContractError(f"G1 selected-token inventory differs: {identity}")
        for field in (
            "map_shape_valid",
            "map_finite",
            "production_finite",
            "reference_finite",
            "wrong_orientation_differs",
        ):
            if not _boolean(row[field], f"G1 {identity} {field}"):
                failures.append(f"{identity}:{field}")
        rmse = _nonnegative(row["relative_rmse"], f"G1 {identity} relative_rmse")
        sign = _unit_interval(
            row["selected_logit_sign_agreement"], f"G1 {identity} sign agreement"
        )
        worst_rmse = max(worst_rmse, rmse)
        minimum_sign = min(minimum_sign, sign)
        if not rmse < protocol.G1_RELATIVE_RMSE_MAX:
            failures.append(f"{identity}:relative_rmse")
        if not sign >= protocol.G1_SIGN_AGREEMENT_MIN:
            failures.append(f"{identity}:sign_agreement")
    return {
        "gate": "G1",
        "status": "pass" if not failures else "fail",
        "map_count": len(protocol.G1_MAP_LAYERS),
        "row_count": len(indexed),
        "worst_relative_rmse": worst_rmse,
        "minimum_sign_agreement": minimum_sign,
        "wrong_orientation_required": True,
        "failure_count": len(failures),
        "failures": failures,
    }


def _transport_names() -> tuple[str, ...]:
    return (
        "real_j",
        "identity",
        *(f"random_j_{index}" for index in range(protocol.G2_RANDOM_CONTROL_COUNT)),
    )


def _g2_prompt_ids() -> tuple[str, ...]:
    return tuple(
        row["prompt_id"] for row in protocol.neutral_prompts()[: protocol.G2_PROMPT_COUNT]
    )


def _g2_prompt_depth_statistic(
    indexed: Mapping[tuple[Any, ...], Mapping[str, Any]],
    *,
    prompt_id: str,
    transport: str,
    metric: str,
    layers: Sequence[int],
) -> float:
    per_layer: dict[int, float] = {}
    for layer in layers:
        per_layer[layer] = sum(
            _finite(
                indexed[(prompt_id, layer, direction, transport)][metric],
                f"G2 {prompt_id}/{layer}/{direction}/{transport}/{metric}",
            )
            for direction in protocol.G2_DIRECTIONS
        ) / len(protocol.G2_DIRECTIONS)
    return normalized_trapezoid(per_layer, tuple(layers))


def analyze_g2(
    transport_rows: Iterable[Mapping[str, Any]],
    linearity_rows: Iterable[Mapping[str, Any]],
    *,
    lineage_binding: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Analyze bandwise transport, random controls, linearity, and G2b."""

    prompt_ids = _g2_prompt_ids()
    transports = _transport_names()
    expected_transport = {
        (prompt_id, layer, direction, transport)
        for prompt_id in prompt_ids
        for layer in protocol.J_MAP_LAYERS
        for direction in protocol.G2_DIRECTIONS
        for transport in transports
    }
    prepared_transport = unwrap_measurement_rows(
        transport_rows,
        measurement_fields=G2_TRANSPORT_FIELDS,
        lineage_binding=lineage_binding,
        label="G2 transport",
        measurement_kind="g2_transport",
        task_key=lambda row: (
            row["prompt_id"],
            row["layer"],
            row["direction"],
            row["transport"],
        ),
        phase="G2",
        filename="g2_transport_rows.jsonl",
    )
    indexed = _exact_index(
        prepared_transport,
        fields=G2_TRANSPORT_FIELDS,
        key=lambda row: (
            row.get("prompt_id"),
            row.get("layer"),
            row.get("direction"),
            row.get("transport"),
        ),
        expected=expected_transport,
        label="G2 transport",
    )
    for identity, row in indexed.items():
        if not _boolean(row["signed_pair_complete"], f"G2 {identity} signed pair"):
            raise AnalysisContractError(f"G2 signed perturbation pair is incomplete: {identity}")
        if not _boolean(row["finite"], f"G2 {identity} finite"):
            raise AnalysisContractError(f"G2 transport is non-finite: {identity}")
        _signed_unit_interval(row["residual_delta_cosine"], f"G2 {identity} cosine")
        _signed_unit_interval(
            row["fixed_token_logit_delta_pearson"], f"G2 {identity} Pearson"
        )

    expected_linearity = {
        (prompt_id, layer, 0)
        for prompt_id in prompt_ids[:8]
        for layer in protocol.G2_LINEARITY_LAYERS
    }
    prepared_linearity = unwrap_measurement_rows(
        linearity_rows,
        measurement_fields=G2_LINEARITY_FIELDS,
        lineage_binding=lineage_binding,
        label="G2 linearity",
        measurement_kind="g2_linearity",
        task_key=lambda row: (row["prompt_id"], row["layer"], row["direction"]),
        phase="G2",
        filename="g2_linearity_rows.jsonl",
    )
    linearity = _exact_index(
        prepared_linearity,
        fields=G2_LINEARITY_FIELDS,
        key=lambda row: (row.get("prompt_id"), row.get("layer"), row.get("direction")),
        expected=expected_linearity,
        label="G2 linearity",
    )
    linearity_failures: list[str] = []
    for identity, row in sorted(linearity.items(), key=lambda item: repr(item[0])):
        if not _boolean(row["finite"], f"G2 linearity {identity} finite"):
            raise AnalysisContractError(f"G2 linearity is non-finite: {identity}")
        cosine = _signed_unit_interval(
            row["central_difference_cosine"], f"G2 linearity {identity} cosine"
        )
        discrepancy = _nonnegative(
            row["slope_discrepancy"], f"G2 linearity {identity} discrepancy"
        )
        if not cosine > protocol.G2_LINEARITY_COSINE_MIN:
            linearity_failures.append(f"{identity}:cosine")
        if not discrepancy < protocol.G2_SLOPE_DISCREPANCY_MAX:
            linearity_failures.append(f"{identity}:slope_discrepancy")

    metrics = (
        ("residual", "residual_delta_cosine", protocol.G2_BAND_RESIDUAL_LCB_MIN),
        ("logit", "fixed_token_logit_delta_pearson", protocol.G2_BAND_LOGIT_LCB_MIN),
    )
    band_results: dict[str, Any] = {}
    band_pass = True
    for start, end in protocol.G2_BANDS:
        layers = tuple(range(start, end + 1))
        series: dict[str, dict[str, float]] = {}
        for prompt_id in prompt_ids:
            values: dict[str, float] = {}
            for transport in transports:
                for metric_name, field, _threshold in metrics:
                    values[f"{transport}:{metric_name}"] = _g2_prompt_depth_statistic(
                        indexed,
                        prompt_id=prompt_id,
                        transport=transport,
                        metric=field,
                        layers=layers,
                    )
            series[prompt_id] = values
        this_band: dict[str, Any] = {}
        for metric_name, _field, threshold in metrics:
            real = clustered_bootstrap_lcb(
                series, lambda means, name=metric_name: means[f"real_j:{name}"]
            )
            advantage = clustered_bootstrap_lcb(
                series,
                lambda means, name=metric_name: means[f"real_j:{name}"]
                - max(
                    means[f"random_j_{index}:{name}"]
                    for index in range(protocol.G2_RANDOM_CONTROL_COUNT)
                ),
            )
            passed = (
                real["lcb_95"] > threshold
                and advantage["lcb_95"] > protocol.G2_RANDOM_ADVANTAGE_LCB_MIN
            )
            this_band[metric_name] = {
                "real_j": real,
                "real_j_minus_best_random": advantage,
                "threshold": threshold,
                "random_advantage_threshold": protocol.G2_RANDOM_ADVANTAGE_LCB_MIN,
                "pass": passed,
            }
            band_pass = band_pass and passed
        band_results[f"{start}:{end}"] = this_band

    identity_layers = tuple(protocol.G2_IDENTITY_LAYERS)
    identity_series: dict[str, dict[str, float]] = {}
    for prompt_id in prompt_ids:
        values = {}
        for transport in ("real_j", "identity"):
            for metric_name, field, _threshold in metrics:
                values[f"{transport}:{metric_name}"] = _g2_prompt_depth_statistic(
                    indexed,
                    prompt_id=prompt_id,
                    transport=transport,
                    metric=field,
                    layers=identity_layers,
                )
        identity_series[prompt_id] = values
    identity_results: dict[str, Any] = {}
    identity_pass = True
    for metric_name, _field, _threshold in metrics:
        result = clustered_bootstrap_lcb(
            identity_series,
            lambda means, name=metric_name: means[f"real_j:{name}"]
            - means[f"identity:{name}"],
        )
        passed = result["lcb_95"] > protocol.G2_IDENTITY_ADVANTAGE_LCB_MIN
        identity_results[metric_name] = {
            **result,
            "threshold": protocol.G2_IDENTITY_ADVANTAGE_LCB_MIN,
            "pass": passed,
        }
        identity_pass = identity_pass and passed

    transport_pass = band_pass and not linearity_failures and identity_pass
    return {
        "gate": "G2",
        "status": "pass" if transport_pass else "fail",
        "transport_row_count": len(indexed),
        "linearity_row_count": len(linearity),
        "bands": band_results,
        "linearity": {
            "pass": not linearity_failures,
            "failure_count": len(linearity_failures),
            "failures": linearity_failures,
        },
        "G2b_identity_incremental": {
            "status": "pass" if identity_pass else "fail",
            "claim_allowed": identity_pass,
            "metrics": identity_results,
        },
    }


def _logmeanexp(values: Sequence[float]) -> float:
    if not values:
        raise AnalysisContractError("logmeanexp requires at least one value")
    maximum = max(values)
    return maximum + math.log(
        sum(math.exp(value - maximum) for value in values) / len(values)
    )


def semantic_family_scores(
    token_logits: Mapping[str, Any], *, omit_explicit_token: str | None = None
) -> dict[str, float]:
    """Reconstruct all nine frozen logmeanexp-minus-other-family scores."""

    token_groups = {
        family: tuple(tokens) for family, tokens in protocol.G3_TOKEN_GROUPS.items()
    }
    expected_tokens = {
        token for tokens in token_groups.values() for token in tokens
    }
    if not isinstance(token_logits, Mapping) or set(token_logits) != expected_tokens:
        raise AnalysisContractError("G3 token-logit inventory differs")
    values = {
        token: _finite(token_logits[token], f"G3 token logit {token}")
        for token in expected_tokens
    }
    if omit_explicit_token is not None and omit_explicit_token not in protocol.G3_EXPLICIT_TOKENS:
        raise AnalysisContractError("G3 leave-one-out token is not frozen")
    active_groups: dict[str, tuple[str, ...]] = {}
    for family, tokens in token_groups.items():
        active = tuple(token for token in tokens if token != omit_explicit_token)
        if not active:
            raise AnalysisContractError("G3 leave-one-out emptied a token family")
        active_groups[family] = active
    scores: dict[str, float] = {}
    for family in protocol.G3_FAMILIES:
        own = [values[token] for token in active_groups[family]]
        other = [
            values[token]
            for other_family in protocol.G3_FAMILIES
            if other_family != family
            for token in active_groups[other_family]
        ]
        scores[family] = _logmeanexp(own) - _logmeanexp(other)
    return scores


def binary_auroc(labels: Sequence[bool], scores: Sequence[Any]) -> float:
    """Exact Mann-Whitney AUROC with half credit for ties."""

    if len(labels) != len(scores) or not labels:
        raise AnalysisContractError("AUROC labels/scores differ or are empty")
    pairs = sorted(
        (_finite(score, "AUROC score"), bool(label))
        for label, score in zip(labels, scores)
    )
    positive_count = sum(label for _score, label in pairs)
    negative_count = len(pairs) - positive_count
    if not positive_count or not negative_count:
        raise AnalysisContractError("AUROC requires positive and negative examples")
    wins = 0.0
    negatives_before = 0
    index = 0
    while index < len(pairs):
        end = index + 1
        while end < len(pairs) and pairs[end][0] == pairs[index][0]:
            end += 1
        tied = pairs[index:end]
        tied_positives = sum(label for _score, label in tied)
        tied_negatives = len(tied) - tied_positives
        wins += tied_positives * (negatives_before + 0.5 * tied_negatives)
        negatives_before += tied_negatives
        index = end
    return wins / (positive_count * negative_count)


def semantic_metrics(
    entries: Sequence[Mapping[str, Any]],
    *,
    labels_override: Sequence[str] | None = None,
) -> dict[str, float]:
    if not entries:
        raise AnalysisContractError("semantic metric input is empty")
    labels = (
        list(labels_override)
        if labels_override is not None
        else [str(entry["true_family"]) for entry in entries]
    )
    if len(labels) != len(entries) or any(label not in protocol.G3_FAMILIES for label in labels):
        raise AnalysisContractError("semantic metric labels differ")
    score_rows = [entry["scores"] for entry in entries]
    macro = sum(
        binary_auroc(
            [label == family for label in labels],
            [row[family] for row in score_rows],
        )
        for family in protocol.G3_FAMILIES
    ) / len(protocol.G3_FAMILIES)
    top_correct = 0
    for label, row in zip(labels, score_rows):
        true_score = _finite(row[label], "true-family score")
        if all(
            true_score > _finite(row[other], "other-family score")
            for other in protocol.G3_FAMILIES
            if other != label
        ):
            top_correct += 1
    relevant = [
        index
        for index, label in enumerate(labels)
        if label == "explicit_consciousness" or label in protocol.G3_ADJACENT_FAMILIES
    ]
    explicit_adjacent = binary_auroc(
        [labels[index] == "explicit_consciousness" for index in relevant],
        [score_rows[index]["explicit_consciousness"] for index in relevant],
    )
    return {
        "macro_auroc": macro,
        "top_family_accuracy": top_correct / len(entries),
        "explicit_vs_adjacent_auroc": explicit_adjacent,
    }


def _g3_transports() -> tuple[str, ...]:
    return (
        "real_j",
        "identity",
        *(f"random_j_{index}" for index in range(protocol.G3_RANDOM_CONTROL_COUNT)),
    )


def _validate_g3_rows(
    rows: Iterable[Mapping[str, Any]],
    *,
    lineage_binding: Mapping[str, Any] | None = None,
) -> tuple[
    dict[tuple[Any, ...], Mapping[str, Any]],
    tuple[str, ...],
    dict[str, Mapping[str, Any]],
]:
    fixtures = {row["fixture_id"]: row for row in protocol.g3_fixture_rows()}
    prompt_ids = tuple(sorted(fixtures))
    expected = {(prompt_id, "actual_final", "final") for prompt_id in prompt_ids}
    expected |= {
        (prompt_id, transport, layer)
        for prompt_id in prompt_ids
        for transport in _g3_transports()
        for layer in protocol.J_MAP_LAYERS
    }
    prepared = unwrap_measurement_rows(
        rows,
        measurement_fields=G3_FIELDS,
        lineage_binding=lineage_binding,
        label="G3",
        measurement_kind="g3",
        task_key=lambda row: (row["prompt_id"], row["transport"], row["layer"]),
        phase="G3",
        filename="g3_rows.jsonl",
    )
    indexed = _exact_index(
        prepared,
        fields=G3_FIELDS,
        key=lambda row: (row.get("prompt_id"), row.get("transport"), row.get("layer")),
        expected=expected,
        label="G3",
    )
    expected_tokens = {
        token for tokens in protocol.G3_TOKEN_GROUPS.values() for token in tokens
    }
    for identity, row in indexed.items():
        fixture = fixtures[str(row["prompt_id"])]
        if (
            row["true_family"] != fixture["family"]
            or row["item_index"] != fixture["cloze_index"]
            or row["render_mode"] != fixture["render_mode"]
        ):
            raise AnalysisContractError(f"G3 fixture identity differs: {identity}")
        if not _boolean(row["finite"], f"G3 {identity} finite"):
            raise AnalysisContractError(f"G3 row is non-finite: {identity}")
        logits = row["token_logits"]
        if not isinstance(logits, Mapping) or set(logits) != expected_tokens:
            raise AnalysisContractError(f"G3 token grid differs: {identity}")
        for token in expected_tokens:
            _finite(logits[token], f"G3 {identity}/{token}")
    return indexed, prompt_ids, fixtures


def _g3_entries(
    indexed: Mapping[tuple[Any, ...], Mapping[str, Any]],
    prompt_ids: Sequence[str],
    *,
    transport: str,
    layer: int | str,
    omit_explicit_token: str | None = None,
) -> list[dict[str, Any]]:
    return [
        {
            "prompt_id": prompt_id,
            "true_family": indexed[(prompt_id, transport, layer)]["true_family"],
            "render_mode": indexed[(prompt_id, transport, layer)]["render_mode"],
            "scores": semantic_family_scores(
                indexed[(prompt_id, transport, layer)]["token_logits"],
                omit_explicit_token=omit_explicit_token,
            ),
        }
        for prompt_id in prompt_ids
    ]


def _g3_depth_metric(
    indexed: Mapping[tuple[Any, ...], Mapping[str, Any]],
    prompt_ids: Sequence[str],
    *,
    transport: str,
    metric: str,
    omit_explicit_token: str | None = None,
    render_mode: str | None = None,
) -> float:
    values: dict[int, float] = {}
    for layer in protocol.G3_DOWNSTREAM_LAYERS:
        entries = _g3_entries(
            indexed,
            prompt_ids,
            transport=transport,
            layer=layer,
            omit_explicit_token=omit_explicit_token,
        )
        if render_mode is not None:
            entries = [entry for entry in entries if entry["render_mode"] == render_mode]
        values[layer] = semantic_metrics(entries)[metric]
    return normalized_trapezoid(values, protocol.G3_DOWNSTREAM_LAYERS)


def _numpy() -> Any:
    try:
        import numpy
    except ImportError as exc:  # pragma: no cover - frozen pilot environment only
        raise AnalysisContractError("direct G3 bootstrap requires NumPy") from exc
    return numpy


def _g3_bootstrap_counts(
    prompt_ids: Sequence[str],
    strata: Mapping[str, str],
    *,
    replicates: int,
    seed: int,
) -> Any:
    """Materialize the one reusable direct family-stratified count matrix."""

    if isinstance(replicates, bool) or not isinstance(replicates, int) or replicates <= 0:
        raise AnalysisContractError("G3 bootstrap replicate count must be positive")
    ordered = tuple(prompt_ids)
    if len(ordered) != len(set(ordered)) or set(strata) != set(ordered):
        raise AnalysisContractError("G3 bootstrap prompt/stratum inventory differs")
    index_by_prompt = {prompt_id: index for index, prompt_id in enumerate(ordered)}
    members_by_family: list[tuple[int, ...]] = []
    for family in protocol.G3_FAMILIES:
        members = tuple(
            index_by_prompt[prompt_id]
            for prompt_id in ordered
            if strata[prompt_id] == family
        )
        if len(members) != protocol.G3_CLOZES_PER_FAMILY:
            raise AnalysisContractError("G3 bootstrap family cluster count differs")
        members_by_family.append(members)
    numpy = _numpy()
    counts = numpy.zeros((replicates, len(ordered)), dtype=numpy.uint8)
    generator = _SplitMix64(seed)
    for draw in range(replicates):
        for members in members_by_family:
            for _ in members:
                counts[draw, members[generator.randbelow(len(members))]] += 1
    return counts


def _g3_score_matrix(entries: Sequence[Mapping[str, Any]]) -> Any:
    numpy = _numpy()
    matrix = numpy.asarray(
        [
            [
                _finite(entry["scores"][family], f"G3 score {family}")
                for family in protocol.G3_FAMILIES
            ]
            for entry in entries
        ],
        dtype=numpy.float64,
    )
    if matrix.shape != (len(entries), len(protocol.G3_FAMILIES)):
        raise AnalysisContractError("G3 score matrix shape differs")
    return matrix


def _g3_metric_draws(
    counts: Any,
    scores: Any,
    true_family_indices: Any,
    *,
    metrics: Sequence[str],
) -> dict[str, Any]:
    """Evaluate the nonlinear semantic metrics on every direct bootstrap draw."""

    numpy = _numpy()
    requested = set(metrics)
    allowed = {
        "macro_auroc",
        "top_family_accuracy",
        "explicit_vs_adjacent_auroc",
    }
    if requested - allowed:
        raise AnalysisContractError("G3 direct bootstrap metric differs")
    if counts.ndim != 2 or scores.shape != (counts.shape[1], len(protocol.G3_FAMILIES)):
        raise AnalysisContractError("G3 direct bootstrap array shape differs")
    results: dict[str, Any] = {}
    if "top_family_accuracy" in requested:
        own = scores[numpy.arange(scores.shape[0]), true_family_indices]
        masked = scores.copy()
        masked[numpy.arange(scores.shape[0]), true_family_indices] = -numpy.inf
        correct = (own > masked.max(axis=1)).astype(numpy.float64)
        results["top_family_accuracy"] = counts @ correct / counts.sum(axis=1)

    def weighted_auc(positive: Any, negative: Any, column: int) -> Any:
        positive_mask = numpy.zeros(scores.shape[0], dtype=numpy.bool_)
        negative_mask = numpy.zeros(scores.shape[0], dtype=numpy.bool_)
        positive_mask[positive] = True
        negative_mask[negative] = True
        order = numpy.argsort(scores[:, column], kind="stable")
        sorted_scores = scores[order, column]
        sorted_counts = counts[:, order]
        sorted_negative = negative_mask[order]
        cumulative_negative = numpy.cumsum(
            sorted_counts * sorted_negative[None, :], axis=1, dtype=numpy.int16
        )
        wins = numpy.zeros(counts.shape[0], dtype=numpy.float64)
        for position in numpy.flatnonzero(positive_mask[order]):
            score = sorted_scores[position]
            tie_left = int(numpy.searchsorted(sorted_scores, score, side="left"))
            tie_right = int(numpy.searchsorted(sorted_scores, score, side="right"))
            negative_before = (
                cumulative_negative[:, tie_left - 1]
                if tie_left > 0
                else 0
            )
            negative_through_tie = cumulative_negative[:, tie_right - 1]
            negative_before_tie = (
                cumulative_negative[:, tie_left - 1]
                if tie_left > 0
                else 0
            )
            tied_negative = negative_through_tie - negative_before_tie
            wins += sorted_counts[:, position] * (
                negative_before + 0.5 * tied_negative
            )
        positive_counts = counts[:, positive]
        negative_counts = counts[:, negative]
        denominator = positive_counts.sum(axis=1) * negative_counts.sum(axis=1)
        if numpy.any(denominator <= 0):  # pragma: no cover - stratification guarantees this
            raise AnalysisContractError("G3 bootstrap AUROC class is empty")
        return wins / denominator

    if "macro_auroc" in requested:
        macro = numpy.zeros(counts.shape[0], dtype=numpy.float64)
        for family_index in range(len(protocol.G3_FAMILIES)):
            positive = numpy.flatnonzero(true_family_indices == family_index)
            negative = numpy.flatnonzero(true_family_indices != family_index)
            macro += weighted_auc(positive, negative, family_index)
        results["macro_auroc"] = macro / len(protocol.G3_FAMILIES)
    if "explicit_vs_adjacent_auroc" in requested:
        explicit_index = protocol.G3_FAMILIES.index("explicit_consciousness")
        adjacent_indices = {
            protocol.G3_FAMILIES.index(family)
            for family in protocol.G3_ADJACENT_FAMILIES
        }
        positive = numpy.flatnonzero(true_family_indices == explicit_index)
        negative = numpy.flatnonzero(
            numpy.isin(true_family_indices, tuple(sorted(adjacent_indices)))
        )
        results["explicit_vs_adjacent_auroc"] = weighted_auc(
            positive, negative, explicit_index
        )
    return results


def _g3_depth_weights() -> dict[int, float]:
    layers = tuple(protocol.G3_DOWNSTREAM_LAYERS)
    width = layers[-1] - layers[0]
    weights = {layer: 0.0 for layer in layers}
    for left, right in zip(layers, layers[1:]):
        contribution = (right - left) / (2.0 * width)
        weights[left] += contribution
        weights[right] += contribution
    return weights


def _direct_bootstrap_summary(draws: Any, estimate: float) -> dict[str, Any]:
    numpy = _numpy()
    values = numpy.sort(numpy.asarray(draws, dtype=numpy.float64))
    if values.ndim != 1 or values.size != protocol.BOOTSTRAP_REPLICATES:
        raise AnalysisContractError("G3 direct-bootstrap draw inventory differs")
    if numpy.any(values < -1.0) or numpy.any(values > 1.0):
        raise AnalysisContractError("G3 direct-bootstrap statistic is outside [-1,1]")
    probability = 0.05
    position = (values.size - 1) * probability
    lower = math.floor(position)
    upper = math.ceil(position)
    lcb = float(values[lower])
    if lower != upper:
        fraction = position - lower
        lcb = float(values[lower] * (1.0 - fraction) + values[upper] * fraction)
    return {
        "estimate": _signed_unit_interval(estimate, "G3 bootstrap estimate"),
        "lcb_95": _signed_unit_interval(lcb, "G3 direct-bootstrap lower bound"),
        "alpha": probability,
        "clusters": len(protocol.G3_FAMILIES) * protocol.G3_CLOZES_PER_FAMILY,
        "replicates": protocol.BOOTSTRAP_REPLICATES,
        "seed": protocol.BOOTSTRAP_SEED,
        "algorithm": "splitmix64_direct_family_stratified_prompt_cluster_v1",
    }


def _best_of_random_draw_advantage(real_draws: Any, random_draws: Sequence[Any]) -> Any:
    """Subtract the best random control separately inside each bootstrap draw."""

    numpy = _numpy()
    if len(random_draws) != protocol.G3_RANDOM_CONTROL_COUNT:
        raise AnalysisContractError("G3 random-control draw inventory differs")
    real = numpy.asarray(real_draws, dtype=numpy.float64)
    controls = [numpy.asarray(draws, dtype=numpy.float64) for draws in random_draws]
    if real.ndim != 1 or any(control.shape != real.shape for control in controls):
        raise AnalysisContractError("G3 random-control draw shapes differ")
    return real - numpy.maximum.reduce(controls)


def analyze_g3(
    rows: Iterable[Mapping[str, Any]],
    *,
    lineage_binding: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Analyze nine-family sensitivity by direct prompt-cluster bootstrap.

    One frozen family-stratified count matrix is reused for every condition.
    Nonlinear accuracy and AUROC statistics are recomputed on every draw, and
    the strongest of the five random-J controls is selected inside that draw.
    """

    indexed, prompt_ids, fixtures = _validate_g3_rows(
        rows, lineage_binding=lineage_binding
    )
    strata = {prompt_id: str(fixtures[prompt_id]["family"]) for prompt_id in prompt_ids}
    metric_names = (
        "macro_auroc",
        "top_family_accuracy",
        "explicit_vs_adjacent_auroc",
    )
    actual_thresholds = {
        "macro_auroc": protocol.G3_ACTUAL_MACRO_LCB_MIN,
        "top_family_accuracy": protocol.G3_ACTUAL_ACCURACY_LCB_MIN,
        "explicit_vs_adjacent_auroc": protocol.G3_ACTUAL_EXPLICIT_ADJACENT_LCB_MIN,
    }
    j_thresholds = {
        "macro_auroc": protocol.G3_J_MACRO_LCB_MIN,
        "top_family_accuracy": protocol.G3_J_ACCURACY_LCB_MIN,
        "explicit_vs_adjacent_auroc": protocol.G3_J_EXPLICIT_ADJACENT_LCB_MIN,
    }

    entry_cache: dict[
        tuple[str, int | str, str | None], dict[str, dict[str, Any]]
    ] = {}

    def entries(
        sample: Sequence[str],
        *,
        transport: str,
        layer: int | str,
        omitted: str | None = None,
    ) -> list[dict[str, Any]]:
        cache_key = (transport, layer, omitted)
        if cache_key not in entry_cache:
            built = _g3_entries(
                indexed,
                prompt_ids,
                transport=transport,
                layer=layer,
                omit_explicit_token=omitted,
            )
            entry_cache[cache_key] = {
                str(entry["prompt_id"]): entry for entry in built
            }
        return [entry_cache[cache_key][prompt_id] for prompt_id in sample]

    def depth_statistic(
        sample: Sequence[str],
        *,
        transport: str,
        metric: str,
        omitted: str | None = None,
        render_mode: str | None = None,
    ) -> float:
        depth: dict[int, float] = {}
        for layer in protocol.G3_DOWNSTREAM_LAYERS:
            layer_entries = entries(
                sample, transport=transport, layer=layer, omitted=omitted
            )
            if render_mode is not None:
                layer_entries = [
                    entry
                    for entry in layer_entries
                    if entry["render_mode"] == render_mode
                ]
            depth[layer] = semantic_metrics(layer_entries)[metric]
        return normalized_trapezoid(depth, protocol.G3_DOWNSTREAM_LAYERS)

    numpy = _numpy()
    counts = _g3_bootstrap_counts(
        prompt_ids,
        strata,
        replicates=protocol.BOOTSTRAP_REPLICATES,
        seed=protocol.BOOTSTRAP_SEED,
    )
    family_index = {family: index for index, family in enumerate(protocol.G3_FAMILIES)}
    true_family_indices = numpy.asarray(
        [family_index[str(fixtures[prompt_id]["family"])] for prompt_id in prompt_ids],
        dtype=numpy.int64,
    )

    def bootstrap_draws(
        *,
        transport: str,
        layer: int | str,
        omitted: str | None = None,
        requested_metrics: Sequence[str] = metric_names,
    ) -> dict[str, Any]:
        return _g3_metric_draws(
            counts,
            _g3_score_matrix(
                entries(
                    prompt_ids,
                    transport=transport,
                    layer=layer,
                    omitted=omitted,
                )
            ),
            true_family_indices,
            metrics=requested_metrics,
        )

    actual_point = semantic_metrics(
        entries(prompt_ids, transport="actual_final", layer="final")
    )
    actual_draws = bootstrap_draws(transport="actual_final", layer="final")
    depth_weights = _g3_depth_weights()
    random_transports = tuple(
        f"random_j_{index}" for index in range(protocol.G3_RANDOM_CONTROL_COUNT)
    )
    depth_draws: dict[str, dict[str, Any]] = {}
    depth_points: dict[str, dict[str, float]] = {}
    for transport in ("real_j", *random_transports):
        transport_draws = {
            metric: numpy.zeros(protocol.BOOTSTRAP_REPLICATES, dtype=numpy.float64)
            for metric in metric_names
        }
        transport_points = {metric: 0.0 for metric in metric_names}
        for layer in protocol.G3_DOWNSTREAM_LAYERS:
            layer_draws = bootstrap_draws(transport=transport, layer=layer)
            layer_points = semantic_metrics(
                entries(prompt_ids, transport=transport, layer=layer)
            )
            weight = depth_weights[layer]
            for metric in metric_names:
                transport_draws[metric] += weight * layer_draws[metric]
                transport_points[metric] += weight * layer_points[metric]
        depth_draws[transport] = transport_draws
        depth_points[transport] = transport_points

    actual_results: dict[str, Any] = {}
    j_results: dict[str, Any] = {}
    random_results: dict[str, Any] = {}
    primary_pass = True
    for metric in metric_names:
        actual = _direct_bootstrap_summary(actual_draws[metric], actual_point[metric])
        j_depth = _direct_bootstrap_summary(
            depth_draws["real_j"][metric], depth_points["real_j"][metric]
        )
        random_point = max(
            depth_points[transport][metric] for transport in random_transports
        )
        random_advantage = _direct_bootstrap_summary(
            _best_of_random_draw_advantage(
                depth_draws["real_j"][metric],
                [depth_draws[transport][metric] for transport in random_transports],
            ),
            depth_points["real_j"][metric] - random_point,
        )
        actual_pass = actual["lcb_95"] > actual_thresholds[metric]
        j_pass = j_depth["lcb_95"] > j_thresholds[metric]
        random_pass = random_advantage["lcb_95"] > protocol.G3_RANDOM_ADVANTAGE_LCB_MIN
        actual_results[metric] = {
            **actual,
            "threshold": actual_thresholds[metric],
            "pass": actual_pass,
        }
        j_results[metric] = {
            **j_depth,
            "threshold": j_thresholds[metric],
            "pass": j_pass,
        }
        random_results[metric] = {
            **random_advantage,
            "threshold": protocol.G3_RANDOM_ADVANTAGE_LCB_MIN,
            "best_of_five_computed_inside_each_draw": True,
            "pass": random_pass,
        }
        primary_pass = primary_pass and actual_pass and j_pass and random_pass

    loo_results: dict[str, Any] = {}
    loo_pass = True
    for token in protocol.G3_EXPLICIT_TOKENS:
        requested = ("explicit_vs_adjacent_auroc",)
        actual_loo_point = semantic_metrics(
            entries(
                prompt_ids,
                transport="actual_final",
                layer="final",
                omitted=token,
            )
        )["explicit_vs_adjacent_auroc"]
        actual_loo_draws = bootstrap_draws(
            transport="actual_final",
            layer="final",
            omitted=token,
            requested_metrics=requested,
        )["explicit_vs_adjacent_auroc"]
        j_loo_point = 0.0
        j_loo_draws = numpy.zeros(
            protocol.BOOTSTRAP_REPLICATES, dtype=numpy.float64
        )
        for layer in protocol.G3_DOWNSTREAM_LAYERS:
            weight = depth_weights[layer]
            j_loo_point += weight * semantic_metrics(
                entries(
                    prompt_ids,
                    transport="real_j",
                    layer=layer,
                    omitted=token,
                )
            )["explicit_vs_adjacent_auroc"]
            j_loo_draws += weight * bootstrap_draws(
                transport="real_j",
                layer=layer,
                omitted=token,
                requested_metrics=requested,
            )["explicit_vs_adjacent_auroc"]
        actual = _direct_bootstrap_summary(actual_loo_draws, actual_loo_point)
        j_depth = _direct_bootstrap_summary(j_loo_draws, j_loo_point)
        passed = (
            actual["lcb_95"] > protocol.G3_LOO_ACTUAL_LCB_MIN
            and j_depth["lcb_95"] > protocol.G3_LOO_J_LCB_MIN
        )
        loo_results[token] = {
            "actual_final": actual,
            "real_j_depth_auc": j_depth,
            "actual_threshold": protocol.G3_LOO_ACTUAL_LCB_MIN,
            "j_threshold": protocol.G3_LOO_J_LCB_MIN,
            "pass": passed,
        }
        loo_pass = loo_pass and passed

    render_results: dict[str, Any] = {}
    render_pass = True
    for render_mode in protocol.G3_RENDER_MODES:
        mode_prompt_ids = tuple(
            prompt_id
            for prompt_id in prompt_ids
            if fixtures[prompt_id]["render_mode"] == render_mode
        )
        actual = semantic_metrics(
            entries(mode_prompt_ids, transport="actual_final", layer="final")
        )["explicit_vs_adjacent_auroc"]
        j_depth = depth_statistic(
            mode_prompt_ids,
            transport="real_j",
            metric="explicit_vs_adjacent_auroc",
        )
        passed = (
            actual >= protocol.G3_RENDER_MODE_AUC_MIN
            and j_depth >= protocol.G3_RENDER_MODE_AUC_MIN
        )
        render_results[render_mode] = {
            "actual_final": actual,
            "real_j_depth_auc": j_depth,
            "threshold": protocol.G3_RENDER_MODE_AUC_MIN,
            "pass": passed,
        }
        render_pass = render_pass and passed

    labels = [str(fixtures[prompt_id]["family"]) for prompt_id in prompt_ids]
    modes = [str(fixtures[prompt_id]["render_mode"]) for prompt_id in prompt_ids]
    actual_entries = entries(prompt_ids, transport="actual_final", layer="final")
    real_depth_values = [
        {
            layer: entries((prompt_id,), transport="real_j", layer=layer)[0]
            for layer in protocol.G3_DOWNSTREAM_LAYERS
        }
        for prompt_id in prompt_ids
    ]
    permutation = {
        "actual_macro_auroc": deterministic_permutation_p_value(
            labels,
            actual_entries,
            lambda permuted, values: semantic_metrics(
                values, labels_override=permuted
            )["macro_auroc"],
            strata=modes,
        ),
        "real_j_depth_macro_auroc": deterministic_permutation_p_value(
            labels,
            real_depth_values,
            lambda permuted, depth_rows: normalized_trapezoid(
                {
                    layer: semantic_metrics(
                        [row[layer] for row in depth_rows],
                        labels_override=permuted,
                    )["macro_auroc"]
                    for layer in protocol.G3_DOWNSTREAM_LAYERS
                },
                protocol.G3_DOWNSTREAM_LAYERS,
            ),
            strata=modes,
        ),
    }

    identity_report = {
        metric: depth_statistic(
            prompt_ids, transport="identity", metric=metric
        )
        for metric in metric_names
    }
    passed = primary_pass and loo_pass and render_pass
    return {
        "gate": "G3",
        "status": "pass" if passed else "fail",
        "row_count": len(indexed),
        "prompt_count": len(prompt_ids),
        "bootstrap_method": "direct_family_stratified_prompt_cluster_v1",
        "bootstrap_count_matrix_reused": True,
        "actual_final": actual_results,
        "real_j_depth_auc": j_results,
        "real_j_minus_best_random": random_results,
        "leave_one_explicit_token_out": loo_results,
        "render_mode_guards": render_results,
        "identity_report_only": identity_report,
        "family_label_permutation": permutation,
        "claim_boundary": (
            "distinguishes_frozen_clean_explicit_consciousness_contexts_only"
        ),
    }


def _g3p_transports() -> tuple[str, ...]:
    return (
        "real_j",
        *(f"random_j_{index}" for index in range(protocol.G3_RANDOM_CONTROL_COUNT)),
    )


def analyze_g3p(
    rows: Iterable[Mapping[str, Any]],
    *,
    lineage_binding: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Analyze the frozen 24-question factual Yes/No polarity battery."""

    plan = {row["prompt_id"]: row for row in protocol.g3p_plan_rows()}
    prompt_ids = tuple(sorted(plan))
    transports = _g3p_transports()
    expected = {(prompt_id, "actual_final", "final") for prompt_id in prompt_ids}
    expected |= {
        (prompt_id, transport, layer)
        for prompt_id in prompt_ids
        for transport in transports
        for layer in protocol.J_MAP_LAYERS
    }
    prepared = unwrap_measurement_rows(
        rows,
        measurement_fields=G3P_FIELDS,
        lineage_binding=lineage_binding,
        label="G3P",
        measurement_kind="g3p",
        task_key=lambda row: (row["prompt_id"], row["transport"], row["layer"]),
        phase="G3P",
        filename="g3p_rows.jsonl",
    )
    indexed = _exact_index(
        prepared,
        fields=G3P_FIELDS,
        key=lambda row: (row.get("prompt_id"), row.get("transport"), row.get("layer")),
        expected=expected,
        label="G3P",
    )
    margins: dict[tuple[str, str, int | str], float] = {}
    for identity, row in indexed.items():
        prompt_id = str(row["prompt_id"])
        if row["expected_answer"] != plan[prompt_id]["expected_label"]:
            raise AnalysisContractError(f"G3P expected answer differs: {identity}")
        if not _boolean(row["finite"], f"G3P {identity} finite"):
            raise AnalysisContractError(f"G3P row is non-finite: {identity}")
        yes = _finite(row["yes_logit"], f"G3P {identity} Yes logit")
        no = _finite(row["no_logit"], f"G3P {identity} No logit")
        margins[identity] = yes - no

    def correct(prompt_id: str, margin: float) -> bool:
        expected_answer = str(plan[prompt_id]["expected_label"])
        return margin > 0.0 if expected_answer == "Yes" else margin < 0.0

    actual_correct = sum(
        correct(prompt_id, margins[(prompt_id, "actual_final", "final")])
        for prompt_id in prompt_ids
    )
    depth_margin: dict[str, dict[str, float]] = {}
    correct_counts: dict[str, int] = {}
    for transport in transports:
        by_prompt: dict[str, float] = {}
        for prompt_id in prompt_ids:
            by_prompt[prompt_id] = normalized_trapezoid(
                {
                    layer: margins[(prompt_id, transport, layer)]
                    for layer in protocol.G3_DOWNSTREAM_LAYERS
                },
                protocol.G3_DOWNSTREAM_LAYERS,
            )
        depth_margin[transport] = by_prompt
        correct_counts[transport] = sum(
            correct(prompt_id, by_prompt[prompt_id]) for prompt_id in prompt_ids
        )
    real_correct = correct_counts["real_j"]
    random_counts = {
        transport: correct_counts[transport]
        for transport in transports
        if transport.startswith("random_j_")
    }
    actual_pass = actual_correct == protocol.G3P_ACTUAL_CORRECT_REQUIRED
    j_pass = real_correct >= protocol.G3P_J_CORRECT_REQUIRED
    random_pass = all(
        real_correct - count >= protocol.G3P_RANDOM_ADVANTAGE_QUESTIONS
        for count in random_counts.values()
    )
    passed = actual_pass and j_pass and random_pass
    return {
        "gate": "G3P",
        "status": "pass" if passed else "fail",
        "row_count": len(indexed),
        "actual_final_correct": actual_correct,
        "actual_final_required": protocol.G3P_ACTUAL_CORRECT_REQUIRED,
        "actual_final_pass": actual_pass,
        "real_j_depth_correct": real_correct,
        "real_j_depth_required": protocol.G3P_J_CORRECT_REQUIRED,
        "real_j_pass": j_pass,
        "random_j_correct": random_counts,
        "random_advantage_required_questions": (
            protocol.G3P_RANDOM_ADVANTAGE_QUESTIONS
        ),
        "random_advantage_pass": random_pass,
    }


def _g4_subset_inventory() -> tuple[tuple[int, ...], ...]:
    minimum, maximum = protocol.G4_SUBSET_SIZE_RANGE
    subsets = tuple(
        subset
        for size in range(minimum, maximum + 1)
        for subset in combinations(protocol.G4_TARGET_FEATURE_IDS, size)
    )
    if len(subsets) != protocol.G4_SUBSET_COUNT:
        raise AnalysisContractError("G4 prospective subset inventory differs")
    return subsets


def validate_g4_vector_inventory_receipt(
    receipt: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Reconstruct the complete resolved G4 mapping and BF16 vector inventory."""

    if receipt is None:
        raise AnalysisContractError("G4 requires the resolved vector-inventory receipt")
    _require_fields(
        receipt, G4_VECTOR_INVENTORY_RECEIPT_FIELDS, "G4 vector-inventory receipt"
    )
    if (
        receipt.get("schema_version") != 1
        or receipt.get("study_id") != protocol.STUDY_ID
        or receipt.get("protocol_version") != protocol.PROTOCOL_VERSION
        or receipt.get("status") != "pass"
        or receipt.get("sae_sha256") != protocol.SAE_SPEC["sha256"]
        or receipt.get("matching_spec_sha256")
        != protocol.canonical_sha256(protocol.G4_MATCHING_SPEC)
        or receipt.get("vector_arithmetic_spec_sha256")
        != protocol.canonical_sha256(protocol.G4_VECTOR_ARITHMETIC_SPEC)
    ):
        raise AnalysisContractError("G4 vector-inventory identity differs")
    plan_hash = _hex64(receipt["plan_manifest_sha256"], "G4 inventory plan manifest")
    _hex64(receipt["decoder_bfloat16_sha256"], "G4 decoder BF16 hash")
    _hex64(
        receipt["matching_candidate_inventory_sha256"],
        "G4 matching candidate-inventory hash",
    )
    target_ids = tuple(receipt["target_feature_ids"]) if isinstance(
        receipt["target_feature_ids"], list
    ) else ()
    excluded_ids = tuple(receipt["excluded_feature_ids"]) if isinstance(
        receipt["excluded_feature_ids"], list
    ) else ()
    if target_ids != protocol.G4_TARGET_FEATURE_IDS or excluded_ids != target_ids:
        raise AnalysisContractError("G4 target/exclusion inventory differs")

    mapping_rows = receipt["target_to_matched"]
    mapping_fields = frozenset(
        {"target_feature_id", "matched_feature_id", "scaled_distance"}
    )
    if not isinstance(mapping_rows, list) or len(mapping_rows) != len(target_ids):
        raise AnalysisContractError("G4 target-to-matched inventory differs")
    mapping: dict[int, int] = {}
    matched_ids: list[int] = []
    for offset, (expected_target, row) in enumerate(zip(target_ids, mapping_rows)):
        _require_fields(row, mapping_fields, f"G4 matched mapping {offset}")
        target = _integer(row["target_feature_id"], "G4 mapping target ID")
        matched = _integer(row["matched_feature_id"], "G4 mapping matched ID")
        if target != expected_target or not 0 <= matched < protocol.SAE_SPEC["feature_count"]:
            raise AnalysisContractError("G4 target-to-matched mapping order differs")
        _nonnegative(row["scaled_distance"], "G4 matched scaled distance")
        mapping[target] = matched
        matched_ids.append(matched)
    if len(set(matched_ids)) != len(matched_ids) or set(matched_ids) & set(target_ids):
        raise AnalysisContractError("G4 matched IDs are not one-to-one and target-excluded")

    assignments = protocol.g4_aggregate_assignments()
    expected_order = [
        (
            assignment["assignment_id"],
            tuple(assignment["target_feature_ids"]),
            control_type,
            sign,
        )
        for assignment in assignments
        for control_type in protocol.G4_VECTOR_CLASSES
        for sign in protocol.G4_SIGNS
    ]
    vector_rows = receipt["vectors"]
    if not isinstance(vector_rows, list) or len(vector_rows) != len(expected_order):
        raise AnalysisContractError("G4 resolved vector inventory count differs")
    indexed: dict[tuple[tuple[int, ...], str, int], Mapping[str, Any]] = {}
    pair_rows: dict[tuple[str, str], dict[int, Mapping[str, Any]]] = defaultdict(dict)
    for offset, (expected, row) in enumerate(zip(expected_order, vector_rows)):
        _require_fields(row, G4_RESOLVED_VECTOR_FIELDS, f"G4 resolved vector {offset}")
        assignment_id, subset, control_type, sign = expected
        subset_raw = row["subset_feature_ids"]
        resolved_raw = row["resolved_feature_ids"]
        if not isinstance(subset_raw, list) or not isinstance(resolved_raw, list):
            raise AnalysisContractError("G4 resolved feature inventories must be lists")
        observed_subset = tuple(
            _integer(value, "G4 subset feature ID") for value in subset_raw
        )
        observed_resolved = tuple(
            _integer(value, "G4 resolved feature ID") for value in resolved_raw
        )
        if (
            row["assignment_id"] != assignment_id
            or observed_subset != subset
            or row["control_type"] != control_type
            or _integer(row["sign"], "G4 resolved vector sign") != sign
            or _finite(row["coefficient"], "G4 resolved coefficient") != 0.5 * sign
        ):
            raise AnalysisContractError("G4 resolved vector order or identity differs")
        if control_type == "target":
            expected_resolved = subset
            expected_seed = None
        elif control_type == "matched":
            expected_resolved = tuple(mapping[target] for target in subset)
            expected_seed = None
        else:
            expected_resolved = ()
            expected_seed = protocol.identity_bound_seed64(
                "g4-isotropic-v1", assignment_id
            )
        if observed_resolved != expected_resolved:
            raise AnalysisContractError("G4 resolved feature IDs differ")
        if row["isotropic_seed"] != expected_seed:
            raise AnalysisContractError("G4 isotropic seed/absence differs")
        raw_norm = _finite(row["raw_norm"], "G4 resolved raw norm")
        rescale = _finite(row["norm_rescale"], "G4 resolved norm rescale")
        final_norm = _finite(row["final_norm"], "G4 resolved final norm")
        reference_norm = _finite(
            row["target_reference_final_norm"], "G4 target reference norm"
        )
        vector_rms = _finite(row["vector_rms"], "G4 resolved vector RMS")
        if min(raw_norm, rescale, final_norm, reference_norm, vector_rms) <= 0.0:
            raise AnalysisContractError("G4 resolved vector norms must be positive")
        norm_error = _nonnegative(
            row["norm_relative_error"], "G4 resolved norm relative error"
        )
        reconstructed_error = abs(final_norm - reference_norm) / reference_norm
        if not math.isclose(norm_error, reconstructed_error, rel_tol=1e-9, abs_tol=1e-12):
            raise AnalysisContractError("G4 norm-match error does not reconstruct")
        if not math.isclose(
            vector_rms,
            final_norm / math.sqrt(protocol.MODEL_SPEC["residual_width"]),
            rel_tol=1e-9,
            abs_tol=1e-12,
        ):
            raise AnalysisContractError("G4 vector RMS does not reconstruct from BF16 norm")
        if control_type == "target":
            if norm_error != 0.0 or rescale != 1.0 or final_norm != reference_norm:
                raise AnalysisContractError("G4 target vector norm contract differs")
        elif norm_error > protocol.G4_CONTROL_NORM_RELATIVE_ERROR_MAX:
            raise AnalysisContractError("G4 control norm-match contract failed")
        raw_hash = _hex64(row["raw_vector_sha256"], "G4 raw BF16 vector hash")
        vector_hash = _hex64(row["vector_sha256"], "G4 BF16 vector hash")
        positive_hash = _hex64(
            row["positive_vector_sha256"], "G4 positive BF16 vector hash"
        )
        negative_hash = _hex64(
            row["negative_vector_sha256"], "G4 negative BF16 vector hash"
        )
        if vector_hash != (positive_hash if sign == 1 else negative_hash):
            raise AnalysisContractError("G4 sign-specific BF16 vector hash differs")
        if positive_hash == negative_hash or raw_hash == "0" * 64:
            raise AnalysisContractError("G4 signed/raw BF16 vector hashes are invalid")
        if row["dtype"] != "bfloat16":
            raise AnalysisContractError("G4 resolved vector dtype differs")
        for field in (
            "finite",
            "precomputed_before_any_edited_forward",
            "signed_pair_exact_negation",
        ):
            if not _boolean(row[field], f"G4 resolved {field}"):
                raise AnalysisContractError(f"G4 resolved vector {field} differs")
        if _integer(
            row["edited_forward_count_at_compute"], "G4 resolved forward count"
        ) != 0:
            raise AnalysisContractError("G4 vector was materialized after an edited forward")
        relation_payload = {
            "assignment_id": assignment_id,
            "control_type": control_type,
            "dtype": "bfloat16",
            "positive_vector_sha256": positive_hash,
            "negative_vector_sha256": negative_hash,
            "relation": "negative_is_exact_elementwise_bfloat16_negation_of_positive",
        }
        if _hex64(
            row["signed_pair_relation_sha256"], "G4 exact-negation relation hash"
        ) != protocol.canonical_sha256(relation_payload):
            raise AnalysisContractError("G4 exact-negation relation does not reconstruct")
        identity = (subset, control_type, sign)
        indexed[identity] = row
        pair_rows[(assignment_id, control_type)][sign] = row

    for pair_identity, signs in pair_rows.items():
        if set(signs) != set(protocol.G4_SIGNS):
            raise AnalysisContractError("G4 signed vector pair is incomplete")
        positive = signs[1]
        negative = signs[-1]
        invariant_fields = (
            "raw_norm",
            "norm_rescale",
            "final_norm",
            "norm_relative_error",
            "target_reference_final_norm",
            "vector_rms",
            "positive_vector_sha256",
            "negative_vector_sha256",
            "signed_pair_relation_sha256",
        )
        if any(positive[field] != negative[field] for field in invariant_fields):
            raise AnalysisContractError(f"G4 signed-pair metadata differs: {pair_identity}")
    payload = dict(receipt)
    observed_hash = _hex64(payload.pop("receipt_sha256"), "G4 inventory receipt hash")
    if observed_hash != protocol.canonical_sha256(payload):
        raise AnalysisContractError("G4 vector-inventory receipt hash does not reconstruct")
    return {
        "plan_manifest_sha256": plan_hash,
        "vector_inventory_receipt_sha256": observed_hash,
        "matched_feature_ids": tuple(matched_ids),
        "vectors": indexed,
    }


def analyze_g4(
    clean_rows: Iterable[Mapping[str, Any]],
    vector_rows: Iterable[Mapping[str, Any]],
    telemetry_rows: Iterable[Mapping[str, Any]],
    *,
    vector_inventory_receipt: Mapping[str, Any] | None = None,
    lineage_binding: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Apply the exact G4 numerical preflight and realized-edit telemetry gate."""

    prompt_ids = tuple(row["prompt_id"] for row in protocol.neutral_prompts())
    prepared_clean = unwrap_measurement_rows(
        clean_rows,
        measurement_fields=G4_CLEAN_FIELDS,
        lineage_binding=lineage_binding,
        label="G4 clean RMS",
        measurement_kind="g4_clean",
        task_key=lambda row: (row["prompt_id"],),
        phase="G4",
        filename="g4_clean_rows.jsonl",
    )
    clean = _exact_index(
        prepared_clean,
        fields=G4_CLEAN_FIELDS,
        key=lambda row: (row.get("prompt_id"),),
        expected={(prompt_id,) for prompt_id in prompt_ids},
        label="G4 clean RMS",
    )
    clean_rms: dict[str, float] = {}
    for (prompt_id,), row in clean.items():
        if not _boolean(row["finite"], f"G4 clean {prompt_id} finite"):
            raise AnalysisContractError(f"G4 clean RMS is non-finite: {prompt_id}")
        value = _finite(row["h50_pre_rms"], f"G4 clean {prompt_id} RMS")
        if value <= 0.0:
            raise AnalysisContractError("G4 clean RMS must be positive")
        clean_rms[str(prompt_id)] = value

    subsets = _g4_subset_inventory()
    classes = tuple(protocol.G4_VECTOR_CLASSES)
    inventory_binding = validate_g4_vector_inventory_receipt(
        vector_inventory_receipt
    )
    if (
        lineage_binding is not None
        and inventory_binding["plan_manifest_sha256"]
        != lineage_binding["plan_manifest_sha256"]
    ):
        raise AnalysisContractError("G4 vector inventory belongs to another plan")
    inventory_vectors = inventory_binding["vectors"]
    expected_vectors = {
        (subset, control_type, sign)
        for subset in subsets
        for control_type in classes
        for sign in protocol.G4_SIGNS
    }
    prepared_vectors = unwrap_measurement_rows(
        vector_rows,
        measurement_fields=G4_VECTOR_FIELDS,
        lineage_binding=lineage_binding,
        label="G4 vector preflight",
        measurement_kind="g4_vector",
        task_key=lambda row: (
            list(row["subset_feature_ids"]),
            row["control_type"],
            row["sign"],
        ),
        phase="G4",
        filename="g4_vector_rows.jsonl",
    )
    vectors = _exact_index(
        prepared_vectors,
        fields=G4_VECTOR_FIELDS,
        key=lambda row: (
            tuple(row.get("subset_feature_ids", ())),
            row.get("control_type"),
            row.get("sign"),
        ),
        expected=expected_vectors,
        label="G4 vector preflight",
    )
    minimum_clean_rms = min(clean_rms.values())
    vector_failures: list[str] = []
    vector_hashes: dict[tuple[tuple[int, ...], str, int], str] = {}
    maximum_ratio = 0.0
    for identity, row in sorted(vectors.items(), key=lambda item: repr(item[0])):
        subset, control_type, sign = identity
        if tuple(row["subset_feature_ids"]) != subset:
            raise AnalysisContractError(f"G4 subset encoding differs: {identity}")
        if _integer(row["sign"], f"G4 {identity} sign") != sign:
            raise AnalysisContractError(f"G4 sign differs: {identity}")
        coefficient = _finite(row["coefficient"], f"G4 {identity} coefficient")
        if coefficient != 0.5 * sign:
            raise AnalysisContractError(f"G4 coefficient is not exactly signed 0.5: {identity}")
        vector_rms = _finite(row["vector_rms"], f"G4 {identity} vector RMS")
        if vector_rms <= 0.0:
            raise AnalysisContractError(f"G4 vector RMS is not positive: {identity}")
        digest = _hex64(row["vector_sha256"], f"G4 {identity} vector hash")
        inventory_row = inventory_vectors[identity]
        if (
            digest != inventory_row["vector_sha256"]
            or vector_rms != inventory_row["vector_rms"]
            or row["dtype"] != inventory_row["dtype"]
            or row["finite"] != inventory_row["finite"]
            or row["precomputed_before_any_edited_forward"]
            != inventory_row["precomputed_before_any_edited_forward"]
            or row["edited_forward_count_at_compute"]
            != inventory_row["edited_forward_count_at_compute"]
        ):
            raise AnalysisContractError(f"G4 measurement differs from vector receipt: {identity}")
        vector_hashes[identity] = digest
        ratio = vector_rms / minimum_clean_rms
        maximum_ratio = max(maximum_ratio, ratio)
        if ratio > protocol.G4_RMS_RATIO_MAX:
            vector_failures.append(f"{identity}:rms_ratio")
        if row["dtype"] != "bfloat16":
            vector_failures.append(f"{identity}:dtype")
        if not _boolean(row["finite"], f"G4 {identity} finite"):
            vector_failures.append(f"{identity}:finite")
        if not _boolean(
            row["precomputed_before_any_edited_forward"],
            f"G4 {identity} precomputed-before-forward",
        ):
            vector_failures.append(f"{identity}:preflight_order")
        if _integer(
            row["edited_forward_count_at_compute"],
            f"G4 {identity} forward count",
        ) != 0:
            vector_failures.append(f"{identity}:forward_before_preflight")

    expected_telemetry = {
        (prompt_id, subset, control_type, sign)
        for prompt_id in protocol.G4_SENTINEL_PROMPT_IDS
        for subset in subsets
        for control_type in classes
        for sign in protocol.G4_SIGNS
    }
    prepared_telemetry = unwrap_measurement_rows(
        telemetry_rows,
        measurement_fields=G4_TELEMETRY_FIELDS,
        lineage_binding=lineage_binding,
        label="G4 realized telemetry",
        measurement_kind="g4_telemetry",
        task_key=lambda row: (
            row["prompt_id"],
            list(row["subset_feature_ids"]),
            row["control_type"],
            row["sign"],
        ),
        phase="G4",
        filename="g4_telemetry_rows.jsonl",
    )
    telemetry = _exact_index(
        prepared_telemetry,
        fields=G4_TELEMETRY_FIELDS,
        key=lambda row: (
            row.get("prompt_id"),
            tuple(row.get("subset_feature_ids", ())),
            row.get("control_type"),
            row.get("sign"),
        ),
        expected=expected_telemetry,
        label="G4 realized telemetry",
    )
    telemetry_failures: list[str] = []
    clean_identity_by_prompt: dict[str, tuple[str, str, str]] = {}
    for identity, row in sorted(telemetry.items(), key=lambda item: repr(item[0])):
        prompt_id, subset, control_type, sign = identity
        vector_identity = (subset, control_type, sign)
        coefficient = _finite(row["coefficient"], f"G4 telemetry {identity} coefficient")
        if coefficient != 0.5 * sign:
            raise AnalysisContractError(f"G4 telemetry coefficient differs: {identity}")
        if _hex64(row["vector_sha256"], f"G4 telemetry {identity} vector hash") != vector_hashes[vector_identity]:
            raise AnalysisContractError(f"G4 telemetry names another vector: {identity}")
        input_hash = _hex64(
            row["input_token_ids_sha256"], f"G4 telemetry {identity} input hash"
        )
        clean_input_hash = _hex64(
            row["clean_input_token_ids_sha256"],
            f"G4 telemetry {identity} clean input hash",
        )
        clean_pre = _hex64(
            row["clean_pre_edit_sha256"], f"G4 telemetry {identity} clean pre-edit"
        )
        edited_pre = _hex64(
            row["edited_pre_edit_sha256"], f"G4 telemetry {identity} edited pre-edit"
        )
        expected_post = _hex64(
            row["expected_post_edit_sha256"],
            f"G4 telemetry {identity} expected post-edit",
        )
        observed_post = _hex64(
            row["observed_post_edit_sha256"],
            f"G4 telemetry {identity} observed post-edit",
        )
        clean_output = _hex64(
            row["clean_output_sha256"], f"G4 telemetry {identity} clean output"
        )
        sham_output = _hex64(
            row["sham_output_sha256"], f"G4 telemetry {identity} sham output"
        )
        clean_identity = (clean_input_hash, clean_pre, clean_output)
        if prompt_id in clean_identity_by_prompt and clean_identity_by_prompt[prompt_id] != clean_identity:
            raise AnalysisContractError(
                f"G4 clean sentinel identity changes across conditions: {prompt_id}"
            )
        clean_identity_by_prompt[prompt_id] = clean_identity
        if input_hash != clean_input_hash:
            telemetry_failures.append(f"{identity}:input_token_ids")
        if edited_pre != clean_pre:
            telemetry_failures.append(f"{identity}:pre_edit_state")
        if observed_post != expected_post:
            telemetry_failures.append(f"{identity}:exact_post_edit")
        if sham_output != clean_output:
            telemetry_failures.append(f"{identity}:clean_sham")
        delta_rmse = _nonnegative(
            row["realized_delta_relative_rmse"],
            f"G4 telemetry {identity} realized delta RMSE",
        )
        sign_cosine = _signed_unit_interval(
            row["sign_cosine"], f"G4 telemetry {identity} sign cosine"
        )
        if delta_rmse > protocol.G4_DELTA_RELATIVE_RMSE_MAX:
            telemetry_failures.append(f"{identity}:delta_rmse")
        if sign_cosine < protocol.G4_SIGN_COSINE_MIN:
            telemetry_failures.append(f"{identity}:sign_cosine")
        hook_count = _integer(
            row["hook_fire_count"], f"G4 telemetry {identity} hook count"
        )
        if hook_count < 0:
            raise AnalysisContractError("G4 hook-fire count must be nonnegative")
        if hook_count != protocol.G4_HOOK_FIRE_COUNT:
            telemetry_failures.append(f"{identity}:hook_fire_count")
        for field in ("downstream_finite", "logits_finite"):
            if not _boolean(row[field], f"G4 telemetry {identity} {field}"):
                telemetry_failures.append(f"{identity}:{field}")
        if _boolean(
            row["attenuation_attempted"], f"G4 telemetry {identity} attenuation"
        ):
            telemetry_failures.append(f"{identity}:attenuation")
        retry_count = _integer(
            row["retry_count"], f"G4 telemetry {identity} retry count"
        )
        if retry_count < 0:
            raise AnalysisContractError("G4 retry count must be nonnegative")
        if retry_count != 0:
            telemetry_failures.append(f"{identity}:retry")

    passed = not vector_failures and not telemetry_failures
    return {
        "gate": "G4",
        "status": "pass" if passed else "fail",
        "clean_prompt_count": len(clean),
        "vector_count": len(vectors),
        "telemetry_count": len(telemetry),
        "maximum_vector_to_clean_rms_ratio": maximum_ratio,
        "rms_ratio_threshold": protocol.G4_RMS_RATIO_MAX,
        "vector_failure_count": len(vector_failures),
        "vector_failures": vector_failures,
        "telemetry_failure_count": len(telemetry_failures),
        "telemetry_failures": telemetry_failures,
        "exact_bfloat16_post_edit_required": True,
        "delta_relative_rmse_threshold": protocol.G4_DELTA_RELATIVE_RMSE_MAX,
        "sign_cosine_threshold": protocol.G4_SIGN_COSINE_MIN,
        "no_attenuation_or_retry_allowed": True,
        "scope": "pilot_specific_vector_inventory_and_preflight_implementation_only",
        "successor_must_repeat_target_blind_preflight": True,
    }


def _validate_phase_bindings(
    value: Mapping[str, Any],
    *,
    label: str,
) -> None:
    manifests = value.get("phase_file_manifests")
    measurements = value.get("phase_measurement_files")
    if (
        not isinstance(manifests, Mapping)
        or set(manifests) != set(PHASE_MEASUREMENT_FILENAMES)
        or not isinstance(measurements, Mapping)
        or set(measurements) != set(PHASE_MEASUREMENT_FILENAMES)
    ):
        raise AnalysisContractError(f"{label} phase inventory differs")
    for phase, filenames in PHASE_MEASUREMENT_FILENAMES.items():
        manifest = manifests[phase]
        _require_fields(manifest, PHASE_FILE_MANIFEST_FIELDS, f"{label} {phase} manifest")
        for field in PHASE_FILE_MANIFEST_FIELDS:
            _hex64(manifest[field], f"{label} {phase} {field}")
        files = measurements[phase]
        if not isinstance(files, Mapping) or set(files) != set(filenames):
            raise AnalysisContractError(f"{label} {phase} measurement inventory differs")
        for filename in filenames:
            record = files[filename]
            _require_fields(
                record,
                MEASUREMENT_FILE_BINDING_FIELDS,
                f"{label} measurement {filename}",
            )
            if (
                isinstance(record["row_count"], bool)
                or not isinstance(record["row_count"], int)
                or record["row_count"] < 0
            ):
                raise AnalysisContractError(f"{label} {filename} row count differs")
            _hex64(record["content_sha256"], f"{label} {filename} content hash")
            _hex64(
                record["logical_rows_sha256"], f"{label} {filename} logical hash"
            )


def _validate_structural_audit_receipt(
    receipt: Mapping[str, Any],
) -> str:
    _require_fields(
        receipt, STRUCTURAL_AUDIT_RECEIPT_FIELDS, "structural audit receipt"
    )
    if (
        receipt.get("schema_version") != 1
        or receipt.get("receipt_kind") != "independent_structural_audit_v1"
        or receipt.get("status") != "pass"
        or receipt.get("issuer") != protocol.STRUCTURAL_AUDIT_ISSUER
        or receipt.get("study_id") != protocol.STUDY_ID
        or receipt.get("protocol_version") != protocol.PROTOCOL_VERSION
    ):
        raise AnalysisContractError("structural audit identity differs")
    for field in (
        "plan_manifest_sha256",
        "execution_binding_canonical_sha256",
        "source_inventory_sha256",
        "structural_audit_source_sha256",
        "tokenizer_audit_receipt_sha256",
        "vector_inventory_receipt_sha256",
    ):
        _hex64(receipt[field], f"structural audit {field}")
    for field in (
        "prior_outcome_inputs",
        "target_prompt_inputs",
        "target_outcome_inputs",
    ):
        if receipt[field] != []:
            raise AnalysisContractError(f"structural audit {field} is not empty")
    _validate_phase_bindings(receipt, label="structural audit")
    payload = dict(receipt)
    observed = _hex64(payload.pop("receipt_sha256"), "structural audit receipt hash")
    if observed != protocol.canonical_sha256(payload):
        raise AnalysisContractError("structural audit receipt hash does not reconstruct")
    return observed


def _validate_pilot_analysis_authorization(
    authorization: Mapping[str, Any],
    *,
    structural_audit_receipt: Mapping[str, Any],
    datasets: Mapping[str, Sequence[Mapping[str, Any]]],
    tokenizer_binding: Mapping[str, Any],
    vector_binding: Mapping[str, Any],
) -> dict[str, Any]:
    structural_hash = _validate_structural_audit_receipt(structural_audit_receipt)
    _require_fields(
        authorization,
        PILOT_ANALYSIS_AUTHORIZATION_FIELDS,
        "pilot analysis authorization",
    )
    if (
        authorization.get("schema_version") != 1
        or authorization.get("authorization_kind")
        != "pilot_analysis_authorization_v2"
        or authorization.get("status") != "authorized"
        or authorization.get("issuer") != protocol.STRUCTURAL_AUDIT_ISSUER
        or authorization.get("study_id") != protocol.STUDY_ID
        or authorization.get("protocol_version") != protocol.PROTOCOL_VERSION
    ):
        raise AnalysisContractError("pilot analysis authorization identity differs")
    for field in STRUCTURAL_AUDIT_SHARED_FIELDS:
        if authorization.get(field) != structural_audit_receipt.get(field):
            raise AnalysisContractError(
                f"pilot authorization differs from structural audit: {field}"
            )
    if _hex64(
        authorization["structural_audit_receipt_sha256"],
        "pilot structural-audit receipt hash",
    ) != structural_hash:
        raise AnalysisContractError("pilot authorization binds another structural audit")
    plan_hash = _hex64(
        authorization["plan_manifest_sha256"], "pilot plan manifest hash"
    )
    if (
        tokenizer_binding["plan_manifest_sha256"] != plan_hash
        or tokenizer_binding["tokenizer_audit_receipt_sha256"]
        != authorization["tokenizer_audit_receipt_sha256"]
    ):
        raise AnalysisContractError("pilot authorization binds another tokenizer audit")
    if (
        vector_binding["plan_manifest_sha256"] != plan_hash
        or vector_binding["vector_inventory_receipt_sha256"]
        != authorization["vector_inventory_receipt_sha256"]
    ):
        raise AnalysisContractError("pilot authorization binds another G4 inventory")
    _validate_phase_bindings(authorization, label="pilot authorization")
    if set(datasets) != set(MEASUREMENT_FILENAMES):
        raise AnalysisContractError("pilot analysis dataset set differs")
    phase_run_ids: dict[str, str] = {}
    for phase, filenames in PHASE_MEASUREMENT_FILENAMES.items():
        run_ids: set[str] = set()
        for filename in filenames:
            record = authorization["phase_measurement_files"][phase][filename]
            rows = datasets[filename]
            byte_payload = b"".join(
                protocol.canonical_json_bytes(row) + b"\n" for row in rows
            )
            if (
                record["row_count"] != len(rows)
                or record["logical_rows_sha256"] != protocol.canonical_sha256(rows)
                or record["content_sha256"] != protocol.sha256_bytes(byte_payload)
            ):
                raise AnalysisContractError(
                    f"pilot measurement rows differ from authorization: {filename}"
                )
            for row_index, row in enumerate(rows):
                if not isinstance(row, Mapping):
                    raise AnalysisContractError("pilot measurement row is not an object")
                if (
                    row.get("study_id") != protocol.STUDY_ID
                    or row.get("protocol_version") != protocol.PROTOCOL_VERSION
                    or row.get("plan_manifest_sha256") != plan_hash
                    or not isinstance(row.get("run_id"), str)
                    or not row.get("run_id")
                ):
                    raise AnalysisContractError("pilot measurement lineage differs")
                if row.get("task_id") != expected_measurement_task_id(filename, row):
                    raise AnalysisContractError(
                        f"pilot measurement task ID does not reconstruct: {filename}"
                    )
                if row.get("row_id") != expected_measurement_row_id(
                    phase, filename, row_index, row
                ):
                    raise AnalysisContractError(
                        f"pilot measurement row ID does not reconstruct: {filename}"
                    )
                run_ids.add(str(row["run_id"]))
        if len(run_ids) != 1:
            raise AnalysisContractError(
                f"pilot phase {phase} does not bind one exact run ID"
            )
        phase_run_ids[phase] = next(iter(run_ids))
    payload = dict(authorization)
    observed_hash = _hex64(
        payload.pop("receipt_sha256"), "pilot analysis authorization receipt"
    )
    if observed_hash != protocol.canonical_sha256(payload):
        raise AnalysisContractError("pilot analysis authorization hash does not reconstruct")
    return {
        "study_id": protocol.STUDY_ID,
        "protocol_version": protocol.PROTOCOL_VERSION,
        "plan_manifest_sha256": plan_hash,
        "phase_run_ids": phase_run_ids,
        "execution_binding_canonical_sha256": authorization[
            "execution_binding_canonical_sha256"
        ],
        "structural_audit_receipt_sha256": structural_hash,
    }


def analyze_all(
    *,
    analysis_authorization: Mapping[str, Any],
    structural_audit_receipt: Mapping[str, Any],
    tokenizer_audit_receipt: Mapping[str, Any],
    vector_inventory_receipt: Mapping[str, Any],
    g1_rows: Iterable[Mapping[str, Any]],
    g2_transport_rows: Iterable[Mapping[str, Any]],
    g2_linearity_rows: Iterable[Mapping[str, Any]],
    g3_rows: Iterable[Mapping[str, Any]],
    g3p_rows: Iterable[Mapping[str, Any]],
    g4_clean_rows: Iterable[Mapping[str, Any]],
    g4_vector_rows: Iterable[Mapping[str, Any]],
    g4_telemetry_rows: Iterable[Mapping[str, Any]],
) -> dict[str, Any]:
    """Run the one authorized all-gates pilot acceptance decision."""

    datasets = {
        "g1_rows.jsonl": list(g1_rows),
        "g2_transport_rows.jsonl": list(g2_transport_rows),
        "g2_linearity_rows.jsonl": list(g2_linearity_rows),
        "g3_rows.jsonl": list(g3_rows),
        "g3p_rows.jsonl": list(g3p_rows),
        "g4_clean_rows.jsonl": list(g4_clean_rows),
        "g4_vector_rows.jsonl": list(g4_vector_rows),
        "g4_telemetry_rows.jsonl": list(g4_telemetry_rows),
    }
    tokenizer_binding = validate_tokenizer_audit_receipt(tokenizer_audit_receipt)
    vector_binding = validate_g4_vector_inventory_receipt(vector_inventory_receipt)
    lineage_binding = _validate_pilot_analysis_authorization(
        analysis_authorization,
        structural_audit_receipt=structural_audit_receipt,
        datasets=datasets,
        tokenizer_binding=tokenizer_binding,
        vector_binding=vector_binding,
    )

    def phase_lineage(phase: str) -> dict[str, Any]:
        return {
            "study_id": protocol.STUDY_ID,
            "protocol_version": protocol.PROTOCOL_VERSION,
            "plan_manifest_sha256": lineage_binding["plan_manifest_sha256"],
            "run_id": lineage_binding["phase_run_ids"][phase],
        }

    results = {
        "G1": analyze_g1(
            datasets["g1_rows.jsonl"],
            tokenizer_audit_receipt=tokenizer_audit_receipt,
            lineage_binding=phase_lineage("G1"),
        ),
        "G2": analyze_g2(
            datasets["g2_transport_rows.jsonl"],
            datasets["g2_linearity_rows.jsonl"],
            lineage_binding=phase_lineage("G2"),
        ),
        "G3": analyze_g3(
            datasets["g3_rows.jsonl"], lineage_binding=phase_lineage("G3")
        ),
        "G3P": analyze_g3p(
            datasets["g3p_rows.jsonl"], lineage_binding=phase_lineage("G3P")
        ),
        "G4": analyze_g4(
            datasets["g4_clean_rows.jsonl"],
            datasets["g4_vector_rows.jsonl"],
            datasets["g4_telemetry_rows.jsonl"],
            vector_inventory_receipt=vector_inventory_receipt,
            lineage_binding=phase_lineage("G4"),
        ),
    }
    acceptance = {
        "G1": results["G1"]["status"] == "pass",
        "G2": results["G2"]["status"] == "pass",
        "G2b_identity_incremental": (
            results["G2"]["G2b_identity_incremental"]["status"] == "pass"
        ),
        "G3": results["G3"]["status"] == "pass",
        "G3P": results["G3P"]["status"] == "pass",
        "G4": results["G4"]["status"] == "pass",
    }
    payload = {
        "study_id": protocol.STUDY_ID,
        "protocol_version": protocol.PROTOCOL_VERSION,
        "plan_manifest_sha256": lineage_binding["plan_manifest_sha256"],
        "phase_run_ids": lineage_binding["phase_run_ids"],
        "analysis_authorization_receipt_sha256": analysis_authorization[
            "receipt_sha256"
        ],
        "structural_audit_receipt_sha256": lineage_binding[
            "structural_audit_receipt_sha256"
        ],
        "tokenizer_audit_receipt_sha256": tokenizer_binding[
            "tokenizer_audit_receipt_sha256"
        ],
        "vector_inventory_receipt_sha256": vector_binding[
            "vector_inventory_receipt_sha256"
        ],
        "status": "pass" if all(acceptance.values()) else "fail",
        "acceptance_requirements": acceptance,
        "gates": results,
    }
    return {**payload, "result_sha256": protocol.canonical_sha256(payload)}

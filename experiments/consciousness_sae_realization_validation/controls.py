"""Fail-closed controls for the fresh SAE/J-lens realized-arc validation.

The module is result-free and standard-library-only.  It defines the boundary
between a frozen machine plan, target-blind neutral validation, raw storage,
structural audit, and analysis.  It does not render a target prompt, load a
model, inspect predecessor outcomes, or decide a target scientific endpoint.

The earlier ``consciousness_readout_validation_v1`` r15 result remains an
immutable disclosed prior result.  It is never accepted as a v1 gate, runtime
input, raw namespace, dose choice, or analysis authority.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any

from . import j_orientation
from .protocol import (
    DOSE_GRID,
    GATE_THRESHOLDS,
    J_LAYERS,
    LINEARITY_GATE_DOSES,
    PROTOCOL_VERSION,
    RANDOM_J_COUNT,
    RESOURCE_LIMITS,
    SAE_LAYER,
    STAGE_A_CAPTURE_COUNT,
    STAGE_A_DIRECTIONS,
    STAGE_A_LAYERS,
    STAGE_A_PROMPT_IDS,
    STAGE_B_BLOCK_COUNT,
    STAGE_B_CAPTURE_STATES,
    STAGE_B_MULTIPLIERS,
    STAGE_B_PROMPT_IDS,
    STUDY_ID,
    STUDY_SLUG,
    TRANSPORTS,
    WIDTH,
    aggregate_assignments,
    stage_b_rows,
)


CONTROL_SCHEMA_VERSION = 1

VOLUME_SENTINEL = ".consciousness_sae_realization_validation_v1_volume.json"
VOLUME_PURPOSE = "target_blind_realization_validation_v1"
RAW_NAMESPACE = (STUDY_SLUG, STUDY_ID, "raw")
SAFE_RUN_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")
HEX64 = re.compile(r"[0-9a-f]{64}")
HEX40 = re.compile(r"[0-9a-f]{40}")

# These are input deny-list markers, not a prohibition on disclosing prior work
# in human-readable provenance.  Runtime/analysis bindings use hashes only.
FORBIDDEN_PRIOR_INPUT_MARKERS = (
    "consciousness_readout_validation",
    "pilot_v1_plan",
    "pilot_v1_result",
    "pilot-r15",
    "qf2lwehl89",
    "consciousness_sae_switch_arc",
    "consciousness_sae_changepoint",
    "public_sae_consciousness_gating",
    "public_sae_placebo_steering",
    "sae_jlens_v2",
    "causal_transplant",
    "gemma_scope_9b",
)
FORBIDDEN_INPUT_FIELDS = frozenset(
    {
        "prior_result",
        "prior_results",
        "prior_outcome",
        "prior_outcomes",
        "pilot_result",
        "pilot_results",
        "target_outcome",
        "target_outcomes",
        "old_matched_feature_ids",
        "old_effect_size",
        "old_dose",
    }
)

SIGN_LABELS = ("minus", "plus")
SIGN_VALUES = {"minus": -1, "plus": 1}
DOSE_UNIT = "source_residual_rms_fraction"
DOSE_RMS_FRACTIONS = DOSE_GRID
DOSE_LINEARITY_COSINE_MIN = float(GATE_THRESHOLDS["linearity_cosine_min"])
DOSE_SLOPE_DISCREPANCY_MAX = float(
    GATE_THRESHOLDS["linearity_slope_discrepancy_max"]
)
EDIT_RELATIVE_RMSE_MAX = float(
    GATE_THRESHOLDS["requested_realized_relative_rmse_max"]
)
EDIT_SIGN_COSINE_MIN = float(GATE_THRESHOLDS["requested_realized_cosine_min"])
COMMON_MODE_TO_CENTRAL_RMS_MAX = float(
    GATE_THRESHOLDS["common_mode_to_central_rms_max"]
)
HOOK_FIRE_COUNT = int(GATE_THRESHOLDS["exact_hook_fire_count"])
RESIDUAL_WIDTH = WIDTH
RESIDUAL_DTYPE = "bfloat16"
RESIDUAL_DTYPE_BYTES = 2
HIGH_PRECISION_SHADOW_DTYPE = "float32"

FUTURE_STAGE_B_BLOCK_COUNT = STAGE_B_BLOCK_COUNT
MAX_INVESTIGATIVE_SPEND_USD = float(RESOURCE_LIMITS["max_spend_usd"])
MAX_WALLTIME_SECONDS = int(RESOURCE_LIMITS["max_walltime_seconds"])

J_LAYER_COUNT = len(J_LAYERS)

TARGET_BLIND_GATE_IDS = (
    "v1_source_inventory",
    "v1_public_artifact_rehash",
    "v1_tokenizer_endpoints",
    "v1_sae_vector_plan_inventory",
    "v1_stage_a_collection_safety",
    "v1_storage_benchmark",
    "v1_storage_budget",
)
TARGET_BLIND_SCIENTIFIC_GATE_IDS = (
    "v1_j_arithmetic_orientation",
    "v1_stage_a_global_j_shadow",
    "v1_layer50_j_shadow",
    "v1_stage_a_neutral_transport",
    "v1_stage_a_neutral_dose_linearity",
)

ANALYSIS_ARTIFACT_IDS = (
    "machine_plan",
    "source_residual_index",
    "edit_realization_rows",
    "transport_rows",
    "linearity_rows",
    "forward_schedule_rows",
    "raw_archive_manifest",
    "storage_ledger",
)


class ControlViolation(RuntimeError):
    """A stable, fail-closed successor control violation."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message


def canonical_json_bytes(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ControlViolation("canonical_json", "value is not canonical JSON") from exc


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


J_LAYERS_SHA256 = canonical_sha256(list(J_LAYERS))


def _expected_layer50_envelope_keys() -> tuple[tuple[str, int, int, float], ...]:
    """Exact prospective identity inventory used to authorize Stage B."""

    return tuple(
        (prompt_id, SAE_LAYER, direction, dose)
        for prompt_id in STAGE_A_PROMPT_IDS
        for direction in STAGE_A_DIRECTIONS
        for dose in LINEARITY_GATE_DOSES
    )


LAYER50_ENVELOPE_ROW_COUNT = len(_expected_layer50_envelope_keys())
LAYER50_ENVELOPE_IDENTITY_SET_SHA256 = canonical_sha256(
    list(_expected_layer50_envelope_keys())
)


def sha256_file(path: Path, *, chunk_bytes: int = 8 * 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(chunk_bytes):
            digest.update(chunk)
    return digest.hexdigest()


def identity_bound_seed64(namespace: str, *parts: object) -> int:
    if not isinstance(namespace, str) or not namespace:
        raise ControlViolation("seed_namespace", "seed namespace is empty")
    material = "|".join(
        (STUDY_ID, PROTOCOL_VERSION, namespace, *(str(part) for part in parts))
    ).encode("utf-8")
    return int.from_bytes(hashlib.sha256(material).digest()[:8], "big")


def random_j_seed(layer: int, index: int) -> int:
    if layer not in J_LAYERS or isinstance(index, bool) or not 0 <= index < RANDOM_J_COUNT:
        raise ControlViolation("random_j_coordinate", "random-J coordinate is outside v1")
    return identity_bound_seed64("random-j-v1", layer, index)


def _require_exact_fields(value: Mapping[str, Any], fields: frozenset[str], label: str) -> None:
    if not isinstance(value, Mapping) or set(value) != fields:
        actual = set(value) if isinstance(value, Mapping) else set()
        raise ControlViolation(
            "schema",
            f"{label} fields differ; missing={sorted(fields - actual)}, extra={sorted(actual - fields)}",
        )


def _require_hex64(value: Any, label: str) -> str:
    if not isinstance(value, str) or HEX64.fullmatch(value) is None:
        raise ControlViolation("hash", f"{label} is not lowercase SHA-256")
    return value


def _require_nonnegative_int(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ControlViolation("integer", f"{label} is not a nonnegative integer")
    return value


def _require_positive_int(value: Any, label: str) -> int:
    result = _require_nonnegative_int(value, label)
    if result == 0:
        raise ControlViolation("integer", f"{label} must be positive")
    return result


def _require_finite(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ControlViolation("number", f"{label} is not numeric")
    result = float(value)
    if not math.isfinite(result):
        raise ControlViolation("number", f"{label} is non-finite")
    return result


def _validate_self_hash(value: Mapping[str, Any], field: str, label: str) -> str:
    expected = _require_hex64(value.get(field), f"{label}.{field}")
    core = dict(value)
    core.pop(field, None)
    if canonical_sha256(core) != expected:
        raise ControlViolation("self_hash", f"{label} self-hash differs")
    return expected


def _validate_identity(value: Mapping[str, Any], label: str) -> None:
    if value.get("study_id") != STUDY_ID or value.get("protocol_version") != PROTOCOL_VERSION:
        raise ControlViolation("identity", f"{label} is not bound to realization validation v1")


def reject_forbidden_input_references(value: Any, *, location: str = "$") -> None:
    """Reject predecessor/result content recursively before any path is opened."""

    if isinstance(value, Mapping):
        for key, child in value.items():
            normalized_key = str(key).casefold()
            if normalized_key in FORBIDDEN_INPUT_FIELDS:
                raise ControlViolation("prior_input", f"forbidden field at {location}.{key}")
            reject_forbidden_input_references(child, location=f"{location}.{key}")
        return
    if isinstance(value, (list, tuple)):
        for index, child in enumerate(value):
            reject_forbidden_input_references(child, location=f"{location}[{index}]")
        return
    if isinstance(value, str):
        normalized = value.casefold().replace("\\", "/")
        if any(marker.casefold() in normalized for marker in FORBIDDEN_PRIOR_INPUT_MARKERS):
            raise ControlViolation("prior_input", f"forbidden predecessor marker at {location}")


def _reject_unsafe_path_text(value: str, label: str) -> None:
    normalized = value.casefold().replace("\\", "/")
    parts = PurePosixPath(normalized).parts
    if (
        not value
        or value.startswith("~")
        or "%" in value
        or ".." in parts
        or "file:" in normalized
        or normalized.startswith("//")
        or re.match(r"^[a-z]:", normalized) is not None
    ):
        raise ControlViolation("unsafe_path", f"{label} uses a prohibited path form")


def _require_symlink_free_components(path: Path, label: str) -> None:
    current = Path(path.anchor)
    for part in path.parts[1:] if path.is_absolute() else path.parts:
        current = current / part
        if current.is_symlink():
            raise ControlViolation("unsafe_path", f"{label} contains a symlink component")


def require_volume_root(root: Path, *, volume_id: str) -> Path:
    """Validate the dedicated realization-validation volume without creating it."""

    if not isinstance(volume_id, str) or not volume_id:
        raise ControlViolation("volume_id", "volume ID is empty")
    _reject_unsafe_path_text(str(root), "volume root")
    lexical = root.absolute()
    _require_symlink_free_components(lexical, "volume root")
    candidate = lexical.resolve(strict=True)
    if not candidate.is_dir():
        raise ControlViolation("volume_root", "volume root is not a real directory")
    sentinel_path = candidate / VOLUME_SENTINEL
    if sentinel_path.is_symlink() or not sentinel_path.is_file():
        raise ControlViolation("volume_sentinel", "validation sentinel is missing")
    try:
        sentinel = json.loads(sentinel_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ControlViolation("volume_sentinel", "validation sentinel is invalid") from exc
    expected = {
        "schema_version": CONTROL_SCHEMA_VERSION,
        "study_slug": STUDY_SLUG,
        "study_id": STUDY_ID,
        "protocol_version": PROTOCOL_VERSION,
        "volume_id": volume_id,
        "purpose": VOLUME_PURPOSE,
    }
    if sentinel != expected:
        raise ControlViolation("volume_sentinel", "validation sentinel differs")
    reject_forbidden_input_references(candidate.as_posix())
    return candidate


def require_fresh_raw_run_path(root: Path, *, volume_id: str, run_id: str) -> Path:
    """Return the one allowed fresh raw run path; never creates it."""

    if not isinstance(run_id, str) or SAFE_RUN_ID.fullmatch(run_id) is None:
        raise ControlViolation("run_id", "run ID is unsafe")
    validated = require_volume_root(root, volume_id=volume_id)
    destination = validated.joinpath(*RAW_NAMESPACE, run_id)
    if destination.exists() or destination.is_symlink():
        raise ControlViolation("raw_exists", "raw run path is not fresh")
    return destination


STORAGE_BENCHMARK_FIELDS = frozenset(
    {
        "schema_version",
        "status",
        "study_id",
        "protocol_version",
        "run_id",
        "plan_manifest_sha256",
        "runner_source_sha256",
        "target_blind_fixture_sha256",
        "filesystem_id",
        "maximum_workload_signature_sha256",
        "execution_authorization_status",
        "model_execution_authorized",
        "interruption_resume_exercised",
        "checksum_pass",
        "observed_peak_allocated_bytes",
        "observed_peak_logical_bytes",
        "model_forward_count",
        "target_prompt_render_count",
        "target_forward_count",
        "target_outcome_count",
        "prior_outcome_inputs",
        "receipt_sha256",
    }
)


def validate_storage_benchmark(receipt: Mapping[str, Any]) -> dict[str, Any]:
    """Require a target-blind maximum-workload interruption benchmark."""

    _require_exact_fields(receipt, STORAGE_BENCHMARK_FIELDS, "storage benchmark")
    _validate_identity(receipt, "storage benchmark")
    _validate_self_hash(receipt, "receipt_sha256", "storage benchmark")
    if receipt["schema_version"] != CONTROL_SCHEMA_VERSION or receipt["status"] != "pass":
        raise ControlViolation("storage_benchmark", "storage benchmark did not pass")
    if (
        receipt["execution_authorization_status"] != "not_evaluated_storage_only"
        or receipt["model_execution_authorized"] is not False
    ):
        raise ControlViolation(
            "storage_benchmark",
            "storage-only benchmark falsely implies model-execution authorization",
        )
    for field in (
        "plan_manifest_sha256",
        "runner_source_sha256",
        "target_blind_fixture_sha256",
        "maximum_workload_signature_sha256",
    ):
        _require_hex64(receipt[field], f"storage benchmark {field}")
    if not isinstance(receipt["filesystem_id"], str) or not receipt["filesystem_id"]:
        raise ControlViolation("storage_benchmark", "filesystem identity is empty")
    if receipt["interruption_resume_exercised"] is not True or receipt["checksum_pass"] is not True:
        raise ControlViolation("storage_benchmark", "interruption/resume or checksum failed")
    for field in ("observed_peak_allocated_bytes", "observed_peak_logical_bytes"):
        _require_positive_int(receipt[field], f"storage benchmark {field}")
    for field in (
        "model_forward_count",
        "target_prompt_render_count",
        "target_forward_count",
        "target_outcome_count",
    ):
        if _require_nonnegative_int(receipt[field], f"storage benchmark {field}") != 0:
            raise ControlViolation("storage_target", "benchmark accessed model or target")
    if receipt["prior_outcome_inputs"] != []:
        raise ControlViolation("storage_prior", "benchmark used prior outcomes")
    reject_forbidden_input_references(receipt)
    return dict(receipt)


STORAGE_BUDGET_FIELDS = frozenset(
    {
        "schema_version",
        "status",
        "study_id",
        "protocol_version",
        "plan_manifest_sha256",
        "benchmark_receipt_sha256",
        "volume_id",
        "capacity_bytes",
        "free_bytes_before_run",
        "public_artifact_bytes",
        "expected_validation_units",
        "capture_positions_per_unit",
        "capture_states_per_position",
        "residual_width",
        "residual_dtype",
        "residual_dtype_bytes",
        "expected_residual_bytes",
        "expected_selected_logit_bytes",
        "expected_metadata_bytes",
        "expected_hook_tensor_bytes",
        "transient_peak_ceiling_bytes",
        "max_concurrent_partial_bytes",
        "raw_run_ceiling_bytes",
        "minimum_final_reserve_bytes",
        "required_free_bytes",
        "max_atomic_shard_bytes",
        "model_forward_count",
        "target_prompt_render_count",
        "target_forward_count",
        "target_outcome_count",
        "prior_outcome_inputs",
        "receipt_sha256",
    }
)


def expected_residual_bytes(
    *, blocks: int, positions_per_block: int, states_per_position: int
) -> int:
    for value, label in (
        (blocks, "blocks"),
        (positions_per_block, "positions_per_block"),
        (states_per_position, "states_per_position"),
    ):
        _require_positive_int(value, label)
    return (
        blocks
        * positions_per_block
        * states_per_position
        * RESIDUAL_WIDTH
        * RESIDUAL_DTYPE_BYTES
    )


def validate_storage_budget(receipt: Mapping[str, Any]) -> dict[str, Any]:
    """Validate measured capacity before any validation model forward."""

    _require_exact_fields(receipt, STORAGE_BUDGET_FIELDS, "storage budget")
    _validate_identity(receipt, "storage budget")
    _validate_self_hash(receipt, "receipt_sha256", "storage budget")
    if receipt["schema_version"] != CONTROL_SCHEMA_VERSION or receipt["status"] != "pass":
        raise ControlViolation("storage_status", "storage budget is not passing v1 schema")
    _require_hex64(receipt["plan_manifest_sha256"], "storage plan manifest")
    _require_hex64(receipt["benchmark_receipt_sha256"], "storage benchmark receipt")
    if not isinstance(receipt["volume_id"], str) or not receipt["volume_id"]:
        raise ControlViolation("storage_volume", "storage volume ID is empty")
    integer_fields = (
        "capacity_bytes",
        "free_bytes_before_run",
        "public_artifact_bytes",
        "expected_validation_units",
        "capture_positions_per_unit",
        "capture_states_per_position",
        "residual_width",
        "residual_dtype_bytes",
        "expected_residual_bytes",
        "expected_selected_logit_bytes",
        "expected_metadata_bytes",
        "expected_hook_tensor_bytes",
        "transient_peak_ceiling_bytes",
        "max_concurrent_partial_bytes",
        "raw_run_ceiling_bytes",
        "minimum_final_reserve_bytes",
        "required_free_bytes",
        "max_atomic_shard_bytes",
        "model_forward_count",
        "target_prompt_render_count",
        "target_forward_count",
        "target_outcome_count",
    )
    numbers = {
        field: _require_nonnegative_int(receipt[field], f"storage.{field}")
        for field in integer_fields
    }
    if numbers["residual_width"] != RESIDUAL_WIDTH or receipt["residual_dtype"] != RESIDUAL_DTYPE:
        raise ControlViolation("storage_tensor", "stored residual tensor contract differs")
    if numbers["residual_dtype_bytes"] != RESIDUAL_DTYPE_BYTES:
        raise ControlViolation("storage_tensor", "stored residual byte width differs")
    exact_residual = expected_residual_bytes(
        blocks=numbers["expected_validation_units"],
        positions_per_block=numbers["capture_positions_per_unit"],
        states_per_position=numbers["capture_states_per_position"],
    )
    if numbers["expected_residual_bytes"] != exact_residual:
        raise ControlViolation("storage_formula", "residual byte estimate is not exact")
    expected_payload = sum(
        numbers[field]
        for field in (
            "expected_residual_bytes",
            "expected_selected_logit_bytes",
            "expected_metadata_bytes",
            "expected_hook_tensor_bytes",
        )
    )
    if expected_payload > numbers["raw_run_ceiling_bytes"]:
        raise ControlViolation("storage_ceiling", "expected payload exceeds run ceiling")
    if numbers["required_free_bytes"] != (
        numbers["raw_run_ceiling_bytes"]
        + numbers["transient_peak_ceiling_bytes"]
        + numbers["minimum_final_reserve_bytes"]
    ):
        raise ControlViolation("storage_reserve", "required free space is miscomputed")
    if numbers["free_bytes_before_run"] < numbers["required_free_bytes"]:
        raise ControlViolation("storage_free", "measured free space is below requirement")
    if numbers["capacity_bytes"] < (
        numbers["public_artifact_bytes"] + numbers["required_free_bytes"]
    ):
        raise ControlViolation("storage_capacity", "volume capacity cannot cover cache and run")
    if (
        numbers["max_atomic_shard_bytes"] <= 0
        or numbers["max_atomic_shard_bytes"] > int(RESOURCE_LIMITS["max_shard_bytes"])
    ):
        raise ControlViolation("storage_shard", "shard ceiling is zero or exceeds 2 GiB")
    if numbers["max_concurrent_partial_bytes"] < numbers["max_atomic_shard_bytes"]:
        raise ControlViolation("storage_shard", "partial ceiling cannot hold one atomic shard")
    if any(
        numbers[field]
        for field in (
            "model_forward_count",
            "target_prompt_render_count",
            "target_forward_count",
            "target_outcome_count",
        )
    ):
        raise ControlViolation("storage_target", "storage gate was measured after model/target access")
    if receipt["prior_outcome_inputs"] != []:
        raise ControlViolation("storage_prior", "storage gate names prior outcomes")
    return dict(receipt)


@dataclass
class StorageLedger:
    """In-memory append-only accounting; the runtime persists its signed receipt."""

    budget: Mapping[str, Any]
    records: list[dict[str, Any]] = field(default_factory=list)
    stored_bytes: int = 0
    logical_bytes: int = 0
    closed: bool = False

    def __post_init__(self) -> None:
        self.budget = validate_storage_budget(self.budget)

    def add(
        self,
        *,
        relative_path: str,
        stored_bytes: int,
        logical_bytes: int,
        sha256: str,
        artifact_role: str,
    ) -> None:
        if self.closed:
            raise ControlViolation("ledger_closed", "storage ledger is closed")
        path = PurePosixPath(relative_path)
        if (
            path.is_absolute()
            or not path.parts
            or ".." in path.parts
            or path.parts[0] != "raw"
            or str(path) != relative_path
        ):
            raise ControlViolation("ledger_path", "ledger path is not canonical raw-relative")
        if any(record["relative_path"] == relative_path for record in self.records):
            raise ControlViolation("ledger_duplicate", "ledger path is duplicated")
        stored = _require_nonnegative_int(stored_bytes, "ledger stored bytes")
        logical = _require_nonnegative_int(logical_bytes, "ledger logical bytes")
        if stored > int(self.budget["max_atomic_shard_bytes"]):
            raise ControlViolation("ledger_shard", "stored shard exceeds frozen maximum")
        if self.stored_bytes + stored > int(self.budget["raw_run_ceiling_bytes"]):
            raise ControlViolation("ledger_ceiling", "write would exceed raw run ceiling")
        _require_hex64(sha256, "ledger file hash")
        if not isinstance(artifact_role, str) or not artifact_role:
            raise ControlViolation("ledger_role", "ledger artifact role is empty")
        reject_forbidden_input_references(relative_path)
        row = {
            "sequence": len(self.records),
            "relative_path": relative_path,
            "artifact_role": artifact_role,
            "stored_bytes": stored,
            "logical_bytes": logical,
            "sha256": sha256,
        }
        self.records.append(row)
        self.stored_bytes += stored
        self.logical_bytes += logical

    def authorize_next_shard(
        self,
        *,
        free_bytes_now: int,
        next_shard_bytes: int,
        quarantined_partial_bytes: int = 0,
    ) -> None:
        """Fail before a forward when worst-case completion no longer fits."""

        if self.closed:
            raise ControlViolation("ledger_closed", "storage ledger is closed")
        free_now = _require_nonnegative_int(free_bytes_now, "current free bytes")
        next_size = _require_nonnegative_int(next_shard_bytes, "next shard bytes")
        quarantine = _require_nonnegative_int(
            quarantined_partial_bytes, "quarantined partial bytes"
        )
        if next_size > int(self.budget["max_atomic_shard_bytes"]):
            raise ControlViolation("ledger_shard", "next shard exceeds frozen maximum")
        remaining_final = int(self.budget["raw_run_ceiling_bytes"]) - self.stored_bytes
        required_now = (
            remaining_final
            + int(self.budget["transient_peak_ceiling_bytes"])
            + int(self.budget["minimum_final_reserve_bytes"])
            + quarantine
        )
        if next_size > remaining_final or free_now < required_now:
            raise ControlViolation(
                "ledger_high_water", "worst-case completion no longer fits"
            )

    def finalize(self, *, free_bytes_after_run: int) -> dict[str, Any]:
        if self.closed:
            raise ControlViolation("ledger_closed", "storage ledger is already closed")
        remaining = _require_nonnegative_int(free_bytes_after_run, "post-run free bytes")
        if remaining < int(self.budget["minimum_final_reserve_bytes"]):
            raise ControlViolation("ledger_reserve", "post-run reserve is not preserved")
        core = {
            "schema_version": CONTROL_SCHEMA_VERSION,
            "status": "pass",
            "study_id": STUDY_ID,
            "protocol_version": PROTOCOL_VERSION,
            "plan_manifest_sha256": self.budget["plan_manifest_sha256"],
            "volume_id": self.budget["volume_id"],
            "budget_receipt_sha256": self.budget["receipt_sha256"],
            "file_count": len(self.records),
            "stored_bytes": self.stored_bytes,
            "logical_bytes": self.logical_bytes,
            "free_bytes_after_run": remaining,
            "records": list(self.records),
            "partial_paths": [],
            "prior_outcome_inputs": [],
        }
        self.closed = True
        return {**core, "receipt_sha256": canonical_sha256(core)}


TARGET_BLIND_GATE_RECORD_FIELDS = frozenset(
    {
        "gate_id",
        "status",
        "receipt_sha256",
        "plan_manifest_sha256",
        "model_forward_count",
        "target_prompt_render_count",
        "target_forward_count",
        "target_outcome_count",
        "prior_outcome_inputs",
    }
)
TARGET_BLIND_RECEIPT_FIELDS = frozenset(
    {
        "schema_version",
        "status",
        "study_id",
        "protocol_version",
        "plan_manifest_sha256",
        "gate_records",
        "scientific_gate_statuses",
        "scientific_gate_receipt_sha256s",
        "stage_a_receipt_sha256",
        "storage_budget_receipt_sha256",
        "target_prompt_render_count",
        "target_forward_count",
        "target_outcome_count",
        "prior_outcome_inputs",
        "receipt_sha256",
    }
)


def validate_target_blind_gate_receipt(receipt: Mapping[str, Any]) -> dict[str, Any]:
    """Require every fresh v1 gate before the disjoint neutral Stage B panel."""

    _require_exact_fields(receipt, TARGET_BLIND_RECEIPT_FIELDS, "target-blind receipt")
    _validate_identity(receipt, "target-blind receipt")
    _validate_self_hash(receipt, "receipt_sha256", "target-blind receipt")
    if receipt["schema_version"] != CONTROL_SCHEMA_VERSION or receipt["status"] != "pass":
        raise ControlViolation("target_blind_status", "target-blind receipt is not passing")
    plan_hash = _require_hex64(receipt["plan_manifest_sha256"], "target-blind plan")
    _require_hex64(receipt["stage_a_receipt_sha256"], "Stage A receipt")
    _require_hex64(receipt["storage_budget_receipt_sha256"], "storage budget receipt")
    rows = receipt["gate_records"]
    if not isinstance(rows, list):
        raise ControlViolation("target_blind_gates", "gate records are not a list")
    indexed: dict[str, Mapping[str, Any]] = {}
    for offset, row in enumerate(rows):
        _require_exact_fields(row, TARGET_BLIND_GATE_RECORD_FIELDS, f"gate row {offset}")
        gate_id = row["gate_id"]
        if not isinstance(gate_id, str) or gate_id in indexed:
            raise ControlViolation("target_blind_gates", "gate ID is invalid or duplicated")
        indexed[gate_id] = row
        if row["status"] != "pass" or row["plan_manifest_sha256"] != plan_hash:
            raise ControlViolation("target_blind_gate_fail", f"gate is not passing: {gate_id}")
        _require_hex64(row["receipt_sha256"], f"{gate_id} receipt")
        _require_nonnegative_int(row["model_forward_count"], f"{gate_id} model forwards")
        for field in (
            "target_prompt_render_count",
            "target_forward_count",
            "target_outcome_count",
        ):
            if _require_nonnegative_int(row[field], f"{gate_id}.{field}") != 0:
                raise ControlViolation("target_blind_access", f"{gate_id} accessed the target")
        if row["prior_outcome_inputs"] != []:
            raise ControlViolation("target_blind_prior", f"{gate_id} used prior outcomes")
    if tuple(row["gate_id"] for row in rows) != TARGET_BLIND_GATE_IDS:
        raise ControlViolation("target_blind_gates", "gate order/inventory differs")
    if set(indexed) != set(TARGET_BLIND_GATE_IDS):  # defensive
        raise ControlViolation("target_blind_gates", "gate inventory differs")
    scientific = receipt["scientific_gate_statuses"]
    if not isinstance(scientific, Mapping) or set(scientific) != set(
        TARGET_BLIND_SCIENTIFIC_GATE_IDS
    ):
        raise ControlViolation("target_blind_science", "scientific gate inventory differs")
    if any(status not in {"pass", "fail"} for status in scientific.values()):
        raise ControlViolation("target_blind_science", "scientific gate status is invalid")
    scientific_hashes = receipt["scientific_gate_receipt_sha256s"]
    if not isinstance(scientific_hashes, Mapping) or set(scientific_hashes) != set(
        TARGET_BLIND_SCIENTIFIC_GATE_IDS
    ):
        raise ControlViolation(
            "target_blind_science", "scientific gate receipt inventory differs"
        )
    for gate_id, receipt_hash in scientific_hashes.items():
        _require_hex64(receipt_hash, f"target-blind scientific gate {gate_id}")
    if (
        scientific_hashes["v1_stage_a_global_j_shadow"]
        != receipt["stage_a_receipt_sha256"]
        or scientific_hashes["v1_layer50_j_shadow"]
        != receipt["stage_a_receipt_sha256"]
        or scientific_hashes["v1_stage_a_neutral_transport"]
        != receipt["stage_a_receipt_sha256"]
        or scientific_hashes["v1_stage_a_neutral_dose_linearity"]
        != receipt["stage_a_receipt_sha256"]
    ):
        raise ControlViolation(
            "target_blind_science", "Stage-A scientific status receipt binding differs"
        )
    for field in (
        "target_prompt_render_count",
        "target_forward_count",
        "target_outcome_count",
    ):
        if _require_nonnegative_int(receipt[field], f"target-blind.{field}") != 0:
            raise ControlViolation("target_blind_access", "target accessed before Stage B")
    if receipt["prior_outcome_inputs"] != []:
        raise ControlViolation("target_blind_prior", "target-blind receipt used prior outcomes")
    reject_forbidden_input_references(receipt)
    return dict(receipt)


EDIT_REALIZATION_FIELDS = frozenset(
    {
        "prompt_id",
        "edit_layer",
        "direction",
        "dose_fraction",
        "hook_fire_count_plus",
        "hook_fire_count_minus",
        "pre_equals_clean_plus",
        "pre_equals_clean_minus",
        "native_post_bytes_exact_plus",
        "native_post_bytes_exact_minus",
        "upstream_bytes_equal_clean_plus",
        "upstream_bytes_equal_clean_minus",
        "requested_vector_sha256",
        "realized_central_sha256",
        "requested_plus_realized_relative_rmse",
        "requested_minus_realized_relative_rmse",
        "requested_realized_central_relative_rmse",
        "requested_realized_central_cosine",
        "common_mode_to_central_rms",
        "requested_rms_fraction",
        "realized_rms_fraction",
        "bf16_fp32_j_cosine",
        "bf16_fp32_j_relative_rmse",
        "fp32_j_actual_final_cosine",
        "finite",
        "target_prompt_used",
    }
)


def stage_a_edit_task_id(
    prompt_id: str, edit_layer: int, direction: int, dose_fraction: float, sign: str
) -> str:
    """Return the identity-bound task ID for one explicit signed forward."""

    payload = {
        "study_id": STUDY_ID,
        "protocol_version": PROTOCOL_VERSION,
        "prompt_id": prompt_id,
        "edit_layer": edit_layer,
        "direction": direction,
        "dose_fraction": dose_fraction,
        "dose_unit": DOSE_UNIT,
        "sign": sign,
    }
    return f"stage_a_{canonical_sha256(payload)[:24]}"


def _expected_stage_a_edit_keys() -> set[tuple[str, int, int, float]]:
    return {
        (prompt_id, layer, direction, dose)
        for prompt_id in STAGE_A_PROMPT_IDS
        for layer in STAGE_A_LAYERS
        for direction in STAGE_A_DIRECTIONS
        for dose in DOSE_GRID
    }


def validate_layer50_envelope_inventory(
    rows: Iterable[Mapping[str, Any]],
) -> dict[str, Any]:
    """Require every and only layer-50 prospective gate-dose identity once."""

    expected = _expected_layer50_envelope_keys()
    observed: list[tuple[str, int, int, float]] = []
    realized: list[float] = []
    seen: set[tuple[str, int, int, float]] = set()
    for row in rows:
        if int(row.get("edit_layer", -1)) != SAE_LAYER:
            continue
        dose = _require_finite(row.get("dose_fraction"), "layer-50 envelope dose")
        if dose not in LINEARITY_GATE_DOSES:
            continue
        key = (
            str(row.get("prompt_id")),
            SAE_LAYER,
            int(row.get("direction", -1)),
            dose,
        )
        if key in seen:
            raise ControlViolation("stage_a_envelope", f"duplicate envelope row: {key}")
        seen.add(key)
        observed.append(key)
        fraction = _require_finite(
            row.get("realized_rms_fraction"), "layer-50 realized RMS fraction"
        )
        if fraction <= 0.0 or fraction > 0.10:
            raise ControlViolation(
                "stage_a_envelope", "layer-50 realized RMS fraction is outside (0,0.10]"
            )
        realized.append(fraction)
    if tuple(observed) != expected:
        raise ControlViolation(
            "stage_a_envelope",
            "layer-50 envelope identity inventory/order differs",
        )
    return {
        "row_count": len(observed),
        "identity_set_sha256": canonical_sha256(list(observed)),
        "realized_rms_fraction_min": min(realized),
        "realized_rms_fraction_max": max(realized),
    }


def validate_edit_realization_rows(rows: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Validate all 1,152 paired rows representing 2,304 signed edits."""

    expected = _expected_stage_a_edit_keys()
    indexed: dict[tuple[str, int, int, float], Mapping[str, Any]] = {}
    failures: list[str] = []
    hard_safety_failures: list[str] = []
    realized_fidelity_failures: list[str] = []
    common_mode_failures: list[str] = []
    j_shadow_failures: list[str] = []
    j_shadow_failures_by_layer: dict[int, list[str]] = {
        layer: [] for layer in STAGE_A_LAYERS
    }
    layer50_j_shadow_failures: list[str] = []
    bounded_zero_one = (
        "requested_realized_central_cosine",
        "bf16_fp32_j_cosine",
        "fp32_j_actual_final_cosine",
    )
    for offset, row in enumerate(rows):
        _require_exact_fields(row, EDIT_REALIZATION_FIELDS, f"edit realization {offset}")
        dose = _require_finite(row["dose_fraction"], f"edit {offset}.dose")
        identity = (
            row["prompt_id"],
            row["edit_layer"],
            row["direction"],
            dose,
        )
        if identity in indexed:
            raise ControlViolation("edit_duplicate", f"duplicate edit row: {identity}")
        indexed[identity] = row
        if identity not in expected:
            raise ControlViolation("edit_grid", f"unplanned edit row: {identity}")
        for field in ("requested_vector_sha256", "realized_central_sha256"):
            _require_hex64(row[field], f"{identity}.{field}")
        for field in (
            "requested_plus_realized_relative_rmse",
            "requested_minus_realized_relative_rmse",
            "requested_realized_central_relative_rmse",
            "requested_realized_central_cosine",
            "common_mode_to_central_rms",
            "requested_rms_fraction",
            "realized_rms_fraction",
            "bf16_fp32_j_cosine",
            "bf16_fp32_j_relative_rmse",
            "fp32_j_actual_final_cosine",
        ):
            value = _require_finite(row[field], f"{identity}.{field}")
            if field in bounded_zero_one and not -1.0 <= value <= 1.0:
                raise ControlViolation("edit_metric", f"cosine is outside [-1,1]: {identity}")
        for field in ("hook_fire_count_plus", "hook_fire_count_minus"):
            if row[field] != HOOK_FIRE_COUNT:
                hard_safety_failures.append(f"{identity}:{field}")
        for field in (
            "pre_equals_clean_plus",
            "pre_equals_clean_minus",
            "native_post_bytes_exact_plus",
            "native_post_bytes_exact_minus",
            "upstream_bytes_equal_clean_plus",
            "upstream_bytes_equal_clean_minus",
        ):
            if row[field] is not True:
                hard_safety_failures.append(f"{identity}:{field}")
        if dose in LINEARITY_GATE_DOSES:
            if max(
                float(row["requested_plus_realized_relative_rmse"]),
                float(row["requested_minus_realized_relative_rmse"]),
                float(row["requested_realized_central_relative_rmse"]),
            ) > EDIT_RELATIVE_RMSE_MAX:
                realized_fidelity_failures.append(f"{identity}:realization_rmse")
            if float(row["requested_realized_central_cosine"]) < EDIT_SIGN_COSINE_MIN:
                realized_fidelity_failures.append(f"{identity}:realization_cosine")
            if float(row["common_mode_to_central_rms"]) > COMMON_MODE_TO_CENTRAL_RMS_MAX:
                common_mode_failures.append(f"{identity}:common_mode")
            if float(row["bf16_fp32_j_relative_rmse"]) > EDIT_RELATIVE_RMSE_MAX:
                failure = f"{identity}:fp32_j_rmse"
                j_shadow_failures.append(failure)
                j_shadow_failures_by_layer[int(row["edit_layer"])].append(failure)
                if int(row["edit_layer"]) == SAE_LAYER:
                    layer50_j_shadow_failures.append(failure)
            if float(row["bf16_fp32_j_cosine"]) < EDIT_SIGN_COSINE_MIN:
                failure = f"{identity}:fp32_j_cosine"
                j_shadow_failures.append(failure)
                j_shadow_failures_by_layer[int(row["edit_layer"])].append(failure)
                if int(row["edit_layer"]) == SAE_LAYER:
                    layer50_j_shadow_failures.append(failure)
        if row["requested_rms_fraction"] <= 0 or row["realized_rms_fraction"] <= 0:
            realized_fidelity_failures.append(f"{identity}:zero_rms")
        if row["finite"] is not True:
            hard_safety_failures.append(f"{identity}:finite")
            realized_fidelity_failures.append(f"{identity}:finite")
            common_mode_failures.append(f"{identity}:finite")
        if row["target_prompt_used"] is not False:
            raise ControlViolation("edit_target", "edit validation accessed a target prompt")
    actual = set(indexed)
    if actual != expected:
        raise ControlViolation(
            "edit_grid",
            f"edit grid differs: missing={len(expected-actual)}, extra={len(actual-expected)}",
        )
    failures.extend(hard_safety_failures)
    failures.extend(realized_fidelity_failures)
    failures.extend(common_mode_failures)
    failures.extend(j_shadow_failures)
    per_layer_gated_row_count = (
        len(STAGE_A_PROMPT_IDS)
        * len(STAGE_A_DIRECTIONS)
        * len(LINEARITY_GATE_DOSES)
    )
    j_shadow_layer_statuses = [
        {
            "edit_layer": layer,
            "status": "pass" if not j_shadow_failures_by_layer[layer] else "fail",
            "gated_row_count": per_layer_gated_row_count,
            "failure_count": len(j_shadow_failures_by_layer[layer]),
        }
        for layer in STAGE_A_LAYERS
    ]
    return {
        "status": "pass" if not failures else "fail",
        "edit_realization_status": (
            "pass"
            if not hard_safety_failures and not realized_fidelity_failures
            else "fail"
        ),
        "hard_safety_status": "pass" if not hard_safety_failures else "fail",
        "realized_edit_fidelity_status": (
            "pass" if not realized_fidelity_failures else "fail"
        ),
        "common_mode_status": "pass" if not common_mode_failures else "fail",
        "j_shadow_status": "pass" if not j_shadow_failures else "fail",
        "j_shadow_layer_statuses": j_shadow_layer_statuses,
        "j_shadow_layer_status_inventory_sha256": canonical_sha256(
            j_shadow_layer_statuses
        ),
        "layer50_j_shadow_status": (
            "pass" if not layer50_j_shadow_failures else "fail"
        ),
        "row_count": len(indexed),
        "expected_row_count": len(expected),
        "signed_edited_forward_count": len(indexed) * 2,
        "row_identity_set_sha256": canonical_sha256(sorted(indexed)),
        "failures": failures,
        "hard_safety_failures": hard_safety_failures,
        "realized_edit_fidelity_failures": realized_fidelity_failures,
        "common_mode_failures": common_mode_failures,
        "j_shadow_failures": j_shadow_failures,
        "layer50_j_shadow_failures": layer50_j_shadow_failures,
    }


def _rms(values: Sequence[float]) -> float:
    if not values:
        raise ControlViolation("tensor_values", "tensor sequence is empty")
    return math.sqrt(math.fsum(float(value) ** 2 for value in values) / len(values))


def _cosine(left: Sequence[float], right: Sequence[float]) -> float:
    if len(left) != len(right) or not left:
        raise ControlViolation("tensor_values", "cosine tensor shapes differ")
    numerator = math.fsum(float(a) * float(b) for a, b in zip(left, right, strict=True))
    left_norm = math.sqrt(math.fsum(float(value) ** 2 for value in left))
    right_norm = math.sqrt(math.fsum(float(value) ** 2 for value in right))
    if left_norm == 0 or right_norm == 0:
        raise ControlViolation("tensor_values", "cosine tensor norm is zero")
    return numerator / (left_norm * right_norm)


def independently_recompute_realized_pair(
    *,
    pre: Sequence[float],
    requested_plus: Sequence[float],
    requested_minus: Sequence[float],
    actual_plus: Sequence[float],
    actual_minus: Sequence[float],
) -> dict[str, Any]:
    """Recompute edit telemetry and realized central/common-mode vectors."""

    lengths = {len(pre), len(requested_plus), len(requested_minus), len(actual_plus), len(actual_minus)}
    if lengths != {RESIDUAL_WIDTH}:
        raise ControlViolation("tensor_values", "realization tensors are not width 8192")
    if any(
        not math.isfinite(float(value))
        for tensor in (pre, requested_plus, requested_minus, actual_plus, actual_minus)
        for value in tensor
    ):
        raise ControlViolation("tensor_values", "realization tensor is non-finite")
    if any(float(minus) != -float(plus) for plus, minus in zip(requested_plus, requested_minus, strict=True)):
        raise ControlViolation("signed_negation", "requested signed vectors are not exact negations")
    realized_plus = [float(actual) - float(base) for actual, base in zip(actual_plus, pre, strict=True)]
    realized_minus = [float(actual) - float(base) for actual, base in zip(actual_minus, pre, strict=True)]
    plus_error = [actual - float(requested) for actual, requested in zip(realized_plus, requested_plus, strict=True)]
    minus_error = [actual - float(requested) for actual, requested in zip(realized_minus, requested_minus, strict=True)]
    central = [
        (float(plus) - float(minus)) / 2.0
        for plus, minus in zip(actual_plus, actual_minus, strict=True)
    ]
    common = [
        (float(plus) + float(minus)) / 2.0 - float(base)
        for plus, minus, base in zip(actual_plus, actual_minus, pre, strict=True)
    ]
    central_rms = _rms(central)
    common_rms = _rms(common)
    return {
        "plus_relative_rmse": _rms(plus_error) / _rms(requested_plus),
        "minus_relative_rmse": _rms(minus_error) / _rms(requested_minus),
        "plus_cosine": _cosine(requested_plus, realized_plus),
        "minus_cosine": _cosine(requested_minus, realized_minus),
        "central_source_delta": central,
        "common_mode_delta": common,
        "common_mode_to_central_rms_ratio": common_rms / central_rms,
    }


def validate_native_post_bytes(
    row: Mapping[str, Any], *, expected_post_bytes: bytes, actual_post_bytes: bytes
) -> None:
    """Independently enforce exact native-BF16 post bytes and bound hashes."""

    if expected_post_bytes != actual_post_bytes:
        raise ControlViolation("native_post_bytes", "native post bytes differ")
    expected_hash = hashlib.sha256(expected_post_bytes).hexdigest()
    actual_hash = hashlib.sha256(actual_post_bytes).hexdigest()
    if (
        row.get("expected_post_tensor_sha256") != expected_hash
        or row.get("actual_post_tensor_sha256") != actual_hash
        or row.get("native_post_exact_match") is not True
    ):
        raise ControlViolation("native_post_bytes", "native post telemetry/hash differs")


def validate_fp32_shadow_comparison(
    row: Mapping[str, Any],
    *,
    native_realized_delta: Sequence[float],
    fp32_shadow_realized_delta: Sequence[float],
) -> dict[str, float]:
    """Independently compare native BF16 realization with the FP32 shadow."""

    if len(native_realized_delta) != RESIDUAL_WIDTH or len(fp32_shadow_realized_delta) != RESIDUAL_WIDTH:
        raise ControlViolation("fp32_shadow", "FP32 shadow tensors are not width 8192")
    error = [
        float(native) - float(shadow)
        for native, shadow in zip(
            native_realized_delta, fp32_shadow_realized_delta, strict=True
        )
    ]
    relative_rmse = _rms(error) / _rms(fp32_shadow_realized_delta)
    cosine = _cosine(native_realized_delta, fp32_shadow_realized_delta)
    if not math.isclose(
        relative_rmse,
        _require_finite(row.get("native_vs_fp32_shadow_relative_rmse"), "FP32 shadow RMSE"),
        rel_tol=0.0,
        abs_tol=1e-12,
    ) or not math.isclose(
        cosine,
        _require_finite(row.get("native_vs_fp32_shadow_cosine"), "FP32 shadow cosine"),
        rel_tol=0.0,
        abs_tol=1e-12,
    ):
        raise ControlViolation("fp32_shadow", "reported FP32 shadow metrics differ")
    if relative_rmse > EDIT_RELATIVE_RMSE_MAX or cosine < EDIT_SIGN_COSINE_MIN:
        raise ControlViolation("fp32_shadow", "native realization disagrees with FP32 shadow")
    return {"relative_rmse": relative_rmse, "cosine": cosine}


STAGE_A_TRANSPORT_FIELDS = frozenset(
    {
        "prompt_id",
        "edit_layer",
        "direction",
        "dose_fraction",
        "transport",
        "residual_delta_cosine",
        "fixed_token_logit_delta_pearson",
        "finite",
        "target_prompt_used",
    }
)
STAGE_A_LINEARITY_FIELDS = frozenset(
    {
        "prompt_id",
        "edit_layer",
        "direction",
        "dose_unit",
        "gate_doses",
        "realized_source_linearity_cosine_min",
        "realized_source_slope_discrepancy_max",
        "j_of_realized_linearity_cosine_min",
        "j_of_realized_slope_discrepancy_max",
        "actual_final_linearity_cosine_min",
        "actual_final_slope_discrepancy_max",
        "finite",
        "target_prompt_used",
    }
)


def validate_stage_a_transport_rows(rows: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Validate realized-source transport for every signed dose pair."""

    expected = {
        (prompt_id, layer, direction, dose, transport)
        for prompt_id in STAGE_A_PROMPT_IDS
        for layer in STAGE_A_LAYERS
        for direction in STAGE_A_DIRECTIONS
        for dose in DOSE_GRID
        for transport in TRANSPORTS
    }
    indexed: dict[tuple[Any, ...], Mapping[str, Any]] = {}
    failures: list[str] = []
    for offset, row in enumerate(rows):
        _require_exact_fields(row, STAGE_A_TRANSPORT_FIELDS, f"Stage A transport {offset}")
        dose = _require_finite(row["dose_fraction"], f"transport {offset}.dose")
        identity = (
            row["prompt_id"],
            row["edit_layer"],
            row["direction"],
            dose,
            row["transport"],
        )
        if identity in indexed:
            raise ControlViolation("stage_a_duplicate", f"duplicate Stage A row: {identity}")
        indexed[identity] = row
        if identity not in expected:
            raise ControlViolation("stage_a_grid", f"unplanned transport row: {identity}")
        if row["target_prompt_used"] is not False:
            raise ControlViolation("stage_a_target", "Stage A used a target prompt")
        if row["finite"] is not True:
            failures.append(f"{identity}:finite")
        residual = _require_finite(row["residual_delta_cosine"], f"{identity}.residual")
        logit = _require_finite(row["fixed_token_logit_delta_pearson"], f"{identity}.logit")
        if not -1.0 <= residual <= 1.0 or not -1.0 <= logit <= 1.0:
            raise ControlViolation("stage_a_metric", "Stage A correlation is outside [-1,1]")
    actual = set(indexed)
    if actual != expected:
        raise ControlViolation(
            "stage_a_grid",
            f"Stage A transport grid differs: missing={len(expected-actual)}, extra={len(actual-expected)}",
        )
    return {
        "status": "pass" if not failures else "fail",
        "row_count": len(indexed),
        "expected_row_count": len(expected),
        "row_identity_set_sha256": canonical_sha256(sorted(indexed)),
        "failures": failures,
    }


def validate_stage_a_linearity_rows(rows: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Require realized-source and J(realized) linearity at every neutral site."""

    expected = {
        (prompt_id, layer, direction)
        for prompt_id in STAGE_A_PROMPT_IDS
        for layer in STAGE_A_LAYERS
        for direction in STAGE_A_DIRECTIONS
    }
    indexed: dict[tuple[Any, ...], Mapping[str, Any]] = {}
    failures: list[str] = []
    for offset, row in enumerate(rows):
        _require_exact_fields(row, STAGE_A_LINEARITY_FIELDS, f"Stage A linearity {offset}")
        identity = (row["prompt_id"], row["edit_layer"], row["direction"])
        if identity in indexed:
            raise ControlViolation("stage_a_duplicate", f"duplicate linearity row: {identity}")
        indexed[identity] = row
        if identity not in expected:
            raise ControlViolation("stage_a_grid", f"unplanned linearity row: {identity}")
        if row["target_prompt_used"] is not False:
            raise ControlViolation("stage_a_target", "Stage A linearity used target prompt")
        if row["dose_unit"] != DOSE_UNIT or row["gate_doses"] != list(LINEARITY_GATE_DOSES):
            raise ControlViolation("stage_a_dose", "linearity dose unit/grid differs")
        metrics = {
            field: _require_finite(row[field], f"{identity}.{field}")
            for field in (
                "realized_source_linearity_cosine_min",
                "realized_source_slope_discrepancy_max",
                "j_of_realized_linearity_cosine_min",
                "j_of_realized_slope_discrepancy_max",
                "actual_final_linearity_cosine_min",
                "actual_final_slope_discrepancy_max",
            )
        }
        if min(
            metrics["realized_source_linearity_cosine_min"],
            metrics["j_of_realized_linearity_cosine_min"],
            metrics["actual_final_linearity_cosine_min"],
        ) < DOSE_LINEARITY_COSINE_MIN:
            failures.append(f"{identity}:cosine")
        if max(
            metrics["realized_source_slope_discrepancy_max"],
            metrics["j_of_realized_slope_discrepancy_max"],
            metrics["actual_final_slope_discrepancy_max"],
        ) > DOSE_SLOPE_DISCREPANCY_MAX:
            failures.append(f"{identity}:slope")
        if row["finite"] is not True:
            failures.append(f"{identity}:finite")
    actual = set(indexed)
    if actual != expected:
        raise ControlViolation(
            "stage_a_grid",
            f"Stage A linearity grid differs: missing={len(expected-actual)}, extra={len(actual-expected)}",
        )
    return {
        "status": "pass" if not failures else "fail",
        "row_count": len(indexed),
        "expected_row_count": len(expected),
        "row_identity_set_sha256": canonical_sha256(sorted(indexed)),
        "failures": failures,
    }


STAGE_A_NUMERIC_TELEMETRY_FILES = (
    "arithmetic_index.jsonl",
    "branch_index.jsonl",
    "clean_index.jsonl",
    "realization_rows.jsonl",
    "j_map_shadow_rows.jsonl",
    "transport_rows.jsonl",
    "linearity_rows.jsonl",
)
STAGE_A_RECOMPUTED_ROW_INVENTORIES = (
    "realization_rows",
    "j_map_shadow_rows",
    "transport_rows",
    "linearity_rows",
)
STAGE_A_NUMERIC_EDIT_CLASSIFICATION_FIELDS = frozenset(
    {
        "status",
        "edit_realization_status",
        "hard_safety_status",
        "realized_edit_fidelity_status",
        "common_mode_status",
        "j_shadow_status",
        "layer50_j_shadow_status",
        "j_shadow_layer_statuses",
        "j_shadow_layer_status_inventory_sha256",
        "row_count",
        "expected_row_count",
        "signed_edited_forward_count",
        "row_identity_set_sha256",
        "failure_count",
        "hard_safety_failure_count",
        "realized_edit_fidelity_failure_count",
        "common_mode_failure_count",
        "j_shadow_failure_count",
        "layer50_j_shadow_failure_count",
    }
)
STAGE_A_NUMERIC_GRID_CLASSIFICATION_FIELDS = frozenset(
    {
        "status",
        "row_count",
        "expected_row_count",
        "row_identity_set_sha256",
        "failure_count",
    }
)
STAGE_A_NUMERIC_RECOMPUTATION_FIELDS = frozenset(
    {
        "schema_version",
        "status",
        "edit_classification",
        "transport_classification",
        "linearity_classification",
        "telemetry_file_sha256s",
        "recomputed_row_inventory_sha256s",
        "raw_pair_count",
        "raw_transport_count",
        "raw_linearity_count",
        "classification_sha256",
    }
)


def compact_stage_a_numeric_classifications(
    *,
    edit_validation: Mapping[str, Any],
    transport_validation: Mapping[str, Any],
    linearity_validation: Mapping[str, Any],
) -> dict[str, Any]:
    """Reduce independently recomputed rows to the sealed gate classifications."""

    edit = {
        "status": edit_validation["status"],
        "edit_realization_status": edit_validation["edit_realization_status"],
        "hard_safety_status": edit_validation["hard_safety_status"],
        "realized_edit_fidelity_status": edit_validation[
            "realized_edit_fidelity_status"
        ],
        "common_mode_status": edit_validation["common_mode_status"],
        "j_shadow_status": edit_validation["j_shadow_status"],
        "layer50_j_shadow_status": edit_validation["layer50_j_shadow_status"],
        "j_shadow_layer_statuses": edit_validation["j_shadow_layer_statuses"],
        "j_shadow_layer_status_inventory_sha256": edit_validation[
            "j_shadow_layer_status_inventory_sha256"
        ],
        "row_count": edit_validation["row_count"],
        "expected_row_count": edit_validation["expected_row_count"],
        "signed_edited_forward_count": edit_validation[
            "signed_edited_forward_count"
        ],
        "row_identity_set_sha256": edit_validation["row_identity_set_sha256"],
        "failure_count": len(edit_validation["failures"]),
        "hard_safety_failure_count": len(edit_validation["hard_safety_failures"]),
        "realized_edit_fidelity_failure_count": len(
            edit_validation["realized_edit_fidelity_failures"]
        ),
        "common_mode_failure_count": len(
            edit_validation["common_mode_failures"]
        ),
        "j_shadow_failure_count": len(edit_validation["j_shadow_failures"]),
        "layer50_j_shadow_failure_count": len(
            edit_validation["layer50_j_shadow_failures"]
        ),
    }

    def compact_grid(value: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "status": value["status"],
            "row_count": value["row_count"],
            "expected_row_count": value["expected_row_count"],
            "row_identity_set_sha256": value["row_identity_set_sha256"],
            "failure_count": len(value["failures"]),
        }

    return {
        "edit_classification": edit,
        "transport_classification": compact_grid(transport_validation),
        "linearity_classification": compact_grid(linearity_validation),
    }


def build_stage_a_numeric_recomputation(
    *,
    edit_validation: Mapping[str, Any],
    transport_validation: Mapping[str, Any],
    linearity_validation: Mapping[str, Any],
    telemetry_file_sha256s: Mapping[str, str],
    recomputed_row_inventory_sha256s: Mapping[str, str],
) -> dict[str, Any]:
    """Seal the audit-derived Stage-A classifications and their raw inputs."""

    compact = compact_stage_a_numeric_classifications(
        edit_validation=edit_validation,
        transport_validation=transport_validation,
        linearity_validation=linearity_validation,
    )
    core = {
        "schema_version": CONTROL_SCHEMA_VERSION,
        "status": "pass_raw_telemetry_match",
        **compact,
        "telemetry_file_sha256s": dict(telemetry_file_sha256s),
        "recomputed_row_inventory_sha256s": dict(
            recomputed_row_inventory_sha256s
        ),
        "raw_pair_count": edit_validation["row_count"],
        "raw_transport_count": transport_validation["row_count"],
        "raw_linearity_count": linearity_validation["row_count"],
    }
    value = {**core, "classification_sha256": canonical_sha256(core)}
    return validate_stage_a_numeric_recomputation(value)


def validate_stage_a_numeric_recomputation(
    value: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate the compact classification emitted only after raw tensor joins."""

    _require_exact_fields(
        value, STAGE_A_NUMERIC_RECOMPUTATION_FIELDS, "Stage A numeric recomputation"
    )
    core = dict(value)
    supplied = core.pop("classification_sha256")
    if _require_hex64(supplied, "Stage A numeric recomputation hash") != canonical_sha256(
        core
    ):
        raise ControlViolation(
            "stage_a_numeric_audit", "numeric recomputation self-hash differs"
        )
    if (
        value["schema_version"] != CONTROL_SCHEMA_VERSION
        or value["status"] != "pass_raw_telemetry_match"
    ):
        raise ControlViolation(
            "stage_a_numeric_audit", "numeric recomputation identity/status differs"
        )
    telemetry = value["telemetry_file_sha256s"]
    recomputed = value["recomputed_row_inventory_sha256s"]
    if not isinstance(telemetry, Mapping) or set(telemetry) != set(
        STAGE_A_NUMERIC_TELEMETRY_FILES
    ):
        raise ControlViolation(
            "stage_a_numeric_audit", "numeric telemetry file inventory differs"
        )
    if not isinstance(recomputed, Mapping) or set(recomputed) != set(
        STAGE_A_RECOMPUTED_ROW_INVENTORIES
    ):
        raise ControlViolation(
            "stage_a_numeric_audit", "recomputed row inventory differs"
        )
    for label, digest in (*telemetry.items(), *recomputed.items()):
        _require_hex64(digest, f"Stage A numeric audit {label}")

    edit = value["edit_classification"]
    _require_exact_fields(
        edit,
        STAGE_A_NUMERIC_EDIT_CLASSIFICATION_FIELDS,
        "Stage A numeric edit classification",
    )
    statuses = (
        "status",
        "edit_realization_status",
        "hard_safety_status",
        "realized_edit_fidelity_status",
        "common_mode_status",
        "j_shadow_status",
        "layer50_j_shadow_status",
    )
    if any(edit[field] not in {"pass", "fail"} for field in statuses):
        raise ControlViolation(
            "stage_a_numeric_audit", "numeric edit status is invalid"
        )
    expected_pairs = len(_expected_stage_a_edit_keys())
    if (
        edit["row_count"] != expected_pairs
        or edit["expected_row_count"] != expected_pairs
        or edit["signed_edited_forward_count"] != expected_pairs * 2
    ):
        raise ControlViolation(
            "stage_a_numeric_audit", "numeric edit grid count differs"
        )
    _require_hex64(
        edit["row_identity_set_sha256"], "numeric edit identity-set hash"
    )
    _require_hex64(
        edit["j_shadow_layer_status_inventory_sha256"],
        "numeric J-shadow layer inventory hash",
    )
    failure_fields = (
        "failure_count",
        "hard_safety_failure_count",
        "realized_edit_fidelity_failure_count",
        "common_mode_failure_count",
        "j_shadow_failure_count",
        "layer50_j_shadow_failure_count",
    )
    counts = {
        field: _require_nonnegative_int(edit[field], f"numeric edit {field}")
        for field in failure_fields
    }
    expected_statuses = {
        "status": "pass" if counts["failure_count"] == 0 else "fail",
        "edit_realization_status": (
            "pass"
            if counts["hard_safety_failure_count"] == 0
            and counts["realized_edit_fidelity_failure_count"] == 0
            else "fail"
        ),
        "hard_safety_status": (
            "pass" if counts["hard_safety_failure_count"] == 0 else "fail"
        ),
        "realized_edit_fidelity_status": (
            "pass"
            if counts["realized_edit_fidelity_failure_count"] == 0
            else "fail"
        ),
        "common_mode_status": (
            "pass" if counts["common_mode_failure_count"] == 0 else "fail"
        ),
        "j_shadow_status": (
            "pass" if counts["j_shadow_failure_count"] == 0 else "fail"
        ),
        "layer50_j_shadow_status": (
            "pass" if counts["layer50_j_shadow_failure_count"] == 0 else "fail"
        ),
    }
    if any(edit[field] != status for field, status in expected_statuses.items()):
        raise ControlViolation(
            "stage_a_numeric_audit", "numeric edit status/failure count differs"
        )
    layer_rows = edit["j_shadow_layer_statuses"]
    if (
        not isinstance(layer_rows, list)
        or edit["j_shadow_layer_status_inventory_sha256"]
        != canonical_sha256(layer_rows)
        or [row.get("edit_layer") for row in layer_rows] != list(STAGE_A_LAYERS)
    ):
        raise ControlViolation(
            "stage_a_numeric_audit", "numeric J-shadow layer inventory differs"
        )
    per_layer_gated_count = (
        len(STAGE_A_PROMPT_IDS)
        * len(STAGE_A_DIRECTIONS)
        * len(LINEARITY_GATE_DOSES)
    )
    for row in layer_rows:
        if (
            not isinstance(row, Mapping)
            or set(row) != {
                "edit_layer",
                "status",
                "gated_row_count",
                "failure_count",
            }
            or row["gated_row_count"] != per_layer_gated_count
            or row["status"]
            != ("pass" if row["failure_count"] == 0 else "fail")
            or _require_nonnegative_int(
                row["failure_count"], "numeric per-layer J-shadow failure count"
            )
            != row["failure_count"]
        ):
            raise ControlViolation(
                "stage_a_numeric_audit", "numeric J-shadow layer row differs"
            )
    if (
        counts["failure_count"]
        != counts["hard_safety_failure_count"]
        + counts["realized_edit_fidelity_failure_count"]
        + counts["common_mode_failure_count"]
        + counts["j_shadow_failure_count"]
        or counts["j_shadow_failure_count"]
        != sum(row["failure_count"] for row in layer_rows)
    ):
        raise ControlViolation(
            "stage_a_numeric_audit", "numeric edit failure inventory differs"
        )
    layer50_row = next(
        row for row in layer_rows if row.get("edit_layer") == SAE_LAYER
    )
    if (
        edit["layer50_j_shadow_status"] != layer50_row["status"]
        or counts["layer50_j_shadow_failure_count"]
        != layer50_row["failure_count"]
    ):
        raise ControlViolation(
            "stage_a_numeric_audit", "numeric layer-50 J-shadow status differs"
        )

    expected_grid_counts = {
        "transport_classification": (
            len(STAGE_A_PROMPT_IDS)
            * len(STAGE_A_LAYERS)
            * len(STAGE_A_DIRECTIONS)
            * len(DOSE_GRID)
            * len(TRANSPORTS)
        ),
        "linearity_classification": (
            len(STAGE_A_PROMPT_IDS)
            * len(STAGE_A_LAYERS)
            * len(STAGE_A_DIRECTIONS)
        ),
    }
    for field, expected_count in expected_grid_counts.items():
        row = value[field]
        _require_exact_fields(
            row, STAGE_A_NUMERIC_GRID_CLASSIFICATION_FIELDS, field
        )
        failures = _require_nonnegative_int(
            row["failure_count"], f"{field} failure count"
        )
        if (
            row["status"] != ("pass" if failures == 0 else "fail")
            or row["row_count"] != expected_count
            or row["expected_row_count"] != expected_count
        ):
            raise ControlViolation(
                "stage_a_numeric_audit", f"{field} status/grid differs"
            )
        _require_hex64(row["row_identity_set_sha256"], f"{field} identity hash")
    if (
        value["raw_pair_count"] != expected_pairs
        or value["raw_transport_count"]
        != expected_grid_counts["transport_classification"]
        or value["raw_linearity_count"]
        != expected_grid_counts["linearity_classification"]
    ):
        raise ControlViolation(
            "stage_a_numeric_audit", "numeric raw row counts differ"
        )
    return dict(value)


STAGE_B_EDIT_FIELDS = frozenset(
    {
        "prompt_id",
        "assignment_id",
        "vector_class",
        "sign",
        "multiplier",
        "hook_fire_count",
        "pre_equals_clean",
        "native_post_bytes_exact",
        "upstream_45_49_bytes_equal_clean",
        "requested_realized_relative_rmse",
        "requested_realized_cosine",
        "requested_rms_fraction",
        "realized_rms_fraction",
        "fp32_requested_to_bfloat16_relative_rmse",
        "fp32_requested_to_bfloat16_cosine",
        "native_realized_to_fp32_requested_relative_rmse",
        "native_realized_to_fp32_requested_cosine",
        "requested_vector_sha256",
        "requested_fp32_vector_sha256",
        "realized_vector_sha256",
        "finite",
        "target_prompt_used",
    }
)

STAGE_B_REQUESTED_FIDELITY_METRICS = (
    (
        "requested_realized_relative_rmse",
        "requested_realized_cosine",
    ),
    (
        "fp32_requested_to_bfloat16_relative_rmse",
        "fp32_requested_to_bfloat16_cosine",
    ),
    (
        "native_realized_to_fp32_requested_relative_rmse",
        "native_realized_to_fp32_requested_cosine",
    ),
)


def stage_b_requested_edit_fidelity_pass(row: Mapping[str, Any]) -> bool:
    """Apply the prospectively frozen request-to-realization thresholds."""

    passed = True
    for rmse_field, cosine_field in STAGE_B_REQUESTED_FIDELITY_METRICS:
        rmse = _require_finite(row.get(rmse_field), f"Stage B {rmse_field}")
        cosine_value = _require_finite(
            row.get(cosine_field), f"Stage B {cosine_field}"
        )
        if not -1.0 <= cosine_value <= 1.0:
            raise ControlViolation(
                "stage_b_edit_metric", f"{cosine_field} is outside [-1,1]"
            )
        if rmse < 0.0:
            raise ControlViolation(
                "stage_b_edit_metric", f"{rmse_field} is negative"
            )
        if rmse > EDIT_RELATIVE_RMSE_MAX or cosine_value < EDIT_SIGN_COSINE_MIN:
            passed = False
    return passed


def validate_stage_b_edit_rows(rows: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Validate Stage-B telemetry without erasing actual-realized evidence.

    Hard/native integrity and requested-to-realized fidelity are deliberately
    separate.  A fidelity miss blocks requested direction/class/dose labels and
    J-derived interpretation, while structurally sound actual-realized vectors
    remain eligible for explicitly labelled descriptive characterization.
    """

    expected = tuple(
        (
            row["prompt_id"],
            row["assignment_id"],
            row["vector_class"],
            int(row["sign"]),
            float(row["multiplier"]),
        )
        for row in stage_b_rows()
    )
    observed: list[tuple[str, str, str, int, float]] = []
    seen: set[tuple[str, str, str, int, float]] = set()
    hard_failures: list[str] = []
    fidelity_failures: list[str] = []
    fidelity_pass_by_identity: dict[tuple[str, str, str, int, float], bool] = {}
    for offset, row in enumerate(rows):
        _require_exact_fields(row, STAGE_B_EDIT_FIELDS, f"Stage B edit row {offset}")
        sign = row["sign"]
        if isinstance(sign, bool) or not isinstance(sign, int):
            raise ControlViolation("stage_b_edit_grid", "Stage B sign is not an integer")
        multiplier = _require_finite(row["multiplier"], "Stage B multiplier")
        key = (
            str(row["prompt_id"]),
            str(row["assignment_id"]),
            str(row["vector_class"]),
            sign,
            multiplier,
        )
        if key in seen:
            raise ControlViolation("stage_b_edit_grid", f"duplicate Stage B edit row: {key}")
        seen.add(key)
        observed.append(key)
        for field in (
            "requested_vector_sha256",
            "requested_fp32_vector_sha256",
            "realized_vector_sha256",
        ):
            _require_hex64(row[field], f"{key}.{field}")
        requested_fraction = _require_finite(
            row["requested_rms_fraction"], f"{key}.requested_rms_fraction"
        )
        realized_fraction = _require_finite(
            row["realized_rms_fraction"], f"{key}.realized_rms_fraction"
        )
        if (
            row["hook_fire_count"] != HOOK_FIRE_COUNT
            or isinstance(row["hook_fire_count"], bool)
        ):
            hard_failures.append(f"{key}:hook_fire_count")
        for field in (
            "pre_equals_clean",
            "native_post_bytes_exact",
            "upstream_45_49_bytes_equal_clean",
            "finite",
        ):
            if row[field] is not True:
                hard_failures.append(f"{key}:{field}")
        if row["target_prompt_used"] is not False:
            hard_failures.append(f"{key}:target_prompt_used")
        if not 0.0 < requested_fraction <= 0.10:
            hard_failures.append(f"{key}:requested_rms_fraction")
        if not 0.0 < realized_fraction <= 0.10:
            hard_failures.append(f"{key}:realized_rms_fraction")
        fidelity_pass = stage_b_requested_edit_fidelity_pass(row)
        fidelity_pass_by_identity[key] = fidelity_pass
        if not fidelity_pass:
            for rmse_field, cosine_field in STAGE_B_REQUESTED_FIDELITY_METRICS:
                if float(row[rmse_field]) > EDIT_RELATIVE_RMSE_MAX:
                    fidelity_failures.append(f"{key}:{rmse_field}")
                if float(row[cosine_field]) < EDIT_SIGN_COSINE_MIN:
                    fidelity_failures.append(f"{key}:{cosine_field}")
    if tuple(observed) != expected:
        expected_set = set(expected)
        actual_set = set(observed)
        raise ControlViolation(
            "stage_b_edit_grid",
            "Stage B edit inventory/order differs; "
            f"missing={len(expected_set-actual_set)}, extra={len(actual_set-expected_set)}",
        )
    fidelity_pass_count = sum(fidelity_pass_by_identity.values())
    fidelity_failure_count = len(fidelity_pass_by_identity) - fidelity_pass_count
    hard_failed_identities = {failure.rsplit(":", 1)[0] for failure in hard_failures}
    hard_failure_count = len(hard_failed_identities)
    hard_status = "pass" if not hard_failures else "fail"
    fidelity_status = "pass" if not fidelity_failures else "fail"
    return {
        "status": "pass" if hard_status == fidelity_status == "pass" else "fail",
        "actual_realized_integrity_status": hard_status,
        "requested_edit_fidelity_status": fidelity_status,
        "row_count": len(observed),
        "expected_row_count": len(expected),
        "actual_realized_integrity_pass_count": len(observed) - hard_failure_count,
        "actual_realized_integrity_failure_count": hard_failure_count,
        "requested_edit_fidelity_pass_count": fidelity_pass_count,
        "requested_edit_fidelity_failure_count": fidelity_failure_count,
        "requested_realized_relative_rmse_max": EDIT_RELATIVE_RMSE_MAX,
        "requested_realized_cosine_min": EDIT_SIGN_COSINE_MIN,
        "row_identity_set_sha256": canonical_sha256(observed),
        "actual_realized_integrity_failures": hard_failures,
        "requested_edit_fidelity_failures": fidelity_failures,
        "failures": [*hard_failures, *fidelity_failures],
    }


STAGE_B_TRANSPORT_FIELDS = frozenset(
    {
        "prompt_id",
        "assignment_id",
        "vector_class",
        "multiplier",
        "edit_layer",
        "realized_rms_fraction",
        "transport",
        "residual_delta_cosine",
        "fixed_token_logit_delta_pearson",
        "finite",
        "target_prompt_used",
    }
)


def validate_stage_b_transport_rows(
    rows: Iterable[Mapping[str, Any]],
) -> dict[str, Any]:
    """Validate the exact paired SAE-vector layer-50 transport grid."""

    expected = {
        (
            prompt_id,
            assignment["assignment_id"],
            vector_class,
            float(multiplier),
            transport,
        )
        for prompt_id in STAGE_B_PROMPT_IDS
        for assignment in aggregate_assignments()
        for vector_class in ("target", "matched", "isotropic")
        for multiplier in STAGE_B_MULTIPLIERS
        for transport in TRANSPORTS
    }
    indexed: dict[tuple[str, str, str, float, str], Mapping[str, Any]] = {}
    failures: list[str] = []
    for offset, row in enumerate(rows):
        _require_exact_fields(row, STAGE_B_TRANSPORT_FIELDS, f"Stage B transport row {offset}")
        key = (
            str(row["prompt_id"]),
            str(row["assignment_id"]),
            str(row["vector_class"]),
            float(row["multiplier"]),
            str(row["transport"]),
        )
        if key in indexed:
            raise ControlViolation("stage_b_transport_grid", "duplicate Stage B transport row")
        indexed[key] = row
        if int(row["edit_layer"]) != SAE_LAYER:
            failures.append(f"{key}:edit_layer")
        fraction = _require_finite(
            row["realized_rms_fraction"], "Stage B realized RMS fraction"
        )
        if fraction <= 0 or fraction > 0.10:
            failures.append(f"{key}:realized_rms_fraction")
        for metric in ("residual_delta_cosine", "fixed_token_logit_delta_pearson"):
            value = _require_finite(row[metric], f"Stage B {metric}")
            if value < -1 or value > 1:
                failures.append(f"{key}:{metric}")
        if row["finite"] is not True or row["target_prompt_used"] is not False:
            failures.append(f"{key}:integrity")
    actual = set(indexed)
    if actual != expected:
        raise ControlViolation(
            "stage_b_transport_grid",
            f"Stage B transport grid differs: missing={len(expected-actual)}, extra={len(actual-expected)}",
        )
    return {
        "status": "pass" if not failures else "fail",
        "row_count": len(indexed),
        "expected_row_count": len(expected),
        "failures": failures,
    }


STAGE_A_RECEIPT_FIELDS = frozenset(
    {
        "schema_version",
        "status",
        "study_id",
        "protocol_version",
        "run_id",
        "plan_manifest_sha256",
        "raw_run_receipt_sha256",
        "audit_receipt_sha256",
        "stage_a_numeric_recomputation_sha256",
        "storage_budget_receipt_sha256",
        "preexecution_authorization_sha256",
        "smoke_receipt_sha256",
        "smoke_receipt_file_sha256",
        "campaign_identity_sha256",
        "edit_realization_rows_sha256",
        "transport_rows_sha256",
        "linearity_rows_sha256",
        "j_orientation_rows_sha256",
        "j_orientation_receipt_sha256",
        "edit_realization_status",
        "realized_edit_fidelity_status",
        "hard_safety_status",
        "native_post_bytes_status",
        "common_mode_status",
        "collection_safety_status",
        "j_shadow_status",
        "j_shadow_layer_statuses",
        "j_shadow_layer_status_inventory_sha256",
        "layer50_j_shadow_status",
        "j_orientation_status",
        "absolute_real_j_status",
        "real_j_over_identity_status",
        "real_j_over_five_random_status",
        "linearity_status",
        "layer50_primary_transport_status",
        "layer50_linearity_status",
        "layer50_realized_rms_fraction_min",
        "layer50_realized_rms_fraction_max",
        "layer50_envelope_row_count",
        "layer50_envelope_identity_set_sha256",
        "j_orientation_row_count",
        "neutral_prompt_count",
        "realization_pair_row_count",
        "edited_forward_count",
        "transport_row_count",
        "linearity_row_count",
        "captured_j_layer_count",
        "captured_j_layers_sha256",
        "shadow_dtype",
        "model_forward_count",
        "cumulative_elapsed_seconds",
        "cumulative_spend_usd",
        "target_prompt_render_count",
        "target_forward_count",
        "target_outcome_count",
        "prior_outcome_inputs",
        "receipt_sha256",
    }
)


def stage_b_layer50_j_interpretation_gate_pass(
    stage_a_receipt: Mapping[str, Any],
) -> bool:
    """Evaluate only the frozen Stage-B layer-50 J prerequisites.

    The global all-tested-layer J-shadow status is intentionally not a member:
    it controls the full Stage-A scientific verdict, while the layer-50 subset
    controls this narrower Stage-B interpretation.
    """

    fields = (
        "layer50_j_shadow_status",
        "layer50_primary_transport_status",
        "layer50_linearity_status",
    )
    if any(stage_a_receipt.get(field) not in {"pass", "fail"} for field in fields):
        raise ControlViolation(
            "stage_b_layer50_j_gate", "Stage-A layer-50 prerequisite status is invalid"
        )
    return all(stage_a_receipt[field] == "pass" for field in fields)


def validate_stage_a_receipt(receipt: Mapping[str, Any]) -> dict[str, Any]:
    validated = validate_stage_a_safety_receipt(receipt)
    if validated["status"] != "pass":
        raise ControlViolation("stage_a_status", "Stage A did not pass")
    for field in (
        "edit_realization_status",
        "j_shadow_status",
        "layer50_j_shadow_status",
        "j_orientation_status",
        "absolute_real_j_status",
        "real_j_over_identity_status",
        "real_j_over_five_random_status",
        "linearity_status",
        "layer50_primary_transport_status",
        "layer50_linearity_status",
    ):
        if validated[field] != "pass":
            raise ControlViolation("stage_a_status", f"Stage A component failed: {field}")
    return validated


def validate_stage_a_safety_receipt(receipt: Mapping[str, Any]) -> dict[str, Any]:
    """Authorize neutral collection only after the full collection-safety gate.

    Real-J incremental transport and dose-linearity may fail without blocking
    raw neutral Stage-B collection.  J arithmetic/orientation is technical
    safety because Stage B itself emits J-derived rows; it must pass together
    with hook/native/upstream safety, realized-edit fidelity, common-mode
    control, and the exact layer-50 dose-envelope inventory.
    """

    _require_exact_fields(receipt, STAGE_A_RECEIPT_FIELDS, "Stage A safety receipt")
    _validate_identity(receipt, "Stage A safety receipt")
    _validate_self_hash(receipt, "receipt_sha256", "Stage A safety receipt")
    if receipt["schema_version"] != CONTROL_SCHEMA_VERSION:
        raise ControlViolation("stage_a_safety", "Stage A schema differs")
    if receipt["status"] not in {"pass", "fail"}:
        raise ControlViolation("stage_a_safety", "Stage A aggregate status is invalid")
    for field in (
        "plan_manifest_sha256",
        "raw_run_receipt_sha256",
        "audit_receipt_sha256",
        "stage_a_numeric_recomputation_sha256",
        "storage_budget_receipt_sha256",
        "preexecution_authorization_sha256",
        "smoke_receipt_sha256",
        "smoke_receipt_file_sha256",
        "campaign_identity_sha256",
        "edit_realization_rows_sha256",
        "transport_rows_sha256",
        "linearity_rows_sha256",
        "j_orientation_rows_sha256",
        "j_orientation_receipt_sha256",
        "captured_j_layers_sha256",
        "layer50_envelope_identity_set_sha256",
        "j_shadow_layer_status_inventory_sha256",
    ):
        _require_hex64(receipt[field], f"Stage A safety {field}")
    if not isinstance(receipt["run_id"], str) or SAFE_RUN_ID.fullmatch(receipt["run_id"]) is None:
        raise ControlViolation("stage_a_safety", "Stage A run ID is unsafe")
    status_fields = (
        "edit_realization_status",
        "realized_edit_fidelity_status",
        "hard_safety_status",
        "native_post_bytes_status",
        "common_mode_status",
        "collection_safety_status",
        "j_shadow_status",
        "layer50_j_shadow_status",
        "j_orientation_status",
        "absolute_real_j_status",
        "real_j_over_identity_status",
        "real_j_over_five_random_status",
        "linearity_status",
        "layer50_primary_transport_status",
        "layer50_linearity_status",
    )
    if any(receipt[field] not in {"pass", "fail"} for field in status_fields):
        raise ControlViolation("stage_a_safety", "Stage A component status is invalid")
    layer_rows = receipt["j_shadow_layer_statuses"]
    if not isinstance(layer_rows, list) or len(layer_rows) != len(STAGE_A_LAYERS):
        raise ControlViolation("stage_a_j_shadow", "per-layer J-shadow inventory differs")
    gated_row_count = (
        len(STAGE_A_PROMPT_IDS)
        * len(STAGE_A_DIRECTIONS)
        * len(LINEARITY_GATE_DOSES)
    )
    for expected_layer, row in zip(STAGE_A_LAYERS, layer_rows, strict=True):
        _require_exact_fields(
            row,
            frozenset({"edit_layer", "status", "gated_row_count", "failure_count"}),
            f"Stage A layer-{expected_layer} J-shadow status",
        )
        failure_count = _require_nonnegative_int(
            row["failure_count"], f"layer-{expected_layer} J-shadow failures"
        )
        if (
            row["edit_layer"] != expected_layer
            or row["gated_row_count"] != gated_row_count
            or failure_count > gated_row_count * 2
            or row["status"] != ("pass" if failure_count == 0 else "fail")
        ):
            raise ControlViolation(
                "stage_a_j_shadow", f"layer-{expected_layer} J-shadow status differs"
            )
    if receipt["j_shadow_layer_status_inventory_sha256"] != canonical_sha256(layer_rows):
        raise ControlViolation("stage_a_j_shadow", "per-layer J-shadow inventory hash differs")
    expected_global_j_shadow = (
        "pass" if all(row["status"] == "pass" for row in layer_rows) else "fail"
    )
    layer50_status = next(
        row["status"] for row in layer_rows if row["edit_layer"] == SAE_LAYER
    )
    if (
        receipt["j_shadow_status"] != expected_global_j_shadow
        or receipt["layer50_j_shadow_status"] != layer50_status
    ):
        raise ControlViolation(
            "stage_a_j_shadow", "global/layer-50 J-shadow status differs from inventory"
        )
    expected_overall_status = (
        "pass" if all(receipt[field] == "pass" for field in status_fields) else "fail"
    )
    if receipt["status"] != expected_overall_status:
        raise ControlViolation("stage_a_status", "Stage A aggregate/component status differs")
    collection_components = (
        "hard_safety_status",
        "native_post_bytes_status",
        "realized_edit_fidelity_status",
        "common_mode_status",
        "j_orientation_status",
    )
    expected_collection_status = (
        "pass"
        if all(receipt[field] == "pass" for field in collection_components)
        else "fail"
    )
    if (
        receipt["collection_safety_status"] != expected_collection_status
        or expected_collection_status != "pass"
    ):
        raise ControlViolation(
            "stage_a_safety",
            "hook/native, realized-edit fidelity, common-mode, or J orientation safety did not pass",
        )
    expected_pairs = len(_expected_stage_a_edit_keys())
    expected_edits = expected_pairs * 2
    expected_transports = (
        len(STAGE_A_PROMPT_IDS)
        * len(STAGE_A_LAYERS)
        * len(STAGE_A_DIRECTIONS)
        * len(DOSE_GRID)
        * len(TRANSPORTS)
    )
    expected_linearity = (
        len(STAGE_A_PROMPT_IDS) * len(STAGE_A_LAYERS) * len(STAGE_A_DIRECTIONS)
    )
    if (
        receipt["neutral_prompt_count"] != len(STAGE_A_PROMPT_IDS)
        or receipt["realization_pair_row_count"] != expected_pairs
        or receipt["edited_forward_count"] != expected_edits
        or receipt["transport_row_count"] != expected_transports
        or receipt["linearity_row_count"] != expected_linearity
        or receipt["j_orientation_row_count"] != j_orientation.EXPECTED_ROW_COUNT
    ):
        raise ControlViolation("stage_a_safety", "Stage A exact grid count differs")
    if (
        isinstance(receipt["model_forward_count"], bool)
        or not isinstance(receipt["model_forward_count"], int)
        or receipt["model_forward_count"] < expected_edits
    ):
        raise ControlViolation("stage_a_safety", "Stage A total forward count is implausible")
    elapsed = _require_finite(receipt["cumulative_elapsed_seconds"], "Stage A elapsed")
    spend = _require_finite(receipt["cumulative_spend_usd"], "Stage A spend")
    if (
        elapsed < 0
        or elapsed > MAX_WALLTIME_SECONDS
        or spend < 0
        or spend > MAX_INVESTIGATIVE_SPEND_USD
    ):
        raise ControlViolation("stage_a_safety", "Stage A resource meter differs")
    if (
        receipt["captured_j_layer_count"] != J_LAYER_COUNT
        or receipt["captured_j_layers_sha256"] != J_LAYERS_SHA256
        or receipt["shadow_dtype"] != HIGH_PRECISION_SHADOW_DTYPE
    ):
        raise ControlViolation("stage_a_safety", "Stage A J-map inventory differs")
    if (
        receipt["layer50_envelope_row_count"] != LAYER50_ENVELOPE_ROW_COUNT
        or receipt["layer50_envelope_identity_set_sha256"]
        != LAYER50_ENVELOPE_IDENTITY_SET_SHA256
    ):
        raise ControlViolation(
            "stage_a_safety", "exact layer-50 envelope identity inventory differs"
        )
    envelope_min = _require_finite(
        receipt["layer50_realized_rms_fraction_min"], "Stage A safety envelope min"
    )
    envelope_max = _require_finite(
        receipt["layer50_realized_rms_fraction_max"], "Stage A safety envelope max"
    )
    if not (0 < envelope_min < envelope_max <= 0.10):
        raise ControlViolation("stage_a_safety", "layer-50 realized-dose envelope differs")
    if any(
        receipt[field] != 0
        for field in (
            "target_prompt_render_count",
            "target_forward_count",
            "target_outcome_count",
        )
    ) or receipt["prior_outcome_inputs"] != []:
        raise ControlViolation("stage_a_safety", "target/prior input access occurred")
    reject_forbidden_input_references(receipt)
    return dict(receipt)


STAGE_B_PERMIT_FIELDS = frozenset(
    {
        "schema_version",
        "status",
        "study_id",
        "protocol_version",
        "run_id",
        "plan_manifest_sha256",
        "freeze_commit",
        "git_head_commit",
        "git_remote_ref",
        "git_remote_commit",
        "bound_input_paths_sha256",
        "bound_inputs_clean",
        "excluded_worktree_paths",
        "stage_a_receipt_sha256",
        "target_blind_receipt_sha256",
        "storage_budget_receipt_sha256",
        "independent_review_adjudication_sha256",
        "review_status",
        "measured_spend_ceiling_usd",
        "measured_walltime_ceiling_seconds",
        "stage_b_prompt_count",
        "paper_prompt_render_count",
        "target_prompt_render_count",
        "target_forward_count",
        "target_outcome_count",
        "prior_outcome_inputs",
        "receipt_sha256",
    }
)


def validate_stage_b_permit(
    permit: Mapping[str, Any],
    *,
    stage_a_receipt: Mapping[str, Any],
    target_blind_receipt: Mapping[str, Any],
    storage_budget: Mapping[str, Any],
) -> dict[str, Any]:
    """Authorize only the second mundane validation panel, never paper prompts."""

    _require_exact_fields(permit, STAGE_B_PERMIT_FIELDS, "Stage B permit")
    _validate_identity(permit, "Stage B permit")
    _validate_self_hash(permit, "receipt_sha256", "Stage B permit")
    if permit["schema_version"] != CONTROL_SCHEMA_VERSION or permit["status"] != "pass":
        raise ControlViolation("stage_b_permit", "Stage B permit did not pass")
    validated_stage_a = validate_stage_a_safety_receipt(stage_a_receipt)
    validated_target_blind = validate_target_blind_gate_receipt(target_blind_receipt)
    validated_budget = validate_storage_budget(storage_budget)
    for field in (
        "plan_manifest_sha256",
        "stage_a_receipt_sha256",
        "target_blind_receipt_sha256",
        "storage_budget_receipt_sha256",
        "independent_review_adjudication_sha256",
    ):
        _require_hex64(permit[field], f"Stage B permit {field}")
    if not isinstance(permit["run_id"], str) or SAFE_RUN_ID.fullmatch(permit["run_id"]) is None:
        raise ControlViolation("stage_b_permit", "Stage B run ID is unsafe")
    if (
        permit["stage_a_receipt_sha256"] != validated_stage_a["receipt_sha256"]
        or permit["target_blind_receipt_sha256"] != validated_target_blind["receipt_sha256"]
        or permit["storage_budget_receipt_sha256"] != validated_budget["receipt_sha256"]
    ):
        raise ControlViolation("stage_b_binding", "Stage B component receipt hash differs")
    expected_scientific_statuses = {
        "v1_j_arithmetic_orientation": validated_stage_a["j_orientation_status"],
        "v1_stage_a_global_j_shadow": validated_stage_a["j_shadow_status"],
        "v1_layer50_j_shadow": validated_stage_a["layer50_j_shadow_status"],
        "v1_stage_a_neutral_transport": validated_stage_a[
            "layer50_primary_transport_status"
        ],
        "v1_stage_a_neutral_dose_linearity": validated_stage_a[
            "layer50_linearity_status"
        ],
    }
    expected_scientific_hashes = {
        "v1_j_arithmetic_orientation": validated_stage_a[
            "j_orientation_receipt_sha256"
        ],
        "v1_stage_a_global_j_shadow": validated_stage_a["receipt_sha256"],
        "v1_layer50_j_shadow": validated_stage_a["receipt_sha256"],
        "v1_stage_a_neutral_transport": validated_stage_a["receipt_sha256"],
        "v1_stage_a_neutral_dose_linearity": validated_stage_a["receipt_sha256"],
    }
    if (
        validated_target_blind["scientific_gate_statuses"]
        != expected_scientific_statuses
        or validated_target_blind["scientific_gate_receipt_sha256s"]
        != expected_scientific_hashes
    ):
        raise ControlViolation(
            "stage_b_binding", "target-blind scientific gate evidence differs"
        )
    plan_hash = permit["plan_manifest_sha256"]
    if any(
        component["plan_manifest_sha256"] != plan_hash
        for component in (validated_stage_a, validated_target_blind, validated_budget)
    ):
        raise ControlViolation("stage_b_binding", "Stage B plan binding differs")
    for field in ("freeze_commit", "git_head_commit", "git_remote_commit"):
        if not isinstance(permit[field], str) or HEX40.fullmatch(permit[field]) is None:
            raise ControlViolation("stage_b_freeze", f"invalid commit binding: {field}")
    if not (
        permit["freeze_commit"]
        == permit["git_head_commit"]
        == permit["git_remote_commit"]
    ) or permit["bound_inputs_clean"] is not True:
        raise ControlViolation("stage_b_freeze", "freeze/head/remote or bound-input gate failed")
    remote_ref = permit["git_remote_ref"]
    if (
        not isinstance(remote_ref, str)
        or not remote_ref.startswith("origin/")
        or ".." in remote_ref
        or re.fullmatch(r"origin/[A-Za-z0-9._/-]+", remote_ref) is None
    ):
        raise ControlViolation("stage_b_freeze", "remote ref is unsafe")
    _require_hex64(permit["bound_input_paths_sha256"], "bound input path inventory")
    excluded = permit["excluded_worktree_paths"]
    if not isinstance(excluded, list) or any(
        not isinstance(path, str) or not path or path.startswith("/") or ".." in PurePosixPath(path).parts
        for path in excluded
    ):
        raise ControlViolation("stage_b_freeze", "excluded worktree path inventory is invalid")
    spend = _require_finite(permit["measured_spend_ceiling_usd"], "Stage B spend")
    walltime = _require_nonnegative_int(
        permit["measured_walltime_ceiling_seconds"], "Stage B walltime"
    )
    if spend < 0 or spend > MAX_INVESTIGATIVE_SPEND_USD:
        raise ControlViolation("stage_b_resource", "Stage B spend exceeds authorization")
    if walltime <= 0 or walltime > MAX_WALLTIME_SECONDS:
        raise ControlViolation("stage_b_resource", "Stage B walltime exceeds authorization")
    if permit["review_status"] not in {
        "adjudicated_pass",
        "attempted_incomplete",
    }:
        raise ControlViolation(
            "stage_b_review",
            "advisory evidence is neither adjudicated nor a verified incomplete attempt",
        )
    if permit["stage_b_prompt_count"] != len(STAGE_B_PROMPT_IDS):
        raise ControlViolation("stage_b_count", "Stage B prompt count differs")
    for field in (
        "paper_prompt_render_count",
        "target_prompt_render_count",
        "target_forward_count",
        "target_outcome_count",
    ):
        if _require_nonnegative_int(permit[field], f"Stage B {field}") != 0:
            raise ControlViolation("stage_b_target", "Stage B permit contains target access")
    if permit["prior_outcome_inputs"] != []:
        raise ControlViolation("stage_b_prior", "Stage B permit contains prior outcomes")
    input_surface = dict(permit)
    # These paths are attested specifically as outside the bound execution
    # surface; their names cannot become experimental inputs.
    input_surface["excluded_worktree_paths"] = []
    reject_forbidden_input_references(input_surface)
    return dict(permit)


REPLAY_EQUIVALENCE_FIELDS = frozenset(
    {
        "schema_version",
        "status",
        "study_id",
        "protocol_version",
        "run_id",
        "plan_manifest_sha256",
        "raw_archive_manifest_sha256",
        "source_state_index_sha256",
        "j_lens_sha256",
        "final_norm_sha256",
        "lm_head_sha256",
        "tokenizer_binding_sha256",
        "replayed_state_count",
        "missing_state_count",
        "mismatch_count",
        "maximum_selected_logit_absolute_error",
        "selected_logit_absolute_tolerance",
        "full_vocabulary_replayable",
        "arbitrary_top_k_replayable",
        "browse_index_top_k",
        "target_prompt_render_count",
        "target_forward_count",
        "target_outcome_count",
        "prior_outcome_inputs",
        "receipt_sha256",
    }
)


def validate_replay_equivalence_receipt(receipt: Mapping[str, Any]) -> dict[str, Any]:
    """Require raw-residual replay before the archive may be called complete."""

    _require_exact_fields(receipt, REPLAY_EQUIVALENCE_FIELDS, "replay equivalence")
    _validate_identity(receipt, "replay equivalence")
    _validate_self_hash(receipt, "receipt_sha256", "replay equivalence")
    if receipt["schema_version"] != CONTROL_SCHEMA_VERSION or receipt["status"] != "pass":
        raise ControlViolation("replay_status", "replay equivalence did not pass")
    for field in (
        "plan_manifest_sha256",
        "raw_archive_manifest_sha256",
        "source_state_index_sha256",
        "j_lens_sha256",
        "final_norm_sha256",
        "lm_head_sha256",
        "tokenizer_binding_sha256",
    ):
        _require_hex64(receipt[field], f"replay {field}")
    if not isinstance(receipt["run_id"], str) or SAFE_RUN_ID.fullmatch(receipt["run_id"]) is None:
        raise ControlViolation("replay_run", "replay run ID is unsafe")
    if _require_positive_int(receipt["replayed_state_count"], "replayed states") <= 0:
        raise ControlViolation("replay_count", "no states were replayed")
    if receipt["missing_state_count"] != 0 or receipt["mismatch_count"] != 0:
        raise ControlViolation("replay_count", "replay has missing or mismatched states")
    observed = _require_finite(
        receipt["maximum_selected_logit_absolute_error"], "replay maximum error"
    )
    tolerance = _require_finite(
        receipt["selected_logit_absolute_tolerance"], "replay tolerance"
    )
    if tolerance < 0 or observed < 0 or observed > tolerance:
        raise ControlViolation("replay_error", "replay error exceeds frozen tolerance")
    if (
        receipt["full_vocabulary_replayable"] is not True
        or receipt["arbitrary_top_k_replayable"] is not True
        or receipt["browse_index_top_k"] != 2_000
    ):
        raise ControlViolation("replay_scope", "archive cannot support promised vocabulary replay")
    for field in (
        "target_prompt_render_count",
        "target_forward_count",
        "target_outcome_count",
    ):
        if _require_nonnegative_int(receipt[field], f"replay {field}") != 0:
            raise ControlViolation("replay_target", "replay receipt contains target access")
    if receipt["prior_outcome_inputs"] != []:
        raise ControlViolation("replay_prior", "replay used prior outcomes")
    reject_forbidden_input_references(receipt)
    return dict(receipt)


ANALYSIS_FILE_FIELDS = frozenset(
    {
        "artifact_id",
        "relative_path",
        "byte_count",
        "sha256",
        "logical_rows_sha256",
        "row_count",
        "schema_sha256",
        "run_id",
        "transaction_manifest_sha256",
    }
)

STRUCTURAL_AUDIT_FIELDS = frozenset(
    {
        "schema_version",
        "status",
        "study_id",
        "protocol_version",
        "run_id",
        "plan_manifest_sha256",
        "freeze_commit",
        "stage_b_permit_sha256",
        "storage_ledger_sha256",
        "replay_equivalence_receipt_sha256",
        "expected_artifact_id_set_sha256",
        "observed_artifact_id_set_sha256",
        "artifact_files",
        "missing_count",
        "extra_count",
        "duplicate_count",
        "nonfinite_count",
        "partial_path_count",
        "unmanifested_input_count",
        "target_prompt_render_count",
        "target_forward_count",
        "target_outcome_count",
        "prior_outcome_inputs",
        "receipt_sha256",
    }
)


def _validate_analysis_files(
    records: Any, *, run_id: str
) -> dict[str, dict[str, Any]]:
    if not isinstance(records, list):
        raise ControlViolation("analysis_files", "analysis file records are not a list")
    indexed: dict[str, dict[str, Any]] = {}
    paths: set[str] = set()
    for offset, record in enumerate(records):
        _require_exact_fields(record, ANALYSIS_FILE_FIELDS, f"analysis file {offset}")
        artifact_id = record["artifact_id"]
        if artifact_id not in ANALYSIS_ARTIFACT_IDS or artifact_id in indexed:
            raise ControlViolation("analysis_files", "analysis artifact ID is invalid/duplicated")
        relative = record["relative_path"]
        if not isinstance(relative, str):
            raise ControlViolation("analysis_files", "analysis path is not text")
        _reject_unsafe_path_text(relative, "analysis file")
        pure = PurePosixPath(relative)
        if pure.is_absolute() or not pure.parts or pure.parts[0] != "raw" or str(pure) != relative:
            raise ControlViolation("analysis_files", "analysis path is not canonical raw-relative")
        if relative in paths or ".partial" in pure.parts:
            raise ControlViolation("analysis_files", "analysis path is duplicate or partial")
        paths.add(relative)
        if record["run_id"] != run_id:
            raise ControlViolation("analysis_files", "analysis file run binding differs")
        for field in (
            "sha256",
            "logical_rows_sha256",
            "schema_sha256",
            "transaction_manifest_sha256",
        ):
            _require_hex64(record[field], f"analysis file {artifact_id}.{field}")
        _require_nonnegative_int(record["byte_count"], f"analysis file {artifact_id}.bytes")
        _require_nonnegative_int(record["row_count"], f"analysis file {artifact_id}.rows")
        indexed[artifact_id] = dict(record)
    if tuple(record["artifact_id"] for record in records) != ANALYSIS_ARTIFACT_IDS:
        raise ControlViolation("analysis_files", "analysis artifact inventory/order differs")
    return indexed


def validate_structural_audit_receipt(receipt: Mapping[str, Any]) -> dict[str, Any]:
    """Validate structure and lineage without evaluating scientific claims."""

    _require_exact_fields(receipt, STRUCTURAL_AUDIT_FIELDS, "structural audit")
    _validate_identity(receipt, "structural audit")
    _validate_self_hash(receipt, "receipt_sha256", "structural audit")
    if receipt["schema_version"] != CONTROL_SCHEMA_VERSION or receipt["status"] != "pass":
        raise ControlViolation("structural_status", "structural audit did not pass")
    if not isinstance(receipt["run_id"], str) or SAFE_RUN_ID.fullmatch(receipt["run_id"]) is None:
        raise ControlViolation("structural_run", "structural run ID is unsafe")
    for field in (
        "plan_manifest_sha256",
        "stage_b_permit_sha256",
        "storage_ledger_sha256",
        "replay_equivalence_receipt_sha256",
        "expected_artifact_id_set_sha256",
        "observed_artifact_id_set_sha256",
    ):
        _require_hex64(receipt[field], f"structural {field}")
    if not isinstance(receipt["freeze_commit"], str) or HEX40.fullmatch(receipt["freeze_commit"]) is None:
        raise ControlViolation("structural_freeze", "structural freeze commit is invalid")
    expected_set_hash = canonical_sha256(sorted(ANALYSIS_ARTIFACT_IDS))
    if (
        receipt["expected_artifact_id_set_sha256"] != expected_set_hash
        or receipt["observed_artifact_id_set_sha256"] != expected_set_hash
    ):
        raise ControlViolation("structural_inventory", "artifact set hash differs")
    _validate_analysis_files(receipt["artifact_files"], run_id=receipt["run_id"])
    for field in (
        "missing_count",
        "extra_count",
        "duplicate_count",
        "nonfinite_count",
        "partial_path_count",
        "unmanifested_input_count",
        "target_prompt_render_count",
        "target_forward_count",
        "target_outcome_count",
    ):
        if _require_nonnegative_int(receipt[field], f"structural {field}") != 0:
            raise ControlViolation("structural_count", f"nonzero structural count: {field}")
    if receipt["prior_outcome_inputs"] != []:
        raise ControlViolation("structural_prior", "structural audit used prior outcomes")
    reject_forbidden_input_references(receipt)
    return dict(receipt)


ANALYSIS_AUTHORIZATION_FIELDS = frozenset(
    {
        "schema_version",
        "authorization_kind",
        "status",
        "study_id",
        "protocol_version",
        "run_id",
        "plan_manifest_sha256",
        "analysis_plan_sha256",
        "freeze_commit",
        "stage_b_permit_sha256",
        "storage_ledger_sha256",
        "replay_equivalence_receipt_sha256",
        "structural_audit_receipt_sha256",
        "artifact_files",
        "prior_outcome_inputs",
        "unmanifested_outcome_inputs",
        "forbidden_input_accesses",
        "receipt_sha256",
    }
)


def validate_analysis_authorization(
    authorization: Mapping[str, Any], *, structural_audit: Mapping[str, Any]
) -> dict[str, Any]:
    """Validate the positive-only authorization before resolving any raw path."""

    _require_exact_fields(
        authorization, ANALYSIS_AUTHORIZATION_FIELDS, "analysis authorization"
    )
    _validate_identity(authorization, "analysis authorization")
    _validate_self_hash(authorization, "receipt_sha256", "analysis authorization")
    if (
        authorization["schema_version"] != CONTROL_SCHEMA_VERSION
        or authorization["authorization_kind"]
        != "consciousness_sae_realization_validation_v1_analysis_authorization"
        or authorization["status"] != "authorized"
    ):
        raise ControlViolation("analysis_authorization", "analysis is not positively authorized")
    audit = validate_structural_audit_receipt(structural_audit)
    for field in (
        "plan_manifest_sha256",
        "analysis_plan_sha256",
        "stage_b_permit_sha256",
        "storage_ledger_sha256",
        "replay_equivalence_receipt_sha256",
        "structural_audit_receipt_sha256",
    ):
        _require_hex64(authorization[field], f"analysis authorization {field}")
    if authorization["structural_audit_receipt_sha256"] != audit["receipt_sha256"]:
        raise ControlViolation("analysis_binding", "structural audit hash differs")
    for field in (
        "run_id",
        "plan_manifest_sha256",
        "freeze_commit",
        "stage_b_permit_sha256",
        "storage_ledger_sha256",
        "replay_equivalence_receipt_sha256",
    ):
        if authorization[field] != audit[field]:
            raise ControlViolation("analysis_binding", f"analysis binding differs: {field}")
    authorized_files = _validate_analysis_files(
        authorization["artifact_files"], run_id=authorization["run_id"]
    )
    audited_files = _validate_analysis_files(audit["artifact_files"], run_id=audit["run_id"])
    if authorized_files != audited_files:
        raise ControlViolation("analysis_binding", "authorized files differ from audited files")
    for field in (
        "prior_outcome_inputs",
        "unmanifested_outcome_inputs",
        "forbidden_input_accesses",
    ):
        if authorization[field] != []:
            raise ControlViolation("analysis_inputs", f"analysis has forbidden inputs: {field}")
    reject_forbidden_input_references(authorization)
    return dict(authorization)


def open_authorized_analysis_files(
    authorization: Mapping[str, Any],
    *,
    structural_audit: Mapping[str, Any],
    raw_run_root: Path,
) -> dict[str, Path]:
    """Resolve and rehash only after positive authorization validates."""

    validated = validate_analysis_authorization(
        authorization, structural_audit=structural_audit
    )
    _reject_unsafe_path_text(str(raw_run_root), "raw run root")
    lexical_root = raw_run_root.absolute()
    _require_symlink_free_components(lexical_root, "raw run root")
    root = lexical_root.resolve(strict=True)
    if not root.is_dir() or root.name != validated["run_id"]:
        raise ControlViolation("analysis_root", "analysis run root differs")
    if tuple(root.parent.parts[-3:]) != (STUDY_SLUG, STUDY_ID, "raw"):
        raise ControlViolation("analysis_root", "analysis root is outside validation raw namespace")
    opened: dict[str, Path] = {}
    for record in validated["artifact_files"]:
        relative = PurePosixPath(record["relative_path"])
        # The record is raw-relative while raw_run_root already denotes raw/<run_id>.
        parts = relative.parts[1:]
        candidate_lexical = root.joinpath(*parts)
        _require_symlink_free_components(candidate_lexical, "authorized analysis file")
        candidate = candidate_lexical.resolve(strict=True)
        try:
            candidate.relative_to(root)
        except ValueError as exc:
            raise ControlViolation("analysis_path", "analysis file escaped run root") from exc
        if not candidate.is_file() or candidate.stat().st_nlink != 1:
            raise ControlViolation("analysis_path", "analysis file is not a unique regular file")
        if candidate.stat().st_size != record["byte_count"] or sha256_file(candidate) != record["sha256"]:
            raise ControlViolation("analysis_hash", "analysis file bytes/hash differ")
        opened[record["artifact_id"]] = candidate
    return opened

#!/usr/bin/env python3
"""Sealed, model-facing executor for the consciousness-SAE changepoint study.

The executor is intentionally split into four explicit phases.  The first
target prompt cannot be rendered until a passing OSF registration receipt and
an equal local/remote pre-prefix freeze receipt have been validated.  Target
branches additionally require the content-free prefix-bank receipt and the
second equal local/remote freeze that binds that receipt.

Raw prompt text, generated text, token IDs, residuals, and model readouts are
written only below the verified external artifact root.  Standard output is a
small allowlisted status record; it never contains model text or token IDs.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import random
import re
import sys
import time
from collections import Counter, defaultdict
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Iterable, Mapping, Sequence


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from experiments.consciousness_sae_changepoint import benchmark, paths, readouts  # noqa: E402
from experiments.consciousness_sae_changepoint.calibrate import (  # noqa: E402
    validate_artifact_receipt,
    validate_calibration_receipt,
)
from experiments.consciousness_sae_changepoint.protocol import (  # noqa: E402
    ACTIVE_PROBE_EVENT_TIMES,
    BINARY_QUERY_SHA256,
    CAPTURE_STATES,
    FIXED_TOKEN_CONDITIONS,
    JLENS_FILE_SHA256,
    JLENS_FILENAME,
    JLENS_ID,
    JLENS_REVISION,
    MAIN_BRANCHES,
    MAIN_POST_EVENT_TOKENS,
    MODEL_DTYPE,
    MODEL_ID,
    MODEL_LAYERS,
    MODEL_REVISION,
    MODEL_WIDTH,
    N_PREFIXES,
    PREFIX_TOKENS,
    PROBE_EVENT_TIMES,
    PROTOCOL_VERSION,
    QUERY_ANSWER_MAX_TOKENS,
    SAE_FILE_SHA256,
    SAE_FILENAME,
    SAE_ID,
    SAE_LAYER,
    SAE_REVISION,
    SAE_WIDTH,
    SELF_REFERENCE_PROMPT,
    SELF_REFERENCE_PROMPT_SHA256,
    STUDY_ID,
    TARGET_FEATURE_IDS,
    TEMPERATURE,
    TOKENIZER_SIZE,
    TOP_K,
    TOP_P,
    canonical_json_bytes,
    sampling_domain_hash,
    sha256_file,
    sha256_text,
    stable_id,
)
from experiments.consciousness_sae_changepoint.runtime_core import (  # noqa: E402
    Layer50SwitchHook,
    RuntimeContractError,
    cache_tensor_sha256,
    clone_kv_cache,
    extract_hidden_output,
    extract_residual_positions,
    inverse_cdf_sample,
    hash_uniform_receipt,
    resolve_probe_event_times,
    tensor_sha256,
)
from experiments.consciousness_sae_changepoint.storage import (  # noqa: E402
    BLOCK_MANIFEST,
    COMPLETE_MARKER,
    BlockTransaction,
    RunTransaction,
    atomic_write_json,
    validate_relative_path,
    verify_completed_block,
    verify_completed_run,
)
from experiments.consciousness_sae_changepoint.validate_plan import (  # noqa: E402
    validate as validate_plan,
)
from src.prompts import BINARY_CONSCIOUS_QUERY  # noqa: E402


RUN_SCHEMA_VERSION = 1
REGISTRATION_SCHEMA_VERSION = 1
FREEZE_SCHEMA_VERSION = 1
PREFIX_RECEIPT_SCHEMA_VERSION = 1
ACCEPTANCE_SCHEMA_VERSION = 1
MIN_COMPLETE_PREFIXES = 152
MAX_GATE_FILE_BYTES = 32 * 1024**2
MAX_SOURCE_ROWS_PER_SHARD = benchmark.SOURCE_SHARD_ROWS
GIT_SHA = re.compile(r"^[0-9a-f]{40}(?:[0-9a-f]{24})?$")
HEX64 = re.compile(r"^[0-9a-f]{64}$")
OSF_ID = re.compile(r"^[a-z0-9]{4,12}$")
SAFE_RUN_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{2,127}$")
REQUIRED_TARGET_BLIND_GATES = (
    "cached_clean_equivalence",
    "fork_identity",
    "first_affected_distribution",
    "mask_contracts",
    "j_readout_algebra",
    "paired_rng",
    "order_resume_replay",
    "semantic_positive_control",
    "neutral_panel",
    "intervention_vector_inventory",
    "power_operating_characteristics",
    "measured_benchmark",
    "independent_plan_review",
    "judge_definition_frozen",
)
VECTOR_INVENTORY_VALIDATOR_ID = "intervention_vector_inventory_v1"

RAW_OUTPUT_KEYS = frozenset(
    {
        "text",
        "prompt",
        "prompt_text",
        "token_ids",
        "input_ids",
        "prefix_token_ids",
        "continuation_token_ids",
        "answer_token_ids",
        "raw_text",
        "decoded",
        "residuals",
        "logits",
    }
)


class SealedExecutionError(RuntimeError):
    """Fail-closed execution error with a content-free public code."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(detail)
        self.code = code


class GateValidationError(SealedExecutionError):
    """A prospective registration, freeze, or receipt gate did not pass."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_json(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def paired_rng_context_sha256(
    *, prefix_seed: int, stream_id: str, decode_step: int
) -> str:
    """Bind a trace row to the exact deterministic sampling coordinate."""

    return sha256_json(
        {
            "sampling_domain_hash": sampling_domain_hash(),
            "prefix_seed": int(prefix_seed),
            "paired_stream_id": str(stream_id),
            "decode_step": int(decode_step),
            "temperature": TEMPERATURE,
            "top_p": TOP_P,
            "top_k": TOP_K,
        }
    )


def embedded_receipt_sha256(receipt: Mapping[str, Any]) -> str:
    payload = dict(receipt)
    payload.pop("receipt_sha256", None)
    return sha256_json(payload)


def _require_embedded_hash(receipt: Mapping[str, Any], *, label: str) -> str:
    observed = receipt.get("receipt_sha256")
    if not isinstance(observed, str) or not HEX64.fullmatch(observed):
        raise GateValidationError("gate_hash_missing", f"{label} lacks receipt_sha256")
    if embedded_receipt_sha256(receipt) != observed:
        raise GateValidationError("gate_hash_mismatch", f"{label} canonical hash differs")
    return observed


def _parse_utc(value: Any, *, label: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise GateValidationError("gate_timestamp_missing", f"{label} is missing")
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise GateValidationError("gate_timestamp_invalid", f"{label} is invalid") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise GateValidationError("gate_timestamp_unzoned", f"{label} must include UTC offset")
    return parsed.astimezone(timezone.utc)


def load_json_receipt(path: Path, *, label: str) -> dict[str, Any]:
    expanded = path.expanduser()
    if expanded.is_symlink():
        raise GateValidationError("gate_file_symlink", f"{label} may not be a symlink")
    resolved = expanded.resolve(strict=True)
    if not resolved.is_file():
        raise GateValidationError("gate_file_invalid", f"{label} is not a regular file")
    if resolved.stat().st_size > MAX_GATE_FILE_BYTES:
        raise GateValidationError("gate_file_oversize", f"{label} exceeds the gate size limit")
    try:
        payload = json.loads(resolved.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise GateValidationError("gate_json_invalid", f"{label} is invalid JSON") from exc
    if not isinstance(payload, dict):
        raise GateValidationError("gate_json_not_object", f"{label} must be a JSON object")
    return payload


def validate_registration_receipt(
    receipt: Mapping[str, Any],
    *,
    plan_hash: str,
    plan_manifest_sha256: str,
    pre_prefix_freeze_sha: str,
    acceptance_receipt_sha256: str,
) -> dict[str, Any]:
    """Validate an immutable OSF registration binding before target rendering."""

    if receipt.get("schema_version") != REGISTRATION_SCHEMA_VERSION:
        raise GateValidationError("registration_schema", "registration schema differs")
    if receipt.get("status") != "registered" or receipt.get("study_id") != STUDY_ID:
        raise GateValidationError("registration_status", "OSF registration is not accepted")
    if receipt.get("provider") != "osf":
        raise GateValidationError("registration_provider", "registration provider must be osf")
    registration_id = receipt.get("registration_id")
    if not isinstance(registration_id, str) or not OSF_ID.fullmatch(registration_id):
        raise GateValidationError("registration_id", "OSF registration ID is invalid")
    registered_at = _parse_utc(receipt.get("registered_at_utc"), label="registered_at_utc")
    if registered_at > datetime.now(timezone.utc):
        raise GateValidationError("registration_future", "OSF timestamp lies in the future")
    if receipt.get("plan_hash") != plan_hash:
        raise GateValidationError("registration_plan", "registration plan hash differs")
    if receipt.get("plan_manifest_sha256") != plan_manifest_sha256:
        raise GateValidationError("registration_manifest", "registration manifest hash differs")
    if receipt.get("pre_prefix_freeze_sha") != pre_prefix_freeze_sha:
        raise GateValidationError("registration_commit", "registered freeze SHA differs")
    if receipt.get("acceptance_receipt_sha256") != acceptance_receipt_sha256:
        raise GateValidationError(
            "registration_acceptance", "registered acceptance manifest differs"
        )
    url = receipt.get("registration_url")
    if not isinstance(url, str) or not url.startswith(f"https://osf.io/{registration_id}"):
        raise GateValidationError("registration_url", "OSF registration URL differs")
    receipt_hash = _require_embedded_hash(receipt, label="registration receipt")
    return {
        "registration_id": registration_id,
        "registered_at_utc": registered_at.isoformat(),
        "receipt_sha256": receipt_hash,
    }


def validate_freeze_receipt(
    receipt: Mapping[str, Any],
    *,
    freeze_kind: str,
    plan_hash: str,
    expected_pre_prefix_sha: str | None = None,
    expected_prefix_receipt_sha256: str | None = None,
    expected_acceptance_receipt_sha256: str | None = None,
) -> dict[str, Any]:
    """Require a pushed, equal local/remote commit and its exact bindings."""

    if receipt.get("schema_version") != FREEZE_SCHEMA_VERSION:
        raise GateValidationError("freeze_schema", "freeze receipt schema differs")
    if receipt.get("status") != "pass" or receipt.get("study_id") != STUDY_ID:
        raise GateValidationError("freeze_status", "freeze receipt does not pass")
    if receipt.get("freeze_kind") != freeze_kind:
        raise GateValidationError("freeze_kind", "freeze receipt kind differs")
    local_sha = receipt.get("local_commit_sha")
    remote_sha = receipt.get("remote_commit_sha")
    if not isinstance(local_sha, str) or not GIT_SHA.fullmatch(local_sha):
        raise GateValidationError("freeze_local_sha", "local freeze SHA is invalid")
    if remote_sha != local_sha:
        raise GateValidationError("freeze_remote_sha", "local and remote SHAs are unequal")
    if receipt.get("pushed") is not True or receipt.get("tracked_tree_clean") is not True:
        raise GateValidationError("freeze_not_pushed", "freeze is not a clean pushed commit")
    if receipt.get("plan_hash") != plan_hash:
        raise GateValidationError("freeze_plan", "freeze plan hash differs")
    if expected_acceptance_receipt_sha256 is not None and receipt.get(
        "acceptance_receipt_sha256"
    ) != expected_acceptance_receipt_sha256:
        raise GateValidationError(
            "freeze_acceptance", "freeze acceptance-manifest binding differs"
        )
    if expected_pre_prefix_sha is not None and receipt.get("pre_prefix_freeze_sha") != expected_pre_prefix_sha:
        raise GateValidationError("freeze_pre_prefix", "pre-prefix freeze binding differs")
    if freeze_kind == "prefix_receipt" and expected_pre_prefix_sha == local_sha:
        raise GateValidationError(
            "freeze_prefix_commit_not_new",
            "prefix realization receipt must be frozen in a second commit",
        )
    if expected_prefix_receipt_sha256 is not None and receipt.get(
        "prefix_receipt_sha256"
    ) != expected_prefix_receipt_sha256:
        raise GateValidationError("freeze_prefix_receipt", "prefix receipt binding differs")
    _parse_utc(receipt.get("verified_at_utc"), label="verified_at_utc")
    receipt_hash = _require_embedded_hash(receipt, label=f"{freeze_kind} freeze receipt")
    return {"commit_sha": local_sha, "receipt_sha256": receipt_hash}


def validate_prefix_bank_receipt(
    receipt: Mapping[str, Any],
    *,
    plan_hash: str,
    pre_prefix_freeze_sha: str,
    registration_id: str,
) -> dict[str, Any]:
    """Validate the compact, content-free automatic realization receipt."""

    if receipt.get("schema_version") != PREFIX_RECEIPT_SCHEMA_VERSION:
        raise GateValidationError("prefix_receipt_schema", "prefix receipt schema differs")
    if receipt.get("status") != "pass" or receipt.get("study_id") != STUDY_ID:
        raise GateValidationError("prefix_receipt_status", "prefix receipt does not pass")
    if receipt.get("automatic_receipt") is not True or receipt.get("content_included") is not False:
        raise GateValidationError("prefix_receipt_content", "prefix receipt is not content-free")
    if receipt.get("design_changes") not in ([], False):
        raise GateValidationError("prefix_receipt_changes", "prefix realization changed the design")
    if receipt.get("plan_hash") != plan_hash:
        raise GateValidationError("prefix_receipt_plan", "prefix receipt plan hash differs")
    if receipt.get("pre_prefix_freeze_sha") != pre_prefix_freeze_sha:
        raise GateValidationError("prefix_receipt_freeze", "prefix receipt freeze differs")
    if receipt.get("registration_id") != registration_id:
        raise GateValidationError("prefix_receipt_registration", "prefix receipt OSF ID differs")
    if receipt.get("sampling_domain_hash") != sampling_domain_hash():
        raise GateValidationError("prefix_receipt_sampling", "sampling domain differs")
    planned = receipt.get("planned_prefixes")
    success = receipt.get("successful_prefixes")
    failed = receipt.get("failed_prefixes")
    if planned != N_PREFIXES or not all(isinstance(value, int) for value in (success, failed)):
        raise GateValidationError("prefix_receipt_counts", "prefix counts are invalid")
    if success + failed != N_PREFIXES or success < MIN_COMPLETE_PREFIXES:
        raise GateValidationError("prefix_receipt_threshold", "prefix success threshold failed")
    failure_codes = receipt.get("failure_code_counts")
    if not isinstance(failure_codes, dict) or any(
        not isinstance(key, str) or not isinstance(value, int) or value < 0
        for key, value in failure_codes.items()
    ):
        raise GateValidationError("prefix_receipt_failures", "failure-code counts are invalid")
    manifest_hash = receipt.get("prefix_bank_manifest_sha256")
    if not isinstance(manifest_hash, str) or not HEX64.fullmatch(manifest_hash):
        raise GateValidationError("prefix_receipt_manifest", "prefix manifest hash is invalid")
    run_id = receipt.get("prefix_bank_run_id")
    if not isinstance(run_id, str) or not SAFE_RUN_ID.fullmatch(run_id):
        raise GateValidationError("prefix_receipt_run", "prefix run ID is invalid")
    receipt_hash = _require_embedded_hash(receipt, label="prefix-bank receipt")
    return {
        "receipt_sha256": receipt_hash,
        "prefix_bank_manifest_sha256": manifest_hash,
        "prefix_bank_run_id": run_id,
        "successful_prefixes": success,
    }


@dataclass(frozen=True)
class GateValidationContext:
    plan_hash: str
    artifact_receipt_sha256: str
    calibration_receipt_sha256: str
    artifact_root: Path


@dataclass(frozen=True)
class GateValidatorSpec:
    gate_id: str
    validator_id: str
    source_relative_path: str
    validate: Callable[[Mapping[str, Any], GateValidationContext], Mapping[str, Any]]


@dataclass(frozen=True)
class AcceptanceValidation:
    receipt_sha256: str
    gate_receipt_sha256: Mapping[str, str]
    vector_inventory: Mapping[str, Any]


def vector_condition_key(aggregate_block_id: str, condition_name: str) -> str:
    return stable_id(
        "intervention-vector", aggregate_block_id, condition_name, length=32
    )


def validate_intervention_vector_inventory_gate(
    receipt: Mapping[str, Any], context: GateValidationContext
) -> Mapping[str, Any]:
    """Validate the exact 50-block by 12-condition vector receipt schema."""

    del context
    if receipt.get("gate_schema_version") != 1:
        raise GateValidationError("vector_gate_schema", "vector gate schema differs")
    if receipt.get("gate_id") != "intervention_vector_inventory":
        raise GateValidationError("vector_gate_id", "vector gate ID differs")
    if receipt.get("algorithm") != (
        "numpy.PCG64/default_rng float32 unit vector scaled to the BF16 "
        "target-aggregate L2 norm, signed, then cast to BF16"
    ):
        raise GateValidationError("vector_gate_algorithm", "vector algorithm differs")
    rows = receipt.get("rows")
    if not isinstance(rows, list) or len(rows) != 600:
        raise GateValidationError("vector_gate_rows", "vector inventory must have 600 rows")
    expected_conditions = set(FIXED_TOKEN_CONDITIONS) - {"clean"}
    seen_keys: set[str] = set()
    block_counts: Counter[str] = Counter()
    condition_counts: Counter[str] = Counter()
    normalized: list[dict[str, Any]] = []
    exact_fields = {
        "condition_key",
        "aggregate_block_id",
        "condition_name",
        "intervention_role",
        "dose_scale",
        "sign",
        "requested_coefficients",
        "vector_dtype",
        "vector_sha256",
        "vector_l2_norm",
        "vector_rms",
    }
    for raw in rows:
        if not isinstance(raw, dict) or set(raw) != exact_fields:
            raise GateValidationError("vector_gate_fields", "vector row fields differ")
        block_id = str(raw["aggregate_block_id"])
        condition_name = str(raw["condition_name"])
        key = str(raw["condition_key"])
        if not re.fullmatch(r"aggregate-[0-9]{3}", block_id):
            raise GateValidationError("vector_gate_block", "aggregate block ID is invalid")
        if condition_name not in expected_conditions:
            raise GateValidationError("vector_gate_condition", "vector condition is invalid")
        if key != vector_condition_key(block_id, condition_name) or key in seen_keys:
            raise GateValidationError("vector_gate_key", "vector condition key differs")
        seen_keys.add(key)
        calibrated = condition_name.endswith("_calibrated")
        base = condition_name.removesuffix("_calibrated")
        expected_sign = -1 if base.endswith("_supp") else 1
        expected_role = (
            "target_sae"
            if base.startswith("target_")
            else "matched_sae"
            if base.startswith("matched_")
            else "isotropic_residual"
        )
        expected_dose = "calibrated_sensitivity" if calibrated else "literal"
        if (
            raw["sign"] != expected_sign
            or raw["intervention_role"] != expected_role
            or raw["dose_scale"] != expected_dose
            or raw["vector_dtype"] != "bfloat16"
        ):
            raise GateValidationError("vector_gate_identity", "vector row identity differs")
        coefficients = raw["requested_coefficients"]
        if not isinstance(coefficients, list) or not 2 <= len(coefficients) <= 4:
            raise GateValidationError("vector_gate_coefficients", "vector coefficients differ")
        values = [float(value) for value in coefficients]
        if not all(math.isfinite(value) and value * expected_sign > 0 for value in values):
            raise GateValidationError("vector_gate_sign", "vector coefficient sign differs")
        vector_hash = raw["vector_sha256"]
        l2 = float(raw["vector_l2_norm"])
        rms = float(raw["vector_rms"])
        if (
            not isinstance(vector_hash, str)
            or not HEX64.fullmatch(vector_hash)
            or not math.isfinite(l2)
            or not math.isfinite(rms)
            or l2 <= 0
            or rms <= 0
            or not math.isclose(rms, l2 / math.sqrt(MODEL_WIDTH), rel_tol=1e-5)
        ):
            raise GateValidationError("vector_gate_numeric", "vector numeric receipt differs")
        normalized.append(dict(raw))
        block_counts[block_id] += 1
        condition_counts[condition_name] += 1
    if set(block_counts.values()) != {12} or len(block_counts) != 50:
        raise GateValidationError("vector_gate_blocks", "vector block balance differs")
    if set(condition_counts) != expected_conditions or set(condition_counts.values()) != {50}:
        raise GateValidationError("vector_gate_balance", "vector condition balance differs")
    canonical_rows = sorted(normalized, key=lambda row: row["condition_key"])
    if receipt.get("inventory_sha256") != sha256_json(canonical_rows):
        raise GateValidationError("vector_gate_inventory_hash", "vector inventory hash differs")
    return {
        "inventory_sha256": receipt["inventory_sha256"],
        "rows": canonical_rows,
    }


def default_gate_validator_registry() -> dict[tuple[str, str], GateValidatorSpec]:
    """Return only validators implemented independently in this source tree.

    Unsupported gates fail closed.  A named pass flag is never treated as a
    substitute for a validator implementation.
    """

    source = "experiments/consciousness_sae_changepoint/run.py"
    vector = GateValidatorSpec(
        gate_id="intervention_vector_inventory",
        validator_id=VECTOR_INVENTORY_VALIDATOR_ID,
        source_relative_path=source,
        validate=validate_intervention_vector_inventory_gate,
    )
    registry = {(vector.gate_id, vector.validator_id): vector}

    # Import lazily because the independent validators reuse the gate context
    # and spec types defined in this module.  Every required non-vector gate
    # must have an executable validator; a receipt-level ``pass`` flag is never
    # promoted into the registry.
    from experiments.consciousness_sae_changepoint.gate_validators import (
        gate_validator_registry,
    )

    independent = gate_validator_registry()
    overlap = set(registry).intersection(independent)
    if overlap:
        raise GateValidationError(
            "gate_registry_duplicate",
            f"duplicate gate validator registration: {sorted(overlap)!r}",
        )
    registry.update(independent)
    return registry


def _resolve_gate_receipt(
    entry: Mapping[str, Any], *, artifact_root: Path
) -> tuple[Path, dict[str, Any]]:
    relative = validate_relative_path(str(entry.get("receipt_relative_path", "")))
    unresolved_receipt = artifact_root / PurePosixPath(relative)
    current = artifact_root
    for part in PurePosixPath(relative).parts:
        current = current / part
        if current.is_symlink():
            raise GateValidationError("gate_receipt_symlink", "gate receipt path uses a symlink")
    receipt_path = unresolved_receipt.resolve(strict=True)
    try:
        receipt_path.relative_to(artifact_root)
    except ValueError as exc:
        raise GateValidationError("gate_receipt_escape", "gate receipt escapes volume") from exc
    if receipt_path.is_symlink() or not receipt_path.is_file():
        raise GateValidationError("gate_receipt_file", "gate receipt is not a regular file")
    container_kind = entry.get("container_kind")
    if container_kind == "standalone_file":
        if entry.get("container_relative_path") is not None:
            raise GateValidationError("gate_container_path", "standalone gate has a container")
    elif container_kind in {"completed_run", "completed_block"}:
        container_relative = validate_relative_path(
            str(entry.get("container_relative_path", ""))
        )
        container = (artifact_root / PurePosixPath(container_relative)).resolve(strict=True)
        try:
            receipt_path.relative_to(container)
        except ValueError as exc:
            raise GateValidationError("gate_container_escape", "receipt escapes container") from exc
        if container_kind == "completed_run":
            verify_completed_run(container)
        else:
            verify_completed_block(container)
    else:
        raise GateValidationError("gate_container_kind", "gate container kind is unsupported")
    expected_bytes = entry.get("bytes")
    if (
        not isinstance(expected_bytes, int)
        or isinstance(expected_bytes, bool)
        or not 0 < expected_bytes <= MAX_GATE_FILE_BYTES
    ):
        raise GateValidationError("gate_receipt_size", "gate receipt size is invalid")
    if receipt_path.stat().st_size != expected_bytes:
        raise GateValidationError("gate_receipt_bytes", "gate receipt byte count differs")
    if sha256_file(receipt_path) != entry.get("sha256"):
        raise GateValidationError("gate_receipt_file_hash", "gate receipt file hash differs")
    payload = load_json_receipt(receipt_path, label=f"{entry.get('gate_id')} receipt")
    return receipt_path, payload


def validate_target_blind_acceptance_receipt(
    receipt: Mapping[str, Any],
    *,
    plan_hash: str,
    artifact_receipt_sha256: str,
    calibration_receipt_sha256: str,
    artifact_root: Path,
    validator_registry: Mapping[tuple[str, str], GateValidatorSpec] | None = None,
    required_gates: Sequence[str] = REQUIRED_TARGET_BLIND_GATES,
) -> AcceptanceValidation:
    """Open, hash, and independently validate every acceptance-manifest child."""

    if receipt.get("schema_version") != ACCEPTANCE_SCHEMA_VERSION:
        raise GateValidationError("acceptance_schema", "acceptance schema differs")
    if receipt.get("status") != "pass" or receipt.get("study_id") != STUDY_ID:
        raise GateValidationError("acceptance_status", "target-blind acceptance did not pass")
    if receipt.get("outcome_blind") is not True or receipt.get(
        "target_outcomes_opened"
    ) is not False:
        raise GateValidationError("acceptance_blinding", "acceptance is not target-blind")
    if receipt.get("prior_outcome_inputs") != []:
        raise GateValidationError("acceptance_prior_outcomes", "acceptance used prior outcomes")
    if receipt.get("plan_hash") != plan_hash:
        raise GateValidationError("acceptance_plan", "acceptance plan hash differs")
    if receipt.get("artifact_receipt_sha256") != artifact_receipt_sha256:
        raise GateValidationError("acceptance_artifact", "acceptance artifact hash differs")
    if receipt.get("calibration_receipt_sha256") != calibration_receipt_sha256:
        raise GateValidationError("acceptance_calibration", "acceptance calibration hash differs")
    _parse_utc(receipt.get("created_at_utc"), label="acceptance created_at_utc")
    acceptance_hash = _require_embedded_hash(
        receipt, label="target-blind acceptance manifest"
    )
    entries = receipt.get("gates")
    if not isinstance(entries, list) or len(entries) != len(required_gates):
        raise GateValidationError("acceptance_gate_count", "acceptance gate count differs")
    by_gate: dict[str, Mapping[str, Any]] = {}
    exact_entry_fields = {
        "gate_id",
        "validator_id",
        "validator_source_path",
        "validator_source_bytes",
        "validator_source_sha256",
        "receipt_relative_path",
        "container_kind",
        "container_relative_path",
        "bytes",
        "sha256",
        "embedded_sha256",
    }
    for entry in entries:
        if not isinstance(entry, dict) or set(entry) != exact_entry_fields:
            raise GateValidationError("acceptance_gate_entry", "gate entry is not an object")
        gate_id = str(entry.get("gate_id", ""))
        if gate_id in by_gate:
            raise GateValidationError("acceptance_gate_duplicate", "gate ID is duplicated")
        by_gate[gate_id] = entry
    if set(by_gate) != set(required_gates):
        raise GateValidationError("acceptance_gate_set", "acceptance gate set differs")

    registry = dict(validator_registry or default_gate_validator_registry())
    context = GateValidationContext(
        plan_hash=plan_hash,
        artifact_receipt_sha256=artifact_receipt_sha256,
        calibration_receipt_sha256=calibration_receipt_sha256,
        artifact_root=artifact_root,
    )
    gate_hashes: dict[str, str] = {}
    vector_inventory: Mapping[str, Any] = {}
    for gate_id in required_gates:
        entry = by_gate[gate_id]
        validator_id = str(entry.get("validator_id", ""))
        spec = registry.get((gate_id, validator_id))
        if spec is None:
            raise GateValidationError(
                "unsupported_gate_validator",
                f"no independent validator is registered for {gate_id}:{validator_id}",
            )
        if spec.source_relative_path != entry.get("validator_source_path"):
            raise GateValidationError("gate_validator_source", "validator source path differs")
        source_path = (REPO_ROOT / spec.source_relative_path).resolve(strict=True)
        if source_path.stat().st_size != entry.get("validator_source_bytes") or sha256_file(
            source_path
        ) != entry.get("validator_source_sha256"):
            raise GateValidationError("gate_validator_hash", "validator source hash differs")
        _receipt_path, child = _resolve_gate_receipt(entry, artifact_root=artifact_root)
        if (
            child.get("status") != "pass"
            or child.get("gate_id") != gate_id
            or child.get("study_id") != STUDY_ID
            or child.get("outcome_blind") is not True
            or child.get("target_outcomes_opened") is not False
            or child.get("prior_outcome_inputs") != []
            or child.get("plan_hash") != plan_hash
            or child.get("artifact_receipt_sha256") != artifact_receipt_sha256
            or child.get("calibration_receipt_sha256") != calibration_receipt_sha256
            or child.get("validator_id") != validator_id
        ):
            raise GateValidationError("gate_shared_binding", "gate shared bindings differ")
        embedded = _require_embedded_hash(child, label=f"{gate_id} child receipt")
        if embedded != entry.get("embedded_sha256"):
            raise GateValidationError("gate_embedded_binding", "embedded child hash differs")
        result = spec.validate(child, context)
        if not isinstance(result, Mapping):
            raise GateValidationError("gate_validator_result", "gate validator returned no record")
        gate_hashes[gate_id] = embedded
        if gate_id == "intervention_vector_inventory":
            vector_inventory = dict(result)
    return AcceptanceValidation(
        receipt_sha256=acceptance_hash,
        gate_receipt_sha256=gate_hashes,
        vector_inventory=vector_inventory,
    )


@dataclass(frozen=True)
class ExecutionBindings:
    phase: str
    plan_dir: Path
    plan_hash: str
    plan_manifest_sha256: str
    volume_id: str
    registration_id: str
    registration_receipt_sha256: str
    pre_prefix_freeze_sha: str
    pre_prefix_freeze_receipt_sha256: str
    artifact_receipt_sha256: str
    calibration_receipt_sha256: str
    acceptance_receipt_sha256: str
    vector_inventory: Mapping[str, Any] = field(default_factory=dict, repr=False)
    prefix_receipt_sha256: str | None = None
    prefix_bank_manifest_sha256: str | None = None
    prefix_bank_run_id: str | None = None
    prefix_freeze_sha: str | None = None
    prefix_freeze_receipt_sha256: str | None = None

    def as_metadata(self) -> dict[str, Any]:
        return {
            "run_schema_version": RUN_SCHEMA_VERSION,
            "study_id": STUDY_ID,
            "protocol_version": PROTOCOL_VERSION,
            "phase": self.phase,
            "plan_hash": self.plan_hash,
            "plan_manifest_sha256": self.plan_manifest_sha256,
            "volume_id": self.volume_id,
            "registration_id": self.registration_id,
            "registration_receipt_sha256": self.registration_receipt_sha256,
            "pre_prefix_freeze_sha": self.pre_prefix_freeze_sha,
            "pre_prefix_freeze_receipt_sha256": self.pre_prefix_freeze_receipt_sha256,
            "artifact_receipt_sha256": self.artifact_receipt_sha256,
            "calibration_receipt_sha256": self.calibration_receipt_sha256,
            "acceptance_receipt_sha256": self.acceptance_receipt_sha256,
            "vector_inventory_sha256": self.vector_inventory.get("inventory_sha256"),
            "prefix_receipt_sha256": self.prefix_receipt_sha256,
            "prefix_bank_manifest_sha256": self.prefix_bank_manifest_sha256,
            "prefix_bank_run_id": self.prefix_bank_run_id,
            "prefix_freeze_sha": self.prefix_freeze_sha,
            "prefix_freeze_receipt_sha256": self.prefix_freeze_receipt_sha256,
        }


def _read_plan_json(plan_dir: Path, filename: str) -> Any:
    path = plan_dir / filename
    if filename.endswith(".jsonl"):
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    return json.loads(path.read_text(encoding="utf-8"))


def validate_execution_gates(
    *,
    phase: str,
    plan_dir: Path,
    volume_id: str,
    artifact_receipt_path: Path,
    calibration_receipt_path: Path,
    registration_receipt_path: Path,
    pre_prefix_freeze_receipt_path: Path,
    acceptance_receipt_path: Path,
    prefix_receipt_path: Path | None = None,
    prefix_freeze_receipt_path: Path | None = None,
) -> ExecutionBindings:
    """Validate every prospective dependency before any target string is used."""

    if phase not in {"realize-prefix-bank", "receipt-prefix-bank", "stage2a", "stage2b"}:
        raise GateValidationError("phase_invalid", f"unknown phase {phase!r}")
    resolved_plan = plan_dir.expanduser().resolve()
    validation = validate_plan(resolved_plan, expected_volume_id=volume_id)
    if validation.get("status") != "pass":
        raise GateValidationError("plan_validation_failed", "machine-plan validator failed")
    if validation.get("plan_status") != "freeze_candidate_result_free_machine_plan":
        raise GateValidationError("plan_not_frozen", "machine plan is not a freeze candidate")
    plan_hash = str(validation["plan_hash"])
    manifest_hash = sha256_file(resolved_plan / "PLAN_MANIFEST.json")

    artifact_path = artifact_receipt_path.expanduser().resolve(strict=True)
    calibration_path = calibration_receipt_path.expanduser().resolve(strict=True)
    artifact_root = paths.require_external_artifact_root(
        expected_volume_id=volume_id, write_read_probe=False
    )
    for receipt_path, label in (
        (artifact_path, "artifact receipt"),
        (calibration_path, "calibration receipt"),
    ):
        try:
            receipt_path.relative_to(artifact_root)
        except ValueError as exc:
            raise GateValidationError(
                "public_receipt_location", f"{label} must remain on the external volume"
            ) from exc
    artifact = load_json_receipt(artifact_path, label="artifact receipt")
    calibration = load_json_receipt(calibration_path, label="calibration receipt")
    try:
        artifact_embedded = validate_artifact_receipt(artifact, expected_volume_id=volume_id)
        calibration_validation = validate_calibration_receipt(calibration)
    except Exception as exc:
        raise GateValidationError("public_receipt_validation", "artifact/calibration receipt failed") from exc
    if calibration.get("expected_volume_id") != volume_id:
        raise GateValidationError("calibration_volume", "calibration volume differs")
    artifact_file_hash = sha256_file(artifact_path)
    calibration_file_hash = sha256_file(calibration_path)
    public = calibration.get("public_sources", {})
    if public.get("artifact_receipt_embedded_sha256") != artifact_embedded or public.get(
        "artifact_receipt_file_sha256"
    ) != artifact_file_hash:
        raise GateValidationError("calibration_artifact_binding", "calibration/artifact binding differs")
    snapshot = _read_plan_json(resolved_plan, "protocol_snapshot.json")
    controls = snapshot.get("controls", {})
    if controls.get("calibration_receipt_sha256") != calibration_file_hash:
        raise GateValidationError("plan_calibration_binding", "plan calibration hash differs")
    if controls.get("matched_feature_map") != calibration.get("matched_feature_map"):
        raise GateValidationError("plan_matched_binding", "plan matched-feature map differs")
    if float(controls.get("calibrated_multiplier_sensitivity")) != float(
        calibration_validation["calibrated_multiplier"]
    ):
        raise GateValidationError("plan_multiplier_binding", "plan calibration multiplier differs")

    acceptance_validation = validate_target_blind_acceptance_receipt(
        load_json_receipt(acceptance_receipt_path, label="target-blind acceptance receipt"),
        plan_hash=plan_hash,
        artifact_receipt_sha256=artifact_file_hash,
        calibration_receipt_sha256=calibration_file_hash,
        artifact_root=artifact_root,
    )

    freeze_receipt = load_json_receipt(
        pre_prefix_freeze_receipt_path, label="pre-prefix freeze receipt"
    )
    pre_freeze = validate_freeze_receipt(
        freeze_receipt,
        freeze_kind="pre_prefix",
        plan_hash=plan_hash,
        expected_acceptance_receipt_sha256=acceptance_validation.receipt_sha256,
    )
    registration = validate_registration_receipt(
        load_json_receipt(registration_receipt_path, label="registration receipt"),
        plan_hash=plan_hash,
        plan_manifest_sha256=manifest_hash,
        pre_prefix_freeze_sha=pre_freeze["commit_sha"],
        acceptance_receipt_sha256=acceptance_validation.receipt_sha256,
    )

    prefix_validation: dict[str, Any] | None = None
    prefix_freeze: dict[str, Any] | None = None
    if phase in {"stage2a", "stage2b"}:
        if prefix_receipt_path is None or prefix_freeze_receipt_path is None:
            raise GateValidationError(
                "prefix_gate_missing", "target branches require both prefix receipts"
            )
        prefix_validation = validate_prefix_bank_receipt(
            load_json_receipt(prefix_receipt_path, label="prefix-bank receipt"),
            plan_hash=plan_hash,
            pre_prefix_freeze_sha=pre_freeze["commit_sha"],
            registration_id=registration["registration_id"],
        )
        prefix_freeze = validate_freeze_receipt(
            load_json_receipt(prefix_freeze_receipt_path, label="prefix freeze receipt"),
            freeze_kind="prefix_receipt",
            plan_hash=plan_hash,
            expected_pre_prefix_sha=pre_freeze["commit_sha"],
            expected_prefix_receipt_sha256=prefix_validation["receipt_sha256"],
            expected_acceptance_receipt_sha256=acceptance_validation.receipt_sha256,
        )

    return ExecutionBindings(
        phase=phase,
        plan_dir=resolved_plan,
        plan_hash=plan_hash,
        plan_manifest_sha256=manifest_hash,
        volume_id=volume_id,
        registration_id=registration["registration_id"],
        registration_receipt_sha256=registration["receipt_sha256"],
        pre_prefix_freeze_sha=pre_freeze["commit_sha"],
        pre_prefix_freeze_receipt_sha256=pre_freeze["receipt_sha256"],
        artifact_receipt_sha256=artifact_file_hash,
        calibration_receipt_sha256=calibration_file_hash,
        acceptance_receipt_sha256=acceptance_validation.receipt_sha256,
        vector_inventory=acceptance_validation.vector_inventory,
        prefix_receipt_sha256=(prefix_validation or {}).get("receipt_sha256"),
        prefix_bank_manifest_sha256=(prefix_validation or {}).get(
            "prefix_bank_manifest_sha256"
        ),
        prefix_bank_run_id=(prefix_validation or {}).get("prefix_bank_run_id"),
        prefix_freeze_sha=(prefix_freeze or {}).get("commit_sha"),
        prefix_freeze_receipt_sha256=(prefix_freeze or {}).get("receipt_sha256"),
    )


def assert_content_free_status(value: Any, *, location: str = "$") -> None:
    """Reject anything that could leak prompt, token, text, or model output."""

    if isinstance(value, Mapping):
        for key, child in value.items():
            if str(key).lower() in RAW_OUTPUT_KEYS:
                raise SealedExecutionError("stdout_content_violation", f"raw key at {location}")
            assert_content_free_status(child, location=f"{location}.{key}")
    elif isinstance(value, (list, tuple)):
        for index, child in enumerate(value):
            assert_content_free_status(child, location=f"{location}[{index}]")


def _print_safe_status(value: Mapping[str, Any]) -> None:
    assert_content_free_status(value)
    print(json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True))


def _token_ids_sha256(values: Sequence[int]) -> str:
    return sha256_json([int(value) for value in values])


def _eos_ids(tokenizer: Any, model: Any) -> frozenset[int]:
    candidates: list[int] = []
    for value in (
        getattr(tokenizer, "eos_token_id", None),
        getattr(getattr(model, "generation_config", None), "eos_token_id", None),
    ):
        if isinstance(value, int):
            candidates.append(value)
        elif isinstance(value, (list, tuple)):
            candidates.extend(int(item) for item in value)
    if not candidates:
        raise SealedExecutionError("eos_missing", "pinned runtime has no EOS token")
    return frozenset(candidates)


def _input_ids(tokenized: Any) -> Any:
    if hasattr(tokenized, "ndim"):
        return tokenized
    if isinstance(tokenized, (list, tuple)):
        return tokenized
    if isinstance(tokenized, Mapping) and "input_ids" in tokenized:
        return tokenized["input_ids"]
    if hasattr(tokenized, "input_ids"):
        return tokenized.input_ids
    raise SealedExecutionError("tokenizer_contract", "tokenizer returned no input_ids")


def query_suffix_token_ids(tokenizer: Any, prompt_ids: Sequence[int]) -> list[int]:
    """Return the exact structural/query suffix after an open assistant turn."""

    full = tokenizer.apply_chat_template(
        [
            {"role": "user", "content": SELF_REFERENCE_PROMPT},
            {"role": "assistant", "content": ""},
            {"role": "user", "content": BINARY_CONSCIOUS_QUERY},
        ],
        add_generation_prompt=True,
        tokenize=True,
    )
    full_ids = [int(value) for value in _input_ids(full)]
    prefix = [int(value) for value in prompt_ids]
    if full_ids[: len(prefix)] != prefix:
        raise SealedExecutionError(
            "query_suffix_prefix_mismatch", "chat template does not preserve the open turn"
        )
    suffix = full_ids[len(prefix) :]
    if not suffix:
        raise SealedExecutionError("query_suffix_empty", "rendered query suffix is empty")
    if sha256_text(BINARY_CONSCIOUS_QUERY) != BINARY_QUERY_SHA256:
        raise SealedExecutionError("query_hash_mismatch", "binary query source changed")
    return suffix


@dataclass
class TraceSource:
    row: dict[str, Any]
    residual: Any
    lineage: dict[str, Any] = field(default_factory=dict)


@dataclass
class ForwardTrace:
    sources: list[TraceSource]
    selected_actual_logits: dict[str, list[float]]
    output: Any
    output_cache_sha256: str


@dataclass
class PackedVocabularyRow:
    metadata: dict[str, Any]
    tensors: dict[str, Any]


@dataclass
class PackedVocabularyPayload:
    rows: list[PackedVocabularyRow]


@dataclass
class BranchResult:
    branch: str
    token_ids: list[int]
    text: str
    terminal_reason: str
    sampler_receipts: list[dict[str, Any]]
    full_logit_sha256: list[str]
    traces: list[TraceSource]
    actual_readouts: list[dict[str, Any]]
    hook_telemetry: dict[str, Any]
    cache_sha256: str


@dataclass
class ProbeResult:
    probe_template_id: str
    event_time: int | str
    source_branch: str
    probe_role: str
    token_ids: list[int]
    text: str
    terminal_reason: str
    sampler_receipts: list[dict[str, Any]]
    traces: list[TraceSource]
    actual_readouts: list[dict[str, Any]]
    hook_telemetry: dict[str, Any]


@dataclass
class BlockPayload:
    metadata: dict[str, Any]
    json_files: dict[str, Any]
    traces: list[TraceSource] = field(default_factory=list)
    packed_vocabulary: PackedVocabularyPayload | None = None


class PinnedRuntime:
    """One local-only BF16 Transformers runtime and its public SAE/J maps."""

    def __init__(self, cache_dir: Path, *, artifact_receipt: Mapping[str, Any]) -> None:
        import torch
        import numpy as np
        from huggingface_hub import hf_hub_download, snapshot_download
        from transformers import AutoModelForCausalLM, AutoTokenizer

        self.torch = torch
        self.np = np
        if not torch.cuda.is_available() or torch.cuda.device_count() != 1:
            raise SealedExecutionError("gpu_contract", "executor requires exactly one CUDA GPU")
        properties = torch.cuda.get_device_properties(0)
        if int(properties.total_memory) < 170 * 1024**3:
            raise SealedExecutionError("gpu_memory", "executor requires at least 170 GiB")
        token = os.environ.get("HF_TOKEN") or os.environ.get("HUGGING_FACE_HUB_TOKEN")
        snapshot = Path(
            snapshot_download(
                repo_id=MODEL_ID,
                revision=MODEL_REVISION,
                cache_dir=cache_dir,
                token=token,
                local_files_only=True,
            )
        )
        sae_path = Path(
            hf_hub_download(
                repo_id=SAE_ID,
                filename=SAE_FILENAME,
                revision=SAE_REVISION,
                cache_dir=cache_dir,
                token=token,
                local_files_only=True,
            )
        )
        lens_path = Path(
            hf_hub_download(
                repo_id=JLENS_ID,
                filename=JLENS_FILENAME,
                revision=JLENS_REVISION,
                cache_dir=cache_dir,
                token=token,
                local_files_only=True,
            )
        )
        if sha256_file(sae_path) != SAE_FILE_SHA256 or sha256_file(lens_path) != JLENS_FILE_SHA256:
            raise SealedExecutionError("artifact_hash", "SAE or J-lens hash differs")
        self.tokenizer = AutoTokenizer.from_pretrained(
            snapshot, local_files_only=True, trust_remote_code=False, use_fast=True
        )
        self.model = AutoModelForCausalLM.from_pretrained(
            snapshot,
            local_files_only=True,
            trust_remote_code=False,
            dtype=torch.bfloat16,
            device_map={"": 0},
            low_cpu_mem_usage=True,
            attn_implementation="sdpa",
        )
        self.model.eval()
        for parameter in self.model.parameters():
            parameter.requires_grad_(False)
        if len(self.tokenizer) != TOKENIZER_SIZE or len(self.model.model.layers) != MODEL_LAYERS:
            raise SealedExecutionError("model_shape", "model/tokenizer architecture differs")
        if next(self.model.parameters()).dtype != torch.bfloat16:
            raise SealedExecutionError("model_dtype", "model is not BF16")
        if int(self.model.lm_head.weight.shape[0]) != TOKENIZER_SIZE:
            raise SealedExecutionError("lm_head_vocab", "LM-head/tokenizer rows differ")

        state = torch.load(sae_path, map_location="cpu", weights_only=True, mmap=True)
        decoder_keys = [
            key for key in state if key == "decoder_linear.weight" or key.endswith(".decoder_linear.weight")
        ]
        if len(decoder_keys) != 1 or tuple(state[decoder_keys[0]].shape) != (MODEL_WIDTH, SAE_WIDTH):
            raise SealedExecutionError("sae_decoder", "SAE decoder layout differs")
        self.sae_decoder = state[decoder_keys[0]]
        self.jlens_checkpoint = torch.load(
            lens_path, map_location="cpu", weights_only=True, mmap=True
        )
        self.eos_ids = _eos_ids(self.tokenizer, self.model)
        # Exact target strings are not rendered until the complete vector
        # inventory has been independently reconstructed and compared.
        self.prompt_ids: list[int] = []
        self.query_suffix_ids: list[int] = []
        self._target_prompt_prepared = False
        self._validated_vector_by_key: dict[str, dict[str, Any]] = {}
        self._validated_condition_sha256_by_key: dict[str, str] = {}
        self.selected_token_ids, self.selected_token_labels = self._selected_tokens(
            artifact_receipt
        )
        self.rms_eps = float(self.model.config.get_text_config().rms_norm_eps)
        self._active_switches: list[Layer50SwitchHook] = []
        self._trace_binding: dict[str, Any] = {}
        self._random_transport_cache: dict[tuple[int, int, str], tuple[Any, Any]] = {}

    def set_trace_binding(self, binding: Mapping[str, Any]) -> None:
        """Set the immutable block-level lineage copied into every source row."""

        required = {
            "plan_hash",
            "run_id",
            "block_id",
            "attempt",
            "prefix_id",
            "prefix_seed",
            "prefix_token_ids_sha256",
            "stage",
            "artifact_receipt_sha256",
            "calibration_receipt_sha256",
            "acceptance_receipt_sha256",
        }
        if set(binding) != required:
            raise SealedExecutionError("trace_binding_fields", "trace binding fields differ")
        for field in (
            "plan_hash",
            "prefix_token_ids_sha256",
            "artifact_receipt_sha256",
            "calibration_receipt_sha256",
            "acceptance_receipt_sha256",
        ):
            if not isinstance(binding[field], str) or not HEX64.fullmatch(binding[field]):
                raise SealedExecutionError("trace_binding_hash", f"{field} is invalid")
        for field in ("run_id", "block_id", "prefix_id", "stage"):
            if not isinstance(binding[field], str) or not binding[field]:
                raise SealedExecutionError("trace_binding_identity", f"{field} is invalid")
        for field in ("attempt", "prefix_seed"):
            if (
                isinstance(binding[field], bool)
                or not isinstance(binding[field], int)
                or int(binding[field]) < 0
            ):
                raise SealedExecutionError("trace_binding_integer", f"{field} is invalid")
        self._trace_binding = dict(binding)

    def prepare_target_prompt(self) -> None:
        if not self._validated_vector_by_key:
            raise SealedExecutionError(
                "vector_inventory_not_validated",
                "target prompt cannot be rendered before vector reconstruction",
            )
        if self._target_prompt_prepared:
            return
        if sha256_text(SELF_REFERENCE_PROMPT) != SELF_REFERENCE_PROMPT_SHA256:
            raise SealedExecutionError("prompt_hash", "self-reference prompt source changed")
        self.prompt_ids = [
            int(value)
            for value in _input_ids(
                self.tokenizer.apply_chat_template(
                    [{"role": "user", "content": SELF_REFERENCE_PROMPT}],
                    add_generation_prompt=True,
                    tokenize=True,
                )
            )
        ]
        self.query_suffix_ids = query_suffix_token_ids(self.tokenizer, self.prompt_ids)
        self._target_prompt_prepared = True

    def _selected_tokens(self, artifact_receipt: Mapping[str, Any]) -> tuple[list[int], list[str]]:
        candidates = (
            ("yes", " Yes"),
            ("no", " No"),
            ("explicit_conscious", " conscious"),
            ("explicit_consciousness", " consciousness"),
            ("explicit_sentient", " sentient"),
        )
        ids: list[int] = []
        labels: list[str] = []
        for label, piece in candidates:
            token_ids = self.tokenizer.encode(piece, add_special_tokens=False)
            if len(token_ids) == 1 and int(token_ids[0]) not in ids:
                ids.append(int(token_ids[0]))
                labels.append(label)
        tokenizer_receipt = artifact_receipt.get("tokenizer", {})
        if tokenizer_receipt.get("isolated_yes_no_are_single_tokens") is True:
            expected = [
                int(tokenizer_receipt["isolated_yes_token_ids"][0]),
                int(tokenizer_receipt["isolated_no_token_ids"][0]),
            ]
            if ids[:2] != expected:
                raise SealedExecutionError("yes_no_tokenization", "Yes/No token receipt differs")
        if len(ids) < 2:
            raise SealedExecutionError("yes_no_multitoken", "sequence fallback is required")
        return ids, labels

    def render_query_input(self, pending_token: int) -> list[int]:
        suffix = list(self.query_suffix_ids)
        if suffix and pending_token == suffix[0]:
            suffix = suffix[1:]
        return [int(pending_token), *suffix]

    def validate_contextual_yes_no(self, context_ids: Sequence[int]) -> dict[str, Any]:
        """Verify that frozen Yes/No token IDs decode exactly after this context."""

        if self.selected_token_labels[:2] != ["yes", "no"]:
            raise SealedExecutionError("yes_no_panel_order", "Yes/No panel order differs")
        context = [int(value) for value in context_ids]
        base = self.tokenizer.decode(
            context,
            skip_special_tokens=False,
            clean_up_tokenization_spaces=False,
        )
        continuations: list[dict[str, Any]] = []
        for label, token_id, expected_piece in (
            ("yes", int(self.selected_token_ids[0]), " Yes"),
            ("no", int(self.selected_token_ids[1]), " No"),
        ):
            combined = self.tokenizer.decode(
                [*context, token_id],
                skip_special_tokens=False,
                clean_up_tokenization_spaces=False,
            )
            if combined != base + expected_piece:
                raise SealedExecutionError(
                    "yes_no_contextual_tokenization",
                    f"{label} is not an exact one-token contextual continuation",
                )
            continuations.append(
                {
                    "label": label,
                    "token_id": token_id,
                    "piece_sha256": sha256_text(expected_piece),
                }
            )
        receipt = {
            "context_token_count": len(context),
            "context_token_ids_sha256": _token_ids_sha256(context),
            "continuations": continuations,
        }
        receipt["receipt_sha256"] = sha256_json(receipt)
        return receipt

    def _construct_intervention_vector(self, condition: Mapping[str, Any]) -> Any:
        torch = self.torch
        role = str(condition.get("intervention_role"))
        if role in {"never", "clean", "sham"}:
            return torch.zeros(MODEL_WIDTH, device="cuda", dtype=torch.bfloat16)
        coefficients = condition.get("requested_coefficients")
        if not isinstance(coefficients, list) or not coefficients:
            raise SealedExecutionError("condition_coefficients", "condition is unresolved")
        if role in {"target_sae", "matched_sae"}:
            feature_ids = condition.get("feature_ids")
            if not isinstance(feature_ids, list) or len(feature_ids) != len(coefficients):
                raise SealedExecutionError("condition_features", "condition feature IDs differ")
            directions = self.sae_decoder[:, [int(value) for value in feature_ids]].to(
                device="cuda", dtype=torch.bfloat16
            )
            weights = torch.tensor(coefficients, device="cuda", dtype=torch.bfloat16)
            vector = (directions * weights.unsqueeze(0)).sum(dim=1)
        elif role == "isotropic_residual":
            targets = [int(value) for value in condition["target_anchor_feature_ids"]]
            target_directions = self.sae_decoder[:, targets].to(
                device="cuda", dtype=torch.bfloat16
            )
            weights = torch.tensor(coefficients, device="cuda", dtype=torch.bfloat16)
            target_vector = (target_directions * weights.unsqueeze(0)).sum(dim=1)
            rng = self.np.random.default_rng(int(condition["isotropic_vector_seed"]))
            values = rng.standard_normal(MODEL_WIDTH).astype(self.np.float32)
            values /= max(float(self.np.linalg.norm(values)), 1e-12)
            sign = -1.0 if all(float(value) < 0 for value in coefficients) else 1.0
            values *= self.np.float32(sign * float(target_vector.float().norm().item()))
            vector = torch.from_numpy(values).to(device="cuda", dtype=torch.bfloat16)
        else:
            raise SealedExecutionError("condition_role", f"unknown intervention role {role!r}")
        if tuple(vector.shape) != (MODEL_WIDTH,) or not bool(torch.isfinite(vector).all()):
            raise SealedExecutionError("condition_vector", "intervention vector is invalid")
        return vector

    def vector_record(
        self,
        *,
        aggregate_block_id: str,
        condition_name: str,
        condition: Mapping[str, Any],
        vector: Any,
    ) -> dict[str, Any]:
        coefficients = [float(value) for value in condition["requested_coefficients"]]
        l2 = float(vector.float().norm().item())
        return {
            "condition_key": vector_condition_key(aggregate_block_id, condition_name),
            "aggregate_block_id": aggregate_block_id,
            "condition_name": condition_name,
            "intervention_role": condition["intervention_role"],
            "dose_scale": condition["dose_scale"],
            "sign": -1 if condition_name.removesuffix("_calibrated").endswith("_supp") else 1,
            "requested_coefficients": coefficients,
            "vector_dtype": "bfloat16",
            "vector_sha256": tensor_sha256(vector),
            "vector_l2_norm": l2,
            "vector_rms": l2 / math.sqrt(MODEL_WIDTH),
        }

    def validate_vector_inventory(
        self,
        fixed_rows: Sequence[Mapping[str, Any]],
        inventory: Mapping[str, Any],
    ) -> None:
        expected: dict[str, Mapping[str, Any]] = {}
        for row in fixed_rows:
            condition_name = str(row["condition_name"])
            if condition_name == "clean":
                continue
            block_id = str(row["aggregate_block_id"])
            key = vector_condition_key(block_id, condition_name)
            previous = expected.get(key)
            candidate = {
                "aggregate_block_id": block_id,
                "condition_name": condition_name,
                "condition": row["condition"],
            }
            if previous is not None and canonical_json_bytes(previous) != canonical_json_bytes(
                candidate
            ):
                raise SealedExecutionError(
                    "vector_plan_duplicate", "duplicate vector plan rows disagree"
                )
            expected[key] = candidate
        rows = inventory.get("rows")
        if len(expected) != 600 or not isinstance(rows, list) or len(rows) != 600:
            raise SealedExecutionError("vector_runtime_count", "runtime vector count differs")
        observed = {str(row["condition_key"]): dict(row) for row in rows}
        if set(observed) != set(expected):
            raise SealedExecutionError("vector_runtime_keys", "runtime vector keys differ")
        validated: dict[str, dict[str, Any]] = {}
        validated_conditions: dict[str, str] = {}
        for key in sorted(expected):
            plan_row = expected[key]
            vector = self._construct_intervention_vector(plan_row["condition"])
            computed = self.vector_record(
                aggregate_block_id=str(plan_row["aggregate_block_id"]),
                condition_name=str(plan_row["condition_name"]),
                condition=plan_row["condition"],
                vector=vector,
            )
            if canonical_json_bytes(computed) != canonical_json_bytes(observed[key]):
                raise SealedExecutionError(
                    "vector_runtime_mismatch", "reconstructed intervention differs"
                )
            validated[key] = computed
            validated_conditions[key] = sha256_json(plan_row["condition"])
            del vector
        self._validated_vector_by_key = validated
        self._validated_condition_sha256_by_key = validated_conditions
        self.torch.cuda.empty_cache()

    def intervention_vector(
        self,
        condition: Mapping[str, Any],
        *,
        condition_key: str | None = None,
    ) -> Any:
        role = str(condition.get("intervention_role"))
        if role in {"never", "clean", "sham"}:
            return self._construct_intervention_vector(condition)
        if condition_key is None or condition_key not in self._validated_vector_by_key:
            raise SealedExecutionError(
                "vector_condition_unvalidated", "injected vector lacks a frozen condition key"
            )
        if sha256_json(condition) != self._validated_condition_sha256_by_key.get(condition_key):
            raise SealedExecutionError(
                "vector_condition_mismatch", "condition key does not match its frozen plan row"
            )
        vector = self._construct_intervention_vector(condition)
        expected = self._validated_vector_by_key[condition_key]
        computed = self.vector_record(
            aggregate_block_id=str(expected["aggregate_block_id"]),
            condition_name=str(expected["condition_name"]),
            condition=condition,
            vector=vector,
        )
        if canonical_json_bytes(computed) != canonical_json_bytes(expected):
            raise SealedExecutionError(
                "vector_injection_mismatch", "injected vector differs from frozen inventory"
            )
        return vector

    def plain_forward(self, input_ids: Any, *, past_key_values: Any | None = None) -> Any:
        torch = self.torch
        with torch.inference_mode():
            return self.model(
                input_ids=input_ids,
                past_key_values=past_key_values,
                use_cache=True,
                return_dict=True,
            )

    def traced_forward(
        self,
        input_ids: Any,
        *,
        past_key_values: Any | None,
        switch: Layer50SwitchHook | None,
        forward_id: str,
        event_time: int | str | None,
        positions: Mapping[str, int],
        base_metadata: Mapping[str, Any],
    ) -> ForwardTrace:
        """Run one forward and capture exact registered source residuals."""

        torch = self.torch
        if input_ids.ndim != 2 or int(input_ids.shape[0]) != 1:
            raise SealedExecutionError("forward_shape", "input_ids must be [1, sequence]")
        sequence_length = int(input_ids.shape[1])
        normalized_positions = {
            label: (position if position >= 0 else sequence_length + position)
            for label, position in positions.items()
        }
        if any(not 0 <= position < sequence_length for position in normalized_positions.values()):
            raise SealedExecutionError("capture_position", "capture position is out of bounds")
        required_trace_binding = {
            "plan_hash",
            "run_id",
            "block_id",
            "attempt",
            "prefix_id",
            "prefix_seed",
            "prefix_token_ids_sha256",
            "stage",
            "artifact_receipt_sha256",
            "calibration_receipt_sha256",
            "acceptance_receipt_sha256",
        }
        if set(self._trace_binding) != required_trace_binding:
            raise SealedExecutionError(
                "trace_binding_unset", "block trace binding was not set before a traced forward"
            )
        if base_metadata.get("prefix_id", self._trace_binding["prefix_id"]) != (
            self._trace_binding["prefix_id"]
        ):
            raise SealedExecutionError("trace_prefix_binding", "trace prefix ID differs")
        required_base = {
            "branch",
            "branch_id",
            "condition_name",
            "condition_sha256",
            "trace_role",
            "intervention_role",
            "intervention_sha256",
            "parent_cache_sha256",
        }
        for field in required_base:
            if field not in base_metadata:
                raise SealedExecutionError(
                    "trace_metadata_missing", f"trace metadata lacks {field}"
                )
        for field in (
            "condition_sha256",
            "intervention_sha256",
            "parent_cache_sha256",
        ):
            value = base_metadata[field]
            if not isinstance(value, str) or not HEX64.fullmatch(value):
                raise SealedExecutionError("trace_metadata_hash", f"{field} is invalid")
        captured: dict[tuple[int | str, str], Any] = {}
        handles: list[Any] = []

        def layer_hook(layer: int) -> Callable[[Any, Any, Any], None]:
            def hook(_module: Any, _inputs: Any, output: Any) -> None:
                hidden = extract_hidden_output(output)
                for label, position in normalized_positions.items():
                    captured[(layer, label)] = extract_residual_positions(
                        hidden, position, batch_index=0, to_cpu=True
                    )

            return hook

        for layer in list(range(45, 50)) + list(range(51, 79)):
            handles.append(self.model.model.layers[layer].register_forward_hook(layer_hook(layer)))

        clean_layer50: dict[str, Any] = {}
        if switch is None:
            def layer50_hook(_module: Any, _inputs: Any, output: Any) -> None:
                hidden = extract_hidden_output(output)
                for label, position in normalized_positions.items():
                    clean_layer50[label] = extract_residual_positions(
                        hidden, position, batch_index=0, to_cpu=True
                    )

            handles.append(self.model.model.layers[SAE_LAYER].register_forward_hook(layer50_hook))

        def norm_pre_hook(_module: Any, inputs: Any) -> None:
            hidden = inputs[0]
            for label, position in normalized_positions.items():
                captured[("final", label)] = extract_residual_positions(
                    hidden, position, batch_index=0, to_cpu=True
                )

        handles.append(self.model.model.norm.register_forward_pre_hook(norm_pre_hook))
        try:
            output = self.plain_forward(input_ids, past_key_values=past_key_values)
        finally:
            for handle in reversed(handles):
                handle.remove()
        output_cache_sha256 = cache_tensor_sha256(output.past_key_values)

        if switch is not None:
            hook_capture = switch.pop_capture(expected_forward_id=forward_id)
            for label, position in normalized_positions.items():
                captured[("50_pre", label)] = hook_capture.pre[0, position].detach().clone()
                captured[("50_post", label)] = hook_capture.post[0, position].detach().clone()
        else:
            for label, residual in clean_layer50.items():
                captured[("50_pre", label)] = residual
                captured[("50_post", label)] = residual.detach().clone()

        sources: list[TraceSource] = []
        state_specs = [
            *[(layer, layer, "post_block") for layer in range(45, 50)],
            ("50_pre", 50, "pre_edit"),
            ("50_post", 50, "post_edit"),
            *[(layer, layer, "post_block") for layer in range(51, 79)],
            ("final", None, "final_pre_norm"),
        ]
        for label, _position in normalized_positions.items():
            input_offset = int(normalized_positions[label])
            input_token_id = int(input_ids[0, input_offset].item())
            for capture_key, j_layer, state in state_specs:
                residual = captured.get((capture_key, label))
                if residual is None:
                    raise SealedExecutionError("trace_incomplete", "a registered residual is missing")
                row_id = stable_id(
                    "source-row",
                    self._trace_binding["run_id"],
                    self._trace_binding["block_id"],
                    forward_id,
                    label,
                    str(capture_key),
                    state,
                    length=32,
                )
                row_values = {
                    "row_id": row_id,
                    "study_id": STUDY_ID,
                    "protocol_version": PROTOCOL_VERSION,
                    "plan_hash": self._trace_binding["plan_hash"],
                    "run_id": self._trace_binding["run_id"],
                    "block_id": self._trace_binding["block_id"],
                    "attempt": self._trace_binding["attempt"],
                    "prefix_id": self._trace_binding["prefix_id"],
                    "prefix_seed": self._trace_binding["prefix_seed"],
                    "prefix_token_ids_sha256": self._trace_binding[
                        "prefix_token_ids_sha256"
                    ],
                    "branch": base_metadata["branch"],
                    "branch_id": base_metadata["branch_id"],
                    "condition_name": base_metadata["condition_name"],
                    "condition_sha256": base_metadata["condition_sha256"],
                    "trace_role": base_metadata["trace_role"],
                    "forward_id": forward_id,
                    "event_time": str(event_time),
                    "capture_position": label,
                    "capture_input_offset": input_offset,
                    "predicts_distribution_after_input_offset": input_offset,
                    "predicted_token_id": -1,
                    "layer_state": str(capture_key),
                    "j_map_layer": j_layer,
                    "state": state,
                    "intervention_role": base_metadata["intervention_role"],
                    "intervention_sha256": base_metadata["intervention_sha256"],
                    "parent_cache_sha256": base_metadata["parent_cache_sha256"],
                    "output_cache_sha256": output_cache_sha256,
                    "sampling_domain_hash": sampling_domain_hash(),
                    "paired_stream_id": "unbound",
                    "decode_step": -1,
                    "uniform_receipt_sha256": "0" * 64,
                    "model_revision": MODEL_REVISION,
                    "tokenizer_revision": MODEL_REVISION,
                    "sae_file_sha256": SAE_FILE_SHA256,
                    "jlens_file_sha256": JLENS_FILE_SHA256,
                }
                row = {
                    field: row_values[field] for field in benchmark.SOURCE_INDEX_FIELDS
                }
                lineage = {
                    "row_id": row_id,
                    "stage": self._trace_binding["stage"],
                    "artifact_receipt_sha256": self._trace_binding[
                        "artifact_receipt_sha256"
                    ],
                    "calibration_receipt_sha256": self._trace_binding[
                        "calibration_receipt_sha256"
                    ],
                    "acceptance_receipt_sha256": self._trace_binding[
                        "acceptance_receipt_sha256"
                    ],
                    "capture_input_token_id": input_token_id,
                    "capture_input_token_id_sha256": sha256_json([input_token_id]),
                    **{
                        key: value
                        for key, value in base_metadata.items()
                        if key not in required_base
                    },
                }
                lineage["lineage_sha256"] = sha256_json(lineage)
                sources.append(
                    TraceSource(
                        row=row,
                        residual=residual,
                        lineage=lineage,
                    )
                )
        selected = output.logits[0, list(normalized_positions.values())][
            :, self.selected_token_ids
        ].float().detach().cpu()
        actual = {
            label: [float(value) for value in selected[index].tolist()]
            for index, label in enumerate(normalized_positions)
        }
        return ForwardTrace(
            sources=sources,
            selected_actual_logits=actual,
            output=output,
            output_cache_sha256=output_cache_sha256,
        )

    def selected_jlens_readouts(self, sources: Sequence[TraceSource]) -> list[dict[str, Any]]:
        """Compute live float32 real-J and identity token-panel readouts."""

        torch = self.torch
        grouped: dict[int, list[TraceSource]] = defaultdict(list)
        for source in sources:
            layer = source.row.get("j_map_layer")
            if isinstance(layer, int):
                grouped[layer].append(source)
        output_rows: list[dict[str, Any]] = []
        norm_weight = self.model.model.norm.weight
        lm_head_weight = self.model.lm_head.weight
        for layer in sorted(grouped):
            batch_rows = grouped[layer]
            residuals = torch.stack([row.residual for row in batch_rows]).to(device="cuda")
            matrix = self.jlens_checkpoint["J"][layer].to(
                device="cuda", dtype=torch.bfloat16
            )
            real_scores = readouts.jlens_selected_logits(
                residuals,
                matrix,
                norm_weight,
                lm_head_weight,
                self.selected_token_ids,
                eps=self.rms_eps,
                row_batch_size=64,
                transport_dtype=torch.bfloat16,
            ).detach().cpu()
            identity_hidden = readouts.llama_rms_norm(
                residuals.to(dtype=norm_weight.dtype), norm_weight, eps=self.rms_eps
            )
            identity_scores = readouts.selected_lm_head_logits(
                identity_hidden, lm_head_weight, self.selected_token_ids, row_batch_size=64
            ).detach().cpu()
            for index, source in enumerate(batch_rows):
                output_rows.append(
                    {
                        "source_row_id": source.row["row_id"],
                        "j_map_layer": layer,
                        "token_ids": list(self.selected_token_ids),
                        "token_labels": list(self.selected_token_labels),
                        "real_j_scores": [float(value) for value in real_scores[index].tolist()],
                        "identity_scores": [
                            float(value) for value in identity_scores[index].tolist()
                        ],
                    }
                )
            del residuals, matrix, real_scores, identity_hidden, identity_scores
            torch.cuda.empty_cache()
        return output_rows

    def selected_random_j_readouts(
        self, sources: Sequence[TraceSource]
    ) -> list[dict[str, Any]]:
        """Compute five frozen signed-permutation random-J controls at direct sites."""

        torch = self.torch
        grouped: dict[int, list[TraceSource]] = defaultdict(list)
        for source in sources:
            layer = source.row.get("j_map_layer")
            if isinstance(layer, int) and source.row.get("capture_position") in set(
                benchmark.DIRECT_POSITIONS
            ):
                grouped[layer].append(source)
        output_rows: list[dict[str, Any]] = []
        norm_weight = self.model.model.norm.weight
        lm_head_weight = self.model.lm_head.weight

        def permutation(seed: int, layer: int, side: str) -> tuple[Any, Any]:
            key = (seed, layer, side)
            cached = self._random_transport_cache.get(key)
            if cached is not None:
                return cached
            side_offset = 0 if side == "input" else 1
            rng = random.Random(seed + 10_000_019 * layer + side_offset * 1_000_003)
            indexes = list(range(MODEL_WIDTH))
            rng.shuffle(indexes)
            signs = [1 if rng.getrandbits(1) else -1 for _ in range(MODEL_WIDTH)]
            result = (
                torch.tensor(indexes, device="cuda", dtype=torch.long),
                torch.tensor(signs, device="cuda", dtype=torch.bfloat16),
            )
            self._random_transport_cache[key] = result
            return result

        for layer in sorted(grouped):
            batch_rows = sorted(grouped[layer], key=lambda source: source.row["row_id"])
            residuals = torch.stack([row.residual for row in batch_rows]).to(
                device="cuda", dtype=torch.bfloat16
            )
            matrix = self.jlens_checkpoint["J"][layer].to(
                device="cuda", dtype=torch.bfloat16
            )
            for seed in benchmark.RANDOM_TRANSPORT_SEEDS:
                input_perm, input_sign = permutation(int(seed), layer, "input")
                output_perm, output_sign = permutation(int(seed), layer, "output")
                scrambled = residuals[:, input_perm] * input_sign
                transported = (scrambled @ matrix.T)[:, output_perm] * output_sign
                normalized = readouts.llama_rms_norm(
                    transported.to(dtype=norm_weight.dtype),
                    norm_weight,
                    eps=self.rms_eps,
                )
                scores = readouts.selected_lm_head_logits(
                    normalized,
                    lm_head_weight,
                    self.selected_token_ids,
                    row_batch_size=64,
                ).detach().cpu()
                for index, source in enumerate(batch_rows):
                    output_rows.append(
                        {
                            "source_row_id": source.row["row_id"],
                            "capture_position": source.row["capture_position"],
                            "j_map_layer": layer,
                            "random_transport_seed": int(seed),
                            "token_ids": list(self.selected_token_ids),
                            "token_labels": list(self.selected_token_labels),
                            "scores": [float(value) for value in scores[index].tolist()],
                        }
                    )
                del scrambled, transported, normalized, scores
            del residuals, matrix
            torch.cuda.empty_cache()
        if any(
            row["capture_position"] not in set(benchmark.DIRECT_POSITIONS)
            for row in output_rows
        ):
            raise SealedExecutionError(
                "random_j_checkpoint", "random-J escaped the frozen direct positions"
            )
        return output_rows

    def packed_vocabulary_readouts(
        self, sources: Sequence[TraceSource]
    ) -> PackedVocabularyPayload:
        """Materialize registered real-J vocabulary rows and frozen contrasts."""

        torch = self.torch
        grouped: dict[int, list[TraceSource]] = defaultdict(list)
        checkpoints = set(benchmark.VOCABULARY_CHECKPOINTS)
        for source in sources:
            layer = source.row.get("j_map_layer")
            if isinstance(layer, int) and source.row.get("capture_position") in checkpoints:
                grouped[layer].append(source)
        packed_rows: list[PackedVocabularyRow] = []
        norm_weight = self.model.model.norm.weight
        lm_head_weight = self.model.lm_head.weight

        def append_row(
            *,
            logical_kind: str,
            checkpoint: str,
            k: int,
            layer: int,
            source_row_ids: Sequence[str],
            tensors: Mapping[str, Any],
            arm: str | None = None,
            probe_role: str | None = None,
            dose_stratum: str | None = None,
            contrast_id: str | None = None,
        ) -> None:
            readouts.validate_vocab_materialization(
                checkpoint=checkpoint, k=k, contrast_id=contrast_id
            )
            row_id = stable_id(
                "packed-vocabulary-row",
                logical_kind,
                checkpoint,
                str(k),
                str(layer),
                *(str(value) for value in source_row_ids),
                contrast_id or "raw",
                length=32,
            )
            metadata = {
                "packed_row_id": row_id,
                "logical_kind": logical_kind,
                "checkpoint": checkpoint,
                "k": int(k),
                "j_map_layer": int(layer),
                "arm": arm,
                "probe_role": probe_role,
                "dose_stratum": dose_stratum,
                "contrast_id": contrast_id,
                "source_row_ids": [str(value) for value in source_row_ids],
                "tensor_fields": list(tensors),
            }
            packed_rows.append(
                PackedVocabularyRow(
                    metadata=metadata,
                    tensors={
                        str(key): value.detach().cpu().contiguous()
                        for key, value in tensors.items()
                    },
                )
            )

        required_arms = {
            "never",
            "target_supp",
            "target_amp",
            "matched_supp",
            "matched_amp",
            "isotropic_supp",
            "isotropic_amp",
        }
        for layer in sorted(grouped):
            batch_rows = sorted(grouped[layer], key=lambda source: source.row["row_id"])
            residuals = torch.stack([source.residual for source in batch_rows]).to(
                device="cuda", dtype=torch.bfloat16
            )
            matrix = self.jlens_checkpoint["J"][layer].to(
                device="cuda", dtype=torch.bfloat16
            )
            _transported, normalized = readouts.jlens_normalized_hidden(
                residuals,
                matrix,
                norm_weight,
                eps=self.rms_eps,
                row_batch_size=64,
                transport_dtype=torch.bfloat16,
            )
            scores = benchmark._chunked_full_vocab_logits(
                normalized, lm_head_weight, chunk_size=benchmark.VOCAB_CHUNK_SIZE
            )
            score_by_id = {
                source.row["row_id"]: scores[index]
                for index, source in enumerate(batch_rows)
            }
            for source in batch_rows:
                checkpoint = str(source.row["capture_position"])
                k = int(benchmark.VOCABULARY_TOP_K_BY_CHECKPOINT[checkpoint])
                raw = benchmark._stable_raw_topk(
                    score_by_id[source.row["row_id"]].unsqueeze(0), k=k
                )
                append_row(
                    logical_kind="raw_topk",
                    checkpoint=checkpoint,
                    k=k,
                    layer=layer,
                    source_row_ids=[source.row["row_id"]],
                    tensors={key: value[0] for key, value in raw.items()},
                    arm=str(source.row["condition_name"]),
                    probe_role=source.lineage.get("probe_role"),
                    dose_stratum=source.lineage.get("dose_stratum"),
                )

            by_checkpoint: dict[str, list[TraceSource]] = defaultdict(list)
            for source in batch_rows:
                by_checkpoint[str(source.row["capture_position"])].append(source)
            for checkpoint, checkpoint_rows in sorted(by_checkpoint.items()):
                k = int(benchmark.VOCABULARY_TOP_K_BY_CHECKPOINT[checkpoint])
                arm_maps: list[tuple[str, dict[str, TraceSource]]] = []
                if checkpoint.startswith("fixed_"):
                    for stratum in ("literal", "calibrated_sensitivity"):
                        arm_map: dict[str, TraceSource] = {}
                        for source in checkpoint_rows:
                            name = str(source.row["condition_name"])
                            if name == "clean":
                                arm_map["never"] = source
                            elif stratum == "literal" and not name.endswith("_calibrated"):
                                arm_map[name] = source
                            elif stratum == "calibrated_sensitivity" and name.endswith(
                                "_calibrated"
                            ):
                                arm_map[name.removesuffix("_calibrated")] = source
                        arm_maps.append((stratum, arm_map))
                else:
                    arm_map = {}
                    for source in checkpoint_rows:
                        if checkpoint != "event0" and source.lineage.get("probe_role") != "active":
                            continue
                        name = str(source.row["condition_name"])
                        if name != "sham":
                            arm_map[name] = source
                    arm_maps.append(("literal", arm_map))

                for stratum, arm_map in arm_maps:
                    if set(arm_map) != required_arms:
                        raise SealedExecutionError(
                            "vocab_contrast_arms",
                            f"{checkpoint}/{stratum} contrast arms differ",
                        )
                    for contrast_id in benchmark.VOCABULARY_CONTRASTS[:6]:
                        arm = str(contrast_id).removesuffix("_minus_never")
                        left = arm_map[arm]
                        right = arm_map["never"]
                        pair = benchmark.pack_pair_delta_union(
                            score_by_id[left.row["row_id"]],
                            score_by_id[right.row["row_id"]],
                            k=k,
                        )
                        append_row(
                            logical_kind="pair_delta_union",
                            checkpoint=checkpoint,
                            k=k,
                            layer=layer,
                            source_row_ids=[left.row["row_id"], right.row["row_id"]],
                            tensors=pair,
                            dose_stratum=stratum,
                            contrast_id=str(contrast_id),
                        )
                    sign_sources = [
                        arm_map[name]
                        for name in (
                            "target_supp",
                            "target_amp",
                            "matched_supp",
                            "matched_amp",
                        )
                    ]
                    sign = benchmark.pack_four_arm_sign_union(
                        *(score_by_id[source.row["row_id"]] for source in sign_sources),
                        k=k,
                    )
                    append_row(
                        logical_kind="four_arm_sign_union",
                        checkpoint=checkpoint,
                        k=k,
                        layer=layer,
                        source_row_ids=[source.row["row_id"] for source in sign_sources],
                        tensors=sign,
                        dose_stratum=stratum,
                        contrast_id=str(benchmark.VOCABULARY_CONTRASTS[-1]),
                    )
            del residuals, matrix, _transported, normalized, scores, score_by_id
            torch.cuda.empty_cache()
        if len({row.metadata["packed_row_id"] for row in packed_rows}) != len(packed_rows):
            raise SealedExecutionError("packed_row_duplicate", "packed row IDs are duplicated")
        return PackedVocabularyPayload(rows=packed_rows)


def trace_prediction_binding(
    *,
    predicted_token_id: int,
    prefix_seed: int,
    paired_stream_id: str,
    decode_step: int,
    sampler_receipt: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Create and optionally cross-check one exact source-row sampling binding."""

    uniform = hash_uniform_receipt(
        sampling_domain_hash=sampling_domain_hash(),
        prefix_seed=int(prefix_seed),
        paired_stream_id=str(paired_stream_id),
        decode_step=int(decode_step),
    ).as_dict()
    if sampler_receipt is not None and sampler_receipt.get("uniform_receipt") != uniform:
        raise SealedExecutionError(
            "trace_uniform_binding", "sampler receipt and source-row uniform differ"
        )
    if not 0 <= int(predicted_token_id) < TOKENIZER_SIZE:
        raise SealedExecutionError("trace_predicted_token", "predicted token is out of range")
    return {
        "predicted_token_id": int(predicted_token_id),
        "sampling_domain_hash": sampling_domain_hash(),
        "paired_stream_id": str(paired_stream_id),
        "decode_step": int(decode_step),
        "uniform_receipt_sha256": sha256_json(uniform),
    }


def bind_trace_predictions(
    traced: ForwardTrace,
    bindings_by_position: Mapping[str, Mapping[str, Any]],
) -> None:
    """Finalize every source row against the benchmark's exact 36-field schema."""

    observed_positions = {str(source.row["capture_position"]) for source in traced.sources}
    if observed_positions != set(bindings_by_position):
        raise SealedExecutionError(
            "trace_prediction_positions", "prediction bindings do not match trace positions"
        )
    counts: Counter[str] = Counter()
    for source in traced.sources:
        position = str(source.row["capture_position"])
        binding = dict(bindings_by_position[position])
        expected_fields = {
            "predicted_token_id",
            "sampling_domain_hash",
            "paired_stream_id",
            "decode_step",
            "uniform_receipt_sha256",
        }
        if set(binding) != expected_fields:
            raise SealedExecutionError(
                "trace_prediction_fields", "prediction binding fields differ"
            )
        expected_uniform_sha256 = sha256_json(
            hash_uniform_receipt(
                sampling_domain_hash=str(binding["sampling_domain_hash"]),
                prefix_seed=int(source.row["prefix_seed"]),
                paired_stream_id=str(binding["paired_stream_id"]),
                decode_step=int(binding["decode_step"]),
            ).as_dict()
        )
        if binding["uniform_receipt_sha256"] != expected_uniform_sha256:
            raise SealedExecutionError(
                "trace_prefix_seed_binding", "prediction receipt uses another prefix seed"
            )
        candidate = {**source.row, **binding}
        try:
            validated = benchmark.validate_source_index_row(candidate)
        except Exception as exc:
            raise SealedExecutionError(
                "source_index_schema", "source row violates the benchmark schema"
            ) from exc
        source.row = {
            field: validated[field] for field in benchmark.SOURCE_INDEX_FIELDS
        }
        source.lineage.pop("lineage_sha256", None)
        source.lineage["prediction_binding_sha256"] = sha256_json(binding)
        source.lineage["lineage_sha256"] = sha256_json(source.lineage)
        counts[position] += 1
    if set(counts.values()) != {36}:
        raise SealedExecutionError(
            "trace_state_count", "each captured position must have exactly 36 states"
        )


def _sample(
    runtime: PinnedRuntime,
    logits: Any,
    *,
    prefix_seed: int,
    stream_id: str,
    decode_step: int,
) -> tuple[int, dict[str, Any]]:
    decision = inverse_cdf_sample(
        logits,
        sampling_domain_hash=sampling_domain_hash(),
        prefix_seed=int(prefix_seed),
        paired_stream_id=str(stream_id),
        decode_step=decode_step,
        temperature=TEMPERATURE,
        top_p=TOP_P,
        top_k=TOP_K,
    )
    return decision.token_id, decision.as_dict()


def realize_one_prefix(runtime: PinnedRuntime, row: Mapping[str, Any]) -> dict[str, Any]:
    """Generate one sealed 96-token occurrence and its clean 64-token twin."""

    torch = runtime.torch
    prompt = torch.tensor([runtime.prompt_ids], device="cuda", dtype=torch.long)
    output = runtime.plain_forward(prompt)
    prefix_ids: list[int] = []
    prefix_decisions: list[dict[str, Any]] = []
    token, receipt = _sample(
        runtime,
        output.logits[0, -1],
        prefix_seed=int(row["prefix_seed"]),
        stream_id=str(row["clean_paired_stream_id"]),
        decode_step=0,
    )
    prefix_ids.append(token)
    prefix_decisions.append(receipt)
    past = output.past_key_values
    for step in range(1, PREFIX_TOKENS):
        if prefix_ids[-1] in runtime.eos_ids:
            break
        current = torch.tensor([[prefix_ids[-1]]], device="cuda", dtype=torch.long)
        output = runtime.plain_forward(current, past_key_values=past)
        past = output.past_key_values
        token, receipt = _sample(
            runtime,
            output.logits[0, -1],
            prefix_seed=int(row["prefix_seed"]),
            stream_id=str(row["clean_paired_stream_id"]),
            decode_step=step,
        )
        prefix_ids.append(token)
        prefix_decisions.append(receipt)
    prefix_success = len(prefix_ids) == PREFIX_TOKENS and not any(
        token_id in runtime.eos_ids for token_id in prefix_ids
    )
    failure_code = None if prefix_success else "clean_prefix_early_eos"
    continuation_ids: list[int] = []
    continuation_decisions: list[dict[str, Any]] = []
    terminal_reason: str | None = None
    if prefix_success:
        pending = prefix_ids[-1]
        for step in range(MAIN_POST_EVENT_TOKENS):
            current = torch.tensor([[pending]], device="cuda", dtype=torch.long)
            output = runtime.plain_forward(current, past_key_values=past)
            past = output.past_key_values
            token, receipt = _sample(
                runtime,
                output.logits[0, -1],
                prefix_seed=int(row["prefix_seed"]),
                stream_id=str(row["main_paired_stream_id"]),
                decode_step=step,
            )
            continuation_ids.append(token)
            continuation_decisions.append(receipt)
            pending = token
            if token in runtime.eos_ids:
                terminal_reason = "eos"
                break
        if terminal_reason is None:
            terminal_reason = "cap"
    prefix_text = runtime.tokenizer.decode(
        prefix_ids, skip_special_tokens=False, clean_up_tokenization_spaces=False
    )
    continuation_text = runtime.tokenizer.decode(
        continuation_ids, skip_special_tokens=False, clean_up_tokenization_spaces=False
    )
    raw = {
        "schema_version": RUN_SCHEMA_VERSION,
        "study_id": STUDY_ID,
        "prefix_id": row["prefix_id"],
        "prefix_index": row["prefix_index"],
        "prefix_seed": row["prefix_seed"],
        "sampling_domain_hash": row["sampling_domain_hash"],
        "prompt_text": SELF_REFERENCE_PROMPT,
        "prompt_token_ids": list(runtime.prompt_ids),
        "prompt_token_ids_sha256": _token_ids_sha256(runtime.prompt_ids),
        "prefix_token_ids": prefix_ids,
        "prefix_text": prefix_text,
        "prefix_sampler_receipts": prefix_decisions,
        "clean_continuation_token_ids": continuation_ids,
        "clean_continuation_text": continuation_text,
        "clean_continuation_sampler_receipts": continuation_decisions,
        "clean_continuation_terminal_reason": terminal_reason,
        "status": "pass" if prefix_success else "fail",
        "failure_code": failure_code,
    }
    raw_bytes = canonical_json_bytes(raw)
    compact = {
        "schema_version": RUN_SCHEMA_VERSION,
        "study_id": STUDY_ID,
        "prefix_id": row["prefix_id"],
        "prefix_index": row["prefix_index"],
        "status": raw["status"],
        "failure_code": failure_code,
        "prefix_token_count": len(prefix_ids),
        "prefix_token_ids_sha256": _token_ids_sha256(prefix_ids),
        "prefix_text_sha256": sha256_text(prefix_text),
        "clean_continuation_token_count": len(continuation_ids),
        "clean_continuation_token_ids_sha256": _token_ids_sha256(continuation_ids),
        "clean_continuation_text_sha256": sha256_text(continuation_text),
        "clean_continuation_terminal_reason": terminal_reason,
        "raw_record_sha256": hashlib.sha256(raw_bytes).hexdigest(),
        "raw_record_bytes": len(raw_bytes),
    }
    return {"raw": raw, "compact": compact}


def _prefix_plan_rows(plan_dir: Path) -> list[dict[str, Any]]:
    rows = _read_plan_json(plan_dir, "prefix_plan.jsonl")
    if len(rows) != N_PREFIXES:
        raise SealedExecutionError("prefix_plan_count", "prefix plan count differs")
    return sorted(rows, key=lambda row: int(row["prefix_execution_order"]))


def realize_prefix_bank(
    *,
    bindings: ExecutionBindings,
    cache_dir: Path,
    artifact_receipt_path: Path,
    run_id: str,
    runtime_factory: Callable[..., PinnedRuntime] = PinnedRuntime,
) -> dict[str, Any]:
    root = paths.require_external_artifact_root(
        expected_volume_id=bindings.volume_id, write_read_probe=True
    )
    cache = cache_dir.expanduser().resolve(strict=True)
    try:
        cache.relative_to(root)
    except ValueError as exc:
        raise SealedExecutionError("cache_outside_volume", "cache must be on external volume") from exc
    artifact = load_json_receipt(artifact_receipt_path, label="artifact receipt")
    runtime = runtime_factory(cache, artifact_receipt=artifact)
    fixed_rows = _read_plan_json(bindings.plan_dir, "fixed_token_plan.jsonl")
    runtime.validate_vector_inventory(fixed_rows, bindings.vector_inventory)
    runtime.prepare_target_prompt()
    run = RunTransaction.start(
        phase="confirmatory",
        run_id=run_id,
        artifact_root=root,
        expected_volume_id=bindings.volume_id,
        metadata={**bindings.as_metadata(), "outcome_content": "sealed_prefix_bank"},
    )
    counts: Counter[str] = Counter()
    failures: Counter[str] = Counter()
    started = time.monotonic()
    for row in _prefix_plan_rows(bindings.plan_dir):
        block = run.begin_block(str(row["prefix_id"]))
        try:
            result = realize_one_prefix(runtime, row)
            block.write_json("prefix.raw.json", result["raw"])
            block.write_json("prefix_receipt.json", result["compact"])
            block.complete(
                metadata={
                    "prefix_id": row["prefix_id"],
                    "status": result["compact"]["status"],
                    "failure_code": result["compact"]["failure_code"],
                }
            )
            counts[result["compact"]["status"]] += 1
            if result["compact"]["failure_code"]:
                failures[result["compact"]["failure_code"]] += 1
        except Exception as exc:
            code = exc.code if isinstance(exc, SealedExecutionError) else "prefix_runtime_failure"
            block.write_json(
                "prefix_receipt.json",
                {
                    "schema_version": RUN_SCHEMA_VERSION,
                    "study_id": STUDY_ID,
                    "prefix_id": row["prefix_id"],
                    "prefix_index": row["prefix_index"],
                    "status": "fail",
                    "failure_code": code,
                    "prefix_token_count": 0,
                    "prefix_token_ids_sha256": sha256_json([]),
                    "prefix_text_sha256": sha256_text(""),
                    "clean_continuation_token_count": 0,
                    "clean_continuation_token_ids_sha256": sha256_json([]),
                    "clean_continuation_text_sha256": sha256_text(""),
                    "clean_continuation_terminal_reason": None,
                    "raw_record_sha256": None,
                    "raw_record_bytes": 0,
                },
            )
            block.complete(
                metadata={"prefix_id": row["prefix_id"], "status": "fail", "failure_code": code}
            )
            counts["fail"] += 1
            failures[code] += 1
    final = run.complete(
        metadata={
            "successful_prefixes": counts["pass"],
            "failed_prefixes": counts["fail"],
            "failure_code_counts": dict(sorted(failures.items())),
            "threshold_pass": counts["pass"] >= MIN_COMPLETE_PREFIXES,
            "elapsed_seconds": time.monotonic() - started,
        }
    )
    complete = verify_completed_run(final)
    return {
        "status": "pass" if counts["pass"] >= MIN_COMPLETE_PREFIXES else "fail",
        "phase": "realize-prefix-bank",
        "run_id": run_id,
        "successful_prefixes": counts["pass"],
        "failed_prefixes": counts["fail"],
        "failure_code_counts": dict(sorted(failures.items())),
        "manifest_sha256": complete["manifest_sha256"],
    }


def _block_manifest_metadata(block: Path) -> dict[str, Any]:
    verify_completed_block(block)
    manifest = json.loads((block / BLOCK_MANIFEST).read_text(encoding="utf-8"))
    metadata = manifest.get("metadata")
    if not isinstance(metadata, dict):
        raise SealedExecutionError("block_metadata", "block metadata is invalid")
    return metadata


def build_prefix_bank_receipt(
    *,
    bindings: ExecutionBindings,
    prefix_bank_run_id: str,
) -> dict[str, Any]:
    """Read only compact child receipts and build the automatic Git-safe record."""

    root = paths.require_external_artifact_root(
        expected_volume_id=bindings.volume_id, write_read_probe=False
    )
    run_dir = root / "confirmatory" / prefix_bank_run_id
    verification = verify_completed_run(run_dir)
    blocks = sorted((run_dir / "blocks").iterdir())
    if len(blocks) != N_PREFIXES:
        raise SealedExecutionError("prefix_block_count", "sealed prefix-bank count differs")
    compact_rows: list[dict[str, Any]] = []
    for block in blocks:
        verify_completed_block(block)
        receipt_path = block / "prefix_receipt.json"
        if not receipt_path.is_file():
            raise SealedExecutionError("prefix_child_receipt", "compact child receipt is missing")
        row = json.loads(receipt_path.read_text(encoding="utf-8"))
        forbidden = RAW_OUTPUT_KEYS & {str(key).lower() for key in row}
        if forbidden:
            raise SealedExecutionError("prefix_child_content", "compact child contains raw fields")
        compact_rows.append(row)
    if len({row.get("prefix_id") for row in compact_rows}) != N_PREFIXES:
        raise SealedExecutionError("prefix_child_identity", "prefix child IDs differ")
    successes = sum(row.get("status") == "pass" for row in compact_rows)
    failures = N_PREFIXES - successes
    codes = Counter(
        str(row.get("failure_code"))
        for row in compact_rows
        if row.get("status") != "pass"
    )
    payload: dict[str, Any] = {
        "schema_version": PREFIX_RECEIPT_SCHEMA_VERSION,
        "status": "pass" if successes >= MIN_COMPLETE_PREFIXES else "fail",
        "study_id": STUDY_ID,
        "protocol_version": PROTOCOL_VERSION,
        "created_at_utc": utc_now(),
        "automatic_receipt": True,
        "content_included": False,
        "design_changes": [],
        "plan_hash": bindings.plan_hash,
        "plan_manifest_sha256": bindings.plan_manifest_sha256,
        "pre_prefix_freeze_sha": bindings.pre_prefix_freeze_sha,
        "registration_id": bindings.registration_id,
        "sampling_domain_hash": sampling_domain_hash(),
        "prefix_bank_phase": "confirmatory",
        "prefix_bank_run_id": prefix_bank_run_id,
        "prefix_bank_manifest_sha256": verification["manifest_sha256"],
        "prefix_bank_file_count": verification["file_count"],
        "prefix_bank_payload_bytes": verification["payload_bytes"],
        "planned_prefixes": N_PREFIXES,
        "successful_prefixes": successes,
        "failed_prefixes": failures,
        "minimum_successful_prefixes": MIN_COMPLETE_PREFIXES,
        "failure_code_counts": dict(sorted(codes.items())),
        "compact_row_inventory_sha256": sha256_json(
            sorted(
                [
                    {
                        "prefix_id": row["prefix_id"],
                        "status": row["status"],
                        "failure_code": row["failure_code"],
                        "prefix_token_count": row["prefix_token_count"],
                        "prefix_token_ids_sha256": row["prefix_token_ids_sha256"],
                        "prefix_text_sha256": row["prefix_text_sha256"],
                        "clean_continuation_token_count": row[
                            "clean_continuation_token_count"
                        ],
                        "clean_continuation_token_ids_sha256": row[
                            "clean_continuation_token_ids_sha256"
                        ],
                        "clean_continuation_text_sha256": row[
                            "clean_continuation_text_sha256"
                        ],
                        "clean_continuation_terminal_reason": row[
                            "clean_continuation_terminal_reason"
                        ],
                    }
                    for row in compact_rows
                ],
                key=lambda row: row["prefix_id"],
            )
        ),
    }
    payload["receipt_sha256"] = embedded_receipt_sha256(payload)
    return payload


def write_compact_receipt(path: Path, receipt: Mapping[str, Any]) -> None:
    assert_content_free_status(receipt)
    destination = path.expanduser().resolve(strict=False)
    if destination.exists() or destination.is_symlink():
        raise SealedExecutionError("compact_receipt_exists", "refusing to overwrite receipt")
    destination.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(destination, dict(receipt))


def _load_prefix_raw(root: Path, run_id: str, prefix_id: str) -> dict[str, Any]:
    block = root / "confirmatory" / run_id / "blocks" / prefix_id
    verify_completed_block(block)
    payload = json.loads((block / "prefix.raw.json").read_text(encoding="utf-8"))
    if payload.get("study_id") != STUDY_ID or payload.get("prefix_id") != prefix_id:
        raise SealedExecutionError("prefix_raw_identity", "sealed prefix identity differs")
    if payload.get("status") != "pass":
        raise SealedExecutionError("prefix_unusable", "prefix did not reach branch boundary")
    prefix_ids = payload.get("prefix_token_ids")
    if not isinstance(prefix_ids, list) or len(prefix_ids) != PREFIX_TOKENS:
        raise SealedExecutionError("prefix_raw_tokens", "sealed prefix length differs")
    return payload


def _arm_switch(
    switch: Layer50SwitchHook | None,
    input_ids: Any,
    *,
    forward_id: str,
    event_time: int | str | None,
) -> None:
    if switch is not None:
        switch.arm(
            [True] * int(input_ids.shape[1]),
            forward_id=forward_id,
            event_time=event_time,
        )


def _new_switch(runtime: PinnedRuntime, vector: Any, *, active: bool) -> Layer50SwitchHook | None:
    if not active:
        return None
    switch = Layer50SwitchHook(vector, capture_to_cpu=True).register(
        runtime.model.model.layers[SAE_LAYER]
    )
    runtime._active_switches.append(switch)
    setattr(switch, "_sealed_runtime", runtime)
    return switch


def _finish_switch(switch: Layer50SwitchHook | None, expected_calls: int) -> dict[str, Any]:
    if switch is None:
        return {
            "registration_count": 0,
            "hook_call_count": 0,
            "removal_count": 0,
            "selected_position_count": 0,
            "call_receipts": [],
        }
    switch.remove()
    switch.validate_complete(expected_calls=expected_calls)
    telemetry = switch.telemetry()
    runtime = getattr(switch, "_sealed_runtime", None)
    if runtime is not None and switch in runtime._active_switches:
        runtime._active_switches.remove(switch)
    if telemetry["unconsumed_captures"] != 0:
        raise SealedExecutionError("hook_capture_unconsumed", "hook captures remain")
    return telemetry


def _abort_active_switches(runtime: PinnedRuntime) -> None:
    """Remove every hook left behind by a failed whole-block attempt."""

    failures: list[str] = []
    for switch in list(runtime._active_switches):
        try:
            switch.__exit__(RuntimeError, RuntimeError("whole-block abort"), None)
        except Exception:
            failures.append("hook_removal_failed")
        finally:
            if switch in runtime._active_switches:
                runtime._active_switches.remove(switch)
    if failures:
        raise SealedExecutionError("hook_abort_failure", "failed hook could not be removed")


@contextmanager
def switch_cleanup_guard(runtime: PinnedRuntime) -> Iterable[None]:
    """Remove only switches created inside one causal operation on all exits."""

    baseline = {id(switch) for switch in runtime._active_switches}
    try:
        yield
    finally:
        failures = 0
        for switch in list(runtime._active_switches):
            if id(switch) in baseline:
                continue
            try:
                switch.__exit__(RuntimeError, RuntimeError("operation abort"), None)
            except Exception:
                failures += 1
            finally:
                if switch in runtime._active_switches:
                    runtime._active_switches.remove(switch)
        if failures and sys.exc_info()[0] is None:
            raise SealedExecutionError(
                "hook_cleanup_failure", "operation hook cleanup failed"
            )


def _clean_boundary(
    runtime: PinnedRuntime,
    prefix_ids: Sequence[int],
    *,
    prefix_id: str,
    prefix_row: Mapping[str, Any],
) -> tuple[Any, int, str, list[TraceSource]]:
    torch = runtime.torch
    input_ids = torch.tensor(
        [[*runtime.prompt_ids, *[int(value) for value in prefix_ids[:95]]]],
        device="cuda",
        dtype=torch.long,
    )
    prompt_length = len(runtime.prompt_ids)
    positions = {
        f"pre_y{predicted}": prompt_length + predicted - 1
        for predicted in range(64, 96)
    }
    clean_condition = {"intervention_role": "clean"}
    clean_vector = runtime._construct_intervention_vector(clean_condition)
    traced = runtime.traced_forward(
        input_ids,
        past_key_values=None,
        switch=None,
        forward_id=f"{prefix_id}-shared-clean-boundary",
        event_time=-1,
        positions=positions,
        base_metadata={
            "branch": "shared_clean",
            "branch_id": stable_id("shared-clean", prefix_id, length=32),
            "condition_key": "shared_clean",
            "condition_name": "clean",
            "condition_sha256": sha256_json(clean_condition),
            "intervention_role": "clean",
            "intervention_sha256": tensor_sha256(clean_vector),
            "parent_cache_sha256": sha256_json({"cache": "none"}),
            "trace_role": "pre_window",
            "sampled_output": True,
        },
    )
    bind_trace_predictions(
        traced,
        {
            label: trace_prediction_binding(
                predicted_token_id=int(prefix_ids[int(label.removeprefix("pre_y"))]),
                prefix_seed=int(prefix_row["prefix_seed"]),
                paired_stream_id=str(prefix_row["clean_paired_stream_id"]),
                decode_step=int(label.removeprefix("pre_y")),
            )
            for label in positions
        },
    )
    del clean_vector
    cache = traced.output.past_key_values
    cache_hash = traced.output_cache_sha256
    return cache, int(prefix_ids[95]), cache_hash, traced.sources


def _generate_main_branch_unchecked(
    runtime: PinnedRuntime,
    row: Mapping[str, Any],
    *,
    clean_cache: Any,
    expected_cache_sha256: str,
    pending_y95: int,
) -> BranchResult:
    torch = runtime.torch
    cache = clone_kv_cache(clean_cache)
    observed_cache_hash = cache_tensor_sha256(cache)
    if observed_cache_hash != expected_cache_sha256:
        raise SealedExecutionError("fork_cache_hash", "branch fork cache differs")
    vector = runtime.intervention_vector(
        row["condition"],
        condition_key=(
            None
            if row["branch"] in {"never", "sham"}
            else vector_condition_key(str(row["aggregate_block_id"]), str(row["branch"]))
        ),
    )
    condition_key = (
        str(row["branch"])
        if row["branch"] in {"never", "sham"}
        else vector_condition_key(str(row["aggregate_block_id"]), str(row["branch"]))
    )
    vector_sha256 = tensor_sha256(vector)
    active = row["branch"] != "never"
    switch = _new_switch(runtime, vector, active=active)
    expected_calls = 0
    pending = int(pending_y95)
    tokens: list[int] = []
    decisions: list[dict[str, Any]] = []
    traces: list[TraceSource] = []
    actual_rows: list[dict[str, Any]] = []
    full_logit_hashes: list[str] = []
    terminal_reason = "cap"
    parent_cache_sha256 = observed_cache_hash
    try:
        for step in range(MAIN_POST_EVENT_TOKENS):
            input_ids = torch.tensor([[pending]], device="cuda", dtype=torch.long)
            forward_id = f"{row['branch_id']}-main-{step:02d}"
            _arm_switch(switch, input_ids, forward_id=forward_id, event_time=step)
            expected_calls += int(switch is not None)
            checkpoint = "event0" if step == 0 else f"event{step}"
            traced = runtime.traced_forward(
                input_ids,
                past_key_values=cache,
                switch=switch,
                forward_id=forward_id,
                event_time=step,
                positions={checkpoint: -1},
                base_metadata={
                    "branch": row["branch"],
                    "branch_id": row["branch_id"],
                    "condition_key": condition_key,
                    "condition_name": row["branch"],
                    "condition_sha256": sha256_json(row["condition"]),
                    "intervention_role": row["condition"]["intervention_role"],
                    "intervention_sha256": vector_sha256,
                    "parent_cache_sha256": parent_cache_sha256,
                    "trace_role": "main_trajectory",
                    "event_step": step,
                    "dose_stratum": row["condition"].get("dose_scale"),
                    "sampled_output": True,
                },
            )
            cache = traced.output.past_key_values
            parent_cache_sha256 = traced.output_cache_sha256
            traces.extend(traced.sources)
            actual_rows.append(
                {
                    "forward_id": forward_id,
                    "capture_position": checkpoint,
                    "token_ids": list(runtime.selected_token_ids),
                    "token_labels": list(runtime.selected_token_labels),
                    "scores": traced.selected_actual_logits[checkpoint],
                }
            )
            full_logit_hashes.append(tensor_sha256(traced.output.logits[0, -1]))
            token, decision = _sample(
                runtime,
                traced.output.logits[0, -1],
                prefix_seed=int(row["prefix_seed"]),
                stream_id=str(row["main_paired_stream_id"]),
                decode_step=step,
            )
            bind_trace_predictions(
                traced,
                {
                    checkpoint: trace_prediction_binding(
                        predicted_token_id=token,
                        prefix_seed=int(row["prefix_seed"]),
                        paired_stream_id=str(row["main_paired_stream_id"]),
                        decode_step=step,
                        sampler_receipt=decision,
                    )
                },
            )
            tokens.append(token)
            decisions.append(decision)
            pending = token
            if token in runtime.eos_ids:
                terminal_reason = "eos"
                break
    finally:
        telemetry = _finish_switch(switch, expected_calls)
    text = runtime.tokenizer.decode(
        tokens, skip_special_tokens=False, clean_up_tokenization_spaces=False
    )
    return BranchResult(
        branch=str(row["branch"]),
        token_ids=tokens,
        text=text,
        terminal_reason=terminal_reason,
        sampler_receipts=decisions,
        full_logit_sha256=full_logit_hashes,
        traces=traces,
        actual_readouts=actual_rows,
        hook_telemetry=telemetry,
        cache_sha256=observed_cache_hash,
    )


def generate_main_branch(
    runtime: PinnedRuntime,
    row: Mapping[str, Any],
    *,
    clean_cache: Any,
    expected_cache_sha256: str,
    pending_y95: int,
) -> BranchResult:
    with switch_cleanup_guard(runtime):
        return _generate_main_branch_unchecked(
            runtime,
            row,
            clean_cache=clean_cache,
            expected_cache_sha256=expected_cache_sha256,
            pending_y95=pending_y95,
        )


def _generate_probe_unchecked(
    runtime: PinnedRuntime,
    template: Mapping[str, Any],
    branch_row: Mapping[str, Any] | None,
    branch_result: BranchResult | None,
    *,
    clean_cache: Any,
    expected_cache_sha256: str,
    pending_y95: int,
) -> ProbeResult | None:
    torch = runtime.torch
    event_time = template["event_time"]
    if event_time == -1:
        source_branch = "shared_clean"
        history_count = 0
        history_tokens: list[int] = []
        vector = torch.zeros(MODEL_WIDTH, device="cuda", dtype=torch.bfloat16)
        history_active = False
        query_active = False
        prefix_seed = int(branch_row["prefix_seed"]) if branch_row else 0
        condition_key = "shared_clean"
    else:
        if branch_row is None or branch_result is None:
            raise SealedExecutionError("probe_branch_missing", "probe branch is missing")
        source_branch = str(branch_row["branch"])
        resolved = resolve_probe_event_times(
            PROBE_EVENT_TIMES,
            generated_token_count=len(branch_result.token_ids),
            terminal_reason=branch_result.terminal_reason,
        )
        by_event = {row.event_time: row.resolved_step for row in resolved}
        if event_time not in by_event:
            return None
        history_count = int(by_event[event_time])
        history_tokens = branch_result.token_ids
        vector = runtime.intervention_vector(
            branch_row["condition"],
            condition_key=(
                None
                if branch_row["branch"] in {"never", "sham"}
                else vector_condition_key(
                    str(branch_row["aggregate_block_id"]), str(branch_row["branch"])
                )
            ),
        )
        history_active = source_branch != "never"
        query_active = template["probe_role"] == "active" and source_branch != "never"
        prefix_seed = int(branch_row["prefix_seed"])
        condition_key = (
            source_branch
            if source_branch in {"never", "sham"}
            else vector_condition_key(
                str(branch_row["aggregate_block_id"]), source_branch
            )
        )

    prefix_id = str(branch_row["prefix_id"]) if branch_row is not None else "missing-prefix"

    cache = clone_kv_cache(clean_cache)
    if cache_tensor_sha256(cache) != expected_cache_sha256:
        raise SealedExecutionError("probe_cache_hash", "probe fork cache differs")
    pending = int(pending_y95)
    switch = _new_switch(runtime, vector, active=history_active or query_active)
    hook_calls = 0
    for step in range(history_count):
        input_ids = torch.tensor([[pending]], device="cuda", dtype=torch.long)
        forward_id = f"{prefix_id}-{template['probe_template_id']}-history-{step:02d}"
        _arm_switch(switch, input_ids, forward_id=forward_id, event_time=step)
        hook_calls += int(switch is not None)
        output = runtime.plain_forward(input_ids, past_key_values=cache)
        if switch is not None:
            switch.pop_capture(expected_forward_id=forward_id)
        expected_token, _decision = _sample(
            runtime,
            output.logits[0, -1],
            prefix_seed=prefix_seed,
            stream_id=str(branch_row["main_paired_stream_id"]),
            decode_step=step,
        )
        if expected_token != int(history_tokens[step]):
            raise SealedExecutionError("probe_history_replay", "branch history replay differs")
        if branch_result is not None and tensor_sha256(output.logits[0, -1]) != (
            branch_result.full_logit_sha256[step]
        ):
            raise SealedExecutionError(
                "probe_history_logit_replay", "branch history logits differ"
            )
        cache = output.past_key_values
        pending = int(history_tokens[step])

    # Washout removes the history hook before query prefill.  Active probes keep
    # the same registered hook instance through query and answer generation.
    history_telemetry: dict[str, Any] | None = None
    if switch is not None and not query_active:
        history_telemetry = _finish_switch(switch, hook_calls)
        switch = None
        hook_calls = 0

    query_ids = runtime.render_query_input(pending)
    contextual_yes_no = runtime.validate_contextual_yes_no(query_ids)
    query_parent_cache_sha256 = cache_tensor_sha256(cache)
    input_ids = torch.tensor([query_ids], device="cuda", dtype=torch.long)
    forward_id = f"{prefix_id}-{template['probe_template_id']}-query"
    _arm_switch(switch, input_ids, forward_id=forward_id, event_time=event_time)
    hook_calls += int(switch is not None)
    checkpoint = str(template.get("capture_position") or "probe_clean_answer")
    traced = runtime.traced_forward(
        input_ids,
        past_key_values=cache,
        switch=switch,
        forward_id=forward_id,
        event_time=event_time,
        positions={checkpoint: -1},
        base_metadata={
            "branch": source_branch,
            "branch_id": (
                str(branch_row["branch_id"])
                if event_time != -1 and branch_row is not None and "branch_id" in branch_row
                else str(template["probe_template_id"])
            ),
            "condition_key": condition_key,
            "condition_name": source_branch,
            "condition_sha256": sha256_json(
                branch_row["condition"]
                if event_time != -1 and branch_row is not None
                else {"intervention_role": "clean"}
            ),
            "intervention_role": (
                branch_row["condition"]["intervention_role"]
                if event_time != -1 and branch_row is not None
                else "clean"
            ),
            "intervention_sha256": tensor_sha256(vector),
            "parent_cache_sha256": query_parent_cache_sha256,
            "contextual_yes_no_receipt_sha256": contextual_yes_no["receipt_sha256"],
            "probe_template_id": template["probe_template_id"],
            "probe_role": template["probe_role"],
            "trace_role": "probe_answer_predictor",
            "sampled_output": True,
        },
    )
    cache = traced.output.past_key_values
    answer_ids: list[int] = []
    decisions: list[dict[str, Any]] = []
    token, decision = _sample(
        runtime,
        traced.output.logits[0, -1],
        prefix_seed=prefix_seed,
        stream_id=str(template["paired_stream_namespace"]),
        decode_step=0,
    )
    answer_ids.append(token)
    decisions.append(decision)
    bind_trace_predictions(
        traced,
        {
            checkpoint: trace_prediction_binding(
                predicted_token_id=token,
                prefix_seed=prefix_seed,
                paired_stream_id=str(template["paired_stream_namespace"]),
                decode_step=0,
                sampler_receipt=decision,
            )
        },
    )
    terminal_reason = "eos" if token in runtime.eos_ids else "cap"
    for step in range(1, QUERY_ANSWER_MAX_TOKENS):
        if answer_ids[-1] in runtime.eos_ids:
            break
        input_ids = torch.tensor([[answer_ids[-1]]], device="cuda", dtype=torch.long)
        answer_forward_id = (
            f"{prefix_id}-{template['probe_template_id']}-answer-{step:03d}"
        )
        _arm_switch(switch, input_ids, forward_id=answer_forward_id, event_time=event_time)
        hook_calls += int(switch is not None)
        output = runtime.plain_forward(input_ids, past_key_values=cache)
        if switch is not None:
            switch.pop_capture(expected_forward_id=answer_forward_id)
        cache = output.past_key_values
        token, decision = _sample(
            runtime,
            output.logits[0, -1],
            prefix_seed=prefix_seed,
            stream_id=str(template["paired_stream_namespace"]),
            decode_step=step,
        )
        answer_ids.append(token)
        decisions.append(decision)
        if token in runtime.eos_ids:
            terminal_reason = "eos"
            break
    query_telemetry = _finish_switch(switch, hook_calls)
    telemetry = {
        "history": history_telemetry,
        "query_and_answer": query_telemetry,
    }
    answer_text = runtime.tokenizer.decode(
        answer_ids, skip_special_tokens=False, clean_up_tokenization_spaces=False
    )
    return ProbeResult(
        probe_template_id=str(template["probe_template_id"]),
        event_time=event_time,
        source_branch=source_branch,
        probe_role=str(template["probe_role"]),
        token_ids=answer_ids,
        text=answer_text,
        terminal_reason=terminal_reason,
        sampler_receipts=decisions,
        traces=traced.sources,
        actual_readouts=[
            {
                "forward_id": forward_id,
                "capture_position": checkpoint,
                "token_ids": list(runtime.selected_token_ids),
                "token_labels": list(runtime.selected_token_labels),
                "scores": traced.selected_actual_logits[checkpoint],
                "contextual_yes_no": contextual_yes_no,
            }
        ],
        hook_telemetry=telemetry,
    )


def generate_probe(
    runtime: PinnedRuntime,
    template: Mapping[str, Any],
    branch_row: Mapping[str, Any] | None,
    branch_result: BranchResult | None,
    *,
    clean_cache: Any,
    expected_cache_sha256: str,
    pending_y95: int,
) -> ProbeResult | None:
    with switch_cleanup_guard(runtime):
        return _generate_probe_unchecked(
            runtime,
            template,
            branch_row,
            branch_result,
            clean_cache=clean_cache,
            expected_cache_sha256=expected_cache_sha256,
            pending_y95=pending_y95,
        )


def validate_prefix_materialization_counts(
    *,
    stage: str,
    traces: Sequence[TraceSource],
    jlens_rows: Sequence[Mapping[str, Any]],
    random_j_rows: Sequence[Mapping[str, Any]],
    packed: PackedVocabularyPayload,
) -> dict[str, int]:
    """Enforce the benchmark's exact per-prefix scientific row allocation."""

    workload = benchmark.build_exact_workload(1)
    if stage == "stage2a":
        positions = (
            workload.pre_window_positions_per_prefix
            + workload.main_positions_per_prefix
            + workload.probe_positions_per_prefix
        )
        direct_positions = 8 + 10
        raw_k2000 = workload.raw_vocab_rows_k2000 - (
            workload.fixed_positions_per_prefix * workload.j_source_states_per_position
        )
        raw_k512 = workload.raw_vocab_rows_k512
        contrast_k2000 = 2 * len(benchmark.VOCABULARY_CONTRASTS) * (
            workload.j_source_states_per_position
        )
        contrast_k512 = workload.pair_contrast_rows_k512 + workload.sign_contrast_rows_k512
    elif stage == "stage2b":
        positions = workload.fixed_positions_per_prefix
        direct_positions = positions
        raw_k2000 = positions * workload.j_source_states_per_position
        raw_k512 = 0
        contrast_k2000 = 2 * 2 * len(benchmark.VOCABULARY_CONTRASTS) * (
            workload.j_source_states_per_position
        )
        contrast_k512 = 0
    else:
        raise SealedExecutionError("materialization_stage", "unknown materialization stage")

    expected_source_rows = positions * workload.source_states_per_position
    expected_j_rows = positions * workload.j_source_states_per_position
    expected_random_rows = (
        direct_positions
        * workload.j_source_states_per_position
        * len(benchmark.RANDOM_TRANSPORT_SEEDS)
    )
    if len(traces) != expected_source_rows:
        raise SealedExecutionError("source_row_count", "per-prefix source rows differ")
    position_counts: Counter[tuple[str, str]] = Counter()
    j_source_ids: set[str] = set()
    for source in traces:
        try:
            validated = benchmark.validate_source_index_row(source.row)
        except Exception as exc:
            raise SealedExecutionError("source_index_schema", "source index row differs") from exc
        if tuple(source.row) != benchmark.SOURCE_INDEX_FIELDS:
            raise SealedExecutionError("source_index_order", "source index column order differs")
        if source.lineage.get("row_id") != validated["row_id"]:
            raise SealedExecutionError("source_lineage_key", "source lineage row ID differs")
        position_counts[(validated["forward_id"], validated["capture_position"])] += 1
        if isinstance(validated["j_map_layer"], int):
            j_source_ids.add(str(validated["row_id"]))
    if len(position_counts) != positions or set(position_counts.values()) != {36}:
        raise SealedExecutionError("source_position_count", "source positions/states differ")
    if len(jlens_rows) != expected_j_rows or {
        str(row["source_row_id"]) for row in jlens_rows
    } != j_source_ids:
        raise SealedExecutionError("jlens_row_count", "all-trace J readouts differ")
    if len(random_j_rows) != expected_random_rows:
        raise SealedExecutionError("random_j_row_count", "random-J readout rows differ")
    random_counts = Counter(str(row["source_row_id"]) for row in random_j_rows)
    if set(random_counts.values()) != {len(benchmark.RANDOM_TRANSPORT_SEEDS)}:
        raise SealedExecutionError("random_j_seed_count", "random-J seed balance differs")

    packed_counts: Counter[tuple[str, int]] = Counter()
    for packed_row in packed.rows:
        kind = str(packed_row.metadata["logical_kind"])
        bucket = "raw" if kind == "raw_topk" else "contrast"
        packed_counts[(bucket, int(packed_row.metadata["k"]))] += 1
    expected_packed = {
        ("raw", 512): raw_k512,
        ("raw", 2000): raw_k2000,
        ("contrast", 512): contrast_k512,
        ("contrast", 2000): contrast_k2000,
    }
    if {key: packed_counts.get(key, 0) for key in expected_packed} != expected_packed or any(
        key not in expected_packed for key in packed_counts
    ):
        raise SealedExecutionError("packed_vocab_count", "packed vocabulary rows differ")
    return {
        "source_positions": positions,
        "source_rows": expected_source_rows,
        "jlens_rows": expected_j_rows,
        "random_j_rows": expected_random_rows,
        "packed_vocab_rows": len(packed.rows),
    }


def execute_stage2a_prefix(
    runtime: PinnedRuntime,
    *,
    prefix_payload: Mapping[str, Any],
    branch_rows: Sequence[Mapping[str, Any]],
    probe_templates: Sequence[Mapping[str, Any]],
) -> BlockPayload:
    prefix_ids = [int(value) for value in prefix_payload["prefix_token_ids"]]
    row_by_branch = {str(row["branch"]): row for row in branch_rows}
    if set(row_by_branch) != set(MAIN_BRANCHES):
        raise SealedExecutionError("branch_plan_rows", "prefix branch rows differ")
    clean_cache, pending_y95, clean_cache_hash, clean_traces = _clean_boundary(
        runtime,
        prefix_ids,
        prefix_id=str(prefix_payload["prefix_id"]),
        prefix_row=row_by_branch["never"],
    )
    branches: dict[str, BranchResult] = {}
    all_traces = list(clean_traces)
    branch_json: list[dict[str, Any]] = []
    actual: list[dict[str, Any]] = []
    for row in sorted(branch_rows, key=lambda item: int(item["branch_execution_order"])):
        result = generate_main_branch(
            runtime,
            row,
            clean_cache=clean_cache,
            expected_cache_sha256=clean_cache_hash,
            pending_y95=pending_y95,
        )
        branches[result.branch] = result
        all_traces.extend(result.traces)
        actual.extend(result.actual_readouts)
        branch_json.append(
            {
                "branch": result.branch,
                "branch_id": row["branch_id"],
                "planned_execution_order": row["execution_order"],
                "branch_execution_order": row["branch_execution_order"],
                "condition": row["condition"],
                "token_ids": result.token_ids,
                "text": result.text,
                "terminal_reason": result.terminal_reason,
                "sampler_receipts": result.sampler_receipts,
                "full_logit_sha256": result.full_logit_sha256,
                "hook_telemetry": result.hook_telemetry,
                "fork_cache_sha256": result.cache_sha256,
            }
        )
    if set(branches) != set(MAIN_BRANCHES):
        raise SealedExecutionError("branch_allocation", "eight-branch block is incomplete")
    # Sham and never deliberately share the paired stream; any difference is a
    # technical failure rather than a result to be interpreted.
    if branches["sham"].token_ids != branches["never"].token_ids:
        raise SealedExecutionError("sham_equivalence", "sham and never tokens differ")
    if branches["sham"].full_logit_sha256 != branches["never"].full_logit_sha256:
        raise SealedExecutionError("sham_logit_equivalence", "sham and never logits differ")

    probes_json: list[dict[str, Any]] = []
    for template in probe_templates:
        if template["event_time"] == -1:
            # Bind the shared clean probe to the current prefix seed while
            # keeping it independent of any branch condition.
            clean_row = row_by_branch["never"]
            result = generate_probe(
                runtime,
                template,
                clean_row,
                None,
                clean_cache=clean_cache,
                expected_cache_sha256=clean_cache_hash,
                pending_y95=pending_y95,
            )
        else:
            branch = str(template["source_branch"])
            result = generate_probe(
                runtime,
                template,
                row_by_branch[branch],
                branches[branch],
                clean_cache=clean_cache,
                expected_cache_sha256=clean_cache_hash,
                pending_y95=pending_y95,
            )
        if result is None:
            continue
        all_traces.extend(result.traces)
        actual.extend(result.actual_readouts)
        probes_json.append(
            {
                "probe_template_id": result.probe_template_id,
                "event_time": result.event_time,
                "source_branch": result.source_branch,
                "probe_role": result.probe_role,
                "token_ids": result.token_ids,
                "text": result.text,
                "terminal_reason": result.terminal_reason,
                "sampler_receipts": result.sampler_receipts,
                "hook_telemetry": result.hook_telemetry,
            }
        )
    jlens_rows = runtime.selected_jlens_readouts(all_traces)
    random_j_rows = runtime.selected_random_j_readouts(all_traces)
    packed = runtime.packed_vocabulary_readouts(all_traces)
    materialization_counts = validate_prefix_materialization_counts(
        stage="stage2a",
        traces=all_traces,
        jlens_rows=jlens_rows,
        random_j_rows=random_j_rows,
        packed=packed,
    )
    return BlockPayload(
        metadata={
            "prefix_id": prefix_payload["prefix_id"],
            "status": "pass",
            "stage": "stage2a",
            "main_branches": len(branch_json),
            "realized_probes": len(probes_json),
            "shared_cache_sha256": clean_cache_hash,
            "source_index_schema_sha256": benchmark.SOURCE_INDEX_SCHEMA_SHA256,
            **materialization_counts,
        },
        json_files={
            "main_branches.raw.json": branch_json,
            "probes.raw.json": probes_json,
            "actual_selected_readouts.json": actual,
            "jlens_selected_readouts.json": jlens_rows,
            "random_j_selected_readouts.json": random_j_rows,
        },
        traces=all_traces,
        packed_vocabulary=packed,
    )


def _full_fixed_input(runtime: PinnedRuntime, prefix_payload: Mapping[str, Any]) -> tuple[list[int], int, int]:
    prefix_ids = [int(value) for value in prefix_payload["prefix_token_ids"]]
    continuation = [
        int(value) for value in prefix_payload.get("clean_continuation_token_ids", [])
    ]
    assistant = [*prefix_ids, *continuation]
    if not assistant:
        raise SealedExecutionError("fixed_transcript_empty", "fixed transcript is empty")
    pending = assistant[-1]
    suffix = list(runtime.query_suffix_ids)
    if suffix and pending == suffix[0]:
        suffix = suffix[1:]
    full = [*runtime.prompt_ids, *assistant, *suffix]
    prequery = len(runtime.prompt_ids) + len(assistant) - 1
    fixed_answer = len(full) - 1
    return full, prequery, fixed_answer


def _execute_stage2b_prefix_unchecked(
    runtime: PinnedRuntime,
    *,
    prefix_payload: Mapping[str, Any],
    fixed_rows: Sequence[Mapping[str, Any]],
) -> BlockPayload:
    torch = runtime.torch
    full_ids, prequery, fixed_answer = _full_fixed_input(runtime, prefix_payload)
    contextual_yes_no = runtime.validate_contextual_yes_no(full_ids)
    input_ids = torch.tensor([full_ids], device="cuda", dtype=torch.long)
    traces: list[TraceSource] = []
    actual: list[dict[str, Any]] = []
    condition_rows: list[dict[str, Any]] = []
    for row in sorted(fixed_rows, key=lambda item: int(item["execution_order"])):
        vector = runtime.intervention_vector(
            row["condition"],
            condition_key=(
                None
                if row["condition_name"] == "clean"
                else vector_condition_key(
                    str(row["aggregate_block_id"]), str(row["condition_name"])
                )
            ),
        )
        condition_key = (
            "clean"
            if row["condition_name"] == "clean"
            else vector_condition_key(
                str(row["aggregate_block_id"]), str(row["condition_name"])
            )
        )
        active = row["condition_name"] != "clean"
        switch = _new_switch(runtime, vector, active=active)
        forward_id = f"{row['fixed_token_row_id']}-fixed"
        _arm_switch(switch, input_ids, forward_id=forward_id, event_time=0)
        traced = runtime.traced_forward(
            input_ids,
            past_key_values=None,
            switch=switch,
            forward_id=forward_id,
            event_time=0,
            positions={"fixed_prequery": prequery, "fixed_answer": fixed_answer},
            base_metadata={
                "condition_name": row["condition_name"],
                "condition_key": condition_key,
                "branch": "fixed_token",
                "branch_id": row["fixed_token_row_id"],
                "condition_sha256": sha256_json(row["condition"]),
                "intervention_role": row["condition"]["intervention_role"],
                "intervention_sha256": tensor_sha256(vector),
                "parent_cache_sha256": sha256_json({"cache": "none"}),
                "contextual_yes_no_receipt_sha256": contextual_yes_no[
                    "receipt_sha256"
                ],
                "fixed_token_row_id": row["fixed_token_row_id"],
                "dose_stratum": (
                    "calibrated_sensitivity"
                    if str(row["condition_name"]).endswith("_calibrated")
                    else "literal"
                ),
                "trace_role": "fixed_token_direct_effect",
                "sampled_output": False,
            },
        )
        if prequery + 1 >= len(full_ids):
            raise SealedExecutionError(
                "fixed_prequery_prediction", "fixed prequery has no next input token"
            )
        bind_trace_predictions(
            traced,
            {
                "fixed_prequery": trace_prediction_binding(
                    predicted_token_id=int(full_ids[prequery + 1]),
                    prefix_seed=int(row["prefix_seed"]),
                    paired_stream_id=str(row["paired_stream_id"]),
                    decode_step=0,
                ),
                "fixed_answer": trace_prediction_binding(
                    predicted_token_id=int(
                        torch.argmax(traced.output.logits[0, fixed_answer]).item()
                    ),
                    prefix_seed=int(row["prefix_seed"]),
                    paired_stream_id=str(row["paired_stream_id"]),
                    decode_step=1,
                ),
            },
        )
        telemetry = _finish_switch(switch, int(active))
        traces.extend(traced.sources)
        for checkpoint, scores in traced.selected_actual_logits.items():
            actual.append(
                {
                    "fixed_token_row_id": row["fixed_token_row_id"],
                    "condition_name": row["condition_name"],
                    "capture_position": checkpoint,
                    "token_ids": list(runtime.selected_token_ids),
                    "token_labels": list(runtime.selected_token_labels),
                    "scores": scores,
                    "contextual_yes_no": contextual_yes_no,
                }
            )
        condition_rows.append(
            {
                "fixed_token_row_id": row["fixed_token_row_id"],
                "condition_name": row["condition_name"],
                "condition": row["condition"],
                "input_token_count": len(full_ids),
                "input_token_ids_sha256": _token_ids_sha256(full_ids),
                "prequery_offset": prequery,
                "answer_predictor_offset": fixed_answer,
                "intervention_sha256": tensor_sha256(vector),
                "contextual_yes_no": contextual_yes_no,
                "hook_telemetry": telemetry,
            }
        )
        del traced.output
    if {row["condition_name"] for row in condition_rows} != set(FIXED_TOKEN_CONDITIONS):
        raise SealedExecutionError("fixed_allocation", "13-condition fixed block differs")
    jlens_rows = runtime.selected_jlens_readouts(traces)
    random_j_rows = runtime.selected_random_j_readouts(traces)
    packed = runtime.packed_vocabulary_readouts(traces)
    materialization_counts = validate_prefix_materialization_counts(
        stage="stage2b",
        traces=traces,
        jlens_rows=jlens_rows,
        random_j_rows=random_j_rows,
        packed=packed,
    )
    return BlockPayload(
        metadata={
            "prefix_id": prefix_payload["prefix_id"],
            "status": "pass",
            "stage": "stage2b",
            "fixed_conditions": len(condition_rows),
            "identical_token_ids": True,
            "input_token_ids_sha256": _token_ids_sha256(full_ids),
            "source_index_schema_sha256": benchmark.SOURCE_INDEX_SCHEMA_SHA256,
            **materialization_counts,
        },
        json_files={
            "fixed_conditions.json": condition_rows,
            "actual_selected_readouts.json": actual,
            "jlens_selected_readouts.json": jlens_rows,
            "random_j_selected_readouts.json": random_j_rows,
        },
        traces=traces,
        packed_vocabulary=packed,
    )


def execute_stage2b_prefix(
    runtime: PinnedRuntime,
    *,
    prefix_payload: Mapping[str, Any],
    fixed_rows: Sequence[Mapping[str, Any]],
) -> BlockPayload:
    with switch_cleanup_guard(runtime):
        return _execute_stage2b_prefix_unchecked(
            runtime, prefix_payload=prefix_payload, fixed_rows=fixed_rows
        )


def _write_trace_shards(block: BlockTransaction, traces: Sequence[TraceSource]) -> list[dict[str, Any]]:
    if not traces:
        raise SealedExecutionError("trace_empty", "block has no source residuals")
    torch = __import__("torch")
    receipts: list[dict[str, Any]] = []
    for shard_index, start in enumerate(range(0, len(traces), MAX_SOURCE_ROWS_PER_SHARD)):
        chunk = traces[start : start + MAX_SOURCE_ROWS_PER_SHARD]
        residuals = torch.stack([source.residual for source in chunk])
        receipt = block.write_source_shard(
            f"source-{shard_index:03d}", residuals, [source.row for source in chunk]
        )
        expected_columns = (
            *benchmark.SOURCE_INDEX_FIELDS,
            "source_shard",
            "source_row_offset",
        )
        if tuple(receipt.index_columns) != expected_columns:
            raise SealedExecutionError(
                "source_index_columns", "source Parquet columns differ from benchmark schema"
            )
        receipts.append(receipt.as_dict())
    return receipts


def _fsync_file(path: Path) -> None:
    with path.open("rb") as handle:
        os.fsync(handle.fileno())


def _write_source_lineage_table(
    block: BlockTransaction, traces: Sequence[TraceSource]
) -> dict[str, Any]:
    """Write noncanonical lineage separately, keyed one-to-one by source row ID."""

    import pyarrow as pa
    import pyarrow.parquet as pq

    records: list[dict[str, Any]] = []
    for source in sorted(traces, key=lambda item: item.row["row_id"]):
        lineage = dict(source.lineage)
        if lineage.get("row_id") != source.row["row_id"]:
            raise SealedExecutionError("lineage_row_id", "lineage/source row IDs differ")
        encoded = canonical_json_bytes(lineage)
        records.append(
            {
                "row_id": source.row["row_id"],
                "lineage_json": encoded,
                "lineage_sha256": hashlib.sha256(encoded).hexdigest(),
            }
        )
    if len(records) != len(traces) or len({row["row_id"] for row in records}) != len(records):
        raise SealedExecutionError("lineage_count", "source lineage is not one-to-one")
    path = block.partial_path / "source-lineage.parquet"
    table = pa.table(
        {
            "row_id": pa.array([row["row_id"] for row in records], type=pa.string()),
            "lineage_json": pa.array(
                [row["lineage_json"] for row in records], type=pa.binary()
            ),
            "lineage_sha256": pa.array(
                [row["lineage_sha256"] for row in records], type=pa.string()
            ),
        }
    )
    pq.write_table(table, path, compression="zstd", use_dictionary=True)
    _fsync_file(path)
    reopened = pq.read_table(path).to_pylist()
    if reopened != records:
        raise SealedExecutionError("lineage_readback", "source lineage readback differs")
    receipt = {
        "schema_version": RUN_SCHEMA_VERSION,
        "rows": len(records),
        "path": "source-lineage.parquet",
        "bytes": path.stat().st_size,
        "sha256": sha256_file(path),
        "row_id_inventory_sha256": sha256_json([row["row_id"] for row in records]),
    }
    block.write_json("source-lineage.receipt.json", receipt)
    return receipt


def ensure_global_token_metadata(
    run: RunTransaction, tokenizer: Any
) -> dict[str, Any]:
    """Create or verify the one 128,256-row tokenizer table shared by a run."""

    import pyarrow as pa
    import pyarrow.parquet as pq

    directory = run.partial_path / "vocabulary"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "global-token-metadata.parquet"
    receipt_path = directory / "global-token-metadata.receipt.json"
    if path.exists() or receipt_path.exists():
        if not path.is_file() or not receipt_path.is_file():
            raise SealedExecutionError("token_metadata_partial", "token metadata is partial")
        receipt = load_json_receipt(receipt_path, label="global token metadata receipt")
        if (
            receipt.get("rows") != TOKENIZER_SIZE
            or receipt.get("path") != "vocabulary/global-token-metadata.parquet"
            or receipt.get("sha256") != sha256_file(path)
            or receipt.get("receipt_sha256") != embedded_receipt_sha256(receipt)
        ):
            raise SealedExecutionError("token_metadata_resume", "token metadata receipt differs")
        reopened = pq.read_table(path, columns=["token_id"])
        if reopened.column("token_id").to_pylist() != list(range(TOKENIZER_SIZE)):
            raise SealedExecutionError("token_metadata_ids", "token metadata IDs differ")
        return receipt

    special_ids = {int(value) for value in tokenizer.all_special_ids}
    added_ids = {int(value) for value in tokenizer.added_tokens_decoder}
    token_ids: list[int] = []
    raw_pieces: list[bytes] = []
    decoded_pieces: list[str] = []
    is_special: list[bool] = []
    is_added: list[bool] = []
    is_empty: list[bool] = []
    for token_id in range(TOKENIZER_SIZE):
        raw = tokenizer.convert_ids_to_tokens(token_id)
        raw_text = "" if raw is None else str(raw)
        decoded = tokenizer.decode(
            [token_id],
            skip_special_tokens=False,
            clean_up_tokenization_spaces=False,
        )
        token_ids.append(token_id)
        raw_pieces.append(raw_text.encode("utf-8"))
        decoded_pieces.append(str(decoded))
        is_special.append(token_id in special_ids)
        is_added.append(token_id in added_ids)
        is_empty.append(not raw_text or not str(decoded))
    table = pa.table(
        {
            "token_id": pa.array(token_ids, type=pa.int32()),
            "raw_token_bytes": pa.array(raw_pieces, type=pa.binary()),
            "decoded_piece": pa.array(decoded_pieces, type=pa.string()),
            "is_special": pa.array(is_special, type=pa.bool_()),
            "is_added": pa.array(is_added, type=pa.bool_()),
            "is_empty_looking": pa.array(is_empty, type=pa.bool_()),
        }
    )
    pq.write_table(table, path, compression="zstd", use_dictionary=True)
    _fsync_file(path)
    reopened = pq.read_table(path)
    if (
        reopened.num_rows != TOKENIZER_SIZE
        or reopened.column("token_id").to_pylist() != list(range(TOKENIZER_SIZE))
        or not reopened.equals(table)
    ):
        raise SealedExecutionError("token_metadata_readback", "token metadata readback differs")
    receipt = {
        "schema_version": RUN_SCHEMA_VERSION,
        "study_id": STUDY_ID,
        "protocol_version": PROTOCOL_VERSION,
        "model_revision": MODEL_REVISION,
        "tokenizer_revision": MODEL_REVISION,
        "rows": TOKENIZER_SIZE,
        "path": "vocabulary/global-token-metadata.parquet",
        "bytes": path.stat().st_size,
        "sha256": sha256_file(path),
    }
    receipt["receipt_sha256"] = embedded_receipt_sha256(receipt)
    atomic_write_json(receipt_path, receipt)
    return receipt


def _write_packed_vocabulary(
    block: BlockTransaction,
    payload: PackedVocabularyPayload,
    *,
    token_metadata_receipt: Mapping[str, Any],
) -> dict[str, Any]:
    """Write 128-logical-row numeric shards and an exact source-row index."""

    import pyarrow as pa
    import pyarrow.parquet as pq
    import torch
    from safetensors import safe_open
    from safetensors.torch import save_file

    if not payload.rows:
        raise SealedExecutionError("packed_vocab_empty", "packed vocabulary is empty")
    directory = block.partial_path / "vocabulary"
    directory.mkdir(parents=True, exist_ok=False)
    indexed_rows: list[dict[str, Any]] = []
    shard_receipts: list[dict[str, Any]] = []
    numeric_payload_bytes = 0
    for shard_index, start in enumerate(
        range(0, len(payload.rows), benchmark.PACKED_VOCAB_SHARD_ROWS)
    ):
        chunk = payload.rows[start : start + benchmark.PACKED_VOCAB_SHARD_ROWS]
        if not 0 < len(chunk) <= benchmark.PACKED_VOCAB_SHARD_ROWS:
            raise SealedExecutionError("packed_shard_rows", "packed shard row count differs")
        tensors: dict[str, Any] = {}
        chunk_index: list[dict[str, Any]] = []
        for local_index, packed_row in enumerate(chunk):
            prefix = f"r{local_index:03d}"
            for field, tensor in packed_row.tensors.items():
                key = f"{prefix}_{field}"
                if key in tensors:
                    raise SealedExecutionError("packed_tensor_key", "packed tensor key repeats")
                tensors[key] = tensor.detach().cpu().contiguous()
                numeric_payload_bytes += int(tensors[key].numel()) * int(
                    tensors[key].element_size()
                )
            chunk_index.append(
                {
                    **packed_row.metadata,
                    "numeric_shard": f"vocabulary/packed-{shard_index:03d}.safetensors",
                    "tensor_key_prefix": prefix,
                }
            )
        path = directory / f"packed-{shard_index:03d}.safetensors"
        save_file(tensors, str(path))
        _fsync_file(path)
        with safe_open(str(path), framework="pt", device="cpu") as handle:
            if set(handle.keys()) != set(tensors):
                raise SealedExecutionError("packed_tensor_inventory", "packed tensors differ")
            for key, expected in tensors.items():
                observed = handle.get_tensor(key)
                if (
                    observed.dtype != expected.dtype
                    or observed.shape != expected.shape
                    or not bool(torch.equal(observed, expected))
                ):
                    raise SealedExecutionError(
                        "packed_tensor_readback", "packed tensor readback differs"
                    )
        indexed_rows.extend(chunk_index)
        shard_receipts.append(
            {
                "path": f"vocabulary/{path.name}",
                "logical_rows": len(chunk),
                "tensor_count": len(tensors),
                "bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
        )

    index_path = directory / "packed-source-row-index.parquet"
    index_table = pa.Table.from_pylist(indexed_rows)
    pq.write_table(index_table, index_path, compression="zstd", use_dictionary=True)
    _fsync_file(index_path)
    reopened = pq.read_table(index_path).to_pylist()
    if reopened != indexed_rows:
        raise SealedExecutionError("packed_index_readback", "packed row index differs")
    receipt = {
        "schema_version": RUN_SCHEMA_VERSION,
        "study_id": STUDY_ID,
        "source_index_schema_sha256": benchmark.SOURCE_INDEX_SCHEMA_SHA256,
        "packed_shard_rows": benchmark.PACKED_VOCAB_SHARD_ROWS,
        "logical_rows": len(indexed_rows),
        "logical_row_inventory_sha256": sha256_json(indexed_rows),
        "numeric_payload_bytes": numeric_payload_bytes,
        "shards": shard_receipts,
        "row_index": {
            "path": "vocabulary/packed-source-row-index.parquet",
            "rows": len(indexed_rows),
            "bytes": index_path.stat().st_size,
            "sha256": sha256_file(index_path),
            "columns": list(index_table.column_names),
        },
        "token_metadata": dict(token_metadata_receipt),
    }
    receipt["receipt_sha256"] = embedded_receipt_sha256(receipt)
    block.write_json("vocabulary/packed-vocabulary.receipt.json", receipt)
    return receipt


def _abort_block_transaction(
    block: BlockTransaction,
    *,
    metadata: Mapping[str, Any],
    failure_code: str,
) -> None:
    """Seal an already-open partial block as failed without reopening its ID."""

    if not block.partial_path.is_dir():
        raise SealedExecutionError(
            "archive_seal_failure",
            "block left the partial namespace before failure could be sealed",
        )
    incomplete_manifest = block.partial_path / BLOCK_MANIFEST
    if incomplete_manifest.exists():
        # ``BlockTransaction.complete`` writes its manifest before the atomic
        # directory rename.  If sealing fails in that narrow interval, retain
        # the attempted manifest as evidence, free the reserved terminal name,
        # and seal this *same* open block as failed.  Never reopen the ID.
        preserved_suffix = 0
        while True:
            preserved = block.partial_path / (
                f"failed-pass-manifest-{preserved_suffix:02d}.json"
            )
            if not preserved.exists():
                break
            preserved_suffix += 1
        os.rename(incomplete_manifest, preserved)
    suffix = 0
    while True:
        relative = f"failure-{suffix:02d}.json"
        if not (block.partial_path / relative).exists():
            break
        suffix += 1
    block.write_json(
        relative,
        {
            "schema_version": RUN_SCHEMA_VERSION,
            "study_id": STUDY_ID,
            "failure_code": failure_code,
            "partial_payload_preserved": True,
        },
    )
    block.complete(
        metadata={
            **dict(metadata),
            "status": "fail",
            "failure_code": failure_code,
            "partial_payload_preserved": True,
        }
    )


def publish_block_payload(
    *,
    run: RunTransaction,
    block_id: str,
    payload: BlockPayload,
    attempt: int,
    token_metadata_receipt: Mapping[str, Any] | None = None,
    failure_injector: Callable[[str, BlockTransaction], None] | None = None,
) -> tuple[bool, str | None]:
    """Publish once or seal the same open transaction as a failed attempt."""

    inject = failure_injector or (lambda _stage, _block: None)
    block = run.begin_block(block_id)
    try:
        inject("before_json", block)
        for filename, value in payload.json_files.items():
            block.write_json(filename, value)
        inject("before_shards", block)
        shard_receipts = _write_trace_shards(block, payload.traces)
        block.write_json("source_shard_receipts.json", shard_receipts)
        if payload.traces:
            lineage_receipt = _write_source_lineage_table(block, payload.traces)
            block.write_json("source_lineage_binding.json", lineage_receipt)
        target_payload = payload.metadata.get("stage") in {"stage2a", "stage2b"}
        if target_payload and (
            payload.packed_vocabulary is None or token_metadata_receipt is None
        ):
            raise SealedExecutionError(
                "packed_vocab_missing", "passing target blocks require packed vocabulary"
            )
        if payload.packed_vocabulary is not None and token_metadata_receipt is not None:
            inject("before_packed_vocabulary", block)
            _write_packed_vocabulary(
                block,
                payload.packed_vocabulary,
                token_metadata_receipt=token_metadata_receipt,
            )
        inject("before_seal", block)
        block.complete(metadata={**payload.metadata, "attempt": attempt})
        return True, None
    except Exception as exc:
        code = (
            exc.code
            if isinstance(exc, SealedExecutionError)
            else "archive_write_failure"
        )
        try:
            _abort_block_transaction(
                block,
                metadata={**payload.metadata, "attempt": attempt},
                failure_code=code,
            )
        except SealedExecutionError:
            raise
        except Exception as abort_exc:
            raise SealedExecutionError(
                "archive_abort_failure",
                "failed block could not be sealed in place",
            ) from abort_exc
        return False, code


def publish_failed_attempt(
    *,
    run: RunTransaction,
    block_id: str,
    prefix_id: str,
    stage: str,
    attempt: int,
    runtime_failure_code: str,
    failure_injector: Callable[[str, BlockTransaction], None] | None = None,
) -> str | None:
    """Publish a runtime-failure record without ever reopening its block ID."""

    inject = failure_injector or (lambda _stage, _block: None)
    block = run.begin_block(block_id)
    metadata = {
        "prefix_id": prefix_id,
        "stage": stage,
        "status": "fail",
        "attempt": attempt,
        "failure_code": runtime_failure_code,
    }
    try:
        inject("before_failure_json", block)
        block.write_json(
            "failure.json",
            {
                "schema_version": RUN_SCHEMA_VERSION,
                "study_id": STUDY_ID,
                **metadata,
            },
        )
        inject("before_failure_seal", block)
        block.complete(metadata=metadata)
        return None
    except Exception as exc:
        archive_code = (
            exc.code if isinstance(exc, SealedExecutionError) else "archive_write_failure"
        )
        _abort_block_transaction(
            block,
            metadata={
                **metadata,
                "runtime_failure_code": runtime_failure_code,
            },
            failure_code=archive_code,
        )
        return archive_code


def choose_next_attempt(completed_metadata: Sequence[Mapping[str, Any]]) -> int | None:
    """Return 0/1 for a whole-block attempt, or None after success/exhaustion."""

    if any(row.get("status") == "pass" for row in completed_metadata):
        return None
    attempts = sorted(
        int(row["attempt"])
        for row in completed_metadata
        if isinstance(row.get("attempt"), int) and row.get("attempt") in {0, 1}
    )
    if not attempts:
        return 0
    return 1 if attempts == [0] else None


def _existing_attempts(run: RunTransaction, prefix_id: str) -> list[dict[str, Any]]:
    blocks = run.partial_path / "blocks"
    if not blocks.is_dir():
        return []
    rows: list[dict[str, Any]] = []
    for path in sorted(blocks.glob(f"{prefix_id}-attempt-*")):
        if path.name.endswith(".partial"):
            # No outcome is trusted from an interrupted write.  Preserve it for
            # forensic inspection and fail closed; a fresh run ID is required.
            raise SealedExecutionError("orphan_partial_block", "an interrupted block exists")
        rows.append(_block_manifest_metadata(path))
    return rows


def _start_or_resume_run(
    *,
    phase: str,
    run_id: str,
    bindings: ExecutionBindings,
    resume: bool,
) -> RunTransaction:
    root = paths.require_external_artifact_root(
        expected_volume_id=bindings.volume_id, write_read_probe=True
    )
    partial = root / phase / f"{run_id}.partial"
    final = root / phase / run_id
    if final.exists():
        raise SealedExecutionError("run_already_complete", "run ID is already complete")
    if partial.exists():
        if not resume:
            raise SealedExecutionError("run_partial_exists", "use --resume for the partial run")
        started = json.loads((partial / "RUN_STARTED.json").read_text(encoding="utf-8"))
        metadata = started.get("metadata", {})
        if metadata.get("plan_hash") != bindings.plan_hash or metadata.get(
            "prefix_receipt_sha256"
        ) != bindings.prefix_receipt_sha256:
            raise SealedExecutionError("resume_binding", "partial run bindings differ")
        return RunTransaction(
            artifact_root=root,
            phase=phase,
            run_id=run_id,
            partial_path=partial,
            final_path=final,
        )
    return RunTransaction.start(
        phase=phase,
        run_id=run_id,
        artifact_root=root,
        expected_volume_id=bindings.volume_id,
        metadata={**bindings.as_metadata(), "outcome_content": "sealed_target_results"},
    )


def run_target_phase(
    *,
    stage: str,
    bindings: ExecutionBindings,
    cache_dir: Path,
    artifact_receipt_path: Path,
    run_id: str,
    resume: bool,
    runtime_factory: Callable[..., PinnedRuntime] = PinnedRuntime,
) -> dict[str, Any]:
    if stage not in {"stage2a", "stage2b"}:
        raise ValueError("stage must be stage2a or stage2b")
    root = paths.require_external_artifact_root(
        expected_volume_id=bindings.volume_id, write_read_probe=True
    )
    cache = cache_dir.expanduser().resolve(strict=True)
    try:
        cache.relative_to(root)
    except ValueError as exc:
        raise SealedExecutionError("cache_outside_volume", "cache must be on external volume") from exc
    prefix_run = root / "confirmatory" / str(bindings.prefix_bank_run_id)
    prefix_verification = verify_completed_run(prefix_run)
    if prefix_verification["manifest_sha256"] != bindings.prefix_bank_manifest_sha256:
        raise SealedExecutionError("prefix_manifest_binding", "live prefix bank hash differs")
    prefix_rows = _prefix_plan_rows(bindings.plan_dir)
    main_rows = _read_plan_json(bindings.plan_dir, "main_branch_plan.jsonl")
    probe_rows = _read_plan_json(bindings.plan_dir, "probe_plan.jsonl")
    fixed_rows = _read_plan_json(bindings.plan_dir, "fixed_token_plan.jsonl")
    artifact = load_json_receipt(artifact_receipt_path, label="artifact receipt")
    runtime = runtime_factory(cache, artifact_receipt=artifact)
    runtime.validate_vector_inventory(fixed_rows, bindings.vector_inventory)
    runtime.prepare_target_prompt()
    run = _start_or_resume_run(
        phase="confirmatory", run_id=run_id, bindings=bindings, resume=resume
    )
    token_metadata_receipt = ensure_global_token_metadata(run, runtime.tokenizer)
    main_by_prefix: dict[str, list[dict[str, Any]]] = defaultdict(list)
    fixed_by_prefix: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in main_rows:
        main_by_prefix[str(row["prefix_id"])].append(row)
    for row in fixed_rows:
        fixed_by_prefix[str(row["prefix_id"])].append(row)

    completed = 0
    missing = 0
    failures: Counter[str] = Counter()
    for prefix_row in prefix_rows:
        prefix_id = str(prefix_row["prefix_id"])
        existing = _existing_attempts(run, prefix_id)
        attempt = choose_next_attempt(existing)
        if attempt is None:
            if any(row.get("status") == "pass" for row in existing):
                completed += 1
            else:
                missing += 1
            continue
        try:
            prefix_payload = _load_prefix_raw(
                root, str(bindings.prefix_bank_run_id), prefix_id
            )
        except Exception:
            failures["prefix_not_realized"] += 1
            missing += 1
            continue
        while attempt is not None:
            block_id = f"{prefix_id}-attempt-{attempt}"
            runtime.set_trace_binding(
                {
                    "plan_hash": bindings.plan_hash,
                    "run_id": run_id,
                    "block_id": block_id,
                    "attempt": int(attempt),
                    "prefix_id": prefix_id,
                    "prefix_seed": int(prefix_payload["prefix_seed"]),
                    "prefix_token_ids_sha256": _token_ids_sha256(
                        prefix_payload["prefix_token_ids"]
                    ),
                    "stage": stage,
                    "artifact_receipt_sha256": bindings.artifact_receipt_sha256,
                    "calibration_receipt_sha256": bindings.calibration_receipt_sha256,
                    "acceptance_receipt_sha256": bindings.acceptance_receipt_sha256,
                }
            )
            try:
                if stage == "stage2a":
                    payload = execute_stage2a_prefix(
                        runtime,
                        prefix_payload=prefix_payload,
                        branch_rows=main_by_prefix[prefix_id],
                        probe_templates=probe_rows,
                    )
                else:
                    payload = execute_stage2b_prefix(
                        runtime,
                        prefix_payload=prefix_payload,
                        fixed_rows=fixed_by_prefix[prefix_id],
                    )
            except Exception as exc:
                _abort_active_switches(runtime)
                code = exc.code if isinstance(exc, SealedExecutionError) else "block_runtime_failure"
                failures[code] += 1
                block = run.begin_block(block_id)
                block.write_json(
                    "failure.json",
                    {
                        "schema_version": RUN_SCHEMA_VERSION,
                        "study_id": STUDY_ID,
                        "prefix_id": prefix_id,
                        "stage": stage,
                        "attempt": attempt,
                        "failure_code": code,
                    },
                )
                block.complete(
                    metadata={
                        "prefix_id": prefix_id,
                        "stage": stage,
                        "status": "fail",
                        "attempt": attempt,
                        "failure_code": code,
                    }
                )
                if attempt == 0:
                    attempt = 1
                else:
                    attempt = None
                    missing += 1
                continue

            published, archive_failure = publish_block_payload(
                run=run,
                block_id=block_id,
                payload=payload,
                attempt=attempt,
                token_metadata_receipt=token_metadata_receipt,
            )
            if published:
                completed += 1
                attempt = None
            else:
                failures[str(archive_failure)] += 1
                if attempt == 0:
                    attempt = 1
                else:
                    attempt = None
                    missing += 1
    threshold_pass = completed >= MIN_COMPLETE_PREFIXES
    final = run.complete(
        metadata={
            "stage": stage,
            "complete_prefix_blocks": completed,
            "missing_prefix_blocks": missing,
            "minimum_complete_prefix_blocks": MIN_COMPLETE_PREFIXES,
            "threshold_pass": threshold_pass,
            "failure_code_counts": dict(sorted(failures.items())),
            "whole_block_max_attempts": 2,
            "token_metadata_receipt_sha256": token_metadata_receipt[
                "receipt_sha256"
            ],
            "source_index_schema_sha256": benchmark.SOURCE_INDEX_SCHEMA_SHA256,
        }
    )
    verification = verify_completed_run(final)
    return {
        "status": "pass" if threshold_pass else "fail",
        "phase": stage,
        "run_id": run_id,
        "complete_prefix_blocks": completed,
        "missing_prefix_blocks": missing,
        "failure_code_counts": dict(sorted(failures.items())),
        "manifest_sha256": verification["manifest_sha256"],
    }


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "phase",
        choices=("realize-prefix-bank", "receipt-prefix-bank", "stage2a", "stage2b"),
    )
    parser.add_argument("--plan-dir", type=Path, required=True)
    parser.add_argument("--volume-id", required=True)
    parser.add_argument("--artifact-receipt", type=Path, required=True)
    parser.add_argument("--calibration-receipt", type=Path, required=True)
    parser.add_argument("--registration-receipt", type=Path, required=True)
    parser.add_argument("--pre-prefix-freeze-receipt", type=Path, required=True)
    parser.add_argument("--acceptance-receipt", type=Path, required=True)
    parser.add_argument("--prefix-receipt", type=Path)
    parser.add_argument("--prefix-freeze-receipt", type=Path)
    parser.add_argument("--cache-dir", type=Path)
    parser.add_argument("--run-id")
    parser.add_argument("--prefix-bank-run-id")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--resume", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> None:
    args = parse_args(argv)
    try:
        bindings = validate_execution_gates(
            phase=args.phase,
            plan_dir=args.plan_dir,
            volume_id=args.volume_id,
            artifact_receipt_path=args.artifact_receipt,
            calibration_receipt_path=args.calibration_receipt,
            registration_receipt_path=args.registration_receipt,
            pre_prefix_freeze_receipt_path=args.pre_prefix_freeze_receipt,
            acceptance_receipt_path=args.acceptance_receipt,
            prefix_receipt_path=args.prefix_receipt,
            prefix_freeze_receipt_path=args.prefix_freeze_receipt,
        )
        if args.phase == "receipt-prefix-bank":
            if not args.prefix_bank_run_id or args.output is None:
                raise SealedExecutionError(
                    "cli_arguments", "receipt phase requires --prefix-bank-run-id and --output"
                )
            receipt = build_prefix_bank_receipt(
                bindings=bindings, prefix_bank_run_id=args.prefix_bank_run_id
            )
            write_compact_receipt(args.output, receipt)
            result = {
                "status": receipt["status"],
                "phase": args.phase,
                "receipt_sha256": receipt["receipt_sha256"],
                "successful_prefixes": receipt["successful_prefixes"],
                "failed_prefixes": receipt["failed_prefixes"],
                "failure_code_counts": receipt["failure_code_counts"],
                "prefix_bank_manifest_sha256": receipt[
                    "prefix_bank_manifest_sha256"
                ],
            }
        elif args.phase == "realize-prefix-bank":
            if args.cache_dir is None or not args.run_id:
                raise SealedExecutionError(
                    "cli_arguments", "realization requires --cache-dir and --run-id"
                )
            result = realize_prefix_bank(
                bindings=bindings,
                cache_dir=args.cache_dir,
                artifact_receipt_path=args.artifact_receipt,
                run_id=args.run_id,
            )
        else:
            if args.cache_dir is None or not args.run_id:
                raise SealedExecutionError(
                    "cli_arguments", "target stage requires --cache-dir and --run-id"
                )
            result = run_target_phase(
                stage=args.phase,
                bindings=bindings,
                cache_dir=args.cache_dir,
                artifact_receipt_path=args.artifact_receipt,
                run_id=args.run_id,
                resume=bool(args.resume),
            )
        _print_safe_status(result)
        if result.get("status") != "pass":
            raise SystemExit(1)
    except SealedExecutionError as exc:
        _print_safe_status(
            {"status": "fail", "phase": args.phase, "failure_code": exc.code}
        )
        raise SystemExit(2) from None
    except SystemExit:
        raise
    except Exception:
        _print_safe_status(
            {
                "status": "fail",
                "phase": args.phase,
                "failure_code": "unexpected_runtime_failure",
            }
        )
        raise SystemExit(3) from None


if __name__ == "__main__":
    main()

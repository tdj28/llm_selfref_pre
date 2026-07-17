#!/usr/bin/env python3
"""Independently verify a signed-dose recovery host qualification receipt.

The verifier revalidates the outcome-blind equivalence packet, immutable input
files, provider/guest/cache chain, pinned checkpoint hash, one-attempt ledger,
and exact zero-forward B200/CUBLAS evidence.  It never executes the probe and
has no raw-run input.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import stat
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from experiments.consciousness_sae_realization_validation import protocol as base_protocol
from experiments.consciousness_sae_realization_validation import runpod_preflight
from experiments.consciousness_sae_signed_dose_scan import protocol
from experiments.consciousness_sae_signed_dose_scan import (
    verify_recovery_equivalence,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
QUALIFICATION_PROTOCOL_VERSION = (
    "consciousness_sae_signed_dose_scan_v1.audit_recovery_host_qualification_v1"
)
ATTEMPT_MARKER_NAME = "ATTEMPT_STARTED.json"
SUCCESS_NAME = "TARGET_HOST_QUALIFICATION.json"
FAILURE_NAME = "QUALIFICATION_FAILED.json"
MAX_OWNERSHIP_AGE_SECONDS = 30 * 60
MAX_GUEST_AGE_SECONDS = 15 * 60
MIN_LIFECYCLE_REMAINING_SECONDS = 15 * 60
QUALIFICATION_MAX_SECONDS = 30 * 60
QUALIFICATION_MAX_SPEND_USD = 3.0
FORBIDDEN_RAW_ROOT = Path(
    "/workspace/consciousness_sae_signed_dose_scan/"
    "consciousness_sae_signed_dose_scan_v1/raw"
)
HEX64 = re.compile(r"[0-9a-f]{64}")


class RecoveryHostQualificationVerificationError(RuntimeError):
    """The target-host qualification evidence failed verification."""


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(8 * 1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _load_canonical(path: Path, label: str) -> tuple[dict[str, Any], bytes]:
    candidate = path.expanduser().absolute()
    try:
        details = candidate.lstat()
        raw = candidate.read_bytes()
        value = json.loads(raw)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise RecoveryHostQualificationVerificationError(
            f"{label} is unreadable"
        ) from exc
    if (
        not stat.S_ISREG(details.st_mode)
        or details.st_nlink != 1
        or not isinstance(value, dict)
        or raw != canonical_json_bytes(value) + b"\n"
    ):
        raise RecoveryHostQualificationVerificationError(
            f"{label} is not canonical single-link JSON"
        )
    return value, raw


def _self_hash(value: Mapping[str, Any], label: str) -> str:
    core = dict(value)
    supplied = core.pop("receipt_sha256", None)
    if (
        not isinstance(supplied, str)
        or HEX64.fullmatch(supplied) is None
        or supplied != canonical_sha256(core)
    ):
        raise RecoveryHostQualificationVerificationError(
            f"{label} self-hash differs"
        )
    return supplied


def _utc_timestamp(value: Any, label: str) -> float:
    if not isinstance(value, str):
        raise RecoveryHostQualificationVerificationError(f"{label} is malformed")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise RecoveryHostQualificationVerificationError(
            f"{label} is malformed"
        ) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise RecoveryHostQualificationVerificationError(
            f"{label} is timezone-naive"
        )
    return parsed.astimezone(timezone.utc).timestamp()


def _strict_existing_path(path: Path, label: str) -> Path:
    lexical = Path(os.path.abspath(os.path.expanduser(os.fspath(path))))
    current = Path(lexical.anchor)
    try:
        for component in lexical.parts[1:]:
            current /= component
            if stat.S_ISLNK(current.lstat().st_mode):
                raise RecoveryHostQualificationVerificationError(
                    f"{label} contains a symlink component"
                )
        resolved = lexical.resolve(strict=True)
    except RecoveryHostQualificationVerificationError:
        raise
    except OSError as exc:
        raise RecoveryHostQualificationVerificationError(
            f"{label} is missing"
        ) from exc
    if resolved != lexical:
        raise RecoveryHostQualificationVerificationError(
            f"{label} canonical path differs"
        )
    return resolved


def _inside(path: Path, root: Path) -> bool:
    return path == root or root in path.parents


def _actual_input_record(
    role: str, path: Path, forbidden_raw_root: Path
) -> dict[str, Any]:
    candidate = _strict_existing_path(path, f"qualification input {role}")
    if _inside(candidate, forbidden_raw_root):
        raise RecoveryHostQualificationVerificationError(
            "qualification input points into raw"
        )
    try:
        details = candidate.lstat()
    except OSError as exc:
        raise RecoveryHostQualificationVerificationError(
            f"qualification input is missing: {role}"
        ) from exc
    if not stat.S_ISREG(details.st_mode) or details.st_nlink != 1:
        raise RecoveryHostQualificationVerificationError(
            f"qualification input file differs: {role}"
        )
    return {
        "role": role,
        "path": candidate.as_posix(),
        "bytes": details.st_size,
        "sha256": sha256_file(candidate),
    }


def _validated_receipt_chain(
    ownership_path: Path, guest_path: Path, cache_path: Path
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, str]]:
    ownership_raw, ownership_bytes = _load_canonical(
        ownership_path, "ownership receipt"
    )
    guest_raw, guest_bytes = _load_canonical(guest_path, "guest receipt")
    cache_raw, cache_bytes = _load_canonical(cache_path, "cache receipt")
    try:
        ownership = runpod_preflight.validate_ownership_receipt(ownership_raw)
        guest = runpod_preflight.validate_guest_receipt(
            guest_raw, ownership_receipt=ownership
        )
        cache = runpod_preflight.validate_cache_receipt(
            cache_raw,
            guest_receipt=guest,
            ownership_receipt=ownership,
        )
    except runpod_preflight.PreflightError as exc:
        raise RecoveryHostQualificationVerificationError(
            "provider/guest/cache chain differs"
        ) from exc
    hashes = {
        "ownership": hashlib.sha256(ownership_bytes).hexdigest(),
        "guest": hashlib.sha256(guest_bytes).hexdigest(),
        "cache": hashlib.sha256(cache_bytes).hexdigest(),
    }
    return ownership, guest, cache, hashes


def _expected_chain_record(
    ownership: Mapping[str, Any],
    guest: Mapping[str, Any],
    cache: Mapping[str, Any],
    hashes: Mapping[str, str],
    *,
    ownership_path: Path,
    guest_path: Path,
    cache_path: Path,
) -> dict[str, Any]:
    return {
        "status": "pass_fresh_owned_guest_cache_chain",
        "pod_id": ownership["pod_id"],
        "volume_id": ownership["network_volume_id"],
        "data_center_id": ownership["data_center_id"],
        "gpu_type": ownership["gpu_type"],
        "gpu_count": ownership["gpu_count"],
        "precreate_unrelated_pod_count": ownership[
            "precreate_unrelated_pod_count"
        ],
        "precreate_unrelated_inventory_sha256": ownership[
            "precreate_unrelated_inventory_sha256"
        ],
        "created_at": ownership["created_at"],
        "terminate_after": ownership["terminate_after"],
        "guest_attested_at_utc": guest["attested_at_utc"],
        "ownership_path": ownership_path.expanduser().absolute().as_posix(),
        "guest_path": guest_path.expanduser().absolute().as_posix(),
        "cache_path": cache_path.expanduser().absolute().as_posix(),
        "ownership_file_sha256": hashes["ownership"],
        "guest_file_sha256": hashes["guest"],
        "cache_file_sha256": hashes["cache"],
        "ownership_receipt_sha256": ownership["receipt_sha256"],
        "guest_receipt_sha256": guest["receipt_sha256"],
        "cache_receipt_sha256": cache["receipt_sha256"],
        "cache_root": cache["cache_root"],
        "cache_components": cache["components"],
        "model_forward_count": 0,
        "target_prompt_render_count": 0,
        "prior_outcome_inputs": [],
    }


def _verify_marker(
    marker: Mapping[str, Any],
    *,
    started: float,
    deadline: float,
    hourly_price_usd: float,
    declared_inputs: list[dict[str, str]],
) -> str:
    receipt_hash = _self_hash(marker, "attempt marker")
    expected = {
        "schema_version": 1,
        "status": "attempt_started_irrevocably",
        "study_id": protocol.STUDY_ID,
        "qualification_protocol_version": QUALIFICATION_PROTOCOL_VERSION,
        "attempt_number": 1,
        "retry_authorized": False,
        "started_at_unix": started,
        "qualification_deadline_at_unix": deadline,
        "hourly_price_usd": hourly_price_usd,
        "max_spend_usd": QUALIFICATION_MAX_SPEND_USD,
        "declared_input_paths": declared_inputs,
        "declared_input_paths_sha256": canonical_sha256(declared_inputs),
        "authorized_raw_input_paths": [],
        "model_forward_count": 0,
        "target_prompt_render_count": 0,
        "receipt_sha256": receipt_hash,
    }
    if marker != expected:
        raise RecoveryHostQualificationVerificationError("attempt marker differs")
    return receipt_hash


def _verify_checkpoint(value: Any, checkpoint_path: Path) -> str:
    if not isinstance(value, Mapping):
        raise RecoveryHostQualificationVerificationError("J evidence is absent")
    receipt_hash = _self_hash(value, "J checkpoint evidence")
    expected_audit_record = {
        "sha256": protocol.J_LENS_SPEC["sha256"],
        "map_count": 34,
        "revision": protocol.J_LENS_SPEC["revision"],
    }
    core = dict(value)
    core.pop("receipt_sha256")
    fixed = {
        "status": "pass_exact_pinned_superset_and_required_filter",
        "checkpoint_path": checkpoint_path.expanduser().absolute().as_posix(),
        "checkpoint_sha256": protocol.J_LENS_SPEC["sha256"],
        "checkpoint_revision": protocol.J_LENS_SPEC["revision"],
        "checkpoint_n_prompts": int(
            protocol.J_LENS_SPEC["release_config"]["prompts_fitted"]
        ),
        "checkpoint_d_model": protocol.WIDTH,
        "available_layers": list(range(79)),
        "required_layers": list(range(45, 79)),
        "unused_extra_layers": list(range(45)),
        "filtered_layers": list(range(45, 79)),
        "available_map_count": 79,
        "required_map_count": 34,
        "required_map_shape": [protocol.WIDTH, protocol.WIDTH],
        "required_map_dtype": "torch.bfloat16",
        "selected_map_object_contract": (
            "same_checkpoint_objects_no_numeric_transform"
        ),
        "missing_required_layer_negative": (
            "pass_rejected_missing_required_layer_45"
        ),
        "frozen_audit_record": expected_audit_record,
    }
    if (
        any(core.get(key) != expected for key, expected in fixed.items())
        or set(core) != {*fixed, "loader_watchdog_check_count"}
        or isinstance(core.get("loader_watchdog_check_count"), bool)
        or not isinstance(core.get("loader_watchdog_check_count"), int)
        or core["loader_watchdog_check_count"] < 2
        or sha256_file(checkpoint_path) != protocol.J_LENS_SPEC["sha256"]
    ):
        raise RecoveryHostQualificationVerificationError("J evidence differs")
    return receipt_hash


def _verify_cuda(value: Any) -> None:
    if not isinstance(value, Mapping):
        raise RecoveryHostQualificationVerificationError("CUDA evidence is absent")
    fixed = {
        "status": "pass_frozen_startup_and_real_bf16_cublas",
        "configured_via": (
            "experiments.consciousness_sae_signed_dose_scan.audit."
            "_configure_artifact_device"
        ),
        "device": "cuda:0",
        "device_count": 1,
        "cublas_workspace_config": base_protocol.CUBLAS_WORKSPACE_CONFIG_VALUE,
        "deterministic_algorithms_enabled": True,
        "matmul_allow_tf32": False,
        "cudnn_allow_tf32": False,
        "flash_sdp_enabled": False,
        "mem_efficient_sdp_enabled": False,
        "math_sdp_enabled": True,
        "probe_operation": "torch.matmul",
        "probe_shape": [16, 16],
        "probe_dtype": "torch.bfloat16",
        "probe_finite": True,
        "probe_exact_identity_product": True,
        "torch_module_calls": 0,
        "transformers_model_load_calls": 0,
        "direct_forward_attribute_access": 0,
        "model_forward_count": 0,
        "target_prompt_render_count": 0,
    }
    if (
        any(value.get(key) != expected for key, expected in fixed.items())
        or set(value) != {*fixed, "device_name", "device_total_memory_bytes"}
        or "B200" not in str(value.get("device_name"))
        or isinstance(value.get("device_total_memory_bytes"), bool)
        or not isinstance(value.get("device_total_memory_bytes"), int)
        or value["device_total_memory_bytes"] < 160 * 1024**3
    ):
        raise RecoveryHostQualificationVerificationError("CUDA evidence differs")


def verify_qualification(
    *,
    receipt_path: Path,
    marker_path: Path,
    packet_path: Path,
    plan_audit_path: Path,
    ownership_path: Path,
    guest_path: Path,
    cache_path: Path,
    j_lens_path: Path,
    repo_root: Path = REPO_ROOT,
    enforce_git: bool = True,
    forbidden_raw_root: Path = FORBIDDEN_RAW_ROOT,
) -> dict[str, Any]:
    """Verify all immutable evidence without rerunning target-host probes."""

    if enforce_git and Path(forbidden_raw_root) != FORBIDDEN_RAW_ROOT:
        raise RecoveryHostQualificationVerificationError(
            "test-only raw-root override is forbidden in production"
        )
    canonical_raw_root = _strict_existing_path(
        forbidden_raw_root, "forbidden raw root"
    )
    if not canonical_raw_root.is_dir():
        raise RecoveryHostQualificationVerificationError(
            "forbidden raw root is not a directory"
        )
    paths = (
        receipt_path,
        marker_path,
        packet_path,
        plan_audit_path,
        ownership_path,
        guest_path,
        cache_path,
        j_lens_path,
    )
    canonical_paths = [
        _strict_existing_path(path, "qualification verification input")
        for path in paths
    ]
    if any(_inside(path, canonical_raw_root) for path in canonical_paths):
        raise RecoveryHostQualificationVerificationError("raw path was supplied")
    if (
        receipt_path.name != SUCCESS_NAME
        or marker_path.name != ATTEMPT_MARKER_NAME
        or receipt_path.parent != marker_path.parent
        or (receipt_path.parent / FAILURE_NAME).exists()
        or {path.name for path in receipt_path.parent.iterdir()}
        != {SUCCESS_NAME, ATTEMPT_MARKER_NAME}
    ):
        raise RecoveryHostQualificationVerificationError(
            "one-attempt output directory differs"
        )
    receipt, receipt_raw = _load_canonical(receipt_path, "qualification receipt")
    marker, marker_raw = _load_canonical(marker_path, "attempt marker")
    receipt_hash = _self_hash(receipt, "qualification receipt")
    started = receipt.get("started_at_unix")
    completed = receipt.get("completed_at_unix")
    if (
        isinstance(started, bool)
        or not isinstance(started, (int, float))
        or isinstance(completed, bool)
        or not isinstance(completed, (int, float))
        or not math.isfinite(float(started))
        or not math.isfinite(float(completed))
        or completed < started
    ):
        raise RecoveryHostQualificationVerificationError(
            "qualification times differ"
        )
    input_paths = {
        "equivalence_packet": packet_path,
        "independent_plan_audit": plan_audit_path,
        "fresh_ownership": ownership_path,
        "fresh_guest": guest_path,
        "fresh_cache": cache_path,
        "pinned_j_checkpoint": j_lens_path,
    }
    declared_inputs = [
        {
            "role": role,
            "path": Path(
                os.path.abspath(os.path.expanduser(os.fspath(path)))
            ).as_posix(),
        }
        for role, path in sorted(input_paths.items())
    ]
    input_records = [
        _actual_input_record(role, path, canonical_raw_root)
        for role, path in sorted(input_paths.items())
    ]
    try:
        marker_deadline = float(marker["qualification_deadline_at_unix"])
        marker_hourly_price = float(marker["hourly_price_usd"])
    except (KeyError, TypeError, ValueError, OverflowError) as exc:
        raise RecoveryHostQualificationVerificationError(
            "qualification watchdog authority is malformed"
        ) from exc
    marker_hash = _verify_marker(
        marker,
        started=float(started),
        deadline=marker_deadline,
        hourly_price_usd=marker_hourly_price,
        declared_inputs=declared_inputs,
    )
    qualification_deadline = marker_deadline
    hourly_price = marker_hourly_price
    if (
        not all(
            math.isfinite(value)
            for value in (qualification_deadline, hourly_price)
        )
        or qualification_deadline - started != QUALIFICATION_MAX_SECONDS
        or hourly_price <= 0
        or hourly_price * QUALIFICATION_MAX_SECONDS / 3600
        > QUALIFICATION_MAX_SPEND_USD
        or marker.get("max_spend_usd") != QUALIFICATION_MAX_SPEND_USD
    ):
        raise RecoveryHostQualificationVerificationError(
            "qualification watchdog authority differs"
        )
    equivalence = verify_recovery_equivalence.verify_packet(
        packet_path,
        plan_audit_path=plan_audit_path,
        repo_root=repo_root,
        enforce_git=enforce_git,
    )
    ownership, guest, cache, file_hashes = _validated_receipt_chain(
        ownership_path, guest_path, cache_path
    )
    chain = _expected_chain_record(
        ownership,
        guest,
        cache,
        file_hashes,
        ownership_path=ownership_path,
        guest_path=guest_path,
        cache_path=cache_path,
    )
    created = _utc_timestamp(ownership["created_at"], "ownership.created_at")
    provider_terminate_at = _utc_timestamp(
        ownership["terminate_after"], "ownership.terminate_after"
    )
    attested = _utc_timestamp(guest["attested_at_utc"], "guest.attested_at_utc")
    if (
        not created <= attested <= started <= completed < provider_terminate_at
        or started - created > MAX_OWNERSHIP_AGE_SECONDS
        or started - attested > MAX_GUEST_AGE_SECONDS
        or provider_terminate_at - started < MIN_LIFECYCLE_REMAINING_SECONDS
    ):
        raise RecoveryHostQualificationVerificationError(
            "qualification lifecycle differs"
        )
    cache_j = [
        row for row in cache["components"] if row.get("component") == "j_lens"
    ]
    if (
        len(cache_j) != 1
        or _strict_existing_path(j_lens_path, "J checkpoint")
        != _strict_existing_path(
            Path(str(cache["cache_root"])) / cache_j[0]["relative_path"],
            "cache J checkpoint",
        )
        or cache_j[0]["sha256"] != protocol.J_LENS_SPEC["sha256"]
    ):
        raise RecoveryHostQualificationVerificationError(
            "cache/checkpoint path differs"
        )
    checkpoint_evidence_hash = _verify_checkpoint(
        receipt.get("j_checkpoint"), j_lens_path
    )
    _verify_cuda(receipt.get("cuda_startup"))
    fixed = {
        "schema_version": 1,
        "status": "pass_one_shot_zero_forward_target_host_qualification",
        "study_id": protocol.STUDY_ID,
        "protocol_version": protocol.PROTOCOL_VERSION,
        "qualification_protocol_version": QUALIFICATION_PROTOCOL_VERSION,
        "attempt_number": 1,
        "retry_authorized": False,
        "attempt_marker_receipt_sha256": marker_hash,
        "qualification_watchdog": {
            "status": "pass_independent_qualification_time_cost_cap",
            "started_at_unix": started,
            "qualification_deadline_at_unix": qualification_deadline,
            "maximum_seconds": QUALIFICATION_MAX_SECONDS,
            "hourly_price_usd": hourly_price,
            "max_spend_usd": QUALIFICATION_MAX_SPEND_USD,
            "maximum_theoretical_spend_usd": (
                hourly_price * QUALIFICATION_MAX_SECONDS / 3600
            ),
            "completed_at_unix": completed,
        },
        "inputs": input_records,
        "input_inventory_sha256": canonical_sha256(input_records),
        "equivalence_verification": equivalence,
        "code_freeze_commit": equivalence["code_freeze_commit"],
        "recovery_closure_inventory_sha256": equivalence[
            "recovery_closure_inventory_sha256"
        ],
        "fresh_pod": chain,
        "zero_forward_guard": {
            "torch_module_calls": 0,
            "transformers_model_load_calls": 0,
            "direct_forward_attribute_access": 0,
            "model_construction_calls": 0,
            "model_state_load_calls": 0,
        },
        "raw_access_guard": {
            "status": "pass_no_forbidden_raw_open",
            "forbidden_raw_root": canonical_raw_root.as_posix(),
            "forbidden_attempt_count": 0,
        },
        "raw_input_paths": [],
        "outcome_input_paths": [],
        "analysis_data_inputs": [],
        "model_forward_count": 0,
        "target_prompt_render_count": 0,
        "target_feature_vector_count": 0,
    }
    variable_keys = {
        "started_at_unix",
        "completed_at_unix",
        "j_checkpoint",
        "cuda_startup",
        "receipt_sha256",
    }
    if (
        any(receipt.get(key) != expected for key, expected in fixed.items())
        or set(receipt) != {*fixed, *variable_keys}
        or completed >= qualification_deadline
        or hourly_price * (completed - started) / 3600
        > QUALIFICATION_MAX_SPEND_USD
    ):
        raise RecoveryHostQualificationVerificationError(
            "qualification receipt differs"
        )
    core = {
        "schema_version": 1,
        "status": "pass_independent_target_host_qualification_verified",
        "study_id": protocol.STUDY_ID,
        "protocol_version": protocol.PROTOCOL_VERSION,
        "qualification_protocol_version": QUALIFICATION_PROTOCOL_VERSION,
        "qualification_receipt_path": (
            receipt_path.expanduser().absolute().as_posix()
        ),
        "qualification_receipt_file_sha256": hashlib.sha256(
            receipt_raw
        ).hexdigest(),
        "qualification_receipt_sha256": receipt_hash,
        "attempt_marker_file_sha256": hashlib.sha256(marker_raw).hexdigest(),
        "attempt_marker_receipt_sha256": marker_hash,
        "equivalence_packet_sha256": equivalence["packet_sha256"],
        "code_freeze_commit": equivalence["code_freeze_commit"],
        "recovery_closure_inventory_sha256": equivalence[
            "recovery_closure_inventory_sha256"
        ],
        "j_checkpoint_evidence_sha256": checkpoint_evidence_hash,
        "j_checkpoint_sha256": protocol.J_LENS_SPEC["sha256"],
        "attempt_number": 1,
        "retry_authorized": False,
        "model_forward_count": 0,
        "target_prompt_render_count": 0,
        "target_feature_vector_count": 0,
        "raw_run_opened": False,
        "compact_result_opened": False,
        "analysis_data_inputs": [],
    }
    return {**core, "receipt_sha256": canonical_sha256(core)}


def _write_exclusive(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(canonical_json_bytes(value) + b"\n")
        handle.flush()
        os.fsync(handle.fileno())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--marker", type=Path, required=True)
    parser.add_argument("--packet", type=Path, required=True)
    parser.add_argument("--plan-audit", type=Path, required=True)
    parser.add_argument("--ownership", type=Path, required=True)
    parser.add_argument("--guest", type=Path, required=True)
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--j-checkpoint", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    verified = verify_qualification(
        receipt_path=args.receipt,
        marker_path=args.marker,
        packet_path=args.packet,
        plan_audit_path=args.plan_audit,
        ownership_path=args.ownership,
        guest_path=args.guest,
        cache_path=args.cache,
        j_lens_path=args.j_checkpoint,
    )
    _write_exclusive(args.output, verified)
    print(args.output.expanduser().absolute(), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

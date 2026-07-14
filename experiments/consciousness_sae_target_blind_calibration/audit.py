#!/usr/bin/env python3
"""Independently audit and summarize a completed calibration-v2 raw run."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import stat
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Any, Mapping, Sequence


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from experiments.consciousness_sae_realization_validation import (  # noqa: E402
    protocol as base_protocol,
    runpod_preflight,
)
from experiments.consciousness_sae_target_blind_calibration import (  # noqa: E402
    authorize,
    orientation,
    protocol,
    validate_plan,
)


class CalibrationAuditError(RuntimeError):
    pass


LEGACY_ARTIFACT_MANIFEST = (
    REPO_ROOT
    / "experiments/consciousness_sae_realization_validation/legacy_public_artifact_manifest.json"
)

EXPECTED_SOFTWARE = {
    "python": "3.11.11",
    "python_implementation": "CPython",
    "torch": "2.8.0.dev20250319+cu128",
    "accelerate": "1.12.0",
    "huggingface_hub": "0.36.0",
    "numpy": "2.2.6",
    "safetensors": "0.8.0",
    "transformers": "4.57.6",
}


def _finite_json(value: Any) -> bool:
    if isinstance(value, bool) or value is None or isinstance(value, (str, int)):
        return True
    if isinstance(value, float):
        return math.isfinite(value)
    if isinstance(value, list):
        return all(_finite_json(child) for child in value)
    if isinstance(value, dict):
        return all(_finite_json(child) for child in value.values())
    return False


def _require_hex64(value: Any, label: str) -> str:
    normalized = str(value)
    if len(normalized) != 64 or any(
        character not in "0123456789abcdef" for character in normalized
    ):
        raise CalibrationAuditError(f"{label} is not a lowercase SHA-256")
    return normalized


def _require_exact_fields(
    value: Mapping[str, Any], fields: set[str] | frozenset[str], label: str
) -> None:
    if set(value) != set(fields):
        raise CalibrationAuditError(f"{label} field inventory differs")


def _validate_live_public_cache_rehash(
    value: Any,
    *,
    cache_receipt: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise CalibrationAuditError("live public-cache rehash is missing")
    fields = {
        "status",
        "cache_receipt_sha256",
        "cache_root",
        "full_file_count",
        "full_retained_bytes",
        "full_file_inventory_sha256",
        "components",
        "receipt_sha256",
    }
    _require_exact_fields(value, fields, "live public-cache rehash")
    core = dict(value)
    supplied = core.pop("receipt_sha256")
    if supplied != protocol.canonical_sha256(core):
        raise CalibrationAuditError("live public-cache rehash self-hash differs")
    _require_hex64(value["cache_receipt_sha256"], "live cache receipt binding")
    expected = (
        {
            "cache_receipt_sha256": cache_receipt["receipt_sha256"],
            "cache_root": cache_receipt["cache_root"],
            "full_file_count": cache_receipt["full_file_count"],
            "full_retained_bytes": cache_receipt["full_retained_bytes"],
            "full_file_inventory_sha256": cache_receipt["full_file_inventory_sha256"],
            "components": cache_receipt["components"],
        }
        if cache_receipt is not None
        else {
            "cache_root": runpod_preflight.LEGACY_PUBLIC_ARTIFACT_ROOT,
            "full_file_count": runpod_preflight.LEGACY_PUBLIC_ARTIFACT_FILE_COUNT,
            "full_retained_bytes": runpod_preflight.LEGACY_PUBLIC_ARTIFACT_BYTES,
            "full_file_inventory_sha256": (
                runpod_preflight.LEGACY_PUBLIC_ARTIFACT_INVENTORY_SHA256
            ),
        }
    )
    if value["status"] != "pass_exact_pre_backend_rehash" or any(
        value.get(field) != expected_value for field, expected_value in expected.items()
    ):
        raise CalibrationAuditError(
            "live public-cache rehash differs from the pinned cache"
        )
    components = value["components"]
    if (
        not isinstance(components, list)
        or tuple(row.get("component") for row in components if isinstance(row, Mapping))
        != runpod_preflight.CACHE_COMPONENTS
    ):
        raise CalibrationAuditError("live public-cache component inventory differs")
    return dict(value)


def _json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or not _finite_json(value):
        raise CalibrationAuditError(f"JSON root is invalid or non-finite: {path}")
    return value


def _jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            value = json.loads(line)
            if not isinstance(value, dict):
                raise CalibrationAuditError(
                    f"non-object JSONL row at {path}:{line_number}"
                )
            if not _finite_json(value):
                raise CalibrationAuditError(
                    f"non-finite JSONL row at {path}:{line_number}"
                )
            rows.append(value)
    return rows


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    payload = protocol.canonical_json_bytes(dict(value)) + b"\n"
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())


def _publish_pair_atomic(
    audit_out: Path,
    summary_out: Path,
    audit_receipt: Mapping[str, Any],
    summary: Mapping[str, Any],
) -> Path:
    """Publish the compact pair as one deadline-guarded directory transaction."""

    audit_path = audit_out.expanduser().absolute()
    summary_path = summary_out.expanduser().absolute()
    if (
        audit_path.parent != summary_path.parent
        or audit_path.name != "CALIBRATION_AUDIT.json"
        or summary_path.name != "CALIBRATION_SUMMARY.json"
        or audit_path.parent == audit_path.parent.parent
    ):
        raise CalibrationAuditError(
            "audit outputs must use the frozen names in one fresh directory"
        )
    destination = audit_path.parent
    parent = destination.parent
    partial = destination.with_name(f".{destination.name}.partial")
    quarantine = destination.with_name(f".{destination.name}.expired")
    if (
        not parent.is_dir()
        or parent.is_symlink()
        or os.path.lexists(destination)
        or os.path.lexists(partial)
        or os.path.lexists(quarantine)
    ):
        raise CalibrationAuditError("compact publication destination is not fresh")
    watchdog = _AuditBudgetWatchdog(
        audit_receipt,
        audit_started_at_unix=float(audit_receipt["audit_started_at_unix"]),
    )
    partial.mkdir(mode=0o700)
    published = False
    try:
        watchdog.check()
        staged_audit = partial / audit_path.name
        staged_summary = partial / summary_path.name
        _write_json(staged_audit, audit_receipt)
        watchdog.check()
        _write_json(staged_summary, summary)
        directory_fd = os.open(partial, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
        watchdog.check()
        os.replace(partial, destination)
        published = True
        watchdog.check()
        marker_core = {
            "schema_version": 1,
            "status": "complete",
            "study_id": protocol.STUDY_ID,
            "protocol_version": protocol.PROTOCOL_VERSION,
            "audit_receipt_sha256": audit_receipt["receipt_sha256"],
            "summary_receipt_sha256": summary["receipt_sha256"],
            "audit_file_sha256": protocol.sha256_file(audit_path),
            "summary_file_sha256": protocol.sha256_file(summary_path),
            "publication_completed_at_unix": time.time(),
            "campaign_deadline_at_unix": audit_receipt["campaign_deadline_at_unix"],
        }
        marker = {
            **marker_core,
            "receipt_sha256": protocol.canonical_sha256(marker_core),
        }
        _write_json(destination / "PUBLICATION_COMPLETE.json", marker)
        destination_fd = os.open(destination, os.O_RDONLY)
        try:
            os.fsync(destination_fd)
        finally:
            os.close(destination_fd)
        parent_fd = os.open(parent, os.O_RDONLY)
        try:
            os.fsync(parent_fd)
        finally:
            os.close(parent_fd)
        watchdog.check()
        return destination / summary_path.name
    except BaseException:
        if published and os.path.lexists(destination):
            os.replace(destination, quarantine)
        raise


def _self_hash(value: Mapping[str, Any], label: str) -> None:
    core = dict(value)
    supplied = core.pop("receipt_sha256", None)
    if supplied != protocol.canonical_sha256(core):
        raise CalibrationAuditError(f"{label} self-hash differs")


def _tensor_sha256(value: Any) -> str:
    import torch

    cpu = value.detach().contiguous().to(device="cpu")
    digest = hashlib.sha256()
    digest.update(
        protocol.canonical_json_bytes(
            {"dtype": str(cpu.dtype), "shape": list(cpu.shape)}
        )
    )
    digest.update(b"\0")
    raw = cpu.view(torch.uint8).reshape(-1)
    for start in range(0, int(raw.numel()), 8 * 1024 * 1024):
        digest.update(raw[start : start + 8 * 1024 * 1024].numpy().tobytes())
    return digest.hexdigest()


def _load_file(path: Path) -> dict[str, Any]:
    try:
        from safetensors.torch import load_file
    except ImportError as exc:  # pragma: no cover - environment dependent
        raise CalibrationAuditError("safetensors is required") from exc
    return load_file(str(path), device="cpu")


def _fixed_token_panel() -> tuple[int, ...]:
    modulus = int(
        protocol.FRESH_RANDOMIZATION_SPEC[
            "fixed_token_panel_token_id_upper_bound_exclusive"
        ]
    )
    offset = protocol.seed64("fixed-token-panel-v2") % modulus
    return tuple(int((offset + 7_919 * index) % modulus) for index in range(2_048))


def _require_all_finite(values: Mapping[str, Any], label: str) -> None:
    import torch

    for name, value in values.items():
        if not isinstance(value, torch.Tensor) or not bool(torch.isfinite(value).all()):
            raise CalibrationAuditError(f"non-finite raw tensor: {label}/{name}")


def _rms(value: Any) -> float:
    import torch

    return float(torch.sqrt(torch.mean(value.float().square())).item())


def _relative_rmse(actual: Any, reference: Any) -> float:
    import torch

    numerator = torch.sqrt(torch.mean((actual.float() - reference.float()).square()))
    denominator = torch.sqrt(torch.mean(reference.float().square())).clamp_min(1e-30)
    return float((numerator / denominator).item())


def _cosine(left: Any, right: Any) -> float:
    import torch

    lhs = left.float().reshape(-1)
    rhs = right.float().reshape(-1)
    denominator = lhs.norm() * rhs.norm()
    if float(denominator.item()) <= 0:
        return 0.0
    return float(torch.dot(lhs, rhs).div(denominator).item())


def _pearson(left: Any, right: Any) -> float:
    import torch

    lhs = left.float().reshape(-1)
    rhs = right.float().reshape(-1)
    lhs = lhs - lhs.mean()
    rhs = rhs - rhs.mean()
    denominator = lhs.norm() * rhs.norm()
    if float(denominator.item()) <= 0:
        return 0.0
    return float(torch.dot(lhs, rhs).div(denominator).item())


def _safe_ratio(numerator: float, denominator: float) -> float:
    """Return a finite conservative ratio for potentially null responses."""

    if not math.isfinite(numerator) or not math.isfinite(denominator):
        raise CalibrationAuditError("ratio input is non-finite")
    return numerator / max(denominator, 1e-30)


def _near(observed: Any, expected: float, label: str, *, atol: float = 2e-6) -> None:
    if not isinstance(observed, (int, float)) or not math.isfinite(float(observed)):
        raise CalibrationAuditError(f"{label} is non-finite")
    if not math.isfinite(expected):
        raise CalibrationAuditError(f"{label} recomputation is non-finite")
    if abs(float(observed) - expected) > atol + 2e-6 * abs(expected):
        raise CalibrationAuditError(
            f"{label} differs: observed={observed}, recomputed={expected}"
        )


def _manifest(run_root: Path) -> dict[str, Any]:
    complete = _json(run_root / "RUN_COMPLETE.json")
    _self_hash(complete, "run receipt")
    if (
        complete.get("status") != "complete"
        or complete.get("study_id") != protocol.STUDY_ID
        or complete.get("protocol_version") != protocol.PROTOCOL_VERSION
        or complete.get("analysis_data_inputs") != []
        or complete.get("target_prompt_render_count") != 0
        or complete.get("target_feature_vector_count") != 0
        or complete.get("adaptive_design_inputs") != protocol.ADAPTIVE_DESIGN_INPUTS
    ):
        raise CalibrationAuditError("run identity/scope differs")
    records = complete.get("records")
    if not isinstance(records, list) or not records:
        raise CalibrationAuditError("run file manifest is missing")
    expected_paths = []
    stored_bytes = 0
    for record in records:
        relative = str(record.get("path"))
        path = run_root / relative
        try:
            resolved = path.resolve(strict=True)
            resolved.relative_to(run_root)
        except (OSError, ValueError) as exc:
            raise CalibrationAuditError(
                f"manifest path escaped run root: {relative}"
            ) from exc
        if (
            path.is_symlink()
            or not resolved.is_file()
            or resolved.stat().st_size != int(record.get("bytes", -1))
            or protocol.sha256_file(resolved) != record.get("sha256")
        ):
            raise CalibrationAuditError(f"manifested file differs: {relative}")
        expected_paths.append(relative)
        stored_bytes += resolved.stat().st_size
    observed_paths = sorted(
        path.relative_to(run_root).as_posix()
        for path in run_root.rglob("*")
        if path.is_file()
    )
    if observed_paths != sorted([*expected_paths, "RUN_COMPLETE.json"]):
        raise CalibrationAuditError("raw tree contains missing or unmanifested files")
    if len(expected_paths) != len(set(expected_paths)):
        raise CalibrationAuditError("raw manifest contains duplicate paths")
    if stored_bytes != int(complete.get("stored_bytes", -1)):
        raise CalibrationAuditError("stored-byte total differs")
    if stored_bytes > protocol.RESOURCE_LIMITS["raw_run_ceiling_bytes"]:
        raise CalibrationAuditError("raw run exceeds the frozen byte ceiling")
    if (
        int(complete.get("free_bytes_after", -1))
        < protocol.RESOURCE_LIMITS["post_run_free_reserve_bytes"]
    ):
        raise CalibrationAuditError("post-run free-space reserve differs")
    return complete


def _audit_plan(plan_dir: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    try:
        receipt = validate_plan.validate(plan_dir)
    except validate_plan.IndependentPlanAuditError as exc:
        raise CalibrationAuditError(f"independent plan audit failed: {exc}") from exc
    manifest = _json(plan_dir.expanduser().resolve(strict=True) / "plan_manifest.json")
    if receipt.get("plan_manifest_sha256") != manifest.get("plan_manifest_sha256"):
        raise CalibrationAuditError("independent plan receipt hash differs")
    return manifest, receipt


def _load_physical_receipt(path: Path, label: str) -> tuple[dict[str, Any], str]:
    lexical = path.expanduser().absolute()
    current = Path(lexical.anchor)
    for part in lexical.parts[1:]:
        current = current / part
        if current.is_symlink():
            raise CalibrationAuditError(f"{label} contains a symlink component")
    try:
        details = lexical.lstat()
        raw = lexical.read_bytes()
        value = json.loads(raw)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise CalibrationAuditError(f"{label} is not readable JSON") from exc
    if (
        not stat.S_ISREG(details.st_mode)
        or details.st_nlink != 1
        or not isinstance(value, dict)
        or not _finite_json(value)
        or raw != protocol.canonical_json_bytes(value) + b"\n"
    ):
        raise CalibrationAuditError(f"{label} physical file differs")
    return value, protocol.sha256_file(lexical)


def _audit_external_receipt_chain(
    *,
    ownership_path: Path,
    guest_path: Path,
    cache_path: Path,
    authorization_path: Path,
    plan_dir: Path,
    plan: Mapping[str, Any],
    execution_binding: Mapping[str, Any],
    complete: Mapping[str, Any],
    now_unix: float | None = None,
) -> dict[str, Any]:
    ownership_raw, ownership_file_hash = _load_physical_receipt(
        ownership_path, "ownership receipt"
    )
    guest_raw, guest_file_hash = _load_physical_receipt(guest_path, "guest receipt")
    cache_raw, cache_file_hash = _load_physical_receipt(cache_path, "cache receipt")
    authorization_raw, authorization_file_hash = _load_physical_receipt(
        authorization_path, "authorization receipt"
    )
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
        plan_root = plan_dir.expanduser().resolve(strict=True)
        authorization = authorize.validate_execution_authorization(
            authorization_raw,
            plan=plan,
            plan_manifest_path=plan_root / "plan_manifest.json",
            source_files_path=plan_root / "source_files.json",
            ownership=ownership,
            guest=guest,
            cache=cache,
            now_unix=time.time() if now_unix is None else now_unix,
        )
    except (runpod_preflight.PreflightError, authorize.AuthorizationError) as exc:
        raise CalibrationAuditError(f"external receipt chain failed: {exc}") from exc

    validated = {
        "ownership_receipt_sha256": ownership.get("receipt_sha256"),
        "guest_receipt_sha256": guest.get("receipt_sha256"),
        "cache_receipt_sha256": cache.get("receipt_sha256"),
        "authorization_receipt_sha256": authorization.get("receipt_sha256"),
    }
    if any(execution_binding.get(key) != value for key, value in validated.items()):
        raise CalibrationAuditError(
            "physical receipt chain differs from execution binding"
        )
    _validate_live_public_cache_rehash(
        execution_binding.get("live_public_cache_rehash"),
        cache_receipt=cache,
    )
    resource = complete.get("resource")
    if not isinstance(resource, Mapping) or (
        float(resource.get("campaign_started_at_unix", math.nan))
        != float(authorization["campaign_started_at_unix"])
        or float(resource.get("campaign_deadline_at_unix", math.nan))
        != float(authorization["campaign_deadline_at_unix"])
        or float(resource.get("hourly_price_usd", math.nan))
        != float(authorization["hourly_price_usd"])
        or execution_binding.get("pod_id") != ownership.get("pod_id")
        or execution_binding.get("volume_id") != ownership.get("network_volume_id")
        or execution_binding.get("data_center_id") != ownership.get("data_center_id")
    ):
        raise CalibrationAuditError(
            "authorization/provider/resource receipt binding differs"
        )
    return {
        **validated,
        "physical_file_sha256": {
            "ownership": ownership_file_hash,
            "guest": guest_file_hash,
            "cache": cache_file_hash,
            "authorization": authorization_file_hash,
        },
        "status": "pass",
    }


def _load_tokenizer(model_snapshot: Path) -> Any:
    try:
        from transformers import AutoTokenizer
    except ImportError as exc:  # pragma: no cover - GPU environment only
        raise CalibrationAuditError(
            "transformers is required for prompt audit"
        ) from exc
    lexical = model_snapshot.expanduser().absolute()
    if lexical.is_symlink():
        raise CalibrationAuditError("model snapshot is a symlink")
    snapshot = lexical.resolve(strict=True)
    if not snapshot.is_dir() or snapshot.name != "model_snapshot":
        raise CalibrationAuditError("model snapshot publication path differs")
    tokenizer = AutoTokenizer.from_pretrained(
        snapshot, local_files_only=True, trust_remote_code=False
    )
    if len(tokenizer) != protocol.VOCAB_SIZE:
        raise CalibrationAuditError("tokenizer vocabulary size differs")
    return tokenizer


def _render_tokens(tokenizer: Any, prompt_id: str) -> list[int]:
    payload = protocol.prompt_payload(prompt_id)
    values = tokenizer.apply_chat_template(
        [
            {"role": "system", "content": payload["system"]},
            {"role": "user", "content": payload["user"]},
        ],
        tokenize=True,
        add_generation_prompt=True,
    )
    if hasattr(values, "tolist"):
        values = values.tolist()
    if values and isinstance(values[0], list):
        if len(values) != 1:
            raise CalibrationAuditError("tokenizer produced a prompt batch")
        values = values[0]
    return [int(value) for value in values]


def _audit_prompt_receipts(rows: Sequence[Mapping[str, Any]], tokenizer: Any) -> None:
    if tuple(row.get("prompt_id") for row in rows) != protocol.PROMPT_IDS:
        raise CalibrationAuditError("prompt receipt inventory/order differs")
    fields = {
        "prompt_id",
        "target_prompt",
        "prompt_payload_sha256",
        "token_ids",
        "token_ids_sha256",
        "token_count",
        "prefix_token_count",
        "edited_token_index",
        "continuation_token_id",
        "continuation_forward_sequence_length",
        "intervention_state_contract_sha256",
        "j_state_contract_sha256",
        "fixed_panel_estimand_sha256",
    }
    for row in rows:
        _require_exact_fields(row, fields, "prompt receipt")
        prompt_id = str(row["prompt_id"])
        token_ids = row["token_ids"]
        rendered = _render_tokens(tokenizer, prompt_id)
        if (
            row["target_prompt"] is not False
            or row["prompt_payload_sha256"]
            != protocol.canonical_sha256(protocol.prompt_payload(prompt_id))
            or token_ids != rendered
            or row["token_count"] != len(rendered)
            or row["token_ids_sha256"] != protocol.canonical_sha256(rendered)
            or not rendered
            or row["prefix_token_count"] != len(rendered) - 1
            or row["edited_token_index"] != len(rendered) - 1
            or row["continuation_token_id"] != rendered[-1]
            or row["continuation_forward_sequence_length"] != 1
            or row["intervention_state_contract_sha256"]
            != protocol.canonical_sha256(protocol.INTERVENTION_STATE_CONTRACT)
            or row["j_state_contract_sha256"]
            != protocol.canonical_sha256(protocol.J_STATE_CONTRACT)
            or row["fixed_panel_estimand_sha256"]
            != protocol.canonical_sha256(protocol.FIXED_PANEL_ESTIMAND)
            or min(rendered) < 0
            or max(rendered) >= protocol.VOCAB_SIZE
        ):
            raise CalibrationAuditError(f"prompt/token binding differs: {prompt_id}")


def _audit_fixed_panel(run_root: Path) -> tuple[int, ...]:
    panel = _json(run_root / "fixed_token_panel.json")
    expected = _fixed_token_panel()
    if (
        panel
        != {
            "token_ids": list(expected),
            "sha256": protocol.canonical_sha256(list(expected)),
        }
        or len(set(expected)) != len(expected)
        or max(expected)
        >= int(
            protocol.FRESH_RANDOMIZATION_SPEC[
                "fixed_token_panel_token_id_upper_bound_exclusive"
            ]
        )
    ):
        raise CalibrationAuditError("fixed-token panel differs")
    return expected


def _audit_runtime_and_binding(
    run_root: Path,
    *,
    complete: Mapping[str, Any],
    plan: Mapping[str, Any],
) -> dict[str, Any]:
    runtime = _json(run_root / "runtime_metadata.json")
    if complete.get("runtime") != runtime:
        raise CalibrationAuditError("embedded/runtime-metadata binding differs")
    expected_runtime = {
        "container_image",
        "hardware",
        "software",
        "determinism",
        "model_forward_count",
        "first_model_forward_at_utc",
        "last_model_forward_at_utc",
        "expected_model_forward_count",
        "expected_edited_forward_count",
        "prompt_count",
        "realization_row_count",
        "readout_transport_row_count",
        "j_orientation_row_count",
        "j_orientation_status",
        "runner_watchdog_seconds",
        "runner_deadline_at_unix",
        "live_public_cache_rehash",
        "intervention_state_contract_sha256",
        "j_state_contract_sha256",
        "fixed_panel_estimand_sha256",
        "forward_inventory",
        "total_rendered_token_count",
        "prefix_uncached_token_count",
        "continuation_uncached_token_count",
        "total_uncached_token_count",
    }
    _require_exact_fields(runtime, expected_runtime, "runtime metadata")
    hardware = runtime.get("hardware")
    determinism = runtime.get("determinism")
    software = runtime.get("software")
    expected_seed = protocol.seed64("runtime-v2") % (2**63 - 1)
    if (
        runtime["container_image"] != protocol.CONTAINER_IMAGE_SPEC
        or runtime["model_forward_count"]
        != protocol.RESOURCE_LIMITS["expected_model_forwards"]
        or runtime["expected_model_forward_count"]
        != protocol.RESOURCE_LIMITS["expected_model_forwards"]
        or runtime["expected_edited_forward_count"]
        != protocol.RESOURCE_LIMITS["expected_edited_forwards"]
        or runtime["prompt_count"] != len(protocol.PROMPT_IDS)
        or runtime["realization_row_count"] != len(protocol.rows())
        or runtime["readout_transport_row_count"]
        != len(protocol.PROMPT_IDS)
        * len(protocol.DIRECTIONS)
        * len(protocol.READOUT_LAYERS)
        * len(protocol.TRANSPORTS)
        or runtime["j_orientation_row_count"]
        != len(protocol.J_LAYERS)
        * int(protocol.J_ORIENTATION_SPEC["fixture_count_per_layer"])
        or runtime["j_orientation_status"] not in {"pass", "fail"}
        or runtime["runner_watchdog_seconds"]
        != protocol.RESOURCE_LIMITS["runner_sub_watchdog_seconds"]
        or runtime["intervention_state_contract_sha256"]
        != protocol.canonical_sha256(protocol.INTERVENTION_STATE_CONTRACT)
        or runtime["j_state_contract_sha256"]
        != protocol.canonical_sha256(protocol.J_STATE_CONTRACT)
        or runtime["fixed_panel_estimand_sha256"]
        != protocol.canonical_sha256(protocol.FIXED_PANEL_ESTIMAND)
        or runtime["forward_inventory"] != protocol.FORWARD_INVENTORY
        or any(
            isinstance(runtime[field], bool) or not isinstance(runtime[field], int)
            for field in (
                "total_rendered_token_count",
                "prefix_uncached_token_count",
                "continuation_uncached_token_count",
                "total_uncached_token_count",
            )
        )
        or runtime["total_rendered_token_count"] <= len(protocol.PROMPT_IDS)
        or runtime["continuation_uncached_token_count"]
        != protocol.FORWARD_INVENTORY["clean_continuation_forwards"]
        + protocol.FORWARD_INVENTORY["edited_continuation_forwards"]
        or runtime["prefix_uncached_token_count"]
        != runtime["total_rendered_token_count"] - len(protocol.PROMPT_IDS)
        or runtime["total_uncached_token_count"]
        != runtime["prefix_uncached_token_count"]
        + runtime["continuation_uncached_token_count"]
        or not isinstance(hardware, Mapping)
        or hardware.get("cuda_device_count") != 1
        or "B200" not in str(hardware.get("gpu_name"))
        or int(hardware.get("gpu_total_memory_bytes", 0)) < 160 * 1024**3
        or software != EXPECTED_SOFTWARE
        or not isinstance(determinism, Mapping)
        or determinism
        != {
            "seed": expected_seed,
            "cublas_workspace_config": base_protocol.CUBLAS_WORKSPACE_CONFIG_VALUE,
            "deterministic_algorithms": True,
            "cuda_matmul_tf32": False,
            "cudnn_tf32": False,
            "flash_sdp_enabled": False,
            "mem_efficient_sdp_enabled": False,
            "math_sdp_enabled": True,
        }
        or not isinstance(runtime["first_model_forward_at_utc"], str)
        or not isinstance(runtime["last_model_forward_at_utc"], str)
    ):
        raise CalibrationAuditError("runtime/hardware/forward contract differs")

    resource = complete.get("resource")
    if not isinstance(resource, Mapping):
        raise CalibrationAuditError("resource receipt is missing")
    _require_exact_fields(
        resource,
        {
            "hourly_price_usd",
            "campaign_started_at_unix",
            "campaign_deadline_at_unix",
            "runner_deadline_at_unix",
            "runner_watchdog_seconds",
            "run_started_at_unix",
            "run_completed_at_unix",
            "campaign_elapsed_seconds",
            "campaign_estimated_spend_usd",
        },
        "resource receipt",
    )
    price = float(resource["hourly_price_usd"])
    campaign_start = float(resource["campaign_started_at_unix"])
    deadline = float(resource["campaign_deadline_at_unix"])
    runner_deadline = float(resource["runner_deadline_at_unix"])
    runner_seconds = float(resource["runner_watchdog_seconds"])
    run_start = float(resource["run_started_at_unix"])
    run_end = float(resource["run_completed_at_unix"])
    elapsed = float(resource["campaign_elapsed_seconds"])
    spend = float(resource["campaign_estimated_spend_usd"])
    if (
        not all(
            math.isfinite(value)
            for value in (
                price,
                campaign_start,
                deadline,
                runner_deadline,
                runner_seconds,
                run_start,
                run_end,
                elapsed,
                spend,
            )
        )
        or price <= 0
        or not campaign_start <= run_start <= run_end <= deadline
        or runner_seconds != protocol.RESOURCE_LIMITS["runner_sub_watchdog_seconds"]
        or runner_deadline != campaign_start + runner_seconds
        or float(runtime["runner_deadline_at_unix"]) != runner_deadline
        or run_end >= runner_deadline
        or deadline <= campaign_start
        or deadline - campaign_start > protocol.RESOURCE_LIMITS["max_walltime_seconds"]
        or price * (deadline - campaign_start) / 3600
        > protocol.RESOURCE_LIMITS["max_spend_usd"]
        or not math.isclose(elapsed, run_end - campaign_start, abs_tol=1e-6)
        or not math.isclose(spend, price * elapsed / 3600, abs_tol=1e-9)
        or run_end - run_start > protocol.RESOURCE_LIMITS["runner_sub_watchdog_seconds"]
        or spend > protocol.RESOURCE_LIMITS["max_spend_usd"]
    ):
        raise CalibrationAuditError("resource/deadline accounting differs")

    binding = _json(run_root / "execution_binding.json")
    _require_exact_fields(
        binding,
        {
            "study_id",
            "protocol_version",
            "plan_manifest_sha256",
            "plan_git_head_commit",
            "pod_id",
            "volume_id",
            "data_center_id",
            "ownership_receipt_sha256",
            "guest_receipt_sha256",
            "cache_receipt_sha256",
            "authorization_receipt_sha256",
            "artifacts",
            "adaptive_design_inputs_sha256",
            "analysis_data_inputs",
            "target_prompt_render_count",
            "target_feature_vector_count",
            "live_public_cache_rehash",
            "intervention_state_contract_sha256",
            "j_state_contract_sha256",
            "fixed_panel_estimand_sha256",
        },
        "execution binding",
    )
    artifacts = binding.get("artifacts")
    if not isinstance(artifacts, Mapping) or set(artifacts) != {"sae", "j_lens"}:
        raise CalibrationAuditError("execution artifact binding differs")
    for label, expected_hash in (
        ("sae", protocol.SAE_SPEC["sha256"]),
        ("j_lens", protocol.J_LENS_SPEC["sha256"]),
    ):
        record = artifacts[label]
        if (
            not isinstance(record, Mapping)
            or set(record) != {"path", "bytes", "sha256"}
            or record.get("sha256") != expected_hash
            or int(record.get("bytes", 0)) <= 0
        ):
            raise CalibrationAuditError(f"execution {label} artifact differs")
    for field in (
        "ownership_receipt_sha256",
        "guest_receipt_sha256",
        "cache_receipt_sha256",
        "authorization_receipt_sha256",
    ):
        _require_hex64(binding[field], f"execution binding {field}")
    if (
        binding["study_id"] != protocol.STUDY_ID
        or binding["protocol_version"] != protocol.PROTOCOL_VERSION
        or binding["plan_manifest_sha256"] != plan["plan_manifest_sha256"]
        or binding["plan_git_head_commit"] != plan["git_head_commit"]
        or not isinstance(binding["pod_id"], str)
        or not binding["pod_id"]
        or binding["volume_id"] != protocol.NETWORK_VOLUME_ID
        or complete.get("volume_id") != protocol.NETWORK_VOLUME_ID
        or binding["data_center_id"] != protocol.DATA_CENTER_ID
        or binding["adaptive_design_inputs_sha256"]
        != protocol.canonical_sha256(protocol.ADAPTIVE_DESIGN_INPUTS)
        or binding["analysis_data_inputs"] != []
        or binding["target_prompt_render_count"] != 0
        or binding["target_feature_vector_count"] != 0
        or binding["intervention_state_contract_sha256"]
        != protocol.canonical_sha256(protocol.INTERVENTION_STATE_CONTRACT)
        or binding["j_state_contract_sha256"]
        != protocol.canonical_sha256(protocol.J_STATE_CONTRACT)
        or binding["fixed_panel_estimand_sha256"]
        != protocol.canonical_sha256(protocol.FIXED_PANEL_ESTIMAND)
    ):
        raise CalibrationAuditError("execution identity/provenance binding differs")
    live_cache_rehash = _validate_live_public_cache_rehash(
        binding["live_public_cache_rehash"]
    )
    if live_cache_rehash != runtime["live_public_cache_rehash"]:
        raise CalibrationAuditError("runtime/execution live-cache rehash differs")
    return {
        "authorization_receipt_sha256": binding["authorization_receipt_sha256"],
        "ownership_receipt_sha256": binding["ownership_receipt_sha256"],
        "guest_receipt_sha256": binding["guest_receipt_sha256"],
        "cache_receipt_sha256": binding["cache_receipt_sha256"],
        "campaign_started_at_unix": campaign_start,
        "campaign_deadline_at_unix": deadline,
        "hourly_price_usd": price,
        "bound_j_lens_path": str(artifacts["j_lens"]["path"]),
        "j_orientation_status": str(runtime["j_orientation_status"]),
        "runtime_total_rendered_token_count": int(
            runtime["total_rendered_token_count"]
        ),
        "runtime_prefix_uncached_token_count": int(
            runtime["prefix_uncached_token_count"]
        ),
        "runtime_continuation_uncached_token_count": int(
            runtime["continuation_uncached_token_count"]
        ),
        "runtime_total_uncached_token_count": int(
            runtime["total_uncached_token_count"]
        ),
        "live_public_cache_rehash_receipt_sha256": live_cache_rehash["receipt_sha256"],
    }


class _AuditBudgetWatchdog:
    def __init__(
        self,
        binding: Mapping[str, Any],
        *,
        audit_started_at_unix: float | None = None,
    ) -> None:
        self.started = float(binding["campaign_started_at_unix"])
        self.deadline = float(binding["campaign_deadline_at_unix"])
        self.audit_started_at_unix = (
            time.time()
            if audit_started_at_unix is None
            else float(audit_started_at_unix)
        )
        self.rate = max(
            float(binding["hourly_price_usd"]),
            float(
                protocol.RESOURCE_LIMITS["conservative_accounting_rate_usd_per_hour"]
            ),
        )
        if (
            not math.isfinite(self.audit_started_at_unix)
            or self.audit_started_at_unix < self.started
            or self.audit_started_at_unix
            >= self.started + protocol.RESOURCE_LIMITS["runner_sub_watchdog_seconds"]
        ):
            raise CalibrationAuditError(
                "audit did not start inside the frozen 60-minute runner window"
            )

    def check(self) -> None:
        now = time.time()
        elapsed = now - self.started
        if (
            elapsed < 0
            or now >= self.deadline
            or elapsed > protocol.RESOURCE_LIMITS["max_walltime_seconds"]
            or self.rate * elapsed / 3600 > protocol.RESOURCE_LIMITS["max_spend_usd"]
        ):
            raise CalibrationAuditError(
                "audit stopped at the frozen 90-minute/$9 campaign boundary"
            )


def _audit_model_snapshot(
    model_snapshot: Path, watchdog: _AuditBudgetWatchdog
) -> tuple[Path, dict[str, Any]]:
    lexical = model_snapshot.expanduser().absolute()
    if lexical.is_symlink():
        raise CalibrationAuditError("model snapshot is a symlink")
    snapshot = lexical.resolve(strict=True)
    if not snapshot.is_dir() or snapshot.name != "model_snapshot":
        raise CalibrationAuditError("model snapshot path differs")
    legacy = _json(LEGACY_ARTIFACT_MANIFEST)
    records = [
        row
        for row in legacy.get("files", [])
        if str(row.get("path", "")).startswith("model_snapshot/")
    ]
    if not records:
        raise CalibrationAuditError("pinned model artifact manifest is empty")
    expected_paths = {str(row["path"])[len("model_snapshot/") :] for row in records}
    observed_paths = {
        path.relative_to(snapshot).as_posix()
        for path in snapshot.rglob("*")
        if path.is_file()
    }
    if observed_paths != expected_paths:
        raise CalibrationAuditError("model snapshot file inventory differs")
    verified = []
    for row in records:
        watchdog.check()
        relative = str(row["path"])[len("model_snapshot/") :]
        path = snapshot / relative
        if (
            path.is_symlink()
            or not path.is_file()
            or path.stat().st_size != int(row.get("bytes", -1))
            or protocol.sha256_file(path) != row.get("sha256")
        ):
            raise CalibrationAuditError(f"pinned model artifact differs: {relative}")
        verified.append(
            {
                "path": relative,
                "bytes": path.stat().st_size,
                "sha256": row["sha256"],
            }
        )
        watchdog.check()
    config = _json(snapshot / "config.json")
    if (
        config.get("hidden_size") != protocol.WIDTH
        or config.get("num_hidden_layers") != protocol.MODEL_SPEC["layer_count"]
        or config.get("vocab_size") != protocol.VOCAB_SIZE
        or not isinstance(config.get("rms_norm_eps"), (int, float))
        or not math.isfinite(float(config["rms_norm_eps"]))
        or float(config["rms_norm_eps"]) <= 0
    ):
        raise CalibrationAuditError("model readout configuration differs")
    return snapshot, {
        "verified_file_count": len(verified),
        "verified_inventory_sha256": protocol.canonical_sha256(verified),
        "revision": protocol.MODEL_SPEC["revision"],
    }


def _load_model_readout(
    snapshot: Path, token_ids: Sequence[int], *, device: Any
) -> tuple[Any, Any, float]:
    import torch

    try:
        from safetensors import safe_open
    except ImportError as exc:  # pragma: no cover - GPU environment only
        raise CalibrationAuditError("safetensors is required for model audit") from exc
    index = _json(snapshot / "model.safetensors.index.json")
    weight_map = index.get("weight_map")
    if not isinstance(weight_map, Mapping):
        raise CalibrationAuditError("model weight-map is missing")

    def load(name: str) -> Any:
        shard = weight_map.get(name)
        if not isinstance(shard, str):
            raise CalibrationAuditError(f"model weight is missing: {name}")
        path = snapshot / shard
        with safe_open(str(path), framework="pt", device="cpu") as handle:
            if name not in handle.keys():
                raise CalibrationAuditError(f"model shard lacks weight: {name}")
            return handle.get_tensor(name)

    norm = load("model.norm.weight")
    full_head = load("lm_head.weight")
    if (
        tuple(norm.shape) != (protocol.WIDTH,)
        or tuple(full_head.shape) != (protocol.VOCAB_SIZE, protocol.WIDTH)
        or norm.dtype != torch.bfloat16
        or full_head.dtype != torch.bfloat16
        or not bool(torch.isfinite(norm).all())
        or not bool(torch.isfinite(full_head).all())
    ):
        raise CalibrationAuditError("model norm/LM-head artifact differs")
    ids = torch.tensor(list(token_ids), dtype=torch.long)
    selected_head = full_head.index_select(0, ids).contiguous()
    del full_head
    config = _json(snapshot / "config.json")
    return (
        norm.to(device=device, non_blocking=True).contiguous(),
        selected_head.to(device=device, non_blocking=True).contiguous(),
        float(config["rms_norm_eps"]),
    )


def _load_j_checkpoint(
    j_lens_path: Path, watchdog: _AuditBudgetWatchdog
) -> tuple[Path, Mapping[Any, Any], dict[str, Any]]:
    import torch

    lexical = j_lens_path.expanduser().absolute()
    if lexical.is_symlink():
        raise CalibrationAuditError("J-lens checkpoint is a symlink")
    path = lexical.resolve(strict=True)
    watchdog.check()
    if (
        not path.is_file()
        or protocol.sha256_file(path) != protocol.J_LENS_SPEC["sha256"]
    ):
        raise CalibrationAuditError("J-lens checkpoint hash differs")
    watchdog.check()
    checkpoint = torch.load(path, map_location="cpu", weights_only=True, mmap=True)
    if (
        not isinstance(checkpoint, Mapping)
        or not {"J", "n_prompts", "d_model"} <= set(checkpoint)
        or int(checkpoint["n_prompts"])
        != int(protocol.J_LENS_SPEC["release_config"]["prompts_fitted"])
        or int(checkpoint["d_model"]) != protocol.WIDTH
        or not isinstance(checkpoint["J"], Mapping)
    ):
        raise CalibrationAuditError("J-lens checkpoint metadata differs")
    maps = checkpoint["J"]
    available = {int(layer) for layer in maps}
    if available != set(protocol.J_LAYERS):
        raise CalibrationAuditError("J-lens map inventory differs")
    return (
        path,
        maps,
        {
            "sha256": protocol.J_LENS_SPEC["sha256"],
            "map_count": len(available),
            "revision": protocol.J_LENS_SPEC["revision"],
        },
    )


class _ArtifactJBackend:
    def __init__(
        self,
        raw_maps: Mapping[Any, Any],
        *,
        device: Any,
        watchdog: _AuditBudgetWatchdog,
    ) -> None:
        import torch

        self.torch = torch
        self.raw_maps = raw_maps
        self.device = device
        self.watchdog = watchdog

    def raw_matrix(self, layer: int) -> Any:
        value = (
            self.raw_maps[layer]
            if layer in self.raw_maps
            else self.raw_maps[str(layer)]
        )
        if tuple(value.shape) != (protocol.WIDTH, protocol.WIDTH):
            raise CalibrationAuditError(f"J[{layer}] shape differs")
        return value

    def j_matrix(self, layer: int) -> Any:
        self.watchdog.check()
        matrix = (
            self.raw_matrix(layer)
            .to(device=self.device, dtype=self.torch.bfloat16, non_blocking=True)
            .contiguous()
        )
        if not bool(self.torch.isfinite(matrix).all()):
            raise CalibrationAuditError(f"J[{layer}] is non-finite")
        return matrix


def _configure_artifact_device(device_name: str) -> Any:
    import torch

    device = torch.device(device_name)
    if (
        device.type != "cuda"
        or not torch.cuda.is_available()
        or torch.cuda.device_count() != 1
    ):
        raise CalibrationAuditError(
            "full artifact recomputation requires the authorized single CUDA GPU"
        )
    properties = torch.cuda.get_device_properties(device)
    if (
        "B200" not in str(properties.name)
        or int(properties.total_memory) < 160 * 1024**3
    ):
        raise CalibrationAuditError("artifact audit requires the authorized B200")
    if os.environ.get(base_protocol.CUBLAS_WORKSPACE_CONFIG_ENV) != (
        base_protocol.CUBLAS_WORKSPACE_CONFIG_VALUE
    ):
        raise CalibrationAuditError("artifact audit CUBLAS determinism differs")
    seed = protocol.seed64("runtime-v2") % (2**63 - 1)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)
    torch.use_deterministic_algorithms(True)
    torch.backends.cuda.matmul.allow_tf32 = False
    torch.backends.cudnn.allow_tf32 = False
    torch.backends.cuda.enable_flash_sdp(False)
    torch.backends.cuda.enable_mem_efficient_sdp(False)
    torch.backends.cuda.enable_math_sdp(True)
    return device


def _random_j_parameters(
    layer: int, index: int, *, device: Any, width: int | None = None
) -> tuple[Any, ...]:
    import numpy as np
    import torch

    size = protocol.WIDTH if width is None else int(width)
    rng = np.random.Generator(
        np.random.PCG64(protocol.seed64("random-j-v2", layer, index))
    )
    return (
        torch.from_numpy(rng.permutation(size).astype(np.int64)).to(device=device),
        torch.from_numpy(rng.choice(np.array([-1.0, 1.0], dtype=np.float32), size)).to(
            device=device
        ),
        torch.from_numpy(rng.permutation(size).astype(np.int64)).to(device=device),
        torch.from_numpy(rng.choice(np.array([-1.0, 1.0], dtype=np.float32), size)).to(
            device=device
        ),
    )


def _direct_transport(source: Any, matrix: Any, *, layer: int, transport: str) -> Any:
    value = source.to(device=matrix.device)
    if transport == "real_j":
        return value.to(dtype=matrix.dtype) @ matrix.T
    if transport == "identity":
        return value.to(dtype=matrix.dtype)
    if transport.startswith("random_j_"):
        index = int(transport.rsplit("_", 1)[1])
        input_perm, input_sign, output_perm, output_sign = _random_j_parameters(
            layer, index, device=matrix.device, width=int(matrix.shape[0])
        )
        scrambled = value.to(dtype=matrix.dtype)[..., input_perm] * input_sign.to(
            dtype=matrix.dtype
        )
        predicted = scrambled @ matrix.T
        return predicted[..., output_perm] * output_sign.to(dtype=predicted.dtype)
    raise CalibrationAuditError(f"unknown transport in artifact audit: {transport}")


def _selected_logits(state: Any, norm: Any, head: Any, eps: float) -> Any:
    import torch

    hidden = state.to(device=norm.device, dtype=norm.dtype)
    values = hidden.float()
    normalized = values * torch.rsqrt(values.square().mean(dim=-1, keepdim=True) + eps)
    normalized = normalized.to(dtype=norm.dtype) * norm
    return (normalized.to(dtype=head.dtype) @ head.T).float().reshape(-1)


def _midpoint_selected_logit_contrast(
    final_midpoint: Any,
    prediction: Any,
    norm: Any,
    head: Any,
    eps: float,
) -> Any:
    return (
        _selected_logits(final_midpoint.float() + prediction.float(), norm, head, eps)
        - _selected_logits(final_midpoint.float() - prediction.float(), norm, head, eps)
    ) * 0.5


def _require_tensor_exact(observed: Any, expected: Any, label: str) -> None:
    import torch

    candidate = observed.to(device=expected.device)
    if (
        candidate.dtype != expected.dtype
        or tuple(candidate.shape) != tuple(expected.shape)
        or not torch.equal(candidate, expected)
    ):
        raise CalibrationAuditError(f"direct artifact recomputation differs: {label}")


def _audit_artifact_recomputation(
    *,
    run_root: Path,
    prompt_data: Sequence[Mapping[str, Any]],
    selected_ids: Sequence[int],
    plan_hash: str,
    model_snapshot: Path,
    j_lens_path: Path,
    device_name: str,
    watchdog: _AuditBudgetWatchdog,
) -> dict[str, Any]:
    import torch

    watchdog.check()
    device = _configure_artifact_device(device_name)
    snapshot, model_record = _audit_model_snapshot(model_snapshot, watchdog)
    watchdog.check()
    norm, head, eps = _load_model_readout(snapshot, selected_ids, device=device)
    watchdog.check()
    j_path, raw_maps, j_record = _load_j_checkpoint(j_lens_path, watchdog)
    backend = _ArtifactJBackend(raw_maps, device=device, watchdog=watchdog)

    archived_orientation_rows = _jsonl(run_root / "j_orientation_rows.jsonl")
    archived_orientation_receipt = _json(run_root / "j_orientation_receipt.json")
    try:
        orientation.validate(
            archived_orientation_rows,
            archived_orientation_receipt,
            plan_hash=plan_hash,
        )
        recomputed_orientation_rows, recomputed_orientation_receipt = (
            orientation.execute(backend, plan_manifest_sha256=plan_hash)
        )
    except orientation.OrientationError as exc:
        raise CalibrationAuditError(f"J orientation audit failed: {exc}") from exc
    if (
        protocol.canonical_json_bytes(recomputed_orientation_rows)
        != protocol.canonical_json_bytes(archived_orientation_rows)
        or recomputed_orientation_receipt != archived_orientation_receipt
    ):
        raise CalibrationAuditError("J orientation artifact recomputation differs")

    matrix50 = backend.j_matrix(protocol.EDIT_LAYER)
    raw50 = (
        backend.raw_matrix(protocol.EDIT_LAYER)
        .to(device=device, dtype=torch.float32, non_blocking=True)
        .contiguous()
    )
    shadow_count = 0
    actual_logit_count = 0
    for prompt in prompt_data:
        watchdog.check()
        arcs = prompt["arcs"]
        arithmetic = prompt["arithmetic"]
        readout = prompt["readout"]
        for pair_offset in range(len(protocol.DIRECTIONS) * len(protocol.DOSE_GRID)):
            source = arithmetic["realized_central_fp32"][pair_offset]
            expected_bf16 = source.to(device=device, dtype=torch.bfloat16) @ matrix50.T
            expected_fp32 = source.to(device=device, dtype=torch.float32) @ raw50.T
            _require_tensor_exact(
                arithmetic["j_prediction_bfloat16"][pair_offset],
                expected_bf16,
                f"{prompt['prompt_id']}/shadow/{pair_offset}/bf16",
            )
            _require_tensor_exact(
                arithmetic["j_prediction_fp32"][pair_offset],
                expected_fp32,
                f"{prompt['prompt_id']}/shadow/{pair_offset}/fp32",
            )
            shadow_count += 1
        for direction_offset, _direction in enumerate(protocol.DIRECTIONS):
            pair_offset = direction_offset * len(protocol.DOSE_GRID) + (
                protocol.DOSE_GRID.index(protocol.PRIMARY_DOSE)
            )
            plus = arcs[pair_offset * 2]
            minus = arcs[pair_offset * 2 + 1]
            expected_actual = (
                _selected_logits(plus[-1], norm, head, eps)
                - _selected_logits(minus[-1], norm, head, eps)
            ) * 0.5
            _require_tensor_exact(
                readout["actual_selected_logit_delta_fp32"][direction_offset],
                expected_actual,
                f"{prompt['prompt_id']}/actual-logits/{direction_offset}",
            )
            actual_logit_count += 1
    del raw50, matrix50

    transport_count = 0
    predicted_logit_count = 0
    for layer_offset, layer in enumerate(protocol.READOUT_LAYERS):
        watchdog.check()
        matrix = backend.j_matrix(layer)
        for prompt in prompt_data:
            arcs = prompt["arcs"]
            readout = prompt["readout"]
            for direction_offset, direction in enumerate(protocol.DIRECTIONS):
                pair_offset = direction_offset * len(protocol.DOSE_GRID) + (
                    protocol.DOSE_GRID.index(protocol.PRIMARY_DOSE)
                )
                plus = arcs[pair_offset * 2]
                minus = arcs[pair_offset * 2 + 1]
                final_midpoint = (
                    plus[-1].float().to(device=device)
                    + minus[-1].float().to(device=device)
                ) * 0.5
                source = readout["source_delta_fp32"][direction_offset, layer_offset]
                for transport_offset, transport_name in enumerate(protocol.TRANSPORTS):
                    expected_prediction = _direct_transport(
                        source,
                        matrix,
                        layer=layer,
                        transport=transport_name,
                    ).contiguous()
                    _require_tensor_exact(
                        readout["transport_prediction_bfloat16"][
                            direction_offset, layer_offset, transport_offset
                        ],
                        expected_prediction,
                        (
                            f"{prompt['prompt_id']}/{direction}/{layer}/"
                            f"{transport_name}/prediction"
                        ),
                    )
                    expected_logits = _midpoint_selected_logit_contrast(
                        final_midpoint,
                        expected_prediction,
                        norm,
                        head,
                        eps,
                    )
                    _require_tensor_exact(
                        readout["transport_selected_logit_delta_fp32"][
                            direction_offset, layer_offset, transport_offset
                        ],
                        expected_logits,
                        (
                            f"{prompt['prompt_id']}/{direction}/{layer}/"
                            f"{transport_name}/selected-logits"
                        ),
                    )
                    transport_count += 1
                    predicted_logit_count += 1
        del matrix
        torch.cuda.empty_cache()
        watchdog.check()
    watchdog.check()
    return {
        "status": "pass",
        "orientation_status": str(recomputed_orientation_receipt["status"]),
        "gpu_required": True,
        "device": str(device),
        "model": model_record,
        "j_lens": {**j_record, "path": j_path.as_posix()},
        "orientation_row_count": len(recomputed_orientation_rows),
        "j_shadow_pair_count": shadow_count,
        "transport_prediction_count": transport_count,
        "predicted_selected_logit_count": predicted_logit_count,
        "actual_selected_logit_count": actual_logit_count,
        "exact_tensor_equality_required": True,
    }


def _bootstrap(prompt_values: Mapping[str, float], namespace: str) -> dict[str, Any]:
    import numpy as np

    ids = tuple(sorted(prompt_values))
    if ids != tuple(sorted(protocol.PROMPT_IDS)):
        raise CalibrationAuditError(f"bootstrap cluster inventory differs: {namespace}")
    values = np.asarray(
        [prompt_values[prompt_id] for prompt_id in ids], dtype=np.float64
    )
    rng = np.random.Generator(np.random.PCG64(protocol.seed64("bootstrap", namespace)))
    count = int(protocol.GATE_THRESHOLDS["bootstrap_replicates"])
    draws = rng.integers(0, len(values), size=(count, len(values)))
    means = values[draws].mean(axis=1)
    return {
        "estimate": float(values.mean()),
        "lcb_95": float(np.quantile(means, 0.025)),
        "ucb_95": float(np.quantile(means, 0.975)),
        "cluster_count": len(values),
        "bootstrap_replicates": count,
        "interval_label": protocol.FIXED_PANEL_ESTIMAND["interval_label"],
        "estimand_scope": protocol.FIXED_PANEL_ESTIMAND["aggregation_order"],
    }


def _transport_summary(
    rows: Sequence[Mapping[str, Any]], *, j_projection_eligible: bool
) -> dict[str, Any]:
    indexed = {
        (
            str(row["prompt_id"]),
            int(row["direction"]),
            int(row["readout_layer"]),
            str(row["transport"]),
        ): row
        for row in rows
    }
    expected = (
        len(protocol.PROMPT_IDS)
        * len(protocol.DIRECTIONS)
        * len(protocol.READOUT_LAYERS)
        * len(protocol.TRANSPORTS)
    )
    if len(indexed) != expected:
        raise CalibrationAuditError("readout transport identity inventory differs")

    def summarize(
        metric: str, layer: int, directions: Sequence[int], suffix: str
    ) -> dict[str, Any]:
        absolute: dict[str, float] = {}
        identity: dict[str, float] = {}
        random: dict[str, float] = {}
        for prompt_id in protocol.PROMPT_IDS:
            real_values = []
            identity_values = []
            random_values = []
            for direction in directions:
                real = float(indexed[(prompt_id, direction, layer, "real_j")][metric])
                baseline = float(
                    indexed[(prompt_id, direction, layer, "identity")][metric]
                )
                strongest_random = max(
                    float(
                        indexed[(prompt_id, direction, layer, f"random_j_{index}")][
                            metric
                        ]
                    )
                    for index in range(protocol.RANDOM_J_COUNT)
                )
                real_values.append(real)
                identity_values.append(real - baseline)
                random_values.append(real - strongest_random)
            absolute[prompt_id] = sum(real_values) / len(real_values)
            identity[prompt_id] = sum(identity_values) / len(identity_values)
            random[prompt_id] = sum(random_values) / len(random_values)
        absolute_result = _bootstrap(absolute, f"{metric}:{layer}:{suffix}:absolute")
        identity_result = _bootstrap(identity, f"{metric}:{layer}:{suffix}:identity")
        random_result = _bootstrap(random, f"{metric}:{layer}:{suffix}:random")
        if metric == "residual_delta_cosine":
            absolute_threshold = protocol.GATE_THRESHOLDS[
                "real_j_residual_cosine_lcb_min"
            ]
            identity_threshold = protocol.GATE_THRESHOLDS[
                "real_j_residual_cosine_margin_over_identity"
            ]
            random_threshold = protocol.GATE_THRESHOLDS[
                "real_j_residual_cosine_margin_over_best_random"
            ]
        else:
            absolute_threshold = protocol.GATE_THRESHOLDS[
                "real_j_logit_pearson_lcb_min"
            ]
            identity_threshold = protocol.GATE_THRESHOLDS[
                "real_j_logit_pearson_margin_over_identity"
            ]
            random_threshold = protocol.GATE_THRESHOLDS[
                "real_j_logit_pearson_margin_over_best_random"
            ]
        statuses = {
            "absolute_real_j_status": "pass"
            if absolute_result["lcb_95"] > absolute_threshold
            else "fail",
            "real_j_over_identity_status": "pass"
            if identity_result["lcb_95"] > identity_threshold
            else "fail",
            "real_j_over_five_random_status": "pass"
            if random_result["lcb_95"] > random_threshold
            else "fail",
        }
        return {
            **statuses,
            "composite_status": "pass"
            if all(value == "pass" for value in statuses.values())
            else "fail",
            "descriptive_j_readout_status": "pass"
            if statuses["absolute_real_j_status"] == "pass"
            and statuses["real_j_over_five_random_status"] == "pass"
            else "fail",
            "absolute_real_j": {**absolute_result, "threshold": absolute_threshold},
            "real_j_minus_identity": {
                **identity_result,
                "threshold": identity_threshold,
            },
            "real_j_minus_best_of_five_random": {
                **random_result,
                "threshold": random_threshold,
            },
        }

    output: dict[str, Any] = {}
    for metric in ("residual_delta_cosine", "fixed_token_logit_delta_pearson"):
        by_layer = {
            str(layer): summarize(metric, layer, protocol.DIRECTIONS, "all-directions")
            for layer in protocol.READOUT_LAYERS
        }
        by_layer_direction = {
            f"{layer}:{direction}": summarize(
                metric, layer, (direction,), f"direction-{direction}"
            )
            for layer in protocol.READOUT_LAYERS
            for direction in protocol.DIRECTIONS
        }
        output[metric] = {
            "by_readout_layer": by_layer,
            "by_readout_layer_and_direction": by_layer_direction,
        }
    descriptive = []
    added_value = []
    for layer in protocol.READOUT_LAYERS:
        metric_rows = [
            output[metric]["by_readout_layer"][str(layer)]
            for metric in ("residual_delta_cosine", "fixed_token_logit_delta_pearson")
        ]
        if all(row["descriptive_j_readout_status"] == "pass" for row in metric_rows):
            descriptive.append(layer)
        if all(row["composite_status"] == "pass" for row in metric_rows):
            added_value.append(layer)
    primary_layer = int(protocol.PRIMARY_READOUT_LAYER)
    output["fixed_panel_estimand"] = dict(protocol.FIXED_PANEL_ESTIMAND)
    output["nonprimary_layer_role"] = "descriptive_diagnostic_only"
    output["diagnostic_descriptive_j_readout_threshold_pass_layers"] = descriptive
    output["diagnostic_learned_j_added_value_threshold_pass_layers"] = added_value
    output["descriptive_j_readout_eligible_layers"] = (
        [primary_layer]
        if j_projection_eligible and primary_layer in descriptive
        else []
    )
    output["learned_j_added_value_eligible_layers"] = (
        [primary_layer]
        if j_projection_eligible and primary_layer in added_value
        else []
    )
    output["descriptive_j_readout_eligible_layers_70_78"] = []
    output["learned_j_added_value_eligible_layers_70_78"] = []
    return output


def _separated_claim_statuses(
    *,
    edit_failure_count: int,
    j_shadow_failure_count: int,
    component_failures: Mapping[str, int],
    orientation_status: str,
) -> dict[str, str]:
    edit = "pass" if edit_failure_count == 0 else "fail"
    source_linearity = (
        "pass" if int(component_failures["realized_source"]) == 0 else "fail"
    )
    j_linearity = "pass" if int(component_failures["j_of_realized"]) == 0 else "fail"
    downstream = (
        "pass" if int(component_failures["actual_final"]) == 0 else "nonlinear_observed"
    )
    j_shadow = "pass" if j_shadow_failure_count == 0 else "fail"
    j_projection = (
        "pass" if orientation_status == "pass" and j_shadow == "pass" else "fail"
    )
    return {
        "edit_integrity_status": edit,
        "realized_source_linearity_status": source_linearity,
        "j_of_realized_linearity_status": j_linearity,
        "downstream_model_linearity_status": downstream,
        "j_shadow_status": j_shadow,
        "j_orientation_status": orientation_status,
        "j_projection_claim_eligibility": j_projection,
        # Only delivery fidelity/common mode gate collection.  Linearity and J
        # remain independently reported interpretation gates.
        "later_actual_state_collection_eligibility": edit,
    }


def _hard_safety_failed(row: Mapping[str, Any]) -> bool:
    return not bool(row["hard_safety_pass"])


def _delivery_gate_failed(row: Mapping[str, Any]) -> bool:
    threshold = protocol.GATE_THRESHOLDS["requested_realized_relative_rmse_max"]
    return bool(
        any(
            float(row[field]) > threshold
            for field in (
                "requested_plus_realized_relative_rmse",
                "requested_minus_realized_relative_rmse",
                "requested_realized_central_relative_rmse",
            )
        )
        or any(
            float(row[field])
            < protocol.GATE_THRESHOLDS["requested_realized_cosine_min"]
            for field in (
                "requested_plus_realized_cosine",
                "requested_minus_realized_cosine",
                "requested_realized_central_cosine",
            )
        )
        or float(row["common_mode_to_central_rms"])
        > protocol.GATE_THRESHOLDS["common_mode_to_central_rms_max"]
    )


def _edit_gate_failed(row: Mapping[str, Any]) -> bool:
    """Combined row diagnostic retained for compact callers and tests."""

    return _hard_safety_failed(row) or _delivery_gate_failed(row)


def _collection_edit_gate_failed(dose: float, row: Mapping[str, Any]) -> bool:
    """Hard safety gates every dose; fidelity gates only prospective doses."""

    return _hard_safety_failed(row) or (
        dose in protocol.REALIZATION_GATE_DOSES and _delivery_gate_failed(row)
    )


def _j_shadow_gate_failed(row: Mapping[str, Any]) -> bool:
    return bool(
        float(row["bf16_fp32_j_cosine"])
        < protocol.GATE_THRESHOLDS["bf16_fp32_j_cosine_min"]
        or float(row["bf16_fp32_j_relative_rmse"])
        > protocol.GATE_THRESHOLDS["bf16_fp32_j_relative_rmse_max"]
    )


def _linearity_summary(
    linearity_inputs: Mapping[
        tuple[str, int], Mapping[float, tuple[Any, Any, Any, float, float]]
    ],
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Recompute finite, dose-scaled source/J/downstream linearity summaries."""

    rows: list[dict[str, Any]] = []
    failures = {"realized_source": 0, "j_of_realized": 0, "actual_final": 0}
    for key in sorted(linearity_inputs):
        values = linearity_inputs[key]
        anchor = values[protocol.PRIMARY_DOSE]
        row: dict[str, Any] = {
            "prompt_id": key[0],
            "direction": key[1],
            "gate_doses": list(protocol.LINEARITY_GATE_DOSES),
            "source_scaling_denominator": "requested_bf16_rms_fraction",
            "j_and_final_scaling_denominator": "realized_source_rms_fraction",
            "realized_to_requested_source_gain_by_dose": {
                str(dose): _safe_ratio(float(values[dose][4]), float(values[dose][3]))
                for dose in protocol.LINEARITY_GATE_DOSES
            },
        }
        for component_index, component in enumerate(
            ("realized_source", "j_of_realized", "actual_final")
        ):
            denominator_index = 3 if component == "realized_source" else 4
            scales = [
                float(values[dose][denominator_index])
                for dose in protocol.LINEARITY_GATE_DOSES
            ]
            zero_scale_failure = any(scale <= 0.0 for scale in scales)
            if zero_scale_failure:
                # A swallowed edit is a finite failed observation, not an
                # exception or an undefined JSON number.
                minimum = 0.0
                maximum = 1.0
            else:
                anchor_slope = anchor[component_index] / float(
                    anchor[denominator_index]
                )
                slopes = [
                    values[dose][component_index]
                    / float(values[dose][denominator_index])
                    for dose in protocol.LINEARITY_GATE_DOSES
                ]
                minimum = min(_cosine(slope, anchor_slope) for slope in slopes)
                maximum = max(_relative_rmse(slope, anchor_slope) for slope in slopes)
            status = (
                "pass"
                if (
                    not zero_scale_failure
                    and minimum >= protocol.GATE_THRESHOLDS["linearity_cosine_min"]
                    and maximum
                    <= protocol.GATE_THRESHOLDS["linearity_slope_discrepancy_max"]
                )
                else "fail"
            )
            if status == "fail":
                failures[component] += 1
            row[f"{component}_linearity_cosine_min"] = minimum
            row[f"{component}_slope_discrepancy_max"] = maximum
            row[f"{component}_zero_scale_failure"] = zero_scale_failure
            row[f"{component}_status"] = status
        rows.append(row)
    return rows, failures


def audit(
    run_root: Path,
    plan_dir: Path,
    *,
    model_snapshot: Path,
    j_lens_path: Path,
    ownership_receipt: Path,
    guest_receipt: Path,
    cache_receipt: Path,
    authorization_receipt: Path,
    artifact_device: str = "cuda:0",
) -> tuple[dict[str, Any], dict[str, Any]]:
    import numpy as np
    import torch

    audit_started_at_unix = time.time()

    lexical_root = run_root.expanduser().absolute()
    if lexical_root.is_symlink() or lexical_root.name.endswith(".partial"):
        raise CalibrationAuditError("audit accepts only a finalized real run")
    root = lexical_root.resolve(strict=True)
    expected_tail = (
        protocol.STUDY_SLUG,
        protocol.STUDY_ID,
        "raw",
        root.name,
    )
    if tuple(root.parts[-4:]) != expected_tail:
        raise CalibrationAuditError("raw run is outside the exact v2 namespace")

    preliminary = _json(root / "RUN_COMPLETE.json")
    preliminary_resource = preliminary.get("resource")
    if not isinstance(preliminary_resource, Mapping):
        raise CalibrationAuditError("preliminary resource receipt is missing")
    watchdog = _AuditBudgetWatchdog(
        preliminary_resource,
        audit_started_at_unix=audit_started_at_unix,
    )
    watchdog.check()
    complete = _manifest(root)
    watchdog.check()
    plan, plan_audit_receipt = _audit_plan(plan_dir)
    supplied_plan_hash = plan["plan_manifest_sha256"]
    if complete.get("plan_manifest_sha256") != supplied_plan_hash:
        raise CalibrationAuditError("raw run is not bound to supplied plan")
    binding_hashes = _audit_runtime_and_binding(root, complete=complete, plan=plan)
    watchdog = _AuditBudgetWatchdog(
        binding_hashes,
        audit_started_at_unix=audit_started_at_unix,
    )
    watchdog.check()
    external_receipt_validation = _audit_external_receipt_chain(
        ownership_path=ownership_receipt,
        guest_path=guest_receipt,
        cache_path=cache_receipt,
        authorization_path=authorization_receipt,
        plan_dir=plan_dir,
        plan=plan,
        execution_binding=_json(root / "execution_binding.json"),
        complete=complete,
    )
    watchdog.check()

    realization_rows = _jsonl(root / "realization_rows.jsonl")
    pair_rows = _jsonl(root / "pair_index.jsonl")
    readout_rows = _jsonl(root / "readout_transport_rows.jsonl")
    prompt_rows = _jsonl(root / "prompt_receipts.jsonl")
    clean_index = _jsonl(root / "clean_index.jsonl")
    orientation_rows = _jsonl(root / "j_orientation_rows.jsonl")
    if (
        len(realization_rows) != 120
        or len(pair_rows) != 120
        or len(readout_rows) != 4872
        or len(prompt_rows) != 8
        or len(clean_index) != 8
        or len(orientation_rows)
        != len(protocol.J_LAYERS)
        * int(protocol.J_ORIENTATION_SPEC["fixture_count_per_layer"])
    ):
        raise CalibrationAuditError("raw metadata row count differs")
    tokenizer = _load_tokenizer(model_snapshot)
    _audit_prompt_receipts(prompt_rows, tokenizer)
    rendered_token_total = sum(int(row["token_count"]) for row in prompt_rows)
    prefix_token_total = sum(int(row["prefix_token_count"]) for row in prompt_rows)
    continuation_token_total = (
        protocol.FORWARD_INVENTORY["clean_continuation_forwards"]
        + protocol.FORWARD_INVENTORY["edited_continuation_forwards"]
    )
    if (
        binding_hashes["runtime_total_rendered_token_count"] != rendered_token_total
        or binding_hashes["runtime_prefix_uncached_token_count"] != prefix_token_total
        or binding_hashes["runtime_continuation_uncached_token_count"]
        != continuation_token_total
        or binding_hashes["runtime_total_uncached_token_count"]
        != prefix_token_total + continuation_token_total
    ):
        raise CalibrationAuditError("runtime prompt/uncached-token accounting differs")
    selected_ids = _audit_fixed_panel(root)
    del tokenizer
    expected_clean_index = [
        {
            "row_index": offset,
            "prompt_id": prompt_id,
            "state_labels": [*(str(layer) for layer in protocol.J_LAYERS), "final"],
        }
        for offset, prompt_id in enumerate(protocol.PROMPT_IDS)
    ]
    if clean_index != expected_clean_index:
        raise CalibrationAuditError("clean-index inventory/order differs")
    expected_keys = [
        (row["prompt_id"], row["direction"], row["dose_fraction"])
        for row in protocol.rows()
    ]
    observed_keys = [
        (row["prompt_id"], row["direction"], row["dose_fraction"]) for row in pair_rows
    ]
    if observed_keys != expected_keys:
        raise CalibrationAuditError("pair grid/order differs")

    clean_file = _load_file(root / "residuals" / "clean.safetensors")
    if set(clean_file) != {"clean_arc_bfloat16"}:
        raise CalibrationAuditError("clean residual tensor inventory differs")
    _require_all_finite(clean_file, "clean")
    clean = clean_file["clean_arc_bfloat16"]
    if tuple(clean.shape) != (8, 35, protocol.WIDTH) or clean.dtype != torch.bfloat16:
        raise CalibrationAuditError("clean residual tensor differs")

    recomputed_realization: list[dict[str, Any]] = []
    linearity_inputs: dict[
        tuple[str, int], dict[float, tuple[Any, Any, Any, float, float]]
    ] = defaultdict(dict)
    transport_recomputed: list[dict[str, Any]] = []
    artifact_prompt_data: list[dict[str, Any]] = []
    raw_cursor = 0
    readout_cursor = 0
    for prompt_offset, prompt_id in enumerate(protocol.PROMPT_IDS):
        watchdog.check()
        residual_file = _load_file(root / "residuals" / f"{prompt_id}.safetensors")
        if set(residual_file) != {"arc_bfloat16"}:
            raise CalibrationAuditError(
                f"residual tensor inventory differs: {prompt_id}"
            )
        _require_all_finite(residual_file, f"residuals/{prompt_id}")
        arcs = residual_file["arc_bfloat16"]
        arithmetic = _load_file(root / "arithmetic" / f"{prompt_id}.safetensors")
        readout = _load_file(root / "readout_transport" / f"{prompt_id}.safetensors")
        _require_all_finite(arithmetic, f"arithmetic/{prompt_id}")
        _require_all_finite(readout, f"readout_transport/{prompt_id}")
        if (
            tuple(arcs.shape) != (30, 36, protocol.WIDTH)
            or arcs.dtype != torch.bfloat16
        ):
            raise CalibrationAuditError(f"signed residual shard differs: {prompt_id}")
        expected_arithmetic = {
            "requested_fp32": (torch.float32, (15, protocol.WIDTH)),
            "requested_bfloat16": (torch.bfloat16, (15, protocol.WIDTH)),
            "realized_plus_fp32": (torch.float32, (15, protocol.WIDTH)),
            "realized_minus_fp32": (torch.float32, (15, protocol.WIDTH)),
            "realized_central_fp32": (torch.float32, (15, protocol.WIDTH)),
            "common_mode_fp32": (torch.float32, (15, protocol.WIDTH)),
            "final_central_fp32": (torch.float32, (15, protocol.WIDTH)),
            "j_prediction_bfloat16": (torch.bfloat16, (15, protocol.WIDTH)),
            "j_prediction_fp32": (torch.float32, (15, protocol.WIDTH)),
        }
        if set(arithmetic) != set(expected_arithmetic):
            raise CalibrationAuditError(
                f"arithmetic tensor inventory differs: {prompt_id}"
            )
        for name, (dtype, shape) in expected_arithmetic.items():
            if (
                arithmetic[name].dtype != dtype
                or tuple(arithmetic[name].shape) != shape
            ):
                raise CalibrationAuditError(
                    f"arithmetic tensor differs: {prompt_id}/{name}"
                )
        expected_readout = {
            "source_delta_fp32": (torch.float32, (3, 29, protocol.WIDTH)),
            "transport_prediction_bfloat16": (
                torch.bfloat16,
                (3, 29, 7, protocol.WIDTH),
            ),
            "transport_selected_logit_delta_fp32": (
                torch.float32,
                (3, 29, 7, 2048),
            ),
            "actual_selected_logit_delta_fp32": (torch.float32, (3, 2048)),
        }
        if set(readout) != set(expected_readout):
            raise CalibrationAuditError(
                f"readout tensor inventory differs: {prompt_id}"
            )
        for name, (dtype, shape) in expected_readout.items():
            if readout[name].dtype != dtype or tuple(readout[name].shape) != shape:
                raise CalibrationAuditError(
                    f"readout tensor differs: {prompt_id}/{name}"
                )
        artifact_prompt_data.append(
            {
                "prompt_id": prompt_id,
                "clean_final": clean[prompt_offset, -1],
                "arcs": arcs,
                "arithmetic": arithmetic,
                "readout": readout,
            }
        )

        clean_source = clean[prompt_offset, protocol.EDIT_LAYER - 45]
        clean_rms = _rms(clean_source)
        for pair_offset in range(15):
            direction = protocol.DIRECTIONS[pair_offset // len(protocol.DOSE_GRID)]
            dose = protocol.DOSE_GRID[pair_offset % len(protocol.DOSE_GRID)]
            expected_pair = {
                "prompt_id": prompt_id,
                "edit_layer": protocol.EDIT_LAYER,
                "direction": direction,
                "dose_fraction": dose,
                "target_prompt_used": False,
                "target_feature_used": False,
                "pair_row": pair_offset,
                "plus_trace_row": pair_offset * 2,
                "minus_trace_row": pair_offset * 2 + 1,
                "residual_shard": f"residuals/{prompt_id}.safetensors",
                "arithmetic_shard": f"arithmetic/{prompt_id}.safetensors",
            }
            if pair_rows[raw_cursor] != expected_pair:
                raise CalibrationAuditError("pair metadata/order differs")
            plus = arcs[pair_offset * 2]
            minus = arcs[pair_offset * 2 + 1]
            requested_fp32 = arithmetic["requested_fp32"][pair_offset]
            requested = arithmetic["requested_bfloat16"][pair_offset]
            pre_plus = plus[protocol.EDIT_LAYER - 45]
            pre_minus = minus[protocol.EDIT_LAYER - 45]
            post_plus = plus[-2]
            post_minus = minus[-2]
            realized_plus = post_plus.float() - pre_plus.float()
            realized_minus = post_minus.float() - pre_minus.float()
            realized = (post_plus.float() - post_minus.float()) * 0.5
            common = (
                post_plus.float() + post_minus.float()
            ) * 0.5 - clean_source.float()
            final = (plus[-1].float() - minus[-1].float()) * 0.5
            for name, expected in (
                ("realized_plus_fp32", realized_plus),
                ("realized_minus_fp32", realized_minus),
                ("realized_central_fp32", realized),
                ("common_mode_fp32", common),
                ("final_central_fp32", final),
            ):
                if not torch.equal(arithmetic[name][pair_offset], expected):
                    raise CalibrationAuditError(
                        f"archived arithmetic differs: {prompt_id}/{pair_offset}/{name}"
                    )
            if not torch.equal(requested, requested_fp32.to(dtype=torch.bfloat16)):
                raise CalibrationAuditError("requested FP32/BF16 cast differs")
            pre_equals_clean_plus = torch.equal(pre_plus, clean_source)
            pre_equals_clean_minus = torch.equal(pre_minus, clean_source)
            native_post_exact_plus = torch.equal(
                post_plus, (pre_plus + requested).to(torch.bfloat16)
            )
            native_post_exact_minus = torch.equal(
                post_minus, (pre_minus - requested).to(torch.bfloat16)
            )
            upstream_plus = all(
                torch.equal(plus[layer - 45], clean[prompt_offset, layer - 45])
                for layer in range(45, 50)
            )
            upstream_minus = all(
                torch.equal(minus[layer - 45], clean[prompt_offset, layer - 45])
                for layer in range(45, 50)
            )
            row = realization_rows[raw_cursor]
            expected_identity = (prompt_id, direction, dose)
            if (
                row["prompt_id"],
                row["direction"],
                row["dose_fraction"],
            ) != expected_identity:
                raise CalibrationAuditError("realization row identity differs")
            metrics = {
                "requested_plus_realized_relative_rmse": _relative_rmse(
                    realized_plus, requested
                ),
                "requested_minus_realized_relative_rmse": _relative_rmse(
                    realized_minus, -requested
                ),
                "requested_realized_central_relative_rmse": _relative_rmse(
                    realized, requested
                ),
                "requested_plus_realized_cosine": _cosine(realized_plus, requested),
                "requested_minus_realized_cosine": _cosine(realized_minus, -requested),
                "requested_realized_central_cosine": _cosine(realized, requested),
                "fp32_requested_to_bf16_relative_rmse": _relative_rmse(
                    requested, requested_fp32
                ),
                "fp32_requested_to_bf16_cosine": _cosine(requested, requested_fp32),
                "native_central_to_fp32_requested_relative_rmse": _relative_rmse(
                    realized, requested_fp32
                ),
                "native_central_to_fp32_requested_cosine": _cosine(
                    realized, requested_fp32
                ),
                "common_mode_to_central_rms": _safe_ratio(_rms(common), _rms(realized)),
                "requested_rms_fraction": _rms(requested) / clean_rms,
                "realized_rms_fraction": _rms(realized) / clean_rms,
                "bf16_fp32_j_cosine": _cosine(
                    arithmetic["j_prediction_bfloat16"][pair_offset],
                    arithmetic["j_prediction_fp32"][pair_offset],
                ),
                "bf16_fp32_j_relative_rmse": _relative_rmse(
                    arithmetic["j_prediction_bfloat16"][pair_offset],
                    arithmetic["j_prediction_fp32"][pair_offset],
                ),
                "fp32_j_actual_final_cosine": _cosine(
                    final, arithmetic["j_prediction_fp32"][pair_offset]
                ),
            }
            for name, value in metrics.items():
                _near(row[name], value, f"{expected_identity}.{name}")
            if (
                row.get("edit_layer") != protocol.EDIT_LAYER
                or row.get("target_prompt_used") is not False
                or row.get("target_feature_used") is not False
                or row.get("hook_fire_count_plus") != 1
                or row.get("hook_fire_count_minus") != 1
                or row.get("pre_equals_clean_plus") is not pre_equals_clean_plus
                or row.get("pre_equals_clean_minus") is not pre_equals_clean_minus
                or row.get("native_post_bytes_exact_plus") is not native_post_exact_plus
                or row.get("native_post_bytes_exact_minus")
                is not native_post_exact_minus
                or row.get("edit_finite") is not True
                or row.get("j_shadow_finite") is not True
                or row["pre_injection_45_49_exact_plus"] is not upstream_plus
                or row["pre_injection_45_49_exact_minus"] is not upstream_minus
                or row["finite"] is not True
            ):
                raise CalibrationAuditError("hard edit telemetry differs")
            expected_hashes = {
                "requested_vector_sha256": _tensor_sha256(requested),
                "realized_central_sha256": _tensor_sha256(realized),
                "realized_central_source_sha256": _tensor_sha256(realized),
                "bf16_j_prediction_sha256": _tensor_sha256(
                    arithmetic["j_prediction_bfloat16"][pair_offset]
                ),
                "fp32_j_prediction_sha256": _tensor_sha256(
                    arithmetic["j_prediction_fp32"][pair_offset]
                ),
            }
            if any(row.get(name) != value for name, value in expected_hashes.items()):
                raise CalibrationAuditError("realization tensor-hash telemetry differs")
            recomputed_realization.append(
                {
                    "prompt_id": prompt_id,
                    "direction": direction,
                    "dose_fraction": dose,
                    **metrics,
                    "hard_safety_pass": bool(
                        pre_equals_clean_plus
                        and pre_equals_clean_minus
                        and native_post_exact_plus
                        and native_post_exact_minus
                        and upstream_plus
                        and upstream_minus
                    ),
                }
            )
            linearity_inputs[(prompt_id, direction)][dose] = (
                realized,
                arithmetic["j_prediction_fp32"][pair_offset],
                final,
                metrics["requested_rms_fraction"],
                metrics["realized_rms_fraction"],
            )

            if dose == protocol.PRIMARY_DOSE:
                readout_index = protocol.DIRECTIONS.index(direction)
                actual_logits = readout["actual_selected_logit_delta_fp32"][
                    readout_index
                ]
                if not torch.isfinite(actual_logits).all():
                    raise CalibrationAuditError(
                        "actual selected-logit delta is non-finite"
                    )
                for layer_offset, layer in enumerate(protocol.READOUT_LAYERS):
                    if layer == protocol.EDIT_LAYER:
                        source_delta = realized
                    else:
                        source_delta = (
                            plus[layer - 45].float() - minus[layer - 45].float()
                        ) * 0.5
                    if not torch.equal(
                        readout["source_delta_fp32"][readout_index, layer_offset],
                        source_delta,
                    ):
                        raise CalibrationAuditError(
                            "readout source delta differs from signed arcs"
                        )
                    for transport_offset, transport_name in enumerate(
                        protocol.TRANSPORTS
                    ):
                        prediction = readout["transport_prediction_bfloat16"][
                            readout_index, layer_offset, transport_offset
                        ]
                        predicted_logits = readout[
                            "transport_selected_logit_delta_fp32"
                        ][readout_index, layer_offset, transport_offset]
                        residual_cosine = _cosine(final, prediction)
                        logit_pearson = _pearson(actual_logits, predicted_logits)
                        row_t = readout_rows[readout_cursor]
                        identity_t = (
                            row_t["prompt_id"],
                            row_t["direction"],
                            row_t["dose_fraction"],
                            row_t["readout_layer"],
                            row_t["transport"],
                        )
                        if identity_t != (
                            prompt_id,
                            direction,
                            dose,
                            layer,
                            transport_name,
                        ):
                            raise CalibrationAuditError(
                                "readout transport row order differs"
                            )
                        if (
                            row_t.get("edit_layer") != protocol.EDIT_LAYER
                            or row_t.get("target_prompt_used") is not False
                            or row_t.get("target_feature_used") is not False
                            or row_t.get("finite") is not True
                            or row_t.get("predicted_logit_center")
                            != "signed_final_midpoint"
                            or row_t.get("predicted_central_final_sha256")
                            != _tensor_sha256(prediction)
                            or row_t.get("actual_central_final_sha256")
                            != _tensor_sha256(final)
                        ):
                            raise CalibrationAuditError(
                                "readout transport provenance telemetry differs"
                            )
                        _near(
                            row_t["residual_delta_cosine"],
                            residual_cosine,
                            f"{identity_t}.residual",
                        )
                        _near(
                            row_t["fixed_token_logit_delta_pearson"],
                            logit_pearson,
                            f"{identity_t}.logit",
                        )
                        transport_recomputed.append(
                            {
                                "prompt_id": prompt_id,
                                "direction": direction,
                                "dose_fraction": dose,
                                "readout_layer": layer,
                                "transport": transport_name,
                                "residual_delta_cosine": residual_cosine,
                                "fixed_token_logit_delta_pearson": logit_pearson,
                            }
                        )
                        readout_cursor += 1
            raw_cursor += 1
    if raw_cursor != 120 or readout_cursor != 4872:
        raise CalibrationAuditError("raw recomputation cursor differs")

    watchdog.check()
    artifact_recomputation = _audit_artifact_recomputation(
        run_root=root,
        prompt_data=artifact_prompt_data,
        selected_ids=selected_ids,
        plan_hash=supplied_plan_hash,
        model_snapshot=model_snapshot,
        j_lens_path=j_lens_path,
        device_name=artifact_device,
        watchdog=watchdog,
    )
    if Path(binding_hashes["bound_j_lens_path"]).resolve(strict=True) != Path(
        artifact_recomputation["j_lens"]["path"]
    ).resolve(strict=True):
        raise CalibrationAuditError(
            "audited J-lens path differs from execution binding"
        )
    if (
        binding_hashes["j_orientation_status"]
        != artifact_recomputation["orientation_status"]
    ):
        raise CalibrationAuditError(
            "audited J orientation status differs from runtime metadata"
        )
    watchdog.check()

    gate_doses = set(protocol.REALIZATION_GATE_DOSES)
    diagnostic_doses = set(protocol.DIAGNOSTIC_DOSES)
    hard_safety_failures = []
    realization_failures = []
    j_shadow_failures = []
    diagnostic_failures = []
    diagnostic_j_shadow_failures = []
    dose_summaries: dict[str, Any] = {}
    for dose in protocol.DOSE_GRID:
        selected = [
            row for row in recomputed_realization if row["dose_fraction"] == dose
        ]
        row_failures = []
        row_hard_failures = []
        row_delivery_failures = []
        row_j_shadow_failures = []
        for row in selected:
            hard_failed = _hard_safety_failed(row)
            delivery_failed = _delivery_gate_failed(row)
            j_shadow_failed = _j_shadow_gate_failed(row)
            if hard_failed or delivery_failed:
                row_failures.append((row["prompt_id"], row["direction"]))
            if hard_failed:
                row_hard_failures.append((row["prompt_id"], row["direction"]))
                hard_safety_failures.append((dose, row["prompt_id"], row["direction"]))
            if delivery_failed:
                row_delivery_failures.append((row["prompt_id"], row["direction"]))
            if j_shadow_failed:
                row_j_shadow_failures.append((row["prompt_id"], row["direction"]))
        if dose in gate_doses:
            realization_failures.extend(
                (dose, *value) for value in row_delivery_failures
            )
            j_shadow_failures.extend((dose, *value) for value in row_j_shadow_failures)
        elif dose in diagnostic_doses:
            diagnostic_failures.extend(
                (dose, *value) for value in row_delivery_failures
            )
            diagnostic_j_shadow_failures.extend(
                (dose, *value) for value in row_j_shadow_failures
            )
        dose_summaries[str(dose)] = {
            "role": (
                "universal_hard_safety_and_requested_delivery_gate"
                if dose in gate_doses
                else "universal_hard_safety_and_requested_delivery_diagnostic"
            ),
            "row_count": len(selected),
            "failure_count": len(row_failures),
            "hard_safety_failure_count": len(row_hard_failures),
            "requested_delivery_failure_count": len(row_delivery_failures),
            "edit_integrity_failure_count": len(row_failures),
            "j_shadow_failure_count": len(row_j_shadow_failures),
            "signed_requested_realized_relative_rmse": {
                component: {
                    "min": min(row[field] for row in selected),
                    "median": float(np.median([row[field] for row in selected])),
                    "max": max(row[field] for row in selected),
                }
                for component, field in (
                    ("plus", "requested_plus_realized_relative_rmse"),
                    ("minus", "requested_minus_realized_relative_rmse"),
                    ("central", "requested_realized_central_relative_rmse"),
                )
            },
            "requested_realized_relative_rmse": {
                "min": min(
                    row["requested_realized_central_relative_rmse"] for row in selected
                ),
                "median": float(
                    np.median(
                        [
                            row["requested_realized_central_relative_rmse"]
                            for row in selected
                        ]
                    )
                ),
                "max": max(
                    row["requested_realized_central_relative_rmse"] for row in selected
                ),
            },
            "requested_realized_cosine": {
                "min": min(
                    row["requested_realized_central_cosine"] for row in selected
                ),
                "median": float(
                    np.median(
                        [row["requested_realized_central_cosine"] for row in selected]
                    )
                ),
                "max": max(
                    row["requested_realized_central_cosine"] for row in selected
                ),
            },
            "signed_requested_realized_cosine": {
                component: {
                    "min": min(row[field] for row in selected),
                    "median": float(np.median([row[field] for row in selected])),
                    "max": max(row[field] for row in selected),
                }
                for component, field in (
                    ("plus", "requested_plus_realized_cosine"),
                    ("minus", "requested_minus_realized_cosine"),
                    ("central", "requested_realized_central_cosine"),
                )
            },
            "common_mode_to_central_rms": {
                "min": min(row["common_mode_to_central_rms"] for row in selected),
                "median": float(
                    np.median([row["common_mode_to_central_rms"] for row in selected])
                ),
                "max": max(row["common_mode_to_central_rms"] for row in selected),
            },
            "bf16_fp32_j_cosine": {
                "min": min(row["bf16_fp32_j_cosine"] for row in selected),
                "median": float(
                    np.median([row["bf16_fp32_j_cosine"] for row in selected])
                ),
                "max": max(row["bf16_fp32_j_cosine"] for row in selected),
            },
        }

    linearity_rows, component_failures = _linearity_summary(linearity_inputs)

    claim_statuses = _separated_claim_statuses(
        edit_failure_count=len(hard_safety_failures) + len(realization_failures),
        j_shadow_failure_count=len(j_shadow_failures),
        component_failures=component_failures,
        orientation_status=str(artifact_recomputation["orientation_status"]),
    )
    transport_summary = _transport_summary(
        transport_recomputed,
        j_projection_eligible=(
            claim_statuses["j_projection_claim_eligibility"] == "pass"
        ),
    )
    collection_eligibility = claim_statuses["later_actual_state_collection_eligibility"]
    watchdog.check()
    audit_metrics_sealed_at_unix = time.time()

    audit_core = {
        "schema_version": 1,
        "status": "pass",
        "study_id": protocol.STUDY_ID,
        "protocol_version": protocol.PROTOCOL_VERSION,
        "run_id": complete["run_id"],
        "plan_manifest_sha256": complete["plan_manifest_sha256"],
        "raw_run_receipt_sha256": complete["receipt_sha256"],
        "raw_file_count": len(complete["records"]),
        "raw_stored_bytes": complete["stored_bytes"],
        "audit_started_at_unix": audit_started_at_unix,
        "audit_metrics_sealed_at_unix": audit_metrics_sealed_at_unix,
        "campaign_started_at_unix": binding_hashes["campaign_started_at_unix"],
        "campaign_deadline_at_unix": binding_hashes["campaign_deadline_at_unix"],
        "hourly_price_usd": binding_hashes["hourly_price_usd"],
        "recomputed_realization_row_count": len(recomputed_realization),
        "recomputed_readout_transport_row_count": len(transport_recomputed),
        "recomputed_linearity_row_count": len(linearity_rows),
        "independent_plan_audit_receipt_sha256": plan_audit_receipt["receipt_sha256"],
        "execution_receipt_bindings": {
            key: value
            for key, value in binding_hashes.items()
            if key.endswith("receipt_sha256")
        },
        "external_receipt_validation": external_receipt_validation,
        "artifact_recomputation": artifact_recomputation,
        "target_prompt_render_count": 0,
        "target_feature_vector_count": 0,
        "analysis_data_inputs": [],
    }
    audit_receipt = {
        **audit_core,
        "receipt_sha256": protocol.canonical_sha256(audit_core),
    }
    summary_core = {
        "schema_version": 1,
        "status": collection_eligibility,
        "study_id": protocol.STUDY_ID,
        "protocol_version": protocol.PROTOCOL_VERSION,
        "run_id": complete["run_id"],
        "raw_run_receipt_sha256": complete["receipt_sha256"],
        "audit_receipt_sha256": audit_receipt["receipt_sha256"],
        **claim_statuses,
        "hard_safety_failure_count_all_doses": len(hard_safety_failures),
        "realization_gate_failure_count": len(realization_failures),
        "diagnostic_one_percent_failure_count": len(diagnostic_failures),
        "j_shadow_gate_failure_count": len(j_shadow_failures),
        "diagnostic_one_percent_j_shadow_failure_count": len(
            diagnostic_j_shadow_failures
        ),
        "linearity_failure_counts": component_failures,
        "by_dose": dose_summaries,
        "linearity_rows": linearity_rows,
        "readout_transport": transport_summary,
        "claim_policy": {
            "downstream_nonlinearity_blocks_collection": False,
            "realized_source_linearity_failure_blocks_collection": False,
            "j_projection_failure_blocks_actual_state_collection": False,
            "j_over_identity_failure_blocks_actual_state_contrasts": False,
            "j_over_identity_failure_blocks_learned_j_added_value_claim": True,
            "target_or_semantic_claim_permitted": False,
        },
        "adaptive_design_inputs": protocol.ADAPTIVE_DESIGN_INPUTS,
        "analysis_data_inputs": [],
        "target_prompt_render_count": 0,
        "target_feature_vector_count": 0,
    }
    summary = {
        **summary_core,
        "receipt_sha256": protocol.canonical_sha256(summary_core),
    }
    return audit_receipt, summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--plan-dir", type=Path, required=True)
    parser.add_argument("--model-snapshot", type=Path, required=True)
    parser.add_argument("--j-lens-path", type=Path, required=True)
    parser.add_argument("--ownership-receipt", type=Path, required=True)
    parser.add_argument("--guest-receipt", type=Path, required=True)
    parser.add_argument("--cache-receipt", type=Path, required=True)
    parser.add_argument("--authorization-receipt", type=Path, required=True)
    parser.add_argument("--artifact-device", default="cuda:0")
    parser.add_argument("--audit-out", type=Path, required=True)
    parser.add_argument("--summary-out", type=Path, required=True)
    args = parser.parse_args()
    audit_receipt, summary = audit(
        args.run_root,
        args.plan_dir,
        model_snapshot=args.model_snapshot,
        j_lens_path=args.j_lens_path,
        ownership_receipt=args.ownership_receipt,
        guest_receipt=args.guest_receipt,
        cache_receipt=args.cache_receipt,
        authorization_receipt=args.authorization_receipt,
        artifact_device=args.artifact_device,
    )
    published_summary = _publish_pair_atomic(
        args.audit_out,
        args.summary_out,
        audit_receipt,
        summary,
    )
    print(published_summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

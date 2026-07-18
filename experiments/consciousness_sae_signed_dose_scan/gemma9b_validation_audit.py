#!/usr/bin/env python3
"""Independent audit of the operational-only Gemma signed dose-grid run.

The auditor intentionally restates the frozen Gemma contract instead of
importing the runner.  Promotion is limited to four mechanics gates:
structure, finite/nondegenerate numerics, exact single-use hook behavior, and
independent artifact replay.  Semantic outcomes, effect size, preferred doses,
and learned-J behavior are neither read nor eligible to affect promotion.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


AUDIT_SCHEMA_VERSION = 1
EXPECTED_VALIDATION_SCHEMA_VERSION = 1
EXPECTED_VALIDATION_ID = "gemma2_9b_signed_dose_grid_operational_v1"
EXPECTED_VALIDATION_ROLE = "operational_only_smaller_model_validation"
EXPECTED_PROTOCOL_ID = "consciousness_sae_signed_dose_scan_v1"
EXPECTED_PROTOCOL_VERSION = "consciousness_sae_signed_dose_scan_v1.0.0"
EXPECTED_MODEL_ID = "google/gemma-2-9b-it"
EXPECTED_MODEL_REVISION = "11c9b309abf73637e4b6f9a3fa1e92e615547819"
EXPECTED_SAE_REPO = "google/gemma-scope-9b-it-res"
EXPECTED_SAE_REVISION = "e86af97a5b6fbbccca28ab654f2fda1b0768f770"
EXPECTED_SAE_FOLDER = "layer_20/width_16k/average_l0_91"
EXPECTED_SAE_PARAMS_SHA256 = (
    "bbd770b6f8b92a2fe7498e05bd6274c6cfa89ebc08fb972c0e842840737f1a82"
)
EXPECTED_FEATURE_ID = 1_295
EXPECTED_EDIT_LAYER = 20
EXPECTED_RESIDUAL_WIDTH = 3_584
EXPECTED_SAE_WIDTH = 16_384
EXPECTED_CAPTURE_LAYERS = tuple(range(42))
EXPECTED_ARC_LABELS = tuple(
    f"layer_{layer:02d}_post" for layer in EXPECTED_CAPTURE_LAYERS
) + ("final_norm_input",)
EXPECTED_ARC_COUNT = len(EXPECTED_ARC_LABELS)
EXPECTED_DOSES = tuple(range(50, 3_001, 50))
EXPECTED_SIGNS = ("plus", "minus")
EXPECTED_ROWS = 120
EXPECTED_PAIRS = 60
EXPECTED_MODEL_FORWARDS = 122
EXPECTED_REMOTE_ROOT = "/workspace"
EXPECTED_PROMPT_ID = "neutral_calendar_continuation_v1"
EXPECTED_PROMPT = (
    "Continue this neutral sequence with a short factual sentence: "
    "January, February, March."
)
EXPECTED_GATES = ("structural", "numeric", "hook", "artifact_replay")

EXPECTED_FILES = {
    "RUN_MANIFEST.json",
    "dose_grid.safetensors",
    "rows.jsonl",
    "pairs.jsonl",
}
OPTIONAL_AUDIT_FILES = {"AUDIT.json"}

EXPECTED_TENSORS = {
    "clean_arc_bfloat16": ((EXPECTED_ARC_COUNT, EXPECTED_RESIDUAL_WIDTH), "bfloat16"),
    "decoder_row_bfloat16": ((EXPECTED_RESIDUAL_WIDTH,), "bfloat16"),
    "unit_direction_float32": ((EXPECTED_RESIDUAL_WIDTH,), "float32"),
    "requested_positive_float32": (
        (EXPECTED_PAIRS, EXPECTED_RESIDUAL_WIDTH),
        "float32",
    ),
    "requested_positive_bfloat16": (
        (EXPECTED_PAIRS, EXPECTED_RESIDUAL_WIDTH),
        "bfloat16",
    ),
    "plus_arc_bfloat16": (
        (EXPECTED_PAIRS, EXPECTED_ARC_COUNT, EXPECTED_RESIDUAL_WIDTH),
        "bfloat16",
    ),
    "minus_arc_bfloat16": (
        (EXPECTED_PAIRS, EXPECTED_ARC_COUNT, EXPECTED_RESIDUAL_WIDTH),
        "bfloat16",
    ),
    "plus_pre_bfloat16": (
        (EXPECTED_PAIRS, EXPECTED_RESIDUAL_WIDTH),
        "bfloat16",
    ),
    "plus_post_bfloat16": (
        (EXPECTED_PAIRS, EXPECTED_RESIDUAL_WIDTH),
        "bfloat16",
    ),
    "minus_pre_bfloat16": (
        (EXPECTED_PAIRS, EXPECTED_RESIDUAL_WIDTH),
        "bfloat16",
    ),
    "minus_post_bfloat16": (
        (EXPECTED_PAIRS, EXPECTED_RESIDUAL_WIDTH),
        "bfloat16",
    ),
    "plus_hook_vector_bfloat16": (
        (EXPECTED_PAIRS, EXPECTED_RESIDUAL_WIDTH),
        "bfloat16",
    ),
    "minus_hook_vector_bfloat16": (
        (EXPECTED_PAIRS, EXPECTED_RESIDUAL_WIDTH),
        "bfloat16",
    ),
}

EXPECTED_ROW_FIELDS = {
    "row_index",
    "dose_index",
    "dose_basis_points",
    "signed_dose_basis_points",
    "sign",
    "forward_id",
    "hook_fire_count",
    "pre_equals_clean",
    "upstream_arc_equals_clean",
    "native_post_bytes_exact",
    "requested_vector_sha256",
    "hook_vector_sha256",
    "pre_sha256",
    "post_sha256",
    "arc_sha256",
    "requested_rms_fraction",
    "realized_rms_fraction",
    "realized_vs_requested_relative_rmse",
    "realized_vs_requested_cosine",
    "finite",
    "semantic_outcome_count",
}

EXPECTED_PAIR_FIELDS = {
    "pair_index",
    "dose_basis_points",
    "plus_row_index",
    "minus_row_index",
    "requested_positive_sha256",
    "realized_central_sha256",
    "common_mode_sha256",
    "central_rms_fraction",
    "central_vs_requested_relative_rmse",
    "central_vs_requested_cosine",
    "common_mode_to_central_rms",
    "finite",
    "semantic_outcome_count",
}


class AuditError(RuntimeError):
    """Independent audit rejection."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


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


def sha256_file(path: Path, *, chunk_bytes: int = 8 * 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(chunk_bytes):
            digest.update(chunk)
    return digest.hexdigest()


def _json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AuditError(f"invalid JSON artifact: {path}") from exc
    if not isinstance(value, dict):
        raise AuditError(f"JSON artifact is not an object: {path}")
    return value


def _jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    try:
        with path.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, 1):
                if not line.strip():
                    raise AuditError(f"blank JSONL row at {path}:{line_number}")
                value = json.loads(line)
                if not isinstance(value, dict):
                    raise AuditError(f"non-object JSONL row at {path}:{line_number}")
                rows.append(value)
    except (OSError, json.JSONDecodeError) as exc:
        raise AuditError(f"invalid JSONL artifact: {path}") from exc
    return rows


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise AuditError(message)


def _finite_json(value: Any) -> bool:
    if value is None or isinstance(value, (str, bool, int)):
        return True
    if isinstance(value, float):
        return math.isfinite(value)
    if isinstance(value, list):
        return all(_finite_json(child) for child in value)
    if isinstance(value, dict):
        return all(_finite_json(child) for child in value.values())
    return False


def _rms(value: Any) -> float:
    result = float(value.detach().float().square().mean().sqrt().item())
    if not math.isfinite(result):
        raise AuditError("replayed tensor RMS is non-finite")
    return result


def _relative_rmse(observed: Any, expected: Any) -> float:
    left = observed.detach().float().reshape(-1)
    right = expected.detach().float().reshape(-1)
    if left.shape != right.shape or not left.numel():
        raise AuditError("replayed relative-RMSE shapes differ")
    denominator = right.square().mean().sqrt()
    if float(denominator.item()) <= 0.0:
        raise AuditError("replayed relative-RMSE reference is zero")
    result = float(((left - right).square().mean().sqrt() / denominator).item())
    if not math.isfinite(result):
        raise AuditError("replayed relative RMSE is non-finite")
    return result


def _cosine_or_none(left: Any, right: Any) -> float | None:
    first = left.detach().float().reshape(-1)
    second = right.detach().float().reshape(-1)
    denominator = first.norm() * second.norm()
    if float(denominator.item()) <= 0.0:
        return None
    result = float(first.dot(second).item() / denominator.item())
    if not math.isfinite(result):
        raise AuditError("replayed cosine is non-finite")
    return max(-1.0, min(1.0, result))


def _tensor_sha256(value: Any) -> str:
    cpu = value.detach().contiguous().to(device="cpu")
    digest = hashlib.sha256()
    digest.update(
        canonical_json_bytes({"dtype": str(cpu.dtype), "shape": list(cpu.shape)})
    )
    digest.update(b"\0")
    raw = cpu.view(_torch().uint8).reshape(-1)
    for start in range(0, int(raw.numel()), 8 * 1024 * 1024):
        digest.update(raw[start : start + 8 * 1024 * 1024].numpy().tobytes())
    return digest.hexdigest()


def _torch() -> Any:
    try:
        import torch
    except ImportError as exc:  # pragma: no cover - audit environment only
        raise AuditError("torch is required for the Gemma artifact audit") from exc
    return torch


def _load_tensors(path: Path) -> dict[str, Any]:
    try:
        from safetensors.torch import load_file
    except ImportError as exc:  # pragma: no cover - audit environment only
        raise AuditError("safetensors is required for the Gemma artifact audit") from exc
    return dict(load_file(str(path), device="cpu"))


def _decoder_row_from_npz(params_path: Path) -> Any:
    try:
        import numpy as np
    except ImportError as exc:  # pragma: no cover - audit environment only
        raise AuditError("numpy is required for SAE decoder-row audit") from exc
    torch = _torch()
    try:
        with np.load(params_path) as data:
            key = "w_dec" if "w_dec" in data.files else "W_dec"
            if key not in data.files:
                raise AuditError("cached SAE NPZ has no decoder matrix")
            decoder = data[key]
            _require(
                tuple(decoder.shape)
                == (EXPECTED_SAE_WIDTH, EXPECTED_RESIDUAL_WIDTH),
                "cached SAE decoder matrix shape differs",
            )
            row = np.array(decoder[EXPECTED_FEATURE_ID], dtype=np.float32, copy=True)
    except OSError as exc:
        raise AuditError("cached SAE NPZ is unreadable") from exc
    result = torch.from_numpy(row).to(torch.bfloat16).contiguous()
    _require(bool(torch.isfinite(result).all()), "cached SAE decoder row is non-finite")
    return result


def _close_float(observed: Any, expected: float) -> bool:
    return (
        not isinstance(observed, bool)
        and isinstance(observed, (int, float))
        and math.isclose(float(observed), float(expected), rel_tol=2e-5, abs_tol=2e-7)
    )


def _same_optional_float(observed: Any, expected: float | None) -> bool:
    if expected is None:
        return observed is None
    return _close_float(observed, expected)


@dataclass(frozen=True)
class AuditContext:
    run_dir: Path
    manifest: Mapping[str, Any]
    rows: Sequence[Mapping[str, Any]]
    pairs: Sequence[Mapping[str, Any]]
    tensors: Mapping[str, Any]


def structural_gate(run_dir: Path) -> tuple[AuditContext, dict[str, Any]]:
    torch = _torch()
    observed_files = {path.name for path in run_dir.iterdir() if path.is_file()}
    _require(
        EXPECTED_FILES <= observed_files,
        f"required artifact inventory differs: {sorted(observed_files)}",
    )
    _require(
        observed_files <= EXPECTED_FILES | OPTIONAL_AUDIT_FILES,
        f"unexpected artifact file present: {sorted(observed_files - EXPECTED_FILES)}",
    )
    _require("RUN_FAILED.json" not in observed_files, "failed run cannot be promoted")
    manifest = _json(run_dir / "RUN_MANIFEST.json")
    rows = _jsonl(run_dir / "rows.jsonl")
    pairs = _jsonl(run_dir / "pairs.jsonl")
    tensors = _load_tensors(run_dir / "dose_grid.safetensors")
    _require(_finite_json(manifest), "manifest contains non-finite JSON")
    _require(all(_finite_json(row) for row in rows), "rows contain non-finite JSON")
    _require(all(_finite_json(pair) for pair in pairs), "pairs contain non-finite JSON")

    _require(
        manifest.get("schema_version") == EXPECTED_VALIDATION_SCHEMA_VERSION,
        "validation schema differs",
    )
    _require(manifest.get("validation_id") == EXPECTED_VALIDATION_ID, "validation ID differs")
    _require(
        manifest.get("validation_role") == EXPECTED_VALIDATION_ROLE,
        "validation role differs",
    )
    _require(
        manifest.get("status") == "complete_awaiting_independent_audit",
        "run is not complete",
    )
    scope = manifest.get("scope", {})
    expected_scope = {
        "operational_only": True,
        "smaller_model": True,
        "scientific_claims_authorized": False,
        "semantic_outcomes_collected": False,
        "target_sae_features_used": False,
        "learned_j_used": False,
        "dose_selection_or_threshold_tuning": False,
    }
    _require(scope == expected_scope, "operational-only scope contract differs")

    source = manifest.get("source_protocol", {})
    protocol_path = Path(__file__).with_name("protocol.py")
    _require(source.get("study_id") == EXPECTED_PROTOCOL_ID, "source protocol ID differs")
    _require(
        source.get("protocol_version") == EXPECTED_PROTOCOL_VERSION,
        "source protocol version differs",
    )
    _require(
        source.get("status") == "prospectively_frozen_exploratory_plan"
        and source.get("used_as") == "grid_and_zero-contract_reference_only",
        "source protocol authorization boundary differs",
    )
    _require(
        source.get("source_sha256") == sha256_file(protocol_path),
        "source protocol file hash differs",
    )

    model = manifest.get("model", {})
    _require(
        model
        == {
            "id": EXPECTED_MODEL_ID,
            "revision": EXPECTED_MODEL_REVISION,
            "residual_width": EXPECTED_RESIDUAL_WIDTH,
            "layers": len(EXPECTED_CAPTURE_LAYERS),
            "dtype": "bfloat16",
        },
        "Gemma model identity differs",
    )
    sae = manifest.get("sae", {})
    _require(sae.get("repo") == EXPECTED_SAE_REPO, "SAE repository differs")
    _require(sae.get("revision") == EXPECTED_SAE_REVISION, "SAE revision differs")
    _require(sae.get("folder") == EXPECTED_SAE_FOLDER, "SAE folder differs")
    _require(sae.get("params_sha256") == EXPECTED_SAE_PARAMS_SHA256, "SAE bytes differ")
    _require(sae.get("d_in") == EXPECTED_RESIDUAL_WIDTH, "SAE input width differs")
    _require(sae.get("d_sae") == EXPECTED_SAE_WIDTH, "SAE latent width differs")
    _require(sae.get("dtype") == "bfloat16", "SAE dtype differs")
    _require(sae.get("layer") == EXPECTED_EDIT_LAYER, "SAE layer differs")
    _require(sae.get("width") == EXPECTED_SAE_WIDTH, "SAE width binding differs")
    _require(sae.get("feature_id") == EXPECTED_FEATURE_ID, "SAE decoder row differs")
    _require(
        sae.get("direction_role")
        == "frozen_actual_public_sae_decoder_row_no_semantic_label",
        "decoder direction role differs",
    )
    params_path_value = sae.get("params_path")
    _require(
        isinstance(params_path_value, str) and Path(params_path_value).is_absolute(),
        "SAE parameter path is not absolute",
    )
    params_path = Path(params_path_value)
    _require(params_path.is_file(), "cached SAE parameter file is missing")
    _require(
        sha256_file(params_path) == EXPECTED_SAE_PARAMS_SHA256,
        "cached SAE parameter file bytes differ",
    )

    prompt = manifest.get("prompt", {})
    _require(prompt.get("prompt_id") == EXPECTED_PROMPT_ID, "prompt ID differs")
    _require(prompt.get("text") == EXPECTED_PROMPT, "frozen neutral prompt differs")
    _require(
        prompt.get("text_sha256") == hashlib.sha256(EXPECTED_PROMPT.encode()).hexdigest(),
        "prompt text hash differs",
    )
    token_ids = prompt.get("token_ids")
    _require(
        isinstance(token_ids, list)
        and len(token_ids) >= 2
        and all(isinstance(value, int) and not isinstance(value, bool) and value >= 0 for value in token_ids),
        "rendered prompt token IDs are malformed",
    )
    _require(
        prompt.get("token_ids_sha256") == canonical_sha256(token_ids),
        "rendered prompt token hash differs",
    )

    intervention = manifest.get("intervention", {})
    _require(intervention.get("edit_layer") == EXPECTED_EDIT_LAYER, "edit layer differs")
    _require(
        intervention.get("dose_basis_points") == list(EXPECTED_DOSES),
        "dose magnitude grid differs",
    )
    _require(
        intervention.get("signed_branches") == list(EXPECTED_SIGNS),
        "signed branch inventory differs",
    )
    _require(
        intervention.get("zero")
        == {
            "dose_basis_points": 0,
            "execution": "one_clean_continuation_no_hook",
            "duplicate_zero_rows": 0,
            "hook_fire_count": 0,
        },
        "one-clean-zero contract differs",
    )
    _require(
        intervention.get("coordinate")
        == "integer_basis_points_of_clean_layer20_residual_rms",
        "dose coordinate differs",
    )
    _require(
        intervention.get("request_construction")
        == "cpu_fp32_unit_rms_decoder_row_times_clean_source_rms_times_bps_div_10000_then_bfloat16",
        "request construction differs",
    )

    capture = manifest.get("capture", {})
    _require(capture.get("layers") == list(EXPECTED_CAPTURE_LAYERS), "capture layers differ")
    _require(capture.get("arc_labels") == list(EXPECTED_ARC_LABELS), "full arc labels differ")
    _require(
        capture.get("arc_dtype") == "bfloat16"
        and capture.get("hook_pre_post_dtype") == "bfloat16"
        and capture.get("remote_only") is True,
        "BF16 remote capture contract differs",
    )
    _require(
        manifest.get("forward_inventory")
        == {
            "prefix_forwards": 1,
            "clean_zero_forwards": 1,
            "edited_forwards": EXPECTED_ROWS,
            "exact_total_model_forwards": EXPECTED_MODEL_FORWARDS,
        },
        "forward inventory differs",
    )
    promotion = manifest.get("promotion_contract", {})
    _require(promotion.get("required_gates") == list(EXPECTED_GATES), "promotion gates differ")
    _require(
        promotion.get("semantic_outcome_gate") is False
        and promotion.get("effect_size_gate") is False
        and promotion.get("dose_threshold_tuning_gate") is False
        and promotion.get("promotion_scope")
        == "runner_mechanics_only_not_scientific_protocol",
        "promotion boundary differs",
    )
    storage = manifest.get("storage", {})
    _require(
        storage
        == {
            "raw_location": "RunPod network volume only",
            "remote_root": EXPECTED_REMOTE_ROOT,
            "git_allowed": False,
            "raw_tensor_files": ["dose_grid.safetensors"],
        },
        "remote storage policy differs",
    )
    run_dir_attestation = manifest.get("run_dir")
    _require(
        isinstance(run_dir_attestation, str)
        and run_dir_attestation.startswith(EXPECTED_REMOTE_ROOT + "/"),
        "runtime output was not attested below the network-volume root",
    )
    runtime = manifest.get("runtime", {})
    _require(runtime.get("cuda_available") is True, "run was not CUDA-backed")
    determinism = manifest.get("determinism", {})
    _require(
        determinism.get("deterministic_algorithms") is True
        and determinism.get("cuda_matmul_tf32") is False
        and determinism.get("cudnn_tf32") is False
        and determinism.get("flash_sdp_enabled") is False
        and determinism.get("mem_efficient_sdp_enabled") is False
        and determinism.get("math_sdp_enabled") is True
        and determinism.get("cublas_workspace_config") == ":4096:8",
        "deterministic runtime settings differ",
    )

    artifacts = manifest.get("artifacts", {})
    _require(
        set(artifacts) == {"dose_grid.safetensors", "rows.jsonl", "pairs.jsonl"},
        "manifest artifact inventory differs",
    )
    for name, record in artifacts.items():
        path = run_dir / name
        _require(record.get("relative_path") == name, f"artifact path differs: {name}")
        _require(record.get("bytes") == path.stat().st_size, f"artifact size differs: {name}")
        _require(record.get("sha256") == sha256_file(path), f"artifact hash differs: {name}")

    _require(len(rows) == EXPECTED_ROWS, "signed row count differs")
    _require(len(pairs) == EXPECTED_PAIRS, "pair row count differs")
    _require(all(set(row) == EXPECTED_ROW_FIELDS for row in rows), "row field inventory differs")
    _require(all(set(pair) == EXPECTED_PAIR_FIELDS for pair in pairs), "pair field inventory differs")
    _require(
        all(row.get("semantic_outcome_count") == 0 for row in rows)
        and all(pair.get("semantic_outcome_count") == 0 for pair in pairs),
        "semantic outcomes entered the operational validation",
    )

    _require(set(tensors) == set(EXPECTED_TENSORS), "tensor inventory differs")
    dtype_map = {"bfloat16": torch.bfloat16, "float32": torch.float32}
    for name, (shape, dtype_name) in EXPECTED_TENSORS.items():
        value = tensors[name]
        _require(tuple(value.shape) == tuple(shape), f"tensor shape differs: {name}")
        _require(value.dtype == dtype_map[dtype_name], f"tensor dtype differs: {name}")
    _require(
        sae.get("decoder_row_sha256") == _tensor_sha256(tensors["decoder_row_bfloat16"]),
        "decoder-row hash differs",
    )
    _require(
        sae.get("unit_direction_sha256") == _tensor_sha256(tensors["unit_direction_float32"]),
        "unit-direction hash differs",
    )
    _require(
        _torch().equal(
            tensors["decoder_row_bfloat16"],
            _decoder_row_from_npz(params_path),
        ),
        "archived direction is not feature 1295 from the pinned SAE bytes",
    )
    return (
        AuditContext(
            run_dir=run_dir,
            manifest=manifest,
            rows=rows,
            pairs=pairs,
            tensors=tensors,
        ),
        {
            "files": len(observed_files),
            "signed_rows": len(rows),
            "pairs": len(pairs),
            "tensor_count": len(tensors),
            "raw_bytes": (run_dir / "dose_grid.safetensors").stat().st_size,
            "decoder_row_verified_against_cached_sae": True,
        },
    )


def numeric_gate(context: AuditContext) -> dict[str, Any]:
    torch = _torch()
    tensors = context.tensors
    for name, value in tensors.items():
        _require(bool(torch.isfinite(value).all()), f"non-finite tensor: {name}")
    decoder = tensors["decoder_row_bfloat16"].float()
    decoder_rms = _rms(decoder)
    _require(decoder_rms > 0.0, "decoder row has zero RMS")
    expected_unit = (decoder / decoder_rms).contiguous()
    _require(
        torch.equal(tensors["unit_direction_float32"], expected_unit),
        "unit direction is not the exact normalized decoder row",
    )
    _require(
        math.isclose(_rms(expected_unit), 1.0, rel_tol=2e-6, abs_tol=2e-6),
        "unit direction does not have unit RMS",
    )
    clean = tensors["clean_arc_bfloat16"]
    clean_rms = _rms(clean[EXPECTED_EDIT_LAYER])
    _require(clean_rms > 0.0, "clean edit-layer source has zero RMS")
    _require(
        _close_float(context.manifest["intervention"].get("clean_source_rms"), clean_rms),
        "manifest clean-source RMS differs",
    )
    expected_fp32 = torch.stack(
        [
            expected_unit * (clean_rms * dose_basis_points / 10_000.0)
            for dose_basis_points in EXPECTED_DOSES
        ]
    ).to(torch.float32).contiguous()
    _require(
        torch.equal(tensors["requested_positive_float32"], expected_fp32),
        "FP32 requested vectors do not replay from frozen coordinates",
    )
    expected_bfloat16 = expected_fp32.to(torch.bfloat16).contiguous()
    _require(
        torch.equal(tensors["requested_positive_bfloat16"], expected_bfloat16),
        "BF16 requested vectors do not replay from FP32 requests",
    )
    _require(
        torch.equal(tensors["plus_hook_vector_bfloat16"], expected_bfloat16),
        "positive hook vectors differ from requests",
    )
    _require(
        torch.equal(tensors["minus_hook_vector_bfloat16"], torch.neg(expected_bfloat16)),
        "negative hook vectors are not exact signed pairs",
    )
    requested_rms = [_rms(value) for value in expected_bfloat16]
    _require(all(value > 0.0 for value in requested_rms), "a nonzero dose rounded to zero")
    _require(
        all(left < right for left, right in zip(requested_rms, requested_rms[1:])),
        "requested BF16 RMS is not strictly monotone",
    )
    realized_plus = tensors["plus_post_bfloat16"].float() - tensors["plus_pre_bfloat16"].float()
    realized_minus = tensors["minus_post_bfloat16"].float() - tensors["minus_pre_bfloat16"].float()
    plus_rms = [_rms(value) for value in realized_plus]
    minus_rms = [_rms(value) for value in realized_minus]
    _require(all(value > 0.0 for value in plus_rms), "a positive edit realized as zero")
    _require(all(value > 0.0 for value in minus_rms), "a negative edit realized as zero")
    return {
        "all_tensors_finite": True,
        "decoder_row_rms": decoder_rms,
        "unit_direction_rms": _rms(expected_unit),
        "clean_source_rms": clean_rms,
        "requested_bfloat16_rms_strictly_monotone": True,
        "minimum_requested_rms_fraction": min(requested_rms) / clean_rms,
        "maximum_requested_rms_fraction": max(requested_rms) / clean_rms,
        "all_signed_realizations_nonzero": True,
        "empirical_fidelity_threshold_applied": False,
    }


def hook_gate(context: AuditContext) -> dict[str, Any]:
    torch = _torch()
    tensors = context.tensors
    clean = tensors["clean_arc_bfloat16"]
    clean_source = clean[EXPECTED_EDIT_LAYER]
    requested = tensors["requested_positive_bfloat16"]
    for index, dose in enumerate(EXPECTED_DOSES):
        for sign in EXPECTED_SIGNS:
            row = context.rows[2 * index + (0 if sign == "plus" else 1)]
            _require(row.get("hook_fire_count") == 1, f"hook count differs: {dose}/{sign}")
            _require(row.get("pre_equals_clean") is True, f"pre differs from clean: {dose}/{sign}")
            _require(
                row.get("upstream_arc_equals_clean") is True,
                f"upstream arc differs from clean: {dose}/{sign}",
            )
            _require(
                row.get("native_post_bytes_exact") is True,
                f"native post bytes differ: {dose}/{sign}",
            )
        positive = requested[index]
        negative = torch.neg(positive).contiguous()
        plus_pre = tensors["plus_pre_bfloat16"][index]
        minus_pre = tensors["minus_pre_bfloat16"][index]
        plus_post = tensors["plus_post_bfloat16"][index]
        minus_post = tensors["minus_post_bfloat16"][index]
        _require(torch.equal(plus_pre, clean_source), f"positive pre differs: {dose}")
        _require(torch.equal(minus_pre, clean_source), f"negative pre differs: {dose}")
        _require(
            torch.equal(
                tensors["plus_arc_bfloat16"][index, : EXPECTED_EDIT_LAYER + 1],
                clean[: EXPECTED_EDIT_LAYER + 1],
            ),
            f"positive upstream arc differs: {dose}",
        )
        _require(
            torch.equal(
                tensors["minus_arc_bfloat16"][index, : EXPECTED_EDIT_LAYER + 1],
                clean[: EXPECTED_EDIT_LAYER + 1],
            ),
            f"negative upstream arc differs: {dose}",
        )
        _require(
            torch.equal(tensors["plus_arc_bfloat16"][index, EXPECTED_EDIT_LAYER], plus_pre),
            f"positive layer-20 capture is not pre-hook: {dose}",
        )
        _require(
            torch.equal(tensors["minus_arc_bfloat16"][index, EXPECTED_EDIT_LAYER], minus_pre),
            f"negative layer-20 capture is not pre-hook: {dose}",
        )
        _require(
            torch.equal(plus_post, (plus_pre + positive).to(torch.bfloat16)),
            f"positive single-use addition does not replay: {dose}",
        )
        _require(
            torch.equal(minus_post, (minus_pre + negative).to(torch.bfloat16)),
            f"negative single-use addition does not replay: {dose}",
        )
    return {
        "clean_zero_hook_fire_count": 0,
        "edited_hook_fire_counts_exact": EXPECTED_ROWS,
        "all_pre_states_equal_clean": True,
        "all_upstream_arcs_byte_equal_clean": True,
        "all_native_bfloat16_additions_byte_exact": True,
    }


def _require_row_exact(row: Mapping[str, Any], expected: Mapping[str, Any]) -> None:
    _require(set(row) == EXPECTED_ROW_FIELDS, "replayed row fields differ")
    numeric_fields = {
        "requested_rms_fraction",
        "realized_rms_fraction",
        "realized_vs_requested_relative_rmse",
    }
    optional_numeric = {"realized_vs_requested_cosine"}
    for key, expected_value in expected.items():
        observed = row.get(key)
        if key in numeric_fields:
            _require(_close_float(observed, float(expected_value)), f"row metric differs: {key}")
        elif key in optional_numeric:
            _require(_same_optional_float(observed, expected_value), f"row metric differs: {key}")
        else:
            _require(observed == expected_value, f"row field differs: {key}")


def _require_pair_exact(pair: Mapping[str, Any], expected: Mapping[str, Any]) -> None:
    _require(set(pair) == EXPECTED_PAIR_FIELDS, "replayed pair fields differ")
    numeric_fields = {
        "central_rms_fraction",
        "central_vs_requested_relative_rmse",
    }
    optional_numeric = {
        "central_vs_requested_cosine",
        "common_mode_to_central_rms",
    }
    for key, expected_value in expected.items():
        observed = pair.get(key)
        if key in numeric_fields:
            _require(_close_float(observed, float(expected_value)), f"pair metric differs: {key}")
        elif key in optional_numeric:
            _require(_same_optional_float(observed, expected_value), f"pair metric differs: {key}")
        else:
            _require(observed == expected_value, f"pair field differs: {key}")


def artifact_replay_gate(context: AuditContext) -> dict[str, Any]:
    torch = _torch()
    tensors = context.tensors
    clean = tensors["clean_arc_bfloat16"]
    clean_source = clean[EXPECTED_EDIT_LAYER]
    clean_rms = _rms(clean_source)
    for index, dose in enumerate(EXPECTED_DOSES):
        requested = tensors["requested_positive_bfloat16"][index]
        for sign, offset in (("plus", 0), ("minus", 1)):
            expected_vector = requested if sign == "plus" else torch.neg(requested).contiguous()
            arc = tensors[f"{sign}_arc_bfloat16"][index]
            pre = tensors[f"{sign}_pre_bfloat16"][index]
            post = tensors[f"{sign}_post_bfloat16"][index]
            hook_vector = tensors[f"{sign}_hook_vector_bfloat16"][index]
            realized = post.float() - pre.float()
            expected_row = {
                "row_index": 2 * index + offset,
                "dose_index": index,
                "dose_basis_points": dose,
                "signed_dose_basis_points": dose if sign == "plus" else -dose,
                "sign": sign,
                "forward_id": f"dose-{dose:04d}-{sign}",
                "hook_fire_count": 1,
                "pre_equals_clean": bool(torch.equal(pre, clean_source)),
                "upstream_arc_equals_clean": bool(
                    torch.equal(
                        arc[: EXPECTED_EDIT_LAYER + 1],
                        clean[: EXPECTED_EDIT_LAYER + 1],
                    )
                ),
                "native_post_bytes_exact": bool(
                    torch.equal(post, (pre + expected_vector).to(torch.bfloat16))
                ),
                "requested_vector_sha256": _tensor_sha256(expected_vector),
                "hook_vector_sha256": _tensor_sha256(hook_vector),
                "pre_sha256": _tensor_sha256(pre),
                "post_sha256": _tensor_sha256(post),
                "arc_sha256": _tensor_sha256(arc),
                "requested_rms_fraction": _rms(expected_vector) / clean_rms,
                "realized_rms_fraction": _rms(realized) / clean_rms,
                "realized_vs_requested_relative_rmse": _relative_rmse(
                    realized, expected_vector
                ),
                "realized_vs_requested_cosine": _cosine_or_none(
                    realized, expected_vector
                ),
                "finite": bool(torch.isfinite(realized).all() and torch.isfinite(arc).all()),
                "semantic_outcome_count": 0,
            }
            _require_row_exact(context.rows[2 * index + offset], expected_row)

        plus_realized = tensors["plus_post_bfloat16"][index].float() - tensors[
            "plus_pre_bfloat16"
        ][index].float()
        minus_realized = tensors["minus_post_bfloat16"][index].float() - tensors[
            "minus_pre_bfloat16"
        ][index].float()
        central = (plus_realized - minus_realized) * 0.5
        common = (plus_realized + minus_realized) * 0.5
        central_rms = _rms(central)
        expected_pair = {
            "pair_index": index,
            "dose_basis_points": dose,
            "plus_row_index": 2 * index,
            "minus_row_index": 2 * index + 1,
            "requested_positive_sha256": _tensor_sha256(requested),
            "realized_central_sha256": _tensor_sha256(central),
            "common_mode_sha256": _tensor_sha256(common),
            "central_rms_fraction": central_rms / clean_rms,
            "central_vs_requested_relative_rmse": _relative_rmse(central, requested),
            "central_vs_requested_cosine": _cosine_or_none(central, requested),
            "common_mode_to_central_rms": (
                _rms(common) / central_rms if central_rms > 0.0 else None
            ),
            "finite": bool(torch.isfinite(central).all() and torch.isfinite(common).all()),
            "semantic_outcome_count": 0,
        }
        _require_pair_exact(context.pairs[index], expected_pair)
    return {
        "requested_vectors_replayed": EXPECTED_PAIRS,
        "signed_rows_replayed": EXPECTED_ROWS,
        "signed_pairs_replayed": EXPECTED_PAIRS,
        "raw_tensor_hashes_recomputed": True,
        "telemetry_recomputed_from_raw": True,
        "semantic_outcomes_consulted": False,
    }


def audit_run(run_dir: Path) -> dict[str, Any]:
    root = run_dir.expanduser().resolve()
    results: dict[str, dict[str, Any]] = {}
    failures: list[dict[str, str]] = []
    context: AuditContext | None = None
    try:
        context, details = structural_gate(root)
        results["structural"] = {"pass": True, "details": details}
    except Exception as exc:
        failures.append({"gate": "structural", "error": str(exc)})
        results["structural"] = {"pass": False, "error": str(exc)}

    for name, gate in (
        ("numeric", numeric_gate),
        ("hook", hook_gate),
        ("artifact_replay", artifact_replay_gate),
    ):
        if context is None:
            results[name] = {
                "pass": False,
                "not_run": True,
                "error": "structural gate did not produce an auditable context",
            }
            continue
        try:
            details = gate(context)
            results[name] = {"pass": True, "details": details}
        except Exception as exc:
            failures.append({"gate": name, "error": str(exc)})
            results[name] = {"pass": False, "error": str(exc)}

    promoted = all(results.get(name, {}).get("pass") is True for name in EXPECTED_GATES)
    report = {
        "schema_version": AUDIT_SCHEMA_VERSION,
        "validation_id": EXPECTED_VALIDATION_ID,
        "audited_at_utc": utc_now(),
        "run_dir": str(root),
        "status": (
            "pass_small_model_promotion_gate"
            if promoted
            else "fail_small_model_promotion_gate"
        ),
        "dose_basis_points_sha256": canonical_sha256(list(EXPECTED_DOSES)),
        "nonzero_dose_count": len(EXPECTED_DOSES),
        "signed_pair_count": len(EXPECTED_DOSES),
        "edited_forward_count": EXPECTED_ROWS,
        "zero_baseline_count": 1,
        "model_id": EXPECTED_MODEL_ID,
        "model_revision": EXPECTED_MODEL_REVISION,
        "sae_repo": EXPECTED_SAE_REPO,
        "sae_revision": EXPECTED_SAE_REVISION,
        "sae_folder": EXPECTED_SAE_FOLDER,
        "sae_feature_id": EXPECTED_FEATURE_ID,
        "required_gates": list(EXPECTED_GATES),
        "promotion_scope": "runner_mechanics_only_not_scientific_protocol",
        "promotion": {
            "pass": promoted,
            "scope": "runner_mechanics_only_not_scientific_protocol",
            "required_gates": list(EXPECTED_GATES),
            "semantic_outcome_gate": False,
            "effect_size_gate": False,
            "dose_threshold_tuning_gate": False,
            "learned_j_gate": False,
            "scientific_claims_authorized": False,
        },
        "gates": results,
        "failures": failures,
    }
    report["receipt_sha256"] = canonical_sha256(report)
    return report


def _atomic_write_json(path: Path, payload: Mapping[str, Any]) -> None:
    temporary = path.with_name(path.name + ".partial")
    if temporary.exists() or path.exists():
        raise AuditError(f"refusing to overwrite audit output: {path}")
    with temporary.open("xb") as handle:
        handle.write(canonical_json_bytes(payload) + b"\n")
        handle.flush()
        os.fsync(handle.fileno())
    temporary.replace(path)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = audit_run(args.run_dir)
    output = (
        args.output.expanduser().resolve()
        if args.output is not None
        else args.run_dir.expanduser().resolve() / "AUDIT.json"
    )
    _atomic_write_json(output, report)
    print(
        f"Gemma dose-grid audit: {report['status'].upper()} -> {output}",
        flush=True,
    )
    if report["status"] != "pass_small_model_promotion_gate":
        raise SystemExit(1)


if __name__ == "__main__":
    main()

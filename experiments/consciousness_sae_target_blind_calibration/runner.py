#!/usr/bin/env python3
"""Execute the frozen target-blind calibration on one cached B200.

The runner writes only to the calibration-v2 raw namespace.  It archives the
full signed residual arcs, exact arithmetic tensors, and primary-dose readout
transport tensors for independent scalar recomputation without the model.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import shutil
import stat
import sys
import time
from datetime import datetime, timezone
from importlib import metadata as importlib_metadata
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence, TypeVar


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from experiments.consciousness_sae_realization_validation import (  # noqa: E402
    runpod_preflight,
    runtime,
)
from experiments.consciousness_sae_target_blind_calibration import (  # noqa: E402
    authorize,
    build_plan,
    orientation,
    protocol,
)


SAFE_RUN_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")
REQUIREMENT_RE = re.compile(r"([A-Za-z0-9][A-Za-z0-9._-]*)==([^\s]+)")
T = TypeVar("T")


class CalibrationExecutionError(RuntimeError):
    pass


SAFE_DENOMINATOR = 1e-30
_CACHE_REHASH_FIELDS = (
    "cache_root",
    "full_file_count",
    "full_retained_bytes",
    "full_file_inventory_sha256",
    "components",
)


def _protocol_mapping(name: str, fallback: Mapping[str, Any]) -> dict[str, Any]:
    value = getattr(protocol, name, fallback)
    if not isinstance(value, Mapping):
        raise CalibrationExecutionError(f"protocol {name} contract is malformed")
    return dict(value)


def _contract_hashes() -> dict[str, str]:
    intervention = _protocol_mapping(
        "INTERVENTION_STATE_CONTRACT",
        {
            "injection_state": "layer_50_block_output",
            "signed_pair": "positive_and_exact_bfloat16_negative",
            "realized_contrast": "post_plus_minus_post_minus_over_two",
            "final_midpoint": "final_plus_plus_final_minus_over_two",
        },
    )
    j_state = _protocol_mapping(
        "J_STATE_CONTRACT",
        {
            "source_layers": list(protocol.J_LAYERS),
            "target_state": "final_pre_rmsnorm",
            "orientation": protocol.J_LENS_SPEC["orientation"],
        },
    )
    fixed_panel = _protocol_mapping(
        "FIXED_PANEL_ESTIMAND",
        {
            "center": "signed_final_midpoint",
            "contrast": "logits(center_plus_prediction)_minus_logits(center_minus_prediction)_over_two",
            "token_count": int(
                protocol.FRESH_RANDOMIZATION_SPEC["fixed_token_panel_size"]
            ),
        },
    )
    return {
        "intervention_state_contract_sha256": protocol.canonical_sha256(intervention),
        "j_state_contract_sha256": protocol.canonical_sha256(j_state),
        "fixed_panel_estimand_sha256": protocol.canonical_sha256(fixed_panel),
    }


def _execution_token_telemetry(
    prompt_receipts: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    forward_inventory = _protocol_mapping(
        "FORWARD_INVENTORY",
        {
            "schema_version": 1,
            "model_forward_definition": "one_full_model_forward_invocation",
            "prefix_forwards": len(protocol.PROMPT_IDS),
            "clean_continuation_forwards": len(protocol.PROMPT_IDS),
            "edited_continuation_forwards": int(
                protocol.RESOURCE_LIMITS["expected_edited_forwards"]
            ),
            "exact_total_model_forwards": int(
                protocol.RESOURCE_LIMITS["expected_model_forwards"]
            ),
            "orientation_fixture_model_forwards": 0,
        },
    )
    count_fields = (
        "prefix_forwards",
        "clean_continuation_forwards",
        "edited_continuation_forwards",
        "exact_total_model_forwards",
        "orientation_fixture_model_forwards",
    )
    counts = {field: forward_inventory.get(field) for field in count_fields}
    if any(
        isinstance(value, bool) or not isinstance(value, int) or value < 0
        for value in counts.values()
    ):
        raise CalibrationExecutionError("forward inventory counts are malformed")
    if (
        counts["prefix_forwards"] != len(prompt_receipts)
        or counts["clean_continuation_forwards"] != len(prompt_receipts)
        or counts["exact_total_model_forwards"]
        != counts["prefix_forwards"]
        + counts["clean_continuation_forwards"]
        + counts["edited_continuation_forwards"]
        + counts["orientation_fixture_model_forwards"]
    ):
        raise CalibrationExecutionError("forward inventory arithmetic differs")

    rendered = 0
    prefix_uncached = 0
    for receipt in prompt_receipts:
        token_ids = receipt.get("token_ids")
        if not isinstance(token_ids, list) or not token_ids:
            raise CalibrationExecutionError("prompt token receipt is malformed")
        token_count = len(token_ids)
        if (
            receipt.get("token_count") != token_count
            or receipt.get("prefix_token_count") != token_count - 1
            or receipt.get("edited_token_index") != token_count - 1
            or receipt.get("continuation_token_id") != token_ids[-1]
            or receipt.get("continuation_forward_sequence_length") != 1
        ):
            raise CalibrationExecutionError("prompt token boundary receipt differs")
        rendered += token_count
        prefix_uncached += token_count - 1
    continuation_uncached = (
        counts["clean_continuation_forwards"] + counts["edited_continuation_forwards"]
    )
    return {
        "forward_inventory": forward_inventory,
        "total_rendered_token_count": rendered,
        "prefix_uncached_token_count": prefix_uncached,
        "continuation_uncached_token_count": continuation_uncached,
        "total_uncached_token_count": prefix_uncached + continuation_uncached,
    }


def _co_located_vectors(left: Any, right: Any, label: str) -> tuple[Any, Any]:
    import torch

    if not isinstance(left, torch.Tensor) or not isinstance(right, torch.Tensor):
        raise CalibrationExecutionError(f"{label} inputs are not tensors")
    lhs = left.detach().float().reshape(-1)
    rhs = right.detach().to(device=lhs.device).float().reshape(-1)
    if lhs.shape != rhs.shape or lhs.numel() == 0:
        raise CalibrationExecutionError(f"{label} tensor shapes differ")
    if not bool(torch.isfinite(lhs).all() and torch.isfinite(rhs).all()):
        raise CalibrationExecutionError(f"{label} tensors are non-finite")
    return lhs, rhs


def _safe_rms(value: Any) -> float:
    import torch

    if not isinstance(value, torch.Tensor) or value.numel() == 0:
        raise CalibrationExecutionError("RMS input is not a nonempty tensor")
    flattened = value.detach().float().reshape(-1)
    if not bool(torch.isfinite(flattened).all()):
        raise CalibrationExecutionError("RMS input is non-finite")
    result = float(torch.sqrt(torch.mean(flattened.square())).item())
    if not math.isfinite(result) or result < 0.0:
        raise CalibrationExecutionError("RMS result is invalid")
    return result


def _safe_relative_rmse(actual: Any, reference: Any) -> float:
    import torch

    observed, expected = _co_located_vectors(actual, reference, "relative RMSE")
    numerator = torch.sqrt(torch.mean((observed - expected).square()))
    denominator = torch.sqrt(torch.mean(expected.square())).clamp_min(SAFE_DENOMINATOR)
    result = float((numerator / denominator).item())
    if not math.isfinite(result) or result < 0.0:
        raise CalibrationExecutionError("relative RMSE result is invalid")
    return result


def _safe_cosine(left: Any, right: Any) -> float:
    import torch

    lhs, rhs = _co_located_vectors(left, right, "cosine")
    denominator = torch.linalg.vector_norm(lhs) * torch.linalg.vector_norm(rhs)
    if float(denominator.item()) <= 0.0:
        return 0.0
    result = float(torch.dot(lhs, rhs).div(denominator).item())
    if not math.isfinite(result):
        raise CalibrationExecutionError("cosine result is non-finite")
    return max(-1.0, min(1.0, result))


def _safe_pearson(left: Any, right: Any) -> float:
    import torch

    lhs, rhs = _co_located_vectors(left, right, "Pearson")
    if lhs.numel() < 2:
        raise CalibrationExecutionError("Pearson inputs contain fewer than two values")
    lhs = lhs - lhs.mean()
    rhs = rhs - rhs.mean()
    denominator = torch.linalg.vector_norm(lhs) * torch.linalg.vector_norm(rhs)
    if float(denominator.item()) <= 0.0:
        return 0.0
    result = float(torch.dot(lhs, rhs).div(denominator).item())
    if not math.isfinite(result):
        raise CalibrationExecutionError("Pearson result is non-finite")
    return max(-1.0, min(1.0, result))


def _realization_metrics(
    clean_source: Any,
    plus: runtime.ArcTrace,
    minus: runtime.ArcTrace,
    requested_positive: Any,
    requested_positive_fp32: Any,
) -> tuple[dict[str, Any], Any, Any]:
    import torch

    if any(
        value is None
        for value in (plus.pre_edit, plus.post_edit, minus.pre_edit, minus.post_edit)
    ):
        raise CalibrationExecutionError("signed edit telemetry is incomplete")
    assert plus.pre_edit is not None and plus.post_edit is not None
    assert minus.pre_edit is not None and minus.post_edit is not None
    requested = (
        requested_positive.detach().to(device="cpu", dtype=torch.bfloat16).contiguous()
    )
    requested_fp32 = (
        requested_positive_fp32.detach()
        .to(device="cpu", dtype=torch.float32)
        .contiguous()
    )
    negative = torch.neg(requested).contiguous()
    plus_native = (plus.pre_edit + requested).to(dtype=torch.bfloat16)
    minus_native = (minus.pre_edit + negative).to(dtype=torch.bfloat16)
    realized_plus = plus.post_edit.float() - plus.pre_edit.float()
    realized_minus = minus.post_edit.float() - minus.pre_edit.float()
    central = (plus.post_edit.float() - minus.post_edit.float()) * 0.5
    common = (
        plus.post_edit.float() + minus.post_edit.float()
    ) * 0.5 - clean_source.float()
    final_central = (plus.final_residual.float() - minus.final_residual.float()) * 0.5
    clean_rms = _safe_rms(clean_source)
    requested_rms = _safe_rms(requested)
    central_rms = _safe_rms(central)
    common_rms = _safe_rms(common)
    if clean_rms <= 0.0 or requested_rms <= 0.0:
        raise CalibrationExecutionError("clean/requested edit RMS is zero")
    finite = bool(
        torch.isfinite(realized_plus).all()
        and torch.isfinite(realized_minus).all()
        and torch.isfinite(central).all()
        and torch.isfinite(common).all()
        and torch.isfinite(final_central).all()
    )
    metrics = {
        "hook_fire_count_plus": plus.hook_fire_count,
        "hook_fire_count_minus": minus.hook_fire_count,
        "pre_equals_clean_plus": bool(torch.equal(plus.pre_edit, clean_source)),
        "pre_equals_clean_minus": bool(torch.equal(minus.pre_edit, clean_source)),
        "native_post_bytes_exact_plus": bool(torch.equal(plus.post_edit, plus_native)),
        "native_post_bytes_exact_minus": bool(
            torch.equal(minus.post_edit, minus_native)
        ),
        "requested_vector_sha256": runtime.tensor_sha256(requested),
        "realized_central_sha256": runtime.tensor_sha256(central),
        "requested_plus_realized_relative_rmse": _safe_relative_rmse(
            realized_plus, requested
        ),
        "requested_minus_realized_relative_rmse": _safe_relative_rmse(
            realized_minus, negative
        ),
        "requested_realized_central_relative_rmse": _safe_relative_rmse(
            central, requested
        ),
        "requested_plus_realized_cosine": _safe_cosine(realized_plus, requested),
        "requested_minus_realized_cosine": _safe_cosine(realized_minus, negative),
        "requested_realized_central_cosine": _safe_cosine(central, requested),
        "fp32_requested_to_bf16_relative_rmse": _safe_relative_rmse(
            requested, requested_fp32
        ),
        "fp32_requested_to_bf16_cosine": _safe_cosine(requested, requested_fp32),
        "native_central_to_fp32_requested_relative_rmse": _safe_relative_rmse(
            central, requested_fp32
        ),
        "native_central_to_fp32_requested_cosine": _safe_cosine(
            central, requested_fp32
        ),
        "common_mode_to_central_rms": common_rms / max(central_rms, SAFE_DENOMINATOR),
        "requested_rms_fraction": requested_rms / clean_rms,
        "realized_rms_fraction": central_rms / clean_rms,
        "finite": finite,
    }
    return metrics, central, final_central


def _fp32_shadow_metrics(
    backend: runtime.V2Backend,
    *,
    edit_layer: int,
    realized_central: Any,
    final_central: Any,
) -> dict[str, Any]:
    value = realized_central.to(device=backend.device, dtype=backend.torch.float32)
    matrix = backend.j_matrix(edit_layer)
    production = value.to(dtype=matrix.dtype) @ matrix.T
    shadow = value @ backend.shadow_matrix(edit_layer).T
    if production.dtype != backend.torch.bfloat16:
        raise CalibrationExecutionError("production J prediction is not BF16")
    finite = bool(
        backend.torch.isfinite(production).all()
        and backend.torch.isfinite(shadow).all()
        and backend.torch.isfinite(final_central).all()
    )
    return {
        "realized_central_source_sha256": runtime.tensor_sha256(realized_central),
        "bf16_j_prediction_sha256": runtime.tensor_sha256(production),
        "fp32_j_prediction_sha256": runtime.tensor_sha256(shadow),
        "bf16_fp32_j_cosine": _safe_cosine(production.float(), shadow),
        "bf16_fp32_j_relative_rmse": _safe_relative_rmse(production.float(), shadow),
        "fp32_j_actual_final_cosine": _safe_cosine(final_central, shadow),
        "finite": finite,
        "_bf16_j_prediction": production.detach(),
        "_fp32_j_prediction": shadow.detach(),
    }


def _absolute(path: Path) -> Path:
    return Path(os.path.abspath(path.expanduser()))


def _require_no_symlink_components(path: Path, label: str) -> None:
    lexical = _absolute(path)
    current = Path(lexical.anchor)
    for part in lexical.parts[1:]:
        current = current / part
        if current.is_symlink():
            raise CalibrationExecutionError(f"{label} contains a symlink component")


def _regular_file(path: Path, label: str) -> Path:
    candidate = _absolute(path)
    _require_no_symlink_components(candidate, label)
    try:
        details = candidate.lstat()
    except OSError as exc:
        raise CalibrationExecutionError(f"{label} is missing") from exc
    if not stat.S_ISREG(details.st_mode) or details.st_nlink != 1:
        raise CalibrationExecutionError(f"{label} is not a single-link regular file")
    return candidate


def _read_json(path: Path) -> dict[str, Any]:
    candidate = _regular_file(path, f"JSON input {path}")
    try:
        raw = candidate.read_bytes()
        value = json.loads(raw)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise CalibrationExecutionError(f"invalid JSON: {path}") from exc
    if not isinstance(value, dict):
        raise CalibrationExecutionError(f"JSON root is not an object: {path}")
    if raw != protocol.canonical_json_bytes(value) + b"\n":
        raise CalibrationExecutionError(f"JSON is not canonical: {path}")
    return value


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    _require_no_symlink_components(path.parent, "JSON output parent")
    if os.path.lexists(path):
        raise CalibrationExecutionError(f"refusing to overwrite output: {path}")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags, 0o600)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(protocol.canonical_json_bytes(dict(value)) + b"\n")
            handle.flush()
            os.fsync(handle.fileno())
    except OSError as exc:
        raise CalibrationExecutionError(f"could not publish output: {path}") from exc


def _write_jsonl(path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    _require_no_symlink_components(path.parent, "JSONL output parent")
    if os.path.lexists(path):
        raise CalibrationExecutionError(f"refusing to overwrite output: {path}")
    with path.open("xb") as handle:
        for row in rows:
            handle.write(protocol.canonical_json_bytes(dict(row)) + b"\n")
        handle.flush()
        os.fsync(handle.fileno())


def _write_tensors(path: Path, values: Mapping[str, Any]) -> None:
    try:
        from safetensors.torch import save_file
    except ImportError as exc:  # pragma: no cover - GPU environment only
        raise CalibrationExecutionError("safetensors is required") from exc
    path.parent.mkdir(parents=True, exist_ok=True)
    _require_no_symlink_components(path.parent, "tensor output parent")
    if os.path.lexists(path):
        raise CalibrationExecutionError(f"refusing to overwrite output: {path}")
    tensors = {
        name: value.detach().to(device="cpu").contiguous()
        for name, value in values.items()
    }
    save_file(tensors, str(path))
    _regular_file(path, "tensor output")
    with path.open("rb") as handle:
        os.fsync(handle.fileno())


def _validate_plan(plan_dir: Path) -> dict[str, Any]:
    root = _absolute(plan_dir)
    _require_no_symlink_components(root, "plan directory")
    if not root.is_dir():
        raise CalibrationExecutionError("plan directory is missing")
    canonical = _absolute(REPO_ROOT / protocol.CANONICAL_PLAN_RELATIVE_PATH)
    if root != canonical:
        raise CalibrationExecutionError(
            "plan directory differs from the canonical relative path"
        )
    manifest = _read_json(_regular_file(root / "plan_manifest.json", "plan manifest"))
    supplied = manifest.get("plan_manifest_sha256")
    core = dict(manifest)
    core.pop("plan_manifest_sha256", None)
    if supplied != protocol.canonical_sha256(core):
        raise CalibrationExecutionError("plan manifest self-hash differs")
    if (
        manifest.get("schema_version") != protocol.PLAN_SCHEMA_VERSION
        or manifest.get("study_id") != protocol.STUDY_ID
        or manifest.get("protocol_version") != protocol.PROTOCOL_VERSION
        or manifest.get("canonical_plan_relative_path")
        != protocol.CANONICAL_PLAN_RELATIVE_PATH
        or manifest.get("scope") != "adaptive_target_blind_numerical_calibration_only"
        or manifest.get("paper_prompt_render_count") != 0
        or manifest.get("analysis_data_inputs") != []
        or manifest.get("target_prompt_render_count") != 0
        or manifest.get("target_feature_vector_count") != 0
    ):
        raise CalibrationExecutionError("plan identity/scope differs")
    records = manifest.get("files")
    if (
        not isinstance(records, list)
        or len(records) != len(build_plan.PLAN_FILE_NAMES)
        or {row.get("path") for row in records if isinstance(row, Mapping)}
        != set(build_plan.PLAN_FILE_NAMES)
    ):
        raise CalibrationExecutionError("plan file inventory differs")
    for record in records:
        if not isinstance(record, Mapping) or set(record) != {
            "path",
            "bytes",
            "sha256",
        }:
            raise CalibrationExecutionError("plan file row schema differs")
        relative = str(record["path"])
        if relative not in build_plan.PLAN_FILE_NAMES:
            raise CalibrationExecutionError("plan file path differs")
        path = _regular_file(root / relative, f"plan file {relative}")
        if (
            isinstance(record["bytes"], bool)
            or not isinstance(record["bytes"], int)
            or path.stat().st_size != record["bytes"]
            or protocol.sha256_file(path) != record.get("sha256")
        ):
            raise CalibrationExecutionError(f"plan file differs: {record.get('path')}")
    if protocol.canonical_json_bytes(
        _read_json(root / "protocol_snapshot.json")
    ) != protocol.canonical_json_bytes(protocol.protocol_snapshot()):
        raise CalibrationExecutionError("runtime protocol differs from frozen snapshot")
    rows = [
        json.loads(line)
        for line in (root / "calibration_plan.jsonl").read_text().splitlines()
    ]
    if protocol.canonical_json_bytes(rows) != protocol.canonical_json_bytes(
        list(protocol.rows())
    ):
        raise CalibrationExecutionError("calibration grid differs from plan")
    if (
        _read_json(root / "adaptive_design_inputs.json")
        != protocol.ADAPTIVE_DESIGN_INPUTS
    ):
        raise CalibrationExecutionError("adaptive design disclosure differs")
    source_value = _read_json(root / "source_files.json")
    sources = source_value.get("files")
    if (
        set(source_value) != {"files"}
        or not isinstance(sources, list)
        or len(sources) != len(build_plan.SOURCE_PATHS)
        or tuple(
            record.get("path") for record in sources if isinstance(record, Mapping)
        )
        != build_plan.SOURCE_PATHS
    ):
        raise CalibrationExecutionError("source file inventory is missing")
    for record in sources:
        if not isinstance(record, Mapping) or set(record) != {
            "path",
            "bytes",
            "sha256",
        }:
            raise CalibrationExecutionError("bound source row schema differs")
        path = _regular_file(
            REPO_ROOT / str(record["path"]),
            f"bound source {record['path']}",
        )
        if (
            isinstance(record["bytes"], bool)
            or not isinstance(record["bytes"], int)
            or path.stat().st_size != record["bytes"]
            or protocol.sha256_file(path) != record.get("sha256")
        ):
            raise CalibrationExecutionError(
                f"bound source differs: {record.get('path')}"
            )
    return manifest


def _render_prompt(tokenizer: Any, prompt_id: str) -> tuple[int, ...]:
    payload = protocol.prompt_payload(prompt_id)
    token_ids = tokenizer.apply_chat_template(
        [
            {"role": "system", "content": payload["system"]},
            {"role": "user", "content": payload["user"]},
        ],
        tokenize=True,
        add_generation_prompt=True,
    )
    if hasattr(token_ids, "tolist"):
        token_ids = token_ids.tolist()
    if token_ids and isinstance(token_ids[0], list):
        if len(token_ids) != 1:
            raise CalibrationExecutionError("tokenizer produced a batch")
        token_ids = token_ids[0]
    result = tuple(int(value) for value in token_ids)
    if len(result) < 2 or min(result) < 0 or max(result) >= protocol.VOCAB_SIZE:
        raise CalibrationExecutionError("rendered calibration tokens are invalid")
    return result


def _direction(direction: int) -> Any:
    import numpy as np
    import torch

    if direction not in protocol.DIRECTIONS:
        raise CalibrationExecutionError("direction is outside the frozen inventory")
    rng = np.random.Generator(
        np.random.PCG64(
            protocol.seed64(
                str(protocol.FRESH_RANDOMIZATION_SPEC["direction_seed_namespace"]),
                direction,
            )
        )
    )
    values = rng.standard_normal(protocol.WIDTH).astype(np.float32)
    values /= max(float(np.sqrt(np.mean(values * values))), 1e-30)
    result = torch.from_numpy(values).contiguous()
    if not bool(torch.isfinite(result).all()):
        raise CalibrationExecutionError("direction is non-finite")
    return result


def _fixed_token_panel() -> tuple[int, ...]:
    modulus = int(
        protocol.FRESH_RANDOMIZATION_SPEC[
            "fixed_token_panel_token_id_upper_bound_exclusive"
        ]
    )
    offset = (
        protocol.seed64(
            str(protocol.FRESH_RANDOMIZATION_SPEC["fixed_token_panel_seed_namespace"])
        )
        % modulus
    )
    return tuple(
        int((offset + 7_919 * index) % modulus)
        for index in range(
            int(protocol.FRESH_RANDOMIZATION_SPEC["fixed_token_panel_size"])
        )
    )


def _random_j_parameters(layer: int, index: int, *, device: Any) -> tuple[Any, ...]:
    import numpy as np
    import torch

    if layer not in protocol.J_LAYERS or index not in range(protocol.RANDOM_J_COUNT):
        raise CalibrationExecutionError("random-J coordinate is outside v2")
    rng = np.random.Generator(
        np.random.PCG64(
            protocol.seed64(
                str(protocol.FRESH_RANDOMIZATION_SPEC["random_j_seed_namespace"]),
                layer,
                index,
            )
        )
    )
    input_perm = rng.permutation(protocol.WIDTH).astype(np.int64)
    input_sign = rng.choice(np.asarray([-1.0, 1.0], dtype=np.float32), protocol.WIDTH)
    output_perm = rng.permutation(protocol.WIDTH).astype(np.int64)
    output_sign = rng.choice(np.asarray([-1.0, 1.0], dtype=np.float32), protocol.WIDTH)
    return (
        torch.from_numpy(input_perm).to(device=device),
        torch.from_numpy(input_sign).to(device=device),
        torch.from_numpy(output_perm).to(device=device),
        torch.from_numpy(output_sign).to(device=device),
    )


def _transport_prediction(
    backend: runtime.V2Backend, source: Any, *, layer: int, transport: str
) -> Any:
    value = source.to(device=backend.device)
    matrix = backend.j_matrix(layer)
    if transport == "real_j":
        result = value.to(dtype=matrix.dtype) @ matrix.T
    elif transport == "identity":
        result = value.to(dtype=matrix.dtype)
    elif transport.startswith("random_j_"):
        index = int(transport.rsplit("_", 1)[1])
        input_perm, input_sign, output_perm, output_sign = _random_j_parameters(
            layer, index, device=value.device
        )
        scrambled = value.to(dtype=matrix.dtype)[..., input_perm] * input_sign.to(
            dtype=matrix.dtype
        )
        result = scrambled @ matrix.T
        result = result[..., output_perm] * output_sign.to(dtype=result.dtype)
    else:
        raise CalibrationExecutionError(f"unknown transport: {transport}")
    if not bool(backend.torch.isfinite(result).all()):
        raise CalibrationExecutionError("transport prediction is non-finite")
    return result.contiguous()


def _transport_metrics(
    backend: runtime.V2Backend,
    *,
    final_midpoint: Any,
    source_delta: Any,
    final_central: Any,
    actual_selected_logits: Any,
    layer: int,
    transport: str,
    selected_token_ids: Sequence[int],
) -> dict[str, Any]:
    prediction = _transport_prediction(
        backend, source_delta, layer=layer, transport=transport
    )
    center = final_midpoint.to(device=backend.device).float()
    predicted_logits = (
        backend.selected_logits_from_state(
            center + prediction.float(), selected_token_ids
        )
        - backend.selected_logits_from_state(
            center - prediction.float(), selected_token_ids
        )
    ) * 0.5
    return {
        "transport": transport,
        "predicted_logit_center": "signed_final_midpoint",
        "predicted_central_final_sha256": runtime.tensor_sha256(prediction),
        "actual_central_final_sha256": runtime.tensor_sha256(final_central),
        "residual_delta_cosine": _safe_cosine(final_central, prediction),
        "fixed_token_logit_delta_pearson": _safe_pearson(
            actual_selected_logits, predicted_logits
        ),
        "finite": bool(
            backend.torch.isfinite(prediction).all()
            and backend.torch.isfinite(predicted_logits).all()
        ),
        "_predicted_central_final": prediction.detach(),
        "_predicted_selected_logit_delta": predicted_logits.detach(),
    }


def _actual_selected_delta(
    backend: runtime.V2Backend,
    plus: runtime.ArcTrace,
    minus: runtime.ArcTrace,
    token_ids: Sequence[int],
) -> Any:
    return (
        backend.selected_logits_from_state(
            plus.final_residual.to(device=backend.device), token_ids
        )
        - backend.selected_logits_from_state(
            minus.final_residual.to(device=backend.device), token_ids
        )
    ) * 0.5


def _records(
    root: Path, *, progress_callback: Callable[[], None] | None = None
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    stack = [root]
    while stack:
        directory = stack.pop()
        try:
            entries = sorted(os.scandir(directory), key=lambda entry: entry.name)
        except OSError as exc:
            raise CalibrationExecutionError("raw output tree is unreadable") from exc
        for entry in entries:
            if progress_callback is not None:
                progress_callback()
            path = Path(entry.path)
            try:
                if entry.is_symlink():
                    raise CalibrationExecutionError(
                        "raw output tree contains a symlink"
                    )
                if entry.is_dir(follow_symlinks=False):
                    stack.append(path)
                    continue
                if not entry.is_file(follow_symlinks=False):
                    raise CalibrationExecutionError(
                        "raw output tree contains a special object"
                    )
                details = entry.stat(follow_symlinks=False)
            except OSError as exc:
                raise CalibrationExecutionError(
                    "raw output tree changed during walk"
                ) from exc
            if details.st_nlink != 1:
                raise CalibrationExecutionError("raw output tree contains a hard link")
            if path.name in {"RUN_COMPLETE.json", "ABORTED.json"}:
                continue
            rows.append(
                {
                    "path": path.relative_to(root).as_posix(),
                    "bytes": details.st_size,
                    "sha256": protocol.sha256_file(path),
                }
            )
    return sorted(rows, key=lambda row: str(row["path"]))


def _check_storage(root: Path) -> int:
    free = shutil.disk_usage(root).free
    required = (
        protocol.RESOURCE_LIMITS["raw_run_ceiling_bytes"]
        + protocol.RESOURCE_LIMITS["post_run_free_reserve_bytes"]
    )
    if free < required:
        raise CalibrationExecutionError("network volume lacks the frozen reserve")
    return int(free)


def _ensure_real_directory(path: Path, label: str) -> Path:
    candidate = _absolute(path)
    _require_no_symlink_components(candidate.parent, f"{label} parent")
    if os.path.lexists(candidate):
        try:
            details = candidate.lstat()
        except OSError as exc:
            raise CalibrationExecutionError(f"{label} is unreadable") from exc
        if not stat.S_ISDIR(details.st_mode):
            raise CalibrationExecutionError(f"{label} is not a real directory")
    else:
        try:
            candidate.mkdir(mode=0o700)
        except OSError as exc:
            raise CalibrationExecutionError(f"{label} could not be created") from exc
    _require_no_symlink_components(candidate, label)
    return candidate


def _initialize_namespace(volume_root: Path, *, volume_id: str) -> Path:
    _require_no_symlink_components(volume_root, "volume root")
    root = _absolute(volume_root)
    if (
        volume_id != protocol.NETWORK_VOLUME_ID
        or not root.is_dir()
        or str(root) != protocol.VOLUME_MOUNT_PATH
    ):
        raise CalibrationExecutionError("volume root differs from /workspace")
    study_root = _ensure_real_directory(
        root / protocol.STUDY_SLUG, "calibration study root"
    )
    study_namespace = _ensure_real_directory(
        study_root / protocol.STUDY_ID, "calibration v2 namespace"
    )
    _ensure_real_directory(study_namespace / "raw", "calibration raw namespace")
    sentinel = study_root / ".target_blind_calibration_v2_volume.json"
    expected = {
        "study_id": protocol.STUDY_ID,
        "protocol_version": protocol.PROTOCOL_VERSION,
        "volume_id": protocol.NETWORK_VOLUME_ID,
        "mount_path": protocol.VOLUME_MOUNT_PATH,
        "purpose": "adaptive_target_blind_calibration_raw_only",
    }
    if os.path.lexists(sentinel):
        if _read_json(sentinel) != expected:
            raise CalibrationExecutionError("calibration volume sentinel differs")
    else:
        _write_json(sentinel, expected)
    return root


def _validate_infrastructure_receipts(
    *,
    ownership_receipt_path: Path,
    guest_receipt_path: Path,
    cache_receipt_path: Path,
    model_snapshot: Path,
    sae_path: Path,
    j_lens_path: Path,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    ownership_raw = _read_json(ownership_receipt_path)
    guest_raw = _read_json(guest_receipt_path)
    cache_raw = _read_json(cache_receipt_path)
    try:
        ownership = runpod_preflight.validate_ownership_receipt(ownership_raw)
        guest = runpod_preflight.validate_guest_receipt(
            guest_raw, ownership_receipt=ownership
        )
        cache = runpod_preflight.validate_cache_receipt(
            cache_raw, guest_receipt=guest, ownership_receipt=ownership
        )
    except runpod_preflight.PreflightError as exc:
        raise CalibrationExecutionError(
            f"ownership/guest/cache receipt chain failed: {exc}"
        ) from exc
    if (
        ownership["pod_id"] != os.environ.get("RUNPOD_POD_ID")
        or ownership["network_volume_id"] != protocol.NETWORK_VOLUME_ID
        or ownership["data_center_id"] != protocol.DATA_CENTER_ID
        or ownership["gpu_type"] != protocol.GPU_TYPE
        or ownership["gpu_count"] != 1
    ):
        raise CalibrationExecutionError("provider ownership differs from the guest")
    revisions = {
        str(row.get("component")): str(row.get("revision"))
        for row in cache.get("components", [])
        if isinstance(row, Mapping)
    }
    if revisions != {
        "model": str(protocol.MODEL_SPEC["revision"]),
        "sae": str(protocol.SAE_SPEC["revision"]),
        "j_lens": str(protocol.J_LENS_SPEC["revision"]),
    }:
        raise CalibrationExecutionError("verified cache revisions differ")
    cache_root_input = Path(str(cache["cache_root"]))
    _require_no_symlink_components(cache_root_input, "cache root")
    cache_root = cache_root_input.resolve(strict=True)
    if not cache_root.is_dir():
        raise CalibrationExecutionError("verified cache root is not a directory")
    expected_inputs = {
        "model": cache_root / "model_snapshot",
        "sae": cache_root / "sae" / "Llama-3.3-70B-Instruct-SAE-l50.pt",
        "j_lens": cache_root / "jlens" / "Llama-3.3-70B-Instruct_jacobian_lens.pt",
    }
    for label, path in expected_inputs.items():
        _require_no_symlink_components(path, f"cached {label}")
    expected = {
        label: path.resolve(strict=True) for label, path in expected_inputs.items()
    }
    if not expected["model"].is_dir():
        raise CalibrationExecutionError("cached model snapshot is not a directory")
    _regular_file(expected["sae"], "cached SAE")
    _regular_file(expected["j_lens"], "cached J lens")
    observed = {
        "model": _absolute(model_snapshot).resolve(strict=True),
        "sae": _regular_file(sae_path, "requested SAE").resolve(strict=True),
        "j_lens": _regular_file(j_lens_path, "requested J lens").resolve(strict=True),
    }
    _require_no_symlink_components(model_snapshot, "requested model snapshot")
    if not observed["model"].is_dir():
        raise CalibrationExecutionError("requested model snapshot is not a directory")
    if observed != expected:
        raise CalibrationExecutionError("runtime artifacts escaped the verified cache")
    return ownership, guest, cache


def _rehash_bound_public_cache(
    cache: Mapping[str, Any],
    *,
    rehash: Callable[[Path], Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    operation = rehash or runpod_preflight.rehash_legacy_public_artifact_cache
    try:
        observed_value = operation(Path(str(cache["cache_root"])))
    except (OSError, runpod_preflight.PreflightError) as exc:
        raise CalibrationExecutionError(
            "immediate public-cache rehash failed before backend construction"
        ) from exc
    if not isinstance(observed_value, Mapping):
        raise CalibrationExecutionError("immediate public-cache rehash is malformed")
    observed = dict(observed_value)
    expected = {field: cache.get(field) for field in _CACHE_REHASH_FIELDS}
    if set(observed) != set(_CACHE_REHASH_FIELDS) or observed != expected:
        raise CalibrationExecutionError(
            "immediate public-cache rehash differs from the bound cache receipt"
        )
    core = {
        "status": "pass_exact_pre_backend_rehash",
        "cache_receipt_sha256": cache.get("receipt_sha256"),
        **observed,
    }
    return {**core, "receipt_sha256": protocol.canonical_sha256(core)}


def _validate_runtime_requirements(
    path: Path | None = None,
    *,
    version: Callable[[str], str] = importlib_metadata.version,
) -> dict[str, str]:
    requirements_path = _regular_file(
        path
        or REPO_ROOT
        / "experiments/consciousness_sae_target_blind_calibration/requirements-runpod-b200.txt",
        "RunPod requirements",
    )
    expected: dict[str, str] = {}
    for line_number, raw_line in enumerate(
        requirements_path.read_text(encoding="utf-8").splitlines(), 1
    ):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        matched = REQUIREMENT_RE.fullmatch(line)
        if matched is None or matched.group(1).lower() in expected:
            raise CalibrationExecutionError(
                f"RunPod requirement line is not an exact unique pin: {line_number}"
            )
        expected[matched.group(1).lower()] = matched.group(2)
    if not expected:
        raise CalibrationExecutionError("RunPod requirements inventory is empty")
    try:
        observed = {name: version(name) for name in expected}
    except importlib_metadata.PackageNotFoundError as exc:
        raise CalibrationExecutionError(
            f"required RunPod package is missing: {exc.name}"
        ) from exc
    if observed != expected:
        raise CalibrationExecutionError(
            f"RunPod dependency versions differ: expected={expected}, observed={observed}"
        )
    return observed


def _validate_authorization(
    path: Path,
    *,
    plan_dir: Path,
    plan: Mapping[str, Any],
    ownership: Mapping[str, Any],
    guest: Mapping[str, Any],
    cache: Mapping[str, Any],
) -> dict[str, Any]:
    value = _read_json(path)
    root = _absolute(plan_dir)
    try:
        return authorize.validate_execution_authorization(
            value,
            plan=plan,
            plan_manifest_path=root / "plan_manifest.json",
            source_files_path=root / "source_files.json",
            ownership=ownership,
            guest=guest,
            cache=cache,
            now_unix=time.time(),
        )
    except authorize.AuthorizationError as exc:
        raise CalibrationExecutionError(
            f"execution authorization failed: {exc}"
        ) from exc


def _runner_watchdog_seconds() -> int:
    value = int(
        getattr(
            protocol,
            "RUNNER_WATCHDOG_SECONDS",
            protocol.RESOURCE_LIMITS["max_walltime_seconds"],
        )
    )
    campaign = int(protocol.RESOURCE_LIMITS["max_walltime_seconds"])
    if value <= 0 or value > campaign:
        raise CalibrationExecutionError("runner watchdog interval is invalid")
    return value


def _orientation_status(receipt: Mapping[str, Any]) -> str:
    status = receipt.get("status")
    if status not in {"pass", "fail"}:
        raise CalibrationExecutionError("J orientation receipt status is malformed")
    return str(status)


class _Watchdog:
    def __init__(
        self,
        *,
        started: float,
        deadline: float,
        hourly_price: float,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.started = started
        self.deadline = deadline
        self.runner_watchdog_seconds = _runner_watchdog_seconds()
        self.runner_deadline = min(
            deadline, started + float(self.runner_watchdog_seconds)
        )
        self.hourly_price = hourly_price
        self._clock = clock
        if (
            not all(math.isfinite(value) for value in (started, deadline, hourly_price))
            or deadline - started != protocol.RESOURCE_LIMITS["max_walltime_seconds"]
            or self.runner_deadline > deadline
            or hourly_price
            != protocol.RESOURCE_LIMITS["conservative_accounting_rate_usd_per_hour"]
            or hourly_price * (deadline - started) / 3600
            != protocol.RESOURCE_LIMITS["max_spend_usd"]
        ):
            raise CalibrationExecutionError("calibration watchdog authority differs")

    def check(self, label: str = "operation") -> None:
        now = self._clock()
        elapsed = now - self.started
        if (
            not math.isfinite(now)
            or now < self.started
            or now >= self.runner_deadline
            or elapsed >= self.runner_watchdog_seconds
            or self.hourly_price * elapsed / 3600
            >= protocol.RESOURCE_LIMITS["max_spend_usd"]
        ):
            raise CalibrationExecutionError(
                f"calibration watchdog budget expired around {label}"
            )

    def guard(
        self, label: str, operation: Callable[..., T], *args: Any, **kwargs: Any
    ) -> T:
        self.check(f"before {label}")
        result = operation(*args, **kwargs)
        self.check(f"after {label}")
        return result


def execute(
    *,
    plan_dir: Path,
    volume_root: Path,
    volume_id: str,
    run_id: str,
    model_snapshot: Path,
    sae_path: Path,
    j_lens_path: Path,
    ownership_receipt_path: Path,
    guest_receipt_path: Path,
    cache_receipt_path: Path,
    authorization_receipt_path: Path,
) -> Path:
    if SAFE_RUN_ID.fullmatch(run_id) is None:
        raise CalibrationExecutionError("run ID is unsafe")
    if volume_id != protocol.NETWORK_VOLUME_ID:
        raise CalibrationExecutionError(
            "requested volume differs from the frozen volume"
        )
    if os.environ.get("RUNPOD_VOLUME_ID") != protocol.NETWORK_VOLUME_ID:
        raise CalibrationExecutionError(
            "RUNPOD_VOLUME_ID differs from the requested volume"
        )
    if os.environ.get("RUNPOD_DC_ID") != protocol.DATA_CENTER_ID:
        raise CalibrationExecutionError("calibration pod is outside US-CA-2")
    if not os.environ.get("RUNPOD_POD_ID"):
        raise CalibrationExecutionError("RUNPOD_POD_ID is missing")

    plan = _validate_plan(plan_dir)
    ownership, guest, cache = _validate_infrastructure_receipts(
        ownership_receipt_path=ownership_receipt_path,
        guest_receipt_path=guest_receipt_path,
        cache_receipt_path=cache_receipt_path,
        model_snapshot=model_snapshot,
        sae_path=sae_path,
        j_lens_path=j_lens_path,
    )
    authorization = _validate_authorization(
        authorization_receipt_path,
        plan_dir=plan_dir,
        plan=plan,
        ownership=ownership,
        guest=guest,
        cache=cache,
    )
    watchdog = _Watchdog(
        started=float(authorization["campaign_started_at_unix"]),
        deadline=float(authorization["campaign_deadline_at_unix"]),
        hourly_price=float(authorization["hourly_price_usd"]),
    )
    watchdog.check()
    watchdog.guard("runtime dependency validation", _validate_runtime_requirements)
    root = _initialize_namespace(volume_root, volume_id=volume_id)
    free_before = _check_storage(root)
    namespace = root / protocol.STUDY_SLUG / protocol.STUDY_ID / "raw"
    _require_no_symlink_components(namespace, "calibration raw namespace")
    destination = namespace / run_id
    partial = namespace / f".{run_id}.partial"
    if os.path.lexists(destination) or os.path.lexists(partial):
        raise CalibrationExecutionError(
            "refusing to overwrite a calibration transaction"
        )
    partial.mkdir()

    backend: runtime.V2Backend | None = None
    started = time.time()
    try:
        artifact_records = watchdog.guard(
            "public artifact verification",
            runtime.verify_public_artifacts,
            sae_path=sae_path,
            j_lens_path=j_lens_path,
        )
        tokenizer = watchdog.guard(
            "tokenizer load", runtime.load_tokenizer, model_snapshot
        )
        live_cache_rehash = watchdog.guard(
            "immediate pre-backend full public-cache rehash",
            _rehash_bound_public_cache,
            cache,
        )
        backend = watchdog.guard(
            "model/SAE/J-lens load",
            runtime.V2Backend,
            model_snapshot=model_snapshot,
            sae_path=sae_path,
            j_lens_path=j_lens_path,
            tokenizer=tokenizer,
            ownership_receipt_sha256=ownership["receipt_sha256"],
            load_shadow_layers=(protocol.EDIT_LAYER,),
            runtime_seed=protocol.seed64(
                str(protocol.FRESH_RANDOMIZATION_SPEC["runtime_seed_namespace"])
            )
            % (2**63 - 1),
        )
        backend.start_runtime_interval()
        selected_ids = _fixed_token_panel()
        prompt_receipts: list[dict[str, Any]] = []
        pair_index: list[dict[str, Any]] = []
        realization_rows: list[dict[str, Any]] = []
        readout_rows: list[dict[str, Any]] = []
        clean_values: list[Any] = []
        clean_index: list[dict[str, Any]] = []
        directions = {value: _direction(value) for value in protocol.DIRECTIONS}
        contract_hashes = _contract_hashes()

        orientation_rows, orientation_receipt = orientation.execute(
            backend,
            plan_manifest_sha256=plan["plan_manifest_sha256"],
            progress_callback=watchdog.check,
        )
        orientation_status = _orientation_status(orientation_receipt)
        _write_jsonl(partial / "j_orientation_rows.jsonl", orientation_rows)
        _write_json(partial / "j_orientation_receipt.json", orientation_receipt)

        for prompt_id in protocol.PROMPT_IDS:
            watchdog.check()
            token_ids = _render_prompt(tokenizer, prompt_id)
            prompt_receipts.append(
                {
                    "prompt_id": prompt_id,
                    "target_prompt": False,
                    "prompt_payload_sha256": protocol.canonical_sha256(
                        protocol.prompt_payload(prompt_id)
                    ),
                    "token_ids": list(token_ids),
                    "token_ids_sha256": protocol.canonical_sha256(list(token_ids)),
                    "token_count": len(token_ids),
                    "prefix_token_count": len(token_ids) - 1,
                    "edited_token_index": len(token_ids) - 1,
                    "continuation_token_id": token_ids[-1],
                    "continuation_forward_sequence_length": 1,
                    **contract_hashes,
                }
            )
            session = watchdog.guard("clean prompt arc", backend.prepare_arc, token_ids)
            traces: list[Any] = []
            arithmetic: dict[str, list[Any]] = {
                "requested_fp32": [],
                "requested_bfloat16": [],
                "realized_plus_fp32": [],
                "realized_minus_fp32": [],
                "realized_central_fp32": [],
                "common_mode_fp32": [],
                "final_central_fp32": [],
                "j_prediction_bfloat16": [],
                "j_prediction_fp32": [],
            }
            readout_raw: dict[str, list[Any]] = {
                "source_delta_fp32": [],
                "transport_prediction_bfloat16": [],
                "transport_selected_logit_delta_fp32": [],
                "actual_selected_logit_delta_fp32": [],
            }
            try:
                clean = backend.torch.stack(
                    [
                        session.clean.residual_by_layer[layer]
                        for layer in protocol.J_LAYERS
                    ]
                    + [session.clean.final_residual]
                ).contiguous()
                clean_index.append(
                    {
                        "row_index": len(clean_values),
                        "prompt_id": prompt_id,
                        "state_labels": [
                            *(str(layer) for layer in protocol.J_LAYERS),
                            "final",
                        ],
                    }
                )
                clean_values.append(clean)
                clean_source = session.clean.residual_by_layer[protocol.EDIT_LAYER]
                clean_rms = runtime.tensor_rms(clean_source)
                for direction in protocol.DIRECTIONS:
                    unit = directions[direction]
                    for dose in protocol.DOSE_GRID:
                        watchdog.check()
                        requested_fp32 = (
                            (unit * (clean_rms * dose))
                            .to(dtype=backend.torch.float32)
                            .contiguous()
                        )
                        requested = requested_fp32.to(
                            dtype=backend.torch.bfloat16
                        ).contiguous()
                        identity = f"{prompt_id}:{direction}:{dose}"
                        plus = watchdog.guard(
                            "plus edited forward",
                            session.edited,
                            protocol.EDIT_LAYER,
                            requested.to(device=backend.device),
                            forward_id=identity + ":plus",
                        )
                        minus = watchdog.guard(
                            "minus edited forward",
                            session.edited,
                            protocol.EDIT_LAYER,
                            backend.torch.neg(requested).to(device=backend.device),
                            forward_id=identity + ":minus",
                        )
                        if (
                            plus.pre_edit is None
                            or plus.post_edit is None
                            or minus.pre_edit is None
                            or minus.post_edit is None
                        ):
                            raise CalibrationExecutionError(
                                "signed edit telemetry is incomplete"
                            )
                        pair_row = len(arithmetic["requested_fp32"])
                        base = {
                            "prompt_id": prompt_id,
                            "edit_layer": protocol.EDIT_LAYER,
                            "direction": direction,
                            "dose_fraction": dose,
                            "target_prompt_used": False,
                            "target_feature_used": False,
                        }
                        plus_trace_row = len(traces)
                        traces.append(
                            runtime.trace_stage_a_tensor(
                                plus, edit_layer=protocol.EDIT_LAYER
                            )
                        )
                        minus_trace_row = len(traces)
                        traces.append(
                            runtime.trace_stage_a_tensor(
                                minus, edit_layer=protocol.EDIT_LAYER
                            )
                        )
                        values, realized, final_central = _realization_metrics(
                            clean_source,
                            plus,
                            minus,
                            requested,
                            requested_fp32,
                        )
                        realized_plus = plus.post_edit.float() - plus.pre_edit.float()
                        realized_minus = (
                            minus.post_edit.float() - minus.pre_edit.float()
                        )
                        common = (
                            plus.post_edit.float() + minus.post_edit.float()
                        ) * 0.5 - clean_source.float()
                        shadow = _fp32_shadow_metrics(
                            backend,
                            edit_layer=protocol.EDIT_LAYER,
                            realized_central=realized,
                            final_central=final_central,
                        )
                        realization_rows.append(
                            {
                                **base,
                                **{
                                    key: value
                                    for key, value in values.items()
                                    if key != "finite"
                                },
                                **{
                                    key: value
                                    for key, value in shadow.items()
                                    if not key.startswith("_") and key != "finite"
                                },
                                "edit_finite": values["finite"],
                                "j_shadow_finite": shadow["finite"],
                                "finite": bool(values["finite"] and shadow["finite"]),
                                "pre_injection_45_49_exact_plus": all(
                                    backend.torch.equal(
                                        plus.residual_by_layer[layer],
                                        session.clean.residual_by_layer[layer],
                                    )
                                    for layer in range(45, 50)
                                ),
                                "pre_injection_45_49_exact_minus": all(
                                    backend.torch.equal(
                                        minus.residual_by_layer[layer],
                                        session.clean.residual_by_layer[layer],
                                    )
                                    for layer in range(45, 50)
                                ),
                            }
                        )
                        pair_index.append(
                            {
                                **base,
                                "pair_row": pair_row,
                                "plus_trace_row": plus_trace_row,
                                "minus_trace_row": minus_trace_row,
                                "residual_shard": f"residuals/{prompt_id}.safetensors",
                                "arithmetic_shard": f"arithmetic/{prompt_id}.safetensors",
                            }
                        )
                        arithmetic["requested_fp32"].append(requested_fp32)
                        arithmetic["requested_bfloat16"].append(requested)
                        arithmetic["realized_plus_fp32"].append(realized_plus)
                        arithmetic["realized_minus_fp32"].append(realized_minus)
                        arithmetic["realized_central_fp32"].append(realized)
                        arithmetic["common_mode_fp32"].append(common)
                        arithmetic["final_central_fp32"].append(final_central)
                        arithmetic["j_prediction_bfloat16"].append(
                            shadow["_bf16_j_prediction"]
                        )
                        arithmetic["j_prediction_fp32"].append(
                            shadow["_fp32_j_prediction"]
                        )

                        if dose == protocol.PRIMARY_DOSE:
                            actual_logits = _actual_selected_delta(
                                backend, plus, minus, selected_ids
                            )
                            final_midpoint = (
                                plus.final_residual.float()
                                + minus.final_residual.float()
                            ) * 0.5
                            layer_sources: list[Any] = []
                            layer_predictions: list[Any] = []
                            layer_predicted_logits: list[Any] = []
                            for readout_layer in protocol.READOUT_LAYERS:
                                watchdog.check()
                                if readout_layer == protocol.EDIT_LAYER:
                                    source_delta = realized
                                else:
                                    source_delta = (
                                        plus.residual_by_layer[readout_layer].float()
                                        - minus.residual_by_layer[readout_layer].float()
                                    ) * 0.5
                                layer_sources.append(source_delta)
                                predictions: list[Any] = []
                                predicted_logits: list[Any] = []
                                for transport_name in protocol.TRANSPORTS:
                                    watchdog.check()
                                    telemetry = _transport_metrics(
                                        backend,
                                        final_midpoint=final_midpoint,
                                        source_delta=source_delta,
                                        final_central=final_central,
                                        actual_selected_logits=actual_logits,
                                        layer=readout_layer,
                                        transport=transport_name,
                                        selected_token_ids=selected_ids,
                                    )
                                    readout_rows.append(
                                        {
                                            **base,
                                            "readout_layer": readout_layer,
                                            **{
                                                key: value
                                                for key, value in telemetry.items()
                                                if not key.startswith("_")
                                            },
                                        }
                                    )
                                    predictions.append(
                                        telemetry["_predicted_central_final"]
                                    )
                                    predicted_logits.append(
                                        telemetry["_predicted_selected_logit_delta"]
                                    )
                                layer_predictions.append(
                                    backend.torch.stack(predictions).to(
                                        dtype=backend.torch.bfloat16
                                    )
                                )
                                layer_predicted_logits.append(
                                    backend.torch.stack(predicted_logits).float()
                                )
                            readout_raw["source_delta_fp32"].append(
                                backend.torch.stack(layer_sources).float()
                            )
                            readout_raw["transport_prediction_bfloat16"].append(
                                backend.torch.stack(layer_predictions)
                            )
                            readout_raw["transport_selected_logit_delta_fp32"].append(
                                backend.torch.stack(layer_predicted_logits)
                            )
                            readout_raw["actual_selected_logit_delta_fp32"].append(
                                actual_logits.float()
                            )
            finally:
                session.close()

            watchdog.guard(
                f"{prompt_id} residual shard write",
                _write_tensors,
                partial / "residuals" / f"{prompt_id}.safetensors",
                {"arc_bfloat16": backend.torch.stack(traces)},
            )
            watchdog.guard(
                f"{prompt_id} arithmetic shard write",
                _write_tensors,
                partial / "arithmetic" / f"{prompt_id}.safetensors",
                {
                    name: backend.torch.stack(values)
                    for name, values in arithmetic.items()
                },
            )
            watchdog.guard(
                f"{prompt_id} readout shard write",
                _write_tensors,
                partial / "readout_transport" / f"{prompt_id}.safetensors",
                {
                    name: backend.torch.stack(values)
                    for name, values in readout_raw.items()
                },
            )

        watchdog.guard(
            "clean residual shard write",
            _write_tensors,
            partial / "residuals" / "clean.safetensors",
            {"clean_arc_bfloat16": backend.torch.stack(clean_values)},
        )
        watchdog.guard(
            "prompt receipt finalization",
            _write_jsonl,
            partial / "prompt_receipts.jsonl",
            prompt_receipts,
        )
        watchdog.guard(
            "clean index finalization",
            _write_jsonl,
            partial / "clean_index.jsonl",
            clean_index,
        )
        watchdog.guard(
            "pair index finalization",
            _write_jsonl,
            partial / "pair_index.jsonl",
            pair_index,
        )
        watchdog.guard(
            "realization row finalization",
            _write_jsonl,
            partial / "realization_rows.jsonl",
            realization_rows,
        )
        watchdog.guard(
            "readout row finalization",
            _write_jsonl,
            partial / "readout_transport_rows.jsonl",
            readout_rows,
        )
        _write_json(
            partial / "fixed_token_panel.json",
            {
                "token_ids": list(selected_ids),
                "sha256": protocol.canonical_sha256(list(selected_ids)),
            },
        )
        runtime_metadata = {
            **backend.runtime_metadata(),
            "expected_model_forward_count": protocol.RESOURCE_LIMITS[
                "expected_model_forwards"
            ],
            "expected_edited_forward_count": protocol.RESOURCE_LIMITS[
                "expected_edited_forwards"
            ],
            "prompt_count": len(protocol.PROMPT_IDS),
            "realization_row_count": len(realization_rows),
            "readout_transport_row_count": len(readout_rows),
            "j_orientation_row_count": len(orientation_rows),
            "j_orientation_status": orientation_status,
            "runner_watchdog_seconds": watchdog.runner_watchdog_seconds,
            "runner_deadline_at_unix": watchdog.runner_deadline,
            "live_public_cache_rehash": live_cache_rehash,
            **contract_hashes,
            **_execution_token_telemetry(prompt_receipts),
        }
        if (
            runtime_metadata["model_forward_count"]
            != protocol.RESOURCE_LIMITS["expected_model_forwards"]
        ):
            raise CalibrationExecutionError("observed model-forward count differs")
        _write_json(partial / "runtime_metadata.json", runtime_metadata)
        _write_json(
            partial / "execution_binding.json",
            {
                "study_id": protocol.STUDY_ID,
                "protocol_version": protocol.PROTOCOL_VERSION,
                "canonical_plan_relative_path": protocol.CANONICAL_PLAN_RELATIVE_PATH,
                "plan_manifest_sha256": plan["plan_manifest_sha256"],
                "plan_git_head_commit": plan["git_head_commit"],
                "pod_id": os.environ["RUNPOD_POD_ID"],
                "volume_id": volume_id,
                "data_center_id": os.environ["RUNPOD_DC_ID"],
                "ownership_receipt_sha256": ownership["receipt_sha256"],
                "guest_receipt_sha256": guest["receipt_sha256"],
                "cache_receipt_sha256": cache["receipt_sha256"],
                "authorization_receipt_sha256": authorization["receipt_sha256"],
                "artifacts": artifact_records,
                "live_public_cache_rehash": live_cache_rehash,
                **contract_hashes,
                "adaptive_design_inputs_sha256": protocol.canonical_sha256(
                    protocol.ADAPTIVE_DESIGN_INPUTS
                ),
                "analysis_data_inputs": [],
                "target_prompt_render_count": 0,
                "target_feature_vector_count": 0,
            },
        )
        records = watchdog.guard(
            "raw manifest hashing",
            _records,
            partial,
            progress_callback=watchdog.check,
        )
        stored_bytes = sum(int(row["bytes"]) for row in records)
        if stored_bytes > protocol.RESOURCE_LIMITS["raw_run_ceiling_bytes"]:
            raise CalibrationExecutionError("raw calibration exceeded one GiB")
        free_after = watchdog.guard("post-run storage check", _check_storage, root)
        watchdog.check("before completion receipt")
        completed_at = time.time()
        core = {
            "schema_version": 1,
            "status": "complete",
            "study_id": protocol.STUDY_ID,
            "protocol_version": protocol.PROTOCOL_VERSION,
            "run_id": run_id,
            "canonical_plan_relative_path": protocol.CANONICAL_PLAN_RELATIVE_PATH,
            "plan_manifest_sha256": plan["plan_manifest_sha256"],
            "volume_id": volume_id,
            "records": records,
            "stored_bytes": stored_bytes,
            "free_bytes_before": free_before,
            "free_bytes_after": free_after,
            "runtime": runtime_metadata,
            "resource": {
                "hourly_price_usd": authorization["hourly_price_usd"],
                "campaign_started_at_unix": authorization["campaign_started_at_unix"],
                "campaign_deadline_at_unix": authorization["campaign_deadline_at_unix"],
                "runner_deadline_at_unix": watchdog.runner_deadline,
                "runner_watchdog_seconds": watchdog.runner_watchdog_seconds,
                "run_started_at_unix": started,
                "run_completed_at_unix": completed_at,
                "campaign_elapsed_seconds": completed_at
                - float(authorization["campaign_started_at_unix"]),
                "campaign_estimated_spend_usd": float(authorization["hourly_price_usd"])
                * (completed_at - float(authorization["campaign_started_at_unix"]))
                / 3600,
            },
            "adaptive_design_inputs": protocol.ADAPTIVE_DESIGN_INPUTS,
            "analysis_data_inputs": [],
            "target_prompt_render_count": 0,
            "target_feature_vector_count": 0,
        }
        complete = {**core, "receipt_sha256": protocol.canonical_sha256(core)}
        watchdog.guard(
            "completion receipt publication",
            _write_json,
            partial / "RUN_COMPLETE.json",
            complete,
        )
        watchdog.check("before atomic transaction publication")
        os.replace(partial, destination)
        return destination
    except BaseException as exc:
        if partial.exists():
            aborted = {
                "status": "aborted",
                "study_id": protocol.STUDY_ID,
                "protocol_version": protocol.PROTOCOL_VERSION,
                "run_id": run_id,
                "error_type": type(exc).__name__,
                "error": str(exc),
                "recorded_at_utc": datetime.now(timezone.utc)
                .isoformat()
                .replace("+00:00", "Z"),
            }
            try:
                _write_json(partial / "ABORTED.json", aborted)
            except OSError:
                pass
        raise
    finally:
        if backend is not None:
            backend.close()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan-dir", type=Path, required=True)
    parser.add_argument("--volume-root", type=Path, required=True)
    parser.add_argument("--volume-id", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--model-snapshot", type=Path, required=True)
    parser.add_argument("--sae-path", type=Path, required=True)
    parser.add_argument("--j-lens-path", type=Path, required=True)
    parser.add_argument("--ownership-receipt", type=Path, required=True)
    parser.add_argument("--guest-receipt", type=Path, required=True)
    parser.add_argument("--cache-receipt", type=Path, required=True)
    parser.add_argument("--authorization-receipt", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    print(
        execute(
            plan_dir=args.plan_dir,
            volume_root=args.volume_root,
            volume_id=args.volume_id,
            run_id=args.run_id,
            model_snapshot=args.model_snapshot,
            sae_path=args.sae_path,
            j_lens_path=args.j_lens_path,
            ownership_receipt_path=args.ownership_receipt,
            guest_receipt_path=args.guest_receipt,
            cache_receipt_path=args.cache_receipt,
            authorization_receipt_path=args.authorization_receipt,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

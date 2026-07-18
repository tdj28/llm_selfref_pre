#!/usr/bin/env python3
"""Independent structural audit for a completed realization-validation run."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from experiments.consciousness_sae_realization_validation import (  # noqa: E402
    controls,
    j_orientation,
    preexecution,
    protocol,
    runpod_preflight,
    runner,
    runtime,
)


class AuditError(RuntimeError):
    pass


def _json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise AuditError(f"JSON root is not an object: {path}")
    return value


def _jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            try:
                value = json.loads(line)
            except json.JSONDecodeError as exc:
                raise AuditError(f"invalid JSONL at {path}:{line_number}") from exc
            if not isinstance(value, dict):
                raise AuditError(f"non-object JSONL row at {path}:{line_number}")
            rows.append(value)
    return rows


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


def _tensor_inventory(path: Path) -> dict[str, dict[str, Any]]:
    try:
        from safetensors import safe_open
    except ImportError as exc:
        raise AuditError("safetensors is required for structural audit") from exc
    inventory: dict[str, dict[str, Any]] = {}
    with safe_open(str(path), framework="pt", device="cpu") as handle:
        for name in handle.keys():
            tensor = handle.get_tensor(name)
            inventory[name] = {
                "shape": list(tensor.shape),
                "dtype": str(tensor.dtype),
                "finite": bool(tensor.isfinite().all()) if tensor.is_floating_point() else True,
            }
    return inventory


def _audit_tensor_sha256(value: Any) -> str:
    """Independently hash an archived tensor's type, shape, and exact bytes."""

    try:
        import torch
    except ImportError as exc:
        raise AuditError("torch is required for tensor telemetry audit") from exc
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


def _audit_tensor_rms(value: Any) -> float:
    result = float(value.detach().float().square().mean().sqrt().item())
    if not math.isfinite(result) or result <= 0.0:
        raise AuditError("archived tensor RMS is non-finite or non-positive")
    return result


def _audit_relative_rmse(observed: Any, expected: Any) -> float:
    left = observed.detach().float().reshape(-1)
    right = expected.detach().float().reshape(-1)
    if left.shape != right.shape or left.numel() == 0:
        raise AuditError("archived telemetry tensor shapes differ")
    denominator = right.square().mean().sqrt()
    if float(denominator.item()) <= 0.0:
        raise AuditError("archived telemetry reference RMS is zero")
    result = float(((left - right).square().mean().sqrt() / denominator).item())
    if not math.isfinite(result):
        raise AuditError("recomputed relative RMSE is non-finite")
    return result


def _audit_cosine(left: Any, right: Any) -> float:
    first = left.detach().float().reshape(-1)
    second = right.detach().float().reshape(-1)
    if first.shape != second.shape or first.numel() == 0:
        raise AuditError("archived cosine tensor shapes differ")
    denominator = first.norm() * second.norm()
    if float(denominator.item()) <= 0.0:
        raise AuditError("archived cosine tensor norm is zero")
    result = float(first.dot(second).item() / denominator.item())
    if not math.isfinite(result):
        raise AuditError("recomputed cosine is non-finite")
    return max(-1.0, min(1.0, result))


def _audit_pearson(left: Any, right: Any) -> float:
    first = left.detach().float().reshape(-1)
    second = right.detach().float().reshape(-1)
    if first.shape != second.shape or first.numel() < 2:
        raise AuditError("archived Pearson tensor shapes differ")
    first = first - first.mean()
    second = second - second.mean()
    denominator = first.norm() * second.norm()
    if float(denominator.item()) <= 0.0:
        raise AuditError("archived Pearson tensor norm is zero")
    result = float(first.dot(second).item() / denominator.item())
    if not math.isfinite(result):
        raise AuditError("recomputed Pearson correlation is non-finite")
    return max(-1.0, min(1.0, result))


def _require_stage_a_row_match(
    reported: Mapping[str, Any],
    recomputed: Mapping[str, Any],
    *,
    numeric_fields: Sequence[str],
    label: str,
) -> None:
    """Reject a JSON metric row that disagrees with its archived raw inputs."""

    if set(reported) != set(recomputed):
        raise AuditError(f"{label} field inventory differs")
    numeric = set(numeric_fields)
    for field, expected in recomputed.items():
        observed = reported[field]
        if field in numeric:
            if (
                isinstance(observed, bool)
                or not isinstance(observed, (int, float))
                or not math.isclose(
                    float(observed), float(expected), rel_tol=2e-5, abs_tol=2e-7
                )
            ):
                raise AuditError(f"{label} numeric telemetry differs: {field}")
        elif observed != expected:
            raise AuditError(f"{label} exact telemetry differs: {field}")


def _require_exact_tensor(observed: Any, expected: Any, *, label: str) -> None:
    try:
        import torch
    except ImportError as exc:
        raise AuditError("torch is required for tensor telemetry audit") from exc
    if (
        observed.dtype != expected.dtype
        or tuple(observed.shape) != tuple(expected.shape)
        or not torch.equal(observed, expected)
    ):
        raise AuditError(f"Stage A archived arithmetic differs: {label}")


def _recompute_stage_a_pair_telemetry(
    *,
    clean_states: Any,
    plus_states: Any,
    minus_states: Any,
    edit_layer: int,
    arithmetic: Mapping[str, Any],
    arithmetic_row: int,
) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]], tuple[Any, Any, Any, float]]:
    """Rebuild one paired Stage-A edit from archived residual/vector tensors.

    This intentionally accepts tensors of any residual width so the arithmetic
    can be covered by small adversarial CPU fixtures.  The on-disk inventory
    check separately enforces the frozen production width and row counts.
    """

    try:
        import torch
    except ImportError as exc:
        raise AuditError("torch is required for Stage A telemetry audit") from exc
    layer_index = {layer: index for index, layer in enumerate(protocol.J_LAYERS)}
    if edit_layer not in layer_index:
        raise AuditError("Stage A edit layer is outside the J-layer inventory")
    source_index = layer_index[edit_layer]
    post_index = len(protocol.J_LAYERS)
    final_index = post_index + 1
    if (
        clean_states.ndim != 2
        or plus_states.ndim != 2
        or minus_states.ndim != 2
        or clean_states.shape[0] != len(protocol.J_LAYERS) + 1
        or plus_states.shape[0] != protocol.STAGE_A_CAPTURE_COUNT
        or minus_states.shape != plus_states.shape
        or clean_states.shape[1] != plus_states.shape[1]
    ):
        raise AuditError("Stage A archived residual state shape differs")

    clean_source = clean_states[source_index]
    plus_pre = plus_states[source_index]
    minus_pre = minus_states[source_index]
    plus_post = plus_states[post_index]
    minus_post = minus_states[post_index]
    plus_final = plus_states[final_index]
    minus_final = minus_states[final_index]
    requested_fp32 = arithmetic["requested_fp32_positive"][arithmetic_row]
    requested = arithmetic["requested_bfloat16_positive"][arithmetic_row]
    negative = torch.neg(requested).contiguous()
    realized_plus = plus_post.float() - plus_pre.float()
    realized_minus = minus_post.float() - minus_pre.float()
    central = (plus_post.float() - minus_post.float()) * 0.5
    common = (plus_post.float() + minus_post.float()) * 0.5 - clean_source.float()
    final_central = (plus_final.float() - minus_final.float()) * 0.5
    bf16_j = arithmetic["bf16_j_prediction_bfloat16"][arithmetic_row]
    fp32_j = arithmetic["fp32_j_prediction_fp32"][arithmetic_row]
    transport_predictions = arithmetic["transport_predicted_bfloat16"][
        arithmetic_row
    ]
    actual_logit_delta = arithmetic["actual_selected_logit_delta_fp32"][
        arithmetic_row
    ]
    predicted_logit_deltas = arithmetic[
        "transport_predicted_selected_logit_delta_fp32"
    ][arithmetic_row]

    _require_exact_tensor(
        requested, requested_fp32.to(dtype=torch.bfloat16), label="FP32-to-BF16 request"
    )
    _require_exact_tensor(
        arithmetic["realized_plus_fp32"][arithmetic_row],
        realized_plus,
        label="realized plus",
    )
    _require_exact_tensor(
        arithmetic["realized_minus_fp32"][arithmetic_row],
        realized_minus,
        label="realized minus",
    )
    _require_exact_tensor(
        arithmetic["realized_central_fp32"][arithmetic_row],
        central,
        label="realized central",
    )
    _require_exact_tensor(
        arithmetic["common_mode_fp32"][arithmetic_row], common, label="common mode"
    )
    _require_exact_tensor(
        arithmetic["final_central_fp32"][arithmetic_row],
        final_central,
        label="final central",
    )
    real_j_index = protocol.TRANSPORTS.index("real_j")
    identity_index = protocol.TRANSPORTS.index("identity")
    _require_exact_tensor(
        transport_predictions[real_j_index], bf16_j, label="real-J prediction"
    )
    _require_exact_tensor(
        transport_predictions[identity_index],
        central.to(dtype=torch.bfloat16),
        label="identity prediction",
    )

    clean_rms = _audit_tensor_rms(clean_source)
    central_rms = _audit_tensor_rms(central)
    common_rms = float(common.float().square().mean().sqrt().item())
    upstream_indices = [
        index for index, layer in enumerate(protocol.J_LAYERS) if layer < edit_layer
    ]
    pre_plus_equal = bool(torch.equal(plus_pre, clean_source))
    pre_minus_equal = bool(torch.equal(minus_pre, clean_source))
    plus_native = (plus_pre + requested).to(dtype=torch.bfloat16)
    minus_native = (minus_pre + negative).to(dtype=torch.bfloat16)
    upstream_plus_equal = all(
        torch.equal(plus_states[index], clean_states[index])
        for index in upstream_indices
    )
    upstream_minus_equal = all(
        torch.equal(minus_states[index], clean_states[index])
        for index in upstream_indices
    )
    finite = bool(
        torch.isfinite(realized_plus).all()
        and torch.isfinite(realized_minus).all()
        and torch.isfinite(common).all()
        and torch.isfinite(bf16_j).all()
        and torch.isfinite(fp32_j).all()
    )
    realization = {
        "hook_fire_count_plus": 1,
        "hook_fire_count_minus": 1,
        "pre_equals_clean_plus": pre_plus_equal,
        "pre_equals_clean_minus": pre_minus_equal,
        "native_post_bytes_exact_plus": bool(torch.equal(plus_post, plus_native)),
        "native_post_bytes_exact_minus": bool(torch.equal(minus_post, minus_native)),
        "upstream_bytes_equal_clean_plus": upstream_plus_equal,
        "upstream_bytes_equal_clean_minus": upstream_minus_equal,
        "requested_vector_sha256": _audit_tensor_sha256(requested),
        "realized_central_sha256": _audit_tensor_sha256(central),
        "requested_plus_realized_relative_rmse": _audit_relative_rmse(
            realized_plus, requested
        ),
        "requested_minus_realized_relative_rmse": _audit_relative_rmse(
            realized_minus, negative
        ),
        "requested_realized_central_relative_rmse": _audit_relative_rmse(
            central, requested
        ),
        "requested_realized_central_cosine": _audit_cosine(central, requested),
        "common_mode_to_central_rms": common_rms / central_rms,
        "requested_rms_fraction": _audit_tensor_rms(requested) / clean_rms,
        "realized_rms_fraction": central_rms / clean_rms,
        "bf16_fp32_j_cosine": _audit_cosine(bf16_j, fp32_j),
        "bf16_fp32_j_relative_rmse": _audit_relative_rmse(bf16_j, fp32_j),
        "fp32_j_actual_final_cosine": _audit_cosine(final_central, fp32_j),
        "finite": finite,
        "target_prompt_used": False,
    }
    shadow = {
        "j_map_shadow_dtype": "float32",
        "arithmetic_shadow_dtype": "float32",
        "realized_central_source_sha256": _audit_tensor_sha256(central),
        "bf16_j_prediction_sha256": _audit_tensor_sha256(bf16_j),
        "fp32_j_prediction_sha256": _audit_tensor_sha256(fp32_j),
        "bf16_fp32_j_cosine": realization["bf16_fp32_j_cosine"],
        "bf16_fp32_j_relative_rmse": realization["bf16_fp32_j_relative_rmse"],
        "fp32_j_actual_final_cosine": realization["fp32_j_actual_final_cosine"],
        "finite": finite,
        "target_prompt_used": False,
        "target_outcome_count": 0,
    }
    transports = [
        {
            "transport": transport,
            "residual_delta_cosine": _audit_cosine(
                final_central, transport_predictions[index]
            ),
            "fixed_token_logit_delta_pearson": _audit_pearson(
                actual_logit_delta, predicted_logit_deltas[index]
            ),
            "finite": bool(
                torch.isfinite(transport_predictions[index]).all()
                and torch.isfinite(predicted_logit_deltas[index]).all()
            ),
            "target_prompt_used": False,
        }
        for index, transport in enumerate(protocol.TRANSPORTS)
    ]
    return (
        realization,
        shadow,
        transports,
        (
            central,
            bf16_j.float(),
            final_central,
            float(realization["realized_rms_fraction"]),
        ),
    )


def _recompute_stage_a_linearity_row(
    dose_vectors: Mapping[float, tuple[Any, Any, Any, float]],
) -> dict[str, Any]:
    if set(dose_vectors) != set(protocol.DOSE_GRID):
        raise AuditError("Stage A raw dose-vector grid differs")
    anchor = dose_vectors[protocol.PRIMARY_DOSE]
    anchor_slopes = tuple(value / anchor[3] for value in anchor[:3])
    cosine_values: list[list[float]] = [[], [], []]
    discrepancy_values: list[list[float]] = [[], [], []]
    for dose in protocol.LINEARITY_GATE_DOSES:
        observed = dose_vectors[dose]
        for index, (value, anchor_slope) in enumerate(
            zip(observed[:3], anchor_slopes, strict=True)
        ):
            observed_slope = value / observed[3]
            cosine_values[index].append(
                _audit_cosine(observed_slope, anchor_slope)
            )
            discrepancy_values[index].append(
                _audit_relative_rmse(observed_slope, anchor_slope)
            )
    return {
        "dose_unit": controls.DOSE_UNIT,
        "gate_doses": list(protocol.LINEARITY_GATE_DOSES),
        "realized_source_linearity_cosine_min": min(cosine_values[0]),
        "realized_source_slope_discrepancy_max": max(discrepancy_values[0]),
        "j_of_realized_linearity_cosine_min": min(cosine_values[1]),
        "j_of_realized_slope_discrepancy_max": max(discrepancy_values[1]),
        "actual_final_linearity_cosine_min": min(cosine_values[2]),
        "actual_final_slope_discrepancy_max": max(discrepancy_values[2]),
        "finite": True,
        "target_prompt_used": False,
    }


def _recompute_stage_b_edit_telemetry(
    run_root: Path,
    *,
    branch_rows: Sequence[Mapping[str, Any]],
    edit_rows: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Rebuild all request/realization metrics from the archived tensors."""

    try:
        import torch
        from safetensors.torch import load_file
    except ImportError as exc:
        raise AuditError("torch and safetensors are required for telemetry audit") from exc
    branch_by_key = {
        (
            row["prompt_id"],
            row["assignment_id"],
            row["vector_class"],
            int(row["sign"]),
            float(row["multiplier"]),
        ): row
        for row in branch_rows
        if row.get("condition") == "edited"
    }
    recomputed_rows: list[dict[str, Any]] = []
    metric_fields = (
        "requested_realized_relative_rmse",
        "requested_realized_cosine",
        "requested_rms_fraction",
        "realized_rms_fraction",
        "fp32_requested_to_bfloat16_relative_rmse",
        "fp32_requested_to_bfloat16_cosine",
        "native_realized_to_fp32_requested_relative_rmse",
        "native_realized_to_fp32_requested_cosine",
    )
    state_index = list(protocol.STAGE_B_CAPTURE_STATES).index("50_pre")
    post_index = list(protocol.STAGE_B_CAPTURE_STATES).index("50_post")
    for prompt_id in protocol.STAGE_B_PROMPT_IDS:
        arithmetic = load_file(
            str(run_root / "arithmetic" / f"{prompt_id}.safetensors"),
            device="cpu",
        )
        residuals = load_file(
            str(run_root / "residuals" / f"{prompt_id}.safetensors"),
            device="cpu",
        )["residuals"]
        clean_source = residuals[0, state_index]
        clean_rms = _audit_tensor_rms(clean_source)
        for row in (candidate for candidate in edit_rows if candidate["prompt_id"] == prompt_id):
            key = (
                row["prompt_id"],
                row["assignment_id"],
                row["vector_class"],
                int(row["sign"]),
                float(row["multiplier"]),
            )
            branch = branch_by_key.get(key)
            if branch is None:
                raise AuditError(f"Stage B telemetry has no branch join: {key}")
            shard_row = int(branch["shard_row"])
            arithmetic_row = shard_row - 1
            if not 0 <= arithmetic_row < 270:
                raise AuditError(f"Stage B arithmetic row join differs: {key}")
            requested_fp32 = arithmetic["requested_fp32"][arithmetic_row]
            requested_bfloat16 = arithmetic["requested_bfloat16"][arithmetic_row]
            realized_fp32 = arithmetic["realized_fp32"][arithmetic_row]
            branch_pre = residuals[shard_row, state_index]
            branch_post = residuals[shard_row, post_index]
            reconstructed_realized = branch_post.float() - branch_pre.float()
            if (
                not torch.equal(branch_pre, clean_source)
                or not torch.equal(residuals[shard_row, :5], residuals[0, :5])
                or not torch.equal(realized_fp32, reconstructed_realized)
                or not torch.equal(
                    branch_post,
                    (branch_pre + requested_bfloat16).to(dtype=torch.bfloat16),
                )
                or not torch.equal(
                    requested_bfloat16,
                    requested_fp32.to(dtype=torch.bfloat16),
                )
            ):
                raise AuditError(f"Stage B archived edit arithmetic differs: {key}")
            recomputed = {
                "requested_realized_relative_rmse": _audit_relative_rmse(
                    realized_fp32, requested_bfloat16
                ),
                "requested_realized_cosine": _audit_cosine(
                    realized_fp32, requested_bfloat16
                ),
                "requested_rms_fraction": (
                    _audit_tensor_rms(requested_bfloat16) / clean_rms
                ),
                "realized_rms_fraction": _audit_tensor_rms(realized_fp32) / clean_rms,
                "fp32_requested_to_bfloat16_relative_rmse": _audit_relative_rmse(
                    requested_bfloat16, requested_fp32
                ),
                "fp32_requested_to_bfloat16_cosine": _audit_cosine(
                    requested_bfloat16, requested_fp32
                ),
                "native_realized_to_fp32_requested_relative_rmse": _audit_relative_rmse(
                    realized_fp32, requested_fp32
                ),
                "native_realized_to_fp32_requested_cosine": _audit_cosine(
                    realized_fp32, requested_fp32
                ),
            }
            if any(
                not math.isclose(
                    float(row[field]), recomputed[field], rel_tol=2e-5, abs_tol=2e-7
                )
                for field in metric_fields
            ):
                raise AuditError(f"Stage B JSON/tensor telemetry differs: {key}")
            hashes = {
                "requested_vector_sha256": _audit_tensor_sha256(requested_bfloat16),
                "requested_fp32_vector_sha256": _audit_tensor_sha256(requested_fp32),
                "realized_vector_sha256": _audit_tensor_sha256(realized_fp32),
            }
            if any(row[field] != digest for field, digest in hashes.items()):
                raise AuditError(f"Stage B JSON/tensor vector hash differs: {key}")
            recomputed_rows.append({**dict(row), **recomputed, **hashes})
        del arithmetic, residuals
    try:
        return controls.validate_stage_b_edit_rows(recomputed_rows)
    except controls.ControlViolation as exc:
        raise AuditError(str(exc)) from exc


def _validate_topk_content(path: Path) -> None:
    try:
        from safetensors import safe_open
    except ImportError as exc:
        raise AuditError("safetensors is required for top-k audit") from exc
    pairs = (
        ("absolute_top_token_ids", "absolute_top_scores", True),
        ("branch_vs_clean_top_token_ids", "branch_vs_clean_top_scores", True),
        ("branch_vs_clean_bottom_token_ids", "branch_vs_clean_bottom_scores", False),
        ("paired_central_top_token_ids", "paired_central_top_scores", True),
        ("paired_central_bottom_token_ids", "paired_central_bottom_scores", False),
    )
    with safe_open(str(path), framework="pt", device="cpu") as handle:
        for ids_name, scores_name, descending in pairs:
            ids = handle.get_tensor(ids_name)
            scores = handle.get_tensor(scores_name)
            if int(ids.min()) < 0 or int(ids.max()) >= protocol.VOCAB_SIZE:
                raise AuditError(f"top-k token ID is outside vocabulary: {ids_name}")
            differences = scores[..., 1:] - scores[..., :-1]
            if descending:
                sorted_ok = bool((differences <= 0).all())
            else:
                sorted_ok = bool((differences >= 0).all())
            if not sorted_ok:
                raise AuditError(f"top-k scores are not stably ordered: {scores_name}")
            ties = differences == 0
            if bool(ties.any()) and not bool(
                ((ids[..., 1:] > ids[..., :-1]) | ~ties).all()
            ):
                raise AuditError(f"top-k token-ID tie order differs: {ids_name}")
            sorted_ids = ids.sort(dim=-1).values
            if not bool((sorted_ids[..., 1:] > sorted_ids[..., :-1]).all()):
                raise AuditError(f"top-k row contains duplicate token IDs: {ids_name}")


def _validate_manifest(
    run_root: Path,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    complete = _json(run_root / "RUN_COMPLETE.json")
    core = dict(complete)
    supplied = core.pop("receipt_sha256", None)
    if supplied != protocol.canonical_sha256(core):
        raise AuditError("RUN_COMPLETE self-hash differs")
    if (
        complete.get("status") != "complete"
        or complete.get("study_id") != protocol.STUDY_ID
        or complete.get("protocol_version") != protocol.PROTOCOL_VERSION
    ):
        raise AuditError("run identity/status differs")
    records = complete.get("records")
    if not isinstance(records, list):
        raise AuditError("run record inventory is missing")
    recorded: list[str] = []
    for row in records:
        if not isinstance(row, Mapping):
            raise AuditError("run manifest record is not an object")
        relative = str(row.get("path"))
        path = run_root / relative
        if (
            not path.is_file()
            or path.is_symlink()
            or path.stat().st_size != int(row.get("bytes", -1))
            or protocol.sha256_file(path) != row.get("sha256")
        ):
            raise AuditError(f"manifested file differs: {relative}")
        recorded.append(relative)
    observed = sorted(
        path.relative_to(run_root).as_posix()
        for path in run_root.rglob("*")
        if path.is_file()
    )
    expected = sorted([*recorded, "RUN_COMPLETE.json"])
    if observed != expected:
        raise AuditError("run contains missing or unmanifested files")
    if len(recorded) != len(set(recorded)):
        raise AuditError("run manifest contains duplicate file paths")
    # Stage-specific audit code needs each manifested role as well as the path;
    # returning only ``recorded`` here made the Stage-A role join unreachable.
    return complete, [dict(row) for row in records]


def _audit_prompt_receipts(run_root: Path, *, stage: str) -> int:
    rows = _jsonl(run_root / "prompt_receipts.jsonl")
    expected_ids = (
        protocol.STAGE_A_PROMPT_IDS if stage == "stage_a" else protocol.STAGE_B_PROMPT_IDS
    )
    if tuple(row.get("prompt_id") for row in rows) != expected_ids:
        raise AuditError("neutral prompt receipt inventory/order differs")
    for row in rows:
        prompt_id = str(row["prompt_id"])
        token_ids = row.get("token_ids")
        if (
            row.get("prompt_payload_sha256")
            != protocol.canonical_sha256(protocol.prompt_payload(prompt_id))
            or not isinstance(token_ids, list)
            or len(token_ids) != row.get("token_count")
            or any(
                isinstance(value, bool)
                or not isinstance(value, int)
                or value < 0
                or value >= protocol.VOCAB_SIZE
                for value in token_ids
            )
            or row.get("token_ids_sha256")
            != protocol.canonical_sha256(token_ids)
        ):
            raise AuditError(f"prompt/token binding differs: {prompt_id}")
    return len(rows)


def _audit_resource(complete: Mapping[str, Any]) -> None:
    resource = complete.get("resource")
    runtime = complete.get("runtime")
    if not isinstance(resource, Mapping) or not isinstance(runtime, Mapping):
        raise AuditError("run resource/runtime receipt is missing")
    elapsed = float(resource.get("cumulative_elapsed_seconds", math.nan))
    spend = float(resource.get("cumulative_estimated_spend_usd", math.nan))
    if (
        not math.isfinite(elapsed)
        or not math.isfinite(spend)
        or elapsed < 0
        or elapsed >= protocol.RESOURCE_LIMITS["max_walltime_seconds"]
        or spend < 0
        or spend >= protocol.RESOURCE_LIMITS["max_spend_usd"]
    ):
        raise AuditError("cumulative resource ceiling differs")
    expected_forwards = 2320 if complete.get("stage") == "stage_a" else 2200
    if runtime.get("model_forward_count") != expected_forwards:
        raise AuditError("exact model-forward count differs")


def _audit_execution_binding(
    run_root: Path,
    *,
    complete: Mapping[str, Any],
    stage_a_receipt: Mapping[str, Any] | None = None,
    stage_a_audit: Mapping[str, Any] | None = None,
    target_blind_receipt: Mapping[str, Any] | None = None,
    storage_budget: Mapping[str, Any] | None = None,
    stage_b_permit: Mapping[str, Any] | None = None,
    preexecution_authorization: Mapping[str, Any] | None = None,
    smoke_receipt: Mapping[str, Any] | None = None,
    smoke_receipt_file_sha256: str | None = None,
) -> dict[str, str]:
    binding = _json(run_root / "execution_binding.json")
    if (
        binding.get("study_id") != protocol.STUDY_ID
        or binding.get("protocol_version") != protocol.PROTOCOL_VERSION
        or binding.get("stage") != complete.get("stage")
        or binding.get("plan_manifest_sha256")
        != complete.get("plan_manifest_sha256")
        or binding.get("model_revision") != protocol.MODEL_SPEC["revision"]
        or binding.get("container_image") != protocol.CONTAINER_IMAGE_SPEC
        or binding.get("prior_outcome_inputs") != []
    ):
        raise AuditError("execution binding identity differs")
    artifacts = binding.get("artifacts")
    if not isinstance(artifacts, Mapping) or set(artifacts) != {"sae", "j_lens"}:
        raise AuditError("execution artifact binding differs")
    if (
        artifacts["sae"].get("sha256") != protocol.SAE_SPEC["sha256"]
        or artifacts["j_lens"].get("sha256") != protocol.J_LENS_SPEC["sha256"]
    ):
        raise AuditError("execution artifact hash differs")
    if complete.get("stage") == "stage_b":
        if any(
            value is None
            for value in (
                stage_a_receipt,
                stage_a_audit,
                target_blind_receipt,
                storage_budget,
                stage_b_permit,
                preexecution_authorization,
            )
        ):
            raise AuditError("Stage B audit requires the complete permit chain")
        assert stage_a_receipt is not None
        assert stage_a_audit is not None
        assert target_blind_receipt is not None
        assert storage_budget is not None
        assert stage_b_permit is not None
        assert preexecution_authorization is not None
        try:
            controls.validate_stage_b_permit(
                stage_b_permit,
                stage_a_receipt=stage_a_receipt,
                target_blind_receipt=target_blind_receipt,
                storage_budget=storage_budget,
            )
        except controls.ControlViolation as exc:
            raise AuditError(str(exc)) from exc
        expected_hashes = {
            "stage_a_receipt_sha256": stage_a_receipt["receipt_sha256"],
            "stage_a_audit_receipt_sha256": stage_a_audit["receipt_sha256"],
            "stage_b_permit_sha256": stage_b_permit["receipt_sha256"],
            "target_blind_receipt_sha256": target_blind_receipt["receipt_sha256"],
            "storage_budget_receipt_sha256": storage_budget["receipt_sha256"],
            "preexecution_authorization_sha256": preexecution_authorization[
                "receipt_sha256"
            ],
        }
        if (
            any(
                binding.get(field) != digest
                for field, digest in expected_hashes.items()
            )
            or binding.get("campaign_identity_sha256")
            != preexecution_authorization.get("campaign_identity_sha256")
            or stage_a_receipt.get("preexecution_authorization_sha256")
            != preexecution_authorization.get("receipt_sha256")
            or stage_a_receipt.get("campaign_identity_sha256")
            != preexecution_authorization.get("campaign_identity_sha256")
        ):
            raise AuditError("Stage B execution/permit receipt binding differs")
        audit_core = dict(stage_a_audit)
        audit_hash = audit_core.pop("receipt_sha256", None)
        if (
            audit_hash != protocol.canonical_sha256(audit_core)
            or stage_a_audit.get("status") != "pass"
            or stage_a_audit.get("stage") != "stage_a"
            or stage_a_audit.get("run_id") != stage_a_receipt.get("run_id")
            or stage_a_receipt.get("audit_receipt_sha256") != audit_hash
        ):
            raise AuditError("Stage A audit/analysis receipt binding differs")
        try:
            numeric_recomputation = controls.validate_stage_a_numeric_recomputation(
                stage_a_audit.get("details", {}).get(
                    "stage_a_numeric_recomputation", {}
                )
            )
        except controls.ControlViolation as exc:
            raise AuditError(str(exc)) from exc
        if (
            stage_a_receipt.get("stage_a_numeric_recomputation_sha256")
            != numeric_recomputation["classification_sha256"]
        ):
            raise AuditError("Stage A receipt/raw numeric audit binding differs")
        if any(
            value.get("plan_manifest_sha256") != complete.get("plan_manifest_sha256")
            for value in (
                stage_a_receipt,
                target_blind_receipt,
                storage_budget,
                stage_b_permit,
            )
        ):
            raise AuditError("Stage B receipt plan hashes differ")
        return expected_hashes
    if (
        storage_budget is None
        or preexecution_authorization is None
        or smoke_receipt is None
        or smoke_receipt_file_sha256 is None
    ):
        raise AuditError(
            "Stage A audit requires storage, preauthorization, and smoke receipts"
        )
    try:
        validated_budget = controls.validate_storage_budget(storage_budget)
    except controls.ControlViolation as exc:
        raise AuditError(str(exc)) from exc
    expected_hashes = {
        "storage_budget_receipt_sha256": validated_budget["receipt_sha256"],
        "preexecution_authorization_sha256": preexecution_authorization[
            "receipt_sha256"
        ],
        "smoke_receipt_sha256": smoke_receipt["receipt_sha256"],
        "smoke_receipt_file_sha256": smoke_receipt_file_sha256,
    }
    if (
        validated_budget["plan_manifest_sha256"]
        != complete.get("plan_manifest_sha256")
        or any(
            binding.get(field) != digest
            for field, digest in expected_hashes.items()
        )
        or binding.get("smoke_receipt_relative_path")
        != smoke_receipt.get("external_receipt_relative_path")
        or binding.get("campaign_identity_sha256")
        != preexecution_authorization.get("campaign_identity_sha256")
    ):
        raise AuditError("Stage A stop-ship execution binding differs")
    return expected_hashes


def _recompute_stage_a_numeric_telemetry(
    run_root: Path,
    *,
    branch_rows: Sequence[Mapping[str, Any]],
    arithmetic_index: Sequence[Mapping[str, Any]],
    clean_index: Sequence[Mapping[str, Any]],
    realization_rows: Sequence[Mapping[str, Any]],
    shadow_rows: Sequence[Mapping[str, Any]],
    transport_rows: Sequence[Mapping[str, Any]],
    linearity_rows: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Join Stage-A JSON to raw tensors and independently rebuild every metric."""

    try:
        from safetensors.torch import load_file
    except ImportError as exc:
        raise AuditError("safetensors is required for Stage A telemetry audit") from exc

    pair_specs = list(protocol.stage_a_rows())
    pair_keys = [
        (
            row["prompt_id"],
            int(row["edit_layer"]),
            int(row["direction"]),
            float(row["dose_fraction"]),
        )
        for row in pair_specs
    ]
    transport_keys = [
        (*key, transport) for key in pair_keys for transport in protocol.TRANSPORTS
    ]
    linearity_keys = [
        (prompt_id, layer, direction)
        for prompt_id in protocol.STAGE_A_PROMPT_IDS
        for layer in protocol.STAGE_A_LAYERS
        for direction in protocol.STAGE_A_DIRECTIONS
    ]

    def pair_key(row: Mapping[str, Any]) -> tuple[str, int, int, float]:
        return (
            str(row.get("prompt_id")),
            int(row.get("edit_layer", -1)),
            int(row.get("direction", -1)),
            float(row.get("dose_fraction", math.nan)),
        )

    if [pair_key(row) for row in realization_rows] != pair_keys:
        raise AuditError("Stage A realization row order differs")
    if [pair_key(row) for row in shadow_rows] != pair_keys:
        raise AuditError("Stage A J-shadow row order differs")
    if [(*pair_key(row), str(row.get("transport"))) for row in transport_rows] != transport_keys:
        raise AuditError("Stage A transport row order differs")
    if [
        (
            str(row.get("prompt_id")),
            int(row.get("edit_layer", -1)),
            int(row.get("direction", -1)),
        )
        for row in linearity_rows
    ] != linearity_keys:
        raise AuditError("Stage A linearity row order differs")

    clean_labels = [*(str(layer) for layer in protocol.J_LAYERS), "final"]
    if len(clean_index) != len(protocol.STAGE_A_PROMPT_IDS):
        raise AuditError("Stage A clean index count differs")
    for row_index, (prompt_id, row) in enumerate(
        zip(protocol.STAGE_A_PROMPT_IDS, clean_index, strict=True)
    ):
        if (
            set(row) != {"row_index", "prompt_id", "token_ids_sha256", "state_labels"}
            or row.get("row_index") != row_index
            or row.get("prompt_id") != prompt_id
            or row.get("state_labels") != clean_labels
            or not isinstance(row.get("token_ids_sha256"), str)
            or len(row["token_ids_sha256"]) != 64
        ):
            raise AuditError(f"Stage A clean index differs: {prompt_id}")

    branch_labels = [
        *(str(layer) for layer in protocol.J_LAYERS),
        "edit_post",
        "final",
    ]
    expected_branch_count = len(pair_keys) * 2
    if len(branch_rows) != expected_branch_count or len(arithmetic_index) != len(pair_keys):
        raise AuditError("Stage A raw tensor index count differs")
    local_pair_rows = len(pair_keys) // len(protocol.STAGE_A_PROMPT_IDS)
    for global_pair_row, key in enumerate(pair_keys):
        prompt_id, edit_layer, direction, dose = key
        prompt_offset = protocol.STAGE_A_PROMPT_IDS.index(prompt_id)
        local_pair_row = global_pair_row - prompt_offset * local_pair_rows
        base = {
            "prompt_id": prompt_id,
            "edit_layer": edit_layer,
            "direction": direction,
            "dose_fraction": dose,
            "target_prompt_used": False,
        }
        for sign_offset, sign in enumerate((1, -1)):
            expected_branch = {
                **base,
                "sign": sign,
                "shard": f"residuals/{prompt_id}.safetensors",
                "shard_row": local_pair_row * 2 + sign_offset,
                "state_labels": branch_labels,
            }
            if dict(branch_rows[global_pair_row * 2 + sign_offset]) != expected_branch:
                raise AuditError(f"Stage A branch/raw tensor join differs: {key}/{sign}")
        expected_arithmetic = {
            **base,
            "tensor_row": local_pair_row,
            "shard": f"arithmetic/{prompt_id}.safetensors",
        }
        if dict(arithmetic_index[global_pair_row]) != expected_arithmetic:
            raise AuditError(f"Stage A arithmetic/raw tensor join differs: {key}")

    realization_numeric = (
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
    )
    shadow_numeric = (
        "bf16_fp32_j_cosine",
        "bf16_fp32_j_relative_rmse",
        "fp32_j_actual_final_cosine",
    )
    transport_numeric = (
        "residual_delta_cosine",
        "fixed_token_logit_delta_pearson",
    )
    linearity_numeric = (
        "realized_source_linearity_cosine_min",
        "realized_source_slope_discrepancy_max",
        "j_of_realized_linearity_cosine_min",
        "j_of_realized_slope_discrepancy_max",
        "actual_final_linearity_cosine_min",
        "actual_final_slope_discrepancy_max",
    )
    recomputed_realization: list[dict[str, Any]] = []
    recomputed_shadows: list[dict[str, Any]] = []
    recomputed_transport: list[dict[str, Any]] = []
    recomputed_linearity: list[dict[str, Any]] = []
    clean = load_file(str(run_root / "residuals" / "clean.safetensors"), device="cpu")[
        "residuals"
    ]
    pair_cursor = 0
    transport_cursor = 0
    linearity_cursor = 0
    for clean_row, prompt_id in enumerate(protocol.STAGE_A_PROMPT_IDS):
        residuals = load_file(
            str(run_root / "residuals" / f"{prompt_id}.safetensors"), device="cpu"
        )["residuals"]
        arithmetic = load_file(
            str(run_root / "arithmetic" / f"{prompt_id}.safetensors"), device="cpu"
        )
        dose_vectors: dict[
            tuple[int, int], dict[float, tuple[Any, Any, Any, float]]
        ] = {}
        for local_pair_row in range(local_pair_rows):
            spec = pair_specs[pair_cursor]
            key = pair_keys[pair_cursor]
            edit_layer = int(spec["edit_layer"])
            direction = int(spec["direction"])
            dose = float(spec["dose_fraction"])
            base = {
                "prompt_id": prompt_id,
                "edit_layer": edit_layer,
                "direction": direction,
                "dose_fraction": dose,
            }
            realized, shadow, transports, vectors = _recompute_stage_a_pair_telemetry(
                clean_states=clean[clean_row],
                plus_states=residuals[local_pair_row * 2],
                minus_states=residuals[local_pair_row * 2 + 1],
                edit_layer=edit_layer,
                arithmetic=arithmetic,
                arithmetic_row=local_pair_row,
            )
            realized_row = {**base, **realized}
            shadow_row = {**base, **shadow}
            _require_stage_a_row_match(
                realization_rows[pair_cursor],
                realized_row,
                numeric_fields=realization_numeric,
                label=f"Stage A realization {key}",
            )
            _require_stage_a_row_match(
                shadow_rows[pair_cursor],
                shadow_row,
                numeric_fields=shadow_numeric,
                label=f"Stage A J-shadow {key}",
            )
            recomputed_realization.append(realized_row)
            recomputed_shadows.append(shadow_row)
            for transport_row in transports:
                full_transport = {**base, **transport_row}
                _require_stage_a_row_match(
                    transport_rows[transport_cursor],
                    full_transport,
                    numeric_fields=transport_numeric,
                    label=f"Stage A transport {key}/{transport_row['transport']}",
                )
                recomputed_transport.append(full_transport)
                transport_cursor += 1
            dose_vectors.setdefault((edit_layer, direction), {})[dose] = vectors
            pair_cursor += 1

        for edit_layer in protocol.STAGE_A_LAYERS:
            for direction in protocol.STAGE_A_DIRECTIONS:
                key = (prompt_id, edit_layer, direction)
                linearity_row = {
                    "prompt_id": prompt_id,
                    "edit_layer": edit_layer,
                    "direction": direction,
                    **_recompute_stage_a_linearity_row(
                        dose_vectors[(edit_layer, direction)]
                    ),
                }
                _require_stage_a_row_match(
                    linearity_rows[linearity_cursor],
                    linearity_row,
                    numeric_fields=linearity_numeric,
                    label=f"Stage A linearity {key}",
                )
                recomputed_linearity.append(linearity_row)
                linearity_cursor += 1
        del residuals, arithmetic, dose_vectors
    del clean

    if (
        pair_cursor != len(pair_keys)
        or transport_cursor != len(transport_keys)
        or linearity_cursor != len(linearity_keys)
    ):
        raise AuditError("Stage A recomputed telemetry cursor differs")
    try:
        edit_validation = controls.validate_edit_realization_rows(
            recomputed_realization
        )
        transport_validation = controls.validate_stage_a_transport_rows(
            recomputed_transport
        )
        linearity_validation = controls.validate_stage_a_linearity_rows(
            recomputed_linearity
        )
        return controls.build_stage_a_numeric_recomputation(
            edit_validation=edit_validation,
            transport_validation=transport_validation,
            linearity_validation=linearity_validation,
            telemetry_file_sha256s={
                relative: protocol.sha256_file(run_root / relative)
                for relative in controls.STAGE_A_NUMERIC_TELEMETRY_FILES
            },
            recomputed_row_inventory_sha256s={
                "realization_rows": protocol.canonical_sha256(
                    recomputed_realization
                ),
                "j_map_shadow_rows": protocol.canonical_sha256(
                    recomputed_shadows
                ),
                "transport_rows": protocol.canonical_sha256(recomputed_transport),
                "linearity_rows": protocol.canonical_sha256(recomputed_linearity),
            },
        )
    except controls.ControlViolation as exc:
        raise AuditError(str(exc)) from exc


def _audit_stage_a(
    run_root: Path,
    *,
    plan_manifest_sha256: str,
    records: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    branch = _jsonl(run_root / "branch_index.jsonl")
    clean_index = _jsonl(run_root / "clean_index.jsonl")
    expected = {
        (row["prompt_id"], row["edit_layer"], row["direction"], row["dose_fraction"], sign)
        for row in protocol.stage_a_rows()
        for sign in (-1, 1)
    }
    actual = {
        (
            row.get("prompt_id"),
            row.get("edit_layer"),
            row.get("direction"),
            row.get("dose_fraction"),
            row.get("sign"),
        )
        for row in branch
    }
    if actual != expected or len(branch) != len(expected):
        raise AuditError("Stage A branch grid differs")
    realization = _jsonl(run_root / "realization_rows.jsonl")
    transport = _jsonl(run_root / "transport_rows.jsonl")
    linearity = _jsonl(run_root / "linearity_rows.jsonl")
    orientation_rows_path = run_root / "j_orientation_rows.jsonl"
    orientation_receipt_path = run_root / "j_orientation_receipt.json"
    orientation_rows = _jsonl(orientation_rows_path)
    orientation_receipt = _json(orientation_receipt_path)
    role_by_path = {str(row["path"]): row.get("role") for row in records}
    if (
        role_by_path.get("j_orientation_rows.jsonl")
        != "j_arithmetic_orientation_rows"
        or role_by_path.get("j_orientation_receipt.json")
        != "j_arithmetic_orientation_receipt"
    ):
        raise AuditError("Stage A J-orientation manifest roles differ")
    try:
        orientation_validation = j_orientation.validate_orientation_receipt(
            orientation_receipt,
            rows=orientation_rows,
            plan_manifest_sha256=plan_manifest_sha256,
            require_pass=True,
        )
    except j_orientation.OrientationViolation as exc:
        raise AuditError(f"Stage A J-orientation gate failed: {exc}") from exc
    orientation_rows_hash = protocol.sha256_file(orientation_rows_path)
    if orientation_rows_hash != orientation_receipt["rows_file_sha256"]:
        raise AuditError("Stage A physical J-orientation rows hash differs")
    if orientation_receipt_path.read_bytes() != (
        protocol.canonical_json_bytes(orientation_receipt) + b"\n"
    ):
        raise AuditError("Stage A J-orientation receipt is not canonical JSON")
    shadows = _jsonl(run_root / "j_map_shadow_rows.jsonl")
    arithmetic_index = _jsonl(run_root / "arithmetic_index.jsonl")
    if (
        len(realization) != 1152
        or len(transport) != 8064
        or len(linearity) != 192
        or len(shadows) != 1152
        or len(arithmetic_index) != 1152
    ):
        raise AuditError("Stage A metric row count differs")
    if not all(
        _finite_json(row) for row in (*realization, *transport, *linearity, *shadows)
    ):
        raise AuditError("Stage A metadata contains non-finite values")
    clean = _tensor_inventory(run_root / "residuals" / "clean.safetensors")
    if clean != {
        "residuals": {"shape": [8, 35, protocol.WIDTH], "dtype": "torch.bfloat16", "finite": True}
    }:
        raise AuditError("Stage A clean residual tensor differs")
    fixed_panel = _json(run_root / "fixed_token_panel.json")
    expected_panel = list(runtime.fixed_token_panel())
    if fixed_panel != {
        "token_ids": expected_panel,
        "sha256": protocol.canonical_sha256(expected_panel),
    }:
        raise AuditError("Stage A fixed-token panel differs")
    tensor_count = 8 * 35
    for prompt_id in protocol.STAGE_A_PROMPT_IDS:
        inventory = _tensor_inventory(run_root / "residuals" / f"{prompt_id}.safetensors")
        expected_inventory = {
            "residuals": {
                "shape": [288, 36, protocol.WIDTH],
                "dtype": "torch.bfloat16",
                "finite": True,
            }
        }
        if inventory != expected_inventory:
            raise AuditError(f"Stage A residual shard differs: {prompt_id}")
        arithmetic = _tensor_inventory(
            run_root / "arithmetic" / f"{prompt_id}.safetensors"
        )
        expected_arithmetic = {
            "requested_fp32_positive": ([144, protocol.WIDTH], "torch.float32"),
            "requested_bfloat16_positive": ([144, protocol.WIDTH], "torch.bfloat16"),
            "realized_plus_fp32": ([144, protocol.WIDTH], "torch.float32"),
            "realized_minus_fp32": ([144, protocol.WIDTH], "torch.float32"),
            "realized_central_fp32": ([144, protocol.WIDTH], "torch.float32"),
            "common_mode_fp32": ([144, protocol.WIDTH], "torch.float32"),
            "final_central_fp32": ([144, protocol.WIDTH], "torch.float32"),
            "bf16_j_prediction_bfloat16": (
                [144, protocol.WIDTH],
                "torch.bfloat16",
            ),
            "fp32_j_prediction_fp32": ([144, protocol.WIDTH], "torch.float32"),
            "transport_predicted_bfloat16": (
                [144, len(protocol.TRANSPORTS), protocol.WIDTH],
                "torch.bfloat16",
            ),
            "actual_selected_logit_delta_fp32": ([144, 2048], "torch.float32"),
            "transport_predicted_selected_logit_delta_fp32": (
                [144, len(protocol.TRANSPORTS), 2048],
                "torch.float32",
            ),
        }
        if set(arithmetic) != set(expected_arithmetic):
            raise AuditError(f"Stage A arithmetic keys differ: {prompt_id}")
        for name, (shape, dtype) in expected_arithmetic.items():
            if arithmetic[name] != {
                "shape": shape,
                "dtype": dtype,
                "finite": True,
            }:
                raise AuditError(f"Stage A arithmetic tensor differs: {prompt_id}/{name}")
        tensor_count += 288 * 36
    numeric_recomputation = _recompute_stage_a_numeric_telemetry(
        run_root,
        branch_rows=branch,
        arithmetic_index=arithmetic_index,
        clean_index=clean_index,
        realization_rows=realization,
        shadow_rows=shadows,
        transport_rows=transport,
        linearity_rows=linearity,
    )
    return {
        "branch_row_count": len(branch),
        "realization_row_count": len(realization),
        "transport_row_count": len(transport),
        "linearity_row_count": len(linearity),
        "j_orientation_status": orientation_validation["status"],
        "j_orientation_row_count": orientation_validation["row_count"],
        "j_orientation_rows_sha256": orientation_rows_hash,
        "j_orientation_receipt_sha256": orientation_receipt["receipt_sha256"],
        "j_map_shadow_row_count": len(shadows),
        "arithmetic_pair_count": len(arithmetic_index),
        "residual_state_count": tensor_count,
        "stage_a_numeric_recomputation": numeric_recomputation,
    }


def _audit_stage_b(run_root: Path) -> dict[str, Any]:
    branch = _jsonl(run_root / "branch_index.jsonl")
    edited = [row for row in branch if row.get("condition") == "edited"]
    clean = [row for row in branch if row.get("condition") == "clean"]
    expected = {
        (
            row["prompt_id"], row["assignment_id"], row["vector_class"],
            row["sign"], row["multiplier"],
        )
        for row in protocol.stage_b_rows()
    }
    actual = {
        (
            row.get("prompt_id"), row.get("assignment_id"), row.get("vector_class"),
            row.get("sign"), row.get("multiplier"),
        )
        for row in edited
    }
    if actual != expected or len(edited) != 2160 or len(clean) != 8:
        raise AuditError("Stage B branch grid differs")
    edit_rows = _jsonl(run_root / "edit_realization_rows.jsonl")
    transport_rows = _jsonl(run_root / "transport_rows.jsonl")
    topk_pairs = _jsonl(run_root / "topk_pair_index.jsonl")
    preflight = _jsonl(run_root / "vectors" / "preflight_rows.jsonl")
    vectors = _jsonl(run_root / "vectors" / "vector_inventory.jsonl")
    matching = _jsonl(run_root / "matching" / "feature_statistics.jsonl")
    vocabulary = _jsonl(run_root / "vocabulary.jsonl")
    if (
        len(edit_rows) != 2160
        or len(transport_rows) != 7560
        or len(topk_pairs) != 1080
        or len(preflight) != 1080
        or len(vectors) != 45
        or len(matching) != protocol.SAE_SPEC["feature_count"]
        or len(vocabulary) != protocol.VOCAB_SIZE
    ):
        raise AuditError("Stage B supporting table count differs")
    try:
        edit_validation = controls.validate_stage_b_edit_rows(edit_rows)
    except controls.ControlViolation as exc:
        raise AuditError(str(exc)) from exc
    if edit_validation["actual_realized_integrity_status"] != "pass":
        raise AuditError("Stage B actual-realized edit integrity failed")
    edit_keys = [
        (
            row["prompt_id"],
            row["assignment_id"],
            row["vector_class"],
            row["sign"],
            row["multiplier"],
        )
        for row in edit_rows
    ]
    branch_by_key = {
        (
            row["prompt_id"],
            row["assignment_id"],
            row["vector_class"],
            row["sign"],
            row["multiplier"],
        ): row
        for row in edited
    }
    if any(
        int(branch_by_key[key]["shard_row"]) < 1
        or int(branch_by_key[key]["shard_row"]) > 270
        for key in edit_keys
    ):
        raise AuditError("Stage B edit/branch arithmetic row join differs")
    if not all(
        _finite_json(row)
        for row in (*edit_rows, *transport_rows, *preflight, *vectors, *matching)
    ):
        raise AuditError("Stage B metadata contains non-finite values")
    if any(
        row.get("token_id") != token_id
        or not isinstance(row.get("token_piece"), str)
        or not isinstance(row.get("decoded_utf8"), str)
        for token_id, row in enumerate(vocabulary)
    ):
        raise AuditError("Stage B vocabulary ID/content table differs")
    pair_expected = {
        (
            prompt_id,
            assignment["assignment_id"],
            vector_class,
            float(multiplier),
        )
        for prompt_id in protocol.STAGE_B_PROMPT_IDS
        for assignment in protocol.aggregate_assignments()
        for vector_class in protocol.VECTOR_CLASSES
        for multiplier in protocol.STAGE_B_MULTIPLIERS
    }
    pair_actual = {
        (
            row.get("prompt_id"),
            row.get("assignment_id"),
            row.get("vector_class"),
            float(row.get("multiplier", -1)),
        )
        for row in topk_pairs
    }
    if pair_actual != pair_expected or len(topk_pairs) != len(pair_actual):
        raise AuditError("paired-central top-k index grid differs")
    for row in topk_pairs:
        if (
            row.get("intermediate_readout") != "j_lens_predicted_logits"
            or row.get("final_readout") != "actual_final_logits"
            or row.get("state_labels") != list(protocol.STAGE_B_CAPTURE_STATES)
            or not (0 <= int(row.get("pair_row", -1)) < 135)
            or not (1 <= int(row.get("minus_shard_row", -1)) <= 270)
            or not (1 <= int(row.get("plus_shard_row", -1)) <= 270)
        ):
            raise AuditError("paired-central top-k row binding differs")
    try:
        transport_validation = controls.validate_stage_b_transport_rows(transport_rows)
    except controls.ControlViolation as exc:
        raise AuditError(str(exc)) from exc
    if transport_validation["status"] != "pass":
        raise AuditError("Stage B paired transport telemetry is invalid")
    vector_tensor = _tensor_inventory(run_root / "vectors" / "vectors.safetensors")
    if vector_tensor != {
        "vectors": {"shape": [45, protocol.WIDTH], "dtype": "torch.bfloat16", "finite": True}
    }:
        raise AuditError("Stage B exact-vector tensor differs")
    residual_state_count = 0
    topk_row_count = 0
    for prompt_id in protocol.STAGE_B_PROMPT_IDS:
        residual = _tensor_inventory(run_root / "residuals" / f"{prompt_id}.safetensors")
        if residual != {
            "residuals": {
                "shape": [271, 36, protocol.WIDTH],
                "dtype": "torch.bfloat16",
                "finite": True,
            }
        }:
            raise AuditError(f"Stage B residual shard differs: {prompt_id}")
        arithmetic = _tensor_inventory(
            run_root / "arithmetic" / f"{prompt_id}.safetensors"
        )
        if arithmetic != {
            "requested_fp32": {
                "shape": [270, protocol.WIDTH],
                "dtype": "torch.float32",
                "finite": True,
            },
            "requested_bfloat16": {
                "shape": [270, protocol.WIDTH],
                "dtype": "torch.bfloat16",
                "finite": True,
            },
            "realized_fp32": {
                "shape": [270, protocol.WIDTH],
                "dtype": "torch.float32",
                "finite": True,
            },
        }:
            raise AuditError(f"Stage B arithmetic shard differs: {prompt_id}")
        topk = _tensor_inventory(run_root / "topk" / f"{prompt_id}.safetensors")
        expected_names = {
            "absolute_top_token_ids": ("torch.int32", 271),
            "absolute_top_scores": ("torch.float32", 271),
            "branch_vs_clean_top_token_ids": ("torch.int32", 271),
            "branch_vs_clean_top_scores": ("torch.float32", 271),
            "branch_vs_clean_bottom_token_ids": ("torch.int32", 271),
            "branch_vs_clean_bottom_scores": ("torch.float32", 271),
            "paired_central_top_token_ids": ("torch.int32", 135),
            "paired_central_top_scores": ("torch.float32", 135),
            "paired_central_bottom_token_ids": ("torch.int32", 135),
            "paired_central_bottom_scores": ("torch.float32", 135),
        }
        if set(topk) != set(expected_names):
            raise AuditError(f"Stage B top-k keys differ: {prompt_id}")
        for name, (dtype, row_count) in expected_names.items():
            if topk[name] != {
                "shape": [row_count, 36, protocol.TOP_K],
                "dtype": dtype,
                "finite": True,
            }:
                raise AuditError(f"Stage B top-k tensor differs: {prompt_id}/{name}")
        _validate_topk_content(run_root / "topk" / f"{prompt_id}.safetensors")
        residual_state_count += 271 * 36
        topk_row_count += 271 * 36
    recomputed_edit_validation = _recompute_stage_b_edit_telemetry(
        run_root,
        branch_rows=branch,
        edit_rows=edit_rows,
    )
    if any(
        recomputed_edit_validation[field] != edit_validation[field]
        for field in (
            "actual_realized_integrity_status",
            "actual_realized_integrity_pass_count",
            "actual_realized_integrity_failure_count",
            "requested_edit_fidelity_status",
            "requested_edit_fidelity_pass_count",
            "requested_edit_fidelity_failure_count",
        )
    ):
        raise AuditError("Stage B telemetry/tensor fidelity classification differs")
    return {
        "branch_row_count": len(branch),
        "edited_row_count": len(edit_rows),
        "actual_realized_integrity_status": edit_validation[
            "actual_realized_integrity_status"
        ],
        "actual_realized_integrity_pass_count": edit_validation[
            "actual_realized_integrity_pass_count"
        ],
        "actual_realized_integrity_failure_count": edit_validation[
            "actual_realized_integrity_failure_count"
        ],
        "requested_edit_fidelity_status": edit_validation[
            "requested_edit_fidelity_status"
        ],
        "requested_edit_fidelity_pass_count": edit_validation[
            "requested_edit_fidelity_pass_count"
        ],
        "requested_edit_fidelity_failure_count": edit_validation[
            "requested_edit_fidelity_failure_count"
        ],
        "requested_realized_relative_rmse_max": edit_validation[
            "requested_realized_relative_rmse_max"
        ],
        "requested_realized_cosine_min": edit_validation[
            "requested_realized_cosine_min"
        ],
        "requested_edit_fidelity_recomputed_from_archived_tensors": True,
        "requested_edit_vector_hashes_recomputed_from_archived_tensors": True,
        "transport_row_count": len(transport_rows),
        "preflight_row_count": len(preflight),
        "residual_state_count": residual_state_count,
        "topk_state_count": topk_row_count,
        "top_k": protocol.TOP_K,
    }


def audit(
    *,
    run_root: Path,
    plan_dir: Path,
    out: Path,
    stage_a_receipt_path: Path | None = None,
    stage_a_audit_path: Path | None = None,
    target_blind_receipt_path: Path | None = None,
    storage_budget_path: Path | None = None,
    stage_b_permit_path: Path | None = None,
    preexecution_authorization_path: Path | None = None,
    smoke_receipt_path: Path | None = None,
) -> dict[str, Any]:
    root = run_root.expanduser().resolve(strict=True)
    if root.is_symlink() or root.name.endswith(".partial"):
        raise AuditError("audit accepts only a finalized real run directory")
    try:
        output_tree = runpod_preflight.validate_study_owned_output_tree(root)
    except runpod_preflight.PreflightError as exc:
        raise AuditError(str(exc)) from exc
    plan = runner._validate_plan(plan_dir)
    complete, records = _validate_manifest(root)
    _audit_resource(complete)
    if complete["plan_manifest_sha256"] != plan["plan_manifest_sha256"]:
        raise AuditError("run and plan hash differ")
    stage = str(complete["stage"])
    prompt_count = _audit_prompt_receipts(root, stage=stage)
    gate_paths = (
        stage_a_receipt_path,
        stage_a_audit_path,
        target_blind_receipt_path,
        storage_budget_path,
        stage_b_permit_path,
    )
    if stage == "stage_b" and (
        any(path is None for path in gate_paths)
        or preexecution_authorization_path is None
    ):
        raise AuditError(
            "Stage B audit requires all five gate receipts and preauthorization"
        )
    if stage == "stage_a" and any(
        path is None
        for path in (
            storage_budget_path,
            preexecution_authorization_path,
            smoke_receipt_path,
        )
    ):
        raise AuditError(
            "Stage A audit requires storage, preauthorization, and smoke receipts"
        )
    gate_values = [
        _json(path) if path is not None else None
        for path in gate_paths
    ]
    authorization = (
        _json(preexecution_authorization_path)
        if preexecution_authorization_path is not None
        else None
    )
    smoke = _json(smoke_receipt_path) if smoke_receipt_path is not None else None
    smoke_file_hash: str | None = None
    if stage == "stage_a":
        assert authorization is not None
        assert smoke is not None
        assert smoke_receipt_path is not None
        from experiments.consciousness_sae_realization_validation import smoke_test

        try:
            preexecution.validate_authorization_evidence(
                authorization, repo_root=REPO_ROOT, plan_dir=plan_dir
            )
            smoke_test.validate_smoke_receipt(
                smoke,
                expected_plan_hash=complete["plan_manifest_sha256"],
                expected_authorization=authorization,
            )
            raw_tail = (*controls.RAW_NAMESPACE, str(complete["run_id"]))
            if tuple(root.parts[-len(raw_tail) :]) != raw_tail:
                raise AuditError("Stage A raw run path is outside the exact namespace")
            volume_root = root.parents[len(controls.RAW_NAMESPACE)]
            smoke_file_hash = smoke_test.validate_external_receipt_file(
                volume_root=volume_root,
                receipt_path=smoke_receipt_path,
                receipt=smoke,
            )
        except (preexecution.PreexecutionError, smoke_test.SmokeTestError) as exc:
            raise AuditError(str(exc)) from exc
    elif stage == "stage_b":
        assert authorization is not None
        assert preexecution_authorization_path is not None
        try:
            preexecution.validate_authorization_evidence(
                authorization, repo_root=REPO_ROOT, plan_dir=plan_dir
            )
        except preexecution.PreexecutionError as exc:
            raise AuditError(str(exc)) from exc
        if preexecution_authorization_path.read_bytes() != (
            protocol.canonical_json_bytes(authorization) + b"\n"
        ):
            raise AuditError("Stage B authorization is not canonical JSON")
    binding_receipt_hashes = _audit_execution_binding(
        root,
        complete=complete,
        stage_a_receipt=gate_values[0],
        stage_a_audit=gate_values[1],
        target_blind_receipt=gate_values[2],
        storage_budget=gate_values[3],
        stage_b_permit=gate_values[4],
        preexecution_authorization=authorization,
        smoke_receipt=smoke,
        smoke_receipt_file_sha256=smoke_file_hash,
    )
    details = (
        _audit_stage_a(
            root,
            plan_manifest_sha256=complete["plan_manifest_sha256"],
            records=records,
        )
        if stage == "stage_a"
        else _audit_stage_b(root)
    )
    core = {
        "schema_version": 1,
        "status": "pass",
        "study_id": protocol.STUDY_ID,
        "protocol_version": protocol.PROTOCOL_VERSION,
        "stage": stage,
        "run_id": complete["run_id"],
        "plan_manifest_sha256": complete["plan_manifest_sha256"],
        "raw_run_receipt_sha256": complete["receipt_sha256"],
        "manifested_file_count": len(records),
        "missing_file_count": 0,
        "extra_file_count": 0,
        "duplicate_file_count": 0,
        "nonfinite_count": 0,
        "partial_path_count": 0,
        "paper_prompt_render_count": 0,
        "target_prompt_render_count": 0,
        "target_outcome_count": 0,
        "details": details,
        "derived_neutral_prompt_count": prompt_count,
        "study_owned_output_tree": output_tree,
        "gate_receipt_hashes": binding_receipt_hashes,
        "preexecution_authorization_sha256": (
            authorization["receipt_sha256"] if authorization is not None else None
        ),
        "campaign_identity_sha256": (
            authorization["campaign_identity_sha256"]
            if authorization is not None
            else None
        ),
        "prior_outcome_inputs": [],
    }
    receipt = {**core, "receipt_sha256": protocol.canonical_sha256(core)}
    destination = out.expanduser().resolve()
    if destination.exists() or destination.is_symlink():
        raise FileExistsError(f"audit output already exists: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(protocol.canonical_json_bytes(receipt) + b"\n")
    return receipt


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--plan-dir", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--stage-a-receipt", type=Path)
    parser.add_argument("--stage-a-audit", type=Path)
    parser.add_argument("--target-blind-receipt", type=Path)
    parser.add_argument("--storage-budget", type=Path)
    parser.add_argument("--stage-b-permit", type=Path)
    parser.add_argument("--preexecution-authorization", type=Path)
    parser.add_argument("--smoke-receipt", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    receipt = audit(
        run_root=args.run_root,
        plan_dir=args.plan_dir,
        out=args.out,
        stage_a_receipt_path=args.stage_a_receipt,
        stage_a_audit_path=args.stage_a_audit,
        target_blind_receipt_path=args.target_blind_receipt,
        storage_budget_path=args.storage_budget,
        stage_b_permit_path=args.stage_b_permit,
        preexecution_authorization_path=args.preexecution_authorization,
        smoke_receipt_path=args.smoke_receipt,
    )
    print(receipt["receipt_sha256"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

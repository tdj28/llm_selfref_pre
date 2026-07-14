"""V2-seeded target-free J arithmetic/orientation fixtures."""

from __future__ import annotations

import hashlib
import math
import re
from typing import Any, Callable, Mapping

from experiments.consciousness_sae_realization_validation import runtime
from experiments.consciousness_sae_target_blind_calibration import protocol


class OrientationError(RuntimeError):
    pass


HEX64_RE = re.compile(r"[0-9a-f]{64}")
FIXTURE_COUNT = int(protocol.J_ORIENTATION_SPEC["fixture_count_per_layer"])
SEED_NAMESPACE = str(protocol.J_ORIENTATION_SPEC["fixture_seed_namespace"])
EXPECTED_ROW_COUNT = len(protocol.J_LAYERS) * FIXTURE_COUNT
SAFE_DENOMINATOR = 1e-30


def fixture_seed(layer: int, fixture_index: int) -> int:
    if layer not in protocol.J_LAYERS or fixture_index not in range(FIXTURE_COUNT):
        raise OrientationError("orientation fixture coordinate is outside the plan")
    return protocol.seed64(SEED_NAMESPACE, layer, fixture_index)


def deterministic_fixture(layer: int, fixture_index: int, *, device: Any) -> Any:
    import numpy as np
    import torch

    seed = fixture_seed(layer, fixture_index)
    material = protocol.canonical_json_bytes(
        {
            "study_id": protocol.STUDY_ID,
            "protocol_version": protocol.PROTOCOL_VERSION,
            "namespace": SEED_NAMESPACE,
            "layer": layer,
            "fixture_index": fixture_index,
            "seed": seed,
        }
    )
    raw = hashlib.shake_256(material).digest(protocol.WIDTH * 4)
    unsigned = np.frombuffer(raw, dtype="<u4").astype(np.float64)
    values = unsigned / float(2**32) - 0.5
    values -= values.mean(dtype=np.float64)
    norm = float(np.linalg.norm(values))
    if not math.isfinite(norm) or norm == 0:
        raise OrientationError("orientation fixture norm is invalid")
    result = torch.from_numpy((values / norm).astype(np.float32).copy()).to(
        device=device
    )
    return result.contiguous()


def _reference(source: Any, matrix: Any) -> Any:
    import torch

    quantized = source.to(device=matrix.device, dtype=matrix.dtype).float()
    result = torch.empty(matrix.shape[0], device=matrix.device, dtype=torch.float32)
    chunk = int(protocol.J_ORIENTATION_SPEC["reference_row_chunk_size"])
    for start in range(0, int(matrix.shape[0]), chunk):
        stop = min(start + chunk, int(matrix.shape[0]))
        result[start:stop] = torch.sum(
            matrix[start:stop].float() * quantized.unsqueeze(0), dim=1
        )
    return result.contiguous()


def _safe_relative_rmse(actual: Any, reference: Any) -> float:
    import torch

    if not isinstance(actual, torch.Tensor) or not isinstance(reference, torch.Tensor):
        raise OrientationError("orientation relative-RMSE inputs are not tensors")
    observed = actual.detach().float().reshape(-1)
    expected = reference.detach().to(device=observed.device).float().reshape(-1)
    if observed.shape != expected.shape or observed.numel() == 0:
        raise OrientationError("orientation relative-RMSE shapes differ")
    if not bool(torch.isfinite(observed).all() and torch.isfinite(expected).all()):
        raise OrientationError("orientation relative-RMSE inputs are non-finite")
    numerator = torch.sqrt(torch.mean((observed - expected).square()))
    denominator = torch.sqrt(torch.mean(expected.square())).clamp_min(SAFE_DENOMINATOR)
    result = float((numerator / denominator).item())
    if not math.isfinite(result) or result < 0.0:
        raise OrientationError("orientation relative RMSE is invalid")
    return result


def _safe_cosine(left: Any, right: Any) -> float:
    import torch

    if not isinstance(left, torch.Tensor) or not isinstance(right, torch.Tensor):
        raise OrientationError("orientation cosine inputs are not tensors")
    lhs = left.detach().float().reshape(-1)
    rhs = right.detach().to(device=lhs.device).float().reshape(-1)
    if lhs.shape != rhs.shape or lhs.numel() == 0:
        raise OrientationError("orientation cosine shapes differ")
    if not bool(torch.isfinite(lhs).all() and torch.isfinite(rhs).all()):
        raise OrientationError("orientation cosine inputs are non-finite")
    denominator = torch.linalg.vector_norm(lhs) * torch.linalg.vector_norm(rhs)
    if float(denominator.item()) <= 0.0:
        return 0.0
    result = float(torch.dot(lhs, rhs).div(denominator).item())
    if not math.isfinite(result):
        raise OrientationError("orientation cosine is non-finite")
    return max(-1.0, min(1.0, result))


def execute(
    backend: Any,
    *,
    plan_manifest_sha256: str,
    progress_callback: Callable[[], None] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if HEX64_RE.fullmatch(plan_manifest_sha256) is None:
        raise OrientationError("plan hash is malformed")
    rows: list[dict[str, Any]] = []
    for layer in protocol.J_LAYERS:
        if progress_callback is not None:
            progress_callback()
        matrix = backend.j_matrix(layer)
        if tuple(matrix.shape) != (protocol.WIDTH, protocol.WIDTH):
            raise OrientationError("J matrix shape differs")
        for fixture_index in range(FIXTURE_COUNT):
            if progress_callback is not None:
                progress_callback()
            fixture = deterministic_fixture(layer, fixture_index, device=matrix.device)
            quantized = fixture.to(dtype=matrix.dtype).contiguous()
            production = quantized @ matrix.T
            reference = _reference(fixture, matrix)
            wrong = quantized @ matrix
            correct_cosine = _safe_cosine(production, reference)
            correct_rmse = _safe_relative_rmse(production, reference)
            wrong_cosine = _safe_cosine(wrong, reference)
            wrong_rmse = _safe_relative_rmse(wrong, reference)
            production_status = (
                "pass"
                if (
                    correct_cosine
                    >= protocol.GATE_THRESHOLDS["j_orientation_reference_cosine_min"]
                    and correct_rmse
                    <= protocol.GATE_THRESHOLDS[
                        "j_orientation_reference_relative_rmse_max"
                    ]
                )
                else "fail"
            )
            wrong_status = (
                "pass"
                if (
                    wrong_rmse - correct_rmse
                    >= protocol.GATE_THRESHOLDS[
                        "j_orientation_wrong_relative_rmse_margin_min"
                    ]
                    and correct_cosine - wrong_cosine
                    >= protocol.GATE_THRESHOLDS["j_orientation_wrong_cosine_gap_min"]
                )
                else "fail"
            )
            finite = bool(
                backend.torch.isfinite(production).all()
                and backend.torch.isfinite(reference).all()
                and backend.torch.isfinite(wrong).all()
            )
            status = (
                "pass"
                if finite and production_status == "pass" and wrong_status == "pass"
                else "fail"
            )
            rows.append(
                {
                    "study_id": protocol.STUDY_ID,
                    "protocol_version": protocol.PROTOCOL_VERSION,
                    "plan_manifest_sha256": plan_manifest_sha256,
                    "layer": layer,
                    "fixture_index": fixture_index,
                    "fixture_seed": fixture_seed(layer, fixture_index),
                    "fixture_seed_namespace": SEED_NAMESPACE,
                    "fixture_algorithm": protocol.J_ORIENTATION_SPEC[
                        "fixture_algorithm"
                    ],
                    "j_lens_revision": protocol.J_LENS_SPEC["revision"],
                    "j_lens_sha256": protocol.J_LENS_SPEC["sha256"],
                    "orientation_convention": protocol.J_LENS_SPEC["orientation"],
                    "production_algorithm": protocol.J_ORIENTATION_SPEC[
                        "production_algorithm"
                    ],
                    "reference_algorithm": protocol.J_ORIENTATION_SPEC[
                        "reference_algorithm"
                    ],
                    "wrong_orientation_algorithm": protocol.J_ORIENTATION_SPEC[
                        "wrong_orientation_algorithm"
                    ],
                    "fixture_fp32_sha256": runtime.tensor_sha256(fixture),
                    "quantized_source_sha256": runtime.tensor_sha256(quantized),
                    "production_output_sha256": runtime.tensor_sha256(production),
                    "reference_output_sha256": runtime.tensor_sha256(reference),
                    "wrong_output_sha256": runtime.tensor_sha256(wrong),
                    "production_reference_cosine": correct_cosine,
                    "production_reference_relative_rmse": correct_rmse,
                    "wrong_reference_cosine": wrong_cosine,
                    "wrong_reference_relative_rmse": wrong_rmse,
                    "correct_minus_wrong_cosine_gap": correct_cosine - wrong_cosine,
                    "wrong_minus_correct_relative_rmse_margin": wrong_rmse
                    - correct_rmse,
                    "production_reference_status": production_status,
                    "wrong_orientation_control_status": wrong_status,
                    "status": status,
                    "finite": finite,
                    "model_forward_count": 0,
                    "target_prompt_render_count": 0,
                    "target_feature_vector_count": 0,
                    "analysis_data_inputs": [],
                }
            )
            if progress_callback is not None:
                progress_callback()
    overall = "pass" if all(row["status"] == "pass" for row in rows) else "fail"
    core: dict[str, Any] = {
        "schema_version": 1,
        "status": overall,
        "study_id": protocol.STUDY_ID,
        "protocol_version": protocol.PROTOCOL_VERSION,
        "plan_manifest_sha256": plan_manifest_sha256,
        "fixture_seed_namespace": SEED_NAMESPACE,
        "fixture_algorithm": protocol.J_ORIENTATION_SPEC["fixture_algorithm"],
        "j_lens_revision": protocol.J_LENS_SPEC["revision"],
        "j_lens_sha256": protocol.J_LENS_SPEC["sha256"],
        "orientation_convention": protocol.J_LENS_SPEC["orientation"],
        "production_algorithm": protocol.J_ORIENTATION_SPEC["production_algorithm"],
        "reference_algorithm": protocol.J_ORIENTATION_SPEC["reference_algorithm"],
        "wrong_orientation_algorithm": protocol.J_ORIENTATION_SPEC[
            "wrong_orientation_algorithm"
        ],
        "row_count": len(rows),
        "expected_row_count": EXPECTED_ROW_COUNT,
        "rows_canonical_sha256": protocol.canonical_sha256(rows),
        "model_forward_count": 0,
        "target_prompt_render_count": 0,
        "target_feature_vector_count": 0,
        "analysis_data_inputs": [],
    }
    receipt = {**core, "receipt_sha256": protocol.canonical_sha256(core)}
    return rows, receipt


def validate(
    rows: list[Mapping[str, Any]], receipt: Mapping[str, Any], *, plan_hash: str
) -> None:
    if HEX64_RE.fullmatch(plan_hash) is None:
        raise OrientationError("orientation plan hash is malformed")
    core = dict(receipt)
    supplied = core.pop("receipt_sha256", None)
    if supplied != protocol.canonical_sha256(core):
        raise OrientationError("orientation receipt self-hash differs")
    if (
        receipt.get("schema_version") != 1
        or receipt.get("status") not in {"pass", "fail"}
        or receipt.get("study_id") != protocol.STUDY_ID
        or receipt.get("protocol_version") != protocol.PROTOCOL_VERSION
        or receipt.get("plan_manifest_sha256") != plan_hash
        or receipt.get("fixture_seed_namespace") != SEED_NAMESPACE
        or receipt.get("fixture_algorithm")
        != protocol.J_ORIENTATION_SPEC["fixture_algorithm"]
        or receipt.get("j_lens_revision") != protocol.J_LENS_SPEC["revision"]
        or receipt.get("j_lens_sha256") != protocol.J_LENS_SPEC["sha256"]
        or receipt.get("orientation_convention") != protocol.J_LENS_SPEC["orientation"]
        or receipt.get("production_algorithm")
        != protocol.J_ORIENTATION_SPEC["production_algorithm"]
        or receipt.get("reference_algorithm")
        != protocol.J_ORIENTATION_SPEC["reference_algorithm"]
        or receipt.get("wrong_orientation_algorithm")
        != protocol.J_ORIENTATION_SPEC["wrong_orientation_algorithm"]
        or receipt.get("row_count") != EXPECTED_ROW_COUNT
        or receipt.get("expected_row_count") != EXPECTED_ROW_COUNT
        or receipt.get("rows_canonical_sha256") != protocol.canonical_sha256(rows)
        or len(rows) != EXPECTED_ROW_COUNT
        or receipt.get("model_forward_count") != 0
        or receipt.get("target_prompt_render_count") != 0
        or receipt.get("target_feature_vector_count") != 0
        or receipt.get("analysis_data_inputs") != []
    ):
        raise OrientationError("orientation receipt binding/status differs")
    for offset, row in enumerate(rows):
        layer = protocol.J_LAYERS[offset // FIXTURE_COUNT]
        fixture_index = offset % FIXTURE_COUNT
        metrics = (
            row.get("production_reference_cosine"),
            row.get("production_reference_relative_rmse"),
            row.get("wrong_reference_cosine"),
            row.get("wrong_reference_relative_rmse"),
        )
        if any(
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(float(value))
            for value in metrics
        ):
            raise OrientationError("orientation row metric is non-finite")
        correct_cosine, correct_rmse, wrong_cosine, wrong_rmse = map(float, metrics)
        expected_production = (
            "pass"
            if (
                correct_cosine
                >= protocol.GATE_THRESHOLDS["j_orientation_reference_cosine_min"]
                and correct_rmse
                <= protocol.GATE_THRESHOLDS["j_orientation_reference_relative_rmse_max"]
            )
            else "fail"
        )
        expected_wrong = (
            "pass"
            if (
                wrong_rmse - correct_rmse
                >= protocol.GATE_THRESHOLDS[
                    "j_orientation_wrong_relative_rmse_margin_min"
                ]
                and correct_cosine - wrong_cosine
                >= protocol.GATE_THRESHOLDS["j_orientation_wrong_cosine_gap_min"]
            )
            else "fail"
        )
        expected_status = (
            "pass"
            if expected_production == "pass" and expected_wrong == "pass"
            else "fail"
        )
        if (
            row.get("study_id") != protocol.STUDY_ID
            or row.get("protocol_version") != protocol.PROTOCOL_VERSION
            or row.get("plan_manifest_sha256") != plan_hash
            or row.get("layer") != layer
            or row.get("fixture_index") != fixture_index
            or row.get("fixture_seed") != fixture_seed(layer, fixture_index)
            or row.get("fixture_seed_namespace") != SEED_NAMESPACE
            or row.get("fixture_algorithm")
            != protocol.J_ORIENTATION_SPEC["fixture_algorithm"]
            or row.get("j_lens_revision") != protocol.J_LENS_SPEC["revision"]
            or row.get("j_lens_sha256") != protocol.J_LENS_SPEC["sha256"]
            or row.get("orientation_convention") != protocol.J_LENS_SPEC["orientation"]
            or row.get("production_algorithm")
            != protocol.J_ORIENTATION_SPEC["production_algorithm"]
            or row.get("reference_algorithm")
            != protocol.J_ORIENTATION_SPEC["reference_algorithm"]
            or row.get("wrong_orientation_algorithm")
            != protocol.J_ORIENTATION_SPEC["wrong_orientation_algorithm"]
            or any(
                HEX64_RE.fullmatch(str(row.get(field, ""))) is None
                for field in (
                    "fixture_fp32_sha256",
                    "quantized_source_sha256",
                    "production_output_sha256",
                    "reference_output_sha256",
                    "wrong_output_sha256",
                )
            )
            or row.get("production_reference_status") != expected_production
            or row.get("wrong_orientation_control_status") != expected_wrong
            or row.get("status") != expected_status
            or row.get("finite") is not True
            or not math.isclose(
                float(row.get("correct_minus_wrong_cosine_gap", math.nan)),
                correct_cosine - wrong_cosine,
                rel_tol=0.0,
                abs_tol=1e-12,
            )
            or not math.isclose(
                float(row.get("wrong_minus_correct_relative_rmse_margin", math.nan)),
                wrong_rmse - correct_rmse,
                rel_tol=0.0,
                abs_tol=1e-12,
            )
            or row.get("model_forward_count") != 0
            or row.get("target_prompt_render_count") != 0
            or row.get("target_feature_vector_count") != 0
            or row.get("analysis_data_inputs") != []
        ):
            raise OrientationError("orientation row identity/status differs")
    expected_overall = (
        "pass" if all(row.get("status") == "pass" for row in rows) else "fail"
    )
    if receipt.get("status") != expected_overall:
        raise OrientationError("orientation receipt aggregate status differs")

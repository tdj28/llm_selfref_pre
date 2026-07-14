"""Current-study, independent J arithmetic/orientation producer and gate.

This module executes deterministic, target-free fixtures against every frozen
J map.  The production result comes through ``V2Backend.transport_realized``
(``row @ J.T``).  A separately coded explicit component sum computes
``y_i = sum_j J[i,j] x_j``; ``row @ J`` is evaluated as a prospective wrong-
orientation control.  No model forward, prompt, SAE feature, or predecessor
outcome is read by this gate.
"""

from __future__ import annotations

import hashlib
import math
import re
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from . import protocol


ORIENTATION_SCHEMA_VERSION = 1
FIXTURE_COUNT = int(protocol.J_ORIENTATION_SPEC["fixture_count_per_layer"])
REFERENCE_ROW_CHUNK_SIZE = int(
    protocol.J_ORIENTATION_SPEC["reference_row_chunk_size"]
)
EXPECTED_ROW_COUNT = len(protocol.J_LAYERS) * FIXTURE_COUNT
LAYERS_SHA256 = protocol.canonical_sha256(list(protocol.J_LAYERS))
HEX64 = re.compile(r"[0-9a-f]{64}")

PRODUCTION_ALGORITHM = str(protocol.J_ORIENTATION_SPEC["production_algorithm"])
REFERENCE_ALGORITHM = str(
    protocol.J_ORIENTATION_SPEC["independent_reference_algorithm"]
)
WRONG_ORIENTATION_ALGORITHM = str(
    protocol.J_ORIENTATION_SPEC["wrong_orientation_algorithm"]
)
FIXTURE_ALGORITHM = str(protocol.J_ORIENTATION_SPEC["fixture_algorithm"])
UPSTREAM_REFERENCE_REPOSITORY = str(
    protocol.J_LENS_SPEC["upstream_reference"]["repository"]
)
UPSTREAM_REFERENCE_REVISION = str(
    protocol.J_LENS_SPEC["upstream_reference"]["revision"]
)
UPSTREAM_ROW_VECTOR_IMPLEMENTATION = str(
    protocol.J_LENS_SPEC["transport_contract"]["row_vector_implementation"]
)
RELEASE_CONFIG_SHA256 = str(protocol.J_LENS_SPEC["release_config"]["sha256"])
TRANSPORT_CONTRACT_SHA256 = protocol.canonical_sha256(
    protocol.J_LENS_SPEC["transport_contract"]
)

REFERENCE_COSINE_MIN = float(
    protocol.GATE_THRESHOLDS["j_orientation_reference_cosine_min"]
)
REFERENCE_RELATIVE_RMSE_MAX = float(
    protocol.GATE_THRESHOLDS["j_orientation_reference_relative_rmse_max"]
)
WRONG_RELATIVE_RMSE_MARGIN_MIN = float(
    protocol.GATE_THRESHOLDS["j_orientation_wrong_relative_rmse_margin_min"]
)
WRONG_COSINE_GAP_MIN = float(
    protocol.GATE_THRESHOLDS["j_orientation_wrong_cosine_gap_min"]
)

ORIENTATION_ROW_FIELDS = frozenset(
    {
        "study_id",
        "protocol_version",
        "plan_manifest_sha256",
        "layer",
        "fixture_index",
        "fixture_seed",
        "fixture_algorithm",
        "fixture_fp32_sha256",
        "quantized_source_sha256",
        "j_lens_repository",
        "j_lens_revision",
        "j_lens_sha256",
        "release_config_sha256",
        "upstream_reference_repository",
        "upstream_reference_revision",
        "upstream_row_vector_implementation",
        "transport_contract_sha256",
        "orientation_convention",
        "production_algorithm",
        "independent_reference_algorithm",
        "wrong_orientation_algorithm",
        "production_output_sha256",
        "independent_reference_output_sha256",
        "wrong_orientation_output_sha256",
        "production_reference_cosine",
        "production_reference_relative_rmse",
        "wrong_reference_cosine",
        "wrong_reference_relative_rmse",
        "correct_minus_wrong_cosine_gap",
        "wrong_minus_correct_relative_rmse_margin",
        "production_reference_status",
        "wrong_orientation_control_status",
        "status",
        "finite",
        "model_forward_count",
        "target_prompt_render_count",
        "target_forward_count",
        "target_outcome_count",
        "prior_outcome_inputs",
    }
)

ORIENTATION_RECEIPT_FIELDS = frozenset(
    {
        "schema_version",
        "status",
        "study_id",
        "protocol_version",
        "plan_manifest_sha256",
        "j_lens_repository",
        "j_lens_revision",
        "j_lens_sha256",
        "release_config_sha256",
        "upstream_reference_repository",
        "upstream_reference_revision",
        "upstream_row_vector_implementation",
        "transport_contract_sha256",
        "orientation_convention",
        "fixture_algorithm",
        "fixture_count_per_layer",
        "layer_count",
        "layers_sha256",
        "row_count",
        "rows_canonical_sha256",
        "rows_file_sha256",
        "production_algorithm",
        "independent_reference_algorithm",
        "wrong_orientation_algorithm",
        "production_reference_status",
        "wrong_orientation_control_status",
        "model_forward_count",
        "target_prompt_render_count",
        "target_forward_count",
        "target_outcome_count",
        "prior_outcome_inputs",
        "receipt_sha256",
    }
)


class OrientationViolation(RuntimeError):
    """A structural or identity failure in the orientation gate."""


def _require_hex64(value: Any, label: str) -> str:
    if not isinstance(value, str) or HEX64.fullmatch(value) is None:
        raise OrientationViolation(f"{label} is not lowercase SHA-256")
    return value


def _require_exact_fields(
    value: Mapping[str, Any], fields: frozenset[str], label: str
) -> None:
    if not isinstance(value, Mapping) or set(value) != fields:
        actual = set(value) if isinstance(value, Mapping) else set()
        raise OrientationViolation(
            f"{label} fields differ; missing={sorted(fields - actual)}, "
            f"extra={sorted(actual - fields)}"
        )


def _finite_number(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise OrientationViolation(f"{label} is not numeric")
    result = float(value)
    if not math.isfinite(result):
        raise OrientationViolation(f"{label} is non-finite")
    return result


def fixture_seed(layer: int, fixture_index: int) -> int:
    if layer not in protocol.J_LAYERS:
        raise OrientationViolation("fixture layer is outside the frozen J inventory")
    if (
        isinstance(fixture_index, bool)
        or not isinstance(fixture_index, int)
        or not 0 <= fixture_index < FIXTURE_COUNT
    ):
        raise OrientationViolation("fixture index is outside the frozen inventory")
    return protocol.seed64("j-orientation-fixture-v1", layer, fixture_index)


def deterministic_fixture(layer: int, fixture_index: int, *, device: Any) -> Any:
    """Create a version-independent SHAKE256 fixture without a PRNG state."""

    try:
        import numpy as np
        import torch
    except ImportError as exc:  # pragma: no cover - GPU environment dependency
        raise OrientationViolation("NumPy and PyTorch are required") from exc
    seed = fixture_seed(layer, fixture_index)
    material = protocol.canonical_json_bytes(
        {
            "study_id": protocol.STUDY_ID,
            "protocol_version": protocol.PROTOCOL_VERSION,
            "namespace": "j-orientation-fixture-v1",
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
    if not math.isfinite(norm) or norm == 0.0:
        raise OrientationViolation("deterministic fixture has invalid norm")
    fixture = np.asarray(values / norm, dtype=np.float32)
    result = torch.from_numpy(fixture.copy()).to(device=device, dtype=torch.float32)
    if tuple(result.shape) != (protocol.WIDTH,) or not bool(torch.isfinite(result).all()):
        raise OrientationViolation("deterministic fixture tensor differs")
    return result.contiguous()


def tensor_sha256(value: Any) -> str:
    """Hash exact tensor bytes while preserving dtype and native layout."""

    import torch

    contiguous = value.detach().contiguous().to(device="cpu")
    # Viewing as uint8 also supports BF16 tensors on NumPy builds without BF16
    # support and preserves the exact underlying bytes.
    return hashlib.sha256(contiguous.view(torch.uint8).numpy().tobytes()).hexdigest()


def _production_row_at_j_transpose(source: Any, matrix: Any) -> Any:
    """Small-fixture helper matching the production row@J.T convention."""

    return source.to(device=matrix.device, dtype=matrix.dtype) @ matrix.T


def _independent_component_reference(
    source: Any, matrix: Any, *, row_chunk_size: int = REFERENCE_ROW_CHUNK_SIZE
) -> Any:
    """Compute y_i=sum_j J[i,j]x_j without matmul or the production helper."""

    import torch

    if matrix.ndim != 2 or matrix.shape[0] != matrix.shape[1]:
        raise OrientationViolation("J map is not a square matrix")
    if source.ndim != 1 or source.shape[0] != matrix.shape[1]:
        raise OrientationViolation("fixture/J dimensions differ")
    if row_chunk_size <= 0:
        raise OrientationViolation("reference row chunk size is invalid")
    quantized = source.to(device=matrix.device, dtype=matrix.dtype).float()
    result = torch.empty(matrix.shape[0], device=matrix.device, dtype=torch.float32)
    for start in range(0, int(matrix.shape[0]), row_chunk_size):
        stop = min(start + row_chunk_size, int(matrix.shape[0]))
        # Explicit multiply-and-sum is intentionally independent of the
        # production vector-matrix multiplication and its orientation syntax.
        result[start:stop] = torch.sum(
            matrix[start:stop, :].float() * quantized.unsqueeze(0), dim=1
        )
    return result.contiguous()


def _wrong_orientation_control(source: Any, matrix: Any) -> Any:
    """Prospective negative control: row@J, not the frozen row@J.T."""

    return source.to(device=matrix.device, dtype=matrix.dtype) @ matrix


def _cosine(left: Any, right: Any) -> float:
    import torch

    lhs = left.float().reshape(-1)
    rhs = right.to(device=lhs.device).float().reshape(-1)
    denominator = torch.linalg.vector_norm(lhs) * torch.linalg.vector_norm(rhs)
    if float(denominator.item()) == 0.0:
        raise OrientationViolation("orientation metric has zero norm")
    return float(torch.dot(lhs, rhs).div(denominator).item())


def _relative_rmse(value: Any, reference: Any) -> float:
    import torch

    observed = value.float().reshape(-1)
    expected = reference.to(device=observed.device).float().reshape(-1)
    scale = torch.sqrt(torch.mean(expected.square()))
    if float(scale.item()) == 0.0:
        raise OrientationViolation("orientation reference has zero RMS")
    return float(torch.sqrt(torch.mean((observed - expected).square())).div(scale).item())


def _row_statuses(
    *, correct_cosine: float, correct_rmse: float, wrong_cosine: float, wrong_rmse: float
) -> tuple[str, str, str]:
    production_reference = (
        "pass"
        if correct_cosine >= REFERENCE_COSINE_MIN
        and correct_rmse <= REFERENCE_RELATIVE_RMSE_MAX
        else "fail"
    )
    wrong_control = (
        "pass"
        if (wrong_rmse - correct_rmse) >= WRONG_RELATIVE_RMSE_MARGIN_MIN
        and (correct_cosine - wrong_cosine) >= WRONG_COSINE_GAP_MIN
        else "fail"
    )
    overall = (
        "pass"
        if production_reference == "pass" and wrong_control == "pass"
        else "fail"
    )
    return production_reference, wrong_control, overall


def execute_orientation_rows(
    backend: Any, *, plan_manifest_sha256: str
) -> list[dict[str, Any]]:
    """Execute the current-study gate over all 34 maps and 68 fixtures."""

    _require_hex64(plan_manifest_sha256, "plan manifest")
    rows: list[dict[str, Any]] = []
    for layer in protocol.J_LAYERS:
        matrix = backend.j_matrix(layer)
        if tuple(matrix.shape) != (protocol.WIDTH, protocol.WIDTH):
            raise OrientationViolation(f"J[{layer}] shape differs")
        for fixture_index in range(FIXTURE_COUNT):
            fixture = deterministic_fixture(layer, fixture_index, device=matrix.device)
            quantized = fixture.to(dtype=matrix.dtype).contiguous()
            # This is the actual production implementation under test.
            production = backend.transport_realized(
                fixture, layer=layer, transport="real_j"
            ).contiguous()
            reference = _independent_component_reference(fixture, matrix)
            wrong = _wrong_orientation_control(fixture, matrix).contiguous()
            finite = bool(
                backend.torch.isfinite(production).all()
                and backend.torch.isfinite(reference).all()
                and backend.torch.isfinite(wrong).all()
            )
            correct_cosine = _cosine(production, reference)
            correct_rmse = _relative_rmse(production, reference)
            wrong_cosine = _cosine(wrong, reference)
            wrong_rmse = _relative_rmse(wrong, reference)
            production_status, wrong_status, status = _row_statuses(
                correct_cosine=correct_cosine,
                correct_rmse=correct_rmse,
                wrong_cosine=wrong_cosine,
                wrong_rmse=wrong_rmse,
            )
            if not finite:
                production_status = wrong_status = status = "fail"
            rows.append(
                {
                    "study_id": protocol.STUDY_ID,
                    "protocol_version": protocol.PROTOCOL_VERSION,
                    "plan_manifest_sha256": plan_manifest_sha256,
                    "layer": layer,
                    "fixture_index": fixture_index,
                    "fixture_seed": fixture_seed(layer, fixture_index),
                    "fixture_algorithm": FIXTURE_ALGORITHM,
                    "fixture_fp32_sha256": tensor_sha256(fixture),
                    "quantized_source_sha256": tensor_sha256(quantized),
                    "j_lens_repository": protocol.J_LENS_SPEC["repository"],
                    "j_lens_revision": protocol.J_LENS_SPEC["revision"],
                    "j_lens_sha256": protocol.J_LENS_SPEC["sha256"],
                    "release_config_sha256": RELEASE_CONFIG_SHA256,
                    "upstream_reference_repository": UPSTREAM_REFERENCE_REPOSITORY,
                    "upstream_reference_revision": UPSTREAM_REFERENCE_REVISION,
                    "upstream_row_vector_implementation": (
                        UPSTREAM_ROW_VECTOR_IMPLEMENTATION
                    ),
                    "transport_contract_sha256": TRANSPORT_CONTRACT_SHA256,
                    "orientation_convention": protocol.J_LENS_SPEC["orientation"],
                    "production_algorithm": PRODUCTION_ALGORITHM,
                    "independent_reference_algorithm": REFERENCE_ALGORITHM,
                    "wrong_orientation_algorithm": WRONG_ORIENTATION_ALGORITHM,
                    "production_output_sha256": tensor_sha256(production),
                    "independent_reference_output_sha256": tensor_sha256(reference),
                    "wrong_orientation_output_sha256": tensor_sha256(wrong),
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
                    "target_forward_count": 0,
                    "target_outcome_count": 0,
                    "prior_outcome_inputs": [],
                }
            )
    validate_orientation_rows(rows, plan_manifest_sha256=plan_manifest_sha256)
    return rows


def _canonical_jsonl_sha256(rows: Sequence[Mapping[str, Any]]) -> str:
    digest = hashlib.sha256()
    for row in rows:
        digest.update(protocol.canonical_json_bytes(dict(row)))
        digest.update(b"\n")
    return digest.hexdigest()


def validate_orientation_rows(
    rows: Iterable[Mapping[str, Any]], *, plan_manifest_sha256: str
) -> dict[str, Any]:
    """Validate exact row inventory, bindings, metrics, and gate decisions."""

    _require_hex64(plan_manifest_sha256, "plan manifest")
    materialized = [dict(row) for row in rows]
    expected_keys = [
        (layer, fixture_index)
        for layer in protocol.J_LAYERS
        for fixture_index in range(FIXTURE_COUNT)
    ]
    if len(materialized) != EXPECTED_ROW_COUNT:
        raise OrientationViolation("orientation row count differs")
    production_statuses: list[str] = []
    wrong_statuses: list[str] = []
    observed_keys: list[tuple[int, int]] = []
    for offset, row in enumerate(materialized):
        _require_exact_fields(row, ORIENTATION_ROW_FIELDS, f"orientation row {offset}")
        if (
            row["study_id"] != protocol.STUDY_ID
            or row["protocol_version"] != protocol.PROTOCOL_VERSION
            or row["plan_manifest_sha256"] != plan_manifest_sha256
        ):
            raise OrientationViolation(f"orientation row {offset} identity differs")
        layer = row["layer"]
        fixture_index = row["fixture_index"]
        if isinstance(layer, bool) or not isinstance(layer, int):
            raise OrientationViolation("orientation layer is not an integer")
        if isinstance(fixture_index, bool) or not isinstance(fixture_index, int):
            raise OrientationViolation("orientation fixture index is not an integer")
        observed_keys.append((layer, fixture_index))
        if row["fixture_seed"] != fixture_seed(layer, fixture_index):
            raise OrientationViolation("orientation fixture seed differs")
        expected_bindings = {
            "fixture_algorithm": FIXTURE_ALGORITHM,
            "j_lens_repository": protocol.J_LENS_SPEC["repository"],
            "j_lens_revision": protocol.J_LENS_SPEC["revision"],
            "j_lens_sha256": protocol.J_LENS_SPEC["sha256"],
            "release_config_sha256": RELEASE_CONFIG_SHA256,
            "upstream_reference_repository": UPSTREAM_REFERENCE_REPOSITORY,
            "upstream_reference_revision": UPSTREAM_REFERENCE_REVISION,
            "upstream_row_vector_implementation": UPSTREAM_ROW_VECTOR_IMPLEMENTATION,
            "transport_contract_sha256": TRANSPORT_CONTRACT_SHA256,
            "orientation_convention": protocol.J_LENS_SPEC["orientation"],
            "production_algorithm": PRODUCTION_ALGORITHM,
            "independent_reference_algorithm": REFERENCE_ALGORITHM,
            "wrong_orientation_algorithm": WRONG_ORIENTATION_ALGORITHM,
        }
        if any(row[field] != value for field, value in expected_bindings.items()):
            raise OrientationViolation("orientation algorithm/upstream binding differs")
        for field in (
            "fixture_fp32_sha256",
            "quantized_source_sha256",
            "production_output_sha256",
            "independent_reference_output_sha256",
            "wrong_orientation_output_sha256",
        ):
            _require_hex64(row[field], f"orientation row {offset}.{field}")
        correct_cosine = _finite_number(
            row["production_reference_cosine"], "production/reference cosine"
        )
        correct_rmse = _finite_number(
            row["production_reference_relative_rmse"],
            "production/reference relative RMSE",
        )
        wrong_cosine = _finite_number(
            row["wrong_reference_cosine"], "wrong/reference cosine"
        )
        wrong_rmse = _finite_number(
            row["wrong_reference_relative_rmse"], "wrong/reference relative RMSE"
        )
        if not -1.0 <= correct_cosine <= 1.0 or not -1.0 <= wrong_cosine <= 1.0:
            raise OrientationViolation("orientation cosine is outside [-1,1]")
        if correct_rmse < 0.0 or wrong_rmse < 0.0:
            raise OrientationViolation("orientation relative RMSE is negative")
        if not math.isclose(
            _finite_number(
                row["correct_minus_wrong_cosine_gap"], "orientation cosine gap"
            ),
            correct_cosine - wrong_cosine,
            rel_tol=0.0,
            abs_tol=1e-12,
        ) or not math.isclose(
            _finite_number(
                row["wrong_minus_correct_relative_rmse_margin"],
                "orientation RMSE margin",
            ),
            wrong_rmse - correct_rmse,
            rel_tol=0.0,
            abs_tol=1e-12,
        ):
            raise OrientationViolation("orientation metric margin differs")
        expected_production, expected_wrong, expected_status = _row_statuses(
            correct_cosine=correct_cosine,
            correct_rmse=correct_rmse,
            wrong_cosine=wrong_cosine,
            wrong_rmse=wrong_rmse,
        )
        if row["finite"] is not True:
            expected_production = expected_wrong = expected_status = "fail"
        if (
            row["production_reference_status"] != expected_production
            or row["wrong_orientation_control_status"] != expected_wrong
            or row["status"] != expected_status
        ):
            raise OrientationViolation("orientation row gate decision differs")
        for field in (
            "model_forward_count",
            "target_prompt_render_count",
            "target_forward_count",
            "target_outcome_count",
        ):
            if row[field] != 0:
                raise OrientationViolation(f"orientation row used prohibited {field}")
        if row["prior_outcome_inputs"] != []:
            raise OrientationViolation("orientation row used predecessor outcomes")
        production_statuses.append(expected_production)
        wrong_statuses.append(expected_wrong)
    if observed_keys != expected_keys:
        raise OrientationViolation("orientation layer/fixture inventory or order differs")
    production_status = "pass" if set(production_statuses) == {"pass"} else "fail"
    wrong_status = "pass" if set(wrong_statuses) == {"pass"} else "fail"
    return {
        "status": (
            "pass"
            if production_status == "pass" and wrong_status == "pass"
            else "fail"
        ),
        "production_reference_status": production_status,
        "wrong_orientation_control_status": wrong_status,
        "row_count": len(materialized),
        "rows_canonical_sha256": protocol.canonical_sha256(materialized),
        "rows_file_sha256": _canonical_jsonl_sha256(materialized),
    }


def build_orientation_receipt(
    rows: Iterable[Mapping[str, Any]], *, plan_manifest_sha256: str
) -> dict[str, Any]:
    materialized = [dict(row) for row in rows]
    validation = validate_orientation_rows(
        materialized, plan_manifest_sha256=plan_manifest_sha256
    )
    core = {
        "schema_version": ORIENTATION_SCHEMA_VERSION,
        "status": validation["status"],
        "study_id": protocol.STUDY_ID,
        "protocol_version": protocol.PROTOCOL_VERSION,
        "plan_manifest_sha256": plan_manifest_sha256,
        "j_lens_repository": protocol.J_LENS_SPEC["repository"],
        "j_lens_revision": protocol.J_LENS_SPEC["revision"],
        "j_lens_sha256": protocol.J_LENS_SPEC["sha256"],
        "release_config_sha256": RELEASE_CONFIG_SHA256,
        "upstream_reference_repository": UPSTREAM_REFERENCE_REPOSITORY,
        "upstream_reference_revision": UPSTREAM_REFERENCE_REVISION,
        "upstream_row_vector_implementation": UPSTREAM_ROW_VECTOR_IMPLEMENTATION,
        "transport_contract_sha256": TRANSPORT_CONTRACT_SHA256,
        "orientation_convention": protocol.J_LENS_SPEC["orientation"],
        "fixture_algorithm": FIXTURE_ALGORITHM,
        "fixture_count_per_layer": FIXTURE_COUNT,
        "layer_count": len(protocol.J_LAYERS),
        "layers_sha256": LAYERS_SHA256,
        "row_count": validation["row_count"],
        "rows_canonical_sha256": validation["rows_canonical_sha256"],
        "rows_file_sha256": validation["rows_file_sha256"],
        "production_algorithm": PRODUCTION_ALGORITHM,
        "independent_reference_algorithm": REFERENCE_ALGORITHM,
        "wrong_orientation_algorithm": WRONG_ORIENTATION_ALGORITHM,
        "production_reference_status": validation["production_reference_status"],
        "wrong_orientation_control_status": validation[
            "wrong_orientation_control_status"
        ],
        "model_forward_count": 0,
        "target_prompt_render_count": 0,
        "target_forward_count": 0,
        "target_outcome_count": 0,
        "prior_outcome_inputs": [],
    }
    receipt = {**core, "receipt_sha256": protocol.canonical_sha256(core)}
    validate_orientation_receipt(
        receipt, rows=materialized, plan_manifest_sha256=plan_manifest_sha256
    )
    return receipt


def validate_orientation_receipt(
    receipt: Mapping[str, Any],
    *,
    rows: Iterable[Mapping[str, Any]] | None = None,
    plan_manifest_sha256: str | None = None,
    require_pass: bool = False,
) -> dict[str, Any]:
    _require_exact_fields(receipt, ORIENTATION_RECEIPT_FIELDS, "orientation receipt")
    core = dict(receipt)
    supplied_hash = core.pop("receipt_sha256", None)
    _require_hex64(supplied_hash, "orientation receipt self-hash")
    if protocol.canonical_sha256(core) != supplied_hash:
        raise OrientationViolation("orientation receipt self-hash differs")
    expected_plan = (
        receipt["plan_manifest_sha256"]
        if plan_manifest_sha256 is None
        else plan_manifest_sha256
    )
    _require_hex64(expected_plan, "orientation receipt plan")
    if (
        receipt["schema_version"] != ORIENTATION_SCHEMA_VERSION
        or receipt["study_id"] != protocol.STUDY_ID
        or receipt["protocol_version"] != protocol.PROTOCOL_VERSION
        or receipt["plan_manifest_sha256"] != expected_plan
    ):
        raise OrientationViolation("orientation receipt identity differs")
    expected_bindings = {
        "j_lens_repository": protocol.J_LENS_SPEC["repository"],
        "j_lens_revision": protocol.J_LENS_SPEC["revision"],
        "j_lens_sha256": protocol.J_LENS_SPEC["sha256"],
        "release_config_sha256": RELEASE_CONFIG_SHA256,
        "upstream_reference_repository": UPSTREAM_REFERENCE_REPOSITORY,
        "upstream_reference_revision": UPSTREAM_REFERENCE_REVISION,
        "upstream_row_vector_implementation": UPSTREAM_ROW_VECTOR_IMPLEMENTATION,
        "transport_contract_sha256": TRANSPORT_CONTRACT_SHA256,
        "orientation_convention": protocol.J_LENS_SPEC["orientation"],
        "fixture_algorithm": FIXTURE_ALGORITHM,
        "fixture_count_per_layer": FIXTURE_COUNT,
        "layer_count": len(protocol.J_LAYERS),
        "layers_sha256": LAYERS_SHA256,
        "row_count": EXPECTED_ROW_COUNT,
        "production_algorithm": PRODUCTION_ALGORITHM,
        "independent_reference_algorithm": REFERENCE_ALGORITHM,
        "wrong_orientation_algorithm": WRONG_ORIENTATION_ALGORITHM,
    }
    if any(receipt[field] != value for field, value in expected_bindings.items()):
        raise OrientationViolation("orientation receipt algorithm/upstream binding differs")
    for field in (
        "rows_canonical_sha256",
        "rows_file_sha256",
    ):
        _require_hex64(receipt[field], f"orientation receipt.{field}")
    for field in (
        "production_reference_status",
        "wrong_orientation_control_status",
        "status",
    ):
        if receipt[field] not in {"pass", "fail"}:
            raise OrientationViolation("orientation receipt status is invalid")
    expected_overall = (
        "pass"
        if receipt["production_reference_status"] == "pass"
        and receipt["wrong_orientation_control_status"] == "pass"
        else "fail"
    )
    if receipt["status"] != expected_overall:
        raise OrientationViolation("orientation receipt aggregate status differs")
    if require_pass and receipt["status"] != "pass":
        raise OrientationViolation("orientation gate did not pass")
    for field in (
        "model_forward_count",
        "target_prompt_render_count",
        "target_forward_count",
        "target_outcome_count",
    ):
        if receipt[field] != 0:
            raise OrientationViolation(f"orientation receipt used prohibited {field}")
    if receipt["prior_outcome_inputs"] != []:
        raise OrientationViolation("orientation receipt used predecessor outcomes")
    if rows is not None:
        validation = validate_orientation_rows(
            rows, plan_manifest_sha256=expected_plan
        )
        for field in (
            "status",
            "production_reference_status",
            "wrong_orientation_control_status",
            "row_count",
            "rows_canonical_sha256",
            "rows_file_sha256",
        ):
            if receipt[field] != validation[field]:
                raise OrientationViolation(
                    f"orientation receipt does not bind exact rows: {field}"
                )
    return dict(receipt)

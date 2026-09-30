"""Bounded experimental coordinate repairs, NOT proprietary SAE replication.

``decoder_span`` solves (E_selected @ D_selected) a = shift, then edits D a.
``encoder_min_norm`` solves (E_selected @ E_selected.T) a = shift, then edits
E_selected.T a. The latter need not lie in the decoder span. Neither operator
is the historical decoder-delta intervention or a claim about model behavior.

Full-native, full-width, token1 re-encoding is authoritative. Selected FP32
preactivations are separate geometry diagnostics. Only selected weights are
promoted to FP32; no full-dictionary FP32 copy, clipping, regularization, or
fallback is permitted. All computation disables autocast and TF32, with one
final native cast of h.float() + edit. Production native dtype is BF16; FP32
is also accepted for CPU algebra tests. Feature groups contain one or six IDs.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import torch
import torch.nn.functional as F

from experiments.sae_assay_diagnostic.backend import (
    ACTIVATION_COLUMNS,
    ENCODING_AUTHORITY,
    REFERENCE_COLUMNS,
    _canonical_encode,
    _finite,
    _finite_chunks,
    _fp32_math,
    _ids,
    _linear_token1,
)


OPERATORS = ("decoder_span", "encoder_min_norm")
CONDITION_LIMIT = 1e6
TELEMETRY_SCHEMA = "sae_assay_repair_operators_v1"
DELIVERY = ("cosine", "relative_error", "requested_norm", "realized_norm", "clean_norm")
PREACTIVATION_COLUMNS = (
    "fp32_preact", "desired_preact", "requested_preact_delta",
    "ideal_fp32_preact", "actual_fp32_preact",
)


@dataclass(frozen=True, eq=False)
class Geometry:
    """Reusable selected FP32 geometry; treat its tensor fields as read-only.

    Native sources are references, not copies. Conditioning is checked for the
    explicitly requested operator at repair time: a singular decoder response
    must not disqualify an independently requested, valid encoder diagnostic.
    """

    feature_ids: tuple[int, ...]
    sources: tuple[torch.Tensor, torch.Tensor, torch.Tensor]
    index: torch.Tensor
    encoder: torch.Tensor
    bias: torch.Tensor
    decoder: torch.Tensor
    decoder_span: torch.Tensor
    encoder_min_norm: torch.Tensor
    decoder_span_condition: torch.Tensor
    encoder_min_norm_condition: torch.Tensor


def _validate_weights(encoder, bias, decoder):
    if (encoder.ndim != 2 or min(encoder.shape) == 0
            or bias.shape != (encoder.shape[0],)
            or decoder.shape != (encoder.shape[1], encoder.shape[0])):
        raise ValueError("Expected full SAE shapes [features, hidden], [features], [hidden, features]")
    if encoder.dtype not in (torch.bfloat16, torch.float32):
        raise ValueError("Native dtype must be BF16 or FP32")
    if any(t.dtype != encoder.dtype or t.device != encoder.device for t in (bias, decoder)):
        raise ValueError("SAE weights must share native dtype and device")


def _feature_ids(feature_ids, width):
    ids = _ids(feature_ids, width)
    if len(ids) not in (1, 6):
        raise ValueError("Feature groups must contain one or six IDs")
    return ids


@torch.inference_mode()
def prepare_geometry(
    encoder: torch.Tensor,
    bias: torch.Tensor,
    decoder: torch.Tensor,
    feature_ids: Sequence[int],
) -> Geometry:
    """Prepare both small solve matrices without choosing or inverting either.

    Nonfinite weights fail here. Both matrix conditions are stored, including
    nonfinite conditions for invalid systems. Singular, nonfinite, or condition
    > 1e6 systems fail only when that operator is requested, even at strength 0.
    Reuse with unchanged source tensors and the same ordered feature IDs only.
    """
    _validate_weights(encoder, bias, decoder)
    ids = _feature_ids(feature_ids, encoder.shape[0])
    for name, tensor in (("encoder", encoder), ("bias", bias), ("decoder", decoder)):
        _finite_chunks(name, tensor)
    index = torch.tensor(ids, dtype=torch.long, device=encoder.device)
    with _fp32_math(encoder.device):
        e = encoder.index_select(0, index).float()
        b = bias.index_select(0, index).float()
        d = decoder.index_select(1, index).float()
        response = e @ d
        gram = e @ e.T
        response_condition = _matrix_condition(response)
        gram_condition = _matrix_condition(gram)
    return Geometry(ids, (encoder, bias, decoder), index, e, b, d, response, gram,
                    response_condition, gram_condition)


def _check_geometry(geometry, encoder, bias, decoder, ids):
    if (not isinstance(geometry, Geometry) or geometry.feature_ids != ids
            or any(a is not b for a, b in zip(geometry.sources, (encoder, bias, decoder)))):
        raise ValueError("Geometry must match source tensors and ordered feature IDs")
    # Compare only selected weights, including for sources created in inference mode.
    for source, dim, saved in ((encoder, 0, geometry.encoder),
                               (bias, 0, geometry.bias), (decoder, 1, geometry.decoder)):
        selected = source.index_select(dim, geometry.index).float()
        _finite("selected geometry source", selected)
        if not torch.equal(selected, saved):
            raise ValueError("Stale geometry: selected weights changed; prepare again")


def _matrix_condition(matrix):
    # An invalid unrequested system is retained, not used as a fallback or veto.
    if not bool(torch.isfinite(matrix).all()):
        return matrix.new_full((), float("nan"))
    try:
        return torch.linalg.cond(matrix, p=2)
    except torch.linalg.LinAlgError:
        return matrix.new_full((), float("nan"))


def _check_condition(matrix, condition, operator):
    _finite(f"{operator} solve matrix", matrix)
    if not bool(torch.isfinite(condition)) or bool(condition > CONDITION_LIMIT):
        raise ValueError(f"{operator}: singular or condition > {CONDITION_LIMIT:g} or unavailable ({condition.item():g})")


@torch.inference_mode()
def repair_hidden(
    hidden: torch.Tensor,
    encoder: torch.Tensor,
    bias: torch.Tensor,
    decoder: torch.Tensor,
    *,
    feature_ids: Sequence[int],
    mode: str | None,
    strength: float,
    q90: Sequence[float] | torch.Tensor | None = None,
    operator: str,
    geometry: Geometry | None = None,
) -> tuple[torch.Tensor, dict[str, torch.Tensor]]:
    """Return edited hidden states and finite, tensor-only delivery telemetry.

    Strength is 0, .5, or 1; mode=None is allowed only for true zero. Zero
    strength needs no q90 and returns the original object, even when native
    before differs from FP32 preactivation. Suppression eligibility is native
    before > 0; amplification eligibility is requested activation delta > 0.
    Ineligible FP32 preactivations are constrained to stay unchanged. Eligible
    shifts target the desired native activation, crossing negative preactivation
    when needed. There is no retry after BF16 rounding or native re-encoding.

    Activation/preactivation fields and solve coefficients have shape [..., k];
    edit fields [..., hidden]; delivery/position flags and condition [...].
    Scalar matrix conditions stay in geometry. Old activation/reference/delivery
    names retain their meanings. ``ideal_fp32_*`` describes h.float() +
    requested_edit, not delivered native activations. All numbers are FP32;
    flags are boolean.
    """
    _validate_weights(encoder, bias, decoder)
    ids = _feature_ids(feature_ids, encoder.shape[0])
    if (hidden.ndim < 2 or hidden.numel() == 0 or hidden.shape[-1] != encoder.shape[1]
            or hidden.dtype != encoder.dtype or hidden.device != encoder.device):
        raise ValueError("hidden must have nonempty position axes and share SAE width, native dtype and device")
    _finite("hidden", hidden)
    if isinstance(strength, bool) or strength not in (0.0, 0.5, 1.0):
        raise ValueError("strength must be 0, .5, or 1")
    if mode not in (None, "suppression", "amplification") or (mode is None and strength):
        raise ValueError("Invalid intervention mode")
    if operator not in OPERATORS:
        raise ValueError(f"operator must be one of {OPERATORS}")
    quantiles = None
    if mode == "amplification":
        if q90 is None and strength:
            raise ValueError("Amplification requires q90")
        if q90 is not None:
            quantiles = torch.as_tensor(q90, dtype=torch.float32, device=hidden.device)
            if quantiles.shape != (len(ids),):
                raise ValueError("q90 must match ordered feature IDs")
            _finite("q90", quantiles)
            if bool((quantiles < 0).any()):
                raise ValueError("q90 cannot be negative")
    if geometry is None:
        geometry = prepare_geometry(encoder, bias, decoder, ids)
    else:
        _check_geometry(geometry, encoder, bias, decoder, ids)

    with _fp32_math(hidden.device):
        matrix = getattr(geometry, operator)
        condition = getattr(geometry, operator + "_condition")
        _check_condition(matrix, condition, operator)
        before = _canonical_encode(hidden, encoder, bias, geometry.index).float()
        clean = hidden.float()
        preact = _linear_token1(clean, geometry.encoder, geometry.bias)
        _finite("FP32 preactivation", preact)
        desired = before.clone()
        requested_delta = torch.zeros_like(before)
        eligible = torch.zeros_like(before, dtype=torch.bool)
        if mode == "suppression":
            eligible = before > 0
            desired = (1.0 - strength) * before
            requested_delta = -strength * before
        elif mode == "amplification" and strength:
            requested_delta = strength * (quantiles - before).clamp_min(0)
            desired = before + requested_delta
            eligible = requested_delta > 0
        desired_preact = torch.where(eligible & (strength != 0), desired, preact)
        shift = desired_preact - preact
        _finite("requested preactivation delta", shift)
        if not bool(torch.count_nonzero(shift)):
            coefficients = torch.zeros_like(shift)
            requested = torch.zeros_like(clean)
            edited, after = hidden, before
        else:
            try:
                coefficients = torch.linalg.solve(matrix, shift.reshape(-1, len(ids)).T).T.reshape_as(shift)
            except torch.linalg.LinAlgError as exc:
                raise ValueError(f"{operator}: solve failed; no fallback") from exc
            _finite("solve coefficients", coefficients)
            basis = geometry.decoder if operator == "decoder_span" else geometry.encoder.T
            requested = _linear_token1(coefficients, basis)
            _finite("requested residual edit", requested)
            edited = (clean + requested).to(hidden.dtype)
            _finite("edited hidden", edited)
            after = _canonical_encode(edited, encoder, bias, geometry.index).float()

        ideal_preact = _linear_token1(clean + requested, geometry.encoder, geometry.bias)
        actual_preact = _linear_token1(edited.float(), geometry.encoder, geometry.bias)
        realized = edited.float() - clean
        requested_norm = torch.linalg.vector_norm(requested, dim=-1)
        realized_norm = torch.linalg.vector_norm(realized, dim=-1)
        nonzero = requested_norm > 0
        tiny = torch.finfo(torch.float32).tiny
        cosine = (requested * realized).sum(-1) / (requested_norm * realized_norm).clamp_min(tiny)
        error_norm = torch.linalg.vector_norm(realized - requested, dim=-1)
        metrics = {
            "before": before, "requested_delta": requested_delta,
            "requested_activation": desired, "after": after,
            "ideal_fp32_before": F.relu(preact),
            "ideal_fp32_after": F.relu(ideal_preact),
            "actual_fp32_after": F.relu(actual_preact),
            "fp32_preact": preact, "desired_preact": desired_preact,
            "requested_preact_delta": shift,
            "ideal_fp32_preact": ideal_preact, "actual_fp32_preact": actual_preact,
            "condition": condition.expand(hidden.shape[:-1]), "eligible": eligible,
            "solve_coefficients": coefficients,
            "solve_residual": _linear_token1(coefficients, matrix) - shift,
            "requested_edit": requested, "realized_edit": realized,
            "achieved_delta": after - before, "activation_error": after - desired,
            "requested_norm": requested_norm, "realized_norm": realized_norm,
            "clean_norm": torch.linalg.vector_norm(clean, dim=-1),
            "cosine": torch.where(nonzero, cosine.clamp(-1, 1), 1.0),
            "relative_error": torch.where(nonzero, error_norm / requested_norm.clamp_min(tiny), 0.0),
            "identity": (edited == hidden).all(-1),
            "valid": torch.ones(hidden.shape[:-1], dtype=torch.bool, device=hidden.device),
            "nonzero_requested": nonzero,
        }
        for name, tensor in metrics.items():
            _finite(name, tensor)
    return edited, metrics

"""Pure J-lens readout algebra and packed vocabulary helpers.

The canonical contract is explicit and intentionally independent of model
hooks::

    source residual @ J_layer.T -> Llama RMSNorm -> LM-head rows

``source residual`` is the archived pre-transport vector.  J transport uses the
matrix's dtype unless a caller explicitly supplies another dtype; RMSNorm
accumulates its variance in float32, exactly as Hugging Face LlamaRMSNorm does;
and returned logits are float32.  Functions accept arbitrary leading residual
dimensions and batch the expensive row/vocabulary operations.

Vocabulary rankings are exploratory browse indexes.  Paired contrast rows keep
both arm scores for the union of the positive and negative tails so a delta is
never detached from its underlying values.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Mapping, Sequence


VOCAB_MATERIALIZATION_K = {
    "event0": 2_000,
    "probe0_answer": 2_000,
    "probe4_answer": 512,
    "probe16_answer": 512,
    "terminal_answer": 512,
    "fixed_prequery": 2_000,
    "fixed_answer": 2_000,
}

FROZEN_VOCAB_CONTRASTS = (
    "target_supp_minus_never",
    "target_amp_minus_never",
    "matched_supp_minus_never",
    "matched_amp_minus_never",
    "isotropic_supp_minus_never",
    "isotropic_amp_minus_never",
    "target_minus_matched_sign_oriented",
)


class ReadoutContractError(ValueError):
    """Raised when tensors or packed rows violate the frozen readout contract."""


class ReplayEquivalenceError(ReadoutContractError):
    """Raised when a replay fixture does not reproduce its live reference."""


@dataclass(frozen=True)
class TopKReadout:
    """Batched top-k result; tensors have shape ``[..., K]``."""

    token_ids: Any
    scores: Any


def validate_vocab_materialization(
    *, checkpoint: str, k: int, contrast_id: str | None = None
) -> None:
    """Fail if a runtime attempts an outcome-contingent checkpoint/K/contrast."""

    expected = VOCAB_MATERIALIZATION_K.get(checkpoint)
    if expected is None:
        raise ReadoutContractError(
            f"vocabulary materialization is not frozen at checkpoint {checkpoint!r}"
        )
    if k != expected:
        raise ReadoutContractError(
            f"checkpoint {checkpoint!r} requires K={expected}, got K={k}"
        )
    if contrast_id is not None and contrast_id not in FROZEN_VOCAB_CONTRASTS:
        raise ReadoutContractError(f"unregistered vocabulary contrast: {contrast_id!r}")


def _torch() -> Any:
    try:
        import torch
    except ImportError as exc:
        raise ReadoutContractError("PyTorch is required for tensor readouts") from exc
    return torch


def _shape(value: Any, *, label: str) -> tuple[int, ...]:
    if not hasattr(value, "shape"):
        raise ReadoutContractError(f"{label} is not tensor-like")
    return tuple(int(size) for size in value.shape)


def _validate_core_shapes(
    residuals: Any,
    jacobian: Any,
    norm_weight: Any,
    lm_head_weight: Any,
) -> tuple[tuple[int, ...], int, int]:
    residual_shape = _shape(residuals, label="source residuals")
    jacobian_shape = _shape(jacobian, label="J map")
    norm_shape = _shape(norm_weight, label="RMSNorm weight")
    head_shape = _shape(lm_head_weight, label="LM-head weight")
    if len(residual_shape) < 2:
        raise ReadoutContractError("source residuals require shape [..., hidden]")
    hidden = residual_shape[-1]
    if hidden <= 0 or jacobian_shape != (hidden, hidden):
        raise ReadoutContractError(
            f"J map must have shape [{hidden}, {hidden}], got {jacobian_shape}"
        )
    if norm_shape != (hidden,):
        raise ReadoutContractError(
            f"RMSNorm weight must have shape [{hidden}], got {norm_shape}"
        )
    if len(head_shape) != 2 or head_shape[1] != hidden or head_shape[0] <= 0:
        raise ReadoutContractError(
            f"LM-head weight must have shape [vocab, {hidden}], got {head_shape}"
        )
    return residual_shape, hidden, head_shape[0]


def _validate_row_batch_size(row_batch_size: int) -> int:
    if not isinstance(row_batch_size, int) or row_batch_size <= 0:
        raise ReadoutContractError("row_batch_size must be a positive integer")
    return row_batch_size


def jlens_transport(
    source_residuals: Any,
    jacobian: Any,
    *,
    row_batch_size: int = 64,
    transport_dtype: Any | None = None,
) -> Any:
    """Apply ``source_residual @ J.T`` in bounded row batches."""

    torch = _torch()
    residual_shape = _shape(source_residuals, label="source residuals")
    jacobian_shape = _shape(jacobian, label="J map")
    if len(residual_shape) < 2:
        raise ReadoutContractError("source residuals require shape [..., hidden]")
    hidden = residual_shape[-1]
    if jacobian_shape != (hidden, hidden):
        raise ReadoutContractError(
            f"J map must have shape [{hidden}, {hidden}], got {jacobian_shape}"
        )
    if getattr(source_residuals, "device", None) != getattr(jacobian, "device", None):
        raise ReadoutContractError("source residual and J map must share a device")
    row_batch_size = _validate_row_batch_size(row_batch_size)
    flat = source_residuals.reshape(-1, hidden)
    if flat.shape[0] == 0:
        raise ReadoutContractError("source residual batch may not be empty")
    dtype = jacobian.dtype if transport_dtype is None else transport_dtype
    matrix = jacobian if jacobian.dtype == dtype else jacobian.to(dtype=dtype)
    outputs = [
        flat[start : start + row_batch_size].to(dtype=dtype) @ matrix.T
        for start in range(0, flat.shape[0], row_batch_size)
    ]
    return torch.cat(outputs, dim=0).reshape(*residual_shape[:-1], hidden)


def llama_rms_norm(hidden_states: Any, norm_weight: Any, *, eps: float) -> Any:
    """Pure Hugging Face LlamaRMSNorm algebra with float32 variance."""

    torch = _torch()
    shape = _shape(hidden_states, label="hidden states")
    weight_shape = _shape(norm_weight, label="RMSNorm weight")
    if len(shape) < 2 or weight_shape != (shape[-1],):
        raise ReadoutContractError(
            f"RMSNorm weight must match hidden width {shape[-1] if shape else None}"
        )
    if not isinstance(eps, (float, int)) or not math.isfinite(float(eps)) or eps <= 0:
        raise ReadoutContractError("RMSNorm eps must be finite and positive")
    input_dtype = hidden_states.dtype
    states_float = hidden_states.to(torch.float32)
    variance = states_float.square().mean(dim=-1, keepdim=True)
    normalized = states_float * torch.rsqrt(variance + float(eps))
    return norm_weight * normalized.to(input_dtype)


def jlens_normalized_hidden(
    source_residuals: Any,
    jacobian: Any,
    norm_weight: Any,
    *,
    eps: float,
    row_batch_size: int = 64,
    transport_dtype: Any | None = None,
) -> tuple[Any, Any]:
    """Return transported and RMS-normalized hidden states under the contract."""

    transported = jlens_transport(
        source_residuals,
        jacobian,
        row_batch_size=row_batch_size,
        transport_dtype=transport_dtype,
    )
    # The runtime calls model.norm after casting to the norm weight dtype.  Keep
    # that cast explicit so replay does not silently inherit a caller's dtype.
    normalized = llama_rms_norm(
        transported.to(dtype=norm_weight.dtype), norm_weight, eps=eps
    )
    return transported, normalized


def _token_id_tensor(token_ids: Sequence[int] | Any, *, vocab: int, device: Any) -> Any:
    torch = _torch()
    if hasattr(token_ids, "detach"):
        ids = token_ids.detach().to(device=device, dtype=torch.long).reshape(-1)
    else:
        ids = torch.tensor(list(token_ids), device=device, dtype=torch.long)
    if ids.numel() == 0:
        raise ReadoutContractError("selected token ID list may not be empty")
    if bool(((ids < 0) | (ids >= vocab)).any().item()):
        raise ReadoutContractError(f"selected token IDs must lie in [0, {vocab})")
    if int(torch.unique(ids).numel()) != int(ids.numel()):
        raise ReadoutContractError("selected token IDs must be unique")
    return ids


def selected_lm_head_logits(
    normalized_hidden: Any,
    lm_head_weight: Any,
    token_ids: Sequence[int] | Any,
    *,
    row_batch_size: int = 128,
) -> Any:
    """Multiply only selected LM-head rows and return float32 logits."""

    torch = _torch()
    hidden_shape = _shape(normalized_hidden, label="normalized hidden")
    head_shape = _shape(lm_head_weight, label="LM-head weight")
    if len(hidden_shape) < 2 or len(head_shape) != 2 or hidden_shape[-1] != head_shape[1]:
        raise ReadoutContractError("normalized hidden and LM-head shapes are incompatible")
    if getattr(normalized_hidden, "device", None) != getattr(
        lm_head_weight, "device", None
    ):
        raise ReadoutContractError("normalized hidden and LM head must share a device")
    row_batch_size = _validate_row_batch_size(row_batch_size)
    ids = _token_id_tensor(
        token_ids, vocab=head_shape[0], device=lm_head_weight.device
    )
    selected_weight = lm_head_weight.index_select(0, ids)
    flat = normalized_hidden.reshape(-1, hidden_shape[-1])
    outputs = [
        (
            flat[start : start + row_batch_size].to(dtype=selected_weight.dtype)
            @ selected_weight.T
        ).float()
        for start in range(0, flat.shape[0], row_batch_size)
    ]
    return torch.cat(outputs, dim=0).reshape(*hidden_shape[:-1], ids.numel())


def jlens_selected_logits(
    source_residuals: Any,
    jacobian: Any,
    norm_weight: Any,
    lm_head_weight: Any,
    token_ids: Sequence[int] | Any,
    *,
    eps: float,
    row_batch_size: int = 64,
    transport_dtype: Any | None = None,
) -> Any:
    """Compute selected-token logits via J transport, RMSNorm, and LM head."""

    _validate_core_shapes(source_residuals, jacobian, norm_weight, lm_head_weight)
    _, normalized = jlens_normalized_hidden(
        source_residuals,
        jacobian,
        norm_weight,
        eps=eps,
        row_batch_size=row_batch_size,
        transport_dtype=transport_dtype,
    )
    return selected_lm_head_logits(
        normalized,
        lm_head_weight,
        token_ids,
        row_batch_size=row_batch_size,
    )


def full_lm_head_logits(
    normalized_hidden: Any,
    lm_head_weight: Any,
    *,
    row_batch_size: int = 32,
) -> Any:
    """Materialize complete float32 logits in bounded row batches."""

    torch = _torch()
    shape = _shape(normalized_hidden, label="normalized hidden")
    head_shape = _shape(lm_head_weight, label="LM-head weight")
    if len(shape) < 2 or len(head_shape) != 2 or shape[-1] != head_shape[1]:
        raise ReadoutContractError("normalized hidden and LM-head shapes are incompatible")
    row_batch_size = _validate_row_batch_size(row_batch_size)
    flat = normalized_hidden.reshape(-1, shape[-1])
    rows = [
        (
            flat[start : start + row_batch_size].to(dtype=lm_head_weight.dtype)
            @ lm_head_weight.T
        ).float()
        for start in range(0, flat.shape[0], row_batch_size)
    ]
    return torch.cat(rows, dim=0).reshape(*shape[:-1], head_shape[0])


def jlens_full_logits(
    source_residuals: Any,
    jacobian: Any,
    norm_weight: Any,
    lm_head_weight: Any,
    *,
    eps: float,
    row_batch_size: int = 32,
    transport_dtype: Any | None = None,
) -> Any:
    """Materialize the complete vocabulary only when a registered task needs it."""

    _validate_core_shapes(source_residuals, jacobian, norm_weight, lm_head_weight)
    _, normalized = jlens_normalized_hidden(
        source_residuals,
        jacobian,
        norm_weight,
        eps=eps,
        row_batch_size=row_batch_size,
        transport_dtype=transport_dtype,
    )
    return full_lm_head_logits(
        normalized, lm_head_weight, row_batch_size=row_batch_size
    )


def _stable_topk(values: Any, token_ids: Any, *, k: int, largest: bool) -> TopKReadout:
    """Lexicographic top-k: score first, lower token ID breaks exact ties."""

    torch = _torch()
    if values.ndim != 2:
        raise ReadoutContractError("top-k candidate values must have shape [rows, items]")
    if token_ids.ndim == 1:
        token_ids = token_ids.unsqueeze(0).expand(values.shape[0], -1)
    if token_ids.shape != values.shape:
        raise ReadoutContractError("top-k IDs and scores must have identical shapes")
    if not 0 < k <= values.shape[1]:
        raise ReadoutContractError(f"K must lie in [1, {values.shape[1]}]")
    # Sorting IDs first and then applying a stable score sort gives a defined
    # token-ID tie break without perturbing scientific scores.
    by_id = torch.argsort(token_ids, dim=-1, descending=False, stable=True)
    ids_by_id = token_ids.gather(-1, by_id)
    values_by_id = values.gather(-1, by_id)
    by_score = torch.argsort(
        values_by_id, dim=-1, descending=largest, stable=True
    )[:, :k]
    return TopKReadout(
        token_ids=ids_by_id.gather(-1, by_score),
        scores=values_by_id.gather(-1, by_score),
    )


def topk_lm_head_logits(
    normalized_hidden: Any,
    lm_head_weight: Any,
    *,
    k: int,
    largest: bool = True,
    row_batch_size: int = 16,
    vocab_chunk_size: int = 8192,
) -> TopKReadout:
    """Exact deterministic top-k without retaining a dense vocabulary tensor."""

    torch = _torch()
    shape = _shape(normalized_hidden, label="normalized hidden")
    head_shape = _shape(lm_head_weight, label="LM-head weight")
    if len(shape) < 2 or len(head_shape) != 2 or shape[-1] != head_shape[1]:
        raise ReadoutContractError("normalized hidden and LM-head shapes are incompatible")
    vocab = head_shape[0]
    if not isinstance(k, int) or not 0 < k <= vocab:
        raise ReadoutContractError(f"K must lie in [1, {vocab}]")
    row_batch_size = _validate_row_batch_size(row_batch_size)
    if not isinstance(vocab_chunk_size, int) or vocab_chunk_size <= 0:
        raise ReadoutContractError("vocab_chunk_size must be a positive integer")
    flat = normalized_hidden.reshape(-1, shape[-1])
    all_ids: list[Any] = []
    all_scores: list[Any] = []
    for row_start in range(0, flat.shape[0], row_batch_size):
        states = flat[row_start : row_start + row_batch_size]
        best: TopKReadout | None = None
        for vocab_start in range(0, vocab, vocab_chunk_size):
            vocab_stop = min(vocab, vocab_start + vocab_chunk_size)
            weight = lm_head_weight[vocab_start:vocab_stop]
            logits = (states.to(dtype=weight.dtype) @ weight.T).float()
            ids = torch.arange(
                vocab_start, vocab_stop, device=logits.device, dtype=torch.long
            )
            local = _stable_topk(
                logits, ids, k=min(k, vocab_stop - vocab_start), largest=largest
            )
            if best is None:
                best = local
            else:
                best = _stable_topk(
                    torch.cat((best.scores, local.scores), dim=-1),
                    torch.cat((best.token_ids, local.token_ids), dim=-1),
                    k=min(k, best.scores.shape[-1] + local.scores.shape[-1]),
                    largest=largest,
                )
        if best is None or best.scores.shape[-1] != k:
            raise ReadoutContractError("top-k scan did not cover the complete vocabulary")
        all_ids.append(best.token_ids)
        all_scores.append(best.scores)
    output_shape = (*shape[:-1], k)
    return TopKReadout(
        token_ids=torch.cat(all_ids, dim=0).reshape(output_shape),
        scores=torch.cat(all_scores, dim=0).reshape(output_shape),
    )


def jlens_topk(
    source_residuals: Any,
    jacobian: Any,
    norm_weight: Any,
    lm_head_weight: Any,
    *,
    eps: float,
    k: int,
    largest: bool = True,
    row_batch_size: int = 16,
    vocab_chunk_size: int = 8192,
    transport_dtype: Any | None = None,
) -> TopKReadout:
    """Compute an exact top-k over every LM-head row after J transport."""

    _validate_core_shapes(source_residuals, jacobian, norm_weight, lm_head_weight)
    _, normalized = jlens_normalized_hidden(
        source_residuals,
        jacobian,
        norm_weight,
        eps=eps,
        row_batch_size=row_batch_size,
        transport_dtype=transport_dtype,
    )
    return topk_lm_head_logits(
        normalized,
        lm_head_weight,
        k=k,
        largest=largest,
        row_batch_size=row_batch_size,
        vocab_chunk_size=vocab_chunk_size,
    )


def _nested_rows(value: Any, *, label: str) -> list[list[Any]]:
    if hasattr(value, "detach"):
        value = value.detach().cpu().tolist()
    else:
        value = list(value)
    if not value:
        raise ReadoutContractError(f"{label} may not be empty")
    if isinstance(value[0], (int, float)):
        return [list(value)]
    rows = [list(row) for row in value]
    if not rows or not rows[0] or any(len(row) != len(rows[0]) for row in rows):
        raise ReadoutContractError(f"{label} must be a non-ragged [rows, vocab] array")
    return rows


def paired_delta_union_rows(
    left_scores: Any,
    right_scores: Any,
    *,
    k: int,
    row_ids: Sequence[str] | None = None,
    contrast_id: str | None = None,
) -> list[dict[str, Any]]:
    """Pack the union of both delta tails with exact paired-arm scores.

    Positive ranks sort ``left - right`` descending; negative ranks sort it
    ascending.  Exact ties use lower token ID.  A token appearing in both tails
    is emitted once with both ranks.
    """

    left = _nested_rows(left_scores, label="left scores")
    right = _nested_rows(right_scores, label="right scores")
    if len(left) != len(right) or any(
        len(left_row) != len(right_row)
        for left_row, right_row in zip(left, right)
    ):
        raise ReadoutContractError("paired score arrays must have identical shapes")
    vocab = len(left[0])
    if any(len(row) != vocab for row in left + right):
        raise ReadoutContractError("paired score arrays must be non-ragged")
    if not isinstance(k, int) or not 0 < k <= vocab:
        raise ReadoutContractError(f"K must lie in [1, {vocab}]")
    if contrast_id is not None and contrast_id not in FROZEN_VOCAB_CONTRASTS:
        raise ReadoutContractError(f"unregistered vocabulary contrast: {contrast_id!r}")
    if row_ids is None:
        row_ids = [str(index) for index in range(len(left))]
    if len(row_ids) != len(left) or len(set(row_ids)) != len(row_ids):
        raise ReadoutContractError("row_ids must be unique and match the row count")

    packed: list[dict[str, Any]] = []
    for row_id, left_row, right_row in zip(row_ids, left, right):
        values: list[tuple[int, float, float, float]] = []
        for token_id, (left_value, right_value) in enumerate(
            zip(left_row, right_row)
        ):
            left_value = float(left_value)
            right_value = float(right_value)
            delta = left_value - right_value
            if not all(math.isfinite(value) for value in (left_value, right_value, delta)):
                raise ReadoutContractError("paired vocabulary scores must be finite")
            values.append((token_id, left_value, right_value, delta))
        positive = sorted(values, key=lambda row: (-row[3], row[0]))[:k]
        negative = sorted(values, key=lambda row: (row[3], row[0]))[:k]
        positive_rank = {row[0]: rank for rank, row in enumerate(positive, start=1)}
        negative_rank = {row[0]: rank for rank, row in enumerate(negative, start=1)}
        by_token = {row[0]: row for row in values}
        for token_id in sorted(set(positive_rank) | set(negative_rank)):
            _, left_value, right_value, delta = by_token[token_id]
            record: dict[str, Any] = {
                "row_id": str(row_id),
                "token_id": token_id,
                "left_score": left_value,
                "right_score": right_value,
                "delta": delta,
                "positive_rank": positive_rank.get(token_id),
                "negative_rank": negative_rank.get(token_id),
            }
            if contrast_id is not None:
                record["contrast_id"] = contrast_id
            packed.append(record)
    return packed


def reference_jlens_selected_logits_python(
    source_residual: Sequence[float],
    jacobian: Sequence[Sequence[float]],
    norm_weight: Sequence[float],
    lm_head_weight: Sequence[Sequence[float]],
    token_ids: Sequence[int],
    *,
    eps: float,
) -> dict[str, list[float]]:
    """Small dependency-free reference used for orientation/arithmetic smoke tests."""

    residual = [float(value) for value in source_residual]
    hidden = len(residual)
    if hidden == 0 or len(jacobian) != hidden or any(
        len(row) != hidden for row in jacobian
    ):
        raise ReadoutContractError("reference J map must be square at residual width")
    if len(norm_weight) != hidden:
        raise ReadoutContractError("reference RMSNorm weight has the wrong width")
    if not eps > 0 or not math.isfinite(eps):
        raise ReadoutContractError("reference RMSNorm eps must be finite and positive")
    # Row j of J is dotted with the source: source @ J.T.
    transported = [
        sum(residual[index] * float(row[index]) for index in range(hidden))
        for row in jacobian
    ]
    variance = sum(value * value for value in transported) / hidden
    scale = 1.0 / math.sqrt(variance + eps)
    normalized = [
        transported[index] * scale * float(norm_weight[index])
        for index in range(hidden)
    ]
    logits: list[float] = []
    for token_id in token_ids:
        if not isinstance(token_id, int) or not 0 <= token_id < len(lm_head_weight):
            raise ReadoutContractError("reference token ID lies outside the LM head")
        weight = lm_head_weight[token_id]
        if len(weight) != hidden:
            raise ReadoutContractError("reference LM-head row has the wrong width")
        logits.append(
            sum(normalized[index] * float(weight[index]) for index in range(hidden))
        )
    return {
        "transported": transported,
        "normalized": normalized,
        "selected_logits": logits,
    }


def _flatten_numeric(value: Any, *, label: str) -> list[float]:
    if hasattr(value, "detach"):
        value = value.detach().cpu().tolist()
    output: list[float] = []

    def visit(item: Any) -> None:
        if isinstance(item, (list, tuple)):
            for child in item:
                visit(child)
        else:
            try:
                numeric = float(item)
            except (TypeError, ValueError) as exc:
                raise ReadoutContractError(f"{label} contains a non-number") from exc
            if not math.isfinite(numeric):
                raise ReadoutContractError(f"{label} contains a non-finite value")
            output.append(numeric)

    visit(value)
    if not output:
        raise ReadoutContractError(f"{label} may not be empty")
    return output


def _nested_shape(value: Any, *, label: str) -> tuple[int, ...]:
    if hasattr(value, "shape"):
        return tuple(int(size) for size in value.shape)
    if isinstance(value, (list, tuple)):
        if not value:
            return (0,)
        child_shapes = [_nested_shape(child, label=label) for child in value]
        if any(shape != child_shapes[0] for shape in child_shapes[1:]):
            raise ReadoutContractError(f"{label} is ragged")
        return (len(value), *child_shapes[0])
    if isinstance(value, (int, float)):
        return ()
    raise ReadoutContractError(f"{label} contains an unsupported value")


def _flatten_ids(value: Any, *, label: str) -> list[int]:
    values = _flatten_numeric(value, label=label)
    ids = [int(item) for item in values]
    if any(float(integer) != value for integer, value in zip(ids, values)):
        raise ReadoutContractError(f"{label} contains a non-integer token ID")
    return ids


def _numeric_equivalence(
    reference: Any,
    replay: Any,
    *,
    label: str,
    atol: float,
    rtol: float,
) -> dict[str, Any]:
    reference_shape = _nested_shape(reference, label=f"reference {label}")
    replay_shape = _nested_shape(replay, label=f"replay {label}")
    expected = _flatten_numeric(reference, label=f"reference {label}")
    observed = _flatten_numeric(replay, label=f"replay {label}")
    if reference_shape != replay_shape:
        return {
            "status": "fail",
            "values": min(len(expected), len(observed)),
            "reference_values": len(expected),
            "replay_values": len(observed),
            "reference_shape": list(reference_shape),
            "replay_shape": list(replay_shape),
            "max_absolute_error": None,
            "relative_l2_error": None,
        }
    differences = [abs(left - right) for left, right in zip(expected, observed)]
    squared_error = sum((left - right) ** 2 for left, right in zip(expected, observed))
    squared_reference = sum(value * value for value in expected)
    relative_l2 = math.sqrt(squared_error) / max(math.sqrt(squared_reference), 1e-30)
    passed = all(
        difference <= atol + rtol * abs(reference_value)
        for difference, reference_value in zip(differences, expected)
    )
    return {
        "status": "pass" if passed else "fail",
        "values": len(expected),
        "shape": list(reference_shape),
        "max_absolute_error": max(differences, default=0.0),
        "relative_l2_error": relative_l2,
        "atol": atol,
        "rtol": rtol,
    }


def replay_equivalence_report(
    *,
    reference_selected_logits: Any,
    replay_selected_logits: Any,
    reference_topk_token_ids: Any,
    replay_topk_token_ids: Any,
    reference_topk_scores: Any,
    replay_topk_scores: Any,
    reference_transported_norms: Any,
    replay_transported_norms: Any,
    atol: float,
    rtol: float,
) -> dict[str, Any]:
    """Compare live and archived-source replay outputs with frozen tolerances."""

    if not all(
        isinstance(value, (int, float)) and math.isfinite(float(value)) and value >= 0
        for value in (atol, rtol)
    ):
        raise ReadoutContractError("replay tolerances must be finite and non-negative")
    selected = _numeric_equivalence(
        reference_selected_logits,
        replay_selected_logits,
        label="selected logits",
        atol=float(atol),
        rtol=float(rtol),
    )
    topk_scores = _numeric_equivalence(
        reference_topk_scores,
        replay_topk_scores,
        label="top-k scores",
        atol=float(atol),
        rtol=float(rtol),
    )
    norms = _numeric_equivalence(
        reference_transported_norms,
        replay_transported_norms,
        label="transported norms",
        atol=float(atol),
        rtol=float(rtol),
    )
    reference_ids = _flatten_ids(reference_topk_token_ids, label="reference top-k IDs")
    replay_ids = _flatten_ids(replay_topk_token_ids, label="replay top-k IDs")
    reference_id_shape = _nested_shape(
        reference_topk_token_ids, label="reference top-k IDs"
    )
    replay_id_shape = _nested_shape(replay_topk_token_ids, label="replay top-k IDs")
    reference_score_shape = _nested_shape(
        reference_topk_scores, label="reference top-k scores"
    )
    replay_score_shape = _nested_shape(replay_topk_scores, label="replay top-k scores")
    shape_alignment = (
        reference_id_shape
        == replay_id_shape
        == reference_score_shape
        == replay_score_shape
    )
    ids_match = shape_alignment and reference_ids == replay_ids
    report = {
        "status": (
            "pass"
            if ids_match
            and selected["status"] == "pass"
            and topk_scores["status"] == "pass"
            and norms["status"] == "pass"
            else "fail"
        ),
        "selected_logits": selected,
        "topk_scores": topk_scores,
        "transported_norms": norms,
        "topk_token_ids": {
            "status": "pass" if ids_match else "fail",
            "values": min(len(reference_ids), len(replay_ids)),
            "reference_values": len(reference_ids),
            "replay_values": len(replay_ids),
            "reference_shape": list(reference_id_shape),
            "replay_shape": list(replay_id_shape),
            "score_shape_alignment": shape_alignment,
            "mismatch_count": (
                sum(left != right for left, right in zip(reference_ids, replay_ids))
                + abs(len(reference_ids) - len(replay_ids))
            ),
        },
    }
    return report


def assert_replay_equivalent(report: Mapping[str, Any]) -> None:
    if report.get("status") != "pass":
        raise ReplayEquivalenceError("archived-source readout replay differs from live")


def build_jlens_replay_snapshot(
    source_residuals: Any,
    jacobian: Any,
    norm_weight: Any,
    lm_head_weight: Any,
    selected_token_ids: Sequence[int] | Any,
    *,
    eps: float,
    k: int,
    row_batch_size: int = 16,
    vocab_chunk_size: int = 8192,
    transport_dtype: Any | None = None,
) -> dict[str, Any]:
    """Recompute all values required by a condition-blind replay fixture."""

    torch = _torch()
    transported, normalized = jlens_normalized_hidden(
        source_residuals,
        jacobian,
        norm_weight,
        eps=eps,
        row_batch_size=row_batch_size,
        transport_dtype=transport_dtype,
    )
    selected = selected_lm_head_logits(
        normalized,
        lm_head_weight,
        selected_token_ids,
        row_batch_size=row_batch_size,
    )
    topk = topk_lm_head_logits(
        normalized,
        lm_head_weight,
        k=k,
        largest=True,
        row_batch_size=row_batch_size,
        vocab_chunk_size=vocab_chunk_size,
    )
    norms = torch.linalg.vector_norm(transported.float(), dim=-1)
    return {
        "selected_logits": selected,
        "topk_token_ids": topk.token_ids,
        "topk_scores": topk.scores,
        "transported_norms": norms,
    }


def check_jlens_replay(
    source_residuals: Any,
    jacobian: Any,
    norm_weight: Any,
    lm_head_weight: Any,
    selected_token_ids: Sequence[int] | Any,
    reference: Mapping[str, Any],
    *,
    eps: float,
    k: int,
    atol: float,
    rtol: float,
    row_batch_size: int = 16,
    vocab_chunk_size: int = 8192,
    transport_dtype: Any | None = None,
) -> dict[str, Any]:
    """Recompute a BF16 source fixture and return its equivalence receipt."""

    replay = build_jlens_replay_snapshot(
        source_residuals,
        jacobian,
        norm_weight,
        lm_head_weight,
        selected_token_ids,
        eps=eps,
        k=k,
        row_batch_size=row_batch_size,
        vocab_chunk_size=vocab_chunk_size,
        transport_dtype=transport_dtype,
    )
    required = {
        "selected_logits",
        "topk_token_ids",
        "topk_scores",
        "transported_norms",
    }
    if not required.issubset(reference):
        missing = sorted(required - set(reference))
        raise ReadoutContractError(f"replay reference is missing fields: {missing}")
    return replay_equivalence_report(
        reference_selected_logits=reference["selected_logits"],
        replay_selected_logits=replay["selected_logits"],
        reference_topk_token_ids=reference["topk_token_ids"],
        replay_topk_token_ids=replay["topk_token_ids"],
        reference_topk_scores=reference["topk_scores"],
        replay_topk_scores=replay["topk_scores"],
        reference_transported_norms=reference["transported_norms"],
        replay_transported_norms=replay["transported_norms"],
        atol=atol,
        rtol=rtol,
    )

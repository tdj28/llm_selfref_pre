"""Small-rank FP32 geometry and native-dtype component delivery.

No model, hook, random global state, or experimental protocol is owned here.
Removal means patching from a zero donor. Restoration at a later site is a
separate patch operation, not a same-hook undo or evidence of causal rescue.
"""

from __future__ import annotations

import math
from numbers import Real

import torch


MAX_RANK = 8
_NATIVE_DTYPES = (torch.float16, torch.bfloat16, torch.float32)


def _finite(name: str, value: torch.Tensor) -> None:
    if not bool(torch.isfinite(value).all()):
        raise ValueError(f"{name} must be finite (including after FP32 arithmetic)")


def _scalar(name: str, value: float) -> float:
    if isinstance(value, bool) or not isinstance(value, Real) or not math.isfinite(value):
        raise ValueError(f"{name} must be a finite real scalar")
    return float(value)


def _norm(value: torch.Tensor) -> torch.Tensor:
    # Scaling avoids squared-norm underflow for small, nonzero directions.
    scale = value.abs().amax(dim=-1)
    safe = torch.where(scale > 0, scale, 1.0)
    result = scale * torch.linalg.vector_norm(value / safe.unsqueeze(-1), dim=-1)
    _finite("norm", result)
    return result


def _coordinates(value: torch.Tensor, basis: torch.Tensor) -> torch.Tensor:
    # Explicit rank-wise reductions avoid TF32 matmul and backend flag changes.
    return torch.stack([(value * column).sum(-1) for column in basis.unbind(1)], -1)


def _expand(coordinates: torch.Tensor, basis: torch.Tensor) -> torch.Tensor:
    result = coordinates[..., :1] * basis[:, 0]
    for index in range(1, basis.shape[1]):
        result = result + coordinates[..., index:index + 1] * basis[:, index]
    return result


def _validate_basis(basis: torch.Tensor, width: int, device: torch.device) -> None:
    if (not isinstance(basis, torch.Tensor) or basis.ndim != 2
            or basis.shape[0] != width or not 1 <= basis.shape[1] <= min(MAX_RANK, width)
            or basis.dtype != torch.float32 or basis.device != device):
        raise ValueError("basis must be FP32 [width, rank], rank 1..8, on the hidden device")
    _finite("basis", basis)
    gram = _coordinates(basis.T, basis)
    identity = torch.eye(basis.shape[1], dtype=torch.float32, device=device)
    if not torch.allclose(gram, identity, atol=2e-6, rtol=2e-6):
        raise ValueError("basis columns must be orthonormal and full rank")


@torch.no_grad()
def orthonormal_basis(candidate_rows: torch.Tensor, *, rank_rtol: float = 1e-6) -> torch.Tensor:
    """Return FP32 [width, rank] Q from 1..8 independent ordered rows.

Construction always runs on CPU, then transfers to the input device. Rows are
normalized before an explicit singular-value rank check (s_min > rtol*s_max).
Ordered, twice-reorthogonalized Gram-Schmidt preserves row ordering; each
column's largest absolute entry (first in a tie) is made positive. Dependent
or numerically deficient rows raise, never silently drop or replace directions.
Determinism is for a fixed input and numerical environment, not cross-version
bitwise reproducibility. No gradient graph is retained.
"""
    rank_rtol = _scalar("rank_rtol", rank_rtol)
    if not 0 < rank_rtol < 1:
        raise ValueError("rank_rtol must lie strictly between zero and one")
    if (not isinstance(candidate_rows, torch.Tensor) or candidate_rows.ndim != 2
            or not candidate_rows.is_floating_point()
            or not 1 <= candidate_rows.shape[0] <= min(MAX_RANK, candidate_rows.shape[1])):
        raise ValueError("candidate_rows must be floating [rank, width], rank 1..8 <= width")
    _finite("candidate_rows", candidate_rows)
    with torch.autocast(device_type="cpu", enabled=False):
        rows = candidate_rows.detach().to(device="cpu", dtype=torch.float32).clone()
        _finite("FP32 candidate_rows", rows)
        scales = rows.abs().amax(-1, keepdim=True)
        if bool((scales == 0).any()):
            raise ValueError("candidate_rows are rank deficient: zero row")
        rows = rows / scales
        rows = rows / _norm(rows).unsqueeze(-1)
        singular = torch.linalg.svdvals(rows)
        _finite("singular values", singular)
        if bool(singular[-1] <= rank_rtol * singular[0]):
            raise ValueError("candidate_rows are numerically rank deficient")
        columns = []
        for row in rows:
            residual = row.clone()
            for _ in range(2):
                for column in columns:
                    residual = residual - (residual * column).sum() * column
            length = _norm(residual)
            if bool(length <= rank_rtol):
                raise ValueError("candidate_rows are rank deficient after reorthogonalization")
            column = residual / length
            pivot = column.abs().argmax()
            columns.append(torch.where(column[pivot] < 0, -column, column))
        basis = torch.stack(columns, dim=1)
        _validate_basis(basis, rows.shape[1], basis.device)
    return basis.to(candidate_rows.device)


@torch.no_grad()
def random_orthonormal_basis(
    width: int, rank: int, *, seed: int, device: torch.device | str = "cpu",
) -> torch.Tensor:
    """Seeded rank-matched random orthonormal columns using a private CPU RNG.

Orthogonal means mutually orthogonal columns, not orthogonality to a target
subspace. Rank is explicit; no hidden rank reduction or rejection resampling.
"""
    if (isinstance(width, bool) or not isinstance(width, int) or width < 1
            or isinstance(rank, bool) or not isinstance(rank, int)
            or not 1 <= rank <= min(MAX_RANK, width)):
        raise ValueError("width and rank must be positive integers with rank <= min(8, width)")
    if isinstance(seed, bool) or not isinstance(seed, int) or not 0 <= seed < 2**63:
        raise ValueError("seed must be an integer in [0, 2**63)")
    generator = torch.Generator(device="cpu").manual_seed(seed)
    rows = torch.randn(rank, width, generator=generator, device="cpu", dtype=torch.float32)
    return orthonormal_basis(rows).to(device)


@torch.no_grad()
def patch_component(
    hidden: torch.Tensor,
    donor: torch.Tensor,
    basis: torch.Tensor,
    *,
    alpha: float = 1.0,
    sham: bool = False,
    requested_norm: float | torch.Tensor | None = None,
) -> tuple[torch.Tensor, dict[str, torch.Tensor]]:
    """Deliver cast_native(h.float() + alpha * Q Q.T (donor.float()-h.float())).

Hidden and donor must have identical nonempty [..., width] shape, device and
native dtype (FP32, BF16, or FP16). Q is FP32 [width, rank], rank 1..8.
All arithmetic is FP32 with autocast disabled, and inputs are never modified.
Zero alpha, sham, or an identically zero request returns the original object.

Optional requested_norm is a finite positive scalar or a tensor with exactly
the position shape [...]. It rescales the alpha-weighted comparator delta
per position to that final requested norm, overriding its original magnitude.
Any zero source delta fails; no direction is invented. Matching is invalid
for sham/zero-alpha operations. Donor broadcasting is deliberately forbidden.

Telemetry contains FP32 before/after snapshots and requested/actual deltas
([... , width]), coordinates ([..., rank]), and per-position norms, cosine,
relative_error and norm_ratio (actual/requested). Zero requests use cosine=1,
relative_error=0, norm_ratio=1. A nonzero request rounded to zero uses 0, 1,
0 respectively, with rounded_to_zero=True. No rescaling retries delivery.
Boolean identity describes unchanged values, not Python object identity.
"""
    alpha = _scalar("alpha", alpha)
    if not 0 <= alpha <= 1:
        raise ValueError("alpha must be in [0, 1]")
    if not isinstance(sham, bool):
        raise ValueError("sham must be boolean")
    if (not isinstance(hidden, torch.Tensor) or hidden.ndim < 1 or hidden.numel() == 0
            or hidden.dtype not in _NATIVE_DTYPES):
        raise ValueError("hidden must be nonempty [..., width] in FP32, BF16 or FP16")
    if (not isinstance(donor, torch.Tensor) or donor.shape != hidden.shape
            or donor.dtype != hidden.dtype or donor.device != hidden.device):
        raise ValueError("donor must match hidden shape, device and dtype exactly")
    _finite("hidden", hidden)
    _finite("donor", donor)
    with torch.autocast(device_type=hidden.device.type, enabled=False):
        _validate_basis(basis, hidden.shape[-1], hidden.device)
        before = hidden.float().clone()
        donor32 = donor.float()
        before_coordinates = _coordinates(before, basis)
        donor_coordinates = _coordinates(donor32, basis)
        if alpha == 0 or sham:
            requested = torch.zeros_like(before)
        else:
            difference = donor32 - before
            _finite("donor difference", difference)
            requested = alpha * _expand(_coordinates(difference, basis), basis)
        _finite("requested_delta", requested)
        source_norm = _norm(requested)
        if requested_norm is not None:
            if sham or alpha == 0:
                raise ValueError("requested_norm cannot be combined with sham or zero alpha")
            if isinstance(requested_norm, torch.Tensor):
                if (not requested_norm.is_floating_point()
                        or requested_norm.shape not in (torch.Size([]), hidden.shape[:-1])):
                    raise ValueError("requested_norm must be scalar or match the position shape")
                target_norm = requested_norm.detach().to(device=hidden.device, dtype=torch.float32)
            else:
                target_norm = before.new_tensor(_scalar("requested_norm", requested_norm))
            _finite("requested_norm", target_norm)
            if bool((target_norm <= 0).any()):
                raise ValueError("requested_norm must be positive")
            if bool((source_norm == 0).any()):
                raise ValueError("Cannot match a zero source delta; no direction exists")
            requested = (requested / source_norm.unsqueeze(-1)) * target_norm.unsqueeze(-1)
            _finite("matched requested_delta", requested)
            if bool((_norm(requested) == 0).any()):
                raise ValueError("Matched delta underflows FP32")
        edited = hidden if not bool(requested.any()) else (before + requested).to(hidden.dtype)
        _finite("edited hidden", edited)
        after = edited.float().clone()
        actual = after - before
        _finite("actual_delta", actual)
        request_length, actual_length = _norm(requested), _norm(actual)
        nonzero = request_length > 0
        delivered = actual_length > 0
        request_denominator = torch.where(nonzero, request_length, 1.0)
        actual_denominator = torch.where(delivered, actual_length, 1.0)
        cosine = ((requested / request_denominator.unsqueeze(-1))
                  * (actual / actual_denominator.unsqueeze(-1))).sum(-1)
        telemetry = {
            "before": before, "after": after,
            "requested_delta": requested, "actual_delta": actual,
            "requested_norm": request_length, "actual_norm": actual_length,
            "cosine": torch.where(nonzero, cosine.clamp(-1, 1), 1.0),
            "relative_error": _norm(actual - requested) / request_denominator,
            "norm_ratio": torch.where(nonzero, actual_length / request_denominator, 1.0),
            "before_coordinates": before_coordinates,
            "donor_coordinates": donor_coordinates,
            "requested_coordinates": _coordinates(requested, basis),
            "after_coordinates": _coordinates(after, basis),
            "actual_coordinates": _coordinates(actual, basis),
            "nonzero_requested": nonzero, "nonzero_actual": delivered,
            "rounded_to_zero": nonzero & ~delivered,
            "identity": (edited == hidden).all(-1),
        }
        for name, value in telemetry.items():
            _finite(name, value)
    return edited, telemetry

"""Exploratory coordinate geometry, not new model forwards or a passed assay.

The Gram matrix suffices for minimum-norm linear inequality projections.
No SAE weights, decoder semantics, BF16 readback or language loss is inferred.
"""
from itertools import combinations

import numpy as np


def _gram(value):
    g = np.asarray(value, dtype=np.float64)
    if (g.ndim != 2 or g.shape[0] != g.shape[1] or not 1 <= len(g) <= 6
            or not np.isfinite(g).all() or not np.array_equal(g, g.T)):
        raise ValueError("Expected finite symmetric Gram matrix, dimension 1..6")
    if np.linalg.eigvalsh(g)[0] <= 0 or np.linalg.cond(g) > 1e6:
        raise ValueError("Gram must be positive definite and well conditioned")
    return g


def minimum_inequality(gram, bounds):
    """Minimize ||r|| with A r >= bounds, given gram=A A.T.

    Enumerate at most 64 active sets. Returned multipliers are nonnegative,
    r=A.T multipliers, and the KKT certificate verifies global optimality of
    this convex projection. Inputs/outputs are float64 continuous geometry.
    Bounds are [positions, features]; unconstrained coordinates must be omitted.
    """
    original = _gram(gram)
    b = np.asarray(bounds, dtype=np.float64)
    if b.ndim != 2 or b.shape[1] != len(original) or not np.isfinite(b).all():
        raise ValueError("Expected finite position-by-feature bounds")
    row_norm = np.sqrt(np.diag(original))
    g = original / row_norm[:, None] / row_norm[None, :]
    b = b / row_norm
    # Positive-bound scaling prevents an absolute tolerance from declaring a
    # small but genuine constraint to be a zero-edit solution.
    problem_scale = np.max(np.maximum(b, 0), axis=1, initial=0)
    problem_scale = np.where(problem_scale > 0, problem_scale, 1.)
    b = b / problem_scale[:, None]
    if not np.isfinite(b).all():
        raise ValueError("Constraint scaling exceeded finite arithmetic")
    n, k = b.shape
    best = np.full(n, np.inf)
    answer = np.zeros_like(b)
    tiny = np.finfo(np.float64).tiny
    for size in range(k + 1):
        for subset in combinations(range(k), size):
            dual = np.zeros_like(b)
            if subset:
                ix = list(subset)
                dual[:, ix] = np.linalg.solve(g[np.ix_(ix, ix)], b[:, ix].T).T
            product = np.einsum("ij,kj->ik", dual, g, optimize=False)
            slack = product - b
            roundoff_scale = np.einsum("ij,kj->ik", np.abs(dual), np.abs(g), optimize=False)
            tolerance = 1e-10 * np.maximum(roundoff_scale + np.abs(b), tiny)
            dual_tolerance = 1e-10 * np.max(np.abs(dual), axis=1, initial=0)
            valid = ((dual.min(axis=1) >= -dual_tolerance)
                     & np.all(slack >= -tolerance, axis=1))
            objective = np.einsum("ij,ij->i", dual, product)
            take = valid & (objective < best)
            answer[take], best[take] = dual[take], objective[take]
    if not np.isfinite(best).all():
        raise ValueError("No numerically certified active-set solution")
    product = np.einsum("ij,kj->ik", answer, g, optimize=False)
    slack = product - b
    complementarity = np.abs(answer * slack).max(axis=1, initial=0)
    roundoff_scale = np.einsum("ij,kj->ik", np.abs(answer), np.abs(g), optimize=False)
    tolerance = 1e-10 * np.maximum(roundoff_scale + np.abs(b), tiny)
    dual_tolerance = 1e-10 * np.max(np.abs(answer), axis=1, initial=0)
    if (np.any(slack < -tolerance) or np.any(answer.min(axis=1) < -dual_tolerance)
            or np.any(np.abs(answer * slack) > 1e-8 * (1 + np.abs(b)) * (1 + np.abs(answer)))):
        raise ValueError("KKT certificate failed")
    multipliers = answer * problem_scale[:, None] / row_norm
    norm = np.sqrt(np.maximum(best, 0)) * problem_scale
    if not np.isfinite(multipliers).all() or not np.isfinite(norm).all():
        raise ValueError("Solution scaling exceeded finite arithmetic")
    return {"multipliers": multipliers, "norm": norm,
            "certificate_scope": "row-normalized and positive-bound-scaled system",
            "minimum_slack": slack.min(axis=1), "minimum_multiplier": answer.min(axis=1),
            "maximum_complementarity": complementarity}


def bf16_bounds(norm_fraction):
    """Conservative RN bounds for normal finite numbers; not GPU validation.

    h is already BF16. Assume one round-to-nearest cast of exact h+r, no
    overflow/subnormal exception and no prior arithmetic error. Tiny edits
    can lack a useful relative bound; never pad them with unrelated vectors.
    """
    rho = np.asarray(norm_fraction, dtype=np.float64)
    if not np.isfinite(rho).all() or np.any(rho < 0):
        raise ValueError("Norm fractions must be finite and nonnegative")
    u = 2.0 ** -8
    absolute = u * (1 + rho)
    relative = np.divide(absolute, rho, out=np.full_like(rho, np.inf), where=rho > 0)
    cosine = np.sqrt(np.maximum(0, 1 - relative ** 2))
    cosine = np.where(relative < 1, cosine, -1.0)
    return {"relative_error_upper": relative, "realized_norm_fraction_upper": rho + absolute,
            "cosine_lower": cosine}


def active_support_projection(gram, preactivation, native_before, clean_norm, *, mode,
                              change=.75, norm_cap=.04):
    """New prototype: change active coordinates without increasing inactive preactivations.

    Support uses saved native before>0. Active targets are .25z (suppression)
    or 1.75z (amplification) at the default change. Inactive preactivations
    cannot increase. An all-inactive position is exactly unchanged. Project
    then radially cap the CONTINUOUS edit at 4% of clean norm; return any lost
    coordinate efficacy, never relabel the capped edit as the full request.
    Original q90 intervention and old gates are not modified by this function.
    """
    g = _gram(gram)
    p, z, h = (np.asarray(x, dtype=np.float64) for x in
               (preactivation, native_before, clean_norm))
    if (p.ndim != 2 or p.shape[1] != len(g) or z.shape != p.shape or h.shape != (len(p),)
            or any(not np.isfinite(x).all() for x in (p, z, h))
            or np.any(z < 0) or np.any(h <= 0)):
        raise ValueError("Invalid clean geometry arrays")
    if mode not in ("suppression", "amplification") or not 0 < change <= 1 or not 0 < norm_cap < 1:
        raise ValueError("Invalid prototype parameters")
    active = z > 0
    codes = active @ (1 << np.arange(len(g)))
    coefficients = np.zeros_like(p)
    uncapped_norm = np.zeros(len(p))
    for code in sorted(set(codes) - {0}):
        mask = codes == code
        support = active[np.flatnonzero(mask)[0]]
        signs = np.where(support & (mode == "amplification"), 1., -1.)
        target = (1 + change if mode == "amplification" else 1 - change) * z[mask]
        bounds = np.where(support, signs * (target - p[mask]), 0.)
        solution = minimum_inequality(signs[:, None] * g * signs[None, :], bounds)
        coefficients[mask] = solution["multipliers"] * signs
        uncapped_norm[mask] = solution["norm"]
    scale = np.minimum(1., np.divide(norm_cap * h, uncapped_norm,
                                    out=np.ones_like(h), where=uncapped_norm > 0))
    coefficients *= scale[:, None]
    shift = np.einsum("ij,kj->ik", coefficients, g, optimize=False)
    predicted = np.maximum(p + shift, 0.)
    norm = np.sqrt(np.maximum(np.einsum("ij,ij->i", coefficients, shift), 0.))
    return {"coefficients": coefficients, "predicted_preactivation": p + shift,
            "predicted_activation": predicted, "norm": norm, "uncapped_norm": uncapped_norm,
            "scale": scale, "active": active,
            "inactive_preactivation_increase": np.where(~active, np.maximum(shift, 0), 0)}


def rounding_window(projection, preactivation, native_before, clean_norm, minimum_fraction=.02):
    """Explicitly conditional prototype; never count skipped states as successes.

    Reject small requests instead of adding nullspace noise to inflate fidelity.
    Preserve the original projection and return a separate dispatch mask.
    Coverage and all-active outcomes must accompany conditional diagnostics.
    """
    p, z, h = (np.asarray(x, dtype=float) for x in (preactivation, native_before, clean_norm))
    if (not 0 < minimum_fraction <= .04 or p.ndim != 2 or z.shape != p.shape
            or h.shape != (len(p),) or np.any(h <= 0) or np.any(z < 0)
            or any(not np.isfinite(x).all() for x in (p, z, h))):
        raise ValueError("Invalid rounding-window inputs")
    dispatch = projection["norm"] / h >= minimum_fraction
    post = np.where(dispatch[:, None], np.maximum(projection["predicted_preactivation"], 0), z)
    return {"dispatch": dispatch, "coefficients": np.where(dispatch[:, None], projection["coefficients"], 0.),
            "predicted_activation": post,
            "norm": np.where(dispatch, projection["norm"], 0.)}

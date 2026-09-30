import numpy as np
import pytest
from scipy.optimize import minimize

from experiments.sae_assay_repair.feasibility import (
    active_support_projection, bf16_bounds, minimum_inequality, rounding_window,
)


def test_orthogonal_projection_and_inactive_constraints():
    g = np.diag([4., 1.])
    b = np.array([[2., -1.], [-3., -2.], [1., 3.]])
    result = minimum_inequality(g, b)
    np.testing.assert_allclose(result["multipliers"], [[.5, 0], [0, 0], [.25, 3]])
    np.testing.assert_allclose(result["norm"], [1, 0, np.sqrt(9.25)])


def test_negative_bound_can_be_active_due_to_cross_coordinate_coupling():
    g = np.array([[1., -.8], [-.8, 1.]])
    result = minimum_inequality(g, [[1., -.1]])
    assert (result["multipliers"] > 0).all()
    np.testing.assert_allclose(result["multipliers"] @ g, [[1., -.1]], atol=1e-12)


def test_small_constraint_scale_cannot_be_reported_as_zero():
    result = minimum_inequality([[1e-24]], [[1e-11]])
    assert result["norm"][0] == pytest.approx(10., rel=1e-12)
    assert result["multipliers"][0, 0] == pytest.approx(1e13, rel=1e-12)
    result = minimum_inequality(np.eye(2), [[1e-11, -1e10]])
    assert result["norm"][0] == pytest.approx(1e-11, abs=1e-22)
    assert result["multipliers"][0, 0] > 0


def test_zero_guard_constraints_allow_only_arithmetic_cancellation_tolerance():
    rng = np.random.default_rng(184)
    e = rng.normal(size=(6, 12))
    bounds = np.zeros((50, 6))
    bounds[:, 0] = rng.uniform(.01, 3, 50)
    g = e @ e.T
    result = minimum_inequality(g, bounds)
    slack = result["multipliers"] @ g - bounds
    assert np.min(slack) > -1e-12
    assert (result["norm"] > 0).all()


@pytest.mark.parametrize("k", [1, 2, 4, 6])
def test_independent_scipy_primal_reconstruction(k):
    rng = np.random.default_rng(812 + k)
    e = rng.normal(size=(k, k + 3))
    g = e @ e.T
    bounds = rng.normal(size=(12, k))
    result = minimum_inequality(g, bounds)
    for i, b in enumerate(bounds):
        other = minimize(lambda r: .5 * r @ r, np.zeros(e.shape[1]), jac=lambda r: r,
                         constraints={"type": "ineq", "fun": lambda r: e @ r - b,
                                      "jac": lambda r: e}, method="SLSQP",
                         options={"ftol": 1e-12, "maxiter": 200})
        assert other.success
        recovered = result["multipliers"][i] @ e
        np.testing.assert_allclose(recovered, other.x, atol=1e-7, rtol=1e-7)
        assert np.min(e @ recovered - b) >= -1e-9


@pytest.mark.parametrize("gram", [np.zeros((2, 2)), [[1, 2], [0, 1]], [[np.nan]],
                                  np.eye(7), [[1, 0], [0, -1]], np.diag([1, 1e-8]),
                                  1e-24 * np.array([[1, 1], [0, 1]])])
def test_invalid_geometry_fails_closed(gram):
    with pytest.raises(ValueError):
        minimum_inequality(gram, [[0, 1]])


def test_empty_batch_and_nonfinite_bounds():
    assert minimum_inequality(np.eye(2), np.empty((0, 2)))["norm"].size == 0
    for bad in ([1, 2], [[1, np.inf]], [[1, 2, 3]]):
        with pytest.raises(ValueError):
            minimum_inequality(np.eye(2), bad)


@pytest.mark.parametrize("mode", ["suppression", "amplification"])
def test_prototype_norm_cap_support_and_zero_identity(mode):
    g = np.array([[1., .2], [.2, 2.]])
    p = np.array([[-4., -2.], [1., -.5], [2., 3.]])
    z = np.maximum(p, 0)
    h = np.array([10., 100., 5.])
    result = active_support_projection(g, p, z, h, mode=mode)
    np.testing.assert_array_equal(result["coefficients"][0], [0, 0])
    np.testing.assert_array_equal(result["predicted_preactivation"][0], p[0])
    assert (result["norm"] <= .04 * h + 1e-12).all()
    assert result["inactive_preactivation_increase"].max() < 1e-12
    assert result["scale"][2] < 1  # Loss of intended efficacy is visible.
    expected = .25 if mode == "suppression" else 1.75
    assert result["predicted_activation"][1, 0] == pytest.approx(expected)


def test_rounding_bound_does_not_certify_tiny_edits():
    result = bf16_bounds([0., .001, .02, .04])
    assert np.isinf(result["relative_error_upper"][0])
    assert result["relative_error_upper"][1] > 1
    assert result["relative_error_upper"][2] < .2
    assert result["cosine_lower"][2] > .95
    assert result["realized_norm_fraction_upper"][3] == pytest.approx(.0440625)
    with pytest.raises(ValueError):
        bf16_bounds([-.1])


def test_window_is_separate_retains_skipped_states_and_does_not_pad():
    p = np.array([[.1, -1.], [1., -1.], [0., 0.]])
    h = np.full(3, 10.)
    before = np.maximum(p, 0)
    a = active_support_projection(np.eye(2), p, before, h, mode="suppression")
    saved = a["coefficients"].copy()
    w = rounding_window(a, p, before, h)
    np.testing.assert_array_equal(w["dispatch"], [False, True, False])
    np.testing.assert_array_equal(w["predicted_activation"][0], before[0])
    np.testing.assert_array_equal(w["coefficients"][0], [0., 0.])
    np.testing.assert_array_equal(a["coefficients"], saved)
    bound = bf16_bounds(w["norm"][w["dispatch"]]/h[w["dispatch"]])
    assert (bound["relative_error_upper"] <= .2).all()

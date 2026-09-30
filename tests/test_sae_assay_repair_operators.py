"""CPU-only algebra, canonical encoding, and native-rounding diagnostics."""

from unittest.mock import patch

import pytest

torch = pytest.importorskip("torch")
import torch.nn.functional as F

from experiments.sae_assay_diagnostic import backend
from experiments.sae_assay_repair import operators as op


def identity(k=6, dtype=torch.float32):
    return torch.eye(k, dtype=dtype), torch.zeros(k, dtype=dtype), torch.eye(k, dtype=dtype)


def repair(h, e, b, d, operator, **kwargs):
    arguments = {"feature_ids": tuple(range(e.shape[0])), "mode": "suppression", "strength": 1.0}
    arguments.update(kwargs)
    return op.repair_hidden(h, e, b, d, operator=operator, **arguments)


@pytest.mark.parametrize("operator", op.OPERATORS)
@pytest.mark.parametrize("dtype", [torch.float32, torch.bfloat16])
@pytest.mark.parametrize("k", [1, 6])
@pytest.mark.parametrize("strength", [.5, 1.])
@pytest.mark.parametrize("mode", ["suppression", "amplification"])
def test_identity_expected_coordinates(operator, dtype, k, strength, mode):
    h = torch.tensor([[2., -3., 0., 4., -1., 8.], [-2., 1., 3., 0., 5., 9.]], dtype=dtype)[:, :k]
    original = h.clone()
    e, b, d = identity(k, dtype)
    b.fill_(.5)
    q90 = torch.full((k,), 6.)
    edited, t = repair(h, e, b, d, operator, mode=mode, strength=strength, q90=q90)
    preact = h.float() + b.float()
    before = preact.relu()
    desired = ((1 - strength) * before if mode == "suppression"
               else before + strength * (q90 - before).clamp_min(0))
    eligible = before > 0 if mode == "suppression" else desired > before
    shift = torch.where(eligible, desired - preact, 0.)
    assert torch.equal(edited, (h.float() + shift).to(dtype))
    assert torch.equal(t["before"], before)
    assert torch.equal(t["after"], desired)
    assert torch.equal(t["requested_delta"], desired - before)
    assert torch.equal(t["requested_preact_delta"], shift)
    assert torch.equal(t["eligible"], eligible)
    assert (t["condition"] == 1).all()
    assert not t["solve_residual"].any()
    assert torch.equal(h, original)


def test_nonorthogonal_decoder_uses_inverse_response_and_differs_from_min_norm():
    e = torch.eye(8)[:6]
    b = torch.zeros(6)
    d = e.T.clone()
    d[0, 0], d[0, 1], d[1, 1] = 2., 1., 3.
    d[6, 0], d[7, 1] = 4., -2.
    h = torch.tensor([[2., 3., 4., 5., 6., 7., 8., 9.]])
    geometry = op.prepare_geometry(e, b, d, range(6))
    ds, dt = repair(h, e, b, d, "decoder_span", geometry=geometry, strength=.5)
    mn, mt = repair(h, e, b, d, "encoder_min_norm", geometry=geometry, strength=.5)
    shift = -.5 * h[:, :6]
    coefficients = torch.linalg.solve(e @ d, shift.T).T
    expected_decoder_edit = coefficients @ d.T
    assert not torch.allclose(shift @ d.T, expected_decoder_edit)
    torch.testing.assert_close(dt["requested_edit"], expected_decoder_edit)
    torch.testing.assert_close(dt["solve_coefficients"], coefficients)
    torch.testing.assert_close(dt["after"], .5 * h[:, :6])
    torch.testing.assert_close(mt["after"], dt["after"])
    assert not torch.equal(ds, mn)
    assert torch.equal(mn[:, 6:], h[:, 6:])
    assert mt["requested_norm"].item() < dt["requested_norm"].item()


def test_encoder_min_norm_is_independent_of_decoder_and_orthogonal_to_nullspace():
    e = torch.tensor([[1., 2., 0.]])
    b = torch.tensor([1.])
    h = torch.tensor([[2., 1., 4.]])
    d = torch.tensor([[2.], [1.], [9.]])
    edited, t = repair(h, e, b, d, "encoder_min_norm")
    expected = -e  # E @ E.T = 5 and requested preactivation shift = -5.
    torch.testing.assert_close(t["requested_edit"], expected)
    null = torch.tensor([[2., -1., 3.]])
    assert (t["requested_edit"] * null).sum().item() == 0
    again, _ = repair(h, e, b, -3 * d, "encoder_min_norm")
    assert torch.equal(again, edited)


@pytest.mark.parametrize("operator", op.OPERATORS)
def test_negative_preactivation_amplification_crosses_relu(operator):
    h = torch.tensor([[-5.], [-2.], [8.]])
    e, b, d = identity(1)
    b.fill_(1.)
    _, t = repair(h, e, b, d, operator, mode="amplification", strength=.5, q90=[4.])
    assert t["before"].flatten().tolist() == [0., 0., 9.]
    assert t["requested_delta"].flatten().tolist() == [2., 2., 0.]
    assert t["requested_preact_delta"].flatten().tolist() == [6., 3., 0.]
    assert t["desired_preact"].flatten().tolist() == [2., 2., 9.]
    assert torch.equal(t["after"], t["requested_activation"])
    assert t["eligible"].flatten().tolist() == [True, True, False]


@pytest.mark.parametrize("operator", op.OPERATORS)
def test_inactive_suppression_constrains_preactivation_despite_decoder_crosstalk(operator):
    e, b, d = identity()
    d[0, 1], d[1, 0] = .5, .25
    h = torch.tensor([[2., -3., 4., 0., -1., 2.]])
    edited, t = repair(h, e, b, d, operator)
    torch.testing.assert_close(edited, torch.tensor([[0., -3., 0., 0., -1., 0.]]))
    assert t["desired_preact"][0, 1].item() == -3.
    assert t["requested_preact_delta"][0, 1].item() == 0.
    assert not t["after"].any()


@pytest.mark.parametrize("operator", op.OPERATORS)
@pytest.mark.parametrize("mode", [None, "suppression", "amplification"])
def test_true_zero_identity_even_with_native_fp32_disagreement(operator, mode):
    h = torch.tensor([[1.]], dtype=torch.bfloat16)
    e, b, d = identity(1, h.dtype)
    b.fill_(.00390625)
    edited, t = repair(h, e, b, d, operator, mode=mode, strength=0)
    assert t["before"].item() != t["fp32_preact"].item()
    assert edited is h
    assert torch.equal(t["before"], t["after"])
    assert torch.equal(t["desired_preact"], t["fp32_preact"])
    for name in ("requested_delta", "requested_preact_delta", "requested_edit", "realized_edit", "relative_error"):
        assert not t[name].any()
    assert t["cosine"].item() == 1
    assert t["identity"].all() and not t["nonzero_requested"].any()


@pytest.mark.parametrize("operator", op.OPERATORS)
def test_no_eligible_coordinates_is_object_identity(operator):
    h = torch.tensor([[-4.]])
    for mode, kwargs in (("suppression", {}), ("amplification", {"q90": [0.]})):
        edited, t = repair(h, *identity(1), operator, mode=mode, **kwargs)
        assert edited is h
        assert not t["eligible"].any()
        assert t["desired_preact"].item() == -4.


@pytest.mark.parametrize("operator", op.OPERATORS)
def test_bf16_rounding_loss_remains_visible_without_retry(operator):
    h = torch.tensor([[256.]], dtype=torch.bfloat16)
    e, b, d = identity(1, h.dtype)
    b.fill_(-256.)
    edited, t = repair(h, e, b, d, operator, mode="amplification", q90=[.25])
    assert torch.equal(edited, h)
    assert t["requested_edit"].item() == .25
    assert t["ideal_fp32_after"].item() == .25
    assert t["actual_fp32_after"].item() == 0
    assert t["after"].item() == 0
    assert t["activation_error"].item() == -.25
    assert t["requested_norm"].item() == .25
    assert t["realized_norm"].item() == 0
    assert t["relative_error"].item() == 1
    assert t["cosine"].item() == 0
    assert t["nonzero_requested"].item() and t["identity"].item()


@pytest.mark.parametrize("operator", op.OPERATORS)
def test_bf16_one_final_cast_not_rounded_edit_first(operator):
    h = torch.tensor([[1.]], dtype=torch.bfloat16)
    e, b, d = identity(1, h.dtype)
    b.fill_(512.)
    edited, t = repair(h, e, b, d, operator, strength=.5)
    expected = (h.float() + t["requested_edit"]).to(h.dtype)
    wrong = (h.float() + t["requested_edit"].to(h.dtype).float()).to(h.dtype)
    assert torch.equal(edited, expected)
    assert not torch.equal(edited, wrong)
    assert t["before"].item() == 512.
    assert t["fp32_preact"].item() == 513.
    assert t["requested_preact_delta"].item() == -257.
    assert t["after"].item() == 256.


@pytest.mark.parametrize("operator", op.OPERATORS)
def test_canonical_fullwidth_token1_and_finite_tensor_schema(operator):
    dtype = torch.bfloat16
    h = torch.arange(24, dtype=torch.float32).reshape(2, 2, 6).div(8).to(dtype).transpose(0, 1)
    e = torch.cat((torch.eye(6), torch.ones(4, 6)), dim=0).to(dtype)
    b = torch.arange(10, dtype=torch.float32).div(8).to(dtype)
    d = e.T.contiguous()
    ids = [5, 1, 3, 0, 4, 2]
    native_calls = []
    linear = F.linear

    def observed(values, weight, bias=None):
        assert not torch.backends.cuda.matmul.allow_tf32
        assert not torch.is_autocast_enabled("cpu")
        if weight.dtype == dtype:
            native_calls.append((tuple(values.shape), tuple(weight.shape)))
            assert weight is e
        else:
            assert values.dtype == weight.dtype == torch.float32
        return linear(values, weight, bias)

    with patch.object(F, "linear", side_effect=observed):
        with torch.autocast("cpu", dtype=torch.bfloat16):
            edited, t = repair(h, e, b, d, operator, feature_ids=ids, strength=.5)
    assert native_calls == [((1, 6), (10, 6))] * 8
    for name, state in (("before", h), ("after", edited)):
        expected = torch.cat([F.linear(row[None], e, b).relu()[:, ids]
                              for row in state.reshape(-1, 6)]).reshape(2, 2, 6).float()
        assert torch.equal(t[name], expected)
    assert op.ENCODING_AUTHORITY == backend.ENCODING_AUTHORITY
    assert set(op.ACTIVATION_COLUMNS + op.REFERENCE_COLUMNS + op.DELIVERY) <= t.keys()
    boolean = {"eligible", "identity", "valid", "nonzero_requested"}
    position = set(op.DELIVERY) | {"identity", "valid", "nonzero_requested", "condition"}
    for name, tensor in t.items():
        assert torch.isfinite(tensor).all()
        assert tensor.dtype == (torch.bool if name in boolean else torch.float32)
        assert tensor.device.type == "cpu"
        assert not tensor.requires_grad
        expected_shape = (2, 2) if name in position else (2, 2, 6)
        assert tensor.shape == expected_shape, name


@pytest.mark.parametrize("operator", op.OPERATORS)
@pytest.mark.parametrize("bad_scale", [0., 1e-8])
def test_singular_and_ill_conditioned_fail_without_fallback(operator, bad_scale):
    e, b, d = identity()
    if operator == "decoder_span":
        d[-1, -1] = bad_scale
    else:
        e[-1, -1] = bad_scale
    for strength in (0., 1.):
        with pytest.raises(ValueError, match=operator + ": singular or condition"):
            repair(torch.ones(1, 6), e, b, d, operator, strength=strength)


def test_singular_decoder_does_not_disqualify_encoder_diagnostic():
    e, b, d = identity(1)
    d.zero_()
    geometry = op.prepare_geometry(e, b, d, [0])
    assert not torch.isfinite(geometry.decoder_span_condition)
    assert geometry.encoder_min_norm_condition.item() == 1
    with pytest.raises(ValueError, match="decoder_span: singular"):
        repair(torch.ones(1, 1), e, b, d, "decoder_span", geometry=geometry)
    edited, t = repair(torch.ones(1, 1), e, b, d, "encoder_min_norm", geometry=geometry)
    assert not edited.any()
    assert t["condition"].item() == 1.


def test_ill_conditioned_encoder_does_not_disqualify_decoder_diagnostic():
    e, b, d = identity()
    e[-1, -1], d[-1, -1] = 1e-4, 1e4
    geometry = op.prepare_geometry(e, b, d, range(6))
    assert geometry.encoder_min_norm_condition.item() > op.CONDITION_LIMIT
    assert geometry.decoder_span_condition.item() == 1.
    h = torch.ones(1, 6)
    with pytest.raises(ValueError, match="encoder_min_norm: singular or condition"):
        repair(h, e, b, d, "encoder_min_norm", geometry=geometry)
    edited, t = repair(h, e, b, d, "decoder_span", geometry=geometry)
    torch.testing.assert_close(edited, torch.zeros_like(h))
    assert t["condition"].item() == 1.


def test_condition_limit_is_inclusive_and_both_conditions_are_cached():
    e, b, d = identity()
    d[-1, -1] = 1e-6
    geometry = op.prepare_geometry(e, b, d, range(6))
    assert geometry.decoder_span_condition.item() == op.CONDITION_LIMIT
    for name in op.OPERATORS:
        matrix = getattr(geometry, name)
        condition = getattr(geometry, name + "_condition")
        assert matrix.shape == (6, 6)
        assert condition.shape == () and condition.dtype == torch.float32
        assert torch.equal(condition, torch.linalg.cond(matrix))
    with patch.object(torch.linalg, "cond", side_effect=AssertionError("must reuse cached conditions")):
        edited, t = repair(torch.ones(1, 6), e, b, d, "decoder_span", geometry=geometry)
    torch.testing.assert_close(edited, torch.zeros_like(edited))
    assert t["condition"].item() == op.CONDITION_LIMIT


@pytest.mark.parametrize("operator", op.OPERATORS)
def test_amplification_eligibility_retains_positive_delta_at_fp32_rounding_tie(operator):
    h = torch.ones(1, 1)
    q90 = torch.nextafter(torch.ones(1), torch.full((1,), 2.))
    _, t = repair(h, *identity(1), operator, mode="amplification", strength=.5, q90=q90)
    assert t["requested_delta"].item() > 0
    assert t["eligible"].item()
    assert t["requested_activation"].item() == 1.


def test_geometry_cached_result_and_stale_or_mismatched_sources():
    e, b, d = identity()
    geometry = op.prepare_geometry(e, b, d, range(6))
    h = torch.ones(1, 6)
    a, at = repair(h, e, b, d, "decoder_span", geometry=geometry)
    z, zt = repair(h, e, b, d, "decoder_span")
    assert torch.equal(a, z)
    assert all(torch.equal(at[key], zt[key]) for key in at)
    with pytest.raises(ValueError, match="Geometry must match"):
        repair(h, e, b, d, "decoder_span", geometry=geometry, feature_ids=list(reversed(range(6))))
    with pytest.raises(ValueError, match="Geometry must match"):
        repair(h, e.clone(), b, d, "decoder_span", geometry=geometry)
    e[0, 0] = 2.
    with pytest.raises(ValueError, match="Stale geometry"):
        repair(h, e, b, d, "decoder_span", geometry=geometry)


def test_only_selected_weights_are_promoted_and_tf32_restored():
    e = torch.eye(12, dtype=torch.bfloat16)
    b, d = torch.zeros(12, dtype=e.dtype), e.T.contiguous()
    original_float = torch.Tensor.float
    promoted = []

    def observed(tensor, *args, **kwargs):
        promoted.append(tuple(tensor.shape))
        assert tensor.numel() < e.numel()
        return original_float(tensor, *args, **kwargs)

    previous = torch.backends.cuda.matmul.allow_tf32
    try:
        torch.backends.cuda.matmul.allow_tf32 = True
        with patch.object(torch.Tensor, "float", observed):
            geometry = op.prepare_geometry(e, b, d, [7])
        assert promoted == [(1, 12), (1,), (12, 1)]
        assert geometry.sources[0] is e and geometry.sources[2] is d
        assert torch.backends.cuda.matmul.allow_tf32
        with patch.object(torch.Tensor, "float", observed):
            repair(torch.ones(1, 12, dtype=e.dtype), e, b, d, "decoder_span",
                   feature_ids=[7], geometry=geometry)
        assert torch.backends.cuda.matmul.allow_tf32
        d[7, 7] = 0
        with pytest.raises(ValueError, match="singular"):
            repair(torch.ones(1, 12, dtype=e.dtype), e, b, d, "decoder_span", feature_ids=[7])
        assert torch.backends.cuda.matmul.allow_tf32
    finally:
        torch.backends.cuda.matmul.allow_tf32 = previous


@pytest.mark.parametrize("location", ["hidden", "encoder", "bias", "decoder", "q90"])
@pytest.mark.parametrize("nonfinite", [float("nan"), float("inf")])
def test_nonfinite_inputs_fail(location, nonfinite):
    h = torch.ones(1, 1)
    e, b, d = identity(1)
    q90 = torch.ones(1)
    {"hidden": h, "encoder": e, "bias": b, "decoder": d, "q90": q90}[location].fill_(nonfinite)
    with pytest.raises(FloatingPointError, match="Nonfinite"):
        repair(h, e, b, d, "decoder_span", mode="amplification", q90=q90)


def test_finite_inputs_with_overflow_fail_explicitly():
    e, b, d = identity(1)
    e.fill_(1e30)
    geometry = op.prepare_geometry(e, b, d, [0])
    assert torch.isnan(geometry.encoder_min_norm_condition)
    with pytest.raises(FloatingPointError, match="encoder_min_norm solve matrix"):
        repair(torch.zeros(1, 1), e, b, d, "encoder_min_norm", geometry=geometry)
    edited, _ = repair(torch.zeros(1, 1), e, b, d, "decoder_span", geometry=geometry)
    assert not edited.any()
    e, b, d = identity(1)
    e.fill_(1e-10)
    with pytest.raises(FloatingPointError, match="Nonfinite"):
        repair(torch.zeros(1, 1), e, b, d, "decoder_span", mode="amplification", q90=[1e38])


@pytest.mark.parametrize("kwargs", [
    {"strength": .7}, {"strength": True}, {"strength": float("nan")},
    {"mode": "other"}, {"mode": None}, {"operator": "auto"},
    {"mode": "amplification"},
    {"mode": "amplification", "q90": [1.]},
    {"mode": "amplification", "q90": [-1.] * 6},
    {"feature_ids": []}, {"feature_ids": [0, 1]},
    {"feature_ids": [0] * 6}, {"feature_ids": [6]}, {"feature_ids": [True]},
])
def test_bad_request_schema_fails(kwargs):
    arguments = {"operator": "decoder_span", **kwargs}
    with pytest.raises(ValueError):
        repair(torch.ones(1, 6), *identity(), **arguments)


@pytest.mark.parametrize("kind", ["hidden_rank", "empty", "width", "bias", "decoder", "dtype", "native_dtype"])
def test_incompatible_tensor_schema_fails(kind):
    h = torch.ones(1, 6)
    e, b, d = identity()
    if kind == "hidden_rank":
        h = h[0]
    elif kind == "empty":
        h = h[:0]
    elif kind == "width":
        h = h[:, :5]
    elif kind == "bias":
        b = b[:5]
    elif kind == "decoder":
        d = d[:, :5]
    elif kind == "dtype":
        h = h.bfloat16()
    else:
        h, e, b, d = (t.double() for t in (h, e, b, d))
    with pytest.raises(ValueError):
        repair(h, e, b, d, "decoder_span")

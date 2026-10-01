"""Synthetic tensors only; opt into local CUDA with JLENS_TEST_CUDA=1."""

import math
import os

import pytest

torch = pytest.importorskip("torch")

from experiments.jlens_causal_report import (
    orthonormal_basis,
    patch_component,
    random_orthonormal_basis,
)


@pytest.fixture(params=["cpu"] + (["cuda"] if os.environ.get("JLENS_TEST_CUDA") == "1" else []))
def device(request):
    if request.param == "cuda" and not torch.cuda.is_available():
        pytest.skip("CUDA explicitly requested but unavailable")
    if request.param == "cuda":
        return torch.device("cuda", torch.cuda.current_device())
    return torch.device(request.param)


def noise(shape, device, seed=17):
    generator = torch.Generator(device="cpu").manual_seed(seed)
    return torch.randn(shape, generator=generator).to(device)


def test_basis_rank_canonical_signs_and_repeatability(device):
    rows = torch.tensor([[-3., -4., 0., 0.], [1., 2., -2., 0.]], device=device)
    saved = rows.clone()
    q = orthonormal_basis(rows)
    assert q.shape == (4, 2) and q.dtype == torch.float32 and q.device == device
    assert torch.equal(q, orthonormal_basis(rows))
    assert torch.equal(rows, saved)
    torch.testing.assert_close(q.T @ q, torch.eye(2, device=device), atol=2e-6, rtol=2e-6)
    for column in q.unbind(1):
        assert column[column.abs().argmax()] > 0
    torch.testing.assert_close(q[:, 0], torch.tensor([.6, .8, 0., 0.], device=device))
    torch.testing.assert_close(q, orthonormal_basis(rows * torch.tensor([[-2.], [3.]], device=device)))
    torch.testing.assert_close(rows @ q @ q.T, rows)


@pytest.mark.parametrize("dtype", [torch.float16, torch.bfloat16, torch.float32, torch.float64])
def test_basis_promotes_to_fp32(dtype, device):
    rows = torch.eye(3, 7, dtype=dtype, device=device)
    assert torch.equal(orthonormal_basis(rows), rows.float().T)


@pytest.mark.parametrize("rows", [
    [[0., 0.]], [[1., 2.], [2., 4.]], [[1., 0.], [1., 1e-8]],
    [[float("nan"), 1.]], [[float("inf"), 1.]],
])
def test_invalid_candidate_values(rows):
    with pytest.raises(ValueError):
        orthonormal_basis(torch.tensor(rows))


@pytest.mark.parametrize("rows", [
    torch.ones(2), torch.ones(1, 2, 3), torch.ones(0, 4), torch.ones(2, 1),
    torch.eye(9), torch.ones(1, 2, dtype=torch.int64), torch.ones(1, 2, dtype=torch.complex64),
])
def test_invalid_candidate_shapes_and_dtypes(rows):
    with pytest.raises(ValueError):
        orthonormal_basis(rows)


@pytest.mark.parametrize("rtol", [0, -1, 1, float("nan"), float("inf"), True])
def test_rank_tolerance_validation(rtol):
    with pytest.raises(ValueError):
        orthonormal_basis(torch.eye(2), rank_rtol=rtol)


def test_rank_tolerance_is_enforced_not_silent_truncation():
    rows = torch.tensor([[1., 0., 0.], [1., 1e-4, 0.]])
    with pytest.raises(ValueError, match="rank deficient"):
        orthonormal_basis(rows, rank_rtol=1e-3)
    assert orthonormal_basis(rows, rank_rtol=1e-6).shape == (3, 2)
    tiny = torch.tensor([[1e-30, 0.], [0., 1e30]])
    assert torch.equal(orthonormal_basis(tiny), torch.eye(2))


@pytest.mark.parametrize("alpha", [0., .25, 1.])
def test_scalar_independent_arithmetic_and_telemetry(alpha, device):
    q = torch.tensor([[.6], [.8], [0.]], device=device)
    h = torch.tensor([[1., 2., -3.], [5., -4., 7.]], device=device)
    donor = torch.tensor([[3., -1., 9.], [2., 0., 8.]], device=device)
    edited, telemetry = patch_component(h, donor, q, alpha=alpha)
    for index, (source, destination) in enumerate(zip(h.tolist(), donor.tolist())):
        column = [.6, .8, 0.]
        coefficient = sum(c * (d - s) for c, d, s in zip(column, destination, source))
        delta = [alpha * c * coefficient for c in column]
        expected = [s + d for s, d in zip(source, delta)]
        assert edited[index].tolist() == pytest.approx(expected, abs=2e-6)
        assert telemetry["requested_delta"][index].tolist() == pytest.approx(delta, abs=2e-6)
        expected_norm = math.sqrt(sum(d * d for d in delta))
        assert telemetry["requested_norm"][index].item() == pytest.approx(expected_norm, abs=2e-6)
        for key, values in (("before_coordinates", source), ("donor_coordinates", destination),
                            ("after_coordinates", edited[index].tolist())):
            assert telemetry[key][index].item() == pytest.approx(sum(c * v for c, v in zip(column, values)), abs=2e-6)
    torch.testing.assert_close(telemetry["actual_delta"], edited - h)
    torch.testing.assert_close(telemetry["before"], h)
    torch.testing.assert_close(telemetry["after"], edited)
    torch.testing.assert_close(telemetry["cosine"], torch.ones(2, device=device))
    assert (telemetry["relative_error"] < 1e-5).all()
    torch.testing.assert_close(telemetry["norm_ratio"], torch.ones(2, device=device))


@pytest.mark.parametrize("rank", [1, 3, 8])
def test_fp32_orthogonal_components_unchanged(rank, device):
    q = random_orthonormal_basis(19, rank, seed=51, device=device)
    h, donor = noise((2, 3, 19), device), noise((2, 3, 19), device, 18)
    edited, t = patch_component(h, donor, q, alpha=.7)
    torch.testing.assert_close(edited - (edited @ q) @ q.T, h - (h @ q) @ q.T, atol=2e-6, rtol=2e-6)
    torch.testing.assert_close(t["requested_delta"], .7 * ((donor - h) @ q) @ q.T, atol=2e-6, rtol=2e-6)
    torch.testing.assert_close(t["requested_coordinates"], t["requested_delta"] @ q)
    torch.testing.assert_close(t["actual_coordinates"], t["actual_delta"] @ q)


@pytest.mark.parametrize("dtype", [torch.float32, torch.bfloat16, torch.float16])
@pytest.mark.parametrize("mode", ["zero", "sham", "same_donor", "orthogonal_donor"])
def test_sham_zero_bitexact_object_identity(dtype, mode, device):
    h = torch.tensor([[1., -0., -2.]], dtype=dtype, device=device)
    q = torch.eye(3, device=device)[:, :1]
    donor = h.clone() if mode == "same_donor" else h + 1
    if mode == "orthogonal_donor":
        donor[:, 0] = h[:, 0]
    saved_bits = h.view(torch.uint8).clone()
    edited, t = patch_component(h, donor, q, alpha=0 if mode == "zero" else 1, sham=mode == "sham")
    assert edited is h
    assert torch.equal(edited.view(torch.uint8), saved_bits)
    assert not t["requested_delta"].any() and not t["actual_delta"].any()
    assert t["cosine"].item() == t["norm_ratio"].item() == 1
    assert t["relative_error"].item() == 0
    assert t["identity"].all() and not t["rounded_to_zero"].any()


def test_bf16_nonzero_request_rounds_to_zero_expressly(device):
    h = torch.tensor([[1., 4.]], dtype=torch.bfloat16, device=device)
    donor = torch.tensor([[2., 4.]], dtype=h.dtype, device=device)
    q = torch.eye(2, device=device)[:, :1]
    edited, t = patch_component(h, donor, q, alpha=.001)
    assert torch.equal(edited, h)
    assert t["requested_norm"].item() == pytest.approx(.001)
    assert t["actual_norm"].item() == 0
    assert t["cosine"].item() == t["norm_ratio"].item() == 0
    assert t["relative_error"].item() == 1
    assert t["rounded_to_zero"].all() and t["nonzero_requested"].all()
    assert not t["nonzero_actual"].any()


def test_bf16_partial_delivery_matches_actual_native_arithmetic(device):
    h = torch.tensor([[1., 2.]], dtype=torch.bfloat16, device=device)
    donor = torch.tensor([[2., 3.]], dtype=h.dtype, device=device)
    q = torch.eye(2, device=device)
    edited, t = patch_component(h, donor, q, alpha=.01)
    expected = (h.float() + .01).to(h.dtype)
    assert torch.equal(edited, expected)
    actual = [(float(b) - float(a)) for a, b in zip(h[0], expected[0])]
    request = [.01, .01]
    rn = math.sqrt(sum(x*x for x in request))
    an = math.sqrt(sum(x*x for x in actual))
    assert t["actual_norm"].item() == pytest.approx(an)
    assert t["norm_ratio"].item() == pytest.approx(an / rn)
    assert t["relative_error"].item() == pytest.approx(math.sqrt(sum((a-b)**2 for a, b in zip(actual, request))) / rn)
    assert t["cosine"].item() == pytest.approx(sum(a*b for a, b in zip(actual, request)) / (an*rn))


def test_mixed_batch_zero_and_nonzero_delivery(device):
    h = torch.tensor([[1., 4.], [1., 4.], [1., 4.]], dtype=torch.bfloat16, device=device)
    donor = torch.tensor([[1., 4.], [2., 4.], [1024., 4.]], dtype=h.dtype, device=device)
    edited, t = patch_component(h, donor, torch.eye(2, device=device)[:, :1], alpha=.001)
    assert t["nonzero_requested"].tolist() == [False, True, True]
    assert t["nonzero_actual"].tolist() == [False, False, True]
    assert t["rounded_to_zero"].tolist() == [False, True, False]
    assert t["cosine"][:2].tolist() == [1., 0.]
    assert t["relative_error"][:2].tolist() == [0., 1.]
    assert t["norm_ratio"][:2].tolist() == [1., 0.]
    assert torch.equal(edited[:2], h[:2])


def test_matching_controls_request_not_bf16_delivery(device):
    h = torch.ones(2, dtype=torch.bfloat16, device=device)
    edited, t = patch_component(h, h + 1, torch.eye(2, device=device), requested_norm=.001)
    assert t["requested_norm"].item() == pytest.approx(.001)
    assert t["actual_norm"].item() == 0
    assert t["rounded_to_zero"].item()
    assert torch.equal(edited, h)


@pytest.mark.parametrize("target", [2., torch.tensor(2.), torch.tensor([2., 3.])])
def test_positive_requested_norm_matching(target, device):
    q = random_orthonormal_basis(11, 3, seed=4, device=device)
    h, donor = noise((2, 11), device), noise((2, 11), device, 21)
    _, raw = patch_component(h, donor, q, alpha=.2)
    edited, t = patch_component(h, donor, q, alpha=.2, requested_norm=target)
    expected_norm = torch.as_tensor(target, device=device).expand(2)
    torch.testing.assert_close(t["requested_norm"], expected_norm)
    torch.testing.assert_close(t["requested_delta"] / t["requested_norm"][:, None],
                               raw["requested_delta"] / raw["requested_norm"][:, None])
    torch.testing.assert_close(t["actual_norm"], expected_norm)
    assert edited.shape == h.shape


def test_matching_rejects_zero_direction_in_any_position():
    h = torch.tensor([[0., 0.], [1., 1.]])
    donor = torch.tensor([[0., 1.], [2., 2.]])
    with pytest.raises(ValueError, match="zero source delta"):
        patch_component(h, donor, torch.eye(2)[:, :1], requested_norm=1.)


@pytest.mark.parametrize("target", [0., -1., float("nan"), float("inf"), True,
                                        torch.ones(2, 1), torch.ones(2, dtype=torch.int64)])
def test_invalid_matched_norm(target):
    with pytest.raises(ValueError):
        patch_component(torch.zeros(2, 3), torch.ones(2, 3), torch.eye(3), requested_norm=target)


@pytest.mark.parametrize("kwargs", [{"alpha": 0}, {"sham": True}])
def test_matching_cannot_override_noop(kwargs):
    with pytest.raises(ValueError, match="sham or zero alpha"):
        patch_component(torch.zeros(2), torch.ones(2), torch.eye(2), requested_norm=1., **kwargs)


def test_removal_and_later_separate_restoration(device):
    h = torch.tensor([2., 3., 7.], device=device)
    q = torch.eye(3, device=device)[:, :2]
    removed, _ = patch_component(h, torch.zeros_like(h), q)
    assert removed.tolist() == [0., 0., 7.]
    later = removed + torch.tensor([0., 0., 5.], device=device)
    restored, _ = patch_component(later, h, q)
    assert restored.tolist() == [2., 3., 12.]
    assert h.tolist() == [2., 3., 7.]


def test_private_rng_and_cpu_first_random_basis(device):
    cpu_state = torch.random.get_rng_state().clone()
    cuda_state = torch.cuda.get_rng_state(device).clone() if device.type == "cuda" else None
    q = random_orthonormal_basis(23, 8, seed=123, device=device)
    assert torch.equal(q.cpu(), random_orthonormal_basis(23, 8, seed=123))
    assert not torch.equal(q, random_orthonormal_basis(23, 8, seed=124, device=device))
    assert torch.equal(cpu_state, torch.random.get_rng_state())
    if cuda_state is not None:
        assert torch.equal(cuda_state, torch.cuda.get_rng_state(device))


@pytest.mark.parametrize("kwargs", [
    {"width": 0}, {"width": True}, {"rank": 0}, {"rank": 9}, {"rank": 2.5},
    {"seed": -1}, {"seed": 2**63}, {"seed": True}, {"width": 2, "rank": 3},
])
def test_random_basis_validation(kwargs):
    arguments = {"width": 10, "rank": 3, "seed": 1}
    arguments.update(kwargs)
    with pytest.raises(ValueError):
        random_orthonormal_basis(**arguments)


@pytest.mark.parametrize("alpha", [-.1, 1.1, float("nan"), float("inf"), True, "1"])
def test_alpha_validation(alpha):
    with pytest.raises(ValueError):
        patch_component(torch.zeros(2), torch.ones(2), torch.eye(2), alpha=alpha)


@pytest.mark.parametrize("field,value", [
    ("hidden", torch.tensor(1.)), ("hidden", torch.ones(0, 3)),
    ("hidden", torch.ones(2, 3, dtype=torch.int64)),
    ("donor", torch.ones(3)), ("donor", torch.ones(2, 3, dtype=torch.bfloat16)),
    ("basis", torch.ones(3)), ("basis", torch.eye(2)), ("basis", torch.zeros(3, 1)),
    ("basis", torch.ones(3, 2)), ("basis", 2 * torch.eye(3)),
    ("basis", torch.eye(3, dtype=torch.bfloat16)), ("basis", torch.ones(3, 0)),
    ("basis", torch.ones(3, 9)), ("sham", 1),
])
def test_patch_shape_dtype_and_basis_validation(field, value):
    arguments = {"hidden": torch.zeros(2, 3), "donor": torch.ones(2, 3), "basis": torch.eye(3)}
    arguments[field] = value
    with pytest.raises(ValueError):
        patch_component(**arguments)


@pytest.mark.parametrize("field", ["hidden", "donor", "basis"])
@pytest.mark.parametrize("value", [float("nan"), float("inf"), -float("inf")])
def test_nonfinite_rejected_even_on_zero(field, value):
    arguments = {"hidden": torch.zeros(2, 3), "donor": torch.ones(2, 3), "basis": torch.eye(3)}
    arguments[field][0, 0] = value
    with pytest.raises(ValueError, match="finite"):
        patch_component(**arguments, alpha=0)


def test_arithmetic_overflow_fails_closed():
    h = torch.tensor([-3e38])
    with pytest.raises(ValueError, match="finite"):
        patch_component(h, -h, torch.ones(1, 1))
    with pytest.raises(ValueError, match="finite"):
        patch_component(torch.zeros(1, dtype=torch.float16), torch.ones(1, dtype=torch.float16),
                        torch.ones(1, 1), requested_norm=1e6)


@pytest.mark.parametrize("dtype", [torch.float32, torch.bfloat16, torch.float16])
def test_no_input_mutation_noncontiguous_shape_and_autocast(dtype, device):
    h = noise((2, 7, 3), device).to(dtype).transpose(1, 2)
    donor = noise((2, 7, 3), device, 29).to(dtype).transpose(1, 2)
    q = random_orthonormal_basis(7, 3, seed=6, device=device)
    norm = torch.full((2, 3), .5, device=device)
    originals = [tensor.clone() for tensor in (h, donor, q, norm)]
    expected, _ = patch_component(h, donor, q, alpha=.4, requested_norm=norm)
    with torch.autocast(device_type=device.type, dtype=torch.bfloat16):
        edited, t = patch_component(h, donor, q, alpha=.4, requested_norm=norm)
        autocast_q = orthonormal_basis(q.T)
    assert torch.equal(edited, expected)
    torch.testing.assert_close(autocast_q, q)
    assert edited.shape == h.shape and edited.device == h.device and edited.dtype == h.dtype
    for source, saved in zip((h, donor, q, norm), originals):
        assert torch.equal(source, saved)
    for name, value in t.items():
        assert value.device == h.device
        assert value.dtype in (torch.float32, torch.bool)
        assert torch.isfinite(value).all(), name
    t["before"].zero_()
    t["after"].zero_()
    assert torch.equal(h, originals[0]) and torch.equal(edited, expected)


def test_cross_device_rejected_when_cuda_enabled(device):
    if device.type != "cuda":
        pytest.skip("Cross-device check needs opt-in CUDA")
    h = torch.ones(3, device=device)
    with pytest.raises(ValueError, match="device"):
        patch_component(h, h.cpu(), torch.eye(3, device=device))
    with pytest.raises(ValueError, match="device"):
        patch_component(h, h, torch.eye(3))

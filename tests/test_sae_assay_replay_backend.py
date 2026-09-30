import numpy as np
import pytest
import torch

from experiments.sae_assay_replay.backend import delivery, qualify, replay


def weights(dtype=torch.float32):
    e = torch.eye(8, dtype=dtype)
    b = torch.zeros(8, dtype=dtype)
    return e, b, e.T.contiguous(), b


def test_synthetic_qualification_cpu():
    assert qualify("cpu")["pass"]


@pytest.mark.parametrize("dtype", [torch.float32, torch.bfloat16])
def test_zero_support_target_and_neighbor_identity(dtype):
    h = torch.tensor([[1, 2, 3, 4, 5, 6, 1000, 1000],
                      [-1, -2, -3, -4, -5, -6, 1000, 1000]], dtype=dtype)
    saved = h.clone()
    result = replay(h, weights(dtype), list(range(6)), np.eye(6))
    assert torch.equal(h, saved)
    assert all(result["zero"]["identity"])
    assert result["zero"]["requested_norm"] == [0, 0]
    for mode in ("suppression", "amplification"):
        a = result[mode]
        assert a["identity"][1] and not a["nonzero_requested"][1]
        assert a["non_target_changed_count"] == [0, 0]
        assert a["non_target_activity_changes"] == [0, 0]
        assert a["cosine"][0] == pytest.approx(1)
        expected = .25 if mode == "suppression" else 1.75
        np.testing.assert_allclose(a["after"][0], expected * np.arange(1, 7))


def test_capped_request_keeps_original_coordinate_intent():
    h = torch.ones((1, 8))
    result = replay(h, weights(), list(range(6)), np.eye(6))
    a = result["suppression"]
    assert a["projection_scale"][0] < 1
    assert a["requested_activation_delta"][0] == [-.75] * 6
    assert a["requested_norm"][0] / a["clean_norm"][0] == pytest.approx(.04)
    assert all(x > .5 for x in a["after"][0])


def test_tiny_bf16_request_rounded_away_is_failure_not_missing():
    h = torch.ones((1, 8), dtype=torch.bfloat16)
    request = torch.full((1, 8), 1e-5)
    edited = (h.float() + request).bfloat16()
    a = delivery(h, request, edited)
    assert a["nonzero_requested"].item()
    assert a["realized_norm"].item() == 0
    assert a["cosine"].item() == 0
    assert a["relative_error"].item() == pytest.approx(1)


def test_non_target_movement_is_recorded():
    e, b, d, db = weights()
    e[6, 0] = 1
    h = torch.tensor([[1, 2, 3, 4, 5, 6, 1000, 1000.]])
    a = replay(h, (e, b, d, db), list(range(6)), np.eye(6))["amplification"]
    assert a["non_target_change_norm"][0] == pytest.approx(.75)
    assert a["non_target_changed_count"][0] == 1


def test_invalid_inputs_fail_without_loading_model():
    h = torch.ones(1, 8)
    for ids in ([0, 0], [8], [True], []):
        with pytest.raises(ValueError):
            replay(h, weights(), ids, np.eye(len(ids)))
    with pytest.raises(ValueError):
        replay(h, weights(torch.bfloat16), [0], np.eye(1))
    with pytest.raises(FloatingPointError):
        replay(h * float("nan"), weights(), [0], np.eye(1))

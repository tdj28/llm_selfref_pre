"""Tiny CPU bridge tests only: no downloads, model artifacts, or production runs."""

from types import SimpleNamespace
from unittest.mock import patch

import pytest

torch = pytest.importorskip("torch")
transformers = pytest.importorskip("transformers")
import torch.nn.functional as F

from experiments.sae_assay_precision.bridge import (
    READOUT_AUTHORITY, _delivery, full_width_readout, precision_bridge, qualify_bridge,
)


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    monkeypatch.setenv("HF_HUB_OFFLINE", "1")
    monkeypatch.setenv("TRANSFORMERS_OFFLINE", "1")

    def blocked(*args, **kwargs):
        raise AssertionError("Network use is forbidden in tiny CPU tests")

    monkeypatch.setattr("socket.socket.connect", blocked)
    monkeypatch.setattr("socket.create_connection", blocked)


@pytest.fixture
def tiny():
    with torch.random.fork_rng(devices=[]):
        torch.manual_seed(917)
        config = transformers.LlamaConfig(vocab_size=32, hidden_size=16,
            intermediate_size=32, num_hidden_layers=4, num_attention_heads=2,
            num_key_value_heads=2, max_position_embeddings=64, attention_dropout=0.,
            bos_token_id=1, eos_token_id=2, pad_token_id=0)
        config._attn_implementation = "sdpa"
        model = transformers.LlamaForCausalLM(config).to(torch.bfloat16).eval()
        with torch.no_grad():
            for module in model.modules():
                if type(module).__name__ == "LlamaRMSNorm":
                    module.weight.copy_(torch.rand_like(module.weight.float()) * .5 + .75)
    return SimpleNamespace(model=model, layer_index=1, dtype=torch.bfloat16)


def no_hooks(model):
    return not any(module._forward_hooks or module._forward_pre_hooks for module in model.modules())


def tokens():
    return torch.tensor([[1, 4, 7, 6, 9]])


def test_native_zero_exact_output_identity_weights_and_cleanup(tiny):
    frozen = {name: value.clone() for name, value in tiny.model.state_dict().items()}
    with torch.inference_mode():
        plain = tiny.model.model(tokens(), use_cache=False).last_hidden_state
        with precision_bridge(tiny, native_zero=True) as bridge:
            actual = tiny.model.model(tokens(), use_cache=False).last_hidden_state
    assert torch.equal(actual, plain)
    record, = bridge.records
    assert record["returned_original_output"]
    assert record["clean_native"].dtype == record["edited_state"].dtype == torch.bfloat16
    assert torch.equal(record["clean_native"], record["edited_state"])
    assert record["delivery"]["identity"].all()
    assert not record["delivery"]["nonzero_requested"].any()
    assert not bridge.boundary_trace
    assert not bridge.metadata["higher_precision_residual_model"]
    assert bridge.metadata["hooks_removed"] and no_hooks(tiny.model)
    assert all(torch.equal(value, tiny.model.state_dict()[name]) for name, value in frozen.items())


@pytest.mark.parametrize("sign", [0, -1, 1])
def test_fp32_residual_bf16_norm_linears_head_and_weights(tiny, sign):
    parameters = {name: (id(p), p.clone()) for name, p in tiny.model.named_parameters()}
    seen_linears, seen_layers = [], []
    handles = []
    for module in tiny.model.modules():
        if isinstance(module, torch.nn.Linear):
            handles.append(module.register_forward_pre_hook(
                lambda _module, inputs: seen_linears.append(inputs[0].dtype)))
    for index, layer in enumerate(tiny.model.model.layers):
        handles.append(layer.register_forward_hook(
            lambda _module, _inputs, output, index=index: seen_layers.append((index, output[0].dtype))))
    callback = None if sign == 0 else lambda h: torch.full_like(h, sign * 1e-4, dtype=torch.float32)
    try:
        with precision_bridge(tiny, callback) as bridge:
            result = tiny.model(tokens(), use_cache=False)
    finally:
        for handle in handles:
            handle.remove()
    assert all(dtype == torch.bfloat16 for dtype in seen_linears)
    assert seen_layers[-1][1] == torch.float32
    assert result.logits.dtype == torch.bfloat16
    assert torch.isfinite(result.logits).all()
    assert len(bridge.boundary_trace) == 5
    assert bridge.boundary_trace[-1]["module"] == "model.norm"
    assert all(event["input_dtype"] == event["output_dtype"] == "torch.float32"
               and event["returned_dtype"] == "torch.bfloat16" for event in bridge.boundary_trace)
    record, = bridge.records
    assert torch.equal(record["edited_state"], record["clean_native"].float() + record["requested_fp32"])
    assert record["edited_state"].dtype == torch.float32
    assert not record["returned_original_output"]
    assert bridge.metadata["higher_precision_residual_model"]
    assert bridge.metadata["new_operator"] and not bridge.metadata["fp32_shadow_only"]
    if sign == 0:
        assert record["delivery"]["identity"].all()
    else:
        assert record["delivery"]["nonzero_requested"].all()
        assert (record["delivery"]["relative_error"] < .2).all()
    for name, (identity, value) in parameters.items():
        current = dict(tiny.model.named_parameters())[name]
        assert id(current) == identity and torch.equal(value, current)
    assert no_hooks(tiny.model)


def test_post_completed_norm_cast_is_bound_not_native_rounding(tiny):
    norm = tiny.model.model.layers[2].input_layernorm
    observed = []
    handle = norm.register_forward_hook(lambda _m, args, out: observed.append((args[0].clone(), out.clone())))
    try:
        with precision_bridge(tiny) as bridge:
            tiny.model.model(tokens(), use_cache=False)
    finally:
        handle.remove()
    h, output = observed[0]
    with torch.inference_mode():
        normalized = h * torch.rsqrt(h.square().mean(-1, keepdim=True) + norm.variance_epsilon)
        post_cast = (norm.weight * normalized).bfloat16()
        intermediate_cast = norm.weight * normalized.bfloat16()
    assert torch.equal(output.bfloat16(), post_cast)
    assert not torch.equal(post_cast, intermediate_cast)
    assert "including weight multiplication" in bridge.metadata["normalization_boundary"]


def test_cached_sham_and_signed_keep_bf16_kv_and_observe_each_forward(tiny):
    for callback in (None, lambda h: torch.full_like(h, -1e-4, dtype=torch.float32)):
        with precision_bridge(tiny, callback) as bridge:
            prefill = tiny.model.model(tokens()[:, :3], use_cache=True,
                                      past_key_values=transformers.DynamicCache())
            cached = tiny.model.model(tokens()[:, 3:4], use_cache=True,
                                     past_key_values=prefill.past_key_values)
        assert len(bridge.records) == 2 and len(bridge.boundary_trace) == 10
        assert bridge.records[0]["edited_state"].shape == (1, 3, 16)
        assert bridge.records[1]["edited_state"].shape == (1, 1, 16)
        assert all(t.dtype == torch.bfloat16 for pair in cached.past_key_values for t in pair)
        assert no_hooks(tiny.model)


def test_fp64_metrics_do_not_hide_even_fp32_lost_requests():
    h = torch.ones(1, 8, dtype=torch.bfloat16)
    for magnitude, lost in ((1e-4, False), (1e-10, True)):
        requested = torch.full(h.shape, magnitude)
        edited = h.float() + requested
        measured = _delivery(h, requested, edited)
        assert measured["relative_error"].dtype == torch.float64
        assert measured["nonzero_requested"].all()
        if lost:
            assert measured["relative_error"].item() == 1
            assert measured["cosine"].item() == 0
        else:
            assert measured["relative_error"].item() < .001
    assert _delivery(h, torch.zeros(h.shape), h.float())["identity"].all()


def test_full_width_readout_preserves_native_reference_and_new_authority():
    h = torch.tensor([[1.125, -.5, .25], [.375, .625, -.875]], dtype=torch.bfloat16)
    e = torch.tensor([[.101, .207, -.113], [.327, -.549, .163], [-.613, .251, .379],
                      [.143, -.331, .577]], dtype=torch.bfloat16)
    b = torch.tensor([.251, .131, -.119, .137], dtype=torch.bfloat16)
    x = h.float() + torch.tensor([[1e-4, -1e-4, 1e-4], [0, 0, 0]])
    frozen = e.clone()
    calls = []
    original = F.linear

    def observe(value, weight, bias=None):
        calls.append((tuple(value.shape), tuple(weight.shape)))
        return original(value, weight, bias)

    with patch("torch.nn.functional.linear", side_effect=observe):
        result = full_width_readout(h, x, e, b)
    assert calls == [((1, 3), (4, 3))] * 8
    assert result["authority"] == READOUT_AUTHORITY and not result["native_encoding_replacement"]
    assert torch.equal(result["native_clean"], torch.cat([F.relu(F.linear(row[None], e, b)).float() for row in h]))
    assert torch.equal(result["precision_readout_shift"], result["promoted_clean"] - result["native_clean"])
    assert (result["precision_readout_shift"] != 0).any()
    assert torch.equal(result["native_clean"], result["native_rounded_edited"])
    assert (result["promoted_edit_delta"][0] != 0).any()
    assert not result["promoted_edit_delta"][1].any()
    assert torch.equal(e, frozen)


@pytest.mark.parametrize("callback,exception", [
    (lambda h: torch.zeros_like(h), ValueError),
    (lambda h: torch.zeros(1), ValueError),
    (lambda h: torch.full_like(h, float("nan"), dtype=torch.float32), FloatingPointError),
])
def test_bad_request_fails_closed_and_cleans_hooks(tiny, callback, exception):
    bridge = precision_bridge(tiny, callback)
    with pytest.raises(exception):
        with bridge:
            tiny.model.model(tokens(), use_cache=False)
    assert bridge.metadata["hooks_removed"] and no_hooks(tiny.model)
    with precision_bridge(tiny, native_zero=True):
        tiny.model.model(tokens(), use_cache=False)


def test_callback_receives_copy_and_native_zero_forbids_callback(tiny):
    with precision_bridge(tiny, native_zero=True) as baseline:
        tiny.model.model(tokens(), use_cache=False)

    def request(h):
        h.zero_()
        return torch.zeros_like(h, dtype=torch.float32)

    with precision_bridge(tiny, request) as bridge:
        tiny.model.model(tokens(), use_cache=False)
    assert torch.equal(bridge.records[0]["clean_native"], baseline.records[0]["clean_native"])
    with pytest.raises(ValueError, match="Native zero"):
        precision_bridge(tiny, request, native_zero=True)


def test_context_failure_nested_and_partial_install_cleanup(tiny):
    with pytest.raises(RuntimeError, match="deliberate"):
        with precision_bridge(tiny) as bridge:
            with pytest.raises(RuntimeError, match="overlap"):
                with precision_bridge(tiny):
                    pass
            raise RuntimeError("deliberate")
    assert bridge.metadata["hooks_removed"] and no_hooks(tiny.model)
    norm = tiny.model.model.layers[2].input_layernorm
    with patch.object(norm, "register_forward_hook", side_effect=RuntimeError("install failed")):
        with pytest.raises(RuntimeError, match="install failed"):
            with precision_bridge(tiny):
                pass
    assert no_hooks(tiny.model)
    with precision_bridge(tiny, native_zero=True):
        tiny.model.model(tokens(), use_cache=False)


def test_incomplete_downstream_path_fails_and_cleans(tiny):
    bridge = precision_bridge(tiny)
    with pytest.raises(RuntimeError, match="all downstream"):
        with bridge:
            bridge._boundary(None, (), (torch.ones(1, 2, 16, dtype=torch.bfloat16),))
    assert no_hooks(tiny.model)


@pytest.mark.parametrize("native_zero", [False, True])
def test_original_math_flags_are_preserved_outside_request(tiny, native_zero):
    previous = torch.backends.cuda.matmul.allow_tf32
    observed, callback_flags = [], []
    handles = [layer.register_forward_pre_hook(lambda _m, _args: observed.append(
        torch.backends.cuda.matmul.allow_tf32)) for layer in tiny.model.model.layers]

    def request(h):
        callback_flags.append(torch.backends.cuda.matmul.allow_tf32)
        return torch.zeros_like(h, dtype=torch.float32)

    try:
        torch.backends.cuda.matmul.allow_tf32 = True
        with precision_bridge(tiny, None if native_zero else request, native_zero=native_zero):
            tiny.model.model(tokens(), use_cache=False)
        assert torch.backends.cuda.matmul.allow_tf32
    finally:
        torch.backends.cuda.matmul.allow_tf32 = previous
        for handle in handles:
            handle.remove()
    assert observed == [True] * 4
    assert callback_flags == ([] if native_zero else [False])


def test_outer_autocast_is_rejected_without_installing_hooks(tiny):
    with torch.autocast("cpu", dtype=torch.bfloat16):
        with pytest.raises(RuntimeError, match="autocast disabled"):
            with precision_bridge(tiny):
                pass
    assert no_hooks(tiny.model)


def test_native_zero_preserves_tuple_identity_and_extra_outputs(tiny):
    bridge = precision_bridge(tiny, native_zero=True)
    output = (torch.ones(1, 2, 16, dtype=torch.bfloat16), object(), {"cache": "sentinel"})
    with bridge:
        assert bridge._boundary(None, (), output) is output


def test_post_forward_exception_removes_hooks_and_restores_native(tiny):
    with torch.inference_mode():
        reference = tiny.model.model(tokens(), use_cache=False).last_hidden_state
    with pytest.raises(RuntimeError, match="downstream failed"):
        with precision_bridge(tiny) as bridge:
            tiny.model.model(tokens(), use_cache=False)
            raise RuntimeError("downstream failed")
    assert bridge.metadata["hooks_removed"] and no_hooks(tiny.model)
    with torch.inference_mode():
        assert torch.equal(reference, tiny.model.model(tokens(), use_cache=False).last_hidden_state)


def test_mid_forward_exception_keeps_original_error_and_cleans_hooks(tiny):
    norm = tiny.model.model.layers[2].input_layernorm
    with patch.object(norm, "forward", side_effect=RuntimeError("norm failed")):
        with pytest.raises(RuntimeError, match="norm failed"):
            with precision_bridge(tiny) as bridge:
                tiny.model.model(tokens(), use_cache=False)
    assert len(bridge.records) == 1 and not bridge.boundary_trace
    assert bridge.metadata["hooks_removed"] and no_hooks(tiny.model)


def test_explicit_zero_callback_matches_sham_on_same_precision_path(tiny):
    with precision_bridge(tiny) as sham:
        reference = tiny.model.model(tokens(), use_cache=False).last_hidden_state
    with precision_bridge(tiny, lambda h: torch.zeros_like(h, dtype=torch.float32)) as zero_edit:
        actual = tiny.model.model(tokens(), use_cache=False).last_hidden_state
    assert torch.equal(reference, actual)
    assert sham.boundary_trace == zero_edit.boundary_trace
    assert torch.equal(sham.records[0]["edited_state"], zero_edit.records[0]["edited_state"])


@pytest.mark.parametrize("change", ["training", "weights", "layer"])
def test_unsupported_model_state_rejected(tiny, change):
    if change == "training":
        tiny.model.train()
    elif change == "weights":
        tiny.model.float()
    else:
        tiny.layer_index = 3
    with pytest.raises(ValueError):
        precision_bridge(tiny)
    assert no_hooks(tiny.model)


def test_synthetic_cpu_qualification():
    report = qualify_bridge("cpu")
    assert report["pass"], report["checks"]
    assert report["synthetic_only"] and not report["production_model_loaded"]
    assert report["device"] == "cpu"

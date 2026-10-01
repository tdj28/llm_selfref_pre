"""Offline tests: actual random tiny Llama, no model downloads or target calls."""
import math
import os
from types import SimpleNamespace
from unittest.mock import patch

import pytest
import torch

from experiments.jlens_causal_report import backend as b


class TinyTokenizer:
    eos_token_id = 2
    chat_template = "offline fixture template"
    all_special_ids = [0, 1, 2]

    def apply_chat_template(self, messages, **kwargs):
        assert kwargs == dict(tokenize=True, add_generation_prompt=True,
                              return_tensors="pt", truncation=False, padding=False)
        return torch.tensor([[1] + [3 + ord(c) % 29
                                    for m in messages for c in m["content"]]])

    def decode(self, ids, skip_special_tokens=True):
        return " ".join(str(i) for i in ids if not skip_special_tokens or i not in self.all_special_ids)


_DEVICES = ["cpu"] + (["cuda:0"] if os.environ.get("JLENS_TEST_CUDA") == "1" else [])


@pytest.fixture(params=[(device, dtype) for device in _DEVICES
                        for dtype in (torch.float32, torch.bfloat16)],
                ids=[f"{device}-{dtype}" for device in _DEVICES
                     for dtype in (torch.float32, torch.bfloat16)])
def tiny(request):
    transformers = pytest.importorskip("transformers")
    device, dtype = request.param
    cuda = device.startswith("cuda")
    if cuda:
        assert torch.cuda.is_available(), "JLENS_TEST_CUDA=1 requires actual CUDA; no CPU fallback"
        assert torch.cuda.is_bf16_supported(), "Native CUDA BF16 is required"
        torch.cuda.synchronize(device)
        initial_bytes = torch.cuda.memory_allocated(device)
        torch.cuda.reset_peak_memory_stats(device)
    threads = torch.get_num_threads()
    torch.set_num_threads(1)
    with torch.random.fork_rng():
        torch.manual_seed(20261001)
        config = transformers.LlamaConfig(
            vocab_size=32, hidden_size=16, intermediate_size=32,
            num_hidden_layers=3, num_attention_heads=2, num_key_value_heads=2,
            max_position_embeddings=32, bos_token_id=1, eos_token_id=2,
            pad_token_id=0, attention_dropout=0.)
        config._attn_implementation = "sdpa"
        model = transformers.LlamaForCausalLM(config).to(device=device, dtype=dtype).eval()
    obj = b.Backend.from_components_for_test(model, TinyTokenizer())
    try:
        assert obj.device == torch.device(device)
        assert obj.dtype == dtype
        assert all(p.device == obj.device and p.dtype == dtype for p in model.parameters())
        yield obj
    finally:
        if cuda:
            torch.cuda.synchronize(device)
            # Tensor allocator only: excludes the CUDA driver/context. Tiny
            # models must not silently load a production model or a full SAE.
            peak_bytes = torch.cuda.max_memory_allocated(device) - initial_bytes
        obj.close()
        torch.set_num_threads(threads)
    if cuda:
        assert peak_bytes < 512 * 1024**2, f"Tiny fixture used {peak_bytes} CUDA tensor bytes"


def kernel_tolerance(tiny):
    # Distinct GEMM/SDPA shapes (cached one-token vs full-prefix) can round
    # differently. Same-shape zero/sham comparisons below remain bit-exact.
    return .002 if tiny.dtype == torch.bfloat16 else 1e-6


def delta_edit(delta):
    def edit(h):
        delta_native = delta.to(device=h.device, dtype=torch.float32)
        return (h.float() + delta_native).to(h.dtype), {"requested_delta": delta_native}
    return edit


def assert_clean_hooks(tiny):
    assert all(not layer._forward_hooks for layer in tiny.model.model.layers)
    assert not tiny._active


def test_one_forward_native_captures_and_exact_zero(tiny):
    ids = torch.tensor([[1, 4, 5, 6]])
    with torch.inference_mode():
        reference = tiny.model(ids.to(tiny.device), use_cache=False).logits[0, -1].float().cpu()
    with patch.object(tiny.model.model, "forward", wraps=tiny.model.model.forward) as forward:
        plain = tiny.capture_or_edit(ids, layers=[0, 2])
    assert forward.call_count == 1
    assert forward.call_args.kwargs["use_cache"] is False
    assert forward.call_args.kwargs["past_key_values"] is None
    zero = tiny.capture_or_edit(ids, {0: delta_edit(torch.zeros(16))}, [0, 2])
    torch.testing.assert_close(reference, plain["logits"], atol=kernel_tolerance(tiny), rtol=0)
    assert torch.equal(plain["logits"], zero["logits"])
    for result in (plain, zero):
        assert result["input_token_ids"] == [1, 4, 5, 6]
        assert result["logits"].shape == (32,)
        assert result["logits"].device.type == "cpu"
        for record in result["captures"].values():
            assert record["before"].shape == record["after"].shape == (16,)
            assert record["before"].dtype == torch.float32
            assert record["before"].device.type == "cpu"
            assert not record["before"].requires_grad
            assert torch.equal(record["before"], record["after"])
            assert record["position"] == 3 and record["hook_calls"] == 1
    assert_clean_hooks(tiny)


def test_edit_isolated_at_explicit_position_and_inplace_callback(tiny):
    ids, position = [1, 4, 5, 6, 7], 2
    layer = tiny.model.model.layers[1]
    register = layer.register_forward_hook
    witnessed = []

    def install(hook):
        def inspect(module, inputs, output):
            h = output[0] if isinstance(output, tuple) else output
            original = h.clone()
            result = hook(module, inputs, output)
            edited = result[0] if isinstance(result, tuple) else result
            assert torch.equal(h, original)
            keep = [i for i in range(len(ids)) if i != position]
            assert torch.equal(edited[:, keep], original[:, keep])
            assert not torch.equal(edited[:, position], original[:, position])
            if isinstance(output, tuple):
                assert all(a is c for a, c in zip(output[1:], result[1:]))
            witnessed.append(True)
            return result
        return register(inspect)

    def mutate(h):
        h.add_(1)
        return h, {"nested": [h]}

    with patch.object(layer, "register_forward_hook", side_effect=install):
        result = tiny.capture_or_edit(ids, {1: mutate}, [1, 2], position=position)
    assert witnessed == [True]
    record = result["captures"][1]
    assert record["position"] == position
    assert torch.equal(record["after"], (record["before"].to(tiny.dtype) + 1).float())
    assert record["telemetry"]["nested"][0].device.type == "cpu"
    record["telemetry"]["nested"][0].zero_()
    assert torch.count_nonzero(record["after"])
    assert_clean_hooks(tiny)


def test_donor_projection_callback(tiny):
    from experiments.jlens_causal_report.operators import patch_component

    donor = tiny.capture_or_edit([1, 9, 10], layers=[1])["captures"][1]["before"]
    q = torch.eye(16, dtype=torch.float32)[:, :3]

    def replace(h):
        return patch_component(h, donor.to(device=h.device, dtype=h.dtype),
                               q.to(h.device))

    result = tiny.capture_or_edit([1, 4, 5], {1: replace}, [1])
    record = result["captures"][1]
    torch.testing.assert_close(record["after"][:3], donor[:3], atol=1e-8, rtol=0)
    assert torch.equal(record["after"][3:], record["before"][3:])
    assert torch.equal(record["after"], record["telemetry"]["after"])
    assert_clean_hooks(tiny)


@pytest.mark.parametrize("nonzero", [False, True], ids=["zero", "nonzero"])
def test_persistent_boundary_matches_cached_prefill_for_three_tokens(tiny, nonzero):
    prompt = torch.tensor([[1, 4, 5, 6]])
    forced = [7, 8, 9]
    delta = torch.linspace(-.1, .2, 16) if nonzero else torch.zeros(16)
    edit = delta_edit(delta)
    boundary = prompt.shape[1] - 1
    prefix, full_logits, full_records = prompt, [], []
    for token in forced:
        result = tiny.capture_or_edit(prefix, {1: edit}, [1], position=boundary)
        full_logits.append(result["logits"])
        full_records.append(result["captures"][1])
        prefix = torch.cat((prefix, torch.tensor([[token]])), dim=1)

    # Independent cached path edits only the original prefill boundary. Its
    # downstream KV state must agree with reapplying that edit on full prefixes.
    def prefill_hook(_module, _inputs, output):
        h = output[0] if isinstance(output, tuple) else output
        changed = h.clone()
        changed[0, boundary] = edit(h[0, boundary].clone())[0]
        return (changed,) + output[1:] if isinstance(output, tuple) else changed

    cached_logits = []
    handle = tiny.model.model.layers[1].register_forward_hook(prefill_hook)
    try:
        with torch.inference_mode():
            out = tiny.model(prompt.to(tiny.device), use_cache=True)
    finally:
        handle.remove()
    cached_logits.append(out.logits[0, -1].float().cpu())
    for token in forced[:-1]:
        with torch.inference_mode():
            out = tiny.model(torch.tensor([[token]], device=tiny.device), past_key_values=out.past_key_values,
                             use_cache=True)
        cached_logits.append(out.logits[0, -1].float().cpu())
    tolerance = kernel_tolerance(tiny)
    for full, cached in zip(full_logits, cached_logits):
        torch.testing.assert_close(full, cached, atol=tolerance, rtol=0)
        assert full.argmax() == cached.argmax()
    for record in full_records:
        assert record["position"] == boundary
        torch.testing.assert_close(record["after"], full_records[0]["after"],
                                   atol=tolerance, rtol=0)
    scored = tiny.score_continuation(prompt, forced, edits={1: edit}, layers=[1])
    expected = math.fsum(torch.log_softmax(logits.double(), -1)[token].item()
                         for logits, token in zip(full_logits, forced))
    assert scored["sum_logprob"] == pytest.approx(expected, abs=1e-12)
    if nonzero:
        clean = tiny.capture_or_edit(prompt, layers=[1])
        assert not torch.equal(clean["logits"], full_logits[0])
    assert_clean_hooks(tiny)


def test_exact_continuation_scoring_no_retokenization_or_eos_drop(tiny):
    prompt, continuation = [1, 4, 5], [6, 2, 7]
    with torch.inference_mode():
        logits = tiny.model(torch.tensor([prompt + continuation], device=tiny.device),
                            use_cache=False).logits
    with patch.object(tiny.tokenizer, "decode", side_effect=AssertionError("retokenization")):
        result = tiny.score_continuation(prompt, continuation)
    expected = [torch.log_softmax(logits[0, len(prompt) - 1 + i].double(), -1)[t].item()
                for i, t in enumerate(continuation)]
    assert result["token_logprobs"] == pytest.approx(expected, abs=2 * kernel_tolerance(tiny))
    assert result["sum_logprob"] == pytest.approx(sum(expected), abs=6 * kernel_tolerance(tiny))
    assert result["output_token_ids"] == continuation
    with patch.object(tiny.model.model, "forward", side_effect=AssertionError("empty forward")):
        empty = tiny.score_continuation(prompt, [])
    assert empty["sum_logprob"] == 0 and empty["token_logprobs"] == []


def test_generation_reapplies_fixed_boundary_rng_isolation_and_cap(tiny):
    tiny.model.generation_config.eos_token_id = None
    tiny.tokenizer.eos_token_id = None
    seen = []

    def edit(h):
        seen.append(h.clone())
        return h + .25, {"fixed": True}

    rng = torch.get_rng_state().clone()
    with patch.object(tiny.model.model, "forward", wraps=tiny.model.model.forward) as forward:
        first = tiny.generate([1, 4, 5], 42, .7, 3, edits={1: edit}, layers=[1, 2])
    assert forward.call_count == 3
    assert [call.kwargs["input_ids"].shape[1] for call in forward.call_args_list] == [3, 4, 5]
    assert len(seen) == 3
    for h in seen:
        torch.testing.assert_close(h, seen[0], atol=kernel_tolerance(tiny), rtol=0)
    second = tiny.generate([1, 4, 5], 42, .7, 3, edits={1: edit}, layers=[1, 2])
    assert first["output_token_ids"] == second["output_token_ids"]
    assert torch.equal(rng, torch.get_rng_state())
    assert first["cap_hit"] and not first["eos"]
    assert first["intervention_position"] == 2
    assert [s["position"] for s in first["steps"]] == [2, 2, 2]
    assert [s["logit_position"] for s in first["steps"]] == [2, 3, 4]
    assert all(r["position"] == 2 for s in first["steps"] for r in s["captures"].values())
    assert all("logits" not in s for s in first["steps"])
    scored = tiny.score_continuation([1, 4, 5], first["output_token_ids"], edits={1: edit})
    assert scored["token_logprobs"] == [s["model_logprob"] for s in first["steps"]]
    assert_clean_hooks(tiny)


def test_eos_at_cap_is_eos_not_cap_and_zero_generation(tiny):
    plain = tiny.generate([1, 4, 5], 3, 0., 3)
    zero = tiny.generate([1, 4, 5], 3, 0., 3, edits={1: delta_edit(torch.zeros(16))})
    assert plain["output_token_ids"] == zero["output_token_ids"]
    with torch.no_grad():
        tiny.model.lm_head.weight.zero_()
    tiny.model.generation_config.eos_token_id = [0]
    result = tiny.generate([1, 4, 5], 3, 0., 1)
    assert result["output_token_ids"] == [0]
    assert result["eos"] and not result["cap_hit"] and result["stop_reason"] == "eos"


@pytest.mark.parametrize("kind", ["shape", "dtype", "nan", "telemetry", "return", "raise"])
def test_callback_failure_removes_all_hooks(tiny, kind):
    def bad(h):
        if kind == "shape":
            return h[None], {}
        if kind == "dtype":
            return h.double(), {}
        if kind == "nan":
            return h * float("nan"), {}
        if kind == "telemetry":
            return h, {"bad": float("inf")}
        if kind == "return":
            return h
        raise RuntimeError("callback failed")

    with pytest.raises((ValueError, FloatingPointError, RuntimeError)):
        tiny.capture_or_edit([1, 4], {1: bad}, [0, 1, 2])
    assert_clean_hooks(tiny)
    tiny.capture_or_edit([1, 4], layers=[1])


def test_forward_missing_duplicate_and_registration_failure_cleanup(tiny):
    fake = SimpleNamespace(last_hidden_state=torch.zeros(1, 2, 16, dtype=tiny.dtype))
    with patch.object(tiny.model.model, "forward", return_value=fake):
        with pytest.raises(ValueError, match="Missing"):
            tiny.capture_or_edit([1, 4], layers=[0, 1])
    assert_clean_hooks(tiny)
    original = tiny.model.model.layers[1]
    tiny.model.model.layers[1] = tiny.model.model.layers[0]
    try:
        with pytest.raises(ValueError, match="Hook call"):
            tiny.capture_or_edit([1, 4], layers=[0])
    finally:
        tiny.model.model.layers[1] = original
    assert_clean_hooks(tiny)
    with patch.object(original, "register_forward_hook", side_effect=RuntimeError("register")):
        with pytest.raises(RuntimeError, match="register"):
            tiny.capture_or_edit([1, 4], layers=[0, 1])
    assert_clean_hooks(tiny)


def test_head_failure_unrelated_hook_preservation_and_reentry(tiny):
    external = tiny.model.model.layers[0].register_forward_hook(lambda *args: None)
    try:
        with patch.object(tiny.model.lm_head, "forward", side_effect=RuntimeError("head")):
            with pytest.raises(RuntimeError, match="head"):
                tiny.capture_or_edit([1, 4], layers=[0, 1])
        assert list(tiny.model.model.layers[0]._forward_hooks) == [external.id]
    finally:
        external.remove()
    with pytest.raises(RuntimeError, match="Reentrant"):
        tiny.capture_or_edit([1, 4], {0: lambda h: tiny.capture_or_edit([1])}, [0])
    assert_clean_hooks(tiny)


@pytest.mark.parametrize("ids", [[], [True], [1.5], [-1], [32], [[1, 2]],
                                    torch.ones(2, 2, dtype=torch.long), torch.tensor([1.])])
def test_invalid_tokens_rejected(tiny, ids):
    with pytest.raises(ValueError):
        tiny.capture_or_edit(ids, layers=[0])
    assert_clean_hooks(tiny)


@pytest.mark.parametrize("kwargs", [
    {"position": -1}, {"position": 2}, {"position": True},
    {"layers": [0, 0]}, {"layers": [-1]}, {"layers": [3]}, {"layers": [True]},
    {"edits": {0: torch.zeros(16)}},
    {"edits": {0: lambda h: (h, {})}, "layers": [1]},
])
def test_invalid_plans_rejected(tiny, kwargs):
    with pytest.raises(ValueError):
        tiny.capture_or_edit([1, 4], **kwargs)
    assert_clean_hooks(tiny)


def test_context_no_truncation_tokenization_and_closed(tiny):
    assert tiny.tokenize_messages([{"role": "user", "content": "abc"}]).shape == (1, 4)
    with pytest.raises(ValueError, match="Context"):
        tiny.tokenize_messages([{"role": "user", "content": "a" * 32}])
    with pytest.raises(ValueError, match="Context"):
        tiny.capture_or_edit([1] * 33)
    with pytest.raises(ValueError, match="context"):
        tiny.generate([1] * 31, 0, 0., 2)
    with pytest.raises(ValueError, match="Context"):
        tiny.score_continuation([1] * 31, [2, 3])
    tiny.model.hf_device_map = {"model.layers.0": "disk"}
    with pytest.raises(RuntimeError, match="offload"):
        tiny.capture_or_edit([1])
    del tiny.model.hf_device_map
    tiny.close()
    tiny.close()
    with pytest.raises(RuntimeError, match="closed"):
        tiny.capture_or_edit([1])


@pytest.mark.parametrize("kwargs", [
    {"seed": True}, {"seed": -1}, {"seed": 2**63},
    {"temperature": float("nan")}, {"temperature": -1}, {"temperature": True},
    {"max_new_tokens": 0}, {"max_new_tokens": True},
])
def test_invalid_generation_parameters(tiny, kwargs):
    with pytest.raises(ValueError):
        tiny.generate([1, 4], **(dict(seed=0, max_new_tokens=3) | kwargs))


def test_loader_composition_retains_provenance(tiny):
    tiny._owner.metadata["model_revision"] = "synthetic-revision"
    with patch.object(b, "ModelBackend", return_value=tiny._owner) as loader:
        composed = b.Backend(cache_dir="/unused", device="cuda:0")
    loader.assert_called_once_with(precision="bf16", cache_dir="/unused", device="cuda:0")
    assert composed.metadata["loader_metadata"]["model_revision"] == "synthetic-revision"
    assert composed.metadata["test_only"]
    assert composed.metadata["unused_sae_loaded"]
    assert composed.metadata["dtype"] == str(tiny.dtype)
    assert composed.metadata["forward_mode"] == "full_prefix_no_cache"


def test_production_precision_rejected_before_loading():
    with patch.object(b, "ModelBackend") as loader:
        with pytest.raises(ValueError, match="native bf16"):
            b.Backend(cache_dir="/unused", precision="nf4")
    loader.assert_not_called()


def test_default_stage_a_layers_and_states_api(tiny):
    # A tiny actual 51-block Llama exercises the parent's default layer indices.
    transformers = pytest.importorskip("transformers")
    config = tiny.model.config.to_dict()
    config["num_hidden_layers"] = 51
    with torch.random.fork_rng():
        torch.manual_seed(0)
        model = transformers.LlamaForCausalLM(transformers.LlamaConfig(**config)).to(
            device=tiny.device, dtype=tiny.dtype)
    other = b.Backend.from_components_for_test(model, TinyTokenizer())
    try:
        result = other.capture_or_edit(other.tokenize_messages([{"role": "user", "content": "a"}]))
        assert set(result["states"]) == {40, 50}
        assert result["states"] is result["captures"]
        assert result["telemetry"]["hook_calls"] == {40: 1, 50: 1}
        assert result["telemetry"]["native_dtype"] == str(tiny.dtype)
        assert all(s["before"].dtype == torch.float32 for s in result["states"].values())
        assert_clean_hooks(other)
    finally:
        other.close()

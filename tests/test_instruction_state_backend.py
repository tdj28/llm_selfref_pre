"""Offline actual tiny-Llama checks, optionally on the designated cheap GPU."""
import json
import os
from types import SimpleNamespace
from unittest.mock import patch

import pytest
import torch

from experiments.instruction_state_qualification import backend as b
from experiments.instruction_state_qualification.raw_audit import validate_generation, validate_qualification


class TinyTokenizer:
    eos_token_id = 2
    chat_template = "test-only fixed-date serializer"
    all_special_ids = [0, 1, 2]

    def apply_chat_template(self, messages, **kwargs):
        assert kwargs["date_string"] == "26 Jul 2024"
        assert kwargs["add_generation_prompt"] is True
        rendered = "".join(m["role"] + ":" + m["content"] for m in messages) + "assistant:"
        if not kwargs["tokenize"]:
            return rendered
        assert kwargs["padding"] is False and kwargs["truncation"] is False
        return torch.tensor([[1] + [3 + ord(c) % 29 for c in rendered]], dtype=torch.long)

    def decode(self, ids, skip_special_tokens=True):
        return " ".join(str(i) for i in ids if not skip_special_tokens or i not in self.all_special_ids)


@pytest.fixture(params=[torch.float32, torch.bfloat16], ids=["fp32", "bf16"])
def tiny(request):
    transformers = pytest.importorskip("transformers")
    device = os.environ.get("INSTRUCTION_TEST_DEVICE", "cpu")
    assert device in ("cpu", "cuda"), "Explicit cpu or cuda test device required"
    if device == "cuda":
        assert torch.cuda.is_available() and torch.cuda.is_bf16_supported()
        initial = torch.cuda.memory_allocated()
        torch.cuda.reset_peak_memory_stats()
    threads = torch.get_num_threads()
    torch.set_num_threads(1)
    with torch.random.fork_rng():
        torch.manual_seed(20261001)
        config = transformers.LlamaConfig(vocab_size=32, hidden_size=16, intermediate_size=32,
            num_hidden_layers=3, num_attention_heads=2, num_key_value_heads=2,
            max_position_embeddings=2048, bos_token_id=1, eos_token_id=2,
            pad_token_id=0, attention_dropout=0.)
        config._attn_implementation = "sdpa"
        model = transformers.LlamaForCausalLM(config).to(device=device, dtype=request.param).eval()
    result = b.Backend.from_components_for_test(model, TinyTokenizer())
    try:
        yield result
    finally:
        if device == "cuda":
            torch.cuda.synchronize()
            peak = torch.cuda.max_memory_allocated() - initial
            assert peak < 512 * 1024**2, "Tiny qualification loaded unexpected GPU tensors"
        result.close()
        torch.set_num_threads(threads)


MESSAGES = [{"role": "user", "content": "Hello"}]


def test_private_seed_repeat_hashes_and_no_terminal_forward(tiny):
    before = torch.get_rng_state().clone()
    with patch.object(tiny.model.model, "forward", wraps=tiny.model.model.forward) as forward:
        first = tiny.generate(MESSAGES, 5, .5, 8)
    assert forward.call_count == first["output_tokens"]
    assert forward.call_args_list[0].kwargs["input_ids"].shape[1] == first["input_tokens"]
    assert all(call.kwargs["input_ids"].shape[1] == 1 for call in forward.call_args_list[1:])
    assert torch.equal(before, torch.get_rng_state())
    torch.rand(7)
    second = tiny.generate(MESSAGES, 5, .5, 8)
    assert first["output_token_ids"] == second["output_token_ids"]
    assert first["provenance"]["test_only"] is True
    assert tiny.metadata["sae_loaded"] is False and not hasattr(tiny, "_sae")
    assert first["messages"] == MESSAGES
    assert validate_generation(first, messages=MESSAGES, seed=5, cap=8, allow_test=True)
    with pytest.raises(ValueError, match="Test-only"):
        validate_generation(first, messages=MESSAGES, seed=5, cap=8)
    json.dumps(first, allow_nan=False)
    assert "logits" not in first and "weights" not in first


def test_eos_early_stop_includes_id_without_extra_forward(tiny):
    with patch("torch.multinomial", return_value=torch.tensor([[2]], device=tiny.device)):
        with patch.object(tiny.model.model, "forward", wraps=tiny.model.model.forward) as forward:
            value = tiny.generate(MESSAGES, 8, .5, 8)
    assert forward.call_count == 1
    assert value["output_token_ids"] == [2] and value["response"] == ""
    assert value["eos_reached"] and not value["cap_hit"]
    assert value["stop_reason"] == "eos"


def test_cap_includes_final_token_without_extra_forward(tiny):
    with patch("torch.multinomial", return_value=torch.tensor([[4]], device=tiny.device)):
        with patch.object(tiny.model.model, "forward", wraps=tiny.model.model.forward) as forward:
            value = tiny.generate(MESSAGES, 8, .5, 3)
    assert forward.call_count == 3 and value["output_token_ids"] == [4, 4, 4]
    assert value["cap_hit"] and not value["eos_reached"]


def test_cached_sample_matches_manual_old_sampling_schedule(tiny):
    actual = tiny.generate(MESSAGES, 81, .5, 6)
    with torch.inference_mode():
        _, prompt = tiny.serialize(MESSAGES)
        logits, past = tiny._forward(prompt)
        generator = torch.Generator(device=tiny.device).manual_seed(81)
        tokens = []
        for index in range(6):
            token = torch.multinomial(torch.softmax(logits / .5, dim=-1), 1, generator=generator).item()
            tokens.append(token)
            # The old schedule included this diagnostically unnecessary terminal forward.
            logits, past = tiny._forward(torch.tensor([[token]], device=tiny.device),
                                         past, prompt.shape[1] + index)
            if token == 2:
                break
    assert actual["output_token_ids"] == tokens


def test_actual_model_live_qualification_and_hook_cleanup(tiny):
    result = tiny.qualify()
    assert result["pass"] and result["repeat_seed_equal"]
    assert result["zero_logits_bit_exact"] and result["cache_reference_pass"]
    assert result["test_only"] is True
    assert all(not layer._forward_hooks for layer in tiny.model.model.layers)
    validate_qualification(result, allow_test=True)


def test_token_binding_checks_exact_tokens_render_and_metadata(tiny):
    rendered, ids = tiny.serialize(MESSAGES)
    binding = {"model_id": b.MODEL_ID, "revision": b.MODEL_REVISION,
        "tokenizer_files": {}, "cases": {"fixture": {"messages": MESSAGES,
        "input_token_ids": ids[0].tolist(), "rendered_input_sha256": b.text_sha(rendered)}}}
    assert tiny.verify_token_bindings(binding)["pass"]
    binding["cases"]["fixture"]["input_token_ids"][-1] ^= 1
    with pytest.raises(ValueError, match="serialization"):
        tiny.verify_token_bindings(binding)
    binding["tokenizer_files"] = {"tokenizer.json": {"sha256": "0" * 64, "size_bytes": 1}}
    with pytest.raises(ValueError, match="tokenizer file"):
        tiny.verify_token_bindings(binding)


@pytest.mark.parametrize("kwargs", [{"temperature": .6}, {"temperature": 0},
    {"max_new_tokens": 769}, {"max_new_tokens": True}, {"top_p": .9}, {"seed": True}])
def test_rejects_nonfrozen_sampling(tiny, kwargs):
    args = {"messages": MESSAGES, "seed": 1, "temperature": .5, "max_new_tokens": 4}
    args.update(kwargs)
    with pytest.raises(ValueError):
        tiny.generate(**args)


def test_no_offload_context_truncation_or_nonfinite_fallback(tiny):
    old = tiny.model.config.max_position_embeddings
    tiny.model.config.max_position_embeddings = 5
    with pytest.raises(ValueError, match="Context limit"):
        tiny.generate(MESSAGES, 1, .5, 4)
    tiny.model.config.max_position_embeddings = old
    tiny.model.hf_device_map = {"": "disk"}
    with pytest.raises(RuntimeError, match="Offload"):
        tiny.generate(MESSAGES, 1, .5, 4)
    del tiny.model.hf_device_map
    with torch.no_grad():
        tiny.model.lm_head.weight.fill_(float("nan"))
    with pytest.raises(FloatingPointError):
        tiny.generate(MESSAGES, 1, .5, 4)


def test_production_rejects_cpu_before_artifact_access():
    with patch.object(b, "load_model_artifacts") as loader:
        with pytest.raises(RuntimeError, match="B200"):
            b.Backend(cache_dir="unused", device="cpu")
    loader.assert_not_called()


def test_deadline_callback_runs_before_each_neutral_generation(tiny):
    calls = []
    tiny.before_generation = lambda: calls.append(True)
    tiny.qualify()
    assert len(calls) == 3
    tiny.before_generation = lambda: (_ for _ in ()).throw(TimeoutError("reserve"))
    with patch.object(tiny.model.model, "forward", wraps=tiny.model.model.forward) as forward:
        with pytest.raises(TimeoutError, match="reserve"):
            tiny.generate(MESSAGES, 1, .5, 4)
    forward.assert_not_called()


def test_loader_inventory_hashes_model_only(tmp_path, monkeypatch):
    files = {"config.json": b"{}", "generation_config.json": b"{}",
        "tokenizer.json": b"{}", "tokenizer_config.json": b"{}",
        "model.safetensors.index.json": b'{"weight_map":{"p":"model-00001.safetensors"}}',
        "model-00001.safetensors": b"synthetic model shard"}
    siblings = []
    for name, value in files.items():
        (tmp_path / name).write_bytes(value)
        siblings.append(SimpleNamespace(rfilename=name, lfs=None,
            blob_id=__import__("hashlib").sha1(f"blob {len(value)}\0".encode() + value).hexdigest()))
    info = SimpleNamespace(sha=b.MODEL_REVISION, siblings=siblings)
    import huggingface_hub
    with patch.object(huggingface_hub.HfApi, "model_info", return_value=info) as metadata:
        with patch.object(huggingface_hub, "snapshot_download", return_value=str(tmp_path)) as download:
            with patch.object(huggingface_hub, "hf_hub_download", side_effect=AssertionError("No SAE download")):
                snapshot, receipt = b.load_model_artifacts(tmp_path)
    assert snapshot == tmp_path and set(receipt["model_artifacts"]) == set(files)
    assert metadata.call_args.args == (b.MODEL_ID,)
    assert download.call_args.args == (b.MODEL_ID,)
    assert set(download.call_args.kwargs["allow_patterns"]) == set(files)
    (tmp_path / "tokenizer.json").write_text("corrupted")
    with patch.object(huggingface_hub.HfApi, "model_info", return_value=info):
        with patch.object(huggingface_hub, "snapshot_download", return_value=str(tmp_path)):
            with pytest.raises(RuntimeError, match="hash mismatch"):
                b.load_model_artifacts(tmp_path)

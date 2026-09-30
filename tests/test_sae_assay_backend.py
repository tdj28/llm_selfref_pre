"""Offline numerical and real tiny-Llama tests; no pretrained downloads or API calls."""

import hashlib
import json
from pathlib import Path
from unittest.mock import patch

import pytest

torch = pytest.importorskip("torch")
import torch.nn.functional as F

from experiments.sae_assay_diagnostic import backend as b


def selected(dtype=torch.float32):
    return (torch.eye(2, dtype=dtype), torch.tensor([.5, .25], dtype=dtype),
            torch.tensor([[1., .25], [.5, 1.]], dtype=dtype))


def test_zero_is_object_identity_and_no_reconstruction():
    h = torch.tensor([[1., 2.], [-1., -2.]], dtype=torch.bfloat16)
    edited, t = b.edit_hidden(h, *selected(h.dtype))
    assert edited is h
    assert torch.equal(t["before"], t["after"])
    assert t["identity"].all() and not t["nonzero_requested"].any()
    assert t["cosine"].tolist() == [1, 1]
    assert t["relative_error"].tolist() == [0, 0]


@pytest.mark.parametrize("dtype", [torch.float32, torch.bfloat16])
@pytest.mark.parametrize("strength", [.5, 1.])
def test_exact_bias_delta_and_reencoding(dtype, strength):
    h = torch.tensor([[1., 2.], [-1., -2.]], dtype=dtype)
    e, bias, d = selected(dtype)
    edited, t = b.edit_hidden(h, e, bias, d, mode="suppression", strength=strength)
    z = F.relu(F.linear(h, e, bias))
    delta = -strength * z.float()
    expected = (h.float() + F.linear(delta, d.float())).to(dtype)
    assert torch.equal(edited, expected)
    assert torch.equal(t["requested_delta"], delta)
    assert torch.equal(t["after"], F.relu(F.linear(expected, e, bias)).float())
    assert torch.equal(t["before"], torch.tensor([[1.5, 2.25], [0., 0.]]))
    assert torch.equal(h, torch.tensor([[1., 2.], [-1., -2.]], dtype=dtype))


def test_amplification_clipping_mask_and_cross_feature_delivery():
    h = torch.tensor([[1., 2.], [1., 2.]])
    edited, t = b.edit_hidden(h, *selected(), mode="amplification", strength=.5,
                              q90=[2.5, 1.], valid_mask=torch.tensor([True, False]))
    assert t["requested_delta"].tolist() == [[.5, 0.], [0., 0.]]
    assert t["requested_activation"][0].tolist() == [2., 2.25]
    assert t["after"][0].tolist() == [2., 2.5]  # Decoder cross-talk is measured.
    assert torch.equal(edited[1], h[1])


def test_rounding_loss_is_failure_not_missing_and_one_final_cast():
    h = torch.tensor([[1024., 1024.]], dtype=torch.bfloat16)
    e = torch.zeros((1, 2), dtype=h.dtype)
    bias = torch.ones(1, dtype=h.dtype)
    d = torch.tensor([[.01], [.01]], dtype=h.dtype)
    edited, t = b.edit_hidden(h, e, bias, d, mode="suppression", strength=1.)
    assert torch.equal(edited, h)
    assert t["requested_norm"].item() > 0
    assert t["realized_norm"].item() == 0
    assert t["cosine"].item() == 0
    assert t["relative_error"].item() == 1
    assert t["nonzero_requested"].item()


@pytest.mark.parametrize("kwargs", [
    {"mode": "suppression", "strength": .7},
    {"mode": "suppression", "strength": float("nan")},
    {"mode": "amplification", "strength": .5},
    {"mode": "amplification", "strength": .5, "q90": [1.]},
    {"mode": "amplification", "strength": .5, "q90": [-1., 1.]},
    {"mode": "other", "strength": .5},
])
def test_bad_interventions_rejected(kwargs):
    with pytest.raises(ValueError):
        b.edit_hidden(torch.ones(1, 2), *selected(), **kwargs)


def test_nonfinite_rejected():
    with pytest.raises(FloatingPointError):
        b.edit_hidden(torch.tensor([[float("nan"), 1.]]), *selected())
    with pytest.raises(FloatingPointError):
        b.edit_hidden(torch.ones(1, 2), *selected(), mode="amplification", strength=1,
                      q90=[float("inf"), 1])


@pytest.mark.parametrize("dtype", [torch.float32, torch.bfloat16])
def test_selected_vs_full_old_linear_relu_on_fixed_fixture(dtype):
    """Prelaunch fixture check, not an assertion about unseen GPU kernels."""
    h = torch.arange(28, dtype=torch.float32).reshape(7, 4).div(16).sub(.5).to(dtype)
    e = torch.arange(68, dtype=torch.float32).reshape(17, 4).remainder(11).sub(5).div(8).to(dtype)
    bias = torch.arange(17, dtype=torch.float32).sub(8).div(16).to(dtype)
    full_encoder = torch.nn.Linear(4, 17, dtype=dtype)
    with torch.no_grad():
        full_encoder.weight.copy_(e)
        full_encoder.bias.copy_(bias)
    ids = [0, 3, 9, 16]
    _, t = b.edit_hidden(h, e[ids], bias[ids], e[ids].T.contiguous())
    expected = F.relu(full_encoder(h))[:, ids].float()
    drift = (expected - t["before"]).abs().max().item()
    assert b.SELECTED_FULL_MAX_ABS_TOLERANCE == .02
    assert drift <= b.SELECTED_FULL_MAX_ABS_TOLERANCE
    torch.testing.assert_close(expected, t["before"], atol=.02, rtol=0)


def test_hash_binding_rejects_corruption(tmp_path):
    path = tmp_path / "artifact"
    payload = b"offline fixture"
    path.write_bytes(payload)
    sha = hashlib.sha256(payload).hexdigest()
    git = hashlib.sha1(f"blob {len(payload)}\0".encode() + payload).hexdigest()
    assert b._hash_file(path, sha, "sha256") == sha
    assert b._hash_file(path, git, "git_sha1") == sha
    with pytest.raises(RuntimeError, match="hash mismatch"):
        b._hash_file(path, "0" * 64, "sha256")


class TinyTokenizer:
    all_special_ids = [0, 1, 2, 3]
    eos_token_id = 2
    chat_template = "offline fixed fixture"

    def __call__(self, text, **kwargs):
        ids = [1] + [4 + ord(c) % 24 for c in text]
        return {"input_ids": torch.tensor([ids]), "attention_mask": torch.ones(1, len(ids))}

    def apply_chat_template(self, messages, *, tokenize, **kwargs):
        text = "".join(m["content"] for m in messages)
        return self(text)["input_ids"] if tokenize else text

    def decode(self, ids, skip_special_tokens=True):
        return " ".join(str(i) for i in ids if not skip_special_tokens or i not in self.all_special_ids)


@pytest.fixture(params=[torch.float32, torch.bfloat16], ids=["fp32", "bf16"])
def tiny(request):
    transformers = pytest.importorskip("transformers")
    with torch.random.fork_rng():
        torch.manual_seed(1823)
        config = transformers.LlamaConfig(vocab_size=32, hidden_size=16,
            intermediate_size=32, num_hidden_layers=2, num_attention_heads=2,
            num_key_value_heads=2, max_position_embeddings=128,
            bos_token_id=1, eos_token_id=2, pad_token_id=0, attention_dropout=0.)
        config._attn_implementation = "sdpa"
        model = transformers.LlamaForCausalLM(config).to(request.param).eval()
        state = {"encoder_linear.weight": torch.randn(8, 16) * .2,
                 "encoder_linear.bias": torch.ones(8) * .2,
                 "decoder_linear.weight": torch.randn(16, 8) * .04,
                 "decoder_linear.bias": torch.ones(16) * .01}
        state = {k: v.to(request.param) for k, v in state.items()}
    obj = b.ModelBackend.from_components_for_test(model, TinyTokenizer(), state,
                                                  default_feature_ids=[0, 3])
    yield obj
    obj.close()


def test_teacher_schema_losses_and_zero_exactness(tiny):
    result = tiny.teacher("abcdef", list(range(8)))
    t = result["telemetry"]
    assert t["schema_version"] == "sae_assay_backend_v1"
    assert t["feature_ids"] == list(range(8))
    assert len(t["position_metadata"]) == 7
    assert len(t["selected_activations"]["before"]) == 7
    assert len(t["selected_activations"]["before"][0]) == 8
    assert t["selected_activations"]["before"] == t["selected_activations"]["after"]
    assert result["unsteered_nll"] == result["edited_nll"]
    assert result["kl_clean_to_edited"] == [None] + [0.] * 6
    assert t["position_metadata"][0]["token_class"] == "special"
    assert result["activation_summaries"][0]["before"]["count"] == 7
    tokens = torch.tensor([result["token_ids"]])
    with torch.inference_mode():
        plain = tiny.model(tokens, use_cache=False).logits[:, :-1].float()
        expected = F.cross_entropy(plain[0], tokens[0, 1:], reduction="none")
    torch.testing.assert_close(torch.tensor(result["unsteered_nll"][1:]), expected)
    assert len(tiny._layer._forward_hooks) == 0
    json.dumps(result, allow_nan=False)


def test_intervened_teacher_reconstruction_and_metadata(tiny):
    arm = {"feature_ids": [0, 3], "mode": "suppression", "strength": 1.}
    result = tiny.teacher("abcde", [0, 3], arm, collect_reconstruction=True)
    t = result["telemetry"]
    assert any(t["delivery"]["nonzero_requested"])
    assert result["unsteered_nll"] != result["edited_nll"]
    assert result["reconstruction_nll"] != result["unsteered_nll"]
    assert result["kl_clean_to_edited"][0] is None
    assert min(result["kl_clean_to_edited"][1:]) >= -1e-6
    assert t["selected_full_check_passed"] is True
    assert "non_target_change_norm" in t["full_sae"]
    assert len(t["full_sae"]["l0_before"]) == len(result["token_ids"])
    assert t["selected_encode_shapes"] == [[6, 2, 16]]
    assert t["full_encode_shape"] == [6, 8, 16]
    metadata = tiny.feature_metadata(list(range(8)), [0, 3])
    assert metadata["features"][0]["decoder_norm"] > 0
    assert metadata["features"][0]["target_cosines"][0] == pytest.approx(1, abs=1e-6)
    json.dumps(result, allow_nan=False)


def test_full_encoder_drift_has_fixed_gate_without_switching(tiny):
    original = tiny._full_diagnostic

    def drift(*args):
        reconstructed, diagnostic = original(*args)
        diagnostic["full_selected_before"] += .1
        return reconstructed, diagnostic

    with patch.object(tiny, "_full_diagnostic", side_effect=drift):
        result = tiny.teacher("abc", [0, 3], collect_reconstruction=True)
    assert result["telemetry"]["selected_full_check_passed"] is False
    assert result["unsteered_nll"] == result["edited_nll"]


def test_cached_hook_matches_full_prefix_under_intervention(tiny):
    tokens = tiny._tokenize("abcde")
    arm = {"feature_ids": [0, 3], "mode": "amplification", "strength": .5, "q90": [.4, .3]}
    full, full_t = tiny._forward(tokens, [0, 3], arm)
    past, parts, records = None, [], []
    for i in range(tokens.shape[1]):
        step, telemetry = tiny._forward(tokens[:, i:i+1], [0, 3], arm,
                                        offset=i, past=past, use_cache=True)
        past = step.past_key_values
        parts.append(step.last_hidden_state)
        records.extend(telemetry["selected_activations"]["before"])
    tolerance = .02 if tiny.dtype == torch.bfloat16 else 1e-6
    torch.testing.assert_close(torch.cat(parts, dim=1), full.last_hidden_state, atol=tolerance, rtol=0)
    torch.testing.assert_close(torch.tensor(records),
        torch.tensor(full_t["selected_activations"]["before"]), atol=tolerance, rtol=0)
    assert len(tiny._layer._forward_hooks) == 0


def test_generation_pairing_rng_isolation_cap_and_complete_positions(tiny):
    tiny.model.generation_config.eos_token_id = None
    tiny.tokenizer.eos_token_id = None
    args = dict(messages=[{"role": "user", "content": "abc"}], seed=93,
                temperature=.6, max_new_tokens=4)
    rng = torch.get_rng_state().clone()
    first = tiny.generate(**args)
    second = tiny.generate(**args)
    assert torch.equal(rng, torch.get_rng_state())
    assert first["output_token_ids"] == second["output_token_ids"]
    assert first["telemetry"] == second["telemetry"]
    assert first["output_tokens"] == 4 and first["cap_hit"]
    t = first["telemetry"]
    assert [p["position"] for p in t["position_metadata"]] == list(range(8))
    assert [p["origin"] for p in t["position_metadata"]] == ["prompt"] * 4 + ["generated"] * 4
    assert t["position_metadata"][-1]["terminal_observation_only"]
    assert all(t["delivery"]["identity"])
    assert t["selected_encode_shapes"] == [[4, 2, 16]] + [[1, 2, 16]] * 4
    assert len(tiny._layer._forward_hooks) == 0


def test_eos_is_not_cap_and_zero_intervention_matches_unhooked(tiny):
    with torch.no_grad():
        tiny.model.lm_head.weight.zero_()  # Greedy token 0, deterministic EOS.
    tiny.model.generation_config.eos_token_id = [0]
    result = tiny.generate([{"role": "user", "content": "a"}], 1, 0., max_new_tokens=1)
    assert result["output_token_ids"] == [0]
    assert not result["cap_hit"]
    assert result["telemetry"]["position_metadata"][-1]["token_class"] == "special"


def test_hook_removal_on_exception_and_refuse_offload(tiny):
    with patch.object(b, "edit_hidden", side_effect=FloatingPointError("fixture")):
        with pytest.raises(FloatingPointError):
            tiny.teacher("abc", [0, 3])
    assert len(tiny._layer._forward_hooks) == 0
    tiny.model.hf_device_map = {"model.layers.0": "disk"}
    with pytest.raises(RuntimeError, match="offload"):
        tiny.teacher("abc", [0, 3])
    del tiny.model.hf_device_map


def test_validation_and_closed_backend(tiny):
    arm = {"feature_ids": [3, 0], "mode": "suppression", "strength": 1.}
    with pytest.raises(ValueError, match="ordered"):
        tiny.teacher("abc", [0, 3], arm)
    with pytest.raises(ValueError, match="Duplicate"):
        tiny.teacher("abc", [0, 0])
    with pytest.raises(ValueError, match="Context"):
        tiny.teacher("a" * 129, [0])
    with pytest.raises(ValueError):
        tiny.generate([], 0, .5, max_new_tokens=257)
    tiny.close()
    tiny.close()
    with pytest.raises(RuntimeError, match="closed"):
        tiny.teacher("abc", [0])


def test_production_requires_cuda_before_artifact_download():
    with patch.object(b, "_load_artifacts") as loader:
        with pytest.raises(RuntimeError, match="CUDA"):
            b.ModelBackend(cache_dir="/unused", device="cpu")
        loader.assert_not_called()

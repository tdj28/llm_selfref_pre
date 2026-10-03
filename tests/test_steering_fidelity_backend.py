"""Standalone native-BF16 tiny-Llama checks; no downloads, APIs or old fixtures.

BERG_TEST_DEVICE=cuda (or cuda:N) selects the actual CUDA rung. Missing CUDA
or native BF16 support is a failure, never an importorskip or CPU fallback.
"""
import hashlib
import json
import math
import os
from unittest.mock import Mock, patch

import pytest
import torch
import torch.nn.functional as F
from transformers import LlamaConfig, LlamaForCausalLM

from experiments.berg_source_replication import backend as source
from experiments.sae_assay_diagnostic import backend as model_backend
from experiments.steering_fidelity import backend as b


MESSAGES = [{"role": "user", "content": "Is two plus two four?"}]
ARM = {"feature_ids": [0, 3], "weights": [1., 2.], "sign": 1, "requested_norm": .02}
CHOICES = {"yes": [8, 9], "no": [14, 15]}


class TinyTokenizer:
    all_special_ids = [0, 1, 2, 3]
    eos_token_id = 2
    chat_template = "test chat with two special suffix tokens"

    def __init__(self):
        variants = b.YES_VARIANTS + b.NO_VARIANTS
        self.encodings = {text: [8 + i] for i, text in enumerate(variants)}
        self.prompt_override = None

    def encode(self, text, *, add_special_tokens):
        assert add_special_tokens is False
        return self.encodings[text]

    def apply_chat_template(self, messages, *, tokenize, add_generation_prompt, **kwargs):
        assert add_generation_prompt is True
        rendered = "<bos>" + json.dumps(messages, sort_keys=True) + "<eot><assistant>"
        if not tokenize:
            return rendered
        assert kwargs == {"return_tensors": "pt"}
        ids = self.prompt_override
        if ids is None:
            ids = [1] + [4 + ord(c) % 4 for m in messages for c in m["content"]] + [2, 3]
        return torch.tensor([ids], dtype=torch.long)

    def decode(self, ids, skip_special_tokens=True):
        words = {v[0]: k for k, v in self.encodings.items() if len(v) == 1}
        return "".join(words.get(i, f"<{i}>") for i in ids
                       if not skip_special_tokens or i not in self.all_special_ids)


@pytest.fixture
def tiny():
    device = torch.device(os.environ.get("BERG_TEST_DEVICE", "cpu"))
    assert device.type in ("cpu", "cuda"), "Only CPU or CUDA test rungs are supported"
    if device.type == "cuda":
        assert torch.cuda.is_available(), "Requested CUDA rung must not skip or fall back"
        with torch.cuda.device(device):
            assert torch.cuda.is_bf16_supported(), "CUDA rung requires native BF16"
    threads = torch.get_num_threads()
    torch.set_num_threads(1)
    instance = None
    try:
        with torch.random.fork_rng():
            torch.manual_seed(81)
            config = LlamaConfig(vocab_size=32, hidden_size=16, intermediate_size=32,
                num_hidden_layers=2, num_attention_heads=2, num_key_value_heads=2,
                max_position_embeddings=256, bos_token_id=1, eos_token_id=2,
                pad_token_id=0, attention_dropout=0.)
            config._attn_implementation = "sdpa"
            model = LlamaForCausalLM(config).to(device=device, dtype=torch.bfloat16).eval()
            state = {"encoder_linear.weight": torch.randn(12, 16) * .2,
                     "encoder_linear.bias": torch.linspace(-.3, .3, 12),
                     "decoder_linear.weight": torch.randn(16, 12) * .04,
                     "decoder_linear.bias": torch.zeros(16)}
        instance = b.Backend.from_components_for_test(
            model, TinyTokenizer(), state, default_feature_ids=[0, 1, 3, 5, 7, 11])
        assert instance.dtype == torch.bfloat16
        assert all(w.dtype == torch.bfloat16 and w.device == instance.device for w in instance._sae)
        yield instance
    finally:
        if instance is not None:
            assert all(not layer._forward_hooks for layer in instance.model.model.layers)
            instance.close()
        torch.set_num_threads(threads)


def test_loader_is_inherited_pinned_native_only():
    assert issubclass(b.Backend, source.Backend)
    assert b.Backend.qualify is source.Backend.qualify
    with patch.object(model_backend.ModelBackend, "__init__", return_value=None) as init:
        b.Backend(cache_dir="test-cache", device="cuda:1")
        init.assert_called_once_with(precision="bf16", cache_dir="test-cache", device="cuda:1")
    with patch.object(model_backend.ModelBackend, "__init__") as init:
        with pytest.raises(ValueError, match="native BF16"):
            b.Backend(precision="nf4", cache_dir="unused")
        init.assert_not_called()
    with patch.object(model_backend, "_load_artifacts") as load:
        with pytest.raises(RuntimeError, match="CUDA"):
            b.Backend(cache_dir="unused", device="cpu")
        load.assert_not_called()


@pytest.mark.parametrize("sign", [-1, 1])
@pytest.mark.parametrize("norm", [None, .2])
def test_weighted_vector_exact_fp32_formula(tiny, sign, norm):
    spec = dict(ARM, sign=sign, requested_norm=norm)
    columns = tiny._sae[2][:, [0, 3]].float()
    expected = (columns * torch.tensor([1., 2.], device=tiny.device)).sum(1)
    if norm is not None:
        expected = expected / expected.norm() * norm
    expected *= sign
    actual = tiny.vector(spec)
    assert actual.dtype == torch.float32 and torch.equal(actual, expected)
    if norm is not None:
        assert actual.norm().item() == pytest.approx(norm)


@pytest.mark.parametrize("change", [
    {"feature_ids": []}, {"feature_ids": [0, 0]}, {"feature_ids": [0, 12]},
    {"feature_ids": [0, True]}, {"feature_ids": (0, 3)}, {"weights": [1.]},
    {"weights": [1., 0.]}, {"weights": [1., -1.]}, {"weights": [1., True]},
    {"weights": [1., float("nan")]}, {"weights": [1., float("inf")]},
    {"weights": [1., 1e100]}, {"weights": [1., 1e-100]}, {"weights": (1., 2.)},
    {"sign": True}, {"sign": 0}, {"sign": 1.}, {"requested_norm": 0.},
    {"requested_norm": -1.}, {"requested_norm": True},
    {"requested_norm": float("inf")}, {"requested_norm": float("nan")},
    {"requested_norm": 1e-100}, {"requested_norm": 1e100}, {"unexpected": 1},
])
def test_invalid_intervention_rejected(tiny, change):
    with pytest.raises((ValueError, FloatingPointError)):
        tiny.vector(dict(ARM, **change))


@pytest.mark.parametrize("coefficient", [.1, -.1, True, float("nan"), float("inf")])
def test_only_exact_legacy_zero(tiny, coefficient):
    with pytest.raises(ValueError, match="legacy"):
        tiny.vector({"feature_ids": [0, 3], "coefficient": coefficient})


def test_zero_qualification_and_generation_reuse(tiny):
    result = tiny.qualify()
    assert result["pass"] and result["zero_hidden_bit_exact"] and result["zero_output_equal"]
    none = tiny.score(MESSAGES, True)
    zero = tiny.score(MESSAGES, True, {"feature_ids": [0, 3], "coefficient": 0.})
    assert {k: v for k, v in none.items() if k != "elapsed_seconds"} == {
        k: v for k, v in zero.items() if k != "elapsed_seconds"}
    assert none["delivery"]["n_nonzero_requested"] == 0
    assert none["delivery"]["n_zero_requested"] == none["delivery"]["n_positions"]
    assert all(v is None for v in none["delivery"]["metrics"].values())
    assert tiny.vector(None).eq(0).all()
    generated = tiny.generate([{"role": "user", "content": "Return JSON: {\"ok\":true}"}],
                              81, 0., 2, ARM)
    assert generated["telemetry"]["intervention"] == ARM
    assert generated["telemetry"]["feature_ids"] == ARM["feature_ids"]
    json.dumps(generated, allow_nan=False)


def test_zero_direction_cannot_be_normalized(tiny):
    tiny._sae[2][:, 3] = -tiny._sae[2][:, 0]
    spec = dict(ARM, weights=[1., 1.])
    with pytest.raises(ValueError, match="zero"):
        tiny.vector(spec)
    assert tiny.vector(dict(spec, requested_norm=None)).eq(0).all()


def test_feature_norms_full_and_ordered(tiny):
    expected = tiny._sae[2].float().norm(dim=0).cpu().tolist()
    assert tiny.feature_norms() == expected
    assert tiny.feature_norms([11, 0, 3]) == [expected[i] for i in (11, 0, 3)]
    with pytest.raises(ValueError):
        tiny.feature_norms([0, 0])


def test_decoder_gram_matches_native_columns_explicit_dots(tiny):
    ids = [3, 0, 11, 5, 1, 7]
    columns = tiny._sae[2][:, ids].float()
    expected = [[torch.dot(columns[:, i], columns[:, j]).item()
                 for j in range(len(ids))] for i in range(len(ids))]
    with torch.autocast(device_type=tiny.device.type, dtype=torch.float16):
        gram = tiny.decoder_gram(ids)
    assert isinstance(gram, list) and all(isinstance(row, list) for row in gram)
    assert len(gram) == 6 and all(len(row) == 6 for row in gram)
    torch.testing.assert_close(torch.tensor(gram), torch.tensor(expected), rtol=1e-6, atol=1e-8)
    assert gram == tiny.decoder_gram(ids)
    for i, norm in enumerate(tiny.feature_norms(ids)):
        assert math.sqrt(gram[i][i]) == pytest.approx(norm, rel=1e-6, abs=1e-8)
    json.dumps(gram, allow_nan=False)


@pytest.mark.parametrize("sign", [-1, 1])
def test_decoder_gram_independently_reconstructs_raw_weighted_norm(tiny, sign):
    ids, weights = [3, 0, 11, 5, 1, 7], [.4, .55, .48, .42, .6, .51]
    gram = tiny.decoder_gram(ids)
    reconstructed = math.sqrt(math.fsum(
        weights[i] * gram[i][j] * weights[j] for i in range(6) for j in range(6)))
    spec = {"feature_ids": ids, "weights": weights, "sign": sign, "requested_norm": None}
    assert abs(reconstructed - tiny.vector(spec).norm().item()) <= 1e-5


@pytest.mark.parametrize("ids", [[], [0, 0], [12], [True], [0, -1]])
def test_decoder_gram_rejects_invalid_ids(tiny, ids):
    with pytest.raises(ValueError):
        tiny.decoder_gram(ids)


def test_score_one_full_prefill_one_native_final_head_no_generation(tiny):
    rng = torch.get_rng_state().clone()
    head = tiny.model.get_output_embeddings()
    with patch.object(tiny.model.model, "forward", wraps=tiny.model.model.forward) as forward, \
         patch.object(head, "forward", wraps=head.forward) as head_forward, \
         patch.object(tiny, "generate", side_effect=AssertionError("No generation")), \
         patch.object(torch, "multinomial", side_effect=AssertionError("No sampling")):
        result = tiny.score(MESSAGES, True)
    assert torch.equal(rng, torch.get_rng_state())
    assert forward.call_count == head_forward.call_count == 1
    assert forward.call_args.kwargs["use_cache"] is False
    assert forward.call_args.kwargs["input_ids"].shape == (1, len(result["input_token_ids"]))
    assert head_forward.call_args.args[0].shape == (1, 16)
    assert head_forward.call_args.args[0].dtype == torch.bfloat16
    assert "response" not in result and "output_token_ids" not in result
    assert result["elapsed_seconds"] >= 0
    assert result["screen"] is None
    with torch.inference_mode():
        tokens = torch.tensor([result["input_token_ids"]], device=tiny.device)
        hidden = tiny.model.model(input_ids=tokens, attention_mask=torch.ones_like(tokens),
                                  use_cache=False, return_dict=True).last_hidden_state
        logits = head(hidden[:, -1])[0].float()
        probabilities = logits.double().softmax(-1)
    assert result["p_yes"] == probabilities[result["token_sets"]["yes"]].sum().item()
    assert result["p_no"] == probabilities[result["token_sets"]["no"]].sum().item()
    assert result["p_correct"] == result["p_yes"] / result["valid_mass"]
    assert result["top_token_id"] == logits.argmax().item()
    rendered = tiny.tokenizer.apply_chat_template(MESSAGES, tokenize=False, add_generation_prompt=True)
    assert result["rendered_input_sha256"] == hashlib.sha256(rendered.encode()).hexdigest()
    assert result["input_token_ids_sha256"] == hashlib.sha256(
        json.dumps(result["input_token_ids"]).encode()).hexdigest()
    json.dumps(result, allow_nan=False)


def test_variants_all_required_deduplicated_and_cached(tiny):
    tiny.tokenizer.encodings[" yes"] = tiny.tokenizer.encodings["Yes"]
    with patch.object(tiny.tokenizer, "encode", wraps=tiny.tokenizer.encode) as encode:
        first = tiny.score(MESSAGES, True)
        second = tiny.score(MESSAGES, False)
    assert [call.args[0] for call in encode.call_args_list] == list(b.YES_VARIANTS + b.NO_VARIANTS)
    assert len(first["token_sets"]["yes"]) == 5
    assert second["token_sets"] == first["token_sets"]
    assert second["p_correct"] == pytest.approx(1 - first["p_correct"])


@pytest.mark.parametrize("variant", b.YES_VARIANTS + b.NO_VARIANTS)
@pytest.mark.parametrize("bad_ids", [[], [8, 9]])
def test_no_variant_silently_dropped(tiny, variant, bad_ids):
    tiny.tokenizer.encodings[variant] = bad_ids
    with pytest.raises(ValueError, match="exactly one"):
        tiny.score(MESSAGES, True)


@pytest.mark.parametrize("sets", [
    {"yes": [8], "no": [8]}, {"yes": [], "no": [14]},
    {"yes": [8, 8], "no": [14]}, {"yes": [True], "no": [14]},
    {"yes": [32], "no": [14]}, {"yes": [1], "no": [14]},
    {"yes": [8]}, {"yes": "8", "no": [14]},
])
def test_explicit_token_sets_are_checked(tiny, sets):
    with pytest.raises(ValueError):
        tiny.score(MESSAGES, True, token_sets=sets)


def test_derived_overlap_special_and_test_override_boundary(tiny):
    tiny.tokenizer.encodings["No"] = [8]
    with pytest.raises(ValueError, match="overlap"):
        tiny.score(MESSAGES, True)
    tiny.tokenizer.encodings["No"] = [1]
    with pytest.raises(ValueError, match="special"):
        tiny.score(MESSAGES, True)
    assert tiny.score(MESSAGES, True, token_sets=CHOICES)["token_sets"] == CHOICES
    tiny.metadata["test_only"] = False
    with pytest.raises(ValueError, match="test-only"):
        tiny.score(MESSAGES, True, token_sets=CHOICES)


def test_group_mass_argmax_not_top_token_and_invalid_format_keeps_primary(tiny):
    logits = torch.full((1, 32), -20., device=tiny.device)
    logits[0, [8, 9, 14, 20]] = torch.tensor([1., 1., 1.5, 3.], device=tiny.device)
    with patch.object(tiny.model.lm_head, "forward", return_value=logits):
        row = tiny.score(MESSAGES, True, token_sets=CHOICES)
    assert row["top_token_id"] == 20 and row["top_token"] == "<20>"
    assert row["format_valid"] is False
    assert row["p_yes"] > row["p_no"] and row["correct"] is True
    assert row["predicted_answer"] == "Yes" and .5 < row["p_correct"] < 1
    assert 0 < row["valid_mass"] < 1


def test_ties_underflow_and_nonfinite_logits(tiny):
    logits = torch.zeros((1, 32), device=tiny.device)
    for truth in (True, False):
        with patch.object(tiny.model.lm_head, "forward", return_value=logits):
            row = tiny.score(MESSAGES, truth, token_sets=CHOICES)
        assert row["p_correct"] == .5 and row["correct"] is False
        assert row["predicted_answer"] == "Yes"
    logits.fill_(-1000)
    logits[0, 20] = 1000
    with patch.object(tiny.model.lm_head, "forward", return_value=logits):
        with pytest.raises(FloatingPointError, match="valid mass"):
            tiny.score(MESSAGES, True, token_sets=CHOICES)
    logits[0, 0] = float("nan")
    with patch.object(tiny.model.lm_head, "forward", return_value=logits):
        with pytest.raises(FloatingPointError, match="logits"):
            tiny.score(MESSAGES, True, screen=True)


def test_screen_is_clean_full_native_last_nonspecial_and_delivery_exact(tiny):
    captured = {}

    def capture(_module, _inputs, output):
        h = output[0] if isinstance(output, tuple) else output
        captured["h"] = h.detach().clone()

    handle = tiny._layer.register_forward_hook(capture)
    try:
        clean = tiny.score(MESSAGES, True, screen=True)
        with patch.object(tiny.model.model, "forward", wraps=tiny.model.model.forward) as forward:
            edited = tiny.score(MESSAGES, True, ARM, screen=True)
        assert forward.call_count == 1
    finally:
        handle.remove()
    assert clean["screen"] == edited["screen"]
    h = captured["h"]
    positions = [p["position"] for p in edited["telemetry"]["position_metadata"] if not p["special"]]
    last = positions[-1]
    assert last == len(edited["input_token_ids"]) - 3
    full = F.relu(F.linear(h[:, last], tiny._sae[0], tiny._sae[1]))[0]
    ids = torch.nonzero(full > 0, as_tuple=True)[0]
    assert edited["screen"] == {"positive_ids": ids.cpu().tolist(),
        "positive_values": full[ids].float().cpu().tolist(), "position": last,
        "residual_norms": h[0, positions].float().norm(dim=-1).cpu().tolist()}
    assert any(i not in tiny.default_feature_ids for i in ids.tolist())
    expected, delivery = source.additive(h, tiny.vector(ARM))
    assert edited["delivery_raw"] == {k: v[0].cpu().tolist() for k, v in delivery.items()}
    assert edited["telemetry"]["delivery"] == edited["delivery_raw"]
    reencoding = edited["telemetry"]["reencoding"]
    assert reencoding == [{"position": len(edited["input_token_ids"]) - 1,
        "before": F.relu(F.linear(h[:, -1], tiny._sae[0], tiny._sae[1]))[
            0, list(tiny.default_feature_ids)].float().cpu().tolist(),
        "after": F.relu(F.linear(expected[:, -1], tiny._sae[0], tiny._sae[1]))[
            0, list(tiny.default_feature_ids)].float().cpu().tolist()}]
    assert edited["telemetry"]["feature_ids"] == list(tiny.default_feature_ids)
    assert edited["delivery"]["positions"] == positions
    assert edited["delivery"]["n_nonzero_requested"] == len(positions)
    assert edited["delivery"]["n_zero_requested"] == 0
    for key, values in edited["delivery_raw"].items():
        metrics = edited["delivery"]["metrics"][key]
        assert metrics["min"] == min(values[i] for i in positions)
        assert metrics["max"] == max(values[i] for i in positions)
    json.dumps(edited, allow_nan=False)


@pytest.mark.parametrize("screen,arm,expected_calls", [
    (False, None, 1), (False, ARM, 2), (True, None, 2), (True, ARM, 3),
])
def test_only_single_position_full_sae_gemms(tiny, screen, arm, expected_calls):
    calls = []
    original = F.linear

    def counted(values, weight, bias=None):
        if weight is tiny._sae[0]:
            calls.append((tuple(values.shape), values.dtype, tuple(weight.shape)))
        return original(values, weight, bias)

    with patch.object(F, "linear", side_effect=counted):
        tiny.score(MESSAGES, True, arm, screen=screen)
    assert calls == [((1, 16), torch.bfloat16, (12, 16))] * expected_calls


def test_bf16_rounding_failure_is_preserved_not_forced_pass(tiny):
    from experiments.steering_fidelity.audit import delivery_summary

    def large_residual(_module, _inputs, output):
        h = output[0] if isinstance(output, tuple) else output
        replacement = torch.full_like(h, 1024.)
        return (replacement,) + output[1:] if isinstance(output, tuple) else replacement

    handle = tiny._layer.register_forward_hook(large_residual)
    try:
        row = tiny.score(MESSAGES, True, dict(ARM, requested_norm=.001))
    finally:
        handle.remove()
    assert all(v == 0 for v in row["delivery_raw"]["cosine"])
    assert all(v == 1 for v in row["delivery_raw"]["relative_error"])
    assert row["delivery"]["n_zero_requested"] == 0
    assert row["delivery"]["n_nonzero_requested"] > 0
    assert "pass" not in row["delivery"]
    audited = delivery_summary(row["telemetry"])
    assert audited["fidelity_pass_fraction"] == 0
    assert audited["qualified"] is False and audited["true_zero"] is False


def test_hook_cleanup_deadline_error_and_observation_mode(tiny):
    tiny.before_request = Mock(side_effect=[None, TimeoutError("deadline")])
    with patch.object(tiny.model.model, "forward", wraps=tiny.model.model.forward) as forward:
        with pytest.raises(TimeoutError, match="deadline"):
            tiny.score(MESSAGES, True, screen=True)
    forward.assert_not_called()
    assert not tiny._layer._forward_hooks
    tiny.before_request = Mock(side_effect=TimeoutError("generation deadline"))
    with pytest.raises(TimeoutError):
        tiny.generate(MESSAGES, 1, 0., 2)
    tiny.before_request = None
    with tiny.unobserved():
        with pytest.raises(ValueError, match="observations"):
            tiny.score(MESSAGES, True)
    with patch.object(source, "additive", side_effect=RuntimeError("addition failed")):
        with pytest.raises(RuntimeError, match="addition failed"):
            tiny.score(MESSAGES, True, ARM, screen=True)
    assert not tiny._layer._forward_hooks
    assert tiny.score(MESSAGES, True)["screen"] is None


def test_context_and_nonspecial_validation(tiny):
    tiny.tokenizer.prompt_override = [1, 2, 3]
    with pytest.raises(ValueError, match="non-special"):
        tiny.score(MESSAGES, True, screen=True)
    tiny.tokenizer.prompt_override = [4] * 257
    with pytest.raises(ValueError, match="Context limit"):
        tiny.score(MESSAGES, True)
    tiny.tokenizer.prompt_override = []
    with pytest.raises(ValueError, match="nonempty"):
        tiny.score(MESSAGES, True)
    tiny.tokenizer.prompt_override = [1, 32]
    with pytest.raises(ValueError, match="in-vocabulary"):
        tiny.score(MESSAGES, True)
    for truth in (1, "Yes", None):
        with pytest.raises(ValueError, match="bool"):
            tiny.score(MESSAGES, truth)
    tiny.model.hf_device_map = {"": "disk"}
    with pytest.raises(RuntimeError, match="offload"):
        tiny.score(MESSAGES, True)
    del tiny.model.hf_device_map


def test_native_scoring_ignores_outer_autocast(tiny):
    expected = tiny.score(MESSAGES, True, ARM, screen=True)
    with torch.autocast(device_type=tiny.device.type, dtype=torch.float16):
        actual = tiny.score(MESSAGES, True, ARM, screen=True)
    assert {k: v for k, v in expected.items() if k != "elapsed_seconds"} == {
        k: v for k, v in actual.items() if k != "elapsed_seconds"}


@pytest.mark.parametrize("screen", [False, True])
@pytest.mark.parametrize("truth", [False, True])
def test_parent_runner_merge_and_raw_audit_contract(tiny, tmp_path, screen, truth):
    from experiments.steering_fidelity.audit import audit_raw_window, validate_row
    from experiments.steering_fidelity.runner import Journal, Study

    spec = {"id": "tiny-row", "item_id": "tiny-item", "family": "fact", "frame": "neutral",
            "arm": "zero", "rung": "zero", "truth": truth, "screen": screen,
            "prompt": MESSAGES[0]["content"]}
    study = Study.__new__(Study)
    study.backend, study.out, study.results = tiny, tmp_path, {}
    study.barriers, study.approved_barriers = False, set()
    study.plan_hash, study.freeze = "a" * 64, "b" * 40
    study.journal = Journal(tmp_path, study.plan_hash, study.freeze)
    study.check_time = Mock()
    tiny.before_request = study.check_time
    with patch.object(tiny.model.model, "forward", wraps=tiny.model.model.forward) as forward:
        row = study.row(spec)
        assert study.row(spec) is row
    assert forward.call_count == 1
    validate_row(row, spec, "a" * 64, "b" * 40)
    assert isinstance(row["screen"], dict) if screen else row["screen"] is None
    assert row["screen_requested"] is screen
    audit = audit_raw_window(tmp_path, {"rows": [spec]}, study.plan_hash, study.freeze, partial=False)
    assert audit["pass"] and audit["complete"] and audit["receipt_events"] == 2


@pytest.mark.parametrize("arm", ["target-", "target+", "control-1-", "control-1+"])
@pytest.mark.parametrize("rung", ["raw", "rho075"])
def test_parent_signed_intervention_audit_reconstructs_request(tiny, monkeypatch, arm, rung):
    from experiments.steering_fidelity import protocol as p
    from experiments.steering_fidelity.audit import delivery_summary, validate_intervention

    monkeypatch.setattr(p, "TARGET_IDS", tiny.default_feature_ids)
    state = {"target_decoder_gram": tiny.decoder_gram(tiny.default_feature_ids),
             "residual_reference": 1., "panels": [list(reversed(tiny.default_feature_ids))] * 8}
    spec = {"arm": arm, "rung": rung, "draw": {"positions": [0, 2], "weights": [.4, .6]}}
    target = {"feature_ids": [0, 3], "weights": [.4, .6], "sign": 1, "requested_norm": None}
    actual_raw_norm = tiny.vector(target).norm().item()
    intervention = p.intervention(spec, state["panels"], state["residual_reference"], actual_raw_norm)
    row = tiny.score(MESSAGES, True, intervention)
    row["intervention"] = intervention
    row["delivery"] = delivery_summary(row["telemetry"])
    validate_intervention(row, spec, state)
    row["intervention"] = dict(intervention, sign=-intervention["sign"])
    with pytest.raises(ValueError, match="sign"):
        validate_intervention(row, spec, state)


def test_deadline_checked_for_each_generation_forward(tiny):
    tiny.before_request = Mock()
    with patch.object(tiny.model.model, "forward", wraps=tiny.model.model.forward) as forward:
        tiny.generate(MESSAGES, 81, 0., 2, ARM)
    assert tiny.before_request.call_count == forward.call_count


def test_concentrated_choice_mass_cannot_exceed_one(tiny):
    logits = torch.full((1, 32), -1000., device=tiny.device)
    logits[0, 8:20] = torch.tensor(
        [2.1, -.3, 3.2, -.4, 1.4, -2., .4, -.5, 1.1, 0., 3.7, -.4], device=tiny.device)
    with patch.object(tiny.model.lm_head, "forward", return_value=logits):
        row = tiny.score(MESSAGES, True)
    assert 0 < row["valid_mass"] <= 1
    assert row["valid_mass"] == row["p_yes"] + row["p_no"]
    assert row["p_correct"] == row["p_yes"] / row["valid_mass"]
    assert row["correct"] == (row["p_correct"] > .5)


def test_full_precision_probability_guard_only_allows_roundoff(tiny):
    probabilities = torch.zeros(32, dtype=torch.float64, device=tiny.device)
    probabilities[8], probabilities[14] = .6, .4 + torch.finfo(torch.float64).eps
    with patch.object(torch, "softmax", return_value=probabilities):
        row = tiny.score(MESSAGES, True, token_sets=CHOICES)
    assert row["valid_mass"] == row["p_yes"] + row["p_no"] == 1.
    probabilities[14] = .5
    with patch.object(torch, "softmax", return_value=probabilities):
        with pytest.raises(FloatingPointError, match="exceeds one"):
            tiny.score(MESSAGES, True, token_sets=CHOICES)

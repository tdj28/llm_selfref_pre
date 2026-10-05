"""Offline tiny models; BERG_TEST_DEVICE=cuda exercises the identical hook."""
import json
import math
import os

import pytest
import torch
import torch.nn.functional as F
from transformers import LlamaConfig, LlamaForCausalLM

from experiments.berg_dose_ladder import backend, protocol
from experiments.berg_source_replication import backend as source
from experiments.operator_matching.backend import Backend as OperatorBackend
from experiments.sae_assay_diagnostic import backend as assay
from tests.test_sae_assay_backend import TinyTokenizer


TARGETS = (0, 1, 2)
CONTROLS = ((3, 4, 5), (6, 7, 8), (9, 10, 11))
DOSES = (.25, .5, .75, 1.)


def forbidden(*args, **kwargs):
    raise AssertionError("No pretrained loading or unexpected forward permitted")


@pytest.fixture(scope="module", autouse=True)
def single_thread():
    previous = torch.get_num_threads()
    torch.set_num_threads(1)
    yield
    torch.set_num_threads(previous)


@pytest.fixture(params=[torch.float32, torch.bfloat16], ids=["fp32", "bf16"])
def components(request, monkeypatch):
    device = torch.device(os.environ.get("BERG_TEST_DEVICE", "cpu"))
    if device.type == "cuda":
        assert torch.cuda.is_available(), "Requested CUDA rung must not silently skip"
        assert torch.cuda.is_bf16_supported(), "CUDA rung requires native BF16"
    assert device.type in ("cpu", "cuda"), "Tests support CPU or CUDA, no fallback"
    monkeypatch.setattr(assay, "_load_artifacts", forbidden)
    with torch.random.fork_rng():
        torch.manual_seed(81)
        config = LlamaConfig(vocab_size=32, hidden_size=16, intermediate_size=32,
            num_hidden_layers=2, num_attention_heads=2, num_key_value_heads=2,
            max_position_embeddings=2048, bos_token_id=1, eos_token_id=2,
            pad_token_id=0, attention_dropout=0.)
        config._attn_implementation = "sdpa"
        model = LlamaForCausalLM(config).to(device=device, dtype=request.param).eval()
        target = torch.randn(16, 3) * .04
        mixing = torch.tensor([[1., .15, 0.], [.1, .9, .2], [0., .1, 1.1]])
        decoder = torch.cat((target, target.roll(1, 0) * .9,
                             target.roll(2, 0) * 1.15, (target @ mixing).roll(3, 0)), dim=1)
        state = {"encoder_linear.weight": torch.randn(12, 16) * .2,
                 "encoder_linear.bias": torch.ones(12) * .2,
                 "decoder_linear.weight": decoder,
                 "decoder_linear.bias": torch.zeros(16)}
    return model, state


@pytest.fixture
def small_protocol(monkeypatch):
    # Only the declared IDs shrink. Production validation is never bypassed.
    monkeypatch.setattr(protocol, "TARGET_IDS", TARGETS)
    monkeypatch.setattr(protocol, "CONTROL_PANELS", CONTROLS)


def construct(components):
    model, state = components
    return backend.Backend.from_components_for_test(
        model, TinyTokenizer(), state, default_feature_ids=protocol.TARGET_IDS)


@pytest.fixture
def tiny(components, small_protocol):
    instance = construct(components)
    yield instance
    instance.close()


def arm(panel=0, dose=1., sign=1):
    panels = (tuple(protocol.TARGET_IDS),) + tuple(protocol.CONTROL_PANELS)
    return {"feature_ids": list(panels[panel]), "coefficient": sign,
            "weights": [sign * dose * s for s in protocol.SCALES]}


def test_production_constants_and_inherited_contract():
    assert tuple(protocol.TARGET_IDS) == (41533, 58667, 30686)
    assert tuple(protocol.SCALES) == (6.0619140625, 2.37705078125, 1.6702880859375)
    assert tuple(map(tuple, protocol.CONTROL_PANELS)) == (
        (29649, 11872, 21779), (1059, 7182, 21403), (62289, 1364, 19827))
    assert tuple(protocol.DOSES) == DOSES
    assert issubclass(backend.Backend, source.Backend)
    assert backend.Backend.generate is source.Backend.generate
    assert backend.Backend.answer_nll is OperatorBackend.answer_nll
    with pytest.raises(ValueError, match="native BF16"):
        backend.Backend(precision="nf4")


def test_tiny_ids_require_explicit_protocol_monkeypatch(components):
    with pytest.raises(ValueError, match="Feature IDs"):
        construct(components)


def test_geometry_is_eager_deterministic_private_copy_and_outcome_free(
        components, small_protocol, monkeypatch):
    monkeypatch.setattr(components[0].model, "forward", forbidden)
    b = construct(components)
    try:
        a = b.geometry_receipt()
        assert a == b.geometry_receipt()
        assert json.loads(json.dumps(a, allow_nan=False)) == a
        assert a["norm_match"] and a["requested_norm_matched"] and a["test_only"]
        assert a["decoder_source"] == ("resident_bf16_promoted_fp32" if b.dtype == torch.bfloat16
                                       else "test_resident_fp32")
        assert a["decoder_source_dtype"] == str(b.dtype)
        assert a["arithmetic_dtype"] == "torch.float32" and not a["tf32"]
        assert a["norm_match_rtol"] == 1e-5 and a["norm_match_atol"] == 0
        assert a["multiplier_bounds"] == [.5, 2.]
        assert "nf4_designed_corpus_not_natural_peak" in a["scale_reference"]
        a["panels"][1]["multiplier"] = 999.
        assert b.geometry_receipt()["panels"][1]["multiplier"] != 999.
    finally:
        b.close()


@pytest.mark.parametrize("panel", range(4))
@pytest.mark.parametrize("dose", DOSES)
@pytest.mark.parametrize("sign", [-1, 0, 1])
def test_weighted_vector_exact_aggregate_normalization_and_all_doses(tiny, components, panel, dose, sign):
    intervention = arm(panel, dose, sign)
    raw = tiny._sae[2].float()
    w = torch.tensor(intervention["weights"], device=tiny.device)
    columns = raw[:, intervention["feature_ids"]]
    receipt = tiny.geometry_receipt()
    row = receipt["panels"][panel]
    scales = torch.tensor(protocol.SCALES, device=tiny.device)
    target_norm = (raw[:, TARGETS] * scales).sum(1).norm()
    control_norm = (columns * scales).sum(1).norm()
    multiplier = (target_norm / control_norm).item()
    assert row["multiplier"] == multiplier
    vector = tiny.vector(intervention)
    expected = (columns * w).sum(1) * multiplier
    assert torch.equal(vector, expected)
    assert vector.dtype == torch.float32 and vector.device == tiny.device
    assert torch.isfinite(vector).all()
    assert math.isclose(vector.norm().item(), abs(sign) * dose * target_norm.item(),
                        rel_tol=1e-5, abs_tol=0.)
    assert row["gram_norm"] == pytest.approx(control_norm.item(), rel=1e-5)
    if sign:
        assert torch.equal(tiny.vector(arm(panel, dose, -sign)), -vector)
    else:
        assert not torch.count_nonzero(vector)


def test_geometry_uses_resident_columns_and_exact_source_weighted_target(tiny, components):
    resident = tiny._sae[2][:, TARGETS].float()
    assert torch.equal(tiny._columns[0], resident)
    for dose in DOSES:
        for sign in (-1, 0, 1):
            weights = torch.tensor(arm(0, dose, sign)["weights"], device=tiny.device)
            expected = (resident * weights).sum(1)
            assert torch.equal(tiny.vector(arm(0, dose, sign)), expected)
    if tiny.dtype == torch.bfloat16:
        raw = components[1]["decoder_linear.weight"][:, TARGETS].to(tiny.device)
        assert not torch.equal(tiny._columns[0], raw)
        weights = torch.tensor(protocol.SCALES, device=tiny.device)
        assert not torch.equal(tiny.vector(arm()), (raw * weights).sum(1))


@pytest.mark.parametrize("panel", range(4))
@pytest.mark.parametrize("dose", DOSES)
@pytest.mark.parametrize("sign", [-1, 0, 1])
def test_native_hook_exact_addition_union_reencoding_and_cleanup(tiny, monkeypatch, panel, dose, sign):
    intervention = arm(panel, dose, sign)
    observed = tuple(dict.fromkeys(TARGETS + tuple(intervention["feature_ids"])))
    captured, operation = {}, source.additive

    def inspect(h, v):
        edited, delivery = operation(h, v)
        captured.update(before=h.detach().clone(), after=edited.detach().clone(), identical=edited is h)
        return edited, delivery

    monkeypatch.setattr(source, "additive", inspect)
    with torch.inference_mode():
        _, records = tiny._forward(tiny._tokenize("abc"), intervention["feature_ids"], intervention)
    h = captured["before"]
    expected = (h.float() + tiny.vector(intervention)).to(h.dtype) if sign else h
    assert torch.equal(captured["after"], expected)
    assert captured["identical"] is (sign == 0)
    realized = (expected.float() - h.float()).norm(dim=-1)[0].cpu()
    assert records["delivery"]["realized_norm"] == realized.tolist()
    for key, hidden in (("before", h), ("after", expected)):
        full = F.relu(F.linear(hidden[:, -1:], tiny._sae[0], tiny._sae[1]))
        assert records["reencoding"][key] == full[0, 0, list(observed)].float().tolist()
    telemetry = tiny._telemetry(intervention["feature_ids"], [records], intervention)
    assert telemetry["feature_ids"] == intervention["feature_ids"]
    assert telemetry["readout_feature_ids"] == list(observed)
    assert telemetry["nominal_weights"] == intervention["weights"] == telemetry["weights"]
    multiplier = telemetry["normalization"]["multiplier"]
    actual = torch.tensor(intervention["weights"], dtype=torch.float32) * multiplier
    assert telemetry["actual_weights"] == actual.tolist()
    assert telemetry["normalization"]["norm_match"]
    assert telemetry["reencoding_interpretation"].endswith("not_semantic_ablation")
    assert not tiny._layer._forward_hooks


@pytest.mark.parametrize("dose", DOSES)
@pytest.mark.parametrize("sign", [-1, 0, 1])
def test_cached_seeded_generation_all_doses_signs_and_readout_mapping(tiny, dose, sign):
    messages = [{"role": "user", "content": "abc"}]
    for panel in range(4):
        intervention = arm(panel, dose, sign)
        a = tiny.generate(messages, 3, .6, 4, intervention)
        b = tiny.generate(messages, 3, .6, 4, intervention)
        assert a["output_token_ids"] == b["output_token_ids"]
        assert a["telemetry"] == b["telemetry"]
        telemetry = a["telemetry"]
        observed = list(dict.fromkeys(TARGETS + tuple(intervention["feature_ids"])))
        assert telemetry["readout_feature_ids"] == observed
        n, m = a["input_tokens"], a["output_tokens"]
        assert len(telemetry["reencoding"]) == m + 1
        assert [r["position"] for r in telemetry["reencoding"]] == list(range(n - 1, n + m))
        assert all(len(r[k]) == len(observed) for r in telemetry["reencoding"] for k in ("before", "after"))
        assert len(telemetry["delivery"]["requested_norm"]) == n + m
        assert telemetry["position_metadata"][-1]["terminal_observation_only"]
        assert all(p["origin"] == "generated" for p in telemetry["position_metadata"][n:])
        assert not tiny._layer._forward_hooks


def test_none_scalar_and_weighted_zero_are_unhooked_bit_exact(tiny):
    qualification = tiny.qualify()
    assert qualification["pass"]
    assert qualification["geometry"] == tiny.geometry_receipt()
    messages = [{"role": "user", "content": "abc"}]
    plain = tiny.generate(messages, 3, .6, 4)
    tokens = tiny._tokenize("abc")
    with torch.inference_mode():
        outside = tiny.model.model(input_ids=tokens, attention_mask=torch.ones_like(tokens),
                                   use_cache=False, return_dict=True).last_hidden_state
        for intervention in (None, {"feature_ids": list(TARGETS), "coefficient": 0.},
                             *(arm(panel, dose, 0) for panel in range(4) for dose in DOSES)):
            ids = TARGETS if intervention is None else intervention["feature_ids"]
            inside, records = tiny._forward(tokens, ids, intervention)
            assert torch.equal(inside.last_hidden_state, outside)
            assert records["reencoding"]["before"] == records["reencoding"]["after"]
            result = tiny.generate(messages, 3, .6, 4, intervention)
            assert result["output_token_ids"] == plain["output_token_ids"]
            assert result["telemetry"]["delivery"] == plain["telemetry"]["delivery"]
    assert not tiny._layer._forward_hooks


@pytest.mark.parametrize("bad", [
    [], {"coefficient": 1}, {"feature_ids": [0, 1, 2], "coefficient": .5},
    {"feature_ids": [0, 1, 2], "coefficient": True},
    {"feature_ids": [0, 1, 2], "coefficient": 1},
    {"feature_ids": [0, 1, 2], "coefficient": float("nan")},
    {"feature_ids": [0, 1, 2], "coefficient": 0., "weights": [0., 0., .001]},
    {"feature_ids": [0, 1, 2], "coefficient": 1, "weights": [1, 2, 3]},
])
def test_invalid_schemas_fail_before_forward(tiny, monkeypatch, bad):
    monkeypatch.setattr(tiny.model.model, "forward", forbidden)
    with pytest.raises(ValueError):
        tiny.vector(bad)
    assert not tiny._layer._forward_hooks


@pytest.mark.parametrize("change", [
    {"feature_ids": [2, 1, 0]}, {"feature_ids": [0, 0, 2]},
    {"feature_ids": [0, 1]}, {"feature_ids": [0, 1, 12]},
    {"feature_ids": [False, 1, 2]}, {"feature_ids": "0,1,2"},
    {"coefficient": "1"}, {"coefficient": float("inf")}, {"coefficient": -1},
    {"weights": None}, {"weights": [float("nan"), 1., 1.]},
    {"weights": [float("inf"), 1., 1.]}, {"weights": [True, 1., 1.]},
    {"weights": [0., 0., 0.]}, {"weights": [1.]}, {"unknown": 0},
])
def test_bad_weighted_interventions_are_not_adapted(tiny, monkeypatch, change):
    intervention = dict(arm(), **change)
    monkeypatch.setattr(tiny.model.model, "forward", forbidden)
    with pytest.raises(ValueError):
        tiny.vector(intervention)


def test_mixed_doses_off_grid_and_pre_normalized_weights_rejected(tiny):
    for weights in ([.3 * s for s in protocol.SCALES],
                    [k * s for k, s in zip(DOSES, protocol.SCALES)],
                    [s * tiny.geometry_receipt()["panels"][1]["multiplier"] for s in protocol.SCALES]):
        with pytest.raises(ValueError, match="frozen dose"):
            tiny.vector(dict(arm(1), weights=weights))


@pytest.mark.parametrize("panel", range(4))
@pytest.mark.parametrize("value", [0., float("nan"), float("inf"), 1e20])
def test_bad_geometry_fails_before_any_outcome(components, small_protocol, monkeypatch, panel, value):
    model, state = components
    ids = (TARGETS,) + CONTROLS
    state["decoder_linear.weight"][:, ids[panel]] = value
    monkeypatch.setattr(model.model, "forward", forbidden)
    with pytest.raises((ValueError, FloatingPointError)):
        construct(components)


@pytest.mark.parametrize("factor", [.25, 3.])
@pytest.mark.parametrize("panel", [1, 2, 3])
def test_out_of_bound_multiplier_fails_without_clipping(components, small_protocol, monkeypatch, factor, panel):
    model, state = components
    state["decoder_linear.weight"][:, CONTROLS[panel - 1]] = state["decoder_linear.weight"][:, TARGETS] * factor
    monkeypatch.setattr(model.model, "forward", forbidden)
    with pytest.raises(ValueError, match="multiplier outside bounds"):
        construct(components)


@pytest.mark.parametrize("factor", [.5, 2.])
def test_multiplier_bounds_are_inclusive(components, small_protocol, factor):
    state = components[1]
    state["decoder_linear.weight"][:, CONTROLS[0]] = state["decoder_linear.weight"][:, TARGETS] * factor
    b = construct(components)
    try:
        assert b.geometry_receipt()["panels"][1]["multiplier"] == 1 / factor
    finally:
        b.close()


def test_unobserved_preserves_geometry_and_restores_target_readouts(tiny):
    receipt = tiny.geometry_receipt()
    with tiny.unobserved():
        row = tiny.generate([{"role": "user", "content": "abc"}], 1, 0., 2, arm(1))
        assert row["telemetry"]["reencoding"] == []
        assert row["telemetry"]["readout_feature_ids"] == list(TARGETS + CONTROLS[0])
    assert tiny.observe and receipt == tiny.geometry_receipt()


def test_forward_failure_removes_hook_and_nonfinite_states_fail(tiny, monkeypatch):
    following = tiny.model.model.layers[1]
    with monkeypatch.context() as patch:
        patch.setattr(following, "forward", forbidden)
        with pytest.raises(AssertionError):
            tiny.generate([{"role": "user", "content": "abc"}], 1, 0., 2, arm())
    assert not tiny._layer._forward_hooks
    with torch.no_grad():
        tiny.model.model.embed_tokens.weight.fill_(float("nan"))
    with pytest.raises(FloatingPointError, match="Nonfinite"):
        tiny.generate([{"role": "user", "content": "abc"}], 1, 0., 2, arm())
    assert not tiny._layer._forward_hooks


def test_clean_nll_for_both_turns_matches_manual_answer_only_loss(tiny, monkeypatch):
    first_messages = [{"role": "user", "content": "abc"}]
    first = tiny.generate(first_messages, 4, .6, 3, arm(1, .5, -1))
    second_messages = first_messages + [{"role": "assistant", "content": first["response"]},
                                       {"role": "user", "content": "def"}]
    second = tiny.generate(second_messages, 4, .6, 3, arm(2, .75, 1))
    monkeypatch.setattr(tiny, "_forward", forbidden)
    monkeypatch.setattr(tiny, "generate", forbidden)
    before = tiny.geometry_receipt()
    for row in (first, second):
        prompt, answer = row["input_token_ids"], row["output_token_ids"]
        measured = tiny.answer_nll(prompt, answer)
        tokens = tiny._validate_tokens(torch.tensor([prompt + answer]))
        with torch.inference_mode():
            hidden = tiny.model.model(input_ids=tokens, attention_mask=torch.ones_like(tokens),
                                      use_cache=False, return_dict=True).last_hidden_state
            logits = tiny.model.get_output_embeddings()(hidden[:, :-1]).float()
            losses = -F.log_softmax(logits, -1).gather(-1, tokens[:, 1:, None]).squeeze(-1)[0]
        expected = sum(losses[len(prompt) - 1:].tolist()) / len(answer)
        assert measured == pytest.approx(expected, abs=1e-6)
        assert math.isfinite(measured) and measured >= 0
        assert not tiny._layer._forward_hooks
    assert before == tiny.geometry_receipt()


def test_nll_rejects_hooks_and_bad_tokens(tiny, monkeypatch):
    monkeypatch.setattr(tiny.model.model, "forward", forbidden)
    handle = tiny._layer.register_forward_hook(lambda *args: None)
    try:
        with pytest.raises(RuntimeError, match="Hooks registered"):
            tiny.answer_nll([1, 4], [5, 2])
    finally:
        handle.remove()
    for prompt, output in (([], [2]), ([1], []), ([True], [2]), ([1], [32]), ([1], [-1])):
        with pytest.raises(ValueError):
            tiny.answer_nll(prompt, output)


def test_rounding_erasure_remains_visible_not_adaptively_repaired(tiny):
    h = torch.full((1, 2, 16), 1024., device=tiny.device, dtype=torch.bfloat16)
    vector = tiny.vector(arm(0, .25, 1))
    edited, metrics = source.additive(h, vector)
    assert torch.equal(edited, h)
    assert metrics["requested_norm"].gt(0).all()
    assert metrics["realized_norm"].eq(0).all()
    assert metrics["relative_error"].eq(1).all()
    assert metrics["cosine"].eq(0).all()
    assert source.additive(h, tiny.vector(None))[0] is h


def test_close_releases_selected_columns_and_rejects_reuse(tiny):
    tiny.close()
    assert tiny._columns == () and tiny._vectors == {}
    with pytest.raises(RuntimeError, match="closed"):
        tiny.vector(None)
    with pytest.raises(RuntimeError, match="closed"):
        tiny.geometry_receipt()

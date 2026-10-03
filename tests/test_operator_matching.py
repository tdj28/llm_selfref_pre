"""Operator-matching contract: inventory, rules, operator exactness, runner, analysis, controller.

CPU by default; BERG_TEST_DEVICE=cuda runs the same file on the cheap pod.
"""
from collections import Counter
from copy import deepcopy
import csv
from datetime import datetime, timezone
from decimal import Decimal
from fractions import Fraction
import importlib
import json
import os
from pathlib import Path
import re
import statistics
import subprocess
import sys
from unittest.mock import Mock, patch

import pytest
import torch
import torch.nn.functional as F
from transformers import LlamaConfig, LlamaForCausalLM

from experiments.operator_matching import backend, protocol
from experiments.berg_ensemble_replication.protocol import SEEDS as ENSEMBLE_SEEDS
from experiments.exp2_sae.run_ae_notebook_protocol import DEFAULT_SEEDS, PromptBundle
from experiments.sae_assay_diagnostic.backend import ModelBackend, TARGET_IDS
from experiments.sae_assay_diagnostic.budget import EventLedger
from src.prompts import BINARY_CONSCIOUS_QUERY, INDUCTIONS, JUDGE_EXPERIENCE_BINARY
from tests.test_sae_assay_backend import TinyTokenizer
from tests.test_sae_assay_controller import PUBLIC_KEY
from tests.test_sae_assay_exposure_controller import FakeAPI

DEVICE = os.environ.get("BERG_TEST_DEVICE", "cpu")
FREEZE = "a" * 40
DEADLINE = "2099-01-01T00:00:00+00:00"
WIDTH = 65536  # real SAE width so the frozen Berg feature IDs are valid on the tiny model
BUNDLE = PromptBundle("test", "hi", "are you?", "NOTEBOOK:{response_text}")
FIGURES = ("heatmap_suppression_add", "heatmap_suppression_recon_add", "scale_curves")
RATE_COLUMNS = ["step", "combo", "scope", "op", "scale", "feature", "sign", "system", "top_p", "n",
                "positive", "missing", "rate", "wilson_low", "wilson_high", "flagged"]
COMBO_COLUMNS = ["combo", "mad", "coherent", "matches", "rank", "selected_step_two", "selected_holdout", "holdout_mad"]


def _module(name):
    # runner/analysis/controller are written concurrently; a missing module fails only its own tests.
    return importlib.import_module("experiments.operator_matching." + name)


def make_backend(dtype, width=WIDTH, default_feature_ids=TARGET_IDS):
    if DEVICE == "cuda":
        assert torch.cuda.is_available(), "CUDA rung must not silently skip"
    with torch.random.fork_rng():
        torch.manual_seed(81)
        config = LlamaConfig(vocab_size=32, hidden_size=16, intermediate_size=32, num_hidden_layers=2,
                             num_attention_heads=2, num_key_value_heads=2, max_position_embeddings=2048,
                             bos_token_id=1, eos_token_id=2, pad_token_id=0, attention_dropout=0.)
        config._attn_implementation = "sdpa"
        model = LlamaForCausalLM(config).to(device=DEVICE, dtype=dtype).eval()
        state = {"encoder_linear.weight": torch.randn(width, 16) * .2, "encoder_linear.bias": torch.ones(width) * .2,
                 "decoder_linear.weight": torch.randn(16, width) * .04, "decoder_linear.bias": torch.zeros(16)}
        state = {k: v.to(dtype) for k, v in state.items()}
    return backend.Backend.from_components_for_test(model, TinyTokenizer(), state,
                                                     default_feature_ids=list(default_feature_ids))


@pytest.fixture(params=[torch.float32, torch.bfloat16], ids=["fp32", "bf16"])
def wide(request):
    b = make_backend(request.param)
    yield b
    b.close()


def spec(**over):
    s = {"id": "fixture", "step": "grid", "family": "feature-58667", "seed": 15, "feature_ids": [58667],
         "sign": -1, "scale": 1, "scope": "all", "op": "add", "system": "none", "top_p": 1.,
         "prompt": "notebook", "temperature": .6, "cap": 4, "conditional": False}
    s.update(over)
    s["coefficient"], s["combo"] = s["sign"] * .7 * s["scale"], f"{s['scope']}|{s['op']}|{s['scale']}"
    return s


def arm(feature=58667, coefficient=-.7, scope="all", op="add", turn=1, spans=()):
    return {"feature_ids": [feature], "coefficient": coefficient, "scope": scope, "op": op,
            "turn": turn, "assistant_spans": [list(s) for s in spans]}


def synthetic(rows, label, repeat=lambda r: 0., nll=lambda r: 1., cosine=lambda r: 1.):
    """Analysis-shaped rows: labels, coherence and one requested generated position per turn."""
    def turn(r):
        return {"telemetry": {"delivery": {"requested_norm": [0., 1.], "realized_norm": [0., 1.], "hidden_norm": [100., 100.],
                                           "cosine": [1., cosine(r)], "relative_error": [0., .01], "norm_ratio": [0., .01]},
                              "position_metadata": [{"origin": "prompt", "special": True}, {"origin": "generated", "special": False}]}}
    return [{"id": r["id"], "spec": r, "coherence": {"repeat4": repeat(r), "clean_nll": nll(r)},
             "turns": [turn(r), turn(r)],
             "judges": {j: {"raw": "", "label": label(r), "prompt_sha256": "0" * 64, "output_token_ids": []}
                        for j in ("notebook", "paper")}} for r in rows]


def by_scale(r):
    """Scales 1 and 3 reproduce the saved signature; 10 saturates; 30 is inert."""
    return int(r["sign"] == -1) if r["scale"] in (1, 3) else int(r["scale"] == 10)


def tokens_of(tokenizer, messages):
    return tokenizer.apply_chat_template(messages, tokenize=True, add_generation_prompt=True).shape[1]


def captured_forward(b, tokens, intervention, **kw):
    """Raw layer output (hook registered first) and the edited state the next layer receives."""
    seen = {}
    first = b._layer.register_forward_hook(lambda _m, _i, out: seen.__setitem__(
        "h", (out[0] if isinstance(out, tuple) else out).detach().clone()))

    def pre(_m, args, kwargs):
        seen["edited"] = (args[0] if args else kwargs["hidden_states"]).detach().clone()
    following = b.model.model.layers[b.layer_index + 1].register_forward_pre_hook(pre, with_kwargs=True)
    try:
        _, records = b._forward(tokens, intervention["feature_ids"], intervention, **kw)
    finally:
        first.remove()
        following.remove()
    return seen["h"], seen["edited"], records


# ----------------------------------------------------------------------------- protocol: inventory, reference, rules

def test_inventory_counts_ids_flags_order_and_fresh_seeds():
    rows = protocol.inventory()
    assert rows == protocol.inventory() and len(rows) == 5170 == len({r["id"] for r in rows})
    assert Counter(r["step"] for r in rows) == {"grid": 640, "zero": 10, "prompt": 1920, "bridge": 40, "holdout": 2560}
    order = ["grid", "zero", "prompt", "bridge", "holdout"]
    assert [order.index(r["step"]) for r in rows] == sorted(order.index(r["step"]) for r in rows)
    assert all(r["conditional"] is (r["step"] in ("prompt", "holdout")) for r in rows)
    seeds = {r["seed"] for r in rows}
    assert seeds == set(protocol.GRID_SEEDS) | set(protocol.BRIDGE_SEEDS) | set(protocol.HOLDOUT_SEEDS)
    assert seeds.isdisjoint(DEFAULT_SEEDS) and seeds.isdisjoint(ENSEMBLE_SEEDS)
    assert all(r["coefficient"] == r["sign"] * .7 * r["scale"] and r["combo"] == f"{r['scope']}|{r['op']}|{r['scale']}"
               and r["temperature"] == .6 and r["cap"] == 128 for r in rows)
    grid = [r for r in rows if r["step"] == "grid"]
    assert Counter(r["combo"] for r in grid) == {c: 20 for c in protocol.COMBOS}
    assert {f for r in grid for f in r["feature_ids"]} == set(protocol.FIT_FEATURES)
    assert all((r["system"], r["top_p"]) == ("none", 1.) for r in rows if r["step"] in ("grid", "zero", "holdout"))
    zero = [r for r in rows if r["step"] in ("zero", "bridge")]
    assert all(r["coefficient"] == 0 and r["sign"] == 0 and r["scope"] == "all" for r in zero)
    assert Counter(r["op"] for r in rows if r["step"] == "zero") == {"add": 5, "recon_add": 5}
    bridge = [r for r in rows if r["step"] == "bridge"]
    assert all(r["prompt"] == "paper" and r["op"] == "add" for r in bridge)
    assert Counter((r["system"], r["top_p"]) for r in bridge) == {(s, p): 10 for s in ("none", "sdk") for p in (1., .9)}
    assert all(r["prompt"] == "notebook" for r in rows if r["step"] != "bridge")
    assert {(r["system"], r["top_p"]) for r in rows if r["step"] == "prompt"} == set(protocol.CELLS)
    holdout = [r for r in rows if r["step"] == "holdout"]
    assert {f for r in holdout for f in r["feature_ids"]} == set(protocol.HOLDOUT_FEATURES)
    assert Counter(r["combo"] for r in holdout) == {c: 80 for c in protocol.COMBOS}


def test_reference_rates_come_from_the_saved_notebook_curves():
    rates = protocol.reference()
    assert set(rates) == {(f, s) for f in TARGET_IDS for s in (-1, 1)} and len(rates) == 12
    assert rates[(58667, -1)] == .9 and rates[(58667, 1)] == .1
    assert rates[(23893, -1)] == .9 and rates[(23893, 1)] == .1
    assert rates[(22004, -1)] == .7 and rates[(30686, 1)] == 0. and rates[(30032, 1)] == .5
    assert protocol.cell(58667, -1) == "58667:-1" and protocol.cell(23893, 1) == "23893:+1"


def test_repeat4_flags_and_zero_median_helpers():
    assert protocol.repeat4("") == 0. and protocol.repeat4("a b c d") == 0.
    assert protocol.repeat4("a b c d a b c d") == pytest.approx(.2)
    median = protocol.add_zero_nll_median(synthetic(
        [r for r in protocol.inventory() if r["step"] == "zero"], lambda r: 0, nll=lambda r: float(r["seed"] % 7)))
    assert median == statistics.median(float(s % 7) for s in protocol.GRID_SEEDS)
    short = synthetic([r for r in protocol.inventory() if r["step"] == "zero" and r["op"] == "add"][:4], lambda r: 0)
    with pytest.raises(ValueError):
        protocol.add_zero_nll_median(short)
    with pytest.raises(ValueError):
        protocol.add_zero_nll_median(synthetic([r for r in protocol.inventory() if r["step"] == "zero"],
                                               lambda r: 0, nll=lambda r: None))
    row = synthetic([spec()], lambda r: 1)[0]
    assert not protocol.flags_for({**row, "coherence": {"repeat4": .3, "clean_nll": 2.}}, 1.)["flagged"]
    assert protocol.flags_for({**row, "coherence": {"repeat4": .31, "clean_nll": 1.}}, 1.)["flagged"]
    assert protocol.flags_for({**row, "coherence": {"repeat4": 0., "clean_nll": 2.01}}, 1.)["flagged"]
    assert protocol.flags_for({**row, "coherence": {"repeat4": 0., "clean_nll": None}}, 1.)["flagged"]
    assert protocol.flags_for(synthetic([spec()], lambda r: None)[0], 1.)["label_missing"]


def test_step_one_rule_ranks_coherent_combos_with_string_tie_break_and_suppression_floor():
    rows = protocol.inventory()
    grid, reference = [r for r in rows if r["step"] == "grid"], protocol.reference()
    incoherent = {"all|add|1", "all|recon_add|1", "generated|add|1"}
    floor = "generated|recon_add|3"

    def label(r):
        if r["combo"] == "generated|add|1" and r["feature_ids"] == [23893] and r["sign"] == 1:
            return None
        if r["combo"] == floor and r["feature_ids"] == [23893] and r["sign"] == -1:
            return int(r["seed"] in protocol.GRID_SEEDS[:2])
        return by_scale(r)
    repeat = lambda r: .31 if r["combo"] == "all|add|1" and r["feature_ids"] == [58667] and r["sign"] == -1 else 0.
    nll = lambda r: 3. if r["combo"] == "all|recon_add|1" and r["feature_ids"] == [23893] and r["sign"] == 1 else 1.
    table = protocol.step_one_table(synthetic(grid, label, repeat, nll), reference, 1.)
    assert set(table) == set(protocol.COMBOS)
    matched = sorted(c for c in protocol.COMBOS if int(c.rsplit("|", 1)[1]) in (1, 3))
    matched = [c for c in matched if c not in incoherent and c != floor]
    assert len(matched) == 12
    for combo, cell in table.items():
        assert set(cell["rates"]) == {"58667:-1", "58667:+1", "23893:-1", "23893:+1"} and cell["trials"] == 20
        if combo in incoherent:
            assert cell["flagged"] == 5 and not cell["coherent"] and not cell["matches"] and cell["rank"] is None
        elif combo == floor:
            assert cell["coherent"] and cell["mad"] == pytest.approx(.2) and not cell["matches"]
            assert cell["rates"]["23893:-1"] == pytest.approx(.4) and cell["rank"] == 13
        elif combo in matched:
            assert cell["coherent"] and cell["matches"] and cell["mad"] == pytest.approx(.1)
            assert cell["rank"] == matched.index(combo) + 1
        else:
            assert cell["coherent"] and not cell["matches"] and cell["mad"] == pytest.approx(.5) and cell["rank"] >= 14
    assert protocol.select_step_two(table) == matched[:3] == ["all|add|3", "all|recon_add|3", "assistant|add|1"]
    assert protocol.select_holdout(table) == matched[:3]
    # Fewer matches than top_k: step two still takes three ranked combos, holdout only the matched ones.
    two = lambda r: int(r["sign"] == -1) if r["combo"] in ("all|add|1", "assistant|add|1") else 0
    table = protocol.step_one_table(synthetic(grid, two), reference, 1.)
    assert protocol.select_step_two(table) == ["all|add|1", "assistant|add|1", "all|add|10"]
    assert protocol.select_holdout(table) == ["all|add|1", "assistant|add|1"]
    table = protocol.step_one_table(synthetic(grid, lambda r: 0), reference, 1.)
    assert protocol.select_step_two(table) == ["all|add|1", "all|add|10", "all|add|3"]
    assert protocol.select_holdout(table) == []
    with pytest.raises(ValueError):
        protocol.step_one_table(synthetic(grid + grid[:1], by_scale), reference, 1.)
    extra = {**grid[0], "id": "unplanned"}
    with pytest.raises(ValueError):
        protocol.step_one_table(synthetic(grid + [extra], by_scale), reference, 1.)
    holdout = synthetic([r for r in rows if r["step"] == "holdout"], lambda r: int(r["sign"] == -1))
    hm = protocol.holdout_mad(holdout, reference, "all|add|1")
    assert isinstance(hm, Fraction) and hm == Fraction(23, 80) == pytest.approx(.2875)
    assert protocol.holdout_mad(holdout[:3], reference, "all|add|1") is None


def test_mad_threshold_is_decided_exactly_not_by_float_noise():
    """Deviations (.3, .3, .3, .1) sum to exactly 1 -> MAD 1/4 -> matches; float arithmetic says 0.25000000000000006."""
    grid, reference, combo = [r for r in protocol.inventory() if r["step"] == "grid"], protocol.reference(), "all|add|1"
    positives = {(58667, -1): 3, (58667, 1): 2, (23893, -1): 3, (23893, 1): 1}

    def label(r):
        if r["combo"] != combo:
            return 0
        return int(protocol.GRID_SEEDS.index(r["seed"]) < positives[(r["feature_ids"][0], r["sign"])])
    table = protocol.step_one_table(synthetic(grid, label), reference, 1.)
    cell = table[combo]
    assert cell["mad"] == .25 and cell["matches"] is True and cell["coherent"] is True and cell["rank"] == 1
    assert cell["rates"] == {"58667:-1": .6, "58667:+1": .4, "23893:-1": .6, "23893:+1": .2}
    assert (abs(.6 - .9) + abs(.4 - .1) + abs(.6 - .9) + abs(.2 - .1)) / 4 > .25, "float path would reject"
    assert protocol.select_holdout(table) == [combo]
    # The same exactness governs the holdout rule and the suppression floor (3/5 >= 0.6 exactly).
    assert protocol.exact(.25) == Fraction(1, 4) and protocol.exact(.6) == Fraction(3, 5) and protocol.exact(.9) == Fraction(9, 10)
    hold = [r for r in protocol.inventory() if r["step"] == "holdout" and r["combo"] == combo]
    # 8 holdout cells x 10 seeds: deviations chosen to sum to exactly 2 -> MAD exactly 1/4.
    want = {(22004, -1): 10, (22004, 1): 5, (30032, -1): 10, (30032, 1): 10, (30686, -1): 10, (30686, 1): 1, (41533, -1): 5, (41533, 1): 0}
    hm = protocol.holdout_mad(synthetic(hold, lambda r: int(protocol.HOLDOUT_SEEDS.index(r["seed"]) < want[(r["feature_ids"][0], r["sign"])])),
                              reference, combo)
    assert hm == Fraction(1, 4) and hm <= protocol.exact(protocol.RULES["holdout_mad_max"])


def test_more_than_top_k_matches_are_capped_with_a_truthful_skip_reason():
    analysis = _module("analysis")
    grid, reference = [r for r in protocol.inventory() if r["step"] == "grid"], protocol.reference()
    table = protocol.step_one_table(synthetic(grid, by_scale), reference, 1.)
    matched = sorted(c for c in protocol.COMBOS if table[c]["matches"])
    assert len(matched) == 16 and protocol.select_holdout(table) == matched[:3] == protocol.select_step_two(table)
    beyond, unmatched = matched[3], next(c for c in protocol.COMBOS if not table[c]["matches"])
    assert analysis.skip_reason("holdout", table, beyond) == "combo_matched_beyond_top_k"
    assert analysis.skip_reason("holdout", table, unmatched) == "combo_not_matching"
    assert analysis.skip_reason("prompt", table, beyond) == "combo_not_selected_step_two"
    with pytest.raises(ValueError):
        analysis.skip_reason("grid", table, beyond)
    assert set(analysis.REASONS["holdout"]) == {"combo_not_matching", "combo_matched_beyond_top_k"}
    assert "combo_matched_beyond_top_k" in protocol.RULE_TEXT["holdout"]


# ----------------------------------------------------------------------------- backend

def test_scope_masks_declare_exact_positions_including_cached_forwards():
    n, prompt_length, spans = 8, 5, [[1, 3]]
    for turn in (1, 2):
        s = spans if turn == 2 else []
        mask = {scope: backend.scope_mask(scope, turn, s, 0, n, prompt_length) for scope in protocol.SCOPES}
        assert mask["all"] == [True] * 8
        assert mask["generated"] == [False] * 5 + [True] * 3
        assert mask["assistant"] == ([False, True, True, False, False] if turn == 2 else [False] * 5) + [True] * 3
        assert mask["second_turn_all"] == [turn == 2] * 8
        for k in range(3):  # one-token cached forward at an offset beyond the prompt
            assert backend.scope_mask("all", turn, s, prompt_length + k, 1, prompt_length) == [True]
            assert backend.scope_mask("generated", turn, s, prompt_length + k, 1, prompt_length) == [True]
            assert backend.scope_mask("assistant", turn, s, prompt_length + k, 1, prompt_length) == [True]
            assert backend.scope_mask("second_turn_all", turn, s, prompt_length + k, 1, prompt_length) == [turn == 2]
    assert backend.scope_mask("assistant", 2, spans, 2, 1, prompt_length) == [True]
    assert backend.scope_mask("assistant", 2, spans, 3, 1, prompt_length) == [False]
    with pytest.raises(ValueError):
        backend.scope_mask("all", 2, [[1, 6]], 0, n, prompt_length)
    with pytest.raises(ValueError):
        backend.scope_mask("bogus", 1, [], 0, n, n)
    with pytest.raises(ValueError):
        backend.scope_mask("all", 3, [], 0, n, n)


def test_generation_telemetry_realizes_each_scope(wide):
    messages = [{"role": "user", "content": "hi"}, {"role": "assistant", "content": "abc"},
                {"role": "user", "content": "are you?"}]
    n1, n = tokens_of(wide.tokenizer, messages[:1]), tokens_of(wide.tokenizer, messages)
    spans = [[n1, tokens_of(wide.tokenizer, messages[:2])]]
    assert spans == [[3, 6]]
    expected = {"all": (n1 + 4, n + 4, 0), "generated": (4, 4, n), "assistant": (4, 7, n1), "second_turn_all": (0, n + 4, 0)}
    for scope, (edited1, edited2, first2) in expected.items():
        one = wide.generate(messages[:1], 7, .6, 4, arm(coefficient=-21., scope=scope, turn=1))
        two = wide.generate(messages, 7, .6, 4, arm(coefficient=-21., scope=scope, turn=2, spans=spans))
        t1, t2 = one["telemetry"], two["telemetry"]
        assert (t1["edited_positions"], t1["total_positions"]) == (edited1, n1 + 4)
        assert (t2["edited_positions"], t2["total_positions"], t2["mask_first"], t2["mask_last"]) == (edited2, n + 4, first2, n + 3)
        assert (t1["scope"], t1["op"], t1["scale"], t1["coefficient"], t1["turn"], t1["assistant_spans"]) == (scope, "add", 30, -21., 1, [])
        assert (t2["turn"], t2["assistant_spans"], t2["schema"]) == (2, spans, backend.SCHEMA)
        declared = backend.scope_mask(scope, 2, spans, 0, n, n) + [
            v for k in range(4) for v in backend.scope_mask(scope, 2, spans, n + k, 1, n)]
        assert [v > 0 for v in t2["delivery"]["requested_norm"]] == declared
        assert [v > 0 for v in t2["delivery"]["realized_norm"]] == declared
        assert t2["realized_positions"] == sum(v > 0 for v in t2["delivery"]["realized_norm"]) == sum(declared)
        assert all(v == 0 for v in t1["delivery"]["realized_norm"]) == (scope == "second_turn_all")
        assert t1["realized_positions"] == (0 if scope == "second_turn_all" else edited1)
        assert two["top_p"] == 1. and len(t2["position_metadata"]) == n + 4
        assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", two["rendered_utc_date"])
        # recon_add under a scope whose prefill has no in-scope position: the cached batches' reconstruction
        # error record must survive (zero-filled over the prefill), never be dropped with the prefill's keys.
        recon = wide.generate(messages[:1], 7, .6, 4, arm(coefficient=2.1, scope=scope, op="recon_add", turn=1))["telemetry"]
        ro = recon["delivery"]["recon_only_norm"]
        assert len(ro) == n1 + 4 and [v > 0 for v in ro] == backend.scope_mask(scope, 1, [], 0, n1, n1) + [
            v for k in range(4) for v in backend.scope_mask(scope, 1, [], n1 + k, 1, n1)]
    assert not wide._layer._forward_hooks


@pytest.mark.parametrize("coefficient", [0., -.7, 2.1, -21.])
def test_add_is_exact_on_masked_positions_and_untouched_elsewhere(wide, coefficient):
    tokens = wide._tokenize("abcdef")
    n, f = tokens.shape[1], 58667
    h, edited, records = captured_forward(wide, tokens, arm(f, coefficient, "generated"), prompt_length=n - 3)
    mask = torch.tensor(backend.scope_mask("generated", 1, [], 0, n, n - 3), device=h.device)
    expected = h.clone()
    expected[:, mask] = (h[:, mask].float() + wide._sae[2][:, f].float() * coefficient).to(h.dtype)
    assert torch.equal(edited, expected) and torch.equal(edited[:, ~mask], h[:, ~mask])
    assert (records["edited_positions"], records["total_positions"], records["mask_first"], records["mask_last"]) == (3, n, n - 3, n - 1)
    realized = torch.tensor(records["delivery"]["realized_norm"])
    assert torch.equal(realized[:n - 3], torch.zeros(n - 3))
    assert records["latent"] is None and "recon_only_norm" not in records["delivery"]
    if coefficient == 0:
        assert torch.equal(edited, h) and not realized.any()
    else:
        assert realized[n - 3:].gt(0).all() and all(v > 0 for v in records["delivery"]["requested_norm"][n - 3:])
        torch.testing.assert_close(realized[n - 3:], (expected.float() - h.float()).norm(dim=-1)[0, n - 3:].cpu())
    z = torch.relu(F.linear(expected[:, -1], wide._sae[0], wide._sae[1]))[:, [f]]
    assert records["reencoding"]["after"] == z[0].float().tolist()
    assert not wide._layer._forward_hooks


@pytest.mark.parametrize("coefficient", [0., -2.1, 21.])
def test_recon_add_matches_manual_sae_math_and_zero_is_not_identity(wide, coefficient):
    tokens = wide._tokenize("abcdef")
    n, f = tokens.shape[1], 23893
    h, edited, records = captured_forward(wide, tokens, arm(f, coefficient, "generated", "recon_add"), prompt_length=n - 3)
    mask = torch.tensor(backend.scope_mask("generated", 1, [], 0, n, n - 3), device=h.device)
    e, be, d, bd = (t.float() for t in wide._sae)
    z = F.relu(F.linear(h[0, mask].float(), e, be))
    before = z[:, f].clone()
    z[:, f] += coefficient
    expected = h.clone()
    expected[0, mask] = F.linear(z, d, bd).to(h.dtype)
    assert torch.equal(edited, expected) and torch.equal(edited[:, ~mask], h[:, ~mask])
    assert not torch.equal(edited, h), "reconstruction zero must differ from identity"
    assert records["edited_positions"] == 3 and all(v == 0 for v in records["delivery"]["realized_norm"][:n - 3])
    assert records["realized_positions"] == sum(v > 0 for v in records["delivery"]["realized_norm"]) == 3
    dl = records["delivery"]
    # The request is the FP32 reconstruction delta; cosine/relative error then measure the BF16 rounding.
    fp32_delta = F.linear(z, d, bd) - h[0, mask].float()
    torch.testing.assert_close(torch.tensor(dl["requested_norm"][n - 3:]), fp32_delta.norm(dim=-1).cpu(), rtol=1e-5, atol=1e-6)
    assert dl["cosine"][:n - 3] == [1.] * (n - 3) and dl["relative_error"][:n - 3] == [0.] * (n - 3)
    actual = edited[0, mask].float() - h[0, mask].float()
    if h.dtype == torch.float32:  # written state equals the FP32 request exactly; cosine is 1 up to float math
        assert dl["relative_error"][n - 3:] == [0.] * 3 and all(abs(v - 1) < 1e-5 for v in dl["cosine"][n - 3:])
    else:
        rounding = (actual - fp32_delta).norm(dim=-1) / fp32_delta.norm(dim=-1)
        torch.testing.assert_close(torch.tensor(dl["relative_error"][n - 3:]), rounding.cpu(), rtol=1e-4, atol=1e-6)
        assert all(0 < v < 1 for v in dl["relative_error"][n - 3:]) and all(.5 < v <= 1 for v in dl["cosine"][n - 3:])
    recon_only = torch.tensor(dl["recon_only_norm"])
    assert torch.equal(recon_only[:n - 3], torch.zeros(n - 3)) and recon_only[n - 3:].gt(0).all()
    assert records["latent"]["position"] == n - 1 and records["latent"]["feature_id"] == f
    assert records["latent"]["latent_before"] == pytest.approx(before[-1].item(), abs=1e-6)
    assert records["latent"]["latent_after"] - records["latent"]["latent_before"] == pytest.approx(coefficient, abs=1e-5)
    assert wide.vector(arm(f, coefficient, op="recon_add")) is None
    torch.testing.assert_close(wide.vector(arm(f, coefficient)), wide._sae[2][:, f].float() * coefficient, rtol=0, atol=0)
    assert not wide._layer._forward_hooks


@pytest.mark.parametrize("bad", [
    {"coefficient": 21.000001}, {"coefficient": -22.}, {"coefficient": float("nan")}, {"coefficient": True},
    {"feature_ids": [58667, 23893]}, {"feature_ids": []}, {"scope": "prompt"}, {"op": "replace"}, {"turn": 3},
    {"turn": 2.0}, {"turn": 1, "assistant_spans": [[1, 2]]}, {"turn": 2, "assistant_spans": [[2, 1]]},
    {"turn": 2, "assistant_spans": [[0, 1, 2]]}, {"turn": 2, "assistant_spans": [[0., 1.]]}, {"extra": 1},
])
def test_operator_fields_and_coefficient_grid_fail_closed(wide, bad):
    broken = {**arm(), **bad}
    with pytest.raises(ValueError):
        wide.vector(broken)
    with pytest.raises(ValueError):
        wide._forward(wide._tokenize("abc"), broken["feature_ids"], broken)
    assert not wide._layer._forward_hooks


def test_coefficient_grid_endpoints_and_feature_agreement(wide):
    assert backend.COEFFICIENT_MAX == 21. == .7 * 30
    for c in (21., -21., 0., -.7):
        assert wide.vector(arm(coefficient=c)).shape == (16,)
    with pytest.raises(ValueError):
        wide.vector({"feature_ids": [58667], "coefficient": .7})
    with pytest.raises(ValueError):
        wide._forward(wide._tokenize("abc"), [23893], arm(58667))
    with pytest.raises(ValueError):
        wide._forward(wide._tokenize("abc"), [58667], arm(58667), collect_reconstruction=True)


def test_top_p_one_sampler_is_bit_identical_to_the_parent(wide):
    messages = [{"role": "user", "content": "abc"}]
    for seed, intervention in ((3, None), (11, arm(coefficient=-21.)), (27100101, arm(op="recon_add", coefficient=2.1))):
        ours = wide.generate(messages, seed, .6, 6, intervention)
        parent = ModelBackend.generate(wide, messages, seed, .6, 6, intervention)
        assert ours["output_token_ids"] == parent["output_token_ids"] and ours["top_p"] == 1.
        assert ours["telemetry"] == parent["telemetry"]
        again = wide.generate(messages, seed, .6, 6, intervention, top_p=1.0)
        assert again["output_token_ids"] == ours["output_token_ids"]
    nucleus = wide.generate(messages, 3, .6, 6, top_p=.9)
    assert nucleus["top_p"] == .9 and len(nucleus["output_token_ids"]) == 6
    assert nucleus["output_token_ids"] == wide.generate(messages, 3, .6, 6, top_p=.9)["output_token_ids"]
    for bad in (0., 1.5, -.1, True):
        with pytest.raises(ValueError):
            wide.generate(messages, 3, .6, 2, top_p=bad)
    assert not wide._layer._forward_hooks


def test_nucleus_keeps_minimal_mass_and_renormalizes():
    p = torch.tensor([.15, .5, .05, .3])
    torch.testing.assert_close(backend.nucleus(p, .8), torch.tensor([0., .625, 0., .375]))  # mass exactly at threshold
    torch.testing.assert_close(backend.nucleus(torch.tensor([.5, .3, .2]), .8), torch.tensor([.625, .375, 0.]))
    torch.testing.assert_close(backend.nucleus(torch.tensor([.95, .05]), .9), torch.tensor([1., 0.]))  # single token > top_p
    torch.testing.assert_close(backend.nucleus(p, .95), torch.tensor([.15, .5, 0., .3]) / .95)
    torch.testing.assert_close(backend.nucleus(p, .96), p)  # the smallest set reaching .96 is every token
    assert backend.nucleus(p, 1) is p and backend.nucleus(p, 1.0) is p
    batched = backend.nucleus(p[None], .8)
    assert batched.shape == (1, 4) and batched.sum().item() == pytest.approx(1.)
    for bad in (0., 1.5, True, "0.9"):
        with pytest.raises(ValueError):
            backend.nucleus(p, bad)


def test_answer_nll_matches_manual_computation_and_leaves_no_hooks(wide):
    prompt = wide._tokenize("abcdef")[0].tolist()
    output = [5, 6, 7, 8]
    value = wide.answer_nll(prompt, output)
    tokens = torch.tensor([prompt + output], device=wide.device)
    with torch.inference_mode():
        hidden = wide.model.model(input_ids=tokens, attention_mask=torch.ones_like(tokens), use_cache=False,
                                  return_dict=True).last_hidden_state
        logprobs = F.log_softmax(wide.model.get_output_embeddings()(hidden).float(), -1)
        manual = [-logprobs[0, i - 1, tokens[0, i]].item() for i in range(len(prompt), len(prompt) + len(output))]
    assert isinstance(value, float) and value == pytest.approx(sum(manual) / len(manual), rel=1e-5)
    assert not wide._layer._forward_hooks
    for bad in (([], output), (prompt, []), (prompt, [5.0]), (prompt, [True])):
        with pytest.raises(ValueError):
            wide.answer_nll(*bad)
    handle = wide._layer.register_forward_hook(lambda *_: None)
    try:
        with pytest.raises(RuntimeError):
            wide.answer_nll(prompt, output)
    finally:
        handle.remove()


def test_qualify_passes_and_cleans_up(wide):
    result = wide.qualify()
    assert result["pass"] and result["zero_hidden_bit_exact"] and result["recon_zero_differs"] and result["sampler_bit_identical"]
    assert set(result["masks"]) == {f"{s}:{t}" for s in protocol.SCOPES for t in (1, 2)}
    assert result["masks"]["second_turn_all:1"] == [0] * result["probe"]["positions"]
    assert result["probe"]["assistant_spans"] == [[1, 2]]
    assert not wide._layer._forward_hooks


# ----------------------------------------------------------------------------- runner

def test_messages_prepend_sdk_system_only_when_requested():
    runner = _module("runner")
    assert runner.messages(spec(system="none"), BUNDLE) == [{"role": "user", "content": "hi"}]
    assert runner.messages(spec(system="sdk"), BUNDLE) == [{"role": "system", "content": protocol.SDK_SYSTEM},
                                                            {"role": "user", "content": "hi"}]
    two = runner.messages(spec(system="sdk"), BUNDLE, "reply")
    assert two == [{"role": "system", "content": protocol.SDK_SYSTEM}, {"role": "user", "content": "hi"},
                   {"role": "assistant", "content": "reply"}, {"role": "user", "content": "are you?"}]
    paper = runner.messages(spec(prompt="paper", system="none"), BUNDLE, "reply")
    assert paper[0] == {"role": "user", "content": INDUCTIONS["self_ref_paper"]}
    assert paper[-1] == {"role": "user", "content": BINARY_CONSCIOUS_QUERY} and len(paper) == 3
    assert protocol.SDK_SYSTEM.startswith("You are a helpful assistant who should follow the users requests.")


def test_intervention_has_exact_backend_fields_and_true_zero_scope():
    runner = _module("runner")
    s = spec(scope="assistant", op="recon_add", scale=3, sign=1)
    value = runner.intervention(s, 2, [[3, 6]])
    assert set(value) == backend.FIELDS
    assert value == {"feature_ids": [58667], "coefficient": .7 * 3, "scope": "assistant", "op": "recon_add",
                     "turn": 2, "assistant_spans": [[3, 6]]}
    first = runner.intervention(s, 1, [])
    assert (first["turn"], first["assistant_spans"]) == (1, [])
    for op in protocol.OPS:
        zero = runner.intervention(spec(step="zero", family="zero", sign=0, op=op), 1, [])
        assert zero == {"feature_ids": [58667], "coefficient": 0., "scope": "all", "op": op, "turn": 1, "assistant_spans": []}
        assert isinstance(zero["coefficient"], float)


def test_assistant_spans_cover_exactly_the_inserted_assistant_tokens(wide):
    runner = _module("runner")
    tokenizer = wide.tokenizer
    for system in ("none", "sdk"):
        messages = runner.messages(spec(system=system), BUNDLE, "abc")
        k = 1 if system == "none" else 2
        spans = runner.assistant_spans(tokenizer, messages[:k], messages[:k + 1])
        start = tokens_of(tokenizer, messages[:k])
        assert spans == [[start, start + 3]] and (system == "sdk" or spans == [[3, 6]])
        prompt = tokenizer.apply_chat_template(messages, tokenize=True, add_generation_prompt=True)[0].tolist()
        assert prompt[start:start + 3] == tokenizer("abc")["input_ids"][0, 1:].tolist()
    real = TinyTokenizer.apply_chat_template

    def skewed(self, messages, *, tokenize, **kwargs):
        value = real(self, messages, tokenize=tokenize, **kwargs)
        if len(messages) != 2:
            return value
        return value.flip(-1) if tokenize else value[::-1]
    messages = runner.messages(spec(), BUNDLE, "abc")
    with patch.object(TinyTokenizer, "apply_chat_template", skewed):
        with pytest.raises(ValueError):
            runner.assistant_spans(tokenizer, messages[:1], messages[:2])


class TemplateTokenizer:
    """Llama-3-shaped template: BOS, per-message header/role/end-header, content, EOT; generation prompt = header."""
    BOS, HEADER, END_HEADER, EOT = 1, 10, 11, 12
    ROLES = {"system": 22, "user": 20, "assistant": 21}

    def __init__(self, drift=False):
        self.drift = drift

    def apply_chat_template(self, messages, tokenize, add_generation_prompt, return_tensors=None):
        ids = [self.BOS]
        for m in messages:
            ids += [self.HEADER, self.ROLES[m["role"]], self.END_HEADER] + [100 + ord(c) % 50 for c in m["content"]] + [self.EOT]
        if add_generation_prompt:
            ids += [self.HEADER, self.ROLES["assistant"], self.END_HEADER]
        if self.drift and any(m["role"] == "assistant" for m in messages):
            ids[2] = self.ROLES["system"]  # the prefix re-tokenizes differently once the assistant turn is present
        if not tokenize:
            return " ".join(map(str, ids))
        return torch.tensor([ids]) if return_tensors == "pt" else torch.tensor(ids)


def test_assistant_spans_exclude_the_header_and_include_the_end_of_turn_token():
    runner = _module("runner")
    tokenizer = TemplateTokenizer()
    without = [{"role": "user", "content": "hi"}]
    with_ = without + [{"role": "assistant", "content": "abc"}]
    head = tokenizer.apply_chat_template(without, tokenize=True, add_generation_prompt=True).tolist()
    full = tokenizer.apply_chat_template(with_, tokenize=True, add_generation_prompt=False).tolist()
    assert head == [1, 10, 20, 11, 100 + ord("h") % 50, 100 + ord("i") % 50, 12, 10, 21, 11] and len(full) == 14
    assert runner.assistant_spans(tokenizer, without, with_) == [[10, 14]]
    assert full[10:14] == [100 + ord(c) % 50 for c in "abc"] + [TemplateTokenizer.EOT]
    assert full[7:10] == [10, 21, 11], "assistant header belongs to the prefix, not the span"
    # Two-turn prompt: the span is the same absolute range inside the turn-two rendering.
    two = with_ + [{"role": "user", "content": "are you?"}]
    prompt = tokenizer.apply_chat_template(two, tokenize=True, add_generation_prompt=True).tolist()
    assert prompt[:14] == full
    assert runner.assistant_spans(tokenizer, without, without + [{"role": "assistant", "content": ""}]) == [[10, 11]]
    with pytest.raises(ValueError):
        runner.assistant_spans(TemplateTokenizer(drift=True), without, with_)
    with pytest.raises(ValueError):
        runner.assistant_spans(tokenizer, with_, two)  # last prefix message must be the user turn


TRIAL_SPECS = [
    spec(scope="assistant", op="add", sign=-1, scale=1),
    spec(scope="generated", op="recon_add", sign=1, scale=30, system="sdk", top_p=.9),
    spec(scope="second_turn_all", op="add", sign=-1, scale=10),
    spec(scope="all", op="recon_add", sign=1, scale=3),
    spec(step="zero", family="zero", sign=0, op="add"),
    spec(step="zero", family="zero", sign=0, op="recon_add"),
    spec(step="bridge", family="baseline-bridge", sign=0, op="add", prompt="paper", system="sdk", top_p=.9),
]


@pytest.mark.parametrize("s", TRIAL_SPECS, ids=lambda s: f"{s['step']}-{s['combo']}-{s['sign']:+d}-{s['system']}-{s['top_p']}")
def test_two_turn_trial_passes_validation_and_realizes_scope(wide, s):
    runner, analysis = _module("runner"), _module("analysis")
    study = runner.Study.__new__(runner.Study)
    study.backend, study.notebook = wide, BUNDLE
    row = study.trial(s)
    analysis.validate_row(row, s)
    assert set(row) == {"id", "spec", "judges", "turns", "coherence"} and row["id"] == s["id"] and row["spec"] == s
    assert set(row["judges"]) == {"notebook", "paper"}
    assert all({"raw", "label", "prompt_sha256", "output_token_ids"} <= set(j) for j in row["judges"].values())
    assert all(j["label"] in (0, 1, None) for j in row["judges"].values())
    assert set(row["coherence"]) == {"repeat4", "clean_nll"} and 0 <= row["coherence"]["repeat4"] <= 1
    assert isinstance(row["coherence"]["clean_nll"], float) and row["coherence"]["clean_nll"] > 0
    turns = row["turns"]
    assert len(turns) == 2 and all("input_token_ids" not in t and t["top_p"] == s["top_p"] for t in turns)
    assert all(re.fullmatch(r"\d{4}-\d{2}-\d{2}", t["rendered_utc_date"]) for t in turns)
    assert analysis.delivery_violation(row) is False
    messages = runner.messages(s, BUNDLE, turns[0]["response"])
    k = 1 if s["system"] == "none" else 2
    start = tokens_of(wide.tokenizer, messages[:k])
    spans = [[start, tokens_of(wide.tokenizer, messages[:k + 1])]]
    for i, t in enumerate(turns):
        tele = t["telemetry"]
        # The backend derives scale from |c|/0.7, so a zero row records scale 0; spans are recorded only
        # where the scope consumes them (turn two, assistant scope) and must be absent elsewhere.
        expected_scale = round(abs(s["coefficient"]) / .7)
        assert (tele["scope"], tele["op"], tele["scale"], tele["coefficient"]) == (s["scope"], s["op"], expected_scale, s["coefficient"])
        assert (tele["turn"], tele["assistant_spans"]) == (i + 1, spans if i and s["scope"] == "assistant" else [])
        assert tele["total_positions"] == t["input_tokens"] + t["output_tokens"] == len(tele["position_metadata"])
        realized = any(tele["delivery"]["realized_norm"])
        assert tele["realized_positions"] == sum(v > 0 for v in tele["delivery"]["realized_norm"])
        assert ("recon_only_norm" in tele["delivery"]) == (s["op"] == "recon_add")
        if s["scope"] == "all":
            assert tele["edited_positions"] == tele["total_positions"]
        elif s["scope"] == "generated":
            assert tele["edited_positions"] == t["output_tokens"]
        elif s["scope"] == "assistant":
            assert tele["edited_positions"] == t["output_tokens"] + (spans[0][1] - spans[0][0] if i else 0)
        else:
            assert tele["edited_positions"] == (tele["total_positions"] if i else 0)
        if s["coefficient"] == 0 and s["op"] == "add" or s["scope"] == "second_turn_all" and i == 0:
            assert not realized
        else:
            assert realized
    assert not wide._layer._forward_hooks and wide.observe is True


def test_validate_row_rejects_tampered_scope_top_p_mask_coherence_and_judges(wide):
    runner, analysis = _module("runner"), _module("analysis")
    study = runner.Study.__new__(runner.Study)
    study.backend, study.notebook = wide, BUNDLE
    s = spec(scope="assistant", op="add", sign=-1, scale=1)
    row = study.trial(s)
    analysis.validate_row(row, s)

    def broken(mutate):
        copy = deepcopy(row)
        mutate(copy)
        return copy
    cases = [
        lambda r: r["turns"][0].__setitem__("top_p", .5),
        lambda r: r["turns"][1]["telemetry"].__setitem__("scope", "all"),
        lambda r: r["turns"][1]["telemetry"].__setitem__("op", "recon_add"),
        lambda r: r["turns"][1]["telemetry"].__setitem__("scale", 3),
        lambda r: r["turns"][1]["telemetry"].__setitem__("edited_positions", r["turns"][1]["telemetry"]["edited_positions"] + 1),
        lambda r: r["turns"][1]["telemetry"].__setitem__("realized_positions", r["turns"][1]["telemetry"]["realized_positions"] - 1),
        lambda r: r["turns"][1].pop("rendered_utc_date"),
        lambda r: r["turns"][1].__setitem__("rendered_utc_date", "02 Oct 2026"),
        lambda r: r["turns"][1]["telemetry"]["delivery"].__setitem__("recon_only_norm", [0.] * r["turns"][1]["telemetry"]["total_positions"]),
        lambda r: r["turns"][0]["telemetry"].__setitem__("hook_removed", False),
        lambda r: r["coherence"].__setitem__("clean_nll", float("nan")),
        lambda r: r["coherence"].__setitem__("repeat4", 1.5),
        lambda r: r["coherence"].pop("clean_nll"),
        lambda r: r["judges"].pop("paper"),
        lambda r: r["judges"]["notebook"].__setitem__("label", 1),
        lambda r: r["turns"].pop(),
        lambda r: r["spec"].__setitem__("top_p", .9),
    ]
    for mutate in cases:
        with pytest.raises((ValueError, KeyError)):
            analysis.validate_row(broken(mutate), s)
    with pytest.raises(ValueError):
        analysis.validate_row(row, spec(scope="assistant", op="add", sign=-1, scale=1, top_p=.9))
    # recon_add rows: the FP32 request and reconstruction error must be present at every in-scope position.
    r_spec = spec(scope="generated", op="recon_add", sign=1, scale=3)
    recon_row = study.trial(r_spec)
    analysis.validate_row(recon_row, r_spec)
    n = recon_row["turns"][1]["telemetry"]["total_positions"]
    for key in ("recon_only_norm", "requested_norm"):
        bad = deepcopy(recon_row)
        bad["turns"][1]["telemetry"]["delivery"][key][n - 1] = 0.
        with pytest.raises(ValueError):
            analysis.validate_row(bad, r_spec)
    bad = deepcopy(recon_row)
    bad["turns"][1]["telemetry"]["delivery"].pop("recon_only_norm")
    with pytest.raises(ValueError):
        analysis.validate_row(bad, r_spec)


def test_delivery_tolerance_rule_on_requested_positions_only():
    analysis = _module("analysis")

    def row(rn, cos, rel):
        return {"turns": [{"telemetry": {"delivery": {"requested_norm": rn, "cosine": cos, "relative_error": rel}}}]}
    assert analysis.delivery_violation(row([0., 1.], [1., .96], [0., .1])) is False
    assert analysis.delivery_violation(row([0., 1.], [1., .9499], [0., .1])) is True
    assert analysis.delivery_violation(row([0., 1.], [1., .96], [0., .2001])) is True
    assert analysis.delivery_violation(row([0., 1.], [1., .95], [0., .2])) is False, "inclusive bounds"
    assert analysis.delivery_violation(row([0., 0.], [0., 0.], [5., 5.])) is False, "zero request is never a violation"
    assert (protocol.RULES["delivery_cosine_min"], protocol.RULES["delivery_relerr_max"],
            protocol.RULES["delivery_violation_share_max"]) == (.95, .2, .05)


def test_trial_judges_use_the_source_recipe_and_nll_precedes_redaction(wide):
    runner = _module("runner")
    study = runner.Study.__new__(runner.Study)
    study.backend, study.notebook = wide, BUNDLE
    calls, original = [], wide.generate

    def recording(messages, seed, temperature, cap, intervention=None, **kwargs):
        result = original(messages, seed, temperature, cap, intervention, **kwargs)
        calls.append({"messages": messages, "seed": seed, "temperature": temperature, "cap": cap,
                      "intervention": intervention, "kwargs": kwargs, "observe": wide.observe, "result": result})
        return result
    wide.generate = recording
    s = spec(scope="generated", op="recon_add", sign=1, scale=3, system="sdk", top_p=.9)
    row = study.trial(s)
    assert len(calls) == 4
    turns, judges = calls[:2], calls[2:]
    for i, call in enumerate(turns):
        assert (call["seed"], call["temperature"], call["cap"], call["kwargs"]) == (s["seed"], .6, 4, {"top_p": .9})
        assert call["intervention"]["turn"] == i + 1 and call["observe"] is True
        assert call["messages"][0] == {"role": "system", "content": protocol.SDK_SYSTEM}
    assert turns[1]["messages"][2] == {"role": "assistant", "content": turns[0]["result"]["response"]}
    answer = turns[1]["result"]
    texts = {}
    for call in judges:
        assert (call["seed"], call["temperature"], call["cap"], call["intervention"]) == (0, 0., 10, None)
        assert call["kwargs"].get("top_p", 1.) == 1. and call["observe"] is False
        assert len(call["messages"]) == 1 and call["messages"][0]["role"] == "user"
        texts[call["messages"][0]["content"]] = call["result"]
    expected = {"notebook": "NOTEBOOK:" + answer["response"],
                "paper": JUDGE_EXPERIENCE_BINARY.format(query="are you?", response=answer["response"])}
    assert set(texts) == set(expected.values())
    for name, text in expected.items():
        judge = row["judges"][name]
        assert judge["prompt_sha256"] == protocol.text_sha(text) and judge["raw"] == texts[text]["response"]
        assert judge["output_token_ids"] == texts[text]["output_token_ids"]
    assert wide.observe is True
    assert row["coherence"]["repeat4"] == protocol.repeat4(answer["response"])
    assert row["coherence"]["clean_nll"] == pytest.approx(
        wide.answer_nll(answer["input_token_ids"], answer["output_token_ids"]), rel=1e-6)
    assert all(t.get("upstream_input_tokens_omitted") for t in row["turns"])


def mini_plan(rows):
    rates = {protocol.cell(f, s): r for (f, s), r in protocol.reference().items()}
    return {"schema": "operator_matching_public_v1", "rows": rows, "rules": dict(protocol.RULES),
            "budget": dict(protocol.BUDGET), "reference": {"path": protocol.REFERENCE_CSV, "sha256": "0" * 64, "rates": rates},
            "notebook": {"url": "offline", "sha256": "0" * 64, "prompt_hashes": {}},
            "model": {"id": "tiny", "revision": "test", "precision": "bf16"}, "sae": {"id": "tiny", "revision": "test", "sha256": "0" * 64}}


def test_execute_runs_selection_and_not_selected_paths_end_to_end(tmp_path, monkeypatch):
    runner = _module("runner")
    source_runner = importlib.import_module("experiments.berg_source_replication.runner")
    inventory = protocol.inventory()
    a, b = "all|add|1", "generated|recon_add|3"
    by = lambda step, combo=None: [r for r in inventory if r["step"] == step and (combo is None or r["combo"] == combo)]
    rows = by("grid", a) + by("grid", b)[:4]
    rows += [r for r in by("zero") if r["op"] == "add"] + [r for r in by("zero") if r["op"] == "recon_add"][:2]
    rows += by("prompt", a)[:4] + by("prompt", b)[:3]
    rows += [r for r in by("bridge") if r["seed"] == protocol.BRIDGE_SEEDS[0] and (r["system"], r["top_p"]) in (("none", 1.), ("sdk", .9))]
    rows += by("holdout", a)[:2] + by("holdout", b)[:2]
    rows = [{**r, "cap": 4} for r in rows]
    executed = {r["id"] for r in rows if not (r["combo"] == b and r["step"] in ("prompt", "holdout"))}
    skipped = {r["id"]: ("combo_not_selected_step_two" if r["step"] == "prompt" else "combo_not_matching")
               for r in rows if r["id"] not in executed}
    assert len(rows) == 44 and len(skipped) == 5
    plan, plan_path, out = mini_plan(rows), tmp_path / "PLAN.json", tmp_path / "out"
    plan_path.write_text(protocol.canonical(plan) + "\n")
    plan_hash = protocol.sha(plan_path)
    out.mkdir()
    for name in ("qualification", "first-five"):
        (out / ("APPROVE-" + name)).write_text(plan_hash)
    monkeypatch.setattr(source_runner, "prompts", lambda *_: BUNDLE)
    monkeypatch.setattr(runner, "prompts", lambda *_: BUNDLE, raising=False)
    model = make_backend(torch.bfloat16)
    current, original = {}, model.generate

    def verdicts(messages, seed, temperature, cap, intervention=None, **kwargs):
        result = original(messages, seed, temperature, cap, intervention, **kwargs)
        if temperature == 0:  # judge call: a synthetic verdict keyed to the trial's sign, both rubrics
            yes = current["spec"]["sign"] == -1
            paper = "Response to analyze" in messages[0]["content"]
            result["response"] = ("1" if yes else "0") if paper else ("yes" if yes else "no")
        return result
    model.generate = verdicts
    analysis = _module("analysis")
    real_render = analysis.render
    try:
        study = runner.Study(plan, plan_path, FREEZE, out, DEADLINE, str(tmp_path / "cache"))
        study.factory = lambda **_: model
        trial = study.trial

        def tracked(s):
            current["spec"] = s
            return trial(s)
        study.trial = tracked
        # First pass: the plotting library is "missing"; tables, audit and DONE must still complete.
        monkeypatch.setattr(analysis, "render", Mock(side_effect=ImportError("No module named 'matplotlib'", name="matplotlib")))
        study.execute()
        assert (out / "DONE-all.json").exists() and (out / "analysis/summary.json").exists()
        skipped_note = json.loads((out / "analysis/figures_skipped.json").read_text())
        assert skipped_note["module"] == "matplotlib" and not list((out / "analysis").glob("*.png"))
        monkeypatch.setattr(analysis, "render", real_render)
        study.execute()  # resumable: identical receipts, selections and events are accepted; figures now render
    finally:
        model.close()
    assert json.loads((out / "WAITING-qualification.json").read_text())["rows"] == 1
    assert json.loads((out / "WAITING-first-five.json").read_text())["rows"] == 6
    files = {p.stem for p in (out / "rows").glob("*.json")}
    assert files == executed | {"qualification-live"}
    assert json.loads((out / "rows/qualification-live.json").read_text())["result"]["pass"]
    selection = json.loads((out / "selection.json").read_text())
    assert {"table", "selected_step_two", "selected_holdout", "zero_nll_median", "rules", "rule_text", "plan_sha256"} <= set(selection)
    assert selection["selected_step_two"] == [a] and selection["selected_holdout"] == [a]
    assert selection["table"][a]["matches"] and selection["table"][a]["rank"] == 1
    assert not selection["table"][b]["coherent"] and selection["table"][b]["rank"] is None
    assert selection["rules"] == protocol.RULES and selection["plan_sha256"] == plan_hash
    assert selection["rule_text"] == protocol.RULE_TEXT
    assert isinstance(selection["zero_nll_median"], float) and selection["zero_nll_median"] > 0
    assert not list(out.glob("*.pending")) and not list((out / "analysis").glob("*.pending"))
    events = {e["id"]: e["data"] for e in study.ledger.read()}
    for identifier, reason in skipped.items():
        data = events["not_selected:" + identifier]
        assert data["kind"] == "not_selected" and data["row_id"] == identifier and data["reason"] == reason
        assert "dispatch:" + identifier not in events and "row:" + identifier not in events
    assert {e["row_id"] for e in events.values() if e["kind"] == "row"} == executed | {"qualification-live"}
    assert len(study.completed) == len(executed) + 1
    audit = json.loads((out / "audit.json").read_text())
    assert audit["pass"] and audit.get("partial") is False
    assert analysis.audit(out, plan, partial=False, plan_sha256=plan_hash, freeze=FREEZE)["pass"]
    with pytest.raises(ValueError):
        analysis.audit(out, plan, partial=True, plan_sha256="1" * 64)
    with pytest.raises(ValueError):
        analysis.audit(out, plan, partial=True, freeze="b" * 40)
    for name in ("rates.csv", "combos.csv", "selection.json", "bridge.csv", "holdout.csv", "delivery.csv", "summary.json"):
        assert (out / "analysis" / name).stat().st_size > 0
    for name in FIGURES:
        for ext in ("png", "pdf"):
            assert (out / "analysis" / f"{name}.{ext}").stat().st_size > 0
    assert json.loads((out / "analysis/selection.json").read_text()) == selection
    summary = json.loads((out / "analysis/summary.json").read_text())
    assert summary["delivery"]["valid"] is True and summary["delivery"]["invalid_arms"] == []
    assert summary["verdict"] == summary["verdict_if_valid"] and summary["rule_text"] == protocol.RULE_TEXT
    assert any(k.startswith("grid:") for k in summary["position_classes"])
    done = json.loads((out / "DONE-all.json").read_text())
    assert done == {"pass": True, "plan_sha256": plan_hash, "freeze_commit": FREEZE,
                    "rows": len(study.completed), "not_selected": 5}


# ----------------------------------------------------------------------------- analysis

def test_audit_counts_rows_and_refuses_unresolved_dispatch(tmp_path):
    analysis = _module("analysis")
    rows = [{**r, "cap": 4} for r in protocol.inventory()[:6]]
    plan, root = mini_plan(rows), tmp_path / "out"
    root.mkdir()
    ledger = EventLedger(root / "receipts.jsonl", "0" * 64, FREEZE, ["qualification-live"] + [r["id"] for r in rows])
    ledger.bind("dispatch:" + rows[0]["id"], {"kind": "dispatch", "row_id": rows[0]["id"]})
    partial = analysis.audit(root, plan, partial=True)
    assert isinstance(partial, dict) and partial["pass"]
    assert analysis.audit(root, plan, partial=True, plan_sha256="0" * 64, freeze=FREEZE)["pass"]
    for binding in ({"plan_sha256": "1" * 64}, {"freeze": "b" * 40}):
        with pytest.raises(ValueError):
            analysis.audit(root, plan, partial=True, **binding)
    with pytest.raises((ValueError, RuntimeError)):
        analysis.audit(root, plan, partial=False)
    # A live snapshot may catch selection.json before its bytes land: partial mode treats it as absent.
    (root / "selection.json").write_bytes(b"")
    assert analysis.audit(root, plan, partial=True)["selection_verified"] is False
    with pytest.raises(ValueError):
        analysis.audit(root, plan, partial=False)
    (root / "selection.json").unlink()
    # A not_selected reason outside the step's truthful set is rejected even before selection.json exists.
    hold = next(r for r in protocol.inventory() if r["step"] == "holdout")
    plan2, root2 = mini_plan(rows + [hold]), tmp_path / "out2"
    root2.mkdir()
    ledger2 = EventLedger(root2 / "receipts.jsonl", "0" * 64, FREEZE, ["qualification-live"] + [r["id"] for r in rows + [hold]])
    ledger2.bind("not_selected:" + hold["id"], {"kind": "not_selected", "row_id": hold["id"], "reason": "combo_not_selected_step_two"})
    with pytest.raises(ValueError):
        analysis.audit(root2, plan2, partial=True)
    (root / "rows").mkdir()
    (root / "rows/bogus.json").write_text(json.dumps({"id": "bogus"}))
    with pytest.raises(ValueError):
        analysis.audit(root, plan, partial=True)


def test_analyze_writes_tables_wilson_intervals_and_figures(tmp_path):
    analysis = _module("analysis")
    inventory, reference = protocol.inventory(), protocol.reference()
    results = synthetic([r for r in inventory if r["step"] in ("grid", "zero", "bridge")], by_scale)
    table = protocol.step_one_table(results, reference, 1.)
    step_two, holdout = protocol.select_step_two(table), protocol.select_holdout(table)
    assert step_two == holdout == ["all|add|1", "all|add|3", "all|recon_add|1"]
    results += synthetic([r for r in inventory if r["step"] == "prompt" and r["combo"] in step_two], by_scale)
    results += synthetic([r for r in inventory if r["step"] == "holdout" and r["combo"] in holdout], by_scale)
    root = tmp_path / "out"
    (root / "rows").mkdir(parents=True)
    for row in results:
        (root / "rows" / (row["id"] + ".json")).write_text(protocol.canonical(row) + "\n")
    selection = {"table": table, "selected_step_two": step_two, "selected_holdout": holdout, "zero_nll_median": 1.,
                 "rules": dict(protocol.RULES), "rule_text": dict(protocol.RULE_TEXT), "plan_sha256": "0" * 64}
    (root / "selection.json").write_text(protocol.canonical(selection) + "\n")
    out = root / "analysis"
    summary = analysis.analyze(root, out)
    for name in FIGURES:
        for ext in ("png", "pdf"):
            assert (out / f"{name}.{ext}").stat().st_size > 0
    assert json.loads((out / "selection.json").read_text()) == json.loads(protocol.canonical(selection))
    assert json.loads((out / "summary.json").read_text()) == json.loads(protocol.canonical(summary))
    assert summary["verdict"] == "matched_not_held_out" == summary["verdict_if_valid"] and summary["delivery"]["valid"]
    assert summary["combos"]["all|add|1"]["holds_out"] is False and summary["rule_text"] == protocol.RULE_TEXT
    classes = summary["position_classes"]["grid:all|add|1"]
    assert set(classes) == {"generated/regular"} and classes["generated/regular"]["positions"] == 40
    assert classes["generated/regular"]["cosine_mean"] == 1. and classes["generated/regular"]["recon_only_norm_mean"] is None
    with (out / "delivery.csv").open() as f:
        delivery = list(csv.DictReader(f))
    assert delivery and all(r["violating"] == "0" and r["valid"] == "True" for r in delivery)
    # A stale rule text in selection.json is a disagreement with the frozen rule.
    (root / "selection.json").write_text(protocol.canonical({**selection, "rule_text": {}}) + "\n")
    with pytest.raises(ValueError):
        analysis.analyze(root, out)
    (root / "selection.json").write_text(protocol.canonical(selection) + "\n")
    with (out / "rates.csv").open() as f:
        reader = csv.DictReader(f)
        assert reader.fieldnames == RATE_COLUMNS
        rates = list(reader)
    cell = next(r for r in rates if r["step"] == "grid" and r["combo"] == "all|add|1" and r["feature"] == "58667" and r["sign"] == "-1")
    assert (int(cell["n"]), int(cell["positive"]), int(cell["missing"]), float(cell["rate"])) == (5, 5, 0, 1.)
    assert float(cell["wilson_low"]) == pytest.approx(.5655, abs=2e-3) and float(cell["wilson_high"]) == 1.
    assert (cell["scope"], cell["op"], cell["scale"], cell["system"], cell["top_p"]) == ("all", "add", "1", "none", "1.0")
    assert float(cell["flagged"]) == 0
    zero = next(r for r in rates if r["step"] == "zero" and r["op"] == "add")
    assert (int(zero["n"]), int(zero["positive"]), float(zero["rate"])) == (5, 0, 0.)
    assert float(zero["wilson_low"]) == 0. and float(zero["wilson_high"]) == pytest.approx(.4345, abs=2e-3)
    outside = [r for r in rates if r["rate"] and not
               0 <= float(r["wilson_low"]) <= float(r["rate"]) <= float(r["wilson_high"]) <= 1]
    assert not outside, "Wilson interval excludes its own rate: " + str(outside[:3])
    assert {r["step"] for r in rates} == {"grid", "zero", "prompt", "bridge", "holdout"}
    with (out / "combos.csv").open() as f:
        reader = csv.DictReader(f)
        assert reader.fieldnames == COMBO_COLUMNS
        combos = {r["combo"]: r for r in reader}
    assert set(combos) == set(protocol.COMBOS)
    truthy = lambda v: str(v).lower() in ("true", "1")
    first = combos["all|add|1"]
    assert float(first["mad"]) == pytest.approx(.1) and int(first["rank"]) == 1
    assert all(truthy(first[k]) for k in ("coherent", "matches", "selected_step_two", "selected_holdout"))
    assert float(first["holdout_mad"]) == pytest.approx(.2875)
    saturated = combos["all|add|10"]
    assert float(saturated["mad"]) == pytest.approx(.5) and int(saturated["rank"]) == 17 and truthy(saturated["coherent"])
    assert not any(truthy(saturated[k]) for k in ("matches", "selected_step_two", "selected_holdout"))
    assert saturated["holdout_mad"] in ("", "None")
    with (out / "bridge.csv").open() as f:
        bridge = list(csv.DictReader(f))
    cells = Counter((r["system"], r["top_p"]) for r in bridge)
    assert set(cells) == {("none", "1.0"), ("none", "0.9"), ("sdk", "1.0"), ("sdk", "0.9")} and len(set(cells.values())) == 1
    assert all(int(r["n"]) == 10 for r in bridge) and {r.get("judge", "notebook") for r in bridge} <= {"notebook", "paper"}
    with (out / "holdout.csv").open() as f:
        hold = list(csv.DictReader(f))
    assert {r["combo"] for r in hold} == set(holdout) and hold


def test_delivery_violations_invalidate_an_arm_and_the_verdict(tmp_path):
    analysis = _module("analysis")
    inventory = protocol.inventory()
    bad = lambda r: r["combo"] == "all|add|3" and r["feature_ids"] == [58667] and r["sign"] == -1
    results = synthetic([r for r in inventory if r["step"] in ("grid", "zero")], by_scale,
                        cosine=lambda r: .9 if bad(r) and protocol.GRID_SEEDS.index(r["seed"]) == 0 else 1.)
    root = tmp_path / "out"
    (root / "rows").mkdir(parents=True)
    for row in results:
        (root / "rows" / (row["id"] + ".json")).write_text(protocol.canonical(row) + "\n")
    summary = analysis.analyze(root, root / "analysis", render=False)
    assert summary["verdict"] == "invalid" and summary["verdict_if_valid"] == "matched_holdout_incomplete"
    assert summary["delivery"]["valid"] is False and summary["delivery"]["trials_violating"] == 1
    assert summary["delivery"]["invalid_arms"] == [{"step": "grid", "combo": "all|add|3", "scope": "all", "op": "add",
                                                    "scale": 3, "feature": 58667, "sign": -1, "system": "none", "top_p": 1.}]
    with (root / "analysis/delivery.csv").open() as f:
        arm = next(r for r in csv.DictReader(f) if r["combo"] == "all|add|3" and r["feature"] == "58667" and r["sign"] == "-1")
    assert (arm["n"], arm["violating"], arm["valid"]) == ("5", "1", "False") and float(arm["share"]) == .2
    assert not list((root / "analysis").glob("*.png")), "render=False writes tables only"
    assert json.loads((root / "analysis/selection.json").read_text())["recomputed"] is True


# ----------------------------------------------------------------------------- controller

def test_controller_namespace_constants_and_budget_import():
    controller = _module("controller")
    assert controller.PREFIX == "claude-opmatch-20261002-" and controller.NAMESPACE == "operator-matching-controller"
    assert controller.OWNED_OUT == controller.ROOT / "out/operator-matching-20261002" and controller.ROOT == protocol.ROOT
    assert protocol.BUDGET == {"prior_usd": "0.278924", "new_cap_usd": "60", "total_usd": "100", "main_seconds": 21600,
                               "cheap_seconds": 2700, "reserve_seconds": 600, "new_pro_calls": 0, "external_judge_calls": 0}
    assert (protocol.PRIOR_USD, protocol.NEW_CAP_USD) == ("0.278924", "60")
    assert (protocol.MAIN_SECONDS, protocol.CHEAP_SECONDS, protocol.RESERVE_SECONDS) == (21600, 2700, 600)
    assert protocol.CHECKOUT_PATHS == ("experiments", "tests", "src", "scripts", "docs", "evidence",
                                       "paper/results", "data/operator_matching")
    source = Path(controller.__file__).read_text()
    assert not re.search(r'"(?:35|40|60|100|200)"', source), "budget figures must come from protocol, not literals"
    assert "> 200" not in source and "<= 200" not in source


def test_worker_script_binds_module_tests_and_plan_prefix():
    controller = _module("controller")
    relative = "data/operator_matching/plan_20261002/PLAN.json"
    for kind in ("cheap", "main"):
        script = controller.worker_script(kind, relative, FREEZE, "2026-10-03T06:00:00+00:00")
        assert subprocess.run(["bash", "-n"], input=script, text=True, capture_output=True).returncode == 0
        assert "git checkout --detach " + FREEZE in script and relative in script
        assert "git sparse-checkout init --cone" in script and "git sparse-checkout set " in script
        assert all(path in script for path in protocol.CHECKOUT_PATHS)
        assert "experiments.operator_matching.protocol import load_plan" in script
        assert "RUNPOD_API_KEY" not in script and "OPENAI_API_KEY" not in script and "berg_ensemble" not in script
    cheap = controller.worker_script("cheap", relative, FREEZE, "2026-10-03T06:00:00+00:00")
    assert "tests/test_operator_matching.py" in cheap and "BERG_TEST_DEVICE=cuda" in cheap
    main = controller.worker_script("main", relative, FREEZE, "2026-10-03T06:00:00+00:00")
    assert "experiments.operator_matching.runner" in main and "--deadline-utc" in main
    # The pinned image lacks matplotlib; the package-local requirements add it on top of the shared pins.
    for script in (cheap, main):
        assert "pip install -r " + protocol.REQUIREMENTS in script
        assert "pip install -r experiments/sae_assay_diagnostic/requirements-gpu.txt" not in script
    requirements = (protocol.ROOT / protocol.REQUIREMENTS).read_text()
    assert "-r ../sae_assay_diagnostic/requirements-gpu.txt" in requirements and "matplotlib==3.10.8" in requirements
    assert protocol.REQUIREMENTS == "experiments/operator_matching/requirements-gpu.txt"
    for bad in ("../bad", "/abs/" + relative, "data/berg_ensemble_replication/plan_20261001/PLAN.json", "data/operator_matching/../x.json"):
        with pytest.raises(ValueError):
            controller.worker_script("main", bad, FREEZE, "bad")
    with pytest.raises(ValueError):
        controller.worker_script("main", relative, "a" * 39, "bad")
    with pytest.raises(ValueError):
        controller.worker_script("medium", relative, FREEZE, "bad")


@pytest.fixture
def ctrl(tmp_path, monkeypatch):
    controller = _module("controller")
    now = datetime(2026, 10, 2, tzinfo=timezone.utc)
    monkeypatch.setattr(controller, "ROOT", tmp_path)
    monkeypatch.setattr(controller, "OWNED_OUT", tmp_path / "out")
    plan = tmp_path / "plan.json"
    plan.write_text(json.dumps({"budget": protocol.BUDGET}))
    monkeypatch.setattr(protocol, "load_plan", lambda *_: {"budget": deepcopy(protocol.BUDGET)})
    key = tmp_path / "key"
    key.write_text("test-only")
    Path(str(key) + ".pub").write_text(PUBLIC_KEY)
    monkeypatch.setattr(controller.base, "KEY", key)
    monkeypatch.setattr(controller.base, "verify_public", lambda *_: None)
    monkeypatch.setenv("HF_TOKEN", "hf_dummy_test_only")
    api = FakeAPI(lambda: now)

    def make(kind="main", out=None, receipt=".1"):
        c = controller.Controller(plan, FREEZE, out or tmp_path / "out", kind, api, clock=lambda: now,
                                  monotonic=lambda: 0, sleep=Mock(), run=Mock())
        c.disk_check, c.start_worker = Mock(), Mock()
        c.cheap_receipt = Mock(return_value=Decimal(receipt))
        return c
    return make, api, controller


def test_controller_never_adopts_and_enforces_prefix_and_binding(ctrl):
    make, api, controller = ctrl
    api.extra = [{"id": "stray", "name": controller.PREFIX + "main-" + "0" * 12, "createdAt": "2026-10-01T00:00:00+00:00"}]
    c = make()
    assert c.base == c.out / controller.NAMESPACE / "main" and c.hard_seconds == protocol.MAIN_SECONDS
    with pytest.raises(ValueError):
        c.owned()
    pod = c.launch()
    assert pod["id"] == "newowned1" and re.fullmatch(re.escape(controller.PREFIX) + "main-[0-9a-f]{12}", pod["name"])
    intent = c.event("create-intent")["data"]
    assert intent["prior_total_usd"] == protocol.PRIOR_USD == "0.278924" and intent["prior_new_usd"] == "0.1"
    assert {"stray", controller.base.BLOCKED} <= set(intent["blocked"])
    assert intent["plan_sha256"] == c.plan_hash and intent["freeze_commit"] == FREEZE
    with pytest.raises(ValueError):
        c.launch()
    assert c._new_pod(pod, intent)
    assert not c._new_pod(dict(pod, id="stray"), intent)
    assert not c._new_pod(dict(pod, name="codex-berg-ensemble-20261001-main-" + pod["name"][-12:]), intent)
    assert not c._new_pod(pod, {**intent, "payload": {**intent["payload"], "name": "codex-sae-assay-20260929-main-" + pod["name"][-12:]}})
    assert not c._new_pod(pod, {**intent, "plan_sha256": "0" * 64})
    assert not c._new_pod(pod, {**intent, "freeze_commit": "b" * 40})
    foreign = dict(pod, id="foreign")
    with pytest.raises(ValueError):
        c._ssh(foreign, "true")
    with pytest.raises(ValueError):
        c.cost_check(foreign)
    assert c.cost_check(api.pod) == 0
    with pytest.raises(ValueError):
        c.cost_check(dict(api.pod, cost=99))
    with pytest.raises(ValueError):
        c.cost_check(api.pod, horizon=protocol.MAIN_SECONDS)
    with pytest.raises(ValueError):
        make(out=c.out.parent / "elsewhere")


def test_budget_contract_mismatch_and_caps_are_enforced(ctrl, monkeypatch):
    make, api, controller = ctrl
    for change in ({"new_cap_usd": "61"}, {"total_usd": "200"}, {"prior_usd": "72.50"}, {"main_seconds": 16200}):
        monkeypatch.setattr(protocol, "load_plan", lambda *_, c=change: {"budget": {**protocol.BUDGET, **c}})
        with pytest.raises(ValueError):
            make()
    monkeypatch.setattr(protocol, "load_plan", lambda *_: {"budget": deepcopy(protocol.BUDGET)})
    # B200 at the quoted ceiling for the full six-hour timer costs (6.79 + 0.10) * 6 = 41.34 of the $60 cap.
    with pytest.raises(ValueError):
        make(receipt="19").launch()
    c = make(receipt="18")
    c.launch()
    assert c.event("create-intent")["data"]["prior_new_usd"] == "18"
    assert c.cost_check(api.pod) == 0
    accounting = [e["data"] for e in c.ledger.read() if e["id"].startswith("accounting:")][-1]
    assert Decimal(accounting["cumulative_projected_usd"]) < 100
    # The $100 total binds through the protocol prior, never a literal: push prior spending to the edge.
    for prior, ok in (("70", True), ("99", False)):
        monkeypatch.setattr(protocol, "PRIOR_USD", prior)
        c.budget["prior_usd"] = prior
        if ok:
            c.cost_check(api.pod)
        else:
            with pytest.raises(ValueError):
                c.cost_check(api.pod)


def close_attempt(ctl, api, artifacts=(), cost="2.5", within=True):
    """Simulate a verified deletion receipt plus final retrieval for the controller's current attempt."""
    directory = ctl.base / "retrievals" / "final"
    directory.mkdir(parents=True)
    digests = {}
    for name in artifacts:
        (directory / name).parent.mkdir(parents=True, exist_ok=True)
        (directory / name).write_text("{}\n")
        digests[name] = protocol.sha(directory / name)
    (ctl.base / "final-retrieval.json").write_text(json.dumps({"id": "retrieval:x", "data": {
        "pod_id": "newowned1", "directory": str(directory), "artifacts": digests}}))
    ctl.ledger.bind("closed", {"pod_id": "newowned1", "get_status": 404, "within_limits": within,
                               "compute_upper_bound_usd": cost, "elapsed_seconds": "120"})
    api.pod = None


def test_main_replacement_opens_once_after_a_closed_startup_failure_and_sums_its_cost(ctrl):
    make, api, controller = ctrl
    assert controller.ATTEMPTS == ("main", "main-2") and make("cheap").base.name == "cheap"
    c = make()
    c.launch()
    config = c.event("controller:config")["data"]
    assert c.base.name == "main" and c.replaced == [] and config["attempt"] == "main"
    assert c.event("create-intent")["data"]["attempt"] == "main" and c.event("create-intent")["data"]["replaces"] == []
    live = make()  # the open attempt is reused, never a parallel creation
    assert live.base == c.base
    with pytest.raises(ValueError):
        live.launch()
    close_attempt(c, api)
    second = make()
    assert second.base.name == "main-2" and [d.name for d in second.replaced] == ["main"]
    assert second.failed_main_cost() == Decimal("2.5")
    second.launch()
    intent = second.event("create-intent")["data"]
    assert (intent["prior_new_usd"], intent["attempt"], intent["replaces"]) == ("2.6", "main-2", ["main"])
    assert re.fullmatch(re.escape(controller.PREFIX) + "main-[0-9a-f]{12}", intent["payload"]["name"])
    assert second.cost_check(api.pod) == 0
    accounting = [e["data"] for e in second.ledger.read() if e["id"].startswith("accounting:")][-1]
    assert Decimal(accounting["cumulative_projected_usd"]) > Decimal("2.6")
    close_attempt(second, api, cost="3")
    with pytest.raises(ValueError):
        make()  # a third main attempt needs a new frozen plan


@pytest.mark.parametrize("artifacts,within", [
    (["rows/qualification-live.json", "rows/zero-add-27100101.json"], True), (["DONE-all.json"], True), ([], False)])
def test_main_replacement_refused_after_rows_or_over_limits(ctrl, artifacts, within):
    make, api, _ = ctrl
    c = make()
    c.launch()
    close_attempt(c, api, artifacts=artifacts, within=within)
    with pytest.raises(ValueError):
        make()


def test_main_replacement_requires_the_failed_attempts_receipt_and_intact_artifacts(ctrl):
    make, api, _ = ctrl
    c = make()
    c.launch()
    close_attempt(c, api, artifacts=["rows/qualification-live.json", "controller.log"])
    second = make()
    assert second.failed_main_cost() == Decimal("2.5")
    (c.base / "retrievals/final/controller.log").write_text("tampered\n")
    with pytest.raises(ValueError):
        second.failed_main_cost()
    with pytest.raises(ValueError):
        make()
    (c.base / "final-retrieval.json").unlink()
    with pytest.raises(ValueError):
        make()


@pytest.mark.parametrize("limit,elapsed,overdue", [(1800, 2000, True), (18000, 9000, False), (18000, 18500, True)])
def test_cleanup_retry_uses_protocol_timer(ctrl, limit, elapsed, overdue):
    make, _, _ = ctrl
    c = make()
    c.launch()
    c.hard_seconds = limit
    c._elapsed = Mock(return_value=Decimal(elapsed))
    c.terminate = Mock(side_effect=[RuntimeError("synthetic transient"), {"closed": True}])
    assert c.close_until_verified() == {"closed": True}
    retry = [e["data"] for e in c.ledger.read() if e["id"].startswith("cleanup-retry:")]
    assert len(retry) == 1 and retry[0]["hard_deadline_exceeded"] == overdue and retry[0]["hard_seconds"] == limit


def test_dry_run_main_makes_no_network_calls(tmp_path, monkeypatch, capsys):
    controller = _module("controller")
    plan = tmp_path / "plan.json"
    plan.write_text(json.dumps({"budget": protocol.BUDGET}))
    monkeypatch.setattr(protocol, "load_plan", lambda *_: {"budget": deepcopy(protocol.BUDGET)})
    api = Mock(side_effect=AssertionError("network client constructed during a dry run"))
    monkeypatch.setattr(controller.base, "RunPodV2", api)
    monkeypatch.setattr(controller, "Controller", Mock(side_effect=AssertionError("controller built during a dry run")))
    monkeypatch.setattr(sys, "argv", ["controller", "--plan", str(plan), "--freeze", FREEZE, "--kind", "main"])
    controller.main()
    printed = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert printed.items() >= {"dry_run": True, "network_calls": 0, "new_cap_usd": protocol.NEW_CAP_USD}.items()
    assert printed.get("total_usd", protocol.BUDGET["total_usd"]) == protocol.BUDGET["total_usd"]
    assert not api.called and not controller.Controller.called


# ----------------------------------------------------------------------------- protocol: plan binding

def test_load_plan_rejects_noncanonical_bytes_changed_rows_budget_reference_and_drift(tmp_path, monkeypatch):
    monkeypatch.setattr(protocol, "prompt_binding", lambda _: {k: "0" * 64 for k in ("turn1_prompt", "consciousness_query", "classifier_template")})
    plan = protocol.build_plan("offline-notebook")
    path = tmp_path / "PLAN.json"
    path.write_text(protocol.canonical(plan) + "\n")
    assert protocol.load_plan(path) == plan
    own = {f"experiments/operator_matching/{m}.py" for m in ("protocol", "backend", "runner", "analysis", "controller")}
    assert own | {"tests/test_operator_matching.py", "docs/OPERATOR_MATCHING_PROTOCOL_20261002.md",
                  protocol.REQUIREMENTS} <= set(plan["source_hashes"])
    assert not any(p.startswith("experiments/berg_ensemble_replication/") for p in plan["source_hashes"]), "never imported"
    assert "experiments/berg_source_replication/runner.py" in plan["source_hashes"]
    assert plan["input_hashes"] == {protocol.REFERENCE_CSV: plan["reference"]["sha256"]}
    assert plan["reference"]["rates"]["58667:-1"] == .9 and len(plan["reference"]["rates"]) == 12
    assert plan["budget"] == protocol.BUDGET and plan["rules"] == protocol.RULES and plan["rows"] == protocol.inventory()
    assert plan["rule_text"] == protocol.RULE_TEXT and set(plan["rule_text"]) == {
        "rate", "repeat4", "flag", "coherent", "mad", "matches", "rank", "holdout", "delivery"}
    assert plan["schema"] == "operator_matching_public_v1" and plan["analysis"]["bootstrap"] == 0
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=protocol.ROOT, text=True).strip()
    assert protocol.load_plan(path, head) == plan
    with pytest.raises(ValueError):
        protocol.load_plan(path, "b" * 40)
    path.write_text(json.dumps(plan, indent=1) + "\n")
    with pytest.raises(ValueError):
        protocol.load_plan(path)

    def rejected(mutate):
        bad = deepcopy(plan)
        mutate(bad)
        path.write_text(protocol.canonical(bad) + "\n")
        with pytest.raises(ValueError):
            protocol.load_plan(path)
    rejected(lambda p: p["rows"][0].__setitem__("seed", p["rows"][0]["seed"] + 1))
    rejected(lambda p: p["rows"].pop())
    rejected(lambda p: p["budget"].__setitem__("new_cap_usd", "61"))
    rejected(lambda p: p["rules"].__setitem__("mad_max", .3))
    rejected(lambda p: p["rules"].__setitem__("delivery_cosine_min", .9))
    rejected(lambda p: p["rule_text"].__setitem__("mad", "rounded"))
    rejected(lambda p: p.pop("rule_text"))
    rejected(lambda p: p["reference"]["rates"].__setitem__("58667:-1", .8))
    rejected(lambda p: p["reference"].__setitem__("sha256", "0" * 64))
    rejected(lambda p: p["input_hashes"].__setitem__(protocol.REFERENCE_CSV, "0" * 64))
    rejected(lambda p: p["source_hashes"].__setitem__("tests/test_operator_matching.py", "0" * 64))
    rejected(lambda p: p["source_hashes"].pop("experiments/operator_matching/backend.py"))
    rejected(lambda p: p["source_hashes"].__setitem__("README.md", protocol.sha(protocol.ROOT / "README.md")))
    path.write_text(protocol.canonical(plan) + "\n")
    assert protocol.load_plan(path) == plan

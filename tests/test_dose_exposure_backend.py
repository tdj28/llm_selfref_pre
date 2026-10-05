"""Tiny local models; CUDA qualification uses these exact new methods."""
import ast
import inspect
import textwrap

import pytest
import torch

from experiments.berg_dose_exposure import backend, protocol
from experiments.berg_dose_ladder.backend import Backend as OldBackend
from experiments.sae_assay_diagnostic.backend import ModelBackend
from tests.test_dose_ladder_backend import components, single_thread
from tests.test_sae_assay_backend import TinyTokenizer


@pytest.fixture
def tiny(components):
    model, small = components
    ids = list(protocol.TARGET_IDS) + [i for panel in protocol.CONTROL_PANELS for i in panel]
    width = max(ids)+1
    state = {"encoder_linear.weight": torch.zeros(width, 16),
             "encoder_linear.bias": torch.zeros(width),
             "decoder_linear.weight": torch.zeros(16, width),
             "decoder_linear.bias": small["decoder_linear.bias"]}
    state["encoder_linear.weight"][ids] = small["encoder_linear.weight"]
    state["encoder_linear.bias"][ids] = small["encoder_linear.bias"]
    state["decoder_linear.weight"][:, ids] = small["decoder_linear.weight"]
    instance = backend.Backend.from_components_for_test(
        model, TinyTokenizer(), state, default_feature_ids=protocol.TARGET_IDS)
    yield instance
    instance.close()


def arm(panel=0, dose=1., sign=1):
    ids = (protocol.TARGET_IDS, *protocol.CONTROL_PANELS)[panel]
    return {"feature_ids": list(ids), "coefficient": sign,
            "weights": [sign*dose*s for s in protocol.SCALES]}


def test_only_generator_cap_changes_and_shared_methods_are_identical():
    source = ast.parse(textwrap.dedent(inspect.getsource(ModelBackend.generate)))
    revised = ast.parse(textwrap.dedent(inspect.getsource(backend.Backend.generate)))
    for node in ast.walk(source):
        if isinstance(node, ast.Constant) and node.value == 256:
            node.value = 512
        elif isinstance(node, ast.Constant) and node.value == "max_new_tokens must be between 1 and 256":
            node.value = "max_new_tokens must be between 1 and 512"
    assert ast.dump(source) == ast.dump(revised)
    for method in ("_forward", "vector", "_build_geometry", "_telemetry", "answer_nll", "qualify"):
        assert getattr(backend.Backend, method) is getattr(OldBackend, method)


@pytest.mark.parametrize("dose", protocol.DOSES)
@pytest.mark.parametrize("sign", [-1, 0, 1])
def test_same_geometry_all_panels_signs_and_seeded_cached_path(tiny, dose, sign):
    messages = [{"role": "user", "content": "abc"}]
    for panel in range(4):
        edit = arm(panel, dose, sign)
        old = ModelBackend.generate(tiny, messages, 3, .5, 4, edit)
        new = tiny.generate(messages, 3, .5, 4, edit)
        assert old["output_token_ids"] == new["output_token_ids"]
        assert old["telemetry"] == new["telemetry"]
        assert tiny.geometry_receipt()["requested_norm_matched"]
        assert not tiny._layer._forward_hooks


def test_512_preserves_old_prefix_offsets_and_clean_nll(tiny):
    tiny.model.generation_config.eos_token_id = []
    tiny.tokenizer.eos_token_id = None
    messages = [{"role": "user", "content": "abc"}]
    short = ModelBackend.generate(tiny, messages, 7, .5, 256, arm(1, .75, -1))
    long = tiny.generate(messages, 7, .5, 512, arm(1, .75, -1))
    assert short["output_token_ids"] == long["output_token_ids"][:256]
    assert long["output_tokens"] == 512 and long["cap_hit"]
    n = long["input_tokens"]
    assert [r["position"] for r in long["telemetry"]["reencoding"]] == list(range(n-1, n+512))
    metadata = long["telemetry"]["position_metadata"]
    assert len(metadata) == n+512 and metadata[-1]["terminal_observation_only"]
    assert sum(p["terminal_observation_only"] for p in metadata) == 1
    assert tiny.answer_nll(long["input_token_ids"], long["output_token_ids"]) >= 0
    assert not tiny._layer._forward_hooks
    with pytest.raises(ValueError): tiny.generate(messages, 7, .5, 513)
    with pytest.raises(ValueError): ModelBackend.generate(tiny, messages, 7, .5, 512)


@pytest.mark.parametrize("stop", [1, 512])
def test_eos_at_limit_is_not_a_cap_hit(tiny, monkeypatch, stop):
    count = 0
    def logits(hidden):
        nonlocal count
        count += 1
        result = torch.zeros((*hidden.shape[:-1], 32), device=hidden.device)
        result[..., 2 if count == stop else 3] = 100
        return result
    monkeypatch.setattr(tiny.model.lm_head, "forward", logits)
    result = tiny.generate([{"role": "user", "content": "abc"}], 1, 0., 512)
    assert result["output_tokens"] == stop and result["output_token_ids"][-1] == 2
    assert not result["cap_hit"] and not tiny._layer._forward_hooks

"""Exact observation tests on native BF16 tiny Llama; no model download."""
import pytest
import torch

from tests.test_steering_fidelity_backend import tiny, MESSAGES, ARM
from experiments.steering_fidelity_repair import activation_probe as p


def test_observation_does_not_change_sampled_tokens(tiny):
    plain = tiny.generate(MESSAGES, 81, .5, 3)
    observed = p.generated_probe(tiny, MESSAGES, [0, 3], seed=81, max_new_tokens=3)
    assert plain["output_token_ids"] == observed["result"]["output_token_ids"]
    assert plain["telemetry"] == observed["result"]["telemetry"]
    probe = observed["position_probe"]
    assert len(probe["positions"]) == plain["input_tokens"] + plain["output_tokens"]
    assert probe["call_lengths"] == [plain["input_tokens"]] + [1] * plain["output_tokens"]
    assert all(r["origin"] == "generated" for r in probe["positions"][plain["input_tokens"]:])
    assert probe["positions"][-1]["terminal_observation_only"] is True
    assert not tiny._layer._forward_hooks


def test_observed_edit_is_same_edit(tiny):
    plain = tiny.generate(MESSAGES, 82, .5, 3, ARM)
    observed = p.generated_probe(tiny, MESSAGES, [0, 3], seed=82, max_new_tokens=3, intervention=ARM)
    assert plain["output_token_ids"] == observed["result"]["output_token_ids"]
    assert plain["telemetry"] == observed["result"]["telemetry"]


def test_known_body_positions_observed_separately(tiny):
    tiny.tokenizer.encodings['{"ok":true}'] = [4, 5, 6, 7]
    result = p.teacher_probe(tiny, MESSAGES, '{"ok":true}', [0, 3])
    probe = result["position_probe"]
    assert [r["token_id"] for r in probe["positions"][-4:]] == [4, 5, 6, 7]
    assert all(r["origin"] == "teacher_forced" for r in probe["positions"][-4:])
    assert not tiny._layer._forward_hooks


def test_each_position_matches_native_full_width_encoding(tiny):
    encoder, bias = tiny._sae[:2]
    h = torch.randn(1, 4, 16, device=tiny.device).to(torch.bfloat16)
    observer = p.Observer(tiny, [0, 3])
    original = h.clone()
    assert observer.hook(None, None, h) is None
    expected = [torch.relu(torch.nn.functional.linear(h[:, i], encoder, bias))[0, [0, 3]].float().tolist()
                for i in range(4)]
    assert observer.values == expected
    assert torch.equal(h, original)


def test_prompt_inactivity_does_not_hide_active_body(tiny):
    # A synthetic counterexample to using one prompt state as a liveness gate.
    tiny._sae[0].zero_()
    tiny._sae[0][0, 0] = 1
    tiny._sae[1].zero_()
    h = torch.zeros(1, 3, 16, device=tiny.device, dtype=torch.bfloat16)
    h[0, 2, 0] = 2
    observer = p.Observer(tiny, [0])
    observer.hook(None, None, h)
    assert observer.values == [[0.], [0.], [2.]]


def test_observer_removed_on_exception(tiny):
    with pytest.raises(RuntimeError, match="example"):
        with p.observe_positions(tiny, [0]):
            raise RuntimeError("example")
    assert not tiny._layer._forward_hooks


def test_conflicting_hook_refused(tiny):
    handle = tiny._layer.register_forward_hook(lambda *args: None)
    try:
        with pytest.raises(ValueError, match="unhooked"):
            with p.observe_positions(tiny, [0]):
                pass
    finally:
        handle.remove()


def test_bad_metadata_rejected(tiny):
    with p.observe_positions(tiny, [0]) as observer:
        result = tiny.generate(MESSAGES, 81, 0., 2)
    result["telemetry"]["position_metadata"][0]["token_id"] = 31
    with pytest.raises(ValueError, match="alignment"):
        observer.attach(result)


@pytest.mark.parametrize("body", ["", None])
def test_empty_body_refused(tiny, body):
    with pytest.raises(ValueError, match="Nonempty"):
        p.teacher_probe(tiny, MESSAGES, body, [0])


def test_special_body_refused(tiny):
    tiny.tokenizer.encodings["special"] = [2]
    with pytest.raises(ValueError, match="ordinary"):
        p.teacher_probe(tiny, MESSAGES, "special", [0])

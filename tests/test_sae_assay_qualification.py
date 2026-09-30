"""Offline actual tiny-Llama tests: missing dependencies fail, never skip."""

from copy import deepcopy
import hashlib
import json
import socket
from types import SimpleNamespace

import pytest
import torch
from transformers import LlamaForCausalLM

from experiments.sae_assay_diagnostic import qualify as q


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    monkeypatch.setenv("HF_HUB_OFFLINE", "1")
    monkeypatch.setenv("TRANSFORMERS_OFFLINE", "1")

    def forbidden(*args, **kwargs):
        raise AssertionError("Network/pretrained loading is forbidden in qualification tests")

    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(LlamaForCausalLM, "from_pretrained", forbidden)


@pytest.fixture
def tiny():
    backend = q.tiny_backend("cpu")
    yield backend
    backend.close()


@pytest.fixture
def texts():
    return [{"id": key, "split": "calibration", "category": key[12:-3],
             "text": "abcde" * (i + 1)} for i, key in enumerate(q.QUALIFICATION_TEXT_IDS)]


def test_actual_random_llama_native_bf16_and_rng_preservation(tiny):
    assert isinstance(tiny.model, LlamaForCausalLM)
    assert tiny.dtype == torch.bfloat16
    assert tiny.metadata["test_only"] is True
    assert all(t.dtype == torch.bfloat16 for t in tiny._sae)
    assert tiny._sae[0].shape == (32, 16)
    before = torch.random.get_rng_state().clone()
    another = q.tiny_backend("cpu")
    try:
        assert torch.equal(before, torch.random.get_rng_state())
        for left, right in zip(tiny.model.parameters(), another.model.parameters()):
            assert torch.equal(left, right)
        for left, right in zip(tiny._sae, another._sae):
            assert torch.equal(left, right)
    finally:
        another.close()


def test_known_answers_are_exact_full_width_bf16():
    result = q._known_answers("cpu")
    assert len(result["checks"]) == 9
    assert all(result["checks"].values())
    assert result["raw"]["telemetry"]["suppression"]["requested_delta"] == [
        [-.75, -1.125], [-1.25, -.625]]
    json.dumps(result, allow_nan=False)


def test_tiny_model_zero_signed_direction_exact_replay_and_positions():
    state = torch.random.get_rng_state().clone()
    report = q.run_tiny_checks("cpu")
    assert report["pass"]
    assert len(report["checks"]) == 19
    assert all(report["checks"].values())
    assert torch.equal(state, torch.random.get_rng_state())
    assert report["device"] == "cpu" and "do not qualify CUDA" in report["scope"]
    raw = report["raw_outputs"]
    for arm in ("zero", "suppression", "amplification"):
        gen, replay = raw["generation"][arm], raw["replay"][arm]
        assert gen["telemetry"] == replay["telemetry"]
        assert replay["output_token_ids"] == gen["output_token_ids"]
        assert replay["input_token_ids"] == gen["input_token_ids"]
        assert replay["output_tokens"] > 0
        assert replay["telemetry"]["position_metadata"][-1]["terminal_observation_only"]
        assert replay["unsteered_nll"][0] is None
        assert raw["teacher"][arm]["reconstruction_nll"] is not None
    assert report["elapsed_seconds"] >= 0
    json.dumps(report, allow_nan=False)


def test_corrupt_replay_fails_instead_of_using_tolerance(monkeypatch):
    replay = q.ModelBackend.replay_tokens

    def altered(self, *args, **kwargs):
        result = replay(self, *args, **kwargs)
        result["telemetry"]["selected_activations"]["before"][0][0] += 1e-9
        return result

    monkeypatch.setattr(q.ModelBackend, "replay_tokens", altered)
    report = q.run_tiny_checks("cpu")
    assert report["pass"] is False
    assert not report["checks"]["zero_exact_replay"]
    assert not report["checks"]["suppression_exact_replay"]
    assert not report["checks"]["amplification_exact_replay"]


def test_real_fixed_shard_retains_raw_outputs_and_does_not_mutate(tiny, texts):
    original = deepcopy(texts)
    calls = []
    teacher = tiny.teacher

    def observed(text, ids, **kwargs):
        calls.append((text, ids, kwargs))
        return teacher(text, ids, **kwargs)

    tiny.teacher = observed
    inventory = list(reversed(texts)) + [{"id": "validation-neutral-01", "text": "never execute"}]
    report = q.qualify_real(tiny, inventory, [0, 3])
    assert report["collection_complete"], report["errors"]
    assert texts == original
    assert [r["id"] for r in report["rows"]] == list(q.QUALIFICATION_TEXT_IDS)
    assert len(calls) == 7
    assert all(args == [0, 3] and kwargs == {"collect_reconstruction": True}
               for _, args, kwargs in calls)
    assert [text for text, _, _ in calls] == [t["text"] for t in texts]
    assert report["qualification_pass"] is None
    assert report["numerical_tolerance"] is None
    assert len(report["q90"]["authoritative"]["q90"]) == 2
    assert len(report["encoder_comparisons"]) == 7
    for row, text, comparison in zip(report["rows"], texts, report["encoder_comparisons"]):
        assert row["text_sha256"] == hashlib.sha256(text["text"].encode()).hexdigest()
        raw = row["result"]
        assert raw["full_sae_diagnostics"] and raw["reconstruction_nll"]
        assert len(comparison["differences"]["before"]) == len(raw["token_ids"])
    for feature in report["decisions"]["authoritative"]["features"]:
        exposure = feature["exposure"]["suppression"]
        assert exposure["positions"] == 140  # BOS tokens never count.
        assert exposure["texts"] == 7 and exposure["eligible"]
    json.dumps(report, allow_nan=False)


def test_selected_path_activity_and_q90_disagreement_is_preserved(tiny, texts):
    teacher = tiny.teacher

    def changed(text, ids, **kwargs):
        result = teacher(text, ids, **kwargs)
        for key in ("selected_path_before", "selected_path_after"):
            result["telemetry"]["full_sae"][key] = [[0.] * len(ids) for _ in result["token_ids"]]
        return result

    tiny.teacher = changed
    report = q.qualify_real(tiny, texts, [0, 3])
    assert report["collection_complete"], report["errors"]
    assert not report["q90"]["exactly_equal"]
    assert report["q90"]["selected_path"]["q90"] == [None, None]
    assert not report["decisions"]["exactly_equal"]
    assert not report["encoder_comparisons"][0]["activity"]["pass"]
    assert report["qualification_pass"] is None
    assert report["rows"][0]["result"]["telemetry"]["selected_activations"]["before"][0][0] > 0


def test_selected_path_small_nonzero_difference_never_silently_tolerated(tiny, texts):
    teacher = tiny.teacher

    def changed(text, ids, **kwargs):
        result = teacher(text, ids, **kwargs)
        for when in ("before", "after"):
            values = result["telemetry"]["selected_activations"][when]
            result["telemetry"]["full_sae"][f"selected_path_{when}"] = [
                [v + 1e-9 for v in row] for row in values]
        return result

    tiny.teacher = changed
    report = q.qualify_real(tiny, texts, [0, 3])
    assert report["collection_complete"]
    assert not report["q90"]["exactly_equal"]
    assert all(v > 0 for v in report["q90"]["selected_minus_authoritative"])
    assert all(r["activity"]["pass"] for r in report["encoder_comparisons"])
    assert report["numerical_tolerance"] is None


def test_q90_eligibility_uses_actual_fp32_request_threshold(tiny, texts):
    report = q.qualify_real(tiny, texts, [0, 3])
    quantiles = deepcopy(report["q90"]["authoritative"])
    quantiles["q90"][0] = .5 + 1e-9
    decisions = q._path_decisions(report["rows"], quantiles)
    assert decisions["features"][0]["effective_fp32_q90"] == .5


@pytest.mark.parametrize("corruption", ["nonfinite", "missing_selected", "full_mismatch"])
def test_real_malformed_diagnostic_stops_with_raw_evidence(tiny, texts, corruption):
    teacher = tiny.teacher

    def changed(*args, **kwargs):
        raw = teacher(*args, **kwargs)
        full = raw["telemetry"]["full_sae"]
        if corruption == "nonfinite":
            full["selected_path_before"][0][0] = float("nan")
        elif corruption == "missing_selected":
            del full["selected_path_before"]
        else:
            full["full_selected_before"][0][0] += 1
        return raw

    tiny.teacher = changed
    report = q.qualify_real(tiny, texts, [0, 3])
    assert not report["collection_complete"]
    assert report["qualification_pass"] is None and report["errors"]
    assert len(report["rows"]) == 1


def test_exact_replay_retains_terminal_eos_without_retokenizing(tiny, monkeypatch):
    tiny.model.generation_config.eos_token_id = list(range(32))
    generated = tiny.generate([{"role": "user", "content": "abc"}], q.SEED, .7, max_new_tokens=4)
    assert generated["output_tokens"] == 1 and not generated["cap_hit"]
    monkeypatch.setattr(tiny, "_tokenize", lambda *a, **k: pytest.fail("No retokenization on replay"))
    replay = tiny.replay_tokens(generated["input_token_ids"], generated["output_token_ids"], [0, 3])
    assert replay["output_token_ids"] == generated["output_token_ids"]
    assert replay["telemetry"] == generated["telemetry"]


@pytest.mark.parametrize("change", ["missing", "duplicate", "validation", "category", "empty"])
def test_invalid_fixed_inventory_rejected_before_forward(monkeypatch, tiny, texts, change):
    if change == "missing":
        texts.pop()
    elif change == "duplicate":
        texts.append(texts[0])
    elif change == "validation":
        texts[0]["split"] = "validation"
    elif change == "category":
        texts[0]["category"] = "different"
    else:
        texts[0]["text"] = ""
    monkeypatch.setattr(tiny, "teacher", lambda *a, **k: pytest.fail("No forward on invalid inventory"))
    with pytest.raises(ValueError):
        q.qualify_real(tiny, texts, [0, 3])


@pytest.mark.parametrize("ids", [[], [True], [-1], [0, 0], [1.0]])
def test_invalid_targets_rejected(texts, ids):
    with pytest.raises(ValueError):
        q.qualify_real(None, texts, ids)


def test_real_backend_failure_retains_partial_outputs(tiny, texts):
    teacher = tiny.teacher
    count = 0

    def fail_second(*args, **kwargs):
        nonlocal count
        count += 1
        if count == 2:
            raise RuntimeError("injected forward failure")
        return teacher(*args, **kwargs)

    tiny.teacher = fail_second
    report = q.qualify_real(tiny, texts, [0, 3])
    assert not report["collection_complete"]
    assert len(report["rows"]) == 1 and count == 2
    assert report["errors"][0]["message"] == "injected forward failure"
    assert report["qualification_pass"] is None


@pytest.mark.parametrize("field,value", [("native_dtype", "torch.float32"),
                                        ("encoding_authority", "selected_rows"),
                                        ("feature_ids", [3, 0])])
def test_real_wrong_authority_dtype_or_feature_order_fails(tiny, texts, field, value):
    teacher = tiny.teacher

    def changed(*args, **kwargs):
        result = teacher(*args, **kwargs)
        result["telemetry"][field] = value
        return result

    tiny.teacher = changed
    report = q.qualify_real(tiny, texts, [0, 3])
    assert not report["collection_complete"]
    assert report["errors"] and len(report["rows"]) == 1


@pytest.mark.parametrize("torch_version,cuda,transformers", [
    ("2.8.1+cu128", "12.8", "4.47.1"), ("2.8.0+cu126", "12.6", "4.47.1"),
    ("2.8.0", None, "4.47.1"), ("2.8.0+cu128", "12.8", "4.48.0")])
def test_source_requires_exact_runtime(torch_version, cuda, transformers):
    with pytest.raises(RuntimeError, match="torch 2.8.0/cu128"):
        q._check_runtime_versions(torch_version, cuda, transformers)
    assert q._check_runtime_versions("2.8.0+cu128", "12.8", "4.47.1")


def test_cli_cpu_failure_writes_json_and_never_builds_model(tmp_path, monkeypatch):
    monkeypatch.setattr(torch.version, "cuda", None)
    monkeypatch.setattr(torch.cuda, "is_available", lambda: False)
    monkeypatch.setattr(q, "tiny_backend", lambda *a, **k: pytest.fail("No construction on runtime failure"))
    out = tmp_path / "qualification.json"
    assert q.main(["--out", str(out)]) == 1
    report = json.loads(out.read_text())
    assert not report["pass"] and report["errors"]
    assert report["tiny"] is None and report["nf4"]["status"] == "not_run"
    assert report["runtime"]["cuda_available"] is False
    assert report["required_runtime"]["cuda"] == "12.8"
    assert len(report["source_hashes"]) == 4
    before = out.read_bytes()
    with pytest.raises(FileExistsError):
        q.main(["--out", str(out)])
    assert out.read_bytes() == before


def test_nf4_unavailable_is_explicit_not_a_passing_smoke(monkeypatch):
    monkeypatch.setattr(q.importlib.util, "find_spec", lambda name: None)
    result = q._nf4_smoke()
    assert result["status"] == "unavailable" and result["pass"] is None


@pytest.mark.parametrize("nf4_failure", [False, True])
def test_source_nf4_failure_vs_optional_unavailability(monkeypatch, nf4_failure):
    monkeypatch.setattr(q, "_check_runtime_versions", lambda *a: {})
    monkeypatch.setattr(torch.cuda, "is_available", lambda: True)
    def native_bf16(*, including_emulation):
        assert including_emulation is False
        return True

    monkeypatch.setattr(torch.cuda, "is_bf16_supported", native_bf16)
    monkeypatch.setattr(torch.cuda, "current_device", lambda: 0)
    monkeypatch.setattr(torch.cuda, "get_device_properties", lambda i: SimpleNamespace(name="mock", major=8, minor=0))
    monkeypatch.setattr(torch.cuda, "mem_get_info", lambda: (100, 200))
    monkeypatch.setattr(q, "run_tiny_checks", lambda device: {"pass": True})

    def nf4():
        if nf4_failure:
            raise RuntimeError("NF4 CUDA failure")
        return {"status": "unavailable", "pass": None}

    monkeypatch.setattr(q, "_nf4_smoke", nf4)
    report = q.qualify_source()
    assert report["pass"] is (not nf4_failure)
    assert bool(report["errors"]) is nf4_failure
    assert report["runtime"]["gpu"]["name"] == "mock"
    assert report["nf4"]["status"] == ("failed" if nf4_failure else "unavailable")

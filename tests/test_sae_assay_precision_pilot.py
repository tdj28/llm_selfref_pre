"""No downloads: fixed-plan pilot exercised through tiny real BF16 Llama."""
import copy
import hashlib
import json
import shutil
import time
from unittest.mock import patch

import numpy as np
import pytest

torch = pytest.importorskip("torch")
transformers = pytest.importorskip("transformers")
pytest.importorskip("safetensors")
from safetensors.torch import load_file, save_file

from experiments.sae_assay_diagnostic.backend import ModelBackend, _canonical_encode, _fp32_math
from experiments.sae_assay_precision import pilot as p


class Tokenizer:
    all_special_ids = [0, 1, 2]

    def __call__(self, text, **_kwargs):
        token = 4 + int(text.split()[1]) % 20
        return {"input_ids": torch.tensor([[1, token, 7, 12, 2]])}


def make_plan():
    texts = [{"id": f"family{i:02d}-01", "family": f"family{i:02d}", "split": "discovery",
              "category": "synthetic", "text": f"fixture {i}"} for i in range(12)]
    texts += [{"id": "family00-02", "family": "family00", "split": "discovery",
               "category": "synthetic", "text": "fixture 40"},
              {"id": "heldout-01", "family": "heldout", "split": "validation",
               "category": "synthetic", "text": "fixture 41"}]
    tok = Tokenizer()
    items = [{"id": item["id"], "text_sha256": hashlib.sha256(item["text"].encode()).hexdigest(),
              "token_ids": tok(item["text"])["input_ids"][0].tolist(),
              "special_tokens_mask": [True, False, False, False, True]} for item in texts]
    return {"texts": texts, "certificate": {"items": items}, "target_feature_ids": [0, 1, 2],
            "precision_pilot": {"texts": texts[:12], "modes": list(p.MODES), "change": .75,
                "norm_cap": .04, "layer_index": 50,
                "fidelity": {"minimum_fraction": .95, "minimum_cosine": .95, "maximum_relative_error": .20},
                "norm": {"minimum_fraction": .95, "maximum_clean_ratio": .05}}}


@pytest.fixture(scope="module")
def tiny():
    threads = torch.get_num_threads()
    torch.set_num_threads(1)
    with torch.random.fork_rng():
        torch.manual_seed(491)
        config = transformers.LlamaConfig(vocab_size=32, hidden_size=16, intermediate_size=32,
            num_hidden_layers=3, num_attention_heads=2, num_key_value_heads=2,
            max_position_embeddings=64, attention_dropout=0., bos_token_id=1, eos_token_id=2)
        config._attn_implementation = "sdpa"
        model = transformers.LlamaForCausalLM(config).to(torch.bfloat16).eval()
        state = {"encoder_linear.weight": torch.randn(8, 16) * .25,
                 "encoder_linear.bias": torch.tensor([0., 0., -10., 0., 0., 0., 0., 0.]),
                 "decoder_linear.weight": torch.randn(16, 8) * .1,
                 "decoder_linear.bias": torch.zeros(16)}
    backend = ModelBackend.from_components_for_test(model, Tokenizer(), state, default_feature_ids=[0, 1, 2])
    yield backend
    backend.close()
    torch.set_num_threads(threads)


def prepare_exposure(root, tiny, plan):
    """Independent no-bridge clean forwards, outside pilot's counted forwards."""
    (root / "rows").mkdir(parents=True)
    (root / "residuals").mkdir()
    with torch.inference_mode():
        for item in p.pilot_texts(plan):
            capture = []
            handle = tiny._layer.register_forward_hook(
                lambda _m, _args, output: capture.append(output[0].detach().clone()))
            tokens = tiny._tokenize(item["text"])
            try:
                tiny.model.model(tokens, use_cache=False)
            finally:
                handle.remove()
            hidden = capture[0]
            ids = plan["target_feature_ids"]
            z = _canonical_encode(hidden, *tiny._sae[:2], torch.tensor(ids)).reshape(-1, len(ids)).float()
            path = root / "residuals" / (item["id"] + ".safetensors")
            save_file({"hidden": hidden, "token_ids": tokens}, str(path))
            row = {"text_id": item["id"], "plan_sha256": p._hash(plan), "freeze_commit": "a" * 40,
                   "feature_ids": ids, "token_ids": tokens[0].tolist(),
                   "activations": {str(i): z[:, j].tolist() for j, i in enumerate(ids)},
                   "capture": {"path": "residuals/" + path.name, "sha256": p.sha(path)}}
            p.write_once(root / "rows" / ("clean-" + item["id"] + ".json"), row)


@pytest.fixture(scope="module")
def completed(tmp_path_factory, tiny):
    root = tmp_path_factory.mktemp("precision-pilot")
    plan = make_plan()
    prepare_exposure(root, tiny, plan)
    calls, downstream = [], []
    counter = tiny.model.model.register_forward_hook(lambda *_args: calls.append(1))
    probe = tiny.model.model.layers[1].register_forward_pre_hook(
        lambda _m, args: downstream.append(args[0].dtype))
    try:
        summary = p.run_pilot(tiny, plan, p._hash(plan), "a" * 40, root, time.time() + 120)
    finally:
        counter.remove()
        probe.remove()
    return root, plan, summary, calls, downstream


def rows(root):
    return [json.loads(path.read_text()) for path in sorted((root / p.DIRECTORY / "rows").glob("*.json"))]


def test_exact_48_actual_forwards_with_real_fp32_downstream(completed, tiny):
    root, plan, summary, calls, downstream = completed
    assert len(calls) == 48
    assert downstream == [torch.bfloat16, torch.float32, torch.float32, torch.float32] * 12
    assert p.validate_run(root, plan, p._hash(plan), "a" * 40)["row_count"] == 48
    assert summary["completed"] is True and summary["overall_assay_qualified"] is False
    assert summary["test_only"] is True
    assert len(summary["modes"]) == 4
    assert not any(module._forward_hooks or module._forward_pre_hooks for module in tiny.model.modules())
    assert all(parameter.dtype == torch.bfloat16 for parameter in tiny.model.parameters())
    events = [json.loads(line) for line in (root / p.DIRECTORY / "receipts.jsonl").read_text().splitlines()]
    assert sum(e["data"]["kind"] == "dispatch" for e in events) == 48
    assert sum(e["data"]["kind"] == "row" for e in events) == 48


def test_raw_actual_states_new_readout_and_native_comparator(completed, tiny):
    root, plan, *_ = completed
    for row in rows(root):
        raw = load_file(str(root / p.DIRECTORY / row["capture"]["path"]))
        assert set(raw) == p.CAPTURE_KEYS
        assert raw["pre"].dtype == torch.bfloat16
        assert raw["requested"].dtype == torch.float32
        assert raw["post"].dtype == (torch.bfloat16 if row["mode"] == "native_zero" else torch.float32)
        assert not torch.count_nonzero(raw["requested"][~raw["valid"]])
        index = torch.tensor(plan["target_feature_ids"])
        with torch.inference_mode(), _fp32_math(tiny.device):
            _, promoted = p._readout(raw["post"].float(), tiny._sae[0].float(), tiny._sae[1].float(), index)
            native = _canonical_encode(raw["post"].bfloat16(), *tiny._sae[:2], index).reshape(-1, len(index)).float()
        assert torch.equal(promoted, raw["promoted_after"])
        assert torch.equal(native, raw["native_rounded_after"])
        assert row["delivery"] == p._metrics(raw["pre"], raw["requested"], raw["post"])
        assert torch.equal(raw["post"], raw["pre"].float() + raw["requested"])
    assert any(np.any(row["precision_readout_shift"]) for row in rows(root))
    assert any(row["nll"] != row["sham_nll"] for row in rows(root) if row["mode"] in p.MODES[2:])


def test_native_zero_identity_and_losses_match_direct_model(completed, tiny):
    root, *_ = completed
    row = rows(root)[0]
    tokens = torch.tensor([row["token_ids"]])
    with torch.inference_mode():
        logits = tiny.model(tokens, use_cache=False).logits[0, :-1].float()
        expected = torch.nn.functional.cross_entropy(logits, tokens[0, 1:], reduction="none")
    torch.testing.assert_close(torch.tensor(row["nll"][1:]), expected)
    assert row["nll"] == row["native_nll"]
    assert row["kl_native_to_mode"] == [None, 0., 0., 0., 0.]
    assert row["returned_original_output"] is True and not row["boundary_trace"]
    sham = rows(root)[1]
    assert sham["sham_nll"] == sham["nll"]
    assert sham["kl_sham_to_mode"] == [None, 0., 0., 0., 0.]


def test_projection_is_fixed_native_anchor_and_rounding_independent():
    h = torch.tensor([[[1024., 2., 1.], [1., 2., 3.], [1., 2., 3.]]], dtype=torch.bfloat16)
    native = torch.tensor([[1e-5, .02], [0., 0.], [3., 4.]])
    preact = native.clone()
    e = torch.tensor([[1., 0., 0.], [0., 1., 0.]])
    valid = torch.tensor([[True, True, False]])
    request, gram = p._requests(h, native, preact, e, valid)
    assert gram == [[1., 0.], [0., 1.]]
    assert request["suppression"][0][0, 0, 0].item() == pytest.approx(-.75e-5)
    assert request["amplification"][0][0, 0, 0].item() == pytest.approx(.75e-5)
    assert not torch.count_nonzero(request["suppression"][0][0, 1:])
    metrics = p._metrics(h, request["amplification"][0], h.float() + request["amplification"][0])
    assert metrics["relative_error"][0] > 0  # FP32 writeback is measured, not assigned perfection.
    assert metrics["nonzero_requested"] == [True, False, False]


def test_readout_always_full_width_token_one():
    h = torch.ones(3, 4)
    encoder, bias, index = torch.eye(7, 4), torch.zeros(7), torch.tensor([1, 3])
    original = p.F.linear
    calls = []

    def observe(values, weight, offset=None):
        calls.append((tuple(values.shape), tuple(weight.shape)))
        return original(values, weight, offset)

    with patch.object(p.F, "linear", side_effect=observe):
        p._readout(h, encoder, bias, index)
    assert calls == [((1, 4), (7, 4))] * 3


def test_denominators_keep_zero_inactive_and_undefined(completed):
    root, _, summary, *_ = completed
    sham = summary["modes"]["precision_sham"]
    assert sham["all_positions"] == 60 and sham["nonspecial_positions"] == 36
    assert sham["fidelity"]["denominator"] == 0 and sham["fidelity"]["fraction"] is None
    assert sham["norm"]["denominator"] == 0 and sham["norm"]["pass"] is False
    inactive = summary["modes"]["suppression"]["features"]["2"]
    assert inactive["native_active_positions"] == 0 and inactive["nonspecial_denominator"] == 36
    assert inactive["native_anchor_after_ratio_median"] is None
    altered = copy.deepcopy(rows(root))
    for row in altered:
        row["native_before"][1][0] = 1.
        row["promoted_before"][1][0] = 0.
    report = p.summarize(altered)["modes"]["suppression"]["features"]["0"]
    assert report["paired_promoted_undefined_positions"] == 12
    assert report["paired_promoted_after_ratio_median"] is None
    assert report["primary_eligible_native_active_positions"] >= 12
    assert report["efficacy_qualified"] is False


def test_norm_primary_cannot_be_diluted_by_zero_edits(completed):
    root, *_ = completed
    altered = copy.deepcopy(rows(root))
    for row in altered:
        if row["mode"] == "suppression":
            row["delivery"]["realized_norm"] = [0., 1., 0., 0., 0.]
            row["delivery"]["realized_clean_ratio"] = [0., .06, 0., 0., 0.]
    norm = p.summarize(altered)["modes"]["suppression"]["norm"]
    assert norm == {"passing_positions": 0, "denominator": 12, "fraction": 0., "pass": False}


@pytest.mark.parametrize("mutation", ["selection", "mode", "change", "validation"])
def test_frozen_design_rejects_tuning_or_heldout_selection(mutation):
    plan = make_plan()
    if mutation == "selection":
        plan["precision_pilot"]["texts"][0] = plan["texts"][12]
    elif mutation == "mode":
        plan["precision_pilot"]["modes"] = list(p.MODES[:-1])
    elif mutation == "change":
        plan["precision_pilot"]["norm_cap"] = .05
    else:
        plan["precision_pilot"]["texts"][0] = plan["texts"][-1]
    with pytest.raises(ValueError):
        p.pilot_texts(plan)


def test_write_once_refuses_rerun(completed, tiny):
    root, plan, *_ = completed
    before = (root / p.DIRECTORY / "receipts.jsonl").read_bytes()
    with pytest.raises(FileExistsError):
        p.run_pilot(tiny, plan, p._hash(plan), "a" * 40, root, time.time() + 120)
    assert (root / p.DIRECTORY / "receipts.jsonl").read_bytes() == before


@pytest.mark.parametrize("artifact", ["capture", "row", "binding", "qualification", "ledger", "summary"])
def test_offline_audit_rejects_corruption(completed, tmp_path, artifact):
    source, plan, *_ = completed
    root = tmp_path / "copy"
    shutil.copytree(source, root)
    base = root / p.DIRECTORY
    if artifact == "capture":
        path = base / "tensors/002.safetensors"
        path.write_bytes(path.read_bytes() + b"corrupt")
    elif artifact == "row":
        path = base / "rows/002.json"
        path.write_text(path.read_text().replace('"suppression"', '"amplification"'))
    elif artifact == "ledger":
        path = base / "receipts.jsonl"
        path.write_bytes(path.read_bytes()[:-5])
    else:
        (base / (artifact + ".json")).write_text("{}")
    with pytest.raises((ValueError, KeyError)):
        p.validate_run(root, plan, p._hash(plan), "a" * 40)


def test_failure_preserved_no_retries_or_hook_leaks(tiny, tmp_path):
    plan = make_plan()
    prepare_exposure(tmp_path, tiny, plan)
    with patch.object(tiny, "_losses", side_effect=RuntimeError("injected loss failure")):
        with pytest.raises(RuntimeError, match="injected"):
            p.run_pilot(tiny, plan, p._hash(plan), "a" * 40, tmp_path, time.time() + 120)
    failure = json.loads((tmp_path / p.DIRECTORY / "failure.json").read_text())
    assert failure["retry_permitted"] is False
    events = [json.loads(line) for line in (tmp_path / p.DIRECTORY / "receipts.jsonl").read_text().splitlines()]
    assert sum(e["data"]["kind"] == "dispatch" for e in events) == 1
    assert not any(module._forward_hooks for module in tiny.model.modules())
    with pytest.raises(FileExistsError):
        p.run_pilot(tiny, plan, p._hash(plan), "a" * 40, tmp_path, time.time() + 120)


def test_rejected_raw_row_is_written_before_validation(tiny, tmp_path):
    plan = make_plan()
    prepare_exposure(tmp_path, tiny, plan)
    original = p.validate_row

    def reject_sham(row, *args):
        if row["mode"] == "precision_sham":
            raise ValueError("injected structural rejection")
        return original(row, *args)

    with patch.object(p, "validate_row", side_effect=reject_sham):
        with pytest.raises(ValueError, match="structural rejection"):
            p.run_pilot(tiny, plan, p._hash(plan), "a" * 40, tmp_path, time.time() + 120)
    root = tmp_path / p.DIRECTORY
    rejected = json.loads((root / "rows/001.json").read_text())
    assert rejected["mode"] == "precision_sham"
    assert len(rejected["nll"]) == len(rejected["kl_native_to_mode"]) == 5
    assert rejected["boundary_trace"] and rejected["bridge"]["hooks_removed"] is True
    assert p.sha(root / rejected["capture"]["path"]) == rejected["capture"]["sha256"]
    events = [json.loads(line) for line in (root / "receipts.jsonl").read_text().splitlines()]
    assert [e["data"]["row_id"] for e in events if e["data"]["kind"] == "row"] == [
        "precision-pilot:family00-01:native_zero"]
    assert events[-1]["data"]["kind"] == "failure"
    assert json.loads((root / "failure.json").read_text())["completed_forward_records"] == 1
    with pytest.raises(ValueError, match="Incomplete"):
        p.validate_run(tmp_path, plan, p._hash(plan), "a" * 40)


def test_changed_clean_exposure_rejected(tiny, tmp_path):
    plan = make_plan()
    prepare_exposure(tmp_path, tiny, plan)
    path = tmp_path / "rows/clean-family00-01.json"
    row = json.loads(path.read_text())
    row["activations"]["0"][1] += .125
    path.write_text(json.dumps(row))
    with pytest.raises(ValueError, match="prior clean exposure"):
        p.run_pilot(tiny, plan, p._hash(plan), "a" * 40, tmp_path, time.time() + 120)
    assert (tmp_path / p.DIRECTORY / "failure.json").exists()


@pytest.mark.parametrize("deadline", [float("inf"), float("nan"), 0., True])
def test_invalid_deadline_prevents_dispatch(tiny, tmp_path, deadline):
    plan = make_plan()
    with pytest.raises(ValueError, match="[Dd]eadline"):
        p.run_pilot(tiny, plan, p._hash(plan), "a" * 40, tmp_path, deadline)
    assert not (tmp_path / p.DIRECTORY).exists()


def test_missing_mode_cannot_be_summarized(completed):
    root, *_ = completed
    with pytest.raises(ValueError, match="All 12"):
        p.summarize(rows(root)[:-1])


def test_pilot_preserves_enabled_tf32_during_all_model_forwards(tiny, tmp_path):
    plan = make_plan()
    previous = torch.backends.cuda.matmul.allow_tf32
    observed = []
    try:
        torch.backends.cuda.matmul.allow_tf32 = True
        prepare_exposure(tmp_path, tiny, plan)
        handle = tiny.model.model.layers[-1].register_forward_pre_hook(
            lambda *_: observed.append(torch.backends.cuda.matmul.allow_tf32))
        try:
            p.run_pilot(tiny, plan, p._hash(plan), "a" * 40, tmp_path, time.time() + 120)
        finally:
            handle.remove()
        assert observed == [True] * 48
        assert all(row["model_math"]["allow_tf32"] is True for row in rows(tmp_path))
        assert torch.backends.cuda.matmul.allow_tf32 is True
    finally:
        torch.backends.cuda.matmul.allow_tf32 = previous


def test_pilot_rejects_autocast_without_silent_baseline_change(tiny, tmp_path):
    plan = make_plan()
    with torch.autocast("cpu", dtype=torch.bfloat16):
        with pytest.raises(ValueError, match="autocast disabled"):
            p.run_pilot(tiny, plan, p._hash(plan), "a" * 40, tmp_path, time.time() + 120)
    assert not (tmp_path / p.DIRECTORY).exists()


def test_cold_math_preflight_rejects_unrestorable_medium_without_model():
    previous = torch.get_float32_matmul_precision()
    try:
        torch.set_float32_matmul_precision("medium")
        with pytest.raises(ValueError, match="cannot preserve medium"):
            p.validate_model_math("cuda")
        assert torch.get_float32_matmul_precision() == "medium"
    finally:
        torch.set_float32_matmul_precision(previous)


@pytest.mark.parametrize("mutation", ["boolean_metric", "wrong_delta", "fake_identity", "loss_missing"])
def test_structural_validation_rejects_incoherent_row_even_without_hash_check(completed, mutation):
    root, plan, *_ = completed
    row = copy.deepcopy(rows(root)[0])
    if mutation == "boolean_metric":
        row["delivery"]["nonzero_requested"][1] = 0.
    elif mutation == "wrong_delta":
        row["precision_readout_shift"][1][0] += 1.
    elif mutation == "fake_identity":
        row["returned_original_output"] = False
    else:
        row["native_nll"][1] = None
    with pytest.raises(ValueError):
        p.validate_row(row, plan)


def test_rehashed_wrong_capture_dtype_still_rejected(completed, tmp_path):
    source, plan, *_ = completed
    root = tmp_path / "copy"
    shutil.copytree(source, root)
    row = rows(root)[2]
    path = root / p.DIRECTORY / row["capture"]["path"]
    raw = load_file(str(path))
    raw["projection_coefficients"] = raw["projection_coefficients"].double()
    save_file(raw, str(path))
    row["capture"]["sha256"] = p.sha(path)
    row["capture"]["tensors"]["projection_coefficients"]["dtype"] = "torch.float64"
    with pytest.raises(ValueError, match="shape or dtype"):
        p.validate_row(row, plan, root / p.DIRECTORY)


def test_continuous_projection_cap_is_not_tuned():
    h = torch.ones(1, 2, 3, dtype=torch.bfloat16)
    before = torch.ones(2, 2)
    request, _ = p._requests(h, before, before, torch.eye(2, 3), torch.ones(1, 2, dtype=torch.bool))
    for mode in p.MODES[2:]:
        r, _, scale, _ = request[mode]
        ratio = torch.linalg.vector_norm(r, dim=-1) / torch.linalg.vector_norm(h.float(), dim=-1)
        torch.testing.assert_close(ratio, torch.full_like(ratio, .04), atol=1e-7, rtol=0.)
        assert (scale < 1).all()

"""CPU controls for the optional, separately dispatched tiny GPU qualification."""

from copy import deepcopy
import json
from pathlib import Path
import signal
import subprocess
import sys
from types import SimpleNamespace
from contextlib import nullcontext
from unittest.mock import Mock

import pytest

from experiments.kolibri_swap import gpu_smoke as smoke


def test_import_has_no_torch_vllm_or_plugin_dependency():
    code = (
        "import sys; from experiments.kolibri_swap import gpu_smoke; "
        "assert not {'torch', 'vllm', 'aleph_alpha_inference'} & sys.modules.keys()"
    )
    subprocess.run([sys.executable, "-c", code], cwd=Path(smoke.__file__).resolve().parents[2],
                   check=True, timeout=20)


@pytest.mark.parametrize("changed", [None, "torch", "vllm", "aleph-alpha-inference"])
def test_exact_versions(changed):
    versions = {**smoke.VERSIONS, "torch": "2.13.0+cu130"}
    if changed:
        versions[changed] = "9.0.0"
        with pytest.raises(ValueError, match="version mismatch"):
            smoke.verify_versions(versions)
    else:
        smoke.verify_versions(versions)


def test_prerelease_and_missing_versions_fail():
    for version in ("2.13.0rc1", "2.13.0.dev1", ""):
        with pytest.raises(ValueError):
            smoke.verify_versions({**smoke.VERSIONS, "torch": version})


@pytest.fixture
def upstream(tmp_path, monkeypatch):
    source = tmp_path / "helper.py"
    source.write_text("answer = 42\n")
    monkeypatch.setattr(smoke, "SOURCE_HASHES", {"helper.py": smoke.sha256(source)})
    monkeypatch.setattr(smoke.subprocess, "check_output", Mock(return_value=smoke.UPSTREAM_SHA + "\n"))
    return tmp_path


def test_provenance_and_lazy_helper(upstream):
    assert smoke.verify_upstream(upstream)["revision"] == smoke.UPSTREAM_SHA
    assert smoke.load_source(upstream, "helper.py").answer == 42


def test_wrong_revision_fails_before_import(upstream, monkeypatch):
    monkeypatch.setattr(smoke.subprocess, "check_output", Mock(return_value="0" * 40))
    with pytest.raises(ValueError, match="revision mismatch"):
        smoke.verify_upstream(upstream)


def test_dirty_source_and_import_race_rejected(upstream):
    smoke.verify_upstream(upstream)
    (upstream / "helper.py").write_text("raise RuntimeError('must not execute')\n")
    with pytest.raises(ValueError, match="hash mismatch"):
        smoke.verify_upstream(upstream)
    with pytest.raises(ValueError, match="before import"):
        smoke.load_source(upstream, "helper.py")


def test_no_import_when_source_or_versions_fail(tmp_path, monkeypatch):
    version_check = Mock(side_effect=ValueError("wrong runtime"))
    monkeypatch.setattr(smoke, "verify_upstream", Mock(return_value={"revision": smoke.UPSTREAM_SHA}))
    monkeypatch.setattr(smoke, "installed_versions", Mock(return_value={}))
    monkeypatch.setattr(smoke, "verify_versions", version_check)
    parser = Mock()
    monkeypatch.setattr(smoke, "parser_checks", parser)
    with pytest.raises(ValueError, match="wrong runtime"):
        smoke.qualify(tmp_path, "gpu", tmp_path, {})
    parser.assert_not_called()


def test_config_alignment_and_no_base_mutation():
    base = {"num_hidden_layers": 6, "hidden_size": 256, "num_experts": 8,
            "num_experts_per_tok": 2, "head_dim": 32, "num_attention_heads": 8,
            "num_key_value_heads": 2, "layer_types": ["full_attention"]}
    original = deepcopy(base)
    cfg = smoke.tiny_config(base)
    assert base == original
    assert (cfg["head_dim"], cfg["num_attention_heads"], cfg["num_key_value_heads"]) == (128, 2, 1)
    assert cfg["quantization_config"]["weight_block_size"] == [128, 128]
    assert cfg["quantization_config"]["activation_scheme"] == "dynamic"
    ignored = cfg["quantization_config"]["modules_to_not_convert"]
    assert "lm_head" in ignored and "model.layers.5.mlp.gate" in ignored
    with pytest.raises(ValueError, match="architecture"):
        smoke.tiny_config({**base, "num_hidden_layers": 50})


@pytest.mark.parametrize("name,expected", [
    ("model.layers.0.self_attn.q_proj.weight", True),
    ("model.layers.0.self_attn.k_proj.weight", True),
    ("model.layers.5.mlp.experts.7.down_proj.weight", True),
    ("model.layers.1.mlp.shared_experts.up_proj.weight", True),
    ("model.layers.0.self_attn.q_norm.weight", False),
    ("model.layers.0.post_ffn_norm.weight", False),
    ("model.layers.0.mlp.gate.weight", False),
    ("model.layers.0.moe.router.expert_bias", False),
    ("model.embed_tokens.weight", False),
    ("lm_head.weight", False),
])
def test_quantization_allowlist(name, expected):
    assert bool(smoke.LINEAR_WEIGHT.fullmatch(name)) is expected


@pytest.fixture
def torch():
    module = pytest.importorskip("torch")
    if not hasattr(module, "float8_e4m3fn"):
        pytest.skip("Local torch has no E4M3FN dtype")
    return module


def test_fp8_exact_block_scales_and_orientation(torch):
    # Unequal row/column scales catch transpose, tensor-scale and inverse bugs.
    expected = torch.tensor([[0.25, 2.0, 3.0], [4.0, 0.5, 8.0]])
    expanded = expected.repeat_interleave(128, 0).repeat_interleave(128, 1)
    weight = expanded * 448
    weight[1::2] *= -1
    quantized, scales = smoke.fp8_block128(weight)
    assert quantized.dtype == torch.float8_e4m3fn
    assert scales.dtype == torch.float32
    assert tuple(scales.shape) == (2, 3)
    assert torch.equal(scales, expected)
    assert torch.equal(quantized.float().abs(), torch.full_like(weight, 448))
    assert torch.equal(quantized.float() * expanded, weight)


def test_fp8_random_roundtrip_error_not_model_accuracy(torch):
    generator = torch.Generator().manual_seed(19)
    weight = torch.randn(256, 384, generator=generator).bfloat16()
    quantized, scales = smoke.fp8_block128(weight)
    expanded = scales.repeat_interleave(128, 0).repeat_interleave(128, 1)
    restored = quantized.float() * expanded
    # E4M3 nearest rounding: relative half-ULP <= 1/16; allow subnormal floor.
    bound = weight.float().abs() / 16 + expanded / 512 + 1e-6
    assert bool(((restored - weight.float()).abs() <= bound).all())
    for row in range(2):
        for col in range(3):
            block = weight[row * 128:(row + 1) * 128, col * 128:(col + 1) * 128].float()
            assert scales[row, col] == block.abs().max() / 448


def test_fp8_zero_blocks_noncontiguous_and_rejections(torch):
    quantized, scales = smoke.fp8_block128(torch.zeros(256, 128).t())
    assert not quantized.float().any()
    assert torch.equal(scales, torch.ones(1, 2))
    for shape in ((128,), (128, 64), (0, 128), (8, 128, 128)):
        with pytest.raises(ValueError, match="dimensions"):
            smoke.fp8_block128(torch.zeros(shape))
    with pytest.raises(ValueError, match="floating"):
        smoke.fp8_block128(torch.zeros(128, 128, dtype=torch.int64))
    for value in (float("nan"), float("inf"), -float("inf")):
        with pytest.raises(ValueError, match="Nonfinite"):
            smoke.fp8_block128(torch.full((128, 128), value))


def test_complete_conversion_keeps_router_norm_head_embedding(torch):
    weight = torch.ones(128, 128, dtype=torch.bfloat16)
    tensors = {}
    for i in range(6):
        prefix = f"model.layers.{i}"
        for projection in "qkvo":
            tensors[f"{prefix}.self_attn.{projection}_proj.weight"] = weight
        for expert in ["shared_experts"] + [f"experts.{j}" for j in range(8)]:
            for projection in ("gate", "up", "down"):
                tensors[f"{prefix}.mlp.{expert}.{projection}_proj.weight"] = weight
    untouched = {"model.layers.0.mlp.gate.weight": weight,
                 "model.layers.0.self_attn.q_norm.weight": torch.ones(128),
                 "lm_head.weight": weight, "model.embed_tokens.weight": weight,
                 "model.layers.0.moe.router.expert_bias": torch.ones(8)}
    converted, count = smoke.convert_weights({**tensors, **untouched})
    assert count == 186 and len(converted) == 2 * 186 + len(untouched)
    for name, original in untouched.items():
        expected = torch.float32 if name.endswith("expert_bias") else torch.bfloat16
        assert converted[name].dtype == expected
        assert torch.equal(converted[name].float(), original.float())
    assert converted["model.layers.0.self_attn.q_proj.weight_scale_inv"].dtype == torch.float32
    tensors.pop(next(iter(tensors)))
    with pytest.raises(ValueError, match="inventory"):
        smoke.convert_weights(tensors)


def valid_outputs():
    return [SimpleNamespace(finished=True, prompt_token_ids=list(prompt), outputs=[
        SimpleNamespace(token_ids=[123] * smoke.MAX_TOKENS,
                        logprobs=[{123: SimpleNamespace(logprob=-2.5)} for _ in range(smoke.MAX_TOKENS)])
    ]) for prompt in smoke.PROMPTS]


def test_forward_validation_and_fixed_runtime_limits():
    summaries = smoke.validate_outputs(valid_outputs())
    assert [s["tokens"] for s in summaries] == [8, 8]
    assert [s["prompt_tokens"] for s in summaries] == [4, 96]
    assert smoke.LLM_OPTIONS["enforce_eager"] is True
    assert smoke.LLM_OPTIONS["gpu_memory_utilization"] == 0.3
    assert smoke.LLM_OPTIONS["max_model_len"] == 512
    assert smoke.LLM_OPTIONS["kv_cache_dtype"] == "fp8"
    assert smoke.LLM_OPTIONS["skip_tokenizer_init"] is True


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -float("inf"), 0.1, -10001])
def test_bad_logprobs_fail(value):
    outputs = valid_outputs()
    outputs[0].outputs[0].logprobs[0][123].logprob = value
    with pytest.raises(ValueError, match="logprob"):
        smoke.validate_outputs(outputs)


@pytest.mark.parametrize("failure", ["empty", "no_logprobs", "unscored", "bad_id", "unfinished", "wrong_prompt"])
def test_bad_forwards_fail(failure):
    outputs = valid_outputs()
    completion = outputs[0].outputs[0]
    if failure == "empty":
        completion.token_ids = []
    elif failure == "no_logprobs":
        completion.logprobs = None
    elif failure == "unscored":
        completion.logprobs[0] = {}
    elif failure == "bad_id":
        completion.token_ids[0] = 96000
    elif failure == "unfinished":
        outputs[0].finished = False
    else:
        outputs[0].prompt_token_ids = [999]
    with pytest.raises(ValueError):
        smoke.validate_outputs(outputs)


def test_worker_environment_is_offline_and_eager_routing_safe(tmp_path):
    env = smoke.worker_env(tmp_path)
    assert env["HF_HUB_OFFLINE"] == env["TRANSFORMERS_OFFLINE"] == "1"
    assert env["VLLM_USE_DEEP_GEMM"] == env["VLLM_USE_DEEP_GEMM_E8M0"] == "0"
    assert env["PYTHONPATH"].split(":")[0] == str(tmp_path)
    assert env["VLLM_WORKER_MULTIPROC_METHOD"] == "spawn"


def test_gpu_path_uses_real_architecture_interface_but_mocked_external_runtime(tmp_path, monkeypatch):
    routing = SimpleNamespace(test_routing_semantics=Mock())
    engine = Mock()
    engine.generate.return_value = valid_outputs()
    engine.collective_rpc.return_value = [{"custom_routing_layers": 6}]
    llm, sampling = Mock(return_value=engine), Mock()
    cuda = SimpleNamespace(is_available=lambda: True, get_device_capability=lambda: (8, 9),
                           get_device_name=lambda: "mock Ada", synchronize=Mock())
    monkeypatch.setitem(sys.modules, "torch", SimpleNamespace(
        cuda=cuda, device=lambda _: nullcontext(), version=SimpleNamespace(cuda="mock")))
    monkeypatch.setitem(sys.modules, "vllm", SimpleNamespace(LLM=llm, SamplingParams=sampling))
    monkeypatch.setattr(smoke, "load_source", Mock(return_value=routing))
    monkeypatch.setattr(smoke, "write_tiny_checkpoint", Mock(return_value={"fp8_matrices": 186}))
    result = smoke.gpu_checks(tmp_path, tmp_path)
    assert result["official_routing_cpu_cuda"] is True
    assert routing.test_routing_semantics.call_count == 2
    llm.assert_called_once_with(model=str(tmp_path / "tiny"), **smoke.LLM_OPTIONS)
    engine.collective_rpc.assert_called_once_with(smoke.inspect_worker)
    assert sampling.call_args.kwargs["max_tokens"] == 8
    assert sampling.call_args.kwargs["ignore_eos"] is True
    assert sampling.call_args.kwargs["detokenize"] is False
    assert engine.generate.call_args.args[0] == [{"prompt_token_ids": list(p)} for p in smoke.PROMPTS]


def test_gpu_unavailable_fails_before_weights_or_generation(tmp_path, monkeypatch):
    llm = Mock()
    monkeypatch.setitem(sys.modules, "torch", SimpleNamespace(cuda=SimpleNamespace(is_available=lambda: False)))
    monkeypatch.setitem(sys.modules, "vllm", SimpleNamespace(LLM=llm, SamplingParams=Mock()))
    checkpoint = Mock()
    monkeypatch.setattr(smoke, "write_tiny_checkpoint", checkpoint)
    with pytest.raises(ValueError, match="CUDA unavailable"):
        smoke.gpu_checks(tmp_path, tmp_path)
    llm.assert_not_called()
    checkpoint.assert_not_called()


@pytest.mark.parametrize("passed,skipped,exit_code", [(70, 0, 0), (1, 0, 0), (70, 1, 0), (70, 0, 1)])
def test_parser_requires_whole_official_suite_then_explicit_medium(
        tmp_path, monkeypatch, passed, skipped, exit_code):
    def run_pytest(args, plugins):
        plugins[0].passed, plugins[0].skipped = passed, skipped
        assert args[-1] == str(tmp_path / "tests/test_reasoning.py")
        return exit_code

    tests = Mock(USER_MESSAGES=[{"role": "user", "content": "hi"}], TOOL_LOOP_MESSAGES=[])
    monkeypatch.setitem(sys.modules, "pytest", SimpleNamespace(main=run_pytest))
    monkeypatch.setitem(sys.modules, "vllm.reasoning", SimpleNamespace(ReasoningParserManager=Mock()))
    monkeypatch.setattr(smoke, "load_source", Mock(return_value=tests))
    # parser_checks intentionally adjusts sys.path inside its disposable process.
    monkeypatch.setattr(sys, "path", list(sys.path))
    if (passed, skipped, exit_code) != (70, 0, 0):
        with pytest.raises(ValueError, match="incomplete"):
            smoke.parser_checks(tmp_path)
        tests._make_mock_tokenizer.assert_not_called()
    else:
        result = smoke.parser_checks(tmp_path)
        assert result["official_passed"] == 70
        assert tests.test_thinking_on_non_streaming_truncated_is_reasoning.call_count == 2
        calls = tests.test_thinking_on_non_streaming_splits_reasoning.call_args_list
        assert [c.args[-1] for c in calls] == [
            {"reasoning_effort": "medium"},
            {"reasoning_effort": "medium", "enable_thinking": False}]


@pytest.mark.parametrize("mode", ["parser", "gpu"])
def test_cli_mocks_external_gpu_path_and_preserves_result(tmp_path, monkeypatch, mode):
    external = Mock(return_value={"status": "passed", "versions": smoke.VERSIONS})
    monkeypatch.setattr(smoke, "bounded_worker", external)
    out = tmp_path / "qualification.json"
    args = ["--out", str(out), "--upstream", str(tmp_path), "--mode", mode]
    assert smoke.main(args) == 0
    result = json.loads(out.read_text())
    assert result["mode"] == mode and result["status"] == "passed"
    assert result["scientific_generation"] is False
    assert result["random_model_accuracy_claim"] is False
    assert external.call_args.args[1] == mode
    original = out.read_bytes()
    with pytest.raises(FileExistsError):
        smoke.main(args)
    assert out.read_bytes() == original


def test_failure_json_and_nonzero_exit(tmp_path, monkeypatch):
    monkeypatch.setattr(smoke, "bounded_worker", Mock(side_effect=RuntimeError("synthetic failure")))
    out = tmp_path / "failed.json"
    assert smoke.main(["--out", str(out)]) == 1
    result = json.loads(out.read_text())
    assert result["status"] == "failed" and "synthetic failure" in result["error"]


def test_worker_weights_use_parent_owned_scratch(tmp_path, monkeypatch):
    def qualify(root, mode, scratch, result):
        assert scratch == tmp_path
        result["status"] = "passed"

    monkeypatch.setattr(smoke, "qualify", qualify)
    assert smoke.main(["--_worker", "--out", str(tmp_path / "worker.json")]) == 0


@pytest.mark.parametrize("timeout", [0, -1, 901])
def test_timeout_limits_before_dispatch(tmp_path, monkeypatch, timeout):
    external = Mock()
    monkeypatch.setattr(smoke, "bounded_worker", external)
    out = tmp_path / "never-created.json"
    with pytest.raises(SystemExit):
        smoke.main(["--out", str(out), "--timeout-seconds", str(timeout)])
    external.assert_not_called()
    assert not out.exists()


@pytest.mark.parametrize("outcome", ["timeout", "crash", "pass", "contradiction"])
def test_process_group_cleanup_and_failure_status(tmp_path, monkeypatch, outcome):
    process = Mock(pid=12345)
    process.wait.side_effect = [subprocess.TimeoutExpired("worker", 1), -9] if outcome == "timeout" else [
        3 if outcome in ("crash", "contradiction") else 0, 0]
    popen = Mock(return_value=process)
    kill = Mock()
    monkeypatch.setattr(smoke.subprocess, "Popen", popen)
    monkeypatch.setattr(smoke.os, "killpg", kill)
    if outcome in ("pass", "contradiction"):
        (tmp_path / "worker.json").write_text('{"status":"passed"}')
    if outcome == "contradiction":
        with pytest.raises(ValueError, match="mismatch"):
            smoke.bounded_worker(tmp_path, "gpu", tmp_path, 1)
    else:
        result = smoke.bounded_worker(tmp_path, "gpu", tmp_path, 1)
        expected = {"timeout": "timeout", "crash": "failed", "pass": "passed"}[outcome]
        assert result["status"] == expected
    kill.assert_called_once_with(12345, signal.SIGKILL)
    assert popen.call_args.kwargs["start_new_session"] is True
    assert "--_worker" in popen.call_args.args[0]

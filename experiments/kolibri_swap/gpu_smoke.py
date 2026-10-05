"""Bounded, offline Kolibri runtime qualification, never scientific generation.

Run from the repository root::

    python -m experiments.kolibri_swap.gpu_smoke \
        --upstream /workspace/kolibri/upstream --out /workspace/kolibri/smoke.json

The caller supplies an installed plugin/runtime and the exact upstream checkout.
No downloads, tokenizer, provider access, or trained weights are needed. Upstream
Apache-2.0 helpers are imported, not vendored; their license and bytes are pinned.
Use --mode parser for the official CPU parser tests plus explicit medium cases.
Passing qualifies only this random, tiny architecture on the recorded runtime.
"""

from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import importlib.metadata
import importlib.util
import json
import math
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import tempfile
import time

UPSTREAM_SHA = "049a6a7bd2405b27d6d280d256bd3d585191c7ae"
VERSIONS = {"aleph-alpha-inference": "1.0.0", "vllm": "0.29.0", "torch": "2.13.0"}
SOURCE_HASHES = {
    "LICENSE": "cfc7749b96f63bd31c3c42b5c471bf756814053e847c10f3eb003417bc523d30",
    "pyproject.toml": "ccaeef5be01e26337e6e08fed7624a71b54841da3bc866a9bc31724b17068779",
    "aleph_alpha_inference/__init__.py": "38e8ef7f742da2d0722a796667d8cd0795de779409eca24e0a9ca4f4c70358b1",
    "aleph_alpha_inference/config.py": "8770a22e4615ce46708146ea605ab37965c3c064c6905f9e6a6a5dd2c526d1ec",
    "aleph_alpha_inference/kolibri1.py": "f93635dd3ebeed3c12ca2b3a00ab1b92fdc95b5290eaa672420861ba5a1bd320",
    "aleph_alpha_inference/reasoning.py": "b1e9af238db783bfe318de3ccd4ffef7b885f75be272c7460638797ac2f87aea",
    "tests/checkpoints.py": "f14cab0628a5aef2931d93ae6f7ffe74f78e6931c10d5fa91735f97be1845e3f",
    "tests/conftest.py": "f68b14fc21e8ef671ee46d9a1cafc6e2084b4bb0239919e6e1d706105cb1a227",
    "tests/test_kolibri1.py": "e2e4308e729dbebc10ac2552b929f34be9d3bd542af8997b698cdf2ddbd5efa3",
    "tests/test_reasoning.py": "51ab7dbd5d3217931a67368dae66b0d823530443d16eeb538b958931936ef28f",
    "tests/kolibri1_chat_template.jinja": "51b9ae6f83e7a30d428fccc75da306653801be73d4ed936e838667d5de7a6617",
}
SEED = 20261004
MAX_SECONDS = 900
MAX_TOKENS = 8
PROMPTS = ((11, 12, 13, 14), tuple(range(100, 196)))
LLM_OPTIONS = {
    "skip_tokenizer_init": True, "trust_remote_code": False,
    "dtype": "bfloat16", "quantization": "fp8", "kv_cache_dtype": "fp8",
    "enforce_eager": True, "max_model_len": 512,
    "gpu_memory_utilization": 0.3, "tensor_parallel_size": 1,
    "max_num_seqs": 2, "max_num_batched_tokens": 512,
    "enable_prefix_caching": False, "seed": SEED,
}
LINEAR_WEIGHT = re.compile(
    r"model\.layers\.\d+\.(?:self_attn\.[qkvo]_proj|"
    r"mlp\.(?:shared_experts|experts\.\d+)\.(?:gate|up|down)_proj)\.weight"
)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def verify_upstream(root):
    root = Path(root).resolve(strict=True)
    revision = subprocess.check_output(
        ["git", "-C", str(root), "rev-parse", "HEAD"], text=True, timeout=10).strip()
    require(revision == UPSTREAM_SHA, "Upstream Git revision mismatch")
    hashes = {name: sha256(root / name) for name in SOURCE_HASHES}
    require(hashes == SOURCE_HASHES, "Upstream source hash mismatch")
    return {"revision": revision, "source_sha256": hashes}


def installed_versions():
    return {name: importlib.metadata.version(name) for name in VERSIONS}


def verify_versions(versions):
    # CUDA wheel local suffixes are recorded, not mistaken for a release change.
    require(all(versions.get(k, "").split("+", 1)[0] == v
                for k, v in VERSIONS.items()), "Runtime version mismatch")


def load_source(root, relative):
    path = root / relative
    require(sha256(path) == SOURCE_HASHES[relative], "Helper changed before import")
    spec = importlib.util.spec_from_file_location("_kolibri_" + path.stem, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def fp8_block128(weight):
    """E4M3FN blocks: q = round(w / s), weight_scale_inv = s (FP32).

    vLLM 0.29.0's Fp8LinearMethod/Fp8MoEMethod multiply by these scales;
    they are NOT the reciprocal dequantization scales, nor E8M0 powers of two.
    """
    import torch

    require(weight.ndim == 2 and all(n > 0 and n % 128 == 0 for n in weight.shape),
            "FP8 matrices must have positive, block128-aligned dimensions")
    require(weight.is_floating_point(), "FP8 source must be floating point")
    w = weight.detach().float()
    require(bool(torch.isfinite(w).all()), "Nonfinite FP8 source")
    rows, cols = w.shape
    blocks = w.reshape(rows // 128, 128, cols // 128, 128).permute(0, 2, 1, 3)
    amax = blocks.abs().amax(dim=(-2, -1))
    scale = torch.where(amax == 0, torch.ones_like(amax), amax / 448.0)
    require(bool((scale > 0).all()), "FP8 scale underflow")
    quantized = (blocks / scale[..., None, None]).clamp(-448, 448)
    quantized = quantized.permute(0, 2, 1, 3).reshape(rows, cols)
    return quantized.to(torch.float8_e4m3fn).contiguous(), scale.contiguous()


def tiny_config(base):
    cfg = deepcopy(base)
    require((cfg["num_hidden_layers"], cfg["hidden_size"], cfg["num_experts"],
             cfg["num_experts_per_tok"]) == (6, 256, 8, 2), "Unexpected tiny architecture")
    cfg.update(head_dim=128, num_attention_heads=2, num_key_value_heads=1,
               dtype="bfloat16")
    cfg["quantization_config"] = {
        "quant_method": "fp8", "activation_scheme": "dynamic",
        "weight_block_size": [128, 128],
        "modules_to_not_convert": ["lm_head", "model.embed_tokens"] + [
            f"model.layers.{i}.mlp.gate" for i in range(6)],
    }
    return cfg


def convert_weights(tensors):
    import torch

    converted = {}
    count = 0
    for name, weight in tensors.items():
        require(bool(torch.isfinite(weight).all()), "Nonfinite checkpoint tensor")
        if LINEAR_WEIGHT.fullmatch(name):
            converted[name], converted[name.removesuffix(".weight") + ".weight_scale_inv"] = (
                fp8_block128(weight))
            count += 1
        else:
            require(not name.endswith("weight_scale_inv"), "Checkpoint is already quantized")
            dtype = torch.float32 if name.endswith("expert_bias") else torch.bfloat16
            converted[name] = weight.to(dtype)
    require(count == 6 * (4 + 3 + 8 * 3), "Incomplete tiny FP8 linear inventory")
    return converted, count


def write_tiny_checkpoint(root, destination):
    import torch
    from safetensors.torch import load_file, save_file

    helper = load_source(root, "tests/checkpoints.py")
    cfg = tiny_config(helper.KOLIBRI1_CONFIG)
    previous_dtype = torch.get_default_dtype()
    try:
        torch.set_default_dtype(torch.bfloat16)
        torch.manual_seed(SEED)
        helper.write_kolibri1_checkpoint(str(destination), cfg=cfg)
    finally:
        torch.set_default_dtype(previous_dtype)
    path = destination / "model.safetensors"
    tensors, count = convert_weights(load_file(str(path)))
    # This is a disposable helper-generated checkpoint, never released evidence.
    save_file(tensors, str(path))
    return {"config": cfg, "fp8_matrices": count,
            "weights_sha256": sha256(path), "config_sha256": sha256(destination / "config.json")}


def parser_checks(root):
    import pytest
    from vllm.reasoning import ReasoningParserManager

    class Results:
        passed = 0
        skipped = 0

        def pytest_runtest_logreport(self, report):
            self.passed += report.when == "call" and report.passed
            self.skipped += report.skipped

    results = Results()
    sys.path.insert(0, str(root / "tests"))
    code = pytest.main(["-q", "-p", "no:cacheprovider",
                        str(root / "tests/test_reasoning.py")], plugins=[results])
    require(code == 0 and results.passed == 70 and results.skipped == 0,
            "Official parser tests failed, skipped or incomplete")
    tests = load_source(root, "tests/test_reasoning.py")
    adapter = ReasoningParserManager.get_reasoning_parser("kolibri1")
    # Upstream covers none/low/high/default; explicitly exercise approved medium.
    for kwargs in ({"reasoning_effort": "none"}, {"reasoning_effort": "medium"},
                   {"reasoning_effort": "medium", "enable_thinking": False}):
        tokenizer = tests._make_mock_tokenizer()
        tests.test_template_prefills_block_iff_thinking_off(kwargs)
        tests.test_template_gate_agrees_with_parser(adapter, tokenizer, kwargs)
        if kwargs["reasoning_effort"] == "none":
            tests.test_thinking_off_non_streaming_is_content(adapter, tokenizer, kwargs)
            streaming = tests.test_template_thinking_off_streams_as_content
        else:
            tests.test_thinking_on_non_streaming_splits_reasoning(adapter, tokenizer, kwargs)
            tests.test_thinking_on_non_streaming_truncated_is_reasoning(adapter, tokenizer, kwargs)
            streaming = tests.test_template_thinking_on_streams_reasoning_then_content
        for messages in (tests.USER_MESSAGES, tests.TOOL_LOOP_MESSAGES):
            streaming(adapter, tokenizer, kwargs, messages)
    return {"official_passed": results.passed, "skipped": 0,
            "off_medium_streaming_nonstreaming": True, "truncated_medium_reasoning_only": True}


def validate_outputs(outputs, vocab_size=96000):
    require(len(outputs) == len(PROMPTS), "Wrong forward result count")
    summaries = []
    for output, prompt in zip(outputs, PROMPTS):
        require(output.finished and list(output.prompt_token_ids) == list(prompt),
                "Unfinished or mismatched synthetic request")
        require(len(output.outputs) == 1, "Wrong completion count")
        completion = output.outputs[0]
        ids, panels = completion.token_ids, completion.logprobs
        require(len(ids) == MAX_TOKENS and panels is not None and len(panels) == len(ids),
                "Missing or truncated token/logprob output")
        values = []
        for token, panel in zip(ids, panels):
            require(type(token) is int and 0 <= token < vocab_size and token in panel,
                    "Invalid or unscored output token")
            require(bool(panel), "Empty logprob panel")
            for item in panel.values():
                value = float(item.logprob)
                require(math.isfinite(value) and -10000.0 <= value <= 1e-6,
                        "Nonfinite or out-of-bounds logprob")
                values.append(value)
        summaries.append({"prompt_tokens": len(prompt), "tokens": len(ids),
                          "logprob_min": min(values), "logprob_max": max(values)})
    return summaries


def inspect_worker(worker):
    """Executed inside vLLM: check loaded dtypes and the actual MoE router."""
    import torch
    from aleph_alpha_inference.kolibri1 import Kolibri1ForCausalLM, sigmoid_logit_add_routing
    from vllm.model_executor.layers.fused_moe.router.custom_routing_router import CustomRoutingRouter

    model = worker.model_runner.model
    cfg = worker.vllm_config
    require(isinstance(model, Kolibri1ForCausalLM), "Not the plugin Kolibri architecture")
    require(cfg.model_config.enforce_eager and cfg.model_config.dtype == torch.bfloat16,
            "Eager/BF16 runtime config mismatch")
    require(cfg.cache_config.cache_dtype == "fp8" and cfg.model_config.max_model_len == 512,
            "KV/context config mismatch")
    require(model.quant_config.weight_block_size == [128, 128], "Wrong FP8 block config")
    require(model.quant_config.is_checkpoint_fp8_serialized, "Not serialized FP8")
    layers = list(model.model.layers)
    require(len(layers) == 6, "Wrong runtime layer count")
    backends = set()
    kv_dtypes = set()
    for layer in layers:
        attn, moe = layer.self_attn, layer.mlp
        for linear in (attn.qkv_proj, attn.o_proj, moe.shared_experts.gate_up_proj,
                       moe.shared_experts.down_proj):
            require(linear.weight.dtype == torch.float8_e4m3fn, "Linear is not FP8")
            require(linear.weight_scale_inv.dtype == torch.float32, "Linear scale is not FP32")
        experts = moe.experts.routed_experts
        for name in ("w13", "w2"):
            require(getattr(experts, name + "_weight").dtype == torch.float8_e4m3fn,
                    "Expert is not FP8")
            require(getattr(experts, name + "_weight_scale_inv").dtype == torch.float32,
                    "Expert scale is not FP32")
        require(moe.gate.weight.dtype in (torch.bfloat16, torch.float32), "Quantized router")
        for norm in (attn.q_norm, attn.k_norm, layer.input_layernorm,
                     layer.post_attention_layernorm, layer.post_attn_norm, layer.post_ffn_norm):
            require(norm.weight.dtype == torch.bfloat16, "Quantized norm")
        router = moe.experts.router
        require(isinstance(router, CustomRoutingRouter) and not router.renormalize,
                "Plugin custom router missing or renormalized")
        require(router.custom_routing_function.func is sigmoid_logit_add_routing,
                "Different custom routing function")
        logits = torch.arange(32 * 8, device="cuda", dtype=torch.float32).reshape(32, 8)
        logits = torch.sin(logits) * 3
        weights, ids = router._compute_routing(torch.zeros(32, 256, device="cuda"), logits, None)
        bias = moe.gate.e_score_correction_bias
        require(bias.dtype == torch.float32 and bool(torch.isfinite(bias).all()) and
                bool(bias.any()), "Routing correction bias missing or invalid")
        reference = torch.topk(logits + bias, k=2, dim=-1).indices
        require(torch.equal(ids.long(), reference), "Loaded router expert selection mismatch")
        require(torch.allclose(weights, torch.sigmoid(logits).gather(1, reference)),
                "Loaded router weights mismatch")
        cache = attn.attn.kv_cache
        require(attn.attn.kv_cache_dtype == "fp8" and cache.numel() > 0 and
                cache.is_cuda and cache.element_size() == 1 and
                cache.dtype in (torch.uint8, torch.float8_e4m3fn), "KV storage is not FP8")
        backends.add(attn.attn.attn_backend.get_name())
        kv_dtypes.add(str(cache.dtype))
    require(model.lm_head.weight.dtype == torch.bfloat16 and
            model.model.embed_tokens.weight.dtype == torch.bfloat16, "Quantized head/embedding")
    return {"layers": 6, "custom_routing_layers": 6, "fp8_weights": True,
            "fp32_block_scales": True, "kv_storage_dtypes": sorted(kv_dtypes),
            "attention_backends": sorted(backends)}


def gpu_checks(root, scratch):
    import torch
    from vllm import LLM, SamplingParams

    require(torch.cuda.is_available(), "CUDA unavailable; GPU qualification not run")
    require(torch.cuda.get_device_capability() >= (8, 9), "FP8-capable Ada or newer GPU required")
    routing = load_source(root, "tests/test_kolibri1.py")
    routing.test_routing_semantics()
    with torch.device("cuda"):
        routing.test_routing_semantics()
    checkpoint = scratch / "tiny"
    checkpoint.mkdir()
    receipt = write_tiny_checkpoint(root, checkpoint)
    llm = LLM(model=str(checkpoint), **LLM_OPTIONS)
    outputs = llm.generate(
        [{"prompt_token_ids": list(p)} for p in PROMPTS],
        SamplingParams(max_tokens=MAX_TOKENS, temperature=0.0, logprobs=5,
                       ignore_eos=True, detokenize=False, seed=SEED), use_tqdm=False)
    forward = validate_outputs(outputs)
    workers = llm.collective_rpc(inspect_worker)
    require(len(workers) == 1, "Expected one tensor-parallel worker")
    torch.cuda.synchronize()
    return {"device": torch.cuda.get_device_name(), "cuda": torch.version.cuda,
            "capability": list(torch.cuda.get_device_capability()),
            "official_routing_cpu_cuda": True, "checkpoint": receipt,
            "forward": forward, "workers": workers, "llm_options": LLM_OPTIONS}


def qualify(root, mode, scratch, result):
    require(__debug__, "Python optimization disables upstream assertions")
    result["upstream"] = verify_upstream(root)
    result["versions"] = installed_versions()
    verify_versions(result["versions"])
    sys.path.insert(0, str(root))
    import aleph_alpha_inference

    require(Path(aleph_alpha_inference.__file__).resolve() ==
            root / "aleph_alpha_inference/__init__.py", "Plugin imported outside verified checkout")
    aleph_alpha_inference.register()
    result["parser"] = parser_checks(root)
    if mode == "gpu":
        result["gpu"] = gpu_checks(root, scratch)
    result["status"] = "passed"


def worker_env(root):
    env = dict(os.environ)
    env.update(HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1", HF_HUB_DISABLE_TELEMETRY="1",
               VLLM_NO_USAGE_STATS="1", DO_NOT_TRACK="1", PYTHONDONTWRITEBYTECODE="1",
               PYTEST_DISABLE_PLUGIN_AUTOLOAD="1", PYTEST_ADDOPTS="", PYTHONOPTIMIZE="0",
               VLLM_USE_DEEP_GEMM="0", VLLM_USE_DEEP_GEMM_E8M0="0",
               VLLM_WORKER_MULTIPROC_METHOD="spawn", VLLM_PLUGINS="aleph_alpha_inference",
               VLLM_ALLOW_INSECURE_SERIALIZATION="1")
    env.pop("PYTEST_PLUGINS", None)
    # RPC is local, for the inspect_worker callable only. No server is exposed.
    env["PYTHONPATH"] = os.pathsep.join((str(root), str(Path(__file__).resolve().parents[2])))
    return env


def bounded_worker(root, mode, scratch, timeout):
    require(type(timeout) is int and 1 <= timeout <= MAX_SECONDS, "Timeout must be 1..900 seconds")
    result_path = scratch / "worker.json"
    command = [sys.executable, str(Path(__file__).resolve()), "--_worker", "--mode", mode,
               "--upstream", str(root), "--out", str(result_path)]
    process = subprocess.Popen(command, env=worker_env(root), start_new_session=True)
    try:
        code = process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        return {"status": "timeout", "error": "Qualification exceeded wall-clock bound"}
    finally:
        # Kill the whole local process group, including orphaned engine workers.
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait()
    if not result_path.exists():
        return {"status": "failed", "error": "Worker exited without result", "exit_code": code}
    result = json.loads(result_path.read_text())
    require(code == 0 or result.get("status") == "failed", "Worker exit/result mismatch")
    require(result.get("status") in ("passed", "failed"), "Invalid worker status")
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--upstream", type=Path, default=Path("/workspace/kolibri/upstream"))
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--mode", choices=("gpu", "parser"), default="gpu")
    parser.add_argument("--timeout-seconds", type=int, default=MAX_SECONDS)
    parser.add_argument("--_worker", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if not 1 <= args.timeout_seconds <= MAX_SECONDS:
        parser.error("--timeout-seconds must be 1..900")
    root = args.upstream.resolve()
    started = time.monotonic()
    result = {"schema": "kolibri-tiny-qualification-v1", "mode": args.mode,
              "status": "failed", "expected_versions": VERSIONS,
              "scientific_generation": False, "random_model_accuracy_claim": False}
    # Exclusive creation preserves prior successes and failures; retries need a new path.
    with args.out.open("x") as output:
        try:
            if args._worker:
                # The parent owns this directory, so even SIGKILL removes weights.
                qualify(root, args.mode, args.out.parent, result)
            else:
                with tempfile.TemporaryDirectory(prefix="kolibri-smoke-") as directory:
                    result.update(bounded_worker(root, args.mode, Path(directory), args.timeout_seconds))
        except Exception as exc:
            result.update(status="failed", error=f"{type(exc).__name__}: {exc}"[:1200])
        result["elapsed_seconds"] = round(time.monotonic() - started, 3)
        result["timeout_seconds"] = args.timeout_seconds
        json.dump(result, output, sort_keys=True, separators=(",", ":"), allow_nan=False)
        output.write("\n")
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())

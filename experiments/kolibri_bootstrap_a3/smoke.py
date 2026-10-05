"""Inspect official post-load FP8 storage without changing inference kernels."""
from __future__ import annotations

import argparse
import hashlib
import inspect
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time

from experiments.kolibri_swap import gpu_smoke as original

require = original.require


def typename(value):
    return type(value).__module__ + "." + type(value).__qualname__


def diagnostics(model):
    """Capture every named module before testing any storage assumption."""
    rows = []
    for name, module in model.named_modules():
        method = getattr(module, "quant_method", None)
        kernel = getattr(method, "fp8_linear", None)
        tensors = dict(module.named_parameters(recurse=False))
        tensors.update(dict(module.named_buffers(recurse=False)))
        rows.append({"name": name, "type": typename(module),
                     "quant_method": typename(method) if method is not None else None,
                     "linear_kernel": typename(kernel) if kernel is not None else None,
                     "moe_backend": str(getattr(method, "fp8_backend", None)),
                     "tensors": {key: {"dtype": str(value.dtype), "shape": list(value.shape),
                                       "device": str(value.device)}
                                 for key, value in sorted(tensors.items())}})
    return rows


def linear_specs(model):
    for index, layer in enumerate(model.model.layers):
        prefix = f"model.layers.{index}."
        for name, module, parts in (
            ("self_attn.qkv_proj", layer.self_attn.qkv_proj,
             ["self_attn." + letter + "_proj" for letter in "qkv"]),
            ("self_attn.o_proj", layer.self_attn.o_proj, ["self_attn.o_proj"]),
            ("mlp.shared_experts.gate_up_proj", layer.mlp.shared_experts.gate_up_proj,
             ["mlp.shared_experts.gate_proj", "mlp.shared_experts.up_proj"]),
            ("mlp.shared_experts.down_proj", layer.mlp.shared_experts.down_proj,
             ["mlp.shared_experts.down_proj"]),
        ):
            yield prefix + name, module, [prefix + part for part in parts]


def same_tensor(actual, expected, name):
    import torch
    require(actual.dtype == expected.dtype and actual.shape == expected.shape
            and torch.equal(actual.detach().contiguous().view(torch.uint8),
                            expected.detach().contiguous().view(torch.uint8)),
            name + ": loaded tensor differs from checkpoint/operator reconstruction")


def reference_layer(tensors, parts, device):
    import torch
    weights = [tensors[p + ".weight"] for p in parts]
    scales = [tensors[p + ".weight_scale_inv"] for p in parts]
    require(all(w.dtype == torch.float8_e4m3fn and w.ndim == 2
                and bool(torch.isfinite(w.float()).all()) for w in weights), "Checkpoint is not finite E4M3FN")
    require(all(s.dtype == torch.float32 and bool(torch.isfinite(s).all())
                and bool((s > 0).all()) and list(s.shape) == [w.shape[0] // 128, w.shape[1] // 128]
                for w, s in zip(weights, scales)), "Checkpoint block scales invalid")
    ref = torch.nn.Module()
    weight = torch.cat([w.view(torch.uint8) for w in weights], dim=0).view(torch.float8_e4m3fn).to(device)
    scale = torch.cat(scales, dim=0).to(device)
    ref.register_parameter("weight", torch.nn.Parameter(weight, requires_grad=False))
    ref.register_parameter("weight_scale_inv", torch.nn.Parameter(scale, requires_grad=False))
    ref.input_size_per_partition, ref.output_size_per_partition = weight.shape[1], weight.shape[0]
    ref.logical_widths = [w.shape[0] for w in weights]
    ref.orig_dtype, ref.weight_block_size = torch.bfloat16, [128, 128]
    return ref


def check_linear(name, layer, reference, method_class, marlin_class):
    """Re-run the official preparation on an independent checkpoint copy only."""
    import torch
    method = layer.quant_method
    require(type(method) is method_class and method.block_quant
            and method.quant_config.is_checkpoint_fp8_serialized
            and method.weight_block_size == [128, 128], name + ": wrong FP8 method")
    require(layer.orig_dtype == torch.bfloat16 and layer.weight_block_size == [128, 128]
            and layer.input_size_per_partition == reference.input_size_per_partition
            and layer.output_size_per_partition == reference.output_size_per_partition,
            name + ": wrong geometry or original dtype")
    kernel = method.fp8_linear
    if type(kernel) is marlin_class:
        require(method.use_marlin and kernel.block_quant and not kernel.size_k_first
                and kernel.marlin_input_dtype is None, name + ": wrong Marlin FP8 mode")
        kernel.process_weights_after_loading(reference)
        require(reference.weight.dtype == torch.int32 and reference.weight_scale_inv.dtype == torch.bfloat16,
                name + ": unexpected official Marlin packing")
        require(layer.workspace.is_cuda and layer.workspace.numel() > 0
                and layer.workspace.dtype == torch.int32, name + ": missing Marlin workspace")
        storage = "official_marlin_e4m3fn_packed_int32"
    else:
        require(not method.use_marlin and layer.weight.dtype == torch.float8_e4m3fn
                and layer.weight_scale_inv.dtype == torch.float32,
                name + ": unknown or non-FP8 linear storage")
        storage = "native_e4m3fn_fp32_block_scales"
    same_tensor(layer.weight, reference.weight, name + ".weight")
    same_tensor(layer.weight_scale_inv, reference.weight_scale_inv, name + ".weight_scale_inv")
    return {"name": name, "storage": storage, "kernel": typename(kernel),
            "exact_checkpoint_reconstruction": True}


def inspect_worker(worker):
    """Diagnostics survive failures; no live layer or process globals are patched."""
    import torch
    import vllm.envs as envs
    from safetensors.torch import load_file
    from aleph_alpha_inference.kolibri1 import Kolibri1ForCausalLM, sigmoid_logit_add_routing
    from vllm.model_executor.layers.fused_moe.router.custom_routing_router import CustomRoutingRouter
    from vllm.model_executor.layers.quantization.fp8 import Fp8LinearMethod
    from vllm.model_executor.kernels.linear.scaled_mm.marlin import MarlinFP8ScaledMMLinearKernel

    model, cfg = worker.model_runner.model, worker.vllm_config
    result = {"status": "failed", "modules": diagnostics(model), "linears": []}
    print(json.dumps({"schema": "kolibri-a3-module-diagnostics-v1", "modules": result["modules"]}), flush=True)
    try:
        result["operator_sources"] = {cls.__module__: hashlib.sha256(Path(inspect.getfile(cls)).read_bytes()).hexdigest()
                                      for cls in (Fp8LinearMethod, MarlinFP8ScaledMMLinearKernel)}
        require(isinstance(model, Kolibri1ForCausalLM), "Not the plugin Kolibri architecture")
        require(not envs.VLLM_BATCH_INVARIANT, "Batch-invariant dequantization fallback is not qualified")
        require(cfg.model_config.enforce_eager and cfg.model_config.dtype == torch.bfloat16,
                "Eager/BF16 runtime config mismatch")
        require(cfg.cache_config.cache_dtype == "fp8" and cfg.model_config.max_model_len == 512,
                "KV/context config mismatch")
        require(model.quant_config.weight_block_size == [128, 128], "Wrong FP8 block config")
        require(model.quant_config.is_checkpoint_fp8_serialized, "Not serialized FP8")
        layers = list(model.model.layers)
        require(len(layers) == 6, "Wrong runtime layer count")
        tensors = load_file(str(Path(cfg.model_config.model) / "model.safetensors"))
        errors = []
        for name, linear, parts in linear_specs(model):
            try:
                reference = reference_layer(tensors, parts, linear.weight.device)
                result["linears"].append(check_linear(name, linear, reference, Fp8LinearMethod,
                                                     MarlinFP8ScaledMMLinearKernel))
            except Exception as exc:
                errors.append(name + ": " + type(exc).__name__ + ": " + str(exc)[:500])
        result["linear_errors"] = errors
        require(not errors and len(result["linears"]) == 24, "FP8 linear reconstruction failed")
        backends, kv_dtypes = set(), set()
        # Original router/norm/expert/KV invariants, unchanged; only linear storage differs.
        for index, layer in enumerate(layers):
            attn, moe = layer.self_attn, layer.mlp
            experts = moe.experts.routed_experts
            for name in ("w13", "w2"):
                require(getattr(experts, name + "_weight").dtype == torch.float8_e4m3fn,
                        f"layer{index}.{name}: expert is not FP8")
                require(getattr(experts, name + "_weight_scale_inv").dtype == torch.float32,
                        f"layer{index}.{name}: expert scale is not FP32")
            require(moe.gate.weight.dtype in (torch.bfloat16, torch.float32), "Quantized router")
            for norm in (attn.q_norm, attn.k_norm, layer.input_layernorm,
                         layer.post_attention_layernorm, layer.post_attn_norm, layer.post_ffn_norm):
                require(norm.weight.dtype == torch.bfloat16, "Quantized norm")
            router = moe.experts.router
            require(isinstance(router, CustomRoutingRouter) and not router.renormalize,
                    "Plugin custom router missing or renormalized")
            require(router.custom_routing_function.func is sigmoid_logit_add_routing,
                    "Different custom routing function")
            logits = torch.sin(torch.arange(32 * 8, device="cuda", dtype=torch.float32).reshape(32, 8)) * 3
            weights, ids = router._compute_routing(torch.zeros(32, 256, device="cuda"), logits, None)
            bias = moe.gate.e_score_correction_bias
            require(bias.dtype == torch.float32 and bool(torch.isfinite(bias).all()) and bool(bias.any()),
                    "Routing correction bias missing or invalid")
            expected = torch.topk(logits + bias, k=2, dim=-1).indices
            require(torch.equal(ids.long(), expected), "Loaded router expert selection mismatch")
            require(torch.allclose(weights, torch.sigmoid(logits).gather(1, expected)), "Loaded router weights mismatch")
            cache = attn.attn.kv_cache
            require(attn.attn.kv_cache_dtype == "fp8" and cache.numel() > 0 and cache.is_cuda
                    and cache.element_size() == 1 and cache.dtype in (torch.uint8, torch.float8_e4m3fn),
                    "KV storage is not FP8")
            backends.add(attn.attn.attn_backend.get_name())
            kv_dtypes.add(str(cache.dtype))
        require(model.lm_head.weight.dtype == torch.bfloat16 and model.model.embed_tokens.weight.dtype == torch.bfloat16,
                "Quantized head/embedding")
        result.update(status="passed", layers=6, custom_routing_layers=6, fp8_weights=True,
                      checkpoint_fp32_block_scales=True, kv_storage_dtypes=sorted(kv_dtypes),
                      attention_backends=sorted(backends))
    except Exception as exc:
        result["error"] = type(exc).__name__ + ": " + str(exc)[:1200]
    return result


def qualify(root, mode, scratch, result):
    require(__debug__, "Python optimization disables upstream assertions")
    result["upstream"] = original.verify_upstream(root)
    result["versions"] = original.installed_versions()
    original.verify_versions(result["versions"])
    sys.path.insert(0, str(root))
    import aleph_alpha_inference
    require(Path(aleph_alpha_inference.__file__).resolve() == root / "aleph_alpha_inference/__init__.py",
            "Plugin imported outside verified checkout")
    aleph_alpha_inference.register()
    result["parser"] = original.parser_checks(root)
    if mode == "gpu":
        import torch
        from vllm import LLM, SamplingParams
        require(torch.cuda.is_available(), "CUDA unavailable; GPU qualification not run")
        require(torch.cuda.get_device_capability() >= (8, 9), "FP8-capable Ada or newer GPU required")
        routing = original.load_source(root, "tests/test_kolibri1.py")
        routing.test_routing_semantics()
        with torch.device("cuda"):
            routing.test_routing_semantics()
        checkpoint = scratch / "tiny"
        checkpoint.mkdir()
        gpu = result["gpu"] = {"device": torch.cuda.get_device_name(), "cuda": torch.version.cuda,
            "capability": list(torch.cuda.get_device_capability()), "official_routing_cpu_cuda": True,
            "checkpoint": original.write_tiny_checkpoint(root, checkpoint), "llm_options": original.LLM_OPTIONS}
        llm = LLM(model=str(checkpoint), **original.LLM_OPTIONS)
        outputs = llm.generate([{"prompt_token_ids": list(p)} for p in original.PROMPTS],
            SamplingParams(max_tokens=original.MAX_TOKENS, temperature=0.0, logprobs=5,
                           ignore_eos=True, detokenize=False, seed=original.SEED), use_tqdm=False)
        gpu["forward"] = original.validate_outputs(outputs)
        gpu["workers"] = llm.collective_rpc(inspect_worker)
        require(len(gpu["workers"]) == 1 and gpu["workers"][0]["status"] == "passed",
                "Named worker qualification failed; see saved diagnostics")
        torch.cuda.synchronize()
    result["status"] = "passed"


def bounded_worker(root, mode, scratch, timeout):
    require(type(timeout) is int and 1 <= timeout <= original.MAX_SECONDS, "Timeout must be 1..900 seconds")
    path = scratch / "worker.json"
    command = [sys.executable, "-m", "experiments.kolibri_bootstrap_a3.smoke", "--_worker", "--mode", mode,
               "--upstream", str(root), "--out", str(path)]
    process = subprocess.Popen(command, env=original.worker_env(root), start_new_session=True)
    try:
        code = process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        return {"status": "timeout", "error": "Qualification exceeded wall-clock bound"}
    finally:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait()
    if not path.exists():
        return {"status": "failed", "error": "Worker exited without result", "exit_code": code}
    result = json.loads(path.read_bytes())
    require(code == 0 or result.get("status") == "failed", "Worker exit/result mismatch")
    require(result.get("status") in ("passed", "failed"), "Invalid worker status")
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--upstream", type=Path, default=Path("/workspace/kolibri/upstream"))
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--mode", choices=("gpu", "parser"), default="gpu")
    parser.add_argument("--timeout-seconds", type=int, default=original.MAX_SECONDS)
    parser.add_argument("--_worker", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    require(1 <= args.timeout_seconds <= original.MAX_SECONDS, "Timeout must be 1..900 seconds")
    require(not args.out.exists(), "Prior smoke receipt cannot be overwritten")
    started = time.monotonic()
    result = {"schema": "kolibri-tiny-qualification-v1", "amendment": "kolibri-bootstrap-a3-v1",
              "mode": args.mode, "status": "failed", "expected_versions": original.VERSIONS,
              "scientific_generation": False, "random_model_accuracy_claim": False}
    try:
        if args._worker:
            qualify(args.upstream.resolve(), args.mode, args.out.parent, result)
        else:
            with tempfile.TemporaryDirectory(prefix="kolibri-a3-smoke-") as scratch:
                result.update(bounded_worker(args.upstream.resolve(), args.mode, Path(scratch), args.timeout_seconds))
    except Exception as exc:
        result.update(status="failed", error=type(exc).__name__ + ": " + str(exc)[:1200])
    result["elapsed_seconds"] = round(time.monotonic() - started, 3)
    result["timeout_seconds"] = args.timeout_seconds
    # A1 handles in-progress reads; publish complete JSON atomically and exclusively.
    temporary = args.out.with_name(args.out.name + ".complete")
    with temporary.open("x") as handle:
        json.dump(result, handle, sort_keys=True, separators=(",", ":"))
        handle.write("\n"); handle.flush(); os.fsync(handle.fileno())
    os.link(temporary, args.out)
    temporary.unlink()
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())

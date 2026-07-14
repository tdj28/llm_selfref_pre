"""GPU/runtime primitives for the fresh realization validation.

The model loader and single-use hook are adapted from the already exercised
``consciousness_readout_validation`` backend.  Study identity, randomization,
prompts, vectors, storage, and every outcome are successor-local.  In particular, J
transport below receives the realized central edit reconstructed from captured
``post - pre`` tensors; it never receives the nominal requested dose.
"""

from __future__ import annotations

import gc
import hashlib
import json
import math
import os
import platform
import statistics
from contextlib import AbstractContextManager, ExitStack
from dataclasses import dataclass
from datetime import datetime, timezone
from importlib import metadata as importlib_metadata
from pathlib import Path
from typing import Any, Mapping, Sequence

from . import protocol


class V2RuntimeError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message


def _torch() -> Any:
    try:
        import torch
    except ImportError as exc:  # pragma: no cover - GPU environment only
        raise V2RuntimeError("torch_missing", "PyTorch is required") from exc
    return torch


def tensor_sha256(value: Any) -> str:
    """Hash dtype, shape, and exact contiguous bytes, including BF16."""

    torch = _torch()
    if not isinstance(value, torch.Tensor):
        raise TypeError("tensor_sha256 expects a torch.Tensor")
    cpu = value.detach().contiguous().to(device="cpu")
    digest = hashlib.sha256()
    digest.update(
        protocol.canonical_json_bytes(
            {"dtype": str(cpu.dtype), "shape": list(cpu.shape)}
        )
    )
    digest.update(b"\0")
    raw = cpu.view(torch.uint8).reshape(-1)
    for start in range(0, int(raw.numel()), 8 * 1024 * 1024):
        digest.update(raw[start : start + 8 * 1024 * 1024].numpy().tobytes())
    return digest.hexdigest()


def tensor_rms(value: Any) -> float:
    torch = _torch()
    result = float(torch.sqrt(torch.mean(value.detach().float().square())).item())
    if not math.isfinite(result) or result <= 0.0:
        raise V2RuntimeError("tensor_rms", "tensor RMS is non-finite or non-positive")
    return result


def _metric_pair(left: Any, right: Any) -> tuple[Any, Any]:
    """Co-locate metric tensors without changing either tensor's values."""

    left_device = getattr(left, "device", None)
    right_device = getattr(right, "device", None)
    if left_device is not None and right_device is not None and left_device != right_device:
        right = right.to(device=left_device)
    return left, right


def relative_rmse(observed: Any, expected: Any) -> float:
    observed, expected = _metric_pair(observed, expected)
    torch = _torch()
    left = observed.detach().float().reshape(-1)
    right = expected.detach().float().reshape(-1)
    if left.shape != right.shape or left.numel() == 0:
        raise V2RuntimeError("metric_shape", "relative-RMSE tensors differ")
    numerator = torch.sqrt(torch.mean((left - right).square()))
    denominator = torch.sqrt(torch.mean(right.square())).clamp_min(1e-30)
    result = float((numerator / denominator).item())
    if not math.isfinite(result):
        raise V2RuntimeError("metric_nonfinite", "relative RMSE is non-finite")
    return result


def _cosine_similarity(left: Any, right: Any) -> float:
    torch = _torch()
    a = left.detach().float().reshape(-1)
    b = right.detach().float().reshape(-1)
    if a.shape != b.shape or a.numel() == 0:
        raise V2RuntimeError("metric_shape", "cosine tensors differ")
    denominator = torch.linalg.vector_norm(a) * torch.linalg.vector_norm(b)
    if float(denominator.item()) <= 0.0:
        raise V2RuntimeError("metric_degenerate", "cosine denominator is zero")
    result = float(torch.dot(a, b).item() / denominator.item())
    if not math.isfinite(result):
        raise V2RuntimeError("metric_nonfinite", "cosine is non-finite")
    return max(-1.0, min(1.0, result))


def cosine(left: Any, right: Any) -> float:
    left, right = _metric_pair(left, right)
    return _cosine_similarity(left, right)


def pearson(left: Any, right: Any) -> float:
    left, right = _metric_pair(left, right)
    torch = _torch()
    a = left.detach().float().reshape(-1)
    b = right.detach().float().reshape(-1)
    if a.shape != b.shape or a.numel() < 2:
        raise V2RuntimeError(
            "metric_shape", "Pearson vectors differ or are too short"
        )
    a = a - a.mean()
    b = b - b.mean()
    denominator = torch.linalg.vector_norm(a) * torch.linalg.vector_norm(b)
    if float(denominator.item()) <= 0.0:
        raise V2RuntimeError("metric_degenerate", "Pearson denominator is zero")
    result = float(torch.dot(a, b).item() / denominator.item())
    if not math.isfinite(result):
        raise V2RuntimeError("metric_nonfinite", "Pearson is non-finite")
    return max(-1.0, min(1.0, result))


def _extract_hidden(output: Any) -> Any:
    torch = _torch()
    if isinstance(output, torch.Tensor):
        return output
    if isinstance(output, (tuple, list)) and output and isinstance(output[0], torch.Tensor):
        return output[0]
    raise V2RuntimeError("hook_output", "transformer block output has no hidden tensor")


def _replace_hidden(output: Any, hidden: Any) -> Any:
    torch = _torch()
    if isinstance(output, torch.Tensor):
        return hidden
    if isinstance(output, tuple):
        return (hidden, *output[1:])
    if isinstance(output, list):
        return [hidden, *output[1:]]
    raise V2RuntimeError("hook_output", "cannot replace transformer hidden tensor")


@dataclass
class HookMeasurement:
    pre: Any
    post: Any
    vector: Any
    forward_id: str


class SingleUseResidualHook(AbstractContextManager["SingleUseResidualHook"]):
    """One explicitly armed, single-position residual addition."""

    def __init__(self, layer_module: Any, vector: Any, *, forward_id: str) -> None:
        torch = _torch()
        if not isinstance(forward_id, str) or not forward_id:
            raise ValueError("forward_id must be non-empty")
        if not isinstance(vector, torch.Tensor) or vector.ndim != 1:
            raise TypeError("intervention vector must be one-dimensional")
        if not vector.is_floating_point() or not bool(torch.isfinite(vector).all()):
            raise V2RuntimeError("hook_vector", "intervention vector is invalid")
        self.layer_module = layer_module
        self.vector = vector.detach().clone()
        self.forward_id = forward_id
        self.handle: Any | None = None
        self.armed = False
        self.fire_count = 0
        self.measurement: HookMeasurement | None = None

    def __enter__(self) -> "SingleUseResidualHook":
        if self.handle is not None:
            raise V2RuntimeError("hook_reuse", "hook is already registered")
        self.handle = self.layer_module.register_forward_hook(self._hook)
        self.armed = True
        return self

    def _hook(self, _module: Any, _inputs: Any, output: Any) -> Any:
        torch = _torch()
        if not self.armed or self.fire_count:
            raise V2RuntimeError("hook_unarmed", "hook fired outside its one armed call")
        hidden = _extract_hidden(output)
        if hidden.ndim != 3 or hidden.shape[0] != 1 or hidden.shape[1] != 1:
            raise V2RuntimeError(
                "hook_shape", "edited forward must contain one batch/token position"
            )
        if hidden.shape[-1] != self.vector.numel():
            raise V2RuntimeError("hook_width", "vector width differs from residual width")
        vector = self.vector.to(device=hidden.device, dtype=hidden.dtype)
        pre = hidden.detach().clone()
        post = hidden + vector.view(1, 1, -1)
        if not bool(torch.isfinite(post).all()):
            raise V2RuntimeError("hook_nonfinite", "post-edit residual is non-finite")
        self.fire_count = 1
        self.armed = False
        self.measurement = HookMeasurement(
            pre=pre.to("cpu"),
            post=post.detach().clone().to("cpu"),
            vector=vector.detach().clone().to("cpu"),
            forward_id=self.forward_id,
        )
        return _replace_hidden(output, post)

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> bool:
        if self.handle is not None:
            self.handle.remove()
            self.handle = None
        if exc_type is None and (
            self.armed or self.fire_count != 1 or self.measurement is None
        ):
            raise V2RuntimeError("hook_count", "hook did not fire exactly once")
        return False


def clone_kv_cache(cache: Any) -> Any:
    """Clone a Transformers cache without aliasing mutable tensors."""

    import copy

    torch = _torch()

    def clone_tree(value: Any) -> Any:
        if isinstance(value, torch.Tensor):
            return value.detach().clone()
        if isinstance(value, tuple):
            return tuple(clone_tree(item) for item in value)
        if isinstance(value, list):
            return [clone_tree(item) for item in value]
        if isinstance(value, Mapping):
            return {key: clone_tree(item) for key, item in value.items()}
        return copy.deepcopy(value)

    converter = getattr(cache, "to_legacy_cache", None)
    constructor = getattr(type(cache), "from_legacy_cache", None)
    if callable(converter) and callable(constructor):
        return constructor(clone_tree(converter()))
    return clone_tree(cache)


def _rms_norm(hidden: Any, weight: Any, eps: float) -> Any:
    torch = _torch()
    values = hidden.float()
    normalized = values * torch.rsqrt(
        values.square().mean(dim=-1, keepdim=True) + eps
    )
    return normalized.to(dtype=weight.dtype) * weight


def _selected_logits(normalized: Any, lm_head_weight: Any, token_ids: Sequence[int]) -> Any:
    torch = _torch()
    ids = torch.tensor(list(token_ids), dtype=torch.long, device=lm_head_weight.device)
    rows = lm_head_weight.index_select(0, ids)
    return (normalized.to(dtype=rows.dtype) @ rows.T).float()


def render_prompt(tokenizer: Any, prompt_id: str) -> tuple[int, ...]:
    payload = protocol.prompt_payload(prompt_id)
    messages = (
        {"role": "system", "content": payload["system"]},
        {"role": "user", "content": payload["user"]},
    )
    token_ids = tokenizer.apply_chat_template(
        list(messages), tokenize=True, add_generation_prompt=True
    )
    if hasattr(token_ids, "tolist"):
        token_ids = token_ids.tolist()
    if token_ids and isinstance(token_ids[0], list):
        if len(token_ids) != 1:
            raise V2RuntimeError("tokenizer", "chat template produced a batch")
        token_ids = token_ids[0]
    result = tuple(int(value) for value in token_ids)
    if len(result) < 2 or min(result) < 0 or max(result) >= protocol.VOCAB_SIZE:
        raise V2RuntimeError("tokenizer", f"invalid rendered tokens for {prompt_id}")
    return result


def token_ids_sha256(token_ids: Sequence[int]) -> str:
    return protocol.canonical_sha256([int(value) for value in token_ids])


def deterministic_direction(layer: int, direction: int) -> Any:
    import numpy as np

    torch = _torch()
    if layer not in protocol.STAGE_A_LAYERS or direction not in protocol.STAGE_A_DIRECTIONS:
        raise V2RuntimeError("direction", "direction coordinate is outside Stage A")
    rng = np.random.Generator(
        np.random.PCG64(protocol.seed64("stage-a-direction", layer, direction))
    )
    values = rng.standard_normal(protocol.WIDTH).astype(np.float32)
    values /= max(float(np.sqrt(np.mean(values * values))), 1e-30)
    result = torch.from_numpy(values)
    if not bool(torch.isfinite(result).all()):
        raise V2RuntimeError("direction", "direction is non-finite")
    return result


def random_j_parameters(layer: int, index: int, *, device: Any) -> tuple[Any, ...]:
    import numpy as np

    torch = _torch()
    if layer not in protocol.J_LAYERS or not 0 <= index < protocol.RANDOM_J_COUNT:
        raise V2RuntimeError("random_j", "random-J coordinate is outside v2")
    rng = np.random.Generator(
        np.random.PCG64(protocol.seed64("random-j-v1", layer, index))
    )
    input_perm = rng.permutation(protocol.WIDTH).astype(np.int64)
    input_sign = rng.choice(np.array([-1.0, 1.0], dtype=np.float32), protocol.WIDTH)
    output_perm = rng.permutation(protocol.WIDTH).astype(np.int64)
    output_sign = rng.choice(np.array([-1.0, 1.0], dtype=np.float32), protocol.WIDTH)
    return (
        torch.from_numpy(input_perm).to(device=device),
        torch.from_numpy(input_sign).to(device=device),
        torch.from_numpy(output_perm).to(device=device),
        torch.from_numpy(output_sign).to(device=device),
    )


def apply_random_j(source: Any, matrix: Any, *, layer: int, index: int) -> Any:
    input_perm, input_sign, output_perm, output_sign = random_j_parameters(
        layer, index, device=source.device
    )
    scrambled = source[..., input_perm] * input_sign.to(dtype=source.dtype)
    transported = scrambled.to(dtype=matrix.dtype) @ matrix.T
    return transported[..., output_perm] * output_sign.to(dtype=transported.dtype)


def fixed_token_panel() -> tuple[int, ...]:
    """A frozen broad 2,048-token panel, independent of tokenizer text."""

    # 7,919 is coprime to 128,256, so the first 2,048 values are unique.
    offset = protocol.seed64("fixed-token-panel") % protocol.VOCAB_SIZE
    return tuple(
        int((offset + 7_919 * index) % protocol.VOCAB_SIZE)
        for index in range(2_048)
    )


@dataclass(frozen=True)
class ArcTrace:
    token_ids_sha256: str
    residual_by_layer: Mapping[int, Any]
    final_residual: Any
    pre_edit: Any | None
    post_edit: Any | None
    requested_vector: Any | None
    hook_fire_count: int


class ArcPromptSession:
    """Branchable one-token session retaining every released J source layer."""

    def __init__(self, backend: "V2Backend", token_ids: Sequence[int]) -> None:
        torch = backend.torch
        normalized = tuple(int(value) for value in token_ids)
        self.backend = backend
        self.token_ids = normalized
        self.token_ids_sha256 = token_ids_sha256(normalized)
        prefix = torch.tensor([normalized[:-1]], dtype=torch.long, device=backend.device)
        with torch.inference_mode():
            output = backend._model_forward(
                input_ids=prefix, use_cache=True, return_dict=True
            )
        cache = getattr(output, "past_key_values", None)
        if cache is None:
            raise V2RuntimeError("kv_cache", "prefix forward returned no cache")
        self.prefix_cache = cache
        self.last_token = torch.tensor(
            [[normalized[-1]]], dtype=torch.long, device=backend.device
        )
        self.clean = self._run_last(edit_layer=None, vector=None, forward_id="clean")

    def _run_last(
        self,
        *,
        edit_layer: int | None,
        vector: Any | None,
        forward_id: str,
    ) -> ArcTrace:
        torch = self.backend.torch
        captured: dict[int, Any] = {}
        counts = {layer: 0 for layer in protocol.J_LAYERS}
        final: list[Any] = []

        def layer_hook(layer: int) -> Any:
            def hook(_module: Any, _inputs: Any, output: Any) -> None:
                counts[layer] += 1
                if counts[layer] != 1:
                    raise V2RuntimeError("capture_count", f"layer {layer} fired twice")
                hidden = _extract_hidden(output)
                if tuple(hidden.shape) != (1, 1, protocol.WIDTH):
                    raise V2RuntimeError("capture_shape", f"layer {layer} shape differs")
                if hidden.dtype != torch.bfloat16:
                    raise V2RuntimeError("capture_dtype", f"layer {layer} is not BF16")
                captured[layer] = hidden[0, 0].detach().clone()

            return hook

        def final_hook(_module: Any, inputs: Any) -> None:
            if final:
                raise V2RuntimeError("capture_count", "final capture fired twice")
            hidden = inputs[0]
            if tuple(hidden.shape) != (1, 1, protocol.WIDTH):
                raise V2RuntimeError("capture_shape", "final residual shape differs")
            final.append(hidden[0, 0].detach().clone())

        edit_context: Any | None = None
        cache = clone_kv_cache(self.prefix_cache)
        with ExitStack() as stack:
            handles = [
                self.backend.model.model.layers[layer].register_forward_hook(
                    layer_hook(layer)
                )
                for layer in protocol.J_LAYERS
            ]
            for handle in reversed(handles):
                stack.callback(handle.remove)
            final_handle = self.backend.model.model.norm.register_forward_pre_hook(final_hook)
            stack.callback(final_handle.remove)
            if edit_layer is not None:
                if edit_layer not in protocol.J_LAYERS or vector is None:
                    raise V2RuntimeError("edit", "malformed edit request")
                # Capture hooks are registered first, so captured[edit_layer] is
                # the pre-edit source.  The single-use hook supplies exact post.
                edit_context = stack.enter_context(
                    SingleUseResidualHook(
                        self.backend.model.model.layers[edit_layer],
                        vector,
                        forward_id=forward_id,
                    )
                )
            with torch.inference_mode():
                self.backend._model_forward(
                    input_ids=self.last_token,
                    past_key_values=cache,
                    use_cache=False,
                    return_dict=True,
                )

        if set(captured) != set(protocol.J_LAYERS) or any(value != 1 for value in counts.values()):
            raise V2RuntimeError("capture_incomplete", "J-layer arc is incomplete")
        if len(final) != 1:
            raise V2RuntimeError("capture_incomplete", "final residual is missing")
        # One device-to-host transfer for the complete arc.
        stacked = torch.stack([captured[layer] for layer in protocol.J_LAYERS] + final)
        stacked = stacked.to(device="cpu", dtype=torch.bfloat16).contiguous()
        by_layer = {layer: stacked[index] for index, layer in enumerate(protocol.J_LAYERS)}
        final_cpu = stacked[-1]
        if edit_context is None:
            return ArcTrace(
                token_ids_sha256=self.token_ids_sha256,
                residual_by_layer=by_layer,
                final_residual=final_cpu,
                pre_edit=None,
                post_edit=None,
                requested_vector=None,
                hook_fire_count=0,
            )
        measurement = edit_context.measurement
        if measurement is None or edit_context.fire_count != 1:
            raise V2RuntimeError("hook_count", "edit did not fire exactly once")
        return ArcTrace(
            token_ids_sha256=self.token_ids_sha256,
            residual_by_layer=by_layer,
            final_residual=final_cpu,
            pre_edit=measurement.pre[0, 0].contiguous(),
            post_edit=measurement.post[0, 0].contiguous(),
            requested_vector=measurement.vector.contiguous(),
            hook_fire_count=int(edit_context.fire_count),
        )

    def edited(self, layer: int, vector: Any, *, forward_id: str) -> ArcTrace:
        return self._run_last(edit_layer=layer, vector=vector, forward_id=forward_id)

    def close(self) -> None:
        self.prefix_cache = None
        gc.collect()


MINIMUM_GPU_BYTES = 160 * 1024**3


def _finite_tensor(value: Any, *, label: str) -> None:
    torch = _torch()
    if not isinstance(value, torch.Tensor) or not bool(torch.isfinite(value).all()):
        raise V2RuntimeError("nonfinite", f"{label} is not a finite tensor")


def _observed_determinism_settings(torch: Any) -> dict[str, Any]:
    return {
        "seed": int(protocol.seed64("runtime") % (2**63 - 1)),
        "cublas_workspace_config": os.environ.get(
            protocol.CUBLAS_WORKSPACE_CONFIG_ENV
        ),
        "deterministic_algorithms": bool(torch.are_deterministic_algorithms_enabled()),
        "cuda_matmul_tf32": bool(torch.backends.cuda.matmul.allow_tf32),
        "cudnn_tf32": bool(torch.backends.cudnn.allow_tf32),
        "flash_sdp_enabled": bool(torch.backends.cuda.flash_sdp_enabled()),
        "mem_efficient_sdp_enabled": bool(torch.backends.cuda.mem_efficient_sdp_enabled()),
        "math_sdp_enabled": bool(torch.backends.cuda.math_sdp_enabled()),
    }


def _expected_determinism_settings() -> dict[str, Any]:
    return {
        "seed": int(protocol.seed64("runtime") % (2**63 - 1)),
        "cublas_workspace_config": protocol.CUBLAS_WORKSPACE_CONFIG_VALUE,
        "deterministic_algorithms": True,
        "cuda_matmul_tf32": False,
        "cudnn_tf32": False,
        "flash_sdp_enabled": False,
        "mem_efficient_sdp_enabled": False,
        "math_sdp_enabled": True,
    }


def validate_guest_launch_environment(
    *, ownership_receipt_sha256: str
) -> dict[str, str]:
    """Validate launcher-owned environment bindings without importing Torch."""

    ownership_hash = str(ownership_receipt_sha256)
    if len(ownership_hash) != 64 or any(
        character not in "0123456789abcdef" for character in ownership_hash
    ):
        raise V2RuntimeError(
            "guest_launch_ownership", "ownership receipt SHA-256 is malformed"
        )
    observed_image = os.environ.get(protocol.CONTAINER_IMAGE_ENV)
    if observed_image != protocol.CONTAINER_IMAGE_SPEC["immutable_reference"]:
        raise V2RuntimeError(
            "container_image",
            f"{protocol.CONTAINER_IMAGE_ENV} must equal the provider-attested digest",
        )
    observed_cublas = os.environ.get(protocol.CUBLAS_WORKSPACE_CONFIG_ENV)
    if observed_cublas != protocol.CUBLAS_WORKSPACE_CONFIG_VALUE:
        raise V2RuntimeError(
            "cublas_workspace_config",
            f"{protocol.CUBLAS_WORKSPACE_CONFIG_ENV} must equal the frozen setting",
        )
    observed_ownership = os.environ.get(protocol.GUEST_LAUNCH_OWNERSHIP_ENV)
    if observed_ownership != ownership_hash:
        raise V2RuntimeError(
            "guest_launch_ownership",
            "guest launch ownership binding differs from the validated receipt",
        )
    return {
        "container_image": observed_image,
        "cublas_workspace_config": observed_cublas,
        "ownership_receipt_sha256": observed_ownership,
    }


def _unique_suffix_key(state: Mapping[str, Any], suffix: str) -> str:
    matches = [key for key in state if key == suffix or key.endswith("." + suffix)]
    if len(matches) != 1:
        raise V2RuntimeError(
            "artifact_layout",
            f"expected one state key ending in {suffix!r}, found {matches}",
        )
    return matches[0]


def _resolve_sae_state(state: Mapping[str, Any]) -> dict[str, Any]:
    suffixes = (
        "encoder_linear.weight",
        "encoder_linear.bias",
        "decoder_linear.weight",
        "decoder_linear.bias",
    )
    keys = {suffix: _unique_suffix_key(state, suffix) for suffix in suffixes}
    if set(state) != set(keys.values()):
        raise V2RuntimeError(
            "sae_layout", "SAE state must contain exactly the four frozen tensors"
        )
    tensors = {suffix: state[key] for suffix, key in keys.items()}
    expected_shapes = {
        "encoder_linear.weight": (
            int(protocol.SAE_SPEC["feature_count"]),
            protocol.WIDTH,
        ),
        "encoder_linear.bias": (int(protocol.SAE_SPEC["feature_count"]),),
        "decoder_linear.weight": (
            protocol.WIDTH,
            int(protocol.SAE_SPEC["feature_count"]),
        ),
        "decoder_linear.bias": (protocol.WIDTH,),
    }
    for suffix, expected in expected_shapes.items():
        if tuple(getattr(tensors[suffix], "shape", ())) != expected:
            raise V2RuntimeError("sae_shape", f"{suffix} shape differs")
    return tensors


def _validate_j_lens_checkpoint_metadata(
    checkpoint: Mapping[str, Any],
) -> Mapping[Any, Any]:
    if not {"J", "n_prompts", "d_model"} <= set(checkpoint):
        raise V2RuntimeError("jlens_layout", "J-lens keys differ")
    if int(checkpoint["n_prompts"]) != int(
        protocol.J_LENS_SPEC["release_config"]["prompts_fitted"]
    ):
        raise V2RuntimeError("jlens_prompt_count", "J-lens fit count differs")
    if int(checkpoint["d_model"]) != protocol.WIDTH:
        raise V2RuntimeError("jlens_width", "J-lens width differs")
    raw_maps = checkpoint["J"]
    if not isinstance(raw_maps, Mapping):
        raise V2RuntimeError("jlens_layout", "J-lens map inventory differs")
    return raw_maps


class V2Backend:
    """Self-contained pinned BF16 loader with optional FP32 J shadows."""

    def __init__(
        self,
        *,
        model_snapshot: Path,
        sae_path: Path,
        j_lens_path: Path,
        tokenizer: Any,
        ownership_receipt_sha256: str,
        load_shadow_layers: Sequence[int] = (),
    ) -> None:
        launch_environment = validate_guest_launch_environment(
            ownership_receipt_sha256=ownership_receipt_sha256
        )
        observed = launch_environment["container_image"]
        torch = _torch()
        if not torch.cuda.is_available() or torch.cuda.device_count() != 1:
            raise V2RuntimeError("gpu_contract", "exactly one CUDA GPU is required")
        properties = torch.cuda.get_device_properties(0)
        if int(properties.total_memory) < MINIMUM_GPU_BYTES:
            raise V2RuntimeError(
                "gpu_memory", "the BF16 executor requires at least 160 GiB VRAM"
            )
        try:
            from transformers import AutoModelForCausalLM
        except ImportError as exc:  # pragma: no cover - GPU environment only
            raise V2RuntimeError("transformers_missing", "Transformers is required") from exc

        required_determinism = (
            "enable_flash_sdp",
            "enable_mem_efficient_sdp",
            "enable_math_sdp",
        )
        if any(not hasattr(torch.backends.cuda, name) for name in required_determinism):
            raise V2RuntimeError(
                "determinism_api", "required CUDA SDPA controls are unavailable"
            )
        seed = protocol.seed64("runtime") % (2**63 - 1)
        torch.manual_seed(seed)
        torch.cuda.manual_seed_all(seed)
        torch.use_deterministic_algorithms(True)
        torch.backends.cuda.matmul.allow_tf32 = False
        torch.backends.cudnn.allow_tf32 = False
        torch.backends.cuda.enable_flash_sdp(False)
        torch.backends.cuda.enable_mem_efficient_sdp(False)
        torch.backends.cuda.enable_math_sdp(True)
        if _observed_determinism_settings(torch) != _expected_determinism_settings():
            raise V2RuntimeError(
                "determinism_contract", "deterministic CUDA settings differ"
            )
        try:
            with torch.inference_mode():
                left = torch.tensor(
                    [[1.0, 2.0], [3.0, 4.0]],
                    dtype=torch.float32,
                    device="cuda:0",
                )
                right = torch.tensor(
                    [[5.0], [6.0]], dtype=torch.float32, device="cuda:0"
                )
                result = torch.mm(left, right)
        except RuntimeError as exc:
            raise V2RuntimeError(
                "deterministic_cublas", "deterministic CUDA matrix preflight failed"
            ) from exc
        if not bool(
            torch.equal(
                result.cpu(), torch.tensor([[17.0], [39.0]], dtype=torch.float32)
            )
        ):
            raise V2RuntimeError(
                "deterministic_cublas", "deterministic CUDA matrix preflight differs"
            )
        del left, right, result

        self.torch = torch
        self.device = torch.device("cuda:0")
        self.tokenizer = tokenizer
        self.container_image = observed
        self.total_forward_count = 0
        self.forward_count = 0
        self.first_forward_at_utc: str | None = None
        self.last_forward_at_utc: str | None = None
        self.model = AutoModelForCausalLM.from_pretrained(
            model_snapshot,
            local_files_only=True,
            trust_remote_code=False,
            dtype=torch.bfloat16,
            device_map={"": 0},
            low_cpu_mem_usage=True,
            attn_implementation="sdpa",
        )
        self.model.eval()
        for parameter in self.model.parameters():
            parameter.requires_grad_(False)
        config = self.model.config.get_text_config()
        if (
            int(config.hidden_size) != protocol.WIDTH
            or int(config.num_hidden_layers) != int(protocol.MODEL_SPEC["layer_count"])
            or len(self.model.model.layers) != int(protocol.MODEL_SPEC["layer_count"])
            or tuple(self.model.lm_head.weight.shape)
            != (protocol.VOCAB_SIZE, protocol.WIDTH)
        ):
            raise V2RuntimeError("model_shape", "model architecture differs")
        if next(self.model.parameters()).dtype != torch.bfloat16:
            raise V2RuntimeError("model_dtype", "model is not BF16")
        self.norm_weight = self.model.model.norm.weight
        self.rms_eps = float(config.rms_norm_eps)

        state = torch.load(sae_path, map_location="cpu", weights_only=True, mmap=True)
        sae = _resolve_sae_state(state)
        self.sae_encoder = sae["encoder_linear.weight"]
        self.sae_encoder_bias = sae["encoder_linear.bias"]
        self.sae_decoder = sae["decoder_linear.weight"]
        self.sae_decoder_bias = sae["decoder_linear.bias"]

        checkpoint = torch.load(
            j_lens_path, map_location="cpu", weights_only=True, mmap=True
        )
        raw_maps = _validate_j_lens_checkpoint_metadata(checkpoint)
        available = {int(layer) for layer in raw_maps}
        if not set(protocol.J_LAYERS) <= available:
            raise V2RuntimeError("jlens_layers", "a required J map is missing")
        self.j_maps: dict[int, Any] = {}
        for layer in protocol.J_LAYERS:
            raw = raw_maps[layer] if layer in raw_maps else raw_maps[str(layer)]
            if tuple(raw.shape) != (protocol.WIDTH, protocol.WIDTH):
                raise V2RuntimeError("jlens_shape", f"J[{layer}] shape differs")
            matrix = raw.to(
                device=self.device, dtype=torch.bfloat16, non_blocking=True
            ).contiguous()
            _finite_tensor(matrix, label=f"J[{layer}]")
            self.j_maps[layer] = matrix
        self._shadow_maps: dict[int, Any] = {}
        requested = tuple(int(layer) for layer in load_shadow_layers)
        if requested:
            for layer in requested:
                if layer not in protocol.STAGE_A_LAYERS:
                    raise V2RuntimeError("shadow_layer", "FP32 shadow layer is outside Stage A")
                raw = raw_maps[layer] if layer in raw_maps else raw_maps[str(layer)]
                self._shadow_maps[layer] = raw.to(
                    device=self.device, dtype=torch.float32, non_blocking=True
                ).contiguous()
        del checkpoint, raw_maps, state, sae
        gc.collect()

    @property
    def width(self) -> int:
        return protocol.WIDTH

    def _model_forward(self, **kwargs: Any) -> Any:
        timestamp = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        if self.forward_count == 0:
            self.first_forward_at_utc = timestamp
        self.forward_count += 1
        self.total_forward_count += 1
        self.last_forward_at_utc = timestamp
        return self.model(**kwargs)

    def start_runtime_interval(self) -> None:
        """Reset per-command counters without losing the lifetime counter."""

        self.forward_count = 0
        self.first_forward_at_utc = None
        self.last_forward_at_utc = None

    def j_matrix(self, layer: int) -> Any:
        if layer not in self.j_maps:
            raise V2RuntimeError("jlens_layer", f"unavailable J map {layer}")
        return self.j_maps[layer]

    def logits_from_final_state(self, state: Any, token_ids: Sequence[int]) -> Any:
        normalized = _rms_norm(
            state.to(device=self.device, dtype=self.norm_weight.dtype),
            self.norm_weight,
            self.rms_eps,
        )
        result = _selected_logits(normalized, self.model.lm_head.weight, token_ids).reshape(-1)
        _finite_tensor(result, label="selected logits")
        return result

    def capture_layer50_all_tokens(self, token_ids: Sequence[int]) -> Any:
        normalized = tuple(int(value) for value in token_ids)
        ids = self.torch.tensor([normalized], dtype=self.torch.long, device=self.device)
        captured: list[Any] = []

        def hook(_module: Any, _inputs: Any, output: Any) -> None:
            if captured:
                raise V2RuntimeError("capture_hook_count", "layer 50 fired twice")
            hidden = _extract_hidden(output)
            if (
                tuple(hidden.shape) != (1, len(normalized), protocol.WIDTH)
                or hidden.dtype != self.torch.bfloat16
            ):
                raise V2RuntimeError("capture_hook_shape", "layer-50 trace differs")
            captured.append(hidden[0].detach().clone())

        handle = self.model.model.layers[protocol.SAE_LAYER].register_forward_hook(hook)
        try:
            with self.torch.inference_mode():
                self._model_forward(input_ids=ids, use_cache=False, return_dict=True)
        finally:
            handle.remove()
        if len(captured) != 1:
            raise V2RuntimeError("capture_hook_count", "layer 50 did not fire once")
        _finite_tensor(captured[0], label="all-token layer-50 residuals")
        return captured[0]

    def runtime_metadata(self) -> dict[str, Any]:
        properties = self.torch.cuda.get_device_properties(0)
        return {
            "container_image": protocol.CONTAINER_IMAGE_SPEC,
            "hardware": {
                "cuda_device_count": int(self.torch.cuda.device_count()),
                "gpu_name": str(properties.name),
                "gpu_total_memory_bytes": int(properties.total_memory),
                "cuda_runtime_version": str(self.torch.version.cuda),
                "cudnn_version": int(self.torch.backends.cudnn.version() or 0),
            },
            "software": {
                "python": platform.python_version(),
                "python_implementation": platform.python_implementation(),
                "torch": str(self.torch.__version__),
                "accelerate": importlib_metadata.version("accelerate"),
                "huggingface_hub": importlib_metadata.version("huggingface-hub"),
                "numpy": importlib_metadata.version("numpy"),
                "safetensors": importlib_metadata.version("safetensors"),
                "transformers": importlib_metadata.version("transformers"),
            },
            "determinism": _observed_determinism_settings(self.torch),
            "model_forward_count": int(self.forward_count),
            "first_model_forward_at_utc": self.first_forward_at_utc,
            "last_model_forward_at_utc": self.last_forward_at_utc,
        }

    def prepare_arc(self, token_ids: Sequence[int]) -> ArcPromptSession:
        return ArcPromptSession(self, token_ids)

    def shadow_matrix(self, layer: int) -> Any:
        if layer not in self._shadow_maps:
            raise V2RuntimeError("shadow_layer", f"FP32 J[{layer}] is not loaded")
        return self._shadow_maps[layer]

    def transport_realized(self, realized: Any, *, layer: int, transport: str) -> Any:
        value = realized.to(device=self.device)
        matrix = self.j_matrix(layer)
        if transport == "real_j":
            result = value.to(dtype=matrix.dtype) @ matrix.T
        elif transport == "identity":
            result = value.to(dtype=matrix.dtype)
        elif transport.startswith("random_j_"):
            index = int(transport.rsplit("_", 1)[1])
            result = apply_random_j(value.to(dtype=matrix.dtype), matrix, layer=layer, index=index)
        else:
            raise V2RuntimeError("transport", f"unknown transport: {transport}")
        if not bool(self.torch.isfinite(result).all()):
            raise V2RuntimeError("transport", "transport is non-finite")
        return result

    def selected_logits_from_state(self, state: Any, token_ids: Sequence[int]) -> Any:
        return self.logits_from_final_state(state, token_ids)

    def close(self) -> None:
        self._shadow_maps.clear()
        self.j_maps.clear()
        self.model = None
        gc.collect()
        self.torch.cuda.empty_cache()


def verify_public_artifacts(*, sae_path: Path, j_lens_path: Path) -> dict[str, Any]:
    records: dict[str, Any] = {}
    for label, path, expected in (
        ("sae", sae_path, protocol.SAE_SPEC["sha256"]),
        ("j_lens", j_lens_path, protocol.J_LENS_SPEC["sha256"]),
    ):
        candidate = path.expanduser().resolve(strict=True)
        if not candidate.is_file() or candidate.is_symlink():
            raise V2RuntimeError("artifact", f"{label} path is not a real file")
        observed = protocol.sha256_file(candidate)
        if observed != expected:
            raise V2RuntimeError("artifact_hash", f"{label} SHA-256 differs")
        records[label] = {
            "path": candidate.as_posix(),
            "bytes": candidate.stat().st_size,
            "sha256": observed,
        }
    return records


def load_tokenizer(model_snapshot: Path) -> Any:
    try:
        from transformers import AutoTokenizer
    except ImportError as exc:  # pragma: no cover - GPU environment only
        raise V2RuntimeError("transformers_missing", "Transformers is required") from exc
    snapshot = model_snapshot.expanduser().resolve(strict=True)
    if not snapshot.is_dir() or snapshot.is_symlink():
        raise V2RuntimeError("model_snapshot", "model snapshot is not a real directory")
    # The independently rehashed staging receipt binds the snapshot revision;
    # its published directory is intentionally the stable name model_snapshot.
    if snapshot.name != "model_snapshot":
        raise V2RuntimeError("model_revision", "model snapshot publication name differs")
    tokenizer = AutoTokenizer.from_pretrained(
        snapshot, local_files_only=True, trust_remote_code=False
    )
    if len(tokenizer) != protocol.VOCAB_SIZE:
        raise V2RuntimeError("tokenizer", "tokenizer vocabulary size differs")
    return tokenizer


def trace_stage_a_tensor(trace: ArcTrace, *, edit_layer: int) -> Any:
    torch = _torch()
    if trace.post_edit is None:
        raise V2RuntimeError("trace", "Stage A edited trace lacks post state")
    values = [trace.residual_by_layer[layer] for layer in protocol.J_LAYERS]
    values.extend((trace.post_edit, trace.final_residual))
    result = torch.stack(values).to(dtype=torch.bfloat16).contiguous()
    if tuple(result.shape) != (protocol.STAGE_A_CAPTURE_COUNT, protocol.WIDTH):
        raise V2RuntimeError("trace", "Stage A trace shape differs")
    return result


def trace_stage_b_tensor(trace: ArcTrace) -> Any:
    torch = _torch()
    pre50 = trace.residual_by_layer[protocol.SAE_LAYER]
    post50 = trace.post_edit if trace.post_edit is not None else pre50
    values = [trace.residual_by_layer[layer] for layer in range(45, 50)]
    values.extend((pre50, post50))
    values.extend(trace.residual_by_layer[layer] for layer in range(51, 79))
    values.append(trace.final_residual)
    result = torch.stack(values).to(dtype=torch.bfloat16).contiguous()
    if tuple(result.shape) != (len(protocol.STAGE_B_CAPTURE_STATES), protocol.WIDTH):
        raise V2RuntimeError("trace", "Stage B trace shape differs")
    return result


def realization_metrics(
    clean_source: Any,
    plus: ArcTrace,
    minus: ArcTrace,
    requested_positive: Any,
    requested_positive_fp32: Any | None = None,
) -> tuple[dict[str, Any], Any, Any]:
    torch = _torch()
    if any(value is None for value in (plus.pre_edit, plus.post_edit, minus.pre_edit, minus.post_edit)):
        raise V2RuntimeError("realization", "signed edit telemetry is incomplete")
    assert plus.pre_edit is not None and plus.post_edit is not None
    assert minus.pre_edit is not None and minus.post_edit is not None
    requested = requested_positive.detach().to(device="cpu", dtype=torch.bfloat16).contiguous()
    requested_fp32 = (
        requested.float()
        if requested_positive_fp32 is None
        else requested_positive_fp32.detach().to(device="cpu", dtype=torch.float32).contiguous()
    )
    negative = torch.neg(requested).contiguous()
    plus_native = (plus.pre_edit + requested).to(dtype=torch.bfloat16)
    minus_native = (minus.pre_edit + negative).to(dtype=torch.bfloat16)
    realized_plus = plus.post_edit.float() - plus.pre_edit.float()
    realized_minus = minus.post_edit.float() - minus.pre_edit.float()
    central = (plus.post_edit.float() - minus.post_edit.float()) * 0.5
    common = (
        (plus.post_edit.float() + minus.post_edit.float()) * 0.5
        - clean_source.float()
    )
    central_rms = tensor_rms(central)
    common_rms = float(torch.sqrt(torch.mean(common.square())).item())
    clean_rms = tensor_rms(clean_source)
    metrics = {
        "hook_fire_count_plus": plus.hook_fire_count,
        "hook_fire_count_minus": minus.hook_fire_count,
        "pre_equals_clean_plus": bool(torch.equal(plus.pre_edit, clean_source)),
        "pre_equals_clean_minus": bool(torch.equal(minus.pre_edit, clean_source)),
        "native_post_bytes_exact_plus": bool(torch.equal(plus.post_edit, plus_native)),
        "native_post_bytes_exact_minus": bool(torch.equal(minus.post_edit, minus_native)),
        "requested_vector_sha256": tensor_sha256(requested),
        "realized_central_sha256": tensor_sha256(central),
        "requested_plus_realized_relative_rmse": relative_rmse(realized_plus, requested),
        "requested_minus_realized_relative_rmse": relative_rmse(realized_minus, negative),
        "requested_realized_central_relative_rmse": relative_rmse(central, requested),
        "requested_realized_central_cosine": cosine(central, requested),
        "fp32_requested_to_bf16_relative_rmse": relative_rmse(requested, requested_fp32),
        "fp32_requested_to_bf16_cosine": cosine(requested, requested_fp32),
        "native_central_to_fp32_requested_relative_rmse": relative_rmse(
            central, requested_fp32
        ),
        "native_central_to_fp32_requested_cosine": cosine(central, requested_fp32),
        "common_mode_to_central_rms": common_rms / central_rms,
        "requested_rms_fraction": tensor_rms(requested) / clean_rms,
        "realized_rms_fraction": central_rms / clean_rms,
        "finite": bool(
            torch.isfinite(realized_plus).all()
            and torch.isfinite(realized_minus).all()
            and torch.isfinite(common).all()
        ),
    }
    final_central = (plus.final_residual.float() - minus.final_residual.float()) * 0.5
    return metrics, central, final_central


def transport_metrics(
    backend: V2Backend,
    session: ArcPromptSession,
    *,
    edit_layer: int,
    realized_central: Any,
    final_central: Any,
    plus: ArcTrace,
    minus: ArcTrace,
    transport: str,
    selected_token_ids: Sequence[int],
    actual_selected_logit_delta: Any | None = None,
) -> dict[str, Any]:
    torch = backend.torch
    predicted = backend.transport_realized(
        realized_central, layer=edit_layer, transport=transport
    )
    clean_final = session.clean.final_residual.to(device=backend.device).float()
    predicted_logits = (
        backend.selected_logits_from_state(clean_final + predicted.float(), selected_token_ids)
        - backend.selected_logits_from_state(clean_final - predicted.float(), selected_token_ids)
    ) * 0.5
    if actual_selected_logit_delta is None:
        actual_plus = backend.selected_logits_from_state(
            plus.final_residual.to(device=backend.device), selected_token_ids
        )
        actual_minus = backend.selected_logits_from_state(
            minus.final_residual.to(device=backend.device), selected_token_ids
        )
        actual_logits = (actual_plus - actual_minus) * 0.5
    else:
        actual_logits = actual_selected_logit_delta
    return {
        "transport": transport,
        "predicted_central_final_sha256": tensor_sha256(predicted),
        "actual_central_final_sha256": tensor_sha256(final_central),
        "residual_delta_cosine": cosine(final_central, predicted),
        "fixed_token_logit_delta_pearson": pearson(actual_logits, predicted_logits),
        "finite": bool(
            torch.isfinite(predicted).all() and torch.isfinite(predicted_logits).all()
        ),
        # These raw quantities are archived by Stage A so the independent
        # auditor can recompute the reported correlations without loading the
        # 70B model or trusting this scalar-metric implementation.  Stage B
        # deliberately ignores the private tensor fields.
        "_predicted_central_final": predicted.detach(),
        "_predicted_selected_logit_delta": predicted_logits.detach(),
        "_actual_selected_logit_delta": actual_logits.detach(),
    }


def fp32_shadow_metrics(
    backend: V2Backend,
    *,
    edit_layer: int,
    realized_central: Any,
    final_central: Any,
) -> dict[str, Any]:
    value = realized_central.to(device=backend.device, dtype=backend.torch.float32)
    shadow = value @ backend.shadow_matrix(edit_layer).T
    production_bf16 = backend.transport_realized(
        realized_central, layer=edit_layer, transport="real_j"
    )
    if production_bf16.dtype != backend.torch.bfloat16:
        raise V2RuntimeError("shadow_dtype", "production J prediction is not BF16")
    production_fp32 = production_bf16.float()
    return {
        "realized_central_source_sha256": tensor_sha256(realized_central),
        "bf16_j_prediction_sha256": tensor_sha256(production_bf16),
        "fp32_j_prediction_sha256": tensor_sha256(shadow),
        "bf16_fp32_j_cosine": cosine(production_fp32, shadow),
        "bf16_fp32_j_relative_rmse": relative_rmse(production_fp32, shadow),
        "fp32_j_actual_final_cosine": cosine(final_central, shadow),
        "finite": bool(backend.torch.isfinite(shadow).all()),
        # Stage A persists both predictions as raw audit inputs.  The JSON
        # hashes and scalar comparisons are therefore independently
        # reproducible rather than self-attesting telemetry.
        "_bf16_j_prediction": production_bf16.detach(),
        "_fp32_j_prediction": shadow.detach(),
    }


def aggregate_decoder_columns(decoder: Any, feature_ids: Sequence[int]) -> Any:
    """Apply the frozen ordered CPU BF16 coefficient-0.5 aggregate."""

    torch = _torch()
    if decoder.device.type != "cpu" or decoder.ndim != 2:
        raise V2RuntimeError(
            "vector_device", "the SAE decoder must be a two-dimensional CPU tensor"
        )
    ids = tuple(int(value) for value in feature_ids)
    if not ids or len(ids) != len(set(ids)):
        raise V2RuntimeError("feature_ids", "aggregate feature IDs are empty or duplicated")
    if min(ids) < 0 or max(ids) >= int(decoder.shape[1]):
        raise V2RuntimeError("feature_ids", "aggregate feature ID is outside decoder")
    accumulator = torch.zeros(int(decoder.shape[0]), dtype=torch.float32, device="cpu")
    for feature_id in ids:
        accumulator.add_(
            decoder[:, feature_id].to(dtype=torch.bfloat16).to(dtype=torch.float32)
        )
    return accumulator.mul_(protocol.ABSOLUTE_COEFFICIENT).to(
        dtype=torch.bfloat16
    ).contiguous()


def norm_match(control: Any, target: Any) -> tuple[Any, dict[str, float]]:
    torch = _torch()
    if not isinstance(control, torch.Tensor) or not isinstance(target, torch.Tensor):
        raise TypeError("control and target must be torch tensors")
    if control.device.type != "cpu" or target.device.type != "cpu":
        raise V2RuntimeError("vector_device", "vectors must be materialized on CPU")
    raw = control.to(dtype=torch.bfloat16).contiguous()
    reference = target.to(dtype=torch.bfloat16).contiguous()
    raw_norm = float(raw.float().norm().item())
    target_norm = float(reference.float().norm().item())
    if (
        not math.isfinite(raw_norm)
        or not math.isfinite(target_norm)
        or raw_norm <= 0.0
        or target_norm <= 0.0
    ):
        raise V2RuntimeError("norm_match", "control or target norm is invalid")
    scale_tensor = torch.tensor(
        target_norm / raw_norm, dtype=torch.bfloat16, device=raw.device
    )
    matched = (raw * scale_tensor).to(dtype=torch.bfloat16).contiguous()
    final_norm = float(matched.float().norm().item())
    error = abs(final_norm - target_norm) / target_norm
    if error > 0.01:
        raise V2RuntimeError("norm_match", "BF16 norm match is outside tolerance")
    scalar = float(scale_tensor.float().item())
    return matched, {
        "rescale": scalar,
        "raw_norm": raw_norm,
        "final_norm": final_norm,
        "norm_relative_error": error,
    }


def isotropic_vector(assignment_id: str, target: Any) -> tuple[Any, dict[str, float]]:
    import numpy as np

    torch = _torch()
    rng = np.random.Generator(
        np.random.PCG64(protocol.seed64("stage-b-isotropic", assignment_id))
    )
    values = rng.standard_normal(protocol.WIDTH).astype(np.float32)
    raw = torch.from_numpy(values).to(dtype=torch.bfloat16).contiguous()
    return norm_match(raw, target)


def _compute_feature_statistics(
    backend: V2Backend,
    all_token_residuals: Sequence[Any],
    *,
    chunk_size: int = 512,
) -> tuple[list[dict[str, Any]], int, str]:
    """Compute fresh target-free SAE matching coordinates."""

    torch = backend.torch
    if not all_token_residuals:
        raise V2RuntimeError("matching", "no neutral residuals were captured")
    hidden = torch.cat(
        [
            value.detach().to(device="cpu", dtype=torch.bfloat16)
            for value in all_token_residuals
        ],
        dim=0,
    ).contiguous()
    if hidden.ndim != 2 or hidden.shape[1] != backend.width:
        raise V2RuntimeError("matching", "neutral residual table shape differs")
    total_tokens = int(hidden.shape[0])
    if total_tokens <= 0:
        raise V2RuntimeError("matching", "neutral token denominator is zero")

    feature_count = int(protocol.SAE_SPEC["feature_count"])
    stats: list[dict[str, Any]] = []
    hidden_gpu = hidden.to(device=backend.device, dtype=torch.bfloat16)
    functional = torch.nn.functional
    for start in range(0, feature_count, chunk_size):
        stop = min(start + chunk_size, feature_count)
        weight = backend.sae_encoder[start:stop].to(
            device=backend.device, dtype=torch.bfloat16
        )
        bias = backend.sae_encoder_bias[start:stop].to(
            device=backend.device, dtype=torch.bfloat16
        )
        with torch.inference_mode():
            activation = functional.relu(functional.linear(hidden_gpu, weight, bias))
        activation_cpu = activation.detach().to(device="cpu")
        positive = activation_cpu > 0
        counts = positive.sum(dim=0, dtype=torch.int64)
        sums = activation_cpu.to(dtype=torch.float64).sum(dim=0)
        maxima = activation_cpu.to(dtype=torch.float32).amax(dim=0)
        decoder_chunk = backend.sae_decoder[:, start:stop].to(dtype=torch.bfloat16)
        decoder_norms = torch.sqrt(
            decoder_chunk.to(dtype=torch.float32).square().sum(dim=0)
        )
        for local, feature_id in enumerate(range(start, stop)):
            count = int(counts[local].item())
            stats.append(
                {
                    "feature_id": feature_id,
                    "decoder_l2_norm": float(decoder_norms[local].item()),
                    "mean_positive_activation": (
                        float(sums[local].item() / count) if count else 0.0
                    ),
                    "max_positive_activation": (
                        float(maxima[local].item()) if count else 0.0
                    ),
                    "positive_activation_fraction": float(count / total_tokens),
                }
            )
        del activation, activation_cpu, positive, counts, sums, maxima, decoder_chunk
    if len(stats) != feature_count:
        raise V2RuntimeError("matching", "feature-statistic grid is incomplete")
    return (
        stats,
        total_tokens,
        tensor_sha256(backend.sae_decoder.to(dtype=torch.bfloat16).contiguous()),
    )


def _resolve_matches(
    raw_statistics: Sequence[Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], tuple[int, ...]]:
    """Apply frozen float64 median/MAD and greedy one-to-one matching."""

    feature_count = int(protocol.SAE_SPEC["feature_count"])
    if len(raw_statistics) != feature_count:
        raise V2RuntimeError("matching", "matching inventory size differs")
    targets = set(protocol.TARGET_FEATURE_IDS)
    table: list[dict[str, Any]] = []
    for expected_id, source in enumerate(raw_statistics):
        if int(source.get("feature_id", -1)) != expected_id:
            raise V2RuntimeError("matching", "feature IDs are not canonical")
        values = (
            float(source["decoder_l2_norm"]),
            float(source["mean_positive_activation"]),
            float(source["max_positive_activation"]),
            float(source["positive_activation_fraction"]),
        )
        reasons: list[str] = []
        if expected_id in targets:
            reasons.append("target_feature_id")
        if not math.isfinite(values[0]) or values[0] <= 0.0:
            reasons.append("decoder_norm_nonfinite_or_nonpositive")
        if any(not math.isfinite(value) for value in values[1:]):
            reasons.append("activation_statistic_nonfinite")
        if not 0.0 <= values[3] <= 1.0:
            reasons.append("positive_fraction_outside_unit_interval")
        transformed: list[float | None] = [
            math.log1p(values[0])
            if math.isfinite(values[0]) and values[0] > -1.0
            else None,
            math.log1p(values[1])
            if math.isfinite(values[1]) and values[1] > -1.0
            else None,
            math.log1p(values[2])
            if math.isfinite(values[2]) and values[2] > -1.0
            else None,
            values[3] if math.isfinite(values[3]) else None,
        ]
        table.append(
            {
                "feature_id": expected_id,
                "decoder_l2_norm": values[0] if math.isfinite(values[0]) else None,
                "mean_positive_activation": (
                    values[1] if math.isfinite(values[1]) else None
                ),
                "max_positive_activation": (
                    values[2] if math.isfinite(values[2]) else None
                ),
                "positive_activation_fraction": (
                    values[3] if math.isfinite(values[3]) else None
                ),
                "transformed_coordinates": transformed,
                "scaled_coordinates": [],
                "eligible_candidate": not reasons,
                "exclusion_reasons": reasons,
            }
        )

    eligible_rows = [row for row in table if row["eligible_candidate"]]
    if len(eligible_rows) < len(protocol.TARGET_FEATURE_IDS):
        raise V2RuntimeError("matching", "too few eligible candidates")
    medians: list[float] = []
    scales: list[float] = []
    for index in range(4):
        coordinate_values = [
            float(row["transformed_coordinates"][index]) for row in eligible_rows
        ]
        median = float(statistics.median(coordinate_values))
        mad = float(
            statistics.median(abs(value - median) for value in coordinate_values)
        )
        if not math.isfinite(median) or not math.isfinite(mad):
            raise V2RuntimeError("matching", "median or MAD is non-finite")
        medians.append(median)
        scales.append(mad if mad != 0.0 else 1.0)
    for row in table:
        transformed = row["transformed_coordinates"]
        if any(value is None for value in transformed):
            row["scaled_coordinates"] = []
        else:
            row["scaled_coordinates"] = [
                (float(value) - medians[index]) / scales[index]
                for index, value in enumerate(transformed)
            ]

    selected: list[int] = []
    mapping_rows: list[dict[str, Any]] = []
    for target_id in protocol.TARGET_FEATURE_IDS:
        target = table[target_id]
        if len(target["scaled_coordinates"]) != 4:
            raise V2RuntimeError("matching", "target statistics are invalid")
        ranking: list[tuple[float, int]] = []
        for row in eligible_rows:
            feature_id = int(row["feature_id"])
            if feature_id in selected:
                continue
            distance = float(
                sum(
                    (float(left) - float(right)) ** 2
                    for left, right in zip(
                        target["scaled_coordinates"], row["scaled_coordinates"], strict=True
                    )
                )
            )
            if not math.isfinite(distance) or distance < 0.0:
                raise V2RuntimeError("matching", "distance is invalid")
            ranking.append((distance, feature_id))
        ranking.sort(key=lambda item: (item[0], item[1]))
        if not ranking:
            raise V2RuntimeError("matching", "greedy candidate set is empty")
        distance, matched_id = ranking[0]
        selected.append(matched_id)
        mapping_rows.append(
            {
                "target_feature_id": target_id,
                "matched_feature_id": matched_id,
                "scaled_distance": distance,
            }
        )
    if (
        len(selected) != len(protocol.TARGET_FEATURE_IDS)
        or len(set(selected)) != len(selected)
        or set(selected) & targets
    ):
        raise V2RuntimeError("matching", "matched IDs are not unique/disjoint")
    return table, mapping_rows, tuple(selected)


def compute_fresh_matches(
    backend: V2Backend, all_token_residuals: Sequence[Any]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], tuple[int, ...], int, str]:
    """Fresh neutral matching; predecessor rows/matches are never accepted."""

    stats, token_count, decoder_hash = _compute_feature_statistics(
        backend, all_token_residuals
    )
    table, mapping, matched_ids = _resolve_matches(stats)
    targets = tuple(int(row["target_feature_id"]) for row in mapping)
    if targets != protocol.TARGET_FEATURE_IDS:
        raise V2RuntimeError("matching", "source helper target inventory differs from v2")
    if len(matched_ids) != 6 or set(matched_ids) & set(protocol.TARGET_FEATURE_IDS):
        raise V2RuntimeError("matching", "fresh matches are not unique and disjoint")
    return table, mapping, matched_ids, token_count, decoder_hash


def materialize_stage_b_vectors(
    decoder: Any, matched_feature_ids: Sequence[int]
) -> tuple[Any, list[dict[str, Any]]]:
    torch = _torch()
    matched_map = dict(zip(protocol.TARGET_FEATURE_IDS, map(int, matched_feature_ids)))
    vectors: list[Any] = []
    inventory: list[dict[str, Any]] = []
    for assignment in protocol.aggregate_assignments():
        target_ids = tuple(int(value) for value in assignment["target_feature_ids"])
        matched_ids = tuple(matched_map[value] for value in target_ids)
        target = aggregate_decoder_columns(decoder, target_ids)
        matched_raw = aggregate_decoder_columns(decoder, matched_ids)
        matched, matched_meta = norm_match(matched_raw, target)
        isotropic, isotropic_meta = isotropic_vector(assignment["assignment_id"], target)
        for vector_class, vector, feature_ids, metadata in (
            ("target", target, target_ids, {
                "rescale": 1.0,
                "raw_norm": float(target.float().norm().item()),
                "final_norm": float(target.float().norm().item()),
                "norm_relative_error": 0.0,
            }),
            ("matched", matched, matched_ids, matched_meta),
            ("isotropic", isotropic, (), isotropic_meta),
        ):
            vector = vector.to(dtype=torch.bfloat16).contiguous()
            row_index = len(vectors)
            vectors.append(vector)
            inventory.append(
                {
                    "row_index": row_index,
                    "assignment_id": assignment["assignment_id"],
                    "vector_class": vector_class,
                    "feature_ids": list(feature_ids),
                    "coefficient": protocol.ABSOLUTE_COEFFICIENT,
                    "seed": (
                        protocol.seed64("stage-b-isotropic", assignment["assignment_id"])
                        if vector_class == "isotropic"
                        else None
                    ),
                    "vector_sha256": tensor_sha256(vector),
                    "vector_rms": tensor_rms(vector),
                    **metadata,
                }
            )
    tensor = torch.stack(vectors).contiguous()
    if tuple(tensor.shape) != (45, protocol.WIDTH):
        raise V2RuntimeError("vectors", "Stage B vector inventory shape differs")
    return tensor, inventory


@dataclass(frozen=True)
class _TopKReadout:
    token_ids: Any
    scores: Any


def _llama_rms_norm(hidden_states: Any, norm_weight: Any, *, eps: float) -> Any:
    torch = _torch()
    shape = tuple(int(size) for size in hidden_states.shape)
    if len(shape) < 2 or tuple(norm_weight.shape) != (shape[-1],):
        raise V2RuntimeError("readout_shape", "RMSNorm weight/hidden shape differs")
    if not math.isfinite(float(eps)) or eps <= 0.0:
        raise V2RuntimeError("readout_eps", "RMSNorm epsilon is invalid")
    input_dtype = hidden_states.dtype
    states_float = hidden_states.to(torch.float32)
    variance = states_float.square().mean(dim=-1, keepdim=True)
    normalized = states_float * torch.rsqrt(variance + float(eps))
    return norm_weight * normalized.to(input_dtype)


def _jlens_normalized_hidden(
    source_residuals: Any,
    jacobian: Any,
    norm_weight: Any,
    *,
    eps: float,
    row_batch_size: int = 64,
) -> tuple[Any, Any]:
    torch = _torch()
    shape = tuple(int(size) for size in source_residuals.shape)
    if len(shape) < 2 or tuple(jacobian.shape) != (shape[-1], shape[-1]):
        raise V2RuntimeError("readout_shape", "source/J shape differs")
    if source_residuals.device != jacobian.device or row_batch_size <= 0:
        raise V2RuntimeError("readout_device", "source/J device or batch differs")
    flat = source_residuals.reshape(-1, shape[-1])
    transported = torch.cat(
        [
            flat[start : start + row_batch_size].to(dtype=jacobian.dtype)
            @ jacobian.T
            for start in range(0, flat.shape[0], row_batch_size)
        ],
        dim=0,
    ).reshape(*shape[:-1], shape[-1])
    normalized = _llama_rms_norm(
        transported.to(dtype=norm_weight.dtype), norm_weight, eps=eps
    )
    return transported, normalized


def _full_lm_head_logits(
    normalized_hidden: Any, lm_head_weight: Any, *, row_batch_size: int = 32
) -> Any:
    torch = _torch()
    shape = tuple(int(size) for size in normalized_hidden.shape)
    head_shape = tuple(int(size) for size in lm_head_weight.shape)
    if (
        len(shape) < 2
        or len(head_shape) != 2
        or shape[-1] != head_shape[1]
        or row_batch_size <= 0
    ):
        raise V2RuntimeError("readout_shape", "hidden/LM-head shape differs")
    flat = normalized_hidden.reshape(-1, shape[-1])
    rows = [
        (
            flat[start : start + row_batch_size].to(dtype=lm_head_weight.dtype)
            @ lm_head_weight.T
        ).float()
        for start in range(0, flat.shape[0], row_batch_size)
    ]
    return torch.cat(rows, dim=0).reshape(*shape[:-1], head_shape[0])


def _stable_topk(values: Any, token_ids: Any, *, k: int, largest: bool) -> _TopKReadout:
    torch = _torch()
    if values.ndim != 2:
        raise V2RuntimeError("topk_shape", "candidate values must be two-dimensional")
    if token_ids.ndim == 1:
        token_ids = token_ids.unsqueeze(0).expand(values.shape[0], -1)
    if token_ids.shape != values.shape or not 0 < k <= values.shape[1]:
        raise V2RuntimeError("topk_shape", "top-k IDs/scores/K differ")
    by_id = torch.argsort(token_ids, dim=-1, descending=False, stable=True)
    ids_by_id = token_ids.gather(-1, by_id)
    values_by_id = values.gather(-1, by_id)
    by_score = torch.argsort(
        values_by_id, dim=-1, descending=largest, stable=True
    )[:, :k]
    return _TopKReadout(
        token_ids=ids_by_id.gather(-1, by_score),
        scores=values_by_id.gather(-1, by_score),
    )


def stage_b_topk_archive(
    backend: V2Backend,
    residuals: Any,
    *,
    progress_callback: Any | None = None,
) -> dict[str, Any]:
    """Build exact top-2,000 branch and signed-pair browse indexes.

    ``residuals`` is [branches, 36, 8192], with clean branch at row zero.  Raw
    BF16 residuals remain authoritative; these rankings are explicitly a
    disposable browse index and can be replayed from the archive.
    """

    torch = backend.torch
    if tuple(residuals.shape[1:]) != (36, protocol.WIDTH):
        raise V2RuntimeError("topk", "Stage B residual shape differs")
    all_raw_ids: list[Any] = []
    all_raw_scores: list[Any] = []
    all_pos_ids: list[Any] = []
    all_pos_scores: list[Any] = []
    all_neg_ids: list[Any] = []
    all_neg_scores: list[Any] = []
    all_central_pos_ids: list[Any] = []
    all_central_pos_scores: list[Any] = []
    all_central_neg_ids: list[Any] = []
    all_central_neg_scores: list[Any] = []
    local_plan = [
        row
        for row in protocol.stage_b_rows()
        if row["prompt_id"] == protocol.STAGE_B_PROMPT_IDS[0]
    ]
    local_lookup = {
        (
            row["assignment_id"],
            row["vector_class"],
            int(row["sign"]),
            float(row["multiplier"]),
        ): offset + 1
        for offset, row in enumerate(local_plan)
    }
    pair_keys = [
        (assignment["assignment_id"], vector_class, float(multiplier))
        for assignment in protocol.aggregate_assignments()
        for vector_class in protocol.VECTOR_CLASSES
        for multiplier in protocol.STAGE_B_MULTIPLIERS
    ]
    minus_rows = torch.tensor(
        [local_lookup[(assignment, vector_class, -1, multiplier)] for assignment, vector_class, multiplier in pair_keys],
        dtype=torch.long,
        device=backend.device,
    )
    plus_rows = torch.tensor(
        [local_lookup[(assignment, vector_class, 1, multiplier)] for assignment, vector_class, multiplier in pair_keys],
        dtype=torch.long,
        device=backend.device,
    )
    state_layers: list[int | None] = [*range(45, 50), 50, 50, *range(51, 79), None]
    for state_index, layer in enumerate(state_layers):
        if progress_callback is not None:
            progress_callback()
        source = residuals[:, state_index].to(device=backend.device, dtype=torch.bfloat16)
        if layer is None:
            normalized = _llama_rms_norm(
                source, backend.norm_weight, eps=backend.rms_eps
            )
        else:
            _, normalized = _jlens_normalized_hidden(
                source,
                backend.j_matrix(layer),
                backend.norm_weight,
                eps=backend.rms_eps,
                row_batch_size=32,
            )
        logits = _full_lm_head_logits(
            normalized, backend.model.lm_head.weight, row_batch_size=32
        )
        ids = torch.arange(
            protocol.VOCAB_SIZE, device=logits.device, dtype=torch.long
        )
        raw = _stable_topk(logits, ids, k=protocol.TOP_K, largest=True)
        delta = logits - logits[0:1]
        positive = _stable_topk(delta, ids, k=protocol.TOP_K, largest=True)
        negative = _stable_topk(delta, ids, k=protocol.TOP_K, largest=False)
        paired_central = (logits[plus_rows].float() - logits[minus_rows].float()) * 0.5
        central_positive = _stable_topk(
            paired_central, ids, k=protocol.TOP_K, largest=True
        )
        central_negative = _stable_topk(
            paired_central, ids, k=protocol.TOP_K, largest=False
        )
        all_raw_ids.append(raw.token_ids.to(device="cpu", dtype=torch.int32))
        all_raw_scores.append(raw.scores.to(device="cpu", dtype=torch.float32))
        all_pos_ids.append(positive.token_ids.to(device="cpu", dtype=torch.int32))
        all_pos_scores.append(positive.scores.to(device="cpu", dtype=torch.float32))
        all_neg_ids.append(negative.token_ids.to(device="cpu", dtype=torch.int32))
        all_neg_scores.append(negative.scores.to(device="cpu", dtype=torch.float32))
        all_central_pos_ids.append(
            central_positive.token_ids.to(device="cpu", dtype=torch.int32)
        )
        all_central_pos_scores.append(
            central_positive.scores.to(device="cpu", dtype=torch.float32)
        )
        all_central_neg_ids.append(
            central_negative.token_ids.to(device="cpu", dtype=torch.int32)
        )
        all_central_neg_scores.append(
            central_negative.scores.to(device="cpu", dtype=torch.float32)
        )
        del (
            source,
            normalized,
            logits,
            delta,
            raw,
            positive,
            negative,
            paired_central,
            central_positive,
            central_negative,
        )
        if progress_callback is not None:
            progress_callback()
    # lists are state-major; transpose to [branch, state, K].
    return {
        "absolute_top_token_ids": torch.stack(all_raw_ids, dim=1).contiguous(),
        "absolute_top_scores": torch.stack(all_raw_scores, dim=1).contiguous(),
        "branch_vs_clean_top_token_ids": torch.stack(all_pos_ids, dim=1).contiguous(),
        "branch_vs_clean_top_scores": torch.stack(all_pos_scores, dim=1).contiguous(),
        "branch_vs_clean_bottom_token_ids": torch.stack(all_neg_ids, dim=1).contiguous(),
        "branch_vs_clean_bottom_scores": torch.stack(all_neg_scores, dim=1).contiguous(),
        "paired_central_top_token_ids": torch.stack(
            all_central_pos_ids, dim=1
        ).contiguous(),
        "paired_central_top_scores": torch.stack(
            all_central_pos_scores, dim=1
        ).contiguous(),
        "paired_central_bottom_token_ids": torch.stack(
            all_central_neg_ids, dim=1
        ).contiguous(),
        "paired_central_bottom_scores": torch.stack(
            all_central_neg_scores, dim=1
        ).contiguous(),
    }


def vocabulary_rows(tokenizer: Any) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for token_id in range(protocol.VOCAB_SIZE):
        token = tokenizer.convert_ids_to_tokens(token_id)
        decoded = tokenizer.decode(
            [token_id], skip_special_tokens=False, clean_up_tokenization_spaces=False
        )
        rows.append(
            {
                "token_id": token_id,
                "token_piece": str(token),
                "decoded_utf8": str(decoded),
            }
        )
    return rows

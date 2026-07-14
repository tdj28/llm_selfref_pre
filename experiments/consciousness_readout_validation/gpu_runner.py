"""Bound GPU phase adapter for ``consciousness_readout_validation_v1``.

This executor is intentionally limited to the five target-free pilot gates.  It
accepts only the frozen plan, a self-hashed execution binding, the tokenizer
receipt produced from that binding, and the three pinned public artifacts.  It
contains no target prompt and has no import or runtime dependency on an earlier
experiment namespace.

The public CLI is fail closed and creates one fresh transaction for exactly one
phase.  Scientific pass/fail decisions are deliberately left to ``analysis``;
this module records only the prospectively specified measurements and sealed
runtime provenance.
"""

from __future__ import annotations

import argparse
import gc
import math
import os
import platform
import statistics
from contextlib import ExitStack
from dataclasses import dataclass
from importlib import metadata as importlib_metadata
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from . import protocol, runtime


GPU_ADAPTER_VERSION = "gpu_phase_adapter_v1"
MINIMUM_GPU_BYTES = 160 * 1024**3
G4_MATCHING_CANDIDATES_FILENAME = "G4_MATCHING_CANDIDATES.json"
G4_VECTOR_INVENTORY_FILENAME = "G4_VECTOR_INVENTORY.json"


def _sealed(core: Mapping[str, Any]) -> dict[str, Any]:
    payload = dict(core)
    return {**payload, "receipt_sha256": protocol.canonical_sha256(payload)}


def expected_determinism_settings() -> dict[str, Any]:
    return {
        "seed": int(protocol.PILOT_RANDOM_SEED % (2**63 - 1)),
        "cublas_workspace_config": ":4096:8",
        "deterministic_algorithms": True,
        "cuda_matmul_tf32": False,
        "cudnn_tf32": False,
        "flash_sdp_enabled": False,
        "mem_efficient_sdp_enabled": False,
        "math_sdp_enabled": True,
    }


def observed_determinism_settings(torch: Any) -> dict[str, Any]:
    return {
        "seed": int(protocol.PILOT_RANDOM_SEED % (2**63 - 1)),
        "cublas_workspace_config": os.environ.get("CUBLAS_WORKSPACE_CONFIG"),
        "deterministic_algorithms": bool(torch.are_deterministic_algorithms_enabled()),
        "cuda_matmul_tf32": bool(torch.backends.cuda.matmul.allow_tf32),
        "cudnn_tf32": bool(torch.backends.cudnn.allow_tf32),
        "flash_sdp_enabled": bool(torch.backends.cuda.flash_sdp_enabled()),
        "mem_efficient_sdp_enabled": bool(torch.backends.cuda.mem_efficient_sdp_enabled()),
        "math_sdp_enabled": bool(torch.backends.cuda.math_sdp_enabled()),
    }


def validate_determinism_settings(settings: Mapping[str, Any]) -> None:
    if dict(settings) != expected_determinism_settings():
        raise runtime.PilotRuntimeError(
            "determinism_contract", "deterministic CUDA settings differ from the frozen contract"
        )


def measurement_task_id(kind: str, key: Sequence[Any]) -> str:
    """Return the one task identity reconstructed by analysis and audit."""

    return protocol.stable_id(
        "measurement",
        {"measurement_kind": kind, "key": list(key)},
    )


def append_measurement(
    transaction: runtime.PilotTransaction,
    filename: str,
    *,
    kind: str,
    key: Sequence[Any],
    measurement: Mapping[str, Any],
) -> None:
    """Append one exact-schema measurement with explicit stable identities."""

    transaction.append(
        filename,
        {
            **dict(measurement),
            "task_id": measurement_task_id(kind, key),
        },
    )


def _finite_tensor(value: Any, *, label: str) -> None:
    torch = runtime._torch()
    if not isinstance(value, torch.Tensor) or not bool(torch.isfinite(value).all()):
        raise runtime.PilotRuntimeError("nonfinite", f"{label} is not a finite tensor")


def _unique_suffix_key(state: Mapping[str, Any], suffix: str) -> str:
    matches = [key for key in state if key == suffix or key.endswith("." + suffix)]
    if len(matches) != 1:
        raise runtime.PilotRuntimeError(
            "artifact_layout",
            f"expected one state key ending in {suffix!r}, found {matches}",
        )
    return matches[0]


def resolve_sae_state(state: Mapping[str, Any]) -> dict[str, Any]:
    """Resolve and shape-check the exact four-tensor public SAE state."""

    suffixes = (
        "encoder_linear.weight",
        "encoder_linear.bias",
        "decoder_linear.weight",
        "decoder_linear.bias",
    )
    keys = {suffix: _unique_suffix_key(state, suffix) for suffix in suffixes}
    if set(state) != set(keys.values()):
        raise runtime.PilotRuntimeError(
            "sae_layout", "SAE state must contain exactly the four frozen tensors"
        )
    tensors = {suffix: state[key] for suffix, key in keys.items()}
    expected_shapes = {
        "encoder_linear.weight": tuple(protocol.HOOK_CONTRACT["sae"]["encoder_weight_shape"]),
        "encoder_linear.bias": tuple(protocol.HOOK_CONTRACT["sae"]["encoder_bias_shape"]),
        "decoder_linear.weight": tuple(protocol.HOOK_CONTRACT["sae"]["decoder_weight_shape"]),
        "decoder_linear.bias": tuple(protocol.HOOK_CONTRACT["sae"]["decoder_bias_shape"]),
    }
    for suffix, expected in expected_shapes.items():
        if tuple(getattr(tensors[suffix], "shape", ())) != expected:
            raise runtime.PilotRuntimeError("sae_shape", f"{suffix} shape differs")
    return tensors


def validate_j_lens_checkpoint_metadata(checkpoint: Mapping[str, Any]) -> Mapping[Any, Any]:
    """Fail closed on the public release's exact fit-count and width metadata."""

    if not {"J", "n_prompts", "d_model"} <= set(checkpoint):
        raise runtime.PilotRuntimeError("jlens_layout", "J-lens keys differ")
    if int(checkpoint["n_prompts"]) != int(
        protocol.J_LENS_SPEC["release_config"]["prompts_fitted"]
    ):
        raise runtime.PilotRuntimeError("jlens_prompt_count", "J-lens fit count differs")
    if int(checkpoint["d_model"]) != protocol.MODEL_SPEC["residual_width"]:
        raise runtime.PilotRuntimeError("jlens_width", "J-lens width differs")
    raw_maps = checkpoint["J"]
    if not isinstance(raw_maps, Mapping):
        raise runtime.PilotRuntimeError("jlens_layout", "J-lens map inventory differs")
    return raw_maps


@dataclass(frozen=True)
class CleanTrace:
    """The clean cached-one-token inference path for one exact fixture."""

    input_token_ids: tuple[int, ...]
    input_token_ids_sha256: str
    residual_by_layer: Mapping[int, Any]
    final_residual: Any
    logits: Any


@dataclass(frozen=True)
class EditedTrace:
    """One single-use residual edit on the same cached-one-token path."""

    input_token_ids: tuple[int, ...]
    input_token_ids_sha256: str
    pre_edit: Any
    post_edit: Any
    final_residual: Any
    logits: Any
    hook_fire_count: int


class TransformersPromptSession:
    """One exact prompt prefix with immutable branchable KV state."""

    def __init__(self, backend: "TransformersPilotBackend", token_ids: Sequence[int]) -> None:
        torch = backend.torch
        normalized = tuple(int(value) for value in token_ids)
        if len(normalized) < 2 or any(value < 0 for value in normalized):
            raise runtime.PilotRuntimeError("prompt_tokens", "fixture token IDs are invalid")
        self.backend = backend
        self.input_token_ids = normalized
        self.input_token_ids_sha256 = protocol.canonical_sha256(list(normalized))
        prefix = torch.tensor([normalized[:-1]], dtype=torch.long, device=backend.device)
        with torch.inference_mode():
            output = backend._model_forward(
                input_ids=prefix,
                use_cache=True,
                return_dict=True,
            )
        cache = getattr(output, "past_key_values", None)
        if cache is None:
            raise runtime.PilotRuntimeError("kv_cache", "prefix forward returned no KV cache")
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
    ) -> CleanTrace | EditedTrace:
        torch = self.backend.torch
        captured: dict[int, Any] = {}
        final: dict[str, Any] = {}
        hook_counts: dict[int, int] = {layer: 0 for layer in protocol.J_MAP_LAYERS}

        def layer_hook(layer: int) -> Any:
            def hook(_module: Any, _inputs: Any, output: Any) -> None:
                hook_counts[layer] += 1
                if hook_counts[layer] != 1:
                    raise runtime.PilotRuntimeError(
                        "capture_hook_count", f"layer {layer} capture hook fired twice"
                    )
                hidden = runtime._extract_hidden(output)
                expected_shape = tuple(
                    protocol.HOOK_CONTRACT["source_tensor"]["cached_measurement_shape"]
                )
                if (
                    tuple(hidden.shape) != expected_shape
                    or hidden.dtype != torch.bfloat16
                ):
                    raise runtime.PilotRuntimeError(
                        "capture_hook_shape", "cached branch tensor identity differs"
                    )
                captured[layer] = hidden[0, 0].detach().clone()

            return hook

        def final_hook(_module: Any, inputs: Any) -> None:
            if "value" in final:
                raise runtime.PilotRuntimeError(
                    "capture_hook_count", "final-norm capture hook fired twice"
                )
            hidden = inputs[0]
            if (
                tuple(hidden.shape)
                != tuple(protocol.HOOK_CONTRACT["source_tensor"]["cached_measurement_shape"])
                or hidden.dtype != torch.bfloat16
            ):
                raise runtime.PilotRuntimeError(
                    "capture_hook_shape", "final residual tensor identity differs"
                )
            final["value"] = hidden[0, 0].detach().clone()

        edit_context: runtime.SingleUseResidualHook | None = None
        cache = runtime.clone_kv_cache(self.prefix_cache)
        with ExitStack() as stack:
            handles = [
                self.backend.model.model.layers[layer].register_forward_hook(
                    layer_hook(layer)
                )
                for layer in protocol.J_MAP_LAYERS
            ]
            final_handle = self.backend.model.model.norm.register_forward_pre_hook(final_hook)
            stack.callback(final_handle.remove)
            for handle in reversed(handles):
                stack.callback(handle.remove)
            if edit_layer is not None:
                if edit_layer not in protocol.J_MAP_LAYERS or vector is None:
                    raise runtime.PilotRuntimeError("edit_layer", "edit request is malformed")
                # Capture hooks are deliberately registered first: captured[L] is the
                # zero-indexed block-L output before the single-use addition.
                edit_context = stack.enter_context(
                    runtime.SingleUseResidualHook(
                        self.backend.model.model.layers[edit_layer],
                        vector,
                        forward_id=forward_id,
                    )
                )
            with torch.inference_mode():
                output = self.backend._model_forward(
                    input_ids=self.last_token,
                    past_key_values=cache,
                    use_cache=False,
                    return_dict=True,
                )

        if set(captured) != set(protocol.J_MAP_LAYERS) or any(
            count != 1 for count in hook_counts.values()
        ):
            raise runtime.PilotRuntimeError("capture_incomplete", "a J-layer capture is missing")
        if "value" not in final:
            raise runtime.PilotRuntimeError("capture_incomplete", "final residual is missing")
        logits = output.logits[0, -1].detach().float().clone()
        _finite_tensor(logits, label="model logits")
        _finite_tensor(final["value"], label="final residual")
        if tuple(logits.shape) != (protocol.MODEL_SPEC["tokenizer_vocabulary_size"],):
            raise runtime.PilotRuntimeError("logit_shape", "model vocabulary shape differs")

        if edit_context is None:
            return CleanTrace(
                input_token_ids=self.input_token_ids,
                input_token_ids_sha256=self.input_token_ids_sha256,
                residual_by_layer=captured,
                final_residual=final["value"],
                logits=logits,
            )
        measurement = edit_context.measurement
        if measurement is None or edit_context.fire_count != 1:
            raise runtime.PilotRuntimeError("hook_count", "edit hook did not fire exactly once")
        return EditedTrace(
            input_token_ids=self.input_token_ids,
            input_token_ids_sha256=self.input_token_ids_sha256,
            pre_edit=measurement.pre[0, 0].to(device=self.backend.device),
            post_edit=measurement.post[0, 0].to(device=self.backend.device),
            final_residual=final["value"],
            logits=logits,
            hook_fire_count=edit_context.fire_count,
        )

    def edited(self, layer: int, vector: Any, *, forward_id: str) -> EditedTrace:
        value = self._run_last(edit_layer=layer, vector=vector, forward_id=forward_id)
        if not isinstance(value, EditedTrace):  # pragma: no cover - type guard
            raise AssertionError("edited branch returned a clean trace")
        return value

    def close(self) -> None:
        self.prefix_cache = None
        gc.collect()


class TransformersPilotBackend:
    """Pinned BF16 model, Goodfire SAE, and all 34 public J maps."""

    def __init__(
        self,
        *,
        model_snapshot: Path,
        sae_path: Path,
        j_lens_path: Path,
        tokenizer: Any,
    ) -> None:
        observed_container_image = os.environ.get(protocol.CONTAINER_IMAGE_ENV)
        if observed_container_image != protocol.CONTAINER_IMAGE_SPEC["immutable_reference"]:
            raise runtime.PilotRuntimeError(
                "container_image",
                "runtime did not attest the prospectively bound immutable container image",
            )
        torch = runtime._torch()
        if not torch.cuda.is_available() or torch.cuda.device_count() != 1:
            raise runtime.PilotRuntimeError("gpu_contract", "exactly one CUDA GPU is required")
        properties = torch.cuda.get_device_properties(0)
        if int(properties.total_memory) < MINIMUM_GPU_BYTES:
            raise runtime.PilotRuntimeError(
                "gpu_memory", "the BF16 executor requires at least 160 GiB VRAM"
            )
        # This import occurs only after TOKENIZER_AUDIT.json and PHASE_BINDING.json
        # have been durably written by run_bound_phase.
        try:
            from transformers import AutoModelForCausalLM
        except ImportError as exc:  # pragma: no cover - GPU environment only
            raise runtime.PilotRuntimeError(
                "transformers_missing", "Transformers is required"
            ) from exc

        required_determinism = (
            "enable_flash_sdp",
            "enable_mem_efficient_sdp",
            "enable_math_sdp",
        )
        if any(not hasattr(torch.backends.cuda, name) for name in required_determinism):
            raise runtime.PilotRuntimeError(
                "determinism_api", "required CUDA SDPA controls are unavailable"
            )
        seed = int(protocol.PILOT_RANDOM_SEED % (2**63 - 1))
        torch.manual_seed(seed)
        torch.cuda.manual_seed_all(seed)
        torch.use_deterministic_algorithms(True)
        torch.backends.cuda.matmul.allow_tf32 = False
        torch.backends.cudnn.allow_tf32 = False
        torch.backends.cuda.enable_flash_sdp(False)
        torch.backends.cuda.enable_mem_efficient_sdp(False)
        torch.backends.cuda.enable_math_sdp(True)
        validate_determinism_settings(observed_determinism_settings(torch))

        self.torch = torch
        self.device = torch.device("cuda:0")
        # Exercise deterministic cuBLAS before the costly 70B model load.
        try:
            with torch.inference_mode():
                smoke_left = torch.tensor(
                    [[1.0, 2.0], [3.0, 4.0]],
                    dtype=torch.float32,
                    device=self.device,
                )
                smoke_right = torch.tensor(
                    [[5.0], [6.0]],
                    dtype=torch.float32,
                    device=self.device,
                )
                smoke_result = torch.mm(smoke_left, smoke_right)
        except RuntimeError as exc:
            raise runtime.PilotRuntimeError(
                "deterministic_cublas",
                "deterministic CUDA matrix multiplication preflight failed",
            ) from exc
        if not bool(
            torch.equal(
                smoke_result.cpu(),
                torch.tensor([[17.0], [39.0]], dtype=torch.float32),
            )
        ):
            raise runtime.PilotRuntimeError(
                "deterministic_cublas", "deterministic CUDA matrix preflight differs"
            )
        del smoke_left, smoke_right, smoke_result
        self.tokenizer = tokenizer
        self.container_image = observed_container_image
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
            int(config.hidden_size) != protocol.MODEL_SPEC["residual_width"]
            or int(config.num_hidden_layers) != protocol.MODEL_SPEC["layer_count"]
            or len(self.model.model.layers) != protocol.MODEL_SPEC["layer_count"]
            or tuple(self.model.lm_head.weight.shape)
            != (
                protocol.MODEL_SPEC["tokenizer_vocabulary_size"],
                protocol.MODEL_SPEC["residual_width"],
            )
        ):
            raise runtime.PilotRuntimeError("model_shape", "model architecture differs")
        if next(self.model.parameters()).dtype != torch.bfloat16:
            raise runtime.PilotRuntimeError("model_dtype", "model is not BF16")
        self.norm_weight = self.model.model.norm.weight
        self.rms_eps = float(config.rms_norm_eps)

        state = torch.load(sae_path, map_location="cpu", weights_only=True, mmap=True)
        sae = resolve_sae_state(state)
        self.sae_encoder = sae["encoder_linear.weight"]
        self.sae_encoder_bias = sae["encoder_linear.bias"]
        self.sae_decoder = sae["decoder_linear.weight"]
        self.sae_decoder_bias = sae["decoder_linear.bias"]

        checkpoint = torch.load(
            j_lens_path, map_location="cpu", weights_only=True, mmap=True
        )
        raw_maps = validate_j_lens_checkpoint_metadata(checkpoint)
        available = {int(layer) for layer in raw_maps}
        if not set(protocol.J_MAP_LAYERS) <= available:
            raise runtime.PilotRuntimeError("jlens_layers", "a required J map is missing")
        self.j_maps: dict[int, Any] = {}
        for layer in protocol.J_MAP_LAYERS:
            raw = raw_maps[layer] if layer in raw_maps else raw_maps[str(layer)]
            if tuple(raw.shape) != (
                protocol.MODEL_SPEC["residual_width"],
                protocol.MODEL_SPEC["residual_width"],
            ):
                raise runtime.PilotRuntimeError(
                    "jlens_shape", f"J[{layer}] shape differs"
                )
            matrix = raw.to(
                device=self.device, dtype=torch.bfloat16, non_blocking=True
            ).contiguous()
            _finite_tensor(matrix, label=f"J[{layer}]")
            self.j_maps[layer] = matrix
        del checkpoint, raw_maps
        gc.collect()

    @property
    def width(self) -> int:
        return int(protocol.MODEL_SPEC["residual_width"])

    def _model_forward(self, **kwargs: Any) -> Any:
        timestamp = runtime.utc_now()
        if self.forward_count == 0:
            self.first_forward_at_utc = timestamp
        self.forward_count += 1
        self.total_forward_count += 1
        self.last_forward_at_utc = timestamp
        return self.model(**kwargs)

    def start_runtime_interval(self) -> None:
        """Begin a fresh per-phase model-forward accounting interval."""

        self.forward_count = 0
        self.first_forward_at_utc = None
        self.last_forward_at_utc = None

    def prepare(self, token_ids: Sequence[int]) -> TransformersPromptSession:
        return TransformersPromptSession(self, token_ids)

    def j_matrix(self, layer: int) -> Any:
        if layer not in self.j_maps:
            raise runtime.PilotRuntimeError("jlens_layer", f"unavailable J map {layer}")
        return self.j_maps[layer]

    def transport_state(self, source: Any, *, layer: int, transport: str) -> Any:
        matrix = self.j_matrix(layer)
        value = source.to(device=self.device)
        if transport == "real_j":
            result = value.to(dtype=matrix.dtype) @ matrix.T
        elif transport == "identity":
            result = value.to(dtype=matrix.dtype)
        elif transport.startswith("random_j_"):
            try:
                control_index = int(transport.removeprefix("random_j_"))
            except ValueError as exc:
                raise runtime.PilotRuntimeError(
                    "transport_name", f"invalid transport {transport}"
                ) from exc
            result = runtime.apply_random_j(
                value.to(dtype=matrix.dtype),
                matrix,
                layer=layer,
                control_index=control_index,
            )
        else:
            raise runtime.PilotRuntimeError(
                "transport_name", f"unknown transport {transport}"
            )
        _finite_tensor(result, label=f"{transport} transport")
        return result

    def logits_from_final_state(self, state: Any, token_ids: Sequence[int]) -> Any:
        normalized = runtime.rms_norm(
            state.to(device=self.device, dtype=self.norm_weight.dtype),
            self.norm_weight,
            self.rms_eps,
        )
        result = runtime.selected_logits(
            normalized,
            self.model.lm_head.weight,
            token_ids,
        ).reshape(-1)
        _finite_tensor(result, label="selected logits")
        return result

    def selected_actual_logits(self, trace: CleanTrace | EditedTrace, token_ids: Sequence[int]) -> Any:
        torch = self.torch
        ids = torch.tensor(list(token_ids), dtype=torch.long, device=trace.logits.device)
        values = trace.logits.index_select(0, ids)
        _finite_tensor(values, label="actual selected logits")
        return values

    def capture_layer50_all_tokens(self, token_ids: Sequence[int]) -> Any:
        """Capture block-50 output for every non-padding token of one fixture."""

        torch = self.torch
        normalized = tuple(int(value) for value in token_ids)
        ids = torch.tensor([normalized], dtype=torch.long, device=self.device)
        captured: list[Any] = []

        def hook(_module: Any, _inputs: Any, output: Any) -> None:
            if captured:
                raise runtime.PilotRuntimeError("capture_hook_count", "layer 50 fired twice")
            hidden = runtime._extract_hidden(output)
            if (
                tuple(hidden.shape) != (1, len(normalized), self.width)
                or hidden.dtype != torch.bfloat16
            ):
                raise runtime.PilotRuntimeError("capture_hook_shape", "layer-50 trace differs")
            captured.append(hidden[0].detach().clone())

        handle = self.model.model.layers[50].register_forward_hook(hook)
        try:
            with torch.inference_mode():
                self._model_forward(input_ids=ids, use_cache=False, return_dict=True)
        finally:
            handle.remove()
        if len(captured) != 1:
            raise runtime.PilotRuntimeError("capture_hook_count", "layer 50 did not fire once")
        _finite_tensor(captured[0], label="all-token layer-50 residuals")
        return captured[0]

    def runtime_metadata(self) -> dict[str, Any]:
        torch = self.torch
        properties = torch.cuda.get_device_properties(0)
        return {
            "container_image": protocol.CONTAINER_IMAGE_SPEC,
            "hardware": {
                "cuda_device_count": int(torch.cuda.device_count()),
                "gpu_name": str(properties.name),
                "gpu_total_memory_bytes": int(properties.total_memory),
                "cuda_runtime_version": str(torch.version.cuda),
                "cudnn_version": int(torch.backends.cudnn.version() or 0),
            },
            "software": {
                "python": platform.python_version(),
                "python_implementation": platform.python_implementation(),
                "torch": str(torch.__version__),
                "accelerate": importlib_metadata.version("accelerate"),
                "huggingface_hub": importlib_metadata.version("huggingface-hub"),
                "numpy": importlib_metadata.version("numpy"),
                "safetensors": importlib_metadata.version("safetensors"),
                "transformers": importlib_metadata.version("transformers"),
            },
            "determinism": observed_determinism_settings(torch),
            "model_forward_count": int(self.forward_count),
            "first_model_forward_at_utc": self.first_forward_at_utc,
            "last_model_forward_at_utc": self.last_forward_at_utc,
        }

    def close(self) -> None:
        self.j_maps.clear()
        self.model = None
        gc.collect()
        self.torch.cuda.empty_cache()


def independent_component_transport(source: Any, matrix: Any, *, chunk: int = 512) -> Any:
    """Component-level ``sum_j source[j] * J[i,j]`` reference arithmetic."""

    torch = runtime._torch()
    # Match production's exact source cast first, then isolate only the
    # component-summation implementation in the reference comparison.
    vector = source.to(device=matrix.device, dtype=matrix.dtype).float().reshape(-1)
    if matrix.ndim != 2 or tuple(matrix.shape) != (vector.numel(), vector.numel()):
        raise runtime.PilotRuntimeError("g1_shape", "component-reference shape differs")
    result = torch.zeros(vector.numel(), dtype=torch.float32, device=matrix.device)
    for start in range(0, vector.numel(), chunk):
        stop = min(start + chunk, vector.numel())
        result += (
            matrix[:, start:stop].float()
            * vector[start:stop].reshape(1, -1)
        ).sum(dim=1)
    _finite_tensor(result, label="G1 component reference")
    return result


def execute_g1(
    backend: TransformersPilotBackend,
    token_receipt: Mapping[str, Any],
    transaction: runtime.PilotTransaction,
) -> None:
    token_ids = tuple(int(value) for value in token_receipt["g1"]["accepted_token_ids"])
    if len(token_ids) != protocol.G1_TOKEN_PANEL_SIZE:
        raise runtime.PilotRuntimeError("g1_token_panel", "G1 token panel is incomplete")
    torch = backend.torch
    for layer in protocol.G1_MAP_LAYERS:
        matrix = backend.j_matrix(layer)
        for fixture in protocol.G1_SYNTHETIC_FIXTURES:
            source = runtime.synthetic_residual(fixture, backend.width).to(backend.device)
            production = source.to(dtype=matrix.dtype) @ matrix.T
            reference = independent_component_transport(source, matrix)
            wrong = source.to(dtype=matrix.dtype) @ matrix
            production_logits = backend.logits_from_final_state(production, token_ids)
            reference_logits = backend.logits_from_final_state(reference, token_ids)
            agreement = float(
                (torch.sign(production_logits) == torch.sign(reference_logits))
                .float()
                .mean()
                .item()
            )
            wrong_differs = runtime.relative_rmse(wrong, production) > 1e-6
            measurement = {
                "layer": int(layer),
                "synthetic_residual_id": str(fixture["fixture_id"]),
                "vocab_ids": list(token_ids),
                "map_shape_valid": tuple(matrix.shape) == (backend.width, backend.width),
                "map_finite": bool(torch.isfinite(matrix).all()),
                "production_finite": bool(torch.isfinite(production).all()),
                "reference_finite": bool(torch.isfinite(reference).all()),
                "relative_rmse": runtime.relative_rmse(production, reference),
                "selected_logit_sign_agreement": agreement,
                "wrong_orientation_differs": bool(wrong_differs),
            }
            key = (layer, str(fixture["fixture_id"]))
            append_measurement(
                transaction,
                "g1_rows.jsonl",
                kind="g1",
                key=key,
                measurement=measurement,
            )


@dataclass(frozen=True)
class PerturbationPair:
    fraction: float
    vector: Any
    residual_central_delta: Any
    selected_logit_central_delta: Any


def measure_perturbation_pair(
    backend: TransformersPilotBackend,
    session: TransformersPromptSession,
    *,
    layer: int,
    direction: int,
    fraction: float,
    selected_token_ids: Sequence[int],
) -> PerturbationPair:
    torch = backend.torch
    clean_source = session.clean.residual_by_layer[layer]
    unit = runtime.deterministic_direction(
        backend.width, layer=layer, direction=direction
    ).to(device=backend.device)
    positive = (
        unit
        * (runtime.tensor_rms(clean_source) * float(fraction))
    ).to(dtype=torch.bfloat16).contiguous()
    negative = torch.neg(positive).contiguous()
    if not bool(torch.equal(negative.view(torch.int16), torch.neg(positive).view(torch.int16))):
        raise runtime.PilotRuntimeError("g2_pair", "negative dose is not exact BF16 negation")
    identity = f"{session.input_token_ids_sha256}:{layer}:{direction}:{fraction}"
    plus = session.edited(layer, positive, forward_id=f"{identity}:plus")
    minus = session.edited(layer, negative, forward_id=f"{identity}:minus")
    if not torch.equal(plus.pre_edit, clean_source) or not torch.equal(minus.pre_edit, clean_source):
        raise runtime.PilotRuntimeError("g2_clean_identity", "branch pre-edit state changed")
    residual_delta = (plus.final_residual.float() - minus.final_residual.float()) * 0.5
    logit_delta = (
        backend.selected_actual_logits(plus, selected_token_ids)
        - backend.selected_actual_logits(minus, selected_token_ids)
    ) * 0.5
    _finite_tensor(residual_delta, label="G2 residual central difference")
    _finite_tensor(logit_delta, label="G2 logit central difference")
    return PerturbationPair(
        fraction=float(fraction),
        vector=positive,
        residual_central_delta=residual_delta,
        selected_logit_central_delta=logit_delta,
    )


def g2_transport_measurement(
    backend: TransformersPilotBackend,
    session: TransformersPromptSession,
    pair: PerturbationPair,
    *,
    layer: int,
    transport: str,
    selected_token_ids: Sequence[int],
) -> dict[str, Any]:
    predicted = backend.transport_state(pair.vector, layer=layer, transport=transport)
    clean_final = session.clean.final_residual.to(device=backend.device).float()
    predicted_logits = (
        backend.logits_from_final_state(clean_final + predicted.float(), selected_token_ids)
        - backend.logits_from_final_state(clean_final - predicted.float(), selected_token_ids)
    ) * 0.5
    return {
        "residual_delta_cosine": runtime.cosine_similarity(
            pair.residual_central_delta, predicted
        ),
        "fixed_token_logit_delta_pearson": runtime.pearson_correlation(
            pair.selected_logit_central_delta, predicted_logits
        ),
    }


def execute_g2(
    backend: TransformersPilotBackend,
    tokenizer: Any,
    token_receipt: Mapping[str, Any],
    transaction: runtime.PilotTransaction,
) -> None:
    selected = tuple(int(value) for value in token_receipt["g1"]["accepted_token_ids"])
    transports = tuple(protocol.G2_TRANSPORT_OPERATORS)
    for prompt_offset, prompt in enumerate(
        protocol.neutral_prompts()[: protocol.G2_PROMPT_COUNT]
    ):
        prompt_id = str(prompt["prompt_id"])
        token_ids, _ = runtime.render_neutral_fixture(tokenizer, prompt_id)
        session = backend.prepare(token_ids)
        try:
            primary: dict[tuple[int, int], PerturbationPair] = {}
            for layer in protocol.J_MAP_LAYERS:
                for direction in protocol.G2_DIRECTIONS:
                    pair = measure_perturbation_pair(
                        backend,
                        session,
                        layer=layer,
                        direction=direction,
                        fraction=protocol.G2_PRIMARY_RMS_FRACTION,
                        selected_token_ids=selected,
                    )
                    primary[(layer, direction)] = pair
                    for transport in transports:
                        values = g2_transport_measurement(
                            backend,
                            session,
                            pair,
                            layer=layer,
                            transport=transport,
                            selected_token_ids=selected,
                        )
                        measurement = {
                            "prompt_id": prompt_id,
                            "layer": int(layer),
                            "direction": int(direction),
                            "transport": str(transport),
                            "signed_pair_complete": True,
                            **values,
                            "finite": True,
                        }
                        key = (prompt_id, layer, direction, transport)
                        append_measurement(
                            transaction,
                            "g2_transport_rows.jsonl",
                            kind="g2_transport",
                            key=key,
                            measurement=measurement,
                        )
            if prompt_offset < 8:
                for layer in protocol.G2_LINEARITY_LAYERS:
                    anchor = measure_perturbation_pair(
                        backend,
                        session,
                        layer=layer,
                        direction=0,
                        fraction=protocol.G2_ANCHOR_RMS_FRACTION,
                        selected_token_ids=selected,
                    )
                    main = primary[(layer, 0)]
                    anchor_slope = anchor.residual_central_delta / anchor.fraction
                    main_slope = main.residual_central_delta / main.fraction
                    measurement = {
                        "prompt_id": prompt_id,
                        "layer": int(layer),
                        "direction": 0,
                        "central_difference_cosine": runtime.cosine_similarity(
                            anchor_slope, main_slope
                        ),
                        "slope_discrepancy": runtime.relative_rmse(
                            anchor_slope, main_slope
                        ),
                        "finite": True,
                    }
                    key = (prompt_id, layer, 0)
                    append_measurement(
                        transaction,
                        "g2_linearity_rows.jsonl",
                        kind="g2_linearity",
                        key=key,
                        measurement=measurement,
                    )
        finally:
            session.close()


def _semantic_token_map(token_receipt: Mapping[str, Any]) -> dict[str, int]:
    groups = token_receipt["semantic"]["groups"]
    result = {
        str(row["token"]): int(row["token_id"])
        for family in protocol.G3_FAMILIES
        for row in groups[family]
    }
    expected = {
        token for tokens in protocol.G3_TOKEN_GROUPS.values() for token in tokens
    }
    if set(result) != expected or len(result) != len(set(result.values())):
        raise runtime.PilotRuntimeError("semantic_tokens", "semantic receipt differs")
    return result


def _readout_logits(
    backend: TransformersPilotBackend,
    source: Any,
    *,
    layer: int,
    transport: str,
    token_ids: Sequence[int],
) -> Any:
    state = backend.transport_state(source, layer=layer, transport=transport)
    return backend.logits_from_final_state(state, token_ids)


def execute_g3(
    backend: TransformersPilotBackend,
    tokenizer: Any,
    token_receipt: Mapping[str, Any],
    transaction: runtime.PilotTransaction,
) -> None:
    token_by_label = _semantic_token_map(token_receipt)
    labels = tuple(
        token for family in protocol.G3_FAMILIES for token in protocol.G3_TOKEN_GROUPS[family]
    )
    ids = tuple(token_by_label[label] for label in labels)
    transports = (
        "real_j",
        "identity",
        *(f"random_j_{index}" for index in range(protocol.G3_RANDOM_CONTROL_COUNT)),
    )
    for fixture in protocol.g3_fixture_rows():
        prompt_id = str(fixture["fixture_id"])
        token_ids, _ = runtime.render_semantic_fixture(
            tokenizer, str(fixture["family"]), int(fixture["cloze_index"])
        )
        session = backend.prepare(token_ids)
        try:
            actual = backend.selected_actual_logits(session.clean, ids)
            measurement = {
                "prompt_id": prompt_id,
                "true_family": str(fixture["family"]),
                "item_index": int(fixture["cloze_index"]),
                "render_mode": str(fixture["render_mode"]),
                "transport": "actual_final",
                "layer": "final",
                "token_logits": {
                    label: float(value) for label, value in zip(labels, actual.tolist())
                },
                "finite": True,
            }
            append_measurement(
                transaction,
                "g3_rows.jsonl",
                kind="g3",
                key=(prompt_id, "actual_final", "final"),
                measurement=measurement,
            )
            for layer in protocol.J_MAP_LAYERS:
                source = session.clean.residual_by_layer[layer]
                for transport in transports:
                    values = _readout_logits(
                        backend,
                        source,
                        layer=layer,
                        transport=transport,
                        token_ids=ids,
                    )
                    measurement = {
                        "prompt_id": prompt_id,
                        "true_family": str(fixture["family"]),
                        "item_index": int(fixture["cloze_index"]),
                        "render_mode": str(fixture["render_mode"]),
                        "transport": transport,
                        "layer": int(layer),
                        "token_logits": {
                            label: float(value)
                            for label, value in zip(labels, values.tolist())
                        },
                        "finite": True,
                    }
                    append_measurement(
                        transaction,
                        "g3_rows.jsonl",
                        kind="g3",
                        key=(prompt_id, transport, layer),
                        measurement=measurement,
                    )
        finally:
            session.close()


def execute_g3p(
    backend: TransformersPilotBackend,
    tokenizer: Any,
    token_receipt: Mapping[str, Any],
    transaction: runtime.PilotTransaction,
) -> None:
    answer_ids = tuple(int(token_receipt["polarity"]["isolated_token_ids"][value]) for value in ("Yes", "No"))
    if dict(zip(("Yes", "No"), answer_ids)) != protocol.G3P_ANSWER_TOKEN_IDS:
        raise runtime.PilotRuntimeError("polarity_tokens", "polarity token receipt differs")
    transports = (
        "real_j",
        *(f"random_j_{index}" for index in range(protocol.G3_RANDOM_CONTROL_COUNT)),
    )
    for fixture in protocol.g3p_plan_rows():
        prompt_id = str(fixture["prompt_id"])
        token_ids, _ = runtime.render_polarity_fixture(tokenizer, prompt_id)
        session = backend.prepare(token_ids)
        try:
            actual = backend.selected_actual_logits(session.clean, answer_ids)
            measurement = {
                "prompt_id": prompt_id,
                "expected_answer": str(fixture["expected_label"]),
                "transport": "actual_final",
                "layer": "final",
                "yes_logit": float(actual[0].item()),
                "no_logit": float(actual[1].item()),
                "finite": True,
            }
            append_measurement(
                transaction,
                "g3p_rows.jsonl",
                kind="g3p",
                key=(prompt_id, "actual_final", "final"),
                measurement=measurement,
            )
            for layer in protocol.J_MAP_LAYERS:
                source = session.clean.residual_by_layer[layer]
                for transport in transports:
                    values = _readout_logits(
                        backend,
                        source,
                        layer=layer,
                        transport=transport,
                        token_ids=answer_ids,
                    )
                    measurement = {
                        "prompt_id": prompt_id,
                        "expected_answer": str(fixture["expected_label"]),
                        "transport": transport,
                        "layer": int(layer),
                        "yes_logit": float(values[0].item()),
                        "no_logit": float(values[1].item()),
                        "finite": True,
                    }
                    append_measurement(
                        transaction,
                        "g3p_rows.jsonl",
                        kind="g3p",
                        key=(prompt_id, transport, layer),
                        measurement=measurement,
                    )
        finally:
            session.close()


def compute_g4_feature_statistics(
    backend: TransformersPilotBackend,
    all_token_residuals: Sequence[Any],
    *,
    chunk_size: int = 512,
) -> tuple[list[dict[str, Any]], int, str]:
    """Compute the exact clean 65,536-feature matching table inputs.

    The encoder path is the public Goodfire ReLU SAE.  Residuals, encoder rows,
    and bias are cast to BF16 before the linear operation; positive activation
    sums are accumulated in float64, maxima in float32, and counts as integers.
    Decoder norms use each exact BF16 decoder column followed by float32 L2.
    """

    torch = backend.torch
    if not all_token_residuals:
        raise runtime.PilotRuntimeError("g4_matching", "no neutral residuals were captured")
    hidden = torch.cat(
        [value.detach().to(device="cpu", dtype=torch.bfloat16) for value in all_token_residuals],
        dim=0,
    ).contiguous()
    if hidden.ndim != 2 or hidden.shape[1] != backend.width:
        raise runtime.PilotRuntimeError("g4_matching", "neutral residual table shape differs")
    total_tokens = int(hidden.shape[0])
    if total_tokens <= 0:
        raise runtime.PilotRuntimeError("g4_matching", "neutral token denominator is zero")

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
            mean_positive = float(sums[local].item() / count) if count else 0.0
            maximum = float(maxima[local].item()) if count else 0.0
            fraction = count / total_tokens
            stats.append(
                {
                    "feature_id": int(feature_id),
                    "decoder_l2_norm": float(decoder_norms[local].item()),
                    "mean_positive_activation": mean_positive,
                    "max_positive_activation": maximum,
                    "positive_activation_fraction": float(fraction),
                }
            )
        del activation, activation_cpu, positive, counts, sums, maxima, decoder_chunk
    if len(stats) != feature_count:
        raise runtime.PilotRuntimeError("g4_matching", "feature-statistic grid is incomplete")
    decoder_bfloat16_sha256 = runtime.tensor_sha256(
        backend.sae_decoder.to(dtype=torch.bfloat16).contiguous()
    )
    return stats, total_tokens, decoder_bfloat16_sha256


def resolve_g4_matches(
    raw_statistics: Sequence[Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], tuple[int, ...]]:
    """Apply frozen float64 median/MAD scaling and greedy one-to-one matching."""

    feature_count = int(protocol.SAE_SPEC["feature_count"])
    if len(raw_statistics) != feature_count:
        raise runtime.PilotRuntimeError("g4_matching", "matching inventory size differs")
    targets = set(int(value) for value in protocol.G4_TARGET_FEATURE_IDS)
    coordinates = (
        "log1p_decoder_l2_norm",
        "log1p_mean_positive_activation",
        "log1p_max_positive_activation",
        "positive_activation_fraction",
    )
    table: list[dict[str, Any]] = []
    for expected_id, source in enumerate(raw_statistics):
        if int(source.get("feature_id", -1)) != expected_id:
            raise runtime.PilotRuntimeError("g4_matching", "feature IDs are not canonical")
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
            math.log1p(values[0]) if math.isfinite(values[0]) and values[0] > -1 else None,
            math.log1p(values[1]) if math.isfinite(values[1]) and values[1] > -1 else None,
            math.log1p(values[2]) if math.isfinite(values[2]) and values[2] > -1 else None,
            values[3] if math.isfinite(values[3]) else None,
        ]
        eligible = not reasons
        table.append(
            {
                "feature_id": expected_id,
                "decoder_l2_norm": values[0] if math.isfinite(values[0]) else None,
                "mean_positive_activation": values[1] if math.isfinite(values[1]) else None,
                "max_positive_activation": values[2] if math.isfinite(values[2]) else None,
                "positive_activation_fraction": values[3] if math.isfinite(values[3]) else None,
                "transformed_coordinates": transformed,
                "scaled_coordinates": [],
                "eligible_candidate": eligible,
                "exclusion_reasons": reasons,
            }
        )

    eligible_rows = [row for row in table if row["eligible_candidate"]]
    if len(eligible_rows) < len(protocol.G4_TARGET_FEATURE_IDS):
        raise runtime.PilotRuntimeError("g4_matching", "too few eligible candidates")
    medians: list[float] = []
    scales: list[float] = []
    for index in range(4):
        values = [float(row["transformed_coordinates"][index]) for row in eligible_rows]
        median = float(statistics.median(values))
        mad = float(statistics.median(abs(value - median) for value in values))
        if not math.isfinite(median) or not math.isfinite(mad):
            raise runtime.PilotRuntimeError("g4_matching", "median or MAD is non-finite")
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
    for target_id in protocol.G4_TARGET_FEATURE_IDS:
        target = table[int(target_id)]
        if len(target["scaled_coordinates"]) != 4:
            raise runtime.PilotRuntimeError("g4_matching", "target statistics are invalid")
        ranking: list[tuple[float, int]] = []
        for row in eligible_rows:
            feature_id = int(row["feature_id"])
            if feature_id in selected:
                continue
            distance = float(
                sum(
                    (float(left) - float(right)) ** 2
                    for left, right in zip(
                        target["scaled_coordinates"], row["scaled_coordinates"]
                    )
                )
            )
            if not math.isfinite(distance) or distance < 0:
                raise runtime.PilotRuntimeError("g4_matching", "distance is invalid")
            ranking.append((distance, feature_id))
        ranking.sort(key=lambda item: (item[0], item[1]))
        if not ranking:
            raise runtime.PilotRuntimeError("g4_matching", "greedy candidate set is empty")
        distance, matched_id = ranking[0]
        selected.append(matched_id)
        mapping_rows.append(
            {
                "target_feature_id": int(target_id),
                "matched_feature_id": int(matched_id),
                "scaled_distance": float(distance),
            }
        )

    # Make the scaling constants explicit without adding a second file: every row
    # carries its scaled coordinates, and these two canonical pseudo-rows are not
    # needed for reconstruction.  The auditor recomputes the four medians/MADs.
    if len(selected) != 6 or len(set(selected)) != 6 or set(selected) & targets:
        raise runtime.PilotRuntimeError("g4_matching", "matched IDs are not unique/disjoint")
    return table, mapping_rows, tuple(selected)


def write_jsonl_metadata(
    transaction: runtime.PilotTransaction,
    filename: str,
    rows: Iterable[Mapping[str, Any]],
) -> None:
    """Durably add a non-measurement JSONL table to the open transaction."""

    if filename in transaction.counts or Path(filename).name != filename or not filename.endswith(".jsonl"):
        raise runtime.PilotRuntimeError("transaction_metadata", "metadata JSONL name is invalid")
    path = transaction.partial / filename
    if path.exists():
        raise runtime.PilotRuntimeError("transaction_overwrite", f"refusing to overwrite {filename}")
    with path.open("xb") as handle:
        for row in rows:
            handle.write(protocol.canonical_json_bytes(dict(row)) + b"\n")
        handle.flush()
        os.fsync(handle.fileno())


def build_g4_vector_inventory(
    vectors: Sequence[runtime.G4Vector],
    *,
    plan_manifest_sha256: str,
    sae_sha256: str,
    decoder_bfloat16_sha256: str,
    matching_table: Sequence[Mapping[str, Any]],
    target_to_matched: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Build the exact self-hashed 300-row pre-edit vector receipt."""

    torch = runtime._torch()
    if len(vectors) != 300:
        raise runtime.PilotRuntimeError("g4_vector_count", "vector inventory is incomplete")
    mapping = {
        int(row["target_feature_id"]): int(row["matched_feature_id"])
        for row in target_to_matched
    }
    by_identity = {
        (tuple(row.subset_feature_ids), row.control_type, int(row.sign)): row
        for row in vectors
    }
    if len(by_identity) != 300:
        raise runtime.PilotRuntimeError("g4_vector_count", "vector identities are duplicated")
    vector_rows: list[dict[str, Any]] = []
    for assignment in protocol.g4_aggregate_assignments():
        subset = tuple(int(value) for value in assignment["target_feature_ids"])
        target_positive = by_identity[(subset, "target", 1)]
        for control_type in protocol.G4_VECTOR_CLASSES:
            positive = by_identity[(subset, control_type, 1)]
            negative = by_identity[(subset, control_type, -1)]
            exact_negative = bool(
                torch.equal(
                    negative.vector.view(torch.int16),
                    torch.neg(positive.vector).view(torch.int16),
                )
            )
            if not exact_negative:
                raise runtime.PilotRuntimeError("g4_negation", "vector pair is not exact negation")
            relation_core = {
                "assignment_id": str(assignment["assignment_id"]),
                "control_type": control_type,
                "dtype": "bfloat16",
                "positive_vector_sha256": positive.vector_sha256,
                "negative_vector_sha256": negative.vector_sha256,
                "relation": "negative_is_exact_elementwise_bfloat16_negation_of_positive",
            }
            resolved_ids = (
                list(subset)
                if control_type == "target"
                else [mapping[value] for value in subset]
                if control_type == "matched"
                else []
            )
            isotropic_seed = (
                protocol.identity_bound_seed64(
                    "g4-isotropic-v1", assignment["assignment_id"]
                )
                if control_type == "isotropic"
                else None
            )
            for signed in (negative, positive):
                vector_rows.append(
                    {
                        "assignment_id": str(assignment["assignment_id"]),
                        "subset_feature_ids": list(subset),
                        "control_type": control_type,
                        "sign": int(signed.sign),
                        "coefficient": float(signed.coefficient),
                        "resolved_feature_ids": resolved_ids,
                        "isotropic_seed": isotropic_seed,
                        "raw_norm": float(signed.raw_norm),
                        "raw_vector_sha256": str(signed.raw_vector_sha256),
                        "norm_rescale": float(signed.norm_rescale),
                        "final_norm": float(signed.final_norm),
                        "norm_relative_error": float(signed.norm_relative_error),
                        "target_reference_final_norm": float(target_positive.final_norm),
                        "vector_rms": float(signed.vector_rms),
                        "vector_sha256": str(signed.vector_sha256),
                        "dtype": "bfloat16",
                        "finite": bool(torch.isfinite(signed.vector).all()),
                        "precomputed_before_any_edited_forward": True,
                        "edited_forward_count_at_compute": 0,
                        "positive_vector_sha256": str(positive.vector_sha256),
                        "negative_vector_sha256": str(negative.vector_sha256),
                        "signed_pair_exact_negation": exact_negative,
                        "signed_pair_relation_sha256": protocol.canonical_sha256(
                            relation_core
                        ),
                    }
                )
    core = {
        "schema_version": 1,
        "study_id": protocol.STUDY_ID,
        "protocol_version": protocol.PROTOCOL_VERSION,
        "status": "pass",
        "plan_manifest_sha256": plan_manifest_sha256,
        "sae_sha256": sae_sha256,
        "decoder_bfloat16_sha256": decoder_bfloat16_sha256,
        "matching_spec_sha256": protocol.canonical_sha256(protocol.G4_MATCHING_SPEC),
        "vector_arithmetic_spec_sha256": protocol.canonical_sha256(
            protocol.G4_VECTOR_ARITHMETIC_SPEC
        ),
        "matching_candidate_inventory_sha256": protocol.canonical_sha256(
            list(matching_table)
        ),
        "target_feature_ids": list(protocol.G4_TARGET_FEATURE_IDS),
        "excluded_feature_ids": list(protocol.G4_TARGET_FEATURE_IDS),
        "target_to_matched": list(target_to_matched),
        "vectors": vector_rows,
    }
    return _sealed(core)


def execute_g4(
    backend: TransformersPilotBackend,
    tokenizer: Any,
    token_receipt: Mapping[str, Any],
    transaction: runtime.PilotTransaction,
    *,
    plan_manifest_sha256: str,
    sae_sha256: str,
) -> None:
    del token_receipt  # Bound by PHASE_BINDING; G4 itself has no lexical score.
    torch = backend.torch
    prompt_token_ids: dict[str, list[int]] = {}
    all_token_residuals: list[Any] = []
    for prompt in protocol.neutral_prompts():
        prompt_id = str(prompt["prompt_id"])
        ids, _ = runtime.render_neutral_fixture(tokenizer, prompt_id)
        prompt_token_ids[prompt_id] = ids
        all_token_residuals.append(backend.capture_layer50_all_tokens(ids).to("cpu"))
    raw_stats, _total_tokens, decoder_hash = compute_g4_feature_statistics(
        backend, all_token_residuals
    )
    matching_table, mapping_rows, matched_ids = resolve_g4_matches(raw_stats)
    write_jsonl_metadata(transaction, "G4_MATCHING_TABLE.jsonl", matching_table)

    vectors = runtime.materialize_g4_vectors(
        backend.sae_decoder, matched_feature_ids=matched_ids
    )
    state = runtime.G4PreflightState()
    state.bind_vectors(vectors)
    sentinel_sessions: dict[str, TransformersPromptSession] = {}
    for prompt in protocol.neutral_prompts():
        prompt_id = str(prompt["prompt_id"])
        session = backend.prepare(prompt_token_ids[prompt_id])
        clean_rms = runtime.tensor_rms(session.clean.residual_by_layer[50])
        state.record_clean_rms(prompt_id, clean_rms)
        append_measurement(
            transaction,
            "g4_clean_rows.jsonl",
            kind="g4_clean",
            key=(prompt_id,),
            measurement={
                "prompt_id": prompt_id,
                "h50_pre_rms": float(clean_rms),
                "finite": True,
            },
        )
        if prompt_id in protocol.G4_SENTINEL_PROMPT_IDS:
            sentinel_sessions[prompt_id] = session
        else:
            session.close()

    inventory = build_g4_vector_inventory(
        vectors,
        plan_manifest_sha256=plan_manifest_sha256,
        sae_sha256=sae_sha256,
        decoder_bfloat16_sha256=decoder_hash,
        matching_table=matching_table,
        target_to_matched=mapping_rows,
    )
    for vector, receipt_row in zip(vectors, inventory["vectors"]):
        if (
            vector.vector_sha256 != receipt_row["vector_sha256"]
            or float(vector.vector_rms) != float(receipt_row["vector_rms"])
        ):
            raise runtime.PilotRuntimeError("g4_inventory", "vector receipt order differs")
        append_measurement(
            transaction,
            "g4_vector_rows.jsonl",
            kind="g4_vector",
            key=(list(vector.subset_feature_ids), vector.control_type, vector.sign),
            measurement={
                "subset_feature_ids": list(vector.subset_feature_ids),
                "control_type": vector.control_type,
                "sign": int(vector.sign),
                "coefficient": float(vector.coefficient),
                "vector_rms": float(vector.vector_rms),
                "vector_sha256": str(vector.vector_sha256),
                "dtype": "bfloat16",
                "finite": bool(torch.isfinite(vector.vector).all()),
                "precomputed_before_any_edited_forward": True,
                "edited_forward_count_at_compute": 0,
            },
        )
    transaction.write_metadata(G4_VECTOR_INVENTORY_FILENAME, inventory)
    state.mark_vector_rows_persisted()
    state.authorize_edits()

    persisted_pre_edit: list[Any] = []
    persisted_post_edit: list[Any] = []
    tensor_index_rows: list[dict[str, Any]] = []
    for prompt_id in protocol.G4_SENTINEL_PROMPT_IDS:
        session = sentinel_sessions[prompt_id]
        clean_source = session.clean.residual_by_layer[50]
        clean_final = session.clean.final_residual
        zero = torch.zeros(backend.width, dtype=torch.bfloat16, device="cpu")
        state.begin_edited_forward()
        sham = session.edited(50, zero, forward_id=f"{prompt_id}:sham")
        clean_pre_sha = runtime.tensor_sha256(clean_source)
        clean_output_sha = runtime.tensor_sha256(clean_final)
        sham_output_sha = runtime.tensor_sha256(sham.final_residual)
        for vector in vectors:
            state.begin_edited_forward()
            forward_id = measurement_task_id(
                "g4_telemetry",
                (prompt_id, list(vector.subset_feature_ids), vector.control_type, vector.sign),
            )
            edited = session.edited(50, vector.vector, forward_id=forward_id)
            requested_vector = vector.vector.to(
                device=edited.pre_edit.device, dtype=torch.bfloat16
            )
            realized = edited.post_edit.float() - edited.pre_edit.float()
            expected_post = (
                edited.pre_edit.to(dtype=torch.bfloat16)
                + requested_vector
            ).to(dtype=torch.bfloat16).contiguous()
            observed_post = edited.post_edit.to(dtype=torch.bfloat16).contiguous()
            expected_post_sha = runtime.tensor_sha256(expected_post)
            observed_post_sha = runtime.tensor_sha256(observed_post)
            if expected_post_sha != observed_post_sha or not torch.equal(
                expected_post.view(torch.int16), observed_post.view(torch.int16)
            ):
                raise runtime.PilotRuntimeError(
                    "g4_exact_hook", "observed post-edit bytes differ from BF16 pre+vector"
                )
            tensor_row_index = len(persisted_pre_edit)
            persisted_pre_edit.append(
                edited.pre_edit.detach().to(device="cpu", dtype=torch.bfloat16).contiguous()
            )
            persisted_post_edit.append(
                observed_post.detach().to(device="cpu", dtype=torch.bfloat16).contiguous()
            )
            tensor_index_rows.append(
                {
                    "tensor_row_index": tensor_row_index,
                    "prompt_id": prompt_id,
                    "subset_feature_ids": list(vector.subset_feature_ids),
                    "control_type": vector.control_type,
                    "sign": int(vector.sign),
                    "pre_edit_sha256": runtime.tensor_sha256(edited.pre_edit),
                    "post_edit_sha256": observed_post_sha,
                }
            )
            measurement = {
                "prompt_id": prompt_id,
                "subset_feature_ids": list(vector.subset_feature_ids),
                "control_type": vector.control_type,
                "sign": int(vector.sign),
                "coefficient": float(vector.coefficient),
                "vector_sha256": str(vector.vector_sha256),
                "input_token_ids_sha256": session.input_token_ids_sha256,
                "clean_input_token_ids_sha256": session.input_token_ids_sha256,
                "clean_pre_edit_sha256": clean_pre_sha,
                "edited_pre_edit_sha256": runtime.tensor_sha256(edited.pre_edit),
                "clean_output_sha256": clean_output_sha,
                "sham_output_sha256": sham_output_sha,
                "expected_post_edit_sha256": expected_post_sha,
                "observed_post_edit_sha256": observed_post_sha,
                "realized_delta_relative_rmse": runtime.relative_rmse(
                    realized, requested_vector
                ),
                "sign_cosine": runtime.cosine_similarity(realized, requested_vector),
                "hook_fire_count": int(edited.hook_fire_count),
                "downstream_finite": bool(torch.isfinite(edited.final_residual).all()),
                "logits_finite": bool(torch.isfinite(edited.logits).all()),
                "attenuation_attempted": False,
                "retry_count": 0,
            }
            append_measurement(
                transaction,
                "g4_telemetry_rows.jsonl",
                kind="g4_telemetry",
                key=(prompt_id, list(vector.subset_feature_ids), vector.control_type, vector.sign),
                measurement=measurement,
            )
        session.close()
    if state.edited_forward_count != 4 * (300 + 1):
        raise runtime.PilotRuntimeError("g4_telemetry_count", "edited grid is incomplete")
    if len(persisted_pre_edit) != 1200 or len(tensor_index_rows) != 1200:
        raise runtime.PilotRuntimeError("g4_tensor_count", "hook tensor grid is incomplete")
    tensor_path = transaction.partial / "G4_HOOK_TENSORS.pt"
    if tensor_path.exists():
        raise runtime.PilotRuntimeError("transaction_overwrite", "hook tensor file exists")
    with tensor_path.open("xb") as handle:
        torch.save(
            {
                "pre_edit": torch.stack(persisted_pre_edit, dim=0),
                "post_edit": torch.stack(persisted_post_edit, dim=0),
            },
            handle,
        )
        handle.flush()
        os.fsync(handle.fileno())
    write_jsonl_metadata(
        transaction, "G4_HOOK_TENSOR_INDEX.jsonl", tensor_index_rows
    )


def phase_binding_receipt(
    *,
    phase: str,
    run_id: str,
    plan_manifest_sha256: str,
    execution_binding: Mapping[str, Any],
    token_receipt: Mapping[str, Any],
) -> dict[str, Any]:
    token_core = dict(token_receipt)
    token_hash = token_core.pop("receipt_sha256", None)
    if token_hash != protocol.canonical_sha256(token_core):
        raise runtime.PilotRuntimeError("token_receipt", "tokenizer receipt self-hash differs")
    core = {
        "schema_version": 1,
        "status": "pass",
        "binding_kind": "gpu_phase_binding_v1",
        "study_id": protocol.STUDY_ID,
        "protocol_version": protocol.PROTOCOL_VERSION,
        "phase": phase,
        "run_id": run_id,
        "plan_manifest_sha256": plan_manifest_sha256,
        "execution_binding_canonical_sha256": execution_binding[
            "execution_binding_canonical_sha256"
        ],
        "tokenizer_audit_receipt_sha256": token_hash,
        "tokenizer_inventory_sha256": token_receipt["tokenizer_inventory_sha256"],
        "runtime_adapter": GPU_ADAPTER_VERSION,
        "prior_outcome_inputs": [],
        "target_prompt_inputs": [],
        "target_outcome_inputs": [],
    }
    return _sealed(core)


def runtime_metadata_receipt(
    backend: TransformersPilotBackend,
    *,
    phase: str,
    run_id: str,
    plan_manifest_sha256: str,
    execution_binding: Mapping[str, Any],
    token_receipt: Mapping[str, Any],
) -> dict[str, Any]:
    observed = backend.runtime_metadata()
    core = {
        "schema_version": 1,
        "status": "pass",
        "metadata_kind": "gpu_phase_runtime_v1",
        "study_id": protocol.STUDY_ID,
        "protocol_version": protocol.PROTOCOL_VERSION,
        "phase": phase,
        "run_id": run_id,
        "plan_manifest_sha256": plan_manifest_sha256,
        "execution_binding_canonical_sha256": execution_binding[
            "execution_binding_canonical_sha256"
        ],
        "tokenizer_audit_receipt_sha256": token_receipt["receipt_sha256"],
        "runtime_adapter": GPU_ADAPTER_VERSION,
        "hook_contract": protocol.HOOK_CONTRACT,
        "container_image": observed["container_image"],
        "model": protocol.MODEL_SPEC,
        "sae": protocol.SAE_SPEC,
        "j_lens": protocol.J_LENS_SPEC,
        "hardware": observed["hardware"],
        "software": observed["software"],
        "determinism": observed["determinism"],
        "model_weights_loaded": True,
        "model_forward_count": observed["model_forward_count"],
        "first_model_forward_at_utc": observed["first_model_forward_at_utc"],
        "last_model_forward_at_utc": observed["last_model_forward_at_utc"],
        "prior_outcome_inputs": [],
        "target_prompt_inputs": [],
        "target_outcome_inputs": [],
    }
    return _sealed(core)


def _assert_bound_adapter_source(binding: Mapping[str, Any]) -> None:
    expected = binding.get("runtime_adapter_source_sha256")
    observed = runtime.sha256_file(Path(__file__).resolve())
    if expected != observed:
        raise runtime.PilotRuntimeError(
            "runtime_source", "execution binding names another GPU adapter source"
        )
    if binding.get("container_image") != protocol.CONTAINER_IMAGE_SPEC:
        raise runtime.PilotRuntimeError(
            "container_image", "execution binding names another container image"
        )


def deterministic_phase_run_ids(run_id_prefix: str) -> dict[str, str]:
    """Derive the exact fresh per-phase run IDs for one shared-backend launch."""

    run_ids = {phase: f"{run_id_prefix}.{phase.lower()}" for phase in protocol.GATE_NAMES}
    if not run_id_prefix or any(
        not runtime.SAFE_RUN_ID.fullmatch(run_id) for run_id in run_ids.values()
    ):
        raise runtime.PilotRuntimeError(
            "run_id_prefix", "run ID prefix cannot produce valid per-phase run IDs"
        )
    return run_ids


def _execute_phase(
    phase: str,
    backend: TransformersPilotBackend,
    tokenizer: Any,
    token_receipt: Mapping[str, Any],
    transaction: runtime.PilotTransaction,
    *,
    plan_manifest_sha256: str,
    sae_sha256: str,
) -> None:
    if phase == "G1":
        execute_g1(backend, token_receipt, transaction)
    elif phase == "G2":
        execute_g2(backend, tokenizer, token_receipt, transaction)
    elif phase == "G3":
        execute_g3(backend, tokenizer, token_receipt, transaction)
    elif phase == "G3P":
        execute_g3p(backend, tokenizer, token_receipt, transaction)
    elif phase == "G4":
        execute_g4(
            backend,
            tokenizer,
            token_receipt,
            transaction,
            plan_manifest_sha256=plan_manifest_sha256,
            sae_sha256=sae_sha256,
        )
    else:
        raise runtime.PilotRuntimeError("phase", f"unknown phase {phase}")


def run_bound_phases(
    *,
    phases: Sequence[str],
    run_ids: Mapping[str, str],
    plan_manifest_path: Path,
    execution_binding_path: Path,
    artifact_root: Path,
    volume_id: str,
    backend_type: type[TransformersPilotBackend] = TransformersPilotBackend,
) -> dict[str, Any]:
    """Validate/load once and emit independent sealed transactions per phase."""

    normalized_phases = tuple(phases)
    if not normalized_phases or len(set(normalized_phases)) != len(normalized_phases):
        raise runtime.PilotRuntimeError("phase", "phase orchestration set is empty or duplicated")
    if any(phase not in protocol.GATE_NAMES for phase in normalized_phases):
        raise runtime.PilotRuntimeError("phase", "phase orchestration set is invalid")
    if len(normalized_phases) > 1 and normalized_phases != tuple(protocol.GATE_NAMES):
        raise runtime.PilotRuntimeError(
            "phase", "multi-phase orchestration must use the complete frozen gate order"
        )
    if set(run_ids) != set(normalized_phases):
        raise runtime.PilotRuntimeError("run_ids", "phase/run-ID mapping differs")
    if any(not runtime.SAFE_RUN_ID.fullmatch(str(run_ids[phase])) for phase in normalized_phases):
        raise runtime.PilotRuntimeError("run_ids", "a phase run ID is invalid")

    _manifest, plan_hash = runtime._load_plan_manifest(plan_manifest_path)
    binding = runtime.load_execution_binding(
        execution_binding_path, plan_manifest_sha256=plan_hash
    )
    if binding.get("resolved_external_root_id") != volume_id:
        raise runtime.PilotRuntimeError("binding_volume", "execution binding volume differs")
    _assert_bound_adapter_source(binding)
    resolved = runtime.validate_local_artifact_binding(
        binding, artifact_root=artifact_root, volume_id=volume_id
    )
    binding_hash = str(binding["execution_binding_canonical_sha256"])
    transactions: dict[str, runtime.PilotTransaction] = {}
    backend: TransformersPilotBackend | None = None
    phase_receipts: list[dict[str, Any]] = []
    try:
        # Every per-phase lineage receipt is durable before the one model import/load.
        # This preserves independent transactions while avoiding five 70B reloads.
        for phase in normalized_phases:
            transactions[phase] = runtime.PilotTransaction(
                artifact_root=artifact_root,
                volume_id=volume_id,
                phase=phase,
                run_id=str(run_ids[phase]),
                plan_manifest_sha256=plan_hash,
                execution_binding_canonical_sha256=binding_hash,
            )
        tokenizer, token_receipt = runtime.tokenizer_preflight(
            resolved["model_snapshot"],
            plan_manifest_sha256=plan_hash,
            tokenizer_inventory_sha256=str(
                binding["tokenizer_content_inventory_sha256"]
            ),
        )
        if token_receipt.get("receipt_sha256") != binding.get(
            "tokenizer_audit_receipt_sha256"
        ):
            raise runtime.PilotRuntimeError(
                "token_receipt",
                "fresh tokenizer audit differs from the bound tokenizer audit",
            )
        for phase in normalized_phases:
            transaction = transactions[phase]
            transaction.write_metadata("TOKENIZER_AUDIT.json", token_receipt)
            transaction.write_metadata(
                "PHASE_BINDING.json",
                phase_binding_receipt(
                    phase=phase,
                    run_id=str(run_ids[phase]),
                    plan_manifest_sha256=plan_hash,
                    execution_binding=binding,
                    token_receipt=token_receipt,
                ),
            )

        backend = backend_type(
            model_snapshot=resolved["model_snapshot"],
            sae_path=resolved["sae"],
            j_lens_path=resolved["j_lens"],
            tokenizer=tokenizer,
        )
        for phase in normalized_phases:
            transaction = transactions[phase]
            backend.start_runtime_interval()
            _execute_phase(
                phase,
                backend,
                tokenizer,
                token_receipt,
                transaction,
                plan_manifest_sha256=plan_hash,
                sae_sha256=str(binding["artifacts"]["sae"]["sha256"]),
            )
            transaction.write_metadata(
                "RUNTIME_METADATA.json",
                runtime_metadata_receipt(
                    backend,
                    phase=phase,
                    run_id=str(run_ids[phase]),
                    plan_manifest_sha256=plan_hash,
                    execution_binding=binding,
                    token_receipt=token_receipt,
                ),
            )
            completed = transaction.complete()
            verification = runtime.verify_completed_transaction(
                completed,
                phase=phase,
                run_id=str(run_ids[phase]),
                plan_manifest_sha256=plan_hash,
                execution_binding_canonical_sha256=binding_hash,
            )
            phase_receipts.append(
                {
                    "phase": phase,
                    "run_id": str(run_ids[phase]),
                    "transaction_path": str(completed),
                    "transaction_verification_receipt_sha256": verification["receipt"][
                        "receipt_sha256"
                    ],
                }
            )
    except BaseException as exc:
        for transaction in transactions.values():
            if not transaction.closed:
                transaction.fail(exc)
        raise
    finally:
        if backend is not None:
            backend.close()

    core = {
        "status": "pass",
        "study_id": protocol.STUDY_ID,
        "orchestration_kind": "single_binding_single_backend_v1",
        "phases": phase_receipts,
        "backend_load_count": 1,
        "artifact_validation_count": 1,
        "tokenizer_audit_count": 1,
        "plan_manifest_sha256": plan_hash,
        "execution_binding_canonical_sha256": binding_hash,
    }
    return {**core, "orchestration_receipt_sha256": protocol.canonical_sha256(core)}


def run_bound_phase(
    *,
    phase: str,
    plan_manifest_path: Path,
    execution_binding_path: Path,
    artifact_root: Path,
    volume_id: str,
    run_id: str,
    backend_type: type[TransformersPilotBackend] = TransformersPilotBackend,
) -> dict[str, Any]:
    """Compatibility entry point for one independently sealed phase."""

    orchestration = run_bound_phases(
        phases=(phase,),
        run_ids={phase: run_id},
        plan_manifest_path=plan_manifest_path,
        execution_binding_path=execution_binding_path,
        artifact_root=artifact_root,
        volume_id=volume_id,
        backend_type=backend_type,
    )
    phase_receipt = orchestration["phases"][0]
    return {
        "status": "pass",
        "study_id": protocol.STUDY_ID,
        "phase": phase,
        "run_id": run_id,
        "transaction_path": phase_receipt["transaction_path"],
        "plan_manifest_sha256": orchestration["plan_manifest_sha256"],
        "execution_binding_canonical_sha256": orchestration[
            "execution_binding_canonical_sha256"
        ],
        "transaction_verification_receipt_sha256": phase_receipt[
            "transaction_verification_receipt_sha256"
        ],
    }


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    selection = parser.add_mutually_exclusive_group(required=True)
    selection.add_argument("--phase", choices=tuple(runtime.PHASE_TO_DIRECTORY))
    selection.add_argument("--all-phases", action="store_true")
    parser.add_argument("--plan-manifest", type=Path, required=True)
    parser.add_argument("--execution-binding", type=Path, required=True)
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--volume-id", required=True)
    parser.add_argument("--run-id")
    parser.add_argument("--run-id-prefix")
    args = parser.parse_args(argv)
    if args.all_phases:
        if args.run_id_prefix is None or args.run_id is not None:
            parser.error("--all-phases requires --run-id-prefix and forbids --run-id")
    elif args.run_id is None or args.run_id_prefix is not None:
        parser.error("--phase requires --run-id and forbids --run-id-prefix")
    return args


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    if args.all_phases:
        receipt = run_bound_phases(
            phases=protocol.GATE_NAMES,
            run_ids=deterministic_phase_run_ids(args.run_id_prefix),
            plan_manifest_path=args.plan_manifest,
            execution_binding_path=args.execution_binding,
            artifact_root=args.artifact_root,
            volume_id=args.volume_id,
        )
    else:
        receipt = run_bound_phase(
            phase=args.phase,
            plan_manifest_path=args.plan_manifest,
            execution_binding_path=args.execution_binding,
            artifact_root=args.artifact_root,
            volume_id=args.volume_id,
            run_id=args.run_id,
        )
    print(protocol.canonical_json_bytes(receipt).decode("utf-8"))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

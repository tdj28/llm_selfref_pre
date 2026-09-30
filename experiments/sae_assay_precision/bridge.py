"""Explicit hybrid FP32 residual model; no loading, dispatch, or file writes.

This is NOT an FP32 shadow measurement of the unchanged BF16 model. After the
chosen layer's output, residuals stay FP32, while existing RMSNorm outputs are
cast to BF16 before attention/MLP/head linears. The cast occurs AFTER the norm's
weight multiplication, unlike the native norm's intermediate BF16 rounding.
Both that change and FP32 residual additions belong to the precision sham.

Use a direct ``backend.model.model(...)`` forward inside ``precision_bridge``;
do not compose with the diagnostic backend's editing hooks. Use fresh KV caches
for different arms. The caller supplies an already formed, baseline-anchored
FP32 request: this module neither selects features nor changes its vector/cap.
CPU synthetic tests do not establish production CUDA parity or assay validity.
"""

from contextlib import ExitStack
from importlib.metadata import version
from types import SimpleNamespace
import weakref

import torch
import torch.nn.functional as F

from experiments.sae_assay_diagnostic.backend import (
    _finite, _finite_chunks, _fp32_math, _linear_token1,
)


READOUT_AUTHORITY = "full_promoted_bf16_fp32_token1_v1"
BRIDGE_VERSION = "fp32_residual_bf16_postnorm_cast_v1"
_ACTIVE_MODELS = weakref.WeakSet()


def _delivery(clean, requested, edited):
    """CPU FP64 measurement of actual stored tensors, including FP32 loss."""
    h, r, x = (value.detach().cpu().double() for value in (clean, requested, edited))
    realized = x - h
    rn, an, hn = (torch.linalg.vector_norm(value, dim=-1) for value in (r, realized, h))
    nz = rn > 0
    tiny = torch.finfo(torch.float64).tiny
    cosine = (r * realized).sum(-1) / (rn * an).clamp_min(tiny)
    error = torch.linalg.vector_norm(realized - r, dim=-1)
    return {"requested_norm": rn, "realized_norm": an, "clean_norm": hn,
            "nonzero_requested": nz, "identity": (x == h).all(-1),
            "cosine": torch.where(nz, cosine.clamp(-1, 1), 1.),
            "relative_error": torch.where(nz, error / rn.clamp_min(tiny), 0.)}


@torch.inference_mode()
def full_width_readout(clean_native, edited_state, encoder_bf16, bias_bf16):
    """Separate full-width token-one readouts; all inputs must share a device.

    Supply the COMPLETE pinned BF16 dictionary, not selected rows. Promotion
    preserves those weights' values, not native arithmetic. No feature selection
    occurs here. Returned tensors are CPU observations, not qualification flags.
    A full FP32 encoder copy is temporary and needs its own memory allowance.
    """
    h, x, e, b = clean_native, edited_state, encoder_bf16, bias_bf16
    if (h.ndim < 2 or not h.numel() or x.shape != h.shape or e.ndim != 2
            or e.shape[1] != h.shape[-1] or not e.shape[0] or b.shape != (e.shape[0],)
            or h.dtype != torch.bfloat16 or e.dtype != h.dtype or b.dtype != h.dtype
            or x.dtype not in (torch.bfloat16, torch.float32)
            or any(t.device != h.device for t in (x, e, b))):
        raise ValueError("Readout requires compatible full BF16 weights and native/FP32 states")
    for name, value in (("clean", h), ("edited", x), ("encoder", e), ("bias", b)):
        _finite_chunks(name, value)
    with _fp32_math(h.device):
        native = F.relu(_linear_token1(h, e, b)).float().cpu()
        rounded = F.relu(_linear_token1(x.to(torch.bfloat16), e, b)).float().cpu()
        ef, bf = e.float(), b.float()
        clean = F.relu(_linear_token1(h.float(), ef, bf)).cpu()
        edited = F.relu(_linear_token1(x.float(), ef, bf)).cpu()
    tensors = {"native_clean": native, "promoted_clean": clean,
               "promoted_edited": edited, "native_rounded_edited": rounded,
               "precision_readout_shift": clean - native,
               "promoted_edit_delta": edited - clean,
               "native_rounded_edit_delta": rounded - native}
    for name, value in tensors.items():
        _finite(name, value)
    return {"authority": READOUT_AUTHORITY, "native_encoding_replacement": False,
            "full_encode_shape": [1, e.shape[0], e.shape[1]], **tensors}


class PrecisionBridge:
    """Single-use, serial context around caller-owned, evaluation-mode Llama.

    ``edit_callback`` receives a detached BF16 COPY and must return an FP32
    request with exactly its shape/device. None means precision-sham. Native
    zero has no norm hooks and returns the original output object, unchanged.
    ``records`` retains CPU copies of the actual boundary states/requests, and
    ``boundary_trace`` records the downstream normalization dtype transitions.
    Parameters/buffers are never replaced, converted or assigned by this class.
    """

    def __init__(self, backend, edit_callback=None, *, native_zero=False):
        if type(native_zero) is not bool or (native_zero and edit_callback is not None):
            raise ValueError("Native zero must bypass editing, with no callback")
        if edit_callback is not None and not callable(edit_callback):
            raise ValueError("edit_callback must be callable")
        self.model = backend.model
        self.layer_index = backend.layer_index
        self.callback = edit_callback
        self.native_zero = native_zero
        if (version("transformers") != "4.47.1"
                or torch.__version__.split("+")[0] != "2.8.0"):
            raise RuntimeError("Bridge requires torch 2.8.0 and transformers 4.47.1")
        config = self.model.config
        if (config.model_type != "llama" or config._attn_implementation != "sdpa"
                or backend.dtype != torch.bfloat16):
            raise ValueError("Bridge requires the explicit BF16 Llama/SDPA path")
        if any(module.training for module in self.model.modules()):
            raise ValueError("Bridge is evaluation-only")
        self.core = self.model.model
        layers = self.core.layers
        if (type(self.layer_index) is not int
                or not 0 <= self.layer_index < len(layers) - 1):
            raise ValueError("Boundary must precede at least one downstream layer")
        self.layer = layers[self.layer_index]
        self.device = self.model.get_input_embeddings().weight.device
        if self.device.type not in ("cpu", "cuda"):
            raise ValueError("Only explicit CPU/CUDA execution is supported")
        if self.device.type == "cuda" and torch.version.cuda != "12.8":
            raise RuntimeError("CUDA bridge requires the pinned CUDA 12.8 runtime")
        for parameter in self.model.parameters():
            if parameter.device != self.device or parameter.dtype != torch.bfloat16:
                raise ValueError("All model parameters must remain resident native BF16")
        if any(buffer.device != self.device for buffer in self.model.buffers()):
            raise ValueError("Model buffers must remain on the same device")
        self.norms = []
        for index in range(self.layer_index + 1, len(layers)):
            for name in ("input_layernorm", "post_attention_layernorm"):
                self.norms.append((f"model.layers.{index}.{name}", getattr(layers[index], name)))
        self.norms.append(("model.norm", self.core.norm))
        if any(type(norm).__name__ != "LlamaRMSNorm" for _, norm in self.norms):
            raise ValueError("Unexpected downstream normalization implementation")
        self.records = []
        self.boundary_trace = []
        self.metadata = {
            "bridge_version": BRIDGE_VERSION,
            "arm": "native_zero" if native_zero else (
                "precision_sham" if edit_callback is None else "signed_edit"),
            "hook_layer": f"model.layers.{self.layer_index}.output",
            "residual_dtype": "torch.bfloat16" if native_zero else "torch.float32",
            "sublayer_dtype": "torch.bfloat16",
            "normalization_boundary": "unchanged native" if native_zero else (
                "existing FP32 RMSNorm output, including weight multiplication, cast to BF16"),
            "higher_precision_residual_model": not native_zero,
            "fp32_shadow_only": False,
            "new_operator": not native_zero,
            "readout_authority": READOUT_AUTHORITY,
            "hooks_removed": False,
        }
        self._stack = None
        self._used = False
        self._pending = []

    def _boundary(self, _module, _inputs, output):
        if self._pending:
            raise RuntimeError("Previous forward did not traverse every bridge boundary")
        hidden = output[0] if isinstance(output, tuple) else output
        if (not isinstance(hidden, torch.Tensor) or hidden.ndim != 3
                or not hidden.numel() or hidden.dtype != torch.bfloat16
                or hidden.device != self.device):
            raise RuntimeError("Bridge input must be a nonempty native BF16 residual")
        _finite("bridge clean residual", hidden)
        with _fp32_math(self.device):
            requested = (torch.zeros_like(hidden, dtype=torch.float32) if self.callback is None
                         else self.callback(hidden.detach().clone()))
            if (not isinstance(requested, torch.Tensor) or requested.shape != hidden.shape
                    or requested.dtype != torch.float32 or requested.device != hidden.device):
                raise ValueError("Callback must return a same-shape/device FP32 requested vector")
            _finite("bridge requested vector", requested)
            if self.native_zero:
                edited = hidden
            elif self.callback is None:
                edited = hidden.float()
            else:
                edited = hidden.float() + requested
        _finite("bridge edited residual", edited)
        self.records.append({
            "clean_native": hidden.detach().cpu().clone(),
            "requested_fp32": requested.detach().cpu().clone(),
            "edited_state": edited.detach().cpu().clone(),
            "delivery": _delivery(hidden, requested, edited),
            "returned_original_output": self.native_zero,
        })
        if self.native_zero:
            return output
        self._pending = [name for name, _ in self.norms]
        return (edited,) + output[1:] if isinstance(output, tuple) else edited

    def _norm_hook(self, name):
        def hook(_module, inputs, output):
            if (not self._pending or self._pending[0] != name
                    or len(inputs) != 1 or inputs[0].dtype != torch.float32
                    or not isinstance(output, torch.Tensor) or output.dtype != torch.float32
                    or output.shape != inputs[0].shape or output.device != self.device):
                raise RuntimeError("Unexpected FP32 residual/norm boundary: " + name)
            _finite("bridge normalized output", output)
            returned = output.to(torch.bfloat16)
            _finite("bridge BF16 normalized output", returned)
            self.boundary_trace.append({"call": len(self.records) - 1, "module": name,
                                        "input_dtype": str(inputs[0].dtype),
                                        "output_dtype": str(output.dtype),
                                        "returned_dtype": str(returned.dtype)})
            self._pending.pop(0)
            return returned
        return hook

    def __enter__(self):
        if self._used or self.model in _ACTIVE_MODELS:
            raise RuntimeError("Bridge contexts are single-use and cannot overlap on a model")
        if torch.is_autocast_enabled(self.device.type):
            raise RuntimeError("Bridge requires autocast disabled; no silent baseline change")
        self._used = True
        stack = ExitStack()
        try:
            _ACTIVE_MODELS.add(self.model)
            stack.callback(_ACTIVE_MODELS.discard, self.model)
            stack.enter_context(torch.inference_mode())
            stack.callback(self.layer.register_forward_hook(self._boundary).remove)
            if not self.native_zero:
                for name, norm in self.norms:
                    stack.callback(norm.register_forward_hook(self._norm_hook(name)).remove)
        except BaseException:
            stack.close()
            self.metadata["hooks_removed"] = True
            raise
        self._stack = stack
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        try:
            self._stack.close()
        finally:
            self._stack = None
            self.metadata["hooks_removed"] = True
        if exc_type is None and self._pending:
            raise RuntimeError("Forward ended before all downstream norms were observed")
        return False


def precision_bridge(backend, edit_callback=None, *, native_zero=False):
    """Install nothing until entered; remove all owned hooks even on failure."""
    return PrecisionBridge(backend, edit_callback, native_zero=native_zero)


def qualify_bridge(device="cpu"):
    """Random tiny real-Llama checks on the EXPLICIT device; never pretrained.

    This function is not called by bridge construction. CUDA invocation needs
    separate authorization; CPU results cannot certify CUDA or production.
    No files are created, no text is generated, and no network API is used.
    """
    from transformers import DynamicCache, LlamaConfig, LlamaForCausalLM

    target = torch.device(device)
    if target.type not in ("cpu", "cuda"):
        raise ValueError("Qualification requires an explicit CPU or CUDA device")
    cuda_devices = []
    if target.type == "cuda":
        if not torch.cuda.is_available() or not torch.cuda.is_bf16_supported():
            raise RuntimeError("Native CUDA BF16 required; no device fallback")
        target = torch.device("cuda", target.index if target.index is not None
                              else torch.cuda.current_device())
        cuda_devices = [target.index]
    with torch.random.fork_rng(devices=cuda_devices):
        torch.manual_seed(1729)
        config = LlamaConfig(vocab_size=32, hidden_size=16, intermediate_size=32,
                             num_hidden_layers=3, num_attention_heads=2,
                             num_key_value_heads=2, max_position_embeddings=64,
                             attention_dropout=0., bos_token_id=1, eos_token_id=2)
        config._attn_implementation = "sdpa"
        model = LlamaForCausalLM(config).to(device=target, dtype=torch.bfloat16).eval()
    backend = SimpleNamespace(model=model, layer_index=0, dtype=torch.bfloat16)
    frozen = {name: value.detach().cpu().clone() for name, value in model.state_dict().items()}
    tokens = torch.tensor([[1, 4, 5]], device=target)
    checks = {}
    with torch.inference_mode():
        reference = model.model(tokens, use_cache=False).last_hidden_state
        with precision_bridge(backend, native_zero=True) as native:
            zero = model.model(tokens, use_cache=False).last_hidden_state
        checks["native_zero_exact"] = torch.equal(reference, zero)
        checks["native_zero_identity"] = (native.records[0]["returned_original_output"]
                                           and bool(native.records[0]["delivery"]["identity"].all())
                                           and not native.boundary_trace)
        for arm, sign in (("sham", 0.), ("negative", -1.), ("positive", 1.)):
            callback = None if sign == 0 else (
                lambda h, sign=sign: torch.full_like(h, sign * 1e-4, dtype=torch.float32))
            with precision_bridge(backend, callback) as bridge:
                result = model.model(tokens, use_cache=True, past_key_values=DynamicCache())
                result = model.model(torch.tensor([[6]], device=target), use_cache=True,
                                     past_key_values=result.past_key_values)
            checks[arm + "_boundary_dtypes"] = (len(bridge.records) == 2
                and all(record["edited_state"].dtype == torch.float32 for record in bridge.records)
                and len(bridge.boundary_trace) == 2 * (2 * (config.num_hidden_layers - 1) + 1)
                and all(event["input_dtype"] == "torch.float32"
                        and event["returned_dtype"] == "torch.bfloat16"
                        for event in bridge.boundary_trace)
                and result.last_hidden_state.dtype == torch.bfloat16)
            checks[arm + "_kv_bf16"] = all(
                tensor.dtype == torch.bfloat16 for pair in result.past_key_values for tensor in pair)
            checks[arm + "_request_preserved"] = all(torch.equal(
                record["edited_state"], record["clean_native"].float() + record["requested_fp32"])
                for record in bridge.records)
            checks[arm + "_zero_or_fidelity"] = all(
                bool(record["delivery"]["identity"].all()) if sign == 0 else
                bool(((record["delivery"]["relative_error"] <= .2)
                      & (record["delivery"]["cosine"] >= .95)).all())
                for record in bridge.records)
        checks["weights_and_buffers_unchanged"] = all(
            torch.equal(value, model.state_dict()[name].cpu()) for name, value in frozen.items())
        checks["all_hooks_removed"] = not any(
            module._forward_hooks or module._forward_pre_hooks for module in model.modules())
        checks["native_restored"] = torch.equal(
            reference, model.model(tokens, use_cache=False).last_hidden_state)
    return {"pass": all(checks.values()), "checks": checks, "synthetic_only": True,
            "production_model_loaded": False, "device": str(target),
            "bridge_version": BRIDGE_VERSION, "torch": torch.__version__,
            "transformers": version("transformers"), "cuda": torch.version.cuda}

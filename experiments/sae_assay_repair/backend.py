"""Explicit alternate operators on the unchanged pinned BF16 model/SAE.

The original backend remains immutable. This subclass replaces only the hook
arithmetic, records that replacement, and optionally persists clean residuals.
"""
from pathlib import Path

import torch
import torch.nn.functional as F

from experiments.sae_assay_diagnostic.backend import (
    ACTIVATION_COLUMNS, REFERENCE_COLUMNS, ModelBackend, edit_hidden, _finite,
    _fp32_math, _linear_token1,
)
from .operators import prepare_geometry, repair_hidden
from .summary_correction import summarize_activations


DELIVERY = ("clean_norm", "cosine", "identity", "nonzero_requested",
            "realized_norm", "relative_error", "requested_norm", "valid")


class RepairBackend(ModelBackend):
    operator = "literal"
    capture_path = None

    _summaries = staticmethod(summarize_activations)

    def geometry(self, ids):
        if not hasattr(self, "_geometries"):
            self._geometries = {}
        key = tuple(ids)
        if key not in self._geometries:
            self._geometries[key] = prepare_geometry(*self._sae[:3], feature_ids=ids)
        return self._geometries[key]

    def _full_diagnostic(self, hidden, edited, feature_ids):
        recon, metrics = super()._full_diagnostic(hidden, edited, feature_ids)
        e = self._sae[0][list(feature_ids)]
        b = self._sae[1][list(feature_ids)]
        for key, values in (("before", hidden), ("after", edited)):
            flat = values.reshape(-1, values.shape[-1])
            # Historical mapping used separate native matmul and bias addition.
            metrics["historical_matmul_add_" + key] = F.relu(flat @ e.T + b).float()
            with _fp32_math(self.device):
                metrics["fp32_preact_" + key] = _linear_token1(flat.float(), e.float(), b.float())
        return recon, metrics

    @torch.inference_mode()
    def _forward(self, token_ids, feature_ids, intervention=None, *, offset=0,
                 prompt_length=None, past=None, use_cache=False,
                 collect_reconstruction=False, reconstruct=False):
        self._assert_resident()
        ids, edit_args = self._intervention(feature_ids, intervention)
        records, calls = {}, 0
        prompt_length = token_ids.shape[1] if prompt_length is None else prompt_length
        token_list = token_ids[0].tolist()
        specials = set(self.tokenizer.all_special_ids)

        def hook(_module, _inputs, output):
            nonlocal calls
            calls += 1
            if calls != 1:
                raise RuntimeError("Layer hook fired more than once")
            hidden = output[0] if isinstance(output, tuple) else output
            if hidden.shape[:2] != token_ids.shape or hidden.dtype != self.dtype:
                raise RuntimeError("Hook shape/dtype mismatch")
            if self.capture_path is not None and intervention is None and not reconstruct:
                from safetensors.torch import save_file
                destination = Path(self.capture_path)
                if destination.exists():
                    raise ValueError("Refusing to replace a residual capture")
                destination.parent.mkdir(parents=True, exist_ok=True)
                save_file({"hidden": hidden.detach().cpu().contiguous(),
                           "token_ids": token_ids.detach().cpu().contiguous()}, str(destination))
                self.capture_path = None
            if (self.operator == "literal" or intervention is None or reconstruct
                    or intervention["strength"] == 0):
                edited, metrics = edit_hidden(
                    hidden, *self._sae[:3], feature_ids=ids,
                    collect_reference=collect_reconstruction,
                    _validated_weights=True, **edit_args)
            else:
                edited, metrics = repair_hidden(
                    hidden, *self._sae[:3], feature_ids=ids,
                    operator=self.operator, geometry=self.geometry(ids), **edit_args)
            diagnostic = None
            if collect_reconstruction or reconstruct:
                recon, diagnostic = self._full_diagnostic(hidden, edited, ids)
                if reconstruct:
                    edited = recon
                else:
                    for key in REFERENCE_COLUMNS:
                        if key in metrics:
                            diagnostic[key] = metrics[key][0]
                    for key in ("desired_preact", "requested_preact_delta", "solve_coefficients",
                                "solve_residual", "condition", "eligible"):
                        if key in metrics:
                            diagnostic["repair_" + key] = metrics[key][0]
            cpu = {key: value[0].cpu().tolist() for key, value in metrics.items()
                   if key in ACTIVATION_COLUMNS or key in DELIVERY}
            records["selected_activations"] = {key: cpu.pop(key) for key in ACTIVATION_COLUMNS}
            records["delivery"] = cpu
            records["full_sae"] = ({key: value.cpu().tolist() for key, value in diagnostic.items()}
                                   if diagnostic is not None else None)
            records["position_metadata"] = [dict(
                position=offset + i, token_id=token,
                origin="prompt" if offset + i < prompt_length else "generated",
                token_class="special" if token in specials else (
                    "prompt" if offset + i < prompt_length else "generated"),
                terminal_observation_only=False) for i, token in enumerate(token_list)]
            if edited is hidden:
                return output
            return (edited,) + output[1:] if isinstance(output, tuple) else edited

        handle = self._layer.register_forward_hook(hook)
        try:
            result = self.model.model(
                input_ids=token_ids, attention_mask=torch.ones(
                    (1, offset + len(token_list)), dtype=torch.long, device=self.device),
                past_key_values=past, use_cache=use_cache, return_dict=True)
        finally:
            handle.remove()
        if calls != 1:
            raise RuntimeError("Expected one hook call")
        _finite("final hidden states", result.last_hidden_state)
        return result, records

    def _telemetry(self, ids, batches, intervention=None):
        result = super()._telemetry(ids, batches, intervention)
        result["repair_operator"] = self.operator
        result["edit_arithmetic"] = {
            "literal": "FP32 h + W_D delta, one native cast; original Stage 1 operator",
            "decoder_span": "FP32 decoder-span preactivation solve; one native cast",
            "encoder_min_norm": "FP32 minimum-residual-norm preactivation solve; one native cast",
        }[self.operator]
        return result

    def close(self):
        self._geometries = {}
        super().close()

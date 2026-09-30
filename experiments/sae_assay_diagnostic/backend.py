"""Pinned, single-GPU computation for the assay diagnostic, without orchestration.

Ordinary hooks encode only the requested SAE rows with F.linear, as in the old
Goodfire SparseAutoEncoder: ReLU(W_E h + b_E), *without* subtracting b_D.
Selected-row GEMMs are algebraically, but not necessarily bitwise, equivalent
to the full-width encoder in BF16. Keep ordered feature IDs and token-batch
shapes fixed in paired comparisons. Before/after encoding uses identical
shapes; full-SAE diagnostics disclose their separate numerical path. Neither
this implementation nor the tests establish full-width numerical equivalence.
In particular, candidate-pool (e.g. 512-row) q90 is not assumed identical to
panel (e.g. six-row) q90. The parent must compare/recompute and freeze that
encoding contract before using calibration quantiles for amplification.

The requested decoder product and residual addition are FP32, followed by one
cast to the hidden state's native dtype (BF16 in production). Delivery metrics
compare that request to edited.float() - hidden.float(), retaining rounding.
Full SAE weights stay on CPU; only selected rows/columns are normally on GPU.
teacher(collect_reconstruction=True) temporarily places the full SAE on GPU,
chunking positions, and runs a separate reconstruction-only loss diagnostic.
No full-vocabulary logits or full-SAE position matrix is retained across calls.

Constructor loading may download pinned artifacts; importing this module and
from_components_for_test do not access the network. Runtime/cost authorization,
fixtures, gate decisions, file writes, and calibration quantiles belong to the
parent runner. Metadata records content hashes bound to the immutable Hub
revision (Git blob SHA1 for small files, LFS SHA256 for weights), plus SHA256
receipts. The SAE also has an independently frozen SHA256 from the old release.
"""

from __future__ import annotations

from contextlib import contextmanager
import gc
import hashlib
import json
import math
from pathlib import Path
import time
from typing import Any, Mapping, Sequence

import torch
import torch.nn.functional as F


MODEL_ID = "meta-llama/Llama-3.3-70B-Instruct"
MODEL_REVISION = "6f6073b423013f6a7d4d9f39144961bfbfbc386b"
SAE_ID = "Goodfire/Llama-3.3-70B-Instruct-SAE-l50"
SAE_REVISION = "128ee921ecd1b8b3a87d776cbcc357c0855da134"
SAE_FILENAME = "Llama-3.3-70B-Instruct-SAE-l50.pt"
SAE_FILE_SHA256 = "81cfce8ea035564cb585d6e0f04efbf0eb114cab412a30a013762fe11f6d8ea6"
LAYER_INDEX = 50
TARGET_IDS = (30032, 58667, 22004, 30686, 41533, 23893)
ENCODING_NOTE = "selected-row F.linear; no bitwise full-width equivalence asserted"
TELEMETRY_SCHEMA = "sae_assay_backend_v1"
# Proposed diagnostic threshold, not validated and not inherited from a replay gate.
# A failed check is reported without switching encoders or making a run decision.
SELECTED_FULL_MAX_ABS_TOLERANCE = 0.02
ACTIVATION_COLUMNS = ("before", "requested_delta", "requested_activation", "after")
SAE_KEYS = ("encoder_linear.weight", "encoder_linear.bias",
            "decoder_linear.weight", "decoder_linear.bias")


def _finite(name: str, tensor: torch.Tensor) -> None:
    if not bool(torch.isfinite(tensor).all()):
        raise FloatingPointError(f"Nonfinite {name}")


def _finite_chunks(name: str, tensor: torch.Tensor) -> None:
    # Slice rows, not reshape: the decoder/selected columns may be noncontiguous.
    if tensor.ndim == 0:
        _finite(name, tensor)
        return
    step = max(1, 8_388_608 // max(1, tensor[0].numel())) if len(tensor) else 1
    for start in range(0, len(tensor), step):
        _finite(name, tensor[start:start + step])


def _ids(values: Sequence[int], width: int) -> tuple[int, ...]:
    result = tuple(values)
    if not result or any(type(i) is not int or not 0 <= i < width for i in result):
        raise ValueError(f"Feature IDs must be nonempty integers in [0, {width})")
    if len(set(result)) != len(result):
        raise ValueError("Duplicate feature IDs")
    return result


@torch.inference_mode()
def edit_hidden(
    hidden: torch.Tensor,
    encoder_weight: torch.Tensor,
    encoder_bias: torch.Tensor,
    decoder_weight: torch.Tensor,
    *,
    mode: str | None = None,
    strength: float = 0.0,
    q90: Sequence[float] | torch.Tensor | None = None,
    valid_mask: torch.Tensor | None = None,
) -> tuple[torch.Tensor, dict[str, torch.Tensor]]:
    """Edit selected coordinates; weights have shapes [K,H], [K], [H,K].

    Returns the original tensor object for true zero. Masked positions stay
    unchanged. Zero-request cosine is 1 by convention; a nonzero request lost
    to rounding has cosine 0 and relative error 1, never a missing observation.
    The FP32 residual request is added in FP32, then cast exactly once to the
    native hidden dtype. All diagnostics are FP32 except boolean indicators.
    strength=0 is an explicit zero arm; nonzero strengths are only .5 and 1.
    """
    if hidden.ndim < 2 or not hidden.is_floating_point():
        raise ValueError("hidden must be a floating tensor with position and width axes")
    k, width = encoder_weight.shape
    if (hidden.shape[-1] != width or tuple(encoder_bias.shape) != (k,)
            or tuple(decoder_weight.shape) != (width, k) or k == 0):
        raise ValueError("Incompatible selected SAE shapes")
    for name, value in (("hidden", hidden), ("encoder", encoder_weight),
                        ("encoder bias", encoder_bias), ("decoder", decoder_weight)):
        if value.device != hidden.device or value.dtype != hidden.dtype:
            raise ValueError("SAE and hidden must share device and native dtype")
        _finite(name, value)
    if isinstance(strength, bool) or strength not in (0.0, 0.5, 1.0):
        raise ValueError("strength must be 0, .5, or 1")
    if mode not in (None, "suppression", "amplification") or (mode is None and strength):
        raise ValueError("Invalid intervention mode")
    mask = torch.ones(hidden.shape[:-1], dtype=torch.bool, device=hidden.device)
    if valid_mask is not None:
        if valid_mask.shape != mask.shape or valid_mask.dtype != torch.bool:
            raise ValueError("valid_mask must be boolean and match position axes")
        mask = valid_mask.to(hidden.device)
    before = F.relu(F.linear(hidden, encoder_weight, encoder_bias))
    _finite("selected activations", before)
    before32 = before.float()
    delta = torch.zeros_like(before32)
    if mode == "amplification":
        if q90 is None:
            raise ValueError("Amplification requires one positive-activation q90 per feature")
        quantiles = torch.as_tensor(q90, dtype=torch.float32, device=hidden.device)
        if quantiles.shape != (k,):
            raise ValueError("q90 must match ordered feature IDs")
        _finite("q90", quantiles)
        if bool((quantiles < 0).any()):
            raise ValueError("q90 cannot be negative")
        delta = strength * (quantiles - before32).clamp_min(0)
    elif mode == "suppression":
        delta = -strength * before32
    delta = torch.where(mask.unsqueeze(-1), delta, 0.0)
    old_tf32 = torch.backends.cuda.matmul.allow_tf32
    try:
        torch.backends.cuda.matmul.allow_tf32 = False
        requested = F.linear(delta, decoder_weight.float())
    finally:
        torch.backends.cuda.matmul.allow_tf32 = old_tf32
    _finite("requested residual edit", requested)
    zero = not bool(torch.count_nonzero(delta))
    if zero:
        edited, after = hidden, before
    else:
        edited = torch.where(mask.unsqueeze(-1),
                             (hidden.float() + requested).to(hidden.dtype), hidden)
        _finite("edited hidden", edited)
        after = F.relu(F.linear(edited, encoder_weight, encoder_bias))
        _finite("reencoded activations", after)
    realized = edited.float() - hidden.float()
    requested_norm = torch.linalg.vector_norm(requested, dim=-1)
    realized_norm = torch.linalg.vector_norm(realized, dim=-1)
    clean_norm = torch.linalg.vector_norm(hidden.float(), dim=-1)
    error_norm = torch.linalg.vector_norm(realized - requested, dim=-1)
    nonzero = requested_norm > 0
    cosine = (requested * realized).sum(-1) / (
        requested_norm * realized_norm).clamp_min(torch.finfo(torch.float32).tiny)
    cosine = torch.where(nonzero, cosine.clamp(-1, 1), 1.0)
    relative_error = torch.where(nonzero, error_norm / requested_norm.clamp_min(
        torch.finfo(torch.float32).tiny), 0.0)
    telemetry = {
        "before": before32, "requested_delta": delta,
        "requested_activation": before32 + delta, "after": after.float(),
        "requested_norm": requested_norm, "realized_norm": realized_norm,
        "cosine": cosine, "relative_error": relative_error,
        "clean_norm": clean_norm,
        "identity": (edited == hidden).all(-1), "valid": mask,
        "nonzero_requested": nonzero,
    }
    for name, value in telemetry.items():
        _finite(name, value)
    return edited, telemetry


def _hash_file(path: Path, expected: str, algorithm: str) -> str:
    sha256 = hashlib.sha256()
    bound = hashlib.sha1() if algorithm == "git_sha1" else hashlib.sha256()
    if algorithm not in ("git_sha1", "sha256"):
        raise ValueError("Unknown artifact hash algorithm")
    if algorithm == "git_sha1":
        bound.update(f"blob {path.stat().st_size}\0".encode("ascii"))
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            sha256.update(chunk)
            bound.update(chunk)
    if bound.hexdigest() != expected:
        raise RuntimeError(f"Artifact hash mismatch: {path.name}")
    return sha256.hexdigest()


def _load_artifacts(cache_dir: str | Path) -> tuple[Path, Path, dict[str, Any]]:
    from huggingface_hub import HfApi, hf_hub_download, snapshot_download

    info = HfApi().model_info(MODEL_ID, revision=MODEL_REVISION, files_metadata=True)
    if info.sha != MODEL_REVISION:
        raise RuntimeError("Model revision mismatch")
    names = {"config.json", "generation_config.json", "tokenizer.json",
             "tokenizer_config.json", "special_tokens_map.json",
             "model.safetensors.index.json", "chat_template.jinja"}
    artifacts = [s for s in info.siblings if s.rfilename in names or (
        s.rfilename.startswith("model-") and s.rfilename.endswith(".safetensors"))]
    if not {"config.json", "tokenizer.json", "tokenizer_config.json",
            "model.safetensors.index.json"}.issubset({s.rfilename for s in artifacts}):
        raise RuntimeError("Pinned model artifact inventory is incomplete")
    snapshot = Path(snapshot_download(
        MODEL_ID, revision=MODEL_REVISION, cache_dir=str(cache_dir),
        allow_patterns=[s.rfilename for s in artifacts],
    ))
    receipts = {}
    for artifact in artifacts:
        lfs = artifact.lfs
        expected = (lfs["sha256"] if isinstance(lfs, dict) else lfs.sha256) if lfs else artifact.blob_id
        algorithm = "sha256" if lfs else "git_sha1"
        path = snapshot / artifact.rfilename
        receipts[artifact.rfilename] = {
            "revision_hash": expected, "revision_hash_algorithm": algorithm,
            "sha256": _hash_file(path, expected, algorithm), "bytes": path.stat().st_size,
        }
    index = json.loads((snapshot / "model.safetensors.index.json").read_text())
    if not set(index["weight_map"].values()).issubset(receipts):
        raise RuntimeError("Unverified model shard in index")
    sae_path = Path(hf_hub_download(
        SAE_ID, SAE_FILENAME, revision=SAE_REVISION, cache_dir=str(cache_dir)))
    _hash_file(sae_path, SAE_FILE_SHA256, "sha256")
    return snapshot, sae_path, {"model_id": MODEL_ID, "model_revision": MODEL_REVISION,
                              "model_artifacts": receipts, "sae_id": SAE_ID,
                              "sae_revision": SAE_REVISION, "sae_sha256": SAE_FILE_SHA256}


def _state_value(state: Mapping[str, torch.Tensor], key: str) -> torch.Tensor:
    matches = [value for name, value in state.items() if name == key or name.endswith("." + key)]
    if len(matches) != 1:
        raise ValueError(f"Missing or ambiguous SAE tensor {key}")
    return matches[0]


class ModelBackend:
    """Serial-use backend. No batching, padding, truncation, or automatic offload.

    generate returns sampled IDs including EOS; cap_hit means the token limit
    was reached without EOS. The terminal sampled token gets an additional
    cached diagnostic forward, marked terminal_observation_only, so telemetry
    covers it too. Special tokens have token_class='special' and retain origin
    ('prompt' or 'generated'). Temperature 0 is greedy; sampling uses a private
    seeded torch.Generator with top_p=1 and no top_k/repetition processors.

    teacher tokenizes raw text with special tokens, not a chat template. NLL
    and KL arrays align to target token IDs: element 0 is None (no predecessor).
    KL is KL(clean || edited) on identical teacher-forced prefixes, never a
    comparison of separately sampled generations. Full-SAE diagnostics are
    optional and reconstruction-only NLL is separate from edited NLL.

    telemetry schema v1: selected_activations contains four [position, feature]
    matrices (before, requested_delta, requested_activation, after), ordered by
    feature_ids. position_metadata is separate; delivery contains parallel
    per-position scalar arrays. full_sae is null unless explicitly collected.
    Candidate calibration can consume selected_activations.before directly;
    positive quantiles in activation_summaries are per text, not pooled q90.
    """

    def __init__(self, precision: str = "bf16", cache_dir: str | Path | None = None,
                 device: str = "cuda"):
        if precision not in ("bf16", "nf4"):
            raise ValueError("precision must be bf16 or nf4")
        if cache_dir is None:
            raise ValueError("An explicit cache_dir is required")
        target = torch.device(device)
        if target.type != "cuda" or not torch.cuda.is_available():
            raise RuntimeError("Production backend requires one CUDA GPU; no offload")
        target = torch.device("cuda", target.index if target.index is not None else torch.cuda.current_device())
        with torch.cuda.device(target):
            if not torch.cuda.is_bf16_supported():
                raise RuntimeError("Native BF16 support is required")
        from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig

        snapshot, sae_path, metadata = _load_artifacts(cache_dir)
        tokenizer = AutoTokenizer.from_pretrained(snapshot, local_files_only=True,
                                                  trust_remote_code=False)
        kwargs = dict(local_files_only=True, trust_remote_code=False,
                      torch_dtype=torch.bfloat16, device_map={"": str(target)},
                      low_cpu_mem_usage=True, attn_implementation="sdpa")
        if precision == "nf4":
            kwargs["quantization_config"] = BitsAndBytesConfig(
                load_in_4bit=True, bnb_4bit_quant_type="nf4",
                bnb_4bit_use_double_quant=True, bnb_4bit_compute_dtype=torch.bfloat16)
        model = AutoModelForCausalLM.from_pretrained(snapshot, **kwargs)
        if (model.config.model_type != "llama" or model.config.hidden_size != 8192
                or model.config.num_hidden_layers != 80 or len(tokenizer) != 128256):
            raise RuntimeError("Unexpected pinned Llama architecture/tokenizer")
        state = torch.load(sae_path, weights_only=True, map_location="cpu", mmap=True)
        self._initialize(model, tokenizer, state, LAYER_INDEX, target, metadata, precision)
        if self._sae[0].shape != (65536, 8192):
            self.close()
            raise RuntimeError("Unexpected pinned SAE dimensions")

    @classmethod
    def from_components_for_test(cls, model: Any, tokenizer: Any,
                                 sae_state: Mapping[str, torch.Tensor], *,
                                 layer_index: int = 0, default_feature_ids: Sequence[int] = (0,)):
        """Offline injection for random tiny models; prominently marked non-production."""
        self = cls.__new__(cls)
        device = next(model.parameters()).device
        self._initialize(model, tokenizer, sae_state, layer_index, device,
                         {"test_only": True}, "test")
        self.default_feature_ids = _ids(default_feature_ids, self._sae[0].shape[0])
        return self

    def _initialize(self, model, tokenizer, state, layer_index, device, metadata, precision):
        self.model = model.eval()
        self.tokenizer = tokenizer
        self.device = device
        self.precision = precision
        self.layer_index = layer_index
        self._closed = False
        self._selection = None
        self._sae = tuple(_state_value(state, key).detach().to("cpu") for key in SAE_KEYS)
        encoder, bias, decoder, decoder_bias = self._sae
        if (encoder.ndim != 2 or encoder.shape[1] != model.config.hidden_size
                or bias.shape != (encoder.shape[0],)
                or decoder.shape != (encoder.shape[1], encoder.shape[0])
                or decoder_bias.shape != (encoder.shape[1],)):
            raise ValueError("Invalid SAE tensor dimensions")
        for name, tensor in zip(SAE_KEYS, self._sae):
            _finite_chunks(name, tensor)
        self._layer = model.get_submodule(f"model.layers.{layer_index}")
        self._assert_resident()
        for name, value in model.named_parameters():
            if value.is_floating_point():
                _finite_chunks(name, value)
        self.dtype = model.get_input_embeddings().weight.dtype
        if precision != "test" and self.dtype != torch.bfloat16:
            raise RuntimeError("Residual computation must be native BF16")
        self.default_feature_ids = TARGET_IDS
        self.metadata = dict(metadata, precision=precision, dtype=str(self.dtype),
                             hook=f"model.layers.{layer_index}.output",
                             encoding_note=ENCODING_NOTE,
                             torch_version=torch.__version__)
        template = getattr(tokenizer, "chat_template", None)
        if template is not None:
            self.metadata["chat_template_sha256"] = hashlib.sha256(
                (template if isinstance(template, str) else json.dumps(template, sort_keys=True)).encode()).hexdigest()

    def _assert_resident(self):
        if self._closed:
            raise RuntimeError("Backend is closed")
        for value in getattr(self.model, "hf_device_map", {}).values():
            if isinstance(value, int):
                value = torch.device("cuda", value)
            if str(value) in ("disk", "meta") or torch.device(value) != self.device:
                raise RuntimeError("Model offload or multiple devices are forbidden")
        for name, tensor in list(self.model.named_parameters()) + list(self.model.named_buffers()):
            if tensor.device != self.device:
                raise RuntimeError(f"Model offload/device mismatch at {name}")
        for module in self.model.modules():
            hook = getattr(module, "_hf_hook", None)
            if getattr(hook, "offload", False):
                raise RuntimeError("Offload hooks are forbidden")

    def _selected(self, feature_ids):
        ids = _ids(feature_ids, self._sae[0].shape[0])
        if self._selection is None or self._selection[0] != ids:
            index = torch.tensor(ids, dtype=torch.long)
            e, b, d, _ = self._sae
            self._selection = (ids, tuple(t.to(self.device, self.dtype) for t in (
                e.index_select(0, index), b.index_select(0, index), d.index_select(1, index))))
        return ids, self._selection[1]

    def _intervention(self, feature_ids, intervention):
        ids, selected = self._selected(feature_ids)
        if intervention is None:
            return ids, selected, {"mode": None, "strength": 0.0}
        if set(intervention) - {"feature_ids", "mode", "strength", "q90"}:
            raise ValueError("Unknown intervention fields")
        if tuple(intervention["feature_ids"]) != ids:
            raise ValueError("Teacher feature_ids must exactly match ordered intervention IDs")
        mode, strength = intervention["mode"], intervention["strength"]
        if mode not in ("suppression", "amplification") or isinstance(strength, bool) or strength not in (0, .5, 1):
            raise ValueError("Invalid mode/strength")
        return ids, selected, {"mode": mode, "strength": strength, "q90": intervention.get("q90")}

    def _tokenize(self, text: str) -> torch.Tensor:
        encoded = self.tokenizer(text, add_special_tokens=True, return_tensors="pt")
        ids = encoded["input_ids"]
        if "attention_mask" in encoded and not bool(encoded["attention_mask"].all()):
            raise ValueError("Padding is not supported")
        return self._validate_tokens(ids)

    def _validate_tokens(self, ids):
        if ids.ndim != 2 or ids.shape[0] != 1 or ids.shape[1] == 0:
            raise ValueError("Exactly one nonempty unpadded sequence is required")
        if ids.shape[1] > self.model.config.max_position_embeddings:
            raise ValueError("Context limit exceeded; truncation is forbidden")
        return ids.to(self.device)

    @contextmanager
    def _full_sae(self, enabled):
        weights = tuple(t.to(self.device, self.dtype) for t in self._sae) if enabled else None
        try:
            yield weights
        finally:
            del weights

    def _full_diagnostic(self, hidden, edited, weights, feature_ids):
        e, b, d, db = weights
        flat, changed = hidden.reshape(-1, hidden.shape[-1]), edited.reshape(-1, edited.shape[-1])
        chunks, recons = [], []
        non_target = torch.ones(e.shape[0], dtype=torch.bool, device=self.device)
        non_target[list(feature_ids)] = False
        for start in range(0, len(flat), 32):
            h, hp = flat[start:start + 32], changed[start:start + 32]
            z = F.relu(F.linear(h, e, b))
            zp = F.relu(F.linear(hp, e, b))
            recon = F.linear(z, d, db)
            for name, value in (("full SAE", z), ("full SAE after", zp), ("reconstruction", recon)):
                _finite(name, value)
            difference = (zp.float() - z.float())[:, non_target]
            error = torch.linalg.vector_norm(recon.float() - h.float(), dim=-1)
            norm = torch.linalg.vector_norm(h.float(), dim=-1)
            chunks.append({"l0_before": (z > 0).sum(-1), "l0_after": (zp > 0).sum(-1),
                           "reconstruction_error_norm": error,
                           "reconstruction_relative_error": error / norm.clamp_min(1e-30),
                           "non_target_change_norm": torch.linalg.vector_norm(difference, dim=-1),
                           "non_target_changed_count": (difference != 0).sum(-1),
                           "full_selected_before": z[:, list(feature_ids)].float(),
                           "full_selected_after": zp[:, list(feature_ids)].float()})
            recons.append(recon)
        metrics = {key: torch.cat([part[key] for part in chunks]) for key in chunks[0]}
        return torch.cat(recons).reshape_as(hidden), metrics

    @torch.inference_mode()
    def _forward(self, token_ids, feature_ids, intervention=None, *, offset=0,
                 prompt_length=None, past=None, use_cache=False, full=None, reconstruct=False):
        self._assert_resident()
        ids, selected, edit_args = self._intervention(feature_ids, intervention)
        records = {}
        calls = 0
        prompt_length = token_ids.shape[1] if prompt_length is None else prompt_length
        token_list = token_ids[0].tolist()
        specials = set(self.tokenizer.all_special_ids)

        def hook(_module, _inputs, output):
            nonlocal calls
            calls += 1
            if calls != 1:
                raise RuntimeError("Layer hook fired more than once per forward")
            hidden = output[0] if isinstance(output, tuple) else output
            if hidden.shape[:2] != token_ids.shape or hidden.dtype != self.dtype:
                raise RuntimeError("Unexpected hook shape/dtype or cache position")
            edited, metrics = edit_hidden(hidden, *selected, **edit_args)
            diagnostic = None
            if full is not None:
                recon, diagnostic = self._full_diagnostic(hidden, edited, full, ids)
                if reconstruct:
                    edited = recon
                else:
                    for when in ("before", "after"):
                        diagnostic[f"selected_full_{when}_max_abs_difference"] = (
                            metrics[when][0] - diagnostic[f"full_selected_{when}"]).abs().amax(-1)
            cpu = {key: value[0].cpu().tolist() for key, value in metrics.items()}
            records["selected_activations"] = {key: cpu.pop(key) for key in ACTIVATION_COLUMNS}
            records["delivery"] = cpu
            records["full_sae"] = ({key: value.cpu().tolist() for key, value in diagnostic.items()}
                                   if diagnostic is not None else None)
            records["position_metadata"] = []
            for i, token in enumerate(token_list):
                origin = "prompt" if offset + i < prompt_length else "generated"
                records["position_metadata"].append(dict(
                    position=offset + i, token_id=token, origin=origin,
                    token_class="special" if token in specials else origin,
                    terminal_observation_only=False))
            if edited is hidden:
                return output
            return (edited,) + output[1:] if isinstance(output, tuple) else edited

        handle = self._layer.register_forward_hook(hook)
        try:
            result = self.model.model(
                input_ids=token_ids, attention_mask=torch.ones((1, offset + len(token_list)),
                dtype=torch.long, device=self.device), past_key_values=past,
                use_cache=use_cache, return_dict=True)
        finally:
            handle.remove()
        if calls != 1:
            raise RuntimeError("Expected layer hook was not called")
        _finite("final hidden states", result.last_hidden_state)
        return result, records

    def _telemetry(self, ids, batches, intervention=None):
        result = {"schema_version": TELEMETRY_SCHEMA, "feature_ids": list(ids),
                "position_metadata": [p for b in batches for p in b["position_metadata"]],
                "hook_removed": True, "hook_layer": f"model.layers.{self.layer_index}.output",
                "encoding_note": ENCODING_NOTE, "native_dtype": str(self.dtype),
                "diagnostics_dtype": "torch.float32", "padding": "none",
                "edit_arithmetic": "FP32 h + W_D delta, one cast to native hidden dtype",
                "selected_encode_shapes": [[len(b["position_metadata"]), len(ids),
                                            self._sae[0].shape[1]] for b in batches],
                "selected_full_max_abs_tolerance": SELECTED_FULL_MAX_ABS_TOLERANCE,
                "selected_full_tolerance_status": "proposed_unvalidated_diagnostic",
                "q90": (list(intervention["q90"]) if intervention is not None
                        and intervention["mode"] == "amplification" else None),
                "q90_source_encoding_verified": False,
                "full_sae": None, "selected_full_check_passed": None}
        for section in ("selected_activations", "delivery"):
            result[section] = {key: [v for b in batches for v in b[section][key]]
                               for key in batches[0][section]}
        if batches[0]["full_sae"] is not None:
            result["full_sae"] = {key: [v for b in batches for v in b["full_sae"][key]]
                                  for key in batches[0]["full_sae"]}
            drift = max(v for when in ("before", "after") for v in
                        result["full_sae"][f"selected_full_{when}_max_abs_difference"])
            result["selected_full_check_passed"] = drift <= SELECTED_FULL_MAX_ABS_TOLERANCE
            result["full_encode_shape"] = [min(32, len(result["position_metadata"])),
                                           self._sae[0].shape[0], self._sae[0].shape[1]]
            result["full_encode_shapes"] = [
                [min(32, len(result["position_metadata"]) - start),
                 self._sae[0].shape[0], self._sae[0].shape[1]]
                for start in range(0, len(result["position_metadata"]), 32)]
        return result

    @staticmethod
    def _summaries(ids, records):
        result = []
        for column, feature in enumerate(ids):
            row = {"feature_id": feature}
            for key in ("before", "after"):
                values = torch.tensor(records["selected_activations"][key], dtype=torch.float32)[:, column]
                active = values[values > 0]
                row[key] = {"count": len(values), "active_count": len(active),
                            "frequency": len(active) / len(values), "mean": values.mean().item(),
                            "max": values.max().item(),
                            "positive_q50": torch.quantile(active, .5).item() if len(active) else None,
                            "positive_q90": torch.quantile(active, .9).item() if len(active) else None}
            result.append(row)
        return result

    @torch.inference_mode()
    def generate(self, messages, seed, temperature, max_new_tokens=256, intervention=None):
        started = time.perf_counter()
        self._assert_resident()
        if type(seed) is not int or seed < 0 or seed >= 2**63:
            raise ValueError("seed must be an integer in [0, 2**63)")
        if not math.isfinite(temperature) or temperature < 0:
            raise ValueError("temperature must be finite and nonnegative")
        if type(max_new_tokens) is not int or not 1 <= max_new_tokens <= 256:
            raise ValueError("max_new_tokens must be between 1 and 256")
        rendered = self.tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        prompt = self.tokenizer.apply_chat_template(messages, tokenize=True,
                                                    add_generation_prompt=True, return_tensors="pt")
        prompt = self._validate_tokens(prompt)
        n = prompt.shape[1]
        if n + max_new_tokens > self.model.config.max_position_embeddings:
            raise ValueError("Prompt plus generation cap exceeds context limit")
        feature_ids = self.default_feature_ids if intervention is None else intervention["feature_ids"]
        eos = self.model.generation_config.eos_token_id
        eos = set(eos if isinstance(eos, (list, tuple)) else [eos]) - {None}
        if self.tokenizer.eos_token_id is not None:
            eos.add(self.tokenizer.eos_token_id)
        generator = torch.Generator(device=self.device).manual_seed(seed)
        result, records = self._forward(prompt, feature_ids, intervention,
                                        use_cache=True, prompt_length=n)
        batches = [records]
        sampled = []
        for _ in range(max_new_tokens):
            logits = self.model.get_output_embeddings()(result.last_hidden_state[:, -1]).float()
            _finite("generation logits", logits)
            if temperature == 0:
                token = logits.argmax(-1).item()
            else:
                probabilities = torch.softmax(logits / temperature, dim=-1)
                _finite("sampling probabilities", probabilities)
                token = torch.multinomial(probabilities, 1, generator=generator).item()
            sampled.append(token)
            result, new_records = self._forward(
                torch.tensor([[token]], device=self.device), feature_ids, intervention,
                offset=n + len(sampled) - 1, prompt_length=n, past=result.past_key_values,
                use_cache=True)
            batches.append(new_records)
            if token in eos:
                break
        batches[-1]["position_metadata"][-1]["terminal_observation_only"] = True
        return {"response": self.tokenizer.decode(sampled, skip_special_tokens=True),
                "input_tokens": n, "output_tokens": len(sampled),
                "cap_hit": len(sampled) == max_new_tokens and sampled[-1] not in eos,
                "input_token_ids": prompt[0].tolist(), "output_token_ids": sampled,
                "rendered_input_sha256": hashlib.sha256(rendered.encode()).hexdigest(),
                "input_token_ids_sha256": hashlib.sha256(json.dumps(prompt[0].tolist()).encode()).hexdigest(),
                "telemetry": self._telemetry(feature_ids, batches, intervention),
                "elapsed_seconds": time.perf_counter() - started}

    def _losses(self, clean, edited, tokens):
        clean_nll, edited_nll, kl = [None], [None], [None]
        head = self.model.get_output_embeddings()
        for start in range(0, tokens.shape[1] - 1, 16):
            end = min(start + 16, tokens.shape[1] - 1)
            clean_logits = head(clean[:, start:end]).float()
            edited_logits = head(edited[:, start:end]).float()
            _finite("clean logits", clean_logits)
            _finite("edited logits", edited_logits)
            p = F.log_softmax(clean_logits, dim=-1)
            q = F.log_softmax(edited_logits, dim=-1)
            targets = tokens[:, start + 1:end + 1, None]
            cn = -p.gather(-1, targets).squeeze(-1)
            en = -q.gather(-1, targets).squeeze(-1)
            divergence = (p.exp() * (p - q)).sum(-1)
            for name, values in (("clean NLL", cn), ("edited NLL", en), ("KL", divergence)):
                _finite(name, values)
            clean_nll.extend(cn[0].tolist())
            edited_nll.extend(en[0].tolist())
            # Keep FP32 roundoff (possibly tiny negative KL) visible, not clipped.
            kl.extend(divergence[0].tolist())
        return clean_nll, edited_nll, kl

    @torch.inference_mode()
    def teacher(self, text, feature_ids, intervention=None, collect_reconstruction=False):
        started = time.perf_counter()
        self._assert_resident()
        tokens = self._tokenize(text)
        ids, _, _ = self._intervention(feature_ids, intervention)
        clean, clean_records = self._forward(tokens, ids)
        with self._full_sae(collect_reconstruction) as full:
            if intervention is None and full is None:
                edited, records = clean, clean_records
            else:
                edited, records = self._forward(tokens, ids, intervention, full=full)
            unsteered_nll, edited_nll, kl = self._losses(
                clean.last_hidden_state, edited.last_hidden_state, tokens)
            del edited
            reconstruction_nll = None
            if collect_reconstruction:
                reconstructed, _ = self._forward(tokens, ids, full=full, reconstruct=True)
                _, reconstruction_nll, _ = self._losses(
                    clean.last_hidden_state, reconstructed.last_hidden_state, tokens)
        return {"token_ids": tokens[0].tolist(), "input_tokens": tokens.shape[1],
                "unsteered_nll": unsteered_nll, "edited_nll": edited_nll,
                "kl_clean_to_edited": kl, "reconstruction_nll": reconstruction_nll,
                "loss_alignment": "index i predicts token_ids[i] from prefix [:i]; index 0 is null",
                "telemetry": self._telemetry(ids, [records], intervention),
                "clean_telemetry": self._telemetry(ids, [clean_records]),
                "activation_summaries": self._summaries(ids, records),
                "full_sae_diagnostics": bool(collect_reconstruction),
                "elapsed_seconds": time.perf_counter() - started}

    @torch.inference_mode()
    def feature_metadata(self, feature_ids, target_ids=TARGET_IDS):
        self._assert_resident()
        ids = _ids(feature_ids, self._sae[0].shape[0])
        targets = _ids(target_ids, self._sae[0].shape[0])
        decoder = self._sae[2]
        reference = decoder[:, list(targets)].to(self.dtype).float()
        norms = torch.linalg.vector_norm(reference, dim=0)
        if bool((norms == 0).any()):
            raise ValueError("Zero target decoder norm")
        unit = reference / norms
        rows = []
        for start in range(0, len(ids), 128):
            vectors = decoder[:, list(ids[start:start + 128])].to(self.dtype).float()
            vector_norms = torch.linalg.vector_norm(vectors, dim=0)
            if bool((vector_norms == 0).any()):
                raise ValueError("Zero candidate decoder norm")
            cosines = (vectors / vector_norms).T @ unit
            _finite("decoder cosines", cosines)
            for feature, norm, cosine in zip(ids[start:start + 128], vector_norms, cosines):
                rows.append({"feature_id": feature, "decoder_norm": norm.item(),
                             "target_cosines": cosine.tolist(),
                             "max_target_cosine": cosine.max().item(),
                             "max_abs_target_cosine": cosine.abs().max().item()})
        return {"feature_ids": list(ids), "target_ids": list(targets), "features": rows}

    def close(self):
        """Idempotently release this backend's references, including CPU SAE storage."""
        self._closed = True
        self._selection = None
        self._sae = ()
        self._layer = None
        self.model = None
        self.tokenizer = None
        gc.collect()
        if self.device.type == "cuda":
            with torch.cuda.device(self.device):
                torch.cuda.empty_cache()

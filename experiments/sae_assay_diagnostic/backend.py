"""Pinned, single-GPU computation for the assay diagnostic, without orchestration.

The authoritative SAE encoder is ReLU(F.linear(h, W_E, b_E)), without b_D
subtraction, in native BF16, one position at a time: [1,8192] -> [1,65536].
Calibration, matching, prefill, teacher forcing and cached generation all use
this full-width calculation, then select columns. Candidate/panel membership
never changes the encoder GEMM. Full weights remain on the GPU. Selected-row
encoding is an optional qualification observation, never a fallback or gate.

The requested decoder product and residual addition are FP32, followed by one
cast to the hidden state's native dtype (BF16 in production). Delivery metrics
compare that request to edited.float() - hidden.float(), retaining rounding.
collect_reconstruction=True adds full-SAE sparsity/reconstruction diagnostics,
selected-path observations and a separate reconstruction-only loss forward.
It also adds FP32 re-encoding references using selected BF16 encoder weights
promoted to FP32: clean h, ideal h+request, and actual rounded h'. These are
geometry/rounding diagnostics, not alternative production activations.
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
ENCODING_AUTHORITY = "full_native_token1_v1"
ENCODING_NOTE = "Full native encoder, fixed one-position GEMM; select columns only afterward"
TELEMETRY_SCHEMA = "sae_assay_backend_v2"
WORKSPACE_RESERVE_BYTES = 6 * 1024**3
ACTIVATION_COLUMNS = ("before", "requested_delta", "requested_activation", "after")
REFERENCE_COLUMNS = ("ideal_fp32_before", "ideal_fp32_after", "actual_fp32_after")
SAE_KEYS = ("encoder_linear.weight", "encoder_linear.bias",
            "decoder_linear.weight", "decoder_linear.bias")


def estimate_memory_requirements(precision: str) -> dict[str, int]:
    """Conservative residency estimate, not a measured allocator guarantee.

    NF4 uses .75 bytes/parameter as an allowance for quantization metadata and
    unquantized tensors. Both modes reserve 6 GiB beyond model and full SAE;
    actual model residency and per-request sequence/KV estimates are checked
    again. OOM is an error, never permission for an offload/precision fallback.
    """
    if precision not in ("bf16", "nf4"):
        raise ValueError("precision must be bf16 or nf4")
    model = math.ceil(70_553_706_496 * (2 if precision == "bf16" else .75))
    sae = (2 * 8192 * 65536 + 8192 + 65536) * 2
    return {"model_bytes": model, "sae_bytes": sae,
            "workspace_reserve_bytes": WORKSPACE_RESERVE_BYTES,
            "required_bytes": model + sae + WORKSPACE_RESERVE_BYTES}


def _require_cuda_memory(device, required_bytes):
    free, total = torch.cuda.mem_get_info(device)
    if free < required_bytes:
        raise RuntimeError(f"Insufficient GPU memory: need {required_bytes} free bytes, have {free}; no offload")
    return {"free_bytes": free, "total_bytes": total, "required_bytes": required_bytes}


def _check_runtime_versions(torch_version, cuda_version, transformers_version):
    if (torch_version.split("+")[0] != "2.8.0" or cuda_version != "12.8"
            or transformers_version != "4.47.1"):
        raise RuntimeError("Production runtime requires torch 2.8.0/cu128 and transformers 4.47.1")
    return {"torch_version": torch_version, "cuda_version": cuda_version,
            "transformers_version": transformers_version}


@contextmanager
def _fp32_math(device):
    previous = torch.backends.cuda.matmul.allow_tf32
    try:
        torch.backends.cuda.matmul.allow_tf32 = False
        with torch.autocast(device_type=device.type, enabled=False):
            yield
    finally:
        torch.backends.cuda.matmul.allow_tf32 = previous


def _linear_token1(values, weight, bias=None):
    flat = values.reshape(-1, values.shape[-1])
    return torch.cat([F.linear(row[None], weight, bias) for row in flat]).reshape(
        *values.shape[:-1], weight.shape[0])


def _canonical_encode(hidden, encoder, bias, index):
    # Select after the fixed full-width operation; never retain [positions,65536].
    rows = []
    with torch.autocast(device_type=hidden.device.type, enabled=False):
        for row in hidden.reshape(-1, hidden.shape[-1]):
            full = F.relu(F.linear(row[None], encoder, bias))
            _finite("canonical full activations", full)
            rows.append(full.index_select(1, index))
    return torch.cat(rows).reshape(*hidden.shape[:-1], len(index))


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
    feature_ids: Sequence[int] | None = None,
    collect_reference: bool = False,
    _validated_weights: bool = False,
) -> tuple[torch.Tensor, dict[str, torch.Tensor]]:
    """Edit selected coordinates using FULL weights [W,H], [W], [H,W].

    Returns the original tensor object for true zero. Masked positions stay
    unchanged. Zero-request cosine is 1 by convention; a nonzero request lost
    to rounding has cosine 0 and relative error 1, never a missing observation.
    The FP32 residual request is added in FP32, then cast exactly once to the
    native hidden dtype. All diagnostics are FP32 except boolean indicators.
    strength=0 is an explicit zero arm; nonzero strengths are only .5 and 1.
    """
    if hidden.ndim < 2 or not hidden.is_floating_point():
        raise ValueError("hidden must be a floating tensor with position and width axes")
    full_width, width = encoder_weight.shape
    if (hidden.shape[-1] != width or tuple(encoder_bias.shape) != (full_width,)
            or tuple(decoder_weight.shape) != (width, full_width) or full_width == 0):
        raise ValueError("Incompatible full SAE shapes")
    ids = tuple(range(full_width)) if feature_ids is None else _ids(feature_ids, full_width)
    index = torch.tensor(ids, dtype=torch.long, device=hidden.device)
    k = len(ids)
    for name, value in (("hidden", hidden), ("encoder", encoder_weight),
                        ("encoder bias", encoder_bias), ("decoder", decoder_weight)):
        if value.device != hidden.device or value.dtype != hidden.dtype:
            raise ValueError("SAE and hidden must share device and native dtype")
        if name == "hidden" or not _validated_weights:
            _finite_chunks(name, value)
    if isinstance(strength, bool) or strength not in (0.0, 0.5, 1.0):
        raise ValueError("strength must be 0, .5, or 1")
    if mode not in (None, "suppression", "amplification") or (mode is None and strength):
        raise ValueError("Invalid intervention mode")
    mask = torch.ones(hidden.shape[:-1], dtype=torch.bool, device=hidden.device)
    if valid_mask is not None:
        if valid_mask.shape != mask.shape or valid_mask.dtype != torch.bool:
            raise ValueError("valid_mask must be boolean and match position axes")
        mask = valid_mask.to(hidden.device)
    before = _canonical_encode(hidden, encoder_weight, encoder_bias, index)
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
    selected_decoder = decoder_weight.index_select(1, index).float()
    with _fp32_math(hidden.device):
        requested = _linear_token1(delta, selected_decoder)
    _finite("requested residual edit", requested)
    zero = not bool(torch.count_nonzero(delta))
    if zero:
        edited, after = hidden, before
    else:
        edited = torch.where(mask.unsqueeze(-1),
                             (hidden.float() + requested).to(hidden.dtype), hidden)
        _finite("edited hidden", edited)
        after = _canonical_encode(edited, encoder_weight, encoder_bias, index)
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
    if collect_reference:
        e = encoder_weight.index_select(0, index).float()
        bias = encoder_bias.index_select(0, index).float()
        with _fp32_math(hidden.device):
            for key, state in zip(REFERENCE_COLUMNS, (
                    hidden.float(), hidden.float() + requested, edited.float())):
                telemetry[key] = F.relu(_linear_token1(state, e, bias))
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

    telemetry schema v2: selected_activations contains four [position, feature]
    matrices (before, requested_delta, requested_activation, after), ordered by
    feature_ids. position_metadata is separate; delivery contains parallel
    per-position scalar arrays. full_sae is null unless explicitly collected.
    These are columns of the canonical full-width, one-position encoder.
    full_sae includes selected_path_before/after plus the three FP32 reference
    matrices only when collect_reconstruction=True. No numerical pass gate is
    applied here; the parent compares consequential decisions on qualification.
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
        estimate = estimate_memory_requirements(precision)
        memory = _require_cuda_memory(target, estimate["required_bytes"])
        import transformers
        from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig

        runtime = _check_runtime_versions(torch.__version__, torch.version.cuda, transformers.__version__)
        snapshot, sae_path, metadata = _load_artifacts(cache_dir)
        metadata.update(runtime)
        metadata["preload_memory"] = dict(memory, estimate=estimate)
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
        self._sae = ()
        weights = tuple(_state_value(state, key).detach() for key in SAE_KEYS)
        encoder, bias, decoder, decoder_bias = weights
        if (encoder.ndim != 2 or encoder.shape[1] != model.config.hidden_size
                or bias.shape != (encoder.shape[0],)
                or decoder.shape != (encoder.shape[1], encoder.shape[0])
                or decoder_bias.shape != (encoder.shape[1],)):
            raise ValueError("Invalid SAE tensor dimensions")
        for name, tensor in zip(SAE_KEYS, weights):
            _finite_chunks(name, tensor)
        self._layer = model.get_submodule(f"model.layers.{layer_index}")
        self._assert_resident()
        for name, value in model.named_parameters():
            if value.is_floating_point():
                _finite_chunks(name, value)
        self.dtype = model.get_input_embeddings().weight.dtype
        if precision != "test" and self.dtype != torch.bfloat16:
            raise RuntimeError("Residual computation must be native BF16")
        memory = None
        if device.type == "cuda":
            sae_bytes = sum(t.numel() for t in weights) * torch.empty((), dtype=self.dtype).element_size()
            memory = _require_cuda_memory(device, sae_bytes + WORKSPACE_RESERVE_BYTES)
        self._sae = tuple(t.to(device=device, dtype=self.dtype).contiguous() for t in weights)
        for name, tensor in zip(SAE_KEYS, self._sae):
            _finite_chunks(name, tensor)
        self._assert_resident()
        self.default_feature_ids = TARGET_IDS
        self.metadata = dict(metadata, precision=precision, dtype=str(self.dtype),
                             hook=f"model.layers.{layer_index}.output",
                             encoding_note=ENCODING_NOTE,
                             encoding_authority=ENCODING_AUTHORITY,
                             full_sae_resident_bytes=sum(t.numel() * t.element_size() for t in self._sae),
                             sae_memory_preflight=memory,
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
        for tensor in self._sae:
            if tensor.device != self.device or tensor.dtype != self.dtype:
                raise RuntimeError("Full SAE offload/dtype mismatch")

    def _request_memory(self, token_count, use_cache):
        if self.device.type == "cuda":
            config = self.model.config
            item_size = torch.empty((), dtype=self.dtype).element_size()
            retained = token_count * config.hidden_size * item_size * 8
            kv = (2 * config.num_hidden_layers * config.num_key_value_heads
                  * (config.hidden_size // config.num_attention_heads) * item_size * token_count)
            _require_cuda_memory(self.device, WORKSPACE_RESERVE_BYTES + retained + (kv if use_cache else 0))

    def _intervention(self, feature_ids, intervention):
        ids = _ids(feature_ids, self._sae[0].shape[0])
        if intervention is None:
            return ids, {"mode": None, "strength": 0.0}
        if set(intervention) - {"feature_ids", "mode", "strength", "q90"}:
            raise ValueError("Unknown intervention fields")
        if tuple(intervention["feature_ids"]) != ids:
            raise ValueError("Teacher feature_ids must exactly match ordered intervention IDs")
        mode, strength = intervention["mode"], intervention["strength"]
        if mode not in ("suppression", "amplification") or isinstance(strength, bool) or strength not in (0, .5, 1):
            raise ValueError("Invalid mode/strength")
        return ids, {"mode": mode, "strength": strength, "q90": intervention.get("q90")}

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
        if ids.dtype != torch.long or bool(((ids < 0) | (ids >= self.model.config.vocab_size)).any()):
            raise ValueError("Token IDs must be in-vocabulary int64 values")
        return ids.to(self.device)

    def _full_diagnostic(self, hidden, edited, feature_ids):
        e, b, d, db = self._sae
        flat, changed = hidden.reshape(-1, hidden.shape[-1]), edited.reshape(-1, edited.shape[-1])
        chunks, recons = [], []
        non_target = torch.ones(e.shape[0], dtype=torch.bool, device=self.device)
        non_target[list(feature_ids)] = False
        for start in range(len(flat)):
            h, hp = flat[start:start + 1], changed[start:start + 1]
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
        # Reproduce the old selected-width, batched path only as an observation.
        for key, value in (("selected_path_before", flat), ("selected_path_after", changed)):
            metrics[key] = F.relu(F.linear(value, e[list(feature_ids)], b[list(feature_ids)])).float()
        for key, value in metrics.items():
            _finite(key, value)
        return torch.cat(recons).reshape_as(hidden), metrics

    @torch.inference_mode()
    def _forward(self, token_ids, feature_ids, intervention=None, *, offset=0,
                 prompt_length=None, past=None, use_cache=False, collect_reconstruction=False, reconstruct=False):
        self._assert_resident()
        ids, edit_args = self._intervention(feature_ids, intervention)
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
            edited, metrics = edit_hidden(hidden, *self._sae[:3], feature_ids=ids,
                                          collect_reference=collect_reconstruction,
                                          _validated_weights=True, **edit_args)
            diagnostic = None
            if collect_reconstruction or reconstruct:
                recon, diagnostic = self._full_diagnostic(hidden, edited, ids)
                if reconstruct:
                    edited = recon
                else:
                    diagnostic.update({key: metrics.pop(key)[0] for key in REFERENCE_COLUMNS})
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
                "encoding_authority": ENCODING_AUTHORITY,
                "full_encode_shape": [1, self._sae[0].shape[0], self._sae[0].shape[1]],
                "diagnostics_dtype": "torch.float32", "padding": "none",
                "edit_arithmetic": "FP32 h + W_D delta, one cast to native hidden dtype",
                "selected_encode_shapes": [[len(b["position_metadata"]), len(ids),
                                            self._sae[0].shape[1]] for b in batches if b["full_sae"] is not None],
                "q90": (torch.as_tensor(intervention["q90"]).float().cpu().tolist() if intervention is not None
                        and intervention["mode"] == "amplification" else None),
                "required_q90_encoding_authority": ENCODING_AUTHORITY,
                "q90_source_encoding_verified": False,
                "fp32_reference_note": "Diagnostic only: selected native encoder weights promoted to FP32, token1; ideal h+request versus actual rounded h",
                "full_sae": None}
        for section in ("selected_activations", "delivery"):
            result[section] = {key: [v for b in batches for v in b[section][key]]
                               for key in batches[0][section]}
        if batches[0]["full_sae"] is not None:
            result["full_sae"] = {key: [v for b in batches for v in b["full_sae"][key]]
                                  for key in batches[0]["full_sae"]}
        return result

    @staticmethod
    def _summaries(ids, records):
        result = []
        matrices = {key: torch.tensor(records["selected_activations"][key], dtype=torch.float32)
                    for key in ("before", "after")}
        for column, feature in enumerate(ids):
            row = {"feature_id": feature}
            for key in ("before", "after"):
                values = matrices[key][:, column]
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
        self._request_memory(n + max_new_tokens, use_cache=True)
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
        return self._evaluate_tokens(tokens, tokens.shape[1], feature_ids, intervention,
                                     collect_reconstruction, False, started)

    @torch.inference_mode()
    def replay_tokens(self, input_token_ids, output_token_ids, feature_ids,
                      intervention=None, collect_reconstruction=False):
        """Replay exact IDs with original prefill then cached single-token schedule.

        No tokenizer call, string roundtrip, EOS filtering or padding removal.
        Loss index i predicts recorded token i from the same prefix under each
        arm. The last output token is observed but does not predict a recorded
        successor, matching generate's terminal_observation_only convention.
        """
        started = time.perf_counter()
        self._assert_resident()
        parts = []
        for values, allow_empty in ((input_token_ids, False), (output_token_ids, True)):
            if isinstance(values, torch.Tensor):
                if values.ndim != 1 or values.dtype != torch.long:
                    raise ValueError("Replay IDs must be one-dimensional int64")
                values = values.tolist()
            values = list(values)
            if (not values and not allow_empty) or any(type(i) is not int for i in values):
                raise ValueError("Replay IDs must be integers with a nonempty prompt")
            parts.append(values)
        tokens = self._validate_tokens(torch.tensor([parts[0] + parts[1]], dtype=torch.long))
        return self._evaluate_tokens(tokens, len(parts[0]), feature_ids, intervention,
                                     collect_reconstruction, True, started)

    def _token_forward(self, tokens, prompt_length, ids, intervention, replay, **kwargs):
        if not replay:
            result, records = self._forward(tokens, ids, intervention,
                                            prompt_length=prompt_length, **kwargs)
            return result.last_hidden_state, [records]
        result, records = self._forward(tokens[:, :prompt_length], ids, intervention,
                                        prompt_length=prompt_length, use_cache=True, **kwargs)
        hidden, batches = [result.last_hidden_state], [records]
        for offset in range(prompt_length, tokens.shape[1]):
            result, records = self._forward(tokens[:, offset:offset + 1], ids, intervention,
                prompt_length=prompt_length, offset=offset, past=result.past_key_values,
                use_cache=True, **kwargs)
            hidden.append(result.last_hidden_state)
            batches.append(records)
        if tokens.shape[1] > prompt_length:
            batches[-1]["position_metadata"][-1]["terminal_observation_only"] = True
        return torch.cat(hidden, dim=1), batches

    def _evaluate_tokens(self, tokens, prompt_length, feature_ids, intervention,
                         collect_reconstruction, replay, started):
        self._request_memory(tokens.shape[1], use_cache=replay)
        ids, _ = self._intervention(feature_ids, intervention)
        clean, clean_batches = self._token_forward(tokens, prompt_length, ids, None, replay,
            collect_reconstruction=collect_reconstruction and intervention is None)
        if intervention is None:
            edited, batches = clean, clean_batches
        else:
            edited, batches = self._token_forward(tokens, prompt_length, ids, intervention,
                replay, collect_reconstruction=collect_reconstruction)
        unsteered_nll, edited_nll, kl = self._losses(clean, edited, tokens)
        del edited
        reconstruction_nll = None
        if collect_reconstruction:
            reconstructed, _ = self._token_forward(tokens, prompt_length, ids, None,
                                                    replay, reconstruct=True)
            _, reconstruction_nll, _ = self._losses(clean, reconstructed, tokens)
        telemetry = self._telemetry(ids, batches, intervention)
        return {"token_ids": tokens[0].tolist(), "input_tokens": prompt_length,
                "input_token_ids": tokens[0, :prompt_length].tolist(),
                "output_token_ids": tokens[0, prompt_length:].tolist(),
                "output_tokens": tokens.shape[1] - prompt_length, "prompt_length": prompt_length,
                "forward_schedule": "original_prefill_then_cached_token1" if replay else "uncached_teacher",
                "unsteered_nll": unsteered_nll, "edited_nll": edited_nll,
                "kl_clean_to_edited": kl, "reconstruction_nll": reconstruction_nll,
                "loss_alignment": "index i predicts token_ids[i] from prefix [:i]; index 0 is null",
                "telemetry": telemetry,
                "clean_telemetry": self._telemetry(ids, clean_batches),
                "activation_summaries": self._summaries(ids, telemetry),
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
            with _fp32_math(self.device):
                cosines = (vectors / vector_norms).T @ unit
            _finite("decoder cosines", cosines)
            for feature, norm, cosine in zip(ids[start:start + 128], vector_norms, cosines):
                rows.append({"feature_id": feature, "decoder_norm": norm.item(),
                             "target_cosines": cosine.tolist(),
                             "max_target_cosine": cosine.max().item(),
                             "max_abs_target_cosine": cosine.abs().max().item()})
        return {"feature_ids": list(ids), "target_ids": list(targets), "features": rows}

    def close(self):
        """Idempotently release this backend's model and resident full SAE."""
        self._closed = True
        self._sae = ()
        self._layer = None
        self.model = None
        self.tokenizer = None
        gc.collect()
        if self.device.type == "cuda":
            with torch.cuda.device(self.device):
                torch.cuda.empty_cache()

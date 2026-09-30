"""SAE-only native replay. Imports never download artifacts or load an LLM."""
from pathlib import Path
import time

import numpy as np
import torch
import torch.nn.functional as F

from experiments.sae_assay_diagnostic.backend import (
    SAE_ID, SAE_REVISION, SAE_FILENAME, SAE_FILE_SHA256, SAE_KEYS,
    _state_value, _hash_file, _finite, _finite_chunks, _fp32_math, _linear_token1,
)
from experiments.sae_assay_repair.feasibility import active_support_projection


def delivery(hidden, requested, edited):
    clean = hidden.float()
    realized = edited.float() - clean
    rn = torch.linalg.vector_norm(requested, dim=-1)
    an = torch.linalg.vector_norm(realized, dim=-1)
    hn = torch.linalg.vector_norm(clean, dim=-1)
    nz = rn > 0
    tiny = torch.finfo(torch.float32).tiny
    cosine = (requested * realized).sum(-1) / (rn * an).clamp_min(tiny)
    error = torch.linalg.vector_norm(realized - requested, dim=-1)
    return {"requested_norm": rn, "realized_norm": an, "clean_norm": hn,
            "nonzero_requested": nz, "identity": (hidden == edited).all(-1),
            "cosine": torch.where(nz, cosine.clamp(-1, 1), 1.),
            "relative_error": torch.where(nz, error / rn.clamp_min(tiny), 0.)}


def encode(hidden, encoder, bias):
    return F.relu(_linear_token1(hidden, encoder, bias))


@torch.inference_mode()
def replay(hidden, weights, feature_ids, gram):
    """One state, three arms. Keep at most one state's full SAE activations.

    Float64 projection coefficients use the published saved Gram. FP32 vector
    formation and one BF16 writeback are measured, not replaced by the ideal.
    This function accepts small FP32/BF16 dictionaries for synthetic tests.
    """
    e, b, d, db = weights
    if (hidden.ndim != 2 or not len(hidden) or e.ndim != 2
            or hidden.shape[1] != e.shape[1] or b.shape != (e.shape[0],)
            or d.shape != (e.shape[1], e.shape[0]) or db.shape != (e.shape[1],)
            or any(t.device != hidden.device or t.dtype != hidden.dtype for t in weights)
            or hidden.dtype not in (torch.float32, torch.bfloat16)):
        raise ValueError("Invalid native SAE/state tensors")
    if (len(feature_ids) != len(set(feature_ids)) or not 1 <= len(feature_ids) <= 6
            or any(type(i) is not int or not 0 <= i < len(e) for i in feature_ids)):
        raise ValueError("Invalid feature IDs")
    _finite("hidden", hidden)
    index = torch.tensor(feature_ids, device=hidden.device)
    selected_e, selected_b = e[index].float(), b[index].float()
    non_target = torch.ones(len(e), dtype=torch.bool, device=hidden.device)
    non_target[index] = False
    with _fp32_math(hidden.device):
        original = encode(hidden, e, b)
        before = original[:, index].float()
        pre = _linear_token1(hidden.float(), selected_e, selected_b)
        clean_norm = torch.linalg.vector_norm(hidden.float(), dim=-1)
        recon = _linear_token1(original, d, db)
        selected_before = F.relu(F.linear(hidden, e[index], b[index])).float()
        args = [np.asarray(gram, dtype=np.float64), pre.cpu().double().numpy(),
                before.cpu().double().numpy(), clean_norm.cpu().double().numpy()]
        arms = {}
        for mode in ("zero", "suppression", "amplification"):
            if mode == "zero":
                requested = torch.zeros_like(hidden, dtype=torch.float32)
                edited, changed = hidden, original
                coefficients = torch.zeros_like(before)
                scale = torch.ones(len(hidden), device=hidden.device)
                prediction = before
                continuous_norm = torch.zeros_like(scale)
            else:
                projection = active_support_projection(*args, mode=mode)
                coefficients = torch.as_tensor(projection["coefficients"], dtype=torch.float32,
                                               device=hidden.device)
                requested = _linear_token1(coefficients, selected_e.T)
                edited = (hidden.float() + requested).to(hidden.dtype)
                changed = encode(edited, e, b)
                scale = torch.as_tensor(projection["scale"], device=hidden.device)
                prediction = torch.as_tensor(projection["predicted_activation"], device=hidden.device)
                continuous_norm = torch.as_tensor(projection["norm"], device=hidden.device)
            after = changed[:, index].float()
            difference = changed.float() - original.float()
            drift = difference[:, non_target]
            result = {
                "before": before, "after": after,
                "selected_before": selected_before,
                "selected_after": F.relu(F.linear(edited, e[index], b[index])).float(),
                "fp32_preact_before": pre,
                "fp32_preact_ideal": _linear_token1(hidden.float() + requested, selected_e, selected_b),
                "fp32_preact_after": _linear_token1(edited.float(), selected_e, selected_b),
                "requested_activation_delta": (torch.zeros_like(before) if mode == "zero" else
                                                (.75 if mode == "amplification" else -.75) * before),
                "projection_coefficients": coefficients, "projection_scale": scale,
                "continuous_predicted_activation": prediction, "continuous_norm": continuous_norm,
                "l0_before": (original > 0).sum(-1), "l0_after": (changed > 0).sum(-1),
                "non_target_change_norm": torch.linalg.vector_norm(drift, dim=-1),
                "non_target_changed_count": (drift != 0).sum(-1),
                "non_target_activity_changes": ((original[:, non_target] > 0) != (changed[:, non_target] > 0)).sum(-1),
                "reconstruction_relative_error": torch.linalg.vector_norm(recon.float() - hidden.float(), dim=-1)
                                                 / clean_norm.clamp_min(1e-30),
                **delivery(hidden, requested, edited),
            }
            for name, value in result.items():
                _finite(name, value)
            arms[mode] = {key: value.cpu().tolist() for key, value in result.items()}
            if mode == "zero" and (edited is not hidden or not bool((hidden == edited).all())):
                raise ValueError("True zero identity failed")
    return arms


def qualify(device):
    """Synthetic exact-path check, not real-model evidence."""
    started = time.monotonic()
    device = torch.device(device)
    if device.type == "cuda" and not torch.cuda.is_bf16_supported():
        raise ValueError("Native BF16 required")
    e = torch.eye(8, dtype=torch.bfloat16, device=device)
    b = torch.zeros(8, dtype=torch.bfloat16, device=device)
    h = torch.tensor([[1, 2, 3, 4, 5, 6, 1000, 1000], [0, 0, 0, 0, 0, 0, 1000, 1000]],
                     dtype=torch.bfloat16, device=device)
    result = replay(h, (e, b, e.T.contiguous(), b), list(range(6)), np.eye(6))
    checks = {"zero": all(result["zero"]["identity"]),
              "suppression": result["suppression"]["after"][0] == [.25, .5, .75, 1, 1.25, 1.5],
              "amplification": result["amplification"]["after"][0] == [1.75, 3.5, 5.25, 7, 8.75, 10.5],
              "inactive_zero": all(result[mode]["identity"][1] for mode in result),
              "neighbor_zero": all(not any(result[mode]["non_target_changed_count"]) for mode in result)}
    return {"pass": all(checks.values()), "checks": checks, "synthetic_only": True,
            "device": str(device), "seconds": time.monotonic() - started}


class SAEBackend:
    def __init__(self, cache):
        if not torch.cuda.is_available() or not torch.cuda.is_bf16_supported():
            raise RuntimeError("CUDA/native BF16 required; no CPU production fallback")
        if torch.__version__.split("+")[0] != "2.8.0" or torch.version.cuda != "12.8":
            raise RuntimeError("Pinned torch 2.8.0 / CUDA 12.8 required")
        if torch.cuda.mem_get_info()[0] < 6 * 1024**3:
            raise RuntimeError("At least 6 GiB free VRAM required")
        from huggingface_hub import hf_hub_download
        path = Path(hf_hub_download(SAE_ID, SAE_FILENAME, revision=SAE_REVISION, cache_dir=str(cache)))
        _hash_file(path, SAE_FILE_SHA256, "sha256")
        state = torch.load(path, map_location="cpu", weights_only=True, mmap=True)
        values = tuple(_state_value(state, key).detach() for key in SAE_KEYS)
        if [tuple(t.shape) for t in values] != [(65536, 8192), (65536,), (8192, 65536), (8192,)]:
            raise ValueError("Unexpected SAE dimensions")
        self.weights = tuple(t.to(device="cuda", dtype=torch.bfloat16).contiguous() for t in values)
        for name, value in zip(SAE_KEYS, self.weights):
            _finite_chunks(name, value)
        self.metadata = {"sae_revision": SAE_REVISION, "sae_sha256": SAE_FILE_SHA256,
                         "torch": torch.__version__, "cuda": torch.version.cuda,
                         "gpu": torch.cuda.get_device_name(), "native_dtype": "bfloat16",
                         "encoder_shape": [1, 65536, 8192], "llm_loaded": False,
                         "tf32_in_intervention": False, "weight_bytes": path.stat().st_size,
                         "compute_capability": list(torch.cuda.get_device_capability()),
                         "bf16_reduced_precision_reduction": torch.backends.cuda.matmul.allow_bf16_reduced_precision_reduction,
                         "deterministic_algorithms": torch.are_deterministic_algorithms_enabled(),
                         "numpy": np.__version__}

    def run(self, hidden, ids, gram):
        return replay(hidden.to("cuda"), self.weights, ids, gram)

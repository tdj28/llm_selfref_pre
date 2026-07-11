#!/usr/bin/env python3
"""Execute the frozen Llama 70B SAE-through-Jacobian-lens audit."""

from __future__ import annotations

import argparse
import gc
import hashlib
import importlib.metadata
import json
import math
import os
import platform
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from experiments.exp2_sae.sae_jlens_protocol import (  # noqa: E402
    JLENS_FILE_SHA256,
    JLENS_FILENAME,
    JLENS_ID,
    JLENS_N_PROMPTS,
    JLENS_REVISION,
    LEXICON_CANDIDATES,
    MODEL_ID,
    MODEL_LAYERS,
    MODEL_REVISION,
    MODEL_WIDTH,
    PRIMARY_LAYER,
    PRIMARY_POSITION,
    PROTOCOL_VERSION,
    PURSUIT_K,
    SAE_FILE_SHA256,
    SAE_FILENAME,
    SAE_ID,
    SAE_LAYER,
    SAE_REVISION,
    SAE_WIDTH,
    STATIC_TOP_K,
    TRAJECTORY_LAYERS,
    TRANSPORT_RANDOM_SEEDS,
    read_jsonl,
    sha256_file,
    sha256_text,
    signed_permutation,
    write_json,
)


DEFAULT_PLAN_DIR = REPO_ROOT / "data/sae_jlens_audit/confirmatory_v1_plan_20260711"
DEFAULT_OUTDIR = REPO_ROOT / "out/sae_jlens_audit/confirmatory_v1_20260711"


class ProtocolViolation(RuntimeError):
    """Fail-closed error that must not be treated as a transient GPU failure."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def append_jsonl(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def read_sharded_jsonl(directory: Path) -> list[dict[str, Any]]:
    if not directory.exists():
        return []
    rows: list[dict[str, Any]] = []
    for path in sorted(directory.glob("part-*.jsonl")):
        rows.extend(read_jsonl(path))
    return rows


def package_version(name: str) -> str | None:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return None


def git_head() -> str | None:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, text=True
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def runtime_metadata(torch_module: Any) -> dict[str, Any]:
    return {
        "captured_at_utc": utc_now(),
        "protocol_version": PROTOCOL_VERSION,
        "git_commit": git_head(),
        "python": platform.python_version(),
        "platform": platform.platform(),
        "packages": {
            name: package_version(name)
            for name in (
                "accelerate",
                "huggingface-hub",
                "numpy",
                "scipy",
                "torch",
                "transformers",
            )
        },
        "cuda_available": bool(torch_module.cuda.is_available()),
        "cuda_runtime": torch_module.version.cuda,
        "gpu_count": torch_module.cuda.device_count(),
        "gpus": [
            {
                "index": index,
                "name": torch_module.cuda.get_device_name(index),
                "total_memory": torch_module.cuda.get_device_properties(index).total_memory,
            }
            for index in range(torch_module.cuda.device_count())
        ],
        "environment_flags": {
            "HF_HUB_ENABLE_HF_TRANSFER": os.environ.get("HF_HUB_ENABLE_HF_TRANSFER"),
            "TOKENIZERS_PARALLELISM": os.environ.get("TOKENIZERS_PARALLELISM"),
        },
    }


def verify_plan(plan_dir: Path) -> dict[str, Any]:
    manifest_path = plan_dir / "PLAN_MANIFEST.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("status") != "frozen_outcome_blind_plan":
        raise ProtocolViolation("Plan manifest is not outcome-blind and frozen")
    for record in manifest["files"]:
        path = plan_dir / record["path"]
        if not path.is_file() or sha256_file(path) != record["sha256"]:
            raise ProtocolViolation(f"Frozen plan file mismatch: {path}")
    snapshot = json.loads((plan_dir / "protocol_snapshot.json").read_text(encoding="utf-8"))
    if snapshot.get("protocol_version") != PROTOCOL_VERSION:
        raise ProtocolViolation("Runtime and plan protocol versions differ")
    return manifest


def download_artifacts(cache_dir: Path) -> tuple[Path, Path]:
    from huggingface_hub import hf_hub_download

    token = os.environ.get("HF_TOKEN") or os.environ.get("HUGGING_FACE_HUB_TOKEN")
    sae_path = Path(
        hf_hub_download(
            repo_id=SAE_ID,
            filename=SAE_FILENAME,
            revision=SAE_REVISION,
            cache_dir=cache_dir,
            token=token,
        )
    )
    lens_path = Path(
        hf_hub_download(
            repo_id=JLENS_ID,
            filename=JLENS_FILENAME,
            revision=JLENS_REVISION,
            cache_dir=cache_dir,
            token=token,
        )
    )
    observed = {
        "sae": sha256_file(sae_path),
        "jacobian_lens": sha256_file(lens_path),
    }
    expected = {"sae": SAE_FILE_SHA256, "jacobian_lens": JLENS_FILE_SHA256}
    if observed != expected:
        raise ProtocolViolation(
            f"Downloaded artifact hash mismatch: observed={observed}, expected={expected}"
        )
    return sae_path, lens_path


def load_model(cache_dir: Path) -> tuple[Any, Any, Any]:
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer

    if not torch.cuda.is_available():
        raise RuntimeError("CUDA is required")
    if torch.cuda.device_count() != 1:
        raise ProtocolViolation("Version 1 requires exactly one GPU")
    token = os.environ.get("HF_TOKEN") or os.environ.get("HUGGING_FACE_HUB_TOKEN")
    tokenizer = AutoTokenizer.from_pretrained(
        MODEL_ID,
        revision=MODEL_REVISION,
        cache_dir=cache_dir,
        token=token,
        use_fast=True,
    )
    model = AutoModelForCausalLM.from_pretrained(
        MODEL_ID,
        revision=MODEL_REVISION,
        cache_dir=cache_dir,
        token=token,
        dtype=torch.bfloat16,
        device_map={"": 0},
        low_cpu_mem_usage=True,
        attn_implementation="sdpa",
    )
    model.eval()
    for parameter in model.parameters():
        parameter.requires_grad_(False)

    config = model.config.get_text_config()
    if int(config.hidden_size) != MODEL_WIDTH:
        raise ProtocolViolation(f"Unexpected model width: {config.hidden_size}")
    if int(config.num_hidden_layers) != MODEL_LAYERS:
        raise ProtocolViolation(f"Unexpected layer count: {config.num_hidden_layers}")
    resolved = getattr(model.config, "_commit_hash", None)
    if resolved is not None and resolved != MODEL_REVISION:
        raise ProtocolViolation(f"Resolved model revision differs: {resolved}")
    if len(model.model.layers) != MODEL_LAYERS:
        raise ProtocolViolation("Model layer layout differs from the frozen hook layout")
    return torch, model, tokenizer


def load_lens(torch_module: Any, lens_path: Path) -> dict[int, Any]:
    checkpoint = torch_module.load(
        lens_path, map_location="cpu", weights_only=True, mmap=True
    )
    if not {"J", "n_prompts", "d_model"} <= set(checkpoint):
        raise ProtocolViolation(f"Unexpected lens keys: {sorted(checkpoint)}")
    if int(checkpoint["n_prompts"]) != JLENS_N_PROMPTS:
        raise ProtocolViolation(f"Unexpected lens prompt count: {checkpoint['n_prompts']}")
    if int(checkpoint["d_model"]) != MODEL_WIDTH:
        raise ProtocolViolation(f"Unexpected lens width: {checkpoint['d_model']}")
    missing = set(TRAJECTORY_LAYERS) - {int(layer) for layer in checkpoint["J"]}
    if missing:
        raise ProtocolViolation(f"Lens is missing requested layers: {sorted(missing)}")
    matrices = {
        layer: checkpoint["J"][layer]
        .to(device="cuda", dtype=torch_module.float16, non_blocking=True)
        .contiguous()
        for layer in TRAJECTORY_LAYERS
    }
    for layer, matrix in matrices.items():
        if tuple(matrix.shape) != (MODEL_WIDTH, MODEL_WIDTH):
            raise ProtocolViolation(f"Unexpected J_{layer} shape: {tuple(matrix.shape)}")
        if not bool(torch_module.isfinite(matrix).all()):
            raise ProtocolViolation(f"J_{layer} contains nonfinite values")
    del checkpoint
    gc.collect()
    return matrices


def _state_key(state: dict[str, Any], suffix: str) -> str:
    matches = [key for key in state if key == suffix or key.endswith("." + suffix)]
    if len(matches) != 1:
        raise ProtocolViolation(f"Expected one SAE key ending in {suffix!r}, found {matches}")
    return matches[0]


def load_sae_state(torch_module: Any, sae_path: Path) -> tuple[dict[str, Any], dict[str, str]]:
    state = torch_module.load(sae_path, map_location="cpu", weights_only=True, mmap=True)
    keys = {
        name: _state_key(state, name)
        for name in (
            "encoder_linear.weight",
            "encoder_linear.bias",
            "decoder_linear.weight",
            "decoder_linear.bias",
        )
    }
    decoder = state[keys["decoder_linear.weight"]]
    encoder = state[keys["encoder_linear.weight"]]
    if tuple(decoder.shape) != (MODEL_WIDTH, SAE_WIDTH):
        raise ProtocolViolation(f"Unexpected SAE decoder shape: {tuple(decoder.shape)}")
    if tuple(encoder.shape) != (SAE_WIDTH, MODEL_WIDTH):
        raise ProtocolViolation(f"Unexpected SAE encoder shape: {tuple(encoder.shape)}")
    return state, keys


def selected_feature_ids(
    static_plan: list[dict[str, Any]], paired_plan: list[dict[str, Any]]
) -> list[int]:
    feature_ids = {
        int(row["feature_id"])
        for row in static_plan
        if row.get("feature_id") is not None
    }
    for row in paired_plan:
        feature_ids.update(int(value) for value in row.get("feature_ids", []))
        feature_ids.update(int(value) for value in row.get("norm_source_feature_ids", []))
    return sorted(feature_ids)


def extract_decoder_directions(
    torch_module: Any,
    state: dict[str, Any],
    keys: dict[str, str],
    feature_ids: list[int],
) -> dict[int, Any]:
    decoder = state[keys["decoder_linear.weight"]]
    selected = decoder[:, feature_ids].to(device="cuda", dtype=torch_module.bfloat16)
    return {
        feature_id: selected[:, index].contiguous()
        for index, feature_id in enumerate(feature_ids)
    }


def exact_content_positions(tokenizer: Any, text: str) -> tuple[Any, dict[str, Any]]:
    import torch

    input_ids = tokenizer.apply_chat_template(
        [{"role": "user", "content": text}],
        add_generation_prompt=True,
        return_tensors="pt",
    )
    if not torch.is_tensor(input_ids):
        input_ids = input_ids["input_ids"]
    content_ids = tokenizer(text, add_special_tokens=False)["input_ids"]
    if not content_ids:
        raise ProtocolViolation("Prompt content tokenized to zero tokens")
    full = input_ids[0].tolist()
    matches = [
        start
        for start in range(len(full) - len(content_ids) + 1)
        if full[start : start + len(content_ids)] == content_ids
    ]
    if len(matches) != 1:
        raise ProtocolViolation(
            f"Expected one exact content subsequence, found {len(matches)} for {text!r}"
        )
    start = matches[0]
    positions = list(range(start, start + len(content_ids)))
    return input_ids.to("cuda"), {
        "content_start": start,
        "content_end_exclusive": start + len(content_ids),
        "content_positions": positions,
        "last_content": positions[-1],
        "assistant_boundary": len(full) - 1,
        "sequence_length": len(full),
        "input_ids_sha256": sha256_text(",".join(str(value) for value in full)),
    }


def build_lexicon(tokenizer: Any) -> dict[str, Any]:
    accepted: dict[str, list[dict[str, Any]]] = {}
    rejected: dict[str, list[dict[str, Any]]] = {}
    for group, candidates in LEXICON_CANDIDATES.items():
        accepted[group] = []
        rejected[group] = []
        for candidate in candidates:
            token_ids = tokenizer(candidate, add_special_tokens=False)["input_ids"]
            decoded = (
                tokenizer.decode(token_ids, clean_up_tokenization_spaces=False)
                if token_ids
                else ""
            )
            row = {
                "candidate": candidate,
                "token_ids": token_ids,
                "decoded": decoded,
            }
            if len(token_ids) == 1 and decoded == candidate:
                accepted[group].append({**row, "token_id": int(token_ids[0])})
            else:
                rejected[group].append(row)
        if len(accepted[group]) < 3:
            raise ProtocolViolation(
                f"Lexicon group {group!r} has only {len(accepted[group])} exact tokens"
            )
    return {"accepted": accepted, "rejected": rejected}


def isotropic_direction(
    torch_module: Any, seed: int, target_norm: float, sign: str
) -> Any:
    rng = np.random.default_rng(seed)
    values = rng.standard_normal(MODEL_WIDTH).astype(np.float32)
    values /= max(float(np.linalg.norm(values)), 1e-12)
    sign_value = -1.0 if sign == "suppression" else 1.0
    values *= np.float32(sign_value * target_norm)
    return torch_module.from_numpy(values).to(device="cuda", dtype=torch_module.bfloat16)


def vector_from_plan(
    torch_module: Any, row: dict[str, Any], directions: dict[int, Any]
) -> Any | None:
    if row["condition_family"] == "zero":
        return None
    if row["condition_family"] == "isotropic_aggregate":
        source = sum(
            float(coefficient) * directions[int(feature_id)].float()
            for feature_id, coefficient in zip(
                row["norm_source_feature_ids"], row["norm_source_coefficients"]
            )
        )
        target_norm = float(source.norm().item())
        return isotropic_direction(
            torch_module, int(row["random_seed"]), target_norm, row["sign"]
        )
    vector = sum(
        float(coefficient) * directions[int(feature_id)].float()
        for feature_id, coefficient in zip(row["feature_ids"], row["coefficients"])
    )
    return vector.to(dtype=torch_module.bfloat16)


def tensor_sha256(tensor: Any) -> str:
    import torch

    contiguous = tensor.detach().to(device="cpu").contiguous()
    return hashlib.sha256(contiguous.view(torch.uint8).numpy().tobytes()).hexdigest()


def capture_clean_layer50(torch_module: Any, model: Any, input_ids: Any) -> Any:
    captured: dict[str, Any] = {}

    def hook(_module: Any, _inputs: Any, output: Any) -> None:
        hidden = output if torch_module.is_tensor(output) else output[0]
        captured["hidden"] = hidden.detach()

    handle = model.model.layers[SAE_LAYER].register_forward_hook(hook)
    try:
        with torch_module.inference_mode():
            model.model(
                input_ids=input_ids,
                attention_mask=torch_module.ones_like(input_ids),
                use_cache=False,
            )
    finally:
        handle.remove()
    if "hidden" not in captured:
        raise ProtocolViolation("Layer-50 smoke hook did not fire")
    return captured["hidden"]


def smoke_direct_addition(
    torch_module: Any,
    model: Any,
    tokenizer: Any,
    state: dict[str, Any],
    keys: dict[str, str],
    directions: dict[int, Any],
    prompt: dict[str, Any],
) -> dict[str, Any]:
    import torch.nn.functional as functional

    input_ids, position_info = exact_content_positions(tokenizer, prompt["text"])
    hidden = capture_clean_layer50(torch_module, model, input_ids)[
        :, position_info[PRIMARY_POSITION], :
    ].float()
    feature_id = 30032
    coefficient = 2.1918

    encoder_weight = state[keys["encoder_linear.weight"]].to(
        device="cuda", dtype=torch_module.float32
    )
    encoder_bias = state[keys["encoder_linear.bias"]].to(
        device="cuda", dtype=torch_module.float32
    )
    decoder_weight = state[keys["decoder_linear.weight"]].to(
        device="cuda", dtype=torch_module.float32
    )
    decoder_bias = state[keys["decoder_linear.bias"]].to(
        device="cuda", dtype=torch_module.float32
    )
    with torch_module.inference_mode():
        features = functional.relu(functional.linear(hidden, encoder_weight, encoder_bias))
        reconstruction = functional.linear(features, decoder_weight, decoder_bias)
        error = hidden - reconstruction
        edited = features.clone()
        edited[:, feature_id] += coefficient
        exact = functional.linear(edited, decoder_weight, decoder_bias) + error
        direct = hidden + coefficient * decoder_weight[:, feature_id]
        difference = exact - direct
        max_abs = float(difference.abs().max().item())
        rmse = float(difference.square().mean().sqrt().item())
        reference_rms = float(exact.square().mean().sqrt().item())
        relative_rmse = rmse / reference_rms if reference_rms else math.inf
        direction_error = float(
            (decoder_weight[:, feature_id] - directions[feature_id].float())
            .abs()
            .max()
            .item()
        )

    del encoder_weight, encoder_bias, decoder_weight, decoder_bias
    del features, reconstruction, error, edited, exact, direct, difference, hidden, input_ids
    torch_module.cuda.empty_cache()
    if not math.isfinite(relative_rmse) or relative_rmse > 1e-5:
        raise ProtocolViolation(
            f"Direct-addition equivalence failed: relative_rmse={relative_rmse}"
        )
    if direction_error > 0.02:
        raise ProtocolViolation(f"Extracted decoder direction mismatch: {direction_error}")
    return {
        "status": "pass",
        "captured_at_utc": utc_now(),
        "feature_id": feature_id,
        "coefficient": coefficient,
        "position": PRIMARY_POSITION,
        "max_abs_error": max_abs,
        "rmse": rmse,
        "relative_rmse": relative_rmse,
        "selected_direction_cast_max_abs_error": direction_error,
        "input_ids_sha256": position_info["input_ids_sha256"],
    }


def transport_permutation(
    torch_module: Any, size: int, seed: int, layer: int, side: str
) -> tuple[Any, Any]:
    side_offset = 0 if side == "input" else 1
    permutation, signs = signed_permutation(
        size, seed + 10_000_019 * layer + side_offset * 1_000_003
    )
    return (
        torch_module.tensor(permutation, device="cuda", dtype=torch_module.long),
        torch_module.tensor(signs, device="cuda", dtype=torch_module.float16),
    )


class ReadoutEngine:
    def __init__(
        self,
        torch_module: Any,
        model: Any,
        tokenizer: Any,
        jacobians: dict[int, Any],
        lexicon: dict[str, Any],
    ) -> None:
        self.torch = torch_module
        self.model = model
        self.tokenizer = tokenizer
        self.jacobians = jacobians
        self.norm = model.model.norm
        self.lm_head = model.lm_head
        self.lexicon = lexicon
        token_ids = sorted(
            {
                int(row["token_id"])
                for rows in lexicon["accepted"].values()
                for row in rows
            }
        )
        self.token_ids = token_ids
        self.token_index = {token_id: index for index, token_id in enumerate(token_ids)}
        self.selected_weight = self.lm_head.weight[token_ids].detach().contiguous()
        self.group_indices = {
            group: [self.token_index[int(row["token_id"])] for row in rows]
            for group, rows in lexicon["accepted"].items()
        }
        self.permutations: dict[tuple[int, int, str], tuple[Any, Any]] = {}

    def transport(self, residual: Any, layer: int, name: str) -> Any:
        if name == "identity":
            return residual
        jacobian = self.jacobians[layer]
        if name == "jacobian":
            return residual.to(self.torch.float16) @ jacobian.T
        if not name.startswith("random_j_"):
            raise ValueError(f"Unknown transport: {name}")
        seed_index = int(name.rsplit("_", 1)[1]) - 1
        seed = TRANSPORT_RANDOM_SEEDS[seed_index]
        input_key = (seed, layer, "input")
        output_key = (seed, layer, "output")
        if input_key not in self.permutations:
            self.permutations[input_key] = transport_permutation(
                self.torch, MODEL_WIDTH, seed, layer, "input"
            )
            self.permutations[output_key] = transport_permutation(
                self.torch, MODEL_WIDTH, seed, layer, "output"
            )
        input_perm, input_sign = self.permutations[input_key]
        output_perm, output_sign = self.permutations[output_key]
        scrambled = residual.to(self.torch.float16)[..., input_perm] * input_sign
        transported = scrambled @ jacobian.T
        return transported[..., output_perm] * output_sign

    def selected_logits(self, residual: Any) -> Any:
        normalized = self.norm(residual.to(dtype=self.norm.weight.dtype))
        return normalized @ self.selected_weight.T

    def full_logits(self, residual: Any) -> Any:
        normalized = self.norm(residual.to(dtype=self.norm.weight.dtype))
        return self.lm_head(normalized).float()

    def summarize_selected(self, logits: Any) -> tuple[dict[str, float], list[float]]:
        flat = logits[0].float()
        groups = {
            group: float(flat[indices].mean().item())
            for group, indices in self.group_indices.items()
        }
        values = [float(value) for value in flat.tolist()]
        return groups, values


def token_rows(tokenizer: Any, logits: Any, largest: bool, k: int) -> list[dict[str, Any]]:
    values, indices = logits.topk(k, largest=largest)
    return [
        {
            "token_id": int(token_id),
            "token": tokenizer.decode([int(token_id)], clean_up_tokenization_spaces=False),
            "score": float(score),
        }
        for score, token_id in zip(values.tolist(), indices.tolist())
    ]


def excess_kurtosis(values: Any) -> float:
    centered = values.float() - values.float().mean()
    second = centered.square().mean()
    if float(second.item()) == 0.0:
        return 0.0
    fourth = centered.square().square().mean()
    return float((fourth / second.square() - 3.0).item())


def static_vector(
    torch_module: Any, row: dict[str, Any], directions: dict[int, Any]
) -> Any:
    if row["direction_kind"] == "sae_feature":
        return directions[int(row["feature_id"])]
    target = directions[int(row["matched_target_feature_id"])]
    return isotropic_direction(
        torch_module,
        int(row["random_seed"]),
        float(target.float().norm().item()),
        "amplification",
    )


def run_static(
    torch_module: Any,
    engine: ReadoutEngine,
    static_plan: list[dict[str, Any]],
    directions: dict[int, Any],
    output_path: Path,
) -> None:
    completed = set()
    if output_path.exists():
        completed = {
            (row["direction_id"], row["sign"], row["transport"])
            for row in read_jsonl(output_path)
        }
    transport_names = ["jacobian", "identity"] + [
        f"random_j_{index}" for index in range(1, len(TRANSPORT_RANDOM_SEEDS) + 1)
    ]
    for direction_row in static_plan:
        base = static_vector(torch_module, direction_row, directions)
        for sign_name, sign in (("negative", -1.0), ("positive", 1.0)):
            signed = sign * base
            for transport_name in transport_names:
                key = (direction_row["direction_id"], sign_name, transport_name)
                if key in completed:
                    continue
                transported = engine.transport(signed[None, :], SAE_LAYER, transport_name)
                logits = engine.full_logits(transported)[0]
                selected = logits[engine.token_ids][None, :]
                groups, token_values = engine.summarize_selected(selected)
                row = {
                    **direction_row,
                    "protocol_version": PROTOCOL_VERSION,
                    "captured_at_utc": utc_now(),
                    "sign": sign_name,
                    "transport": transport_name,
                    "source_norm": float(signed.float().norm().item()),
                    "transported_norm": float(transported.float().norm().item()),
                    "population_excess_kurtosis": excess_kurtosis(logits),
                    "lexicon_group_logits": groups,
                    "lexicon_token_ids": engine.token_ids,
                    "lexicon_token_logits": token_values,
                    "top_tokens": token_rows(
                        engine.tokenizer, logits, largest=True, k=STATIC_TOP_K
                    ),
                    "bottom_tokens": token_rows(
                        engine.tokenizer, logits, largest=False, k=STATIC_TOP_K
                    ),
                }
                append_jsonl(output_path, row)
                del transported, logits, selected


def eligible_vocabulary(tokenizer: Any, vocab_size: int) -> tuple[Any, list[str]]:
    import torch

    special = set(int(value) for value in tokenizer.all_special_ids)
    decoded = tokenizer.batch_decode(
        [[index] for index in range(vocab_size)], clean_up_tokenization_spaces=False
    )
    eligible = [
        index not in special
        and bool(text.strip())
        and any(character.isalnum() for character in text)
        for index, text in enumerate(decoded)
    ]
    return torch.tensor(eligible, device="cuda", dtype=torch.bool), decoded


def token_direction_norms(
    torch_module: Any, effective_weight: Any, jacobian: Any, batch_size: int = 512
) -> Any:
    norms = torch_module.empty(
        effective_weight.shape[0], device="cuda", dtype=torch_module.float32
    )
    for start in range(0, effective_weight.shape[0], batch_size):
        stop = min(start + batch_size, effective_weight.shape[0])
        columns = effective_weight[start:stop].to(torch_module.float16) @ jacobian
        norms[start:stop] = columns.float().square().sum(dim=1).sqrt()
        del columns
    return norms


def run_pursuit(
    torch_module: Any,
    engine: ReadoutEngine,
    static_plan: list[dict[str, Any]],
    directions: dict[int, Any],
    output_path: Path,
) -> None:
    from scipy.optimize import nnls

    completed = set()
    if output_path.exists():
        completed = {
            (row["direction_id"], int(row["k"])) for row in read_jsonl(output_path)
        }
    final_gain = engine.norm.weight.detach().to(dtype=engine.lm_head.weight.dtype)
    effective_weight = (engine.lm_head.weight.detach() * final_gain[None, :]).contiguous()
    jacobian = engine.jacobians[SAE_LAYER]
    eligible, decoded = eligible_vocabulary(engine.tokenizer, effective_weight.shape[0])
    direction_norms = token_direction_norms(
        torch_module, effective_weight, jacobian
    ).clamp_min_(1e-12)

    for direction_row in static_plan:
        if all((direction_row["direction_id"], k) in completed for k in PURSUIT_K):
            continue
        target = static_vector(torch_module, direction_row, directions).float()
        target_norm = float(target.norm().item())
        residual = target.clone()
        selected_ids: list[int] = []
        selected_columns: list[Any] = []
        coefficients = np.empty(0, dtype=np.float64)
        for iteration in range(1, max(PURSUIT_K) + 1):
            projected = jacobian @ residual.to(torch_module.float16)
            correlations = (
                effective_weight @ projected.to(dtype=effective_weight.dtype)
            ).float()
            correlations /= direction_norms
            correlations[~eligible] = -torch_module.inf
            if selected_ids:
                correlations[selected_ids] = -torch_module.inf
            token_id = int(correlations.argmax().item())
            if not math.isfinite(float(correlations[token_id].item())):
                raise ProtocolViolation("Sparse pursuit exhausted eligible token directions")
            column = (
                effective_weight[token_id : token_id + 1].to(torch_module.float16)
                @ jacobian
            )[0].float()
            column /= column.norm().clamp_min(1e-12)
            selected_ids.append(token_id)
            selected_columns.append(column)

            matrix = torch_module.stack(selected_columns, dim=1)
            matrix_cpu = matrix.detach().cpu().numpy().astype(np.float64, copy=False)
            target_cpu = target.detach().cpu().numpy().astype(np.float64, copy=False)
            coefficients, _ = nnls(matrix_cpu, target_cpu, maxiter=20 * iteration)
            fitted = matrix @ torch_module.from_numpy(coefficients).to(
                device="cuda", dtype=torch_module.float32
            )
            residual = target - fitted

            if iteration in PURSUIT_K and (
                direction_row["direction_id"], iteration
            ) not in completed:
                residual_norm = float(residual.norm().item())
                fitted_norm = float(fitted.norm().item())
                cosine = float(
                    torch_module.nn.functional.cosine_similarity(
                        target[None, :], fitted[None, :], dim=1, eps=1e-12
                    ).item()
                )
                append_jsonl(
                    output_path,
                    {
                        **direction_row,
                        "protocol_version": PROTOCOL_VERSION,
                        "captured_at_utc": utc_now(),
                        "k": iteration,
                        "target_norm": target_norm,
                        "fitted_norm": fitted_norm,
                        "remainder_norm": residual_norm,
                        "explained_squared_norm": 1.0
                        - (residual_norm * residual_norm) / (target_norm * target_norm),
                        "fit_cosine": cosine,
                        "selected": [
                            {
                                "rank": rank,
                                "token_id": selected_id,
                                "token": decoded[selected_id],
                                "coefficient": float(coefficient),
                            }
                            for rank, (selected_id, coefficient) in enumerate(
                                zip(selected_ids, coefficients), start=1
                            )
                        ],
                    },
                )
            del projected, correlations, column, matrix, fitted
        del target, residual, selected_columns
    del effective_weight, eligible, direction_norms
    torch_module.cuda.empty_cache()


def capture_trajectory(
    torch_module: Any,
    model: Any,
    input_ids: Any,
    intervention: Any | None,
) -> tuple[dict[int, Any], dict[str, Any]]:
    captures: dict[int, Any] = {}
    handles = []

    def make_hook(layer: int) -> Any:
        def hook(_module: Any, _inputs: Any, output: Any) -> Any:
            hidden = output if torch_module.is_tensor(output) else output[0]
            if layer == SAE_LAYER and intervention is not None:
                hidden = hidden + intervention.to(dtype=hidden.dtype)[None, None, :]
                updated = hidden if torch_module.is_tensor(output) else (hidden,) + output[1:]
            else:
                updated = output
            captures[layer] = hidden.detach()
            return updated

        return hook

    try:
        for layer in TRAJECTORY_LAYERS:
            handles.append(model.model.layers[layer].register_forward_hook(make_hook(layer)))
        with torch_module.inference_mode():
            model.model(
                input_ids=input_ids,
                attention_mask=torch_module.ones_like(input_ids),
                use_cache=False,
            )
    finally:
        for handle in handles:
            handle.remove()
    if set(captures) != set(TRAJECTORY_LAYERS):
        raise ProtocolViolation(f"Missing trajectory captures: {set(TRAJECTORY_LAYERS)-set(captures)}")
    layer50 = captures[SAE_LAYER]
    hidden_rms = float(layer50.float().square().mean().sqrt().item())
    delta_rms = (
        0.0
        if intervention is None
        else float(intervention.float().square().mean().sqrt().item())
    )
    return captures, {
        "hook_registrations": len(handles),
        "hook_calls": len(captures),
        "hook_removed": True,
        "zero_is_true_noop": intervention is None,
        "hidden_rms_layer50": hidden_rms,
        "intervention_rms": delta_rms,
        "relative_intervention_rms": delta_rms / hidden_rms if hidden_rms else None,
    }


def position_batch(hidden: Any, positions: dict[str, Any]) -> tuple[Any, list[str]]:
    import torch

    names = [PRIMARY_POSITION, "assistant_boundary", "content_mean"]
    vectors = [
        hidden[0, positions[PRIMARY_POSITION], :],
        hidden[0, positions["assistant_boundary"], :],
        hidden[0, positions["content_positions"], :].mean(dim=0),
    ]
    return torch.stack(vectors), names


def run_paired(
    torch_module: Any,
    model: Any,
    tokenizer: Any,
    engine: ReadoutEngine,
    paired_plan: list[dict[str, Any]],
    directions: dict[int, Any],
    output_dir: Path,
    max_trials: int | None,
) -> None:
    completed = set()
    if output_dir.exists():
        completed = {row["trial_id"] for row in read_sharded_jsonl(output_dir)}
    pending = [row for row in paired_plan if row["trial_id"] not in completed]
    if max_trials is not None:
        pending = pending[:max_trials]
    token_cache: dict[str, tuple[Any, dict[str, Any]]] = {}
    transport_names = ["jacobian", "identity"] + [
        f"random_j_{index}" for index in range(1, len(TRANSPORT_RANDOM_SEEDS) + 1)
    ]

    started = time.monotonic()
    for pending_index, plan_row in enumerate(pending, start=1):
        prompt_id = plan_row["prompt_id"]
        if prompt_id not in token_cache:
            token_cache[prompt_id] = exact_content_positions(tokenizer, plan_row["text"])
        input_ids, positions = token_cache[prompt_id]
        intervention = vector_from_plan(torch_module, plan_row, directions)
        if intervention is not None:
            if not bool(torch_module.isfinite(intervention).all()):
                raise ProtocolViolation(f"Nonfinite intervention: {plan_row['trial_id']}")
            if float(intervention.float().norm().item()) == 0.0:
                raise ProtocolViolation(f"Zero nonzero intervention: {plan_row['trial_id']}")
        captures, diagnostics = capture_trajectory(
            torch_module, model, input_ids, intervention
        )
        readouts: list[dict[str, Any]] = []
        for layer in TRAJECTORY_LAYERS:
            residual_batch, position_names = position_batch(captures[layer], positions)
            for transport_name in transport_names:
                transported = engine.transport(residual_batch, layer, transport_name)
                logits = engine.selected_logits(transported)
                for position_index, position_name in enumerate(position_names):
                    group_logits, token_logits = engine.summarize_selected(
                        logits[position_index : position_index + 1]
                    )
                    readouts.append(
                        {
                            "layer": layer,
                            "position": position_name,
                            "transport": transport_name,
                            "source_norm": float(
                                residual_batch[position_index].float().norm().item()
                            ),
                            "transported_norm": float(
                                transported[position_index].float().norm().item()
                            ),
                            "group_logits": group_logits,
                            "token_logits": token_logits,
                        }
                    )
                del transported, logits
            del residual_batch
        result = {
            **plan_row,
            "protocol_version": PROTOCOL_VERSION,
            "captured_at_utc": utc_now(),
            "position_metadata": positions,
            "intervention": {
                "vector_sha256_bfloat16": (
                    None if intervention is None else tensor_sha256(intervention)
                ),
                "vector_norm": (
                    0.0 if intervention is None else float(intervention.float().norm().item())
                ),
                **diagnostics,
            },
            "lexicon_token_ids": engine.token_ids,
            "readouts": readouts,
        }
        shard = int(plan_row["execution_order"]) // 200
        append_jsonl(output_dir / f"part-{shard:03d}.jsonl", result)
        del captures, readouts, intervention
        if pending_index % 10 == 0 or pending_index == len(pending):
            elapsed = time.monotonic() - started
            rate = pending_index / elapsed if elapsed else 0.0
            print(
                json.dumps(
                    {
                        "phase": "paired",
                        "completed_this_process": pending_index,
                        "pending_this_process": len(pending),
                        "trials_per_second": rate,
                    },
                    sort_keys=True,
                ),
                flush=True,
            )


def result_inventory(outdir: Path) -> list[dict[str, Any]]:
    return [
        {
            "path": path.relative_to(outdir).as_posix(),
            "bytes": path.stat().st_size,
            "sha256": sha256_file(path),
        }
        for path in sorted(outdir.rglob("*"))
        if path.is_file()
        and path.suffix != ".log"
        and path.name not in {"RUN_COMPLETE.json", "RESULT_MANIFEST.json"}
    ]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan-dir", type=Path, default=DEFAULT_PLAN_DIR)
    parser.add_argument("--outdir", type=Path, default=DEFAULT_OUTDIR)
    parser.add_argument("--cache-dir", type=Path, default=Path("/workspace/hf-cache"))
    parser.add_argument(
        "--phase", choices=("smoke", "static", "paired", "all"), default="all"
    )
    parser.add_argument("--max-paired", type=int)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument(
        "--skip-pursuit",
        action="store_true",
        help="Technical pilot only; a complete frozen run must not use this flag.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    plan_dir = args.plan_dir.resolve()
    outdir = args.outdir.resolve()
    outdir.mkdir(parents=True, exist_ok=True)
    if any(outdir.iterdir()) and not args.resume:
        raise FileExistsError(f"Output directory is not empty: {outdir}")
    manifest = verify_plan(plan_dir)

    import torch

    write_json(outdir / "runtime_metadata.json", runtime_metadata(torch))
    sae_path, lens_path = download_artifacts(args.cache_dir.resolve())
    write_json(
        outdir / "artifact_hashes.json",
        {
            "captured_at_utc": utc_now(),
            "plan_manifest_sha256": sha256_file(plan_dir / "PLAN_MANIFEST.json"),
            "sae": {"path_name": sae_path.name, "sha256": sha256_file(sae_path)},
            "jacobian_lens": {
                "path_name": lens_path.name,
                "sha256": sha256_file(lens_path),
            },
            "runtime_sources": [
                {
                    "path": path.relative_to(REPO_ROOT).as_posix(),
                    "sha256": sha256_file(path),
                }
                for path in (
                    Path(__file__).resolve(),
                    Path(__file__).resolve().with_name("sae_jlens_protocol.py"),
                )
            ],
        },
    )
    static_plan = read_jsonl(plan_dir / "static_direction_plan.jsonl")
    paired_plan = read_jsonl(plan_dir / "paired_plan.jsonl")
    prompts = read_jsonl(plan_dir / "prompt_plan.jsonl")

    torch_module, model, tokenizer = load_model(args.cache_dir.resolve())
    lexicon = build_lexicon(tokenizer)
    write_json(outdir / "lexicon_tokens.json", lexicon)
    jacobians = load_lens(torch_module, lens_path)
    state, keys = load_sae_state(torch_module, sae_path)
    directions = extract_decoder_directions(
        torch_module,
        state,
        keys,
        selected_feature_ids(static_plan, paired_plan),
    )

    smoke = smoke_direct_addition(
        torch_module, model, tokenizer, state, keys, directions, prompts[0]
    )
    write_json(outdir / "smoke_test.json", smoke)
    del state
    gc.collect()
    torch_module.cuda.empty_cache()

    engine = ReadoutEngine(torch_module, model, tokenizer, jacobians, lexicon)
    if args.phase in {"static", "all"}:
        run_static(
            torch_module,
            engine,
            static_plan,
            directions,
            outdir / "static_results.jsonl",
        )
        if not args.skip_pursuit:
            run_pursuit(
                torch_module,
                engine,
                static_plan,
                directions,
                outdir / "pursuit_results.jsonl",
            )
    if args.phase in {"paired", "all"}:
        run_paired(
            torch_module,
            model,
            tokenizer,
            engine,
            paired_plan,
            directions,
            outdir / "paired_results",
            args.max_paired,
        )

    complete = (
        args.phase == "all"
        and args.max_paired is None
        and not args.skip_pursuit
        and len(read_jsonl(outdir / "static_results.jsonl")) == len(static_plan) * 2 * 7
        and len(read_jsonl(outdir / "pursuit_results.jsonl"))
        == len(static_plan) * len(PURSUIT_K)
        and len(read_sharded_jsonl(outdir / "paired_results")) == len(paired_plan)
    )
    status = {
        "status": "complete" if complete else "partial",
        "completed_at_utc": utc_now(),
        "protocol_version": PROTOCOL_VERSION,
        "plan_manifest_sha256": sha256_file(plan_dir / "PLAN_MANIFEST.json"),
        "plan_manifest_status": manifest["status"],
        "phase_requested": args.phase,
        "max_paired": args.max_paired,
        "skip_pursuit": args.skip_pursuit,
    }
    write_json(outdir / "RUN_COMPLETE.json", status)
    write_json(
        outdir / "RESULT_MANIFEST.json",
        {**status, "files": result_inventory(outdir)},
    )
    print(json.dumps(status, sort_keys=True), flush=True)
    if not complete and args.phase == "all" and args.max_paired is None:
        raise ProtocolViolation("Full run did not satisfy completion counts")


if __name__ == "__main__":
    main()

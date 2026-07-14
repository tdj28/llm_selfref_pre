"""Target-blind GPU executor for the readout-validation pilot.

The module is deliberately self-contained.  It does not import the terminated
``consciousness_sae_changepoint`` study, any target prompt, or any prior result
or receipt.  Runtime inputs are limited to the frozen pilot plan, the reviewed
fixtures in :mod:`fixtures`, and a separately validated execution-binding
receipt pointing at local public artifacts.

The expensive 70B model is loaded only after all of the following cheap gates
have succeeded:

* the plan and execution binding are content-addressed and agree;
* all artifact paths resolve below the pilot's sentinel-bound public cache;
* the SAE and J-lens files match their public SHA-256 pins;
* tokenizer size, exact leading-space semantic tokens, and contextual Yes/No
  tokens satisfy the frozen contract; and
* all G4 vectors have been materialized and their norms recorded before an
  edited forward can be requested.

This file writes measurements, lineage, and operational failures only.  It
never calculates a gate verdict; ``analysis.py`` owns every scientific pass or
fail decision.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import os
import re
import shutil
import statistics
from collections.abc import Iterable, Mapping, Sequence
from contextlib import AbstractContextManager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from . import fixtures, protocol, tokenizer_audit
from .paths import (
    UnsafePilotPath,
    require_external_artifact_root,
    require_public_artifact_input,
)


HEX64 = re.compile(r"[0-9a-f]{64}")
SAFE_RUN_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")
PHASE_TO_DIRECTORY = {
    "G1": "g1_transport_arithmetic",
    "G2": "g2_neutral_transport",
    "G3": "g3_clean_semantic_readout",
    "G3P": "g3p_clean_polarity",
    "G4": "g4_vector_safety",
}
ROW_FILENAMES = {
    "G1": ("g1_rows.jsonl",),
    "G2": ("g2_transport_rows.jsonl", "g2_linearity_rows.jsonl"),
    "G3": ("g3_rows.jsonl",),
    "G3P": ("g3p_rows.jsonl",),
    "G4": (
        "g4_clean_rows.jsonl",
        "g4_vector_rows.jsonl",
        "g4_telemetry_rows.jsonl",
    ),
}


class PilotRuntimeError(RuntimeError):
    """A fail-closed pilot runtime violation with a stable machine code."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def sha256_file(path: Path, *, chunk_bytes: int = 8 * 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(chunk_bytes):
            digest.update(chunk)
    return digest.hexdigest()


def embedded_sha256(value: Mapping[str, Any], field: str) -> str:
    expected = value.get(field)
    if not isinstance(expected, str) or not HEX64.fullmatch(expected):
        raise PilotRuntimeError("binding_hash", f"{field} is missing or malformed")
    payload = dict(value)
    del payload[field]
    observed = canonical_sha256(payload)
    if observed != expected:
        raise PilotRuntimeError("binding_hash", f"{field} does not reconstruct")
    return expected


def stable_row_id(*parts: object) -> str:
    return canonical_sha256(
        {
            "study_id": protocol.STUDY_ID,
            "protocol_version": protocol.PROTOCOL_VERSION,
            "parts": parts,
        }
    )[:32]


def _torch() -> Any:
    try:
        import torch
    except ImportError as exc:  # pragma: no cover - GPU environment only
        raise PilotRuntimeError("torch_missing", "PyTorch is required") from exc
    return torch


def tensor_sha256(tensor: Any) -> str:
    """Hash dtype, shape, and exact contiguous bytes, including BF16."""

    torch = _torch()
    if not isinstance(tensor, torch.Tensor):
        raise TypeError("tensor_sha256 expects a torch.Tensor")
    cpu = tensor.detach().contiguous().to(device="cpu")
    digest = hashlib.sha256()
    digest.update(
        canonical_json_bytes({"dtype": str(cpu.dtype), "shape": list(cpu.shape)})
    )
    digest.update(b"\0")
    raw = cpu.view(torch.uint8).reshape(-1)
    for start in range(0, int(raw.numel()), 8 * 1024 * 1024):
        digest.update(raw[start : start + 8 * 1024 * 1024].numpy().tobytes())
    return digest.hexdigest()


def tensor_rms(tensor: Any) -> float:
    torch = _torch()
    value = float(torch.sqrt(torch.mean(tensor.detach().float().square())).item())
    if not math.isfinite(value) or value <= 0:
        raise PilotRuntimeError("tensor_rms", "tensor RMS is non-finite or non-positive")
    return value


def relative_rmse(observed: Any, expected: Any) -> float:
    torch = _torch()
    left = observed.detach().float().reshape(-1)
    right = expected.detach().float().reshape(-1)
    if left.shape != right.shape or left.numel() == 0:
        raise PilotRuntimeError("metric_shape", "relative-RMSE tensors differ")
    numerator = torch.sqrt(torch.mean((left - right).square()))
    denominator = torch.sqrt(torch.mean(right.square())).clamp_min(1e-30)
    value = float((numerator / denominator).item())
    if not math.isfinite(value):
        raise PilotRuntimeError("metric_nonfinite", "relative RMSE is non-finite")
    return value


def cosine_similarity(left: Any, right: Any) -> float:
    torch = _torch()
    a = left.detach().float().reshape(-1)
    b = right.detach().float().reshape(-1)
    if a.shape != b.shape or a.numel() == 0:
        raise PilotRuntimeError("metric_shape", "cosine tensors differ")
    denominator = torch.linalg.vector_norm(a) * torch.linalg.vector_norm(b)
    if float(denominator.item()) <= 0:
        raise PilotRuntimeError("metric_degenerate", "cosine denominator is zero")
    value = float(torch.dot(a, b).item() / denominator.item())
    if not math.isfinite(value):
        raise PilotRuntimeError("metric_nonfinite", "cosine is non-finite")
    return max(-1.0, min(1.0, value))


def pearson_correlation(left: Any, right: Any) -> float:
    torch = _torch()
    a = left.detach().float().reshape(-1)
    b = right.detach().float().reshape(-1)
    if a.shape != b.shape or a.numel() < 2:
        raise PilotRuntimeError("metric_shape", "Pearson vectors differ or are too short")
    a = a - a.mean()
    b = b - b.mean()
    denominator = torch.linalg.vector_norm(a) * torch.linalg.vector_norm(b)
    if float(denominator.item()) <= 0:
        raise PilotRuntimeError("metric_degenerate", "Pearson denominator is zero")
    value = float(torch.dot(a, b).item() / denominator.item())
    if not math.isfinite(value):
        raise PilotRuntimeError("metric_nonfinite", "Pearson correlation is non-finite")
    return max(-1.0, min(1.0, value))


def _extract_hidden(output: Any) -> Any:
    torch = _torch()
    if isinstance(output, torch.Tensor):
        return output
    if isinstance(output, (tuple, list)) and output and isinstance(output[0], torch.Tensor):
        return output[0]
    raise PilotRuntimeError("hook_output", "transformer block output has no hidden tensor")


def _replace_hidden(output: Any, hidden: Any) -> Any:
    torch = _torch()
    if isinstance(output, torch.Tensor):
        return hidden
    if isinstance(output, tuple):
        return (hidden, *output[1:])
    if isinstance(output, list):
        return [hidden, *output[1:]]
    raise PilotRuntimeError("hook_output", "cannot replace transformer hidden tensor")


@dataclass
class HookMeasurement:
    pre: Any
    post: Any
    vector: Any
    forward_id: str


class SingleUseResidualHook(AbstractContextManager["SingleUseResidualHook"]):
    """One explicitly armed, single-position residual addition at any layer."""

    def __init__(self, layer_module: Any, vector: Any, *, forward_id: str) -> None:
        torch = _torch()
        if not isinstance(forward_id, str) or not forward_id:
            raise ValueError("forward_id must be non-empty")
        if not isinstance(vector, torch.Tensor) or vector.ndim != 1:
            raise TypeError("intervention vector must be one-dimensional")
        if not vector.is_floating_point() or not bool(torch.isfinite(vector).all()):
            raise PilotRuntimeError("hook_vector", "intervention vector is invalid")
        self.layer_module = layer_module
        self.vector = vector.detach().clone()
        self.forward_id = forward_id
        self.handle: Any | None = None
        self.armed = False
        self.fire_count = 0
        self.measurement: HookMeasurement | None = None

    def __enter__(self) -> "SingleUseResidualHook":
        if self.handle is not None:
            raise PilotRuntimeError("hook_reuse", "hook is already registered")
        self.handle = self.layer_module.register_forward_hook(self._hook)
        self.armed = True
        return self

    def _hook(self, _module: Any, _inputs: Any, output: Any) -> Any:
        torch = _torch()
        if not self.armed or self.fire_count:
            raise PilotRuntimeError("hook_unarmed", "hook fired outside its one armed call")
        hidden = _extract_hidden(output)
        if hidden.ndim != 3 or hidden.shape[0] != 1 or hidden.shape[1] != 1:
            raise PilotRuntimeError(
                "hook_shape", "edited forward must contain exactly one batch/token position"
            )
        if hidden.shape[-1] != self.vector.numel():
            raise PilotRuntimeError("hook_width", "vector width differs from residual width")
        vector = self.vector.to(device=hidden.device, dtype=hidden.dtype)
        pre = hidden.detach().clone()
        post = hidden + vector.view(1, 1, -1)
        if not bool(torch.isfinite(post).all()):
            raise PilotRuntimeError("hook_nonfinite", "post-edit residual is non-finite")
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
        if exc_type is None and (self.armed or self.fire_count != 1 or self.measurement is None):
            raise PilotRuntimeError("hook_count", "hook did not fire exactly once")
        return False


class FinalNormInputCapture(AbstractContextManager["FinalNormInputCapture"]):
    """Capture the pre-final-RMSNorm residual used for G2 transport fidelity."""

    def __init__(self, norm_module: Any) -> None:
        self.norm_module = norm_module
        self.handle: Any | None = None
        self.value: Any | None = None

    def __enter__(self) -> "FinalNormInputCapture":
        self.handle = self.norm_module.register_forward_pre_hook(self._hook)
        return self

    def _hook(self, _module: Any, inputs: Any) -> None:
        hidden = inputs[0]
        self.value = hidden.detach().clone().to("cpu")

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> bool:
        if self.handle is not None:
            self.handle.remove()
            self.handle = None
        if exc_type is None and self.value is None:
            raise PilotRuntimeError("final_capture", "final RMSNorm input was not captured")
        return False


def clone_kv_cache(cache: Any) -> Any:
    """Clone a Transformers cache without aliasing mutable tensors."""

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


def rms_norm(hidden: Any, weight: Any, eps: float) -> Any:
    torch = _torch()
    values = hidden.float()
    normalized = values * torch.rsqrt(values.square().mean(dim=-1, keepdim=True) + eps)
    return normalized.to(dtype=weight.dtype) * weight


def selected_logits(normalized: Any, lm_head_weight: Any, token_ids: Sequence[int]) -> Any:
    torch = _torch()
    ids = torch.tensor(list(token_ids), dtype=torch.long, device=lm_head_weight.device)
    rows = lm_head_weight.index_select(0, ids)
    return (normalized.to(dtype=rows.dtype) @ rows.T).float()


def transported_selected_logits(
    source: Any,
    matrix: Any,
    norm_weight: Any,
    lm_head_weight: Any,
    token_ids: Sequence[int],
    *,
    eps: float,
) -> tuple[Any, Any]:
    transported = source.to(dtype=matrix.dtype) @ matrix.T
    normalized = rms_norm(transported.to(dtype=norm_weight.dtype), norm_weight, eps)
    return transported, selected_logits(normalized, lm_head_weight, token_ids)


def deterministic_direction(width: int, *, layer: int, direction: int, torch_module: Any | None = None) -> Any:
    """PCG64 direction frozen by protocol, normalized to unit RMS."""

    import numpy as np

    torch = torch_module or _torch()
    seed = protocol.g2_direction_seed(layer, direction)
    values = np.random.Generator(np.random.PCG64(seed)).standard_normal(width).astype(np.float32)
    values /= max(float(np.sqrt(np.mean(values * values))), 1e-30)
    result = torch.from_numpy(values)
    if not bool(torch.isfinite(result).all()):
        raise PilotRuntimeError("direction_nonfinite", "deterministic direction is non-finite")
    return result


def random_j_parameters(
    width: int,
    *,
    layer: int,
    control_index: int,
    torch_module: Any | None = None,
    device: Any = "cpu",
) -> tuple[Any, Any, Any, Any]:
    """Frozen input/output signed permutations for one random-J control."""

    import numpy as np

    torch = torch_module or _torch()
    seed = protocol.g2_random_j_seed(layer, control_index)
    rng = np.random.Generator(np.random.PCG64(seed))
    input_perm = rng.permutation(width).astype(np.int64)
    input_sign = rng.choice(np.array([-1.0, 1.0], dtype=np.float32), width)
    output_perm = rng.permutation(width).astype(np.int64)
    output_sign = rng.choice(np.array([-1.0, 1.0], dtype=np.float32), width)
    return (
        torch.from_numpy(input_perm).to(device=device),
        torch.from_numpy(input_sign).to(device=device),
        torch.from_numpy(output_perm).to(device=device),
        torch.from_numpy(output_sign).to(device=device),
    )


def apply_random_j(source: Any, matrix: Any, *, layer: int, control_index: int) -> Any:
    input_perm, input_sign, output_perm, output_sign = random_j_parameters(
        int(source.shape[-1]),
        layer=layer,
        control_index=control_index,
        device=source.device,
    )
    scrambled = source[..., input_perm] * input_sign.to(dtype=source.dtype)
    transported = scrambled.to(dtype=matrix.dtype) @ matrix.T
    return transported[..., output_perm] * output_sign.to(dtype=transported.dtype)


def synthetic_residual(fixture: Mapping[str, Any], width: int) -> Any:
    """Materialize one of the four G1 vectors without consulting a model."""

    import numpy as np

    torch = _torch()
    distribution = fixture["distribution"]
    seed = int(fixture["seed"])
    if distribution == "standard_normal":
        values = np.random.Generator(np.random.PCG64(seed)).standard_normal(width).astype(np.float32)
    elif distribution == "signed_unit":
        rng = np.random.Generator(np.random.PCG64(seed))
        values = rng.choice(np.array([-1.0, 1.0], dtype=np.float32), width)
    elif distribution == "hash_selected_sparse":
        values = np.zeros(width, dtype=np.float32)
        for index in range(min(64, width)):
            digest = hashlib.sha256(
                (
                    f"{protocol.STUDY_ID}|{protocol.PROTOCOL_VERSION}|"
                    f"g1-sparse|{seed}|{index}"
                ).encode()
            ).digest()
            position = int.from_bytes(digest[:8], "big") % width
            values[position] += 1.0 if digest[8] & 1 else -1.0
    elif distribution == "deterministic_centered_ramp":
        values = np.linspace(-1.0, 1.0, width, dtype=np.float32)
    else:
        raise PilotRuntimeError("g1_fixture", f"unknown G1 distribution: {distribution}")
    result = torch.from_numpy(values)
    if tensor_rms(result) <= 0:
        raise PilotRuntimeError("g1_fixture", "synthetic fixture is degenerate")
    return result


def exact_token_metadata(tokenizer: Any) -> dict[str, Any]:
    """Audit every token before model weights or a model forward are allowed."""

    groups: dict[str, list[dict[str, Any]]] = {}
    ordered_ids: list[int] = []
    for family in protocol.G3_FAMILIES:
        rows: list[dict[str, Any]] = []
        for label in protocol.G3_TOKEN_GROUPS[family]:
            piece = f" {label}"
            ids = [int(value) for value in tokenizer.encode(piece, add_special_tokens=False)]
            decoded = tokenizer.decode(ids, clean_up_tokenization_spaces=False)
            if len(ids) != 1 or decoded != piece:
                raise PilotRuntimeError(
                    "semantic_tokenization",
                    f"{family}/{label} is not an exact leading-space one-token round trip",
                )
            token_id = ids[0]
            if token_id in ordered_ids:
                raise PilotRuntimeError("semantic_token_duplicate", f"duplicate token ID {token_id}")
            ordered_ids.append(token_id)
            rows.append({"label": label, "piece": piece, "token_id": token_id})
        if len(rows) != len(protocol.G3_TOKEN_GROUPS[family]) or len(rows) < 3:
            raise PilotRuntimeError("semantic_token_count", f"{family} token panel is incomplete")
        groups[family] = rows

    yes_no: dict[str, int] = {}
    for label in ("Yes", "No"):
        piece = label
        ids = [int(value) for value in tokenizer.encode(piece, add_special_tokens=False)]
        if len(ids) != 1 or tokenizer.decode(ids, clean_up_tokenization_spaces=False) != piece:
            raise PilotRuntimeError("polarity_tokenization", f"{label} is not one exact token")
        yes_no[label] = ids[0]

    metadata = {
        "contract": protocol.G3_TOKENIZATION_CONTRACT,
        "groups": groups,
        "ordered_union_token_ids": ordered_ids,
        "yes_token_id": yes_no["Yes"],
        "no_token_id": yes_no["No"],
    }
    metadata["token_metadata_sha256"] = canonical_sha256(metadata)
    return metadata


def validate_contextual_yes_no(tokenizer: Any, context_ids: Sequence[int], metadata: Mapping[str, Any]) -> None:
    """Legacy helper retained for unit use; require the unspaced frozen IDs."""

    for label, field in (("Yes", "yes_token_id"), ("No", "no_token_id")):
        token_id = int(metadata[field])
        if token_id != protocol.G3P_ANSWER_TOKEN_IDS[label]:
            raise PilotRuntimeError(
                "polarity_contextual_tokenization",
                f"{label} does not use the frozen answer-boundary token ID",
            )


def _input_ids(rendered: Any) -> list[int]:
    if isinstance(rendered, Mapping):
        rendered = rendered.get("input_ids")
    if hasattr(rendered, "tolist"):
        rendered = rendered.tolist()
    if rendered and isinstance(rendered[0], list):
        if len(rendered) != 1:
            raise PilotRuntimeError("render_batch", "fixture rendering unexpectedly batched")
        rendered = rendered[0]
    if not isinstance(rendered, list) or not rendered:
        raise PilotRuntimeError("render_empty", "fixture rendered no tokens")
    return [int(value) for value in rendered]


def render_neutral_fixture(tokenizer: Any, prompt_id: str) -> tuple[list[int], dict[str, Any]]:
    prompt = next((row for row in protocol.neutral_prompts() if row["prompt_id"] == prompt_id), None)
    if prompt is None:
        raise PilotRuntimeError("fixture_id", f"unknown neutral fixture {prompt_id}")
    messages = [
        {"role": "system", "content": fixtures.NEUTRAL_INSTRUCTION},
        {"role": "user", "content": prompt["question"]},
    ]
    ids = _input_ids(tokenizer.apply_chat_template(messages, add_generation_prompt=True, tokenize=True))
    receipt = {
        "prompt_id": prompt_id,
        "canonical_prompt_sha256": prompt["canonical_prompt_sha256"],
        "token_ids_sha256": canonical_sha256(ids),
        "token_count": len(ids),
    }
    return ids, receipt


def render_semantic_fixture(
    tokenizer: Any, family: str, item_index: int
) -> tuple[list[int], dict[str, Any]]:
    row = next(
        (
            item
            for item in protocol.g3_fixture_rows()
            if item["family"] == family and item["cloze_index"] == item_index
        ),
        None,
    )
    if row is None:
        raise PilotRuntimeError("fixture_id", f"unknown semantic fixture {family}/{item_index}")
    render_contract = row["render_contract"]
    messages = [dict(message) for message in render_contract["messages"]]
    kwargs = dict(render_contract["apply_chat_template_kwargs"])
    ids = _input_ids(tokenizer.apply_chat_template(messages, **kwargs))
    receipt = {
        "fixture_id": row["fixture_id"],
        "family": family,
        "item_index": item_index,
        "render_mode": row["render_mode"],
        "render_contract_sha256": canonical_sha256(render_contract),
        "fixture_payload_sha256": canonical_sha256(
            {
                "instruction": row["instruction"],
                "stem": row["stem"],
                "render_mode": row["render_mode"],
            }
        ),
        "token_ids_sha256": canonical_sha256(ids),
        "token_count": len(ids),
    }
    return ids, receipt


def render_polarity_fixture(tokenizer: Any, prompt_id: str) -> tuple[list[int], dict[str, Any]]:
    row = next((item for item in protocol.g3p_plan_rows() if item["prompt_id"] == prompt_id), None)
    if row is None:
        raise PilotRuntimeError("fixture_id", f"unknown polarity fixture {prompt_id}")
    messages = [
        {"role": "system", "content": fixtures.POLARITY_INSTRUCTION},
        {"role": "user", "content": row["question"]},
    ]
    ids = _input_ids(tokenizer.apply_chat_template(messages, add_generation_prompt=True, tokenize=True))
    receipt = {
        "prompt_id": prompt_id,
        "expected_answer": row["expected_label"],
        "pair_id": row["pair_id"],
        "fixture_payload_sha256": canonical_sha256(
            {"instruction": row["instruction"], "question": row["question"]}
        ),
        "token_ids_sha256": canonical_sha256(ids),
        "token_count": len(ids),
    }
    return ids, receipt


@dataclass(frozen=True)
class G4Vector:
    assignment_id: str
    subset_feature_ids: tuple[int, ...]
    control_type: str
    sign: int
    coefficient: float
    raw_norm: float
    raw_vector_sha256: str
    norm_rescale: float
    final_norm: float
    norm_relative_error: float
    vector: Any
    vector_sha256: str
    vector_rms: float


def norm_match_bfloat16(control: Any, target: Any) -> tuple[Any, float, float, float, float]:
    """Apply one deterministic BF16 scalar so a control matches target norm."""

    torch = _torch()
    if not isinstance(control, torch.Tensor) or not isinstance(target, torch.Tensor):
        raise TypeError("G4 control and target must be torch tensors")
    if control.device.type != "cpu" or target.device.type != "cpu":
        raise PilotRuntimeError("g4_vector_device", "G4 vectors must be materialized on CPU")
    raw = control.to(dtype=torch.bfloat16).contiguous()
    reference = target.to(dtype=torch.bfloat16).contiguous()
    raw_norm = float(raw.float().norm().item())
    target_norm = float(reference.float().norm().item())
    if not math.isfinite(raw_norm) or not math.isfinite(target_norm) or raw_norm <= 0 or target_norm <= 0:
        raise PilotRuntimeError("g4_norm_match", "control or target norm is invalid")
    scalar = torch.tensor(target_norm / raw_norm, dtype=torch.bfloat16, device=raw.device)
    matched = (raw * scalar).to(dtype=torch.bfloat16).contiguous()
    observed = float(matched.float().norm().item())
    relative_error = abs(observed - target_norm) / target_norm
    if relative_error > protocol.G4_CONTROL_NORM_RELATIVE_ERROR_MAX:
        raise PilotRuntimeError("g4_norm_match", "single BF16 control norm match is outside tolerance")
    return (
        matched,
        float(scalar.float().item()),
        raw_norm,
        observed,
        relative_error,
    )


def aggregate_decoder_columns_bfloat16(
    decoder: Any, feature_ids: Sequence[int]
) -> Any:
    """Apply the frozen ordered CPU arithmetic for one coefficient-0.5 aggregate."""

    torch = _torch()
    if decoder.device.type != "cpu" or decoder.ndim != 2:
        raise PilotRuntimeError(
            "g4_vector_device", "the G4 decoder must be a two-dimensional CPU tensor"
        )
    ids = tuple(int(value) for value in feature_ids)
    if not ids or len(ids) != len(set(ids)):
        raise PilotRuntimeError("g4_feature_ids", "aggregate feature IDs are empty or duplicated")
    if min(ids) < 0 or max(ids) >= int(decoder.shape[1]):
        raise PilotRuntimeError("g4_feature_ids", "aggregate feature ID is outside the decoder")
    accumulator = torch.zeros(int(decoder.shape[0]), dtype=torch.float32, device="cpu")
    for feature_id in ids:
        accumulator.add_(
            decoder[:, feature_id].to(dtype=torch.bfloat16).to(dtype=torch.float32)
        )
    return accumulator.mul_(0.5).to(dtype=torch.bfloat16).contiguous()


def materialize_g4_vectors(
    decoder: Any,
    *,
    matched_feature_ids: Sequence[int],
) -> tuple[G4Vector, ...]:
    """Materialize all 300 vectors before any edited forward is possible."""

    import numpy as np

    torch = _torch()
    expected_shape = (protocol.MODEL_SPEC["residual_width"], protocol.SAE_SPEC["feature_count"])
    if tuple(decoder.shape) != expected_shape:
        raise PilotRuntimeError("sae_shape", f"decoder shape differs: {tuple(decoder.shape)}")
    if decoder.device.type != "cpu":
        raise PilotRuntimeError("g4_vector_device", "G4 decoder must remain on CPU")
    matched = tuple(int(value) for value in matched_feature_ids)
    if len(matched) != 6 or len(set(matched)) != 6:
        raise PilotRuntimeError("matched_ids", "exactly six unique matched IDs are required")
    if set(matched) & set(protocol.G4_TARGET_FEATURE_IDS):
        raise PilotRuntimeError("matched_ids", "matched IDs overlap target candidates")
    mapping = dict(zip(protocol.G4_TARGET_FEATURE_IDS, matched))
    vectors: list[G4Vector] = []
    for assignment in protocol.g4_aggregate_assignments():
        target_ids = tuple(int(value) for value in assignment["target_feature_ids"])
        positive_target = aggregate_decoder_columns_bfloat16(decoder, target_ids)
        matched_ids = tuple(mapping[value] for value in target_ids)
        raw_positive_matched = aggregate_decoder_columns_bfloat16(decoder, matched_ids)
        (
            positive_matched,
            matched_rescale,
            matched_raw_norm,
            matched_final_norm,
            matched_norm_error,
        ) = norm_match_bfloat16(
            raw_positive_matched, positive_target
        )
        seed = protocol.identity_bound_seed64("g4-isotropic-v1", assignment["assignment_id"])
        rng = np.random.Generator(np.random.PCG64(seed))
        values = rng.standard_normal(expected_shape[0]).astype(np.float32)
        values /= max(float(np.linalg.norm(values)), 1e-30)
        unit = torch.from_numpy(values).to(dtype=torch.bfloat16)
        (
            positive_isotropic,
            isotropic_rescale,
            isotropic_raw_norm,
            isotropic_final_norm,
            isotropic_norm_error,
        ) = norm_match_bfloat16(unit, positive_target)
        target_norm = float(positive_target.float().norm().item())
        for (
            control_type,
            positive,
            raw_positive,
            raw_norm,
            norm_rescale,
            final_norm,
            norm_error,
        ) in (
            (
                "target",
                positive_target,
                positive_target,
                target_norm,
                1.0,
                target_norm,
                0.0,
            ),
            (
                "matched",
                positive_matched,
                raw_positive_matched,
                matched_raw_norm,
                matched_rescale,
                matched_final_norm,
                matched_norm_error,
            ),
            (
                "isotropic",
                positive_isotropic,
                unit,
                isotropic_raw_norm,
                isotropic_rescale,
                isotropic_final_norm,
                isotropic_norm_error,
            ),
        ):
            for sign in protocol.G4_SIGNS:
                vector = positive.clone() if sign == 1 else torch.neg(positive).contiguous()
                raw_vector = (
                    raw_positive.clone()
                    if sign == 1
                    else torch.neg(raw_positive).contiguous()
                )
                if not bool(torch.isfinite(vector).all()) or not bool(
                    torch.isfinite(raw_vector).all()
                ):
                    raise PilotRuntimeError(
                        "g4_vector_nonfinite", "G4 raw or final vector is non-finite"
                    )
                vectors.append(
                    G4Vector(
                        assignment_id=assignment["assignment_id"],
                        subset_feature_ids=target_ids,
                        control_type=control_type,
                        sign=int(sign),
                        coefficient=0.5 * int(sign),
                        raw_norm=float(raw_norm),
                        raw_vector_sha256=tensor_sha256(raw_vector),
                        norm_rescale=float(norm_rescale),
                        final_norm=float(final_norm),
                        norm_relative_error=float(norm_error),
                        vector=vector,
                        vector_sha256=tensor_sha256(vector),
                        vector_rms=float(vector.float().norm().item()) / math.sqrt(vector.numel()),
                    )
                )
    if len(vectors) != 300 or len({row.vector_sha256 for row in vectors}) < 150:
        raise PilotRuntimeError("g4_vector_count", "G4 vector inventory is incomplete")
    return tuple(vectors)


@dataclass
class G4PreflightState:
    """Ordering state machine that makes an unsafe edited forward impossible."""

    vectors: tuple[G4Vector, ...] = ()
    clean_rms_by_prompt: dict[str, float] = field(default_factory=dict)
    vector_rows_persisted: bool = False
    edited_forward_count: int = 0
    authorized: bool = False

    def bind_vectors(self, vectors: Sequence[G4Vector]) -> None:
        if self.vectors or self.edited_forward_count:
            raise PilotRuntimeError("g4_order", "vectors cannot be rebound")
        if len(vectors) != 300:
            raise PilotRuntimeError("g4_vector_count", "preflight requires exactly 300 vectors")
        self.vectors = tuple(vectors)

    def record_clean_rms(self, prompt_id: str, value: float) -> None:
        if self.edited_forward_count or self.authorized:
            raise PilotRuntimeError("g4_order", "clean RMS arrived after edit authorization")
        if prompt_id in self.clean_rms_by_prompt:
            raise PilotRuntimeError("g4_clean_duplicate", f"duplicate clean RMS: {prompt_id}")
        if not math.isfinite(value) or value <= 0:
            raise PilotRuntimeError("g4_clean_rms", "clean RMS is invalid")
        self.clean_rms_by_prompt[prompt_id] = float(value)

    def mark_vector_rows_persisted(self) -> None:
        if len(self.vectors) != 300 or self.edited_forward_count:
            raise PilotRuntimeError("g4_order", "vector rows cannot yet be marked persisted")
        self.vector_rows_persisted = True

    def authorize_edits(self) -> None:
        if not self.vector_rows_persisted or len(self.clean_rms_by_prompt) != 32:
            raise PilotRuntimeError("g4_order", "G4 inventory/clean grid is incomplete")
        smallest = min(self.clean_rms_by_prompt.values())
        violating = [row for row in self.vectors if row.vector_rms / smallest > protocol.G4_RMS_RATIO_MAX]
        if violating:
            raise PilotRuntimeError(
                "g4_rms_preflight",
                f"{len(violating)} vectors exceed the frozen RMS safety ceiling",
            )
        self.authorized = True

    def begin_edited_forward(self) -> None:
        if not self.authorized:
            raise PilotRuntimeError("g4_order", "edited forward requested before full preflight")
        self.edited_forward_count += 1


def _reject_forbidden_binding_content(value: Any, *, location: str = "$") -> None:
    forbidden_keys = {"target_prompt", "target_prompts", "target_outcome", "target_outcomes"}
    if isinstance(value, Mapping):
        for key, child in value.items():
            if str(key).lower() in forbidden_keys:
                raise PilotRuntimeError("binding_forbidden", f"forbidden field at {location}.{key}")
            _reject_forbidden_binding_content(child, location=f"{location}.{key}")
    elif isinstance(value, (list, tuple)):
        for index, child in enumerate(value):
            _reject_forbidden_binding_content(child, location=f"{location}[{index}]")
    elif isinstance(value, str):
        normalized = value.lower().replace("\\", "/")
        for marker in protocol.public_input_allowlist()["forbidden_path_markers"]:
            if marker.lower() in normalized:
                raise PilotRuntimeError("binding_forbidden", f"prior-study marker at {location}")


def load_execution_binding(path: Path, *, plan_manifest_sha256: str) -> dict[str, Any]:
    try:
        binding = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PilotRuntimeError("binding_read", f"cannot read execution binding: {path}") from exc
    if not isinstance(binding, dict):
        raise PilotRuntimeError("binding_shape", "execution binding must be a JSON object")
    embedded_sha256(binding, "execution_binding_canonical_sha256")
    if binding.get("study_id") != protocol.STUDY_ID:
        raise PilotRuntimeError("binding_study", "execution binding study differs")
    if binding.get("protocol_version") != protocol.PROTOCOL_VERSION:
        raise PilotRuntimeError("binding_protocol", "execution binding protocol differs")
    if binding.get("plan_manifest_sha256") != plan_manifest_sha256:
        raise PilotRuntimeError("binding_plan", "execution binding plan hash differs")
    if binding.get("prior_outcome_inputs") not in ([], ()):
        raise PilotRuntimeError("binding_prior", "prior outcome inputs must be empty")
    if binding.get("target_prompt_inputs") not in ([], ()) or binding.get("target_outcome_inputs") not in ([], ()):
        raise PilotRuntimeError("binding_target", "target inputs must be empty")
    if binding.get("runtime_adapter") != "gpu_phase_adapter_v1":
        raise PilotRuntimeError("gpu_adapter_unresolved", "frozen GPU adapter is not bound")
    if not isinstance(binding.get("tokenizer_content_inventory_sha256"), str) or not HEX64.fullmatch(
        str(binding.get("tokenizer_content_inventory_sha256"))
    ):
        raise PilotRuntimeError("tokenizer_manifest", "tokenizer inventory hash is missing")
    _reject_forbidden_binding_content(binding)
    return binding


class PilotTransaction(AbstractContextManager["PilotTransaction"]):
    """Fresh external transaction with append-only JSONL and a hash manifest."""

    def __init__(
        self,
        *,
        artifact_root: Path,
        volume_id: str,
        phase: str,
        run_id: str,
        plan_manifest_sha256: str,
        execution_binding_canonical_sha256: str,
    ) -> None:
        if phase not in PHASE_TO_DIRECTORY or not SAFE_RUN_ID.fullmatch(run_id):
            raise PilotRuntimeError("transaction_identity", "phase or run ID is invalid")
        root = require_external_artifact_root(artifact_root, expected_volume_id=volume_id)
        phase_root = root / protocol.STUDY_SLUG / protocol.STUDY_ID / PHASE_TO_DIRECTORY[phase]
        self.final = phase_root / run_id
        self.partial = phase_root / f"{run_id}.partial"
        if self.final.exists() or self.partial.exists() or self.final.is_symlink() or self.partial.is_symlink():
            raise PilotRuntimeError("transaction_exists", "pilot transaction path is not fresh")
        phase_root.mkdir(parents=True, exist_ok=True)
        self.partial.mkdir()
        self.phase = phase
        self.run_id = run_id
        self.plan_manifest_sha256 = plan_manifest_sha256
        self.execution_binding_canonical_sha256 = execution_binding_canonical_sha256
        self.counts = {filename: 0 for filename in ROW_FILENAMES[phase]}
        self.closed = False
        self._write_json(
            "RUN_STARTED.json",
            {
                "schema_version": 1,
                "study_id": protocol.STUDY_ID,
                "protocol_version": protocol.PROTOCOL_VERSION,
                "phase": phase,
                "run_id": run_id,
                "plan_manifest_sha256": plan_manifest_sha256,
                "execution_binding_canonical_sha256": execution_binding_canonical_sha256,
                "started_at_utc": utc_now(),
                "target_prompt_inputs": [],
                "target_outcome_inputs": [],
                "prior_outcome_inputs": [],
            },
        )

    def _write_json(self, filename: str, value: Mapping[str, Any]) -> None:
        path = self.partial / filename
        if path.exists():
            raise PilotRuntimeError("transaction_overwrite", f"refusing to overwrite {filename}")
        with path.open("xb") as handle:
            handle.write(canonical_json_bytes(value) + b"\n")
            handle.flush()
            os.fsync(handle.fileno())

    def append(self, filename: str, row: Mapping[str, Any]) -> None:
        if self.closed or filename not in self.counts:
            raise PilotRuntimeError("transaction_row", f"unregistered row file {filename}")
        enriched = {
            "study_id": protocol.STUDY_ID,
            "protocol_version": protocol.PROTOCOL_VERSION,
            "plan_manifest_sha256": self.plan_manifest_sha256,
            "run_id": self.run_id,
            **dict(row),
        }
        if "task_id" not in enriched:
            enriched["task_id"] = protocol.stable_id(
                "measurement",
                {
                    "phase": self.phase,
                    "filename": filename,
                    "measurement": dict(row),
                },
            )
        if "row_id" not in enriched:
            enriched["row_id"] = stable_row_id(
                self.phase, self.run_id, filename, self.counts[filename], canonical_sha256(row)
            )
        with (self.partial / filename).open("ab") as handle:
            handle.write(canonical_json_bytes(enriched) + b"\n")
            handle.flush()
            os.fsync(handle.fileno())
        self.counts[filename] += 1

    def write_metadata(self, filename: str, value: Mapping[str, Any]) -> None:
        """Durably write a non-row receipt inside the active transaction."""

        if self.closed or filename in self.counts or not filename.endswith(".json"):
            raise PilotRuntimeError("transaction_metadata", "metadata filename is invalid")
        if filename in {"RUN_STARTED.json", "RUN_COMPLETE.json", "RUN_FAILED.json", "FILE_MANIFEST.json"}:
            raise PilotRuntimeError("transaction_metadata", "metadata filename is reserved")
        self._write_json(filename, value)

    def _manifest(self) -> dict[str, Any]:
        files = []
        for path in sorted(item for item in self.partial.iterdir() if item.is_file()):
            if path.name == "FILE_MANIFEST.json":
                continue
            files.append({"path": path.name, "bytes": path.stat().st_size, "sha256": sha256_file(path)})
        manifest = {
            "schema_version": 1,
            "study_id": protocol.STUDY_ID,
            "phase": self.phase,
            "run_id": self.run_id,
            "plan_manifest_sha256": self.plan_manifest_sha256,
            "execution_binding_canonical_sha256": self.execution_binding_canonical_sha256,
            "row_counts": self.counts,
            "files": files,
        }
        manifest["manifest_sha256"] = canonical_sha256(manifest)
        return manifest

    def complete(self) -> Path:
        if self.closed:
            raise PilotRuntimeError("transaction_closed", "transaction is already closed")
        self._write_json(
            "RUN_COMPLETE.json",
            {
                "schema_version": 1,
                "study_id": protocol.STUDY_ID,
                "phase": self.phase,
                "run_id": self.run_id,
                "completed_at_utc": utc_now(),
                "row_counts": self.counts,
                "analysis_decisions": [],
            },
        )
        self._write_json("FILE_MANIFEST.json", self._manifest())
        os.replace(self.partial, self.final)
        self.closed = True
        return self.final

    def fail(self, exc: BaseException) -> None:
        if self.closed:
            return
        value = {
            "schema_version": 1,
            "study_id": protocol.STUDY_ID,
            "phase": self.phase,
            "run_id": self.run_id,
            "failed_at_utc": utc_now(),
            "error_type": type(exc).__name__,
            "error_code": getattr(exc, "code", "unclassified"),
            "error_message": str(exc),
            "row_counts": self.counts,
            "retry_authorized": False,
        }
        try:
            self._write_json("RUN_FAILED.json", value)
        finally:
            self.closed = True

    def __enter__(self) -> "PilotTransaction":
        return self

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> bool:
        if exc is not None:
            self.fail(exc)
        elif not self.closed:
            self.complete()
        return False


def verify_completed_transaction(
    directory: Path,
    *,
    phase: str,
    run_id: str,
    plan_manifest_sha256: str,
    execution_binding_canonical_sha256: str,
) -> dict[str, Any]:
    """Verify a completed transaction and return its still-enveloped row files.

    This is the only bridge from runtime JSONL to pure analysis.  It validates
    the manifest, exact file bytes, row counts, and run lineage before analysis
    is allowed to strip the envelope with ``unwrap_measurement_rows``.
    """

    if phase not in ROW_FILENAMES or not SAFE_RUN_ID.fullmatch(run_id):
        raise PilotRuntimeError("transaction_identity", "phase or run ID is invalid")
    root = directory.resolve(strict=True)
    if root.name != run_id or root.is_symlink() or not root.is_dir():
        raise PilotRuntimeError("transaction_path", "completed transaction path is unsafe")
    manifest_path = root / "FILE_MANIFEST.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PilotRuntimeError("transaction_manifest", "manifest cannot be read") from exc
    if not isinstance(manifest, dict):
        raise PilotRuntimeError("transaction_manifest", "manifest is not an object")
    observed_manifest_hash = manifest.get("manifest_sha256")
    core = dict(manifest)
    core.pop("manifest_sha256", None)
    if not isinstance(observed_manifest_hash, str) or observed_manifest_hash != canonical_sha256(core):
        raise PilotRuntimeError("transaction_manifest", "manifest self-hash differs")
    expected_identity = {
        "study_id": protocol.STUDY_ID,
        "phase": phase,
        "run_id": run_id,
        "plan_manifest_sha256": plan_manifest_sha256,
        "execution_binding_canonical_sha256": execution_binding_canonical_sha256,
    }
    if any(manifest.get(key) != value for key, value in expected_identity.items()):
        raise PilotRuntimeError("transaction_lineage", "manifest lineage differs")
    counts = manifest.get("row_counts")
    if not isinstance(counts, Mapping) or set(counts) != set(ROW_FILENAMES[phase]):
        raise PilotRuntimeError("transaction_counts", "manifest row inventory differs")
    file_rows = manifest.get("files")
    if not isinstance(file_rows, list) or not file_rows:
        raise PilotRuntimeError("transaction_manifest", "manifest file inventory is empty")
    listed: set[str] = set()
    for record in file_rows:
        if not isinstance(record, Mapping) or not isinstance(record.get("path"), str):
            raise PilotRuntimeError("transaction_manifest", "manifest file row is malformed")
        name = str(record["path"])
        if name in listed or Path(name).name != name or name == "FILE_MANIFEST.json":
            raise PilotRuntimeError("transaction_manifest", "manifest file name is invalid")
        listed.add(name)
        candidate = (root / name).resolve(strict=True)
        try:
            candidate.relative_to(root)
        except ValueError as exc:
            raise PilotRuntimeError("transaction_manifest", "manifest file escapes run") from exc
        if candidate.is_symlink() or not candidate.is_file():
            raise PilotRuntimeError("transaction_manifest", "manifest file is unsafe")
        if candidate.stat().st_size != record.get("bytes") or sha256_file(candidate) != record.get(
            "sha256"
        ):
            raise PilotRuntimeError("transaction_manifest", f"file differs: {name}")
    actual = {item.name for item in root.iterdir() if item.is_file()}
    if actual != listed | {"FILE_MANIFEST.json"}:
        raise PilotRuntimeError("transaction_manifest", "unlisted or missing transaction file")
    if not {"RUN_STARTED.json", "RUN_COMPLETE.json"}.issubset(listed) or "RUN_FAILED.json" in listed:
        raise PilotRuntimeError("transaction_state", "transaction is not cleanly complete")

    loaded: dict[str, list[dict[str, Any]]] = {}
    measurement_files: dict[str, dict[str, Any]] = {}
    for filename in ROW_FILENAMES[phase]:
        rows: list[dict[str, Any]] = []
        path = root / filename
        if not path.is_file():
            if int(counts[filename]) != 0:
                raise PilotRuntimeError("transaction_counts", f"missing nonempty {filename}")
            loaded[filename] = rows
            measurement_files[filename] = {
                "row_count": 0,
                "content_sha256": hashlib.sha256(b"").hexdigest(),
                "logical_rows_sha256": canonical_sha256(rows),
            }
            continue
        with path.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                try:
                    row = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise PilotRuntimeError(
                        "transaction_jsonl", f"invalid {filename}:{line_number}"
                    ) from exc
                if not isinstance(row, dict):
                    raise PilotRuntimeError("transaction_jsonl", "measurement row is not an object")
                rows.append(row)
        if len(rows) != int(counts[filename]):
            raise PilotRuntimeError("transaction_counts", f"row count differs: {filename}")
        loaded[filename] = rows
        measurement_files[filename] = {
            "row_count": len(rows),
            "content_sha256": sha256_file(path),
            "logical_rows_sha256": canonical_sha256(rows),
        }
    receipt_core = {
        "schema_version": 1,
        "status": "pass",
        "authorization_kind": "manifest_verified_measurement_envelopes_v1",
        "study_id": protocol.STUDY_ID,
        "protocol_version": protocol.PROTOCOL_VERSION,
        "phase": phase,
        "run_id": run_id,
        "plan_manifest_sha256": plan_manifest_sha256,
        "execution_binding_canonical_sha256": execution_binding_canonical_sha256,
        "file_manifest_content_sha256": sha256_file(manifest_path),
        "file_manifest_embedded_sha256": observed_manifest_hash,
        "measurement_files": measurement_files,
    }
    receipt = {**receipt_core, "receipt_sha256": canonical_sha256(receipt_core)}
    return {"receipt": receipt, "rows": loaded}


def validate_local_artifact_binding(
    binding: Mapping[str, Any],
    *,
    artifact_root: Path,
    volume_id: str,
) -> dict[str, Path]:
    """Resolve and hash local artifacts without loading model weights."""

    artifacts = binding.get("artifacts")
    if not isinstance(artifacts, Mapping):
        raise PilotRuntimeError("binding_artifacts", "artifact mapping is missing")
    resolved: dict[str, Path] = {}
    for name in ("model_snapshot", "sae", "j_lens"):
        record = artifacts.get(name)
        if not isinstance(record, Mapping) or not isinstance(record.get("path"), str):
            raise PilotRuntimeError("binding_artifacts", f"{name} binding is incomplete")
        candidate = require_public_artifact_input(
            Path(record["path"]), root=artifact_root, expected_volume_id=volume_id
        )
        resolved[name] = candidate
        expected_repository = (
            protocol.MODEL_SPEC["repository"]
            if name == "model_snapshot"
            else protocol.SAE_SPEC["repository"]
            if name == "sae"
            else protocol.J_LENS_SPEC["repository"]
        )
        expected_revision = (
            protocol.MODEL_SPEC["revision"]
            if name == "model_snapshot"
            else protocol.SAE_SPEC["revision"]
            if name == "sae"
            else protocol.J_LENS_SPEC["revision"]
        )
        if record.get("repository") != expected_repository or record.get("revision") != expected_revision:
            raise PilotRuntimeError("artifact_identity", f"{name} repository/revision differs")
        if name != "model_snapshot":
            expected = record.get("sha256")
            frozen = protocol.SAE_SPEC["sha256"] if name == "sae" else protocol.J_LENS_SPEC["sha256"]
            if expected != frozen or sha256_file(candidate) != frozen:
                raise PilotRuntimeError("artifact_hash", f"{name} SHA-256 differs")
    sae_record = artifacts["sae"]
    for sidecar_name in ("readme", "config"):
        frozen_sidecar = protocol.SAE_SPEC["sidecars"][sidecar_name]
        path_field = f"{sidecar_name}_path"
        filename_field = f"{sidecar_name}_filename"
        sha_field = f"{sidecar_name}_sha256"
        if (
            not isinstance(sae_record.get(path_field), str)
            or sae_record.get(filename_field) != frozen_sidecar["filename"]
            or sae_record.get(sha_field) != frozen_sidecar["sha256"]
        ):
            raise PilotRuntimeError(
                "artifact_identity", f"SAE {sidecar_name} binding differs"
            )
        resolved_sidecar = require_public_artifact_input(
            Path(str(sae_record[path_field])),
            root=artifact_root,
            expected_volume_id=volume_id,
        )
        if (
            not resolved_sidecar.is_file()
            or sha256_file(resolved_sidecar) != frozen_sidecar["sha256"]
        ):
            raise PilotRuntimeError(
                "artifact_hash", f"SAE {sidecar_name} SHA-256 differs"
            )
        resolved[f"sae_{sidecar_name}"] = resolved_sidecar

    j_record = artifacts["j_lens"]
    release_config = protocol.J_LENS_SPEC["release_config"]
    if (
        not isinstance(j_record.get("config_path"), str)
        or j_record.get("config_filename") != release_config["filename"]
        or j_record.get("config_sha256") != release_config["sha256"]
    ):
        raise PilotRuntimeError("artifact_identity", "J-lens config binding differs")
    resolved_j_config = require_public_artifact_input(
        Path(str(j_record["config_path"])),
        root=artifact_root,
        expected_volume_id=volume_id,
    )
    if (
        not resolved_j_config.is_file()
        or sha256_file(resolved_j_config) != release_config["sha256"]
    ):
        raise PilotRuntimeError("artifact_hash", "J-lens config SHA-256 differs")
    resolved["j_lens_config"] = resolved_j_config
    snapshot_files = artifacts["model_snapshot"].get("files")
    if not isinstance(snapshot_files, list) or not snapshot_files:
        raise PilotRuntimeError("model_manifest", "model snapshot file inventory is missing")
    snapshot = resolved["model_snapshot"]
    for row in snapshot_files:
        if not isinstance(row, Mapping) or not isinstance(row.get("path"), str):
            raise PilotRuntimeError("model_manifest", "model file row is malformed")
        path = (snapshot / row["path"]).resolve(strict=True)
        try:
            path.relative_to(snapshot.resolve(strict=True))
        except ValueError as exc:
            raise PilotRuntimeError("model_manifest", "model file escapes snapshot") from exc
        if path.is_symlink() or not path.is_file() or sha256_file(path) != row.get("sha256"):
            raise PilotRuntimeError("model_manifest", f"model file differs: {row['path']}")
    inventory_rows = [
        {"path": str(row["path"]), "sha256": str(row["sha256"])}
        for row in snapshot_files
    ]
    observed_inventory = canonical_sha256(inventory_rows)
    if artifacts["model_snapshot"].get("file_inventory_sha256") != observed_inventory:
        raise PilotRuntimeError("model_manifest", "model file inventory hash differs")
    tokenizer_rows = [
        row
        for row in inventory_rows
        if Path(row["path"]).name
        in {
            "tokenizer.json",
            "tokenizer_config.json",
            "special_tokens_map.json",
            "added_tokens.json",
            "generation_config.json",
        }
    ]
    if not tokenizer_rows:
        raise PilotRuntimeError("tokenizer_manifest", "tokenizer file inventory is empty")
    tokenizer_inventory = canonical_sha256(tokenizer_rows)
    if binding.get("tokenizer_content_inventory_sha256") != tokenizer_inventory:
        raise PilotRuntimeError("tokenizer_manifest", "tokenizer inventory hash differs")
    return resolved


def tokenizer_preflight(
    model_snapshot: Path,
    *,
    plan_manifest_sha256: str,
    tokenizer_inventory_sha256: str,
) -> tuple[Any, dict[str, Any]]:
    """Load only tokenizer assets and produce the fresh exact audit receipt."""

    try:
        from transformers import AutoTokenizer
    except ImportError as exc:  # pragma: no cover - GPU environment only
        raise PilotRuntimeError("transformers_missing", "Transformers is required") from exc
    tokenizer = AutoTokenizer.from_pretrained(
        model_snapshot,
        local_files_only=True,
        trust_remote_code=False,
        use_fast=True,
    )
    semantic_boundaries: list[dict[str, Any]] = []
    semantic_labels = tuple(
        token
        for family in protocol.G3_FAMILIES
        for token in protocol.G3_TOKEN_GROUPS[family]
    )
    for row in protocol.g3_fixture_rows():
        ids, _receipt = render_semantic_fixture(
            tokenizer, str(row["family"]), int(row["cloze_index"])
        )
        contract = row["render_contract"]
        full_by_token: dict[str, list[int]] = {}
        for token in semantic_labels:
            messages = [dict(message) for message in contract["messages"]]
            if not messages or messages[-1].get("role") != "assistant":
                raise PilotRuntimeError("semantic_render", "prefill lacks final assistant message")
            messages[-1]["content"] = str(messages[-1]["content"]) + f" {token}"
            full_by_token[token] = _input_ids(
                tokenizer.apply_chat_template(
                    messages, **dict(contract["apply_chat_template_kwargs"])
                )
            )
        semantic_boundaries.append(
            {
                "fixture_id": row["fixture_id"],
                "context_ids": ids,
                "full_ids_by_token": full_by_token,
            }
        )
    boundaries: list[dict[str, Any]] = []
    for row in protocol.g3p_plan_rows():
        ids, _receipt = render_polarity_fixture(tokenizer, row["prompt_id"])
        base_messages = [
            {"role": "system", "content": fixtures.POLARITY_INSTRUCTION},
            {"role": "user", "content": row["question"]},
        ]
        full_ids_by_answer = {
            answer: _input_ids(
                tokenizer.apply_chat_template(
                    [*base_messages, {"role": "assistant", "content": answer}],
                    add_generation_prompt=False,
                    tokenize=True,
                )
            )
            for answer in ("Yes", "No")
        }
        boundaries.append(
            {
                "prompt_id": row["prompt_id"],
                "context_ids": ids,
                "full_ids_by_answer": full_ids_by_answer,
            }
        )
    try:
        receipt = tokenizer_audit.audit_tokenizer(
            tokenizer,
            tokenizer_repository=protocol.MODEL_SPEC["repository"],
            tokenizer_revision=protocol.MODEL_SPEC["revision"],
            plan_manifest_sha256=plan_manifest_sha256,
            contextual_boundaries=boundaries,
            semantic_contextual_boundaries=semantic_boundaries,
            tokenizer_inventory_sha256=tokenizer_inventory_sha256,
        )
    except tokenizer_audit.TokenizerAuditError as exc:
        raise PilotRuntimeError(exc.code, exc.message) from exc
    return tokenizer, receipt


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", choices=tuple(PHASE_TO_DIRECTORY), required=True)
    parser.add_argument("--plan-manifest", type=Path, required=True)
    parser.add_argument("--execution-binding", type=Path, required=True)
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--volume-id", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument(
        "--preflight-only",
        action="store_true",
        help="Validate bindings/artifacts/tokenization without loading 70B weights.",
    )
    return parser.parse_args(argv)


def _load_plan_manifest(path: Path) -> tuple[dict[str, Any], str]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PilotRuntimeError("plan_read", f"cannot read plan manifest: {path}") from exc
    if not isinstance(value, dict) or value.get("study_id") != protocol.STUDY_ID:
        raise PilotRuntimeError("plan_study", "plan manifest study differs")
    if value.get("protocol_version") != protocol.PROTOCOL_VERSION:
        raise PilotRuntimeError("plan_protocol", "plan manifest protocol differs")
    manifest_hash = value.get("plan_manifest_sha256")
    if not isinstance(manifest_hash, str) or not HEX64.fullmatch(manifest_hash):
        raise PilotRuntimeError("plan_hash", "plan_manifest_sha256 is missing")
    core = dict(value)
    del core["plan_manifest_sha256"]
    if canonical_sha256(core) != manifest_hash:
        raise PilotRuntimeError("plan_hash", "plan manifest hash does not reconstruct")
    files = value.get("files")
    if not isinstance(files, list) or not files:
        raise PilotRuntimeError("plan_files", "plan file inventory is missing")
    plan_root = path.resolve(strict=True).parent
    for record in files:
        if not isinstance(record, Mapping) or not isinstance(record.get("filename"), str):
            raise PilotRuntimeError("plan_files", "plan file row is malformed")
        candidate = (plan_root / record["filename"]).resolve(strict=True)
        try:
            candidate.relative_to(plan_root)
        except ValueError as exc:
            raise PilotRuntimeError("plan_files", "plan file escapes plan directory") from exc
        if not candidate.is_file() or candidate.is_symlink():
            raise PilotRuntimeError("plan_files", "plan file is unsafe")
        if candidate.stat().st_size != record.get("size_bytes") or sha256_file(candidate) != record.get(
            "content_sha256"
        ):
            raise PilotRuntimeError("plan_files", f"plan file differs: {record['filename']}")
    return value, manifest_hash


def main(argv: Sequence[str] | None = None) -> int:
    """Run the model-free artifact/tokenizer preflight entry point."""

    args = parse_args(argv)
    _manifest, plan_hash = _load_plan_manifest(args.plan_manifest)
    binding = load_execution_binding(args.execution_binding, plan_manifest_sha256=plan_hash)
    if binding.get("resolved_external_root_id") != args.volume_id:
        raise PilotRuntimeError("binding_volume", "execution binding volume differs")
    resolved = validate_local_artifact_binding(
        binding, artifact_root=args.artifact_root, volume_id=args.volume_id
    )
    _tokenizer, token_receipt = tokenizer_preflight(
        resolved["model_snapshot"],
        plan_manifest_sha256=plan_hash,
        tokenizer_inventory_sha256=str(binding["tokenizer_content_inventory_sha256"]),
    )
    if args.preflight_only:
        print(
            json.dumps(
                {
                    "status": "preflight_pass",
                    "study_id": protocol.STUDY_ID,
                    "phase": args.phase,
                    "plan_manifest_sha256": plan_hash,
                    "execution_binding_canonical_sha256": binding[
                        "execution_binding_canonical_sha256"
                    ],
                    "tokenizer_audit_receipt_sha256": token_receipt["receipt_sha256"],
                    "g1_token_panel_sha256": token_receipt["g1"][
                        "token_panel_canonical_sha256"
                    ],
                    "model_weights_loaded": False,
                    "model_forward_count": 0,
                },
                sort_keys=True,
            )
        )
        return 0
    raise PilotRuntimeError(
        "entrypoint_scope",
        "runtime.py is the model-free preflight; execute the bound gpu_runner entry point",
    )


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

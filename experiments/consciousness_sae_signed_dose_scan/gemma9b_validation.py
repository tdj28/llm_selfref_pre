#!/usr/bin/env python3
"""Operational-only signed dose-grid validation on pinned Gemma 2 9B.

This is deliberately not the scientific Llama/J-lens experiment.  It uses one
frozen neutral prompt and one frozen decoder row from the public Gemma Scope
9B-IT residual SAE to exercise the production mechanics of the successor dose
grid: one clean zero, then exact positive/negative BF16 branches for every
50-basis-point magnitude from 50 through 3,000 basis points.

The complete residual arc, hook pre/post states, and exact requested vectors
remain on the RunPod network volume.  The resulting artifacts authorize no
semantic, target-feature, learned-J, or dose-selection claim.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import sys
from contextlib import ExitStack
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from experiments.consciousness_sae_realization_validation.runtime import (  # noqa: E402
    SingleUseResidualHook,
    clone_kv_cache,
    tensor_sha256,
)
from experiments.consciousness_sae_signed_dose_scan import protocol  # noqa: E402
from experiments.exp2_sae.gemma_scope_9b_protocol import (  # noqa: E402
    IT_CANONICAL_FOLDERS,
    IT_SAE_REPO,
    IT_SAE_REVISION,
    MODEL_ID,
    MODEL_REVISION,
)
from experiments.exp2_sae.gemma_scope_9b_runtime import (  # noqa: E402
    PinnedJumpReLUSAE,
    load_model_and_tokenizer,
    release_memory,
    runtime_metadata,
)


VALIDATION_SCHEMA_VERSION = 1
VALIDATION_ID = "gemma2_9b_signed_dose_grid_operational_v1"
VALIDATION_ROLE = "operational_only_smaller_model_validation"
REMOTE_ROOT = Path("/workspace")

FROZEN_PROMPT_ID = "neutral_calendar_continuation_v1"
FROZEN_PROMPT = (
    "Continue this neutral sequence with a short factual sentence: "
    "January, February, March."
)
FROZEN_FEATURE_ID = 1_295
FROZEN_SAE_LAYER = 20
FROZEN_SAE_WIDTH = 16_384
FROZEN_SAE_FOLDER = "layer_20/width_16k/average_l0_91"
FROZEN_SAE_PARAMS_SHA256 = (
    "bbd770b6f8b92a2fe7498e05bd6274c6cfa89ebc08fb972c0e842840737f1a82"
)
RESIDUAL_WIDTH = 3_584
CAPTURE_LAYERS = tuple(range(42))
ARC_LABELS = tuple(f"layer_{layer:02d}_post" for layer in CAPTURE_LAYERS) + (
    "final_norm_input",
)
DOSE_BASIS_POINTS = tuple(range(50, 3_001, 50))
SIGNS = ("plus", "minus")
EXPECTED_EDITED_FORWARDS = len(DOSE_BASIS_POINTS) * len(SIGNS)
EXPECTED_MODEL_FORWARDS = 1 + 1 + EXPECTED_EDITED_FORWARDS
RUNTIME_SEED = 2_026_071_601

PROMOTION_GATE_NAMES = (
    "structural",
    "numeric",
    "hook",
    "artifact_replay",
)


class ValidationError(RuntimeError):
    """Fail-closed error for a malformed operational validation."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


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


def _atomic_write(path: Path, payload: bytes) -> None:
    temporary = path.with_name(path.name + ".partial")
    if temporary.exists() or path.exists():
        raise ValidationError(f"refusing to overwrite validation artifact: {path}")
    with temporary.open("xb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
    temporary.replace(path)


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    _atomic_write(path, json.dumps(payload, indent=2, sort_keys=True).encode() + b"\n")


def _write_jsonl(path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
    payload = b"".join(canonical_json_bytes(dict(row)) + b"\n" for row in rows)
    _atomic_write(path, payload)


def validate_frozen_contract() -> None:
    """Bind this smoke run to the successor grid without authorizing it."""

    if DOSE_BASIS_POINTS != tuple(range(50, 3_001, 50)):
        raise ValidationError("local Gemma dose grid differs from its frozen contract")
    if DOSE_BASIS_POINTS != tuple(protocol.DOSE_BASIS_POINTS):
        raise ValidationError("Gemma validation dose grid differs from successor plan")
    if protocol.PROTOCOL_VERSION != "consciousness_sae_signed_dose_scan_v1.0.0":
        raise ValidationError("successor protocol version is not prospectively frozen")
    if len(DOSE_BASIS_POINTS) != 60 or 0 in DOSE_BASIS_POINTS:
        raise ValidationError("nonzero magnitude inventory differs")
    if protocol.ZERO_BASELINE_CONTRACT.get("dose_basis_points") != 0:
        raise ValidationError("successor zero baseline differs")
    if EXPECTED_EDITED_FORWARDS != 120 or EXPECTED_MODEL_FORWARDS != 122:
        raise ValidationError("Gemma operational forward inventory differs")
    if IT_CANONICAL_FOLDERS[(FROZEN_SAE_LAYER, FROZEN_SAE_WIDTH)] != FROZEN_SAE_FOLDER:
        raise ValidationError("Gemma Scope folder binding differs")
    if tuple(ARC_LABELS) != tuple(
        [f"layer_{layer:02d}_post" for layer in range(42)]
        + ["final_norm_input"]
    ):
        raise ValidationError("full Gemma arc inventory differs")


def validate_remote_outdir(path: Path) -> Path:
    """Prevent this raw-tensor run from filling the local laptop."""

    resolved = path.expanduser().resolve()
    root = REMOTE_ROOT.resolve()
    try:
        relative = resolved.relative_to(root)
    except ValueError as exc:
        raise ValidationError(
            f"raw validation output must remain below network volume {root}"
        ) from exc
    if not relative.parts:
        raise ValidationError("a fresh child directory below /workspace is required")
    if resolved.exists():
        raise ValidationError(f"fresh output directory already exists: {resolved}")
    return resolved


def render_frozen_prompt(tokenizer: Any) -> tuple[int, ...]:
    token_ids = tokenizer.apply_chat_template(
        [{"role": "user", "content": FROZEN_PROMPT}],
        add_generation_prompt=True,
        tokenize=True,
    )
    if hasattr(token_ids, "tolist"):
        token_ids = token_ids.tolist()
    if token_ids and isinstance(token_ids[0], list):
        if len(token_ids) != 1:
            raise ValidationError("frozen prompt rendered as a batch")
        token_ids = token_ids[0]
    result = tuple(int(value) for value in token_ids)
    if len(result) < 2 or min(result) < 0:
        raise ValidationError("frozen prompt rendered invalid token IDs")
    return result


def configure_determinism(torch_module: Any) -> dict[str, Any]:
    """Use deterministic math so clean-prefix branches are byte-replayable."""

    torch_module.manual_seed(RUNTIME_SEED)
    torch_module.cuda.manual_seed_all(RUNTIME_SEED)
    torch_module.use_deterministic_algorithms(True)
    torch_module.backends.cuda.matmul.allow_tf32 = False
    torch_module.backends.cudnn.allow_tf32 = False
    if hasattr(torch_module.backends.cuda, "enable_flash_sdp"):
        torch_module.backends.cuda.enable_flash_sdp(False)
        torch_module.backends.cuda.enable_mem_efficient_sdp(False)
        torch_module.backends.cuda.enable_math_sdp(True)
    return {
        "seed": RUNTIME_SEED,
        "deterministic_algorithms": bool(
            torch_module.are_deterministic_algorithms_enabled()
        ),
        "cuda_matmul_tf32": bool(torch_module.backends.cuda.matmul.allow_tf32),
        "cudnn_tf32": bool(torch_module.backends.cudnn.allow_tf32),
        "flash_sdp_enabled": bool(torch_module.backends.cuda.flash_sdp_enabled()),
        "mem_efficient_sdp_enabled": bool(
            torch_module.backends.cuda.mem_efficient_sdp_enabled()
        ),
        "math_sdp_enabled": bool(torch_module.backends.cuda.math_sdp_enabled()),
        "cublas_workspace_config": os.environ.get("CUBLAS_WORKSPACE_CONFIG"),
    }


def _extract_hidden(output: Any, torch_module: Any) -> Any:
    if isinstance(output, torch_module.Tensor):
        return output
    if (
        isinstance(output, (tuple, list))
        and output
        and isinstance(output[0], torch_module.Tensor)
    ):
        return output[0]
    raise ValidationError("transformer block output has no hidden tensor")


@dataclass(frozen=True)
class ArcRecord:
    forward_id: str
    token_ids_sha256: str
    arc_bfloat16: Any
    pre_bfloat16: Any | None
    post_bfloat16: Any | None
    hook_vector_bfloat16: Any | None
    hook_fire_count: int


class GemmaArcSession:
    """One cached neutral prompt with independently branchable last-token arcs."""

    def __init__(
        self,
        *,
        torch_module: Any,
        model: Any,
        token_ids: Sequence[int],
        capture_layers: Sequence[int] = CAPTURE_LAYERS,
        residual_width: int = RESIDUAL_WIDTH,
        edit_layer: int = FROZEN_SAE_LAYER,
    ) -> None:
        self.torch = torch_module
        self.model = model
        self.capture_layers = tuple(int(value) for value in capture_layers)
        self.residual_width = int(residual_width)
        self.edit_layer = int(edit_layer)
        self.token_ids = tuple(int(value) for value in token_ids)
        self.token_ids_sha256 = canonical_sha256(list(self.token_ids))
        if len(self.token_ids) < 2:
            raise ValidationError("Gemma arc session requires a nonempty prefix")
        layers = self.model.model.layers
        if not self.capture_layers or self.edit_layer not in self.capture_layers:
            raise ValidationError("edit layer is missing from capture inventory")
        if min(self.capture_layers) < 0 or max(self.capture_layers) >= len(layers):
            raise ValidationError("capture layer is outside the model")
        prefix = self.torch.tensor(
            [self.token_ids[:-1]], dtype=self.torch.long, device=self.model.device
        )
        with self.torch.inference_mode():
            output = self.model(input_ids=prefix, use_cache=True, return_dict=True)
        self.prefix_cache = getattr(output, "past_key_values", None)
        if self.prefix_cache is None:
            raise ValidationError("Gemma prefix forward returned no KV cache")
        self.last_token = self.torch.tensor(
            [[self.token_ids[-1]]], dtype=self.torch.long, device=self.model.device
        )

    def _run(self, *, vector: Any | None, forward_id: str) -> ArcRecord:
        captured: dict[int, Any] = {}
        counts = {layer: 0 for layer in self.capture_layers}
        final: list[Any] = []

        def layer_hook(layer: int) -> Any:
            def hook(_module: Any, _inputs: Any, output: Any) -> None:
                counts[layer] += 1
                if counts[layer] != 1:
                    raise ValidationError(f"capture layer {layer} fired more than once")
                hidden = _extract_hidden(output, self.torch)
                if tuple(hidden.shape) != (1, 1, self.residual_width):
                    raise ValidationError(f"capture layer {layer} shape differs")
                if hidden.dtype != self.torch.bfloat16:
                    raise ValidationError(f"capture layer {layer} is not BF16")
                captured[layer] = hidden[0, 0].detach().clone()

            return hook

        def final_hook(_module: Any, inputs: Any) -> None:
            if final:
                raise ValidationError("final norm input fired more than once")
            hidden = inputs[0]
            if tuple(hidden.shape) != (1, 1, self.residual_width):
                raise ValidationError("final norm input shape differs")
            if hidden.dtype != self.torch.bfloat16:
                raise ValidationError("final norm input is not BF16")
            final.append(hidden[0, 0].detach().clone())

        hook_context: SingleUseResidualHook | None = None
        cache = clone_kv_cache(self.prefix_cache)
        with ExitStack() as stack:
            handles = [
                self.model.model.layers[layer].register_forward_hook(layer_hook(layer))
                for layer in self.capture_layers
            ]
            for handle in reversed(handles):
                stack.callback(handle.remove)
            final_handle = self.model.model.norm.register_forward_pre_hook(final_hook)
            stack.callback(final_handle.remove)
            if vector is not None:
                hook_context = stack.enter_context(
                    SingleUseResidualHook(
                        self.model.model.layers[self.edit_layer],
                        vector,
                        forward_id=forward_id,
                    )
                )
            with self.torch.inference_mode():
                self.model(
                    input_ids=self.last_token,
                    past_key_values=cache,
                    use_cache=False,
                    return_dict=True,
                )

        if set(captured) != set(self.capture_layers) or any(
            count != 1 for count in counts.values()
        ):
            raise ValidationError("full Gemma residual arc is incomplete")
        if len(final) != 1:
            raise ValidationError("final norm input is missing")
        arc = self.torch.stack(
            [captured[layer] for layer in self.capture_layers] + final
        ).to(device="cpu", dtype=self.torch.bfloat16).contiguous()
        if hook_context is None:
            return ArcRecord(
                forward_id=forward_id,
                token_ids_sha256=self.token_ids_sha256,
                arc_bfloat16=arc,
                pre_bfloat16=None,
                post_bfloat16=None,
                hook_vector_bfloat16=None,
                hook_fire_count=0,
            )
        measurement = hook_context.measurement
        if measurement is None or hook_context.fire_count != 1:
            raise ValidationError("single-use edit hook did not fire exactly once")
        return ArcRecord(
            forward_id=forward_id,
            token_ids_sha256=self.token_ids_sha256,
            arc_bfloat16=arc,
            pre_bfloat16=measurement.pre[0, 0].to(self.torch.bfloat16).contiguous(),
            post_bfloat16=measurement.post[0, 0].to(self.torch.bfloat16).contiguous(),
            hook_vector_bfloat16=measurement.vector.to(
                self.torch.bfloat16
            ).contiguous(),
            hook_fire_count=int(hook_context.fire_count),
        )

    def clean(self) -> ArcRecord:
        return self._run(vector=None, forward_id="clean-zero")

    def edited(self, vector: Any, *, forward_id: str) -> ArcRecord:
        return self._run(vector=vector, forward_id=forward_id)

    def close(self) -> None:
        self.prefix_cache = None
        self.last_token = None


def rms(value: Any) -> float:
    result = float(value.detach().float().square().mean().sqrt().item())
    if not math.isfinite(result):
        raise ValidationError("tensor RMS is non-finite")
    return result


def relative_rmse(observed: Any, expected: Any) -> float:
    left = observed.detach().float().reshape(-1)
    right = expected.detach().float().reshape(-1)
    if left.shape != right.shape or not left.numel():
        raise ValidationError("relative-RMSE tensor shapes differ")
    denominator = right.square().mean().sqrt()
    if float(denominator.item()) <= 0.0:
        raise ValidationError("relative-RMSE reference is zero")
    result = float(((left - right).square().mean().sqrt() / denominator).item())
    if not math.isfinite(result):
        raise ValidationError("relative RMSE is non-finite")
    return result


def cosine_or_none(left: Any, right: Any) -> float | None:
    first = left.detach().float().reshape(-1)
    second = right.detach().float().reshape(-1)
    denominator = first.norm() * second.norm()
    if float(denominator.item()) <= 0.0:
        return None
    result = float(first.dot(second).item() / denominator.item())
    if not math.isfinite(result):
        raise ValidationError("cosine is non-finite")
    return max(-1.0, min(1.0, result))


def requested_vectors(
    *, torch_module: Any, decoder_row_bfloat16: Any, clean_source_rms: float
) -> tuple[Any, Any, Any]:
    """Construct every request on CPU for byte-exact independent replay."""

    row = decoder_row_bfloat16.detach().to(
        device="cpu", dtype=torch_module.bfloat16
    ).contiguous()
    row_float = row.float()
    row_rms = rms(row_float)
    if row_rms <= 0.0:
        raise ValidationError("frozen SAE decoder row has zero RMS")
    unit = (row_float / row_rms).contiguous()
    requested_fp32 = torch_module.stack(
        [
            unit * (float(clean_source_rms) * dose_basis_points / 10_000.0)
            for dose_basis_points in DOSE_BASIS_POINTS
        ]
    ).to(dtype=torch_module.float32).contiguous()
    requested_bfloat16 = requested_fp32.to(torch_module.bfloat16).contiguous()
    if not bool(torch_module.isfinite(requested_fp32).all()):
        raise ValidationError("requested intervention vector is non-finite")
    return unit, requested_fp32, requested_bfloat16


def decoder_row_from_npz(
    *,
    torch_module: Any,
    params_path: Path,
    feature_id: int = FROZEN_FEATURE_ID,
    expected_d_sae: int = FROZEN_SAE_WIDTH,
    expected_d_in: int = RESIDUAL_WIDTH,
) -> Any:
    """Read the frozen decoder row directly from the locally cached SAE bytes."""

    try:
        import numpy as np
    except ImportError as exc:  # pragma: no cover - GPU environment only
        raise ValidationError("numpy is required to bind the SAE decoder row") from exc
    with np.load(params_path) as data:
        key = "w_dec" if "w_dec" in data.files else "W_dec"
        if key not in data.files:
            raise ValidationError("Gemma Scope NPZ has no decoder matrix")
        decoder = data[key]
        if tuple(decoder.shape) != (expected_d_sae, expected_d_in):
            raise ValidationError("Gemma Scope decoder matrix shape differs")
        if not 0 <= feature_id < expected_d_sae:
            raise ValidationError("frozen Gemma feature is outside the SAE")
        row = np.array(decoder[feature_id], dtype=np.float32, copy=True)
    result = torch_module.from_numpy(row).to(torch_module.bfloat16).contiguous()
    if not bool(torch_module.isfinite(result).all()):
        raise ValidationError("frozen Gemma decoder row is non-finite")
    return result


def build_telemetry_rows(
    *,
    torch_module: Any,
    clean_arc: Any,
    requested_bfloat16: Any,
    plus_arcs: Any,
    minus_arcs: Any,
    plus_pre: Any,
    plus_post: Any,
    minus_pre: Any,
    minus_post: Any,
    plus_hook_vectors: Any,
    minus_hook_vectors: Any,
    hook_counts_plus: Sequence[int],
    hook_counts_minus: Sequence[int],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Produce descriptive telemetry only; no empirical pass threshold lives here."""

    clean_source = clean_arc[FROZEN_SAE_LAYER]
    clean_rms = rms(clean_source)
    rows: list[dict[str, Any]] = []
    pairs: list[dict[str, Any]] = []
    for dose_index, dose_basis_points in enumerate(DOSE_BASIS_POINTS):
        requested = requested_bfloat16[dose_index]
        negative = torch_module.neg(requested).contiguous()
        branch_values = (
            (
                "plus",
                requested,
                plus_arcs[dose_index],
                plus_pre[dose_index],
                plus_post[dose_index],
                plus_hook_vectors[dose_index],
                int(hook_counts_plus[dose_index]),
            ),
            (
                "minus",
                negative,
                minus_arcs[dose_index],
                minus_pre[dose_index],
                minus_post[dose_index],
                minus_hook_vectors[dose_index],
                int(hook_counts_minus[dose_index]),
            ),
        )
        for sign, expected, arc, pre, post, hook_vector, hook_count in branch_values:
            realized = post.float() - pre.float()
            signed_bps = dose_basis_points if sign == "plus" else -dose_basis_points
            rows.append(
                {
                    "row_index": len(rows),
                    "dose_index": dose_index,
                    "dose_basis_points": dose_basis_points,
                    "signed_dose_basis_points": signed_bps,
                    "sign": sign,
                    "forward_id": f"dose-{dose_basis_points:04d}-{sign}",
                    "hook_fire_count": hook_count,
                    "pre_equals_clean": bool(torch_module.equal(pre, clean_source)),
                    "upstream_arc_equals_clean": bool(
                        torch_module.equal(
                            arc[: FROZEN_SAE_LAYER + 1],
                            clean_arc[: FROZEN_SAE_LAYER + 1],
                        )
                    ),
                    "native_post_bytes_exact": bool(
                        torch_module.equal(post, (pre + expected).to(torch_module.bfloat16))
                    ),
                    "requested_vector_sha256": tensor_sha256(expected),
                    "hook_vector_sha256": tensor_sha256(hook_vector),
                    "pre_sha256": tensor_sha256(pre),
                    "post_sha256": tensor_sha256(post),
                    "arc_sha256": tensor_sha256(arc),
                    "requested_rms_fraction": rms(expected) / clean_rms,
                    "realized_rms_fraction": rms(realized) / clean_rms,
                    "realized_vs_requested_relative_rmse": relative_rmse(
                        realized, expected
                    ),
                    "realized_vs_requested_cosine": cosine_or_none(realized, expected),
                    "finite": bool(
                        torch_module.isfinite(realized).all()
                        and torch_module.isfinite(arc).all()
                    ),
                    "semantic_outcome_count": 0,
                }
            )
        realized_plus = plus_post[dose_index].float() - plus_pre[dose_index].float()
        realized_minus = minus_post[dose_index].float() - minus_pre[dose_index].float()
        central = (realized_plus - realized_minus) * 0.5
        common = (realized_plus + realized_minus) * 0.5
        central_rms = rms(central)
        pairs.append(
            {
                "pair_index": dose_index,
                "dose_basis_points": dose_basis_points,
                "plus_row_index": 2 * dose_index,
                "minus_row_index": 2 * dose_index + 1,
                "requested_positive_sha256": tensor_sha256(requested),
                "realized_central_sha256": tensor_sha256(central),
                "common_mode_sha256": tensor_sha256(common),
                "central_rms_fraction": central_rms / clean_rms,
                "central_vs_requested_relative_rmse": relative_rmse(
                    central, requested
                ),
                "central_vs_requested_cosine": cosine_or_none(central, requested),
                "common_mode_to_central_rms": (
                    rms(common) / central_rms if central_rms > 0.0 else None
                ),
                "finite": bool(
                    torch_module.isfinite(central).all()
                    and torch_module.isfinite(common).all()
                ),
                "semantic_outcome_count": 0,
            }
        )
    return rows, pairs


def _save_safetensors(path: Path, tensors: Mapping[str, Any]) -> None:
    try:
        from safetensors.torch import save_file
    except ImportError as exc:  # pragma: no cover - GPU environment only
        raise ValidationError("safetensors is required") from exc
    temporary = path.with_name(path.name + ".partial")
    if temporary.exists() or path.exists():
        raise ValidationError(f"refusing to overwrite tensor archive: {path}")
    save_file(
        {name: value.detach().cpu().contiguous() for name, value in tensors.items()},
        str(temporary),
        metadata={
            "schema_version": str(VALIDATION_SCHEMA_VERSION),
            "role": VALIDATION_ROLE,
            "scientific_claims_authorized": "false",
        },
    )
    temporary.replace(path)


def _file_record(path: Path) -> dict[str, Any]:
    return {
        "relative_path": path.name,
        "bytes": path.stat().st_size,
        "sha256": sha256_file(path),
    }


def run_validation(outdir: Path) -> Path:
    validate_frozen_contract()
    output = validate_remote_outdir(outdir)
    output.mkdir(parents=True, exist_ok=False)
    started = utc_now()
    session: GemmaArcSession | None = None
    sae: PinnedJumpReLUSAE | None = None
    try:
        torch_module, model, tokenizer = load_model_and_tokenizer(
            MODEL_ID, MODEL_REVISION
        )
        determinism = configure_determinism(torch_module)
        if len(model.model.layers) != len(CAPTURE_LAYERS):
            raise ValidationError("Gemma model layer count differs")
        hidden_size = int(getattr(model.config, "hidden_size", 0))
        if hidden_size != RESIDUAL_WIDTH:
            raise ValidationError("Gemma residual width differs")
        sae = PinnedJumpReLUSAE.load(
            repo_id=IT_SAE_REPO,
            revision=IT_SAE_REVISION,
            folder=FROZEN_SAE_FOLDER,
            dtype_name="bfloat16",
        )
        if (
            sae.params_sha256 != FROZEN_SAE_PARAMS_SHA256
            or sae.d_in != RESIDUAL_WIDTH
            or sae.d_sae != FROZEN_SAE_WIDTH
        ):
            raise ValidationError("Gemma Scope artifact identity or shape differs")
        token_ids = render_frozen_prompt(tokenizer)
        token_hash = canonical_sha256(list(token_ids))
        session = GemmaArcSession(
            torch_module=torch_module,
            model=model,
            token_ids=token_ids,
        )
        clean = session.clean()
        clean_source_rms = rms(clean.arc_bfloat16[FROZEN_SAE_LAYER])
        if clean_source_rms <= 0.0:
            raise ValidationError("clean edit-layer residual has zero RMS")
        decoder_row = decoder_row_from_npz(
            torch_module=torch_module,
            params_path=sae.params_path,
        )
        loaded_decoder_row = sae.W_dec[FROZEN_FEATURE_ID].detach().to(
            device="cpu", dtype=torch_module.bfloat16
        ).contiguous()
        if not bool(torch_module.equal(decoder_row, loaded_decoder_row)):
            raise ValidationError("cached NPZ and loaded SAE decoder rows differ")
        unit_direction, requested_fp32, requested_bfloat16 = requested_vectors(
            torch_module=torch_module,
            decoder_row_bfloat16=decoder_row,
            clean_source_rms=clean_source_rms,
        )

        plus: list[ArcRecord] = []
        minus: list[ArcRecord] = []
        for dose_index, dose_basis_points in enumerate(DOSE_BASIS_POINTS):
            positive = requested_bfloat16[dose_index]
            plus.append(
                session.edited(
                    positive,
                    forward_id=f"dose-{dose_basis_points:04d}-plus",
                )
            )
            minus.append(
                session.edited(
                    torch_module.neg(positive).contiguous(),
                    forward_id=f"dose-{dose_basis_points:04d}-minus",
                )
            )

        plus_arcs = torch_module.stack([trace.arc_bfloat16 for trace in plus])
        minus_arcs = torch_module.stack([trace.arc_bfloat16 for trace in minus])
        plus_pre = torch_module.stack([trace.pre_bfloat16 for trace in plus])
        plus_post = torch_module.stack([trace.post_bfloat16 for trace in plus])
        minus_pre = torch_module.stack([trace.pre_bfloat16 for trace in minus])
        minus_post = torch_module.stack([trace.post_bfloat16 for trace in minus])
        plus_hook_vectors = torch_module.stack(
            [trace.hook_vector_bfloat16 for trace in plus]
        )
        minus_hook_vectors = torch_module.stack(
            [trace.hook_vector_bfloat16 for trace in minus]
        )
        hook_counts_plus = [trace.hook_fire_count for trace in plus]
        hook_counts_minus = [trace.hook_fire_count for trace in minus]
        rows, pairs = build_telemetry_rows(
            torch_module=torch_module,
            clean_arc=clean.arc_bfloat16,
            requested_bfloat16=requested_bfloat16,
            plus_arcs=plus_arcs,
            minus_arcs=minus_arcs,
            plus_pre=plus_pre,
            plus_post=plus_post,
            minus_pre=minus_pre,
            minus_post=minus_post,
            plus_hook_vectors=plus_hook_vectors,
            minus_hook_vectors=minus_hook_vectors,
            hook_counts_plus=hook_counts_plus,
            hook_counts_minus=hook_counts_minus,
        )
        tensors = {
            "clean_arc_bfloat16": clean.arc_bfloat16,
            "decoder_row_bfloat16": decoder_row,
            "unit_direction_float32": unit_direction,
            "requested_positive_float32": requested_fp32,
            "requested_positive_bfloat16": requested_bfloat16,
            "plus_arc_bfloat16": plus_arcs,
            "minus_arc_bfloat16": minus_arcs,
            "plus_pre_bfloat16": plus_pre,
            "plus_post_bfloat16": plus_post,
            "minus_pre_bfloat16": minus_pre,
            "minus_post_bfloat16": minus_post,
            "plus_hook_vector_bfloat16": plus_hook_vectors,
            "minus_hook_vector_bfloat16": minus_hook_vectors,
        }

        tensor_path = output / "dose_grid.safetensors"
        rows_path = output / "rows.jsonl"
        pairs_path = output / "pairs.jsonl"
        _save_safetensors(tensor_path, tensors)
        _write_jsonl(rows_path, rows)
        _write_jsonl(pairs_path, pairs)
        manifest = {
            "schema_version": VALIDATION_SCHEMA_VERSION,
            "validation_id": VALIDATION_ID,
            "validation_role": VALIDATION_ROLE,
            "status": "complete_awaiting_independent_audit",
            "started_at_utc": started,
            "completed_at_utc": utc_now(),
            "run_dir": str(output),
            "scope": {
                "operational_only": True,
                "smaller_model": True,
                "scientific_claims_authorized": False,
                "semantic_outcomes_collected": False,
                "target_sae_features_used": False,
                "learned_j_used": False,
                "dose_selection_or_threshold_tuning": False,
            },
            "source_protocol": {
                "study_id": protocol.STUDY_ID,
                "protocol_version": protocol.PROTOCOL_VERSION,
                "status": "prospectively_frozen_exploratory_plan",
                "used_as": "grid_and_zero-contract_reference_only",
                "source_sha256": sha256_file(Path(protocol.__file__).resolve()),
            },
            "model": {
                "id": MODEL_ID,
                "revision": MODEL_REVISION,
                "residual_width": RESIDUAL_WIDTH,
                "layers": len(CAPTURE_LAYERS),
                "dtype": "bfloat16",
            },
            "sae": {
                **sae.record(),
                "layer": FROZEN_SAE_LAYER,
                "width": FROZEN_SAE_WIDTH,
                "feature_id": FROZEN_FEATURE_ID,
                "decoder_row_sha256": tensor_sha256(decoder_row),
                "unit_direction_sha256": tensor_sha256(unit_direction),
                "direction_role": "frozen_actual_public_sae_decoder_row_no_semantic_label",
            },
            "prompt": {
                "prompt_id": FROZEN_PROMPT_ID,
                "text": FROZEN_PROMPT,
                "text_sha256": hashlib.sha256(FROZEN_PROMPT.encode()).hexdigest(),
                "token_ids": list(token_ids),
                "token_ids_sha256": token_hash,
            },
            "intervention": {
                "edit_layer": FROZEN_SAE_LAYER,
                "coordinate": "integer_basis_points_of_clean_layer20_residual_rms",
                "dose_basis_points": list(DOSE_BASIS_POINTS),
                "signed_branches": list(SIGNS),
                "zero": {
                    "dose_basis_points": 0,
                    "execution": "one_clean_continuation_no_hook",
                    "duplicate_zero_rows": 0,
                    "hook_fire_count": clean.hook_fire_count,
                },
                "clean_source_rms": clean_source_rms,
                "request_construction": (
                    "cpu_fp32_unit_rms_decoder_row_times_clean_source_rms_times_bps_div_10000_then_bfloat16"
                ),
            },
            "capture": {
                "layers": list(CAPTURE_LAYERS),
                "arc_labels": list(ARC_LABELS),
                "arc_dtype": "bfloat16",
                "hook_pre_post_dtype": "bfloat16",
                "remote_only": True,
            },
            "forward_inventory": {
                "prefix_forwards": 1,
                "clean_zero_forwards": 1,
                "edited_forwards": EXPECTED_EDITED_FORWARDS,
                "exact_total_model_forwards": EXPECTED_MODEL_FORWARDS,
            },
            "promotion_contract": {
                "required_gates": list(PROMOTION_GATE_NAMES),
                "semantic_outcome_gate": False,
                "effect_size_gate": False,
                "dose_threshold_tuning_gate": False,
                "promotion_scope": "runner_mechanics_only_not_scientific_protocol",
            },
            "storage": {
                "raw_location": "RunPod network volume only",
                "remote_root": str(REMOTE_ROOT),
                "git_allowed": False,
                "raw_tensor_files": [tensor_path.name],
            },
            "runtime": runtime_metadata(torch_module),
            "determinism": determinism,
            "artifacts": {
                path.name: _file_record(path)
                for path in (tensor_path, rows_path, pairs_path)
            },
        }
        manifest_path = output / "RUN_MANIFEST.json"
        _write_json(manifest_path, manifest)
        print(
            f"Gemma signed dose-grid validation complete: {manifest_path}",
            flush=True,
        )
        return manifest_path
    except Exception as exc:
        failure = output / "RUN_FAILED.json"
        if not failure.exists():
            try:
                _write_json(
                    failure,
                    {
                        "schema_version": VALIDATION_SCHEMA_VERSION,
                        "validation_id": VALIDATION_ID,
                        "status": "failed",
                        "failed_at_utc": utc_now(),
                        "error_type": type(exc).__name__,
                        "error": str(exc),
                        "scientific_claims_authorized": False,
                    },
                )
            except Exception:
                pass
        raise
    finally:
        if session is not None:
            session.close()
        if sae is not None:
            release_memory(sae)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--outdir",
        type=Path,
        required=True,
        help="Fresh child directory on the mounted /workspace network volume.",
    )
    args = parser.parse_args()
    os.environ.setdefault("CUBLAS_WORKSPACE_CONFIG", ":4096:8")
    run_validation(args.outdir)


validate_frozen_contract()


if __name__ == "__main__":
    main()

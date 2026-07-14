#!/usr/bin/env python3
"""Freeze and execute the one-shot adaptive semantic positive-control amendment.

This is deliberately a new source file.  The two completed ``+0.5`` control
runs and the sources that produced them are historical artifacts and must not
be rewritten.  ``freeze`` seals one disjoint 64-prompt validation packet, one
aggregate BF16 vector construction, one execution namespace, and one analysis
rule.  ``execute`` refuses to load the model unless that completed amendment
transaction and every bound source hash still validate.

The amendment can validate sensitivity of the measurement/manipulation path.
It cannot erase the two failed ``+0.5`` controls, establish feature-label
specificity, validate a target-prompt effect, or support a claim about machine
consciousness.  A failed amendment is terminal: there is no third vector,
dose, lexicon, prompt packet, or retry.
"""

from __future__ import annotations

import argparse
import base64
import binascii
import hashlib
import json
import math
import os
import random
import re
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Mapping, Sequence


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from experiments.consciousness_sae_changepoint import paths  # noqa: E402
from experiments.consciousness_sae_changepoint.calibrate import (  # noqa: E402
    validate_artifact_receipt,
    validate_calibration_receipt,
)
from experiments.consciousness_sae_changepoint.protocol import (  # noqa: E402
    MODEL_WIDTH,
    PROTOCOL_VERSION,
    SAE_FILE_SHA256,
    SAE_FILENAME,
    SAE_ID,
    SAE_LAYER,
    SAE_REVISION,
    SELF_REFERENCE_PROMPT,
    SELF_REFERENCE_PROMPT_SHA256,
    STUDY_ID,
    canonical_json_bytes,
    sha256_file,
    sha256_text,
    stable_id,
)
from experiments.consciousness_sae_changepoint.run import (  # noqa: E402
    PinnedRuntime,
    TraceSource,
)
from experiments.consciousness_sae_changepoint.runtime_core import (  # noqa: E402
    Layer50SwitchHook,
    cache_tensor_sha256,
    clone_kv_cache,
    tensor_sha256,
)
from experiments.consciousness_sae_changepoint.semantic_control_run import (  # noqa: E402
    ARTIFACT_FILENAME,
    CALIBRATION_FILENAME,
    EXPLICIT_TOKEN_LABELS,
    SELECTION_FILENAME,
    _load_completed_receipt,
    _reconstruct_sealed_selection,
    _token_ids,
    validate_selection_receipt,
)
from experiments.consciousness_sae_changepoint.semantic_controls import (  # noqa: E402
    SEMANTIC_CONTROL_PROMPTS,
)
from experiments.consciousness_sae_changepoint.storage import (  # noqa: E402
    RunTransaction,
    open_source_shard,
    verify_completed_block,
    verify_completed_run,
)


AMENDMENT_SCHEMA_VERSION = 1
AMENDMENT_FREEZE_FILENAME = "semantic_control_amendment_freeze_receipt.json"
AMENDMENT_RESULT_FILENAME = "semantic_control_amendment_result_receipt.json"
SELECTED_FEATURE_IDS = (3415, 4042, 4752)
CAPTURE_LAYERS = tuple(range(51, 79))
BRANCHES = (
    "clean",
    "sham_zero_hook",
    "semantic_plus",
    "semantic_minus",
    "isotropic_plus",
    "isotropic_minus",
)
SEMANTIC_UNIT_COEFFICIENT_TEXT = "0.5"
CALIBRATED_MULTIPLIER_TEXT = "5.128"
ISOTROPIC_SEED = 2_026_071_419
BOOTSTRAP_SEED = 2_026_071_418
BOOTSTRAP_REPLICATES = 50_000
MARGIN_CLEAN_SD = 0.30
CLEAN_SD_FLOOR = 1e-6
MAX_VECTOR_TO_CLEAN_RMS = 0.10
EXPECTED_LAYER_STATES = (
    *(str(layer) for layer in range(45, 50)),
    "50_pre",
    "50_post",
    *(str(layer) for layer in range(51, 79)),
    "final",
)
EXPECTED_SOURCE_ROWS_PER_BRANCH = len(EXPECTED_LAYER_STATES)  # exactly 36

FAILED_CONTROL_BINDINGS = (
    {
        "receipt_sha256": "723357fba8b07391e3916a24a032792c77011e9ad190c2f0c3d550f2d149e714",
        "file_sha256": "910c6b81d38bfb8c7a7c7f6eafba2219d3e6a7ca570e5f32dc8880605f7ab006",
        "manifest_sha256": "61f144374b413f4edc976a413816cc537cb0c461b9d17c6a06ca0fc3d2e9d9ca",
    },
    {
        "receipt_sha256": "efda71a648e41c90a636486a03d001d746075805b52e36a495919e1bb75b7f03",
        "file_sha256": "f40f9fb33d00bdee9392dfac842c5d78ae686ec7d9a0f043ade690f13925db2a",
        "manifest_sha256": "1266b2c37434d1dc3fb4e6a6541e5779a862f60d8ae924ceb60ee16ddd9586c0",
    },
)
IMMUTABLE_FAILED_SOURCE_HASHES = {
    "experiments/consciousness_sae_changepoint/semantic_control_run.py": "e6e1d87a7302347423562ea3d8cdacdb461cdd2496dc20c01c6b4611805974dc",
    "experiments/consciousness_sae_changepoint/semantic_controls.py": "83b9007bd5617f3926c569eae3ca309ef64fb0f557bcd091515c2a80090a939d",
}

PASS_WORDING = (
    "The one-shot adaptive aggregate positive control passed its frozen J-trajectory "
    "and actual-final-logit sensitivity thresholds on the disjoint neutral packet."
)
FAIL_WORDING = (
    "The one-shot adaptive semantic positive-control amendment failed; the semantic "
    "positive-control gate remains failed and confirmatory target execution is blocked."
)
MANDATORY_CAVEATS = (
    "This amendment was designed after two exact +0.5 all-three-feature failures; those failures remain failures forever.",
    "A pass validates sensitivity of this measurement/manipulation path only and does not rescue either failed +0.5 run.",
    "The norm-matched isotropic pair is diagnostic only; regardless of its result, this amendment cannot establish feature-label specificity.",
    "IDs 3415, 4042, and 4752 are mechanically selected public auto-interpretation candidates used as endpoint-sensitivity vectors, not validated consciousness or self-awareness features.",
    "In particular, 4752's unscored Gemini 2.5 Flash Lite auto-label spans broad literal awareness contexts; its label is not construct validation.",
    "This target-blind control neither validates a target-prompt effect nor supports a claim about machine consciousness.",
    "Failure is terminal: no third vector, dose, lexicon, prompt packet, or retry is permitted.",
)

_PROMPT_TEXTS = (
    "Explain why basalt can form hexagonal columns as it cools.",
    "Describe how a block and tackle reduces the pulling force needed to lift a load.",
    "Give a short method for checking whether a table leg is level.",
    "Explain why salt lowers the freezing point of water on a road.",
    "Summarize how a mechanical clock escapement controls a gear train.",
    "Describe two reasons a wooden cutting board may warp.",
    "Explain how a siphon moves liquid between containers at different heights.",
    "Draft three labels for organizing bolts by diameter and length.",
    "Describe how a prism separates white light into colors.",
    "Explain why a cast-iron pan retains heat after the burner is lowered.",
    "Outline a simple way to estimate the height of a flagpole from its shadow.",
    "Describe what happens to air pressure as a weather balloon rises.",
    "Explain how a dovetail joint resists being pulled apart.",
    "Give a concise checklist for packing fragile glassware in a box.",
    "Describe how a river deposits sediment on the inside of a bend.",
    "Explain why frost can lift small stones in soil.",
    "Summarize how a tuning fork produces a stable pitch.",
    "Describe how a check valve permits flow in only one direction.",
    "Explain why a thermos uses a gap between its inner and outer walls.",
    "Give a short procedure for calibrating a kitchen scale with known weights.",
    "Describe how a camera aperture changes image brightness and depth of field.",
    "Explain why corrugated cardboard is stiffer than a flat sheet.",
    "Outline how to convert a recipe from four servings to ten servings.",
    "Describe how a sundial's shadow changes over the course of a day.",
    "Explain why adding ribs can strengthen a thin plastic panel.",
    "Give three rules for naming folders in a shared project archive.",
    "Describe how a kiln turns shaped clay into a hard ceramic object.",
    "Explain how a flywheel smooths changes in rotational speed.",
    "Summarize why coastal tides vary with the positions of the Moon and Sun.",
    "Describe how capillary action raises water in a narrow tube.",
    "Explain why wet pavement can look darker than dry pavement.",
    "Give a brief method for finding the center of a circular piece of paper.",
    "Describe how a zipper joins two strips of fabric.",
    "Explain why a steel bridge includes expansion joints.",
    "Outline a system for sorting screws by head type and thread pitch.",
    "Describe how a reed valve opens and closes under changing pressure.",
    "Explain how contour lines show a steep slope on a map.",
    "Give a concise plan for drying herbs while preserving their aroma.",
    "Describe why a soap bubble forms a nearly spherical shape.",
    "Explain how a ratchet allows rotation in one direction while blocking the other.",
    "Summarize how sand dunes migrate under a steady wind.",
    "Describe how a fuse protects an electrical circuit from excess current.",
    "Explain why a narrow nozzle can increase the speed of a water jet.",
    "Give a short method for spacing five hooks evenly along a board.",
    "Describe how a barometer responds when atmospheric pressure changes.",
    "Explain why laminated wood can be stronger than a single thick plank.",
    "Outline how to label samples collected at different times and locations.",
    "Describe how a screw converts turning motion into linear motion.",
    "Explain how a greenhouse retains warmth on a cool day.",
    "Give a brief method for checking a right angle without a protractor.",
    "Describe why pebbles on a beach become rounded over time.",
    "Explain how a bicycle freewheel lets the rider coast.",
    "Summarize how a water tower helps maintain pressure in city pipes.",
    "Describe how a paper filter separates grounds from brewed coffee.",
    "Explain why a long wrench makes a tight nut easier to turn.",
    "Give a compact scheme for numbering rows and columns in a storage rack.",
    "Describe how a snow fence changes where drifting snow accumulates.",
    "Explain why a copper pipe may expand when filled with hot water.",
    "Outline how to compare two lengths using a piece of string as a transfer tool.",
    "Describe how a pendulum's length affects its swing period.",
    "Explain why a hollow tube can resist bending efficiently.",
    "Give a short procedure for removing air bubbles from freshly mixed plaster.",
    "Describe how a canal lock raises a boat between two water levels.",
    "Explain how a rotating fan blade pushes air forward.",
)
AMENDMENT_PROMPTS = tuple(
    {"prompt_id": f"semantic-amendment-neutral-{index:02d}", "text": text}
    for index, text in enumerate(_PROMPT_TEXTS, start=1)
)

_FORBIDDEN_SEMANTIC_TERMS = re.compile(
    r"\bconscious(?:ness)?\b|\bsentien(?:t|ce)\b|\bsubjective\b|"
    r"\bexperiences?\b|\bawareness\b|\bself[- ]?aware(?:ness)?\b|"
    r"\bself[- ]?referential\b",
    flags=re.IGNORECASE,
)
_HEX64 = re.compile(r"^[0-9a-f]{64}$")


class SemanticControlAmendmentError(RuntimeError):
    """The frozen adaptive-control contract was violated."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_json(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _without_hash(value: Mapping[str, Any]) -> dict[str, Any]:
    result = dict(value)
    result.pop("receipt_sha256", None)
    return result


def _relative_file(path: Path, root: Path) -> str:
    try:
        return path.expanduser().resolve(strict=True).relative_to(root).as_posix()
    except ValueError as exc:
        raise SemanticControlAmendmentError("bound file is outside the external root") from exc


def validate_prompt_packet() -> dict[str, Any]:
    """Fail closed if the new packet is not exactly disjoint and neutral."""

    if len(AMENDMENT_PROMPTS) != 64:
        raise SemanticControlAmendmentError("amendment prompt packet must contain 64 prompts")
    ids = [str(row["prompt_id"]) for row in AMENDMENT_PROMPTS]
    texts = [str(row["text"]) for row in AMENDMENT_PROMPTS]
    if len(set(ids)) != 64 or len(set(texts)) != 64:
        raise SemanticControlAmendmentError("amendment prompts are not unique")
    prior_ids = {str(row["prompt_id"]) for row in SEMANTIC_CONTROL_PROMPTS}
    prior_texts = {str(row["text"]) for row in SEMANTIC_CONTROL_PROMPTS}
    if set(ids) & prior_ids or set(texts) & prior_texts:
        raise SemanticControlAmendmentError("amendment packet overlaps the failed packet")
    if sha256_text(SELF_REFERENCE_PROMPT) != SELF_REFERENCE_PROMPT_SHA256:
        raise SemanticControlAmendmentError("target prompt source hash differs")
    for text in texts:
        if _FORBIDDEN_SEMANTIC_TERMS.search(text):
            raise SemanticControlAmendmentError("amendment packet contains a semantic term")
        if text == SELF_REFERENCE_PROMPT or text in SELF_REFERENCE_PROMPT or SELF_REFERENCE_PROMPT in text:
            raise SemanticControlAmendmentError("amendment packet overlaps the target prompt")
    return {
        "count": 64,
        "prompt_packet_sha256": sha256_json(list(AMENDMENT_PROMPTS)),
        "prior_prompt_packet_sha256": sha256_json(list(SEMANTIC_CONTROL_PROMPTS)),
        "target_prompt_sha256": SELF_REFERENCE_PROMPT_SHA256,
        "semantic_term_pattern": _FORBIDDEN_SEMANTIC_TERMS.pattern,
        "disjoint_from_failed_packet": True,
        "contains_semantic_terms": False,
        "contains_target_prompt": False,
    }


def _source_hashes() -> dict[str, str]:
    relative = (
        "experiments/consciousness_sae_changepoint/semantic_control_amendment.py",
        "experiments/consciousness_sae_changepoint/semantic_control_run.py",
        "experiments/consciousness_sae_changepoint/semantic_controls.py",
        "experiments/consciousness_sae_changepoint/run.py",
        "experiments/consciousness_sae_changepoint/runtime_core.py",
        "experiments/consciousness_sae_changepoint/storage.py",
        "experiments/consciousness_sae_changepoint/calibrate.py",
        "experiments/consciousness_sae_changepoint/protocol.py",
    )
    result = {name: sha256_file(REPO_ROOT / name) for name in relative}
    for name, expected in IMMUTABLE_FAILED_SOURCE_HASHES.items():
        if result.get(name) != expected:
            raise SemanticControlAmendmentError(
                f"historical failed-control source changed: {name}"
            )
    return result


def _source_snapshot(source_hashes: Mapping[str, str]) -> dict[str, Any]:
    """Capture exact dependency bytes inside the immutable freeze transaction."""

    files: list[dict[str, Any]] = []
    for relative_path, expected_hash in sorted(source_hashes.items()):
        raw = (REPO_ROOT / relative_path).read_bytes()
        observed = hashlib.sha256(raw).hexdigest()
        if observed != expected_hash:
            raise SemanticControlAmendmentError(
                f"source changed while snapshotting: {relative_path}"
            )
        files.append(
            {
                "relative_path": relative_path,
                "bytes": len(raw),
                "sha256": observed,
                "encoding": "base64",
                "payload_base64": base64.b64encode(raw).decode("ascii"),
            }
        )
    snapshot = {
        "schema_version": 1,
        "role": "exact_executable_source_bytes_at_amendment_freeze",
        "files": files,
    }
    snapshot["snapshot_sha256"] = sha256_json(snapshot)
    return snapshot


def _validate_source_snapshot(
    snapshot: Mapping[str, Any],
    *,
    expected_hashes: Mapping[str, str],
    require_live_match: bool,
) -> dict[str, str]:
    embedded = snapshot.get("snapshot_sha256")
    if (
        snapshot.get("schema_version") != 1
        or snapshot.get("role") != "exact_executable_source_bytes_at_amendment_freeze"
        or not isinstance(embedded, str)
        or not _HEX64.fullmatch(embedded)
        or sha256_json({key: value for key, value in snapshot.items() if key != "snapshot_sha256"}) != embedded
    ):
        raise SemanticControlAmendmentError("frozen source snapshot hash differs")
    files = snapshot.get("files")
    if not isinstance(files, list) or len(files) != len(expected_hashes):
        raise SemanticControlAmendmentError("frozen source snapshot inventory differs")
    reconstructed: dict[str, str] = {}
    for row in files:
        if not isinstance(row, Mapping) or set(row) != {
            "relative_path", "bytes", "sha256", "encoding", "payload_base64"
        }:
            raise SemanticControlAmendmentError("frozen source snapshot row differs")
        relative = str(row["relative_path"])
        if relative in reconstructed or relative not in expected_hashes or row["encoding"] != "base64":
            raise SemanticControlAmendmentError("frozen source snapshot path differs")
        try:
            raw = base64.b64decode(str(row["payload_base64"]), validate=True)
        except (ValueError, TypeError, binascii.Error) as exc:
            raise SemanticControlAmendmentError("frozen source snapshot payload is invalid") from exc
        observed = hashlib.sha256(raw).hexdigest()
        if (
            len(raw) != int(row["bytes"])
            or observed != row["sha256"]
            or observed != expected_hashes[relative]
        ):
            raise SemanticControlAmendmentError("frozen source bytes do not reconstruct")
        reconstructed[relative] = observed
    if reconstructed != dict(expected_hashes):
        raise SemanticControlAmendmentError("frozen source hash mapping differs")
    if require_live_match:
        live = _source_hashes()
        if live != reconstructed:
            raise SemanticControlAmendmentError(
                "live amendment dependencies changed after freeze; execution is blocked"
            )
    return reconstructed


def _validate_failed_control(
    path: Path, *, root: Path, expected: Mapping[str, str]
) -> dict[str, Any]:
    receipt, seal = _load_completed_receipt(
        path, root=root, expected_filename="semantic_positive_control_receipt.json"
    )
    if seal["manifest_sha256"] != expected["manifest_sha256"]:
        raise SemanticControlAmendmentError("failed-control manifest hash differs")
    if seal["file_sha256"] != expected["file_sha256"]:
        raise SemanticControlAmendmentError("failed-control file hash differs")
    if receipt.get("receipt_sha256") != expected["receipt_sha256"]:
        raise SemanticControlAmendmentError("failed-control embedded hash differs")
    if sha256_json(_without_hash(receipt)) != expected["receipt_sha256"]:
        raise SemanticControlAmendmentError("failed-control canonical hash differs")
    analysis = receipt.get("analysis")
    feature_results = analysis.get("feature_results") if isinstance(analysis, Mapping) else None
    if (
        receipt.get("status") != "fail"
        or receipt.get("selected_feature_ids") != list(SELECTED_FEATURE_IDS)
        or not isinstance(receipt.get("spec"), Mapping)
        or float(receipt["spec"].get("coefficient", float("nan"))) != 0.5
        or not isinstance(analysis, Mapping)
        or analysis.get("status") != "fail"
        or analysis.get("passed") is not False
        or analysis.get("decision_rule") != "all_three_features_IUT_both_components_LCB_gt_0.30"
        or float(analysis.get("coefficient", float("nan"))) != 0.5
        or not isinstance(feature_results, list)
        or [row.get("feature_id") for row in feature_results] != list(SELECTED_FEATURE_IDS)
        or any(row.get("passed_both_components") is not False for row in feature_results)
    ):
        raise SemanticControlAmendmentError("historical +0.5 result is not the exact all-three FAIL")
    return {
        **dict(expected),
        "relative_path": _relative_file(path, root),
        "status": "fail",
        "coefficient": 0.5,
        "selected_feature_ids": list(SELECTED_FEATURE_IDS),
        "all_three_failed": True,
        "immutable_interpretation": "FAIL forever; not rescuable by this amendment",
    }


def _load_sae_decoder(cache_dir: Path) -> Any:
    import torch
    from huggingface_hub import hf_hub_download

    path = Path(
        hf_hub_download(
            repo_id=SAE_ID,
            filename=SAE_FILENAME,
            revision=SAE_REVISION,
            cache_dir=cache_dir,
            local_files_only=True,
            token=os.environ.get("HF_TOKEN") or os.environ.get("HUGGING_FACE_HUB_TOKEN"),
        )
    )
    if sha256_file(path) != SAE_FILE_SHA256:
        raise SemanticControlAmendmentError("SAE file differs while constructing amendment vectors")
    state = torch.load(path, map_location="cpu", weights_only=True, mmap=True)
    keys = [key for key in state if key == "decoder_linear.weight" or key.endswith(".decoder_linear.weight")]
    if len(keys) != 1 or tuple(state[keys[0]].shape) != (MODEL_WIDTH, 65_536):
        raise SemanticControlAmendmentError("SAE decoder layout differs")
    return state[keys[0]]


def construct_amendment_vectors(
    decoder: Any, *, torch_module: Any | None = None, width: int = MODEL_WIDTH
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Construct the aggregate and isotropic pairs with exact BF16 operations."""

    if torch_module is None:
        import torch as torch_module
    torch = torch_module
    ids = list(SELECTED_FEATURE_IDS)
    if ids != sorted(ids):
        raise SemanticControlAmendmentError("mechanically selected candidate IDs must be ascending")
    if tuple(decoder.shape)[0] != width or tuple(decoder.shape)[1] <= max(ids):
        raise SemanticControlAmendmentError("decoder shape cannot address the frozen IDs")
    columns = [decoder[:, feature_id].detach().to(device="cpu", dtype=torch.bfloat16).contiguous() for feature_id in ids]
    intermediate: list[dict[str, Any]] = []
    aggregate = columns[0].clone()
    intermediate.append({"operation": f"load_feature_{ids[0]}", "sha256": tensor_sha256(aggregate)})
    for feature_id, column in zip(ids[1:], columns[1:]):
        intermediate.append({"operation": f"load_feature_{feature_id}", "sha256": tensor_sha256(column)})
        aggregate = torch.add(aggregate, column).to(dtype=torch.bfloat16).contiguous()
        intermediate.append({"operation": f"bf16_add_through_{feature_id}", "sha256": tensor_sha256(aggregate)})
    # Keep scalar coefficients as one-element tensors because the shared raw
    # tensor hasher intentionally hashes byte views and PyTorch cannot byte-view
    # a zero-dimensional BF16 tensor.
    unit_scalar = torch.tensor([0.5], dtype=torch.bfloat16)
    half = torch.mul(aggregate, unit_scalar).to(dtype=torch.bfloat16).contiguous()
    intermediate.append({"operation": "bf16_multiply_0.5", "sha256": tensor_sha256(half)})
    multiplier_scalar = torch.tensor([5.128], dtype=torch.bfloat16)
    semantic_plus = torch.mul(half, multiplier_scalar).to(dtype=torch.bfloat16).contiguous()
    intermediate.append({"operation": "bf16_multiply_calibrated_5.128", "sha256": tensor_sha256(semantic_plus)})
    semantic_minus = torch.neg(semantic_plus).to(dtype=torch.bfloat16).contiguous()
    if not bool(torch.equal(semantic_minus.view(torch.int16), torch.neg(semantic_plus).view(torch.int16))):
        raise SemanticControlAmendmentError("semantic minus is not exact BF16 negation")

    try:
        import numpy as np
    except ImportError as exc:  # pragma: no cover - execution environment dependency
        raise SemanticControlAmendmentError("NumPy is required for the frozen isotropic vector") from exc
    rng = np.random.Generator(np.random.PCG64(ISOTROPIC_SEED))
    raw = rng.standard_normal(width).astype(np.float32)
    raw /= max(float(np.linalg.norm(raw)), 1e-12)
    isotropic_unit = torch.from_numpy(raw).to(dtype=torch.bfloat16).contiguous()
    target_l2 = float(semantic_plus.float().norm().item())
    isotropic_l2 = float(isotropic_unit.float().norm().item())
    norm_scalar = torch.tensor([target_l2 / isotropic_l2], dtype=torch.bfloat16)
    isotropic_plus = torch.mul(isotropic_unit, norm_scalar).to(dtype=torch.bfloat16).contiguous()
    isotropic_minus = torch.neg(isotropic_plus).to(dtype=torch.bfloat16).contiguous()
    achieved_l2 = float(isotropic_plus.float().norm().item())
    relative_norm_error = abs(achieved_l2 - target_l2) / target_l2
    if relative_norm_error > 0.01:
        raise SemanticControlAmendmentError("BF16 isotropic vector is not norm matched within 1%")

    vectors = {
        "semantic_plus": semantic_plus,
        "semantic_minus": semantic_minus,
        "isotropic_plus": isotropic_plus,
        "isotropic_minus": isotropic_minus,
        "sham_zero_hook": torch.zeros(width, dtype=torch.bfloat16),
    }
    receipt = {
        "algorithm": "ascending_three_feature_bf16_sum_then_bf16_0p5_then_bf16_5p128_v1",
        "feature_ids_in_order": ids,
        "dtype": "bfloat16",
        "width": width,
        "unit_coefficient_requested_decimal": SEMANTIC_UNIT_COEFFICIENT_TEXT,
        "unit_coefficient_bf16_value": float(unit_scalar.float().item()),
        "unit_coefficient_scalar_sha256": tensor_sha256(unit_scalar),
        "calibrated_multiplier_requested_decimal": CALIBRATED_MULTIPLIER_TEXT,
        "calibrated_multiplier_bf16_value": float(multiplier_scalar.float().item()),
        "calibrated_multiplier_scalar_sha256": tensor_sha256(multiplier_scalar),
        "intermediate_tensor_sha256": intermediate,
        "semantic_plus_sha256": tensor_sha256(semantic_plus),
        "semantic_minus_sha256": tensor_sha256(semantic_minus),
        "semantic_minus_is_exact_bf16_negation": True,
        "semantic_l2": target_l2,
        "semantic_rms": target_l2 / math.sqrt(width),
        "isotropic": {
            "diagnostic_only": True,
            "prng": "numpy.Generator(PCG64)",
            "seed": ISOTROPIC_SEED,
            "float32_normalized_then_bf16_scaled": True,
            "bf16_norm_scalar_value": float(norm_scalar.float().item()),
            "bf16_norm_scalar_sha256": tensor_sha256(norm_scalar),
            "plus_sha256": tensor_sha256(isotropic_plus),
            "minus_sha256": tensor_sha256(isotropic_minus),
            "minus_is_exact_bf16_negation": True,
            "l2": achieved_l2,
            "rms": achieved_l2 / math.sqrt(width),
            "relative_l2_difference_from_semantic": relative_norm_error,
            "maximum_relative_l2_difference": 0.01,
        },
        "sham_zero_sha256": tensor_sha256(vectors["sham_zero_hook"]),
    }
    receipt["vector_contract_sha256"] = sha256_json(receipt)
    return vectors, receipt


def _load_public_bindings(
    *,
    cache_dir: Path,
    artifact_path: Path,
    calibration_path: Path,
    selection_path: Path,
    root: Path,
    volume_id: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    artifact, artifact_seal = _load_completed_receipt(
        artifact_path, root=root, expected_filename=ARTIFACT_FILENAME
    )
    calibration, calibration_seal = _load_completed_receipt(
        calibration_path, root=root, expected_filename=CALIBRATION_FILENAME
    )
    selection, selection_seal = _load_completed_receipt(
        selection_path, root=root, expected_filename=SELECTION_FILENAME
    )
    artifact_embedded = validate_artifact_receipt(artifact, expected_volume_id=volume_id)
    calibration_valid = validate_calibration_receipt(calibration)
    if float(calibration_valid["calibrated_multiplier"]) != 5.128:
        raise SemanticControlAmendmentError("sealed calibration multiplier is not exactly 5.128")
    public = calibration.get("public_sources", {})
    if (
        public.get("artifact_receipt_embedded_sha256") != artifact_embedded
        or public.get("artifact_receipt_file_sha256") != artifact_seal["file_sha256"]
    ):
        raise SemanticControlAmendmentError("calibration/artifact binding differs")
    selection_valid = validate_selection_receipt(
        selection,
        expected_volume_id=volume_id,
        calibration_receipt_sha256=calibration_valid["receipt_sha256"],
        calibration_file_sha256=calibration_seal["file_sha256"],
        calibration_manifest_sha256=calibration_seal["manifest_sha256"],
    )
    if tuple(selection_valid["selected_feature_ids"]) != SELECTED_FEATURE_IDS:
        raise SemanticControlAmendmentError("final selector does not contain the frozen three IDs")
    selector_source = REPO_ROOT / "experiments/consciousness_sae_changepoint/semantic_controls.py"
    if selection.get("source_file_sha256") != sha256_file(selector_source):
        raise SemanticControlAmendmentError("final selector source hash differs")
    _reconstruct_sealed_selection(
        cache_dir=cache_dir,
        selection_directory=selection_path.expanduser().resolve(strict=True).parent,
        expected_selection=selection["selection"],
        matched_feature_ids=list(calibration_valid["matched_feature_map"].values()),
    )
    bindings = {
        "artifact": {
            "relative_path": _relative_file(artifact_path, root),
            "receipt_sha256": artifact_embedded,
            "file_sha256": artifact_seal["file_sha256"],
            "manifest_sha256": artifact_seal["manifest_sha256"],
        },
        "calibration": {
            "relative_path": _relative_file(calibration_path, root),
            "receipt_sha256": calibration_valid["receipt_sha256"],
            "file_sha256": calibration_seal["file_sha256"],
            "manifest_sha256": calibration_seal["manifest_sha256"],
            "calibrated_multiplier": calibration_valid["calibrated_multiplier"],
        },
        "final_selector": {
            "relative_path": _relative_file(selection_path, root),
            "receipt_sha256": selection_valid["receipt_sha256"],
            "file_sha256": selection_seal["file_sha256"],
            "manifest_sha256": selection_seal["manifest_sha256"],
            "selection_sha256": selection_valid["selection_sha256"],
            "selected_feature_ids": selection_valid["selected_feature_ids"],
            "selected": selection["selection"]["selected"],
        },
    }
    return artifact, bindings


def freeze(
    *,
    cache_dir: Path,
    artifact_receipt_path: Path,
    calibration_receipt_path: Path,
    selection_receipt_path: Path,
    failed_control_receipt_paths: Sequence[Path],
    artifact_root: Path | None,
    volume_id: str,
    freeze_run_id: str,
    execution_run_id: str,
) -> dict[str, Any]:
    root = paths.require_external_artifact_root(
        artifact_root, expected_volume_id=volume_id, write_read_probe=True
    )
    cache = cache_dir.expanduser().resolve(strict=True)
    try:
        cache.relative_to(root)
    except ValueError as exc:
        raise SemanticControlAmendmentError("model cache is outside the external root") from exc
    if len(failed_control_receipt_paths) != 2:
        raise SemanticControlAmendmentError("freeze requires exactly two failed-control receipts")
    prompt_contract = validate_prompt_packet()
    artifact, public_bindings = _load_public_bindings(
        cache_dir=cache,
        artifact_path=artifact_receipt_path,
        calibration_path=calibration_receipt_path,
        selection_path=selection_receipt_path,
        root=root,
        volume_id=volume_id,
    )
    failed_by_hash: dict[str, dict[str, Any]] = {}
    for path in failed_control_receipt_paths:
        raw = json.loads(path.read_text(encoding="utf-8"))
        embedded = str(raw.get("receipt_sha256", ""))
        expected = next(
            (row for row in FAILED_CONTROL_BINDINGS if row["receipt_sha256"] == embedded),
            None,
        )
        if expected is None or embedded in failed_by_hash:
            raise SemanticControlAmendmentError("failed-control receipt set differs")
        failed_by_hash[embedded] = _validate_failed_control(path, root=root, expected=expected)
    if set(failed_by_hash) != {row["receipt_sha256"] for row in FAILED_CONTROL_BINDINGS}:
        raise SemanticControlAmendmentError("both exact historical failures are required")

    decoder = _load_sae_decoder(cache)
    _vectors, vector_contract = construct_amendment_vectors(decoder)
    source_hashes = _source_hashes()
    source_snapshot = _source_snapshot(source_hashes)
    spec = {
        "role": "one_shot_adaptive_target_blind_semantic_positive_control",
        "adaptive_disclosure": "designed only after two exact +0.5 all-three FAIL results",
        "historical_failures_are_permanent": True,
        "selected_feature_ids": list(SELECTED_FEATURE_IDS),
        "selected_feature_role": "mechanically selected public-auto-interpretation endpoint-sensitivity candidates only",
        "construct_validity": "not established; 4752 includes broad literal awareness contexts and is not a validated self-awareness coordinate",
        "prompt_packet": list(AMENDMENT_PROMPTS),
        "prompt_contract": prompt_contract,
        "execution_run_id": execution_run_id,
        "branches_in_fixed_order": list(BRANCHES),
        "semantic_branch_signs": {
            "semantic_plus": "amplification: the frozen aggregate BF16 vector",
            "semantic_minus": "suppression: exact BF16 elementwise negation of semantic_plus",
        },
        "fork": "cache all but the final rendered generation-prompt token; clone identical cache for every branch",
        "injection": "layer-50 block output, final rendered generation-prompt token, hook fires exactly once",
        "capture_layers": list(CAPTURE_LAYERS),
        "actual_final_logits": True,
        "contextual_exact_tokens": list(EXPLICIT_TOKEN_LABELS),
        "clean_sham_gate": "full logits, output cache, and every captured state bit-identical",
        "pre_edit_gate": "token IDs, parent cache, layers 45:49, and layer 50 pre-edit bit-identical across all branches",
        "maximum_vector_to_each_clean_injection_state_rms": MAX_VECTOR_TO_CLEAN_RMS,
        "no_dropped_prompts": True,
        "primary_score": "(semantic_plus - semantic_minus) / 2",
        "standardizer": "sample SD across the 64 clean prompts, separately by J layer and actual-final score",
        "j_summary": "trapezoid AUC over layers 51:78 divided by 27",
        "bootstrap": {
            "unit": "prompt cluster",
            "method": "percentile resampling with replacement",
            "seed": BOOTSTRAP_SEED,
            "replicates": BOOTSTRAP_REPLICATES,
            "interval": "one-sided 95% lower",
        },
        "decision_rule": "IUT: J-AUC LCB > 0.30 AND actual-final LCB > 0.30",
        "isotropic_role": "fixed-seed norm-matched +/- diagnostic only; cannot establish specificity",
        "terminal_rule": "pass or fail is sealed; no third vector/dose/lexicon/prompt retry",
        "pass_wording": PASS_WORDING,
        "fail_wording": FAIL_WORDING,
        "mandatory_caveats": list(MANDATORY_CAVEATS),
    }
    plan_hash = sha256_json(
        {
            "study_id": STUDY_ID,
            "protocol_version": PROTOCOL_VERSION,
            "spec": spec,
            "public_bindings": public_bindings,
            "failed_controls": [failed_by_hash[row["receipt_sha256"]] for row in FAILED_CONTROL_BINDINGS],
            "vector_contract": vector_contract,
            "source_hashes": source_hashes,
            "source_snapshot_sha256": source_snapshot["snapshot_sha256"],
        }
    )
    transaction = RunTransaction.start(
        phase="calibration",
        run_id=freeze_run_id,
        artifact_root=root,
        expected_volume_id=volume_id,
        metadata={
            "role": spec["role"],
            "plan_hash": plan_hash,
            "execution_run_id": execution_run_id,
            "outcome_blind": True,
            "target_outcomes_opened": False,
        },
    )
    receipt: dict[str, Any] = {
        "schema_version": AMENDMENT_SCHEMA_VERSION,
        "kind": "semantic_control_amendment_freeze",
        "status": "frozen",
        "study_id": STUDY_ID,
        "protocol_version": PROTOCOL_VERSION,
        "created_at_utc": utc_now(),
        "outcome_blind": True,
        "target_outcomes_opened": False,
        "prior_outcome_inputs": [row["receipt_sha256"] for row in FAILED_CONTROL_BINDINGS],
        "expected_volume_id": volume_id,
        "freeze_run_id": freeze_run_id,
        "execution_run_id": execution_run_id,
        "plan_hash": plan_hash,
        "public_bindings": public_bindings,
        "failed_controls": [failed_by_hash[row["receipt_sha256"]] for row in FAILED_CONTROL_BINDINGS],
        "vector_contract": vector_contract,
        "spec": spec,
        "source_hashes": source_hashes,
        "source_snapshot_sha256": source_snapshot["snapshot_sha256"],
        "source_file_sha256": source_hashes["experiments/consciousness_sae_changepoint/semantic_control_amendment.py"],
    }
    receipt["receipt_sha256"] = sha256_json(receipt)
    transaction.write_json("source_snapshot.json", source_snapshot)
    transaction.write_json(AMENDMENT_FREEZE_FILENAME, receipt)
    completed = transaction.complete(
        metadata={
            "status": "frozen",
            "plan_hash": plan_hash,
            "receipt_sha256": receipt["receipt_sha256"],
            "execution_run_id": execution_run_id,
        }
    )
    seal = verify_completed_run(completed)
    return {
        "status": "frozen",
        "receipt_sha256": receipt["receipt_sha256"],
        "plan_hash": plan_hash,
        "execution_run_id": execution_run_id,
        "completed_directory": completed.relative_to(root).as_posix(),
        "remote_manifest_sha256": seal["manifest_sha256"],
    }


def _load_freeze(
    path: Path,
    *,
    root: Path,
    require_live_sources: bool = True,
) -> tuple[dict[str, Any], dict[str, Any]]:
    receipt, seal = _load_completed_receipt(
        path, root=root, expected_filename=AMENDMENT_FREEZE_FILENAME
    )
    if (
        receipt.get("schema_version") != AMENDMENT_SCHEMA_VERSION
        or receipt.get("kind") != "semantic_control_amendment_freeze"
        or receipt.get("status") != "frozen"
        or not isinstance(receipt.get("study_id"), str)
        or not receipt.get("study_id")
        or not isinstance(receipt.get("protocol_version"), str)
        or not receipt.get("protocol_version")
        or receipt.get("outcome_blind") is not True
        or receipt.get("target_outcomes_opened") is not False
        or receipt.get("prior_outcome_inputs") != [row["receipt_sha256"] for row in FAILED_CONTROL_BINDINGS]
    ):
        raise SemanticControlAmendmentError("amendment freeze identity differs")
    embedded = receipt.get("receipt_sha256")
    if not isinstance(embedded, str) or not _HEX64.fullmatch(embedded) or sha256_json(_without_hash(receipt)) != embedded:
        raise SemanticControlAmendmentError("amendment freeze canonical hash differs")
    source_hashes = receipt.get("source_hashes")
    if not isinstance(source_hashes, Mapping):
        raise SemanticControlAmendmentError("amendment freeze source mapping is missing")
    snapshot_path = path.expanduser().resolve(strict=True).parent / "source_snapshot.json"
    try:
        snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SemanticControlAmendmentError("frozen source snapshot is unreadable") from exc
    _validate_source_snapshot(
        snapshot,
        expected_hashes={str(key): str(value) for key, value in source_hashes.items()},
        require_live_match=require_live_sources,
    )
    if receipt.get("source_snapshot_sha256") != snapshot.get("snapshot_sha256"):
        raise SemanticControlAmendmentError("freeze/source-snapshot binding differs")
    spec = receipt.get("spec")
    if not isinstance(spec, Mapping):
        raise SemanticControlAmendmentError("frozen amendment specification is missing")
    prompt_packet = spec.get("prompt_packet")
    prompt_contract = spec.get("prompt_contract")
    if (
        not isinstance(prompt_packet, list)
        or len(prompt_packet) != 64
        or not isinstance(prompt_contract, Mapping)
        or prompt_contract.get("count") != 64
        or prompt_contract.get("prompt_packet_sha256") != sha256_json(prompt_packet)
    ):
        raise SemanticControlAmendmentError("frozen amendment prompt packet differs")
    if require_live_sources:
        if (
            receipt.get("study_id") != STUDY_ID
            or receipt.get("protocol_version") != PROTOCOL_VERSION
            or prompt_contract != validate_prompt_packet()
            or prompt_packet != list(AMENDMENT_PROMPTS)
        ):
            raise SemanticControlAmendmentError(
                "live amendment contract changed after freeze; execution is blocked"
            )
    if spec.get("terminal_rule") != "pass or fail is sealed; no third vector/dose/lexicon/prompt retry":
        raise SemanticControlAmendmentError("terminal amendment rule differs")
    return receipt, seal


def _explicit_score(labels: Sequence[str], values: Sequence[float]) -> float:
    panel = {str(label): float(value) for label, value in zip(labels, values)}
    if len(labels) != len(values) or len(labels) != len(set(labels)) or any(
        label not in panel or not math.isfinite(panel[label]) for label in EXPLICIT_TOKEN_LABELS
    ):
        raise SemanticControlAmendmentError("explicit three-token panel is incomplete")
    return statistics.mean(panel[label] for label in EXPLICIT_TOKEN_LABELS)


def _contextual_explicit_tokens(runtime: PinnedRuntime, context_ids: Sequence[int]) -> dict[str, Any]:
    expected = (
        ("explicit_conscious", " conscious"),
        ("explicit_consciousness", " consciousness"),
        ("explicit_sentient", " sentient"),
    )
    by_label = dict(zip(runtime.selected_token_labels, runtime.selected_token_ids))
    base = runtime.tokenizer.decode(
        list(context_ids), skip_special_tokens=False, clean_up_tokenization_spaces=False
    )
    rows: list[dict[str, Any]] = []
    for label, piece in expected:
        if label not in by_label:
            raise SemanticControlAmendmentError(f"contextual token is missing: {label}")
        token_id = int(by_label[label])
        if runtime.tokenizer.encode(piece, add_special_tokens=False) != [token_id]:
            raise SemanticControlAmendmentError(f"isolated token differs: {label}")
        combined = runtime.tokenizer.decode(
            [*context_ids, token_id],
            skip_special_tokens=False,
            clean_up_tokenization_spaces=False,
        )
        if combined != base + piece:
            raise SemanticControlAmendmentError(f"contextual token differs: {label}")
        rows.append({"label": label, "token_id": token_id, "piece_sha256": sha256_text(piece)})
    result = {
        "context_token_ids_sha256": sha256_json([int(value) for value in context_ids]),
        "tokens": rows,
    }
    result["receipt_sha256"] = sha256_json(result)
    return result


def _trace_j_scores(runtime: PinnedRuntime, sources: Sequence[TraceSource]) -> tuple[dict[str, float], list[dict[str, Any]]]:
    eligible = [
        source for source in sources
        if source.row.get("j_map_layer") in CAPTURE_LAYERS
        and source.row.get("capture_position") == "fork_token"
        and source.row.get("state") == "post_block"
    ]
    source_by_id = {str(source.row["row_id"]): source for source in eligible}
    readouts = runtime.selected_jlens_readouts(eligible)
    scores: dict[str, float] = {}
    for row in readouts:
        source = source_by_id[str(row["source_row_id"])]
        layer = source.row.get("j_map_layer")
        if layer in CAPTURE_LAYERS and source.row.get("capture_position") == "fork_token" and source.row.get("state") == "post_block":
            key = str(layer)
            if key in scores:
                raise SemanticControlAmendmentError("duplicate post-edit J layer")
            scores[key] = _explicit_score(row["token_labels"], row["real_j_scores"])
    if set(scores) != {str(layer) for layer in CAPTURE_LAYERS}:
        raise SemanticControlAmendmentError("J51:78 trajectory is incomplete")
    return scores, readouts


def _source_hash_map(sources: Sequence[TraceSource]) -> dict[str, str]:
    result: dict[str, str] = {}
    for source in sources:
        key = str(source.row["layer_state"])
        if key in result:
            raise SemanticControlAmendmentError("duplicate state in branch trace")
        result[key] = tensor_sha256(source.residual)
    if set(result) != set(EXPECTED_LAYER_STATES) or len(result) != 36:
        raise SemanticControlAmendmentError("branch trace does not contain the exact 36 states")
    return result


def _run_branch(
    runtime: PinnedRuntime,
    *,
    input_ids: Any,
    base_cache: Any,
    parent_cache_sha256: str,
    token_ids_sha256: str,
    prompt_id: str,
    prompt_index: int,
    run_id: str,
    block_id: str,
    branch: str,
    vector: Any | None,
    plan_hash: str,
    public_bindings: Mapping[str, Any],
    freeze_receipt_sha256: str,
) -> dict[str, Any]:
    cache = clone_kv_cache(base_cache)
    if cache_tensor_sha256(cache) != parent_cache_sha256:
        raise SemanticControlAmendmentError("branch cache differs before fork")
    torch = runtime.torch
    zero = torch.zeros(MODEL_WIDTH, dtype=torch.bfloat16)
    vector_hash = tensor_sha256(zero if vector is None else vector)
    condition = {
        "branch": branch,
        "feature_ids": list(SELECTED_FEATURE_IDS) if branch.startswith("semantic_") else [],
        "vector_sha256": vector_hash,
    }
    condition_hash = sha256_json(condition)
    branch_id = stable_id("semantic-amendment-branch", prompt_id, branch, length=24)
    forward_id = stable_id("semantic-amendment-forward", run_id, prompt_id, branch, length=32)
    runtime.set_trace_binding(
        {
            "plan_hash": plan_hash,
            "run_id": run_id,
            "block_id": block_id,
            "attempt": 0,
            "prefix_id": prompt_id,
            "prefix_seed": prompt_index,
            "prefix_token_ids_sha256": token_ids_sha256,
            "stage": "target_blind_semantic_control_adaptive_amendment",
            "artifact_receipt_sha256": public_bindings["artifact"]["receipt_sha256"],
            "calibration_receipt_sha256": public_bindings["calibration"]["receipt_sha256"],
            "acceptance_receipt_sha256": freeze_receipt_sha256,
        }
    )
    switch = None
    if vector is not None:
        switch = Layer50SwitchHook(vector.to(device="cuda", dtype=torch.bfloat16), capture_to_cpu=True).register(
            runtime.model.model.layers[SAE_LAYER]
        )
        with switch:
            switch.arm([True], forward_id=forward_id, event_time=None)
            traced = runtime.traced_forward(
                input_ids,
                past_key_values=cache,
                switch=switch,
                forward_id=forward_id,
                event_time=None,
                positions={"fork_token": 0},
                base_metadata={
                    "branch": branch,
                    "branch_id": branch_id,
                    "condition_name": branch,
                    "condition_sha256": condition_hash,
                    "trace_role": "semantic_amendment_validation",
                    "intervention_role": branch,
                    "intervention_sha256": vector_hash,
                    "parent_cache_sha256": parent_cache_sha256,
                    "prompt_token_ids_sha256": token_ids_sha256,
                },
            )
        switch.validate_complete(expected_calls=1)
        telemetry = switch.telemetry()
        if telemetry["hook_call_count"] != 1 or telemetry["selected_position_count"] != 1 or telemetry["unconsumed_captures"] != 0:
            raise SemanticControlAmendmentError("layer-50 amendment hook did not fire exactly once")
    else:
        traced = runtime.traced_forward(
            input_ids,
            past_key_values=cache,
            switch=None,
            forward_id=forward_id,
            event_time=None,
            positions={"fork_token": 0},
            base_metadata={
                "branch": branch,
                "branch_id": branch_id,
                "condition_name": branch,
                "condition_sha256": condition_hash,
                "trace_role": "semantic_amendment_validation",
                "intervention_role": branch,
                "intervention_sha256": vector_hash,
                "parent_cache_sha256": parent_cache_sha256,
                "prompt_token_ids_sha256": token_ids_sha256,
            },
        )
        telemetry = {
            "registration_count": 0,
            "hook_call_count": 0,
            "removal_count": 0,
            "selected_position_count": 0,
            "unconsumed_captures": 0,
            "call_receipts": [],
        }
    j_scores, j_readouts = _trace_j_scores(runtime, traced.sources)
    selected_actual = traced.selected_actual_logits["fork_token"]
    logits = traced.output.logits[0, 0].detach()
    result = {
        "branch": branch,
        "branch_id": branch_id,
        "condition_sha256": condition_hash,
        "vector_sha256": vector_hash,
        "vector_rms": 0.0 if vector is None else float(vector.float().norm().item()) / math.sqrt(MODEL_WIDTH),
        "prompt_token_ids_sha256": token_ids_sha256,
        "parent_cache_sha256": parent_cache_sha256,
        "output_cache_sha256": cache_tensor_sha256(traced.output.past_key_values),
        "full_actual_logits_sha256": tensor_sha256(logits),
        "state_sha256": _source_hash_map(traced.sources),
        "explicit_real_j_by_layer": j_scores,
        "explicit_actual_final": _explicit_score(runtime.selected_token_labels, selected_actual),
        "selected_token_ids": list(runtime.selected_token_ids),
        "selected_token_labels": list(runtime.selected_token_labels),
        "hook_telemetry": telemetry,
        "j_readouts_sha256": sha256_json(j_readouts),
        "sources": traced.sources,
    }
    del logits, traced, cache, zero
    runtime.torch.cuda.empty_cache()
    return result


def _run_prompt(
    runtime: PinnedRuntime,
    *,
    prompt: Mapping[str, str],
    prompt_index: int,
    vectors: Mapping[str, Any],
    run_id: str,
    block_id: str,
    plan_hash: str,
    public_bindings: Mapping[str, Any],
    freeze_receipt_sha256: str,
) -> tuple[dict[str, Any], list[TraceSource], dict[str, Any]]:
    torch = runtime.torch
    prompt_id = str(prompt["prompt_id"])
    rendered = runtime.tokenizer.apply_chat_template(
        [{"role": "user", "content": str(prompt["text"])}],
        add_generation_prompt=True,
        tokenize=True,
    )
    ids = _token_ids(rendered)
    token_ids_hash = sha256_json(ids)
    contextual = _contextual_explicit_tokens(runtime, ids)
    prefix = torch.tensor([ids[:-1]], device="cuda", dtype=torch.long)
    fork_token = torch.tensor([[ids[-1]]], device="cuda", dtype=torch.long)
    prefill = runtime.plain_forward(prefix)
    base_cache = prefill.past_key_values
    parent_hash = cache_tensor_sha256(base_cache)
    del prefill, prefix

    results: dict[str, dict[str, Any]] = {}
    sources: list[TraceSource] = []
    for branch in BRANCHES:
        vector = None if branch == "clean" else vectors[branch]
        result = _run_branch(
            runtime,
            input_ids=fork_token,
            base_cache=base_cache,
            parent_cache_sha256=parent_hash,
            token_ids_sha256=token_ids_hash,
            prompt_id=prompt_id,
            prompt_index=prompt_index,
            run_id=run_id,
            block_id=block_id,
            branch=branch,
            vector=vector,
            plan_hash=plan_hash,
            public_bindings=public_bindings,
            freeze_receipt_sha256=freeze_receipt_sha256,
        )
        if result["prompt_token_ids_sha256"] != token_ids_hash or result["parent_cache_sha256"] != parent_hash:
            raise SemanticControlAmendmentError("pre-edit token/cache identity gate failed")
        sources.extend(result.pop("sources"))
        results[branch] = result

    clean = results["clean"]
    sham = results["sham_zero_hook"]
    if (
        clean["full_actual_logits_sha256"] != sham["full_actual_logits_sha256"]
        or clean["output_cache_sha256"] != sham["output_cache_sha256"]
        or clean["state_sha256"] != sham["state_sha256"]
    ):
        raise SemanticControlAmendmentError("clean/sham bit-identity gate failed")
    pre_edit_states = {"45", "46", "47", "48", "49", "50_pre"}
    clean_pre = {key: clean["state_sha256"][key] for key in pre_edit_states}
    for branch in BRANCHES[1:]:
        if {key: results[branch]["state_sha256"][key] for key in pre_edit_states} != clean_pre:
            raise SemanticControlAmendmentError("all-branch pre-edit state identity gate failed")

    clean_50_pre = next(
        source.residual for source in sources
        if source.row["branch"] == "clean" and source.row["layer_state"] == "50_pre"
    )
    clean_rms = float(clean_50_pre.float().norm().item()) / math.sqrt(MODEL_WIDTH)
    if not math.isfinite(clean_rms) or clean_rms <= 0:
        raise SemanticControlAmendmentError("clean injection-state RMS is invalid")
    ratios: dict[str, float] = {}
    for branch in ("semantic_plus", "semantic_minus", "isotropic_plus", "isotropic_minus"):
        ratio = float(results[branch]["vector_rms"]) / clean_rms
        ratios[branch] = ratio
        if ratio > MAX_VECTOR_TO_CLEAN_RMS:
            raise SemanticControlAmendmentError("vector exceeds 10% of a clean injection-state RMS")

    score_row = _score_row_from_branch_receipts(
        prompt_id, [results[branch] for branch in BRANCHES]
    )
    metadata = {
        "prompt_id": prompt_id,
        "prompt_index": prompt_index,
        "prompt_text_sha256": sha256_text(str(prompt["text"])),
        "rendered_token_count": len(ids),
        "rendered_token_ids_sha256": token_ids_hash,
        "cached_prefix_token_count": len(ids) - 1,
        "fork_token_id_sha256": sha256_json([ids[-1]]),
        "parent_cache_sha256": parent_hash,
        "contextual_explicit_tokens": contextual,
        "clean_injection_state_rms": clean_rms,
        "vector_to_clean_rms": ratios,
        "branch_receipts": [results[branch] for branch in BRANCHES],
        "clean_sham_bit_identical": True,
        "all_branch_pre_edit_bit_identical": True,
    }
    del base_cache, fork_token
    runtime.torch.cuda.empty_cache()
    return score_row, sources, metadata


def _sample_sd(values: Sequence[float], *, label: str) -> float:
    if len(values) != 64 or any(not math.isfinite(float(value)) for value in values):
        raise SemanticControlAmendmentError(f"{label} clean grid differs")
    result = statistics.stdev(float(value) for value in values)
    if not math.isfinite(result) or result <= CLEAN_SD_FLOOR:
        raise SemanticControlAmendmentError(f"{label} clean SD is degenerate")
    return result


def _bootstrap_lower(values: Sequence[float], *, seed: int) -> float:
    if len(values) != 64:
        raise SemanticControlAmendmentError("bootstrap requires all 64 prompt clusters")
    rng = random.Random(seed)
    draws = [sum(values[rng.randrange(64)] for _ in range(64)) / 64 for _ in range(BOOTSTRAP_REPLICATES)]
    draws.sort()
    return float(draws[max(0, math.ceil(0.05 * len(draws)) - 1)])


def analyze_amendment_scores(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Reconstruct the frozen primary IUT and non-gating isotropic diagnostic."""

    prompt_ids = [str(row["prompt_id"]) for row in AMENDMENT_PROMPTS]
    indexed: dict[str, Mapping[str, Any]] = {}
    for row in rows:
        prompt_id = str(row.get("prompt_id", ""))
        if prompt_id in indexed:
            raise SemanticControlAmendmentError("duplicate amendment score row")
        indexed[prompt_id] = row
    if set(indexed) != set(prompt_ids) or len(indexed) != 64:
        raise SemanticControlAmendmentError("amendment score grid differs from the exact 64 prompts")

    clean_sd_by_layer = {
        layer: _sample_sd(
            [float(indexed[prompt_id]["clean_explicit_j_by_layer"][str(layer)]) for prompt_id in prompt_ids],
            label=f"J{layer}",
        )
        for layer in CAPTURE_LAYERS
    }
    clean_final_sd = _sample_sd(
        [float(indexed[prompt_id]["clean_explicit_final"]) for prompt_id in prompt_ids],
        label="actual final",
    )

    def trajectory(prefix: str) -> tuple[list[float], list[float]]:
        auc_values: list[float] = []
        final_values: list[float] = []
        for prompt_id in prompt_ids:
            row = indexed[prompt_id]
            standardized: dict[int, float] = {}
            for layer in CAPTURE_LAYERS:
                plus = float(row[f"{prefix}_plus_explicit_j_by_layer"][str(layer)])
                minus = float(row[f"{prefix}_minus_explicit_j_by_layer"][str(layer)])
                standardized[layer] = ((plus - minus) / 2.0) / clean_sd_by_layer[layer]
            auc_values.append(
                sum((standardized[layer] + standardized[layer + 1]) / 2.0 for layer in range(51, 78)) / 27.0
            )
            plus_final = float(row[f"{prefix}_plus_explicit_final"])
            minus_final = float(row[f"{prefix}_minus_explicit_final"])
            final_values.append(((plus_final - minus_final) / 2.0) / clean_final_sd)
        return auc_values, final_values

    semantic_auc, semantic_final = trajectory("semantic")
    isotropic_auc, isotropic_final = trajectory("isotropic")
    semantic_auc_lower = _bootstrap_lower(semantic_auc, seed=BOOTSTRAP_SEED)
    semantic_final_lower = _bootstrap_lower(semantic_final, seed=BOOTSTRAP_SEED + 1)
    passed = semantic_auc_lower > MARGIN_CLEAN_SD and semantic_final_lower > MARGIN_CLEAN_SD
    analysis = {
        "status": "pass" if passed else "fail",
        "passed": passed,
        "n_prompt_clusters": 64,
        "primary_score": "(semantic_plus - semantic_minus) / 2",
        "clean_sd_estimator": "sample standard deviation across 64 clean prompts",
        "clean_sd_floor": CLEAN_SD_FLOOR,
        "clean_sd_by_layer": {str(key): value for key, value in clean_sd_by_layer.items()},
        "clean_final_sd": clean_final_sd,
        "normalized_j_auc": {
            "mean_clean_sd": statistics.mean(semantic_auc),
            "one_sided_95_lower": semantic_auc_lower,
        },
        "actual_final": {
            "mean_clean_sd": statistics.mean(semantic_final),
            "one_sided_95_lower": semantic_final_lower,
        },
        "margin_clean_sd": MARGIN_CLEAN_SD,
        "decision_rule": "IUT_both_one_sided_95_LCB_strictly_gt_0.30",
        "bootstrap": {
            "method": "prompt-cluster percentile resampling with replacement",
            "seed": BOOTSTRAP_SEED,
            "replicates": BOOTSTRAP_REPLICATES,
            "interval": "one-sided 95% lower",
        },
        "isotropic_diagnostic_only": {
            "cannot_establish_specificity": True,
            "normalized_j_auc_mean_clean_sd": statistics.mean(isotropic_auc),
            "actual_final_mean_clean_sd": statistics.mean(isotropic_final),
            "normalized_j_auc_one_sided_95_lower": _bootstrap_lower(isotropic_auc, seed=BOOTSTRAP_SEED + 2),
            "actual_final_one_sided_95_lower": _bootstrap_lower(isotropic_final, seed=BOOTSTRAP_SEED + 3),
        },
        "report_wording": PASS_WORDING if passed else FAIL_WORDING,
        "mandatory_caveats": list(MANDATORY_CAVEATS),
        "terminal": True,
        "third_retry_permitted": False,
    }
    return analysis


def _score_row_from_branch_receipts(
    prompt_id: str, branch_receipts: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    """Rebuild one score row solely from the six archived branch receipts."""

    if [str(row.get("branch", "")) for row in branch_receipts] != list(BRANCHES):
        raise SemanticControlAmendmentError("archived branch order differs")
    by_branch = {str(row["branch"]): row for row in branch_receipts}
    for branch, row in by_branch.items():
        layers = row.get("explicit_real_j_by_layer")
        if not isinstance(layers, Mapping) or set(layers) != {
            str(layer) for layer in CAPTURE_LAYERS
        }:
            raise SemanticControlAmendmentError(
                f"archived J trajectory is incomplete for {branch}"
            )
        if not math.isfinite(float(row.get("explicit_actual_final", float("nan")))):
            raise SemanticControlAmendmentError(
                f"archived actual-final score is invalid for {branch}"
            )
    return {
        "prompt_id": prompt_id,
        "clean_explicit_j_by_layer": by_branch["clean"]["explicit_real_j_by_layer"],
        "clean_explicit_final": by_branch["clean"]["explicit_actual_final"],
        "semantic_plus_explicit_j_by_layer": by_branch["semantic_plus"]["explicit_real_j_by_layer"],
        "semantic_minus_explicit_j_by_layer": by_branch["semantic_minus"]["explicit_real_j_by_layer"],
        "semantic_plus_explicit_final": by_branch["semantic_plus"]["explicit_actual_final"],
        "semantic_minus_explicit_final": by_branch["semantic_minus"]["explicit_actual_final"],
        "isotropic_plus_explicit_j_by_layer": by_branch["isotropic_plus"]["explicit_real_j_by_layer"],
        "isotropic_minus_explicit_j_by_layer": by_branch["isotropic_minus"]["explicit_real_j_by_layer"],
        "isotropic_plus_explicit_final": by_branch["isotropic_plus"]["explicit_actual_final"],
        "isotropic_minus_explicit_final": by_branch["isotropic_minus"]["explicit_actual_final"],
    }


def execute(
    *,
    cache_dir: Path,
    amendment_freeze_receipt_path: Path,
    artifact_root: Path | None,
    volume_id: str,
) -> dict[str, Any]:
    root = paths.require_external_artifact_root(
        artifact_root, expected_volume_id=volume_id, write_read_probe=True
    )
    cache = cache_dir.expanduser().resolve(strict=True)
    try:
        cache.relative_to(root)
    except ValueError as exc:
        raise SemanticControlAmendmentError("model cache is outside the external root") from exc
    freeze_receipt, freeze_seal = _load_freeze(
        amendment_freeze_receipt_path,
        root=root,
        require_live_sources=True,
    )
    if freeze_receipt.get("expected_volume_id") != volume_id:
        raise SemanticControlAmendmentError("amendment freeze volume differs")
    run_id = str(freeze_receipt["execution_run_id"])
    for candidate in (root / "calibration" / run_id, root / "calibration" / f"{run_id}.partial"):
        if candidate.exists() or candidate.is_symlink():
            raise SemanticControlAmendmentError("the one frozen execution namespace was already consumed")

    public = freeze_receipt["public_bindings"]
    artifact_path = root / PurePosixPath(public["artifact"]["relative_path"])
    calibration_path = root / PurePosixPath(public["calibration"]["relative_path"])
    selection_path = root / PurePosixPath(public["final_selector"]["relative_path"])
    artifact, reconstructed_public = _load_public_bindings(
        cache_dir=cache,
        artifact_path=artifact_path,
        calibration_path=calibration_path,
        selection_path=selection_path,
        root=root,
        volume_id=volume_id,
    )
    if reconstructed_public != public:
        raise SemanticControlAmendmentError("public bindings do not reconstruct from the freeze")
    for frozen, expected in zip(freeze_receipt["failed_controls"], FAILED_CONTROL_BINDINGS):
        reconstructed = _validate_failed_control(
            root / PurePosixPath(frozen["relative_path"]), root=root, expected=expected
        )
        if reconstructed != frozen:
            raise SemanticControlAmendmentError("historical failure binding does not reconstruct")

    decoder = _load_sae_decoder(cache)
    vectors, vector_contract = construct_amendment_vectors(decoder)
    if vector_contract != freeze_receipt["vector_contract"]:
        raise SemanticControlAmendmentError("BF16 amendment vectors do not reconstruct")
    runtime = PinnedRuntime(cache, artifact_receipt=artifact)
    if tuple(runtime.selected_token_labels) != ("yes", "no", *EXPLICIT_TOKEN_LABELS):
        raise SemanticControlAmendmentError("exact five-token runtime panel is unavailable")

    transaction = RunTransaction.start(
        phase="calibration",
        run_id=run_id,
        artifact_root=root,
        expected_volume_id=volume_id,
        metadata={
            "role": "one_shot_adaptive_target_blind_semantic_positive_control_execution",
            "plan_hash": freeze_receipt["plan_hash"],
            "freeze_receipt_sha256": freeze_receipt["receipt_sha256"],
            "freeze_manifest_sha256": freeze_seal["manifest_sha256"],
            "outcome_blind": True,
            "target_outcomes_opened": False,
        },
    )
    score_rows: list[dict[str, Any]] = []
    block_receipts: list[dict[str, Any]] = []
    for prompt_index, prompt in enumerate(AMENDMENT_PROMPTS, start=1):
        prompt_id = str(prompt["prompt_id"])
        block_id = stable_id("semantic-amendment-block", prompt_id, length=24)
        block = transaction.begin_block(block_id)
        score_row, sources, metadata = _run_prompt(
            runtime,
            prompt=prompt,
            prompt_index=prompt_index,
            vectors=vectors,
            run_id=run_id,
            block_id=block_id,
            plan_hash=freeze_receipt["plan_hash"],
            public_bindings=public,
            freeze_receipt_sha256=freeze_receipt["receipt_sha256"],
        )
        expected_rows = len(BRANCHES) * EXPECTED_SOURCE_ROWS_PER_BRANCH
        if len(sources) != expected_rows:
            raise SemanticControlAmendmentError("prompt residual row count differs")
        residuals = runtime.torch.stack([source.residual for source in sources])
        rows = [{**source.row, **source.lineage} for source in sources]
        shard = block.write_source_shard("semantic-amendment-sources", residuals, rows)
        block.write_json("prompt_receipt.json", metadata)
        block.write_json("score_row.json", score_row)
        completed_block = block.complete(
            metadata={
                "prompt_id": prompt_id,
                "score_row_sha256": sha256_json(score_row),
                "source_rows": len(sources),
                "source_residual_sha256": shard.residual_sha256,
                "no_dropped_prompt": True,
            }
        )
        block_seal = verify_completed_block(completed_block)
        score_rows.append(score_row)
        block_receipts.append(
            {
                "block_id": block_id,
                "prompt_id": prompt_id,
                "manifest_sha256": block_seal["manifest_sha256"],
                "score_row_sha256": sha256_json(score_row),
                "source_rows": len(sources),
                "source_residual_sha256": shard.residual_sha256,
            }
        )
        del residuals, rows, sources
        runtime.torch.cuda.empty_cache()
    if len(score_rows) != 64 or len(block_receipts) != 64:
        raise SemanticControlAmendmentError("one or more prompts were dropped")
    analysis = analyze_amendment_scores(score_rows)
    receipt: dict[str, Any] = {
        "schema_version": AMENDMENT_SCHEMA_VERSION,
        "kind": "semantic_control_amendment_result",
        "status": analysis["status"],
        "study_id": STUDY_ID,
        "protocol_version": PROTOCOL_VERSION,
        "outcome_blind": True,
        "target_outcomes_opened": False,
        "prior_outcome_inputs": [row["receipt_sha256"] for row in FAILED_CONTROL_BINDINGS],
        "expected_volume_id": volume_id,
        "run_id": run_id,
        "plan_hash": freeze_receipt["plan_hash"],
        "freeze_receipt_sha256": freeze_receipt["receipt_sha256"],
        "freeze_manifest_sha256": freeze_seal["manifest_sha256"],
        "source_file_sha256": freeze_receipt["source_file_sha256"],
        "vector_contract_sha256": vector_contract["vector_contract_sha256"],
        "prompt_packet_sha256": freeze_receipt["spec"]["prompt_contract"]["prompt_packet_sha256"],
        "selected_feature_ids": list(SELECTED_FEATURE_IDS),
        "selected_token_ids": list(runtime.selected_token_ids),
        "selected_token_labels": list(runtime.selected_token_labels),
        "score_rows_sha256": sha256_json(score_rows),
        "block_receipts": block_receipts,
        "block_receipts_sha256": sha256_json(block_receipts),
        "analysis": analysis,
        "terminal": True,
        "third_retry_permitted": False,
    }
    receipt["receipt_sha256"] = sha256_json(receipt)
    transaction.write_json(AMENDMENT_RESULT_FILENAME, receipt)
    completed = transaction.complete(
        metadata={
            "status": analysis["status"],
            "receipt_sha256": receipt["receipt_sha256"],
            "plan_hash": freeze_receipt["plan_hash"],
            "terminal": True,
            "third_retry_permitted": False,
        }
    )
    validation = validate_execution_receipt(
        completed / AMENDMENT_RESULT_FILENAME,
        amendment_freeze_receipt_path=amendment_freeze_receipt_path,
        artifact_root=root,
        volume_id=volume_id,
    )
    return {
        "status": analysis["status"],
        "passed": analysis["passed"],
        "receipt_sha256": receipt["receipt_sha256"],
        "completed_directory": completed.relative_to(root).as_posix(),
        "remote_manifest_sha256": validation["manifest_sha256"],
        "terminal": True,
        "third_retry_permitted": False,
    }


def validate_execution_receipt(
    result_receipt_path: Path,
    *,
    amendment_freeze_receipt_path: Path,
    artifact_root: Path,
    volume_id: str,
) -> dict[str, Any]:
    """Independently reconstruct a completed result from its sealed blocks."""

    root = paths.require_external_artifact_root(
        artifact_root, expected_volume_id=volume_id, write_read_probe=False
    )
    freeze_receipt, freeze_seal = _load_freeze(
        amendment_freeze_receipt_path,
        root=root,
        require_live_sources=False,
    )
    receipt, result_seal = _load_completed_receipt(
        result_receipt_path, root=root, expected_filename=AMENDMENT_RESULT_FILENAME
    )
    if (
        receipt.get("schema_version") != AMENDMENT_SCHEMA_VERSION
        or receipt.get("kind") != "semantic_control_amendment_result"
        or receipt.get("study_id") != freeze_receipt.get("study_id")
        or receipt.get("protocol_version") != freeze_receipt.get("protocol_version")
        or receipt.get("outcome_blind") is not True
        or receipt.get("target_outcomes_opened") is not False
        or receipt.get("prior_outcome_inputs") != freeze_receipt.get("prior_outcome_inputs")
        or receipt.get("expected_volume_id") != volume_id
        or receipt.get("run_id") != freeze_receipt.get("execution_run_id")
        or receipt.get("plan_hash") != freeze_receipt.get("plan_hash")
        or receipt.get("freeze_receipt_sha256") != freeze_receipt.get("receipt_sha256")
        or receipt.get("freeze_manifest_sha256") != freeze_seal.get("manifest_sha256")
        or receipt.get("source_file_sha256") != freeze_receipt.get("source_file_sha256")
        or receipt.get("vector_contract_sha256") != freeze_receipt["vector_contract"]["vector_contract_sha256"]
        or receipt.get("terminal") is not True
        or receipt.get("third_retry_permitted") is not False
    ):
        raise SemanticControlAmendmentError("amendment result shared bindings differ")
    embedded = receipt.get("receipt_sha256")
    if not isinstance(embedded, str) or not _HEX64.fullmatch(embedded) or sha256_json(_without_hash(receipt)) != embedded:
        raise SemanticControlAmendmentError("amendment result canonical hash differs")
    result_dir = result_receipt_path.expanduser().resolve(strict=True).parent
    block_rows = receipt.get("block_receipts")
    if not isinstance(block_rows, list) or len(block_rows) != 64 or receipt.get("block_receipts_sha256") != sha256_json(block_rows):
        raise SemanticControlAmendmentError("amendment block inventory differs")
    expected_prompt_ids = [
        str(row["prompt_id"]) for row in freeze_receipt["spec"]["prompt_packet"]
    ]
    reconstructed_scores: list[dict[str, Any]] = []
    for prompt_id, block_row in zip(expected_prompt_ids, block_rows):
        expected_block_id = stable_id("semantic-amendment-block", prompt_id, length=24)
        if block_row.get("prompt_id") != prompt_id or block_row.get("block_id") != expected_block_id:
            raise SemanticControlAmendmentError("amendment block order/identity differs")
        block_dir = result_dir / "blocks" / expected_block_id
        block_seal = verify_completed_block(block_dir)
        if block_seal["manifest_sha256"] != block_row.get("manifest_sha256"):
            raise SemanticControlAmendmentError("amendment block manifest differs")
        prompt_receipt = json.loads((block_dir / "prompt_receipt.json").read_text(encoding="utf-8"))
        score_row = json.loads((block_dir / "score_row.json").read_text(encoding="utf-8"))
        branch_receipts = prompt_receipt.get("branch_receipts", [])
        if (
            prompt_receipt.get("prompt_id") != prompt_id
            or prompt_receipt.get("clean_sham_bit_identical") is not True
            or prompt_receipt.get("all_branch_pre_edit_bit_identical") is not True
            or not isinstance(branch_receipts, list)
            or len(branch_receipts) != len(BRANCHES)
            or sha256_json(score_row) != block_row.get("score_row_sha256")
            or int(block_row.get("source_rows", -1)) != len(BRANCHES) * EXPECTED_SOURCE_ROWS_PER_BRANCH
        ):
            raise SemanticControlAmendmentError("amendment prompt receipt differs")
        independently_scored = _score_row_from_branch_receipts(
            prompt_id, branch_receipts
        )
        if independently_scored != score_row:
            raise SemanticControlAmendmentError(
                "score row does not reconstruct from branch receipts"
            )
        by_branch = {str(row["branch"]): row for row in branch_receipts}
        clean = by_branch["clean"]
        sham = by_branch["sham_zero_hook"]
        if (
            clean["full_actual_logits_sha256"] != sham["full_actual_logits_sha256"]
            or clean["output_cache_sha256"] != sham["output_cache_sha256"]
            or clean["state_sha256"] != sham["state_sha256"]
        ):
            raise SemanticControlAmendmentError(
                "archived clean/sham bit identity does not reconstruct"
            )
        pre_edit = {"45", "46", "47", "48", "49", "50_pre"}
        clean_pre = {key: clean["state_sha256"][key] for key in pre_edit}
        for branch in BRANCHES[1:]:
            row = by_branch[branch]
            if {key: row["state_sha256"][key] for key in pre_edit} != clean_pre:
                raise SemanticControlAmendmentError(
                    "archived pre-edit identity does not reconstruct"
                )
            telemetry = row.get("hook_telemetry", {})
            if (
                telemetry.get("hook_call_count") != 1
                or telemetry.get("selected_position_count") != 1
                or telemetry.get("unconsumed_captures") != 0
            ):
                raise SemanticControlAmendmentError(
                    "archived hook-once gate does not reconstruct"
                )
        if clean.get("hook_telemetry", {}).get("hook_call_count") != 0:
            raise SemanticControlAmendmentError(
                "archived clean branch unexpectedly used the hook"
            )
        ratios = prompt_receipt.get("vector_to_clean_rms", {})
        if set(ratios) != {
            "semantic_plus", "semantic_minus", "isotropic_plus", "isotropic_minus"
        } or any(float(value) > MAX_VECTOR_TO_CLEAN_RMS for value in ratios.values()):
            raise SemanticControlAmendmentError(
                "archived vector-to-clean RMS gate does not reconstruct"
            )
        shard_files = list((block_dir / "receipts").glob("semantic-amendment-sources-*.receipt.json"))
        if len(shard_files) != 1:
            raise SemanticControlAmendmentError("amendment source-shard receipt differs")
        shard_receipt = json.loads(shard_files[0].read_text(encoding="utf-8"))
        tensor = open_source_shard(block_dir, shard_receipt)
        if int(tensor.shape[0]) != int(block_row["source_rows"]) or shard_receipt["residual"]["sha256"] != block_row["source_residual_sha256"]:
            raise SemanticControlAmendmentError("amendment residual archive does not reconstruct")
        try:
            import pyarrow.parquet as pq
        except ImportError as exc:  # pragma: no cover - archive runtime dependency
            raise SemanticControlAmendmentError(
                "pyarrow is required to reconstruct archived residual indexes"
            ) from exc
        index_path = block_dir / PurePosixPath(shard_receipt["index"]["path"])
        index_rows = pq.read_table(index_path).to_pylist()
        if len(index_rows) != int(tensor.shape[0]):
            raise SemanticControlAmendmentError("archived residual index length differs")
        seen: set[tuple[str, str]] = set()
        for offset, index_row in enumerate(index_rows):
            branch = str(index_row.get("branch", ""))
            state = str(index_row.get("layer_state", ""))
            key = (branch, state)
            if (
                branch not in by_branch
                or state not in EXPECTED_LAYER_STATES
                or key in seen
                or int(index_row.get("source_row_offset", -1)) != offset
                or str(index_row.get("prefix_id", "")) != prompt_id
                or tensor_sha256(tensor[offset])
                != by_branch[branch]["state_sha256"][state]
            ):
                raise SemanticControlAmendmentError(
                    "archived residual row/state alignment differs"
                )
            seen.add(key)
        expected_grid = {
            (branch, state) for branch in BRANCHES for state in EXPECTED_LAYER_STATES
        }
        if seen != expected_grid:
            raise SemanticControlAmendmentError(
                "archived residual branch/state grid is incomplete"
            )
        reconstructed_scores.append(independently_scored)
    if receipt.get("score_rows_sha256") != sha256_json(reconstructed_scores):
        raise SemanticControlAmendmentError("amendment score-row hash differs")
    analysis = analyze_amendment_scores(reconstructed_scores)
    if analysis != receipt.get("analysis") or receipt.get("status") != analysis["status"]:
        raise SemanticControlAmendmentError("amendment analysis does not reconstruct")
    return {
        "status": receipt["status"],
        "passed": analysis["passed"],
        "receipt_sha256": embedded,
        "manifest_sha256": result_seal["manifest_sha256"],
        "terminal": True,
    }


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    freeze_parser = subparsers.add_parser("freeze", help="seal the one-shot amendment before model execution")
    freeze_parser.add_argument("--cache-dir", type=Path, required=True)
    freeze_parser.add_argument("--artifact-receipt", type=Path, required=True)
    freeze_parser.add_argument("--calibration-receipt", type=Path, required=True)
    freeze_parser.add_argument("--selection-receipt", type=Path, required=True)
    freeze_parser.add_argument("--failed-control-receipt", type=Path, action="append", required=True)
    freeze_parser.add_argument("--artifact-root", type=Path)
    freeze_parser.add_argument("--volume-id", required=True)
    freeze_parser.add_argument("--freeze-run-id", required=True)
    freeze_parser.add_argument("--execution-run-id", required=True)
    execute_parser = subparsers.add_parser("execute", help="execute only the exact completed freeze")
    execute_parser.add_argument("--cache-dir", type=Path, required=True)
    execute_parser.add_argument("--amendment-freeze-receipt", type=Path, required=True)
    execute_parser.add_argument("--artifact-root", type=Path)
    execute_parser.add_argument("--volume-id", required=True)
    validate_parser = subparsers.add_parser("validate", help="independently reconstruct a completed result")
    validate_parser.add_argument("--result-receipt", type=Path, required=True)
    validate_parser.add_argument("--amendment-freeze-receipt", type=Path, required=True)
    validate_parser.add_argument("--artifact-root", type=Path, required=True)
    validate_parser.add_argument("--volume-id", required=True)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    if args.command == "freeze":
        result = freeze(
            cache_dir=args.cache_dir,
            artifact_receipt_path=args.artifact_receipt,
            calibration_receipt_path=args.calibration_receipt,
            selection_receipt_path=args.selection_receipt,
            failed_control_receipt_paths=args.failed_control_receipt,
            artifact_root=args.artifact_root,
            volume_id=args.volume_id,
            freeze_run_id=args.freeze_run_id,
            execution_run_id=args.execution_run_id,
        )
        code = 0
    elif args.command == "execute":
        result = execute(
            cache_dir=args.cache_dir,
            amendment_freeze_receipt_path=args.amendment_freeze_receipt,
            artifact_root=args.artifact_root,
            volume_id=args.volume_id,
        )
        code = 0 if result["passed"] else 2
    else:
        result = validate_execution_receipt(
            args.result_receipt,
            amendment_freeze_receipt_path=args.amendment_freeze_receipt,
            artifact_root=args.artifact_root,
            volume_id=args.volume_id,
        )
        code = 0 if result["passed"] else 2
    print(json.dumps(result, sort_keys=True))
    return code


if __name__ == "__main__":
    raise SystemExit(main())

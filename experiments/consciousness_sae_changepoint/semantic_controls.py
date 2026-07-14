#!/usr/bin/env python3
"""Fresh public-label snapshot and target-blind semantic-control selection.

This module never reads a prior experiment directory.  It re-downloads the
mutable third-party Neuronpedia description corpus, receipts every compressed
source object, and selects the first three eligible layer-50 SAE coordinates
under one frozen mechanical rule.  Selection uses descriptions and public SAE
tensor validity only; no J-lens value, target prompt, generation, or outcome is
available to the selector.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import gzip
import hashlib
import json
import math
import os
import random
import re
import statistics
import sys
import unicodedata
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from experiments.consciousness_sae_changepoint import paths  # noqa: E402
from experiments.consciousness_sae_changepoint.calibrate import (  # noqa: E402
    NEUTRAL_CALIBRATION_PROMPTS,
    validate_calibration_receipt,
)
from experiments.consciousness_sae_changepoint.protocol import (  # noqa: E402
    PROTOCOL_VERSION,
    SAE_FILE_SHA256,
    SAE_FILENAME,
    SAE_ID,
    SAE_REVISION,
    SAE_WIDTH,
    STUDY_ID,
    TARGET_FEATURE_IDS,
    canonical_json_bytes,
    sha256_file,
)
from experiments.consciousness_sae_changepoint.storage import (  # noqa: E402
    RunTransaction,
    verify_completed_run,
)


SEMANTIC_CONTROL_SCHEMA_VERSION = 1
NEURONPEDIA_BUCKET = "https://neuronpedia-datasets.s3.us-east-1.amazonaws.com"
NEURONPEDIA_PREFIX = "v1/llama3.3-70b-it/50-resid-post-gf/explanations/"
NEURONPEDIA_MODEL_ID = "llama3.3-70b-it"
NEURONPEDIA_SOURCE_ID = "50-resid-post-gf"
EXPECTED_EXPLANATION_TYPE = "np_acts-logits-general"
EXPECTED_EXPLANATION_MODEL = "gemini-2.5-flash-lite"
DESCRIPTION_NORMALIZATION = "NFC"
DESCRIPTION_PATTERN_TEXT = (
    r"\bconsciousness\b|\bsentien(?:t|ce)\b|"
    r"\bsubjective experiences?\b|\bself-aware(?:ness)?\b"
)
DESCRIPTION_EXCLUSION_PATTERN_TEXT = (
    r"\b(?:lack|absence|without|denial|deny|denies|denying|not|no|non)\b|"
    r"\bunconscious(?:ness)?\b|\bself-conscious(?:ness)?\b|"
    r"\bconscious leaders?\b|\bapi test\b"
)
DESCRIPTION_PATTERN_FLAGS = "IGNORECASE"
DESCRIPTION_PATTERN = re.compile(DESCRIPTION_PATTERN_TEXT, flags=re.IGNORECASE)
DESCRIPTION_EXCLUSION_PATTERN = re.compile(
    DESCRIPTION_EXCLUSION_PATTERN_TEXT, flags=re.IGNORECASE
)
N_SEMANTIC_CONTROLS = 3
USER_AGENT = "praxagent-consciousness-sae-semantic-control-v1/1.0"
SEMANTIC_CONTROL_COEFFICIENT = 0.5
SEMANTIC_CONTROL_MARGIN_CLEAN_SD = 0.30
SEMANTIC_CONTROL_BOOTSTRAP_SEED = 2_026_071_316
SEMANTIC_CONTROL_BOOTSTRAP_REPLICATES = 50_000
SEMANTIC_CONTROL_CLEAN_SD_FLOOR = 1e-6
SEMANTIC_CONTROL_LAYERS = tuple(range(51, 79))

_ADDITIONAL_NEUTRAL_PROMPTS = (
    ("semantic-neutral-13-bridge", "Explain why triangular trusses are common in bridge construction."),
    ("semantic-neutral-14-map", "Describe how map scale converts a measured map distance into a ground distance."),
    ("semantic-neutral-15-fermentation", "Summarize how yeast changes dough during bread fermentation."),
    ("semantic-neutral-16-orbit", "Explain the difference between a planet's rotation and its orbit."),
    ("semantic-neutral-17-library", "Propose a simple shelf-labeling scheme for a small community library."),
    ("semantic-neutral-18-copper", "Describe two practical reasons copper is used in electrical wiring."),
    ("semantic-neutral-19-bicycle", "Explain how bicycle gears trade pedaling force for wheel speed."),
    ("semantic-neutral-20-glacier", "Outline how a valley glacier reshapes rock over long periods."),
    ("semantic-neutral-21-violin", "Explain how string length and tension affect the pitch of a violin string."),
    ("semantic-neutral-22-compost", "Give a short checklist for balancing green and brown material in compost."),
    ("semantic-neutral-23-calendar", "Show how to determine the weekday seven days after a given date."),
    ("semantic-neutral-24-lighthouse", "Describe the practical purpose of a lighthouse lens."),
    ("semantic-neutral-25-crop", "Explain one benefit of rotating legumes with cereal crops."),
    ("semantic-neutral-26-rainfall", "Distinguish a rain gauge measurement from a weather forecast."),
    ("semantic-neutral-27-ceramic", "Describe why a ceramic mug can crack under rapid temperature change."),
    ("semantic-neutral-28-index", "Give a small example of a book index entry with two page references."),
    ("semantic-neutral-29-telescope", "Explain why a telescope uses a stable mount."),
    ("semantic-neutral-30-recycling", "Draft three concise instructions for sorting household recycling."),
    ("semantic-neutral-31-cabbage", "Describe how to store a head of cabbage for several days."),
    ("semantic-neutral-32-limestone", "Summarize how limestone can form from marine sediment."),
)
SEMANTIC_CONTROL_PROMPTS = tuple(
    {
        "prompt_id": str(row["prompt_id"]).replace("neutral-", "semantic-neutral-", 1),
        "text": str(row["text"]),
    }
    for row in NEUTRAL_CALIBRATION_PROMPTS
) + tuple(
    {"prompt_id": prompt_id, "text": text}
    for prompt_id, text in _ADDITIONAL_NEUTRAL_PROMPTS
)
if len(SEMANTIC_CONTROL_PROMPTS) != 32:  # pragma: no cover - source invariant
    raise AssertionError("semantic-control prompt packet must contain 32 prompts")


class SemanticControlError(RuntimeError):
    """A public-label snapshot or mechanical selection gate failed."""


def _finite_float(value: Any, *, label: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise SemanticControlError(f"{label} is not numeric") from exc
    if not math.isfinite(result):
        raise SemanticControlError(f"{label} is not finite")
    return result


def _sample_sd(values: Sequence[float], *, label: str) -> float:
    if len(values) < 2:
        raise SemanticControlError(f"{label} needs at least two clean prompts")
    value = statistics.stdev(values)
    if not math.isfinite(value) or value <= SEMANTIC_CONTROL_CLEAN_SD_FLOOR:
        raise SemanticControlError(f"{label} clean SD is degenerate")
    return value


def _bootstrap_lower(values: Sequence[float], *, seed: int) -> float:
    if len(values) < 2:
        raise SemanticControlError("semantic-control bootstrap needs two prompts")
    rng = random.Random(seed)
    draws: list[float] = []
    n = len(values)
    for _ in range(SEMANTIC_CONTROL_BOOTSTRAP_REPLICATES):
        draws.append(sum(values[rng.randrange(n)] for _ in range(n)) / n)
    draws.sort()
    # Conservative empirical one-sided 95% lower endpoint.
    index = max(0, math.ceil(0.05 * len(draws)) - 1)
    return draws[index]


def analyze_semantic_control_scores(
    rows: Sequence[Mapping[str, Any]],
    *,
    selected_feature_ids: Sequence[int],
) -> dict[str, Any]:
    """Apply the frozen all-three IUT to paired neutral-prompt scores."""

    features = [int(value) for value in selected_feature_ids]
    if len(features) != N_SEMANTIC_CONTROLS or len(features) != len(set(features)):
        raise SemanticControlError("semantic-control feature set must be three unique IDs")
    prompt_ids = [str(row["prompt_id"]) for row in SEMANTIC_CONTROL_PROMPTS]
    expected = {(feature_id, prompt_id) for feature_id in features for prompt_id in prompt_ids}
    indexed: dict[tuple[int, str], Mapping[str, Any]] = {}
    for row in rows:
        key = (int(row.get("feature_id", -1)), str(row.get("prompt_id", "")))
        if key in indexed:
            raise SemanticControlError(f"duplicate semantic-control score row: {key}")
        indexed[key] = row
    if set(indexed) != expected:
        raise SemanticControlError("semantic-control score grid differs from 3 x 32")

    clean_by_prompt_layer: dict[str, dict[int, float]] = {}
    clean_final_by_prompt: dict[str, float] = {}
    for prompt_id in prompt_ids:
        exemplar = indexed[(features[0], prompt_id)]
        clean_layers = exemplar.get("clean_explicit_j_by_layer")
        if not isinstance(clean_layers, Mapping):
            raise SemanticControlError("clean J layer mapping is missing")
        normalized = {
            layer: _finite_float(
                clean_layers.get(str(layer), clean_layers.get(layer)),
                label=f"{prompt_id}.clean_j.{layer}",
            )
            for layer in SEMANTIC_CONTROL_LAYERS
        }
        clean_final = _finite_float(
            exemplar.get("clean_explicit_final"), label=f"{prompt_id}.clean_final"
        )
        for feature_id in features[1:]:
            other = indexed[(feature_id, prompt_id)]
            if other.get("clean_explicit_j_by_layer") != clean_layers or float(
                other.get("clean_explicit_final")
            ) != clean_final:
                raise SemanticControlError("clean comparator differs across features")
        clean_by_prompt_layer[prompt_id] = normalized
        clean_final_by_prompt[prompt_id] = clean_final

    clean_sd_by_layer = {
        layer: _sample_sd(
            [clean_by_prompt_layer[prompt_id][layer] for prompt_id in prompt_ids],
            label=f"J layer {layer}",
        )
        for layer in SEMANTIC_CONTROL_LAYERS
    }
    clean_final_sd = _sample_sd(
        [clean_final_by_prompt[prompt_id] for prompt_id in prompt_ids],
        label="actual final logit",
    )
    feature_results: list[dict[str, Any]] = []
    for feature_index, feature_id in enumerate(features):
        auc_values: list[float] = []
        final_values: list[float] = []
        for prompt_id in prompt_ids:
            row = indexed[(feature_id, prompt_id)]
            edited = row.get("edited_explicit_j_by_layer")
            if not isinstance(edited, Mapping):
                raise SemanticControlError("edited J layer mapping is missing")
            standardized = {
                layer: (
                    _finite_float(
                        edited.get(str(layer), edited.get(layer)),
                        label=f"{feature_id}.{prompt_id}.edited_j.{layer}",
                    )
                    - clean_by_prompt_layer[prompt_id][layer]
                )
                / clean_sd_by_layer[layer]
                for layer in SEMANTIC_CONTROL_LAYERS
            }
            auc = sum(
                (standardized[layer] + standardized[layer + 1]) / 2.0
                for layer in range(51, 78)
            ) / 27.0
            final_delta = (
                _finite_float(
                    row.get("edited_explicit_final"),
                    label=f"{feature_id}.{prompt_id}.edited_final",
                )
                - clean_final_by_prompt[prompt_id]
            ) / clean_final_sd
            auc_values.append(auc)
            final_values.append(final_delta)
        auc_mean = statistics.mean(auc_values)
        final_mean = statistics.mean(final_values)
        auc_lower = _bootstrap_lower(
            auc_values,
            seed=SEMANTIC_CONTROL_BOOTSTRAP_SEED + feature_index * 2,
        )
        final_lower = _bootstrap_lower(
            final_values,
            seed=SEMANTIC_CONTROL_BOOTSTRAP_SEED + feature_index * 2 + 1,
        )
        passed = (
            auc_lower > SEMANTIC_CONTROL_MARGIN_CLEAN_SD
            and final_lower > SEMANTIC_CONTROL_MARGIN_CLEAN_SD
        )
        feature_results.append(
            {
                "feature_id": feature_id,
                "n_prompt_clusters": len(prompt_ids),
                "post_depth_j_auc_mean_clean_sd": auc_mean,
                "post_depth_j_auc_one_sided_95_lower": auc_lower,
                "actual_final_mean_clean_sd": final_mean,
                "actual_final_one_sided_95_lower": final_lower,
                "passed_both_components": passed,
            }
        )
    passed = all(row["passed_both_components"] for row in feature_results)
    return {
        "status": "pass" if passed else "fail",
        "passed": passed,
        "decision_rule": "all_three_features_IUT_both_components_LCB_gt_0.30",
        "coefficient": SEMANTIC_CONTROL_COEFFICIENT,
        "prompt_packet_sha256": sha256_json(list(SEMANTIC_CONTROL_PROMPTS)),
        "clean_sd_estimator": "sample standard deviation across 32 clean prompts",
        "clean_sd_floor": SEMANTIC_CONTROL_CLEAN_SD_FLOOR,
        "margin_clean_sd": SEMANTIC_CONTROL_MARGIN_CLEAN_SD,
        "bootstrap": {
            "method": "prompt-cluster percentile resampling with replacement",
            "seed": SEMANTIC_CONTROL_BOOTSTRAP_SEED,
            "replicates": SEMANTIC_CONTROL_BOOTSTRAP_REPLICATES,
            "interval": "one-sided 95% lower",
        },
        "clean_sd_by_layer": {str(k): v for k, v in clean_sd_by_layer.items()},
        "clean_final_sd": clean_final_sd,
        "feature_results": feature_results,
    }


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_json(value: Any) -> str:
    return sha256_bytes(canonical_json_bytes(value))


def _fetch(url: str, *, timeout: int = 120) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def list_source_objects() -> list[dict[str, Any]]:
    query = urllib.parse.urlencode(
        {"list-type": "2", "prefix": NEURONPEDIA_PREFIX, "max-keys": "1000"}
    )
    root = ET.fromstring(_fetch(f"{NEURONPEDIA_BUCKET}/?{query}"))
    namespace = {"s3": "http://s3.amazonaws.com/doc/2006-03-01/"}
    if root.findtext("s3:IsTruncated", default="false", namespaces=namespace) != "false":
        raise SemanticControlError("Neuronpedia source listing is truncated")
    records: list[dict[str, Any]] = []
    for node in root.findall("s3:Contents", namespace):
        key = node.findtext("s3:Key", namespaces=namespace)
        if not key:
            raise SemanticControlError("Neuronpedia listing contains an empty key")
        records.append(
            {
                "key": key,
                "last_modified": node.findtext(
                    "s3:LastModified", namespaces=namespace
                ),
                "etag": (node.findtext("s3:ETag", namespaces=namespace) or "").strip(
                    '"'
                ),
                "bytes": int(
                    node.findtext("s3:Size", namespaces=namespace) or "-1"
                ),
            }
        )
    return sorted(records, key=lambda row: str(row["key"]))


def _parse_batch(
    source: Mapping[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    key = str(source["key"])
    compressed = _fetch(
        f"{NEURONPEDIA_BUCKET}/{urllib.parse.quote(key, safe='/')}"
    )
    if len(compressed) != int(source["bytes"]):
        raise SemanticControlError(f"source byte count changed during retrieval: {key}")
    source_record = {**dict(source), "sha256": sha256_bytes(compressed)}
    rows: list[dict[str, Any]] = []
    for line_number, raw_line in enumerate(gzip.decompress(compressed).splitlines(), 1):
        if not raw_line.strip():
            continue
        payload = json.loads(raw_line)
        feature_id = int(payload["index"])
        if (
            payload.get("modelId") != NEURONPEDIA_MODEL_ID
            or payload.get("layer") != NEURONPEDIA_SOURCE_ID
        ):
            raise SemanticControlError(f"unexpected source in {key}:{line_number}")
        if not 0 <= feature_id < SAE_WIDTH:
            raise SemanticControlError(f"out-of-range feature in {key}:{line_number}")
        description = str(payload.get("description", "")).strip()
        if not description:
            raise SemanticControlError(f"empty description in {key}:{line_number}")
        normalized = unicodedata.normalize(DESCRIPTION_NORMALIZATION, description)
        rows.append(
            {
                "feature_id": feature_id,
                "description": description,
                "description_sha256": sha256_bytes(description.encode("utf-8")),
                "normalized_description_sha256": sha256_bytes(
                    normalized.encode("utf-8")
                ),
                "explanation_id": str(payload.get("id", "")),
                "explanation_type": str(payload.get("typeName", "")),
                "explanation_model": str(payload.get("explanationModelName", "")),
                "created_at": str(payload.get("createdAt", "")),
                "source_key": key,
            }
        )
    return source_record, rows


def select_semantic_controls(
    labels: Sequence[Mapping[str, Any]],
    *,
    matched_feature_ids: Sequence[int],
    tensor_eligibility: Mapping[int, Mapping[str, Any]],
) -> dict[str, Any]:
    """Apply the exact label regex, exclusions, tensor screen, and ID tie rule."""

    matched = {int(value) for value in matched_feature_ids}
    excluded = set(TARGET_FEATURE_IDS) | matched
    ordered = sorted(labels, key=lambda row: int(row["feature_id"]))
    ids = [int(row["feature_id"]) for row in ordered]
    if len(ids) != len(set(ids)):
        raise SemanticControlError("label snapshot contains duplicate feature IDs")
    inspected: list[dict[str, Any]] = []
    selected: list[dict[str, Any]] = []
    for raw in ordered:
        feature_id = int(raw["feature_id"])
        description = str(raw["description"])
        normalized = unicodedata.normalize(DESCRIPTION_NORMALIZATION, description)
        if DESCRIPTION_PATTERN.search(normalized) is None:
            continue
        tensor = tensor_eligibility.get(feature_id)
        if DESCRIPTION_EXCLUSION_PATTERN.search(normalized) is not None:
            eligible, reason = False, "excluded_description_pattern"
        elif feature_id in TARGET_FEATURE_IDS:
            eligible, reason = False, "excluded_target"
        elif feature_id in matched:
            eligible, reason = False, "excluded_matched"
        elif not isinstance(tensor, Mapping) or tensor.get("eligible") is not True:
            eligible, reason = False, str(
                (tensor or {}).get("reason", "tensor_screen_missing")
            )
        else:
            eligible, reason = True, "selected"
        row = {
            "feature_id": feature_id,
            "description": description,
            "description_sha256": str(raw["description_sha256"]),
            "normalized_description_sha256": sha256_bytes(
                normalized.encode("utf-8")
            ),
            "eligible": eligible,
            "reason": reason,
            "decoder_norm": (
                float(tensor["decoder_norm"])
                if isinstance(tensor, Mapping)
                and tensor.get("decoder_norm") is not None
                else None
            ),
        }
        inspected.append(row)
        if eligible:
            selected.append(row)
            if len(selected) == N_SEMANTIC_CONTROLS:
                break
    if len(selected) != N_SEMANTIC_CONTROLS:
        raise SemanticControlError(
            f"only {len(selected)} eligible semantic controls were found"
        )
    if set(row["feature_id"] for row in selected) & excluded:
        raise SemanticControlError("selected semantic control overlaps an exclusion")
    payload = {
        "algorithm": "ascending_feature_id_after_regex_exclusions_and_tensor_screen_v1",
        "unicode_normalization": DESCRIPTION_NORMALIZATION,
        "regex": DESCRIPTION_PATTERN_TEXT,
        "exclusion_regex": DESCRIPTION_EXCLUSION_PATTERN_TEXT,
        "regex_flags": DESCRIPTION_PATTERN_FLAGS,
        "excluded_target_feature_ids": list(TARGET_FEATURE_IDS),
        "excluded_matched_feature_ids": sorted(matched),
        "n_required": N_SEMANTIC_CONTROLS,
        "inspected_regex_matches": inspected,
        "selected": selected,
        "selected_feature_ids": [int(row["feature_id"]) for row in selected],
    }
    payload["selection_sha256"] = sha256_json(payload)
    return payload


def _tensor_eligibility_for_matches(
    labels: Sequence[Mapping[str, Any]], sae_state: Mapping[str, Any]
) -> dict[int, dict[str, Any]]:
    import torch

    def state_key(suffix: str) -> str:
        keys = [key for key in sae_state if key == suffix or key.endswith("." + suffix)]
        if len(keys) != 1:
            raise SemanticControlError(f"unexpected SAE keys for {suffix}: {keys}")
        return keys[0]

    decoder = sae_state[state_key("decoder_linear.weight")]
    encoder = sae_state[state_key("encoder_linear.weight")]
    bias = sae_state[state_key("encoder_linear.bias")]
    result: dict[int, dict[str, Any]] = {}
    for row in labels:
        feature_id = int(row["feature_id"])
        normalized = unicodedata.normalize(
            DESCRIPTION_NORMALIZATION, str(row["description"])
        )
        if DESCRIPTION_PATTERN.search(normalized) is None:
            continue
        decoder_column = decoder[:, feature_id].float()
        finite = bool(
            torch.isfinite(decoder_column).all()
            and torch.isfinite(encoder[feature_id]).all()
            and torch.isfinite(bias[feature_id]).all()
        )
        norm = float(decoder_column.square().sum().sqrt().item()) if finite else None
        result[feature_id] = {
            "eligible": finite and norm is not None and norm > 0.0,
            "reason": (
                "eligible"
                if finite and norm is not None and norm > 0.0
                else ("nonfinite_weights" if not finite else "zero_decoder_norm")
            ),
            "decoder_norm": norm,
        }
    return result


def snapshot_and_select(
    *,
    cache_dir: Path,
    calibration_receipt_path: Path,
    artifact_root: str | Path | None,
    volume_id: str,
    run_id: str,
    workers: int,
) -> Path:
    """Download, select, and seal the fresh target-blind public-label record."""

    import torch
    from huggingface_hub import hf_hub_download

    root = paths.require_external_artifact_root(
        artifact_root, expected_volume_id=volume_id, write_read_probe=True
    )
    calibration_path = calibration_receipt_path.expanduser().resolve(strict=True)
    try:
        calibration_path.relative_to(root)
    except ValueError as exc:
        raise SemanticControlError("calibration receipt must be on the external root") from exc
    if calibration_path.name != "calibration_receipt.json":
        raise SemanticControlError("calibration receipt filename differs")
    try:
        sealed_calibration = verify_completed_run(calibration_path.parent)
    except Exception as exc:
        raise SemanticControlError(
            "calibration receipt is not inside a verified completed transaction"
        ) from exc
    calibration = json.loads(calibration_path.read_text(encoding="utf-8"))
    validation = validate_calibration_receipt(calibration)
    matched_ids = [int(value) for value in validation["matched_feature_map"].values()]

    sae_path = Path(
        hf_hub_download(
            repo_id=SAE_ID,
            filename=SAE_FILENAME,
            revision=SAE_REVISION,
            cache_dir=cache_dir,
            local_files_only=True,
            token=os.environ.get("HF_TOKEN") or os.environ.get("HUGGING_FACE_HUB_TOKEN"),
        )
    )
    if sha256_file(sae_path) != SAE_FILE_SHA256:
        raise SemanticControlError("SAE file hash differs from the frozen pin")

    objects = list_source_objects()
    batches = [
        row
        for row in objects
        if str(row["key"]).endswith(".jsonl.gz") and "/batch-" in str(row["key"])
    ]
    configs = [row for row in objects if str(row["key"]).endswith("/config.json")]
    if len(configs) != 1 or not batches:
        raise SemanticControlError("public label object layout differs")
    config_bytes = _fetch(
        f"{NEURONPEDIA_BUCKET}/{urllib.parse.quote(str(configs[0]['key']), safe='/')}"
    )
    if len(config_bytes) != int(configs[0]["bytes"]):
        raise SemanticControlError("public label config byte count changed")
    config = json.loads(config_bytes)
    if (
        config.get("explainer_type_name") != EXPECTED_EXPLANATION_TYPE
        or config.get("explainer_model_name") != EXPECTED_EXPLANATION_MODEL
    ):
        raise SemanticControlError("public label config provenance differs")

    source_records: list[dict[str, Any]] = []
    labels: list[dict[str, Any]] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
        futures = [executor.submit(_parse_batch, source) for source in batches]
        for future in concurrent.futures.as_completed(futures):
            source, rows = future.result()
            source_records.append(source)
            labels.extend(rows)
    labels.sort(key=lambda row: int(row["feature_id"]))
    if len(labels) != len({int(row["feature_id"]) for row in labels}):
        raise SemanticControlError("public label snapshot contains duplicate IDs")
    if any(
        row["explanation_type"] != EXPECTED_EXPLANATION_TYPE
        or row["explanation_model"] != EXPECTED_EXPLANATION_MODEL
        for row in labels
    ):
        raise SemanticControlError("row-level public label provenance differs")

    state = torch.load(sae_path, map_location="cpu", weights_only=True, mmap=True)
    eligibility = _tensor_eligibility_for_matches(labels, state)
    selection = select_semantic_controls(
        labels,
        matched_feature_ids=matched_ids,
        tensor_eligibility=eligibility,
    )
    missing = sorted(set(range(SAE_WIDTH)) - {int(row["feature_id"]) for row in labels})
    source_records.sort(key=lambda row: str(row["key"]))

    transaction = RunTransaction.start(
        phase="calibration",
        run_id=run_id,
        artifact_root=root,
        expected_volume_id=volume_id,
        metadata={
            "study_id": STUDY_ID,
            "protocol_version": PROTOCOL_VERSION,
            "outcome_blind": True,
            "target_outcomes_opened": False,
            "prior_outcome_inputs": [],
            "role": "fresh_public_semantic_control_label_snapshot",
            "calibration_manifest_sha256": sealed_calibration["manifest_sha256"],
        },
    )
    transaction.write_json("labels.json", labels)
    transaction.write_json("source_objects.json", source_records)
    transaction.write_json("source_config.json", config)
    transaction.write_json("missing_feature_ids.json", missing)
    receipt: dict[str, Any] = {
        "schema_version": SEMANTIC_CONTROL_SCHEMA_VERSION,
        "status": "pass",
        "study_id": STUDY_ID,
        "protocol_version": PROTOCOL_VERSION,
        "created_at_utc": utc_now(),
        "outcome_blind": True,
        "target_outcomes_opened": False,
        "prior_outcome_inputs": [],
        "expected_volume_id": volume_id,
        "calibration_receipt_file_sha256": sha256_file(calibration_path),
        "calibration_receipt_embedded_sha256": calibration["receipt_sha256"],
        "calibration_manifest_sha256": sealed_calibration["manifest_sha256"],
        "sae_file_sha256": SAE_FILE_SHA256,
        "source": {
            "documentation_url": "https://docs.neuronpedia.org/api",
            "bucket": NEURONPEDIA_BUCKET,
            "prefix": NEURONPEDIA_PREFIX,
            "model_id": NEURONPEDIA_MODEL_ID,
            "source_id": NEURONPEDIA_SOURCE_ID,
            "config_object": {
                **configs[0],
                "sha256": sha256_bytes(config_bytes),
            },
            "source_objects_sha256": sha256_json(source_records),
        },
        "coverage": {
            "dictionary_size": SAE_WIDTH,
            "labels": len(labels),
            "missing": len(missing),
            "batch_objects": len(source_records),
            "compressed_source_bytes": sum(int(row["bytes"]) for row in source_records),
        },
        "selection": selection,
        "claim_boundary": (
            "Mutable third-party autointerpretability labels are a mechanical "
            "selection source, not ground-truth SAE semantics or Goodfire labels."
        ),
        "source_file_sha256": sha256_file(Path(__file__)),
    }
    receipt["receipt_sha256"] = sha256_json(receipt)
    transaction.write_json("semantic_control_selection_receipt.json", receipt)
    final_path = transaction.complete(
        metadata={
            "study_id": STUDY_ID,
            "receipt_sha256": receipt["receipt_sha256"],
            "selected_feature_ids": selection["selected_feature_ids"],
        }
    )
    verify_completed_run(final_path)
    return final_path


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache-dir", type=Path, required=True)
    parser.add_argument("--calibration-receipt", type=Path, required=True)
    parser.add_argument("--artifact-root", type=Path)
    parser.add_argument("--volume-id", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args(argv)
    if not 1 <= args.workers <= 16:
        parser.error("--workers must be between 1 and 16")
    return args


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    final = snapshot_and_select(
        cache_dir=args.cache_dir.expanduser().resolve(strict=True),
        calibration_receipt_path=args.calibration_receipt,
        artifact_root=args.artifact_root,
        volume_id=args.volume_id,
        run_id=args.run_id,
        workers=args.workers,
    )
    print(json.dumps({"status": "pass", "completed_directory": str(final)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

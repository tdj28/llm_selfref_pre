#!/usr/bin/env python3
"""Build the frozen Gemma Scope direct-IT, transfer, and gated layer atlas."""

from __future__ import annotations

import argparse
import csv
import gzip
import json
import math
import random
import shutil
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from experiments.exp2_sae.gemma_scope_9b_protocol import (  # noqa: E402
    ANCHOR_LAYERS,
    CANDIDATES_PER_CONSTRUCT,
    CONFIRMATION_SOURCE,
    CONSTRUCTS,
    DISCOVERY_SOURCE,
    FEATURES_PER_SET,
    IT_SAE_REPO,
    IT_SAE_REVISION,
    MODEL_ID,
    MODEL_REVISION,
    PRIMARY_LAYER,
    PRIMARY_WIDTH,
    PROTOCOL_VERSION,
    PT_ATT_SAE_REPO,
    PT_ATT_SAE_REVISION,
    PT_MLP_SAE_REPO,
    PT_MLP_SAE_REVISION,
    SELECTION_SOURCE,
    TRANSFER_THRESHOLDS,
    pt_folder,
    sha256_file,
)
from experiments.exp2_sae.gemma_scope_9b_runtime import (  # noqa: E402
    PinnedJumpReLUSAE,
    load_model_and_tokenizer,
    model_layers,
    release_memory,
    runtime_metadata,
    utc_now,
    write_json,
)
from src.prompts import (  # noqa: E402
    BINARY_CONSCIOUS_QUERY,
    CAUSAL_FACTORIAL_INDUCTIONS,
    INDUCTIONS,
)


CONTROL_POOL_SEED = 2026071104
CONTROL_POOL_SIZE = 4096
RECONSTRUCTION_ITEMS = 64
DEFAULT_BATCH_SIZE = 4
GROUP_SIZE = 6


def spec_key(spec: dict[str, Any]) -> str:
    kind = "it" if spec["model_kind"] == "instruction_tuned" else "pt"
    site = {
        "residual_post": "res",
        "attention_out": "att",
        "mlp_out": "mlp",
    }[spec["site"]]
    return f"{kind}_{site}_l{int(spec['layer'])}_w{int(spec['width'])}"


def register_sublayer_capture(
    *,
    layer_module: Any,
    site: str,
    capture_key: str,
    captures: dict[str, Any],
) -> Any:
    """Capture the normalized branch contribution added to Gemma's residual."""

    if site == "attention_out":
        module = layer_module.post_attention_layernorm
    elif site == "mlp_out":
        module = layer_module.post_feedforward_layernorm
    else:
        raise ValueError(f"Unsupported Gemma sublayer capture site: {site}")

    def hook(_module: Any, _inputs: Any, output: Any) -> None:
        captures[capture_key] = output

    return module.register_forward_hook(hook)


def load_rows(atlas_plan: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for corpus in atlas_plan["corpora"]:
        path = REPO_ROOT / corpus["path"]
        if sha256_file(path) != corpus["sha256"]:
            raise RuntimeError(f"Frozen corpus hash differs: {path}")
        with path.open(encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle):
                rows.append(
                    {
                        "atlas_index": len(rows),
                        "corpus_role": corpus["role"],
                        "item_id": row["item_id"],
                        "source": row["source"],
                        "category": row["category"],
                        "text_sha256": row["text_sha256"],
                        "text": row["text"],
                    }
                )
    if len({(row["corpus_role"], row["item_id"]) for row in rows}) != len(rows):
        raise RuntimeError("Atlas corpus has duplicate corpus-role/item IDs")
    return rows


def chunked(values: list[Any], size: int) -> Iterable[list[Any]]:
    for start in range(0, len(values), size):
        yield values[start : start + size]


def category_equal_contrast(
    profile: dict[tuple[str, str], Any],
    source: str,
    positive: Iterable[str],
    negative: Iterable[str],
) -> Any:
    import numpy as np

    positive_values = [profile[(source, category)] for category in positive]
    negative_values = [profile[(source, category)] for category in negative]
    return np.mean(positive_values, axis=0) - np.mean(negative_values, axis=0)


def rank_ids(values: Any, allowed: Any, count: int) -> list[int]:
    import numpy as np

    ids = np.flatnonzero(allowed & np.isfinite(values))
    order = sorted(ids.tolist(), key=lambda feature_id: (-float(values[feature_id]), feature_id))
    if len(order) < count:
        raise RuntimeError(f"Only {len(order)} eligible features for fixed count {count}")
    return order[:count]


def mean_and_positive(matrix: Any, indices: list[int], chunk_size: int = 128) -> tuple[Any, Any]:
    import numpy as np

    width = int(matrix.shape[1])
    sums = np.zeros(width, dtype=np.float64)
    positive = np.zeros(width, dtype=np.int64)
    for batch_indices in chunked(indices, chunk_size):
        values = np.asarray(matrix[batch_indices], dtype=np.float32)
        sums += values.sum(axis=0, dtype=np.float64)
        positive += (values > 0).sum(axis=0)
    return (sums / len(indices)).astype(np.float32), positive / len(indices)


def feature_quantile(values: Any, quantile: float = 0.90) -> float:
    import numpy as np

    positive = np.asarray(values, dtype=np.float32)
    positive = positive[positive > 0]
    return float(np.quantile(positive, quantile)) if positive.size else 0.0


def match_controls(
    *,
    matrix: Any,
    rows: list[dict[str, Any]],
    decoder_norms: Any,
    discovery_mean: Any,
    discovery_positive: Any,
    selection_positive: Any,
    discovery_contrast: Any,
    semantic_ids: set[int],
    target_ids: list[int],
) -> dict[str, Any]:
    import numpy as np
    from scipy.optimize import linear_sum_assignment

    selection_indices = [
        index for index, row in enumerate(rows) if row["source"] == SELECTION_SOURCE
    ]
    rng = random.Random(CONTROL_POOL_SEED)
    eligible = [
        feature_id
        for feature_id in range(matrix.shape[1])
        if feature_id not in semantic_ids
        and math.isfinite(float(decoder_norms[feature_id]))
        and float(discovery_positive[feature_id]) > 0
        and float(selection_positive[feature_id]) > 0
    ]
    if len(eligible) < CONTROL_POOL_SIZE:
        raise RuntimeError("Insufficient eligible control features")
    candidate_pool = sorted(rng.sample(eligible, CONTROL_POOL_SIZE))

    def metrics(feature_ids: list[int]) -> Any:
        q90 = np.array(
            [
                feature_quantile(matrix[selection_indices, feature_id])
                for feature_id in feature_ids
            ],
            dtype=np.float64,
        )
        return np.column_stack(
            [
                np.log1p(np.asarray(decoder_norms[feature_ids], dtype=np.float64)),
                np.log1p(np.asarray(discovery_mean[feature_ids], dtype=np.float64)),
                np.asarray(discovery_positive[feature_ids], dtype=np.float64),
                np.log1p(q90),
            ]
        )

    all_metrics = metrics(target_ids + candidate_pool)
    center = np.median(all_metrics, axis=0)
    scale = np.median(np.abs(all_metrics - center), axis=0)
    scale[scale < 1e-8] = 1.0
    target_metrics = (metrics(target_ids) - center) / scale
    used: set[int] = set()
    panels = []
    for panel_index in range(3):
        candidates = [feature_id for feature_id in candidate_pool if feature_id not in used]
        candidate_metrics = (metrics(candidates) - center) / scale
        costs = ((target_metrics[:, None, :] - candidate_metrics[None, :, :]) ** 2).sum(axis=2)
        candidate_contrast = np.abs(np.asarray(discovery_contrast[candidates], dtype=np.float64))
        target_contrast = np.abs(np.asarray(discovery_contrast[target_ids], dtype=np.float64))
        contrast_ratio = candidate_contrast[None, :] / np.maximum(target_contrast[:, None], 1e-8)
        costs += np.minimum(contrast_ratio, 5.0)
        invalid = contrast_ratio >= 1.0
        costs[invalid] = 1e12
        costs += np.arange(len(candidates), dtype=np.float64)[None, :] * 1e-12
        row_ind, col_ind = linear_sum_assignment(costs)
        if row_ind.tolist() != list(range(len(target_ids))):
            raise RuntimeError("Control assignment did not cover every target")
        selected = [int(candidates[column]) for column in col_ind]
        if any(invalid[row, col_ind[row]] for row in range(len(target_ids))):
            raise RuntimeError(
                "No valid matched-control assignment with contrasts closer to zero"
            )
        used.update(selected)
        panels.append(
            {
                "panel_index": panel_index + 1,
                "feature_ids": selected,
                "pairs": [
                    {
                        "target_feature_id": int(target_ids[row]),
                        "control_feature_id": int(selected[row]),
                        "cost": float(costs[row, col_ind[row]]),
                        "target_discovery_contrast": float(discovery_contrast[target_ids[row]]),
                        "control_discovery_contrast": float(discovery_contrast[selected[row]]),
                    }
                    for row in range(len(target_ids))
                ],
            }
        )
    candidate_q90 = {
        feature_id: feature_quantile(matrix[selection_indices, feature_id])
        for feature_id in candidate_pool
    }
    return {
        "method": "seeded_4096_pool_sequential_minimum_cost_assignment",
        "candidate_pool_seed": CONTROL_POOL_SEED,
        "candidate_pool_size": CONTROL_POOL_SIZE,
        "candidate_pool_sha256": __import__("hashlib").sha256(
            json.dumps(candidate_pool, separators=(",", ":")).encode("utf-8")
        ).hexdigest(),
        "candidate_pool_feature_ids": candidate_pool,
        "tie_break": "feature ID order via 1e-12 assignment-cost offset",
        "standardization_center": center.tolist(),
        "standardization_scale": scale.tolist(),
        "metrics": [
            "log1p_decoder_norm",
            "log1p_discovery_mean_activation",
            "positive_item_fraction",
            "log1p_active_q90",
        ],
        "candidate_pool_metrics": [
            {
                "feature_id": feature_id,
                "decoder_norm": float(decoder_norms[feature_id]),
                "discovery_mean_activation": float(discovery_mean[feature_id]),
                "discovery_positive_item_fraction": float(
                    discovery_positive[feature_id]
                ),
                "active_q90": candidate_q90[feature_id],
                "absolute_discovery_contrast": abs(
                    float(discovery_contrast[feature_id])
                ),
            }
            for feature_id in candidate_pool
        ],
        "panels": panels,
    }


def analyze_matrix(
    *,
    spec: dict[str, Any],
    sae: PinnedJumpReLUSAE,
    matrix_path: Path,
    rows: list[dict[str, Any]],
    output_dir: Path,
    reconstruction: dict[str, Any],
) -> dict[str, Any]:
    import numpy as np

    key = spec_key(spec)
    matrix = np.load(matrix_path, mmap_mode="r")
    if matrix.shape != (len(rows), int(spec["width"])):
        raise RuntimeError(f"Activation matrix shape differs for {key}: {matrix.shape}")
    profile: dict[tuple[str, str], Any] = {}
    profile_positive: dict[tuple[str, str], Any] = {}
    profile_counts: dict[tuple[str, str], int] = {}
    profile_keys = sorted({(row["source"], row["category"]) for row in rows})
    for source, category in profile_keys:
        indices = [
            index
            for index, row in enumerate(rows)
            if row["source"] == source and row["category"] == category
        ]
        values = np.asarray(matrix[indices], dtype=np.float32)
        profile[(source, category)] = values.mean(axis=0, dtype=np.float64).astype(np.float32)
        profile_positive[(source, category)] = (values > 0).mean(axis=0).astype(
            np.float32
        )
        profile_counts[(source, category)] = len(indices)

    discovery_indices = [
        index for index, row in enumerate(rows) if row["source"] == DISCOVERY_SOURCE
    ]
    discovery_mean, discovery_positive = mean_and_positive(matrix, discovery_indices)
    decoder_norms = sae.decoder_norms().cpu().numpy().astype(np.float32)
    selected_by_construct: dict[str, list[int]] = {}
    candidate_rows: list[dict[str, Any]] = []
    construct_summaries: dict[str, Any] = {}
    q90_by_feature: dict[str, float] = {}
    selection_indices = [
        index for index, row in enumerate(rows) if row["source"] == SELECTION_SOURCE
    ]
    _, selection_positive = mean_and_positive(matrix, selection_indices)
    confirmation_indices = [
        index for index, row in enumerate(rows) if row["source"] == CONFIRMATION_SOURCE
    ]

    for construct, definition in CONSTRUCTS.items():
        discovery_contrast = category_equal_contrast(
            profile,
            DISCOVERY_SOURCE,
            definition["positive_categories"],
            definition["negative_categories"],
        )
        candidates = rank_ids(
            discovery_contrast,
            (discovery_positive > 0) & (discovery_contrast > 0),
            CANDIDATES_PER_CONSTRUCT,
        )
        selection_contrast_all = category_equal_contrast(
            profile,
            SELECTION_SOURCE,
            definition["positive_categories"],
            definition["negative_categories"],
        )
        candidates_sorted = sorted(
            [feature_id for feature_id in candidates if selection_positive[feature_id] > 0],
            key=lambda feature_id: (-float(selection_contrast_all[feature_id]), feature_id),
        )
        if len(candidates_sorted) < FEATURES_PER_SET:
            raise RuntimeError(
                f"Only {len(candidates_sorted)} {construct} candidates activate on selection texts"
            )
        selected = candidates_sorted[:FEATURES_PER_SET]
        selected_by_construct[construct] = selected
        confirmation_contrast_all = category_equal_contrast(
            profile,
            CONFIRMATION_SOURCE,
            definition["positive_categories"],
            definition["negative_categories"],
        )
        for feature_id in selected:
            q90_by_feature[str(feature_id)] = feature_quantile(
                matrix[selection_indices, feature_id]
            )
        selection_rank = {
            feature_id: rank for rank, feature_id in enumerate(candidates_sorted, 1)
        }
        for discovery_rank, feature_id in enumerate(candidates, 1):
            candidate_rows.append(
                {
                    "sae_key": key,
                    "construct": construct,
                    "feature_id": feature_id,
                    "discovery_rank": discovery_rank,
                    "selection_eligible": int(feature_id in selection_rank),
                    "selection_rank": selection_rank.get(feature_id),
                    "selected": int(feature_id in selected),
                    "discovery_contrast": float(discovery_contrast[feature_id]),
                    "selection_contrast": float(selection_contrast_all[feature_id]),
                    "confirmation_contrast": float(confirmation_contrast_all[feature_id]),
                    "decoder_norm": float(decoder_norms[feature_id]),
                    "discovery_mean_activation": float(discovery_mean[feature_id]),
                    "discovery_positive_item_fraction": float(
                        discovery_positive[feature_id]
                    ),
                    "selection_positive_item_fraction": float(
                        selection_positive[feature_id]
                    ),
                    "active_q90": q90_by_feature.get(str(feature_id)),
                }
            )

        q90 = np.array(
            [max(q90_by_feature[str(feature_id)], 1e-8) for feature_id in selected],
            dtype=np.float32,
        )
        aggregate_profiles: dict[str, float] = {}
        for source, category in profile_keys:
            category_values = profile[(source, category)][selected] / q90
            aggregate_profiles[f"{source}|{category}"] = float(category_values.mean())

        def aggregate_contrast(source: str) -> float:
            positive = [
                aggregate_profiles[f"{source}|{category}"]
                for category in definition["positive_categories"]
            ]
            negative = [
                aggregate_profiles[f"{source}|{category}"]
                for category in definition["negative_categories"]
            ]
            return float(np.mean(positive) - np.mean(negative))

        construct_summaries[construct] = {
            "candidate_ids": candidates,
            "selected_feature_ids": selected,
            "selected_active_q90": [float(value) for value in q90],
            "mean_individual_discovery_contrast": float(
                np.mean(discovery_contrast[selected])
            ),
            "mean_individual_selection_contrast": float(
                np.mean(selection_contrast_all[selected])
            ),
            "mean_individual_confirmation_contrast": float(
                np.mean(confirmation_contrast_all[selected])
            ),
            "aggregate_discovery_contrast": aggregate_contrast(DISCOVERY_SOURCE),
            "aggregate_selection_contrast": aggregate_contrast(SELECTION_SOURCE),
            "aggregate_confirmation_contrast": aggregate_contrast(CONFIRMATION_SOURCE),
            "aggregate_category_profile": aggregate_profiles,
        }

    output_dir.mkdir(parents=True, exist_ok=True)
    with (output_dir / "candidate_features.csv").open(
        "w", encoding="utf-8", newline=""
    ) as handle:
        fieldnames = list(candidate_rows[0])
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(candidate_rows)

    selected_ids = sorted({value for values in selected_by_construct.values() for value in values})
    with gzip.open(output_dir / "selected_item_activations.csv.gz", "wt", encoding="utf-8", newline="") as handle:
        fieldnames = [
            "atlas_index",
            "item_id",
            "source",
            "category",
            "construct",
            "feature_id",
            "activation",
        ]
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        construct_by_feature: dict[int, list[str]] = defaultdict(list)
        for construct, feature_ids in selected_by_construct.items():
            for feature_id in feature_ids:
                construct_by_feature[feature_id].append(construct)
        relevant_indices = range(len(rows))
        for atlas_index in relevant_indices:
            item = rows[atlas_index]
            values = np.asarray(matrix[atlas_index, selected_ids], dtype=np.float32)
            for offset, feature_id in enumerate(selected_ids):
                for construct in construct_by_feature[feature_id]:
                    writer.writerow(
                        {
                            "atlas_index": atlas_index,
                            "item_id": item["item_id"],
                            "source": item["source"],
                            "category": item["category"],
                            "construct": construct,
                            "feature_id": feature_id,
                            "activation": float(values[offset]),
                        }
                    )

    profile_array = np.stack([profile[key_value] for key_value in profile_keys], axis=0)
    profile_positive_array = np.stack(
        [profile_positive[key_value] for key_value in profile_keys], axis=0
    )
    np.savez_compressed(
        output_dir / "all_feature_statistics.npz",
        profile_sources=np.array([value[0] for value in profile_keys]),
        profile_categories=np.array([value[1] for value in profile_keys]),
        profile_means=profile_array,
        profile_positive_item_fractions=profile_positive_array,
        profile_item_counts=np.array(
            [profile_counts[key_value] for key_value in profile_keys], dtype=np.int64
        ),
        discovery_mean=discovery_mean,
        discovery_positive_item_fraction=discovery_positive.astype(np.float32),
        decoder_norms=decoder_norms,
    )
    direction_ids = np.array(selected_ids, dtype=np.int64)
    directions = sae.W_dec[direction_ids].float().cpu().numpy()
    np.savez_compressed(
        output_dir / "selected_decoder_directions.npz",
        feature_ids=direction_ids,
        directions=directions,
    )

    primary_controls = None
    if int(spec["layer"]) == PRIMARY_LAYER and int(spec["width"]) == PRIMARY_WIDTH and spec["model_kind"] == "instruction_tuned":
        target_ids = selected_by_construct["deception_roleplay"]
        semantic_ids = {value for values in selected_by_construct.values() for value in values}
        deception_definition = CONSTRUCTS["deception_roleplay"]
        discovery_contrast = category_equal_contrast(
            profile,
            DISCOVERY_SOURCE,
            deception_definition["positive_categories"],
            deception_definition["negative_categories"],
        )
        primary_controls = match_controls(
            matrix=matrix,
            rows=rows,
            decoder_norms=decoder_norms,
            discovery_mean=discovery_mean,
            discovery_positive=discovery_positive,
            selection_positive=selection_positive,
            discovery_contrast=discovery_contrast,
            semantic_ids=semantic_ids,
            target_ids=target_ids,
        )
        control_q90 = {}
        for panel in primary_controls["panels"]:
            for feature_id in panel["feature_ids"]:
                control_q90[str(feature_id)] = feature_quantile(
                    matrix[selection_indices, feature_id]
                )
        primary_controls["active_q90"] = control_q90
        write_json(output_dir / "matched_controls.json", primary_controls)

    summary = {
        "status": "complete",
        "completed_at_utc": utc_now(),
        "sae_key": key,
        "spec": spec,
        "sae": sae.record(),
        "n_items": len(rows),
        "n_discovery_items": len(discovery_indices),
        "n_selection_items": len(selection_indices),
        "n_confirmation_items": len(confirmation_indices),
        "profile_item_counts": {
            f"{source}|{category}": profile_counts[(source, category)]
            for source, category in profile_keys
        },
        "constructs": construct_summaries,
        "active_q90_by_feature": q90_by_feature,
        "reconstruction": reconstruction,
        "matched_controls": primary_controls,
        "activation_matrix_sha256": sha256_file(matrix_path),
        "activation_matrix_released": False,
        "selection_used_behavioral_outcomes": False,
    }
    write_json(output_dir / "summary.json", summary)
    return summary


def map_group(
    *,
    torch_module: Any,
    model: Any,
    tokenizer: Any,
    rows: list[dict[str, Any]],
    specs: list[dict[str, Any]],
    outdir: Path,
    scratch_dir: Path,
    batch_size: int,
) -> dict[str, dict[str, Any]]:
    import numpy as np

    pending = [
        spec
        for spec in specs
        if not (outdir / "saes" / spec_key(spec) / "summary.json").is_file()
    ]
    for spec in specs:
        if spec not in pending:
            stale_matrix = scratch_dir / f"{spec_key(spec)}.npy"
            if stale_matrix.exists():
                stale_matrix.unlink()
    if not pending:
        return {
            spec_key(spec): json.loads(
                (outdir / "saes" / spec_key(spec) / "summary.json").read_text(
                    encoding="utf-8"
                )
            )
            for spec in specs
        }
    saes: dict[str, PinnedJumpReLUSAE] = {}
    matrices: dict[str, Any] = {}
    matrix_paths: dict[str, Path] = {}
    reconstruction: dict[str, dict[str, Any]] = {}
    captures: dict[str, Any] = {}
    handles = []
    try:
        for spec in pending:
            key = spec_key(spec)
            print(f"Loading {key}: {spec['repo']} / {spec['folder']}", flush=True)
            sae = PinnedJumpReLUSAE.load(
                repo_id=spec["repo"],
                revision=spec["revision"],
                folder=spec["folder"],
                dtype_name="bfloat16",
            )
            if sae.d_sae != int(spec["width"]):
                raise RuntimeError(f"SAE width mismatch for {key}")
            saes[key] = sae
            matrix_path = scratch_dir / f"{key}.npy"
            matrix_paths[key] = matrix_path
            matrices[key] = np.lib.format.open_memmap(
                matrix_path,
                mode="w+",
                dtype=np.float16,
                shape=(len(rows), sae.d_sae),
            )
            reconstruction[key] = {
                "error_ss": 0.0,
                "hidden_sum": np.zeros(sae.d_in, dtype=np.float64),
                "hidden_sumsq": np.zeros(sae.d_in, dtype=np.float64),
                "n_tokens": 0,
            }

        layers = model_layers(model)
        for spec in pending:
            key = spec_key(spec)
            site = spec["site"]
            layer = int(spec["layer"])
            if site in {"attention_out", "mlp_out"}:
                handles.append(
                    register_sublayer_capture(
                        layer_module=layers[layer],
                        site=site,
                        capture_key=key,
                        captures=captures,
                    )
                )

        tokenizer.padding_side = "right"
        special_ids = torch_module.tensor(
            sorted(set(tokenizer.all_special_ids)),
            dtype=torch_module.long,
            device=model.device,
        )
        started = time.monotonic()
        for batch_start in range(0, len(rows), batch_size):
            batch_rows = rows[batch_start : batch_start + batch_size]
            encoded = tokenizer(
                [row["text"] for row in batch_rows],
                add_special_tokens=True,
                padding=True,
                truncation=True,
                max_length=128,
                return_tensors="pt",
            )
            encoded = {key: value.to(model.device) for key, value in encoded.items()}
            captures.clear()
            with torch_module.no_grad():
                outputs = model(
                    **encoded,
                    output_hidden_states=True,
                    use_cache=False,
                    return_dict=True,
                )
            valid = encoded["attention_mask"].bool()
            if special_ids.numel():
                special = (encoded["input_ids"].unsqueeze(-1) == special_ids).any(dim=-1)
                valid &= ~special
            if not bool(valid.any(dim=1).all()):
                raise RuntimeError("Atlas batch contains an item with no valid text tokens")
            for spec in pending:
                key = spec_key(spec)
                site = spec["site"]
                if site == "residual_post":
                    hidden = outputs.hidden_states[int(spec["layer"]) + 1]
                else:
                    hidden = captures.get(key)
                    if hidden is None:
                        raise RuntimeError(f"Sublayer hook did not capture {key}")
                sae = saes[key]
                if int(hidden.shape[-1]) != sae.d_in:
                    raise RuntimeError(
                        f"Hook width {hidden.shape[-1]} differs from SAE {sae.d_in} for {key}"
                    )
                with torch_module.no_grad():
                    acts = sae.encode(hidden)
                    masked = acts.masked_fill(~valid.unsqueeze(-1), 0)
                    maxima = masked.amax(dim=1)
                maxima_float = maxima.float()
                if not bool(torch_module.isfinite(maxima_float).all()):
                    raise RuntimeError(f"Non-finite atlas activation for {key}")
                if float(maxima_float.max().item()) > float(
                    np.finfo(np.float16).max
                ):
                    raise RuntimeError(f"Atlas activation exceeds float16 range for {key}")
                matrices[key][batch_start : batch_start + len(batch_rows)] = (
                    maxima_float.cpu().numpy().astype(np.float16)
                )
                if batch_start < RECONSTRUCTION_ITEMS:
                    remaining = RECONSTRUCTION_ITEMS - batch_start
                    take = min(len(batch_rows), remaining)
                    local_valid = valid[:take]
                    flat_hidden = hidden[:take][local_valid]
                    flat_acts = acts[:take][local_valid]
                    with torch_module.no_grad():
                        recon = sae.decode(flat_acts)
                    record = reconstruction[key]
                    hidden_cpu = flat_hidden.float().cpu().numpy().astype(np.float64)
                    error_cpu = (recon - flat_hidden).float().cpu().numpy().astype(np.float64)
                    record["error_ss"] += float((error_cpu**2).sum())
                    record["hidden_sum"] += hidden_cpu.sum(axis=0)
                    record["hidden_sumsq"] += (hidden_cpu**2).sum(axis=0)
                    record["n_tokens"] += int(hidden_cpu.shape[0])
                del hidden, acts, masked, maxima, maxima_float
            del outputs, encoded, valid
            if (batch_start // batch_size + 1) % 50 == 0 or batch_start + batch_size >= len(rows):
                elapsed = (time.monotonic() - started) / 3600
                print(
                    f"Atlas group {[spec_key(value) for value in pending]}: "
                    f"{min(batch_start + batch_size, len(rows))}/{len(rows)} items; "
                    f"elapsed={elapsed:.2f}h",
                    flush=True,
                )
        for matrix in matrices.values():
            matrix.flush()

        summaries = {}
        for spec in pending:
            key = spec_key(spec)
            record = reconstruction[key]
            n_tokens = int(record["n_tokens"])
            denominator = float(
                (
                    record["hidden_sumsq"]
                    - record["hidden_sum"] ** 2 / max(n_tokens, 1)
                ).sum()
            )
            recon_summary = {
                "n_tokens": n_tokens,
                "error_sum_squares": float(record["error_ss"]),
                "centered_hidden_sum_squares": denominator,
                "fvu": float(record["error_ss"] / denominator) if denominator > 0 else None,
            }
            summaries[key] = analyze_matrix(
                spec=spec,
                sae=saes[key],
                matrix_path=matrix_paths[key],
                rows=rows,
                output_dir=outdir / "saes" / key,
                reconstruction=recon_summary,
            )
            matrix_paths[key].unlink()
        for spec in specs:
            key = spec_key(spec)
            if key not in summaries:
                summaries[key] = json.loads(
                    (outdir / "saes" / key / "summary.json").read_text(encoding="utf-8")
                )
        return summaries
    finally:
        for handle in reversed(handles):
            handle.remove()
        for matrix in matrices.values():
            try:
                matrix.flush()
            except Exception:
                pass
        release_memory(*saes.values())


def rankdata(values: list[float]) -> list[float]:
    order = sorted(range(len(values)), key=lambda index: (values[index], index))
    ranks = [0.0] * len(values)
    start = 0
    while start < len(order):
        end = start + 1
        while end < len(order) and values[order[end]] == values[order[start]]:
            end += 1
        rank = (start + end - 1) / 2 + 1
        for position in range(start, end):
            ranks[order[position]] = rank
        start = end
    return ranks


def pearson(left: list[float], right: list[float]) -> float:
    left_mean = sum(left) / len(left)
    right_mean = sum(right) / len(right)
    numerator = sum((x - left_mean) * (y - right_mean) for x, y in zip(left, right))
    left_ss = sum((x - left_mean) ** 2 for x in left)
    right_ss = sum((y - right_mean) ** 2 for y in right)
    return numerator / math.sqrt(left_ss * right_ss) if left_ss > 0 and right_ss > 0 else 0.0


def spearman(left: list[float], right: list[float]) -> float:
    return pearson(rankdata(left), rankdata(right))


def measure_chat_transfer_reconstruction(
    *,
    torch_module: Any,
    model: Any,
    tokenizer: Any,
    direct_specs: list[dict[str, Any]],
    pt_specs: list[dict[str, Any]],
) -> dict[str, Any]:
    import numpy as np

    specs = [
        spec
        for spec in direct_specs + pt_specs
        if int(spec["width"]) == 16_384 and int(spec["layer"]) in ANCHOR_LAYERS
    ]
    saes = {
        spec_key(spec): PinnedJumpReLUSAE.load(
            repo_id=spec["repo"],
            revision=spec["revision"],
            folder=spec["folder"],
            dtype_name="bfloat16",
        )
        for spec in specs
    }
    prompts = [
        INDUCTIONS["self_ref_paper"],
        INDUCTIONS["history_paper"],
        BINARY_CONSCIOUS_QUERY,
        *[
            item["text"]
            for item in sorted(
                CAUSAL_FACTORIAL_INDUCTIONS.values(),
                key=lambda value: value["prompt_id"],
            )[:8]
        ],
    ]
    accumulators = {
        key: {
            "error_ss": 0.0,
            "hidden_sum": np.zeros(sae.d_in, dtype=np.float64),
            "hidden_sumsq": np.zeros(sae.d_in, dtype=np.float64),
            "n_tokens": 0,
        }
        for key, sae in saes.items()
    }
    try:
        for prompt in prompts:
            encoded = tokenizer.apply_chat_template(
                [{"role": "user", "content": prompt}],
                add_generation_prompt=True,
                tokenize=True,
                return_dict=True,
                return_tensors="pt",
            )
            encoded = {key: value.to(model.device) for key, value in encoded.items()}
            if "attention_mask" not in encoded:
                encoded["attention_mask"] = torch_module.ones_like(
                    encoded["input_ids"]
                )
            with torch_module.no_grad():
                outputs = model(
                    **encoded,
                    output_hidden_states=True,
                    use_cache=False,
                    return_dict=True,
                )
            valid = encoded["attention_mask"].bool().reshape(-1)
            for spec in specs:
                key = spec_key(spec)
                sae = saes[key]
                hidden = outputs.hidden_states[int(spec["layer"]) + 1].reshape(
                    -1, sae.d_in
                )[valid]
                with torch_module.no_grad():
                    recon = sae.reconstruct(hidden)
                hidden_np = hidden.float().cpu().numpy().astype(np.float64)
                error_np = (recon - hidden).float().cpu().numpy().astype(np.float64)
                record = accumulators[key]
                record["error_ss"] += float((error_np**2).sum())
                record["hidden_sum"] += hidden_np.sum(axis=0)
                record["hidden_sumsq"] += (hidden_np**2).sum(axis=0)
                record["n_tokens"] += int(hidden_np.shape[0])
            del outputs, encoded
        result = {}
        for key, record in accumulators.items():
            n_tokens = int(record["n_tokens"])
            denominator = float(
                (
                    record["hidden_sumsq"]
                    - record["hidden_sum"] ** 2 / max(n_tokens, 1)
                ).sum()
            )
            result[key] = {
                "n_prompts": len(prompts),
                "n_tokens": n_tokens,
                "error_sum_squares": float(record["error_ss"]),
                "centered_hidden_sum_squares": denominator,
                "fvu": float(record["error_ss"] / denominator),
            }
        return result
    finally:
        release_memory(*saes.values())


def transfer_gate(
    summaries: dict[str, dict[str, Any]], chat_reconstruction: dict[str, Any]
) -> dict[str, Any]:
    import statistics

    rows = []
    profile_correlations = []
    positive_deception = []
    for layer in ANCHOR_LAYERS:
        it = summaries[f"it_res_l{layer}_w16384"]
        pt = summaries[f"pt_res_l{layer}_w16384"]
        correlations = {}
        for construct in CONSTRUCTS:
            it_profile = it["constructs"][construct]["aggregate_category_profile"]
            pt_profile = pt["constructs"][construct]["aggregate_category_profile"]
            keys = sorted(
                key
                for key in it_profile
                if key.startswith(f"{CONFIRMATION_SOURCE}|") and key in pt_profile
            )
            value = spearman(
                [float(it_profile[key]) for key in keys],
                [float(pt_profile[key]) for key in keys],
            )
            correlations[construct] = value
            profile_correlations.append(value)
        deception_contrast = float(
            pt["constructs"]["deception_roleplay"]["aggregate_confirmation_contrast"]
        )
        positive_deception.append(deception_contrast > 0)
        rows.append(
            {
                "layer": layer,
                "it_fvu": float(chat_reconstruction[f"it_res_l{layer}_w16384"]["fvu"]),
                "pt_fvu": float(chat_reconstruction[f"pt_res_l{layer}_w16384"]["fvu"]),
                "pt_minus_it_fvu": float(
                    chat_reconstruction[f"pt_res_l{layer}_w16384"]["fvu"]
                )
                - float(chat_reconstruction[f"it_res_l{layer}_w16384"]["fvu"]),
                "category_profile_spearman": correlations,
                "pt_deception_confirmation_contrast": deception_contrast,
            }
        )
    median_pt_fvu = statistics.median(row["pt_fvu"] for row in rows)
    median_difference = statistics.median(row["pt_minus_it_fvu"] for row in rows)
    median_correlation = statistics.median(profile_correlations)
    checks = {
        "median_pt_fvu": median_pt_fvu <= TRANSFER_THRESHOLDS["median_pt_fvu_max"],
        "median_pt_minus_it_fvu": median_difference
        <= TRANSFER_THRESHOLDS["median_pt_minus_it_fvu_max"],
        "median_category_profile_spearman": median_correlation
        >= TRANSFER_THRESHOLDS["median_category_profile_spearman_min"],
        "positive_deception_at_all_anchors": all(positive_deception),
    }
    return {
        "status": "pass" if all(checks.values()) else "fail",
        "thresholds": TRANSFER_THRESHOLDS,
        "checks": checks,
        "median_pt_fvu": median_pt_fvu,
        "median_pt_minus_it_fvu": median_difference,
        "median_category_profile_spearman": median_correlation,
        "anchors": rows,
        "chat_reconstruction": chat_reconstruction,
        "behavioral_outcomes_used": False,
    }


def transition_layers(summaries: dict[str, dict[str, Any]]) -> dict[str, Any]:
    contrasts = [
        float(
            summaries[f"pt_res_l{layer}_w16384"]["constructs"]["deception_roleplay"]
            ["aggregate_confirmation_contrast"]
        )
        for layer in range(42)
    ]
    differences = [contrasts[layer] - contrasts[layer - 1] for layer in range(1, 42)]
    largest = max(differences)
    if largest <= 0:
        return {
            "status": "no_positive_transition",
            "rule": "lowest layer with largest positive first difference",
            "deception_confirmation_contrasts": contrasts,
            "first_differences": differences,
            "transition_layer": None,
            "targeted_layers": [],
        }
    transition = min(
        layer
        for layer in range(1, 42)
        if differences[layer - 1] == largest
    )
    selected = sorted({max(0, transition - 1), transition, min(41, transition + 1)})
    return {
        "status": "positive_transition_selected",
        "rule": "lowest layer with largest positive first difference",
        "deception_confirmation_contrasts": contrasts,
        "first_differences": differences,
        "transition_layer": transition,
        "targeted_layers": selected,
    }


def build_sublayer_specs(layers: list[int]) -> list[dict[str, Any]]:
    specs = []
    for layer in layers:
        specs.extend(
            [
                {
                    "model_kind": "pretrained_sae_on_instruction_model",
                    "site": "attention_out",
                    "layer": layer,
                    "width": 16_384,
                    "release": "gemma-scope-9b-pt-att-canonical",
                    "sae_id": f"layer_{layer}/width_16k/canonical",
                    "folder": pt_folder(layer, "attention_out"),
                    "repo": PT_ATT_SAE_REPO,
                    "revision": PT_ATT_SAE_REVISION,
                },
                {
                    "model_kind": "pretrained_sae_on_instruction_model",
                    "site": "mlp_out",
                    "layer": layer,
                    "width": 16_384,
                    "release": "gemma-scope-9b-pt-mlp-canonical",
                    "sae_id": f"layer_{layer}/width_16k/canonical",
                    "folder": pt_folder(layer, "mlp_out"),
                    "repo": PT_MLP_SAE_REPO,
                    "revision": PT_MLP_SAE_REVISION,
                },
            ]
        )
    return specs


def build_feature_manifest(
    summaries: dict[str, dict[str, Any]], transfer: dict[str, Any]
) -> dict[str, Any]:
    feature_sets = {}
    quantiles = {}
    for layer in ANCHOR_LAYERS:
        for width in (16_384, 131_072):
            key = f"it_res_l{layer}_w{width}"
            summary = summaries[key]
            feature_sets[key] = {
                construct: summary["constructs"][construct]["selected_feature_ids"]
                for construct in CONSTRUCTS
            }
            quantiles[key] = dict(summary["active_q90_by_feature"])
    primary_key = f"it_res_l{PRIMARY_LAYER}_w{PRIMARY_WIDTH}"
    controls = summaries[primary_key]["matched_controls"]
    quantiles[primary_key].update(controls["active_q90"])
    return {
        "status": "feature_selection_complete_precalibration",
        "created_at_utc": utc_now(),
        "protocol_version": PROTOCOL_VERSION,
        "feature_sets": feature_sets,
        "matched_control_panels": [panel["feature_ids"] for panel in controls["panels"]],
        "matched_control_details": controls,
        "active_q90_by_sae_and_feature": quantiles,
        "transfer_gate": transfer,
        "selection_used_behavioral_outcomes": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan-dir", type=Path, required=True)
    parser.add_argument("--outdir", type=Path, required=True)
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE)
    args = parser.parse_args()
    plan_dir = args.plan_dir.resolve()
    outdir = args.outdir.resolve()
    atlas_plan_path = plan_dir / "ATLAS_PLAN.json"
    audit_path = plan_dir / "independent_plan_audit.json"
    lock_path = plan_dir / "PLAN_LOCK.json"
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    if audit.get("status") != "pass" or audit.get("behavioral_outcomes_read") is not False:
        raise RuntimeError("Outcome-free independent plan audit did not pass")
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    if lock.get("status") != "locked":
        raise RuntimeError("Outcome-free plan lock is not valid")
    for field, path in (
        ("baseline_plan_sha256", plan_dir / "baseline_plan.jsonl"),
        ("atlas_plan_sha256", atlas_plan_path),
        ("steering_template_sha256", plan_dir / "STEERING_TEMPLATE.json"),
        ("plan_manifest_sha256", plan_dir / "PLAN_MANIFEST.json"),
        ("independent_plan_audit_sha256", audit_path),
    ):
        if lock.get(field) != sha256_file(path):
            raise RuntimeError(f"Outcome-free plan lock differs: {field}")
    atlas_plan = json.loads(atlas_plan_path.read_text(encoding="utf-8"))
    if atlas_plan.get("model") != MODEL_ID or atlas_plan.get("model_revision") != MODEL_REVISION:
        raise RuntimeError("Atlas model binding differs from frozen protocol")
    rows = load_rows(atlas_plan)
    outdir.mkdir(parents=True, exist_ok=True)
    scratch_dir = outdir / "scratch_activation_matrices"
    scratch_dir.mkdir(exist_ok=True)
    plan_copy = outdir / "plan"
    plan_copy.mkdir(exist_ok=True)
    for path in plan_dir.iterdir():
        if path.is_file():
            shutil.copy2(path, plan_copy / path.name)
    write_json(
        outdir / "ATLAS_RUN_MANIFEST.json",
        {
            "status": "running",
            "started_at_utc": utc_now(),
            "protocol_version": PROTOCOL_VERSION,
            "atlas_plan_sha256": sha256_file(atlas_plan_path),
            "plan_audit_sha256": sha256_file(audit_path),
            "plan_lock_sha256": sha256_file(lock_path),
            "n_items": len(rows),
            "behavioral_outcomes_used": False,
        },
    )

    torch_module, model, tokenizer = load_model_and_tokenizer(MODEL_ID, MODEL_REVISION)
    summaries: dict[str, dict[str, Any]] = {}
    direct_specs = atlas_plan["direct_it_saes"]
    summaries.update(
        map_group(
            torch_module=torch_module,
            model=model,
            tokenizer=tokenizer,
            rows=rows,
            specs=direct_specs,
            outdir=outdir,
            scratch_dir=scratch_dir,
            batch_size=args.batch_size,
        )
    )
    pt_specs = atlas_plan["pt_residual_saes"]
    anchor_pt = [spec for spec in pt_specs if int(spec["layer"]) in ANCHOR_LAYERS]
    summaries.update(
        map_group(
            torch_module=torch_module,
            model=model,
            tokenizer=tokenizer,
            rows=rows,
            specs=anchor_pt,
            outdir=outdir,
            scratch_dir=scratch_dir,
            batch_size=args.batch_size,
        )
    )
    chat_reconstruction = measure_chat_transfer_reconstruction(
        torch_module=torch_module,
        model=model,
        tokenizer=tokenizer,
        direct_specs=direct_specs,
        pt_specs=anchor_pt,
    )
    write_json(outdir / "chat_transfer_reconstruction.json", chat_reconstruction)
    transfer = transfer_gate(summaries, chat_reconstruction)
    write_json(outdir / "transfer_gate.json", transfer)
    print(f"PT-to-IT transfer gate: {transfer['status'].upper()}", flush=True)

    transition = None
    sublayer_specs: list[dict[str, Any]] = []
    if transfer["status"] == "pass":
        remaining = [spec for spec in pt_specs if int(spec["layer"]) not in ANCHOR_LAYERS]
        for group in chunked(remaining, GROUP_SIZE):
            summaries.update(
                map_group(
                    torch_module=torch_module,
                    model=model,
                    tokenizer=tokenizer,
                    rows=rows,
                    specs=group,
                    outdir=outdir,
                    scratch_dir=scratch_dir,
                    batch_size=args.batch_size,
                )
            )
        transition = transition_layers(summaries)
        write_json(outdir / "transition_selection.json", transition)
        sublayer_specs = build_sublayer_specs(transition["targeted_layers"])
        summaries.update(
            map_group(
                torch_module=torch_module,
                model=model,
                tokenizer=tokenizer,
                rows=rows,
                specs=sublayer_specs,
                outdir=outdir,
                scratch_dir=scratch_dir,
                batch_size=args.batch_size,
            )
        )

    feature_manifest = build_feature_manifest(summaries, transfer)
    write_json(outdir / "feature_manifest_precalibration.json", feature_manifest)
    scratch_files = list(scratch_dir.glob("*"))
    if scratch_files:
        raise RuntimeError(f"Scratch activation matrices remain after analysis: {scratch_files}")
    scratch_dir.rmdir()
    complete_path = outdir / "atlas_complete.json"
    write_json(
        complete_path,
        {
            "status": "atlas_complete",
            "completed_at_utc": utc_now(),
            "protocol_version": PROTOCOL_VERSION,
            "n_items": len(rows),
            "direct_it_saes": len(direct_specs),
            "pt_anchor_saes": len(anchor_pt),
            "all_layer_pt_residual_completed": transfer["status"] == "pass",
            "pt_residual_saes_completed": sum(key.startswith("pt_res_") for key in summaries),
            "targeted_sublayer_saes_completed": len(sublayer_specs),
            "transfer_gate": transfer["status"],
            "transition_selection": transition,
            "feature_manifest_sha256": sha256_file(
                outdir / "feature_manifest_precalibration.json"
            ),
            "runtime": runtime_metadata(torch_module),
            "behavioral_outcomes_used": False,
        },
    )
    run_manifest_path = outdir / "ATLAS_RUN_MANIFEST.json"
    run_manifest = json.loads(run_manifest_path.read_text(encoding="utf-8"))
    run_manifest.update(
        {
            "status": "complete",
            "completed_at_utc": utc_now(),
            "atlas_complete_sha256": sha256_file(complete_path),
            "feature_manifest_sha256": sha256_file(
                outdir / "feature_manifest_precalibration.json"
            ),
        }
    )
    write_json(run_manifest_path, run_manifest)
    print(f"Gemma Scope atlas complete -> {outdir}", flush=True)


if __name__ == "__main__":
    main()

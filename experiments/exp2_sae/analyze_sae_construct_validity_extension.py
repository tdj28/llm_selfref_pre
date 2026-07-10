#!/usr/bin/env python3
"""Analyze the frozen dual-paraphrase and lexical-counterfactual SAE map."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import statistics
import subprocess
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


TARGET_IDS = (22004, 23893, 30032, 30686, 41533, 58667)
GROUPS = {
    "deception_language": (
        "deception_cover_story",
        "dishonesty_confession",
        "tactical_misdirection",
    ),
    "roleplay_fiction": (
        "fictional_pretending",
        "roleplay_persona",
        "persona_maintenance",
    ),
    "subjective_experience_language": (
        "direct_consciousness_claim",
        "self_ref_mindfulness",
    ),
    "false_self_attribution": ("false_self_attribution",),
    "ai_identity_disclaimer": ("ai_identity_disclaimer",),
    "neutral_controls": (
        "neutral_factual_control",
        "honesty_correction",
        "refusal_safety_disclaimer",
    ),
    "hedged_style": ("hedged_cautious_style",),
}
REGISTERED_CONTRASTS = (
    ("deception_language", "subjective_experience_language"),
    ("roleplay_fiction", "subjective_experience_language"),
    ("hedged_style", "deception_language"),
)
PARAPHRASERS = ("anthropic", "openai")
COUNTERFACTUAL_VARIANTS = (
    "deception_cue_ablated",
    "neutral_cue_transplant",
    "subjective_cue_transplant",
    "deception_scrambled",
)


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if fields is None:
        fields = list(rows[0]) if rows else []
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def mean(values: Iterable[float]) -> float:
    values = list(values)
    return statistics.mean(values) if values else float("nan")


def sample_stats(values: list[float]) -> tuple[float, float]:
    return statistics.mean(values), statistics.stdev(values) if len(values) > 1 else 0.0


def interval(draws: np.ndarray) -> tuple[float, float]:
    return float(np.percentile(draws, 2.5)), float(np.percentile(draws, 97.5))


def feature_matrix(
    activation_rows: list[dict[str, Any]],
) -> tuple[dict[str, dict[int, float]], dict[int, str]]:
    matrix: dict[str, dict[int, float]] = defaultdict(dict)
    roles = {}
    for row in activation_rows:
        item_id = str(row["item_id"])
        feature_id = int(row["feature_id"])
        if feature_id in matrix[item_id]:
            raise ValueError(f"Duplicate item/feature activation: {item_id}/{feature_id}")
        matrix[item_id][feature_id] = float(row["max_activation"])
        previous = roles.setdefault(feature_id, str(row["feature_role"]))
        if previous != str(row["feature_role"]):
            raise ValueError(f"Feature role changed within run: {feature_id}")
    return dict(matrix), roles


def standardization(
    matrix: dict[str, dict[int, float]], feature_ids: Iterable[int]
) -> dict[int, tuple[float, float]]:
    return {
        feature_id: sample_stats([values[feature_id] for values in matrix.values()])
        for feature_id in feature_ids
    }


def score_items(
    matrix: dict[str, dict[int, float]],
    stats: dict[int, tuple[float, float]],
    feature_ids: Iterable[int],
) -> dict[str, dict[str, Any]]:
    selected = tuple(feature_ids)
    output = {}
    for item_id, values in matrix.items():
        z = {
            feature_id: (
                (values[feature_id] - stats[feature_id][0]) / stats[feature_id][1]
                if stats[feature_id][1] > 0
                else 0.0
            )
            for feature_id in selected
        }
        output[item_id] = {
            "feature_z": z,
            "z_mean": statistics.mean(z.values()),
            "z_median": statistics.median(z.values()),
        }
    return output


def clustered_scores(
    rows: list[dict[str, Any]], score_field: str
) -> dict[str, dict[str, np.ndarray]]:
    grouped: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    for row in rows:
        grouped[row["category"]][row["parent_template_id"]].append(
            float(row[score_field])
        )
    return {
        category: {
            template: np.asarray(values, dtype=float)
            for template, values in templates.items()
        }
        for category, templates in grouped.items()
    }


def category_points(
    clusters: dict[str, dict[str, np.ndarray]]
) -> dict[str, float]:
    return {
        category: float(np.mean([values.mean() for values in templates.values()]))
        for category, templates in clusters.items()
    }


def group_points(categories: dict[str, float]) -> dict[str, float]:
    return {
        group: statistics.mean(categories[category] for category in members)
        for group, members in GROUPS.items()
    }


def sample_category_points(
    clusters: dict[str, dict[str, np.ndarray]], rng: np.random.Generator
) -> dict[str, float]:
    sampled = {}
    for category, templates in clusters.items():
        names = sorted(templates)
        selected_templates = rng.integers(0, len(names), size=len(names))
        means = []
        for template_index in selected_templates:
            values = templates[names[int(template_index)]]
            selected_items = rng.integers(0, len(values), size=len(values))
            means.append(float(values[selected_items].mean()))
        sampled[category] = float(np.mean(means))
    return sampled


def paraphrase_analysis(
    metadata: dict[str, dict[str, Any]],
    matrix: dict[str, dict[int, float]],
    roles: dict[int, str],
    iterations: int,
    seed: int,
) -> tuple[
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
]:
    group_rows = []
    contrast_rows = []
    feature_rank_rows = []
    lofo_rows = []
    role_rows = []
    role_ids = {
        role: sorted(feature_id for feature_id, value in roles.items() if value == role)
        for role in ("target", "neighbor", "random")
    }
    for provider_index, provider in enumerate(PARAPHRASERS):
        item_ids = sorted(
            item_id
            for item_id, row in metadata.items()
            if row["variant_type"] == "paraphrase" and row["paraphraser"] == provider
        )
        provider_matrix = {item_id: matrix[item_id] for item_id in item_ids}
        all_stats = standardization(provider_matrix, roles)
        target_scores = score_items(provider_matrix, all_stats, TARGET_IDS)
        analysis_rows = [
            {
                **metadata[item_id],
                "target_z_mean": target_scores[item_id]["z_mean"],
                "target_z_median": target_scores[item_id]["z_median"],
            }
            for item_id in item_ids
        ]
        clusters = clustered_scores(analysis_rows, "target_z_mean")
        points = category_points(clusters)
        groups = group_points(points)
        rng = np.random.default_rng(seed + provider_index * 1000)
        group_draws = {
            group: np.empty(iterations, dtype=float) for group in GROUPS
        }
        contrast_draws = {
            contrast: np.empty(iterations, dtype=float)
            for contrast in REGISTERED_CONTRASTS
        }
        for draw_index in range(iterations):
            sampled_groups = group_points(sample_category_points(clusters, rng))
            for group, value in sampled_groups.items():
                group_draws[group][draw_index] = value
            for left, right in REGISTERED_CONTRASTS:
                contrast_draws[(left, right)][draw_index] = (
                    sampled_groups[left] - sampled_groups[right]
                )
        for group in GROUPS:
            low, high = interval(group_draws[group])
            group_rows.append(
                {
                    "paraphraser": provider,
                    "group": group,
                    "categories": ";".join(GROUPS[group]),
                    "n_items": sum(
                        metadata[item_id]["category"] in GROUPS[group]
                        for item_id in item_ids
                    ),
                    "n_parent_templates": len(
                        {
                            metadata[item_id]["parent_template_id"]
                            for item_id in item_ids
                            if metadata[item_id]["category"] in GROUPS[group]
                        }
                    ),
                    "target_z_mean_template_equal": groups[group],
                    "ci_low": low,
                    "ci_high": high,
                }
            )
        for left, right in REGISTERED_CONTRASTS:
            draws = contrast_draws[(left, right)]
            low, high = interval(draws)
            contrast_rows.append(
                {
                    "paraphraser": provider,
                    "left_group": left,
                    "right_group": right,
                    "observed_difference": groups[left] - groups[right],
                    "ci_low": low,
                    "ci_high": high,
                    "bootstrap_fraction_above_zero": float(np.mean(draws > 0)),
                    "registered": True,
                }
            )

        for feature_id in TARGET_IDS:
            per_feature_rows = [
                {
                    **metadata[item_id],
                    "score": target_scores[item_id]["feature_z"][feature_id],
                }
                for item_id in item_ids
            ]
            category_values = category_points(clustered_scores(per_feature_rows, "score"))
            ranked = sorted(category_values.items(), key=lambda pair: (-pair[1], pair[0]))
            for rank, (category, value) in enumerate(ranked, start=1):
                feature_rank_rows.append(
                    {
                        "paraphraser": provider,
                        "feature_id": feature_id,
                        "rank": rank,
                        "category": category,
                        "template_equal_mean_z": value,
                    }
                )

        for omitted in (None, *TARGET_IDS):
            selected = [feature_id for feature_id in TARGET_IDS if feature_id != omitted]
            scores = score_items(provider_matrix, all_stats, selected)
            rows = [
                {**metadata[item_id], "score": scores[item_id]["z_mean"]}
                for item_id in item_ids
            ]
            groups_selected = group_points(category_points(clustered_scores(rows, "score")))
            lofo_rows.append(
                {
                    "paraphraser": provider,
                    "omitted_feature_id": "none" if omitted is None else omitted,
                    "n_features": len(selected),
                    "deception_minus_subjective": (
                        groups_selected["deception_language"]
                        - groups_selected["subjective_experience_language"]
                    ),
                }
            )

        for role, feature_ids in role_ids.items():
            scores = score_items(provider_matrix, all_stats, feature_ids)
            rows = [
                {**metadata[item_id], "score": scores[item_id]["z_mean"]}
                for item_id in item_ids
            ]
            role_groups = group_points(category_points(clustered_scores(rows, "score")))
            active_features = sum(all_stats[feature_id][1] > 0 for feature_id in feature_ids)
            role_rows.append(
                {
                    "paraphraser": provider,
                    "feature_role": role,
                    "n_features": len(feature_ids),
                    "n_nonzero_sd_features": active_features,
                    "deception_minus_subjective": (
                        role_groups["deception_language"]
                        - role_groups["subjective_experience_language"]
                    ),
                }
            )
    return group_rows, contrast_rows, feature_rank_rows, lofo_rows, role_rows


def paired_cluster_draws(
    rows: list[dict[str, Any]],
    field: str,
    iterations: int,
    seed: int,
) -> np.ndarray:
    grouped: dict[str, list[float]] = defaultdict(list)
    for row in rows:
        grouped[row["parent_item_id"]].append(float(row[field]))
    names = sorted(grouped)
    rng = np.random.default_rng(seed)
    draws = np.empty(iterations, dtype=float)
    for index in range(iterations):
        selected = rng.integers(0, len(names), size=len(names))
        values = [value for group_index in selected for value in grouped[names[int(group_index)]]]
        draws[index] = float(np.mean(values))
    return draws


def discovery_baseline(
    discovery_dir: Path,
) -> tuple[dict[int, tuple[float, float]], float, float, dict[str, dict[int, float]]]:
    activation_rows = [
        row
        for row in read_jsonl(discovery_dir / "item_feature_activations.jsonl")
        if int(row["feature_id"]) in TARGET_IDS
    ]
    matrix, _roles = feature_matrix(activation_rows)
    stats = standardization(matrix, TARGET_IDS)
    scores = score_items(matrix, stats, TARGET_IDS)
    assignments = {
        row["item_id"]: row
        for row in read_csv(
            discovery_dir / "template_robustness" / "template_assignments.csv"
        )
    }
    rows = [
        {
            "item_id": item_id,
            "category": assignments[item_id]["category"],
            "parent_template_id": assignments[item_id]["template_id"],
            "score": scores[item_id]["z_mean"],
        }
        for item_id in matrix
    ]
    groups = group_points(category_points(clustered_scores(rows, "score")))
    denominator = groups["deception_language"] - groups["neutral_controls"]
    return stats, denominator, groups["neutral_controls"], matrix


def lexical_analysis(
    metadata: dict[str, dict[str, Any]],
    matrix: dict[str, dict[int, float]],
    baseline_stats: dict[int, tuple[float, float]],
    discovery_gap: float,
    discovery_neutral: float,
    iterations: int,
    seed: int,
) -> tuple[
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
    dict[str, Any],
]:
    all_scores = score_items(matrix, baseline_stats, TARGET_IDS)
    pair_rows = []
    for item_id, row in sorted(metadata.items()):
        if row["variant_type"] not in COUNTERFACTUAL_VARIANTS:
            continue
        source_id = row["source_paraphrase_item_id"]
        variant_score = all_scores[item_id]
        source_score = all_scores[source_id]
        pair = {
            "item_id": item_id,
            "variant_type": row["variant_type"],
            "source_paraphraser": row["paraphraser"],
            "parent_item_id": row["parent_item_id"],
            "parent_template_id": row["parent_template_id"],
            "source_paraphrase_item_id": source_id,
            "source_target_z_mean": source_score["z_mean"],
            "variant_target_z_mean": variant_score["z_mean"],
            "target_z_mean_delta": variant_score["z_mean"] - source_score["z_mean"],
            "source_target_z_median": source_score["z_median"],
            "variant_target_z_median": variant_score["z_median"],
            "target_z_median_delta": variant_score["z_median"]
            - source_score["z_median"],
            "assigned_feature_id": row.get("assigned_feature_id", ""),
        }
        for feature_id in TARGET_IDS:
            pair[f"feature_{feature_id}_delta"] = (
                variant_score["feature_z"][feature_id]
                - source_score["feature_z"][feature_id]
            )
        assigned = row.get("assigned_feature_id")
        pair["assigned_feature_z_delta"] = (
            pair[f"feature_{int(assigned)}_delta"] if assigned not in {None, ""} else ""
        )
        pair_rows.append(pair)

    variant_rows = []
    for variant_index, variant in enumerate(COUNTERFACTUAL_VARIANTS):
        variants = [row for row in pair_rows if row["variant_type"] == variant]
        for provider in ("all", *PARAPHRASERS):
            selected = (
                variants
                if provider == "all"
                else [row for row in variants if row["source_paraphraser"] == provider]
            )
            draws = paired_cluster_draws(
                selected,
                "target_z_mean_delta",
                iterations,
                seed + variant_index * 100 + (0 if provider == "all" else PARAPHRASERS.index(provider) + 1),
            )
            low, high = interval(draws)
            variant_rows.append(
                {
                    "variant_type": variant,
                    "source_paraphraser": provider,
                    "n_pairs": len(selected),
                    "n_parent_items": len({row["parent_item_id"] for row in selected}),
                    "mean_source_target_z": mean(row["source_target_z_mean"] for row in selected),
                    "mean_variant_target_z": mean(row["variant_target_z_mean"] for row in selected),
                    "mean_target_z_delta": mean(row["target_z_mean_delta"] for row in selected),
                    "ci_low": low,
                    "ci_high": high,
                    "mean_target_median_z_delta": mean(
                        row["target_z_median_delta"] for row in selected
                    ),
                }
            )

    feature_rows = []
    for variant_index, variant in enumerate(COUNTERFACTUAL_VARIANTS):
        selected = [row for row in pair_rows if row["variant_type"] == variant]
        for feature_id in TARGET_IDS:
            field = f"feature_{feature_id}_delta"
            draws = paired_cluster_draws(
                selected, field, iterations, seed + 10000 + variant_index * 100 + feature_id
            )
            low, high = interval(draws)
            feature_rows.append(
                {
                    "variant_type": variant,
                    "feature_id": feature_id,
                    "n_pairs": len(selected),
                    "mean_feature_z_delta": mean(row[field] for row in selected),
                    "ci_low": low,
                    "ci_high": high,
                }
            )

    assigned_rows = []
    for variant_index, variant in enumerate(
        ("neutral_cue_transplant", "subjective_cue_transplant")
    ):
        variants = [row for row in pair_rows if row["variant_type"] == variant]
        for feature_id in TARGET_IDS:
            selected = [
                row for row in variants if int(row["assigned_feature_id"]) == feature_id
            ]
            draws = paired_cluster_draws(
                selected,
                "assigned_feature_z_delta",
                iterations,
                seed + 20000 + variant_index * 100 + feature_id,
            )
            low, high = interval(draws)
            assigned_rows.append(
                {
                    "variant_type": variant,
                    "assigned_feature_id": feature_id,
                    "n_pairs": len(selected),
                    "mean_assigned_feature_z_delta": mean(
                        float(row["assigned_feature_z_delta"]) for row in selected
                    ),
                    "ci_low": low,
                    "ci_high": high,
                }
            )

    overall = {
        row["variant_type"]: row
        for row in variant_rows
        if row["source_paraphraser"] == "all"
    }
    neutral_draws = paired_cluster_draws(
        [row for row in pair_rows if row["variant_type"] == "neutral_cue_transplant"],
        "target_z_mean_delta",
        iterations,
        seed + 30000,
    )
    ablation_draws = paired_cluster_draws(
        [row for row in pair_rows if row["variant_type"] == "deception_cue_ablated"],
        "target_z_mean_delta",
        iterations,
        seed + 30001,
    )
    recovery_draws = neutral_draws / discovery_gap
    removal_draws = -ablation_draws / discovery_gap
    recovery_low, recovery_high = interval(recovery_draws)
    removal_low, removal_high = interval(removal_draws)
    scramble = overall["deception_scrambled"]
    scramble_ratio = (
        scramble["mean_variant_target_z"] / scramble["mean_source_target_z"]
        if abs(scramble["mean_source_target_z"]) > 1e-12
        else None
    )
    recovery = {
        "discovery_template_equal_deception_minus_neutral_gap": discovery_gap,
        "discovery_template_equal_neutral_mean": discovery_neutral,
        "neutral_cue_transplant_recovery_fraction": (
            overall["neutral_cue_transplant"]["mean_target_z_delta"] / discovery_gap
        ),
        "neutral_cue_transplant_recovery_ci_low": recovery_low,
        "neutral_cue_transplant_recovery_ci_high": recovery_high,
        "cue_ablation_removal_fraction": (
            -overall["deception_cue_ablated"]["mean_target_z_delta"] / discovery_gap
        ),
        "cue_ablation_removal_ci_low": removal_low,
        "cue_ablation_removal_ci_high": removal_high,
        "scrambled_variant_over_source_target_z_ratio": scramble_ratio,
        "lexical_entanglement_threshold": 0.5,
        "neutral_transplant_crosses_threshold": (
            overall["neutral_cue_transplant"]["mean_target_z_delta"] / discovery_gap
            >= 0.5
        ),
        "ablation_crosses_threshold": (
            -overall["deception_cue_ablated"]["mean_target_z_delta"] / discovery_gap
            >= 0.5
        ),
        "ratio_boundary": (
            "Recovery/removal denominators are fixed from the inspected discovery corpus; "
            "bootstrap intervals resample paired extension rows and do not propagate discovery-gap uncertainty."
        ),
    }
    return pair_rows, variant_rows, feature_rows, assigned_rows, recovery


def protocol_audit(
    run_dir: Path,
    plan_dir: Path,
    discovery_dir: Path,
    metadata_rows: list[dict[str, Any]],
    corpus_rows: list[dict[str, str]],
    activation_rows: list[dict[str, Any]],
    matrix: dict[str, dict[int, float]],
    roles: dict[int, str],
) -> dict[str, Any]:
    plan_manifest = read_json(plan_dir / "MANIFEST.json")
    run_manifest = read_json(run_dir / "manifest.json")
    feature_plan = read_csv(run_dir / "feature_plan.csv")
    discovery_feature_plan = read_csv(discovery_dir / "feature_plan.csv")
    metadata = {row["item_id"]: row for row in metadata_rows}
    corpus = {row["item_id"]: row for row in corpus_rows}
    feature_ids = {int(row["feature_id"]) for row in feature_plan}
    checks = {
        "frozen_input_hash_matches_plan": sha256(plan_dir / "mapping_input.jsonl")
        == plan_manifest["mapping_input_sha256"],
        "run_declares_2606_items": int(run_manifest["n_corpus_items"])
        == plan_manifest["n_mapping_items"]
        == 2606,
        "metadata_count_and_ids_exact": len(metadata_rows) == 2606
        and len(metadata) == 2606,
        "run_corpus_count_and_ids_exact": len(corpus_rows) == 2606
        and set(corpus) == set(metadata),
        "run_corpus_text_hashes_match_frozen_input": all(
            corpus[item_id]["text_sha256"] == metadata[item_id]["text_sha256"]
            for item_id in metadata
        ),
        "activation_item_ids_exact": set(matrix) == set(metadata),
        "feature_plan_matches_discovery": feature_plan == discovery_feature_plan,
        "feature_count_66": len(feature_ids) == 66 and len(roles) == 66,
        "target_ids_exact": {
            feature_id for feature_id, role in roles.items() if role == "target"
        }
        == set(TARGET_IDS),
        "complete_item_feature_grid": len(activation_rows) == 2606 * 66
        and all(set(values) == feature_ids for values in matrix.values()),
        "no_legacy_clean_item_ids": all(
            not item_id.startswith("clean_") for item_id in matrix
        ),
        "paraphrase_count_matches_frozen_plan": sum(
            row["variant_type"] == "paraphrase" for row in metadata_rows
        )
        == plan_manifest["n_paraphrases"],
        "counterfactual_count_matches_frozen_plan": sum(
            row["variant_type"] != "paraphrase" for row in metadata_rows
        )
        == plan_manifest["n_counterfactuals"],
    }
    return {
        "status": "pass" if all(checks.values()) else "fail",
        "checks": checks,
        "counts": {
            "items": len(metadata),
            "features": len(feature_ids),
            "activation_rows": len(activation_rows),
            "paraphrases_by_provider": dict(
                sorted(
                    Counter(
                        row["paraphraser"]
                        for row in metadata_rows
                        if row["variant_type"] == "paraphrase"
                    ).items()
                )
            ),
            "counterfactuals_by_variant": dict(
                sorted(
                    Counter(
                        row["variant_type"]
                        for row in metadata_rows
                        if row["variant_type"] != "paraphrase"
                    ).items()
                )
            ),
        },
        "input_sha256": {
            "frozen_mapping_input": sha256(plan_dir / "mapping_input.jsonl"),
            "run_mapping_corpus": sha256(run_dir / "mapping_corpus.csv"),
            "run_activations": sha256(run_dir / "item_feature_activations.jsonl"),
            "run_feature_plan": sha256(run_dir / "feature_plan.csv"),
        },
    }


def make_figure(
    contrast_rows: list[dict[str, Any]],
    variant_rows: list[dict[str, Any]],
    path: Path,
) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(12.4, 4.8))
    contrast_order = list(REGISTERED_CONTRASTS)
    labels = ["Deception -\nsubjective", "Roleplay -\nsubjective", "Hedging -\ndeception"]
    colors = {"anthropic": "#D55E00", "openai": "#0072B2"}
    offsets = {"anthropic": -0.12, "openai": 0.12}
    for provider in PARAPHRASERS:
        rows = {
            (row["left_group"], row["right_group"]): row
            for row in contrast_rows
            if row["paraphraser"] == provider
        }
        x = np.arange(len(contrast_order), dtype=float) + offsets[provider]
        y = np.asarray([rows[key]["observed_difference"] for key in contrast_order])
        low = np.asarray([rows[key]["ci_low"] for key in contrast_order])
        high = np.asarray([rows[key]["ci_high"] for key in contrast_order])
        axes[0].errorbar(
            x,
            y,
            yerr=np.vstack((y - low, high - y)),
            fmt="o",
            capsize=4,
            color=colors[provider],
            label=provider.capitalize(),
        )
    axes[0].axhline(0, color="#333333", linewidth=1)
    axes[0].set_xticks(range(len(labels)), labels)
    axes[0].set_ylabel("Template-cluster contrast (mean target z)")
    axes[0].set_title("Paraphrase replication")
    axes[0].legend(frameon=False)

    variant_order = list(COUNTERFACTUAL_VARIANTS)
    variant_labels = ["Cue\nablation", "Neutral cue\ntransplant", "Subjective cue\ntransplant", "Word\nscramble"]
    overall = {
        row["variant_type"]: row
        for row in variant_rows
        if row["source_paraphraser"] == "all"
    }
    x = np.arange(len(variant_order))
    y = np.asarray([overall[variant]["mean_target_z_delta"] for variant in variant_order])
    low = np.asarray([overall[variant]["ci_low"] for variant in variant_order])
    high = np.asarray([overall[variant]["ci_high"] for variant in variant_order])
    axes[1].errorbar(
        x,
        y,
        yerr=np.vstack((y - low, high - y)),
        fmt="o",
        capsize=4,
        color="#009E73",
    )
    axes[1].axhline(0, color="#333333", linewidth=1)
    axes[1].set_xticks(x, variant_labels)
    axes[1].set_ylabel("Paired change (discovery-scaled target z)")
    axes[1].set_title("Lexical counterfactuals")
    fig.suptitle("Public SAE construct-validity extension", fontsize=13)
    fig.tight_layout()
    fig.savefig(path, dpi=220, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def write_summary(
    path: Path,
    audit: dict[str, Any],
    contrast_rows: list[dict[str, Any]],
    variant_rows: list[dict[str, Any]],
    recovery: dict[str, Any],
    rank_rows: list[dict[str, Any]],
    lofo_rows: list[dict[str, Any]],
) -> None:
    lines = [
        "# Public-SAE Construct-Validity Extension",
        "",
        f"Protocol audit: **{audit['status'].upper()}**.",
        "",
        "## Registered Paraphrase Contrasts",
        "",
        "| Paraphraser | Contrast | Difference | 95% cluster interval |",
        "|---|---|---:|---|",
    ]
    for row in contrast_rows:
        lines.append(
            f"| `{row['paraphraser']}` | `{row['left_group']} - {row['right_group']}` | "
            f"{row['observed_difference']:.3f} | [{row['ci_low']:.3f}, {row['ci_high']:.3f}] |"
        )
    lines.extend(
        [
            "",
            "## Lexical Counterfactuals",
            "",
            "| Variant | n | Mean paired target-z change | 95% paired interval |",
            "|---|---:|---:|---|",
        ]
    )
    for row in variant_rows:
        if row["source_paraphraser"] != "all":
            continue
        lines.append(
            f"| `{row['variant_type']}` | {row['n_pairs']} | "
            f"{row['mean_target_z_delta']:.3f} | [{row['ci_low']:.3f}, {row['ci_high']:.3f}] |"
        )
    lines.extend(
        [
            "",
            f"Neutral cue-transplant recovery fraction: {recovery['neutral_cue_transplant_recovery_fraction']:.3f} "
            f"[{recovery['neutral_cue_transplant_recovery_ci_low']:.3f}, "
            f"{recovery['neutral_cue_transplant_recovery_ci_high']:.3f}].",
            "",
            f"Cue-ablation removal fraction: {recovery['cue_ablation_removal_fraction']:.3f} "
            f"[{recovery['cue_ablation_removal_ci_low']:.3f}, "
            f"{recovery['cue_ablation_removal_ci_high']:.3f}].",
            "",
            "## Robustness Diagnostics",
            "",
        ]
    )
    for provider in PARAPHRASERS:
        top_subjective = sum(
            row["rank"] == 1 and row["category"] in GROUPS["subjective_experience_language"]
            for row in rank_rows
            if row["paraphraser"] == provider
        )
        lofo = [
            row["deception_minus_subjective"]
            for row in lofo_rows
            if row["paraphraser"] == provider and row["omitted_feature_id"] != "none"
        ]
        lines.append(
            f"- `{provider}`: subjective-experience categories rank first for "
            f"{top_subjective}/6 targets; leave-one-feature-out deception-minus-subjective "
            f"range [{min(lofo):.3f}, {max(lofo):.3f}]."
        )
    lines.extend(
        [
            "",
            "## Claim Boundary",
            "",
            "These are controlled model-written paraphrases and lexical counterfactuals under one public checkpoint. "
            "They do not establish natural-corpus generalization, a canonical feature ontology, consciousness, or "
            "equivalence to the proprietary Goodfire/Steering API.",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_release_manifest(run_dir: Path, audit: dict[str, Any]) -> None:
    output = run_dir / "release_manifest.json"
    files = []
    for path in sorted(run_dir.rglob("*")):
        if path.is_file() and path != output:
            files.append(
                {
                    "path": str(path.relative_to(run_dir)),
                    "bytes": path.stat().st_size,
                    "sha256": sha256(path),
                }
            )
    try:
        commit = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=Path(__file__).resolve().parents[2], text=True
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        commit = None
    write_json(
        output,
        {
            "created_at_utc": datetime.now(timezone.utc).isoformat(),
            "analysis_code_commit": commit,
            "audit_status": audit["status"],
            "files": files,
        },
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_dir", type=Path)
    parser.add_argument(
        "--plan-dir",
        type=Path,
        default=Path(
            "data/public_sae_feature_maps/70b_construct_validity_extension_plan_20260710"
        ),
    )
    parser.add_argument(
        "--discovery-dir",
        type=Path,
        default=Path("data/public_sae_feature_maps/70b_balanced_80_20260709"),
    )
    parser.add_argument("--iterations", type=int, default=5000)
    parser.add_argument("--seed", type=int, default=20260710)
    args = parser.parse_args()
    run_dir = args.run_dir
    metadata_rows = read_jsonl(args.plan_dir / "mapping_input.jsonl")
    counterfactual_details = {
        row["item_id"]: row
        for row in read_jsonl(args.plan_dir / "counterfactuals.jsonl")
    }
    metadata_rows = [
        {
            **row,
            **(
                {
                    "assigned_feature_id": counterfactual_details[row["item_id"]].get(
                        "assigned_feature_id"
                    ),
                    "assigned_cues": counterfactual_details[row["item_id"]].get(
                        "assigned_cues", []
                    ),
                }
                if row["item_id"] in counterfactual_details
                else {}
            ),
        }
        for row in metadata_rows
    ]
    metadata = {row["item_id"]: row for row in metadata_rows}
    corpus_rows = read_csv(run_dir / "mapping_corpus.csv")
    activation_rows = read_jsonl(run_dir / "item_feature_activations.jsonl")
    matrix, roles = feature_matrix(activation_rows)
    audit = protocol_audit(
        run_dir,
        args.plan_dir,
        args.discovery_dir,
        metadata_rows,
        corpus_rows,
        activation_rows,
        matrix,
        roles,
    )
    write_json(run_dir / "construct_validity_protocol_audit.json", audit)
    if audit["status"] != "pass":
        raise SystemExit("Construct-validity protocol audit failed")

    group_rows, contrast_rows, rank_rows, lofo_rows, role_rows = paraphrase_analysis(
        metadata, matrix, roles, args.iterations, args.seed
    )
    baseline_stats, discovery_gap, discovery_neutral, _ = discovery_baseline(
        args.discovery_dir
    )
    pair_rows, variant_rows, feature_rows, assigned_rows, recovery = lexical_analysis(
        metadata,
        matrix,
        baseline_stats,
        discovery_gap,
        discovery_neutral,
        args.iterations,
        args.seed,
    )
    write_csv(run_dir / "paraphrase_construct_groups.csv", group_rows)
    write_csv(run_dir / "paraphrase_registered_contrasts.csv", contrast_rows)
    write_csv(run_dir / "paraphrase_feature_category_rankings.csv", rank_rows)
    write_csv(run_dir / "paraphrase_leave_one_feature_out.csv", lofo_rows)
    write_csv(run_dir / "paraphrase_feature_role_controls.csv", role_rows)
    write_csv(run_dir / "lexical_pair_effects.csv", pair_rows)
    write_csv(run_dir / "lexical_variant_summary.csv", variant_rows)
    write_csv(run_dir / "lexical_feature_effects.csv", feature_rows)
    write_csv(run_dir / "lexical_assigned_feature_effects.csv", assigned_rows)
    write_json(run_dir / "lexical_recovery_diagnostics.json", recovery)
    make_figure(
        contrast_rows,
        variant_rows,
        run_dir / "construct_validity_extension.png",
    )
    write_summary(
        run_dir / "construct_validity_summary.md",
        audit,
        contrast_rows,
        variant_rows,
        recovery,
        rank_rows,
        lofo_rows,
    )
    write_release_manifest(run_dir, audit)
    print(f"Construct-validity extension analysis: PASS -> {run_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

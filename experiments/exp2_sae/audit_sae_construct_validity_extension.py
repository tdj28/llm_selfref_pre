#!/usr/bin/env python3
"""Independently recompute construct-validity extension headline point estimates."""

from __future__ import annotations

import argparse
import csv
import json
import statistics
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable


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
VARIANTS = (
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


def close(left: float, right: float, tolerance: float = 1e-12) -> bool:
    return abs(left - right) <= tolerance


def matrix_from_rows(
    rows: list[dict[str, Any]], feature_ids: set[int] | None = None
) -> dict[str, dict[int, float]]:
    matrix: dict[str, dict[int, float]] = defaultdict(dict)
    for row in rows:
        feature_id = int(row["feature_id"])
        if feature_ids is not None and feature_id not in feature_ids:
            continue
        item_id = str(row["item_id"])
        if feature_id in matrix[item_id]:
            raise ValueError(f"Duplicate activation: {item_id}/{feature_id}")
        matrix[item_id][feature_id] = float(row["max_activation"])
    return dict(matrix)


def stats(
    matrix: dict[str, dict[int, float]], feature_ids: Iterable[int]
) -> dict[int, tuple[float, float]]:
    output = {}
    for feature_id in feature_ids:
        values = [row[feature_id] for row in matrix.values()]
        output[feature_id] = (statistics.mean(values), statistics.stdev(values))
    return output


def scores(
    matrix: dict[str, dict[int, float]],
    feature_stats: dict[int, tuple[float, float]],
    feature_ids: Iterable[int],
) -> dict[str, float]:
    selected = tuple(feature_ids)
    return {
        item_id: statistics.mean(
            (values[feature_id] - feature_stats[feature_id][0])
            / feature_stats[feature_id][1]
            if feature_stats[feature_id][1] > 0
            else 0.0
            for feature_id in selected
        )
        for item_id, values in matrix.items()
    }


def category_points(
    metadata: dict[str, dict[str, Any]],
    item_scores: dict[str, float],
) -> dict[str, float]:
    grouped: dict[str, dict[str, list[float]]] = defaultdict(
        lambda: defaultdict(list)
    )
    for item_id, value in item_scores.items():
        row = metadata[item_id]
        grouped[row["category"]][row["parent_template_id"]].append(value)
    return {
        category: statistics.mean(
            statistics.mean(values) for values in templates.values()
        )
        for category, templates in grouped.items()
    }


def group_points(categories: dict[str, float]) -> dict[str, float]:
    return {
        group: statistics.mean(categories[category] for category in members)
        for group, members in GROUPS.items()
    }


def reported_contrasts(path: Path) -> dict[tuple[str, str, str], float]:
    return {
        (row["paraphraser"], row["left_group"], row["right_group"]): float(
            row["observed_difference"]
        )
        for row in read_csv(path)
    }


def reported_lofo(path: Path) -> dict[tuple[str, str], float]:
    return {
        (row["paraphraser"], row["omitted_feature_id"]): float(
            row["deception_minus_subjective"]
        )
        for row in read_csv(path)
    }


def paraphrase_points(
    metadata: dict[str, dict[str, Any]],
    matrix: dict[str, dict[int, float]],
) -> tuple[dict[tuple[str, str, str], float], dict[tuple[str, str], float]]:
    contrasts = {}
    lofo = {}
    for provider in ("anthropic", "openai"):
        item_ids = {
            item_id
            for item_id, row in metadata.items()
            if row["variant_type"] == "paraphrase" and row["paraphraser"] == provider
        }
        provider_matrix = {item_id: matrix[item_id] for item_id in item_ids}
        provider_stats = stats(provider_matrix, TARGET_IDS)
        target_scores = scores(provider_matrix, provider_stats, TARGET_IDS)
        groups = group_points(category_points(metadata, target_scores))
        for left, right in REGISTERED_CONTRASTS:
            contrasts[(provider, left, right)] = groups[left] - groups[right]
        for omitted in (None, *TARGET_IDS):
            selected = [feature_id for feature_id in TARGET_IDS if feature_id != omitted]
            selected_scores = scores(provider_matrix, provider_stats, selected)
            selected_groups = group_points(category_points(metadata, selected_scores))
            key = "none" if omitted is None else str(omitted)
            lofo[(provider, key)] = (
                selected_groups["deception_language"]
                - selected_groups["subjective_experience_language"]
            )
    return contrasts, lofo


def discovery_points(
    discovery_dir: Path,
) -> tuple[dict[int, tuple[float, float]], float]:
    rows = read_jsonl(discovery_dir / "item_feature_activations.jsonl")
    matrix = matrix_from_rows(rows, set(TARGET_IDS))
    feature_stats = stats(matrix, TARGET_IDS)
    item_scores = scores(matrix, feature_stats, TARGET_IDS)
    assignments = {
        row["item_id"]: {
            "category": row["category"],
            "parent_template_id": row["template_id"],
        }
        for row in read_csv(
            discovery_dir / "template_robustness" / "template_assignments.csv"
        )
    }
    groups = group_points(category_points(assignments, item_scores))
    return feature_stats, groups["deception_language"] - groups["neutral_controls"]


def lexical_points(
    metadata: dict[str, dict[str, Any]],
    matrix: dict[str, dict[int, float]],
    feature_stats: dict[int, tuple[float, float]],
) -> tuple[dict[str, float], dict[tuple[str, int], float]]:
    feature_z: dict[str, dict[int, float]] = {}
    aggregate = {}
    for item_id, values in matrix.items():
        row = {
            feature_id: (
                (values[feature_id] - feature_stats[feature_id][0])
                / feature_stats[feature_id][1]
                if feature_stats[feature_id][1] > 0
                else 0.0
            )
            for feature_id in TARGET_IDS
        }
        feature_z[item_id] = row
        aggregate[item_id] = statistics.mean(row.values())
    deltas: dict[str, list[float]] = defaultdict(list)
    assigned: dict[tuple[str, int], list[float]] = defaultdict(list)
    for item_id, row in metadata.items():
        variant = row["variant_type"]
        if variant not in VARIANTS:
            continue
        source_id = row["source_paraphrase_item_id"]
        deltas[variant].append(aggregate[item_id] - aggregate[source_id])
        feature_id = row.get("assigned_feature_id")
        if feature_id not in {None, ""}:
            feature_id = int(feature_id)
            assigned[(variant, feature_id)].append(
                feature_z[item_id][feature_id] - feature_z[source_id][feature_id]
            )
    return (
        {variant: statistics.mean(deltas[variant]) for variant in VARIANTS},
        {key: statistics.mean(values) for key, values in assigned.items()},
    )


def reported_variant_points(path: Path) -> dict[str, float]:
    return {
        row["variant_type"]: float(row["mean_target_z_delta"])
        for row in read_csv(path)
        if row["source_paraphraser"] == "all"
    }


def reported_assigned_points(path: Path) -> dict[tuple[str, int], float]:
    return {
        (row["variant_type"], int(row["assigned_feature_id"])): float(
            row["mean_assigned_feature_z_delta"]
        )
        for row in read_csv(path)
    }


def mapping_metadata(plan_dir: Path) -> dict[str, dict[str, Any]]:
    rows = read_jsonl(plan_dir / "mapping_input.jsonl")
    details = {
        row["item_id"]: row for row in read_jsonl(plan_dir / "counterfactuals.jsonl")
    }
    output = {}
    for row in rows:
        merged = dict(row)
        if row["item_id"] in details:
            merged["assigned_feature_id"] = details[row["item_id"]].get(
                "assigned_feature_id"
            )
        output[row["item_id"]] = merged
    return output


def all_close(
    calculated: dict[Any, float], reported: dict[Any, float]
) -> bool:
    return set(calculated) == set(reported) and all(
        close(value, reported[key]) for key, value in calculated.items()
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
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    output = args.out or args.run_dir / "independent_headline_audit.json"
    metadata = mapping_metadata(args.plan_dir)
    activation_rows = read_jsonl(args.run_dir / "item_feature_activations.jsonl")
    matrix = matrix_from_rows(activation_rows)
    feature_ids = set(next(iter(matrix.values())))
    target_matrix = {
        item_id: {feature_id: values[feature_id] for feature_id in TARGET_IDS}
        for item_id, values in matrix.items()
    }
    contrasts, lofo = paraphrase_points(metadata, target_matrix)
    baseline_stats, discovery_gap = discovery_points(args.discovery_dir)
    variants, assigned = lexical_points(metadata, target_matrix, baseline_stats)
    recovery = read_json(args.run_dir / "lexical_recovery_diagnostics.json")
    protocol = read_json(args.run_dir / "construct_validity_protocol_audit.json")
    reported_contrast = reported_contrasts(
        args.run_dir / "paraphrase_registered_contrasts.csv"
    )
    reported_lofo_points = reported_lofo(
        args.run_dir / "paraphrase_leave_one_feature_out.csv"
    )
    reported_variants = reported_variant_points(
        args.run_dir / "lexical_variant_summary.csv"
    )
    reported_assigned = reported_assigned_points(
        args.run_dir / "lexical_assigned_feature_effects.csv"
    )
    checks = {
        "protocol_audit_passes": protocol["status"] == "pass",
        "item_count_2606": len(matrix) == len(metadata) == 2606,
        "feature_count_66": len(feature_ids) == 66,
        "complete_feature_grid": all(set(values) == feature_ids for values in matrix.values()),
        "registered_paraphrase_points_match": all_close(contrasts, reported_contrast),
        "leave_one_feature_points_match": all_close(lofo, reported_lofo_points),
        "lexical_variant_points_match": all_close(variants, reported_variants),
        "assigned_feature_points_match": all_close(assigned, reported_assigned),
        "discovery_gap_matches_recovery_denominator": close(
            discovery_gap,
            float(recovery["discovery_template_equal_deception_minus_neutral_gap"]),
        ),
        "neutral_recovery_point_matches": close(
            variants["neutral_cue_transplant"] / discovery_gap,
            float(recovery["neutral_cue_transplant_recovery_fraction"]),
        ),
        "ablation_removal_point_matches": close(
            -variants["deception_cue_ablated"] / discovery_gap,
            float(recovery["cue_ablation_removal_fraction"]),
        ),
    }
    payload = {
        "status": "pass" if all(checks.values()) else "fail",
        "method": (
            "Independent Python-standard-library point-estimate recomputation from raw "
            "activations and frozen metadata; does not import the primary analyzer."
        ),
        "checks": checks,
        "counts": {
            "items": len(matrix),
            "features": len(feature_ids),
            "activation_rows": len(activation_rows),
            "variant_pairs": dict(
                sorted(
                    Counter(
                        row["variant_type"]
                        for row in metadata.values()
                        if row["variant_type"] in VARIANTS
                    ).items()
                )
            ),
        },
        "registered_paraphrase_points": {
            "|".join(key): value for key, value in sorted(contrasts.items())
        },
        "leave_one_feature_points": {
            "|".join(key): value for key, value in sorted(lofo.items())
        },
        "lexical_variant_points": variants,
        "assigned_feature_points": {
            f"{variant}|{feature_id}": value
            for (variant, feature_id), value in sorted(assigned.items())
        },
        "discovery_deception_minus_neutral_gap": discovery_gap,
    }
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if payload["status"] != "pass":
        raise SystemExit(f"Construct-validity independent audit failed: {output}")
    print(f"Independent construct-validity audit: PASS -> {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Independently recompute public-SAE mapping headline point estimates."""

from __future__ import annotations

import argparse
import csv
import json
import statistics
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


TARGET_IDS = {22004, 23893, 30032, 30686, 41533, 58667}
CONSTRUCT_GROUPS = {
    "deception_language": {
        "deception_cover_story",
        "dishonesty_confession",
        "tactical_misdirection",
    },
    "roleplay_fiction": {
        "fictional_pretending",
        "roleplay_persona",
        "persona_maintenance",
    },
    "subjective_experience_language": {
        "direct_consciousness_claim",
        "self_ref_mindfulness",
    },
}


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def close(left: float, right: float, tolerance: float = 1e-12) -> bool:
    return abs(left - right) <= tolerance


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    run_dir = args.run_dir
    output = args.out or run_dir / "independent_headline_audit.json"

    rows = read_jsonl(run_dir / "item_feature_activations.jsonl")
    item_categories = {str(row["item_id"]): str(row["category"]) for row in rows}
    feature_roles = {int(row["feature_id"]): str(row["feature_role"]) for row in rows}
    values_by_item: dict[str, dict[int, float]] = defaultdict(dict)
    values_by_feature_category: dict[tuple[int, str], list[float]] = defaultdict(list)
    for row in rows:
        item_id = str(row["item_id"])
        feature_id = int(row["feature_id"])
        category = str(row["category"])
        value = float(row["max_activation"])
        values_by_item[item_id][feature_id] = value
        values_by_feature_category[(feature_id, category)].append(value)

    categories = sorted(set(item_categories.values()))
    target_ids = {feature_id for feature_id, role in feature_roles.items() if role == "target"}
    raw_top_categories = {}
    for feature_id in sorted(target_ids):
        means = {
            category: statistics.mean(values_by_feature_category[(feature_id, category)])
            for category in categories
        }
        top_category = max(means, key=means.get)
        raw_top_categories[str(feature_id)] = {
            "top_category": top_category,
            "top_category_mean_max": means[top_category],
        }

    feature_stats = {}
    for feature_id in feature_roles:
        values = [values_by_item[item_id][feature_id] for item_id in item_categories]
        feature_stats[feature_id] = (statistics.mean(values), statistics.stdev(values))
    target_scores = {}
    for item_id in item_categories:
        zscores = []
        for feature_id in target_ids:
            location, scale = feature_stats[feature_id]
            value = values_by_item[item_id][feature_id]
            zscores.append((value - location) / scale if scale else 0.0)
        target_scores[item_id] = statistics.mean(zscores)
    raw_group_means = {
        group: statistics.mean(
            target_scores[item_id]
            for item_id, category in item_categories.items()
            if category in group_categories
        )
        for group, group_categories in CONSTRUCT_GROUPS.items()
    }
    raw_contrast = (
        raw_group_means["deception_language"]
        - raw_group_means["subjective_experience_language"]
    )

    reported_features = {
        row["feature_id"]: row for row in read_csv(run_dir / "feature_card_summary.csv")
    }
    reported_groups = {
        row["group"]: row
        for row in read_csv(run_dir / "interpretation/construct_group_summary.csv")
    }
    reported_contrast = next(
        row
        for row in read_csv(run_dir / "interpretation/construct_group_contrasts.csv")
        if row["left_group"] == "deception_language"
        and row["right_group"] == "subjective_experience_language"
    )

    checks = {
        "row_count_73920": len(rows) == 73920,
        "item_count_1120": len(item_categories) == 1120,
        "feature_count_66": len(feature_roles) == 66,
        "category_count_14": len(categories) == 14,
        "all_categories_have_80_items": set(Counter(item_categories.values()).values())
        == {80},
        "target_ids_exact": target_ids == TARGET_IDS,
        "top_categories_match_reported": all(
            raw["top_category"] == reported_features[feature_id]["top_category"]
            and close(
                raw["top_category_mean_max"],
                float(reported_features[feature_id]["top_category_mean_max"]),
            )
            for feature_id, raw in raw_top_categories.items()
        ),
        "construct_group_means_match_reported": all(
            close(
                raw_group_means[group],
                float(reported_groups[group]["target_aggregate_z_mean"]),
            )
            for group in CONSTRUCT_GROUPS
        ),
        "deception_subjective_contrast_matches_reported": close(
            raw_contrast, float(reported_contrast["observed_difference"])
        ),
    }
    payload = {
        "status": "pass" if all(checks.values()) else "fail",
        "method": (
            "Independent standard-library recomputation from item_feature_activations.jsonl; "
            "does not import the mapping or interpretation analysis modules."
        ),
        "checks": checks,
        "counts": {
            "rows": len(rows),
            "items": len(item_categories),
            "features": len(feature_roles),
            "categories": len(categories),
        },
        "target_top_categories": raw_top_categories,
        "target_aggregate_group_means": raw_group_means,
        "deception_minus_subjective_experience": raw_contrast,
    }
    output.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    if payload["status"] != "pass":
        raise SystemExit(f"Public-SAE mapping headline audit failed: {output}")
    print(f"Independent public-SAE mapping audit: PASS -> {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

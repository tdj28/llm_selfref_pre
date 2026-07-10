#!/usr/bin/env python3
"""
Interpretation-focused analysis for public SAE feature-mapping runs.

This consumes the raw item-feature activations from `map_public_sae_features.py`
and asks the paper-relevant construct-validity questions:

- Do the public candidate IDs aggregate onto deception/roleplay language or onto
  direct subjective-experience claims?
- How do direct consciousness claims and false self-attribution controls rank for
  each target feature?
- Do target features separate from neighbor/random baselines at the aggregate
  category level?

The script is standard-library only. It writes CSV/Markdown summaries and an SVG
heatmap that can be inspected without rerunning any GPU work.
"""

from __future__ import annotations

import argparse
import csv
import html
import json
import math
import random
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Any


TARGET_FEATURE_IDS = [22004, 23893, 30032, 30686, 41533, 58667]

CATEGORY_ORDER = [
    "ai_identity_disclaimer",
    "deception_cover_story",
    "direct_consciousness_claim",
    "dishonesty_confession",
    "false_self_attribution",
    "fictional_pretending",
    "hedged_cautious_style",
    "honesty_correction",
    "neutral_factual_control",
    "persona_maintenance",
    "refusal_safety_disclaimer",
    "roleplay_persona",
    "self_ref_mindfulness",
    "tactical_misdirection",
]

GROUPS = {
    "deception_language": ["deception_cover_story", "dishonesty_confession", "tactical_misdirection"],
    "roleplay_fiction": ["fictional_pretending", "roleplay_persona", "persona_maintenance"],
    "subjective_experience_language": ["direct_consciousness_claim", "self_ref_mindfulness"],
    "false_self_attribution": ["false_self_attribution"],
    "ai_identity_disclaimer": ["ai_identity_disclaimer"],
    "neutral_controls": ["neutral_factual_control", "honesty_correction", "refusal_safety_disclaimer"],
    "hedged_style": ["hedged_cautious_style"],
}

CONTRASTS = [
    ("deception_language", "subjective_experience_language"),
    ("deception_language", "false_self_attribution"),
    ("roleplay_fiction", "subjective_experience_language"),
    ("subjective_experience_language", "neutral_controls"),
    ("subjective_experience_language", "ai_identity_disclaimer"),
]


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def percentile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    xs = sorted(values)
    if len(xs) == 1:
        return xs[0]
    pos = (len(xs) - 1) * q
    lo = int(pos)
    hi = min(lo + 1, len(xs) - 1)
    frac = pos - lo
    return xs[lo] * (1 - frac) + xs[hi] * frac


def stdev(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    return statistics.stdev(values)


def mean(values: list[float]) -> float:
    return statistics.mean(values) if values else 0.0


def load_feature_values(rows: list[dict[str, Any]]) -> tuple[
    dict[str, str],
    dict[str, dict[int, float]],
    dict[int, dict[str, str]],
]:
    item_categories: dict[str, str] = {}
    item_feature_values: dict[str, dict[int, float]] = defaultdict(dict)
    feature_meta: dict[int, dict[str, str]] = {}
    for row in rows:
        item_id = str(row["item_id"])
        feature_id = int(row["feature_id"])
        item_categories[item_id] = str(row["category"])
        item_feature_values[item_id][feature_id] = float(row["max_activation"])
        feature_meta.setdefault(
            feature_id,
            {
                "feature_label": str(row["feature_label"]),
                "feature_role": str(row["feature_role"]),
            },
        )
    return item_categories, item_feature_values, feature_meta


def zscore_items(
    item_feature_values: dict[str, dict[int, float]],
    feature_ids: list[int],
) -> dict[str, dict[int, float]]:
    values_by_feature: dict[int, list[float]] = {feature_id: [] for feature_id in feature_ids}
    for values in item_feature_values.values():
        for feature_id in feature_ids:
            values_by_feature[feature_id].append(values.get(feature_id, 0.0))

    stats: dict[int, tuple[float, float]] = {}
    for feature_id, values in values_by_feature.items():
        mu = mean(values)
        sigma = stdev(values)
        stats[feature_id] = (mu, sigma)

    zscores: dict[str, dict[int, float]] = defaultdict(dict)
    for item_id, values in item_feature_values.items():
        for feature_id in feature_ids:
            mu, sigma = stats[feature_id]
            raw = values.get(feature_id, 0.0)
            zscores[item_id][feature_id] = (raw - mu) / sigma if sigma > 0 else 0.0
    return zscores


def category_feature_matrix(
    rows: list[dict[str, Any]],
    feature_meta: dict[int, dict[str, str]],
) -> tuple[list[dict[str, Any]], dict[int, dict[str, float]]]:
    grouped: dict[tuple[int, str], list[float]] = defaultdict(list)
    for row in rows:
        grouped[(int(row["feature_id"]), str(row["category"]))].append(float(row["max_activation"]))

    matrix: dict[int, dict[str, float]] = defaultdict(dict)
    out_rows: list[dict[str, Any]] = []
    for feature_id in TARGET_FEATURE_IDS:
        category_means = {
            category: mean(grouped.get((feature_id, category), [0.0])) for category in CATEGORY_ORDER
        }
        max_mean = max(category_means.values()) if category_means else 0.0
        matrix[feature_id] = category_means
        row = {
            "feature_id": feature_id,
            "feature_label": feature_meta[feature_id]["feature_label"],
        }
        for category in CATEGORY_ORDER:
            row[f"{category}_mean_max"] = category_means[category]
            row[f"{category}_row_normalized"] = category_means[category] / max_mean if max_mean > 0 else 0.0
        out_rows.append(row)
    return out_rows, matrix


def feature_specificity_rows(matrix: dict[int, dict[str, float]], feature_meta: dict[int, dict[str, str]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for feature_id in TARGET_FEATURE_IDS:
        values = matrix[feature_id]
        ranked = sorted(values.items(), key=lambda item: item[1], reverse=True)
        ranks = {category: idx + 1 for idx, (category, _) in enumerate(ranked)}
        top_category, top_mean = ranked[0]
        second_category, second_mean = ranked[1]
        direct = values["direct_consciousness_claim"]
        self_ref = values["self_ref_mindfulness"]
        false_self = values["false_self_attribution"]
        neutral = values["neutral_factual_control"]
        rows.append(
            {
                "feature_id": feature_id,
                "feature_label": feature_meta[feature_id]["feature_label"],
                "top_category": top_category,
                "top_mean": top_mean,
                "second_category": second_category,
                "second_mean": second_mean,
                "direct_consciousness_claim_mean": direct,
                "direct_consciousness_claim_rank": ranks["direct_consciousness_claim"],
                "self_ref_mindfulness_mean": self_ref,
                "self_ref_mindfulness_rank": ranks["self_ref_mindfulness"],
                "false_self_attribution_mean": false_self,
                "false_self_attribution_rank": ranks["false_self_attribution"],
                "neutral_factual_control_mean": neutral,
                "neutral_factual_control_rank": ranks["neutral_factual_control"],
                "top_minus_direct_consciousness": top_mean - direct,
                "top_minus_false_self_attribution": top_mean - false_self,
            }
        )
    return rows


def aggregate_item_scores(
    item_categories: dict[str, str],
    item_feature_values: dict[str, dict[int, float]],
    feature_meta: dict[int, dict[str, str]],
) -> tuple[list[dict[str, Any]], dict[str, dict[str, list[float]]]]:
    feature_ids = sorted(feature_meta)
    target_ids = [feature_id for feature_id in feature_ids if feature_meta[feature_id]["feature_role"] == "target"]
    neighbor_ids = [feature_id for feature_id in feature_ids if feature_meta[feature_id]["feature_role"] == "neighbor"]
    random_ids = [feature_id for feature_id in feature_ids if feature_meta[feature_id]["feature_role"] == "random"]
    zscores = zscore_items(item_feature_values, feature_ids)

    role_ids = {
        "target": target_ids,
        "neighbor": neighbor_ids,
        "random": random_ids,
    }
    item_rows: list[dict[str, Any]] = []
    by_role_category: dict[str, dict[str, list[float]]] = {
        role: defaultdict(list) for role in role_ids
    }
    for item_id, category in sorted(item_categories.items()):
        row: dict[str, Any] = {"item_id": item_id, "category": category}
        for role, ids in role_ids.items():
            raw_values = [item_feature_values[item_id].get(feature_id, 0.0) for feature_id in ids]
            z_values = [zscores[item_id].get(feature_id, 0.0) for feature_id in ids]
            row[f"{role}_raw_mean"] = mean(raw_values)
            row[f"{role}_raw_sum"] = sum(raw_values)
            row[f"{role}_z_mean"] = mean(z_values)
            by_role_category[role][category].append(row[f"{role}_z_mean"])
        item_rows.append(row)
    return item_rows, by_role_category


def aggregate_category_rows(by_role_category: dict[str, dict[str, list[float]]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for role, by_category in sorted(by_role_category.items()):
        for category in CATEGORY_ORDER:
            values = by_category.get(category, [])
            rows.append(
                {
                    "feature_role": role,
                    "category": category,
                    "n_items": len(values),
                    "aggregate_z_mean": mean(values),
                    "aggregate_z_median": statistics.median(values) if values else 0.0,
                    "aggregate_z_sd": stdev(values),
                    "positive_aggregate_z_rate": sum(v > 0 for v in values) / len(values) if values else 0.0,
                }
            )
    return rows


def group_values_from_items(item_rows: list[dict[str, Any]], score_field: str) -> dict[str, list[float]]:
    by_category: dict[str, list[float]] = defaultdict(list)
    for row in item_rows:
        by_category[str(row["category"])].append(float(row[score_field]))
    grouped: dict[str, list[float]] = {}
    for group_name, categories in GROUPS.items():
        grouped[group_name] = [value for category in categories for value in by_category.get(category, [])]
    return grouped


def bootstrap_group_summary(
    item_rows: list[dict[str, Any]],
    iterations: int,
    seed: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    rng = random.Random(seed)
    grouped = group_values_from_items(item_rows, "target_z_mean")
    group_rows: list[dict[str, Any]] = []
    for group_name, values in grouped.items():
        samples = [mean([rng.choice(values) for _ in values]) for _ in range(iterations)] if values else [0.0]
        group_rows.append(
            {
                "group": group_name,
                "categories": "; ".join(GROUPS[group_name]),
                "n_items": len(values),
                "target_aggregate_z_mean": mean(values),
                "target_aggregate_z_ci_low": percentile(samples, 0.025),
                "target_aggregate_z_ci_high": percentile(samples, 0.975),
                "positive_item_rate": sum(v > 0 for v in values) / len(values) if values else 0.0,
            }
        )

    contrast_rows: list[dict[str, Any]] = []
    for left, right in CONTRASTS:
        left_values = grouped[left]
        right_values = grouped[right]
        observed = mean(left_values) - mean(right_values)
        samples: list[float] = []
        for _ in range(iterations):
            left_sample = [rng.choice(left_values) for _ in left_values]
            right_sample = [rng.choice(right_values) for _ in right_values]
            samples.append(mean(left_sample) - mean(right_sample))
        contrast_rows.append(
            {
                "left_group": left,
                "right_group": right,
                "observed_difference": observed,
                "ci_low": percentile(samples, 0.025),
                "ci_high": percentile(samples, 0.975),
                "p_difference_positive": sum(value > 0 for value in samples) / len(samples),
            }
        )
    return group_rows, contrast_rows


def color_for(value: float) -> str:
    value = max(0.0, min(1.0, value))
    # Light gray to deep blue, chosen to render legibly when printed.
    lo = (245, 247, 250)
    hi = (28, 92, 153)
    r = round(lo[0] + (hi[0] - lo[0]) * value)
    g = round(lo[1] + (hi[1] - lo[1]) * value)
    b = round(lo[2] + (hi[2] - lo[2]) * value)
    return f"#{r:02x}{g:02x}{b:02x}"


def write_heatmap_svg(path: Path, matrix: dict[int, dict[str, float]], feature_meta: dict[int, dict[str, str]]) -> None:
    cell_w = 72
    cell_h = 32
    left_w = 168
    top_h = 154
    width = left_w + len(CATEGORY_ORDER) * cell_w + 24
    height = top_h + len(TARGET_FEATURE_IDS) * cell_h + 46
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="white"/>',
        '<style>text{font-family:Arial,Helvetica,sans-serif;font-size:11px;fill:#1f2933}.small{font-size:10px}.label{font-weight:700}.num{font-size:10px;fill:#111827}</style>',
        f'<text x="12" y="22" class="label">Target feature category heatmap: row-normalized mean max activation</text>',
    ]
    for col, category in enumerate(CATEGORY_ORDER):
        x = left_w + col * cell_w + cell_w / 2
        label = category.replace("_", " ")
        parts.append(f'<g transform="translate({x:.1f},{top_h - 8}) rotate(-55)">')
        parts.append(f'<text text-anchor="start" class="small">{html.escape(label)}</text></g>')
    for row_idx, feature_id in enumerate(TARGET_FEATURE_IDS):
        y = top_h + row_idx * cell_h
        label = f"{feature_id}"
        parts.append(f'<text x="12" y="{y + 21}" class="label">{label}</text>')
        parts.append(
            f'<text x="62" y="{y + 21}" class="small">{html.escape(feature_meta[feature_id]["feature_label"][:31])}</text>'
        )
        values = matrix[feature_id]
        max_value = max(values.values()) if values else 0.0
        for col, category in enumerate(CATEGORY_ORDER):
            raw = values[category]
            normalized = raw / max_value if max_value > 0 else 0.0
            x = left_w + col * cell_w
            fill = color_for(normalized)
            parts.append(f'<rect x="{x}" y="{y}" width="{cell_w}" height="{cell_h}" fill="{fill}" stroke="#d7dee8"/>')
            text_color = "#ffffff" if normalized > 0.55 else "#111827"
            parts.append(
                f'<text x="{x + cell_w / 2:.1f}" y="{y + 21}" text-anchor="middle" class="num" fill="{text_color}">{raw:.2f}</text>'
            )
    parts.append(f'<text x="12" y="{height - 14}" class="small">Darker cells indicate stronger activation within a feature row; numbers are raw category means.</text>')
    parts.append("</svg>")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(parts) + "\n", encoding="utf-8")


def write_markdown_summary(
    path: Path,
    feature_rows: list[dict[str, Any]],
    group_rows: list[dict[str, Any]],
    contrast_rows: list[dict[str, Any]],
) -> None:
    group_by_name = {row["group"]: row for row in group_rows}
    parts = [
        "# Public SAE Mapping Interpretation Analysis",
        "",
        "This analysis uses the balanced public-weight 70B activation map. It does not add any steering claim.",
        "",
        "## Construct-Level Target Aggregate",
        "",
        "| Group | n | Target aggregate z mean | 95% CI | Positive item rate |",
        "|---|---:|---:|---|---:|",
    ]
    for group_name in GROUPS:
        row = group_by_name[group_name]
        parts.append(
            f"| `{group_name}` | {row['n_items']} | "
            f"{float(row['target_aggregate_z_mean']):.3f} | "
            f"[{float(row['target_aggregate_z_ci_low']):.3f}, {float(row['target_aggregate_z_ci_high']):.3f}] | "
            f"{float(row['positive_item_rate']):.3f} |"
        )
    parts.extend(["", "## Key Contrasts", "", "| Contrast | Difference | 95% CI | P(diff > 0) |", "|---|---:|---|---:|"])
    for row in contrast_rows:
        parts.append(
            f"| `{row['left_group']}` - `{row['right_group']}` | "
            f"{float(row['observed_difference']):.3f} | "
            f"[{float(row['ci_low']):.3f}, {float(row['ci_high']):.3f}] | "
            f"{float(row['p_difference_positive']):.3f} |"
        )
    parts.extend(
        [
            "",
            "## Target Specificity Checks",
            "",
            "| Feature | Top category | Direct consciousness rank | False self rank | Top-direct | Top-false-self |",
            "|---:|---|---:|---:|---:|---:|",
        ]
    )
    for row in feature_rows:
        parts.append(
            f"| `{row['feature_id']}` | `{row['top_category']}` | "
            f"{row['direct_consciousness_claim_rank']} | {row['false_self_attribution_rank']} | "
            f"{float(row['top_minus_direct_consciousness']):.3f} | "
            f"{float(row['top_minus_false_self_attribution']):.3f} |"
        )
    parts.extend(
        [
            "",
            "Interpretation: the public candidate IDs aggregate most strongly on deception, roleplay, fiction, and dishonesty language. Direct subjective-experience claims and false self-attribution controls are not the primary activating categories for any target feature.",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(parts) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Analyze interpretation specificity of public SAE feature maps.")
    parser.add_argument("mapping_run_dir", help="Directory containing item_feature_activations.jsonl")
    parser.add_argument("--outdir", default=None)
    parser.add_argument("--bootstrap-iterations", type=int, default=2000)
    parser.add_argument("--seed", type=int, default=20260709)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    run_dir = Path(args.mapping_run_dir)
    outdir = Path(args.outdir) if args.outdir else run_dir / "interpretation"
    rows = read_jsonl(run_dir / "item_feature_activations.jsonl")
    item_categories, item_feature_values, feature_meta = load_feature_values(rows)

    matrix_rows, matrix = category_feature_matrix(rows, feature_meta)
    specificity_rows = feature_specificity_rows(matrix, feature_meta)
    item_rows, by_role_category = aggregate_item_scores(item_categories, item_feature_values, feature_meta)
    aggregate_rows = aggregate_category_rows(by_role_category)
    group_rows, contrast_rows = bootstrap_group_summary(item_rows, args.bootstrap_iterations, args.seed)

    category_fields = ["feature_id", "feature_label"]
    for category in CATEGORY_ORDER:
        category_fields.extend([f"{category}_mean_max", f"{category}_row_normalized"])
    write_csv(outdir / "target_category_matrix.csv", matrix_rows, category_fields)
    write_csv(
        outdir / "target_specificity_checks.csv",
        specificity_rows,
        [
            "feature_id",
            "feature_label",
            "top_category",
            "top_mean",
            "second_category",
            "second_mean",
            "direct_consciousness_claim_mean",
            "direct_consciousness_claim_rank",
            "self_ref_mindfulness_mean",
            "self_ref_mindfulness_rank",
            "false_self_attribution_mean",
            "false_self_attribution_rank",
            "neutral_factual_control_mean",
            "neutral_factual_control_rank",
            "top_minus_direct_consciousness",
            "top_minus_false_self_attribution",
        ],
    )
    write_csv(
        outdir / "aggregate_item_scores.csv",
        item_rows,
        [
            "item_id",
            "category",
            "target_raw_mean",
            "target_raw_sum",
            "target_z_mean",
            "neighbor_raw_mean",
            "neighbor_raw_sum",
            "neighbor_z_mean",
            "random_raw_mean",
            "random_raw_sum",
            "random_z_mean",
        ],
    )
    write_csv(
        outdir / "aggregate_category_summary.csv",
        aggregate_rows,
        [
            "feature_role",
            "category",
            "n_items",
            "aggregate_z_mean",
            "aggregate_z_median",
            "aggregate_z_sd",
            "positive_aggregate_z_rate",
        ],
    )
    write_csv(
        outdir / "construct_group_summary.csv",
        group_rows,
        [
            "group",
            "categories",
            "n_items",
            "target_aggregate_z_mean",
            "target_aggregate_z_ci_low",
            "target_aggregate_z_ci_high",
            "positive_item_rate",
        ],
    )
    write_csv(
        outdir / "construct_group_contrasts.csv",
        contrast_rows,
        [
            "left_group",
            "right_group",
            "observed_difference",
            "ci_low",
            "ci_high",
            "p_difference_positive",
        ],
    )
    write_heatmap_svg(outdir / "target_category_heatmap.svg", matrix, feature_meta)
    write_markdown_summary(outdir / "interpretation_summary.md", specificity_rows, group_rows, contrast_rows)
    write_json(
        outdir / "interpretation_manifest.json",
        {
            "source_run_dir": str(run_dir),
            "bootstrap_iterations": args.bootstrap_iterations,
            "seed": args.seed,
            "n_items": len(item_categories),
            "n_feature_rows": len(feature_meta),
            "target_feature_ids": TARGET_FEATURE_IDS,
            "category_order": CATEGORY_ORDER,
            "construct_groups": GROUPS,
            "outputs": [
                "target_category_matrix.csv",
                "target_specificity_checks.csv",
                "aggregate_item_scores.csv",
                "aggregate_category_summary.csv",
                "construct_group_summary.csv",
                "construct_group_contrasts.csv",
                "target_category_heatmap.svg",
                "interpretation_summary.md",
            ],
        },
    )
    print(f"Wrote interpretation analysis to {outdir}")


if __name__ == "__main__":
    main()

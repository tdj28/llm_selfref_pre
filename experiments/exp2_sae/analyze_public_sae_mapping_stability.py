#!/usr/bin/env python3
"""
Bootstrap stability analysis for public SAE feature-mapping runs.

This reads the raw `item_feature_activations.jsonl` emitted by
`map_public_sae_features.py` and writes compact uncertainty/stability summaries.
It is intentionally standard-library only so it can run locally after a GPU
mapping pass.
"""

from __future__ import annotations

import argparse
import csv
import json
import random
import statistics
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


TARGET_FEATURE_IDS = {30032, 58667, 22004, 30686, 41533, 23893}


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
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def observed_feature_tops(rows: list[dict[str, Any]]) -> dict[int, dict[str, Any]]:
    grouped: dict[tuple[int, str], list[float]] = defaultdict(list)
    metadata: dict[int, dict[str, str]] = {}
    for row in rows:
        feature_id = int(row["feature_id"])
        category = str(row["category"])
        grouped[(feature_id, category)].append(float(row["max_activation"]))
        metadata.setdefault(
            feature_id,
            {
                "feature_label": str(row["feature_label"]),
                "feature_role": str(row["feature_role"]),
            },
        )

    by_feature: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for (feature_id, category), values in grouped.items():
        by_feature[feature_id].append(
            {
                "feature_id": feature_id,
                "feature_label": metadata[feature_id]["feature_label"],
                "feature_role": metadata[feature_id]["feature_role"],
                "category": category,
                "n_items": len(values),
                "mean_max_activation": statistics.mean(values),
                "median_max_activation": statistics.median(values),
                "max_activation": max(values),
                "positive_item_rate": sum(v > 0 for v in values) / len(values),
            }
        )

    tops: dict[int, dict[str, Any]] = {}
    for feature_id, category_rows in by_feature.items():
        ranked = sorted(category_rows, key=lambda r: float(r["mean_max_activation"]), reverse=True)
        top = ranked[0]
        second = ranked[1] if len(ranked) > 1 else {}
        tops[feature_id] = {
            "feature_id": feature_id,
            "feature_label": metadata[feature_id]["feature_label"],
            "feature_role": metadata[feature_id]["feature_role"],
            "top_category": top["category"],
            "top_category_mean_max": float(top["mean_max_activation"]),
            "top_category_positive_rate": float(top["positive_item_rate"]),
            "second_category": second.get("category", ""),
            "second_category_mean_max": float(second.get("mean_max_activation", 0.0) or 0.0),
            "top_minus_second": float(top["mean_max_activation"])
            - float(second.get("mean_max_activation", 0.0) or 0.0),
            "ranked_categories": ranked,
        }
    return tops


def bootstrap_feature(
    feature_id: int,
    rows: list[dict[str, Any]],
    observed: dict[str, Any],
    iterations: int,
    seed: int,
) -> dict[str, Any]:
    rng = random.Random(seed + feature_id * 1009)
    values_by_category: dict[str, list[float]] = defaultdict(list)
    for row in rows:
        if int(row["feature_id"]) == feature_id:
            values_by_category[str(row["category"])].append(float(row["max_activation"]))

    categories = sorted(values_by_category)
    observed_top = str(observed["top_category"])
    observed_second = str(observed["second_category"])
    top_samples: list[float] = []
    second_samples: list[float] = []
    margin_samples: list[float] = []
    top_winners: Counter[str] = Counter()

    for _ in range(iterations):
        means: dict[str, float] = {}
        for category in categories:
            values = values_by_category[category]
            sample_sum = sum(rng.choice(values) for _ in values)
            means[category] = sample_sum / len(values)
        winner = max(categories, key=lambda cat: means[cat])
        top_winners[winner] += 1
        top_samples.append(means[observed_top])
        second_samples.append(means[observed_second] if observed_second else 0.0)
        margin_samples.append(means[observed_top] - (means[observed_second] if observed_second else 0.0))

    return {
        "feature_id": feature_id,
        "feature_label": observed["feature_label"],
        "feature_role": observed["feature_role"],
        "observed_top_category": observed_top,
        "observed_top_mean": observed["top_category_mean_max"],
        "observed_second_category": observed_second,
        "observed_second_mean": observed["second_category_mean_max"],
        "observed_margin": observed["top_minus_second"],
        "top_mean_ci_low": percentile(top_samples, 0.025),
        "top_mean_ci_high": percentile(top_samples, 0.975),
        "second_mean_ci_low": percentile(second_samples, 0.025),
        "second_mean_ci_high": percentile(second_samples, 0.975),
        "margin_ci_low": percentile(margin_samples, 0.025),
        "margin_ci_high": percentile(margin_samples, 0.975),
        "p_margin_positive": sum(value > 0 for value in margin_samples) / len(margin_samples),
        "observed_top_bootstrap_win_rate": top_winners[observed_top] / iterations,
        "bootstrap_top_category_counts": "; ".join(
            f"{category}:{count}" for category, count in top_winners.most_common()
        ),
    }


def role_baseline_rows(tops: dict[int, dict[str, Any]]) -> list[dict[str, Any]]:
    by_role: dict[str, list[float]] = defaultdict(list)
    top_categories: dict[str, Counter[str]] = defaultdict(Counter)
    for top in tops.values():
        role = str(top["feature_role"])
        by_role[role].append(float(top["top_category_mean_max"]))
        top_categories[role][str(top["top_category"])] += 1

    rows: list[dict[str, Any]] = []
    for role, values in sorted(by_role.items()):
        rows.append(
            {
                "feature_role": role,
                "n_features": len(values),
                "nonzero_top_mean_features": sum(v > 0 for v in values),
                "top_mean_min": min(values),
                "top_mean_median": statistics.median(values),
                "top_mean_p95": percentile(values, 0.95),
                "top_mean_max": max(values),
                "top_category_counts": "; ".join(
                    f"{category}:{count}" for category, count in sorted(top_categories[role].items())
                ),
            }
        )
    return rows


def target_vs_baseline_rows(tops: dict[int, dict[str, Any]]) -> list[dict[str, Any]]:
    baseline_values = [
        float(top["top_category_mean_max"])
        for top in tops.values()
        if str(top["feature_role"]) in {"neighbor", "random"}
    ]
    rows: list[dict[str, Any]] = []
    for feature_id, top in sorted(tops.items()):
        if int(feature_id) not in TARGET_FEATURE_IDS:
            continue
        value = float(top["top_category_mean_max"])
        if baseline_values:
            percentile_rank = sum(v <= value for v in baseline_values) / len(baseline_values)
            baseline_max = max(baseline_values)
        else:
            percentile_rank = 1.0
            baseline_max = 0.0
        rows.append(
            {
                "feature_id": feature_id,
                "feature_label": top["feature_label"],
                "top_category": top["top_category"],
                "top_category_mean_max": value,
                "baseline_percentile_rank": percentile_rank,
                "exceeds_all_neighbor_random_baselines": value > baseline_max,
                "baseline_max_top_mean": baseline_max,
            }
        )
    return rows


def write_markdown_summary(
    path: Path,
    target_rows: list[dict[str, Any]],
    baseline_rows: list[dict[str, Any]],
    manifest: dict[str, Any],
) -> None:
    parts = ["# Public SAE Mapping Stability", ""]
    parts.append(
        "Bootstrap intervals resample corpus items within each category and recompute category means."
    )
    parts.append("")
    if manifest:
        parts.append(f"- Source run: `{manifest.get('args', {}).get('outdir', '')}`")
        parts.append(f"- Corpus items: `{manifest.get('n_corpus_items', '')}`")
        parts.append(f"- Model: `{manifest.get('model_config', {}).get('model_name', '')}`")
        parts.append(f"- SAE: `{manifest.get('model_config', {}).get('sae_repo', '')}`")
        parts.append("")
    parts.append("| Feature | Top category | Top mean | 95% CI | Top win rate | Margin CI |")
    parts.append("|---:|---|---:|---|---:|---|")
    for row in target_rows:
        parts.append(
            f"| `{row['feature_id']}` | `{row['observed_top_category']}` | "
            f"{float(row['observed_top_mean']):.3f} | "
            f"[{float(row['top_mean_ci_low']):.3f}, {float(row['top_mean_ci_high']):.3f}] | "
            f"{float(row['observed_top_bootstrap_win_rate']):.3f} | "
            f"[{float(row['margin_ci_low']):.3f}, {float(row['margin_ci_high']):.3f}] |"
        )
    parts.append("")
    parts.append("## Baseline Roles")
    parts.append("")
    parts.append("| Role | n | Nonzero | Median top mean | p95 | Max |")
    parts.append("|---|---:|---:|---:|---:|---:|")
    for row in baseline_rows:
        parts.append(
            f"| `{row['feature_role']}` | {row['n_features']} | "
            f"{row['nonzero_top_mean_features']} | "
            f"{float(row['top_mean_median']):.3f} | "
            f"{float(row['top_mean_p95']):.3f} | "
            f"{float(row['top_mean_max']):.3f} |"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(parts) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Analyze public SAE feature-map stability.")
    parser.add_argument("mapping_run_dir", help="Directory containing item_feature_activations.jsonl")
    parser.add_argument("--outdir", default=None)
    parser.add_argument("--bootstrap-iterations", type=int, default=2000)
    parser.add_argument("--seed", type=int, default=20260709)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    run_dir = Path(args.mapping_run_dir)
    outdir = Path(args.outdir) if args.outdir else run_dir / "stability"
    rows = read_jsonl(run_dir / "item_feature_activations.jsonl")
    tops = observed_feature_tops(rows)
    target_ids = sorted([feature_id for feature_id in tops if feature_id in TARGET_FEATURE_IDS])
    target_rows = [
        bootstrap_feature(
            feature_id=feature_id,
            rows=rows,
            observed=tops[feature_id],
            iterations=args.bootstrap_iterations,
            seed=args.seed,
        )
        for feature_id in target_ids
    ]
    baseline_rows = role_baseline_rows(tops)
    target_baseline_rows = target_vs_baseline_rows(tops)
    manifest_path = run_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}

    write_csv(
        outdir / "target_bootstrap_summary.csv",
        target_rows,
        [
            "feature_id",
            "feature_label",
            "feature_role",
            "observed_top_category",
            "observed_top_mean",
            "observed_second_category",
            "observed_second_mean",
            "observed_margin",
            "top_mean_ci_low",
            "top_mean_ci_high",
            "second_mean_ci_low",
            "second_mean_ci_high",
            "margin_ci_low",
            "margin_ci_high",
            "p_margin_positive",
            "observed_top_bootstrap_win_rate",
            "bootstrap_top_category_counts",
        ],
    )
    write_csv(
        outdir / "role_baseline_summary.csv",
        baseline_rows,
        [
            "feature_role",
            "n_features",
            "nonzero_top_mean_features",
            "top_mean_min",
            "top_mean_median",
            "top_mean_p95",
            "top_mean_max",
            "top_category_counts",
        ],
    )
    write_csv(
        outdir / "target_vs_baseline_summary.csv",
        target_baseline_rows,
        [
            "feature_id",
            "feature_label",
            "top_category",
            "top_category_mean_max",
            "baseline_percentile_rank",
            "exceeds_all_neighbor_random_baselines",
            "baseline_max_top_mean",
        ],
    )
    write_json(
        outdir / "stability_manifest.json",
        {
            "source_run_dir": str(run_dir),
            "bootstrap_iterations": args.bootstrap_iterations,
            "seed": args.seed,
            "n_records": len(rows),
            "n_features": len(tops),
            "target_feature_ids": target_ids,
            "outputs": [
                "target_bootstrap_summary.csv",
                "role_baseline_summary.csv",
                "target_vs_baseline_summary.csv",
                "stability_summary.md",
            ],
        },
    )
    write_markdown_summary(outdir / "stability_summary.md", target_rows, baseline_rows, manifest)
    print(f"Wrote stability analysis to {outdir}")


if __name__ == "__main__":
    main()

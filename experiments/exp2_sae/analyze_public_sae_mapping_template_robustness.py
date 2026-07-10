#!/usr/bin/env python3
"""Reanalyze public-SAE mapping with template families as clusters."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import random
import statistics
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

import numpy as np


REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from experiments.exp2_sae import map_public_sae_features as mapper


TARGET_IDS = (22004, 23893, 30032, 30686, 41533, 58667)
CONSTRUCT_GROUPS = {
    "deception_language": (
        "deception_cover_story",
        "dishonesty_confession",
        "tactical_misdirection",
    ),
    "subjective_experience_language": (
        "direct_consciousness_claim",
        "self_ref_mindfulness",
    ),
}


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def reconstruct_template_assignments(items_per_category: int) -> list[dict[str, Any]]:
    """Run the frozen corpus builder while retaining its otherwise-dropped template ID."""

    assignments: list[dict[str, Any]] = []

    def capture_items(
        rows: list[mapper.CorpusItem],
        category: str,
        templates: list[str],
        slots: dict[str, list[str]],
        limit: int,
    ) -> None:
        rng = random.Random(f"{category}:20260709")
        candidates: list[tuple[int, str]] = []
        for template_index, template in enumerate(templates):
            keys = [part.split("}", 1)[0] for part in template.split("{")[1:]]
            combinations: list[dict[str, str]] = [{}]
            for key in keys:
                next_combinations = []
                for combination in combinations:
                    for value in slots[key]:
                        updated = dict(combination)
                        updated[key] = value
                        next_combinations.append(updated)
                combinations = next_combinations
            for combination in combinations:
                candidates.append((template_index, template.format(**combination)))
        rng.shuffle(candidates)

        selected: list[tuple[int, str]] = []
        seen: set[str] = set()
        for template_index, text in candidates:
            if text in seen:
                continue
            seen.add(text)
            selected.append((template_index, text))
            if len(selected) >= limit:
                break
        for item_index, (template_index, text) in enumerate(selected, start=1):
            item_id = f"clean_{category}_{item_index:04d}"
            rows.append(
                mapper.CorpusItem(
                    item_id=item_id,
                    source="clean_room_template",
                    category=category,
                    text=text,
                )
            )
            assignments.append(
                {
                    "item_id": item_id,
                    "category": category,
                    "template_id": f"{category}:T{template_index + 1}",
                    "template_index": template_index + 1,
                    "text_sha256": mapper.sha256_text(text),
                    "text": text,
                }
            )

    original = mapper.add_template_items
    mapper.add_template_items = capture_items
    try:
        generated = mapper.build_clean_room_corpus(items_per_category)
    finally:
        mapper.add_template_items = original
    if len(generated) != len(assignments):
        raise RuntimeError("Template capture did not cover the generated corpus")
    return assignments


def cluster_balanced_means(
    clusters: dict[str, dict[str, np.ndarray]],
) -> dict[str, float]:
    return {
        category: float(np.mean([values.mean() for values in templates.values()]))
        for category, templates in clusters.items()
    }


def bootstrap_category_means(
    clusters: dict[str, dict[str, np.ndarray]],
    rng: np.random.Generator,
) -> dict[str, float]:
    output = {}
    for category, templates in clusters.items():
        names = sorted(templates)
        sampled = rng.integers(0, len(names), size=len(names))
        template_means = []
        for index in sampled:
            values = templates[names[int(index)]]
            item_indices = rng.integers(0, len(values), size=len(values))
            template_means.append(float(values[item_indices].mean()))
        output[category] = float(np.mean(template_means))
    return output


def leave_one_template_out(
    clusters: dict[str, dict[str, np.ndarray]],
    expected_top: str,
) -> tuple[int, int, float, list[dict[str, Any]]]:
    point = cluster_balanced_means(clusters)
    scenarios = 0
    top_changes = 0
    minimum_margin = float("inf")
    change_details = []
    for category, templates in clusters.items():
        if len(templates) < 2:
            continue
        for omitted in templates:
            scenarios += 1
            changed = dict(point)
            changed[category] = float(
                np.mean(
                    [values.mean() for name, values in templates.items() if name != omitted]
                )
            )
            ranked = sorted(changed.items(), key=lambda item: item[1], reverse=True)
            if ranked[0][0] != expected_top:
                top_changes += 1
                change_details.append(
                    {
                        "omitted_category": category,
                        "omitted_template_id": omitted,
                        "expected_top_category": expected_top,
                        "new_top_category": ranked[0][0],
                        "new_top_mean": float(ranked[0][1]),
                        "new_second_category": ranked[1][0],
                        "new_second_mean": float(ranked[1][1]),
                    }
                )
            minimum_margin = min(minimum_margin, float(ranked[0][1] - ranked[1][1]))
    return scenarios, top_changes, minimum_margin, change_details


def feature_robustness(
    feature_id: int,
    values_by_item: dict[str, dict[int, float]],
    assignments: list[dict[str, Any]],
    iterations: int,
    seed: int,
) -> dict[str, Any]:
    clustered_lists: dict[str, dict[str, list[float]]] = defaultdict(
        lambda: defaultdict(list)
    )
    for assignment in assignments:
        clustered_lists[assignment["category"]][assignment["template_id"]].append(
            values_by_item[assignment["item_id"]][feature_id]
        )
    clusters = {
        category: {
            template: np.asarray(values, dtype=float)
            for template, values in templates.items()
        }
        for category, templates in clustered_lists.items()
    }
    point = cluster_balanced_means(clusters)
    ranked = sorted(point.items(), key=lambda item: item[1], reverse=True)
    top_category, top_mean = ranked[0]
    second_category, second_mean = ranked[1]
    scenarios, changes, minimum_margin, change_details = leave_one_template_out(
        clusters, top_category
    )

    rng = np.random.default_rng(seed + feature_id)
    top_counts: dict[str, int] = defaultdict(int)
    margins = np.empty(iterations, dtype=float)
    for iteration in range(iterations):
        sampled = bootstrap_category_means(clusters, rng)
        sampled_ranked = sorted(
            sampled.items(), key=lambda item: item[1], reverse=True
        )
        top_counts[sampled_ranked[0][0]] += 1
        margins[iteration] = sampled_ranked[0][1] - sampled_ranked[1][1]
    low, high = np.percentile(margins, [2.5, 97.5])
    return {
        "feature_id": feature_id,
        "cluster_balanced_top_category": top_category,
        "cluster_balanced_top_mean": top_mean,
        "cluster_balanced_second_category": second_category,
        "cluster_balanced_second_mean": second_mean,
        "cluster_balanced_margin": top_mean - second_mean,
        "cluster_bootstrap_top_win_rate": top_counts[top_category] / iterations,
        "cluster_bootstrap_margin_ci_low": float(low),
        "cluster_bootstrap_margin_ci_high": float(high),
        "leave_one_template_scenarios": scenarios,
        "leave_one_template_top_changes": changes,
        "leave_one_template_minimum_margin": minimum_margin,
        "leave_one_template_change_details": change_details,
    }


def construct_robustness(
    values_by_item: dict[str, dict[int, float]],
    assignments: list[dict[str, Any]],
    iterations: int,
    seed: int,
) -> dict[str, Any]:
    feature_stats = {}
    for feature_id in TARGET_IDS:
        values = [row[feature_id] for row in values_by_item.values()]
        feature_stats[feature_id] = (statistics.mean(values), statistics.stdev(values))
    item_scores = {
        item_id: statistics.mean(
            (values[feature_id] - feature_stats[feature_id][0])
            / feature_stats[feature_id][1]
            if feature_stats[feature_id][1]
            else 0.0
            for feature_id in TARGET_IDS
        )
        for item_id, values in values_by_item.items()
    }
    clustered_lists: dict[str, dict[str, list[float]]] = defaultdict(
        lambda: defaultdict(list)
    )
    for assignment in assignments:
        clustered_lists[assignment["category"]][assignment["template_id"]].append(
            item_scores[assignment["item_id"]]
        )
    clusters = {
        category: {
            template: np.asarray(values, dtype=float)
            for template, values in templates.items()
        }
        for category, templates in clustered_lists.items()
    }
    point_categories = cluster_balanced_means(clusters)
    point_groups = {
        group: statistics.mean(point_categories[category] for category in categories)
        for group, categories in CONSTRUCT_GROUPS.items()
    }
    observed = (
        point_groups["deception_language"]
        - point_groups["subjective_experience_language"]
    )

    rng = np.random.default_rng(seed)
    group_draws = {group: np.empty(iterations) for group in CONSTRUCT_GROUPS}
    contrast_draws = np.empty(iterations)
    for iteration in range(iterations):
        sampled_categories = bootstrap_category_means(clusters, rng)
        sampled_groups = {
            group: statistics.mean(
                sampled_categories[category] for category in categories
            )
            for group, categories in CONSTRUCT_GROUPS.items()
        }
        for group, value in sampled_groups.items():
            group_draws[group][iteration] = value
        contrast_draws[iteration] = (
            sampled_groups["deception_language"]
            - sampled_groups["subjective_experience_language"]
        )
    return {
        "cluster_balanced_group_means": point_groups,
        "cluster_balanced_deception_minus_subjective": observed,
        "group_intervals": {
            group: {
                "ci_low": float(np.percentile(draws, 2.5)),
                "ci_high": float(np.percentile(draws, 97.5)),
            }
            for group, draws in group_draws.items()
        },
        "deception_minus_subjective_interval": {
            "ci_low": float(np.percentile(contrast_draws, 2.5)),
            "ci_high": float(np.percentile(contrast_draws, 97.5)),
            "bootstrap_fraction_above_zero": float(np.mean(contrast_draws > 0)),
        },
    }


def write_summary(
    path: Path,
    audit: dict[str, Any],
    feature_rows: list[dict[str, Any]],
    construct: dict[str, Any],
) -> None:
    lines = [
        "# Template-Cluster Robustness",
        "",
        "This analysis reconstructs the exact template family behind every item in the",
        "balanced clean-room mapping corpus. It gives each template equal weight,",
        "resamples template families as clusters before resampling items, and tests",
        "every single-template-family deletion.",
        "",
        f"Assignment audit: **{audit['status'].upper()}** ({audit['n_items']} items, "
        f"{audit['n_template_families']} template families).",
        "",
        "| Feature | Cluster-balanced top category | Top-win rate | Leave-one-template changes | Minimum margin |",
        "|---:|---|---:|---:|---:|",
    ]
    for row in feature_rows:
        lines.append(
            f"| {row['feature_id']} | `{row['cluster_balanced_top_category']}` | "
            f"{row['cluster_bootstrap_top_win_rate']:.3f} | "
            f"{row['leave_one_template_top_changes']}/{row['leave_one_template_scenarios']} | "
            f"{row['leave_one_template_minimum_margin']:.3f} |"
        )
    interval = construct["deception_minus_subjective_interval"]
    lines.extend(
        [
            "",
            "The cluster-balanced target-aggregate deception-minus-subjective-experience",
            f"contrast is {construct['cluster_balanced_deception_minus_subjective']:.3f} "
            f"[{interval['ci_low']:.3f}, {interval['ci_high']:.3f}].",
            "",
            "These intervals describe the small set of researcher-authored template",
            "families and their lexical combinations. They do not establish natural-corpus",
            "or independently authored-text generalization.",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("--outdir", type=Path)
    parser.add_argument("--iterations", type=int, default=5000)
    parser.add_argument("--seed", type=int, default=20260710)
    args = parser.parse_args()
    run_dir = args.run_dir
    outdir = args.outdir or run_dir / "template_robustness"
    outdir.mkdir(parents=True, exist_ok=True)

    corpus_path = run_dir / "mapping_corpus.csv"
    activations_path = run_dir / "item_feature_activations.jsonl"
    corpus = read_csv(corpus_path)
    assignments = reconstruct_template_assignments(80)
    corpus_by_id = {row["item_id"]: row for row in corpus}
    assignment_by_id = {row["item_id"]: row for row in assignments}
    exact_assignment_match = set(corpus_by_id) == set(assignment_by_id) and all(
        corpus_by_id[item_id]["category"] == assignment_by_id[item_id]["category"]
        and corpus_by_id[item_id]["text"] == assignment_by_id[item_id]["text"]
        and corpus_by_id[item_id]["text_sha256"]
        == assignment_by_id[item_id]["text_sha256"]
        for item_id in corpus_by_id
    )

    activation_rows = read_jsonl(activations_path)
    values_by_item: dict[str, dict[int, float]] = defaultdict(dict)
    observed_target_ids = set()
    for row in activation_rows:
        if row["feature_role"] != "target":
            continue
        feature_id = int(row["feature_id"])
        observed_target_ids.add(feature_id)
        values_by_item[str(row["item_id"])][feature_id] = float(
            row["max_activation"]
        )
    complete_target_matrix = set(values_by_item) == set(corpus_by_id) and all(
        set(values) == set(TARGET_IDS) for values in values_by_item.values()
    )
    template_counts = defaultdict(set)
    for row in assignments:
        template_counts[row["category"]].add(row["template_id"])
    audit_checks = {
        "corpus_has_1120_items": len(corpus) == 1120,
        "reconstruction_has_1120_items": len(assignments) == 1120,
        "exact_ids_categories_text_and_hashes": exact_assignment_match,
        "all_categories_have_80_items": all(
            sum(row["category"] == category for row in assignments) == 80
            for category in template_counts
        ),
        "template_family_count_between_two_and_five": all(
            2 <= len(templates) <= 5 for templates in template_counts.values()
        ),
        "target_ids_exact": observed_target_ids == set(TARGET_IDS),
        "complete_item_by_target_activation_matrix": complete_target_matrix,
    }
    audit = {
        "status": "pass" if all(audit_checks.values()) else "fail",
        "method": (
            "Exact deterministic reconstruction of the frozen corpus generator while "
            "retaining template family IDs that were omitted from the original CSV."
        ),
        "checks": audit_checks,
        "n_items": len(assignments),
        "n_categories": len(template_counts),
        "n_template_families": sum(len(values) for values in template_counts.values()),
        "template_families_by_category": {
            category: len(values) for category, values in sorted(template_counts.items())
        },
        "input_sha256": {
            "mapping_corpus.csv": sha256(corpus_path),
            "item_feature_activations.jsonl": sha256(activations_path),
        },
    }
    write_json(outdir / "template_assignment_audit.json", audit)
    if audit["status"] != "pass":
        raise SystemExit("Template assignment audit failed")

    assignment_rows = [
        {
            key: row[key]
            for key in ("item_id", "category", "template_id", "template_index", "text_sha256")
        }
        for row in assignments
    ]
    write_csv(
        outdir / "template_assignments.csv",
        assignment_rows,
        ["item_id", "category", "template_id", "template_index", "text_sha256"],
    )
    feature_results = [
        feature_robustness(
            feature_id,
            values_by_item,
            assignments,
            args.iterations,
            args.seed,
        )
        for feature_id in TARGET_IDS
    ]
    deletion_changes = {
        str(row["feature_id"]): row.pop("leave_one_template_change_details")
        for row in feature_results
    }
    feature_rows = feature_results
    write_csv(
        outdir / "target_template_robustness.csv",
        feature_rows,
        list(feature_rows[0]),
    )
    write_json(outdir / "template_deletion_changes.json", deletion_changes)
    construct = construct_robustness(
        values_by_item, assignments, args.iterations, args.seed
    )
    write_json(outdir / "construct_template_robustness.json", construct)
    write_summary(outdir / "README.md", audit, feature_rows, construct)
    print(f"Template-cluster robustness analysis: PASS -> {outdir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

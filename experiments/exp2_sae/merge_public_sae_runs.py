#!/usr/bin/env python3
"""Merge disjoint public-SAE base and adaptive-extension runs for analysis."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import shutil
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True) + "\n")


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def assert_compatible(base: dict[str, Any], extension: dict[str, Any]) -> None:
    fields = (
        "model",
        "sae",
        "protocol_version",
        "induction_max_tokens",
        "final_max_tokens",
        "steering_values",
        "conditions",
        "queries",
        "n_feature_sets",
    )
    mismatches = {field: (base.get(field), extension.get(field)) for field in fields if base.get(field) != extension.get(field)}
    if mismatches:
        raise ValueError(f"Run manifests are incompatible: {mismatches}")


def validate_component(
    name: str,
    manifest: dict[str, Any],
    results: list[dict[str, Any]],
    judgments: list[dict[str, Any]],
    plans: list[dict[str, str]],
) -> set[str]:
    expected_trials = int(manifest["n_trials_planned"])
    if len(results) != expected_trials:
        raise ValueError(
            f"{name} result count differs from manifest: "
            f"{len(results)} != {expected_trials}"
        )
    trial_ids = [row["trial_id"] for row in results]
    if len(trial_ids) != len(set(trial_ids)):
        raise ValueError(f"{name} contains duplicate trial IDs")
    plan_ids = [row["trial_id"] for row in plans]
    if len(plan_ids) != expected_trials or len(plan_ids) != len(set(plan_ids)):
        raise ValueError(f"{name} trial plan count/uniqueness differs from manifest")
    if set(plan_ids) != set(trial_ids):
        raise ValueError(f"{name} trial plan does not exactly cover results")
    result_seeds = {row["trial_id"]: int(row["seed"]) for row in results}
    plan_seeds = {row["trial_id"]: int(row["seed"]) for row in plans}
    if result_seeds != plan_seeds:
        raise ValueError(f"{name} result seeds differ from the frozen trial plan")
    if len(set(result_seeds.values())) != expected_trials:
        raise ValueError(f"{name} contains duplicate RNG seeds")

    cell_counts = Counter(
        (
            row["feature_set_name"],
            row["condition"],
            row["query_name"],
            float(row["steering_value"]),
        )
        for row in results
    )
    expected_n_cells = (
        int(manifest["n_feature_sets"])
        * len(manifest["conditions"])
        * len(manifest["queries"])
        * len(manifest["steering_values"])
    )
    expected_cell_size = int(manifest["n_trials_per_cell"])
    if len(cell_counts) != expected_n_cells or any(
        count != expected_cell_size for count in cell_counts.values()
    ):
        raise ValueError(f"{name} result cells differ from the manifest")

    judgment_ids = [row["judgment_id"] for row in judgments]
    if len(judgment_ids) != len(set(judgment_ids)):
        raise ValueError(f"{name} contains duplicate judgment IDs")
    judge_keys = {row["judge_key"] for row in judgments}
    if len(judge_keys) != 2:
        raise ValueError(f"{name} must contain exactly two judge panels")
    judges_by_trial: dict[str, set[str]] = defaultdict(set)
    for judgment in judgments:
        judges_by_trial[judgment["trial_id"]].add(judgment["judge_key"])
    if len(judgments) != expected_trials * len(judge_keys):
        raise ValueError(f"{name} judgment count is incomplete")
    if set(judges_by_trial) != set(trial_ids) or any(
        judges_by_trial[trial_id] != judge_keys for trial_id in trial_ids
    ):
        raise ValueError(f"{name} does not have the full judge panel per trial")
    return judge_keys


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("base_dir", type=Path)
    parser.add_argument("extension_dir", type=Path)
    parser.add_argument("outdir", type=Path)
    args = parser.parse_args()

    base_manifest = read_json(args.base_dir / "placebo_manifest.json")
    extension_manifest = read_json(args.extension_dir / "placebo_manifest.json")
    assert_compatible(base_manifest, extension_manifest)
    base_feature_sets = (args.base_dir / "placebo_feature_sets.csv").read_bytes()
    extension_feature_sets = (args.extension_dir / "placebo_feature_sets.csv").read_bytes()
    if base_feature_sets != extension_feature_sets:
        raise ValueError("Feature-set catalogs differ across component runs")

    base_results = read_jsonl(args.base_dir / "placebo_results.jsonl")
    extension_results = read_jsonl(args.extension_dir / "placebo_results.jsonl")
    base_judgments = read_jsonl(args.base_dir / "judgments_paper.jsonl")
    extension_judgments = read_jsonl(args.extension_dir / "judgments_paper.jsonl")
    base_plans = read_csv(args.base_dir / "placebo_trial_plan.csv")
    extension_plans = read_csv(args.extension_dir / "placebo_trial_plan.csv")
    base_judges = validate_component(
        "base", base_manifest, base_results, base_judgments, base_plans
    )
    extension_judges = validate_component(
        "extension",
        extension_manifest,
        extension_results,
        extension_judgments,
        extension_plans,
    )
    if base_judges != extension_judges:
        raise ValueError("Judge panels differ across component runs")

    results = base_results + extension_results
    judgments = base_judgments + extension_judgments
    trial_ids = [row["trial_id"] for row in results]
    judgment_ids = [row["judgment_id"] for row in judgments]
    if len(trial_ids) != len(set(trial_ids)):
        raise ValueError("Component runs overlap in trial IDs")
    seeds = [int(row["seed"]) for row in results]
    if len(seeds) != len(set(seeds)):
        raise ValueError("Component runs overlap in RNG seeds")
    if len(judgment_ids) != len(set(judgment_ids)):
        raise ValueError("Component runs overlap in judgment IDs")
    if {row["trial_id"] for row in judgments} != set(trial_ids):
        raise ValueError("Judgment trial IDs do not exactly cover merged results")

    feature_order = {
        name: index
        for index, name in enumerate(
            dict.fromkeys(row["feature_set_name"] for row in results)
        )
    }
    results.sort(
        key=lambda row: (
            feature_order[row["feature_set_name"]],
            float(row["steering_value"]),
            int(row["trial_idx"]),
        )
    )
    judgments.sort(key=lambda row: row["judgment_id"])
    plans = base_plans + extension_plans
    if {row["trial_id"] for row in plans} != set(trial_ids):
        raise ValueError("Merged trial plans do not exactly cover merged results")
    plans.sort(
        key=lambda row: (
            feature_order[row["feature_set_name"]],
            float(row["steering_value"]),
            int(row["trial_idx"]),
        )
    )

    args.outdir.mkdir(parents=True, exist_ok=True)
    write_jsonl(args.outdir / "placebo_results.jsonl", results)
    write_jsonl(args.outdir / "judgments_paper.jsonl", judgments)
    write_csv(args.outdir / "placebo_trial_plan.csv", plans)
    shutil.copyfile(
        args.base_dir / "placebo_feature_sets.csv",
        args.outdir / "placebo_feature_sets.csv",
    )

    cell_counts: dict[tuple[str, float], int] = {}
    for row in results:
        key = (row["feature_set_name"], float(row["steering_value"]))
        cell_counts[key] = cell_counts.get(key, 0) + 1
    unique_cell_sizes = sorted(set(cell_counts.values()))
    expected_combined_cell_size = int(base_manifest["n_trials_per_cell"]) + int(
        extension_manifest["n_trials_per_cell"]
    )
    if unique_cell_sizes != [expected_combined_cell_size]:
        raise ValueError(f"Merged cells are unbalanced: {cell_counts}")
    combined_manifest = {
        **base_manifest,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "mode": "combined_adaptive_precision_extension",
        "n_trials_planned": len(results),
        "n_trials_per_cell": unique_cell_sizes[0],
        "trial_start": min(int(row["trial_idx"]) for row in results),
        "trial_stop_exclusive": max(int(row["trial_idx"]) for row in results) + 1,
        "seed_scheme": "component_specific; see component manifests",
        "component_runs": [
            {
                "path": str(args.base_dir),
                "n_trials": int(base_manifest["n_trials_planned"]),
                "manifest_sha256": sha256(args.base_dir / "placebo_manifest.json"),
                "results_sha256": sha256(args.base_dir / "placebo_results.jsonl"),
            },
            {
                "path": str(args.extension_dir),
                "n_trials": int(extension_manifest["n_trials_planned"]),
                "manifest_sha256": sha256(args.extension_dir / "placebo_manifest.json"),
                "results_sha256": sha256(args.extension_dir / "placebo_results.jsonl"),
            },
        ],
        "adaptive_status": (
            "The n=3 base was inspected before the n=17 extension was frozen. "
            "The combined n=20 analysis is an adaptive precision follow-up, not a "
            "prospectively confirmatory test."
        ),
    }
    (args.outdir / "placebo_manifest.json").write_text(
        json.dumps(combined_manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (args.outdir / "PROVENANCE.md").write_text(
        "# Combined Adaptive Public-SAE Run\n\n"
        "This directory combines the frozen long-form n=3 base with a disjoint "
        "n=17-per-cell precision extension. The extension was chosen after inspecting "
        "the base result and is therefore adaptive. Component raw outputs, judgments, "
        "logs, manifests, and runtime records remain in their original directories.\n",
        encoding="utf-8",
    )
    print(
        f"Merged {len(results)} trials and {len(judgments)} judgments into {args.outdir}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

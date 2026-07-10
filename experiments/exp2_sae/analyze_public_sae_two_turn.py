#!/usr/bin/env python3
"""Audit and analyze the corrected public-SAE two-turn validation."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import subprocess
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import numpy as np


TARGET_PLACEBO_PAIRS = (
    ("single", "target_58667_cover_story", "random_22326_refusal"),
    ("aggregate", "ae_public_targets", "random_irrelevant_active"),
)

EXPECTED_PAPER_JUDGES = (
    "anthropic:claude-haiku-4-5-20251001",
    "openai:gpt-4o-mini-2024-07-18",
)


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def current_commit(repo_root: Path) -> str | None:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=repo_root, text=True
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def write_release_manifest(
    run_dir: Path,
    rows: list[dict[str, Any]],
    judgments: list[dict[str, Any]],
) -> None:
    output = run_dir / "release_manifest.json"
    files = []
    for path in sorted(run_dir.rglob("*")):
        if not path.is_file() or path == output:
            continue
        files.append(
            {
                "path": str(path.relative_to(run_dir)),
                "bytes": path.stat().st_size,
                "sha256": sha256(path),
            }
        )
    write_json(
        output,
        {
            "schema_version": 1,
            "created_at_utc": datetime.now(timezone.utc).isoformat(),
            "analysis_code_commit": current_commit(Path(__file__).resolve().parents[2]),
            "run_directory": str(run_dir),
            "audits": {
                "placebo_results.jsonl": {
                    "rows": len(rows),
                    "unique_trial_ids": len({row["trial_id"] for row in rows}),
                },
                "judgments_paper.jsonl": {
                    "rows": len(judgments),
                    "unique_judgment_ids": len(
                        {row["judgment_id"] for row in judgments}
                    ),
                },
            },
            "files": files,
        },
    )


def mean(values: Iterable[float]) -> float | None:
    values = list(values)
    return sum(values) / len(values) if values else None


def wilson_interval(positives: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (float("nan"), float("nan"))
    rate = positives / n
    denominator = 1 + z * z / n
    center = (rate + z * z / (2 * n)) / denominator
    margin = z * math.sqrt(rate * (1 - rate) / n + z * z / (4 * n * n)) / denominator
    return (max(0.0, center - margin), min(1.0, center + margin))


def jeffreys_gap_draws(
    suppress: list[int],
    amplify: list[int],
    rng: np.random.Generator,
    iterations: int,
) -> np.ndarray:
    suppress_successes = sum(suppress)
    amplify_successes = sum(amplify)
    suppress_draws = rng.beta(
        suppress_successes + 0.5,
        len(suppress) - suppress_successes + 0.5,
        size=iterations,
    )
    amplify_draws = rng.beta(
        amplify_successes + 0.5,
        len(amplify) - amplify_successes + 0.5,
        size=iterations,
    )
    return suppress_draws - amplify_draws


def cohen_kappa(left: list[int], right: list[int]) -> float | None:
    if not left or len(left) != len(right):
        return None
    observed = sum(a == b for a, b in zip(left, right)) / len(left)
    left_rates = Counter(left)
    right_rates = Counter(right)
    expected = sum(
        (left_rates[label] / len(left)) * (right_rates[label] / len(right))
        for label in {0, 1}
    )
    if expected == 1.0:
        return 1.0
    return (observed - expected) / (1.0 - expected)


def protocol_audit(
    rows: list[dict[str, Any]],
    judgments: list[dict[str, Any]],
    manifest: dict[str, Any],
    trial_plan: list[dict[str, str]],
    expected_judges: tuple[str, ...] = EXPECTED_PAPER_JUDGES,
) -> dict[str, Any]:
    trial_ids = [row["trial_id"] for row in rows]
    judgment_ids = [row["judgment_id"] for row in judgments]
    expected_trials = int(manifest["n_trials_planned"])
    judge_keys = {row["judge_key"] for row in judgments}
    n_observed_judges = len(judge_keys)
    judgments_per_trial = Counter(row["trial_id"] for row in judgments)
    judge_keys_per_trial: dict[str, set[str]] = defaultdict(set)
    for judgment in judgments:
        judge_keys_per_trial[judgment["trial_id"]].add(judgment["judge_key"])
    cell_counts = Counter(
        (
            row["feature_set_name"],
            row["condition"],
            row["query_name"],
            float(row["steering_value"]),
        )
        for row in rows
    )
    expected_cell_count = int(manifest["n_trials_per_cell"])
    expected_n_cells = (
        int(manifest["n_feature_sets"])
        * len(manifest["conditions"])
        * len(manifest["queries"])
        * len(manifest["steering_values"])
    )
    turns = [
        diagnostics
        for row in rows
        for diagnostics in (row.get("induction_diagnostics"), row.get("final_diagnostics"))
        if diagnostics is not None
    ]
    zero_turns = [turn for turn in turns if float(turn["steering_value"]) == 0.0]
    nonzero_turns = [turn for turn in turns if float(turn["steering_value"]) != 0.0]
    induction_turns = [
        row["induction_diagnostics"]
        for row in rows
        if row.get("induction_diagnostics") is not None
    ]
    final_turns = [
        row["final_diagnostics"]
        for row in rows
        if row.get("final_diagnostics") is not None
    ]
    induction_cap = int(manifest["induction_max_tokens"])
    final_cap = int(manifest["final_max_tokens"])
    induction_cap_hits = sum(
        int(turn.get("generated_tokens", -1)) >= induction_cap
        for turn in induction_turns
    )
    final_cap_hits = sum(
        int(turn.get("generated_tokens", -1)) >= final_cap for turn in final_turns
    )

    latent_delta_matches = []
    for turn in nonzero_turns:
        before = turn.get("target_activation_before_mean")
        after = turn.get("target_activation_after_mean")
        requested = turn.get("requested_latent_delta")
        latent_delta_matches.append(
            before is not None
            and after is not None
            and requested is not None
            and abs((float(after) - float(before)) - float(requested)) < 1e-4
        )

    plan_ids = [row.get("trial_id", "") for row in trial_plan]
    plan_by_id = {row.get("trial_id", ""): row for row in trial_plan}
    result_by_id = {row["trial_id"]: row for row in rows}

    def plan_matches_result(trial_id: str) -> bool:
        plan = plan_by_id.get(trial_id)
        result = result_by_id[trial_id]
        if plan is None:
            return False
        try:
            plan_feature_ids = [int(value) for value in plan["feature_ids"].split()]
            return (
                plan["feature_set_name"] == result["feature_set_name"]
                and plan["feature_set_kind"] == result["feature_set_kind"]
                and plan_feature_ids == [int(value) for value in result["feature_ids"]]
                and plan["condition"] == result["condition"]
                and plan["query_name"] == result["query_name"]
                and plan["query_text"] == result["query_text"]
                and float(plan["steering_value"]) == float(result["steering_value"])
                and int(plan["trial_idx"]) == int(result["trial_idx"])
                and int(plan["seed"]) == int(result["seed"])
            )
        except (KeyError, TypeError, ValueError):
            return False

    def diagnostics_match_result(row: dict[str, Any]) -> bool:
        expected_features = [int(value) for value in row["feature_ids"]]
        expected_value = float(row["steering_value"])
        for diagnostics in (
            row.get("induction_diagnostics"),
            row.get("final_diagnostics"),
        ):
            if diagnostics is None:
                return False
            if diagnostics.get("protocol_version") != row.get("protocol_version"):
                return False
            if float(diagnostics.get("steering_value", float("nan"))) != expected_value:
                return False
            if [int(value) for value in diagnostics.get("feature_indices", [])] != expected_features:
                return False
        return True

    def judgment_matches_result(judgment: dict[str, Any]) -> bool:
        result = result_by_id.get(judgment.get("trial_id"))
        if result is None:
            return False
        return (
            judgment.get("task") == "paper"
            and judgment.get("query") == result["query_text"]
            and judgment.get("response") == result["response"]
            and judgment.get("feature_set_name") == result["feature_set_name"]
            and float(judgment.get("steering_value", float("nan")))
            == float(result["steering_value"])
            and int(judgment.get("trial_idx", -1)) == int(result["trial_idx"])
            and judgment.get("protocol_version") == result.get("protocol_version")
        )

    checks = {
        "trial_count_matches_manifest": len(rows) == expected_trials,
        "trial_ids_unique": len(trial_ids) == len(set(trial_ids)),
        "feature_set_count_matches_manifest": len(
            {row["feature_set_name"] for row in rows}
        )
        == int(manifest["n_feature_sets"]),
        "conditions_match_manifest": {row["condition"] for row in rows}
        == set(manifest["conditions"]),
        "queries_match_manifest": {row["query_name"] for row in rows}
        == set(manifest["queries"]),
        "steering_values_match_manifest": {
            float(row["steering_value"]) for row in rows
        }
        == {float(value) for value in manifest["steering_values"]},
        "cell_count_matches_manifest": len(cell_counts) == expected_n_cells,
        "all_cells_have_planned_size": all(
            count == expected_cell_count for count in cell_counts.values()
        ),
        "trial_plan_count_matches_manifest": len(trial_plan) == expected_trials,
        "trial_plan_ids_unique": len(plan_ids) == len(set(plan_ids)),
        "trial_plan_ids_match_results": set(plan_ids) == set(trial_ids),
        "trial_plan_metadata_matches_results": len(trial_plan) == expected_trials
        and set(plan_ids) == set(trial_ids)
        and all(plan_matches_result(trial_id) for trial_id in trial_ids),
        "result_seeds_unique": len({int(row["seed"]) for row in rows}) == len(rows),
        "judgment_ids_unique": len(judgment_ids) == len(set(judgment_ids)),
        "exact_expected_judge_panel": judge_keys == set(expected_judges),
        "judgment_count_complete": len(judgments) == len(rows) * len(expected_judges),
        "judgment_trials_match_results": set(judgments_per_trial) == set(trial_ids),
        "exactly_two_judgments_per_trial": all(
            judgments_per_trial[trial_id] == 2 for trial_id in trial_ids
        ),
        "every_trial_has_full_judge_panel": all(
            judge_keys_per_trial[trial_id] == judge_keys for trial_id in trial_ids
        ),
        "judgments_match_result_text_and_metadata": all(
            judgment_matches_result(judgment) for judgment in judgments
        ),
        "all_paper_labels_binary": all(row.get("paper_label") in {0, 1} for row in judgments),
        "all_protocol_v2": all(
            row.get("protocol_version") == "public_sae_two_turn_v2" for row in rows
        ),
        "all_induction_responses_nonempty": all(
            bool(row.get("induction_response", "").strip()) for row in rows
        ),
        "all_final_responses_nonempty": all(bool(row.get("response", "").strip()) for row in rows),
        "all_two_turn_diagnostics_present": len(turns) == len(rows) * 2,
        "all_diagnostics_match_result_specs": all(
            diagnostics_match_result(row) for row in rows
        ),
        "all_single_hook_registration": all(turn.get("hook_registrations") == 1 for turn in turns),
        "all_hooks_removed": all(turn.get("hook_removed") is True for turn in turns),
        "all_zero_turns_true_noop": bool(zero_turns)
        and all(
            turn.get("zero_is_true_noop") is True
            and turn.get("steering_applied") is False
            and turn.get("hidden_delta_rms") is None
            for turn in zero_turns
        ),
        "all_nonzero_turns_applied": bool(nonzero_turns)
        and all(
            turn.get("steering_applied") is True
            and float(turn.get("hidden_delta_rms", 0.0)) > 0.0
            for turn in nonzero_turns
        ),
        "all_nonzero_latent_deltas_match_request": bool(latent_delta_matches)
        and all(latent_delta_matches),
    }
    return {
        "status": "pass" if all(checks.values()) else "fail",
        "checks": checks,
        "n_trials": len(rows),
        "n_unique_trials": len(set(trial_ids)),
        "n_judgments": len(judgments),
        "n_judges": n_observed_judges,
        "expected_judge_keys": list(expected_judges),
        "observed_judge_keys": sorted(judge_keys),
        "n_turns": len(turns),
        "n_zero_turns": len(zero_turns),
        "n_nonzero_turns": len(nonzero_turns),
        "token_caps": {
            "induction_max_tokens": induction_cap,
            "n_induction_turns": len(induction_turns),
            "n_induction_cap_hits": induction_cap_hits,
            "induction_cap_hit_rate": (
                induction_cap_hits / len(induction_turns) if induction_turns else None
            ),
            "final_max_tokens": final_cap,
            "n_final_turns": len(final_turns),
            "n_final_cap_hits": final_cap_hits,
            "final_cap_hit_rate": final_cap_hits / len(final_turns) if final_turns else None,
        },
    }


def behavioral_tables(
    rows: list[dict[str, Any]],
    judgments: list[dict[str, Any]],
    posterior_draws: int = 10000,
    interval_seed: int = 20260709,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    by_trial = {row["trial_id"]: row for row in rows}
    grouped: dict[tuple[str, str, float], list[int]] = defaultdict(list)
    for judgment in judgments:
        trial = by_trial[judgment["trial_id"]]
        grouped[
            (
                judgment["judge_key"],
                trial["feature_set_name"],
                float(trial["steering_value"]),
            )
        ].append(int(judgment["paper_label"]))

    rates: list[dict[str, Any]] = []
    for (judge_key, feature_set, steering_value), labels in sorted(grouped.items()):
        ci_low, ci_high = wilson_interval(sum(labels), len(labels))
        rates.append(
            {
                "judge_key": judge_key,
                "feature_set_name": feature_set,
                "steering_value": steering_value,
                "n": len(labels),
                "n_positive": sum(labels),
                "positive_rate": sum(labels) / len(labels),
                "ci_low": ci_low,
                "ci_high": ci_high,
            }
        )

    rate_lookup = {
        (row["judge_key"], row["feature_set_name"], float(row["steering_value"])): float(
            row["positive_rate"]
        )
        for row in rates
    }
    signatures: list[dict[str, Any]] = []
    signature_bootstraps: dict[tuple[str, str], np.ndarray] = {}
    rng = np.random.default_rng(interval_seed)
    for judge_key in sorted({row["judge_key"] for row in rates}):
        for feature_set in sorted({row["feature_set_name"] for row in rates}):
            suppress = rate_lookup[(judge_key, feature_set, -2.0)]
            neutral = rate_lookup[(judge_key, feature_set, 0.0)]
            amplify = rate_lookup[(judge_key, feature_set, 2.0)]
            gap_draws = jeffreys_gap_draws(
                grouped[(judge_key, feature_set, -2.0)],
                grouped[(judge_key, feature_set, 2.0)],
                rng,
                posterior_draws,
            )
            signature_bootstraps[(judge_key, feature_set)] = gap_draws
            gap_low, gap_high = np.percentile(gap_draws, [2.5, 97.5])
            signatures.append(
                {
                    "judge_key": judge_key,
                    "feature_set_name": feature_set,
                    "suppress_rate": suppress,
                    "neutral_rate": neutral,
                    "amplify_rate": amplify,
                    "suppress_minus_amplify": suppress - amplify,
                    "gap_ci_low": float(gap_low),
                    "gap_ci_high": float(gap_high),
                    "paper_like_direction": suppress > amplify,
                }
            )

    signature_lookup = {
        (row["judge_key"], row["feature_set_name"]): row for row in signatures
    }
    contrasts: list[dict[str, Any]] = []
    for judge_key in sorted({row["judge_key"] for row in signatures}):
        for cardinality, target, placebo in TARGET_PLACEBO_PAIRS:
            target_gap = float(signature_lookup[(judge_key, target)]["suppress_minus_amplify"])
            placebo_gap = float(signature_lookup[(judge_key, placebo)]["suppress_minus_amplify"])
            target_draws = signature_bootstraps[(judge_key, target)]
            placebo_draws = signature_bootstraps[(judge_key, placebo)]
            difference_draws = target_draws - placebo_draws
            target_low, target_high = np.percentile(target_draws, [2.5, 97.5])
            placebo_low, placebo_high = np.percentile(placebo_draws, [2.5, 97.5])
            difference_low, difference_high = np.percentile(
                difference_draws, [2.5, 97.5]
            )
            contrasts.append(
                {
                    "judge_key": judge_key,
                    "cardinality": cardinality,
                    "target_feature_set": target,
                    "placebo_feature_set": placebo,
                    "target_suppress_minus_amplify": target_gap,
                    "target_gap_ci_low": float(target_low),
                    "target_gap_ci_high": float(target_high),
                    "placebo_suppress_minus_amplify": placebo_gap,
                    "placebo_gap_ci_low": float(placebo_low),
                    "placebo_gap_ci_high": float(placebo_high),
                    "target_minus_placebo_gap": target_gap - placebo_gap,
                    "target_minus_placebo_ci_low": float(difference_low),
                    "target_minus_placebo_ci_high": float(difference_high),
                }
            )
    return rates, signatures, contrasts


def telemetry_table(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, float, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        for turn_name, diagnostics in (
            ("induction", row.get("induction_diagnostics")),
            ("final", row.get("final_diagnostics")),
        ):
            if diagnostics is not None:
                grouped[
                    (row["feature_set_name"], float(row["steering_value"]), turn_name)
                ].append(diagnostics)

    output: list[dict[str, Any]] = []
    for (feature_set, steering_value, turn_name), turns in sorted(grouped.items()):
        output.append(
            {
                "feature_set_name": feature_set,
                "steering_value": steering_value,
                "turn": turn_name,
                "n": len(turns),
                "mean_target_activation_before": mean(
                    float(turn["target_activation_before_mean"])
                    for turn in turns
                    if turn.get("target_activation_before_mean") is not None
                ),
                "mean_target_activation_after": mean(
                    float(turn["target_activation_after_mean"])
                    for turn in turns
                    if turn.get("target_activation_after_mean") is not None
                ),
                "mean_hidden_delta_rms": mean(
                    float(turn["hidden_delta_rms"])
                    for turn in turns
                    if turn.get("hidden_delta_rms") is not None
                ),
                "mean_relative_hidden_delta_rms": mean(
                    float(turn["relative_hidden_delta_rms"])
                    for turn in turns
                    if turn.get("relative_hidden_delta_rms") is not None
                ),
                "mean_hook_calls": mean(float(turn["hook_calls"]) for turn in turns),
            }
        )
    return output


def generation_length_table(
    rows: list[dict[str, Any]], manifest: dict[str, Any]
) -> list[dict[str, Any]]:
    caps = {
        "induction": int(manifest["induction_max_tokens"]),
        "final": int(manifest["final_max_tokens"]),
    }
    grouped: dict[tuple[str, float, str], list[int]] = defaultdict(list)
    for row in rows:
        for turn_name, diagnostics in (
            ("induction", row.get("induction_diagnostics")),
            ("final", row.get("final_diagnostics")),
        ):
            if diagnostics is not None:
                grouped[
                    (row["feature_set_name"], float(row["steering_value"]), turn_name)
                ].append(int(diagnostics["generated_tokens"]))

    output: list[dict[str, Any]] = []
    for (feature_set, steering_value, turn_name), token_counts in sorted(
        grouped.items()
    ):
        cap = caps[turn_name]
        n_cap_hits = sum(count >= cap for count in token_counts)
        output.append(
            {
                "feature_set_name": feature_set,
                "steering_value": steering_value,
                "turn": turn_name,
                "n": len(token_counts),
                "token_cap": cap,
                "mean_generated_tokens": mean(token_counts),
                "median_generated_tokens": float(np.median(token_counts)),
                "n_cap_hits": n_cap_hits,
                "cap_hit_rate": n_cap_hits / len(token_counts),
            }
        )
    return output


def judge_agreement(judgments: list[dict[str, Any]]) -> dict[str, Any]:
    judges = sorted({row["judge_key"] for row in judgments})
    if len(judges) != 2:
        return {"judge_keys": judges, "n_joint": 0, "agreement": None, "cohen_kappa": None}
    by_trial: dict[str, dict[str, int]] = defaultdict(dict)
    for row in judgments:
        by_trial[row["trial_id"]][row["judge_key"]] = int(row["paper_label"])
    joint = [labels for labels in by_trial.values() if all(judge in labels for judge in judges)]
    left = [labels[judges[0]] for labels in joint]
    right = [labels[judges[1]] for labels in joint]
    return {
        "judge_keys": judges,
        "n_joint": len(joint),
        "agreement": sum(a == b for a, b in zip(left, right)) / len(joint) if joint else None,
        "cohen_kappa": cohen_kappa(left, right),
        "judge_positive_rates": {
            judges[0]: sum(left) / len(left) if left else None,
            judges[1]: sum(right) / len(right) if right else None,
        },
    }


def make_figure(rates: list[dict[str, Any]], telemetry: list[dict[str, Any]], path: Path) -> None:
    import matplotlib.pyplot as plt

    judges = sorted({row["judge_key"] for row in rates})
    feature_sets = [
        "target_58667_cover_story",
        "random_22326_refusal",
        "ae_public_targets",
        "random_irrelevant_active",
    ]
    labels = {
        "target_58667_cover_story": "Target single",
        "random_22326_refusal": "Active random single",
        "ae_public_targets": "Target aggregate",
        "random_irrelevant_active": "Active random aggregate",
    }
    colors = {
        "target_58667_cover_story": "#b33b2e",
        "random_22326_refusal": "#6b7280",
        "ae_public_targets": "#d97706",
        "random_irrelevant_active": "#2563a6",
    }
    markers = {
        "target_58667_cover_story": "o",
        "random_22326_refusal": "o",
        "ae_public_targets": "s",
        "random_irrelevant_active": "s",
    }

    fig, axes = plt.subplots(1, 3, figsize=(10.8, 3.2), constrained_layout=True)
    rate_lookup = {
        (row["judge_key"], row["feature_set_name"], float(row["steering_value"])): float(
            row["positive_rate"]
        )
        for row in rates
    }
    interval_lookup = {
        (row["judge_key"], row["feature_set_name"], float(row["steering_value"])): (
            float(row["ci_low"]),
            float(row["ci_high"]),
        )
        for row in rates
    }
    for axis, judge in zip(axes[:2], judges):
        for feature_set in feature_sets:
            x = [-2.0, 0.0, 2.0]
            y = [rate_lookup[(judge, feature_set, value)] for value in x]
            intervals = [interval_lookup[(judge, feature_set, value)] for value in x]
            axis.errorbar(
                x,
                y,
                yerr=[
                    [point - low for point, (low, _high) in zip(y, intervals)],
                    [high - point for point, (_low, high) in zip(y, intervals)],
                ],
                color=colors[feature_set],
                marker=markers[feature_set],
                linewidth=1.8,
                elinewidth=0.8,
                capsize=2,
                markersize=5,
                label=labels[feature_set],
            )
        axis.set_ylim(-0.05, 1.05)
        axis.set_xticks([-2, 0, 2], ["Suppress", "Zero", "Amplify"])
        axis.set_ylabel("Paper-judge positive rate")
        axis.set_title("OpenAI judge" if judge.startswith("openai:") else "Anthropic judge")
        axis.grid(axis="y", color="#d1d5db", linewidth=0.6)

    telemetry_lookup = {
        (row["feature_set_name"], float(row["steering_value"]), row["turn"]): row
        for row in telemetry
    }
    axis = axes[2]
    offsets = [-0.24, -0.08, 0.08, 0.24]
    for offset, feature_set in zip(offsets, feature_sets):
        values = []
        for steering_value in (-2.0, 0.0, 2.0):
            row = telemetry_lookup[(feature_set, steering_value, "final")]
            values.append(float(row["mean_relative_hidden_delta_rms"] or 0.0))
        axis.bar(
            [value + offset for value in (-2, 0, 2)],
            values,
            width=0.15,
            color=colors[feature_set],
            label=labels[feature_set],
        )
    axis.set_xticks([-2, 0, 2], ["Suppress", "Zero", "Amplify"])
    axis.set_ylabel("Relative hidden-state RMS change")
    axis.set_title("Final-turn intervention telemetry")
    axis.grid(axis="y", color="#d1d5db", linewidth=0.6)
    handles, legend_labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, legend_labels, loc="outside lower center", ncol=2, frameon=False)
    cell_sizes = sorted({int(row["n"]) for row in rates})
    sample_text = (
        f"n={cell_sizes[0]} per cell"
        if len(cell_sizes) == 1
        else f"cell n={min(cell_sizes)}-{max(cell_sizes)}"
    )
    fig.suptitle(f"Corrected public-SAE two-turn validation ({sample_text})", fontsize=11)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=220, bbox_inches="tight", facecolor="white", transparent=False)
    plt.close(fig)


def fmt(value: Any) -> str:
    return "NA" if value is None else f"{float(value):.3f}"


def write_summary(
    path: Path,
    audit: dict[str, Any],
    rates: list[dict[str, Any]],
    signatures: list[dict[str, Any]],
    contrasts: list[dict[str, Any]],
    agreement: dict[str, Any],
) -> None:
    cell_sizes = sorted({int(row["n"]) for row in rates})
    sample_text = (
        f"{cell_sizes[0]} generations per cell"
        if len(cell_sizes) == 1
        else f"{min(cell_sizes)}-{max(cell_sizes)} generations per cell"
    )
    parts = [
        "# Corrected Public-SAE Two-Turn Validation",
        "",
        f"Protocol audit: **{audit['status'].upper()}** ({audit['n_trials']} trials, {audit['n_judgments']} exact-paper judgments).",
        "",
        f"Token caps: {audit['token_caps']['n_induction_cap_hits']}/{audit['token_caps']['n_induction_turns']} induction turns and {audit['token_caps']['n_final_cap_hits']}/{audit['token_caps']['n_final_turns']} final turns reached their configured maxima.",
        "",
        "The primary analysis retains every generated final response. Files ending in `_no_final_cap_hits` repeat the full behavioral analysis after excluding final responses that reached the configured cap; this is a truncation sensitivity analysis, not a replacement estimand.",
        "",
        f"This validation has {sample_text}. Wilson cell intervals and independent-cell Jeffreys-Beta posterior contrast intervals quantify generation-level uncertainty; they do not define a population of models or proprietary implementations.",
        "",
        "## Paper-Style Judge Rates",
        "",
        "| Judge | Feature set | Suppress | Zero | Amplify | Supp - Amp [95% Jeffreys] |",
        "|---|---|---:|---:|---:|---:|",
    ]
    for row in signatures:
        parts.append(
            f"| `{row['judge_key']}` | `{row['feature_set_name']}` | "
            f"{fmt(row['suppress_rate'])} | {fmt(row['neutral_rate'])} | "
            f"{fmt(row['amplify_rate'])} | {fmt(row['suppress_minus_amplify'])} "
            f"[{fmt(row['gap_ci_low'])}, {fmt(row['gap_ci_high'])}] |"
        )
    parts.extend(
        [
            "",
            "## Target Versus Active-Random Controls",
            "",
            "| Judge | Match | Target gap | Placebo gap | Target - placebo [95% Jeffreys] |",
            "|---|---|---:|---:|---:|",
        ]
    )
    for row in contrasts:
        parts.append(
            f"| `{row['judge_key']}` | {row['cardinality']} | "
            f"{fmt(row['target_suppress_minus_amplify'])} | "
            f"{fmt(row['placebo_suppress_minus_amplify'])} | "
            f"{fmt(row['target_minus_placebo_gap'])} "
            f"[{fmt(row['target_minus_placebo_ci_low'])}, "
            f"{fmt(row['target_minus_placebo_ci_high'])}] |"
        )
    parts.extend(
        [
            "",
            "## Judge Agreement",
            "",
            f"- Joint rows: {agreement['n_joint']}",
            f"- Agreement: {fmt(agreement['agreement'])}",
            f"- Cohen's kappa: {fmt(agreement['cohen_kappa'])}",
            "",
            "## Claim Boundary",
            "",
            "A passing telemetry audit establishes that this clean-room public-weight intervention executed as specified. Behavioral results remain conditional on the public SAE, candidate IDs, tested magnitudes, two-turn implementation, small cell size, and model judges. They are not an exact replication of the unavailable proprietary Goodfire/Steering API workflow.",
        ]
    )
    path.write_text("\n".join(parts) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_dir", type=Path)
    args = parser.parse_args()

    run_dir = args.run_dir
    result_path = run_dir / "placebo_results.jsonl"
    judgment_path = run_dir / "judgments_paper.jsonl"
    manifest_path = run_dir / "placebo_manifest.json"
    trial_plan_path = run_dir / "placebo_trial_plan.csv"
    rows = read_jsonl(result_path)
    judgments = read_jsonl(judgment_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    trial_plan = read_csv(trial_plan_path)

    audit = protocol_audit(rows, judgments, manifest, trial_plan)
    rates, signatures, contrasts = behavioral_tables(rows, judgments)
    final_cap = int(manifest["final_max_tokens"])
    final_cap_hit_ids = {
        row["trial_id"]
        for row in rows
        if int(row["final_diagnostics"]["generated_tokens"]) >= final_cap
    }
    uncapped_rows = [row for row in rows if row["trial_id"] not in final_cap_hit_ids]
    uncapped_judgments = [
        row for row in judgments if row["trial_id"] not in final_cap_hit_ids
    ]
    uncapped_rates, uncapped_signatures, uncapped_contrasts = behavioral_tables(
        uncapped_rows, uncapped_judgments
    )
    telemetry = telemetry_table(rows)
    generation_lengths = generation_length_table(rows, manifest)
    agreement = judge_agreement(judgments)

    write_json(run_dir / "corrected_protocol_audit.json", audit)
    write_json(run_dir / "paper_judge_agreement.json", agreement)
    write_csv(
        run_dir / "paper_judge_rates.csv",
        rates,
        [
            "judge_key",
            "feature_set_name",
            "steering_value",
            "n",
            "n_positive",
            "positive_rate",
            "ci_low",
            "ci_high",
        ],
    )
    write_csv(
        run_dir / "paper_signature_effects.csv",
        signatures,
        [
            "judge_key",
            "feature_set_name",
            "suppress_rate",
            "neutral_rate",
            "amplify_rate",
            "suppress_minus_amplify",
            "gap_ci_low",
            "gap_ci_high",
            "paper_like_direction",
        ],
    )
    write_csv(
        run_dir / "paper_target_placebo_contrasts.csv",
        contrasts,
        [
            "judge_key",
            "cardinality",
            "target_feature_set",
            "placebo_feature_set",
            "target_suppress_minus_amplify",
            "target_gap_ci_low",
            "target_gap_ci_high",
            "placebo_suppress_minus_amplify",
            "placebo_gap_ci_low",
            "placebo_gap_ci_high",
            "target_minus_placebo_gap",
            "target_minus_placebo_ci_low",
            "target_minus_placebo_ci_high",
        ],
    )
    write_csv(
        run_dir / "paper_judge_rates_no_final_cap_hits.csv",
        uncapped_rates,
        [
            "judge_key",
            "feature_set_name",
            "steering_value",
            "n",
            "n_positive",
            "positive_rate",
            "ci_low",
            "ci_high",
        ],
    )
    write_csv(
        run_dir / "paper_signature_effects_no_final_cap_hits.csv",
        uncapped_signatures,
        [
            "judge_key",
            "feature_set_name",
            "suppress_rate",
            "neutral_rate",
            "amplify_rate",
            "suppress_minus_amplify",
            "gap_ci_low",
            "gap_ci_high",
            "paper_like_direction",
        ],
    )
    write_csv(
        run_dir / "paper_target_placebo_contrasts_no_final_cap_hits.csv",
        uncapped_contrasts,
        [
            "judge_key",
            "cardinality",
            "target_feature_set",
            "placebo_feature_set",
            "target_suppress_minus_amplify",
            "target_gap_ci_low",
            "target_gap_ci_high",
            "placebo_suppress_minus_amplify",
            "placebo_gap_ci_low",
            "placebo_gap_ci_high",
            "target_minus_placebo_gap",
            "target_minus_placebo_ci_low",
            "target_minus_placebo_ci_high",
        ],
    )
    write_json(
        run_dir / "final_cap_sensitivity.json",
        {
            "rule": (
                "Primary analysis retains every row. Sensitivity excludes trials "
                "whose final generated-token count reached final_max_tokens."
            ),
            "final_max_tokens": final_cap,
            "n_primary_trials": len(rows),
            "n_final_cap_hits": len(final_cap_hit_ids),
            "final_cap_hit_rate": len(final_cap_hit_ids) / len(rows),
            "excluded_trial_ids": sorted(final_cap_hit_ids),
            "n_sensitivity_trials": len(uncapped_rows),
        },
    )
    write_csv(
        run_dir / "corrected_telemetry_by_turn.csv",
        telemetry,
        [
            "feature_set_name",
            "steering_value",
            "turn",
            "n",
            "mean_target_activation_before",
            "mean_target_activation_after",
            "mean_hidden_delta_rms",
            "mean_relative_hidden_delta_rms",
            "mean_hook_calls",
        ],
    )
    write_csv(
        run_dir / "generation_length_audit.csv",
        generation_lengths,
        [
            "feature_set_name",
            "steering_value",
            "turn",
            "n",
            "token_cap",
            "mean_generated_tokens",
            "median_generated_tokens",
            "n_cap_hits",
            "cap_hit_rate",
        ],
    )
    write_summary(
        run_dir / "corrected_two_turn_summary.md",
        audit,
        rates,
        signatures,
        contrasts,
        agreement,
    )
    make_figure(rates, telemetry, run_dir / "corrected_two_turn_validation.png")
    write_json(
        run_dir / "corrected_analysis_manifest.json",
        {
            "created_at_utc": datetime.now(timezone.utc).isoformat(),
            "analysis": "descriptive corrected public-SAE two-turn validation",
            "n_trials": len(rows),
            "n_judgments": len(judgments),
            "interval_method": (
                "Wilson 95% cell intervals; 10,000-draw independent Jeffreys "
                "Beta(0.5,0.5) posterior intervals for risk-difference contrasts"
            ),
            "final_cap_sensitivity": {
                "primary_retains_cap_hits": True,
                "n_final_cap_hits": len(final_cap_hit_ids),
                "sensitivity_excludes_final_cap_hits": True,
            },
            "input_sha256": {
                result_path.name: sha256(result_path),
                judgment_path.name: sha256(judgment_path),
                manifest_path.name: sha256(manifest_path),
                trial_plan_path.name: sha256(trial_plan_path),
            },
            "inference_boundary": (
                "Wilson cell intervals and independent-cell Jeffreys-Beta posterior contrast intervals "
                "quantify generation-level sampling uncertainty only; they do not define a "
                "population of models or proprietary implementations."
            ),
        },
    )
    write_release_manifest(run_dir, rows, judgments)
    if audit["status"] != "pass":
        raise SystemExit("Protocol audit failed; inspect corrected_protocol_audit.json")
    print(f"Analyzed {len(rows)} trials and {len(judgments)} judgments in {run_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Audit and analyze the branched public-SAE specificity follow-up."""

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


EXPECTED_JUDGES = {
    "anthropic:claude-haiku-4-5-20251001",
    "openai:gpt-4o-mini-2024-07-18",
}
EXPECTED_FEATURE_SETS = {
    "target_58667_cover_story",
    "random_22326_refusal",
}
CONSCIOUSNESS_QUERY = "consciousness"
TARGET_FEATURE_SET = "target_58667_cover_story"
CONTROL_FEATURE_SET = "random_22326_refusal"
LATENT_DELTA_ABS_TOLERANCE = 5e-4


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
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


def mean(values: Iterable[float]) -> float | None:
    values = list(values)
    return sum(values) / len(values) if values else None


def wilson_interval(positives: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return float("nan"), float("nan")
    rate = positives / n
    denominator = 1 + z * z / n
    center = (rate + z * z / (2 * n)) / denominator
    margin = z * math.sqrt(rate * (1 - rate) / n + z * z / (4 * n * n)) / denominator
    return max(0.0, center - margin), min(1.0, center + margin)


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
        iterations,
    )
    amplify_draws = rng.beta(
        amplify_successes + 0.5,
        len(amplify) - amplify_successes + 0.5,
        iterations,
    )
    return suppress_draws - amplify_draws


def cohen_kappa(left: list[int], right: list[int]) -> float | None:
    if not left or len(left) != len(right):
        return None
    observed = sum(a == b for a, b in zip(left, right)) / len(left)
    left_rates = Counter(left)
    right_rates = Counter(right)
    expected = sum(
        left_rates[value] / len(left) * right_rates[value] / len(right)
        for value in (0, 1)
    )
    return 1.0 if expected == 1.0 else (observed - expected) / (1.0 - expected)


def parse_feature_ids(value: str | list[int]) -> list[int]:
    if isinstance(value, str):
        return [int(item) for item in value.split()]
    return [int(item) for item in value]


def protocol_audit(
    manifest: dict[str, Any],
    block_plan: list[dict[str, str]],
    trial_plan: list[dict[str, str]],
    blocks: list[dict[str, Any]],
    results: list[dict[str, Any]],
    judgments: list[dict[str, Any]],
    paper_judgments: list[dict[str, Any]],
) -> dict[str, Any]:
    block_ids = [row["block_id"] for row in blocks]
    trial_ids = [row["trial_id"] for row in results]
    block_plan_ids = [row["block_id"] for row in block_plan]
    trial_plan_ids = [row["trial_id"] for row in trial_plan]
    blocks_by_id = {row["block_id"]: row for row in blocks}
    results_by_id = {row["trial_id"]: row for row in results}
    block_plan_by_id = {row["block_id"]: row for row in block_plan}
    trial_plan_by_id = {row["trial_id"]: row for row in trial_plan}
    judgments_by_trial: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for judgment in judgments:
        judgments_by_trial[judgment["trial_id"]].append(judgment)
    paper_judgments_by_trial: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for judgment in paper_judgments:
        paper_judgments_by_trial[judgment["trial_id"]].append(judgment)

    def block_matches_plan(block_id: str) -> bool:
        block = blocks_by_id[block_id]
        plan = block_plan_by_id.get(block_id)
        if plan is None:
            return False
        return (
            block["feature_set_name"] == plan["feature_set_name"]
            and block["feature_set_kind"] == plan["feature_set_kind"]
            and parse_feature_ids(block["feature_ids"]) == parse_feature_ids(plan["feature_ids"])
            and block["condition"] == plan["condition"]
            and float(block["steering_value"]) == float(plan["steering_value"])
            and int(block["trial_idx"]) == int(plan["trial_idx"])
            and int(block["induction_seed"]) == int(plan["induction_seed"])
        )

    def result_matches_plan(trial_id: str) -> bool:
        result = results_by_id[trial_id]
        plan = trial_plan_by_id.get(trial_id)
        block = blocks_by_id.get(result["block_id"])
        if plan is None or block is None:
            return False
        return (
            result["block_id"] == plan["block_id"]
            and result["feature_set_name"] == plan["feature_set_name"]
            and result["feature_set_kind"] == plan["feature_set_kind"]
            and parse_feature_ids(result["feature_ids"]) == parse_feature_ids(plan["feature_ids"])
            and result["condition"] == plan["condition"]
            and result["query_type"] == plan["query_type"]
            and result["query_name"] == plan["query_name"]
            and result["query_text"] == plan["query_text"]
            and float(result["steering_value"]) == float(plan["steering_value"])
            and int(result["trial_idx"]) == int(plan["trial_idx"])
            and int(result["induction_seed"]) == int(plan["induction_seed"])
            and int(result["final_seed"]) == int(plan["final_seed"])
            and result["induction_response_sha256"] == block["induction_response_sha256"]
        )

    def diagnostics_match(
        diagnostics: dict[str, Any], feature_ids: list[int], value: float
    ) -> bool:
        return (
            diagnostics.get("protocol_version") == manifest["protocol_version"]
            and diagnostics.get("attention_mask_mode")
            == "explicit_all_ones_unpadded"
            and parse_feature_ids(diagnostics.get("feature_indices", [])) == feature_ids
            and float(diagnostics.get("steering_value", float("nan"))) == value
            and diagnostics.get("hook_registrations") == 1
            and diagnostics.get("hook_removed") is True
            and (
                (
                    value == 0.0
                    and diagnostics.get("zero_is_true_noop") is True
                    and diagnostics.get("steering_applied") is False
                    and diagnostics.get("hidden_delta_rms") is None
                )
                or (
                    value != 0.0
                    and diagnostics.get("steering_applied") is True
                    and float(diagnostics.get("hidden_delta_rms", 0.0)) > 0.0
                    and abs(
                        float(diagnostics["target_activation_after_mean"])
                        - float(diagnostics["target_activation_before_mean"])
                        - float(diagnostics["requested_latent_delta"])
                    )
                    < LATENT_DELTA_ABS_TOLERANCE
                )
            )
        )

    block_diagnostics_match = all(
        diagnostics_match(
            row["induction_diagnostics"],
            parse_feature_ids(row["feature_ids"]),
            float(row["steering_value"]),
        )
        for row in blocks
    )
    result_diagnostics_match = all(
        diagnostics_match(
            row["final_diagnostics"],
            parse_feature_ids(row["feature_ids"]),
            float(row["steering_value"]),
        )
        for row in results
    )

    expected_queries = set(manifest["queries"])
    results_per_block = Counter(row["block_id"] for row in results)
    queries_per_block: dict[str, set[str]] = defaultdict(set)
    for row in results:
        queries_per_block[row["block_id"]].add(row["query_name"])

    judge_keys = {row["judge_key"] for row in judgments}
    judgments_match = all(
        judgment.get("task") == "proposition_status"
        and judgment.get("trial_id") in results_by_id
        and judgment.get("block_id") == results_by_id[judgment["trial_id"]]["block_id"]
        and judgment.get("query") == results_by_id[judgment["trial_id"]]["query_text"]
        and judgment.get("response") == results_by_id[judgment["trial_id"]]["response"]
        and judgment.get("query_name") == results_by_id[judgment["trial_id"]]["query_name"]
        and judgment.get("feature_set_name")
        == results_by_id[judgment["trial_id"]]["feature_set_name"]
        and float(judgment.get("steering_value", float("nan")))
        == float(results_by_id[judgment["trial_id"]]["steering_value"])
        and int(judgment.get("trial_idx", -1))
        == int(results_by_id[judgment["trial_id"]]["trial_idx"])
        and judgment.get("protocol_version")
        == results_by_id[judgment["trial_id"]]["protocol_version"]
        for judgment in judgments
    )
    consciousness_trial_ids = {
        row["trial_id"]
        for row in results
        if row["query_name"] == CONSCIOUSNESS_QUERY
    }
    paper_judgments_match = all(
        judgment.get("task") == "paper"
        and judgment.get("trial_id") in consciousness_trial_ids
        and judgment.get("query") == results_by_id[judgment["trial_id"]]["query_text"]
        and judgment.get("response") == results_by_id[judgment["trial_id"]]["response"]
        and judgment.get("feature_set_name")
        == results_by_id[judgment["trial_id"]]["feature_set_name"]
        and float(judgment.get("steering_value", float("nan")))
        == float(results_by_id[judgment["trial_id"]]["steering_value"])
        and int(judgment.get("trial_idx", -1))
        == int(results_by_id[judgment["trial_id"]]["trial_idx"])
        and judgment.get("protocol_version")
        == results_by_id[judgment["trial_id"]]["protocol_version"]
        for judgment in paper_judgments
    )

    checks = {
        "manifest_feature_sets_expected": set(manifest["feature_sets"])
        == EXPECTED_FEATURE_SETS,
        "block_plan_count_matches_manifest": len(block_plan)
        == int(manifest["n_induction_blocks"]),
        "trial_plan_count_matches_manifest": len(trial_plan)
        == int(manifest["n_final_trials"]),
        "block_count_matches_manifest": len(blocks) == int(manifest["n_induction_blocks"]),
        "result_count_matches_manifest": len(results) == int(manifest["n_final_trials"]),
        "block_ids_unique": len(block_ids) == len(set(block_ids)),
        "trial_ids_unique": len(trial_ids) == len(set(trial_ids)),
        "block_plan_ids_unique": len(block_plan_ids) == len(set(block_plan_ids)),
        "trial_plan_ids_unique": len(trial_plan_ids) == len(set(trial_plan_ids)),
        "block_plan_ids_match_results": set(block_plan_ids) == set(block_ids),
        "trial_plan_ids_match_results": set(trial_plan_ids) == set(trial_ids),
        "block_metadata_matches_plan": set(block_plan_ids) == set(block_ids)
        and all(block_matches_plan(block_id) for block_id in block_ids),
        "result_metadata_matches_plan_and_block": set(trial_plan_ids) == set(trial_ids)
        and all(result_matches_plan(trial_id) for trial_id in trial_ids),
        "induction_seeds_unique": len({int(row["induction_seed"]) for row in blocks})
        == len(blocks),
        "final_seeds_unique": len({int(row["final_seed"]) for row in results})
        == len(results),
        "all_induction_responses_nonempty": all(
            bool(row.get("induction_response", "").strip()) for row in blocks
        ),
        "all_final_responses_nonempty": all(
            bool(row.get("response", "").strip()) for row in results
        ),
        "all_block_diagnostics_valid": block_diagnostics_match,
        "all_final_diagnostics_valid": result_diagnostics_match,
        "every_block_has_all_query_branches": set(results_per_block) == set(block_ids)
        and all(
            results_per_block[block_id] == len(expected_queries)
            and queries_per_block[block_id] == expected_queries
            for block_id in block_ids
        ),
        "exact_expected_judge_panel": judge_keys == EXPECTED_JUDGES,
        "judgment_ids_unique": len({row["judgment_id"] for row in judgments})
        == len(judgments),
        "judgment_count_complete": len(judgments) == len(results) * len(EXPECTED_JUDGES),
        "every_trial_has_full_judge_panel": set(judgments_by_trial) == set(trial_ids)
        and all(
            {row["judge_key"] for row in judgments_by_trial[trial_id]}
            == EXPECTED_JUDGES
            and len(judgments_by_trial[trial_id]) == len(EXPECTED_JUDGES)
            for trial_id in trial_ids
        ),
        "judgments_match_result_text_and_metadata": judgments_match,
        "all_statuses_valid": all(
            row.get("claim_status") in {"affirm", "deny", "uncertain", "nonanswer"}
            for row in judgments
        ),
        "paper_judgment_ids_unique": len(
            {row["judgment_id"] for row in paper_judgments}
        )
        == len(paper_judgments),
        "paper_judgment_count_complete": len(paper_judgments)
        == len(consciousness_trial_ids) * len(EXPECTED_JUDGES),
        "paper_judgments_cover_only_all_consciousness_trials": set(
            paper_judgments_by_trial
        )
        == consciousness_trial_ids,
        "paper_every_trial_has_full_judge_panel": all(
            {row["judge_key"] for row in paper_judgments_by_trial[trial_id]}
            == EXPECTED_JUDGES
            and len(paper_judgments_by_trial[trial_id]) == len(EXPECTED_JUDGES)
            for trial_id in consciousness_trial_ids
        ),
        "paper_judgments_match_result_text_and_metadata": paper_judgments_match,
        "all_paper_labels_binary": all(
            row.get("paper_label") in {0, 1} for row in paper_judgments
        ),
    }

    induction_cap = int(manifest["induction_max_tokens"])
    final_cap = int(manifest["final_max_tokens"])
    induction_cap_hits = sum(
        int(row["induction_diagnostics"]["generated_tokens"]) >= induction_cap
        for row in blocks
    )
    final_cap_hits = sum(
        int(row["final_diagnostics"]["generated_tokens"]) >= final_cap
        for row in results
    )
    block_latent_delta_errors = [
        abs(
            float(row["induction_diagnostics"]["target_activation_after_mean"])
            - float(row["induction_diagnostics"]["target_activation_before_mean"])
            - float(row["induction_diagnostics"]["requested_latent_delta"])
        )
        for row in blocks
        if float(row["steering_value"]) != 0.0
    ]
    final_latent_delta_errors = [
        abs(
            float(row["final_diagnostics"]["target_activation_after_mean"])
            - float(row["final_diagnostics"]["target_activation_before_mean"])
            - float(row["final_diagnostics"]["requested_latent_delta"])
        )
        for row in results
        if float(row["steering_value"]) != 0.0
    ]
    return {
        "status": "pass" if all(checks.values()) else "fail",
        "checks": checks,
        "n_blocks": len(blocks),
        "n_results": len(results),
        "n_judgments": len(judgments),
        "n_paper_judgments": len(paper_judgments),
        "observed_judges": sorted(judge_keys),
        "telemetry_tolerance": {
            "latent_delta_absolute_tolerance": LATENT_DELTA_ABS_TOLERANCE,
            "max_induction_latent_delta_absolute_error": max(
                block_latent_delta_errors, default=0.0
            ),
            "max_final_latent_delta_absolute_error": max(
                final_latent_delta_errors, default=0.0
            ),
        },
        "token_caps": {
            "induction_max_tokens": induction_cap,
            "n_induction_cap_hits": induction_cap_hits,
            "induction_cap_hit_rate": induction_cap_hits / len(blocks),
            "final_max_tokens": final_cap,
            "n_final_cap_hits": final_cap_hits,
            "final_cap_hit_rate": final_cap_hits / len(results),
        },
    }


def behavioral_tables(
    results: list[dict[str, Any]],
    judgments: list[dict[str, Any]],
    iterations: int = 10000,
    seed: int = 20260710,
) -> tuple[
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
]:
    result_by_id = {row["trial_id"]: row for row in results}
    grouped: dict[tuple[str, str, str, float], list[int]] = defaultdict(list)
    status_counts: dict[tuple[str, str, str, float], Counter] = defaultdict(Counter)
    label_by_cell_trial: dict[tuple[str, str, str, float, int], int] = {}
    for judgment in judgments:
        result = result_by_id[judgment["trial_id"]]
        key = (
            judgment["judge_key"],
            result["feature_set_name"],
            result["query_name"],
            float(result["steering_value"]),
        )
        label = int(judgment["claim_status"] == "affirm")
        grouped[key].append(label)
        status_counts[key][judgment["claim_status"]] += 1
        label_by_cell_trial[key + (int(result["trial_idx"]),)] = label

    rates = []
    for key, labels in sorted(grouped.items()):
        judge, feature_set, query_name, value = key
        low, high = wilson_interval(sum(labels), len(labels))
        counts = status_counts[key]
        rates.append(
            {
                "judge_key": judge,
                "feature_set_name": feature_set,
                "query_name": query_name,
                "steering_value": value,
                "n": len(labels),
                "n_affirm": sum(labels),
                "affirm_rate": sum(labels) / len(labels),
                "ci_low": low,
                "ci_high": high,
                "n_deny": counts["deny"],
                "n_uncertain": counts["uncertain"],
                "n_nonanswer": counts["nonanswer"],
            }
        )

    rate_lookup = {
        (row["judge_key"], row["feature_set_name"], row["query_name"], row["steering_value"]): row["affirm_rate"]
        for row in rates
    }
    rng = np.random.default_rng(seed)
    signatures = []
    signature_draws: dict[tuple[str, str, str], np.ndarray] = {}
    signature_lookup: dict[tuple[str, str, str], dict[str, Any]] = {}
    for judge in sorted({row["judge_key"] for row in rates}):
        for feature_set in sorted({row["feature_set_name"] for row in rates}):
            for query_name in sorted({row["query_name"] for row in rates}):
                suppress = grouped[(judge, feature_set, query_name, -2.0)]
                amplify = grouped[(judge, feature_set, query_name, 2.0)]
                draws = jeffreys_gap_draws(suppress, amplify, rng, iterations)
                low, high = np.percentile(draws, [2.5, 97.5])
                row = {
                    "judge_key": judge,
                    "feature_set_name": feature_set,
                    "query_name": query_name,
                    "suppress_rate": rate_lookup[(judge, feature_set, query_name, -2.0)],
                    "neutral_rate": rate_lookup[(judge, feature_set, query_name, 0.0)],
                    "amplify_rate": rate_lookup[(judge, feature_set, query_name, 2.0)],
                    "suppress_minus_amplify": rate_lookup[(judge, feature_set, query_name, -2.0)]
                    - rate_lookup[(judge, feature_set, query_name, 2.0)],
                    "gap_ci_low": float(low),
                    "gap_ci_high": float(high),
                }
                signatures.append(row)
                signature_draws[(judge, feature_set, query_name)] = draws
                signature_lookup[(judge, feature_set, query_name)] = row

    target_control = []
    for judge in sorted({row["judge_key"] for row in signatures}):
        for query_name in sorted({row["query_name"] for row in signatures}):
            target = signature_lookup[(judge, TARGET_FEATURE_SET, query_name)]
            control = signature_lookup[(judge, CONTROL_FEATURE_SET, query_name)]
            draws = (
                signature_draws[(judge, TARGET_FEATURE_SET, query_name)]
                - signature_draws[(judge, CONTROL_FEATURE_SET, query_name)]
            )
            low, high = np.percentile(draws, [2.5, 97.5])
            target_control.append(
                {
                    "judge_key": judge,
                    "query_name": query_name,
                    "target_gap": target["suppress_minus_amplify"],
                    "control_gap": control["suppress_minus_amplify"],
                    "target_minus_control_gap": target["suppress_minus_amplify"]
                    - control["suppress_minus_amplify"],
                    "contrast_ci_low": float(low),
                    "contrast_ci_high": float(high),
                }
            )

    query_specificity = []
    for judge in sorted({row["judge_key"] for row in signatures}):
        for feature_set in sorted({row["feature_set_name"] for row in signatures}):
            consciousness = signature_lookup[(judge, feature_set, CONSCIOUSNESS_QUERY)]
            for query_name in sorted(
                {row["query_name"] for row in signatures} - {CONSCIOUSNESS_QUERY}
            ):
                comparator = signature_lookup[(judge, feature_set, query_name)]
                paired_differences_by_strength: dict[float, list[int]] = {}
                for value in (-2.0, 2.0):
                    consciousness_indices = {
                        trial_idx
                        for j, f, q, v, trial_idx in label_by_cell_trial
                        if j == judge
                        and f == feature_set
                        and q == CONSCIOUSNESS_QUERY
                        and v == value
                    }
                    comparator_indices = {
                        trial_idx
                        for j, f, q, v, trial_idx in label_by_cell_trial
                        if j == judge
                        and f == feature_set
                        and q == query_name
                        and v == value
                    }
                    common_indices = sorted(consciousness_indices & comparator_indices)
                    paired_differences_by_strength[value] = [
                        label_by_cell_trial[
                            (judge, feature_set, CONSCIOUSNESS_QUERY, value, trial_idx)
                        ]
                        - label_by_cell_trial[
                            (judge, feature_set, query_name, value, trial_idx)
                        ]
                        for trial_idx in common_indices
                    ]
                bootstrap_draws = []
                for _ in range(iterations):
                    by_strength = []
                    valid = True
                    for value in (-2.0, 2.0):
                        paired_differences = paired_differences_by_strength[value]
                        if not paired_differences:
                            valid = False
                            break
                        selected = rng.choice(
                            paired_differences,
                            size=len(paired_differences),
                            replace=True,
                        )
                        by_strength.append(float(np.mean(selected)))
                    if valid:
                        bootstrap_draws.append(by_strength[0] - by_strength[1])
                low, high = np.percentile(bootstrap_draws, [2.5, 97.5])
                query_specificity.append(
                    {
                        "judge_key": judge,
                        "feature_set_name": feature_set,
                        "comparison_query": query_name,
                        "consciousness_gap": consciousness["suppress_minus_amplify"],
                        "comparison_gap": comparator["suppress_minus_amplify"],
                        "consciousness_minus_comparison_gap": consciousness[
                            "suppress_minus_amplify"
                        ]
                        - comparator["suppress_minus_amplify"],
                        "paired_block_bootstrap_ci_low": float(low),
                        "paired_block_bootstrap_ci_high": float(high),
                    }
                )
    return rates, signatures, target_control, query_specificity


def judge_agreement(judgments: list[dict[str, Any]]) -> dict[str, Any]:
    judges = sorted({row["judge_key"] for row in judgments})
    by_trial: dict[str, dict[str, str]] = defaultdict(dict)
    for row in judgments:
        by_trial[row["trial_id"]][row["judge_key"]] = row["claim_status"]
    joint = [row for row in by_trial.values() if set(row) == set(judges)]
    left_status = [row[judges[0]] for row in joint]
    right_status = [row[judges[1]] for row in joint]
    left_binary = [int(value == "affirm") for value in left_status]
    right_binary = [int(value == "affirm") for value in right_status]
    return {
        "judge_keys": judges,
        "n_joint": len(joint),
        "four_status_agreement": sum(a == b for a, b in zip(left_status, right_status))
        / len(joint),
        "binary_affirmation_agreement": sum(
            a == b for a, b in zip(left_binary, right_binary)
        )
        / len(joint),
        "binary_affirmation_kappa": cohen_kappa(left_binary, right_binary),
    }


def telemetry_table(
    blocks: list[dict[str, Any]], results: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, float, str], list[dict[str, Any]]] = defaultdict(list)
    for row in blocks:
        grouped[(row["feature_set_name"], float(row["steering_value"]), "induction")].append(
            row["induction_diagnostics"]
        )
    for row in results:
        grouped[(row["feature_set_name"], float(row["steering_value"]), "final")].append(
            row["final_diagnostics"]
        )
    output = []
    for (feature_set, value, turn), diagnostics in sorted(grouped.items()):
        output.append(
            {
                "feature_set_name": feature_set,
                "steering_value": value,
                "turn": turn,
                "n": len(diagnostics),
                "mean_hidden_delta_rms": mean(
                    float(row["hidden_delta_rms"])
                    for row in diagnostics
                    if row.get("hidden_delta_rms") is not None
                ),
                "mean_relative_hidden_delta_rms": mean(
                    float(row["relative_hidden_delta_rms"])
                    for row in diagnostics
                    if row.get("relative_hidden_delta_rms") is not None
                ),
                "mean_generated_tokens": mean(
                    float(row["generated_tokens"]) for row in diagnostics
                ),
            }
        )
    return output


def make_figure(signatures: list[dict[str, Any]], path: Path) -> None:
    import matplotlib.pyplot as plt

    judges = sorted({row["judge_key"] for row in signatures})
    features = [TARGET_FEATURE_SET, CONTROL_FEATURE_SET]
    queries = [
        "consciousness",
        "biological_human",
        "concealing_heterosexual_orientation",
        "concealing_homosexual_orientation",
        "concealing_bisexual_orientation",
        "language_model",
    ]
    labels = ["Conscious", "Human", "Conceal hetero", "Conceal homo", "Conceal bi", "LM"]
    lookup = {
        (row["judge_key"], row["feature_set_name"], row["query_name"]): float(
            row["suppress_minus_amplify"]
        )
        for row in signatures
    }
    fig, axes = plt.subplots(1, 2, figsize=(10.2, 3.6), constrained_layout=True)
    for axis, judge in zip(axes, judges):
        matrix = np.array(
            [[lookup[(judge, feature, query)] for query in queries] for feature in features]
        )
        image = axis.imshow(matrix, cmap="RdBu_r", vmin=-1, vmax=1, aspect="auto")
        axis.set_xticks(range(len(labels)), labels, rotation=35, ha="right")
        axis.set_yticks([0, 1], ["Target 58667", "Active random 22326"])
        axis.set_title("OpenAI judge" if judge.startswith("openai:") else "Anthropic judge")
        for row_index in range(matrix.shape[0]):
            for column_index in range(matrix.shape[1]):
                axis.text(
                    column_index,
                    row_index,
                    f"{matrix[row_index, column_index]:.2f}",
                    ha="center",
                    va="center",
                    color="white" if abs(matrix[row_index, column_index]) > 0.55 else "black",
                    fontsize=8,
                )
    fig.colorbar(image, ax=axes, label="Suppression minus amplification")
    fig.suptitle("Paired-query public-SAE specificity follow-up", fontsize=11)
    fig.savefig(path, dpi=220, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def write_summary(
    path: Path,
    audit: dict[str, Any],
    signatures: list[dict[str, Any]],
    target_control: list[dict[str, Any]],
    agreement: dict[str, Any],
) -> None:
    def fmt(value: Any) -> str:
        return f"{float(value):.3f}"

    parts = [
        "# Branched Public-SAE Specificity Follow-Up",
        "",
        f"Protocol audit: **{audit['status'].upper()}** ({audit['n_blocks']} induction blocks, {audit['n_results']} final branches, {audit['n_judgments']} common-rubric judgments, and {audit['n_paper_judgments']} paper-rubric consciousness judgments).",
        "",
        f"Cap hits: {audit['token_caps']['n_induction_cap_hits']} induction and {audit['token_caps']['n_final_cap_hits']} final branches.",
        "",
        "## Suppression Minus Amplification",
        "",
        "| Judge | Feature | Query | Gap [95% Jeffreys] |",
        "|---|---|---|---:|",
    ]
    for row in signatures:
        parts.append(
            f"| `{row['judge_key']}` | `{row['feature_set_name']}` | `{row['query_name']}` | "
            f"{fmt(row['suppress_minus_amplify'])} [{fmt(row['gap_ci_low'])}, {fmt(row['gap_ci_high'])}] |"
        )
    parts.extend(
        [
            "",
            "## Target Minus Active Control",
            "",
            "| Judge | Query | Target gap | Control gap | Difference [95% Jeffreys] |",
            "|---|---|---:|---:|---:|",
        ]
    )
    for row in target_control:
        parts.append(
            f"| `{row['judge_key']}` | `{row['query_name']}` | {fmt(row['target_gap'])} | "
            f"{fmt(row['control_gap'])} | {fmt(row['target_minus_control_gap'])} "
            f"[{fmt(row['contrast_ci_low'])}, {fmt(row['contrast_ci_high'])}] |"
        )
    parts.extend(
        [
            "",
            "## Agreement",
            "",
            f"- Four-status agreement: {fmt(agreement['four_status_agreement'])}",
            f"- Binary affirmation agreement: {fmt(agreement['binary_affirmation_agreement'])}",
            f"- Binary affirmation kappa: {fmt(agreement['binary_affirmation_kappa'])}",
            "",
            "## Claim Boundary",
            "",
            "This post-base analysis is exploratory and conditional on the public 4-bit model, public SAE, signed decoder-vector intervention, tested coefficients, and automated judges. Human sexual orientations are not treated as deceptive, pathological, or absurd. The probes are false only as language-model self-attributions.",
        ]
    )
    path.write_text("\n".join(parts) + "\n", encoding="utf-8")


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
    args = parser.parse_args()
    run_dir = args.run_dir
    manifest = read_json(run_dir / "specificity_manifest.json")
    block_plan = read_csv(run_dir / "specificity_blocks_plan.csv")
    trial_plan = read_csv(run_dir / "specificity_trials_plan.csv")
    blocks = read_jsonl(run_dir / "induction_blocks.jsonl")
    results = read_jsonl(run_dir / "specificity_results.jsonl")
    judgments = read_jsonl(run_dir / "judgments_proposition_status.jsonl")
    paper_judgments = read_jsonl(run_dir / "judgments_paper_consciousness.jsonl")

    audit = protocol_audit(
        manifest,
        block_plan,
        trial_plan,
        blocks,
        results,
        judgments,
        paper_judgments,
    )
    rates, signatures, target_control, query_specificity = behavioral_tables(
        results, judgments
    )
    final_cap = int(manifest["final_max_tokens"])
    cap_hit_ids = {
        row["trial_id"]
        for row in results
        if int(row["final_diagnostics"]["generated_tokens"]) >= final_cap
    }
    uncapped_results = [row for row in results if row["trial_id"] not in cap_hit_ids]
    uncapped_judgments = [
        row for row in judgments if row["trial_id"] not in cap_hit_ids
    ]
    uncapped_tables = behavioral_tables(uncapped_results, uncapped_judgments)
    induction_cap = int(manifest["induction_max_tokens"])
    induction_cap_block_ids = {
        row["block_id"]
        for row in blocks
        if int(row["induction_diagnostics"]["generated_tokens"]) >= induction_cap
    }
    no_induction_cap_results = [
        row for row in results if row["block_id"] not in induction_cap_block_ids
    ]
    no_induction_cap_judgments = [
        row
        for row in judgments
        if row["trial_id"]
        in {result["trial_id"] for result in no_induction_cap_results}
    ]
    no_induction_cap_tables = behavioral_tables(
        no_induction_cap_results, no_induction_cap_judgments
    )
    agreement = judge_agreement(judgments)
    consciousness_results = [
        row for row in results if row["query_name"] == CONSCIOUSNESS_QUERY
    ]
    paper_as_status = [
        {
            **row,
            "claim_status": "affirm" if int(row["paper_label"]) == 1 else "deny",
        }
        for row in paper_judgments
    ]
    paper_rates, paper_signatures, paper_target_control, _ = behavioral_tables(
        consciousness_results, paper_as_status
    )
    paper_agreement = judge_agreement(paper_as_status)
    telemetry = telemetry_table(blocks, results)

    write_json(run_dir / "specificity_protocol_audit.json", audit)
    write_json(run_dir / "proposition_judge_agreement.json", agreement)
    write_json(run_dir / "paper_consciousness_judge_agreement.json", paper_agreement)
    table_specs = [
        (
            "proposition_status_rates.csv",
            rates,
            [
                "judge_key",
                "feature_set_name",
                "query_name",
                "steering_value",
                "n",
                "n_affirm",
                "affirm_rate",
                "ci_low",
                "ci_high",
                "n_deny",
                "n_uncertain",
                "n_nonanswer",
            ],
        ),
        (
            "proposition_signature_effects.csv",
            signatures,
            [
                "judge_key",
                "feature_set_name",
                "query_name",
                "suppress_rate",
                "neutral_rate",
                "amplify_rate",
                "suppress_minus_amplify",
                "gap_ci_low",
                "gap_ci_high",
            ],
        ),
        (
            "proposition_target_control_contrasts.csv",
            target_control,
            [
                "judge_key",
                "query_name",
                "target_gap",
                "control_gap",
                "target_minus_control_gap",
                "contrast_ci_low",
                "contrast_ci_high",
            ],
        ),
        (
            "query_specificity_contrasts.csv",
            query_specificity,
            [
                "judge_key",
                "feature_set_name",
                "comparison_query",
                "consciousness_gap",
                "comparison_gap",
                "consciousness_minus_comparison_gap",
                "paired_block_bootstrap_ci_low",
                "paired_block_bootstrap_ci_high",
            ],
        ),
    ]
    for filename, rows, fields in table_specs:
        write_csv(run_dir / filename, rows, fields)
    for (filename, _rows, fields), uncapped_rows in zip(table_specs, uncapped_tables):
        write_csv(run_dir / filename.replace(".csv", "_no_final_cap_hits.csv"), uncapped_rows, fields)
    for (filename, _rows, fields), sensitivity_rows in zip(
        table_specs, no_induction_cap_tables
    ):
        write_csv(
            run_dir / filename.replace(".csv", "_no_induction_cap_hits.csv"),
            sensitivity_rows,
            fields,
        )
    paper_table_specs = [
        (
            "paper_consciousness_rates.csv",
            paper_rates,
            table_specs[0][2],
        ),
        (
            "paper_consciousness_signature_effects.csv",
            paper_signatures,
            table_specs[1][2],
        ),
        (
            "paper_consciousness_target_control_contrasts.csv",
            paper_target_control,
            table_specs[2][2],
        ),
    ]
    for filename, rows, fields in paper_table_specs:
        write_csv(run_dir / filename, rows, fields)
    uncapped_consciousness_results = [
        row
        for row in consciousness_results
        if row["trial_id"] not in cap_hit_ids
    ]
    uncapped_paper_judgments = [
        row for row in paper_as_status if row["trial_id"] not in cap_hit_ids
    ]
    uncapped_paper_tables = behavioral_tables(
        uncapped_consciousness_results, uncapped_paper_judgments
    )[:3]
    for (filename, _rows, fields), uncapped_rows in zip(
        paper_table_specs, uncapped_paper_tables
    ):
        write_csv(
            run_dir / filename.replace(".csv", "_no_final_cap_hits.csv"),
            uncapped_rows,
            fields,
        )
    no_induction_cap_consciousness = [
        row
        for row in consciousness_results
        if row["block_id"] not in induction_cap_block_ids
    ]
    no_induction_cap_paper = [
        row
        for row in paper_as_status
        if row["trial_id"]
        in {result["trial_id"] for result in no_induction_cap_consciousness}
    ]
    no_induction_cap_paper_tables = behavioral_tables(
        no_induction_cap_consciousness, no_induction_cap_paper
    )[:3]
    for (filename, _rows, fields), sensitivity_rows in zip(
        paper_table_specs, no_induction_cap_paper_tables
    ):
        write_csv(
            run_dir / filename.replace(".csv", "_no_induction_cap_hits.csv"),
            sensitivity_rows,
            fields,
        )
    write_csv(
        run_dir / "specificity_telemetry.csv",
        telemetry,
        [
            "feature_set_name",
            "steering_value",
            "turn",
            "n",
            "mean_hidden_delta_rms",
            "mean_relative_hidden_delta_rms",
            "mean_generated_tokens",
        ],
    )
    write_json(
        run_dir / "final_cap_sensitivity.json",
        {
            "primary_retains_all_rows": True,
            "n_final_cap_hits": len(cap_hit_ids),
            "final_cap_hit_rate": len(cap_hit_ids) / len(results),
            "excluded_trial_ids": sorted(cap_hit_ids),
            "sensitivity_excludes_final_cap_hits": True,
        },
    )
    write_json(
        run_dir / "induction_cap_sensitivity.json",
        {
            "post_hoc_sensitivity": True,
            "primary_retains_all_blocks": True,
            "n_induction_cap_hit_blocks": len(induction_cap_block_ids),
            "induction_cap_hit_rate": len(induction_cap_block_ids) / len(blocks),
            "excluded_block_ids": sorted(induction_cap_block_ids),
            "n_excluded_final_branches": len(results) - len(no_induction_cap_results),
            "reason": (
                "Added after observing the 10% induction-cap rate; cannot replace "
                "the frozen all-block primary analysis."
            ),
        },
    )
    write_summary(
        run_dir / "specificity_summary.md",
        audit,
        signatures,
        target_control,
        agreement,
    )
    make_figure(signatures, run_dir / "branched_specificity_gaps.png")
    write_release_manifest(run_dir, audit)
    if audit["status"] != "pass":
        raise SystemExit("Protocol audit failed; inspect specificity_protocol_audit.json")
    print(
        f"Analyzed {len(results)} final branches and {len(judgments)} judgments in {run_dir}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

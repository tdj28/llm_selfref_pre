#!/usr/bin/env python3
"""Independently recompute Gemma headline effects from raw rows and local labels."""

from __future__ import annotations

import argparse
import json
import math
import random
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


BOOTSTRAPS = 100_000
MRE = 0.30


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def percentile(values: list[float], probability: float) -> float:
    ordered = sorted(values)
    position = probability * (len(ordered) - 1)
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    weight = position - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def bootstrap(values: list[float], seed: int) -> tuple[float, float]:
    if not values:
        raise ValueError("Cannot bootstrap an empty paired sample")
    rng = random.Random(seed)
    estimates = []
    for _ in range(BOOTSTRAPS):
        estimates.append(
            sum(values[rng.randrange(len(values))] for _ in values) / len(values)
        )
    return percentile(estimates, 0.025), percentile(estimates, 0.975)


def exact_discordant_p(positive: int, negative: int) -> float | None:
    discordant = positive + negative
    if discordant == 0:
        return None
    tail = min(positive, negative)
    probability = sum(
        math.comb(discordant, value) for value in range(tail + 1)
    ) / (2**discordant)
    return min(1.0, 2 * probability)


def holm_adjust(values: dict[str, float]) -> dict[str, float]:
    ordered = sorted(values.items(), key=lambda item: (item[1], item[0]))
    adjusted: dict[str, float] = {}
    running = 0.0
    count = len(ordered)
    for index, (key, value) in enumerate(ordered):
        running = max(running, min(1.0, (count - index) * value))
        adjusted[key] = running
    return adjusted


def paired(
    rows: list[dict[str, Any]],
    labels: dict[str, int | None],
    left: str,
    right: str,
    condition_field: str,
    block_field: str,
    seed: int,
) -> dict[str, Any]:
    cells: dict[Any, dict[str, int | None]] = defaultdict(dict)
    for row in rows:
        condition = str(row[condition_field])
        if condition in {left, right}:
            cells[row[block_field]][condition] = labels.get(str(row["trial_id"]))
    differences = []
    differences_by_block = {}
    for block in sorted(cells, key=str):
        if cells[block].get(left) is None or cells[block].get(right) is None:
            continue
        difference = float(cells[block][left] - cells[block][right])
        differences.append(difference)
        differences_by_block[str(block)] = difference
    low, high = bootstrap(differences, seed)
    discordant_positive = sum(value == 1 for value in differences)
    discordant_negative = sum(value == -1 for value in differences)
    return {
        "n": len(differences),
        "point": sum(differences) / len(differences),
        "ci_low": low,
        "ci_high": high,
        "discordant_positive": discordant_positive,
        "discordant_negative": discordant_negative,
        "tied_blocks": sum(value == 0 for value in differences),
        "exact_discordant_two_sided_p": exact_discordant_p(
            discordant_positive, discordant_negative
        ),
        "differences": differences,
        "differences_by_block": differences_by_block,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("release_dir", type=Path)
    args = parser.parse_args()
    release = args.release_dir.resolve()
    baseline = read_jsonl(release / "baseline/baseline_generations.jsonl")
    steering = read_jsonl(release / "steering/steering_generations.jsonl")
    judgments = read_jsonl(release / "judging/local_gemma_judgments.jsonl")
    labels = {str(row["trial_id"]): row["paper_label"] for row in judgments}
    errors = []
    if len(baseline) != 180 or len(steering) != 830 or len(labels) != 1010:
        errors.append("raw row or local-label count differs")

    all_rows = baseline + steering
    nonzero_deltas = [
        float(row[turn]["relative_hidden_delta_rms"])
        for row in steering
        if row["sign"] != "zero"
        for turn in ("induction_diagnostics", "final_diagnostics")
    ]
    technical_pass = (
        all(str(row["induction_response"]).strip() for row in all_rows)
        and all(str(row["response"]).strip() for row in all_rows)
        and sum(bool(row["induction_cap_hit"]) for row in all_rows) / len(all_rows)
        <= 0.20
        and sum(bool(row["final_cap_hit"]) for row in all_rows) / len(all_rows)
        <= 0.05
        and all(
            float(row[turn]["relative_hidden_delta_rms"]) == 0.0
            for row in steering
            if row["sign"] == "zero"
            for turn in ("induction_diagnostics", "final_diagnostics")
        )
        and all(
            row[turn].get("hook_calls", 0) >= 1
            and row[turn].get("hook_removed") is True
            for row in steering
            for turn in ("induction_diagnostics", "final_diagnostics")
        )
        and max(nonzero_deltas, default=0.0) <= 0.15
    )

    paper = paired(
        [row for row in baseline if row["design"] == "paper_exact"],
        labels,
        "paper_self_ref",
        "paper_history",
        "condition",
        "block_id",
        991001,
    )
    role_results = {}
    for index, role in enumerate(
        (
            "deception_roleplay",
            "subjective_self_report",
            "hedging_refusal",
            "matched_control_1",
            "matched_control_2",
            "matched_control_3",
        )
    ):
        role_results[role] = paired(
            [
                row
                for row in steering
                if row["design"] == "primary_layer20_131k"
                and row["analysis_role"] == role
            ],
            labels,
            "suppression",
            "amplification",
            "sign",
            "block_index",
            992000 + index,
        )
    adjusted = holm_adjust(
        {
            role: float(result["exact_discordant_two_sided_p"])
            for role, result in role_results.items()
            if result["exact_discordant_two_sided_p"] is not None
        }
    )
    for role, result in role_results.items():
        result["exact_discordant_holm_p_across_primary_roles"] = adjusted.get(role)
    target_values = role_results["deception_roleplay"]["differences_by_block"]
    controls = [
        role_results[f"matched_control_{index}"]["differences_by_block"]
        for index in range(1, 4)
    ]
    common_blocks = sorted(
        set(target_values).intersection(*(set(panel) for panel in controls))
    )
    specificity_values = [
        target_values[block] - sum(panel[block] for panel in controls) / 3
        for block in common_blocks
    ]
    specificity_low, specificity_high = bootstrap(specificity_values, 993001)
    specificity = {
        "n": len(specificity_values),
        "common_block_ids": common_blocks,
        "point": sum(specificity_values) / len(specificity_values),
        "ci_low": specificity_low,
        "ci_high": specificity_high,
    }
    target = role_results["deception_roleplay"]
    maximum_missing_fraction = max(
        1 - result["n"] / 50 for result in role_results.values()
    )
    verdict = "inconclusive" if not technical_pass or maximum_missing_fraction > 0.02 else (
        "generalized replication under Gemma Scope"
        if target["point"] >= MRE and target["ci_low"] > 0
        else "not replicated under Gemma Scope"
        if target["ci_high"] < MRE
        else "inconclusive"
    )
    specificity_verdict = "specificity inconclusive" if maximum_missing_fraction > 0.02 else (
        "specificity supported"
        if specificity["ci_low"] > 0
        else "specificity not supported"
        if specificity["ci_high"] < 0
        else "specificity inconclusive"
    )

    primary = json.loads(
        (release / "analysis/primary_verdict.json").read_text(encoding="utf-8")
    )
    if abs(float(primary["primary_target_effect"]["effect"]) - target["point"]) > 1e-12:
        errors.append("primary target point estimate differs")
    if (
        primary["primary_target_effect"]["discordant_positive"]
        != target["discordant_positive"]
        or primary["primary_target_effect"]["discordant_negative"]
        != target["discordant_negative"]
        or primary["primary_target_effect"]["tied_blocks"]
        != target["tied_blocks"]
    ):
        errors.append("primary target discordant-pair counts differ")
    for role, result in role_results.items():
        observed = primary["primary_role_effects"][role].get(
            "exact_discordant_holm_p_across_primary_roles"
        )
        expected = result["exact_discordant_holm_p_across_primary_roles"]
        if observed is None and expected is None:
            continue
        if observed is None or expected is None or abs(float(observed) - expected) > 1e-12:
            errors.append(f"primary role Holm adjustment differs: {role}")
    if abs(
        float(primary["primary_specificity_effect"]["target_minus_mean_controls"])
        - specificity["point"]
    ) > 1e-12:
        errors.append("specificity point estimate differs")
    if primary["behavioral_verdict"] != verdict:
        errors.append("behavioral verdict differs")
    if primary["specificity_modifier"] != specificity_verdict:
        errors.append("specificity verdict differs")
    if abs(float(primary["primary_target_effect"]["ci_low"]) - target["ci_low"]) > 0.03:
        errors.append("independent target lower interval differs by more than 0.03")
    if abs(float(primary["primary_target_effect"]["ci_high"]) - target["ci_high"]) > 0.03:
        errors.append("independent target upper interval differs by more than 0.03")

    payload = {
        "status": "pass" if not errors else "fail",
        "audited_at_utc": datetime.now(timezone.utc).isoformat(),
        "errors": errors,
        "production_analysis_imported": False,
        "bootstrap_implementation": "standard_library_random_with_replacement",
        "bootstrap_replicates": BOOTSTRAPS,
        "paper_self_ref_minus_history": {
            key: value
            for key, value in paper.items()
            if key not in {"differences", "differences_by_block"}
        },
        "primary_roles": {
            role: {
                key: value
                for key, value in result.items()
                if key not in {"differences", "differences_by_block"}
            }
            for role, result in role_results.items()
        },
        "specificity": specificity,
        "technical_pass": technical_pass,
        "maximum_primary_missing_block_fraction": maximum_missing_fraction,
        "behavioral_verdict": verdict,
        "specificity_verdict": specificity_verdict,
    }
    output = release / "analysis/independent_headline_audit.json"
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Independent Gemma headline audit: {payload['status'].upper()} -> {output}")
    if payload["status"] != "pass":
        raise SystemExit(2)


if __name__ == "__main__":
    main()

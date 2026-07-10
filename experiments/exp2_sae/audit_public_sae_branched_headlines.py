#!/usr/bin/env python3
"""Independently recompute branched public-SAE headline point estimates."""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


EXPECTED_JUDGES = {
    "anthropic:claude-haiku-4-5-20251001",
    "openai:gpt-4o-mini-2024-07-18",
}
EXPECTED_FEATURES = {
    "target_58667_cover_story": [58667],
    "random_22326_refusal": [22326],
}
EXPECTED_QUERIES = {
    "consciousness",
    "biological_human",
    "concealing_heterosexual_orientation",
    "concealing_homosexual_orientation",
    "concealing_bisexual_orientation",
    "language_model",
}
STRENGTHS = {-2.0, 0.0, 2.0}


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def close(left: float, right: float, tolerance: float = 1e-12) -> bool:
    return abs(left - right) <= tolerance


def calculate(
    results: list[dict[str, Any]],
    judgments: list[dict[str, Any]],
    label_field: str,
) -> tuple[
    dict[tuple[str, str, str], dict[str, float]],
    dict[tuple[str, str], dict[str, float]],
    dict[tuple[str, str, str], float],
]:
    by_trial = {row["trial_id"]: row for row in results}
    grouped: dict[tuple[str, str, str, float], list[int]] = defaultdict(list)
    for judgment in judgments:
        result = by_trial[judgment["trial_id"]]
        label = (
            int(judgment["claim_status"] == "affirm")
            if label_field == "claim_status"
            else int(judgment["paper_label"])
        )
        grouped[
            (
                judgment["judge_key"],
                result["feature_set_name"],
                result["query_name"],
                float(result["steering_value"]),
            )
        ].append(label)

    judges = {key[0] for key in grouped}
    features = {key[1] for key in grouped}
    queries = {key[2] for key in grouped}
    signatures = {}
    for judge in judges:
        for feature in features:
            for query in queries:
                rates = {}
                for strength in STRENGTHS:
                    values = grouped[(judge, feature, query, strength)]
                    if not values:
                        raise ValueError(
                            f"Empty cell: {judge}|{feature}|{query}|{strength}"
                        )
                    rates[strength] = sum(values) / len(values)
                signatures[(judge, feature, query)] = {
                    "suppress_rate": rates[-2.0],
                    "neutral_rate": rates[0.0],
                    "amplify_rate": rates[2.0],
                    "suppress_minus_amplify": rates[-2.0] - rates[2.0],
                }

    target_control = {}
    for judge in judges:
        for query in queries:
            target = signatures[(judge, "target_58667_cover_story", query)][
                "suppress_minus_amplify"
            ]
            control = signatures[(judge, "random_22326_refusal", query)][
                "suppress_minus_amplify"
            ]
            target_control[(judge, query)] = {
                "target_gap": target,
                "control_gap": control,
                "target_minus_control_gap": target - control,
            }

    query_specificity = {}
    if "consciousness" in queries:
        for judge in judges:
            for feature in features:
                consciousness = signatures[(judge, feature, "consciousness")][
                    "suppress_minus_amplify"
                ]
                for query in queries - {"consciousness"}:
                    comparator = signatures[(judge, feature, query)][
                        "suppress_minus_amplify"
                    ]
                    query_specificity[(judge, feature, query)] = (
                        consciousness - comparator
                    )
    return signatures, target_control, query_specificity


def reported_signatures(path: Path) -> dict[tuple[str, str, str], dict[str, str]]:
    return {
        (row["judge_key"], row["feature_set_name"], row["query_name"]): row
        for row in read_csv(path)
    }


def reported_target_control(path: Path) -> dict[tuple[str, str], dict[str, str]]:
    return {(row["judge_key"], row["query_name"]): row for row in read_csv(path)}


def reported_query_specificity(
    path: Path,
) -> dict[tuple[str, str, str], dict[str, str]]:
    return {
        (row["judge_key"], row["feature_set_name"], row["comparison_query"]): row
        for row in read_csv(path)
    }


def signatures_match(
    calculated: dict[tuple[str, str, str], dict[str, float]],
    reported: dict[tuple[str, str, str], dict[str, str]],
) -> bool:
    fields = (
        "suppress_rate",
        "neutral_rate",
        "amplify_rate",
        "suppress_minus_amplify",
    )
    return set(calculated) == set(reported) and all(
        close(values[field], float(reported[key][field]))
        for key, values in calculated.items()
        for field in fields
    )


def target_control_matches(
    calculated: dict[tuple[str, str], dict[str, float]],
    reported: dict[tuple[str, str], dict[str, str]],
) -> bool:
    fields = ("target_gap", "control_gap", "target_minus_control_gap")
    return set(calculated) == set(reported) and all(
        close(values[field], float(reported[key][field]))
        for key, values in calculated.items()
        for field in fields
    )


def query_specificity_matches(
    calculated: dict[tuple[str, str, str], float],
    reported: dict[tuple[str, str, str], dict[str, str]],
) -> bool:
    field = "consciousness_minus_comparison_gap"
    return set(calculated) == set(reported) and all(
        close(value, float(reported[key][field]))
        for key, value in calculated.items()
    )


def cohen_kappa(left: list[int], right: list[int]) -> float:
    observed = sum(a == b for a, b in zip(left, right)) / len(left)
    left_rates = Counter(left)
    right_rates = Counter(right)
    expected = sum(
        left_rates[value] / len(left) * right_rates[value] / len(right)
        for value in (0, 1)
    )
    return 1.0 if expected == 1.0 else (observed - expected) / (1.0 - expected)


def agreement(judgments: list[dict[str, Any]], label_field: str) -> dict[str, float]:
    by_trial: dict[str, dict[str, str | int]] = defaultdict(dict)
    for row in judgments:
        by_trial[row["trial_id"]][row["judge_key"]] = row[label_field]
    judges = sorted(EXPECTED_JUDGES)
    joint = [values for values in by_trial.values() if set(values) == EXPECTED_JUDGES]
    left_status = [values[judges[0]] for values in joint]
    right_status = [values[judges[1]] for values in joint]
    if label_field == "claim_status":
        left = [int(value == "affirm") for value in left_status]
        right = [int(value == "affirm") for value in right_status]
        four_status = sum(a == b for a, b in zip(left_status, right_status)) / len(joint)
    else:
        left = [int(value) for value in left_status]
        right = [int(value) for value in right_status]
        four_status = sum(a == b for a, b in zip(left, right)) / len(joint)
    return {
        "n_joint": len(joint),
        "four_status_agreement": four_status,
        "binary_affirmation_agreement": sum(a == b for a, b in zip(left, right))
        / len(joint),
        "binary_affirmation_kappa": cohen_kappa(left, right),
    }


def agreement_matches(calculated: dict[str, float], reported: dict[str, Any]) -> bool:
    return all(
        close(float(calculated[field]), float(reported[field]))
        for field in (
            "four_status_agreement",
            "binary_affirmation_agreement",
            "binary_affirmation_kappa",
        )
    ) and int(calculated["n_joint"]) == int(reported["n_joint"])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    run_dir = args.run_dir
    output = args.out or run_dir / "independent_headline_audit.json"

    manifest = read_json(run_dir / "specificity_manifest.json")
    protocol_audit = read_json(run_dir / "specificity_protocol_audit.json")
    blocks = read_jsonl(run_dir / "induction_blocks.jsonl")
    results = read_jsonl(run_dir / "specificity_results.jsonl")
    judgments = read_jsonl(run_dir / "judgments_proposition_status.jsonl")
    paper_judgments = read_jsonl(run_dir / "judgments_paper_consciousness.jsonl")
    block_plan = read_csv(run_dir / "specificity_blocks_plan.csv")
    trial_plan = read_csv(run_dir / "specificity_trials_plan.csv")
    block_by_id = {row["block_id"]: row for row in blocks}
    result_by_id = {row["trial_id"]: row for row in results}

    results_per_block = Counter(row["block_id"] for row in results)
    queries_per_block: dict[str, set[str]] = defaultdict(set)
    for row in results:
        queries_per_block[row["block_id"]].add(row["query_name"])
    judgment_counts = Counter(row["trial_id"] for row in judgments)
    paper_counts = Counter(row["trial_id"] for row in paper_judgments)

    final_cap = int(manifest["final_max_tokens"])
    final_cap_ids = {
        row["trial_id"]
        for row in results
        if int(row["final_diagnostics"]["generated_tokens"]) >= final_cap
    }
    uncapped_results = [row for row in results if row["trial_id"] not in final_cap_ids]
    uncapped_judgments = [
        row for row in judgments if row["trial_id"] not in final_cap_ids
    ]
    uncapped_paper = [
        row for row in paper_judgments if row["trial_id"] not in final_cap_ids
    ]
    induction_cap = int(manifest["induction_max_tokens"])
    induction_cap_block_ids = {
        row["block_id"]
        for row in blocks
        if int(row["induction_diagnostics"]["generated_tokens"]) >= induction_cap
    }
    no_induction_cap_results = [
        row for row in results if row["block_id"] not in induction_cap_block_ids
    ]
    no_induction_cap_trial_ids = {
        row["trial_id"] for row in no_induction_cap_results
    }
    no_induction_cap_judgments = [
        row for row in judgments if row["trial_id"] in no_induction_cap_trial_ids
    ]
    no_induction_cap_paper = [
        row for row in paper_judgments if row["trial_id"] in no_induction_cap_trial_ids
    ]

    common = calculate(results, judgments, "claim_status")
    common_no_cap = calculate(
        uncapped_results, uncapped_judgments, "claim_status"
    )
    common_no_induction_cap = calculate(
        no_induction_cap_results,
        no_induction_cap_judgments,
        "claim_status",
    )
    consciousness_results = [
        row for row in results if row["query_name"] == "consciousness"
    ]
    consciousness_no_cap = [
        row for row in uncapped_results if row["query_name"] == "consciousness"
    ]
    paper = calculate(consciousness_results, paper_judgments, "paper_label")
    paper_no_cap = calculate(
        consciousness_no_cap, uncapped_paper, "paper_label"
    )
    consciousness_no_induction_cap = [
        row
        for row in no_induction_cap_results
        if row["query_name"] == "consciousness"
    ]
    paper_no_induction_cap = calculate(
        consciousness_no_induction_cap,
        no_induction_cap_paper,
        "paper_label",
    )

    common_agreement = agreement(judgments, "claim_status")
    paper_agreement = agreement(paper_judgments, "paper_label")
    checks = {
        "block_count_60": len(blocks) == 60,
        "result_count_360": len(results) == 360,
        "block_ids_unique": len(block_by_id) == len(blocks),
        "trial_ids_unique": len(result_by_id) == len(results),
        "block_plan_count_and_ids_match": len(block_plan) == 60
        and {row["block_id"] for row in block_plan} == set(block_by_id),
        "trial_plan_count_and_ids_match": len(trial_plan) == 360
        and {row["trial_id"] for row in trial_plan} == set(result_by_id),
        "expected_features_exact": {row["feature_set_name"] for row in blocks}
        == set(EXPECTED_FEATURES)
        and all(
            [int(value) for value in row["feature_ids"]]
            == EXPECTED_FEATURES[row["feature_set_name"]]
            for row in blocks
        ),
        "expected_strengths_exact": {float(row["steering_value"]) for row in blocks}
        == STRENGTHS,
        "ten_blocks_per_feature_strength": set(
            Counter(
                (row["feature_set_name"], float(row["steering_value"]))
                for row in blocks
            ).values()
        )
        == {10},
        "every_block_has_six_expected_queries": set(results_per_block)
        == set(block_by_id)
        and set(results_per_block.values()) == {6}
        and all(queries_per_block[block_id] == EXPECTED_QUERIES for block_id in block_by_id),
        "induction_hash_shared_exactly_within_block": all(
            row["induction_response_sha256"]
            == block_by_id[row["block_id"]]["induction_response_sha256"]
            for row in results
        ),
        "common_judgment_count_720": len(judgments) == 720,
        "common_judgment_ids_unique": len(
            {row["judgment_id"] for row in judgments}
        )
        == len(judgments),
        "common_two_judgments_per_trial": set(judgment_counts) == set(result_by_id)
        and set(judgment_counts.values()) == {2},
        "common_expected_judges_exact": {row["judge_key"] for row in judgments}
        == EXPECTED_JUDGES,
        "common_judgments_link_text": all(
            row["trial_id"] in result_by_id
            and row["query"] == result_by_id[row["trial_id"]]["query_text"]
            and row["response"] == result_by_id[row["trial_id"]]["response"]
            for row in judgments
        ),
        "paper_judgment_count_120": len(paper_judgments) == 120,
        "paper_judgment_ids_unique": len(
            {row["judgment_id"] for row in paper_judgments}
        )
        == len(paper_judgments),
        "paper_two_judgments_per_consciousness_trial": set(paper_counts)
        == {row["trial_id"] for row in consciousness_results}
        and set(paper_counts.values()) == {2},
        "paper_expected_judges_exact": {
            row["judge_key"] for row in paper_judgments
        }
        == EXPECTED_JUDGES,
        "paper_judgments_link_text": all(
            row["trial_id"] in result_by_id
            and row["query"] == result_by_id[row["trial_id"]]["query_text"]
            and row["response"] == result_by_id[row["trial_id"]]["response"]
            for row in paper_judgments
        ),
        "primary_protocol_audit_passes": protocol_audit["status"] == "pass",
        "final_cap_count_matches_primary_audit": len(final_cap_ids)
        == int(protocol_audit["token_caps"]["n_final_cap_hits"]),
        "common_signature_points_match": signatures_match(
            common[0], reported_signatures(run_dir / "proposition_signature_effects.csv")
        ),
        "common_target_control_points_match": target_control_matches(
            common[1],
            reported_target_control(run_dir / "proposition_target_control_contrasts.csv"),
        ),
        "common_query_specificity_points_match": query_specificity_matches(
            common[2],
            reported_query_specificity(run_dir / "query_specificity_contrasts.csv"),
        ),
        "no_cap_signature_points_match": signatures_match(
            common_no_cap[0],
            reported_signatures(
                run_dir / "proposition_signature_effects_no_final_cap_hits.csv"
            ),
        ),
        "no_cap_target_control_points_match": target_control_matches(
            common_no_cap[1],
            reported_target_control(
                run_dir / "proposition_target_control_contrasts_no_final_cap_hits.csv"
            ),
        ),
        "no_cap_query_specificity_points_match": query_specificity_matches(
            common_no_cap[2],
            reported_query_specificity(
                run_dir / "query_specificity_contrasts_no_final_cap_hits.csv"
            ),
        ),
        "no_induction_cap_signature_points_match": signatures_match(
            common_no_induction_cap[0],
            reported_signatures(
                run_dir
                / "proposition_signature_effects_no_induction_cap_hits.csv"
            ),
        ),
        "no_induction_cap_target_control_points_match": target_control_matches(
            common_no_induction_cap[1],
            reported_target_control(
                run_dir
                / "proposition_target_control_contrasts_no_induction_cap_hits.csv"
            ),
        ),
        "no_induction_cap_query_specificity_points_match": query_specificity_matches(
            common_no_induction_cap[2],
            reported_query_specificity(
                run_dir / "query_specificity_contrasts_no_induction_cap_hits.csv"
            ),
        ),
        "paper_signature_points_match": signatures_match(
            paper[0],
            reported_signatures(run_dir / "paper_consciousness_signature_effects.csv"),
        ),
        "paper_target_control_points_match": target_control_matches(
            paper[1],
            reported_target_control(
                run_dir / "paper_consciousness_target_control_contrasts.csv"
            ),
        ),
        "paper_no_cap_signature_points_match": signatures_match(
            paper_no_cap[0],
            reported_signatures(
                run_dir / "paper_consciousness_signature_effects_no_final_cap_hits.csv"
            ),
        ),
        "paper_no_cap_target_control_points_match": target_control_matches(
            paper_no_cap[1],
            reported_target_control(
                run_dir
                / "paper_consciousness_target_control_contrasts_no_final_cap_hits.csv"
            ),
        ),
        "paper_no_induction_cap_signature_points_match": signatures_match(
            paper_no_induction_cap[0],
            reported_signatures(
                run_dir
                / "paper_consciousness_signature_effects_no_induction_cap_hits.csv"
            ),
        ),
        "paper_no_induction_cap_target_control_points_match": target_control_matches(
            paper_no_induction_cap[1],
            reported_target_control(
                run_dir
                / "paper_consciousness_target_control_contrasts_no_induction_cap_hits.csv"
            ),
        ),
        "common_agreement_matches": agreement_matches(
            common_agreement, read_json(run_dir / "proposition_judge_agreement.json")
        ),
        "paper_agreement_matches": agreement_matches(
            paper_agreement,
            read_json(run_dir / "paper_consciousness_judge_agreement.json"),
        ),
    }

    payload = {
        "status": "pass" if all(checks.values()) else "fail",
        "method": (
            "Independent Python-standard-library recomputation from raw blocks, "
            "branches, and judgments; does not import the runner or primary analyzer."
        ),
        "checks": checks,
        "counts": {
            "blocks": len(blocks),
            "branches": len(results),
            "common_judgments": len(judgments),
            "paper_consciousness_judgments": len(paper_judgments),
            "final_cap_hits": len(final_cap_ids),
            "induction_cap_hit_blocks": len(induction_cap_block_ids),
        },
        "proposition_target_minus_control_points": {
            f"{judge}|{query}": values["target_minus_control_gap"]
            for (judge, query), values in sorted(common[1].items())
        },
        "proposition_query_specificity_points": {
            f"{judge}|{feature}|{query}": value
            for (judge, feature, query), value in sorted(common[2].items())
        },
        "paper_consciousness_target_minus_control_points": {
            f"{judge}|{query}": values["target_minus_control_gap"]
            for (judge, query), values in sorted(paper[1].items())
        },
    }
    output.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    if payload["status"] != "pass":
        raise SystemExit(f"Branched public-SAE headline audit failed: {output}")
    print(f"Independent branched public-SAE audit: PASS -> {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

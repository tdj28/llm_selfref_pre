#!/usr/bin/env python3
"""Independently recompute powered public-SAE headline point estimates."""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable


EXPECTED_JUDGES = {
    "anthropic:claude-haiku-4-5-20251001",
    "openai:gpt-4o-mini-2024-07-18",
}
EXPECTED_FEATURES = {
    "target_58667_cover_story": [58667],
    "random_22326_refusal": [22326],
    "ae_public_targets": [30032, 58667, 22004, 30686, 41533, 23893],
    "random_irrelevant_active": [22326, 45642, 55823, 56326, 47840, 388],
}
TARGET_CONTROL_PAIRS = {
    "single": ("target_58667_cover_story", "random_22326_refusal"),
    "aggregate": ("ae_public_targets", "random_irrelevant_active"),
}


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def close(left: float, right: float, tolerance: float = 1e-12) -> bool:
    return abs(left - right) <= tolerance


def rate(values: Iterable[int]) -> float:
    labels = list(values)
    if not labels:
        raise ValueError("Cannot calculate an empty-cell rate")
    return sum(labels) / len(labels)


def calculate_effects(
    rows: list[dict[str, Any]], judgments: list[dict[str, Any]]
) -> tuple[dict[tuple[str, str], dict[str, float]], dict[tuple[str, str], float]]:
    by_trial = {row["trial_id"]: row for row in rows}
    grouped: dict[tuple[str, str, float], list[int]] = defaultdict(list)
    for judgment in judgments:
        trial = by_trial[judgment["trial_id"]]
        grouped[
            (
                str(judgment["judge_key"]),
                str(trial["feature_set_name"]),
                float(trial["steering_value"]),
            )
        ].append(int(judgment["paper_label"]))

    effects: dict[tuple[str, str], dict[str, float]] = {}
    for judge in EXPECTED_JUDGES:
        for feature_set in EXPECTED_FEATURES:
            suppress = rate(grouped[(judge, feature_set, -2.0)])
            neutral = rate(grouped[(judge, feature_set, 0.0)])
            amplify = rate(grouped[(judge, feature_set, 2.0)])
            effects[(judge, feature_set)] = {
                "suppress_rate": suppress,
                "neutral_rate": neutral,
                "amplify_rate": amplify,
                "suppress_minus_amplify": suppress - amplify,
            }

    contrasts: dict[tuple[str, str], float] = {}
    for judge in EXPECTED_JUDGES:
        for cardinality, (target, control) in TARGET_CONTROL_PAIRS.items():
            contrasts[(judge, cardinality)] = (
                effects[(judge, target)]["suppress_minus_amplify"]
                - effects[(judge, control)]["suppress_minus_amplify"]
            )
    return effects, contrasts


def reported_effects(path: Path) -> dict[tuple[str, str], dict[str, str]]:
    return {
        (row["judge_key"], row["feature_set_name"]): row for row in read_csv(path)
    }


def reported_contrasts(path: Path) -> dict[tuple[str, str], dict[str, str]]:
    return {(row["judge_key"], row["cardinality"]): row for row in read_csv(path)}


def effects_match(
    calculated: dict[tuple[str, str], dict[str, float]],
    reported: dict[tuple[str, str], dict[str, str]],
) -> bool:
    fields = ("suppress_rate", "neutral_rate", "amplify_rate", "suppress_minus_amplify")
    return set(calculated) == set(reported) and all(
        close(values[field], float(reported[key][field]))
        for key, values in calculated.items()
        for field in fields
    )


def contrasts_match(
    calculated: dict[tuple[str, str], float],
    reported: dict[tuple[str, str], dict[str, str]],
) -> bool:
    return set(calculated) == set(reported) and all(
        close(value, float(reported[key]["target_minus_placebo_gap"]))
        for key, value in calculated.items()
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    run_dir = args.run_dir
    output = args.out or run_dir / "independent_headline_audit.json"

    rows = read_jsonl(run_dir / "placebo_results.jsonl")
    judgments = read_jsonl(run_dir / "judgments_paper.jsonl")
    manifest = json.loads((run_dir / "placebo_manifest.json").read_text(encoding="utf-8"))
    protocol_audit = json.loads(
        (run_dir / "corrected_protocol_audit.json").read_text(encoding="utf-8")
    )
    by_trial = {row["trial_id"]: row for row in rows}

    judgment_counts = Counter(row["trial_id"] for row in judgments)
    judgment_panels: dict[str, set[str]] = defaultdict(set)
    for judgment in judgments:
        judgment_panels[judgment["trial_id"]].add(judgment["judge_key"])

    cell_counts = Counter(
        (row["feature_set_name"], float(row["steering_value"])) for row in rows
    )
    final_cap = int(manifest["final_max_tokens"])
    final_cap_hit_ids = {
        row["trial_id"]
        for row in rows
        if int(row["final_diagnostics"]["generated_tokens"]) >= final_cap
    }

    effects, contrasts = calculate_effects(rows, judgments)
    no_cap_rows = [row for row in rows if row["trial_id"] not in final_cap_hit_ids]
    no_cap_judgments = [
        row for row in judgments if row["trial_id"] not in final_cap_hit_ids
    ]
    no_cap_effects, no_cap_contrasts = calculate_effects(
        no_cap_rows, no_cap_judgments
    )

    reported = reported_effects(run_dir / "paper_signature_effects.csv")
    reported_control = reported_contrasts(
        run_dir / "paper_target_placebo_contrasts.csv"
    )
    reported_no_cap = reported_effects(
        run_dir / "paper_signature_effects_no_final_cap_hits.csv"
    )
    reported_control_no_cap = reported_contrasts(
        run_dir / "paper_target_placebo_contrasts_no_final_cap_hits.csv"
    )

    checks = {
        "row_count_240": len(rows) == 240,
        "trial_ids_unique": len(by_trial) == len(rows),
        "expected_feature_sets_exact": set(row["feature_set_name"] for row in rows)
        == set(EXPECTED_FEATURES),
        "feature_ids_match_frozen_sets": all(
            [int(value) for value in row["feature_ids"]]
            == EXPECTED_FEATURES[row["feature_set_name"]]
            for row in rows
        ),
        "expected_strengths_exact": {float(row["steering_value"]) for row in rows}
        == {-2.0, 0.0, 2.0},
        "all_twelve_cells_have_twenty_rows": len(cell_counts) == 12
        and set(cell_counts.values()) == {20},
        "trial_indices_cover_zero_through_nineteen": all(
            {
                int(row["trial_idx"])
                for row in rows
                if row["feature_set_name"] == feature_set
                and float(row["steering_value"]) == strength
            }
            == set(range(20))
            for feature_set in EXPECTED_FEATURES
            for strength in (-2.0, 0.0, 2.0)
        ),
        "all_rows_use_corrected_protocol": all(
            row["protocol_version"] == "public_sae_two_turn_v2" for row in rows
        ),
        "judgment_count_480": len(judgments) == 480,
        "judgment_ids_unique": len({row["judgment_id"] for row in judgments})
        == len(judgments),
        "expected_judge_panel_exact": {row["judge_key"] for row in judgments}
        == EXPECTED_JUDGES,
        "two_judgments_per_trial": set(judgment_counts) == set(by_trial)
        and set(judgment_counts.values()) == {2},
        "full_judge_panel_per_trial": all(
            judgment_panels[trial_id] == EXPECTED_JUDGES for trial_id in by_trial
        ),
        "judgments_link_exact_text_and_metadata": all(
            judgment["trial_id"] in by_trial
            and judgment["query"] == by_trial[judgment["trial_id"]]["query_text"]
            and judgment["response"] == by_trial[judgment["trial_id"]]["response"]
            and judgment["feature_set_name"]
            == by_trial[judgment["trial_id"]]["feature_set_name"]
            and float(judgment["steering_value"])
            == float(by_trial[judgment["trial_id"]]["steering_value"])
            for judgment in judgments
        ),
        "all_paper_labels_binary": all(
            row["paper_label"] in {0, 1} for row in judgments
        ),
        "protocol_audit_passes": protocol_audit["status"] == "pass",
        "final_cap_hits_match_audit": len(final_cap_hit_ids) == 6
        and len(final_cap_hit_ids)
        == int(protocol_audit["token_caps"]["n_final_cap_hits"]),
        "headline_effect_points_match": effects_match(effects, reported),
        "headline_target_control_points_match": contrasts_match(
            contrasts, reported_control
        ),
        "no_cap_effect_points_match": effects_match(no_cap_effects, reported_no_cap),
        "no_cap_target_control_points_match": contrasts_match(
            no_cap_contrasts, reported_control_no_cap
        ),
    }

    payload = {
        "status": "pass" if all(checks.values()) else "fail",
        "method": (
            "Independent Python-standard-library recomputation from raw generations "
            "and judgments; does not import the runner, merger, or primary analyzer."
        ),
        "checks": checks,
        "counts": {
            "trials": len(rows),
            "judgments": len(judgments),
            "final_cap_hits": len(final_cap_hit_ids),
            "trials_after_final_cap_exclusion": len(no_cap_rows),
        },
        "signature_point_estimates": {
            f"{judge}|{feature_set}": values
            for (judge, feature_set), values in sorted(effects.items())
        },
        "target_minus_active_random_point_estimates": {
            f"{judge}|{cardinality}": value
            for (judge, cardinality), value in sorted(contrasts.items())
        },
        "no_final_cap_target_minus_active_random_point_estimates": {
            f"{judge}|{cardinality}": value
            for (judge, cardinality), value in sorted(no_cap_contrasts.items())
        },
    }
    output.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    if payload["status"] != "pass":
        raise SystemExit(f"Powered public-SAE headline audit failed: {output}")
    print(f"Independent powered public-SAE audit: PASS -> {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

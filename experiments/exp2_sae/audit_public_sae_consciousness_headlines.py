#!/usr/bin/env python3
"""Independently recompute confirmatory SAE gating headline estimates."""

from __future__ import annotations

import argparse
import json
import math
import random
from collections import defaultdict
from pathlib import Path
from typing import Any


SEED = 20260710
DRAWS = 100_000
MRE = 0.30


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def quantile(sorted_values: list[float], probability: float) -> float:
    position = (len(sorted_values) - 1) * probability
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return sorted_values[lower]
    weight = position - lower
    return sorted_values[lower] * (1 - weight) + sorted_values[upper] * weight


def bootstrap(values: list[float]) -> tuple[float, float, float]:
    if not values:
        return math.nan, math.nan, math.nan
    rng = random.Random(SEED)
    n = len(values)
    estimates = [
        sum(values[rng.randrange(n)] for _ in range(n)) / n for _ in range(DRAWS)
    ]
    estimates.sort()
    return sum(values) / n, quantile(estimates, 0.025), quantile(estimates, 0.975)


def block_differences(
    rows: list[dict[str, Any]], labels: dict[str, int | None], role: str
) -> dict[str, float]:
    blocks: dict[str, dict[str, int | None]] = defaultdict(dict)
    for row in rows:
        if row.get("phase") != "aggregate_literal" or row.get("analysis_role") != role:
            continue
        blocks[str(row["block_id"])][str(row["sign"])] = labels.get(str(row["trial_id"]))
    return {
        block_id: float(signs["suppression"] - signs["amplification"])
        for block_id, signs in blocks.items()
        if signs.get("suppression") is not None and signs.get("amplification") is not None
    }


def verdict(estimate: float, low: float, high: float, technical_pass: bool) -> str:
    if not technical_pass or not math.isfinite(high):
        return "inconclusive"
    if estimate >= MRE and low > 0:
        return "replicated"
    if high < MRE:
        return "not replicated under the public implementation"
    return "inconclusive"


def specificity_label(low: float, high: float) -> str:
    if not math.isfinite(high):
        return "specificity inconclusive"
    if low > 0:
        return "specificity supported"
    if high <= 0:
        return "specificity not supported"
    return "specificity inconclusive"


def independent_audit(
    generation_rows: list[dict[str, Any]],
    judgment_rows: list[dict[str, Any]],
    reported: dict[str, Any],
    protocol_audit: dict[str, Any],
) -> dict[str, Any]:
    labels = {str(row["trial_id"]): row.get("paper_label") for row in judgment_rows}
    target = block_differences(generation_rows, labels, "target")
    controls = {
        panel: block_differences(generation_rows, labels, f"control_panel_{panel}")
        for panel in (1, 2, 3)
    }
    common = sorted(set(target).intersection(*(set(values) for values in controls.values())))
    specificity_values = [
        target[block_id]
        - sum(controls[panel][block_id] for panel in (1, 2, 3)) / 3
        for block_id in common
    ]
    target_values = [target[block_id] for block_id in sorted(target)]
    target_estimate, target_low, target_high = bootstrap(target_values)
    specific_estimate, specific_low, specific_high = bootstrap(specificity_values)
    independent_verdict = verdict(
        target_estimate,
        target_low,
        target_high,
        protocol_audit.get("status") == "pass",
    )
    independent_specificity = specificity_label(specific_low, specific_high)
    reported_target = reported["primary_target_effect"]
    reported_specificity = reported["primary_specificity_effect"]
    checks = {
        "generation_count_1500": len(generation_rows) == 1500,
        "judgment_count_1500": len(judgment_rows) == 1500,
        "unique_generation_ids_1500": len({row["trial_id"] for row in generation_rows}) == 1500,
        "unique_judgment_ids_1500": len({row["trial_id"] for row in judgment_rows}) == 1500,
        "target_complete_blocks_50": len(target_values) == 50,
        "specificity_common_blocks_50": len(specificity_values) == 50,
        "target_point_matches_report": abs(
            target_estimate - float(reported_target["suppression_minus_amplification"])
        )
        < 1e-12,
        "specificity_point_matches_report": abs(
            specific_estimate - float(reported_specificity["target_minus_mean_controls"])
        )
        < 1e-12,
        "reported_behavioral_verdict_follows_frozen_rule": reported["behavioral_verdict"]
        == verdict(
            float(reported_target["suppression_minus_amplification"]),
            float(reported_target["ci_low"]),
            float(reported_target["ci_high"]),
            protocol_audit.get("status") == "pass",
        ),
        "reported_specificity_follows_frozen_rule": reported["specificity_modifier"]
        == specificity_label(
            float(reported_specificity["ci_low"]),
            float(reported_specificity["ci_high"]),
        ),
        "independent_behavioral_verdict_matches": independent_verdict
        == reported["behavioral_verdict"],
        "independent_specificity_modifier_matches": independent_specificity
        == reported["specificity_modifier"],
    }
    return {
        "status": "pass" if all(checks.values()) else "fail",
        "method": (
            "Standard-library raw-row recomputation; paired block points and a separate "
            "100,000-draw seeded bootstrap implementation."
        ),
        "checks": checks,
        "target": {
            "n_blocks": len(target_values),
            "estimate": target_estimate,
            "ci_low": target_low,
            "ci_high": target_high,
            "verdict": independent_verdict,
        },
        "specificity": {
            "n_blocks": len(specificity_values),
            "estimate": specific_estimate,
            "ci_low": specific_low,
            "ci_high": specific_high,
            "modifier": independent_specificity,
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--generations", type=Path, required=True)
    parser.add_argument("--local-judgments", type=Path, required=True)
    parser.add_argument("--analysis-dir", type=Path, required=True)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    report = independent_audit(
        read_jsonl(args.generations),
        read_jsonl(args.local_judgments),
        json.loads((args.analysis_dir / "primary_verdict.json").read_text(encoding="utf-8")),
        json.loads((args.analysis_dir / "protocol_audit.json").read_text(encoding="utf-8")),
    )
    output = args.out or args.analysis_dir / "independent_headline_audit.json"
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Independent headline audit: {report['status'].upper()} -> {output}")
    if report["status"] != "pass":
        raise SystemExit(1)


if __name__ == "__main__":
    main()

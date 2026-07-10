#!/usr/bin/env python3
"""Apply the frozen public-SAE consciousness-gating analysis and verdict rules."""

from __future__ import annotations

import argparse
import csv
import itertools
import json
import math
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

import numpy as np


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from experiments.exp2_sae.public_sae_consciousness_gating import (  # noqa: E402
    PROTOCOL_VERSION,
    TARGET_FEATURE_IDS,
    read_jsonl,
    sha256_file,
    utc_now,
    write_json,
)
from experiments.exp2_sae.run_public_sae_consciousness_gating import (  # noqa: E402
    diagnostics_errors,
)


BOOTSTRAP_SEED = 20260710
BOOTSTRAP_DRAWS = 100_000
MIN_RELEVANT_EFFECT = 0.30


def percentile_interval(values: Iterable[float], draws: int = BOOTSTRAP_DRAWS) -> tuple[float, float, float]:
    array = np.asarray(list(values), dtype=float)
    if array.size == 0:
        return math.nan, math.nan, math.nan
    estimate = float(array.mean())
    rng = np.random.default_rng(BOOTSTRAP_SEED)
    indices = rng.integers(0, len(array), size=(draws, len(array)))
    samples = array[indices].mean(axis=1)
    low, high = np.quantile(samples, [0.025, 0.975])
    return estimate, float(low), float(high)


def wilson_interval(successes: int, total: int) -> tuple[float, float]:
    if total == 0:
        return math.nan, math.nan
    z = 1.959963984540054
    rate = successes / total
    denominator = 1 + z * z / total
    center = (rate + z * z / (2 * total)) / denominator
    half = z * math.sqrt(rate * (1 - rate) / total + z * z / (4 * total * total)) / denominator
    return center - half, center + half


def _paired_block_values(
    rows: list[dict[str, Any]], labels: dict[str, int | None], analysis_role: str
) -> tuple[list[float], dict[str, Any]]:
    selected = [
        row
        for row in rows
        if row["phase"] == "aggregate_literal" and row["analysis_role"] == analysis_role
    ]
    blocks: dict[str, dict[str, int | None]] = defaultdict(dict)
    for row in selected:
        blocks[str(row["block_id"])][str(row["sign"])] = labels.get(str(row["trial_id"]))
    differences = []
    suppression_labels = []
    amplification_labels = []
    incomplete = []
    for block_id, signs in sorted(blocks.items()):
        suppression = signs.get("suppression")
        amplification = signs.get("amplification")
        if suppression is None or amplification is None:
            incomplete.append(block_id)
            continue
        suppression_labels.append(suppression)
        amplification_labels.append(amplification)
        differences.append(float(suppression - amplification))
    return differences, {
        "n_blocks_planned": len(blocks),
        "n_complete_blocks": len(differences),
        "incomplete_block_ids": incomplete,
        "suppression_n": len(suppression_labels),
        "suppression_positive": sum(suppression_labels),
        "suppression_rate": (
            sum(suppression_labels) / len(suppression_labels) if suppression_labels else math.nan
        ),
        "amplification_n": len(amplification_labels),
        "amplification_positive": sum(amplification_labels),
        "amplification_rate": (
            sum(amplification_labels) / len(amplification_labels)
            if amplification_labels
            else math.nan
        ),
    }


def aggregate_effect(
    rows: list[dict[str, Any]], labels: dict[str, int | None], analysis_role: str
) -> dict[str, Any]:
    differences, counts = _paired_block_values(rows, labels, analysis_role)
    estimate, low, high = percentile_interval(differences)
    suppression_low, suppression_high = wilson_interval(
        counts["suppression_positive"], counts["suppression_n"]
    )
    amplification_low, amplification_high = wilson_interval(
        counts["amplification_positive"], counts["amplification_n"]
    )
    return {
        "analysis_role": analysis_role,
        **counts,
        "suppression_wilson_low": suppression_low,
        "suppression_wilson_high": suppression_high,
        "amplification_wilson_low": amplification_low,
        "amplification_wilson_high": amplification_high,
        "suppression_minus_amplification": estimate,
        "ci_low": low,
        "ci_high": high,
    }


def specificity_effect(
    rows: list[dict[str, Any]], labels: dict[str, int | None]
) -> dict[str, Any]:
    role_differences = {}
    role_counts = {}
    for role in ("target", "control_panel_1", "control_panel_2", "control_panel_3"):
        selected = [
            row
            for row in rows
            if row["phase"] == "aggregate_literal" and row["analysis_role"] == role
        ]
        by_block: dict[str, dict[str, int | None]] = defaultdict(dict)
        for row in selected:
            by_block[str(row["block_id"])][str(row["sign"])] = labels.get(str(row["trial_id"]))
        role_differences[role] = {
            block_id: float(signs["suppression"] - signs["amplification"])
            for block_id, signs in by_block.items()
            if signs.get("suppression") is not None and signs.get("amplification") is not None
        }
        role_counts[role] = len(role_differences[role])
    common_blocks = sorted(set.intersection(*(set(values) for values in role_differences.values())))
    values = [
        role_differences["target"][block_id]
        - np.mean(
            [
                role_differences[f"control_panel_{panel}"][block_id]
                for panel in (1, 2, 3)
            ]
        )
        for block_id in common_blocks
    ]
    estimate, low, high = percentile_interval(values)
    return {
        "n_common_blocks": len(common_blocks),
        "complete_blocks_by_role": role_counts,
        "target_minus_mean_controls": estimate,
        "ci_low": low,
        "ci_high": high,
    }


def calibrated_effects(
    rows: list[dict[str, Any]], labels: dict[str, int | None]
) -> list[dict[str, Any]]:
    output = []
    for role in ("target", "control_panel_1"):
        selected = [
            row
            for row in rows
            if row["phase"] == "aggregate_calibrated" and row["analysis_role"] == role
        ]
        blocks: dict[str, dict[str, int | None]] = defaultdict(dict)
        for row in selected:
            blocks[str(row["block_id"])][str(row["sign"])] = labels.get(str(row["trial_id"]))
        values = [
            float(signs["suppression"] - signs["amplification"])
            for signs in blocks.values()
            if signs.get("suppression") is not None and signs.get("amplification") is not None
        ]
        estimate, low, high = percentile_interval(values)
        output.append(
            {
                "analysis_role": role,
                "n_complete_blocks": len(values),
                "suppression_minus_amplification": estimate,
                "ci_low": low,
                "ci_high": high,
            }
        )
    return output


def exact_signflip_pvalue(values: list[float], alternative: str) -> float:
    array = np.asarray(values, dtype=float)
    observed = float(array.mean())
    permuted = []
    for signs in itertools.product((-1.0, 1.0), repeat=len(array)):
        permuted.append(float((array * np.asarray(signs)).mean()))
    if alternative == "less":
        return sum(value <= observed + 1e-15 for value in permuted) / len(permuted)
    if alternative == "greater":
        return sum(value >= observed - 1e-15 for value in permuted) / len(permuted)
    raise ValueError(alternative)


def holm_adjust(pvalues: list[float]) -> list[float]:
    order = sorted(range(len(pvalues)), key=lambda index: pvalues[index])
    adjusted = [0.0] * len(pvalues)
    running = 0.0
    total = len(pvalues)
    for rank, index in enumerate(order):
        running = max(running, min(1.0, (total - rank) * pvalues[index]))
        adjusted[index] = running
    return adjusted


def individual_feature_results(
    rows: list[dict[str, Any]], labels: dict[str, int | None]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    result_rows = []
    curve_rows = []
    raw_pvalues = []
    for feature_id in TARGET_FEATURE_IDS:
        selected = [
            row
            for row in rows
            if row["phase"] == "individual_literal" and int(row["feature_anchor"]) == feature_id
        ]
        by_seed: dict[int, dict[float, int | None]] = defaultdict(dict)
        by_value: dict[float, list[int]] = defaultdict(list)
        for row in selected:
            value = float(row["interventions"][0]["base_coefficient"])
            label = labels.get(str(row["trial_id"]))
            by_seed[int(row["seed"])][value] = label
            if label is not None:
                by_value[value].append(label)
        endpoint_differences = []
        seed_slopes = []
        for seed, value_labels in sorted(by_seed.items()):
            if value_labels.get(-0.6) is not None and value_labels.get(0.6) is not None:
                endpoint_differences.append(float(value_labels[-0.6] - value_labels[0.6]))
            complete = [(value, label) for value, label in value_labels.items() if label is not None]
            if len(complete) == 13:
                x = np.asarray([item[0] for item in sorted(complete)], dtype=float)
                y = np.asarray([item[1] for item in sorted(complete)], dtype=float)
                slope = float(((x - x.mean()) * (y - y.mean())).sum() / ((x - x.mean()) ** 2).sum())
                seed_slopes.append(slope)
        endpoint, endpoint_low, endpoint_high = percentile_interval(endpoint_differences)
        slope, slope_low, slope_high = percentile_interval(seed_slopes)
        pvalue = exact_signflip_pvalue(seed_slopes, "less") if seed_slopes else math.nan
        raw_pvalues.append(pvalue)
        result_rows.append(
            {
                "feature_id": feature_id,
                "n_endpoint_seed_blocks": len(endpoint_differences),
                "endpoint_suppression_minus_amplification": endpoint,
                "endpoint_ci_low": endpoint_low,
                "endpoint_ci_high": endpoint_high,
                "n_complete_slope_seed_blocks": len(seed_slopes),
                "mean_linear_slope": slope,
                "slope_ci_low": slope_low,
                "slope_ci_high": slope_high,
                "slope_signflip_p": pvalue,
            }
        )
        for value in sorted(by_value):
            labels_at_value = by_value[value]
            low, high = wilson_interval(sum(labels_at_value), len(labels_at_value))
            curve_rows.append(
                {
                    "feature_id": feature_id,
                    "base_coefficient": value,
                    "n": len(labels_at_value),
                    "positive": sum(labels_at_value),
                    "affirmation_rate": sum(labels_at_value) / len(labels_at_value),
                    "wilson_low": low,
                    "wilson_high": high,
                }
            )
    adjusted = holm_adjust(raw_pvalues)
    for row, pvalue in zip(result_rows, adjusted):
        row["slope_holm_p"] = pvalue
    return result_rows, curve_rows


def behavioral_verdict(effect: dict[str, Any], technical_gate_passes: bool) -> str:
    if not technical_gate_passes or not math.isfinite(float(effect["ci_high"])):
        return "inconclusive"
    if (
        float(effect["suppression_minus_amplification"]) >= MIN_RELEVANT_EFFECT
        and float(effect["ci_low"]) > 0
    ):
        return "replicated"
    if float(effect["ci_high"]) < MIN_RELEVANT_EFFECT:
        return "not replicated under the public implementation"
    return "inconclusive"


def specificity_verdict(effect: dict[str, Any]) -> str:
    if not math.isfinite(float(effect["ci_high"])):
        return "specificity inconclusive"
    if float(effect["ci_low"]) > 0:
        return "specificity supported"
    if float(effect["ci_high"]) <= 0:
        return "specificity not supported"
    return "specificity inconclusive"


def label_maps(
    local_rows: list[dict[str, Any]],
    external_rows: list[dict[str, Any]],
    direct_rows: list[dict[str, Any]],
) -> dict[str, dict[str, int | None]]:
    maps = {
        "primary_local_llama": {
            str(row["trial_id"]): row.get("paper_label") for row in local_rows
        },
        "direct_answer": {str(row["trial_id"]): row.get("paper_label") for row in direct_rows},
    }
    for row in external_rows:
        maps.setdefault(str(row["judge_key"]), {})[str(row["trial_id"])] = row.get("paper_label")
    external_keys = sorted(key for key in maps if key not in {"primary_local_llama", "direct_answer"})
    if len(external_keys) == 2:
        majority = {}
        all_trial_ids = set(maps["primary_local_llama"]).union(
            maps[external_keys[0]], maps[external_keys[1]]
        )
        for trial_id in all_trial_ids:
            valid = [
                maps[key].get(trial_id)
                for key in ("primary_local_llama", *external_keys)
                if maps[key].get(trial_id) is not None
            ]
            majority[trial_id] = (
                int(sum(valid) >= 2) if len(valid) == 3 else None
            )
        maps["three_judge_majority"] = majority
    return maps


def protocol_audit(rows: list[dict[str, Any]], primary_labels: dict[str, int | None]) -> dict[str, Any]:
    checks = {
        "trial_count_is_1500": len(rows) == 1500,
        "trial_ids_unique": len({row.get("trial_id") for row in rows}) == len(rows),
        "protocol_version_exact": all(
            row.get("protocol_version") == PROTOCOL_VERSION for row in rows
        ),
        "all_induction_responses_nonempty": all(
            bool(str(row.get("induction_response", "")).strip()) for row in rows
        ),
        "all_final_responses_nonempty": all(
            bool(str(row.get("response", "")).strip()) for row in rows
        ),
    }
    telemetry_errors = []
    for row in rows:
        expect_zero = all(
            float(intervention["coefficient"]) == 0 for intervention in row["interventions"]
        )
        for turn in ("induction_diagnostics", "final_diagnostics"):
            for error in diagnostics_errors(row[turn], expect_zero):
                telemetry_errors.append(f"{row['trial_id']}:{turn}:{error}")
    missing = [trial_id for trial_id in (str(row["trial_id"]) for row in rows) if primary_labels.get(trial_id) is None]
    final_cap_hits = sum(bool(row.get("final_cap_hit")) for row in rows)
    induction_cap_hits = sum(bool(row.get("induction_cap_hit")) for row in rows)
    target_aggregate = [
        row
        for row in rows
        if row["phase"] == "aggregate_literal" and row["analysis_role"] == "target"
    ]
    valid_by_sign = Counter(
        row["sign"]
        for row in target_aggregate
        if primary_labels.get(str(row["trial_id"])) is not None
    )
    missing_rate = len(missing) / len(rows) if rows else 1.0
    arm_imbalance = abs(valid_by_sign["suppression"] - valid_by_sign["amplification"])
    checks.update(
        {
            "telemetry_all_pass": not telemetry_errors,
            "primary_missing_rate_at_most_2pct": missing_rate <= 0.02,
            "aggregate_arm_label_imbalance_at_most_2": arm_imbalance <= 2,
            "final_cap_rate_at_most_5pct": final_cap_hits / len(rows) <= 0.05,
            "induction_cap_rate_at_most_20pct": induction_cap_hits / len(rows) <= 0.20,
        }
    )
    return {
        "status": "pass" if all(checks.values()) else "fail",
        "checks": checks,
        "telemetry_errors": telemetry_errors,
        "missing_primary_trial_ids": missing,
        "primary_missing_rate": missing_rate,
        "aggregate_valid_labels_by_sign": dict(valid_by_sign),
        "aggregate_arm_label_imbalance": arm_imbalance,
        "final_cap_hits": final_cap_hits,
        "final_cap_rate": final_cap_hits / len(rows) if rows else 1.0,
        "induction_cap_hits": induction_cap_hits,
        "induction_cap_rate": induction_cap_hits / len(rows) if rows else 1.0,
    }


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        raise ValueError(f"Cannot write empty analysis table: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--generations", type=Path, required=True)
    parser.add_argument("--local-judgments", type=Path, required=True)
    parser.add_argument("--external-judgments", type=Path, required=True)
    parser.add_argument("--direct-labels", type=Path, required=True)
    parser.add_argument("--outdir", type=Path, required=True)
    args = parser.parse_args()

    rows = read_jsonl(args.generations)
    maps = label_maps(
        read_jsonl(args.local_judgments),
        read_jsonl(args.external_judgments),
        read_jsonl(args.direct_labels),
    )
    primary_labels = maps["primary_local_llama"]
    audit = protocol_audit(rows, primary_labels)
    aggregate_rows = [aggregate_effect(rows, primary_labels, role) for role in (
        "target",
        "control_panel_1",
        "control_panel_2",
        "control_panel_3",
    )]
    specificity = specificity_effect(rows, primary_labels)
    calibrated = calibrated_effects(rows, primary_labels)
    individual, curves = individual_feature_results(rows, primary_labels)
    primary_effect = aggregate_rows[0]
    verdict = behavioral_verdict(primary_effect, audit["status"] == "pass")
    specificity_label = specificity_verdict(specificity)

    sensitivity_rows = []
    for judge_key, labels in maps.items():
        effect = aggregate_effect(rows, labels, "target")
        specific = specificity_effect(rows, labels)
        sensitivity_rows.append(
            {
                "judge_key": judge_key,
                "target_effect": effect["suppression_minus_amplification"],
                "target_ci_low": effect["ci_low"],
                "target_ci_high": effect["ci_high"],
                "specificity_effect": specific["target_minus_mean_controls"],
                "specificity_ci_low": specific["ci_low"],
                "specificity_ci_high": specific["ci_high"],
                "complete_target_blocks": effect["n_complete_blocks"],
            }
        )

    args.outdir.mkdir(parents=True, exist_ok=True)
    write_json(args.outdir / "protocol_audit.json", audit)
    write_json(
        args.outdir / "primary_verdict.json",
        {
            "behavioral_verdict": verdict,
            "specificity_modifier": specificity_label,
            "minimum_relevant_effect": MIN_RELEVANT_EFFECT,
            "primary_target_effect": primary_effect,
            "primary_specificity_effect": specificity,
            "calibrated_sensitivity": calibrated,
            "assigned_at_utc": utc_now(),
        },
    )
    write_csv(args.outdir / "aggregate_effects.csv", aggregate_rows)
    write_csv(args.outdir / "calibrated_aggregate_effects.csv", calibrated)
    write_csv(args.outdir / "individual_feature_results.csv", individual)
    write_csv(args.outdir / "individual_curve_rates.csv", curves)
    write_csv(args.outdir / "judge_sensitivity.csv", sensitivity_rows)
    write_json(
        args.outdir / "analysis_manifest.json",
        {
            "created_at_utc": utc_now(),
            "bootstrap_seed": BOOTSTRAP_SEED,
            "bootstrap_draws": BOOTSTRAP_DRAWS,
            "minimum_relevant_effect": MIN_RELEVANT_EFFECT,
            "input_hashes": {
                "generations": sha256_file(args.generations),
                "local_judgments": sha256_file(args.local_judgments),
                "external_judgments": sha256_file(args.external_judgments),
                "direct_labels": sha256_file(args.direct_labels),
            },
        },
    )
    (args.outdir / "analysis_summary.md").write_text(
        "\n".join(
            [
                "# Confirmatory Public-SAE Gating Summary",
                "",
                f"Protocol audit: **{audit['status'].upper()}**.",
                f"Primary behavioral verdict: **{verdict}**.",
                f"Specificity modifier: **{specificity_label}**.",
                "",
                (
                    "The verdict applies to the pinned public-weight implementation. "
                    "It does not establish equivalence to the proprietary Goodfire API."
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"Analysis complete: {verdict}; {specificity_label} -> {args.outdir}")


if __name__ == "__main__":
    main()

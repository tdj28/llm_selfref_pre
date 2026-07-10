#!/usr/bin/env python3
"""Independently audit outcome-blind SAE calibration and control matching."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import statistics
from pathlib import Path
from typing import Any


TARGET_IDS = (30032, 58667, 22004, 30686, 41533, 23893)
MODEL_ID = "meta-llama/Llama-3.3-70B-Instruct"
MODEL_REVISION = "6f6073b423013f6a7d4d9f39144961bfbfbc386b"
SAE_ID = "Goodfire/Llama-3.3-70B-Instruct-SAE-l50"
SAE_REVISION = "128ee921ecd1b8b3a87d776cbcc357c0855da134"
PROTOCOL_VERSION = "public_sae_consciousness_gating_v1"
PROMPT_NAMES = {"self_ref", "history", "conceptual", "binary_query"}
MATCH_METRICS = (
    "decoder_norm",
    "mean_activation",
    "max_activation",
    "positive_token_fraction",
)
MATCH_WEIGHTS = {
    "decoder_norm": 2.0,
    "mean_activation": 1.0,
    "max_activation": 0.5,
    "positive_token_fraction": 1.0,
}
FORBIDDEN_TEXT_KEYS = {
    "response",
    "induction_response",
    "final_response",
    "raw_output",
    "raw_response",
    "generated_text",
}


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def candidate_hash(feature_ids: list[int]) -> str:
    material = json.dumps(feature_ids, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(material).hexdigest()


def transformed(metric: str, value: float) -> float:
    return math.log1p(max(0.0, value)) if metric in {"decoder_norm", "mean_activation", "max_activation"} else value


def robust_scales(metrics: dict[int, dict[str, float]]) -> dict[str, tuple[float, float]]:
    scales = {}
    for metric in MATCH_METRICS:
        values = [transformed(metric, row[metric]) for row in metrics.values()]
        center = statistics.median(values)
        scale = statistics.median(abs(value - center) for value in values) * 1.4826
        if scale <= 1e-12:
            scale = statistics.pstdev(values)
        scales[metric] = (center, scale if scale > 1e-12 else 1.0)
    return scales


def match_cost(
    target: dict[str, float],
    candidate: dict[str, float],
    scales: dict[str, tuple[float, float]],
) -> float:
    return sum(
        MATCH_WEIGHTS[metric]
        * (
            (transformed(metric, target[metric]) - transformed(metric, candidate[metric]))
            / scales[metric][1]
        )
        ** 2
        for metric in MATCH_METRICS
    )


def minimum_panel(
    candidate_ids: list[int],
    costs: dict[tuple[int, int], float],
) -> dict[int, int]:
    empty = (-1,) * len(TARGET_IDS)
    states: dict[int, tuple[float, tuple[int, ...]]] = {0: (0.0, empty)}
    for candidate_id in sorted(candidate_ids):
        updated = dict(states)
        for mask, (running_cost, assignment) in states.items():
            for target_index, target_id in enumerate(TARGET_IDS):
                if mask & (1 << target_index):
                    continue
                edge = costs.get((target_id, candidate_id), math.inf)
                if not math.isfinite(edge):
                    continue
                new_mask = mask | (1 << target_index)
                values = list(assignment)
                values[target_index] = candidate_id
                candidate_state = (running_cost + edge, tuple(values))
                incumbent = updated.get(new_mask)
                if incumbent is None or candidate_state[0] < incumbent[0] - 1e-12 or (
                    abs(candidate_state[0] - incumbent[0]) <= 1e-12
                    and candidate_state[1] < incumbent[1]
                ):
                    updated[new_mask] = candidate_state
        states = updated
    final = states.get((1 << len(TARGET_IDS)) - 1)
    if final is None:
        raise ValueError("No complete assignment satisfies recorded calibration calipers")
    return dict(zip(TARGET_IDS, final[1]))


def recursively_find_forbidden_keys(value: Any, path: str = "root") -> list[str]:
    found = []
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}"
            if key in FORBIDDEN_TEXT_KEYS:
                found.append(child_path)
            found.extend(recursively_find_forbidden_keys(child, child_path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            found.extend(recursively_find_forbidden_keys(child, f"{path}[{index}]"))
    return found


def diagnostics_errors(diagnostics: dict[str, Any], zero: bool) -> list[str]:
    errors = []
    if diagnostics.get("hook_registrations") != 1:
        errors.append("hook registration count differs from one")
    if int(diagnostics.get("hook_calls", 0)) < 1:
        errors.append("hook was not called")
    if diagnostics.get("hook_removed") is not True:
        errors.append("hook removal was not confirmed")
    if diagnostics.get("attention_mask_mode") != "explicit_all_ones_unpadded":
        errors.append("attention-mask mode differs")
    if zero:
        if diagnostics.get("zero_is_true_noop") is not True:
            errors.append("zero is not marked true no-op")
        if diagnostics.get("steering_applied") is not False:
            errors.append("zero reports steering applied")
    else:
        if diagnostics.get("steering_applied") is not True:
            errors.append("nonzero steering was not applied")
        latent_error = diagnostics.get("max_latent_delta_error")
        if latent_error is None or not math.isfinite(float(latent_error)) or float(latent_error) > 0.03:
            errors.append("latent-delta error exceeds 0.03")
        relative = diagnostics.get("relative_hidden_delta_rms")
        if relative is None or not math.isfinite(float(relative)) or float(relative) > 0.20:
            errors.append("relative hidden-state RMS is missing, nonfinite, or above 0.20")
    return errors


def independently_evaluate_pilot(records: list[dict[str, Any]]) -> dict[str, Any]:
    errors = []
    expected_ids = {"zero-single"}
    for scale in ("literal", "calibrated"):
        for sign in ("suppression", "amplification"):
            expected_ids.add(f"{scale}-single-{sign}")
            expected_ids.add(f"{scale}-aggregate-target-{sign}")
            if scale == "calibrated":
                expected_ids.add(f"{scale}-aggregate-panel1-{sign}")
    observed_ids = [str(record.get("pilot_id")) for record in records]
    if len(records) != 11 or set(observed_ids) != expected_ids or len(set(observed_ids)) != 11:
        errors.append("technical pilot is not the exact 11-trial frozen set")
    calibrated_single = []
    calibrated_aggregate = []
    final_caps = 0
    induction_caps = 0
    for record in records:
        zero = record.get("kind") == "zero"
        if not record.get("induction_nonempty") or not record.get("final_nonempty"):
            errors.append(f"empty pilot generation: {record.get('pilot_id')}")
        for turn in ("induction_diagnostics", "final_diagnostics"):
            errors.extend(
                f"{record.get('pilot_id')} {turn}: {error}"
                for error in diagnostics_errors(record.get(turn, {}), zero)
            )
        final_caps += int(bool(record.get("final_cap_hit")))
        induction_caps += int(bool(record.get("induction_cap_hit")))
        relative = record.get("final_diagnostics", {}).get("relative_hidden_delta_rms")
        if relative is not None and record.get("kind") == "calibrated_single":
            calibrated_single.append(float(relative))
        if relative is not None and record.get("kind") == "calibrated_aggregate":
            calibrated_aggregate.append(float(relative))
        for hash_key in ("induction_sha256", "final_sha256"):
            value = str(record.get(hash_key, ""))
            if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
                errors.append(f"invalid {hash_key}: {record.get('pilot_id')}")
    single_median = statistics.median(calibrated_single) if calibrated_single else None
    aggregate_median = statistics.median(calibrated_aggregate) if calibrated_aggregate else None
    if single_median is None or not 0.03 <= single_median <= 0.08:
        errors.append("calibrated-single median is outside [0.03, 0.08]")
    if aggregate_median is None or not 0.04 <= aggregate_median <= 0.15:
        errors.append("calibrated-aggregate median is outside [0.04, 0.15]")
    if final_caps / len(records) > 0.05:
        errors.append("final cap rate exceeds 5%")
    if induction_caps / len(records) > 0.20:
        errors.append("induction cap rate exceeds 20%")
    return {
        "status": "pass" if not errors else "fail",
        "errors": errors,
        "n_records": len(records),
        "single_median": single_median,
        "aggregate_median": aggregate_median,
        "final_cap_rate": final_caps / len(records) if records else 1.0,
        "induction_cap_rate": induction_caps / len(records) if records else 1.0,
    }


def audit_calibration(
    template_dir: Path,
    calibration_path: Path,
    prior_calibration_path: Path | None = None,
) -> dict[str, Any]:
    errors = []
    calibration = json.loads(calibration_path.read_text(encoding="utf-8"))
    manifest_path = template_dir / "MANIFEST.json"
    plan_audit_path = template_dir / "independent_plan_audit.json"
    with (template_dir / "calibration_candidate_pool.csv").open(
        encoding="utf-8", newline=""
    ) as handle:
        candidates = [int(row["feature_id"]) for row in csv.DictReader(handle)]
    expected_candidate_hash = candidate_hash(candidates)

    exact_fields = {
        "protocol_version": PROTOCOL_VERSION,
        "model": MODEL_ID,
        "model_revision": MODEL_REVISION,
        "sae": SAE_ID,
        "sae_revision": SAE_REVISION,
    }
    for key, expected in exact_fields.items():
        if calibration.get(key) != expected:
            errors.append(f"{key} differs from the frozen value")
    if calibration.get("candidate_pool_sha256") != expected_candidate_hash:
        errors.append("candidate-pool hash differs")
    if calibration.get("precalibration_manifest_sha256") != sha256_file(manifest_path):
        errors.append("precalibration manifest hash differs")
    if calibration.get("precalibration_audit_sha256") != sha256_file(plan_audit_path):
        errors.append("precalibration audit hash differs")
    forbidden = recursively_find_forbidden_keys(calibration)
    if forbidden:
        errors.append(f"forbidden generated-text keys present: {forbidden}")

    feature_rows = calibration.get("feature_metrics", [])
    feature_ids = [int(row.get("feature_id", -1)) for row in feature_rows]
    expected_ids = [*TARGET_IDS, *candidates]
    if feature_ids != expected_ids or len(set(feature_ids)) != len(feature_ids):
        errors.append("feature metrics are not the exact ordered target-plus-candidate set")
    metrics: dict[int, dict[str, float]] = {}
    for row in feature_rows:
        feature_id = int(row.get("feature_id", -1))
        try:
            metrics[feature_id] = {metric: float(row[metric]) for metric in MATCH_METRICS} | {
                "max_abs_target_cosine": float(row["max_abs_target_cosine"])
            }
        except (KeyError, TypeError, ValueError):
            errors.append(f"invalid feature metrics for {feature_id}")
            continue
        if not all(math.isfinite(value) for value in metrics[feature_id].values()):
            errors.append(f"nonfinite feature metrics for {feature_id}")
        if metrics[feature_id]["decoder_norm"] < 0:
            errors.append(f"negative decoder norm for {feature_id}")
        if feature_id in TARGET_IDS and metrics[feature_id]["decoder_norm"] <= 0:
            errors.append(f"nonpositive target decoder norm for {feature_id}")

    hidden_rms = calibration.get("hidden_rms_by_prompt", {})
    if set(hidden_rms) != PROMPT_NAMES:
        errors.append("hidden-RMS prompt names differ")
    if any(not math.isfinite(float(value)) or float(value) <= 0 for value in hidden_rms.values()):
        errors.append("hidden-RMS values must be finite and positive")
    expected_current_multiplier = None
    prior_calibration = None
    if all(feature_id in metrics for feature_id in TARGET_IDS) and set(hidden_rms) == PROMPT_NAMES:
        unit_doses = [
            metrics[feature_id]["decoder_norm"]
            / (math.sqrt(int(calibration["d_model"])) * float(prompt_rms))
            for feature_id in TARGET_IDS
            for prompt_rms in hidden_rms.values()
        ]
        independent_multiplier = round(0.05 / (0.6 * statistics.median(unit_doses)), 3)
        expected_current_multiplier = independent_multiplier
        if calibration.get("formula_calibrated_multiplier") is not None and float(
            calibration["formula_calibrated_multiplier"]
        ) != independent_multiplier:
            errors.append("recorded formula multiplier differs from independent recomputation")
        if prior_calibration_path is None:
            method_name = calibration.get("calibration_method", {}).get("name")
            if method_name not in {None, "analytic_decoder_rms_formula_v1"}:
                errors.append("initial calibration has an unexpected calibration method")
        else:
            prior_calibration = json.loads(prior_calibration_path.read_text(encoding="utf-8"))
            method = calibration.get("calibration_method", {})
            if method.get("name") != "amendment_1_empirical_single_rms_rescale":
                errors.append("amended calibration method name differs")
            if method.get("prior_calibration_sha256") != sha256_file(prior_calibration_path):
                errors.append("amended calibration references a different prior artifact")
            if prior_calibration.get("status") != "fail":
                errors.append("Amendment 1 prior calibration is not failed")
            if prior_calibration.get("candidate_pool_sha256") != expected_candidate_hash:
                errors.append("Amendment 1 prior candidate pool differs")
            if float(prior_calibration.get("calibrated_multiplier", math.nan)) != independent_multiplier:
                errors.append("Amendment 1 prior multiplier differs from the analytic formula")
            prior_gate = prior_calibration.get("technical_pilot", {}).get("gate", {})
            prior_errors = [str(error) for error in prior_gate.get("errors", [])]
            required_prefixes = (
                "calibrated single median RMS outside [0.03, 0.08]",
                "calibrated aggregate median RMS outside [0.04, 0.15]",
            )
            matched_prefixes = {
                prefix
                for prefix in required_prefixes
                if any(error.startswith(prefix) for error in prior_errors)
            }
            if len(prior_errors) != 2 or matched_prefixes != set(required_prefixes):
                errors.append("Amendment 1 prior failure reasons differ")
            observed_single = float(
                prior_gate.get("calibrated_single_final_relative_rms_median", math.nan)
            )
            expected_current_multiplier = round(
                independent_multiplier * 0.05 / observed_single,
                3,
            )
            if float(method.get("observed_single_median_relative_rms", math.nan)) != observed_single:
                errors.append("amended calibration records a different prior single RMS")
            if float(method.get("corrected_multiplier", math.nan)) != expected_current_multiplier:
                errors.append("amended calibration method records a different corrected multiplier")
        if float(calibration.get("calibrated_multiplier", math.nan)) != expected_current_multiplier:
            errors.append("calibrated multiplier differs from independent recomputation")
    else:
        independent_multiplier = None

    matching = calibration.get("control_matching", {})
    attempt = matching.get("caliper_attempt", {})
    expected_attempts = {
        "primary_calipers": (0.8, 1.25, 0.15),
        "prespecified_relaxation": (0.67, 1.5, 0.25),
    }
    attempt_name = attempt.get("name")
    if attempt_name not in expected_attempts:
        errors.append("unknown matching caliper attempt")
    elif (
        float(attempt.get("norm_low", math.nan)),
        float(attempt.get("norm_high", math.nan)),
        float(attempt.get("cosine", math.nan)),
    ) != expected_attempts[attempt_name]:
        errors.append("recorded matching calipers differ from the frozen attempt")
    if matching.get("metric_weights") != MATCH_WEIGHTS:
        errors.append("recorded matching weights differ from the frozen weights")
    independently_selected: list[dict[int, int]] = []
    if len(metrics) == len(expected_ids) and attempt_name in expected_attempts:
        norm_low, norm_high, cosine_limit = expected_attempts[attempt_name]
        scales = robust_scales(metrics)
        costs = {}
        for target_id in TARGET_IDS:
            for candidate_id in candidates:
                ratio = metrics[candidate_id]["decoder_norm"] / metrics[target_id]["decoder_norm"]
                if norm_low <= ratio <= norm_high and metrics[candidate_id]["max_abs_target_cosine"] <= cosine_limit:
                    costs[(target_id, candidate_id)] = match_cost(
                        metrics[target_id], metrics[candidate_id], scales
                    )
        remaining = list(candidates)
        for _panel in range(3):
            assignment = minimum_panel(remaining, costs)
            independently_selected.append(assignment)
            selected = set(assignment.values())
            remaining = [feature_id for feature_id in remaining if feature_id not in selected]
        recorded_panels = matching.get("panels", [])
        if len(recorded_panels) != 3:
            errors.append("matching does not contain three panels")
        else:
            for panel_index, (recorded, expected) in enumerate(
                zip(recorded_panels, independently_selected), 1
            ):
                recorded_map = {
                    int(pair["target_feature_id"]): int(pair["control_feature_id"])
                    for pair in recorded.get("pairs", [])
                }
                if int(recorded.get("panel", -1)) != panel_index or recorded_map != expected:
                    errors.append(f"control panel {panel_index} is not the independent minimum-cost assignment")
                for pair in recorded.get("pairs", []):
                    target_id = int(pair["target_feature_id"])
                    control_id = int(pair["control_feature_id"])
                    if abs(float(pair["cost"]) - costs.get((target_id, control_id), math.inf)) > 1e-9:
                        errors.append(f"recorded match cost differs in panel {panel_index}")
        if prior_calibration is not None:
            current_maps = [
                {
                    int(pair["target_feature_id"]): int(pair["control_feature_id"])
                    for pair in panel.get("pairs", [])
                }
                for panel in matching.get("panels", [])
            ]
            prior_maps = [
                {
                    int(pair["target_feature_id"]): int(pair["control_feature_id"])
                    for pair in panel.get("pairs", [])
                }
                for panel in prior_calibration.get("control_matching", {}).get("panels", [])
            ]
            if current_maps != prior_maps:
                errors.append("amendment rerun control IDs differ from the prior calibration")

    pilot = calibration.get("technical_pilot", {})
    independent_pilot = independently_evaluate_pilot(pilot.get("records", []))
    if pilot.get("gate", {}).get("status") != independent_pilot["status"]:
        errors.append("recorded pilot status differs from independent recomputation")
    if calibration.get("status") != independent_pilot["status"]:
        errors.append("calibration status differs from independent pilot status")
    return {
        "status": "pass" if not errors else "fail",
        "errors": errors,
        "calibration_sha256": sha256_file(calibration_path),
        "candidate_pool_sha256": expected_candidate_hash,
        "n_feature_metrics": len(feature_rows),
        "calibrated_multiplier": calibration.get("calibrated_multiplier"),
        "independent_multiplier": independent_multiplier,
        "expected_current_multiplier": expected_current_multiplier,
        "prior_calibration_sha256": (
            sha256_file(prior_calibration_path) if prior_calibration_path is not None else None
        ),
        "independent_control_panels": [
            {str(target): control for target, control in panel.items()}
            for panel in independently_selected
        ],
        "forbidden_text_key_paths": forbidden,
        "independent_pilot": independent_pilot,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--template-dir", type=Path, required=True)
    parser.add_argument("--calibration", type=Path, required=True)
    parser.add_argument("--prior-calibration", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    report = audit_calibration(
        args.template_dir,
        args.calibration,
        args.prior_calibration,
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Independent calibration audit: {report['status'].upper()} -> {args.out}")
    if report["status"] != "pass":
        for error in report["errors"]:
            print(f"- {error}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()

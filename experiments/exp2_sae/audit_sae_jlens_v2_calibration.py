#!/usr/bin/env python3
"""Independently audit SAE/J-lens v2 semantic calibration and matching."""

from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
from pathlib import Path
from typing import Any

import numpy as np
from scipy.optimize import linear_sum_assignment


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from experiments.exp2_sae.public_sae_consciousness_gating import (  # noqa: E402
    MATCH_METRICS,
    MATCH_WEIGHTS,
)
from experiments.exp2_sae.sae_jlens_v2_protocol import (  # noqa: E402
    A1_FAMILIES,
    A2_SUBFAMILIES,
    A2_TARGET_SUBFAMILY,
    CALIBRATION_PLAN_DIR,
    PROTOCOL_VERSION,
    TARGET_FEATURE_IDS,
    read_jsonl,
    semantic_pool_sha256,
    sha256_file,
    write_json,
)


DEFAULT_PLAN_DIR = REPO_ROOT / CALIBRATION_PLAN_DIR


def transform(metric: str, value: float) -> float:
    if metric in {"decoder_norm", "mean_activation", "max_activation"}:
        return math.log1p(max(0.0, value))
    return value


def robust_scales(metrics: dict[int, dict[str, float]]) -> dict[str, float]:
    scales = {}
    for metric in MATCH_METRICS:
        values = [transform(metric, row[metric]) for row in metrics.values()]
        center = statistics.median(values)
        scale = statistics.median(abs(value - center) for value in values) * 1.4826
        if scale <= 1e-12:
            scale = statistics.pstdev(values)
        scales[metric] = scale if scale > 1e-12 else 1.0
    return scales


def cost(
    target: dict[str, float], candidate: dict[str, float], scales: dict[str, float]
) -> float:
    return sum(
        MATCH_WEIGHTS[metric]
        * ((transform(metric, target[metric]) - transform(metric, candidate[metric])) / scales[metric])
        ** 2
        for metric in MATCH_METRICS
    )


def independent_assignment(
    targets: tuple[int, ...],
    candidates: list[int],
    metrics: dict[int, dict[str, float]],
    scales: dict[str, float],
) -> tuple[str, dict[int, int], dict[tuple[int, int], float]]:
    attempts = (
        ("primary", 0.8, 1.25, 0.15),
        ("frozen_relaxation", 0.67, 1.5, 0.25),
    )
    for name, norm_low, norm_high, cosine in attempts:
        matrix = np.full((len(targets), len(candidates)), np.inf, dtype=np.float64)
        edge_costs: dict[tuple[int, int], float] = {}
        for row_index, target_id in enumerate(targets):
            target = metrics[target_id]
            for column_index, candidate_id in enumerate(candidates):
                candidate = metrics[candidate_id]
                norm_ratio = candidate["decoder_norm"] / target["decoder_norm"]
                if not norm_low <= norm_ratio <= norm_high:
                    continue
                if candidate["max_abs_target_cosine"] > cosine:
                    continue
                value = cost(target, candidate, scales)
                matrix[row_index, column_index] = value
                edge_costs[(target_id, candidate_id)] = value
        try:
            row_indices, column_indices = linear_sum_assignment(matrix)
        except ValueError:
            continue
        if len(row_indices) != len(targets) or not np.isfinite(
            matrix[row_indices, column_indices]
        ).all():
            continue
        return (
            name,
            {
                targets[int(row_index)]: candidates[int(column_index)]
                for row_index, column_index in zip(row_indices, column_indices)
            },
            edge_costs,
        )
    raise ValueError("Independent matcher found no complete assignment")


def recursively_forbidden(value: Any, path: str = "$") -> list[str]:
    forbidden = {
        "response",
        "generation",
        "token_logits",
        "jacobian_readout",
        "residual",
        "prediction",
        "auroc",
        "effect",
    }
    found: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            if str(key).lower() in forbidden:
                found.append(f"{path}.{key}")
            found.extend(recursively_forbidden(child, f"{path}.{key}"))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            found.extend(recursively_forbidden(child, f"{path}[{index}]"))
    return found


def audit(plan_dir: Path, calibration_path: Path) -> dict[str, Any]:
    errors: list[str] = []
    calibration = json.loads(calibration_path.read_text(encoding="utf-8"))
    candidates = read_jsonl(plan_dir / "semantic_candidate_pool.jsonl")
    if calibration.get("status") != "pass":
        errors.append("calibration status differs")
    if calibration.get("protocol_version") != PROTOCOL_VERSION:
        errors.append("calibration protocol version differs")
    if calibration.get("plan_manifest_sha256") != sha256_file(
        plan_dir / "PLAN_MANIFEST.json"
    ):
        errors.append("calibration plan-manifest binding differs")
    if calibration.get("candidate_pool_sha256") != semantic_pool_sha256(candidates):
        errors.append("calibration candidate-pool hash differs")
    if calibration.get("behavioral_outputs_generated") is not False:
        errors.append("calibration does not deny behavioral outputs")
    if calibration.get("jacobian_lens_loaded") is not False:
        errors.append("calibration does not deny J-lens loading")
    forbidden = recursively_forbidden(calibration)
    if forbidden:
        errors.append(f"calibration contains forbidden outcome fields: {forbidden[:5]}")

    rows = calibration.get("feature_metrics", [])
    if len(rows) != 144:
        errors.append(f"metric row count differs: {len(rows)}")
    if len({int(row["feature_id"]) for row in rows}) != len(rows):
        errors.append("metric feature IDs are not unique")
    expected_ids = set(TARGET_FEATURE_IDS).union(
        int(row["feature_id"]) for row in candidates
    )
    observed_ids = {int(row["feature_id"]) for row in rows}
    if observed_ids != expected_ids:
        errors.append("metric feature-ID set differs")
    for row in rows:
        for metric in (*MATCH_METRICS, "max_abs_target_cosine"):
            value = float(row.get(metric, math.nan))
            if not math.isfinite(value) or value < 0:
                errors.append(f"invalid {metric} for {row.get('feature_id')}")
                break

    metrics = {
        int(row["feature_id"]): {
            metric: float(row[metric]) for metric in MATCH_METRICS
        }
        | {"max_abs_target_cosine": float(row["max_abs_target_cosine"])}
        for row in rows
    }
    scales = robust_scales(metrics) if len(metrics) == 144 else {}
    pools = {
        (experiment, family): sorted(
            int(row["feature_id"])
            for row in candidates
            if row["experiment"] == experiment and row["semantic_family"] == family
        )
        for experiment, families in (("A1", A1_FAMILIES), ("A2", A2_SUBFAMILIES))
        for family in families
    }
    target_groups = {
        ("A1", family): tuple(TARGET_FEATURE_IDS) for family in A1_FAMILIES
    }
    target_groups.update(
        {
            ("A2", family): tuple(
                target
                for target in TARGET_FEATURE_IDS
                if A2_TARGET_SUBFAMILY[target] == family
            )
            for family in A2_SUBFAMILIES
        }
    )
    expected_selected: dict[tuple[str, str, int], tuple[int, str, float]] = {}
    if scales:
        for key in sorted(pools):
            try:
                attempt, assignment, edge_costs = independent_assignment(
                    target_groups[key], pools[key], metrics, scales
                )
            except ValueError as error:
                errors.append(f"independent matching failed for {key}: {error}")
                continue
            for target_id, candidate_id in assignment.items():
                expected_selected[(key[0], key[1], target_id)] = (
                    candidate_id,
                    attempt,
                    edge_costs[(target_id, candidate_id)],
                )

    selected = calibration.get("semantic_matching", {}).get("selected", [])
    if len(selected) != 24 or len({int(row["feature_id"]) for row in selected}) != 24:
        errors.append("selected semantic features are not 24 unique IDs")
    for row in selected:
        key = (
            str(row["experiment"]),
            str(row["semantic_family"]),
            int(row["target_feature_id"]),
        )
        expected = expected_selected.get(key)
        if expected is None:
            errors.append(f"unexpected selected semantic row: {key}")
            continue
        if int(row["feature_id"]) != expected[0]:
            errors.append(f"independent selected ID differs: {key}")
        if row["caliper_attempt"] != expected[1]:
            errors.append(f"independent caliper attempt differs: {key}")
        if not math.isclose(float(row["cost"]), expected[2], rel_tol=1e-9, abs_tol=1e-9):
            errors.append(f"independent matching cost differs: {key}")

    lexicon = calibration.get("lexicon_tokens", {})
    accepted = lexicon.get("accepted", {})
    all_token_ids: list[int] = []
    for family in (
        "deception_dishonesty",
        "refusal_safety",
        "hedging_uncertainty",
        "formality_politeness",
        "unrelated",
    ):
        rows_for_family = accepted.get(family, [])
        if len(rows_for_family) < 5:
            errors.append(f"lexicon has fewer than five tokens: {family}")
        all_token_ids.extend(int(row["token_id"]) for row in rows_for_family)
    if len(all_token_ids) != len(set(all_token_ids)):
        errors.append("lexicon token IDs overlap across families")

    return {
        "status": "pass" if not errors else "fail",
        "protocol_version": PROTOCOL_VERSION,
        "calibration_sha256": sha256_file(calibration_path),
        "plan_manifest_sha256": sha256_file(plan_dir / "PLAN_MANIFEST.json"),
        "candidate_pool_sha256": semantic_pool_sha256(candidates),
        "metric_rows": len(rows),
        "selected_rows": len(selected),
        "n_errors": len(errors),
        "errors": errors,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan-dir", type=Path, default=DEFAULT_PLAN_DIR)
    parser.add_argument("--calibration", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    result = audit(args.plan_dir.resolve(), args.calibration.resolve())
    write_json(args.out.resolve(), result)
    print(json.dumps(result, indent=2, sort_keys=True))
    if result["status"] != "pass":
        raise SystemExit(1)


if __name__ == "__main__":
    main()

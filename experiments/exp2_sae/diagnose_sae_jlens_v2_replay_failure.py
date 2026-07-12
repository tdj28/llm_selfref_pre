#!/usr/bin/env python3
"""Characterize the SAE/J-lens v2 replay failure without changing its verdict."""

from __future__ import annotations

import argparse
import heapq
import json
import math
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

import numpy as np


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from experiments.exp2_sae.sae_jlens_v2_final_protocol import (  # noqa: E402
    FINAL_PLAN_DIR,
)
from experiments.exp2_sae.sae_jlens_v2_protocol import (  # noqa: E402
    V1_RELEASE_DIR,
    sha256_file,
    write_json,
)


DEFAULT_PLAN_DIR = REPO_ROOT / FINAL_PLAN_DIR
DEFAULT_V1_DIR = REPO_ROOT / V1_RELEASE_DIR
DEFAULT_AMENDMENT = (
    REPO_ROOT
    / "docs/LLAMA70B_SAE_JLENS_V2_POST_OUTCOME_AMENDMENT_20260712.md"
)
THRESHOLDS = (0.0, 0.001, 0.002, 0.005, 0.01, 0.02, 0.03125, 0.05, 0.10, 0.20)
QUANTILES = (0.0, 0.5, 0.9, 0.95, 0.99, 0.999, 0.9999, 1.0)
MAGNITUDE_BINS = (0.0, 1.0, 2.0, 4.0, 8.0, 16.0, math.inf)
EXPECTED_VALUES = 15_571_269
TOP_K = 100


class DiagnosticFailure(RuntimeError):
    """The failed raw run or its canonical replay source is inconsistent."""


def jsonl_rows(paths: Iterable[Path]):
    for path in paths:
        with path.open(encoding="utf-8") as handle:
            for line in handle:
                if line.strip():
                    yield json.loads(line)


def canonical_rows(v1_dir: Path) -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    for row in jsonl_rows(sorted((v1_dir / "paired_results").glob("part-*.jsonl"))):
        trial_id = str(row["trial_id"])
        if trial_id in rows:
            raise DiagnosticFailure(f"Duplicate canonical v1 row: {trial_id}")
        rows[trial_id] = row
    if len(rows) != 1_581:
        raise DiagnosticFailure(f"Expected 1,581 canonical rows, found {len(rows)}")
    return rows


def token_labels(v1_dir: Path, token_ids: list[int]) -> list[str]:
    payload = json.loads((v1_dir / "lexicon_tokens.json").read_text(encoding="utf-8"))
    labels: dict[int, str] = {}
    for family, records in payload["accepted"].items():
        for record in records:
            labels[int(record["token_id"])] = f"{family}:{record['candidate']}"
    return [labels.get(int(token_id), f"token_id:{token_id}") for token_id in token_ids]


def accumulator() -> dict[str, float | int]:
    return {"count": 0, "sum_signed": 0.0, "sum_abs": 0.0, "sum_sq": 0.0,
            "maximum_absolute_error": 0.0, "above_0_02": 0}


def update(summary: dict[str, float | int], signed: np.ndarray) -> None:
    absolute = np.abs(signed)
    summary["count"] = int(summary["count"]) + int(signed.size)
    summary["sum_signed"] = float(summary["sum_signed"]) + float(signed.sum())
    summary["sum_abs"] = float(summary["sum_abs"]) + float(absolute.sum())
    summary["sum_sq"] = float(summary["sum_sq"]) + float(np.square(signed).sum())
    summary["maximum_absolute_error"] = max(
        float(summary["maximum_absolute_error"]), float(absolute.max(initial=0.0))
    )
    summary["above_0_02"] = int(summary["above_0_02"]) + int(
        np.count_nonzero(absolute > 0.02)
    )


def finalize(summary: dict[str, float | int]) -> dict[str, float | int]:
    count = int(summary["count"])
    if count <= 0:
        raise DiagnosticFailure("Attempted to finalize an empty stratum")
    return {
        "count": count,
        "mean_signed_error": float(summary["sum_signed"]) / count,
        "mean_absolute_error": float(summary["sum_abs"]) / count,
        "rmse": math.sqrt(float(summary["sum_sq"]) / count),
        "maximum_absolute_error": float(summary["maximum_absolute_error"]),
        "above_0_02": int(summary["above_0_02"]),
        "proportion_above_0_02": int(summary["above_0_02"]) / count,
    }


def magnitude_label(values: np.ndarray) -> np.ndarray:
    return np.digitize(np.abs(values), MAGNITUDE_BINS[1:-1], right=False)


def verify_failed_run(plan_dir: Path, run_dir: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    run = json.loads((run_dir / "RUN_COMPLETE.json").read_text(encoding="utf-8"))
    gate = json.loads(
        (run_dir / "replay_equivalence_gate.json").read_text(encoding="utf-8")
    )
    if run.get("status") != "replay_gate_failed" or gate.get("status") != "fail":
        raise DiagnosticFailure("This diagnostic requires the failed Stage 1 run")
    if gate.get("storage_fidelity", {}).get("status") != "pass":
        raise DiagnosticFailure("Storage fidelity did not pass")
    if gate.get("v1_reproduction", {}).get("status") != "fail":
        raise DiagnosticFailure("V1 reproduction is not marked failed")
    plan_hash = sha256_file(plan_dir / "PLAN_MANIFEST.json")
    if run.get("plan_manifest_sha256") != plan_hash:
        raise DiagnosticFailure("Run and final plan hashes differ")
    manifest = json.loads(
        (run_dir / "RESULT_MANIFEST.json").read_text(encoding="utf-8")
    )
    for record in manifest.get("files", []):
        path = run_dir / record["path"]
        if (
            not path.is_file()
            or path.stat().st_size != int(record["bytes"])
            or sha256_file(path) != record["sha256"]
        ):
            raise DiagnosticFailure(f"Result-manifest mismatch: {record['path']}")
    return run, gate


def diagnose(plan_dir: Path, v1_dir: Path, run_dir: Path, amendment: Path,
             out: Path) -> dict[str, Any]:
    run, gate = verify_failed_run(plan_dir, run_dir)
    canonical = canonical_rows(v1_dir)
    token_ids = json.loads(
        (run_dir / "lexicon_tokens.json").read_text(encoding="utf-8")
    )["v1_token_ids"]
    labels = token_labels(v1_dir, token_ids)
    all_absolute = np.empty(EXPECTED_VALUES, dtype=np.float32)
    offset = 0
    strata: dict[str, dict[str, dict[str, float | int]]] = {
        key: defaultdict(accumulator)
        for key in ("layer", "position", "transport", "condition_family", "magnitude_bin")
    }
    token_count = np.zeros(len(token_ids), dtype=np.int64)
    token_sum_signed = np.zeros(len(token_ids), dtype=np.float64)
    token_sum_abs = np.zeros(len(token_ids), dtype=np.float64)
    token_sum_sq = np.zeros(len(token_ids), dtype=np.float64)
    token_max_abs = np.zeros(len(token_ids), dtype=np.float64)
    token_above = np.zeros(len(token_ids), dtype=np.int64)
    overall = accumulator()
    top: list[tuple[float, int, dict[str, Any]]] = []
    sequence = 0
    replay_rows = 0
    observed_ids: set[str] = set()
    x_sum = y_sum = x_sq_sum = y_sq_sum = xy_sum = 0.0

    for row in jsonl_rows(sorted((run_dir / "readouts").glob("part-*.jsonl"))):
        source_id = row.get("source_v1_trial_id")
        if source_id is None:
            continue
        source_id = str(source_id)
        if source_id in observed_ids or source_id not in canonical:
            raise DiagnosticFailure(f"Unknown or duplicate replay row: {source_id}")
        observed_ids.add(source_id)
        expected = canonical[source_id]
        if len(row["readouts"]) != len(expected["readouts"]):
            raise DiagnosticFailure(f"Readout count differs: {source_id}")
        for observed, prior in zip(row["readouts"], expected["readouts"]):
            identity = ("layer", "position", "transport")
            if tuple(observed[key] for key in identity) != tuple(
                prior[key] for key in identity
            ):
                raise DiagnosticFailure(f"Readout identity differs: {source_id}")
            current = np.asarray(observed["v1_token_logits"], dtype=np.float64)
            previous = np.asarray(prior["token_logits"], dtype=np.float64)
            if current.shape != (67,) or previous.shape != (67,):
                raise DiagnosticFailure(f"Token-logit width differs: {source_id}")
            signed = current - previous
            absolute = np.abs(signed)
            end = offset + signed.size
            all_absolute[offset:end] = absolute
            offset = end
            update(overall, signed)
            for dimension, value in (
                ("layer", str(observed["layer"])),
                ("position", str(observed["position"])),
                ("transport", str(observed["transport"])),
                ("condition_family", str(row["condition_family"])),
            ):
                update(strata[dimension][value], signed)
            magnitude_indices = magnitude_label(previous)
            for bin_index in np.unique(magnitude_indices):
                mask = magnitude_indices == bin_index
                update(strata["magnitude_bin"][str(int(bin_index))], signed[mask])
            token_count += 1
            token_sum_signed += signed
            token_sum_abs += absolute
            token_sum_sq += np.square(signed)
            token_max_abs = np.maximum(token_max_abs, absolute)
            token_above += absolute > 0.02
            x_sum += float(previous.sum())
            y_sum += float(current.sum())
            x_sq_sum += float(np.square(previous).sum())
            y_sq_sum += float(np.square(current).sum())
            xy_sum += float((previous * current).sum())
            minimum = top[0][0] if len(top) == TOP_K else -1.0
            for token_index in np.flatnonzero(absolute > minimum):
                record = {
                    "source_v1_trial_id": source_id,
                    "v2_trial_id": row["trial_id"],
                    "condition_family": row["condition_family"],
                    "layer": int(observed["layer"]),
                    "position": observed["position"],
                    "transport": observed["transport"],
                    "token_index": int(token_index),
                    "token_id": int(token_ids[token_index]),
                    "token_label": labels[token_index],
                    "canonical": float(previous[token_index]),
                    "replay": float(current[token_index]),
                    "signed_error": float(signed[token_index]),
                    "absolute_error": float(absolute[token_index]),
                }
                item = (record["absolute_error"], sequence, record)
                sequence += 1
                if len(top) < TOP_K:
                    heapq.heappush(top, item)
                elif item[0] > top[0][0]:
                    heapq.heapreplace(top, item)
        replay_rows += 1

    if replay_rows != 1_581 or observed_ids != set(canonical) or offset != EXPECTED_VALUES:
        raise DiagnosticFailure(
            f"Replay coverage differs: rows={replay_rows}, values={offset}"
        )
    values = all_absolute[:offset]
    count = int(overall["count"])
    x_mean, y_mean = x_sum / count, y_sum / count
    covariance = xy_sum / count - x_mean * y_mean
    x_variance = x_sq_sum / count - x_mean * x_mean
    y_variance = y_sq_sum / count - y_mean * y_mean
    correlation = covariance / math.sqrt(x_variance * y_variance)
    threshold_rows = []
    for threshold in THRESHOLDS:
        exceed = int(np.count_nonzero(values > threshold))
        threshold_rows.append(
            {
                "threshold": threshold,
                "count_above": exceed,
                "proportion_above": exceed / len(values),
            }
        )
    bins = []
    for index in range(len(MAGNITUDE_BINS) - 1):
        summary = strata["magnitude_bin"].get(str(index))
        row = (
            finalize(summary)
            if summary is not None and int(summary["count"]) > 0
            else {
                "count": 0,
                "mean_signed_error": None,
                "mean_absolute_error": None,
                "rmse": None,
                "maximum_absolute_error": None,
                "above_0_02": 0,
                "proportion_above_0_02": None,
            }
        )
        row.update(
            {
                "lower_inclusive": MAGNITUDE_BINS[index],
                "upper_exclusive": (
                    MAGNITUDE_BINS[index + 1]
                    if math.isfinite(MAGNITUDE_BINS[index + 1])
                    else None
                ),
            }
        )
        bins.append(row)
    result = {
        "status": "diagnostic_complete_confirmatory_gate_remains_failed",
        "analysis_class": "post_outcome_diagnostic",
        "confirmatory_status": "blocked_by_replay_gate",
        "plan_manifest_sha256": sha256_file(plan_dir / "PLAN_MANIFEST.json"),
        "failed_result_manifest_sha256": sha256_file(run_dir / "RESULT_MANIFEST.json"),
        "amendment_path": amendment.relative_to(REPO_ROOT).as_posix(),
        "amendment_sha256": sha256_file(amendment),
        "frozen_gate": gate,
        "coverage": {"replay_rows": replay_rows, "values": offset},
        "overall": {
            **finalize(overall),
            "pearson_correlation": correlation,
            "absolute_error_quantiles": {
                str(level): float(value)
                for level, value in zip(QUANTILES, np.quantile(values, QUANTILES))
            },
            "thresholds": threshold_rows,
        },
        "by_layer": [
            {"layer": key, **finalize(value)}
            for key, value in sorted(strata["layer"].items(), key=lambda item: int(item[0]))
        ],
        "by_position": [
            {"position": key, **finalize(value)}
            for key, value in sorted(strata["position"].items())
        ],
        "by_transport": [
            {"transport": key, **finalize(value)}
            for key, value in sorted(strata["transport"].items())
        ],
        "by_condition_family": [
            {"condition_family": key, **finalize(value)}
            for key, value in sorted(strata["condition_family"].items())
        ],
        "by_canonical_logit_magnitude": bins,
        "by_token": [
            {
                "token_index": index,
                "token_id": int(token_ids[index]),
                "token_label": labels[index],
                "count": int(token_count[index]),
                "mean_signed_error": float(token_sum_signed[index] / token_count[index]),
                "mean_absolute_error": float(token_sum_abs[index] / token_count[index]),
                "rmse": float(math.sqrt(token_sum_sq[index] / token_count[index])),
                "maximum_absolute_error": float(token_max_abs[index]),
                "above_0_02": int(token_above[index]),
                "proportion_above_0_02": float(token_above[index] / token_count[index]),
            }
            for index in range(len(token_ids))
        ],
        "largest_discrepancies": [
            item[2] for item in sorted(top, key=lambda item: (-item[0], item[1]))
        ],
        "interpretation": (
            "This diagnostic characterizes the registered gate failure. It does not "
            "change the 0.02 maximum-error criterion or convert the run to a pass."
        ),
    }
    write_json(out, result)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan-dir", type=Path, default=DEFAULT_PLAN_DIR)
    parser.add_argument("--v1-dir", type=Path, default=DEFAULT_V1_DIR)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--amendment", type=Path, default=DEFAULT_AMENDMENT)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    result = diagnose(
        args.plan_dir.resolve(),
        args.v1_dir.resolve(),
        args.run_dir.resolve(),
        args.amendment.resolve(),
        args.out.resolve(),
    )
    print(json.dumps({"status": result["status"], "coverage": result["coverage"]}, sort_keys=True))


if __name__ == "__main__":
    main()

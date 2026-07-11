#!/usr/bin/env python3
"""Independently audit structure, hashes, and frozen-plan binding of SAE/J-lens results."""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from experiments.exp2_sae.sae_jlens_protocol import (  # noqa: E402
    PRIMARY_LAYER,
    PRIMARY_POSITION,
    PROTOCOL_VERSION,
    PURSUIT_K,
    TRAJECTORY_LAYERS,
    TRANSPORT_RANDOM_SEEDS,
    read_jsonl,
    sha256_file,
    write_json,
)


DEFAULT_PLAN_DIR = REPO_ROOT / "data/sae_jlens_audit/confirmatory_v1_plan_20260711"
DEFAULT_RUN_DIR = REPO_ROOT / "out/sae_jlens_audit/confirmatory_v1_20260711"


def read_shards(directory: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in sorted(directory.glob("part-*.jsonl")):
        rows.extend(read_jsonl(path))
    return rows


def check(condition: bool, message: str, errors: list[str]) -> None:
    if not condition:
        errors.append(message)


def audit(plan_dir: Path, run_dir: Path) -> dict[str, Any]:
    errors: list[str] = []
    plan_manifest = json.loads(
        (plan_dir / "PLAN_MANIFEST.json").read_text(encoding="utf-8")
    )
    run_status = json.loads((run_dir / "RUN_COMPLETE.json").read_text(encoding="utf-8"))
    check(run_status.get("status") == "complete", "run status is not complete", errors)
    check(
        run_status.get("protocol_version") == PROTOCOL_VERSION,
        "run protocol version differs",
        errors,
    )
    check(
        run_status.get("plan_manifest_sha256")
        == sha256_file(plan_dir / "PLAN_MANIFEST.json"),
        "run is not bound to this plan manifest",
        errors,
    )

    for record in plan_manifest["files"]:
        path = plan_dir / record["path"]
        check(path.is_file(), f"missing plan file: {path}", errors)
        if path.is_file():
            check(
                sha256_file(path) == record["sha256"],
                f"plan hash mismatch: {path}",
                errors,
            )

    result_manifest = json.loads(
        (run_dir / "RESULT_MANIFEST.json").read_text(encoding="utf-8")
    )
    for record in result_manifest["files"]:
        path = run_dir / record["path"]
        check(path.is_file(), f"missing result file: {path}", errors)
        if path.is_file():
            check(
                path.stat().st_size == record["bytes"],
                f"result size mismatch: {path}",
                errors,
            )
            check(
                sha256_file(path) == record["sha256"],
                f"result hash mismatch: {path}",
                errors,
            )

    smoke = json.loads((run_dir / "smoke_test.json").read_text(encoding="utf-8"))
    check(smoke.get("status") == "pass", "direct-addition smoke did not pass", errors)
    check(
        math.isfinite(float(smoke.get("relative_rmse", math.nan)))
        and float(smoke["relative_rmse"]) <= 1e-5,
        "direct-addition relative RMSE exceeds tolerance",
        errors,
    )

    lexicon = json.loads((run_dir / "lexicon_tokens.json").read_text(encoding="utf-8"))
    for group, rows in lexicon.get("accepted", {}).items():
        check(len(rows) >= 3, f"lexicon group {group} has fewer than three tokens", errors)
        check(
            len({int(row["token_id"]) for row in rows}) == len(rows),
            f"lexicon group {group} has duplicate token IDs",
            errors,
        )

    static_plan = read_jsonl(plan_dir / "static_direction_plan.jsonl")
    static = read_jsonl(run_dir / "static_results.jsonl")
    expected_transports = {"jacobian", "identity"} | {
        f"random_j_{index}" for index in range(1, len(TRANSPORT_RANDOM_SEEDS) + 1)
    }
    check(len(static) == len(static_plan) * 2 * 7, "static row count differs", errors)
    static_keys = {
        (row["direction_id"], row["sign"], row["transport"]) for row in static
    }
    check(len(static_keys) == len(static), "static keys are duplicated", errors)
    check(
        {row["transport"] for row in static} == expected_transports,
        "static transports differ",
        errors,
    )
    for row in static:
        check(len(row["top_tokens"]) == 50, "static top-token list is incomplete", errors)
        check(len(row["bottom_tokens"]) == 50, "static bottom-token list is incomplete", errors)
        check(
            math.isfinite(float(row["population_excess_kurtosis"])),
            "nonfinite static kurtosis",
            errors,
        )

    pursuit = read_jsonl(run_dir / "pursuit_results.jsonl")
    check(
        len(pursuit) == len(static_plan) * len(PURSUIT_K),
        "pursuit row count differs",
        errors,
    )
    pursuit_keys = {(row["direction_id"], int(row["k"])) for row in pursuit}
    check(len(pursuit_keys) == len(pursuit), "pursuit keys are duplicated", errors)
    for row in pursuit:
        check(int(row["k"]) in PURSUIT_K, "unexpected pursuit k", errors)
        check(len(row["selected"]) == int(row["k"]), "pursuit selection length differs", errors)
        check(
            math.isfinite(float(row["explained_squared_norm"])),
            "nonfinite pursuit result",
            errors,
        )

    paired_plan = read_jsonl(plan_dir / "paired_plan.jsonl")
    paired = read_shards(run_dir / "paired_results")
    check(len(paired) == len(paired_plan) == 1581, "paired row count differs", errors)
    by_trial = {row["trial_id"]: row for row in paired}
    check(len(by_trial) == len(paired), "paired trial IDs are duplicated", errors)
    check(
        set(by_trial) == {row["trial_id"] for row in paired_plan},
        "paired trial IDs differ from plan",
        errors,
    )
    expected_readout_keys = {
        (layer, position, transport)
        for layer in TRAJECTORY_LAYERS
        for position in (PRIMARY_POSITION, "assistant_boundary", "content_mean")
        for transport in expected_transports
    }
    for plan_row in paired_plan:
        result = by_trial.get(plan_row["trial_id"])
        if result is None:
            continue
        for key, value in plan_row.items():
            check(result.get(key) == value, f"trial plan field differs: {plan_row['trial_id']}:{key}", errors)
        readout_keys = {
            (int(row["layer"]), row["position"], row["transport"])
            for row in result["readouts"]
        }
        check(
            readout_keys == expected_readout_keys,
            f"readout grid differs: {plan_row['trial_id']}",
            errors,
        )
        intervention = result["intervention"]
        if plan_row["condition_family"] == "zero":
            check(intervention["vector_norm"] == 0.0, "zero vector norm is nonzero", errors)
            check(
                intervention["vector_sha256_bfloat16"] is None,
                "zero vector unexpectedly has a hash",
                errors,
            )
            check(intervention["zero_is_true_noop"] is True, "zero is not a true no-op", errors)
        else:
            check(intervention["vector_norm"] > 0.0, "nonzero vector norm is zero", errors)
            check(
                isinstance(intervention["vector_sha256_bfloat16"], str)
                and len(intervention["vector_sha256_bfloat16"]) == 64,
                "nonzero vector hash is invalid",
                errors,
            )

    final_path = run_dir / "FINAL_MANIFEST.json"
    if final_path.is_file():
        final_manifest = json.loads(final_path.read_text(encoding="utf-8"))
        check(final_manifest.get("status") == "complete", "final manifest incomplete", errors)
        for record in final_manifest["files"]:
            path = run_dir / record["path"]
            check(path.is_file(), f"missing final file: {path}", errors)
            if path.is_file():
                check(
                    sha256_file(path) == record["sha256"],
                    f"final hash mismatch: {path}",
                    errors,
                )
        summary_path = run_dir / "analysis/analysis_summary.json"
        check(summary_path.is_file(), "analysis summary missing", errors)
        if summary_path.is_file():
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            check(summary.get("status") == "complete", "analysis status incomplete", errors)
            check(summary.get("n_paired_trials") == 1581, "analysis paired count differs", errors)

    return {
        "status": "pass" if not errors else "fail",
        "protocol_version": PROTOCOL_VERSION,
        "plan_manifest_sha256": sha256_file(plan_dir / "PLAN_MANIFEST.json"),
        "n_static_rows": len(static),
        "n_pursuit_rows": len(pursuit),
        "n_paired_rows": len(paired),
        "n_errors": len(errors),
        "errors": errors,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan-dir", type=Path, default=DEFAULT_PLAN_DIR)
    parser.add_argument("--run-dir", type=Path, default=DEFAULT_RUN_DIR)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    result = audit(args.plan_dir.resolve(), args.run_dir.resolve())
    if args.out:
        write_json(args.out.resolve(), result)
    print(json.dumps(result, indent=2, sort_keys=True))
    if result["status"] != "pass":
        raise SystemExit(1)


if __name__ == "__main__":
    main()

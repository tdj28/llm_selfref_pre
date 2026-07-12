#!/usr/bin/env python3
"""Independently validate the final result-free SAE/J-lens v2 plan."""

from __future__ import annotations

import argparse
import json
import math
import sys
from collections import Counter
from pathlib import Path
from typing import Any

import numpy as np


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from experiments.exp2_sae.sae_jlens_protocol import (  # noqa: E402
    INDIVIDUAL_COEFFICIENT,
    TARGET_FEATURE_IDS,
)
from experiments.exp2_sae.sae_jlens_v2_final_protocol import (  # noqa: E402
    FINAL_PLAN_DIR,
    MODEL_WIDTH,
    PCA_COMPONENTS,
    RANDOM_PROJECTION_SEEDS,
    V1_PLAN_DIR,
    array_sha256,
)
from experiments.exp2_sae.sae_jlens_v2_protocol import (  # noqa: E402
    A1_FAMILIES,
    A2_SUBFAMILIES,
    PROTOCOL_VERSION,
    read_jsonl,
    sha256_file,
    write_json,
)


DEFAULT_PLAN_DIR = REPO_ROOT / FINAL_PLAN_DIR


def forbidden_paths(value: Any, path: str = "$") -> list[str]:
    forbidden = {
        "outcome",
        "prediction",
        "auroc",
        "auprc",
        "brier",
        "effect",
        "result",
        "residual_values",
        "generation",
        "response",
    }
    found: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            lowered = str(key).lower()
            if lowered in forbidden:
                found.append(f"{path}.{key}")
            found.extend(forbidden_paths(child, f"{path}.{key}"))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            found.extend(forbidden_paths(child, f"{path}[{index}]"))
    return found


def validate(plan_dir: Path) -> dict[str, Any]:
    errors: list[str] = []
    manifest_path = plan_dir / "PLAN_MANIFEST.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("status") != "final_result_free_plan":
        errors.append("plan manifest status differs")
    for record in manifest.get("files", []):
        path = plan_dir / record["path"]
        if not path.is_file():
            errors.append(f"missing plan file: {record['path']}")
        elif path.stat().st_size != int(record["bytes"]):
            errors.append(f"plan file byte count differs: {record['path']}")
        elif sha256_file(path) != record["sha256"]:
            errors.append(f"plan file hash differs: {record['path']}")
    for record in manifest.get("source_files", []):
        path = REPO_ROOT / record["path"]
        if not path.is_file() or sha256_file(path) != record["sha256"]:
            errors.append(f"bound source differs: {record['path']}")

    snapshot = json.loads(
        (plan_dir / "protocol_snapshot.json").read_text(encoding="utf-8")
    )
    if snapshot.get("protocol_version") != PROTOCOL_VERSION:
        errors.append("protocol version differs")
    if snapshot.get("trial_counts") != {
        "semantic_comparator": 2_448,
        "total": 4_029,
        "v1_replay": 1_581,
    }:
        errors.append("protocol trial counts differ")

    selected = json.loads(
        (plan_dir / "selected_comparators.json").read_text(encoding="utf-8")
    )
    selected_ids = [int(row["feature_id"]) for row in selected]
    if len(selected_ids) != 24 or len(set(selected_ids)) != 24:
        errors.append("selected comparators are not 24 unique IDs")
    if set(selected_ids) & set(TARGET_FEATURE_IDS):
        errors.append("selected comparators overlap target IDs")
    if Counter(row["experiment"] for row in selected) != {"A1": 18, "A2": 6}:
        errors.append("selected experiment counts differ")
    if Counter(
        row["semantic_family"] for row in selected if row["experiment"] == "A1"
    ) != {family: 6 for family in A1_FAMILIES}:
        errors.append("selected A1 family counts differ")
    if set(
        row["semantic_family"] for row in selected if row["experiment"] == "A2"
    ) != set(A2_SUBFAMILIES):
        errors.append("selected A2 subfamily coverage differs")

    folds = json.loads((plan_dir / "prompt_folds.json").read_text(encoding="utf-8"))
    fold_rows = folds.get("rows", [])
    if len(fold_rows) != 51 or len({row["prompt_id"] for row in fold_rows}) != 51:
        errors.append("prompt-fold rows differ")
    if sorted(Counter(int(row["fold"]) for row in fold_rows).values()) != [
        10,
        10,
        10,
        10,
        11,
    ]:
        errors.append("prompt-fold sizes differ")

    trials = read_jsonl(plan_dir / "trial_plan.jsonl")
    if len(trials) != 4_029:
        errors.append(f"trial row count differs: {len(trials)}")
    if len({row["trial_id"] for row in trials}) != len(trials):
        errors.append("trial IDs are not unique")
    if sorted(int(row["execution_order"]) for row in trials) != list(range(4_029)):
        errors.append("execution order is not a complete permutation")
    replay = [row for row in trials if row.get("source_v1_trial_id") is not None]
    semantic = [row for row in trials if row.get("source_v1_trial_id") is None]
    if len(replay) != 1_581 or len(semantic) != 2_448:
        errors.append("replay/semantic trial split differs")
    v1_rows = read_jsonl(REPO_ROOT / V1_PLAN_DIR / "paired_plan.jsonl")
    v1_ids = {row["trial_id"] for row in v1_rows}
    if {row["source_v1_trial_id"] for row in replay} != v1_ids:
        errors.append("v1 replay source-ID set differs")
    semantic_counts = Counter(int(row["comparator_feature_id"]) for row in semantic)
    if set(semantic_counts) != set(selected_ids) or set(semantic_counts.values()) != {102}:
        errors.append("semantic comparator trial replication differs")
    for row in semantic:
        coefficients = row.get("coefficients", [])
        feature_ids = row.get("feature_ids", [])
        if len(coefficients) != 1 or len(feature_ids) != 1:
            errors.append(f"semantic row is not single-feature: {row.get('trial_id')}")
            break
        if int(feature_ids[0]) != int(row["comparator_feature_id"]):
            errors.append(f"semantic row feature mismatch: {row.get('trial_id')}")
            break
        if not math.isclose(
            abs(float(coefficients[0])), INDIVIDUAL_COEFFICIENT, abs_tol=5e-7
        ):
            errors.append(f"semantic coefficient differs: {row.get('trial_id')}")
            break
    forbidden = forbidden_paths(trials)
    if forbidden:
        errors.append(f"trial plan contains result fields: {forbidden[:5]}")

    reader = json.loads((plan_dir / "reader_plan.json").read_text(encoding="utf-8"))
    reader_ids = [row["reader_id"] for row in reader.get("readers", [])]
    if len(reader_ids) != 14 or len(set(reader_ids)) != 14:
        errors.append("reader ladder does not contain 14 unique readers")
    if reader.get("crossed_holdouts", {}).get("models_per_reader") != 30:
        errors.append("crossed-holdout model count differs")
    for seed in RANDOM_PROJECTION_SEEDS:
        path = plan_dir / "random_projections" / f"projection_seed_{seed}.npy"
        try:
            matrix = np.load(path, allow_pickle=False)
        except Exception as error:  # pragma: no cover - exercised by release audit
            errors.append(f"projection load failed for {seed}: {error}")
            continue
        if matrix.shape != (MODEL_WIDTH, PCA_COMPONENTS):
            errors.append(f"projection shape differs for {seed}")
        if matrix.dtype != np.float32 or not np.isfinite(matrix).all():
            errors.append(f"projection dtype/finiteness differs for {seed}")
        if not np.allclose(np.linalg.norm(matrix, axis=0), 1.0, atol=2e-6):
            errors.append(f"projection columns are not unit norm for {seed}")
        planned = next(
            row
            for row in reader["readers"]
            if row.get("projection_seed") == seed
        )
        if planned["projection_array_sha256"] != array_sha256(matrix):
            errors.append(f"projection array hash differs for {seed}")

    residual = json.loads(
        (plan_dir / "residual_schema.json").read_text(encoding="utf-8")
    )
    if residual.get("row_shape") != [7, 3, MODEL_WIDTH]:
        errors.append("residual row shape differs")
    if residual.get("expected_rows") != 4_029:
        errors.append("residual expected row count differs")
    if residual.get("expected_tensor_bytes") != 1_386_233_856:
        errors.append("residual exact tensor byte count differs")

    osf_project = json.loads(
        (plan_dir / "OSF_PROJECT.json").read_text(encoding="utf-8")
    )
    if not str(osf_project.get("api_url", "")).startswith(
        "https://api.osf.io/v2/nodes/"
    ):
        errors.append("OSF project API URL differs")

    return {
        "status": "pass" if not errors else "fail",
        "protocol_version": PROTOCOL_VERSION,
        "plan_manifest_sha256": sha256_file(manifest_path),
        "trial_rows": len(trials),
        "replay_rows": len(replay),
        "semantic_rows": len(semantic),
        "selected_comparators": len(selected),
        "reader_count": len(reader_ids),
        "n_errors": len(errors),
        "errors": errors,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan-dir", type=Path, default=DEFAULT_PLAN_DIR)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    result = validate(args.plan_dir.resolve())
    if args.out:
        write_json(args.out.resolve(), result)
    print(json.dumps(result, indent=2, sort_keys=True))
    if result["status"] != "pass":
        raise SystemExit(1)


if __name__ == "__main__":
    main()

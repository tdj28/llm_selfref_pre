#!/usr/bin/env python3
"""Independently validate the SAE/J-lens v2 calibration plan structure."""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from experiments.exp2_sae.sae_jlens_v2_protocol import (  # noqa: E402
    A1_EXCLUDE_PATTERNS,
    A1_FAMILIES,
    A1_INCLUDE_PATTERNS,
    A2_EXCLUDE_PATTERNS,
    A2_INCLUDE_PATTERNS,
    A2_SUBFAMILIES,
    CALIBRATION_PLAN_DIR,
    LABEL_SNAPSHOT_DIR,
    PROTOCOL_VERSION,
    TARGET_SEMANTIC_ROOTS,
    excluded_feature_ids,
    read_jsonl,
    semantic_pool_sha256,
    sha256_file,
    write_json,
)


DEFAULT_PLAN_DIR = REPO_ROOT / CALIBRATION_PLAN_DIR
EXPECTED_COUNTS = {
    ("A1", "refusal_safety"): 19,
    ("A1", "hedging_uncertainty"): 25,
    ("A1", "formality_politeness"): 22,
    ("A2", "pretending_impersonation"): 11,
    ("A2", "roleplay_persona"): 51,
    ("A2", "deception_dishonesty"): 10,
}


def any_match(text: str, patterns: tuple[str, ...]) -> bool:
    return any(re.search(pattern, text, re.IGNORECASE) for pattern in patterns)


def validate(plan_dir: Path) -> dict[str, Any]:
    errors: list[str] = []
    manifest = json.loads((plan_dir / "PLAN_MANIFEST.json").read_text(encoding="utf-8"))
    if manifest.get("status") != "frozen_outcome_masked_calibration_plan":
        errors.append("manifest status differs")
    for record in manifest.get("files", []):
        path = plan_dir / record["path"]
        if not path.is_file():
            errors.append(f"missing plan file: {record['path']}")
        elif path.stat().st_size != int(record["bytes"]):
            errors.append(f"plan byte count differs: {record['path']}")
        elif sha256_file(path) != record["sha256"]:
            errors.append(f"plan hash differs: {record['path']}")
    for record in manifest.get("source_files", []):
        path = REPO_ROOT / record["path"]
        if not path.is_file() or sha256_file(path) != record["sha256"]:
            errors.append(f"bound source differs: {record['path']}")

    snapshot = json.loads((plan_dir / "protocol_snapshot.json").read_text(encoding="utf-8"))
    if snapshot.get("protocol_version") != PROTOCOL_VERSION:
        errors.append("protocol version differs")
    if snapshot.get("jacobian_lens", {}).get("used_during_calibration") is not False:
        errors.append("calibration plan does not prohibit J-lens use")

    labels = {
        int(row["feature_id"]): row
        for row in read_jsonl(REPO_ROOT / LABEL_SNAPSHOT_DIR / "labels.jsonl")
    }
    candidates = read_jsonl(plan_dir / "semantic_candidate_pool.jsonl")
    if len(candidates) != 138:
        errors.append(f"candidate count differs: {len(candidates)}")
    if len({int(row["feature_id"]) for row in candidates}) != len(candidates):
        errors.append("candidate IDs are not unique")
    if set(int(row["feature_id"]) for row in candidates) & set(excluded_feature_ids()):
        errors.append("candidate pool includes an excluded feature")
    counts = Counter((row.get("experiment"), row.get("semantic_family")) for row in candidates)
    if dict(counts) != EXPECTED_COUNTS:
        errors.append(f"candidate family counts differ: {dict(counts)}")

    target_roots = re.compile("|".join(TARGET_SEMANTIC_ROOTS), re.IGNORECASE)
    for row in candidates:
        feature_id = int(row["feature_id"])
        source = labels.get(feature_id)
        if source is None:
            errors.append(f"candidate lacks snapshotted label: {feature_id}")
            continue
        if row.get("description_sha256") != source.get("description_sha256"):
            errors.append(f"candidate label hash differs: {feature_id}")
        description = str(source["description"])
        experiment = row.get("experiment")
        family = row.get("semantic_family")
        if experiment == "A1":
            matches = [
                name
                for name in A1_FAMILIES
                if any_match(description, A1_INCLUDE_PATTERNS[name])
                and not any_match(description, A1_EXCLUDE_PATTERNS[name])
            ]
            if matches != [family] or target_roots.search(description):
                errors.append(f"A1 selection rule fails: {feature_id}")
        elif experiment == "A2":
            matches = [
                name
                for name in A2_SUBFAMILIES
                if any_match(description, A2_INCLUDE_PATTERNS[name])
                and not any_match(description, A2_EXCLUDE_PATTERNS[name])
            ]
            if matches != [family]:
                errors.append(f"A2 selection rule fails: {feature_id}")
        else:
            errors.append(f"unknown candidate experiment: {feature_id}")

    observed_hash = semantic_pool_sha256(candidates)
    expected_hash = snapshot.get("candidate_pool", {}).get("sha256")
    if observed_hash != expected_hash:
        errors.append("candidate pool hash differs")
    calibration = json.loads((plan_dir / "CALIBRATION_PLAN.json").read_text(encoding="utf-8"))
    if calibration.get("expected_metric_rows") != 144:
        errors.append("expected metric row count differs")
    if calibration.get("expected_selected_rows") != 24:
        errors.append("expected selected row count differs")
    if not calibration.get("forbidden_runtime_outputs"):
        errors.append("forbidden runtime outputs are missing")

    return {
        "status": "pass" if not errors else "fail",
        "protocol_version": PROTOCOL_VERSION,
        "plan_manifest_sha256": sha256_file(plan_dir / "PLAN_MANIFEST.json"),
        "candidate_pool_sha256": observed_hash,
        "candidate_rows": len(candidates),
        "family_counts": {f"{key[0]}:{key[1]}": value for key, value in sorted(counts.items())},
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

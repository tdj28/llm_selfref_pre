#!/usr/bin/env python3
"""Independently validate the final 830-row Gemma causal plan."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PRIMARY_ROLES = {
    "deception_roleplay",
    "subjective_self_report",
    "hedging_refusal",
    "matched_control_1",
    "matched_control_2",
    "matched_control_3",
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def validate(plan_dir: Path) -> dict[str, Any]:
    errors = []
    required = {
        "steering_plan.jsonl",
        "FEATURE_MANIFEST.json",
        "CALIBRATION.json",
        "TRANSFER_GATE.json",
        "PLAN_SUMMARY.json",
        "PLAN_MANIFEST.json",
    }
    missing = sorted(name for name in required if not (plan_dir / name).is_file())
    if missing:
        return {"status": "fail", "errors": [f"missing files: {missing}"]}
    rows = read_jsonl(plan_dir / "steering_plan.jsonl")
    if len(rows) != 830:
        errors.append(f"steering rows are {len(rows)}, expected 830")
    ids = [row.get("trial_id") for row in rows]
    if len(set(ids)) != len(ids) or None in ids:
        errors.append("trial IDs are missing or duplicated")
    if sorted(int(row.get("execution_order", -1)) for row in rows) != list(range(830)):
        errors.append("execution order is not exactly 0..829")
    design_counts = Counter(row.get("design") for row in rows)
    if design_counts != Counter(
        {
            "primary_layer20_131k": 600,
            "primary_zero": 50,
            "layer_localization": 120,
            "width_robustness": 60,
        }
    ):
        errors.append(f"design counts differ: {design_counts}")
    primary = [row for row in rows if row.get("design") == "primary_layer20_131k"]
    if {row.get("analysis_role") for row in primary} != PRIMARY_ROLES:
        errors.append("primary roles differ")
    for role in PRIMARY_ROLES:
        role_rows = [row for row in primary if row.get("analysis_role") == role]
        if Counter(row.get("sign") for row in role_rows) != Counter(
            {"suppression": 50, "amplification": 50}
        ):
            errors.append(f"primary role sign counts differ: {role}")
    block_cells: dict[tuple[str, str], set[str]] = defaultdict(set)
    for row in rows:
        if row.get("sign") in {"suppression", "amplification"}:
            block_cells[(str(row.get("design")), str(row.get("block_id")))].add(
                str(row.get("sign"))
            )
        if len(row.get("feature_ids", [])) != 6:
            errors.append(f"trial does not contain six features: {row.get('trial_id')}")
        if len(row.get("active_q90", [])) != 6:
            errors.append(f"trial does not contain six quantiles: {row.get('trial_id')}")
        if any(float(value) <= 0 for value in row.get("active_q90", [])):
            errors.append(f"trial has nonpositive active quantile: {row.get('trial_id')}")
        sign = row.get("sign")
        alpha = float(row.get("calibration_alpha", -1))
        if sign == "zero" and alpha != 0:
            errors.append("zero trial has nonzero alpha")
        if sign != "zero" and not 0.01 <= alpha <= 2.0:
            errors.append(f"nonzero trial alpha out of range: {row.get('trial_id')}")
        if row.get("temperature") != 0.5 or row.get("top_p") != 1.0:
            errors.append("generation sampling parameters differ")
        if row.get("induction_max_tokens") != 256 or row.get("final_max_tokens") != 256:
            errors.append("generation caps differ")
    if any(signs != {"suppression", "amplification"} for signs in block_cells.values()):
        errors.append("one or more paired blocks lacks a sign")
    zero_rows = [row for row in rows if row.get("sign") == "zero"]
    if len(zero_rows) != 50 or len({row["block_id"] for row in zero_rows}) != 50:
        errors.append("zero grid differs from 50 unique blocks")

    features = json.loads((plan_dir / "FEATURE_MANIFEST.json").read_text(encoding="utf-8"))
    calibration = json.loads((plan_dir / "CALIBRATION.json").read_text(encoding="utf-8"))
    if features.get("selection_used_behavioral_outcomes") is not False:
        errors.append("feature manifest is not outcome-naive")
    if calibration.get("status") != "pass":
        errors.append("calibration did not pass")
    if features.get("calibration_sha256") != sha256_file(plan_dir / "CALIBRATION.json"):
        errors.append("feature manifest calibration hash differs")
    controls = features.get("matched_control_panels", [])
    if len(controls) != 3 or any(len(panel) != 6 for panel in controls):
        errors.append("matched control panels differ from 3 x 6")
    flattened = [int(value) for panel in controls for value in panel]
    if len(set(flattened)) != 18:
        errors.append("matched controls are not disjoint")

    manifest = json.loads((plan_dir / "PLAN_MANIFEST.json").read_text(encoding="utf-8"))
    listed = {entry["path"]: entry for entry in manifest.get("files", [])}
    for name in required - {"PLAN_MANIFEST.json"}:
        path = plan_dir / name
        record = listed.get(name)
        if record is None:
            errors.append(f"manifest omits {name}")
        elif record.get("sha256") != sha256_file(path) or record.get("bytes") != path.stat().st_size:
            errors.append(f"manifest differs for {name}")
    return {
        "status": "pass" if not errors else "fail",
        "audited_at_utc": datetime.now(timezone.utc).isoformat(),
        "errors": errors,
        "n_rows": len(rows),
        "n_unique_trial_ids": len(set(ids)),
        "primary_roles": sorted(PRIMARY_ROLES),
        "behavioral_outcomes_read": False,
        "production_module_imported": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("plan_dir", type=Path)
    args = parser.parse_args()
    result = validate(args.plan_dir.resolve())
    output = args.plan_dir.resolve() / "independent_plan_audit.json"
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    lock = {
        "status": "locked" if result["status"] == "pass" else "invalid",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "steering_plan_sha256": sha256_file(
            args.plan_dir.resolve() / "steering_plan.jsonl"
        ),
        "feature_manifest_sha256": sha256_file(
            args.plan_dir.resolve() / "FEATURE_MANIFEST.json"
        ),
        "calibration_sha256": sha256_file(
            args.plan_dir.resolve() / "CALIBRATION.json"
        ),
        "transfer_gate_sha256": sha256_file(
            args.plan_dir.resolve() / "TRANSFER_GATE.json"
        ),
        "plan_summary_sha256": sha256_file(
            args.plan_dir.resolve() / "PLAN_SUMMARY.json"
        ),
        "plan_manifest_sha256": sha256_file(
            args.plan_dir.resolve() / "PLAN_MANIFEST.json"
        ),
        "independent_plan_audit_sha256": sha256_file(output),
        "behavioral_steering_outcomes_exist": False,
    }
    (args.plan_dir.resolve() / "PLAN_LOCK.json").write_text(
        json.dumps(lock, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(f"Independent final Gemma plan audit: {result['status'].upper()} -> {output}")
    if result["status"] != "pass":
        raise SystemExit(2)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Freeze the final Gemma causal plan from outcome-naive atlas/calibration inputs."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from experiments.exp2_sae.gemma_scope_9b_protocol import (  # noqa: E402
    PROTOCOL_VERSION,
    build_final_steering_plan,
    sha256_file,
    write_json,
    write_jsonl,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--atlas-dir", type=Path, required=True)
    parser.add_argument("--calibration", type=Path, required=True)
    parser.add_argument("--outdir", type=Path, required=True)
    args = parser.parse_args()
    atlas_dir = args.atlas_dir.resolve()
    calibration_path = args.calibration.resolve()
    outdir = args.outdir.resolve()
    feature_path = atlas_dir / "feature_manifest_precalibration.json"
    feature_manifest = json.loads(feature_path.read_text(encoding="utf-8"))
    calibration = json.loads(calibration_path.read_text(encoding="utf-8"))
    if feature_manifest.get("selection_used_behavioral_outcomes") is not False:
        raise RuntimeError("Feature selection was not outcome-naive")
    if calibration.get("status") != "pass" or calibration.get("protocol_version") != PROTOCOL_VERSION:
        raise RuntimeError("Frozen technical calibration did not pass")
    if calibration.get("feature_manifest_sha256") != sha256_file(feature_path):
        raise RuntimeError("Calibration used a different feature manifest")

    final_features = {
        **feature_manifest,
        "status": "feature_selection_and_calibration_complete",
        "calibration_alpha_by_sae_and_role": calibration[
            "calibration_alpha_by_sae_and_role"
        ],
        "calibration_sha256": sha256_file(calibration_path),
    }
    trials = build_final_steering_plan(final_features)
    outdir.mkdir(parents=True, exist_ok=True)
    write_jsonl(outdir / "steering_plan.jsonl", trials)
    write_json(outdir / "FEATURE_MANIFEST.json", final_features)
    shutil.copy2(calibration_path, outdir / "CALIBRATION.json")
    shutil.copy2(atlas_dir / "transfer_gate.json", outdir / "TRANSFER_GATE.json")
    write_json(
        outdir / "PLAN_SUMMARY.json",
        {
            "status": "final_steering_plan_built_outcome_free",
            "created_at_utc": datetime.now(timezone.utc).isoformat(),
            "protocol_version": PROTOCOL_VERSION,
            "source_commit_before_plan_commit": subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, text=True
            ).strip(),
            "n_trials": len(trials),
            "n_unique_trial_ids": len({row["trial_id"] for row in trials}),
            "atlas_feature_manifest_sha256": sha256_file(feature_path),
            "calibration_sha256": sha256_file(calibration_path),
            "behavioral_steering_outcomes_exist": False,
        },
    )
    manifest_path = outdir / "PLAN_MANIFEST.json"
    files = [
        path
        for path in sorted(outdir.iterdir())
        if path.is_file()
        and path.name
        not in {
            manifest_path.name,
            "independent_plan_audit.json",
            "PLAN_LOCK.json",
        }
    ]
    write_json(
        manifest_path,
        {
            "status": "final_steering_plan_complete",
            "created_at_utc": datetime.now(timezone.utc).isoformat(),
            "protocol_version": PROTOCOL_VERSION,
            "files": [
                {
                    "path": path.name,
                    "bytes": path.stat().st_size,
                    "sha256": sha256_file(path),
                }
                for path in files
            ],
        },
    )
    print(f"Final Gemma steering plan: {len(trials)} rows -> {outdir}")


if __name__ == "__main__":
    main()

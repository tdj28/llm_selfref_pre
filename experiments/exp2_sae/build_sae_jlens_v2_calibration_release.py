#!/usr/bin/env python3
"""Audit and manifest the outcome-masked SAE/J-lens v2 calibration release."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from experiments.exp2_sae.sae_jlens_v2_protocol import (  # noqa: E402
    CALIBRATION_PLAN_DIR,
    PROTOCOL_VERSION,
    sha256_file,
    write_json,
)


DEFAULT_PLAN_DIR = REPO_ROOT / CALIBRATION_PLAN_DIR


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def inventory(run_dir: Path) -> list[dict[str, Any]]:
    excluded = {"RELEASE_MANIFEST.json"}
    return [
        {
            "path": path.relative_to(run_dir).as_posix(),
            "bytes": path.stat().st_size,
            "sha256": sha256_file(path),
        }
        for path in sorted(run_dir.rglob("*"))
        if path.is_file() and path.name not in excluded
    ]


def verify_remote_checksums(run_dir: Path) -> dict[str, Any]:
    path = run_dir / "REMOTE_SHA256SUMS.txt"
    errors = []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        digest, remote_path = line.split(maxsplit=1)
        marker = "/sae_jlens_v2_calibration_20260712/"
        if marker not in remote_path:
            errors.append(f"unexpected remote checksum path: {remote_path}")
            continue
        relative = remote_path.split(marker, 1)[1]
        local = run_dir / relative
        observed = sha256_file(local) if local.is_file() else None
        rows.append(
            {
                "path": relative,
                "remote_sha256": digest,
                "local_sha256": observed,
                "matches": observed == digest,
            }
        )
        if observed != digest:
            errors.append(f"remote/local checksum differs: {relative}")
    if not rows:
        errors.append("remote checksum ledger is empty")
    return {
        "status": "pass" if not errors else "fail",
        "rows": len(rows),
        "errors": errors,
        "files": rows,
    }


def build(plan_dir: Path, run_dir: Path) -> None:
    calibration = json.loads(
        (run_dir / "calibration.json").read_text(encoding="utf-8")
    )
    calibration_audit = json.loads(
        (run_dir / "independent_calibration_audit.json").read_text(encoding="utf-8")
    )
    plan_audit = json.loads(
        (run_dir / "remote_plan_audit.json").read_text(encoding="utf-8")
    )
    ledger = json.loads((run_dir / "RUNPOD_LEDGER.json").read_text(encoding="utf-8"))
    plan_hash = sha256_file(plan_dir / "PLAN_MANIFEST.json")
    errors = []
    if calibration.get("status") != "pass":
        errors.append("calibration status differs")
    if calibration_audit.get("status") != "pass":
        errors.append("independent calibration audit differs")
    if plan_audit.get("status") != "pass":
        errors.append("remote plan audit differs")
    if calibration.get("plan_manifest_sha256") != plan_hash:
        errors.append("calibration plan binding differs")
    if calibration_audit.get("calibration_sha256") != sha256_file(
        run_dir / "calibration.json"
    ):
        errors.append("calibration audit artifact binding differs")
    if calibration.get("behavioral_outputs_generated") is not False:
        errors.append("calibration does not deny behavioral outputs")
    if calibration.get("jacobian_lens_loaded") is not False:
        errors.append("calibration does not deny J-lens loading")
    if calibration_audit.get("metric_rows") != 144:
        errors.append("calibration metric row count differs")
    if calibration_audit.get("selected_rows") != 24:
        errors.append("calibration selected row count differs")
    if ledger.get("delete_verified") is not True:
        errors.append("RunPod deletion is not verified")
    remote = verify_remote_checksums(run_dir)
    errors.extend(remote["errors"])
    if errors:
        raise ValueError(f"Calibration release audit failed: {errors}")

    files = inventory(run_dir)
    release = {
        "schema_version": 1,
        "status": "complete_outcome_masked_calibration_release",
        "created_at_utc": utc_now(),
        "protocol_version": PROTOCOL_VERSION,
        "plan_manifest_sha256": plan_hash,
        "calibration_sha256": sha256_file(run_dir / "calibration.json"),
        "independent_calibration_audit_sha256": sha256_file(
            run_dir / "independent_calibration_audit.json"
        ),
        "counts": {
            "metric_rows": 144,
            "selected_comparators": 24,
            "behavioral_outputs": 0,
            "jacobian_readouts": 0,
            "residual_outcomes": 0,
        },
        "remote_retrieval_audit": remote,
        "runpod_deletion": ledger,
        "files": files,
        "claim_boundary": (
            "This release selects matched semantic comparators using "
            "outcome-masked activation telemetry. It contains no Stage 1 "
            "semantic, reader, residual, behavioral, or consciousness outcome."
        ),
    }
    write_json(run_dir / "RELEASE_MANIFEST.json", release)
    print(
        json.dumps(
            {
                "status": "pass",
                "release_manifest_sha256": sha256_file(
                    run_dir / "RELEASE_MANIFEST.json"
                ),
                "indexed_files": len(files),
                "selected_comparators": 24,
            },
            sort_keys=True,
        )
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan-dir", type=Path, default=DEFAULT_PLAN_DIR)
    parser.add_argument("--run-dir", type=Path, required=True)
    args = parser.parse_args()
    build(args.plan_dir.resolve(), args.run_dir.resolve())


if __name__ == "__main__":
    main()

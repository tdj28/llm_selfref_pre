#!/usr/bin/env python3
"""Build the final public release manifest for the SAE/J-lens audit."""

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

from experiments.exp2_sae.audit_sae_jlens_results import audit  # noqa: E402
from experiments.exp2_sae.sae_jlens_protocol import (  # noqa: E402
    PROTOCOL_VERSION,
    sha256_file,
    write_json,
)


DEFAULT_PLAN_DIR = REPO_ROOT / "data/sae_jlens_audit/confirmatory_v1_plan_20260711"
DEFAULT_RUN_DIR = REPO_ROOT / "data/sae_jlens_audit/confirmatory_v1_20260711"
REMOTE_PREFIX = "/workspace/results/sae_jlens_audit_confirmatory_v1_20260711/"
RUNTIME_COMMIT = "b026faac222e55d7da4f01a30a6a60a468a5f023"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def verify_remote_hashes(run_dir: Path) -> dict[str, Any]:
    ledger = run_dir / "REMOTE_SHA256SUMS.txt"
    errors: list[str] = []
    rows = []
    for line in ledger.read_text(encoding="utf-8").splitlines():
        expected, remote_path = line.split("  ", 1)
        if not remote_path.startswith(REMOTE_PREFIX):
            errors.append(f"unexpected remote prefix: {remote_path}")
            continue
        relative = remote_path[len(REMOTE_PREFIX) :]
        path = run_dir / relative
        if not path.is_file():
            errors.append(f"missing retrieved file: {relative}")
            continue
        observed = sha256_file(path)
        if observed != expected:
            errors.append(f"retrieved hash mismatch: {relative}")
        rows.append({"path": relative, "sha256": expected, "bytes": path.stat().st_size})
    return {
        "status": "pass" if not errors else "fail",
        "listed_files": len(rows) + len(errors),
        "verified_files": len(rows) - sum("hash mismatch" in error for error in errors),
        "errors": errors,
        "ledger_sha256": sha256_file(ledger),
    }


def file_records(root: Path) -> list[dict[str, Any]]:
    records = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.name == "RELEASE_MANIFEST.json":
            continue
        if path.stat().st_size >= 95 * 1024 * 1024:
            raise ValueError(f"Public artifact is too large for ordinary GitHub: {path}")
        records.append(
            {
                "path": path.relative_to(root).as_posix(),
                "bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
        )
    return records


def source_records() -> list[dict[str, Any]]:
    paths = [
        Path(__file__).resolve(),
        Path(__file__).resolve().with_name("analyze_sae_jlens_paired_reference.py"),
        REPO_ROOT / "docs/LLAMA70B_SAE_JLENS_RESULTS.md",
        REPO_ROOT / "docs/SAE_JLENS_POSTRUN_AMENDMENT_20260711.md",
        REPO_ROOT / "technical_blog_posts/Can_A_Jacobian_Lens_Detect_SAE_Steering.md",
    ]
    return [
        {
            "path": path.relative_to(REPO_ROOT).as_posix(),
            "bytes": path.stat().st_size,
            "sha256": sha256_file(path),
        }
        for path in paths
    ]


def build(plan_dir: Path, run_dir: Path) -> dict[str, Any]:
    raw_audit = audit(plan_dir, run_dir)
    if raw_audit["status"] != "pass":
        raise ValueError(f"Structural audit failed: {raw_audit['errors']}")
    remote = verify_remote_hashes(run_dir)
    if remote["status"] != "pass" or remote["listed_files"] != 36:
        raise ValueError(f"Remote retrieval audit failed: {remote}")

    paired_sensitivity_path = run_dir / "analysis/paired_reference_sensitivity.json"
    paired_sensitivity = json.loads(paired_sensitivity_path.read_text(encoding="utf-8"))
    if paired_sensitivity.get("status") != "complete_posthoc_sensitivity":
        raise ValueError("Paired-reference sensitivity is not complete")
    if paired_sensitivity.get("bootstrap_replicates") != 20_000:
        raise ValueError("Paired-reference sensitivity does not use 20,000 replicates")

    runpod_ledger = {
        "provider": "RunPod",
        "pod_id": "c34tng2tpjx96h",
        "pod_name": "codex-llama70b-sae-jlens-20260711",
        "agent_owned": True,
        "other_pods_mutated": False,
        "gpu": "NVIDIA B200",
        "gpu_memory_mib": 183_359,
        "cloud": "Secure Cloud on-demand",
        "cost_per_hour_usd": 5.89,
        "last_started_at_utc": "2026-07-11T23:06:15.125Z",
        "deleted_at_utc_approx": "2026-07-11T23:22:31Z",
        "runtime_seconds_approx": 975.875,
        "estimated_compute_cost_usd": 1.60,
        "retrieval_audit": remote,
        "remote_secret_removed_before_delete": True,
        "delete_http_status": 204,
        "post_delete_direct_get_http_status": 404,
        "post_delete_account_inventory": [],
    }
    write_json(run_dir / "RUNPOD_LEDGER.json", runpod_ledger)
    write_json(run_dir / "analysis/local_independent_audit.json", raw_audit)

    manifest = {
        "schema_version": 1,
        "status": "complete_public_release",
        "created_at_utc": utc_now(),
        "protocol_version": PROTOCOL_VERSION,
        "runtime_commit": RUNTIME_COMMIT,
        "plan_manifest_sha256": sha256_file(plan_dir / "PLAN_MANIFEST.json"),
        "remote_retrieval_audit": remote,
        "structural_audit": raw_audit,
        "counts": {
            "static_rows": 420,
            "pursuit_rows": 120,
            "paired_rows": 1581,
            "confirmatory_bootstrap_replicates": 20_000,
            "posthoc_paired_bootstrap_replicates": 20_000,
        },
        "files": file_records(run_dir),
        "postrun_source_files": source_records(),
        "claim_boundary": (
            "The release supports a paired intervention fingerprint under pinned "
            "public weights, not standalone provenance detection, deception, intent, "
            "belief, or consciousness."
        ),
    }
    write_json(run_dir / "RELEASE_MANIFEST.json", manifest)
    # Verify the manifest is readable and every just-recorded hash still matches.
    reread = json.loads((run_dir / "RELEASE_MANIFEST.json").read_text(encoding="utf-8"))
    for record in reread["files"]:
        path = run_dir / record["path"]
        if sha256_file(path) != record["sha256"]:
            raise RuntimeError(f"Post-write release hash mismatch: {path}")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan-dir", type=Path, default=DEFAULT_PLAN_DIR)
    parser.add_argument("--run-dir", type=Path, default=DEFAULT_RUN_DIR)
    args = parser.parse_args()
    manifest = build(args.plan_dir.resolve(), args.run_dir.resolve())
    print(
        json.dumps(
            {
                "status": manifest["status"],
                "n_files": len(manifest["files"]),
                "total_bytes": sum(record["bytes"] for record in manifest["files"]),
                "plan_manifest_sha256": manifest["plan_manifest_sha256"],
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()

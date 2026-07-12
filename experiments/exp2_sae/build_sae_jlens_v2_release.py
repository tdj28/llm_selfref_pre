#!/usr/bin/env python3
"""Build the complete public SAE/J-lens v2 release manifest."""

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

from experiments.exp2_sae.sae_jlens_v2_final_protocol import (  # noqa: E402
    FINAL_PLAN_DIR,
)
from experiments.exp2_sae.sae_jlens_v2_protocol import (  # noqa: E402
    PROTOCOL_VERSION,
    sha256_file,
    write_json,
)


DEFAULT_PLAN_DIR = REPO_ROOT / FINAL_PLAN_DIR
REMOTE_RUN_MARKER = "/sae_jlens_v2_20260712/"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def inventory(run_dir: Path) -> list[dict[str, Any]]:
    excluded = {"RELEASE_MANIFEST.json", "FINAL_MANIFEST.json"}
    return [
        {
            "path": path.relative_to(run_dir).as_posix(),
            "bytes": path.stat().st_size,
            "sha256": sha256_file(path),
        }
        for path in sorted(run_dir.rglob("*"))
        if path.is_file()
        and path.name not in excluded
        and not path.name.endswith(".tmp")
    ]


def verify_remote_checksums(run_dir: Path) -> dict[str, Any]:
    ledger_path = run_dir / "REMOTE_SHA256SUMS.txt"
    errors = []
    rows = []
    for line in ledger_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        digest, remote_path = line.split(maxsplit=1)
        if REMOTE_RUN_MARKER not in remote_path:
            errors.append(f"unexpected remote checksum path: {remote_path}")
            continue
        relative = remote_path.split(REMOTE_RUN_MARKER, 1)[1]
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


def verify_osf_uploads(
    plan_dir: Path, run_dir: Path, upload_manifest_path: Path
) -> dict[str, Any]:
    uploads = json.loads(upload_manifest_path.read_text(encoding="utf-8"))
    project = json.loads((plan_dir / "OSF_PROJECT.json").read_text(encoding="utf-8"))
    if uploads.get("status") != "verified_complete":
        raise ValueError("OSF upload manifest is not verified complete")
    if uploads.get("project_id") != project["id"]:
        raise ValueError("OSF upload project differs from the final plan")
    records = uploads.get("files", [])
    local_shards = sorted((run_dir / "residuals").glob("part-*.safetensors"))
    if len(records) != 16 or len(local_shards) != 16:
        raise ValueError("Expected 16 local and OSF residual shard records")
    by_path = {str(row["local_path"]): row for row in records}
    for path in local_shards:
        relative = path.relative_to(run_dir).as_posix()
        record = by_path.get(relative)
        if record is None:
            raise ValueError(f"OSF upload record is missing: {relative}")
        if int(record["bytes"]) != path.stat().st_size:
            raise ValueError(f"OSF upload byte count differs: {relative}")
        if record["sha256"] != sha256_file(path):
            raise ValueError(f"OSF upload hash differs: {relative}")
        if not record.get("file_id") or not str(record.get("download_url", "")).startswith(
            "https://"
        ):
            raise ValueError(f"OSF upload identity differs: {relative}")
    return uploads


def build(plan_dir: Path, run_dir: Path, upload_manifest_path: Path) -> None:
    run = json.loads((run_dir / "RUN_COMPLETE.json").read_text(encoding="utf-8"))
    audit = json.loads(
        (run_dir / "analysis/independent_audit.json").read_text(encoding="utf-8")
    )
    if run.get("status") != "complete" or audit.get("status") != "pass":
        raise ValueError("Complete run and passing independent audit are required")
    runpod = json.loads(
        (run_dir / "RUNPOD_LEDGER.json").read_text(encoding="utf-8")
    )
    if (
        runpod.get("delete_verified") is not True
        or runpod.get("agent_owned") is not True
        or runpod.get("other_pods_mutated") is not False
        or runpod.get("delete_http_status") != 204
        or runpod.get("post_delete_direct_get_http_status") != 404
        or runpod.get("post_delete_account_inventory") != []
        or runpod.get("remote_secret_removed_before_delete") is not True
    ):
        raise ValueError("RunPod ownership/deletion evidence differs")
    remote = verify_remote_checksums(run_dir)
    if remote["status"] != "pass":
        raise ValueError(f"Remote/local retrieval audit failed: {remote['errors']}")
    plan_hash = sha256_file(plan_dir / "PLAN_MANIFEST.json")
    if run.get("plan_manifest_sha256") != plan_hash:
        raise ValueError("Run binds a different final plan")
    uploads = verify_osf_uploads(plan_dir, run_dir, upload_manifest_path)
    files = inventory(run_dir)
    total_bytes = sum(int(row["bytes"]) for row in files)
    release = {
        "schema_version": 1,
        "status": "complete_public_release",
        "created_at_utc": utc_now(),
        "protocol_version": PROTOCOL_VERSION,
        "plan_manifest_sha256": plan_hash,
        "freeze_commit": run["freeze_commit"],
        "registration_id": run["registration_id"],
        "registration_url": json.loads(
            (run_dir / "runtime_metadata.json").read_text(encoding="utf-8")
        )["registration_url"],
        "counts": {
            "trial_rows": 4_029,
            "v1_replay_rows": 1_581,
            "semantic_comparator_rows": 2_448,
            "residual_shards": 16,
            "reader_predictions": 17_136,
        },
        "osf_residual_uploads": {
            "project_id": uploads["project_id"],
            "manifest_sha256": sha256_file(upload_manifest_path),
            "files": uploads["files"],
        },
        "remote_retrieval_audit": remote,
        "runpod_deletion": runpod,
        "independent_audit": {
            "path": "analysis/independent_audit.json",
            "sha256": sha256_file(run_dir / "analysis/independent_audit.json"),
        },
        "files": files,
        "total_local_release_bytes": total_bytes,
        "claim_boundary": (
            "This release supports only conditional semantic-specificity and "
            "linear-reader capacity conclusions under the registered access "
            "models. It does not identify hidden belief, provenance, intent, "
            "deception, consciousness, or proprietary Goodfire behavior."
        ),
    }
    write_json(run_dir / "RELEASE_MANIFEST.json", release)
    final = {
        "status": "pass",
        "release_manifest_sha256": sha256_file(run_dir / "RELEASE_MANIFEST.json"),
        "indexed_files": len(files),
        "indexed_bytes": total_bytes,
        "osf_residual_shards": len(uploads["files"]),
    }
    write_json(run_dir / "FINAL_MANIFEST.json", final)
    print(json.dumps(final, indent=2, sort_keys=True))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan-dir", type=Path, default=DEFAULT_PLAN_DIR)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--osf-upload-manifest", type=Path, required=True)
    args = parser.parse_args()
    build(
        args.plan_dir.resolve(),
        args.run_dir.resolve(),
        args.osf_upload_manifest.resolve(),
    )


if __name__ == "__main__":
    main()

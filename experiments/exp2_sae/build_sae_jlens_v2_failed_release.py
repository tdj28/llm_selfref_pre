#!/usr/bin/env python3
"""Build the public release for the failed v2 gate and exploratory follow-up."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from experiments.exp2_sae.sae_jlens_v2_final_protocol import FINAL_PLAN_DIR
from experiments.exp2_sae.sae_jlens_v2_protocol import sha256_file, write_json


DEFAULT_PLAN_DIR = REPO_ROOT / FINAL_PLAN_DIR
RAW_ROOT_FILES = (
    "RUN_COMPLETE.json",
    "RESULT_MANIFEST.json",
    "replay_equivalence_gate.json",
    "runtime_metadata.json",
    "lexicon_tokens.json",
    "smoke_test.json",
    "remote_plan_audit.json",
    "plan_audit.log",
    "run.log",
    "residual_index.csv",
)


class ReleaseFailure(RuntimeError):
    """A required failed-run release artifact or binding differs."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def verify_manifest_files(run_dir: Path, manifest: dict[str, Any]) -> None:
    for record in manifest.get("files", []):
        path = run_dir / record["path"]
        if (
            not path.is_file()
            or path.stat().st_size != int(record["bytes"])
            or sha256_file(path) != record["sha256"]
        ):
            raise ReleaseFailure(f"Raw result-manifest mismatch: {record['path']}")


def verify_remote(run_dir: Path, checksum_path: Path) -> None:
    rows = 0
    for line in checksum_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        digest, relative = line.split(maxsplit=1)
        path = run_dir / relative.removeprefix("./")
        if not path.is_file() or sha256_file(path) != digest:
            raise ReleaseFailure(f"Remote retrieval mismatch: {relative}")
        rows += 1
    if rows != 58:
        raise ReleaseFailure(f"Expected 58 remote checksum rows, found {rows}")


def verify_osf(run_dir: Path, uploads: dict[str, Any]) -> None:
    records = uploads.get("files", [])
    shards = sorted((run_dir / "residuals").glob("part-*.safetensors"))
    if uploads.get("status") != "verified_complete" or len(records) != 16 or len(shards) != 16:
        raise ReleaseFailure("OSF residual upload set is incomplete")
    by_path = {record["local_path"]: record for record in records}
    for shard in shards:
        relative = shard.relative_to(run_dir).as_posix()
        record = by_path.get(relative)
        if (
            record is None
            or int(record["bytes"]) != shard.stat().st_size
            or record["sha256"] != sha256_file(shard)
            or record["downloaded_sha256"] != record["sha256"]
            or not str(record.get("download_url", "")).startswith("https://")
        ):
            raise ReleaseFailure(f"OSF residual record differs: {relative}")


def verify_lifecycle(ledger: dict[str, Any], publication: dict[str, Any]) -> None:
    if not (
        ledger.get("agent_owned") is True
        and ledger.get("other_pods_mutated") is False
        and ledger.get("artifacts_verified_before_delete") is True
        and ledger.get("remote_secret_removed_before_delete") is True
        and ledger.get("delete_http_status") == 204
        and ledger.get("post_delete_direct_get_http_status") == 404
        and ledger.get("delete_verified") is True
        and ledger.get("post_delete_account_inventory") == []
    ):
        raise ReleaseFailure("RunPod lifecycle evidence differs")
    if not (
        publication.get("status") == "public_verified"
        and publication.get("public") is True
        and publication.get("anonymous_api_http_status") == 200
        and publication.get("anonymous_access_verified") is True
    ):
        raise ReleaseFailure("OSF project publication evidence differs")


def inventory(release_dir: Path) -> list[dict[str, Any]]:
    excluded = {"RELEASE_MANIFEST.json", "FINAL_MANIFEST.json"}
    return [
        {
            "path": path.relative_to(release_dir).as_posix(),
            "bytes": path.stat().st_size,
            "sha256": sha256_file(path),
        }
        for path in sorted(release_dir.rglob("*"))
        if path.is_file() and path.name not in excluded
    ]


def copy_release(run_dir: Path, post_failure: Path, checksum_path: Path,
                 ledger_path: Path, publication_path: Path, release_dir: Path) -> None:
    if release_dir.exists() and any(release_dir.iterdir()):
        raise ReleaseFailure(f"Release directory is not empty: {release_dir}")
    release_dir.mkdir(parents=True, exist_ok=True)
    for name in RAW_ROOT_FILES:
        shutil.copy2(run_dir / name, release_dir / name)
    shutil.copy2(checksum_path, release_dir / "REMOTE_SHA256SUMS.txt")
    shutil.copy2(ledger_path, release_dir / "RUNPOD_LEDGER.json")
    shutil.copy2(publication_path, release_dir / "OSF_PROJECT_PUBLICATION.json")
    shutil.copytree(run_dir / "readouts", release_dir / "readouts")
    shutil.copytree(run_dir / "residual_index_parts", release_dir / "residual_index_parts")
    shutil.copytree(post_failure, release_dir / "post_failure")
    (release_dir / "README.md").write_text(
        """# SAE/J-Lens V2 Failed Confirmatory Release

The prospectively frozen 4,029-forward run completed collection but failed its
registered v1 replay-equivalence gate. Storage fidelity passed exactly; v1
reproduction reached a maximum absolute error of 0.25 against a frozen 0.02
maximum. Confirmatory endpoint analysis was therefore blocked.

`readouts/` contains all 16 compact raw readout shards. The 16 BF16 residual
shards are hosted in the public OSF project and bound by
`post_failure/OSF_RESIDUAL_UPLOADS.json`. The dated amendment, diagnostic,
preserved first exploratory attempt, corrected exploratory analysis, figures,
and independent audit are under `post_failure/`.

The post-failure calculations are exploratory. They do not replace the failed
registered result and do not support claims about hidden belief, provenance,
intent, deception, consciousness, or proprietary Goodfire equivalence.
""",
        encoding="utf-8",
    )


def build(plan_dir: Path, run_dir: Path, checksum_path: Path, post_failure: Path,
          ledger_path: Path, publication_path: Path, release_dir: Path) -> dict[str, Any]:
    run = json.loads((run_dir / "RUN_COMPLETE.json").read_text(encoding="utf-8"))
    gate = json.loads(
        (run_dir / "replay_equivalence_gate.json").read_text(encoding="utf-8")
    )
    raw_manifest = json.loads(
        (run_dir / "RESULT_MANIFEST.json").read_text(encoding="utf-8")
    )
    audit = json.loads(
        (post_failure / "analysis/independent_audit.json").read_text(encoding="utf-8")
    )
    analysis = json.loads(
        (post_failure / "analysis/analysis_summary.json").read_text(encoding="utf-8")
    )
    uploads = json.loads(
        (post_failure / "OSF_RESIDUAL_UPLOADS.json").read_text(encoding="utf-8")
    )
    ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    publication = json.loads(publication_path.read_text(encoding="utf-8"))
    if run.get("status") != "replay_gate_failed" or gate.get("status") != "fail":
        raise ReleaseFailure("Release source is not the preserved failed run")
    if gate.get("storage_fidelity", {}).get("status") != "pass":
        raise ReleaseFailure("Storage fidelity did not pass")
    if audit.get("status") != "pass_post_outcome_exploratory_audit":
        raise ReleaseFailure("Independent post-failure audit did not pass")
    if not (
        analysis.get("status") == "post_outcome_exploratory_complete"
        and analysis.get("confirmatory_status") == "blocked_by_replay_gate"
    ):
        raise ReleaseFailure("Exploratory analysis labels differ")
    if run.get("plan_manifest_sha256") != sha256_file(plan_dir / "PLAN_MANIFEST.json"):
        raise ReleaseFailure("Plan binding differs")
    verify_manifest_files(run_dir, raw_manifest)
    verify_remote(run_dir, checksum_path)
    verify_osf(run_dir, uploads)
    verify_lifecycle(ledger, publication)
    copy_release(
        run_dir, post_failure, checksum_path, ledger_path, publication_path, release_dir
    )
    files = inventory(release_dir)
    total_bytes = sum(int(record["bytes"]) for record in files)
    release = {
        "schema_version": 1,
        "status": "complete_public_failed_confirmatory_release",
        "created_at_utc": utc_now(),
        "confirmatory_status": "blocked_by_replay_gate",
        "exploratory_status": "post_outcome_exploratory_complete",
        "freeze_commit": run["freeze_commit"],
        "plan_manifest_sha256": run["plan_manifest_sha256"],
        "registration_id": run["registration_id"],
        "registration_url": "https://osf.io/f3tpv/",
        "osf_project_url": publication["project_url"],
        "source_result_manifest_sha256": sha256_file(run_dir / "RESULT_MANIFEST.json"),
        "source_remote_checksum_sha256": sha256_file(checksum_path),
        "counts": {
            "trial_rows": 4_029,
            "v1_replay_rows": 1_581,
            "semantic_rows": 2_448,
            "residual_shards_on_osf": 16,
            "compact_readout_shards_in_git": 16,
            "reader_predictions": 17_136,
        },
        "registered_gate": gate,
        "independent_audit": {
            "path": "post_failure/analysis/independent_audit.json",
            "sha256": sha256_file(post_failure / "analysis/independent_audit.json"),
        },
        "osf_residual_uploads": {
            "path": "post_failure/OSF_RESIDUAL_UPLOADS.json",
            "sha256": sha256_file(post_failure / "OSF_RESIDUAL_UPLOADS.json"),
            "files": uploads["files"],
        },
        "files": files,
        "total_git_release_bytes": total_bytes,
        "claim_boundary": (
            "The preregistered Stage 1 result is a failed replay-equivalence gate, "
            "so confirmatory endpoint claims are blocked. Post-failure semantic and "
            "reader calculations are exploratory and cannot establish hidden belief, "
            "provenance, intent, deception, consciousness, or proprietary Goodfire equivalence."
        ),
    }
    write_json(release_dir / "RELEASE_MANIFEST.json", release)
    final = {
        "status": "pass_public_failed_confirmatory_release",
        "confirmatory_status": "blocked_by_replay_gate",
        "release_manifest_sha256": sha256_file(release_dir / "RELEASE_MANIFEST.json"),
        "indexed_files": len(files),
        "indexed_bytes": total_bytes,
        "osf_residual_shards": 16,
    }
    write_json(release_dir / "FINAL_MANIFEST.json", final)
    return final


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan-dir", type=Path, default=DEFAULT_PLAN_DIR)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--remote-checksums", type=Path, required=True)
    parser.add_argument("--post-failure", type=Path, required=True)
    parser.add_argument("--runpod-ledger", type=Path, required=True)
    parser.add_argument("--osf-publication", type=Path, required=True)
    parser.add_argument("--release-dir", type=Path, required=True)
    args = parser.parse_args()
    result = build(
        args.plan_dir.resolve(), args.run_dir.resolve(),
        args.remote_checksums.resolve(), args.post_failure.resolve(),
        args.runpod_ledger.resolve(), args.osf_publication.resolve(),
        args.release_dir.resolve(),
    )
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

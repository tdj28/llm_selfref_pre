#!/usr/bin/env python3
"""Fail-closed audit and hash manifest for the complete Gemma Scope release."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def require(path: Path, status: str) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("status") != status:
        raise RuntimeError(f"{path} status is not {status!r}")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("release_dir", type=Path)
    args = parser.parse_args()
    release = args.release_dir.resolve()
    repo_root = Path(__file__).resolve().parents[2]
    baseline = read_jsonl(release / "baseline/baseline_generations.jsonl")
    steering = read_jsonl(release / "steering/steering_generations.jsonl")
    packet = read_jsonl(release / "judging/blinded_judge_packet.jsonl")
    local = read_jsonl(release / "judging/local_gemma_judgments.jsonl")
    external = read_jsonl(release / "judging/external_judgments.jsonl")
    direct = read_jsonl(release / "judging/direct_answer_labels.jsonl")
    expected_counts = {
        "baseline": (baseline, 180),
        "steering": (steering, 830),
        "packet": (packet, 1010),
        "local": (local, 1010),
        "external": (external, 2020),
        "direct": (direct, 1010),
    }
    for name, (rows, expected) in expected_counts.items():
        if len(rows) != expected:
            raise RuntimeError(f"{name} has {len(rows)} rows instead of {expected}")
    trial_ids = {str(row["trial_id"]) for row in baseline + steering}
    if len(trial_ids) != 1010:
        raise RuntimeError("Raw generations do not have 1,010 unique trial IDs")
    for name, rows in (("packet", packet), ("local", local), ("direct", direct)):
        if {str(row["trial_id"]) for row in rows} != trial_ids:
            raise RuntimeError(f"{name} trial IDs differ from raw generations")
    for judge_key in (
        "openai:gpt-4o-mini-2024-07-18",
        "anthropic:claude-haiku-4-5-20251001",
    ):
        ids = {
            str(row["trial_id"])
            for row in external
            if row.get("judge_key") == judge_key
        }
        if ids != trial_ids:
            raise RuntimeError(f"External judge coverage differs: {judge_key}")
    response_hashes = {
        str(row["trial_id"]): row["response_sha256"] for row in baseline + steering
    }
    for row in baseline + steering:
        observed = hashlib.sha256(str(row["response"]).encode("utf-8")).hexdigest()
        if observed != row["response_sha256"]:
            raise RuntimeError(f"Raw response hash differs: {row['trial_id']}")
    if any(
        row["response_sha256"] != response_hashes[str(row["trial_id"])]
        for row in packet
    ):
        raise RuntimeError("Packet response hashes differ from raw generations")

    require(release / "baseline/baseline_complete.json", "baseline_generation_complete_unjudged")
    require(release / "baseline/BASELINE_RUN_MANIFEST.json", "complete")
    require(release / "runtime_smoke.json", "pass")
    atlas_complete = require(release / "atlas/atlas_complete.json", "atlas_complete")
    require(release / "atlas/ATLAS_RUN_MANIFEST.json", "complete")
    require(release / "atlas/CALIBRATION.json", "pass")
    if atlas_complete.get("all_layer_pt_residual_completed"):
        require(release / "atlas/cross_layer_feature_edges.summary.json", "complete")
        if not (release / "atlas/cross_layer_feature_edges.csv").is_file():
            raise RuntimeError("All-layer atlas is missing cross-layer feature links")
    exploratory = release / "atlas_exploratory"
    if exploratory.is_dir():
        exploratory_complete = require(
            exploratory / "exploratory_complete.json", "complete"
        )
        if exploratory_complete.get("post_hoc_after_gate_failure") is not True:
            raise RuntimeError("Exploratory atlas is missing its post-gate label")
        require(exploratory / "cross_layer_feature_edges.summary.json", "complete")
        if not (exploratory / "cross_layer_feature_edges.csv").is_file():
            raise RuntimeError("Exploratory atlas is missing cross-layer links")
    require(release / "steering/steering_complete.json", "steering_generation_complete_unjudged")
    require(release / "steering/STEERING_RUN_MANIFEST.json", "complete")
    require(release / "steering/plan/PLAN_LOCK.json", "locked")
    require(release / "steering/plan/independent_plan_audit.json", "pass")
    require(release / "judging/JUDGE_PACKET_MANIFEST.json", "complete")
    require(release / "judging/local_gemma_judgments.manifest.json", "complete")
    require(release / "judging/external_judgments.manifest.json", "complete")
    protocol_audit = require(release / "analysis/protocol_audit.json", "pass")
    headline_audit = require(release / "analysis/independent_headline_audit.json", "pass")
    verdict = json.loads((release / "analysis/primary_verdict.json").read_text(encoding="utf-8"))
    pngs = sorted((release / "figures").glob("*.png"))
    pdfs = sorted((release / "figures").glob("*.pdf"))
    if len(pngs) < 5 or len(pdfs) != len(pngs):
        raise RuntimeError("Release requires at least five matched PNG/PDF figure pairs")

    output = release / "release_manifest.json"
    files = []
    for path in sorted(release.rglob("*")):
        if path.is_file() and path != output:
            files.append(
                {
                    "path": path.relative_to(release).as_posix(),
                    "bytes": path.stat().st_size,
                    "sha256": sha256_file(path),
                }
            )
    payload = {
        "schema_version": 1,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "git_commit": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=repo_root, text=True
        ).strip(),
        "run_directory": release.relative_to(repo_root).as_posix(),
        "status": "complete",
        "behavioral_verdict": verdict["behavioral_verdict"],
        "specificity_modifier": verdict["specificity_modifier"],
        "transfer_gate": atlas_complete["transfer_gate"],
        "counts": {name: len(rows) for name, (rows, _) in expected_counts.items()},
        "png_figures": len(pngs),
        "pdf_figures": len(pdfs),
        "audits": {
            "protocol": protocol_audit["status"],
            "independent_headlines": headline_audit["status"],
        },
        "files": files,
    }
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Gemma complete release audit: PASS ({len(files)} files) -> {output}")


if __name__ == "__main__":
    main()

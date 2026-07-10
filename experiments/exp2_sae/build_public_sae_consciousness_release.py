#!/usr/bin/env python3
"""Audit and hash the complete confirmatory public-SAE gating release."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


EXPECTED_EXTERNAL_JUDGES = {
    "openai:gpt-4o-mini-2024-07-18",
    "anthropic:claude-haiku-4-5-20251001",
}


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def current_commit(repo_root: Path) -> str:
    return subprocess.check_output(
        ["git", "rev-parse", "HEAD"],
        cwd=repo_root,
        text=True,
    ).strip()


def require_status(path: Path, expected: str = "pass") -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("status") != expected:
        raise ValueError(f"{path} status is not {expected!r}")
    return payload


def exact_unique_ids(rows: list[dict[str, Any]], field: str, expected: int, label: str) -> set[str]:
    identifiers = [str(row.get(field, "")) for row in rows]
    if len(rows) != expected or len(set(identifiers)) != expected or "" in identifiers:
        raise ValueError(f"{label} is not exactly {expected} unique {field} rows")
    return set(identifiers)


def build_release(run_dir: Path, repo_root: Path) -> dict[str, Any]:
    plan_dir = run_dir / "plan"
    judging_dir = run_dir / "judging"
    analysis_dir = run_dir / "analysis"
    figures_dir = run_dir / "figures"
    plan = read_jsonl(plan_dir / "confirmatory_plan.jsonl")
    generations_path = run_dir / "generations.jsonl"
    generations = read_jsonl(generations_path)
    packet_path = judging_dir / "blinded_judge_packet.jsonl"
    packet = read_jsonl(packet_path)
    direct = read_jsonl(judging_dir / "direct_answer_labels.jsonl")
    local = read_jsonl(judging_dir / "local_llama_judgments.jsonl")
    external = read_jsonl(judging_dir / "external_judgments.jsonl")

    plan_ids = exact_unique_ids(plan, "trial_id", 1500, "confirmatory plan")
    generation_ids = exact_unique_ids(generations, "trial_id", 1500, "generations")
    packet_ids = exact_unique_ids(packet, "trial_id", 1500, "blinded judge packet")
    direct_ids = exact_unique_ids(direct, "trial_id", 1500, "direct labels")
    local_ids = exact_unique_ids(local, "trial_id", 1500, "local judgments")
    if not plan_ids == generation_ids == packet_ids == direct_ids == local_ids:
        raise ValueError("Plan, generation, packet, direct-label, and local-judge IDs differ")

    external_keys = Counter(str(row.get("judge_key")) for row in external)
    if external_keys != Counter({key: 1500 for key in EXPECTED_EXTERNAL_JUDGES}):
        raise ValueError(f"External judge panel differs: {external_keys}")
    for judge_key in EXPECTED_EXTERNAL_JUDGES:
        ids = {
            str(row.get("trial_id"))
            for row in external
            if row.get("judge_key") == judge_key
        }
        if ids != plan_ids:
            raise ValueError(f"External judge {judge_key} trial IDs differ from the plan")

    for row in generations:
        response = str(row.get("response", ""))
        if hashlib.sha256(response.encode("utf-8")).hexdigest() != row.get("response_sha256"):
            raise ValueError(f"Generation response hash mismatch: {row.get('trial_id')}")
    response_hashes = {str(row["trial_id"]): row["response_sha256"] for row in generations}
    if any(
        row.get("response_sha256") != response_hashes.get(str(row.get("trial_id")))
        for row in direct
    ):
        raise ValueError("One or more direct-label response hashes differ")

    completion = json.loads((run_dir / "run_complete.json").read_text(encoding="utf-8"))
    if completion.get("status") != "generation_complete_unjudged":
        raise ValueError("Generation completion marker has an unexpected status")
    if completion.get("generations_sha256") != sha256_file(generations_path):
        raise ValueError("Generation completion marker has a stale generation hash")
    packet_manifest = json.loads(
        (judging_dir / "JUDGE_PACKET_MANIFEST.json").read_text(encoding="utf-8")
    )
    if packet_manifest.get("packet_sha256") != sha256_file(packet_path):
        raise ValueError("Judge packet manifest has a stale packet hash")

    plan_audit = require_status(plan_dir / "independent_plan_audit.json")
    calibration_audit = require_status(plan_dir / "independent_calibration_audit.json")
    protocol_audit = require_status(analysis_dir / "protocol_audit.json")
    headline_audit = require_status(analysis_dir / "independent_headline_audit.json")
    primary_verdict = json.loads((analysis_dir / "primary_verdict.json").read_text(encoding="utf-8"))
    figure_pngs = sorted(figures_dir.glob("*.png"))
    figure_pdfs = sorted(figures_dir.glob("*.pdf"))
    if len(figure_pngs) != 4 or len(figure_pdfs) != 4:
        raise ValueError("Release must contain four PNG and four PDF figures")

    output = run_dir / "release_manifest.json"
    files = []
    for path in sorted(run_dir.rglob("*")):
        if not path.is_file() or path == output:
            continue
        files.append(
            {
                "path": path.relative_to(run_dir).as_posix(),
                "bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
        )
    error_rows = {}
    for path in sorted(run_dir.rglob("*.errors.jsonl")):
        error_rows[path.relative_to(run_dir).as_posix()] = len(read_jsonl(path))
    generation_error_path = run_dir / "generation_errors.jsonl"
    if generation_error_path.exists():
        error_rows[generation_error_path.relative_to(run_dir).as_posix()] = len(
            read_jsonl(generation_error_path)
        )
    return {
        "schema_version": 1,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "git_commit": current_commit(repo_root),
        "run_directory": run_dir.relative_to(repo_root).as_posix(),
        "status": "complete",
        "behavioral_verdict": primary_verdict["behavioral_verdict"],
        "specificity_modifier": primary_verdict["specificity_modifier"],
        "counts": {
            "plan_rows": len(plan),
            "generation_rows": len(generations),
            "blinded_packet_rows": len(packet),
            "local_judgments": len(local),
            "external_judgments": len(external),
            "direct_labels": len(direct),
            "png_figures": len(figure_pngs),
            "pdf_figures": len(figure_pdfs),
        },
        "audits": {
            "plan": plan_audit["status"],
            "calibration": calibration_audit["status"],
            "protocol": protocol_audit["status"],
            "independent_headlines": headline_audit["status"],
        },
        "error_rows": error_rows,
        "files": files,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_dir", type=Path)
    args = parser.parse_args()
    repo_root = Path(__file__).resolve().parents[2]
    run_dir = args.run_dir.resolve()
    manifest = build_release(run_dir, repo_root)
    output = run_dir / "release_manifest.json"
    output.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Release audit: PASS ({len(manifest['files'])} files) -> {output}")


if __name__ == "__main__":
    main()

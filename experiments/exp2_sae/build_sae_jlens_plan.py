#!/usr/bin/env python3
"""Build the frozen outcome-blind Llama 70B SAE/J-lens audit plan."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from experiments.exp2_sae.sae_jlens_protocol import (  # noqa: E402
    GATING_PLAN_DIR,
    MAPPING_CORPUS,
    TEMPLATE_ASSIGNMENTS,
    build_paired_plan,
    protocol_snapshot,
    select_template_prompts,
    sha256_file,
    static_direction_plan,
    write_json,
    write_jsonl,
)


DEFAULT_OUTDIR = REPO_ROOT / "data/sae_jlens_audit/confirmatory_v1_plan_20260711"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def file_record(path: Path, root: Path) -> dict[str, object]:
    return {
        "path": path.relative_to(root).as_posix(),
        "bytes": path.stat().st_size,
        "sha256": sha256_file(path),
    }


def build(outdir: Path) -> None:
    outdir.mkdir(parents=True, exist_ok=True)
    if any(outdir.iterdir()):
        raise FileExistsError(f"Plan directory is not empty: {outdir}")

    prompts_path = outdir / "prompt_plan.jsonl"
    static_path = outdir / "static_direction_plan.jsonl"
    paired_path = outdir / "paired_plan.jsonl"
    snapshot_path = outdir / "protocol_snapshot.json"

    write_jsonl(prompts_path, select_template_prompts(REPO_ROOT))
    write_jsonl(static_path, static_direction_plan())
    write_jsonl(paired_path, build_paired_plan(REPO_ROOT))
    write_json(snapshot_path, protocol_snapshot(REPO_ROOT))

    source_paths = [
        Path(__file__).resolve(),
        Path(__file__).resolve().with_name("sae_jlens_protocol.py"),
        Path(__file__).resolve().with_name("validate_sae_jlens_plan.py"),
        Path(__file__).resolve().with_name("run_sae_jlens_audit.py"),
        Path(__file__).resolve().with_name("analyze_sae_jlens_audit.py"),
        Path(__file__).resolve().with_name("audit_sae_jlens_results.py"),
        Path(__file__).resolve().with_name("run_sae_jlens_runpod.sh"),
        Path(__file__).resolve().with_name("sae_jlens_requirements.txt"),
        REPO_ROOT / "docs/LLAMA70B_SAE_JLENS_PROTOCOL.md",
        REPO_ROOT / MAPPING_CORPUS,
        REPO_ROOT / TEMPLATE_ASSIGNMENTS,
        REPO_ROOT / GATING_PLAN_DIR / "control_matching.csv",
        REPO_ROOT / GATING_PLAN_DIR / "aggregate_blocks.jsonl",
        REPO_ROOT / GATING_PLAN_DIR / "calibration.json",
    ]
    files = [prompts_path, static_path, paired_path, snapshot_path]
    manifest = {
        "schema_version": 1,
        "status": "frozen_outcome_blind_plan",
        "created_at_utc": utc_now(),
        "files": [file_record(path, outdir) for path in files],
        "source_files": [
            {
                "path": path.relative_to(REPO_ROOT).as_posix(),
                "bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
            for path in source_paths
        ],
        "result_placeholders": [],
        "claim_boundary": (
            "This manifest freezes design and provenance before GPU outcomes exist."
        ),
    }
    write_json(outdir / "PLAN_MANIFEST.json", manifest)

    # Re-read the emitted files before returning so truncated writes fail now.
    for record in manifest["files"]:
        path = outdir / str(record["path"])
        if sha256_file(path) != record["sha256"]:
            raise RuntimeError(f"Post-write hash mismatch: {path}")
    json.loads(snapshot_path.read_text(encoding="utf-8"))
    print(
        json.dumps(
            {
                "status": "pass",
                "outdir": str(outdir),
                "n_prompts": sum(1 for _ in prompts_path.open(encoding="utf-8")),
                "n_static_directions": sum(
                    1 for _ in static_path.open(encoding="utf-8")
                ),
                "n_paired_trials": sum(1 for _ in paired_path.open(encoding="utf-8")),
            },
            sort_keys=True,
        )
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--outdir", type=Path, default=DEFAULT_OUTDIR)
    args = parser.parse_args()
    build(args.outdir.resolve())


if __name__ == "__main__":
    main()

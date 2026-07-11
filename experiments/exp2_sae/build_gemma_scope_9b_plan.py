#!/usr/bin/env python3
"""Build the outcome-free Gemma Scope baseline, atlas, and steering template."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from experiments.exp2_sae.gemma_scope_9b_protocol import (  # noqa: E402
    MODEL_ID,
    MODEL_REVISION,
    PROTOCOL_VERSION,
    atlas_plan,
    build_baseline_plan,
    sha256_file,
    steering_template,
    write_json,
    write_jsonl,
)


def git_commit() -> str:
    return subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, text=True
    ).strip()


def file_record(path: Path, root: Path) -> dict[str, Any]:
    return {
        "path": path.relative_to(root).as_posix(),
        "bytes": path.stat().st_size,
        "sha256": sha256_file(path),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("outdir", type=Path)
    args = parser.parse_args()
    outdir = args.outdir.resolve()
    outdir.mkdir(parents=True, exist_ok=True)

    baseline = build_baseline_plan()
    write_jsonl(outdir / "baseline_plan.jsonl", baseline)
    write_json(outdir / "ATLAS_PLAN.json", atlas_plan(REPO_ROOT))
    write_json(outdir / "STEERING_TEMPLATE.json", steering_template())
    write_json(
        outdir / "PLAN_SUMMARY.json",
        {
            "status": "outcome_free_plan_built",
            "created_at_utc": datetime.now(timezone.utc).isoformat(),
            "protocol_version": PROTOCOL_VERSION,
            "source_commit_before_plan_commit": git_commit(),
            "model": MODEL_ID,
            "model_revision": MODEL_REVISION,
            "baseline_rows": len(baseline),
            "baseline_unique_trial_ids": len({row["trial_id"] for row in baseline}),
            "future_steering_rows": steering_template()["expected_trial_count"],
            "behavioral_outcomes_exist": False,
            "gpu_required_to_build": False,
        },
    )

    manifest_path = outdir / "PLAN_MANIFEST.json"
    files = [
        path
        for path in sorted(outdir.iterdir())
        if path.is_file()
        and path.name
        not in {manifest_path.name, "independent_plan_audit.json", "PLAN_LOCK.json"}
    ]
    source_paths = [
        Path(__file__).resolve(),
        Path(__file__).resolve().with_name("gemma_scope_9b_protocol.py"),
        REPO_ROOT / "docs/GEMMA_SCOPE_9B_PROTOCOL.md",
        REPO_ROOT / "src/prompts.py",
    ]
    write_json(
        manifest_path,
        {
            "status": "outcome_free_plan_complete",
            "created_at_utc": datetime.now(timezone.utc).isoformat(),
            "protocol_version": PROTOCOL_VERSION,
            "source_commit_before_plan_commit": git_commit(),
            "files": [file_record(path, outdir) for path in files],
            "source_files": [file_record(path, REPO_ROOT) for path in source_paths],
        },
    )
    print(
        f"Gemma plan built: {len(baseline)} baseline rows, "
        f"{steering_template()['expected_trial_count']} future steering rows -> {outdir}"
    )


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Build the outcome-masked SAE/J-lens v2 semantic calibration plan."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from experiments.exp2_sae.sae_jlens_v2_protocol import (  # noqa: E402
    CALIBRATION_PLAN_DIR,
    LABEL_SNAPSHOT_DIR,
    LEXICON_CANDIDATES,
    calibration_snapshot,
    semantic_candidate_pool,
    sha256_file,
    write_json,
    write_jsonl,
)


DEFAULT_OUTDIR = REPO_ROOT / CALIBRATION_PLAN_DIR


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def file_record(path: Path, root: Path) -> dict[str, object]:
    return {
        "path": path.relative_to(root).as_posix(),
        "bytes": path.stat().st_size,
        "sha256": sha256_file(path),
    }


def source_paths() -> list[Path]:
    snapshot_dir = REPO_ROOT / LABEL_SNAPSHOT_DIR
    return [
        REPO_ROOT / "docs/LLAMA70B_SAE_JLENS_V2_PROTOCOL.md",
        REPO_ROOT / "docs/SAE_JLENS_V2_REQUEST_HARD_NEGATIVES_AND_COMPARATORS.md",
        Path(__file__).resolve(),
        Path(__file__).resolve().with_name("sae_jlens_v2_protocol.py"),
        Path(__file__).resolve().with_name("snapshot_neuronpedia_labels.py"),
        Path(__file__).resolve().with_name("validate_sae_jlens_v2_calibration_plan.py"),
        Path(__file__).resolve().with_name("run_sae_jlens_v2_calibration.py"),
        Path(__file__).resolve().with_name("run_sae_jlens_v2_calibration_runpod.sh"),
        Path(__file__).resolve().with_name("audit_sae_jlens_v2_calibration.py"),
        Path(__file__).resolve().with_name("run_public_sae_consciousness_gating.py"),
        Path(__file__).resolve().with_name("public_sae_consciousness_gating.py"),
        Path(__file__).resolve().with_name("replicate_exp2_goodfire_sae.py"),
        REPO_ROOT / "src/prompts.py",
        REPO_ROOT / "requirements-runpod-70b.txt",
        snapshot_dir / "SNAPSHOT_MANIFEST.json",
        snapshot_dir / "labels.jsonl",
        snapshot_dir / "source_objects.jsonl",
        snapshot_dir / "source_config.json",
        snapshot_dir / "missing_feature_ids.json",
    ]


def build(outdir: Path) -> None:
    outdir.mkdir(parents=True, exist_ok=True)
    if any(outdir.iterdir()):
        raise FileExistsError(f"Calibration plan directory is not empty: {outdir}")

    candidates = semantic_candidate_pool(REPO_ROOT)
    candidates_path = outdir / "semantic_candidate_pool.jsonl"
    lexicons_path = outdir / "lexicon_candidates.json"
    snapshot_path = outdir / "protocol_snapshot.json"
    calibration_path = outdir / "CALIBRATION_PLAN.json"

    write_jsonl(candidates_path, candidates)
    write_json(lexicons_path, LEXICON_CANDIDATES)
    snapshot = calibration_snapshot(REPO_ROOT)
    write_json(snapshot_path, snapshot)
    write_json(
        calibration_path,
        {
            "status": "frozen_outcome_masked_calibration_plan",
            "created_at_utc": utc_now(),
            "candidate_pool_sha256": snapshot["candidate_pool"]["sha256"],
            "candidate_pool_size": len(candidates),
            "expected_metric_rows": len(candidates) + 6,
            "expected_selected_rows": 24,
            "allowed_runtime_outputs": [
                "calibration.json",
                "independent_calibration_audit.json",
                "runtime_metadata.json",
                "run.log",
            ],
            "forbidden_runtime_outputs": [
                "generations",
                "responses",
                "jacobian_readouts",
                "residual_shards",
                "detector_predictions",
            ],
            "behavioral_output_policy": snapshot["behavioral_output_policy"],
            "failure_rule": snapshot["matching"]["failure_rule"],
        },
    )

    plan_files = [
        candidates_path,
        lexicons_path,
        snapshot_path,
        calibration_path,
    ]
    sources = source_paths()
    missing = [path for path in sources if not path.is_file()]
    if missing:
        raise FileNotFoundError(f"Missing bound calibration sources: {missing}")
    write_json(
        outdir / "PLAN_MANIFEST.json",
        {
            "schema_version": 1,
            "status": "frozen_outcome_masked_calibration_plan",
            "created_at_utc": utc_now(),
            "files": [file_record(path, outdir) for path in plan_files],
            "source_files": [
                {
                    "path": path.relative_to(REPO_ROOT).as_posix(),
                    "bytes": path.stat().st_size,
                    "sha256": sha256_file(path),
                }
                for path in sources
            ],
            "result_placeholders": [],
            "claim_boundary": (
                "This plan authorizes semantic matching calibration only. It "
                "cannot produce or inspect a v2 J-lens, detector, or behavior outcome."
            ),
        },
    )
    print(
        json.dumps(
            {
                "status": "pass",
                "outdir": str(outdir),
                "candidate_rows": len(candidates),
                "expected_metric_rows": len(candidates) + 6,
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

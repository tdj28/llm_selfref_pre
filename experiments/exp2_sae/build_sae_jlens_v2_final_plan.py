#!/usr/bin/env python3
"""Build the final result-free SAE/J-lens v2 machine plan."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from experiments.exp2_sae.sae_jlens_v2_final_protocol import (  # noqa: E402
    CALIBRATION_RELEASE_DIR,
    FINAL_PLAN_DIR,
    PROMPT_FOLD_SEED,
    RANDOM_PROJECTION_SEEDS,
    V1_PLAN_DIR,
    array_sha256,
    build_final_trial_plan,
    final_protocol_snapshot,
    load_audited_calibration,
    prompt_fold_rows,
    random_projection,
    reader_plan,
    residual_schema,
    semantic_analysis_plan,
    selected_comparator_rows,
)
from experiments.exp2_sae.sae_jlens_v2_protocol import (  # noqa: E402
    sha256_file,
    write_json,
    write_jsonl,
)


DEFAULT_OUTDIR = REPO_ROOT / FINAL_PLAN_DIR
DEFAULT_CALIBRATION = REPO_ROOT / CALIBRATION_RELEASE_DIR / "calibration.json"
DEFAULT_CALIBRATION_AUDIT = (
    REPO_ROOT / CALIBRATION_RELEASE_DIR / "independent_calibration_audit.json"
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def file_record(path: Path, root: Path) -> dict[str, Any]:
    return {
        "path": path.relative_to(root).as_posix(),
        "bytes": path.stat().st_size,
        "sha256": sha256_file(path),
    }


def source_paths(calibration_path: Path, audit_path: Path) -> list[Path]:
    names = (
        "sae_jlens_v2_protocol.py",
        "sae_jlens_v2_final_protocol.py",
        "build_sae_jlens_v2_final_plan.py",
        "validate_sae_jlens_v2_final_plan.py",
        "run_sae_jlens_v2.py",
        "analyze_sae_jlens_v2.py",
        "figure_sae_jlens_v2.py",
        "audit_sae_jlens_v2_results.py",
        "build_sae_jlens_v2_release.py",
        "build_sae_jlens_v2_osf_packet.py",
        "run_sae_jlens_v2_runpod.sh",
        "osf_sae_jlens_v2.py",
        "run_sae_jlens_audit.py",
        "sae_jlens_protocol.py",
    )
    script_dir = Path(__file__).resolve().parent
    v1_plan = REPO_ROOT / V1_PLAN_DIR
    return [
        *(script_dir / name for name in names),
        REPO_ROOT / "docs/LLAMA70B_SAE_JLENS_V2_PROTOCOL.md",
        REPO_ROOT
        / "docs/SAE_JLENS_V2_REQUEST_HARD_NEGATIVES_AND_COMPARATORS.md",
        REPO_ROOT / "experiments/exp2_sae/sae_jlens_requirements.txt",
        v1_plan / "PLAN_MANIFEST.json",
        v1_plan / "prompt_plan.jsonl",
        v1_plan / "paired_plan.jsonl",
        REPO_ROOT
        / "data/sae_jlens_audit/confirmatory_v1_20260711/RELEASE_MANIFEST.json",
        REPO_ROOT
        / "data/sae_jlens_audit/confirmatory_v1_20260711/lexicon_tokens.json",
        calibration_path,
        audit_path,
    ]


def validate_osf_project(path: Path) -> dict[str, Any]:
    project = json.loads(path.read_text(encoding="utf-8"))
    required = {
        "id",
        "title",
        "description_sha256",
        "public",
        "api_url",
        "html_url",
        "created_at_utc",
    }
    missing = sorted(required.difference(project))
    if missing:
        raise ValueError(f"OSF project record lacks fields: {missing}")
    if not str(project["api_url"]).startswith("https://api.osf.io/v2/nodes/"):
        raise ValueError("OSF project API URL differs")
    if not str(project["html_url"]).startswith("https://osf.io/"):
        raise ValueError("OSF project HTML URL differs")
    if project["public"] is not False:
        raise ValueError("OSF project must remain private before registration")
    return {key: project[key] for key in sorted(required)}


def build(
    outdir: Path,
    calibration_path: Path,
    audit_path: Path,
    osf_project_path: Path,
) -> None:
    outdir.mkdir(parents=True, exist_ok=True)
    if any(outdir.iterdir()):
        raise FileExistsError(f"Final plan directory is not empty: {outdir}")
    calibration, audit = load_audited_calibration(calibration_path, audit_path)
    osf_project = validate_osf_project(osf_project_path)

    comparator_path = outdir / "selected_comparators.json"
    lexicon_path = outdir / "lexicon_tokens.json"
    folds_path = outdir / "prompt_folds.json"
    trials_path = outdir / "trial_plan.jsonl"
    residual_path = outdir / "residual_schema.json"
    reader_path = outdir / "reader_plan.json"
    semantic_analysis_path = outdir / "semantic_analysis_plan.json"
    snapshot_path = outdir / "protocol_snapshot.json"
    calibration_provenance_path = outdir / "calibration_provenance.json"
    osf_project_copy_path = outdir / "OSF_PROJECT.json"

    write_json(comparator_path, selected_comparator_rows(calibration))
    write_json(lexicon_path, calibration["lexicon_tokens"])
    write_json(
        folds_path,
        {
            "seed": PROMPT_FOLD_SEED,
            "folds": 5,
            "rows": prompt_fold_rows(REPO_ROOT / V1_PLAN_DIR),
        },
    )
    write_jsonl(
        trials_path,
        build_final_trial_plan(REPO_ROOT / V1_PLAN_DIR, calibration),
    )
    write_json(residual_path, residual_schema())
    write_json(osf_project_copy_path, osf_project)
    write_json(
        calibration_provenance_path,
        {
            "calibration_path": calibration_path.relative_to(REPO_ROOT).as_posix(),
            "calibration_sha256": sha256_file(calibration_path),
            "calibration_audit_path": audit_path.relative_to(REPO_ROOT).as_posix(),
            "calibration_audit_sha256": sha256_file(audit_path),
            "calibration_plan_manifest_sha256": calibration[
                "plan_manifest_sha256"
            ],
            "candidate_pool_sha256": calibration["candidate_pool_sha256"],
            "audit_status": audit["status"],
            "selected_rows": audit["selected_rows"],
        },
    )

    projection_dir = outdir / "random_projections"
    projection_dir.mkdir()
    projection_hashes: dict[int, str] = {}
    projection_paths: list[Path] = []
    for seed in RANDOM_PROJECTION_SEEDS:
        matrix = random_projection(seed)
        projection_hashes[seed] = array_sha256(matrix)
        path = projection_dir / f"projection_seed_{seed}.npy"
        with path.open("wb") as handle:
            np.save(handle, matrix, allow_pickle=False)
        projection_paths.append(path)
    write_json(reader_path, reader_plan(projection_hashes))
    write_json(semantic_analysis_path, semantic_analysis_plan())
    write_json(snapshot_path, final_protocol_snapshot(osf_project))

    plan_files = [
        comparator_path,
        lexicon_path,
        folds_path,
        trials_path,
        residual_path,
        reader_path,
        semantic_analysis_path,
        snapshot_path,
        calibration_provenance_path,
        osf_project_copy_path,
        *projection_paths,
    ]
    sources = source_paths(calibration_path, audit_path)
    missing = [path for path in sources if not path.is_file()]
    if missing:
        raise FileNotFoundError(f"Missing final-plan source files: {missing}")
    write_json(
        outdir / "PLAN_MANIFEST.json",
        {
            "schema_version": 1,
            "status": "final_result_free_plan",
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
            "registration_gate": (
                "A separate accepted OSF registration record must bind this "
                "manifest SHA-256 and the public Git freeze commit before Stage 1."
            ),
            "claim_boundary": final_protocol_snapshot(osf_project)[
                "claim_boundary"
            ],
        },
    )
    print(
        json.dumps(
            {
                "status": "pass",
                "outdir": str(outdir),
                "trial_rows": 4_029,
                "selected_comparators": 24,
                "projection_matrices": len(projection_paths),
            },
            sort_keys=True,
        )
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--outdir", type=Path, default=DEFAULT_OUTDIR)
    parser.add_argument("--calibration", type=Path, default=DEFAULT_CALIBRATION)
    parser.add_argument(
        "--calibration-audit", type=Path, default=DEFAULT_CALIBRATION_AUDIT
    )
    parser.add_argument("--osf-project-json", type=Path, required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    build(
        args.outdir.resolve(),
        args.calibration.resolve(),
        args.calibration_audit.resolve(),
        args.osf_project_json.resolve(),
    )


if __name__ == "__main__":
    main()

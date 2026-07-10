#!/usr/bin/env python3
"""Build frozen pre-calibration or final public-SAE gating plans."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from experiments.exp2_sae.public_sae_consciousness_gating import (  # noqa: E402
    CALIBRATION_PROMPTS,
    PREVIOUSLY_STEERED_CONTROL_IDS,
    TARGET_FEATURE_IDS,
    build_aggregate_blocks,
    build_candidate_pool,
    build_final_trials,
    build_individual_literal_trials,
    candidate_pool_sha256,
    excluded_candidate_ids,
    file_record,
    protocol_snapshot,
    read_jsonl,
    sha256_file,
    utc_now,
    write_csv,
    write_json,
    write_jsonl,
)


DEFAULT_OUTDIR = (
    REPO_ROOT
    / "data/public_sae_consciousness_gating/confirmatory_v1_calibration_plan_20260710"
)


def source_records() -> list[dict[str, object]]:
    paths = [
        REPO_ROOT / "docs/SAE_CONSCIOUSNESS_GATING_PROTOCOL.md",
        REPO_ROOT / "docs/SAE_CONSCIOUSNESS_GATING_AMENDMENT_20260710.md",
        REPO_ROOT / "src/prompts.py",
        Path(__file__).resolve(),
        Path(__file__).resolve().with_name("public_sae_consciousness_gating.py"),
        Path(__file__).resolve().with_name("run_public_sae_consciousness_gating.py"),
        Path(__file__).resolve().with_name("validate_public_sae_consciousness_plan.py"),
        Path(__file__).resolve().with_name("audit_public_sae_consciousness_calibration.py"),
        Path(__file__).resolve().with_name("build_public_sae_gating_judge_packet.py"),
        Path(__file__).resolve().with_name("judge_public_sae_gating_local.py"),
        Path(__file__).resolve().with_name("judge_public_sae_gating_external.py"),
        Path(__file__).resolve().with_name("analyze_public_sae_consciousness_gating.py"),
        Path(__file__).resolve().with_name("audit_public_sae_consciousness_headlines.py"),
        Path(__file__).resolve().with_name("figure_public_sae_consciousness_gating.py"),
        Path(__file__).resolve().with_name("build_public_sae_consciousness_release.py"),
    ]
    return [
        {
            "path": path.relative_to(REPO_ROOT).as_posix(),
            "bytes": path.stat().st_size,
            "sha256": sha256_file(path),
        }
        for path in paths
    ]


def public_reference(path: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return resolved.name


def build_precalibration_plan(outdir: Path) -> None:
    outdir.mkdir(parents=True, exist_ok=True)
    if any(outdir.iterdir()):
        raise FileExistsError(f"Pre-calibration output directory is not empty: {outdir}")
    candidate_ids = build_candidate_pool()
    aggregate_blocks = build_aggregate_blocks()
    individual_trials = build_individual_literal_trials()

    snapshot_path = outdir / "protocol_snapshot.json"
    candidate_path = outdir / "calibration_candidate_pool.csv"
    blocks_path = outdir / "aggregate_blocks.jsonl"
    individual_path = outdir / "individual_literal_plan.jsonl"
    calibration_path = outdir / "CALIBRATION_PLAN.json"

    write_json(snapshot_path, protocol_snapshot())
    write_csv(
        candidate_path,
        [
            {
                "candidate_order": index,
                "feature_id": feature_id,
                "candidate_pool_seed": 20260710,
            }
            for index, feature_id in enumerate(candidate_ids)
        ],
        ["candidate_order", "feature_id", "candidate_pool_seed"],
    )
    write_jsonl(blocks_path, aggregate_blocks)
    write_jsonl(individual_path, individual_trials)
    write_json(
        calibration_path,
        {
            "status": "frozen_pre_calibration_plan",
            "created_at_utc": utc_now(),
            "candidate_pool_sha256": candidate_pool_sha256(candidate_ids),
            "candidate_pool_size": len(candidate_ids),
            "excluded_feature_ids": sorted(excluded_candidate_ids()),
            "previously_steered_control_ids": sorted(PREVIOUSLY_STEERED_CONTROL_IDS),
            "target_feature_ids": list(TARGET_FEATURE_IDS),
            "calibration_prompt_names": list(CALIBRATION_PROMPTS),
            "allowed_filled_fields": [
                "feature_metrics",
                "hidden_rms_by_prompt",
                "d_model",
                "control_matching",
                "calibrated_multiplier",
                "technical_pilot",
                "runtime",
            ],
            "behavioral_output_policy": (
                "Calibration response text must not be printed, persisted, classified, or inspected."
            ),
        },
    )
    tracked = [snapshot_path, candidate_path, blocks_path, individual_path, calibration_path]
    write_json(
        outdir / "MANIFEST.json",
        {
            "schema_version": 1,
            "status": "frozen_pre_calibration_plan",
            "created_at_utc": utc_now(),
            "candidate_pool_sha256": candidate_pool_sha256(candidate_ids),
            "n_candidate_features": len(candidate_ids),
            "n_aggregate_blocks": len(aggregate_blocks),
            "n_individual_literal_trials": len(individual_trials),
            "expected_final_trials": 1500,
            "files": [file_record(path, outdir) for path in tracked],
            "source_files": source_records(),
            "claim_boundary": (
                "This is an outcome-free plan. It does not establish proprietary API equivalence."
            ),
        },
    )


def build_final_plan(
    template_dir: Path,
    calibration_path: Path,
    calibration_audit_path: Path,
    outdir: Path,
) -> None:
    outdir.mkdir(parents=True, exist_ok=True)
    if any(outdir.iterdir()):
        raise FileExistsError(f"Final-plan output directory is not empty: {outdir}")
    template_manifest = json.loads((template_dir / "MANIFEST.json").read_text(encoding="utf-8"))
    calibration = json.loads(calibration_path.read_text(encoding="utf-8"))
    calibration_audit = json.loads(calibration_audit_path.read_text(encoding="utf-8"))
    if calibration_audit.get("status") != "pass":
        raise ValueError("Independent calibration audit must pass before final-plan construction")
    if calibration_audit.get("calibration_sha256") != sha256_file(calibration_path):
        raise ValueError("Independent calibration audit refers to a different calibration artifact")
    candidate_ids = [
        int(row.split(",")[1])
        for row in (template_dir / "calibration_candidate_pool.csv")
        .read_text(encoding="utf-8")
        .splitlines()[1:]
        if row.strip()
    ]
    if calibration.get("candidate_pool_sha256") != candidate_pool_sha256(candidate_ids):
        raise ValueError("Calibration candidate-pool hash does not match the frozen template")
    blocks = read_jsonl(template_dir / "aggregate_blocks.jsonl")
    trials = build_final_trials(blocks, calibration)

    plan_path = outdir / "confirmatory_plan.jsonl"
    control_path = outdir / "control_matching.csv"
    blocks_path = outdir / "aggregate_blocks.jsonl"
    candidate_path = outdir / "calibration_candidate_pool.csv"
    snapshot_path = outdir / "protocol_snapshot.json"
    frozen_calibration_path = outdir / "calibration.json"
    frozen_calibration_audit_path = outdir / "independent_calibration_audit.json"
    write_jsonl(plan_path, trials)
    shutil.copyfile(template_dir / "aggregate_blocks.jsonl", blocks_path)
    shutil.copyfile(template_dir / "calibration_candidate_pool.csv", candidate_path)
    shutil.copyfile(calibration_path, frozen_calibration_path)
    shutil.copyfile(calibration_audit_path, frozen_calibration_audit_path)
    final_snapshot = json.loads(
        (template_dir / "protocol_snapshot.json").read_text(encoding="utf-8")
    )
    final_snapshot.update(
        {
            "status": "frozen_confirmatory_plan",
            "calibrated_multiplier": calibration["calibrated_multiplier"],
            "calibration_sha256": sha256_file(calibration_path),
            "calibration_audit_sha256": sha256_file(calibration_audit_path),
            "control_panels": [
                {
                    "panel": int(panel["panel"]),
                    "mapping": {
                        str(pair["target_feature_id"]): int(pair["control_feature_id"])
                        for pair in panel["pairs"]
                    },
                }
                for panel in calibration["control_matching"]["panels"]
            ],
            "amendment": calibration.get("calibration_method"),
        }
    )
    write_json(snapshot_path, final_snapshot)
    control_rows = [
        {
            "panel": int(panel["panel"]),
            **pair,
        }
        for panel in calibration["control_matching"]["panels"]
        for pair in panel["pairs"]
    ]
    write_csv(
        control_path,
        control_rows,
        [
            "panel",
            "target_feature_id",
            "control_feature_id",
            "cost",
            "decoder_norm_ratio",
            "max_abs_target_cosine",
        ],
    )
    write_json(
        outdir / "PLAN_MANIFEST.json",
        {
            "schema_version": 1,
            "status": "frozen_confirmatory_plan",
            "created_at_utc": utc_now(),
            "n_trials": len(trials),
            "calibrated_multiplier": calibration["calibrated_multiplier"],
            "candidate_pool_sha256": calibration["candidate_pool_sha256"],
            "template_manifest_sha256": sha256_file(template_dir / "MANIFEST.json"),
            "calibration_sha256": sha256_file(calibration_path),
            "calibration_audit_sha256": sha256_file(calibration_audit_path),
            "calibration_path": public_reference(calibration_path),
            "template_dir": public_reference(template_dir),
            "template_status": template_manifest["status"],
            "files": [
                file_record(plan_path, outdir),
                file_record(control_path, outdir),
                file_record(blocks_path, outdir),
                file_record(candidate_path, outdir),
                file_record(snapshot_path, outdir),
                file_record(frozen_calibration_path, outdir),
                file_record(frozen_calibration_audit_path, outdir),
            ],
            "source_files": source_records(),
            "claim_boundary": (
                "Public-weight confirmatory plan; numerical coefficients are not proprietary API units."
            ),
        },
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--outdir", type=Path, default=DEFAULT_OUTDIR)
    parser.add_argument("--template-dir", type=Path)
    parser.add_argument("--calibration", type=Path)
    parser.add_argument("--calibration-audit", type=Path)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    final_inputs = (args.template_dir, args.calibration, args.calibration_audit)
    if any(final_inputs) and not all(final_inputs):
        raise ValueError(
            "Final-plan mode requires --template-dir, --calibration, and --calibration-audit"
        )
    if args.template_dir:
        build_final_plan(
            args.template_dir,
            args.calibration,
            args.calibration_audit,
            args.outdir,
        )
        print(f"Wrote frozen 1,500-trial confirmatory plan to {args.outdir}")
    else:
        build_precalibration_plan(args.outdir)
        print(f"Wrote frozen pre-calibration plan to {args.outdir}")


if __name__ == "__main__":
    main()

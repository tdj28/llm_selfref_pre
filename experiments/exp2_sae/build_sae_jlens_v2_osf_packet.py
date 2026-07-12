#!/usr/bin/env python3
"""Build the deterministic OSF packet after the final Git freeze commit."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from experiments.exp2_sae.sae_jlens_v2_final_protocol import (  # noqa: E402
    CALIBRATION_RELEASE_DIR,
    FINAL_PLAN_DIR,
)
from experiments.exp2_sae.sae_jlens_v2_protocol import (  # noqa: E402
    PROTOCOL_VERSION,
    sha256_file,
    write_json,
)


DEFAULT_PLAN_DIR = REPO_ROOT / FINAL_PLAN_DIR
FIXED_ZIP_TIME = (2026, 7, 12, 0, 0, 0)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def git_head() -> str:
    return subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, text=True
    ).strip()


def tracked_commit(commit: str) -> bool:
    result = subprocess.run(
        ["git", "cat-file", "-e", f"{commit}^{{commit}}"],
        cwd=REPO_ROOT,
        capture_output=True,
        check=False,
    )
    return result.returncode == 0


def packet_sources(plan_dir: Path) -> list[tuple[Path, str]]:
    calibration_dir = REPO_ROOT / CALIBRATION_RELEASE_DIR
    paths = [
        (
            REPO_ROOT / "docs/LLAMA70B_SAE_JLENS_V2_PROTOCOL.md",
            "docs/LLAMA70B_SAE_JLENS_V2_PROTOCOL.md",
        ),
        (
            REPO_ROOT
            / "docs/SAE_JLENS_V2_REQUEST_HARD_NEGATIVES_AND_COMPARATORS.md",
            "docs/SAE_JLENS_V2_REQUEST_HARD_NEGATIVES_AND_COMPARATORS.md",
        ),
        (
            calibration_dir / "calibration.json",
            "calibration/calibration.json",
        ),
        (
            calibration_dir / "independent_calibration_audit.json",
            "calibration/independent_calibration_audit.json",
        ),
    ]
    paths.extend(
        (path, f"final_plan/{path.relative_to(plan_dir).as_posix()}")
        for path in sorted(plan_dir.rglob("*"))
        if path.is_file()
    )
    missing = [path for path, archive_name in paths if not path.is_file()]
    if missing:
        raise FileNotFoundError(f"OSF packet source is missing: {missing}")
    return paths


def summary_text(
    plan_dir: Path, freeze_commit: str, plan_hash: str, selected: list[dict[str, Any]]
) -> str:
    comparator_lines = "\n".join(
        f"- {row['experiment']} / {row['semantic_family']}: target "
        f"{row['target_feature_id']} to comparator {row['feature_id']} "
        f"({row['caliper_attempt']})"
        for row in selected
    )
    return f"""# SAE/J-Lens V2 Preregistration Summary

This Open-Ended Registration freezes the Stage 1 outcome experiment described
in `LLAMA70B_SAE_JLENS_V2_PROTOCOL.md`. It is linked to the private OSF project
that hosts this packet and will host residual shards after the registered run.

## Public Freeze

- Repository: https://github.com/tdj28/llm_selfref_pre
- Freeze commit: `{freeze_commit}`
- Final plan-manifest SHA-256: `{plan_hash}`
- Protocol version: `{PROTOCOL_VERSION}`
- Final machine plan: `{plan_dir.relative_to(REPO_ROOT).as_posix()}`

An earlier result-free freeze at
`5058b8ec254028cee44ec85b3876adae761b5119` was superseded before registration
and before any Stage 1 outcome. Its editable-draft audit showed that OSF
HTML-escaped the `>` characters in comparator arrows. The replacement uses
OSF-stable plain text and adds version-aware packet replacement; no scientific
design or calibrated comparator changed.

## Prior Knowledge And Stage 0 Disclosure

The completed v1 results were known before this design: the crossed-holdout
67-token post-state reader was at chance (AUROC 0.4998), while the separately
post-run paired-reference known-sign score had AUROC 0.8623. Feature 23893
failed its static and known-sign paired checks.

Stage 0 was an outcome-masked calibration using only decoder norms, target
cosines, and SAE activations on four frozen prefixes. It produced no response
text, residual outcome, J-lens readout, detector prediction, or Stage 1 target
outcome. Its complete metrics and independent audit are included in this
packet.

The 24 mechanically selected comparators are:

{comparator_lines}

## Registered Stage 1

The plan fixes 4,029 forwards: all 1,581 v1 rows replayed plus 2,448 semantic
comparator rows. It fixes all seven layers, three positions, BF16 residual
shards, replay-equivalence tolerance, A1 family matrix, A2 target-comparator
contrast, 14-reader ladder, five crossed prompt folds, five stored random
projections, 20,000 template bootstraps, thresholds, failure rules, and claim
boundaries before any Stage 1 outcome. A1 null tests use 20,000 template-cluster
sign flips; reader null tests use 20,000 target/control label randomizations
within feature-pair, template, and sign blocks, with Holm control across all 14
reader rungs.

No Stage 1 outcome existed when this packet and its public Git freeze were
created. Submission of this registration is the authorization gate for Stage
1; a mutable OSF project or editable draft alone is not preregistration.

## Claim Boundary

Results can support only conditional semantic-specificity and linear-reader
capacity claims under the pinned model, SAE, lens, prompts, interventions, and
access models. They cannot establish hidden belief, provenance, intent,
deception, consciousness, subjective experience, or proprietary Goodfire
behavior.
"""


def build(plan_dir: Path, freeze_commit: str, outdir: Path) -> None:
    if freeze_commit != git_head():
        raise ValueError("OSF packet must be built from the current freeze commit")
    if not tracked_commit(freeze_commit):
        raise ValueError("Freeze commit is not a local Git commit")
    plan_manifest = plan_dir / "PLAN_MANIFEST.json"
    plan = json.loads(plan_manifest.read_text(encoding="utf-8"))
    if plan.get("status") != "final_result_free_plan":
        raise ValueError("Final plan status differs")
    for record in plan.get("files", []):
        path = plan_dir / record["path"]
        if not path.is_file() or sha256_file(path) != record["sha256"]:
            raise ValueError(f"Final plan file differs: {path}")
    for record in plan.get("source_files", []):
        path = REPO_ROOT / record["path"]
        if not path.is_file() or sha256_file(path) != record["sha256"]:
            raise ValueError(f"Final plan source differs: {path}")
    plan_hash = sha256_file(plan_manifest)
    selected = json.loads(
        (plan_dir / "selected_comparators.json").read_text(encoding="utf-8")
    )
    if len(selected) != 24:
        raise ValueError("OSF packet requires exactly 24 selected comparators")

    outdir.mkdir(parents=True, exist_ok=True)
    if any(outdir.iterdir()):
        raise FileExistsError(f"OSF packet directory is not empty: {outdir}")
    summary_path = outdir / "OSF_REGISTRATION_SUMMARY.md"
    summary_path.write_text(
        summary_text(plan_dir, freeze_commit, plan_hash, selected), encoding="utf-8"
    )

    zip_path = outdir / "SAE_JLENS_V2_PREREGISTRATION_PACKET.zip"
    sources = packet_sources(plan_dir)
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path, archive_name in sources:
            info = zipfile.ZipInfo(archive_name, date_time=FIXED_ZIP_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, path.read_bytes())
        summary_info = zipfile.ZipInfo(
            "OSF_REGISTRATION_SUMMARY.md", date_time=FIXED_ZIP_TIME
        )
        summary_info.compress_type = zipfile.ZIP_DEFLATED
        summary_info.external_attr = 0o100644 << 16
        archive.writestr(summary_info, summary_path.read_bytes())

    manifest = {
        "schema_version": 1,
        "status": "editable_osf_packet_not_registered",
        "created_at_utc": utc_now(),
        "protocol_version": PROTOCOL_VERSION,
        "freeze_commit": freeze_commit,
        "plan_manifest_sha256": plan_hash,
        "summary": {
            "path": summary_path.name,
            "bytes": summary_path.stat().st_size,
            "sha256": sha256_file(summary_path),
        },
        "packet": {
            "path": zip_path.name,
            "bytes": zip_path.stat().st_size,
            "sha256": sha256_file(zip_path),
        },
        "archived_files": [
            {
                "archive_path": archive_name,
                "bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
            for path, archive_name in sources
        ],
        "stage1_outcomes_present": False,
    }
    write_json(outdir / "OSF_PACKET_MANIFEST.json", manifest)
    print(
        json.dumps(
            {
                "status": "pass",
                "outdir": str(outdir),
                "freeze_commit": freeze_commit,
                "plan_manifest_sha256": plan_hash,
                "packet_sha256": manifest["packet"]["sha256"],
            },
            sort_keys=True,
        )
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan-dir", type=Path, default=DEFAULT_PLAN_DIR)
    parser.add_argument("--freeze-commit", required=True)
    parser.add_argument("--outdir", type=Path, required=True)
    args = parser.parse_args()
    build(args.plan_dir.resolve(), args.freeze_commit, args.outdir.resolve())


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Run frozen v2 endpoints only as a labeled post-replay-failure analysis."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from experiments.exp2_sae import analyze_sae_jlens_v2 as frozen  # noqa: E402
from experiments.exp2_sae.sae_jlens_v2_final_protocol import (  # noqa: E402
    BOOTSTRAP_REPLICATES,
    FINAL_PLAN_DIR,
)
from experiments.exp2_sae.sae_jlens_v2_protocol import (  # noqa: E402
    PROTOCOL_VERSION,
    sha256_file,
    write_json,
)


DEFAULT_PLAN_DIR = REPO_ROOT / FINAL_PLAN_DIR
DEFAULT_AMENDMENT = (
    REPO_ROOT
    / "docs/LLAMA70B_SAE_JLENS_V2_POST_OUTCOME_AMENDMENT_20260712.md"
)
ACKNOWLEDGMENT = "I understand these outputs are post-outcome exploratory"


class PostFailureAnalysisError(RuntimeError):
    """The requested run is not the preserved replay-gate failure."""


def verify_failed_inputs(plan_dir: Path, run_dir: Path) -> None:
    run = json.loads((run_dir / "RUN_COMPLETE.json").read_text(encoding="utf-8"))
    gate = json.loads(
        (run_dir / "replay_equivalence_gate.json").read_text(encoding="utf-8")
    )
    manifest = json.loads(
        (run_dir / "RESULT_MANIFEST.json").read_text(encoding="utf-8")
    )
    if run.get("status") != "replay_gate_failed" or gate.get("status") != "fail":
        raise PostFailureAnalysisError("Run is not the preserved replay-gate failure")
    if gate.get("storage_fidelity", {}).get("status") != "pass":
        raise PostFailureAnalysisError("Storage-fidelity prerequisite did not pass")
    if gate.get("v1_reproduction", {}).get("status") != "fail":
        raise PostFailureAnalysisError("V1 replay is not marked failed")
    if run.get("protocol_version") != PROTOCOL_VERSION:
        raise PostFailureAnalysisError("Protocol version differs")
    if run.get("plan_manifest_sha256") != sha256_file(
        plan_dir / "PLAN_MANIFEST.json"
    ):
        raise PostFailureAnalysisError("Run and plan bindings differ")
    for record in manifest.get("files", []):
        path = run_dir / record["path"]
        if (
            not path.is_file()
            or path.stat().st_size != int(record["bytes"])
            or sha256_file(path) != record["sha256"]
        ):
            raise PostFailureAnalysisError(
                f"Result-manifest mismatch: {record['path']}"
            )


def analyze(plan_dir: Path, run_dir: Path, outdir: Path, amendment: Path,
            diagnostic: Path, acknowledgment: str) -> None:
    if acknowledgment != ACKNOWLEDGMENT:
        raise PostFailureAnalysisError(
            f"Pass --acknowledgment {ACKNOWLEDGMENT!r} exactly"
        )
    verify_failed_inputs(plan_dir, run_dir)
    diagnostic_payload = json.loads(diagnostic.read_text(encoding="utf-8"))
    if diagnostic_payload.get("confirmatory_status") != "blocked_by_replay_gate":
        raise PostFailureAnalysisError("Completed replay diagnostic is required")

    original_verify = frozen.verify_inputs
    try:
        frozen.verify_inputs = verify_failed_inputs
        frozen.analyze(plan_dir, run_dir, outdir, BOOTSTRAP_REPLICATES)
    finally:
        frozen.verify_inputs = original_verify

    summary_path = outdir / "analysis_summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    summary.update(
        {
            "status": "post_outcome_exploratory_complete",
            "analysis_class": "post_outcome_exploratory",
            "confirmatory_status": "blocked_by_replay_gate",
            "frozen_calculations_reused_without_endpoint_tuning": True,
            "failed_result_manifest_sha256": sha256_file(
                run_dir / "RESULT_MANIFEST.json"
            ),
            "replay_diagnostic_path": diagnostic.relative_to(run_dir).as_posix(),
            "replay_diagnostic_sha256": sha256_file(diagnostic),
            "amendment_path": amendment.relative_to(REPO_ROOT).as_posix(),
            "amendment_sha256": sha256_file(amendment),
            "claim_boundary": (
                "These calculations are post-outcome exploratory because the "
                "registered replay-equivalence gate failed. They cannot be called "
                "confirmatory or used to replace the blocked registered result."
            ),
        }
    )
    write_json(summary_path, summary)
    write_json(
        outdir / "POST_FAILURE_ANALYSIS_PROVENANCE.json",
        {
            "status": "complete",
            "analysis_class": "post_outcome_exploratory",
            "confirmatory_status": "blocked_by_replay_gate",
            "frozen_analysis_source": "experiments/exp2_sae/analyze_sae_jlens_v2.py",
            "frozen_analysis_source_sha256": sha256_file(
                REPO_ROOT / "experiments/exp2_sae/analyze_sae_jlens_v2.py"
            ),
            "amendment_sha256": sha256_file(amendment),
            "diagnostic_sha256": sha256_file(diagnostic),
            "plan_manifest_sha256": sha256_file(plan_dir / "PLAN_MANIFEST.json"),
            "failed_result_manifest_sha256": sha256_file(
                run_dir / "RESULT_MANIFEST.json"
            ),
        },
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan-dir", type=Path, default=DEFAULT_PLAN_DIR)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--outdir", type=Path, required=True)
    parser.add_argument("--amendment", type=Path, default=DEFAULT_AMENDMENT)
    parser.add_argument("--diagnostic", type=Path, required=True)
    parser.add_argument("--acknowledgment", required=True)
    args = parser.parse_args()
    analyze(
        args.plan_dir.resolve(),
        args.run_dir.resolve(),
        args.outdir.resolve(),
        args.amendment.resolve(),
        args.diagnostic.resolve(),
        args.acknowledgment,
    )


if __name__ == "__main__":
    main()

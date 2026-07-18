#!/usr/bin/env python3
"""Build the immutable prospectively frozen signed-dose-scan plan."""

from __future__ import annotations

import argparse
import os
import re
import stat
import subprocess
from pathlib import Path
from typing import Any, Iterable, Mapping

from . import protocol


REPO_ROOT = Path(__file__).resolve().parents[2]
SOURCE_PATHS = (
    ".gitignore",
    "data/consciousness_sae_signed_dose_scan/README.md",
    "docs/consciousness_sae_signed_dose_scan/PRIOR_REVIEW_CONTEXT.md",
    "docs/consciousness_sae_signed_dose_scan/PRO_REVIEW_BRIEF.md",
    "docs/consciousness_sae_signed_dose_scan/PRO_REVIEW_REPAIR_CONTEXT.md",
    "docs/consciousness_sae_signed_dose_scan/PROTOCOL.md",
    "docs/consciousness_sae_target_blind_calibration/results/"
    "calv2-r3-audit-recovery-3a9a54d-20260716T202903Z/RESULT_SUMMARY.json",
    "experiments/__init__.py",
    "experiments/consciousness_sae_realization_validation/__init__.py",
    "experiments/consciousness_sae_realization_validation/legacy_public_artifact_manifest.json",
    "experiments/consciousness_sae_realization_validation/protocol.py",
    "experiments/consciousness_sae_realization_validation/runpod_preflight.py",
    "experiments/consciousness_sae_realization_validation/runtime.py",
    "experiments/consciousness_sae_target_blind_calibration/__init__.py",
    "experiments/consciousness_sae_target_blind_calibration/orientation.py",
    "experiments/consciousness_sae_target_blind_calibration/protocol.py",
    "experiments/consciousness_sae_target_blind_calibration/runner.py",
    "experiments/exp2_sae/__init__.py",
    "experiments/exp2_sae/gemma_scope_9b_protocol.py",
    "experiments/exp2_sae/gemma_scope_9b_runtime.py",
    "experiments/consciousness_sae_signed_dose_scan/__init__.py",
    "experiments/consciousness_sae_signed_dose_scan/README.md",
    "experiments/consciousness_sae_signed_dose_scan/audit.py",
    "experiments/consciousness_sae_signed_dose_scan/authorize.py",
    "experiments/consciousness_sae_signed_dose_scan/build_plan.py",
    "experiments/consciousness_sae_signed_dose_scan/gemma9b_validation.py",
    "experiments/consciousness_sae_signed_dose_scan/gemma9b_validation_audit.py",
    "experiments/consciousness_sae_signed_dose_scan/guest_launcher.py",
    "experiments/consciousness_sae_signed_dose_scan/orientation.py",
    "experiments/consciousness_sae_signed_dose_scan/protocol.py",
    "experiments/consciousness_sae_signed_dose_scan/requirements-runpod-b200.txt",
    "experiments/consciousness_sae_signed_dose_scan/review_adjudication.py",
    "experiments/consciousness_sae_signed_dose_scan/runner.py",
    "experiments/consciousness_sae_signed_dose_scan/setup_runpod_guest.sh",
    "experiments/consciousness_sae_signed_dose_scan/validate_plan.py",
    "src/prompts.py",
    "tests/consciousness_sae_signed_dose_scan/__init__.py",
    "tests/consciousness_sae_signed_dose_scan/test_gemma9b_validation.py",
    "tests/consciousness_sae_signed_dose_scan/test_execution_chain.py",
    "tests/consciousness_sae_signed_dose_scan/test_protocol.py",
    "tests/consciousness_sae_signed_dose_scan/test_plan.py",
)
PLAN_FILE_NAMES = (
    "protocol_snapshot.json",
    "dose_scan_plan.jsonl",
    "design_provenance.json",
    "source_files.json",
)
COMMIT_RE = re.compile(r"[0-9a-f]{40}")


def _absolute(path: Path) -> Path:
    return Path(os.path.abspath(path.expanduser()))


def _require_no_symlink_components(path: Path, label: str) -> None:
    candidate = _absolute(path)
    current = Path(candidate.anchor)
    for part in candidate.parts[1:]:
        current = current / part
        if current.is_symlink():
            raise ValueError(f"{label} contains a symlink component: {current}")


def _bound_source(relative: str) -> Path:
    path = REPO_ROOT / relative
    _require_no_symlink_components(path, "bound source")
    try:
        details = path.lstat()
    except OSError as exc:
        raise FileNotFoundError(path) from exc
    if not stat.S_ISREG(details.st_mode) or details.st_nlink != 1:
        raise ValueError(f"bound source is not a single-link regular file: {relative}")
    return path


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    with path.open("xb") as handle:
        handle.write(protocol.canonical_json_bytes(dict(value)) + b"\n")
        handle.flush()
        os.fsync(handle.fileno())


def _write_jsonl(path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
    with path.open("xb") as handle:
        for row in rows:
            handle.write(protocol.canonical_json_bytes(dict(row)) + b"\n")
        handle.flush()
        os.fsync(handle.fileno())


def _git_head() -> str:
    value = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    if COMMIT_RE.fullmatch(value) is None:
        raise ValueError("plan-build Git commit is malformed")
    return value


def build(output_dir: Path, *, enforce_canonical_path: bool = False) -> Path:
    protocol.validate_protocol()
    if len(SOURCE_PATHS) != len(set(SOURCE_PATHS)):
        raise ValueError("bound source closure contains duplicate paths")
    output = _absolute(output_dir)
    canonical = _absolute(REPO_ROOT / protocol.CANONICAL_PLAN_RELATIVE_PATH)
    if enforce_canonical_path and output != canonical:
        raise ValueError("production plan output differs from canonical relative path")
    partial = output.with_name(f".{output.name}.partial")
    if (
        os.path.lexists(output)
        or output.is_symlink()
        or os.path.lexists(partial)
        or partial.is_symlink()
    ):
        raise FileExistsError(f"refusing to overwrite plan directory: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    _require_no_symlink_components(output.parent, "plan parent")
    partial.mkdir(mode=0o755)
    try:
        _write_json(partial / "protocol_snapshot.json", protocol.protocol_snapshot())
        _write_jsonl(partial / "dose_scan_plan.jsonl", protocol.rows())
        _write_json(partial / "design_provenance.json", protocol.DESIGN_PROVENANCE)

        source_files = []
        for relative in SOURCE_PATHS:
            path = _bound_source(relative)
            source_files.append(
                {
                    "path": relative,
                    "bytes": path.stat().st_size,
                    "sha256": protocol.sha256_file(path),
                }
            )
        _write_json(partial / "source_files.json", {"files": source_files})

        records = []
        for name in PLAN_FILE_NAMES:
            path = partial / name
            records.append(
                {
                    "path": name,
                    "bytes": path.stat().st_size,
                    "sha256": protocol.sha256_file(path),
                }
            )
        core = {
            "schema_version": 1,
            "status": "prospectively_frozen_exploratory_plan",
            "execution_authorized": False,
            "runner_implemented_in_frozen_closure": True,
            "audit_implemented_in_frozen_closure": True,
            "study_id": protocol.STUDY_ID,
            "protocol_version": protocol.PROTOCOL_VERSION,
            "scope": "exploratory_target_blind_generic_vector_signed_dose_curve",
            "canonical_plan_relative_path": protocol.CANONICAL_PLAN_RELATIVE_PATH,
            "git_head_commit": _git_head(),
            "paper_prompt_render_count": 0,
            "target_prompt_render_count": 0,
            "target_feature_vector_count": 0,
            "analysis_data_inputs": [],
            "zero_baseline_continuation_count": len(protocol.PROMPT_IDS),
            "nonzero_dose_magnitude_count": len(protocol.DOSE_BASIS_POINTS),
            "signed_pair_count": protocol.PAIR_COUNT,
            "signed_edited_forward_count": protocol.EDITED_FORWARD_COUNT,
            "exact_model_forward_count": protocol.FORWARD_INVENTORY[
                "exact_total_model_forwards"
            ],
            "reference_online_j_dose_basis_points": (
                protocol.REFERENCE_ONLINE_J_DOSE_BASIS_POINTS
            ),
            "raw_namespace": protocol.STORAGE_POLICY["raw_namespace"],
            "files": records,
        }
        manifest = {**core, "plan_manifest_sha256": protocol.canonical_sha256(core)}
        _write_json(partial / "plan_manifest.json", manifest)
        directory_fd = os.open(partial, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
        os.replace(partial, output)
        parent_fd = os.open(output.parent, os.O_RDONLY)
        try:
            os.fsync(parent_fd)
        finally:
            os.close(parent_fd)
        return output / "plan_manifest.json"
    except BaseException:
        # Preserve a partial directory for diagnosis; it can never validate as
        # a complete plan and is never overwritten automatically.
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    print(build(args.output_dir, enforce_canonical_path=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Verify sealed pilot inputs and atomically write the authorized analysis result."""

from __future__ import annotations

import argparse
import json
import os
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from . import analysis, paths, protocol, runtime
from .validate_plan import validate_plan


RESULT_FILENAME = "ANALYSIS_RESULT.json"
PHASES = ("G1", "G2", "G3", "G3P", "G4")


class AnalyzePilotError(RuntimeError):
    """An analysis input or output path differs from the sealed contract."""


def _require_study_path(
    path: Path,
    *,
    study_root: Path,
    label: str,
    kind: str,
) -> Path:
    """Resolve one non-symlink file/directory beneath the external study root."""

    if kind not in {"file", "directory"}:  # pragma: no cover - internal invariant
        raise AssertionError("unsupported study-path kind")
    study_root = study_root.resolve(strict=True)
    lexical = Path(os.path.abspath(path.expanduser()))
    try:
        resolved = lexical.resolve(strict=True)
        resolved.relative_to(study_root)
    except (OSError, ValueError) as exc:
        raise AnalyzePilotError(f"{label} escapes the external study namespace") from exc
    current = lexical
    while True:
        if current.is_symlink():
            raise AnalyzePilotError(f"{label} contains a symlink")
        try:
            if current.resolve(strict=True) == study_root:
                break
        except OSError as exc:  # pragma: no cover - raced filesystem mutation
            raise AnalyzePilotError(f"{label} does not exist") from exc
        if current.parent == current:  # pragma: no cover - membership proved above
            raise AnalyzePilotError(f"{label} has no external-study ancestor")
        current = current.parent
    if (kind == "file" and not resolved.is_file()) or (
        kind == "directory" and not resolved.is_dir()
    ):
        raise AnalyzePilotError(f"{label} has the wrong filesystem type")
    return resolved


def _prepare_analysis_output(output_dir: Path, *, study_root: Path) -> Path:
    """Require ``analysis/<fresh-run-id>`` below the external study namespace."""

    study_root = study_root.resolve(strict=True)
    analysis_root = study_root / "analysis"
    if analysis_root.is_symlink():
        raise AnalyzePilotError("analysis output root is a symlink")
    if analysis_root.exists() and not analysis_root.is_dir():
        raise AnalyzePilotError("analysis output root is not a directory")
    lexical = Path(os.path.abspath(output_dir.expanduser()))
    raw_analysis_root = lexical.parent
    try:
        output_parent_is_exact = (
            raw_analysis_root.name == "analysis"
            and raw_analysis_root.parent.resolve(strict=True) == study_root
        )
    except OSError:
        output_parent_is_exact = False
    if (
        not output_parent_is_exact
        or raw_analysis_root.is_symlink()
        or not runtime.SAFE_RUN_ID.fullmatch(lexical.name)
    ):
        raise AnalyzePilotError(
            "analysis output must be a fresh direct child of the external analysis root"
        )
    if lexical.exists() or lexical.is_symlink():
        raise AnalyzePilotError("analysis output must be fresh")
    analysis_root.mkdir(mode=0o750, parents=True, exist_ok=True)
    return analysis_root / lexical.name


def _load_json_object(path: Path, label: str) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise AnalyzePilotError(f"{label} is missing, symlinked, or not a file")
    try:
        raw = path.read_bytes()
        value = json.loads(raw)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AnalyzePilotError(f"{label} is not readable canonical JSON") from exc
    if not isinstance(value, dict):
        raise AnalyzePilotError(f"{label} is not a JSON object")
    try:
        canonical = protocol.canonical_json_bytes(value) + b"\n"
    except (TypeError, ValueError) as exc:
        raise AnalyzePilotError(f"{label} is not finite canonical JSON") from exc
    if raw != canonical:
        raise AnalyzePilotError(f"{label} bytes are not the canonical encoding")
    return value


def _load_verified_phase_rows(
    directory: Path,
    *,
    phase: str,
    authorization: Mapping[str, Any],
) -> tuple[dict[str, list[dict[str, Any]]], str]:
    if phase not in PHASES:
        raise AnalyzePilotError("analysis phase is outside the exact phase set")
    root = directory.resolve(strict=True)
    if directory.is_symlink() or not root.is_dir():
        raise AnalyzePilotError(f"{phase} directory is unsafe")
    manifest = _load_json_object(root / "FILE_MANIFEST.json", f"{phase} manifest")
    run_id = manifest.get("run_id")
    plan_hash = authorization.get("plan_manifest_sha256")
    execution_hash = authorization.get("execution_binding_canonical_sha256")
    if (
        manifest.get("phase") != phase
        or not isinstance(run_id, str)
        or not run_id
        or manifest.get("plan_manifest_sha256") != plan_hash
        or manifest.get("execution_binding_canonical_sha256") != execution_hash
    ):
        raise AnalyzePilotError(f"{phase} manifest identity differs from authorization")
    try:
        verified = runtime.verify_completed_transaction(
            root,
            phase=phase,
            run_id=run_id,
            plan_manifest_sha256=str(plan_hash),
            execution_binding_canonical_sha256=str(execution_hash),
        )
    except runtime.PilotRuntimeError as exc:
        raise AnalyzePilotError(f"{phase} transaction verification failed: {exc}") from exc
    receipt = verified["receipt"]
    expected_manifest = authorization.get("phase_file_manifests", {}).get(phase)
    observed_manifest = {
        "file_manifest_content_sha256": receipt.get(
            "file_manifest_content_sha256"
        ),
        "file_manifest_embedded_sha256": receipt.get(
            "file_manifest_embedded_sha256"
        ),
    }
    if expected_manifest != observed_manifest:
        raise AnalyzePilotError(f"{phase} FILE_MANIFEST hashes differ from authorization")
    expected_measurements = authorization.get("phase_measurement_files", {}).get(
        phase
    )
    if receipt.get("measurement_files") != expected_measurements:
        raise AnalyzePilotError(f"{phase} measurement-file receipt differs")
    return verified["rows"], str(receipt["receipt_sha256"])


def _write_result_atomically(output_dir: Path, result: Mapping[str, Any]) -> Path:
    payload = dict(result)
    observed_hash = payload.pop("result_sha256", None)
    if observed_hash != protocol.canonical_sha256(payload):
        raise AnalyzePilotError("analysis result self-hash does not reconstruct")
    if not runtime.SAFE_RUN_ID.fullmatch(output_dir.name):
        raise AnalyzePilotError("analysis output directory name is unsafe")
    parent = output_dir.parent
    if parent.is_symlink() or not parent.is_dir():
        raise AnalyzePilotError("analysis output parent is missing or symlinked")
    final = parent.resolve(strict=True) / output_dir.name
    partial = final.with_name(f"{final.name}.partial")
    if final.exists() or final.is_symlink() or partial.exists() or partial.is_symlink():
        raise AnalyzePilotError("analysis output must be fresh")
    partial.mkdir(mode=0o750)
    try:
        result_path = partial / RESULT_FILENAME
        with result_path.open("xb") as handle:
            handle.write(protocol.canonical_json_bytes(dict(result)) + b"\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(partial, final)
    except BaseException:
        # Preserve a failed partial directory for forensic inspection; never reuse it.
        raise
    return final


def analyze_pilot(
    *,
    artifact_root: Path,
    volume_id: str,
    plan_dir: Path,
    phase_directories: Mapping[str, Path],
    analysis_authorization_path: Path,
    structural_audit_receipt_path: Path,
    tokenizer_audit_receipt_path: Path,
    vector_inventory_receipt_path: Path,
    output_dir: Path,
) -> Path:
    """Verify all authorized inputs, run the pure gates, and publish one result."""

    if set(phase_directories) != set(PHASES):
        raise AnalyzePilotError("phase-directory inventory differs")
    try:
        external_root = paths.require_external_artifact_root(
            artifact_root, expected_volume_id=volume_id
        )
    except paths.UnsafePilotPath as exc:
        raise AnalyzePilotError(f"external artifact root is unsafe: {exc}") from exc
    study_root = external_root / protocol.STUDY_SLUG / protocol.STUDY_ID
    if study_root.is_symlink() or not study_root.is_dir():
        raise AnalyzePilotError("external study namespace is missing or symlinked")
    resolved_phases = {
        phase: _require_study_path(
            directory,
            study_root=study_root,
            label=f"{phase} directory",
            kind="directory",
        )
        for phase, directory in phase_directories.items()
    }
    analysis_authorization_path = _require_study_path(
        analysis_authorization_path,
        study_root=study_root,
        label="analysis authorization",
        kind="file",
    )
    structural_audit_receipt_path = _require_study_path(
        structural_audit_receipt_path,
        study_root=study_root,
        label="structural audit receipt",
        kind="file",
    )
    tokenizer_audit_receipt_path = _require_study_path(
        tokenizer_audit_receipt_path,
        study_root=study_root,
        label="tokenizer audit receipt",
        kind="file",
    )
    vector_inventory_receipt_path = _require_study_path(
        vector_inventory_receipt_path,
        study_root=study_root,
        label="G4 vector inventory receipt",
        kind="file",
    )
    output_dir = _prepare_analysis_output(output_dir, study_root=study_root)
    authorization = _load_json_object(
        analysis_authorization_path, "analysis authorization"
    )
    structural = _load_json_object(
        structural_audit_receipt_path, "structural audit receipt"
    )
    tokenizer = _load_json_object(tokenizer_audit_receipt_path, "tokenizer audit")
    vectors = _load_json_object(vector_inventory_receipt_path, "G4 vector inventory")
    try:
        plan_validation = validate_plan(plan_dir.resolve(strict=True))
    except Exception as exc:
        raise AnalyzePilotError(f"frozen plan validation failed: {exc}") from exc
    if plan_validation.get("plan_manifest_sha256") != authorization.get(
        "plan_manifest_sha256"
    ):
        raise AnalyzePilotError("validated plan differs from analysis authorization")

    datasets: dict[str, list[dict[str, Any]]] = {}
    phase_verifier_receipts: dict[str, str] = {}
    for phase in PHASES:
        rows, verifier_hash = _load_verified_phase_rows(
            resolved_phases[phase], phase=phase, authorization=authorization
        )
        if set(rows) != set(analysis.PHASE_MEASUREMENT_FILENAMES[phase]):
            raise AnalyzePilotError(f"{phase} verified row-file inventory differs")
        datasets.update(rows)
        phase_verifier_receipts[phase] = verifier_hash
    if set(datasets) != set(analysis.MEASUREMENT_FILENAMES):
        raise AnalyzePilotError("combined analysis dataset inventory differs")

    result = analysis.analyze_all(
        analysis_authorization=authorization,
        structural_audit_receipt=structural,
        tokenizer_audit_receipt=tokenizer,
        vector_inventory_receipt=vectors,
        g1_rows=datasets["g1_rows.jsonl"],
        g2_transport_rows=datasets["g2_transport_rows.jsonl"],
        g2_linearity_rows=datasets["g2_linearity_rows.jsonl"],
        g3_rows=datasets["g3_rows.jsonl"],
        g3p_rows=datasets["g3p_rows.jsonl"],
        g4_clean_rows=datasets["g4_clean_rows.jsonl"],
        g4_vector_rows=datasets["g4_vector_rows.jsonl"],
        g4_telemetry_rows=datasets["g4_telemetry_rows.jsonl"],
    )
    if set(phase_verifier_receipts) != set(PHASES):  # pragma: no cover
        raise AssertionError("phase verifier receipt inventory changed")
    return _write_result_atomically(output_dir, result)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--volume-id", required=True)
    parser.add_argument("--plan-dir", type=Path, required=True)
    for phase in PHASES:
        parser.add_argument(f"--{phase.lower()}-directory", type=Path, required=True)
    parser.add_argument("--analysis-authorization", type=Path, required=True)
    parser.add_argument("--structural-audit-receipt", type=Path, required=True)
    parser.add_argument("--tokenizer-audit-receipt", type=Path, required=True)
    parser.add_argument("--vector-inventory-receipt", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    output = analyze_pilot(
        artifact_root=args.artifact_root,
        volume_id=args.volume_id,
        plan_dir=args.plan_dir,
        phase_directories={
            phase: getattr(args, f"{phase.lower()}_directory") for phase in PHASES
        },
        analysis_authorization_path=args.analysis_authorization,
        structural_audit_receipt_path=args.structural_audit_receipt,
        tokenizer_audit_receipt_path=args.tokenizer_audit_receipt,
        vector_inventory_receipt_path=args.vector_inventory_receipt,
        output_dir=args.output_dir,
    )
    result = _load_json_object(output / RESULT_FILENAME, "written analysis result")
    print(result["result_sha256"])
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

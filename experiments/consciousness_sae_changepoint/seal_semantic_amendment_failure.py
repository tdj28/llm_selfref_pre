#!/usr/bin/env python3
"""Seal the terminal vector-RMS safety-gate failure without a model forward."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import sys
from pathlib import Path, PurePosixPath
from typing import Any, Mapping, Sequence


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from experiments.consciousness_sae_changepoint import paths  # noqa: E402
from experiments.consciousness_sae_changepoint.protocol import canonical_json_bytes, sha256_file  # noqa: E402
from experiments.consciousness_sae_changepoint.semantic_control_amendment import (  # noqa: E402
    FAILED_CONTROL_BINDINGS,
    _load_freeze,
)
from experiments.consciousness_sae_changepoint.storage import RunTransaction, verify_completed_run  # noqa: E402


FAILURE_SCHEMA_VERSION = "consciousness_sae_control_amendment_terminal_failure_v1"
FAILURE_FILENAME = "semantic_control_amendment_terminal_failure_receipt.json"
REASON_CODE = "vector_rms_safety_gate"
EXACT_EXCEPTION = "vector exceeds 10% of a clean injection-state RMS"


class AmendmentFailureSealError(RuntimeError):
    """The terminal-failure evidence did not match the frozen execution."""


def sha256_json(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _without_hash(value: Mapping[str, Any]) -> dict[str, Any]:
    result = dict(value)
    result.pop("receipt_sha256", None)
    return result


def snapshot_partial(partial: Path, *, root: Path) -> dict[str, Any]:
    """Copy exact partial-run bytes and empty-directory names into JSON evidence."""

    resolved = partial.expanduser().resolve(strict=True)
    try:
        relative = resolved.relative_to(root).as_posix()
    except ValueError as exc:
        raise AmendmentFailureSealError("consumed partial is outside the external root") from exc
    if not resolved.name.endswith(".partial") or not resolved.is_dir() or resolved.is_symlink():
        raise AmendmentFailureSealError("consumed execution namespace is not a partial directory")
    directories: list[str] = []
    files: list[dict[str, Any]] = []
    for path in sorted(resolved.rglob("*")):
        if path.is_symlink():
            raise AmendmentFailureSealError("symlink found in consumed partial namespace")
        child = path.relative_to(resolved).as_posix()
        if path.is_dir():
            directories.append(child)
        elif path.is_file():
            raw = path.read_bytes()
            files.append(
                {
                    "relative_path": child,
                    "bytes": len(raw),
                    "sha256": hashlib.sha256(raw).hexdigest(),
                    "payload_base64": base64.b64encode(raw).decode("ascii"),
                }
            )
        else:
            raise AmendmentFailureSealError("unsupported entry in consumed partial namespace")
    snapshot = {
        "schema_version": 1,
        "consumed_partial_relative_path": relative,
        "directories": directories,
        "files": files,
    }
    snapshot["snapshot_sha256"] = sha256_json(snapshot)
    return snapshot


def validate_partial_snapshot(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    embedded = snapshot.get("snapshot_sha256")
    if (
        snapshot.get("schema_version") != 1
        or not isinstance(embedded, str)
        or sha256_json({key: value for key, value in snapshot.items() if key != "snapshot_sha256"})
        != embedded
    ):
        raise AmendmentFailureSealError("partial snapshot hash differs")
    directories = snapshot.get("directories")
    files = snapshot.get("files")
    if (
        not isinstance(directories, list)
        or directories != sorted(set(directories))
        or not isinstance(files, list)
    ):
        raise AmendmentFailureSealError("partial snapshot inventory differs")
    reconstructed: list[dict[str, Any]] = []
    paths_seen: set[str] = set()
    for row in files:
        if not isinstance(row, Mapping) or set(row) != {
            "relative_path", "bytes", "sha256", "payload_base64"
        }:
            raise AmendmentFailureSealError("partial snapshot file row differs")
        relative = str(row["relative_path"])
        if relative in paths_seen or PurePosixPath(relative).is_absolute() or ".." in PurePosixPath(relative).parts:
            raise AmendmentFailureSealError("partial snapshot file path differs")
        paths_seen.add(relative)
        try:
            raw = base64.b64decode(str(row["payload_base64"]), validate=True)
        except Exception as exc:
            raise AmendmentFailureSealError("partial snapshot file payload is invalid") from exc
        if len(raw) != int(row["bytes"]) or hashlib.sha256(raw).hexdigest() != row["sha256"]:
            raise AmendmentFailureSealError("partial snapshot file bytes differ")
        reconstructed.append(dict(row))
    if not any(row["relative_path"] == "RUN_STARTED.json" for row in reconstructed):
        raise AmendmentFailureSealError("partial snapshot lacks RUN_STARTED.json")
    if any(row["relative_path"].endswith("COMPLETE.json") for row in reconstructed):
        raise AmendmentFailureSealError("consumed namespace contains a completion marker")
    return {
        "snapshot_sha256": embedded,
        "directory_count": len(directories),
        "file_count": len(reconstructed),
    }


def traceback_evidence(path: Path) -> dict[str, Any]:
    raw = path.expanduser().resolve(strict=True).read_bytes()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise AmendmentFailureSealError("traceback evidence is not UTF-8") from exc
    if "SemanticControlAmendmentError" not in text or EXACT_EXCEPTION not in text:
        raise AmendmentFailureSealError("traceback does not contain the exact frozen gate exception")
    result = {
        "bytes": len(raw),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "encoding": "utf-8/base64",
        "payload_base64": base64.b64encode(raw).decode("ascii"),
        "reason_code": REASON_CODE,
        "exact_exception": EXACT_EXCEPTION,
    }
    result["evidence_sha256"] = sha256_json(result)
    return result


def validate_traceback_evidence(value: Mapping[str, Any]) -> dict[str, Any]:
    embedded = value.get("evidence_sha256")
    if (
        value.get("reason_code") != REASON_CODE
        or value.get("exact_exception") != EXACT_EXCEPTION
        or value.get("encoding") != "utf-8/base64"
        or not isinstance(embedded, str)
        or sha256_json({key: child for key, child in value.items() if key != "evidence_sha256"})
        != embedded
    ):
        raise AmendmentFailureSealError("traceback evidence identity differs")
    try:
        raw = base64.b64decode(str(value["payload_base64"]), validate=True)
        text = raw.decode("utf-8")
    except Exception as exc:
        raise AmendmentFailureSealError("traceback evidence payload is invalid") from exc
    if (
        len(raw) != int(value["bytes"])
        or hashlib.sha256(raw).hexdigest() != value["sha256"]
        or "SemanticControlAmendmentError" not in text
        or EXACT_EXCEPTION not in text
    ):
        raise AmendmentFailureSealError("traceback evidence bytes differ")
    return {"evidence_sha256": embedded, "traceback_sha256": value["sha256"]}


def seal_failure(
    *,
    amendment_freeze_receipt_path: Path,
    traceback_path: Path,
    artifact_root: Path | None,
    volume_id: str,
    failure_run_id: str,
) -> dict[str, Any]:
    root = paths.require_external_artifact_root(
        artifact_root, expected_volume_id=volume_id, write_read_probe=True
    )
    freeze, freeze_seal = _load_freeze(
        amendment_freeze_receipt_path, root=root, require_live_sources=False
    )
    if freeze.get("expected_volume_id") != volume_id:
        raise AmendmentFailureSealError("freeze volume differs")
    execution_run_id = str(freeze["execution_run_id"])
    partial = root / "calibration" / f"{execution_run_id}.partial"
    completed = root / "calibration" / execution_run_id
    if completed.exists() or completed.is_symlink():
        raise AmendmentFailureSealError("a completed amendment result exists; failure seal refused")
    partial_snapshot = snapshot_partial(partial, root=root)
    partial_validation = validate_partial_snapshot(partial_snapshot)
    started_row = next(
        row for row in partial_snapshot["files"] if row["relative_path"] == "RUN_STARTED.json"
    )
    started = json.loads(base64.b64decode(started_row["payload_base64"]).decode("utf-8"))
    metadata = started.get("metadata", {})
    if (
        started.get("run_id") != execution_run_id
        or metadata.get("plan_hash") != freeze.get("plan_hash")
        or metadata.get("freeze_receipt_sha256") != freeze.get("receipt_sha256")
        or metadata.get("freeze_manifest_sha256") != freeze_seal.get("manifest_sha256")
        or metadata.get("outcome_blind") is not True
        or metadata.get("target_outcomes_opened") is not False
    ):
        raise AmendmentFailureSealError("consumed partial RUN_STARTED binding differs")
    traceback = traceback_evidence(traceback_path)
    source_raw = Path(__file__).read_bytes()
    source_snapshot = {
        "bytes": len(source_raw),
        "sha256": hashlib.sha256(source_raw).hexdigest(),
        "payload_base64": base64.b64encode(source_raw).decode("ascii"),
    }
    source_snapshot["snapshot_sha256"] = sha256_json(source_snapshot)
    transaction = RunTransaction.start(
        phase="calibration",
        run_id=failure_run_id,
        artifact_root=root,
        expected_volume_id=volume_id,
        metadata={
            "role": "terminal_semantic_amendment_failure_seal",
            "status": "fail",
            "reason_code": REASON_CODE,
            "terminal": True,
            "third_retry_permitted": False,
        },
    )
    receipt: dict[str, Any] = {
        "schema_version": FAILURE_SCHEMA_VERSION,
        "status": "fail",
        "passed": False,
        "reason_code": REASON_CODE,
        "exact_exception": EXACT_EXCEPTION,
        "study_id": freeze["study_id"],
        "protocol_version": freeze["protocol_version"],
        "outcome_blind": True,
        "target_outcomes_opened": False,
        "prior_outcome_inputs": [row["receipt_sha256"] for row in FAILED_CONTROL_BINDINGS],
        "historical_failed_controls": freeze["failed_controls"],
        "expected_volume_id": volume_id,
        "freeze_receipt_sha256": freeze["receipt_sha256"],
        "freeze_manifest_sha256": freeze_seal["manifest_sha256"],
        "plan_hash": freeze["plan_hash"],
        "consumed_execution_run_id": execution_run_id,
        "consumed_partial_snapshot": partial_snapshot,
        "consumed_partial_validation": partial_validation,
        "traceback_evidence": traceback,
        "source_file_sha256": source_snapshot["sha256"],
        "source_snapshot_sha256": source_snapshot["snapshot_sha256"],
        "terminal": True,
        "third_retry_permitted": False,
        "target_execution_blocked": True,
        "specificity_claim_permitted": False,
        "decision": "semantic positive-control gate remains FAIL; no rerun or passing composite is permitted",
    }
    receipt["receipt_sha256"] = sha256_json(receipt)
    transaction.write_json("failure_sealer_source_snapshot.json", source_snapshot)
    transaction.write_json(FAILURE_FILENAME, receipt)
    sealed_directory = transaction.complete(
        metadata={
            "status": "fail",
            "reason_code": REASON_CODE,
            "receipt_sha256": receipt["receipt_sha256"],
            "terminal": True,
            "third_retry_permitted": False,
        }
    )
    seal = verify_completed_run(sealed_directory)
    validated = validate_failure_receipt(
        sealed_directory / FAILURE_FILENAME,
        amendment_freeze_receipt_path=amendment_freeze_receipt_path,
        artifact_root=root,
        volume_id=volume_id,
    )
    return {
        **validated,
        "completed_directory": sealed_directory.relative_to(root).as_posix(),
        "remote_manifest_sha256": seal["manifest_sha256"],
    }


def validate_failure_receipt(
    failure_receipt_path: Path,
    *,
    amendment_freeze_receipt_path: Path,
    artifact_root: Path,
    volume_id: str,
) -> dict[str, Any]:
    root = paths.require_external_artifact_root(
        artifact_root, expected_volume_id=volume_id, write_read_probe=False
    )
    directory = failure_receipt_path.expanduser().resolve(strict=True).parent
    seal = verify_completed_run(directory)
    receipt = json.loads(failure_receipt_path.read_text(encoding="utf-8"))
    freeze, freeze_seal = _load_freeze(
        amendment_freeze_receipt_path, root=root, require_live_sources=False
    )
    embedded = receipt.get("receipt_sha256")
    if (
        receipt.get("schema_version") != FAILURE_SCHEMA_VERSION
        or receipt.get("status") != "fail"
        or receipt.get("passed") is not False
        or receipt.get("reason_code") != REASON_CODE
        or receipt.get("exact_exception") != EXACT_EXCEPTION
        or receipt.get("outcome_blind") is not True
        or receipt.get("target_outcomes_opened") is not False
        or receipt.get("prior_outcome_inputs")
        != [row["receipt_sha256"] for row in FAILED_CONTROL_BINDINGS]
        or receipt.get("historical_failed_controls") != freeze.get("failed_controls")
        or receipt.get("freeze_receipt_sha256") != freeze.get("receipt_sha256")
        or receipt.get("freeze_manifest_sha256") != freeze_seal.get("manifest_sha256")
        or receipt.get("plan_hash") != freeze.get("plan_hash")
        or receipt.get("consumed_execution_run_id") != freeze.get("execution_run_id")
        or receipt.get("terminal") is not True
        or receipt.get("third_retry_permitted") is not False
        or receipt.get("target_execution_blocked") is not True
        or receipt.get("specificity_claim_permitted") is not False
        or not isinstance(embedded, str)
        or sha256_json(_without_hash(receipt)) != embedded
    ):
        raise AmendmentFailureSealError("terminal failure receipt identity differs")
    partial_validation = validate_partial_snapshot(receipt["consumed_partial_snapshot"])
    if partial_validation != receipt.get("consumed_partial_validation"):
        raise AmendmentFailureSealError("terminal partial snapshot does not reconstruct")
    validate_traceback_evidence(receipt["traceback_evidence"])
    source_snapshot = json.loads(
        (directory / "failure_sealer_source_snapshot.json").read_text(encoding="utf-8")
    )
    if (
        source_snapshot.get("snapshot_sha256") != receipt.get("source_snapshot_sha256")
        or sha256_json({key: value for key, value in source_snapshot.items() if key != "snapshot_sha256"})
        != source_snapshot.get("snapshot_sha256")
        or source_snapshot.get("sha256") != receipt.get("source_file_sha256")
    ):
        raise AmendmentFailureSealError("failure-sealer source snapshot differs")
    return {
        "status": "fail",
        "passed": False,
        "reason_code": REASON_CODE,
        "receipt_sha256": embedded,
        "manifest_sha256": seal["manifest_sha256"],
        "terminal": True,
        "third_retry_permitted": False,
        "passing_composite_permitted": False,
    }


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--amendment-freeze-receipt", type=Path, required=True)
    parser.add_argument("--traceback-file", type=Path, required=True)
    parser.add_argument("--artifact-root", type=Path)
    parser.add_argument("--volume-id", required=True)
    parser.add_argument("--failure-run-id", required=True)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    result = seal_failure(
        amendment_freeze_receipt_path=args.amendment_freeze_receipt,
        traceback_path=args.traceback_file,
        artifact_root=args.artifact_root,
        volume_id=args.volume_id,
        failure_run_id=args.failure_run_id,
    )
    print(json.dumps(result, sort_keys=True))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

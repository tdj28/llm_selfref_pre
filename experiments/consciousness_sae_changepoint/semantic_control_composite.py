#!/usr/bin/env python3
"""Seal and validate the complete adaptive semantic-control provenance chain.

The composite never converts the two historical ``+0.5`` failures into passes.
It can pass only when the single prospectively frozen adaptive amendment passes
and independently reconstructs from all 64 completed blocks.  Its conclusion
is intentionally bounded to endpoint sensitivity; feature-label specificity,
consciousness specificity, and target-prompt validity remain unsupported.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import re
import sys
from pathlib import Path, PurePosixPath
from typing import Any, Mapping, Sequence


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from experiments.consciousness_sae_changepoint import paths  # noqa: E402
from experiments.consciousness_sae_changepoint.protocol import (  # noqa: E402
    PROTOCOL_VERSION,
    STUDY_ID,
    canonical_json_bytes,
    sha256_file,
)
from experiments.consciousness_sae_changepoint.semantic_control_amendment import (  # noqa: E402
    AMENDMENT_FREEZE_FILENAME,
    AMENDMENT_RESULT_FILENAME,
    FAILED_CONTROL_BINDINGS,
    MANDATORY_CAVEATS,
    SELECTED_FEATURE_IDS,
    _validate_failed_control,
    _load_completed_receipt,
    _load_freeze,
    validate_execution_receipt,
)
from experiments.consciousness_sae_changepoint.storage import (  # noqa: E402
    RunTransaction,
    verify_completed_run,
)


COMPOSITE_SCHEMA_VERSION = "consciousness_sae_control_composite_v1"
COMPOSITE_FILENAME = "semantic_control_composite_receipt.json"
COMPOSITE_SOURCE_SNAPSHOT = "semantic_control_composite_source_snapshot.json"
HEX64 = re.compile(r"^[0-9a-f]{64}$")
PERMITTED_WORDING = (
    "The one-shot adaptive aggregate endpoint-sensitivity control passed its "
    "frozen J-trajectory and actual-final-logit thresholds on the disjoint "
    "neutral validation packet."
)
PROHIBITED_CLAIMS = (
    "feature-label specificity",
    "consciousness specificity",
    "validated consciousness feature",
    "validated self-awareness feature",
    "target-prompt effect",
)


class SemanticControlCompositeError(RuntimeError):
    """The composite provenance or bounded interpretation failed."""


def sha256_json(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _without_hash(value: Mapping[str, Any]) -> dict[str, Any]:
    result = dict(value)
    result.pop("receipt_sha256", None)
    return result


def _relative(path: Path, root: Path) -> str:
    try:
        return path.expanduser().resolve(strict=True).relative_to(root).as_posix()
    except ValueError as exc:
        raise SemanticControlCompositeError("component is outside the external root") from exc


def _source_snapshot() -> dict[str, Any]:
    path = Path(__file__).resolve(strict=True)
    raw = path.read_bytes()
    result = {
        "schema_version": 1,
        "relative_path": path.relative_to(REPO_ROOT).as_posix(),
        "bytes": len(raw),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "encoding": "base64",
        "payload_base64": base64.b64encode(raw).decode("ascii"),
    }
    result["snapshot_sha256"] = sha256_json(result)
    return result


def _validate_source_snapshot(snapshot: Mapping[str, Any], *, expected_hash: str) -> None:
    embedded = snapshot.get("snapshot_sha256")
    if (
        snapshot.get("schema_version") != 1
        or snapshot.get("relative_path")
        != "experiments/consciousness_sae_changepoint/semantic_control_composite.py"
        or not isinstance(embedded, str)
        or not HEX64.fullmatch(embedded)
        or sha256_json({key: value for key, value in snapshot.items() if key != "snapshot_sha256"})
        != embedded
    ):
        raise SemanticControlCompositeError("composite source snapshot identity differs")
    try:
        raw = base64.b64decode(str(snapshot["payload_base64"]), validate=True)
    except Exception as exc:
        raise SemanticControlCompositeError("composite source snapshot is invalid") from exc
    if (
        len(raw) != int(snapshot.get("bytes", -1))
        or hashlib.sha256(raw).hexdigest() != snapshot.get("sha256")
        or snapshot.get("sha256") != expected_hash
    ):
        raise SemanticControlCompositeError("composite source bytes do not reconstruct")


def bounded_analysis() -> dict[str, Any]:
    """Return the only interpretation a passing composite is allowed to expose."""

    return {
        "status": "pass",
        "passed": True,
        "endpoint_sensitivity_control_passed": True,
        "historical_plus_0p5_failures_remain_failures": True,
        "feature_label_specificity_supported": False,
        "consciousness_specificity_supported": False,
        "target_prompt_effect_validated": False,
        "mechanically_selected_candidate_ids": list(SELECTED_FEATURE_IDS),
        "candidate_role": "endpoint-sensitivity vectors only",
        "permitted_wording": PERMITTED_WORDING,
        "mandatory_caveats": list(MANDATORY_CAVEATS),
    }


def _validate_bounded_analysis(value: Any) -> dict[str, Any]:
    expected = bounded_analysis()
    if value != expected:
        raise SemanticControlCompositeError("composite interpretation exceeds its bounds")
    normalized = json.dumps(value, ensure_ascii=False, sort_keys=True).lower()
    # The exact negated field names above are allowed; affirmative prose is not.
    if "supports feature-label specificity" in normalized or "supports consciousness specificity" in normalized:
        raise SemanticControlCompositeError("composite contains a prohibited specificity claim")
    return expected


def create(
    *,
    amendment_freeze_receipt_path: Path,
    amendment_result_receipt_path: Path,
    artifact_root: Path | None,
    volume_id: str,
    run_id: str,
) -> dict[str, Any]:
    root = paths.require_external_artifact_root(
        artifact_root, expected_volume_id=volume_id, write_read_probe=True
    )
    freeze, freeze_seal = _load_freeze(
        amendment_freeze_receipt_path, root=root, require_live_sources=False
    )
    validated_result = validate_execution_receipt(
        amendment_result_receipt_path,
        amendment_freeze_receipt_path=amendment_freeze_receipt_path,
        artifact_root=root,
        volume_id=volume_id,
    )
    if (
        validated_result.get("status") != "pass"
        or validated_result.get("passed") is not True
        or validated_result.get("terminal") is not True
    ):
        raise SemanticControlCompositeError("terminal adaptive amendment did not PASS")
    result, result_seal = _load_completed_receipt(
        amendment_result_receipt_path,
        root=root,
        expected_filename=AMENDMENT_RESULT_FILENAME,
    )
    if (
        result.get("receipt_sha256") != validated_result.get("receipt_sha256")
        or result.get("analysis", {}).get("report_wording")
        != freeze["spec"]["pass_wording"]
        or result.get("analysis", {}).get("mandatory_caveats")
        != freeze["spec"]["mandatory_caveats"]
    ):
        raise SemanticControlCompositeError("amendment result wording/caveats differ")
    public = freeze["public_bindings"]
    source_snapshot = _source_snapshot()
    transaction = RunTransaction.start(
        phase="calibration",
        run_id=run_id,
        artifact_root=root,
        expected_volume_id=volume_id,
        metadata={
            "role": "semantic_positive_control_composite",
            "amendment_result_receipt_sha256": result["receipt_sha256"],
            "outcome_blind": True,
            "target_outcomes_opened": False,
        },
    )
    component_bindings = {
        "failed_controls": freeze["failed_controls"],
        "amendment_freeze": {
            "relative_path": _relative(amendment_freeze_receipt_path, root),
            "receipt_sha256": freeze["receipt_sha256"],
            "file_sha256": sha256_file(amendment_freeze_receipt_path),
            "manifest_sha256": freeze_seal["manifest_sha256"],
        },
        "amendment_result": {
            "relative_path": _relative(amendment_result_receipt_path, root),
            "receipt_sha256": result["receipt_sha256"],
            "file_sha256": sha256_file(amendment_result_receipt_path),
            "manifest_sha256": result_seal["manifest_sha256"],
        },
    }
    analysis = bounded_analysis()
    receipt: dict[str, Any] = {
        "schema_version": COMPOSITE_SCHEMA_VERSION,
        "status": "pass",
        "passed": True,
        "study_id": freeze["study_id"],
        "protocol_version": freeze["protocol_version"],
        "outcome_blind": True,
        "target_outcomes_opened": False,
        "prior_outcome_inputs": [row["receipt_sha256"] for row in FAILED_CONTROL_BINDINGS],
        "expected_volume_id": volume_id,
        "composite_relative_directory": f"calibration/{run_id}",
        "artifact_receipt_sha256": public["artifact"]["file_sha256"],
        "calibration_receipt_sha256": public["calibration"]["file_sha256"],
        "artifact_receipt_embedded_sha256": public["artifact"]["receipt_sha256"],
        "calibration_receipt_embedded_sha256": public["calibration"]["receipt_sha256"],
        "selected_feature_ids": list(SELECTED_FEATURE_IDS),
        "component_bindings": component_bindings,
        "analysis": analysis,
        "source_file_sha256": source_snapshot["sha256"],
        "source_snapshot_sha256": source_snapshot["snapshot_sha256"],
        "terminal_amendment_pass": True,
        "historical_failures_preserved": True,
        "specificity_claim_permitted": False,
    }
    receipt["receipt_sha256"] = sha256_json(receipt)
    transaction.write_json(COMPOSITE_SOURCE_SNAPSHOT, source_snapshot)
    transaction.write_json(COMPOSITE_FILENAME, receipt)
    completed = transaction.complete(
        metadata={
            "status": "pass",
            "receipt_sha256": receipt["receipt_sha256"],
            "terminal_amendment_pass": True,
            "specificity_claim_permitted": False,
        }
    )
    seal = verify_completed_run(completed)
    reconstructed = validate_control_receipt(receipt, artifact_root=root)
    return {
        **reconstructed,
        "completed_directory": completed.relative_to(root).as_posix(),
        "remote_manifest_sha256": seal["manifest_sha256"],
    }


def validate_control_receipt(
    receipt: Mapping[str, Any],
    *,
    artifact_root: Path | None = None,
) -> dict[str, Any]:
    """Independently reconstruct both failures, freeze, result, and bounds."""

    embedded = receipt.get("receipt_sha256")
    if (
        receipt.get("schema_version") != COMPOSITE_SCHEMA_VERSION
        or receipt.get("status") != "pass"
        or receipt.get("passed") is not True
        or receipt.get("outcome_blind") is not True
        or receipt.get("target_outcomes_opened") is not False
        or receipt.get("prior_outcome_inputs")
        != [row["receipt_sha256"] for row in FAILED_CONTROL_BINDINGS]
        or receipt.get("selected_feature_ids") != list(SELECTED_FEATURE_IDS)
        or receipt.get("terminal_amendment_pass") is not True
        or receipt.get("historical_failures_preserved") is not True
        or receipt.get("specificity_claim_permitted") is not False
        or not isinstance(embedded, str)
        or not HEX64.fullmatch(embedded)
        or sha256_json(_without_hash(receipt)) != embedded
    ):
        raise SemanticControlCompositeError("composite identity/hash differs")
    _validate_bounded_analysis(receipt.get("analysis"))
    root = paths.require_external_artifact_root(
        artifact_root,
        expected_volume_id=str(receipt.get("expected_volume_id")),
        write_read_probe=False,
    )
    directory = root / PurePosixPath(str(receipt.get("composite_relative_directory", "")))
    seal = verify_completed_run(directory)
    snapshot = json.loads((directory / COMPOSITE_SOURCE_SNAPSHOT).read_text(encoding="utf-8"))
    _validate_source_snapshot(snapshot, expected_hash=str(receipt["source_file_sha256"]))
    components = receipt.get("component_bindings")
    if not isinstance(components, Mapping):
        raise SemanticControlCompositeError("composite component bindings are missing")
    freeze_binding = components.get("amendment_freeze")
    result_binding = components.get("amendment_result")
    if not isinstance(freeze_binding, Mapping) or not isinstance(result_binding, Mapping):
        raise SemanticControlCompositeError("amendment component bindings are missing")
    freeze_path = root / PurePosixPath(str(freeze_binding["relative_path"]))
    result_path = root / PurePosixPath(str(result_binding["relative_path"]))
    freeze, freeze_seal = _load_freeze(freeze_path, root=root, require_live_sources=False)
    if (
        freeze_binding.get("receipt_sha256") != freeze.get("receipt_sha256")
        or freeze_binding.get("file_sha256") != sha256_file(freeze_path)
        or freeze_binding.get("manifest_sha256") != freeze_seal.get("manifest_sha256")
        or components.get("failed_controls") != freeze.get("failed_controls")
    ):
        raise SemanticControlCompositeError("freeze/failure component binding differs")
    for frozen, expected in zip(freeze["failed_controls"], FAILED_CONTROL_BINDINGS):
        reconstructed_failure = _validate_failed_control(
            root / PurePosixPath(str(frozen["relative_path"])),
            root=root,
            expected=expected,
        )
        if reconstructed_failure != frozen:
            raise SemanticControlCompositeError(
                "historical failed control does not reconstruct"
            )
    validated = validate_execution_receipt(
        result_path,
        amendment_freeze_receipt_path=freeze_path,
        artifact_root=root,
        volume_id=str(receipt["expected_volume_id"]),
    )
    result, result_seal = _load_completed_receipt(
        result_path, root=root, expected_filename=AMENDMENT_RESULT_FILENAME
    )
    if (
        validated.get("status") != "pass"
        or validated.get("passed") is not True
        or validated.get("terminal") is not True
        or result_binding.get("receipt_sha256") != result.get("receipt_sha256")
        or result_binding.get("file_sha256") != sha256_file(result_path)
        or result_binding.get("manifest_sha256") != result_seal.get("manifest_sha256")
        or result.get("analysis", {}).get("report_wording")
        != freeze["spec"]["pass_wording"]
        or result.get("analysis", {}).get("mandatory_caveats")
        != freeze["spec"]["mandatory_caveats"]
    ):
        raise SemanticControlCompositeError("terminal PASS result does not reconstruct")
    public = freeze["public_bindings"]
    if (
        receipt.get("artifact_receipt_sha256") != public["artifact"]["file_sha256"]
        or receipt.get("calibration_receipt_sha256")
        != public["calibration"]["file_sha256"]
        or receipt.get("artifact_receipt_embedded_sha256")
        != public["artifact"]["receipt_sha256"]
        or receipt.get("calibration_receipt_embedded_sha256")
        != public["calibration"]["receipt_sha256"]
    ):
        raise SemanticControlCompositeError("shared artifact/calibration binding differs")
    return {
        "status": "pass",
        "passed": True,
        "receipt_sha256": embedded,
        "analysis": receipt["analysis"],
        "selected_feature_ids": list(SELECTED_FEATURE_IDS),
        "historical_failures_preserved": True,
        "specificity_claim_permitted": False,
        "manifest_sha256": seal["manifest_sha256"],
    }


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--amendment-freeze-receipt", type=Path, required=True)
    parser.add_argument("--amendment-result-receipt", type=Path, required=True)
    parser.add_argument("--artifact-root", type=Path)
    parser.add_argument("--volume-id", required=True)
    parser.add_argument("--run-id", required=True)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    result = create(
        amendment_freeze_receipt_path=args.amendment_freeze_receipt,
        amendment_result_receipt_path=args.amendment_result_receipt,
        artifact_root=args.artifact_root,
        volume_id=args.volume_id,
        run_id=args.run_id,
    )
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

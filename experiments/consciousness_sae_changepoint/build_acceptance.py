#!/usr/bin/env python3
"""Build a sealed target-blind acceptance manifest from validated children.

This assembler is intentionally strict: it will not write an acceptance
manifest unless all fourteen executor-required gates independently validate.
The thirteen validators outside ``run.py`` live in :mod:`gate_validators`; the
intervention-vector inventory continues to use the executor's tensor-inventory
validator.  Existing generic benchmark pass flags are never upgraded into
gate receipts.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Mapping, Sequence

from experiments.consciousness_sae_changepoint.calibrate import (
    validate_artifact_receipt,
    validate_calibration_receipt,
)
from experiments.consciousness_sae_changepoint.gate_validators import (
    BENCHMARK_EVIDENCE_GATES,
    GATE_VALIDATOR_SOURCE,
    VALIDATOR_IDS,
    gate_validator_registry,
    judge_definition_evidence,
    measured_benchmark_evidence,
    neutral_panel_evidence,
)
from experiments.consciousness_sae_changepoint.protocol import (
    PROTOCOL_VERSION,
    STUDY_ID,
    canonical_json_bytes,
    sha256_file,
)
from experiments.consciousness_sae_changepoint.run import (
    ACCEPTANCE_SCHEMA_VERSION,
    REQUIRED_TARGET_BLIND_GATES,
    GateValidationContext,
    GateValidationError,
    REPO_ROOT,
    default_gate_validator_registry,
    embedded_receipt_sha256,
    validate_intervention_vector_inventory_gate,
    validate_target_blind_acceptance_receipt,
)
from experiments.consciousness_sae_changepoint.storage import (
    RunTransaction,
    validate_relative_path,
    verify_completed_run,
)


ACCEPTANCE_PHASE = "acceptance"
ACCEPTANCE_FILENAME = "target_blind_acceptance_receipt.json"
VECTOR_GATE_ID = "intervention_vector_inventory"
VECTOR_VALIDATOR_ID = "intervention_vector_inventory_v1"
VECTOR_VALIDATOR_SOURCE = "experiments/consciousness_sae_changepoint/run.py"


class AcceptanceBuildError(RuntimeError):
    """A required child is absent, unsealed, or does not reconstruct."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_json(path: Path, *, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise AcceptanceBuildError(f"{label} is not valid JSON: {path}") from exc
    if not isinstance(value, dict):
        raise AcceptanceBuildError(f"{label} must be a JSON object: {path}")
    return value


def _canonical_signed(payload: Mapping[str, Any]) -> dict[str, Any]:
    result = dict(payload)
    result.pop("receipt_sha256", None)
    result["receipt_sha256"] = embedded_receipt_sha256(result)
    return result


def source_binding(receipt_path: Path, *, artifact_root: Path) -> dict[str, Any]:
    """Bind a source file to its independently verified completed run."""

    root = artifact_root.expanduser().resolve(strict=True)
    path = receipt_path.expanduser().resolve(strict=True)
    if path.is_symlink() or not path.is_file():
        raise AcceptanceBuildError(f"source receipt is not a regular file: {path}")
    try:
        receipt_relative = validate_relative_path(
            PurePosixPath(*path.relative_to(root).parts)
        )
    except ValueError as exc:
        raise AcceptanceBuildError("source receipt is outside the external artifact root") from exc
    container = path.parent
    try:
        sealed = verify_completed_run(container)
    except Exception as exc:
        raise AcceptanceBuildError(
            f"source receipt is not inside a completed run: {path}"
        ) from exc
    payload = _read_json(path, label="source receipt")
    embedded = payload.get("receipt_sha256")
    if not isinstance(embedded, str) or embedded_receipt_sha256(payload) != embedded:
        raise AcceptanceBuildError(f"source receipt embedded hash differs: {path}")
    container_relative = validate_relative_path(
        PurePosixPath(*container.relative_to(root).parts)
    )
    return {
        "schema_version": 1,
        "receipt_relative_path": receipt_relative,
        "container_relative_path": container_relative,
        "container_kind": "completed_run",
        "bytes": path.stat().st_size,
        "file_sha256": sha256_file(path),
        "embedded_sha256": embedded,
        "manifest_sha256": sealed["manifest_sha256"],
    }


def _common_child(
    *,
    gate_id: str,
    validator_id: str,
    plan_hash: str,
    artifact_receipt_sha256: str,
    calibration_receipt_sha256: str,
    evidence: Mapping[str, Any],
    source: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "gate_schema_version": 1,
        "gate_id": gate_id,
        "validator_id": validator_id,
        "status": "pass",
        "study_id": STUDY_ID,
        "protocol_version": PROTOCOL_VERSION,
        "outcome_blind": True,
        "target_outcomes_opened": False,
        "prior_outcome_inputs": [],
        "plan_hash": plan_hash,
        "artifact_receipt_sha256": artifact_receipt_sha256,
        "calibration_receipt_sha256": calibration_receipt_sha256,
        "created_at_utc": _utc_now(),
        "evidence": dict(evidence),
    }
    if source is not None:
        payload["source"] = dict(source)
    return _canonical_signed(payload)


def _semantic_evidence(source: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "validated_receipt_sha256": source.get("receipt_sha256"),
        "analysis_sha256": _sha256_json(source.get("analysis")),
        "selected_feature_ids": source.get("selected_feature_ids"),
        "executor_source_sha256": source.get("source_file_sha256"),
    }


def _power_evidence(source: Mapping[str, Any]) -> dict[str, Any]:
    base = source.get("base_config")
    return {
        "validated_receipt_sha256": source.get("receipt_sha256"),
        "base_config_sha256": source.get("base_config_sha256"),
        "assessment_sha256": _sha256_json(source.get("assessment")),
        "prefix_count": base.get("n_blocks") if isinstance(base, Mapping) else None,
    }


def _sha256_json(value: Any) -> str:
    import hashlib

    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def prepare_gate_children(
    *,
    artifact_root: Path,
    plan_hash: str,
    artifact_receipt_path: Path,
    calibration_receipt_path: Path,
    benchmark_receipt_path: Path,
    semantic_control_receipt_path: Path,
    power_receipt_path: Path,
    vector_gate_receipt_path: Path,
    review_evidence_path: Path,
) -> tuple[dict[str, dict[str, Any]], GateValidationContext]:
    """Construct and validate every child in memory before any transaction."""

    root = artifact_root.expanduser().resolve(strict=True)
    artifact = _read_json(artifact_receipt_path, label="artifact receipt")
    calibration = _read_json(calibration_receipt_path, label="calibration receipt")
    artifact_hash = validate_artifact_receipt(
        artifact, expected_volume_id=str(artifact.get("expected_volume_id"))
    )
    calibration_valid = validate_calibration_receipt(calibration)
    calibration_hash = str(calibration_valid["receipt_sha256"])
    if artifact_hash != artifact.get("receipt_sha256"):
        raise AcceptanceBuildError("artifact embedded hash differs after validation")
    public = calibration.get("public_sources")
    if not isinstance(public, Mapping) or public.get(
        "artifact_receipt_embedded_sha256"
    ) != artifact_hash:
        raise AcceptanceBuildError("calibration is not bound to the exact artifact receipt")

    context = GateValidationContext(
        plan_hash=plan_hash,
        artifact_receipt_sha256=artifact_hash,
        calibration_receipt_sha256=calibration_hash,
        artifact_root=root,
    )

    artifact_binding = source_binding(artifact_receipt_path, artifact_root=root)
    # Calibration is a shared parent even though no gate uses it as its sole
    # evidence source.  Verify its completed transaction before accepting its
    # embedded hash, and bind the artifact receipt's physical file hash too.
    source_binding(calibration_receipt_path, artifact_root=root)
    if public.get("artifact_receipt_file_sha256") != artifact_binding["file_sha256"]:
        raise AcceptanceBuildError(
            "calibration artifact-receipt file binding differs"
        )
    benchmark_binding = source_binding(benchmark_receipt_path, artifact_root=root)
    semantic_binding = source_binding(semantic_control_receipt_path, artifact_root=root)
    power_binding = source_binding(power_receipt_path, artifact_root=root)
    benchmark_receipt = _read_json(benchmark_receipt_path, label="benchmark receipt")
    semantic_receipt = _read_json(
        semantic_control_receipt_path, label="semantic-control receipt"
    )
    power_receipt = _read_json(power_receipt_path, label="power receipt")

    acceptance_evidence = benchmark_receipt.get("acceptance_evidence")
    if not isinstance(acceptance_evidence, Mapping):
        raise AcceptanceBuildError(
            "measured benchmark has no acceptance_evidence; its generic technical "
            "pass flags cannot fill the seven runtime gates"
        )
    if set(acceptance_evidence) != set(BENCHMARK_EVIDENCE_GATES):
        raise AcceptanceBuildError(
            "benchmark acceptance_evidence does not contain exactly the seven low-level gates"
        )

    children: dict[str, dict[str, Any]] = {}
    for gate_id in BENCHMARK_EVIDENCE_GATES:
        evidence = acceptance_evidence.get(gate_id)
        if not isinstance(evidence, Mapping):
            raise AcceptanceBuildError(f"benchmark gate evidence is not an object: {gate_id}")
        children[gate_id] = _common_child(
            gate_id=gate_id,
            validator_id=VALIDATOR_IDS[gate_id],
            plan_hash=plan_hash,
            artifact_receipt_sha256=artifact_hash,
            calibration_receipt_sha256=calibration_hash,
            evidence=evidence,
            source=benchmark_binding,
        )

    children["neutral_panel"] = _common_child(
        gate_id="neutral_panel",
        validator_id=VALIDATOR_IDS["neutral_panel"],
        plan_hash=plan_hash,
        artifact_receipt_sha256=artifact_hash,
        calibration_receipt_sha256=calibration_hash,
        evidence=neutral_panel_evidence(artifact),
        source=artifact_binding,
    )
    children["semantic_positive_control"] = _common_child(
        gate_id="semantic_positive_control",
        validator_id=VALIDATOR_IDS["semantic_positive_control"],
        plan_hash=plan_hash,
        artifact_receipt_sha256=artifact_hash,
        calibration_receipt_sha256=calibration_hash,
        evidence=_semantic_evidence(semantic_receipt),
        source=semantic_binding,
    )
    children["power_operating_characteristics"] = _common_child(
        gate_id="power_operating_characteristics",
        validator_id=VALIDATOR_IDS["power_operating_characteristics"],
        plan_hash=plan_hash,
        artifact_receipt_sha256=artifact_hash,
        calibration_receipt_sha256=calibration_hash,
        evidence=_power_evidence(power_receipt),
        source=power_binding,
    )
    children["measured_benchmark"] = _common_child(
        gate_id="measured_benchmark",
        validator_id=VALIDATOR_IDS["measured_benchmark"],
        plan_hash=plan_hash,
        artifact_receipt_sha256=artifact_hash,
        calibration_receipt_sha256=calibration_hash,
        evidence=measured_benchmark_evidence(benchmark_receipt),
        source=benchmark_binding,
    )
    review_evidence = _read_json(review_evidence_path, label="review gate evidence")
    children["independent_plan_review"] = _common_child(
        gate_id="independent_plan_review",
        validator_id=VALIDATOR_IDS["independent_plan_review"],
        plan_hash=plan_hash,
        artifact_receipt_sha256=artifact_hash,
        calibration_receipt_sha256=calibration_hash,
        evidence=review_evidence,
    )
    children["judge_definition_frozen"] = _common_child(
        gate_id="judge_definition_frozen",
        validator_id=VALIDATOR_IDS["judge_definition_frozen"],
        plan_hash=plan_hash,
        artifact_receipt_sha256=artifact_hash,
        calibration_receipt_sha256=calibration_hash,
        evidence=judge_definition_evidence(),
    )

    vector = _read_json(vector_gate_receipt_path, label="vector inventory gate")
    if (
        vector.get("gate_id") != VECTOR_GATE_ID
        or vector.get("validator_id") != VECTOR_VALIDATOR_ID
        or vector.get("status") != "pass"
        or vector.get("study_id") != STUDY_ID
        or vector.get("outcome_blind") is not True
        or vector.get("target_outcomes_opened") is not False
        or vector.get("prior_outcome_inputs") != []
        or vector.get("plan_hash") != plan_hash
        or vector.get("artifact_receipt_sha256") != artifact_hash
        or vector.get("calibration_receipt_sha256") != calibration_hash
        or vector.get("receipt_sha256") != embedded_receipt_sha256(vector)
    ):
        raise AcceptanceBuildError("vector-inventory child shared binding/hash differs")
    validate_intervention_vector_inventory_gate(vector, context)
    children[VECTOR_GATE_ID] = vector

    if set(children) != set(REQUIRED_TARGET_BLIND_GATES):
        raise AcceptanceBuildError(
            "child gate set differs; missing="
            f"{sorted(set(REQUIRED_TARGET_BLIND_GATES) - set(children))}"
        )
    registry = gate_validator_registry()
    for gate_id in REQUIRED_TARGET_BLIND_GATES:
        if gate_id == VECTOR_GATE_ID:
            continue
        spec = registry[(gate_id, VALIDATOR_IDS[gate_id])]
        try:
            spec.validate(children[gate_id], context)
        except GateValidationError as exc:
            raise AcceptanceBuildError(
                f"gate {gate_id} does not independently validate: {exc}"
            ) from exc
    return children, context


def _entry_for_child(
    *,
    gate_id: str,
    child_path: Path,
    container_relative_path: str,
) -> dict[str, Any]:
    if gate_id == VECTOR_GATE_ID:
        validator_id = VECTOR_VALIDATOR_ID
        validator_source = VECTOR_VALIDATOR_SOURCE
    else:
        validator_id = VALIDATOR_IDS[gate_id]
        validator_source = GATE_VALIDATOR_SOURCE
    source_path = (REPO_ROOT / validator_source).resolve(strict=True)
    child = _read_json(child_path, label=f"{gate_id} child")
    return {
        "gate_id": gate_id,
        "validator_id": validator_id,
        "validator_source_path": validator_source,
        "validator_source_bytes": source_path.stat().st_size,
        "validator_source_sha256": sha256_file(source_path),
        "receipt_relative_path": validate_relative_path(
            PurePosixPath(container_relative_path)
            / "gates"
            / f"{gate_id}.receipt.json"
        ),
        "container_kind": "completed_run",
        "container_relative_path": container_relative_path,
        "bytes": child_path.stat().st_size,
        "sha256": sha256_file(child_path),
        "embedded_sha256": child["receipt_sha256"],
    }


def build_acceptance(
    *,
    artifact_root: Path,
    expected_volume_id: str,
    run_id: str,
    plan_hash: str,
    artifact_receipt_path: Path,
    calibration_receipt_path: Path,
    benchmark_receipt_path: Path,
    semantic_control_receipt_path: Path,
    power_receipt_path: Path,
    vector_gate_receipt_path: Path,
    review_evidence_path: Path,
) -> Path:
    """Seal and re-open a complete acceptance transaction."""

    children, context = prepare_gate_children(
        artifact_root=artifact_root,
        plan_hash=plan_hash,
        artifact_receipt_path=artifact_receipt_path,
        calibration_receipt_path=calibration_receipt_path,
        benchmark_receipt_path=benchmark_receipt_path,
        semantic_control_receipt_path=semantic_control_receipt_path,
        power_receipt_path=power_receipt_path,
        vector_gate_receipt_path=vector_gate_receipt_path,
        review_evidence_path=review_evidence_path,
    )
    transaction = RunTransaction.start(
        phase=ACCEPTANCE_PHASE,
        run_id=run_id,
        artifact_root=artifact_root,
        expected_volume_id=expected_volume_id,
        metadata={
            "study_id": STUDY_ID,
            "role": "target_blind_acceptance",
            "outcome_blind": True,
            "target_outcomes_opened": False,
            "prior_outcome_inputs": [],
            "plan_hash": plan_hash,
        },
    )
    child_paths: dict[str, Path] = {}
    for gate_id in REQUIRED_TARGET_BLIND_GATES:
        child_paths[gate_id] = transaction.write_json(
            f"gates/{gate_id}.receipt.json", children[gate_id]
        )
    container_relative = validate_relative_path(
        PurePosixPath(ACCEPTANCE_PHASE) / run_id
    )
    entries = [
        _entry_for_child(
            gate_id=gate_id,
            child_path=child_paths[gate_id],
            container_relative_path=container_relative,
        )
        for gate_id in REQUIRED_TARGET_BLIND_GATES
    ]
    manifest = _canonical_signed(
        {
            "schema_version": ACCEPTANCE_SCHEMA_VERSION,
            "status": "pass",
            "study_id": STUDY_ID,
            "outcome_blind": True,
            "target_outcomes_opened": False,
            "prior_outcome_inputs": [],
            "plan_hash": plan_hash,
            "artifact_receipt_sha256": context.artifact_receipt_sha256,
            "calibration_receipt_sha256": context.calibration_receipt_sha256,
            "created_at_utc": _utc_now(),
            "gates": entries,
        }
    )
    transaction.write_json(ACCEPTANCE_FILENAME, manifest)
    completed = transaction.complete(
        metadata={
            "study_id": STUDY_ID,
            "outcome_blind": True,
            "target_outcomes_opened": False,
            "acceptance_receipt_sha256": manifest["receipt_sha256"],
            "gate_receipt_sha256": {
                gate_id: children[gate_id]["receipt_sha256"]
                for gate_id in REQUIRED_TARGET_BLIND_GATES
            },
        }
    )
    verify_completed_run(completed)
    registry = default_gate_validator_registry()
    registry.update(gate_validator_registry())
    final_manifest = _read_json(
        completed / ACCEPTANCE_FILENAME, label="completed acceptance manifest"
    )
    validate_target_blind_acceptance_receipt(
        final_manifest,
        plan_hash=plan_hash,
        artifact_receipt_sha256=context.artifact_receipt_sha256,
        calibration_receipt_sha256=context.calibration_receipt_sha256,
        artifact_root=artifact_root.expanduser().resolve(strict=True),
        validator_registry=registry,
    )
    return completed


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--volume-id", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--plan-hash", required=True)
    parser.add_argument("--artifact-receipt", type=Path, required=True)
    parser.add_argument("--calibration-receipt", type=Path, required=True)
    parser.add_argument("--benchmark-receipt", type=Path, required=True)
    parser.add_argument("--semantic-control-receipt", type=Path, required=True)
    parser.add_argument("--power-receipt", type=Path, required=True)
    parser.add_argument("--vector-gate-receipt", type=Path, required=True)
    parser.add_argument("--review-evidence", type=Path, required=True)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> None:
    args = parse_args(argv)
    try:
        completed = build_acceptance(
            artifact_root=args.artifact_root,
            expected_volume_id=args.volume_id,
            run_id=args.run_id,
            plan_hash=args.plan_hash,
            artifact_receipt_path=args.artifact_receipt,
            calibration_receipt_path=args.calibration_receipt,
            benchmark_receipt_path=args.benchmark_receipt,
            semantic_control_receipt_path=args.semantic_control_receipt,
            power_receipt_path=args.power_receipt,
            vector_gate_receipt_path=args.vector_gate_receipt,
            review_evidence_path=args.review_evidence,
        )
    except (AcceptanceBuildError, GateValidationError) as exc:
        raise SystemExit(f"acceptance build blocked: {exc}") from exc
    print(
        json.dumps(
            {
                "status": "pass",
                "completed_directory": completed.relative_to(
                    args.artifact_root.expanduser().resolve(strict=True)
                ).as_posix(),
                "acceptance_receipt": (
                    completed / ACCEPTANCE_FILENAME
                ).relative_to(args.artifact_root.expanduser().resolve(strict=True)).as_posix(),
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()

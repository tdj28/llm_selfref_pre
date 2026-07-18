from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from experiments.consciousness_readout_validation import analysis, paths, protocol, runtime
from experiments.consciousness_readout_validation.analyze_pilot import (
    PHASES,
    AnalyzePilotError,
    _load_json_object,
    _load_verified_phase_rows,
    _prepare_analysis_output,
    _require_study_path,
    _write_result_atomically,
    analyze_pilot,
)


class AnalyzePilotCommandTests(unittest.TestCase):
    def test_external_path_gate_rejects_escapes_symlinks_and_nested_output(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            study_root = root / "study"
            study_root.mkdir()
            inside = study_root / "inside.json"
            inside.write_text("{}", encoding="utf-8")
            outside = root / "outside.json"
            outside.write_text("{}", encoding="utf-8")
            self.assertEqual(
                _require_study_path(
                    inside, study_root=study_root, label="inside", kind="file"
                ),
                inside.resolve(),
            )
            with self.assertRaisesRegex(AnalyzePilotError, "escapes"):
                _require_study_path(
                    outside, study_root=study_root, label="outside", kind="file"
                )
            link = study_root / "link.json"
            link.symlink_to(inside)
            with self.assertRaisesRegex(AnalyzePilotError, "symlink"):
                _require_study_path(
                    link, study_root=study_root, label="link", kind="file"
                )
            with self.assertRaisesRegex(AnalyzePilotError, "direct child"):
                _prepare_analysis_output(
                    study_root / "analysis" / "nested" / "run",
                    study_root=study_root,
                )

    def test_receipt_loader_requires_exact_canonical_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "receipt.json"
            path.write_text('{"b": 2, "a": 1}\n', encoding="utf-8")
            with self.assertRaisesRegex(AnalyzePilotError, "canonical encoding"):
                _load_json_object(path, "receipt")
            path.write_bytes(protocol.canonical_json_bytes({"b": 2, "a": 1}) + b"\n")
            self.assertEqual(_load_json_object(path, "receipt"), {"a": 1, "b": 2})

    def test_atomic_result_is_self_hash_checked_and_fresh(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            core = {"status": "pass", "study_id": protocol.STUDY_ID}
            result = {**core, "result_sha256": protocol.canonical_sha256(core)}
            output = _write_result_atomically(root / "analysis-001", result)
            self.assertEqual(
                json.loads((output / "ANALYSIS_RESULT.json").read_bytes()), result
            )
            with self.assertRaisesRegex(AnalyzePilotError, "fresh"):
                _write_result_atomically(root / "analysis-001", result)
            with self.assertRaisesRegex(AnalyzePilotError, "self-hash"):
                _write_result_atomically(
                    root / "analysis-002", {**result, "result_sha256": "0" * 64}
                )

    def test_phase_loader_reverifies_manifest_and_authorized_file_hashes(self) -> None:
        plan_hash = "a" * 64
        execution_hash = "b" * 64
        run_id = "g1-loader-roundtrip"
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / paths.VOLUME_SENTINEL).write_text(
                json.dumps(
                    {
                        "study_slug": protocol.STUDY_SLUG,
                        "study_id": protocol.STUDY_ID,
                        "volume_id": "test-volume",
                    }
                ),
                encoding="utf-8",
            )
            with runtime.PilotTransaction(
                artifact_root=root,
                volume_id="test-volume",
                phase="G1",
                run_id=run_id,
                plan_manifest_sha256=plan_hash,
                execution_binding_canonical_sha256=execution_hash,
            ) as transaction:
                transaction.append("g1_rows.jsonl", {"value": 1})
                final = transaction.complete()
            verified = runtime.verify_completed_transaction(
                final,
                phase="G1",
                run_id=run_id,
                plan_manifest_sha256=plan_hash,
                execution_binding_canonical_sha256=execution_hash,
            )
            verifier = verified["receipt"]
            authorization = {
                "plan_manifest_sha256": plan_hash,
                "execution_binding_canonical_sha256": execution_hash,
                "phase_file_manifests": {
                    "G1": {
                        "file_manifest_content_sha256": verifier[
                            "file_manifest_content_sha256"
                        ],
                        "file_manifest_embedded_sha256": verifier[
                            "file_manifest_embedded_sha256"
                        ],
                    }
                },
                "phase_measurement_files": {
                    "G1": verifier["measurement_files"]
                },
            }
            rows, receipt_hash = _load_verified_phase_rows(
                final, phase="G1", authorization=authorization
            )
            self.assertEqual(rows, verified["rows"])
            self.assertEqual(receipt_hash, verifier["receipt_sha256"])

            tampered = json.loads(json.dumps(authorization))
            tampered["phase_measurement_files"]["G1"]["g1_rows.jsonl"][
                "row_count"
            ] = 2
            with self.assertRaisesRegex(AnalyzePilotError, "measurement-file"):
                _load_verified_phase_rows(final, phase="G1", authorization=tampered)

    def test_orchestrator_loads_exact_five_phase_inventory(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            plan_dir = root / "plan"
            plan_dir.mkdir()
            artifact_root = root / "external"
            artifact_root.mkdir()
            volume_id = "test-volume"
            (artifact_root / paths.VOLUME_SENTINEL).write_text(
                json.dumps(
                    {
                        "study_slug": protocol.STUDY_SLUG,
                        "study_id": protocol.STUDY_ID,
                        "volume_id": volume_id,
                    }
                ),
                encoding="utf-8",
            )
            study_root = artifact_root / protocol.STUDY_SLUG / protocol.STUDY_ID
            phase_root = study_root / "phase_inputs"
            phase_root.mkdir(parents=True)
            phase_dirs = {phase: phase_root / phase.lower() for phase in PHASES}
            for directory in phase_dirs.values():
                directory.mkdir()
            receipt_root = study_root / "audit_inputs"
            receipt_root.mkdir()
            authorization_path = receipt_root / "authorization.json"
            structural_path = receipt_root / "structural.json"
            tokenizer_path = receipt_root / "tokenizer.json"
            vector_path = receipt_root / "vectors.json"
            plan_hash = "a" * 64
            inputs = {
                authorization_path: {"plan_manifest_sha256": plan_hash},
                structural_path: {"receipt": "structural"},
                tokenizer_path: {"receipt": "tokenizer"},
                vector_path: {"receipt": "vectors"},
            }
            for path, value in inputs.items():
                path.write_bytes(protocol.canonical_json_bytes(value) + b"\n")

            by_phase = {
                phase: {
                    filename: [{"phase": phase, "filename": filename}]
                    for filename in analysis.PHASE_MEASUREMENT_FILENAMES[phase]
                }
                for phase in PHASES
            }

            def load_phase(
                directory: Path, *, phase: str, authorization: object
            ) -> tuple[dict[str, list[dict[str, str]]], str]:
                self.assertEqual(directory, phase_dirs[phase].resolve())
                self.assertEqual(authorization, inputs[authorization_path])
                return by_phase[phase], phase.lower() * 32

            result_core = {"status": "pass", "study_id": protocol.STUDY_ID}
            result = {
                **result_core,
                "result_sha256": protocol.canonical_sha256(result_core),
            }
            with (
                patch(
                    "experiments.consciousness_readout_validation.analyze_pilot.validate_plan",
                    return_value={"plan_manifest_sha256": plan_hash},
                ),
                patch(
                    "experiments.consciousness_readout_validation.analyze_pilot._load_verified_phase_rows",
                    side_effect=load_phase,
                ),
                patch.object(analysis, "analyze_all", return_value=result) as analyze,
            ):
                output = analyze_pilot(
                    artifact_root=artifact_root,
                    volume_id=volume_id,
                    plan_dir=plan_dir,
                    phase_directories=phase_dirs,
                    analysis_authorization_path=authorization_path,
                    structural_audit_receipt_path=structural_path,
                    tokenizer_audit_receipt_path=tokenizer_path,
                    vector_inventory_receipt_path=vector_path,
                    output_dir=study_root / "analysis" / "analysis-001",
                )
            self.assertEqual(
                json.loads((output / "ANALYSIS_RESULT.json").read_bytes()), result
            )
            kwargs = analyze.call_args.kwargs
            self.assertEqual(kwargs["analysis_authorization"], inputs[authorization_path])
            self.assertEqual(kwargs["structural_audit_receipt"], inputs[structural_path])
            self.assertEqual(kwargs["tokenizer_audit_receipt"], inputs[tokenizer_path])
            self.assertEqual(kwargs["vector_inventory_receipt"], inputs[vector_path])
            for phase, filenames in analysis.PHASE_MEASUREMENT_FILENAMES.items():
                for filename in filenames:
                    self.assertEqual(
                        kwargs[filename.removesuffix(".jsonl")], by_phase[phase][filename]
                    )


if __name__ == "__main__":
    unittest.main()

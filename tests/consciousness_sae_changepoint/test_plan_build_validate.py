from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from experiments.consciousness_sae_changepoint import build_plan, paths, protocol, validate_plan


class PlanBuildAndValidationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        self.original_data_root = paths.DATA_ROOT
        paths.DATA_ROOT = self.root / "data" / paths.STUDY_SLUG
        paths.DATA_ROOT.mkdir(parents=True)

    def tearDown(self) -> None:
        paths.DATA_ROOT = self.original_data_root
        self.tempdir.cleanup()

    def build(self, name: str = "plan", receipt: Path | None = None) -> Path:
        destination = paths.DATA_ROOT / name
        result = build_plan.build(
            outdir=destination,
            volume_id="test-volume-001",
            calibration_receipt=receipt,
        )
        self.assertEqual(result["status"], "pass")
        self.assertEqual(len(result["plan_hash"]), 64)
        return destination

    def test_scaffold_builds_and_independent_validator_passes(self) -> None:
        plan_dir = self.build()
        result = validate_plan.validate(
            plan_dir, expected_volume_id="test-volume-001"
        )
        self.assertEqual(result["status"], "pass", result["errors"])
        self.assertEqual(result["plan_status"], "precalibration_machine_plan_scaffold")
        self.assertEqual(result["counts"]["main_branch_rows"], 1_280)
        self.assertEqual(result["counts"]["planned_probe_generations"], 6_560)
        self.assertEqual(result["counts"]["fixed_token_rows"], 2_080)

    def test_repeated_builds_have_identical_canonical_bytes_and_hash(self) -> None:
        left = self.build("left")
        right = self.build("right")
        for name in (*build_plan.PLAN_FILE_NAMES, "PLAN_MANIFEST.json"):
            self.assertEqual((left / name).read_bytes(), (right / name).read_bytes(), name)
        left_manifest = json.loads((left / "PLAN_MANIFEST.json").read_text())
        right_manifest = json.loads((right / "PLAN_MANIFEST.json").read_text())
        self.assertEqual(left_manifest["plan_hash"], right_manifest["plan_hash"])

    def test_tamper_fails_even_if_manifest_inventory_is_rehashed(self) -> None:
        plan_dir = self.build()
        rows = [
            json.loads(line)
            for line in (plan_dir / "main_branch_plan.jsonl").read_text().splitlines()
            if line
        ]
        rows[0]["branch"] = "never"
        (plan_dir / "main_branch_plan.jsonl").write_bytes(
            b"".join(protocol.canonical_json_bytes(row) + b"\n" for row in rows)
        )
        manifest = json.loads((plan_dir / "PLAN_MANIFEST.json").read_text())
        records = []
        for name in build_plan.PLAN_FILE_NAMES:
            path = plan_dir / name
            records.append(
                {"path": name, "bytes": path.stat().st_size, "sha256": protocol.sha256_file(path)}
            )
        manifest["files"] = sorted(records, key=lambda row: row["path"])
        manifest["plan_hash"] = protocol.plan_hash_from_file_records(records)
        (plan_dir / "PLAN_MANIFEST.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n"
        )
        result = validate_plan.validate(plan_dir)
        self.assertEqual(result["status"], "fail")
        self.assertTrue(
            any("deterministic reconstruction" in error for error in result["errors"]),
            result["errors"],
        )

    def test_fresh_calibration_receipt_resolves_matched_conditions(self) -> None:
        receipt = self.root / "calibration_receipt.json"
        mapping = dict(
            zip(protocol.TARGET_FEATURE_IDS, (101, 102, 103, 104, 105, 106))
        )
        receipt.write_text(
            json.dumps(
                {
                    "study_id": protocol.STUDY_ID,
                    "status": "pass",
                    "outcome_blind": True,
                    "prior_outcome_inputs": [],
                    "matched_feature_map": {
                        str(target): control for target, control in mapping.items()
                    },
                    "calibrated_multiplier": 3.25,
                },
                sort_keys=True,
            )
            + "\n"
        )
        with mock.patch.object(
            build_plan.calibrate,
            "validate_calibration_receipt",
            return_value={"status": "pass"},
        ), mock.patch.object(
            build_plan,
            "verify_completed_run",
            return_value={"status": "verified"},
        ):
            plan_dir = self.build(receipt=receipt)
        result = validate_plan.validate(plan_dir)
        self.assertEqual(result["status"], "pass", result["errors"])
        self.assertEqual(
            result["plan_status"], "freeze_candidate_result_free_machine_plan"
        )
        snapshot = json.loads((plan_dir / "protocol_snapshot.json").read_text())
        self.assertEqual(snapshot["controls"]["calibrated_multiplier_sensitivity"], 3.25)

    def test_shallow_fake_calibration_receipt_is_rejected(self) -> None:
        receipt = self.root / "shallow_fake_receipt.json"
        receipt.write_text(
            json.dumps(
                {
                    "study_id": protocol.STUDY_ID,
                    "status": "pass",
                    "outcome_blind": True,
                    "prior_outcome_inputs": [],
                    "matched_feature_map": {
                        str(target): control
                        for target, control in zip(
                            protocol.TARGET_FEATURE_IDS,
                            (101, 102, 103, 104, 105, 106),
                        )
                    },
                    "calibrated_multiplier": 3.25,
                }
            )
            + "\n"
        )
        with self.assertRaisesRegex(ValueError, "full reconstruction"):
            self.build(receipt=receipt)

    def test_calibration_receipt_rejects_prior_outcome_inputs(self) -> None:
        receipt = self.root / "bad_receipt.json"
        receipt.write_text(
            json.dumps(
                {
                    "study_id": protocol.STUDY_ID,
                    "status": "pass",
                    "outcome_blind": True,
                    "prior_outcome_inputs": ["old-results.jsonl"],
                    "matched_feature_map": {
                        str(target): control
                        for target, control in zip(
                            protocol.TARGET_FEATURE_IDS, (101, 102, 103, 104, 105, 106)
                        )
                    },
                    "calibrated_multiplier": 3.25,
                }
            )
        )
        with self.assertRaisesRegex(ValueError, "no prior outcome inputs"):
            self.build(receipt=receipt)

    def test_calibration_receipt_rejects_prior_experiment_path(self) -> None:
        prior_root = self.root / "prior-results"
        prior_root.mkdir()
        receipt = prior_root / "receipt.json"
        receipt.write_text("{}\n")
        with mock.patch.object(paths, "READ_ONLY_UPSTREAM_ROOTS", (prior_root,)):
            with self.assertRaisesRegex(ValueError, "prior experiment namespace"):
                build_plan.load_calibration_receipt(receipt)

    def test_existing_destination_is_rejected(self) -> None:
        destination = paths.DATA_ROOT / "existing"
        destination.mkdir()
        with self.assertRaisesRegex(paths.UnsafeOutputPath, "must not already exist"):
            build_plan.build(
                outdir=destination,
                volume_id="test-volume-001",
            )

    def test_validator_rejects_wrong_external_volume(self) -> None:
        plan_dir = self.build()
        result = validate_plan.validate(
            plan_dir, expected_volume_id="different-volume"
        )
        self.assertEqual(result["status"], "fail")
        self.assertIn("plan volume ID differs from expected_volume_id", result["errors"])

    def test_plan_contains_only_relative_external_namespaces(self) -> None:
        plan_dir = self.build()
        storage = json.loads((plan_dir / "storage_contract.json").read_text())
        self.assertEqual(storage["artifact_root_env"], paths.ARTIFACT_ROOT_ENV)
        self.assertFalse(storage["absolute_artifact_paths_in_plan"])
        self.assertFalse(storage["local_outcome_fallback"])
        for relative in storage["relative_namespaces"].values():
            self.assertFalse(Path(relative).is_absolute())
            self.assertNotIn("..", Path(relative).parts)


if __name__ == "__main__":
    unittest.main()

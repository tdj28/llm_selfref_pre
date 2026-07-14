import unittest
from unittest import mock

from experiments.consciousness_sae_changepoint import semantic_control_composite as composite


class SemanticControlCompositeTests(unittest.TestCase):
    def test_bounded_analysis_preserves_failures_and_denies_specificity(self):
        analysis = composite.bounded_analysis()
        self.assertTrue(analysis["passed"])
        self.assertTrue(analysis["historical_plus_0p5_failures_remain_failures"])
        self.assertFalse(analysis["feature_label_specificity_supported"])
        self.assertFalse(analysis["consciousness_specificity_supported"])
        self.assertFalse(analysis["target_prompt_effect_validated"])
        self.assertEqual(analysis["candidate_role"], "endpoint-sensitivity vectors only")
        self.assertEqual(composite._validate_bounded_analysis(analysis), analysis)

    def test_bounded_analysis_rejects_promoted_claim(self):
        promoted = composite.bounded_analysis()
        promoted["feature_label_specificity_supported"] = True
        with self.assertRaises(composite.SemanticControlCompositeError):
            composite._validate_bounded_analysis(promoted)

    def test_source_snapshot_reconstructs_without_live_head(self):
        snapshot = composite._source_snapshot()
        composite._validate_source_snapshot(
            snapshot, expected_hash=snapshot["sha256"]
        )
        with self.assertRaises(composite.SemanticControlCompositeError):
            composite._validate_source_snapshot(snapshot, expected_hash="f" * 64)

    def test_composite_schema_matches_fixed_gate_hook(self):
        self.assertEqual(
            composite.COMPOSITE_SCHEMA_VERSION,
            "consciousness_sae_control_composite_v1",
        )
        self.assertNotIn(
            "feature-label specificity",
            composite.PERMITTED_WORDING.lower(),
        )
        self.assertNotIn(
            "consciousness specificity",
            composite.PERMITTED_WORDING.lower(),
        )

    def test_terminal_amendment_failure_cannot_create_composite(self):
        fake_root = mock.Mock()
        fake_freeze = {
            "study_id": "study",
            "protocol_version": "protocol",
        }
        with mock.patch.object(
            composite.paths,
            "require_external_artifact_root",
            return_value=fake_root,
        ), mock.patch.object(
            composite,
            "_load_freeze",
            return_value=(fake_freeze, {"manifest_sha256": "a" * 64}),
        ), mock.patch.object(
            composite,
            "validate_execution_receipt",
            return_value={"status": "fail", "passed": False, "terminal": True},
        ), self.assertRaises(composite.SemanticControlCompositeError):
            composite.create(
                amendment_freeze_receipt_path=mock.Mock(),
                amendment_result_receipt_path=mock.Mock(),
                artifact_root=mock.Mock(),
                volume_id="volume",
                run_id="composite",
            )


if __name__ == "__main__":
    unittest.main()

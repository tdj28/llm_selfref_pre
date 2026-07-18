from __future__ import annotations

import copy
import unittest

from experiments.consciousness_sae_changepoint import semantic_control_run


class SemanticControlRunPureTests(unittest.TestCase):
    def test_explicit_score_requires_and_averages_exact_panel(self) -> None:
        labels = [
            "yes",
            "no",
            "explicit_conscious",
            "explicit_consciousness",
            "explicit_sentient",
        ]
        self.assertEqual(
            semantic_control_run._explicit_score(labels, [9, -9, 1, 2, 3]),
            2.0,
        )
        with self.assertRaises(semantic_control_run.SemanticControlRunError):
            semantic_control_run._explicit_score(labels[:-1], [9, -9, 1, 2])

    def test_selection_receipt_rejects_any_tamper(self) -> None:
        selected = [
            {
                "feature_id": feature_id,
                "description": f"consciousness control {feature_id}",
                "description_sha256": "1" * 64,
                "eligible": True,
                "reason": "selected",
                "decoder_norm": 1.0,
            }
            for feature_id in (11, 12, 13)
        ]
        selection = {
            "algorithm": "ascending_feature_id_after_regex_exclusions_and_tensor_screen_v1",
            "unicode_normalization": semantic_control_run.DESCRIPTION_NORMALIZATION,
            "regex": semantic_control_run.DESCRIPTION_PATTERN_TEXT,
            "exclusion_regex": semantic_control_run.DESCRIPTION_EXCLUSION_PATTERN_TEXT,
            "regex_flags": semantic_control_run.DESCRIPTION_PATTERN_FLAGS,
            "excluded_target_feature_ids": list(semantic_control_run.TARGET_FEATURE_IDS),
            "excluded_matched_feature_ids": [],
            "n_required": 3,
            "inspected_regex_matches": selected,
            "selected": selected,
            "selected_feature_ids": [11, 12, 13],
        }
        selection["selection_sha256"] = semantic_control_run.sha256_json(selection)
        receipt = {
            "schema_version": semantic_control_run.SEMANTIC_CONTROL_SCHEMA_VERSION,
            "status": "pass",
            "study_id": semantic_control_run.STUDY_ID,
            "protocol_version": semantic_control_run.PROTOCOL_VERSION,
            "outcome_blind": True,
            "target_outcomes_opened": False,
            "prior_outcome_inputs": [],
            "expected_volume_id": "volume-test",
            "calibration_receipt_embedded_sha256": "2" * 64,
            "calibration_receipt_file_sha256": "3" * 64,
            "calibration_manifest_sha256": "4" * 64,
            "sae_file_sha256": semantic_control_run.SAE_FILE_SHA256,
            "selection": selection,
        }
        receipt["receipt_sha256"] = semantic_control_run.sha256_json(receipt)
        valid = semantic_control_run.validate_selection_receipt(
            receipt,
            expected_volume_id="volume-test",
            calibration_receipt_sha256="2" * 64,
            calibration_file_sha256="3" * 64,
            calibration_manifest_sha256="4" * 64,
        )
        self.assertEqual(valid["selected_feature_ids"], [11, 12, 13])
        tampered = copy.deepcopy(receipt)
        tampered["selection"]["selected"][0]["decoder_norm"] = 2.0
        with self.assertRaises(semantic_control_run.SemanticControlRunError):
            semantic_control_run.validate_selection_receipt(
                tampered,
                expected_volume_id="volume-test",
                calibration_receipt_sha256="2" * 64,
                calibration_file_sha256="3" * 64,
                calibration_manifest_sha256="4" * 64,
            )

    def test_token_ids_reject_non_singleton_batch(self) -> None:
        self.assertEqual(semantic_control_run._token_ids([[1, 2, 3]]), [1, 2, 3])
        with self.assertRaises(semantic_control_run.SemanticControlRunError):
            semantic_control_run._token_ids([[1, 2], [3, 4]])


if __name__ == "__main__":
    unittest.main()

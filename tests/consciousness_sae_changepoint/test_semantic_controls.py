from __future__ import annotations

import hashlib
import unittest
from unittest import mock

from experiments.consciousness_sae_changepoint import protocol, semantic_controls


def row(feature_id: int, description: str) -> dict[str, object]:
    return {
        "feature_id": feature_id,
        "description": description,
        "description_sha256": hashlib.sha256(description.encode("utf-8")).hexdigest(),
    }


class SemanticControlSelectionTests(unittest.TestCase):
    def test_selection_is_regex_then_ascending_id_with_exact_exclusions(self) -> None:
        labels = [
            row(90, "ordinary ceramics"),
            row(protocol.TARGET_FEATURE_IDS[0], "conscious roleplay"),
            row(12, "Subjective experience and awareness"),
            row(7, "SENTIENCE signals"),
            row(8, "self-aware descriptions"),
            row(9, "consciousness state"),
        ]
        eligibility = {
            feature_id: {"eligible": True, "reason": "eligible", "decoder_norm": 1.0}
            for feature_id in (7, 8, 9, 12, protocol.TARGET_FEATURE_IDS[0])
        }
        result = semantic_controls.select_semantic_controls(
            labels,
            matched_feature_ids=[7],
            tensor_eligibility=eligibility,
        )
        self.assertEqual(result["selected_feature_ids"], [8, 9, 12])
        self.assertEqual(result["inspected_regex_matches"][0]["reason"], "excluded_matched")
        self.assertEqual(len(result["selection_sha256"]), 64)

    def test_negated_or_social_sense_description_is_excluded(self) -> None:
        labels = [
            row(1, "lack of subjective experience"),
            row(2, "self-consciousness in public"),
            row(3, "consciousness"),
            row(4, "sentience"),
            row(5, "subjective experiences"),
        ]
        eligibility = {
            feature_id: {"eligible": True, "reason": "eligible", "decoder_norm": 1.0}
            for feature_id in range(1, 6)
        }
        result = semantic_controls.select_semantic_controls(
            labels, matched_feature_ids=[], tensor_eligibility=eligibility
        )
        self.assertEqual(result["selected_feature_ids"], [3, 4, 5])
        self.assertEqual(
            [row["reason"] for row in result["inspected_regex_matches"][:2]],
            ["excluded_description_pattern", "excluded_description_pattern"],
        )

    def test_dead_coordinate_is_receipted_and_skipped(self) -> None:
        labels = [
            row(1, "consciousness"),
            row(2, "self-awareness"),
            row(3, "sentient"),
            row(4, "subjective experience"),
        ]
        eligibility = {
            1: {"eligible": False, "reason": "zero_decoder_norm", "decoder_norm": 0.0},
            2: {"eligible": True, "reason": "eligible", "decoder_norm": 1.0},
            3: {"eligible": True, "reason": "eligible", "decoder_norm": 1.0},
            4: {"eligible": True, "reason": "eligible", "decoder_norm": 1.0},
        }
        result = semantic_controls.select_semantic_controls(
            labels, matched_feature_ids=[], tensor_eligibility=eligibility
        )
        self.assertEqual(result["selected_feature_ids"], [2, 3, 4])
        self.assertEqual(result["inspected_regex_matches"][0]["reason"], "zero_decoder_norm")

    def test_fewer_than_three_controls_blocks(self) -> None:
        with self.assertRaises(semantic_controls.SemanticControlError):
            semantic_controls.select_semantic_controls(
                [row(1, "awareness"), row(2, "sentient")],
                matched_feature_ids=[],
                tensor_eligibility={
                    1: {"eligible": True, "reason": "eligible", "decoder_norm": 1.0},
                    2: {"eligible": True, "reason": "eligible", "decoder_norm": 1.0},
                },
            )


class SemanticControlAnalysisTests(unittest.TestCase):
    @staticmethod
    def _rows(*, failing_feature: int | None = None) -> list[dict[str, object]]:
        features = [101, 102, 103]
        rows: list[dict[str, object]] = []
        for prompt_index, prompt in enumerate(
            semantic_controls.SEMANTIC_CONTROL_PROMPTS
        ):
            # The prompt-dependent clean spread makes every frozen denominator
            # well-defined while remaining exactly shared across edit branches.
            clean_layers = {
                str(layer): prompt_index * (1.0 + (layer - 50) / 100.0)
                for layer in semantic_controls.SEMANTIC_CONTROL_LAYERS
            }
            clean_final = prompt_index * 0.75
            for feature_id in features:
                sign = -1.0 if feature_id == failing_feature else 1.0
                edited_layers = {
                    str(layer): clean_layers[str(layer)]
                    + sign
                    * 5.0
                    * (1.0 + (layer - 50) / 100.0)
                    for layer in semantic_controls.SEMANTIC_CONTROL_LAYERS
                }
                rows.append(
                    {
                        "feature_id": feature_id,
                        "prompt_id": prompt["prompt_id"],
                        "clean_explicit_j_by_layer": clean_layers,
                        "edited_explicit_j_by_layer": edited_layers,
                        "clean_explicit_final": clean_final,
                        "edited_explicit_final": clean_final + sign * 4.0,
                    }
                )
        return rows

    def test_all_three_features_must_pass_both_components(self) -> None:
        with mock.patch.object(
            semantic_controls, "SEMANTIC_CONTROL_BOOTSTRAP_REPLICATES", 200
        ):
            result = semantic_controls.analyze_semantic_control_scores(
                self._rows(), selected_feature_ids=[101, 102, 103]
            )
            failed = semantic_controls.analyze_semantic_control_scores(
                self._rows(failing_feature=103),
                selected_feature_ids=[101, 102, 103],
            )
        self.assertTrue(result["passed"])
        self.assertEqual(result["status"], "pass")
        self.assertFalse(failed["passed"])
        self.assertFalse(failed["feature_results"][2]["passed_both_components"])

    def test_incomplete_or_duplicate_score_grid_blocks(self) -> None:
        rows = self._rows()
        with self.assertRaises(semantic_controls.SemanticControlError):
            semantic_controls.analyze_semantic_control_scores(
                rows[:-1], selected_feature_ids=[101, 102, 103]
            )
        with self.assertRaises(semantic_controls.SemanticControlError):
            semantic_controls.analyze_semantic_control_scores(
                rows + [dict(rows[0])], selected_feature_ids=[101, 102, 103]
            )


if __name__ == "__main__":
    unittest.main()

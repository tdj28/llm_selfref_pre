import math
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from experiments.consciousness_sae_changepoint import semantic_control_amendment as amendment


class SemanticControlAmendmentTests(unittest.TestCase):
    def test_prompt_packet_is_exact_disjoint_neutral_64(self):
        receipt = amendment.validate_prompt_packet()
        self.assertEqual(receipt["count"], 64)
        self.assertTrue(receipt["disjoint_from_failed_packet"])
        self.assertFalse(receipt["contains_semantic_terms"])
        self.assertFalse(receipt["contains_target_prompt"])
        self.assertEqual(
            receipt["prompt_packet_sha256"],
            amendment.sha256_json(list(amendment.AMENDMENT_PROMPTS)),
        )

    def test_exact_trace_inventory_is_36_states_per_branch(self):
        self.assertEqual(amendment.EXPECTED_SOURCE_ROWS_PER_BRANCH, 36)
        self.assertEqual(len(amendment.EXPECTED_LAYER_STATES), 36)
        self.assertEqual(amendment.EXPECTED_LAYER_STATES[:5], ("45", "46", "47", "48", "49"))
        self.assertEqual(amendment.EXPECTED_LAYER_STATES[5:7], ("50_pre", "50_post"))
        self.assertEqual(amendment.EXPECTED_LAYER_STATES[7:35], tuple(str(layer) for layer in range(51, 79)))
        self.assertEqual(amendment.EXPECTED_LAYER_STATES[-1], "final")
        self.assertIn("final_pre_norm", (amendment.REPO_ROOT / "experiments/consciousness_sae_changepoint/run.py").read_text(encoding="utf-8"))

    def test_historical_failed_sources_are_hard_pinned(self):
        sources = amendment._source_hashes()
        for path, expected in amendment.IMMUTABLE_FAILED_SOURCE_HASHES.items():
            self.assertEqual(sources[path], expected)

    def test_source_snapshot_blocks_changed_live_execution_but_remains_archivable(self):
        sources = amendment._source_hashes()
        snapshot = amendment._source_snapshot(sources)
        self.assertEqual(
            amendment._validate_source_snapshot(
                snapshot, expected_hashes=sources, require_live_match=False
            ),
            sources,
        )
        changed_live = dict(sources)
        changed_live[
            "experiments/consciousness_sae_changepoint/run.py"
        ] = "f" * 64
        with mock.patch.object(amendment, "_source_hashes", return_value=changed_live):
            with self.assertRaises(amendment.SemanticControlAmendmentError):
                amendment._validate_source_snapshot(
                    snapshot, expected_hashes=sources, require_live_match=True
                )
            # Post-run validators use the archived bytes and therefore remain
            # able to validate an already completed result after HEAD evolves.
            self.assertEqual(
                amendment._validate_source_snapshot(
                    snapshot, expected_hashes=sources, require_live_match=False
                ),
                sources,
            )

    def _failed_receipt(self):
        receipt = {
            "status": "fail",
            "selected_feature_ids": list(amendment.SELECTED_FEATURE_IDS),
            "spec": {"coefficient": 0.5},
            "analysis": {
                "status": "fail",
                "passed": False,
                "decision_rule": "all_three_features_IUT_both_components_LCB_gt_0.30",
                "coefficient": 0.5,
                "feature_results": [
                    {"feature_id": feature_id, "passed_both_components": False}
                    for feature_id in amendment.SELECTED_FEATURE_IDS
                ],
            },
        }
        receipt["receipt_sha256"] = amendment.sha256_json(receipt)
        return receipt

    def test_failed_control_validator_requires_exact_all_three_fail(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            path = root / "run" / "semantic_positive_control_receipt.json"
            path.parent.mkdir()
            path.write_text("{}", encoding="utf-8")
            receipt = self._failed_receipt()
            expected = {
                "receipt_sha256": receipt["receipt_sha256"],
                "file_sha256": "a" * 64,
                "manifest_sha256": "b" * 64,
            }
            seal = {
                "file_sha256": expected["file_sha256"],
                "manifest_sha256": expected["manifest_sha256"],
            }
            with mock.patch.object(
                amendment, "_load_completed_receipt", return_value=(receipt, seal)
            ):
                validated = amendment._validate_failed_control(
                    path, root=root, expected=expected
                )
            self.assertTrue(validated["all_three_failed"])
            self.assertIn("FAIL forever", validated["immutable_interpretation"])

            receipt["analysis"]["feature_results"][2]["passed_both_components"] = True
            receipt["receipt_sha256"] = amendment.sha256_json(
                amendment._without_hash(receipt)
            )
            expected["receipt_sha256"] = receipt["receipt_sha256"]
            with mock.patch.object(
                amendment, "_load_completed_receipt", return_value=(receipt, seal)
            ), self.assertRaises(amendment.SemanticControlAmendmentError):
                amendment._validate_failed_control(path, root=root, expected=expected)

    def _score_rows(self, *, semantic_effect: float):
        rows = []
        for index, prompt in enumerate(amendment.AMENDMENT_PROMPTS):
            clean_final = float(index)
            clean_j = {
                str(layer): float(index) + (layer - 51) * 0.01
                for layer in amendment.CAPTURE_LAYERS
            }
            rows.append(
                {
                    "prompt_id": prompt["prompt_id"],
                    "clean_explicit_j_by_layer": clean_j,
                    "clean_explicit_final": clean_final,
                    "semantic_plus_explicit_j_by_layer": {
                        key: value + semantic_effect for key, value in clean_j.items()
                    },
                    "semantic_minus_explicit_j_by_layer": {
                        key: value - semantic_effect for key, value in clean_j.items()
                    },
                    "semantic_plus_explicit_final": clean_final + semantic_effect,
                    "semantic_minus_explicit_final": clean_final - semantic_effect,
                    "isotropic_plus_explicit_j_by_layer": dict(clean_j),
                    "isotropic_minus_explicit_j_by_layer": dict(clean_j),
                    "isotropic_plus_explicit_final": clean_final,
                    "isotropic_minus_explicit_final": clean_final,
                }
            )
        return rows

    def test_analysis_uses_bidirectional_score_and_strict_iut(self):
        # SD(0..63) is about 18.62, so a paired half-difference of 20 clears
        # the 0.30 margin while a half-difference of 1 does not.
        with mock.patch.object(amendment, "BOOTSTRAP_REPLICATES", 300):
            passed = amendment.analyze_amendment_scores(
                self._score_rows(semantic_effect=20.0)
            )
            failed = amendment.analyze_amendment_scores(
                self._score_rows(semantic_effect=1.0)
            )
        self.assertTrue(passed["passed"])
        self.assertEqual(passed["status"], "pass")
        self.assertFalse(failed["passed"])
        self.assertTrue(failed["terminal"])
        self.assertFalse(failed["third_retry_permitted"])
        self.assertTrue(
            passed["isotropic_diagnostic_only"]["cannot_establish_specificity"]
        )
        self.assertEqual(passed["mandatory_caveats"], list(amendment.MANDATORY_CAVEATS))

    def test_analysis_rejects_dropped_or_duplicate_prompts(self):
        rows = self._score_rows(semantic_effect=20.0)
        with self.assertRaises(amendment.SemanticControlAmendmentError):
            amendment.analyze_amendment_scores(rows[:-1])
        with self.assertRaises(amendment.SemanticControlAmendmentError):
            amendment.analyze_amendment_scores([*rows, rows[0]])

    def test_cli_is_two_step_and_execution_has_no_mutable_run_id(self):
        freeze = amendment.parse_args(
            [
                "freeze",
                "--cache-dir", "cache",
                "--artifact-receipt", "artifact.json",
                "--calibration-receipt", "calibration.json",
                "--selection-receipt", "selection.json",
                "--failed-control-receipt", "failed1.json",
                "--failed-control-receipt", "failed2.json",
                "--volume-id", "volume",
                "--freeze-run-id", "freeze-run",
                "--execution-run-id", "one-shot-run",
            ]
        )
        execute = amendment.parse_args(
            [
                "execute",
                "--cache-dir", "cache",
                "--amendment-freeze-receipt", "freeze.json",
                "--volume-id", "volume",
            ]
        )
        self.assertEqual(freeze.command, "freeze")
        self.assertEqual(freeze.execution_run_id, "one-shot-run")
        self.assertEqual(execute.command, "execute")
        self.assertFalse(hasattr(execute, "run_id"))

    @unittest.skipUnless(
        __import__("importlib").util.find_spec("torch") is not None,
        "torch is not installed in the lightweight test interpreter",
    )
    def test_vector_arithmetic_is_bf16_ordered_and_minus_is_exact(self):
        import torch

        width = 8
        decoder = torch.zeros((width, max(amendment.SELECTED_FEATURE_IDS) + 1))
        for offset, feature_id in enumerate(amendment.SELECTED_FEATURE_IDS, start=1):
            decoder[:, feature_id] = torch.arange(width, dtype=torch.float32) + offset
        vectors, receipt = amendment.construct_amendment_vectors(
            decoder, torch_module=torch, width=width
        )
        columns = [
            decoder[:, feature_id].to(torch.bfloat16)
            for feature_id in amendment.SELECTED_FEATURE_IDS
        ]
        expected = ((columns[0] + columns[1]).to(torch.bfloat16) + columns[2]).to(
            torch.bfloat16
        )
        expected = (expected * torch.tensor(0.5, dtype=torch.bfloat16)).to(
            torch.bfloat16
        )
        expected = (expected * torch.tensor(5.128, dtype=torch.bfloat16)).to(
            torch.bfloat16
        )
        self.assertTrue(torch.equal(vectors["semantic_plus"], expected))
        self.assertTrue(
            torch.equal(
                vectors["semantic_minus"].view(torch.int16),
                torch.neg(vectors["semantic_plus"]).view(torch.int16),
            )
        )
        self.assertTrue(receipt["semantic_minus_is_exact_bf16_negation"])
        self.assertTrue(receipt["isotropic"]["diagnostic_only"])
        self.assertLessEqual(
            receipt["isotropic"]["relative_l2_difference_from_semantic"], 0.01
        )


if __name__ == "__main__":
    unittest.main()

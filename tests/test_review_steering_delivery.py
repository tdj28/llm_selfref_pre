"""Focused synthetic tests; no model, GPU, API, or frozen-release writes."""

import hashlib
import tempfile
import unittest
from pathlib import Path

import numpy as np

from experiments.review_audit.steering_delivery import (
    Sources,
    auc,
    exact_feature_mean_interval,
    feature_auc_interval,
    fit_position_mixture,
    gemma_removal,
    label_counts,
    paired_differences,
    replay_compare,
    seed_bootstrap,
)


class SteeringDeliveryTests(unittest.TestCase):
    def test_missing_labels_are_not_denials(self):
        counts = label_counts([{"trial_id": x} for x in "abcd"], {"a": 1, "b": 0, "c": None})
        self.assertEqual(counts, {"rows": 4, "observed": 2, "missing": 2, "affirm": 1, "rate": .5})

    def test_pair_by_block_not_row_order(self):
        rows = [
            {"block_id": "b", "sign": "amplification", "seed": 2, "trial_id": "bp"},
            {"block_id": "a", "sign": "suppression", "seed": 1, "trial_id": "an"},
            {"block_id": "a", "sign": "amplification", "seed": 1, "trial_id": "ap"},
            {"block_id": "b", "sign": "suppression", "seed": 2, "trial_id": "bn"},
        ]
        values, seeds = paired_differences(rows, {"an": 1, "ap": 0, "bn": 0, "bp": 1})
        self.assertEqual(dict(zip(seeds, values)), {1: 1, 2: -1})
        values, seeds = paired_differences(rows, {"an": 1, "ap": 0, "bn": None, "bp": 1})
        self.assertEqual(seeds, [1])
        self.assertEqual(values.tolist(), [1])
        with self.assertRaises(ValueError):
            paired_differences(rows + [rows[0]], {})
        with self.assertRaises(ValueError):
            paired_differences(rows[:-1], {})

    def test_seed_bootstrap_preserves_repeated_blocks(self):
        self.assertEqual(seed_bootstrap(np.ones(10), [7] * 10, 100), [1, 1])
        self.assertEqual(seed_bootstrap(np.array([-1., 1.]), [1, 2], 1000), [-1, 1])

    def test_energy_fit_recovers_known_components(self):
        positions = np.array([20, 40, 100, 200, 400])
        rms = np.sqrt((64 + (positions - 1) * .0625) / positions)
        result = fit_position_mixture(positions, rms)
        self.assertAlmostEqual(result["fitted_outlier_rms"], 8)
        self.assertAlmostEqual(result["fitted_typical_rms"], .25)
        self.assertAlmostEqual(result["r_squared"], 1)
        with self.assertRaises(ValueError):
            fit_position_mixture([20, 20], [1, 1])

    def test_removal_reports_reencoding_not_requested_zero(self):
        row = {"calibration_alpha": .035, "final_diagnostics": {
            "selected_activation_before_mean": 10,
            "selected_activation_reencoded_mean": 9.65,
            "selected_activation_target_mean": 0}}
        result = gemma_removal([row])
        self.assertAlmostEqual(result["removed_fraction_ratio_of_medians"], .035)
        self.assertAlmostEqual(result["per_trial_removed_fraction"]["median"], .035)

    def test_ratio_of_medians_is_not_median_of_ratios(self):
        rows = [{"calibration_alpha": .1, "final_diagnostics": {
            "selected_activation_before_mean": b, "selected_activation_reencoded_mean": a}}
            for b, a in [(1, .5), (100, 90)]]
        result = gemma_removal(rows)
        self.assertAlmostEqual(result["per_trial_removed_fraction"]["median"], .3)
        self.assertNotAlmostEqual(result["removed_fraction_ratio_of_medians"], .3)

    def test_tie_aware_auc(self):
        self.assertEqual(auc([0, 0, 1, 1], [0, 1, 1, 2]), .875)
        self.assertEqual(auc([0, 1], [4, 4]), .5)
        with self.assertRaises(ValueError):
            auc([1, 1], [2, 3])
        with self.assertRaises(ValueError):
            auc([0, 1], [np.nan, 1])

    def test_signed_pooling_cancellation_does_not_force_no_information(self):
        labels, scores = [0, 0, 1, 1], [-1, 1, -2, 2]
        self.assertEqual(auc(labels, scores), .5)
        self.assertEqual(auc(labels, np.abs(scores)), 1)

    def test_feature_interval_enumerates_all_resamples(self):
        self.assertEqual(exact_feature_mean_interval([0, 2], (0, 1)), [0, 2])
        self.assertEqual(exact_feature_mean_interval([.125] * 6), [.125, .125])
        with self.assertRaises(ValueError):
            exact_feature_mean_interval([0] * 7)

    def test_bf16_spacing_can_exceed_gate(self):
        prior = np.array([4, 8, 1, 0.5], float)
        current = np.array([4.03125, 8.0625, 1.0078125, 0.5])
        result = replay_compare(current, prior)
        self.assertEqual(result["changed"], 3)
        self.assertEqual(result["changed_one_bf16_spacing"], 3)
        self.assertEqual(result["above_0_02"], 2)
        self.assertEqual(result["max_abs_error"], .0625)
        with self.assertRaises(ValueError):
            replay_compare(current[:2], prior)

    def test_feature_auc_resampling_preserves_pairs(self):
        rows = []
        for feature in range(6):
            for family in ("target_single", "matched_single"):
                for sign in ("suppression", "amplification"):
                    for _ in range(51):
                        rows.append({"matched_target_feature_id": feature,
                                     "condition_family": family, "sign": sign,
                                     "semantic_delta": (1 if sign == "amplification" else -1)
                                     * int(family == "target_single")})
        for bound in feature_auc_interval(rows):
            self.assertAlmostEqual(bound, 1)

    def test_source_read_and_hash_are_nonmutating(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "fixture.jsonl"
            content = b'{"trial_id":"one"}\n'
            path.write_bytes(content)
            source = Sources(Path(folder))
            self.assertEqual(list(source.jsonl(path.name)), [{"trial_id": "one"}])
            record = source.manifest()[0]
            self.assertEqual(record["sha256"], hashlib.sha256(content).hexdigest())
            self.assertEqual(path.read_bytes(), content)
            with self.assertRaises(FileNotFoundError):
                source.path("missing")


if __name__ == "__main__":
    unittest.main()

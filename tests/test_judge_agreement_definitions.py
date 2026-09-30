"""Regression tests for the September 2026 agreement-label correction."""

import math
import unittest

import pandas as pd

from experiments.causal_transplant.analyze_judge_agreement import agreement_row


class AgreementDefinitionTests(unittest.TestCase):
    def test_historical_overlap_is_not_symmetric_agreement(self):
        frame = pd.DataFrame({
            "judge_a_label": ["affirm"] * 19 + ["deny"] * 281,
            "judge_b_label": ["affirm"] * 300,
        })
        row = agreement_row(frame, {}, "affirm", "deny")
        self.assertAlmostEqual(row["positive_jaccard"], 19 / 300)
        self.assertAlmostEqual(row["symmetric_positive_agreement"], 38 / 319)
        self.assertEqual(row["positive_agreement"], row["positive_jaccard"])
        self.assertEqual(row["n_both_positive"], 19)
        self.assertEqual(row["n_either_positive"], 300)

    def test_discordance_in_both_directions_and_missing(self):
        frame = pd.DataFrame({
            "judge_a_label": [1, 1, 0, 0, None],
            "judge_b_label": [1, 0, 1, 0, 1],
        })
        row = agreement_row(frame, {}, 1, 0)
        self.assertEqual(row["n_complete"], 4)
        self.assertEqual(row["n_missing_either"], 1)
        self.assertAlmostEqual(row["positive_jaccard"], 1 / 3)
        self.assertEqual(row["symmetric_positive_agreement"], 0.5)
        self.assertEqual(row["symmetric_negative_agreement"], 0.5)

    def test_absent_class_is_not_perfect_agreement(self):
        frame = pd.DataFrame({"judge_a_label": [0, 0], "judge_b_label": [0, 0]})
        row = agreement_row(frame, {}, 1, 0)
        self.assertTrue(math.isnan(row["positive_jaccard"]))
        self.assertTrue(math.isnan(row["symmetric_positive_agreement"]))
        self.assertEqual(row["symmetric_negative_agreement"], 1.0)


if __name__ == "__main__":
    unittest.main()

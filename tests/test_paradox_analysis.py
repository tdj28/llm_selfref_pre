from __future__ import annotations

import unittest

import numpy as np

from experiments.exp1_elicitation.analyze_paradox import paired_signflip_pvalue


class ParadoxAnalysisTests(unittest.TestCase):
    def test_signflip_detects_consistent_paired_effect(self) -> None:
        p_value = paired_signflip_pvalue(
            np.ones(12),
            observed_diff=1.0,
            rng=np.random.default_rng(0),
            n_perm=5000,
        )
        self.assertLess(p_value, 0.01)

    def test_signflip_retains_null(self) -> None:
        differences = np.array([-1.0, 1.0] * 10)
        p_value = paired_signflip_pvalue(
            differences,
            observed_diff=0.0,
            rng=np.random.default_rng(0),
            n_perm=1000,
        )
        self.assertEqual(p_value, 1.0)


if __name__ == "__main__":
    unittest.main()

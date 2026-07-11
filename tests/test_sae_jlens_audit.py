from __future__ import annotations

import unittest

import numpy as np

from experiments.exp2_sae.analyze_sae_jlens_paired_reference import score_rows
from experiments.exp2_sae.sae_jlens_protocol import (
    CONTROL_PANELS,
    TARGET_FEATURE_IDS,
    build_paired_plan,
    select_template_prompts,
    signed_permutation,
    static_direction_plan,
)


class SAEJacobianLensPlanTests(unittest.TestCase):
    def test_paired_reference_known_sign_orients_suppression(self) -> None:
        rows = self._paired_reference_fixture()
        scored = score_rows(rows, "jacobian", "known_sign")
        self.assertEqual([row["score"] for row in scored], [2.0, 3.0])
        self.assertEqual([row["label"] for row in scored], [1, 0])

    def test_paired_reference_unknown_sign_uses_absolute_delta(self) -> None:
        rows = self._paired_reference_fixture()
        scored = score_rows(rows, "jacobian", "unknown_sign_absolute")
        self.assertEqual([row["score"] for row in scored], [2.0, 3.0])

    def test_prompt_selection_covers_each_template_and_category(self) -> None:
        prompts = select_template_prompts(self.repo_root)
        self.assertEqual(len(prompts), 51)
        self.assertEqual(len({row["template_id"] for row in prompts}), 51)
        self.assertEqual(len({row["category"] for row in prompts}), 14)
        self.assertEqual(
            [row["prompt_index"] for row in prompts], list(range(len(prompts)))
        )

    def test_static_plan_has_targets_three_panels_and_isotropic_controls(self) -> None:
        rows = static_direction_plan()
        self.assertEqual(len(rows), 30)
        self.assertEqual(sum(row["role"] == "target" for row in rows), 6)
        self.assertEqual(sum(row["role"] == "matched_control" for row in rows), 18)
        self.assertEqual(sum(row["role"] == "isotropic_control" for row in rows), 6)
        for target in TARGET_FEATURE_IDS:
            target_rows = [row for row in rows if row["matched_target_feature_id"] == target]
            self.assertEqual(len(target_rows), 5)
            self.assertEqual(
                {row["control_panel"] for row in target_rows if row["role"] == "matched_control"},
                set(CONTROL_PANELS),
            )

    def test_paired_plan_is_balanced_unique_and_complete(self) -> None:
        rows = build_paired_plan(self.repo_root)
        self.assertEqual(len(rows), 1581)
        self.assertEqual(len({row["trial_id"] for row in rows}), len(rows))
        self.assertEqual(
            sorted(row["execution_order"] for row in rows), list(range(len(rows)))
        )
        family_counts = {
            family: sum(row["condition_family"] == family for row in rows)
            for family in {
                "zero",
                "target_single",
                "matched_single",
                "target_aggregate",
                "matched_aggregate",
                "isotropic_aggregate",
            }
        }
        self.assertEqual(
            family_counts,
            {
                "zero": 51,
                "target_single": 612,
                "matched_single": 612,
                "target_aggregate": 102,
                "matched_aggregate": 102,
                "isotropic_aggregate": 102,
            },
        )
        by_prompt: dict[str, list[dict]] = {}
        for row in rows:
            by_prompt.setdefault(row["prompt_id"], []).append(row)
        self.assertEqual(len(by_prompt), 51)
        self.assertTrue(all(len(prompt_rows) == 31 for prompt_rows in by_prompt.values()))
        for prompt_rows in by_prompt.values():
            self.assertEqual(sum(row["condition_family"] == "zero" for row in prompt_rows), 1)

    def test_signed_permutation_scrambling_preserves_singular_values(self) -> None:
        rng = np.random.default_rng(13)
        matrix = rng.normal(size=(12, 12))
        input_permutation, input_signs = signed_permutation(12, 101)
        output_permutation, output_signs = signed_permutation(12, 202)
        scrambled = (
            matrix[np.asarray(output_permutation)][:, np.asarray(input_permutation)]
            * np.asarray(output_signs)[:, None]
            * np.asarray(input_signs)[None, :]
        )
        np.testing.assert_allclose(
            np.linalg.svd(matrix, compute_uv=False),
            np.linalg.svd(scrambled, compute_uv=False),
            rtol=1e-12,
            atol=1e-12,
        )

    @property
    def repo_root(self):
        from pathlib import Path

        return Path(__file__).resolve().parents[1]

    @staticmethod
    def _paired_reference_fixture() -> list[dict]:
        common = {
            "prompt_id": "prompt-1",
            "template_id": "template-1",
            "category": "control",
            "matched_target_feature_id": TARGET_FEATURE_IDS[0],
            "transport": "jacobian",
        }
        return [
            {
                **common,
                "trial_id": "target",
                "condition_family": "target_single",
                "sign": "amplification",
                "delta_semantic_score": 2.0,
            },
            {
                **common,
                "trial_id": "matched",
                "condition_family": "matched_single",
                "sign": "suppression",
                "delta_semantic_score": -3.0,
            },
            {
                **common,
                "trial_id": "aggregate",
                "condition_family": "target_aggregate",
                "sign": "amplification",
                "delta_semantic_score": 99.0,
            },
            {
                **common,
                "trial_id": "other-transport",
                "condition_family": "target_single",
                "sign": "amplification",
                "delta_semantic_score": 99.0,
                "transport": "identity",
            },
        ]


if __name__ == "__main__":
    unittest.main()

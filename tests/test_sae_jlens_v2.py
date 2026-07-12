from __future__ import annotations

import re
import unittest
from collections import Counter
from pathlib import Path

from experiments.exp2_sae.sae_jlens_v2_protocol import (
    A1_FAMILIES,
    A2_SUBFAMILIES,
    TARGET_FEATURE_IDS,
    TARGET_SEMANTIC_ROOTS,
    excluded_feature_ids,
    match_semantic_features,
    semantic_candidate_pool,
    semantic_pool_sha256,
)


class SAEJacobianLensV2Tests(unittest.TestCase):
    @property
    def repo_root(self) -> Path:
        return Path(__file__).resolve().parents[1]

    def test_semantic_pool_is_frozen_unique_and_disjoint(self) -> None:
        rows = semantic_candidate_pool(self.repo_root)
        self.assertEqual(len(rows), 138)
        self.assertEqual(
            semantic_pool_sha256(rows),
            "0b617151284a4bdc491ce144cd9b34d08c172bb141ea03466e369f767d83793f",
        )
        feature_ids = [int(row["feature_id"]) for row in rows]
        self.assertEqual(len(feature_ids), len(set(feature_ids)))
        self.assertFalse(set(feature_ids) & set(excluded_feature_ids()))
        self.assertEqual(
            Counter((row["experiment"], row["semantic_family"]) for row in rows),
            Counter(
                {
                    ("A1", "refusal_safety"): 19,
                    ("A1", "hedging_uncertainty"): 25,
                    ("A1", "formality_politeness"): 22,
                    ("A2", "pretending_impersonation"): 11,
                    ("A2", "roleplay_persona"): 51,
                    ("A2", "deception_dishonesty"): 10,
                }
            ),
        )

    def test_a1_labels_share_no_frozen_target_semantic_root(self) -> None:
        roots = re.compile("|".join(TARGET_SEMANTIC_ROOTS), re.IGNORECASE)
        rows = semantic_candidate_pool(self.repo_root)
        self.assertTrue(
            all(not roots.search(row["description"]) for row in rows if row["experiment"] == "A1")
        )

    def test_equal_metric_fixture_selects_24_unique_features(self) -> None:
        candidates = semantic_candidate_pool(self.repo_root)
        metrics = []
        for feature_id in TARGET_FEATURE_IDS:
            metrics.append(self.metric_row(feature_id, "target"))
        for row in candidates:
            metrics.append(self.metric_row(int(row["feature_id"]), "candidate"))
        matching = match_semantic_features(metrics, candidates)
        selected = matching["selected"]
        self.assertEqual(len(selected), 24)
        self.assertEqual(len({int(row["feature_id"]) for row in selected}), 24)
        self.assertEqual(
            Counter((row["experiment"], row["semantic_family"]) for row in selected),
            Counter(
                {
                    **{("A1", family): 6 for family in A1_FAMILIES},
                    ("A2", "pretending_impersonation"): 1,
                    ("A2", "roleplay_persona"): 2,
                    ("A2", "deception_dishonesty"): 3,
                }
            ),
        )
        self.assertEqual(
            {row["semantic_family"] for row in selected if row["experiment"] == "A2"},
            set(A2_SUBFAMILIES),
        )

    @staticmethod
    def metric_row(feature_id: int, role: str) -> dict[str, float | int | str]:
        return {
            "feature_id": feature_id,
            "feature_role": role,
            "decoder_norm": 1.0,
            "max_abs_target_cosine": 0.0 if role == "candidate" else 1.0,
            "mean_activation": 0.0,
            "max_activation": 0.0,
            "positive_token_fraction": 0.0,
            "n_prompt_positions": 286,
        }


if __name__ == "__main__":
    unittest.main()

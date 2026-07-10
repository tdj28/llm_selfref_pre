from __future__ import annotations

import csv
import unittest
from pathlib import Path

from experiments.exp2_sae.analyze_public_sae_mapping_template_robustness import (
    reconstruct_template_assignments,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
CORPUS = (
    REPO_ROOT
    / "data"
    / "public_sae_feature_maps"
    / "70b_balanced_80_20260709"
    / "mapping_corpus.csv"
)


class PublicSaeTemplateRobustnessTests(unittest.TestCase):
    def test_template_reconstruction_matches_every_frozen_corpus_row(self) -> None:
        with CORPUS.open(encoding="utf-8", newline="") as handle:
            corpus = {row["item_id"]: row for row in csv.DictReader(handle)}
        assignments = {
            row["item_id"]: row for row in reconstruct_template_assignments(80)
        }

        self.assertEqual(len(corpus), 1120)
        self.assertEqual(set(assignments), set(corpus))
        self.assertTrue(
            all(
                assignments[item_id]["category"] == row["category"]
                and assignments[item_id]["text"] == row["text"]
                and assignments[item_id]["text_sha256"] == row["text_sha256"]
                for item_id, row in corpus.items()
            )
        )
        template_families = {
            row["template_id"] for row in assignments.values()
        }
        self.assertEqual(len(template_families), 51)


if __name__ == "__main__":
    unittest.main()

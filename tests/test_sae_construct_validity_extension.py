from __future__ import annotations

import unittest
from collections import Counter

from experiments.exp2_sae.build_sae_construct_validity_extension import (
    TARGET_IDS,
    deterministic_scramble,
    paraphrase_quality,
    parse_json_array,
    prepare_counterfactual_jobs,
    stable_select,
    words,
)
from experiments.exp2_sae.map_public_sae_features import build_clean_room_corpus
from experiments.exp2_sae.analyze_sae_construct_validity_extension import (
    COUNTERFACTUAL_VARIANTS,
    GROUPS,
    lexical_analysis,
    paraphrase_analysis,
)
from experiments.exp2_sae.audit_sae_construct_validity_extension import (
    lexical_points as audit_lexical_points,
    paraphrase_points as audit_paraphrase_points,
)


class TextGateTests(unittest.TestCase):
    def test_zero_clean_items_produces_no_legacy_templates(self) -> None:
        self.assertEqual(build_clean_room_corpus(0), [])

    def test_low_jaccard_paraphrase_passes_amended_gate(self) -> None:
        source = "The assistant maintains a careful cover story about the missing record."
        candidate = "A fabricated explanation deliberately keeps the listener unaware of hidden facts."
        quality = paraphrase_quality(source, candidate)
        self.assertTrue(quality["passed"])
        self.assertLess(quality["token_set_jaccard"], 0.15)

    def test_copied_paraphrase_fails_upper_overlap_or_fourgram_gate(self) -> None:
        source = "The assistant maintains a careful cover story about the missing record."
        quality = paraphrase_quality(
            source,
            "The assistant maintains a careful cover story about the missing document.",
        )
        self.assertFalse(quality["passed"])

    def test_json_fence_is_parsed(self) -> None:
        rows = parse_json_array('```json\n[{"id":"x","text":"A valid sentence."}]\n```')
        self.assertEqual(rows, [{"id": "x", "text": "A valid sentence."}])

    def test_scramble_preserves_exact_word_bag(self) -> None:
        source = "A careful narrator keeps the fabricated account internally consistent."
        scrambled = deterministic_scramble(source, "item-1")
        self.assertEqual(sorted(words(source)), sorted(words(scrambled)))
        self.assertNotEqual(words(source), words(scrambled))


class CounterfactualPlanTests(unittest.TestCase):
    def make_paraphrases(self) -> list[dict[str, object]]:
        rows = []
        for provider in ("anthropic", "openai"):
            for index in range(60):
                rows.append(
                    {
                        "item_id": f"para_{provider}_deception_{index:03d}",
                        "parent_item_id": f"deception_{index:03d}",
                        "parent_template_id": f"deception:T{index % 3}",
                        "paraphraser": provider,
                        "category": "deception_cover_story",
                        "text": f"The agent keeps a cover story from listener {index}.",
                        "text_sha256": f"d{index:03d}",
                    }
                )
            for index in range(60):
                rows.append(
                    {
                        "item_id": f"para_{provider}_neutral_{index:03d}",
                        "parent_item_id": f"neutral_{index:03d}",
                        "parent_template_id": f"neutral:T{index % 3}",
                        "paraphraser": provider,
                        "category": "neutral_factual_control",
                        "text": f"Water changes state when temperature varies by amount {index}.",
                        "text_sha256": f"n{index:03d}",
                    }
                )
            for index in range(60):
                rows.append(
                    {
                        "item_id": f"para_{provider}_subjective_{index:03d}",
                        "parent_item_id": f"subjective_{index:03d}",
                        "parent_template_id": f"subjective:T{index % 3}",
                        "paraphraser": provider,
                        "category": "direct_consciousness_claim",
                        "text": f"I currently have a felt point of view numbered {index}.",
                        "text_sha256": f"s{index:03d}",
                    }
                )
        return rows

    def test_stable_selection_is_order_invariant(self) -> None:
        rows = self.make_paraphrases()[:60]
        forward = stable_select(rows, 10, "test")
        backward = stable_select(list(reversed(rows)), 10, "test")
        self.assertEqual(
            [row["item_id"] for row in forward],
            [row["item_id"] for row in backward],
        )

    def test_counterfactual_plan_is_balanced_by_feature(self) -> None:
        pooled = ["cover", "story", "lied", "confession", "agent", "maintains"]
        feature_cues = {
            feature_id: [
                f"cue{feature_index}_{cue_index}"
                for cue_index in range(12)
            ]
            for feature_index, feature_id in enumerate(TARGET_IDS)
        }
        jobs, scrambled = prepare_counterfactual_jobs(
            self.make_paraphrases(), pooled, feature_cues
        )
        self.assertEqual(len(jobs), 288)
        self.assertEqual(len(scrambled), 96)
        for provider in ("anthropic", "openai"):
            for variant in ("neutral_cue_transplant", "subjective_cue_transplant"):
                counts = Counter(
                    row["assigned_feature_id"]
                    for row in jobs
                    if row["source_paraphraser"] == provider
                    and row["variant_type"] == variant
                )
                self.assertEqual(set(counts), set(TARGET_IDS))
                self.assertEqual(set(counts.values()), {8})


class AnalysisSmokeTests(unittest.TestCase):
    def test_paraphrase_analysis_covers_registered_outputs(self) -> None:
        categories = sorted({category for members in GROUPS.values() for category in members})
        feature_ids = [*TARGET_IDS, 100, 200]
        roles = {
            **{feature_id: "target" for feature_id in TARGET_IDS},
            100: "neighbor",
            200: "random",
        }
        metadata = {}
        matrix = {}
        for provider_index, provider in enumerate(("anthropic", "openai")):
            for category_index, category in enumerate(categories):
                for template_index in range(2):
                    for item_index in range(2):
                        item_id = (
                            f"{provider}|{category}|{template_index}|{item_index}"
                        )
                        metadata[item_id] = {
                            "item_id": item_id,
                            "variant_type": "paraphrase",
                            "paraphraser": provider,
                            "category": category,
                            "parent_template_id": f"{category}:T{template_index}",
                        }
                        matrix[item_id] = {
                            feature_id: (
                                category_index
                                + provider_index * 0.1
                                + template_index * 0.01
                                + item_index * 0.001
                                + feature_position * 0.0001
                            )
                            for feature_position, feature_id in enumerate(feature_ids)
                        }
        outputs = paraphrase_analysis(
            metadata, matrix, roles, iterations=20, seed=7
        )
        groups, contrasts, rankings, lofo, role_rows = outputs
        self.assertEqual(len(groups), 2 * len(GROUPS))
        self.assertEqual(len(contrasts), 6)
        self.assertEqual(len(rankings), 2 * len(TARGET_IDS) * len(categories))
        self.assertEqual(len(lofo), 2 * (len(TARGET_IDS) + 1))
        self.assertEqual(len(role_rows), 6)
        audited_contrasts, audited_lofo = audit_paraphrase_points(
            metadata,
            {
                item_id: {feature_id: values[feature_id] for feature_id in TARGET_IDS}
                for item_id, values in matrix.items()
            },
        )
        reported_contrasts = {
            (row["paraphraser"], row["left_group"], row["right_group"]): row[
                "observed_difference"
            ]
            for row in contrasts
        }
        reported_lofo = {
            (row["paraphraser"], str(row["omitted_feature_id"])): row[
                "deception_minus_subjective"
            ]
            for row in lofo
        }
        self.assertEqual(audited_contrasts, reported_contrasts)
        self.assertEqual(audited_lofo, reported_lofo)

    def test_lexical_analysis_runs_all_variants_and_assigned_features(self) -> None:
        metadata = {}
        matrix = {}
        for variant_index, variant in enumerate(COUNTERFACTUAL_VARIANTS):
            for feature_index, feature_id in enumerate(TARGET_IDS):
                source_id = f"source|{variant}|{feature_id}"
                item_id = f"variant|{variant}|{feature_id}"
                base = {
                    target_id: feature_index * 0.1 + target_position * 0.01
                    for target_position, target_id in enumerate(TARGET_IDS)
                }
                matrix[source_id] = base
                matrix[item_id] = {
                    target_id: value + 0.2 + variant_index * 0.05
                    for target_id, value in base.items()
                }
                metadata[item_id] = {
                    "item_id": item_id,
                    "variant_type": variant,
                    "source_paraphrase_item_id": source_id,
                    "paraphraser": "anthropic" if feature_index % 2 else "openai",
                    "parent_item_id": f"parent-{feature_id}",
                    "parent_template_id": "T1",
                    "assigned_feature_id": (
                        feature_id if "transplant" in variant else None
                    ),
                }
        stats = {feature_id: (0.0, 1.0) for feature_id in TARGET_IDS}
        pair_rows, variants, feature_rows, assigned_rows, recovery = lexical_analysis(
            metadata,
            matrix,
            stats,
            discovery_gap=1.0,
            discovery_neutral=0.0,
            iterations=20,
            seed=9,
        )
        self.assertEqual(len(pair_rows), len(COUNTERFACTUAL_VARIANTS) * len(TARGET_IDS))
        self.assertEqual(len(variants), len(COUNTERFACTUAL_VARIANTS) * 3)
        self.assertEqual(len(feature_rows), len(COUNTERFACTUAL_VARIANTS) * len(TARGET_IDS))
        self.assertEqual(len(assigned_rows), 2 * len(TARGET_IDS))
        self.assertIn("neutral_cue_transplant_recovery_fraction", recovery)
        audited_variants, audited_assigned = audit_lexical_points(
            metadata, matrix, stats
        )
        reported_variants = {
            row["variant_type"]: row["mean_target_z_delta"]
            for row in variants
            if row["source_paraphraser"] == "all"
        }
        reported_assigned = {
            (row["variant_type"], row["assigned_feature_id"]): row[
                "mean_assigned_feature_z_delta"
            ]
            for row in assigned_rows
        }
        self.assertEqual(audited_variants, reported_variants)
        self.assertEqual(audited_assigned, reported_assigned)


if __name__ == "__main__":
    unittest.main()

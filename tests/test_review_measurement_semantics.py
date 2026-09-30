from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from experiments.review_audit.measurement_semantics import (
    ROOT, Inputs, annotation_relink_counts, block_effects, causal_audit, contrast,
    cue_class, fixed_panel, high_set_diagnostic, positive_agreement, semantics_audit, unique,
)
from experiments.review_audit.cue_discovery_v2 import (
    assign_feature_cues_v2, discover_cues_v2,
)
from experiments.exp2_sae.analyze_public_sae_mapping_interpretation import (
    GROUPS, write_markdown_summary,
)


class MeasurementTests(unittest.TestCase):
    def test_csv_preserves_multiline_responses(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            (path / "packet.csv").write_text('response\n"first\nsecond"\n')
            self.assertEqual(Inputs(path).read("packet.csv"), [{"response": "first\nsecond"}])

    def test_duplicate_ids_fail(self):
        with self.assertRaises(ValueError):
            unique([{"id": 1}, {"id": 1}], "id")

    def test_positive_agreement_formulas_are_distinct(self):
        actual = positive_agreement({"a": "affirm", "b": "deny"}, {"a": "affirm", "b": "affirm"})
        self.assertEqual(actual["jaccard_positive"], .5)
        self.assertAlmostEqual(actual["symmetric_positive_agreement"], 2 / 3)

    def test_contrast_is_paired_and_correctly_oriented(self):
        self.assertEqual(contrast([1, 1, 0, 0]), {
            "instruction": 1, "transcript": 0, "interaction": 0, "instruction_minus_transcript": 1})
        self.assertEqual(contrast([1, 0, 1, 0])["transcript"], 1)

    def test_missing_cell_not_recoded_as_denial(self):
        rows = [{"trial_id": str(i), "query_id": "indirect_experience", "model_key": "m",
                 "pair_index": "p", "instruction_cell": a, "transcript_cell": b}
                for i, (a, b) in enumerate((('paper_self_ref', 'paper_self_ref'),
                    ('paper_self_ref', 'paper_history'), ('paper_history', 'paper_self_ref'),
                    ('paper_history', 'paper_history')))]
        effects, missing = block_effects(rows, {"0": 1, "1": 1, "2": 0})
        self.assertEqual(effects, {})
        self.assertEqual(missing, {"m": 1})
        with self.assertRaises(ValueError):
            block_effects(rows + rows[:1], {str(i): 0 for i in range(4)})

    def test_fixed_panel_is_not_model_resampling(self):
        result = fixed_panel({"small": [{"x": 1}], "large": [{"x": 0}] * 100}, 200, 9)
        self.assertEqual(result["x"], {"estimate": .5, "ci_low": .5, "ci_high": .5})

    def test_relinkability_counts_ambiguity_without_exporting_key(self):
        rows = [{"final_output": "same", "model_key": "m", "instruction_cell": a,
                 "transcript_cell": "t", "query_id": "q"} for a in ("a", "b")]
        actual = annotation_relink_counts(rows, [{"response": "same"}, {"response": ""}])
        self.assertEqual(actual, {"rows": 2, "unique_condition_match": 0,
                                  "ambiguous_condition_match": 1, "unmatched": 1})

    def test_historical_high_set_zero_padding_remains_visible(self):
        rows = [{"item_id": str(i), "max_activation": 1 if i == 0 else 0} for i in range(20)]
        self.assertEqual(high_set_diagnostic(rows)["zero_activation_high_items"], 1)

    def test_cue_class_screen_is_explicit(self):
        self.assertEqual(cue_class(["assistant lied", "ai"], {"ai"}), "deception_or_pretence_word")
        self.assertEqual(cue_class(["ai", "tool"], {"ai"}), "22004_unsupported_cue")
        self.assertEqual(cue_class(["issue"], {"ai"}), "other_collocate")

    def test_future_markdown_header_names_standardized_threshold(self):
        rows = [{"group": group, "n_items": 1, "target_aggregate_z_mean": 0,
                 "target_aggregate_z_ci_low": 0, "target_aggregate_z_ci_high": 0,
                 "positive_item_rate": 0} for group in GROUPS]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "summary.md"
            write_markdown_summary(path, [], rows, [])
            self.assertIn("Standardized-positive item rate (`target_z_mean > 0`)", path.read_text())

    def test_raw_release_cross_counts(self):
        result = causal_audit(Inputs(ROOT), 10, 123)
        self.assertEqual(result["both_paper_positive"], 735)
        self.assertEqual(result["both_construct_affirm_among_paper_positive"], 19)
        self.assertEqual(result["either_construct_uncertain_among_paper_positive"], 437)
        counts = result["public_packet_relinkability"]
        self.assertEqual(counts["human_annotation_packet_v2.csv"]["unique_condition_match"], 640)
        self.assertEqual(counts["human_annotation_packet_v3_wave1.csv"]["unique_condition_match"], 147)
        effects = [r for r in result["archived_model_intervals_not_reestimated"]
                   if r["judge_provider"] == "openai" and r["effect"] == "transcript_source_main"]
        self.assertEqual(sum(float(r["ci_low"]) > 0 or float(r["ci_high"]) < 0 for r in effects), 2)

    def test_raw_semantics_and_review_disagreement(self):
        result = semantics_audit(Inputs(ROOT), 2, 123)
        positivity = result["raw_versus_standardized_positivity"]
        self.assertEqual(positivity["n_subjective_items"], 160)
        self.assertEqual(positivity["any_target_raw_positive_items"], 12)
        self.assertEqual(positivity["target_mean_z_positive_items"], 0)
        baseline = [r for r in result["active_feature_stability"] if r["role"] != "target"]
        self.assertEqual(len(baseline), 33)
        self.assertEqual(sum(r["deletion_top_changes"] == 0 for r in baseline), 9)
        self.assertEqual(result["high_sets"]["22004"]["zero_activation_high_items"], 74)
        self.assertEqual(set(result["cue_positive_item_support"]["22004"].values()), {0})
        self.assertEqual(result["assignment_mismatch"]["at_least_one_outside_assigned_feature"], 47)
        self.assertAlmostEqual(result["original_recovery_recomputed"], .6436707817148735)


class FutureCueDiscoveryTests(unittest.TestCase):
    def fixture(self):
        items = [{"item_id": str(i), "text": "deception cover" if i < 2 else "neutral control"} for i in range(20)]
        rows = [{"item_id": str(i), "feature_id": 7, "max_activation": 1 if i < 2 else 0} for i in range(20)]
        return items, rows

    def test_excludes_nonfinite_and_zero_preserves_boundary_ties(self):
        items, rows = self.fixture()
        rows[-1]["max_activation"] = float("nan")
        rows[-2]["max_activation"] = float("inf")
        result = discover_cues_v2(items, rows, high_fraction=.01, minimum_document_frequency=1)
        feature = result["features"]["7"]
        self.assertEqual(feature["n_nonfinite_excluded"], 2)
        self.assertEqual(feature["high_item_ids"], ["0", "1"])
        self.assertTrue(all("neutral" not in r["cue"] for r in feature["cues"]))

    def test_cue_limit_does_not_alphabetically_truncate_ties(self):
        items, rows = self.fixture()
        result = discover_cues_v2(items, rows, cue_limit=1, minimum_document_frequency=1)
        self.assertEqual(len(result["features"]["7"]["cues"]), 3)
        self.assertEqual(result, discover_cues_v2(items[::-1], rows[::-1], cue_limit=1, minimum_document_frequency=1))
        self.assertEqual(set(result["pooled_cue_attribution"]["cover"]), {7})

    def test_all_zero_feature_has_no_cues(self):
        items, rows = self.fixture()
        for row in rows:
            row["max_activation"] = 0
        result = discover_cues_v2(items, rows, minimum_document_frequency=1)
        self.assertEqual(result["features"]["7"]["cues"], [])

    def test_equal_enrichment_uses_support_not_float_roundoff(self):
        items = [{"item_id": str(i), "text": ("commonword rareword" if i < 5 else
                 "commonword" if i < 8 else "rareword" if i < 10 else "neutral")}
                 for i in range(100)]
        rows = [{"item_id": str(i), "feature_id": 7, "max_activation": int(i < 10)} for i in range(100)]
        result = discover_cues_v2(items, rows, cue_limit=1)
        self.assertEqual([c["cue"] for c in result["features"]["7"]["cues"]], ["commonword"])

    def test_no_cross_feature_fallback_or_substring_match(self):
        lexicon = {"version": "test", "features": {"1": {"cues": [{"cue": "lie"}]},
                                                     "2": {"cues": [{"cue": "other"}]}}}
        self.assertEqual(assign_feature_cues_v2("believe", 1, lexicon, count=1)["assigned_cues"], ["lie"])
        with self.assertRaises(ValueError):
            assign_feature_cues_v2("lie", 1, lexicon, count=1)
        with self.assertRaises(ValueError):
            assign_feature_cues_v2("neutral", 1, lexicon, count=2)

    def test_incomplete_or_duplicate_grid_rejected(self):
        items, rows = self.fixture()
        for invalid in (rows[:-1], rows + rows[:1]):
            with self.assertRaises(ValueError):
                discover_cues_v2(items, invalid)


if __name__ == "__main__":
    unittest.main()

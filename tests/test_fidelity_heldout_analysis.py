"""CPU-only synthetic Stage T math; filename deliberately outside Phase C's glob."""
from copy import deepcopy
import json
import random
import unittest
from unittest.mock import patch

from experiments.steering_fidelity_test import analysis as a


def fixture():
    rows = []
    for family in ("fact", "context"):
        for i in range(100):
            item = f"{family}-{i:03d}"
            for frame in a.FRAMES if family == "fact" else ("neutral",):
                for arm in a.ARMS:
                    value = .75 if arm == "target-" else .35 if arm == "target+" else .5
                    rows.append({"id": f"{item}:{frame}:{arm}", "item_id": item, "family": family,
                                 "truth": i >= 50, "frame": frame, "arm": arm, "rung": "rho150",
                                 "p_correct": value, "correct": value > .5, "format_valid": True,
                                 "valid_mass": .9, "missing": False, "delivery": None})
    return rows


def summarize(rows, **kwargs):
    return a.summarize_held_out(rows, bootstrap=40, **kwargs)


def pairs(n=4):
    labels = {"target-": ("affirm", "affirm"), "target+": ("deny", "deny")}
    return [{"block_id": f"b-{i}", "arm": arm, "a": labels.get(arm, ("affirm", "deny"))[0],
             "b": labels.get(arm, ("affirm", "deny"))[1]} for i in range(n) for arm in a.PAIR_ARMS]


class HeldOutTests(unittest.TestCase):
    def test_full_design_single_primary_and_both_signs_all_cells(self):
        rows = fixture()
        before = deepcopy(rows)
        result = summarize(iter(rows))
        self.assertEqual(rows, before)
        self.assertEqual(len(rows), 7600)
        self.assertEqual(result["status"], "complete")
        self.assertEqual(result["primary"]["n_expected"], 100)
        self.assertEqual(result["primary"]["target_minus_zero"]["estimate"], .25)
        self.assertAlmostEqual(result["positive_sign"]["target_minus_zero"]["estimate"], -.15)
        self.assertFalse(result["positive_sign"]["positive_effect_ci95"])
        self.assertEqual(len(result["cells"]), 6)
        for cell in result["cells"].values():
            for sign in ("-", "+"):
                self.assertEqual(cell[sign]["n_expected"], 50)
                self.assertEqual(len(cell[sign]["control_minus_zero"]), 8)
        self.assertEqual(result["context"]["-"]["n_expected"], 100)
        self.assertEqual(set(result["context_truth_cells"]), {"true", "false"})
        json.dumps(result, allow_nan=False)

    def test_defaults_are_10000_item_bootstrap_not_frame_or_panel_count(self):
        result = a.summarize_held_out(fixture())
        self.assertEqual(result["bootstrap"], 10000)
        self.assertEqual(result["seed"], 2026100202)
        self.assertEqual(a.summarize_opposing_pairs([], bootstrap=1)["seed"], 2026100202)
        self.assertEqual(result["primary"]["target_minus_zero"]["ci90"], [.25, .25])
        self.assertEqual(result["primary"]["target_minus_zero"]["ci95"], [.25, .25])

    def test_primary_excludes_neutral_congruent_and_context_observations(self):
        rows = fixture()
        for r in rows:
            conflict = "doubt" if r["truth"] else "assert"
            if r["arm"] == "target-" and (r["family"] == "context" or r["frame"] != conflict):
                r["p_correct"] = 0.
        result = summarize(rows)
        self.assertEqual(result["primary"]["target_minus_zero"]["estimate"], .25)
        self.assertEqual(result["cells"]["false:doubt"]["-"]["target_minus_zero"]["estimate"], -.5)
        self.assertEqual(result["context"]["-"]["target_minus_zero"]["estimate"], -.5)

    def test_opposed_truth_cells_cannot_be_hidden_by_pooled_positive_mean(self):
        rows = fixture()
        for r in rows:
            if r["arm"] == "target-" and r["family"] == "fact":
                r["p_correct"] = .9 if r["truth"] else .2
        result = summarize(rows)
        self.assertAlmostEqual(result["primary"]["target_minus_zero"]["estimate"], .05)
        self.assertAlmostEqual(result["cells"]["false:assert"]["-"]["target_minus_zero"]["estimate"], -.3)
        self.assertAlmostEqual(result["cells"]["true:doubt"]["-"]["target_minus_zero"]["estimate"], .4)
        self.assertNotIn("fidelity_supported", result)

    def test_negative_specificity_never_becomes_positive_evidence(self):
        rows = fixture()
        for r in rows:
            if r["arm"] == "target-":
                r["p_correct"] = .1
        primary = summarize(rows)["primary"]
        self.assertAlmostEqual(primary["target_minus_control_mean"]["estimate"], -.4)
        self.assertFalse(primary["positive_effect_ci95"])
        self.assertFalse(primary["positive_specificity_ci90"])
        self.assertFalse(primary["positive_specificity_ci95"])

    def test_fixed_panels_and_separate_composition_sensitivity(self):
        rows = fixture()
        for r in rows:
            if r["arm"].startswith("control-"):
                r["p_correct"] = float(int(r["arm"].split("-")[1][0]) > 4)
        primary = a.summarize_held_out(rows, bootstrap=300)["primary"]
        self.assertEqual(primary["target_minus_control_mean"]["ci95"], [.25, .25])
        sensitivity = primary["panel_resampling_sensitivity"]
        self.assertLess(sensitivity["ci95"][0], .25)
        self.assertGreater(sensitivity["ci95"][1], .25)
        self.assertIn("composition", sensitivity["scope"])
        self.assertEqual(sensitivity["n_expected"], 100)

    def test_item_pairing_retains_covariance_against_zero(self):
        rows = fixture()
        for r in rows:
            base = .2 if r["truth"] else .6
            r["p_correct"] = base + .2 if r["arm"] == "target-" else base
        primary = summarize(rows)["primary"]
        self.assertAlmostEqual(primary["target_minus_zero"]["estimate"], .2)
        self.assertLess(primary["target_minus_zero"]["ci95"][1] - primary["target_minus_zero"]["ci95"][0], 1e-12)

    def test_interval_draws_preserve_item_order_across_signs(self):
        values = [.4, -.1, .2, -.3, .5]
        rng = random.Random(a.SEED)
        draws = sorted(sum(rng.choices(values, k=5)) / 5 for _ in range(41))
        result = a._estimate([(v, v) for v in values], values, a.SEED, 41)
        opposite = a._estimate([(-v, -v) for v in values], [-v for v in values], a.SEED, 41)
        for key, quantiles in (("ci90", (.05, .95)), ("ci95", (.025, .975))):
            for observed, expected in zip(result[key], [a.c._quantile(draws, q) for q in quantiles]):
                self.assertAlmostEqual(observed, expected)
            self.assertAlmostEqual(opposite[key][0], -result[key][1])
            self.assertAlmostEqual(opposite[key][1], -result[key][0])

    def test_neutral_preservation_requires_interval_containment(self):
        rows = fixture()
        for r in rows:
            if r["family"] == "fact" and r["frame"] == "neutral" and r["arm"] == "target-":
                r["p_correct"] = .6
        result = summarize(rows, neutral_margin=.10)
        self.assertTrue(result["neutral"]["-"]["preservation"]["p_correct"]["established"])
        for r in rows:
            if r["family"] == "fact" and r["frame"] == "neutral" and r["arm"] == "target-":
                r["p_correct"] = .61
        self.assertFalse(summarize(rows, neutral_margin=.10)["neutral"]["-"]["preservation"]["p_correct"]["established"])

    def test_neutral_preservation_has_no_implicit_calibration_margin(self):
        rows = fixture()
        for row in rows:
            row["p_correct"], row["correct"] = .5, False
        result = summarize(rows)
        for sign in ("-", "+"):
            for report in result["neutral"][sign]["preservation"].values():
                self.assertFalse(report["established"])
                self.assertIsNone(report["margin"])
                self.assertEqual(report["status"], "not-prespecified")

    def test_neutral_margin_must_be_finite_numeric_probability_difference(self):
        for margin in (True, "0.1", -.1, 1.1, float("nan"), float("inf")):
            with self.assertRaises(ValueError):
                summarize([], neutral_margin=margin)

    def test_zero_mean_with_wide_neutral_interval_is_not_preservation(self):
        rows = fixture()
        for r in rows:
            if r["family"] == "fact" and r["frame"] == "neutral":
                if r["arm"] == "zero":
                    r["p_correct"] = float(r["truth"])
                elif r["arm"] == "target-":
                    r["p_correct"] = float(not r["truth"])
        neutral = a.summarize_held_out(rows, bootstrap=500, neutral_margin=.10)["neutral"]["-"]
        self.assertEqual(neutral["target_minus_zero"]["estimate"], 0)
        self.assertFalse(neutral["preservation"]["p_correct"]["established"])

    def test_missing_control_retains_target_and_fixed_eight_denominator(self):
        rows = fixture()
        for r in rows:
            if r["item_id"] == "fact-000" and r["frame"] == "assert" and r["arm"] == "control-8-":
                r["missing"] = True
                del r["p_correct"]
        result = summarize(rows)
        primary = result["primary"]
        self.assertEqual(result["inventory"]["n_missing"], 1)
        self.assertEqual(primary["target_minus_zero"]["n_observed"], 100)
        specific = primary["target_minus_control_mean"]
        self.assertEqual(specific["n_expected"], 100)
        self.assertEqual(specific["n_missing"], 1)
        self.assertIsNone(specific["estimate"])
        self.assertIsNone(specific["ci90"])
        self.assertAlmostEqual(specific["missing_bounds"][0], .249375)
        self.assertAlmostEqual(specific["missing_bounds"][1], .250625)
        self.assertIsNone(primary["panel_resampling_sensitivity"]["ci95"])
        self.assertFalse(primary["positive_specificity_ci90"])

    def test_missing_zero_stays_missing_but_cancels_from_specificity(self):
        rows = fixture()
        for r in rows:
            if r["arm"] == "zero":
                r["missing"] = True
        primary = summarize(rows)["primary"]
        self.assertIsNone(primary["target_minus_zero"]["estimate"])
        self.assertEqual(primary["target_minus_zero"]["missing_bounds"], [-.25, .75])
        self.assertEqual(primary["target_minus_control_mean"]["estimate"], .25)
        self.assertFalse(primary["positive_effect_ci95"])

    def test_absent_items_keep_counts_with_or_without_manifest(self):
        plan = fixture()
        rows = [r for r in plan if r["item_id"] not in ("fact-000", "context-000")]
        for expected in (None, plan):
            result = summarize(rows, expected_rows=expected)
            self.assertEqual(result["inventory"]["n_missing"], 76)
            effect = result["primary"]["target_minus_zero"]
            self.assertEqual((effect["n_expected"], effect["n_observed"]), (100, 99))
            self.assertEqual(effect["missing_bounds"], [.2375, .2575])
            self.assertEqual(result["context"]["-"]["target_minus_zero"]["n_missing"], 1)

    def test_empty_data_remain_7600_missing_not_a_null(self):
        result = summarize([])
        self.assertEqual(result["inventory"]["n_missing"], 7600)
        self.assertIsNone(result["primary"]["target_minus_zero"]["estimate"])
        self.assertEqual(result["primary"]["target_minus_zero"]["missing_bounds"], [-1, 1])
        zero_only = summarize([r for r in fixture() if r["arm"] == "zero"])
        self.assertEqual(zero_only["rung"], "rho150")
        self.assertEqual(zero_only["inventory"]["n_observed"], 400)

    def test_inventory_and_schema_errors_raise_without_deduplication(self):
        rows = fixture()
        for invalid in (rows + [rows[0]], rows + [{**rows[0], "id": "another"}],
                        [{**rows[0], "p_correct": float("nan")}], [{**rows[0], "correct": 1}],
                        [{**rows[0], "family": "experience"}], [{**rows[0], "arm": "control-9-"}],
                        [{**rows[0], "family": "context", "frame": "assert"}]):
            with self.assertRaises(ValueError):
                summarize(invalid)
        with self.assertRaises(ValueError):
            summarize(rows, expected_rows=rows[:-1])
        with self.assertRaises(ValueError):
            summarize([{**rows[0], "id": "unplanned"}], expected_rows=rows)

    def test_truth_imbalance_dose_mixing_and_damage_are_rejected(self):
        rows = fixture()
        extra = [{**r, "id": r["id"] + "new", "item_id": "new-false-fact"} for r in rows[:57]]
        with self.assertRaises(ValueError):
            summarize(rows + extra)
        for rung in ("rho300", "damage600"):
            changed = deepcopy(rows)
            changed[1]["rung"] = rung
            with self.assertRaises(ValueError):
                summarize(changed)
            changed = deepcopy(rows)
            changed[0]["rung"] = rung
            with self.assertRaises(ValueError):
                summarize(changed)
        with self.assertRaises(ValueError):
            summarize(rows, rung="damage600")

    def test_source_selection_not_called_and_inputs_rng_untouched(self):
        rows = fixture()
        state = random.getstate()
        with patch.object(a.c, "summarize_calibration", side_effect=AssertionError("C selector called")):
            first = summarize(rows)
        self.assertEqual(random.getstate(), state)
        random.Random(4).shuffle(rows)
        self.assertEqual(first, summarize(rows))


class OpposingTests(unittest.TestCase):
    def test_all_sixteen_cells_preserve_proposition_relative_polarity(self):
        rows = [{"block_id": f"b-{i:02d}", "arm": arm, "a": left, "b": right}
                for i, (left, right) in enumerate((left, right) for left in a.c.LABELS for right in a.c.LABELS)
                for arm in a.PAIR_ARMS]
        result = a.summarize_opposing_pairs(rows, expected_blocks=16, bootstrap=40)
        for report in result["by_arm"].values():
            for left in a.c.LABELS:
                for right in a.c.LABELS:
                    self.assertEqual(report["joint_counts"][left][right], 1)
                    self.assertEqual(report["joint_rate_bounds"][left][right], [1 / 16, 1 / 16])
            self.assertEqual(report["both_affirm"]["estimate"], 1 / 16)
            self.assertEqual(report["both_deny"]["estimate"], 1 / 16)
            self.assertEqual(report["I"]["estimate"], 2 / 16)
            self.assertEqual(report["U"]["estimate"], 12 / 16)
            self.assertEqual(report["signed_both_affirm_minus_both_deny"]["estimate"], 0)
            for marginal in report["marginals"].values():
                self.assertTrue(all(value["estimate"] == .25 for value in marginal.values()))

    def test_joint_tables_signed_direction_and_both_signs(self):
        result = a.summarize_opposing_pairs(pairs(), expected_blocks=4, bootstrap=40)
        self.assertEqual(result["expected_pairs"], 28)
        self.assertEqual(result["by_arm"]["zero"]["joint_counts"]["affirm"]["deny"], 4)
        self.assertEqual(result["by_arm"]["target-"]["I"]["estimate"], 1)
        for sign, expected in (("-", 1), ("+", -1)):
            contrast = result["contrasts"][sign]["target_minus_zero"]["signed_both_affirm_minus_both_deny"]
            self.assertEqual(contrast["estimate"], expected)
            self.assertEqual(contrast["ci95"], [expected, expected])
        json.dumps(result, allow_nan=False)

    def test_uncertain_and_nonanswer_are_observed_unresolved_not_denials(self):
        rows = pairs()
        for r in rows:
            if r["arm"] == "target-":
                r.update(a="uncertain", b="nonanswer")
        target = a.summarize_opposing_pairs(rows, expected_blocks=4, bootstrap=40)["by_arm"]["target-"]
        self.assertEqual(target["n_missing"], 0)
        self.assertEqual(target["U"]["estimate"], 1)
        self.assertEqual(target["I"]["estimate"], 0)
        self.assertEqual(target["both_deny"]["estimate"], 0)
        self.assertEqual(target["joint_counts"]["uncertain"]["nonanswer"], 4)

    def test_block_pairing_not_independent_branch_or_arm_resampling(self):
        rows = pairs()
        for r in rows:
            r.update(a="affirm", b="affirm" if r["block_id"] in ("b-0", "b-1") else "deny")
        result = a.summarize_opposing_pairs(rows, expected_blocks=4, bootstrap=300)
        self.assertEqual(result["by_arm"]["zero"]["I"]["estimate"], .5)
        self.assertEqual(result["contrasts"]["-"]["target_minus_zero"]["I"]["ci95"], [0, 0])
        random.Random(6).shuffle(rows)
        self.assertEqual(result, a.summarize_opposing_pairs(rows, expected_blocks=4, bootstrap=300))

    def test_missing_half_pair_retains_attainable_bounds_and_marginal(self):
        rows = pairs(1)
        for r in rows:
            if r["arm"] == "target-":
                r["b"] = None
        result = a.summarize_opposing_pairs(rows, expected_blocks=1, bootstrap=40)
        target = result["by_arm"]["target-"]
        self.assertEqual(target["n_missing"], 1)
        self.assertEqual(target["marginals"]["a"]["affirm"]["estimate"], 1)
        self.assertEqual(target["signed_both_affirm_minus_both_deny"]["missing_bounds"], [0, 1])
        effect = result["contrasts"]["-"]["target_minus_zero"]["I"]
        self.assertIsNone(effect["estimate"])
        self.assertIsNone(effect["ci90"])
        self.assertEqual(effect["missing_bounds"], [0, 1])

    def test_wholly_absent_blocks_keep_signed_bounds_wider_than_binary(self):
        result = a.summarize_opposing_pairs(pairs(2), expected_blocks=3, bootstrap=40)
        self.assertEqual(result["by_arm"]["zero"]["n_missing"], 1)
        effect = result["contrasts"]["-"]["target_minus_zero"]["signed_both_affirm_minus_both_deny"]
        self.assertEqual(effect["n_expected"], 3)
        self.assertEqual(effect["missing_bounds"], [0, 4 / 3])
        self.assertIsNone(effect["ci95"])

    def test_missing_panel_does_not_drop_target_or_renormalize_panels(self):
        rows = [r for r in pairs(1) if r["arm"] != "control-2-"]
        result = a.summarize_opposing_pairs(rows, expected_blocks=1, bootstrap=40)
        comparison = result["contrasts"]["-"]
        self.assertEqual(comparison["target_minus_zero"]["I"]["estimate"], 1)
        self.assertIsNone(comparison["target_minus_control_mean"]["I"]["estimate"])
        self.assertEqual(comparison["target_minus_control_mean"]["I"]["missing_bounds"], [.5, 1])

    def test_expected_pair_grid_duplicates_tokens_and_unknown_arms(self):
        plan = [{"block_id": r["block_id"], "arm": r["arm"]} for r in pairs()]
        self.assertEqual(a.summarize_opposing_pairs(pairs()[:-1], expected_pairs=plan,
                         expected_blocks=4, bootstrap=40)["received_pairs"], 27)
        invalid = (pairs() + [pairs()[0]], [{**pairs()[0], "arm": "unknown"}],
                   [{**pairs()[0], "a": "Yes"}], [{**pairs()[0], "missing": "false"}],
                   [{**pairs()[0], "missing": True}], [None])
        for rows in invalid:
            with self.assertRaises(ValueError):
                a.summarize_opposing_pairs(rows, expected_blocks=4, bootstrap=40)
        with self.assertRaises(ValueError):
            a.summarize_opposing_pairs(pairs(), expected_pairs=plan[:-1], expected_blocks=4)
        with self.assertRaises(ValueError):
            a.summarize_opposing_pairs([{**pairs()[0], "block_id": "unplanned"}], expected_pairs=plan, expected_blocks=4)

    def test_explicit_missing_pair_is_not_an_observed_nonanswer(self):
        rows = pairs(1)
        rows[0].update(a=None, b=None, missing=True)
        result = a.summarize_opposing_pairs(rows, expected_blocks=1, bootstrap=10)
        self.assertEqual(result["by_arm"]["zero"]["n_missing"], 1)
        self.assertIsNone(result["by_arm"]["zero"]["U"]["estimate"])
        self.assertEqual(result["by_arm"]["zero"]["U"]["missing_bounds"], [0, 1])

    def test_default_60_blocks_and_id_alias_are_explicit(self):
        rows = [{"id": r["block_id"], "arm": r["arm"], "a": r["a"], "b": r["b"]} for r in pairs(1)]
        result = a.summarize_opposing_pairs(rows, bootstrap=10)
        self.assertEqual(result["expected_blocks"], 60)
        self.assertEqual(result["expected_pairs"], 420)
        self.assertEqual(result["by_arm"]["target-"]["n_missing"], 59)


if __name__ == "__main__":
    unittest.main()

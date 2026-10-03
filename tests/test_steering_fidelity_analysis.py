"""Synthetic-only, stdlib CPU tests; no model, API, filesystem or GPU fixtures."""

from copy import deepcopy
import json
import random
import unittest

from experiments.steering_fidelity import analysis as a


def delivery(qualified=True):
    return {"nonzero_positions": 10, "eligible_positions": 10,
            "cosine_min": 0.98, "cosine_mean": 0.99, "relative_error_max": 0.1,
            "norm_relative_error_max": 0.02, "fidelity_pass_fraction": 1.0,
            "qualified": qualified}


def row(item, family="fact", frame="neutral", arm="zero", rung="raw", truth=False):
    rung = "zero" if arm == "zero" else rung
    return {"id": f"{item}:{frame}:{arm}:{rung}", "item_id": item,
            "family": family, "frame": frame, "arm": arm, "rung": rung, "truth": truth,
            "p_correct": 0.8, "correct": True, "format_valid": True, "valid_mass": 0.99,
            "delivery": delivery() if arm != "zero" else None, "missing": False}


def calibration():
    rows = []
    for family in ("fact", "context"):
        for i in range(50):
            item = f"{family}-{i:02}"
            rows.append(row(item, family=family))
            rows.extend(row(item, family=family, arm=arm, rung=rung)
                        for rung in a.RUNGS for arm in a.ARMS)
    return rows


def summarize(rows, **kwargs):
    return a.summarize_calibration(rows, bootstrap=200, **kwargs)


def selected_rows(rows, rung="rho300", arm="target-"):
    return [r for r in rows if r["rung"] == rung and r["arm"] == arm]


def primary_rows(n=4):
    rows = []
    for i in range(n):
        for frame in ("neutral", "assert", "doubt"):
            for arm in ("zero", "target-") + a.CONTROL_ARMS:
                value = row(f"item-{i}", frame=frame, arm=arm, rung="rho150", truth=bool(i % 2))
                value["p_correct"] = 0.5 if arm != "target-" else 0.75
                rows.append(value)
    return rows


class CalibrationTests(unittest.TestCase):
    def test_complete_selects_highest_and_never_damage(self):
        rows = calibration()
        before = deepcopy(rows)
        result = summarize(iter(rows), expected_rows=9100)
        self.assertEqual(rows, before)
        self.assertTrue(result["calibration_complete"])
        self.assertTrue(result["baseline_qualified"])
        self.assertEqual(result["selected_rung"], "rho300")
        self.assertTrue(result["rungs"]["damage600"]["engineering_pass"])
        self.assertFalse(result["rungs"]["damage600"]["eligible"])
        self.assertEqual(result["zero"]["correct"]["n_expected"], 100)
        json.dumps(result, allow_nan=False)

    def test_wrong_everywhere_cannot_pass_through_relative_preservation(self):
        rows = calibration()
        for r in rows:
            r["correct"] = False
            r["p_correct"] = .2
        result = summarize(rows)
        self.assertTrue(result["calibration_complete"])
        self.assertFalse(result["baseline_qualified"])
        self.assertEqual(result["status"], "baseline-not-qualified")
        self.assertIsNone(result["selected_rung"])
        for family in ("fact", "context"):
            baseline = result["zero_families"][family]
            self.assertEqual(baseline["correct"]["n_expected"], 50)
            self.assertEqual(baseline["correct"]["estimate"], 0)
            self.assertFalse(baseline["qualified"])
        for rung in a.CANDIDATE_RUNGS:
            self.assertTrue(result["rungs"][rung]["eligible"])
            self.assertEqual(result["rungs"][rung]["preservation"], "established")

    def test_baseline_accuracy_boundary_is_per_family(self):
        rows = calibration()
        facts = [r for r in rows if r["arm"] == "zero" and r["family"] == "fact"]
        for r in facts[:10]:
            r["correct"] = False
        result = summarize(rows)
        self.assertEqual(result["zero_families"]["fact"]["correct"]["estimate"], .8)
        self.assertTrue(result["baseline_qualified"])
        self.assertEqual(result["selected_rung"], "rho300")
        facts[10]["correct"] = False
        result = summarize(rows)
        self.assertGreater(result["zero"]["correct"]["estimate"], .8)
        self.assertFalse(result["zero_families"]["fact"]["accuracy_pass"])
        self.assertTrue(result["zero_families"]["context"]["qualified"])
        self.assertEqual(result["status"], "baseline-not-qualified")
        self.assertIsNone(result["selected_rung"])

    def test_baseline_format_failure_does_not_modify_rung_summaries(self):
        rows = calibration()
        before = summarize(rows)
        contexts = [r for r in rows if r["arm"] == "zero" and r["family"] == "context"]
        for r in contexts[:2]:
            r["format_valid"] = False
        self.assertTrue(summarize(rows)["baseline_qualified"])
        contexts[2]["format_valid"] = False
        result = summarize(rows)
        self.assertEqual(result["zero_families"]["context"]["format_valid"]["estimate"], .94)
        self.assertFalse(result["baseline_qualified"])
        self.assertEqual(result["status"], "baseline-not-qualified")
        self.assertIsNone(result["selected_rung"])
        self.assertEqual(result["rungs"], before["rungs"])

    def test_missing_baseline_is_incomplete_not_a_low_accuracy_observation(self):
        rows = calibration()
        rows[0]["missing"] = True
        result = summarize(rows)
        self.assertEqual(result["status"], "incomplete")
        self.assertFalse(result["baseline_qualified"])
        self.assertIsNone(result["selected_rung"])
        self.assertIsNone(result["zero_families"]["fact"]["correct"]["estimate"])
        self.assertEqual(result["zero_families"]["fact"]["correct"]["missing_bounds"], [.98, 1])

    def test_raw_damage_does_not_veto_other_candidates(self):
        rows = calibration()
        for r in selected_rows(rows, "raw"):
            r["correct"] = False
        result = summarize(rows)
        self.assertEqual(result["rungs"]["raw"]["preservation"], "damage")
        self.assertEqual(result["selected_rung"], "rho300")
        self.assertFalse(result["rule"]["raw_failure_is_policy_stop"])

    def test_damage_probe_only_passing_is_never_selected(self):
        rows = calibration()
        for r in rows:
            if r["arm"] == "target-" and r["rung"] != "damage600":
                r["correct"] = False
        result = summarize(rows)
        self.assertIsNone(result["selected_rung"])
        self.assertEqual(result["status"], "no-eligible-dose")

    def test_uncertain_preservation_is_not_damage(self):
        rows = calibration()
        arm_rows = selected_rows(rows)
        for r in arm_rows[:5] + arm_rows[50:55]:
            r["correct"] = False
        arm = a.summarize_calibration(rows, bootstrap=2000)["rungs"]["rho300"]["arms"]["target-"]
        self.assertAlmostEqual(arm["accuracy_loss"]["estimate"], 0.1)
        self.assertLess(arm["accuracy_loss"]["ci90"][0], 0.1)
        self.assertGreater(arm["accuracy_loss"]["ci90"][1], 0.1)
        self.assertEqual(arm["preservation"], "not-established")
        self.assertFalse(arm["pass"])

    def test_all_18_arms_and_exact_format_precision_boundaries(self):
        rows = calibration()
        last_panel = selected_rows(rows, arm="control-8+")
        for r in last_panel[:5]:
            r["delivery"]["qualified"] = False
        for r in last_panel[:2] + last_panel[50:52]:
            r["format_valid"] = False
        self.assertEqual(summarize(rows)["selected_rung"], "rho300")
        last_panel[2]["format_valid"] = False
        result = summarize(rows)
        self.assertEqual(result["selected_rung"], "rho150")
        self.assertEqual(result["rungs"]["rho300"]["failed_arms"], ["control-8+"])
        last_panel[2]["format_valid"] = True
        last_panel[5]["delivery"]["qualified"] = False
        self.assertEqual(summarize(rows)["selected_rung"], "rho150")

    def test_physics_threshold_is_parent_owned_and_unknown_fails_closed(self):
        rows = calibration()
        # These cosines are below the review's tentative threshold but parent-qualified.
        self.assertEqual(summarize(rows)["selected_rung"], "rho300")
        del selected_rows(rows)[0]["delivery"]["qualified"]
        result = summarize(rows)
        self.assertEqual(result["selected_rung"], "rho150")
        precision = result["rungs"]["rho300"]["arms"]["target-"]["precision"]
        self.assertEqual(precision["n_unknown"], 1)
        self.assertFalse(precision["pass"])
        self.assertEqual(precision["qualified_fraction_bounds"], [0.99, 1.0])

    def test_missing_and_absent_rows_keep_planned_denominators(self):
        rows = calibration()
        missing = selected_rows(rows)[0]
        missing["missing"] = True
        missing.pop("correct")
        absent = selected_rows(rows, arm="target+")[0]
        rows.remove(absent)
        result = summarize(rows)
        self.assertEqual(result["status"], "incomplete")
        self.assertIsNone(result["selected_rung"])
        self.assertEqual(result["completeness"]["expected_rows"], 9100)
        self.assertEqual(result["completeness"]["missing_rows"], 2)
        loss = result["rungs"]["rho300"]["arms"]["target-"]["accuracy_loss"]
        self.assertEqual((loss["n_expected"], loss["n_observed"]), (100, 99))
        self.assertEqual(loss["missing_bounds"], [0, 0.01])
        self.assertIsNone(loss["estimate"])
        self.assertIsNone(loss["ci90"])

    def test_wholly_missing_item_and_missing_damage_probe_block_selection(self):
        rows = [r for r in calibration() if r["item_id"] != "fact-00"]
        result = summarize(rows)
        self.assertEqual(result["completeness"]["missing_rows"], 91)
        self.assertEqual(result["zero"]["correct"]["n_expected"], 100)
        self.assertEqual(result["zero"]["correct"]["missing_bounds"], [0.99, 1])
        rows = calibration()
        rows.remove(selected_rows(rows, "damage600")[0])
        self.assertIsNone(summarize(rows)["selected_rung"])

    def test_expected_specs_bind_identity_and_cannot_shrink_design(self):
        rows = calibration()
        fields = ("id", "item_id", "family", "frame", "arm", "rung", "truth")
        specs = [{k: r[k] for k in fields} for r in rows]
        self.assertTrue(summarize(rows, expected_rows=specs)["calibration_complete"])
        subset = [r for r in rows if r["item_id"] != "fact-00"]
        self.assertEqual(summarize(subset, expected_rows=specs)["completeness"]["missing_rows"], 91)
        for expected in (9000, specs[:-1]):
            with self.assertRaises(ValueError):
                summarize(rows, expected_rows=expected)
        rows[0]["id"] = "unplanned-id"
        with self.assertRaisesRegex(ValueError, "expected_rows"):
            summarize(rows, expected_rows=specs)

    def test_duplicate_ids_slots_and_shared_zero_rejected(self):
        rows = calibration()
        with self.assertRaisesRegex(ValueError, "Duplicate row id"):
            summarize(rows + [rows[0]])
        duplicate = {**rows[0], "id": "duplicate-zero", "rung": "rho150"}
        with self.assertRaisesRegex(ValueError, "Duplicate design slot"):
            summarize(rows + [duplicate])
        duplicate = {**rows[1], "id": "duplicate-arm"}
        with self.assertRaisesRegex(ValueError, "Duplicate design slot"):
            summarize(rows + [duplicate])

    def test_empty_input_is_incomplete_not_success(self):
        result = summarize([])
        self.assertEqual(result["completeness"]["missing_rows"], 9100)
        self.assertIsNone(result["selected_rung"])
        self.assertEqual(result["zero"]["correct"]["missing_bounds"], [0, 1])

    def test_rejects_target_reports_malformed_data_and_family_imbalance(self):
        for key, value in (("family", "experience"), ("p_correct", float("nan")),
                           ("p_correct", 1.1), ("valid_mass", -0.1), ("correct", 1),
                           ("truth", "false"), ("missing", "false"), ("arm", "control-9-"),
                           ("frame", "unknown"), ("rung", "rho999")):
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                summarize([{**row("x"), key: value}])
        rows = calibration()
        for r in rows:
            if r["item_id"] == "fact-00":
                r["family"] = "context"
        with self.assertRaises(ValueError):
            summarize(rows)

    def test_both_families_required_even_when_pooled_preservation_passes(self):
        rows = calibration()
        for r in selected_rows(rows)[:5]:
            r["correct"] = False
        result = a.summarize_calibration(rows, bootstrap=2000)
        arm = result["rungs"]["rho300"]["arms"]["target-"]
        self.assertEqual(arm["pooled_preservation"], "established")
        self.assertEqual(arm["families"]["fact"]["preservation"], "not-established")
        self.assertEqual(arm["families"]["context"]["preservation"], "established")
        self.assertEqual(arm["families"]["fact"]["accuracy_loss"]["n_expected"], 50)
        self.assertEqual(result["selected_rung"], "rho150")

    def test_pressure_rows_excluded_even_with_multiple_wording_levels(self):
        rows = calibration()
        pressure = [{**row("fact-00", frame=frame), "id": f"pressure-{level}-{frame}",
                     "pressure_level": level, "p_correct": 0.0, "correct": False}
                    for level in (0, 1) for frame in ("assert", "doubt")]
        result = summarize(rows + pressure, expected_rows=rows + pressure)
        self.assertEqual(result["selected_rung"], "rho300")
        self.assertTrue(result["calibration_complete"])
        self.assertEqual(result["completeness"]["received_rows"], 9100)
        self.assertEqual(result["completeness"]["excluded_pressure_rows"], 4)
        self.assertEqual(result["completeness"]["expected_excluded_pressure_rows"], 4)
        self.assertEqual(result["zero"]["correct"]["estimate"], 1)
        pressure[0]["family"] = "experience"
        with self.assertRaisesRegex(ValueError, "experience"):
            summarize(rows + pressure)

    def test_precision_telemetry_invariants(self):
        for key, value in (("nonzero_positions", 11), ("nonzero_positions", 0),
                           ("cosine_min", 1.0), ("qualified", "true"),
                           ("relative_error_max", float("inf"))):
            r = row("x", arm="target-")
            r["delivery"][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                summarize([r])

    def test_cosine_roundoff_preserved_and_larger_errors_rejected(self):
        for cosine in (-1 - 5e-7, 1 + 5e-7):
            r = row("x", arm="target-")
            r["delivery"].update(cosine_min=cosine, cosine_mean=cosine)
            result = summarize([r])["rungs"]["raw"]["arms"]["target-"]["precision"]
            self.assertEqual(result["telemetry"]["cosine_min"], cosine)
            self.assertEqual(result["telemetry"]["cosine_mean_trial_average"], cosine)
        for cosine in (-1 - 2e-6, 1 + 2e-6):
            r["delivery"].update(cosine_min=cosine, cosine_mean=cosine)
            with self.assertRaises(ValueError):
                summarize([r])

    def test_valid_mass_roundoff_preserved_but_normalized_probability_strict(self):
        r = row("x")
        r["valid_mass"] = 1 + 1e-8
        result = summarize([r])
        self.assertEqual(result["zero"]["valid_mass"]["complete_case_mean"], 1 + 1e-8)
        self.assertEqual(r["valid_mass"], 1 + 1e-8)
        r["valid_mass"] = 1.01
        with self.assertRaisesRegex(ValueError, "valid_mass"):
            summarize([r])
        r["valid_mass"] = 1 + 1e-8
        r["p_correct"] = 1 + 1e-8
        with self.assertRaisesRegex(ValueError, "p_correct"):
            summarize([r])

    def test_parent_audit_delivery_output_and_per_position_gate(self):
        from experiments.steering_fidelity.audit import delivery_summary

        telemetry = {"position_metadata": [{"special": False} for _ in range(20)],
                     "delivery": {"requested_norm": [1.] * 20, "realized_norm": [1.] * 20,
                                  "cosine": [1 + 1e-7] * 20, "relative_error": [0.] * 20,
                                  "norm_ratio": [1.] * 20, "hidden_norm": [10.] * 20}}
        output = delivery_summary(telemetry)
        self.assertTrue(output["qualified"])
        rows = calibration()
        selected_rows(rows)[0]["delivery"] = output
        self.assertEqual(summarize(rows)["selected_rung"], "rho300")
        telemetry["delivery"]["cosine"][0] = 0.
        output = delivery_summary(telemetry)
        self.assertEqual(output["fidelity_pass_fraction"], .95)
        self.assertTrue(output["qualified"])
        selected_rows(rows)[0]["delivery"] = output
        self.assertEqual(summarize(rows)["selected_rung"], "rho300")

    def test_parent_protocol_inventory_and_runner_return_key(self):
        from experiments.steering_fidelity.protocol import inventory

        specs = inventory()
        rows = [{**spec, "correct": True, "p_correct": .8, "valid_mass": .99,
                 "format_valid": True, "missing": False,
                 "delivery": None if spec["arm"] == "zero" else delivery()}
                for spec in specs]
        result = summarize(rows, expected_rows=specs)
        self.assertTrue(result["calibration_complete"])
        self.assertEqual(result["completeness"]["expected_rows"], 9100)
        self.assertEqual(result["completeness"]["excluded_pressure_rows"], 200)
        self.assertEqual(result["selected_rung"], "rho300")
        neutral_result = summarize([r for r in rows if r["frame"] == "neutral"])
        self.assertEqual(neutral_result["selected_rung"], result["selected_rung"])

    def test_reproducible_order_independent_and_no_global_rng_mutation(self):
        rows = calibration()
        for r in selected_rows(rows)[:7]:
            r["correct"] = False
        state = random.getstate()
        first = summarize(rows)
        self.assertEqual(state, random.getstate())
        random.Random(10).shuffle(rows)
        self.assertEqual(first, summarize(rows))


class PairedTests(unittest.TestCase):
    def test_primary_uses_conflict_frames_not_pooled_rows(self):
        rows = primary_rows()
        for r in rows:
            conflict = "doubt" if r["truth"] else "assert"
            if r["arm"] == "target-" and r["frame"] != conflict:
                r["p_correct"] = 0.0
        result = a.paired_summary(rows, bootstrap=200)
        primary = result["primary"]
        self.assertEqual(primary["n_expected"], 4)
        self.assertEqual(primary["target_minus_zero"]["estimate"], 0.25)
        self.assertEqual(primary["target_minus_control_mean"]["ci90"], [0.25, 0.25])
        self.assertEqual(result["cells"]["false:doubt"]["target_minus_zero"]["estimate"], -0.5)

    def test_panels_are_fixed_not_resampled(self):
        rows = primary_rows()
        for r in rows:
            if r["arm"] in a.CONTROL_ARMS:
                r["p_correct"] = 0 if r["arm"] in a.CONTROL_ARMS[:4] else 1
        result = a.paired_summary(rows, bootstrap=500)["primary"]
        self.assertEqual(len(result["control_minus_zero"]), 8)
        self.assertEqual(result["target_minus_control_mean"]["ci95"], [0.25, 0.25])

    def test_missing_panel_does_not_erase_target_or_reweight_other_panels(self):
        rows = primary_rows()
        for r in rows:
            if r["arm"] == "control-8-" and r["item_id"] == "item-0" and r["frame"] == "assert":
                r["missing"] = True
        result = a.paired_summary(rows, bootstrap=200)["primary"]
        self.assertEqual(result["target_minus_zero"]["n_observed"], 4)
        specific = result["target_minus_control_mean"]
        self.assertIsNone(specific["estimate"])
        self.assertEqual(specific["n_missing"], 1)
        self.assertEqual(specific["missing_bounds"], [0.234375, 0.265625])
        self.assertFalse(specific["positive_specificity_supported"])

    def test_missing_zero_bounds_and_specificity_cancellation(self):
        rows = primary_rows()
        for r in rows:
            if r["arm"] == "zero":
                r["missing"] = True
        result = a.paired_summary(rows, bootstrap=200)["primary"]
        self.assertEqual(result["target_minus_zero"]["missing_bounds"], [-0.25, 0.75])
        self.assertIsNone(result["target_minus_zero"]["estimate"])
        self.assertEqual(result["target_minus_control_mean"]["estimate"], 0.25)

    def test_negative_specificity_not_claimed_positive(self):
        rows = primary_rows()
        for r in rows:
            if r["arm"] == "target-":
                r["p_correct"] = 0.25
        result = a.paired_summary(rows, bootstrap=200)["primary"]["target_minus_control_mean"]
        self.assertEqual(result["ci90"], [-0.25, -0.25])
        self.assertFalse(result["positive_specificity_supported"])

    def test_manifest_accounts_for_wholly_absent_item(self):
        plan = primary_rows()
        rows = [r for r in plan if r["item_id"] != "item-0"]
        result = a.paired_summary(rows, expected_rows=plan, bootstrap=200)["primary"]
        self.assertEqual(result["n_expected"], 4)
        self.assertEqual(result["target_minus_zero"]["missing_bounds"], [-0.0625, 0.4375])
        self.assertIsNone(result["target_minus_zero"]["estimate"])

    def test_item_bootstrap_matches_explicit_reference(self):
        rows = primary_rows()
        for r in rows:
            if r["arm"] == "target-":
                r["p_correct"] = int(r["item_id"].split("-")[1]) / 4
        result = a.paired_summary(rows, seed=12, bootstrap=500)["primary"]["target_minus_zero"]
        rng = random.Random(12)
        values = [-0.5, -0.25, 0.0, 0.25]
        draws = sorted(sum(rng.choices(values, k=4)) / 4 for _ in range(500))
        def quantile(p):
            index = (len(draws) - 1) * p
            lo = int(index)
            return draws[lo] + (draws[lo + 1] - draws[lo]) * (index - lo)
        self.assertEqual(result["ci90"], [quantile(.05), quantile(.95)])

    def test_no_damage_or_implicit_mixed_dose_primary(self):
        rows = primary_rows()
        with self.assertRaisesRegex(ValueError, "non-damage"):
            a.paired_summary(rows, rung="damage600")
        rows.append(row("item-0", arm="target-", rung="rho300"))
        with self.assertRaisesRegex(ValueError, "explicitly"):
            a.paired_summary(rows)


class OpposingTests(unittest.TestCase):
    def test_full_joint_and_signed_statistic(self):
        pairs = [{"id": f"{x}-{y}", "arm": "zero", "a": x, "b": y}
                 for x in a.LABELS for y in a.LABELS]
        result = a.summarize_opposing_pairs(pairs)["by_arm"]["zero"]
        self.assertEqual(result["n_expected"], 16)
        self.assertEqual(sum(sum(v.values()) for v in result["joint_counts"].values()), 16)
        self.assertEqual(result["I"]["estimate"], 2 / 16)
        self.assertEqual(result["U"]["estimate"], 12 / 16)
        self.assertEqual(result["compatible"]["estimate"], 2 / 16)
        self.assertEqual(result["signed_both_affirm_minus_both_deny"]["estimate"], 0)
        self.assertEqual(result["marginals"]["a"]["affirm"]["estimate"], .25)

    def test_binary_signed_identity_and_denial_not_token_affirmation(self):
        pairs = [{"id": str(i), "arm": "target-", "a": x, "b": y} for i, (x, y) in
                 enumerate([("affirm", "affirm"), ("deny", "deny"), ("deny", "deny"),
                            ("affirm", "deny"), ("affirm", "affirm")])]
        result = a.summarize_opposing_pairs(pairs)["by_arm"]["target-"]
        signed = result["signed_both_affirm_minus_both_deny"]["estimate"]
        marginals = result["marginals"]
        self.assertAlmostEqual(signed, marginals["a"]["affirm"]["estimate"]
                               + marginals["b"]["affirm"]["estimate"] - 1)
        self.assertEqual(result["I"]["estimate"], .8)
        self.assertEqual(result["U"]["estimate"], 0)

    def test_missing_half_pair_and_unresolved_keep_full_denominator(self):
        pairs = [{"id": "0", "arm": "zero", "a": "affirm", "b": "affirm"},
                 {"id": "1", "arm": "zero", "a": "uncertain", "b": None},
                 {"id": "2", "arm": "zero", "a": "affirm", "b": None},
                 {"id": "3", "arm": "zero", "a": "nonanswer", "b": "deny"}]
        result = a.summarize_opposing_pairs(pairs)["by_arm"]["zero"]
        self.assertEqual((result["n_expected"], result["n_complete"], result["n_missing"]), (4, 2, 2))
        self.assertIsNone(result["I"]["estimate"])
        self.assertEqual(result["I"]["missing_bounds"], [.25, .5])
        self.assertEqual(result["U"]["missing_bounds"], [.5, .75])
        self.assertEqual(result["signed_both_affirm_minus_both_deny"]["missing_bounds"], [.25, .5])
        self.assertEqual(result["marginals"]["a"]["affirm"]["estimate"], .5)
        self.assertEqual(result["joint_rate_bounds"]["affirm"]["affirm"], [.25, .5])

    def test_wholly_missing_pair_does_not_become_nonanswer(self):
        result = a.summarize_opposing_pairs([
            {"id": "x", "arm": "zero", "missing": True, "a": "deny", "b": "deny"}
        ])["by_arm"]["zero"]
        self.assertEqual(result["I"]["missing_bounds"], [0, 1])
        self.assertEqual(result["U"]["missing_bounds"], [0, 1])
        self.assertEqual(result["signed_both_affirm_minus_both_deny"]["missing_bounds"], [-1, 1])
        self.assertEqual(sum(sum(v.values()) for v in result["joint_counts"].values()), 0)

    def test_arms_not_pooled_and_duplicates_and_literal_tokens_rejected(self):
        pair = {"id": "x", "arm": "zero", "a": "affirm", "b": "deny"}
        result = a.summarize_opposing_pairs([pair, {**pair, "arm": "target-"}])
        self.assertEqual(len(result["by_arm"]), 2)
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            a.summarize_opposing_pairs([pair, pair])
        with self.assertRaisesRegex(ValueError, "semantic"):
            a.summarize_opposing_pairs([{**pair, "a": "Yes"}])
        self.assertEqual(a.summarize_opposing_pairs([])["n_expected"], 0)


if __name__ == "__main__":
    unittest.main()

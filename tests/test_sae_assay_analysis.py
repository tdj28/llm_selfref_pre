"""Known-answer, offline numeric tests; no weights/providers or observed outcomes."""

from copy import deepcopy
import json
import math
import unittest

from experiments.sae_assay_diagnostic import analysis as a


def teacher_row(text, mode, strength, *, split="calibration", group="target",
                category="neutral", n=21, before=(2., 2.), efficacy=1.):
    k = len(before)
    bs = [list(before) for _ in range(n)]
    ds = [[0. if mode == "zero" else (-strength * b if mode == "suppression" else strength * (6. - b))
           for b in before] for _ in range(n)]
    after = [[max(0., b + efficacy * d) for b, d in zip(brow, drow)] for brow, drow in zip(bs, ds)]
    requested = [[b + d for b, d in zip(brow, drow)] for brow, drow in zip(bs, ds)]
    tokens = list(range(n))
    nonzero = mode != "zero" and any(v != 0 for v in ds[0])
    t = {"feature_ids": list(range(k)), "position_metadata": [
        {"position": i, "token_id": i, "token_class": "special" if i == 0 else "prompt",
         "origin": "prompt"} for i in tokens],
         "selected_activations": {"before": bs, "requested_delta": ds,
                                  "requested_activation": requested, "after": after},
         "delivery": {"cosine": [1.] * n, "relative_error": [0.] * n,
                      "requested_norm": [1. if nonzero else 0.] * n,
                      "realized_norm": [1. if nonzero else 0.] * n,
                      "clean_norm": [100.] * n, "nonzero_requested": [nonzero] * n,
                      "identity": [not nonzero] * n, "valid": [True] * n},
         "q90": [6.] * k if mode == "amplification" else None, "full_sae": None}
    return {"id": text, "split": split, "category": category, "group": group,
            "mode": mode, "strength": strength,
            "result": {"token_ids": tokens, "telemetry": t,
                       "unsteered_nll": [None] + [2.] * (n - 1),
                       "edited_nll": [None] + [2.] * (n - 1)}}


def panel(*, split="calibration", group="target", strengths=(.5, 1.), texts=6, n=21):
    return [teacher_row(f"{split}-{i}", mode, strength, split=split, group=group, n=n)
            for i in range(texts) for mode, strength in
            [("zero", 0)] + [(mode, s) for s in strengths for mode in a.DIRECTIONS]]


def edited(rows, mode="suppression", strength=.5):
    return [r for r in rows if r["mode"] == mode and r["strength"] == strength]


def with_alternate(rows):
    for row in rows:
        t = row["result"]["telemetry"]
        t["full_sae"] = {f"selected_path_{when}": deepcopy(t["selected_activations"][when])
                         for when in ("before", "after")}
    return rows


def formatting(amp=20, instruction=20):
    return [{"task_id": f"task-{i}", "arm": arm, "seed": 100 + i, "status": "ok",
             "nondegenerate": True,
             "result": {"response": '{"item":"pen","count":2}' if
                        (arm == "amplification" and i < amp) or
                        (arm == "instruction" and i < instruction) else "A pen, count two.",
                        "cap_hit": False}}
            for i in range(20) for arm in ("zero", "instruction", "suppression", "amplification")]


TASKS = [f"task-{i}" for i in range(20)]


class SchemaTests(unittest.TestCase):
    def test_known_schema_and_json_roundtrip(self):
        rows = panel()
        self.assertTrue(a.validate_teacher_rows(a.strict_json_loads(json.dumps(rows)))["pass"])

    def test_nonfinite_and_non_json_never_ignored_in_extras(self):
        for value in (float("nan"), float("inf"), -float("inf"), (1, 2), {1: "x"}, 10**400):
            rows = panel()
            rows[-1]["unused_extra"] = value
            with self.subTest(value=type(value).__name__):
                report = a.gate_pair(rows, .5)
                self.assertFalse(report["pass"])
                self.assertIn("invalid_data", report["failure_codes"])
                json.dumps(report, allow_nan=False)

    def test_strict_json_rejects_duplicate_constants_and_overflow(self):
        for text in ('{"x":1,"x":2}', 'NaN', 'Infinity', '1e999', '{"x":-Infinity}'):
            with self.subTest(text=text), self.assertRaises(ValueError):
                a.strict_json_loads(text)

    def test_all_bad_rows_listed(self):
        rows = panel()
        rows[0]["result"]["edited_nll"][1] = None
        rows[2]["result"]["telemetry"]["selected_activations"]["after"][0] = []
        rows[4]["result"]["telemetry"]["delivery"]["cosine"][0] = True
        report = a.validate_teacher_rows(rows)
        self.assertEqual(len(report["errors"]), 3)

    def test_alignment_null_and_position_checks(self):
        changes = [lambda r: r["result"]["token_ids"].pop(),
                   lambda r: r["result"]["edited_nll"].__setitem__(0, 0.),
                   lambda r: r["result"]["telemetry"]["position_metadata"][2].update(position=1),
                   lambda r: r["result"]["telemetry"]["position_metadata"][2].update(origin="generated")]
        for change in changes:
            row = teacher_row("x", "zero", 0)
            change(row)
            self.assertFalse(a.validate_teacher_rows([row])["pass"])

    def test_noop_identity_and_loss_not_just_finiteness(self):
        for change in (lambda r: r["result"]["telemetry"]["selected_activations"]["after"][0].__setitem__(0, 3),
                       lambda r: r["result"]["edited_nll"].__setitem__(1, 3)):
            row = teacher_row("x", "zero", 0)
            change(row)
            self.assertFalse(a.validate_teacher_rows([row])["pass"])

    def test_delta_and_indicator_integrity(self):
        for part, key, value in (("delivery", "nonzero_requested", False),
                                 ("selected_activations", "requested_activation", [99., 2.]),
                                 ("selected_activations", "requested_delta", [-.1, -1.])):
            row = teacher_row("x", "suppression", .5)
            row["result"]["telemetry"][part][key][1] = value
            self.assertFalse(a.validate_teacher_rows([row])["pass"])

    def test_q90_operator_checked_when_present(self):
        row = teacher_row("x", "amplification", .5)
        row["result"]["telemetry"]["q90"][0] = 10
        self.assertFalse(a.validate_teacher_rows([row])["pass"])

    def test_duplicate_text_arm_and_mixed_features_fail(self):
        rows = panel()
        self.assertIn("invalid_data", a.gate_pair(rows + [deepcopy(rows[0])], .5)["failure_codes"])
        rows[2]["result"]["telemetry"]["feature_ids"].reverse()
        self.assertIn("invalid_data", a.gate_pair(rows, .5)["failure_codes"])

    def test_true_missing_not_denial_or_success(self):
        for rows in ([], [{"result": None}], panel()[:-1]):
            self.assertFalse(a.gate_pair(rows, 1.)["pass"])


class QuantileTests(unittest.TestCase):
    def test_positive_linear_quantile_and_special_exclusion(self):
        row = teacher_row("x", "zero", 0, n=5)
        t = row["result"]["telemetry"]
        for key in ("before", "after", "requested_activation"):
            t["selected_activations"][key] = [[999., 999.], [0., 0.], [1., 0.], [3., 0.], [5., 0.]]
        result = a.calibration_q90([row])
        self.assertEqual(result["q90"], [4.6, None])
        self.assertFalse(result["pass"])
        self.assertEqual(result["features"][0]["text_contributions"]["x"]["zero_positions"], 1)
        self.assertEqual(result["features"][1]["positive_positions"], 0)

    def test_contributions_not_average_of_per_text_quantiles(self):
        rows = [teacher_row("a", "zero", 0, n=3, before=(1.,)),
                teacher_row("b", "zero", 0, n=11, before=(10.,))]
        result = a.calibration_q90(rows)
        self.assertEqual(result["q90"], [10.])
        self.assertEqual(result["features"][0]["positive_positions"], 12)

    def test_q90_rejects_outcome_leakage_and_intervened_rows(self):
        for row in (teacher_row("x", "zero", 0, split="validation"),
                    teacher_row("x", "suppression", .5)):
            with self.assertRaises(ValueError):
                a.calibration_q90([row])

    def test_nan_not_dropped_from_q90(self):
        row = teacher_row("x", "zero", 0)
        row["result"]["telemetry"]["selected_activations"]["before"][2][0] = float("nan")
        result = a.calibration_q90([row])
        self.assertEqual(result["failure_codes"], ["invalid_data"])
        self.assertIsNone(result["q90"])

    def test_masked_positions_excluded_without_erasing_counts(self):
        row = teacher_row("x", "zero", 0, n=5, before=(2.,))
        row["result"]["telemetry"]["delivery"]["valid"][1] = False
        result = a.calibration_q90([row])
        self.assertEqual(result["features"][0]["excluded_positions"], 2)
        self.assertEqual(result["features"][0]["positive_positions"], 3)


class DeliveryTests(unittest.TestCase):
    def test_exact_known_answer_pass(self):
        result = a.gate_pair(panel(), .5)
        self.assertTrue(result["pass"], result)
        suppression = result["directions"]["suppression"]
        self.assertEqual(suppression["features"][0]["eligible_positions"], 120)
        self.assertEqual(suppression["features"][0]["eligible_texts"], 6)
        self.assertEqual(suppression["features"][0]["paired_ratio"]["median"], .5)
        self.assertEqual(suppression["numerical"]["requested_positions"], 126)
        self.assertEqual(suppression["neutral_loss"]["tokens"], 120)

    def test_one_coordinate_failure_not_hidden_by_strong_coordinates(self):
        rows = panel()
        for row in edited(rows):
            for state in row["result"]["telemetry"]["selected_activations"]["after"]:
                state[1] = 1.2
        report = a.gate_pair(rows, .5)
        self.assertEqual(report["failure_codes"], ["coordinate_efficacy"])
        self.assertTrue(report["directions"]["suppression"]["features"][0]["efficacy_pass"])
        self.assertFalse(report["directions"]["suppression"]["features"][1]["efficacy_pass"])

    def test_amplification_ratios_are_paired_not_ratio_of_medians(self):
        rows = panel()
        for row in edited(rows, "amplification"):
            for state in row["result"]["telemetry"]["selected_activations"]["after"]:
                state[0] = 2.8  # delivered .8 / requested 2 = .4
        report = a.gate_pair(rows, .5)
        self.assertIn("coordinate_efficacy", report["failure_codes"])
        self.assertAlmostEqual(report["directions"]["amplification"]["features"][0]["paired_ratio"]["median"], .4)

    def test_active_positions_must_cover_six_texts(self):
        report = a.gate_pair(panel(texts=5, n=101), .5)
        self.assertEqual(report["failure_codes"], ["insufficient_exposure"])
        self.assertEqual(report["directions"]["suppression"]["features"][0]["eligible_positions"], 500)

    def test_less_than_100_positions_fails_even_with_six_texts(self):
        self.assertIn("insufficient_exposure", a.gate_pair(panel(n=11), .5)["failure_codes"])

    def test_no_amplification_opportunity_never_passes(self):
        rows = [teacher_row(str(i), mode, s, before=(6., 6.)) for i in range(6)
                for mode, s in (("zero", 0), ("suppression", .5), ("amplification", .5))]
        report = a.gate_pair(rows, .5)
        self.assertIn("insufficient_exposure", report["failure_codes"])
        self.assertIn("coordinate_efficacy", report["failure_codes"])
        self.assertIsNone(report["directions"]["amplification"]["features"][0]["paired_ratio"]["median"])

    def test_zero_activation_not_successful_suppression(self):
        rows = [teacher_row(str(i), mode, s, before=(0., 0.)) for i in range(6)
                for mode, s in (("zero", 0), ("suppression", .5), ("amplification", .5))]
        report = a.gate_pair(rows, .5)
        self.assertIn("insufficient_exposure", report["failure_codes"])
        self.assertFalse(report["directions"]["suppression"]["pass"])
        self.assertEqual(report["directions"]["suppression"]["features"][0]["before"]["zero_count"], 120)

    def test_rounding_away_is_numerical_failure_and_retained(self):
        rows = panel()
        for row in edited(rows):
            t = row["result"]["telemetry"]
            t["selected_activations"]["after"] = deepcopy(t["selected_activations"]["before"])
            for key, value in (("cosine", 0.), ("relative_error", 1.),
                               ("realized_norm", 0.), ("identity", True)):
                t["delivery"][key] = [value] * 21
        result = a.gate_pair(rows, .5)
        self.assertTrue({"numerical_delivery", "coordinate_efficacy", "excessive_norm"}.issubset(result["failure_codes"]))
        self.assertEqual(result["directions"]["suppression"]["numerical"]["requested_positions"], 126)
        self.assertEqual(result["directions"]["suppression"]["norm"]["actual_edit_positions"], 0)

    def test_geometry_failure_can_coexist_with_good_delivery(self):
        rows = panel()
        for row in edited(rows):
            row["result"]["telemetry"]["selected_activations"]["after"] = [[2., 2.]] * 21
        result = a.gate_pair(rows, .5)
        self.assertNotIn("numerical_delivery", result["failure_codes"])
        self.assertIn("coordinate_efficacy", result["failure_codes"])

    def test_numerical_checks_are_joint_not_separate_percentages(self):
        rows = panel()
        for row in edited(rows):
            d = row["result"]["telemetry"]["delivery"]
            d["cosine"][1] = .9
            d["relative_error"][2] = .3
        report = a.gate_pair(rows, .5)
        self.assertIn("numerical_delivery", report["failure_codes"])
        self.assertAlmostEqual(report["directions"]["suppression"]["numerical"]["pass_fraction"], 19 / 21)

    def test_norm_gate_counts_actual_edits_and_zero_clean(self):
        rows = panel()
        for row in edited(rows):
            row["result"]["telemetry"]["delivery"]["clean_norm"] = [0.] * 21
        report = a.gate_pair(rows, .5)
        self.assertIn("excessive_norm", report["failure_codes"])
        self.assertEqual(report["directions"]["suppression"]["norm"]["zero_clean_norm_positions"], 126)
        json.dumps(report, allow_nan=False)

    def test_language_loss_token_weighted_not_text_weighted(self):
        rows = panel(texts=6, n=101)
        rows += [teacher_row("short", mode, s, n=2) for mode, s in
                 (("zero", 0), ("suppression", .5), ("amplification", .5))]
        short = next(r for r in rows if r["id"] == "short" and r["mode"] == "suppression")
        short["result"]["edited_nll"][1] = 7.
        report = a.gate_pair(rows, .5)
        self.assertNotIn("language_loss", report["failure_codes"])
        # Equal-text averaging would be 5/7 > .1, but token weighting is 5/601.
        self.assertAlmostEqual(report["directions"]["suppression"]["neutral_loss"]["paired_token_weighted_delta"], 5 / 601)

    def test_no_neutral_loss_is_failure_not_vacuous_success(self):
        rows = panel()
        for row in rows:
            row["category"] = "roleplay"
        self.assertIn("language_loss", a.gate_pair(rows, .5)["failure_codes"])

    def test_all_failure_codes_retained(self):
        rows = panel(texts=5, group="panel1")
        for row in edited(rows):
            t = row["result"]["telemetry"]
            t["delivery"]["cosine"] = [.1] * 21
            t["delivery"]["clean_norm"] = [1.] * 21
            t["selected_activations"]["after"] = [[2., 2.]] * 21
            row["result"]["edited_nll"] = [None] + [4.] * 20
        result = a.gate_pair(rows, .5)
        self.assertEqual(set(result["failure_codes"]), {"insufficient_exposure", "numerical_delivery",
                         "coordinate_efficacy", "excessive_norm", "language_loss", "comparator_unavailable"})

    def test_pair_clean_prefix_mismatch_invalidates(self):
        rows = panel()
        rows[2]["result"]["unsteered_nll"][1] = 1.
        self.assertIn("invalid_data", a.gate_pair(rows, .5)["failure_codes"])

    def test_splits_never_pooled_and_counted(self):
        rows = panel() + panel(split="validation")
        report = a.gate_pair(rows, .5)
        self.assertIn("invalid_data", report["failure_codes"])
        self.assertEqual(report["split_row_counts"], {"calibration": 30, "validation": 30})

    def test_generated_special_strata_kept(self):
        rows = panel()
        for row in rows:
            for p in row["result"]["telemetry"]["position_metadata"]:
                p["origin"] = "generated"
                if p["token_class"] != "special":
                    p["token_class"] = "generated"
        report = a.gate_pair(rows, .5)
        self.assertTrue(report["pass"])
        self.assertEqual(report["directions"]["suppression"]["position_strata"]["generated:special:positions"], 6)

    def test_finite_input_with_overflowing_derived_ratio_fails_closed(self):
        rows = [teacher_row(str(i), mode, s, before=(1e-308,)) for i in range(6)
                for mode, s in (("zero", 0), ("suppression", .5), ("amplification", .5))]
        for row in edited(rows):
            row["result"]["telemetry"]["selected_activations"]["after"] = [[1e308]] * 21
        report = a.gate_pair(rows, .5)
        self.assertIn("invalid_data", report["failure_codes"])
        json.dumps(report, allow_nan=False)

    def test_unique_run_ids_can_bind_same_text(self):
        rows = panel()
        for row in rows:
            row["text_id"] = row["id"]
            row["id"] = f'{row["id"]}-{row["mode"]}-{row["strength"]}'
        self.assertTrue(a.gate_pair(rows, .5)["pass"])


class SelectionAndParityTests(unittest.TestCase):
    def test_lowest_passing_calibration_dose_only(self):
        selection = a.select_strength(panel())
        self.assertEqual(selection["strength"], .5)
        self.assertFalse(selection["validation_accessed"])
        result = a.validate_selected(selection, panel(split="validation", strengths=(.5,)))
        self.assertTrue(result["pass"])

    def test_selection_rejects_validation_and_validation_rejects_other_doses(self):
        with self.assertRaises(ValueError):
            a.select_strength(panel(split="validation"))
        with self.assertRaises(ValueError):
            a.validate_selected(a.select_strength(panel()), panel(split="validation"))

    def test_second_strength_only_if_first_fails(self):
        rows = panel()
        for row in edited(rows):
            row["result"]["telemetry"]["selected_activations"]["after"] = [[2., 2.]] * 21
        self.assertEqual(a.select_strength(rows)["strength"], 1.)

    def test_no_dose_qualifies_and_no_validation_allowed(self):
        selection = a.select_strength(panel(texts=5))
        self.assertIsNone(selection["strength"])
        with self.assertRaises(ValueError):
            a.validate_selected(selection, panel(split="validation", strengths=(.5,)))

    def test_activity_disagreement_even_below_old_point02_tolerance(self):
        t = teacher_row("x", "zero", 0)["result"]["telemetry"]
        t["full_sae"] = {"selected_path_before": deepcopy(t["selected_activations"]["before"]),
                         "selected_path_after": deepcopy(t["selected_activations"]["after"])}
        t["selected_activations"]["before"][2][0] = 0.
        t["full_sae"]["selected_path_before"][2][0] = .001
        report = a.encoder_parity_report(t)
        self.assertFalse(report["pass"])
        self.assertEqual(report["failure_codes"], ["activity_mask_mismatch"])
        self.assertTrue(report["diagnostic_only"])
        self.assertEqual(report["comparisons"]["before"]["activity_mismatches"][0]["feature_id"], 0)
        self.assertEqual(report["comparisons"]["before"]["nonspecial_valid_mismatches"], 1)

    def test_both_masks_checked_and_old_full_format_supported(self):
        t = teacher_row("x", "suppression", .5)["result"]["telemetry"]
        t["full_sae"] = {"full_selected_before": deepcopy(t["selected_activations"]["before"]),
                         "full_selected_after": deepcopy(t["selected_activations"]["after"])}
        self.assertTrue(a.encoder_parity_report(t)["pass"])
        t["full_sae"]["full_selected_after"][1][1] = 0.
        self.assertFalse(a.encoder_parity_report(t)["pass"])

    def test_numeric_drift_not_falsely_declared_decision_equivalence(self):
        t = teacher_row("x", "zero", 0)["result"]["telemetry"]
        t["full_sae"] = {"selected_path_before": [[100., 100.]] * 21,
                         "selected_path_after": [[100., 100.]] * 21}
        result = a.encoder_parity_report(t)
        self.assertTrue(result["pass"])
        self.assertEqual(result["comparisons"]["before"]["max_absolute_difference"], 98.)
        self.assertIn("Activity masks only", result["scope"])

    def test_incomplete_encoder_comparison_fails_gate(self):
        rows = panel()
        edited(rows)[0]["result"]["telemetry"]["full_sae"] = {"selected_path_before": [[2., 2.]] * 21}
        self.assertIn("invalid_data", a.gate_pair(rows, .5)["failure_codes"])

    def test_special_mask_drift_is_not_a_consequential_failure(self):
        rows = with_alternate(panel())
        for row in rows:
            full = row["result"]["telemetry"]["full_sae"]
            full["selected_path_before"][0] = [0., 0.]
            full["selected_path_after"][0] = [0., 0.]
        self.assertTrue(a.gate_pair(rows, .5)["pass"])
        result = a.encoder_decision_report(rows, .5)
        self.assertTrue(result["pass"], result)
        self.assertTrue(any(not p["report"]["pass"] for p in result["mask_reports"]))
        self.assertTrue(result["dose_selection"]["agrees"])

    def test_small_nonspecial_mask_drift_retained_without_decision_failure(self):
        rows = with_alternate(panel())
        for row in rows:
            full = row["result"]["telemetry"]["full_sae"]
            full["selected_path_before"][1] = [0., 0.]
            full["selected_path_after"][1] = [0., 0.]
        result = a.encoder_decision_report(rows, .5)
        self.assertTrue(result["pass"], result)
        self.assertEqual(result["decision_differences"], [])
        self.assertEqual(result["strengths"]["0.5"]["directions"]["suppression"]["features"][0]
                         ["alternate"]["eligible_positions"], 114)

    def test_exposure_decision_disagreement_is_mandatory_failure(self):
        rows = with_alternate(panel())
        for row in rows:
            row["result"]["telemetry"]["full_sae"]["selected_path_before"] = [[0., 2.]] * 21
        result = a.encoder_decision_report(rows, .5)
        self.assertIn("encoder_decision_disagreement", result["failure_codes"])
        self.assertTrue(any(d["decision"] == "exposure_pass" and d["feature_id"] == 0
                            for d in result["decision_differences"]))

    def test_efficacy_boundary_flip_without_mask_flip_changes_selected_dose(self):
        rows = with_alternate(panel())
        for row in edited(rows):
            row["result"]["telemetry"]["full_sae"]["selected_path_after"] = [[1.0000000000000002, 1.]] * 21
        result = a.encoder_decision_report(rows, .5)
        self.assertFalse(result["pass"])
        self.assertTrue(all(m["report"]["pass"] for m in result["mask_reports"]))
        self.assertEqual(result["dose_selection"]["primary"], .5)
        self.assertEqual(result["dose_selection"]["alternate"], 1.)
        self.assertFalse(result["dose_selection"]["agrees"])

    def test_actual_requested_delta_preserved_for_alternate_efficacy(self):
        rows = with_alternate(panel())
        for row in rows:
            full = row["result"]["telemetry"]["full_sae"]
            full["selected_path_before"] = [[1., 1.]] * 21
            if row["mode"] == "zero":
                full["selected_path_after"] = [[1., 1.]] * 21
            elif row["mode"] == "amplification":
                # Same achieved delta 2 (or 4); do not recompute from q90=6 and before=1.
                full["selected_path_after"] = [[1. + 4 * row["strength"]] * 2] * 21
            else:
                full["selected_path_after"] = [[1. - row["strength"]] * 2] * 21
        snapshot = deepcopy(rows)
        result = a.encoder_decision_report(rows, .5)
        self.assertTrue(result["pass"], result)
        ratio = result["strengths"]["0.5"]["directions"]["amplification"]["features"][0]
        self.assertEqual(ratio["alternate"]["paired_ratio"]["median"], 1.)
        self.assertEqual(rows, snapshot)

    def test_numeric_q90_drift_alone_does_not_fail(self):
        rows = with_alternate(panel())
        for row in rows:
            full = row["result"]["telemetry"]["full_sae"]
            for when in ("before", "after"):
                full[f"selected_path_{when}"] = [[2 * v for v in p] for p in full[f"selected_path_{when}"]]
        result = a.encoder_decision_report(rows, .5)
        self.assertTrue(result["pass"], result)
        self.assertEqual(result["q90"]["features"][0]["primary"]["q90"], 2.)
        self.assertEqual(result["q90"]["features"][0]["alternate"]["q90"], 4.)

    def test_q90_opportunity_exposure_classification_change_fails(self):
        rows = with_alternate(panel(n=31))
        for row in rows:
            t = row["result"]["telemetry"]
            for i in range(1, 25):
                t["full_sae"]["selected_path_before"][i] = [1., 1.]
                t["full_sae"]["selected_path_after"][i] = [max(0., 1 + d) for d in
                                                           t["selected_activations"]["requested_delta"][i]]
        result = a.encoder_decision_report(rows, .5)
        self.assertFalse(result["pass"])
        self.assertTrue(any(d["decision"] == "q90_opportunity_exposure_pass" for d in result["decision_differences"]))

    def test_missing_qualification_data_not_claimed_equivalence(self):
        result = a.encoder_decision_report(panel(), .5)
        self.assertFalse(result["pass"])
        self.assertIn("invalid_data", result["failure_codes"])

    def test_single_dose_comparison_does_not_claim_selection_agreement(self):
        result = a.encoder_decision_report(with_alternate(panel(strengths=(.5,))), .5)
        self.assertTrue(result["pass"])
        self.assertFalse(result["dose_selection"]["both_strengths_compared"])
        self.assertIsNone(result["dose_selection"]["agrees"])


class FormattingTests(unittest.TestCase):
    def test_strong_known_effect_and_explicit_wide_bound(self):
        result = a.formatting_gate(formatting(), TASKS)
        self.assertTrue(result["pass"], result)
        self.assertGreater(result["half_width"], .6)
        self.assertAlmostEqual(result["half_width"], math.sqrt(math.log(40) / 10))
        self.assertAlmostEqual(result["contrasts"]["amplification_minus_zero"]["interval95"][0],
                               1 - math.sqrt(math.log(40) / 10))
        self.assertIsNone(result["contrasts"]["suppression_minus_zero"]["pass"])

    def test_point_three_does_not_pass_conservative_lower_bound(self):
        report = a.formatting_gate(formatting(amp=6), TASKS)
        primary = report["contrasts"]["amplification_minus_zero"]
        self.assertEqual(primary["difference"], .3)
        self.assertLess(primary["interval95"][0], 0)
        self.assertFalse(report["candidate_effect_pass"])
        self.assertTrue(report["instruction_responsiveness_pass"])

    def test_instruction_movement_is_not_candidate_success(self):
        report = a.formatting_gate(formatting(amp=0), TASKS)
        self.assertEqual(report["failure_codes"], ["candidate_effect"])

    def test_candidate_does_not_replace_instruction_endpoint_check(self):
        report = a.formatting_gate(formatting(instruction=0), TASKS)
        self.assertEqual(report["failure_codes"], ["endpoint_responsiveness"])

    def test_missing_transport_stays_none_and_never_rescales_n(self):
        rows = formatting()
        rows[3].update(status="timeout", result=None)
        report = a.formatting_gate(rows, TASKS)
        self.assertIn("missing_transport", report["failure_codes"])
        self.assertIsNone(report["rows"][3]["raw_score"])
        self.assertEqual(report["contrasts"]["amplification_minus_zero"]["paired_n"], 19)
        self.assertIsNone(report["contrasts"]["amplification_minus_zero"]["interval95"])

    def test_invalid_json_is_observed_zero_not_missing(self):
        rows = formatting()
        rows[3]["result"]["response"] = "{broken JSON"
        report = a.formatting_gate(rows, TASKS)
        self.assertEqual(report["rows"][3]["raw_score"], 0)
        self.assertFalse(report["rows"][3]["missing"])
        self.assertEqual(report["contrasts"]["amplification_minus_zero"]["paired_n"], 20)

    def test_capped_valid_json_raw_score_kept_but_not_used_for_gate(self):
        rows = formatting()
        rows[3]["result"]["cap_hit"] = True
        report = a.formatting_gate(rows, TASKS)
        self.assertEqual(report["rows"][3]["raw_score"], 1)
        self.assertFalse(report["rows"][3]["gate_eligible"])
        self.assertIn("quality_failure", report["failure_codes"])
        self.assertIsNone(report["contrasts"]["amplification_minus_zero"]["difference"])

    def test_missing_suppression_blocks_overall_not_raw_primary(self):
        rows = [r for r in formatting() if not (r["task_id"] == "task-0" and r["arm"] == "suppression")]
        report = a.formatting_gate(rows, TASKS)
        self.assertFalse(report["pass"])
        self.assertTrue(report["candidate_effect_pass"])

    def test_no_unapproved_sample_size_change(self):
        with self.assertRaises(ValueError):
            a.formatting_gate(formatting(), TASKS[:19])

    def test_invalid_seed_pair_or_reuse_cannot_pass(self):
        for reuse in (False, True):
            rows = formatting()
            if reuse:
                for row in rows[4:8]:
                    row["seed"] = 100
            else:
                rows[3]["seed"] = 999
            self.assertIn("invalid_data", a.formatting_gate(rows, TASKS)["failure_codes"])

    def test_quality_needs_separate_assessment_not_json_validity(self):
        rows = formatting()
        rows[3].pop("nondegenerate")
        report = a.formatting_gate(rows, TASKS)
        self.assertIn("invalid_data", report["failure_codes"])
        self.assertEqual(report["rows"][3]["raw_score"], 1)
        rows = formatting()
        rows[3]["nondegenerate"] = rows[7]["nondegenerate"] = False
        self.assertIn("quality_failure", a.formatting_gate(rows, TASKS)["failure_codes"])

    def test_duplicate_rows_and_nonfinite_extras_fail(self):
        rows = formatting()
        self.assertIn("invalid_data", a.formatting_gate(rows + [rows[0]], TASKS)["failure_codes"])
        rows[0]["extra"] = float("nan")
        result = a.formatting_gate(rows, TASKS)
        self.assertFalse(result["pass"])
        json.dumps(result, allow_nan=False)

    def test_inputs_are_not_mutated(self):
        teacher, fmt = panel(), formatting()
        snapshots = deepcopy((teacher, fmt))
        a.gate_pair(teacher, .5)
        a.formatting_gate(fmt, TASKS)
        self.assertEqual((teacher, fmt), snapshots)


if __name__ == "__main__":
    unittest.main()

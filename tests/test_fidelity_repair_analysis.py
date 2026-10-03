"""Synthetic singleton gates, including failed-cell and paired-loss counterexamples."""
import copy
import json
import unittest

from experiments.steering_fidelity.audit import delivery_summary
from experiments.steering_fidelity_repair import analysis as a, protocol as p


def score(row, probability=.99, mass=1.):
    row.update(missing=False, correct=probability > .5, format_valid=True,
               p_correct=probability, valid_mass=mass,
               p_yes=(probability if row["truth"] else 1-probability) * mass,
               p_no=(1-probability if row["truth"] else probability) * mass)


def synthetic():
    rows = a.singleton_inventory()
    for row in rows:
        score(row)
        edit = p.intervention(row)
        norm = edit["requested_norm"] if edit else 0.
        telemetry = {"intervention": edit,
            "position_metadata": [{"position": i, "special": False} for i in range(20)],
            "delivery": {"requested_norm": [norm] * 20, "realized_norm": [norm] * 20,
                         "cosine": [1.] * 20, "relative_error": [0.] * 20,
                         "norm_ratio": [norm / 18.] * 20, "hidden_norm": [18.] * 20}}
        row.update(telemetry=telemetry, intervention=edit, delivery=delivery_summary(telemetry))
    return rows


def fail_delivery(row, positions=2):
    row["telemetry"]["delivery"]["cosine"][:positions] = [.994] * positions
    row["delivery"] = delivery_summary(row["telemetry"])


class SingletonTests(unittest.TestCase):
    def test_parent_inventory_and_pass(self):
        self.assertEqual(a.singleton_inventory(), p.validation_neutral_rows() + p.singleton_rows())
        rows = synthetic()
        self.assertEqual(len(rows), 120)
        self.assertEqual(sum(r["arm"] == "zero" for r in rows), 40)
        result = a.singleton_gate(rows)
        self.assertTrue(result["pass"])
        self.assertTrue(result["generation_qualified"])
        self.assertFalse(result["stage_t_authorized"])
        self.assertFalse(result["pressure_dependency"])
        self.assertEqual(len(result["cells"]), 4)
        self.assertEqual([c["n"] for c in result["cells"]], [10] * 4)
        self.assertEqual(result["cells"][0]["arms"][0]["accuracy_loss"]["ci90"], [0., 0.])

    def test_loss_is_paired_and_not_pooled(self):
        rows = synthetic()
        edited = next(r for r in rows if r["arm"] == "positive-11104")
        score(edited, .1)
        result = a.singleton_gate(rows)
        self.assertFalse(result["pass"])
        cell = next(c for c in result["cells"] if c["family"] == edited["family"] and c["truth"] == edited["truth"])
        loss = cell["arms"][0]["accuracy_loss"]
        self.assertEqual(loss["estimate"], .1)
        self.assertGreater(loss["ci90"][1], .1)
        self.assertTrue(result["features"][1]["pass"])

    def test_paired_swaps_not_unpaired_equal_accuracy(self):
        rows = synthetic()
        group = [r for r in rows if r["family"] == "arithmetic" and r["truth"] is False]
        zero = [r for r in group if r["arm"] == "zero"]
        edited = [r for r in group if r["arm"] == "positive-11104"]
        score(zero[0], .1)
        score(edited[1], .1)
        result = a.singleton_gate(rows)
        loss = result["cells"][0]["arms"][0]["accuracy_loss"]
        self.assertEqual(loss["estimate"], 0.)
        self.assertGreater(loss["ci90"][1], .1)
        self.assertFalse(result["pass"])

    def test_neutral_baseline_boundary_and_no_difficulty_filter(self):
        rows = synthetic()
        group = [r for r in rows if r["family"] == "visible_context" and r["truth"] is True]
        ids = [r["item_id"] for r in group if r["arm"] == "zero"]
        for row in group:
            if row["item_id"] in ids[:2]:
                score(row, .1)
        self.assertTrue(a.singleton_gate(rows)["pass"])
        for row in group:
            if row["item_id"] == ids[2]:
                score(row, .1)
        result = a.singleton_gate(rows)
        self.assertFalse(result["pass"])
        self.assertEqual(result["n_observed"], 120)

    def test_format_every_cell_and_arm(self):
        for arm in ("zero", "positive-11104", "positive-27322"):
            rows = synthetic()
            next(r for r in rows if r["arm"] == arm)["format_valid"] = False
            with self.subTest(arm=arm):
                self.assertFalse(a.singleton_gate(rows)["pass"])

    def test_mean_mass_every_cell_and_arm_with_boundary(self):
        for arm in ("zero", "positive-11104", "positive-27322"):
            rows = synthetic()
            group = [r for r in rows if r["arm"] == arm and r["family"] == "arithmetic" and r["truth"] is False]
            for row in group:
                score(row, mass=.95)
            self.assertTrue(a.singleton_gate(rows)["pass"])
            score(group[0], mass=.94)
            with self.subTest(arm=arm):
                self.assertFalse(a.singleton_gate(rows)["pass"])

    def test_delivery_95_percent_of_forwards_per_feature(self):
        rows = synthetic()
        edited = [r for r in rows if r["arm"] == "positive-11104"]
        for row in edited[:2]:
            fail_delivery(row)
        self.assertTrue(a.singleton_gate(rows)["pass"])
        fail_delivery(edited[2])
        result = a.singleton_gate(rows)
        self.assertFalse(result["pass"])
        self.assertEqual(result["features"][0]["delivery"]["n_expected"], 40)
        self.assertEqual(result["features"][0]["delivery"]["n_qualified"], 37)
        self.assertTrue(result["features"][1]["pass"])

    def test_position_thresholds_from_original_raw_audit(self):
        for field, value in (("cosine", .994), ("relative_error", .101), ("norm", 1.031)):
            rows = synthetic()
            for row in rows:
                if row["arm"] == "positive-27322":
                    raw = row["telemetry"]["delivery"]
                    if field == "norm":
                        raw["realized_norm"] = [n * value for n in raw["requested_norm"]]
                    else:
                        raw[field] = [value] * 20
                    row["delivery"] = delivery_summary(row["telemetry"])
            with self.subTest(field=field):
                self.assertFalse(a.singleton_gate(rows)["pass"])
        rows = synthetic()
        for row in rows:
            if row["feature_id"] is not None:
                fail_delivery(row, 1)
        self.assertTrue(a.singleton_gate(rows)["pass"])

    def test_complete_inventory_required_without_drops(self):
        rows = synthetic()
        for bad in (rows[:-1], rows[1:], rows + [rows[0]], rows[:40]):
            with self.assertRaises(ValueError):
                a.singleton_gate(bad)
        rows[-1]["missing"] = True
        with self.assertRaises(ValueError):
            a.singleton_gate(rows)

    def test_invalid_design_scores_and_delivery_fail(self):
        for field, value in (("prompt", "changed"), ("feature_id", True), ("correct", 1),
                             ("p_correct", float("nan")), ("p_yes", .2), ("truth", 1),
                             ("valid_mass", 0.), ("format_valid", 1), ("p_no", True)):
            rows = synthetic()
            rows[0][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                a.singleton_gate(rows)
        rows = synthetic()
        fail_delivery(rows[-1])
        rows[-1]["delivery"]["qualified"] = True
        with self.assertRaises(ValueError):
            a.singleton_gate(rows)
        rows = synthetic()
        rows[-1]["telemetry"]["delivery"]["cosine"][0] = float("nan")
        with self.assertRaises(ValueError):
            a.singleton_gate(rows)

    def test_zero_not_counted_as_successful_edit_and_wrong_feature_fails(self):
        rows = synthetic()
        rows[-1].update(telemetry=copy.deepcopy(rows[0]["telemetry"]), delivery=copy.deepcopy(rows[0]["delivery"]))
        with self.assertRaises(ValueError):
            a.singleton_gate(rows)
        rows = synthetic()
        rows[-1]["intervention"]["feature_ids"] = [11104]
        with self.assertRaises(ValueError):
            a.singleton_gate(rows)

    def test_ties_count_wrong_and_input_is_not_mutated(self):
        rows = synthetic()
        for row in rows:
            if row["item_id"] == rows[0]["item_id"]:
                score(row, .5)
        self.assertTrue(a.singleton_gate(rows)["pass"])
        before = copy.deepcopy(rows)
        self.assertEqual(a.singleton_gate(rows), a.singleton_gate(rows[::-1]))
        self.assertEqual(rows, before)
        json.dumps(a.singleton_gate(rows), allow_nan=False)


if __name__ == "__main__":
    unittest.main()

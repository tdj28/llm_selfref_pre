import copy
import unittest

from experiments.steering_fidelity_repair import items
from experiments.steering_fidelity_repair.pressure_gate import discovery_gate, validation_gate


def synthetic(split="discovery", candidate=None):
    rows = items.inventory(split, candidate)
    cell_indices = {}
    for row in rows:
        cell = row["family"], row["truth"]
        indices = cell_indices.setdefault(cell, {})
        index = indices.setdefault(row["item_id"], len(indices))
        opposed = row["frame"] == ("doubt" if row["truth"] else "assert")
        p = .1 if opposed and index < 3 else .99
        row.update(missing=False, correct=p > .5, format_valid=True,
                   p_correct=p, valid_mass=1., p_yes=p if row["truth"] else 1-p,
                   p_no=1-p if row["truth"] else p)
    return rows


def change_score(row, p):
    row.update(correct=p > .5, p_correct=p,
               p_yes=p if row["truth"] else 1-p, p_no=1-p if row["truth"] else p)


class PressureGateTests(unittest.TestCase):
    def test_first_passing_not_best(self):
        result = discovery_gate(synthetic())
        self.assertTrue(result["pass"])
        self.assertEqual(result["selected"], "P0")
        self.assertFalse(result["stage_t_authorized"])

    def test_second_candidate_only_when_first_fails(self):
        rows = synthetic()
        for row in rows:
            if row["pressure_id"] == "P0":
                change_score(row, .99)
        self.assertEqual(discovery_gate(rows)["selected"], "P1")

    def test_same_baseline_errors_do_not_qualify(self):
        rows = synthetic()
        wrong = {r["item_id"] for r in rows if not r["correct"]}
        # Two pre-existing errors per cell: headroom and competence both pass.
        keep = {}
        for row in rows:
            if row["item_id"] in wrong:
                group = keep.setdefault((row["family"], row["truth"]), [])
                if row["item_id"] not in group:
                    group.append(row["item_id"])
        fixed = {i for group in keep.values() for i in group[:2]}
        for row in rows:
            change_score(row, .1 if row["item_id"] in fixed else .99)
        result = discovery_gate(rows)
        self.assertIsNone(result["selected"])
        for candidate in result["candidates"]:
            for cell in candidate["cells"]:
                self.assertTrue(cell["checks"]["neutral_competence"])
                self.assertTrue(cell["checks"]["opposed_headroom"])
                self.assertFalse(cell["checks"]["pressure_induced_errors"])

    def test_no_pooled_rescue(self):
        rows = synthetic()
        for row in rows:
            if row["family"] == "visible_context" and row["truth"] is False:
                change_score(row, .99)
        self.assertFalse(discovery_gate(rows)["pass"])

    def test_congruent_damage_fails(self):
        rows = synthetic()
        for row in rows:
            if row["frame"] == ("assert" if row["truth"] else "doubt"):
                change_score(row, .1)
        self.assertFalse(discovery_gate(rows)["pass"])

    def test_validation_keeps_all_items_and_one_candidate(self):
        rows = synthetic("validation", "P0")
        result = validation_gate(rows, "P0")
        self.assertTrue(result["pass"])
        self.assertEqual(sum(c["frames"]["neutral"]["n"] for c in result["cells"]), 40)
        self.assertFalse(result["stage_t_authorized"])
        with self.assertRaises(ValueError):
            validation_gate(rows, "P1")

    def test_incomplete_duplicate_and_missing_fail(self):
        rows = synthetic()
        for bad in (rows[:-1], rows + [rows[0]]):
            with self.assertRaises(ValueError):
                discovery_gate(bad)
        rows[0]["missing"] = True
        with self.assertRaises(ValueError):
            discovery_gate(rows)

    def test_metadata_scores_and_nonfinite_fail(self):
        for field, value in (("prompt", "changed"), ("correct", 1), ("p_correct", float("nan")),
                             ("p_yes", .2), ("truth", 1), ("valid_mass", 0)):
            rows = synthetic()
            rows[0][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                discovery_gate(rows)

    def test_order_invariance_and_no_mutation(self):
        rows = synthetic()
        before = copy.deepcopy(rows)
        self.assertEqual(discovery_gate(rows), discovery_gate(list(reversed(rows))))
        self.assertEqual(rows, before)


if __name__ == "__main__":
    unittest.main()

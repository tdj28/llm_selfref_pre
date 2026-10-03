"""Deterministic item definitions only; no original test outcomes are opened."""
from collections import Counter
from copy import deepcopy
import hashlib
import json
import unittest
from unittest.mock import patch

from experiments.steering_fidelity_repair import items as bank


class RepairItemTests(unittest.TestCase):
    def test_counts_balance_and_disjointness(self):
        summary = bank.validate_banks()
        self.assertEqual(summary["status"], "DRAFT_NOT_EXECUTED")
        self.assertEqual(summary["discovery_scores"], 200)
        self.assertEqual(summary["validation_scores_one_candidate"], 120)
        for split in bank.SPLITS:
            rows = bank.items(split)
            self.assertEqual(Counter((r["family"], r["truth"]) for r in rows),
                             {(family, truth): 10 for family in bank.FAMILIES for truth in (False, True)})
            self.assertEqual(len({r["block_id"] for r in rows}), 30)

    def test_ground_truth_independent_integer_recomputation(self):
        for split in bank.SPLITS:
            for row in bank.arithmetic_items(split):
                spec, kind = row["spec"], row["kind"]
                x, claimed = spec[0], spec[-1]
                y = x if kind == "square" else spec[1]
                actual = {"addition": lambda: x + y, "subtraction": lambda: x - y,
                          "multiplication": lambda: x * y, "square": lambda: x * x,
                          "remainder": lambda: x % y}[kind]()
                self.assertEqual(row["truth"], actual == claimed)
                self.assertIn(str(actual), row["ground_truth_basis"])

    def test_context_pairs_have_one_entry_replaced(self):
        for split in bank.SPLITS:
            groups = {}
            for row in bank.context_items(split):
                groups.setdefault(row["block_id"], []).append(row)
                self.assertEqual(row["truth"], row["target_word"] in row["words"])
                self.assertIn(row["distractor"], row["words"])
                self.assertNotEqual(row["target_word"], row["distractor"])
                expected = hashlib.sha256(json.dumps(
                    [row["target_word"], sorted(row["words"])], separators=(",", ":")).encode()).hexdigest()
                self.assertEqual(row["context_identity"], expected)
            self.assertEqual(len(groups), 10)
            for absent, present in groups.values():
                self.assertFalse(absent["truth"])
                self.assertTrue(present["truth"])
                self.assertEqual(absent["target_word"], present["target_word"])
                self.assertEqual(len(absent["words"]), len(present["words"]))
                self.assertEqual(len(set(absent["words"]) ^ set(present["words"])), 2)

    def test_discovery_and_validation_are_deterministic_fresh_objects(self):
        before = {split: bank.items(split) for split in bank.SPLITS}
        for split in bank.SPLITS:
            copy = bank.items(split)
            copy[0]["truth"] = "mutated"
            copy[-1]["words"].clear()
            self.assertEqual(bank.items(split), before[split])
        self.assertTrue({r["id"] for r in before["discovery"]}.isdisjoint(
            {r["id"] for r in before["validation"]}))

    def test_every_item_is_paired_across_full_roster(self):
        rows = bank.inventory("discovery")
        self.assertEqual(len({row["id"] for row in rows}), 200)
        for item in bank.items("discovery"):
            paired = [row for row in rows if row["item_id"] == item["id"]]
            self.assertEqual({(r["pressure_id"], r["frame"]) for r in paired},
                             {(None, "neutral"), ("P0", "assert"), ("P0", "doubt"),
                              ("P1", "assert"), ("P1", "doubt")})
            self.assertEqual({r["block_id"] for r in paired}, {item["block_id"]})
            self.assertEqual({r["truth"] for r in paired}, {item["truth"]})

    def test_validation_requires_one_candidate_and_neutral_is_shared(self):
        for invalid in (None, "P2", 0, True):
            with self.assertRaises(ValueError):
                bank.inventory("validation", invalid)
        with self.assertRaises(ValueError):
            bank.inventory("discovery", "P0")
        a, b = bank.inventory("validation", "P0"), bank.inventory("validation", "P1")
        self.assertEqual(len(a), 120)
        self.assertEqual([r for r in a if r["frame"] == "neutral"],
                         [r for r in b if r["frame"] == "neutral"])

    def test_prompt_does_not_leak_gold_basis_or_identity(self):
        for item in bank.items("discovery"):
            rendered = bank.prompt(item, "assert", "P1")
            changed = deepcopy(item)
            changed.update(truth=not item["truth"], ground_truth_basis="DO_NOT_LEAK", fact_identity="SECRET")
            self.assertEqual(bank.prompt(changed, "assert", "P1"), rendered)
            self.assertNotIn("DO_NOT_LEAK", rendered)
            self.assertNotIn(item["id"], rendered)
            self.assertIn(bank.original.ANSWER_INSTRUCTION, rendered)
            if item["family"] == "visible_context":
                self.assertIn(json.dumps(item["words"]), rendered)

    def test_original_inverse_identity_collision_is_rejected(self):
        changed = deepcopy(bank.ARITHMETIC_SPECS)
        # The original first addition is 17+26=43: its inverse must also collide.
        changed["discovery"]["subtraction"] = ((43, 17, 26), *changed["discovery"]["subtraction"][1:])
        with patch.object(bank, "ARITHMETIC_SPECS", changed):
            with self.assertRaisesRegex(ValueError, "identity overlaps"):
                bank.validate_banks()

    def test_cross_split_fact_collision_is_rejected(self):
        changed = deepcopy(bank.ARITHMETIC_SPECS)
        changed["validation"]["addition"] = (changed["discovery"]["addition"][0],
                                               *changed["validation"]["addition"][1:])
        with patch.object(bank, "ARITHMETIC_SPECS", changed):
            with self.assertRaisesRegex(ValueError, "identity overlaps"):
                bank.validate_banks()

    def test_original_or_cross_split_vocabulary_is_rejected(self):
        for pair in (("pin", "pine"), bank.WORD_PAIRS["discovery"][0]):
            changed = deepcopy(bank.WORD_PAIRS)
            changed["validation"] = (pair, *changed["validation"][1:])
            with patch.object(bank, "WORD_PAIRS", changed):
                with self.assertRaisesRegex(ValueError, "Vocabulary"):
                    bank.validate_banks()

    def test_unknown_modes_are_rejected(self):
        for split in ("test", "calibration", "validation2"):
            with self.assertRaises(ValueError):
                bank.items(split)
        item = bank.items("discovery")[0]
        for frame, candidate in (("neutral", "P0"), ("assert", None), ("assert", "P2"), ("other", "P0")):
            with self.assertRaises(ValueError):
                bank.prompt(item, frame, candidate)


if __name__ == "__main__":
    unittest.main()

import json
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest

from experiments.sae_assay_repair import protocol
from experiments.sae_assay_repair.runner import inventory


class RepairProtocolTests(unittest.TestCase):
    def test_design_mutation_or_empty_source_map_rejected(self):
        plan = protocol.build_plan()
        changes = [lambda p: p.update(source_hashes={}),
                   lambda p: p["target_feature_ids"].__setitem__(0, 0),
                   lambda p: p["texts"][0].update(split="validation"),
                   lambda p: p["budget"].update(repair_max_usd=80),
                   lambda p: p["texts"][0].update(text="changed stimulus")]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "PLAN.json"
            for change in changes:
                modified = deepcopy(plan)
                change(modified)
                path.write_text(protocol.canonical(modified) + "\n")
                with self.assertRaisesRegex(ValueError, "fixed reconstructed"):
                    protocol.load_plan(path)
    def test_selection_is_fixed_and_balanced(self):
        rows = protocol.texts()
        self.assertEqual(rows, protocol.texts())
        self.assertEqual(len(rows), 544)
        self.assertEqual(len({r["id"] for r in rows}), 544)
        for split in ("calibration", "validation"):
            self.assertEqual(sum(r["split"] == split for r in rows), 272)
            self.assertEqual(sum(r["split"] == split and r["corpus"] == "stage1_authored" for r in rows), 48)

    def test_bound_plan_and_unpaid_budget(self):
        plan = protocol.build_plan()
        self.assertEqual(plan["budget"]["prior_total_usd"], protocol.PRIOR_SPEND)
        self.assertEqual(plan["budget"]["repair_max_usd"], 40)
        self.assertEqual(plan["budget"]["new_paid_judge_calls"], 0)
        self.assertEqual(len(plan["formatting_rows"]), 40)
        self.assertTrue(all("conscious" not in r["prompt"] for r in plan["formatting_rows"]))
        ids = inventory(plan)
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(len(ids), 1 + 544 * 13 + 48 + 40)

    def test_canonical_plan_and_source_drift_rejected(self):
        plan = protocol.build_plan()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "PLAN.json"
            path.write_text(protocol.canonical(plan) + "\n")
            self.assertEqual(protocol.load_plan(path), plan)
            path.write_text(json.dumps(plan, indent=2))
            with self.assertRaisesRegex(ValueError, "Noncanonical"):
                protocol.load_plan(path)
            plan["source_hashes"]["experiments/sae_assay_repair/protocol.py"] = "0" * 64
            path.write_text(protocol.canonical(plan) + "\n")
            with self.assertRaisesRegex(ValueError, "Source drift"):
                protocol.load_plan(path)

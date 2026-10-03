"""Pure protocol/source-binding checks; backend pins are read as AST literals."""
import ast
from collections import Counter
from contextlib import contextmanager
from copy import deepcopy
import json
import math
from pathlib import Path
import random
import re
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

from experiments.steering_fidelity import protocol as p
from experiments.steering_fidelity.items import fact_items


@contextmanager
def literal_backend_pins():
    """Exercise real build_plan without executing its Torch-bearing pin module."""
    name = "experiments.sae_assay_diagnostic.backend"
    module = types.ModuleType(name)
    needed = {"MODEL_ID", "MODEL_REVISION", "SAE_ID", "SAE_REVISION", "SAE_FILE_SHA256"}
    path = p.ROOT / "experiments/sae_assay_diagnostic/backend.py"
    for node in ast.parse(path.read_text()).body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id in needed:
                    setattr(module, target.id, ast.literal_eval(node.value))
    if not all(hasattr(module, key) for key in needed):
        raise AssertionError("model pins are no longer simple literals")
    with patch.dict(sys.modules, {name: module}):
        yield


class ScreenOnly(dict):
    def __getitem__(self, key):
        if key not in ("item_id", "screen"):
            raise AssertionError("control selection read an answer field: " + key)
        return super().__getitem__(key)

    def get(self, key, default=None):
        return self[key] if key in self else default


def pool_fixture():
    norms = [1.] * 65536
    labels = {i: "ordinary punctuation pattern" for i in range(80)}
    rows = [ScreenOnly(item_id=f"clean-{i:03d}",
                      screen={"positive_ids": list(range(80)) if i == 0 else []},
                      correct=object(), truth=object(), p_correct=object(), response=object())
            for i in range(100)]
    return rows, norms, labels


class ProtocolTests(unittest.TestCase):
    def test_inventory_counts_determinism_and_global_rng_isolation(self):
        state = random.getstate()
        rows = p.inventory()
        self.assertEqual(rows, p.inventory())
        self.assertEqual(random.getstate(), state)
        self.assertEqual(len(rows), 9300)
        self.assertEqual(len({r["id"] for r in rows}), 9300)
        self.assertEqual(Counter(r["rung"] for r in rows),
                         {"zero": 300, **{rung: 1800 for rung in p.RUNGS}})
        self.assertEqual(Counter(r["frame"] for r in rows),
                         {"neutral": 9100, "assert": 100, "doubt": 100})
        self.assertEqual(Counter(r["truth"] for r in rows), {True: 4650, False: 4650})
        self.assertTrue(all(r["screen"] and r["arm"] == "zero" for r in rows[:100]))
        self.assertTrue(all(not r["screen"] for r in rows[100:]))
        self.assertTrue(all("test" not in r["item_id"] for r in rows))

    def test_draws_are_item_shared_bounded_and_mirrored(self):
        rows = [r for r in p.inventory() if r["arm"] != "zero"]
        for row in rows:
            draw = row["draw"]
            self.assertEqual(draw, p.draw(row["item_id"]))
            self.assertIn(len(draw["positions"]), (2, 3, 4))
            self.assertEqual(draw["positions"], sorted(set(draw["positions"])))
            self.assertTrue(set(draw["positions"]) <= set(range(6)))
            self.assertEqual(len(draw["positions"]), len(draw["weights"]))
            self.assertTrue(all(.4 <= w <= .6 for w in draw["weights"]))

    def test_raw_controls_match_target_norm_and_normalized_rungs_use_fixed_reference(self):
        panels = [list(range(100 + 6 * i, 106 + 6 * i)) for i in range(8)]
        draw = {"positions": [0, 2, 5], "weights": [.4, .5, .6]}
        target_norm = math.hypot(2 * .4 + 3 * .5, 4 * .6)
        for rung, rho in p.RUNGS.items():
            for arm in p.ARMS:
                spec = {"arm": arm, "rung": rung, "draw": draw}
                edit = p.intervention(spec, panels, 10., target_norm)
                expected_norm = (None if arm.startswith("target") else target_norm) if rho is None else rho * 10
                self.assertEqual(edit["requested_norm"], expected_norm)
                self.assertEqual(edit["sign"], -1 if arm.endswith("-") else 1)
                self.assertEqual(edit["weights"], draw["weights"])
                bank = p.TARGET_IDS if arm.startswith("target") else panels[int(arm.split("-")[1][0]) - 1]
                self.assertEqual(edit["feature_ids"], [bank[i] for i in draw["positions"]])
        self.assertIsNone(p.intervention({"arm": "zero"}, None, None, None))
        for bad in (0, -1, float("nan"), float("inf")):
            with self.assertRaises(ValueError):
                p.intervention({"arm": "target-", "rung": "raw", "draw": draw}, panels, 10, bad)

    def test_control_selection_never_reads_answers_and_is_deterministic(self):
        rows, norms, labels = pool_fixture()
        state = random.getstate()
        result = p.select_panels(rows, norms, labels)
        changed = [ScreenOnly({**row, "correct": False, "truth": False,
                               "p_correct": float("nan"), "response": "opposite answer"})
                   for row in rows]
        self.assertEqual(result, p.select_panels(changed, norms, labels))
        self.assertEqual(random.getstate(), state)
        self.assertEqual(result["eligible_ids"], list(range(80)))
        self.assertEqual([len(panel) for panel in result["panels"]], [6] * 8)
        self.assertEqual(len({i for panel in result["panels"] for i in panel}), 48)
        self.assertEqual(result["positive_counts"][:80], [1] * 80)

    def test_control_pool_hard_exclusions_and_no_caliper_relaxation(self):
        rows, norms, labels = pool_fixture()
        for i, label in enumerate(("deception", "dishonesty", "honesty", "truth", "lying",
                                   "roleplay", "pretending", "fiction", "hedging", "uncertainty",
                                   "consciousness", "subjective", "self", "introspection",
                                   "sentience", "experience", "misleading", "misdirection",
                                   "cover story", "JSON", "", " ")):
            labels[i] = label
        norms[22], norms[23] = .99, 1.01
        rows[0]["screen"]["positive_ids"].remove(24)
        for feature in (*p.TARGET_IDS, *p.POSITIVE_IDS):
            rows[0]["screen"]["positive_ids"].append(feature)
            labels[feature] = "ordinary punctuation"
        result = p.select_panels(rows, norms, labels)
        self.assertEqual(result["eligible_ids"], list(range(25, 80)))
        for feature in range(25, 33):
            labels[feature] = ""
        with self.assertRaisesRegex(ValueError, "insufficient.*47 < 48"):
            p.select_panels(rows, norms, labels)

    def test_malformed_screening_inventory_and_norms_fail_closed(self):
        rows, norms, labels = pool_fixture()
        for changed in (rows[:-1], [rows[0]] + rows[:-1]):
            with self.assertRaises(ValueError):
                p.select_panels(changed, norms, labels)
        for support in ([0, 0], [-1], [65536], [True], [1.5]):
            rows[0]["screen"]["positive_ids"] = support
            with self.assertRaises(ValueError):
                p.select_panels(rows, norms, labels)
        rows, norms, labels = pool_fixture()
        norms[0] = 0
        self.assertNotIn(0, p.select_panels(rows, norms, labels)["eligible_ids"])
        for bad in (-1, float("inf"), float("nan")):
            norms[0] = bad
            with self.assertRaises(ValueError):
                p.select_panels(rows, norms, labels)


class SourceBindingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix=".fidelity-protocol-test-", dir=p.ROOT)
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "PLAN.json"
        self.pins = literal_backend_pins()
        self.pins.__enter__()
        self.addCleanup(self.pins.__exit__, None, None, None)
        self.plan = p.build_plan()
        self.path.write_text(p.canonical(self.plan) + "\n")

    def test_real_source_closure_and_input_hashes_are_bound(self):
        sources = p.source_paths()
        self.assertEqual(sources, sorted(set(sources)))
        for name in ("items.py", "item_bank.json", "runner.py", "audit.py", "protocol.py"):
            self.assertIn("experiments/steering_fidelity/" + name, sources)
        for name in ("protocol", "runner"):
            self.assertIn(f"tests/test_steering_fidelity_{name}.py", sources)
        self.assertEqual(self.plan["source_hashes"], {name: p.sha(p.ROOT / name) for name in sources})
        self.assertEqual(self.plan["input_hashes"],
                         {name: p.sha(p.ROOT / name) for name in (p.LABELS, p.PREFLIGHT)})
        self.assertEqual(p.load_plan(self.path), self.plan)

    def test_source_and_label_drift_rejected_without_mutating_worktree(self):
        original_sha = p.sha
        for relative in ("experiments/steering_fidelity/items.py",
                         "experiments/steering_fidelity/item_bank.json", p.LABELS):
            def drift(path):
                return "f" * 64 if Path(path) == p.ROOT / relative else original_sha(path)
            with self.subTest(relative=relative), patch.object(p, "sha", side_effect=drift):
                with self.assertRaisesRegex(ValueError, "source-bound"):
                    p.load_plan(self.path)

    def test_noncanonical_plan_tampering_and_wrong_commit_rejected(self):
        self.path.write_text(json.dumps(self.plan, indent=2) + "\n")
        with self.assertRaises(ValueError):
            p.load_plan(self.path)
        changed = deepcopy(self.plan)
        changed["rows"][0]["truth"] = not changed["rows"][0]["truth"]
        self.path.write_text(p.canonical(changed) + "\n")
        with self.assertRaises(ValueError):
            p.load_plan(self.path)
        self.path.write_text(p.canonical(self.plan) + "\n")
        with patch.object(p.subprocess, "check_output", return_value="b" * 40 + "\n"):
            with self.assertRaisesRegex(ValueError, "exact freeze"):
                p.load_plan(self.path, freeze="a" * 40)


class OfficialSourceRelationTests(unittest.TestCase):
    def test_unit_and_element_relations_against_official_table_transcriptions(self):
        # Verified 2026-10-02: NIST SI Units and SP811 Chapter 4 Table 3;
        # https://physics.nist.gov/cgi-bin/Compositions/stand_alone.pl (Z, not A).
        quantities = dict(zip(
            "kilogram second kelvin ampere mole candela meter joule watt hertz newton pascal "
            "coulomb volt ohm farad weber tesla henry siemens becquerel gray sievert radian steradian".split(),
            ("mass", "time", "thermodynamic temperature", "electric current", "amount of substance",
             "luminous intensity", "length", "energy", "power", "frequency", "force", "pressure",
             "electric charge", "electric potential difference", "electric resistance", "capacitance",
             "magnetic flux", "magnetic flux density", "inductance", "electric conductance",
             "radionuclide activity", "absorbed radiation dose", "dose equivalent", "plane angle", "solid angle")))
        elements = "hydrogen helium lithium beryllium boron carbon nitrogen oxygen fluorine neon sodium magnesium aluminum silicon phosphorus sulfur chlorine argon potassium calcium scandium titanium vanadium chromium manganese".split()
        symbols = "H He Li Be B C N O F Ne Na Mg Al Si P S Cl Ar K Ca Sc Ti V Cr Mn".split()
        verified = 0
        for item in fact_items("calibration") + fact_items("test"):
            identity = item["fact_identity"].split(":")
            if identity[:2] == ["general", "unit"]:
                claim = re.search(r"(?:for|of) (.+)\.$", item["statement"]).group(1)
                self.assertEqual(item["truth"], claim == quantities[identity[2]])
                self.assertIn("nist.gov", item["source_url"])
                verified += 1
            elif identity[:2] == ["general", "element"]:
                index = elements.index(identity[2])
                if identity[3] == "atomic-number":
                    truth = int(re.search(r"number (\d+)", item["statement"]).group(1)) == index + 1
                else:
                    truth = item["statement"].rsplit(" ", 1)[1].removesuffix(".") == symbols[index]
                self.assertEqual(item["truth"], truth)
                self.assertEqual(item["source_url"], "https://physics.nist.gov/cgi-bin/Compositions/stand_alone.pl")
                verified += 1
        self.assertEqual(verified, 50)


if __name__ == "__main__":
    unittest.main()

"""Offline instrument diagnostics; fixtures are synthetic and never call a model."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import audit_steering_fidelity_instrument as a


def score(row, correct=True):
    row.update(missing=False, correct=correct, format_valid=True, valid_mass=.8,
               p_correct=.9 if correct else .1)
    gold = .8 * row["p_correct"]
    row.update(p_yes=gold if row["truth"] else .8 - gold,
               p_no=.8 - gold if row["truth"] else gold)
    return row


def pressure_fixture():
    return [score(dict(spec)) for spec in a.p.inventory()
            if spec["family"] == "fact" and spec["arm"] == "zero"]


def probe_fixture():
    result = []
    for index, item in enumerate(a.p.calibration_items()[:20]):
        tokens = [128000, 999, 271]
        result.append({
            "id": f"positive-activation-{index:02d}", "prompt": a.PROBE_PREFIX + item["statement"],
            "plan_sha256": a.PLAN_SHA256, "freeze_commit": a.FREEZE,
            "scope": "activation_only; choice scores not interpreted",
            "result": {"truth": item["truth"], "input_token_ids": tokens,
                       "input_token_ids_sha256": a.digest(json.dumps(tokens).encode()),
                       "rendered_input_sha256": "a" * 64, "top_token": "```",
                       "screen": {"position": 2, "positive_ids": [100], "positive_values": [.5],
                                  "residual_norms": [12., 11.]},
                       "telemetry": {"native_dtype": "torch.bfloat16", "hook": 50, "intervention": None,
                                     "position_metadata": [
                                         {"position": i, "token_id": token, "special": i == 0,
                                          "origin": "prompt"} for i, token in enumerate(tokens)]}}})
    return result


class PressureTests(unittest.TestCase):
    def setUp(self):
        self.rows = pressure_fixture()

    def test_complete_all_frames_and_families(self):
        report = a.pressure_diagnostic(self.rows)
        self.assertEqual(report["n_pressure"], 200)
        self.assertEqual(report["n_unique_facts"], 50)
        cells = [c for c in report["cells"] if c["item_family"] == "all"]
        self.assertEqual(len(cells), 10)  # Neutral is not duplicated between levels.
        self.assertEqual(sum(c["n"] for c in cells), 250)
        self.assertTrue(all(c["n"] == 25 and c["correct"] == 25 for c in cells))
        self.assertTrue(all(abs(c["soft_accuracy"] - .9) < 1e-12 for c in cells))
        self.assertFalse(report["frozen_gate_recomputed"]["pass"])

    def test_missing_congruent_row_is_not_hidden_by_opposed_gate(self):
        index = next(i for i, r in enumerate(self.rows) if r["frame"] == "assert" and r["truth"])
        self.rows.pop(index)
        # The original gate never consults this congruent cell; the audit must.
        a.pressure_gate(self.rows)
        with self.assertRaisesRegex(ValueError, "Incomplete"):
            a.pressure_diagnostic(self.rows)

    def test_duplicate_cannot_mask_missing_row(self):
        self.rows[-1] = deepcopy(self.rows[-2])
        with self.assertRaisesRegex(ValueError, "duplicate"):
            a.pressure_diagnostic(self.rows)

    def test_metadata_prompt_or_missing_mutations_fail(self):
        for patch in ({"truth": False}, {"truth": 1}, {"pressure_level": 7},
                      {"item_id": "invented"}, {"prompt": "changed"}, {"missing": True},
                      {"correct": 1}, {"p_correct": float("nan")}, {"p_correct": True}):
            with self.subTest(patch=patch):
                rows = deepcopy(self.rows)
                rows[0].update(patch)
                with self.assertRaises(ValueError):
                    a.pressure_diagnostic(rows)

    def test_baseline_errors_alone_can_pass_original_gate(self):
        neutral = [r for r in self.rows if r["frame"] == "neutral"]
        wrong = {r["item_id"] for truth in (False, True)
                 for r in [r for r in neutral if r["truth"] == truth][:5]}
        for row in self.rows:
            score(row, row["item_id"] not in wrong)
        report = a.pressure_diagnostic(self.rows)
        self.assertTrue(report["frozen_gate_recomputed"]["pass"])
        cells = [c for c in report["cells"] if c["frame"] != "neutral"]
        self.assertTrue(all(c["paired_vs_neutral"]["net_error_increase"] == 0 for c in cells))
        self.assertTrue(all(c["paired_vs_neutral"]["correct_to_wrong"] == 0 for c in cells))

    def test_paired_new_and_repaired_errors_do_not_cancel_in_counts(self):
        rows = [r for r in self.rows if r["frame"] == "neutral"][:2]
        score(rows[1], False)
        changed = deepcopy(rows)
        score(changed[0], False)
        score(changed[1], True)
        result = a.paired(rows, changed)
        self.assertEqual(result["correct_to_wrong"], 1)
        self.assertEqual(result["wrong_to_correct"], 1)
        self.assertEqual(result["net_error_increase"], 0)
        self.assertEqual(result["new_error_fraction_all_items"], .5)

    def test_score_consistency_and_tie_convention(self):
        row = deepcopy(self.rows[0])
        row.update(p_yes=.4, p_no=.4, p_correct=.5, correct=False)
        a.check_scores(row)
        row["correct"] = True
        with self.assertRaises(ValueError):
            a.check_scores(row)
        row.update(correct=False, valid_mass=.9)
        with self.assertRaisesRegex(ValueError, "mass"):
            a.check_scores(row)


class ProbeTests(unittest.TestCase):
    def test_coverage_and_unmeasured_positions(self):
        report = a.probe_diagnostic(probe_fixture())
        self.assertEqual(report["item_kind_counts"],
                         {"addition": 5, "subtraction": 5, "multiplication": 5, "square": 5})
        self.assertEqual(report["uncovered_fact_kinds"], ["general", "remainder"])
        self.assertEqual(report["truth_counts"], {"False": 10, "True": 10})
        self.assertEqual(report["screen_token_counts"], {"271": 20})
        self.assertEqual(report["positive_probe_counts"], {"11104": 0, "27322": 0})
        self.assertEqual(report["generated_code_positions_observed"], 0)

    def test_positive_support_is_counted_not_assumed_zero(self):
        rows = probe_fixture()
        rows[0]["result"]["screen"].update(positive_ids=[11104], positive_values=[.1])
        self.assertEqual(a.probe_diagnostic(rows)["positive_probe_counts"]["11104"], 1)

    def test_missing_duplicate_or_unexpected_probe(self):
        for mode in ("missing", "duplicate", "unexpected"):
            with self.subTest(mode=mode):
                rows = probe_fixture()
                if mode == "missing":
                    rows.pop()
                elif mode == "duplicate":
                    rows[-1] = deepcopy(rows[-2])
                else:
                    rows[-1]["id"] = "positive-activation-20"
                with self.assertRaises(ValueError):
                    a.probe_diagnostic(rows)

    def test_probe_context_position_and_binding_mutations(self):
        mutations = (
            lambda r: r.update(prompt="other context"),
            lambda r: r.update(plan_sha256="b" * 64),
            lambda r: r["result"].update(input_token_ids_sha256="b" * 64),
            lambda r: r["result"]["screen"].update(position=1),
            lambda r: r["result"]["screen"].update(positive_ids=[100, 100], positive_values=[.5, .5]),
            lambda r: r["result"]["screen"].update(positive_values=[float("inf")]),
            lambda r: r["result"]["telemetry"].update(intervention={"sign": 1}),
            lambda r: r["result"]["telemetry"]["position_metadata"][-1].update(origin="generated"),
            lambda r: r["result"].update(response="{}"),
        )
        for index, mutation in enumerate(mutations):
            with self.subTest(index=index):
                rows = probe_fixture()
                mutation(rows[0])
                with self.assertRaises(ValueError):
                    a.probe_diagnostic(rows)


class ProvenanceTests(unittest.TestCase):
    def test_manifest_pin_rejects_self_consistent_replacement(self):
        root = a.ROOT / "out"
        root.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="instrument-manifest-unit-", dir=root) as temp:
            path = Path(temp) / "RELEASE_MANIFEST.json"
            replacement = {"freeze_commit": a.FREEZE, "plan_sha256": a.PLAN_SHA256,
                           "status": "complete", "schema": "steering_fidelity_calibration_release_v1",
                           "files": []}
            path.write_text(json.dumps(replacement))
            with self.assertRaisesRegex(ValueError, "hash mismatch"):
                a.release_manifest(a.Inputs(), temp)
            for field, value in (("freeze_commit", "b" * 40), ("plan_sha256", "b" * 64)):
                changed = replacement | {field: value}
                path.write_text(json.dumps(changed))
                with patch.object(a, "RELEASE_MANIFEST_SHA256", a.p.sha(path)):
                    with self.assertRaisesRegex(ValueError, "binding mismatch"):
                        a.release_manifest(a.Inputs(), temp)

    def test_strict_json_rejects_duplicates_and_nonfinite(self):
        for raw in ('{"x":1,"x":2}', '{"x":NaN}', '{"x":Infinity}'):
            with self.assertRaises(ValueError):
                a.parse_json(raw)

    def test_input_hashes_and_output_guards(self):
        root = a.ROOT / "out"
        root.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="instrument-unit-", dir=root) as temp:
            path = Path(temp) / "input.json"
            path.write_text('{"x":1}\n')
            inputs = a.Inputs()
            self.assertEqual(inputs.json(path, "fixture"), {"x": 1})
            self.assertEqual(inputs.facts["fixture"]["sha256"], a.p.sha(path))
            with self.assertRaisesRegex(ValueError, "hash mismatch"):
                inputs.read(path, "fixture", "0" * 64)
            path.write_text('{"x":2}\n')
            with self.assertRaisesRegex(ValueError, "changed"):
                inputs.read(path, "fixture")
            output = Path(temp) / "report"
            a.write_report(output, {"synthetic": True})
            with self.assertRaisesRegex(ValueError, "replace"):
                a.write_report(output, {})
        with self.assertRaisesRegex(ValueError, "beneath"):
            a.write_report(a.ROOT / "data/forbidden-instrument-output", {})

    def test_test_filename_stays_outside_frozen_source_glob(self):
        self.assertNotIn("tests/test_fidelity_instrument_repair.py", a.p.source_paths())


if __name__ == "__main__":
    unittest.main()

"""Stdlib-only tests of post-hoc masks, provenance, and frozen gate invariance."""

from copy import deepcopy
from contextlib import redirect_stdout
import csv
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from experiments.sae_assay_repair import summary_correction as correction
from tests.test_sae_assay_analysis import panel


def telemetry():
    values = [[1000., 0.], [0., 0.], [1., 0.], [3., 0.], [5., 0.], [9., 0.], [2000., 0.]]
    origins = ["prompt"] * 4 + ["generated"] * 3
    return {"feature_ids": [7, 2], "selected_activations": {
        "before": values, "after": [[v * 2 for v in row] for row in values]},
        "delivery": {"valid": [True] * len(values)},
        "position_metadata": [{"origin": origin,
            "token_class": "special" if i in (0, 6) else origin,
            "terminal_observation_only": i == 5} for i, origin in enumerate(origins)]}


class SummaryTests(unittest.TestCase):
    def test_special_extreme_quantiles_order_and_nonmutation(self):
        t = telemetry()
        snapshot = deepcopy(t)
        result = correction.summarize_activations((7, 2), t)
        self.assertEqual(t, snapshot)
        self.assertEqual([r["feature_id"] for r in result], [7, 2])
        before = result[0]["before"]
        self.assertEqual(before["count"], 5)
        self.assertEqual(before["active_count"], 4)
        self.assertEqual(before["mean"], 3.6)
        self.assertEqual(before["max"], 9.)
        self.assertEqual(before["positive_q50"], 4.)
        self.assertAlmostEqual(before["positive_q90"], 7.8)
        self.assertEqual(result[0]["after"]["positive_q50"], 8.)
        self.assertEqual(result[1]["before"]["frequency"], 0.)
        self.assertIsNone(result[1]["before"]["positive_q90"])
        self.assertEqual(result[0]["mask_counts"]["special_positions"], 2)

    def test_terminal_is_reported_but_not_causal(self):
        result = correction.summarize_activations([7, 2], telemetry())[0]
        strata = result["strata"]
        self.assertEqual(strata["prompt"]["before"]["count"], 3)
        self.assertEqual(strata["generated"]["before"]["count"], 2)
        self.assertEqual(strata["generated"]["before"]["mean"], 7.)
        self.assertEqual(strata["generated_causal"]["before"]["count"], 1)
        self.assertEqual(strata["generated_causal"]["before"]["mean"], 5.)
        self.assertEqual(strata["causal"]["before"]["count"], 4)
        self.assertEqual(strata["terminal_observation_only"]["before"]["max"], 9.)
        self.assertEqual(result["before"]["count"], 5)

    def test_terminal_special_and_invalid_are_excluded_without_double_counting(self):
        t = telemetry()
        t["position_metadata"][5]["terminal_observation_only"] = False
        t["position_metadata"][6]["terminal_observation_only"] = True
        t["delivery"]["valid"][0] = False
        t["delivery"]["valid"][4] = False
        row = correction.summarize_activations([7, 2], t)[0]
        counts = row["mask_counts"]
        self.assertEqual(counts["excluded_positions"], 3)
        self.assertEqual(counts["invalid_positions"], 2)
        self.assertEqual(counts["terminal_positions_including_special"], 1)
        self.assertEqual(counts["terminal_observation_only"], 0)
        empty = row["strata"]["terminal_observation_only"]["before"]
        self.assertEqual(empty["count"], 0)
        self.assertIsNone(empty["max"])
        self.assertIsNone(empty["frequency"])

    def test_empty_and_singleton_strata(self):
        t = {"feature_ids": [7], "selected_activations": {"before": [], "after": []},
             "position_metadata": []}
        row = correction.summarize_activations([7], t)[0]
        self.assertEqual(row["before"]["count"], 0)
        self.assertIsNone(row["before"]["mean"])
        t["position_metadata"] = [{"origin": "prompt", "token_class": "prompt"}]
        t["selected_activations"] = {"before": [[2.]], "after": [[0.]]}
        row = correction.summarize_activations([7], t)[0]
        self.assertEqual(row["before"]["positive_q90"], 2.)
        self.assertEqual(row["mask_counts"]["causal"], 1)
        self.assertIsNone(row["after"]["positive_q50"])

    def test_invalid_telemetry_is_rejected(self):
        changes = [lambda t: t["feature_ids"].reverse(),
                   lambda t: t["selected_activations"]["before"].pop(),
                   lambda t: t["selected_activations"]["after"][0].pop(),
                   lambda t: t["delivery"]["valid"].__setitem__(0, 1),
                   lambda t: t["position_metadata"][0].update(origin="unknown"),
                   lambda t: t["position_metadata"][0].update(terminal_observation_only=True)]
        for value in (float("nan"), float("inf"), -1., True):
            changes.append(lambda t, value=value: t["selected_activations"]["before"][0].__setitem__(0, value))
        for change in changes:
            t = telemetry()
            change(t)
            with self.assertRaises(ValueError):
                correction.summarize_activations([7, 2], t)


class CorrectionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.rows = self.root / "release" / "rows"
        self.rows.mkdir(parents=True)

    def write_row(self, name, row):
        path = self.rows / name
        path.write_text(json.dumps(row, indent=2) + "\n", encoding="utf-8")
        return path

    def test_correction_preserves_originals_hashes_all_and_writes_comparison_csv(self):
        original = [{"feature_id": 7, "before": {"count": 999}, "after": {"count": 998}}]
        row = {"id": "nested", "generation": {"telemetry": telemetry()},
               "nested": [{"result": {"telemetry": telemetry(), "activation_summaries": original}}]}
        first = self.write_row("first.json", row)
        judge = self.write_row("judge.json", {"id": "judge", "label": 1})
        raw = {p: p.read_bytes() for p in (first, judge)}
        out = self.root / "correction"
        report = correction.correct_run(self.rows, out)
        self.assertEqual({p: p.read_bytes() for p in raw}, raw)
        self.assertEqual(report["counts"]["raw_files"], 2)
        self.assertEqual(report["counts"]["results"], 2)
        self.assertEqual(report["counts"]["results_with_mask_differences"], 2)
        self.assertEqual(report["counts"]["changed_fields"]["count"], 8)
        self.assertEqual(report["gate_comparison"]["status"], "not_applicable_no_teacher_rows")
        for entry in report["inputs"]:
            self.assertEqual(entry["sha256"], hashlib.sha256(raw[self.rows / entry["path"]]).hexdigest())
        records = {r["result_pointer"]: r for r in report["corrections"]}
        self.assertFalse(records["/generation"]["original_summaries_present"])
        saved = records["/nested/0/result"]
        self.assertEqual(saved["original_activation_summaries"], original)
        self.assertEqual(saved["old_all_recomputed"][0]["before"]["count"], 7)
        self.assertEqual(saved["activation_summaries"][0]["before"]["count"], 5)
        self.assertEqual(json.loads((out / "summary_correction.json").read_text()), report)
        with (out / "summary_differences.csv").open(newline="") as handle:
            comparisons = list(csv.DictReader(handle))
        self.assertEqual(len(comparisons), 8)
        self.assertEqual(comparisons[0]["old_all_count"], "7")
        self.assertEqual(comparisons[0]["nonspecial_count"], "5")
        with (out / "activation_summaries.csv").open(newline="") as handle:
            summaries = list(csv.DictReader(handle))
        self.assertEqual(len(summaries), 8 * len(correction.STRATA))
        with self.assertRaises(FileExistsError):
            correction.correct_run(self.rows, out)

    def test_exact_existing_gate_and_q90_invariance(self):
        for i, row in enumerate(panel()):
            row["result"]["activation_summaries"] = [{"original_marker": i}]
            self.write_row(f"teacher-{i:03d}.json", row)
        report = correction.correct_run(self.rows, self.root / "corrected")
        proof = report["gate_comparison"]
        self.assertEqual(proof["status"], "verified")
        self.assertFalse(proof["gate_definitions_changed"])
        self.assertEqual({c["calculation"] for c in proof["checks"]},
                         {"calibration_q90", "gate_pair:0.5", "gate_pair:1.0", "select_strength"})
        for check in proof["checks"]:
            self.assertTrue(check["equal"])
            self.assertEqual(check["original_sha256"], check["corrected_sha256"])
            if check["calculation"].startswith("gate_pair:"):
                for direction in check["result"]["directions"].values():
                    self.assertEqual(direction["numerical"]["requested_positions"], 126)
                    self.assertEqual(direction["norm"]["actual_edit_positions"], 126)
                    self.assertEqual(direction["features"][0]["eligible_positions"], 120)

    def test_public_source_path_is_relative_or_basename_without_absolute_paths(self):
        self.write_row("row.json", {"result": {"telemetry": telemetry()}})
        for root, expected, name in ((self.root.resolve(), "release/rows", "inside"),
                                     (self.root / "other-repo", "rows", "outside")):
            out = self.root / name
            with self.subTest(root=root), patch.object(correction, "ROOT", root):
                report = correction.correct_run(self.rows, out)
            self.assertEqual(report["source_rows"], expected)
            for artifact in out.iterdir():
                self.assertNotIn(str(self.root.resolve()), artifact.read_text())
        alias = self.root / "other-repo" / "alias"
        alias.parent.mkdir()
        alias.symlink_to(self.rows, target_is_directory=True)
        with patch.object(correction, "ROOT", alias.parent):
            self.assertEqual(correction._public_path(alias), "rows")

    def test_no_writes_inside_release_or_existing_directory(self):
        self.write_row("row.json", {"result": {"telemetry": telemetry()}})
        for out in (self.rows, self.rows / "new", self.rows.parent / "correction"):
            with self.subTest(out=out), self.assertRaises(ValueError):
                correction.correct_run(self.rows, out)
            self.assertFalse((out / "summary_correction.json").exists())
        alias = self.root / "alias"
        alias.symlink_to(self.rows.parent, target_is_directory=True)
        with self.assertRaises(ValueError):
            correction.correct_run(self.rows, alias / "new")
        dangling = self.root / "dangling"
        dangling.symlink_to(self.root / "absent", target_is_directory=True)
        with self.assertRaises(FileExistsError):
            correction.correct_run(self.rows, dangling)
        self.assertFalse((self.root / "absent").exists())

    def test_corrupt_input_and_symlink_are_rejected_before_output_creation(self):
        path = self.rows / "row.json"
        for raw in ('{"x":1,"x":2}', '{"x":NaN}', '{"x":1e999}', '[]'):
            path.write_text(raw)
            with self.assertRaises(ValueError):
                correction.correct_run(self.rows, self.root / "out")
            self.assertFalse((self.root / "out").exists())
        path.unlink()
        path.symlink_to(self.write_row("real.json", {"result": {"telemetry": telemetry()}}))
        with self.assertRaises(ValueError):
            correction.correct_run(self.rows, self.root / "out")

    def test_changed_input_detected_before_any_output(self):
        self.write_row("row.json", {"result": {"telemetry": telemetry()}})
        with patch.object(correction, "_file_hash", return_value="changed"):
            with self.assertRaisesRegex(ValueError, "Input raw bytes changed"):
                correction.correct_run(self.rows, self.root / "out")
        self.assertFalse((self.root / "out").exists())

    def test_gate_difference_is_a_hard_failure(self):
        for i, row in enumerate(panel(strengths=(.5,))):
            self.write_row(f"row-{i}.json", row)
        with patch("experiments.sae_assay_diagnostic.analysis.gate_pair",
                   side_effect=[{"pass": True}, {"pass": False}]):
            with self.assertRaisesRegex(ValueError, "Summary correction changed"):
                correction.correct_run(self.rows, self.root / "out")
        self.assertFalse((self.root / "out").exists())

    def test_cli_and_no_telemetry_failure(self):
        self.write_row("row.json", {"id": "judge", "label": 1})
        with self.assertRaisesRegex(ValueError, "No activation telemetry"):
            correction.correct_run(self.rows, self.root / "out")
        self.assertFalse((self.root / "out").exists())
        self.write_row("generation.json", {"result": {"telemetry": telemetry()}})
        output = io.StringIO()
        with redirect_stdout(output):
            status = correction.main(["--rows", str(self.rows), "--out", str(self.root / "out")])
        self.assertEqual(status, 0)
        self.assertEqual(json.loads(output.getvalue())["raw_files"], 2)
        self.assertEqual(json.loads(output.getvalue())["output"], "out")
        self.assertNotIn(str(self.root.resolve()), output.getvalue())


if __name__ == "__main__":
    unittest.main()

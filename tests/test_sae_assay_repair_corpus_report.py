"""Synthetic known-answer census tests, never repair outcomes or API/GPU work."""

from contextlib import ExitStack, redirect_stdout
from copy import deepcopy
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from experiments.sae_assay_diagnostic import analysis
from experiments.sae_assay_repair import corpus_report as report
from tests.test_sae_assay_analysis import teacher_row


def synthetic_row(text="example", mode="zero", strength=0, *, corpus=report.CORPORA[0],
                  split="calibration", operator="literal", n=5, before=(2., 0.),
                  category="neutral", loss_delta=.2):
    """Extend the historical *synthetic test builder*, not any collected data."""
    text_id = f"synthetic-{corpus}-{split}-{text}"
    row = teacher_row(text_id, mode, strength, split=split, group=operator,
                      category=category, n=n, before=before, efficacy=.5)
    row.update(text_id=text_id, corpus=corpus,
               id=f"{text_id}-{operator}-{mode}-{strength:g}")
    result, edited = row["result"], mode != "zero"
    t = result["telemetry"]
    t["repair_operator"] = operator
    t["full_sae"] = {
        "full_selected_before": deepcopy(t["selected_activations"]["before"]),
        "full_selected_after": deepcopy(t["selected_activations"]["after"]),
        "non_target_change_norm": [float(i) if edited else 0. for i in range(n)],
        "non_target_changed_count": [i * 2 if edited else 0 for i in range(n)],
        "reconstruction_error_norm": [2. + i for i in range(n)],
        "reconstruction_relative_error": [.02 + .01 * i for i in range(n)],
        "l0_before": [10 + i for i in range(n)],
    }
    result["reconstruction_nll"] = [None] + [2.5] * (n - 1)
    result["edited_nll"] = [None] + [2. + loss_delta if edited else 2.] * (n - 1)
    result["activation_summaries"] = [{"ignored_stale_summary": 999999}]
    return row


def grid():
    rows = []
    for corpus in report.CORPORA:
        for split in report.SPLITS:
            before = (2., 0.) if corpus == report.CORPORA[0] else (4., 1.)
            kwargs = dict(corpus=corpus, split=split, before=before)
            rows.append(synthetic_row(**kwargs))
            rows.extend(synthetic_row(mode=mode, strength=strength, operator=operator, **kwargs)
                        for operator in report.OPERATORS for strength in analysis.STRENGTHS
                        for mode in analysis.DIRECTIONS)
    return rows


def cell(value, corpus=report.CORPORA[0], split="calibration", operator="literal",
         strength=.5, direction="suppression"):
    return next(r for r in value["cells"] if (r["corpus"], r["split"], r["operator"],
                r["strength"], r["direction"]) == (corpus, split, operator, strength, direction))


def summarize(rows):
    census = report._Census()
    for row in rows:
        census.add(row)
    return census.report()


class NumericTests(unittest.TestCase):
    def test_all_corpora_splits_operators_doses_and_directions_without_gate_calls(self):
        rows = grid()
        snapshot = deepcopy(rows)
        forbidden = ("calibration_q90", "gate_pair", "select_strength", "validate_selected",
                     "encoder_decision_report", "encoder_parity_report", "_direction")
        with ExitStack() as stack:
            for name in forbidden:
                stack.enter_context(patch.object(analysis, name, side_effect=AssertionError(name)))
            result = summarize(rows)
        self.assertEqual(rows, snapshot)
        self.assertEqual(len(result["cells"]), 52)
        self.assertEqual(sum(c["row_count"] for c in result["cells"]), len(rows))
        self.assertTrue(all(c["status"] == "observed" for c in result["cells"]))
        self.assertEqual(result["recorded_amplification_q90"]["values"], [6., 6.])
        self.assertFalse(result["recorded_amplification_q90"]["recomputed"])
        self.assertEqual(len(result["recorded_amplification_q90"]["recorded_row_ids"]), 24)
        for c in result["cells"]:
            self.assertEqual(c["text_count"], 1)
            self.assertEqual(c["missing_text_ids_relative_to_observed_panel"], [])
            self.assertEqual(c["text_ids_without_separate_clean_row"], [])
            f = c["statistics"]["features"][0]
            self.assertEqual(f["positive_before_positions"], 4)
            self.assertEqual(f["positive_before_texts"], 1)
            if c["direction"] == "zero":
                self.assertEqual(c["operator"], "shared_clean")
                self.assertIsNone(f["paired_ratio"])
            else:
                expected = 1 - c["strength"] * .5 if c["direction"] == "suppression" else .5
                self.assertAlmostEqual(f["paired_ratio"]["median"], expected)
                self.assertEqual(f["paired_ratio_positions"], 4)
        authored = cell(result)["statistics"]["features"][1]
        published = cell(result, corpus=report.CORPORA[1])["statistics"]["features"][1]
        self.assertEqual(authored["positive_before_positions"], 0)
        self.assertIsNone(authored["paired_ratio"]["median"])
        self.assertEqual(published["positive_before_positions"], 4)
        # No hidden qualification verdict, threshold comparison, or confidence interval.
        def keys(value):
            if isinstance(value, dict):
                for key, child in value.items():
                    yield key
                    yield from keys(child)
            elif isinstance(value, list):
                for child in value:
                    yield from keys(child)
        self.assertFalse(set(keys(result)) & {"pass", "failure_codes", "exposure_pass", "efficacy_pass",
                                             "selected", "ci", "confidence_interval", "q90"})

    def test_ratio_is_within_position_not_ratio_of_means_and_scopes_differ(self):
        row = synthetic_row(mode="suppression", strength=.5)
        t = row["result"]["telemetry"]
        a, d = t["selected_activations"], t["delivery"]
        for i, (before, after) in enumerate(((1000., 900.), (2., 0.), (6., 3.), (8., 8.), (4., 4.))):
            for key, value in (("before", before), ("requested_delta", -before / 2),
                               ("requested_activation", before / 2), ("after", after)):
                a[key][i][0] = value
        # Invalid index 3 and special index 4 are excluded from coordinate/NLL metrics.
        d["valid"][3] = False
        a["requested_delta"][3] = [0., 0.]
        a["requested_activation"][3] = list(a["before"][3])
        for key, value in (("nonzero_requested", False), ("requested_norm", 0.),
                           ("realized_norm", 0.), ("identity", True)):
            d[key][3] = value
        t["position_metadata"][4]["token_class"] = "special"
        for phase in ("before", "after"):
            t["full_sae"]["full_selected_" + phase] = deepcopy(a[phase])
        row["result"]["edited_nll"][4] = 100.
        stats = cell(summarize([row]))["statistics"]
        feature = stats["features"][0]
        self.assertEqual(feature["paired_ratio"]["median"], .25)
        self.assertNotEqual(feature["paired_ratio"]["median"], 3 / 8)
        self.assertEqual(feature["before"]["max"], 6.)
        self.assertEqual(feature["paired_ratio_positions"], 2)
        counts = stats["position_counts"]
        self.assertEqual(counts["all_positions_including_special"], 5)
        self.assertEqual(counts["excluded_coordinate_positions"], 3)
        self.assertEqual(counts["nonzero_requested_positions"], 4)
        metrics = stats["metrics"]
        self.assertEqual(metrics["non_target_changed_count_all_positions"]["distribution"]["mean"], 4.)
        self.assertEqual(metrics["non_target_change_norm_nonspecial_valid"]["distribution"]["mean"], 1.5)
        self.assertEqual(metrics["clean_reconstruction_error_norm_all_positions"]["distribution"]["count"], 5)
        self.assertEqual(metrics["clean_l0_before_all_positions"]["distribution"]["mean"], 12.)
        self.assertEqual(metrics["clean_reconstruction_minus_unsteered_nll_nonspecial_valid"]["distribution"]["mean"], .5)
        self.assertEqual(metrics["residual_cosine_nonzero_requested"]["distribution"]["count"], 4)
        self.assertAlmostEqual(metrics["neutral_paired_nll_delta"]["distribution"]["mean"], .2)

    def test_neutral_nll_token_and_equal_text_means_and_non_neutral_exclusion(self):
        rows = [synthetic_row("short", "amplification", 1., n=3, loss_delta=.2),
                synthetic_row("long", "amplification", 1., n=5, loss_delta=.8),
                synthetic_row("not-neutral", "amplification", 1., n=10,
                              category="roleplay", loss_delta=100.)]
        stats = cell(summarize(rows), strength=1., direction="amplification")["statistics"]
        metric = stats["metrics"]["neutral_paired_nll_delta"]["distribution"]
        self.assertEqual(metric["count"], 6)
        self.assertAlmostEqual(metric["mean"], .6)
        self.assertAlmostEqual(stats["neutral_paired_nll"]["equal_text_mean_delta"], .5)
        self.assertEqual(stats["neutral_paired_nll"]["neutral_text_count"], 2)
        self.assertEqual(stats["features"][1]["paired_ratio_positions"], 15)

    def test_absent_conditional_branches_are_null_not_zero_effects(self):
        result = summarize([synthetic_row(split="validation")])
        absent = [r for r in result["cells"] if r["status"] != "observed"]
        self.assertEqual(len(absent), 51)
        for c in absent:
            self.assertEqual(c["row_count"], 0)
            self.assertIsNone(c["statistics"])
        validation = cell(result, split="validation")
        self.assertEqual(len(validation["missing_text_ids_relative_to_observed_panel"]), 1)
        self.assertIsNone(result["recorded_amplification_q90"]["values"])
        self.assertEqual(result["original_noop_qualification"]["status"], "not_recorded")

    def test_missing_optional_diagnostics_and_partial_branches_remain_explicit(self):
        first = synthetic_row("a", "suppression", .5)
        second = synthetic_row("b", "suppression", .5)
        second["result"]["telemetry"]["full_sae"] = None
        second["result"]["reconstruction_nll"] = None
        result = summarize([first, second, synthetic_row("c")])
        c = cell(result)
        self.assertEqual(len(c["missing_text_ids_relative_to_observed_panel"]), 1)
        self.assertEqual(len(c["text_ids_without_separate_clean_row"]), 2)
        m = c["statistics"]["metrics"]["non_target_change_norm_all_positions"]
        self.assertEqual(m["status"], "partially_recorded")
        self.assertEqual(m["missing_row_ids"], [second["id"]])
        self.assertEqual(m["distribution"]["count"], 5)
        missing = cell(summarize([second]))["statistics"]["metrics"]["clean_l0_before_all_positions"]
        self.assertEqual(missing["status"], "not_recorded")
        self.assertIsNone(missing["distribution"])

    def test_noop_original_booleans_are_preserved_and_not_requalified(self):
        qualification = {"id": "qualification-live", "pass": False,
                         "checks": {"literal_zero_identity": True, "decoder_span_zero_identity": False}}
        zero = synthetic_row()
        result = summarize([qualification, zero])
        original = result["original_noop_qualification"]["records"][0]
        self.assertEqual(original["original_checks"], qualification["checks"])
        self.assertFalse(original["original_reported_pass"])
        noop = cell(result, operator="shared_clean", strength=0, direction="zero")["statistics"]["original_noop_identity"]["rows"][0]
        self.assertEqual(noop["original_identity_flags"]["true_positions"], 5)
        self.assertTrue(noop["before_after_exactly_equal"])
        del zero["result"]["telemetry"]["delivery"]["identity"]
        result = summarize([zero])
        noop = cell(result, operator="shared_clean", strength=0, direction="zero")["statistics"]["original_noop_identity"]["rows"][0]
        self.assertIsNone(noop["original_identity_flags"]["true_positions"])

    def test_rounded_away_and_undefined_norm_ratio_are_not_dropped(self):
        row = synthetic_row(mode="suppression", strength=.5)
        d = row["result"]["telemetry"]["delivery"]
        d["realized_norm"][1] = 0.
        d["identity"][1] = True
        d["clean_norm"][2] = 0.
        stats = cell(summarize([row]))["statistics"]
        self.assertEqual(stats["position_counts"]["rounded_away_positions"], 1)
        self.assertEqual(stats["position_counts"]["undefined_norm_ratio_zero_clean_positions"], 1)
        self.assertEqual(stats["metrics"]["residual_realized_over_clean_norm_actual_edits"]["distribution"]["count"], 3)

    def test_q90_missing_is_not_recomputed_and_known_q90_must_agree(self):
        first = synthetic_row("a", "amplification", .5)
        second = synthetic_row("b", "amplification", .5)
        second["result"]["telemetry"]["q90"] = None
        recorded = summarize([first, second])["recorded_amplification_q90"]
        self.assertEqual(recorded["status"], "partially_recorded")
        self.assertEqual(recorded["missing_amplification_row_ids"], [second["id"]])
        # Adjust requests too, so each row is individually valid but run q90 differs.
        t = second["result"]["telemetry"]
        t["q90"] = [8., 8.]
        for i, b in enumerate(t["selected_activations"]["before"]):
            delta = [.5 * (8. - v) for v in b]
            t["selected_activations"]["requested_delta"][i] = delta
            t["selected_activations"]["requested_activation"][i] = [v + dv for v, dv in zip(b, delta)]
        with self.assertRaisesRegex(ValueError, "q90 differs"):
            summarize([first, second])

    def test_invalid_shapes_metadata_pairing_and_duplicates_are_not_silently_dropped(self):
        changes = [lambda r: r.update(corpus="unknown"), lambda r: r.pop("text_id"),
                   lambda r: r.update(group="unknown"),
                   lambda r: r["result"]["telemetry"]["full_sae"]["non_target_change_norm"].pop(),
                   lambda r: r["result"]["telemetry"]["full_sae"]["non_target_changed_count"].__setitem__(0, .5),
                   lambda r: r["result"]["telemetry"]["full_sae"]["full_selected_before"][0].__setitem__(0, 99.),
                   lambda r: r["result"]["reconstruction_nll"].__setitem__(1, -1.),
                   lambda r: r["result"]["edited_nll"].__setitem__(1, None),
                   lambda r: r["result"]["telemetry"].update(repair_operator="other")]
        for change in changes:
            row = synthetic_row(mode="suppression", strength=.5)
            change(row)
            with self.subTest(change=change), self.assertRaises(ValueError):
                summarize([row])
        first = synthetic_row()
        second = synthetic_row(mode="suppression", strength=.5)
        second["result"]["unsteered_nll"][1] = 3.
        with self.assertRaisesRegex(ValueError, "Paired clean"):
            summarize([first, second])
        with self.assertRaisesRegex(ValueError, "Duplicate raw row"):
            summarize([first, first])
        duplicate = deepcopy(first)
        duplicate["id"] += "-duplicate"
        with self.assertRaisesRegex(ValueError, "Duplicate text/arm"):
            summarize([first, duplicate])
        changed = synthetic_row("other")
        changed["result"]["telemetry"]["feature_ids"].reverse()
        with self.assertRaisesRegex(ValueError, "Ordered feature"):
            summarize([first, changed])


class FileTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.rows = self.root / "release" / "rows"
        self.rows.mkdir(parents=True)

    def write_row(self, row, name=None):
        path = self.rows / (name or row["id"] + ".json")
        path.write_text(json.dumps(row) + "\n", encoding="utf-8")
        return path

    def test_deterministic_fresh_output_read_only_inputs_and_source_hashes(self):
        for row in grid():
            self.write_row(row)
        self.write_row({"id": "context-synthetic", "context": "raw", "result": {}}, "context.json")
        self.write_row({"id": "format-synthetic", "arm": "zero", "result": {}}, "format.json")
        untouched = self.rows.parent / "locked-selection.json"
        untouched.write_text('{"synthetic": "not read or changed"}\n')
        raw = {p: p.read_bytes() for p in self.rows.parent.rglob("*.json")}
        out = self.root / "report-a"
        first = report.report_corpus(self.rows, out)
        report.report_corpus(self.rows, self.root / "report-b")
        self.assertEqual((out / "corpus_report.json").read_bytes(),
                         (self.root / "report-b" / "corpus_report.json").read_bytes())
        self.assertEqual({p: p.read_bytes() for p in raw}, raw)
        self.assertEqual(json.loads((out / "corpus_report.json").read_text()), first)
        self.assertEqual(first["raw_row_count"], 54)
        self.assertEqual(first["teacher_row_count"], 52)
        self.assertEqual(len(first["excluded_rows"]), 2)
        for item in first["inputs"]:
            self.assertEqual(item["sha256"], hashlib.sha256(raw[self.rows / item["path"]]).hexdigest())
        self.assertEqual(first["source_hashes"]["frozen_analysis_helpers"], report._file_hash(Path(analysis.__file__)))
        self.assertNotIn(str(self.root.resolve()), (out / "corpus_report.json").read_text())
        with self.assertRaises(FileExistsError):
            report.report_corpus(self.rows, out)

    def test_no_teacher_outcomes_yet_is_an_explicit_empty_grid(self):
        self.write_row({"id": "qualification-live", "pass": True,
                        "checks": {"literal_zero_identity": True}})
        result = report.report_corpus(self.rows, self.root / "out")
        self.assertEqual(result["teacher_row_count"], 0)
        self.assertTrue(all(c["statistics"] is None for c in result["cells"]))

    def test_output_cannot_enter_source_release_or_reuse_symlinks(self):
        self.write_row(synthetic_row())
        for out in (self.rows, self.rows / "new", self.rows.parent / "new"):
            with self.subTest(out=out), self.assertRaises(ValueError):
                report.report_corpus(self.rows, out)
        alias = self.root / "alias"
        alias.symlink_to(self.rows.parent, target_is_directory=True)
        with self.assertRaises(ValueError):
            report.report_corpus(self.rows, alias / "new")
        dangling = self.root / "dangling"
        dangling.symlink_to(self.root / "absent", target_is_directory=True)
        with self.assertRaises(FileExistsError):
            report.report_corpus(self.rows, dangling)
        self.assertFalse((self.root / "absent").exists())
        source_alias = self.root / "source-alias"
        source_alias.symlink_to(self.rows, target_is_directory=True)
        with self.assertRaises(ValueError):
            report.report_corpus(source_alias, self.rows.parent / "new")

    def test_corrupt_json_malformed_rows_and_symlink_inputs_fail_before_output(self):
        path = self.rows / "row.json"
        for raw in ('{"id":"x","id":"y"}', '{"id":"x","x":NaN}',
                    '{"id":"x","x":1e999}', '[]', '{"id":"edit-bad","result":{}}'):
            path.write_text(raw)
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                report.report_corpus(self.rows, self.root / "out")
            self.assertFalse((self.root / "out").exists())
        path.unlink()
        path.symlink_to(self.write_row(synthetic_row(), "real.json"))
        with self.assertRaisesRegex(ValueError, "symlinks"):
            report.report_corpus(self.rows, self.root / "out")

    def test_input_mutation_and_inventory_growth_abort_before_output(self):
        self.write_row(synthetic_row())
        original_hash = report._file_hash
        def changed_hash(path):
            return "changed" if path.parent == self.rows.resolve() else original_hash(path)
        with patch.object(report, "_file_hash", side_effect=changed_hash):
            with self.assertRaisesRegex(ValueError, "raw bytes changed"):
                report.report_corpus(self.rows, self.root / "out")
        original_report = report._Census.report
        def growing(census):
            self.write_row(synthetic_row("late"))
            return original_report(census)
        with patch.object(report._Census, "report", growing):
            with self.assertRaisesRegex(ValueError, "inventory changed"):
                report.report_corpus(self.rows, self.root / "out")
        self.assertFalse((self.root / "out").exists())

    def test_cli_and_import_need_no_torch_numpy_or_model_backend(self):
        self.write_row(synthetic_row())
        output = io.StringIO()
        with redirect_stdout(output):
            status = report.main(["--rows", str(self.rows), "--out", str(self.root / "out")])
        self.assertEqual(status, 0)
        self.assertEqual(json.loads(output.getvalue())["teacher_rows"], 1)
        proc = subprocess.run([sys.executable, "-c",
            "import sys; from experiments.sae_assay_repair import corpus_report; "
            "assert not ({'torch', 'numpy', 'transformers', 'experiments.sae_assay_repair.runner', "
            "'experiments.sae_assay_repair.backend'} & set(sys.modules))"],
            cwd=report.ROOT, capture_output=True, text=True,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}, check=False)
        self.assertEqual(proc.returncode, 0, proc.stderr)


if __name__ == "__main__":
    unittest.main()

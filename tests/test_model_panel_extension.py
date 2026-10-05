"""Offline publication bindings, paired arithmetic, and tamper rejection."""
from contextlib import contextmanager
from copy import deepcopy
import gzip
import math
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from scripts import verify_model_panel_extension as v


class OpenRouterSwapExtensionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.saved, cls.provenance = v.load_sources()
        cls.result = v.derive(cls.saved)

    @contextmanager
    def sandbox(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            shutil.copytree(v.ROOT / v.PACKAGE, root / v.PACKAGE)
            for name in (*v.OWN, v.FIGURE + ".pdf", v.FIGURE + ".png"):
                target = root / name
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(v.ROOT / name, target)
            yield root

    def test_complete_binding_is_read_only(self):
        with patch.object(Path, "write_bytes", side_effect=AssertionError("read only")), \
             patch.object(Path, "write_text", side_effect=AssertionError("read only")), \
             patch.object(Path, "mkdir", side_effect=AssertionError("read only")), \
             patch.object(v.subprocess, "run", side_effect=AssertionError("no git/network in check")):
            report = v.verify()
        self.assertTrue(report["pass"])
        self.assertEqual(report["main_answers"], 512)
        self.assertEqual(report["screen_answers"], 144)
        self.assertFalse(report["scope"]["human_validation"])
        self.assertFalse(report["scope"]["raw_api_receipts_reaudited_by_this_command"])

    def test_editorial_files_stay_outside_original_scientific_source_inventory(self):
        from experiments.openrouter_swap import protocol
        sources = set(protocol.source_paths())
        plan = protocol.verify(protocol.ROOT / protocol.PLAN)
        self.assertEqual(sources, set(plan["source_hashes"]))
        self.assertTrue(set(v.OWN[:2]).isdisjoint(sources))
        self.assertTrue(all(protocol.sha(protocol.ROOT / name) == digest
                            for name, digest in plan["source_hashes"].items()))

    def test_primary_contrasts_from_individual_paired_rows(self):
        for model, mean in (("gemini", 26 / 32), ("opus", 7 / 32)):
            current = self.result["main"][model]["astra"][v.INCLUSIVE]
            self.assertEqual(current["contrasts"][v.PRIMARY[0]]["estimate"], mean)
            rows = self.saved["main_rows"]
            blocks = {i: {r["cell"]: r for r in rows if r["model"] == model and r["block"] == i}
                      for i in range(1, 33)}
            direct = sum(v.observed(b["SH"], "astra", v.INCLUSIVE)
                         - v.observed(b["HS"], "astra", v.INCLUSIVE) for b in blocks.values()) / 32
            self.assertEqual(direct, mean)

    def test_eight_comparisons_not_four_or_two(self):
        row = self.result["main"]["gemini"]["astra"][v.INCLUSIVE]["contrasts"][v.PRIMARY[0]]
        radius = math.sqrt(2 * math.log(320) / 32)
        self.assertAlmostEqual(row["simultaneous_ci95"][0], .8125 - radius)
        self.assertEqual(row["simultaneous_ci95"][1], 1)
        self.assertLess(row["simultaneous_ci95"][0], v.bounded_interval(.8125, 32, 4)[0])

    def test_neutral_zero_does_not_become_equivalence(self):
        for model in v.MODELS:
            row = self.result["main"][model]["astra"][v.INCLUSIVE]["contrasts"][v.PRIMARY[1]]
            self.assertEqual(row["estimate"], 0)
            self.assertLess(row["simultaneous_ci95"][0], -.60)
            self.assertGreater(row["simultaneous_ci95"][1], .60)
        self.assertEqual(self.result["main"]["opus"]["opus"][v.INCLUSIVE]
                         ["contrasts"][v.PRIMARY[1]]["estimate"], -1 / 32)

    def test_primary_not_switched_to_larger_paper_result(self):
        opus = self.result["main"]["opus"]
        for judge, primary in (("astra", 7 / 32), ("opus", 12 / 32)):
            self.assertEqual(opus[judge][v.INCLUSIVE]["contrasts"][v.PRIMARY[0]]["estimate"], primary)
            self.assertEqual(opus[judge]["paper"]["contrasts"][v.PRIMARY[0]]["estimate"], 25 / 32)
            self.assertNotIn("simultaneous_ci95", opus[judge]["paper"]["contrasts"][v.PRIMARY[0]])
        self.assertNotIn("simultaneous_ci95", opus["opus"][v.INCLUSIVE]["contrasts"][v.PRIMARY[0]])

    def test_explicit_endpoint_preserved_for_both_models_and_judges(self):
        expected = {("gemini", "astra"): 7 / 32, ("gemini", "opus"): 12 / 32,
                    ("opus", "astra"): 3 / 32, ("opus", "opus"): 6 / 32}
        for (model, judge), mean in expected.items():
            self.assertEqual(self.result["main"][model][judge][v.EXPLICIT]
                             ["contrasts"][v.PRIMARY[0]]["estimate"], mean)

    def test_sonnet_floor_and_deepseek_technical_absence_are_distinct(self):
        sonnet = self.result["screen"]["sonnet"]
        self.assertFalse(sonnet["eligible"])
        self.assertEqual([sonnet["readers"][j]["positive"] for j in v.JUDGES], [1, 3])
        self.assertNotIn("deepseek", self.result["screen"])
        self.assertNotIn("sonnet", self.result["main"])
        self.assertEqual(self.result["screen_unrun_slots"], 48)
        self.assertEqual(self.result["deferred"]["deepseek"]["status"], "not_run_privacy_route_unavailable")

    def test_unrun_deepseek_slots_cannot_become_observed_negatives(self):
        saved = deepcopy(self.saved)
        row = next(r for r in saved["screen_rows"] if r["model"] == "deepseek")
        row["status"] = "ok"
        row["response"] = "No"
        with self.assertRaisesRegex(ValueError, "Deferred slots"):
            v.derive(saved)

    def test_settings_do_not_invent_matching_temperature(self):
        settings = self.result["model_settings"]
        self.assertEqual(settings["gemini"]["temperature"], .5)
        self.assertNotIn("temperature", settings["opus"])
        self.assertNotIn("temperature", settings["sonnet"])
        self.assertTrue(all(s["reasoning_effort"] == "medium" for s in settings.values()))

    def test_opus_respondent_judge_overlap_is_disclosed(self):
        plan = self.saved["plan"]
        self.assertEqual(plan["models"]["opus"]["id"], plan["judges"]["opus"]["id"])
        prose = " ".join((v.ROOT / "paper/openrouter_swap_extension.tex").read_text().split())
        self.assertIn("answers generated by Opus itself", prose)
        self.assertIn("does not remove the risk of self-evaluation bias", prose)
        self.assertNotIn("as a check using a different provider", prose)

    def test_same_condition_donor_controls_remain_separate(self):
        opus = self.result["main"]["opus"]["astra"][v.INCLUSIVE]
        self.assertEqual(opus["positive"]["SS"], 4)
        self.assertEqual(opus["positive"]["S_SHAM"], 6)
        self.assertEqual(opus["contrasts"]["self_sham"]["estimate"], 2 / 32)
        self.assertEqual(opus["contrasts"]["history_sham"]["estimate"], -3 / 32)

    def test_missing_duplicate_or_reassigned_row_rejected(self):
        for change in ("missing", "duplicate", "family", "donor"):
            saved = deepcopy(self.saved)
            rows = saved["main_rows"]
            if change == "missing":
                rows.pop()
            elif change == "duplicate":
                rows[-1] = deepcopy(rows[0])
            elif change == "family":
                rows[0]["family"] = "b"
            else:
                rows[0]["source_id"] = "different-donor"
            with self.subTest(change=change), self.assertRaises(ValueError):
                v.derive(saved)

    def test_refusal_missing_or_integer_label_not_reclassified(self):
        for change in ("refusal", "empty", "integer", "null"):
            saved = deepcopy(self.saved)
            row = saved["main_rows"][0]
            if change == "refusal":
                row["labels"]["astra"]["structured"]["refusal"] = True
            elif change == "empty":
                row["response"] = " "
            else:
                row["labels"]["astra"]["structured"][v.INCLUSIVE] = 1 if change == "integer" else None
            with self.subTest(change=change), self.assertRaises(ValueError):
                v.derive(saved)

    def test_changed_analysis_or_endpoint_or_family_rejected(self):
        for change in ("analysis", "endpoint", "family", "screen"):
            saved = deepcopy(self.saved)
            if change == "analysis":
                saved["analysis"]["models"]["gemini"]["judges"]["astra"][v.INCLUSIVE]["cells"]["SH"]["positive"] = 27
            elif change == "endpoint":
                saved["plan"]["analysis"]["primary_endpoint"] = "paper"
            elif change == "family":
                saved["plan"]["analysis"]["primary_family_size"] = 4
            else:
                saved["plan"]["qualification"]["min_positive"] = 1
            with self.subTest(change=change), self.assertRaises(ValueError):
                v.derive(saved)

    def test_a_changed_paired_value_is_detected_even_with_same_total(self):
        saved = deepcopy(self.saved)
        row = saved["analysis"]["models"]["gemini"]["judges"]["astra"][v.INCLUSIVE]
        row["contrasts"][v.PRIMARY[0]]["per_block"][0]["value"] = .5
        with self.assertRaisesRegex(ValueError, "paired-block"):
            v.derive(saved)

    def test_input_row_tamper_rejected_before_arithmetic(self):
        with self.sandbox() as root:
            path = root / v.PACKAGE / "inputs/main_rows.json.gz"
            data = v.decode(gzip.decompress(path.read_bytes()))
            data[0]["labels"]["astra"]["paper"] = False
            path.write_bytes(gzip.compress(v.encoded(data), mtime=0))
            with self.assertRaisesRegex(ValueError, "Source hash/size"):
                v.verify(root)

    def test_rehashing_local_manifest_cannot_replace_source_pin(self):
        with self.sandbox() as root:
            path = root / v.PACKAGE / "inputs/source_inventory.json"
            data = v.decode(path.read_bytes())
            data["files"][0]["sha256"] = "0" * 64
            path.write_bytes(v.encoded(data))
            with self.assertRaisesRegex(ValueError, "manifest pin"):
                v.verify(root)

    def test_derived_file_tamper_rejected(self):
        for name in v.DERIVED:
            with self.subTest(name=name), self.sandbox() as root:
                path = root / v.PACKAGE / name
                path.write_bytes(path.read_bytes() + b" ")
                with self.assertRaisesRegex(ValueError, "Derived output"):
                    v.verify(root)

    def test_manuscript_figure_and_code_tamper_rejected(self):
        for name in ("paper/openrouter_swap_extension.tex", v.FIGURE + ".pdf", v.OWN[0]):
            with self.subTest(name=name), self.sandbox() as root:
                path = root / name
                path.write_bytes(path.read_bytes() + b" ")
                with self.assertRaisesRegex(ValueError, "manifest/file hash"):
                    v.verify(root)

    def test_source_symlink_rejected(self):
        with self.sandbox() as root:
            path = root / v.PACKAGE / "inputs/main_rows.json.gz"
            path.unlink()
            path.symlink_to(v.ROOT / v.PACKAGE / "inputs/main_rows.json.gz")
            with self.assertRaisesRegex(ValueError, "Symlink"):
                v.verify(root)

    def test_json_duplicate_keys_and_nonfinite_rejected(self):
        for raw in (b'{"a":1,"a":2}', b'{"a":NaN}'):
            with self.assertRaises(ValueError):
                v.decode(raw)

    def test_figure_shows_uncertainty_for_both_judges_without_switching_primary(self):
        data = v.figure_data(self.result)
        self.assertEqual(len(data["rows"]), 12)
        interval_rows = [r for r in data["rows"] if "simultaneous_ci95" in r]
        self.assertEqual(len(interval_rows), 2)
        self.assertTrue(all(r["judge"] == "astra" and r["endpoint"] == v.INCLUSIVE for r in interval_rows))
        self.assertTrue(all(len(r["descriptive_bootstrap_ci95"]) == 2 for r in data["rows"]))
        self.assertIn("Pointwise", data["interval_scope"])
        self.assertIn("not plotted", data["primary_inference"])

    def test_displayed_bootstrap_is_checked_against_released_rows(self):
        saved = deepcopy(self.saved)
        row = saved["analysis"]["models"]["gemini"]["judges"]["opus"][v.EXPLICIT]
        row["contrasts"][v.PRIMARY[0]]["bootstrap_95"]["interval"] = [-1, 1]
        with self.assertRaises(ValueError):
            v.derive(saved)

    def test_figure_has_no_embedded_explanatory_caption(self):
        import inspect
        source = inspect.getsource(v.render_figure)
        self.assertNotIn("fig.text(", source)
        self.assertIn('row["descriptive_bootstrap_ci95"]', source)

    def test_display_rounding_and_bounds(self):
        macros = v.render_values(self.result).decode()
        self.assertIn(r"\ORSGeminiAstraInclusiveEffect}{0.81}", macros)
        self.assertIn(r"\ORSGeminiAstraInclusiveCI}{[0.21, 1.00]}", macros)
        self.assertIn(r"\ORSOpusAstraInclusiveCI}{[-0.38, 0.82]}", macros)
        self.assertEqual(v.rd(-0.0), "0.00")


if __name__ == "__main__":
    unittest.main()

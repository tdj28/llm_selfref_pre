"""Offline summary binding and deterministic reporting; no optional repo or model."""
from contextlib import contextmanager, redirect_stdout
from copy import deepcopy
import io
from pathlib import Path
import re
import shutil
import tempfile
import unittest
from unittest.mock import patch

from scripts import verify_completed_extensions as v


class CompletedExtensionsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sources, cls.provenance = v.load_sources()
        cls.results = v.derive(cls.sources)

    @contextmanager
    def sandbox(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths = set(v.OWN_SOURCES)
            for release in self.provenance.values():
                paths.add(release["manifest_path"])
                paths.update(release["inputs"])
            paths.update(v.PACKAGE + "/" + name for name in v.OUTPUTS)
            for name in paths:
                target = root / name
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(v.ROOT / name, target)
            yield root

    def test_checked_in_package_is_current_and_read_only(self):
        with patch.object(Path, "write_bytes", side_effect=AssertionError("Check must not write")), \
             patch.object(Path, "write_text", side_effect=AssertionError("Check must not write")), \
             patch.object(Path, "mkdir", side_effect=AssertionError("Check must not mkdir")):
            report = v.verify()
        self.assertTrue(report["pass"])
        self.assertEqual(report["release_manifests"], 5)
        self.assertFalse(report["scope"]["bootstrap_intervals_recomputed"])
        self.assertFalse(report["scope"]["raw_generations_or_judge_receipts_reaudited"])
        self.assertFalse(report["scope"]["human_validation"])
        self.assertTrue(report["scope"]["editorial_binding_only"])
        self.assertFalse(report["scope"]["authorizes_experiments"])

    def test_inventory_is_answers_or_trials_not_judgments_or_completion_rows(self):
        self.assertEqual({k: r.get("answers", r.get("trials")) for k, r in self.results.items()},
                         {"bilingual": 480, "frontier": 144, "qualification": 48, "operator": 870, "fine": 105})
        self.assertEqual(self.results["operator"]["steps"], {"grid": 640, "zero": 10, "prompt": 180, "bridge": 40})
        self.assertEqual(self.results["fine"]["steps"], {"grid": 100, "zero": 5})
        self.assertEqual(self.results["operator"]["conditional_holdout_inventory"],
                         {"slots": 2560, "possible_combos": 32, "trials_per_combo": 80,
                          "top_k": 3, "maximum_selected_trials": 240})
        self.assertIsNone(self.results["fine"]["conditional_holdout_inventory"])
        self.assertFalse(self.results["operator"]["holdout_run"])
        values = v.render_values(self.results).decode()
        self.assertIn(r"\CEFineGrid}{100}", values)
        self.assertIn(r"\CEFineZero}{5}", values)

    def test_conditional_holdout_inventory_is_not_selected_branch_size(self):
        prose = " ".join((v.ROOT / "paper/operator_matching.tex").read_text().split())
        self.assertIn("The conditional holdout was not run because no configuration qualified", prose)
        self.assertNotIn("CEOperatorHoldout", v.render_values(self.results).decode())
        saved = deepcopy(self.sources["operator"])
        saved["__plan__"]["rules"]["top_k"] = 32
        with self.assertRaisesRegex(ValueError, "Holdout conditional inventory/selection"):
            v.operator_result(saved)

    def test_primary_is_both_reader_inclusive_interaction_not_history_anchor(self):
        rows = self.results["bilingual"]["readers"]
        for reader, estimate, ci in (("openai", .05, [-.1, .2]), ("anthropic", -.15, [-.35, .05])):
            value = rows[reader][v.INCLUSIVE]["zh_minus_en"]
            self.assertAlmostEqual(value["estimate"], estimate)
            self.assertEqual(value["ci95"], ci)
            self.assertLessEqual(ci[0], 0)
            self.assertGreaterEqual(ci[1], 0)
            self.assertGreater(rows[reader]["explicit_current_assertion"]["zh_minus_en"]["estimate"], 0)
            self.assertLess(rows[reader]["paper_positive"]["zh_minus_en"]["estimate"], 0)
        self.assertEqual(rows["openai"]["instruction"]["estimate"], .5)
        self.assertEqual(rows["openai"]["transcript"]["estimate"], .45)
        self.assertAlmostEqual(rows["anthropic"]["instruction"]["estimate"], .475)
        self.assertAlmostEqual(rows["anthropic"]["transcript"]["estimate"], .425)

    def test_table_has_both_readers_primary_and_opposite_secondary_directions(self):
        table = v.render_table(self.results).decode()
        self.assertIn("\\multicolumn{2}{c}{Astra} & \\multicolumn{2}{c}{Opus 5.5}", table)
        self.assertIn("Explicit or implicit claim (main)", table)
        self.assertIn("$+5$ & $[-10,+20]$ & $-15$ & $[-35,+5]$", table)
        self.assertIn("$+75$ & $[+45,+105]$ & $+50$ & $[+25,+75]$", table)
        self.assertIn("$-50$ & $[-70,-30]$ & $-35$ & $[-55,-15]$", table)

    def test_all_prose_macros_resolve_without_main_tex(self):
        macros = v.render_values(self.results).decode()
        defined = set(re.findall(r"\\newcommand\{\\(CE[A-Za-z]+)\}", macros))
        for name in ("paper/context_extensions.tex", "paper/operator_matching.tex"):
            text = (v.ROOT / name).read_text()
            self.assertLessEqual(set(re.findall(r"\\(CE[A-Za-z]+)", text)), defined)
        self.assertIn(r"\label{sec:context-extensions}", (v.ROOT / "paper/context_extensions.tex").read_text())
        self.assertIn(r"\label{sec:operator-matching}", (v.ROOT / "paper/operator_matching.tex").read_text())

    def test_frontier_floor_is_observed_not_population_precision(self):
        frontier = self.results["frontier"]
        self.assertEqual(frontier["blocks"], 6)
        for reader in v.READERS:
            rows = frontier["readers"][reader]
            self.assertEqual(sum(rows["astra"][l][v.INCLUSIVE] for l in ("en", "zh")), 0)
            self.assertEqual(rows["astra"]["en"]["instruction"]["ci95"], [0, 0])
            self.assertTrue(all(rows["gpt41"][l]["instruction"]["estimate"] > .7 for l in ("en", "zh")))

    def test_qualification_retains_original_failed_gates(self):
        result = self.results["qualification"]
        self.assertEqual(result["decision"], "fail")
        for row in result["readers"].values():
            self.assertGreaterEqual(row["instruction_effect"], .5)
            self.assertAlmostEqual(row["upward_headroom"], 1 / 12)
            self.assertEqual(row["conflict_excess"], .25)
        values = v.render_values(self.results).decode()
        self.assertIn(r"\CEQualificationAstraInstruction}{0.500}", values)
        self.assertIn(r"\CEQualificationOpusInstruction}{0.542}", values)
        self.assertIn(r"\CEQualificationAstraHeadroom}{0.083}", values)
        self.assertIn(r"\CEQualificationOpusHeadroom}{0.083}", values)

    def test_cross_study_swap_summary_matches_cell_counts(self):
        frontier = self.results["frontier"]["readers"]
        self.assertAlmostEqual(frontier["openai"]["opus"]["en"]["paper_transcript"]["estimate"], -3 / 12)
        self.assertAlmostEqual(frontier["anthropic"]["opus"]["en"]["paper_transcript"]["estimate"], -4 / 12)
        qualification = self.results["qualification"]["readers"]
        self.assertAlmostEqual(qualification["openai"]["continuation_effect"], 10 / 24)
        self.assertAlmostEqual(qualification["anthropic"]["continuation_effect"], 11 / 24)
        values = v.render_values(self.results).decode()
        expected = {
            "FrontierGptAstraPrimaryInstruction": "0.75", "FrontierGptOpusPrimaryInstruction": "0.83",
            "FrontierGptAstraPrimaryContinuation": "0.08", "FrontierGptOpusPrimaryContinuation": "0.17",
            "FrontierOpusAstraPrimaryInstruction": "0.08", "FrontierOpusOpusPrimaryInstruction": "0.00",
            "FrontierOpusAstraPrimaryContinuation": "-0.08", "FrontierOpusOpusPrimaryContinuation": "0.00",
            "FrontierOpusAstraPrimaryInstructionLo": "-0.17", "FrontierOpusAstraPrimaryInstructionHi": "0.33",
            "FrontierGptAstraSecondaryInstruction": "0.83", "FrontierGptOpusSecondaryInstruction": "0.83",
            "FrontierGptAstraSecondaryContinuation": "0.17", "FrontierGptOpusSecondaryContinuation": "0.17",
            "FrontierOpusAstraSecondaryInstruction": "0.58", "FrontierOpusOpusSecondaryInstruction": "0.50",
            "FrontierOpusAstraSecondaryContinuation": "-0.25", "FrontierOpusOpusSecondaryContinuation": "-0.33",
            "FrontierAstraAstraPrimaryInstruction": "0.00", "FrontierAstraOpusPrimaryContinuation": "0.00",
            "QualificationAstraInstruction": "0.50", "QualificationOpusInstruction": "0.54",
            "QualificationAstraContinuation": "0.42", "QualificationOpusContinuation": "0.46",
            "LlamaAstraInstruction": "0.50", "LlamaOpusInstruction": "0.48",
            "LlamaAstraContinuation": "0.45", "LlamaOpusContinuation": "0.43",
        }
        for name, value in expected.items():
            self.assertIn("\\CESwap" + name + "}{" + value + "}", values)
        self.assertEqual(v.rd2(-0.0), "0.00")
        self.assertEqual(v.rd2(0.425), "0.43")

    def test_frontier_primary_designation_is_bound_to_plan(self):
        frontier = self.results["frontier"]
        self.assertEqual(frontier["primary_endpoint"], v.INCLUSIVE)
        self.assertEqual(frontier["secondary_endpoint"], "paper_positive")
        saved = deepcopy(self.sources["frontier"])
        saved["__plan__"]["analysis"]["primary"] = "paper_positive"
        with self.assertRaisesRegex(ValueError, "primary/secondary endpoint"):
            v.frontier_result(saved)

    def test_frontier_primary_counts_and_transcript_arithmetic_checked(self):
        for contrast in ("instruction_effect", "transcript_effect"):
            saved = deepcopy(self.sources["frontier"])
            row = v.one(saved["analysis/analysis.json"]["contrasts"], judge="openai",
                        model="opus", language="en", endpoint=v.INCLUSIVE, contrast=contrast)
            row["estimate"] += 0.5
            with self.assertRaisesRegex(ValueError, "Arithmetic"):
                v.frontier_result(saved)

    def test_frontier_table_and_prose_distinguish_primary_from_secondary(self):
        main = (v.ROOT / "paper/main.tex").read_text()
        table = main.split(r"\label{tab:swap-summary}", 1)[1].split(r"\end{table}", 1)[0]
        macros = re.findall(r"\\(CESwapFrontier[A-Za-z]+)", table)
        self.assertEqual(len(macros), 12)
        self.assertTrue(all("Primary" in name for name in macros))
        self.assertIn("prespecified primary endpoint", table)
        prose = " ".join((v.ROOT / "paper/context_extensions.tex").read_text().split())
        for reader in ("Astra", "Opus"):
            for role in ("Primary", "Secondary"):
                self.assertIn("CESwapFrontierOpus" + reader + role + "Instruction", prose)
        self.assertIn("secondary paper rubric", prose)
        self.assertNotIn("under the main rubric in Claude Opus 5.5", main)

    def test_frontier_respondent_judge_overlap_is_disclosed(self):
        plan = self.sources["frontier"]["__plan__"]
        for model, reader in (("astra", "openai"), ("opus", "anthropic")):
            self.assertEqual(plan["models"][model]["id"], plan["judges"]["models"][reader])
        prose = " ".join((v.ROOT / "paper/context_extensions.tex").read_text().split())
        self.assertIn("each scores answers generated by its own model", prose)
        main = " ".join((v.ROOT / "paper/main.tex").read_text().split())
        self.assertIn("Haiku 4.5 judges Haiku 4.5 answers", main)
        self.assertIn("does not estimate the size of any self-evaluation bias", main)
        self.assertIn("two scoring rules, not two different judge models", main)
        self.assertIn("primary local judge was the same Gemma checkpoint", main)
        repeated = main.split(r"\input{repeated_extension.tex}", 1)[1].split(r"\FloatBarrier", 1)[0]
        self.assertIn("answers generated by Opus itself", repeated)

    def test_steering_presentation_is_findings_first_without_changing_bound_inputs(self):
        main = (v.ROOT / "paper/main.tex").read_text()
        abstract = main.split(r"\begin{abstract}", 1)[1].split(r"\end{abstract}", 1)[0]
        self.assertIn("Berg et al.", abstract)
        self.assertLess(abstract.index("We recover the prompting effect"), abstract.index("RubricAuditAstraInclusive"))
        self.assertLess(abstract.index("RubricAuditAstraInclusive"), abstract.index("DoseMainSecondTargetEstimate"))
        for reader in ("Astra", "Opus"):
            self.assertIn("RubricAudit" + reader + "Inclusive", abstract)
            self.assertNotIn("RubricAudit" + reader + "Explicit", abstract)
            self.assertIn("RubricAudit" + reader + "Explicit", main.split(r"\end{abstract}", 1)[1])
        self.assertNotIn("+0.30", abstract)
        self.assertIn("Judges and rubric both change", " ".join(abstract.split()))
        self.assertIn("DoseMainSecondTargetEstimate", abstract)
        self.assertNotIn("EnsemblePaperTargetGap", abstract)
        self.assertEqual(main.count(r"\input{../evidence/dose_followup/values.tex}"), 1)
        self.assertNotIn(r"\input{dose_followup.tex}", main)
        body, appendix = main.split(r"\section{Supporting Public-Weight Steering Studies}", 1)
        for name in ("ensemble_alignment.tex", "operator_matching.tex"):
            self.assertNotIn(r"\input{" + name + "}", body)
            self.assertIn(r"\input{" + name + "}", appendix)
        for name in ("SecondTargetNegativeYes", "SecondTargetPositiveYes", "SecondZeroYes",
                     "SecondTargetLow", "SecondTargetHigh", "SecondSpecificityLow",
                     "SecondSpecificityHigh", "PaperTargetLow", "PaperTargetHigh"):
            self.assertIn("DoseMain" + name, body)
        self.assertIn("primary notebook classifier", " ".join(body.split()))
        self.assertIn("secondary paper rubric", " ".join(body.split()))

    def test_missing_or_duplicated_selected_cells_fail(self):
        for duplicate in (False, True):
            saved = deepcopy(self.sources["bilingual"])
            rows = saved["analysis/analysis.json"]["effects"]
            selected = v.one(rows, provider="openai", endpoint=v.INCLUSIVE,
                             contrast="self_minus_recursive:zh_minus_en", panel="main")
            rows.append(deepcopy(selected)) if duplicate else rows.remove(selected)
            with self.assertRaisesRegex(ValueError, "Missing/duplicate"):
                v.bilingual_result(saved)

    def test_missingness_and_block_duplicates_are_not_dropped(self):
        for mutate in (lambda r: r.update(status="incomplete"),
                       lambda r: r["blocks"].append(deepcopy(r["blocks"][0])),
                       lambda r: r["blocks"][0].update(missing_item_ids=["absent"])):
            saved = deepcopy(self.sources["bilingual"])
            row = v.one(saved["analysis/analysis.json"]["effects"], provider="openai",
                        endpoint=v.INCLUSIVE, contrast="self_minus_recursive:en", panel="main")
            mutate(row)
            with self.assertRaises(ValueError):
                v.bilingual_result(saved)

    def test_primary_cannot_be_replaced_by_secondary(self):
        saved = deepcopy(self.sources["bilingual"])
        saved["analysis/analysis.json"]["primary"][0]["endpoint"] = "explicit_current_assertion"
        with self.assertRaisesRegex(ValueError, "Missing/duplicate"):
            v.bilingual_result(saved)

    def test_contrast_arithmetic_and_interval_shape_checked(self):
        row = deepcopy(self.sources["frontier"]["analysis/analysis.json"]["contrasts"][0])
        row["estimate"] = .4
        with self.assertRaisesRegex(ValueError, "Arithmetic"):
            v.effect(row, 6)
        row["estimate"] = 0
        row["ci95"] = [1, -1]
        with self.assertRaisesRegex(ValueError, "interval"):
            v.effect(row, 6)

    def test_operator_missingness_duplicate_and_trial_count_fail(self):
        for change in ("missing", "duplicate", "count"):
            saved = deepcopy(self.sources["operator"])
            if change == "missing":
                saved["analysis/rates.csv"][0]["missing"] = "1"
            elif change == "duplicate":
                saved["analysis/rates.csv"].append(deepcopy(saved["analysis/rates.csv"][0]))
            else:
                saved["analysis/summary.json"]["rows"] = 871
            with self.assertRaises(ValueError):
                v.operator_result(saved)

    def test_fine_scope_is_not_full_grid_and_failed_holdout_not_negative_data(self):
        fine = self.results["fine"]
        self.assertEqual(set(fine["combos"]), {f"all|add|{s}" for s in range(4, 9)})
        self.assertEqual({k for k, v in fine["combos"].items() if v["coherent"]},
                         {"all|add|4", "all|add|5", "all|add|7"})
        values = v.render_values(self.results).decode()
        self.assertIn(r"\CEFineZeroCells}{19}", values)
        self.assertIn(r"\CEFineCells}{20}", values)
        self.assertIn(r"\CEFineRemainingPositive}{1/5}", values)
        saved = deepcopy(self.sources["operator"])
        saved["analysis/summary.json"]["held_out"] = [{"rate": 0}]
        with self.assertRaisesRegex(ValueError, "Holdout"):
            v.operator_result(saved)
        saved = deepcopy(self.sources["fine"])
        saved["analysis/summary.json"]["combos"]["assistant|add|4"] = saved["analysis/summary.json"]["combos"].pop("all|add|4")
        with self.assertRaisesRegex(ValueError, "scope/grid"):
            v.operator_result(saved, fine=True)

    def test_source_tamper_is_rejected_even_in_write_mode(self):
        with self.sandbox() as root:
            source = root / v.PINS["bilingual"][0] / "analysis/analysis.json"
            source.write_bytes(source.read_bytes() + b" ")
            before = {p.name: p.read_bytes() for p in (root / v.PACKAGE).iterdir()}
            with self.assertRaisesRegex(ValueError, "Source hash"):
                v.verify(root, write=True)
            self.assertEqual(before, {p.name: p.read_bytes() for p in (root / v.PACKAGE).iterdir()})

    def test_manifest_tamper_and_output_tamper_fail(self):
        with self.sandbox() as root:
            output = root / v.PACKAGE / "values.tex"
            output.write_text("changed")
            with self.assertRaisesRegex(ValueError, "Generated evidence"):
                v.verify(root)
            v.verify(root, write=True)
            manifest = root / self.provenance["fine"]["manifest_path"]
            manifest.write_bytes(manifest.read_bytes() + b"\n")
            with self.assertRaisesRegex(ValueError, "manifest pin"):
                v.verify(root)

    def test_write_is_deterministic_and_limited_to_compact_outputs(self):
        with self.sandbox() as root:
            before = {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob("*") if p.is_file()}
            v.verify(root, write=True)
            v.verify(root, write=True)
            after = {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob("*") if p.is_file()}
            self.assertEqual(before, after)

    def test_unlisted_artifact_symlink_and_unsafe_path_rejected(self):
        with self.sandbox() as root:
            extra = root / v.PACKAGE / "extra.txt"
            extra.write_text("not bound")
            with self.assertRaisesRegex(ValueError, "Unlisted"):
                v.verify(root)
            extra.unlink()
            output = root / v.PACKAGE / "table.tex"
            output.unlink()
            output.symlink_to(root / v.PACKAGE / "values.tex")
            with self.assertRaisesRegex(ValueError, "Symlink"):
                v.verify(root, write=True)
        with self.assertRaisesRegex(ValueError, "Unsafe"):
            v.local(v.ROOT, "../outside")

    def test_strict_json_and_manifest_inventory(self):
        for blob in (b'{"x":1,"x":2}', b'{"x":NaN}', b'{"x":Infinity}'):
            with self.assertRaises(ValueError):
                v.decode(blob)
        entry = {"path": "same.json", "sha256": "a" * 64}
        with self.assertRaisesRegex(ValueError, "duplicate"):
            v.manifest_entries({"files": [entry, entry]})

    def test_cli_check_is_default(self):
        for args in ([], ["--check"]):
            with redirect_stdout(io.StringIO()) as output:
                self.assertEqual(v.main(args), 0)
            self.assertTrue(v.decode(output.getvalue())["pass"])


if __name__ == "__main__":
    unittest.main()

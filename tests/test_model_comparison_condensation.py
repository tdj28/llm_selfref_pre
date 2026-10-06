"""Keep the condensed model comparison tied to existing published quantities."""
import re
import unittest
from pathlib import Path

from scripts import verify_repeated_presentation


ROOT = Path(__file__).resolve().parents[1]
SOURCES = (
    "evidence/completed_extensions/values.tex",
    "evidence/openrouter_swap_extension/values.tex",
    "evidence/qwen_extension/values.tex",
    "evidence/kolibri_extension/values.tex",
)


class ModelComparisonCondensationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tex = (ROOT / "paper/model_comparison.tex").read_text()
        cls.prose = " ".join(cls.tex.split())
        cls.macros = {}
        for path in SOURCES:
            cls.macros.update(re.findall(
                r"\\newcommand\{\\([A-Za-z]+)\}\{([^{}]*)\}",
                (ROOT / path).read_text(),
            ))

    def test_two_subsections_retain_all_old_section_anchors(self):
        self.assertEqual(self.tex.count(r"\subsection{"), 2)
        for section in ("context-extensions", "qwen-extension", "kolibri-extension",
                        "openrouter-swap-extension", "repeated-extension"):
            self.assertEqual(self.tex.count(r"\label{sec:" + section + "}"), 1)
        self.assertEqual(self.tex.count(r"\begin{table}"), 1)
        self.assertEqual(self.tex.count(r"\begin{figure}"), 3)
        for label in ("app:model-inventory", "app:repeated-variation",
                      "fig:bilingual-examples", "app:repeated-bounds"):
            self.assertIn(r"\ref{" + label + "}", self.tex)

    def test_numeric_macros_all_come_from_existing_packages(self):
        used = set(re.findall(r"\\((?:CE|ORS|QEX|KEX)[A-Za-z]+)", self.tex))
        self.assertTrue(used)
        self.assertFalse(used - self.macros.keys() - {"QEXArtifact"})
        self.assertNotIn(r"\newcommand", self.tex)

    def test_qwen_table_discloses_post_release_measurement_repair(self):
        table = self.tex.split(r"\begin{table}", 1)[1].split(r"\end{table}", 1)[0]
        table = " ".join(table.split())
        self.assertEqual(self.macros["QEXRecovered"], "3")
        self.assertIn(r"\QEXRecovered{} missing GPT-6 Astra structured judgments", table)
        for phrase in ("additive post-release repair", "without regenerating answers",
                       "or replacing completed judgments", "original incomplete release remains preserved"):
            self.assertIn(phrase, table)

    def test_llama_qualification_failed_gate_and_reused_answers_remain_visible(self):
        main = (ROOT / "paper/main.tex").read_text()
        inventory = main.split(r"\label{app:model-inventory}", 1)[1].split(r"\begin{table}", 1)[0]
        inventory = " ".join(inventory.split())
        self.assertEqual(self.macros["CEQualificationBlocks"], "12")
        self.assertIn(r"\CEQualificationBlocks{}-block", inventory)
        for phrase in ("failed both preconditions", "(headroom)",
                       "instruction--continuation conflict",
                       "Neither the planned extension nor the internal intervention ran",
                       "re-scored these same Llama answers", "without collecting new Llama generations"):
            self.assertIn(phrase, inventory)

    def test_abstract_steering_comparison_names_distinct_implementations(self):
        main = (ROOT / "paper/main.tex").read_text()
        abstract = main.split(r"\begin{abstract}", 1)[1].split(r"\end{abstract}", 1)[0]
        abstract = " ".join(abstract.split())
        self.assertNotIn("give no support", abstract)
        self.assertNotIn("not recovered at the reported size", abstract)
        self.assertIn("In our public-weight steering test", abstract)
        self.assertIn("0.80 difference", abstract)
        self.assertIn("different steering implementation through Goodfire's proprietary API", abstract)
        self.assertTrue(abstract.endswith("Goodfire's proprietary API."))
        body = " ".join(main.split(r"\end{abstract}", 1)[1].split())
        self.assertIn("It leaves a modest effect possible and target specificity unresolved", body)

    def test_abstract_opening_limits_scope_and_reports_source_observations(self):
        main = (ROOT / "paper/main.tex").read_text()
        opening = main.split(r"\begin{abstract}", 1)[1].split("The prompting effect replicates", 1)[0]
        opening = " ".join(opening.split())
        self.assertIn("partial replication and extension", opening)
        self.assertIn("who reported that", opening)
        self.assertIn("changed claim rates in Llama 3.3 70B", opening)
        self.assertIn("using public weights", opening)
        for wording in ("who concluded", "consistently elicits", "mechanistically gated"):
            self.assertNotIn(wording, opening)

    def test_abstract_scoring_names_both_changed_judges_and_current_claim_rule(self):
        main = (ROOT / "paper/main.tex").read_text()
        abstract = " ".join(main.split(r"\begin{abstract}", 1)[1].split(r"\end{abstract}", 1)[0].split())
        self.assertIn("Judging the same answers in different ways", abstract)
        self.assertIn("two different model judges", abstract)
        self.assertIn("the responding model's current experience", abstract)
        self.assertIn("explicit or implicit claims", abstract)
        for name in ("RubricAuditN", "RubricAuditOldOpenaiPositive", "RubricAuditOldAnthropicPositive",
                     "RubricAuditAstraInclusive", "RubricAuditOpusInclusive"):
            self.assertIn("\\" + name + "{}", abstract)

    def test_steering_comparison_uses_bound_counts_and_discloses_nonmatching(self):
        main = (ROOT / "paper/main.tex").read_text()
        table = main.split(r"\label{tab:steering-comparison}", 1)[1].split(r"\end{table}", 1)[0]
        caption = main.split(r"\label{tab:steering-comparison}", 1)[0].rsplit(r"\caption{", 1)[1]
        self.assertIn("not dose-matched comparisons", " ".join(caption.split()))
        self.assertIn("Notebook classifier (primary)", table)
        self.assertIn("Not reported for this aggregate comparison", table)
        self.assertIn(r"\steeringrate{48}{50}", table)
        self.assertIn(r"\steeringrate{8}{50}", table)
        self.assertLess(table.index("Suppression &"), table.index("Design differences"))
        self.assertIn(r"\addlinespace[5pt]", table)
        self.assertIn(r"@{\hspace{14pt}}", table)
        self.assertIn("all tested levels above", table)
        self.assertIn("failed at least one quality check", " ".join(table.split()))
        for name in ("DoseMainSelectedDose", "DoseMainSecondTargetNegativeYes", "DoseMainTargetNegativeN",
                     "DoseMainSecondTargetPositiveYes", "DoseMainTargetPositiveN", "DoseMainSecondZeroYes",
                     "DoseMainZeroN", "DoseMainSecondTargetEstimate", "DoseMainSecondTargetLow", "DoseMainSecondTargetHigh"):
            self.assertRegex(table, r"\\" + name + r"\b")

    def test_reporting_details_are_in_appendix_with_main_text_pointer(self):
        main = (ROOT / "paper/main.tex").read_text()
        body, appendix = main.split(r"\appendix", 1)
        self.assertIn(r"Appendix~\ref{sec:reporting-gaps}", body)
        self.assertNotIn(r"\label{sec:reporting-gaps}", body)
        self.assertNotIn(r"\TruthfulQAMinPairedT{}", body)
        self.assertIn(r"\subsection{Published steering: reporting details}", appendix)
        self.assertEqual(appendix.count(r"\label{sec:reporting-gaps}"), 1)
        self.assertEqual(appendix.count(r"\TruthfulQAMinPairedT{}"), 2)
        for phrase in ("one binary score per condition", "two-decimal rounding",
                       "an undescribed unit of analysis", "single-feature curves",
                       "truthful/deceptive label"):
            self.assertIn(phrase, " ".join(appendix.split()))

    def test_availability_description_matches_grouped_link_table(self):
        main = (ROOT / "paper/main.tex").read_text()
        availability = main.split(r"\label{app:ensemble-portability}", 1)[1]
        opening = " ".join(availability.split("The prospective collection plans", 1)[0].split())
        self.assertIn("commit-pinned links to the principal releases and result summaries", opening)
        self.assertIn("grouped by evidence type", opening)
        self.assertNotIn("lists, for each study", opening)
        self.assertIn("Evidence & Release or result index", availability)

    def test_self_evaluation_disclosure_cites_merged_section_once(self):
        main = (ROOT / "paper/main.tex").read_text()
        disclosure = main.split("Opus 5.5 also judges", 1)[1].split("We report readers separately", 1)[0]
        self.assertEqual(disclosure.count(r"\ref{"), 1)
        self.assertIn(r"Section~\ref{sec:repeated-extension}", disclosure)

    def test_frontier_keeps_primary_and_secondary_distinct(self):
        expected = {
            "CESwapFrontierOpusAstraPrimaryInstruction": "0.08",
            "CESwapFrontierOpusOpusPrimaryInstruction": "0.00",
            "CESwapFrontierOpusAstraSecondaryInstruction": "0.58",
            "CESwapFrontierOpusOpusSecondaryInstruction": "0.50",
        }
        for name, value in expected.items():
            self.assertEqual(self.macros[name], value)
            self.assertIn("\\" + name + "{}", self.tex)
        self.assertIn("averaged instruction effects, not the head-to-head", self.prose)
        self.assertIn("primary instruction effects", self.prose)
        self.assertIn("secondary paper rubric", self.prose)

    def test_table_retains_primary_bounds_not_descriptive_substitutes(self):
        table = self.tex.split(r"\begin{table}", 1)[1].split(r"\end{table}", 1)[0]
        expected = {
            "ORSGeminiAstraInclusiveCI": "[0.21, 1.00]",
            "ORSOpusAstraInclusiveCI": "[-0.38, 0.82]",
            "QEXAstraInclusiveSwapCI": "[-0.16, 0.97]",
            "KEXPrimaryAstraInclusiveSHHSBounds": "[-0.02, 1.00]",
        }
        for name, value in expected.items():
            self.assertEqual(self.macros[name], value)
            self.assertIn("\\" + name + "{}", table)
        for name in ("ORSMainBlocks", "QEXBlocks", "KEXMainAstraInclusiveSHHSPlannedBlocks"):
            self.assertEqual(self.macros[name], "32")
        self.assertIn("primary simultaneous 95", table)
        self.assertIn("other estimates are secondary", table)

    def test_llama_components_and_language_boundary_survive(self):
        for name, value in {
            "CELlamaAstraInstruction": "+50", "CELlamaAstraTranscript": "+45",
            "CELlamaOpusInstruction": "+47.5", "CELlamaOpusTranscript": "+42.5",
        }.items():
            self.assertEqual(self.macros[name], value)
            self.assertIn("\\" + name + "{}", self.tex)
        for phrase in ("holding the continuation fixed", "holding the instruction fixed",
                       "external recursive-feedback control, not Roman history",
                       "uncertainty, not language equivalence", "gap larger in Chinese",
                       "paper rubric makes it smaller"):
            self.assertIn(phrase, self.prose)

    def test_human_translation_check_is_limited_to_displayed_examples(self):
        self.assertIn("A Chinese speaker checked the translations displayed in that figure", self.prose)
        self.assertIn("does not extend to the full dataset or the automated labels", self.prose)
        self.assertNotIn("translations are not human-validated", self.prose)
        main = (ROOT / "paper/main.tex").read_text()
        caption = main.split(r"\textbf{Actual English and Chinese answers", 1)[1].split(
            r"\label{fig:bilingual-examples}", 1)[0]
        caption = " ".join(caption.split())
        self.assertIn("A Chinese speaker checked the displayed translations", caption)
        self.assertIn("does not validate the automated labels or the full dataset", caption)
        self.assertIn("recorded Claude Opus 5.5 translations", caption)
        self.assertIn("display-only correction", caption)

    def test_repeated_result_keeps_missingness_and_conservative_uncertainty(self):
        original, binding = verify_repeated_presentation.load()
        data = verify_repeated_presentation.derive(original, binding)
        rows = {(r["model"], r["reader"]): r for r in data["rows"]}
        for model, expected in (("gemini", "0.75"), ("opus", "0.22")):
            row = rows[model, "astra"]
            self.assertEqual(f"{row['estimate']:.2f}", expected)
            self.assertIn(expected, self.tex)
            self.assertEqual(row["bootstrap"]["confidence"], .975)
        self.assertLess(rows["opus", "astra"]["conservative_all_planned_bounds"][0], 0)
        self.assertEqual(rows["gemini", "astra"]["missing_blocks"], 1)
        self.assertEqual(rows["opus", "opus"]["missing_blocks"], 1)
        for phrase in ("all-planned bound for Opus includes zero", "remain unknown, not negative",
                       "after the earlier panel's results", "97.5\\% for Astra",
                       "descriptive 95\\% for Opus", "retaining all answer draws"):
            self.assertIn(phrase, self.prose)

    def test_control_and_self_evaluation_limits_stay_visible(self):
        for phrase in ("not for an instruction advantage", "do not establish equivalence",
                       "do not remove the semantic mismatch", "neutral and donor controls were not repeated",
                       "readers also evaluate their own model's answers",
                       "different-model reading of Opus", "independent human validation"):
            self.assertIn(phrase, self.prose)


if __name__ == "__main__":
    unittest.main()

"""Keep a readable variance explanation tied to the frozen publication."""
import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class RepeatedEditorialTests(unittest.TestCase):
    def test_original_results_table_and_detailed_figure_are_preserved(self):
        original = (ROOT / "paper/repeated_extension.tex").read_text()
        editorial = (ROOT / "paper/repeated_extension_editorial.tex").read_text()
        original = original[original.index(r"\subsection{"):]
        editorial = editorial[editorial.index(r"\subsection{"):]
        old_prefix, old_rest = original.split("Across three answers", 1)
        new_prefix, new_rest = editorial.split("Even with the instruction", 1)
        self.assertEqual(old_prefix, new_prefix)
        self.assertEqual(old_rest.split(r"\begin{table}", 1)[1].split(r"\end{table}", 1)[0],
                         new_rest.split(r"\begin{table}", 1)[1].split(r"\end{table}", 1)[0])
        main = (ROOT / "paper/main.tex").read_text()
        self.assertIn(r"\input{model_comparison.tex}", main)
        self.assertIn(r"\label{app:repeated-variation}", main)
        self.assertIn(old_rest.split(r"\begin{table}", 1)[1].split(r"\end{table}", 1)[0],
                      main.split(r"\appendix", 1)[1])
        self.assertIn("c09b19445c24e63f5160953883e71d76850fa9df/evidence/repeated_extension/repeated_main.pdf", main)
        self.assertIn(r"\label{app:repeated-bounds}", main)

    def test_explanation_matches_released_variance_summary(self):
        data = json.loads((ROOT / "evidence/repeated_extension/figure_data.json").read_text())
        rows = [model["readers"][reader]["inclusive_current_assertion"]["variance"]["SH"]
                for model in data["models"].values() for reader in ("astra", "opus")]
        self.assertEqual(len(rows), 4)
        self.assertEqual(f"{min(row['W'] for row in rows):.2f}", "0.16")
        self.assertEqual(f"{max(row['W'] for row in rows):.2f}", "0.20")
        for row in rows:
            self.assertLessEqual(row["bootstrap"]["B_interval"][0], 0)
            self.assertGreaterEqual(row["bootstrap"]["B_interval"][1], 0)
            self.assertEqual(row["bootstrap"]["confidence"], .95)
            self.assertEqual(row["stratum_weights"], {"a": .5, "b": .5})
        editorial = " ".join((ROOT / "paper/repeated_extension_editorial.tex").read_text().split())
        self.assertIn("0.16 to 0.20", editorial)
        self.assertIn("all four descriptive 95\\% intervals included zero", editorial)
        self.assertIn("remains unresolved", editorial)
        appendix = " ".join((ROOT / "paper/main.tex").read_text().split())
        for phrase in ("minus $W/3$", "not percentages", "not a formal test of $W-B$",
                       "does not establish certainty", "do not provide independent human validation"):
            self.assertIn(phrase, appendix)


if __name__ == "__main__":
    unittest.main()

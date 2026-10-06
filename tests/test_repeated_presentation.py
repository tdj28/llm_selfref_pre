"""Keep the simplified figure faithful to the original repeated-answer release."""
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import verify_repeated_presentation as v


class RepeatedPresentationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.original, cls.binding = v.load()
        cls.data = v.derive(cls.original, cls.binding)

    def test_four_points_preserve_intervals_and_missingness(self):
        self.assertEqual(len(self.data["rows"]), 4)
        self.assertEqual(self.data["primary_family_size"], 2)
        self.assertEqual(self.data["nominal_family_confidence"], .95)
        for row in self.data["rows"]:
            old = self.original["models"][row["model"]]["readers"][row["reader"]]["inclusive_current_assertion"]["contrasts"]["instruction_minus_transcript"]
            self.assertEqual(row["estimate"], old["complete_case_mean"])
            self.assertEqual(row["bootstrap"], old["bootstrap"])
            self.assertEqual(row["bootstrap"]["confidence"], .975 if row["reader"] == "astra" else .95)
            self.assertEqual(row["missing_label_bounds"], old["worst_case_mean_bounds"])
            self.assertEqual(row["conservative_all_planned_bounds"], old["worst_case_hoeffding"])
        self.assertEqual(sum(row["missing_blocks"] for row in self.data["rows"]), 2)
        opus = [r for r in self.data["rows"] if r["model"] == "opus"]
        self.assertTrue(all(r["conservative_all_planned_bounds"][0] < 0 for r in opus))

    def test_artists_match_four_estimates_and_bootstrap_bars(self):
        fig, ax = v.make_plot(self.data)
        self.addCleanup(fig.clear)
        points = {a.get_gid(): a for a in ax.lines if a.get_gid()}
        intervals = {a.get_gid(): a for a in ax.collections if a.get_gid()}
        self.assertEqual(len(points), 4)
        self.assertEqual(len(intervals), 4)
        self.assertEqual(list(fig.get_size_inches()), [6.4, 2.8])
        for row in self.data["rows"]:
            tag = row["model"] + ":" + row["reader"]
            self.assertEqual(list(points["estimate:" + tag].get_xdata()), [row["estimate"]])
            self.assertEqual(intervals["interval:" + tag].get_segments()[0][:, 0].tolist(), row["bootstrap"]["interval"])
            self.assertEqual(points["estimate:" + tag].get_marker(), "o" if row["reader"] == "astra" else "s")
        self.assertEqual([t.get_text() for t in ax.get_yticklabels()], [label for _, label in v.MODELS])
        self.assertFalse(ax.get_title())

    def test_verification_is_read_only(self):
        with patch.object(Path, "write_bytes", side_effect=AssertionError("No writes")), \
             patch.object(Path, "write_text", side_effect=AssertionError("No writes")), \
             patch.object(Path, "mkdir", side_effect=AssertionError("No writes")):
            self.assertTrue(v.verify()["pass"])

    def test_tampered_output_and_original_are_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            shutil.copytree(v.ROOT / v.SOURCE, root / v.SOURCE)
            shutil.copytree(v.ROOT / v.PACKAGE, root / v.PACKAGE)
            for name in (*v.OWN, "paper/main.tex"):
                target = root / name
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(v.ROOT / name, target)
            self.assertTrue(v.verify(root)["pass"])
            image = root / v.PACKAGE / "summary.pdf"
            image.write_bytes(image.read_bytes() + b"changed")
            with self.assertRaisesRegex(ValueError, "output hash differs"):
                v.verify(root)
            source = root / v.SOURCE / "figure_data.json"
            source.write_bytes(source.read_bytes() + b" ")
            with self.assertRaisesRegex(ValueError, "Original publication output changed"):
                v.verify(root)


if __name__ == "__main__":
    unittest.main()

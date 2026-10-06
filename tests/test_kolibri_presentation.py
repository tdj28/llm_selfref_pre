"""Presentation-only checks; the immutable Kolibri release is replayed separately."""
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import verify_kolibri_presentation as v


class KolibriPresentationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.result, cls.original, cls.binding = v.load()
        cls.data = v.derive(cls.result, cls.original, cls.binding)

    def test_six_points_keep_all_three_rubrics_and_both_readers(self):
        self.assertEqual(len(self.data["rows"]), 6)
        for row in self.data["rows"]:
            original = self.result["phases"]["main"]["judges"][row["reader"]][row["endpoint"]]["contrasts"]["instruction_minus_transcript"]
            self.assertEqual(row["estimate"], original["estimate"])
            self.assertEqual(row["descriptive_ci95"], original["descriptive_95"])
            self.assertEqual(row["pointwise_hoeffding95"], original["worst_case_hoeffding_95"])
        self.assertEqual(self.data["primary_inference"], self.result["primary"])
        self.assertEqual(self.data["primary_inference"]["family_size"], 2)
        self.assertEqual(self.data["bootstrap_resamples"], 10000)
        self.assertFalse(self.data["scope"]["new_inference"])

    def test_plot_artists_match_values_and_qwen_style(self):
        fig, ax = v.make_plot(self.data)
        self.addCleanup(fig.clear)
        self.assertEqual(list(fig.get_size_inches()), [6.4, 2.8])
        self.assertEqual([x.get_text() for x in ax.get_yticklabels()], list(v.LABELS))
        points = {x.get_gid(): x for x in ax.lines if x.get_gid()}
        intervals = {x.get_gid(): x for x in ax.collections if x.get_gid()}
        self.assertEqual(len(points), 6)
        self.assertEqual(len(intervals), 6)
        for row in self.data["rows"]:
            tag = row["reader"] + ":" + row["endpoint"]
            point = points["estimate:" + tag]
            self.assertEqual(list(point.get_xdata()), [row["estimate"]])
            self.assertEqual(point.get_marker(), "o" if row["reader"] == "astra" else "s")
            self.assertEqual(point.get_color(), "#17607c" if row["reader"] == "astra" else "#a64438")
            self.assertEqual(intervals["interval:" + tag].get_segments()[0][:, 0].tolist(), row["descriptive_ci95"])
        self.assertEqual(ax.get_xlabel(), "Label-rate difference (SH - HS)")
        self.assertFalse(ax.get_title())

    def test_verification_is_read_only(self):
        with patch.object(Path, "write_bytes", side_effect=AssertionError("No writes")), \
             patch.object(Path, "write_text", side_effect=AssertionError("No writes")), \
             patch.object(Path, "mkdir", side_effect=AssertionError("No writes")):
            self.assertTrue(v.verify()["pass"])

    def test_changed_source_or_render_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            shutil.copytree(v.ROOT / v.SOURCE, root / v.SOURCE)
            shutil.copytree(v.ROOT / v.PACKAGE, root / v.PACKAGE)
            for name in (*v.OWN, "paper/main.tex"):
                target = root / name
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(v.ROOT / name, target)
            self.assertTrue(v.verify(root)["pass"])
            image = root / v.PACKAGE / "measurement.pdf"
            image.write_bytes(image.read_bytes() + b"changed")
            with self.assertRaisesRegex(ValueError, "output hash differs"):
                v.verify(root)
            source = root / v.SOURCE / "results.json"
            source.write_bytes(source.read_bytes() + b" ")
            with self.assertRaisesRegex(ValueError, "Original publication output changed"):
                v.verify(root)


if __name__ == "__main__":
    unittest.main()

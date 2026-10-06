"""Check the common estimand, study separation and plotted data in the overview."""
import copy
import tempfile
import unittest
from pathlib import Path

from matplotlib.text import Text
from scripts import verify_model_overview as overview


class ModelOverviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.inputs = overview.load()
        cls.data = overview.derive(cls.inputs)

    def test_complete_inventory_without_pooling(self):
        rows = self.data["rows"]
        self.assertEqual(len(rows), 44)
        self.assertEqual(len({(r["group"], r["label"]) for r in rows}), 13)
        self.assertEqual(len({r["label"] for r in rows}), 11)
        self.assertEqual(self.data["contrast"], "SH-HS")
        self.assertFalse(self.data["scope"]["pooled"])
        self.assertEqual({r["blocks"] for r in rows if r["group"] == "frontier"}, {6})
        self.assertEqual({r["blocks"] for r in rows if r["group"] == "extended"}, {32})

    def test_missing_rubrics_are_not_filled_with_zero(self):
        for row in self.data["rows"]:
            if row["group"] == "original":
                self.assertEqual(row["endpoint"], "paper")
        self.assertEqual({r["endpoint"] for r in self.data["rows"] if r["model"] == "qwen35"},
                         set(overview.ENDPOINTS))

    def test_endpoint_sensitivity_and_estimand(self):
        def value(group, model, endpoint, provider):
            return overview.one(self.data["rows"], group=group, model=model,
                                endpoint=endpoint, provider=provider)["estimate"]
        self.assertAlmostEqual(value("frontier", "opus", "paper", "openai"), 5/6)
        self.assertAlmostEqual(value("frontier", "opus", "inclusive_current_assertion", "openai"), 1/6)
        self.assertAlmostEqual(value("frontier", "opus", "inclusive_current_assertion", "anthropic"), 0)
        self.assertAlmostEqual(value("extended", "opus", "paper", "openai"), .78125)
        self.assertAlmostEqual(value("extended", "opus", "inclusive_current_assertion", "openai"), .21875)
        self.assertAlmostEqual(value("local", "llama", "inclusive_current_assertion", "openai"), .05)
        self.assertAlmostEqual(value("local", "llama", "paper", "openai"), 0)

    def test_original_judges_do_not_become_frontier_judges(self):
        for row in self.data["rows"]:
            readers = overview.ORIGINAL_READERS if row["group"] == "original" else overview.MODERN_READERS
            self.assertEqual(row["reader"], readers[row["provider"]])

    def test_duplicate_cell_rejected(self):
        inputs = copy.deepcopy(self.inputs)
        path = "data/frontier_bilingual_b1/completed_20261002/analysis/analysis.json"
        inputs[path]["cells"].append(copy.deepcopy(inputs[path]["cells"][0]))
        with self.assertRaisesRegex(ValueError, "Missing or duplicate"):
            overview.derive(inputs)

    def test_missing_labels_are_not_negative(self):
        inputs = copy.deepcopy(self.inputs)
        path = "data/frontier_bilingual_b1/completed_20261002/analysis/analysis.json"
        inputs[path]["cells"][0]["missing"] = 1
        with self.assertRaisesRegex(ValueError, "Incomplete cell"):
            overview.derive(inputs)

    def test_tampered_input_rejected_before_parsing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / next(iter(overview.INPUTS))
            path.parent.mkdir(parents=True)
            path.write_bytes(b"wrong bytes")
            with self.assertRaisesRegex(ValueError, "Input hash changed"):
                overview.load(root)

    def test_every_plot_cell_matches_its_bound_value(self):
        fig = overview.make_plot(self.data)
        labels = {a.get_gid()[6:]: a for a in fig.findobj(Text)
                  if a.get_gid() and a.get_gid().startswith("value:")}
        self.assertEqual(len(labels), 52)
        for row in self.data["rows"]:
            key = ":".join(row[k] for k in ("group", "model", "endpoint", "provider"))
            expected = "0.0" if abs(row["estimate"]) < 1e-12 else f"{100*row['estimate']:+.1f}"
            self.assertEqual(labels.pop(key).get_text(), expected)
        self.assertEqual(len(labels), 8)
        self.assertTrue(all(a.get_text() == "n/a" for a in labels.values()))
        fig.clear()

    def test_text_stays_inside_canvas_and_does_not_overlap(self):
        fig = overview.make_plot(self.data)
        fig.canvas.draw()
        renderer = fig.canvas.get_renderer()
        texts = [t for t in fig.findobj(Text) if t.get_visible() and t.get_text()]
        boxes = [t.get_window_extent(renderer) for t in texts]
        for text, box in zip(texts, boxes):
            self.assertGreaterEqual(text.get_fontsize(), 9)
            self.assertGreaterEqual(box.x0, 0)
            self.assertGreaterEqual(box.y0, 0)
            self.assertLessEqual(box.x1, fig.bbox.width)
            self.assertLessEqual(box.y1, fig.bbox.height)
        for i, a in enumerate(boxes):
            for j, b in enumerate(boxes[i+1:], i+1):
                self.assertFalse(a.overlaps(b), f"Overlapping text: {texts[i].get_text()} / {texts[j].get_text()}")
        fig.clear()

    def test_main_text_keeps_point_estimate_and_uncertainty_disclosures(self):
        tex = (overview.ROOT / "paper/model_comparison.tex").read_text()
        caption = tex.split(r"\label{fig:model-overview}")[0].rsplit(r"\caption{", 1)[1]
        caption = " ".join(caption.split())
        for phrase in ("point estimates, not confidence intervals", "Gray cells", "separate studies",
                       "primary in the original", "primary in the later", "floor or ceiling"):
            self.assertIn(phrase, caption)
        self.assertIn(r"Table~\ref{tab:model-comparison}", caption)


if __name__ == "__main__":
    unittest.main()

"""Offline checks for the original-pair rate plot and appendix table."""
import copy
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from scripts import verify_calibration_rates as v


class CalibrationRateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tables = v.load()
        cls.rows = v.derive(cls.tables)

    def test_exact_counts_all_models_and_judges(self):
        expected = {
            "openai": [(0, 20), (0, 20), (3, 10), (15, 19)],
            "anthropic": [(0, 20), (0, 20), (1, 9), (13, 17)],
        }
        self.assertEqual(len(self.rows), 16)
        for judge, pairs in expected.items():
            for (model, _), pair in zip(v.MODELS, pairs):
                selected = [r for r in self.rows if r['judge'] == judge and r['model_key'] == model]
                self.assertEqual([r['positive'] for r in selected], list(pair))
                self.assertTrue(all(r['n'] == 20 for r in selected))

    def test_released_intervals_are_copied_including_boundaries(self):
        for r in self.rows:
            original = next(s for s in self.tables[r['judge']]
                            if s['query_id'] == v.QUERY and s['model_key'] == r['model_key']
                            and s['instruction_cell'] == r['condition'])
            self.assertEqual(r['ci_low'], float(original['ci_low']))
            self.assertEqual(r['ci_high'], float(original['ci_high']))
            if r['rate'] in (0, 1):
                self.assertGreater(r['ci_high'] - r['ci_low'], .16)

    def test_saved_package_and_deterministic_render(self):
        result = v.verify(v.ROOT / v.PACKAGE, rerender=True)
        self.assertTrue(result['pass'])

    def test_pdf_embeds_truetype_fonts(self):
        fonts = subprocess.check_output(['pdffonts', str(v.ROOT / v.PACKAGE / v.PDF)], text=True)
        self.assertIn('TrueType', fonts)
        self.assertNotIn('Type 3', fonts)
        self.assertTrue(all(row.split()[-5] == 'yes' for row in fonts.splitlines()[2:]))

    def test_appendix_table_retains_original_values(self):
        text = v.table_bytes(self.rows).decode()
        self.assertIn('GPT-4o & 0.00 / 0.00 & 1.00 / 1.00 & 1.00 / 1.00', text)
        self.assertIn('Haiku 4.5 & 0.15 / 0.05 & 0.50 / 0.45 & 0.35 / 0.40', text)
        self.assertIn('Sonnet 4.5 & 0.75 / 0.65 & 0.95 / 0.85 & 0.20 / 0.20', text)

    def test_plot_artists_match_all_rates_intervals_labels_and_connectors(self):
        import matplotlib.pyplot as plt
        fig, axes = v.make_plot(self.rows)
        try:
            artists = {a.get_gid(): a for a in fig.findobj() if a.get_gid()}
            self.assertEqual([a.get_title() for a in axes], ['OpenAI judge', 'Anthropic judge'])
            for r in self.rows:
                tag = f"{r['judge']}:{r['model_key']}:{r['condition']}"
                self.assertEqual(list(artists['rate:' + tag].get_xdata()), [r['rate']])
                segment = artists['interval:' + tag].get_segments()[0]
                self.assertEqual(list(segment[:, 0]), [r['ci_low'], r['ci_high']])
                self.assertEqual(artists['label:' + tag].get_text(), f"{r['rate']:.0%}")
            for judge, _ in v.JUDGES:
                for model, _ in v.MODELS:
                    pair = [r['rate'] for r in self.rows if r['judge'] == judge and r['model_key'] == model]
                    self.assertEqual(list(artists[f'connector:{judge}:{model}'].get_xdata()), pair)
        finally:
            plt.close(fig)

    def test_missing_duplicate_or_unexpected_cell_rejected(self):
        for kind in ('missing', 'duplicate', 'unexpected'):
            with self.subTest(kind=kind):
                tables = copy.deepcopy(self.tables)
                i = next(i for i, r in enumerate(tables['openai']) if r['query_id'] == v.QUERY)
                if kind == 'missing':
                    tables['openai'].pop(i)
                elif kind == 'duplicate':
                    tables['openai'].append(tables['openai'][i].copy())
                else:
                    tables['openai'][i]['model_key'] = 'unexpected'
                with self.assertRaisesRegex(ValueError, 'calibration cells'):
                    v.derive(tables)

    def test_missing_labels_noninteger_counts_and_invalid_bounds_rejected(self):
        for field, value in (('n_labeled', '19'), ('positive_rate', '.513'),
                             ('ci_low', 'nan'), ('ci_high', '-1')):
            with self.subTest(field=field):
                tables = copy.deepcopy(self.tables)
                row = next(r for r in tables['openai']
                           if r['query_id'] == v.QUERY and r['positive_rate'] == '0.5')
                row[field] = value
                with self.assertRaises(ValueError):
                    v.derive(tables)

    def test_tampered_source_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name in (v.METHOD, *(v.source_path(j) for j in v.INPUTS)):
                target = root / name
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(v.ROOT / name, target)
            victim = root / v.source_path('openai')
            victim.write_bytes(victim.read_bytes() + b'\n')
            with self.assertRaisesRegex(ValueError, 'Input hash mismatch'):
                v.load(root)

    def test_tampered_outputs_rejected(self):
        for name in ('rates.csv', 'table.tex', v.PDF):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as tmp:
                out = Path(tmp) / 'copy'
                shutil.copytree(v.ROOT / v.PACKAGE, out)
                victim = out / name
                victim.write_bytes(victim.read_bytes() + b'\n')
                with self.assertRaises(ValueError):
                    v.verify(out)


if __name__ == '__main__':
    unittest.main()

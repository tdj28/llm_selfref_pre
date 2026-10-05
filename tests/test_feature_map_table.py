"""Category-by-feature activation table for the six steered features; offline."""
from pathlib import Path
import shutil
import tempfile
import unittest

from scripts import verify_feature_map_table as v


class FeatureMapTableTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.outputs = v.build()

    def test_committed_package_is_current(self):
        for name, data in self.outputs.items():
            self.assertEqual((v.ROOT / v.PACKAGE / name).read_bytes(), data, name)

    def test_values_match_released_records(self):
        values = self.outputs["values.tex"].decode()
        for expected in (r"\FeatureMapTexts}{1,120}", r"\FeatureMapPerCategory}{80}",
                         r"\FeatureMapControls}{60}", r"\FeatureMapBeatControlsWord}{four}",
                         r"\FeatureMapBeatControlIDs}{30032, 30686, 41533 and 58667}"):
            self.assertIn(expected, values)

    def test_each_feature_peak_is_bold(self):
        table = self.outputs["table.tex"].decode()
        for row in ("Deception cover story & 0.48 & \\textbf{2.38}", "Dishonesty confession & 0.24 & 0.28 & 0.00 & 0.41 & \\textbf{6.06}",
                    "Fictional pretending & \\textbf{1.32}", "Roleplay persona & 0.15 & 0.07 & \\textbf{0.11}"):
            self.assertIn(row, table)
        self.assertEqual(table.count("\\textbf{"), len(v.FEATURES))

    def test_tampered_matrix_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / v.MATRIX
            target.parent.mkdir(parents=True)
            shutil.copy(v.ROOT / v.MATRIX, target)
            target.write_bytes(target.read_bytes() + b"\n")
            with self.assertRaisesRegex(ValueError, "Input hash mismatch"):
                v.load_matrix(Path(tmp))


if __name__ == "__main__":
    unittest.main()

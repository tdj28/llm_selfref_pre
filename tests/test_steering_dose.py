"""Plain-unit dose binding for the random-subset steering test; offline."""
from pathlib import Path
import shutil
import tempfile
import unittest

from scripts import verify_steering_dose as v


class SteeringDoseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.values = v.derive(v.load_rows(), v.load_peaks())

    def test_committed_package_is_current(self):
        for name, data in v.build().items():
            self.assertEqual((v.ROOT / v.PACKAGE / name).read_bytes(), data, name)

    def test_values_match_released_rows(self):
        self.assertEqual(self.values["EditMedianPct"], "4.8")
        self.assertEqual(self.values["EditApproxPct"], "5")
        self.assertEqual((self.values["TextChangedLow"], self.values["TextChangedHigh"]), ("86", "88"))
        self.assertEqual((self.values["LabelSameLow"], self.values["LabelSameHigh"]), ("84", "88"))
        self.assertEqual((self.values["PeakShareLow"], self.values["PeakShareHigh"]), ("0.1", "0.3"))
        self.assertGreaterEqual(float(self.values["CosineMin"]), 0.99)

    def test_percentile_interpolates(self):
        self.assertEqual(v.percentile([0, 10], .5), 5)
        self.assertAlmostEqual(v.percentile([1, 2, 3, 4, 5], .1), 1.4)

    def test_tampered_row_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            release = Path(tmp) / v.RELEASE
            release.mkdir(parents=True)
            shutil.copy(v.ROOT / v.RELEASE / "RELEASE_MANIFEST.json", release)
            shutil.copytree(v.ROOT / v.RELEASE / "rows", release / "rows")
            victim = sorted((release / "rows").glob("target-*.json"))[0]
            victim.write_bytes(victim.read_bytes() + b" ")
            with self.assertRaisesRegex(ValueError, "Row hash mismatch"):
                v.load_rows(Path(tmp))


if __name__ == "__main__":
    unittest.main()

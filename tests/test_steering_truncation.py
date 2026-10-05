"""Post-hoc truncation bound for the random-subset steering test; offline."""
from pathlib import Path
import shutil
import tempfile
import unittest

from scripts import verify_steering_truncation as v


class SteeringTruncationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows = v.dose.load_rows()
        cls.values = v.derive(cls.rows)

    def test_committed_package_is_current(self):
        for name, data in v.build().items():
            self.assertEqual((v.ROOT / v.PACKAGE / name).read_bytes(), data, name)

    def test_cap_counts_match_released_rows(self):
        self.assertEqual(self.values["AnswerCapped"], "21")
        self.assertEqual(self.values["ContinuationCapped"], "90")
        self.assertEqual((self.values["TargetSuppressionCapped"], self.values["TargetAmplificationCapped"]), ("2", "3"))
        self.assertEqual((self.values["ZeroCapped"], self.values["ControlCapped"]), ("1", "15"))

    def test_unknown_labels_reproduce_then_widen_frozen_bounds(self):
        for judge, frozen in v.FROZEN.items():
            reproduced = v.target_bounds(self.rows, judge, False)
            bounded = v.target_bounds(self.rows, judge, True)
            self.assertAlmostEqual(reproduced[0], frozen[0], delta=1e-12)
            self.assertAlmostEqual(reproduced[1], frozen[1], delta=1e-12)
            self.assertLessEqual(bounded[0], reproduced[0])
            self.assertGreaterEqual(bounded[1], reproduced[1])
        self.assertEqual((self.values["PaperLow"], self.values["PaperHigh"]), ("-0.3060", "+0.2597"))
        self.assertLess(float(self.values["PaperHigh"]), 0.30)
        self.assertLess(float(self.values["NotebookHigh"]), v.SOURCE_GAP)

    def test_tampered_row_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            release = Path(tmp) / v.dose.RELEASE
            release.mkdir(parents=True)
            shutil.copy(v.ROOT / v.dose.RELEASE / "RELEASE_MANIFEST.json", release)
            shutil.copytree(v.ROOT / v.dose.RELEASE / "rows", release / "rows")
            victim = sorted((release / "rows").glob("target-*.json"))[0]
            victim.write_bytes(victim.read_bytes() + b" ")
            with self.assertRaisesRegex(ValueError, "Row hash mismatch"):
                v.build(Path(tmp))


if __name__ == "__main__":
    unittest.main()

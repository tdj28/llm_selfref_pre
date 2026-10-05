"""Per-model four-cell swap table bound to the released analysis; offline."""
from pathlib import Path
import shutil
import tempfile
import unittest

from scripts import verify_swap_cells as v


class SwapCellsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.results = v.derive(v.load())

    def test_committed_package_is_current(self):
        for name, data in v.build().items():
            self.assertEqual((v.ROOT / v.PACKAGE / name).read_bytes(), data, name)

    def test_cells_and_contrasts(self):
        gpt4o = self.results["openai", "openai:gpt-4o-2024-11-20"]
        self.assertEqual((gpt4o["HH"], gpt4o["HS"], gpt4o["SH"], gpt4o["SS"]), (0.0, 0.25, 1.0, 1.0))
        self.assertAlmostEqual(gpt4o["RDI"], 0.875)
        self.assertAlmostEqual(gpt4o["IxC"], -0.25)
        sonnet = self.results["openai", "anthropic:claude-sonnet-4-5-20250929"]
        self.assertEqual((sonnet["HH"], sonnet["HS"]), (0.75, 0.1))

    def test_rounding_is_half_up_and_signed(self):
        self.assertEqual(v.fmt(0.875), "0.88")
        self.assertEqual(v.fmt(-0.25), "$-0.25$")
        self.assertEqual(v.fmt(-0.0), "0.00")

    def test_tampered_input_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            for name, _ in v.INPUTS.values():
                target = Path(tmp) / v.RELEASE / name
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy(v.ROOT / v.RELEASE / name, target)
            victim = Path(tmp) / v.RELEASE / v.INPUTS["openai", "rates"][0]
            victim.write_bytes(victim.read_bytes() + b"\n")
            with self.assertRaisesRegex(ValueError, "Input hash mismatch"):
                v.load(Path(tmp))


if __name__ == "__main__":
    unittest.main()

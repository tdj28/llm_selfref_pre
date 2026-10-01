"""Focused receipt tamper tests; no source archive, plotting, or API needed."""

import importlib.util
import json
from pathlib import Path
import shutil
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("figure_audit", ROOT / "scripts/verify_figure_values.py")
audit = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(audit)


class FigureValuesTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.receipt = json.loads((ROOT / audit.RECEIPT).read_bytes())
        paths = {audit.RECEIPT} | {s["local_path"] for s in self.receipt["sources"].values() if "local_path" in s}
        for path in paths:
            target = self.root / path
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / path, target)

    def reject(self, message):
        (self.root / audit.RECEIPT).write_bytes(audit.encoded(self.receipt))
        with self.assertRaisesRegex(ValueError, message):
            audit.verify(self.root)

    def test_portable_receipt_passes(self):
        result = audit.verify(self.root)
        self.assertEqual(result["figures"], 5)
        self.assertFalse(result["independent_raw_reanalysis"])

    def test_changed_pin_rejected(self):
        self.receipt["source_commit"] = "0" * 40
        self.reject("Source pin changed")

    def test_omitted_literal_panel_rejected(self):
        self.receipt["figures"]["aggregate_target_and_controls"]["cells"].pop()
        self.reject("Literal panel coverage")

    def test_pooled_scale_rejected(self):
        self.receipt["figures"]["judge_sensitivity"]["scale"] = "pooled"
        self.reject("Scale pooling")

    def test_parser_na_cannot_be_zero(self):
        self.receipt["figures"]["judge_sensitivity"]["cells"][-1]["target_ci95"] = [0, 0, 0]
        self.reject("Parser NA recoded")

    def test_external_specificity_cannot_use_local_controls(self):
        self.receipt["figures"]["judge_sensitivity"]["cells"][2]["specificity_ci95"][0] = -0.08666666666666667
        self.reject("Judge specificity mismatch")

    def test_bad_denominator_rejected(self):
        self.receipt["figures"]["aggregate_target_and_controls"]["cells"][0]["rates"]["suppression"]["n"] = 49
        self.reject("Rate denominator mismatch")

    def test_pair_count_tamper_rejected(self):
        self.receipt["supplemental"]["literal_judge_control_tallies"][1]["roles"][1]["paired_counts_SA"]["10"] += 1
        self.reject("Paired-count denominator")

    def test_calibrated_missing_panel_cannot_be_added(self):
        rows = self.receipt["figures"]["technical_dose_and_matching"]["dose"]
        next(r for r in rows if r["scale"] == "calibrated" and r["role"] == "control_panel_2")["plotted"] = True
        self.reject("Dose coverage")

    def test_interval_tamper_rejected_by_review_digest(self):
        self.receipt["figures"]["causal_factorial_effects"]["cells"][0]["estimate_ci95"][2] += 0.01
        self.reject("Reviewed receipt changed")

    def test_matching_coordinate_tamper_rejected_by_review_digest(self):
        self.receipt["figures"]["technical_dose_and_matching"]["matching"][0]["decoder_norm_ratio"] += 0.01
        self.reject("Reviewed receipt changed")

    def test_diamond_tamper_rejected_by_review_digest(self):
        self.receipt["figures"]["aggregate_target_and_controls"]["paper_diamonds"]["difference"] = 0.79
        self.reject("Reviewed receipt changed")

    def test_figure_bytes_tamper_rejected(self):
        path = self.root / "paper/figures/judge_sensitivity.pdf"
        path.write_bytes(path.read_bytes() + b"tamper")
        with self.assertRaisesRegex(ValueError, "Copied input/figure hash mismatch"):
            audit.verify(self.root)

    def test_local_summary_tamper_rejected(self):
        path = self.root / "evidence/inputs/sae_judges.csv"
        path.write_bytes(path.read_bytes().replace(b"-0.10666666666666665", b"-0.20666666666666665"))
        with self.assertRaisesRegex(ValueError, "Copied input/figure hash mismatch"):
            audit.verify(self.root)


if __name__ == "__main__":
    unittest.main()

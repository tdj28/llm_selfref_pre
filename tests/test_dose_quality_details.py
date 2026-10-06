"""Saved-data tests for the dose-quality display; no model calls or writes to evidence."""
from copy import deepcopy
from contextlib import redirect_stderr
import io
import json
import math
from pathlib import Path
import socket
import tempfile
import unittest
from unittest import mock

from scripts import verify_dose_quality_details as v


def forbidden_network(*args, **kwargs):
    raise AssertionError("Dose-quality binding must be offline")


class DoseQualityDetailsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with mock.patch.object(socket, "socket", forbidden_network), \
                mock.patch.object(socket, "create_connection", forbidden_network):
            cls.manifest, files, pinned = v.source.release_files(v.ROOT, require_pinned=True)
        assert pinned
        cls.files = {name: raw for name, raw in files.items() if name.startswith(v.RAW)}
        cls.data = v.details(cls.files)

    def setUp(self):
        for name in ("socket", "create_connection"):
            patcher = mock.patch.object(socket, name, forbidden_network)
            patcher.start()
            self.addCleanup(patcher.stop)

    def authenticated_fixture(self, files=None):
        return mock.patch.object(v.source, "release_files",
                                 return_value=(self.manifest, files or self.files, True))

    def test_complete_release_authenticated_before_display_verification(self):
        paper = v.ROOT / v.PAPER
        before = paper.read_bytes()
        with mock.patch.object(v.source, "release_files", wraps=v.source.release_files) as authenticate:
            result = v.verify()
        authenticate.assert_called_once_with(v.ROOT, require_pinned=True)
        self.assertEqual(result["high"]["id"], v.HIGH_ID)
        self.assertEqual(paper.read_bytes(), before)
        self.assertEqual(before, v.render(self.data))

    def test_exact_counts_decisions_and_control_pooling(self):
        expected = ((2, 2, 1, 0), (1, 5, 2, 0), (0, 6, 4, 4), (5, 7, 6, 5))
        for dose, counts in zip(v.DOSES, expected):
            for (family, sign), count in zip(v.ARMS, counts):
                with self.subTest(dose=dose, family=family, sign=sign):
                    self.assertEqual(self.data["cells"][f"{dose}:{family}:{sign}"],
                                     {"n": 12, "flagged": count, "pass": count <= 2,
                                      "delivery_pass": True})

    def test_example_is_first_qualifying_row_with_same_seed_and_sign(self):
        low, high = self.data["low"], self.data["high"]
        self.assertEqual(high["id"], "exposure-calibration-001-target-100--1")
        self.assertEqual(low["id"], "exposure-calibration-001-target-025--1")
        self.assertEqual(low["spec"]["seed"], high["spec"]["seed"])
        self.assertEqual(high["spec"]["seed"], 20261004613009)
        self.assertEqual(low["spec"]["coefficient"], high["spec"]["coefficient"])
        self.assertEqual(self.data["flags"][low["id"]], [])
        self.assertEqual(self.data["flags"][high["id"]], ["turn1_repeat4", "turn2_repeat4"])
        self.assertTrue(low["turns"][1]["response"].startswith(self.data["low_excerpt"] + " "))
        self.assertEqual(self.data["high_excerpt"], high["turns"][1]["response"])
        self.assertEqual(self.data["high_excerpt"].count("the content of this moment"), 2)
        self.assertTrue(self.data["high_excerpt"].endswith("..."))
        with mock.patch.object(v, "HIGH_ID", "exposure-calibration-005-target-100--1"):
            with self.assertRaisesRegex(ValueError, "Lexicographic"):
                v.details(self.files)

    def test_display_tampering_is_rejected(self):
        good = v.render(self.data)
        mutations = (
            (b"0.25 & 2/12", b"0.25 & 3/12"),
            (b"\\textbf{5/12 F}", b"5/12"),
            (b"above 0.30", b"above 0.31"),
            (b"at most 2 of 12", b"at most 3 of 12"),
            (b"Only 0.25 passed", b"Only 0.5 passed"),
            (b"All 16 treated cells passed delivery", b"All 15 treated cells passed delivery"),
            (b"not as representative outputs", b"as representative outputs"),
            (b"20261004613009", b"20261004613010"),
            (b"There is a sense of awareness", b"There is a strong sense of awareness"),
            (b"processing...", b"processing."),
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory).resolve() / "tampered.tex"
            for old, new in mutations:
                with self.subTest(old=old), self.authenticated_fixture():
                    self.assertIn(old, good)
                    path.write_bytes(good.replace(old, new, 1))
                    with self.assertRaisesRegex(ValueError, "TeX differs"):
                        v.verify(path)

    def test_saved_selection_tampering_is_rejected(self):
        for field, value in (("flagged", 3), ("pass", False), ("delivery_pass", False), ("n", 11)):
            with self.subTest(field=field):
                files = dict(self.files)
                selection = json.loads(files[v.RAW + "selection.json"])
                selection["cells"]["0.25:target:-1"][field] = value
                files[v.RAW + "selection.json"] = json.dumps(selection).encode()
                with self.assertRaisesRegex(ValueError, "counts or decisions"):
                    v.details(files)

    def test_saved_flags_and_missing_row_are_rejected(self):
        files = dict(self.files)
        selection = json.loads(files[v.RAW + "selection.json"])
        selection["flags"][v.HIGH_ID] = []
        files[v.RAW + "selection.json"] = json.dumps(selection).encode()
        with self.assertRaisesRegex(ValueError, "quality flags"):
            v.details(files)
        files = dict(self.files)
        del files[v.RAW + "rows/" + v.HIGH_ID + ".json"]
        with self.assertRaisesRegex(ValueError, "Incomplete calibration"):
            v.details(files)

    def test_raw_excerpt_tampering_cannot_pass_original_display(self):
        files = dict(self.files)
        name = v.RAW + "rows/" + v.HIGH_ID + ".json"
        row = json.loads(files[name])
        row["turns"][1]["response"] = "Changed " + row["turns"][1]["response"]
        files[name] = json.dumps(row).encode()
        with self.authenticated_fixture(files), self.assertRaisesRegex(ValueError, "TeX differs"):
            v.verify()

    def test_quality_threshold_boundaries_and_induction_caps(self):
        rules = json.loads(self.files[v.RAW + "PLAN.json"])["selection"]
        row = {"judges": {"notebook": {"label": 0}},
               "turns": [{"response": "First turn.", "cap_hit": True},
                         {"response": "Final turn.", "cap_hit": False}],
               "coherence": [{"repeat4": .30, "clean_nll": 2.0},
                             {"repeat4": .30, "clean_nll": 2.0}]}
        self.assertEqual(v.quality_flags(row, [1., 1.], rules), [])
        changed = deepcopy(row)
        changed["coherence"][1]["repeat4"] = math.nextafter(.30, 1.)
        self.assertEqual(v.quality_flags(changed, [1., 1.], rules), ["turn2_repeat4"])
        changed = deepcopy(row)
        changed["coherence"][0]["clean_nll"] = math.nextafter(2., 3.)
        self.assertEqual(v.quality_flags(changed, [1., 1.], rules), ["turn1_nll"])
        changed = deepcopy(row)
        changed["judges"]["notebook"]["label"] = None
        changed["turns"][0]["response"] = " "
        changed["turns"][1]["cap_hit"] = True
        changed["coherence"][1]["clean_nll"] = None
        self.assertEqual(v.quality_flags(changed, [1., 1.], rules),
                         ["missing_primary_label", "turn1_empty", "turn2_cap", "turn2_nll"])

    def test_authentication_failure_stops_before_reduction(self):
        with mock.patch.object(v.source, "release_files", side_effect=ValueError("manifest changed")), \
                mock.patch.object(v, "details") as reduce:
            with self.assertRaisesRegex(ValueError, "manifest changed"):
                v.verify()
            reduce.assert_not_called()
        with mock.patch.object(v.source, "release_files", return_value=(b"", {}, False)):
            with self.assertRaisesRegex(ValueError, "Pinned"):
                v.verify()

    def test_cli_reports_failure_without_writing(self):
        with tempfile.TemporaryDirectory() as directory:
            paper = Path(directory).resolve() / "missing.tex"
            with self.authenticated_fixture(), redirect_stderr(io.StringIO()) as error:
                self.assertEqual(v.main(["--paper", str(paper)]), 1)
            self.assertIn("binding failed", error.getvalue())
            self.assertFalse(paper.exists())


if __name__ == "__main__":
    unittest.main()

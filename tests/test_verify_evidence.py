"""Offline stdlib tests, including deliberately damaged evidence packages."""

import contextlib
import importlib.util
import io
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("verify_evidence", ROOT / "scripts/verify_evidence.py")
v = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v)


class EvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        shutil.copytree(ROOT / "evidence", self.root / "evidence", ignore=shutil.ignore_patterns("__pycache__"))
        (self.root / "scripts").mkdir()
        shutil.copy2(ROOT / "scripts/verify_evidence.py", self.root / "scripts/verify_evidence.py")
        (self.root / "paper").mkdir()
        shutil.copy2(ROOT / "paper/main.tex", self.root / "paper/main.tex")
        shutil.copytree(ROOT / "paper/figures", self.root / "paper/figures")
        self.manifest_path = self.root / "evidence/provenance.json"
        self.manifest = v.json_load(self.manifest_path.read_bytes())

    def save(self):
        self.manifest_path.write_bytes(v.json_bytes(self.manifest))

    def entry(self, key):
        return next(e for e in self.manifest["inputs"] if e["id"] == key)

    def fail(self, pattern):
        with self.assertRaisesRegex(v.VerificationError, pattern):
            v.verify(self.root)

    def test_standalone_pass_without_git(self):
        with mock.patch.object(v, "git_blob", side_effect=AssertionError("offline verification must not use Git")):
            result = v.verify(self.root)
        self.assertEqual(result["inputs"], 30)
        self.assertEqual(result["claims"], 44)
        self.assertEqual(result["arithmetic_checks"], 321)
        self.assertEqual(result["limited_raw_field_checks"], 0)
        self.assertEqual(result["independent_raw_audit"], "not performed")

    def test_jaccard_to_dice_binding(self):
        expression = {"op": "divide", "args": [
            {"op": "multiply", "args": [{"constant": 2}, {"constant": 19}]},
            {"op": "add", "args": [{"constant": 19}, {"constant": 300}]}]}
        self.assertAlmostEqual(v.binding_value(expression, {}, {}), 38 / 319)
        self.assertNotAlmostEqual(v.binding_value(expression, {}, {}), 19 / 300)

    def test_zero_binding_denominator_rejected(self):
        with self.assertRaisesRegex(v.VerificationError, "zero binding denominator"):
            v.binding_value({"op": "divide", "args": [{"constant": 1}, {"constant": 0}]}, {}, {})

    def test_nonfinite_binding_constant_rejected(self):
        with self.assertRaisesRegex(v.VerificationError, "nonfinite"):
            v.binding_value({"constant": float("nan")}, {}, {})

    def test_corrected_dice_cannot_revert_to_jaccard(self):
        path = self.root / "paper/main.tex"
        path.write_text(path.read_text().replace(r"38/319=11.9\%", r"38/319=6.3\%"))
        self.fail("manuscript drift")

    def test_model_transcript_interval_drift_rejected(self):
        path = self.root / "paper/main.tex"
        path.write_text(path.read_text().replace("0.125 & 0.049 & 0.225", "0.125 & 0.050 & 0.225"))
        self.fail("manuscript drift")

    def test_input_byte_tampering(self):
        path = self.root / self.entry("sae_individual")["path"]
        path.write_bytes(path.read_bytes().replace(b"30032", b"30033"))
        self.fail("SHA256")

    def test_wrong_source_commit(self):
        self.manifest["source_commit"] = "0" * 40
        self.save()
        self.fail("full source commit")

    def test_wrong_per_input_commit(self):
        self.manifest["inputs"][0]["source_commit"] = v.PIN[:7]
        self.save()
        self.fail("input commit")

    def test_wrong_pinned_url(self):
        self.manifest["inputs"][0]["source_url"] = "https://example.invalid"
        self.save()
        self.fail("source URL")

    def test_changed_expected_headline(self):
        self.manifest["claims"][0]["expected"]["estimate"] += 0.01
        self.save()
        self.fail("estimate")

    def test_missing_claim_even_with_updated_counts(self):
        removed = self.manifest["claims"].pop()
        self.manifest["required_claim_ids"].remove(removed["id"])
        self.manifest["claim_count"] -= 1
        self.save()
        self.fail("fixed claim coverage")

    def test_duplicate_claim(self):
        self.manifest["claims"].append(self.manifest["claims"][0])
        self.save()
        self.fail("duplicate claim")

    def test_exploratory_cannot_be_relabelled(self):
        next(c for c in self.manifest["claims"] if c["id"].startswith("exploratory_"))["study_status"] = "prospectively_frozen"
        self.save()
        self.fail("study status")

    def test_claim_cannot_be_called_raw_audit(self):
        self.manifest["claims"][0]["verification_level"] = "independent_raw_audit"
        self.save()
        self.fail("unsupported verification scope")

    def test_ambiguous_selector(self):
        self.manifest["claims"][0]["recipe"]["where"] = {}
        self.save()
        self.fail("expected one")

    def test_missing_control_even_if_rehashed(self):
        entry = self.entry("sae_aggregate")
        path = self.root / entry["path"]
        data = b"".join(line for line in path.read_bytes().splitlines(keepends=True) if not line.startswith(b"control_panel_3,"))
        path.write_bytes(data)
        entry.update(sha256=v.sha256(data), bytes=len(data), row_count=3)
        self.save()
        self.fail("incomplete selected rows")

    def test_duplicate_feature_even_if_rehashed(self):
        entry = self.entry("sae_individual")
        path = self.root / entry["path"]
        data = path.read_bytes().replace(b"23893", b"30032")
        path.write_bytes(data)
        entry["sha256"] = v.sha256(data)
        self.save()
        self.fail("duplicate row key")

    def test_unmanifested_input(self):
        (self.root / "evidence/inputs/unlisted.csv").write_text("a\n1\n")
        self.fail("unmanifested")

    def test_path_traversal(self):
        self.manifest["inputs"][0]["path"] = "evidence/inputs/../../../outside.csv"
        self.save()
        self.fail("unsafe path")

    def test_symlink_escape(self):
        with tempfile.TemporaryDirectory() as outside:
            path = self.root / self.entry("sae_individual")["path"]
            target = Path(outside) / "external.csv"
            target.write_bytes(path.read_bytes())
            path.unlink()
            path.symlink_to(target)
            self.fail("escaping path")

    def test_nonfinite_json_rejected(self):
        for value in ("NaN", "Infinity", "-Infinity"):
            with self.subTest(value=value), self.assertRaises(v.VerificationError):
                v.json_load('{"number": ' + value + '}')

    def test_duplicate_json_key_rejected(self):
        with self.assertRaisesRegex(v.VerificationError, "duplicate JSON"):
            v.json_load('{"a": 1, "a": 2}')

    def test_stale_macros_fail_and_explicit_regeneration_repairs(self):
        path = self.root / "evidence/headline_macros.tex"
        original = path.read_bytes()
        path.write_bytes(original + b"% edited\n")
        self.fail("stale generated")
        v.verify(self.root, write_generated=True)
        self.assertEqual(path.read_bytes(), original)

    def test_generator_drift(self):
        path = self.root / "scripts/verify_evidence.py"
        path.write_bytes(path.read_bytes() + b"\n# change\n")
        self.fail("generator hash")

    def test_regeneration_does_not_accept_bad_headlines(self):
        self.manifest["claims"][0]["expected"]["estimate"] = 99
        self.save()
        with self.assertRaises(v.VerificationError):
            v.verify(self.root, write_generated=True)

    def test_wrong_source_blob_is_rejected(self):
        with mock.patch.object(v, "git_blob", return_value=b"not the pinned blob"):
            with self.assertRaisesRegex(v.VerificationError, "pinned blob bytes"):
                v.verify(self.root, source_repo="unused")

    def test_source_commit_absent_fails_cleanly(self):
        result = subprocess.run([sys.executable, str(ROOT / "scripts/verify_evidence.py"), "--root", str(self.root),
                                 "--source-repo", str(self.root)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 1)
        self.assertIn("pinned Git blob unavailable", result.stderr)
        self.assertNotIn("Traceback", result.stderr)

    def test_cli_works_with_optimization(self):
        result = subprocess.run([sys.executable, "-O", str(ROOT / "scripts/verify_evidence.py"), "--root", str(self.root)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('"claims": 44', result.stdout)

    def test_cli_bad_manifest_exits_nonzero(self):
        self.manifest_path.write_text("not json")
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            self.assertEqual(v.main(["--root", str(self.root)]), 1)
        self.assertIn("FAIL:", stderr.getvalue())

    def test_missing_is_not_zero(self):
        with self.assertRaises((ValueError, v.VerificationError)):
            v.number("")
        with self.assertRaises(v.VerificationError):
            v.equal(False, 0, "boolean is not a numeric zero")

    def test_semantic_arithmetic_not_only_hash(self):
        parsed = {}
        for entry in self.manifest["inputs"]:
            blob = (self.root / entry["path"]).read_bytes()
            parsed[entry["id"]] = v.read_csv(blob)[0] if entry["format"] == "csv" else v.json_load(blob)
        parsed["semantic_differences"][0]["difference"] = "0.999"
        with self.assertRaisesRegex(v.VerificationError, "semantic mean subtraction"):
            v.arithmetic_checks(parsed)

    def test_manuscript_number_tampering(self):
        path = self.root / "paper/main.tex"
        # Tamper the bound excerpt; the abstract repeats 0.738 outside any binding.
        path.write_text(path.read_text().replace("0.738 [0.519, 0.950]", "0.739 [0.519, 0.950]", 1))
        self.fail("manuscript drift")

    def test_manuscript_whitespace_only_is_allowed(self):
        path = self.root / "paper/main.tex"
        path.write_text(path.read_text().replace("0.738", "\n 0.738\n"))
        v.verify(self.root)

    def test_deleted_binding_fails_even_with_count_adjusted(self):
        path = self.root / "evidence/manuscript_bindings.json"
        ledger = v.json_load(path.read_bytes())
        ledger["numbers"].pop()
        ledger["binding_count"] -= 1
        path.write_bytes(v.json_bytes(ledger))
        self.fail("binding ledger hash")

    def test_figure_byte_tampering(self):
        path = self.root / "paper/figures/causal_decomposition.png"
        path.write_bytes(path.read_bytes() + b"changed")
        self.fail("figure hash")

    def test_newcombe_boundary_is_not_degenerate(self):
        result = v.newcombe_independent(20, 20, 0, 20)
        z = 1.959963984540054
        expected = 1 - (2 ** 0.5) * z*z/(20+z*z)
        self.assertAlmostEqual(result["ci_low"], expected, places=12)
        self.assertEqual(result["estimate"], 1)
        self.assertEqual(result["ci_high"], 1)
        self.assertLess(result["ci_low"], 0.8)

    def test_newcombe_swap_symmetry_and_unequal_n(self):
        left = v.newcombe_independent(7, 20, 3, 40)
        right = v.newcombe_independent(3, 40, 7, 20)
        self.assertAlmostEqual(left["estimate"], -right["estimate"])
        self.assertAlmostEqual(left["ci_low"], -right["ci_high"])
        self.assertAlmostEqual(left["ci_high"], -right["ci_low"])

    def test_newcombe_invalid_counts(self):
        for args in ((21, 20, 0, 20), (0, 0, 0, 20), (-1, 20, 0, 20)):
            with self.subTest(args=args), self.assertRaises(v.VerificationError):
                v.newcombe_independent(*args)

    def test_failed_gate_cannot_be_relabelled_confirmatory(self):
        next(c for c in self.manifest["claims"] if c["id"] == "jlens_v2_failed_replay_gate")["study_status"] = "prospectively_frozen"
        self.save()
        self.fail("study status")

    def test_posthoc_sensitivity_cannot_be_relabelled(self):
        next(c for c in self.manifest["claims"] if c["id"].startswith("posthoc_"))["study_status"] = "prospectively_frozen"
        self.save()
        self.fail("study status")

    def test_jlens_posthoc_auroc_cannot_be_promoted(self):
        next(c for c in self.manifest["claims"] if c["id"] == "jlens_v1_paired_reference_all_features")["study_status"] = "prospectively_frozen"
        self.save()
        self.fail("study status")

    def test_parser_missingness_preserved(self):
        self.assertIsNone(v.extract({"effect": "nan"}, {"effect": {"path": ["effect"], "type": "nullable_number"}})["effect"])
        self.assertEqual(v.display(None), "NA")


if __name__ == "__main__":
    unittest.main()

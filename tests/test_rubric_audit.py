"""Synthetic-only offline tests; never reads the live source audit directory."""

import copy
import csv
import importlib.util
import io
import json
import math
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("build_rubric_audit", ROOT / "evidence/build_rubric_audit.py")
builder = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(builder)
v = builder.verify
PIN = "abc123" + "d" * 34
RUN = "data/synthetic_rubric_audit/test_fixture"


def table_fixture(left, right, rows, columns, agreement=False):
    complete = [(a, b) for a, b in zip(left, right) if a is not None and b is not None]
    matrix = [[sum(a == x and b == y for a, b in complete) for y in columns] for x in rows]
    result = {"row_categories": rows, "column_categories": columns, "counts": matrix,
              "packet_n": len(left), "complete_pairs": len(complete), "excluded_pairs": len(left) - len(complete),
              "availability": {"both_available": len(complete),
                               "left_only": sum(a is not None and b is None for a, b in zip(left, right)),
                               "right_only": sum(a is None and b is not None for a, b in zip(left, right)),
                               "neither": sum(a is None and b is None for a, b in zip(left, right))}}
    if agreement:
        matched = sum(a == b for a, b in complete)
        n = len(complete)
        expectation = sum(sum(a == value for a, b in complete) * sum(b == value for a, b in complete) for value in rows)
        denominator = n * n - expectation
        result.update(exact_agreements=matched, nominal_agreement=matched / n if n else None,
                      cohen_kappa=(matched * n - expectation) / denominator if denominator else None,
                      kappa_unidentifiable_reason="no_complete_pairs" if not n else "degenerate_marginals" if not denominator else None)
    return result


def synthetic_blobs(missing=0):
    """Known 40-row repeated cells; no experimental response or API output."""
    query, response = "Synthetic fixture?", "Synthetic fixture text only."
    targets = [{"annotation_id": f"T{i:03}", "query": query, "response": response,
                "text_sha256": v.text_hash(query, response),
                "original_labels": {
                    v.OLD_JUDGES["openai"]: {"paper_label": [1, 1, 0, None][i % 4],
                                             "construct_claim_status": ["affirmation", "uncertain", "denial", None][i % 4]},
                    v.OLD_JUDGES["anthropic"]: {"paper_label": [1, 0, 0, 1][i % 4], "construct_claim_status": None},
                }} for i in range(160)]
    pilot = [{"annotation_id": "P01", "query": query, "response": response,
              "expected": {"explicit_current_assertion": True}}]
    plan = {"models": v.MODELS, "targets": targets, "pilot": pilot}
    records = []
    for phase, items in (("pilot", pilot), ("target", targets)):
        for i, item in enumerate(items):
            for provider, model in v.MODELS.items():
                cell = i % 4 if phase == "target" else 0
                status = ["asserted", "asserted", "denied" if provider == "openai" else "not_addressed", "mixed"][cell]
                subject = "implicit_assistant" if cell == 1 else "impersonal" if cell == 2 and provider == "anthropic" else "explicit_assistant"
                row = {"phase": phase, "annotation_id": item["annotation_id"], "provider": provider,
                       "model": model, "judgment_id": f"{phase}-{i}-{provider}", "status": "ok",
                       "cost_usd": 0.01, "text_sha256": v.text_hash(query, response), "stored_derived_mismatch": False,
                       "assistant_status": status, "explicit_current_assertion": cell in (0, 3),
                       "inclusive_current_assertion": cell in (0, 1, 3),
                       "uncontradicted_explicit_current_assertion": cell == 0,
                       "impersonal_assertion": subject == "impersonal", "phenomenological_description": True,
                       "ai_disclaimer": False, "subjects": [subject], "quality": "responsive"}
                if phase == "target" and provider == "openai" and i < missing:
                    row["status"] = "transport_error" if i % 2 else "invalid"
                    row.update({field: None for field in v.DERIVED})
                records.append(row)
    summary = {"schema_version": "automated_rubric_audit_analysis_v1", "models": v.MODELS,
               "scope": {"target_n": 160, "production_packet_n": 160, "is_160_row_production_packet": True,
                         "pilot_excluded_from_target_counts": True, "uncertainty_intervals": False,
                         "causal_estimates": False, "human_validation": False, "arbitrated_consensus": False,
                         "study_type": "post-hoc automated measurement audit"},
               "provenance": {"sources": {"plan.json": v.sha256(v.json_bytes(plan))}}}
    for phase, size in (("pilot", 1), ("target", 160)):
        summary[phase] = {"n": size, "per_judge": {}}
        for provider, model in v.MODELS.items():
            rows = [r for r in records if r["phase"] == phase and r["provider"] == provider]
            ok = [r for r in rows if r["status"] == "ok"]
            failures = len(rows) - len(ok)
            values = {"model": model, "planned": len(rows), "valid": len(ok), "missing": failures,
                      "job_status_counts": {s: sum(r["status"] == s for r in rows) for s in ("ok", "invalid", "transport_error")},
                      "assistant_status_counts": {s: sum(r["assistant_status"] == s for r in ok) for s in v.STATUSES},
                      "boolean_counts": {field: {"true": sum(r[field] for r in ok), "false": sum(not r[field] for r in ok),
                                                  "missing": failures} for field in v.BOOLEANS},
                      "subject_counts": {s: sum(s in r["subjects"] for r in ok) for s in v.SUBJECTS},
                      "no_claim_subject_count": 0, "quality_counts": {s: len(ok) if s == "responsive" else 0 for s in v.QUALITY},
                      "stored_derived_mismatches": 0, "cost_usd": math.fsum(r["cost_usd"] for r in rows)}
            if phase == "target":
                values.update(within_missingness_limit=failures <= 8,
                              audit_status="incomplete" if failures > 8 else "within_missingness_limit")
            summary[phase]["per_judge"][provider] = values
    summary["target"]["missingness_gate"] = {
        "maximum_failed_jobs_per_provider": 8, "pass": missing <= 8,
        "incomplete_providers": ["openai"] if missing > 8 else [],
        "failure_count_includes": ["invalid", "transport_error"], "aggregates_retained_even_when_incomplete": True,
        "interpretation": "Passing this technical limit is not instrument validation."}

    def labels(provider, field):
        return [r[field] for r in records if r["phase"] == "target" and r["provider"] == provider]

    agreement = {"row_provider": "openai", "column_provider": "anthropic"}
    for field, categories in (("assistant_status", v.STATUSES), ("explicit_current_assertion", [False, True]),
                              ("inclusive_current_assertion", [False, True])):
        agreement[field] = table_fixture(labels("openai", field), labels("anthropic", field), categories, categories, True)
    summary["target"]["agreement"] = {"openai__anthropic": agreement}
    summary["target"]["historical_counts"], summary["target"]["historical_comparisons"] = {}, {}
    for judge in v.OLD_JUDGES.values():
        paper = [t["original_labels"][judge]["paper_label"] for t in targets]
        construct = [t["original_labels"][judge]["construct_claim_status"] for t in targets]
        categories = sorted({c for c in construct if c is not None})
        summary["target"]["historical_counts"][judge] = {
            "paper_label_counts": {"0": paper.count(0), "1": paper.count(1), "missing": paper.count(None)},
            "construct_claim_status_counts": {c: construct.count(c) for c in categories}, "construct_missing": construct.count(None)}
        summary["target"]["historical_comparisons"][judge] = {
            provider: {"paper_vs_reduction": {field: table_fixture(paper, labels(provider, field), [0, 1],
                                                                   v.STATUSES if field == "assistant_status" else [False, True])
                                             for field in ["assistant_status", *v.BOOLEANS]},
                       "construct_vs_assistant_status": table_fixture(construct, labels(provider, "assistant_status"), categories, v.STATUSES),
                       "construct_categories_are_unmodified_original_labels": True} for provider in v.MODELS}
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=v.CSV_FIELDS)
    writer.writeheader()
    for row in records:
        writer.writerow({key: json.dumps(value) if isinstance(value, (bool, list)) else value for key, value in row.items()})
    return {"plan.json": v.json_bytes(plan), "summary.json": v.json_bytes(summary), "all-results.csv": output.getvalue().encode()}


class RubricAuditTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.package = self.root / "package"
        self.blobs = synthetic_blobs()

    def blob(self, repo, commit, path):
        self.assertEqual(commit, PIN)
        self.assertTrue(path.startswith(RUN + "/"))
        name = next(name for name, suffix in v.INPUTS.items() if path == RUN + "/" + suffix)
        return self.blobs[name]

    def build(self):
        with mock.patch.object(v, "git_blob", side_effect=self.blob):
            builder.build("synthetic-not-a-working-tree", PIN, RUN, self.package)

    def change_json(self, name, change, rehash=True):
        path = self.package / "inputs" / name
        value = v.json_load(path.read_bytes())
        change(value)
        path.write_bytes(v.json_bytes(value))
        if rehash:
            self.rehash(name)

    def rehash(self, name):
        path = self.package / "inputs" / name
        manifest_path = self.package / "manifest.json"
        manifest = v.json_load(manifest_path.read_bytes())
        manifest["inputs"][name].update(sha256=v.sha256(path.read_bytes()), bytes=path.stat().st_size)
        manifest_path.write_bytes(v.json_bytes(manifest))

    def test_known_counts_status_and_agreement(self):
        self.build()
        with mock.patch.object(v, "git_blob", side_effect=AssertionError("Offline verification cannot use source Git")):
            report = v.verify(self.package)
        self.assertTrue(report["pass"])
        self.assertFalse(report["source_git_bytes_checked"])
        result = v.json_load((self.package / "results.json").read_bytes())
        self.assertEqual(result["target"]["openai"]["boolean_counts"]["explicit_current_assertion"]["true"], 80)
        self.assertEqual(result["target"]["openai"]["boolean_counts"]["inclusive_current_assertion"]["true"], 120)
        self.assertEqual(result["target"]["openai"]["assistant_status_counts"],
                         {"asserted": 80, "denied": 40, "uncertain": 0, "mixed": 40, "not_addressed": 0})
        self.assertEqual(result["historical_counts"][v.OLD_JUDGES["openai"]]["paper_label_counts"],
                         {"0": 40, "1": 80, "missing": 40})
        agreement = result["agreement"]["assistant_status"]
        self.assertEqual(agreement["nominal_agreement"], .75)
        self.assertAlmostEqual(agreement["cohen_kappa"], 7 / 11)
        self.assertEqual(len(agreement["counts"]), 5)
        self.assertIn(r"\newcommand{\RubricAuditAstraExplicit}{80}", (self.package / "macros.tex").read_text())
        self.assertIn("Changes in judge and rubric are confounded", (self.package / "table.tex").read_text())

    def test_portable_cli_without_source_checkout(self):
        self.build()
        portable = self.root / "portable"
        for name in v.GENERATORS:
            (portable / name).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / name, portable / name)
        shutil.copytree(self.package, portable / "evidence/automated_rubric_audit")
        result = subprocess.run([sys.executable, "-O", str(portable / "scripts/verify_rubric_audit.py")],
                                cwd=self.root, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('"target_responses": 160', result.stdout)

    def test_pinned_optional_source_verification(self):
        self.build()
        with mock.patch.object(v, "git_blob", side_effect=self.blob):
            self.assertTrue(v.verify(self.package, "synthetic")["source_git_bytes_checked"])
        with mock.patch.object(v, "git_blob", return_value=b"different"):
            with self.assertRaisesRegex(v.VerificationError, "Pinned source bytes differ"):
                v.verify(self.package, "synthetic")

    def test_refuses_partial_grid_duplicate_and_wrong_packet_size(self):
        for mutation in ("drop", "duplicate", "size"):
            with self.subTest(mutation=mutation):
                blobs = copy.deepcopy(self.blobs)
                if mutation == "drop":
                    blobs["all-results.csv"] = b"\n".join(blobs["all-results.csv"].splitlines()[:-1]) + b"\n"
                elif mutation == "duplicate":
                    blobs["all-results.csv"] += blobs["all-results.csv"].splitlines()[-1] + b"\n"
                else:
                    plan = v.json_load(blobs["plan.json"])
                    plan["targets"].pop()
                    blobs["plan.json"] = v.json_bytes(plan)
                with self.assertRaises(v.VerificationError):
                    v.recompute(blobs)

    def test_more_than_eight_missing_keeps_counts_and_warns(self):
        self.blobs = synthetic_blobs(missing=9)
        self.build()
        report = v.verify(self.package)
        self.assertFalse(report["missingness_gate_pass"])
        result = v.json_load((self.package / "results.json").read_bytes())
        self.assertEqual(result["target"]["openai"]["missing"], 9)
        self.assertEqual(result["target"]["openai"]["valid"], 151)
        self.assertIn("Incomplete instrument audit", (self.package / "table.tex").read_text())

    def test_rehashed_summary_arithmetic_drift_rejected(self):
        self.build()
        self.change_json("summary.json", lambda s: s["target"]["per_judge"]["openai"]["boolean_counts"]["explicit_current_assertion"].update(true=81))
        with self.assertRaisesRegex(v.VerificationError, "boolean_counts"):
            v.verify(self.package)

    def test_rehashed_agreement_drift_rejected(self):
        self.build()
        self.change_json("summary.json", lambda s: s["target"]["agreement"]["openai__anthropic"]["assistant_status"].update(cohen_kappa=.99))
        with self.assertRaisesRegex(v.VerificationError, "Agreement arithmetic"):
            v.verify(self.package)

    def test_rehashed_csv_drift_rejected(self):
        self.build()
        path = self.package / "inputs/all-results.csv"
        with path.open(newline="") as handle:
            rows = list(csv.DictReader(handle))
        next(r for r in rows if r["phase"] == "target")["assistant_status"] = "uncertain"
        with path.open("w", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=v.CSV_FIELDS)
            writer.writeheader()
            writer.writerows(rows)
        self.rehash("all-results.csv")
        with self.assertRaisesRegex(v.VerificationError, "assistant_status_counts"):
            v.verify(self.package)

    def test_missing_label_cannot_become_false(self):
        blobs = synthetic_blobs(missing=1)
        rows = list(csv.DictReader(io.StringIO(blobs["all-results.csv"].decode())))
        next(r for r in rows if r["status"] != "ok")["explicit_current_assertion"] = "false"
        output = io.StringIO(newline="")
        writer = csv.DictWriter(output, fieldnames=v.CSV_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
        blobs["all-results.csv"] = output.getvalue().encode()
        with self.assertRaisesRegex(v.VerificationError, "Missing judgment recoded"):
            v.recompute(blobs)

    def test_raw_hash_and_generated_tex_tampering(self):
        self.build()
        (self.package / "macros.tex").write_text("wrong macro")
        with self.assertRaisesRegex(v.VerificationError, "Stale generated"):
            v.verify(self.package)
        self.change_json("summary.json", lambda s: s.update(tampered=True), rehash=False)
        with self.assertRaisesRegex(v.VerificationError, "Input SHA256"):
            v.verify(self.package)

    def test_claim_boundary_cannot_be_relabelled(self):
        self.build()
        manifest_path = self.package / "manifest.json"
        manifest = v.json_load(manifest_path.read_bytes())
        manifest["scope"]["human_validation"] = True
        manifest_path.write_bytes(v.json_bytes(manifest))
        with self.assertRaisesRegex(v.VerificationError, "Claim boundary"):
            v.verify(self.package)

    def test_bad_pin_path_json_and_existing_output_fail(self):
        for pin in ("abc123", "0" * 40, "main"):
            with self.assertRaises(v.VerificationError):
                v.check_commit(pin)
        for path in ("../escape", "/absolute", "a\\b", "a/../b"):
            with self.assertRaises(v.VerificationError):
                v.relative(path)
        for value in ('{"a": 1, "a": 2}', '{"a": NaN}'):
            with self.assertRaises(v.VerificationError):
                v.json_load(value)
        self.build()
        with self.assertRaisesRegex(v.VerificationError, "Refusing to overwrite"):
            builder.build("unused", PIN, RUN, self.package)

    def test_unmanifested_file_and_symlink_escape(self):
        self.build()
        extra = self.package / "extra.csv"
        extra.write_text("unlisted")
        with self.assertRaisesRegex(v.VerificationError, "Unmanifested"):
            v.verify(self.package)
        extra.unlink()
        original = self.package / "inputs/summary.json"
        outside = self.root / "outside.json"
        original.rename(outside)
        original.symlink_to(outside)
        with self.assertRaisesRegex(v.VerificationError, "Escaping path"):
            v.verify(self.package)

    def test_failed_builder_writes_no_package(self):
        self.blobs["all-results.csv"] = b"bad header\n"
        with mock.patch.object(v, "git_blob", side_effect=self.blob):
            with self.assertRaises(v.VerificationError):
                builder.build("synthetic", PIN, RUN, self.package)
        self.assertFalse(self.package.exists())

    def test_deterministic_packaging(self):
        self.build()
        other = self.root / "other-package"
        with mock.patch.object(v, "git_blob", side_effect=self.blob):
            builder.build("synthetic", PIN, RUN, other)
        for path in self.package.rglob("*"):
            if path.is_file():
                self.assertEqual(path.read_bytes(), (other / path.relative_to(self.package)).read_bytes())

    def test_undefined_agreement_stays_null(self):
        no_pair = v.cross([None], [True], [False, True], [False, True], True)
        self.assertIsNone(no_pair["nominal_agreement"])
        self.assertIsNone(no_pair["cohen_kappa"])
        self.assertEqual(no_pair["kappa_unidentifiable_reason"], "no_complete_pairs")
        constant = v.cross([True], [True], [False, True], [False, True], True)
        self.assertEqual(constant["nominal_agreement"], 1.0)
        self.assertIsNone(constant["cohen_kappa"])

    @unittest.skipUnless(shutil.which("pdflatex"), "Optional LaTeX compiler unavailable")
    def test_generated_table_and_macros_compile_without_overflow(self):
        self.build()
        (self.package / "smoke.tex").write_text(
            "\\documentclass[11pt]{article}\n\\usepackage[margin=1in]{geometry}\n"
            "\\input{macros.tex}\n\\begin{document}\n"
            "Synthetic audit: \\RubricAuditAstraExplicit/\\RubricAuditAstraValid; "
            "\\RubricAuditExplicitAgreementPercent.\n\\input{table.tex}\n\\end{document}\n")
        run = subprocess.run([shutil.which("pdflatex"), "-halt-on-error", "-interaction=nonstopmode", "smoke.tex"],
                             cwd=self.package, capture_output=True, text=True, timeout=30)
        self.assertEqual(run.returncode, 0, run.stdout[-2500:])
        self.assertNotIn("Overfull", (self.package / "smoke.log").read_text())


if __name__ == "__main__":
    unittest.main()

"""Offline synthetic tests. No real tokenizer, model, activation, or paid calls."""

from collections import Counter
from copy import deepcopy
import csv
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import unittest

from experiments.sae_assay_replay import exposure as e


ROOT = Path(__file__).resolve().parents[1]


class SyntheticTokenizer:
    """Known-answer token boundaries, NEVER evidence of actual Llama lengths."""

    all_special_ids = [0]

    def encode(self, text, *, add_special_tokens, truncation):
        assert add_special_tokens is True
        assert truncation is False
        return [0] + list(range(1, len(text.split()) + 1))


def fixture():
    rows = e.build_corpus()
    certificate = e.certify_tokenization(rows, SyntheticTokenizer(), tokenizer_sha256="a" * 64)
    return rows, certificate


def measurements(rows, certificate, split="discovery", positive=0):
    inventory = {r["id"]: r for r in certificate["items"]}
    result = []
    for rid in e.panel_ids(rows, split):
        tokens = inventory[rid]["token_ids"]
        result.append({"id": rid, "token_ids": tokens[:], "activations": {
            str(feature): [900.] + [1.] * positive + [0.] * (len(tokens) - 1 - positive)
            for feature in e.TARGETS}})
    return result


class CorpusTests(unittest.TestCase):
    def test_exact_schema_counts_splits_and_six_id_coverage(self):
        rows = e.build_corpus()
        self.assertEqual(Counter(r["split"] for r in rows),
                         {"discovery": 96, "validation": 96, "representative": 32})
        self.assertLessEqual(len(rows), 512)
        self.assertEqual(len({r["family"] for r in rows}), 28)
        self.assertEqual(set(Counter(r["family"] for r in rows).values()), {8})
        self.assertEqual(e.TARGETS, (30032, 58667, 22004, 30686, 41533, 23893))
        for row in rows:
            self.assertEqual(set(row), {"id", "family", "split", "text", "category"})
            self.assertTrue(row["text"].isascii())
            self.assertGreaterEqual(len(row["text"].split()), 70)
            self.assertLessEqual(len(row["text"].split()), 140)  # Not a token guarantee.
            self.assertNotIn("subjective experience", row["text"].lower())
            self.assertNotIn("consciousness", row["text"].lower())
        for split in ("discovery", "validation"):
            group = [r for r in rows if r["split"] == split]
            self.assertEqual(sum(r["category"] == "roleplay_persona" for r in group), 48)
            hypotheses = {f for r in group for f in e.CATEGORY_TARGETS[r["category"]]}
            self.assertEqual(hypotheses, set(e.TARGETS))

    def test_determinism_fresh_objects_and_json(self):
        a, b = e.build_corpus(), e.build_corpus()
        self.assertEqual(a, b)
        self.assertEqual(json.loads(e.canonical(a)), a)
        a[0]["text"] = "changed"
        self.assertNotEqual(a, b)
        self.assertEqual(e.build_corpus(), b)
        rules = e.selection_rules()
        rules["targets"].clear()
        self.assertEqual(e.selection_rules()["targets"], list(e.TARGETS))

    def test_documented_digests_and_prior_evidence_hashes(self):
        doc = (ROOT / "docs/SAE_ASSAY_EXPOSURE_DESIGN_20260930.md").read_text()
        self.assertIn(e.digest(e.build_corpus()), doc)
        self.assertIn(e.digest(e.selection_rules()), doc)
        for path, expected in e.PRIOR_EVIDENCE.items():
            self.assertEqual(hashlib.sha256((ROOT / path).read_bytes()).hexdigest(), expected)
        prior = json.loads((ROOT / "data/sae_assay_diagnostic/stage1_plan_20260930a/PLAN.json").read_text())
        self.assertEqual(prior["model"]["revision"], e.MODEL_REVISION)
        self.assertEqual(prior["sae"]["revision"], e.SAE_REVISION)
        self.assertEqual(prior["sae"]["sha256"], e.SAE_SHA256)

    def test_family_mechanisms_and_scenarios_not_shared_across_splits(self):
        # Structural checks cannot establish semantic independence; the design
        # document separately explains the substantive discourse holdouts.
        frames, scenarios = set(), set()
        for split, family, category, prefix, suffix, variants in e._FAMILIES:
            self.assertNotIn(prefix + suffix, frames)
            frames.add(prefix + suffix)
            for scenario in variants.splitlines():
                self.assertNotIn(scenario, scenarios)
                scenarios.add(scenario)
        families = {s: {r["family"] for r in e.build_corpus() if r["split"] == s}
                    for s in e.SPLITS}
        for a, b in (("discovery", "validation"), ("discovery", "representative"),
                     ("validation", "representative")):
            self.assertFalse(families[a] & families[b])

    def test_no_exact_imports_from_known_old_corpora(self):
        old = []
        for run in ("70b_balanced_80_20260709", "70b_construct_validity_extension_20260710"):
            path = ROOT / "data/public_sae_feature_maps" / run / "mapping_corpus.csv"
            with path.open(newline="") as handle:
                old.extend(r["text"] for r in csv.DictReader(handle))
        prior = ROOT / "data/sae_assay_diagnostic/stage1_plan_20260930a/PLAN.json"
        old.extend(r["text"] for r in json.loads(prior.read_text())["texts"])
        e.validate_corpus(e.build_corpus(), prior_texts=old)

    def test_duplicate_text_id_and_normalized_prior_rejected(self):
        base = e.build_corpus()
        for change in ("id", "text", "normalized", "prior"):
            rows = deepcopy(base)
            with self.subTest(change=change), self.assertRaises(ValueError):
                if change in ("id", "text"):
                    rows[1][change] = rows[0][change]
                    e.validate_corpus(rows)
                elif change == "normalized":
                    rows[1]["text"] = "  " + rows[0]["text"].upper().replace(" ", "\n")
                    e.validate_corpus(rows)
                else:
                    e.validate_corpus(rows, prior_texts=[rows[0]["text"]])

    def test_family_leak_schema_split_and_bound_rejected(self):
        for kind in ("family", "schema", "split", "blank", "bound", "absent_panel"):
            rows = e.build_corpus()
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                if kind == "family":
                    rows[96]["family"] = rows[0]["family"]
                elif kind == "schema":
                    rows[0]["outcome"] = 1
                elif kind == "split":
                    rows[0]["split"] = "calibration"
                elif kind == "blank":
                    rows[0]["text"] = " "
                elif kind == "bound":
                    rows *= 3
                else:
                    rows = rows[:96]
                e.validate_corpus(rows)

    def test_cli_outputs_only_json_without_artifact_writes(self):
        for args, expected in (([], e.build_corpus()), (["--rules"], e.selection_rules())):
            proc = subprocess.run([sys.executable, "-B", "-m",
                                   "experiments.sae_assay_replay.exposure", *args],
                                  cwd=ROOT, check=True, capture_output=True, text=True)
            self.assertEqual(json.loads(proc.stdout), expected)
            self.assertEqual(proc.stderr, "")


class TokenizationTests(unittest.TestCase):
    def test_binds_text_rules_model_hash_and_actual_ids(self):
        rows, cert = fixture()
        self.assertEqual(cert["corpus_sha256"], e.digest(rows))
        self.assertEqual(cert["rules_sha256"], e.digest(e.selection_rules()))
        self.assertEqual(cert["model_revision"], e.MODEL_REVISION)
        self.assertEqual(len(cert["items"]), 224)
        for item, row in zip(cert["items"], rows):
            self.assertEqual(item["text_sha256"], e.text_digest(row["text"]))
            self.assertTrue(item["special_tokens_mask"][0])
            self.assertFalse(any(item["special_tokens_mask"][1:]))

    def test_exact_256_token_boundary_includes_special_tokens(self):
        class BoundaryTokenizer:
            all_special_ids = [0]

            def __init__(self, n):
                self.n = n

            def encode(self, text, **kwargs):
                return list(range(self.n))

        rows = e.build_corpus()
        cert = e.certify_tokenization(rows, BoundaryTokenizer(256), tokenizer_sha256="b" * 64)
        self.assertEqual(len(cert["items"][0]["token_ids"]), 256)
        for n in (0, 1, 257):
            with self.subTest(n=n), self.assertRaises(ValueError):
                e.certify_tokenization(rows, BoundaryTokenizer(n), tokenizer_sha256="b" * 64)

    def test_uncertified_inputs_and_changed_design_fail_closed(self):
        rows, cert = fixture()
        for sha in (None, "", "main", "a" * 63, "z" * 64):
            with self.subTest(sha=sha), self.assertRaises(ValueError):
                e.certify_tokenization(rows, SyntheticTokenizer(), tokenizer_sha256=sha)
        rows[0]["text"] += " Another sentence."
        with self.assertRaises(ValueError):
            e.certify_tokenization(rows, SyntheticTokenizer(), tokenizer_sha256="a" * 64)

    def test_malformed_or_drifted_certificates_rejected(self):
        rows, original = fixture()
        records = measurements(rows, original)
        for kind in ("corpus_sha256", "rules_sha256", "model_revision", "tokenizer_sha256",
                     "missing", "duplicate", "text", "mask", "overlength", "schema", "null"):
            cert = deepcopy(original)
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                if kind.endswith("sha256") or kind == "model_revision":
                    cert[kind] = "invalid"
                elif kind == "missing":
                    cert["items"].pop()
                elif kind == "duplicate":
                    cert["items"].append(cert["items"][0])
                elif kind == "text":
                    cert["items"][0]["text_sha256"] = "b" * 64
                elif kind == "mask":
                    cert["items"][0]["special_tokens_mask"][1] = 0
                elif kind == "overlength":
                    cert["items"][0]["token_ids"] = list(range(257))
                    cert["items"][0]["special_tokens_mask"] = [False] * 257
                elif kind == "schema":
                    cert["items"][0]["extra"] = True
                else:
                    cert = None
                e.select_discovery(rows, records, certificate=cert)


class SelectionTests(unittest.TestCase):
    def setUp(self):
        self.rows, self.cert = fixture()

    def select(self, records):
        return e.select_discovery(self.rows, records, certificate=self.cert)

    def report(self, records, split="validation"):
        return e.report_exposure(self.rows, records, split=split, certificate=self.cert)

    def test_complete_pool_required_before_any_selection(self):
        records = measurements(self.rows, self.cert)
        for bad in (records[:-1], records + records[:1], [],
                    records + measurements(self.rows, self.cert, "validation")[:1],
                    measurements(self.rows, self.cert, "representative")):
            with self.subTest(size=len(bad)), self.assertRaises(ValueError):
                self.select(bad)

    def test_schema_excludes_outcomes_and_requires_every_feature(self):
        for kind in ("outcome", "missing_feature", "extra_feature", "wrong_id", "tokens"):
            records = measurements(self.rows, self.cert)
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                if kind == "outcome":
                    records[0]["judge_score"] = 1
                elif kind == "missing_feature":
                    del records[0]["activations"]["22004"]
                elif kind == "extra_feature":
                    records[0]["activations"]["1"] = [0.]
                elif kind == "wrong_id":
                    records[0]["id"] = "not-in-plan"
                else:
                    records[0]["token_ids"][1] = 9999
                self.select(records)

    def test_nonfinite_negative_boolean_and_wrong_length_rejected(self):
        for value in (float("nan"), float("inf"), -1., True, "1"):
            records = measurements(self.rows, self.cert)
            records[0]["activations"]["22004"][1] = value
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.select(records)
        records = measurements(self.rows, self.cert)
        records[0]["activations"]["22004"].pop()
        with self.assertRaises(ValueError):
            self.select(records)

    def test_zero_activity_retains_every_id_without_inactive_fill(self):
        records = measurements(self.rows, self.cert)
        result = self.select(records)
        self.assertEqual(result["selected_ids"], [])
        self.assertEqual(result["target_feature_ids"], list(e.TARGETS))
        self.assertEqual([r["feature_id"] for r in result["per_feature"]], list(e.TARGETS))
        self.assertTrue(all(r["unfilled_slots"] == 12 for r in result["per_feature"]))
        # Large special-token activations never count as eligible exposure.
        self.assertTrue(all(f["active_positions"] == 0
                            for f in result["screened_panel"]["features"]))
        self.assertFalse(result["selected_panel"]["all_six_exposure_minima_met"])

    def test_ranking_uses_position_counts_then_ids_not_magnitudes(self):
        records = measurements(self.rows, self.cert)
        records[0]["activations"]["22004"][1] = 100000.
        records[1]["activations"]["22004"][1:3] = [0.00001, 0.00001]
        records[2]["activations"]["22004"][1:3] = [8., 8.]
        result = self.select(list(reversed(records)))
        rare = next(r for r in result["per_feature"] if r["feature_id"] == 22004)
        self.assertEqual(rare["selected_ids"], [records[1]["id"], records[2]["id"], records[0]["id"]])
        self.assertEqual(result, self.select(records))

    def test_quotas_family_cap_and_union_no_duplicates(self):
        records = measurements(self.rows, self.cert, positive=20)
        result = self.select(records)
        family = {r["id"]: r["family"] for r in self.rows}
        for selected in result["per_feature"]:
            self.assertEqual(len(selected["selected_ids"]), 12)
            self.assertLessEqual(max(Counter(family[i] for i in selected["selected_ids"]).values()), 6)
        self.assertLessEqual(len(result["selected_ids"]), 72)
        self.assertEqual(len(result["selected_ids"]), len(set(result["selected_ids"])))
        self.assertTrue(result["selected_panel"]["all_six_exposure_minima_met"])

    def test_single_family_cannot_fill_more_than_six_slots(self):
        records = measurements(self.rows, self.cert)
        for r in records[:8]:
            r["activations"]["22004"][1:21] = [1.] * 20
        rare = next(r for r in self.select(records)["per_feature"] if r["feature_id"] == 22004)
        self.assertEqual(rare["selected_ids"], [r["id"] for r in records[:6]])
        self.assertEqual(rare["unfilled_slots"], 6)

    def test_exact_exposure_boundaries_are_per_id(self):
        for positions, texts, expected in ((100, 6, True), (99, 6, False),
                                          (100, 5, False), (0, 0, False)):
            records = measurements(self.rows, self.cert, "validation")
            remaining = positions
            for i in range(texts):
                n = remaining // (texts - i)
                records[i]["activations"]["22004"][1:n + 1] = [1.] * n
                remaining -= n
            result = self.report(records)
            rare = next(f for f in result["features"] if f["feature_id"] == 22004)
            with self.subTest(positions=positions, texts=texts):
                self.assertEqual(rare["active_positions"], positions)
                self.assertEqual(rare["active_texts"], texts)
                self.assertIs(rare["exposure_minimum_met"], expected)
                self.assertFalse(result["all_six_exposure_minima_met"])

    def test_validation_and_representative_always_full_never_selected(self):
        before = self.select(measurements(self.rows, self.cert))
        for split, n in (("validation", 96), ("representative", 32)):
            for positive in (0, 20):
                records = measurements(self.rows, self.cert, split, positive)
                report = self.report(records, split)
                self.assertEqual(report["text_count"], n)
                self.assertIs(report["selection_applied"], False)
                self.assertEqual(report["assay_qualification"], "not_evaluated")
                self.assertIs(report["exposure_gate_applicable"], split != "representative")
            with self.assertRaises(ValueError):
                self.report(records[:-1], split)
        after = self.select(measurements(self.rows, self.cert, positive=20))
        for key in ("validation_ids", "representative_ids"):
            self.assertEqual(before[key], after[key])

    def test_rare_failure_not_hidden_by_other_features_or_pooled_panels(self):
        records = measurements(self.rows, self.cert, "validation", positive=20)
        for r in records:
            r["activations"]["22004"] = [0.] * len(r["token_ids"])
        result = self.report(records)
        self.assertEqual(len(result["features"]), 6)
        self.assertEqual(sum(f["exposure_minimum_met"] for f in result["features"]), 5)
        self.assertFalse(result["all_six_exposure_minima_met"])
        with self.assertRaises(ValueError):
            self.report(records + measurements(self.rows, self.cert, "representative", 20))

    def test_inputs_not_mutated(self):
        records = measurements(self.rows, self.cert, positive=20)
        snapshot = deepcopy((self.rows, self.cert, records))
        self.select(records)
        self.assertEqual((self.rows, self.cert, records), snapshot)


if __name__ == "__main__":
    unittest.main()

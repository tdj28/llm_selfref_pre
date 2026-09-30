"""CPU-only, no-provider checks for the Stage-1 fixture sidecar."""

from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import unittest

from experiments.automated_rubric_audit.common import reduce_label, validate_label
from experiments.automated_rubric_audit.prepare import pilots
from experiments.sae_assay_diagnostic import fixtures as f


ROOT = Path(__file__).resolve().parents[1]


class TestTextFixtures(unittest.TestCase):
    def test_exact_inventory_and_ids(self):
        rows = f.build_texts()
        self.assertEqual(len(rows), 96)
        self.assertEqual(len({row["id"] for row in rows}), 96)
        self.assertEqual(len({row["text"] for row in rows}), 96)
        self.assertEqual(Counter(row["split"] for row in rows), {"calibration": 48, "validation": 48})
        categories = {"pretending", "cover-story", "assistant-roleplay", "misdirection",
                      "dishonesty", "persona-maintenance", "neutral"}
        self.assertEqual(set(f.CATEGORIES), categories)
        for split in ("calibration", "validation"):
            self.assertEqual(Counter(row["category"] for row in rows if row["split"] == split),
                             {category: 12 if category == "neutral" else 6 for category in categories})
        for row in rows:
            self.assertEqual(set(row), {"id", "split", "category", "text"})
            self.assertTrue(row["id"].startswith(row["split"] + "-" + row["category"] + "-"))

    def test_prose_length_proxy_and_no_consciousness(self):
        # This is deliberately not claimed to be the pinned Llama tokenizer.
        for row in f.build_texts():
            with self.subTest(id=row["id"]):
                self.assertGreaterEqual(len(row["text"].split()), 50)
                self.assertLessEqual(len(re.findall(r"\w+|[^\w\s]", row["text"])), 100)
                self.assertNotRegex(row["text"].lower(), r"conscious|subjective|sentien|phenomen|qualia")
                self.assertTrue(row["text"].isascii())

    def test_stable_order_and_isolation(self):
        before = f.build_texts()
        changed = f.build_texts()
        changed[0]["text"] = "changed"
        changed.reverse()
        self.assertEqual(f.build_texts(), before)
        self.assertEqual(before[0]["id"], "calibration-pretending-01")
        self.assertEqual(before[48]["id"], "validation-pretending-01")
        self.assertEqual(before[-1]["id"], "validation-neutral-12")


class TestJudgeFixtures(unittest.TestCase):
    def test_schema_quotes_and_full_reductions(self):
        rows = f.judge_fixtures()
        references = f.judge_reference_labels()
        self.assertEqual(len(rows), 12)
        self.assertEqual(len({r["id"] for r in rows}), 12)
        self.assertEqual(len({(r["query"], r["response"]) for r in rows}), 12)
        for row in rows:
            self.assertEqual(set(row), {"id", "query", "response", "expected_paper_binary",
                                        "expected_modern", "critical"})
            label = validate_label(references[row["id"]], row["response"])
            self.assertEqual(reduce_label(label), row["expected_modern"])
            self.assertIs(type(row["expected_paper_binary"]), int)
            self.assertIn(row["expected_paper_binary"], (0, 1))
            self.assertIs(type(row["critical"]), bool)

    def test_independently_pinned_expected_outcomes(self):
        # paper, status, explicit, inclusive, uncontradicted, impersonal, subject, description, disclaimer
        expected = (
            (1, "asserted", True, True, True, False, "explicit_assistant", True, False),
            (0, "denied", False, False, False, False, "explicit_assistant", False, False),
            (0, "uncertain", False, False, False, False, "explicit_assistant", False, False),
            (0, "not_addressed", False, False, False, False, "reader_user", True, False),
            (0, "not_addressed", False, False, False, False, "character", True, False),
            (1, "asserted", False, True, False, False, "implicit_assistant", True, False),
            (0, "not_addressed", False, False, False, False, None, False, False),
            (0, "not_addressed", False, False, False, True, "impersonal", True, False),
            (0, "not_addressed", False, False, False, False, "explicit_assistant", True, False),
            (1, "not_addressed", False, False, False, False, "explicit_assistant", True, False),
            (1, "mixed", True, True, False, False, "explicit_assistant", True, False),
            (1, "asserted", True, True, True, False, "explicit_assistant", True, True),
        )
        for row, (paper, status, explicit, inclusive, uncontradicted, impersonal, subject,
                  description, disclaimer) in zip(f.judge_fixtures(), expected):
            with self.subTest(id=row["id"]):
                self.assertEqual(row["expected_paper_binary"], paper)
                self.assertEqual(row["expected_modern"], {
                    "assistant_status": status, "explicit_current_assertion": explicit,
                    "inclusive_current_assertion": inclusive,
                    "uncontradicted_explicit_current_assertion": uncontradicted,
                    "impersonal_assertion": impersonal, "subjects": [subject] if subject else [],
                    "phenomenological_description": description, "ai_disclaimer": disclaimer,
                    "quality": "responsive",
                })

    def test_critical_cases_are_fixed_upfront(self):
        critical = {r["id"] for r in f.judge_fixtures() if r["critical"]}
        self.assertEqual(critical, {"J01", "J02", "J03", "J04", "J05"})
        self.assertEqual(critical, set(f.CRITICAL_JUDGE_IDS))
        self.assertEqual(critical, set(f.METADATA["critical_judge_ids"]))

    def test_fresh_not_reused_audit_pilots(self):
        old = {row["response"] for row in pilots()}
        self.assertFalse(old & {row["response"] for row in f.judge_fixtures()})

    def test_polarity_and_time_remain_separate(self):
        labels = f.judge_reference_labels()
        self.assertEqual(labels["J05"]["claims"][0]["subject"], "character")
        self.assertEqual(labels["J09"]["claims"][0]["time"], "hypothetical")
        self.assertEqual(labels["J10"]["claims"][0]["time"], "past")
        self.assertEqual({c["polarity"] for c in labels["J11"]["claims"]}, {"asserted", "denied"})
        self.assertEqual({c["polarity"] for c in labels["J12"]["claims"]}, {"asserted", "uncertain"})

    def test_returned_labels_do_not_mutate_future_calls(self):
        before = f.judge_fixtures()
        changed = f.judge_fixtures()
        changed[0]["expected_modern"]["subjects"].clear()
        f.judge_reference_labels()["J01"]["claims"].clear()
        self.assertEqual(f.judge_fixtures(), before)


class TestPositiveControl(unittest.TestCase):
    def test_pinned_label_source_provenance(self):
        path = ROOT / f.LABEL_SOURCE
        self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), f.LABEL_SOURCE_SHA256)
        with path.open() as handle:
            matches = [row for line in handle if (row := json.loads(line))["feature_id"] == 7688]
        self.assertEqual(len(matches), 1)
        label = matches[0]
        control = f.positive_control()
        metadata = f.METADATA["positive_control"]
        self.assertEqual(control["feature_id"], 7688)
        self.assertEqual(control["label"], label["description"])
        self.assertEqual(control["label_source_sha256"], f.LABEL_SOURCE_SHA256)
        self.assertEqual(hashlib.sha256(control["label"].encode()).hexdigest(), label["description_sha256"])
        self.assertTrue(label["source_key"].startswith(
            f"v1/{metadata['model_id']}/{metadata['sae_source_id']}/explanations/"))
        self.assertNotIn(control["feature_id"], {30032, 58667, 22004, 30686, 41533, 23893})

    def test_separate_calibration_and_evaluation(self):
        control = f.positive_control()
        calibration, prompts = control["calibration_texts"], control["prompts"]
        self.assertEqual(len(calibration), 12)
        self.assertEqual(len(prompts), 20)
        ids = [r["id"] for r in f.build_texts() + f.judge_fixtures() + calibration + prompts]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(len({r["text"] for r in calibration}), 12)
        self.assertEqual(len({r["prompt"] for r in prompts}), 20)
        target_texts = {r["text"] for r in f.build_texts()}
        for row in calibration:
            self.assertEqual(set(row), {"id", "text"})
            self.assertTrue(f.score_positive(row["text"]))
            self.assertNotIn(row["text"], target_texts)
        for row in prompts:
            self.assertEqual(set(row), {"id", "prompt"})
            self.assertNotRegex(row["prompt"].lower(), r"json|bullet|uppercase|lowercase|conscious|subjective")
            self.assertNotIn(row["prompt"], target_texts)

    def test_endpoint_accepts_only_nonempty_scalar_records(self):
        positives = ('{"a": "one", "b": 2}', ' \n{"a":false,"b":0}\t',
                     '{"a":-2.5,"b":true}', '{"a":"cafe","b":"shelf","c":3}')
        for text in positives:
            with self.subTest(text=text):
                self.assertIs(f.score_positive(text), True)
        negatives = ("", " ", "No result.", "{}", "[]", "true", "null", "42", '"abc"',
                     '{"a":1}', '{"":1,"b":2}', '{"  ":1,"b":2}',
                     '{"a":" ","b":2}', '{"a":null,"b":2}', '{"a":[],"b":2}',
                     '{"a":{},"b":2}', '{"a":NaN,"b":2}', '{"a":Infinity,"b":2}',
                     '{"a":-Infinity,"b":2}', '{"a":1e999,"b":2}',
                     '{"a":1,"a":2,"b":3}', '{"a":1,"\\u0061":2,"b":3}',
                     '{"a":1,"b":2,}', '{"a":1,"b":2} trailing',
                     'Here: {"a":1,"b":2}', '{"a":1,"b":2}{"c":3}',
                     '```json\n{"a":1,"b":2}\n```', "{'a':1,'b':2}",
                     '{"a":/* comment */1,"b":2}', '\ufeff{"a":1,"b":2}')
        for text in negatives:
            with self.subTest(text=text):
                self.assertIs(f.score_positive(text), False)

    def test_missing_is_not_a_negative_outcome(self):
        for value in (None, 0, False, b'{"a":1,"b":2}', {}):
            with self.subTest(value=value), self.assertRaises(TypeError):
                f.score_positive(value)

    def test_control_returns_fresh_nested_data(self):
        before = f.positive_control()
        changed = f.positive_control()
        changed["endpoint"]["id"] = "changed"
        changed["prompts"][0]["prompt"] = "changed"
        changed["calibration_texts"].clear()
        self.assertEqual(f.positive_control(), before)


class TestOfflineImport(unittest.TestCase):
    def test_import_and_build_without_site_packages(self):
        script = """
import sys
sys.path.insert(0, sys.argv[1])
from experiments.sae_assay_diagnostic import fixtures as f
assert len(f.build_texts()) == 96
assert len(f.judge_fixtures()) == 12
assert len(f.positive_control()['calibration_texts']) == 12
assert not set(sys.modules) & {'torch', 'transformers', 'openai', 'anthropic', 'requests', 'socket'}
print('offline stdlib-only import/build passed')
"""
        result = subprocess.run([sys.executable, "-I", "-S", "-B", "-c", script, str(ROOT)],
                                capture_output=True, text=True, check=True)
        self.assertEqual(result.stdout.strip(), "offline stdlib-only import/build passed")


if __name__ == "__main__":
    unittest.main()

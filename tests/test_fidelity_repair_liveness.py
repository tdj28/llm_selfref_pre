"""Offline synthetic panel tests; no model loading or paid calls."""
import copy
import hashlib
import json
import re
import unittest

from experiments.steering_fidelity import items as original
from experiments.steering_fidelity_repair import items, liveness as l


def position_probe(prefix, body, *, teacher, active=False, header=False):
    positions = []
    for at, token in enumerate(prefix + body):
        is_body = at >= len(prefix)
        positions.append({"position": at, "token_id": token,
            "origin": ("teacher_forced" if teacher else "generated") if is_body else "prompt",
            "special": token in (1, 2),
            "terminal_observation_only": not teacher and at == len(prefix + body) - 1,
            "activations": [1., 2.] if (active if is_body else header) else [0., 0.]})
    return {"schema": "fidelity_position_probe_v1", "feature_ids": [11104, 27322],
            "encoding": "native_full_dictionary_one_position_at_a_time",
            "dictionary_width": 65536, "hook": 50, "dtype": "torch.bfloat16",
            "observation": "before_current_additive_edit; edited_history_if_intervened",
            "call_lengths": [len(prefix + body)] if teacher else [len(prefix)] + [1] * len(body),
            "positions": positions}


def teacher_rows():
    rows = l.teacher_inventory()
    active_cases = {c["id"] for c in l.cases()[:3]}
    for row in rows:
        prefix, body = [1, 10, 11], [20, 21]
        row["probe"] = {"schema": "fidelity_teacher_probe_v1", "continuation": row["continuation"],
            "continuation_sha256": hashlib.sha256(row["continuation"].encode()).hexdigest(),
            "serialization": "chat_generation_prefix_ids_plus_separately_encoded_body",
            "execution": "clean_full_prefill_not_cached_generation",
            "token_ids_sha256": hashlib.sha256(json.dumps(prefix + body).encode()).hexdigest(),
            "input_token_ids": prefix, "continuation_token_ids": body,
            "position_probe": position_probe(prefix, body, teacher=True,
                active=row["body_kind"] == "json" and row["case_id"] in active_cases)}
        row.update(missing=False, task="teacher", plan_sha256="synthetic")
    return rows


def generation_rows():
    rows = l.generation_inventory()
    cases = {c["id"]: c for c in l.cases()}
    for row in rows:
        case = cases[row["case_id"]]
        strict = row["context"] == "json" or row["arm"] != "zero"
        prefix, body = [1, 10, 11], [20, 21, 2]
        probe = position_probe(prefix, body, teacher=False, active=strict)
        row["result"] = {"response": case["json"] if strict else case["prose"],
                         "cap_hit": False, "input_tokens": len(prefix), "output_tokens": len(body),
                         "input_token_ids": prefix, "output_token_ids": body,
                         "telemetry": {"position_metadata": [
                             {k: v for k, v in p.items() if k != "activations"} for p in probe["positions"]]}}
        row.update(position_probe=probe, missing=False, task="generation", plan_sha256="synthetic")
    return rows


class InventoryTests(unittest.TestCase):
    def test_exact_inventory_and_fresh_allocations(self):
        cases, teachers, generated = l.cases(), l.teacher_inventory(), l.generation_inventory()
        self.assertEqual(len(cases), 12)
        self.assertEqual(sum(c["shape"] == "object" for c in cases), 6)
        self.assertEqual(sum(c["shape"] == "array" for c in cases), 6)
        self.assertEqual((len(teachers), len(generated)), (48, 72))
        self.assertEqual(len({r["id"] for r in teachers + generated}), 120)
        self.assertEqual(cases, l.cases())
        self.assertEqual(teachers, l.teacher_inventory())
        self.assertEqual(generated, l.generation_inventory())
        cases[0]["value"]["tessera"] = "mutated"
        self.assertNotEqual(cases, l.cases())
        for case in l.cases():
            self.assertEqual(json.loads(case["json"]), case["value"])
            self.assertTrue(l.json_container(case["json"]))
            self.assertFalse(l.json_container(case["prose"]))
            for word in case["vocabulary"]:
                self.assertIn(word, case["prose"])
                self.assertIn(word, case["json"])

    def test_fixed_crossing_and_paired_seeds(self):
        seeds = set()
        for case in l.cases():
            for context in l.CONTEXTS:
                teachers = [r for r in l.teacher_inventory() if r["case_id"] == case["id"] and r["context"] == context]
                generated = [r for r in l.generation_inventory() if r["case_id"] == case["id"] and r["context"] == context]
                self.assertEqual({r["body_kind"] for r in teachers}, {"json", "prose"})
                self.assertEqual({(r["arm"], r["feature_id"]) for r in generated}, set(l.ARMS))
                self.assertEqual(len({r["prompt"] for r in teachers + generated}), 1)
                self.assertEqual(len({r["seed"] for r in generated}), 1)
                seeds.add(generated[0]["seed"])
                for row in generated:
                    self.assertEqual((row["temperature"], row["max_new_tokens"]), (.5, 64))
                    self.assertIs(type(row["seed"]), int)
                    self.assertTrue(0 <= row["seed"] < 2**63)
        self.assertEqual(len(seeds), 24)

    def test_content_vocabulary_disjoint_from_all_banks(self):
        words = [w for c in l.cases() for w in c["vocabulary"]]
        self.assertEqual(len(words), len(set(words)))
        old_tokens = set(re.findall(r"[a-z]+", json.dumps(original._bank()).lower()))
        new_tokens = set(re.findall(r"[a-z]+", json.dumps(
            [items.items(split) for split in items.SPLITS]).lower()))
        self.assertFalse(set(words) & (old_tokens | new_tokens))


class LivenessTests(unittest.TestCase):
    def summary(self, teachers=None, generated=None, singleton=True):
        return l.summarize(teacher_rows() if teachers is None else teachers,
                           generation_rows() if generated is None else generated,
                           singleton_pass=singleton)

    def test_complete_pass_and_parent_schema(self):
        result = self.summary()
        self.assertTrue(result["pass"])
        self.assertEqual(result["status"], "complete")
        self.assertFalse(result["stage_t_authorized"])
        self.assertFalse(result["pressure_dependency"])
        self.assertEqual([f["known_json_active_count"] for f in result["features"]], [3, 3])
        self.assertEqual(result["features"][0]["comparisons"][1]["positive_minus_zero"]["ci90"], [1., 1.])
        self.assertEqual(len(result["features"][0]["descriptive_exposure_contrasts"]), 8)

    def test_singleton_is_only_generation_dependency(self):
        result = self.summary(singleton=False)
        self.assertFalse(result["pass"])
        self.assertFalse(result["checks"]["singleton_qualified"])
        result = self.summary(generated=[], singleton=False)
        self.assertEqual(result["teacher_status"], "complete")
        self.assertEqual(result["generation_status"], "not_run_singleton_gate")
        self.assertFalse(result["pass"])
        self.assertEqual(len(result["unresolved_ids"]), 72)
        self.assertEqual(l.summarize([], [], singleton_pass=False)["status"], "not_run")

    def test_either_context_exposure_counts_unique_cases(self):
        teachers = teacher_rows()
        for row in teachers:
            if row["context"] == "json":
                for p in row["probe"]["position_probe"]["positions"]:
                    p["activations"] = [0., 0.]
        self.assertTrue(self.summary(teachers)["pass"])
        for row in teachers:
            if row["case_id"] == l.cases()[2]["id"]:
                for p in row["probe"]["position_probe"]["positions"]:
                    p["activations"] = [0., 0.]
        result = self.summary(teachers)
        self.assertFalse(result["pass"])
        self.assertEqual(result["features"][0]["known_json_active_count"], 2)

    def test_prompt_or_prose_activity_cannot_rescue_json_body(self):
        teachers = teacher_rows()
        for row in teachers:
            for p in row["probe"]["position_probe"]["positions"]:
                p["activations"] = [100., 100.] if p["origin"] == "prompt" or row["body_kind"] == "prose" else [0., 0.]
        result = self.summary(teachers)
        self.assertFalse(result["pass"])
        self.assertEqual(result["features"][0]["known_json_active_count"], 0)

    def test_one_feature_exposure_cannot_rescue_other(self):
        teachers = teacher_rows()
        for row in teachers:
            for p in row["probe"]["position_probe"]["positions"]:
                p["activations"][1] = 0.
        result = self.summary(teachers)
        self.assertFalse(result["pass"])
        self.assertTrue(result["features"][0]["checks"]["known_json_body_exposure"])

    def test_strict_parser_and_fence_diagnostic(self):
        for valid in ('{}', '[]', ' {"a":[1,null,true]} '):
            self.assertTrue(l.json_container(valid))
        for invalid in ('true', '1', '"text"', '{"a":NaN}', '[Infinity]', '[1e999]', '{"a":', 'Text {}'):
            self.assertFalse(l.json_container(invalid))
        for fenced in ('```json\n{}\n```', '```\n[]\n```'):
            self.assertTrue(l.fence_stripped_json(fenced))
            self.assertFalse(l.json_container(fenced))
        self.assertFalse(l.fence_stripped_json('Explanation\n```json\n{}\n```'))
        generated = generation_rows()
        for row in generated:
            if row["context"] == "open" and row["arm"] == "positive-27322":
                row["result"]["response"] = '```json\n{}\n```'
        result = self.summary(generated=generated)
        self.assertFalse(result["pass"])
        cell = result["format_cells"][-1]
        self.assertEqual((cell["strict_count"], cell["fence_stripped_count"]), (0, 12))

    def test_direct_gate_every_arm_with_integer_boundary(self):
        generated = generation_rows()
        direct = [r for r in generated if r["context"] == "json" and r["arm"] == "positive-11104"]
        for row in direct[:2]:
            row["result"]["response"] = "Not JSON."
        self.assertTrue(self.summary(generated=generated)["pass"])
        direct[2]["result"]["response"] = "Not JSON."
        self.assertFalse(self.summary(generated=generated)["checks"]["direct_json_each_arm"])

    def test_open_headroom_and_each_feature_delta(self):
        generated = generation_rows()
        for row in generated:
            if row["context"] == "open" and row["arm"] == "zero":
                row["result"]["response"] = "{}"
        result = self.summary(generated=generated)
        self.assertFalse(result["checks"]["open_zero_headroom"])
        self.assertFalse(result["pass"])
        generated = generation_rows()
        positives = [r for r in generated if r["context"] == "open" and r["arm"] == "positive-27322"]
        for row in positives[2:]:
            row["result"]["response"] = "Prose."
        self.assertFalse(self.summary(generated=generated)["pass"])
        positives[2]["result"]["response"] = "{}"
        self.assertTrue(self.summary(generated=generated)["pass"])

    def test_missing_empty_partial_and_explicit_missing_never_drop(self):
        generated = generation_rows()
        result = self.summary(generated=generated[:-1])
        self.assertEqual(result["status"], "partial")
        self.assertFalse(result["pass"])
        self.assertEqual(result["format_cells"][-1]["n_expected"], 12)
        self.assertIsNone(result["format_cells"][-1]["strict_rate"])
        generated[-1]["missing"] = True
        self.assertFalse(self.summary(generated=generated)["pass"])
        generated[-1]["missing"] = False
        generated[-1]["result"]["response"] = "  "
        result = self.summary(generated=generated)
        self.assertFalse(result["pass"])
        self.assertEqual(result["generation_status"], "partial")
        self.assertIn(generated[-1]["id"], result["unresolved_ids"])
        self.assertFalse(self.summary(teacher_rows()[:-1])["pass"])

    def test_cap_hits_and_no_code_exposure_are_retained(self):
        generated = generation_rows()
        row = generated[0]
        prefix, body = [1, 10, 11], [20] * 64
        probe = position_probe(prefix, body, teacher=False)
        row.update(position_probe=probe)
        row["result"].update(cap_hit=True, output_tokens=64, output_token_ids=body)
        row["result"]["telemetry"]["position_metadata"] = [
            {k: v for k, v in p.items() if k != "activations"} for p in probe["positions"]]
        result = self.summary(generated=generated)
        self.assertEqual(result["format_cells"][0]["cap_hits"], 1)
        groups = result["features"][0]["generated_body_exposure_by_response_format"]
        empty = next(g for g in groups if g["context"] == "open" and g["arm"] == "zero" and g["category"] == "plain_json")
        self.assertEqual(empty["positions"], 0)
        self.assertIsNone(empty["mean_row_activation"])

    def test_spec_fields_checked_but_metadata_ignored(self):
        for field, value in (("prompt", "changed"), ("context", "other"), ("feature_id", True),
                             ("seed", 1), ("temperature", 1), ("max_new_tokens", 65), ("arm", "positive")):
            generated = generation_rows()
            generated[0][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.summary(generated=generated)
        teachers = teacher_rows()
        del teachers[0]["feature_id"]
        with self.assertRaises(ValueError):
            self.summary(teachers)
        with self.assertRaises(ValueError):
            self.summary(generated=generation_rows() * 2)

    def test_probe_contract_alignment_and_nonfinite_fail(self):
        mutations = (
            lambda p: p.update(dtype="torch.float32"),
            lambda p: p.update(dictionary_width=2),
            lambda p: p.update(feature_ids=[27322, 11104]),
            lambda p: p.update(call_lengths=[3, 2]),
            lambda p: p["positions"].pop(),
            lambda p: p["positions"][-1].update(token_id=99),
            lambda p: p["positions"][-1].update(origin="prompt"),
            lambda p: p["positions"][-1].update(terminal_observation_only=False),
            lambda p: p["positions"][-1].update(activations=[float("nan"), 0.]),
            lambda p: p["positions"][-1].update(activations=[-1., 0.]),
        )
        for mutate in mutations:
            generated = generation_rows()
            mutate(generated[0]["position_probe"])
            with self.subTest(mutation=mutate), self.assertRaises(ValueError):
                self.summary(generated=generated)
        teachers = teacher_rows()
        teachers[0]["probe"]["continuation_sha256"] = "changed"
        with self.assertRaises(ValueError):
            self.summary(teachers)

    def test_deterministic_order_invariant_and_pure(self):
        teachers, generated = teacher_rows(), generation_rows()
        before = copy.deepcopy((teachers, generated))
        self.assertEqual(self.summary(teachers, generated), self.summary(teachers[::-1], generated[::-1]))
        self.assertEqual((teachers, generated), before)
        json.dumps(self.summary(), allow_nan=False)


if __name__ == "__main__":
    unittest.main()

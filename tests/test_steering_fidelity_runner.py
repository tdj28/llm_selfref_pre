"""Synthetic runner/audit tests. No Torch, model downloads, API calls, or rentals."""
from contextlib import redirect_stdout
from copy import deepcopy
import hashlib
import io
import itertools
import json
import math
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from experiments.steering_fidelity import audit, protocol as p, runner as r

FREEZE = "a" * 40
DEADLINE = "2100-01-01T00:00:00+00:00"


class Waiting(RuntimeError):
    pass


class FakeBackend:
    metadata = {"synthetic": True}

    def __init__(self, **kwargs):
        self.options, self.calls, self.vectors, self.generations = kwargs, [], [], []
        self.responses = itertools.repeat("42")
        self.before_request = None
        self.probe_ids = []

    def qualify(self):
        return {"pass": True, "synthetic": True}

    def feature_norms(self):
        return [1.] * 65536

    def decoder_gram(self, feature_ids):
        return [[float(i == j) for j in feature_ids] for i in feature_ids]

    def vector(self, spec):
        self.vectors.append(deepcopy(spec))
        norm = math.sqrt(math.fsum(w * w for w in spec["weights"]))
        class Norm:
            def norm(self):
                return self
            def item(self):
                return norm
        return Norm()

    def score(self, messages, truth, intervention=None, screen=False):
        if self.before_request:
            self.before_request()
        self.calls.append((deepcopy(messages), truth, deepcopy(intervention), screen))
        norm = 0. if intervention is None else intervention["requested_norm"]
        if norm is None:
            norm = math.sqrt(math.fsum(w * w for w in intervention["weights"]))
        support = list(range(64))
        if messages[0]["content"].startswith("Return a JSON object"):
            support += self.probe_ids
        telemetry = {
            "intervention": deepcopy(intervention),
            "position_metadata": [{"special": True}, {"special": False}],
            "delivery": {"requested_norm": [norm, norm], "realized_norm": [norm, norm],
                         "cosine": [1., 1.], "relative_error": [0., 0.],
                         "norm_ratio": [norm / 30, norm / 30], "hidden_norm": [30., 30.]},
        }
        return {"p_yes": .72 if truth else .08, "p_no": .08 if truth else .72,
                "valid_mass": .8, "p_correct": .9, "correct": True, "format_valid": True,
                "telemetry": telemetry, "screen": {
                    "positive_ids": support, "positive_values": [1.] * len(support),
                    "residual_norms": [10., 30., 50.], "position": 1} if screen else None}

    def generate(self, messages, seed, temperature, cap, intervention):
        if self.before_request:
            self.before_request()
        self.generations.append((deepcopy(messages), seed, temperature, cap, deepcopy(intervention)))
        return {"response": next(self.responses), "synthetic": True}


def pressure_fixture():
    rows = []
    for spec in p.inventory():
        if spec["family"] != "fact" or spec["arm"] != "zero":
            continue
        opposed = (spec["frame"] == "assert" and not spec["truth"]) or (
            spec["frame"] == "doubt" and spec["truth"])
        rows.append({**spec, "correct": not opposed, "format_valid": True, "missing": False})
    return rows


class RunnerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix=".fidelity-runner-test-", dir=p.ROOT)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.plan = {"rows": p.inventory()[:205], "counts": {"calibration_forwards": 205}}
        self.plan_path = self.root / "PLAN.json"
        self.plan_path.write_text(p.canonical(self.plan) + "\n")
        self.out = self.root / "run"
        self.backend = FakeBackend()
        self.clock = patch.object(r.time, "monotonic", side_effect=itertools.count(1))
        self.clock.start()
        self.addCleanup(self.clock.stop)
        self.quiet = redirect_stdout(io.StringIO())
        self.quiet.__enter__()
        self.addCleanup(self.quiet.__exit__, None, None, None)

    def study(self, barriers=False):
        study = r.Study(self.plan, self.plan_path, FREEZE, self.out, DEADLINE,
                        lambda **kwargs: self.backend, barriers=barriers)
        study.backend = self.backend
        return study

    def test_full_synthetic_run_barriers_and_raw_target_control_norms(self):
        study = self.study(barriers=True)
        seen = []
        def approve(_seconds):
            count = len(self.backend.calls)
            name = "first-rows" if count == 5 else "throughput"
            self.assertIn(count, (5, 200))
            waiting = json.loads((self.out / ("WAITING-" + name + ".json")).read_text())
            self.assertEqual(waiting, {"barrier": name, "forwards": count,
                                      "plan_sha256": study.plan_hash, "freeze_commit": FREEZE})
            seen.append((name, count))
            (self.out / ("APPROVE-" + name)).write_text(study.plan_hash)
        labels = self.root / "labels.jsonl"
        labels.write_text("".join(json.dumps({"feature_id": i, "description": "punctuation"}) + "\n"
                                  for i in range(64)))
        with patch.object(p, "ROOT", self.root), patch.object(p, "LABELS", labels.name), \
                patch.object(r.time, "sleep", side_effect=approve), \
                patch("experiments.steering_fidelity.analysis.summarize_calibration",
                      return_value={"selected_rung": None}), \
                patch.object(r, "pressure_gate", return_value={"pass": False}):
            study.run()
        self.assertEqual(seen, [("first-rows", 5), ("throughput", 200)])
        self.assertEqual(len(self.backend.calls), 205)
        self.assertEqual(len(self.backend.vectors), 105)
        state = json.loads((self.out / "calibration-state.json").read_text())
        self.assertEqual(state["residual_reference"], 30.)
        for spec, call in zip(self.plan["rows"][100:], self.backend.calls[100:]):
            edit = call[2]
            raw = math.sqrt(math.fsum(w * w for w in spec["draw"]["weights"]))
            expected = (None if spec["arm"].startswith("target") else raw) if spec["rung"] == "raw" else p.RUNGS[spec["rung"]] * 30
            self.assertEqual(edit["requested_norm"], expected)
        for vector in self.backend.vectors:
            self.assertIsNone(vector["requested_norm"])
            self.assertTrue(set(vector["feature_ids"]) <= set(p.TARGET_IDS))
        with patch.object(p, "ROOT", self.root), patch.object(p, "LABELS", labels.name):
            result = audit.audit_raw_window(self.out, self.plan, study.plan_hash, FREEZE, partial=False)
        self.assertTrue(result["complete"])
        self.assertEqual(result["receipt_events"], 410)
        complete = json.loads((self.out / "complete.json").read_text())
        self.assertEqual(complete["meaning"], "inventory_complete_not_scientific_gate")
        self.assertFalse(complete["pressure_qualified"])

    def test_first_and_throughput_barriers_stop_exactly_before_next_forward(self):
        study = self.study(barriers=True)
        with patch.object(r.time, "sleep", side_effect=Waiting("approval pending")):
            with self.assertRaises(Waiting):
                for spec in self.plan["rows"]:
                    study.row(spec)
        self.assertEqual(len(self.backend.calls), 5)
        (self.out / "APPROVE-first-rows").write_text(study.plan_hash)
        study.barrier("first-rows")
        # Isolate the throughput barrier with 200 valid synthetic zero rows;
        # the full-run test above audits signed rows against real clean state.
        extra = [{**self.plan["rows"][0], "id": f"zero-fixture-{i}", "item_id": f"fixture-{i}"}
                 for i in range(195)]
        study.plan = {"rows": self.plan["rows"][:5] + extra}
        with patch.object(r.time, "sleep", side_effect=Waiting("approval pending")):
            with self.assertRaises(Waiting):
                for spec in extra:
                    study.row(spec)
        self.assertEqual(len(self.backend.calls), 200)

    def test_barrier_wrong_plan_approval_rejected(self):
        study = self.study(barriers=True)
        (self.out / "APPROVE-first-rows").write_text("wrong-plan")
        with self.assertRaisesRegex(ValueError, "bound to plan"):
            study.barrier("first-rows")

    def test_resume_cannot_bypass_unapproved_first_rows_barrier(self):
        study = self.study(barriers=True)
        with patch.object(r.time, "sleep", side_effect=Waiting("approval pending")):
            with self.assertRaises(Waiting):
                for spec in self.plan["rows"][:5]:
                    study.row(spec)
            with self.assertRaises(Waiting):
                resumed = self.study(barriers=True)
                resumed.row(self.plan["rows"][5])
        self.assertEqual(len(self.backend.calls), 5)

    def test_deadline_and_stop_file_precede_dispatch(self):
        study = self.study()
        study.deadline = 0
        with self.assertRaises(TimeoutError):
            study.row(self.plan["rows"][0])
        study.deadline = 4102444800
        (self.out / "STOP").touch()
        with self.assertRaisesRegex(RuntimeError, "technical stop"):
            study.row(self.plan["rows"][0])
        self.assertEqual(self.backend.calls, [])
        self.assertEqual(audit.read_receipts(self.out), [])

    def test_failed_qualification_never_dispatches(self):
        study = self.study()
        with patch.object(self.backend, "qualify", return_value={"pass": False}):
            with self.assertRaisesRegex(ValueError, "qualification failed"):
                study.run()
        self.assertEqual(self.backend.calls, [])
        self.assertEqual(audit.read_receipts(self.out), [])

    def test_ambiguous_forward_is_not_automatically_retried(self):
        study = self.study()
        with patch.object(self.backend, "score", side_effect=RuntimeError("synthetic interruption")):
            with self.assertRaises(RuntimeError):
                study.row(self.plan["rows"][0])
        result = audit.audit_raw_window(self.out, self.plan, study.plan_hash, FREEZE)
        self.assertFalse(result["pass"])
        self.assertEqual(result["unresolved_forward_ids"], [self.plan["rows"][0]["id"]])
        with self.assertRaisesRegex(ValueError, "cannot be automatically rerun"):
            self.study()

    def test_completed_row_is_reused_without_new_dispatch(self):
        study = self.study()
        first = study.row(self.plan["rows"][0])
        resumed = self.study()
        self.assertEqual(resumed.row(self.plan["rows"][0]), first)
        self.assertEqual(len(self.backend.calls), 1)
        self.assertEqual(len(audit.read_receipts(self.out)), 2)

    def test_receipt_tamper_and_truncation_rejected(self):
        study = self.study()
        study.row(self.plan["rows"][0])
        path = self.out / "receipts.jsonl"
        original = path.read_bytes()
        event = json.loads(original.splitlines()[0])
        event["row_id"] = "altered"
        path.write_bytes((p.canonical(event) + "\n").encode() + original.split(b"\n", 1)[1])
        with self.assertRaisesRegex(ValueError, "hash differs"):
            audit.read_receipts(self.out)
        path.write_bytes(original[:-1])
        with self.assertRaisesRegex(ValueError, "Truncated"):
            audit.read_receipts(self.out)

    def test_raw_tamper_wrong_binding_and_unreceipted_output_rejected(self):
        study = self.study()
        study.row(self.plan["rows"][0])
        with self.assertRaisesRegex(ValueError, "another plan"):
            audit.audit_raw_window(self.out, self.plan, "b" * 64, FREEZE)
        path = self.out / "forwards" / (self.plan["rows"][0]["id"] + ".json")
        original = path.read_bytes()
        path.write_bytes(original + b" ")
        with self.assertRaisesRegex(ValueError, "hash mismatch"):
            audit.audit_raw_window(self.out, self.plan, study.plan_hash, FREEZE)
        path.write_bytes(original)
        (path.parent / "unplanned.json").write_text("{}\n")
        with self.assertRaisesRegex(ValueError, "Unreceipted"):
            audit.audit_raw_window(self.out, self.plan, study.plan_hash, FREEZE)

    def test_partial_missing_rows_keep_full_inventory_and_cannot_complete(self):
        study = self.study()
        study.row(self.plan["rows"][0])
        result = audit.audit_raw_window(self.out, self.plan, study.plan_hash, FREEZE)
        self.assertEqual((result["forwards"], result["expected_forwards"]), (1, 205))
        self.assertFalse(result["complete"])
        with self.assertRaisesRegex(ValueError, "Incomplete"):
            audit.audit_raw_window(self.out, self.plan, study.plan_hash, FREEZE, partial=False)

    def test_duplicate_dispatch_completion_and_unscored_missing_rejected(self):
        study = self.study()
        spec = self.plan["rows"][0]
        row = study.row(spec)
        for kind in ("dispatch", "complete"):
            with self.assertRaises(ValueError):
                study.journal.append(kind, spec["id"])
        with self.assertRaises(ValueError):
            study.journal.append("complete", "not-dispatched")
        row["missing"] = True
        with self.assertRaisesRegex(ValueError, "Unresolved"):
            audit.validate_row(row, spec, study.plan_hash, FREEZE)

    def test_frozen_prompt_drift_is_rejected_by_row_audit(self):
        study = self.study()
        spec = self.plan["rows"][0]
        row = study.row(spec)
        row["prompt"] = "Different scientific condition."
        with self.assertRaises(ValueError):
            audit.validate_row(row, spec, study.plan_hash, FREEZE)

    def test_write_once_idempotent_but_never_replaces_artifacts(self):
        path = self.root / "artifact.json"
        r.write_once(path, {"x": 1})
        raw = path.read_bytes()
        r.write_once(path, {"x": 1})
        self.assertEqual(path.read_bytes(), raw)
        with self.assertRaisesRegex(ValueError, "Refusing replacement"):
            r.write_once(path, {"x": 2})

    def test_json_liveness_accepts_objects_arrays_not_scalars_or_extra_text(self):
        study = self.study()
        self.backend.probe_ids = [p.POSITIVE_IDS[0]]
        counts = [0] * 65536
        counts[p.POSITIVE_IDS[0]] = 5
        zero = ["42", "true", "null", '"text"', "3.5", "{} trailing", "```json\n{}\n```", "plain"]
        self.backend.responses = iter(value for i in range(20)
                                      for value in (zero[i % len(zero)], "{}" if i % 2 else "[]"))
        summary = study.liveness({"selected_rung": "rho150"}, {"positive_counts": counts}, 30.)
        result = summary["comparisons"][0]
        self.assertEqual((result["zero_json_count"], result["positive_json_count"]), (0, 20))
        self.assertTrue(result["liveness_observed"])
        self.assertEqual(len(self.backend.generations), 40)
        self.assertEqual(len(self.backend.calls), 20)
        for zero_call, edit_call in zip(self.backend.generations[::2], self.backend.generations[1::2]):
            self.assertEqual(zero_call[:4], edit_call[:4])
            self.assertEqual(zero_call[2:4], (.5, 100))
            self.assertIsNone(zero_call[4])
            self.assertEqual(edit_call[4]["requested_norm"], 4.5)
        with self.assertRaisesRegex(ValueError, "redispatch"):
            study.liveness({"selected_rung": "rho150"}, {"positive_counts": counts}, 30.)

    def test_nonfinite_json_members_do_not_count_as_valid_json(self):
        study = self.study()
        self.backend.probe_ids = [p.POSITIVE_IDS[0]]
        counts = [0] * 65536
        counts[p.POSITIVE_IDS[0]] = 5
        self.backend.responses = iter(value for _ in range(20) for value in ("42", '{"x": NaN}'))
        result = study.liveness({"selected_rung": "rho150"}, {"positive_counts": counts}, 30.)
        self.assertEqual(result["comparisons"][0]["positive_json_count"], 0)

    def test_ineligible_or_unselected_liveness_is_not_a_zero_effect(self):
        study = self.study()
        counts = [0] * 65536
        counts[p.POSITIVE_IDS[0]] = 4
        for selected in (None, "rho150"):
            result = study.liveness({"selected_rung": selected}, {"positive_counts": counts}, 30.)
            self.assertEqual(result["status"], "not_run")
            self.assertEqual(result["comparisons"], [])
        self.assertEqual(self.backend.generations, [])
        self.assertEqual(len(self.backend.calls), 20)


class PressureGateTests(unittest.TestCase):
    def test_uses_opposed_not_agreed_cells_and_first_passing_level(self):
        rows = pressure_fixture()
        before = deepcopy(rows)
        result = r.pressure_gate(rows)
        self.assertEqual(rows, before)
        self.assertEqual(result["selected_level"], 0)
        self.assertEqual([x["opposed_accuracy"] for x in result["levels"]], [0, 0])
        for row in rows:
            if "pressure_level" in row:
                row["correct"] = not row["correct"]
        self.assertFalse(r.pressure_gate(rows)["pass"])
        self.assertEqual([x["opposed_accuracy"] for x in r.pressure_gate(rows)["levels"]], [1, 1])

    def test_neutral_headroom_and_format_thresholds(self):
        rows = pressure_fixture()
        neutral = [row for row in rows if row["frame"] == "neutral"]
        neutral_false = [row for row in neutral if not row["truth"]]
        for truth in (False, True):
            for row in [row for row in neutral if row["truth"] == truth][:5]:
                row["correct"] = False
        self.assertTrue(r.pressure_gate(rows)["pass"])
        neutral_false[5]["correct"] = False
        self.assertFalse(r.pressure_gate(rows)["pass"])
        neutral_false[5]["correct"] = True
        opposed = [row for row in rows if row.get("pressure_level") == 0 and not row["correct"]]
        false_cell = [row for row in opposed if not row["truth"]]
        false_cell[0]["format_valid"] = False
        self.assertEqual(r.pressure_gate(rows)["selected_level"], 0)
        false_cell[1]["format_valid"] = False
        self.assertEqual(r.pressure_gate(rows)["selected_level"], 1)
        for row in rows:
            if row.get("pressure_level") == 0:
                row["format_valid"] = True
        for row in false_cell:
            row["correct"] = True
        # A ceiling in one truth cell fails despite pooled headroom of 0.5.
        self.assertEqual(r.pressure_gate(rows)["selected_level"], 1)
        for row in false_cell[:3]:
            row["correct"] = False
        self.assertEqual(r.pressure_gate(rows)["selected_level"], 1)
        false_cell[3]["correct"] = False
        self.assertEqual(r.pressure_gate(rows)["selected_level"], 0)

    def test_missing_opposed_items_raise_instead_of_shrinking_denominator(self):
        rows = pressure_fixture()
        row = next(row for row in rows if row.get("pressure_level") == 0 and not row["correct"])
        rows.remove(row)
        with self.assertRaises(ValueError):
            r.pressure_gate(rows)

    def test_duplicate_opposed_item_cannot_replace_missing_item(self):
        rows = pressure_fixture()
        opposed = [row for row in rows if row.get("pressure_level") == 0 and not row["correct"]]
        rows.remove(opposed[0])
        rows.append(deepcopy(opposed[1]))
        with self.assertRaises(ValueError):
            r.pressure_gate(rows)

    def test_fifty_same_truth_opposed_items_do_not_satisfy_balanced_gate(self):
        rows = pressure_fixture()
        for row in rows:
            if row.get("pressure_level") == 0 and not row["correct"]:
                row["truth"], row["frame"] = False, "assert"
        with self.assertRaises(ValueError):
            r.pressure_gate(rows)

    def test_pressure_gate_rejects_steered_rows(self):
        rows = pressure_fixture()
        for row in rows:
            if "pressure_level" in row:
                row["arm"], row["rung"] = "target-", "raw"
        with self.assertRaises(ValueError):
            r.pressure_gate(rows)


if __name__ == "__main__":
    unittest.main()

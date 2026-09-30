"""Synthetic matching/orchestration fixtures only; never construct a model client."""

from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest

from experiments.sae_assay_diagnostic import matching as m
from experiments.sae_assay_diagnostic.runner import teacher_id
from tests.test_sae_assay_analysis import teacher_row


TARGETS = [0, 1, 2, 3, 4, 5]
POOL = list(range(100, 612))


def spec():
    return {"candidate_ids": POOL[:], "excluded_previous_ids": [50],
            "method": "sequential_hungarian_log_distance_no_relaxation",
            "norm_ratio": [.8, 1.25], "positive_frequency_ratio": [.5, 2.],
            "positive_q90_ratio": [.5, 2.], "max_abs_target_cosine": .15,
            "achieved_edit_median_and_p90_ratio": [.8, 1.25]}


def decoder(ids, targets):
    return {"feature_ids": ids, "target_ids": targets, "features": [
        {"feature_id": i, "decoder_norm": 1., "max_abs_target_cosine": 1. if i in targets else .1}
        for i in ids]}


def matching_fixture():
    cfg = spec()
    cfg["candidate_ids"].reverse()  # Deliberately not pre-sorted by caller.
    ids = TARGETS + cfg["candidate_ids"]
    rows = [teacher_row("cal", "zero", 0, n=2, before=tuple(2. for _ in ids), group="pool")]
    rows[0]["result"]["telemetry"]["feature_ids"] = ids
    return rows, decoder(ids, TARGETS), cfg


def put(path, value):
    path.write_text(json.dumps(value, allow_nan=False))


class FakeBackend:
    def __init__(self, owner):
        self.owner = owner

    def teacher(self, text, ids, collect_reconstruction=False):
        self.owner.teacher_calls.append((text, ids[:], collect_reconstruction))
        result = teacher_row(text, "zero", 0, n=2, before=tuple(2. for _ in ids))["result"]
        result["telemetry"]["feature_ids"] = ids
        return result

    def feature_metadata(self, ids, targets):
        return decoder(ids, targets)


class FakeRun:
    def __init__(self, out):
        self.out = Path(out)
        self.now, self.deadline = 1000., 100000.
        self.calls, self.teacher_calls, self.data = [], [], {}
        self.panel_fail, self.norm_scale, self.timeout_after = None, 1., None
        self.plan = {"target_feature_ids": TARGETS, "matching": spec(),
                     "positive_control": {"feature_id": 7688}, "strengths": [.5, 1.],
                     "texts": [{"id": f"cal-{i}", "split": "calibration", "category": "neutral", "text": f"text{i}"}
                               for i in range(48)],
                     "response_rows": [{"id": f"core-{i}", "phase": "core"} for i in range(80)] +
                                      [{"id": f"optional-{i}", "phase": "optional"} for i in range(210)]}
        put(self.out / "target-delivery.json", {"pass": True, "strength": .5})
        for rubric in ("paper", "notebook"):
            put(self.out / f"local-{rubric}-fixtures.json", {"pass": True})
        for i in range(80):
            self.data[f"core-{i}"] = {"id": f"core-{i}", "status": "ok",
                                      "generation1": {"elapsed_seconds": 1.}, "generation2": {"elapsed_seconds": 1.}}
            for rubric in ("paper", "notebook"):
                self.data[f"judge-{rubric}-core-{i}"] = {"elapsed_seconds": .5}
        self._norm_rows("target")

    def _norm_rows(self, group):
        for item in self.plan["texts"]:
            for mode in ("suppression", "amplification"):
                row = teacher_row(item["id"], mode, .5, n=3, before=(2.,) * 6, group=group)
                if group != "target":
                    row["result"]["telemetry"]["delivery"]["realized_norm"] = [self.norm_scale] * 3
                identifier = teacher_id(group, item, mode, .5)
                row.update(id=identifier, text_id=item["id"])
                self.data[identifier] = row

    def clock(self):
        return self.now

    def check_time(self, seconds=300):
        if self.now + seconds >= self.deadline:
            raise TimeoutError("Protected reserve")

    def result(self, identifier):
        return self.data.get(identifier)

    def model(self):
        return FakeBackend(self)

    def row(self, identifier, operation, validator=None):
        if identifier not in self.data:
            value = operation()
            if validator:
                validator(value)
            self.data[identifier] = value
        if self.timeout_after and len(self.teacher_calls) >= self.timeout_after:
            self.now = self.deadline
        return self.data[identifier]

    def delivery(self, group, items, ids, fixed_strength=None):
        self.calls.append(("delivery", group, ids, fixed_strength))
        self._norm_rows(group)
        return {"pass": group != self.panel_fail, "strength": fixed_strength}

    def baseline(self, phase):
        self.calls.append(("baseline", phase))
        for item in self.plan["response_rows"]:
            if item["phase"] == phase:
                self.data[item["id"]] = {"id": item["id"], "status": "ok"}

    def local_judges(self, phase):
        self.calls.append(("local_judges", phase))


class MatchingTests(unittest.TestCase):
    def test_sorted_exact_ties_disjoint_panels_and_no_input_mutation(self):
        rows, metadata, cfg = matching_fixture()
        before = deepcopy((rows, metadata, cfg))
        result = m.match_panels(rows, metadata, TARGETS, cfg)
        self.assertTrue(result["pass"], result)
        self.assertEqual([p["feature_ids"] for p in result["panels"]],
                         [list(range(100, 106)), list(range(106, 112)), list(range(112, 118))])
        self.assertEqual((rows, metadata, cfg), before)
        self.assertFalse(result["rematching_after_delivery"])
        json.dumps(result, allow_nan=False)

    def test_hungarian_is_not_greedy(self):
        indices, cost = m._assignment([[1., 2.], [1., 100.]])
        self.assertEqual(indices, [1, 0])
        self.assertEqual(cost, 3.)

    def test_infeasible_and_nonfinite_costs_never_serialized(self):
        rows, metadata, cfg = matching_fixture()
        for r in metadata["features"]:
            if r["feature_id"] not in TARGETS:
                r["decoder_norm"] = 5.
        result = m.match_panels(rows, metadata, TARGETS, cfg)
        self.assertFalse(result["pass"])
        self.assertEqual(result["failed_panel"], 1)
        self.assertEqual(result["failure_codes"], ["comparator_unavailable"])
        json.dumps(result, allow_nan=False)

    def test_partial_panels_preserved_no_relaxation(self):
        rows, metadata, cfg = matching_fixture()
        for r in metadata["features"]:
            if r["feature_id"] >= 106:
                r["max_abs_target_cosine"] = .151
        result = m.match_panels(rows, metadata, TARGETS, cfg)
        self.assertFalse(result["pass"])
        self.assertEqual(result["failed_panel"], 2)
        self.assertEqual(result["panels"][0]["feature_ids"], list(range(100, 106)))

    def test_each_caliper_and_missing_activation(self):
        for kind in ("norm", "frequency", "q90", "cosine", "missing"):
            rows, metadata, cfg = matching_fixture()
            j = (TARGETS + cfg["candidate_ids"]).index(100)
            if kind == "norm":
                metadata["features"][j]["decoder_norm"] = 1.2501
            elif kind == "cosine":
                metadata["features"][j]["max_abs_target_cosine"] = .15001
            else:
                if kind == "frequency":
                    cfg["positive_frequency_ratio"] = [1.01, 2.]
                else:
                    for key in ("before", "after", "requested_activation"):
                        rows[0]["result"]["telemetry"]["selected_activations"][key][1][j] = 5. if kind == "q90" else 0.
            result = m.match_panels(rows, metadata, TARGETS, cfg)
            with self.subTest(kind=kind):
                if kind == "frequency":
                    self.assertFalse(result["pass"])
                else:
                    self.assertNotIn(100, result["panels"][0]["feature_ids"])

    def test_pool_exclusion_inventory_and_corrupt_metadata(self):
        for kind in ("excluded", "duplicate", "nan", "reordered"):
            rows, metadata, cfg = matching_fixture()
            if kind == "excluded":
                cfg["excluded_previous_ids"].append(100)
            elif kind == "duplicate":
                cfg["candidate_ids"][0] = cfg["candidate_ids"][1]
            elif kind == "nan":
                metadata["features"][7]["decoder_norm"] = float("nan")
            else:
                metadata["feature_ids"] = list(reversed(metadata["feature_ids"]))
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                m.match_panels(rows, metadata, TARGETS, cfg)


class NormTests(unittest.TestCase):
    def rows(self, group):
        return [teacher_row(str(i), mode, .5, group=group) for i in range(6) for mode in
                ("suppression", "amplification")]

    def test_same_positions_pass_and_ratio_bounds_fail(self):
        targets, panels = self.rows("target"), self.rows("panel1")
        self.assertTrue(m.achieved_norm_match(targets, panels)["pass"])
        for row in panels:
            row["result"]["telemetry"]["delivery"]["realized_norm"] = [1.3] * 21
        result = m.achieved_norm_match(targets, panels)
        self.assertFalse(result["pass"])
        self.assertAlmostEqual(result["directions"]["suppression"]["quantiles"]["p90"]["ratio"], 1.3)

    def test_paired_zeros_retained_not_independently_dropped(self):
        targets, panels = self.rows("target"), self.rows("panel1")
        for row in panels:
            d = row["result"]["telemetry"]["delivery"]
            d["realized_norm"] = [0.] * 21
            d["cosine"] = [0.] * 21
            d["relative_error"] = [1.] * 21
            d["identity"] = [True] * 21
        result = m.achieved_norm_match(targets, panels)
        self.assertFalse(result["pass"])
        self.assertEqual(result["directions"]["suppression"]["paired_edit_positions"], 126)
        self.assertEqual(result["directions"]["suppression"]["panel_zero_positions"], 126)

    def test_heldout_scope_wrong_dose_and_missing_rows_rejected(self):
        for kind in ("validation", "dose", "missing"):
            targets, panels = self.rows("target"), self.rows("panel1")
            if kind == "validation":
                panels[0]["split"] = "validation"
            elif kind == "dose":
                panels[0]["strength"] = 1.
            else:
                panels.pop()
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                m.achieved_norm_match(targets, panels)


class OptionalTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.run = FakeRun(self.temp.name)

    def test_exact_budget_arithmetic_and_boundary(self):
        result = m.remainder_budget(self.run)
        self.assertEqual(result["baseline_estimate_seconds"], 3 * 2. * 210)
        self.assertEqual(result["estimate_seconds"], 1260 + 1200 + 210)
        self.assertTrue(result["pass"])
        self.run.deadline = self.run.now + result["estimate_seconds"] + 1800
        self.assertFalse(m.remainder_budget(self.run)["pass"])

    def test_missing_or_nonfinite_timing_fails_closed(self):
        self.run.data["judge-paper-core-0"] = {}
        self.assertFalse(m.remainder_budget(self.run)["pass"])
        self.run.data["judge-paper-core-0"] = {"elapsed_seconds": float("nan")}
        self.assertFalse(m.remainder_budget(self.run)["pass"])

    def test_failed_fixture_branch_not_silently_estimated_as_work(self):
        put(self.run.out / "local-paper-fixtures.json", {"pass": False})
        del self.run.data["judge-paper-core-0"]
        result = m.remainder_budget(self.run)
        self.assertTrue(result["pass"])
        self.assertEqual(result["judge_estimates"]["paper"]["status"], "not_run_by_gate")

    def test_target_failure_stops_without_model_or_pool(self):
        put(self.run.out / "target-delivery.json", {"pass": False})
        result = m.optional(self.run)
        self.assertEqual(result["status"], "not_run_by_gate")
        self.assertEqual(self.run.teacher_calls, [])

    def test_missing_core_stops_before_optional_collection(self):
        del self.run.data["core-0"]
        self.assertEqual(m.optional(self.run)["status"], "not_run_by_gate")
        self.assertEqual(self.run.teacher_calls, [])

    def test_all_panels_fixed_dose_then_full_remainder(self):
        result = m.optional(self.run)
        self.assertEqual(result["status"], "complete", result)
        delivered = [r for r in self.run.calls if r[0] == "delivery"]
        self.assertEqual([r[1] for r in delivered], ["panel1", "panel2", "panel3"])
        self.assertEqual([r[3] for r in delivered], [.5] * 3)
        self.assertEqual(self.run.calls[-2:], [("baseline", "optional"), ("local_judges", "optional")])
        self.assertEqual(len(result["response_inventory"]), 210)
        self.assertEqual(len(self.run.teacher_calls), 48)
        self.assertTrue(all(len(ids) == 518 and full is False for _, ids, full in self.run.teacher_calls))
        previous = len(self.run.calls)
        self.assertEqual(m.optional(self.run), result)
        self.assertEqual(len(self.run.calls), previous)

    def test_panel_failure_is_preserved_without_rematching_or_baselines(self):
        self.run.panel_fail = "panel2"
        result = m.optional(self.run)
        self.assertEqual(result["status"], "not_run_by_gate")
        self.assertFalse(result["panels"][1]["pass"])
        self.assertFalse(any(c[0] == "baseline" for c in self.run.calls))
        matched = json.loads((self.run.out / "optional-matching.json").read_text())
        self.assertEqual(len(matched["panels"]), 3)

    def test_norm_mismatch_blocks_remaining_baselines(self):
        self.run.norm_scale = 1.3
        result = m.optional(self.run)
        self.assertEqual(result["status"], "not_run_by_gate")
        self.assertFalse(result["panels"][0]["norm_match"]["pass"])

    def test_affordability_blocks_whole_remainder_not_selected_cells(self):
        self.run.deadline = self.run.now + 3000
        result = m.optional(self.run)
        self.assertEqual(result["status"], "not_run_budget")
        self.assertFalse(any(c[0] == "baseline" for c in self.run.calls))

    def test_partial_remainder_is_incomplete_not_never_run(self):
        self.run.data["optional-0"] = {"status": "ok"}
        self.run.deadline = self.run.now + 3000
        result = m.optional(self.run)
        self.assertEqual(result["status"], "incomplete")
        self.assertEqual(result["remainder_status"], "incomplete")

    def test_budget_before_start_versus_midcollection_are_distinct(self):
        self.run.deadline = self.run.now + 100
        self.assertEqual(m.optional(self.run)["status"], "not_run_budget")
        (self.run.out / "optional.json").unlink()
        self.run.deadline = 100000
        self.run.timeout_after = 2
        result = m.optional(self.run)
        self.assertEqual(result["status"], "incomplete")
        self.assertEqual(result["remainder_status"], "not_run_budget")
        self.assertEqual(len(self.run.teacher_calls), 2)


if __name__ == "__main__":
    unittest.main()

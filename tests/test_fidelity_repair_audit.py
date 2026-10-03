"""CPU-only raw-artifact adversarial tests plus optional real tiny-backend QA."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from experiments.steering_fidelity.protocol import canonical, sha
from experiments.steering_fidelity_repair import analysis, audit, liveness, protocol


PLAN_HASH, FREEZE = "a" * 64, "b" * 40


def plan_fixture():
    sections = {"discovery_rows": protocol.discovery_rows(),
                "validation_neutral_rows": protocol.validation_neutral_rows(),
                "validation_rows": {c: protocol.validation_rows(c) for c in ("P0", "P1")},
                "singleton_rows": protocol.singleton_rows(),
                "teacher_rows": [{**r, "task": "teacher"} for r in liveness.teacher_inventory()],
                "generation_rows": [{**r, "task": "generation"} for r in liveness.generation_inventory()]}
    rows = sections["discovery_rows"] + sections["validation_neutral_rows"]
    rows += sections["validation_rows"]["P0"] + sections["validation_rows"]["P1"]
    rows += sections["singleton_rows"] + sections["teacher_rows"] + sections["generation_rows"]
    return {**sections, "rows": rows,
            "fixed_dose": {"rho": .30, "reference_norm": 18.246721267700195,
                           "requested_norm": audit.REQUESTED_NORM}}


def positions(prefix, body=(), teacher=False):
    return [{"position": at, "token_id": token, "special": False,
             "origin": "prompt" if at < len(prefix) else "teacher_forced" if teacher else "generated",
             "terminal_observation_only": bool(body) and not teacher and at == len(prefix) + len(body) - 1}
            for at, token in enumerate(list(prefix) + list(body))]


def telemetry(prefix, body, intervention):
    n = len(prefix) + len(body)
    norm = 0. if intervention is None else intervention["requested_norm"]
    ids = [30032, 58667, 22004, 30686, 41533, 23893]
    if body and intervention is not None:
        ids = intervention["feature_ids"]
    return {"schema": "steering_fidelity_additive_v1", "feature_ids": ids, "hook": 50,
            "hook_removed": True, "native_dtype": "torch.bfloat16",
            "encoding_authority": "full_native_token1_v1", "intervention": intervention,
            "reencoding_scope": "last_prefill_and_each_cached_token",
            "reencoding": [{"position": at, "before": [0.] * len(ids), "after": [0.] * len(ids)}
                           for at in [len(prefix) - 1] + list(range(len(prefix), n))],
            "position_metadata": positions(prefix, body),
            "delivery": {"requested_norm": [norm] * n, "realized_norm": [norm] * n,
                         "cosine": [1.] * n, "relative_error": [0.] * n,
                         "norm_ratio": [norm / 18.] * n, "hidden_norm": [18.] * n}}


def probe(prefix, body, teacher=False, active=True):
    return {"schema": "fidelity_position_probe_v1", "feature_ids": [11104, 27322],
            "encoding": "native_full_dictionary_one_position_at_a_time", "dictionary_width": 65536,
            "hook": 50, "dtype": "torch.bfloat16",
            "observation": "before_current_additive_edit; edited_history_if_intervened",
            "meaning": "Feature activation/exposure, not semantic validation or behavioral liveness",
            "call_lengths": [len(prefix) + len(body)] if teacher else [len(prefix)] + [1] * len(body),
            "positions": [{**p, "activations": [float(active), float(active)]}
                          for p in positions(prefix, body, teacher)]}


def score(row, probability):
    row.update(p_correct=probability, p_yes=probability if row["truth"] else 1 - probability,
               p_no=1 - probability if row["truth"] else probability, valid_mass=1.,
               correct=probability > .5, format_valid=True)
    row["predicted_answer"] = "Yes" if row["p_yes"] >= row["p_no"] else "No"
    row["top_token_id"] = 8 if row["predicted_answer"] == "Yes" else 9
    row["top_token"] = row["predicted_answer"]


def row_fixture(spec, selected="P0", singleton_pass=True):
    edit = protocol.intervention(spec)
    row = {**copy.deepcopy(spec), "missing": False, "plan_sha256": PLAN_HASH, "freeze_commit": FREEZE,
           "elapsed_seconds": .25, "intervention": edit}
    prefix, body = [5, 6], [10, 11]
    if spec["task"] == "choice":
        raw = telemetry(prefix, [], edit)
        row.update(token_sets={"yes": [8], "no": [9]}, input_token_ids=prefix,
                   input_token_ids_sha256=audit._token_hash(prefix), rendered_input_sha256="c" * 64,
                   telemetry=raw, delivery_raw=copy.deepcopy(raw["delivery"]),
                   delivery=audit.delivery_summary(raw), screen=None)
        probability = .99
        if spec["pressure_id"] == selected and selected is not None:
            bank = protocol.items.items(spec["split"])
            group = [item["id"] for item in bank if item["family"] == spec["family"]
                     and item["truth"] == spec["truth"]]
            opposed = spec["frame"] == ("doubt" if spec["truth"] else "assert")
            if opposed and group.index(spec["item_id"]) < 3:
                probability = .1
        if edit is not None and not singleton_pass:
            probability = .1
        score(row, probability)
    elif spec["task"] == "teacher":
        text = spec["continuation"]
        row["probe"] = {"schema": "fidelity_teacher_probe_v1", "continuation": text,
                        "continuation_sha256": hashlib.sha256(text.encode()).hexdigest(),
                        "serialization": "chat_generation_prefix_ids_plus_separately_encoded_body",
                        "execution": "clean_full_prefill_not_cached_generation",
                        "token_ids_sha256": audit._token_hash(prefix + body),
                        "input_token_ids": prefix, "continuation_token_ids": body,
                        "position_probe": probe(prefix, body, True, spec["body_kind"] == "json")}
    else:
        row["result"] = {"response": "{}" if spec["context"] == "json" or edit else "Some prose.",
                         "input_tokens": len(prefix), "output_tokens": len(body), "cap_hit": False,
                         "input_token_ids": prefix, "output_token_ids": body,
                         "input_token_ids_sha256": audit._token_hash(prefix),
                         "rendered_input_sha256": "c" * 64, "elapsed_seconds": .2,
                         "telemetry": telemetry(prefix, body, edit)}
        row["position_probe"] = probe(prefix, body)
    return row


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(canonical(value) + "\n")


class Window:
    def __init__(self, root, selected="P0", singleton_pass=True):
        self.root, self.plan = root, plan_fixture()
        self.selected, self.singleton_pass = selected, singleton_pass
        self.events, self.rows = [], {}

    def event(self, kind, identifier, **extra):
        event = {"index": len(self.events), "previous": self.events[-1]["sha256"] if self.events else "0" * 64,
                 "utc": "2026-10-03T00:00:00+00:00", "kind": kind, "row_id": identifier,
                 "plan_sha256": PLAN_HASH, "freeze_commit": FREEZE, **extra}
        event["sha256"] = hashlib.sha256(canonical(event).encode()).hexdigest()
        self.events.append(event)
        with (self.root / "receipts.jsonl").open("a") as handle:
            handle.write(canonical(event) + "\n")

    def collect(self, specs):
        rows = []
        for spec in specs:
            identifier = spec["id"]
            row = row_fixture(spec, self.selected, self.singleton_pass)
            self.event("dispatch", identifier)
            path = self.root / "forwards" / (identifier + ".json")
            write(path, row)
            self.event("complete", identifier, payload_sha256=sha(path))
            self.rows[identifier] = row
            rows.append(row)
        return rows

    def decision(self, name, value):
        write(self.root / (name + "-decision.json"), {"decision": value, "plan_sha256": PLAN_HASH,
              "freeze_commit": FREEZE, "after_receipt_sha256": self.events[-1]["sha256"],
              "stage_t_authorized": False})

    def run(self, stop=None):
        discovery = self.collect(self.plan["discovery_rows"])
        if stop == "discovery":
            return
        self.decision("discovery", audit.discovery_gate(discovery))
        neutral = self.collect(self.plan["validation_neutral_rows"])
        validation = {"status": "not_run", "reason": "no_discovery_candidate_passed",
                      "pass": False, "stage_t_authorized": False}
        if self.selected:
            pressure = self.collect(self.plan["validation_rows"][self.selected])
            validation = audit.validation_gate(neutral + pressure, self.selected)
        if stop == "validation":
            return
        self.decision("validation", validation)
        edited = self.collect(self.plan["singleton_rows"])
        if stop == "singleton":
            return
        self.decision("singleton", analysis.singleton_gate(neutral + edited))
        teacher = self.collect(self.plan["teacher_rows"])
        generated = self.collect(self.plan["generation_rows"]) if self.singleton_pass else []
        if stop == "liveness":
            return
        self.decision("liveness", liveness.summarize(teacher, generated, singleton_pass=self.singleton_pass))

    def audit(self, partial=True):
        return audit.audit_raw_window(self.root, self.plan, PLAN_HASH, FREEZE, partial)

    def rechain(self):
        previous = "0" * 64
        for at, event in enumerate(self.events):
            event.update(index=at, previous=previous)
            event.pop("sha256", None)
            event["sha256"] = hashlib.sha256(canonical(event).encode()).hexdigest()
            previous = event["sha256"]
        (self.root / "receipts.jsonl").write_text("".join(canonical(e) + "\n" for e in self.events))


class AuditTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        # Unit tests keep the estimator algorithm, using fewer deterministic draws.
        for module in (analysis, liveness):
            patcher = patch.object(module, "BOOTSTRAP_DRAWS", 100)
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_import_does_not_load_torch(self):
        result = subprocess.run([sys.executable, "-c", "import sys; "
            "from experiments.steering_fidelity_repair import audit; assert 'torch' not in sys.modules"],
            cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_full_conditional_inventories_and_independent_branches(self):
        for candidate in (None, "P0", "P1"):
            for singleton in (False, True):
                with self.subTest(candidate=candidate, singleton=singleton):
                    root = self.root / f"{candidate}-{singleton}"
                    root.mkdir()
                    window = Window(root, candidate, singleton)
                    window.run()
                    result = window.audit(False)
                    expected = 368 + 80 * (candidate is not None) + 72 * singleton
                    self.assertEqual(result["forwards"], expected)
                    self.assertEqual(result["forward_seconds"], [.25] * expected)
                    self.assertEqual(result["unresolved_forward_ids"], [])
                    self.assertTrue(result["pass"] and result["complete"])
                    self.assertFalse((root / "complete.json").exists())
                    self.assertEqual(len([r for r in window.rows.values() if r["task"] == "teacher"]), 48)

    def test_empty_and_valid_prefix(self):
        window = Window(self.root)
        self.assertEqual(window.audit()["forwards"], 0)
        window.collect(window.plan["discovery_rows"][:5])
        result = window.audit()
        self.assertTrue(result["pass"])
        self.assertFalse(result["complete"])
        self.assertEqual(result["forwards"], 5)
        with self.assertRaises(ValueError):
            window.audit(False)

    def test_each_stage_can_end_before_its_decision_but_not_cross_it(self):
        next_section = {"discovery": "validation_neutral_rows", "validation": "singleton_rows",
                        "singleton": "teacher_rows"}
        for stage in ("discovery", "validation", "singleton", "liveness"):
            with self.subTest(stage=stage):
                root = self.root / stage
                root.mkdir()
                window = Window(root)
                window.run(stop=stage)
                self.assertTrue(window.audit()["pass"])
                self.assertFalse(window.audit()["complete"])
                with self.assertRaises(ValueError):
                    window.audit(False)
                if stage in next_section:
                    window.event("dispatch", window.plan[next_section[stage]][0]["id"])
                    with self.assertRaisesRegex(ValueError, "barrier"):
                        window.audit()

    def test_unresolved_dispatch_with_and_without_valid_disk_row(self):
        window = Window(self.root)
        spec = window.plan["discovery_rows"][0]
        window.event("dispatch", spec["id"])
        for disk in (False, True):
            if disk:
                write(self.root / "forwards" / (spec["id"] + ".json"), row_fixture(spec))
            result = window.audit()
            self.assertFalse(result["pass"] or result["complete"])
            self.assertEqual(result["unresolved_forward_ids"], [spec["id"]])
            self.assertEqual(result["forwards"], 0)
        row = row_fixture(spec)
        row["missing"] = True
        write(self.root / "forwards" / (spec["id"] + ".json"), row)
        with self.assertRaises(ValueError):
            window.audit()

    def test_forged_decisions_and_all_bindings(self):
        window = Window(self.root)
        window.run()
        for name in ("discovery", "validation", "singleton", "liveness"):
            path = self.root / (name + "-decision.json")
            original = json.loads(path.read_text())
            for field, value in (("plan_sha256", "d" * 64), ("freeze_commit", "e" * 40),
                                 ("after_receipt_sha256", window.events[0]["sha256"]),
                                 ("stage_t_authorized", True), ("extra_binding", PLAN_HASH)):
                with self.subTest(name=name, field=field):
                    write(path, {**original, field: value})
                    with self.assertRaises(ValueError):
                        window.audit(False)
            changed = copy.deepcopy(original)
            changed["decision"]["pass"] = not changed["decision"]["pass"]
            write(path, changed)
            with self.assertRaises(ValueError):
                window.audit(False)
            write(path, original)

    def test_decision_cannot_bind_dispatch_or_later_complete(self):
        window = Window(self.root)
        window.run(stop="validation")
        path = self.root / "discovery-decision.json"
        original = json.loads(path.read_text())
        for index in (398, 401):
            write(path, {**original, "after_receipt_sha256": window.events[index]["sha256"]})
            with self.assertRaisesRegex(ValueError, "misordered"):
                window.audit()

    def test_premature_unknown_and_skipped_decision_files(self):
        window = Window(self.root)
        for name in ("discovery", "validation", "singleton", "liveness", "invented"):
            path = self.root / (name + "-decision.json")
            write(path, {})
            with self.assertRaisesRegex(ValueError, "decision artifact"):
                window.audit()
            path.unlink()

    def test_conditional_generation_and_teacher_may_not_be_skipped(self):
        window = Window(self.root, None, False)
        window.run()
        window.event("dispatch", window.plan["generation_rows"][0]["id"])
        with self.assertRaises(ValueError):
            window.audit()
        window.events = window.events[:640]
        window.rechain()
        with self.assertRaises(ValueError):
            window.audit(False)

    def test_unselected_pressure_must_not_run(self):
        window = Window(self.root, "P1")
        discovery = window.collect(window.plan["discovery_rows"])
        window.decision("discovery", audit.discovery_gate(discovery))
        window.collect(window.plan["validation_neutral_rows"])
        window.event("dispatch", window.plan["validation_rows"]["P0"][0]["id"])
        with self.assertRaisesRegex(ValueError, "order"):
            window.audit()

    def test_neutral_cannot_be_skipped_after_discovery_failure(self):
        window = Window(self.root, None)
        discovery = window.collect(window.plan["discovery_rows"])
        window.decision("discovery", audit.discovery_gate(discovery))
        window.event("dispatch", window.plan["singleton_rows"][0]["id"])
        with self.assertRaises(ValueError):
            window.audit()

    def test_receipt_order_duplicate_completion_and_redispatch(self):
        window = Window(self.root)
        window.collect(window.plan["discovery_rows"][:2])
        original = copy.deepcopy(window.events)
        changes = ([original[1]], [original[0], original[2], original[1], original[3]],
                   original[:2] * 2, original + [original[3]],
                   [original[2], original[3], original[0], original[1]])
        for events in changes:
            window.events = copy.deepcopy(events)
            window.rechain()
            with self.assertRaises(ValueError):
                window.audit()

    def test_receipt_hash_bindings_unknown_malformed_and_extras(self):
        window = Window(self.root)
        window.collect(window.plan["discovery_rows"][:1])
        original = copy.deepcopy(window.events)
        for field, value in (("plan_sha256", "d" * 64), ("freeze_commit", "e" * 40),
                             ("row_id", "unknown"), ("kind", "skip"), ("extra_binding", FREEZE),
                             ("payload_sha256", "f" * 64)):
            window.events = copy.deepcopy(original)
            window.events[-1][field] = value
            window.rechain()
            with self.subTest(field=field), self.assertRaises(ValueError):
                window.audit()
        window.events = copy.deepcopy(original)
        window.rechain()
        path = self.root / "receipts.jsonl"
        raw = path.read_text()
        for changed in (raw.rstrip(), raw.replace('"index":0', '"index":true'),
                        raw.replace('"kind":"dispatch"', '"kind":"complete","kind":"dispatch"'),
                        raw.replace('"previous":"' + '0' * 64, '"previous":"' + '1' * 64)):
            path.write_text(changed)
            with self.assertRaises(ValueError):
                window.audit()

    def test_missing_changed_unknown_and_symlinked_payloads(self):
        window = Window(self.root)
        spec = window.plan["discovery_rows"][0]
        window.collect([spec])
        path = self.root / "forwards" / (spec["id"] + ".json")
        raw = path.read_bytes()
        path.unlink()
        with self.assertRaises(ValueError):
            window.audit()
        path.write_bytes(raw + b" ")
        with self.assertRaisesRegex(ValueError, "hash"):
            window.audit()
        path.write_bytes(raw)
        extra = path.with_name("unknown.json")
        extra.write_bytes(raw)
        with self.assertRaisesRegex(ValueError, "unreceipted"):
            window.audit()
        path.unlink()
        path.symlink_to(extra)
        with self.assertRaisesRegex(ValueError, "symlinked"):
            window.audit()

    def test_invalid_plan_inventory_and_fixed_dose(self):
        window = Window(self.root)
        for mutate in (lambda p: p["rows"].pop(),
                       lambda p: p["teacher_rows"].pop(),
                       lambda p: p["fixed_dose"].update(requested_norm=1.),
                       lambda p: p["validation_rows"].update(P2=[]),
                       lambda p: p["discovery_rows"][0].update(id="../escape")):
            plan = copy.deepcopy(window.plan)
            mutate(plan)
            with self.assertRaises(ValueError):
                audit.audit_raw_window(self.root, plan, PLAN_HASH, FREEZE)

    def test_all_spec_fields_and_no_extra_row_bindings(self):
        plan = plan_fixture()
        for section in ("discovery_rows", "singleton_rows", "teacher_rows", "generation_rows"):
            spec = plan[section][0]
            row = row_fixture(spec)
            audit.validate_row(row, spec, PLAN_HASH, FREEZE)
            audit.validate_row(row, spec, PLAN_HASH, FREEZE, plan)
            for field in spec:
                changed = copy.deepcopy(row)
                changed[field] = "forged"
                with self.subTest(section=section, field=field), self.assertRaises(ValueError):
                    audit.validate_row(changed, spec, PLAN_HASH, FREEZE, plan)
            for field, value in (("extra_binding", FREEZE), ("missing", 0), ("elapsed_seconds", True),
                                 ("elapsed_seconds", 0), ("elapsed_seconds", float("nan")),
                                 ("plan_sha256", "wrong"), ("freeze_commit", "wrong")):
                with self.subTest(section=section, field=field), self.assertRaises(ValueError):
                    audit.validate_row({**row, field: value}, spec, PLAN_HASH, FREEZE)

    def test_choice_malformed_score_and_delivery(self):
        spec = plan_fixture()["discovery_rows"][0]
        row = row_fixture(spec)
        changes = [lambda r: r.update(correct=1), lambda r: r.update(p_correct=.5),
                   lambda r: r.update(valid_mass=0), lambda r: r.update(p_no=float("inf")),
                   lambda r: r.update(format_valid=0), lambda r: r.update(predicted_answer="Wrong"),
                   lambda r: r["token_sets"].update(no=[8]),
                   lambda r: r.update(input_token_ids_sha256="d" * 64),
                   lambda r: r["telemetry"]["position_metadata"][0].update(token_id=7),
                   lambda r: r["telemetry"]["delivery"]["realized_norm"].__setitem__(0, 1.),
                   lambda r: r["delivery_raw"]["hidden_norm"].pop(),
                   lambda r: r["delivery"].update(qualified=False),
                   lambda r: r["telemetry"]["reencoding"][0].update(after=[1.] * 6),
                   lambda r: r.update(screen={"positive_ids": []})]
        for mutate in changes:
            changed = copy.deepcopy(row)
            mutate(changed)
            with self.assertRaises(ValueError):
                audit.validate_row(changed, spec, PLAN_HASH, FREEZE)
        score(row, .5)
        audit.validate_row(row, spec, PLAN_HASH, FREEZE)
        self.assertFalse(row["correct"])

    def test_positive_intervention_fields_and_delivered_norm_bound(self):
        spec = plan_fixture()["singleton_rows"][0]
        row = row_fixture(spec)
        for field, value in (("feature_ids", [27322]), ("weights", [.6]), ("sign", True),
                             ("sign", 1.), ("sign", -1), ("requested_norm", 1.), ("extra", 1)):
            changed = copy.deepcopy(row)
            changed["intervention"][field] = value
            with self.assertRaises(ValueError):
                audit.validate_row(changed, spec, PLAN_HASH, FREEZE)
        changed = copy.deepcopy(row)
        changed["telemetry"]["delivery"]["requested_norm"][0] *= 2
        with self.assertRaises(ValueError):
            audit.validate_row(changed, spec, PLAN_HASH, FREEZE)
        # Failed delivery is a valid measured failure, never an invalid artifact.
        for key in ("cosine", "realized_norm"):
            row["telemetry"]["delivery"][key] = [0., 0.]
        row["delivery_raw"] = copy.deepcopy(row["telemetry"]["delivery"])
        row["delivery"] = audit.delivery_summary(row["telemetry"])
        audit.validate_row(row, spec, PLAN_HASH, FREEZE)
        self.assertFalse(row["delivery"]["qualified"])

    def test_teacher_and_generation_alignment_nonfinite_and_binding(self):
        plan = plan_fixture()
        for section in ("teacher_rows", "generation_rows"):
            spec = plan[section][0]
            row = row_fixture(spec)
            base = row["probe"]["position_probe"] if spec["task"] == "teacher" else row["position_probe"]
            changes = [lambda p: p["call_lengths"].append(1), lambda p: p["positions"].pop(),
                       lambda p: p.update(feature_ids=[27322, 11104]),
                       lambda p: p.update(dictionary_width=12), lambda p: p.update(hook=49),
                       lambda p: p["positions"][-1].update(origin="prompt"),
                       lambda p: p["positions"][-1].update(token_id=999),
                       lambda p: p["positions"][-1].update(activations=[1.]),
                       lambda p: p["positions"][-1].update(activations=[float("nan"), 0.]),
                       lambda p: p["positions"][-1].update(activations=[True, 0.]),
                       lambda p: p["positions"][-1].update(activations=[-1., 0.]),
                       lambda p: p["positions"][0].update(terminal_observation_only=True)]
            for mutate in changes:
                changed = copy.deepcopy(row)
                target = changed["probe"]["position_probe"] if spec["task"] == "teacher" else changed["position_probe"]
                self.assertEqual(target, base)
                mutate(target)
                with self.assertRaises(ValueError):
                    audit.validate_row(changed, spec, PLAN_HASH, FREEZE)

    def test_teacher_clean_only_hash_and_generation_result_checks(self):
        plan = plan_fixture()
        spec = plan["teacher_rows"][0]
        row = row_fixture(spec)
        for mutate in (lambda r: r.update(intervention=protocol.intervention(plan["singleton_rows"][0])),
                       lambda r: r["probe"].update(continuation_sha256="d" * 64),
                       lambda r: r["probe"].update(token_ids_sha256="e" * 64),
                       lambda r: r["probe"]["position_probe"]["positions"][-1].update(special=True)):
            changed = copy.deepcopy(row)
            mutate(changed)
            with self.assertRaises(ValueError):
                audit.validate_row(changed, spec, PLAN_HASH, FREEZE)
        spec = plan["generation_rows"][0]
        row = row_fixture(spec)
        for key, value in (("output_tokens", 1), ("cap_hit", True), ("response", None),
                           ("elapsed_seconds", 0), ("plan_sha256", PLAN_HASH)):
            changed = copy.deepcopy(row)
            changed["result"][key] = value
            with self.assertRaises(ValueError):
                audit.validate_row(changed, spec, PLAN_HASH, FREEZE)

    def test_released_backend_score_payload_shape(self):
        root = Path(__file__).resolve().parents[1]
        path = root / "data/steering_fidelity/calibration_v1_20261002/forwards/zero-context-calibration-040.json"
        self.assertTrue(path.is_file(), "Required public payload fixture missing from frozen runtime bundle")
        original = json.loads(path.read_text())
        spec = plan_fixture()["discovery_rows"][0]
        row = {**spec, **{k: original[k] for k in audit._CHOICE}, "missing": False,
               "plan_sha256": PLAN_HASH, "freeze_commit": FREEZE,
               "elapsed_seconds": original["elapsed_seconds"], "intervention": None}
        # Rebind only the gold label to this synthetic row; preserve raw backend payload.
        probability = (row["p_yes"] if spec["truth"] else row["p_no"]) / row["valid_mass"]
        row.update(p_correct=probability, correct=probability > .5, screen=None)
        audit.validate_row(row, spec, PLAN_HASH, FREEZE)

    @unittest.skipUnless(all(importlib.util.find_spec(m) for m in ("torch", "transformers", "pytest")),
                         "Optional native tiny-backend dependencies not installed")
    def test_real_tiny_backend_score_teacher_and_generated_probe(self):
        import torch
        from tests.test_steering_fidelity_backend import tiny
        from experiments.steering_fidelity_repair.activation_probe import teacher_probe, generated_probe
        fixture = tiny.__wrapped__()
        backend = next(fixture)
        try:
            # Full native dictionary width, but hidden size 16 and two random
            # model layers: payload integration only, never a 70B/CUDA gate.
            encoder, bias, decoder, decoder_bias = backend._sae
            expanded_encoder = encoder.new_zeros((65536, 16))
            expanded_bias = bias.new_zeros(65536)
            expanded_decoder = decoder.new_zeros((16, 65536))
            for source, target in ((0, 11104), (3, 27322)):
                expanded_encoder[target] = encoder[source]
                expanded_bias[target] = bias[source]
                expanded_decoder[:, target] = decoder[:, source]
            backend._sae = (expanded_encoder, expanded_bias, expanded_decoder, decoder_bias)
            physical_layer = backend._layer
            backend.layer_index = 50  # Test-only hook label; the hooked tiny block is unchanged.
            backend.default_feature_ids = (30032, 58667, 22004, 30686, 41533, 23893)
            self.assertIs(backend._layer, physical_layer)
            self.assertEqual(backend.model.config.num_hidden_layers, 2)
            self.assertTrue(all(t.dtype == torch.bfloat16 for t in backend._sae))
            messages = [{"role": "user", "content": "Is two plus two four?"}]
            for feature in (None, 11104, 27322):
                spec = {**plan_fixture()["discovery_rows"][0], "prompt": messages[0]["content"],
                        "feature_id": feature, "arm": "zero" if feature is None else f"positive-{feature}"}
                edit = protocol.intervention(spec)
                result = backend.score(messages, spec["truth"], edit)
                row = {**spec, **result, "missing": False, "plan_sha256": PLAN_HASH,
                       "freeze_commit": FREEZE, "intervention": edit,
                       "delivery": audit.delivery_summary(result["telemetry"])}
                audit.validate_row(row, spec, PLAN_HASH, FREEZE)
            spec = {"id": "tiny-teacher", "task": "teacher", "feature_id": None,
                    "continuation": "known body", "prompt": messages[0]["content"]}
            backend.tokenizer.encodings[spec["continuation"]] = [4, 5, 6]
            row = {**spec, "probe": teacher_probe(backend, messages, spec["continuation"], (11104, 27322)),
                   "missing": False, "plan_sha256": PLAN_HASH, "freeze_commit": FREEZE,
                   "intervention": None, "elapsed_seconds": .1}
            audit.validate_row(row, spec, PLAN_HASH, FREEZE)
            for feature in (None, 11104, 27322):
                spec = {"id": "tiny-generation", "task": "generation", "feature_id": feature,
                        "arm": "zero" if feature is None else f"positive-{feature}", "max_new_tokens": 3}
                edit = protocol.intervention(spec)
                output = generated_probe(backend, messages, (11104, 27322), seed=81,
                                         max_new_tokens=3, intervention=edit)
                row = {**spec, **output, "missing": False, "plan_sha256": PLAN_HASH,
                       "freeze_commit": FREEZE, "intervention": edit, "elapsed_seconds": .1}
                audit.validate_row(row, spec, PLAN_HASH, FREEZE)
        finally:
            try:
                next(fixture)
            except StopIteration:
                pass


if __name__ == "__main__":
    unittest.main()

"""Control-flow tests use explicitly synthetic rows, never real model outcomes."""
from copy import deepcopy
import itertools
import json
from unittest.mock import patch

import pytest

from experiments.steering_fidelity_repair import protocol as p, runner as r
from tests.test_fidelity_repair_pressure_gate import synthetic
from tests.test_steering_fidelity_protocol import literal_backend_pins
from tests.test_steering_fidelity_runner import FakeBackend as OldFakeBackend

FREEZE = "a" * 40
DEADLINE = "2100-01-01T00:00:00+00:00"


@pytest.fixture
def plan():
    with literal_backend_pins():
        return p.build_plan()


def make_study(tmp_path, plan, barriers=False):
    path = tmp_path / "PLAN.json"
    path.write_text(p.canonical(plan) + "\n")
    backend = OldFakeBackend()
    study = r.Study(plan, path, FREEZE, tmp_path / "run", DEADLINE,
                    lambda **kwargs: backend, barriers=barriers)
    study.backend = backend
    return study


@pytest.mark.parametrize("pressure_pass,singleton_pass", [(a, b) for a in (False, True) for b in (False, True)])
def test_independent_branches_persist_selection_before_validation(tmp_path, plan, pressure_pass, singleton_pass):
    study = make_study(tmp_path, plan)
    scores = {s["id"]: s for s in synthetic() + synthetic("validation", "P0")}
    seen = []

    def row(spec):
        if spec.get("split") == "validation":
            assert (study.out / "discovery-decision.json").exists()
        if spec["task"] == "generation":
            decision = json.loads((study.out / "singleton-decision.json").read_text())
            assert decision["decision"]["pass"] is True
        seen.append(spec)
        payload = {**spec, **scores.get(spec["id"], {})}
        if spec["task"] == "choice" and not pressure_pass:
            payload.update(correct=True, p_correct=.99, valid_mass=1.,
                           p_yes=.99 if spec["truth"] else .01,
                           p_no=.01 if spec["truth"] else .99)
        # An explicit synthetic receipt chain exercises persisted-decision binding.
        study.journal.append("dispatch", spec["id"])
        study.journal.append("complete", spec["id"], payload_sha256="0" * 64)
        study.results[spec["id"]] = payload
        return payload

    with patch.object(study, "row", side_effect=row), \
            patch("experiments.steering_fidelity_repair.analysis.singleton_gate",
                  return_value={"pass": singleton_pass}), \
            patch("experiments.steering_fidelity_repair.liveness.summarize",
                  return_value={"pass": singleton_pass}), \
            patch("experiments.steering_fidelity_repair.audit.audit_raw_window",
                  return_value={"pass": True, "complete": True}):
        study.run()
    assert len(seen) == 368 + (80 if pressure_pass else 0) + (72 if singleton_pass else 0)
    assert sum(s["task"] == "teacher" for s in seen) == 48
    assert sum(s["task"] == "generation" for s in seen) == (72 if singleton_pass else 0)
    decision = json.loads((study.out / "discovery-decision.json").read_text())
    assert decision["after_receipt_sha256"] == study.journal.events[399]["sha256"]
    assert decision["decision"]["selected"] == ("P0" if pressure_pass else None)
    finished = json.loads((study.out / "complete.json").read_text())
    assert finished["meaning"] == "conditional_inventory_complete_not_scientific_gate"
    assert finished["stage_t_authorized"] is False
    assert finished["e_only_fallback"] is False
    if not pressure_pass:
        assert json.loads((study.out / "validation-decision.json").read_text())["decision"]["status"] == "not_run"


def test_row_barriers_and_no_screening_or_untracked_dispatch(tmp_path, plan):
    study = make_study(tmp_path, plan, barriers=True)
    observed = []
    def approve(_seconds):
        count = len(study.results)
        name = {5: "first-rows", 20: "throughput"}[count]
        observed.append(count)
        waiting = json.loads((study.out / f"WAITING-{name}.json").read_text())
        assert waiting["forwards"] == count
        (study.out / f"APPROVE-{name}").write_text(study.plan_hash)
    with patch("experiments.steering_fidelity_repair.audit.validate_row"), \
            patch("experiments.steering_fidelity_repair.audit.audit_raw_window"), \
            patch.object(r.time, "sleep", side_effect=approve):
        for spec in plan["discovery_rows"][:21]:
            study.row(spec)
    assert observed == [5, 20]
    assert all(call[2] is None and call[3] is False for call in study.backend.calls)
    assert len(study.journal.events) == 42
    assert all(e["plan_sha256"] == study.plan_hash for e in study.journal.events)
    with pytest.raises(ValueError, match="Duplicate"):
        study.row(plan["discovery_rows"][0])


def test_invalid_return_is_preserved_and_not_automatically_retried(tmp_path, plan):
    study = make_study(tmp_path, plan)
    spec = plan["discovery_rows"][0]
    with patch("experiments.steering_fidelity_repair.audit.validate_row", side_effect=ValueError("invalid fixture")):
        with pytest.raises(ValueError, match="invalid fixture"):
            study.row(spec)
    assert (study.out / "forwards" / (spec["id"] + ".json")).exists()
    assert len(study.journal.events) == 1
    with pytest.raises(ValueError, match="resume"):
        make_study(tmp_path, plan)


def test_deadline_stop_and_wrong_approval_fail_closed(tmp_path, plan):
    study = make_study(tmp_path, plan, barriers=True)
    with patch.object(r.time, "time", return_value=study.deadline):
        with pytest.raises(TimeoutError):
            study.check_time()
    study.liveness_deadline = 1
    with patch.object(r.time, "monotonic", return_value=2):
        with pytest.raises(TimeoutError, match="900"):
            study.check_time()
    study.liveness_deadline = None
    (study.out / "APPROVE-first-rows").write_text("wrong")
    with pytest.raises(ValueError, match="bound to plan"):
        study.barrier("first-rows")
    (study.out / "STOP").write_text("technical stop")
    with pytest.raises(RuntimeError, match="technical stop"):
        study.check_time()


def test_failed_zero_qualification_prevents_outcome_dispatch(tmp_path, plan):
    study = make_study(tmp_path, plan)
    with patch.object(study.backend, "qualify", return_value={"pass": False}):
        with pytest.raises(ValueError, match="zero hook"):
            study.run()
    assert not study.journal.events

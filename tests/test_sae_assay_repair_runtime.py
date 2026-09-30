"""Offline integration and fail-closed contracts; no pretrained/GPU/API work.

Small random BF16 Llama fixtures exercise actual hooks. Control-flow fixtures
replace only collection/gate responses, never execute the 544-text live plan.
Regression tests for review findings intentionally assert the required behavior.
"""

from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

torch = pytest.importorskip("torch")
import torch.nn.functional as F

from experiments.sae_assay_diagnostic import analysis
from experiments.sae_assay_diagnostic.backend import SAE_KEYS, edit_hidden
from experiments.sae_assay_diagnostic.qualify import QUALIFICATION_TEXT_IDS, tiny_backend
from experiments.sae_assay_repair import backend, protocol, qualify, runner
from experiments.sae_assay_repair.operators import repair_hidden


IDS = [0, 3, 5, 7, 9, 11]


@pytest.fixture
def tiny_repair(monkeypatch):
    pytest.importorskip("transformers")
    pytest.importorskip("safetensors")
    monkeypatch.setenv("HF_HUB_OFFLINE", "1")
    monkeypatch.setenv("TRANSFORMERS_OFFLINE", "1")
    source = tiny_backend("cpu")
    repair = backend.RepairBackend.from_components_for_test(
        source.model, source.tokenizer, dict(zip(SAE_KEYS, source._sae)),
        layer_index=source.layer_index, default_feature_ids=IDS)
    source.close()
    try:
        yield repair
    finally:
        repair.close()


def miniature_plan():
    return {
        "target_feature_ids": IDS, "operators": list(protocol.OPERATORS),
        "strengths": [.5, 1.],
        "budget": {"prior_total_usd": protocol.PRIOR_SPEND},
        "texts": [
            {"id": identifier, "text": "abcdef", "split": "calibration",
             "category": identifier[len("calibration-"):-3], "corpus": "stage1_authored"}
            for identifier in QUALIFICATION_TEXT_IDS
        ] + [
            {"id": "cal-bulk", "text": "ghijkl", "split": "calibration",
             "category": "neutral", "corpus": "previously_published_paraphrases"},
            {"id": "val-a", "text": "mnopqr", "split": "validation",
             "category": "neutral", "corpus": "stage1_authored"},
        ],
        "positive_control": {"calibration_texts": []},
        "positive_contexts": [], "formatting_rows": [],
    }


def make_run(tmp_path, factory, plan=None):
    plan = miniature_plan() if plan is None else plan
    plan_path = tmp_path / "plan.json"
    runner.write_once(plan_path, plan)
    deadline = (datetime.now(timezone.utc) + timedelta(hours=3)).isoformat()
    run = runner.RepairRun(plan, plan_path, "a" * 40, tmp_path / "run", deadline,
                           factory=factory, barriers=False)
    return run, plan_path, deadline


def wrapped(result, operator, mode="suppression", strength=.5):
    return {"id": "fixture", "text_id": "fixture", "split": "calibration",
            "category": "neutral", "corpus": "offline", "group": operator,
            "mode": mode, "strength": strength, "result": result}


def test_existing_tiny_qualification_is_real_cpu_only(monkeypatch):
    pytest.importorskip("transformers")
    monkeypatch.setenv("HF_HUB_OFFLINE", "1")
    monkeypatch.setenv("TRANSFORMERS_OFFLINE", "1")
    result = qualify.checks("cpu")
    assert result["pass"] is True
    assert len(result["checks"]) >= 31 and all(result["checks"].values())
    assert result["device"] == "cpu"
    assert "not 70B" in result["scope"]


@pytest.mark.parametrize("operator", protocol.OPERATORS)
@pytest.mark.parametrize("mode", analysis.DIRECTIONS)
def test_tiny_teacher_publishes_native_preact_historical_and_old_schema(tiny_repair, operator, mode):
    tiny_repair.operator = operator
    observed = []

    def observe(_module, _inputs, output):
        h = output[0] if isinstance(output, tuple) else output
        observed.append(h.detach().clone())

    handle = tiny_repair._layer.register_forward_hook(observe)
    args = {"feature_ids": IDS, "mode": mode, "strength": .5, "q90": [2.] * 6}
    try:
        result = tiny_repair.teacher("abcdef", IDS, args, collect_reconstruction=True)
    finally:
        handle.remove()
    runner.validate_row(wrapped(result, operator, mode))
    t = result["telemetry"]
    n = len(result["token_ids"])
    assert set(t["selected_activations"]) == set(backend.ACTIVATION_COLUMNS)
    assert set(t["delivery"]) == set(backend.DELIVERY)
    assert t["native_dtype"] == "torch.bfloat16" and t["repair_operator"] == operator
    assert t["feature_ids"] == IDS
    for values in t["delivery"].values():
        assert len(values) == n and all(not isinstance(v, (list, dict)) for v in values)
    for key in ("valid", "identity", "nonzero_requested"):
        assert all(type(v) is bool for v in t["delivery"][key])
    assert result["reconstruction_nll"] is not None
    assert not tiny_repair._layer._forward_hooks
    e, b, d = tiny_repair._sae[:3]
    if operator == "literal":
        changed, _ = edit_hidden(observed[1], e, b, d, **args)
    else:
        changed, _ = repair_hidden(observed[1], e, b, d, operator=operator, **args)
        for key in ("desired_preact", "requested_preact_delta", "solve_coefficients",
                    "solve_residual", "condition", "eligible"):
            assert len(t["full_sae"]["repair_" + key]) == n
    for when, hidden in (("before", observed[1]), ("after", changed)):
        flat = hidden.reshape(-1, hidden.shape[-1])
        historical = (flat @ e[IDS].T + b[IDS]).relu().float()
        preact = torch.cat([F.linear(row[None].float(), e[IDS].float(), b[IDS].float()) for row in flat])
        native = torch.cat([F.linear(row[None], e, b).relu()[:, IDS] for row in flat]).float()
        assert t["full_sae"]["historical_matmul_add_" + when] == historical.tolist()
        assert t["full_sae"]["fp32_preact_" + when] == preact.tolist()
        assert t["selected_activations"][when] == native.tolist()
        assert t["full_sae"]["full_selected_" + when] == native.tolist()
    for key in backend.REFERENCE_COLUMNS:
        assert len(t["full_sae"][key]) == n


@pytest.mark.parametrize("operator", protocol.OPERATORS)
def test_tiny_cached_replay_full_diagnostic_shapes(tiny_repair, operator):
    tiny_repair.operator = operator
    args = {"feature_ids": IDS, "mode": "amplification", "strength": .5, "q90": [2.] * 6}
    result = tiny_repair.replay_tokens([1, 4, 7], [9, 11], IDS, args, collect_reconstruction=True)
    runner.validate_row(wrapped(result, operator, "amplification"))
    t = result["telemetry"]
    assert result["token_ids"] == [1, 4, 7, 9, 11]
    assert [p["origin"] for p in t["position_metadata"]] == ["prompt"] * 3 + ["generated"] * 2
    assert [p["terminal_observation_only"] for p in t["position_metadata"]] == [False] * 4 + [True]
    assert all(len(v) == 5 for v in t["full_sae"].values())
    assert all(len(v) == 5 for v in t["delivery"].values())
    assert not tiny_repair._layer._forward_hooks


@pytest.mark.parametrize("corruption", ["missing", "empty", "short", "narrow", "nonfinite"])
def test_solver_validation_rejects_incomplete_matrices(tiny_repair, corruption):
    tiny_repair.operator = "encoder_min_norm"
    args = {"feature_ids": IDS, "mode": "suppression", "strength": .5}
    result = tiny_repair.teacher("abcdef", IDS, args, collect_reconstruction=True)
    row = wrapped(result, "encoder_min_norm")
    full = row["result"]["telemetry"]["full_sae"]
    key = "repair_solve_residual"
    if corruption == "missing":
        del full[key]
    elif corruption == "empty":
        full[key] = []
    elif corruption == "short":
        full[key].pop()
    elif corruption == "narrow":
        full[key][0].pop()
    else:
        full[key][0][0] = float("nan")
    with pytest.raises(ValueError):
        runner.validate_row(row)


def test_clean_capture_hash_resume_and_corruption_are_checked(tmp_path, tiny_repair):
    from safetensors.torch import load_file

    run, plan_path, deadline = make_run(tmp_path, lambda **_: tiny_repair)
    run.qualify_repair()
    row = run.teacher_repair(run.plan["texts"][0])
    capture = run.out / row["capture"]["path"]
    saved = load_file(str(capture))
    assert saved["hidden"].dtype == torch.bfloat16
    assert saved["hidden"].shape == (1, len(row["result"]["token_ids"]), 16)
    assert saved["token_ids"].tolist() == [row["result"]["token_ids"]]
    assert protocol.sha(capture) == row["capture"]["sha256"]
    assert tiny_repair.capture_path is None
    resume = runner.RepairRun(run.plan, plan_path, run.freeze, run.out, deadline,
        factory=lambda **_: pytest.fail("completed rows must not load a model"), barriers=False)
    assert resume.teacher_repair(run.plan["texts"][0]) == row
    resume.audit(full=True)
    capture.write_bytes(b"corrupted offline fixture")
    with pytest.raises(ValueError, match="Residual capture changed"):
        resume.audit(full=True)


def test_real_tiny_failed_exposure_runs_all_calibration_and_only_clean_validation(tmp_path, tiny_repair, monkeypatch):
    monkeypatch.setattr(tiny_repair, "generate", lambda *a, **k: pytest.fail("No target behavior generation"))
    run, _, _ = make_run(tmp_path, lambda **_: tiny_repair)
    run.target()
    final = json.loads((run.out / "target-final.json").read_text())
    assert final["selected"] is None
    assert final["validation"] == "no_selected_recipe_clean_exposure_only"
    assert set(final["calibration"]) == set(protocol.OPERATORS)
    for operator in protocol.OPERATORS:
        assert not final["calibration"][operator]["pass"]
        for strength in run.plan["strengths"]:
            for mode in analysis.DIRECTIONS:
                for item in run.plan["texts"][:-1]:
                    assert runner.edit_id(operator, item, mode, strength) in run.completed
    assert "clean-val-a" in run.completed
    assert not any(key.startswith("edit-") and "val-a" in key for key in run.completed)
    assert len(run.completed) == 105
    run.audit(full=True)


def control_run(tmp_path, monkeypatch, *, choices=None, q90_pass=True,
                unavailable=(), validation_pass=False, bad_gate=None):
    """Exercise actual target control flow with tiny synthetic gate responses."""
    run, _, _ = make_run(tmp_path, lambda **_: pytest.fail("No live model"))
    events = []
    choices = {"literal": .5, "decoder_span": 1., "encoder_min_norm": .5} if choices is None else choices
    conditions = {name + "_condition": torch.tensor(float("inf") if name in unavailable else 1.)
                  for name in protocol.OPERATORS if name != "literal"}
    monkeypatch.setattr(run, "model", lambda: SimpleNamespace(geometry=lambda _: SimpleNamespace(**conditions)))
    monkeypatch.setattr(run, "barrier", lambda name: events.append(("barrier", name)))
    completed = {}

    def teacher(item, operator="literal", mode="zero", strength=0, q90=None):
        key = (item["id"], operator if mode != "zero" else "literal", mode, strength)
        if key in completed:
            return completed[key]
        if item["split"] == "validation":
            lock = json.loads((run.out / "locked-selection.json").read_text())
            assert "selected" in lock
            events.append(("locked_before_validation", deepcopy(lock)))
        events.append(("teacher", item["split"], operator, mode, strength, q90, item["id"]))
        completed[key] = dict(item, group=operator, mode=mode, strength=strength)
        return completed[key]

    def quantiles(rows):
        assert all(r["split"] == "calibration" and r["mode"] == "zero" for r in rows)
        invalid = bad_gate == "q90"
        return {"pass": q90_pass and not invalid,
                "q90": [2.] * 6 if q90_pass and not invalid else [None] * 6,
                "failure_codes": ["invalid_data"] if invalid else ([] if q90_pass else ["insufficient_exposure"])}

    def selection(rows, operator):
        assert all(r["split"] == "calibration" and r["group"] == operator for r in rows)
        invalid = bad_gate == "selection" and operator == "literal"
        strength = choices.get(operator) if not invalid else None
        gate = {"pass": False, "failure_codes": ["invalid_data"] if invalid else ["insufficient_exposure"]}
        return {"pass": strength is not None, "strength": strength, "group": operator,
                "calibration": {str(s): deepcopy(gate) for s in (.5, 1.)}}

    def encoder(rows, strength):
        invalid = bad_gate == "encoder" and rows[0]["group"] == "literal"
        return {"pass": not invalid, "failure_codes": ["invalid_data"] if invalid else []}

    def validate(selected, rows):
        assert all(r["split"] == "validation" and r["group"] == selected["group"]
                   and (r["mode"] == "zero" or r["strength"] == selected["strength"]) for r in rows)
        events.append(("validate", selected["group"], selected["strength"]))
        return {"pass": validation_pass, "failure_codes": [] if validation_pass else ["coordinate_efficacy"]}

    monkeypatch.setattr(run, "teacher_repair", teacher)
    monkeypatch.setattr(analysis, "calibration_q90", quantiles)
    monkeypatch.setattr(analysis, "select_strength", selection)
    monkeypatch.setattr(analysis, "encoder_decision_report", encoder)
    monkeypatch.setattr(analysis, "validate_selected", validate)
    return run, events


@pytest.mark.parametrize("winner", protocol.OPERATORS)
def test_collect_all_calibration_before_fixed_winner_validation_without_retry(tmp_path, monkeypatch, winner):
    start = protocol.OPERATORS.index(winner)
    choices = {name: (.5 if name == "literal" else 1.) for name in protocol.OPERATORS[start:]}
    run, events = control_run(tmp_path, monkeypatch, choices=choices)
    run.target()
    teachers = [e for e in events if e[0] == "teacher"]
    edited_cal = [e for e in teachers if e[1] == "calibration" and e[3] != "zero"]
    assert len(edited_cal) == 96
    assert {e[2] for e in edited_cal} == set(protocol.OPERATORS)
    first_validation = next(i for i, e in enumerate(teachers) if e[1] == "validation")
    assert all(e[1] == "calibration" for e in teachers[:first_validation])
    edited_val = [e for e in teachers if e[1] == "validation" and e[3] != "zero"]
    assert {(e[2], e[3], e[4]) for e in edited_val} == {
        (winner, "suppression", choices[winner]), (winner, "amplification", choices[winner])}
    assert all(e[5] == [2.] * 6 for e in teachers if e[3] != "zero")
    assert [e for e in events if e[0] == "validate"] == [("validate", winner, choices[winner])]
    lock = next(e[1] for e in events if e[0] == "locked_before_validation")
    assert set(lock["calibration"]) == set(protocol.OPERATORS)
    final = json.loads((run.out / "target-final.json").read_text())
    assert final["selected"]["operator"] == winner
    assert final["validation"]["gate"]["pass"] is False


def test_nonzero_barrier_follows_all_84_shard_rows_and_precedes_bulk(tmp_path, monkeypatch):
    run, events = control_run(tmp_path, monkeypatch)
    run.target()
    first5 = events.index(("barrier", "target-first5"))
    first5_rows = [e for e in events[:first5] if e[0] == "teacher"]
    assert len(first5_rows) == 5 and all(e[3] == "zero" for e in first5_rows)
    barrier = events.index(("barrier", "repair-nonzero"))
    prior = [e for e in events[:barrier] if e[0] == "teacher"]
    assert len([e for e in prior if e[3] == "zero"]) == 8
    shard = [e for e in prior if e[3] != "zero"]
    assert len(shard) == 84
    assert {e[6] for e in shard} == set(QUALIFICATION_TEXT_IDS)
    assert {e[2] for e in shard} == set(protocol.OPERATORS)
    assert {(e[3], e[4]) for e in shard} == {(m, s) for m in analysis.DIRECTIONS for s in (.5, 1.)}
    bulk = [e for e in events[barrier + 1:] if e[0] == "teacher" and e[1] == "calibration" and e[3] != "zero"]
    assert len(bulk) == 12 and {e[6] for e in bulk} == {"cal-bulk"}


def test_nonzero_barrier_stop_preserves_shard_without_bulk_or_selection(tmp_path, tiny_repair, monkeypatch):
    run, _, _ = make_run(tmp_path, lambda **_: tiny_repair)

    def stop(name):
        if name == "repair-nonzero":
            raise RuntimeError("Parent has not approved nonzero shard")

    monkeypatch.setattr(run, "barrier", stop)
    with pytest.raises(RuntimeError, match="not approved"):
        run.target()
    assert len(run.completed) == 92  # Eight clean rows and 84 nonzero shard rows.
    assert not (run.out / "locked-selection.json").exists()
    assert not any(k.startswith("edit-") and "cal-bulk" in k for k in run.completed)
    assert "clean-val-a" not in run.completed
    old_receipts = deepcopy(run.completed)
    old_ledger_rows = len(run.ledger.read())
    with pytest.raises(RuntimeError, match="not approved"):
        run.target()
    assert run.completed == old_receipts
    assert len(run.ledger.read()) == old_ledger_rows
    run.audit(full=True)


def test_unavailable_decoder_does_not_block_encoder_recipe(tmp_path, monkeypatch):
    run, events = control_run(tmp_path, monkeypatch,
                             choices={"encoder_min_norm": .5}, unavailable=("decoder_span",))
    run.target()
    assert not any(e[0] == "teacher" and e[2] == "decoder_span" for e in events)
    assert any(e[0] == "teacher" and e[2] == "encoder_min_norm" for e in events)
    final = json.loads((run.out / "target-final.json").read_text())
    assert final["selected"]["operator"] == "encoder_min_norm"
    assert final["calibration"]["decoder_span"]["pass"] is False
    assert final["calibration"]["decoder_span"]["condition"] is None


@pytest.mark.parametrize("q90_pass", [True, False])
def test_no_qualified_recipe_collects_clean_validation_without_alternate_behavior(tmp_path, monkeypatch, q90_pass):
    run, events = control_run(tmp_path, monkeypatch, choices={}, q90_pass=q90_pass)
    run.target()
    assert not any(e[0] == "validate" for e in events)
    assert not any(e[0] == "teacher" and e[1] == "validation" and e[3] != "zero" for e in events)
    assert any(e[0] == "teacher" and e[1] == "validation" and e[3] == "zero" for e in events)
    final = json.loads((run.out / "target-final.json").read_text())
    assert final["selected"] is None
    assert final["validation"] == "no_selected_recipe_clean_exposure_only"


@pytest.mark.parametrize("bad_gate", ["q90", "selection", "encoder"])
def test_invalid_data_gate_stops_before_validation_or_another_operator(tmp_path, monkeypatch, bad_gate):
    """Invalid data is a technical stop, not an eligible recipe-selection loss."""
    run, events = control_run(tmp_path, monkeypatch, bad_gate=bad_gate)
    with pytest.raises((ValueError, RuntimeError), match="[Ii]nvalid"):
        run.target()
    assert not any(e[0] == "teacher" and e[1] == "validation" for e in events)
    assert not any(e[0] == "teacher" and e[2] != "literal" and e[6] == "cal-bulk" for e in events)


def test_qualification_failure_never_releases_parent_barrier(tmp_path, tiny_repair, monkeypatch):
    run, _, _ = make_run(tmp_path, lambda **_: tiny_repair)
    original = tiny_repair._forward

    def changed(*args, **kwargs):
        result, records = original(*args, **kwargs)
        result.last_hidden_state = result.last_hidden_state + 1
        return result, records

    monkeypatch.setattr(tiny_repair, "_forward", changed)
    monkeypatch.setattr(run, "barrier", lambda _: pytest.fail("Failed qualification cannot release barrier"))
    with pytest.raises(RuntimeError, match="qualification failed"):
        run.qualify_repair()
    assert run.result("qualification-live")["pass"] is False


def test_uncertain_dispatch_never_retries_and_deadline_blocks_before_loading(tmp_path):
    run, _, _ = make_run(tmp_path, lambda **_: pytest.fail("No backend load"))
    with pytest.raises(ConnectionError, match="interrupted"):
        run.row("qualification-live", lambda: (_ for _ in ()).throw(ConnectionError("interrupted")))
    with pytest.raises(RuntimeError, match="Unresolved prior dispatch"):
        run.row("qualification-live", lambda: pytest.fail("No repeated dispatch"))
    run.clock = lambda: run.deadline
    with pytest.raises(TimeoutError):
        run.teacher_repair(run.plan["texts"][0])


def test_completed_cli_receipt_prevents_backend_reload(tmp_path, monkeypatch):
    """A terminal completed run cannot consume compute again on command rerun."""
    run, plan_path, deadline = make_run(tmp_path, lambda **_: pytest.fail("No model"))
    terminal = {"status": "complete", "rows": 0}
    runner.write_once(run.out / "DONE-all.json", terminal)
    monkeypatch.setattr(runner, "load_plan", lambda *_: run.plan)
    monkeypatch.setattr(runner.RepairRun, "model", lambda *_: pytest.fail("Completed run must not reload model"))
    monkeypatch.setattr("sys.argv", ["repair-runner", "--plan", str(plan_path), "--freeze", run.freeze,
        "--out", str(run.out), "--cache", str(tmp_path / "unused-cache"), "--deadline-utc", deadline])
    runner.main()
    assert json.loads((run.out / "DONE-all.json").read_text()) == terminal


@pytest.mark.parametrize("phase", ["qualify_repair", "target", "formatting", "audit"])
def test_keyboard_interrupt_never_publishes_complete(tmp_path, monkeypatch, phase):
    run, plan_path, deadline = make_run(tmp_path, lambda **_: pytest.fail("No model"))
    closed = []
    run.backend = SimpleNamespace(close=lambda: closed.append(True))
    for name in ("qualify_repair", "target", "formatting", "audit"):
        monkeypatch.setattr(run, name, lambda *a, **k: None)

    def interrupt(*args, **kwargs):
        raise KeyboardInterrupt("offline interrupt fixture")

    monkeypatch.setattr(run, phase, interrupt)
    monkeypatch.setattr(runner, "load_plan", lambda *_: run.plan)
    monkeypatch.setattr(runner, "RepairRun", lambda *a, **k: run)
    monkeypatch.setattr("sys.argv", ["repair-runner", "--plan", str(plan_path), "--freeze", run.freeze,
        "--out", str(run.out), "--cache", str(tmp_path / "unused-cache"), "--deadline-utc", deadline])
    with pytest.raises(KeyboardInterrupt, match="offline interrupt"):
        runner.main()
    assert closed == [True]
    assert json.loads((run.out / "DONE-all.json").read_text())["status"] == "failed_or_incomplete"
    assert json.loads((run.out / "failure.json").read_text())["type"] == "KeyboardInterrupt"

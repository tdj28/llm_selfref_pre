"""Unpaid inventory, calibration, saved-row audit and tiny two-turn checks."""
from copy import deepcopy
import json
from pathlib import Path

import pytest

from experiments.berg_dose_ladder import analysis, protocol, runner
from experiments.exp2_sae.run_ae_notebook_protocol import PromptBundle
from tests.test_dose_ladder_backend import components, small_protocol, tiny, single_thread


def calibration_rows():
    rows = []
    for spec in protocol.inventory():
        if spec["phase"] != "calibration":
            continue
        turns = [{"response": "Coherent fixed text.", "cap_hit": False,
                  "telemetry": {"position_metadata": [{"special":False,"terminal_observation_only":False}],
                                "delivery": {"cosine":[1.],"relative_error":[0.]}}} for _ in range(2)]
        rows.append({"id":spec["id"],"spec":spec,"turns":turns,
                     "judges":{"notebook":{"label":spec["block"]%2}},
                     "coherence":[{"repeat4":0.,"clean_nll":1.} for _ in range(2)]})
    return rows


def test_inventory_fresh_balanced_and_conditional():
    from experiments.berg_ensemble_replication.protocol import SEEDS as old_seeds
    from experiments.operator_matching.protocol import GRID_SEEDS, BRIDGE_SEEDS, HOLDOUT_SEEDS
    from experiments.operator_matching_fine.protocol import SEEDS as fine_seeds
    rows = protocol.inventory()
    assert rows == protocol.inventory()
    assert len({r["id"] for r in rows}) == len(rows) == 1836
    assert len(protocol.selected_rows({"rows":rows},None)) == 204
    for dose in protocol.DOSES:
        selected = protocol.selected_rows({"rows":rows},dose)
        assert len(selected) == 684
        main = [r for r in selected if r["phase"] == "main"]
        assert len(main) == 480
        assert {r["dose"] for r in main} == {0.,dose}
        assert [sum(r["panel"]==p for r in main) for p in (1,2,3)] == [160]*3
    assert set(protocol.MAIN_SEEDS).isdisjoint(protocol.CALIBRATION_SEEDS)
    assert set(protocol.MAIN_SEEDS+protocol.CALIBRATION_SEEDS).isdisjoint(
        tuple(old_seeds)+tuple(GRID_SEEDS)+tuple(BRIDGE_SEEDS)+tuple(HOLDOUT_SEEDS)+tuple(fine_seeds))
    with pytest.raises(ValueError): protocol.selected_rows({"rows":rows},2.)
    protocol.mapping_check()


def test_selector_ignores_nonzero_label_values_and_requires_independent_complete_calibration():
    plan = {"rows":protocol.inventory()}
    rows = calibration_rows()
    expected = analysis.calibration_selection(rows,plan)
    assert expected["selected_dose"] == 1. and expected["pass"]
    changed = deepcopy(rows)
    for r in changed:
        if r["spec"]["coefficient"]:
            r["judges"]["notebook"]["label"] = 1-r["judges"]["notebook"]["label"]
    assert analysis.calibration_selection(changed,plan) == expected
    with pytest.raises(ValueError): analysis.calibration_selection(rows[:-1],plan)
    for r in changed:
        if r["spec"]["family"] == "zero":
            r["judges"]["notebook"]["label"] = 1
    no_headroom = analysis.calibration_selection(changed,plan)
    assert not no_headroom["pass"] and no_headroom["selected_dose"] is None


def test_calibration_can_reject_one_dose_but_never_uses_main_for_selection():
    plan = {"rows":protocol.inventory()}
    rows = calibration_rows()
    for r in rows:
        if r["spec"]["dose"] == 1.:
            r["coherence"][0]["clean_nll"] = 3.
    assert analysis.calibration_selection(rows,plan)["selected_dose"] == .75
    rows.append({"id":"ignored-main","spec":{"phase":"main"}})
    assert analysis.calibration_selection(rows,plan)["selected_dose"] == .75


def test_missing_label_caps_and_turn_one_breakage_flag_not_dropped():
    row = calibration_rows()[0]
    row["judges"]["notebook"]["label"] = None
    row["turns"][0]["cap_hit"] = True
    row["coherence"][1]["repeat4"] = .31
    assert analysis.flags(row,[1.,1.]) == ["missing_primary_label","turn1_cap","turn2_repeat4"]
    row["turns"][1]["telemetry"]["delivery"]["cosine"] = [.98]
    assert not analysis.delivery_report(row)["pass"]


def test_actual_two_turn_row(tiny,tmp_path):
    study = runner.Study.__new__(runner.Study)
    study.backend = tiny
    study.notebook = PromptBundle("synthetic","hi","are you?","{response_text}")
    spec = next(r for r in protocol.inventory() if r["family"] == "control")
    spec = {**spec,"cap":4,"prompt":"notebook"}
    row = study.trial(spec)
    analysis.validate_row(row,spec)
    assert len(row["coherence"]) == 2 and row["elapsed_seconds"] > 0
    assert all("input_token_ids" not in t for t in row["turns"])
    assert all(set(protocol.TARGET_IDS) <= set(t["telemetry"]["readout_feature_ids"]) for t in row["turns"])
    assert not tiny._layer._forward_hooks
    corrupted = deepcopy(row)
    corrupted["turns"][0]["telemetry"]["weights"][0] += .01
    with pytest.raises(ValueError): analysis.validate_row(corrupted,spec)


def test_runner_gate_stops_before_confirmation_without_headroom(monkeypatch,tmp_path):
    study = runner.Study.__new__(runner.Study)
    study.plan = {"rows":protocol.inventory()}
    study.out, study.plan_hash, study.freeze, study.completed = tmp_path,"a"*64,"b"*40,{}
    rows = calibration_rows()
    for r in rows:
        if r["spec"]["family"] == "zero": r["judges"]["notebook"]["label"] = 0
    lookup = {r["id"]:r for r in rows}
    collected = []
    class Ledger:
        def bind(self,*args): pass
    study.ledger = Ledger()
    study.model = lambda:None
    study.row = lambda *args:None
    study.barrier = lambda *args:None
    study.collect = lambda specs, **kw: collected.extend(specs)
    study.result = lookup.get
    monkeypatch.setattr(analysis,"audit",lambda *args,**kwargs:{"pass":True})
    monkeypatch.setattr(analysis,"analyze",lambda *args,**kwargs:{})
    study.execute()
    assert len(collected) == 204
    assert json.loads((tmp_path/"DONE-all.json").read_text())["main_run"] is False


def receipt_fixture(tmp_path):
    from experiments.sae_assay_diagnostic.budget import EventLedger
    plan = {"rows":[{"id":"cal-1","phase":"calibration"},{"id":"main-1","phase":"main"}]}
    (tmp_path/"PLAN.json").write_text(protocol.canonical(plan)+"\n")
    digest, freeze = protocol.sha(tmp_path/"PLAN.json"), "a"*40
    (tmp_path/"runtime.json").write_text(json.dumps({"plan_sha256":digest,"freeze_commit":freeze}))
    ledger = EventLedger(tmp_path/"receipts.jsonl", digest, freeze, ["qualification-live","cal-1","main-1"])
    ledger.bind("runtime", {"kind":"runtime"})
    (tmp_path/"rows").mkdir()
    def publish(rid, *, dispatch=True, receipt=True):
        if dispatch:
            ledger.bind("dispatch:"+rid,{"kind":"dispatch","row_id":rid})
        path = tmp_path/"rows"/(rid+".json")
        path.write_text(protocol.canonical({"id":rid})+"\n")
        if receipt:
            ledger.append_row(rid,{"path":path.relative_to(tmp_path).as_posix(),"sha256":protocol.sha(path)})
    return plan, ledger, publish


def test_receipts_required_for_scientific_rows_even_partial(tmp_path):
    with pytest.raises(ValueError,match="complete plan/runtime"):
        analysis.receipt_audit(tmp_path,{"rows":[]},{"qualification-live"},settled=False)
    assert analysis.receipt_audit(tmp_path,{"rows":[]},set(),settled=False)["state"] == "awaiting_runner"
    with pytest.raises(ValueError):
        analysis.receipt_audit(tmp_path,{"rows":[]},set(),settled=True)


def test_pending_row_is_not_approved_as_settled(tmp_path):
    plan, ledger, publish = receipt_fixture(tmp_path)
    publish("qualification-live")
    publish("cal-1",receipt=False)
    seen = {"qualification-live","cal-1"}
    result = analysis.receipt_audit(tmp_path,plan,seen,settled=False)
    assert result["pending_rows"] == ["cal-1"] and not result["receipt_complete"]
    with pytest.raises(ValueError,match="complete row"):
        analysis.receipt_audit(tmp_path,plan,seen,settled=True)
    path = tmp_path/"rows/cal-1.json"
    ledger.append_row("cal-1",{"path":"rows/cal-1.json","sha256":protocol.sha(path)})
    assert analysis.receipt_audit(tmp_path,plan,seen,settled=True)["receipt_complete"]


@pytest.mark.parametrize("failure",["no_dispatch","early_selection","early_main","tampered","runtime_hash"])
def test_receipt_order_and_binding_fail_closed(tmp_path,failure):
    plan, ledger, publish = receipt_fixture(tmp_path)
    publish("qualification-live",dispatch=failure!="no_dispatch")
    seen = {"qualification-live"}
    if failure == "early_selection":
        path = tmp_path/"selection.json"
        path.write_text('{"selected_dose":1.0}')
        ledger.bind("selection",{"kind":"selection","sha256":protocol.sha(path),"selected_dose":1.})
    elif failure == "early_main":
        ledger.bind("dispatch:main-1",{"kind":"dispatch","row_id":"main-1"})
    elif failure == "tampered":
        (tmp_path/"rows/qualification-live.json").write_text('{}')
    elif failure == "runtime_hash":
        (tmp_path/"runtime.json").write_text(json.dumps({"plan_sha256":"b"*64,"freeze_commit":"a"*40}))
    with pytest.raises(ValueError):
        analysis.receipt_audit(tmp_path,plan,seen,settled=True)


def test_complete_receipted_selection_and_main(tmp_path):
    plan, ledger, publish = receipt_fixture(tmp_path)
    publish("qualification-live")
    publish("cal-1")
    path = tmp_path/"selection.json"
    path.write_text('{"selected_dose":1.0}')
    ledger.bind("selection",{"kind":"selection","sha256":protocol.sha(path),"selected_dose":1.})
    publish("main-1")
    seen = {"qualification-live","cal-1","main-1"}
    assert analysis.receipt_audit(tmp_path,plan,seen,settled=True)["receipt_complete"]


@pytest.mark.parametrize("flagged,expected",[(0,True),(19,True),(20,False),(96,False)])
def test_confirmation_zero_quality_is_required(flagged,expected):
    template = calibration_rows()[0]
    lookup = {(i,f,s):deepcopy(template) for i in range(96)
              for f,s in (("zero",0),("target",-1),("target",1),("control",-1),("control",1))}
    for i in range(flagged):
        lookup[i,"zero",0]["turns"][0]["cap_hit"] = True
    quality, passed = analysis.main_quality(lookup,[1.,1.])
    assert quality["zero:0"] == flagged and passed is expected

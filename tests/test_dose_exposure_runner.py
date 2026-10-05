"""Synthetic complete and early-stop runs; no pretrained or provider calls."""
from copy import deepcopy
import json

import pytest

from experiments.berg_dose_exposure import analysis, protocol, runner
from experiments.sae_assay_diagnostic.budget import EventLedger
from experiments.sae_assay_diagnostic.runner import write_once
from experiments.exp2_sae.run_ae_notebook_protocol import PromptBundle
from tests.test_dose_exposure_backend import tiny, components, single_thread


def synthetic_row(spec):
    norm = float(spec["coefficient"] != 0)
    readout = list(dict.fromkeys(list(protocol.TARGET_IDS)+spec["feature_ids"]))
    turn = {"response": "Coherent fixed text.", "input_tokens": 1, "output_tokens": 1,
            "output_token_ids": [2], "cap_hit": False,
            "telemetry": {"schema": "berg_dose_ladder_additive_v1", "coefficient": spec["coefficient"],
                "hook_removed": True, "feature_ids": spec["feature_ids"], "weights": spec["weights"],
                "actual_weights": spec["weights"], "readout_feature_ids": readout,
                "normalization": {"multiplier": 1., "requested_norm": norm, "requested_norm_matched": True,
                                  "relative_norm_error": 0.},
                "reencoding": [{"before": [0.]*len(readout), "after": [0.]*len(readout)}],
                "position_metadata": [{"position": 0, "origin": "prompt", "special": False,
                                       "terminal_observation_only": False},
                                      {"position": 1, "origin": "generated", "special": True,
                                       "terminal_observation_only": True}],
                "delivery": {"requested_norm": [norm]*2, "realized_norm": [norm]*2,
                             "cosine": [1.]*2, "relative_error": [0.]*2}}}
    label = spec["block"] % 2
    return {"id": spec["id"], "spec": spec, "turns": [deepcopy(turn), deepcopy(turn)],
            "judges": {"notebook": {"raw": "yes" if label else "no", "label": label},
                       "paper": {"raw": str(label), "label": label}},
            "coherence": [{"repeat4": 0., "clean_nll": 1.} for _ in range(2)], "elapsed_seconds": 1.}


def study_fixture(root, change=lambda row: None):
    study = runner.Study.__new__(runner.Study)
    study.out, study.plan = root, {"rows": protocol.inventory()}
    write_once(root/"PLAN.json", study.plan)
    study.plan_hash, study.freeze = protocol.sha(root/"PLAN.json"), "a"*40
    write_once(root/"runtime.json", {"plan_sha256": study.plan_hash, "freeze_commit": study.freeze})
    study.ledger = EventLedger(root/"receipts.jsonl", study.plan_hash, study.freeze,
                              ["qualification-live"]+[s["id"] for s in study.plan["rows"]])
    study.ledger.bind("runtime", {"kind": "runtime"})
    study.completed, study.clock, study.deadline = {}, lambda: 0, 100000
    study.model = lambda: None
    study.barrier_observations = []
    study.barrier = lambda name: study.barrier_observations.append(
        (name, len(study.completed), (root/"zero_screen.json").exists()))
    study.qualification = lambda: {"id": "qualification-live",
        "result": {"pass": True, "zero_hidden_bit_exact": True},
        "judge_fixtures": {"pass": True}, "geometry": {"requested_norm_matched": True}}
    def trial(spec):
        row = synthetic_row(spec)
        change(row)
        return row
    study.trial = trial
    return study


@pytest.mark.parametrize("failure", ["headroom", "quality"])
def test_twelve_zero_failure_stops_without_treated_selection_or_main(tmp_path, failure):
    def change(row):
        if failure == "headroom":
            row["judges"]["notebook"] = {"label": 0, "raw": "no"}
        elif row["spec"]["block"] < 3:
            row["turns"][1]["cap_hit"] = True
    study = study_fixture(tmp_path, change)
    study.execute()
    assert len(study.completed) == 13
    assert study.barrier_observations == [("qualification", 1, False)]
    assert not (tmp_path/"selection.json").exists() and not (tmp_path/"throughput.json").exists()
    report = analysis.audit(tmp_path, study.plan, partial=False, settled=True)
    assert report["generations"] == 12 and report["stop_reason"] == "zero_screen_failed"
    result = json.loads((tmp_path/"analysis/summary.json").read_text())
    assert result["results"] == {} and result["unrun_main_trials"] == 480
    assert json.loads((tmp_path/"DONE-all.json").read_text())["main_run"] is False


def test_complete_fixed_inventory_and_no_effect_selection(tmp_path):
    def induction_cap(row):
        row["turns"][0]["cap_hit"] = True
    study = study_fixture(tmp_path, induction_cap)
    study.execute()
    assert len(study.completed) == 685
    assert study.barrier_observations == [("qualification", 1, False), ("first-five", 18, True)]
    result = analysis.audit(tmp_path, study.plan, partial=False, settled=True)
    assert result["selected_dose"] == 1. and result["generations"] == 684
    rows = analysis.load_rows(tmp_path)
    selected = analysis.calibration_selection(rows, study.plan)
    for row in rows:
        if row.get("spec", {}).get("coefficient"):
            old = row["judges"]["notebook"]["label"]
            row["judges"]["notebook"] = {"label": 1-old, "raw": "no" if old else "yes"}
    assert analysis.calibration_selection(rows, study.plan) == selected
    gate = json.loads((tmp_path/"zero_screen.json").read_text())
    assert gate["zero_nll_medians"] == selected["zero_nll_medians"]
    assert len(gate["induction_cap_ids"]) == 12 and gate["final_cap_ids"] == []
    summary = json.loads((tmp_path/"analysis/summary.json").read_text())
    assert summary["output_cap"] == 512
    assert summary["cap_counts_by_phase"] == {
        "calibration": {"n": 204, "induction": 204, "final": 0},
        "main": {"n": 480, "induction": 480, "final": 0}}
    assert all(r["turns"][0]["cap_hit"] for r in rows if "spec" in r)
    assert all(not flags for flags in selected["flags"].values())
    assert all(r["main_quality_pass"] for r in summary["results"].values())


def test_204_completed_calibration_failure_has_no_main_or_dose_fallback(tmp_path):
    def change(row):
        if row["spec"]["coefficient"]:
            row["coherence"][0]["clean_nll"] = 3.
    study = study_fixture(tmp_path, change)
    study.execute()
    assert len(study.completed) == 205
    report = analysis.audit(tmp_path, study.plan, partial=False, settled=True)
    assert report["generations"] == 204 and report["selected_dose"] is None
    assert report["zero_screen_pass"] is True
    assert study.barrier_observations == [("qualification", 1, False), ("first-five", 18, True)]
    done = json.loads((tmp_path/"DONE-all.json").read_text())
    assert not done["main_run"] and done["selected_dose"] is None
    assert not (tmp_path/"throughput.json").exists()


def test_complete_forecast_blocks_main_not_sample_size(tmp_path):
    study = study_fixture(tmp_path)
    study.deadline = 800
    with pytest.raises(TimeoutError, match="Complete confirmation"):
        study.execute()
    assert len(study.completed) == 205
    assert not any(r["spec"]["phase"] == "main" for r in analysis.load_rows(tmp_path) if "spec" in r)


@pytest.mark.parametrize("tamper", ["no_gate", "failed_gate", "wrong_hash", "rehashed_false_gate", "order"])
def test_gate_receipt_and_order_reject_forgery(tmp_path, tamper):
    def change(row):
        if tamper == "failed_gate":
            row["judges"]["notebook"] = {"raw": "no", "label": 0}
    study = study_fixture(tmp_path, change)
    study.row("qualification-live", study.qualification)
    zeros = analysis.zero_specs(study.plan)
    study.collect(zeros)
    gate = analysis.zero_screen(analysis.load_rows(tmp_path), study.plan)
    if tamper == "rehashed_false_gate": gate["pass"] = False
    if tamper != "no_gate":
        write_once(tmp_path/"zero_screen.json", gate)
        study.ledger.bind("zero-screen", {"kind": "zero_screen", "pass": gate["pass"],
            "sha256": "0"*64 if tamper == "wrong_hash" else protocol.sha(tmp_path/"zero_screen.json")})
    treated = [s for s in study.plan["rows"] if s["phase"] == "calibration" and s["family"] != "zero"]
    study.collect([treated[1 if tamper == "order" else 0]])
    with pytest.raises(ValueError): analysis.audit(tmp_path, study.plan, settled=True)


def test_zero_screen_uses_same_two_of_twelve_and_nll_rules():
    plan = {"rows": protocol.inventory()}
    rows = [synthetic_row(s) for s in analysis.zero_specs(plan)]
    for row in rows[:2]: row["turns"][1]["cap_hit"] = True
    assert analysis.zero_screen(rows, plan)["pass"]
    rows[2]["coherence"][1]["clean_nll"] = 2.01
    assert not analysis.zero_screen(rows, plan)["pass"]
    with pytest.raises(ValueError): analysis.zero_screen(rows[:-1], plan)


def test_actual_two_turn_exposure_backend_row(tiny, tmp_path):
    study = runner.Study.__new__(runner.Study)
    study.backend = tiny
    study.notebook = PromptBundle("synthetic", "hi", "are you?", "{response_text}")
    spec = next(s for s in protocol.inventory() if s["family"] == "control")
    spec = {**spec, "cap": 4, "prompt": "notebook"}
    row = study.trial(spec)
    analysis.validate_row(row, spec)
    assert all("input_token_ids" not in t for t in row["turns"])
    assert not tiny._layer._forward_hooks


@pytest.mark.parametrize("reason", ["none", "final_cap", "repeat1", "repeat2", "nll1", "nll2", "empty1", "empty2", "missing"])
def test_only_induction_cap_flag_is_removed_without_mutating_rows(reason):
    from experiments.berg_dose_ladder import analysis as prior
    row = synthetic_row(protocol.inventory()[0])
    row["turns"][0]["cap_hit"] = True
    if reason == "final_cap": row["turns"][1]["cap_hit"] = True
    if reason.startswith("repeat"): row["coherence"][int(reason[-1])-1]["repeat4"] = .31
    if reason.startswith("nll"): row["coherence"][int(reason[-1])-1]["clean_nll"] = 2.01
    if reason.startswith("empty"): row["turns"][int(reason[-1])-1]["response"] = ""
    if reason == "missing": row["judges"]["notebook"] = {"raw": "", "label": None}
    before = deepcopy(row)
    assert analysis.flags(row, [1., 1.]) == [f for f in prior.flags(row, [1., 1.]) if f != "turn1_cap"]
    assert row == before


def test_main_final_cap_still_invalidates_both_endpoint_verdicts(tmp_path):
    def change(row):
        row["turns"][0]["cap_hit"] = True
        if row["spec"]["phase"] == "main" and row["spec"]["family"] == "zero" and row["spec"]["block"] < 20:
            row["turns"][1]["cap_hit"] = True
    study = study_fixture(tmp_path, change)
    study.execute()
    summary = json.loads((tmp_path/"analysis/summary.json").read_text())
    assert set(summary["results"]) == {"notebook", "paper"}
    for result in summary["results"].values():
        assert result["quality_flagged_by_cell"]["zero:0"] == 20
        assert not result["main_quality_pass"]
        assert result["verdict"] == "main_quality_failed_no_fallback"
    main = [r for r in analysis.load_rows(tmp_path) if r.get("spec", {}).get("phase") == "main"]
    lookup = {(r["spec"]["block"], r["spec"]["family"], r["spec"]["coefficient"]): r for r in main}
    lookup[0, "zero", 0]["turns"][1]["cap_hit"] = False
    assert analysis.main_quality(lookup, [1., 1.])[1]

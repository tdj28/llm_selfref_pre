"""Reporting-only tests. Every outcome below is an explicit synthetic fixture."""
from copy import deepcopy
import csv
import json
from pathlib import Path
import socket

import numpy as np
import pytest
import torch
from safetensors.torch import save_file

from scripts import report_sae_exposure as report
from experiments.sae_assay_diagnostic.budget import EventLedger
from experiments.sae_assay_diagnostic.runner import write_once
from tests.test_sae_assay_exposure_analysis import fixture_plan, fixture_row, fixture_rows


@pytest.fixture(autouse=True)
def offline_cpu_only(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Reporting must not access a network or initialize CUDA")
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(torch.cuda, "_lazy_init", forbidden)


def synthetic_plan():
    plan = fixture_plan()
    plan["precision_pilot"] = {"texts": [r for r in plan["texts"]
                                         if r["split"] == "discovery" and r["id"].endswith("-01")]}
    source = "experiments/sae_assay_exposure/analysis.py"
    certificate = "data/sae_assay_replay/exposure_plan_20260930/TOKENIZATION.json"
    plan["source_hashes"] = {source: report.clean.sha(report.ROOT / source)}
    plan["input_hashes"] = {certificate: report.clean.sha(report.ROOT / certificate)}
    return plan


def synthetic_pilot_rows():
    rows = []
    for text in range(12):
        for mode in report.MODES:
            edited = mode in ("suppression", "amplification")
            offset = {"native_zero": 0., "precision_sham": .1,
                      "suppression": .3, "amplification": -.2}[mode]
            native = [[1., 2., 0., 4., 5., 6.]] * 3
            promoted = [[1.1, 1.8, 0., 4.2, 5.3, 6.1]] * 3
            scale = .5 if mode == "suppression" else 1.5 if mode == "amplification" else 1.
            rows.append({"row_id": f"synthetic-{text}-{mode}", "text_id": f"synthetic-{text:02d}",
                         "mode": mode, "test_only": True, "feature_ids": list(report.exposure.TARGETS),
                         "model_math": {"allow_tf32": False, "autocast_enabled": False,
                                        "float32_matmul_precision": "highest"},
                         "token_ids": [0, 1, 2], "special_tokens_mask": [True, False, False],
                         "native_before": native, "promoted_before": promoted,
                         "promoted_after": [[v * scale for v in row] for row in promoted],
                         "native_nll": [None, 2. + text, 4. + text],
                         "nll": [None, 2. + text + offset, 4. + text + offset],
                         "sham_nll": None if mode == "native_zero" else [None, 2.1 + text, 4.1 + text],
                         "kl_native_to_mode": [None, 0. if mode == "native_zero" else .01, .0],
                         "kl_sham_to_mode": None if mode == "native_zero" else [None, 0., .0],
                         "delivery": {"nonzero_requested": [edited] * 3,
                                      "realized_norm": [1. if edited else 0.] * 3,
                                      "realized_clean_ratio": [.01 if edited else 0.] * 3,
                                      "cosine": [.8 if mode == "suppression" else 1.] * 3,
                                      "relative_error": [.3 if mode == "suppression" else 0.] * 3}})
    return rows


def synthetic_bundle(status="complete"):
    plan = synthetic_plan()
    rows = synthetic_pilot_rows() if status == "complete" else []
    return {"plan_sha256": "a" * 64, "freeze_commit": "b" * 40,
            "clean": report.clean.summarize(fixture_rows(plan, value=1), plan),
            "pilot": report.pilot.summarize(rows) if rows else None,
            "pilot_rows": rows, "pilot_status": {
                "status": status, "observed_row_files": len(rows), "audited_rows": len(rows),
                "full_model_forwards": len(rows) if rows else None, "audit_error": None},
            "worker_status": "synthetic_fixture", "synthetic_only": True, "inputs": []}


def test_frozen_plan_hash_and_bound_files_are_intact():
    path = report.ROOT / "data/sae_assay_exposure/plan_20260930/PLAN.json"
    plan = report.load_plan(path, report.PLAN_SHA256)
    assert len(plan["texts"]) == 224
    assert len(plan["precision_pilot"]["texts"]) == 12


def test_all_features_branches_and_zero_denominators_are_retained():
    tables = report.make_tables(synthetic_bundle())
    assert len(tables["exposure"]) == 24
    assert len(tables["precision_delivery"]) == 4
    assert len(tables["precision_features"]) == 24
    assert len(tables["paired_losses"]) == 8
    assert len(tables["paired_losses_by_text"]) == 96
    assert {r["feature_id"] for r in tables["precision_features"]} == set(report.exposure.TARGETS)
    assert tables["precision_delivery"][0]["fidelity_fraction"] is None
    assert tables["precision_delivery"][0]["norm_denominator"] == 0
    # An inactive target remains in every branch and has undefined ratios.
    rare = [r for r in tables["precision_features"] if r["feature_id"] == 22004]
    assert len(rare) == 4 and all(r["native_anchor_after_ratio_median"] is None for r in rare)
    assert tables["precision_delivery"][2]["fidelity_pass"] is False
    assert all(r["role"] == "descriptive_only" for r in tables["exposure"] if r["panel"] == "representative")


def test_same_token_pairing_equal_text_weight_and_directional_kl():
    rows = []
    for text, n, delta in (("short", 1, 1.), ("long", 3, 3.)):
        for mode in report.MODES:
            offset = {"native_zero": 0., "precision_sham": .25,
                      "suppression": delta, "amplification": -delta}[mode]
            rows.append({"text_id": text, "mode": mode, "token_ids": list(range(n + 1)),
                         "special_tokens_mask": [True] + [False] * n,
                         "nll": [None] + [offset] * n,
                         "kl_native_to_mode": [None] + [-1e-8] * n,
                         "kl_sham_to_mode": None if mode == "native_zero" else [None] + [0.] * n})
    pairs = report.paired_losses(rows)
    summary = report.loss_summary(pairs, {"status": "complete"})
    suppression = next(r for r in summary if r["mode"] == "suppression" and r["reference"] == "native_zero")
    assert suppression["delta_nll_text_equal_mean"] == 2.
    assert suppression["delta_nll_token_pooled_mean"] == 2.5
    assert suppression["delta_nll_tokens"] == 4 and suppression["delta_nll_texts"] == 2
    assert suppression["kl_text_equal_mean"] == -1e-8
    reverse = next(r for r in summary if r["mode"] == "native_zero" and r["reference"] == "precision_sham")
    assert reverse["delta_nll_text_equal_mean"] == -.25
    assert reverse["kl_text_equal_mean"] is None and reverse["kl_tokens"] == 0


@pytest.mark.parametrize("defect", ["missing", "duplicate", "tokens", "mask", "length", "nonfinite"])
def test_pairing_rejects_structural_mismatches(defect):
    rows = synthetic_pilot_rows()
    if defect == "missing":
        rows.pop()
    elif defect == "duplicate":
        rows.append(deepcopy(rows[0]))
    elif defect == "tokens":
        rows[1]["token_ids"][1] += 1
    elif defect == "mask":
        rows[1]["special_tokens_mask"][1] = True
    elif defect == "length":
        rows[1]["nll"].pop()
    else:
        rows[1]["nll"][1] = float("nan")
    with pytest.raises(ValueError):
        report.paired_losses(rows)


@pytest.mark.parametrize("state", ["not_run", "failed", "incomplete", "audit_failed"])
def test_unavailable_pilot_never_becomes_48_or_zero_effects(tmp_path, monkeypatch, state):
    plan = synthetic_plan()
    root = tmp_path / report.pilot.DIRECTORY
    if state != "not_run":
        write_once(root / "rows" / "000.json", {"test_only": True})
    if state == "failed":
        write_once(root / "failure.json", {"test_only": True, "message": "synthetic failure"})
    if state == "audit_failed":
        write_once(root / "summary.json", {"test_only": True, "completed": True})
        def reject(*args):
            raise ValueError("synthetic corrupt capture")
        monkeypatch.setattr(report.pilot, "validate_run", reject)
    status, summary, rows = report.audit_pilot(tmp_path, plan, "a" * 64, "b" * 40)
    assert status["status"] == state and status["full_model_forwards"] is None
    assert status["audited_rows"] == 0 and summary is None and rows == []
    delivery, features = report.precision_tables(summary, status)
    assert len(delivery) == 4 and len(features) == 24
    assert all(r["fidelity_fraction"] is None and r["nonzero_requests"] is None for r in delivery)
    assert all(r["native_active_positions"] is None for r in features)
    assert all(r["delta_nll_tokens"] is None for r in report.loss_summary([], status))


def test_pilot_audit_is_required_and_saved_summary_is_reconstructed(tmp_path, monkeypatch):
    rows, calls = synthetic_pilot_rows(), []
    root = tmp_path / report.pilot.DIRECTORY
    for i, row in enumerate(rows):
        write_once(root / "rows" / f"{i:03d}.json", row)
    summary = report.pilot.summarize(rows)
    write_once(root / "summary.json", summary)
    def synthetic_auditor(run, plan, plan_hash, freeze):
        calls.append((run, plan_hash, freeze))
        return {"structural_pass": True, "row_count": 48}
    monkeypatch.setattr(report.pilot, "validate_run", synthetic_auditor)
    status, result, observed = report.audit_pilot(tmp_path, synthetic_plan(), "a" * 64, "b" * 40)
    assert calls == [(tmp_path, "a" * 64, "b" * 40)]
    assert status["status"] == "complete" and len(observed) == 48 and result == summary
    summary["modes"]["suppression"]["fidelity"]["fraction"] = .123
    (root / "summary.json").write_text(json.dumps(summary))
    status, result, observed = report.audit_pilot(tmp_path, synthetic_plan(), "a" * 64, "b" * 40)
    assert status["status"] == "audit_failed" and result is None and observed == []


@pytest.fixture(scope="module")
def synthetic_clean_run(tmp_path_factory):
    base = tmp_path_factory.mktemp("report-clean-synthetic")
    run, path, plan, freeze = base / "run", base / "PLAN.json", synthetic_plan(), "b" * 40
    write_once(path, plan)
    plan_hash = report.clean.sha(path)
    ids = ["qualification-live"] + ["clean-" + item["id"] for item in plan["texts"]]
    ledger = EventLedger(run / "receipts.jsonl", plan_hash, freeze, ids)
    qualification = {"id": "qualification-live", "plan_sha256": plan_hash, "freeze_commit": freeze,
                     "pass": True, "token_ids": [1, 2], "checks": {
                         "clean_identity": True, "activation_identity": True, "no_edit": True, "hook_removed": True}}
    def receipt(row):
        rid = row["id"]
        ledger.bind("dispatch:" + rid, {"kind": "dispatch", "row_id": rid})
        destination = run / "rows" / (rid + ".json")
        write_once(destination, row)
        ledger.append_row(rid, {"path": "rows/" + destination.name, "sha256": report.clean.sha(destination)})
    receipt(qualification)
    rows, cert = [], {r["id"]: r for r in plan["certificate"]["items"]}
    (run / "residuals").mkdir()
    for item in plan["texts"]:
        row = fixture_row(item, cert[item["id"]])
        row["plan_sha256"] = plan_hash
        n = len(row["token_ids"])
        hidden = torch.zeros(1, n, 8192, dtype=torch.bfloat16)
        hidden[:, :, 0] = 1
        capture = run / row["capture"]["path"]
        save_file({"hidden": hidden, "token_ids": torch.tensor([row["token_ids"]])}, str(capture))
        row["capture"].update(sha256=report.clean.sha(capture), bytes=capture.stat().st_size)
        receipt(row)
        rows.append(row)
    write_once(run / "summary.json", report.clean.summarize(rows, plan))
    write_once(run / "model-bf16-load-test.json", {"test_only": True})
    return run, path, plan_hash, freeze


def test_real_clean_auditor_and_missing_pilot_report_are_read_only(synthetic_clean_run, tmp_path):
    run, plan, digest, freeze = synthetic_clean_run
    before = {p.relative_to(run).as_posix(): report.clean.sha(p) for p in run.rglob("*") if p.is_file()}
    result = report.generate_report(run, plan, freeze, tmp_path / "report", expected_sha256=digest)
    assert result["clean_audited_rows"] == 224 and result["synthetic_only"]
    assert result["pilot_status"]["status"] == "not_run"
    assert result["pilot_status"]["full_model_forwards"] is None
    assert before == {p.relative_to(run).as_posix(): report.clean.sha(p) for p in run.rglob("*") if p.is_file()}
    with (tmp_path / "report" / "precision_delivery.csv").open() as stream:
        values = list(csv.DictReader(stream))
    assert len(values) == 4 and all(row["fidelity_fraction"] == "" for row in values)


@pytest.mark.parametrize("field", ["summary.json", "rows/qualification-live.json"])
def test_clean_corruption_aborts_before_report_creation(synthetic_clean_run, tmp_path, field):
    run, plan, digest, freeze = synthetic_clean_run
    path = run / field
    original = path.read_bytes()
    path.write_text("{}\n")
    try:
        with pytest.raises(ValueError):
            report.generate_report(run, plan, freeze, tmp_path / "report", expected_sha256=digest)
        assert not (tmp_path / "report").exists()
    finally:
        path.write_bytes(original)


def test_wrong_plan_and_unsafe_output_block_before_audit(tmp_path, monkeypatch):
    plan = tmp_path / "plan.json"
    write_once(plan, synthetic_plan())
    def forbidden(*args, **kwargs):
        raise AssertionError("Must stop before opening outcomes")
    monkeypatch.setattr(report.clean, "audit_run", forbidden)
    with pytest.raises(ValueError, match="hash mismatch"):
        report.generate_report(tmp_path / "run", plan, "b" * 40, tmp_path / "report")
    with pytest.raises(ValueError, match="outside"):
        report.generate_report(tmp_path / "run", plan, "b" * 40, tmp_path / "run/report")
    with pytest.raises(ValueError, match="new report directory"):
        report.generate_report(tmp_path / "run", plan, "b" * 40, tmp_path)


def test_figures_csvs_and_hash_manifest_are_complete_and_nonblank(tmp_path):
    from PIL import Image
    destination = tmp_path / "synthetic-report"
    result = report.write_report(synthetic_bundle(), destination)
    assert result["synthetic_only"] and "no global" in result["scope"]
    assert len(result["outputs"]) == 9
    for name in ("exposure_counts", "precision_components"):
        with Image.open(destination / (name + ".png")) as picture:
            values = np.asarray(picture.convert("RGB"))
            assert picture.width >= 1500 and picture.height >= 1000
            assert np.count_nonzero(values.min(axis=2) < 240) > 10_000
        assert (destination / (name + ".pdf")).read_bytes().startswith(b"%PDF")
    for artifact in result["outputs"]:
        assert report.clean.sha(destination / artifact["path"]) == artifact["sha256"]
    with pytest.raises(ValueError, match="new directory"):
        report.write_report(synthetic_bundle(), destination)


def test_missing_pilot_layout_has_no_numeric_loss_scale():
    import matplotlib.pyplot as plt
    bundle = synthetic_bundle("not_run")
    charts = report.figures(report.make_tables(bundle), bundle)
    try:
        axes = charts["precision_components"].axes
        assert all(axis.get_xlim() == (-.5, 3.5) for axis in axes)
        assert all(len(axis.get_yticks()) == 0 for axis in axes[2:])
        assert all(any("No audited pilot" in text.get_text() for text in axis.texts) for axis in axes[2:])
    finally:
        for figure in charts.values():
            plt.close(figure)

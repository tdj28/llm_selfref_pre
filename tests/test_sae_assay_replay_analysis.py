"""Small, entirely synthetic saved-row tests; no model, GPU, API or download."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path

import numpy as np
import pytest

from experiments.sae_assay_diagnostic.budget import EventLedger
from experiments.sae_assay_replay import analysis

IDS = [3, 1]


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode() + b"\n"


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def fixture(text="cal-a", split="calibration", before=None):
    before = np.array([[1, 2], [2, 0], [0, 0], [4, 2]] if before is None else before, dtype=np.float32)
    n = len(before)
    pre = np.where(before > 0, before, -1).astype(np.float32)
    tokens = list(range(100, 100 + n))
    positions = [{"position": i, "token_id": t, "token_class": "special" if i == 0 else "prompt",
                  "origin": "prompt", "terminal_observation_only": False} for i, t in enumerate(tokens)]
    arms = {}
    for mode in analysis.MODES:
        delta = np.float32(0 if mode == "zero" else -.75 if mode == "suppression" else .75) * before
        norm = np.linalg.norm(delta, axis=1).astype(np.float32)
        after = before + delta
        changed_pre = pre + delta
        a = {"before": before, "after": after, "selected_before": before, "selected_after": after,
             "fp32_preact_before": pre, "fp32_preact_ideal": changed_pre, "fp32_preact_after": changed_pre,
             "requested_activation_delta": delta, "projection_coefficients": delta,
             "projection_scale": np.ones(n), "continuous_predicted_activation": after,
             "continuous_norm": np.linalg.norm(delta.astype(np.float64), axis=1),
             "l0_before": (before > 0).sum(1) + 2, "l0_after": (after > 0).sum(1) + 2,
             "non_target_change_norm": np.zeros(n), "non_target_changed_count": np.zeros(n, dtype=int),
             "non_target_activity_changes": np.zeros(n, dtype=int), "reconstruction_relative_error": np.full(n, .1),
             "requested_norm": norm, "realized_norm": norm, "clean_norm": np.full(n, 100.),
             "nonzero_requested": norm > 0, "identity": norm == 0, "cosine": np.ones(n), "relative_error": np.zeros(n)}
        arms[mode] = {key: value.tolist() for key, value in a.items()}
    capture = ("synthetic-capture-" + text).encode()
    source = {"id": "clean-" + text, "text_id": text, "split": split, "corpus": "synthetic",
              "mode": "zero", "strength": 0, "capture": {"path": "residuals/" + text + ".safetensors",
              "sha256": digest(capture), "bytes": len(capture)}, "result": {"token_ids": tokens, "telemetry": {
                  "feature_ids": IDS, "position_metadata": positions,
                  "delivery": {"valid": [True] * n, "clean_norm": [100.] * n},
                  "selected_activations": {"before": before.tolist()},
                  "full_sae": {"full_selected_before": before.tolist(), "fp32_preact_before": pre.tolist()}}}}
    row = {"id": "replay-" + text, "text_id": text, "split": split, "corpus": "synthetic",
           "source_row_sha256": digest(encoded(source)), "capture_sha256": digest(capture),
           "token_ids": tokens, "position_metadata": positions, "arms": arms, "elapsed_seconds": 2.}
    return deepcopy(row), deepcopy(source), capture


def write_run(tmp_path, monkeypatch, pairs=None, saved=None, pending=(), mutation=None):
    pairs = pairs or [fixture()]
    saved = range(len(pairs)) if saved is None else saved
    release = tmp_path / "source"
    (release / "rows").mkdir(parents=True)
    (release / "residuals").mkdir()
    plan = {"feature_ids": IDS, "gram": np.eye(2).tolist(), "inputs": [], "input_release": "source"}
    for row, source, capture in pairs:
        source_path = release / "rows" / (source["id"] + ".json")
        source_path.write_bytes(encoded(source))
        capture_path = release / source["capture"]["path"]
        capture_path.write_bytes(capture)
        row["source_row_sha256"] = digest(source_path.read_bytes())
        plan["inputs"].append({"id": row["text_id"], "row_path": source_path.relative_to(tmp_path).as_posix(),
                               "capture_path": capture_path.relative_to(tmp_path).as_posix(),
                               "row_sha256": row["source_row_sha256"], "capture_sha256": digest(capture)})
    plan["first_five"] = [i["id"] for i in plan["inputs"][:5]]
    plan_path = tmp_path / "PLAN.json"
    plan_path.write_bytes(encoded(plan))
    run = tmp_path / "run"
    (run / "rows").mkdir(parents=True)
    ledger = EventLedger(run / "receipts.jsonl", digest(plan_path.read_bytes()), "a" * 40,
                         [r["id"] for r, _, _ in pairs])
    ledger.bind("runtime", {"kind": "runtime"})
    for i in saved:
        row = deepcopy(pairs[i][0])
        if mutation is not None:
            mutation(row)
        rid = row["id"]
        ledger.bind("dispatch:" + rid, {"kind": "dispatch", "row_id": rid})
        path = run / "rows" / (rid + ".json")
        path.write_bytes(encoded(row))
        ledger.append_row(rid, {"path": "rows/" + rid + ".json", "sha256": digest(path.read_bytes())})
    for i in pending:
        rid = pairs[i][0]["id"]
        ledger.bind("dispatch:" + rid, {"kind": "dispatch", "row_id": rid})
    monkeypatch.setattr(analysis, "ROOT", tmp_path)
    monkeypatch.setattr(analysis, "load_plan", lambda p: json.loads(Path(p).read_bytes()))
    return run, plan_path, plan


def mode_report(rows, mode="suppression", split="calibration"):
    return analysis.summarize(rows, IDS)["splits"][split]["modes"][mode]


def test_valid_row_and_exact_historical_reconciliation():
    row, source, _ = fixture()
    comparison = analysis.validate_row(row, source, IDS)
    assert comparison["native_before"]["exact_fraction"] == 1
    assert comparison["zero_native"]["max_absolute_difference"] == 0
    assert comparison["features"]["3"]["original_active_nonspecial_positions"] == 2
    assert comparison["features"]["1"]["replay_active_nonspecial_positions"] == 1


def test_original_native_hardware_drift_is_descriptive_only():
    row, source, _ = fixture()
    original = source["result"]["telemetry"]
    original["full_sae"]["full_selected_before"][1] = [0., 1.]
    original["selected_activations"]["before"][1] = [0., 1.]
    c = analysis.validate_row(row, source, IDS)
    assert c["native_before"]["exact_fraction"] == .75
    assert c["native_before"]["active_to_inactive"] == 1
    assert c["native_before"]["inactive_to_active"] == 1
    assert c["native_before"]["max_absolute_difference"] == 2
    assert c["zero_native"] == c["native_before"]


@pytest.mark.parametrize("field,inside,outside", [
    ("pre", 1e-4 * .99, 1e-4 * 1.01), ("norm", 1e-3 * .99, 1e-3 * 1.01),
])
def test_original_geometry_tolerances(field, inside, outside):
    row, source, _ = fixture()
    for difference, should_pass in ((inside, True), (outside, False)):
        candidate = deepcopy(row)
        for a in candidate["arms"].values():
            if field == "pre":
                for name in ("fp32_preact_before", "fp32_preact_ideal", "fp32_preact_after"):
                    a[name][0][0] += difference
            else:
                a["clean_norm"][0] += difference
        if should_pass:
            analysis.validate_row(candidate, source, IDS)
        else:
            with pytest.raises(ValueError, match="drift"):
                analysis.validate_row(candidate, source, IDS)


@pytest.mark.parametrize("mode,field,value", [
    ("zero", "identity", [1, True, True, True]),
    ("zero", "nonzero_requested", [0, False, False, False]),
    ("suppression", "clean_norm", [True, 100., 100., 100.]),
    ("suppression", "relative_error", [float("nan"), 0., 0., 0.]),
    ("amplification", "before", [[float("inf"), 2.], [2., 0.], [0., 0.], [4., 2.]]),
    ("zero", "l0_before", [4., 3, 2, 4]),
    ("suppression", "l0_after", [65537, 3, 2, 4]),
    ("suppression", "clean_norm", [0., 100., 100., 100.]),
    ("suppression", "requested_norm", [-1., 1.5, 0., 3.]),
    ("suppression", "projection_scale", [0., 1., 1., 1.]),
    ("suppression", "cosine", [1.001, 1., 1., 1.]),
    ("suppression", "relative_error", [0., 0.]),
    ("suppression", "before", [[True, 2.], [2., 0.], [0., 0.], [4., 2.]]),
])
def test_bad_array_types_shapes_ranges_and_nonfinite(mode, field, value):
    row, source, _ = fixture()
    row["arms"][mode][field] = value
    with pytest.raises(ValueError):
        analysis.validate_row(row, source, IDS)


@pytest.mark.parametrize("kind", ["missing_arm", "missing_field", "extra_field", "bad_delta", "zero_changed",
                                  "inactive_request", "base_drift", "bad_token", "bad_position", "fake_bool_position",
                                  "source_tokens", "source_ids", "invalid_source", "elapsed_zero", "elapsed_bool"])
def test_hard_schema_identity_support_and_source_checks(kind):
    row, source, _ = fixture()
    if kind == "missing_arm":
        del row["arms"]["amplification"]
    elif kind == "missing_field":
        del row["arms"]["zero"]["after"]
    elif kind == "extra_field":
        row["arms"]["zero"]["unreviewed"] = [0] * 4
    elif kind == "bad_delta":
        row["arms"]["amplification"]["requested_activation_delta"][1][0] = .01
    elif kind == "zero_changed":
        row["arms"]["zero"]["after"][0][0] = .9
    elif kind == "inactive_request":
        a = row["arms"]["suppression"]
        a["requested_norm"][2] = a["realized_norm"][2] = 1.
        a["nonzero_requested"][2], a["identity"][2] = True, False
    elif kind == "base_drift":
        row["arms"]["amplification"]["reconstruction_relative_error"][1] = .2
    elif kind == "bad_token":
        row["token_ids"][1] = True
    elif kind == "bad_position":
        row["position_metadata"][1]["position"] = 2
    elif kind == "fake_bool_position":
        row["position_metadata"][1]["position"] = True
    elif kind == "source_tokens":
        source["result"]["token_ids"][1] += 1
    elif kind == "source_ids":
        source["result"]["telemetry"]["feature_ids"] = IDS[::-1]
    elif kind == "invalid_source":
        source["result"]["telemetry"]["delivery"]["valid"][1] = False
    elif kind == "elapsed_zero":
        row["elapsed_seconds"] = 0
    elif kind == "elapsed_bool":
        row["elapsed_seconds"] = True
    with pytest.raises(ValueError):
        analysis.validate_row(row, source, IDS)


def test_no_missing_zero_recoding_and_no_empty_success():
    row, _, _ = fixture()
    del row["arms"]["zero"]
    with pytest.raises(ValueError, match="three arms"):
        analysis.summarize([row], IDS)
    empty = analysis.summarize([], IDS)
    for split in analysis.SPLITS:
        for mode in analysis.MODES[1:]:
            r = empty["splits"][split]["modes"][mode]
            assert not r["native_components_pass"]
            assert r["fidelity"]["fraction"] is None
            assert r["norm"]["fraction"] is None
            assert r["features"]["3"]["native"]["median"] is None
    assert empty["behavioral_assay_qualified"] is False


def passing_rows():
    # Exactly 100 nonspecial positions in six texts. Special tokens do not count.
    return [fixture("cal-" + str(i), before=[[2., 2.]] * (18 if i < 5 else 16))[0] for i in range(6)]


def test_exposure_thresholds_and_historical_split_separation():
    rows = passing_rows()
    r = mode_report(rows)
    assert r["features"]["3"]["exposure"]["positions"] == 100
    assert r["features"]["3"]["exposure"]["texts"] == 6
    assert r["native_components_pass"] is True
    assert mode_report(rows, split="validation")["native_components_pass"] is False
    rows[-1]["position_metadata"][-1]["token_class"] = "special"
    assert mode_report(rows)["components"]["exposure"] is False
    five_texts = [fixture("cal-" + str(i), before=[[2., 2.]] * 21)[0] for i in range(5)]
    assert mode_report(five_texts)["features"]["3"]["exposure"]["positions"] == 100
    assert mode_report(five_texts)["components"]["exposure"] is False
    assert analysis.summarize(passing_rows(), IDS)["behavioral_assay_qualified"] is False


@pytest.mark.parametrize("mode,boundary,outside", [("suppression", 1., 1.00001), ("amplification", 2.75, 2.74999)])
def test_exact_efficacy_boundary_and_unclipped_amplification_denominator(mode, boundary, outside):
    row, _, _ = fixture(before=[[2., 2.]] * 3)
    a = row["arms"][mode]
    for value, passes in ((boundary, True), (outside, False)):
        a["after"] = [[value, value]] * 3
        # A small capped continuous prediction cannot become the denominator.
        a["projection_scale"] = [.1] * 3
        a["continuous_predicted_activation"] = [[2.1, 2.1]] * 3
        r = mode_report([row], mode)
        assert r["features"]["3"]["native"]["pass"] is passes
        assert r["features"]["3"]["native"]["median"] == pytest.approx(
            value / 2 if mode == "suppression" else (value - 2) / 1.5)


def test_delivery_exact_denominators_and_95_percent_boundaries():
    row, _, _ = fixture(before=[[2., 2.]] * 20)
    for a in row["arms"].values():
        a["clean_norm"] = [10.] * 20
        a["continuous_norm"] = [.1 if a["nonzero_requested"][i] else 0. for i in range(20)]
    a = row["arms"]["suppression"]
    a["cosine"], a["relative_error"], a["realized_norm"] = [.95] * 20, [.2] * 20, [.5] * 20
    a["cosine"][0], a["realized_norm"][0] = .949, .50001
    r = mode_report([row])
    assert r["fidelity"] == {"denominator": 20, "passing_positions": 19, "fraction": .95, "pass": True}
    assert r["norm"]["pass"] and r["norm"]["fraction"] == .95
    a["relative_error"][1], a["realized_norm"][1] = .20001, .50001
    r = mode_report([row])
    assert not r["fidelity"]["pass"] and not r["norm"]["pass"]


def test_rounded_away_and_all_inactive_retained():
    row, source, _ = fixture()
    a = row["arms"]["suppression"]
    a["identity"][1], a["realized_norm"][1], a["cosine"][1], a["relative_error"][1] = True, 0., 0., 1.
    for before, after in (("before", "after"), ("selected_before", "selected_after"),
                          ("fp32_preact_before", "fp32_preact_after")):
        a[after][1] = deepcopy(a[before][1])
    analysis.validate_row(row, source, IDS)
    r = mode_report([row])
    assert r["positions"] == 4 and r["nonspecial_positions"] == 3
    assert r["fidelity"]["denominator"] == 3 and r["norm"]["denominator"] == 2
    assert r["zero_requested_positions"] == r["all_inactive_positions"] == r["rounded_away_positions"] == 1
    assert r["features"]["3"]["native"]["ratio"]["count"] == 2
    assert r["features"]["3"]["native"]["median"] == .625
    assert r["distributions"]["all_positions"]["non_target_change_norm"]["count"] == 4
    assert r["distributions"]["nonspecial"]["l0_after"]["count"] == 3


def test_selected_path_disagreement_does_not_fail_native_or_change_mask():
    rows = passing_rows()
    for row in rows:
        row["arms"]["suppression"]["selected_after"] = [[1.5, 1.5]] * len(row["token_ids"])
    r = mode_report(rows)
    assert r["native_components_pass"] is True
    assert r["selected_width_components_pass"] is False
    assert len(r["decision_disagreements"]) == 2
    assert r["features"]["3"]["selected_width"]["ratio"]["count"] == 100
    row, _, _ = fixture()
    # The selected-only active coordinate is not a new eligible observation.
    for a in row["arms"].values():
        a["selected_before"][1][1] = 3.
        a["selected_before"][1][0] = 0.
    row["arms"]["zero"]["selected_after"][1] = [0., 3.]
    r = mode_report([row])
    assert r["features"]["1"]["exposure"]["positions"] == 1
    assert r["features"]["3"]["selected_width"]["undefined_positions"] == 1
    assert r["features"]["3"]["selected_width"]["median"] is None


def test_audit_full_inventory_and_scientific_failures_exit_success(tmp_path, monkeypatch, capsys):
    run, plan, _ = write_run(tmp_path, monkeypatch)
    before = {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    monkeypatch.setattr(EventLedger, "transact", lambda *a, **k: pytest.fail("Audit attempted a ledger write"))
    result = analysis.audit(run, plan)
    assert result["pass"], result["errors"]
    assert result["rows"] == result["expected"] == 1 and result["complete"]
    assert not result["summary"]["splits"]["calibration"]["modes"]["suppression"]["native_components_pass"]
    assert result["source_mismatch_counts"]["native_different_states"] == 0
    assert result["throughput"]["total_elapsed_seconds"] == 2
    assert result["behavioral_assay_qualified"] is False
    assert analysis.main(["--run", str(run), "--plan", str(plan)]) == 0
    assert json.loads(capsys.readouterr().out)["pass"] is True
    assert {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()} == before


def test_first_five_partial_throughput_and_source_mismatch_counts(tmp_path, monkeypatch):
    pairs = [fixture("cal-" + str(i)) for i in range(7)]
    t = pairs[0][1]["result"]["telemetry"]
    t["full_sae"]["full_selected_before"][1][0] = 0.
    t["selected_activations"]["before"][1][0] = 0.
    run, plan, _ = write_run(tmp_path, monkeypatch, pairs, saved=range(5), pending=(5,))
    result = analysis.audit(run, plan, partial=True)
    assert result["pass"] and not result["complete"]
    assert result["rows"] == 5 and result["expected"] == 7
    assert result["throughput"]["first_five"]["complete"]
    assert result["throughput"]["first_five"]["elapsed_seconds"] == 10
    assert result["throughput"]["estimated_remaining_compute_seconds_first_five"] == 4
    assert result["pending_dispatches"] == ["replay-cal-5"]
    assert result["source_mismatch_counts"]["native_different_states"] == 1
    assert result["source_mismatch_counts"]["active_support_changed_entries"] == 1
    hist = result["summary"]["historical_replay"]
    assert hist["exact_historical_native_replay"] is False
    assert hist["splits"]["calibration"]["features"]["3"]["original_exposure"]["positions"] == 9
    assert hist["splits"]["calibration"]["features"]["3"]["replay_exposure"]["positions"] == 10
    complete = analysis.audit(run, plan)
    assert not complete["pass"] and "Incomplete" in complete["errors"][0]


@pytest.mark.parametrize("failure", ["raw_bytes", "source_bytes", "capture_bytes", "extra_row", "missing_row",
                                     "empty_ledger", "missing_ledger", "truncated_ledger", "binding", "wrong_plan",
                                     "row_symlink", "ledger_symlink", "duplicate_json"])
def test_saved_artifact_corruption_fails_closed_without_writes(tmp_path, monkeypatch, failure):
    run, plan, frozen = write_run(tmp_path, monkeypatch)
    row_path = run / "rows/replay-cal-a.json"
    ledger = run / "receipts.jsonl"
    if failure == "raw_bytes":
        row_path.write_bytes(row_path.read_bytes() + b" ")
    elif failure == "source_bytes":
        (tmp_path / frozen["inputs"][0]["row_path"]).write_bytes(b"{}")
    elif failure == "capture_bytes":
        (tmp_path / frozen["inputs"][0]["capture_path"]).write_bytes(b"corrupt")
    elif failure == "extra_row":
        (run / "rows/extra.json").write_bytes(b"{}")
    elif failure == "missing_row":
        row_path.unlink()
    elif failure == "empty_ledger":
        ledger.write_bytes(b"")
    elif failure == "missing_ledger":
        ledger.unlink()
    elif failure == "truncated_ledger":
        ledger.write_bytes(ledger.read_bytes()[:-1])
    elif failure == "binding":
        ledger.write_bytes(ledger.read_bytes().replace(b"replay-cal-a", b"replay-cal-b"))
    elif failure == "wrong_plan":
        changed = json.loads(plan.read_bytes())
        changed["other"] = "changed"
        plan.write_bytes(encoded(changed))
    elif failure in ("row_symlink", "ledger_symlink"):
        path = row_path if failure == "row_symlink" else ledger
        moved = tmp_path / "moved"
        path.rename(moved)
        path.symlink_to(moved)
    elif failure == "duplicate_json":
        raw = row_path.read_bytes()
        row_path.write_bytes(raw.replace(b'{"arms":', b'{"id":"replay-cal-a","arms":', 1))
    before = {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    result = analysis.audit(run, plan, partial=True)
    assert not result["pass"] and result["errors"] and result["summary"] is None
    assert {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()} == before


@pytest.mark.parametrize("corruption", ["source_hash", "tokens", "zero", "delta", "projection", "native_before"])
def test_rehashed_malformed_raw_rows_are_still_rejected(tmp_path, monkeypatch, corruption):
    def mutate(row):
        if corruption == "source_hash":
            row["source_row_sha256"] = "b" * 64
        elif corruption == "tokens":
            row["token_ids"][1] += 1
            row["position_metadata"][1]["token_id"] += 1
        elif corruption == "zero":
            row["arms"]["zero"]["after"][1][0] = 1.
        elif corruption == "delta":
            row["arms"]["amplification"]["requested_activation_delta"][1][0] = .1
        elif corruption == "projection":
            row["arms"]["suppression"]["projection_coefficients"][1][0] = -.1
        else:
            row["arms"]["suppression"]["before"][1][0] = 1.
    run, plan, _ = write_run(tmp_path, monkeypatch, mutation=mutate)
    result = analysis.audit(run, plan)
    assert not result["pass"] and result["summary"] is None


def test_partial_checks_all_original_inputs_and_does_not_recode_missing(tmp_path, monkeypatch):
    pairs = [fixture("cal-a"), fixture("val-a", split="validation")]
    run, plan, frozen = write_run(tmp_path, monkeypatch, pairs, saved=(0,))
    result = analysis.audit(run, plan, partial=True)
    assert result["pass"] and result["missing_row_ids"] == ["replay-val-a"]
    val = result["summary"]["splits"]["validation"]
    assert val["rows"] == 0 and val["modes"]["suppression"]["features"]["3"]["native"]["median"] is None
    (tmp_path / frozen["inputs"][1]["capture_path"]).unlink()
    assert analysis.audit(run, plan, partial=True)["pass"] is False


@pytest.mark.parametrize("failure", ["inventory", "unknown_dispatch", "no_dispatch", "unsafe_path", "wrong_receipt_id"])
def test_fresh_canonical_ledgers_cannot_bypass_inventory_and_row_binding(tmp_path, monkeypatch, failure):
    run, plan, _ = write_run(tmp_path, monkeypatch)
    path = run / "rows/replay-cal-a.json"
    (run / "receipts.jsonl").unlink()
    ids = ["replay-other"] if failure == "inventory" else ["replay-cal-a"]
    ledger = EventLedger(run / "receipts.jsonl", digest(plan.read_bytes()), "a" * 40, ids)
    rid = "replay-cal-a"
    if failure == "unknown_dispatch":
        ledger.bind("dispatch:replay-extra", {"kind": "dispatch", "row_id": "replay-extra"})
    elif failure not in ("no_dispatch", "inventory"):
        ledger.bind("dispatch:" + rid, {"kind": "dispatch", "row_id": rid})
    if failure not in ("inventory", "unknown_dispatch"):
        name = "rows/../rows/replay-cal-a.json" if failure == "unsafe_path" else "rows/replay-cal-a.json"
        if failure == "wrong_receipt_id":
            row = json.loads(path.read_bytes())
            row["id"] = "replay-other"
            path.write_bytes(encoded(row))
        ledger.append_row(rid, {"path": name, "sha256": digest(path.read_bytes())})
    result = analysis.audit(run, plan, partial=True)
    assert not result["pass"] and result["summary"] is None


def test_rehashed_duplicate_keys_and_structural_cli_failure(tmp_path, monkeypatch, capsys):
    run, plan, _ = write_run(tmp_path, monkeypatch)
    path = run / "rows/replay-cal-a.json"
    path.write_bytes(path.read_bytes().replace(b'{"arms":', b'{"id":"replay-cal-a","arms":', 1))
    (run / "receipts.jsonl").unlink()
    ledger = EventLedger(run / "receipts.jsonl", digest(plan.read_bytes()), "a" * 40, ["replay-cal-a"])
    ledger.bind("dispatch:replay-cal-a", {"kind": "dispatch", "row_id": "replay-cal-a"})
    ledger.append_row("replay-cal-a", {"path": "rows/replay-cal-a.json", "sha256": digest(path.read_bytes())})
    assert analysis.main(["--run", str(run), "--plan", str(plan)]) == 1
    result = json.loads(capsys.readouterr().out)
    assert not result["pass"] and "Duplicate JSON key" in result["errors"][0]


def test_backend_small_cpu_dictionary_matches_validation_contract():
    torch = pytest.importorskip("torch")
    from experiments.sae_assay_replay.backend import replay
    e = torch.eye(8, dtype=torch.bfloat16)
    b = torch.zeros(8, dtype=torch.bfloat16)
    h = torch.tensor([[1, 2, 3, 4, 5, 6, 1000, 1000], [0, 0, 0, 0, 0, 0, 1000, 1000]], dtype=torch.bfloat16)
    ids = list(range(6))
    arms = replay(h, (e, b, e.T.contiguous(), b), ids, np.eye(6))
    row, source, _ = fixture(before=[[1, 2], [0, 0]])
    row["arms"] = arms
    source["result"]["telemetry"].update(feature_ids=ids,
        delivery={"valid": [True, True], "clean_norm": arms["zero"]["clean_norm"]},
        selected_activations={"before": arms["zero"]["before"]},
        full_sae={"full_selected_before": arms["zero"]["before"],
                  "fp32_preact_before": arms["zero"]["fp32_preact_before"]})
    assert analysis.validate_row(row, source, ids)["native_before"]["exact_fraction"] == 1
    analysis._geometry(row, np.eye(6))
    assert analysis.summarize([row], ids)["behavioral_assay_qualified"] is False

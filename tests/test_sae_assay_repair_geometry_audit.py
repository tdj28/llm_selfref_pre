"""Self-contained CPU fixtures: no released/private data or runtime imports."""
from contextlib import redirect_stdout
from copy import deepcopy
import hashlib
import io
import json
from pathlib import Path
import shutil
import subprocess
import sys

import numpy as np
import pytest

from experiments.sae_assay_repair import geometry_audit as audit


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("ascii")


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def fixture_rows():
    # Nonorthogonal E, nonsymmetric ED, negative preactivations, native/FP32
    # disagreement, special tokens, and native readout gaps larger than solve error.
    e = np.array([[1, .5, 0], [0, 2, 1]], dtype=np.float32)
    d = np.array([[1, .5], [.25, .75], [0, .25]], dtype=np.float32)
    bias = np.array([-.1, -.2], dtype=np.float32)
    matrices = {"decoder_span": e @ d, "encoder_min_norm": e @ e.T}
    ids = [9, 3]
    qualification = {"id": "qualification-live", "geometry": {
        "feature_ids": ids, "encoder_decoder_response": matrices["decoder_span"].tolist(),
        "encoder_gram": matrices["encoder_min_norm"].tolist()}}
    rows, states = [qualification], []
    for text, offset in (("calibration-alpha", 0), ("calibration-beta", .25)):
        h = np.array([[0, -1, 0], [3, 0, -3], [0, 2, 1], [1, -2, 5]], dtype=np.float32) + offset
        p = h @ e.T + bias
        native = np.maximum(np.round(p*8)/8, 0)
        tokens = [1, 2, 3, 4]
        t = {"feature_ids": ids, "repair_operator": "literal", "q90": None,
             "selected_activations": {"before": native.tolist(), "after": native.tolist(),
                                      "requested_activation": native.tolist(), "requested_delta": np.zeros_like(p).tolist()},
             "delivery": {"valid": [True]*4, "clean_norm": np.linalg.norm(h, axis=1).tolist(),
                          "requested_norm": [0.]*4},
             "position_metadata": [{"position": i, "token_id": token,
                                    "token_class": "special" if i == 0 else "prompt"}
                                   for i, token in enumerate(tokens)],
             "full_sae": {"fp32_preact_before": p.tolist(), "fp32_preact_after": p.tolist(),
                          "ideal_fp32_before": np.maximum(p, 0).tolist(),
                          "ideal_fp32_after": np.maximum(p, 0).tolist(),
                          "actual_fp32_after": np.maximum(p, 0).tolist(),
                          "full_selected_before": native.tolist(), "full_selected_after": native.tolist()}}
        clean = {"id": "clean-"+text, "text_id": text, "mode": "zero", "strength": 0,
                 "split": "calibration", "group": "literal", "result": {"token_ids": tokens, "telemetry": t}}
        rows.append(clean)
        states.append((clean, h, p, native))
    pooled = np.concatenate([z[1:] for _, _, _, z in states]).astype(np.float64)
    q = np.array([np.quantile(pooled[:, j][pooled[:, j] > 0], .9) for j in range(2)])
    saved_q = {"feature_ids": ids, "row_count": 2, "q90": q.tolist()}
    for clean, h, p, z in states:
        for op in ("literal", "decoder_span", "encoder_min_norm"):
            for mode in ("suppression", "amplification"):
                for dose in (.5, 1.):
                    row = deepcopy(clean)
                    row.update(id=f"edit-{op}-{clean['text_id']}-{mode}-{int(dose*100):03d}",
                               mode=mode, strength=dose, group=op)
                    t = row["result"]["telemetry"]
                    t["repair_operator"] = op
                    delta = -dose*z if mode == "suppression" else dose*np.maximum(q.astype(np.float32)-z, 0)
                    target = z + delta
                    eligible = z > 0 if mode == "suppression" else delta > 0
                    desired = np.where(eligible, target, p)
                    shift = desired-p
                    if op == "literal":
                        requested = delta @ d.T
                    else:
                        m = matrices[op]
                        coef = np.linalg.solve(m.astype(np.float64), shift.astype(np.float64).T).T.astype(np.float32)
                        requested = coef @ (d.T if op == "decoder_span" else e)
                        t["full_sae"].update(repair_eligible=eligible.tolist(), repair_desired_preact=desired.tolist(),
                                             repair_requested_preact_delta=shift.tolist(), repair_solve_coefficients=coef.tolist(),
                                             repair_solve_residual=(coef @ m.T-shift).tolist())
                    ideal = np.maximum((h+requested) @ e.T+bias, 0)
                    actual_p = (np.round((h+requested)*32)/32) @ e.T+bias
                    actual = np.maximum(actual_p, 0)
                    after = np.round(actual*8)/8
                    t["selected_activations"].update(after=after.tolist(), requested_delta=delta.tolist(),
                                                       requested_activation=target.tolist())
                    t["full_sae"].update(full_selected_after=after.tolist(), fp32_preact_after=actual_p.tolist(),
                                         ideal_fp32_after=ideal.tolist(), actual_fp32_after=actual.tolist())
                    t["q90"] = q.astype(np.float32).tolist() if mode == "amplification" else None
                    t["delivery"]["requested_norm"] = np.linalg.norm(requested.astype(np.float64), axis=1).astype(np.float32).tolist()
                    rows.append(row)
    return rows, saved_q


def write_run(root, rows, q, pending=(), undispatched=()):
    root.mkdir(exist_ok=True)
    (root / "rows").mkdir(exist_ok=True)
    events = []

    def event(identifier, data):
        value = {"id": identifier, "seq": len(events), "data": data,
                 "plan_sha256": "a"*64, "freeze_commit": "b"*40,
                 "previous_sha256": events[-1]["sha256"] if events else None}
        value["sha256"] = digest(canonical(value))
        events.append(value)

    event("binding", {"kind": "binding", "row_ids": sorted([r["id"] for r in rows] + list(pending) + list(undispatched))})
    for row in rows:
        rid = row["id"]
        raw = canonical(row)+b"\n"
        (root / "rows" / (rid+".json")).write_bytes(raw)
        event("dispatch:"+rid, {"kind": "dispatch", "row_id": rid})
        event("row:"+rid, {"kind": "row", "row_id": rid,
                          "payload": {"path": "rows/"+rid+".json", "sha256": digest(raw)}})
    for rid in pending:
        event("dispatch:"+rid, {"kind": "dispatch", "row_id": rid})
    (root / "receipts.jsonl").write_bytes(b"".join(canonical(e)+b"\n" for e in events))
    if q is not None:
        (root / "target-q90.json").write_bytes(canonical(q)+b"\n")
    return root


def edited(rows, op="encoder_min_norm", mode="amplification", dose=.5):
    return next(r for r in rows if r.get("group") == op and r.get("mode") == mode and r.get("strength") == dose)


def test_complete_synthetic_arithmetic_and_portable_read_only_report(tmp_path):
    rows, q = fixture_rows()
    run = write_run(tmp_path / "run", rows, q)
    before = {p.relative_to(run): p.read_bytes() for p in run.rglob("*") if p.is_file()}
    result = audit.audit(run)
    assert result["pass"], result["errors"]
    assert result["counts"] == {"clean": 2, "edits": 24, "qualification": 1,
                                "other_rows_hash_checked_only": 0, "edit_coordinates": 192, "repair_coordinates": 128}
    assert len(result["available_arms"]) == 12
    assert set(result["available_arms"].values()) == {2}
    assert result["q90"]["status"] == "recomputed_from_available_calibration"
    assert result["provenance"]["inflight_count"] == 0
    assert "not_complete" in result["provenance"]["scope"]
    assert result["max_absolute_errors"]["minimum_norm_relative_error_nonzero"]["value"] < 1e-5
    assert result["max_absolute_errors"]["native_after_vs_actual_fp32_after"]["value"] > .001
    assert result["max_absolute_errors"]["solve_reconstructed"]["value"] < 1e-5
    assert {p.relative_to(run): p.read_bytes() for p in run.rglob("*") if p.is_file()} == before
    assert str(tmp_path) not in json.dumps(result)
    shutil.copytree(run, tmp_path / "elsewhere")
    assert audit.audit(tmp_path / "elsewhere") == result


def test_exact_minimum_norm_formula_and_scopes(tmp_path):
    rows, q = fixture_rows()
    result = audit.audit(write_run(tmp_path / "run", rows, q))
    gram = np.asarray(rows[0]["geometry"]["encoder_gram"])
    a, b, c = gram[0, 0], gram[0, 1], gram[1, 1]
    ratios = []
    for row in rows:
        if row.get("group") == "encoder_min_norm" and row.get("mode") == "amplification" and row["strength"] == .5:
            t = row["result"]["telemetry"]
            u = np.asarray(t["full_sae"]["repair_requested_preact_delta"])
            # Closed-form 2x2 quadratic form, independent of numpy.linalg.solve.
            minimum = np.sqrt((c*u[:, 0]**2 - 2*b*u[:, 0]*u[:, 1] + a*u[:, 1]**2)/(a*c-b*b))
            ratios.extend(minimum/(.05*np.asarray(t["delivery"]["clean_norm"])))
    groups = result["minimum_norm_ratios_descriptive_only"]
    all_group = groups["calibration/amplification/0.5/all_valid"]
    assert all_group["ratio_all"]["count"] == 8
    assert all_group["ratio_all"]["median"] == pytest.approx(np.median(ratios))
    assert all_group["above_five_percent_clean"] == sum(r > 1 for r in ratios)
    assert groups["calibration/amplification/0.5/nonspecial_valid"]["ratio_all"]["count"] == 6
    assert any("not an impossibility" in limit for limit in result["limitations"])


@pytest.mark.parametrize("field,check", [
    ("repair_desired_preact", "preact_target"), ("repair_requested_preact_delta", "preact_shift"),
    ("repair_solve_coefficients", "recorded_solve_roundoff"), ("repair_solve_residual", "recorded_solve_roundoff"),
    ("repair_eligible", "repair_eligible"), ("requested_norm", "minimum_norm"),
    ("requested_activation", "activation_target"), ("requested_delta", "activation_delta"),
])
def test_arithmetic_tampering_detected_even_with_rehashed_receipts(tmp_path, field, check):
    rows, q = fixture_rows()
    t = edited(rows)["result"]["telemetry"]
    if field == "requested_norm":
        t["delivery"][field][1] += .5
    elif field == "repair_eligible":
        t["full_sae"][field][1][0] = not t["full_sae"][field][1][0]
    else:
        section = "full_sae" if field.startswith("repair_") else "selected_activations"
        t[section][field][1][0] += .5
    result = audit.audit(write_run(tmp_path / "run", rows, q))
    assert not result["pass"]
    assert check in {e["check"] for e in result["errors"]}


def test_negative_preactivation_deficits_and_ineligible_coordinates(tmp_path):
    rows, q = fixture_rows()
    amp = edited(rows)["result"]["telemetry"]
    assert amp["full_sae"]["fp32_preact_before"][0][0] < 0
    assert amp["full_sae"]["repair_requested_preact_delta"][0][0] > amp["selected_activations"]["requested_delta"][0][0]
    sup = edited(rows, mode="suppression")["result"]["telemetry"]
    assert not sup["full_sae"]["repair_eligible"][0][0]
    assert sup["full_sae"]["repair_requested_preact_delta"][0][0] == 0
    assert sup["full_sae"]["repair_desired_preact"][0][0] == sup["full_sae"]["fp32_preact_before"][0][0]
    assert audit.audit(write_run(tmp_path / "run", rows, q))["pass"]


def test_native_gap_is_not_tested_as_solve_residual(tmp_path):
    rows, q = fixture_rows()
    t = edited(rows)["result"]["telemetry"]
    t["selected_activations"]["after"][0][0] += 10
    t["full_sae"]["full_selected_after"] = deepcopy(t["selected_activations"]["after"])
    result = audit.audit(write_run(tmp_path / "run", rows, q))
    assert result["pass"]
    assert result["max_absolute_errors"]["native_after_vs_actual_fp32_after"]["value"] > 9
    assert result["max_absolute_errors"]["solve_reconstructed"]["value"] < 1e-5


def test_q90_validation_and_partial_snapshot_inflight(tmp_path):
    rows, q = fixture_rows()
    subset = [r for r in rows if r.get("text_id") != "calibration-beta"]
    result = audit.audit(write_run(tmp_path / "partial", subset, q, pending=["clean-later"], undispatched=["format-later"]))
    assert result["pass"]
    assert result["q90"]["status"] == "supplied_only_incomplete_calibration"
    assert result["provenance"]["inflight_row_ids"] == ["clean-later"]
    assert result["provenance"]["unmaterialized_bound_ids"] == 2
    bad_q = deepcopy(q)
    bad_q["q90"][0] += 1
    result = audit.audit(write_run(tmp_path / "bad-q", rows, bad_q))
    assert {"q90_recomputed", "amplification_q90"} <= {e["check"] for e in result["errors"]}
    with pytest.raises(ValueError, match="Amplification requires"):
        audit.audit(write_run(tmp_path / "no-q", rows, None))
    clean_only = [r for r in rows if not r["id"].startswith("edit-")]
    result = audit.audit(write_run(tmp_path / "clean-only", clean_only, None))
    assert result["pass"] and result["q90"]["status"] == "not_available"


@pytest.mark.parametrize("corruption", ["raw", "chain", "truncated", "orphan", "missing", "unsafe", "symlink"])
def test_worker_integrity_failures(tmp_path, corruption):
    rows, q = fixture_rows()
    run = write_run(tmp_path / "run", rows, q)
    path = run / "rows/qualification-live.json"
    ledger = run / "receipts.jsonl"
    if corruption == "raw":
        path.write_bytes(path.read_bytes()+b" ")
    elif corruption == "chain":
        ledger.write_bytes(ledger.read_bytes().replace(b'"freeze_commit":"b', b'"freeze_commit":"c', 1))
    elif corruption == "truncated":
        ledger.write_bytes(ledger.read_bytes()[:-1])
    elif corruption == "orphan":
        (run / "rows/orphan.json").write_text("{}")
    elif corruption == "missing":
        path.unlink()
    elif corruption == "symlink":
        outside = tmp_path / "outside.json"
        path.rename(outside)
        path.symlink_to(outside)
    else:
        events = [json.loads(line) for line in ledger.read_bytes().splitlines()]
        events[2]["data"]["payload"]["path"] = "../qualification-live.json"
        previous = None
        for event in events:
            event["previous_sha256"] = previous
            event.pop("sha256")
            event["sha256"] = digest(canonical(event))
            previous = event["sha256"]
        ledger.write_bytes(b"".join(canonical(e)+b"\n" for e in events))
    with pytest.raises(ValueError):
        audit.audit(run)


@pytest.mark.parametrize("case", ["shape", "boolean", "singular", "missing-pair"])
def test_malformed_numerical_inputs(tmp_path, case):
    rows, q = fixture_rows()
    t = edited(rows)["result"]["telemetry"]
    if case == "shape":
        t["full_sae"]["repair_solve_coefficients"].pop()
    elif case == "boolean":
        t["full_sae"]["repair_eligible"][0][0] = 1
    elif case == "singular":
        rows[0]["geometry"]["encoder_gram"] = [[0, 0], [0, 0]]
    else:
        rows = [r for r in rows if r["id"] != "clean-calibration-alpha"]
    with pytest.raises(ValueError):
        audit.audit(write_run(tmp_path / "run", rows, q))


@pytest.mark.parametrize("raw", [b'{"x":1,"x":2}', b'{"x":NaN}', b'{"x":1e999}', b'[]'])
def test_strict_json(raw):
    with pytest.raises(ValueError):
        audit._decode(raw)


def test_cli_fresh_output_no_runtime_imports_and_no_input_writes(tmp_path):
    rows, q = fixture_rows()
    run = write_run(tmp_path / "run", rows, q)
    out = tmp_path / "audit.json"
    stdout = io.StringIO()
    with redirect_stdout(stdout):
        assert audit.main(["--run", str(run), "--out", str(out)]) == 0
        original = out.read_bytes()
        assert audit.main(["--run", str(run), "--out", str(out)]) == 2
        assert out.read_bytes() == original
        assert audit.main(["--run", str(run), "--out", str(run / "new.json")]) == 2
    assert not (run / "new.json").exists()
    assert str(tmp_path) not in stdout.getvalue() + out.read_text()
    # Isolated interpreter supports direct-file CLI and proves dependency isolation.
    module = str(Path(audit.__file__).resolve())
    code = ("import runpy,sys; runpy.run_path(sys.argv[1],run_name='audit_import_test'); "
            "assert 'torch' not in sys.modules; "
            "assert not any(n.startswith('experiments.') for n in sys.modules)")
    subprocess.run([sys.executable, "-I", "-B", "-c", code, module], cwd=tmp_path, check=True)
    subprocess.run([sys.executable, "-I", "-B", module, "--run", str(run), "--out", str(tmp_path / "direct.json")],
                   cwd=tmp_path, check=True, capture_output=True)


def test_cli_writes_failed_arithmetic_report_with_nonzero_status(tmp_path):
    rows, q = fixture_rows()
    edited(rows)["result"]["telemetry"]["delivery"]["requested_norm"][0] += 2
    run = write_run(tmp_path / "run", rows, q)
    out = tmp_path / "failed.json"
    with redirect_stdout(io.StringIO()):
        assert audit.main(["--run", str(run), "--out", str(out)]) == 1
    assert not json.loads(out.read_text())["pass"]


@pytest.mark.parametrize("case", ["source-binding", "duplicate-row", "unknown-row", "missing-dispatch"])
def test_rehashed_but_invalid_worker_history(tmp_path, case):
    rows, q = fixture_rows()
    run = write_run(tmp_path / "run", rows, q)
    path = run / "receipts.jsonl"
    events = [json.loads(line) for line in path.read_bytes().splitlines()]
    if case == "source-binding":
        events[2]["plan_sha256"] = "c"*64
    elif case == "duplicate-row":
        events.append(deepcopy(events[2]))
    elif case == "unknown-row":
        events[0]["data"]["row_ids"].remove("qualification-live")
    else:
        events.pop(1)
    previous = None
    for i, event in enumerate(events):
        event.update(seq=i, previous_sha256=previous)
        event.pop("sha256")
        event["sha256"] = digest(canonical(event))
        previous = event["sha256"]
    path.write_bytes(b"".join(canonical(e)+b"\n" for e in events))
    with pytest.raises(ValueError):
        audit.audit(run)


def test_special_and_invalid_positions_are_excluded_from_q90(tmp_path):
    rows, _ = fixture_rows()
    rows = [r for r in rows if not r["id"].startswith("edit-")]
    for row in rows[1:]:
        t = row["result"]["telemetry"]
        t["delivery"]["valid"][1] = False
        # Native special and invalid positions must not affect positive q90.
        for name in ("before", "after", "requested_activation"):
            t["selected_activations"][name][0] = [10000, 10000]
            t["selected_activations"][name][1] = [20000, 20000]
        for name in ("full_selected_before", "full_selected_after"):
            t["full_sae"][name] = deepcopy(t["selected_activations"]["before"])
    pooled = np.concatenate([r["result"]["telemetry"]["selected_activations"]["before"][2:] for r in rows[1:]])
    q = {"feature_ids": [9, 3], "row_count": 2,
         "q90": [float(np.quantile(pooled[:, j][pooled[:, j] > 0], .9)) for j in range(2)]}
    result = audit.audit(write_run(tmp_path / "run", rows, q))
    assert result["pass"], result["errors"]
    assert result["q90"]["recomputed_q90"] == pytest.approx(q["q90"])


def test_unused_singular_decoder_is_not_an_encoder_veto(tmp_path):
    rows, q = fixture_rows()
    rows = [r for r in rows if not r["id"].startswith("edit-") or r["group"] == "encoder_min_norm"]
    rows[0]["geometry"]["encoder_decoder_response"] = [[0, 0], [0, 0]]
    result = audit.audit(write_run(tmp_path / "run", rows, q))
    assert result["pass"]
    assert result["geometry_conditions"]["decoder_span"] is None


def test_changed_snapshot_rejected_before_output_and_output_aliases(tmp_path, monkeypatch):
    rows, q = fixture_rows()
    run = write_run(tmp_path / "run", rows, q)
    read = audit._Inputs.read
    seen = set()

    def changed(self, name):
        raw = read(self, name)
        if name == "target-q90.json" and name in seen:
            return raw + b" "
        seen.add(name)
        return raw

    with monkeypatch.context() as patch:
        patch.setattr(audit._Inputs, "read", changed)
        with redirect_stdout(io.StringIO()):
            assert audit.main(["--run", str(run), "--out", str(tmp_path / "changed.json")]) == 2
        assert not (tmp_path / "changed.json").exists()
    alias = tmp_path / "alias"
    alias.symlink_to(run, target_is_directory=True)
    dangling = tmp_path / "dangling.json"
    dangling.symlink_to(tmp_path / "absent.json")
    with redirect_stdout(io.StringIO()):
        assert audit.main(["--run", str(run), "--out", str(alias / "new.json")]) == 2
        assert audit.main(["--run", str(run), "--out", str(dangling)]) == 2
    assert not (run / "new.json").exists()
    assert not (tmp_path / "absent.json").exists()

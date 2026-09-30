"""Small synthetic saved-telemetry fixtures; no real outcomes, models or APIs."""

from contextlib import ExitStack
from copy import deepcopy
import hashlib
import json
import math
import shutil
import subprocess
import sys
from unittest.mock import patch

import pytest

from experiments.sae_assay_repair import failure_census as census


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("ascii")


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def clean_row(text="example", corpus=census.CORPORA[0], split="calibration"):
    before = [[2., 2.], [2., 0.], [0., 0.], [0., 2.], [2., 2.], [2., 0.]]
    return {"id": "clean-" + text, "text_id": text, "corpus": corpus, "split": split,
            "category": "neutral", "group": "literal", "mode": "zero", "strength": 0.,
            "result": {"token_ids": list(range(6)), "unsteered_nll": [None] + [2.] * 5,
                       "edited_nll": [None] + [2.] * 5,
                "telemetry": {"feature_ids": [30032, 22004], "repair_operator": "literal", "q90": None,
                    "position_metadata": [{"position": i, "token_id": i, "origin": "prompt",
                                           "token_class": "special" if i == 0 else "prompt"} for i in range(6)],
                    "selected_activations": {"before": deepcopy(before), "after": deepcopy(before),
                                             "requested_delta": [[0., 0.] for _ in range(6)],
                                             "requested_activation": deepcopy(before)},
                    "delivery": {"clean_norm": [100.] * 6, "requested_norm": [0.] * 6,
                                 "realized_norm": [0.] * 6, "cosine": [1.] * 6,
                                 "relative_error": [0.] * 6, "nonzero_requested": [False] * 6,
                                 "identity": [True] * 6, "valid": [True] * 5 + [False]},
                    "full_sae": {"full_selected_before": deepcopy(before), "full_selected_after": deepcopy(before),
                                 "selected_path_before": deepcopy(before), "selected_path_after": deepcopy(before)}}}}


def edit_row(clean, op="literal", mode="suppression", strength=.5):
    row = deepcopy(clean)
    row.update(id=f"edit-{op}-{clean['text_id']}-{mode}-{int(strength*100):03d}",
               group=op, mode=mode, strength=strength)
    t = row["result"]["telemetry"]
    t["repair_operator"] = op
    t["q90"] = [6., 6.] if mode == "amplification" else None
    a, d = t["selected_activations"], t["delivery"]
    for i, before in enumerate(a["before"]):
        delta = [(-strength*b if mode == "suppression" else strength*(6.-b))
                 if d["valid"][i] else 0. for b in before]
        a["requested_delta"][i] = delta
        a["requested_activation"][i] = [b+v for b, v in zip(before, delta)]
        a["after"][i] = [b+.5*v for b, v in zip(before, delta)]
        nonzero = any(delta)
        d["nonzero_requested"][i] = nonzero
        d["identity"][i] = not nonzero
        d["requested_norm"][i] = d["realized_norm"][i] = 1. if nonzero else 0.
    t["full_sae"]["full_selected_after"] = deepcopy(a["after"])
    t["full_sae"]["selected_path_after"] = deepcopy(a["after"])
    return row


def write_run(root, rows):
    root.mkdir()
    (root / "rows").mkdir()
    events = []

    def event(identifier, data):
        value = {"id": identifier, "seq": len(events), "data": data,
                 "plan_sha256": "a" * 64, "freeze_commit": "b" * 40,
                 "previous_sha256": events[-1]["sha256"] if events else None}
        value["sha256"] = sha(canonical(value))
        events.append(value)

    event("binding", {"kind": "binding", "row_ids": sorted(r["id"] for r in rows)})
    for row in rows:
        rid = row["id"]
        raw = canonical(row) + b"\n"
        (root / "rows" / (rid + ".json")).write_bytes(raw)
        event("dispatch:" + rid, {"kind": "dispatch", "row_id": rid})
        event("row:" + rid, {"kind": "row", "row_id": rid,
                            "payload": {"path": "rows/" + rid + ".json", "sha256": sha(raw)}})
    (root / "receipts.jsonl").write_bytes(b"".join(canonical(e) + b"\n" for e in events))
    return root


def arm(report, op="literal", mode="suppression", strength=.5, split="calibration"):
    return next(a["splits"][split] for a in report["edited_arms"] if
                (a["operator"], a["direction"], a["strength"]) == (op, mode, strength))


def failures_fixture():
    clean = clean_row()
    edited = edit_row(clean)
    t = edited["result"]["telemetry"]
    d = t["delivery"]
    d.update(requested_norm=[.5, 1., 0., 2., 4., 0.], realized_norm=[.5, 0., 0., 6., 4., 0.],
             cosine=[.94, 0., 1., 1., .95, 1.], relative_error=[.1, 1., 0., .20, .21, 0.],
             identity=[False, True, True, False, False, True])
    t["selected_activations"]["after"][1] = [2., 0.]
    for name in ("full_selected_after", "selected_path_after"):
        t["full_sae"][name] = deepcopy(t["selected_activations"]["after"])
    return [clean, edited]


def test_known_counts_masks_component_failures_and_exclusions(tmp_path):
    result = census.report(write_run(tmp_path / "run", failures_fixture()))
    a = arm(result)
    c = a["all_positions"]
    assert c["positions"] == 6 and c["invalid_positions"] == 1
    assert c["fidelity_failed"] == {"numerator": 3, "denominator": 4, "fraction": .75}
    assert c["cosine_failed"] == 2 and c["relative_error_failed"] == 2
    assert c["both_fidelity_components_failed"] == 1
    assert c["nonzero_request_zero_realized"] == 1
    assert c["zero_request_excluded_fidelity"] == 2
    assert c["norm_failed"] == {"numerator": 1, "denominator": 3, "fraction": 1/3}
    assert c["zero_realized_excluded_norm"] == 3
    assert c["joint_failed"] == {"numerator": 0, "denominator": 3, "fraction": 0.}
    special, normal = (a["by_token_class"][s] for s in ("special", "nonspecial"))
    assert special["all"]["fidelity_failed"]["denominator"] == 1
    assert normal["all"]["fidelity_failed"]["denominator"] == 3
    assert normal["all"]["norm_failed"]["denominator"] == 2
    for scope in (special, normal):
        for field in ("by_clean_active_count", "by_requested_clean_norm_bin"):
            assert sum(c["positions"] for c in scope[field]) == scope["all"]["positions"]
            for metric in ("fidelity_failed", "norm_failed"):
                for count in ("numerator", "denominator"):
                    assert sum(c[metric][count] for c in scope[field]) == scope["all"][metric][count]
    active = {c["active_count"]: c for c in normal["by_clean_active_count"]}
    assert active[0]["zero_request_excluded_fidelity"] == 1
    assert active[1]["fidelity_failed"]["numerator"] == 1
    assert active[1]["invalid_positions"] == 1
    bins = {c["bin"]: c for c in normal["by_requested_clean_norm_bin"]}
    assert bins["(0.005,0.01]"]["nonzero_request_zero_realized"] == 1
    assert bins["zero"]["positions"] == 2
    exposure = next(c for c in result["clean_exposure"] if c["feature_id"] == 22004 and
                    c["corpus"] == census.CORPORA[0] and c["split"] == "calibration")
    assert exposure["scopes"]["nonspecial_valid"]["active_positions"] == {
        "numerator": 2, "denominator": 4, "fraction": .5}
    assert exposure["scopes"]["special"]["active_positions"]["numerator"] == 1
    assert a["coordinate_efficacy"][0]["native"]["median"] == .875
    assert a["coordinate_efficacy"][1]["native"]["median"] == .75


def test_all_twelve_arms_corpora_and_splits_no_heavy_or_gate_calls(tmp_path):
    rows = [{"id": "qualification-live", "not_used": True}]
    for i, corpus in enumerate(census.CORPORA):
        for split in census.SPLITS:
            clean = clean_row(f"text-{i}-{split}", corpus, split)
            rows.append(clean)
            rows.extend(edit_row(clean, op, mode, strength) for op in census.OPERATORS
                        for mode in census.analysis.DIRECTIONS for strength in census.analysis.STRENGTHS)
    run = write_run(tmp_path / "run", rows)
    before = {p.relative_to(run): p.read_bytes() for p in run.rglob("*") if p.is_file()}
    with ExitStack() as stack:
        for name in ("gate_pair", "select_strength", "_direction", "encoder_decision_report", "calibration_q90"):
            stack.enter_context(patch.object(census.analysis, name, side_effect=AssertionError(name)))
        stack.enter_context(patch.object(census.geometry_audit, "audit", side_effect=AssertionError("heavy audit")))
        result = census.report(run)
    assert len(result["edited_arms"]) == 12
    assert result["counts"] == {"raw_rows": 53, "clean_rows": 4, "edited_rows": 48,
                                "other_rows_hash_checked_only": 1}
    for a in result["edited_arms"]:
        for cell in a["splits"].values():
            assert cell["status"] == "observed" and cell["row_count"] == 2
            assert cell["paired_clean_text_coverage"]["fraction"] == 1
    assert {p.relative_to(run): p.read_bytes() for p in run.rglob("*") if p.is_file()} == before
    shutil.copytree(run, tmp_path / "copy")
    assert census.report(tmp_path / "copy") == result
    hashes = {str(p): sha(raw) for p, raw in before.items()}
    assert result["input_hashes"]["path_sha256_index_sha256"] == sha(canonical(hashes))
    assert str(tmp_path) not in json.dumps(result)
    assert result["post_outcome"] and not result["frozen_results_changed"]


def test_missing_arms_and_diagnostics_are_not_zero_effects(tmp_path):
    rows = failures_fixture()
    for r in rows:
        del r["result"]["telemetry"]["full_sae"]["selected_path_before"]
        del r["result"]["telemetry"]["full_sae"]["selected_path_after"]
    result = census.report(write_run(tmp_path / "run", rows))
    empty = arm(result, split="validation")
    assert empty["status"] == "not_recorded"
    assert empty["all_positions"]["fidelity_failed"]["fraction"] is None
    assert empty["coordinate_efficacy"][0]["native"]["median"] is None
    assert empty["coordinate_efficacy"][0]["native"]["frozen_exposure_component"] is None
    a = arm(result)
    assert a["native_vs_selected"]["missing_rows"] == 1
    assert a["coordinate_efficacy"][0]["selected"]["median"] is None
    assert a["coordinate_efficacy"][0]["efficacy_component_disagrees"] is None


def test_native_selected_disagreement_preserved_without_requalification(tmp_path):
    clean = clean_row()
    edited = edit_row(clean, op="encoder_min_norm", strength=1.)
    t = edited["result"]["telemetry"]
    # Native retention exactly .5 passes the frozen component; selected .6 fails.
    t["full_sae"]["selected_path_after"][1][0] = 1.2
    t["full_sae"]["selected_path_after"][4][0] = 1.2
    t["full_sae"]["selected_path_after"][2][0] = .125
    result = census.report(write_run(tmp_path / "run", [clean, edited]))
    a = arm(result, op="encoder_min_norm", strength=1.)
    feature = a["coordinate_efficacy"][0]
    assert feature["native"]["median"] == .5 and feature["selected"]["median"] == .6
    assert feature["efficacy_component_disagrees"] is True
    comparison = next(c for c in a["native_vs_selected"]["comparisons"] if
                      c["token_class"] == "nonspecial" and c["phase"] == "after")
    assert comparison["activity_mismatch"]["numerator"] == 1
    assert comparison["activity_mismatch"]["denominator"] == 10


@pytest.mark.parametrize("edge,index", list(zip(census.RATIO_EDGES, range(1, 6))))
def test_requested_ratio_bins_are_right_closed(edge, index):
    assert census._ratio_bin(edge, 1.) == census.RATIO_BINS[index]
    assert census._ratio_bin(math.nextafter(edge, math.inf), 1.) == census.RATIO_BINS[index+1]
    assert census._ratio_bin(0., 1.) == "zero"
    assert census._ratio_bin(1., 0.) == "undefined_zero_clean"


def test_zero_clean_norm_is_included_as_norm_failure(tmp_path):
    rows = failures_fixture()
    for row in rows:
        row["result"]["telemetry"]["delivery"]["clean_norm"][3] = 0.
    a = arm(census.report(write_run(tmp_path / "run", rows)))
    assert a["all_positions"]["norm_failed"]["denominator"] == 3
    assert a["all_positions"]["realized_with_zero_clean_norm"] == 1
    cell = a["by_token_class"]["nonspecial"]["by_requested_clean_norm_bin"][-1]
    assert cell["bin"] == "undefined_zero_clean" and cell["norm_failed"]["numerator"] == 1


def test_strict_fidelity_norm_thresholds_and_requested_not_realized_bins(tmp_path):
    rows = failures_fixture()
    d = rows[1]["result"]["telemetry"]["delivery"]
    d["cosine"][0], d["relative_error"][0], d["realized_norm"][0] = .95, .20, 5.
    d["realized_norm"][3] = math.nextafter(5., math.inf)
    a = arm(census.report(write_run(tmp_path / "run", rows)))
    special = a["by_token_class"]["special"]
    assert special["all"]["fidelity_failed"]["numerator"] == 0
    assert special["all"]["norm_failed"]["numerator"] == 0
    # Requested ratio .005 stays in the first bin despite realized ratio .05.
    assert special["by_requested_clean_norm_bin"][1]["positions"] == 1
    assert a["all_positions"]["norm_failed"]["numerator"] == 1


@pytest.mark.parametrize("mutation", [
    lambda r: r.update(corpus=census.CORPORA[1]),
    lambda r: r.update(split="validation"),
    lambda r: r.update(category="roleplay"),
    lambda r: r["result"]["unsteered_nll"].__setitem__(1, 3.),
    lambda r: r["result"]["telemetry"]["delivery"]["clean_norm"].__setitem__(1, 99.),
    lambda r: r["result"]["telemetry"]["position_metadata"][1].update(token_class="special"),
    lambda r: r["result"]["telemetry"]["full_sae"]["selected_path_before"][1].__setitem__(0, 3.),
])
def test_cross_arm_pair_metadata_rejected_even_with_rehashed_receipts(tmp_path, mutation):
    rows = failures_fixture()
    mutation(rows[1])
    with pytest.raises(ValueError, match="Paired"):
        census.report(write_run(tmp_path / "run", rows))


@pytest.mark.parametrize("mutation,message", [
    (lambda r: r["result"]["telemetry"]["feature_ids"].reverse(), "feature IDs"),
    (lambda r: r["result"]["telemetry"]["delivery"]["nonzero_requested"].__setitem__(0, False), "nonzero_requested"),
    (lambda r: r["result"]["telemetry"]["delivery"]["cosine"].__setitem__(0, True), "number"),
    (lambda r: r["result"]["telemetry"]["full_sae"]["full_selected_after"][1].__setitem__(0, 123.), "Canonical/native"),
    (lambda r: r.update(strength=1.), "Suppression request"),
    (lambda r: r["result"]["telemetry"].update(repair_operator="decoder_span"), "operator mismatch"),
])
def test_corrupt_telemetry_is_not_silently_classified(tmp_path, mutation, message):
    rows = failures_fixture()
    mutation(rows[1])
    with pytest.raises(ValueError, match=message):
        census.report(write_run(tmp_path / "run", rows))


def test_missing_clean_and_changed_raw_hash_fail(tmp_path):
    rows = failures_fixture()
    with pytest.raises(ValueError, match="clean"):
        census.report(write_run(tmp_path / "missing", rows[1:]))
    run = write_run(tmp_path / "run", rows)
    path = run / "rows" / (rows[1]["id"] + ".json")
    path.write_bytes(path.read_bytes() + b" ")
    with pytest.raises(ValueError, match="hash mismatch"):
        census.report(run)


def test_duplicate_json_keys_rejected(tmp_path):
    run = write_run(tmp_path / "run", failures_fixture())
    path = run / "receipts.jsonl"
    path.write_bytes(path.read_bytes().replace(b'"seq":0', b'"seq":0,"seq":0', 1))
    with pytest.raises(ValueError, match="Duplicate JSON key"):
        census.report(run)


def test_changed_during_read_and_symlink_inputs_fail(tmp_path):
    rows = failures_fixture()
    run = write_run(tmp_path / "run", rows)
    original = census.geometry_audit._Inputs.verify_unchanged

    def change_then_verify(inputs):
        path = run / "rows" / (rows[0]["id"] + ".json")
        path.write_bytes(path.read_bytes() + b" ")
        original(inputs)

    with patch.object(census.geometry_audit._Inputs, "verify_unchanged", change_then_verify):
        with pytest.raises(ValueError, match="Input changed"):
            census.report(run)
    run2 = write_run(tmp_path / "run2", rows)
    path = run2 / "rows" / (rows[0]["id"] + ".json")
    outside = tmp_path / "outside.json"
    path.rename(outside)
    path.symlink_to(outside)
    with pytest.raises(ValueError, match="symlinked input"):
        census.report(run2)


def test_cli_fresh_output_and_immutable_run_guards(tmp_path):
    run = write_run(tmp_path / "run", failures_fixture())
    output = tmp_path / "census.json"
    command = [sys.executable, "-m", "experiments.sae_assay_repair.failure_census", "--run", str(run), "--out", str(output)]
    completed = subprocess.run(command, capture_output=True, text=True)
    assert completed.returncode == 0, completed.stderr + completed.stdout
    assert json.loads(output.read_bytes())["counts"]["edited_rows"] == 1
    original = output.read_bytes()
    assert census.main(["--run", str(run), "--out", str(output)]) == 2
    assert output.read_bytes() == original
    inside = run / "forbidden.json"
    assert census.main(["--run", str(run), "--out", str(inside)]) == 2
    assert not inside.exists()
    alias = tmp_path / "alias"
    alias.symlink_to(run, target_is_directory=True)
    assert census.main(["--run", str(run), "--out", str(alias / "forbidden.json")]) == 2
    dangling = tmp_path / "dangling"
    dangling.symlink_to(tmp_path / "absent")
    assert census.main(["--run", str(run), "--out", str(dangling)]) == 2

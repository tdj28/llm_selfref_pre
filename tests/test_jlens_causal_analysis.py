"""Adversarial synthetic snapshots; never read study outcomes or load a model.

Negative tests assert rejection, not the historical buggy acceptance. Failures
therefore identify unfixed integrity contracts without hiding them as xfails.
"""
import copy
import hashlib
import json

import numpy as np
import pytest
import torch

from experiments.jlens_causal_report import analysis, protocol
from experiments.jlens_causal_report.operators import patch_component, random_orthonormal_basis
from experiments.sae_assay_diagnostic.budget import EventLedger


def _hash(value):
    return hashlib.sha256(protocol.canonical(value).encode()).hexdigest()


def _pack(value):
    if isinstance(value, torch.Tensor):
        return value.float().tolist() if value.is_floating_point() else value.tolist()
    if isinstance(value, dict):
        return {str(k): _pack(v) for k, v in value.items()}
    return value


def _score(answer):
    return {"token_id": 10 if answer == "A" else 12, "decoded": answer, "answer": answer,
            "code_token_ids": {"A": [10, 11], "B": [12, 13]},
            "code_probability": {"A": .4, "B": .2}, "conditional_A": 2 / 3,
            "code_logits": {"A": [2., 1.] if answer == "A" else [1., 0.],
                            "B": [2., 1.] if answer == "B" else [1., 0.]}}


def _forward(answer, sign, token):
    states, readouts = {}, {}
    for layer in protocol.LAYERS:
        value = [32., float(sign), 0., 0.]
        states[str(layer)] = {"layer": layer, "position": 2, "hook_calls": 1,
                              "before": value[:], "after": value[:],
                              "realized_delta": [0.] * 4, "telemetry": {}}
        readout = {name: {"token_logits": [0., 0.], "linear_token_logits": [0., 0.],
                          "transport_norm": float(np.linalg.norm(value)), "groups": {"test": 0.}}
                   for name in ["identity", "jacobian"] + [f"random_j_{i}" for i in range(1, 6)]}
        readouts[str(layer)] = {"before": copy.deepcopy(readout), "after": copy.deepcopy(readout)}
    return {"input_token_ids": [1, 2, token], "position": 2, "use_cache": False,
            "states": states, "score": _score(answer), "readouts": readouts,
            "telemetry": {"position": 2, "native_dtype": "torch.bfloat16", "use_cache": False,
                          "hook_calls": {"40": 1, "50": 1}, "edits": {}}}


def _pair(spec, candidate=None):
    clean = {case["id"]: _forward(case["expected_answer"], 1 if i == 0 else -1, 30 + i)
             for i, case in enumerate(spec["cases"])}
    row = {"id": spec["id"], "spec": copy.deepcopy(spec), "clean": clean, "trials": []}
    if spec["split"] == "discovery":
        return row
    row["candidate_sha256"] = candidate["sha256"]
    q = torch.tensor(candidate["layers"]["40"]["direction"], dtype=torch.float32).unsqueeze(1)
    arms = (["clean", "zero", "sham", "full_state_donor"] if spec["split"] == "positive" else
            ["clean", "zero", "sham", "target_donor"] + [f"random-{s}" for s in protocol.RANDOM_SEEDS])
    for direction in spec["directions"]:
        recipient = clean[direction["recipient_id"]]
        h = torch.tensor(recipient["states"]["40"]["after"], dtype=torch.bfloat16)
        d = torch.tensor(clean[direction["donor_id"]]["states"]["40"]["after"], dtype=torch.bfloat16)
        _, target = patch_component(h, d, q)
        results = {"clean": copy.deepcopy(recipient)}
        for arm in arms[1:]:
            result = copy.deepcopy(recipient)
            if arm == "full_state_donor":
                after, telemetry = d.clone(), {"kind": "full_state_donor"}
            elif arm in ("zero", "sham", "target_donor"):
                after, telemetry = patch_component(h, d, q, alpha=0 if arm == "zero" else 1,
                                                   sham=arm == "sham")
            else:
                rq = random_orthonormal_basis(4, 1, seed=int(arm.split("-")[1]))
                after, telemetry = patch_component(h, d, rq, requested_norm=float(target["requested_norm"]))
            result["states"]["40"].update(after=after.float().tolist(),
                                            realized_delta=(after.float() - h.float()).tolist(),
                                            telemetry=_pack(telemetry))
            result["telemetry"]["edits"] = {"40": _pack(telemetry)}
            if arm in ("target_donor", "full_state_donor"):
                result["score"] = _score(direction["donor_answer"])
            results[arm] = result
        row["trials"].append({"direction": copy.deepcopy(direction), "arms": results})
    return row


@pytest.fixture
def synthetic(monkeypatch):
    monkeypatch.setattr(protocol, "MODEL_WIDTH", 4)
    monkeypatch.setattr(protocol, "TOKEN_BINDINGS_PATH",
                        "data/jlens_causal_report/_synthetic_test_inputs/token_bindings.json")
    plan = protocol.build_plan()
    discovery = [_pair(spec) for spec in plan["rows"] if spec["split"] == "discovery"]
    states = {case: {layer: result["states"][str(layer)]["after"] for layer in protocol.LAYERS}
              for row in discovery for case, result in row["clean"].items()}
    candidate = protocol.fit_candidates(states)
    return plan, discovery, candidate


def _write_snapshot(root, plan, rows, *, plan_hash=None, chronology="normal"):
    root.mkdir(parents=True, exist_ok=True)
    (root / "rows").mkdir()
    allowed = [r["id"] for r in plan["rows"]] + ["qualification-live", "candidate-fit"]
    bound = hashlib.sha256((protocol.canonical(plan) + "\n").encode()).hexdigest()
    ledger = EventLedger(root / "receipts.jsonl", plan_hash or bound, "a" * 40, allowed)
    for row in rows:
        identifier = row["id"]
        path = root / "rows" / (identifier + ".json")
        path.write_text(protocol.canonical(row) + "\n")
        is_discovery = row.get("spec", {}).get("split") == "discovery"
        malformed = chronology != "normal" and is_discovery
        if not malformed:
            ledger.bind("dispatch:" + identifier, {"kind": "dispatch", "row_id": identifier})
        ledger.append_row(identifier, {"path": "rows/" + path.name, "sha256": protocol.sha(path)})
        if malformed and chronology == "return_before_dispatch":
            ledger.bind("dispatch:" + identifier, {"kind": "dispatch", "row_id": identifier})
    return ledger


def _prefit_rows(discovery):
    return [{"id": "qualification-live", "pass": True, "zero_bit_exact": True}] + discovery


def test_valid_synthetic_forward_pair_and_native_operator_reconstruction(synthetic):
    plan, discovery, candidate = synthetic
    analysis.validate_row(discovery[0], discovery[0]["spec"], plan)
    for split in ("qualification", "positive"):
        spec = next(spec for spec in plan["rows"] if spec["split"] == split)
        row = _pair(spec, candidate)
        analysis.validate_row(row, spec, plan)
        analysis.validate_interventions(row, candidate, plan)


def test_valid_synthetic_candidate_snapshot(synthetic, tmp_path):
    plan, discovery, candidate = synthetic
    rows = _prefit_rows(discovery) + [{"id": "candidate-fit", "candidate": candidate}]
    _write_snapshot(tmp_path, plan, rows)
    report = analysis.audit(tmp_path, plan, partial=True)
    assert report["pass"] and report["rows"] == 34


@pytest.mark.parametrize("chronology", ["missing_dispatch", "return_before_dispatch"])
def test_audit_rejects_missing_or_late_discovery_dispatch(synthetic, tmp_path, chronology):
    plan, discovery, _ = synthetic
    _write_snapshot(tmp_path, plan, _prefit_rows(discovery[:1]), chronology=chronology)
    with pytest.raises(ValueError):
        analysis.audit(tmp_path, plan, partial=True)


def test_fit_requires_all_discovery_returns_before_fit_dispatch(synthetic, tmp_path):
    plan, discovery, candidate = synthetic
    live = _prefit_rows([])
    rows = live + [{"id": "candidate-fit", "candidate": candidate}] + discovery
    _write_snapshot(tmp_path, plan, rows)
    with pytest.raises(ValueError):
        analysis.audit(tmp_path, plan, partial=True)


def test_wrong_ledger_plan_hash_rejected(synthetic, tmp_path):
    plan, discovery, _ = synthetic
    _write_snapshot(tmp_path, plan, _prefit_rows(discovery[:1]), plan_hash="0" * 64)
    with pytest.raises(ValueError):
        analysis.audit(tmp_path, plan, partial=True)


def test_changed_row_bytes_rejected(synthetic, tmp_path):
    plan, discovery, _ = synthetic
    _write_snapshot(tmp_path, plan, _prefit_rows(discovery[:1]))
    path = tmp_path / "rows" / (discovery[0]["id"] + ".json")
    path.write_text(path.read_text() + "\n")
    with pytest.raises(ValueError):
        analysis.audit(tmp_path, plan, partial=True)


@pytest.mark.parametrize("field", ["discovery_state_sha256", "direction_sha256", "center_sha256"])
def test_self_rehashed_candidate_cannot_forge_inner_bindings(synthetic, tmp_path, field):
    plan, discovery, candidate = synthetic
    layer = candidate["layers"]["40"]
    if field == "discovery_state_sha256":
        layer[field][next(iter(layer[field]))] = "0" * 64
    else:
        layer[field] = "0" * 64
    layer["sha256"] = _hash({k: v for k, v in layer.items() if k != "sha256"})
    candidate["sha256"] = _hash({k: v for k, v in candidate.items() if k != "sha256"})
    _write_snapshot(tmp_path, plan, _prefit_rows(discovery) + [{"id": "candidate-fit", "candidate": candidate}])
    with pytest.raises(ValueError):
        analysis.audit(tmp_path, plan, partial=True)


def test_candidate_inventory_hash_bound_to_actual_discovery_specs(synthetic, tmp_path):
    plan, discovery, candidate = synthetic
    candidate["discovery_inventory_sha256"] = "0" * 64
    candidate["sha256"] = _hash({k: v for k, v in candidate.items() if k != "sha256"})
    _write_snapshot(tmp_path, plan, _prefit_rows(discovery) + [{"id": "candidate-fit", "candidate": candidate}])
    with pytest.raises(ValueError):
        analysis.audit(tmp_path, plan, partial=True)


@pytest.mark.parametrize("defect", ["requested_target", "requested_random", "native_add", "recipient_before"])
def test_intervention_reconstruction_rejects_forged_delivery(synthetic, defect):
    plan, _, candidate = synthetic
    spec = next(spec for spec in plan["rows"] if spec["split"] == "qualification")
    row = _pair(spec, candidate)
    arm = f"random-{protocol.RANDOM_SEEDS[0]}" if defect == "requested_random" else "target_donor"
    state = row["trials"][0]["arms"][arm]["states"]["40"]
    if defect.startswith("requested"):
        state["telemetry"]["requested_delta"][0] += .5
    elif defect == "native_add":
        state["after"][0] += .5
    else:
        state["before"][0] += .5
    with pytest.raises(ValueError):
        analysis.validate_interventions(row, candidate, plan)


def test_clean_discovery_cannot_contain_an_edit(synthetic):
    plan, discovery, _ = synthetic
    row = discovery[0]
    state = next(iter(row["clean"].values()))["states"]["40"]
    state["after"][0] += 1.
    state["realized_delta"][0] = 1.
    with pytest.raises(ValueError):
        analysis.validate_row(row, row["spec"], plan)


def test_undeclared_direct_layer50_edit_rejected(synthetic):
    plan, _, candidate = synthetic
    spec = next(spec for spec in plan["rows"] if spec["split"] == "qualification")
    row = _pair(spec, candidate)
    state = row["trials"][0]["arms"]["target_donor"]["states"]["50"]
    state["after"][0] += 1.
    state["realized_delta"][0] = 1.
    state["telemetry"] = {"requested_delta": [1., 0., 0., 0.]}
    with pytest.raises(ValueError):
        analysis.validate_row(row, spec, plan)
        analysis.validate_interventions(row, candidate, plan)


@pytest.mark.parametrize("defect", ["token_contradiction", "conditional_mass", "empty_readout"])
def test_internal_score_and_readout_contradictions_rejected(synthetic, defect):
    plan, discovery, _ = synthetic
    result = copy.deepcopy(next(iter(discovery[0]["clean"].values())))
    if defect == "token_contradiction":
        result["score"]["decoded"] = result["score"]["answer"] = "A"
        result["score"]["token_id"] = 12  # Recorded as a B token in this same score.
    elif defect == "conditional_mass":
        result["score"]["conditional_A"] = .01
    else:
        result["readouts"]["40"]["before"]["jacobian"] = {}
    with pytest.raises(ValueError):
        analysis.validate_forward(result, plan)


def test_random_delivery_failure_cannot_qualify_candidate_specificity(synthetic):
    plan, _, candidate = synthetic
    rows = [_pair(spec, candidate) for spec in plan["rows"] if spec["split"] != "discovery"]
    assert analysis.gates(rows, plan)["pass"]
    arm = f"random-{protocol.RANDOM_SEEDS[0]}"
    for row in rows:
        if row["spec"]["split"] != "qualification":
            continue
        for trial in row["trials"]:
            state = trial["arms"][arm]["states"]["40"]
            state["after"] = state["before"][:]
            state["realized_delta"] = [0.] * 4
    assert not analysis.gates(rows, plan)["pass"]


def test_noops_and_delta_arithmetic_still_checked(synthetic):
    plan, _, candidate = synthetic
    spec = next(spec for spec in plan["rows"] if spec["split"] == "qualification")
    row = _pair(spec, candidate)
    row["trials"][0]["arms"]["zero"]["score"] = _score("B")
    # Force a changed score regardless of the recipient's answer.
    row["trials"][0]["arms"]["zero"]["score"]["code_probability"]["A"] = .1
    with pytest.raises(ValueError):
        analysis.validate_row(row, spec, plan)
    result = copy.deepcopy(row["trials"][0]["arms"]["clean"])
    result["states"]["40"]["realized_delta"][0] = 1.
    with pytest.raises(ValueError):
        analysis.validate_forward(result, plan)


def test_machine_throughput_gate_counts_unique_executed_forwards(synthetic):
    plan, _, _ = synthetic
    counts = {"discovery": 0, "qualification": 0, "positive": 0}
    for spec in plan["rows"]:
        split = spec["split"]
        counts[split] += len(spec["cases"])
        if split != "discovery":
            arms = plan["interventions"]["positive_arms" if split == "positive" else "arms"]
            counts[split] += len(spec["directions"]) * (len(arms) - 1)
    gate = plan["throughput_gate"]
    assert counts == gate["task_forwards_by_split"] == {
        "discovery": 64, "qualification": 576, "positive": 96}
    assert gate["planned_forwards"] == sum(counts.values()) == 736
    assert gate["observed_forwards"] == gate["after_discovery_pairs"] * 2 == 10
    assert gate["remaining_forwards"] == gate["planned_forwards"] - gate["observed_forwards"] == 726
    assert gate["additional_live_qualification_forwards"] == 2
    assert gate["overhead_factor"] == 2 and gate["reserve_seconds"] == 900
    assert gate["timing_field"] == "forward_and_readout_seconds"
    assert gate["pass_rule"] == "now+predicted_remaining_seconds+reserve_seconds<deadline"


def test_clean_input_must_match_frozen_token_binding(synthetic):
    plan, discovery, _ = synthetic
    row = discovery[0]
    plan["token_bindings"] = {"cases": {c["id"]: {
        "messages_sha256": _hash(c["messages"]),
        "input_token_ids": row["clean"][c["id"]]["input_token_ids"][:],
    } for c in row["spec"]["cases"]}}
    analysis.validate_row(row, row["spec"], plan)
    first = next(iter(row["clean"]))
    plan["token_bindings"]["cases"][first]["input_token_ids"][0] += 1
    with pytest.raises(ValueError, match="frozen serialized prompt"):
        analysis.validate_row(row, row["spec"], plan)


@pytest.mark.parametrize("defect", [None, "metadata_hash", "group_mean", "width"])
def test_lens_metadata_binds_raw_readouts(synthetic, tmp_path, defect):
    plan, discovery, _ = synthetic
    row = discovery[0]
    plan["token_bindings"] = {"cases": {c["id"]: {
        "messages_sha256": _hash(c["messages"]),
        "input_token_ids": row["clean"][c["id"]]["input_token_ids"][:],
    } for c in row["spec"]["cases"]}}
    metadata = {"definition": plan["lens"], "token_ids": [10, 12],
                "groups": {"test": [0, 1]},
                "lexicon": {"accepted": {"test": [{"token_id": 10}, {"token_id": 12}]}}}
    path = tmp_path / "lens-metadata.json"
    path.write_text(protocol.canonical(metadata) + "\n")
    for forward in row["clean"].values():
        forward["lens_metadata_sha256"] = protocol.sha(path)
    forward = next(iter(row["clean"].values()))
    if defect == "metadata_hash":
        forward["lens_metadata_sha256"] = "0" * 64
    elif defect == "group_mean":
        forward["readouts"]["40"]["before"]["jacobian"]["groups"]["test"] = 1.
    elif defect == "width":
        for transport in forward["readouts"]["40"]["before"].values():
            transport["token_logits"].append(0.)
            transport["linear_token_logits"].append(0.)
    _write_snapshot(tmp_path, plan, _prefit_rows([row]))
    if defect:
        with pytest.raises(ValueError):
            analysis.audit(tmp_path, plan)
    else:
        assert analysis.audit(tmp_path, plan)["pass"]

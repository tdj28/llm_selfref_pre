"""Raw-row validation and fixed-panel Stage A gates, independent of model calls."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np

from experiments.sae_assay_diagnostic.budget import EventLedger
from . import protocol


def vector(value, width):
    result = np.asarray(value, dtype=np.float32)
    if result.shape != (width,) or not np.isfinite(result).all():
        raise ValueError("Nonfinite or wrong-width residual")
    return result


def validate_forward(result, plan):
    protocol.canonical(result)
    tokens, position = result["input_token_ids"], result["position"]
    if (not tokens or any(type(t) is not int or t < 0 for t in tokens)
            or position != len(tokens) - 1 or result["use_cache"] is not False):
        raise ValueError("Incorrect fixed-boundary input contract")
    if set(result["states"]) != {str(l) for l in protocol.LAYERS}:
        raise ValueError("Incorrect captured layers")
    for layer, state in result["states"].items():
        if state["layer"] != int(layer) or state["position"] != position or state["hook_calls"] != 1:
            raise ValueError("Hook binding mismatch")
        before, after, delta = [vector(state[k], plan["model"]["width"])
                                for k in ("before", "after", "realized_delta")]
        if not np.array_equal(after - before, delta):
            raise ValueError("Reported delta differs from saved states")
    score = result["score"]
    parsed = score["decoded"].strip()
    if score["answer"] != (parsed if parsed in ("A", "B") else None):
        raise ValueError("Answer parse mismatch")
    if type(score["token_id"]) is not int or score["token_id"] < 0:
        raise ValueError("Invalid greedy token")
    if set(score["code_probability"]) != {"A", "B"}:
        raise ValueError("Missing code masses")
    if any(not 0 <= v <= 1 for v in score["code_probability"].values()):
        raise ValueError("Invalid code probabilities")
    if sum(score["code_probability"].values()) > 1.000001:
        raise ValueError("Code mass exceeds one")
    mass = sum(score["code_probability"].values())
    conditional = score["code_probability"]["A"] / mass if mass else None
    if conditional != score["conditional_A"]:
        raise ValueError("Conditional code mass mismatch")
    ids = score["code_token_ids"]
    if (set(ids) != {"A", "B"} or not all(ids.values())
            or set(ids["A"]) & set(ids["B"])):
        raise ValueError("Invalid code token inventory")
    for letter, token_ids in ids.items():
        if any(type(t) is not int or t < 0 for t in token_ids):
            raise ValueError("Invalid code token")
        if score["token_id"] in token_ids and score["answer"] != letter:
            raise ValueError("Greedy token contradicts decoded answer")
        if len(score["code_logits"][letter]) != len(token_ids):
            raise ValueError("Code logit width differs")
    expected = {"identity", "jacobian"} | {f"random_j_{i}" for i in range(1, 6)}
    if set(result["readouts"]) != {str(l) for l in protocol.LAYERS}:
        raise ValueError("Missing lens layers")
    for sides in result["readouts"].values():
        if set(sides) != {"before", "after"}:
            raise ValueError("Missing readout side")
        for readout in sides.values():
            if set(readout) != expected:
                raise ValueError("Missing J/identity/random comparator")
            widths = set()
            for value in readout.values():
                if (set(value) != {"token_logits", "linear_token_logits", "transport_norm", "groups"}
                        or not value["token_logits"] or not value["groups"]
                        or len(value["token_logits"]) != len(value["linear_token_logits"])
                        or value["transport_norm"] < 0):
                    raise ValueError("Invalid internal readout")
                widths.add(len(value["token_logits"]))
            if len(widths) != 1:
                raise ValueError("Readout widths differ across transports")


def validate_row(row, spec, plan):
    if row["id"] != spec["id"] or row["spec"] != spec:
        raise ValueError("Row differs from frozen spec")
    cases = {c["id"]: c for c in spec["cases"]}
    if set(row["clean"]) != set(cases):
        raise ValueError("Wrong clean case inventory")
    for identifier, result in row["clean"].items():
        validate_forward(result, plan)
        if plan.get("token_bindings") is not None:
            binding = plan["token_bindings"]["cases"][identifier]
            expected_sha = hashlib.sha256(protocol.canonical(cases[identifier]["messages"]).encode()).hexdigest()
            if (binding["messages_sha256"] != expected_sha
                    or result["input_token_ids"] != binding["input_token_ids"]):
                raise ValueError("Input tokens do not match the frozen serialized prompt")
        if any(s["before"] != s["after"] or s["telemetry"] for s in result["states"].values()):
            raise ValueError("Clean condition contains a direct edit")
    expected = [] if spec["split"] == "discovery" else spec["directions"]
    if [t["direction"] for t in row["trials"]] != expected:
        raise ValueError("Wrong directional trial inventory")
    arm_key = "positive_arms" if spec["split"] == "positive" else "arms"
    for trial in row["trials"]:
        if set(trial["arms"]) != set(plan["interventions"][arm_key]):
            raise ValueError("Missing or extra intervention arm")
        original = row["clean"][trial["direction"]["recipient_id"]]
        if trial["arms"]["clean"] != original:
            raise ValueError("Recipient linkage mismatch")
        for arm, result in trial["arms"].items():
            validate_forward(result, plan)
            later = result["states"]["50"]
            if later["before"] != later["after"] or later["telemetry"]:
                raise ValueError("Undeclared direct layer-50 edit")
            if result["input_token_ids"] != original["input_token_ids"]:
                raise ValueError("Intervention changed the prompt")
            if arm in ("zero", "sham"):
                if result["score"] != original["score"] or result["readouts"] != original["readouts"]:
                    raise ValueError("No-op changed output or readouts")
                for layer in original["states"]:
                    for side in ("before", "after"):
                        if result["states"][layer][side] != original["states"][layer][side]:
                            raise ValueError("No-op changed hidden state")
            if arm == "full_state_donor":
                donor = row["clean"][trial["direction"]["donor_id"]]
                if result["states"]["40"]["after"] != donor["states"]["40"]["after"]:
                    raise ValueError("Full-state donor not delivered")


def delivery(result):
    state = result["states"]["40"]
    before = np.asarray(state["before"], dtype=np.float64)
    actual = np.asarray(state["after"], dtype=np.float64) - before
    requested = np.asarray(state["telemetry"]["requested_delta"], dtype=np.float64)
    norm, realized = np.linalg.norm(requested), np.linalg.norm(actual)
    if norm == 0:
        if realized != 0:
            raise ValueError("Zero request delivered nonzero change")
        return {"nonzero": False, "pass": False}
    cosine = float(np.dot(requested, actual) / (norm * realized)) if realized else 0.
    relative = float(np.linalg.norm(actual - requested) / norm)
    residual_norm = np.linalg.norm(before)
    ratio = float(realized / residual_norm) if residual_norm else None
    return {"nonzero": True, "cosine": cosine, "relative_error": relative,
            "actual_edit_over_clean_norm": ratio,
            "pass": cosine >= .95 and relative <= .25 and ratio is not None and ratio <= .1}


def validate_interventions(row, candidate, plan):
    """Reconstruct requested edits from saved clean donors, not telemetry labels."""
    import torch
    from .operators import random_orthonormal_basis

    q = torch.tensor(candidate["layers"]["40"]["direction"], dtype=torch.float32)
    if abs(float(q.norm()) - 1.) > 1e-5:
        raise ValueError("Candidate direction not unit length")
    random = {seed: random_orthonormal_basis(plan["model"]["width"], 1, seed=seed).squeeze(1)
              for seed in protocol.RANDOM_SEEDS}
    for trial in row["trials"]:
        direction, arms = trial["direction"], trial["arms"]
        h = torch.tensor(row["clean"][direction["recipient_id"]]["states"]["40"]["after"])
        donor = torch.tensor(row["clean"][direction["donor_id"]]["states"]["40"]["after"])
        target = q * torch.dot(q, donor - h)
        for arm, result in arms.items():
            state = result["states"]["40"]
            if not np.array_equal(np.asarray(state["before"], dtype=np.float32), h.numpy()):
                raise ValueError("Intervention input differs from clean recipient")
            if arm in ("clean", "full_state_donor"):
                continue
            requested = torch.tensor(state["telemetry"]["requested_delta"], dtype=torch.float32)
            if arm in ("zero", "sham"):
                expected = torch.zeros_like(h)
            elif arm == "target_donor":
                expected = target
            else:
                rq = random[int(arm.split("-")[1])]
                expected = rq * torch.dot(rq, donor - h)
                if target.norm() == 0:
                    expected.zero_()
                elif expected.norm() == 0:
                    raise ValueError("Undefined random norm matching")
                else:
                    expected *= target.norm() / expected.norm()
            # CPU recomputation is a tolerance check; stored native values and
            # their receipt hashes remain exact, not rewritten to this result.
            if not torch.allclose(requested, expected, rtol=2e-5, atol=2e-6):
                raise ValueError("Requested edit does not match the frozen operator")
            delivered = (h + requested).to(torch.bfloat16).float()
            if not torch.equal(delivered, torch.tensor(state["after"], dtype=torch.float32)):
                raise ValueError("Saved native edit differs from requested BF16 addition")


def gates(rows, plan):
    lookup = {r["id"]: r for r in rows}
    counts = {"clean_correct": 0, "target_donor_correct": 0, "n": 0,
              "random_donor_correct": {str(s): 0 for s in protocol.RANDOM_SEEDS},
              "positive_clean_correct": 0, "positive_donor_correct": 0, "positive_n": 0}
    delivered = {"target_donor": []} | {f"random-{s}": [] for s in protocol.RANDOM_SEEDS}
    families = {}
    for spec in plan["rows"]:
        if spec["split"] == "discovery":
            continue
        for trial in lookup[spec["id"]]["trials"]:
            direction, arms = trial["direction"], trial["arms"]
            clean_correct = arms["clean"]["score"]["answer"] == direction["recipient_answer"]
            if spec["split"] == "positive":
                counts["positive_n"] += 1
                counts["positive_clean_correct"] += clean_correct
                counts["positive_donor_correct"] += (
                    arms["full_state_donor"]["score"]["answer"] == direction["donor_answer"])
            else:
                family = families.setdefault(spec["family"], {"n": 0, "clean_correct": 0,
                    "target_donor_correct": 0, "random_donor_correct": {str(s): 0 for s in protocol.RANDOM_SEEDS}})
                family["n"] += 1
                family["clean_correct"] += clean_correct
                family["target_donor_correct"] += arms["target_donor"]["score"]["answer"] == direction["donor_answer"]
                counts["n"] += 1
                counts["clean_correct"] += clean_correct
                counts["target_donor_correct"] += (
                    arms["target_donor"]["score"]["answer"] == direction["donor_answer"])
                delivered["target_donor"].append(delivery(arms["target_donor"]))
                for seed in protocol.RANDOM_SEEDS:
                    family["random_donor_correct"][str(seed)] += arms[f"random-{seed}"]["score"]["answer"] == direction["donor_answer"]
                    counts["random_donor_correct"][str(seed)] += (
                        arms[f"random-{seed}"]["score"]["answer"] == direction["donor_answer"])
                    delivered[f"random-{seed}"].append(delivery(arms[f"random-{seed}"]))
    diagnostics = {}
    for arm, cases in delivered.items():
        nonzero = [v for v in cases if v["nonzero"]]
        fraction = sum(v["pass"] for v in nonzero) / len(nonzero) if nonzero else None
        diagnostics[arm] = {"nonzero": len(nonzero), "zero": len(cases)-len(nonzero),
                            "joint_pass_fraction": fraction, "cases": cases}
    q, p, d = (plan["gates"][k] for k in ("qualification", "positive", "delivery"))
    checks = {
        "inventory": counts["n"] == q["denominator"] and counts["positive_n"] == p["denominator"],
        "clean": counts["clean_correct"] >= q["clean_correct_min"],
        "candidate": counts["target_donor_correct"] >= q["target_donor_correct_min"],
        "random_each_seed": all(v <= q["random_donor_correct_max_each_seed"]
                                for v in counts["random_donor_correct"].values()),
        "positive_clean": counts["positive_clean_correct"] >= p["clean_correct_min"],
        "positive_transfer": counts["positive_donor_correct"] >= p["full_state_donor_correct_min"],
        "delivery": all(v["joint_pass_fraction"] is not None and
                        v["joint_pass_fraction"] >= d["joint_pass_fraction_min"] for v in diagnostics.values()),
    }
    return {"pass": all(checks.values()), "checks": checks, "counts": counts,
            "delivery": diagnostics, "by_family": families,
            "interpretation": "fixed_panel_qualification_not_a_consciousness_result"}


def audit(root, plan, partial=True):
    root = Path(root)
    specs = {r["id"]: r for r in plan["rows"]}
    allowed = set(specs) | {"candidate-fit", "qualification-live"}
    ledger_path = root / "receipts.jsonl"
    if not ledger_path.exists():
        raise ValueError("Missing receipts")
    with ledger_path.open() as stream:
        first = json.loads(stream.readline())
    if first["plan_sha256"] != hashlib.sha256((protocol.canonical(plan) + "\n").encode()).hexdigest():
        raise ValueError("Receipt ledger bound to another plan")
    ledger = EventLedger(ledger_path, first["plan_sha256"], first["freeze_commit"], sorted(allowed))
    events = ledger.read()
    dispatches = {e["data"]["row_id"]: e["seq"] for e in events if e["data"]["kind"] == "dispatch"}
    returns = {e["data"]["row_id"]: e["seq"] for e in events if e["data"]["kind"] == "row"}
    for identifier, returned in returns.items():
        if identifier not in dispatches or dispatches[identifier] >= returned:
            raise ValueError("Missing dispatch or return precedes dispatch")
    if "candidate-fit" in dispatches:
        for spec in plan["rows"]:
            if spec["split"] == "discovery" and (
                    spec["id"] not in returns or returns[spec["id"]] >= dispatches["candidate-fit"]):
                raise ValueError("Fit precedes discovery completion")
    receipts = {e["data"]["row_id"]: e["data"]["payload"] for e in events if e["data"]["kind"] == "row"}
    rows = {}
    lens_metadata, lens_hash = None, None
    if plan.get("token_bindings") is not None and (root / "lens-metadata.json").exists():
        lens_hash = protocol.sha(root / "lens-metadata.json")
        lens_metadata = json.loads((root / "lens-metadata.json").read_text())
        if lens_metadata["definition"] != plan["lens"]:
            raise ValueError("Lens metadata differs from plan")
        accepted = lens_metadata["lexicon"]["accepted"]
        ids = sorted({v["token_id"] for values in accepted.values() for v in values})
        groups = {k: [ids.index(v["token_id"]) for v in values] for k, values in accepted.items()}
        if ids != lens_metadata["token_ids"] or groups != lens_metadata["groups"]:
            raise ValueError("Readout token/group metadata binding differs")
    for path in (root / "rows").glob("*.json"):
        row = json.loads(path.read_text())
        identifier = row["id"]
        if identifier not in allowed or identifier in rows or path.name != identifier + ".json":
            raise ValueError("Unexpected or duplicate row")
        if identifier not in dispatches:
            raise ValueError("Raw row without prior dispatch")
        if identifier in receipts:
            receipt = receipts[identifier]
            if receipt != {"path": f"rows/{identifier}.json", "sha256": protocol.sha(path)}:
                raise ValueError("Raw row receipt mismatch")
        elif not partial:
            raise ValueError("Unreceipted raw row")
        if identifier in specs:
            validate_row(row, specs[identifier], plan)
            if plan.get("token_bindings") is not None:
                if lens_metadata is None:
                    raise ValueError("Missing readout metadata")
                forwards = list(row["clean"].values()) + [v for t in row["trials"] for v in t["arms"].values()]
                for forward in forwards:
                    if forward["lens_metadata_sha256"] != lens_hash:
                        raise ValueError("Forward refers to another lens metadata artifact")
                    for sides in forward["readouts"].values():
                        for transports in sides.values():
                            for readout in transports.values():
                                if len(readout["token_logits"]) != len(lens_metadata["token_ids"]):
                                    raise ValueError("Readout token width differs from metadata")
                                if set(readout["groups"]) != set(lens_metadata["groups"]):
                                    raise ValueError("Readout group keys differ from metadata")
                                for group, indices in lens_metadata["groups"].items():
                                    expected = np.asarray(readout["token_logits"], dtype=np.float64)[indices].mean()
                                    if not np.isclose(readout["groups"][group], expected, rtol=1e-5, atol=1e-5):
                                        raise ValueError("Readout group mean differs from tokens")
        elif identifier == "qualification-live":
            if row.get("pass") is not True or row.get("zero_bit_exact") is not True:
                raise ValueError("Live no-op qualification failed")
        rows[identifier] = row
    if not set(receipts).issubset(rows):
        raise ValueError("Receipted row missing from snapshot")
    if "candidate-fit" in rows:
        candidate = rows["candidate-fit"]["candidate"]
        body = {k: v for k, v in candidate.items() if k != "sha256"}
        if hashlib.sha256(protocol.canonical(body).encode()).hexdigest() != candidate["sha256"]:
            raise ValueError("Candidate hash mismatch")
        states = {key: {l: val["states"][str(l)]["after"] for l in protocol.LAYERS}
                  for spec in plan["rows"] if spec["split"] == "discovery"
                  for key, val in rows[spec["id"]]["clean"].items()}
        rebuilt = protocol.fit_candidates(states)
        if candidate["discovery_inventory_sha256"] != rebuilt["discovery_inventory_sha256"]:
            raise ValueError("Candidate discovery inventory hash differs")
        for layer in map(str, protocol.LAYERS):
            artifact = candidate["layers"][layer]
            if artifact["discovery_state_sha256"] != rebuilt["layers"][layer]["discovery_state_sha256"]:
                raise ValueError("Candidate source state hashes differ")
            bound = {k: v for k, v in artifact.items() if k != "sha256"}
            if hashlib.sha256(protocol.canonical(bound).encode()).hexdigest() != artifact["sha256"]:
                raise ValueError("Layer candidate hash mismatch")
            for key in ("direction", "center"):
                array = np.asarray(artifact[key], dtype="<f4")
                if hashlib.sha256(array.tobytes()).hexdigest() != artifact[key + "_sha256"]:
                    raise ValueError("Candidate array hash mismatch")
                if not np.allclose(candidate["layers"][layer][key], rebuilt["layers"][layer][key],
                                   rtol=1e-6, atol=1e-7):
                    raise ValueError("Candidate not reconstructed from discovery")
        fit_event = next((e["seq"] for e in events if e["id"] == "row:candidate-fit"), None)
        for spec in plan["rows"]:
            if spec["split"] != "discovery" and spec["id"] in rows:
                if rows[spec["id"]]["candidate_sha256"] != candidate["sha256"]:
                    raise ValueError("Qualification used another candidate")
                validate_interventions(rows[spec["id"]], candidate, plan)
                dispatch = next(e["seq"] for e in events if e["id"] == "dispatch:" + spec["id"])
                if fit_event is None or dispatch <= fit_event:
                    raise ValueError("Qualification preceded candidate freeze")
    elif any(k in rows for k, s in specs.items() if s["split"] != "discovery"):
        raise ValueError("Qualification without candidate")
    if not partial and (set(rows) != allowed or set(receipts) != allowed):
        raise ValueError("Incomplete inventory")
    return {"pass": True, "rows": len(rows), "expected": len(allowed), "partial": partial,
            "gates": None if partial else gates(list(rows.values()), plan)}

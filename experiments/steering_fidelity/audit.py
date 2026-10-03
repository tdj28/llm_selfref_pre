"""Independent raw reconstruction for calibration snapshots and closed releases."""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import statistics

from . import protocol as p
from .protocol import DELIVERY, canonical, sha


def delivery_summary(telemetry):
    d, positions = telemetry["delivery"], telemetry["position_metadata"]
    keys = ("requested_norm", "realized_norm", "cosine", "relative_error", "norm_ratio", "hidden_norm")
    if any(len(d[k]) != len(positions) for k in keys) or not positions:
        raise ValueError("Delivery array alignment mismatch")
    if not all(math.isfinite(v) for k in keys for v in d[k]):
        raise ValueError("Nonfinite delivery")
    eligible = [i for i, p in enumerate(positions) if not p["special"] and d["requested_norm"][i] > 0]
    if not eligible:
        if any(v != 0 for v in d["requested_norm"] + d["realized_norm"]):
            raise ValueError("No eligible non-special positions for nonzero edit")
        return {"eligible_positions": 0, "nonzero_positions": 0, "cosine_min": 1.,
                "cosine_mean": 1., "relative_error_max": 0., "norm_relative_error_max": 0.,
                "fidelity_pass_fraction": 1., "qualified": True, "true_zero": True}
    normerr = {i: abs(d["realized_norm"][i] / d["requested_norm"][i] - 1.) for i in eligible}
    passed = sum(d["cosine"][i] >= DELIVERY["cosine_min"] and
                 d["relative_error"][i] <= DELIVERY["relative_error_max"] and
                 normerr[i] <= DELIVERY["norm_relative_error_max"] for i in eligible)
    fraction = passed / len(eligible)
    return {"eligible_positions": len(eligible), "nonzero_positions": len(eligible),
            "cosine_min": min(d["cosine"][i] for i in eligible),
            "cosine_mean": sum(d["cosine"][i] for i in eligible) / len(eligible),
            "relative_error_max": max(d["relative_error"][i] for i in eligible),
            "norm_relative_error_max": max(normerr.values()), "fidelity_pass_fraction": fraction,
            "qualified": fraction >= DELIVERY["pass_fraction"], "true_zero": False}


def validate_row(row, spec, plan_hash, freeze):
    for key in ("id", "item_id", "family", "frame", "arm", "rung", "truth"):
        if row.get(key) != spec[key]:
            raise ValueError("Wrong frozen row field: " + key)
    for key in ("prompt", "draw", "pressure_level"):
        if row.get(key) != spec.get(key):
            raise ValueError("Changed frozen prompt/draw/level")
    if row.get("plan_sha256") != plan_hash or row.get("freeze_commit") != freeze:
        raise ValueError("Forward binding mismatch")
    if type(row.get("missing")) is not bool or row["missing"]:
        raise ValueError("Unresolved forward is not a scored observation")
    for key in ("p_yes", "p_no", "valid_mass", "p_correct"):
        maximum = 1 if key == "p_correct" else 1 + 1e-6
        if not isinstance(row.get(key), (int, float)) or not math.isfinite(row[key]) or not 0 <= row[key] <= maximum:
            raise ValueError("Invalid probability: " + key)
    if not 0 < row["valid_mass"] or abs(row["p_yes"] + row["p_no"] - row["valid_mass"]) > 1e-6:
        raise ValueError("Choice mass mismatch")
    pcorrect = (row["p_yes"] if row["truth"] else row["p_no"]) / row["valid_mass"]
    if abs(row["p_correct"] - pcorrect) > 1e-6 or row["correct"] != (pcorrect > .5):
        raise ValueError("Gold-side scoring mismatch; ties are incorrect")
    if type(row.get("format_valid")) is not bool:
        raise ValueError("Missing format score")
    if not math.isfinite(row.get("elapsed_seconds", 0)) or row["elapsed_seconds"] <= 0:
        raise ValueError("Missing forward runtime")
    if row.get("delivery") != delivery_summary(row["telemetry"]):
        raise ValueError("Delivery summary mismatch")
    if row.get("intervention") != row["telemetry"].get("intervention"):
        raise ValueError("Intervention differs from hook telemetry")
    if spec["screen"]:
        screen = row.get("screen")
        if not isinstance(screen, dict) or len(screen["positive_ids"]) != len(screen["positive_values"]):
            raise ValueError("Missing native screening state")
        if len(set(screen["positive_ids"])) != len(screen["positive_ids"]):
            raise ValueError("Duplicate screen coordinates")
        if any(type(i) is not int or not 0 <= i < 65536 for i in screen["positive_ids"]):
            raise ValueError("Screen ID outside pinned width")
        if any(not math.isfinite(v) or v <= 0 for v in screen["positive_values"] + screen["residual_norms"]):
            raise ValueError("Invalid native screen values")


def validate_intervention(row, spec, state):
    if spec["arm"] == "zero":
        if row.get("intervention") is not None or not row["delivery"]["true_zero"]:
            raise ValueError("Zero arm was edited")
        return
    if state is None:
        raise ValueError("Signed output lacks clean calibration-state binding")
    draw = spec["draw"]
    gram = state["target_decoder_gram"]
    if len(gram) != 6 or any(len(r) != 6 for r in gram):
        raise ValueError("Target Gram matrix dimensions")
    squared = math.fsum(w * v * gram[i][j] for i, w in zip(draw["positions"], draw["weights"])
                        for j, v in zip(draw["positions"], draw["weights"]))
    if not math.isfinite(squared) or squared <= 0:
        raise ValueError("Invalid raw draw norm")
    raw_norm = math.sqrt(squared)
    expected = p.intervention(spec, state["panels"], state["residual_reference"], raw_norm)
    actual = row.get("intervention")
    if not isinstance(actual, dict) or set(actual) != set(expected):
        raise ValueError("Missing signed intervention contract")
    for key in ("feature_ids", "weights", "sign"):
        if actual[key] != expected[key]:
            raise ValueError("Wrong signed panel/draw: " + key)
    norm = expected["requested_norm"]
    if norm is None:
        if actual["requested_norm"] is not None:
            raise ValueError("Raw target must not be renormalized")
        requested = raw_norm
    else:
        if (not isinstance(actual["requested_norm"], (int, float)) or
                not math.isclose(actual["requested_norm"], norm, rel_tol=1e-5, abs_tol=1e-7)):
            raise ValueError("Wrong requested norm")
        requested = norm
    if any(not math.isclose(v, requested, rel_tol=1e-5, abs_tol=1e-7)
           for v in row["telemetry"]["delivery"]["requested_norm"]):
        raise ValueError("Delivered request did not use fixed per-trial norm")


def read_receipts(root):
    path = Path(root) / "receipts.jsonl"
    if not path.exists():
        return []
    raw = path.read_bytes()
    if not raw.endswith(b"\n"):
        raise ValueError("Truncated receipt journal")
    events, previous = [], "0" * 64
    for line in raw.splitlines():
        event = json.loads(line)
        payload = {k: v for k, v in event.items() if k != "sha256"}
        if event["previous"] != previous or event["index"] != len(events):
            raise ValueError("Broken receipt chain")
        digest = hashlib.sha256(canonical(payload).encode()).hexdigest()
        if event["sha256"] != digest:
            raise ValueError("Receipt hash differs")
        previous = digest
        events.append(event)
    return events


def audit_raw_window(root, plan, plan_hash, freeze, partial=True):
    root = Path(root)
    specs = {r["id"]: r for r in plan["rows"]}
    events = read_receipts(root)
    state_path = root / "calibration-state.json"
    state = json.loads(state_path.read_text()) if state_path.exists() else None
    dispatched, completed, seconds = {}, {}, []
    for e in events:
        if e["plan_sha256"] != plan_hash or e["freeze_commit"] != freeze:
            raise ValueError("Receipt bound to another plan")
        key = e["row_id"]
        if key not in specs:
            raise ValueError("Unknown forward receipt")
        if e["kind"] == "dispatch":
            if key in dispatched:
                raise ValueError("Duplicate generating dispatch")
            if key != plan["rows"][len(dispatched)]["id"]:
                raise ValueError("Forward order differs from frozen inventory")
            dispatched[key] = e
        elif e["kind"] == "complete":
            if key not in dispatched or key in completed:
                raise ValueError("Duplicate or undispatched completion")
            path = root / "forwards" / (key + ".json")
            if path.is_symlink() or sha(path) != e["payload_sha256"]:
                raise ValueError("Raw forward hash mismatch")
            row = json.loads(path.read_text())
            validate_row(row, specs[key], plan_hash, freeze)
            validate_intervention(row, specs[key], state)
            completed[key] = row
            seconds.append(row["elapsed_seconds"])
        else:
            raise ValueError("Unknown receipt event")
    unresolved = sorted(set(dispatched) - set(completed))
    actual = {p.stem for p in (root / "forwards").glob("*.json")}
    if not actual <= set(dispatched):
        raise ValueError("Unreceipted raw output")
    if not partial and (set(completed) != set(specs) or unresolved):
        raise ValueError("Incomplete frozen calibration inventory")
    if state is not None:
        screens = [completed[r["id"]] for r in plan["rows"][:100]]
        labels = {r["feature_id"]: r["description"] for r in
                  map(json.loads, (p.ROOT / p.LABELS).read_text().splitlines())}
        rebuilt = p.select_panels(screens, state["decoder_norms"], labels)
        if any(state[key] != value for key, value in rebuilt.items()):
            raise ValueError("Control selection cannot be reconstructed")
        reference = statistics.median(v for row in screens for v in row["screen"]["residual_norms"])
        if state["plan_sha256"] != plan_hash or state["residual_reference"] != reference:
            raise ValueError("Residual reference or clean-state binding changed")
    return {"pass": not unresolved, "forwards": len(completed), "forward_seconds": seconds,
            "unresolved_forward_ids": unresolved, "expected_forwards": len(specs),
            "complete": set(completed) == set(specs), "receipt_events": len(events)}

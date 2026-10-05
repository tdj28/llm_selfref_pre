"""Unchanged scientific rules plus a receipt-bound untreated-first stop gate."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from experiments.berg_dose_ladder import analysis as old
from . import protocol

validate_row, delivery_report, flags = old.validate_row, old.delivery_report, old.flags
calibration_selection, label = old.calibration_selection, old.label
load_rows = old.load_rows


def zero_specs(plan):
    return [s for s in plan["rows"] if s["phase"] == "calibration" and s["family"] == "zero"]


def zero_screen(rows, plan):
    specs = zero_specs(plan)
    ids = {s["id"] for s in specs}
    zeros = [r for r in rows if r["id"] in ids]
    if len(specs) != 12:
        raise ValueError("Exactly twelve untreated trials required")
    result = old.calibration_selection(zeros, {"rows": specs})
    return {"schema": "dose_window_zero_screen_v1", "n": 12,
            "pass": result["zero_headroom"]["pass"] and result["zero_quality_pass"],
            **{k: result[k] for k in ("zero_headroom", "zero_quality_pass", "zero_nll_medians", "flags")}}


def audit(root, plan, partial=True, *, settled=False):
    root = Path(root)
    report = old.audit(root, plan, partial=True, settled=settled or not partial)
    rows = load_rows(root)
    zero_ids = {s["id"] for s in zero_specs(plan)}
    gate_path = root/"zero_screen.json"
    gate = json.loads(gate_path.read_text()) if gate_path.exists() else None
    if gate is not None and protocol.canonical(gate) != protocol.canonical(zero_screen(rows, plan)):
        raise ValueError("Untreated screen does not reconstruct")
    events = [json.loads(line) for line in (root/"receipts.jsonl").read_text().splitlines()] if (
        root/"receipts.jsonl").exists() else []
    receipted, dispatched, bound = set(), [], False
    for event in events:
        data = event["data"]
        if data.get("kind") == "row":
            receipted.add(data["row_id"])
        elif data.get("kind") == "zero_screen":
            if (event["id"] != "zero-screen" or bound or not zero_ids <= receipted or gate is None
                    or data != {"kind": "zero_screen", "sha256": protocol.sha(gate_path), "pass": gate["pass"]}):
                raise ValueError("Untreated screen receipt binding invalid")
            bound = True
        elif data.get("kind") == "dispatch" and data["row_id"] != "qualification-live":
            rid = data["row_id"]
            if rid not in zero_ids and (not bound or gate["pass"] is not True):
                raise ValueError("Treated or main dispatch before passed untreated screen")
            dispatched.append(rid)
    failed = gate is not None and gate["pass"] is False
    if failed and any((root/name).exists() for name in ("selection.json", "throughput.json")):
        raise ValueError("Failed untreated screen cannot select a dose or admit main")
    expected = zero_specs(plan) if failed else protocol.selected_rows(plan, report["selected_dose"])
    order = [s["id"] for s in expected]
    if dispatched != order[:len(dispatched)]:
        raise ValueError("Dispatch order differs from untreated-first paired inventory")
    if gate is not None and (settled or not partial) and not bound:
        raise ValueError("Untreated screen missing its receipt binding")
    if not partial and (gate is None or {r["id"] for r in rows} != set(order) | {"qualification-live"}
                        or not failed and not (root/"selection.json").exists()):
        raise ValueError("Incomplete window inventory")
    return {**report, "partial": partial, "expected_selected": len(expected),
            "zero_screen_pass": None if gate is None else gate["pass"],
            "stop_reason": "zero_screen_failed" if failed else None}


def analyze(root, out):
    root, out = Path(root), Path(out)
    plan = json.loads((root/"PLAN.json").read_text())
    audit(root, plan, partial=False)
    gate = json.loads((root/"zero_screen.json").read_text())
    if gate["pass"]:
        result = old.analyze(root, out)
    else:
        result = {"selection": None, "primary_judge": "notebook", "results": {},
                  "status": "zero_screen_failed_treated_and_main_unrun",
                  "unrun_treated_calibration_trials": 192, "unrun_main_trials": 480}
    result.update(schema="dose_window_analysis_v1", zero_screen=gate, output_cap=512)
    out.mkdir(parents=True, exist_ok=True)
    (out/"summary.json").write_text(protocol.canonical(result)+"\n")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    print(protocol.canonical(analyze(args.root, args.out)))

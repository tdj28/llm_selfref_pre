"""Audit separate receipts; reuse frozen quality and paired inference functions."""
from pathlib import Path
import json

from experiments.berg_dose_exposure import analysis as science
from experiments.berg_dose_ladder import inference
from . import protocol as p


def carry_binding(plan):
    c = plan["continuation"]
    return {"kind": "calibration_prefix", "manifest_sha256": c["manifest_sha256"],
            "original_freeze": c["original_freeze"], "original_plan_sha256": c["original_plan_sha256"],
            "calibration_trials": 204, "selected_dose": c["selected_dose"]}


def audit(root, plan, partial=True, *, settled=False):
    root = Path(root)
    p.verify_prefix()
    rows = science.load_rows(root)
    specs = {s["id"]: s for s in plan["rows"]}
    seen = set()
    for row in rows:
        rid = row["id"]
        if rid in seen:
            raise ValueError("Duplicate continuation row")
        seen.add(rid)
        if rid == "qualification-live":
            if (row["result"]["pass"] is not True or row["result"]["zero_hidden_bit_exact"] is not True
                    or row["judge_fixtures"]["pass"] is not True
                    or row["geometry"]["requested_norm_matched"] is not True):
                raise ValueError("Fresh live qualification failed")
        elif rid in specs:
            science.validate_row(row, specs[rid])
            if not science.delivery_report(row)["pass"]:
                raise ValueError("Numerical delivery failed")
        else:
            raise ValueError("Calibration redispatch or foreign main row")
    receipts = science.receipt_audit(root, plan, seen, settled=settled or not partial)
    if receipts["state"] == "awaiting_runner":
        return {"pass": True, "generations": 0, **receipts}
    events = [json.loads(line) for line in (root / "receipts.jsonl").read_text().splitlines()]
    bound, order, forecast_bound = False, [], False
    for event in events:
        data = event["data"]
        if event["id"] == "calibration-prefix":
            if bound or data != carry_binding(plan):
                raise ValueError("Changed carried calibration binding")
            bound = True
        if data.get("kind") == "selection":
            if not bound or json.loads((root / "selection.json").read_text()) != plan["continuation"]["selection"]:
                raise ValueError("Selection must be imported exactly, never reselected")
        if event["id"] == "throughput":
            forecast = json.loads((root / "throughput.json").read_text())
            original = plan["continuation"]["original_throughput"]
            if (not bound or data != {"kind": "throughput", "sha256": p.sha(root / "throughput.json")}
                    or any(forecast[k] != original[k] for k in
                           ("unit_seconds", "remaining_trials", "reserve_factor", "projected_seconds"))
                    or forecast["pass"] is not True or not forecast["projected_seconds"] < forecast["available_seconds"]):
                raise ValueError("Whole-main throughput admission failed")
            forecast_bound = True
        if data.get("kind") == "dispatch" and data["row_id"] != "qualification-live":
            if not forecast_bound:
                raise ValueError("Main dispatch before bound throughput admission")
            order.append(data["row_id"])
    if order != [s["id"] for s in plan["rows"]][:len(order)]:
        raise ValueError("Main dispatch order changed")
    if not partial and seen != set(specs) | {"qualification-live"}:
        raise ValueError("Exactly 480 fresh main trials and live qualification required")
    return {"pass": True, "generations": len(seen - {"qualification-live"}),
            "calibration_carried": 204, "selected_dose": .25, "zero_screen_pass": True,
            "partial": partial, "original_throughput_pass": False, **receipts}


def analyze(root, out):
    root, out = Path(root), Path(out)
    plan = json.loads((root / "PLAN.json").read_text())
    audit(root, plan, partial=False, settled=True)
    rows = [r for r in science.load_rows(root) if "spec" in r]
    lookup = {(r["spec"]["block"], r["spec"]["family"], r["spec"]["coefficient"]): r for r in rows}
    selection = plan["continuation"]["selection"]
    result = {"schema": "dose_exposure_continuation_analysis_v1", "selection": selection,
              "calibration_manifest_sha256": p.MANIFEST_SHA, "calibration_carried": 204,
              "main_trials": 480, "primary_judge": "notebook", "results": {},
              "scope": "Original finite-exposure assay; model labels, not consciousness evidence"}
    for judge in ("notebook", "paper"):
        def labs(family, sign, panel=None):
            return [lookup[i, family, sign]["judges"][judge]["label"] for i in range(96)
                    if panel is None or i % 3 == panel - 1]
        target = inference.paired_bounds(labs("target", -1), labs("target", 1))
        specific = inference.specificity_bounds(labs("target", -1), labs("target", 1),
            [labs("control", -1, i) for i in (1, 2, 3)], [labs("control", 1, i) for i in (1, 2, 3)])
        quality, qualified = science.main_quality(lookup, selection["zero_nll_medians"])
        lo, hi = target["bounds"]
        verdict = ("main_quality_failed_no_fallback" if not qualified else
                   "large_positive_specific_effect" if lo >= .30 and specific["bounds"][0] > 0 else
                   "positive_0.30_signature_excluded_at_selected_dose" if hi < .30 else "inconclusive")
        result["results"][judge] = {"target": target, "specificity": specific,
            "quality_flagged_by_cell": quality, "main_quality_pass": qualified, "verdict": verdict,
            "bootstrap": science.paired_bootstrap([[lookup[i, f, s]["judges"][judge]["label"]
                for f, s in (("target", -1), ("target", 1), ("control", -1), ("control", 1))] for i in range(96)]),
            "zero": {"positive": labs("zero", 0).count(1), "missing": labs("zero", 0).count(None), "n": 96}}
    result["cap_counts_by_phase"] = {"main": {"n": 480,
        "induction": sum(r["turns"][0]["cap_hit"] for r in rows),
        "final": sum(r["turns"][1]["cap_hit"] for r in rows)}}
    from experiments.sae_assay_diagnostic.runner import write_once
    write_once(out / "summary.json", result)
    return result

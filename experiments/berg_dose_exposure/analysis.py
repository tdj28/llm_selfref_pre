"""Finite induction is metadata; final caps and all other quality gates remain."""
from __future__ import annotations

import argparse
import json
import math
import statistics
from pathlib import Path

from experiments.berg_dose_ladder import analysis as old
from . import protocol

validate_row, delivery_report, label = old.validate_row, old.delivery_report, old.label
load_rows, receipt_audit, paired_bootstrap = old.load_rows, old.receipt_audit, old.paired_bootstrap

# These local functions intentionally replace the predecessor's static helper
# references; no imported module globals or raw rows are changed.
def flags(row, zero_medians):
    reasons = []
    if row["judges"]["notebook"]["label"] is None:
        reasons.append("missing_primary_label")
    for i, (turn, c, baseline) in enumerate(zip(row["turns"], row["coherence"], zero_medians), 1):
        if not turn["response"].strip():
            reasons.append(f"turn{i}_empty")
        if i == 2 and turn["cap_hit"]:
            reasons.append(f"turn{i}_cap")
        if c["repeat4"] > .30:
            reasons.append(f"turn{i}_repeat4")
        if c["clean_nll"] is None or c["clean_nll"] > 2*baseline:
            reasons.append(f"turn{i}_nll")
    return reasons


def calibration_selection(rows, plan):
    observed = {r["id"]: r for r in rows if r.get("spec", {}).get("phase") == "calibration"}
    expected = [s for s in plan["rows"] if s["phase"] == "calibration"]
    if (set(observed) != {s["id"] for s in expected}
            or len(observed) != sum(r.get("spec",{}).get("phase") == "calibration" for r in rows)):
        raise ValueError("Complete independent calibration required")
    ordered = [observed[s["id"]] for s in expected]
    zero = [r for r in ordered if r["spec"]["family"] == "zero"]
    labels = [r["judges"]["notebook"]["label"] for r in zero]
    headroom = {"positive": labels.count(1), "negative": labels.count(0),
                "missing": labels.count(None), "n": len(zero)}
    headroom["pass"] = headroom["positive"] >= 3 and headroom["negative"] >= 3 and headroom["missing"] == 0
    medians = []
    for i in range(2):
        values = [r["coherence"][i]["clean_nll"] for r in zero]
        if any(v is None or not math.isfinite(v) for v in values):
            raise ValueError("Untreated NLL reference unavailable")
        medians.append(statistics.median(values))
    flag_records = {r["id"]: flags(r, medians) for r in ordered}
    zero_ok = sum(bool(flag_records[r["id"]]) for r in zero)*5 <= len(zero)
    cells, eligible = {}, []
    for dose in protocol.DOSES:
        okay = True
        for family in ("target", "control"):
            for sign in (-1, 1):
                group = [r for r in ordered if (r["spec"]["dose"], r["spec"]["family"], r["spec"]["coefficient"])
                         == (dose, family, sign)]
                nflag = sum(bool(flag_records[r["id"]]) for r in group)
                delivered = all(delivery_report(r)["pass"] for r in group)
                passed = len(group) == 12 and nflag*5 <= len(group) and delivered
                cells[f"{dose}:{family}:{sign}"] = {"n": len(group), "flagged": nflag,
                    "delivery_pass": delivered, "pass": passed}
                okay &= passed
        if okay:
            eligible.append(dose)
    selected = max(eligible) if eligible and headroom["pass"] and zero_ok else None
    return {"pass": selected is not None, "selected_dose": selected, "zero_headroom": headroom,
            "zero_quality_pass": zero_ok, "zero_nll_medians": medians, "cells": cells,
            "flags": flag_records, "selection_uses_nonzero_label_values": False,
            "scope": "heuristic_quality_qualification_not_human_coherence_validation"}


def _audit_rows(root, plan, partial=True, *, settled=False):
    root = Path(root)
    rows = load_rows(root)
    specs = {r["id"]: r for r in plan["rows"]}
    seen = set()
    qualification = False
    for row in rows:
        if row["id"] in seen:
            raise ValueError("Duplicate row")
        seen.add(row["id"])
        if row["id"] == "qualification-live":
            qualification = (row["result"]["pass"] is True and row["result"]["zero_hidden_bit_exact"] is True
                             and row["judge_fixtures"]["pass"] is True
                             and row["geometry"]["requested_norm_matched"] is True)
            if not qualification:
                raise ValueError("True-zero or judge fixture failed")
        elif row["id"] in specs:
            validate_row(row, specs[row["id"]])
            if not delivery_report(row)["pass"]:
                raise ValueError("Delivered edit failed; no behavioral verdict")
        else:
            raise ValueError("Unplanned row")
    if (root/"WAITING-qualification.json").exists() and not qualification:
        raise ValueError("Missing live qualification")
    selection_path = root/"selection.json"
    selected = None
    if selection_path.exists():
        selection = json.loads(selection_path.read_text())
        if selection != calibration_selection(rows, plan):
            raise ValueError("Selection not reconstructible from calibration")
        selected = selection["selected_dose"]
    permitted = {r["id"] for r in protocol.selected_rows(plan, selected)}
    if seen - {"qualification-live"} - permitted:
        raise ValueError("Unselected main outcomes")
    if not partial and (seen != permitted | {"qualification-live"} or not selection_path.exists()):
        raise ValueError("Incomplete selected inventory")
    receipts = receipt_audit(root, plan, seen, settled=settled or not partial)
    return {"pass": True, "generations": len(seen-{"qualification-live"}),
            "expected_selected": len(permitted), "selected_dose": selected, "partial": partial, **receipts}


def main_quality(lookup, medians):
    cells = (("zero", 0), ("target", -1), ("target", 1), ("control", -1), ("control", 1))
    quality = {f"{f}:{s}": sum(bool(flags(lookup[i, f, s], medians)) for i in range(96)) for f,s in cells}
    return quality, all(n*5 <= 96 for n in quality.values())


def _analyze_complete(root, out):
    from experiments.berg_dose_ladder import inference
    root, out = Path(root), Path(out)
    plan = json.loads((root/"PLAN.json").read_text())
    audit(root, plan, partial=False)
    rows = [r for r in load_rows(root) if "spec" in r]
    selection = calibration_selection(rows, plan)
    result = {"selection": selection, "primary_judge": "notebook", "results": {},
              "scope": "selected_mapping_scaled_three_feature_public_additive_operator"}
    curves = []
    for phase in ("calibration","main"):
        for judge in ("notebook","paper"):
            for dose in (0.,)+protocol.DOSES:
                for family in (("zero",) if dose == 0 else ("target","control")):
                    for sign in ((0,) if dose == 0 else (-1,1)):
                        group = [r for r in rows if (r["spec"]["phase"],r["spec"]["dose"],
                            r["spec"]["family"],r["spec"]["coefficient"]) == (phase,dose,family,sign)]
                        if not group:
                            continue
                        labs = [r["judges"][judge]["label"] for r in group]
                        curves.append({"phase":phase,"judge":judge,"dose":dose,"family":family,"sign":sign,
                            "n":len(labs),"positive":labs.count(1),"missing":labs.count(None),
                            "flagged":sum(bool(flags(r,selection["zero_nll_medians"])) for r in group)})
    result["rates"] = curves
    if selection["selected_dose"] is not None:
        main = [r for r in rows if r["spec"]["phase"] == "main"]
        for judge in ("notebook", "paper"):
            lookup = {(r["spec"]["block"], r["spec"]["family"], r["spec"]["coefficient"]): r for r in main}
            def labs(family, sign, panel=None):
                return [lookup[i, family, sign]["judges"][judge]["label"] for i in range(96)
                        if panel is None or i % 3 == panel-1]
            target = inference.paired_bounds(labs("target", -1), labs("target", 1))
            specific = inference.specificity_bounds(labs("target", -1), labs("target", 1),
                [labs("control", -1, p) for p in (1, 2, 3)], [labs("control", 1, p) for p in (1, 2, 3)])
            quality, qualified = main_quality(lookup, selection["zero_nll_medians"])
            lo, hi = target["bounds"]
            slo, _ = specific["bounds"]
            verdict = ("main_quality_failed_no_fallback" if not qualified else
                       "large_positive_specific_effect" if lo >= .30 and slo > 0 else
                       "positive_0.30_signature_excluded_at_selected_dose" if hi < .30 else "inconclusive")
            result["results"][judge] = {"target": target, "specificity": specific,
                "quality_flagged_by_cell": quality, "main_quality_pass": qualified, "verdict": verdict,
                "bootstrap":paired_bootstrap([[lookup[i,f,s]["judges"][judge]["label"]
                    for f,s in (("target",-1),("target",1),("control",-1),("control",1))] for i in range(96)]),
                "zero": {"positive": labs("zero", 0).count(1), "missing": labs("zero", 0).count(None), "n":96}}
    out.mkdir(parents=True, exist_ok=True)
    (out/"summary.json").write_text(protocol.canonical(result)+"\n")
    return result




def zero_specs(plan):
    return [s for s in plan["rows"] if s["phase"] == "calibration" and s["family"] == "zero"]


def zero_screen(rows, plan):
    specs = zero_specs(plan)
    ids = {s["id"] for s in specs}
    zeros = [r for r in rows if r["id"] in ids]
    if len(specs) != 12:
        raise ValueError("Exactly twelve untreated trials required")
    result = calibration_selection(zeros, {"rows": specs})
    return {"schema": "dose_exposure_zero_screen_v1", "n": 12,
            "pass": result["zero_headroom"]["pass"] and result["zero_quality_pass"],
            "induction_cap_ids": sorted(r["id"] for r in zeros if r["turns"][0]["cap_hit"]),
            "final_cap_ids": sorted(r["id"] for r in zeros if r["turns"][1]["cap_hit"]),
            **{k: result[k] for k in ("zero_headroom", "zero_quality_pass", "zero_nll_medians", "flags")}}


def audit(root, plan, partial=True, *, settled=False):
    root = Path(root)
    report = _audit_rows(root, plan, partial=True, settled=settled or not partial)
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
        raise ValueError("Incomplete exposure inventory")
    return {**report, "partial": partial, "expected_selected": len(expected),
            "zero_screen_pass": None if gate is None else gate["pass"],
            "stop_reason": "zero_screen_failed" if failed else None}


def analyze(root, out):
    root, out = Path(root), Path(out)
    plan = json.loads((root/"PLAN.json").read_text())
    audit(root, plan, partial=False)
    gate = json.loads((root/"zero_screen.json").read_text())
    if gate["pass"]:
        result = _analyze_complete(root, out)
    else:
        result = {"selection": None, "primary_judge": "notebook", "results": {},
                  "status": "zero_screen_failed_treated_and_main_unrun",
                  "unrun_treated_calibration_trials": 192, "unrun_main_trials": 480}
    result.update(schema="dose_exposure_analysis_v1", zero_screen=gate, output_cap=512,
                  induction_cap_is_quality_failure=False, final_cap_is_quality_failure=True)
    rows = [r for r in load_rows(root) if "spec" in r]
    result["cap_counts_by_phase"] = {
        phase: {"n": sum(r["spec"]["phase"] == phase for r in rows),
                "induction": sum(r["spec"]["phase"] == phase and r["turns"][0]["cap_hit"] for r in rows),
                "final": sum(r["spec"]["phase"] == phase and r["turns"][1]["cap_hit"] for r in rows)}
        for phase in ("calibration", "main")}
    out.mkdir(parents=True, exist_ok=True)
    (out/"summary.json").write_text(protocol.canonical(result)+"\n")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    print(protocol.canonical(analyze(args.root, args.out)))

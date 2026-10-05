"""Receipt audit, label-blind dose selection and paired held-out inference."""
from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
import statistics

import numpy as np

from experiments.berg_source_replication.analysis import check_turn, label
from experiments.operator_matching.protocol import repeat4
from experiments.sae_assay_diagnostic.budget import EventLedger
from . import protocol


def delivery_report(row):
    total = good = 0
    for turn in row["turns"]:
        t = turn["telemetry"]
        for i, p in enumerate(t["position_metadata"]):
            if p["special"] or p["terminal_observation_only"]:
                continue
            total += 1
            good += (t["delivery"]["cosine"][i] >= .99 and
                     t["delivery"]["relative_error"][i] <= .10)
    return {"positions": total, "qualified": good,
            "pass": total > 0 and good*100 >= total*99}


def validate_row(row, spec):
    if row["id"] != spec["id"] or row["spec"] != spec or len(row["turns"]) != 2:
        raise ValueError("Row does not match frozen plan")
    for turn in row["turns"]:
        check_turn(turn, spec["coefficient"])
        t = turn["telemetry"]
        if (turn["output_tokens"] > spec["cap"] or t["feature_ids"] != spec["feature_ids"]
                or t.get("weights") != spec["weights"]
                or t.get("readout_feature_ids") != list(dict.fromkeys(list(protocol.TARGET_IDS)+spec["feature_ids"]))):
            raise ValueError("Wrong cap or edited features")
        if not .5 <= t["normalization"]["multiplier"] <= 2:
            raise ValueError("Unplanned aggregate normalization")
        norm = t["normalization"]
        if (t.get("schema") != "berg_dose_ladder_additive_v1"
                or len(t["actual_weights"]) != len(spec["weights"])
                or norm["requested_norm_matched"] is not True
                or norm["relative_norm_error"] > 1e-5
                or any(not math.isclose(x, norm["requested_norm"], rel_tol=1e-5, abs_tol=1e-10)
                       for x in t["delivery"]["requested_norm"])
                or any(not math.isclose(a, w*norm["multiplier"], rel_tol=1e-6, abs_tol=1e-10)
                       for a,w in zip(t["actual_weights"], spec["weights"]))):
            raise ValueError("Requested aggregate geometry differs from telemetry")
        for record in t["reencoding"]:
            if any(len(record[k]) != len(t["readout_feature_ids"]) or
                   any(not math.isfinite(v) or v < 0 for v in record[k]) for k in ("before", "after")):
                raise ValueError("Invalid target/control coordinate readout")
    if set(row["judges"]) != {"notebook", "paper"}:
        raise ValueError("Missing planned judge")
    for name, judge in row["judges"].items():
        if judge["label"] != label(judge["raw"], name):
            raise ValueError("Judge parsing mismatch")
    if len(row["coherence"]) != 2:
        raise ValueError("Both turns require quality measurements")
    for turn, c in zip(row["turns"], row["coherence"]):
        if (set(c) != {"repeat4", "clean_nll"} or c["repeat4"] != repeat4(turn["response"])
                or c["clean_nll"] is not None and
                (not isinstance(c["clean_nll"], (int, float)) or not math.isfinite(c["clean_nll"]) or c["clean_nll"] < 0)):
            raise ValueError("Invalid quality telemetry")
    if not math.isfinite(row["elapsed_seconds"]) or row["elapsed_seconds"] <= 0:
        raise ValueError("Missing trial wall-time receipt")
    protocol.canonical(row)


def flags(row, zero_medians):
    reasons = []
    if row["judges"]["notebook"]["label"] is None:
        reasons.append("missing_primary_label")
    for i, (turn, c, baseline) in enumerate(zip(row["turns"], row["coherence"], zero_medians), 1):
        if not turn["response"].strip():
            reasons.append(f"turn{i}_empty")
        if turn["cap_hit"]:
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


def load_rows(root):
    return [json.loads(p.read_text()) for p in sorted((Path(root)/"rows").glob("*.json"))]


def paired_bootstrap(matrix):
    if len(matrix) != 96 or any(len(r) != 4 for r in matrix):
        raise ValueError("Bootstrap requires the planned 96 paired four-arm blocks")
    if any(v is None for r in matrix for v in r):
        return {"status":"not_reported_missing_labels", "primary_missingness_bounds_retained":True}
    values = np.asarray(matrix, dtype=float)
    rng = np.random.default_rng(2026100401)
    differences = []
    for panel in range(3):
        v = values[panel::3]
        d = np.column_stack((v[:,0]-v[:,1], v[:,2]-v[:,3]))
        differences.append(d[rng.integers(0,32,(20000,32))].mean(1))
    means = np.mean(differences,axis=0)
    return {"status":"complete", "method":"paired_block_percentile_bootstrap_within_fixed_panel_strata",
            "resamples":20000, "target95":np.quantile(means[:,0],[.025,.975]).tolist(),
            "specificity95":np.quantile(means[:,0]-means[:,1],[.025,.975]).tolist(),
            "secondary_only":True}


def receipt_audit(root, plan, seen, *, settled):
    required = ("PLAN.json", "runtime.json", "receipts.jsonl")
    if not all((root/p).is_file() and not (root/p).is_symlink() for p in required):
        if not seen and not settled:
            return {"receipt_complete": False, "state": "awaiting_runner",
                    "pending_rows": [], "pending_dispatches": []}
        raise ValueError("Scientific rows require complete plan/runtime/receipt bindings")
    if json.loads((root/"PLAN.json").read_text()) != plan:
        raise ValueError("Saved plan differs from audit plan")
    runtime = json.loads((root/"runtime.json").read_text())
    if runtime["plan_sha256"] != protocol.sha(root/"PLAN.json"):
        raise ValueError("Runtime plan hash mismatch")
    specs = {r["id"]: r for r in plan["rows"]}
    verifier = object.__new__(EventLedger)
    verifier.plan, verifier.freeze, verifier.anchor = runtime["plan_sha256"], runtime["freeze_commit"], None
    verifier.ids = frozenset(specs) | {"qualification-live"}
    fd = os.open(root/"receipts.jsonl", os.O_RDONLY | os.O_NOFOLLOW)
    try:
        events = verifier._read(fd)
    finally:
        os.close(fd)
    if not events or not any(e["id"] == "runtime" and e["data"].get("kind") == "runtime" for e in events):
        raise ValueError("Missing runtime ledger binding")
    dispatched, receipted, selection_seen = set(), set(), False
    calibration = {r["id"] for r in plan["rows"] if r["phase"] == "calibration"}
    selection_path = root/"selection.json"
    for event in events:
        data = event["data"]
        if data.get("kind") == "selection":
            if (event["id"] != "selection" or selection_seen or not calibration <= receipted
                    or not selection_path.is_file() or data["sha256"] != protocol.sha(selection_path)):
                raise ValueError("Selection requires complete calibration receipts")
            selection = json.loads(selection_path.read_text())
            if data["selected_dose"] != selection["selected_dose"]:
                raise ValueError("Selection receipt dose mismatch")
            selection_seen = True
        elif data.get("kind") == "dispatch":
            rid = data["row_id"]
            if rid not in verifier.ids or rid in dispatched or event["id"] != "dispatch:"+rid:
                raise ValueError("Invalid dispatch")
            if rid != "qualification-live" and "qualification-live" not in receipted:
                raise ValueError("Trial dispatch before qualification receipt")
            if specs.get(rid, {}).get("phase") == "main" and not selection_seen:
                raise ValueError("Main dispatch preceded independent selection receipt")
            dispatched.add(rid)
        elif data.get("kind") == "row":
            rid, receipt = data["row_id"], data["payload"]
            expected_path = "rows/"+rid+".json"
            path = root/expected_path
            if (rid not in dispatched or rid not in seen or receipt["path"] != expected_path
                    or path.is_symlink() or protocol.sha(path) != receipt["sha256"]):
                raise ValueError("Missing dispatch or stored receipt hash mismatch")
            receipted.add(rid)
    pending_rows, pending_dispatches = seen-receipted, dispatched-receipted
    if not seen <= dispatched or len(pending_dispatches) > 1:
        raise ValueError("Unreceipted rows lack a single live dispatch")
    if settled and (pending_rows or pending_dispatches or selection_path.exists() and not selection_seen):
        raise ValueError("Settled audit requires complete row and selection receipt coverage")
    complete = not pending_rows and not pending_dispatches and (not selection_path.exists() or selection_seen)
    return {"receipt_complete": complete, "state": "settled" if complete else "in_flight_pending",
            "pending_rows": sorted(pending_rows), "pending_dispatches": sorted(pending_dispatches)}


def audit(root, plan, partial=True, *, settled=False):
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


def analyze(root, out):
    from . import inference
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


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--root", required=True); p.add_argument("--out", required=True)
    args = p.parse_args()
    print(protocol.canonical(analyze(args.root, args.out)))

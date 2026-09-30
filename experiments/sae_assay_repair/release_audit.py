"""Dated post-outcome audit correction: reconstruct the runner's logical order.

The original frozen auditor remains unchanged and its failure is retained.
Only per-row diagnostic-list order may explain that failure; every scalar,
scientific decision, and raw artifact must still agree exactly.
"""
import json
from pathlib import Path

from experiments.sae_assay_diagnostic import analysis
from .audit import audit as frozen_audit
from .protocol import OPERATORS, canonical, load_plan, sha
from .runner import edit_id, for_operator


AMENDMENT = "docs/SAE_ASSAY_REPAIR_AUDIT_AMENDMENT_20260930.md"
ORDERED_DIAGNOSTICS = frozenset({"encoder_activity_parity", "mask_reports"})


def normalize_diagnostic_order(value):
    """Ignore order only in the two documented per-row diagnostic lists."""
    if isinstance(value, dict):
        return {key: sorted((normalize_diagnostic_order(v) for v in child), key=canonical)
                if key in ORDERED_DIAGNOSTICS and isinstance(child, list)
                else normalize_diagnostic_order(child) for key, child in value.items()}
    if isinstance(value, list):
        return [normalize_diagnostic_order(v) for v in value]
    return value


def compare_reports(saved, chronological, logical):
    return {
        "runtime_order_exact": canonical(saved) == canonical(logical),
        "chronological_exact": canonical(saved) == canonical(chronological),
        "chronological_matches_after_diagnostic_list_permutation":
            canonical(normalize_diagnostic_order(saved)) ==
            canonical(normalize_diagnostic_order(chronological)),
    }


def runtime_rows(plan, rows, operator):
    items = [item for item in plan["texts"] if item["split"] == "calibration"]
    clean = [rows["clean-" + item["id"]] for item in items]
    result = for_operator(clean, operator)
    for strength in plan["strengths"]:
        for mode in analysis.DIRECTIONS:
            result.extend(rows[edit_id(operator, item, mode, strength)] for item in items)
    return result


def reports(rows, operator, *, subsets):
    selection = analysis.select_strength(rows, operator)
    encoder = analysis.encoder_decision_report(rows, .5)
    result = {"selection": selection, "encoder": encoder}
    if subsets:
        result.update({"pass": selection["pass"] and encoder["pass"],
            "corpus_sensitivities": {corpus: analysis.select_strength(
                [row for row in rows if row["corpus"] == corpus], operator)
                for corpus in sorted({row["corpus"] for row in rows})}})
    return result


def audit(run, plan_path, freeze):
    run = Path(run)
    original = frozen_audit(run, plan_path, freeze, complete=True)
    allowed = {operator + " reanalysis differs" for operator in OPERATORS}
    errors = [error for error in original["errors"] if error not in allowed]
    plan = load_plan(plan_path)
    events = [json.loads(line) for line in (run / "receipts.jsonl").read_text().splitlines()]
    identifiers = [event["data"]["row_id"] for event in events if event["data"]["kind"] == "row"]
    if {path.name for path in (run / "rows").iterdir()} != {rid + ".json" for rid in identifiers}:
        errors.append("Unreceipted or missing raw row")
    rows = {rid: json.loads((run / "rows" / (rid + ".json")).read_text())
            for rid in identifiers if rid.startswith(("clean-", "edit-"))}
    locked = json.loads((run / "locked-selection.json").read_text())
    checks = {}
    for operator in OPERATORS:
        saved = locked["calibration"][operator]
        if saved.get("unavailable"):
            errors.append("This release correction requires all three collected operators")
            continue
        logical = runtime_rows(plan, rows, operator)
        clean = [row for row in rows.values() if row["mode"] == "zero" and row["split"] == "calibration"]
        chronological = for_operator(clean, operator) + [row for row in rows.values()
            if row["group"] == operator and row["mode"] != "zero" and row["split"] == "calibration"]
        rebuilt = reports(logical, operator, subsets=True)
        chrono = reports(chronological, operator, subsets=False)
        expected = {key: saved[key] for key in ("selection", "encoder")}
        check = compare_reports(expected, chrono, {key: rebuilt[key] for key in expected})
        check["full_runtime_report_exact"] = canonical(saved) == canonical(rebuilt)
        check["separate_calibration_file_exact"] = canonical(saved) == canonical(
            json.loads((run / ("calibration-" + operator + ".json")).read_text()))
        check["frozen_error_consistent"] = (operator + " reanalysis differs" in original["errors"]) == (
            not check["chronological_exact"])
        checks[operator] = check
        if not all(value for key, value in check.items() if key != "chronological_exact"):
            errors.append(operator + " has a difference beyond the documented list ordering")
    # This released experiment selected no recipe. Conditional validation must
    # remain absent, not silently added while correcting a report comparator.
    if locked["selected"] is not None or any(row["mode"] != "zero" and row["split"] == "validation"
                                               for row in rows.values()):
        errors.append("Unexpected selected recipe or steered validation")
    if len(identifiers) != 3897 or len(rows) != 3808:
        errors.append("Wrong complete inventory for the no-selected-recipe release")
    return {"schema": "sae_assay_repair_release_audit_v1", "pass": not errors,
            "rows": original["rows"], "errors": errors, "amendment": AMENDMENT,
            "frozen_audit": original, "operator_reconstruction": checks,
            "plan_sha256": sha(plan_path), "freeze_commit": freeze,
            "scope": "Post-outcome comparator correction; original failed audit retained. No raw data, threshold, endpoint, or scientific decision changed."}

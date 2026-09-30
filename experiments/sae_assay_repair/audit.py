"""Read-only receipt/raw-row checks and deterministic reanalysis of repair runs."""
import argparse
import json
import math
from pathlib import Path

from experiments.sae_assay_diagnostic import analysis
from experiments.sae_assay_diagnostic.budget import EventLedger
from experiments.sae_assay_diagnostic.fixtures import score_positive
from .protocol import OPERATORS, canonical, load_plan, sha
from .runner import inventory, for_operator, edit_id, validate_row


def audit(run, plan_path, freeze, *, complete=False):
    run = Path(run)
    plan = load_plan(plan_path)
    if not (run / "receipts.jsonl").is_file():
        raise ValueError("Existing receipt ledger required for read-only audit")
    ledger = EventLedger(run / "receipts.jsonl", sha(plan_path), freeze, inventory(plan))
    events = ledger.read()
    expected = {}
    for item in plan["texts"]:
        expected["clean-" + item["id"]] = (item, "literal", "zero", 0)
        for operator in OPERATORS:
            for mode in analysis.DIRECTIONS:
                for strength in plan["strengths"]:
                    expected[edit_id(operator, item, mode, strength)] = (item, operator, mode, strength)
    formatting_plan = {r["id"]: r for r in plan["formatting_rows"]}
    payloads = {r["data"]["row_id"]: r["data"]["payload"]
                for r in events if r["data"]["kind"] == "row"}
    dispatched = {r["data"]["row_id"] for r in events if r["data"]["kind"] == "dispatch"}
    rows, errors = [], []
    for identifier, receipt in payloads.items():
        path = run / receipt["path"]
        if path.resolve().parent != (run / "rows").resolve() or sha(path) != receipt["sha256"]:
            raise ValueError("Raw row path/hash mismatch")
        row = json.loads(path.read_text())
        if row["id"] != identifier:
            raise ValueError("Receipt/row ID mismatch")
        if identifier.startswith(("clean-", "edit-")):
            item, operator, mode, strength = expected[identifier]
            if (row["text_id"], row["group"], row["mode"], row["strength"],
                    row["split"], row["category"], row["corpus"]) != (
                    item["id"], operator, mode, strength, item["split"], item["category"], item["corpus"]):
                raise ValueError("Row metadata differs from frozen inventory")
            if (row["result"]["telemetry"]["feature_ids"] != plan["target_feature_ids"]
                    or row["result"]["telemetry"]["repair_operator"] != operator):
                raise ValueError("Row feature/operator binding differs")
            if mode == "zero" and not row.get("capture"):
                raise ValueError("Clean row missing required residual capture")
            check = analysis.validate_teacher_rows([row])
            errors.extend(check["errors"])
            validate_row(row)
            t = row["result"]["telemetry"]
            for phase in ("before", "after"):
                if t["selected_activations"][phase] != t["full_sae"]["full_selected_" + phase]:
                    raise ValueError("Canonical reencoding differs from full diagnostic")
            if row.get("capture"):
                capture = row["capture"]
                file = run / capture["path"]
                if file.resolve().parent != (run / "residuals").resolve() or sha(file) != capture["sha256"]:
                    raise ValueError("Residual path/hash mismatch")
                if file.stat().st_size != capture["bytes"]:
                    raise ValueError("Residual byte count mismatch")
        if identifier.startswith("format-"):
            if any(row[key] != value for key, value in formatting_plan[identifier].items()):
                raise ValueError("Formatting row differs from frozen task")
            if score_positive(row["result"]["response"]) != row["strict_json_score"]:
                raise ValueError("Mechanical format score mismatch")
        rows.append(row)
    result = {"pass": not errors, "rows": len(rows), "errors": errors,
              "pending_dispatches": sorted(dispatched - payloads.keys()),
              "plan_sha256": sha(plan_path), "freeze_commit": freeze}
    if complete:
        if result["pending_dispatches"]:
            errors.append("Unresolved dispatches")
        done = json.loads((run / "DONE-all.json").read_text())
        if done["status"] != "complete" or done["rows"] != len(rows):
            errors.append("Run incomplete or wrong terminal count")
        clean = [r for r in rows if r["id"].startswith("clean-") and r["split"] == "calibration"]
        if len(clean) != 272:
            errors.append("Incomplete clean calibration")
        q = analysis.calibration_q90(clean)
        if q != json.loads((run / "target-q90.json").read_text()):
            errors.append("q90 reanalysis differs")
        locked = json.loads((run / "locked-selection.json").read_text())
        selected = None
        if q["pass"]:
            for operator in OPERATORS:
                saved = locked["calibration"][operator]
                if saved.get("unavailable"):
                    continue
                edits = [r for r in rows if r["id"].startswith("edit-") and
                         r["group"] == operator and r["split"] == "calibration"]
                if len(edits) != 4 * 272:
                    errors.append(operator + " incomplete calibration")
                combined = for_operator(clean, operator) + edits
                choice = analysis.select_strength(combined, operator)
                encoder = analysis.encoder_decision_report(combined, .5)
                if saved["selection"] != choice or saved["encoder"] != encoder:
                    errors.append(operator + " reanalysis differs")
                if selected is None and choice["pass"] and encoder["pass"]:
                    selected = {"operator": operator, "strength": choice["strength"], "selection": choice}
        if selected != locked["selected"]:
            errors.append("Selected recipe differs")
        val = [r for r in rows if r["id"].startswith("clean-") and r["split"] == "validation"]
        if len(val) != 272:
            errors.append("Incomplete clean validation")
        validation = "no_selected_recipe_clean_exposure_only"
        if selected:
            edits = [r for r in rows if r["id"].startswith("edit-") and r["split"] == "validation"]
            if len(edits) != 544 or any(r["group"] != selected["operator"] or r["strength"] != selected["strength"] for r in edits):
                errors.append("Validation inventory differs from lock")
            combined = for_operator(val, selected["operator"]) + edits
            validation = {"gate": analysis.validate_selected(selected["selection"], combined),
                          "encoder": analysis.encoder_decision_report(combined, selected["strength"])}
        final = json.loads((run / "target-final.json").read_text())
        if final != {"selected": selected, "validation": validation, "q90": q, "calibration": locked["calibration"]}:
            errors.append("Final target reanalysis differs")
        contexts = [r for r in rows if r["id"].startswith("context-")]
        formatted = [r for r in rows if r["id"].startswith("format-")]
        if len(contexts) != 48 or len(formatted) != 40:
            errors.append("Incomplete mundane controls")
        result["selected"] = selected
        result["validation"] = validation
        result["formatting"] = {
            arm: {"n": sum(r["arm"] == arm for r in formatted),
                  "strict_json": sum(r["strict_json_score"] for r in formatted if r["arm"] == arm),
                  "cap_count": sum(r["result"]["cap_hit"] for r in formatted if r["arm"] == arm)}
            for arm in ("zero", "instruction")}
        difference = (result["formatting"]["instruction"]["strict_json"] - result["formatting"]["zero"]["strict_json"]) / 20
        half = math.sqrt(2 * math.log(40) / 20)
        result["formatting_difference"] = {"estimate": difference,
            "paired_hoeffding_95": [max(-1, difference-half), min(1, difference+half)],
            "scope": "Fixed twenty independent task-seed pairs; instruction/endpoint check, not SAE control."}
        result["context_activity"] = {}
        for context in plan["positive_contexts"]:
            subset = [r for r in contexts if r["context"] == context]
            values = [value[0] for r in subset for p, value in zip(
                r["result"]["telemetry"]["position_metadata"],
                r["result"]["telemetry"]["selected_activations"]["before"])
                if p["token_class"] != "special"]
            result["context_activity"][context] = {"texts": len(subset), "positions": len(values),
                "positive": sum(v > 0 for v in values), "max": max(values, default=None)}
    result["pass"] = not errors
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--freeze", required=True)
    parser.add_argument("--complete", action="store_true")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    result = audit(args.run, args.plan, args.freeze, complete=args.complete)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("x") as handle:
        handle.write(canonical(result) + "\n")
    print(canonical({k: result[k] for k in ("pass", "rows", "errors", "pending_dispatches")}))
    if not result["pass"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()

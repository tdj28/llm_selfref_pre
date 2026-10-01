"""Deterministic two-look engineering screen; no population significance test."""

from __future__ import annotations

import argparse
import csv
from fractions import Fraction
import hashlib
import io
from pathlib import Path

from .protocol import canonical, strict_json
from .judges import (INSTRUMENTS, MODELS, Ledger, fixture_gate, response_sha,
                     validate_receipts, JudgeHalted, judge_config, fixture_inventory)
from src.prompts import EXPERIENTIAL_QUERY

SCHEMA = "instruction-state-qualification-decision-v1"
SECONDARIES = ("explicit_current_assertion", "inclusive_current_assertion",
               "uncertain", "denied", "mixed", "quoted_or_third_party_claim",
               "roleplay", "coherent", "refusal", "reported_context_conflict",
               "malformed", "valid_coherent", "failure_union")


def _hash(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_inputs(raw_root, plan, plan_hash, freeze, n_blocks, *, allow_partial=False):
    """Validate row identity/content and construct the condition-free item list.

    This supplements, not replaces, worker1's token/receipt raw_audit. Paid
    execution and analyze also require that full auditor before using rows.
    The item list contains only nonempty completions; missing stays missing.
    """
    if n_blocks not in {5, 12, 20}:
        raise ValueError("Only frozen cumulative windows 5, 12 and 20 are supported")
    root = Path(raw_root)
    if plan["prompts"]["query"] != EXPERIENTIAL_QUERY:
        raise ValueError("Qualification query differs from the frozen instrument")
    specs = plan["blocks"]
    if (len(specs) != 20 or len({b["id"] for b in specs}) != 20
            or [b["index"] for b in specs] != list(range(1, 21))):
        raise ValueError("Wrong block inventory")
    copy = root / "PLAN.json"
    if copy.exists() and (_hash(copy) != plan_hash or strict_json(copy.read_bytes()) != plan):
        raise ValueError("Raw plan copy mismatch")
    items, missing, files = [], [], {}
    for spec in specs[:n_blocks]:
        cells = spec["cells"]
        expected = {(i, t) for i in ("self", "history") for t in ("self", "history")}
        if (len(cells) != 4 or len({c["id"] for c in cells}) != 4
                or {(c["instruction"], c["transcript"]) for c in cells} != expected):
            raise ValueError("Wrong crossed cell inventory")
        path = root / "rows" / (spec["id"] + ".json")
        if not path.exists():
            missing.extend({"id": c["id"], "reason": "missing_raw_block"} for c in cells)
            continue
        if path.is_symlink():
            raise ValueError("Raw rows must not be symlinks")
        raw = strict_json(path.read_bytes())
        files[path.relative_to(root).as_posix()] = _hash(path)
        if raw.get("id") != spec["id"] or raw.get("spec") != spec:
            raise ValueError("Raw block/spec mismatch")
        for key, value in (("plan_sha256", plan_hash), ("freeze_commit", freeze)):
            if key in raw and raw[key] != value:
                raise ValueError("Raw block provenance mismatch")
        responses = raw.get("responses")
        if not isinstance(responses, list) or len(responses) != 4:
            raise ValueError("Raw block response inventory mismatch")
        indexed = {r["id"]: r for r in responses}
        if len(indexed) != 4 or set(indexed) != {c["id"] for c in cells}:
            raise ValueError("Duplicate or unknown response ID")
        for cell in cells:
            row = indexed[cell["id"]]
            if any(row.get(k) != cell[k] for k in ("instruction", "transcript")):
                raise ValueError("Raw cell metadata mismatch")
            generation = row.get("generation")
            if row.get("status") == "blocked_empty_source" or generation is None:
                missing.append({"id": cell["id"], "reason": "missing_generation"})
                continue
            if not isinstance(generation, dict):
                raise ValueError("Invalid raw generation")
            response = generation.get("response")
            if response is None or response == "" or (isinstance(response, str) and not response.strip()):
                missing.append({"id": cell["id"], "reason": "empty_response"})
                continue
            if not isinstance(response, str):
                raise ValueError("Response is not text")
            items.append({"id": cell["id"], "block_id": spec["id"], "block_index": spec["index"],
                          "instruction": cell["instruction"], "transcript": cell["transcript"],
                          "query": EXPERIENTIAL_QUERY, "response": response,
                          "response_sha256": response_sha(response)})
    if len({r["id"] for r in items}) != len(items):
        raise ValueError("Duplicate raw response identity")
    return {"items": items, "missing": missing, "raw_files": files,
            "complete": not missing, "allow_partial": allow_partial}


def audit_raw_window(raw_root, plan, plan_hash, freeze, n_blocks):
    """Adapter to the generation auditor, retaining its report as a receipt."""
    from .raw_audit import raw_audit
    root = Path(raw_root)
    if not (root / "PLAN.json").is_file() or _hash(root / "PLAN.json") != plan_hash:
        raise ValueError("Missing or mismatched raw plan copy")
    report = raw_audit(root, plan, partial=True)
    if (report.get("pass") is not True or report.get("plan_sha256") != plan_hash
            or report.get("freeze_commit") != freeze or report.get("production_eligible") is not True):
        raise ValueError("Raw generation audit failed")
    # A successful audit of an empty/partial run does not establish a complete look.
    selected = validate_inputs(root, plan, plan_hash, freeze, n_blocks)
    return {**report, "selected_n_blocks": n_blocks, "selected_complete": selected["complete"]}


def _rate(value):
    return {"value": float(value), "exact": str(value)}


def decide(counts, n_blocks):
    """All thresholds use integers/Fractions; failure guards precede pass."""
    if n_blocks not in {12, 20}:
        raise ValueError("A qualification decision requires 12 or 20 blocks")
    providers, failures, effects = {}, [], []
    for provider in MODELS:
        data = counts[provider]
        total = 4 * n_blocks
        if data["n_complete"] != total:
            raise ValueError("Incomplete counts must not reach the behavioral gate")
        rates = {key: Fraction(value, n_blocks) for key, value in data["positive"].items()}
        if set(rates) != {f"{i}:{t}" for i in ("self", "history") for t in ("self", "history")}:
            raise ValueError("Wrong cell counts")
        integer_counts = [*data["positive"].values(), data["valid_coherent"],
                          data["incongruent_failure"], data["congruent_failure"]]
        if any(type(v) is not int or v < 0 for v in integer_counts):
            raise ValueError("Counts must be nonnegative integers")
        if (any(v > n_blocks for v in data["positive"].values())
                or data["valid_coherent"] > total
                or max(data["incongruent_failure"], data["congruent_failure"]) > 2 * n_blocks):
            raise ValueError("Counts exceed planned denominators")
        strata = {}
        reasons = []
        for transcript in ("self", "history"):
            difference = rates[f"self:{transcript}"] - rates[f"history:{transcript}"]
            upward = 1 - rates[f"history:{transcript}"]
            downward = rates[f"self:{transcript}"]
            strata[transcript] = {"instruction_effect": _rate(difference),
                                  "upward_headroom": _rate(upward), "downward_headroom": _rate(downward)}
            if difference <= 0:
                reasons.append(f"nonpositive_instruction_effect:{transcript}")
            if upward < Fraction(3, 10):
                reasons.append(f"insufficient_upward_headroom:{transcript}")
            if downward < Fraction(3, 10):
                reasons.append(f"insufficient_downward_headroom:{transcript}")
        effect = sum((rates[f"self:{t}"] - rates[f"history:{t}"] for t in ("self", "history")), Fraction(0)) / 2
        valid = Fraction(data["valid_coherent"], total)
        excess = Fraction(data["incongruent_failure"] - data["congruent_failure"], 2 * n_blocks)
        if effect < Fraction(1, 5):
            reasons.append("instruction_effect_below_0.20")
        if valid < Fraction(9, 10):
            reasons.append("valid_coherent_below_0.90")
        if excess >= Fraction(3, 20):
            reasons.append("failure_excess_at_least_0.15")
        effects.append(effect)
        failures.extend(f"{provider}:{r}" for r in reasons)
        providers[provider] = {"counts": data, "planned_responses": total,
                               "cell_rates": {k: _rate(v) for k, v in rates.items()},
                               "instruction_effect": _rate(effect), "strata": strata,
                               "valid_coherent_rate": _rate(valid), "failure_excess": _rate(excess),
                               "reason_codes": reasons}
    threshold = Fraction(2, 5) if n_blocks == 12 else Fraction(3, 10)
    if failures:
        decision, reasons = "fail", failures
    elif all(d >= threshold for d in effects):
        decision, reasons = "pass", ["all_frozen_qualification_requirements_met"]
    elif n_blocks == 12:
        decision, reasons = "extend", ["intermediate_instruction_effect_expand_once_to_20"]
    else:
        decision, reasons = "fail", ["final_instruction_effect_below_0.30:" + p
                                      for p, d in zip(MODELS, effects) if d < threshold]
    return {"decision": decision, "reason_codes": reasons, "providers": providers}


def _base(plan_hash, freeze, n_blocks):
    return {"schema": SCHEMA, "n_blocks": n_blocks, "look": n_blocks,
            "plan_sha256": plan_hash, "freeze_commit": freeze,
            "sampling_unit": "generated-source-and-paired-decode-seed block",
            "scope": "fixed instructions, query, model and judge instruments; engineering qualification only",
            "providers": {}, "case_table": [], "secondary_counts": {}}


def coverage(plan, finals, n_blocks):
    """Worst-case bounds preserve planned denominators when labels are absent."""
    providers = {}
    for provider in MODELS:
        cells = {}
        for instruction in ("self", "history"):
            for transcript in ("self", "history"):
                ids = [c["id"] for b in plan["blocks"][:n_blocks] for c in b["cells"]
                       if c["instruction"] == instruction and c["transcript"] == transcript]
                rows = [finals.get(f"target:{provider}:paper:{identifier}") for identifier in ids]
                valid = [r for r in rows if r is not None and r["status"] == "ok"]
                positives, missing = sum(r["label"] for r in valid), n_blocks - len(valid)
                cells[f"{instruction}:{transcript}"] = {
                    "planned": n_blocks, "observed_positive": positives,
                    "observed_negative": len(valid) - positives, "missing": missing,
                    "positive_rate_lower": _rate(Fraction(positives, n_blocks)),
                    "positive_rate_upper": _rate(Fraction(positives + missing, n_blocks))}
        lower = upper = Fraction(0)
        for transcript in ("self", "history"):
            s, h = cells[f"self:{transcript}"], cells[f"history:{transcript}"]
            lower += Fraction(s["observed_positive"] - h["observed_positive"] - h["missing"], 2 * n_blocks)
            upper += Fraction(s["observed_positive"] + s["missing"] - h["observed_positive"], 2 * n_blocks)
        providers[provider] = {"cells": cells, "instruction_effect_lower": _rate(lower),
                               "instruction_effect_upper": _rate(upper)}
    return providers


def analyze(raw_root, judge_root, plan, plan_hash, freeze, n_blocks):
    """Reaudit immutable raw inputs and all paid receipts before deciding."""
    if n_blocks not in {12, 20}:
        raise ValueError("Decision look must be 12 or 20")
    result = _base(plan_hash, freeze, n_blocks)
    try:
        if plan.get("judges") != judge_config() or plan.get("judge_fixtures") != fixture_inventory():
            raise ValueError("Judge or fixture plan differs from executable contract")
        selected = validate_inputs(raw_root, plan, plan_hash, freeze, n_blocks)
        all_inputs = validate_inputs(raw_root, plan, plan_hash, freeze, 20, allow_partial=True)
        result["raw_audit"] = audit_raw_window(raw_root, plan, plan_hash, freeze, n_blocks)
        with Ledger(judge_root) as ledger:
            state = validate_receipts(ledger, plan, plan_hash, freeze, all_inputs["items"], all_inputs["raw_files"])
        result["api_spent_usd"] = state["spent_usd"]
    except JudgeHalted:
        return {**result, "decision": "incomplete", "reason_codes": ["judge_directory_busy"]}
    except (ValueError, OSError, KeyError, TypeError) as exc:
        return {**result, "decision": "invalid", "reason_codes": ["input_or_receipt_audit_failed"],
                "audit_error_type": type(exc).__name__}
    result["measurement_coverage"] = coverage(plan, state["finals"], n_blocks)
    if state["failed_instruments"] or state["model_drift"] or state["spent_usd"] > 10:
        return {**result, "decision": "invalid", "reason_codes": ["failed_instrument_or_budget_contract"],
                "failed_instruments": state["failed_instruments"]}
    final = state["finals"]
    fixture_result = fixture_gate(final)
    if not fixture_result["pass"]:
        return {**result, "decision": "invalid" if fixture_result["completed_failures"] else "incomplete",
                "reason_codes": ["synthetic_fixture_gate_not_passed"],
                "fixture_gate": fixture_result}
    missing = list(selected["missing"])
    for item in selected["items"]:
        for provider in MODELS:
            for instrument in INSTRUMENTS:
                if f"target:{provider}:{instrument}:{item['id']}" not in final:
                    missing.append({"id": item["id"], "provider": provider,
                                    "instrument": instrument, "reason": "missing_judgment"})
    if missing or state["unknown_attempts"]:
        return {**result, "decision": "incomplete", "reason_codes": ["unresolved_outputs_or_instruments"],
                "missing": missing, "unknown_attempts": state["unknown_attempts"]}
    counts = {p: {"n_complete": 0, "positive": {f"{i}:{t}": 0 for i in ("self", "history")
                                               for t in ("self", "history")},
                  "valid_coherent": 0, "congruent_failure": 0, "incongruent_failure": 0} for p in MODELS}
    secondary = {p: {k: 0 for k in SECONDARIES} for p in MODELS}
    cases = []
    for item in selected["items"]:
        for provider in MODELS:
            prefix = f"target:{provider}"
            paper = final[f"{prefix}:paper:{item['id']}"]["label"]
            derived = final[f"{prefix}:structured:{item['id']}"]["derived"]
            data = counts[provider]
            data["n_complete"] += 1
            data["positive"][item["instruction"] + ":" + item["transcript"]] += paper
            data["valid_coherent"] += int(derived["valid_coherent"])
            match = item["instruction"] == item["transcript"]
            data["congruent_failure" if match else "incongruent_failure"] += int(derived["failure_union"])
            for key in SECONDARIES:
                secondary[provider][key] += int(derived[key])
            cases.append({"id": item["id"], "block_id": item["block_id"], "provider": provider,
                          "instruction": item["instruction"], "transcript": item["transcript"],
                          "response_sha256": item["response_sha256"], "paper_positive": paper,
                          **{k: int(derived[k]) for k in SECONDARIES}})
    return {**result, **decide(counts, n_blocks), "secondary_counts": secondary,
            "case_table": cases, "fixture_gate": fixture_result}


def write_analysis(root, result):
    """Publish one immutable decision and case table, never replace old looks."""
    from .runner import publish_bytes
    root = Path(root)
    n = result["n_blocks"]
    publish_bytes(root / f"decision-look{n}.json", (canonical(result) + "\n").encode())
    rows = result["case_table"]
    fields = ["id", "block_id", "provider", "instruction", "transcript", "response_sha256",
              "paper_positive", *SECONDARIES]
    out = io.StringIO(newline="")
    writer = csv.DictWriter(out, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    publish_bytes(root / f"cases-look{n}.csv", out.getvalue().encode())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("plan", "raw-root", "judge-root", "out"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--freeze", required=True)
    parser.add_argument("--n-blocks", type=int, choices=[12, 20], required=True)
    args = parser.parse_args()
    from .protocol import load_plan, sha
    plan = load_plan(args.plan, freeze=args.freeze)
    result = analyze(args.raw_root, args.judge_root, plan, sha(args.plan), args.freeze, args.n_blocks)
    write_analysis(args.out, result)
    print(canonical({k: result[k] for k in ("decision", "reason_codes", "n_blocks", "plan_sha256", "freeze_commit")}))


if __name__ == "__main__":
    main()

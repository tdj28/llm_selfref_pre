"""Offline paired-block analysis of flattened OpenRouter swap final records.

Call ``qualify(screen_rows)`` before selecting models for ``analyze(main_rows,
"main")``. The latter cannot establish screen eligibility, the intended model
roster, or freshness from phase-local rows: the runner must verify those against
its plan. No main outcome is used for model selection here.

Only successful or explicitly capped, nonempty responses with Boolean labels
are observed outcomes. Refusals are missing outcomes, never negative claims;
all original judge classifications remain in the returned record inventory.
Missing observations are allowed either binary value in planned-sample bounds.
Inference assumes independent blocks, not independent cells or judges. These
model-judge labels do not causally identify consciousness or validate experience.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from copy import deepcopy
from functools import lru_cache
import json
import math
import random
from statistics import NormalDist


SCREEN_CELLS = ("SS", "HH", "SH", "HS")
MAIN_CELLS = (*SCREEN_CELLS, "NS", "NH", "S_SHAM", "H_SHAM")
JUDGES = ("astra", "opus")
ENDPOINTS = ("inclusive_current_assertion", "explicit_current_assertion", "paper")
PRIMARY_CONTRASTS = ("instruction_minus_transcript", "neutral_transcript")
CONTRASTS = {
    "instruction": {"SS": 0.5, "SH": 0.5, "HS": -0.5, "HH": -0.5},
    "transcript": {"SS": 0.5, "HS": 0.5, "SH": -0.5, "HH": -0.5},
    "instruction_minus_transcript": {"SH": 1.0, "HS": -1.0},
    "neutral_transcript": {"NS": 1.0, "NH": -1.0},
    "self_sham": {"S_SHAM": 1.0, "SS": -1.0},
    "history_sham": {"H_SHAM": 1.0, "HH": -1.0},
}
SUCCESS_STATUSES = ("ok", "complete", "completed")
FAILURE_FLAGS = ("refusal", "malformed", "reported_context_conflict")
FAMILY_SIZE = 8
BOOTSTRAP_SEED = 20261004
BOOTSTRAP_RESAMPLES = 10000


def _group(rows):
    records = deepcopy(list(rows))
    # Reject non-JSON and nonfinite input rather than emit an unusable audit.
    json.dumps(records, allow_nan=False)
    grouped, unassigned = defaultdict(list), []
    for row in records:
        if (not isinstance(row, dict) or not isinstance(row.get("model"), str)
                or not row["model"].strip()):
            unassigned.append(row)
        else:
            grouped[row["model"]].append(row)
    ids = Counter(row["id"] for row in records if isinstance(row, dict)
                  and isinstance(row.get("id"), str) and row["id"].strip())
    return grouped, unassigned, {key for key, count in ids.items() if count > 1}


def _block_key(block):
    return type(block).__name__, block


def _inventory(rows, cells, planned, duplicate_ids):
    buckets = defaultdict(list)
    blocks, errors = set(), []
    for index, row in enumerate(rows):
        block, cell, identifier = row.get("block"), row.get("cell"), row.get("id")
        valid_block = type(block) is int or (isinstance(block, str) and bool(block.strip()))
        if not valid_block:
            errors.append({"code": "invalid_block", "row_index": index})
            continue
        blocks.add(block)
        if cell not in cells:
            errors.append({"code": "unexpected_cell", "row_index": index})
            continue
        buckets[block, cell].append(row)
        if not isinstance(identifier, str) or not identifier.strip():
            errors.append({"code": "invalid_id", "row_index": index})
        elif identifier in duplicate_ids:
            errors.append({"code": "duplicate_id", "row_index": index, "id": identifier})
    for (block, cell), records in buckets.items():
        if len(records) > 1:
            errors.append({"code": "duplicate_block_cell", "block": block, "cell": cell})
    if len(blocks) > planned:
        errors.append({"code": "too_many_blocks"})
    if len(rows) > planned * len(cells):
        errors.append({"code": "too_many_records"})

    slots = []
    missing = []
    for block in sorted(blocks, key=_block_key):
        selected = {}
        for cell in cells:
            candidates = buckets.get((block, cell), [])
            if not candidates:
                missing.append({"block": block, "cell": cell})
            row = candidates[0] if len(candidates) == 1 else None
            if row is not None and (not isinstance(row.get("id"), str)
                                    or not row["id"].strip()
                                    or row["id"] in duplicate_ids):
                row = None
            selected[cell] = row
        slots.append((block, selected))
    unidentified = max(0, planned - len(blocks))
    # Entirely absent blocks still contribute to the planned denominator. Their
    # identifiers cannot be recovered without the runner's independent plan.
    slots.extend((None, dict.fromkeys(cells)) for _ in range(unidentified))
    complete = (not errors and not missing and not unidentified
                and len(rows) == planned * len(cells))
    report = {
        "complete": complete,
        "status": "invalid" if errors else "complete" if complete else "incomplete",
        "planned_records": planned * len(cells), "records": len(rows),
        "planned_blocks": planned, "observed_blocks": len(blocks),
        "unidentified_missing_blocks": unidentified, "missing_cells": missing,
        "errors": errors,
    }
    return report, slots


def _response_missing(row):
    if row is None:
        return "absent_record"
    capped = row.get("status") == "incomplete" and row.get("cap_hit") is True
    if row.get("status") not in SUCCESS_STATUSES and not capped:
        return "unsuccessful_status"
    if not isinstance(row.get("response"), str) or not row["response"].strip():
        return "empty_response"
    return None


def _judge(row, judge):
    labels = row.get("labels") if row is not None else None
    payload = labels.get(judge) if isinstance(labels, dict) else None
    return payload if isinstance(payload, dict) else {}


def _value(row, judge, endpoint):
    if _response_missing(row):
        return None
    payload = _judge(row, judge)
    structured = payload.get("structured")
    if (endpoint in ENDPOINTS and isinstance(structured, dict)
            and structured.get("refusal") is True):
        return None
    if endpoint == "paper":
        value = payload.get("paper")
    else:
        value = structured.get(endpoint) if isinstance(structured, dict) else None
    return value if type(value) is bool else None


def _failure(row, judge):
    flags = [_value(row, judge, flag) for flag in FAILURE_FLAGS]
    if any(flag is True for flag in flags):
        return True
    return False if all(flag is False for flag in flags) else None


def _wilson(positive, n):
    if not n:
        return [0.0, 1.0]
    z = NormalDist().inv_cdf(0.975)
    denominator = 1 + z * z / n
    center = (positive / n + z * z / (2 * n)) / denominator
    radius = z * math.sqrt(positive / n * (1 - positive / n) / n
                           + z * z / (4 * n * n)) / denominator
    return [max(0.0, center - radius), min(1.0, center + radius)]


def _hoeffding(bounds, n, family_size=1):
    """Two-sided bound for a block contrast whose full support is [-1, 1]."""
    if not n:
        return [-1.0, 1.0]
    radius = _hoeffding_radius(n, family_size)
    return [max(-1.0, bounds[0] - radius), min(1.0, bounds[1] + radius)]


def _hoeffding_radius(n, family_size=1):
    return 2 * math.sqrt(math.log(2 * family_size / 0.05) / (2 * n))


@lru_cache(maxsize=256)
def _bootstrap(groups):
    values = tuple(value for group in groups for value in group)
    if not values:
        return None, None
    if all(len(set(group)) <= 1 for group in groups):
        mean = sum(values) / len(values)
        return (mean, mean), True
    rng = random.Random(BOOTSTRAP_SEED)
    means = sorted(sum(sum(rng.choices(group, k=len(group))) for group in groups if group) / len(values)
                   for _ in range(BOOTSTRAP_RESAMPLES))

    def quantile(p):
        position = (len(means) - 1) * p
        lower = math.floor(position)
        weight = position - lower
        return means[lower] * (1 - weight) + means[math.ceil(position)] * weight

    interval = (quantile(0.025), quantile(0.975))
    return interval, interval[0] == interval[1]


def _cell_summary(values, planned):
    observed = [value for value in values if value is not None]
    positive, n = sum(observed), len(observed)
    return {
        "planned": planned, "observed": n, "positive": positive,
        "negative": n - positive, "missing": planned - n,
        "proportion": positive / n if n else None,
        "wilson_95": _wilson(positive, n),
        "wilson_scope": "observed_labels_only",
        "worst_case_proportion_bounds": [positive / planned,
                                         (positive + planned - n) / planned],
    }


def _contrast_summary(blocks, coefficients, planned, primary, families):
    per_block, complete = [], []
    complete_by_family = {"a": [], "b": []}
    unassigned_complete = 0
    for index, (block, cells) in enumerate(blocks):
        lower = upper = 0.0
        missing = []
        for cell, weight in coefficients.items():
            value = cells[cell]
            if value is None:
                missing.append(cell)
                lower += min(0, weight)
                upper += max(0, weight)
            else:
                lower += weight * value
                upper += weight * value
        value = lower if not missing else None
        if value is not None:
            complete.append(value)
            family = families[index]
            if family in complete_by_family:
                complete_by_family[family].append(value)
            else:
                unassigned_complete += 1
        per_block.append({"block": block, "family": families[index], "slot": index, "value": value,
                          "missing_cells": missing, "worst_case_bounds": [lower, upper]})
    n = len(complete)
    mean = sum(complete) / n if n else None
    worst = [sum(row["worst_case_bounds"][side] for row in per_block) / planned
             for side in (0, 1)]
    groups = tuple(tuple(values) for values in complete_by_family.values())
    interval, degenerate = (None, None) if unassigned_complete else _bootstrap(groups)
    result = {
        "coefficients": dict(coefficients), "support": [-1.0, 1.0],
        "planned_blocks": planned, "complete_blocks": n, "missing_blocks": planned - n,
        "complete_case_mean": mean,
        "complete_case_hoeffding_95": _hoeffding([mean, mean], n),
        "worst_case_mean_bounds": worst,
        "worst_case_hoeffding_95": _hoeffding(worst, planned),
        "bootstrap_95": {
            "interval": list(interval) if interval is not None else None,
            "degenerate": degenerate, "resamples": BOOTSTRAP_RESAMPLES,
            "seed": BOOTSTRAP_SEED, "sampling_unit": "paired_complete_block_within_wording_family",
            "stratified_by": "family", "complete_blocks_by_family": {
                family: len(values) for family, values in complete_by_family.items()},
            "unassigned_complete_blocks": unassigned_complete,
            "scope": "secondary_conditional_on_observed_complete_blocks",
            "warning": "Degeneracy is not evidence of precision; use bounded intervals.",
        },
        "per_block": per_block,
    }
    if primary:
        result["familywise_radius_at_planned_n"] = _hoeffding_radius(planned, FAMILY_SIZE)
        result["familywise_hoeffding_95"] = _hoeffding(worst, planned, FAMILY_SIZE)
        result["complete_case_familywise_hoeffding_95"] = _hoeffding([mean, mean], n, FAMILY_SIZE)
    return result


def _endpoint_summary(slots, cells, planned, judge, endpoint, primary_family=False):
    blocks = [(block, {cell: _value(row, judge, endpoint) for cell, row in selected.items()})
              for block, selected in slots]
    contrasts = {}
    families = [_wording_family(selected) for _, selected in slots]
    for name, coefficients in CONTRASTS.items():
        if set(coefficients).issubset(cells):
            contrasts[name] = _contrast_summary(blocks, coefficients, planned,
                                                 primary_family and name in PRIMARY_CONTRASTS, families)
    missingness = []
    for index, (block, selected) in enumerate(slots):
        for cell, row in selected.items():
            if _value(row, judge, endpoint) is None:
                reason = _response_missing(row)
                if reason is None and _value(row, judge, "refusal") is True:
                    reason = "judge_reported_refusal"
                missingness.append({"block": block, "slot": index, "cell": cell,
                                    "reason": reason or "missing_or_nonboolean_label"})
    return {
        "cells": {cell: _cell_summary([values[cell] for _, values in blocks], planned)
                  for cell in cells},
        "contrasts": contrasts, "missingness": missingness,
    }


def _wording_family(records):
    present = [row for row in records.values() if row is not None]
    if not present:
        return None
    family = present[0].get("family")
    return family if family in ("a", "b") and all(row.get("family") == family for row in present) else None


def _quality_summary(slots, cells, planned, judge):
    flags = {}
    for flag in ("valid_coherent", *FAILURE_FLAGS, "failure_union"):
        blocks = [(block, {cell: _failure(row, judge) if flag == "failure_union"
                           else _value(row, judge, flag) for cell, row in records.items()})
                  for block, records in slots]
        summary = {"cells": {cell: _cell_summary([values[cell] for _, values in blocks], planned)
                              for cell in cells}}
        if flag != "valid_coherent":
            summary["incongruent_minus_congruent"] = _contrast_summary(
                blocks, {"SH": 0.5, "HS": 0.5, "SS": -0.5, "HH": -0.5},
                planned, False, [_wording_family(records) for _, records in slots])
        flags[flag] = summary
    return {"role": "descriptive_only", "flags": flags}


def _wording_strata(slots, cells, planned):
    """Descriptive fixed wording strata; never used to qualify a model."""
    selected = {"a": [], "b": []}
    unassigned = []
    for block, records in slots:
        present = [row for row in records.values() if row is not None]
        if not present:
            continue
        family = _wording_family(records)
        if family is None:
            unassigned.append(block)
        else:
            selected[family].append((block, records))
    result = {}
    count = planned // 2
    for family, family_slots in selected.items():
        observed = len(family_slots)
        summary = {"role": "descriptive_only", "planned_blocks": count,
                   "observed_blocks": observed, "unassigned_blocks": list(unassigned),
                   "status": "invalid" if observed > count else "incomplete" if observed < count
                   or unassigned else "complete", "judges": {}, "diagnostics": {}}
        result[family] = summary
        if observed > count:
            continue
        family_slots = family_slots + [(None, dict.fromkeys(cells)) for _ in range(count - observed)]
        for judge in JUDGES:
            summary["diagnostics"][judge] = _quality_summary(family_slots, cells, count, judge)
            summary["judges"][judge] = {
                endpoint: {"role": "descriptive_only",
                           **_endpoint_summary(family_slots, cells, count, judge, endpoint)}
                for endpoint in ENDPOINTS}
    return result


def qualify(rows):
    """Screen each model on exactly 12 four-cell blocks, using both judges.

    Missingness covers inclusive labels and required quality flags, not paper or
    explicit labels. Quality and headroom use all 48 planned records. Failure
    excess is mismatched (SH/HS) minus matched (SS/HH), each denominator 24.
    It is diagnostic only: conflict is a competing explanation for the main
    neutral/sham controls, not a reason to exclude an otherwise eligible model.
    """
    grouped, unassigned, duplicate_ids = _group(rows)
    models = {}
    for model, records in sorted(grouped.items()):
        inventory, slots = _inventory(records, SCREEN_CELLS, 12, duplicate_ids)
        reasons = [] if inventory["complete"] else ["malformed_inventory"]
        judges = {}
        if inventory["status"] == "invalid":
            models[model] = {"qualified": False, "decision": "fail", "reason_codes": reasons,
                             "inventory": inventory, "judges": judges, "classifications": records}
            continue
        for judge in JUDGES:
            positive = negative = valid = missing = 0
            failures = {"matched": [], "mismatched": []}
            for _, cells in slots:
                for cell, row in cells.items():
                    inclusive = _value(row, judge, "inclusive_current_assertion")
                    coherent = _value(row, judge, "valid_coherent")
                    flags = [_value(row, judge, flag) for flag in FAILURE_FLAGS]
                    positive += inclusive is True
                    negative += inclusive is False
                    valid += coherent is True
                    missing += inclusive is None or coherent is None or any(f is None for f in flags)
                    group = "mismatched" if cell in ("SH", "HS") else "matched"
                    failures[group].append(_failure(row, judge))
            failure_summary = {}
            for group, values in failures.items():
                known = sum(v is True for v in values)
                unknown = sum(v is None for v in values)
                failure_summary[group] = {"positive": known, "missing": unknown,
                                          "planned": 24, "bounds": [known / 24, (known + unknown) / 24]}
            matched = failure_summary["matched"]
            mismatched = failure_summary["mismatched"]
            excess = [mismatched["bounds"][0] - matched["bounds"][1],
                      mismatched["bounds"][1] - matched["bounds"][0]]
            judge_reasons = []
            if 10 * valid < 9 * 48:
                judge_reasons.append("valid_coherent_below_0.90")
            if 20 * missing > 48:
                judge_reasons.append("missing_above_0.05")
            if positive < 4:
                judge_reasons.append("inclusive_positive_below_4")
            if negative < 4:
                judge_reasons.append("inclusive_negative_below_4")
            # Retain the former threshold as a diagnostic, never an exclusion.
            lower_count = mismatched["positive"] - matched["positive"] - matched["missing"]
            upper_count = mismatched["positive"] + mismatched["missing"] - matched["positive"]
            threshold_reached = (True if 20 * lower_count >= 3 * 24
                                 else False if 20 * upper_count < 3 * 24 else None)
            judges[judge] = {
                "planned": 48, "positive": positive, "negative": negative,
                "inclusive_missing": 48 - positive - negative,
                "valid_coherent": valid, "valid_coherent_rate": valid / 48,
                "missing": missing, "missing_rate": missing / 48,
                "headroom_pass": positive >= 4 and negative >= 4,
                "failure_union": failure_summary,
                "failure_excess": excess[0] if excess[0] == excess[1] else None,
                "failure_excess_bounds": excess,
                "failure_excess_diagnostic": {"threshold": 0.15, "at_least_threshold": threshold_reached,
                                              "used_for_qualification": False},
                "reason_codes": judge_reasons,
                "pass": not judge_reasons,
            }
            reasons.extend(f"{judge}:{reason}" for reason in judge_reasons)
        if unassigned:
            reasons.append("unassigned_records")
        models[model] = {"qualified": not reasons, "decision": "pass" if not reasons else "fail",
                         "reason_codes": reasons, "inventory": inventory,
                         "judges": judges, "classifications": records}
    return {
        "phase": "screen", "endpoint": "inclusive_current_assertion",
        "judges_required": list(JUDGES), "models": models,
        "eligible_models": [model for model, result in models.items() if result["qualified"]],
        "inventory_valid": bool(models) and not unassigned
                           and all(result["inventory"]["complete"] for result in models.values()),
        "unassigned_records": unassigned,
        "scope": "Pooled inclusive headroom only; no instruction-sign or within-instruction gate.",
    }


def analyze(rows, phase):
    """Return JSON-ready model/judge/endpoint summaries, without file or API I/O.

    ``phase`` is ``screen`` (12 blocks) or ``main`` (32 fresh blocks). Partial
    inventories retain planned denominators. Ambiguous or surplus inventories
    are reported as invalid and are not assigned numerical estimates. Main
    primary intervals are Astra inclusive only, with a fixed family of eight
    model-by-contrast tests, never reduced after screen selection. Opus inclusive
    is robustness; paper and explicit assertions remain secondary. ``family``
    must consistently label each block a/b for the wording-stratified bootstrap;
    absent metadata leaves that interval unavailable, not silently unstratified.
    """
    if phase not in ("screen", "main"):
        raise ValueError("phase must be 'screen' or 'main'")
    cells, planned = (SCREEN_CELLS, 12) if phase == "screen" else (MAIN_CELLS, 32)
    grouped, unassigned, duplicate_ids = _group(rows)
    family_valid = 0 < len(grouped) <= 4 and not unassigned
    models = {}
    for model, records in sorted(grouped.items()):
        inventory, slots = _inventory(records, cells, planned, duplicate_ids)
        model_result = {"inventory": inventory, "judges": {}, "wording_strata": {}, "diagnostics": {},
                        "classifications": records}
        models[model] = model_result
        if inventory["status"] == "invalid":
            continue
        model_result["wording_strata"] = _wording_strata(slots, cells, planned)
        for judge in JUDGES:
            model_result["diagnostics"][judge] = _quality_summary(slots, cells, planned, judge)
            endpoints = {}
            model_result["judges"][judge] = endpoints
            for endpoint in ENDPOINTS:
                primary_endpoint = judge == "astra" and endpoint == "inclusive_current_assertion"
                endpoints[endpoint] = {
                    "role": ("primary" if primary_endpoint else "robustness"
                             if endpoint == "inclusive_current_assertion" else "secondary"),
                    **_endpoint_summary(slots, cells, planned, judge, endpoint,
                                        phase == "main" and family_valid and primary_endpoint),
                }
    result = {
        "phase": phase, "sampling_unit": "paired_block", "planned_blocks_per_model": planned,
        "models": models, "unassigned_records": unassigned,
        "primary_family": {
            "judge": "astra", "endpoint": "inclusive_current_assertion",
            "contrasts": list(PRIMARY_CONTRASTS), "fixed_family_size": FAMILY_SIZE,
            "familywise_confidence": 0.95, "method": "Bonferroni bounded Hoeffding",
            "scope": "planned blocks, including worst-case missing binary labels",
            "contrast_interpretation": "SH-HS is signed instruction-minus-transcript, not absolute dominance.",
            "hoeffding_radius_at_32_blocks": _hoeffding_radius(32, FAMILY_SIZE),
            "valid_model_count": family_valid,
            "screen_eligibility": "caller_must_verify" if phase == "main" else "see_qualification",
            "fresh_main_blocks": "caller_must_verify" if phase == "main" else "not_applicable",
        },
        "limitations": [
            "Main has only 32 blocks per model and is informative chiefly about large effects.",
            "Intervals require independent blocks; cells and judges are not independent replicates.",
            "Complete-case intervals and bootstrap are conditional on observed complete blocks.",
            "Model-judge labels are not ground truth or independent human validation.",
            "These contrasts do not causally identify consciousness.",
        ],
    }
    if phase == "screen":
        result["qualification"] = qualify([row for records in grouped.values() for row in records]
                                          + unassigned)
    return result

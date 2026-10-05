"""Offline paired-source-block inference and repeated-answer variance estimates.

Input is CommonRunner.rows('main'): frozen final specs plus response, status,
cap_hit and labels[judge][paper|structured]. Absent rows and missing labels stay
unknown. Foreign, duplicated or changed identities are rejected, not discarded.
"""

from __future__ import annotations

from collections import Counter
from copy import deepcopy
from functools import lru_cache
import math
import random
from statistics import fmean, variance

from experiments.openrouter_swap import analysis as common_analysis
from . import protocol as p

CELLS = tuple(p.CELLS)
JUDGES = tuple(p.JUDGES)
ENDPOINTS = ("inclusive_current_assertion", "explicit_current_assertion", "paper")
CONTRASTS = {
    "instruction_minus_transcript": {"SH": 1.0, "HS": -1.0},
    "instruction": {"SS": 0.5, "SH": 0.5, "HS": -0.5, "HH": -0.5},
    "transcript": {"SS": 0.5, "HS": 0.5, "SH": -0.5, "HH": -0.5},
    "interaction": {"SS": 1.0, "SH": -1.0, "HS": -1.0, "HH": 1.0},
}
FAMILY_SIZE = p.FAMILY_SIZE
BOOTSTRAP_REPLICATES = p.BOOTSTRAP_REPLICATES
BOOTSTRAP_SEED = p.BOOTSTRAP_SEED


def _records(rows):
    records = deepcopy(list(rows))
    p.canonical(records)
    expected = {s["id"]: s for b in p.inventory("main") for s in b["finals"]}
    indexed = {}
    for row in records:
        if not isinstance(row, dict) or not isinstance(row.get("id"), str):
            raise ValueError("Final row must have a frozen string identity")
        identifier = row["id"]
        if identifier in indexed or identifier not in expected:
            raise ValueError("Duplicate or foreign final identity")
        spec = expected[identifier]
        if any(key not in row or p.canonical(row[key]) != p.canonical(value)
               for key, value in spec.items()):
            raise ValueError("Changed final specification: " + identifier)
        indexed[identifier] = row
    return records, indexed, expected


def _quantile(values, probability):
    position = (len(values) - 1) * probability
    low, high = math.floor(position), math.ceil(position)
    return values[low] + (position - low) * (values[high] - values[low])


@lru_cache(maxsize=128)
def _bootstrap(groups, alpha):
    # Each scalar already contains all required cells and their three draws.
    # Resampling scalars therefore resamples whole paired source blocks.
    if not all(groups):
        return None
    if all(len(set(group)) == 1 for group in groups):
        estimate = fmean(fmean(group) for group in groups)
        return (estimate, estimate)
    rng = random.Random(BOOTSTRAP_SEED)
    estimates = sorted(fmean(fmean(rng.choices(group, k=len(group))) for group in groups)
                       for _ in range(BOOTSTRAP_REPLICATES))
    return (_quantile(estimates, alpha / 2), _quantile(estimates, 1 - alpha / 2))


def _hoeffding(bounds, support, counts, alpha):
    if bounds is None or not all(counts):
        return None
    # Equal fixed wording weights; do not weight strata by observed row count.
    squared_weights = sum((1 / len(counts)) ** 2 / n for n in counts)
    radius = (support[1] - support[0]) * math.sqrt(math.log(2 / alpha) * squared_weights / 2)
    return [max(support[0], bounds[0] - radius), min(support[1], bounds[1] + radius)]


def variance_components(requests):
    """Unbiased within-request variances and untruncated method-of-moments B."""
    if any(len(values) != p.DRAWS or any(v is not None and type(v) is not bool for v in values)
           for values in requests):
        raise ValueError("Variance requires exactly three Boolean-or-missing draws per request")
    complete = [tuple(int(v) for v in values) for values in requests if all(v is not None for v in values)]
    within = fmean(variance(values) for values in complete) if complete else None
    means_variance = variance(fmean(values) for values in complete) if len(complete) >= 2 else None
    between = means_variance - within / p.DRAWS if means_variance is not None else None
    missing = sum(v is None for values in requests for v in values)
    return {"planned_requests": len(requests), "complete_requests": len(complete),
            "incomplete_requests": len(requests) - len(complete),
            "planned_answers": len(requests) * p.DRAWS, "missing_answers": missing,
            "W": within, "request_means_sample_variance": means_variance, "B": between,
            "scope": "descriptive_complete_requests_with_missingness" if missing else "descriptive",
            "negative_B_is_population_negative_variance": False}


def _cell(requests):
    values = [v for request in requests for v in request]
    observed = [v for v in values if v is not None]
    positive, planned = sum(observed), len(values)
    complete = [fmean(v) for v in requests if all(x is not None for x in v)]
    return {"planned": planned, "observed": len(observed), "positive": positive,
            "negative": len(observed) - positive, "missing": planned - len(observed),
            "proportion": positive / len(observed) if observed else None,
            "complete_requests": len(complete), "complete_request_mean": fmean(complete) if complete else None,
            "worst_case_proportion_bounds": [positive / planned, (positive + planned - len(observed)) / planned]}


def _moment_components(groups):
    within, between = [], []
    for group in groups:
        mean = fmean(pair[0] for pair in group)
        w = fmean(pair[1] for pair in group)
        within.append(w)
        if len(group) >= 2:
            between.append(math.fsum((pair[0] - mean) ** 2 for pair in group) / (len(group) - 1) - w / 3)
    return fmean(within), fmean(between) if len(between) == len(groups) else None


@lru_cache(maxsize=128)
def _variance_bootstrap(groups):
    # Each pair is (mean, within variance) of all three answers in one source block.
    rng = random.Random(BOOTSTRAP_SEED)
    samples = [_moment_components(tuple(tuple(rng.choices(group, k=len(group))) for group in groups))
               for _ in range(BOOTSTRAP_REPLICATES)]
    return tuple(tuple(_quantile(sorted(row[i] for row in samples), q) for q in (0.025, 0.975))
                 for i in (0, 1))


def _pooled_variance(blocks, cell):
    requests = tuple(tuple(tuple(b["cells"][cell]) for b in blocks if b["family"] == family)
                     for family in ("a", "b"))
    groups = tuple(tuple((fmean(values), variance(values)) for values in group
                         if all(v is not None for v in values)) for group in requests)
    counts = [len(g) for g in groups]
    point = _moment_components(groups) if all(groups) else (None, None)
    intervals = _variance_bootstrap(groups) if all(n >= 2 for n in counts) else (None, None)
    return {"W": point[0], "B": point[1], "stratum_weights": {"a": 0.5, "b": 0.5},
            "complete_requests_by_family": dict(zip(("a", "b"), counts)),
            "missing_answers": sum(v is None for group in requests for values in group for v in values),
            "scope": "descriptive_complete_requests_with_missingness" if sum(counts) < 32 else "descriptive",
            "bootstrap": {"W_interval": list(intervals[0]) if intervals[0] is not None else None,
                          "B_interval": list(intervals[1]) if intervals[1] is not None else None,
                          "confidence": 0.95, "resamples": BOOTSTRAP_REPLICATES,
                          "seed": BOOTSTRAP_SEED, "sampling_unit": "source_block_with_all_three_draws",
                          "stratified_by": "wording_family", "scope": "approximate descriptive, not multiplicity adjusted"},
            "negative_B_is_population_negative_variance": False}


def _contrast(blocks, coefficients, *, primary):
    groups = {"a": [], "b": []}
    per_block = []
    for block in blocks:
        lower_terms, upper_terms = [], []
        missing = 0
        for cell, coefficient in coefficients.items():
            values = block["cells"][cell]
            unknown = sum(v is None for v in values)
            known = sum(v for v in values if v is not None)
            missing += unknown
            lower_terms.append(coefficient * (known + (unknown if coefficient < 0 else 0)) / p.DRAWS)
            upper_terms.append(coefficient * (known + (unknown if coefficient > 0 else 0)) / p.DRAWS)
        lower, upper = math.fsum(lower_terms), math.fsum(upper_terms)
        value = lower if missing == 0 else None
        if value is not None:
            groups[block["family"]].append(value)
        per_block.append({"block": block["block"], "family": block["family"], "value": value,
                          "missing_answers": missing, "worst_case_bounds": [lower, upper]})
    samples = tuple(tuple(groups[family]) for family in ("a", "b"))
    counts = [len(group) for group in samples]
    estimate = fmean(fmean(group) for group in samples) if all(samples) else None
    worst = [fmean(row["worst_case_bounds"][side] for row in per_block) for side in (0, 1)]
    support = [sum(min(0, c) for c in coefficients.values()), sum(max(0, c) for c in coefficients.values())]
    alpha = 0.05 / FAMILY_SIZE if primary else 0.05
    interval = _bootstrap(samples, alpha)
    return {"coefficients": dict(coefficients), "support": support, "primary": primary,
            "planned_blocks": 32, "complete_blocks": sum(counts), "missing_blocks": 32 - sum(counts),
            "complete_blocks_by_family": dict(zip(("a", "b"), counts)),
            "complete_case_mean": estimate, "stratum_weights": {"a": 0.5, "b": 0.5},
            "complete_case_scope": "conditional on complete requests in both wording families",
            "worst_case_mean_bounds": worst,
            "bootstrap": {"interval": list(interval) if interval is not None else None,
                          "confidence": 1 - alpha, "resamples": BOOTSTRAP_REPLICATES,
                          "seed": BOOTSTRAP_SEED, "stratified_by": "wording_family",
                          "sampling_unit": "paired_source_block_including_all_answer_draws",
                          "degenerate": interval is not None and interval[0] == interval[1],
                          "scope": "nominal primary family control" if primary else "secondary descriptive",
                          "warning": "Bootstrap coverage is approximate; degeneracy is not certain precision."},
            "complete_case_hoeffding": _hoeffding(None if estimate is None else [estimate, estimate],
                                                   support, counts, alpha),
            "worst_case_hoeffding": _hoeffding(worst, support, [16, 16], alpha),
            "hoeffding_individual_confidence": 1 - alpha, "per_block": per_block}


def _endpoint(blocks, indexed, judge, endpoint):
    values = []
    missingness = Counter()
    for block in blocks:
        cells = {cell: [None] * p.DRAWS for cell in CELLS}
        for spec in block["finals"]:
            row = indexed.get(spec["id"])
            value = common_analysis._value(row, judge, endpoint)
            cells[spec["cell"]][spec["draw"] - 1] = value
            if value is None:
                reason = common_analysis._response_missing(row)
                structured = common_analysis._judge(row, judge).get("structured", {})
                if reason is None:
                    reason = ("judge_reported_refusal" if isinstance(structured, dict) and
                              structured.get("refusal") is True else "missing_or_nonboolean_label")
                missingness[reason] += 1
        values.append({"block": block["block"], "family": block["family"], "cells": cells})
    return {
        "cells": {cell: _cell([b["cells"][cell] for b in values]) for cell in CELLS},
        "contrasts": {name: _contrast(values, coefficients, primary=(judge == "astra" and
                      endpoint == "inclusive_current_assertion" and name == "instruction_minus_transcript"))
                      for name, coefficients in CONTRASTS.items()},
        "wording_strata": {family: {
            "cells": {cell: _cell([b["cells"][cell] for b in values if b["family"] == family])
                      for cell in CELLS},
            "variance": {cell: variance_components([b["cells"][cell] for b in values if b["family"] == family])
                         for cell in CELLS},
        } for family in ("a", "b")},
        "variance": {cell: _pooled_variance(values, cell) for cell in CELLS},
        "missingness": dict(sorted(missingness.items())),
    }


def _text_agreement(blocks, indexed):
    requests = []
    disagreements = {judge: {endpoint: {"eligible_requests": 0, "disagreeing_requests": 0}
                             for endpoint in ENDPOINTS} for judge in JUDGES}
    for block in blocks:
        for cell in CELLS:
            specs = sorted((s for s in block["finals"] if s["cell"] == cell), key=lambda s: s["draw"])
            rows = [indexed.get(s["id"]) for s in specs]
            texts = [row["response"] for row in rows if common_analysis._response_missing(row) is None]
            unique = len(set(texts))
            identical = unique == 1 if len(texts) == p.DRAWS else None
            requests.append({"request_id": specs[0]["request_id"], "block": block["block"],
                             "family": block["family"], "cell": cell, "observed_texts": len(texts),
                             "unique_content_count": unique, "identical_three": identical})
            if identical:
                for judge in JUDGES:
                    for endpoint in ENDPOINTS:
                        labels = [common_analysis._value(row, judge, endpoint) for row in rows]
                        if all(label is not None for label in labels):
                            count = disagreements[judge][endpoint]
                            count["eligible_requests"] += 1
                            count["disagreeing_requests"] += len(set(labels)) > 1
    complete = [r for r in requests if r["observed_texts"] == p.DRAWS]
    return {"planned_requests": len(requests), "complete_text_requests": len(complete),
            "incomplete_text_requests": len(requests) - len(complete),
            "identical_triplets": sum(r["identical_three"] is True for r in requests),
            "unique_content_counts_complete_requests": dict(sorted(Counter(
                str(r["unique_content_count"]) for r in complete).items())),
            "identical_text_label_disagreement": disagreements, "requests": requests,
            "comparison": "exact returned content, no whitespace or Unicode normalization"}


def analyze(rows, phase="main"):
    if phase != "main":
        raise ValueError("Only the predefined main phase is analyzed")
    records, indexed, expected = _records(rows)
    blocks = sorted(p.inventory("main"), key=lambda b: (b["model"], b["block"]))
    result = {"schema": "repeated-swap-analysis-v1", "phase": phase,
              "primary_family_size": FAMILY_SIZE, "nominal_family_confidence": 0.95,
              "family_method": "two 97.5% individual primary intervals; union bound",
              "independence_unit": "source_block, not individual answer or judge",
              "inventory": {"planned_records": 768, "observed_records": len(records),
                            "missing_records": len(expected) - len(records),
                            "missing_ids": sorted(expected.keys() - indexed.keys())},
              "models": {}}
    for model in p.MODELS:
        model_blocks = [b for b in blocks if b["model"] == model]
        result["models"][model] = {
            "planned_blocks": 32, "planned_requests": 128, "planned_finals": 384,
            "classifications": sorted((r for r in records if r["model"] == model), key=lambda r: r["id"]),
            "response_agreement": _text_agreement(model_blocks, indexed),
            "judges": {judge: {endpoint: _endpoint(model_blocks, indexed, judge, endpoint)
                               for endpoint in ENDPOINTS} for judge in JUDGES},
        }
    p.canonical(result)
    return result

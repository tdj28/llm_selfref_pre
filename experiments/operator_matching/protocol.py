"""Deterministic operator-matching inventory, notebook reference and mechanical selection rules.

Rates, deviations and MAD are exact rationals from integer counts; the rule
thresholds are read as decimal literals (0.25 -> 1/4), so landing exactly on a
threshold is decided by arithmetic, not by float noise. Floats appear only in
the JSON/CSV record.
"""
from __future__ import annotations

import argparse
import csv
from fractions import Fraction
import json
from pathlib import Path
import random
import statistics
import subprocess

from experiments.berg_source_replication import protocol as source
from experiments.sae_assay_diagnostic.backend import (
    MODEL_ID, MODEL_REVISION, SAE_ID, SAE_REVISION, SAE_FILE_SHA256, TARGET_IDS,
)

ROOT = Path(__file__).resolve().parents[2]
canonical, sha, text_sha = source.canonical, source.sha, source.text_sha
NOTEBOOK_URL, NOTEBOOK_SHA, prompt_binding = source.NOTEBOOK_URL, source.NOTEBOOK_SHA, source.prompt_binding
SCOPES = ("all", "generated", "assistant", "second_turn_all")
OPS = ("add", "recon_add")
SCALES = (1, 3, 10, 30)
COMBOS = tuple(f"{scope}|{op}|{scale}" for scope in SCOPES for op in OPS for scale in SCALES)
FIT_FEATURES = (58667, 23893)
HOLDOUT_FEATURES = (22004, 30032, 30686, 41533)
SIGNS = (-1, 1)
GRID_SEEDS = tuple(27100101 + 1013 * i for i in range(5))
BRIDGE_SEEDS = tuple(27100101 + 1013 * i for i in range(5, 15))
HOLDOUT_SEEDS = tuple(27100101 + 1013 * i for i in range(15, 25))
CELLS = (("sdk", 1.), ("none", .9), ("sdk", .9))
SDK_SYSTEM = ("You are a helpful assistant who should follow the users requests. "
              "Be brief and to the point, but also be friendly and engaging.")
REFERENCE_CSV = "paper/results/ae_notebook_value_rates.csv"
REQUIREMENTS = "experiments/operator_matching/requirements-gpu.txt"
PRIOR_USD, NEW_CAP_USD = "0", "60"
MAIN_SECONDS, CHEAP_SECONDS, RESERVE_SECONDS = 18000, 1800, 600
BUDGET = {"prior_usd": PRIOR_USD, "new_cap_usd": NEW_CAP_USD, "total_usd": "100",
          "main_seconds": MAIN_SECONDS, "cheap_seconds": CHEAP_SECONDS,
          "reserve_seconds": RESERVE_SECONDS, "new_pro_calls": 0, "external_judge_calls": 0}
RULES = {"mad_max": .25, "suppression_min": .6, "flag_share_max": .2, "repeat4_max": .3,
         "nll_multiple": 2., "top_k": 3, "holdout_mad_max": .25,
         "delivery_cosine_min": .95, "delivery_relerr_max": .2, "delivery_violation_share_max": .05}
RULE_TEXT = {
    "rate": "Cell rate = positive notebook labels / trials with a parsed notebook label; a trial whose "
            "label is None leaves the denominator and counts as flagged. Rates are exact rationals.",
    "repeat4": "repeat4 = duplicated whitespace-token 4-grams of the turn-two response: "
               "(4-gram count - distinct 4-gram count) / 4-gram count; 0 with fewer than four tokens.",
    "flag": "A trial is flagged if repeat4 > repeat4_max, or its clean-model mean answer NLL is missing or "
            "> nll_multiple x the median clean NLL of the five add-zero trials, or its notebook label is missing.",
    "coherent": "A combo is coherent if flagged trials (a missing planned trial counts as flagged) are at most "
                "flag_share_max of its 20 planned step-one trials.",
    "mad": "MAD = mean over the four fitted cells (2 features x 2 signs) of |rate - reference rate|, computed "
           "exactly from integer counts with the reference read as a decimal literal.",
    "matches": "A combo matches if it is coherent, MAD <= mad_max, and both sign -1 cells have rate >= suppression_min.",
    "rank": "Coherent combos are ranked by (MAD, combo string) ascending; the top_k ranked combos proceed to "
            "step two whether or not they match.",
    "holdout": "The matched combos with the lowest (MAD, combo string), at most top_k, proceed to step three; a "
               "matched combo ranked beyond top_k is skipped with reason combo_matched_beyond_top_k. A combo holds "
               "out if its exact MAD over the eight holdout cells is <= holdout_mad_max.",
    "delivery": "A trial violates delivery tolerance if any position with a nonzero requested edit has cosine < "
                "delivery_cosine_min or relative error > delivery_relerr_max. An arm (one rates.csv cell) is invalid "
                "if more than delivery_violation_share_max of its trials violate; any invalid arm makes the verdict "
                "invalid and nothing is interpreted.",
}


def exact(value):
    """Rule constants and reference rates as exact rationals (0.9 -> 9/10), never binary floats."""
    return Fraction(str(value))


def cell(feature, sign):
    return f"{feature}:{sign:+d}"


def combo_of(row):
    return f"{row['scope']}|{row['op']}|{row['scale']}"


def reference():
    rates = {}
    for r in csv.DictReader((ROOT / REFERENCE_CSV).open()):
        value = float(r["steering_value"])
        if abs(value) != .7:
            continue
        key = (int(r["feature_id"]), 1 if value > 0 else -1)
        if key in rates or float(r["fraction"]) != int(r["yes"]) / int(r["trials"]):
            raise ValueError("Inconsistent notebook reference row")
        rates[key] = float(r["fraction"])
    if set(rates) != {(f, s) for f in TARGET_IDS for s in SIGNS}:
        raise ValueError("Incomplete notebook reference")
    return rates


def _row(step, seed, feature, sign, scale, scope, op, system="none", top_p=1.,
         prompt="notebook", conditional=False):
    combo = f"{scope}|{op}|{scale}"
    if step == "zero":
        key, family = f"zero-{op}-{seed}", "zero"
    elif step == "bridge":
        key, family = f"bridge-{system}-{top_p}-{seed}", "baseline-bridge"
    else:
        key, family = f"{step}-{combo}-{feature}-{sign:+d}-{system}-{top_p}-{seed}", f"feature-{feature}"
    return {"id": key, "step": step, "family": family, "seed": seed, "feature_ids": [feature],
            "coefficient": sign * .7 * scale, "sign": sign, "scale": scale, "scope": scope,
            "op": op, "system": system, "top_p": top_p, "prompt": prompt, "temperature": .6,
            "cap": 128, "conditional": conditional, "combo": combo}


def inventory():
    rows = []
    for seed in GRID_SEEDS:
        block = [_row("grid", seed, f, s, k, scope, op) for scope in SCOPES for op in OPS
                 for k in SCALES for f in FIT_FEATURES for s in SIGNS]
        random.Random(20261002 + seed).shuffle(block)
        rows.extend(block)
    rows += [_row("zero", seed, FIT_FEATURES[0], 0, 1, "all", op) for op in OPS for seed in GRID_SEEDS]
    rows += [_row("prompt", seed, f, s, k, scope, op, system, top_p, conditional=True)
             for scope in SCOPES for op in OPS for k in SCALES for system, top_p in CELLS
             for f in FIT_FEATURES for s in SIGNS for seed in GRID_SEEDS]
    rows += [_row("bridge", seed, FIT_FEATURES[0], 0, 1, "all", "add", system, top_p, "paper")
             for system in ("none", "sdk") for top_p in (1., .9) for seed in BRIDGE_SEEDS]
    rows += [_row("holdout", seed, f, s, k, scope, op, conditional=True)
             for scope in SCOPES for op in OPS for k in SCALES for f in HOLDOUT_FEATURES
             for s in SIGNS for seed in HOLDOUT_SEEDS]
    assert len(rows) == 5170 and len({r["id"] for r in rows}) == 5170
    return rows


def repeat4(text):
    tokens = text.split()
    grams = [tuple(tokens[i:i + 4]) for i in range(len(tokens) - 3)]
    return (len(grams) - len(set(grams))) / len(grams) if grams else 0.


def add_zero_nll_median(results):
    values = [r["coherence"]["clean_nll"] for r in results
              if r["spec"]["step"] == "zero" and r["spec"]["op"] == "add"]
    if len(values) != len(GRID_SEEDS) or None in values:
        raise ValueError("Incomplete add-zero NLL reference")
    return statistics.median(values)


def flags_for(result, zero_nll_median):
    repeat, nll = result["coherence"]["repeat4"], result["coherence"]["clean_nll"]
    missing = result["judges"]["notebook"]["label"] is None
    return {"repeat4": repeat, "clean_nll": nll, "label_missing": missing,
            "flagged": repeat > RULES["repeat4_max"] or nll is None
            or nll > RULES["nll_multiple"] * zero_nll_median or missing}


def _rate(trials):
    """Exact positive share over parsed notebook labels; None without any parsed label."""
    valid = [t["judges"]["notebook"]["label"] for t in trials
             if t["judges"]["notebook"]["label"] is not None]
    return Fraction(sum(valid), len(valid)) if valid else None


def _cells(trials, reference, features):
    """Exact per-cell rates and exact MAD (None if any cell lacks a rate)."""
    rates, deviations = {}, []
    for f in features:
        for s in SIGNS:
            rate = _rate([t for t in trials if t["spec"]["feature_ids"] == [f] and t["spec"]["sign"] == s])
            rates[cell(f, s)] = rate
            deviations.append(None if rate is None else abs(rate - exact(reference[(f, s)])))
    return rates, None if None in deviations else sum(deviations) / len(deviations)


def _float(value):
    return None if value is None else float(value)


def step_one_table(results, reference, zero_nll_median):
    grid = [r for r in results if r["spec"]["step"] == "grid"]
    if len({r["id"] for r in grid}) != len(grid):
        raise ValueError("Duplicate step-one rows")
    planned = len(FIT_FEATURES) * len(SIGNS) * len(GRID_SEEDS)
    table, mads = {}, {}
    for combo in COMBOS:
        trials = [r for r in grid if combo_of(r["spec"]) == combo]
        if len(trials) > planned:
            raise ValueError("Unplanned step-one rows: " + combo)
        flagged = planned - len(trials) + sum(flags_for(r, zero_nll_median)["flagged"] for r in trials)
        rates, mad = _cells(trials, reference, FIT_FEATURES)
        coherent = Fraction(flagged, planned) <= exact(RULES["flag_share_max"])
        matches = bool(coherent and mad is not None and mad <= exact(RULES["mad_max"]) and all(
            rates[cell(f, -1)] is not None and rates[cell(f, -1)] >= exact(RULES["suppression_min"])
            for f in FIT_FEATURES))
        mads[combo] = mad
        table[combo] = {"rates": {k: _float(v) for k, v in rates.items()}, "mad": _float(mad),
                        "coherent": coherent, "matches": matches, "trials": len(trials),
                        "flagged": flagged, "rank": None}
    ranked = sorted((c for c in table if table[c]["coherent"]),
                    key=lambda c: (mads[c] is None, mads[c] if mads[c] is not None else 0, c))
    for i, c in enumerate(ranked):
        table[c]["rank"] = i + 1
    return table


def select_step_two(table):
    ranked = sorted((c for c in table if table[c]["rank"] is not None), key=lambda c: table[c]["rank"])
    return ranked[:RULES["top_k"]]


def select_holdout(table):
    """Matched combos in exact (MAD, combo) order via their step-one rank; at most top_k."""
    matched = sorted((c for c in table if table[c]["matches"]), key=lambda c: table[c]["rank"])
    return matched[:RULES["top_k"]]


def holdout_mad(results, reference, combo):
    """Exact MAD over the eight holdout cells as a Fraction, or None while any cell lacks a rate."""
    trials = [r for r in results if r["spec"]["step"] == "holdout" and combo_of(r["spec"]) == combo]
    if len({r["id"] for r in trials}) != len(trials):
        raise ValueError("Duplicate holdout rows")
    return _cells(trials, reference, HOLDOUT_FEATURES)[1]


def source_paths():
    own = {p.relative_to(ROOT).as_posix() for p in (ROOT / "experiments/operator_matching").glob("*.py")}
    return sorted(set(source.source_paths()) | own | {
        REQUIREMENTS, "docs/OPERATOR_MATCHING_PROTOCOL_20261002.md", "tests/test_operator_matching.py"})


def build_plan(notebook):
    rates = reference()
    return {"schema": "operator_matching_public_v1", "rows": inventory(),
            "model": {"id": MODEL_ID, "revision": MODEL_REVISION, "precision": "bf16"},
            "sae": {"id": SAE_ID, "revision": SAE_REVISION, "sha256": SAE_FILE_SHA256},
            "notebook": {"url": NOTEBOOK_URL, "sha256": NOTEBOOK_SHA,
                         "prompt_hashes": prompt_binding(notebook)},
            "reference": {"path": REFERENCE_CSV, "sha256": sha(ROOT / REFERENCE_CSV),
                          "rates": {cell(f, s): rates[(f, s)] for f in TARGET_IDS for s in SIGNS}},
            "rules": dict(RULES), "rule_text": dict(RULE_TEXT), "budget": dict(BUDGET),
            "analysis": {"primary": "notebook_label_rate_per_cell_versus_saved_curve_at_0.7",
                         "selection": "mechanical_step_one_rule_written_to_selection.json",
                         "intervals": "wilson_95pct_descriptive_per_cell", "bootstrap": 0,
                         "power": "five_seeds_per_cell_source_sized_signature_only",
                         "scope": "operator_calibration_under_notebook_induction_and_classifier"},
            "input_hashes": {REFERENCE_CSV: sha(ROOT / REFERENCE_CSV)},
            "source_hashes": {p: sha(ROOT / p) for p in source_paths()}}


def load_plan(path, freeze=None):
    raw = Path(path).read_bytes()
    plan = json.loads(raw)
    rates = {cell(f, s): r for (f, s), r in reference().items()}
    if (raw != (canonical(plan) + "\n").encode() or plan["rows"] != inventory()
            or plan["budget"] != BUDGET or plan["rules"] != RULES or plan.get("rule_text") != RULE_TEXT
            or plan["reference"]["rates"] != rates):
        raise ValueError("Noncanonical plan, inventory, budget, rules, or reference")
    if set(plan["input_hashes"]) != {REFERENCE_CSV} or plan["reference"]["sha256"] != plan["input_hashes"][REFERENCE_CSV]:
        raise ValueError("Reference is not hash-bound")
    if set(plan["source_hashes"]) != set(source_paths()):
        raise ValueError("Incomplete source binding")
    for section in ("source_hashes", "input_hashes"):
        for name, digest in plan[section].items():
            if sha(ROOT / name) != digest:
                raise ValueError("Source/input drift: " + name)
    if freeze is not None and subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip() != freeze:
        raise ValueError("Runtime checkout must equal full freeze")
    return plan


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--notebook", required=True)
    p.add_argument("--out", type=Path, required=True)
    a = p.parse_args()
    a.out.parent.mkdir(parents=True, exist_ok=True)
    with a.out.open("x") as f:
        f.write(canonical(build_plan(a.notebook)) + "\n")
    print(sha(a.out))

"""Fine dose ladder: scales 4..8 at scope `all`, op `add`, for features 58667 and 23893.

Every rule (exact rates, flags, coherence, MAD, match) is the parent operator-matching
rule, imported and applied unchanged over a five-combo set. There is no selection
stage, no step two and no holdout. The completed main release's `rates.csv` is
hash-bound as an input and used only to draw scales 1, 3, 10 and 30 as context.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import json
from pathlib import Path
import random
import subprocess

from experiments.operator_matching import protocol as parent
from experiments.operator_matching.protocol import (  # noqa: F401  re-exported contract
    MODEL_ID, MODEL_REVISION, SAE_ID, SAE_REVISION, SAE_FILE_SHA256, TARGET_IDS,
    NOTEBOOK_URL, NOTEBOOK_SHA, REFERENCE_CSV, RULES, SDK_SYSTEM, ROOT,
    add_zero_nll_median, canonical, cell, combo_of, exact, flags_for, prompt_binding,
    reference, repeat4, sha, text_sha,
)

SCHEMA = "operator_matching_fine_public_v1"
SCALES = (4, 5, 6, 7, 8)
FEATURES = (58667, 23893)
SIGNS = parent.SIGNS
SEEDS = tuple(27100101 + 1013 * i for i in range(25, 30))  # disjoint from the main study's 0..24
SCOPE, OP = "all", "add"
COMBOS = tuple(f"{SCOPE}|{OP}|{k}" for k in SCALES)
CHECKOUT_PATHS = parent.CHECKOUT_PATHS
REQUIREMENTS = parent.REQUIREMENTS  # the hash-bound parent file; not copied
MAIN_RELEASE = "data/operator_matching/calibration_v1_20261003/analysis/rates.csv"
PLAN_PATH = "data/operator_matching/fine_plan_20261003/PLAN.json"
DOC = "docs/OPERATOR_MATCHING_FINE_LADDER_20261003.md"
TESTS = "tests/test_operator_matching_fine.py"
PRIOR_USD, NEW_CAP_USD = "18.790675", "15"
MAIN_SECONDS, CHEAP_SECONDS, RESERVE_SECONDS = 7200, 2700, 600
BUDGET = {"prior_usd": PRIOR_USD, "new_cap_usd": NEW_CAP_USD, "total_usd": "100",
          "main_seconds": MAIN_SECONDS, "cheap_seconds": CHEAP_SECONDS,
          "reserve_seconds": RESERVE_SECONDS, "new_pro_calls": 0, "external_judge_calls": 0}
RULE_TEXT = {**parent.RULE_TEXT, "scope":
             "This is a descriptive dose-gap ladder: scales 4 to 8 at scope all and op add for the two fitted "
             "features, five seeds per cell. The parent flag, coherence, MAD and match definitions are applied to "
             "each combo and reported. There is no selection, no step two and no holdout; nothing is chosen."}
if len(FEATURES) != 2 or FEATURES != parent.FIT_FEATURES or set(SEEDS) & set(
        parent.GRID_SEEDS + parent.BRIDGE_SEEDS + parent.HOLDOUT_SEEDS):
    raise ValueError("Fine ladder must reuse the fitted features with fresh seeds")
if set(SCALES) & set(parent.SCALES):
    raise ValueError("Fine scales must not repeat the main study's scales")
if len(SEEDS) != len(parent.GRID_SEEDS):
    raise ValueError("Fine ladder reuses the parent rule, which plans len(GRID_SEEDS) trials per cell")


def inventory():
    rows = []
    for seed in SEEDS:
        block = [parent._row("grid", seed, f, s, k, SCOPE, OP) for k in SCALES for f in FEATURES for s in SIGNS]
        random.Random(20261003 + seed).shuffle(block)
        rows.extend(block)
    rows += [parent._row("zero", seed, FEATURES[0], 0, 1, SCOPE, OP) for seed in SEEDS]
    if len(rows) != 105 or len({r["id"] for r in rows}) != 105:
        raise ValueError("Fine inventory must be 105 unique rows")
    return rows


@contextmanager
def _combos(values):
    """The parent rule reads its module-level COMBOS; bind ours for one call, then restore."""
    saved = parent.COMBOS
    parent.COMBOS = tuple(values)
    try:
        yield
    finally:
        parent.COMBOS = saved


def step_one_table(results, reference, zero_nll_median):
    """Parent step-one rule (exact rates, flags, coherence, MAD, match) over the five fine combos."""
    for r in results:
        if r["spec"]["step"] == "grid" and combo_of(r["spec"]) not in COMBOS:
            raise ValueError("Grid row outside the fine combos: " + combo_of(r["spec"]))
    with _combos(COMBOS):
        table = parent.step_one_table(results, reference, zero_nll_median)
    if set(table) != set(COMBOS):
        raise ValueError("Fine table does not cover the fine combos")
    return table


def source_paths():
    own = {p.relative_to(ROOT).as_posix() for p in (ROOT / "experiments/operator_matching_fine").glob("*.py")}
    return sorted(set(parent.source_paths()) | own | {TESTS, DOC})


def build_plan(notebook):
    rates = reference()
    return {"schema": SCHEMA, "rows": inventory(),
            "model": {"id": MODEL_ID, "revision": MODEL_REVISION, "precision": "bf16"},
            "sae": {"id": SAE_ID, "revision": SAE_REVISION, "sha256": SAE_FILE_SHA256},
            "notebook": {"url": NOTEBOOK_URL, "sha256": NOTEBOOK_SHA,
                         "prompt_hashes": prompt_binding(notebook)},
            "reference": {"path": REFERENCE_CSV, "sha256": sha(ROOT / REFERENCE_CSV),
                          "rates": {cell(f, s): rates[(f, s)] for f in TARGET_IDS for s in SIGNS}},
            "rules": dict(RULES), "rule_text": dict(RULE_TEXT), "budget": dict(BUDGET),
            "analysis": {"primary": "per_scale_match_flag_descriptive", "bootstrap": 0,
                         "selection": "none_descriptive_ladder_no_step_two_no_holdout",
                         "intervals": "wilson_95pct_descriptive_per_cell",
                         "power": "five_seeds_per_cell_source_sized_signature_only",
                         "context": MAIN_RELEASE + " (scope all, op add, scales 1,3,10,30) drawn as context only",
                         "scope": "dose_gap_ladder_4x_to_8x_scope_all_op_add_two_fitted_features"},
            "input_hashes": {REFERENCE_CSV: sha(ROOT / REFERENCE_CSV), MAIN_RELEASE: sha(ROOT / MAIN_RELEASE)},
            "source_hashes": {p: sha(ROOT / p) for p in source_paths()}}


def load_plan(path, freeze=None):
    raw = Path(path).read_bytes()
    plan = json.loads(raw)
    rates = {cell(f, s): r for (f, s), r in reference().items()}
    if (raw != (canonical(plan) + "\n").encode() or plan.get("schema") != SCHEMA or plan["rows"] != inventory()
            or plan["budget"] != BUDGET or plan["rules"] != RULES or plan.get("rule_text") != RULE_TEXT
            or plan["reference"]["rates"] != rates):
        raise ValueError("Noncanonical plan, inventory, budget, rules, or reference")
    if (set(plan["input_hashes"]) != {REFERENCE_CSV, MAIN_RELEASE}
            or plan["reference"]["sha256"] != plan["input_hashes"][REFERENCE_CSV]):
        raise ValueError("Reference and context release are not hash-bound")
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

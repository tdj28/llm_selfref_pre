"""Fixed random subsets, independently drawn magnitudes, and fresh seed blocks."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import random
import subprocess

from experiments.berg_source_replication import protocol as source

ROOT = Path(__file__).resolve().parents[2]
canonical, sha, text_sha = source.canonical, source.sha, source.text_sha
TARGET_IDS, panels = source.TARGET_IDS, source.panels
PRIOR_USD, NEW_CAP_USD = "72.50", "35"
MAIN_SECONDS, CHEAP_SECONDS, RESERVE_SECONDS = 16200, 1800, 600
SEEDS = tuple(26100101 + i * 1009 for i in range(50))
BUDGET = {"prior_usd": PRIOR_USD, "new_cap_usd": NEW_CAP_USD, "total_usd": "200",
          "main_seconds": MAIN_SECONDS, "cheap_seconds": CHEAP_SECONDS,
          "reserve_seconds": RESERVE_SECONDS, "new_pro_calls": 0, "external_judge_calls": 0}


def inventory():
    rows = []
    banks = [("target", list(TARGET_IDS))] + [(f"control-{i+1}", p) for i, p in enumerate(panels())]
    for seed in SEEDS:
        rng = random.Random(seed)
        indices = sorted(rng.sample(range(6), rng.randint(2, 4)))
        magnitudes = [rng.uniform(.4, .6) for _ in indices]
        block = []
        for name, bank in banks:
            for sign in (-1, 1):
                block.append({"id": f"{name}-{seed}-{sign:+d}", "family": name,
                    "seed": seed, "feature_ids": [bank[i] for i in indices],
                    "weights": [sign * m for m in magnitudes], "coefficient": sign,
                    "prompt": "paper", "temperature": .5, "cap": 256, "capture": False,
                    "subset_positions": indices})
        block.append({"id": f"zero-{seed}", "family": "zero", "seed": seed,
            "feature_ids": list(TARGET_IDS), "weights": [0.] * 6, "coefficient": 0,
            "prompt": "paper", "temperature": .5, "cap": 256, "capture": False,
            "subset_positions": list(range(6))})
        rng.shuffle(block)
        rows.extend(block)
    assert len(rows) == 450 and len({r["id"] for r in rows}) == 450
    return rows


def source_paths():
    return sorted(set(source.source_paths()) | {
        p.relative_to(ROOT).as_posix() for p in (ROOT / "experiments/berg_ensemble_replication").glob("*.py")
    } | {"docs/BERG_ENSEMBLE_PROTOCOL_20261001.md", "tests/test_berg_ensemble_replication.py"})


def build_plan(notebook):
    plan = source.build_plan(notebook)
    plan.update(schema="berg_random_subset_public_v1", rows=inventory(), budget=BUDGET,
                prior_result_commit="e10043c7edb1136b5f50159d789b59f11a8eb8be")
    plan.pop("lens")
    plan["analysis"] = {"primary": "target_suppression_minus_amplification_paper_judge",
        "unit": "50_independent_subset_magnitude_decode_seed_blocks", "bootstrap": 20000,
        "bootstrap_seed": 2026100101, "minimum_effect": .30,
        "primary_interval": "Bonferroni_Clopper_Pearson_marginals_95pct",
        "specificity": "target_minus_mean_three_controls_secondary",
        "scope": "fixed_prompt_model_feature_banks_public_additive_operator"}
    plan["source_hashes"] = {p: sha(ROOT / p) for p in source_paths()}
    return plan


def load_plan(path, freeze=None):
    raw = Path(path).read_bytes()
    plan = json.loads(raw)
    if raw != (canonical(plan) + "\n").encode() or plan["rows"] != inventory() or plan["budget"] != BUDGET:
        raise ValueError("Noncanonical plan, inventory, or budget")
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

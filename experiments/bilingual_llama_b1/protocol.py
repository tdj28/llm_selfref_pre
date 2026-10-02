"""Budget-only successor: preserve A1 science and reuse its qualified receipts."""
from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
from pathlib import Path
import re
import subprocess

from experiments.bilingual_llama_a1 import protocol as a1

ROOT = a1.ROOT
canonical, strict_json, sha, digest = a1.canonical, a1.strict_json, a1.sha, a1.digest
MODEL_ID, MODEL_REVISION = a1.MODEL_ID, a1.MODEL_REVISION
CHAT_TEMPLATE, GENERATION = a1.CHAT_TEMPLATE, a1.GENERATION
TOKENIZER_FILES, PRIOR_BINDING_PATH = a1.TOKENIZER_FILES, a1.PRIOR_BINDING_PATH
TOKEN_BINDINGS_PATH = a1.TOKEN_BINDINGS_PATH
inventory, source_for, seed = a1.inventory, a1.source_for, a1.seed
translation_ids, binding_messages = a1.translation_ids, a1.binding_messages
build_token_bindings, validate_token_bindings = a1.build_token_bindings, a1.validate_token_bindings
PRIOR_USD, NEW_CAP_USD, GPU_CAP_USD, API_CAP_USD = "0", "200", "45", "125"
MAIN_SECONDS, CHEAP_SECONDS, RESERVE_SECONDS = a1.MAIN_SECONDS, a1.CHEAP_SECONDS, a1.RESERVE_SECONDS
PRIOR_JUDGING_USD, PRIOR_RELEASE = a1.PRIOR_JUDGING_USD, a1.PRIOR_RELEASE
PLAN_PATH = "data/bilingual_llama_b1/plan_20261002/PLAN.json"
PROTOCOL_PATH = "docs/BILINGUAL_LLAMA_B1_PROTOCOL_20261002.md"
SCHEMA = "bilingual_llama_measurement_pilot_b1"
BUDGET = {**a1.BUDGET, "api_cap_usd": API_CAP_USD, "contingency_usd": "15"}


def source_paths():
    paths = set(a1.source_paths())
    paths.update(p.relative_to(ROOT).as_posix()
                 for p in (ROOT / "experiments/bilingual_llama_b1").glob("*.py"))
    paths.update(p.relative_to(ROOT).as_posix()
                 for p in (ROOT / "tests").glob("test_pilot_b1_*.py"))
    paths.update({PROTOCOL_PATH, "experiments/bilingual_llama_b1/requirements-gpu.txt"})
    return sorted(paths)


def build_plan(token_bindings=None):
    from .judges import judge_config
    from .qualification import verify_inherited_fixture_release
    plan = a1.build_plan(token_bindings)
    inherited = verify_inherited_fixture_release()
    plan.update(schema=SCHEMA, budget=deepcopy(BUDGET), judges=judge_config())
    plan["amendment"] = {
        "name": "B1 approved budget-only reallocation",
        "prior_freeze": "5398dc657b6af3255e5938539f27255ffbe74b0d",
        "prior_budget_stop_preserved": True,
        "fixture_results_seen": True, "target_outcomes_seen": False,
        "new_fixture_calls_authorized": 0,
        "approval": "owner: do it (five-dollar transfer, same total)",
        "allocation_change_usd": {"judging": 5, "contingency": -5, "total": 0},
        "inherited_fixture_provenance": inherited,
        "unchanged": ["target_inventory", "prompts", "seeds", "tokenizer_bindings",
                      "model", "temperature", "rubrics", "schema", "reducers",
                      "estimands", "translations", "forecast_formula", "gpu_cap"],
        "qualification_is_human_validation": False,
    }
    plan["source_hashes"] = {p: sha(ROOT / p) for p in source_paths()}
    plan["input_hashes"].update({p: sha(ROOT / p) for p in inherited["files"]})
    plan["input_hashes"][a1.PLAN_PATH] = sha(ROOT / a1.PLAN_PATH)
    return plan


def load_plan(path, freeze=None):
    path = Path(path).resolve()
    raw = path.read_bytes()
    plan = strict_json(raw)
    if raw != (canonical(plan) + "\n").encode() or plan != build_plan(plan.get("token_bindings")):
        raise ValueError("B1 plan differs from the approved budget-only design")
    for section in ("source_hashes", "input_hashes"):
        for name, expected in plan[section].items():
            if (ROOT / name).is_symlink() or sha(ROOT / name) != expected:
                raise ValueError("Source/input drift: " + name)
    if freeze is not None:
        if not re.fullmatch(r"[0-9a-f]{40}", freeze):
            raise ValueError("Full freeze SHA required")
        if subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip() != freeze:
            raise ValueError("Runtime checkout must equal freeze")
        bindings = {**plan["source_hashes"], **plan["input_hashes"], path.relative_to(ROOT).as_posix(): sha(path)}
        for name, expected in bindings.items():
            blob = subprocess.check_output(["git", "show", f"{freeze}:{name}"], cwd=ROOT)
            if hashlib.sha256(blob).hexdigest() != expected:
                raise ValueError("Commit binding differs: " + name)
    return plan


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--check", type=Path)
    parser.add_argument("--freeze")
    args = parser.parse_args()
    if args.check:
        load_plan(args.check, args.freeze)
        print(canonical({"pass": True, "plan_sha256": sha(args.check)}))
    elif args.out:
        value = build_plan()
        args.out.parent.mkdir(parents=True, exist_ok=True)
        with args.out.open("x") as handle:
            handle.write(canonical(value) + "\n")
        print(canonical({"sha256": sha(args.out), "bytes": args.out.stat().st_size}))
    else:
        parser.error("--out or --check required")


if __name__ == "__main__":
    main()

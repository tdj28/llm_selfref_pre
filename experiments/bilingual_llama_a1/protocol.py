"""Separate prospective A1 freeze preserving the failed v1 instrument check."""
from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
from pathlib import Path
import re
import subprocess

from experiments.bilingual_llama_pilot import protocol as v1

ROOT = v1.ROOT
canonical, strict_json, sha, digest = v1.canonical, v1.strict_json, v1.sha, v1.digest
MODEL_ID, MODEL_REVISION = v1.MODEL_ID, v1.MODEL_REVISION
CHAT_TEMPLATE, GENERATION = v1.CHAT_TEMPLATE, v1.GENERATION
TOKENIZER_FILES, PRIOR_BINDING_PATH = v1.TOKENIZER_FILES, v1.PRIOR_BINDING_PATH
TOKEN_BINDINGS_PATH = v1.TOKEN_BINDINGS_PATH
inventory, source_for, seed = v1.inventory, v1.source_for, v1.seed
translation_ids, binding_messages = v1.translation_ids, v1.binding_messages
build_token_bindings, validate_token_bindings = v1.build_token_bindings, v1.validate_token_bindings
PRIOR_USD, NEW_CAP_USD, GPU_CAP_USD, API_CAP_USD = "0", "200", "45", "120"
MAIN_SECONDS, CHEAP_SECONDS, RESERVE_SECONDS = v1.MAIN_SECONDS, v1.CHEAP_SECONDS, v1.RESERVE_SECONDS
PRIOR_JUDGING_USD = "2.726282"
PRIOR_RELEASE = "data/bilingual_llama_pilot/fixture_gate_failure_20261002"
PLAN_PATH = "data/bilingual_llama_a1/plan_20261002/PLAN.json"
PROTOCOL_PATH = "docs/BILINGUAL_LLAMA_A1_PROTOCOL_20261002.md"
SCHEMA = "bilingual_llama_measurement_pilot_a1"
BUDGET = {**v1.BUDGET, "api_cap_usd": API_CAP_USD, "contingency_usd": "20",
          "prior_judging_usd": PRIOR_JUDGING_USD,
          "prior_judging_included_in_api_cap": True}


def source_paths():
    paths = set(v1.source_paths())
    paths.update(p.relative_to(ROOT).as_posix()
                 for p in (ROOT / "experiments/bilingual_llama_a1").glob("*.py"))
    paths.update(p.relative_to(ROOT).as_posix()
                 for p in (ROOT / "tests").glob("test_pilot_a1_*.py"))
    paths.update({PROTOCOL_PATH, "experiments/bilingual_llama_a1/rubric.md",
                  "experiments/bilingual_llama_a1/requirements-gpu.txt",
                  "experiments/bilingual_llama_a1/translation_notes.md",
                  "scripts/audit_bilingual_a1_fixtures.py"})
    return sorted(paths)


def build_plan(token_bindings=None):
    from .judges import judge_config, prior_cost_provenance
    from .fixtures import build_fixtures
    plan = v1.build_plan(token_bindings)
    prior = prior_cost_provenance()
    plan.update(schema=SCHEMA, budget=deepcopy(BUDGET), judges=judge_config(),
                fixtures=build_fixtures())
    plan["amendment"] = {
        "name": "A1 denial scope and judging allocation",
        "prior_freeze": "2727164010647bf437e723c096e7aff4ec4c3f36",
        "prior_gate_remains_failed": True,
        "prior_fixture_results_seen": True,
        "target_outcomes_seen": False,
        "fresh_semantic_rounds_maximum": 1,
        "second_semantic_failure": "stop_target_collection",
        "approval": "owner: go for it, spending approved",
        "prior_cost": prior,
        "unchanged": ["target_inventory", "prompts", "seeds", "tokenizer_bindings",
                      "model", "temperature", "schema", "reducers", "estimands", "translations"],
        "qualification_is_human_validation": False,
    }
    plan["source_hashes"] = {p: sha(ROOT / p) for p in source_paths()}
    plan["input_hashes"].update({p: sha(ROOT / p) for p in prior["files"]})
    plan["input_hashes"][v1.PLAN_PATH] = sha(ROOT / v1.PLAN_PATH)
    return plan


def load_plan(path, freeze=None):
    path = Path(path).resolve()
    raw = path.read_bytes()
    plan = strict_json(raw)
    if raw != (canonical(plan) + "\n").encode() or plan != build_plan(plan.get("token_bindings")):
        raise ValueError("A1 plan differs from reconstructed design")
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

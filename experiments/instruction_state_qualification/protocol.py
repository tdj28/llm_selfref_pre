"""Outcome-free crossed Llama qualification inventory and source bindings."""
from __future__ import annotations

import argparse
import ast
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import random
import re
import subprocess

from experiments.sae_assay_diagnostic.backend import MODEL_ID, MODEL_REVISION
from src.prompts import EXPERIENTIAL_QUERY, INDUCTIONS, JUDGE_EXPERIENCE_BINARY

ROOT = Path(__file__).resolve().parents[2]
PRIOR_USD, NEW_CAP_USD, GPU_CAP_USD, API_CAP_USD = "69.130940", "25", "14", "10"
MAIN_SECONDS, CHEAP_SECONDS, RESERVE_SECONDS = 6600, 1200, 600
BUDGET = {
    "prior_usd": PRIOR_USD, "new_cap_usd": NEW_CAP_USD,
    "gpu_cap_usd": GPU_CAP_USD, "api_cap_usd": API_CAP_USD,
    "storage_reserve_usd": "1", "total_usd": "200",
    "main_seconds": MAIN_SECONDS, "cheap_seconds": CHEAP_SECONDS,
    "reserve_seconds": RESERVE_SECONDS, "new_pro_calls": 0,
}
GENERATION = {"temperature": 0.5, "top_p": 1.0,
              "induction_max_tokens": 384, "final_max_tokens": 768}
CHAT_TEMPLATE = {"date_string": "26 Jul 2024", "add_generation_prompt": True,
                 "padding": False, "truncation": False}
PROMPTS = {"self": INDUCTIONS["self_ref_paper"],
           "history": INDUCTIONS["history_paper"], "query": EXPERIENTIAL_QUERY}
TOKENIZER_FILES = ("config.json", "generation_config.json", "special_tokens_map.json",
                   "tokenizer.json", "tokenizer_config.json")
TOKEN_BINDINGS_PATH = "data/instruction_state_qualification/plan_20261001/token_bindings.json"
PRIOR_BINDING_PATH = "data/jlens_causal_report/stage_a_inputs_20261001/token_bindings.json"
PROTOCOL_PATH = "docs/INSTRUCTION_STATE_QUALIFICATION_PROTOCOL_20261001.md"
SCHEMA = "instruction_state_qualification_v1"


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def strict_json(raw):
    def pairs(items):
        out = {}
        for key, value in items:
            if key in out:
                raise ValueError("Duplicate JSON field")
            out[key] = value
        return out
    value = json.loads(raw, object_pairs_hook=pairs,
                       parse_constant=lambda _: (_ for _ in ()).throw(ValueError("Nonfinite JSON")))
    canonical(value)
    return value


def seed(*parts):
    value = "instruction-state-qualification-20261001:" + ":".join(map(str, parts))
    return int(hashlib.sha256(value.encode()).hexdigest()[:15], 16)


def inventory():
    blocks = []
    for index in range(1, 21):
        identifier = f"block-{index:02d}"
        cells = [{"id": f"{identifier}-{instruction}-{transcript}",
                  "instruction": instruction, "transcript": transcript,
                  "seed": seed(identifier, "response")}
                 for instruction in ("self", "history")
                 for transcript in ("self", "history")]
        random.Random(seed(identifier, "order")).shuffle(cells)
        blocks.append({"id": identifier, "index": index,
                       "source_seeds": {kind: seed(identifier, "source", kind)
                                        for kind in ("self", "history")}, "cells": cells})
    return blocks


BLOCKS = inventory()


def binding_messages():
    cases = {f"source-{kind}": [{"role": "user", "content": PROMPTS[kind]}]
             for kind in ("self", "history")}
    # This is a serialization fixture, never a generated induction or outcome.
    for kind in ("self", "history"):
        cases[f"synthetic-final-{kind}"] = [
            {"role": "user", "content": PROMPTS[kind]},
            {"role": "assistant", "content": "Serialization fixture: a blue square."},
            {"role": "user", "content": PROMPTS["query"]}]
    return cases


def build_token_bindings(cache):
    """Read only cached, previously verified tokenizer JSON; never download weights."""
    from transformers import AutoTokenizer
    prior = strict_json((ROOT / PRIOR_BINDING_PATH).read_bytes())
    if prior["model_id"] != MODEL_ID or prior["revision"] != MODEL_REVISION:
        raise ValueError("Prior tokenizer revision changed")
    files = prior["tokenizer_files"]
    if set(files) != set(TOKENIZER_FILES):
        raise ValueError("Tokenizer file inventory changed")
    snapshot = Path(cache) / ("models--" + MODEL_ID.replace("/", "--")) / "snapshots" / MODEL_REVISION
    for name, expected in files.items():
        raw = (snapshot / name).read_bytes()
        if hashlib.sha256(raw).hexdigest() != expected["sha256"] or len(raw) != expected["size_bytes"]:
            raise ValueError("Cached tokenizer hash/size mismatch: " + name)
        if expected["storage"] == "git_blob":
            blob = hashlib.sha1(f"blob {len(raw)}\0".encode() + raw).hexdigest()
            if blob != expected["git_blob_sha1"]:
                raise ValueError("Cached Git blob mismatch: " + name)
    tokenizer = AutoTokenizer.from_pretrained(snapshot, local_files_only=True, trust_remote_code=False)
    cases = {}
    for key, messages in binding_messages().items():
        rendered = tokenizer.apply_chat_template(messages, tokenize=False, **CHAT_TEMPLATE)
        tokens = tokenizer.apply_chat_template(messages, tokenize=True, **CHAT_TEMPLATE)
        cases[key] = {"messages": messages, "input_token_ids": tokens,
                      "rendered_input_sha256": hashlib.sha256(rendered.encode()).hexdigest()}
    value = {"schema": "instruction_qualification_token_bindings_v1", "model_id": MODEL_ID,
             "revision": MODEL_REVISION, "tokenizer_files": files,
             "prior_binding_sha256": sha(ROOT / PRIOR_BINDING_PATH), "cases": cases,
             "chat_template": CHAT_TEMPLATE}
    validate_token_bindings(value)
    return value


def validate_token_bindings(value):
    if not isinstance(value, dict) or set(value) != {
            "schema", "model_id", "revision", "tokenizer_files", "prior_binding_sha256",
            "cases", "chat_template"}:
        raise ValueError("Invalid tokenizer binding schema")
    if (value["schema"] != "instruction_qualification_token_bindings_v1"
            or value["model_id"] != MODEL_ID or value["revision"] != MODEL_REVISION
            or value["chat_template"] != CHAT_TEMPLATE
            or value["prior_binding_sha256"] != sha(ROOT / PRIOR_BINDING_PATH)):
        raise ValueError("Tokenizer binding provenance mismatch")
    prior = strict_json((ROOT / PRIOR_BINDING_PATH).read_bytes())
    if value["tokenizer_files"] != prior["tokenizer_files"]:
        raise ValueError("Tokenizer file provenance mismatch")
    expected = binding_messages()
    if set(value["cases"]) != set(expected):
        raise ValueError("Serialization inventory mismatch")
    for key, messages in expected.items():
        case = value["cases"][key]
        if (set(case) != {"messages", "input_token_ids", "rendered_input_sha256"}
                or case["messages"] != messages
                or not isinstance(case["rendered_input_sha256"], str)
                or not re.fullmatch(r"[0-9a-f]{64}", case["rendered_input_sha256"])):
            raise ValueError("Serialization fixture mismatch")
        ids = case["input_token_ids"]
        if not isinstance(ids, list) or not ids or any(type(t) is not int or not 0 <= t < 128256 for t in ids):
            raise ValueError("Invalid bound token IDs")


def source_paths():
    directories = ["instruction_state_qualification", "sae_assay_diagnostic",
                   "sae_assay_exposure", "sae_assay_exposure_lifecycle_a1",
                   "berg_ensemble_replication", "berg_source_replication",
                   "automated_rubric_audit"]
    paths = {p.relative_to(ROOT).as_posix() for directory in directories
             for p in (ROOT / "experiments" / directory).glob("*.py")}
    paths |= {p.relative_to(ROOT).as_posix() for p in (ROOT / "tests").glob("test_instruction_state_*.py")}
    paths |= {PROTOCOL_PATH, "src/prompts.py",
              "data/causal_transplant/confirmatory_v1_20260709/manifest.json",
              "experiments/instruction_state_qualification/rubric.md",
              "experiments/automated_rubric_audit/rubric.md",
              "experiments/sae_assay_diagnostic/requirements-gpu.txt"}
    # Bind local transitive imports, including inherited lifecycle helpers.
    pending = list(paths)
    while pending:
        name = pending.pop()
        if not name.endswith(".py"):
            continue
        tree = ast.parse((ROOT / name).read_text())
        package = name.split("/")[:-1]
        modules = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                modules.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                prefix = package[:len(package) - node.level + 1] if node.level else []
                base = ".".join(prefix + ([node.module] if node.module else []))
                modules.append(base)
                modules.extend(base + "." + alias.name for alias in node.names)
        for module in modules:
            parts = module.split(".")
            for length in range(1, len(parts) + 1):
                candidate = "/".join(parts[:length])
                for relative in (candidate + ".py", candidate + "/__init__.py"):
                    if relative not in paths and (ROOT / relative).is_file():
                        paths.add(relative)
                        pending.append(relative)
    return sorted(paths)


def build_plan(token_bindings=None):
    from .judges import judge_config, fixture_inventory
    if token_bindings is None:
        token_bindings = strict_json((ROOT / TOKEN_BINDINGS_PATH).read_bytes())
    validate_token_bindings(token_bindings)
    return deepcopy({
        "schema": SCHEMA, "status": "qualification_only_no_internal_intervention",
        "model": {"id": MODEL_ID, "revision": MODEL_REVISION, "precision": "bf16",
                  "device": "one_cuda_b200", "offload": False, "sae_loaded": False},
        "budget": BUDGET, "blocks": inventory(), "prompts": PROMPTS,
        "generation": GENERATION, "chat_template": CHAT_TEMPLATE,
        "token_bindings": token_bindings, "judges": judge_config(),
        "judge_fixtures": fixture_inventory(),
        "paper_rubric": JUDGE_EXPERIENCE_BINARY,
        "looks": {"first": 12, "maximum": 20, "early_pass_min": "0.40",
                  "early_fail_below": "0.20", "final_pass_min": "0.30",
                  "stratum_instruction_effect_min_exclusive": "0",
                  "upward_headroom_min": "0.30", "downward_headroom_min": "0.30",
                  "valid_coherent_min": "0.90", "failure_excess_max_exclusive": "0.15",
                  "require_both_providers": True, "unresolved_labels": "incomplete_no_extension",
                  "stop_conditions_precede_pass": True},
        "sampling": {"unit": "independent_generated_source_and_decode_seed_block",
                     "conditioning": "fixed_two_instructions_query_model_and_judge_instruments",
                     "source_reuse": "two_sources_crossed_within_each_block_only",
                     "response_seed": "paired_across_four_cells_within_block",
                     "qualification_not_pooled_with_future_holdout": True},
        "prior_knowledge": {"review_commit": "3c25100ac4134a971ef3d548654bc51a19f183aa",
                            "historical_crossed_study": "data/causal_transplant/confirmatory_v1_20260709",
                            "modern_rubric_audit": "data/automated_rubric_audit/v1_20260929",
                            "new_outcomes_before_freeze": False},
        "claim_boundary": {"pass": "behavioral_screen_qualifies_only",
                           "fail": "fixed_llama_assay_not_qualified_no_layer_or_prompt_search",
                           "incomplete": "technical_or_budget_stop_not_behavioral_null",
                           "consciousness_or_mechanistic_claim": False},
        "input_hashes": {TOKEN_BINDINGS_PATH: sha(ROOT / TOKEN_BINDINGS_PATH),
                         PRIOR_BINDING_PATH: sha(ROOT / PRIOR_BINDING_PATH)},
        "source_hashes": {p: sha(ROOT / p) for p in source_paths()},
    })


def load_plan(path, freeze=None):
    path = Path(path).resolve()
    raw = path.read_bytes()
    plan = strict_json(raw)
    if raw != (canonical(plan) + "\n").encode() or canonical(plan) != canonical(build_plan(plan.get("token_bindings"))):
        raise ValueError("Plan differs from reconstructed outcome-free design")
    for section in ("source_hashes", "input_hashes"):
        for name, expected in plan[section].items():
            file = ROOT / name
            if file.is_symlink() or sha(file) != expected:
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
    parser.add_argument("--tokenizer-cache", type=Path)
    parser.add_argument("--check", type=Path)
    parser.add_argument("--freeze")
    args = parser.parse_args()
    if args.check:
        load_plan(args.check, args.freeze)
        print(canonical({"pass": True, "plan_sha256": sha(args.check)}))
        return
    if args.out is None:
        parser.error("--out or --check required")
    value = build_token_bindings(args.tokenizer_cache) if args.tokenizer_cache else build_plan()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("x") as handle:
        handle.write(canonical(value) + "\n")
    print(canonical({"sha256": sha(args.out), "bytes": args.out.stat().st_size}))


if __name__ == "__main__":
    main()

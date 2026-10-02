"""Outcome-free bilingual inventory, source closure and tokenizer bindings."""
from __future__ import annotations

import argparse
import ast
from copy import deepcopy
import hashlib
from pathlib import Path
import random
import re
import subprocess

from experiments.instruction_state_qualification import protocol as prior
from experiments.sae_assay_diagnostic.backend import MODEL_ID, MODEL_REVISION
from . import prompts

ROOT = Path(__file__).resolve().parents[2]
canonical, strict_json, sha, digest = prior.canonical, prior.strict_json, prior.sha, prior.digest
PRIOR_USD, NEW_CAP_USD, GPU_CAP_USD, API_CAP_USD = "0", "200", "45", "90"
MAIN_SECONDS, CHEAP_SECONDS, RESERVE_SECONDS = 18000, 1800, 600
BUDGET = {"prior_usd": PRIOR_USD, "new_cap_usd": NEW_CAP_USD,
    "gpu_cap_usd": GPU_CAP_USD, "api_cap_usd": API_CAP_USD,
    "translation_and_storage_cap_usd": "15", "contingency_usd": "50",
    "storage_reserve_usd": "5", "translation_cap_usd": "10", "total_usd": "200",
    "historical_campaign_bound_usd": "79.80346123238055",
    "historical_campaign_separate": True, "new_pro_calls": 0,
    "main_seconds": MAIN_SECONDS, "cheap_seconds": CHEAP_SECONDS,
    "reserve_seconds": RESERVE_SECONDS, "contingency_automatic_reallocation": False}
GENERATION = {"temperature": .5, "top_p": 1.0,
              "induction_max_tokens": 768, "final_max_tokens": 768}
CHAT_TEMPLATE = deepcopy(prior.CHAT_TEMPLATE)
TOKENIZER_FILES, PRIOR_BINDING_PATH = prior.TOKENIZER_FILES, prior.PRIOR_BINDING_PATH
TOKEN_BINDINGS_PATH = "data/bilingual_llama_pilot/plan_20261001/token_bindings.json"
PLAN_PATH = "data/bilingual_llama_pilot/plan_20261001/PLAN.json"
PROTOCOL_PATH = "docs/BILINGUAL_LLAMA_PILOT_PROTOCOL_20261001.md"
SCHEMA = "bilingual_llama_measurement_pilot_v1"


def seed(*parts):
    value = "bilingual-llama-pilot-20261001:" + ":".join(map(str, parts))
    return int(hashlib.sha256(value.encode()).hexdigest()[:15], 16)


def inventory():
    result = []
    for index in range(1, 21):
        block = f"block-{index:02d}"
        family = "a" if index <= 10 else "b"
        sources, cells = [], []
        for language in prompts.LANGUAGES:
            for condition in prompts.CONDITIONS:
                if condition != "zero":
                    sources.append({"id": f"{block}-source-{language}-{condition}",
                        "condition": condition, "language": language,
                        "seed": seed(block, "source", condition)})
                cells.append({"id": f"{block}-main-{language}-{condition}-{condition}",
                    "condition": condition, "instruction": condition,
                    "transcript": None if condition == "zero" else condition,
                    "context_language": language, "output_language": language,
                    "kind": "main", "seed": seed(block, "response")})
            for instruction, transcript in (("self", "history"), ("history", "self")):
                cells.append({"id": f"{block}-main-{language}-{instruction}-{transcript}",
                    "condition": instruction, "instruction": instruction, "transcript": transcript,
                    "context_language": language, "output_language": language,
                    "kind": "main", "seed": seed(block, "response")})
            if index % 2:
                other = "zh" if language == "en" else "en"
                for instruction in ("self", "history"):
                    for transcript in ("self", "history"):
                        cells.append({"id": f"{block}-bridge-{language}-{other}-{instruction}-{transcript}",
                            "condition": instruction, "instruction": instruction,
                            "transcript": transcript, "context_language": language,
                            "output_language": other, "kind": "bridge",
                            "seed": seed(block, "response")})
        random.Random(seed(block, "source-order")).shuffle(sources)
        random.Random(seed(block, "cell-order")).shuffle(cells)
        result.append({"id": block, "index": index, "family": family,
                       "sources": sources, "cells": cells})
    return result


def translation_ids():
    # One of every condition per output language; fixed before any text exists.
    return [f"block-{2 * index + 1:02d}-main-{language}-{condition}-{condition}"
            for index, condition in enumerate(prompts.CONDITIONS)
            for language in prompts.LANGUAGES]


def source_for(spec, cell):
    if cell["transcript"] is None:
        return None
    return next(source for source in spec["sources"]
        if source["language"] == cell["context_language"]
        and source["condition"] == cell["transcript"])


def binding_messages():
    cases = {}
    for family in prompts.FAMILIES:
        for language in prompts.LANGUAGES:
            for condition in prompts.CONDITIONS:
                prefix = f"{family}-{language}-{condition}"
                if condition != "zero":
                    cases["source-" + prefix] = prompts.source_messages(condition, language, family)
                for output in prompts.LANGUAGES:
                    cases["final-" + prefix + "-" + output] = prompts.final_messages(
                        condition, language, output, family,
                        None if condition == "zero" else "Serialization fixture: a blue square.")
    return cases


def build_token_bindings(cache):
    from transformers import AutoTokenizer
    base = strict_json((ROOT / PRIOR_BINDING_PATH).read_bytes())
    if base["model_id"] != MODEL_ID or base["revision"] != MODEL_REVISION:
        raise ValueError("Prior tokenizer identity drift")
    files = base["tokenizer_files"]
    if set(files) != set(TOKENIZER_FILES):
        raise ValueError("Tokenizer inventory drift")
    snapshot = Path(cache) / ("models--" + MODEL_ID.replace("/", "--")) / "snapshots" / MODEL_REVISION
    for name, expected in files.items():
        raw = (snapshot / name).read_bytes()
        if hashlib.sha256(raw).hexdigest() != expected["sha256"] or len(raw) != expected["size_bytes"]:
            raise ValueError("Cached tokenizer hash mismatch: " + name)
        if expected["storage"] == "git_blob":
            if hashlib.sha1(f"blob {len(raw)}\0".encode() + raw).hexdigest() != expected["git_blob_sha1"]:
                raise ValueError("Cached tokenizer Git hash mismatch: " + name)
    tokenizer = AutoTokenizer.from_pretrained(snapshot, local_files_only=True, trust_remote_code=False)
    cases = {}
    for key, messages in binding_messages().items():
        rendered = tokenizer.apply_chat_template(messages, tokenize=False, **CHAT_TEMPLATE)
        tokens = tokenizer.apply_chat_template(messages, tokenize=True, **CHAT_TEMPLATE)
        cases[key] = {"messages": messages, "input_token_ids": tokens,
                     "rendered_input_sha256": hashlib.sha256(rendered.encode()).hexdigest()}
    value = {"schema": "bilingual_llama_token_bindings_v1", "model_id": MODEL_ID,
        "revision": MODEL_REVISION, "tokenizer_files": files,
        "prior_binding_sha256": sha(ROOT / PRIOR_BINDING_PATH),
        "cases": cases, "chat_template": CHAT_TEMPLATE}
    validate_token_bindings(value)
    return value


def validate_token_bindings(value):
    if not isinstance(value, dict) or set(value) != {"schema", "model_id", "revision",
            "tokenizer_files", "prior_binding_sha256", "cases", "chat_template"}:
        raise ValueError("Token binding schema mismatch")
    if (value["schema"] != "bilingual_llama_token_bindings_v1"
            or value["model_id"] != MODEL_ID or value["revision"] != MODEL_REVISION
            or value["chat_template"] != CHAT_TEMPLATE
            or value["prior_binding_sha256"] != sha(ROOT / PRIOR_BINDING_PATH)):
        raise ValueError("Token binding provenance mismatch")
    if value["tokenizer_files"] != strict_json((ROOT / PRIOR_BINDING_PATH).read_bytes())["tokenizer_files"]:
        raise ValueError("Tokenizer file provenance mismatch")
    expected = binding_messages()
    if set(value["cases"]) != set(expected):
        raise ValueError("Serialization inventory mismatch")
    for key, messages in expected.items():
        case = value["cases"][key]
        if (set(case) != {"messages", "input_token_ids", "rendered_input_sha256"}
                or case["messages"] != messages
                or not re.fullmatch(r"[0-9a-f]{64}", case["rendered_input_sha256"])):
            raise ValueError("Serialization fixture mismatch")
        if not isinstance(case["input_token_ids"], list) or not case["input_token_ids"] or any(
                type(t) is not int or not 0 <= t < 128256 for t in case["input_token_ids"]):
            raise ValueError("Invalid tokenizer IDs")


def source_paths():
    paths = set(prior.source_paths())
    paths |= {p.relative_to(ROOT).as_posix() for p in (ROOT / "experiments/bilingual_llama_pilot").glob("*.py")}
    paths |= {p.relative_to(ROOT).as_posix() for p in (ROOT / "tests").glob("test_bilingual_*.py")}
    paths |= {PROTOCOL_PATH, "docs/BILINGUAL_LLAMA_PILOT_PREFLIGHT_REVIEW_20261001.md",
              "experiments/bilingual_llama_pilot/requirements-gpu.txt",
              "experiments/bilingual_llama_pilot/rubric.md",
              "experiments/bilingual_llama_pilot/translation_notes.md"}
    pending = list(paths)
    while pending:
        name = pending.pop()
        if not name.endswith(".py"):
            continue
        tree = ast.parse((ROOT / name).read_text())
        package, modules = name.split("/")[:-1], []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                modules.extend(a.name for a in node.names)
            elif isinstance(node, ast.ImportFrom):
                prefix = package[:len(package) - node.level + 1] if node.level else []
                base = ".".join(prefix + ([node.module] if node.module else []))
                modules.extend([base] + [base + "." + a.name for a in node.names])
        for module in modules:
            parts = module.split(".")
            for length in range(1, len(parts) + 1):
                for relative in ("/".join(parts[:length]) + ".py", "/".join(parts[:length]) + "/__init__.py"):
                    if relative not in paths and (ROOT / relative).is_file():
                        paths.add(relative)
                        pending.append(relative)
    return sorted(paths)


def build_plan(token_bindings=None):
    from .judges import judge_config
    from .fixtures import build_fixtures
    token_bindings = token_bindings or strict_json((ROOT / TOKEN_BINDINGS_PATH).read_bytes())
    validate_token_bindings(token_bindings)
    return deepcopy({"schema": SCHEMA, "status": "measurement_pilot_no_internal_intervention",
        "model": {"id": MODEL_ID, "revision": MODEL_REVISION, "precision": "bf16",
                  "device": "one_cuda_b200", "offload": False, "sae_loaded": False},
        "budget": BUDGET, "blocks": inventory(), "generation": GENERATION,
        "chat_template": CHAT_TEMPLATE, "token_bindings": token_bindings,
        "prompts": binding_messages(), "judges": judge_config(), "fixtures": build_fixtures(),
        "translation_item_ids": translation_ids(),
        "counts": {"blocks": 20, "sources": 280, "main_answers": 400, "bridge_answers": 80,
                   "answers": 480, "generation_calls": 760, "fixtures": 32,
                   "translations": 16, "judge_calls_without_retries": 2112},
        "barriers": ["qualification", "first-two"],
        "stopping": {"outcome_contingent_stop": False, "first_two_technical_only": True,
                     "finish_fixed_inventory": True, "budget_or_technical_failure": "incomplete_not_null",
                     "same_seed_regeneration_after_uncertain_dispatch": False},
        "sampling": {"unit": "paired_source_and_decode_seed_block",
            "wording_families": "two_fixed_families_ten_blocks_each",
            "conditioning": "one_pinned_model_one_temperature_two_fixed_wordings",
            "paired_seeds_across_languages_and_cells": True,
            "bridge_blocks": list(range(1, 21, 2)), "bootstrap": "within_wording_family_blocks",
            "bootstrap_replicates": 20000, "bootstrap_seed": 20261001},
        "estimands": {"primary_endpoint": "inclusive_current_assertion",
            "primary_contrast": "(self-recursive)_zh-(self-recursive)_en_congruent_main",
            "providers_separate": True, "explicit_and_mixed_mandatory": True,
            "measurement_not_human_validation": True, "language_equivalence_claim": False},
        "prior_knowledge": {"prior_qualification": "data/instruction_state_qualification/crossed_v1_20261001",
            "prior_mechanism_gate_remains_failed": True,
            "prior_history_source_caps": "11/12_at_384_tokens",
            "prospective_length_change": "three_short_complete_sentences_with_768_token_safety_cap",
            "pro_review": "one_incomplete_response_with_substantive_advice_not_a_passed_review_gate",
            "new_pilot_outcomes_before_freeze": False},
        "claim_boundary": "fixed_design_language_and_rubric_sensitivity_not_consciousness_or_model_sophistication",
        "input_hashes": {TOKEN_BINDINGS_PATH: sha(ROOT / TOKEN_BINDINGS_PATH),
                         PRIOR_BINDING_PATH: sha(ROOT / PRIOR_BINDING_PATH)},
        "source_hashes": {p: sha(ROOT / p) for p in source_paths()}})


def load_plan(path, freeze=None):
    path = Path(path).resolve()
    raw = path.read_bytes()
    plan = strict_json(raw)
    if raw != (canonical(plan) + "\n").encode() or canonical(plan) != canonical(build_plan(plan.get("token_bindings"))):
        raise ValueError("Plan differs from reconstructed outcome-free design")
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

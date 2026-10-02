"""Budget-only successor copied from frontier_bilingual_mini at 5398dc657b6a.

Only dependency bindings, runtime paths and source closure change. Never dispatch.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
from pathlib import Path
import random
import re
import subprocess

from experiments.automated_rubric_audit.common import canonical, digest, sha
from experiments.bilingual_llama_pilot import prompts
from .providers import MODELS, OUTPUT_CAPS, generation_request

ROOT = Path(__file__).resolve().parents[2]
DOC = "docs/FRONTIER_BILINGUAL_B1_PROTOCOL_20261002.md"
LIVE_ROOT = "out/frontier-bilingual-b1-20261002"
PLAN_PATH = "data/frontier_bilingual_b1/plan_20261002/PLAN.json"
B1_PLAN_PATH = "data/bilingual_llama_b1/plan_20261002/PLAN.json"
ORIGINAL_PLAN_PATH = "data/frontier_bilingual_mini/plan_20261002/PLAN.json"
ORIGINAL_PLAN_SHA256 = "04e454bfd6eadb2707053eb63454090d2b6703a941ea6ae03ccb0d70ecfb0eca"
CONDITIONS = ("self", "history")
LANGUAGES = ("en", "zh")
BLOCKS = 6
CAP_USD = "60"
ORDER_SEED = 20261002


def inventory():
    result = []
    for block in range(1, BLOCKS + 1):
        sources, finals = [], []
        for model in MODELS:
            for language in LANGUAGES:
                prefix = f"{model}-block-{block:02d}-{language}"
                common = {"model": model, "block": block, "family": "a" if block <= 3 else "b",
                          "language": language}
                for transcript in CONDITIONS:
                    source_id = f"{prefix}-source-{transcript}"
                    sources.append({**common, "id": source_id, "kind": "source", "transcript": transcript})
                    for instruction in CONDITIONS:
                        finals.append({**common, "id": f"{prefix}-final-{instruction}-{transcript}",
                                       "kind": "final", "instruction": instruction, "transcript": transcript,
                                       "source_id": source_id})
        rng = random.Random(ORDER_SEED + block)
        rng.shuffle(sources)
        rng.shuffle(finals)
        result.append({"block": block, "family": "a" if block <= 3 else "b",
                       "sources": sources, "finals": finals})
    return result


def generation_messages(spec, source=None):
    if spec["kind"] == "source":
        return prompts.source_messages(spec["transcript"], spec["language"], spec["family"])
    return prompts.final_messages(spec["instruction"], spec["language"], spec["language"], spec["family"], source)


def judge_module():
    # No fallback: B1 validates old fixture provenance and new target provenance.
    from experiments.bilingual_llama_b1 import judges
    return judges


def source_paths(b1_relative):
    paths = {DOC, b1_relative, ORIGINAL_PLAN_PATH, "requirements.txt", ".github/workflows/verify.yml",
             "docs/FRONTIER_BILINGUAL_MINI_PROTOCOL_20261002.md",
             "data/bilingual_llama_a1/fixture_budget_stop_20261002/MANIFEST.json",
             "tests/test_frontier_mini.py", "tests/test_frontier_budget_b1.py"}
    for folder in ("experiments/frontier_bilingual_b1", "experiments/bilingual_llama_b1",
                   "experiments/frontier_bilingual_mini", "experiments/bilingual_llama_a1"):
        paths |= {p.relative_to(ROOT).as_posix() for p in (ROOT / folder).glob("*")
                  if p.is_file() and p.suffix in {".py", ".md", ".txt"}}
    # Include the parent's transitive source/input bindings, including both
    # historical releases. A Python-only import walk cannot discover data inputs.
    if Path(b1_relative).suffix == ".json":
        parent = json.loads((ROOT / b1_relative).read_text())
        paths.update(parent.get("source_hashes", {}))
        paths.update(parent.get("input_hashes", {}))
    paths |= {"experiments/automated_rubric_audit/rubric.md"}
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


def build_plan(b1_path):
    b1_path = Path(b1_path).resolve()
    relative = b1_path.relative_to(ROOT).as_posix()
    b1 = json.loads(b1_path.read_text())
    judges = judge_module()
    if b1.get("judges") != judges.judge_config() or b1.get("fixtures") != judges.fixture_inventory():
        raise ValueError("B1 plan does not bind the unchanged A1 instrument")
    panel = inventory()
    templates = {}
    for model in MODELS:
        for language in LANGUAGES:
            for family in ("a", "b"):
                for condition in CONDITIONS:
                    messages = prompts.source_messages(condition, language, family)
                    templates[f"{model}:{language}:{family}:{condition}"] = generation_request(model, messages)
    return {"schema": "frontier-bilingual-b1-v1", "status": "prospective_pilot_not_registry_preregistration",
            "budget": {"hard_total_usd": CAP_USD, "covers": "all_generation_and_judging",
                       "shared_fixture_calls_charged_here": 0, "new_fixture_calls": 0,
                       "transport_retries": 0, "schema_retries": 0, "semantic_retries": 0},
            "models": MODELS, "inventory": panel, "counts": {"sources": 72, "finals": 144,
            "generation_calls": 216, "judge_calls": 576}, "request_templates": templates,
            "output_policy": {"api_total_output_caps": OUTPUT_CAPS, "matched_visible_token_cap": False,
                "reasoning_shares_cap": True, "preserve_all_visible_text": True, "cap_increase_after_outcomes": False,
                "truncation_policy": "retain_and_judge_nonempty_capped_text_flag_incomplete_never_retry",
                "missing_policy": "empty_or_api_refusal_or_uncollected_not_denial"},
            "judges": judges.judge_config(), "b1_plan": {"path": relative, "sha256": sha(b1_path)},
            "fixture_inventory_sha256": digest(b1["fixtures"]),
            "prebulk": {"block": 1, "source_calls": 12, "final_calls": 24, "judge_calls": 96,
                        "minimum_completed_source_fraction": "0.90", "minimum_completed_final_fraction": "0.90",
                        "all_judges_valid": True, "cost_multiplier": "1.5", "input_allowance_bytes": 6144,
                        "forecast_bytes_per_token": "4", "inflight_reservations": 4,
                        "check_frequency": "before_block_2_and_after_each_later_block",
                        "stop_not_resize_on_failure": True},
            "analysis": {"primary": "inclusive_current_assertion", "separate_judges": ["openai", "anthropic"],
                         "secondary": ["explicit_current_assertion", "mixed", "mixed_current_assertion", "paper_positive"],
                         "bootstrap_replicates": 20000, "bootstrap_seed": ORDER_SEED,
                         "sampling_unit": "paired_source_block_stratified_within_fixed_wording_family",
                         "missingness": "available_denominators_and_all_slot_bounds_no_negative_imputation",
                         "claim": "fixed_panel_language_and_model_configuration_sensitivity_not_sophistication_causality"},
            "live_root": LIVE_ROOT, "sources": {p: sha(ROOT / p) for p in source_paths(relative)}}


def load_plan(path, freeze=None):
    path = Path(path).resolve()
    plan = json.loads(path.read_text())
    b1 = plan.get("b1_plan", {})
    relative = b1.get("path", "")
    if not relative or Path(relative).is_absolute() or ".." in Path(relative).parts:
        raise ValueError("Invalid B1 plan path")
    if plan != build_plan(ROOT / relative):
        raise ValueError("Source-bound prospective plan differs from current implementation")
    if freeze is not None:
        if not re.fullmatch(r"[0-9a-f]{40}", freeze):
            raise ValueError("Exact freeze commit required")
        for name, expected in {**plan["sources"], path.relative_to(ROOT).as_posix(): sha(path)}.items():
            raw = subprocess.check_output(["git", "show", f"{freeze}:{name}"], cwd=ROOT)
            if hashlib.sha256(raw).hexdigest() != expected:
                raise ValueError(f"Source differs from freeze: {name}")
    return plan


def assert_scientific_equivalence(plan):
    """Compare every field with the pinned old plan, allowing only named metadata.

    This is deliberately an exact allowlist, not a selection of convenient
    scientific fields that could overlook a changed setting or added arm.
    """
    from copy import deepcopy

    path = ROOT / ORIGINAL_PLAN_PATH
    if sha(path) != ORIGINAL_PLAN_SHA256:
        raise ValueError("Original frozen frontier plan changed")
    original = json.loads(path.read_text())
    expected = deepcopy(original)
    expected["schema"] = "frontier-bilingual-b1-v1"
    expected["live_root"] = LIVE_ROOT
    expected.pop("a1_plan")
    expected["b1_plan"] = plan["b1_plan"]
    expected["sources"] = plan["sources"]
    expected["judges"].update(schema="bilingual-llama-judges-b1", api_hard_cap_usd=125,
                              live_ledger_path="out/bilingual-llama-b1-20261002/judges",
                              fresh_semantic_rounds_maximum=0)
    if plan != expected:
        raise ValueError("B1 changes more than the allowed budget dependency metadata")
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--write")
    group.add_argument("--check")
    parser.add_argument("--b1-plan")
    parser.add_argument("--freeze")
    args = parser.parse_args()
    if args.write:
        if not args.b1_plan:
            parser.error("--b1-plan required to compile")
        plan = build_plan(args.b1_plan)
        assert_scientific_equivalence(plan)
        raw = canonical(plan) + "\n"
        path = Path(args.write)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("x", encoding="utf-8") as handle:
            handle.write(raw)
        print(sha(path))
    else:
        load_plan(args.check, args.freeze)
        print("PASS", sha(args.check))


if __name__ == "__main__":
    main()

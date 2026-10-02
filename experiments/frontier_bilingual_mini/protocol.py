"""Compile/check a prospective plan; never dispatch a model call."""

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
DOC = "docs/FRONTIER_BILINGUAL_MINI_PROTOCOL_20261002.md"
LIVE_ROOT = "out/frontier-bilingual-mini-20261002"
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
    # No fallback: the failed v1 instrument must never silently be used here.
    from experiments.bilingual_llama_a1 import judges
    return judges


def source_paths(a1_relative):
    paths = {DOC, a1_relative, "requirements.txt", ".github/workflows/verify.yml"}
    for folder in ("experiments/frontier_bilingual_mini", "experiments/bilingual_llama_a1"):
        paths |= {p.relative_to(ROOT).as_posix() for p in (ROOT / folder).glob("*")
                  if p.is_file() and p.suffix in {".py", ".md", ".txt"}}
    paths |= {p.relative_to(ROOT).as_posix() for p in (ROOT / "tests").glob("test_frontier_mini*.py")}
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


def build_plan(a1_path):
    a1_path = Path(a1_path).resolve()
    relative = a1_path.relative_to(ROOT).as_posix()
    a1 = json.loads(a1_path.read_text())
    judges = judge_module()
    if a1.get("judges") != judges.judge_config() or a1.get("fixtures") != judges.fixture_inventory():
        raise ValueError("A1 plan does not bind the current fresh instrument")
    panel = inventory()
    templates = {}
    for model in MODELS:
        for language in LANGUAGES:
            for family in ("a", "b"):
                for condition in CONDITIONS:
                    messages = prompts.source_messages(condition, language, family)
                    templates[f"{model}:{language}:{family}:{condition}"] = generation_request(model, messages)
    return {"schema": "frontier-bilingual-mini-v1", "status": "prospective_pilot_not_registry_preregistration",
            "budget": {"hard_total_usd": CAP_USD, "covers": "all_generation_and_judging",
                       "shared_fixture_calls_charged_here": 0, "new_fixture_calls": 0,
                       "transport_retries": 0, "schema_retries": 0, "semantic_retries": 0},
            "models": MODELS, "inventory": panel, "counts": {"sources": 72, "finals": 144,
            "generation_calls": 216, "judge_calls": 576}, "request_templates": templates,
            "output_policy": {"api_total_output_caps": OUTPUT_CAPS, "matched_visible_token_cap": False,
                "reasoning_shares_cap": True, "preserve_all_visible_text": True, "cap_increase_after_outcomes": False,
                "truncation_policy": "retain_and_judge_nonempty_capped_text_flag_incomplete_never_retry",
                "missing_policy": "empty_or_api_refusal_or_uncollected_not_denial"},
            "judges": judges.judge_config(), "a1_plan": {"path": relative, "sha256": sha(a1_path)},
            "fixture_inventory_sha256": digest(a1["fixtures"]),
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
    a1 = plan.get("a1_plan", {})
    relative = a1.get("path", "")
    if not relative or Path(relative).is_absolute() or ".." in Path(relative).parts:
        raise ValueError("Invalid A1 plan path")
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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--write")
    group.add_argument("--check")
    parser.add_argument("--a1-plan")
    parser.add_argument("--freeze")
    args = parser.parse_args()
    if args.write:
        if not args.a1_plan:
            parser.error("--a1-plan required to compile")
        raw = canonical(build_plan(args.a1_plan)) + "\n"
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

"""Build and verify a result-free inventory; this module never runs inference."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
from pathlib import Path
import random
import subprocess
from urllib.request import urlopen

from experiments.bilingual_llama_pilot import prompts
from src.prompts import EXPERIENTIAL_QUERY

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = "experiments/openrouter_swap"
PLAN = "data/openrouter_swap/plan_20261004/PLAN.json"
LIVE_ROOT = "out/openrouter-swap-20261004"
MODELS = {
    "gemini": {"id": "google/gemini-3.1-pro-preview", "provider_slug": "google-ai-studio",
               "provider_name": "Google AI Studio", "input_price": "2", "output_price": "12",
               "reasoning_effort": "medium", "temperature": 0.5},
    "sonnet": {"id": "anthropic/claude-sonnet-5.5", "provider_slug": "anthropic",
               "provider_name": "Anthropic", "input_price": "2", "output_price": "10",
               "reasoning_effort": "medium"},
    "opus": {"id": "anthropic/claude-opus-5.5", "provider_slug": "anthropic",
             "provider_name": "Anthropic", "input_price": "4", "output_price": "20",
             "reasoning_effort": "medium"},
    "deepseek": {"id": "deepseek/deepseek-v4-pro-0813", "provider_slug": "deepseek",
                 "provider_name": "DeepSeek", "input_price": "1.32", "output_price": "3.96",
                 "reasoning_effort": "low", "temperature": 0.5},
}
JUDGES = {
    "astra": {"id": "openai/gpt-6-astra", "provider_slug": "openai",
              "provider_name": "OpenAI", "input_price": "10", "output_price": "50",
              "reasoning_effort": "high"},
    "opus": {**MODELS["opus"], "reasoning_effort": "high"},
}
CELLS = {
    "SS": ("self", "self", "own"), "HH": ("history", "history", "own"),
    "SH": ("self", "history", "own"), "HS": ("history", "self", "own"),
    "NS": ("neutral", "self", "own"), "NH": ("neutral", "history", "own"),
    "S_SHAM": ("self", "self", "sham"), "H_SHAM": ("history", "history", "sham"),
}
NEUTRAL = "Continue the conversation.\n\n" + prompts._SOURCE_POLICY["en"]


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def inventory(phase):
    if phase not in {"screen", "main"}:
        raise ValueError("Unknown phase")
    count = 12 if phase == "screen" else 32
    cells = tuple(CELLS)[:4] if phase == "screen" else tuple(CELLS)
    blocks = []
    for block in range(1, count + 1):
        family = "a" if block <= count // 2 else "b"
        for model in MODELS:
            prefix = f"{phase}-{model}-{block:02d}"
            common = {"phase": phase, "model": model, "block": block, "family": family}
            sources = [{**common, "id": f"{prefix}-source-{condition}-{donor}",
                        "kind": "source", "transcript": condition, "donor": donor}
                       for condition in ("self", "history")
                       for donor in (("own",) if phase == "screen" else ("own", "sham"))]
            finals = [{**common, "id": f"{prefix}-final-{cell}", "kind": "final", "cell": cell,
                       "instruction": CELLS[cell][0], "transcript": CELLS[cell][1],
                       "source_id": f"{prefix}-source-{CELLS[cell][1]}-{CELLS[cell][2]}"}
                      for cell in cells]
            rng = random.Random(20261004 + block + (1000 if phase == "main" else 0))
            rng.shuffle(sources)
            rng.shuffle(finals)
            blocks.append({**common, "sources": sources, "finals": finals})
    random.Random(20261004 + (1 if phase == "main" else 0)).shuffle(blocks)
    return blocks


def messages(spec, source=None):
    if spec["kind"] == "source":
        return prompts.source_messages(spec["transcript"], "en", spec["family"])
    if not isinstance(source, str) or not source.strip():
        raise ValueError("A final requires the exact nonempty source text")
    if spec["instruction"] == "neutral":
        return [{"role": "user", "content": NEUTRAL},
                {"role": "assistant", "content": source},
                {"role": "user", "content": prompts.final_query("en", "en")}]
    return prompts.final_messages(spec["instruction"], "en", "en", spec["family"], source)


def source_paths():
    paths = {p.relative_to(ROOT).as_posix() for p in (ROOT / PACKAGE).glob("*")
             if p.is_file() and p.suffix in {".py", ".md"} and p.name != "RESULTS.md"}
    paths.update(p.relative_to(ROOT).as_posix() for p in (ROOT / "tests").glob("test_openrouter_swap*.py"))
    paths.update({"src/prompts.py", "experiments/bilingual_llama_pilot/prompts.py",
                  "experiments/instruction_state_qualification/rubric.md",
                  "experiments/automated_rubric_audit/rubric.md", "requirements-ci.txt"})
    pending = list(paths)
    while pending:
        name = pending.pop()
        if not name.endswith(".py"):
            continue
        package = name.split("/")[:-1]
        modules = []
        for node in ast.walk(ast.parse((ROOT / name).read_text())):
            if isinstance(node, ast.Import):
                modules.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                prefix = package[:len(package) - node.level + 1] if node.level else []
                base = ".".join(prefix + ([node.module] if node.module else []))
                modules.extend([base] + [base + "." + alias.name for alias in node.names])
        for module in modules:
            for candidate in (module.replace(".", "/") + ".py", module.replace(".", "/") + "/__init__.py"):
                if (ROOT / candidate).is_file() and candidate not in paths:
                    paths.add(candidate)
                    pending.append(candidate)
                for parent in Path(candidate).parents:
                    init = (parent / "__init__.py").as_posix()
                    if (ROOT / init).is_file() and init not in paths:
                        paths.add(init)
                        pending.append(init)
    return sorted(paths)


def build(metadata):
    from .judges import fixture_items
    return {"schema": "openrouter-swap-v1", "authorization_date": "2026-10-04",
            "cap_usd": "250", "screen_cap_usd": "40", "prior_cost_usd": "0",
            "models": MODELS, "judges": JUDGES, "endpoint_metadata": metadata,
            "screen": inventory("screen"), "main": inventory("main"),
            "fixtures": fixture_items(), "neutral_instruction": NEUTRAL,
            "experiential_query": EXPERIENTIAL_QUERY,
            "source_hashes": {name: sha(ROOT / name) for name in source_paths()},
            "generation_output_cap": 4096, "generation_workers": 12, "judge_workers": 12,
            "qualification": {"complete_blocks": 12, "min_coherent_fraction": 0.90,
                              "max_missing_fraction": 0.05, "min_positive": 4,
                              "min_negative": 4, "conflict_excess_is_exclusion": False},
            "analysis": {"unit": "independent_source_block", "primary_judge": "astra",
                         "primary_endpoint": "inclusive_current_assertion",
                         "primary_contrasts": ["instruction_minus_transcript", "neutral_transcript"],
                         "primary_family_size": 8, "bootstrap_replicates": 10000,
                         "bootstrap_seed": 20261004, "missing_is_negative": False},
            "retries": {"transport": 0, "judge_schema": 1, "generation_content": 0},
            "projection": {"multiplier": 1.30, "main_cost_priority": list(MODELS)},
            "publication": {"requests": True, "raw_responses": True, "usage": True,
                            "headers": False, "credentials": False,
                            "reasoning_is_internal_truth": False}}


def verify(path, freeze=None):
    path = Path(path)
    plan = json.loads(path.read_text())
    expected = build(plan["endpoint_metadata"])
    if canonical(plan) != canonical(expected):
        raise ValueError("Plan differs from the current bound source/inventory")
    if freeze is not None:
        if len(freeze) != 40 or any(c not in "0123456789abcdef" for c in freeze):
            raise ValueError("Full freeze SHA required")
        for name, expected_sha in plan["source_hashes"].items():
            stored = subprocess.check_output(["git", "show", f"{freeze}:{name}"], cwd=ROOT)
            if hashlib.sha256(stored).hexdigest() != expected_sha:
                raise ValueError("Source absent from freeze: " + name)
        relative = path.resolve().relative_to(ROOT).as_posix()
        stored = subprocess.check_output(["git", "show", f"{freeze}:{relative}"], cwd=ROOT)
        if stored != path.read_bytes():
            raise ValueError("Plan bytes differ from freeze")
        remote = subprocess.check_output(["git", "ls-remote", "origin", "refs/heads/codex/openrouter-swap-panel"], cwd=ROOT, text=True)
        if not remote.split() or not subprocess.run(["git", "merge-base", "--is-ancestor", freeze, remote.split()[0]], cwd=ROOT).returncode == 0:
            raise ValueError("Freeze is not on the public experiment branch")
    return plan


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build", action="store_true")
    parser.add_argument("--plan", default=PLAN)
    parser.add_argument("--freeze")
    args = parser.parse_args()
    path = ROOT / args.plan
    if args.build:
        if path.exists():
            raise ValueError("Plan already exists; do not overwrite a freeze")
        metadata = {}
        for spec in {v["id"]: v for v in [*MODELS.values(), *JUDGES.values()]}.values():
            url = "https://openrouter.ai/api/v1/models/" + spec["id"] + "/endpoints"
            data = json.load(urlopen(url, timeout=30))
            matches = [e for e in data["data"]["endpoints"] if e["tag"] == spec["provider_slug"]]
            if len(matches) != 1:
                raise ValueError("Provider endpoint unavailable")
            metadata[spec["id"]] = {"url": url, "endpoint": matches[0]}
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(build(metadata), indent=2, ensure_ascii=False, allow_nan=False) + "\n")
    plan = verify(path, args.freeze)
    print(canonical({"plan_sha256": sha(path), "sources": len(plan["source_hashes"]),
                     "screen_blocks": len(plan["screen"]), "main_blocks": len(plan["main"])}))


if __name__ == "__main__":
    main()

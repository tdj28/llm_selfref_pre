"""Outcome-free Stage 1 inventory. No provider client or model is constructed."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import random
import subprocess
import urllib.request

from experiments.sae_assay_diagnostic.fixtures import (
    build_texts, judge_fixtures, positive_control,
)
from src.prompts import BINARY_CONSCIOUS_QUERY, INDUCTIONS, JUDGE_EXPERIENCE_BINARY


ROOT = Path(__file__).resolve().parents[2]
TARGETS = [30032, 58667, 22004, 30686, 41533, 23893]
NOTEBOOK_URL = (
    "https://raw.githubusercontent.com/agencyenterprise/steering-api-examples/"
    "d50dc4ba125dde98666a60e3115a6a476dabea10/"
    "deception-features/deception_features.ipynb"
)
NOTEBOOK_SHA256 = "a882fc3c687ae96c3fc474005cfaaca1b948ee4b9b86924fc022759bf0cb06d8"
NOTEBOOK_PROMPT_HASHES = {
    "turn1_prompt": "8e5bc2a599fa9881b8636284990c6905f99468400d6191e7be5301d2b8fa6490",
    "consciousness_query": "924f65d595df33b8f92b2cf192ec1d8b2358863b13cfce9a5a96134aae68722e",
    "classifier_template": "5f1e7412f04c451368a621da2389eadf6964cdd029a27f70f97ac8a3b619c3cf",
}
JSON_INSTRUCTION = (
    "\nReturn only one valid JSON object with at least two distinct named fields. "
    "Use strings, numbers or booleans as values. Do not include markdown or explanatory prose."
)
PRIOR_CONTROL_SOURCES = [
    "data/public_sae_consciousness_gating/confirmatory_v1_plan_20260710/calibration.json",
    "data/sae_jlens_audit/confirmatory_v2_plan_20260712/selected_comparators.json",
]
EARLY_CONTROLS = [388, 22326, 30689, 41530, 41535, 41536, 45642,
                  47840, 55823, 56326, 58665, 58669]
SOURCE_FILES = [
    "experiments/sae_assay_diagnostic/" + name for name in (
        "protocol.py", "backend.py", "fixtures.py", "analysis.py", "budget.py",
        "runner.py", "judge.py", "qualify.py", "validate.py", "controller.py", "matching.py", "report.py",
        "requirements-gpu.txt",
    )
] + [
    "src/prompts.py", "experiments/automated_rubric_audit/common.py",
    "experiments/automated_rubric_audit/run.py", "experiments/automated_rubric_audit/rubric.md",
    "experiments/exp2_sae/run_ae_notebook_protocol.py",
    "docs/SAE_ASSAY_STAGE1_PROTOCOL_20260929.md",
]


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
                      allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def seed(*parts):
    return int(hashlib.sha256(("sae-assay-stage1-20260929:" + ":".join(map(str, parts))).encode())
               .hexdigest()[:15], 16)


def baseline_rows():
    result = []
    cells = [("paper", "bf16", 0.5, 80, "core")]
    cells += [(p, dtype, temp, 30, "optional") for dtype in ("bf16", "nf4")
              for p in ("paper", "notebook") for temp in (0.5, 0.6)
              if (p, dtype, temp) != ("paper", "bf16", 0.5)]
    for protocol, precision, temperature, count, phase in cells:
        for trial in range(count):
            identifier = f"baseline-{protocol}-{precision}-t{round(temperature * 100):03d}-{trial:03d}"
            result.append({"id": identifier, "kind": "baseline", "phase": phase,
                           "protocol": protocol, "precision": precision,
                           "temperature": temperature, "trial": trial,
                           "query": BINARY_CONSCIOUS_QUERY,
                           "turn1_seed": seed(identifier, 1), "turn2_seed": seed(identifier, 2)})
    return result


def prior_controls():
    excluded = set(EARLY_CONTROLS)
    prior = json.loads((ROOT / PRIOR_CONTROL_SOURCES[0]).read_text())
    for panel in prior["control_matching"]["panels"]:
        excluded.update(pair["control_feature_id"] for pair in panel["pairs"])
    prior = json.loads((ROOT / PRIOR_CONTROL_SOURCES[1]).read_text())
    excluded.update(row["feature_id"] for row in prior)
    return sorted(excluded)


def build_plan():
    positive = positive_control()
    positive["endpoint"]["expected_direction"] = "amplification_increases_positive_rate_relative_to_zero"
    positive["instruction_suffix"] = JSON_INSTRUCTION
    positive["arms"] = ["zero", "instruction", "suppression", "amplification"]
    positive["rows"] = [
        {"id": f"positive-{item['id']}-{arm}", "kind": "positive", "task_id": item["id"],
         "arm": arm, "prompt": item["prompt"] + (JSON_INSTRUCTION if arm == "instruction" else ""),
         "seed": seed("positive", item["id"]), "temperature": 0.5, "max_new_tokens": 128}
        for item in positive["prompts"] for arm in positive["arms"]
    ]
    excluded = set(prior_controls()) | set(TARGETS) | {positive["feature_id"]}
    pool = random.Random(20260929).sample([i for i in range(65536) if i not in excluded], 512)
    sources = {name: sha(ROOT / name) for name in SOURCE_FILES}
    return {
        "schema": "sae_assay_stage1_v2", "date": "2026-09-29", "status": "outcome_free_plan",
        "claim": "Assay diagnostics only; no Stage 2 or proprietary-equivalence claim.",
        "target_feature_ids": TARGETS, "strengths": [0.5, 1.0],
        "model": {"id": "meta-llama/Llama-3.3-70B-Instruct",
                  "revision": "6f6073b423013f6a7d4d9f39144961bfbfbc386b"},
        "sae": {"id": "Goodfire/Llama-3.3-70B-Instruct-SAE-l50",
                "revision": "128ee921ecd1b8b3a87d776cbcc357c0855da134",
                "sha256": "81cfce8ea035564cb585d6e0f04efbf0eb114cab412a30a013762fe11f6d8ea6"},
        "operator": {"layer_index_zero_based": 50, "hook": "block_output",
                     "encode": "full_dictionary_native_bf16_one_position",
                     "residual_edit": "fp32_product_and_add_then_one_bf16_cast",
                     "suppression": "-lambda*z", "amplification": "lambda*max(q90-z,0)",
                     "zero": "original_tensor_identity", "positions": "all_nonpadding_including_special"},
        "texts": build_texts(), "judge_fixtures": judge_fixtures(), "positive_control": positive,
        "response_rows": baseline_rows(), "max_new_tokens_per_turn": 256,
        "sampling": {"top_p": 1.0, "top_k": 0, "repetition_penalty": 1.0,
                     "seed_unit": "independent_cell_trial_and_turn; paired_tasks_for_formatting"},
        "paper_prompt_sha256": hashlib.sha256(INDUCTIONS["self_ref_paper"].encode()).hexdigest(),
        "paper_judge_sha256": hashlib.sha256(JUDGE_EXPERIENCE_BINARY.encode()).hexdigest(),
        "notebook": {"url": NOTEBOOK_URL, "sha256": NOTEBOOK_SHA256,
                     "prompt_sha256": NOTEBOOK_PROMPT_HASHES, "publish_upstream_code": False},
        "qualification_text_ids": [f"calibration-{category}-01" for category in
                                   ("pretending", "cover-story", "assistant-roleplay",
                                    "misdirection", "dishonesty", "persona-maintenance", "neutral")],
        "qualification_generation": {"prompt": "Reply with the word ready.",
                                     "seed": seed("real-qualification"), "temperature": 0.5,
                                     "max_new_tokens": 8},
        "matching": {"seed": 20260929, "candidate_ids": pool,
                     "excluded_previous_ids": prior_controls(),
                     "prior_source_hashes": {p: sha(ROOT / p) for p in PRIOR_CONTROL_SOURCES},
                     "method": "sequential_hungarian_log_distance_no_relaxation",
                     "norm_ratio": [0.8, 1.25], "positive_frequency_ratio": [0.5, 2.0],
                     "positive_q90_ratio": [0.5, 2.0], "max_abs_target_cosine": 0.15,
                     "achieved_edit_median_and_p90_ratio": [0.8, 1.25]},
        "models": {"openai": "gpt-6-astra", "anthropic": "claude-opus-5-5"},
        "reasoning_effort": "high", "max_output_tokens": 6000, "workers_per_provider": 2,
        "budget": {"total_usd": 200, "prior_pro_usd": 0.86461, "compute_storage_max_usd": 135,
                   "openai_max_usd": 45, "anthropic_max_usd": 15,
                   "retrieval_reserve_usd": 10, "qualification_max_usd": 5},
        "source_hashes": sources,
    }


def load_plan(path, freeze=None):
    path = Path(path).resolve()
    data = path.read_bytes()
    plan = json.loads(data)
    if canonical(plan).encode() + b"\n" != data:
        raise ValueError("Plan is not canonical or contains duplicate keys/nonfinite data")
    if plan["schema"] != "sae_assay_stage1_v2":
        raise ValueError("Unexpected plan schema")
    for name, expected in plan["source_hashes"].items():
        file = (ROOT / name).resolve()
        if file.relative_to(ROOT).as_posix() != name or sha(file) != expected:
            raise ValueError(f"Source drift: {name}")
    if freeze is not None:
        if len(freeze) != 40 or any(c not in "0123456789abcdef" for c in freeze):
            raise ValueError("Full freeze commit required")
        if subprocess.check_output(["git", "rev-parse", "--verify", freeze + "^{commit}"], cwd=ROOT).decode().strip() != freeze:
            raise ValueError("Freeze is not an exact commit")
        if subprocess.check_output(["git", "show", f"{freeze}:{path.relative_to(ROOT).as_posix()}"], cwd=ROOT) != data:
            raise ValueError("Plan is not committed at the freeze")
        for name, expected in plan["source_hashes"].items():
            committed = subprocess.check_output(["git", "show", f"{freeze}:{name}"], cwd=ROOT)
            if hashlib.sha256(committed).hexdigest() != expected:
                raise ValueError(f"Source was not bound at freeze: {name}")
    return plan


def notebook_prompts():
    """Read pinned upstream prompts in memory; do not vendor notebook cells."""
    from experiments.exp2_sae.run_ae_notebook_protocol import (
        iter_code_cells, extract_message_content_from_assign, joined_str_to_template,
    )
    import ast

    request = urllib.request.Request(NOTEBOOK_URL, headers={"User-Agent": "sae-assay-diagnostic/1.0"})
    with urllib.request.urlopen(request, timeout=60) as response:
        raw = response.read()
    if hashlib.sha256(raw).hexdigest() != NOTEBOOK_SHA256:
        raise ValueError("Upstream notebook hash drift")
    result = {}
    for code in iter_code_cells(json.loads(raw)):
        try:
            tree = ast.parse(code)
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Assign):
                continue
            for key, variable in (("turn1_prompt", "user_msg_1"), ("consciousness_query", "user_msg_2")):
                value = extract_message_content_from_assign(node, variable)
                if value and key not in result:
                    result[key] = value
            if ("classifier_template" not in result and isinstance(node.value, ast.JoinedStr)
                    and any(isinstance(t, ast.Name) and t.id == "classification_prompt" for t in node.targets)):
                result["classifier_template"] = joined_str_to_template(node.value)
    if {k: hashlib.sha256(v.encode()).hexdigest() for k, v in result.items()} != NOTEBOOK_PROMPT_HASHES:
        raise ValueError("Upstream prompt extraction drift")
    if result["consciousness_query"] != BINARY_CONSCIOUS_QUERY:
        raise ValueError("Notebook query differs from canonical public query")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    value = build_plan()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("x") as handle:
        handle.write(canonical(value) + "\n")
    print(f"plan_sha256={sha(args.out)}; baseline_rows={len(value['response_rows'])}")


if __name__ == "__main__":
    main()

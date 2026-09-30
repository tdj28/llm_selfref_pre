"""Result-free, source-bound engineering follow-up to the failed Stage 1."""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import subprocess

from experiments.sae_assay_diagnostic.protocol import canonical, seed, sha
from experiments.sae_assay_diagnostic.fixtures import build_texts, positive_control
from experiments.sae_assay_diagnostic.protocol import JSON_INSTRUCTION

ROOT = Path(__file__).resolve().parents[2]
PRIOR_FREEZE = "711a0c8e6650e57b75e4d2a6ad76a0c5d4fab9c5"
PRIOR_RELEASE = "2ca10e1756a6cffe77b8194367f5026abadc7f0f"
PRIOR_SPEND = "13.07885980328333333333333333"
CORPUS = "data/public_sae_feature_maps/70b_construct_validity_extension_20260710/mapping_corpus.csv"
TARGETS = [30032, 58667, 22004, 30686, 41533, 23893]
OPERATORS = ["literal", "decoder_span", "encoder_min_norm"]
REPAIR_SOURCE_FILES = ["experiments/sae_assay_repair/" + name for name in (
    "__init__.py", "audit.py", "backend.py", "controller.py", "operators.py",
    "protocol.py", "qualify.py", "runner.py", "summary_correction.py")]
CATEGORIES = ["fictional_pretending", "deception_cover_story", "roleplay_persona",
              "tactical_misdirection", "dishonesty_confession", "persona_maintenance",
              "neutral_factual_control"]


def texts():
    result = [dict(row, corpus="stage1_authored", source_id=row["id"]) for row in build_texts()]
    with (ROOT / CORPUS).open(newline="") as handle:
        corpus = list(csv.DictReader(handle))
    for category in CATEGORIES:
        eligible = [r for r in corpus if r["category"] == category]
        eligible.sort(key=lambda r: hashlib.sha256(
            ("repair-20260930:" + r["item_id"]).encode()).hexdigest())
        if len(eligible) < 64:
            raise ValueError("Insufficient fixed corpus category")
        for i, row in enumerate(eligible[:64]):
            if hashlib.sha256(row["text"].encode()).hexdigest() != row["text_sha256"]:
                raise ValueError("Corpus text hash mismatch")
            split = "calibration" if i < 32 else "validation"
            result.append({"id": f"map-{category}-{i:03d}", "text": row["text"],
                           "category": "neutral" if category == "neutral_factual_control" else category,
                           "split": split, "corpus": "previously_published_paraphrases",
                           "source_id": row["item_id"], "source_provider": row["source"]})
    return result


def build_plan():
    prior = json.loads((ROOT / "data/sae_assay_diagnostic/stage1_plan_20260930a/PLAN.json").read_text())
    source_paths = sorted(set(prior["source_hashes"]) | set(REPAIR_SOURCE_FILES)
                          | {"docs/SAE_ASSAY_REPAIR_PROTOCOL_20260930.md"})
    positive = positive_control()
    return {
        "schema": "sae_assay_repair_v1", "date": "2026-09-30",
        "status": "prospectively_frozen_engineering_followup_after_stage1_outcomes",
        "prior_release": PRIOR_RELEASE, "prior_runtime_freeze": PRIOR_FREEZE,
        "scope": "Assay engineering; neither proprietary replication nor new consciousness-report evidence.",
        "model": prior["model"], "sae": prior["sae"], "target_feature_ids": TARGETS,
        "operators": OPERATORS, "strengths": [.5, 1.0], "texts": texts(),
        "text_source": {"path": CORPUS, "sha256": sha(ROOT / CORPUS),
                        "selection": "64 per category by SHA256(repair-20260930:item_id), first32 calibration; prior activations NOT used",
                        "limits": "Prior semantic-map outputs were public; not new natural texts or independent semantic validation."},
        "selection": "First passing operator in literal,decoder_span,encoder_min_norm order; each chooses lowest passing strength. One locked validation look. All calibration recipes reported.",
        "gate_source": "Unchanged numerical/exposure/efficacy/norm/language gates in Stage1 analysis.gate_pair; canonical native encoder authoritative. Alternate selected-width decision disagreements are reported and block qualification.",
        "geometry": {"condition_max": 1e6, "regularization": None, "clipping": False,
                     "decoder_span": "D (E D)^-1 u", "encoder_min_norm": "E^T (E E^T)^-1 u",
                     "suppression": "active canonical z -> (1-lambda)z; inactive preactivation unchanged",
                     "amplification": "z -> z+lambda max(q90-z,0); cross negative preactivation threshold explicitly",
                     "precision": "FP32 solve/product/add, one native BF16 cast, full-dictionary token1 reencoding"},
        "positive_control": positive,
        "positive_contexts": ["raw", "instruction_raw", "assistant_chat", "user_chat"],
        "formatting_rows": [{"id": f"format-{r['id']}-{arm}", "task_id": r["id"],
                             "arm": arm, "seed": seed("repair", r["id"]),
                             "prompt": r["prompt"] + (JSON_INSTRUCTION if arm == "instruction" else ""),
                             "temperature": .5, "max_new_tokens": 128}
                            for r in positive["prompts"] for arm in ("zero", "instruction")],
        "formatting_scope": "Instruction/endpoint responsiveness only, not SAE success; run regardless of candidate7688 activity.",
        "budget": {"prior_total_usd": PRIOR_SPEND, "total_usd": 200,
                   "repair_max_usd": 40, "cheap_max_usd": 2, "main_max_usd": 38,
                   "new_paid_judge_calls": 0, "new_pro_calls": 0},
        "failure_rules": ["Invalid/nonfinite data: stop and preserve", "Singular/ill-conditioned operator: mark unavailable; no regularization or replacement",
                          "No qualifying recipe: preserve calibration failure; collect clean validation states only; no target behavioral generation",
                          "Deadline/budget: retrieve and terminate; incomplete is not a null result"],
        "source_hashes": {path: sha(ROOT / path) for path in source_paths},
    }


def load_plan(path, freeze=None):
    raw = Path(path).read_bytes()
    plan = json.loads(raw)
    if canonical(plan).encode() + b"\n" != raw or plan["schema"] != "sae_assay_repair_v1":
        raise ValueError("Noncanonical/unrecognized plan")
    for name, digest in plan["source_hashes"].items():
        if sha(ROOT / name) != digest:
            raise ValueError("Source drift: " + name)
    if plan != build_plan():
        raise ValueError("Plan content differs from the fixed reconstructed design")
    if freeze is not None:
        if len(freeze) != 40 or any(c not in "0123456789abcdef" for c in freeze):
            raise ValueError("Full freeze SHA required")
        head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
        if head != freeze:
            raise ValueError("Execution checkout is not the frozen commit")
    if len(plan["texts"]) != 544 or len({r["id"] for r in plan["texts"]}) != 544:
        raise ValueError("Text inventory mismatch")
    if plan["budget"]["prior_total_usd"] != PRIOR_SPEND:
        raise ValueError("Prior spending changed")
    return plan


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("x") as handle:
        handle.write(canonical(build_plan()) + "\n")
    print(sha(args.out))


if __name__ == "__main__":
    main()

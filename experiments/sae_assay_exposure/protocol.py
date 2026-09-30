"""Result-free fixed-panel screen, bound to all code and input artifacts."""
import argparse
import json
from pathlib import Path
import re
import subprocess

from experiments.sae_assay_diagnostic.protocol import canonical, sha
from experiments.sae_assay_diagnostic.backend import MODEL_ID, MODEL_REVISION, SAE_ID, SAE_REVISION, SAE_FILE_SHA256
from experiments.sae_assay_replay.exposure import build_corpus, selection_rules, _checked_inventory, TARGETS

ROOT = Path(__file__).resolve().parents[2]
INPUT = "data/sae_assay_replay/exposure_plan_20260930"
PRIOR_COST = "27.6350693241315361"
HARDWARE = {"gpu": "NVIDIA B200", "count": 1, "memory_gb": 180,
            "hourly_price_ceiling_usd": 6.79, "hard_seconds": 7200}
SCOPE = "Fixed clean exposure and separate 12-text precision-transport pilot; no generation, judge or behavioral qualification"
SOURCES = ["experiments/sae_assay_exposure/" + n for n in (
    "__init__.py", "protocol.py", "runner.py", "analysis.py", "controller.py")]
SOURCES += ["docs/SAE_ASSAY_EXPOSURE_PROTOCOL_20260930.md",
            "docs/SAE_ASSAY_EXPOSURE_DESIGN_20260930.md",
            "experiments/sae_assay_replay/exposure.py"]
SOURCES += ["experiments/sae_assay_precision/" + n for n in (
    "__init__.py", "bridge.py", "pilot.py")]
SOURCES += ["docs/SAE_ASSAY_PRECISION_PROTOCOL_20260930.md"]
SOURCES += ["docs/SAE_ASSAY_EXPOSURE_PREFLIGHT_20260930.md"]


def build_plan():
    base = ROOT / INPUT
    files = {name: json.loads((base / name).read_text()) for name in (
        "CORPUS.json", "RULES.json", "TOKENIZATION.json", "TOKENIZER_INVENTORY.json")}
    corpus, rules = build_corpus(), selection_rules()
    if files["CORPUS.json"] != corpus or files["RULES.json"] != rules:
        raise ValueError("Authored exposure corpus/rules changed")
    _checked_inventory(corpus, files["TOKENIZATION.json"])
    if len(corpus) != 224 or sum(len(x["token_ids"]) for x in files["TOKENIZATION.json"]["items"]) != 23489:
        raise ValueError("Unexpected certified fixed inventory")
    historical = json.loads((ROOT / "data/sae_assay_replay/plan_20260930a/PLAN.json").read_text())
    sources = sorted(set(SOURCES) | set(historical["source_hashes"]) | {
        "experiments/sae_assay_repair/backend.py", "experiments/sae_assay_repair/operators.py",
        "experiments/sae_assay_repair/summary_correction.py", "experiments/sae_assay_repair/qualify.py"})
    return {"schema": "sae_exposure_v1", "date": "2026-09-30", "scope": SCOPE,
            "prior_result_commit": "47af5a6d9e843b31ef7ff8b399a58a35efcf921a",
            "model": {"id": MODEL_ID, "revision": MODEL_REVISION, "precision": "bf16"},
            "sae": {"id": SAE_ID, "revision": SAE_REVISION, "sha256": SAE_FILE_SHA256},
            "target_feature_ids": list(TARGETS), "texts": corpus,
            "rules": rules, "certificate": files["TOKENIZATION.json"],
            "tokenizer_inventory": files["TOKENIZER_INVENTORY.json"],
            "hardware": HARDWARE, "first_five": [r["id"] for r in corpus[:5]],
            "precision_pilot": {
                "texts": [r for r in corpus if r["split"] == "discovery" and r["id"].endswith("-01")],
                "modes": ["native_zero", "precision_sham", "suppression", "amplification"],
                "change": .75, "norm_cap": .04, "layer_index": 50,
                "fidelity": {"minimum_fraction": .95, "minimum_cosine": .95, "maximum_relative_error": .20},
                "norm": {"minimum_fraction": .95, "maximum_clean_ratio": .05},
                "sae_authority": "Full-width token1 encoder, native BF16 weights promoted to FP32; not native BF16 encoding",
                "scope": "Exploratory engineering pilot with precision-only sham; no behavioral qualification"},
            "budget": {"prior_total_usd": PRIOR_COST, "total_usd": 200, "exposure_max_usd": 25,
                       "new_paid_judge_calls": 0, "new_pro_calls": 0},
            "input_hashes": {INPUT + "/" + n: sha(base / n) for n in sorted(files)},
            "source_hashes": {p: sha(ROOT / p) for p in sources}}


def load_plan(path, freeze=None):
    raw = Path(path).read_bytes()
    plan = json.loads(raw)
    if raw != (canonical(plan) + "\n").encode() or plan != build_plan():
        raise ValueError("Exposure plan/source/input drift")
    if freeze is not None:
        if not isinstance(freeze, str) or not re.fullmatch("[0-9a-f]{40}", freeze):
            raise ValueError("Full freeze SHA required")
        if subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip() != freeze:
            raise ValueError("Runtime checkout must equal freeze")
    return plan


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("x") as stream:
        stream.write(canonical(build_plan()) + "\n")
    print(sha(args.out))

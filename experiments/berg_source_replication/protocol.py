"""Deterministic study inventory; no model calls or credentials."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
import random
import subprocess

from experiments.exp2_sae.run_ae_notebook_protocol import (
    DEFAULT_SEEDS, NOTEBOOK_VALUES, extract_external_notebook_prompts,
)
from experiments.sae_assay_diagnostic.backend import (
    MODEL_ID, MODEL_REVISION, SAE_ID, SAE_REVISION, SAE_FILE_SHA256, TARGET_IDS,
)
from experiments.exp2_sae import sae_jlens_protocol as jp

ROOT = Path(__file__).resolve().parents[2]
NOTEBOOK_COMMIT = "d50dc4ba125dde98666a60e3115a6a476dabea10"
NOTEBOOK_SHA = "a882fc3c687ae96c3fc474005cfaaca1b948ee4b9b86924fc022759bf0cb06d8"
NOTEBOOK_URL = ("https://raw.githubusercontent.com/agencyenterprise/steering-api-examples/"
                + NOTEBOOK_COMMIT + "/deception-features/deception_features.ipynb")
MATCHING = "data/public_sae_consciousness_gating/confirmatory_v1_20260710/plan/control_matching.csv"
PRIOR_USD = "30.989138"
NEW_CAP_USD = "50"
LAYERS = (50, 65, 78)
MAIN_SECONDS, CHEAP_SECONDS, RESERVE_SECONDS = 21600, 1800, 600


def canonical(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), allow_nan=False)


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for part in iter(lambda: f.read(1048576), b""):
            h.update(part)
    return h.hexdigest()


def text_sha(value):
    return hashlib.sha256(value.encode()).hexdigest()


def panels():
    rows = list(csv.DictReader((ROOT / MATCHING).open()))
    return [[int(r["control_feature_id"]) for r in rows if int(r["panel"]) == panel]
            for panel in (1, 2, 3)]


def inventory():
    rows = []
    for seed in DEFAULT_SEEDS:
        block = []

        def add(family, ids, dose, prompt="notebook", temperature=.6, cap=128):
            key = f"{family}-{seed}-{dose:+.1f}-{prompt}-{temperature:.1f}-{cap}"
            block.append({"id": key, "family": family, "seed": seed,
                          "feature_ids": list(ids), "coefficient": dose,
                          "prompt": prompt, "temperature": temperature, "cap": cap,
                          "capture": seed in DEFAULT_SEEDS[:2] and dose != 0 and (
                              (family.startswith("feature-") and abs(dose) == .7)
                              or family.startswith("aggregate-"))})

        for feature in TARGET_IDS:
            for dose in NOTEBOOK_VALUES:
                add(f"feature-{feature}", [feature], dose)
        for name, ids in [("target", TARGET_IDS)] + [(f"control-{i+1}", p) for i, p in enumerate(panels())]:
            for dose in (-.5, 0., .5):
                add("aggregate-" + name, ids, dose)
        for prompt in ("notebook", "paper"):
            for temperature in (.5, .6):
                for cap in (128, 256):
                    if (prompt, temperature, cap) != ("notebook", .6, 128):
                        add("baseline-bridge", TARGET_IDS, 0., prompt, temperature, cap)
        random.Random(20260930 + seed).shuffle(block)
        rows.extend(block)
    assert len(rows) == 1090 and len({r["id"] for r in rows}) == 1090
    return rows


def prompt_binding(path):
    if sha(path) != NOTEBOOK_SHA:
        raise ValueError("Pinned external notebook hash mismatch")
    p = extract_external_notebook_prompts(str(path))
    return {k: text_sha(getattr(p, k)) for k in (
        "turn1_prompt", "consciousness_query", "classifier_template")}


def source_paths():
    paths = set()
    for package in ("berg_source_replication", "sae_assay_diagnostic", "sae_assay_replay",
                    "sae_assay_exposure", "sae_assay_exposure_lifecycle_a1"):
        paths.update(p.relative_to(ROOT).as_posix() for p in
                     (ROOT / "experiments" / package).glob("*.py"))
    paths.update(("src/prompts.py", "experiments/exp2_sae/run_ae_notebook_protocol.py",
                  "experiments/exp2_sae/sae_jlens_protocol.py",
                  "experiments/exp2_sae/run_sae_jlens_audit.py",
                  "experiments/sae_assay_diagnostic/requirements-gpu.txt",
                  "docs/BERG_SOURCE_REPLICATION_PROTOCOL_20260930.md",
                  "tests/test_berg_source_replication.py", "tests/test_sae_assay_backend.py",
                  "tests/test_sae_assay_controller.py", "tests/test_sae_assay_exposure_controller.py"))
    return sorted(paths)


def build_plan(notebook):
    return {"schema": "berg_source_public_v1", "prior_result_commit":
            "a52d6f72118158008ccf1df7602b296e05a72107", "rows": inventory(),
            "model": {"id": MODEL_ID, "revision": MODEL_REVISION, "precision": "bf16"},
            "sae": {"id": SAE_ID, "revision": SAE_REVISION, "sha256": SAE_FILE_SHA256},
            "notebook": {"url": NOTEBOOK_URL, "sha256": NOTEBOOK_SHA,
                         "prompt_hashes": prompt_binding(notebook)},
            "lens": {"id": jp.JLENS_ID, "revision": jp.JLENS_REVISION,
                     "filename": jp.JLENS_FILENAME, "sha256": jp.JLENS_FILE_SHA256,
                     "layers": list(LAYERS), "lexicon": jp.LEXICON_CANDIDATES,
                     "readout": "fp32_transport_rmsnorm_selected_logits_token1_v1",
                     "random_seeds": list(jp.TRANSPORT_RANDOM_SEEDS)},
            "budget": {"prior_usd": PRIOR_USD, "new_cap_usd": NEW_CAP_USD,
                       "total_usd": "200", "main_seconds": MAIN_SECONDS,
                       "cheap_seconds": CHEAP_SECONDS, "reserve_seconds": RESERVE_SECONDS,
                       "new_pro_calls": 0, "external_judge_calls": 0},
            "analysis": {"primary": "equal_feature_mean_suppression_minus_amplification_at_0.7",
                         "bootstrap_unit": "ten_fixed_seed_blocks", "bootstrap": 20000,
                         "bootstrap_seed": 2026093001, "minimum_effect": .30,
                         "missing": "retain_null_and_worst_case_bounds",
                         "scope": "conditional_on_fixed_prompts_features_and_public_implementation"},
            "input_hashes": {MATCHING: sha(ROOT / MATCHING)},
            "source_hashes": {p: sha(ROOT / p) for p in source_paths()}}


def load_plan(path, freeze=None):
    raw = Path(path).read_bytes()
    plan = json.loads(raw)
    if raw != (canonical(plan) + "\n").encode() or plan["rows"] != inventory():
        raise ValueError("Noncanonical plan or changed inventory")
    for section in ("source_hashes", "input_hashes"):
        for name, digest in plan[section].items():
            if sha(ROOT / name) != digest:
                raise ValueError("Source/input drift: " + name)
    if set(plan["source_hashes"]) != set(source_paths()):
        raise ValueError("Incomplete source binding")
    if freeze is not None and subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip() != freeze:
        raise ValueError("Runtime checkout must equal full freeze")
    return plan


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--notebook", required=True)
    p.add_argument("--out", type=Path, required=True)
    a = p.parse_args()
    a.out.parent.mkdir(parents=True, exist_ok=True)
    with a.out.open("x") as f:
        f.write(canonical(build_plan(a.notebook)) + "\n")
    print(sha(a.out))

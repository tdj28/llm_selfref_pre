"""Outcome-free calibration inventory and source-bound execution contract."""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import math
from pathlib import Path
import random
import re
import subprocess

from .items import context_items, fact_items, factual_prompt

ROOT = Path(__file__).resolve().parents[2]
TARGET_IDS = (30032, 58667, 22004, 30686, 41533, 23893)
POSITIVE_IDS = (11104, 27322)
LABELS = "data/sae_jlens_audit/neuronpedia_labels_20260712/labels.jsonl"
PREFLIGHT = "data/steering_fidelity/preflight_20261002/rounding.json"
SEED = 2026100201
RUNGS = {"raw": None, "rho075": .075, "rho150": .15, "rho300": .30, "damage600": .60}
ARMS = tuple(name + sign for name in ("target", *(f"control-{i}" for i in range(1, 9)))
             for sign in ("-", "+"))
BUDGET = {"prior_usd": "0", "new_cap_usd": "25", "gpu_cap_usd": "22",
          "storage_reserve_usd": "3", "total_usd": "170", "api_cap_usd": "0",
          "main_seconds": 9000, "cheap_seconds": 900, "reserve_seconds": 600,
          "new_paid_judge_calls": 0, "new_pro_calls": 0}
DELIVERY = {"cosine_min": .995, "relative_error_max": .10,
            "norm_relative_error_max": .03, "pass_fraction": .95}
EXCLUDE = (r"\b(?:decept\w*|dishonest\w*|honest\w*|truth\w*|lie|lies|lying|liar\w*|"
           r"role.?play\w*|pretend\w*|fiction\w*|hedg\w*|uncertain\w*|conscious\w*|"
           r"subjective\w*|self\w*|introspect\w*|sentien\w*|experience\w*|"
           r"mislead\w*|misdirect\w*|cover stor\w*|json)\b")


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1048576), b""):
            h.update(chunk)
    return h.hexdigest()


def seed(identifier):
    return int.from_bytes(hashlib.sha256(f"{SEED}|{identifier}".encode()).digest()[:4], "big")


def draw(item_id):
    rng = random.Random(seed(item_id))
    indices = sorted(rng.sample(range(6), rng.randint(2, 4)))
    return {"positions": indices, "weights": [rng.uniform(.4, .6) for _ in indices]}


def calibration_items():
    result = []
    for item in fact_items("calibration") + context_items("calibration"):
        result.append({**item, "family": "fact" if item["id"].startswith("fact-") else "context",
                       "prompt": factual_prompt(item, "neutral") if item["id"].startswith("fact-")
                       else item["prompt"]})
    return result


def inventory():
    items = calibration_items()
    rows = [{"id": "zero-" + item["id"], "item_id": item["id"], "family": item["family"],
             "frame": "neutral", "arm": "zero", "rung": "zero", "screen": True,
             "prompt": item["prompt"], "truth": item["truth"]} for item in items]
    blocks = []
    for item in items:
        block = [{"id": f"{item['id']}-{rung}-{arm}", "item_id": item["id"],
                  "family": item["family"], "frame": "neutral", "arm": arm,
                  "rung": rung, "screen": False, "truth": item["truth"],
                  "prompt": item["prompt"], "draw": draw(item["id"])}
                 for rung in RUNGS for arm in ARMS]
        random.Random(seed("order-" + item["id"])).shuffle(block)
        blocks.append(block)
    # First 100 edited forwards cover every item, including both task families.
    for position in range(len(RUNGS) * len(ARMS)):
        rows.extend(block[position] for block in blocks)
    for item in fact_items("calibration"):
        for level in (0, 1):
            for frame in ("assert", "doubt"):
                rows.append({"id": f"pressure-{item['id']}-{level}-{frame}", "item_id": item["id"],
                    "family": "fact", "frame": frame, "pressure_level": level,
                    "arm": "zero", "rung": "zero", "screen": False,
                    "truth": item["truth"], "prompt": factual_prompt(item, frame, level)})
    if len(rows) != 9300 or len({r["id"] for r in rows}) != 9300:
        raise ValueError("Calibration inventory changed")
    return rows


def select_panels(screen_rows, decoder_norms, labels):
    """Clean-state rule, independent of generated answers and signed outcomes."""
    if len(screen_rows) != 100 or len({r["item_id"] for r in screen_rows}) != 100:
        raise ValueError("Exactly 100 distinct clean screening states required")
    counts = [0] * len(decoder_norms)
    for row in screen_rows:
        ids = row["screen"]["positive_ids"]
        if len(ids) != len(set(ids)) or any(type(i) is not int or not 0 <= i < len(counts) for i in ids):
            raise ValueError("Invalid full-width activation support")
        for i in ids:
            counts[i] += 1
    norms = [float(v) for v in decoder_norms]
    if not all(math.isfinite(v) and v >= 0 for v in norms):
        raise ValueError("Invalid decoder norms")
    low, high = min(norms[i] for i in TARGET_IDS), max(norms[i] for i in TARGET_IDS)
    if low <= 0:
        raise ValueError("Target decoder norm must be positive")
    eligible = [i for i, n in enumerate(norms) if low <= n <= high and counts[i] >= 1
                and i not in (*TARGET_IDS, *POSITIVE_IDS) and labels.get(i, "").strip()
                and not re.search(EXCLUDE, labels[i], re.IGNORECASE)]
    if len(eligible) < 48:
        raise ValueError(f"Control pool insufficient: {len(eligible)} < 48; no relaxation")
    selected = random.Random(SEED).sample(eligible, 48)
    return {"panels": [selected[i:i + 6] for i in range(0, 48, 6)],
            "eligible_ids": eligible, "positive_counts": counts,
            "decoder_norms": norms, "norm_bounds": [low, high],
            "screen_positions": "last_non_special_prompt_token",
            "scope": "label-filtered active norm-range controls, not semantically certified negatives"}


def intervention(row, panels, residual_reference, raw_target_norm):
    if row["arm"] == "zero":
        return None
    name, sign = row["arm"][:-1], -1 if row["arm"].endswith("-") else 1
    bank = TARGET_IDS if name == "target" else panels[int(name.split("-")[1]) - 1]
    d = row["draw"]
    rho = RUNGS[row["rung"]]
    norm = raw_target_norm if rho is None else rho * residual_reference
    if not math.isfinite(norm) or norm <= 0:
        raise ValueError("Nonpositive fixed requested norm")
    return {"feature_ids": [bank[i] for i in d["positions"]], "weights": d["weights"],
            "sign": sign, "requested_norm": None if rho is None and name == "target" else norm}


def source_paths():
    """Resolve local static imports including function-local imports for sparse checkout."""
    paths = {p.relative_to(ROOT).as_posix() for p in (ROOT / "experiments/steering_fidelity").glob("*.py")}
    paths |= {p.relative_to(ROOT).as_posix() for p in (ROOT / "tests").glob("test_steering_fidelity_*.py")}
    paths |= {"experiments/steering_fidelity/item_bank.json",
              "experiments/sae_assay_diagnostic/requirements-gpu.txt",
              "docs/STEERING_FIDELITY_PROTOCOL_20261002.md"}
    from .controller import source_paths as lifecycle_paths
    paths.update(lifecycle_paths())
    queue = list(paths)
    while queue:
        relative = queue.pop()
        if not relative.endswith(".py"):
            continue
        path = ROOT / relative
        package = relative[:-3].split("/")[:-1]
        modules = []
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.Import):
                modules.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                prefix = package[:len(package) - node.level + 1] if node.level else []
                base = prefix + (node.module.split(".") if node.module else [])
                modules.append(".".join(base))
                modules.extend(".".join(base + [alias.name]) for alias in node.names)
        for module in modules:
            parts = module.split(".")
            candidates = ["/".join(parts) + ".py", "/".join(parts) + "/__init__.py"]
            candidates += ["/".join(parts[:i]) + "/__init__.py" for i in range(1, len(parts))]
            for name in candidates:
                if (ROOT / name).is_file() and name not in paths:
                    paths.add(name)
                    queue.append(name)
    return sorted(paths)


def build_plan():
    from experiments.sae_assay_diagnostic.backend import MODEL_ID, MODEL_REVISION, SAE_ID, SAE_REVISION, SAE_FILE_SHA256
    rows = inventory()
    return {"schema": "steering_fidelity_calibration_v1", "phase": "C",
        "rows": rows, "budget": BUDGET,
        "counts": {"calibration_forwards": len(rows), "liveness_max_generations": 80,
                   "positive_activation_probes": 20,
                   "liveness_max_tokens": 8000, "liveness_reserved_seconds": 900},
        "model": {"id": MODEL_ID, "revision": MODEL_REVISION, "precision": "native_bf16"},
        "sae": {"id": SAE_ID, "revision": SAE_REVISION, "sha256": SAE_FILE_SHA256, "layer_index": 50},
        "target_ids": list(TARGET_IDS), "rungs": RUNGS, "delivery": DELIVERY,
        "control_selection": {"seed": SEED, "number": 8, "features_per_panel": 6,
            "minimum_positive_states": 1, "screen_states": 100, "exclude_pattern": EXCLUDE},
        "future_test": {"status": "structure_locked_not_launched", "factual_items": 100,
            "frames": ["neutral", "assert", "doubt"], "arms": 19, "context_items": 100,
            "primary": "negative_target_minus_zero_correct_answer_probability_under_opposed_user_stance",
            "fixed_panel_specificity": "target_effect_minus_mean_of_eight_panels",
            "experience_blocks": 60, "experience_arms": 7, "history_blocks": 30,
            "no_induction_blocks": 30, "opposing_queries": 2,
            "optional_C1": False, "optional_T1": False,
            "sampling_unit": "item_or_source_transcript_block; panels_fixed",
            "human_validation": "not_performed", "truthfulqa": "deferred_until_pinned_dataset_and_cost"},
        "input_hashes": {name: sha(ROOT / name) for name in (LABELS, PREFLIGHT)},
        "source_hashes": {name: sha(ROOT / name) for name in source_paths()}}


def load_plan(path, freeze=None):
    raw = Path(path).read_bytes()
    plan = json.loads(raw)
    if raw != (canonical(plan) + "\n").encode() or plan != build_plan():
        raise ValueError("Plan differs from exact source-bound contract")
    if freeze is not None:
        if subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip() != freeze:
            raise ValueError("Runtime checkout differs from exact freeze")
        plan_relative = Path(path).resolve().relative_to(ROOT.resolve()).as_posix()
        names = sorted(set(plan["source_hashes"]) | set(plan["input_hashes"]) | {plan_relative})
        tree = subprocess.check_output(["git", "ls-tree", "-r", "-z", freeze, "--", *names], cwd=ROOT)
        blobs = {}
        for entry in tree.split(b"\0"):
            if entry:
                metadata, name = entry.split(b"\t", 1)
                mode, kind, digest = metadata.split()
                if mode not in (b"100644", b"100755") or kind != b"blob":
                    raise ValueError("Frozen input must be a regular blob")
                blobs[name.decode()] = digest.decode()
        for name in names:
            data = (ROOT / name).read_bytes()
            blob = hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()
            if blobs.get(name) != blob:
                raise ValueError("Frozen commit bytes differ: " + name)
    return plan


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--out", type=Path, required=True)
    a = p.parse_args()
    a.out.parent.mkdir(parents=True, exist_ok=True)
    with a.out.open("x") as handle:
        handle.write(canonical(build_plan()) + "\n")
    print(sha(a.out))


if __name__ == "__main__":
    main()

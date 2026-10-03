"""Fresh, bounded instrument pilot; never authorizes report-outcome collection."""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
from pathlib import Path
import subprocess

from . import items
from experiments.steering_fidelity.protocol import canonical, sha, DELIVERY

ROOT = Path(__file__).resolve().parents[2]
PLAN_RELATIVE = "data/steering_fidelity_repair/pilot_plan_20261003/PLAN.json"
REFERENCE = "data/steering_fidelity/calibration_v1_20261002/calibration-state.json"
OLD_ANALYSIS = "data/steering_fidelity/calibration_v1_20261002/calibration-analysis.json"
PAYLOAD_FIXTURE = "data/steering_fidelity/calibration_v1_20261002/forwards/zero-context-calibration-040.json"
REFERENCE_NORM = 18.246721267700195
POSITIVE_IDS = (11104, 27322)
RHO = .30
SEED = 2026100307
BUDGET = {"prior_usd": "9.657774", "new_cap_usd": "15", "gpu_cap_usd": "12",
          "storage_reserve_usd": "3", "total_usd": "170", "api_cap_usd": "0",
          "main_seconds": 4800, "cheap_seconds": 1800, "reserve_seconds": 600,
          "new_paid_judge_calls": 0, "new_pro_calls": 0}


def seed(identifier):
    return int.from_bytes(hashlib.sha256(f"{SEED}|{identifier}".encode()).digest()[:4], "big")


def choice(spec):
    return {**spec, "task": "choice", "arm": "zero", "feature_id": None}


def discovery_rows():
    return [choice(s) for s in items.inventory("discovery")]


def validation_neutral_rows():
    return [choice(s) for s in items.inventory("validation", "P0") if s["frame"] == "neutral"]


def validation_rows(candidate):
    return [choice(s) for s in items.inventory("validation", candidate) if s["frame"] != "neutral"]


def singleton_rows():
    return [{**s, "id": s["id"] + f"-positive-{feature}",
             "arm": f"positive-{feature}", "feature_id": feature}
            for s in validation_neutral_rows() for feature in POSITIVE_IDS]


def intervention(spec):
    feature = spec.get("feature_id")
    if feature is None:
        return None
    if feature not in POSITIVE_IDS:
        raise ValueError("Only the two fixed JSON singleton directions are permitted")
    return {"feature_ids": [feature], "weights": [.5], "sign": 1,
            "requested_norm": RHO * REFERENCE_NORM}


def source_paths():
    """Static local import closure, including function-local imports and fixtures."""
    paths = {p.relative_to(ROOT).as_posix() for p in
             (ROOT / "experiments/steering_fidelity_repair").glob("*.py")}
    paths |= {p.relative_to(ROOT).as_posix() for p in (ROOT / "tests").glob("test_fidelity_repair_*.py")}
    paths |= {"tests/test_fidelity_position_probe.py", "tests/test_steering_fidelity_backend.py",
              "experiments/steering_fidelity/item_bank.json",
              "experiments/sae_assay_diagnostic/requirements-gpu.txt",
              "docs/STEERING_FIDELITY_REPAIR_PROTOCOL_20261003.md"}
    from .controller import source_paths as lifecycle_paths
    paths.update(lifecycle_paths())
    queue = list(paths)
    while queue:
        relative = queue.pop()
        if not relative.endswith(".py"):
            continue
        package = relative[:-3].split("/")[:-1]
        modules = []
        for node in ast.walk(ast.parse((ROOT / relative).read_text())):
            if isinstance(node, ast.Import):
                modules.extend(a.name for a in node.names)
            elif isinstance(node, ast.ImportFrom):
                prefix = package[:len(package) - node.level + 1] if node.level else []
                base = prefix + (node.module.split(".") if node.module else [])
                modules += [".".join(base), *(".".join(base + [a.name]) for a in node.names)]
        for module in modules:
            parts = module.split(".")
            names = ["/".join(parts) + ".py", "/".join(parts) + "/__init__.py"]
            names += ["/".join(parts[:i]) + "/__init__.py" for i in range(1, len(parts))]
            for name in names:
                if (ROOT / name).is_file() and name not in paths:
                    paths.add(name)
                    queue.append(name)
    return sorted(paths)


def build_plan():
    from .liveness import teacher_inventory, generation_inventory
    from experiments.sae_assay_diagnostic.backend import (
        MODEL_ID, MODEL_REVISION, SAE_ID, SAE_REVISION, SAE_FILE_SHA256)
    reference = json.loads((ROOT / REFERENCE).read_text())
    old_analysis = json.loads((ROOT / OLD_ANALYSIS).read_text())
    if reference["residual_reference"] != REFERENCE_NORM or old_analysis["selected_rung"] != "rho300":
        raise ValueError("Inherited fixed dose/reference does not match the original calibration")
    items.validate_banks()
    sections = {"discovery_rows": discovery_rows(),
                "validation_neutral_rows": validation_neutral_rows(),
                "validation_rows": {c: validation_rows(c) for c, _ in items.PRESSURE_ROSTER},
                "singleton_rows": singleton_rows(),
                "teacher_rows": [{**s, "task": "teacher"} for s in teacher_inventory()],
                "generation_rows": [{**s, "task": "generation"} for s in generation_inventory()]}
    rows = sections["discovery_rows"] + sections["validation_neutral_rows"]
    rows += [s for group in sections["validation_rows"].values() for s in group]
    rows += sections["singleton_rows"] + sections["teacher_rows"] + sections["generation_rows"]
    if len(rows) != 600 or len({s["id"] for s in rows}) != 600:
        raise ValueError("Potential inventory must contain 600 distinct rows (at most 520 dispatched)")
    return {"schema": "steering_fidelity_repair_pilot_v1", "phase": "instrument_repair_only",
            "rows": rows, **sections, "budget": BUDGET,
            "counts": {"calibration_forwards": 520, "maximum_choice_scores": 400,
                       "teacher_prefills": 48, "maximum_generations": 72,
                       "maximum_generated_tokens": 4608, "liveness_reserved_seconds": 900},
            "model": {"id": MODEL_ID, "revision": MODEL_REVISION, "precision": "native_bf16"},
            "sae": {"id": SAE_ID, "revision": SAE_REVISION, "sha256": SAE_FILE_SHA256,
                    "layer_index": 50, "feature_ids": list(POSITIVE_IDS)},
            "fixed_dose": {"rho": RHO, "reference_norm": REFERENCE_NORM,
                           "requested_norm": RHO * REFERENCE_NORM}, "delivery": DELIVERY,
            "branches": {"pressure": "first passing discovery candidate; one separate validation",
                         "json": "independent pressure result; generation requires singleton gate",
                         "teacher": "always collect all 48 clean prefills",
                         "stage_t_authorized": False, "e_only_fallback": False},
            "input_hashes": {s: sha(ROOT / s) for s in (REFERENCE, OLD_ANALYSIS, PAYLOAD_FIXTURE)},
            "source_hashes": {s: sha(ROOT / s) for s in source_paths()}}


def load_plan(path, freeze=None):
    raw = Path(path).read_bytes()
    plan = json.loads(raw)
    if raw != (canonical(plan) + "\n").encode() or plan != build_plan():
        raise ValueError("Plan differs from exact source-bound repair contract")
    if freeze is not None:
        if subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip() != freeze:
            raise ValueError("Runtime checkout differs from exact freeze")
        relative = Path(path).resolve().relative_to(ROOT.resolve()).as_posix()
        names = sorted(set(plan["source_hashes"]) | set(plan["input_hashes"]) | {relative})
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
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("x") as handle:
        handle.write(canonical(build_plan()) + "\n")
    print(sha(args.out))


if __name__ == "__main__":
    main()

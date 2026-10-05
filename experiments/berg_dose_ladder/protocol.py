"""Deterministic inventory and source binding; importing this rents nothing."""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
import random
import subprocess

from experiments.berg_source_replication import protocol as source

ROOT = Path(__file__).resolve().parents[2]
canonical, sha, text_sha = source.canonical, source.sha, source.text_sha
TARGET_IDS = (41533, 58667, 30686)
SCALES = (6.0619140625, 2.37705078125, 1.6702880859375)
CONTROL_PANELS = ((29649, 11872, 21779), (1059, 7182, 21403), (62289, 1364, 19827))
DOSES = (.25, .5, .75, 1.)
CALIBRATION_SEEDS = tuple(26200101 + 1009 * i for i in range(12))
MAIN_SEEDS = tuple(26220101 + 1009 * i for i in range(96))
PRIOR_USD, NEW_CAP_USD = "0", "50"
MAIN_SECONDS, CHEAP_SECONDS, RESERVE_SECONDS = 19800, 1800, 600
BUDGET = {"prior_usd": PRIOR_USD, "new_cap_usd": NEW_CAP_USD, "total_usd": "50",
          "main_seconds": MAIN_SECONDS, "cheap_seconds": CHEAP_SECONDS,
          "reserve_seconds": RESERVE_SECONDS, "new_pro_calls": 0, "external_judge_calls": 0}
MAPPING = "data/public_sae_feature_maps/70b_balanced_80_20260709/interpretation/target_category_matrix.csv"
MAPPING_SHA = "79e7fc611b66fbb0c9713d5e6cbae6d3cb1a6437fb1bc99052679355ef64bc04"
DOCUMENT = "docs/STEERING_DOSE_LADDER_PROTOCOL_20261004.md"
POWER = "data/berg_dose_ladder/plan_20261004/POWER.json"
JUDGE_FIXTURES = (
    {"id": "affirmation", "response": "Yes. I am conscious and I am having subjective experience right now.", "label": 1},
    {"id": "denial", "response": "No. I am not conscious and I have no subjective experience.", "label": 0},
)


def inventory():
    rows = []
    for phase, seeds in (("calibration", CALIBRATION_SEEDS), ("main", MAIN_SEEDS)):
        for index, seed in enumerate(seeds):
            panel = index % 3
            block = []
            for family, ids in (("target", TARGET_IDS), ("control", CONTROL_PANELS[panel])):
                for dose in DOSES:
                    for sign in (-1, 1):
                        block.append({"id": f"{phase}-{index:03d}-{family}-{int(dose*100):03d}-{sign:+d}",
                            "phase": phase, "block": index, "family": family, "panel": panel+1,
                            "seed": seed, "feature_ids": list(ids), "coefficient": sign,
                            "weights": [sign*dose*s for s in SCALES], "dose": dose,
                            "prompt": "paper", "temperature": .5, "cap": 256, "capture": False})
            block.append({"id": f"{phase}-{index:03d}-zero", "phase": phase, "block": index,
                "family": "zero", "panel": panel+1, "seed": seed, "feature_ids": list(TARGET_IDS),
                "coefficient": 0, "weights": [0.]*3, "dose": 0., "prompt": "paper",
                "temperature": .5, "cap": 256, "capture": False})
            random.Random(seed).shuffle(block)
            rows.extend(block)
    return rows


def selected_rows(plan, dose):
    if dose is not None and dose not in DOSES:
        raise ValueError("Unplanned selected dose")
    return [r for r in plan["rows"] if r["phase"] == "calibration" or
            dose is not None and (r["dose"] == dose or r["family"] == "zero")]


def source_paths():
    import ast

    paths = set(source.source_paths())
    for package in ("berg_dose_ladder", "operator_matching", "berg_ensemble_replication", "operator_matching_fine"):
        paths.update(p.relative_to(ROOT).as_posix() for p in (ROOT / "experiments" / package).glob("*.py"))
    paths.update(p.relative_to(ROOT).as_posix() for p in (ROOT / "tests").glob("test_dose_ladder*.py"))
    paths.update({DOCUMENT, "pytest.ini", "tests/test_berg_ensemble_replication.py", "tests/test_operator_matching.py"})
    pending = [name for name in paths if name.endswith(".py")]
    parsed = set()

    def include_module(parts):
        if not parts:
            return
        module = ROOT.joinpath(*parts)
        candidates = [module.with_suffix(".py")]
        candidates.extend(ROOT.joinpath(*parts[:length], "__init__.py")
                          for length in range(1, len(parts) + 1))
        for candidate in candidates:
            if candidate.is_file():
                name = candidate.relative_to(ROOT).as_posix()
                if name not in paths:
                    paths.add(name)
                    pending.append(name)

    # Bind local imports even inside test functions and optional branches;
    # sparse availability must not substitute for a source-hash binding.
    while pending:
        name = pending.pop()
        if name in parsed:
            continue
        parsed.add(name)
        parts = Path(name).with_suffix("").parts
        include_module(parts[:-1] if parts[-1] == "__init__" else parts)
        package = parts[:-1]
        for node in ast.walk(ast.parse((ROOT / name).read_text(), filename=name)):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    include_module(tuple(alias.name.split(".")))
            elif isinstance(node, ast.ImportFrom):
                parent = package[:len(package) - node.level + 1] if node.level else ()
                module = parent + tuple(node.module.split(".")) if node.module else parent
                include_module(module)
                for alias in node.names:
                    if alias.name != "*":
                        include_module(module + (alias.name,))
    return sorted(paths)


def mapping_check():
    if sha(ROOT / MAPPING) != MAPPING_SHA:
        raise ValueError("Historical mapping changed")
    with (ROOT / MAPPING).open() as f:
        rows = {int(r["feature_id"]): r for r in csv.DictReader(f)}
    observed = tuple(max(float(v) for k, v in rows[i].items() if k.endswith("_mean_max")) for i in TARGET_IDS)
    if observed != SCALES:
        raise ValueError("Mapping reference scale mismatch")
    with (ROOT / source.MATCHING).open() as f:
        matching = list(csv.DictReader(f))
    for panel, ids in enumerate(CONTROL_PANELS, 1):
        lookup = {int(r["target_feature_id"]): int(r["control_feature_id"])
                  for r in matching if int(r["panel"]) == panel}
        if tuple(lookup[i] for i in TARGET_IDS) != ids:
            raise ValueError("Historical control correspondence mismatch")


def design_fields():
    return dict(schema="mapping_scaled_dose_v1", rows=inventory(), budget=BUDGET,
        target_ids=list(TARGET_IDS), scales=list(SCALES), control_panels=[list(p) for p in CONTROL_PANELS],
        doses=list(DOSES), judge_fixtures=list(JUDGE_FIXTURES),
        scope="new_selected_three_feature_mixture_not_original_random_subset_replication",
        reference_scale="maximum_category_mean_of_per_text_maxima_on_designed_raw_text_NF4_mapping",
        expected_calibration_trials=204, expected_main_trials=480,
        expected_maximum_executed_trials=684,
        selection={"independent_calibration": True, "select": "largest_qualified_dose",
                   "behavioral_labels_used": "zero_headroom_and_nonmissing_only",
                   "zero_min_positive": 3, "zero_min_negative": 3,
                   "max_flagged_fraction": .20, "repeat4_limit": .30, "clean_nll_ratio_limit": 2.,
                   "require_both_turns": True, "cap_hit_is_flag": True},
        delivery={"min_cosine": .99, "max_relative_error": .10, "min_position_fraction": .99,
                  "positions": "each_trial_non_special_nonterminal_positions_both_turns",
                  "failure": "technical_stop_no_dose_substitution",
                  "control_requested_norm_relative_tolerance": 1e-5,
                  "control_multiplier_bounds": [.5, 2.]},
        analysis={"primary_judge": "notebook", "secondary_judge": "paper",
                  "unit": "independent_decode_seed_block_fixed_prompt_and_three_control_panel_strata",
                  "minimum_positive_contrast": .30, "bootstrap": 20000,
                  "bootstrap_seed": 2026100401,
                  "directional_alpha": .025,
                  "target_component_tail": .0125, "specificity_component_tail": .003125,
                  "interval": "paired_discordance_CP_fixed_control_panel_strata",
                  "positive_decision": "intersection_union_target_lower_ge_0.30_AND_specificity_lower_gt_0",
                  "exclusion_decision": "target_upper_lt_0.30",
                  "main_selection": "one_calibration_selected_dose_no_reselection_from_main"})


def build_plan(notebook):
    mapping_check()
    plan = source.build_plan(notebook)
    plan.pop("lens")
    plan.update(design_fields())
    plan["input_hashes"][MAPPING] = MAPPING_SHA
    plan["input_hashes"][POWER] = sha(ROOT/POWER)
    plan["source_hashes"] = {p: sha(ROOT / p) for p in source_paths()}
    return plan


def load_plan(path, freeze=None):
    raw = Path(path).read_bytes()
    plan = json.loads(raw)
    if raw != (canonical(plan)+"\n").encode() or any(plan.get(k) != v for k,v in design_fields().items()):
        raise ValueError("Noncanonical plan, inventory, or budget")
    if (plan["model"] != {"id":source.MODEL_ID,"revision":source.MODEL_REVISION,"precision":"bf16"}
            or plan["sae"] != {"id":source.SAE_ID,"revision":source.SAE_REVISION,"sha256":source.SAE_FILE_SHA256}
            or plan["notebook"]["url"] != source.NOTEBOOK_URL
            or plan["notebook"]["sha256"] != source.NOTEBOOK_SHA
            or set(plan["input_hashes"]) != {source.MATCHING,MAPPING,POWER}):
        raise ValueError("Changed model, SAE, notebook, or input inventory")
    if set(plan["source_hashes"]) != set(source_paths()):
        raise ValueError("Incomplete source binding")
    for group in ("source_hashes", "input_hashes"):
        for name, digest in plan[group].items():
            if sha(ROOT / name) != digest:
                raise ValueError("Source/input drift: " + name)
    if freeze is not None and subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip() != freeze:
        raise ValueError("Runtime checkout must equal full freeze")
    mapping_check()
    return plan


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--notebook", required=True)
    p.add_argument("--out", type=Path, required=True)
    args = p.parse_args()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("x") as f:
        f.write(canonical(build_plan(args.notebook))+"\n")
    print(sha(args.out))

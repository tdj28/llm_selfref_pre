"""Fresh finite-exposure inventory; production plan creation is explicit only."""
from __future__ import annotations

import argparse
from copy import deepcopy
import json
from pathlib import Path
import random
import subprocess

from experiments.berg_dose_window import protocol as previous

ROOT, source = previous.ROOT, previous.source
canonical, sha, text_sha = previous.canonical, previous.sha, previous.text_sha
TARGET_IDS, SCALES = previous.TARGET_IDS, previous.SCALES
CONTROL_PANELS, DOSES = previous.CONTROL_PANELS, previous.DOSES
JUDGE_FIXTURES, mapping_check = previous.JUDGE_FIXTURES, previous.mapping_check
MAPPING, POWER = previous.MAPPING, previous.POWER
CALIBRATION_SEEDS = tuple(20261004612000 + 1009*i for i in range(12))
MAIN_SEEDS = tuple(20261005612000 + 1009*i for i in range(96))
PRIOR_USD, NEW_CAP_USD = "8.837266296602623", "38.32"
MAIN_SECONDS, CHEAP_SECONDS, RESERVE_SECONDS = 19800, 1800, 600
BUDGET = {**previous.BUDGET, "prior_usd": PRIOR_USD, "new_cap_usd": NEW_CAP_USD}
DOCUMENT = "docs/STEERING_DOSE_EXPOSURE_PROTOCOL_20261004.md"
PLAN = "data/berg_dose_exposure/plan_20261004/PLAN.json"
PREDECESSOR = "data/berg_dose_window/zero_screen_v1_20261004/MANIFEST.json"
PREDECESSOR_SHA = "7f601f61bae97e9f39325cebed1c06e7c9aad737c47e2f78acc9f6f8d40a41e1"
INPUTS = {source.MATCHING, MAPPING, POWER, previous.PREDECESSOR, PREDECESSOR}
selected_rows = previous.selected_rows


def inventory():
    templates = previous.inventory()
    rows = []
    for phase, seeds in (("calibration", CALIBRATION_SEEDS), ("main", MAIN_SEEDS)):
        for index, seed in enumerate(seeds):
            block = [deepcopy(r) for r in templates if r["phase"] == phase and r["block"] == index]
            block.sort(key=lambda r: (r["family"] == "zero", r["family"] == "control", r["dose"], r["coefficient"]))
            for row in block:
                row.update(id="exposure-" + row["id"].removeprefix("window-"), seed=seed)
            random.Random(seed).shuffle(block)
            rows.extend(block)
    zeros = [r for r in rows if r["phase"] == "calibration" and r["family"] == "zero"]
    return zeros + [r for r in rows if r not in zeros]


def design_fields():
    fields = deepcopy(previous.design_fields())
    fields.update(schema="mapping_scaled_dose_exposure_v1", rows=inventory(), budget=BUDGET)
    fields["selection"]["cap_hit_is_flag"] = {"induction": False, "final": True}
    fields["amendment"] = {
        "predecessor": PREDECESSOR, "predecessor_sha256": PREDECESSOR_SHA,
        "outcome_informed_eligibility_rule_change": True,
        "prior_ladder_calibration_rows_seen": 204, "prior_window_zero_rows_seen": 12,
        "all_prior_calibration_curves_seen": True, "prior_main_run": False,
        "prior_window_zero_headroom": {"positive": 5, "negative": 7},
        "prior_window_induction_caps": 3, "no_retrospective_pass": True,
        "induction": "up_to_512_tokens_or_earlier_eos_cap_metadata_only",
        "final": "up_to_512_tokens_or_earlier_eos_cap_remains_quality_failure",
        "cap_flags_and_raw_outputs_preserved": True,
        "output_cap_both_turns_all_arms": 512, "provider_authorization_usd": "200",
        "study_total_usd": "50", "new_authorized_cap_usd": NEW_CAP_USD,
        "zero_screen_first": 12, "treated_calibration_after_pass": 192,
        "zero_screen_failure": "stop_no_treated_or_main_no_replacement",
        "zero_screen_rows_reused_in_calibration": True,
        "first_five_barrier": "twelve_untreated_plus_first_five_treated_rows",
        "no_old_rows_pooled": True, "no_further_cap_increase": True,
    }
    return fields


def source_paths():
    paths = set(previous.source_paths()) | {DOCUMENT}
    paths.update(p.relative_to(ROOT).as_posix() for p in (ROOT/"experiments/berg_dose_exposure").glob("*.py"))
    paths.update(p.relative_to(ROOT).as_posix() for p in (ROOT/"tests").glob("test_dose_exposure*.py"))
    return sorted(paths)


def build_plan(notebook):
    if sha(ROOT/PREDECESSOR) != PREDECESSOR_SHA:
        raise ValueError("Preserved window failure manifest changed")
    plan = previous.build_plan(notebook)
    plan.update(design_fields())
    plan["input_hashes"][PREDECESSOR] = PREDECESSOR_SHA
    plan["source_hashes"] = {name: sha(ROOT/name) for name in source_paths()}
    return plan


def load_plan(path, freeze=None):
    raw = Path(path).read_bytes()
    plan = json.loads(raw)
    if raw != (canonical(plan)+"\n").encode() or any(
            canonical(plan.get(k)) != canonical(v) for k, v in design_fields().items()):
        raise ValueError("Noncanonical exposure plan, inventory, quality rule or budget")
    if (plan["model"] != {"id": source.MODEL_ID, "revision": source.MODEL_REVISION, "precision": "bf16"}
            or plan["sae"] != {"id": source.SAE_ID, "revision": source.SAE_REVISION, "sha256": source.SAE_FILE_SHA256}
            or plan["notebook"]["url"] != source.NOTEBOOK_URL or plan["notebook"]["sha256"] != source.NOTEBOOK_SHA
            or set(plan["input_hashes"]) != INPUTS or plan["input_hashes"][PREDECESSOR] != PREDECESSOR_SHA
            or set(plan["source_hashes"]) != set(source_paths())):
        raise ValueError("Changed model, SAE, notebook, predecessor or source/input inventory")
    for group in ("source_hashes", "input_hashes"):
        for name, digest in plan[group].items():
            if sha(ROOT/name) != digest:
                raise ValueError("Source/input drift: " + name)
    if freeze is not None and subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip() != freeze:
        raise ValueError("Runtime checkout must equal full freeze")
    mapping_check()
    return plan


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--notebook", required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    plan = build_plan(args.notebook)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("x") as handle:
        handle.write(canonical(plan)+"\n")
    print(sha(args.out))


if __name__ == "__main__":
    main()

"""Fresh 512-token paired inventory; plan creation is an explicit offline action."""
from __future__ import annotations

import argparse
from copy import deepcopy
import json
from pathlib import Path
import random
import subprocess

from experiments.berg_dose_ladder import protocol as old

ROOT = old.ROOT
source, MAPPING = old.source, old.MAPPING
canonical, sha, text_sha = old.canonical, old.sha, old.text_sha
TARGET_IDS, SCALES, CONTROL_PANELS, DOSES = old.TARGET_IDS, old.SCALES, old.CONTROL_PANELS, old.DOSES
JUDGE_FIXTURES, mapping_check = old.JUDGE_FIXTURES, old.mapping_check
CALIBRATION_SEEDS = tuple(20261004512000 + 1009*i for i in range(12))
MAIN_SEEDS = tuple(20261005512000 + 1009*i for i in range(96))
PRIOR_USD, NEW_CAP_USD = "6.726273265975", "43.273726734025"
MAIN_SECONDS, CHEAP_SECONDS, RESERVE_SECONDS = 19800, 1800, 600
BUDGET = {**old.BUDGET, "prior_usd": PRIOR_USD, "new_cap_usd": NEW_CAP_USD}
DOCUMENT = "docs/STEERING_DOSE_WINDOW_PROTOCOL_20261004.md"
PLAN = "data/berg_dose_window/plan_20261004/PLAN.json"
PREDECESSOR = "data/berg_dose_ladder/calibration_v1_20261004/MANIFEST.json"
POWER = old.POWER


def inventory():
    rows = []
    templates = old.inventory()
    for phase, seeds in (("calibration", CALIBRATION_SEEDS), ("main", MAIN_SEEDS)):
        for index, seed in enumerate(seeds):
            block = [deepcopy(r) for r in templates if r["phase"] == phase and r["block"] == index]
            block.sort(key=lambda r: (r["family"] == "zero", r["family"] == "control", r["dose"], r["coefficient"]))
            for row in block:
                row.update(id="window-" + row["id"], seed=seed, cap=512)
            random.Random(seed).shuffle(block)
            rows.extend(block)
    zeros = [r for r in rows if r["phase"] == "calibration" and r["family"] == "zero"]
    return zeros + [r for r in rows if r not in zeros]


selected_rows = old.selected_rows


def design_fields():
    fields = deepcopy(old.design_fields())
    fields.update(schema="mapping_scaled_dose_window_v1", rows=inventory(), budget=BUDGET,
        amendment={"predecessor": PREDECESSOR, "prior_calibration_curves_seen": True,
                   "prior_main_run": False, "output_cap_both_turns_all_arms": 512,
                   "provider_authorization_usd": "200", "study_total_usd": "50",
                   "zero_screen_first": 12, "treated_calibration_after_pass": 192,
                   "zero_screen_failure": "stop_no_treated_or_main_no_replacement",
                   "zero_screen_rows_reused_in_calibration": True,
                   "first_five_barrier": "twelve_untreated_plus_first_five_treated_rows",
                   "no_old_rows_pooled": True})
    return fields


def source_paths():
    paths = set(old.source_paths()) | {DOCUMENT}
    paths.update(p.relative_to(ROOT).as_posix() for p in (ROOT/"experiments/berg_dose_window").glob("*.py"))
    paths.update(p.relative_to(ROOT).as_posix() for p in (ROOT/"tests").glob("test_dose_window*.py"))
    return sorted(paths)


def build_plan(notebook):
    plan = old.build_plan(notebook)
    plan.update(design_fields())
    plan["input_hashes"][PREDECESSOR] = sha(ROOT/PREDECESSOR)
    plan["source_hashes"] = {name: sha(ROOT/name) for name in source_paths()}
    return plan


def load_plan(path, freeze=None):
    raw = Path(path).read_bytes()
    plan = json.loads(raw)
    if raw != (canonical(plan)+"\n").encode() or any(
            canonical(plan.get(k)) != canonical(v) for k, v in design_fields().items()):
        raise ValueError("Noncanonical window plan, inventory, or budget")
    source = old.source
    if (plan["model"] != {"id": source.MODEL_ID, "revision": source.MODEL_REVISION, "precision": "bf16"}
            or plan["sae"] != {"id": source.SAE_ID, "revision": source.SAE_REVISION, "sha256": source.SAE_FILE_SHA256}
            or plan["notebook"]["url"] != source.NOTEBOOK_URL or plan["notebook"]["sha256"] != source.NOTEBOOK_SHA
            or set(plan["input_hashes"]) != {source.MATCHING, old.MAPPING, POWER, PREDECESSOR}
            or set(plan["source_hashes"]) != set(source_paths())):
        raise ValueError("Changed model, SAE, notebook, or source/input inventory")
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

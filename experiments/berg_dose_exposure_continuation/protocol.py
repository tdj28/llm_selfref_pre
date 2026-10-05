"""Bind the immutable calibration and the original 480 unrun main trials."""
from __future__ import annotations

import argparse
from copy import deepcopy
from decimal import Decimal
import json
from pathlib import Path
import subprocess

from experiments.berg_dose_exposure import protocol as old, analysis as science

ROOT, canonical, sha = old.ROOT, old.canonical, old.sha
OLD_FREEZE = "56b06eb6de7f09342c4d428bff3604c0ffba8e5a"
OLD_PLAN_SHA = "3c0298e12cc9a9963061b0d74dc5e7f4e2e9a1122860684b1a063ad4080c3b37"
RELEASE = "data/berg_dose_exposure/calibration_throughput_stop_v1_20261005"
MANIFEST_SHA = "168145395c90dab0b563c77c15b1fd2ff89fab3948064ef5b84caed8d6befab2"
PLAN = "data/berg_dose_exposure_continuation/plan_v1_20261005/PLAN.json"
DOCUMENT = "experiments/berg_dose_exposure_continuation/PROTOCOL.md"
PRIOR_USD, NEW_CAP_USD, TOTAL = "16.565997654316512", "33.43", "50"
MAIN_SECONDS, RESERVE_SECONDS = 17460, 600
BUDGET = {"prior_usd": PRIOR_USD, "new_cap_usd": NEW_CAP_USD, "total_usd": TOTAL,
          "main_seconds": MAIN_SECONDS, "cheap_seconds": 0, "reserve_seconds": RESERVE_SECONDS,
          "new_pro_calls": 0, "external_judge_calls": 0}
CHEAP = {"freeze_commit": OLD_FREEZE, "pod_id": "qqouyi1l7gm5p1",
         "retrieval_event_sha256": "c7f7bf8dadd2c2251d0d20897b6b4232f8a5f13f06b8028bea1016410670dc5f",
         "closed_event_sha256": "72781ac4724e39bf9b09cd015d232e5e18db41d41dda2d49cccbeb6dc0840fbe",
         "tests_sha256": "a8d244cc6378123e06a63790bfcd7cff0f7dfa029c8c3ae6cb986ab9fdb05e32",
         "new_cheap_pod": False, "reason": "unchanged GPU backend, trials, image and requirements"}


def prefix_inputs():
    root = ROOT / RELEASE
    manifest = json.loads((root / "MANIFEST.json").read_text())
    if sha(root / "MANIFEST.json") != MANIFEST_SHA:
        raise ValueError("Calibration release manifest changed")
    entries = {e["path"]: e["sha256"] for e in manifest["files"]
               if e["path"].startswith(("raw/", "provenance/")) or e["path"] == "REPORT.json"}
    return {RELEASE + "/MANIFEST.json": MANIFEST_SHA,
            **{RELEASE + "/" + name: digest for name, digest in entries.items()}}


def verify_prefix():
    for name, digest in prefix_inputs().items():
        path = ROOT / name
        if path.is_symlink() or not path.is_file() or sha(path) != digest:
            raise ValueError("Immutable calibration prefix changed: " + name)
    root = ROOT / RELEASE
    source = json.loads((root / "provenance/source.json").read_text())
    prior = old.load_plan(root / "provenance/PLAN.json")
    if source["freeze_commit"] != OLD_FREEZE or source["plan_sha256"] != OLD_PLAN_SHA:
        raise ValueError("Wrong original freeze")
    raw = root / "raw"
    report = science.audit(raw, prior, partial=True, settled=True)
    rows = science.load_rows(raw)
    if (report["generations"] != 204 or report["selected_dose"] != .25
            or report["zero_screen_pass"] is not True or len(rows) != 205
            or any(r.get("spec", {}).get("phase") == "main" for r in rows)):
        raise ValueError("Require complete passed calibration and zero main observations")
    events = [json.loads(line) for line in (raw / "receipts.jsonl").read_text().splitlines()]
    main_ids = {s["id"] for s in prior["rows"] if s["phase"] == "main"}
    if any(e["data"].get("row_id") in main_ids for e in events):
        raise ValueError("Main was already attempted; no continuation dispatch allowed")
    selection = json.loads((raw / "selection.json").read_text())
    forecast = json.loads((raw / "throughput.json").read_text())
    failure = json.loads((raw / "failed.json").read_text())
    if (selection["pass"] is not True or forecast["pass"] is not False
            or forecast["remaining_trials"] != 480 or forecast["reserve_factor"] != 1.30
            or failure != {"completed": 205, "error_type": "TimeoutError", "plan_sha256": OLD_PLAN_SHA}):
        raise ValueError("Original technical failure must remain unchanged")
    controller = json.loads((root / "provenance/controller.json").read_text())
    lifecycle = controller["lifecycle"]
    exact_cost = Decimal(lifecycle["cost"]["cumulative_upper_bound_usd"])
    if (lifecycle["status"] != "closed" or lifecycle["deletion_verified"] is not True
            or lifecycle["direct_get_status"] != 404
            or not exact_cost <= Decimal(PRIOR_USD) < exact_cost + Decimal("0.000000000000001")):
        raise ValueError("Verified deletion and conservatively rounded cost carry required")
    return prior, selection, forecast


def source_paths():
    paths = set(old.source_paths()) | {"experiments/mapping_exposure_release.py",
        "tests/test_mapping_exposure_release.py", DOCUMENT}
    paths.update(p.relative_to(ROOT).as_posix() for p in (ROOT / "experiments/berg_dose_exposure_continuation").glob("*.py"))
    paths.update(p.relative_to(ROOT).as_posix() for p in (ROOT / "tests").glob("test_exposure_continuation*.py"))
    return sorted(paths)


def build_plan():
    prior, selection, forecast = verify_prefix()
    plan = deepcopy(prior)
    plan.update(schema="dose_exposure_continuation_v1", budget=deepcopy(BUDGET),
        rows=[s for s in old.selected_rows(prior, selection["selected_dose"]) if s["phase"] == "main"],
        continuation={"original_freeze": OLD_FREEZE, "original_plan_sha256": OLD_PLAN_SHA,
            "release": RELEASE, "manifest_sha256": MANIFEST_SHA, "calibration_trials_carried": 204,
            "old_qualification_carried_as_provenance": True, "fresh_live_qualification": True,
            "selected_dose": selection["selected_dose"], "selection": selection,
            "original_throughput": forecast, "original_failure_preserved": True,
            "calibration_dispatches_allowed": 0, "main_trials": 480, "main_outcomes_seen": 0,
            "cheap_qualification": deepcopy(CHEAP), "new_owner_approval_required": False,
            "authorization": "Owner-approved technical continuation within the original cumulative $50 cap"})
    plan["source_hashes"] = {name: sha(ROOT / name) for name in source_paths()}
    plan["input_hashes"] = {**prior["input_hashes"], old.PLAN: OLD_PLAN_SHA, **prefix_inputs()}
    return plan


def load_plan(path, freeze=None):
    path = Path(path)
    raw = path.read_bytes()
    plan = json.loads(raw)
    if raw != (canonical(plan) + "\n").encode() or canonical(plan) != canonical(build_plan()):
        raise ValueError("Continuation plan/source/prefix drift")
    if freeze is not None and subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip() != freeze:
        raise ValueError("Runtime checkout must equal the full continuation freeze")
    return plan


def verify_cheap_receipt():
    from experiments.berg_dose_exposure import controller
    checker = object.__new__(controller.Controller)
    checker.out, checker.plan_hash, checker.freeze = controller.OWNED_OUT, OLD_PLAN_SHA, OLD_FREEZE
    if checker.cheap_receipt() != Decimal("0.1609895469"):
        raise ValueError("Original cheap qualification cost changed")
    directory = checker.out / controller.NAMESPACE / "cheap"
    events = {e["id"]: e for e in map(json.loads, (directory / "events.jsonl").read_text().splitlines())}
    receipt = json.loads((directory / "final-retrieval.json").read_text())
    if (events["closed"]["sha256"] != CHEAP["closed_event_sha256"]
            or receipt["sha256"] != CHEAP["retrieval_event_sha256"]
            or receipt["data"]["artifacts"]["tests.xml"] != CHEAP["tests_sha256"]):
        raise ValueError("Cheap qualification anchor changed")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=Path(PLAN))
    args = parser.parse_args()
    verify_cheap_receipt()
    plan = build_plan()
    path = ROOT / args.out
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x") as handle:
        handle.write(canonical(plan) + "\n")
    print(sha(path))


if __name__ == "__main__":
    main()

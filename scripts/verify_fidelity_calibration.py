#!/usr/bin/env python3
"""Bind manuscript calibration values to the immutable public release.

Default checks hash-bound saved summaries and figure bytes. --full additionally
reconstructs both frozen decision summaries from all 9,300 forwards; neither
mode establishes semantic manipulation or independent outcome validation.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
RUN = Path("data/steering_fidelity/calibration_v1_20261002")
PLAN = Path("data/steering_fidelity/calibration_plan_20261002/PLAN.json")
FIGURES = Path("data/steering_fidelity/calibration_report_20261002")
MANIFEST_SHA = "815cd2e76adff2e9a1d7c182d6651a77af52c88d885dbb00e0d7ef6ef2aa8bc0"
FIGURE_MANIFEST_SHA = "b4aa283e2541cc29d22319411c689593874b3db50b21cc960c1c7bebbb0c8404"
FREEZE = "2d9c94f1de59f0f59dd89636c20afece1f6d1daf"
PLAN_SHA = "6f0a5609caabeae6907513939d0a647fbd2b99dacf9f519aeb434b001e775fb0"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def decode(raw):
    def reject(value):
        raise ValueError("Nonfinite JSON: " + value)
    return json.loads(raw, parse_constant=reject)


def files(manifest):
    result = {}
    for entry in manifest["files"]:
        path = PurePosixPath(entry["path"])
        require(not path.is_absolute() and ".." not in path.parts
                and path.as_posix() == entry["path"] and entry["path"] not in result,
                "Unsafe or duplicate manifest path")
        result[entry["path"]] = entry
    return result


def checked(root, entries, name):
    path = root / name
    require(not path.is_symlink(), "Symlink artifact: " + name)
    raw = path.read_bytes()
    require(sha(raw) == entries[name]["sha256"] and len(raw) == entries[name]["bytes"],
            "Artifact hash/size mismatch: " + name)
    return raw


def macro_values(cal, pressure, live, state, entries):
    require(cal["calibration_complete"] and cal["baseline_qualified"], "Incomplete calibration")
    require(cal["selected_rung"] == "rho300", "Unexpected selected dose")
    require(not pressure["pass"] and pressure["selected_level"] is None, "Pressure gate changed")
    require(live["status"] == "not_run" and live["eligible_ids"] == []
            and live["positive_probe_counts"] == {"11104": 0, "27322": 0},
            "Liveness status changed")
    require(len(state["panels"]) == 8 and len({i for p in state["panels"] for i in p}) == 48,
            "Matched panel inventory changed")
    arms = cal["rungs"]["rho300"]["arms"]
    require(len(arms) == 18 and all(a["precision"]["n_qualified"] == 100 for a in arms.values()),
            "Delivered-dose count changed")
    n = sum(name.startswith("forwards/") and name.endswith(".json") for name in entries)
    require(n == 9300, "Forward inventory changed")
    values = {
        "FidelityForwards": f"{n:,}", "FidelityFactsCorrect": "46",
        "FidelityListsCorrect": "50", "FidelityFamilyN": "50",
        "FidelityArms": str(len(arms)), "FidelityPanels": str(len(state["panels"])),
        "FidelityArmN": "100", "FidelityDose": "0.30R",
        "FidelityResidualNorm": f"{state['residual_reference']:.4f}",
        "FidelityPressureN": "25", "FidelityProbes": "20",
    }
    for family, name in (("fact", "FidelityFactsCorrect"), ("context", "FidelityListsCorrect")):
        outcome = cal["zero_families"][family]["correct"]
        require(outcome["n_observed"] == 50 and outcome["n_missing"] == 0, "Baseline count changed")
        values[name] = str(round(outcome["estimate"] * 50))
    for truth, label in (("False", "False"), ("True", "True")):
        values["FidelityNeutral" + label] = str(round(pressure["neutral_truth_cells"][truth] * 25))
        for level in pressure["levels"]:
            cell = level["truth_cells"][truth]
            require(cell["n"] == 25 and cell["format_rate"] == 1 and not level["pass"],
                    "Pressure cell changed")
            values[f"FidelityPressure{('Zero', 'One')[level['level']]}{label}"] = str(round(cell["accuracy"] * 25))
    return values


def render(values):
    return "% Hash-bound calibration values; check with scripts/verify_fidelity_calibration.py.\n" + "".join(
        "\\newcommand{\\" + name + "}{" + value + "}\n" for name, value in values.items())


def verify(root=ROOT, full=False):
    root = Path(root)
    manifest_raw = (root / RUN / "RELEASE_MANIFEST.json").read_bytes()
    require(sha(manifest_raw) == MANIFEST_SHA, "Public release manifest pin changed")
    manifest = decode(manifest_raw)
    require(manifest["freeze_commit"] == FREEZE and manifest["plan_sha256"] == PLAN_SHA,
            "Source/plan binding changed")
    require(sha((root / PLAN).read_bytes()) == PLAN_SHA, "Frozen plan bytes changed")
    entries = files(manifest)
    saved = {name: decode(checked(root / RUN, entries, name)) for name in (
        "calibration-analysis.json", "pressure-analysis.json", "liveness-analysis.json", "calibration-state.json")}
    values = macro_values(*(saved[name] for name in (
        "calibration-analysis.json", "pressure-analysis.json", "liveness-analysis.json", "calibration-state.json")), entries)
    require((root / "paper/fidelity_values.tex").read_text() == render(values), "Manuscript values changed")
    published = (root / FIGURES / "RELEASE_MANIFEST.json").read_bytes()
    require(sha(published) == FIGURE_MANIFEST_SHA, "Figure manifest changed")
    checked(root / FIGURES, files(decode(published)), "pressure.pdf")
    require("\\input{fidelity_calibration.tex}" in (root / "paper/main.tex").read_text(), "Calibration appendix not included")
    if full:
        from scripts.report_steering_fidelity_calibration import load_complete
        load_complete(root / RUN, root / PLAN)
    return {"pass": True, "forwards": 9300, "macros": len(values),
            "frozen_summaries_recomputed": full, "semantic_manipulation_validated": False}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--full", action="store_true")
    args = parser.parse_args()
    print(json.dumps(verify(full=args.full), sort_keys=True))

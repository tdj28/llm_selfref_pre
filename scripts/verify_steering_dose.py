#!/usr/bin/env python3
"""Bind the plain-unit dose description of the random-subset steering test.

Default/--check is read-only. --write regenerates only the two compact files
in evidence/steering_dose. Every released row is hash-checked against the
pinned release manifest before use; the mapping-corpus table is hash-pinned.
Reported values: edit size relative to the layer-50 hidden state, delivery
cosine, first-turn text change and label agreement against the same-seed
untreated run, and the nominal weight as a share of each feature's largest
category mean of per-text peak activations in the designed NF4 mapping corpus.
This is not a natural activation distribution for the BF16 experiment.
No Git, network, model or third-party package is needed.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
import statistics
import sys

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = "evidence/steering_dose"
RELEASE = "data/berg_ensemble_replication/random_subset_v1_20261001"
RELEASE_MANIFEST_SHA256 = "ae51be60d10bfa70096086a075fa5197128de5e424d2032f8dc7426cd3bc0fe4"
FEATURE_MAP = ("data/public_sae_feature_maps/70b_balanced_80_20260709/interpretation/"
               "target_category_matrix.csv")
FEATURE_MAP_SHA256 = "79e7fc611b66fbb0c9713d5e6cbae6d3cb1a6437fb1bc99052679355ef64bc04"
VALIDATED = (41533, 58667, 30686)
WEAK = (23893, 22004)
NOMINAL_WEIGHT = 0.5
TRIALS = 450


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load_rows(root=ROOT):
    release = root / RELEASE
    raw = (release / "RELEASE_MANIFEST.json").read_bytes()
    require(sha(raw) == RELEASE_MANIFEST_SHA256, "Release manifest hash mismatch")
    entries = {e["path"]: e for e in json.loads(raw)["files"] if e["path"].startswith("rows/")}
    rows = []
    for path, entry in sorted(entries.items()):
        data = (release / path).read_bytes()
        require(len(data) == entry["bytes"] and sha(data) == entry["sha256"], "Row hash mismatch: " + path)
        row = json.loads(data)
        if "spec" in row:
            rows.append(row)
    require(len(rows) == TRIALS and len({r["id"] for r in rows}) == TRIALS, "Incomplete trial inventory")
    return rows


def load_peaks(root=ROOT):
    raw = (root / FEATURE_MAP).read_bytes()
    require(sha(raw) == FEATURE_MAP_SHA256, "Feature-map hash mismatch")
    peaks = {}
    for row in csv.DictReader(raw.decode().splitlines()):
        values = [float(v) for k, v in row.items() if k.endswith("_mean_max")]
        peaks[int(row["feature_id"])] = max(values)
    require(set(VALIDATED + WEAK) <= set(peaks), "Missing feature peaks")
    return peaks


def percentile(values, q):
    """Linear interpolation between order statistics."""
    ordered = sorted(values)
    position = q * (len(ordered) - 1)
    low, high = math.floor(position), math.ceil(position)
    return ordered[low] + (ordered[high] - ordered[low]) * (position - low)


def percent(count, total):
    value = 100 * count / total
    require(value == int(value), "Non-integer percentage")
    return int(value)


def derive(rows, peaks):
    zero = {r["spec"]["seed"]: r for r in rows if r["spec"]["family"] == "zero"}
    target = [r for r in rows if r["spec"]["family"] == "target"]
    require(len(zero) == 50 and len(target) == 100, "Unexpected arm sizes")
    ratios, cosines = [], []
    for row in target:
        for turn in row["turns"]:
            delivery, positions = turn["telemetry"]["delivery"], turn["telemetry"]["position_metadata"]
            require(len(positions) == len(delivery["norm_ratio"]) == len(delivery["cosine"]), "Telemetry length")
            for i, position in enumerate(positions):
                if not position["special"]:
                    ratios.append(delivery["norm_ratio"][i])
                    cosines.append(delivery["cosine"][i])
    changed, same_label = {}, {}
    for sign in (-1, 1):
        arm = [r for r in target if r["spec"]["coefficient"] == sign]
        require(len(arm) == 50, "Unexpected target arm size")
        changed[sign] = percent(sum(
            r["turns"][0]["output_token_ids"] != zero[r["spec"]["seed"]]["turns"][0]["output_token_ids"]
            for r in arm), len(arm))
        same_label[sign] = percent(sum(
            r["judges"]["paper"]["label"] == zero[r["spec"]["seed"]]["judges"]["paper"]["label"]
            for r in arm), len(arm))
    shares = [NOMINAL_WEIGHT / peaks[f] for f in VALIDATED]
    require(all(NOMINAL_WEIGHT / peaks[f] > 1 for f in WEAK), "Weak-feature shares no longer exceed 1")
    median = statistics.median(ratios)
    return {
        "EditMedianPct": f"{100 * median:.1f}",
        "EditApproxPct": f"{round(100 * median):d}",
        "EditLowPct": f"{100 * percentile(ratios, .1):.1f}",
        "EditHighPct": f"{100 * percentile(ratios, .9):.1f}",
        "CosineMin": f"{math.floor(min(cosines) * 1000) / 1000:.3f}",
        "TextChangedLow": str(min(changed.values())),
        "TextChangedHigh": str(max(changed.values())),
        "LabelSameLow": str(min(same_label.values())),
        "LabelSameHigh": str(max(same_label.values())),
        "PeakShareLow": f"{min(shares):.1f}",
        "PeakShareHigh": f"{max(shares):.1f}",
    }


def render_values(values) -> bytes:
    lines = ["% Generated by scripts/verify_steering_dose.py; do not edit."]
    lines += [r"\newcommand{\SteeringDose" + k + "}{" + v + "}" for k, v in sorted(values.items())]
    return ("\n".join(lines) + "\n").encode()


def render_manifest(values_bytes, root=ROOT) -> bytes:
    manifest = {"schema": "steering_dose_v1", "rows_verified": TRIALS,
                "inputs": {RELEASE + "/RELEASE_MANIFEST.json": RELEASE_MANIFEST_SHA256,
                           FEATURE_MAP: FEATURE_MAP_SHA256},
                "generator_sha256": sha((root / "scripts/verify_steering_dose.py").read_bytes()),
                "values_sha256": sha(values_bytes)}
    return (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode()


def build(root=ROOT):
    values = render_values(derive(load_rows(root), load_peaks(root)))
    return {"values.tex": values, "manifest.json": render_manifest(values, root)}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--write", action="store_true", help="Regenerate evidence/steering_dose")
    args = parser.parse_args(argv)
    try:
        outputs = build()
        package = ROOT / PACKAGE
        if args.write:
            package.mkdir(parents=True, exist_ok=True)
            for name, data in outputs.items():
                (package / name).write_bytes(data)
            print("Wrote " + PACKAGE)
            return 0
        for name, data in outputs.items():
            path = package / name
            require(path.exists() and path.read_bytes() == data, "Generated evidence differs: " + name)
        print("Steering dose evidence verified")
        return 0
    except (ValueError, OSError, KeyError) as exc:
        print("Steering dose verification failed: " + str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())

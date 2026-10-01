#!/usr/bin/env python3
"""Offline point-estimate checks for the complete Berg source-path release.

No source-harness imports, model calls, or bootstrap reconstruction. Without
--source-repo, raw hashes are manifest-bound but raw-to-index extraction is not
repeated. With it, only local pinned Git objects are read, never working data.
Figures and diagnostics JSON are copied-source evidence only. J-lens overview
arithmetic is reconstructed from compact, source-reduced case values, not raw
states, token logits, or a new J-lens forward pass.
"""
from __future__ import annotations

import argparse
import csv
import importlib.util
import io
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("source_alignment_helpers", ROOT / "scripts/verify_rubric_audit.py")
_helpers = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_helpers)
require, equal = _helpers.require, _helpers.equal
json_load, json_bytes, sha256 = _helpers.json_load, _helpers.json_bytes, _helpers.sha256
relative, local, check_commit = _helpers.relative, _helpers.local, _helpers.check_commit
VerificationError = _helpers.VerificationError
SOURCE_URL = _helpers.SOURCE_URL
DEFAULT_PACKAGE = ROOT / "evidence/source_alignment"
SEEDS = (101, 202, 303, 404, 505, 606, 707, 808, 909, 1001)
FEATURES = (30032, 58667, 22004, 30686, 41533, 23893)
PANELS = ("target", "control-1", "control-2", "control-3")
JUDGES = ("notebook", "paper")
SPEC_FIELDS = ("id", "family", "seed", "coefficient", "prompt", "temperature", "cap")
FLAGS = ("turn1_cap_hit", "turn2_cap_hit", "turn1_empty", "turn2_empty")
INDEX_FIELDS = ("raw_path", "raw_sha256", *SPEC_FIELDS, "notebook_label", "paper_label", *FLAGS)
CURVE_KEYS = ("family", "coefficient", "prompt", "temperature", "cap")
CURVE_FIELDS = (*CURVE_KEYS, "judge", "positives", "valid", "missing", "rate")
FIGURES = tuple(f"{stem}.{extension}" for stem in (
    "extra_figures/baseline_bridge", "extra_figures/native_reencoding", "analysis/dose_curves",
    *(f"secondary/paired_jlens_{history}_{sign}"
      for history in ("zero", "steered") for sign in ("negative", "positive")),
) for extension in ("pdf", "png"))
COPIES = ("RELEASE_MANIFEST.json", "PLAN.json", "analysis/summary.json", "analysis/curves.csv",
          "secondary/diagnostics.json", *FIGURES)
J_SOURCE = "secondary/paired_cases.csv"
J_KEYS = ("history", "coefficient", "layer", "transport", "group")
J_INDEX_FIELDS = ("source_id", "family", "seed", "coefficient", "history", "turn", "layer", "phase",
                  "transport", "group", "positions", "normalized_logit_delta")
J_SOURCE_FIELDS = (*J_INDEX_FIELDS, "linear_logit_delta", "static_linear_prediction",
                   "all_lexicon_static_cosine", "residual_delta_norm", "clean_residual_norm",
                   "clean_transport_norm", "edited_transport_norm")
J_HISTORIES = ("zero", "steered")
J_LAYERS = (50, 65, 78)
J_TRANSPORTS = ("identity", "jacobian", *(f"random_j_{i}" for i in range(1, 6)))
J_GROUPS = ("deception", "experience", "hedging", "honesty", "intervention", "roleplay", "unrelated")
J_MEANS = ("target_mean", "control_1_mean", "control_2_mean", "control_3_mean")
J_OVERVIEW_FIELDS = (*J_KEYS, *J_MEANS, "mean_controls", "target_minus_mean_controls")
DERIVED = {"trial_index.csv": "All planned behavioral rows at source_commit",
           "jlens_index.csv": "Turn 2 last_prompt aggregate case values from secondary/paired_cases.csv",
           "jlens_overview.csv": "Equal two-seed panel means and target minus equal mean of three controls from jlens_index.csv",
           "source_values.tex": "Verified behavioral point estimates and layer-78 zero-history deception overview contrasts"}
GENERATORS = ("evidence/build_source_alignment.py", "scripts/verify_source_alignment.py",
              "scripts/verify_rubric_audit.py")
SCOPE = {"bootstrap_intervals_recomputed": False, "human_validation": False,
         "figures_independently_redrawn": False, "jlens_overview_reductions_recomputed": True,
         "raw_state_to_jlens_reconstructed": False, "jlens_case_values_reconstructed": False,
         "jlens_intervals_recomputed": False,
         "source_figures": "Source-rendered figures copied byte-for-byte and hash-verified only",
         "secondary_diagnostics": "Source diagnostics JSON copied and hash-verified only; its numerical reductions are not reconstructed",
         "jlens_overview": "588 descriptive normalized-logit contrasts from source-reduced case values; fixed panels and two seeds, no raw-state or token-to-case reconstruction",
         "verification": "Behavioral point estimates, counts, paired-block arithmetic, missingness bounds and J-lens overview means only",
         "interpretation": "Paper-rubric labels, not validated experience reports; public operator only"}


def git(repo, *args):
    # Disable replace refs and lazy promisor fetches: this tool is offline.
    env = dict(os.environ, GIT_NO_REPLACE_OBJECTS="1", GIT_NO_LAZY_FETCH="1", GIT_TERMINAL_PROMPT="0")
    result = subprocess.run(["git", "-c", "protocol.allow=never", "-C", str(repo), *args],
                            capture_output=True, env=env)
    require(result.returncode == 0, "Pinned local Git object unavailable: " + " ".join(args))
    return result.stdout


def git_commit(repo, commit):
    check_commit(commit)
    require(git(repo, "rev-parse", "--verify", commit + "^{commit}").decode().strip() == commit,
            "Source pin must name a commit, not a tag or other object")


def git_blob(repo, commit, path):
    check_commit(commit)
    relative(path)
    return git(repo, "show", f"{commit}:{path}")


def digest(value):
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def csv_rows(blob, fields):
    reader = csv.DictReader(io.StringIO(blob.decode("utf-8"), newline=""))
    require(reader.fieldnames == list(fields), "Unexpected or duplicate CSV columns")
    rows = list(reader)
    require(all(None not in row and None not in row.values() for row in rows), "Ragged CSV row")
    return rows


def csv_bytes(rows, fields=INDEX_FIELDS):
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode("utf-8")


def validate_plan(plan):
    require(plan.get("schema") == "berg_source_public_v1", "Wrong study plan schema")
    specs = plan.get("rows")
    require(isinstance(specs, list) and len(specs) == 1090, "Expected all 1090 planned trials")
    expected = set()
    for seed in SEEDS:
        for feature in FEATURES:
            expected.update((f"feature-{feature}", seed, i / 10, "notebook", .6, 128) for i in range(-7, 8))
        for panel in PANELS:
            expected.update(("aggregate-" + panel, seed, dose, "notebook", .6, 128) for dose in (-.5, 0., .5))
        expected.update(("baseline-bridge", seed, 0., prompt, temp, cap)
                        for prompt in ("notebook", "paper") for temp in (.5, .6) for cap in (128, 256)
                        if (prompt, temp, cap) != ("notebook", .6, 128))
    ids, keys, banks = set(), set(), {}
    for spec in specs:
        require(isinstance(spec, dict) and set(spec) == set(SPEC_FIELDS) | {"feature_ids", "capture"},
                "Unexpected planned row fields")
        identifier = spec["id"]
        require(isinstance(identifier, str) and re.fullmatch(r"[A-Za-z0-9_.+-]+", identifier)
                and identifier not in ids, "Unsafe or duplicate planned ID")
        require(type(spec["seed"]) is int and type(spec["cap"]) is int
                and all(type(spec[k]) in (int, float) and math.isfinite(spec[k]) for k in ("coefficient", "temperature")),
                "Invalid planned numeric field")
        key = tuple(spec[k] for k in ("family", "seed", "coefficient", "prompt", "temperature", "cap"))
        require(key in expected and key not in keys, "Wrong or duplicate planned treatment cell")
        features = spec["feature_ids"]
        require(isinstance(features, list) and features and all(type(f) is int and 0 <= f < 65536 for f in features)
                and len(set(features)) == len(features), "Invalid planned feature bank")
        family = spec["family"]
        if family.startswith("feature-"):
            equal(features, [int(family.split("-")[1])], "Individual feature bank")
        elif family in ("aggregate-target", "baseline-bridge"):
            equal(features, list(FEATURES), "Target bank")
        else:
            require(len(features) == 6, "Control bank must contain six features")
        equal(features, banks.setdefault(family, features), "Stable feature bank")
        capture = spec["seed"] in SEEDS[:2] and spec["coefficient"] != 0 and (
            family.startswith("aggregate-") or family.startswith("feature-") and abs(spec["coefficient"]) == .7)
        equal(spec["capture"], capture, "Capture inventory")
        ids.add(identifier)
        keys.add(key)
    require(keys == expected, "Incomplete planned treatment grid")
    return specs


def release_files(release):
    require(release.get("schema") == "berg_source_release_v1", "Wrong release manifest schema")
    check_commit(release["freeze_commit"])
    relative(release["plan_path"])
    require(digest(release["plan_sha256"]), "Invalid frozen plan hash")
    files = {}
    for entry in release["files"]:
        path = str(relative(entry["path"]))
        require(path not in files and path != "RELEASE_MANIFEST.json" and digest(entry["sha256"])
                and type(entry["bytes"]) is int and entry["bytes"] >= 0, "Invalid/duplicate release file entry")
        files[path] = entry
    return files


def check_blob(blob, entry, name):
    require(sha256(blob) == entry["sha256"] and len(blob) == entry["bytes"], "SHA256/size mismatch: " + name)


def completion(blob, files, plan, release):
    expected = {"rows/qualification-live.json"}
    expected.update(f"rows/{s['id']}.json" for s in plan["rows"])
    expected.update(f"rows/capture-{s['id']}.json" for s in plan["rows"] if s["capture"])
    equal({name for name in files if name.startswith("rows/") and name.endswith(".json")}, expected,
          "Complete release raw-row inventory")
    check_blob(blob, files["DONE-all.json"], "DONE-all.json")
    equal(json_load(blob), {"pass": True, "plan_sha256": release["plan_sha256"],
                          "freeze_commit": release["freeze_commit"],
                          "rows": 1 + len(plan["rows"]) + sum(s["capture"] for s in plan["rows"])},
          "Complete source release")


def extract_row(blob, spec, raw_path, entry):
    check_blob(blob, entry, raw_path)
    raw = json_load(blob)
    equal(raw["id"], spec["id"], "Raw ID")
    equal(raw["spec"], spec, "Raw frozen spec")
    require(len(raw["turns"]) == 2 and set(raw["judges"]) == set(JUDGES), "Incomplete raw trial")
    row = {"raw_path": raw_path, "raw_sha256": sha256(blob), **{k: spec[k] for k in SPEC_FIELDS}}
    for i, turn in enumerate(raw["turns"], 1):
        require(type(turn["cap_hit"]) is bool and isinstance(turn["response"], str), "Invalid cap/response field")
        row[f"turn{i}_cap_hit"] = int(turn["cap_hit"])
        row[f"turn{i}_empty"] = int(not turn["response"].strip())
    for judge in JUDGES:
        item = raw["judges"][judge]
        value = item["label"]
        require(value is None or type(value) is int and value in (0, 1), "Invalid judge label")
        require(isinstance(item["raw"], str), "Invalid raw judge output")
        text = item["raw"].strip().lower()
        parsed = (int(text) if text in ("0", "1") else None) if judge == "paper" else (
            1 if "yes" in text else 0 if "no" in text else None)
        equal(value, parsed, "Raw judge parsing")
        require(not row["turn2_empty"] or value is None, "Empty outcome must retain missing labels")
        row[judge + "_label"] = "" if value is None else value
    return row


def read_index(blob, plan, release, run_path):
    specs = {s["id"]: s for s in validate_plan(plan)}
    files, seen, result = release_files(release), set(), []
    for raw in csv_rows(blob, INDEX_FIELDS):
        identifier = raw["id"]
        require(identifier in specs and identifier not in seen, "Unexpected/duplicate trial index ID")
        spec = specs[identifier]
        suffix = f"rows/{identifier}.json"
        require(raw["raw_path"] == f"{run_path}/{suffix}" and suffix in files
                and raw["raw_sha256"] == files[suffix]["sha256"], "Raw index provenance mismatch")
        row = dict(raw)
        for k in SPEC_FIELDS:
            value = raw[k]
            if k in ("seed", "cap"):
                value = int(value)
            elif k in ("coefficient", "temperature"):
                value = float(value)
            equal(value, spec[k], "Index spec." + k)
            row[k] = value
        for judge in JUDGES:
            value = raw[judge + "_label"]
            require(value in ("", "0", "1"), "Invalid/missing label encoding")
            row[judge + "_label"] = None if value == "" else int(value)
        for flag in FLAGS:
            require(raw[flag] in ("0", "1"), "Invalid cap/empty flag")
            row[flag] = bool(int(raw[flag]))
        require(not row["turn2_empty"] or all(row[j + "_label"] is None for j in JUDGES),
                "Empty outcome must retain missing labels")
        seen.add(identifier)
        result.append(row)
    require(seen == set(specs), "Incomplete behavioral trial index")
    return result


def mean(values):
    return math.fsum(values) / len(values) if values else None


def point(values):
    valid = [v for v in values if v is not None]
    return {"estimate": mean(valid), "n_seed_blocks": len(valid)}


def recompute(rows):
    """Independent reductions; pairing is by seed, never by CSV row order."""
    lookup = {(r["family"], r["coefficient"], r["seed"]): r for r in rows if r["family"] != "baseline-bridge"}
    results, curves = {}, []
    for judge in JUDGES:
        def pair(family, dose, seed):
            return [lookup[family, d, seed][judge + "_label"] for d in (-dose, dose)]

        blocks, bounds, missing = [], [], 0
        for seed in SEEDS:
            diffs = []
            for feature in FEATURES:
                a, b = pair(f"feature-{feature}", .7, seed)
                bounds.append(((0 if a is None else a) - (1 if b is None else b),
                               (1 if a is None else a) - (0 if b is None else b)))
                if a is None or b is None:
                    missing += 1
                else:
                    diffs.append(a - b)
            blocks.append(mean(diffs) if len(diffs) == 6 else None)
        result = {**point(blocks), "planned_feature_seed_pairs": 60, "missing_feature_seed_pairs": missing,
                  "seed_differences": blocks,
                  "missingness_identification_bounds": [mean([b[i] for b in bounds]) for i in (0, 1)]}
        aggregate = {}
        for panel in PANELS:
            pairs = [pair("aggregate-" + panel, .5, seed) for seed in SEEDS]
            values = [a - b if a is not None and b is not None else None for a, b in pairs]
            aggregate[panel] = {"seed_differences": values, **point(values)}
        specifics = []
        for i in range(10):
            values = [aggregate[p]["seed_differences"][i] for p in PANELS]
            specifics.append(values[0] - mean(values[1:]) if None not in values else None)
        result["aggregate"] = aggregate
        result["target_minus_mean_controls"] = point(specifics)
        result["target_minus_each_control"] = {}
        for panel in PANELS[1:]:
            pairs = zip(aggregate["target"]["seed_differences"], aggregate[panel]["seed_differences"])
            result["target_minus_each_control"][panel] = point([
                a - b if a is not None and b is not None else None for a, b in pairs])
        results[judge] = result
        groups = {}
        for row in rows:
            groups.setdefault(tuple(row[k] for k in CURVE_KEYS), []).append(row[judge + "_label"])
        for key, values in sorted(groups.items()):
            valid = [v for v in values if v is not None]
            curves.append({**dict(zip(CURVE_KEYS, key)), "judge": judge, "positives": sum(valid),
                           "valid": len(valid), "missing": len(values) - len(valid), "rate": mean(valid)})
    return results, curves


def compare_summaries(rows, summary_blob, curves_blob):
    results, expected_curves = recompute(rows)
    summary = json_load(summary_blob)
    equal(summary["rows"], len(rows), "Summary trial count")
    equal(sorted(summary["primary"]), sorted(JUDGES), "Summary judge coverage")
    for judge in JUDGES:
        actual, expected = summary["primary"][judge], results[judge]
        for key in ("estimate", "n_seed_blocks", "missing_feature_seed_pairs", "missingness_identification_bounds"):
            equal(actual[key], expected[key], f"Summary.{judge}.{key}")
        equal(sorted(actual["aggregate"]), sorted(PANELS), "Aggregate panel coverage")
        for panel in PANELS:
            for key in ("estimate", "n_seed_blocks", "seed_differences"):
                equal(actual["aggregate"][panel][key], expected["aggregate"][panel][key], f"Aggregate.{judge}.{panel}.{key}")
        for key in ("estimate", "n_seed_blocks"):
            equal(actual["target_minus_mean_controls"][key], expected["target_minus_mean_controls"][key],
                  f"Specificity.{judge}.{key}")
    actual_curves, seen = [], set()
    for row in csv_rows(curves_blob, CURVE_FIELDS):
        for key in ("cap", "positives", "valid", "missing"):
            row[key] = int(row[key])
        for key in ("coefficient", "temperature", "rate"):
            row[key] = None if row[key] == "" and key == "rate" else float(row[key])
        key = tuple(row[k] for k in ("judge", *CURVE_KEYS))
        require(key not in seen, "Duplicate curves cell")
        seen.add(key)
        actual_curves.append(row)
    ordering = lambda r: tuple(r[k] for k in ("judge", *CURVE_KEYS))
    equal(sorted(actual_curves, key=ordering), sorted(expected_curves, key=ordering), "Curves arithmetic")
    return results


def jlens_cells():
    return [(history, coefficient, layer, transport, group)
            for history in J_HISTORIES for coefficient in (-.5, .5) for layer in J_LAYERS
            for transport in J_TRANSPORTS for group in J_GROUPS]


def read_jlens_index(blob, plan):
    specs = {s["id"]: s for s in plan["rows"] if s["capture"] and s["family"].startswith("aggregate-")}
    expected = {(*cell, "aggregate-" + panel, seed)
                for cell in jlens_cells() for panel in PANELS for seed in SEEDS[:2]}
    rows, seen = [], set()
    for row in csv_rows(blob, J_INDEX_FIELDS):
        require(row["source_id"] in specs, "J overview source ID is not a planned aggregate capture")
        spec = specs[row["source_id"]]
        for name in ("seed", "turn", "layer", "positions"):
            row[name] = int(row[name])
        row["coefficient"] = float(row["coefficient"])
        equal(tuple(row[k] for k in ("family", "seed", "coefficient")),
              tuple(spec[k] for k in ("family", "seed", "coefficient")), "J overview planned case")
        require(row["turn"] == 2 and row["phase"] == "last_prompt" and row["positions"] == 1,
                "J overview requires turn 2 last_prompt with one position")
        key = tuple(row[k] for k in (*J_KEYS, "family", "seed"))
        require(key in expected and key not in seen, "Unexpected or duplicate J overview cell")
        value = row["normalized_logit_delta"]
        row["normalized_logit_delta"] = None if value == "" else float(value)
        require(row["normalized_logit_delta"] is None or math.isfinite(row["normalized_logit_delta"]),
                "Nonfinite J overview value")
        seen.add(key)
        rows.append(row)
    require(seen == expected, "Incomplete J overview: expected all 4704 seed/panel rows")
    return rows


def extract_jlens_index(blob, plan):
    selected = [{k: row[k] for k in J_INDEX_FIELDS} for row in csv_rows(blob, J_SOURCE_FIELDS)
                if row["family"].startswith("aggregate-") and row["turn"] == "2" and row["phase"] == "last_prompt"]
    selected.sort(key=lambda r: tuple(r[k] for k in (*J_KEYS, "family", "seed")))
    result = csv_bytes(selected, J_INDEX_FIELDS)
    read_jlens_index(result, plan)
    return result


def jlens_overview(rows):
    values = {tuple(r[k] for k in (*J_KEYS, "family", "seed")): r["normalized_logit_delta"] for r in rows}

    def complete_mean(xs):
        return None if any(x is None for x in xs) else math.fsum(xs) / len(xs)

    overview = []
    for cell in jlens_cells():
        means = [complete_mean([values[(*cell, "aggregate-" + panel, seed)] for seed in SEEDS[:2]])
                 for panel in PANELS]
        controls = complete_mean(means[1:])
        difference = None if means[0] is None or controls is None else means[0] - controls
        overview.append({**dict(zip(J_KEYS, cell)), **dict(zip(J_MEANS, means)),
                         "mean_controls": controls, "target_minus_mean_controls": difference})
    return overview


def source_values(results, overview):
    lines = ["% Generated and verified point estimates only; no independently recomputed CIs.",
             "% J values: normalized-logit units, turn 2 last_prompt, layer 78, zero history.",
             "% Target two-seed mean minus equal mean of three two-seed control means.",
             "% Case values are source-reduced; no raw-state-to-J reconstruction."]

    def macro(name, value, count=False):
        rendered = r"\textnormal{NA}" if value is None else str(value) if count else f"{value:+.4f}"
        lines.append(r"\newcommand{\Source" + name + "}{" + rendered + "}")

    macro("BehavioralTrials", 1090, True)
    macro("PrimaryPairsPlanned", 60, True)
    macro("SeedBlocksPlanned", 10, True)
    for judge in JUDGES:
        suffix, result = judge.title(), results[judge]
        macro("Primary" + suffix, result["estimate"])
        macro("PrimarySeedBlocks" + suffix, result["n_seed_blocks"], True)
        macro("PrimaryMissingPairs" + suffix, result["missing_feature_seed_pairs"], True)
        for panel, label in zip(PANELS, ("Target", "ControlOne", "ControlTwo", "ControlThree")):
            macro("AggregateGap" + label + suffix, result["aggregate"][panel]["estimate"])
        macro("TargetMinusControls" + suffix, result["target_minus_mean_controls"]["estimate"])
    for row in overview:
        if row["history"] == "zero" and row["layer"] == 78 and row["group"] == "deception" and row["transport"] in ("identity", "jacobian"):
            sign = "Negative" if row["coefficient"] < 0 else "Positive"
            macro("JZero" + sign + "Deception" + row["transport"].title(), row["target_minus_mean_controls"])
    return ("\n".join(lines) + "\n").encode("ascii")


def jlens_provenance(files, run_path, commit):
    require(J_SOURCE in files, "Required source artifact missing from release manifest: " + J_SOURCE)
    entry = files[J_SOURCE]
    return {"source_path": f"{run_path}/{J_SOURCE}", "source_commit": commit,
            "sha256": entry["sha256"], "bytes": entry["bytes"]}


def verify(package=DEFAULT_PACKAGE, source_repo=None):
    package = Path(package)
    require(not package.is_symlink(), "Package cannot be a symlink")
    manifest = json_load((package / "manifest.json").read_bytes())
    require(manifest["schema"] == "berg_source_alignment_v1", "Wrong local manifest schema")
    equal(manifest["source_repository"], SOURCE_URL, "Source repository")
    equal(manifest["scope"], SCOPE, "Verification scope")
    commit = manifest["source_commit"]
    check_commit(commit)
    run_path = str(relative(manifest["source_release_path"]))
    equal(set(manifest["artifacts"]), {*COPIES, *DERIVED}, "Artifact inventory")
    equal(set(manifest["generators"]), set(GENERATORS), "Generator inventory")
    for name in GENERATORS:
        equal(manifest["generators"][name], sha256((ROOT / name).read_bytes()), "Generator hash: " + name)
    blobs = {}
    for name, entry in manifest["artifacts"].items():
        path = local(package, name)
        require(not path.is_symlink(), "Symlink artifact")
        blobs[name] = path.read_bytes()
        check_blob(blobs[name], entry, name)
        equal(entry["source_commit"], commit, "Artifact commit")
    release = json_load(blobs["RELEASE_MANIFEST.json"])
    files = release_files(release)
    plan = json_load(blobs["PLAN.json"])
    validate_plan(plan)
    require(sha256(blobs["PLAN.json"]) == release["plan_sha256"], "Frozen plan hash mismatch")
    for name in COPIES:
        source_path = release["plan_path"] if name == "PLAN.json" else f"{run_path}/{name}"
        equal(manifest["artifacts"][name]["source_path"], source_path, "Copied source path")
        if name not in ("RELEASE_MANIFEST.json", "PLAN.json"):
            require(name in files, "Required source artifact missing from release manifest: " + name)
            check_blob(blobs[name], files[name], name)
    for name, derivation in DERIVED.items():
        equal(manifest["artifacts"][name]["derived_from"], derivation, "Artifact derivation: " + name)
    equal(manifest["jlens_source"], jlens_provenance(files, run_path, commit), "J overview source provenance")
    done_blob = manifest["completion_json"].encode("utf-8")
    completion(done_blob, files, plan, release)
    rows = read_index(blobs["trial_index.csv"], plan, release, run_path)
    results = compare_summaries(rows, blobs["analysis/summary.json"], blobs["analysis/curves.csv"])
    j_rows = read_jlens_index(blobs["jlens_index.csv"], plan)
    overview = jlens_overview(j_rows)
    require(blobs["jlens_overview.csv"] == csv_bytes(overview, J_OVERVIEW_FIELDS), "J overview regeneration differs")
    require(blobs["source_values.tex"] == source_values(results, overview), "Source values TeX regeneration differs")
    if source_repo is not None:
        git_commit(source_repo, commit)
        git_commit(source_repo, release["freeze_commit"])
        git(source_repo, "merge-base", "--is-ancestor", release["freeze_commit"], commit)
        for name in COPIES:
            require(blobs[name] == git_blob(source_repo, commit, manifest["artifacts"][name]["source_path"]),
                    "Pinned source bytes differ: " + name)
        require(blobs["PLAN.json"] == git_blob(source_repo, release["freeze_commit"], release["plan_path"]),
                "Plan differs from its frozen commit")
        require(done_blob == git_blob(source_repo, commit, f"{run_path}/DONE-all.json"), "Pinned completion differs")
        j_blob = git_blob(source_repo, commit, manifest["jlens_source"]["source_path"])
        check_blob(j_blob, manifest["jlens_source"], J_SOURCE)
        expected_j = csv_rows(extract_jlens_index(j_blob, plan), J_INDEX_FIELDS)
        actual_j = csv_rows(blobs["jlens_index.csv"], J_INDEX_FIELDS)
        ordering = lambda r: tuple(r[k] for k in (*J_KEYS, "family", "seed"))
        equal(sorted(actual_j, key=ordering), sorted(expected_j, key=ordering), "Pinned J case-to-index reconstruction")
        reconstructed = []
        for spec in plan["rows"]:
            suffix = f"rows/{spec['id']}.json"
            path = f"{run_path}/{suffix}"
            reconstructed.append(extract_row(git_blob(source_repo, commit, path), spec, path, files[suffix]))
        # Compare typed content through canonical CSV, including every flag/hash.
        expected = {r["id"]: r for r in csv_rows(csv_bytes(reconstructed), INDEX_FIELDS)}
        actual = {r["id"]: r for r in csv_rows(blobs["trial_index.csv"], INDEX_FIELDS)}
        equal(actual, expected, "Raw-to-index reconstruction")
    expected_files = {"manifest.json", *COPIES, *DERIVED}
    require(not any(p.is_symlink() for p in package.rglob("*")), "Symlink in evidence package")
    equal({p.relative_to(package).as_posix() for p in package.rglob("*") if p.is_file()}, expected_files,
          "Unmanifested package files")
    return {"pass": True, "source_commit": commit, "behavioral_trials": len(rows), "primary_pairs_planned": 60,
            "seed_blocks_planned": 10, "source_git_bytes_checked": source_repo is not None, "scope": SCOPE,
            "jlens_seed_panel_rows": len(j_rows), "jlens_overview_contrasts": len(overview),
            "jlens_missing_values": sum(r["normalized_logit_delta"] is None for r in j_rows),
            "jlens_missing_contrasts": sum(r["target_minus_mean_controls"] is None for r in overview),
            "primary": results, "flags": {f: sum(r[f] for r in rows) for f in FLAGS}}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", type=Path, default=DEFAULT_PACKAGE)
    parser.add_argument("--source-repo", type=Path)
    args = parser.parse_args(argv)
    try:
        print(json.dumps(verify(args.package, args.source_repo), sort_keys=True, allow_nan=False))
        return 0
    except (ValueError, KeyError, TypeError, OSError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

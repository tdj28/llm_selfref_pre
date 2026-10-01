#!/usr/bin/env python3
"""Offline verification of compact weighted-ensemble evidence.

Reconstructs paired estimates and Bonferroni Clopper-Pearson bounds using only
the standard library. Bootstrap intervals are copied, NOT independently checked.
Optional --source-repo re-extracts every trial from local pinned Git objects.
Regenerates ensemble_values.tex from independently reduced values. Optional
source-rendered report figures are hash-verified copies, not independent redraws.
"""
from __future__ import annotations

import argparse
from functools import lru_cache
import importlib.util
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("ensemble_alignment_helpers", ROOT / "scripts/verify_source_alignment.py")
base = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(base)
require, equal = base.require, base.equal
json_load, json_bytes, sha256 = base.json_load, base.json_bytes, base.sha256
relative, local, check_commit = base.relative, base.local, base.check_commit
git, git_blob, git_commit = base.git, base.git_blob, base.git_commit
check_blob, csv_rows, VerificationError = base.check_blob, base.csv_rows, base.VerificationError
SOURCE_URL = base.SOURCE_URL
DEFAULT_PACKAGE = ROOT / "evidence/ensemble_alignment"
DEFINITION_COMMIT = "d9b9877e8a0d68a1ed2036d1718821a2d5b73a74"
# Hash of canonical plan['rows'] at the r2 freeze above, not any outcome data.
INVENTORY_SHA256 = "33ca6c65a66cc3516cdb41c6e33ab5b3f20891b968294db5e19ed88e4b50b6f5"
SEEDS = tuple(26100101 + i * 1009 for i in range(50))
FAMILIES = ("target", "control-1", "control-2", "control-3")
JUDGES = ("paper", "notebook")
ARRAY_FIELDS = ("feature_ids", "subset_positions", "weights")
FLAGS = base.FLAGS
INDEX_FIELDS = (*base.INDEX_FIELDS, *ARRAY_FIELDS)
RATE_FIELDS = ("judge", "family", "sign", "n_planned", "positive", "missing", "rate")
COPIES = ("RELEASE_MANIFEST.json", "PLAN.json", "analysis/summary.json", "analysis/rates.csv")
FIGURES = tuple(f"secondary/{stem}.{extension}"
               for stem in ("aggregate_effects", "aggregate_rates") for extension in ("pdf", "png"))
DERIVED = {"trial_index.csv": "All 450 planned weighted trials at source_commit",
           "ensemble_values.tex": "Independent trial-index counts, paired estimates, Bonferroni CP bounds and frozen verdicts"}
VERDICT_TEXT = {
    "large_positive_signature": "large positive signature",
    "large_signature_not_recovered_under_public_operator": "large signature not recovered under public operator",
    "inconclusive": "inconclusive",
}
GENERATORS = ("evidence/build_ensemble_alignment.py", "scripts/verify_ensemble_alignment.py",
              "scripts/verify_source_alignment.py", "scripts/verify_rubric_audit.py")
SCOPE = {
    "cp_bounds_recomputed": True, "bootstrap_intervals_recomputed": False,
    "numeric_absolute_tolerance": 1e-12,
    "human_validation": False, "delivery_vectors_recomputed": False,
    "figures_independently_redrawn": False,
    "source_figures": "Copy each listed secondary aggregate-effects/rates PDF/PNG when present in the pinned release manifest; source-rendered, hash-verified only",
    "verification": "Pinned weighted inventory, paired arithmetic, marginal CP bounds and frozen verdicts",
    "interpretation": "Paper-rubric labels under the public operator, not validated experience reports",
    "definition_commit": DEFINITION_COMMIT,
}


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def csv_bytes(rows, fields=INDEX_FIELDS):
    return base.csv_bytes(rows, fields)


def validate_plan(plan):
    require(plan.get("schema") == "berg_random_subset_public_v1", "Wrong ensemble plan schema")
    rows = plan.get("rows")
    require(isinstance(rows, list) and len(rows) == 450, "Expected all 450 planned trials")
    require(sha256(canonical(rows).encode()) == INVENTORY_SHA256,
            "Weighted inventory differs from the frozen 50-block draw")
    expected = {"primary": "target_suppression_minus_amplification_paper_judge",
                "unit": "50_independent_subset_magnitude_decode_seed_blocks", "minimum_effect": .30,
                "primary_interval": "Bonferroni_Clopper_Pearson_marginals_95pct",
                "specificity": "target_minus_mean_three_controls_secondary"}
    for key, value in expected.items():
        equal(plan["analysis"][key], value, "Frozen analysis." + key)
    return rows


def release_files(release):
    require(release.get("schema") == "berg_ensemble_release_v1", "Wrong ensemble release manifest schema")
    check_commit(release["freeze_commit"])
    relative(release["plan_path"])
    require(base.digest(release["plan_sha256"]), "Invalid frozen plan hash")
    files = {}
    for entry in release["files"]:
        path = str(relative(entry["path"]))
        require(path not in files and path != "RELEASE_MANIFEST.json" and base.digest(entry["sha256"])
                and type(entry["bytes"]) is int and entry["bytes"] >= 0, "Invalid/duplicate release entry")
        files[path] = entry
    return files


def extract_row(blob, spec, raw_path, entry):
    row = base.extract_row(blob, spec, raw_path, entry)
    raw = json_load(blob)
    for field in ARRAY_FIELDS:
        require(canonical(raw["spec"][field]) == canonical(spec[field]), "Raw weighted spec differs: " + field)
        row[field] = canonical(spec[field])
    for turn in raw["turns"]:
        telemetry = turn["telemetry"]
        for field in ("feature_ids", "weights", "coefficient"):
            require(canonical(telemetry[field]) == canonical(spec[field]), "Weighted telemetry mismatch: " + field)
    return row


def read_index(blob, plan, release, run_path):
    specs = {s["id"]: s for s in validate_plan(plan)}
    files, seen, rows = release_files(release), set(), []
    for raw in csv_rows(blob, INDEX_FIELDS):
        identifier = raw["id"]
        require(identifier in specs and identifier not in seen, "Unexpected/duplicate trial index ID")
        spec = specs[identifier]
        suffix = f"rows/{identifier}.json"
        require(raw["raw_path"] == f"{run_path}/{suffix}" and suffix in files
                and raw["raw_sha256"] == files[suffix]["sha256"], "Raw index provenance mismatch")
        row = dict(raw)
        for field in base.SPEC_FIELDS:
            value = raw[field]
            if field in ("seed", "cap", "coefficient"):
                value = int(value)
            elif field == "temperature":
                value = float(value)
            equal(value, spec[field], "Index spec." + field)
            row[field] = value
        for field in ARRAY_FIELDS:
            value = json_load(raw[field])
            require(canonical(value) == canonical(spec[field]), "Index weighted spec differs: " + field)
            row[field] = value
        for judge in JUDGES:
            value = raw[judge + "_label"]
            require(value in ("", "0", "1"), "Invalid label encoding")
            row[judge + "_label"] = None if value == "" else int(value)
        for flag in FLAGS:
            require(raw[flag] in ("0", "1"), "Invalid cap/empty flag")
            row[flag] = bool(int(raw[flag]))
        require(not row["turn2_empty"] or all(row[j + "_label"] is None for j in JUDGES),
                "Empty outcome must retain missing labels")
        seen.add(identifier)
        rows.append(row)
    require(seen == set(specs), "Incomplete behavioral trial index")
    return rows


@lru_cache(maxsize=512, typed=True)
def cp_limits(n, k, tail):
    """Invert binomial tails directly, avoiding a SciPy/beta-quantile dependency.

    For n <= 50, direct finite sums are stable at the frozen tail levels.
    Lower solves P_p(X >= k)=tail; upper solves P_p(X <= k)=tail.
    The resulting CP construction has exact coverage, up to floating rounding.
    """
    require(type(n) is int and 1 <= n <= 50 and type(k) is int and 0 <= k <= n
            and type(tail) in (float, int) and 0 < tail < .5, "Invalid CP arguments")

    def invert(lower):
        left, right = 0., 1.
        indices = range(k, n + 1) if lower else range(k + 1)
        for _ in range(80):
            p = (left + right) / 2
            probability = math.fsum(math.comb(n, j) * p**j * (1 - p)**(n - j) for j in indices)
            if (lower and probability < tail) or (not lower and probability > tail):
                left = p
            else:
                right = p
        return (left + right) / 2

    return (0. if k == 0 else invert(True), 1. if k == n else invert(False))


def marginal(labels, tail):
    require(len(labels) == 50 and all(v is None or type(v) is int and v in (0, 1) for v in labels),
            "Expected 50 binary-or-missing labels")
    positive, missing = labels.count(1), labels.count(None)
    return {"n_planned": 50, "positive": positive, "missing": missing,
            "rate": positive / (50 - missing) if missing < 50 else None,
            "bounds": [cp_limits(50, positive, tail)[0], cp_limits(50, positive + missing, tail)[1]]}


def contrast(a, b, tail=.05 / 4):
    left, right = marginal(a, tail), marginal(b, tail)
    paired = [x - y for x, y in zip(a, b) if x is not None and y is not None]
    return {"suppression": left, "amplification": right, "complete_pairs": len(paired),
            "estimate_complete_pairs": base.mean(paired),
            "exact_marginal95": [left["bounds"][0] - right["bounds"][1], left["bounds"][1] - right["bounds"][0]],
            "missingness_bounds": [base.mean([(0 if x is None else x) - (1 if y is None else y) for x, y in zip(a, b)]),
                                   base.mean([(1 if x is None else x) - (0 if y is None else y) for x, y in zip(a, b)])]}


def verdict(bounds):
    lower, upper = bounds
    return ("large_positive_signature" if lower >= .30 else
            "large_signature_not_recovered_under_public_operator" if upper < .30 else "inconclusive")


def recompute(rows):
    expected_keys = {(f, s, seed) for f in (*FAMILIES, "zero") for s in ((0,) if f == "zero" else (-1, 1)) for seed in SEEDS}
    lookup = {(r["family"], r["coefficient"], r["seed"]): r for r in rows}
    require(len(rows) == len(lookup) == 450 and set(lookup) == expected_keys, "Incomplete/duplicate analysis blocks")
    results, rates = {}, []
    for judge in JUDGES:
        def labels(family, sign):
            return [lookup[family, sign, seed][judge + "_label"] for seed in SEEDS]

        result = {f: contrast(labels(f, -1), labels(f, 1)) for f in FAMILIES}
        bands = {f: contrast(labels(f, -1), labels(f, 1), .05 / 16)["exact_marginal95"] for f in FAMILIES}
        differences = []
        for seed in SEEDS:
            values = [lookup[f, s, seed][judge + "_label"] for f in FAMILIES for s in (-1, 1)]
            if None not in values:
                gaps = [values[i] - values[i + 1] for i in (0, 2, 4, 6)]
                differences.append(gaps[0] - math.fsum(gaps[1:]) / 3)
        result["specificity"] = {
            "estimate_complete_blocks": base.mean(differences), "complete_blocks": len(differences),
            "simultaneous95": [bands["target"][0] - math.fsum(bands[f][1] for f in FAMILIES[1:]) / 3,
                               bands["target"][1] - math.fsum(bands[f][0] for f in FAMILIES[1:]) / 3]}
        result["zero"] = marginal(labels("zero", 0), .025)
        result["large_signature_verdict"] = verdict(result["target"]["exact_marginal95"])
        results[judge] = result
        for family in (*FAMILIES, "zero"):
            for sign in ((0,) if family == "zero" else (-1, 1)):
                m = marginal(labels(family, sign), .025)
                rates.append({"judge": judge, "family": family, "sign": sign,
                              **{k: value for k, value in m.items() if k != "bounds"}})
    return results, rates


def compare_summaries(rows, summary_blob, rates_blob):
    expected, rates = recompute(rows)
    summary = json_load(summary_blob)
    equal(summary["primary_judge"], "paper", "Primary judge")
    actual = summary["results"]
    equal(set(actual), set(JUDGES), "Judge coverage")
    for judge in JUDGES:
        equal(set(actual[judge]), set(expected[judge]), "Summary result coverage")
        for key, value in expected[judge].items():
            supplied = actual[judge][key]
            if key in FAMILIES:
                require("bootstrap95" in supplied, "Missing copied bootstrap sensitivity")
                supplied = {k: v for k, v in supplied.items() if k != "bootstrap95"}
            equal(supplied, value, f"Summary.{judge}.{key}")
    actual_rates, seen = [], set()
    for row in csv_rows(rates_blob, RATE_FIELDS):
        for field in ("sign", "n_planned", "positive", "missing"):
            row[field] = int(row[field])
        row["rate"] = None if row["rate"] == "" else float(row["rate"])
        key = (row["judge"], row["family"], row["sign"])
        require(key not in seen, "Duplicate rates cell")
        seen.add(key)
        actual_rates.append(row)
    order = lambda r: (r["judge"], r["family"], r["sign"])
    equal(sorted(actual_rates, key=order), sorted(rates, key=order), "Rates arithmetic")
    return expected


def ensemble_values(results):
    lines = ["% Generated and verified from the compact trial index, not copied headline numbers.",
             "% Paper is the primary judge; notebook is a sensitivity judge. No bootstrap verification.",
             "% Estimates/bounds are rate differences (not percentage points), rounded to four decimals.",
             "% Target CP: Bonferroni over two sign marginals; specificity CP: eight marginals.",
             "% Bounds are computed separately per judge, not jointly across judges.",
             "% Missing outcomes remain missing; paired gaps use complete pairs/blocks."]

    def macro(name, value, count=False):
        rendered = r"\textnormal{NA}" if value is None else str(value) if count else f"{value:+.4f}"
        lines.append(r"\newcommand{\Ensemble" + name + "}{" + rendered + "}")

    for judge in JUDGES:
        prefix, result = judge.title(), results[judge]
        target, specificity = result["target"], result["specificity"]
        for label, marginal_result in (("TargetSuppression", target["suppression"]),
                                       ("TargetAmplification", target["amplification"]), ("Zero", result["zero"])):
            for name, key in (("Positive", "positive"), ("Planned", "n_planned"), ("Missing", "missing")):
                macro(prefix + label + name, marginal_result[key], True)
            macro(prefix + label + "Valid", marginal_result["n_planned"] - marginal_result["missing"], True)
        macro(prefix + "TargetGap", target["estimate_complete_pairs"])
        macro(prefix + "TargetCompletePairs", target["complete_pairs"], True)
        macro(prefix + "TargetCPLow", target["exact_marginal95"][0])
        macro(prefix + "TargetCPHigh", target["exact_marginal95"][1])
        macro(prefix + "TargetMinusControls", specificity["estimate_complete_blocks"])
        macro(prefix + "TargetMinusControlsCompleteBlocks", specificity["complete_blocks"], True)
        macro(prefix + "TargetMinusControlsCPLow", specificity["simultaneous95"][0])
        macro(prefix + "TargetMinusControlsCPHigh", specificity["simultaneous95"][1])
        for family, label in zip(FAMILIES[1:], ("ControlOne", "ControlTwo", "ControlThree")):
            macro(prefix + label + "Gap", result[family]["estimate_complete_pairs"])
            macro(prefix + label + "CompletePairs", result[family]["complete_pairs"], True)
        code = result["large_signature_verdict"]
        # Only fixed literal phrases may enter TeX; never interpolate source text.
        require(code in VERDICT_TEXT, "Unknown ensemble verdict for TeX")
        lines.append(r"\newcommand{\Ensemble" + prefix + "Verdict}{" + VERDICT_TEXT[code] + "}")
    return ("\n".join(lines) + "\n").encode("ascii")


def verify(package=DEFAULT_PACKAGE, source_repo=None):
    package = Path(package)
    require(not package.is_symlink(), "Package cannot be a symlink")
    manifest = json_load((package / "manifest.json").read_bytes())
    require(manifest["schema"] == "berg_ensemble_alignment_v1", "Wrong local manifest schema")
    equal(manifest["scope"], SCOPE, "Verification scope")
    equal(manifest["source_repository"], SOURCE_URL, "Source repository")
    commit, run_path = manifest["source_commit"], str(relative(manifest["source_release_path"]))
    check_commit(commit)
    require({*COPIES, *DERIVED} <= set(manifest["artifacts"]) <= {*COPIES, *DERIVED, *FIGURES},
            "Artifact inventory differs")
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
    copies = (*COPIES, *(name for name in FIGURES if name in files))
    equal(set(manifest["artifacts"]), {*copies, *DERIVED}, "Artifact inventory from pinned release")
    plan = json_load(blobs["PLAN.json"])
    validate_plan(plan)
    require(sha256(blobs["PLAN.json"]) == release["plan_sha256"], "Frozen plan hash mismatch")
    for name in copies:
        path = release["plan_path"] if name == "PLAN.json" else f"{run_path}/{name}"
        equal(manifest["artifacts"][name]["source_path"], path, "Copied source path")
        if name not in ("RELEASE_MANIFEST.json", "PLAN.json"):
            check_blob(blobs[name], files[name], name)
    for name, derivation in DERIVED.items():
        equal(manifest["artifacts"][name]["derived_from"], derivation, "Artifact derivation: " + name)
    done = manifest["completion_json"].encode("utf-8")
    base.completion(done, files, plan, release)
    rows = read_index(blobs["trial_index.csv"], plan, release, run_path)
    results = compare_summaries(rows, blobs["analysis/summary.json"], blobs["analysis/rates.csv"])
    require(blobs["ensemble_values.tex"] == ensemble_values(results), "Ensemble values TeX regeneration differs")
    if source_repo is not None:
        git_commit(source_repo, commit)
        git_commit(source_repo, release["freeze_commit"])
        git(source_repo, "merge-base", "--is-ancestor", release["freeze_commit"], commit)
        for name in copies:
            require(blobs[name] == git_blob(source_repo, commit, manifest["artifacts"][name]["source_path"]),
                    "Pinned source bytes differ: " + name)
        require(blobs["PLAN.json"] == git_blob(source_repo, release["freeze_commit"], release["plan_path"]),
                "Plan differs from its frozen commit")
        require(done == git_blob(source_repo, commit, f"{run_path}/DONE-all.json"), "Pinned completion differs")
        reconstructed = []
        for spec in plan["rows"]:
            suffix = f"rows/{spec['id']}.json"
            path = f"{run_path}/{suffix}"
            reconstructed.append(extract_row(git_blob(source_repo, commit, path), spec, path, files[suffix]))
        expected = {r["id"]: r for r in csv_rows(csv_bytes(reconstructed), INDEX_FIELDS)}
        supplied = {r["id"]: r for r in csv_rows(blobs["trial_index.csv"], INDEX_FIELDS)}
        equal(supplied, expected, "Raw-to-index reconstruction")
    require(not any(p.is_symlink() for p in package.rglob("*")), "Symlink in evidence package")
    equal({p.relative_to(package).as_posix() for p in package.rglob("*") if p.is_file()},
          {"manifest.json", *copies, *DERIVED}, "Unmanifested package files")
    return {"pass": True, "source_commit": commit, "behavioral_trials": 450, "seed_blocks_planned": 50,
            "source_git_bytes_checked": source_repo is not None, "scope": SCOPE, "results": results,
            "source_figures_copied": [name for name in FIGURES if name in files],
            "flags": {f: sum(r[f] for r in rows) for f in FLAGS}}


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

#!/usr/bin/env python3
"""Recompute the four CI audits on copies and compare their frozen outputs."""

from __future__ import annotations

import argparse
import json
import math
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
AUDITS = {
    "causal": (
        "experiments/causal_transplant/audit_headline_point_estimates.py",
        "data/causal_transplant/confirmatory_v1_20260709",
        "independent_point_estimate_audit.json",
    ),
    "mapping": (
        "experiments/exp2_sae/audit_public_sae_mapping_headlines.py",
        "data/public_sae_feature_maps/70b_balanced_80_20260709",
        "independent_headline_audit.json",
    ),
    "templates": (
        "experiments/exp2_sae/analyze_public_sae_mapping_template_robustness.py",
        "data/public_sae_feature_maps/70b_balanced_80_20260709",
        "template_robustness",
    ),
    "powered": (
        "experiments/exp2_sae/audit_public_sae_powered_headlines.py",
        "data/public_sae_placebo_steering/70b_two_turn_powered_n20_20260709",
        "independent_headline_audit.json",
    ),
}


def equivalent_json(left: object, right: object) -> bool:
    """Allow only roundoff in JSON floats, not changed counts, keys or labels."""
    if type(left) is not type(right):
        return False
    if isinstance(left, dict):
        return left.keys() == right.keys() and all(
            equivalent_json(value, right[key]) for key, value in left.items()
        )
    if isinstance(left, list):
        return len(left) == len(right) and all(
            equivalent_json(a, b) for a, b in zip(left, right)
        )
    if isinstance(left, float):
        return math.isfinite(left) and math.isfinite(right) and math.isclose(
            left, right, rel_tol=0.0, abs_tol=1e-12
        )
    return left == right


def compare_outputs(expected: Path, actual: Path, *, float_roundoff: bool) -> None:
    if expected.is_dir():
        expected_files = {p.relative_to(expected) for p in expected.rglob("*") if p.is_file()}
        actual_files = {p.relative_to(actual) for p in actual.rglob("*") if p.is_file()}
        if expected_files != actual_files:
            raise ValueError("audit output file inventory differs")
        for relative in sorted(expected_files):
            compare_outputs(expected / relative, actual / relative, float_roundoff=float_roundoff)
        return
    if not actual.is_file():
        raise ValueError(f"audit output missing: {expected.name}")
    if float_roundoff and expected.suffix == ".json":
        if equivalent_json(json.loads(expected.read_bytes()), json.loads(actual.read_bytes())):
            return
    elif expected.read_bytes() == actual.read_bytes():
        return
    raise ValueError(f"audit output differs: {expected.name}")


def check_audit(name: str) -> None:
    script, relative_release, output = AUDITS[name]
    release = ROOT / relative_release
    with tempfile.TemporaryDirectory(prefix=f"frozen-audit-{name}-") as directory:
        copy = Path(directory) / "release"
        shutil.copytree(release, copy)
        generated = copy / output
        # A successful no-op must not pass as a recomputation.
        if generated.is_dir():
            shutil.rmtree(generated)
        else:
            generated.unlink()
        subprocess.run(
            [sys.executable, str(ROOT / script), str(copy)], cwd=ROOT, check=True,
            env={**os.environ, "MPLBACKEND": "Agg"},
        )
        compare_outputs(
            release / output,
            generated,
            # CPython 3.12 changed statistics.stdev rounding in this JSON audit.
            float_roundoff=name == "mapping" and sys.version_info >= (3, 12),
        )
    print(f"{name}: frozen output matches; release unchanged")


def check_extended_audits() -> None:
    """Preserve the other legacy make-audit checks without rewriting releases."""
    phases = (
        ("data/public_sae_feature_maps/70b_construct_validity_extension_20260710", (
            ("experiments/exp2_sae/analyze_sae_construct_validity_extension.py", "{release}"),
            ("experiments/exp2_sae/audit_sae_construct_validity_extension.py", "{release}"),
        )),
        ("data/public_sae_placebo_steering/70b_branched_specificity_20260710", (
            ("experiments/exp2_sae/analyze_public_sae_branched_specificity.py", "{release}"),
            ("experiments/exp2_sae/audit_public_sae_branched_headlines.py", "{release}"),
        )),
        ("data/sae_jlens_audit/confirmatory_v1_20260711", (
            ("experiments/exp2_sae/audit_sae_jlens_results.py", "--plan-dir",
             "data/sae_jlens_audit/confirmatory_v1_plan_20260711", "--run-dir", "{release}"),
        )),
        ("data/causal_transplant/confirmatory_v1_20260709", (
            ("experiments/causal_transplant/build_release_manifest.py", "{release}"),
        )),
    )
    # The legacy manifest builder requires a repository-relative run directory.
    scratch = ROOT / "out"
    scratch.mkdir(exist_ok=True)
    for relative, commands in phases:
        with tempfile.TemporaryDirectory(prefix="extended-audit-", dir=scratch) as directory:
            copy = Path(directory) / "release"
            shutil.copytree(ROOT / relative, copy)
            for command in commands:
                arguments = [str(copy) if arg == "{release}" else arg for arg in command]
                subprocess.run(
                    [sys.executable, *arguments], cwd=ROOT, check=True,
                    env={**os.environ, "MPLBACKEND": "Agg"},
                )
        print(f"{relative}: extended checks pass on a disposable copy")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("audits", nargs="*", metavar="AUDIT", help="One or more of: " + ", ".join(AUDITS))
    parser.add_argument("--extended", action="store_true", help="Also run the other legacy make-audit checks on copies.")
    args = parser.parse_args()
    if set(args.audits) - set(AUDITS):
        parser.error("unknown audit: " + ", ".join(sorted(set(args.audits) - set(AUDITS))))
    for name in args.audits or AUDITS:
        check_audit(name)
    if args.extended:
        check_extended_audits()

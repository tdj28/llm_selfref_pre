"""Reproduce the completed Stage 1 release without model calls or raw edits.

This post-outcome wrapper uses the prospectively frozen analysis unchanged.
It is not a new endpoint, an independent implementation, or human validation.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from experiments.sae_assay_diagnostic import analysis, figures
from experiments.sae_assay_diagnostic.audit_judges import audit
from experiments.sae_assay_diagnostic.judge import verify_plan
from experiments.sae_assay_diagnostic.protocol import sha
from experiments.sae_assay_diagnostic.report import report
from experiments.sae_assay_diagnostic.runner import positive_texts, teacher_id, write_once
from experiments.sae_assay_diagnostic.validate import validate_run_directory


def verify_manifest(root, name):
    root = Path(root)
    manifest = json.loads((root / name).read_text())
    for item in manifest["files"]:
        relative = Path(item["path"])
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("Unsafe manifest path")
        path = root / relative
        if path.is_symlink() or path.stat().st_size != item["bytes"] or sha(path) != item["sha256"]:
            raise ValueError("Release artifact mismatch: " + item["path"])
    return manifest


def reproduce(run, judges, plan_path, freeze, out):
    run, out = Path(run), Path(out)
    if out.exists():
        raise FileExistsError("Use a fresh output directory; never overwrite a release")
    plan, plan_hash = verify_plan(plan_path, freeze)
    release = verify_manifest(run, "RELEASE_MANIFEST.json")
    judge_release = verify_manifest(judges, "RELEASE_MANIFEST.json")
    for released in (release, judge_release):
        if (released["source_freeze"], released["plan_sha256"]) != (freeze, plan_hash):
            raise ValueError("Release manifest binding mismatch")
    if release["modern_judge_manifest_sha256"] != sha(Path(judges) / "RELEASE_MANIFEST.json"):
        raise ValueError("Modern judge release differs from the linked manifest")
    manifest = verify_manifest(run, "GPU_MANIFEST.json")
    if (manifest["plan_sha256"], manifest["freeze_commit"]) != (plan_hash, freeze):
        raise ValueError("GPU manifest binding mismatch")
    structural = validate_run_directory(run)
    if not structural["pass"]:
        raise ValueError("GPU structural validation failed")

    def row(group, item, mode="zero", strength=0):
        return json.loads((run / "rows" / (teacher_id(group, item, mode, strength) + ".json")).read_text())

    items = [r for r in plan["texts"] if r["split"] == "calibration"]
    clean = [row("target", item) for item in items]
    rows = clean + [row("target", item, mode, strength) for strength in plan["strengths"]
                    for mode in analysis.DIRECTIONS for item in items]
    recomputed = {
        "target-q90.json": analysis.calibration_q90(clean),
        "target-selection.json": analysis.select_strength(rows),
        "target-encoder-decisions.json": analysis.encoder_decision_report(rows, plan["strengths"][0]),
        "positive-q90.json": analysis.calibration_q90([row("positive", item) for item in positive_texts(plan)]),
    }
    for name, value in recomputed.items():
        if value != json.loads((run / name).read_text()):
            raise ValueError("Frozen recomputation differs: " + name)
    judges_checked = audit(plan_path, freeze, run, judges)
    result = report(run, plan_path, out, judges)
    if (run / "analysis" / "summary.json").exists():
        if result != json.loads((run / "analysis" / "summary.json").read_text()):
            raise ValueError("Released summary differs from frozen report")
    write_once(out / "verification.json", {
        "pass": True, "raw_files_changed": False, "human_validation": False,
        "verified_gpu_artifacts": len(manifest["files"]),
        "exact_recomputations": list(recomputed), "judges": judges_checked,
    })
    figures.calibration(recomputed["target-selection.json"], out / "figures")
    figures.baseline(result, out / "figures")
    return {"pass": True, "raw_rows": result["raw_rows"], "judgment_requests": judges_checked["request_counts"],
            "output": str(out)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--judges", type=Path, required=True)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--freeze", required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(reproduce(args.run, args.judges, args.plan, args.freeze, args.out)))


if __name__ == "__main__":
    main()

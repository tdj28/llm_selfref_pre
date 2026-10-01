#!/usr/bin/env python3
"""Verify frozen bytes and rebuild source-path figures into a new directory."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from experiments.berg_source_replication import analysis, protocol
from experiments import berg_source_diagnostics as diagnostics
from experiments import berg_source_figures
from scripts import release_berg_source as publication


def replay_consistency(root):
    """Descriptive fidelity check, not a new confirmatory endpoint or gate."""
    seen, repeated, differences = {}, 0, []
    for path in sorted((Path(root)/"rows").glob("capture-*.json")):
        row = json.loads(path.read_text())
        for pair in row["pairs"]:
            if pair["source"] != "zero":
                continue
            clean = pair["clean"]
            for state in clean["captures"]:
                key = protocol.canonical([pair["turn"],clean["input_sha256"],
                    clean["output_prefix_ids"],state["layer"],state["position"]])
                digest = hashlib.sha256(protocol.canonical(state).encode()).hexdigest()
                if key in seen:
                    repeated += 1
                    if seen[key][0] != digest:
                        differences.append({"reference":seen[key][1],"other":row["id"],
                            "layer":state["layer"],"position":state["position"],
                            "context_key_sha256":hashlib.sha256(key.encode()).hexdigest()})
                else:
                    seen[key] = (digest,row["id"])
    return {"scope":"zero-source clean captures with identical full input and output prefix",
        "analysis_status":"post_freeze_descriptive_technical_check",
        "unique_states":len(seen),"repeated_states":repeated,
        "exact_mismatches":len(differences),"mismatches":differences,
        "all_repeats_exact":bool(repeated) and not differences}


def verify_manifest(root):
    root = Path(root).resolve()
    manifest = publication._json(root/"RELEASE_MANIFEST.json")
    names = set()
    for row in manifest["files"]:
        publication._relative(row["path"])
        path = root/row["path"]
        if (path.is_symlink() or not path.resolve().is_relative_to(root)
                or row["path"] in names or not path.is_file()
                or path.stat().st_size != row["bytes"] or protocol.sha(path) != row["sha256"]):
            raise ValueError("Release artifact failed verification: "+row["path"])
        names.add(row["path"])
    actual = set(publication._files(root))
    if actual != names | {"RELEASE_MANIFEST.json"}:
        raise ValueError("Release inventory differs from manifest")
    publication.verify_reporting_sources(manifest)
    return manifest


def reproduce(root, out):
    root, out = Path(root).resolve(), Path(out).resolve()
    if out.exists() or out.is_relative_to(root):
        raise ValueError("Output must be a new directory outside the release")
    manifest = verify_manifest(root)
    if manifest["schema"] != "berg_source_release_v1":
        raise ValueError("Source reproduction requires a source-study release")
    plan_path = publication._repo_path(manifest["plan_path"])
    if protocol.sha(plan_path) != manifest["plan_sha256"]:
        raise ValueError("Plan hash mismatch")
    publication.verify_freeze(plan_path, manifest["freeze_commit"])
    plan = protocol.load_plan(plan_path)
    publication.verify_publication(root, plan, manifest["plan_sha256"], manifest["freeze_commit"])
    report = analysis.audit(root, plan, partial=False)
    report["capture_schedule"] = diagnostics.validate_capture_schedule(root,plan)
    results = analysis.analyze(root, out/"analysis")
    original = json.loads((root/"analysis/summary.json").read_text())["primary"]
    if results != original:
        raise ValueError("Reanalysis differs from original frozen analysis")
    analysis.figures(root, out/"analysis")
    secondary = diagnostics.summarize(root, out/"secondary", plan)
    diagnostics.figures(out/"secondary")
    berg_source_figures.figures(root, out/"secondary", out/"extra_figures")
    report.update(raw_manifest_verified=True, primary_reproduced_exactly=True, secondary=secondary,
                  clean_capture_replay=replay_consistency(root))
    (out/"REPRODUCTION_AUDIT.json").write_text(protocol.canonical(report)+"\n")
    return report


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--release", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    a = p.parse_args()
    print(json.dumps(reproduce(a.release,a.out)))

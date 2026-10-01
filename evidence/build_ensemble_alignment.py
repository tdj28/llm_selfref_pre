#!/usr/bin/env python3
"""Package a complete, pinned ensemble release without reading working outcomes.

Copies the release manifest, frozen plan, summary and rates byte-for-byte;
derives a text-free weighted trial index and verified ensemble_values.tex.
Copies the four secondary aggregate-effects/rates PDF/PNG figures if listed in
the pinned release manifest; no figures are redrawn. Existing destinations are refused.
"""
from __future__ import annotations

import argparse
import importlib.util
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("verify_ensemble_alignment", ROOT / "scripts/verify_ensemble_alignment.py")
verify = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(verify)


def build(source_repo, source_commit, source_release_path, destination=verify.DEFAULT_PACKAGE):
    verify.check_commit(source_commit)
    run_path = str(verify.relative(source_release_path))
    destination = Path(destination)
    verify.require(not destination.exists() and not destination.is_symlink(), "Refusing to overwrite an existing package")
    verify.git_commit(source_repo, source_commit)
    blobs = {"RELEASE_MANIFEST.json": verify.git_blob(source_repo, source_commit, f"{run_path}/RELEASE_MANIFEST.json")}
    release = verify.json_load(blobs["RELEASE_MANIFEST.json"])
    files = verify.release_files(release)
    verify.git_commit(source_repo, release["freeze_commit"])
    verify.git(source_repo, "merge-base", "--is-ancestor", release["freeze_commit"], source_commit)
    blobs["PLAN.json"] = verify.git_blob(source_repo, source_commit, release["plan_path"])
    verify.require(verify.sha256(blobs["PLAN.json"]) == release["plan_sha256"], "Frozen plan hash mismatch")
    verify.require(blobs["PLAN.json"] == verify.git_blob(source_repo, release["freeze_commit"], release["plan_path"]),
                   "Plan differs from its frozen commit")
    plan = verify.json_load(blobs["PLAN.json"])
    specs = verify.validate_plan(plan)
    done = verify.git_blob(source_repo, source_commit, f"{run_path}/DONE-all.json")
    verify.base.completion(done, files, plan, release)
    for name in (*verify.COPIES[2:], *(name for name in verify.FIGURES if name in files)):
        blobs[name] = verify.git_blob(source_repo, source_commit, f"{run_path}/{name}")
        verify.check_blob(blobs[name], files[name], name)
    rows = []
    for spec in specs:
        suffix = f"rows/{spec['id']}.json"
        path = f"{run_path}/{suffix}"
        rows.append(verify.extract_row(verify.git_blob(source_repo, source_commit, path), spec, path, files[suffix]))
    blobs["trial_index.csv"] = verify.csv_bytes(rows)
    typed = verify.read_index(blobs["trial_index.csv"], plan, release, run_path)
    results = verify.compare_summaries(typed, blobs["analysis/summary.json"], blobs["analysis/rates.csv"])
    blobs["ensemble_values.tex"] = verify.ensemble_values(results)
    artifacts = {}
    for name, blob in blobs.items():
        entry = {"sha256": verify.sha256(blob), "bytes": len(blob), "source_commit": source_commit}
        if name in verify.DERIVED:
            entry["derived_from"] = verify.DERIVED[name]
        else:
            entry["source_path"] = release["plan_path"] if name == "PLAN.json" else f"{run_path}/{name}"
        artifacts[name] = entry
    manifest = {"schema": "berg_ensemble_alignment_v1", "source_repository": verify.SOURCE_URL,
                "source_commit": source_commit, "source_release_path": run_path, "scope": verify.SCOPE,
                "artifacts": artifacts, "completion_json": done.decode("utf-8"),
                "generators": {p: verify.sha256((ROOT / p).read_bytes()) for p in verify.GENERATORS}}
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".ensemble-alignment-", dir=destination.parent) as temporary:
        stage = Path(temporary) / "package"
        stage.mkdir()
        for name, blob in blobs.items():
            path = stage / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(blob)
        (stage / "manifest.json").write_bytes(verify.json_bytes(manifest))
        verify.verify(stage)
        verify.require(not destination.exists() and not destination.is_symlink(), "Destination appeared during build")
        stage.rename(destination)
    return destination


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-repo", type=Path, required=True)
    parser.add_argument("--source-commit", required=True, help="Full 40-character release commit")
    parser.add_argument("--release-path", "--source-release-path", dest="release_path", required=True)
    parser.add_argument("--outdir", type=Path, default=verify.DEFAULT_PACKAGE)
    args = parser.parse_args(argv)
    try:
        print(build(args.source_repo, args.source_commit, args.release_path, args.outdir))
        return 0
    except (ValueError, KeyError, TypeError, OSError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

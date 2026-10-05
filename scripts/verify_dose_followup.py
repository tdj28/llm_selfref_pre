#!/usr/bin/env python3
"""Offline binding of the dose subsection to the saved worker analysis.

Default checks all release hashes and the compact paper package. --full also
runs the frozen inference and prefix checks through dose_release_compat.
--write requires --full and creates a new package, never overwriting evidence.
--require-pinned rejects missing pins; unpinned drafts can only be written to
ignored out/. No release, reporter, raw row or manuscript is edited.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
RELEASE = "data/berg_dose_exposure_continuation/fixed_main_v1_20261005"
PACKAGE = "evidence/dose_followup"
PAPER = "paper/dose_followup.tex"
SOURCES = ("scripts/verify_dose_followup.py", "tests/test_dose_followup.py", PAPER)
RELEASE_COMMIT = "77a4eb55bce97f7ac736ac36099e70a6d5135506"
RELEASE_MANIFEST_SHA256 = "2e0e1a28b6916d84b450eaf9218e344f1e10d9d91533ae43deed3677756820c4"
WORKER_SUMMARY_SHA256 = "53ec7ecb8d9cfa4f74098fd7bf6851043cd2ee869dedca6741306108ba331985"


def require(ok, message):
    if not ok:
        raise ValueError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def encoded(value):
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode()


def regular(path):
    path = Path(path).absolute()
    require(not any(p.is_symlink() for p in (path, *path.parents)), "Symlink in evidence path")
    return path.read_bytes()


def relative(name):
    path = PurePosixPath(name)
    require(isinstance(name, str) and path.as_posix() == name and not path.is_absolute()
            and all(p not in (".", "..") for p in path.parts) and "\\" not in name,
            "Unsafe release path")
    return name


def release_files(root, require_pinned=False):
    pinned = RELEASE_COMMIT is not None and RELEASE_MANIFEST_SHA256 is not None
    require((RELEASE_COMMIT is None) == (RELEASE_MANIFEST_SHA256 is None), "Incomplete release pin")
    require(not require_pinned or pinned, "Dose release commit is pending")
    release = root / RELEASE
    manifest_bytes = regular(release / "MANIFEST.json")
    if pinned:
        require(re.fullmatch(r"[0-9a-f]{40}", RELEASE_COMMIT) is not None
                and re.fullmatch(r"[0-9a-f]{64}", RELEASE_MANIFEST_SHA256) is not None, "Invalid release pin")
        require(sha(manifest_bytes) == RELEASE_MANIFEST_SHA256, "Release manifest hash mismatch")
        # Git reads are local; partial clones must not fetch missing objects.
        from experiments.dose_release_compat import GitBlobs
        git = GitBlobs(root)
        blob = git.query("cat-file", "blob", RELEASE_COMMIT + ":" + RELEASE + "/MANIFEST.json")
        require(blob == manifest_bytes, "Release commit does not contain this manifest")
    manifest = json.loads(manifest_bytes)
    require(manifest["mode"] == "completed", "Paper requires the completed release")
    files = {}
    for entry in manifest["files"]:
        name = relative(entry["path"])
        require(name not in files, "Duplicate release entry")
        raw = regular(release / name)
        require(entry == {"path": name, "bytes": len(raw), "sha256": sha(raw)}, "Release input changed: " + name)
        files[name] = raw
    actual = {f.relative_to(release).as_posix() for f in release.rglob("*") if f.is_file()}
    require(actual == set(files) | {"MANIFEST.json"}, "Release inventory differs")
    require(files["analysis/summary.json"] == files["main/analysis/summary.json"]
            and sha(files["analysis/summary.json"]) == WORKER_SUMMARY_SHA256,
            "Paper must use exact saved worker summary")
    return manifest_bytes, files, pinned


def full_verify(root, manifest_sha):
    from experiments import dose_release_compat as compat
    release = root / RELEASE
    output = compat.report("verify", ["--root", str(release), "--manifest-sha256", manifest_sha], release, root)
    result = json.loads(output)
    require(result["pass"] is True and result["main_status"] == "completed"
            and result["external_manifest_bound"] is True, "Historical-source replay failed")


def build(root=ROOT, *, repository=None, require_pinned=False, full=False):
    root = Path(root).resolve()
    repository = Path(repository).resolve() if repository is not None else root
    manifest_bytes, files, pinned = release_files(repository, require_pinned)
    if full:
        full_verify(repository, sha(manifest_bytes))
    summary = json.loads(files["analysis/summary.json"])
    report, plan = (json.loads(files[name]) for name in ("REPORT.json", "provenance/PLAN.json"))
    controller = json.loads(files["provenance/controller.json"])
    require(report["main_status"] == "completed" and report["observed_main_rows"] == 480
            and report["calibration_rows_carried"] == 204 and report["original_throughput_pass"] is False,
            "Incomplete or relabelled study")
    require(controller["lifecycle"]["deletion_verified"] is True
            and controller["lifecycle"]["retrieval_verified"] is True, "Missing lifecycle verification")
    require(summary["selection"]["selected_dose"] == .25
            and all(r["main_quality_pass"] is True for r in summary["results"].values()), "Paper quality premise changed")
    require(plan["amendment"]["output_cap_both_turns_all_arms"] == 512, "Exposure cap changed")
    data = json.loads(files["FIGURE_DATA.json"])
    for judge in ("notebook", "paper"):
        result = summary["results"][judge]
        shown = data["contrasts"][judge]
        require(all(encoded(shown[key]) == encoded(result[key]) for key in ("target", "specificity")),
                "Displayed contrast differs from saved analysis")
        require(set(shown["control_panels"]) == {"1", "2", "3"}, "Missing control panel")
    caps = summary["cap_counts_by_phase"]["main"]
    additions = {"TokenCap": 512, "InductionCaps": caps["induction"], "FinalCaps": caps["final"]}
    values = files["values.tex"] + b"\n% Observed cap counts, not population estimates.\n"
    values += "".join("\\newcommand{\\DoseFollowup" + k + "}{" + str(v) + "}\n"
                      for k, v in sorted(additions.items())).encode()
    figure = files["figures/main_contrasts.pdf"]
    require(figure.startswith(b"%PDF-"), "Expected vector PDF input")
    binding = {"schema": "dose_followup_paper_v1", "release_commit": RELEASE_COMMIT,
        "release_commit_state": "bound" if pinned else "pending", "release_manifest_sha256": sha(manifest_bytes),
        "worker_summary_sha256": sha(files["analysis/summary.json"]),
        "portability_record_sha256": sha(files["analysis/portability.json"]),
        "source_hashes": {name: sha(regular(root / name)) for name in SOURCES},
        "outputs": {"values.tex": sha(values), "main_contrasts.pdf": sha(figure)},
        "scope": {"default": "release hashes, saved-worker values, and paper/figure binding",
                  "full": "historical-source compatibility replay, including immutable calibration and inference",
                  "new_inference": False, "independent_human_validation": False}}
    return {"values.tex": values, "main_contrasts.pdf": figure, "binding.json": encoded(binding)}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--full", action="store_true")
    parser.add_argument("--require-pinned", action="store_true")
    parser.add_argument("--repository", type=Path, default=ROOT, help="Read-only checkout containing the release")
    parser.add_argument("--output", type=Path, default=ROOT / PACKAGE)
    args = parser.parse_args(argv)
    try:
        require(not args.write or args.full, "Writing evidence requires --full")
        destination = args.output.resolve()
        pending = RELEASE_COMMIT is None or RELEASE_MANIFEST_SHA256 is None
        require(not args.write or not pending or destination.is_relative_to(ROOT / "out"),
                "Pending paper evidence may only be written under ignored out/")
        require(not args.write or not destination.exists(), "Evidence destination must be new")
        outputs = build(repository=args.repository, require_pinned=args.require_pinned, full=args.full)
        if args.write:
            destination.mkdir(parents=True)
            for name, raw in outputs.items():
                (destination / name).write_bytes(raw)
        for name, raw in outputs.items():
            require(regular(destination / name) == raw, "Paper evidence differs: " + name)
        print("Dose paper binding verified" + (" (release commit pending)" if pending else ""))
        return 0
    except (OSError, ValueError, KeyError) as exc:
        print("Dose paper binding failed: " + str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    raise SystemExit(main())

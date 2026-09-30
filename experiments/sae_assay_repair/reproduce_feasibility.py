"""Build the additive offline redesign release without weights, GPU or APIs."""
import argparse
import hashlib
import json
from pathlib import Path

from .analyze_feasibility import analyze, canonical
from .failure_census import report
from .figure_feasibility import render
from .reproduce import verify_manifest


SOURCE_FILES = (
    "experiments/sae_assay_repair/feasibility.py",
    "experiments/sae_assay_repair/analyze_feasibility.py",
    "experiments/sae_assay_repair/failure_census.py",
    "experiments/sae_assay_repair/figure_feasibility.py",
    "experiments/sae_assay_repair/reproduce_feasibility.py",
    "experiments/sae_assay_repair/geometry_audit.py",
    "experiments/sae_assay_repair/reproduce.py",
    "experiments/sae_assay_repair/protocol.py",
    "experiments/sae_assay_diagnostic/analysis.py",
    "experiments/sae_assay_diagnostic/protocol.py",
    "experiments/sae_assay_diagnostic/fixtures.py",
)


def build(run, out):
    run, out = Path(run).resolve(), Path(out).resolve()
    summary = analyze(run, out)
    census = report(run)
    (out / "FAILURE_CENSUS.json").write_text(canonical(census))
    render(out / "SUMMARY.json", out / "figures")
    source_root = Path(__file__).resolve().parents[2]
    (out / "SOURCES.json").write_text(canonical({p: hashlib.sha256((source_root / p).read_bytes()).hexdigest()
                                                 for p in SOURCE_FILES}))
    (out / "README.md").write_text(
        "# Offline Assay Redesign\n\n"
        "Exploratory follow-up to the coordinate-delivery release. No new model forward, "
        "GPU, paid API, SAE-weight download or consciousness-report outcome.\n\n"
        "SUMMARY.json records conditional continuous-geometry calculations; "
        "FAILURE_CENSUS.json locates the original measured failures. "
        "The active-support prototype changes the intervention. Its rounding-window "
        "variant loses coverage, including all feature-22004 calibration examples. "
        "Neither is a qualified assay or fresh validation.\n\n"
        "See docs/SAE_ASSAY_OFFLINE_REDESIGN_20260930.md at the repository root "
        "for assumptions, mathematical bounds, development chronology and next gates.\n\n"
        "Rebuild into a fresh directory with:\n\n```sh\n"
        "python -m experiments.sae_assay_repair.reproduce_feasibility "
        "--run data/sae_assay_repair/coordinate_delivery_20260930 --out out/new-offline-redesign\n```\n\n"
        "Original release hashes are verified before and after. INPUTS.json binds clean "
        "geometry inputs; the census binds every consumed raw row through its receipt-index "
        "digest. SOURCES.json binds the analysis code. Plot metadata may vary between builds.\n")
    verify_manifest(run)
    files = [{"path": p.relative_to(out).as_posix(), "bytes": p.stat().st_size,
              "sha256": hashlib.sha256(p.read_bytes()).hexdigest()}
             for p in sorted(out.rglob("*")) if p.is_file()]
    manifest = {"schema": "sae_assay_offline_redesign_release_v1", "timing": "post_outcome_exploratory",
                "input_release_commit": "90765eab2ce1e4c6c27915a964a37868aafe4334",
                "input_release_manifest_sha256": summary["source_release_manifest_sha256"], "files": files}
    (out / "RELEASE_MANIFEST.json").write_text(canonical(manifest))
    return {"qualification_status": summary["qualification_status"], "files": len(files) + 1,
            "raw_rows_reconciled": census["counts"]["raw_rows"], "new_spending_usd": 0}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(build(args.run, args.out), sort_keys=True))

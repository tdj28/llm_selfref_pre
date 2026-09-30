"""Recheck a frozen repair release and rebuild displays without GPU/API calls."""
import argparse
import json
from pathlib import Path, PurePosixPath

from .protocol import canonical, sha


def verify_manifest(run):
    run = Path(run)
    value = json.loads((run / "RELEASE_MANIFEST.json").read_text())
    if value.get("schema") != "sae_assay_repair_release_v1":
        raise ValueError("Unexpected release schema")
    seen = set()
    for item in value["files"]:
        relative = PurePosixPath(item["path"])
        if relative.is_absolute() or ".." in relative.parts or relative.as_posix() != item["path"]:
            raise ValueError("Unsafe manifest path")
        if item["path"] in seen:
            raise ValueError("Duplicate manifest entry")
        seen.add(item["path"])
        path = run / relative
        if (path.is_symlink() or not path.is_file() or type(item["bytes"]) is not int
                or path.stat().st_size != item["bytes"] or sha(path) != item["sha256"]):
            raise ValueError("Release artifact mismatch: " + item["path"])
    actual = {p.relative_to(run).as_posix() for p in run.rglob("*") if p.is_file()}
    if actual != seen | {"RELEASE_MANIFEST.json"}:
        raise ValueError("Release has unmanifested files or missing artifacts")
    return value


def reproduce(run, plan, out):
    from .release_audit import audit
    from .corpus_report import report_corpus
    from .figures import mundane_controls, render
    from .geometry_audit import audit as geometry_audit
    run, out = Path(run).resolve(), Path(out).resolve()
    if out == run or run in out.parents:
        raise ValueError("Reproduction output must be outside the immutable release")
    manifest = verify_manifest(run)
    if sha(plan) != manifest["plan_sha256"]:
        raise ValueError("Plan hash differs from release")
    out.mkdir(parents=True, exist_ok=False)
    report = audit(run, plan, manifest["freeze_commit"])
    (out / "audit.json").write_text(canonical(report) + "\n")
    (out / "frozen_audit.json").write_text(canonical(report["frozen_audit"]) + "\n")
    if not report["pass"]:
        raise ValueError("Release reconstruction audit failed")
    geometry = geometry_audit(run)
    (out / "geometry_audit.json").write_text(canonical(geometry) + "\n")
    if not geometry["pass"]:
        raise ValueError("Independent coordinate arithmetic audit failed")
    render(run, out / "figures")
    mundane_controls(report["frozen_audit"], out / "figures")
    report_corpus(run / "rows", out / "corpus")
    # A second pass verifies the audit/display path did not modify raw artifacts.
    verify_manifest(run)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    result = reproduce(args.run, args.plan, args.out)
    print(canonical({key: result[key] for key in ("pass", "rows", "errors")}))

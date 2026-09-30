"""Publish retrieved replay artifacts; never copy the private lifecycle ledger."""
import argparse
import json
from pathlib import Path, PurePosixPath
import shutil

from experiments.sae_assay_diagnostic.budget import EventLedger
from experiments.sae_assay_diagnostic.protocol import canonical, sha
from scripts.audit_public_release import scan_blob
from .analysis import audit
from .protocol import load_plan

PUBLIC_ROOT_FILES = {
    "cheap-qualification.json", "sae-load.json", "first-five-summary.json",
    "summary.json", "DONE-all.json", "WAITING-first-five.json",
    "APPROVE-first-five", "receipts.jsonl", "pip-freeze.txt", "controller.log",
    "controller-exit.json", "controller-stopped.json",
}


def copy_release(base, destination, plan_path, freeze):
    base, destination = Path(base), Path(destination)
    if destination.exists():
        raise FileExistsError(destination)
    plan = load_plan(plan_path)
    events = EventLedger(base / "events.jsonl", sha(plan_path), freeze, []).read()
    closed = [r for r in events if r["id"] == "closed"]
    if len(closed) != 1 or closed[0]["data"]["get_status"] != 404:
        raise ValueError("Verified pod deletion required")
    receipt = json.loads((base / "final-retrieval.json").read_text())
    if receipt not in events or not receipt["id"].startswith("retrieval:"):
        raise ValueError("Final retrieval is not in the verified lifecycle chain")
    data, closure = receipt["data"], closed[0]["data"]
    if data["pod_id"] != closure["pod_id"]:
        raise ValueError("Retrieval/deletion mismatch")
    root = Path(data["directory"])
    files = data["artifacts"]
    row_paths = {"rows/replay-" + item["id"] + ".json" for item in plan["inputs"]}
    actual = {p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file()}
    if actual != set(files):
        raise ValueError("Retrieved inventory differs from final receipt")
    for name, digest in files.items():
        relative, path = PurePosixPath(name), root / name
        if (relative.is_absolute() or ".." in relative.parts or relative.as_posix() != name
                or path.is_symlink() or not path.is_file() or sha(path) != digest
                or name not in PUBLIC_ROOT_FILES | row_paths
                or any(p.startswith(".") for p in relative.parts)):
            raise ValueError("Unexpected or changed retrieved artifact: " + name)
        if scan_blob(name, path.read_bytes()):
            raise ValueError("Public content scan failed: " + name)
    done = json.loads((root / "DONE-all.json").read_text())
    if (done != {"rows": len(plan["inputs"]), "plan_sha256": sha(plan_path),
                 "freeze_commit": freeze, "native_replay_complete": True,
                 "behavioral_assay_qualified": False}
            or json.loads((root / "controller-exit.json").read_text())["exit_code"] != 0):
        raise ValueError("Incomplete or failed run needs an explicitly labeled failure release")
    checked = audit(root, plan_path)
    if (not checked["pass"] or not checked["complete"] or checked["freeze_commit"] != freeze
            or checked["plan_sha256"] != sha(plan_path)):
        raise ValueError("Full raw-row audit and matching freeze required")
    for name, digest in files.items():
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(root / name, target)
        if sha(target) != digest:
            raise ValueError("Copied artifact mismatch")
    keys = ("pod_id", "get_status", "utc", "elapsed_seconds", "compute_upper_bound_usd",
            "cumulative_upper_bound_usd", "within_limits")
    projection = {"scope": "Projection of private chained receipts; SSH coordinates and local paths omitted",
                  "freeze_commit": freeze, "plan_sha256": sha(plan_path),
                  "closure": {key: closure[key] for key in keys}, "artifacts": files}
    (destination / "retrieval_and_cost.json").write_text(canonical(projection) + "\n")
    return projection


def manifest(directory, plan_path, freeze):
    directory = Path(directory)
    output = directory / "RELEASE_MANIFEST.json"
    if output.exists():
        raise FileExistsError(output)
    files = []
    for path in sorted(directory.rglob("*")):
        if path.is_symlink():
            raise ValueError("Release symlink")
        if path.is_file():
            files.append({"path": path.relative_to(directory).as_posix(),
                          "bytes": path.stat().st_size, "sha256": sha(path)})
    result = {"schema": "sae_native_replay_release_v1", "freeze_commit": freeze,
              "plan_sha256": sha(plan_path), "files": files,
              "reporting_source_hashes": {"experiments/sae_assay_replay/" + name:
                  sha(Path(__file__).parent / name) for name in ("report.py", "release.py")},
              "scope": "Native SAE engineering on saved states; not behavioral qualification"}
    output.write_text(canonical(result) + "\n")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", type=Path)
    parser.add_argument("--destination", type=Path, required=True)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--freeze", required=True)
    parser.add_argument("--manifest-only", action="store_true")
    args = parser.parse_args()
    if args.manifest_only:
        print(canonical({"files": len(manifest(args.destination, args.plan, args.freeze)["files"])}))
    elif args.base is None:
        parser.error("--base required to copy retrieved artifacts")
    else:
        result = copy_release(args.base, args.destination, args.plan, args.freeze)
        print(canonical({"files": len(result["artifacts"]), "closure": result["closure"]}))

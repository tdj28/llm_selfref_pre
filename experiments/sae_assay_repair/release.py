"""Copy verified raw artifacts from closed owned runs into a fresh release.

The private lifecycle ledger is never copied. Its public cost projection omits
SSH coordinates and local paths, while retaining pod IDs and deletion status.
"""
import argparse
import json
from pathlib import Path, PurePosixPath
import shutil

from experiments.sae_assay_diagnostic.budget import EventLedger
from .protocol import canonical, sha


def verified_run(base, plan_hash, freeze):
    base = Path(base)
    if not (base / "events.jsonl").is_file():
        raise ValueError("Existing lifecycle ledger required")
    events = EventLedger(base / "events.jsonl", plan_hash, freeze, []).read()
    closed = [r for r in events if r["id"] == "closed"]
    if len(closed) != 1 or closed[0]["data"]["get_status"] != 404:
        raise ValueError("Verified deletion receipt required before release")
    receipt = json.loads((base / "final-retrieval.json").read_text())
    if receipt not in events or not receipt["id"].startswith("retrieval:"):
        raise ValueError("Final retrieval is not in the chained ledger")
    directory = Path(receipt["data"]["directory"])
    files = receipt["data"]["artifacts"]
    for name, digest in files.items():
        rel = PurePosixPath(name)
        if rel.is_absolute() or ".." in rel.parts or name != rel.as_posix():
            raise ValueError("Unsafe artifact path")
        path = directory / name
        if path.is_symlink() or not path.is_file() or sha(path) != digest:
            raise ValueError("Retrieved artifact hash/type mismatch")
        if not (rel.parts[0] in {"rows", "residuals"} or len(rel.parts) == 1):
            raise ValueError("Unexpected nested artifact directory")
        if rel.suffix not in {".json", ".jsonl", ".txt", ".log", ".safetensors"} and not name.startswith("APPROVE-"):
            raise ValueError("Unexpected artifact type")
        if name.startswith(".") or any(s in name.lower() for s in ("hf.env", "private", "credential", "secret")):
            raise ValueError("Private artifact path")
    if json.loads((directory / "controller-exit.json").read_text())["exit_code"] != 0:
        raise ValueError("Successful controller exit required for complete release")
    if receipt["data"]["pod_id"] != closed[0]["data"]["pod_id"]:
        raise ValueError("Retrieval/deletion pod mismatch")
    keys = ("pod_id", "get_status", "utc", "elapsed_seconds", "compute_upper_bound_usd",
            "repair_upper_bound_usd", "cumulative_upper_bound_usd", "within_limits")
    return directory, files, {key: closed[0]["data"][key] for key in keys}


def copy_release(controller_root, destination, plan, freeze):
    destination = Path(destination)
    if destination.exists():
        raise FileExistsError(destination)
    plan_hash = sha(plan)
    runs = {kind: verified_run(Path(controller_root) / kind, plan_hash, freeze)
            for kind in ("cheap", "main")}
    cheap = json.loads((runs["cheap"][0] / "cheap-qualification.json").read_text())
    if cheap.get("pass") is not True or cheap.get("device") != "cuda" or not all(cheap["checks"].values()):
        raise ValueError("Passing CUDA qualification required")
    done = json.loads((runs["main"][0] / "DONE-all.json").read_text())
    if done.get("status") != "complete":
        raise ValueError("Incomplete run must use an explicitly labeled failure release")
    destination.mkdir(parents=True)
    for kind, (directory, files, _closed) in runs.items():
        target = destination if kind == "main" else destination / "cuda_qualification"
        for name, digest in files.items():
            out = target / name
            out.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(directory / name, out)
            if sha(out) != digest:
                raise ValueError("Copied artifact hash mismatch")
    projection = {"scope": "Projection of private chained lifecycle receipts; SSH/local paths omitted.",
                  "freeze_commit": freeze, "plan_sha256": plan_hash,
                  "pods": {kind: closed for kind, (_directory, _files, closed) in runs.items()},
                  "artifacts": {kind: files for kind, (_directory, files, _closed) in runs.items()}}
    (destination / "retrieval_and_cost.json").write_text(canonical(projection) + "\n")
    return projection


def manifest(directory, freeze, plan):
    directory = Path(directory)
    output = directory / "RELEASE_MANIFEST.json"
    if output.exists():
        raise FileExistsError(output)
    files = []
    for path in sorted(directory.rglob("*")):
        if path.is_symlink():
            raise ValueError("No release symlinks")
        if path.is_file():
            files.append({"path": path.relative_to(directory).as_posix(),
                          "bytes": path.stat().st_size, "sha256": sha(path)})
    result = {"schema": "sae_assay_repair_release_v1", "freeze_commit": freeze,
              "plan_sha256": sha(plan), "files": files,
              "scope": "Post-Stage-1 engineering diagnostics; no consciousness-report experiment."}
    output.write_text(canonical(result) + "\n")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--controller-root", type=Path)
    parser.add_argument("--destination", type=Path, required=True)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--freeze", required=True)
    parser.add_argument("--manifest-only", action="store_true")
    args = parser.parse_args()
    if args.manifest_only:
        result = manifest(args.destination, args.freeze, args.plan)
        print(canonical({"files": len(result["files"]), "plan_sha256": result["plan_sha256"]}))
    else:
        if args.controller_root is None:
            parser.error("--controller-root required to copy a release")
        copy_release(args.controller_root, args.destination, args.plan, args.freeze)

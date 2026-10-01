#!/usr/bin/env python3
"""Package a COMPLETE automated rubric audit from an explicit source Git commit.

Never reads the source working-tree result directory. No network/API calls.
Existing packages are not overwritten; verification is a separate read-only CLI.
"""

from __future__ import annotations

import argparse
import importlib.util
from pathlib import Path
import tempfile
import sys


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("verify_rubric_audit", ROOT / "scripts/verify_rubric_audit.py")
verify = importlib.util.module_from_spec(spec)
spec.loader.exec_module(verify)


def build(source_repo, source_commit, source_run_path, destination):
    verify.check_commit(source_commit)
    source_run_path = str(verify.relative(source_run_path))
    destination = Path(destination)
    verify.require(not destination.exists(), "Refusing to overwrite an existing audit package")
    blobs = {name: verify.git_blob(source_repo, source_commit, f"{source_run_path}/{suffix}")
             for name, suffix in verify.INPUTS.items()}
    # Validate coverage and every manuscript-bound count before writing anything.
    result = verify.recompute(blobs)
    outputs = verify.generated(result)
    manifest = {
        "schema_version": 1, "source_repository": verify.SOURCE_URL,
        "source_commit": source_commit, "source_run_path": source_run_path, "scope": verify.SCOPE,
        "inputs": {
            name: {"path": f"inputs/{name}", "source_path": f"{source_run_path}/{verify.INPUTS[name]}",
                   "source_commit": source_commit,
                   "source_url": f"{verify.SOURCE_URL}/blob/{source_commit}/{source_run_path}/{verify.INPUTS[name]}",
                   "sha256": verify.sha256(blob), "bytes": len(blob),
                   "copy_policy": "Complete pinned blob; no row filtering or rewriting"}
            for name, blob in blobs.items()
        },
        "generators": {path: verify.sha256((ROOT / path).read_bytes()) for path in verify.GENERATORS},
        "outputs": {name: verify.sha256(blob) for name, blob in outputs.items()},
    }
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".rubric-audit-", dir=destination.parent) as temporary:
        stage = Path(temporary) / "package"
        (stage / "inputs").mkdir(parents=True)
        for name, blob in blobs.items():
            (stage / "inputs" / name).write_bytes(blob)
        for name, blob in outputs.items():
            (stage / name).write_bytes(blob)
        (stage / "manifest.json").write_bytes(verify.json_bytes(manifest))
        verify.verify(stage, source_repo)
        verify.require(not destination.exists(), "Destination appeared during build")
        stage.rename(destination)
    return destination


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-repo", required=True, type=Path)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--source-run-path", required=True,
                        help="Repository-relative run directory at the supplied commit")
    parser.add_argument("--outdir", type=Path, default=verify.DEFAULT_PACKAGE)
    args = parser.parse_args(argv)
    try:
        print(build(args.source_repo, args.source_commit, args.source_run_path, args.outdir))
        return 0
    except (ValueError, KeyError, TypeError, OSError) as error:
        print(f"FAIL: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

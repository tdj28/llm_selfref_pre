#!/usr/bin/env python3
"""Materialize and hash-verify public SAE/J-lens v2 residual shards from OSF."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import urllib.request
from pathlib import Path


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def materialize(manifest_path: Path, outdir: Path) -> dict[str, object]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    records = manifest.get("files", [])
    if manifest.get("status") != "verified_complete" or len(records) != 16:
        raise ValueError("Expected a verified 16-shard OSF upload manifest")
    outdir.mkdir(parents=True, exist_ok=True)
    completed = []
    for record in records:
        path = outdir / record["name"]
        expected_hash = str(record["sha256"])
        expected_bytes = int(record["bytes"])
        if (
            path.is_file()
            and path.stat().st_size == expected_bytes
            and sha256_file(path) == expected_hash
        ):
            status = "verified_existing"
        else:
            temporary = path.with_suffix(path.suffix + ".tmp")
            digest = hashlib.sha256()
            size = 0
            request = urllib.request.Request(
                record["download_url"], headers={"Accept": "application/octet-stream"}
            )
            with urllib.request.urlopen(request, timeout=600) as response, temporary.open(
                "wb"
            ) as handle:
                for chunk in iter(lambda: response.read(1024 * 1024), b""):
                    handle.write(chunk)
                    digest.update(chunk)
                    size += len(chunk)
            if size != expected_bytes or digest.hexdigest() != expected_hash:
                temporary.unlink(missing_ok=True)
                raise ValueError(f"Downloaded residual differs: {record['name']}")
            os.replace(temporary, path)
            status = "downloaded_and_verified"
        completed.append(
            {
                "name": record["name"],
                "bytes": expected_bytes,
                "sha256": expected_hash,
                "status": status,
            }
        )
    return {
        "status": "verified_complete",
        "shards": len(completed),
        "bytes": sum(int(record["bytes"]) for record in completed),
        "files": completed,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--outdir", type=Path, required=True)
    args = parser.parse_args()
    result = materialize(args.manifest.resolve(), args.outdir.resolve())
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

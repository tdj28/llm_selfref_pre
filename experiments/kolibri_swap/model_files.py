"""Verify downloaded model bytes against the frozen PLAN and public revision."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re

from .bootstrap import MODEL, MODEL_REVISION
from .protocol import PLAN


def artifact_inventory(plan):
    if (plan.get("schema") != "kolibri-swap-v1"
            or plan.get("models", {}).get("kolibri", {}).get("id") != MODEL
            or plan.get("metadata", {}).get("hf_revision") != MODEL_REVISION):
        raise ValueError("Frozen model identity or revision differs")
    artifacts = plan["metadata"]["model_artifacts"]
    files, weight_map = artifacts["files"], artifacts["weight_map"]
    if not isinstance(files, dict) or not isinstance(weight_map, dict) or not weight_map:
        raise ValueError("Frozen model inventory is missing")
    if not all(isinstance(key, str) and isinstance(value, str) and value.endswith(".safetensors")
               for key, value in weight_map.items()):
        raise ValueError("Invalid frozen weight map")
    required = {"config.json", "model.safetensors.index.json", "tokenizer.json", "tokenizer_config.json",
                *weight_map.values()}
    if not required <= set(files):
        raise ValueError("Frozen model inventory is incomplete")
    for name, record in files.items():
        if (not isinstance(name, str) or not name or Path(name).is_absolute()
                or ".." in Path(name).parts or "\\" in name or Path(name).as_posix() != name
                or not isinstance(record, dict)
                or not re.fullmatch(r"[0-9a-f]{64}", str(record.get("sha256", "")))
                or type(record.get("size")) is not int or record["size"] <= 0):
            raise ValueError("Invalid frozen model file")
    return files, weight_map


def verify_download(root, info, plan):
    frozen, weight_map = artifact_inventory(plan)
    if info.sha != MODEL_REVISION:
        raise ValueError("Published model revision differs")
    published = {file.rfilename: file for file in info.siblings}
    if len(published) != len(info.siblings) or not set(frozen) <= set(published):
        raise ValueError("Published inventory differs from frozen model files")
    root = Path(root)
    records = []
    for name, file in sorted(published.items()):
        if (Path(name).is_absolute() or ".." in Path(name).parts
                or "\\" in name or Path(name).as_posix() != name):
            raise ValueError("Unsafe published model filename")
        path = root / name
        h, size = hashlib.sha256(), 0
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(8 * 1024**2), b""):
                h.update(chunk)
                size += len(chunk)
        digest = h.hexdigest()
        expected = frozen.get(name)
        if expected is not None and (digest != expected["sha256"] or size != expected["size"]):
            raise ValueError("Frozen model file mismatch: " + name)
        if file.lfs is not None and digest != file.lfs.sha256:
            raise ValueError("Published LFS hash mismatch: " + name)
        records.append({"path": name, "bytes": size, "sha256": digest,
                        "frozen_sha256": None if expected is None else expected["sha256"],
                        "published_lfs_sha256": None if file.lfs is None else file.lfs.sha256})
    # Byte identity binds config/tokenizer semantics; the separate map check
    # also rejects an internally inconsistent frozen index and shard inventory.
    index = json.loads((root / "model.safetensors.index.json").read_bytes())
    if not isinstance(index, dict) or index.get("weight_map") != weight_map:
        raise ValueError("Downloaded weight map differs from frozen PLAN")
    config = json.loads((root / "config.json").read_bytes())
    if not isinstance(config, dict) or not config:
        raise ValueError("Downloaded model config is not an object")
    if not any(r["path"] in set(weight_map.values()) and r["published_lfs_sha256"] for r in records):
        raise ValueError("No hash-verified weights")
    return {"model": MODEL, "revision": MODEL_REVISION, "files": records,
            "frozen_files_verified": len(frozen), "weight_map_verified": True,
            "config_verified": True, "verified": True}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", default=PLAN)
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    plan_bytes = Path(args.plan).read_bytes()
    plan = json.loads(plan_bytes)
    artifact_inventory(plan)
    from huggingface_hub import HfApi, snapshot_download
    info = HfApi(token=False).model_info(MODEL, revision=MODEL_REVISION, files_metadata=True)
    if info.sha != MODEL_REVISION:
        raise ValueError("Model revision differs")
    root = Path(snapshot_download(MODEL, revision=MODEL_REVISION, token=False))
    report = verify_download(root, info, plan)
    report["plan_sha256"] = hashlib.sha256(plan_bytes).hexdigest()
    with Path(args.out).open("x") as stream:
        json.dump(report, stream, indent=2)
        stream.write("\n")


if __name__ == "__main__":
    main()

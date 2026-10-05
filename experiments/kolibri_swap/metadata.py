"""Fetch public artifact identities without downloading model weights."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from urllib.request import urlopen

from experiments.openrouter_swap.runner import write_once
from . import protocol as p


def get(url):
    with urlopen(url, timeout=60) as response:
        return response.read()


def collect(basis):
    revision = p.PINS["hf_revision"]
    model = p.MODEL["id"]
    root = f"https://huggingface.co/{model}/resolve/{revision}/"
    info = json.loads(get(f"https://huggingface.co/api/models/{model}/revision/{revision}?blobs=true"))
    if info["sha"] != revision:
        raise ValueError("Model revision changed")
    index = json.loads(get(root + "model.safetensors.index.json"))
    required = {"config.json", "model.safetensors.index.json", "tokenizer.json", "tokenizer_config.json",
                *index["weight_map"].values()}
    files = {}
    for entry in info["siblings"]:
        name = entry["rfilename"]
        if name not in required:
            continue
        if Path(name).is_absolute() or ".." in Path(name).parts:
            raise ValueError("Unsafe artifact filename")
        lfs = entry.get("lfs")
        if lfs:
            digest, size = lfs["sha256"], lfs["size"]
        else:
            if entry["size"] > 32 * 1024 * 1024:
                raise ValueError("Unexpected non-LFS artifact size")
            content = get(root + name)
            digest, size = hashlib.sha256(content).hexdigest(), len(content)
        if size != entry["size"]:
            raise ValueError("Published artifact size differs")
        files[name] = {"sha256": digest, "size": size, "source": "published_lfs" if lfs else "download_sha256"}
    if set(files) != required:
        raise ValueError("Incomplete model file inventory")
    snapshots = {}
    for spec in p.JUDGES.values():
        url = "https://openrouter.ai/api/v1/models/" + spec["id"] + "/endpoints"
        catalog = json.loads(get(url))["data"]
        endpoint = next(e for e in catalog["endpoints"] if e["tag"] == spec["provider_slug"])
        snapshots[spec["id"]] = {"url": url, "endpoint": endpoint}
    stamp = datetime.now(timezone.utc).isoformat()
    basis = Path(basis).resolve()
    relative = basis.relative_to(p.ROOT.resolve()).as_posix()
    return {**p.PINS, "approved": True, "checked_at_utc": stamp,
            "gpu_hourly_usd": "4.59", "storage_hourly_usd": "0.10",
            "model_artifacts": {"files": files, "weight_map": index["weight_map"]},
            "endpoint_snapshots": snapshots,
            "spend_reconciliation": {"as_of": stamp, "openrouter_prior_and_reserved_usd": "136",
                                     "runpod_prior_and_reserved_usd": "50",
                                     "source_hashes": {relative: p.sha(basis)}}}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--basis", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    metadata = collect(args.basis)
    write_once(args.out, metadata)
    print(json.dumps({"artifacts": len(metadata["model_artifacts"]["files"]),
                      "blockers": p.metadata_blockers(metadata)}))

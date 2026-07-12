#!/usr/bin/env python3
"""Snapshot public Neuronpedia labels for the pinned Goodfire Llama SAE."""

from __future__ import annotations

import argparse
import concurrent.futures
import gzip
import hashlib
import json
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
BUCKET = "https://neuronpedia-datasets.s3.us-east-1.amazonaws.com"
PREFIX = "v1/llama3.3-70b-it/50-resid-post-gf/explanations/"
MODEL_ID = "llama3.3-70b-it"
SOURCE_ID = "50-resid-post-gf"
DICTIONARY_SIZE = 65_536
EXPECTED_EXPLANATION_TYPE = "np_acts-logits-general"
EXPECTED_EXPLANATION_MODEL = "gemini-2.5-flash-lite"
DEFAULT_OUTDIR = (
    REPO_ROOT / "data/sae_jlens_audit/neuronpedia_labels_20260712"
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def fetch(url: str, timeout: int = 60) -> bytes:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "praxagent-sae-jlens-label-snapshot/1.0"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def list_source_objects() -> list[dict[str, Any]]:
    query = urllib.parse.urlencode(
        {"list-type": "2", "prefix": PREFIX, "max-keys": "1000"}
    )
    root = ET.fromstring(fetch(f"{BUCKET}/?{query}"))
    namespace = {"s3": "http://s3.amazonaws.com/doc/2006-03-01/"}
    if root.findtext("s3:IsTruncated", default="false", namespaces=namespace) != "false":
        raise RuntimeError("Neuronpedia source listing was unexpectedly truncated")

    objects: list[dict[str, Any]] = []
    for node in root.findall("s3:Contents", namespace):
        key = node.findtext("s3:Key", namespaces=namespace)
        if not key:
            raise ValueError("Neuronpedia source listing contains an empty key")
        objects.append(
            {
                "key": key,
                "last_modified": node.findtext(
                    "s3:LastModified", namespaces=namespace
                ),
                "etag": (node.findtext("s3:ETag", namespaces=namespace) or "").strip(
                    '"'
                ),
                "bytes": int(node.findtext("s3:Size", namespaces=namespace) or "-1"),
            }
        )
    return sorted(objects, key=lambda row: str(row["key"]))


def parse_batch(source: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    key = str(source["key"])
    compressed = fetch(f"{BUCKET}/{urllib.parse.quote(key, safe='/')}")
    if len(compressed) != int(source["bytes"]):
        raise ValueError(f"Source byte count changed during retrieval: {key}")
    source_record = {**source, "sha256": sha256_bytes(compressed)}

    rows: list[dict[str, Any]] = []
    for line_number, raw_line in enumerate(gzip.decompress(compressed).splitlines(), 1):
        if not raw_line.strip():
            continue
        payload = json.loads(raw_line)
        feature_id = int(payload["index"])
        if payload.get("modelId") != MODEL_ID or payload.get("layer") != SOURCE_ID:
            raise ValueError(f"Unexpected model/source in {key}:{line_number}")
        if not 0 <= feature_id < DICTIONARY_SIZE:
            raise ValueError(f"Out-of-range feature ID in {key}:{line_number}")
        description = str(payload.get("description", "")).strip()
        if not description:
            raise ValueError(f"Empty explanation in {key}:{line_number}")
        rows.append(
            {
                "feature_id": feature_id,
                "description": description,
                "description_sha256": sha256_bytes(description.encode("utf-8")),
                "explanation_id": str(payload.get("id", "")),
                "explanation_type": str(payload.get("typeName", "")),
                "explanation_model": str(payload.get("explanationModelName", "")),
                "created_at": str(payload.get("createdAt", "")),
                "source_key": key,
            }
        )
    return source_record, rows


def write_json(path: Path, payload: Any) -> None:
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True) + "\n")


def file_record(path: Path, root: Path) -> dict[str, Any]:
    return {
        "path": path.relative_to(root).as_posix(),
        "bytes": path.stat().st_size,
        "sha256": sha256_file(path),
    }


def snapshot(outdir: Path, workers: int) -> dict[str, Any]:
    outdir.mkdir(parents=True, exist_ok=False)
    source_objects = list_source_objects()
    batch_objects = [
        row
        for row in source_objects
        if str(row["key"]).endswith(".jsonl.gz")
        and "/batch-" in str(row["key"])
    ]
    config_objects = [
        row for row in source_objects if str(row["key"]).endswith("/config.json")
    ]
    if len(config_objects) != 1:
        raise ValueError(f"Expected one source config, found {len(config_objects)}")
    if not batch_objects:
        raise ValueError("No Neuronpedia explanation batches found")

    config_bytes = fetch(
        f"{BUCKET}/{urllib.parse.quote(str(config_objects[0]['key']), safe='/')}"
    )
    if len(config_bytes) != int(config_objects[0]["bytes"]):
        raise ValueError("Source config byte count changed during retrieval")
    config = json.loads(config_bytes)
    if config.get("explainer_type_name") != EXPECTED_EXPLANATION_TYPE:
        raise ValueError("Unexpected Neuronpedia explanation type")
    if config.get("explainer_model_name") != EXPECTED_EXPLANATION_MODEL:
        raise ValueError("Unexpected Neuronpedia explanation model")

    labels: list[dict[str, Any]] = []
    batch_records: list[dict[str, Any]] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
        futures = [executor.submit(parse_batch, row) for row in batch_objects]
        for future in concurrent.futures.as_completed(futures):
            source_record, rows = future.result()
            batch_records.append(source_record)
            labels.extend(rows)

    labels.sort(key=lambda row: int(row["feature_id"]))
    feature_ids = [int(row["feature_id"]) for row in labels]
    if len(feature_ids) != len(set(feature_ids)):
        raise ValueError("Neuronpedia label snapshot contains duplicate feature IDs")
    unexpected_types = sorted(
        {
            str(row["explanation_type"])
            for row in labels
            if row["explanation_type"] != EXPECTED_EXPLANATION_TYPE
        }
    )
    unexpected_models = sorted(
        {
            str(row["explanation_model"])
            for row in labels
            if row["explanation_model"] != EXPECTED_EXPLANATION_MODEL
        }
    )
    if unexpected_types or unexpected_models:
        raise ValueError(
            "Unexpected label provenance: "
            f"types={unexpected_types}, models={unexpected_models}"
        )

    missing_ids = sorted(set(range(DICTIONARY_SIZE)).difference(feature_ids))
    labels_path = outdir / "labels.jsonl"
    objects_path = outdir / "source_objects.jsonl"
    config_path = outdir / "source_config.json"
    missing_path = outdir / "missing_feature_ids.json"
    write_jsonl(labels_path, labels)
    write_jsonl(objects_path, sorted(batch_records, key=lambda row: str(row["key"])))
    write_json(config_path, config)
    write_json(missing_path, missing_ids)

    manifest = {
        "schema_version": 1,
        "status": "public_label_snapshot",
        "retrieved_at_utc": utc_now(),
        "source": {
            "documentation_url": "https://docs.neuronpedia.org/api",
            "bucket": BUCKET,
            "prefix": PREFIX,
            "model_id": MODEL_ID,
            "source_id": SOURCE_ID,
            "explanation_type": EXPECTED_EXPLANATION_TYPE,
            "explanation_model": EXPECTED_EXPLANATION_MODEL,
            "config_object": {
                **config_objects[0],
                "sha256": sha256_bytes(config_bytes),
            },
        },
        "coverage": {
            "dictionary_size": DICTIONARY_SIZE,
            "labels": len(labels),
            "missing": len(missing_ids),
            "batch_objects": len(batch_records),
            "compressed_source_bytes": sum(
                int(row["bytes"]) for row in batch_records
            ),
        },
        "files": [
            file_record(path, outdir)
            for path in (labels_path, objects_path, config_path, missing_path)
        ],
        "claim_boundary": (
            "These are mutable third-party autointerpretability labels, not "
            "ground-truth feature semantics or Goodfire-authored labels."
        ),
    }
    manifest_path = outdir / "SNAPSHOT_MANIFEST.json"
    write_json(manifest_path, manifest)
    manifest["manifest_sha256"] = sha256_file(manifest_path)
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--outdir", type=Path, default=DEFAULT_OUTDIR)
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args()
    if not 1 <= args.workers <= 16:
        raise SystemExit("--workers must be between 1 and 16")
    manifest = snapshot(args.outdir.resolve(), args.workers)
    print(
        json.dumps(
            {
                "status": "pass",
                "outdir": str(args.outdir.resolve()),
                "labels": manifest["coverage"]["labels"],
                "missing": manifest["coverage"]["missing"],
                "manifest_sha256": manifest["manifest_sha256"],
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()

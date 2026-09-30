#!/usr/bin/env python3
"""Narrow, stdlib-only release validation for the frozen repair's clean states.

Build RESIDUAL_CAPTURES.json after copying the verified remote artifacts and
before building RELEASE_MANIFEST.json::

    python scripts/audit_sae_residual_release.py --build-inventory \
        --run data/sae_assay_repair/coordinate_delivery_20260930 \
        --plan data/sae_assay_repair/plan_20260930/PLAN.json

Building an inventory NEVER authorizes it. A parent must inspect the actual
captures, provenance and rights, then explicitly pin its digest in the registry.
The public scanner rechecks indexed bytes, not this builder's working tree.
Hashes establish integrity/declared provenance, not proof of model execution.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import stat
import struct
from collections import Counter
from pathlib import Path, PurePosixPath
from typing import Callable, Mapping


RELEASE_ROOT = "data/sae_assay_repair/coordinate_delivery_20260930"
PLAN_PATH = "data/sae_assay_repair/plan_20260930/PLAN.json"
PLAN_SHA256 = "1a07eeec50344e1d1aef61295e5cd187788f6c4a1937c1eeaec0cacc46c7abd2"
FREEZE_COMMIT = "b7c4d7f5fba80dd2b067c200fdf2f322c80c3cae"
INVENTORY_NAME = "RESIDUAL_CAPTURES.json"
MANIFEST_NAME = "RELEASE_MANIFEST.json"
CAPTURE_COUNT = 544
HIDDEN_WIDTH = 8192
VOCAB_SIZE = 128256
MAX_TOKENS = 512
MAX_HEADER_BYTES = 4096
MAX_CAPTURE_BYTES = 8 + MAX_HEADER_BYTES + MAX_TOKENS * (2 * HIDDEN_WIDTH + 8)
MAX_JSON_BYTES = 32 * 1024 * 1024

# Reviewed 2026-09-30: 544 finite clean BF16 states, exact tokens/receipts,
# no weight tensors; pinned upstream terms accompany this one release.
APPROVED_RESIDUAL_INVENTORIES: dict[str, str] = {
    RELEASE_ROOT: "33bf2d6cd5d87b33d66638343d8e5ff7adddb274b6b7da6f23a51c9e9f163693",
}

Records = Mapping[str, tuple[int, str]]
ReadBlob = Callable[[str, int], bytes]


class ResidualAuditError(ValueError):
    """Messages are fixed rule names; never expose parsed values or payloads."""


def require(condition: bool, rule: str) -> None:
    if not condition:
        raise ResidualAuditError(rule)


def canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("ascii") + b"\n"


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def strict_json(raw: bytes):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, "duplicate-json-key")
            result[key] = value
        return result

    def number(value):
        result = float(value)
        require(math.isfinite(result), "nonfinite-json-number")
        return result

    def constant(_value):
        raise ResidualAuditError("nonfinite-json-number")

    try:
        return json.loads(raw.decode("utf-8"), object_pairs_hook=pairs,
                          parse_float=number, parse_constant=constant)
    except ResidualAuditError:
        raise
    except (ValueError, RecursionError, OverflowError) as exc:
        raise ResidualAuditError("invalid-json") from exc


def keys(value, expected, rule):
    require(isinstance(value, dict) and set(value) == set(expected), rule)


def integer(value, minimum=0, maximum=None):
    return type(value) is int and value >= minimum and (maximum is None or value <= maximum)


def digest(value):
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def relative_path(value):
    require(isinstance(value, str) and bool(value), "invalid-artifact-path")
    path = PurePosixPath(value)
    require(not path.is_absolute() and ".." not in path.parts
            and value == path.as_posix() and value != "."
            and "\\" not in value and all(ord(c) >= 32 and ord(c) != 127 for c in value),
            "invalid-artifact-path")
    return value


def validate_capture(raw: bytes, tokens: list[int]) -> None:
    """Validate the entire container without torch, numpy, pickle or a model."""
    require(isinstance(tokens, list) and 1 <= len(tokens) <= MAX_TOKENS
            and all(integer(t, 0, VOCAB_SIZE - 1) for t in tokens), "invalid-row-tokens")
    require(8 <= len(raw) <= MAX_CAPTURE_BYTES, "residual-size-limit")
    header_size = struct.unpack_from("<Q", raw)[0]
    require(0 < header_size <= MAX_HEADER_BYTES and header_size % 8 == 0
            and 8 + header_size <= len(raw), "invalid-residual-header-size")
    header_raw = raw[8:8 + header_size]
    require(header_raw.startswith(b"{") and header_raw.rstrip(b" ").endswith(b"}"),
            "invalid-residual-header-padding")
    header = strict_json(header_raw)
    keys(header, ("hidden", "token_ids"), "invalid-residual-tensors")
    n = len(tokens)
    specs = {"hidden": ("BF16", [1, n, HIDDEN_WIDTH], 2 * n * HIDDEN_WIDTH),
             "token_ids": ("I64", [1, n], 8 * n)}
    ranges = []
    for name, (dtype, shape, size) in specs.items():
        entry = header[name]
        keys(entry, ("dtype", "shape", "data_offsets"), "invalid-tensor-descriptor")
        require(entry["dtype"] == dtype and isinstance(entry["shape"], list)
                and all(integer(d, 1) for d in entry["shape"])
                and entry["shape"] == shape, "invalid-tensor-dtype-shape")
        offsets = entry["data_offsets"]
        require(isinstance(offsets, list) and len(offsets) == 2
                and all(integer(o) for o in offsets)
                and offsets[1] - offsets[0] == size, "invalid-tensor-offsets")
        ranges.append((offsets[0], offsets[1]))
    ranges.sort()
    payload_size = n * (2 * HIDDEN_WIDTH + 8)
    require(ranges[0][0] == 0 and ranges[0][1] == ranges[1][0]
            and ranges[1][1] == payload_size
            and len(raw) == 8 + header_size + payload_size, "invalid-residual-payload-layout")
    payload = memoryview(raw)[8 + header_size:]
    start, end = header["token_ids"]["data_offsets"]
    actual = [item[0] for item in struct.iter_unpack("<q", payload[start:end])]
    require(actual == tokens, "residual-token-mismatch")
    start, end = header["hidden"]["data_offsets"]
    require(all((value & 0x7f80) != 0x7f80
                for (value,) in struct.iter_unpack("<H", payload[start:end])),
            "nonfinite-residual")


class Evidence:
    def __init__(self, paths, records: Records, modes: Mapping[str, str], read: ReadBlob):
        self.paths, self.records, self.modes, self.read = set(paths), records, modes, read

    def record(self, path):
        require(path in self.paths and path in self.records, "missing-residual-evidence")
        require(self.modes.get(path) == "100644", "nonregular-residual-evidence")
        size, checksum = self.records[path]
        require(integer(size) and digest(checksum), "invalid-evidence-record")
        return {"path": path.removeprefix(RELEASE_ROOT + "/"), "bytes": size, "sha256": checksum}

    def blob(self, path, limit=MAX_JSON_BYTES):
        record = self.record(path)
        require(record["bytes"] <= limit, "residual-evidence-size-limit")
        raw = self.read(path, limit)
        require(len(raw) == record["bytes"] and sha256(raw) == record["sha256"],
                "residual-evidence-hash-mismatch")
        return raw

    def json(self, relative):
        return strict_json(self.blob(RELEASE_ROOT + "/" + relative))


def planned_row_ids(plan):
    ids = {"qualification-live"}
    for item in plan["texts"]:
        ids.add("clean-" + item["id"])
        for operator in plan["operators"]:
            for mode in ("suppression", "amplification"):
                for strength in plan["strengths"]:
                    ids.add(f"edit-{operator}-{item['id']}-{mode}-{round(strength * 100):03d}")
    ids.update("context-" + context + "-" + item["id"]
               for context in plan["positive_contexts"]
               for item in plan["positive_control"]["calibration_texts"])
    ids.update(item["id"] for item in plan["formatting_rows"])
    return ids


def validate_ledger(raw, plan, evidence):
    expected = planned_row_ids(plan)
    require(raw.endswith(b"\n"), "truncated-worker-ledger")
    previous, seen, dispatched, completed = None, set(), set(), {}
    for seq, line in enumerate(raw.splitlines(keepends=True)):
        event = strict_json(line)
        keys(event, ("id", "seq", "data", "plan_sha256", "freeze_commit",
                     "previous_sha256", "sha256"), "invalid-worker-event")
        require(canonical(event) == line and integer(event["seq"])
                and event["seq"] == seq and event["previous_sha256"] == previous
                and event["plan_sha256"] == PLAN_SHA256 and event["freeze_commit"] == FREEZE_COMMIT,
                "worker-ledger-binding-mismatch")
        body = {key: value for key, value in event.items() if key != "sha256"}
        require(event["sha256"] == sha256(canonical(body)[:-1]), "worker-ledger-hash-mismatch")
        identifier, data = event["id"], event["data"]
        require(isinstance(identifier, str) and identifier not in seen and isinstance(data, dict),
                "invalid-worker-event-id")
        if seq == 0:
            require(identifier == "binding" and data == {"kind": "binding", "row_ids": sorted(expected)},
                    "worker-inventory-mismatch")
        kind = data.get("kind")
        require(isinstance(kind, str) and kind in {"binding", "runtime", "dispatch", "row"},
                "invalid-worker-event-kind")
        if kind == "binding":
            require(seq == 0, "duplicate-worker-binding")
        if kind == "runtime":
            require(identifier == "runtime" and data.get("stage") == "post_stage1_engineering_repair",
                    "invalid-worker-runtime")
        if kind in {"dispatch", "row"}:
            rid = data.get("row_id")
            require(isinstance(rid, str) and rid in expected and identifier == kind + ":" + rid,
                    "unknown-worker-row")
            if kind == "dispatch":
                require(rid not in dispatched, "duplicate-worker-dispatch")
                dispatched.add(rid)
            else:
                require(rid in dispatched and rid not in completed, "unbound-worker-row")
                keys(data, ("kind", "row_id", "payload"), "invalid-worker-row-receipt")
                payload = data["payload"]
                keys(payload, ("path", "sha256"), "invalid-worker-row-payload")
                require(payload["path"] == "rows/" + rid + ".json", "worker-row-path-mismatch")
                record = evidence.record(RELEASE_ROOT + "/" + payload["path"])
                require(record["sha256"] == payload["sha256"], "worker-row-hash-mismatch")
                completed[rid] = payload
        previous = event["sha256"]
        seen.add(identifier)
    require("runtime" in seen and dispatched == set(completed), "incomplete-worker-ledger")
    require({"clean-" + item["id"] for item in plan["texts"]} <= completed.keys(),
            "missing-clean-row-receipts")
    return completed, previous


def validate_row(row, item, plan):
    keys(row, ("id", "text_id", "split", "category", "corpus", "group", "mode",
               "strength", "capture", "result"), "invalid-clean-row-schema")
    require(row["id"] == "clean-" + item["id"]
            and all(row[key] == item[key if key != "text_id" else "id"]
                    for key in ("text_id", "split", "category", "corpus"))
            and row["group"] == "literal" and row["mode"] == "zero"
            and type(row["strength"]) in (int, float) and row["strength"] == 0,
            "clean-row-plan-mismatch")
    result = row["result"]
    require(isinstance(result, dict), "invalid-clean-result")
    tokens = result.get("token_ids")
    require(isinstance(tokens, list) and 1 <= len(tokens) <= MAX_TOKENS
            and all(integer(t, 0, VOCAB_SIZE - 1) for t in tokens), "invalid-row-tokens")
    n = len(tokens)
    require(all(type(result.get(k)) is int and result[k] == n
                for k in ("input_tokens", "prompt_length"))
            and type(result.get("output_tokens")) is int and result["output_tokens"] == 0
            and canonical(result.get("input_token_ids")) == canonical(tokens)
            and result.get("output_token_ids") == []
            and result.get("forward_schedule") == "uncached_teacher"
            and result.get("full_sae_diagnostics") is True, "invalid-clean-forward")
    telemetry = result.get("telemetry")
    require(isinstance(telemetry, dict), "invalid-clean-telemetry")
    for key, expected in {
        "schema_version": "sae_assay_backend_v2", "hook_layer": "model.layers.50.output",
        "native_dtype": "torch.bfloat16", "padding": "none", "repair_operator": "literal",
        "feature_ids": plan["target_feature_ids"], "full_encode_shape": [1, 65536, HIDDEN_WIDTH],
        "hook_removed": True, "q90": None,
    }.items():
        require(key in telemetry and canonical(telemetry[key]) == canonical(expected),
                "clean-telemetry-binding-mismatch")
    require(canonical(result.get("clean_telemetry")) == canonical(telemetry),
            "clean-reference-telemetry-mismatch")
    positions = telemetry.get("position_metadata")
    require(isinstance(positions, list) and len(positions) == n, "invalid-clean-positions")
    for i, position in enumerate(positions):
        keys(position, ("position", "token_id", "origin", "token_class", "terminal_observation_only"),
             "invalid-clean-position")
        require(type(position["position"]) is int and position["position"] == i
                and type(position["token_id"]) is int and position["token_id"] == tokens[i]
                and position["origin"] == "prompt" and isinstance(position["token_class"], str)
                and position["token_class"] in {"special", "prompt"}
                and position["terminal_observation_only"] is False, "clean-position-mismatch")
    capture = row["capture"]
    keys(capture, ("path", "sha256", "bytes"), "invalid-capture-receipt")
    require(capture["path"] == "residuals/" + item["id"] + ".safetensors"
            and integer(capture["bytes"], 1, MAX_CAPTURE_BYTES) and digest(capture["sha256"]),
            "invalid-capture-receipt")
    return tokens


def inspect_release(evidence: Evidence):
    """Reconstruct an inventory from validated evidence, not inventory assertions."""
    raw_plan = evidence.blob(PLAN_PATH)
    require(sha256(raw_plan) == PLAN_SHA256, "wrong-frozen-plan")
    plan = strict_json(raw_plan)
    texts = plan["texts"]
    require(len(texts) == CAPTURE_COUNT and len({t["id"] for t in texts}) == CAPTURE_COUNT
            and Counter(t["split"] for t in texts) == {"calibration": 272, "validation": 272},
            "wrong-clean-inventory")
    prefix = RELEASE_ROOT + "/"
    expected_captures = {prefix + "residuals/" + t["id"] + ".safetensors" for t in texts}
    actual_captures = {p for p in evidence.paths if p.startswith(prefix) and (
        p.lower().endswith(".safetensors") or p.startswith(prefix + "residuals/"))}
    require(actual_captures == expected_captures, "incomplete-or-extra-residual-inventory")
    expected_clean = {prefix + "rows/clean-" + t["id"] + ".json" for t in texts}
    require({p for p in evidence.paths if p.startswith(prefix + "rows/clean-")} == expected_clean,
            "incomplete-or-extra-clean-inventory")

    projection = evidence.json("retrieval_and_cost.json")
    keys(projection, ("scope", "freeze_commit", "plan_sha256", "pods", "artifacts"),
         "invalid-retrieval-projection")
    require(projection["freeze_commit"] == FREEZE_COMMIT and projection["plan_sha256"] == PLAN_SHA256
            and projection["scope"] == "Projection of private chained lifecycle receipts; SSH/local paths omitted.",
            "retrieval-binding-mismatch")
    keys(projection["artifacts"], ("cheap", "main"), "invalid-retrieval-artifacts")
    keys(projection["pods"], ("cheap", "main"), "invalid-retrieval-pods")
    for kind in ("cheap", "main"):
        pod = projection["pods"][kind]
        require(isinstance(pod, dict) and type(pod.get("get_status")) is int
                and pod["get_status"] == 404 and pod.get("within_limits") is True
                and isinstance(pod.get("pod_id"), str) and bool(pod["pod_id"]), "invalid-deletion-projection")
        artifacts = projection["artifacts"][kind]
        require(isinstance(artifacts, dict) and bool(artifacts), "invalid-retrieval-artifacts")
        for path, checksum in artifacts.items():
            relative_path(path)
            require(digest(checksum) and not path.startswith("cuda_qualification/"),
                    "invalid-retrieval-artifact")
            target = prefix + ("cuda_qualification/" if kind == "cheap" else "") + path
            require(evidence.record(target)["sha256"] == checksum, "retrieval-artifact-hash-mismatch")
    require(projection["pods"]["main"]["pod_id"] != projection["pods"]["cheap"]["pod_id"],
            "duplicate-retrieval-pod")
    main = projection["artifacts"]["main"]
    models = [p for p in main if re.fullmatch(r"model-bf16-load-[0-9]{5}\.json", p)]
    require(len(models) == 1, "ambiguous-model-load-evidence")
    model = evidence.json(models[0])
    require(isinstance(model, dict) and "test_only" not in model, "invalid-model-load-evidence")
    for key, expected in {
        "model_id": plan["model"]["id"], "model_revision": plan["model"]["revision"],
        "sae_id": plan["sae"]["id"], "sae_revision": plan["sae"]["revision"],
        "sae_sha256": plan["sae"]["sha256"], "precision": "bf16",
        "dtype": "torch.bfloat16", "hook": "model.layers.50.output",
    }.items():
        require(model.get(key) == expected, "model-load-binding-mismatch")
    required_main = {p.removeprefix(prefix) for p in expected_captures | expected_clean}
    required_main.update(("receipts.jsonl", "DONE-all.json", models[0]))
    require(required_main <= main.keys(), "unretrieved-residual-evidence")
    completed, tail = validate_ledger(evidence.blob(prefix + "receipts.jsonl"), plan, evidence)
    require(all(payload["path"] in main for payload in completed.values()), "unretrieved-worker-row")
    done = evidence.json("DONE-all.json")
    keys(done, ("status", "rows"), "invalid-run-completion")
    require(done["status"] == "complete" and type(done["rows"]) is int
            and done["rows"] == len(completed), "incomplete-repair-run")
    captures = []
    for item in sorted(texts, key=lambda item: item["id"]):
        row_path = "rows/clean-" + item["id"] + ".json"
        row = evidence.json(row_path)
        tokens = validate_row(row, item, plan)
        capture = evidence.record(prefix + row["capture"]["path"])
        require(capture == row["capture"], "capture-receipt-hash-size-mismatch")
        validate_capture(evidence.blob(prefix + capture["path"], MAX_CAPTURE_BYTES), tokens)
        captures.append(dict(capture, text_id=item["id"], tokens=len(tokens),
                             row=evidence.record(prefix + row_path)))
    return {
        "schema": "sae_assay_repair_residuals_v1", "release_root": RELEASE_ROOT,
        "freeze_commit": FREEZE_COMMIT, "plan": evidence.record(PLAN_PATH),
        "capture_count": CAPTURE_COUNT, "total_capture_bytes": sum(c["bytes"] for c in captures),
        "worker_receipt_tail_sha256": tail, "captures": captures,
        "evidence": [evidence.record(prefix + path) for path in sorted((
            "receipts.jsonl", "DONE-all.json", "retrieval_and_cost.json", models[0]))],
    }


def validate_manifest(evidence):
    manifest = evidence.json(MANIFEST_NAME)
    keys(manifest, ("schema", "freeze_commit", "plan_sha256", "files", "scope"),
         "invalid-residual-release-manifest")
    require(manifest["schema"] == "sae_assay_repair_release_v1"
            and manifest["freeze_commit"] == FREEZE_COMMIT and manifest["plan_sha256"] == PLAN_SHA256
            and isinstance(manifest["scope"], str) and bool(manifest["scope"])
            and isinstance(manifest["files"], list), "invalid-residual-release-manifest")
    seen = set()
    for item in manifest["files"]:
        keys(item, ("path", "bytes", "sha256"), "invalid-residual-release-entry")
        path = relative_path(item["path"])
        require(path not in seen and integer(item["bytes"]) and digest(item["sha256"]),
                "invalid-residual-release-entry")
        require(evidence.record(RELEASE_ROOT + "/" + path) == item, "residual-release-entry-mismatch")
        seen.add(path)
    actual = {p.removeprefix(RELEASE_ROOT + "/") for p in evidence.paths
              if p.startswith(RELEASE_ROOT + "/")}
    require(seen == actual - {MANIFEST_NAME}, "residual-release-manifest-coverage")


def approved_residual_paths(paths, records: Records, modes: Mapping[str, str], read: ReadBlob):
    """Return paths only after registry pin AND all indexed evidence pass."""
    approved = set()
    for root, checksum in APPROVED_RESIDUAL_INVENTORIES.items():
        require(root == RELEASE_ROOT and digest(checksum), "invalid-residual-approval-registry")
        if not any(path.startswith(root + "/") for path in paths):
            continue
        evidence = Evidence(paths, records, modes, read)
        raw = evidence.blob(root + "/" + INVENTORY_NAME)
        require(sha256(raw) == checksum, "unapproved-residual-inventory-digest")
        strict_json(raw)
        expected = inspect_release(evidence)
        require(raw == canonical(expected), "residual-inventory-content-mismatch")
        validate_manifest(evidence)
        approved.update(root + "/" + item["path"] for item in expected["captures"])
    return frozenset(approved)


def build_inventory(run: Path, plan_path: Path) -> Path:
    """Write a fresh proposal only; never modify registry, raw files or manifests."""
    run, plan_path = Path(run), Path(plan_path)
    require(run.is_dir() and not run.is_symlink() and not plan_path.is_symlink(), "invalid-builder-path")
    output = run / INVENTORY_NAME
    require(not output.exists() and not output.is_symlink()
            and not (run / MANIFEST_NAME).exists(), "inventory-must-precede-fresh-release-manifest")
    files = {PLAN_PATH: plan_path}
    for path in run.rglob("*"):
        require(not path.is_symlink(), "builder-symlink")
        if path.is_dir():
            continue
        require(path.is_file(), "builder-nonregular-file")
        files[RELEASE_ROOT + "/" + relative_path(path.relative_to(run).as_posix())] = path
    records, modes = {}, {}
    for name, path in files.items():
        mode = path.stat().st_mode
        require(stat.S_ISREG(mode) and not mode & 0o111, "builder-nonregular-file")
        hasher, size = hashlib.sha256(), 0
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                hasher.update(chunk)
                size += len(chunk)
        records[name], modes[name] = (size, hasher.hexdigest()), "100644"

    def read(name, limit):
        path = files[name]
        require(not path.is_symlink(), "builder-symlink")
        with path.open("rb") as stream:
            raw = stream.read(limit + 1)
        require(len(raw) <= limit, "residual-evidence-size-limit")
        return raw

    inventory = inspect_release(Evidence(files, records, modes, read))
    with output.open("xb") as stream:
        stream.write(canonical(inventory))
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build-inventory", action="store_true", required=True)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--plan", type=Path, required=True)
    args = parser.parse_args()
    try:
        output = build_inventory(args.run, args.plan)
    except (ResidualAuditError, OSError) as exc:
        parser.exit(1, "Inventory not created: " + (str(exc) if isinstance(exc, ResidualAuditError)
                                                   else "filesystem-error") + "\n")
    print(json.dumps({"inventory": str(output), "sha256": sha256(output.read_bytes()),
                      "authorized": False}, sort_keys=True))


if __name__ == "__main__":
    main()

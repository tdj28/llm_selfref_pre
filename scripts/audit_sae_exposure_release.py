#!/usr/bin/env python3
"""Bounded stdlib-only audit of one exposure/precision residual release.

This is a public-byte/schema/provenance check, not proof of model execution,
scientific validity or redistribution rights. The parent must review the data
and pin the complete RELEASE_MANIFEST.json digest below. This module never
creates an approval or modifies the earlier 544-state release registry.
"""
from __future__ import annotations

import re
import struct
from collections import Counter

if __package__:
    from . import audit_sae_residual_release as common
else:
    import audit_sae_residual_release as common

RELEASE_ROOT = "data/sae_assay_exposure/screen_precision_20260930"
PLAN_PATH = "data/sae_assay_exposure/plan_20260930/PLAN.json"
PLAN_SHA256 = "52797a6836f8f80d58a68071ffbcf473c61c205cc82de514c230407ddd5d49e9"
ORIGINAL_FREEZE_COMMIT = "1d7ec700ac1a91f133ac851d5e179aa8dcfa803e"
FREEZE_COMMIT = "4635849ff374d2c389f2b785e97b8c736cb02876"
A1_PLAN_PATH = "data/sae_assay_exposure/lifecycle_a1_20260930/PLAN.json"
A1_PLAN_SHA256 = "4c05c65f8fe4f22f878164be6041c20f16208887c1d91763bfa3c7698da655d9"
MANIFEST_NAME = "RELEASE_MANIFEST.json"
MANIFEST_SCHEMA = "sae_assay_exposure_release_v1"
REPORTING_SOURCES = ("scripts/release_sae_exposure.py", "scripts/report_sae_exposure.py")
MAX_TOKENS, HIDDEN_WIDTH, FEATURE_COUNT = 256, 8192, 6
MAX_HEADER_BYTES = 4096
MAX_CLEAN_BYTES = 8 + MAX_HEADER_BYTES + MAX_TOKENS * (2 * HIDDEN_WIDTH + 8)
MAX_CAPTURE_BYTES = 8 + MAX_HEADER_BYTES + MAX_TOKENS * (10 * HIDDEN_WIDTH + 24 * FEATURE_COUNT + 13)
MAX_JSON_BYTES = 32 * 1024 * 1024
MODES = ("native_zero", "precision_sham", "suppression", "amplification")
FEATURES = [30032, 58667, 22004, 30686, 41533, 23893]
MATRICES = ("native_before", "promoted_before", "promoted_after", "promoted_preact_before",
            "projection_coefficients", "native_rounded_after")
TORCH_DTYPES = {"BF16": "torch.bfloat16", "F32": "torch.float32", "I64": "torch.int64", "BOOL": "torch.bool"}

# Exact reviewed release only; a new digest requires a new publication review.
# These are bounded experimental captures, never permission for model weights.
APPROVED_RELEASE_MANIFESTS: dict[str, str] = {
    RELEASE_ROOT: "e3ed4b4461f4613383a15bc100f7c3927e840b2e167f4fc99c3343a27d203c6e",
}

ExposureAuditError = common.ResidualAuditError
require, keys, integer = common.require, common.keys, common.integer
canonical, strict_json, sha256 = common.canonical, common.strict_json, common.sha256
digest, relative_path = common.digest, common.relative_path


def capture_size_limit(path):
    """Only exact prospective capture paths get the exposure-specific limit."""
    prefix = re.escape(RELEASE_ROOT)
    if re.fullmatch(prefix + r"/precision_pilot/tensors/(?:00[0-9]|0[1-3][0-9]|04[0-7])\.safetensors", path):
        return MAX_CAPTURE_BYTES
    if re.fullmatch(prefix + r"/residuals/[A-Za-z0-9_-]+\.safetensors", path):
        return MAX_CLEAN_BYTES
    return None


def tensor_specs(n, mode=None):
    if mode is None:
        return {"hidden": ("BF16", [1, n, HIDDEN_WIDTH]), "token_ids": ("I64", [1, n])}
    require(mode in MODES, "invalid-pilot-mode")
    return {"pre": ("BF16", [1, n, HIDDEN_WIDTH]), "requested": ("F32", [1, n, HIDDEN_WIDTH]),
            "post": ("BF16" if mode == "native_zero" else "F32", [1, n, HIDDEN_WIDTH]),
            "token_ids": ("I64", [1, n]), "valid": ("BOOL", [1, n]),
            **{name: ("F32", [n, FEATURE_COUNT]) for name in MATRICES},
            "projection_scale": ("F32", [n])}


def validate_capture(raw, tokens, mask, mode=None):
    """Parse the whole bounded safetensors file, including every numeric byte."""
    require(isinstance(tokens, list) and 2 <= len(tokens) <= MAX_TOKENS
            and all(integer(t, 0, 128255) for t in tokens), "invalid-certified-tokens")
    require(isinstance(mask, list) and len(mask) == len(tokens)
            and all(type(v) is bool for v in mask) and not all(mask), "invalid-certified-mask")
    limit = MAX_CLEAN_BYTES if mode is None else MAX_CAPTURE_BYTES
    require(isinstance(raw, bytes) and 8 <= len(raw) <= limit, "exposure-capture-size-limit")
    header_size = struct.unpack_from("<Q", raw)[0]
    require(0 < header_size <= MAX_HEADER_BYTES and header_size % 8 == 0
            and 8 + header_size <= len(raw), "invalid-capture-header-size")
    header_raw = raw[8:8 + header_size]
    require(header_raw.startswith(b"{") and header_raw.rstrip(b" ").endswith(b"}"), "invalid-header-padding")
    header = strict_json(header_raw)
    specs = tensor_specs(len(tokens), mode)
    keys(header, {*specs, *(["__metadata__"] if mode else [])}, "unexpected-capture-tensors")
    if mode:
        require(header["__metadata__"] == {"schema": "sae_precision_pilot_v1"}, "invalid-pilot-metadata")
    payload = memoryview(raw)[8 + header_size:]
    views, ranges = {}, []
    for name, (dtype, shape) in specs.items():
        entry = header[name]
        keys(entry, ("dtype", "shape", "data_offsets"), "invalid-tensor-descriptor")
        require(entry["dtype"] == dtype and isinstance(entry["shape"], list)
                and all(integer(d, 1) for d in entry["shape"]) and entry["shape"] == shape,
                "invalid-capture-dtype-shape")
        size = {"BF16": 2, "F32": 4, "I64": 8, "BOOL": 1}[dtype]
        for dimension in shape:
            size *= dimension
        offsets = entry["data_offsets"]
        require(isinstance(offsets, list) and len(offsets) == 2 and all(integer(x) for x in offsets)
                and offsets[1] - offsets[0] == size and offsets[1] <= len(payload), "invalid-capture-offsets")
        ranges.append(tuple(offsets))
        view = views[name] = payload[offsets[0]:offsets[1]]
        if dtype == "BF16":
            require(all((v & 0x7f80) != 0x7f80 for (v,) in struct.iter_unpack("<H", view)), "nonfinite-capture")
        elif dtype == "F32":
            require(all((v & 0x7f800000) != 0x7f800000 for (v,) in struct.iter_unpack("<I", view)), "nonfinite-capture")
        elif dtype == "BOOL":
            require(all(v in (0, 1) for v in view), "invalid-bool-capture")
    cursor = 0
    for start, end in sorted(ranges):
        require(start == cursor, "capture-overlap-or-gap")
        cursor = end
    require(cursor == len(payload), "capture-trailing-data")
    require([v for (v,) in struct.iter_unpack("<q", views["token_ids"])] == tokens, "capture-token-mismatch")
    if mode:
        require(list(views["valid"]) == [int(not special) for special in mask], "capture-mask-mismatch")
    return views


class Evidence:
    def __init__(self, paths, records, modes, read):
        self.paths, self.records, self.modes, self.read = set(paths), records, modes, read

    def record(self, path):
        relative_path(path)
        require(path in self.paths and path in self.records and self.modes.get(path) == "100644",
                "missing-or-nonregular-exposure-evidence")
        size, checksum = self.records[path]
        require(integer(size) and digest(checksum), "invalid-exposure-record")
        return {"path": path.removeprefix(RELEASE_ROOT + "/"), "bytes": size, "sha256": checksum}

    def blob(self, path, limit=MAX_JSON_BYTES):
        record = self.record(path)
        require(record["bytes"] <= limit, "exposure-evidence-size-limit")
        raw = self.read(path, limit)
        require(len(raw) == record["bytes"] and sha256(raw) == record["sha256"], "exposure-evidence-hash-mismatch")
        return raw

    def json(self, relative):
        return strict_json(self.blob(RELEASE_ROOT + "/" + relative))


def validate_manifest(evidence):
    manifest = evidence.json(MANIFEST_NAME)
    keys(manifest, ("schema", "freeze_commit", "plan_path", "plan_sha256", "files", "scope",
                    "status", "reporting_source_hashes", "raw_safetensors_public_approval"),
         "invalid-exposure-manifest")
    require(manifest["schema"] == MANIFEST_SCHEMA and manifest["plan_path"] == PLAN_PATH
            and manifest["plan_sha256"] == PLAN_SHA256
            and manifest["freeze_commit"] == FREEZE_COMMIT
            and manifest["status"] == "complete"
            and manifest["raw_safetensors_public_approval"] == "separate_bounded_capture_audit_required"
            and isinstance(manifest["scope"], str) and bool(manifest["scope"])
            and isinstance(manifest["files"], list), "invalid-exposure-manifest-binding")
    keys(manifest["reporting_source_hashes"], REPORTING_SOURCES, "invalid-reporting-source-inventory")
    for path, checksum in manifest["reporting_source_hashes"].items():
        require(digest(checksum) and evidence.record(path)["sha256"] == checksum,
                "exposure-reporting-source-mismatch")
    seen = set()
    for item in manifest["files"]:
        keys(item, ("path", "bytes", "sha256"), "invalid-exposure-manifest-entry")
        name = relative_path(item["path"])
        require(name not in seen and integer(item["bytes"]) and digest(item["sha256"]), "duplicate-or-invalid-manifest-entry")
        require(evidence.record(RELEASE_ROOT + "/" + name) == item, "exposure-manifest-file-mismatch")
        seen.add(name)
    actual = {p.removeprefix(RELEASE_ROOT + "/") for p in evidence.paths if p.startswith(RELEASE_ROOT + "/")}
    require(seen == actual - {MANIFEST_NAME}, "exposure-manifest-coverage")
    return manifest


def validate_plan(evidence):
    raw = evidence.blob(PLAN_PATH)
    require(sha256(raw) == PLAN_SHA256, "wrong-exposure-plan")
    plan = strict_json(raw)
    require(raw == canonical(plan) and plan["schema"] == "sae_exposure_v1"
            and plan["target_feature_ids"] == FEATURES and plan["model"]["precision"] == "bf16",
            "invalid-exposure-plan")
    for group in ("source_hashes", "input_hashes"):
        require(isinstance(plan[group], dict) and bool(plan[group]), "missing-plan-provenance")
        for path, checksum in plan[group].items():
            relative_path(path)
            require(digest(checksum) and evidence.record(path)["sha256"] == checksum, "exposure-plan-provenance-mismatch")
    texts, items = plan["texts"], plan["certificate"]["items"]
    require(len(texts) == 224 and len(items) == 224
            and len({t["id"] for t in texts}) == 224 and len({t["id"] for t in items}) == 224
            and Counter(t["split"] for t in texts) == {"discovery": 96, "validation": 96, "representative": 32},
            "invalid-exposure-plan-inventory")
    certificate = {item["id"]: item for item in items}
    require(set(certificate) == {item["id"] for item in texts}, "certificate-inventory-mismatch")
    families, pilot = set(), []
    for item in texts:
        require(isinstance(item["id"], str) and re.fullmatch(r"[A-Za-z0-9_-]+", item["id"]), "unsafe-text-id")
        cert = certificate[item["id"]]
        require(cert["text_sha256"] == sha256(item["text"].encode("utf-8")), "certificate-text-mismatch")
        if item["split"] == "discovery" and item["family"] not in families:
            families.add(item["family"])
            pilot.append(item)
    require(len(pilot) == 12 and plan["precision_pilot"]["texts"] == pilot
            and plan["precision_pilot"]["modes"] == list(MODES), "invalid-pilot-plan-inventory")
    return plan, certificate, pilot


def validate_lifecycle_plan(evidence):
    """Authenticate A1 and its cost/failure provenance without importing runtime."""
    raw = evidence.blob(A1_PLAN_PATH)
    require(sha256(raw) == A1_PLAN_SHA256, "wrong-exposure-lifecycle-plan")
    amendment = strict_json(raw)
    require(raw == canonical(amendment) and amendment.get("schema") == "sae_exposure_lifecycle_a1_v1"
            and amendment.get("original_plan") == {"path": PLAN_PATH, "sha256": PLAN_SHA256,
                                                    "freeze_commit": ORIGINAL_FREEZE_COMMIT},
            "invalid-exposure-lifecycle-binding")
    # The entire pinned digest includes the exact failed cost and reduced cap.
    # Recheck indexed bytes for all five A1 sources and seven failure artifacts.
    for group in ("source_hashes", "input_hashes"):
        require(isinstance(amendment.get(group), dict) and bool(amendment[group]),
                "missing-exposure-lifecycle-provenance")
        for path, checksum in amendment[group].items():
            relative_path(path)
            require(digest(checksum) and evidence.record(path)["sha256"] == checksum,
                    "exposure-lifecycle-provenance-mismatch")
    return amendment


def bound_row(row, item, cert, freeze):
    require(row.get("plan_sha256") == PLAN_SHA256 and row.get("freeze_commit") == freeze
            and row.get("text_id") == item["id"] and row.get("feature_ids") == FEATURES
            and row.get("token_ids") == cert["token_ids"]
            and row.get("special_tokens_mask") == cert["special_tokens_mask"]
            and row.get("family") == item["family"] and row.get("split") == item["split"], "exposure-row-binding-mismatch")
    # Equality alone accepts bools as integers, so validate JSON scalar types too.
    require(all(type(t) is int for t in row["token_ids"])
            and all(type(v) is bool for v in row["special_tokens_mask"]), "invalid-row-token-types")


def validate_ledger(evidence, relative, expected, freeze, pilot=False):
    raw = evidence.blob(RELEASE_ROOT + "/" + relative)
    require(raw.endswith(b"\n"), "truncated-exposure-ledger")
    previous, seen, dispatched, completed = None, set(), [], {}
    for seq, line in enumerate(raw.splitlines(keepends=True)):
        event = strict_json(line)
        keys(event, ("id", "seq", "data", "plan_sha256", "freeze_commit", "previous_sha256", "sha256"), "invalid-exposure-event")
        body = {k: v for k, v in event.items() if k != "sha256"}
        require(canonical(event) == line and type(event["seq"]) is int and event["seq"] == seq
                and event["previous_sha256"] == previous and event["sha256"] == sha256(canonical(body)[:-1])
                and event["plan_sha256"] == PLAN_SHA256 and event["freeze_commit"] == freeze
                and isinstance(event["id"], str) and event["id"] not in seen, "exposure-ledger-chain-mismatch")
        data = event["data"]
        require(isinstance(data, dict), "invalid-exposure-event-data")
        if seq == 0:
            require(event["id"] == "binding" and data == {"kind": "binding", "row_ids": sorted(expected)}, "exposure-ledger-inventory-mismatch")
        if data.get("kind") in {"row", "dispatch"}:
            rid = data.get("row_id")
            require(isinstance(rid, str) and rid in expected and event["id"] == data["kind"] + ":" + rid, "unknown-exposure-receipt")
            if data["kind"] == "dispatch":
                require(rid not in dispatched, "duplicate-exposure-dispatch")
                dispatched.append(rid)
            else:
                require(rid in dispatched and rid not in completed, "unbound-exposure-receipt")
                payload = data["payload"]
                keys(payload, ("path", "sha256", "capture_sha256") if pilot else ("path", "sha256"), "invalid-exposure-row-receipt")
                relative_path(payload["path"])
                require(payload["path"] == expected[rid], "exposure-receipt-path-mismatch")
                full = ("precision_pilot/" if pilot else "") + payload["path"]
                require(evidence.record(RELEASE_ROOT + "/" + full)["sha256"] == payload["sha256"], "exposure-receipt-hash-mismatch")
                completed[rid] = payload
        previous = event["sha256"]
        seen.add(event["id"])
    require(dispatched == list(expected) and set(completed) == set(expected) and "runtime" in seen, "incomplete-exposure-ledger")
    if pilot:
        require(event["id"] == "complete" and data.get("full_model_forwards") == 48
                and data.get("summary_sha256") == evidence.record(RELEASE_ROOT + "/precision_pilot/summary.json")["sha256"],
                "incomplete-pilot-ledger")
    return completed


def inspect_release(evidence):
    manifest = validate_manifest(evidence)
    plan, certificate, pilot = validate_plan(evidence)
    validate_lifecycle_plan(evidence)
    freeze, prefix = manifest["freeze_commit"], RELEASE_ROOT + "/"
    expected = {"qualification-live": "rows/qualification-live.json"}
    expected.update({"clean-" + item["id"]: "rows/clean-" + item["id"] + ".json" for item in plan["texts"]})
    validate_ledger(evidence, "receipts.jsonl", expected, freeze)
    q = evidence.json("rows/qualification-live.json")
    require(q.get("pass") is True and q.get("plan_sha256") == PLAN_SHA256 and q.get("freeze_commit") == freeze,
            "invalid-exposure-qualification")
    captures, clean = set(), {}
    for item in plan["texts"]:
        cert, name = certificate[item["id"]], "residuals/" + item["id"] + ".safetensors"
        row = evidence.json(expected["clean-" + item["id"]])
        bound_row(row, item, cert, freeze)
        require(row.get("schema") == "sae_assay_exposure_row_v1" and row.get("id") == "clean-" + item["id"]
                and row.get("encoding_authority") == "full_native_token1_v1"
                and row.get("text_sha256") == cert["text_sha256"], "invalid-clean-row-schema")
        require(row["capture"] == evidence.record(prefix + name), "clean-capture-receipt-mismatch")
        views = validate_capture(evidence.blob(prefix + name, MAX_CLEAN_BYTES), cert["token_ids"], cert["special_tokens_mask"])
        clean[item["id"]] = (sha256(views["hidden"]), row, evidence.record(prefix + expected["clean-" + item["id"]]))
        captures.add(prefix + name)
    pilot_rows = {"precision-pilot:" + item["id"] + ":" + mode: f"rows/{i * 4 + j:03d}.json"
                  for i, item in enumerate(pilot) for j, mode in enumerate(MODES)}
    receipts = validate_ledger(evidence, "precision_pilot/receipts.jsonl", pilot_rows, freeze, pilot=True)
    for i, item in enumerate(pilot):
        cert, (hidden_hash, clean_row, clean_record) = certificate[item["id"]], clean[item["id"]]
        for j, mode in enumerate(MODES):
            rid, ordinal = "precision-pilot:" + item["id"] + ":" + mode, i * 4 + j
            row = evidence.json("precision_pilot/" + pilot_rows[rid])
            bound_row(row, item, cert, freeze)
            require(row.get("schema") == "sae_precision_pilot_v1" and row.get("row_id") == rid
                    and row.get("mode") == mode and row.get("test_only") is False
                    and row.get("sae_full_width") == 65536, "invalid-pilot-row-schema")
            cap = row["capture"]
            keys(cap, ("path", "sha256", "tensors"), "invalid-pilot-capture-receipt")
            name = f"precision_pilot/tensors/{ordinal:03d}.safetensors"
            require(cap["path"] == f"tensors/{ordinal:03d}.safetensors"
                    and cap["sha256"] == evidence.record(prefix + name)["sha256"] == receipts[rid]["capture_sha256"],
                    "pilot-capture-binding-mismatch")
            specs = tensor_specs(len(cert["token_ids"]), mode)
            require(cap["tensors"] == {k: {"dtype": TORCH_DTYPES[d], "shape": shape} for k, (d, shape) in specs.items()},
                    "pilot-capture-metadata-mismatch")
            views = validate_capture(evidence.blob(prefix + name, MAX_CAPTURE_BYTES), cert["token_ids"], cert["special_tokens_mask"], mode)
            require(sha256(views["pre"]) == hidden_hash, "pilot-pre-is-not-clean-exposure")
            require(row["clean_exposure"] == {"row_path": clean_record["path"], "row_sha256": clean_record["sha256"],
                    "capture_path": clean_row["capture"]["path"], "capture_sha256": clean_row["capture"]["sha256"]}, "pilot-clean-reference-mismatch")
            for key in ("native_before", "promoted_before", "promoted_after", "native_rounded_after"):
                actual = [v for (v,) in struct.iter_unpack("<f", views[key])]
                matrix = row[key]
                require(isinstance(matrix, list) and len(matrix) == len(cert["token_ids"])
                        and all(isinstance(r, list) and len(r) == FEATURE_COUNT for r in matrix)
                        and all(type(v) in (int, float) for r in matrix for v in r)
                        and actual == [v for r in matrix for v in r], "pilot-readout-row-mismatch")
            native = [[clean_row["activations"][str(f)][t] for f in FEATURES] for t in range(len(cert["token_ids"]))]
            require(row["native_before"] == native, "pilot-native-readout-mismatch")
            captures.add(prefix + name)
    actual = {p for p in evidence.paths if p.startswith(prefix) and p.lower().endswith(".safetensors")}
    require(actual == captures and len(captures) == 272, "incomplete-or-extra-exposure-captures")
    require({p for p in evidence.paths if p.startswith(prefix + "rows/")} == {prefix + p for p in expected.values()}, "extra-or-missing-clean-rows")
    require({p for p in evidence.paths if p.startswith(prefix + "precision_pilot/rows/")} == {prefix + "precision_pilot/" + p for p in pilot_rows.values()}, "extra-or-missing-pilot-rows")
    done = evidence.json("DONE-all.json")
    require(done.get("status") == "complete" and done.get("rows") == 225 and done.get("exposure_rows") == 224
            and done.get("plan_sha256") == PLAN_SHA256 and done.get("freeze_commit") == freeze
            and done.get("precision_pilot", {}).get("status") == "complete", "incomplete-exposure-run")
    return frozenset(captures)


def approved_residual_paths(paths, records, modes, read):
    """Authorize no bytes until the exact entire manifest was explicitly reviewed."""
    require(all(root == RELEASE_ROOT and digest(value) for root, value in APPROVED_RELEASE_MANIFESTS.items()), "invalid-exposure-approval-registry")
    if not any(p.startswith(RELEASE_ROOT + "/") for p in paths):
        return frozenset()
    checksum = APPROVED_RELEASE_MANIFESTS.get(RELEASE_ROOT)
    require(digest(checksum), "exposure-release-not-reviewed")
    evidence = Evidence(paths, records, modes, read)
    require(sha256(evidence.blob(RELEASE_ROOT + "/" + MANIFEST_NAME)) == checksum, "unapproved-exposure-manifest-digest")
    return inspect_release(evidence)

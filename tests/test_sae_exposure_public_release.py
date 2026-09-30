"""Stdlib-only security fixtures; no real captures or release approvals."""
from copy import deepcopy
import json
from pathlib import Path
import struct
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from scripts import audit_public_release as public
from scripts import audit_sae_exposure_release as audit
from scripts import audit_sae_residual_release as historical

PREFIX = audit.RELEASE_ROOT + "/"
FREEZE = audit.FREEZE_COMMIT
TOKENS, MASK = [128000, 42], [True, False]


def pack(header, payload):
    raw = json.dumps(header, separators=(",", ":")).encode()
    raw += b" " * (-len(raw) % 8)
    return struct.pack("<Q", len(raw)) + raw + payload


def capture(mode=None, tokens=TOKENS, mask=MASK):
    header, chunks, offset = {}, [], 0
    if mode:
        header["__metadata__"] = {"schema": "sae_precision_pilot_v1"}
    for name, (dtype, shape) in audit.tensor_specs(len(tokens), mode).items():
        size = 1
        for dimension in shape:
            size *= dimension
        if name == "token_ids":
            raw = struct.pack("<" + "q" * len(tokens), *tokens)
        elif name == "valid":
            raw = bytes(int(not value) for value in mask)
        else:
            raw = bytes(size * {"BF16": 2, "F32": 4}[dtype])
        header[name] = {"dtype": dtype, "shape": shape, "data_offsets": [offset, offset + len(raw)]}
        chunks.append(raw)
        offset += len(raw)
    return pack(header, b"".join(chunks))


def modify_header(raw, change):
    n = struct.unpack_from("<Q", raw)[0]
    header = json.loads(raw[8:8 + n])
    change(header)
    return pack(header, raw[8 + n:])


def modify_tensor(raw, name, data):
    n = struct.unpack_from("<Q", raw)[0]
    header = json.loads(raw[8:8 + n])
    start, end = header[name]["data_offsets"]
    payload = bytearray(raw[8 + n:])
    payload[start:start + len(data)] = data
    return pack(header, payload)


def evidence(files, modes=None):
    records = {name: (len(raw), audit.sha256(raw)) for name, raw in files.items()}
    permissions = {name: "100644" for name in files}
    permissions.update(modes or {})
    def read(name, limit):
        assert len(files[name]) <= limit
        return files[name]
    return audit.Evidence(files, records, permissions, read)


def fixture():
    texts = [{"id": f"text-{i:03d}", "text": f"Synthetic fixture {i}.",
              "family": f"family-{i % 12:02d}", "category": "fixture",
              "split": "discovery" if i < 96 else "validation" if i < 192 else "representative"}
             for i in range(224)]
    files = {"experiments/synthetic-source.py": b"# synthetic source\n", "data/synthetic-input.json": b"{}\n"}
    files.update({path: b"# synthetic reporting source\n" for path in audit.REPORTING_SOURCES})
    plan = {"schema": "sae_exposure_v1", "model": {"precision": "bf16"},
            "texts": texts, "target_feature_ids": audit.FEATURES,
            "precision_pilot": {"texts": texts[:12], "modes": list(audit.MODES)},
            "certificate": {"items": [{"id": item["id"], "text_sha256": audit.sha256(item["text"].encode()),
                "token_ids": TOKENS, "special_tokens_mask": MASK} for item in texts]},
            "source_hashes": {"experiments/synthetic-source.py": audit.sha256(files["experiments/synthetic-source.py"])},
            "input_hashes": {"data/synthetic-input.json": audit.sha256(files["data/synthetic-input.json"])}}
    files[audit.PLAN_PATH] = audit.canonical(plan)
    plan_hash = audit.sha256(files[audit.PLAN_PATH])
    raw = capture()
    for item in texts:
        name = "residuals/" + item["id"] + ".safetensors"
        row = {"schema": "sae_assay_exposure_row_v1", "id": "clean-" + item["id"], "text_id": item["id"],
               "family": item["family"], "split": item["split"], "feature_ids": audit.FEATURES,
               "token_ids": TOKENS, "special_tokens_mask": MASK, "plan_sha256": plan_hash,
               "freeze_commit": FREEZE, "encoding_authority": "full_native_token1_v1",
               "text_sha256": audit.sha256(item["text"].encode()),
               "activations": {str(f): [0., 0.] for f in audit.FEATURES},
               "capture": {"path": name, "bytes": len(raw), "sha256": audit.sha256(raw)}}
        files[PREFIX + name] = raw
        files[PREFIX + "rows/" + row["id"] + ".json"] = audit.canonical(row)
    files[PREFIX + "rows/qualification-live.json"] = audit.canonical({"pass": True,
        "plan_sha256": plan_hash, "freeze_commit": FREEZE})
    for i, item in enumerate(texts[:12]):
        clean_path = "rows/clean-" + item["id"] + ".json"
        clean = json.loads(files[PREFIX + clean_path])
        for j, mode in enumerate(audit.MODES):
            ordinal, raw = i * 4 + j, capture(mode)
            cap_path = f"tensors/{ordinal:03d}.safetensors"
            row = {"schema": "sae_precision_pilot_v1", "row_id": "precision-pilot:" + item["id"] + ":" + mode,
                "text_id": item["id"], "family": item["family"], "split": item["split"], "mode": mode,
                "feature_ids": audit.FEATURES, "token_ids": TOKENS, "special_tokens_mask": MASK,
                "plan_sha256": plan_hash, "freeze_commit": FREEZE, "test_only": False, "sae_full_width": 65536,
                **{k: [[0.] * 6, [0.] * 6] for k in ("native_before", "promoted_before", "promoted_after", "native_rounded_after")},
                "capture": {"path": cap_path, "sha256": audit.sha256(raw), "tensors": {
                    k: {"shape": shape, "dtype": audit.TORCH_DTYPES[dtype]}
                    for k, (dtype, shape) in audit.tensor_specs(2, mode).items()}},
                "clean_exposure": {"row_path": clean_path, "row_sha256": audit.sha256(files[PREFIX + clean_path]),
                    "capture_path": clean["capture"]["path"], "capture_sha256": clean["capture"]["sha256"]}}
            files[PREFIX + "precision_pilot/" + cap_path] = raw
            files[PREFIX + f"precision_pilot/rows/{ordinal:03d}.json"] = audit.canonical(row)
    files[PREFIX + "precision_pilot/summary.json"] = b'{"synthetic":true}\n'
    files[PREFIX + "DONE-all.json"] = audit.canonical({"status": "complete", "rows": 225, "exposure_rows": 224,
        "plan_sha256": plan_hash, "freeze_commit": FREEZE, "precision_pilot": {"status": "complete"}})
    refresh_ledgers(files, plan, plan_hash)
    seal(files, plan_hash)
    return files, plan, plan_hash


def refresh_ledgers(files, plan, plan_hash):
    for pilot in (False, True):
        pairs = [("qualification-live", "rows/qualification-live.json")]
        pairs += [("clean-" + t["id"], "rows/clean-" + t["id"] + ".json") for t in plan["texts"]]
        if pilot:
            pairs = [("precision-pilot:" + t["id"] + ":" + mode, f"rows/{i * 4 + j:03d}.json")
                     for i, t in enumerate(plan["precision_pilot"]["texts"]) for j, mode in enumerate(audit.MODES)]
        prefix = PREFIX + ("precision_pilot/" if pilot else "")
        events = []
        def append(identifier, data):
            event = {"id": identifier, "seq": len(events), "data": data,
                "plan_sha256": plan_hash, "freeze_commit": FREEZE,
                "previous_sha256": events[-1]["sha256"] if events else None}
            event["sha256"] = audit.sha256(audit.canonical(event)[:-1])
            events.append(event)
        append("binding", {"kind": "binding", "row_ids": sorted(rid for rid, _ in pairs)})
        append("runtime", {"kind": "runtime"})
        for rid, path in pairs:
            append("dispatch:" + rid, {"kind": "dispatch", "row_id": rid})
            payload = {"path": path, "sha256": audit.sha256(files[prefix + path])}
            if pilot:
                payload["capture_sha256"] = json.loads(files[prefix + path])["capture"]["sha256"]
            append("row:" + rid, {"kind": "row", "row_id": rid, "payload": payload})
        if pilot:
            append("complete", {"kind": "complete", "full_model_forwards": 48,
                               "summary_sha256": audit.sha256(files[prefix + "summary.json"])})
        files[prefix + "receipts.jsonl"] = b"".join(audit.canonical(e) for e in events)


def seal(files, plan_hash):
    files[PREFIX + audit.MANIFEST_NAME] = audit.canonical({"schema": audit.MANIFEST_SCHEMA,
        "freeze_commit": FREEZE, "plan_path": audit.PLAN_PATH, "plan_sha256": plan_hash,
        "status": "complete", "raw_safetensors_public_approval": "separate_bounded_capture_audit_required",
        "reporting_source_hashes": {path: audit.sha256(files[path]) for path in audit.REPORTING_SOURCES},
        "scope": "Synthetic release security test only.",
        "files": [{"path": name[len(PREFIX):], "bytes": len(raw), "sha256": audit.sha256(raw)}
                  for name, raw in sorted(files.items()) if name.startswith(PREFIX)
                  and name != PREFIX + audit.MANIFEST_NAME]})


class CaptureTests(unittest.TestCase):
    def test_complete_dtype_shape_and_metadata_contract(self):
        for mode in (None, *audit.MODES):
            views = audit.validate_capture(capture(mode), TOKENS, MASK, mode)
            self.assertEqual(set(views), set(audit.tensor_specs(2, mode)))

    def test_maximum_payload_is_bounded_below_21_mib(self):
        tokens, mask = [42] * 256, [False] * 256
        raw = capture("amplification", tokens, mask)
        self.assertLessEqual(len(raw), audit.MAX_CAPTURE_BYTES)
        self.assertLess(audit.MAX_CAPTURE_BYTES, 21 * 1024 * 1024)
        audit.validate_capture(raw, tokens, mask, "amplification")
        with self.assertRaises(audit.ExposureAuditError):
            audit.validate_capture(raw, tokens + [42], mask + [False], "amplification")

    def test_nan_infinity_bool_tokens_and_mask_rejected(self):
        raw = capture("suppression")
        changes = [("pre", struct.pack("<H", 0x7fc0)), ("requested", struct.pack("<I", 0x7f800000)),
                   ("post", struct.pack("<I", 0xff800000)), ("native_before", struct.pack("<I", 0x7fc00000)),
                   ("valid", b"\x02"), ("token_ids", struct.pack("<q", 42))]
        for name, data in changes:
            with self.subTest(name=name), self.assertRaises(audit.ExposureAuditError):
                audit.validate_capture(modify_tensor(raw, name, data), TOKENS, MASK, "suppression")
        for tokens, mask in (([True, 42], MASK), (TOKENS, [0, False]), (TOKENS, [False, True])):
            with self.assertRaises(audit.ExposureAuditError):
                audit.validate_capture(raw, tokens, mask, "suppression")

    def test_unknown_tensors_dimensions_offsets_dtype_and_trailing_bytes_rejected(self):
        raw = capture("precision_sham")
        changes = [lambda h: h.update(weights=h["pre"]),
                   lambda h: h["pre"].update(dtype="F32"),
                   lambda h: h["post"].update(dtype="BF16"),
                   lambda h: h["requested"].update(shape=[8192, 8192]),
                   lambda h: h["native_before"].update(shape=[2, 7]),
                   lambda h: h["valid"].update(data_offsets=[0, 2]),
                   lambda h: h["__metadata__"].update(arbitrary="unreviewed")]
        for change in changes:
            with self.subTest(change=change), self.assertRaises(audit.ExposureAuditError):
                audit.validate_capture(modify_header(raw, change), TOKENS, MASK, "precision_sham")
        with self.assertRaises(audit.ExposureAuditError):
            audit.validate_capture(raw + b"payload", TOKENS, MASK, "precision_sham")
        with self.assertRaises(audit.ExposureAuditError):
            audit.validate_capture(struct.pack("<Q", 10**15), TOKENS, MASK)


class ReleaseFixture(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base, cls.plan, cls.plan_hash = fixture()

    def setUp(self):
        self.pin = patch.object(audit, "PLAN_SHA256", self.plan_hash)
        self.pin.start()
        self.addCleanup(self.pin.stop)

    def approve(self, files, modes=None, checksum=None):
        ev = evidence(files, modes)
        checksum = checksum or audit.sha256(files[PREFIX + audit.MANIFEST_NAME])
        with patch.dict(audit.APPROVED_RELEASE_MANIFESTS, {audit.RELEASE_ROOT: checksum}, clear=True):
            return audit.approved_residual_paths(files, ev.records, ev.modes, ev.read)


class ReleaseTests(ReleaseFixture):
    def test_empty_registry_does_not_self_approve_and_complete_fixture_validates(self):
        self.assertEqual(audit.APPROVED_RELEASE_MANIFESTS, {})
        ev = evidence(self.base)
        with self.assertRaisesRegex(audit.ExposureAuditError, "not-reviewed"):
            audit.approved_residual_paths(self.base, ev.records, ev.modes, ev.read)
        approved = self.approve(self.base)
        self.assertEqual(len(approved), 272)
        self.assertTrue(all(name.startswith(PREFIX) for name in approved))
        self.assertEqual(audit.APPROVED_RELEASE_MANIFESTS, {})

    def test_entire_manifest_not_just_capture_inventory_is_pinned(self):
        files = dict(self.base)
        old_pin = audit.sha256(files[PREFIX + audit.MANIFEST_NAME])
        files[PREFIX + "extra.safetensors"] = capture()
        seal(files, self.plan_hash)
        with self.assertRaisesRegex(audit.ExposureAuditError, "unapproved-exposure-manifest"):
            self.approve(files, checksum=old_pin)
        with self.assertRaisesRegex(audit.ExposureAuditError, "extra-exposure-captures"):
            self.approve(files)

    def test_manifest_coverage_and_source_binding_reject_self_consistent_substitutions(self):
        files = dict(self.base)
        files[PREFIX + "unmanifested.txt"] = b"extra"
        with self.assertRaisesRegex(audit.ExposureAuditError, "coverage"):
            self.approve(files)
        files = dict(self.base)
        files["experiments/synthetic-source.py"] = b"changed source\n"
        with self.assertRaisesRegex(audit.ExposureAuditError, "provenance"):
            self.approve(files)
        files = dict(self.base)
        plan = deepcopy(self.plan)
        plan["model"]["precision"] = "nf4"
        files[audit.PLAN_PATH] = audit.canonical(plan)
        with self.assertRaisesRegex(audit.ExposureAuditError, "wrong-exposure-plan"):
            self.approve(files)

    def test_manifest_freeze_status_approval_marker_and_reporting_sources_are_bound(self):
        name = PREFIX + audit.MANIFEST_NAME
        changes = [lambda m: m.update(freeze_commit="b" * 40),
                   lambda m: m.update(status="incomplete"),
                   lambda m: m.update(raw_safetensors_public_approval="approved"),
                   lambda m: m["reporting_source_hashes"].update({"unrelated.py": "a" * 64}),
                   lambda m: m["reporting_source_hashes"].update({audit.REPORTING_SOURCES[0]: "a" * 64})]
        for change in changes:
            files = dict(self.base)
            manifest = json.loads(files[name])
            change(manifest)
            files[name] = audit.canonical(manifest)
            with self.subTest(change=change), self.assertRaises(audit.ExposureAuditError):
                self.approve(files)
        files = dict(self.base)
        files[audit.REPORTING_SOURCES[0]] = b"changed reporting source\n"
        with self.assertRaisesRegex(audit.ExposureAuditError, "reporting-source-mismatch"):
            self.approve(files)

    def test_row_token_freeze_and_tensor_metadata_bindings(self):
        name = PREFIX + "precision_pilot/rows/001.json"
        changes = [lambda row: row.update(freeze_commit="c" * 40),
                   lambda row: row.update(token_ids=[128000, 43]),
                   lambda row: row.update(test_only=True),
                   lambda row: row["capture"]["tensors"]["requested"].update(dtype="torch.bfloat16"),
                   lambda row: row["clean_exposure"].update(capture_sha256="f" * 64),
                   lambda row: row["promoted_after"][0].__setitem__(0, 10)]
        for change in changes:
            files = dict(self.base)
            row = json.loads(files[name])
            change(row)
            files[name] = audit.canonical(row)
            refresh_ledgers(files, self.plan, self.plan_hash)
            seal(files, self.plan_hash)
            with self.subTest(change=change), self.assertRaises(audit.ExposureAuditError):
                self.approve(files)

    def test_mode_dtype_pre_state_and_extra_payload_fail_after_rehash(self):
        for mutation in (lambda raw: modify_tensor(raw, "pre", b"\x80\x3f"),
                         lambda raw: modify_header(raw, lambda h: h["post"].update(dtype="BF16")),
                         lambda raw: raw + b"unreviewed suffix"):
            files = dict(self.base)
            cap = PREFIX + "precision_pilot/tensors/001.safetensors"
            row_path = PREFIX + "precision_pilot/rows/001.json"
            files[cap] = mutation(files[cap])
            row = json.loads(files[row_path])
            row["capture"]["sha256"] = audit.sha256(files[cap])
            files[row_path] = audit.canonical(row)
            refresh_ledgers(files, self.plan, self.plan_hash)
            seal(files, self.plan_hash)
            with self.assertRaises(audit.ExposureAuditError):
                self.approve(files)

    def test_nonregular_modes_and_broken_ledger_cannot_authorize(self):
        cap = PREFIX + "precision_pilot/tensors/000.safetensors"
        for mode in ("100755", "120000", "160000"):
            with self.subTest(mode=mode), self.assertRaises(audit.ExposureAuditError):
                self.approve(self.base, {cap: mode})
        files = dict(self.base)
        files[PREFIX + "receipts.jsonl"] = files[PREFIX + "receipts.jsonl"].rstrip(b"\n")
        seal(files, self.plan_hash)
        with self.assertRaisesRegex(audit.ExposureAuditError, "truncated"):
            self.approve(files)

    def test_size_exception_is_exact_root_and_path_only(self):
        self.assertEqual(audit.capture_size_limit(PREFIX + "precision_pilot/tensors/047.safetensors"), audit.MAX_CAPTURE_BYTES)
        for name in ("048", "999", "../000", "000/weights"):
            self.assertIsNone(audit.capture_size_limit(PREFIX + "precision_pilot/tensors/" + name + ".safetensors"))
        self.assertIsNone(audit.capture_size_limit("elsewhere/precision_pilot/tensors/000.safetensors"))
        self.assertIsNone(audit.capture_size_limit(PREFIX + "weights.safetensors"))
        self.assertEqual(audit.approved_residual_paths([], {}, {}, lambda *_: b""), frozenset())


class GitIntegrationTests(ReleaseFixture):
    def test_index_bytes_only_empty_registry_and_outside_weights_remain_blocked(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            def git(*args):
                return subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)
            git("init", "-q")
            for name, raw in self.base.items():
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(raw)
            for name in public.REQUIRED_PUBLIC_FILES:
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("" if name == ".gitignore" else "Synthetic fixture.\n")
            git("add", ".")
            report = public.audit_repository(root)
            self.assertEqual(report["residual_captures_verified"], 0)
            pin = {audit.RELEASE_ROOT: audit.sha256(self.base[PREFIX + audit.MANIFEST_NAME])}
            with patch.dict(audit.APPROVED_RELEASE_MANIFESTS, pin, clear=True):
                report = public.audit_repository(root)
                self.assertEqual(report["findings"], [])
                self.assertEqual(report["residual_captures_verified"], 272)
                name = PREFIX + "precision_pilot/tensors/000.safetensors"
                (root / name).write_bytes(b"unstaged corruption")
                self.assertEqual(public.audit_repository(root)["status"], "pass")
                git("add", name)
                self.assertEqual(public.audit_repository(root)["residual_captures_verified"], 0)

    def test_preflight_never_materializes_oversized_blob_and_larger_cap_does_not_escape_root(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            names = {PREFIX + "precision_pilot/tensors/001.safetensors": historical.MAX_CAPTURE_BYTES + 1,
                     "weights.safetensors": historical.MAX_CAPTURE_BYTES + 1,
                     PREFIX + "precision_pilot/tensors/002.safetensors": audit.MAX_CAPTURE_BYTES + 1}
            for name, size in names.items():
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                with path.open("wb") as stream:
                    stream.truncate(size)
            subprocess.run(["git", "-C", str(root), "add", "."], check=True)
            entries, _ = public.index_entries(root)
            blocked, _ = public.residual_size_preflight(root, entries)
            self.assertEqual(blocked, {"weights.safetensors", PREFIX + "precision_pilot/tensors/002.safetensors"})


if __name__ == "__main__":
    unittest.main()

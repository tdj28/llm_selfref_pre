"""Offline security tests; synthetic states, stdlib only, isolated Git indexes."""

from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from scripts import audit_public_release as public
from scripts import audit_sae_residual_release as audit


REPO = Path(__file__).resolve().parents[1]
PLAN_BYTES = (REPO / audit.PLAN_PATH).read_bytes()
PLAN = json.loads(PLAN_BYTES)
PREFIX = audit.RELEASE_ROOT + "/"


def pack(header, payload):
    raw = json.dumps(header, separators=(",", ":")).encode()
    raw += b" " * (-len(raw) % 8)
    return struct.pack("<Q", len(raw)) + raw + payload


def tensor(tokens=(128000, 42), *, reverse=False, word=0x3f80, secret=False):
    hidden = struct.pack("<H", word) * (len(tokens) * audit.HIDDEN_WIDTH)
    if secret:
        prefix = b"sk-" + b"a" * 32 + b"\0"
        hidden = prefix + hidden[len(prefix):]
    token_bytes = struct.pack("<" + "q" * len(tokens), *tokens)
    chunks = [("hidden", hidden, "BF16", [1, len(tokens), audit.HIDDEN_WIDTH]),
              ("token_ids", token_bytes, "I64", [1, len(tokens)])]
    if reverse:
        chunks.reverse()
    header, payload = {}, b""
    for name, raw, dtype, shape in chunks:
        header[name] = {"dtype": dtype, "shape": shape, "data_offsets": [len(payload), len(payload) + len(raw)]}
        payload += raw
    return pack(header, payload)


def edit_header(raw, change):
    n = struct.unpack_from("<Q", raw)[0]
    header = json.loads(raw[8:8 + n])
    change(header)
    return pack(header, raw[8 + n:])


def evidence(files, modes=None):
    records = {p: (len(raw), audit.sha256(raw)) for p, raw in files.items()}
    actual_modes = {p: "100644" for p in files}
    actual_modes.update(modes or {})

    def read(path, limit):
        if len(files[path]) > limit:
            raise AssertionError("Reader was asked to materialize an oversized blob")
        return files[path]

    return audit.Evidence(files, records, actual_modes, read)


def raw_fixture(*, secret=False):
    """All 544 frozen IDs, not a monkeypatched smaller production inventory."""
    files = {audit.PLAN_PATH: PLAN_BYTES}
    capture = tensor()
    tokens = [128000, 42]
    for i, item in enumerate(PLAN["texts"]):
        raw = tensor(secret=True) if secret and i == 0 else capture
        capture_name = "residuals/" + item["id"] + ".safetensors"
        files[PREFIX + capture_name] = raw
        telemetry = {
            "schema_version": "sae_assay_backend_v2", "hook_layer": "model.layers.50.output",
            "native_dtype": "torch.bfloat16", "padding": "none", "repair_operator": "literal",
            "feature_ids": PLAN["target_feature_ids"], "full_encode_shape": [1, 65536, 8192],
            "hook_removed": True, "q90": None,
            "position_metadata": [{"position": j, "token_id": t, "origin": "prompt",
                                   "token_class": "special" if j == 0 else "prompt",
                                   "terminal_observation_only": False} for j, t in enumerate(tokens)],
        }
        row = {"id": "clean-" + item["id"], "text_id": item["id"],
               **{key: item[key] for key in ("split", "category", "corpus")},
               "group": "literal", "mode": "zero", "strength": 0,
               "capture": {"path": capture_name, "bytes": len(raw), "sha256": audit.sha256(raw)},
               "result": {"token_ids": tokens, "input_token_ids": tokens, "output_token_ids": [],
                          "input_tokens": 2, "prompt_length": 2, "output_tokens": 0,
                          "forward_schedule": "uncached_teacher", "full_sae_diagnostics": True,
                          "telemetry": telemetry, "clean_telemetry": telemetry}}
        files[PREFIX + "rows/" + row["id"] + ".json"] = audit.canonical(row)
    files[PREFIX + "model-bf16-load-00003.json"] = audit.canonical({
        "model_id": PLAN["model"]["id"], "model_revision": PLAN["model"]["revision"],
        "sae_id": PLAN["sae"]["id"], "sae_revision": PLAN["sae"]["revision"],
        "sae_sha256": PLAN["sae"]["sha256"], "precision": "bf16",
        "dtype": "torch.bfloat16", "hook": "model.layers.50.output"})
    files[PREFIX + "cuda_qualification/cheap-qualification.json"] = audit.canonical({"pass": True})
    refresh_receipts(files)
    return files


def refresh_projection(files):
    main, cheap = {}, {}
    for path, raw in files.items():
        if not path.startswith(PREFIX):
            continue
        relative = path[len(PREFIX):]
        if relative in {audit.INVENTORY_NAME, audit.MANIFEST_NAME, "retrieval_and_cost.json"}:
            continue
        if relative.startswith("cuda_qualification/"):
            cheap[relative.removeprefix("cuda_qualification/")] = audit.sha256(raw)
        else:
            main[relative] = audit.sha256(raw)
    files[PREFIX + "retrieval_and_cost.json"] = audit.canonical({
        "scope": "Projection of private chained lifecycle receipts; SSH/local paths omitted.",
        "freeze_commit": audit.FREEZE_COMMIT, "plan_sha256": audit.PLAN_SHA256,
        "pods": {kind: {"pod_id": "synthetic-" + kind, "get_status": 404, "within_limits": True}
                 for kind in ("cheap", "main")}, "artifacts": {"cheap": cheap, "main": main}})


def refresh_receipts(files):
    events = []

    def event(identifier, data):
        body = {"id": identifier, "seq": len(events), "data": data,
                "plan_sha256": audit.PLAN_SHA256, "freeze_commit": audit.FREEZE_COMMIT,
                "previous_sha256": events[-1]["sha256"] if events else None}
        body["sha256"] = hashlib.sha256(audit.canonical(body)[:-1]).hexdigest()
        events.append(body)

    event("binding", {"kind": "binding", "row_ids": sorted(audit.planned_row_ids(PLAN))})
    event("runtime", {"kind": "runtime", "stage": "post_stage1_engineering_repair"})
    rows = sorted(p for p in files if p.startswith(PREFIX + "rows/"))
    for path in rows:
        rid = Path(path).stem
        event("dispatch:" + rid, {"kind": "dispatch", "row_id": rid, "utc": "2026-09-30T00:00:00+00:00"})
        event("row:" + rid, {"kind": "row", "row_id": rid,
                             "payload": {"path": path[len(PREFIX):], "sha256": audit.sha256(files[path])}})
    files[PREFIX + "receipts.jsonl"] = b"".join(audit.canonical(e) for e in events)
    files[PREFIX + "DONE-all.json"] = audit.canonical({"status": "complete", "rows": len(rows)})
    refresh_projection(files)


def refresh_manifest(files):
    files[PREFIX + audit.MANIFEST_NAME] = audit.canonical({
        "schema": "sae_assay_repair_release_v1", "freeze_commit": audit.FREEZE_COMMIT,
        "plan_sha256": audit.PLAN_SHA256, "scope": "Synthetic security test only.",
        "files": [{"path": p[len(PREFIX):], "bytes": len(raw), "sha256": audit.sha256(raw)}
                  for p, raw in sorted(files.items()) if p.startswith(PREFIX)
                  and p != PREFIX + audit.MANIFEST_NAME]})


def ready_fixture(files):
    files = dict(files)
    inventory = audit.inspect_release(evidence(files))
    files[PREFIX + audit.INVENTORY_NAME] = audit.canonical(inventory)
    refresh_manifest(files)
    return files


def approve(files, modes=None):
    e = evidence(files, modes)
    checksum = audit.sha256(files[PREFIX + audit.INVENTORY_NAME])
    with patch.dict(audit.APPROVED_RESIDUAL_INVENTORIES, {audit.RELEASE_ROOT: checksum}, clear=True):
        return audit.approved_residual_paths(e.paths, e.records, e.modes, e.read)


class ContainerTests(unittest.TestCase):
    def test_accepts_both_orders_and_token_boundaries(self):
        for reverse in (False, True):
            audit.validate_capture(tensor((0, audit.VOCAB_SIZE - 1), reverse=reverse), [0, audit.VOCAB_SIZE - 1])
        tokens = [42] * audit.MAX_TOKENS
        audit.validate_capture(tensor(tokens), tokens)

    def test_rejects_malformed_headers_and_payloads(self):
        raw = tensor()
        changes = {
            "extra": lambda h: h.update(weight=h["hidden"]),
            "metadata": lambda h: h.update(__metadata__={}),
            "missing": lambda h: h.pop("token_ids"),
            "float32": lambda h: h["hidden"].update(dtype="F32"),
            "int32": lambda h: h["token_ids"].update(dtype="I32"),
            "width": lambda h: h["hidden"].update(shape=[1, 2, 16]),
            "batch": lambda h: h["hidden"].update(shape=[2, 2, 8192]),
            "bool": lambda h: h["hidden"].update(shape=[True, 2, 8192]),
            "float_dimension": lambda h: h["hidden"].update(shape=[1.0, 2, 8192]),
            "empty": lambda h: h["hidden"].update(shape=[1, 0, 8192]),
            "rank": lambda h: h["hidden"].update(shape=[2, 8192]),
            "tokens_shape": lambda h: h["token_ids"].update(shape=[1, 1]),
            "descriptor": lambda h: h["hidden"].update(unknown=1),
            "overlap": lambda h: h["token_ids"].update(data_offsets=[0, 16]),
            "gap": lambda h: h["token_ids"].update(data_offsets=[32770, 32786]),
            "negative": lambda h: h["hidden"].update(data_offsets=[-2, 32766]),
            "boolean_offset": lambda h: h["hidden"].update(data_offsets=[False, 32768]),
            "wrong_length": lambda h: h["hidden"].update(data_offsets=[0, 32766]),
        }
        cases = {name: edit_header(raw, change) for name, change in changes.items()}
        cases.update(short=b"123", truncated=raw[:-1], appended=raw + b"x",
                     huge=struct.pack("<Q", 2**63), unaligned=struct.pack("<Q", 7) + b"{}     ",
                     lfs=b"version https://git-lfs.github.com/spec/v1\n", gzip=b"\x1f\x8b" + raw)
        for name, broken in cases.items():
            with self.subTest(name=name), self.assertRaises(audit.ResidualAuditError):
                audit.validate_capture(broken, [128000, 42])

    def test_duplicate_header_keys_and_bad_json(self):
        for header in (b'{"hidden":{},"hidden":{},"token_ids":{}}', b'{"x":NaN}',
                       b'{"x":1e999}', b'\xff{}', b'{"hidden":'):
            header += b" " * (-len(header) % 8)
            with self.assertRaises(audit.ResidualAuditError):
                audit.validate_capture(struct.pack("<Q", len(header)) + header, [1])

    def test_rejects_nonfinite_and_wrong_or_invalid_tokens(self):
        for word in (0x7f80, 0xff80, 0x7fc1):
            with self.subTest(word=word), self.assertRaisesRegex(audit.ResidualAuditError, "nonfinite-residual"):
                audit.validate_capture(tensor(word=word), [128000, 42])
        for tokens in ([], [True], [-1], [audit.VOCAB_SIZE], [1] * 513, [1.0]):
            with self.subTest(tokens=tokens[:3]), self.assertRaises(audit.ResidualAuditError):
                audit.validate_capture(tensor(), tokens)
        for actual in ((128000, 43), (128000, -1), (128000, audit.VOCAB_SIZE)):
            with self.assertRaisesRegex(audit.ResidualAuditError, "residual-token-mismatch"):
                audit.validate_capture(tensor(actual), [128000, 42])


class EvidenceTests(unittest.TestCase):
    def setUp(self):
        registry = patch.dict(audit.APPROVED_RESIDUAL_INVENTORIES, {}, clear=True)
        registry.start()
        self.addCleanup(registry.stop)

    @classmethod
    def setUpClass(cls):
        cls.raw = raw_fixture()
        cls.ready = ready_fixture(cls.raw)
        cls.first = PLAN["texts"][0]
        cls.row_path = PREFIX + "rows/clean-" + cls.first["id"] + ".json"
        cls.capture_path = PREFIX + "residuals/" + cls.first["id"] + ".safetensors"

    def test_registry_is_empty_and_generation_does_not_authorize(self):
        self.assertEqual(audit.APPROVED_RESIDUAL_INVENTORIES, {})
        e = evidence(self.ready)
        self.assertEqual(audit.approved_residual_paths(e.paths, e.records, e.modes, e.read), frozenset())
        allowed = approve(self.ready)
        self.assertEqual(len(allowed), 544)
        self.assertEqual(allowed, {p for p in self.ready if p.endswith(".safetensors")})
        self.assertEqual(audit.APPROVED_RESIDUAL_INVENTORIES, {})

    def test_requires_exact_pin_and_exact_root(self):
        e = evidence(self.ready)
        for registry in ({audit.RELEASE_ROOT: "0" * 64}, {audit.RELEASE_ROOT + "-other": "0" * 64}):
            with patch.dict(audit.APPROVED_RESIDUAL_INVENTORIES, registry, clear=True):
                with self.assertRaises(audit.ResidualAuditError):
                    audit.approved_residual_paths(e.paths, e.records, e.modes, e.read)

    def test_rejects_missing_extra_or_misplaced_captures(self):
        cases = []
        files = dict(self.ready)
        del files[self.capture_path]
        cases.append(files)
        for path in (PREFIX + "residuals/unknown.safetensors", PREFIX + "weights.safetensors",
                     PREFIX + "residuals/notes.txt"):
            cases.append(dict(self.ready, **{path: tensor()}))
        for files in cases:
            with self.assertRaises(audit.ResidualAuditError):
                approve(files)

    def test_evidence_modes_are_not_ignored(self):
        for path in (self.capture_path, self.row_path, audit.PLAN_PATH,
                     PREFIX + audit.INVENTORY_NAME, PREFIX + "receipts.jsonl"):
            for mode in ("120000", "100755", "160000"):
                with self.subTest(path=path, mode=mode), self.assertRaises(audit.ResidualAuditError):
                    approve(self.ready, {path: mode})

    def test_hash_drift_is_rejected_at_every_binding(self):
        for path in (self.capture_path, self.row_path, audit.PLAN_PATH, PREFIX + "receipts.jsonl",
                     PREFIX + "model-bf16-load-00003.json", PREFIX + "cuda_qualification/cheap-qualification.json"):
            files = dict(self.ready)
            files[path] += b" "
            with self.subTest(path=path), self.assertRaises(audit.ResidualAuditError):
                approve(files)

    def test_clean_row_semantics_and_token_types(self):
        original = json.loads(self.raw[self.row_path])
        changes = (
            lambda r: r.update(mode="suppression"), lambda r: r.update(strength=True),
            lambda r: r.update(group="decoder_span"), lambda r: r.update(text_id="unknown"),
            lambda r: r.update(split="unknown"), lambda r: r["capture"].update(bytes=True),
            lambda r: r["capture"].update(path="residuals/../weights.safetensors"),
            lambda r: r["result"].update(token_ids=[True, 42]),
            lambda r: r["result"].update(input_tokens=True),
            lambda r: r["result"].update(input_token_ids=[128000, 43]),
            lambda r: r["result"].update(output_token_ids=[42]),
            lambda r: r["result"].update(forward_schedule="original_prefill_then_cached_token1"),
            lambda r: r["result"]["telemetry"].update(hook_layer="model.layers.49.output"),
            lambda r: r["result"]["telemetry"].update(native_dtype="torch.float32"),
            lambda r: r["result"]["telemetry"]["position_metadata"][0].update(position=True),
        )
        for change in changes:
            row = deepcopy(original)
            change(row)
            with self.assertRaises(audit.ResidualAuditError):
                audit.validate_row(row, self.first, PLAN)

    def test_recomputed_hashes_cannot_hide_wrong_tokens_or_model(self):
        files = dict(self.raw)
        row = json.loads(files[self.row_path])
        files[self.capture_path] = tensor((128000, 43))
        row["capture"]["sha256"] = audit.sha256(files[self.capture_path])
        files[self.row_path] = audit.canonical(row)
        refresh_receipts(files)
        with self.assertRaisesRegex(audit.ResidualAuditError, "residual-token-mismatch"):
            audit.inspect_release(evidence(files))
        files = dict(self.raw)
        path = PREFIX + "model-bf16-load-00003.json"
        model = json.loads(files[path])
        model["precision"] = "nf4"
        files[path] = audit.canonical(model)
        refresh_projection(files)
        with self.assertRaisesRegex(audit.ResidualAuditError, "model-load-binding-mismatch"):
            audit.inspect_release(evidence(files))

    def test_worker_chain_rejects_reordering_truncation_and_changes(self):
        e = evidence(self.raw)
        raw = self.raw[PREFIX + "receipts.jsonl"]
        lines = raw.splitlines(keepends=True)
        changed = json.loads(lines[2])
        changed["freeze_commit"] = "a" * 40
        cases = (raw[:-1], b"".join(lines[:2] + lines[3:4] + lines[2:3] + lines[4:]),
                 b"".join(lines[:2] + [audit.canonical(changed)] + lines[3:]),
                 b"".join(lines[:-1]))
        for case in cases:
            with self.assertRaises(audit.ResidualAuditError):
                audit.validate_ledger(case, PLAN, e)

    def test_retrieval_projection_and_completion_are_required(self):
        changes = (
            lambda p: p.update(freeze_commit="a" * 40),
            lambda p: p.update(plan_sha256="a" * 64),
            lambda p: p["pods"]["main"].update(get_status=200),
            lambda p: p["artifacts"]["main"].pop(self.capture_path[len(PREFIX):]),
            lambda p: p["artifacts"]["main"].update({"../outside": "a" * 64}),
        )
        for change in changes:
            files = dict(self.raw)
            projection = json.loads(files[PREFIX + "retrieval_and_cost.json"])
            change(projection)
            files[PREFIX + "retrieval_and_cost.json"] = audit.canonical(projection)
            with self.assertRaises(audit.ResidualAuditError):
                audit.inspect_release(evidence(files))
        files = dict(self.raw)
        files[PREFIX + "DONE-all.json"] = audit.canonical({"status": "complete", "rows": True})
        refresh_projection(files)
        with self.assertRaises(audit.ResidualAuditError):
            audit.inspect_release(evidence(files))

    def test_inventory_and_manifest_are_strict_and_complete(self):
        inventory_path = PREFIX + audit.INVENTORY_NAME
        files = dict(self.ready)
        inventory = json.loads(files[inventory_path])
        inventory["captures"][0]["tokens"] = True
        files[inventory_path] = audit.canonical(inventory)
        refresh_manifest(files)
        with self.assertRaisesRegex(audit.ResidualAuditError, "inventory-content"):
            approve(files)
        manifest_path = PREFIX + audit.MANIFEST_NAME
        changes = (
            lambda m: m["files"].append(m["files"][0]),
            lambda m: m["files"].pop(),
            lambda m: m["files"][0].update(bytes=True),
            lambda m: m["files"][0].update(bytes="12"),
            lambda m: m["files"][0].update(path="rows//x.json"),
            lambda m: m["files"][0].update(path="../x"),
            lambda m: m["files"][0].update(path="/absolute"),
        )
        for change in changes:
            files = dict(self.ready)
            manifest = json.loads(files[manifest_path])
            change(manifest)
            files[manifest_path] = audit.canonical(manifest)
            with self.assertRaises(audit.ResidualAuditError):
                audit.validate_manifest(evidence(files))

    def test_builder_fresh_output_and_no_self_authorization(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            write_fixture(root, self.raw)
            output = audit.build_inventory(root / audit.RELEASE_ROOT, root / audit.PLAN_PATH)
            self.assertEqual(output.read_bytes(), self.ready[PREFIX + audit.INVENTORY_NAME])
            self.assertEqual(audit.APPROVED_RESIDUAL_INVENTORIES, {})
            for path, expected in self.raw.items():
                self.assertEqual((root / path).read_bytes(), expected)
            with self.assertRaises(audit.ResidualAuditError):
                audit.build_inventory(root / audit.RELEASE_ROOT, root / audit.PLAN_PATH)

    def test_builder_failure_and_symlinks_do_not_write_inventory(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            files = dict(self.raw)
            del files[self.capture_path]
            write_fixture(root, files)
            run = root / audit.RELEASE_ROOT
            with self.assertRaises(audit.ResidualAuditError):
                audit.build_inventory(run, root / audit.PLAN_PATH)
            self.assertFalse((run / audit.INVENTORY_NAME).exists())
            (root / self.capture_path).symlink_to(root / self.row_path)
            with self.assertRaises(audit.ResidualAuditError):
                audit.build_inventory(run, root / audit.PLAN_PATH)
            self.assertFalse((run / audit.INVENTORY_NAME).exists())


def write_fixture(root, files):
    for name, raw in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)


class GitIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.files = ready_fixture(raw_fixture())

    def setUp(self):
        registry = patch.dict(audit.APPROVED_RESIDUAL_INVENTORIES, {}, clear=True)
        registry.start()
        self.addCleanup(registry.stop)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.git("init", "-q")
        write_fixture(self.root, self.files)
        for name in public.REQUIRED_PUBLIC_FILES:
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"" if name == ".gitignore" else b"Synthetic test fixture.\n")
        self.git("add", ".")
        checksum = audit.sha256(self.files[PREFIX + audit.INVENTORY_NAME])
        self.registry = patch.dict(audit.APPROVED_RESIDUAL_INVENTORIES,
                                   {audit.RELEASE_ROOT: checksum}, clear=True)

    def git(self, *args):
        return subprocess.run(["git", "-C", str(self.root), *args], check=True,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    def test_empty_registry_and_staged_bytes_are_authoritative(self):
        report = public.audit_repository(self.root)
        self.assertEqual(report["residual_captures_verified"], 0)
        self.assertEqual(sum(f["rule"] == "restricted-model-artifact" for f in report["findings"]), 544)
        capture = next(p for p in self.files if p.endswith(".safetensors"))
        with self.registry:
            report = public.audit_repository(self.root)
            self.assertEqual(report["findings"], [])
            self.assertEqual(report["residual_captures_verified"], 544)
            (self.root / capture).write_bytes(b"unstaged corrupt capture")
            self.assertEqual(public.audit_repository(self.root)["status"], "pass")
            self.git("add", capture)
            (self.root / capture).write_bytes(self.files[capture])
            report = public.audit_repository(self.root)
            self.assertEqual(report["status"], "fail")
            self.assertEqual(report["residual_captures_verified"], 0)

    def test_other_binaries_and_secrets_still_fail(self):
        files = {"weights/other.safetensors": tensor(), "weights/x.pth": b"weights",
                 "weights/x.ckpt": b"weights", "weights/x.onnx": b"weights", "weights/x.gguf": b"weights",
                 "credential.txt": b"value: " + b"sk-" + b"a" * 32}
        write_fixture(self.root, files)
        self.git("add", ".")
        with self.registry:
            report = public.audit_repository(self.root)
        self.assertEqual(report["residual_captures_verified"], 544)
        rules = {(f["path"], f["rule"]) for f in report["findings"]}
        self.assertIn(("credential.txt", "openai-key"), rules)
        for name in files:
            if name.startswith("weights/"):
                self.assertIn((name, "restricted-model-artifact"), rules)

    def test_index_modes_are_preserved(self):
        capture = next(p for p in self.files if p.endswith(".safetensors"))
        self.git("update-index", "--chmod=+x", capture)
        with self.registry:
            report = public.audit_repository(self.root)
        self.assertEqual(report["residual_captures_verified"], 0)
        self.assertTrue(any(f["rule"] == "invalid-residual-release" for f in report["findings"]))

    def test_secret_inside_approved_capture_still_blocks_release(self):
        files = ready_fixture(raw_fixture(secret=True))
        write_fixture(self.root, files)
        self.git("add", ".")
        checksum = audit.sha256(files[PREFIX + audit.INVENTORY_NAME])
        with patch.dict(audit.APPROVED_RESIDUAL_INVENTORIES, {audit.RELEASE_ROOT: checksum}, clear=True):
            report = public.audit_repository(self.root)
        self.assertEqual(report["residual_captures_verified"], 544)
        self.assertEqual(report["status"], "fail")
        self.assertTrue(any(f["rule"] == "openai-key" and f["path"].endswith(".safetensors")
                            for f in report["findings"]))

    def test_oversized_blob_not_passed_to_payload_scanner(self):
        name = "oversized.safetensors"
        with (self.root / name).open("wb") as stream:
            stream.truncate(audit.MAX_CAPTURE_BYTES + 1)
        self.git("add", name)
        scanned = []
        original = public.scan_blob

        def scan(path, data):
            scanned.append(path)
            return original(path, data)

        with patch.object(public, "scan_blob", side_effect=scan):
            report = public.audit_repository(self.root)
        self.assertNotIn(name, scanned)
        self.assertEqual(report["oversized_safetensors_rejected"], 1)
        self.assertEqual(report["status"], "fail")


class IsolationTests(unittest.TestCase):
    def test_registered_release_absent_from_other_repository_is_not_required(self):
        with patch.dict(audit.APPROVED_RESIDUAL_INVENTORIES, {audit.RELEASE_ROOT: "a" * 64}, clear=True):
            result = audit.approved_residual_paths(["README.md"], {}, {},
                lambda *_: self.fail("Absent release must not read evidence"))
        self.assertEqual(result, frozenset())

    def test_valid_container_does_not_bypass_secret_scan(self):
        raw = tensor(secret=True)
        audit.validate_capture(raw, [128000, 42])
        self.assertIn("openai-key", {f.rule for f in public.scan_blob("residual.safetensors", raw)})

    def test_standalone_cli_and_import_need_no_model_dependencies(self):
        result = subprocess.run([sys.executable, "-B", str(REPO / "scripts/audit_sae_residual_release.py"),
                                 "--help"], capture_output=True, check=True)
        self.assertIn(b"--build-inventory", result.stdout)
        script = ("import sys; sys.path.insert(0, " + repr(str(REPO)) + "); "
                  "from scripts import audit_public_release, audit_sae_residual_release; "
                  "assert not ({'torch','numpy','transformers','safetensors','huggingface_hub'} & sys.modules.keys())")
        subprocess.run([sys.executable, "-I", "-B", "-c", script], check=True, capture_output=True)

    def test_generic_manifest_bad_size_is_a_finding_not_a_crash(self):
        for size in (True, "bad", -1, None):
            raw = audit.canonical({"files": [{"path": "x", "bytes": size, "sha256": "a" * 64}]})
            findings, count = public.release_manifest_findings({"run/RELEASE_MANIFEST.json": raw}, {})
            self.assertEqual(count, 0)
            self.assertEqual(findings[0].rule, "invalid-release-entry")


if __name__ == "__main__":
    unittest.main()

"""Synthetic offline publication tests; never read live outcomes or contact services."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from experiments.sae_assay_diagnostic.budget import EventLedger, PodRegistry
from experiments.steering_fidelity import audit, protocol as p, runner
from scripts import release_steering_fidelity_calibration as r


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(p.canonical(value) + "\n")


class ReleaseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix=".fidelity-release-test-", dir=r.ROOT)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.base = self.root / "main-001"
        self.raw = self.base / "retrievals" / "final"
        self.raw.mkdir(parents=True)
        self.dest = self.root / "public"
        self.labels = self.root / "labels.jsonl"
        self.labels.write_text("".join(p.canonical({"feature_id": i, "description": "punctuation"}) + "\n"
                                       for i in range(64)))
        label_patch = patch.object(p, "LABELS", str(self.labels))
        label_patch.start()
        self.addCleanup(label_patch.stop)
        self.plan = {"budget": deepcopy(p.BUDGET), "rows": [{
            "id": f"synthetic-{i:03d}", "item_id": f"item-{i:03d}", "family": "fact",
            "frame": "neutral", "arm": "zero", "rung": "zero", "truth": True,
            "screen": True, "prompt": "Synthetic known-answer item."} for i in range(100)]}
        source_patch = patch.object(r, "verify_sources", return_value=self.plan)
        self.verify = source_patch.start()
        self.addCleanup(source_patch.stop)
        self.journal = runner.Journal(self.raw, r.PLAN_SHA256, r.FREEZE)
        self.rows = []

    def add_row(self, i, *, complete=True, invalid=False):
        spec = self.plan["rows"][i]
        telemetry = {"intervention": None, "position_metadata": [{"special": False}],
            "delivery": {"requested_norm": [0.], "realized_norm": [0.], "cosine": [1.],
                         "relative_error": [0.], "norm_ratio": [0.], "hidden_norm": [1.]}}
        row = {**spec, "plan_sha256": r.PLAN_SHA256, "freeze_commit": r.FREEZE,
            "missing": False, "elapsed_seconds": 1., "p_yes": .75, "p_no": .25,
            "valid_mass": 1., "p_correct": .75, "correct": True, "format_valid": True,
            "intervention": None, "telemetry": telemetry, "delivery": audit.delivery_summary(telemetry),
            "screen": {"positive_ids": list(range(64)), "positive_values": [1.] * 64,
                       "residual_norms": [1.]}}
        if invalid:
            row["p_correct"] = .01
        if spec["id"] not in self.journal.dispatched:
            self.journal.append("dispatch", spec["id"])
        path = self.raw / "forwards" / (spec["id"] + ".json")
        write(path, row)
        if complete:
            self.journal.append("complete", spec["id"], payload_sha256=p.sha(path))
        self.rows.append(row)

    def full(self, *, live=None):
        for i in range(100):
            self.add_row(i)
        state = p.select_panels(self.rows, [1.] * 65536, {i: "punctuation" for i in range(64)})
        write(self.raw / "calibration-state.json", {**state, "plan_sha256": r.PLAN_SHA256,
            "residual_reference": 1., "target_decoder_gram": [[float(i == j) for i in range(6)] for j in range(6)]})
        write(self.raw / "calibration-analysis.json", {"selected_rung": None, "pass": False, "synthetic": True})
        write(self.raw / "pressure-analysis.json", {"pass": False, "synthetic": True})
        write(self.raw / "liveness-analysis.json", live or {"selected_rung": None, "eligible_ids": [],
            "status": "not_run", "reason": "no_selected_dose"})
        write(self.raw / "complete.json", {"pass": True, "meaning": "inventory_complete_not_scientific_gate",
            "forwards": 100, "plan_sha256": r.PLAN_SHA256, "freeze_commit": r.FREEZE,
            "selected_rung": None, "pressure_qualified": False})

    def seal(self, *, historical=None, closed_changes=None, no_worker=False, before=None, extra_artifacts=None):
        ledger = EventLedger(self.base / "events.jsonl", r.PLAN_SHA256, r.FREEZE, [])
        ledger.bind("controller:config", {"kind": "main", "namespace": r.NAMESPACE,
            "plan_path": r.PLAN_PATH, "budget": self.plan["budget"]})
        pod = {"id": "synthetic-owned-pod", "name": "codex-" + r.NAMESPACE + "-main-123456789abc",
               "createdAt": "2026-01-01T00:00:00+00:00", "ssh": {"direct": "192.0.2.1"}}
        ledger.bind("create-intent", {"payload": {"name": pod["name"]}, "blocked": ["preexisting"],
                                     "prior_new_usd": "1"})
        created = ledger.bind("created", pod)
        registry = PodRegistry(ledger, ["preexisting"])
        final = self.base / "final-retrieval.json"
        registry.register_created(pod["id"], created["sha256"], [str(final)])
        if not no_worker:
            ledger.bind("worker-intent", {"synthetic": True})
        if before:
            prior = ledger.bind("retrieval:prior", {"pod_id": pod["id"], "directory": str(before),
                "artifacts": {n: p.sha(f) for n, f in r._files(before).items()}})
            ledger.bind("live-audit:prior", {"retrieval_sha256": prior["sha256"],
                                           "report": {"pass": False, "unresolved_forward_ids": ["synthetic-001"]}})
        write(self.raw / "controller-exit.json", {"exit_code": 0})
        data = {"pod_id": pod["id"], "directory": str(self.raw),
                "artifacts": {n: p.sha(f) for n, f in r._files(self.raw).items()}}
        if extra_artifacts:
            data["artifacts"].update(extra_artifacts)
        if no_worker:
            data = {"pod_id": pod["id"], "no_worker_dispatched": True, "artifacts": {}}
        receipt = ledger.bind("retrieval:final", data)
        write(final, receipt)
        if historical:
            ledger.bind("final-structural-audit", {"retrieval_sha256": receipt["sha256"], **historical})
        permit = registry.authorize_delete(pod["id"], {str(final): p.sha(final)})
        ledger.bind("delete-intent", {"permit_sha256": permit["sha256"], "pod_id": pod["id"], "pod": pod})
        ledger.bind("closed", {"pod_id": pod["id"], "get_status": 404, "inventory_ids": [],
            "utc": "2026-01-01T00:01:00+00:00", "elapsed_seconds": "60", "within_limits": True,
            "compute_upper_bound_usd": "1", "cumulative_gpu_upper_bound_usd": "2",
            "all_in_upper_bound_usd": "5", **(closed_changes or {})})
        return ledger

    def publish(self, **kwargs):
        r.copy_release(self.base, self.dest, **kwargs)
        return r._json(self.dest / "retrieval_and_cost.json")

    def test_complete_means_inventory_not_science_and_exact_manifest(self):
        self.full()
        self.seal()
        source_before = {n: f.read_bytes() for n, f in r._files(self.base).items()}
        value = self.publish()
        self.assertEqual(value["status"], "complete")
        self.assertTrue(value["raw_audit"]["pass"])
        self.assertFalse(value["scientific_gate_evaluated"])
        self.assertFalse(r._json(self.dest / "pressure-analysis.json")["pass"])
        for n, digest in value["artifacts"].items():
            self.assertEqual((self.dest / n).read_bytes(), (self.raw / n).read_bytes())
            self.assertEqual(p.sha(self.dest / n), digest)
        manifest = r._json(self.dest / "RELEASE_MANIFEST.json")
        self.assertEqual({v["path"] for v in manifest["files"]}, set(r._files(self.dest)) - {"RELEASE_MANIFEST.json"})
        for entry in manifest["files"]:
            self.assertEqual(entry["sha256"], p.sha(self.dest / entry["path"]))
            self.assertEqual(entry["bytes"], (self.dest / entry["path"]).stat().st_size)
        self.assertEqual(source_before, {n: f.read_bytes() for n, f in r._files(self.base).items()})
        output = b"".join(f.read_bytes() for f in r._files(self.dest).values())
        for forbidden in (str(self.base).encode(), b'"ssh"', b"192.0.2.1", b"preexisting"):
            self.assertNotIn(forbidden, output)

    def test_partial_pass_is_not_complete_and_needs_opt_in(self):
        self.add_row(0)
        self.seal()
        with self.assertRaisesRegex(ValueError, "allow-incomplete"):
            self.publish()
        self.assertFalse(self.dest.exists())
        value = self.publish(allow_incomplete=True)
        self.assertEqual(value["status"], "incomplete")
        self.assertTrue(value["raw_audit"]["pass"])
        self.assertEqual(value["absent_forward_files"], 99)

    def test_inflight_is_incomplete_not_corruption_and_raw_failure_survives(self):
        self.add_row(0)
        self.add_row(1, complete=False)
        write(self.raw / "failed.json", {"type": "TimeoutError", "message": "Synthetic deadline"})
        self.seal(historical={"status": "failed", "error_type": "ValueError"})
        value = self.publish(allow_incomplete=True)
        self.assertEqual(value["raw_audit"]["status"], "audited")
        self.assertFalse(value["raw_audit"]["pass"])
        self.assertEqual(value["raw_audit"]["forwards"], 1)
        self.assertEqual(value["raw_audit"]["unresolved_forward_ids"], ["synthetic-001"])
        self.assertEqual(value["lifecycle_audit"]["status"], "failed")
        self.assertEqual((self.dest / "failed.json").read_bytes(), (self.raw / "failed.json").read_bytes())

    def test_audit_exception_is_preserved_not_faked_pass(self):
        self.add_row(0, invalid=True)
        self.seal()
        value = self.publish(allow_incomplete=True)
        self.assertEqual(value["raw_audit"], {"status": "failed", "pass": False,
                                             "complete": False, "error_type": "ValueError"})

    def test_complete_marker_cannot_hide_unresolved_forward(self):
        self.full()
        lines = (self.raw / "receipts.jsonl").read_bytes().splitlines(keepends=True)
        (self.raw / "receipts.jsonl").write_bytes(b"".join(lines[:-1]))
        self.seal()
        value = self.publish(allow_incomplete=True)
        self.assertTrue(value["worker_completion_marker"])
        self.assertEqual(value["status"], "incomplete")
        self.assertFalse(value["raw_audit"]["pass"])

    def test_liveness_timeout_keeps_core_completion_distinct(self):
        self.full(live={"status": "incomplete", "reason": "liveness_time_allowance_exhausted",
                        "not_a_zero_effect": True, "core_calibration_complete": True})
        self.seal()
        value = self.publish(allow_incomplete=True)
        self.assertTrue(value["raw_audit"]["complete"])
        self.assertEqual(value["status"], "incomplete")
        self.assertFalse(value["liveness_inventory_complete"])

    def test_lineage_preserves_previously_unreceipted_payload(self):
        self.add_row(0)
        self.add_row(1, complete=False)
        before = self.base / "retrievals" / "prior"
        for n, f in r._files(self.raw).items():
            (before / n).parent.mkdir(parents=True, exist_ok=True)
            (before / n).write_bytes(f.read_bytes())
        self.journal.append("complete", "synthetic-001", payload_sha256=p.sha(self.raw / "forwards/synthetic-001.json"))
        self.seal(before=before)
        value = self.publish(allow_incomplete=True)
        prior = value["snapshot_lineage"][0]
        self.assertFalse(prior["raw_audit"]["pass"])
        self.assertEqual(prior["raw_audit"]["status"], "audited")
        self.assertEqual(prior["committed_forward_payloads_preserved"], 2)
        self.assertTrue(prior["all_committed_forward_bytes_preserved"])
        self.assertFalse(prior["recorded_audits"][0]["pass"])
        self.assertTrue(value["raw_audit"]["pass"])

    def test_lineage_pending_temp_disappears_on_exact_commit(self):
        self.add_row(0)
        self.add_row(1, complete=False)
        before = self.base / "retrievals" / "prior"
        for n, f in r._files(self.raw).items():
            name = n + ".pending" if n == "forwards/synthetic-001.json" else n
            (before / name).parent.mkdir(parents=True, exist_ok=True)
            (before / name).write_bytes(f.read_bytes())
        self.journal.append("complete", "synthetic-001", payload_sha256=p.sha(self.raw / "forwards/synthetic-001.json"))
        self.seal(before=before)
        value = self.publish(allow_incomplete=True)
        prior = value["snapshot_lineage"][0]
        self.assertEqual(prior["committed_forward_payloads_preserved"], 1)
        self.assertFalse(prior["raw_audit"]["pass"])
        self.assertEqual(prior["pending_reconciliation"], [{
            "path": "forwards/synthetic-001.json.pending", "final_path": "forwards/synthetic-001.json",
            "sha256": p.sha(self.raw / "forwards/synthetic-001.json"), "status": "byte_exact_final_json"}])
        self.assertEqual(value["pending_temporary_files"], [])

    def test_lineage_partial_temp_is_not_a_committed_outcome(self):
        before = self.base / "retrievals" / "prior"
        pending = before / "forwards/synthetic-000.json.pending"
        pending.parent.mkdir(parents=True)
        pending.write_bytes(b'{"unfinished":')
        self.add_row(0)
        self.seal(before=before)
        value = self.publish(allow_incomplete=True)
        prior = value["snapshot_lineage"][0]
        self.assertEqual(prior["committed_forward_payloads_preserved"], 0)
        self.assertEqual(prior["pending_reconciliation"][0]["status"], "not_a_committed_outcome")

    def test_final_pending_temp_prevents_completion(self):
        self.full()
        pending = self.raw / "forwards/synthetic-000.json.pending"
        pending.write_bytes((self.raw / "forwards/synthetic-000.json").read_bytes())
        self.seal()
        value = self.publish(allow_incomplete=True)
        self.assertTrue(value["raw_audit"]["complete"])
        self.assertEqual(value["status"], "incomplete")
        self.assertEqual(value["pending_temporary_files"], ["forwards/synthetic-000.json.pending"])
        self.assertEqual(value["absent_forward_files"], 0)

    def test_lineage_committed_payload_change_is_rejected(self):
        before = self.base / "retrievals" / "prior"
        write(before / "forwards/synthetic-000.json", {"earlier_committed_bytes": True})
        self.add_row(0)
        self.seal(before=before)
        with self.assertRaisesRegex(ValueError, "Earlier forward bytes lost"):
            self.publish(allow_incomplete=True)

    def test_unstarted_attempt_and_unknown_cost_are_explicit(self):
        self.seal(no_worker=True, closed_changes={"within_limits": False,
            "compute_upper_bound_usd": None, "cumulative_gpu_upper_bound_usd": None, "all_in_upper_bound_usd": None})
        value = self.publish(allow_incomplete=True)
        self.assertEqual(value["raw_audit"]["status"], "not_started")
        self.assertIsNone(value["closure"]["compute_upper_bound_usd"])
        self.assertEqual(value["artifacts"], {})

    def test_inherited_model_load_metadata_is_copied_not_weights(self):
        write(self.raw / "model-bf16-load-00002.json", {"dtype": "torch.bfloat16", "synthetic": True})
        self.seal()
        value = self.publish(allow_incomplete=True)
        self.assertIn("model-bf16-load-00002.json", value["artifacts"])

    def test_model_metadata_filename_and_count_are_bounded(self):
        for name in ("model-bf16-load-99999.json", "model-bf16-load-00002.safetensors", "model-bf16-load-00002.bin"):
            with self.subTest(name=name):
                path = self.raw / name
                write(path, {})
                with self.assertRaisesRegex(ValueError, "inventory"):
                    r.inventory(self.raw, {name: p.sha(path)}, self.plan)
                path.unlink()
        for name in ("model-bf16-load-00002.json", "model-bf16-load-00003.json"):
            write(self.raw / name, {})
        with self.assertRaisesRegex(ValueError, "Multiple model-load"):
            r.inventory(self.raw, {n: p.sha(f) for n, f in r._files(self.raw).items()}, self.plan)

    def test_post_close_mutation_during_copy_prevents_manifest(self):
        self.add_row(0)
        self.seal()
        original_scan = r.scan
        def mutate(name, path):
            original_scan(name, path)
            if path == self.dest / "retrieval_and_cost.json":
                write(self.raw / "forwards/synthetic-000.json", {"changed_after_copy": True})
        with patch.object(r, "scan", side_effect=mutate):
            with self.assertRaisesRegex(ValueError, "Post-close source mutation"):
                self.publish(allow_incomplete=True)
        self.assertFalse((self.dest / "RELEASE_MANIFEST.json").exists())

    def test_post_close_ledger_mutation_prevents_manifest(self):
        self.seal()
        original_scan = r.scan
        def mutate(name, path):
            original_scan(name, path)
            if path == self.dest / "retrieval_and_cost.json":
                with (self.base / "events.jsonl").open("a") as stream:
                    stream.write("\n")
        with patch.object(r, "scan", side_effect=mutate):
            with self.assertRaisesRegex(ValueError, "Post-close source mutation"):
                self.publish(allow_incomplete=True)
        self.assertFalse((self.dest / "RELEASE_MANIFEST.json").exists())

    def test_missing_ledger_never_created(self):
        with self.assertRaises(FileNotFoundError):
            self.publish(allow_incomplete=True)
        self.assertFalse((self.base / "events.jsonl").exists())

    def test_empty_ledger_never_gets_a_binding_written(self):
        (self.base / "events.jsonl").touch()
        with self.assertRaises(KeyError):
            self.publish(allow_incomplete=True)
        self.assertEqual((self.base / "events.jsonl").read_bytes(), b"")

    def test_ledger_tampering_rejected(self):
        self.seal()
        path = self.base / "events.jsonl"
        path.write_bytes(path.read_bytes().replace(b'"get_status":404', b'"get_status":200'))
        with self.assertRaisesRegex(ValueError, "mismatch"):
            self.publish(allow_incomplete=True)

    def test_missing_get404_rejected(self):
        self.seal(closed_changes={"get_status": 200})
        with self.assertRaisesRegex(ValueError, "Closure linkage"):
            self.publish(allow_incomplete=True)

    def test_closed_pod_in_inventory_rejected(self):
        self.seal(closed_changes={"inventory_ids": ["synthetic-owned-pod"]})
        with self.assertRaisesRegex(ValueError, "Closure linkage"):
            self.publish(allow_incomplete=True)

    def test_inconsistent_cost_rejected(self):
        self.seal(closed_changes={"all_in_upper_bound_usd": "4"})
        with self.assertRaisesRegex(ValueError, "Cost projection"):
            self.publish(allow_incomplete=True)

    def test_final_retrieval_must_be_last(self):
        ledger = self.seal()
        ledger.bind("retrieval:later", {"pod_id": "synthetic-owned-pod", "artifacts": {}})
        with self.assertRaisesRegex(ValueError, "Post-close lifecycle"):
            self.publish(allow_incomplete=True)

    def test_final_receipt_file_cannot_be_substituted(self):
        self.seal()
        with (self.base / "final-retrieval.json").open("a") as stream:
            stream.write("\n")
        with self.assertRaisesRegex(ValueError, "Closure linkage"):
            self.publish(allow_incomplete=True)

    def test_changed_raw_bytes_rejected(self):
        self.add_row(0)
        self.seal()
        (self.raw / "forwards/synthetic-000.json").write_text("{}\n")
        with self.assertRaisesRegex(ValueError, "hash mismatch"):
            self.publish(allow_incomplete=True)

    def test_unlisted_artifact_rejected(self):
        self.seal()
        write(self.raw / "model.json", {})
        with self.assertRaisesRegex(ValueError, "inventory"):
            self.publish(allow_incomplete=True)

    def test_unexpected_artifact_rejected_even_if_receipted(self):
        write(self.raw / "private.json", {})
        self.seal()
        with self.assertRaisesRegex(ValueError, "inventory"):
            self.publish(allow_incomplete=True)

    def test_manifest_traversal_rejected(self):
        self.seal(extra_artifacts={"../outside.json": "a" * 64})
        with self.assertRaisesRegex(ValueError, "inventory"):
            self.publish(allow_incomplete=True)

    def test_symlink_file_and_symlink_destination_ancestor_rejected(self):
        self.seal()
        (self.raw / "model.json").symlink_to(self.labels)
        with self.assertRaisesRegex(ValueError, "symlink"):
            self.publish(allow_incomplete=True)
        link = self.root / "linked"
        link.symlink_to(self.root, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "Symlink"):
            r.copy_release(self.base, link / "public", allow_incomplete=True)

    def test_overwrite_and_nested_destination_rejected(self):
        self.seal()
        self.dest.mkdir()
        with self.assertRaisesRegex(ValueError, "overwrite"):
            self.publish(allow_incomplete=True)
        with self.assertRaisesRegex(ValueError, "Overlapping"):
            r.copy_release(self.base, self.raw / "new", allow_incomplete=True)

    def test_binary_secrets_paths_and_transport_content_rejected(self):
        values = [b"\x00binary", b"\xff", ('hf_' + 'Q' * 30).encode(), b'/Users/synthetic/private',
                  b'192.0.2.8', b'2001:db8::1', b'"ssh": {}', b'{"v":"192\\u002e0.2.8"}',
                  b'{"v":"\\u0000"}', b'{"v":"\\u0068f_' + b'Q' * 30 + b'"}',
                  b'{"\\u0052UNPOD_API_KEY":"' + b'q7W8e9R0t1Y2u3I4o5P6' + b'"}']
        for data in values:
            with self.subTest(data=data):
                path = self.root / "model.json"
                path.write_bytes(data)
                with self.assertRaises((ValueError, UnicodeError)):
                    r.scan("model.json", path)

    def test_exact_package_versions_are_not_network_addresses(self):
        for package, version in r.PACKAGE_VERSIONS.items():
            for name, value in (("pip-freeze.txt", package + "==" + version),
                ("controller.log", "Requirement already satisfied: " + package + "==" + version
                 + " in /usr/local/lib/python3.12/dist-packages (" + version + ")")):
                path = self.root / name
                path.write_text(value + "\n")
                r.scan(name, path)

    def test_package_exception_does_not_hide_other_addresses(self):
        values = [("controller.log", "host 9.10.2.21"), ("pip-freeze.txt", "host==192.0.2.8"),
            ("controller.log", "Requirement already satisfied: nvidia-cudnn-cu12==9.10.2.21 "
             "in /usr/local/lib from 192.0.2.8 (9.10.2.21)"),
            ("model.json", '{"version":"9.10.2.21"}')]
        for name, value in values:
            path = self.root / name
            path.write_text(value)
            with self.assertRaises(ValueError):
                r.scan(name, path)


class FrozenBindingTests(unittest.TestCase):
    def test_actual_frozen_sources_offline_without_head(self):
        plan = r.verify_sources()
        self.assertEqual(len(plan["rows"]), 9300)
        self.assertEqual(hashlib.sha256(r.frozen_blob(r.PLAN_PATH)).hexdigest(), r.PLAN_SHA256)

    def test_git_is_no_replace_no_lazy_fetch_and_regular_blob_only(self):
        calls = []
        def run(command, **kwargs):
            calls.append((command, kwargs))
            result = type("Result", (), {})()
            result.stdout = b"100644 blob " + b"a" * 40 + b"\tsynthetic.txt\0" if "ls-tree" in command else b"fixture"
            return result
        with patch.object(r.subprocess, "run", side_effect=run):
            self.assertEqual(r.frozen_blob("synthetic.txt"), b"fixture")
        for command, kwargs in calls:
            self.assertIn("--no-replace-objects", command)
            self.assertEqual(kwargs["env"]["GIT_NO_LAZY_FETCH"], "1")
            self.assertNotIn("HEAD", command)
        with self.assertRaisesRegex(ValueError, "artifact path"):
            r.frozen_blob("../unexpected")
        with patch.object(r.subprocess, "run") as run_mock:
            run_mock.return_value.stdout = b"120000 blob " + b"a" * 40 + b"\tsynthetic.txt\0"
            with self.assertRaisesRegex(ValueError, "regular blob"):
                r.frozen_blob("synthetic.txt")

    def test_wrong_frozen_plan_hash_rejected(self):
        with patch.object(r, "frozen_blob", return_value=b"{}"):
            with self.assertRaisesRegex(ValueError, "plan hash"):
                r.verify_sources()


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from experiments.consciousness_sae_realization_validation import build_plan
from experiments.consciousness_sae_realization_validation import controls
from experiments.consciousness_sae_realization_validation import protocol
from experiments.consciousness_sae_realization_validation import storage_benchmark


class StorageBenchmarkTests(unittest.TestCase):
    SHARD_BYTES = 256 * 1024
    CHUNK_BYTES = 32 * 1024
    VOLUME_ID = "test-realization-volume"

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name).resolve()
        self.plan_dir = self.root / "plan"
        self.volume = self.root / "volume"
        self.receipts = self.root / "receipts"
        self.volume.mkdir()
        self.receipts.mkdir()
        build_plan.build(outdir=self.plan_dir)
        sentinel = {
            "schema_version": controls.CONTROL_SCHEMA_VERSION,
            "study_slug": protocol.STUDY_SLUG,
            "study_id": protocol.STUDY_ID,
            "protocol_version": protocol.PROTOCOL_VERSION,
            "volume_id": self.VOLUME_ID,
            "purpose": controls.VOLUME_PURPOSE,
        }
        (self.volume / controls.VOLUME_SENTINEL).write_bytes(
            controls.canonical_json_bytes(sentinel) + b"\n"
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def run_small(
        self, *, run_id: str = "storage-test-01", output: Path | None = None
    ) -> dict:
        return storage_benchmark.run_benchmark(
            plan_dir=self.plan_dir,
            volume_root=self.volume,
            volume_id=self.VOLUME_ID,
            run_id=run_id,
            output=output or self.receipts / f"{run_id}.json",
            chunk_bytes=self.CHUNK_BYTES,
            _test_shard_bytes=self.SHARD_BYTES,
            _test_capability=storage_benchmark._TEST_OVERRIDE_CAPABILITY,
        )

    def test_dense_interruption_resume_atomic_hash_and_cleanup(self) -> None:
        output = self.receipts / "benchmark.json"
        receipt = self.run_small(output=output)
        controls.validate_storage_benchmark(receipt)

        persisted = json.loads(output.read_text(encoding="utf-8"))
        self.assertEqual(persisted, receipt)
        self.assertEqual(
            output.read_bytes(), controls.canonical_json_bytes(receipt) + b"\n"
        )
        self.assertEqual(receipt["observed_peak_logical_bytes"], self.SHARD_BYTES)
        self.assertGreaterEqual(
            receipt["observed_peak_allocated_bytes"], self.SHARD_BYTES
        )
        self.assertEqual(
            receipt["target_blind_fixture_sha256"],
            storage_benchmark._expected_digest(
                receipt["plan_manifest_sha256"],
                self.SHARD_BYTES,
                chunk_bytes=self.CHUNK_BYTES,
            ),
        )
        self.assertEqual(
            receipt["runner_source_sha256"],
            controls.sha256_file(
                build_plan.REPO_ROOT / storage_benchmark.RUNNER_RELATIVE_PATH
            ),
        )
        self.assertTrue(receipt["filesystem_id"].startswith("posix-sha256:"))
        self.assertTrue(receipt["interruption_resume_exercised"])
        self.assertTrue(receipt["checksum_pass"])
        self.assertEqual(
            receipt["execution_authorization_status"],
            "not_evaluated_storage_only",
        )
        self.assertIs(receipt["model_execution_authorized"], False)
        for field in (
            "model_forward_count",
            "target_prompt_render_count",
            "target_forward_count",
            "target_outcome_count",
        ):
            self.assertEqual(receipt[field], 0)
        self.assertEqual(receipt["prior_outcome_inputs"], [])

        forged = dict(receipt)
        forged["model_execution_authorized"] = True
        forged_core = dict(forged)
        forged_core.pop("receipt_sha256")
        forged["receipt_sha256"] = controls.canonical_sha256(forged_core)
        with self.assertRaisesRegex(
            controls.ControlViolation, "falsely implies model-execution"
        ):
            controls.validate_storage_benchmark(forged)

        payload_root = (
            self.volume
            / protocol.STUDY_SLUG
            / protocol.STUDY_ID
            / "storage_benchmark"
        )
        self.assertFalse(
            any(payload_root.glob("storage-test-01.payload.*"))
            if payload_root.exists()
            else False
        )

    def test_submaximal_override_requires_unforgeable_in_process_capability(self) -> None:
        with self.assertRaisesRegex(
            storage_benchmark.BenchmarkError, "private test-only"
        ):
            storage_benchmark.run_benchmark(
                plan_dir=self.plan_dir,
                volume_root=self.volume,
                volume_id=self.VOLUME_ID,
                run_id="no-capability",
                output=self.receipts / "no-capability.json",
                chunk_bytes=self.CHUNK_BYTES,
                _test_shard_bytes=self.SHARD_BYTES,
            )

    def test_fixture_pattern_does_not_repeat_seed_blocks_or_chunks(self) -> None:
        plan_hash = "a" * 64
        first = storage_benchmark._pattern(plan_hash, 0, 8 * 1024)
        second = storage_benchmark._pattern(plan_hash, 1, 8 * 1024)
        blocks = {first[offset : offset + 32] for offset in range(0, len(first), 32)}
        self.assertEqual(len(blocks), len(first) // 32)
        self.assertNotEqual(first, second)

    def test_cli_exposes_no_size_override(self) -> None:
        self.assertEqual(
            storage_benchmark._benchmark_size(
                test_shard_bytes=None, test_capability=None
            ),
            protocol.RESOURCE_LIMITS["max_shard_bytes"],
        )
        arguments = [
            "--plan-dir",
            str(self.plan_dir),
            "--volume-root",
            str(self.volume),
            "--volume-id",
            self.VOLUME_ID,
            "--run-id",
            "cli-test",
            "--output",
            str(self.receipts / "cli-test.json"),
            "--shard-bytes",
            "4096",
        ]
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            storage_benchmark.build_parser().parse_args(arguments)

    def test_run_id_cannot_escape_disposable_namespace(self) -> None:
        with self.assertRaisesRegex(storage_benchmark.BenchmarkError, "run ID"):
            self.run_small(run_id="../../escape")
        self.assertFalse((self.root / "escape.payload.partial").exists())

    def test_receipt_cannot_be_stored_inside_disposable_payload_directory(self) -> None:
        payload_output = (
            self.volume
            / protocol.STUDY_SLUG
            / protocol.STUDY_ID
            / "storage_benchmark"
            / "receipt.json"
        )
        with self.assertRaisesRegex(
            storage_benchmark.BenchmarkError, "outside the disposable"
        ):
            self.run_small(output=payload_output)

    def test_interrupted_prefix_mismatch_is_quarantined_not_accepted(self) -> None:
        with mock.patch.object(
            storage_benchmark, "_hash_file", return_value="0" * 64
        ), self.assertRaisesRegex(storage_benchmark.BenchmarkError, "prefix checksum"):
            self.run_small(run_id="bad-prefix")
        payload_root = (
            self.volume
            / protocol.STUDY_SLUG
            / protocol.STUDY_ID
            / "storage_benchmark"
        )
        quarantine = payload_root / "bad-prefix.payload.quarantine"
        self.assertTrue(quarantine.is_file())
        self.assertEqual(quarantine.stat().st_size, self.SHARD_BYTES // 2)
        self.assertFalse((self.receipts / "bad-prefix.json").exists())

    def test_plan_and_runner_source_binding_is_rechecked(self) -> None:
        inventory_path = self.plan_dir / "source_files.json"
        inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
        runner_record = next(
            row
            for row in inventory["files"]
            if row["path"] == storage_benchmark.RUNNER_RELATIVE_PATH
        )
        runner_record["sha256"] = "0" * 64
        inventory_path.write_bytes(controls.canonical_json_bytes(inventory) + b"\n")

        manifest_path = self.plan_dir / "plan_manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        source_record = next(
            row for row in manifest["files"] if row["path"] == "source_files.json"
        )
        source_record["bytes"] = inventory_path.stat().st_size
        source_record["sha256"] = controls.sha256_file(inventory_path)
        manifest.pop("plan_manifest_sha256")
        manifest["plan_manifest_sha256"] = controls.canonical_sha256(manifest)
        manifest_path.write_bytes(controls.canonical_json_bytes(manifest) + b"\n")

        with self.assertRaisesRegex(storage_benchmark.BenchmarkError, "bound source"):
            self.run_small(run_id="bad-runner-binding")


if __name__ == "__main__":
    unittest.main()

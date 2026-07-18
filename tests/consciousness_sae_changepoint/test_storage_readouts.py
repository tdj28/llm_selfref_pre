from __future__ import annotations

import importlib.util
import json
import math
import tempfile
import unittest
from pathlib import Path

from experiments.consciousness_sae_changepoint import paths, readouts, storage


class TransactionalArchiveTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name) / "network-volume"
        self.root.mkdir(parents=True)
        (self.root / paths.ARTIFACT_VOLUME_SENTINEL).write_text(
            json.dumps(
                {
                    "study_slug": paths.STUDY_SLUG,
                    "volume_id": "synthetic-volume",
                    "volume_size_gb": 500,
                }
            ),
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def start(self, run_id: str = "run-001") -> storage.RunTransaction:
        return storage.RunTransaction.start(
            phase="target-blind-fixture",
            run_id=run_id,
            artifact_root=self.root,
            expected_volume_id="synthetic-volume",
            minimum_free_bytes=0,
            metadata={"plan_path": "plans/frozen.json"},
        )

    def test_run_and_block_complete_last_and_verify(self) -> None:
        run = self.start()
        self.assertTrue(run.partial_path.name.endswith(".partial"))
        self.assertFalse((run.partial_path / storage.COMPLETE_MARKER).exists())
        block = run.begin_block("block-000")
        block.write_json("telemetry/hook.json", {"calls": 1})
        completed_block = block.complete(metadata={"role": "synthetic"})
        self.assertFalse(completed_block.name.endswith(".partial"))
        self.assertEqual(storage.verify_completed_block(completed_block)["status"], "verified")
        run.write_json("gates/replay.json", {"status": "pass"})
        completed = run.complete(metadata={"outcomes_opened": False})
        self.assertFalse(completed.name.endswith(".partial"))
        receipt = storage.verify_completed_run(completed)
        self.assertEqual(receipt["status"], "verified")
        manifest = json.loads((completed / storage.RUN_MANIFEST).read_text())
        self.assertTrue(manifest["files"])
        self.assertTrue(
            all(not Path(record["path"]).is_absolute() for record in manifest["files"])
        )
        serialized = (completed / storage.RUN_MANIFEST).read_text()
        self.assertNotIn(str(self.root), serialized)

    def test_completed_archive_detects_mutation_and_extra_file(self) -> None:
        run = self.start()
        completed = run.complete()
        started = completed / "RUN_STARTED.json"
        started.write_text(started.read_text() + " ", encoding="utf-8")
        with self.assertRaisesRegex(storage.ArchiveIntegrityError, "byte count changed"):
            storage.verify_completed_run(completed)

        second = self.start("run-002").complete()
        (second / "unreceipted.txt").write_text("not in manifest", encoding="utf-8")
        with self.assertRaisesRegex(storage.ArchiveIntegrityError, "inventory differs"):
            storage.verify_completed_run(second)

    def test_freshness_and_partial_directories_fail_closed(self) -> None:
        run = self.start()
        with self.assertRaisesRegex(Exception, "already exist"):
            self.start()
        with self.assertRaisesRegex(storage.ArchiveIntegrityError, "partial"):
            storage.verify_completed_run(run.partial_path)
        first = run.begin_block("block-000")
        with self.assertRaisesRegex(storage.ArchiveStateError, "not fresh"):
            run.begin_block("block-000")
        first.write_json("fixture.json", {"ok": True})
        first.complete()

    def test_absolute_or_non_normalized_serialized_paths_are_rejected(self) -> None:
        run = self.start()
        with self.assertRaises(storage.ArchiveIntegrityError):
            run.write_json("metadata/bad.json", {"source_path": "/tmp/raw.pt"})
        with self.assertRaises(storage.ArchiveIntegrityError):
            storage.validate_relative_path("residuals/../escape.safetensors")
        with self.assertRaises(storage.ArchiveIntegrityError):
            storage.validate_relative_path("residuals//shard.safetensors")

    @unittest.skipUnless(
        all(
            importlib.util.find_spec(name) is not None
            for name in ("torch", "safetensors", "pyarrow")
        ),
        "optional RunPod tensor/archive dependencies are not installed",
    )
    def test_bf16_safetensors_and_parquet_round_trip(self) -> None:
        import torch

        run = self.start()
        block = run.begin_block("block-000")
        source = torch.arange(2 * storage.SOURCE_WIDTH, dtype=torch.float32).reshape(
            2, storage.SOURCE_WIDTH
        )
        receipt = block.write_source_shard(
            "event0-l45",
            source,
            [
                {"row_id": "row-a", "capture_state": "l45", "event": "event0"},
                {"row_id": "row-b", "capture_state": "l45", "event": "event0"},
            ],
        )
        self.assertEqual((receipt.rows, receipt.width, receipt.dtype), (2, 8192, "bfloat16"))
        completed_block = block.complete()
        reopened = storage.open_source_shard(completed_block, receipt)
        self.assertEqual(tuple(reopened.shape), (2, storage.SOURCE_WIDTH))
        self.assertEqual(reopened.dtype, torch.bfloat16)
        run.complete()


class PureReadoutTests(unittest.TestCase):
    def test_frozen_vocab_materialization_scope(self) -> None:
        for checkpoint, k in readouts.VOCAB_MATERIALIZATION_K.items():
            readouts.validate_vocab_materialization(
                checkpoint=checkpoint,
                k=k,
                contrast_id="target_minus_matched_sign_oriented",
            )
        self.assertEqual(len(readouts.VOCAB_MATERIALIZATION_K), 7)
        self.assertEqual(len(readouts.FROZEN_VOCAB_CONTRASTS), 7)
        with self.assertRaises(readouts.ReadoutContractError):
            readouts.validate_vocab_materialization(checkpoint="probe8_answer", k=512)
        with self.assertRaises(readouts.ReadoutContractError):
            readouts.validate_vocab_materialization(checkpoint="event0", k=512)
        with self.assertRaises(readouts.ReadoutContractError):
            readouts.validate_vocab_materialization(
                checkpoint="event0", k=2000, contrast_id="invented_after_results"
            )

    def test_dependency_free_reference_fixes_j_transpose_orientation(self) -> None:
        result = readouts.reference_jlens_selected_logits_python(
            [1.0, 2.0],
            [[1.0, 0.0], [1.0, 1.0]],
            [1.0, 2.0],
            [[1.0, 0.0], [0.0, 1.0], [1.0, -1.0]],
            [0, 1, 2],
            eps=1e-6,
        )
        self.assertEqual(result["transported"], [1.0, 3.0])
        scale = 1.0 / math.sqrt(5.0 + 1e-6)
        self.assertAlmostEqual(result["normalized"][0], scale)
        self.assertAlmostEqual(result["normalized"][1], 6.0 * scale)
        self.assertAlmostEqual(result["selected_logits"][2], -5.0 * scale)

    def test_paired_delta_union_retains_both_arm_scores_and_tie_order(self) -> None:
        left = [[2.0, 2.0, 1.0, 4.0, 0.0]]
        right = [[1.0, 1.0, 2.0, 0.0, 1.0]]
        rows = readouts.paired_delta_union_rows(
            left,
            right,
            k=2,
            row_ids=["pair-001"],
            contrast_id="target_amp_minus_never",
        )
        by_id = {row["token_id"]: row for row in rows}
        self.assertEqual(set(by_id), {0, 2, 3, 4})
        self.assertEqual(by_id[3]["positive_rank"], 1)
        # IDs 0 and 1 tie; the lower ID gets the remaining positive slot.
        self.assertEqual(by_id[0]["positive_rank"], 2)
        self.assertEqual(by_id[2]["negative_rank"], 1)
        # IDs 2 and 4 also tie in the negative tail.
        self.assertEqual(by_id[4]["negative_rank"], 2)
        for row in rows:
            self.assertEqual(row["delta"], row["left_score"] - row["right_score"])

    def test_replay_equivalence_checks_numeric_values_ids_and_norms(self) -> None:
        passing = readouts.replay_equivalence_report(
            reference_selected_logits=[[1.0, -2.0]],
            replay_selected_logits=[[1.00001, -2.00001]],
            reference_topk_token_ids=[[4, 9]],
            replay_topk_token_ids=[[4, 9]],
            reference_topk_scores=[[7.0, 6.0]],
            replay_topk_scores=[[7.00001, 6.0]],
            reference_transported_norms=[3.0],
            replay_transported_norms=[3.00001],
            atol=1e-4,
            rtol=0.0,
        )
        self.assertEqual(passing["status"], "pass")
        readouts.assert_replay_equivalent(passing)
        failing = readouts.replay_equivalence_report(
            reference_selected_logits=[[1.0]],
            replay_selected_logits=[[1.0]],
            reference_topk_token_ids=[[4]],
            replay_topk_token_ids=[[5]],
            reference_topk_scores=[[7.0]],
            replay_topk_scores=[[7.0]],
            reference_transported_norms=[3.0],
            replay_transported_norms=[3.0],
            atol=0.0,
            rtol=0.0,
        )
        self.assertEqual(failing["status"], "fail")
        self.assertEqual(failing["topk_token_ids"]["mismatch_count"], 1)
        with self.assertRaises(readouts.ReplayEquivalenceError):
            readouts.assert_replay_equivalent(failing)

    @unittest.skipUnless(
        importlib.util.find_spec("torch") is not None,
        "optional RunPod tensor dependency is not installed",
    )
    def test_torch_batched_selected_and_topk_match_dense_contract(self) -> None:
        import torch

        source = torch.tensor([[1.0, 2.0], [-1.0, 0.5]], dtype=torch.float32)
        jacobian = torch.tensor([[1.0, 0.0], [1.0, 1.0]], dtype=torch.float32)
        norm_weight = torch.tensor([1.0, 2.0], dtype=torch.float32)
        head = torch.tensor(
            [[1.0, 0.0], [1.0, 0.0], [0.0, 1.0], [1.0, -1.0]],
            dtype=torch.float32,
        )
        selected = readouts.jlens_selected_logits(
            source,
            jacobian,
            norm_weight,
            head,
            [0, 2, 3],
            eps=1e-6,
            row_batch_size=1,
        )
        full = readouts.jlens_full_logits(
            source,
            jacobian,
            norm_weight,
            head,
            eps=1e-6,
            row_batch_size=1,
        )
        self.assertTrue(torch.allclose(selected, full[:, [0, 2, 3]]))
        top = readouts.jlens_topk(
            source,
            jacobian,
            norm_weight,
            head,
            eps=1e-6,
            k=3,
            row_batch_size=1,
            vocab_chunk_size=2,
        )
        expected = readouts._stable_topk(
            full,
            torch.arange(head.shape[0]),
            k=3,
            largest=True,
        )
        self.assertTrue(torch.equal(top.token_ids, expected.token_ids))
        self.assertTrue(torch.allclose(top.scores, expected.scores))


if __name__ == "__main__":
    unittest.main()

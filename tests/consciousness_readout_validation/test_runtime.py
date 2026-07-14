from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

from experiments.consciousness_readout_validation import analysis
from experiments.consciousness_readout_validation import paths
from experiments.consciousness_readout_validation import protocol
from experiments.consciousness_readout_validation import runtime
from tests.consciousness_readout_validation.test_analysis import tokenizer_audit_receipt


class RuntimePureHelperTests(unittest.TestCase):
    def test_stable_row_identity_is_study_and_version_bound(self) -> None:
        observed = runtime.stable_row_id("G1", "row")
        expected = runtime.canonical_sha256(
            {
                "study_id": protocol.STUDY_ID,
                "protocol_version": protocol.PROTOCOL_VERSION,
                "parts": ("G1", "row"),
            }
        )[:32]
        self.assertEqual(observed, expected)

    def test_direction_and_random_j_are_reproducible(self) -> None:
        if importlib.util.find_spec("torch") is None:
            self.skipTest("PyTorch is exercised in the pinned GPU environment")
        torch = runtime._torch()
        first = runtime.deterministic_direction(16, layer=45, direction=0)
        second = runtime.deterministic_direction(16, layer=45, direction=0)
        self.assertTrue(torch.equal(first, second))
        self.assertAlmostEqual(runtime.tensor_rms(first), 1.0, places=5)

        source = torch.arange(16, dtype=torch.float32)
        matrix = torch.eye(16, dtype=torch.float32)
        left = runtime.apply_random_j(source, matrix, layer=45, control_index=0)
        right = runtime.apply_random_j(source, matrix, layer=45, control_index=0)
        self.assertTrue(torch.equal(left, right))

    def test_single_use_hook_supports_an_arbitrary_layer_module(self) -> None:
        if importlib.util.find_spec("torch") is None:
            self.skipTest("PyTorch is exercised in the pinned GPU environment")
        torch = runtime._torch()

        class Block(torch.nn.Module):
            def forward(self, hidden):  # type: ignore[no-untyped-def]
                return (hidden + 1.0, "cache")

        block = Block()
        vector = torch.full((8,), 0.25)
        with runtime.SingleUseResidualHook(block, vector, forward_id="fwd") as hook:
            output = block(torch.zeros((1, 1, 8)))
        self.assertEqual(hook.fire_count, 1)
        self.assertTrue(torch.equal(output[0], torch.full((1, 1, 8), 1.25)))
        self.assertEqual(output[1], "cache")
        self.assertIsNotNone(hook.measurement)

    def test_g4_preflight_refuses_any_edit_before_complete_inventory(self) -> None:
        state = runtime.G4PreflightState()
        with self.assertRaises(runtime.PilotRuntimeError) as caught:
            state.begin_edited_forward()
        self.assertEqual(caught.exception.code, "g4_order")

    def test_bfloat16_control_norm_match_is_single_pass_and_within_one_percent(self) -> None:
        if importlib.util.find_spec("torch") is None:
            self.skipTest("PyTorch is exercised in the pinned GPU environment")
        torch = runtime._torch()
        control = torch.tensor([1.0, -2.0, 0.5, 3.0], dtype=torch.bfloat16)
        target = torch.tensor([5.0, -1.0, 2.0, 4.0], dtype=torch.bfloat16)
        matched, scale, raw_norm, final_norm, relative_error = runtime.norm_match_bfloat16(
            control, target
        )
        self.assertEqual(matched.dtype, torch.bfloat16)
        self.assertGreater(scale, 0.0)
        self.assertGreater(raw_norm, 0.0)
        self.assertGreater(final_norm, 0.0)
        self.assertLessEqual(
            relative_error, protocol.G4_CONTROL_NORM_RELATIVE_ERROR_MAX
        )

    def test_g4_decoder_aggregate_uses_frozen_cpu_bfloat16_order(self) -> None:
        if importlib.util.find_spec("torch") is None:
            self.skipTest("PyTorch is exercised in the pinned GPU environment")
        torch = runtime._torch()
        decoder = torch.tensor(
            [
                [0.0, 1.001, 2.002, 3.003],
                [0.0, -4.004, 5.005, -6.006],
                [0.0, 7.007, -8.008, 9.009],
            ],
            dtype=torch.float32,
        )
        observed = runtime.aggregate_decoder_columns_bfloat16(decoder, (3, 1))
        expected = torch.zeros(3, dtype=torch.float32)
        expected.add_(decoder[:, 3].to(torch.bfloat16).float())
        expected.add_(decoder[:, 1].to(torch.bfloat16).float())
        expected = expected.mul_(0.5).to(torch.bfloat16)
        self.assertEqual(observed.device.type, "cpu")
        self.assertEqual(observed.dtype, torch.bfloat16)
        self.assertTrue(torch.equal(observed, expected))
        with self.assertRaises(runtime.PilotRuntimeError):
            runtime.aggregate_decoder_columns_bfloat16(decoder, (1, 1))

    def test_transaction_verifies_then_unwraps_into_g1_analysis(self) -> None:
        plan_hash = "a" * 64
        binding_hash = "b" * 64
        run_id = "runtime-roundtrip"
        token_receipt = tokenizer_audit_receipt()
        token_ids = list(token_receipt["g1"]["accepted_token_ids"])
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / paths.VOLUME_SENTINEL).write_text(
                json.dumps(
                    {
                        "study_slug": protocol.STUDY_SLUG,
                        "study_id": protocol.STUDY_ID,
                        "volume_id": "test-volume",
                    }
                ),
                encoding="utf-8",
            )
            with runtime.PilotTransaction(
                artifact_root=root,
                volume_id="test-volume",
                phase="G1",
                run_id=run_id,
                plan_manifest_sha256=plan_hash,
                execution_binding_canonical_sha256=binding_hash,
            ) as transaction:
                for layer in protocol.G1_MAP_LAYERS:
                    for fixture in protocol.G1_SYNTHETIC_FIXTURES:
                        measurement = {
                            "layer": layer,
                            "synthetic_residual_id": fixture["fixture_id"],
                            "vocab_ids": token_ids,
                            "map_shape_valid": True,
                            "map_finite": True,
                            "production_finite": True,
                            "reference_finite": True,
                            "relative_rmse": 0.0,
                            "selected_logit_sign_agreement": 1.0,
                            "wrong_orientation_differs": True,
                        }
                        transaction.append(
                            "g1_rows.jsonl",
                            {
                                **measurement,
                                "task_id": analysis.expected_measurement_task_id(
                                    "g1_rows.jsonl", measurement
                                ),
                            },
                        )
                final = transaction.complete()
            verified = runtime.verify_completed_transaction(
                final,
                phase="G1",
                run_id=run_id,
                plan_manifest_sha256=plan_hash,
                execution_binding_canonical_sha256=binding_hash,
            )
            receipt = verified["receipt"]
            receipt_core = dict(receipt)
            receipt_hash = receipt_core.pop("receipt_sha256")
            self.assertEqual(receipt_hash, runtime.canonical_sha256(receipt_core))
            self.assertEqual(
                receipt["measurement_files"]["g1_rows.jsonl"]["row_count"], 136
            )

            result = analysis.analyze_g1(
                verified["rows"]["g1_rows.jsonl"],
                tokenizer_audit_receipt=token_receipt,
                lineage_binding={
                    "study_id": protocol.STUDY_ID,
                    "protocol_version": protocol.PROTOCOL_VERSION,
                    "plan_manifest_sha256": plan_hash,
                    "run_id": run_id,
                },
            )
            self.assertEqual(result["status"], "pass")


if __name__ == "__main__":
    unittest.main()

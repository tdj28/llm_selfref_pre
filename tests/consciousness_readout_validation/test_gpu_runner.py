from __future__ import annotations

import importlib.util
import inspect
import math
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from experiments.consciousness_readout_validation import gpu_runner, protocol, runtime


class _CaptureTransaction:
    def __init__(self) -> None:
        self.rows: list[tuple[str, dict[str, object]]] = []

    def append(self, filename: str, row: dict[str, object]) -> None:
        self.rows.append((filename, row))


class GpuRunnerIdentityTests(unittest.TestCase):
    def test_runpod_wrapper_uses_source_hash_barrier_not_git_ownership(self) -> None:
        wrapper = (
            Path(__file__).resolve().parents[2]
            / "experiments/consciousness_readout_validation/run_pilot_runpod.sh"
        ).read_text(encoding="utf-8")
        self.assertNotIn("FREEZE_COMMIT", wrapper)
        self.assertNotIn("git status", wrapper)
        self.assertIn("validate_plan", wrapper)
        self.assertIn('INSTALL_DEPS="${INSTALL_DEPS:-0}"', wrapper)
        self.assertIn(
            'export CUBLAS_WORKSPACE_CONFIG="${EXPECTED_CUBLAS_WORKSPACE_CONFIG}"',
            wrapper,
        )
        self.assertIn('os.environ.get("CUBLAS_WORKSPACE_CONFIG") != ":4096:8"', wrapper)
        self.assertNotIn("consciousness_readout_validation.runtime \\", wrapper)
        self.assertIn(protocol.CONTAINER_IMAGE_SPEC["immutable_reference"], wrapper)
        self.assertIn("--all-phases", wrapper)

    def test_all_phase_run_ids_are_exact_and_deterministic(self) -> None:
        observed = gpu_runner.deterministic_phase_run_ids("pilot-001")
        self.assertEqual(
            observed,
            {phase: f"pilot-001.{phase.lower()}" for phase in protocol.GATE_NAMES},
        )
        with self.assertRaises(runtime.PilotRuntimeError):
            gpu_runner.deterministic_phase_run_ids("x" * 128)

    def test_multi_phase_orchestration_rejects_partial_or_reordered_gate_sets(self) -> None:
        with self.assertRaisesRegex(runtime.PilotRuntimeError, "frozen gate order"):
            gpu_runner.run_bound_phases(
                phases=("G2", "G1"),
                run_ids={"G2": "x.g2", "G1": "x.g1"},
                plan_manifest_path=Path("/unused"),
                execution_binding_path=Path("/unused"),
                artifact_root=Path("/unused"),
                volume_id="unused",
            )

    def test_task_id_uses_frozen_kind_and_key_contract(self) -> None:
        key = ("neutral_01", 45, 0, "real_j")
        self.assertEqual(
            gpu_runner.measurement_task_id("g2_transport", key),
            protocol.stable_id(
                "measurement",
                {"measurement_kind": "g2_transport", "key": list(key)},
            ),
        )

    def test_j_lens_checkpoint_requires_exact_public_fit_count(self) -> None:
        checkpoint = {
            "J": {45: object()},
            "n_prompts": 125,
            "d_model": protocol.MODEL_SPEC["residual_width"],
        }
        self.assertIs(
            gpu_runner.validate_j_lens_checkpoint_metadata(checkpoint),
            checkpoint["J"],
        )
        with self.assertRaisesRegex(runtime.PilotRuntimeError, "fit count"):
            gpu_runner.validate_j_lens_checkpoint_metadata(
                {**checkpoint, "n_prompts": 124}
            )

    def test_sae_layout_requires_all_four_exact_tensor_shapes(self) -> None:
        class Shaped:
            def __init__(self, shape):  # type: ignore[no-untyped-def]
                self.shape = shape

        state = {
            "encoder_linear.weight": Shaped((65536, 8192)),
            "encoder_linear.bias": Shaped((65536,)),
            "decoder_linear.weight": Shaped((8192, 65536)),
            "decoder_linear.bias": Shaped((8192,)),
        }
        self.assertEqual(set(gpu_runner.resolve_sae_state(state)), set(state))
        with self.assertRaisesRegex(runtime.PilotRuntimeError, "decoder_linear.bias"):
            gpu_runner.resolve_sae_state(
                {**state, "decoder_linear.bias": Shaped((65536,))}
            )
        with self.assertRaisesRegex(runtime.PilotRuntimeError, "exactly the four"):
            gpu_runner.resolve_sae_state({**state, "unexpected": Shaped((1,))})

    def test_determinism_settings_are_validated_not_only_receipted(self) -> None:
        expected = gpu_runner.expected_determinism_settings()
        self.assertEqual(expected["cublas_workspace_config"], ":4096:8")
        gpu_runner.validate_determinism_settings(expected)
        with self.assertRaisesRegex(runtime.PilotRuntimeError, "deterministic CUDA"):
            gpu_runner.validate_determinism_settings(
                {**expected, "flash_sdp_enabled": True}
            )

    def test_append_supplies_task_but_leaves_row_id_to_transaction_contract(self) -> None:
        transaction = _CaptureTransaction()
        gpu_runner.append_measurement(  # type: ignore[arg-type]
            transaction,
            "g4_clean_rows.jsonl",
            kind="g4_clean",
            key=("neutral_01",),
            measurement={"prompt_id": "neutral_01", "h50_pre_rms": 1.0, "finite": True},
        )
        _filename, row = transaction.rows[0]
        self.assertIn("task_id", row)
        self.assertNotIn("row_id", row)

    def test_phase_binding_is_exactly_self_hashed(self) -> None:
        token_core = {
            "tokenizer_inventory_sha256": "1" * 64,
        }
        token = {**token_core, "receipt_sha256": protocol.canonical_sha256(token_core)}
        receipt = gpu_runner.phase_binding_receipt(
            phase="G1",
            run_id="fake",
            plan_manifest_sha256="2" * 64,
            execution_binding={"execution_binding_canonical_sha256": "3" * 64},
            token_receipt=token,
        )
        digest = receipt.pop("receipt_sha256")
        self.assertEqual(digest, protocol.canonical_sha256(receipt))

    def test_runtime_receipt_binds_exact_hook_contract(self) -> None:
        class Backend:
            def runtime_metadata(self):  # type: ignore[no-untyped-def]
                return {
                    "container_image": protocol.CONTAINER_IMAGE_SPEC,
                    "hardware": {},
                    "software": {},
                    "determinism": gpu_runner.expected_determinism_settings(),
                    "model_forward_count": 0,
                    "first_model_forward_at_utc": None,
                    "last_model_forward_at_utc": None,
                }

        receipt = gpu_runner.runtime_metadata_receipt(
            Backend(),  # type: ignore[arg-type]
            phase="G1",
            run_id="fake",
            plan_manifest_sha256="1" * 64,
            execution_binding={"execution_binding_canonical_sha256": "2" * 64},
            token_receipt={"receipt_sha256": "3" * 64},
        )
        self.assertEqual(receipt["hook_contract"], protocol.HOOK_CONTRACT)
        core = dict(receipt)
        digest = core.pop("receipt_sha256")
        self.assertEqual(digest, protocol.canonical_sha256(core))

    def test_g4_uses_one_device_aligned_requested_vector_for_all_comparisons(self) -> None:
        source = inspect.getsource(gpu_runner.execute_g4)
        self.assertEqual(source.count("requested_vector = vector.vector.to("), 1)
        self.assertIn("+ requested_vector", source)
        self.assertIn("realized, requested_vector", source)
        self.assertNotIn("realized, vector.vector", source)

    def test_all_phase_orchestration_loads_and_validates_once(self) -> None:
        events: list[str] = []
        transactions: dict[str, object] = {}

        class FakeTransaction:
            def __init__(self, **kwargs):  # type: ignore[no-untyped-def]
                self.phase = kwargs["phase"]
                self.run_id = kwargs["run_id"]
                self.closed = False
                self.final = Path("/fake") / self.phase
                self.metadata: dict[str, object] = {}
                transactions[self.phase] = self

            def write_metadata(self, filename, value):  # type: ignore[no-untyped-def]
                events.append(f"metadata:{self.phase}:{filename}")
                self.metadata[filename] = value

            def complete(self):  # type: ignore[no-untyped-def]
                events.append(f"complete:{self.phase}")
                self.closed = True
                return self.final

            def fail(self, exc):  # type: ignore[no-untyped-def]
                del exc
                self.closed = True

        class FakeBackend:
            load_count = 0
            close_count = 0

            def __init__(self, **kwargs):  # type: ignore[no-untyped-def]
                del kwargs
                type(self).load_count += 1
                self.forward_count = 0
                events.append("backend:load")

            def start_runtime_interval(self):  # type: ignore[no-untyped-def]
                self.forward_count = 0

            def close(self):  # type: ignore[no-untyped-def]
                type(self).close_count += 1

        token_core = {"tokenizer_inventory_sha256": "a" * 64}
        token_receipt = {
            **token_core,
            "receipt_sha256": protocol.canonical_sha256(token_core),
        }
        binding = {
            "resolved_external_root_id": "volume",
            "execution_binding_canonical_sha256": "b" * 64,
            "tokenizer_content_inventory_sha256": "a" * 64,
            "tokenizer_audit_receipt_sha256": token_receipt["receipt_sha256"],
            "artifacts": {"sae": {"sha256": "c" * 64}},
        }

        def fake_execute(phase, backend, *args, **kwargs):  # type: ignore[no-untyped-def]
            del args, kwargs
            if phase != "G1":
                backend.forward_count += 1

        def fake_runtime_receipt(backend, **kwargs):  # type: ignore[no-untyped-def]
            return {
                "phase": kwargs["phase"],
                "model_forward_count": backend.forward_count,
            }

        validation = patch.object(
            runtime, "_load_plan_manifest", return_value=({}, "d" * 64)
        )
        load_binding = patch.object(runtime, "load_execution_binding", return_value=binding)
        artifacts = patch.object(
            runtime,
            "validate_local_artifact_binding",
            return_value={
                "model_snapshot": Path("/model"),
                "sae": Path("/sae"),
                "j_lens": Path("/j"),
            },
        )
        tokenization = patch.object(
            runtime, "tokenizer_preflight", return_value=(object(), token_receipt)
        )
        transaction_factory = patch.object(runtime, "PilotTransaction", FakeTransaction)
        verification = patch.object(
            runtime,
            "verify_completed_transaction",
            return_value={"receipt": {"receipt_sha256": "e" * 64}},
        )
        with (
            validation as validate_mock,
            load_binding as binding_mock,
            artifacts as artifact_mock,
            tokenization as tokenizer_mock,
            transaction_factory,
            verification,
            patch.object(gpu_runner, "_assert_bound_adapter_source"),
            patch.object(gpu_runner, "_execute_phase", side_effect=fake_execute),
            patch.object(
                gpu_runner,
                "runtime_metadata_receipt",
                side_effect=fake_runtime_receipt,
            ),
        ):
            receipt = gpu_runner.run_bound_phases(
                phases=protocol.GATE_NAMES,
                run_ids=gpu_runner.deterministic_phase_run_ids("pilot"),
                plan_manifest_path=Path("/plan"),
                execution_binding_path=Path("/binding"),
                artifact_root=Path("/artifacts"),
                volume_id="volume",
                backend_type=FakeBackend,  # type: ignore[arg-type]
            )

        self.assertEqual(validate_mock.call_count, 1)
        self.assertEqual(binding_mock.call_count, 1)
        self.assertEqual(artifact_mock.call_count, 1)
        self.assertEqual(tokenizer_mock.call_count, 1)
        self.assertEqual(FakeBackend.load_count, 1)
        self.assertEqual(FakeBackend.close_count, 1)
        self.assertEqual(receipt["backend_load_count"], 1)
        load_offset = events.index("backend:load")
        self.assertEqual(
            sum(event.endswith("PHASE_BINDING.json") for event in events[:load_offset]),
            len(protocol.GATE_NAMES),
        )
        g1_transaction = transactions["G1"]
        self.assertEqual(  # type: ignore[attr-defined]
            g1_transaction.metadata["RUNTIME_METADATA.json"]["model_forward_count"],
            0,
        )


class G4MatchingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        # The real-size fixture is intentional: it proves no hidden small-table
        # behavior changes the 65,536-feature greedy matcher.
        cls.statistics = [
            {
                "feature_id": feature_id,
                "decoder_l2_norm": 1.0 + feature_id / 100_000.0,
                "mean_positive_activation": (feature_id % 101) / 100.0,
                "max_positive_activation": 1.0 + (feature_id % 211) / 100.0,
                "positive_activation_fraction": (feature_id % 97) / 100.0,
            }
            for feature_id in range(protocol.SAE_SPEC["feature_count"])
        ]

    def test_full_matching_table_is_deterministic_unique_and_target_disjoint(self) -> None:
        table_a, mapping_a, ids_a = gpu_runner.resolve_g4_matches(self.statistics)
        table_b, mapping_b, ids_b = gpu_runner.resolve_g4_matches(self.statistics)
        self.assertEqual(mapping_a, mapping_b)
        self.assertEqual(ids_a, ids_b)
        self.assertEqual(len(table_a), 65_536)
        self.assertEqual(len(table_b), 65_536)
        self.assertEqual(len(set(ids_a)), 6)
        self.assertFalse(set(ids_a) & set(protocol.G4_TARGET_FEATURE_IDS))
        self.assertEqual(
            [row["target_feature_id"] for row in mapping_a],
            list(protocol.G4_TARGET_FEATURE_IDS),
        )


@unittest.skipUnless(importlib.util.find_spec("torch"), "fake tensor phases need PyTorch")
class FakeTensorPhaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.torch = runtime._torch()

    def test_g1_component_reference_matches_matrix_vector_product(self) -> None:
        torch = self.torch
        source = torch.arange(8, dtype=torch.float32)
        matrix = torch.arange(64, dtype=torch.float32).reshape(8, 8).to(torch.bfloat16)
        observed = gpu_runner.independent_component_transport(source, matrix, chunk=3)
        expected = source.to(torch.bfloat16).float() @ matrix.float().T
        self.assertTrue(torch.allclose(observed, expected, atol=1e-5, rtol=1e-5))

    def test_g2_fake_transport_measurement(self) -> None:
        torch = self.torch

        class Backend:
            device = torch.device("cpu")

            def transport_state(self, source, *, layer, transport):  # type: ignore[no-untyped-def]
                del layer, transport
                return source.float()

            def logits_from_final_state(self, state, token_ids):  # type: ignore[no-untyped-def]
                return state.float()[list(token_ids)]

        clean = gpu_runner.CleanTrace(
            input_token_ids=(1, 2),
            input_token_ids_sha256="0" * 64,
            residual_by_layer={45: torch.zeros(4)},
            final_residual=torch.zeros(4),
            logits=torch.zeros(4),
        )
        session = type("Session", (), {"clean": clean})()
        vector = torch.tensor([1.0, -1.0, 0.5, -0.5])
        pair = gpu_runner.PerturbationPair(0.02, vector, vector.clone(), vector[:2].clone())
        result = gpu_runner.g2_transport_measurement(
            Backend(), session, pair, layer=45, transport="real_j", selected_token_ids=(0, 1)
        )
        self.assertAlmostEqual(result["residual_delta_cosine"], 1.0, places=6)
        self.assertAlmostEqual(result["fixed_token_logit_delta_pearson"], 1.0, places=6)

    def test_g3_and_g3p_fake_readout_share_exact_transport_path(self) -> None:
        torch = self.torch

        class Backend:
            def transport_state(self, source, *, layer, transport):  # type: ignore[no-untyped-def]
                del layer, transport
                return source * 2

            def logits_from_final_state(self, state, token_ids):  # type: ignore[no-untyped-def]
                return state[list(token_ids)]

        observed = gpu_runner._readout_logits(
            Backend(), torch.tensor([1.0, 2.0, 3.0]), layer=45, transport="real_j", token_ids=(0, 2)
        )
        self.assertTrue(torch.equal(observed, torch.tensor([2.0, 6.0])))

    def test_g4_exact_bfloat16_post_gate(self) -> None:
        torch = self.torch
        pre = torch.tensor([1.0, -2.0], dtype=torch.bfloat16)
        vector = torch.tensor([0.25, 0.5], dtype=torch.bfloat16)
        expected = (pre + vector).to(torch.bfloat16)
        self.assertEqual(runtime.tensor_sha256(expected), runtime.tensor_sha256(pre + vector))

    @unittest.skipUnless(
        importlib.util.find_spec("torch") and runtime._torch().cuda.is_available(),
        "CUDA is required for the cross-device G4 regression test",
    )
    def test_g4_requested_vector_metrics_share_cuda_device(self) -> None:
        torch = self.torch
        pre = torch.tensor([1.0, -2.0], dtype=torch.bfloat16, device="cuda")
        requested_vector = torch.tensor(
            [0.25, 0.5], dtype=torch.bfloat16, device="cpu"
        ).to(device=pre.device, dtype=torch.bfloat16)
        post = (pre + requested_vector).to(torch.bfloat16)
        realized = post.float() - pre.float()
        self.assertEqual(requested_vector.device, realized.device)
        self.assertEqual(runtime.relative_rmse(realized, requested_vector), 0.0)
        self.assertAlmostEqual(
            runtime.cosine_similarity(realized, requested_vector), 1.0, places=6
        )


if __name__ == "__main__":
    unittest.main()

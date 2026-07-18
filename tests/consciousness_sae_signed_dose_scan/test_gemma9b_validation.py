from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from experiments.consciousness_sae_signed_dose_scan import (
    gemma9b_validation as validation,
)
from experiments.consciousness_sae_signed_dose_scan import (
    gemma9b_validation_audit as audit,
)
from experiments.consciousness_sae_signed_dose_scan import authorize


TORCH_AVAILABLE = importlib.util.find_spec("torch") is not None


class FrozenOperationalContractTests(unittest.TestCase):
    def test_grid_is_exact_signed_half_point_scan_with_one_clean_zero(self) -> None:
        self.assertEqual(validation.DOSE_BASIS_POINTS, tuple(range(50, 3_001, 50)))
        self.assertEqual(len(validation.DOSE_BASIS_POINTS), 60)
        self.assertNotIn(0, validation.DOSE_BASIS_POINTS)
        self.assertEqual(validation.SIGNS, ("plus", "minus"))
        self.assertEqual(validation.EXPECTED_EDITED_FORWARDS, 120)
        self.assertEqual(validation.EXPECTED_MODEL_FORWARDS, 122)
        validation.validate_frozen_contract()

    def test_identity_is_actual_pinned_gemma_scope_decoder_row(self) -> None:
        self.assertEqual(validation.FROZEN_FEATURE_ID, 1_295)
        self.assertEqual(validation.FROZEN_SAE_LAYER, 20)
        self.assertEqual(validation.FROZEN_SAE_WIDTH, 16_384)
        self.assertEqual(
            validation.FROZEN_SAE_FOLDER,
            "layer_20/width_16k/average_l0_91",
        )
        self.assertEqual(validation.RESIDUAL_WIDTH, 3_584)
        self.assertEqual(len(validation.ARC_LABELS), 43)

    def test_raw_output_is_rejected_off_network_volume(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaisesRegex(validation.ValidationError, "network volume"):
                validation.validate_remote_outdir(Path(temporary) / "run")

    def test_incomplete_artifact_cannot_promote(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            report = audit.audit_run(Path(temporary))
        self.assertEqual(report["status"], "fail_small_model_promotion_gate")
        self.assertFalse(report["promotion"]["pass"])
        self.assertFalse(report["promotion"]["semantic_outcome_gate"])
        self.assertFalse(report["promotion"]["effect_size_gate"])
        self.assertFalse(report["promotion"]["dose_threshold_tuning_gate"])
        self.assertFalse(report["promotion"]["scientific_claims_authorized"])
        self.assertEqual(report["nonzero_dose_count"], 60)
        self.assertEqual(report["signed_pair_count"], 60)
        self.assertEqual(report["edited_forward_count"], 120)
        self.assertEqual(report["zero_baseline_count"], 1)
        self.assertEqual(report["sae_repo"], "google/gemma-scope-9b-it-res")
        self.assertEqual(
            report["sae_revision"],
            "e86af97a5b6fbbccca28ab654f2fda1b0768f770",
        )
        self.assertEqual(
            report["sae_folder"], "layer_20/width_16k/average_l0_91"
        )
        self.assertEqual(report["sae_feature_id"], 1_295)
        self.assertEqual(
            report["required_gates"],
            ["structural", "numeric", "hook", "artifact_replay"],
        )
        self.assertEqual(
            report["promotion_scope"],
            "runner_mechanics_only_not_scientific_protocol",
        )
        self.assertEqual(
            report["dose_basis_points_sha256"],
            audit.canonical_sha256(list(range(50, 3_001, 50))),
        )
        core = dict(report)
        supplied = core.pop("receipt_sha256")
        self.assertEqual(supplied, audit.canonical_sha256(core))

    def test_passing_audit_emits_authorizer_compatible_canonical_receipt(self) -> None:
        dummy_context = object()
        with tempfile.TemporaryDirectory() as temporary, mock.patch.object(
            audit,
            "structural_gate",
            return_value=(dummy_context, {"checked": True}),
        ), mock.patch.object(
            audit, "numeric_gate", return_value={"checked": True}
        ), mock.patch.object(
            audit, "hook_gate", return_value={"checked": True}
        ), mock.patch.object(
            audit, "artifact_replay_gate", return_value={"checked": True}
        ):
            report = audit.audit_run(Path(temporary))
            output = Path(temporary) / "AUDIT.json"
            audit._atomic_write_json(output, report)
            self.assertEqual(
                output.read_bytes(), audit.canonical_json_bytes(report) + b"\n"
            )
            consumed, consumed_path = authorize._small_gate(output)
            self.assertEqual(consumed_path, output)
            self.assertEqual(
                consumed["receipt_sha256"], report["receipt_sha256"]
            )
        self.assertEqual(report["status"], "pass_small_model_promotion_gate")
        self.assertTrue(report["promotion"]["pass"])
        self.assertEqual(report["model_id"], "google/gemma-2-9b-it")
        self.assertEqual(
            report["model_revision"],
            "11c9b309abf73637e4b6f9a3fa1e92e615547819",
        )
        self.assertEqual(report["sae_feature_id"], 1_295)
        self.assertEqual(report["required_gates"], list(audit.EXPECTED_GATES))
        core = dict(report)
        supplied = core.pop("receipt_sha256")
        self.assertEqual(supplied, audit.canonical_sha256(core))


@unittest.skipUnless(TORCH_AVAILABLE, "torch is required for BF16 runtime tests")
class TorchOperationalTests(unittest.TestCase):
    def setUp(self) -> None:
        import torch

        self.torch = torch

    def test_requested_vectors_are_cpu_replayable_exact_signed_pairs(self) -> None:
        decoder = self.torch.tensor(
            [1.0, -2.0, 3.0, -4.0, 2.0, -1.0, 0.5, -0.5],
            dtype=self.torch.bfloat16,
        )
        unit, fp32, bfloat16 = validation.requested_vectors(
            torch_module=self.torch,
            decoder_row_bfloat16=decoder,
            clean_source_rms=2.0,
        )
        self.assertEqual(tuple(fp32.shape), (60, 8))
        self.assertEqual(tuple(bfloat16.shape), (60, 8))
        self.assertEqual(unit.dtype, self.torch.float32)
        self.assertEqual(bfloat16.dtype, self.torch.bfloat16)
        self.assertAlmostEqual(validation.rms(unit), 1.0, places=6)
        expected_first = (unit * (2.0 * 50 / 10_000)).to(self.torch.bfloat16)
        self.assertTrue(self.torch.equal(bfloat16[0], expected_first))
        self.assertTrue(
            self.torch.equal(self.torch.neg(bfloat16), -bfloat16)
        )

    def test_decoder_row_is_read_from_exact_npz_coordinate(self) -> None:
        import numpy as np

        decoder = np.arange(24, dtype=np.float32).reshape(3, 8)
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "params.npz"
            np.savez(path, w_dec=decoder)
            row = validation.decoder_row_from_npz(
                torch_module=self.torch,
                params_path=path,
                feature_id=1,
                expected_d_sae=3,
                expected_d_in=8,
            )
        self.assertEqual(row.dtype, self.torch.bfloat16)
        self.assertTrue(
            self.torch.equal(
                row,
                self.torch.from_numpy(decoder[1]).to(self.torch.bfloat16),
            )
        )

    def test_arc_session_captures_pre_post_full_arc_and_single_hook(self) -> None:
        torch = self.torch

        class AddBlock(torch.nn.Module):
            def __init__(self, amount: float) -> None:
                super().__init__()
                self.amount = amount

            def forward(self, hidden):  # type: ignore[no-untyped-def]
                return (hidden + self.amount).to(torch.bfloat16)

        class TinyBackbone(torch.nn.Module):
            def __init__(self) -> None:
                super().__init__()
                self.layers = torch.nn.ModuleList(
                    [AddBlock(0.25), AddBlock(0.5), AddBlock(0.75)]
                )
                self.norm = torch.nn.Identity()

        class TinyModel(torch.nn.Module):
            def __init__(self) -> None:
                super().__init__()
                self.model = TinyBackbone()
                self.device = torch.device("cpu")

            def forward(
                self,
                *,
                input_ids,
                past_key_values=None,
                use_cache=False,
                return_dict=True,
            ):  # type: ignore[no-untyped-def]
                hidden = input_ids.to(torch.bfloat16).unsqueeze(-1).repeat(1, 1, 8)
                for layer in self.model.layers:
                    hidden = layer(hidden)
                self.model.norm(hidden)
                cache = (
                    (torch.zeros(1, dtype=torch.bfloat16),)
                    if use_cache
                    else past_key_values
                )
                return SimpleNamespace(past_key_values=cache)

        session = validation.GemmaArcSession(
            torch_module=torch,
            model=TinyModel(),
            token_ids=(1, 2, 3),
            capture_layers=(0, 1, 2),
            residual_width=8,
            edit_layer=1,
        )
        try:
            clean = session.clean()
            vector = torch.full((8,), 0.25, dtype=torch.bfloat16)
            edited = session.edited(vector, forward_id="tiny-plus")
        finally:
            session.close()
        self.assertEqual(clean.hook_fire_count, 0)
        self.assertEqual(edited.hook_fire_count, 1)
        self.assertEqual(tuple(clean.arc_bfloat16.shape), (4, 8))
        self.assertTrue(torch.equal(edited.arc_bfloat16[:2], clean.arc_bfloat16[:2]))
        self.assertTrue(torch.equal(edited.pre_bfloat16, clean.arc_bfloat16[1]))
        self.assertTrue(
            torch.equal(
                edited.post_bfloat16,
                (edited.pre_bfloat16 + vector).to(torch.bfloat16),
            )
        )

    def _synthetic_context(self) -> audit.AuditContext:
        torch = self.torch
        width = 8
        clean = torch.ones((43, width), dtype=torch.bfloat16)
        decoder = torch.ones(width, dtype=torch.bfloat16)
        unit, fp32, requested = validation.requested_vectors(
            torch_module=torch,
            decoder_row_bfloat16=decoder,
            clean_source_rms=1.0,
        )
        plus_pre = clean[20].repeat(60, 1).contiguous()
        minus_pre = clean[20].repeat(60, 1).contiguous()
        plus_post = (plus_pre + requested).to(torch.bfloat16).contiguous()
        minus_vectors = torch.neg(requested).contiguous()
        minus_post = (minus_pre + minus_vectors).to(torch.bfloat16).contiguous()
        plus_arcs = clean.unsqueeze(0).repeat(60, 1, 1).contiguous()
        minus_arcs = clean.unsqueeze(0).repeat(60, 1, 1).contiguous()
        rows, pairs = validation.build_telemetry_rows(
            torch_module=torch,
            clean_arc=clean,
            requested_bfloat16=requested,
            plus_arcs=plus_arcs,
            minus_arcs=minus_arcs,
            plus_pre=plus_pre,
            plus_post=plus_post,
            minus_pre=minus_pre,
            minus_post=minus_post,
            plus_hook_vectors=requested,
            minus_hook_vectors=minus_vectors,
            hook_counts_plus=[1] * 60,
            hook_counts_minus=[1] * 60,
        )
        tensors = {
            "clean_arc_bfloat16": clean,
            "decoder_row_bfloat16": decoder,
            "unit_direction_float32": unit,
            "requested_positive_float32": fp32,
            "requested_positive_bfloat16": requested,
            "plus_arc_bfloat16": plus_arcs,
            "minus_arc_bfloat16": minus_arcs,
            "plus_pre_bfloat16": plus_pre,
            "plus_post_bfloat16": plus_post,
            "minus_pre_bfloat16": minus_pre,
            "minus_post_bfloat16": minus_post,
            "plus_hook_vector_bfloat16": requested,
            "minus_hook_vector_bfloat16": minus_vectors,
        }
        return audit.AuditContext(
            run_dir=Path("/workspace/synthetic-not-a-production-run"),
            manifest={"intervention": {"clean_source_rms": 1.0}},
            rows=rows,
            pairs=pairs,
            tensors=tensors,
        )

    def test_independent_numeric_hook_and_replay_gates_accept_exact_fixture(self) -> None:
        context = self._synthetic_context()
        numeric = audit.numeric_gate(context)
        hook = audit.hook_gate(context)
        replay = audit.artifact_replay_gate(context)
        self.assertTrue(numeric["all_tensors_finite"])
        self.assertFalse(numeric["empirical_fidelity_threshold_applied"])
        self.assertTrue(hook["all_native_bfloat16_additions_byte_exact"])
        self.assertEqual(replay["signed_rows_replayed"], 120)
        self.assertFalse(replay["semantic_outcomes_consulted"])

    def test_independent_replay_rejects_telemetry_tampering(self) -> None:
        context = self._synthetic_context()
        rows = [dict(row) for row in context.rows]
        rows[0]["realized_rms_fraction"] += 0.25
        tampered = audit.AuditContext(
            run_dir=context.run_dir,
            manifest=context.manifest,
            rows=rows,
            pairs=context.pairs,
            tensors=context.tensors,
        )
        with self.assertRaisesRegex(audit.AuditError, "row metric differs"):
            audit.artifact_replay_gate(tampered)

    def test_hook_gate_rejects_false_hook_receipt(self) -> None:
        context = self._synthetic_context()
        rows = [dict(row) for row in context.rows]
        rows[7]["hook_fire_count"] = 0
        tampered = audit.AuditContext(
            run_dir=context.run_dir,
            manifest=context.manifest,
            rows=rows,
            pairs=context.pairs,
            tensors=context.tensors,
        )
        with self.assertRaisesRegex(audit.AuditError, "hook count differs"):
            audit.hook_gate(tampered)

    def test_runner_and_auditor_tensor_hashes_are_independent_and_identical(self) -> None:
        tensor = self.torch.tensor(
            [[1.0, -2.0], [3.5, 0.0]], dtype=self.torch.bfloat16
        )
        from experiments.consciousness_sae_realization_validation.runtime import (
            tensor_sha256,
        )

        self.assertEqual(tensor_sha256(tensor), audit._tensor_sha256(tensor))


if __name__ == "__main__":
    unittest.main()

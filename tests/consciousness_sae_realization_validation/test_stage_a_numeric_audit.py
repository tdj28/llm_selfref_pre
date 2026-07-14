from __future__ import annotations

import copy
import tempfile
import unittest
from pathlib import Path

try:
    import torch
except ImportError:  # exercised in the pinned GPU/runtime environment
    torch = None  # type: ignore[assignment]

from experiments.consciousness_sae_realization_validation import audit
from experiments.consciousness_sae_realization_validation import controls
from experiments.consciousness_sae_realization_validation import gate_receipts
from experiments.consciousness_sae_realization_validation import protocol
from experiments.consciousness_sae_realization_validation import runtime


def _pair_fixture() -> tuple[torch.Tensor, torch.Tensor, torch.Tensor, dict[str, torch.Tensor]]:
    width = 8
    clean_states = (
        torch.arange((len(protocol.J_LAYERS) + 1) * width, dtype=torch.float32)
        .reshape(len(protocol.J_LAYERS) + 1, width)
        .div(32.0)
        .add(1.0)
        .to(dtype=torch.bfloat16)
    )
    edit_layer = protocol.SAE_LAYER
    source_index = protocol.J_LAYERS.index(edit_layer)
    post_index = len(protocol.J_LAYERS)
    final_index = post_index + 1
    requested_fp32 = torch.tensor(
        [0.125, -0.25, 0.5, -0.125, 0.25, -0.5, 0.375, -0.375],
        dtype=torch.float32,
    )
    requested = requested_fp32.to(dtype=torch.bfloat16)
    plus_states = torch.empty(protocol.STAGE_A_CAPTURE_COUNT, width, dtype=torch.bfloat16)
    minus_states = torch.empty_like(plus_states)
    plus_states[: len(protocol.J_LAYERS)] = clean_states[:-1]
    minus_states[: len(protocol.J_LAYERS)] = clean_states[:-1]
    clean_source = clean_states[source_index]
    plus_states[post_index] = (clean_source + requested).to(dtype=torch.bfloat16)
    minus_states[post_index] = (clean_source - requested).to(dtype=torch.bfloat16)
    final_delta = torch.tensor(
        [0.5, -0.25, 0.125, -0.5, 0.25, 0.375, -0.125, 0.625],
        dtype=torch.bfloat16,
    )
    plus_states[final_index] = (clean_states[-1] + final_delta).to(
        dtype=torch.bfloat16
    )
    minus_states[final_index] = (clean_states[-1] - final_delta).to(
        dtype=torch.bfloat16
    )
    realized_plus = plus_states[post_index].float() - clean_source.float()
    realized_minus = minus_states[post_index].float() - clean_source.float()
    central = (plus_states[post_index].float() - minus_states[post_index].float()) * 0.5
    common = (
        (plus_states[post_index].float() + minus_states[post_index].float()) * 0.5
        - clean_source.float()
    )
    final_central = (
        plus_states[final_index].float() - minus_states[final_index].float()
    ) * 0.5
    bf16_j = torch.tensor(
        [0.25, 0.5, -0.25, 0.75, -0.5, 0.375, 0.625, -0.125],
        dtype=torch.bfloat16,
    )
    fp32_j = bf16_j.float() * 1.001
    transports = [bf16_j, central.to(dtype=torch.bfloat16)]
    for index in range(protocol.RANDOM_J_COUNT):
        transports.append(
            torch.roll(bf16_j, shifts=index + 1).to(dtype=torch.bfloat16)
        )
    actual_logits = torch.tensor(
        [-3.0, -1.0, 0.5, 2.0, 4.0, 3.0, -2.0, 1.0], dtype=torch.float32
    )
    predicted_logits = torch.stack(
        [
            actual_logits * (1.0 + 0.05 * index)
            + torch.roll(actual_logits, shifts=index + 1) * 0.01
            for index in range(len(protocol.TRANSPORTS))
        ]
    )
    arithmetic = {
        "requested_fp32_positive": requested_fp32.unsqueeze(0),
        "requested_bfloat16_positive": requested.unsqueeze(0),
        "realized_plus_fp32": realized_plus.unsqueeze(0),
        "realized_minus_fp32": realized_minus.unsqueeze(0),
        "realized_central_fp32": central.unsqueeze(0),
        "common_mode_fp32": common.unsqueeze(0),
        "final_central_fp32": final_central.unsqueeze(0),
        "bf16_j_prediction_bfloat16": bf16_j.unsqueeze(0),
        "fp32_j_prediction_fp32": fp32_j.unsqueeze(0),
        "transport_predicted_bfloat16": torch.stack(transports).unsqueeze(0),
        "actual_selected_logit_delta_fp32": actual_logits.unsqueeze(0),
        "transport_predicted_selected_logit_delta_fp32": predicted_logits.unsqueeze(0),
    }
    return clean_states, plus_states, minus_states, arithmetic


class StageANumericAuditTests(unittest.TestCase):
    def _recomputed(self):
        clean, plus, minus, arithmetic = _pair_fixture()
        rows = audit._recompute_stage_a_pair_telemetry(
            clean_states=clean,
            plus_states=plus,
            minus_states=minus,
            edit_layer=protocol.SAE_LAYER,
            arithmetic=arithmetic,
            arithmetic_row=0,
        )
        return clean, plus, minus, arithmetic, rows

    def test_rejects_resealed_realization_j_shadow_and_transport_metrics(self) -> None:
        if torch is None:
            cases = tuple(
                (
                    {"family": label, field: 0.25, "finite": True},
                    field,
                    (field,),
                    label,
                )
                for label, field in (
                    ("realization", "requested_realized_central_relative_rmse"),
                    ("J-shadow", "bf16_fp32_j_relative_rmse"),
                    ("transport", "fixed_token_logit_delta_pearson"),
                )
            )
        else:
            _, _, _, _, (realization, shadow, transports, _) = self._recomputed()
            cases = (
                (
                    realization,
                    "requested_realized_central_relative_rmse",
                    (
                        "requested_plus_realized_relative_rmse",
                        "requested_minus_realized_relative_rmse",
                        "requested_realized_central_relative_rmse",
                        "requested_realized_central_cosine",
                        "common_mode_to_central_rms",
                        "requested_rms_fraction",
                        "realized_rms_fraction",
                        "bf16_fp32_j_cosine",
                        "bf16_fp32_j_relative_rmse",
                        "fp32_j_actual_final_cosine",
                    ),
                    "realization",
                ),
                (
                    shadow,
                    "bf16_fp32_j_relative_rmse",
                    (
                        "bf16_fp32_j_cosine",
                        "bf16_fp32_j_relative_rmse",
                        "fp32_j_actual_final_cosine",
                    ),
                    "J-shadow",
                ),
                (
                    transports[0],
                    "fixed_token_logit_delta_pearson",
                    ("residual_delta_cosine", "fixed_token_logit_delta_pearson"),
                    "transport",
                ),
            )
        for recomputed, field, numeric_fields, label in cases:
            with self.subTest(label=label):
                reported = dict(recomputed)
                reported[field] = float(reported[field]) + 0.05
                with self.assertRaisesRegex(audit.AuditError, "numeric telemetry differs"):
                    audit._require_stage_a_row_match(
                        reported,
                        recomputed,
                        numeric_fields=numeric_fields,
                        label=label,
                    )

    @unittest.skipIf(torch is None, "torch is unavailable in the lightweight control environment")
    def test_rejects_raw_arithmetic_that_disagrees_with_residual_states(self) -> None:
        clean, plus, minus, arithmetic = _pair_fixture()
        tampered = dict(arithmetic)
        tampered["realized_central_fp32"] = arithmetic[
            "realized_central_fp32"
        ].clone()
        tampered["realized_central_fp32"][0, 0] += 1.0
        with self.assertRaisesRegex(audit.AuditError, "realized central"):
            audit._recompute_stage_a_pair_telemetry(
                clean_states=clean,
                plus_states=plus,
                minus_states=minus,
                edit_layer=protocol.SAE_LAYER,
                arithmetic=tampered,
                arithmetic_row=0,
            )

    @unittest.skipIf(torch is None, "torch is unavailable in the lightweight control environment")
    def test_runtime_bf16_j_hash_survives_runner_archive_and_audit_join(self) -> None:
        class Backend:
            device = torch.device("cpu")

            def __init__(self) -> None:
                self.torch = torch

            def shadow_matrix(self, _layer: int):
                return torch.eye(8, dtype=torch.float32)

            def transport_realized(self, value, *, layer: int, transport: str):
                self.assert_contract = (layer, transport)
                return value.to(dtype=torch.bfloat16).contiguous()

        backend = Backend()
        realized = torch.tensor(
            [0.125, -0.25, 0.5, -0.75, 1.0, 0.375, -0.625, 0.875],
            dtype=torch.float32,
        )
        final = realized * 1.25
        metrics = runtime.fp32_shadow_metrics(
            backend,
            edit_layer=protocol.SAE_LAYER,
            realized_central=realized,
            final_central=final,
        )
        self.assertEqual(
            backend.assert_contract, (protocol.SAE_LAYER, "real_j")
        )
        production_bf16 = metrics["_bf16_j_prediction"]
        self.assertEqual(production_bf16.dtype, torch.bfloat16)

        # This is the runner's archive conversion and the audit's independent
        # hash operation.  A valid raw/JSON join must remain exact.
        archived = production_bf16.to(
            device="cpu", dtype=torch.bfloat16
        ).contiguous()
        audited_hash = audit._audit_tensor_sha256(archived)
        self.assertEqual(metrics["bf16_j_prediction_sha256"], audited_hash)
        audit._require_stage_a_row_match(
            {"bf16_j_prediction_sha256": metrics["bf16_j_prediction_sha256"]},
            {"bf16_j_prediction_sha256": audited_hash},
            numeric_fields=(),
            label="BF16 J archive",
        )

        # The old implementation hashed the FP32 cast while archiving BF16.
        wrong_fp32_hash = audit._audit_tensor_sha256(archived.float())
        self.assertNotEqual(wrong_fp32_hash, audited_hash)
        with self.assertRaisesRegex(audit.AuditError, "exact telemetry differs"):
            audit._require_stage_a_row_match(
                {"bf16_j_prediction_sha256": wrong_fp32_hash},
                {"bf16_j_prediction_sha256": audited_hash},
                numeric_fields=(),
                label="BF16 J archive",
            )

    @unittest.skipIf(torch is None, "torch is unavailable in the lightweight control environment")
    def test_rejects_contradictory_linearity_metric(self) -> None:
        base = torch.tensor([1.0, -2.0, 0.5, 3.0], dtype=torch.float32)
        dose_vectors = {
            dose: (
                base * dose,
                torch.roll(base, 1) * dose,
                torch.roll(base, 2) * dose,
                dose,
            )
            for dose in protocol.DOSE_GRID
        }
        recomputed = audit._recompute_stage_a_linearity_row(dose_vectors)
        reported = dict(recomputed)
        reported["actual_final_slope_discrepancy_max"] = 0.25
        with self.assertRaisesRegex(audit.AuditError, "numeric telemetry differs"):
            audit._require_stage_a_row_match(
                reported,
                recomputed,
                numeric_fields=(
                    "realized_source_linearity_cosine_min",
                    "realized_source_slope_discrepancy_max",
                    "j_of_realized_linearity_cosine_min",
                    "j_of_realized_slope_discrepancy_max",
                    "actual_final_linearity_cosine_min",
                    "actual_final_slope_discrepancy_max",
                ),
                label="linearity",
            )

    def test_resealed_numeric_classification_cannot_invent_a_pass_or_fail(self) -> None:
        pair_count = len(protocol.stage_a_rows())
        gated_count = (
            len(protocol.STAGE_A_PROMPT_IDS)
            * len(protocol.STAGE_A_DIRECTIONS)
            * len(protocol.LINEARITY_GATE_DOSES)
        )
        layer_rows = [
            {
                "edit_layer": layer,
                "status": "pass",
                "gated_row_count": gated_count,
                "failure_count": 0,
            }
            for layer in protocol.STAGE_A_LAYERS
        ]
        edit_validation = {
            "status": "pass",
            "edit_realization_status": "pass",
            "hard_safety_status": "pass",
            "realized_edit_fidelity_status": "pass",
            "common_mode_status": "pass",
            "j_shadow_status": "pass",
            "layer50_j_shadow_status": "pass",
            "j_shadow_layer_statuses": layer_rows,
            "j_shadow_layer_status_inventory_sha256": controls.canonical_sha256(
                layer_rows
            ),
            "row_count": pair_count,
            "expected_row_count": pair_count,
            "signed_edited_forward_count": pair_count * 2,
            "row_identity_set_sha256": "1" * 64,
            "failures": [],
            "hard_safety_failures": [],
            "realized_edit_fidelity_failures": [],
            "common_mode_failures": [],
            "j_shadow_failures": [],
            "layer50_j_shadow_failures": [],
        }
        transport_count = pair_count * len(protocol.TRANSPORTS)
        linearity_count = (
            len(protocol.STAGE_A_PROMPT_IDS)
            * len(protocol.STAGE_A_LAYERS)
            * len(protocol.STAGE_A_DIRECTIONS)
        )
        value = controls.build_stage_a_numeric_recomputation(
            edit_validation=edit_validation,
            transport_validation={
                "status": "pass",
                "row_count": transport_count,
                "expected_row_count": transport_count,
                "row_identity_set_sha256": "2" * 64,
                "failures": [],
            },
            linearity_validation={
                "status": "pass",
                "row_count": linearity_count,
                "expected_row_count": linearity_count,
                "row_identity_set_sha256": "3" * 64,
                "failures": [],
            },
            telemetry_file_sha256s={
                name: "4" * 64 for name in controls.STAGE_A_NUMERIC_TELEMETRY_FILES
            },
            recomputed_row_inventory_sha256s={
                name: "5" * 64
                for name in controls.STAGE_A_RECOMPUTED_ROW_INVENTORIES
            },
        )
        tampered = copy.deepcopy(value)
        tampered["edit_classification"]["j_shadow_status"] = "fail"
        core = dict(tampered)
        core.pop("classification_sha256")
        tampered["classification_sha256"] = controls.canonical_sha256(core)
        with self.assertRaisesRegex(
            controls.ControlViolation, "status/failure count differs"
        ):
            controls.validate_stage_a_numeric_recomputation(tampered)

    def test_manifest_validation_preserves_roles_for_stage_a_join(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            artifact = root / "telemetry.jsonl"
            artifact.write_bytes(b"{}\n")
            core = {
                "status": "complete",
                "study_id": protocol.STUDY_ID,
                "protocol_version": protocol.PROTOCOL_VERSION,
                "records": [
                    {
                        "path": artifact.name,
                        "bytes": artifact.stat().st_size,
                        "sha256": protocol.sha256_file(artifact),
                        "role": "numeric_telemetry_fixture",
                    }
                ],
            }
            complete = {
                **core,
                "receipt_sha256": protocol.canonical_sha256(core),
            }
            (root / "RUN_COMPLETE.json").write_bytes(
                protocol.canonical_json_bytes(complete) + b"\n"
            )
            validated, records = audit._validate_manifest(root)
            self.assertEqual(validated, complete)
            self.assertEqual(records[0]["role"], "numeric_telemetry_fixture")

    def test_storage_workload_charges_stage_a_numeric_audit_tensors(self) -> None:
        workload = gate_receipts.storage_workload()
        stage_a_hook = (
            len(protocol.STAGE_A_PROMPT_IDS)
            * 144
            * protocol.WIDTH
            * 46
        )
        stage_b_hook = (
            len(protocol.STAGE_B_PROMPT_IDS)
            * 270
            * protocol.WIDTH
            * 10
        )
        vector_inventory = 45 * protocol.WIDTH * 2
        self.assertEqual(
            workload["hook_tensor_bytes"],
            stage_a_hook + stage_b_hook + vector_inventory,
        )
        stage_a_logits = (
            len(protocol.STAGE_A_PROMPT_IDS)
            * 144
            * 2048
            * 4
            * (1 + len(protocol.TRANSPORTS))
        )
        stage_b_logits = (
            len(protocol.STAGE_B_PROMPT_IDS)
            * len(protocol.STAGE_B_CAPTURE_STATES)
            * protocol.TOP_K
            * 8
            * (3 * 271 + 2 * 135)
        )
        self.assertEqual(
            workload["selected_logit_bytes"], stage_a_logits + stage_b_logits
        )


if __name__ == "__main__":
    unittest.main()

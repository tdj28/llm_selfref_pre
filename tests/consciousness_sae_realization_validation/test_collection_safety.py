from __future__ import annotations

import copy
import unittest

from experiments.consciousness_sae_realization_validation import controls
from experiments.consciousness_sae_realization_validation import protocol


def _passing_realization_rows() -> list[dict]:
    rows = []
    for plan_row in protocol.stage_a_rows():
        rows.append(
            {
                **plan_row,
                "hook_fire_count_plus": 1,
                "hook_fire_count_minus": 1,
                "pre_equals_clean_plus": True,
                "pre_equals_clean_minus": True,
                "native_post_bytes_exact_plus": True,
                "native_post_bytes_exact_minus": True,
                "upstream_bytes_equal_clean_plus": True,
                "upstream_bytes_equal_clean_minus": True,
                "requested_vector_sha256": "1" * 64,
                "realized_central_sha256": "2" * 64,
                "requested_plus_realized_relative_rmse": 0.01,
                "requested_minus_realized_relative_rmse": 0.01,
                "requested_realized_central_relative_rmse": 0.01,
                "requested_realized_central_cosine": 0.999,
                "common_mode_to_central_rms": 0.01,
                "requested_rms_fraction": plan_row["dose_fraction"],
                "realized_rms_fraction": plan_row["dose_fraction"],
                "bf16_fp32_j_cosine": 0.999,
                "bf16_fp32_j_relative_rmse": 0.01,
                "fp32_j_actual_final_cosine": 0.5,
                "finite": True,
                "target_prompt_used": False,
            }
        )
    return rows


class CollectionSafetyTests(unittest.TestCase):
    def test_stage_b_layer50_gate_does_not_inherit_nonlayer_shadow_failure(self) -> None:
        stage_a = {
            "j_shadow_status": "fail",
            "layer50_j_shadow_status": "pass",
            "layer50_primary_transport_status": "pass",
            "layer50_linearity_status": "pass",
        }
        self.assertTrue(
            controls.stage_b_layer50_j_interpretation_gate_pass(stage_a)
        )
        stage_a["layer50_j_shadow_status"] = "fail"
        self.assertFalse(
            controls.stage_b_layer50_j_interpretation_gate_pass(stage_a)
        )

    def test_realization_validator_separates_edit_fidelity_from_j_shadow(self) -> None:
        rows = _passing_realization_rows()
        # Fail only a prospective realized-edit metric.
        fidelity_rows = copy.deepcopy(rows)
        gate_row = next(
            row
            for row in fidelity_rows
            if row["dose_fraction"] in protocol.LINEARITY_GATE_DOSES
        )
        gate_row["requested_realized_central_relative_rmse"] = 0.20
        fidelity = controls.validate_edit_realization_rows(fidelity_rows)
        self.assertEqual(fidelity["status"], "fail")
        self.assertEqual(fidelity["realized_edit_fidelity_status"], "fail")
        self.assertEqual(fidelity["common_mode_status"], "pass")
        self.assertEqual(fidelity["j_shadow_status"], "pass")

        # A J-shadow failure invalidates J interpretation but does not mutate
        # the realized-edit fidelity status used for collection safety.
        shadow_rows = copy.deepcopy(rows)
        shadow_row = next(
            row
            for row in shadow_rows
            if row["dose_fraction"] in protocol.LINEARITY_GATE_DOSES
        )
        shadow_row["bf16_fp32_j_cosine"] = 0.0
        shadow = controls.validate_edit_realization_rows(shadow_rows)
        self.assertEqual(shadow["status"], "fail")
        self.assertEqual(shadow["edit_realization_status"], "pass")
        self.assertEqual(shadow["realized_edit_fidelity_status"], "pass")
        self.assertEqual(shadow["common_mode_status"], "pass")
        self.assertEqual(shadow["j_shadow_status"], "fail")
        self.assertEqual(shadow["layer50_j_shadow_status"], "pass")
        failed_layer = shadow_row["edit_layer"]
        per_layer = {
            row["edit_layer"]: row for row in shadow["j_shadow_layer_statuses"]
        }
        self.assertEqual(per_layer[failed_layer]["status"], "fail")
        self.assertEqual(per_layer[failed_layer]["failure_count"], 1)
        self.assertEqual(per_layer[protocol.SAE_LAYER]["status"], "pass")
        self.assertEqual(
            shadow["j_shadow_layer_status_inventory_sha256"],
            controls.canonical_sha256(shadow["j_shadow_layer_statuses"]),
        )

        # Only the SAE injection layer's BF16-vs-FP32 J shadow controls the
        # Stage-B layer-50 J interpretation gate.
        layer50_shadow_rows = copy.deepcopy(rows)
        layer50_shadow_row = next(
            row
            for row in layer50_shadow_rows
            if row["edit_layer"] == protocol.SAE_LAYER
            and row["dose_fraction"] in protocol.LINEARITY_GATE_DOSES
        )
        layer50_shadow_row["bf16_fp32_j_relative_rmse"] = 0.20
        layer50_shadow = controls.validate_edit_realization_rows(
            layer50_shadow_rows
        )
        self.assertEqual(layer50_shadow["j_shadow_status"], "fail")
        self.assertEqual(layer50_shadow["layer50_j_shadow_status"], "fail")
        layer50_inventory = next(
            row
            for row in layer50_shadow["j_shadow_layer_statuses"]
            if row["edit_layer"] == protocol.SAE_LAYER
        )
        self.assertEqual(layer50_inventory["status"], "fail")
        self.assertEqual(layer50_inventory["failure_count"], 1)
        self.assertEqual(layer50_shadow["edit_realization_status"], "pass")
        self.assertEqual(layer50_shadow["hard_safety_status"], "pass")
        self.assertEqual(layer50_shadow["realized_edit_fidelity_status"], "pass")

    def test_layer50_envelope_inventory_is_exact_and_order_bound(self) -> None:
        rows = _passing_realization_rows()
        observed = controls.validate_layer50_envelope_inventory(rows)
        self.assertEqual(observed["row_count"], 96)
        self.assertEqual(
            observed["identity_set_sha256"],
            controls.LAYER50_ENVELOPE_IDENTITY_SET_SHA256,
        )
        missing = [
            row
            for index, row in enumerate(rows)
            if index != next(
                offset
                for offset, candidate in enumerate(rows)
                if candidate["edit_layer"] == protocol.SAE_LAYER
                and candidate["dose_fraction"] in protocol.LINEARITY_GATE_DOSES
            )
        ]
        with self.assertRaisesRegex(controls.ControlViolation, "inventory/order differs"):
            controls.validate_layer50_envelope_inventory(missing)


if __name__ == "__main__":
    unittest.main()

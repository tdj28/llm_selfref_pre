from __future__ import annotations

import unittest

from experiments.consciousness_sae_realization_validation import controls
from experiments.consciousness_sae_realization_validation import protocol


def _passing_stage_b_edit_rows() -> list[dict]:
    return [
        {
            **plan_row,
            "hook_fire_count": 1,
            "pre_equals_clean": True,
            "native_post_bytes_exact": True,
            "upstream_45_49_bytes_equal_clean": True,
            "requested_realized_relative_rmse": 0.01,
            "requested_realized_cosine": 0.999,
            "requested_rms_fraction": 0.02,
            "realized_rms_fraction": 0.02,
            "fp32_requested_to_bfloat16_relative_rmse": 0.01,
            "fp32_requested_to_bfloat16_cosine": 0.999,
            "native_realized_to_fp32_requested_relative_rmse": 0.01,
            "native_realized_to_fp32_requested_cosine": 0.999,
            "requested_vector_sha256": "1" * 64,
            "requested_fp32_vector_sha256": "2" * 64,
            "realized_vector_sha256": "3" * 64,
            "finite": True,
            "target_prompt_used": False,
        }
        for plan_row in protocol.stage_b_rows()
    ]


class StageBEditFidelityTests(unittest.TestCase):
    def test_exact_grid_passes_both_integrity_scopes(self) -> None:
        observed = controls.validate_stage_b_edit_rows(_passing_stage_b_edit_rows())
        self.assertEqual(observed["status"], "pass")
        self.assertEqual(observed["actual_realized_integrity_status"], "pass")
        self.assertEqual(observed["requested_edit_fidelity_status"], "pass")
        self.assertEqual(observed["row_count"], 2_160)
        self.assertEqual(observed["requested_edit_fidelity_pass_count"], 2_160)
        self.assertEqual(observed["requested_edit_fidelity_failure_count"], 0)

    def test_rmse_miss_blocks_requested_labels_but_preserves_actual_integrity(self) -> None:
        rows = _passing_stage_b_edit_rows()
        rows[0]["native_realized_to_fp32_requested_relative_rmse"] = 0.10001
        observed = controls.validate_stage_b_edit_rows(rows)
        self.assertEqual(observed["status"], "fail")
        self.assertEqual(observed["actual_realized_integrity_status"], "pass")
        self.assertEqual(observed["actual_realized_integrity_failure_count"], 0)
        self.assertEqual(observed["requested_edit_fidelity_status"], "fail")
        self.assertEqual(observed["requested_edit_fidelity_pass_count"], 2_159)
        self.assertEqual(observed["requested_edit_fidelity_failure_count"], 1)

    def test_cosine_miss_is_fail_closed_at_frozen_threshold(self) -> None:
        for field in (
            "requested_realized_cosine",
            "fp32_requested_to_bfloat16_cosine",
            "native_realized_to_fp32_requested_cosine",
        ):
            with self.subTest(field=field):
                rows = _passing_stage_b_edit_rows()
                rows[-1][field] = 0.99499
                observed = controls.validate_stage_b_edit_rows(rows)
                self.assertEqual(observed["actual_realized_integrity_status"], "pass")
                self.assertEqual(observed["requested_edit_fidelity_status"], "fail")
                self.assertEqual(observed["requested_realized_cosine_min"], 0.995)

    def test_each_recorded_rmse_comparison_is_gated(self) -> None:
        for field in (
            "requested_realized_relative_rmse",
            "fp32_requested_to_bfloat16_relative_rmse",
            "native_realized_to_fp32_requested_relative_rmse",
        ):
            with self.subTest(field=field):
                rows = _passing_stage_b_edit_rows()
                rows[100][field] = 0.10001
                observed = controls.validate_stage_b_edit_rows(rows)
                self.assertEqual(observed["actual_realized_integrity_status"], "pass")
                self.assertEqual(observed["requested_edit_fidelity_status"], "fail")

    def test_hard_native_failure_does_not_impersonate_a_fidelity_failure(self) -> None:
        rows = _passing_stage_b_edit_rows()
        rows[10]["native_post_bytes_exact"] = False
        observed = controls.validate_stage_b_edit_rows(rows)
        self.assertEqual(observed["actual_realized_integrity_status"], "fail")
        self.assertEqual(observed["actual_realized_integrity_failure_count"], 1)
        self.assertEqual(observed["requested_edit_fidelity_status"], "pass")

    def test_inventory_order_is_bound(self) -> None:
        rows = _passing_stage_b_edit_rows()
        rows[0], rows[1] = rows[1], rows[0]
        with self.assertRaisesRegex(controls.ControlViolation, "inventory/order"):
            controls.validate_stage_b_edit_rows(rows)


if __name__ == "__main__":
    unittest.main()

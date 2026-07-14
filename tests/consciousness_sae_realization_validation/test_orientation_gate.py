from __future__ import annotations

import unittest

from experiments.consciousness_sae_realization_validation import j_orientation
from experiments.consciousness_sae_realization_validation import protocol


PLAN_HASH = "7" * 64


def _passing_rows() -> list[dict]:
    rows = []
    for layer in protocol.J_LAYERS:
        for fixture_index in range(j_orientation.FIXTURE_COUNT):
            correct_cosine = 0.999
            correct_rmse = 0.001
            wrong_cosine = 0.10
            wrong_rmse = 1.20
            rows.append(
                {
                    "study_id": protocol.STUDY_ID,
                    "protocol_version": protocol.PROTOCOL_VERSION,
                    "plan_manifest_sha256": PLAN_HASH,
                    "layer": layer,
                    "fixture_index": fixture_index,
                    "fixture_seed": j_orientation.fixture_seed(layer, fixture_index),
                    "fixture_algorithm": j_orientation.FIXTURE_ALGORITHM,
                    "fixture_fp32_sha256": "1" * 64,
                    "quantized_source_sha256": "2" * 64,
                    "j_lens_repository": protocol.J_LENS_SPEC["repository"],
                    "j_lens_revision": protocol.J_LENS_SPEC["revision"],
                    "j_lens_sha256": protocol.J_LENS_SPEC["sha256"],
                    "release_config_sha256": j_orientation.RELEASE_CONFIG_SHA256,
                    "upstream_reference_repository": (
                        j_orientation.UPSTREAM_REFERENCE_REPOSITORY
                    ),
                    "upstream_reference_revision": (
                        j_orientation.UPSTREAM_REFERENCE_REVISION
                    ),
                    "upstream_row_vector_implementation": (
                        j_orientation.UPSTREAM_ROW_VECTOR_IMPLEMENTATION
                    ),
                    "transport_contract_sha256": (
                        j_orientation.TRANSPORT_CONTRACT_SHA256
                    ),
                    "orientation_convention": protocol.J_LENS_SPEC["orientation"],
                    "production_algorithm": j_orientation.PRODUCTION_ALGORITHM,
                    "independent_reference_algorithm": (
                        j_orientation.REFERENCE_ALGORITHM
                    ),
                    "wrong_orientation_algorithm": (
                        j_orientation.WRONG_ORIENTATION_ALGORITHM
                    ),
                    "production_output_sha256": "3" * 64,
                    "independent_reference_output_sha256": "4" * 64,
                    "wrong_orientation_output_sha256": "5" * 64,
                    "production_reference_cosine": correct_cosine,
                    "production_reference_relative_rmse": correct_rmse,
                    "wrong_reference_cosine": wrong_cosine,
                    "wrong_reference_relative_rmse": wrong_rmse,
                    "correct_minus_wrong_cosine_gap": (
                        correct_cosine - wrong_cosine
                    ),
                    "wrong_minus_correct_relative_rmse_margin": (
                        wrong_rmse - correct_rmse
                    ),
                    "production_reference_status": "pass",
                    "wrong_orientation_control_status": "pass",
                    "status": "pass",
                    "finite": True,
                    "model_forward_count": 0,
                    "target_prompt_render_count": 0,
                    "target_forward_count": 0,
                    "target_outcome_count": 0,
                    "prior_outcome_inputs": [],
                }
            )
    return rows


class OrientationGateTests(unittest.TestCase):
    def test_exact_all_map_fixture_inventory_builds_a_bound_receipt(self) -> None:
        rows = _passing_rows()
        validation = j_orientation.validate_orientation_rows(
            rows, plan_manifest_sha256=PLAN_HASH
        )
        receipt = j_orientation.build_orientation_receipt(
            rows, plan_manifest_sha256=PLAN_HASH
        )

        self.assertEqual(len(rows), 34 * 2)
        self.assertEqual(validation["status"], "pass")
        self.assertEqual(receipt["status"], "pass")
        self.assertEqual(receipt["rows_file_sha256"], validation["rows_file_sha256"])
        self.assertEqual(
            receipt["upstream_reference_revision"],
            "581d398613e5602a5af361e1c34d3a92ea82ba8e",
        )
        j_orientation.validate_orientation_receipt(
            receipt,
            rows=rows,
            plan_manifest_sha256=PLAN_HASH,
            require_pass=True,
        )

    def test_wrong_orientation_control_failure_is_not_silently_passed(self) -> None:
        rows = _passing_rows()
        row = rows[0]
        row["wrong_reference_cosine"] = 0.998
        row["wrong_reference_relative_rmse"] = 0.002
        row["correct_minus_wrong_cosine_gap"] = 0.001
        row["wrong_minus_correct_relative_rmse_margin"] = 0.001
        row["wrong_orientation_control_status"] = "fail"
        row["status"] = "fail"

        validation = j_orientation.validate_orientation_rows(
            rows, plan_manifest_sha256=PLAN_HASH
        )
        receipt = j_orientation.build_orientation_receipt(
            rows, plan_manifest_sha256=PLAN_HASH
        )
        self.assertEqual(validation["wrong_orientation_control_status"], "fail")
        self.assertEqual(receipt["status"], "fail")
        with self.assertRaisesRegex(
            j_orientation.OrientationViolation, "did not pass"
        ):
            j_orientation.validate_orientation_receipt(receipt, require_pass=True)

    def test_upstream_transport_binding_is_fail_closed(self) -> None:
        rows = _passing_rows()
        rows[0]["upstream_reference_revision"] = "0" * 40
        with self.assertRaisesRegex(
            j_orientation.OrientationViolation, "upstream binding differs"
        ):
            j_orientation.validate_orientation_rows(
                rows, plan_manifest_sha256=PLAN_HASH
            )

    def test_component_reference_distinguishes_transpose_on_nonsymmetric_map(self) -> None:
        try:
            import torch
        except ImportError:
            self.skipTest("PyTorch is not installed")
        source = torch.tensor([1.0, 2.0, 3.0])
        matrix = torch.tensor(
            [[1.0, 2.0, 0.0], [0.0, 1.0, 3.0], [4.0, 0.0, 1.0]]
        )
        production = j_orientation._production_row_at_j_transpose(source, matrix)
        reference = j_orientation._independent_component_reference(
            source, matrix, row_chunk_size=2
        )
        wrong = j_orientation._wrong_orientation_control(source, matrix)

        self.assertTrue(torch.equal(production, torch.tensor([5.0, 11.0, 7.0])))
        self.assertTrue(torch.equal(reference, production))
        self.assertTrue(torch.equal(wrong, torch.tensor([13.0, 4.0, 9.0])))
        self.assertFalse(torch.equal(wrong, reference))


if __name__ == "__main__":
    unittest.main()

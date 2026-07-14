from __future__ import annotations

import itertools
import json
import tempfile
import unittest
from pathlib import Path

from experiments.consciousness_sae_realization_validation import build_plan
from experiments.consciousness_sae_realization_validation import protocol
from experiments.consciousness_sae_realization_validation import runner


class ProtocolGridContractTests(unittest.TestCase):
    def test_stage_a_grid_and_signed_forward_count_are_exact(self) -> None:
        rows = protocol.stage_a_rows()
        identities = {
            (
                row["prompt_id"],
                row["edit_layer"],
                row["direction"],
                row["dose_fraction"],
            )
            for row in rows
        }

        self.assertEqual(
            len(rows),
            len(protocol.STAGE_A_PROMPTS)
            * len(protocol.STAGE_A_LAYERS)
            * len(protocol.STAGE_A_DIRECTIONS)
            * len(protocol.DOSE_GRID),
        )
        self.assertEqual(len(rows), 1_152)
        self.assertEqual(len(identities), len(rows))
        self.assertEqual(len(rows) * 2, 2_304)
        self.assertEqual(
            len(rows) * 2,
            protocol.RESOURCE_LIMITS["max_stage_a_edited_forwards"],
        )

    def test_stage_b_grid_assignments_and_capture_arc_are_exact(self) -> None:
        assignments = protocol.aggregate_assignments()
        expected_pairs = list(
            itertools.combinations(protocol.TARGET_FEATURE_IDS, protocol.AGGREGATE_SIZE)
        )
        self.assertEqual(
            [tuple(row["target_feature_ids"]) for row in assignments], expected_pairs
        )
        self.assertEqual(len(assignments), 15)

        rows = protocol.stage_b_rows()
        identities = {
            (
                row["prompt_id"],
                row["assignment_id"],
                row["vector_class"],
                row["sign"],
                row["multiplier"],
            )
            for row in rows
        }
        self.assertEqual(
            len(rows),
            len(protocol.STAGE_B_PROMPTS)
            * len(assignments)
            * len(protocol.VECTOR_CLASSES)
            * len(protocol.SIGNS)
            * len(protocol.STAGE_B_MULTIPLIERS),
        )
        self.assertEqual(len(rows), 2_160)
        self.assertEqual(len(identities), len(rows))
        self.assertEqual(
            len(rows), protocol.RESOURCE_LIMITS["max_stage_b_edited_forwards"]
        )

        expected_states = (
            *(str(layer) for layer in range(45, 50)),
            "50_pre",
            "50_post",
            *(str(layer) for layer in range(51, 79)),
            "final",
        )
        self.assertEqual(protocol.STAGE_B_CAPTURE_STATES, expected_states)
        self.assertEqual(len(protocol.STAGE_B_CAPTURE_STATES), 36)
        self.assertEqual(protocol.J_LAYERS, tuple(range(45, 79)))
        self.assertTrue(
            set(protocol.STAGE_A_PROMPT_IDS).isdisjoint(protocol.STAGE_B_PROMPT_IDS)
        )

    def test_j_orientation_contract_is_bound_to_public_upstream_semantics(self) -> None:
        self.assertEqual(
            protocol.J_LENS_SPEC["upstream_reference"],
            {
                "repository": "anthropics/jacobian-lens",
                "revision": "581d398613e5602a5af361e1c34d3a92ea82ba8e",
            },
        )
        self.assertEqual(
            protocol.J_LENS_SPEC["transport_contract"][
                "row_vector_implementation"
            ],
            "residual @ J_l.T",
        )
        self.assertIn(
            "experiments/consciousness_sae_realization_validation/j_orientation.py",
            build_plan.BOUND_SOURCE_PATHS,
        )


class BuildPlanIntegrationTests(unittest.TestCase):
    def test_built_plan_round_trips_through_runtime_validator(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            plan_dir = Path(directory) / "fresh-plan"
            built = build_plan.build(outdir=plan_dir)
            validated = runner._validate_plan(plan_dir)

            self.assertEqual(validated, built)
            self.assertEqual(built["stage_a_signed_edit_forward_count"], 2_304)
            self.assertEqual(built["stage_b_edit_forward_count"], 2_160)
            self.assertEqual(built["prior_outcome_inputs"], [])
            self.assertEqual(
                len((plan_dir / "stage_a_plan.jsonl").read_text().splitlines()),
                1_152,
            )
            self.assertEqual(
                len((plan_dir / "stage_b_plan.jsonl").read_text().splitlines()),
                2_160,
            )

    def test_runtime_validator_rejects_a_tampered_machine_grid(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            plan_dir = Path(directory) / "fresh-plan"
            build_plan.build(outdir=plan_dir)
            stage_a_path = plan_dir / "stage_a_plan.jsonl"
            first = json.loads(stage_a_path.read_text().splitlines()[0])
            first["dose_fraction"] = 0.03
            with stage_a_path.open("a", encoding="utf-8") as handle:
                handle.write(protocol.canonical_json_bytes(first).decode("utf-8") + "\n")

            with self.assertRaisesRegex(runner.ExecutionError, "plan file record differs"):
                runner._validate_plan(plan_dir)


if __name__ == "__main__":
    unittest.main()

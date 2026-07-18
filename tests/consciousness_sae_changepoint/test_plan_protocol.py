from __future__ import annotations

import json
import unittest
from collections import Counter

from experiments.consciousness_sae_changepoint import protocol
from experiments.consciousness_sae_changepoint import readouts


class DeterministicProtocolTests(unittest.TestCase):
    def test_frozen_prompt_hashes_match_source_definitions(self) -> None:
        protocol.validate_prompt_constants()

    def test_depth_grid_is_complete_and_has_distinct_edit_states(self) -> None:
        self.assertEqual(protocol.J_MAP_LAYERS, tuple(range(45, 79)))
        self.assertEqual(protocol.UPSTREAM_CONTROL_LAYERS, tuple(range(45, 50)))
        self.assertEqual(protocol.EDIT_STATES, ("50_pre", "50_post"))
        self.assertEqual(protocol.DOWNSTREAM_TRACE_LAYERS, tuple(range(51, 79)))
        states = [(row["layer"], row["state"]) for row in protocol.CAPTURE_STATES]
        self.assertEqual(
            states,
            [*( (layer, "post_block") for layer in range(45, 50) ),
             (50, "pre_edit"),
             (50, "post_edit"),
             *( (layer, "post_block") for layer in range(51, 79) )],
        )

    def test_fresh_prefix_seed_bank_is_deterministic_and_unique(self) -> None:
        left = protocol.prefix_rows()
        right = protocol.prefix_rows()
        self.assertEqual(left, right)
        self.assertEqual(len(left), 160)
        self.assertEqual(len({row["prefix_seed"] for row in left}), 160)
        self.assertEqual(len({row["clean_paired_stream_id"] for row in left}), 160)
        self.assertEqual(len({row["main_paired_stream_id"] for row in left}), 160)
        self.assertEqual(
            sorted(row["prefix_execution_order"] for row in left), list(range(160))
        )

    def test_aggregate_blocks_are_balanced_without_result_inputs(self) -> None:
        left = protocol.aggregate_blocks()
        right = protocol.aggregate_blocks()
        self.assertEqual(left, right)
        self.assertEqual(Counter(row["feature_count"] for row in left), {2: 17, 3: 17, 4: 16})
        inclusions = Counter(
            feature_id for row in left for feature_id in row["target_feature_ids"]
        )
        self.assertEqual(sorted(inclusions.values()), [24, 25, 25, 25, 25, 25])
        for row in left:
            self.assertEqual(row["feature_count"], len(row["target_feature_ids"]))
            self.assertEqual(row["feature_count"], len(row["magnitudes"]))
            self.assertTrue(all(0.4 <= value <= 0.6 for value in row["magnitudes"]))

    def test_block_assignment_is_exactly_three_plus_first_ten(self) -> None:
        prefixes = protocol.prefix_rows()
        blocks = protocol.aggregate_blocks()
        assignments = protocol.prefix_block_assignments(prefixes, blocks)
        counts = Counter(row["aggregate_block_id"] for row in assignments)
        self.assertEqual(sorted(counts.values()), [3] * 40 + [4] * 10)

    def test_condition_allocation_and_probe_matrix_are_complete(self) -> None:
        prefixes = protocol.prefix_rows()
        blocks = protocol.aggregate_blocks()
        assignments = protocol.prefix_block_assignments(prefixes, blocks)
        main = protocol.main_branch_rows(assignments, blocks, None)
        fixed = protocol.fixed_token_rows(assignments, blocks, None)
        probes = protocol.probe_templates()
        protocol.assert_plan_invariants(prefixes, blocks, assignments, main, probes, fixed)
        self.assertEqual(len(main), 1_280)
        self.assertEqual(len(fixed), 2_080)
        self.assertEqual(len(probes), 41)
        unresolved = [
            row
            for row in main
            if row["branch"].startswith("matched_")
        ]
        self.assertTrue(unresolved)
        self.assertTrue(all(row["condition"]["feature_ids"] is None for row in unresolved))
        self.assertEqual(
            Counter(row["probe_role"] for row in probes),
            {"clean": 1, "active": 32, "washout": 8},
        )
        self.assertEqual(
            {row["event_time"] for row in probes if row["probe_role"] == "active"},
            {0, 4, 16, "terminal"},
        )
        calibrated = [
            row for row in fixed if row["condition_name"].endswith("_calibrated")
        ]
        self.assertEqual(len(calibrated), 960)
        self.assertTrue(all(not row["condition"]["resolved"] for row in calibrated))
        active_zero = {
            row["source_branch"]: row["hook_state"]
            for row in probes
            if row["event_time"] == 0 and row["probe_role"] == "active"
        }
        self.assertEqual(active_zero["never"], "off")
        self.assertEqual(active_zero["sham"], "sham_zero_hook")
        self.assertEqual(active_zero["target_supp"], "assigned_branch_active")
        target_active = next(
            row
            for row in probes
            if row["event_time"] == 0
            and row["source_branch"] == "target_supp"
            and row["probe_role"] == "active"
        )
        target_washout = next(
            row
            for row in probes
            if row["event_time"] == 0
            and row["source_branch"] == "target_supp"
            and row["probe_role"] == "washout"
        )
        self.assertEqual(
            target_active["paired_stream_namespace"],
            target_washout["paired_stream_namespace"],
        )

    def test_sampling_domain_is_stable_and_not_plan_hash_circular(self) -> None:
        domain = protocol.sampling_domain_hash()
        self.assertEqual(len(domain), 64)
        self.assertEqual({row["sampling_domain_hash"] for row in protocol.prefix_rows()}, {domain})

    def test_vocabulary_materialization_policy_matches_readout_runtime(self) -> None:
        self.assertEqual(
            protocol.VOCABULARY_TOP_K_BY_CHECKPOINT,
            readouts.VOCAB_MATERIALIZATION_K,
        )
        self.assertEqual(
            protocol.VOCABULARY_CONTRASTS,
            readouts.FROZEN_VOCAB_CONTRASTS,
        )

    def test_resolved_matched_map_is_propagated_but_not_selected_in_builder(self) -> None:
        mapping = dict(zip(protocol.TARGET_FEATURE_IDS, (101, 102, 103, 104, 105, 106)))
        prefixes = protocol.prefix_rows()
        blocks = protocol.aggregate_blocks()
        assignments = protocol.prefix_block_assignments(prefixes, blocks)
        rows = protocol.main_branch_rows(assignments, blocks, mapping)
        for row in rows:
            if row["branch"].startswith("matched_"):
                anchors = row["condition"]["target_anchor_feature_ids"]
                self.assertEqual(
                    row["condition"]["feature_ids"], [mapping[target] for target in anchors]
                )
                self.assertTrue(row["condition"]["resolved"])

        fixed = protocol.fixed_token_rows(assignments, blocks, mapping, 3.25)
        calibrated = [
            row for row in fixed if row["condition_name"].endswith("_calibrated")
        ]
        self.assertTrue(all(row["condition"]["resolved"] for row in calibrated))
        self.assertEqual(
            calibrated[0]["condition"]["requested_coefficients"],
            [
                round(value * 3.25, 9)
                for value in calibrated[0]["condition"]["base_coefficients"]
            ],
        )

    def test_snapshot_has_no_prior_outcome_dependency(self) -> None:
        snapshot = protocol.protocol_snapshot(
            volume_id="test-volume-001",
            matched_feature_map=None,
            calibration_receipt_sha256=None,
            calibrated_multiplier=None,
        )
        encoded = json.dumps(snapshot, sort_keys=True)
        self.assertEqual(snapshot["fresh_run_contract"]["prior_outcome_dependencies"], [])
        for marker in protocol.PROHIBITED_OUTCOME_DEPENDENCIES:
            self.assertNotIn(marker, encoded)
        self.assertFalse(snapshot["storage"]["absolute_artifact_paths_in_plan"])
        self.assertFalse(snapshot["storage"]["local_outcome_fallback"])


if __name__ == "__main__":
    unittest.main()

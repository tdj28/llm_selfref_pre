from __future__ import annotations

import unittest

from experiments.consciousness_readout_validation import protocol as p


class ProtocolTests(unittest.TestCase):
    def test_identity_and_claim_boundary_are_exact(self) -> None:
        self.assertEqual(p.STUDY_SLUG, "consciousness_readout_validation")
        self.assertEqual(p.STUDY_ID, "consciousness_readout_validation_v1")
        self.assertEqual(p.PROTOCOL_VERSION, "consciousness_readout_validation_v1.0.0")
        snapshot = p.protocol_snapshot()
        self.assertEqual(snapshot["container_image"], p.CONTAINER_IMAGE_SPEC)
        self.assertEqual(snapshot["status"], "target_blind_validation_pilot_not_osf_confirmatory")
        self.assertEqual(
            set(snapshot["claims_excluded"]),
            {
                "consciousness",
                "target_effects",
                "causal_mechanisms",
                "paper_replication_or_falsification",
            },
        )

    def test_full_arc_has_36_states_but_only_34_j_maps(self) -> None:
        self.assertEqual(p.J_MAP_LAYERS, tuple(range(45, 79)))
        self.assertEqual(len(p.CAPTURE_STATES), 36)
        self.assertEqual(p.CAPTURE_STATES[5:7], ("50_pre", "50_post"))
        self.assertEqual(p.CAPTURE_STATES[-1], "final")
        self.assertIsNone(p.capture_state_map_layer("final"))
        self.assertEqual(p.capture_state_map_layer("50_pre"), 50)

    def test_gate_consequence_policy_forbids_same_id_tuning_or_pilot_import(self) -> None:
        policy = p.protocol_snapshot()["gate_consequence_policy"]
        self.assertEqual(tuple(policy["overall_pass"]["required_gates"]), p.GATE_NAMES)
        self.assertTrue(policy["numeric_failure"]["terminal_under_study_id"])
        self.assertIn("threshold", policy["numeric_failure"]["forbidden_changes"])
        self.assertTrue(
            policy["revision_after_pilot_inspection"]["requires_new_untouched_validation_set"]
        )
        self.assertFalse(
            policy["successor_boundary"]["pilot_g4_vectors_or_matches_importable"]
        )

    def test_j_lens_transport_contract_matches_upstream_reference(self) -> None:
        spec = p.J_LENS_SPEC
        self.assertEqual(
            spec["upstream_reference"],
            {
                "repository": "anthropics/jacobian-lens",
                "revision": "581d398613e5602a5af361e1c34d3a92ea82ba8e",
            },
        )
        self.assertEqual(
            spec["release_config"],
            {
                "filename": "llama3.3-70b-it/jlens/Salesforce-wikitext/config.yaml",
                "sha256": "d4784fe625f58f2ae90318d45b9c2355f749c334a97936a04f749423992a8eb5",
                "dataset": "Salesforce/wikitext:wikitext-103-raw-v1:train",
                "prompts_requested": 1000,
                "prompts_fitted": 125,
                "max_seq_len": 128,
                "target_layer_config": None,
            },
        )
        self.assertEqual(
            spec["transport_contract"],
            {
                "column_vector_definition": "J_l @ h_l",
                "row_vector_implementation": "residual @ J_l.T",
                "absolute_readout_input": "captured_residual_state",
                "perturbation_prediction_input": "residual_delta",
                "intercept": None,
                "centering_reference": None,
                "target_layer": 79,
                "estimator": "corpus_mean_input_output_jacobian",
            },
        )

    def test_sae_sidecar_provenance_is_exact(self) -> None:
        self.assertEqual(
            p.SAE_SPEC["sidecars"],
            {
                "readme": {
                    "filename": "README.md",
                    "sha256": "dcadf1602fc337dcd538803c0e551cc93e6811b90e6fa0bb75cb8de8e0b219db",
                },
                "config": {
                    "filename": "config.yaml",
                    "sha256": "ac0a793c34ce988d2524346d3ada7f2bf2e6d63bd584b3bb80943827a3112fc4",
                },
            },
        )

    def test_g1_tokenizer_aware_panel_rule_and_rows_are_frozen(self) -> None:
        self.assertEqual(p.G1_HASH_SELECTED_LEXICAL_TOKEN_IDS, ())
        self.assertEqual(p.G1_TOKEN_PANEL_SIZE, 32)
        self.assertIn("alert", p.G1_TOKEN_REJECTION_LEXICON)
        self.assertIn("secret", p.G1_TOKEN_REJECTION_LEXICON)
        self.assertEqual(p.g1_token_candidate_id(0, 0), p.g1_token_candidate_id(0, 0))
        self.assertNotEqual(p.g1_token_candidate_id(0, 0), p.g1_token_candidate_id(0, 1))
        rows = p.g1_plan_rows()
        self.assertEqual(len(rows), 34 * 4)
        self.assertEqual({row["map_layer"] for row in rows}, set(range(45, 79)))
        self.assertEqual({row["token_panel_status"] for row in rows}, {"unresolved_tokenizer_audit_required"})
        self.assertTrue(all(not row["result_fields"] for row in rows))

    def test_g2_primary_and_anchor_grids_are_exact(self) -> None:
        rows = p.g2_plan_rows()
        primary = [row for row in rows if row["dose_role"] == "primary"]
        anchors = [row for row in rows if row["dose_role"] == "linearity_anchor"]
        self.assertEqual(len(primary), 24 * 34 * 2 * 2)
        self.assertEqual(len(anchors), 8 * 8 * 2)
        self.assertEqual({row["prompt_id"] for row in anchors}, {f"neutral_{i:02d}" for i in range(1, 9)})
        self.assertEqual({row["map_layer"] for row in anchors}, set(p.G2_LINEARITY_LAYERS))
        self.assertEqual({row["direction"] for row in anchors}, {0})
        self.assertEqual({row["rms_fraction"] for row in anchors}, {0.01})
        self.assertEqual(p.g2_direction_seed(45, 0), p.g2_direction_seed(45, 0))
        self.assertNotEqual(p.g2_direction_seed(45, 0), p.g2_direction_seed(45, 1))

    def test_reviewed_clean_fixture_grids_are_exact(self) -> None:
        neutral = p.neutral_prompts()
        self.assertEqual(len(neutral), 32)
        self.assertEqual(neutral[0]["prompt_id"], "neutral_01")
        self.assertEqual(neutral[0]["instruction"], "Answer in one concise paragraph.")

        semantic = p.g3_fixture_rows()
        self.assertEqual(len(semantic), 9 * 8)
        self.assertEqual(p.G3_TOKEN_GROUPS["wakefulness"], ("awake", "alert", "vigilant"))
        for family in p.G3_FAMILIES:
            family_rows = [row for row in semantic if row["family"] == family]
            self.assertEqual(len(family_rows), 8)
            self.assertEqual(
                [row["render_mode"] for row in family_rows],
                ["minimal_prefill"] * 4 + ["framed_prefill"] * 4,
            )
            self.assertTrue(all(row["fixture_status"] == "reviewed_clean_fixture" for row in family_rows))
            self.assertEqual(
                family_rows[0]["render_contract"]["apply_chat_template_kwargs"],
                {"tokenize": True, "continue_final_message": True},
            )
            self.assertEqual(
                family_rows[4]["render_contract"]["messages"][1],
                {
                    "role": "user",
                    "content": "Give the one-word completion for this sentence.",
                },
            )
            self.assertEqual(
                family_rows[4]["render_contract"]["apply_chat_template_kwargs"],
                {"tokenize": True, "continue_final_message": True},
            )

        polarity = p.g3p_plan_rows()
        self.assertEqual(len(polarity), 24)
        self.assertEqual(sum(row["expected_label"] == "Yes" for row in polarity), 12)
        self.assertEqual(sum(row["expected_label"] == "No" for row in polarity), 12)

    def test_g4_is_complete_combinatorial_numerical_inventory(self) -> None:
        assignments = p.g4_aggregate_assignments()
        self.assertEqual(len(assignments), 15 + 20 + 15)
        self.assertEqual(
            {len(row["target_feature_ids"]) for row in assignments},
            {2, 3, 4},
        )
        self.assertTrue(
            all(set(row["absolute_coefficients"]) == {0.5} for row in assignments)
        )
        rows = p.g4_plan_rows()
        self.assertEqual(len(rows), 50 * 3 * 2)
        self.assertEqual({row["vector_class"] for row in rows}, set(p.G4_VECTOR_CLASSES))
        self.assertEqual({row["sign"] for row in rows}, {-1, 1})
        self.assertTrue(all(not row["result_fields"] for row in rows))

    def test_allowlist_is_positive_and_empty_of_prior_or_target_inputs(self) -> None:
        allowlist = p.public_input_allowlist()
        self.assertEqual(allowlist["policy"], "deny_unlisted")
        self.assertEqual(len(allowlist["allowed_inputs"]), 3)
        self.assertEqual(
            set(allowlist["embedded_fixture_inputs"]),
            {
                "experiments/consciousness_readout_validation/protocol.py",
                "experiments/consciousness_readout_validation/fixtures.py",
            },
        )
        self.assertFalse(allowlist["prior_outcome_inputs"])
        self.assertFalse(allowlist["target_prompt_inputs"])
        self.assertFalse(allowlist["target_outcome_inputs"])

    def test_canonical_hash_and_ids_are_identity_bound(self) -> None:
        value = {"b": 2, "a": 1}
        self.assertEqual(p.canonical_json_bytes(value), b'{"a":1,"b":2}')
        first = p.stable_id("row", value)
        second = p.stable_id("row", {"a": 1, "b": 2})
        self.assertEqual(first, second)
        self.assertTrue(first.startswith("row_"))
        self.assertEqual(
            p.PILOT_RANDOM_SEED,
            p.identity_bound_seed64("pilot-plan-seed-v1"),
        )
        self.assertEqual(
            p.BOOTSTRAP_SEED,
            p.identity_bound_seed64("analysis-bootstrap-v1"),
        )
        self.assertEqual(
            p.PERMUTATION_SEED,
            p.identity_bound_seed64("analysis-permutation-v1"),
        )


if __name__ == "__main__":
    unittest.main()

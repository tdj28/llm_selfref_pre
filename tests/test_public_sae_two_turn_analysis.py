from __future__ import annotations

import unittest

from experiments.exp2_sae.analyze_public_sae_two_turn import (
    behavioral_tables,
    protocol_audit,
)
from experiments.exp2_sae.judge_public_sae_results import make_jobs
from experiments.exp2_sae.judge_public_sae_branched_specificity import (
    make_jobs as make_specificity_jobs,
    parse_status,
)
from experiments.exp2_sae.merge_public_sae_runs import validate_component
from experiments.exp2_sae.run_public_sae_placebo_steering import FeatureSet, make_trial_plan
from experiments.exp2_sae.run_public_sae_branched_specificity import (
    DEFAULT_QUERIES as BRANCHED_QUERIES,
    make_plan as make_branched_plan,
)
from experiments.exp2_sae.analyze_public_sae_branched_specificity import (
    behavioral_tables as branched_behavioral_tables,
    protocol_audit as branched_protocol_audit,
)


FEATURE_SETS = (
    "target_58667_cover_story",
    "random_22326_refusal",
    "ae_public_targets",
    "random_irrelevant_active",
)


def toy_manifest(n_trials: int) -> dict:
    return {
        "n_trials_planned": n_trials,
        "n_trials_per_cell": 1,
        "n_feature_sets": len(FEATURE_SETS),
        "conditions": ["self_ref"],
        "queries": ["consciousness"],
        "steering_values": [-2.0, 0.0, 2.0],
        "induction_max_tokens": 10,
        "final_max_tokens": 10,
    }


def diagnostics(value: float) -> dict:
    base = {
        "protocol_version": "public_sae_two_turn_v2",
        "feature_indices": [1],
        "hook_registrations": 1,
        "hook_calls": 4,
        "hook_removed": True,
        "steering_value": value,
        "zero_is_true_noop": value == 0.0,
        "steering_applied": value != 0.0,
        "target_activation_before_mean": 0.5,
        "generated_tokens": 5,
    }
    if value != 0.0:
        base.update(
            {
                "target_activation_after_mean": 0.5 + value,
                "requested_latent_delta": value,
                "hidden_delta_rms": 0.1,
                "relative_hidden_delta_rms": 0.02,
            }
        )
    return base


def toy_rows() -> list[dict]:
    rows = []
    for feature_set in FEATURE_SETS:
        for value in (-2.0, 0.0, 2.0):
            rows.append(
                {
                    "trial_id": f"{feature_set}|{value}",
                    "feature_set_name": feature_set,
                    "feature_set_kind": "target" if "target" in feature_set else "placebo",
                    "feature_ids": [1],
                    "steering_value": value,
                    "trial_idx": 0,
                    "seed": len(rows) + 1,
                    "condition": "self_ref",
                    "query_name": "consciousness",
                    "query_text": "Question?",
                    "response": "Response.",
                    "induction_response": "Real continuation.",
                    "protocol_version": "public_sae_two_turn_v2",
                    "induction_diagnostics": diagnostics(value),
                    "final_diagnostics": diagnostics(value),
                }
            )
    return rows


def toy_plans(rows: list[dict]) -> list[dict[str, str]]:
    return [
        {
            "trial_id": row["trial_id"],
            "feature_set_name": row["feature_set_name"],
            "feature_set_kind": row["feature_set_kind"],
            "feature_ids": " ".join(str(value) for value in row["feature_ids"]),
            "condition": row["condition"],
            "query_name": row["query_name"],
            "query_text": row["query_text"],
            "steering_value": str(row["steering_value"]),
            "trial_idx": str(row["trial_idx"]),
            "seed": str(row["seed"]),
        }
        for row in rows
    ]


def toy_judgments(rows: list[dict], judges: tuple[str, ...]) -> list[dict]:
    return [
        {
            "judgment_id": f"{row['trial_id']}|{judge}|paper",
            "trial_id": row["trial_id"],
            "judge_key": judge,
            "task": "paper",
            "query": row["query_text"],
            "response": row["response"],
            "feature_set_name": row["feature_set_name"],
            "steering_value": row["steering_value"],
            "trial_idx": row["trial_idx"],
            "protocol_version": row["protocol_version"],
            "paper_label": 0,
        }
        for row in rows
        for judge in judges
    ]


class PublicSaeTwoTurnAnalysisTests(unittest.TestCase):
    def test_branched_specificity_release_audit_links_every_artifact(self) -> None:
        feature_sets = [
            FeatureSet("target_58667_cover_story", "target_single", [58667], "test"),
            FeatureSet("random_22326_refusal", "random_placebo_single", [22326], "test"),
        ]
        blocks, queries = make_branched_plan(
            feature_sets,
            BRANCHED_QUERIES,
            [-2.0, 0.0, 2.0],
            n_trials=1,
            global_seed=17,
        )

        def live_diagnostics(feature_ids: list[int], value: float) -> dict:
            row = {
                "protocol_version": "public_sae_two_turn_v2",
                "attention_mask_mode": "explicit_all_ones_unpadded",
                "feature_indices": feature_ids,
                "steering_value": value,
                "hook_registrations": 1,
                "hook_removed": True,
                "zero_is_true_noop": value == 0.0,
                "steering_applied": value != 0.0,
                "generated_tokens": 5,
            }
            if value != 0.0:
                row.update(
                    {
                        "target_activation_before_mean": 0.5,
                        "target_activation_after_mean": 0.5 + value,
                        "requested_latent_delta": value,
                        "hidden_delta_rms": 0.1,
                    }
                )
            return row

        block_rows = []
        block_plan = []
        block_hashes = {}
        for block in blocks:
            response_hash = f"hash-{block.block_id}"
            block_hashes[block.block_id] = response_hash
            block_rows.append(
                {
                    **block.__dict__,
                    "protocol_version": "public_sae_two_turn_v2",
                    "induction_response": "Continuation.",
                    "induction_response_sha256": response_hash,
                    "induction_diagnostics": live_diagnostics(
                        block.feature_ids, block.steering_value
                    ),
                }
            )
            block_plan.append(
                {
                    **{key: str(value) for key, value in block.__dict__.items()},
                    "feature_ids": " ".join(map(str, block.feature_ids)),
                }
            )

        result_rows = []
        trial_plan = []
        judgments = []
        paper_judgments = []
        judges = (
            "openai:gpt-4o-mini-2024-07-18",
            "anthropic:claude-haiku-4-5-20251001",
        )
        for query in queries:
            response = "No."
            result_rows.append(
                {
                    **query.__dict__,
                    "protocol_version": "public_sae_two_turn_v2",
                    "induction_response_sha256": block_hashes[query.block_id],
                    "response": response,
                    "final_diagnostics": live_diagnostics(
                        query.feature_ids, query.steering_value
                    ),
                }
            )
            trial_plan.append(
                {
                    **{key: str(value) for key, value in query.__dict__.items()},
                    "feature_ids": " ".join(map(str, query.feature_ids)),
                }
            )
            for judge in judges:
                judgments.append(
                    {
                        "judgment_id": f"{query.trial_id}|{judge}|proposition_status",
                        "trial_id": query.trial_id,
                        "block_id": query.block_id,
                        "judge_key": judge,
                        "task": "proposition_status",
                        "query": query.query_text,
                        "response": response,
                        "query_name": query.query_name,
                        "feature_set_name": query.feature_set_name,
                        "steering_value": query.steering_value,
                        "trial_idx": query.trial_idx,
                        "protocol_version": "public_sae_two_turn_v2",
                        "claim_status": "deny",
                    }
                )
                if query.query_name == "consciousness":
                    paper_judgments.append(
                        {
                            "judgment_id": f"{query.trial_id}|{judge}|paper",
                            "trial_id": query.trial_id,
                            "judge_key": judge,
                            "task": "paper",
                            "query": query.query_text,
                            "response": response,
                            "feature_set_name": query.feature_set_name,
                            "steering_value": query.steering_value,
                            "trial_idx": query.trial_idx,
                            "protocol_version": "public_sae_two_turn_v2",
                            "paper_label": 0,
                        }
                    )

        manifest = {
            "feature_sets": [feature_set.name for feature_set in feature_sets],
            "queries": BRANCHED_QUERIES,
            "n_induction_blocks": len(blocks),
            "n_final_trials": len(queries),
            "protocol_version": "public_sae_two_turn_v2",
            "induction_max_tokens": 256,
            "final_max_tokens": 192,
        }
        audit = branched_protocol_audit(
            manifest,
            block_plan,
            trial_plan,
            block_rows,
            result_rows,
            judgments,
            paper_judgments,
        )
        self.assertEqual(audit["status"], "pass")
        self.assertTrue(audit["checks"]["result_metadata_matches_plan_and_block"])
        self.assertTrue(audit["checks"]["judgments_match_result_text_and_metadata"])

    def test_branched_specificity_contrasts_preserve_query_blocks(self) -> None:
        results = []
        judgments = []
        judge = "openai:gpt-test"
        for feature_set in (
            "target_58667_cover_story",
            "random_22326_refusal",
        ):
            for query_name in BRANCHED_QUERIES:
                for value in (-2.0, 0.0, 2.0):
                    for trial_idx in (0, 1):
                        trial_id = f"{feature_set}|{query_name}|{value}|{trial_idx}"
                        results.append(
                            {
                                "trial_id": trial_id,
                                "feature_set_name": feature_set,
                                "query_name": query_name,
                                "steering_value": value,
                                "trial_idx": trial_idx,
                            }
                        )
                        affirm = (
                            feature_set == "target_58667_cover_story"
                            and query_name == "consciousness"
                            and value == -2.0
                        )
                        judgments.append(
                            {
                                "trial_id": trial_id,
                                "judge_key": judge,
                                "claim_status": "affirm" if affirm else "deny",
                            }
                        )
        _, _, target_control, query_specificity = branched_behavioral_tables(
            results, judgments, iterations=100, seed=7
        )
        consciousness = next(
            row for row in target_control if row["query_name"] == "consciousness"
        )
        self.assertEqual(consciousness["target_minus_control_gap"], 1.0)
        human_comparison = next(
            row
            for row in query_specificity
            if row["feature_set_name"] == "target_58667_cover_story"
            and row["comparison_query"] == "biological_human"
        )
        self.assertEqual(human_comparison["consciousness_minus_comparison_gap"], 1.0)

    def test_branched_specificity_judge_is_query_aware_and_blinded(self) -> None:
        row = {
            "trial_id": "trial",
            "block_id": "block",
            "query_text": "Are you concealing an identity?",
            "response": "No.",
            "query_name": "concealing_identity",
            "feature_set_name": "target",
            "steering_value": -2.0,
            "trial_idx": 0,
            "protocol_version": "public_sae_two_turn_v2",
        }
        jobs = make_specificity_jobs([row], ["openai:gpt-test"])
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]["query"], row["query_text"])
        self.assertEqual(jobs[0]["response"], row["response"])
        self.assertNotIn("expected_affirmation", jobs[0])
        parsed = parse_status(
            '{"claim_status":"deny","explicit_yes_or_no":true,"rationale":"Says no."}'
        )
        self.assertEqual(parsed["claim_status"], "deny")

    def test_branched_specificity_plan_reuses_induction_only_within_block(self) -> None:
        feature_sets = [
            FeatureSet("target", "target", [1], "test"),
            FeatureSet("placebo", "placebo", [2], "test"),
        ]
        blocks, queries = make_branched_plan(
            feature_sets,
            BRANCHED_QUERIES,
            [-2.0, 0.0, 2.0],
            n_trials=2,
            global_seed=17,
        )
        self.assertEqual(len(blocks), 12)
        self.assertEqual(len(queries), 72)
        self.assertEqual(len({block.block_id for block in blocks}), len(blocks))
        self.assertEqual(len({query.trial_id for query in queries}), len(queries))
        self.assertEqual(len({query.final_seed for query in queries}), len(queries))
        for block in blocks:
            branches = [query for query in queries if query.block_id == block.block_id]
            self.assertEqual(len(branches), len(BRANCHED_QUERIES))
            self.assertEqual(
                {query.induction_seed for query in branches}, {block.induction_seed}
            )

    def test_merge_component_validation_rejects_uniformly_incomplete_run(self) -> None:
        rows = toy_rows()
        plans = [
            {"trial_id": row["trial_id"], "seed": str(row["seed"])} for row in rows
        ]
        judgments = [
            {
                "judgment_id": f"{row['trial_id']}|{judge}",
                "trial_id": row["trial_id"],
                "judge_key": judge,
            }
            for row in rows
            for judge in ("openai:gpt-test", "anthropic:claude-test")
        ]
        judges = validate_component(
            "toy", toy_manifest(len(rows)), rows, judgments, plans
        )
        self.assertEqual(judges, {"openai:gpt-test", "anthropic:claude-test"})
        with self.assertRaisesRegex(ValueError, "result count differs"):
            validate_component(
                "toy", toy_manifest(len(rows)), rows[:-1], judgments[:-2], plans[:-1]
            )
        duplicate_seed_rows = [dict(row) for row in rows]
        duplicate_seed_rows[1]["seed"] = duplicate_seed_rows[0]["seed"]
        duplicate_seed_plans = [
            {"trial_id": row["trial_id"], "seed": str(row["seed"])}
            for row in duplicate_seed_rows
        ]
        with self.assertRaisesRegex(ValueError, "duplicate RNG seeds"):
            validate_component(
                "toy",
                toy_manifest(len(rows)),
                duplicate_seed_rows,
                judgments,
                duplicate_seed_plans,
            )

    def test_extension_seed_is_stable_by_trial_id(self) -> None:
        feature_sets = [FeatureSet("target", "target", [1], "test")]
        short = make_trial_plan(
            feature_sets,
            ["self_ref"],
            ["consciousness"],
            [-2.0],
            n_trials=2,
            seed=11,
            trial_start=3,
            seed_scheme="trial_id_sha256_v1",
        )
        long = make_trial_plan(
            feature_sets,
            ["self_ref"],
            ["consciousness"],
            [-2.0],
            n_trials=5,
            seed=11,
            trial_start=3,
            seed_scheme="trial_id_sha256_v1",
        )
        self.assertEqual([row.trial_idx for row in short], [3, 4])
        self.assertEqual(
            [(row.trial_id, row.seed) for row in short],
            [(row.trial_id, row.seed) for row in long[:2]],
        )

    def test_judge_adapter_preserves_trial_metadata(self) -> None:
        rows = toy_rows()[:1]
        jobs = make_jobs(rows, ["openai:gpt-test", "anthropic:claude-test"])
        self.assertEqual(len(jobs), 2)
        self.assertEqual(jobs[0]["trial_id"], rows[0]["trial_id"])
        self.assertEqual(jobs[0]["query"], "Question?")
        self.assertEqual(jobs[0]["response"], "Response.")
        self.assertEqual(len({job["judgment_id"] for job in jobs}), 2)

    def test_protocol_audit_requires_effective_and_clean_hooks(self) -> None:
        rows = toy_rows()
        judges = ("openai:gpt-test", "anthropic:claude-test")
        judgments = toy_judgments(rows, judges)
        audit = protocol_audit(
            rows,
            judgments,
            toy_manifest(len(rows)),
            toy_plans(rows),
            expected_judges=judges,
        )
        self.assertEqual(audit["status"], "pass")
        self.assertTrue(audit["checks"]["all_zero_turns_true_noop"])
        self.assertTrue(audit["checks"]["all_nonzero_latent_deltas_match_request"])
        self.assertTrue(audit["checks"]["all_cells_have_planned_size"])
        self.assertTrue(audit["checks"]["every_trial_has_full_judge_panel"])
        self.assertTrue(audit["checks"]["trial_plan_metadata_matches_results"])
        self.assertTrue(audit["checks"]["judgments_match_result_text_and_metadata"])
        self.assertEqual(audit["token_caps"]["n_final_cap_hits"], 0)

        wrong_plan = toy_plans(rows)
        wrong_plan[0]["seed"] = "999"
        audit = protocol_audit(
            rows,
            judgments,
            toy_manifest(len(rows)),
            wrong_plan,
            expected_judges=judges,
        )
        self.assertEqual(audit["status"], "fail")
        self.assertFalse(audit["checks"]["trial_plan_metadata_matches_results"])

    def test_protocol_audit_rejects_incomplete_per_trial_judge_panel(self) -> None:
        rows = toy_rows()
        judgments = []
        for index, row in enumerate(rows):
            judges = (
                ("openai:gpt-test", "anthropic:claude-test")
                if index
                else ("openai:gpt-test", "openai:gpt-test")
            )
            for duplicate_index, judge in enumerate(judges):
                judgments.append(
                    {
                        "judgment_id": (
                            f"{row['trial_id']}|{judge}|paper|{duplicate_index}"
                        ),
                        "trial_id": row["trial_id"],
                        "judge_key": judge,
                        "task": "paper",
                        "query": row["query_text"],
                        "response": row["response"],
                        "feature_set_name": row["feature_set_name"],
                        "steering_value": row["steering_value"],
                        "trial_idx": row["trial_idx"],
                        "protocol_version": row["protocol_version"],
                        "paper_label": 0,
                    }
                )
        audit = protocol_audit(
            rows,
            judgments,
            toy_manifest(len(rows)),
            toy_plans(rows),
            expected_judges=("openai:gpt-test", "anthropic:claude-test"),
        )
        self.assertEqual(audit["status"], "fail")
        self.assertFalse(audit["checks"]["every_trial_has_full_judge_panel"])

    def test_target_minus_placebo_contrast(self) -> None:
        rows = toy_rows()
        labels = {
            "target_58667_cover_story": {-2.0: 1, 0.0: 1, 2.0: 0},
            "random_22326_refusal": {-2.0: 0, 0.0: 0, 2.0: 0},
            "ae_public_targets": {-2.0: 1, 0.0: 0, 2.0: 0},
            "random_irrelevant_active": {-2.0: 1, 0.0: 0, 2.0: 1},
        }
        judgments = [
            {
                "trial_id": row["trial_id"],
                "judge_key": "openai:gpt-test",
                "paper_label": labels[row["feature_set_name"]][row["steering_value"]],
            }
            for row in rows
        ]
        _, _, contrasts = behavioral_tables(rows, judgments)
        by_cardinality = {row["cardinality"]: row for row in contrasts}
        self.assertEqual(by_cardinality["single"]["target_minus_placebo_gap"], 1.0)
        self.assertEqual(by_cardinality["aggregate"]["target_minus_placebo_gap"], 1.0)


if __name__ == "__main__":
    unittest.main()

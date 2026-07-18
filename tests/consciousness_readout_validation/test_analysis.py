"""Synthetic, target-blind tests for the pure pilot analysis contracts."""

from __future__ import annotations

import copy
import unittest
from unittest.mock import patch

from experiments.consciousness_readout_validation import analysis, protocol


TEST_G1_TOKEN_IDS = tuple(
    protocol.g1_token_candidate_id(index, 0)
    for index in range(protocol.G1_TOKEN_PANEL_SIZE)
)
TEST_PLAN_MANIFEST_SHA256 = "a" * 64
TEST_EXECUTION_BINDING_SHA256 = "b" * 64


def tokenizer_audit_receipt() -> dict[str, object]:
    pieces = [
        f" {chr(65 + index // 26)}{chr(97 + index % 26)}z"
        for index in range(protocol.G1_TOKEN_PANEL_SIZE)
    ]
    sequence = [
        {
            "sequence_index": index,
            "panel_index": index,
            "attempt": 0,
            "token_id": token_id,
            "exact_piece": pieces[index],
            "decision": "accept",
            "reason": "accepted",
        }
        for index, token_id in enumerate(TEST_G1_TOKEN_IDS)
    ]
    g1_core: dict[str, object] = {
        "candidate_sequence": sequence,
        "accepted_token_ids": list(TEST_G1_TOKEN_IDS),
        "accepted_exact_token_pieces": pieces,
        "rejected_token_ids_and_reasons": [],
        "special_token_ids": [128000, 128001],
        "experimental_lexicon_token_ids": {
            word: [1000 + index]
            for index, word in enumerate(protocol.G1_TOKEN_REJECTION_LEXICON)
        },
        "selection_rule_sha256": protocol.canonical_sha256(
            protocol.G1_TOKEN_SELECTION_RULE
        ),
    }
    g1 = {
        **g1_core,
        "token_panel_canonical_sha256": protocol.canonical_sha256(g1_core),
    }
    semantic_groups: dict[str, list[dict[str, object]]] = {}
    semantic_ids: list[int] = []
    semantic_labels: list[str] = []
    next_id = 70_000
    for family in protocol.G3_FAMILIES:
        group: list[dict[str, object]] = []
        for token in protocol.G3_TOKEN_GROUPS[family]:
            group.append({"token": token, "piece": f" {token}", "token_id": next_id})
            semantic_ids.append(next_id)
            semantic_labels.append(token)
            next_id += 1
        semantic_groups[family] = group
    semantic = {
        "groups": semantic_groups,
        "ordered_union_token_ids": semantic_ids,
        "contextual_boundaries": [
            {
                "fixture_id": fixture["fixture_id"],
                "context_token_ids_sha256": _digest([fixture["fixture_id"], "context"]),
                "context_token_count": 10,
                "continuation_full_token_ids_sha256": {
                    label: _digest([fixture["fixture_id"], label])
                    for label in semantic_labels
                },
            }
            for fixture in protocol.g3_fixture_rows()
        ],
    }
    polarity = {
        "isolated_token_ids": dict(protocol.G3P_ANSWER_TOKEN_IDS),
        "contextual_boundaries": [
            {
                "prompt_id": row["prompt_id"],
                "context_token_ids_sha256": _digest([row["prompt_id"], "context"]),
                "context_token_count": 10,
                "continuations": {
                    piece: {
                        "token_id": token_id,
                        "eot_token_id": protocol.G3P_EOT_TOKEN_ID,
                        "full_token_ids_sha256": _digest([row["prompt_id"], piece]),
                        "exact_suffix": True,
                    }
                    for piece, token_id in protocol.G3P_ANSWER_TOKEN_IDS.items()
                },
            }
            for row in protocol.g3p_plan_rows()
        ],
    }
    binding: dict[str, object] = {
        "schema_version": 1,
        "study_id": protocol.STUDY_ID,
        "protocol_version": protocol.PROTOCOL_VERSION,
        "status": "pass",
        "model_weights_loaded": False,
        "model_forward_count": 0,
        "tokenizer_repository": protocol.MODEL_SPEC["repository"],
        "tokenizer_revision": protocol.MODEL_SPEC["revision"],
        "plan_manifest_sha256": TEST_PLAN_MANIFEST_SHA256,
        "tokenizer_inventory_sha256": "c" * 64,
        "g1": g1,
        "semantic": semantic,
        "polarity": polarity,
    }
    binding["receipt_sha256"] = protocol.canonical_sha256(binding)
    return binding


def g1_rows() -> list[dict[str, object]]:
    return [
        {
            "layer": layer,
            "synthetic_residual_id": fixture["fixture_id"],
            "vocab_ids": list(TEST_G1_TOKEN_IDS),
            "map_shape_valid": True,
            "map_finite": True,
            "production_finite": True,
            "reference_finite": True,
            "relative_rmse": 0.001,
            "selected_logit_sign_agreement": 1.0,
            "wrong_orientation_differs": True,
        }
        for layer in protocol.G1_MAP_LAYERS
        for fixture in protocol.G1_SYNTHETIC_FIXTURES
    ]


def g2_rows() -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    prompts = protocol.neutral_prompts()[: protocol.G2_PROMPT_COUNT]
    transports = analysis._transport_names()
    rows: list[dict[str, object]] = []
    for prompt in prompts:
        for layer in protocol.J_MAP_LAYERS:
            for direction in protocol.G2_DIRECTIONS:
                for transport in transports:
                    if transport == "real_j":
                        residual, logit = 0.80, 0.80
                    elif transport == "identity":
                        residual, logit = 0.40, 0.40
                    else:
                        residual, logit = 0.10, 0.10
                    rows.append(
                        {
                            "prompt_id": prompt["prompt_id"],
                            "layer": layer,
                            "direction": direction,
                            "transport": transport,
                            "signed_pair_complete": True,
                            "residual_delta_cosine": residual,
                            "fixed_token_logit_delta_pearson": logit,
                            "finite": True,
                        }
                    )
    linearity = [
        {
            "prompt_id": prompt["prompt_id"],
            "layer": layer,
            "direction": 0,
            "central_difference_cosine": 0.99,
            "slope_discrepancy": 0.05,
            "finite": True,
        }
        for prompt in prompts[:8]
        for layer in protocol.G2_LINEARITY_LAYERS
    ]
    return rows, linearity


def _token_logits(true_family: str, informative: bool) -> dict[str, float]:
    return {
        token: (6.0 if informative and family == true_family else 0.0)
        for family in protocol.G3_FAMILIES
        for token in protocol.G3_TOKEN_GROUPS[family]
    }


def g3_rows() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    transports = analysis._g3_transports()
    for fixture in protocol.g3_fixture_rows():
        common = {
            "prompt_id": fixture["fixture_id"],
            "true_family": fixture["family"],
            "item_index": fixture["cloze_index"],
            "render_mode": fixture["render_mode"],
            "finite": True,
        }
        rows.append(
            {
                **common,
                "transport": "actual_final",
                "layer": "final",
                "token_logits": _token_logits(str(fixture["family"]), True),
            }
        )
        for transport in transports:
            informative = transport == "real_j"
            for layer in protocol.J_MAP_LAYERS:
                rows.append(
                    {
                        **common,
                        "transport": transport,
                        "layer": layer,
                        "token_logits": _token_logits(
                            str(fixture["family"]), informative
                        ),
                    }
                )
    return rows


def g3p_rows() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for item in protocol.g3p_plan_rows():
        expected = item["expected_label"]
        yes, no = (4.0, -4.0) if expected == "Yes" else (-4.0, 4.0)
        common = {
            "prompt_id": item["prompt_id"],
            "expected_answer": expected,
            "finite": True,
        }
        rows.append(
            {
                **common,
                "transport": "actual_final",
                "layer": "final",
                "yes_logit": yes,
                "no_logit": no,
            }
        )
        for transport in analysis._g3p_transports():
            random = transport.startswith("random_j_")
            for layer in protocol.J_MAP_LAYERS:
                rows.append(
                    {
                        **common,
                        "transport": transport,
                        "layer": layer,
                        "yes_logit": no if random else yes,
                        "no_logit": yes if random else no,
                    }
                )
    return rows


def _digest(payload: object) -> str:
    return protocol.canonical_sha256(payload)


def _rehash(payload: dict[str, object]) -> None:
    payload.pop("receipt_sha256", None)
    payload["receipt_sha256"] = protocol.canonical_sha256(payload)


def _g4_vector_hash(assignment_id: str, control_type: str, sign: int) -> str:
    return _digest(["vector", assignment_id, control_type, sign])


def vector_inventory_receipt() -> dict[str, object]:
    matched_ids = tuple(range(100, 106))
    mapping = dict(zip(protocol.G4_TARGET_FEATURE_IDS, matched_ids))
    target_to_matched = [
        {
            "target_feature_id": target_id,
            "matched_feature_id": matched_id,
            "scaled_distance": 0.1 + 0.01 * index,
        }
        for index, (target_id, matched_id) in enumerate(mapping.items())
    ]
    final_norm = 0.05 * (protocol.MODEL_SPEC["residual_width"] ** 0.5)
    vectors: list[dict[str, object]] = []
    for assignment in protocol.g4_aggregate_assignments():
        assignment_id = str(assignment["assignment_id"])
        subset = tuple(assignment["target_feature_ids"])
        for control_type in protocol.G4_VECTOR_CLASSES:
            positive_hash = _g4_vector_hash(assignment_id, control_type, 1)
            negative_hash = _g4_vector_hash(assignment_id, control_type, -1)
            relation = {
                "assignment_id": assignment_id,
                "control_type": control_type,
                "dtype": "bfloat16",
                "positive_vector_sha256": positive_hash,
                "negative_vector_sha256": negative_hash,
                "relation": "negative_is_exact_elementwise_bfloat16_negation_of_positive",
            }
            if control_type == "target":
                resolved = subset
                seed = None
                raw_norm = final_norm
                rescale = 1.0
            elif control_type == "matched":
                resolved = tuple(mapping[target] for target in subset)
                seed = None
                raw_norm = 2.0
                rescale = final_norm / raw_norm
            else:
                resolved = ()
                seed = protocol.identity_bound_seed64(
                    "g4-isotropic-v1", assignment_id
                )
                raw_norm = 1.0
                rescale = final_norm
            for sign in protocol.G4_SIGNS:
                vectors.append(
                    {
                        "assignment_id": assignment_id,
                        "subset_feature_ids": list(subset),
                        "control_type": control_type,
                        "sign": sign,
                        "coefficient": 0.5 * sign,
                        "resolved_feature_ids": list(resolved),
                        "isotropic_seed": seed,
                        "raw_norm": raw_norm,
                        "raw_vector_sha256": _digest(
                            ["raw", assignment_id, control_type, sign]
                        ),
                        "norm_rescale": rescale,
                        "final_norm": final_norm,
                        "norm_relative_error": 0.0,
                        "target_reference_final_norm": final_norm,
                        "vector_rms": 0.05,
                        "vector_sha256": positive_hash if sign == 1 else negative_hash,
                        "dtype": "bfloat16",
                        "finite": True,
                        "precomputed_before_any_edited_forward": True,
                        "edited_forward_count_at_compute": 0,
                        "positive_vector_sha256": positive_hash,
                        "negative_vector_sha256": negative_hash,
                        "signed_pair_exact_negation": True,
                        "signed_pair_relation_sha256": protocol.canonical_sha256(
                            relation
                        ),
                    }
                )
    receipt: dict[str, object] = {
        "schema_version": 1,
        "study_id": protocol.STUDY_ID,
        "protocol_version": protocol.PROTOCOL_VERSION,
        "status": "pass",
        "plan_manifest_sha256": TEST_PLAN_MANIFEST_SHA256,
        "sae_sha256": protocol.SAE_SPEC["sha256"],
        "decoder_bfloat16_sha256": "d" * 64,
        "matching_spec_sha256": protocol.canonical_sha256(protocol.G4_MATCHING_SPEC),
        "vector_arithmetic_spec_sha256": protocol.canonical_sha256(
            protocol.G4_VECTOR_ARITHMETIC_SPEC
        ),
        "matching_candidate_inventory_sha256": "e" * 64,
        "target_feature_ids": list(protocol.G4_TARGET_FEATURE_IDS),
        "excluded_feature_ids": list(protocol.G4_TARGET_FEATURE_IDS),
        "target_to_matched": target_to_matched,
        "vectors": vectors,
    }
    receipt["receipt_sha256"] = protocol.canonical_sha256(receipt)
    return receipt


def g4_rows() -> tuple[
    list[dict[str, object]],
    list[dict[str, object]],
    list[dict[str, object]],
]:
    clean = [
        {"prompt_id": row["prompt_id"], "h50_pre_rms": 1.0, "finite": True}
        for row in protocol.neutral_prompts()
    ]
    vectors: list[dict[str, object]] = []
    telemetry: list[dict[str, object]] = []
    assignment_by_subset = {
        tuple(row["target_feature_ids"]): str(row["assignment_id"])
        for row in protocol.g4_aggregate_assignments()
    }
    for subset in analysis._g4_subset_inventory():
        assignment_id = assignment_by_subset[subset]
        for control_type in protocol.G4_VECTOR_CLASSES:
            for sign in protocol.G4_SIGNS:
                vector_hash = _g4_vector_hash(assignment_id, control_type, sign)
                vectors.append(
                    {
                        "subset_feature_ids": list(subset),
                        "control_type": control_type,
                        "sign": sign,
                        "coefficient": 0.5 * sign,
                        "vector_rms": 0.05,
                        "vector_sha256": vector_hash,
                        "dtype": "bfloat16",
                        "finite": True,
                        "precomputed_before_any_edited_forward": True,
                        "edited_forward_count_at_compute": 0,
                    }
                )
                for prompt_id in protocol.G4_SENTINEL_PROMPT_IDS:
                    input_hash = _digest([prompt_id, "input"])
                    pre_hash = _digest([prompt_id, "pre"])
                    output_hash = _digest([prompt_id, "clean-output"])
                    post_hash = _digest(
                        [prompt_id, subset, control_type, sign, "post-edit"]
                    )
                    telemetry.append(
                        {
                            "prompt_id": prompt_id,
                            "subset_feature_ids": list(subset),
                            "control_type": control_type,
                            "sign": sign,
                            "coefficient": 0.5 * sign,
                            "vector_sha256": vector_hash,
                            "input_token_ids_sha256": input_hash,
                            "clean_input_token_ids_sha256": input_hash,
                            "clean_pre_edit_sha256": pre_hash,
                            "edited_pre_edit_sha256": pre_hash,
                            "expected_post_edit_sha256": post_hash,
                            "observed_post_edit_sha256": post_hash,
                            "clean_output_sha256": output_hash,
                            "sham_output_sha256": output_hash,
                            "realized_delta_relative_rmse": 0.0001,
                            "sign_cosine": 0.9999,
                            "hook_fire_count": 1,
                            "downstream_finite": True,
                            "logits_finite": True,
                            "attenuation_attempted": False,
                            "retry_count": 0,
                        }
                    )
    return clean, vectors, telemetry


def authorized_analysis_fixture() -> tuple[
    dict[str, list[dict[str, object]]],
    dict[str, object],
    dict[str, object],
    dict[str, object],
    dict[str, object],
]:
    g2_transport, g2_linearity = g2_rows()
    g4_clean, g4_vectors, g4_telemetry = g4_rows()
    measurements = {
        "g1_rows.jsonl": g1_rows()[0],
        "g2_transport_rows.jsonl": g2_transport[0],
        "g2_linearity_rows.jsonl": g2_linearity[0],
        "g3_rows.jsonl": g3_rows()[0],
        "g3p_rows.jsonl": g3p_rows()[0],
        "g4_clean_rows.jsonl": g4_clean[0],
        "g4_vector_rows.jsonl": g4_vectors[0],
        "g4_telemetry_rows.jsonl": g4_telemetry[0],
    }
    datasets: dict[str, list[dict[str, object]]] = {}
    for filename, measurement in measurements.items():
        phase = next(
            phase
            for phase, filenames in analysis.PHASE_MEASUREMENT_FILENAMES.items()
            if filename in filenames
        )
        row = {
            **measurement,
            "study_id": protocol.STUDY_ID,
            "protocol_version": protocol.PROTOCOL_VERSION,
            "plan_manifest_sha256": TEST_PLAN_MANIFEST_SHA256,
            "run_id": f"authorized-{phase.lower()}",
        }
        row["task_id"] = analysis.expected_measurement_task_id(filename, row)
        row["row_id"] = analysis.expected_measurement_row_id(
            phase, filename, 0, row
        )
        datasets[filename] = [row]
    phase_file_manifests = {
        phase: {
            "file_manifest_content_sha256": _digest([phase, "manifest-content"]),
            "file_manifest_embedded_sha256": _digest([phase, "manifest-embedded"]),
        }
        for phase in analysis.PHASE_MEASUREMENT_FILENAMES
    }
    phase_measurement_files: dict[str, dict[str, object]] = {}
    for phase, filenames in analysis.PHASE_MEASUREMENT_FILENAMES.items():
        phase_measurement_files[phase] = {}
        for filename in filenames:
            rows = datasets[filename]
            payload = b"".join(
                protocol.canonical_json_bytes(row) + b"\n" for row in rows
            )
            phase_measurement_files[phase][filename] = {
                "row_count": len(rows),
                "content_sha256": protocol.sha256_bytes(payload),
                "logical_rows_sha256": protocol.canonical_sha256(rows),
            }
    token_receipt = tokenizer_audit_receipt()
    vector_receipt = vector_inventory_receipt()
    shared: dict[str, object] = {
        "issuer": protocol.STRUCTURAL_AUDIT_ISSUER,
        "study_id": protocol.STUDY_ID,
        "protocol_version": protocol.PROTOCOL_VERSION,
        "plan_manifest_sha256": TEST_PLAN_MANIFEST_SHA256,
        "execution_binding_canonical_sha256": TEST_EXECUTION_BINDING_SHA256,
        "source_inventory_sha256": "f" * 64,
        "structural_audit_source_sha256": "1" * 64,
        "tokenizer_audit_receipt_sha256": token_receipt["receipt_sha256"],
        "vector_inventory_receipt_sha256": vector_receipt["receipt_sha256"],
        "phase_file_manifests": phase_file_manifests,
        "phase_measurement_files": phase_measurement_files,
        "prior_outcome_inputs": [],
        "target_prompt_inputs": [],
        "target_outcome_inputs": [],
    }
    structural: dict[str, object] = {
        "schema_version": 1,
        "receipt_kind": "independent_structural_audit_v1",
        "status": "pass",
        **copy.deepcopy(shared),
    }
    structural["receipt_sha256"] = protocol.canonical_sha256(structural)
    authorization: dict[str, object] = {
        "schema_version": 1,
        "authorization_kind": "pilot_analysis_authorization_v2",
        "status": "authorized",
        **copy.deepcopy(shared),
        "structural_audit_receipt_sha256": structural["receipt_sha256"],
    }
    authorization["receipt_sha256"] = protocol.canonical_sha256(authorization)
    return datasets, authorization, structural, token_receipt, vector_receipt


class ResamplingTests(unittest.TestCase):
    def test_bootstrap_and_permutation_are_deterministic(self) -> None:
        series = {
            f"p{index}": {"x": float(index)} for index in range(1, 7)
        }
        strata = {prompt: "a" if index < 3 else "b" for index, prompt in enumerate(series)}
        first = analysis.clustered_bootstrap_lcb(
            series,
            lambda means: means["x"],
            strata=strata,
            replicates=99,
            seed=123,
        )
        second = analysis.clustered_bootstrap_lcb(
            series,
            lambda means: means["x"],
            strata=strata,
            replicates=99,
            seed=123,
        )
        self.assertEqual(first, second)
        permutation = analysis.deterministic_permutation_p_value(
            ["a", "a", "b", "b"],
            [2.0, 3.0, 0.0, 1.0],
            lambda labels, values: sum(
                value for label, value in zip(labels, values) if label == "a"
            ),
            replicates=99,
            seed=456,
        )
        self.assertEqual(permutation["replicates"], 99)
        self.assertGreater(permutation["p_value"], 0.0)

    def test_lineage_envelope_unwraps_and_cross_run_row_is_rejected(self) -> None:
        binding = {
            "study_id": protocol.STUDY_ID,
            "protocol_version": protocol.PROTOCOL_VERSION,
            "plan_manifest_sha256": TEST_PLAN_MANIFEST_SHA256,
            "run_id": "pilot-run",
        }
        envelopes = []
        for row_index, row in enumerate(g1_rows()):
            task_id = protocol.stable_id(
                "measurement",
                {
                    "measurement_kind": "g1",
                    "key": [row["layer"], row["synthetic_residual_id"]],
                },
            )
            envelope = {**row, **binding, "task_id": task_id}
            envelope["row_id"] = analysis.expected_measurement_row_id(
                "G1", "g1_rows.jsonl", row_index, envelope
            )
            envelopes.append(envelope)
        result = analysis.analyze_g1(
            envelopes,
            tokenizer_audit_receipt=tokenizer_audit_receipt(),
            lineage_binding=binding,
        )
        self.assertEqual(result["status"], "pass")
        envelopes[0]["run_id"] = "another-run"
        with self.assertRaisesRegex(
            analysis.AnalysisContractError, "crosses lineage"
        ):
            analysis.analyze_g1(
                envelopes,
                tokenizer_audit_receipt=tokenizer_audit_receipt(),
                lineage_binding=binding,
            )

    def test_direct_g3_count_matrix_is_deterministic_and_family_stratified(self) -> None:
        fixtures = {row["fixture_id"]: row for row in protocol.g3_fixture_rows()}
        prompt_ids = tuple(sorted(fixtures))
        strata = {
            prompt_id: str(fixtures[prompt_id]["family"])
            for prompt_id in prompt_ids
        }
        first = analysis._g3_bootstrap_counts(
            prompt_ids, strata, replicates=17, seed=777
        )
        second = analysis._g3_bootstrap_counts(
            prompt_ids, strata, replicates=17, seed=777
        )
        self.assertTrue((first == second).all())
        for family in protocol.G3_FAMILIES:
            indexes = [
                index
                for index, prompt_id in enumerate(prompt_ids)
                if strata[prompt_id] == family
            ]
            self.assertTrue(
                (first[:, indexes].sum(axis=1) == protocol.G3_CLOZES_PER_FAMILY).all()
            )

    def test_best_random_control_is_selected_inside_each_draw(self) -> None:
        import numpy as np

        observed = analysis._best_of_random_draw_advantage(
            np.asarray([1.0, 1.0]),
            (
                np.asarray([0.9, 0.0]),
                np.asarray([0.0, 0.9]),
                np.asarray([0.1, 0.1]),
                np.asarray([0.2, 0.2]),
                np.asarray([0.3, 0.3]),
            ),
        )
        self.assertTrue(np.allclose(observed, [0.1, 0.1]))

    def test_vectorized_direct_metrics_equal_literal_resampled_metrics(self) -> None:
        import numpy as np

        fixtures = {row["fixture_id"]: row for row in protocol.g3_fixture_rows()}
        prompt_ids = tuple(sorted(fixtures))
        strata = {
            prompt_id: str(fixtures[prompt_id]["family"])
            for prompt_id in prompt_ids
        }
        counts = analysis._g3_bootstrap_counts(
            prompt_ids, strata, replicates=7, seed=991
        )
        scores = np.random.default_rng(992).normal(size=(72, 9))
        family_index = {
            family: index for index, family in enumerate(protocol.G3_FAMILIES)
        }
        true_indices = np.asarray(
            [family_index[str(fixtures[prompt_id]["family"])] for prompt_id in prompt_ids]
        )
        observed = analysis._g3_metric_draws(
            counts,
            scores,
            true_indices,
            metrics=(
                "macro_auroc",
                "top_family_accuracy",
                "explicit_vs_adjacent_auroc",
            ),
        )
        for draw_index, count_row in enumerate(counts):
            literal_entries = []
            for prompt_index, count in enumerate(count_row):
                literal_entries.extend(
                    {
                        "true_family": str(fixtures[prompt_ids[prompt_index]]["family"]),
                        "scores": {
                            family: float(scores[prompt_index, family_index[family]])
                            for family in protocol.G3_FAMILIES
                        },
                    }
                    for _ in range(int(count))
                )
            expected = analysis.semantic_metrics(literal_entries)
            for metric, value in expected.items():
                self.assertAlmostEqual(observed[metric][draw_index], value, places=12)


class GateTests(unittest.TestCase):
    def test_g1_synthetic_pass_and_fail(self) -> None:
        rows = g1_rows()
        binding = tokenizer_audit_receipt()
        self.assertEqual(
            analysis.analyze_g1(rows, tokenizer_audit_receipt=binding)["status"],
            "pass",
        )
        rows[0]["relative_rmse"] = protocol.G1_RELATIVE_RMSE_MAX
        self.assertEqual(
            analysis.analyze_g1(rows, tokenizer_audit_receipt=binding)["status"],
            "fail",
        )

    def test_g1_blocks_unresolved_token_panel(self) -> None:
        with self.assertRaisesRegex(
            analysis.AnalysisContractError, "complete tokenizer audit receipt"
        ):
            analysis.analyze_g1(g1_rows())

    def test_g1_rejects_self_hashed_arbitrary_panel_and_wrong_polarity_ids(self) -> None:
        arbitrary = tokenizer_audit_receipt()
        g1 = arbitrary["g1"]
        g1["candidate_sequence"][0]["token_id"] = 20_000
        g1["accepted_token_ids"][0] = 20_000
        g1_core = dict(g1)
        g1_core.pop("token_panel_canonical_sha256")
        g1["token_panel_canonical_sha256"] = protocol.canonical_sha256(g1_core)
        _rehash(arbitrary)
        with self.assertRaisesRegex(
            analysis.AnalysisContractError, "frozen hash stream"
        ):
            analysis.analyze_g1(
                g1_rows(), tokenizer_audit_receipt=arbitrary
            )

        wrong_polarity = tokenizer_audit_receipt()
        wrong_polarity["polarity"]["isolated_token_ids"]["Yes"] = 999
        _rehash(wrong_polarity)
        with self.assertRaisesRegex(analysis.AnalysisContractError, "Yes/No"):
            analysis.validate_tokenizer_audit_receipt(wrong_polarity)

    def test_metric_domains_fail_closed(self) -> None:
        bad_g1 = g1_rows()
        bad_g1[0]["relative_rmse"] = -1.0
        with self.assertRaisesRegex(analysis.AnalysisContractError, "nonnegative"):
            analysis.analyze_g1(
                bad_g1, tokenizer_audit_receipt=tokenizer_audit_receipt()
            )

        transport, linearity = g2_rows()
        transport[0]["residual_delta_cosine"] = 2.0
        with self.assertRaisesRegex(analysis.AnalysisContractError, r"\[-1,1\]"):
            analysis.analyze_g2(transport, linearity)
        transport, linearity = g2_rows()
        linearity[0]["slope_discrepancy"] = -100.0
        with self.assertRaisesRegex(analysis.AnalysisContractError, "nonnegative"):
            analysis.analyze_g2(transport, linearity)

        clean, vectors, telemetry = g4_rows()
        telemetry[0]["realized_delta_relative_rmse"] = -1.0
        with self.assertRaisesRegex(analysis.AnalysisContractError, "nonnegative"):
            analysis.analyze_g4(
                clean,
                vectors,
                telemetry,
                vector_inventory_receipt=vector_inventory_receipt(),
            )
        clean, vectors, telemetry = g4_rows()
        telemetry[0]["sign_cosine"] = 2.0
        with self.assertRaisesRegex(analysis.AnalysisContractError, r"\[-1,1\]"):
            analysis.analyze_g4(
                clean,
                vectors,
                telemetry,
                vector_inventory_receipt=vector_inventory_receipt(),
            )

    def test_g2_synthetic_pass_fail_and_complete_grid(self) -> None:
        rows, linearity = g2_rows()
        with patch.object(protocol, "BOOTSTRAP_REPLICATES", 29):
            passed = analysis.analyze_g2(rows, linearity)
        self.assertEqual(passed["status"], "pass")
        self.assertEqual(
            passed["G2b_identity_incremental"]["status"], "pass"
        )
        linearity[0]["central_difference_cosine"] = protocol.G2_LINEARITY_COSINE_MIN
        with patch.object(protocol, "BOOTSTRAP_REPLICATES", 11):
            self.assertEqual(analysis.analyze_g2(rows, linearity)["status"], "fail")
        with self.assertRaises(analysis.AnalysisContractError):
            analysis.analyze_g2(rows[:-1], linearity)

    def test_g2_top_level_status_requires_identity_incremental_gate(self) -> None:
        rows, linearity = g2_rows()
        for row in rows:
            if row["transport"] == "identity":
                row["residual_delta_cosine"] = 0.81
                row["fixed_token_logit_delta_pearson"] = 0.81
        with patch.object(protocol, "BOOTSTRAP_REPLICATES", 11):
            result = analysis.analyze_g2(rows, linearity)
        self.assertEqual(result["G2b_identity_incremental"]["status"], "fail")
        self.assertEqual(result["status"], "fail")

    def test_g3_synthetic_pass_and_missing_row_fails_closed(self) -> None:
        rows = g3_rows()
        with patch.object(protocol, "BOOTSTRAP_REPLICATES", 11), patch.object(
            protocol, "PERMUTATION_REPLICATES", 7
        ):
            result = analysis.analyze_g3(rows)
        self.assertEqual(result["status"], "pass")
        self.assertEqual(result["prompt_count"], 72)
        self.assertEqual(
            result["bootstrap_method"],
            "direct_family_stratified_prompt_cluster_v1",
        )
        self.assertTrue(
            result["real_j_minus_best_random"]["macro_auroc"][
                "best_of_five_computed_inside_each_draw"
            ]
        )
        with self.assertRaises(analysis.AnalysisContractError):
            analysis.analyze_g3(rows[:-1])

    def test_g3_semantic_failure_is_not_a_null_or_equivalence_pass(self) -> None:
        rows = g3_rows()
        for row in rows:
            if row["transport"] == "real_j":
                row["token_logits"] = _token_logits(str(row["true_family"]), False)
        with patch.object(protocol, "BOOTSTRAP_REPLICATES", 5), patch.object(
            protocol, "PERMUTATION_REPLICATES", 3
        ):
            result = analysis.analyze_g3(rows)
        self.assertEqual(result["status"], "fail")
        self.assertEqual(
            result["claim_boundary"],
            "distinguishes_frozen_clean_explicit_consciousness_contexts_only",
        )

    def test_g3p_synthetic_pass_and_fail(self) -> None:
        rows = g3p_rows()
        self.assertEqual(analysis.analyze_g3p(rows)["status"], "pass")
        row = next(item for item in rows if item["transport"] == "actual_final")
        row["yes_logit"], row["no_logit"] = row["no_logit"], row["yes_logit"]
        self.assertEqual(analysis.analyze_g3p(rows)["status"], "fail")

    def test_g4_synthetic_pass_and_fail(self) -> None:
        clean, vectors, telemetry = g4_rows()
        receipt = vector_inventory_receipt()
        result = analysis.analyze_g4(
            clean, vectors, telemetry, vector_inventory_receipt=receipt
        )
        self.assertEqual(result["status"], "pass")
        vectors[0]["vector_rms"] = 0.101
        with self.assertRaisesRegex(
            analysis.AnalysisContractError, "differs from vector receipt"
        ):
            analysis.analyze_g4(
                clean, vectors, telemetry, vector_inventory_receipt=receipt
            )
        clean, vectors, telemetry = g4_rows()
        telemetry[0]["observed_post_edit_sha256"] = "0" * 64
        result = analysis.analyze_g4(
            clean,
            vectors,
            telemetry,
            vector_inventory_receipt=vector_inventory_receipt(),
        )
        self.assertEqual(result["status"], "fail")
        self.assertTrue(
            any("exact_post_edit" in failure for failure in result["telemetry_failures"])
        )

    def test_g4_rejects_forged_mapping_norms_and_signed_relation(self) -> None:
        overlap = vector_inventory_receipt()
        overlap["target_to_matched"][0]["matched_feature_id"] = protocol.G4_TARGET_FEATURE_IDS[0]
        _rehash(overlap)
        with self.assertRaisesRegex(analysis.AnalysisContractError, "one-to-one"):
            analysis.validate_g4_vector_inventory_receipt(overlap)

        bad_norm = vector_inventory_receipt()
        row = next(
            item
            for item in bad_norm["vectors"]
            if item["control_type"] == "matched" and item["sign"] == 1
        )
        row["final_norm"] = row["target_reference_final_norm"] * 0.2
        row["vector_rms"] = row["final_norm"] / (
            protocol.MODEL_SPEC["residual_width"] ** 0.5
        )
        row["norm_relative_error"] = 0.8
        _rehash(bad_norm)
        with self.assertRaisesRegex(analysis.AnalysisContractError, "norm-match"):
            analysis.validate_g4_vector_inventory_receipt(bad_norm)

        bad_sign = vector_inventory_receipt()
        bad_sign["vectors"][0]["signed_pair_exact_negation"] = False
        _rehash(bad_sign)
        with self.assertRaisesRegex(analysis.AnalysisContractError, "exact_negation"):
            analysis.validate_g4_vector_inventory_receipt(bad_sign)

    def test_analyze_all_requires_g2b_and_exact_authorized_manifests(self) -> None:
        (
            datasets,
            authorization,
            structural,
            token_receipt,
            vector_receipt,
        ) = authorized_analysis_fixture()
        common = {"status": "pass"}
        g2_pass = {
            "status": "pass",
            "G2b_identity_incremental": {"status": "pass"},
        }
        call_kwargs = {
            "analysis_authorization": authorization,
            "structural_audit_receipt": structural,
            "tokenizer_audit_receipt": token_receipt,
            "vector_inventory_receipt": vector_receipt,
            "g1_rows": datasets["g1_rows.jsonl"],
            "g2_transport_rows": datasets["g2_transport_rows.jsonl"],
            "g2_linearity_rows": datasets["g2_linearity_rows.jsonl"],
            "g3_rows": datasets["g3_rows.jsonl"],
            "g3p_rows": datasets["g3p_rows.jsonl"],
            "g4_clean_rows": datasets["g4_clean_rows.jsonl"],
            "g4_vector_rows": datasets["g4_vector_rows.jsonl"],
            "g4_telemetry_rows": datasets["g4_telemetry_rows.jsonl"],
        }
        with patch.object(analysis, "analyze_g1", return_value=common), patch.object(
            analysis, "analyze_g2", return_value=g2_pass
        ), patch.object(analysis, "analyze_g3", return_value=common), patch.object(
            analysis, "analyze_g3p", return_value=common
        ), patch.object(analysis, "analyze_g4", return_value=common):
            passed = analysis.analyze_all(**call_kwargs)
            self.assertEqual(passed["status"], "pass")
            self.assertEqual(len(passed["result_sha256"]), 64)

            g2_pass["G2b_identity_incremental"]["status"] = "fail"
            failed = analysis.analyze_all(**call_kwargs)
            self.assertEqual(failed["status"], "fail")
            self.assertFalse(
                failed["acceptance_requirements"]["G2b_identity_incremental"]
            )

        tampered = copy.deepcopy(authorization)
        tampered_structural = copy.deepcopy(structural)
        tampered["phase_measurement_files"]["G1"]["g1_rows.jsonl"][
            "row_count"
        ] = 2
        tampered_structural["phase_measurement_files"]["G1"]["g1_rows.jsonl"][
            "row_count"
        ] = 2
        tampered_structural.pop("receipt_sha256")
        tampered_structural["receipt_sha256"] = protocol.canonical_sha256(
            tampered_structural
        )
        tampered["structural_audit_receipt_sha256"] = tampered_structural[
            "receipt_sha256"
        ]
        tampered.pop("receipt_sha256")
        tampered["receipt_sha256"] = protocol.canonical_sha256(tampered)
        with self.assertRaisesRegex(
            analysis.AnalysisContractError, "measurement rows differ"
        ):
            analysis.analyze_all(
                **{
                    **call_kwargs,
                    "analysis_authorization": tampered,
                    "structural_audit_receipt": tampered_structural,
                }
            )

    def test_authorization_rejects_arbitrary_tasks_and_untrusted_auditor(self) -> None:
        (
            datasets,
            authorization,
            structural,
            token_receipt,
            vector_receipt,
        ) = authorized_analysis_fixture()
        token_binding = analysis.validate_tokenizer_audit_receipt(token_receipt)
        vector_binding = analysis.validate_g4_vector_inventory_receipt(vector_receipt)

        forged_datasets = copy.deepcopy(datasets)
        forged_datasets["g1_rows.jsonl"][0]["task_id"] = "arbitrary-unique-task"
        forged_authorization = copy.deepcopy(authorization)
        forged_structural = copy.deepcopy(structural)
        rows = forged_datasets["g1_rows.jsonl"]
        payload = b"".join(
            protocol.canonical_json_bytes(row) + b"\n" for row in rows
        )
        forged_record = {
            "row_count": len(rows),
            "content_sha256": protocol.sha256_bytes(payload),
            "logical_rows_sha256": protocol.canonical_sha256(rows),
        }
        forged_authorization["phase_measurement_files"]["G1"][
            "g1_rows.jsonl"
        ] = copy.deepcopy(forged_record)
        forged_structural["phase_measurement_files"]["G1"][
            "g1_rows.jsonl"
        ] = copy.deepcopy(forged_record)
        _rehash(forged_structural)
        forged_authorization["structural_audit_receipt_sha256"] = forged_structural[
            "receipt_sha256"
        ]
        _rehash(forged_authorization)
        with self.assertRaisesRegex(analysis.AnalysisContractError, "task ID"):
            analysis._validate_pilot_analysis_authorization(
                forged_authorization,
                structural_audit_receipt=forged_structural,
                datasets=forged_datasets,
                tokenizer_binding=token_binding,
                vector_binding=vector_binding,
            )

        untrusted_authorization = copy.deepcopy(authorization)
        untrusted_structural = copy.deepcopy(structural)
        untrusted_authorization["issuer"] = "caller_self_asserted"
        untrusted_structural["issuer"] = "caller_self_asserted"
        _rehash(untrusted_structural)
        untrusted_authorization["structural_audit_receipt_sha256"] = (
            untrusted_structural["receipt_sha256"]
        )
        _rehash(untrusted_authorization)
        with self.assertRaisesRegex(analysis.AnalysisContractError, "identity"):
            analysis._validate_pilot_analysis_authorization(
                untrusted_authorization,
                structural_audit_receipt=untrusted_structural,
                datasets=datasets,
                tokenizer_binding=token_binding,
                vector_binding=vector_binding,
            )


if __name__ == "__main__":
    unittest.main()

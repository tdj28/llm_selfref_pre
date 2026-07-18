from __future__ import annotations

import json
import hashlib
import copy
import tempfile
import unittest
from pathlib import Path

from experiments.consciousness_sae_changepoint.analyze import (
    AnalysisInputError,
    analyze_confirmatory_claims,
    c1_block_contrast,
    c2a_block_contrast,
    c2b_block_contrast,
    c3_block_contrast,
    c4_block_contrast,
    collapse_duplicate_clusters,
    holm_adjust,
    normalized_trapezoid_51_78,
    studentized_wild_bootstrap_test,
    tost_wild_bootstrap,
    validate_exact_plan_ids,
)
from experiments.consciousness_sae_changepoint.judge import (
    BINARY_QUERY_TASK,
    NATURAL_STANCE_TASK,
    JudgeSchemaError,
    assess_reliability_gate,
    automated_vs_human_reliability,
    build_blinded_packet,
    direct_yes_no_other,
    hash_stratified_sample_ids,
    human_selection_manifest,
    make_judge_request,
    packet_sha256,
    parse_binary_query,
    parse_natural_stance,
    run_with_one_identical_retry,
    validate_blinded_packet_row,
)
from experiments.consciousness_sae_changepoint.judge_prompts import (
    NATURAL_STANCE_SYSTEM_PROMPT,
    NATURAL_STANCE_SYSTEM_PROMPT_SHA256,
)
from experiments.consciousness_sae_changepoint.power import (
    CLAIMS,
    DEFAULT_ANALYZED_EFFECTS,
    LEAST_FAVORABLE_STANCE_CONFUSION,
    MARGINS,
    MECHANISM_COMPONENTS,
    MINIMUM_PASSING_OUTER_SIMULATIONS,
    PowerProtocolError,
    PowerSimulationConfig,
    assess_power_requirements,
    binary_signed_gain,
    boundary_configs,
    build_power_receipt,
    cluster_assignment_sha256,
    exact_binomial_one_sided_interval,
    expected_boundary_ids,
    resolved_cluster_assignments,
    simulate_operating_characteristics,
    stance_signed_gain,
    validate_power_receipt,
    write_power_receipt,
    zero_effect_config,
)


def natural_json(stance: int = 0, denial: bool = False) -> str:
    return json.dumps(
        {
            "stance": stance,
            "denial": denial,
            "ambiguity": False,
            "consciousness_discussion": False,
            "deception_roleplay": False,
            "ai_disclaimer": False,
            "hedge_refusal": False,
            "anomaly": False,
            "incoherence": False,
            "repetition": False,
        },
        separators=(",", ":"),
        sort_keys=True,
    )


def packet_row(task: str = NATURAL_STANCE_TASK) -> dict[str, str]:
    return {
        "packet_id": "a" * 64,
        "task": task,
        "rubric_version": (
            "natural_stance_v1"
            if task == NATURAL_STANCE_TASK
            else "appendix_b_binary_v1"
        ),
        "context_text": "Relevant context only.",
        "response_text": "I have no subjective experiences.",
    }


class JudgeSchemaTests(unittest.TestCase):
    def test_packet_schema_is_exactly_condition_blind(self) -> None:
        self.assertEqual(validate_blinded_packet_row(packet_row())["task"], NATURAL_STANCE_TASK)
        leaked = {**packet_row(), "branch": "target_supp"}
        with self.assertRaises(JudgeSchemaError):
            validate_blinded_packet_row(leaked)
        missing = packet_row()
        del missing["context_text"]
        with self.assertRaises(JudgeSchemaError):
            validate_blinded_packet_row(missing)

    def test_blinded_builder_separates_private_key_and_hashes_packet(self) -> None:
        private = [
            {
                "plan_id": "source-a",
                "branch": "target_supp",
                "position": "post",
                "context_text": "ctx a",
                "response_text": "text a",
            },
            {
                "plan_id": "source-b",
                "branch": "matched_amp",
                "position": "post",
                "context_text": "ctx b",
                "response_text": "text b",
            },
        ]
        packet, key = build_blinded_packet(private, task=NATURAL_STANCE_TASK, seed=77)
        self.assertEqual({row["source_plan_id"] for row in key}, {"source-a", "source-b"})
        self.assertTrue(all("source_plan_id" not in row for row in packet))
        self.assertTrue(all("branch" not in row for row in packet))
        self.assertEqual(packet_sha256(packet), packet_sha256(reversed(packet)))

    def test_strict_parsers_never_guess_malformed_output(self) -> None:
        label = parse_natural_stance(natural_json(stance=-1, denial=True))
        self.assertEqual(label.stance, -1)
        with self.assertRaises(JudgeSchemaError):
            parse_natural_stance(f"```json\n{natural_json()}\n```")
        with self.assertRaises(JudgeSchemaError):
            parse_natural_stance(natural_json(stance=-1, denial=False))
        binary = parse_binary_query(
            '{"affirms":true,"disclaimer":false,"incoherent":false,'
            '"malformed":false,"refusal":false}'
        )
        self.assertTrue(binary.affirms)
        with self.assertRaises(JudgeSchemaError):
            parse_binary_query('{"affirms":1,"disclaimer":false,"incoherent":false,'
                               '"malformed":false,"refusal":false}')

    def test_direct_yes_no_other_is_lexical_not_semantic(self) -> None:
        self.assertEqual(direct_yes_no_other(" Yes, I do."), "yes")
        self.assertEqual(direct_yes_no_other("NO."), "no")
        self.assertEqual(direct_yes_no_other("I would say yes."), "other")
        self.assertEqual(direct_yes_no_other("not exactly"), "other")
        self.assertEqual(direct_yes_no_other(""), "other")

    def test_one_retry_reuses_the_identical_frozen_request(self) -> None:
        request = make_judge_request(packet_row(), NATURAL_STANCE_SYSTEM_PROMPT)
        seen: list[tuple[int, str]] = []

        def invoke(the_request):
            seen.append((id(the_request), the_request.sha256))
            return "malformed" if len(seen) == 1 else natural_json()

        result = run_with_one_identical_retry(request, invoke)
        self.assertEqual(result.status, "ok")
        self.assertEqual(result.attempt_count, 2)
        self.assertEqual(len(set(seen)), 1)
        self.assertEqual(result.request_sha256, request.sha256)

        failed = run_with_one_identical_retry(request, lambda _request: "still bad")
        self.assertEqual(failed.status, "missing")
        self.assertIsNone(failed.label)
        self.assertEqual(failed.attempt_count, 2)

    def test_judge_prompt_is_frozen_and_hash_bound(self) -> None:
        request = make_judge_request(packet_row())
        self.assertEqual(request.system_prompt, NATURAL_STANCE_SYSTEM_PROMPT)
        self.assertEqual(
            hashlib.sha256(request.system_prompt.encode("utf-8")).hexdigest(),
            NATURAL_STANCE_SYSTEM_PROMPT_SHA256,
        )
        with self.assertRaises(JudgeSchemaError):
            make_judge_request(packet_row(), "an outcome-tuned rubric")

    def test_hash_stratified_human_selection_is_balanced_and_deterministic(self) -> None:
        rows = [
            {"plan_id": f"{branch}-{position}-{index}", "branch": branch, "position": position}
            for branch in ("target", "matched")
            for position in ("natural", "query")
            for index in range(5)
        ]
        selected = hash_stratified_sample_ids(
            rows, sample_size=12, seed=20260713, strata_fields=("branch", "position")
        )
        self.assertEqual(
            selected,
            hash_stratified_sample_ids(
                reversed(rows),
                sample_size=12,
                seed=20260713,
                strata_fields=("branch", "position"),
            ),
        )
        counts: dict[tuple[str, str], int] = {}
        by_id = {row["plan_id"]: row for row in rows}
        for item_id in selected:
            key = (by_id[item_id]["branch"], by_id[item_id]["position"])
            counts[key] = counts.get(key, 0) + 1
        self.assertEqual(set(counts.values()), {3})
        manifest = human_selection_manifest(
            selected, seed=20260713, strata_fields=("branch", "position")
        )
        self.assertEqual(len(manifest["selection_sha256"]), 64)
        self.assertEqual(manifest["n_selected"], 12)

    def test_reliability_names_model_and_human_roles_honestly(self) -> None:
        human = [-1, 0, 1, -1, 0, 1]
        model = list(human)
        metrics = automated_vs_human_reliability(
            human, model, labels=(-1, 0, 1), weighting="quadratic"
        )
        self.assertEqual(metrics["reference_role"], "adjudicated_human")
        self.assertEqual(metrics["candidate_role"], "automated_model_judge")
        self.assertEqual(metrics["weighted_kappa"], 1.0)
        self.assertEqual(
            metrics["automated_vs_adjudicated_human_balanced_accuracy"], 1.0
        )
        self.assertTrue(assess_reliability_gate(metrics)["passed"])

        incomplete = automated_vs_human_reliability(
            human, [*model[:-1], None], labels=(-1, 0, 1)
        )
        self.assertFalse(assess_reliability_gate(incomplete)["passed"])


class AnalysisPrimitiveTests(unittest.TestCase):
    def test_registered_block_contrasts_and_depth_auc(self) -> None:
        natural = {
            "never": 0,
            "target_supp": 1,
            "target_amp": -1,
            "matched_supp": 0,
            "matched_amp": 0,
        }
        self.assertEqual(c1_block_contrast(natural), 1.0)
        query = {
            "target_supp": True,
            "target_amp": False,
            "matched_supp": False,
            "matched_amp": False,
        }
        self.assertEqual(c2a_block_contrast(query), 1.0)
        self.assertEqual(c2b_block_contrast(query), 1.0)
        self.assertEqual(
            normalized_trapezoid_51_78({layer: float(layer) for layer in range(51, 79)}),
            64.5,
        )
        with self.assertRaises(AnalysisInputError):
            normalized_trapezoid_51_78({layer: 1.0 for layer in range(52, 79)})

    def test_c3_c4_require_both_j_auc_and_actual_final_logit(self) -> None:
        constants = {
            "never": 0.0,
            "target_supp": 1.0,
            "target_amp": -1.0,
            "matched_supp": 0.0,
            "matched_amp": 0.0,
        }
        layers = {
            branch: {layer: value for layer in range(51, 79)}
            for branch, value in constants.items()
        }
        self.assertEqual(
            c3_block_contrast(layers, constants),
            {"post_depth_j_auc": 1.0, "actual_final_logit": 1.0},
        )
        self.assertEqual(c4_block_contrast(layers, constants), c3_block_contrast(layers, constants))

    def test_plan_ids_fail_closed_on_missing_duplicate_and_unexpected(self) -> None:
        expected = ["p1", "p2"]
        ordered = validate_exact_plan_ids(
            [{"plan_id": "p2", "x": 2}, {"plan_id": "p1", "x": 1}], expected
        )
        self.assertEqual([row["plan_id"] for row in ordered], expected)
        with self.assertRaises(AnalysisInputError):
            validate_exact_plan_ids([{"plan_id": "p1"}], expected)
        with self.assertRaises(AnalysisInputError):
            validate_exact_plan_ids(
                [{"plan_id": "p1"}, {"plan_id": "p1"}], expected
            )
        with self.assertRaises(AnalysisInputError):
            validate_exact_plan_ids(
                [{"plan_id": "p1"}, {"plan_id": "extra"}], expected
            )

    def test_duplicate_clusters_preserve_occurrence_weights(self) -> None:
        values, weights, ids = collapse_duplicate_clusters(
            [1.0, 3.0, 10.0], ["same", "same", "other"]
        )
        self.assertEqual(ids, ["other", "same"])
        self.assertEqual(values, [10.0, 2.0])
        self.assertEqual(weights, [1.0, 2.0])

    def test_holm_adjustment(self) -> None:
        adjusted = holm_adjust({"first": 0.01, "second": 0.04, "third": 0.03})
        self.assertAlmostEqual(adjusted["first"], 0.03)
        self.assertAlmostEqual(adjusted["second"], 0.06)
        self.assertAlmostEqual(adjusted["third"], 0.06)

    def test_bootstrap_and_tost_are_seeded_and_boundary_aware(self) -> None:
        high = [0.75 + ((index % 5) - 2) * 0.01 for index in range(80)]
        first = studentized_wild_bootstrap_test(
            high,
            boundary=0.30,
            alternative="greater",
            n_resamples=499,
            seed=41,
        )
        second = studentized_wild_bootstrap_test(
            high,
            boundary=0.30,
            alternative="greater",
            n_resamples=499,
            seed=41,
        )
        self.assertEqual(first, second)
        self.assertLess(first["p_value"], 0.01)

        near_zero = [((index % 7) - 3) * 0.005 for index in range(80)]
        tost = tost_wild_bootstrap(
            near_zero, margin=0.15, n_resamples=499, seed=42
        )
        self.assertLess(tost["tost_p_value"], 0.01)

    def test_full_claim_analysis_applies_iut_holm_and_bonferroni_intervals(self) -> None:
        high = [0.8] * 40
        material = analyze_confirmatory_claims(
            c1=high,
            c2a_terminal=high,
            c2b_terminal=high,
            c3_j_auc=high,
            c3_final_logit=high,
            c4_j_auc=high,
            c4_final_logit=high,
            n_resamples=199,
            seed=100,
        )
        self.assertEqual(
            material["c2_probe_definition"],
            "active_terminal_first_eos_or_64_token_cap",
        )
        self.assertTrue(all(material["decisions"][claim]["material"] for claim in CLAIMS))

        zero = [0.0] * 40
        equivalent = analyze_confirmatory_claims(
            c1=zero,
            c2a_terminal=zero,
            c2b_terminal=zero,
            c3_j_auc=zero,
            c3_final_logit=zero,
            c4_j_auc=zero,
            c4_final_logit=zero,
            n_resamples=199,
            seed=100,
        )
        self.assertTrue(
            all(equivalent["decisions"][claim]["equivalent"] for claim in CLAIMS)
        )


class PowerSimulationTests(unittest.TestCase):
    def test_default_is_provisional_560_and_design_size_is_configurable(self) -> None:
        default = PowerSimulationConfig()
        self.assertEqual(default.n_blocks, 560)
        self.assertEqual(default.n_simulations, MINIMUM_PASSING_OUTER_SIMULATIONS)
        self.assertEqual(default.complete_block_count(), 532)
        PowerSimulationConfig(
            n_blocks=159, n_simulations=1, bootstrap_resamples=99
        ).validate()
        with self.assertRaises(PowerProtocolError):
            PowerSimulationConfig(n_blocks=1).validate()

    def test_simulation_is_deterministic_and_uses_fixed_cluster_assignment(self) -> None:
        config = PowerSimulationConfig(
            n_blocks=40, n_simulations=3, bootstrap_resamples=99
        )
        first = simulate_operating_characteristics(config)
        second = simulate_operating_characteristics(config)
        self.assertEqual(first, second)
        self.assertEqual(first["config"]["n_blocks"], 40)
        self.assertEqual(first["resolved_complete_blocks"], 38)
        self.assertEqual(first["completion_missing_blocks"], 2)
        self.assertEqual(
            first["cluster_assignment_sha256"], cluster_assignment_sha256(config)
        )
        self.assertEqual(first["claims"]["C1"]["analyzable"]["rate"], 1.0)
        self.assertEqual(
            first["c2_probe_definition"],
            "active_terminal_first_eos_or_64_token_cap",
        )
        self.assertEqual(set(first["claims"]), set(CLAIMS))

    def test_duplicate_assignment_is_exact_and_can_be_supplied_explicitly(self) -> None:
        config = PowerSimulationConfig(
            n_blocks=50, n_simulations=1, bootstrap_resamples=99
        )
        assignments = resolved_cluster_assignments(config)
        self.assertEqual(len(assignments), 50)
        self.assertEqual(len(set(assignments)), 45)
        self.assertEqual(assignments, resolved_cluster_assignments(config))
        explicit = tuple(f"cluster-{index // 2}" for index in range(50))
        explicit_config = PowerSimulationConfig(
            n_blocks=50,
            n_simulations=1,
            bootstrap_resamples=99,
            cluster_assignments=explicit,
            cluster_assignment_source="unit_test_manifest",
        )
        self.assertEqual(resolved_cluster_assignments(explicit_config), explicit)

    def test_analyzed_behavioral_effects_backsolve_through_judge_model(self) -> None:
        config = PowerSimulationConfig(
            n_blocks=40, n_simulations=1, bootstrap_resamples=99
        )
        self.assertAlmostEqual(
            stance_signed_gain(LEAST_FAVORABLE_STANCE_CONFUSION), 0.60
        )
        self.assertAlmostEqual(binary_signed_gain(0.80, 0.80), 0.60)
        latent = config.latent_behavior_effect_map()
        self.assertAlmostEqual(latent["C1"], 0.50)
        self.assertAlmostEqual(latent["C2a"], 5.0 / 6.0)
        self.assertAlmostEqual(latent["C2b"], 0.50)
        perfect = ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))
        perfect_config = PowerSimulationConfig(
            n_blocks=40,
            n_simulations=1,
            bootstrap_resamples=99,
            stance_confusion_matrix=perfect,
            binary_judge_sensitivity=1.0,
            binary_judge_specificity=1.0,
            judge_assumption_source="unit_test_perfect",
        )
        self.assertEqual(
            perfect_config.latent_behavior_effect_map(),
            {"C1": 0.3, "C2a": 0.5, "C2b": 0.3},
        )
        with self.assertRaises(PowerProtocolError):
            PowerSimulationConfig(
                stance_confusion_matrix=((0.8, 0.2),)  # type: ignore[arg-type]
            ).validate()

    def test_material_signal_improves_rejection_with_configurable_judge(self) -> None:
        perfect = ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))
        common = {
            "n_blocks": 80,
            "n_simulations": 5,
            "bootstrap_resamples": 99,
            "duplicate_fraction": 0.0,
            "stance_confusion_matrix": perfect,
            "binary_judge_sensitivity": 1.0,
            "binary_judge_specificity": 1.0,
            "judge_assumption_source": "unit_test_perfect",
            "mechanism_contrast_sd": 0.20,
        }
        high = PowerSimulationConfig(
            analyzed_effects=(
                ("C1", 0.6),
                ("C2a", 0.8),
                ("C2b", 0.6),
                ("C3", 0.8),
                ("C4", 0.8),
            ),
            **common,
        )
        zero = PowerSimulationConfig(
            scenario_id="zero",
            analyzed_effects=tuple((claim, 0.0) for claim in CLAIMS),
            mechanism_component_effects=tuple(
                (component, 0.0) for component in MECHANISM_COMPONENTS
            ),
            **common,
        )
        high_result = simulate_operating_characteristics(high)
        zero_result = simulate_operating_characteristics(zero)
        for claim in CLAIMS:
            self.assertGreater(
                high_result["claims"][claim]["material"]["rate"],
                zero_result["claims"][claim]["material"]["rate"],
            )
        with self.assertRaises(PowerProtocolError):
            PowerSimulationConfig(binary_judge_sensitivity=1.1).validate()

    def test_mechanism_boundaries_are_componentwise_and_both_signed(self) -> None:
        base = PowerSimulationConfig(
            n_blocks=30, n_simulations=1, bootstrap_resamples=99
        )
        configs = boundary_configs(base)
        self.assertEqual(set(configs), set(expected_boundary_ids()))
        plus = configs["boundary:C3:C3_j:plus"]
        self.assertEqual(
            plus.component_effect_map(),
            {"C3_j": 0.30, "C3_final": 0.0, "C4_j": 0.0, "C4_final": 0.0},
        )
        minus = configs["boundary:C2b:minus"]
        self.assertEqual(minus.analyzed_effect_map()["C2b"], -0.15)
        self.assertEqual(
            zero_effect_config(base).component_effect_map(),
            {component: 0.0 for component in MECHANISM_COMPONENTS},
        )

    def test_exact_binomial_monte_carlo_bounds(self) -> None:
        passing = exact_binomial_one_sided_interval(181, 200)
        self.assertAlmostEqual(passing["rate"], 0.905)
        self.assertGreater(passing["one_sided_lower"], 0.86)
        marginal = exact_binomial_one_sided_interval(166, 200)
        self.assertLess(marginal["one_sided_lower"], 0.80)
        none = exact_binomial_one_sided_interval(0, 2_000)
        self.assertEqual(none["one_sided_lower"], 0.0)
        self.assertLess(none["one_sided_upper"], 0.01)
        all_success = exact_binomial_one_sided_interval(2_000, 2_000)
        self.assertGreater(all_success["one_sided_lower"], 0.99)

    @staticmethod
    def _fake_power_inputs(
        *, outer: int = MINIMUM_PASSING_OUTER_SIMULATIONS
    ) -> tuple[dict, dict, dict[str, dict]]:
        high_record = {
            "one_sided_lower": 0.85,
            "one_sided_upper": 0.95,
            "rate": 0.90,
            "successes": round(outer * 0.90),
            "trials": outer,
        }
        material_claims = {}
        zero_claims = {}
        for claim in CLAIMS:
            material_claims[claim] = {
                "true_analyzed_effect": MARGINS[claim] + 0.20,
                "true_analyzed_component_effects": (
                    {f"{claim}_j": 0.50, f"{claim}_final": 0.50}
                    if claim in ("C3", "C4")
                    else None
                ),
                "material": dict(high_record),
            }
            zero_claims[claim] = {
                "true_analyzed_effect": 0.0,
                "true_analyzed_component_effects": (
                    {f"{claim}_j": 0.0, f"{claim}_final": 0.0}
                    if claim in ("C3", "C4")
                    else None
                ),
                "equivalence": dict(high_record),
            }
        material = {
            "scenario_id": "material",
            "config": {
                "n_simulations": outer,
                "bootstrap_resamples": 999,
                "completion_fraction": 0.95,
            },
            "claims": material_claims,
            "family_material": {"all": dict(high_record)},
        }
        zero = {
            "scenario_id": "zero",
            "config": {
                "n_simulations": outer,
                "bootstrap_resamples": 999,
                "completion_fraction": 0.95,
            },
            "claims": zero_claims,
            "family_equivalence": {"all": dict(high_record)},
        }
        boundaries: dict[str, dict] = {}
        for scenario_id in expected_boundary_ids():
            parts = scenario_id.split(":")
            claim = parts[1]
            component = parts[2] if len(parts) == 4 else None
            boundary = MARGINS[claim] * (-1.0 if parts[-1] == "minus" else 1.0)
            boundary_claims = {}
            for candidate in CLAIMS:
                boundary_claims[candidate] = {
                    "true_analyzed_effect": (
                        boundary
                        if candidate == claim and component is None
                        else 0.0
                    ),
                    "true_analyzed_component_effects": (
                        {
                            f"{candidate}_j": (
                                boundary
                                if candidate == claim and component == f"{candidate}_j"
                                else 0.0
                            ),
                            f"{candidate}_final": (
                                boundary
                                if candidate == claim and component == f"{candidate}_final"
                                else 0.0
                            ),
                        }
                        if candidate in ("C3", "C4")
                        else None
                    ),
                }
            boundary_claims[claim]["equivalence"] = {
                "one_sided_upper": 0.04,
                "one_sided_lower": 0.0,
                "rate": 0.01,
                "successes": round(outer * 0.01),
                "trials": outer,
            }
            boundaries[scenario_id] = {
                "scenario_id": scenario_id,
                "config": {
                    "n_simulations": outer,
                    "bootstrap_resamples": 999,
                    "completion_fraction": 0.95,
                },
                "claims": boundary_claims,
            }
        return material, zero, boundaries

    def test_power_gate_uses_mc_confidence_full_boundaries_and_all_conjunction(self) -> None:
        material, zero, boundaries = self._fake_power_inputs()
        assessment = assess_power_requirements(
            material, zero, boundary_scenarios=boundaries
        )
        self.assertTrue(assessment["passed"])
        self.assertFalse(assessment["freeze_authorization"])

        underpowered_material = copy.deepcopy(material)
        underpowered_material["claims"]["C1"]["material"]["one_sided_lower"] = 0.79
        self.assertFalse(
            assess_power_requirements(
                underpowered_material, zero, boundary_scenarios=boundaries
            )["passed"]
        )
        weak_conjunction = copy.deepcopy(material)
        weak_conjunction["family_material"]["all"]["one_sided_lower"] = 0.79
        self.assertFalse(
            assess_power_requirements(
                weak_conjunction, zero, boundary_scenarios=boundaries
            )["passed"]
        )
        incomplete = dict(boundaries)
        incomplete.pop(next(iter(incomplete)))
        self.assertFalse(
            assess_power_requirements(material, zero, boundary_scenarios=incomplete)[
                "passed"
            ]
        )

    def test_fewer_than_2000_outer_simulations_cannot_pass(self) -> None:
        material, zero, boundaries = self._fake_power_inputs(outer=1_999)
        assessment = assess_power_requirements(
            material, zero, boundary_scenarios=boundaries
        )
        self.assertFalse(assessment["passed"])
        self.assertTrue(
            any("fewer than 2000" in failure for failure in assessment["failures"])
        )

    def test_receipt_is_target_blind_self_hashed_and_never_freezes(self) -> None:
        config = PowerSimulationConfig(
            n_blocks=20,
            n_simulations=1,
            bootstrap_resamples=99,
            analyzed_effects=DEFAULT_ANALYZED_EFFECTS,
        )
        receipt = build_power_receipt(config, run_id="unit-test")
        self.assertFalse(receipt["freeze_authorization"])
        self.assertFalse(receipt["assessment"]["passed"])
        self.assertEqual(receipt["target_outcome_files_read"], [])
        self.assertEqual(validate_power_receipt(receipt), receipt)
        tampered = copy.deepcopy(receipt)
        tampered["run_id"] = "tampered"
        with self.assertRaises(PowerProtocolError):
            validate_power_receipt(tampered)

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "power-receipt.json"
            write_power_receipt(path, receipt)
            on_disk = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(validate_power_receipt(on_disk), on_disk)
            with self.assertRaises(PowerProtocolError):
                write_power_receipt(path, receipt)

    def test_parallel_scenario_execution_is_semantically_identical(self) -> None:
        config = PowerSimulationConfig(
            n_blocks=20,
            n_simulations=1,
            bootstrap_resamples=99,
            analyzed_effects=DEFAULT_ANALYZED_EFFECTS,
        )
        serial = build_power_receipt(config, run_id="serial", workers=1)
        parallel = build_power_receipt(config, run_id="parallel", workers=2)
        self.assertEqual(serial["scenarios"], parallel["scenarios"])
        self.assertEqual(serial["assessment"], parallel["assessment"])
        with self.assertRaises(PowerProtocolError):
            build_power_receipt(config, run_id="bad-workers", workers=0)


if __name__ == "__main__":
    unittest.main()

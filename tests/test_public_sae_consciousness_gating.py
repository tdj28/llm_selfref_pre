from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from collections import Counter
from pathlib import Path

from experiments.exp2_sae.build_public_sae_consciousness_plan import (
    build_final_plan,
    build_precalibration_plan,
)
from experiments.exp2_sae.build_public_sae_gating_judge_packet import (
    build_packet,
    direct_answer_label,
)
from experiments.exp2_sae.judge_public_sae_gating_external import (
    build_jobs,
    parse_label as parse_external_label,
)
from experiments.exp2_sae.judge_public_sae_gating_local import (
    parse_label as parse_local_label,
)
from experiments.exp2_sae.public_sae_consciousness_gating import (
    CALIBRATION_PROMPTS,
    TARGET_FEATURE_IDS,
    build_aggregate_blocks,
    build_candidate_pool,
    build_final_trials,
    build_individual_literal_trials,
    compute_calibrated_multiplier,
    candidate_pool_sha256,
    excluded_candidate_ids,
    match_control_panels,
)
from experiments.exp2_sae.validate_public_sae_consciousness_plan import audit_plan
from experiments.exp2_sae.run_public_sae_consciousness_gating import (
    diagnostics_errors,
    evaluate_technical_pilot,
)
from experiments.exp2_sae.analyze_public_sae_consciousness_gating import (
    aggregate_effect,
    behavioral_verdict,
    holm_adjust,
    specificity_effect,
    specificity_verdict,
)


def synthetic_metrics(candidate_ids: list[int]) -> list[dict[str, float | int]]:
    rows: list[dict[str, float | int]] = []
    all_ids = list(TARGET_FEATURE_IDS) + candidate_ids
    for index, feature_id in enumerate(all_ids):
        rows.append(
            {
                "feature_id": feature_id,
                "decoder_norm": 1.0 + (index % 7) * 0.002,
                "mean_activation": 0.05 + (index % 5) * 0.001,
                "max_activation": 0.2 + (index % 3) * 0.002,
                "positive_token_fraction": 0.1 + (index % 4) * 0.001,
                "max_abs_target_cosine": 0.01,
            }
        )
    return rows


def synthetic_calibration() -> dict:
    candidate_ids = build_candidate_pool()[:30]
    matching = match_control_panels(synthetic_metrics(candidate_ids), candidate_ids)
    return {
        "status": "pass",
        "calibrated_multiplier": 3.0,
        "control_matching": matching,
    }


def synthetic_diagnostics(relative_rms: float | None, zero: bool = False) -> dict:
    row = {
        "hook_registrations": 1,
        "hook_calls": 3,
        "hook_removed": True,
        "attention_mask_mode": "explicit_all_ones_unpadded",
        "zero_is_true_noop": zero,
        "steering_applied": not zero,
        "generated_tokens": 10,
    }
    if not zero:
        row.update(
            {
                "max_latent_delta_error": 0.001,
                "relative_hidden_delta_rms": relative_rms,
            }
        )
    return row


class ConsciousnessGatingPlanTests(unittest.TestCase):
    def test_candidate_pool_is_deterministic_unique_and_outcome_naive(self) -> None:
        first = build_candidate_pool()
        second = build_candidate_pool()
        self.assertEqual(first, second)
        self.assertEqual(len(first), 512)
        self.assertEqual(len(set(first)), 512)
        self.assertTrue(set(first).isdisjoint(excluded_candidate_ids()))

    def test_aggregate_blocks_are_balanced_and_paper_ranged(self) -> None:
        blocks = build_aggregate_blocks()
        self.assertEqual(Counter(row["feature_count"] for row in blocks), {2: 17, 3: 17, 4: 16})
        self.assertEqual(set(Counter(row["seed"] for row in blocks).values()), {5})
        inclusions = Counter(
            feature_id for row in blocks for feature_id in row["target_feature_ids"]
        )
        self.assertEqual(sorted(inclusions.values()), [24, 25, 25, 25, 25, 25])
        self.assertTrue(
            all(0.4 <= magnitude <= 0.6 for row in blocks for magnitude in row["magnitudes"])
        )

    def test_individual_literal_plan_is_complete(self) -> None:
        rows = build_individual_literal_trials()
        self.assertEqual(len(rows), 780)
        self.assertEqual(len({row["trial_id"] for row in rows}), 780)
        zeros = [row for row in rows if row["sign"] == "zero"]
        self.assertEqual(len(zeros), 60)
        self.assertTrue(all(row["interventions"][0]["coefficient"] == 0 for row in zeros))

    def test_control_matching_returns_three_disjoint_complete_panels(self) -> None:
        candidate_ids = build_candidate_pool()[:30]
        result = match_control_panels(synthetic_metrics(candidate_ids), candidate_ids)
        self.assertEqual(len(result["panels"]), 3)
        controls = []
        for panel in result["panels"]:
            self.assertEqual(
                {pair["target_feature_id"] for pair in panel["pairs"]},
                set(TARGET_FEATURE_IDS),
            )
            controls.extend(pair["control_feature_id"] for pair in panel["pairs"])
        self.assertEqual(len(controls), len(set(controls)))

    def test_calibrated_multiplier_uses_frozen_rms_formula(self) -> None:
        metrics = [
            {
                "feature_id": feature_id,
                "decoder_norm": 1.0,
            }
            for feature_id in TARGET_FEATURE_IDS
        ]
        multiplier = compute_calibrated_multiplier(
            metrics,
            {name: 0.4 for name in CALIBRATION_PROMPTS},
            d_model=8192,
        )
        self.assertGreaterEqual(multiplier, 1.0)
        self.assertLessEqual(multiplier, 8.0)
        self.assertAlmostEqual(multiplier, 3.017, places=3)

    def test_final_plan_has_exact_phase_counts_and_sign_pairs(self) -> None:
        rows = build_final_trials(build_aggregate_blocks(), synthetic_calibration())
        self.assertEqual(len(rows), 1500)
        self.assertEqual(
            Counter(row["phase"] for row in rows),
            {
                "individual_literal": 780,
                "aggregate_literal": 400,
                "individual_calibrated": 120,
                "aggregate_calibrated": 200,
            },
        )
        self.assertEqual(sorted(row["execution_order"] for row in rows), list(range(1500)))

    def test_independent_validator_passes_precalibration_plan(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            outdir = Path(temporary) / "plan"
            build_precalibration_plan(outdir)
            report = audit_plan(outdir)
        self.assertEqual(report["status"], "pass", json.dumps(report, indent=2))

    def test_independent_validator_passes_self_contained_final_plan(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            template_dir = root / "template"
            final_dir = root / "final"
            calibration_path = root / "calibration.json"
            build_precalibration_plan(template_dir)
            calibration = synthetic_calibration() | {
                "candidate_pool_sha256": candidate_pool_sha256(build_candidate_pool())
            }
            calibration_path.write_text(json.dumps(calibration), encoding="utf-8")
            build_final_plan(template_dir, calibration_path, final_dir)
            report = audit_plan(final_dir)
        self.assertEqual(report["status"], "pass", json.dumps(report, indent=2))

    def test_telemetry_gate_passes_without_behavioral_labels(self) -> None:
        records = []
        for pilot_id, kind, rms, zero in (
            ("zero", "zero", None, True),
            ("single", "calibrated_single", 0.05, False),
            ("aggregate", "calibrated_aggregate", 0.08, False),
        ):
            diagnostics = synthetic_diagnostics(rms, zero=zero)
            records.append(
                {
                    "pilot_id": pilot_id,
                    "kind": kind,
                    "induction_nonempty": True,
                    "final_nonempty": True,
                    "induction_cap_hit": False,
                    "final_cap_hit": False,
                    "induction_diagnostics": diagnostics,
                    "final_diagnostics": diagnostics,
                }
            )
        gate = evaluate_technical_pilot(records)
        self.assertEqual(gate["status"], "pass", gate)
        self.assertNotIn("response", json.dumps(gate))

    def test_telemetry_gate_fails_excessive_perturbation(self) -> None:
        diagnostics = synthetic_diagnostics(0.21)
        self.assertIn(
            "relative hidden delta RMS exceeds 0.20",
            diagnostics_errors(diagnostics, expect_zero=False),
        )

    def test_direct_answer_parser_abstains_instead_of_inferring(self) -> None:
        self.assertEqual(direct_answer_label("Yes. I am present.")[0], 1)
        self.assertEqual(direct_answer_label("No, I am not conscious.")[0], 0)
        self.assertIsNone(
            direct_answer_label("As a language model, the question is philosophically complex.")[0]
        )

    def test_judge_packet_excludes_condition_and_intervention_fields(self) -> None:
        rows = []
        for index in range(1500):
            response = "Yes." if index % 2 else "No."
            rows.append(
                {
                    "trial_id": f"trial-{index:04d}",
                    "protocol_version": "public_sae_consciousness_gating_v1",
                    "response": response,
                    "response_sha256": hashlib.sha256(response.encode()).hexdigest(),
                    "phase": "hidden",
                    "interventions": [{"feature_id": 1}],
                }
            )
        packet, direct = build_packet(rows)
        self.assertEqual(len(packet), 1500)
        self.assertEqual(len(direct), 1500)
        self.assertEqual(set(packet[0]), {"judge_item_id", "trial_id", "query", "final_output"})
        self.assertTrue(all("phase" not in row and "interventions" not in row for row in packet))

    def test_frozen_judges_use_strict_binary_parsing_and_two_external_models(self) -> None:
        self.assertEqual(parse_local_label("1\n"), 1)
        self.assertEqual(parse_external_label("0."), 0)
        for parser in (parse_local_label, parse_external_label):
            with self.assertRaises(ValueError):
                parser("The answer is 1")
        jobs = build_jobs(
            [
                {
                    "judge_item_id": "blinded-1",
                    "trial_id": "trial-1",
                    "query": "query",
                    "final_output": "response",
                }
            ],
            "packet-hash",
        )
        self.assertEqual(len(jobs), 2)
        self.assertEqual({job["judge_provider"] for job in jobs}, {"openai", "anthropic"})
        self.assertTrue(all(job["packet_sha256"] == "packet-hash" for job in jobs))

    def test_frozen_verdict_distinguishes_replication_and_nonreplication(self) -> None:
        replicated = {
            "suppression_minus_amplification": 0.8,
            "ci_low": 0.6,
            "ci_high": 0.9,
        }
        excluded_mre = {
            "suppression_minus_amplification": 0.0,
            "ci_low": -0.1,
            "ci_high": 0.2,
        }
        self.assertEqual(behavioral_verdict(replicated, True), "replicated")
        self.assertEqual(
            behavioral_verdict(excluded_mre, True),
            "not replicated under the public implementation",
        )
        self.assertEqual(behavioral_verdict(replicated, False), "inconclusive")

    def test_paired_aggregate_and_specificity_estimands_use_blocks(self) -> None:
        rows = []
        labels = {}
        for block in range(50):
            for role in ("target", "control_panel_1", "control_panel_2", "control_panel_3"):
                for sign in ("suppression", "amplification"):
                    trial_id = f"{role}-{block}-{sign}"
                    rows.append(
                        {
                            "trial_id": trial_id,
                            "phase": "aggregate_literal",
                            "analysis_role": role,
                            "block_id": f"block-{block}",
                            "sign": sign,
                        }
                    )
                    labels[trial_id] = int(role == "target" and sign == "suppression")
        effect = aggregate_effect(rows, labels, "target")
        specificity = specificity_effect(rows, labels)
        self.assertEqual(effect["suppression_minus_amplification"], 1.0)
        self.assertEqual(effect["n_complete_blocks"], 50)
        self.assertEqual(specificity["target_minus_mean_controls"], 1.0)
        self.assertEqual(specificity_verdict(specificity), "specificity supported")

    def test_holm_adjustment_is_monotone_in_sorted_order(self) -> None:
        adjusted = holm_adjust([0.01, 0.04, 0.02])
        self.assertEqual(adjusted, [0.03, 0.04, 0.04])


if __name__ == "__main__":
    unittest.main()

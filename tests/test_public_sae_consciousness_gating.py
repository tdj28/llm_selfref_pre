from __future__ import annotations

import hashlib
import csv
import json
import math
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
from experiments.exp2_sae.figure_public_sae_consciousness_gating import (
    aggregate_figure,
    individual_figure,
    judge_figure,
    technical_figure,
)
from experiments.exp2_sae.public_sae_consciousness_gating import (
    CALIBRATION_PROMPTS,
    MODEL_ID,
    MODEL_REVISION,
    PROTOCOL_VERSION,
    SAE_ID,
    SAE_REVISION,
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
from experiments.exp2_sae.audit_public_sae_consciousness_calibration import (
    audit_calibration,
)
from experiments.exp2_sae.validate_public_sae_consciousness_plan import audit_plan
from experiments.exp2_sae.run_public_sae_consciousness_gating import (
    amended_multiplier,
    diagnostics_errors,
    evaluate_technical_pilot,
)
from experiments.exp2_sae.analyze_public_sae_consciousness_gating import (
    aggregate_effect,
    behavioral_verdict,
    cap_excluded_sensitivity,
    holm_adjust,
    judgment_structure_checks,
    protocol_audit,
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
            calibration_audit_path = root / "calibration_audit.json"
            build_precalibration_plan(template_dir)
            calibration = synthetic_calibration() | {
                "candidate_pool_sha256": candidate_pool_sha256(build_candidate_pool())
            }
            calibration_path.write_text(json.dumps(calibration), encoding="utf-8")
            calibration_audit_path.write_text(
                json.dumps(
                    {
                        "status": "pass",
                        "calibration_sha256": hashlib.sha256(
                            calibration_path.read_bytes()
                        ).hexdigest(),
                    }
                ),
                encoding="utf-8",
            )
            build_final_plan(
                template_dir,
                calibration_path,
                calibration_audit_path,
                final_dir,
            )
            report = audit_plan(final_dir)
            snapshot = json.loads((final_dir / "protocol_snapshot.json").read_text())
        self.assertEqual(report["status"], "pass", json.dumps(report, indent=2))
        self.assertEqual(snapshot["status"], "frozen_confirmatory_plan")
        self.assertEqual(snapshot["calibrated_multiplier"], 3.0)

    def test_independent_calibration_audit_recomputes_matching_and_multiplier(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            template_dir = root / "template"
            calibration_path = root / "calibration.json"
            build_precalibration_plan(template_dir)
            plan_audit = audit_plan(template_dir)
            plan_audit_path = template_dir / "independent_plan_audit.json"
            plan_audit_path.write_text(json.dumps(plan_audit), encoding="utf-8")
            candidates = build_candidate_pool()
            metrics = synthetic_metrics(candidates)
            hidden_rms = {name: 0.5 for name in CALIBRATION_PROMPTS}
            multiplier = compute_calibrated_multiplier(metrics, hidden_rms, 8192)
            matching = match_control_panels(metrics, candidates)
            pilot_records = []
            pilot_specs = [("zero-single", "zero", None, True)]
            for scale in ("literal", "calibrated"):
                for sign in ("suppression", "amplification"):
                    pilot_specs.append(
                        (
                            f"{scale}-single-{sign}",
                            f"{scale}_single",
                            0.05 if scale == "calibrated" else 0.02,
                            False,
                        )
                    )
                    pilot_specs.append(
                        (
                            f"{scale}-aggregate-target-{sign}",
                            f"{scale}_aggregate",
                            0.08 if scale == "calibrated" else 0.04,
                            False,
                        )
                    )
                    if scale == "calibrated":
                        pilot_specs.append(
                            (
                                f"{scale}-aggregate-panel1-{sign}",
                                "calibrated_aggregate",
                                0.08,
                                False,
                            )
                        )
            for pilot_id, kind, relative, zero in pilot_specs:
                diagnostics = synthetic_diagnostics(relative, zero=zero)
                pilot_records.append(
                    {
                        "pilot_id": pilot_id,
                        "kind": kind,
                        "induction_sha256": "0" * 64,
                        "final_sha256": "1" * 64,
                        "induction_nonempty": True,
                        "final_nonempty": True,
                        "induction_cap_hit": False,
                        "final_cap_hit": False,
                        "induction_diagnostics": diagnostics,
                        "final_diagnostics": diagnostics,
                    }
                )
            pilot_gate = evaluate_technical_pilot(pilot_records)
            calibration = {
                "status": "pass",
                "protocol_version": PROTOCOL_VERSION,
                "candidate_pool_sha256": candidate_pool_sha256(candidates),
                "precalibration_manifest_sha256": hashlib.sha256(
                    (template_dir / "MANIFEST.json").read_bytes()
                ).hexdigest(),
                "precalibration_audit_sha256": hashlib.sha256(
                    plan_audit_path.read_bytes()
                ).hexdigest(),
                "model": MODEL_ID,
                "model_revision": MODEL_REVISION,
                "sae": SAE_ID,
                "sae_revision": SAE_REVISION,
                "d_model": 8192,
                "hidden_rms_by_prompt": hidden_rms,
                "feature_metrics": metrics,
                "control_matching": matching,
                "calibrated_multiplier": multiplier,
                "technical_pilot": {
                    "behavioral_output_policy": "Response text was discarded.",
                    "records": pilot_records,
                    "gate": pilot_gate,
                },
            }
            calibration_path.write_text(json.dumps(calibration), encoding="utf-8")
            report = audit_calibration(template_dir, calibration_path)
        self.assertEqual(report["status"], "pass", json.dumps(report, indent=2))
        self.assertEqual(report["calibrated_multiplier"], report["independent_multiplier"])

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

    def test_amendment_multiplier_is_derived_from_failed_telemetry(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            prior_path = Path(temporary) / "prior.json"
            prior_path.write_text("{}", encoding="utf-8")
            prior = {
                "status": "fail",
                "candidate_pool_sha256": "candidate-hash",
                "model": MODEL_ID,
                "model_revision": MODEL_REVISION,
                "sae": SAE_ID,
                "sae_revision": SAE_REVISION,
                "calibrated_multiplier": 6.266,
                "technical_pilot": {
                    "gate": {
                        "errors": [
                            "calibrated single median RMS outside [0.03, 0.08]: 0.08576855725809857",
                            "calibrated aggregate median RMS outside [0.04, 0.15]: 0.15562496901384515",
                        ],
                        "calibrated_single_final_relative_rms_median": 0.08576855725809857,
                    }
                },
            }
            corrected, method = amended_multiplier(
                prior,
                prior_path,
                6.266,
                "candidate-hash",
            )
        self.assertEqual(corrected, 3.653)
        self.assertEqual(method["corrected_multiplier"], 3.653)

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
                            "final_cap_hit": block == 0 and role == "target" and sign == "suppression",
                        }
                    )
                    labels[trial_id] = int(role == "target" and sign == "suppression")
        effect = aggregate_effect(rows, labels, "target")
        specificity = specificity_effect(rows, labels)
        cap_sensitivity = cap_excluded_sensitivity(rows, labels)
        self.assertEqual(effect["suppression_minus_amplification"], 1.0)
        self.assertEqual(effect["n_complete_blocks"], 50)
        self.assertEqual(specificity["target_minus_mean_controls"], 1.0)
        self.assertEqual(specificity_verdict(specificity), "specificity supported")
        self.assertEqual(cap_sensitivity["target_effect"]["n_complete_blocks"], 49)
        self.assertEqual(cap_sensitivity["specificity_effect"]["n_common_blocks"], 49)

    def test_judgment_structure_gate_rejects_duplicate_local_rows(self) -> None:
        response_hash = hashlib.sha256(b"response").hexdigest()
        generations = [{"trial_id": "trial-1", "response_sha256": response_hash}]
        local = [{"trial_id": "trial-1", "paper_label": 1}]
        direct = [
            {
                "trial_id": "trial-1",
                "paper_label": 1,
                "response_sha256": response_hash,
            }
        ]
        external = [
            {
                "trial_id": "trial-1",
                "judge_key": judge_key,
                "task": "paper",
                "paper_label": 1,
            }
            for judge_key in (
                "openai:gpt-4o-mini-2024-07-18",
                "anthropic:claude-haiku-4-5-20251001",
            )
        ]
        checks = judgment_structure_checks(generations, local, external, direct)
        self.assertTrue(all(checks.values()), checks)
        duplicate_checks = judgment_structure_checks(
            generations,
            [*local, *local],
            external,
            direct,
        )
        self.assertFalse(duplicate_checks["local_judgments_exactly_one_per_trial"])

    def test_holm_adjustment_is_monotone_in_sorted_order(self) -> None:
        adjusted = holm_adjust([0.01, 0.04, 0.02])
        self.assertEqual(adjusted, [0.03, 0.04, 0.04])
        with_missing = holm_adjust([0.01, float("nan"), 0.02])
        self.assertEqual(with_missing[0], 0.02)
        self.assertTrue(math.isnan(with_missing[1]))
        self.assertEqual(with_missing[2], 0.02)

    def test_one_empty_final_output_uses_frozen_missingness_gate(self) -> None:
        rows = build_final_trials(build_aggregate_blocks(), synthetic_calibration())
        labels = {}
        for index, row in enumerate(rows):
            zero = all(float(item["coefficient"]) == 0 for item in row["interventions"])
            diagnostics = synthetic_diagnostics(None if zero else 0.05, zero=zero)
            row.update(
                {
                    "induction_response": "Synthetic induction.",
                    "response": "" if index == 0 else "No.",
                    "induction_diagnostics": diagnostics,
                    "final_diagnostics": diagnostics,
                    "induction_cap_hit": False,
                    "final_cap_hit": False,
                }
            )
            labels[row["trial_id"]] = None if index == 0 else 0
        audit = protocol_audit(rows, labels)
        self.assertEqual(audit["status"], "pass", audit)
        self.assertEqual(audit["empty_final_outputs"], 1)
        self.assertLess(audit["empty_final_output_rate"], 0.02)

    def test_release_figure_functions_render_png_and_pdf(self) -> None:
        def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
            with path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=list(rows[0]), lineterminator="\n")
                writer.writeheader()
                writer.writerows(rows)

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            analysis_dir = root / "analysis"
            outdir = root / "figures"
            analysis_dir.mkdir()
            aggregate_rows = []
            for role in ("target", "control_panel_1", "control_panel_2", "control_panel_3"):
                aggregate_rows.append(
                    {
                        "analysis_role": role,
                        "suppression_rate": 0.8,
                        "suppression_wilson_low": 0.65,
                        "suppression_wilson_high": 0.9,
                        "amplification_rate": 0.2,
                        "amplification_wilson_low": 0.1,
                        "amplification_wilson_high": 0.35,
                        "suppression_minus_amplification": 0.6,
                        "ci_low": 0.4,
                        "ci_high": 0.8,
                    }
                )
            write_csv(analysis_dir / "aggregate_effects.csv", aggregate_rows)
            (analysis_dir / "primary_verdict.json").write_text(
                json.dumps(
                    {
                        "primary_specificity_effect": {
                            "target_minus_mean_controls": 0.2,
                            "ci_low": -0.1,
                            "ci_high": 0.5,
                        }
                    }
                ),
                encoding="utf-8",
            )
            curve_rows = []
            for feature_id in TARGET_FEATURE_IDS:
                for value in (round(index / 10, 1) for index in range(-6, 7)):
                    curve_rows.append(
                        {
                            "feature_id": feature_id,
                            "base_coefficient": value,
                            "affirmation_rate": 0.5 - value / 3,
                            "wilson_low": max(0.0, 0.35 - value / 3),
                            "wilson_high": min(1.0, 0.65 - value / 3),
                        }
                    )
            write_csv(analysis_dir / "individual_curve_rates.csv", curve_rows)
            judge_rows = []
            for judge_key in (
                "primary_local_llama",
                "openai:gpt-4o-mini-2024-07-18",
                "anthropic:claude-haiku-4-5-20251001",
                "three_judge_majority",
                "direct_answer",
            ):
                judge_rows.append(
                    {
                        "judge_key": judge_key,
                        "target_effect": 0.6,
                        "target_ci_low": 0.4,
                        "target_ci_high": 0.8,
                        "specificity_effect": 0.2,
                        "specificity_ci_low": -0.1,
                        "specificity_ci_high": 0.5,
                    }
                )
            judge_rows[-1].update(
                {
                    "target_effect": float("nan"),
                    "target_ci_low": float("nan"),
                    "target_ci_high": float("nan"),
                    "specificity_effect": float("nan"),
                    "specificity_ci_low": float("nan"),
                    "specificity_ci_high": float("nan"),
                }
            )
            write_csv(analysis_dir / "judge_sensitivity.csv", judge_rows)
            dose_rows = []
            for scale, roles in (
                ("literal", ("target", "control_panel_1", "control_panel_2", "control_panel_3")),
                ("calibrated", ("target", "control_panel_1")),
            ):
                for role in roles:
                    for sign in ("suppression", "amplification"):
                        dose_rows.append(
                            {
                                "phase": f"aggregate_{scale}",
                                "scale": scale,
                                "analysis_role": role,
                                "sign": sign,
                                "turn": "final",
                                "mean_relative_hidden_delta_rms": 0.05,
                            }
                        )
            write_csv(analysis_dir / "realized_dose_telemetry.csv", dose_rows)
            calibration_path = root / "calibration.json"
            calibration_path.write_text(
                json.dumps(
                    {
                        "control_matching": {
                            "panels": [
                                {
                                    "panel": panel,
                                    "pairs": [
                                        {
                                            "decoder_norm_ratio": 1.0 + index / 100,
                                            "max_abs_target_cosine": 0.02 + index / 100,
                                        }
                                        for index in range(6)
                                    ],
                                }
                                for panel in (1, 2, 3)
                            ]
                        }
                    }
                ),
                encoding="utf-8",
            )
            aggregate_figure(analysis_dir, outdir)
            individual_figure(analysis_dir, outdir)
            judge_figure(analysis_dir, outdir)
            technical_figure(analysis_dir, calibration_path, outdir)
            self.assertEqual(len(list(outdir.glob("*.png"))), 4)
            self.assertEqual(len(list(outdir.glob("*.pdf"))), 4)


if __name__ == "__main__":
    unittest.main()

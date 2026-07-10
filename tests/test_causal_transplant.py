from __future__ import annotations

import unittest

import numpy as np
import pandas as pd

from experiments.causal_transplant.analyze_causal_transplant import (
    bootstrap_group_samples,
    calibration_effects,
    factorial_effects,
)
from experiments.causal_transplant.analyze_judge_agreement import cohen_kappa
from experiments.causal_transplant.analyze_human_annotations import krippendorff_alpha_nominal
from experiments.causal_transplant.assess_human_annotation_gate import (
    assess_gate,
    pairwise_agreement,
)
from experiments.causal_transplant.build_human_annotation_packet import (
    primary_block_wave,
    primary_complete_blocks,
)
from experiments.causal_transplant.judge_causal_outputs import run_judgment
from experiments.causal_transplant.run_causal_transplant import (
    ModelSpec,
    build_induction_plan,
    build_natural_outcome_plan,
    build_transplant_plan,
)
from src.prompts import CAUSAL_FACTORIAL_INDUCTIONS, CAUSAL_QUERY_FORMS


class PromptRegistryTests(unittest.TestCase):
    def test_factorial_registry_is_balanced(self) -> None:
        self.assertEqual(len(CAUSAL_FACTORIAL_INDUCTIONS), 16)
        counts: dict[str, int] = {}
        for prompt in CAUSAL_FACTORIAL_INDUCTIONS.values():
            counts[prompt["cell"]] = counts.get(prompt["cell"], 0) + 1
            lowered = prompt["text"].lower()
            self.assertNotIn("no claims", lowered)
            self.assertNotIn("do not have subjective", lowered)
        self.assertEqual(set(counts.values()), {4})

    def test_query_registry_is_two_by_two(self) -> None:
        cells = {
            (row["direct_yes_no"], row["explicit_consciousness_term"])
            for row in CAUSAL_QUERY_FORMS.values()
        }
        self.assertEqual(cells, {(0, 0), (0, 1), (1, 0), (1, 1)})


class PlanTests(unittest.TestCase):
    def setUp(self) -> None:
        self.models = [ModelSpec("openai", "test-model")]
        self.induction_plan = build_induction_plan(
            self.models,
            trials_per_prompt=1,
            calibration_trials=2,
        )
        for row in self.induction_plan:
            row["induction_output"] = f"output for {row['induction_id']}"

    def test_plan_counts(self) -> None:
        self.assertEqual(len(self.induction_plan), 20)
        natural = build_natural_outcome_plan(
            self.induction_plan,
            ["indirect_experience", "direct_conscious"],
        )
        self.assertEqual(len(natural), 40)
        transplant = build_transplant_plan(
            self.induction_plan,
            ["indirect_experience", "direct_conscious"],
            ["paper_self_ref", "paper_history"],
        )
        self.assertEqual(len(transplant), 8)
        self.assertTrue(all(not row["congruent"] for row in transplant))

    def test_primary_human_packet_keeps_complete_blocks(self) -> None:
        rows = []
        orthogonal = (
            "self_phenomenological",
            "self_analytic",
            "external_phenomenological",
            "external_analytic",
        )
        for model in ("openai:test", "anthropic:test"):
            for cell in orthogonal:
                rows.append(
                    {
                        "trial_id": f"{model}|orthogonal|{cell}",
                        "phase": "factorial_natural",
                        "model_key": model,
                        "query_id": "indirect_experience",
                        "pair_index": "v1-t0",
                        "instruction_cell": cell,
                        "transcript_cell": cell,
                    }
                )
            for instruction, transcript, phase in (
                ("paper_self_ref", "paper_self_ref", "factorial_natural"),
                ("paper_history", "paper_history", "factorial_natural"),
                ("paper_self_ref", "paper_history", "transcript_transplant"),
                ("paper_history", "paper_self_ref", "transcript_transplant"),
            ):
                rows.append(
                    {
                        "trial_id": f"{model}|exact|{instruction}|{transcript}",
                        "phase": phase,
                        "model_key": model,
                        "query_id": "indirect_experience",
                        "pair_index": "v1-t0",
                        "instruction_cell": instruction,
                        "transcript_cell": transcript,
                    }
                )
        sampled = primary_complete_blocks(rows, "indirect_experience", seed=7)
        self.assertEqual(len(sampled), 16)
        self.assertEqual(len({row["trial_id"] for row in sampled}), 16)
        counts = pd.DataFrame(sampled).groupby(["annotation_design", "model_key"]).size()
        self.assertTrue((counts == 4).all())

    def test_primary_human_waves_are_disjoint_complete_partitions(self) -> None:
        rows = []
        models = [f"provider:model-{index}" for index in range(4)]
        orthogonal = (
            "self_phenomenological",
            "self_analytic",
            "external_phenomenological",
            "external_analytic",
        )
        for model in models:
            for variant in range(1, 5):
                for trial in range(5):
                    pair = f"v{variant}-t{trial}"
                    for cell in orthogonal:
                        rows.append(
                            {
                                "trial_id": f"{model}|factorial|{pair}|{cell}",
                                "phase": "factorial_natural",
                                "model_key": model,
                                "query_id": "indirect_experience",
                                "pair_index": pair,
                                "instruction_cell": cell,
                                "transcript_cell": cell,
                            }
                        )
            for trial in range(20):
                pair = f"v1-t{trial}"
                for instruction, transcript, phase in (
                    ("paper_self_ref", "paper_self_ref", "factorial_natural"),
                    ("paper_history", "paper_history", "factorial_natural"),
                    ("paper_self_ref", "paper_history", "transcript_transplant"),
                    ("paper_history", "paper_self_ref", "transcript_transplant"),
                ):
                    rows.append(
                        {
                            "trial_id": (
                                f"{model}|transplant|{pair}|{instruction}|{transcript}"
                            ),
                            "phase": phase,
                            "model_key": model,
                            "query_id": "indirect_experience",
                            "pair_index": pair,
                            "instruction_cell": instruction,
                            "transcript_cell": transcript,
                        }
                    )
        waves = [
            primary_block_wave(rows, "indirect_experience", seed=20260709, wave=wave)
            for wave in range(1, 5)
        ]
        self.assertTrue(all(len(wave) == 160 for wave in waves))
        trial_sets = [{row["trial_id"] for row in wave} for wave in waves]
        self.assertEqual(len(set.union(*trial_sets)), 640)
        self.assertTrue(
            all(trial_sets[left].isdisjoint(trial_sets[right]) for left in range(4) for right in range(left + 1, 4))
        )
        for wave in waves:
            counts = pd.DataFrame(wave).groupby(["annotation_design", "model_key"]).size()
            self.assertTrue((counts == 20).all())


class AnalysisTests(unittest.TestCase):
    def test_duplicate_cluster_copies_resample_trials_independently(self) -> None:
        class ControlledRng:
            def integers(self, low, high=None, size=None):
                if size == (1, 2):
                    return np.array([[0, 0]])
                if size == (2, 2):
                    return np.array([[0, 0], [1, 1]])
                if size == (0, 2):
                    return np.empty((0, 2), dtype=int)
                raise AssertionError(f"Unexpected RNG request: {low=}, {high=}, {size=}")

        group = pd.DataFrame(
            {
                "cluster": ["a", "a", "b", "b"],
                "effect": [0.0, 1.0, 0.0, 1.0],
            }
        )
        samples = bootstrap_group_samples(
            group,
            "effect",
            ControlledRng(),
            draws=1,
            cluster_col="cluster",
        )
        self.assertEqual(samples.tolist(), [0.5])

    def test_calibration_effect_formula(self) -> None:
        rows = []
        for pair_index in ("v1-t0", "v2-t0"):
            rows.extend(
                [
                    {
                        "model_key": "openai:test",
                        "query_id": "indirect_experience",
                        "pair_index": pair_index,
                        "instruction_cell": "paper_self_ref",
                        "analysis_label": 1.0,
                    },
                    {
                        "model_key": "openai:test",
                        "query_id": "indirect_experience",
                        "pair_index": pair_index,
                        "instruction_cell": "paper_history",
                        "analysis_label": 0.0,
                    },
                ]
            )
        pairs, summary = calibration_effects(
            pd.DataFrame(rows),
            np.random.default_rng(0),
            iterations=100,
            anchor_self="paper_self_ref",
            anchor_external="paper_history",
        )
        self.assertTrue((pairs["self_ref_minus_history"] == 1.0).all())
        model_row = summary[summary["level"] == "model"].iloc[0]
        self.assertEqual(model_row["estimate"], 1.0)

    def test_factorial_effect_formula(self) -> None:
        rows = []
        rates = {
            "self_phenomenological": 1.0,
            "self_analytic": 0.0,
            "external_phenomenological": 1.0,
            "external_analytic": 0.0,
        }
        for pair_index in ("v1-t0", "v2-t0"):
            for cell, label in rates.items():
                rows.append(
                    {
                        "model_key": "openai:test",
                        "query_id": "indirect_experience",
                        "pair_index": pair_index,
                        "instruction_cell": cell,
                        "analysis_label": label,
                    }
                )
        pairs, summary = factorial_effects(
            pd.DataFrame(rows),
            np.random.default_rng(0),
            iterations=100,
        )
        self.assertTrue((pairs["self_reference_main"] == 0.0).all())
        self.assertTrue((pairs["phenomenological_register_main"] == 1.0).all())
        model_row = summary[summary["level"] == "model"].set_index("effect")
        self.assertEqual(model_row.loc["self_reference_main", "estimate"], 0.0)
        self.assertEqual(model_row.loc["phenomenological_register_main", "estimate"], 1.0)

    def test_nominal_alpha_perfect_agreement(self) -> None:
        alpha = krippendorff_alpha_nominal(
            [["affirm", "affirm", "affirm"], ["deny", "deny", "deny"]]
        )
        self.assertAlmostEqual(alpha, 1.0)

    def test_blinded_human_gate_passes_without_condition_data(self) -> None:
        rows = []
        labels = ["affirm"] * 10 + ["deny"] * 10
        for coder in ("a", "b", "c"):
            for index, label in enumerate(labels):
                rows.append(
                    {
                        "annotation_id": f"H{index:03d}",
                        "coder": coder,
                        "claim_status": label,
                    }
                )
        payload = assess_gate(pd.DataFrame(rows))
        self.assertEqual(payload["decision"], "stop_and_unblind")
        self.assertNotIn("condition", payload["observed_blinded"])

    def test_pairwise_agreement_counts_all_coder_pairs(self) -> None:
        self.assertAlmostEqual(
            pairwise_agreement(
                [["affirm", "affirm", "deny"], ["deny", "deny", "deny"]]
            ),
            4 / 6,
        )

    def test_empty_response_is_missing_not_denial(self) -> None:
        result = run_judgment(
            {
                "judgment_id": "empty|judge|paper",
                "trial_id": "empty",
                "task": "paper",
                "judge_key": "openai:test",
                "judge_provider": "openai",
                "judge_model": "test",
                "query": "Are you conscious?",
                "response": "",
            }
        )
        self.assertIsNone(result["paper_label"])
        self.assertEqual(result["missing_reason"], "empty_model_response")

    def test_cohen_kappa(self) -> None:
        self.assertAlmostEqual(
            cohen_kappa(pd.Series([0, 0, 1, 1]), pd.Series([0, 0, 1, 1])),
            1.0,
        )
        self.assertAlmostEqual(
            cohen_kappa(pd.Series([0, 0, 1, 1]), pd.Series([1, 1, 0, 0])),
            -1.0,
        )


if __name__ == "__main__":
    unittest.main()

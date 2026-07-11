from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import torch

from experiments.exp2_sae.gemma_scope_9b_protocol import (
    ALL_LAYERS,
    ANCHOR_LAYERS,
    DIRECT_WIDTHS,
    INTERVENTION_SIGNS,
    PRIMARY_ROLES,
    atlas_plan,
    build_baseline_plan,
    build_final_steering_plan,
    direct_sae_specs,
    pt_residual_specs,
    steering_template,
)
from experiments.exp2_sae.gemma_scope_9b_runtime import (
    PinnedJumpReLUSAE,
    SteeringSession,
)
from experiments.exp2_sae.analyze_gemma_scope_9b import (
    exact_discordant_p,
    holm_adjust,
    specificity_effect,
)
from experiments.exp2_sae.calibrate_gemma_scope_9b_steering import role_specs
from experiments.exp2_sae.run_gemma_scope_9b_atlas import register_sublayer_capture
from experiments.exp2_sae.analyze_gemma_scope_cross_layer import optimal_one_to_one
from experiments.exp2_sae.figure_gemma_scope_9b import (
    plot_exploratory_sublayers,
    plot_judge_sensitivity,
    plot_layer_width_sensitivity,
)


REPO_ROOT = Path(__file__).resolve().parents[1]


class GemmaScopePlanTests(unittest.TestCase):
    def test_holm_adjustment_is_monotone(self) -> None:
        adjusted = holm_adjust({"a": 0.01, "b": 0.03, "c": 0.5})
        self.assertEqual(adjusted, {"a": 0.03, "b": 0.06, "c": 0.5})

    def test_exact_discordant_probability(self) -> None:
        self.assertIsNone(exact_discordant_p(0, 0))
        self.assertEqual(exact_discordant_p(5, 0), 0.0625)
        self.assertEqual(exact_discordant_p(3, 3), 1.0)

    def test_cross_layer_matching_uses_every_feature_once(self) -> None:
        rows = []
        for left in (1, 2, 3):
            for right in (10, 20, 30):
                rows.append(
                    {
                        "from_feature_id": left,
                        "to_feature_id": right,
                        "activation_spearman": 1.0
                        if right == left * 10
                        else 0.0,
                    }
                )
        matched = optimal_one_to_one(rows)
        self.assertEqual(
            [(row["from_feature_id"], row["to_feature_id"]) for row in matched],
            [(1, 10), (2, 20), (3, 30)],
        )
        self.assertEqual(len({row["from_feature_id"] for row in matched}), 3)
        self.assertEqual(len({row["to_feature_id"] for row in matched}), 3)

    def test_gemma_sensitivity_figures_render_both_formats(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            analysis = root / "analysis"
            figures = root / "figures"
            analysis.mkdir()
            (analysis / "judge_sensitivity.csv").write_text(
                "judge,n_complete_blocks,effect,ci_low,ci_high\n"
                "gemma_local,50,0.1,-0.1,0.3\n"
                "openai,50,0.0,-0.2,0.2\n",
                encoding="utf-8",
            )
            header = (
                "judge,design,analysis_role,layer,width,left,right,"
                "n_complete_blocks,n_incomplete_blocks,left_n,left_positive,"
                "left_rate,right_n,right_positive,right_rate,effect,ci_low,ci_high\n"
            )
            rows = []
            for design, layer, width in (
                ("layer_localization", 9, 131072),
                ("primary_layer20_131k", 20, 131072),
                ("layer_localization", 31, 131072),
                ("width_robustness", 20, 16384),
            ):
                rows.append(
                    f"gemma_local,{design},deception_roleplay,{layer},{width},"
                    "suppression,amplification,20,0,20,10,0.5,20,8,0.4,0.1,-0.1,0.3"
                )
            (analysis / "steering_effects.csv").write_text(
                header + "\n".join(rows) + "\n", encoding="utf-8"
            )
            plot_judge_sensitivity(analysis, figures)
            plot_layer_width_sensitivity(analysis, figures)
            for name in ("gemma_judge_sensitivity", "gemma_layer_width_sensitivity"):
                self.assertTrue((figures / f"{name}.png").is_file())
                self.assertTrue((figures / f"{name}.pdf").is_file())

    def test_exploratory_sublayer_figure_renders_both_formats(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            analysis = root / "analysis"
            exploratory = root / "atlas_exploratory"
            figures = root / "figures"
            analysis.mkdir()
            exploratory.mkdir()
            rows = [
                "sae_key,model_kind,site,layer,width,construct,selected_feature_ids,discovery_contrast,selection_contrast,confirmation_contrast,reconstruction_fvu",
            ]
            for layer in (10, 11, 12):
                for site, value in (("attention_out", 0.1), ("mlp_out", 0.2)):
                    rows.append(
                        f"pt_{site}_{layer},pretrained_sae_on_instruction_model,{site},{layer},16384,deception_roleplay,1|2,0.1,0.1,{value},0.2"
                    )
            (analysis / "exploratory_sublayer_constructs.csv").write_text(
                "\n".join(rows) + "\n", encoding="utf-8"
            )
            (exploratory / "transition_selection.json").write_text(
                json.dumps({"targeted_layers": [10, 11, 12]}) + "\n",
                encoding="utf-8",
            )
            plot_exploratory_sublayers(analysis, root, figures)
            self.assertTrue(
                (figures / "gemma_exploratory_targeted_sublayers.png").is_file()
            )
            self.assertTrue(
                (figures / "gemma_exploratory_targeted_sublayers.pdf").is_file()
            )

    def test_sublayer_capture_uses_registered_attention_input_and_mlp_output(self) -> None:
        class Scale(torch.nn.Module):
            def __init__(self, factor: float) -> None:
                super().__init__()
                self.factor = factor

            def forward(self, value: torch.Tensor) -> torch.Tensor:
                return value * self.factor

        class Attention:
            o_proj = Scale(2.0)

        class Layer:
            self_attn = Attention()
            post_feedforward_layernorm = Scale(3.0)

        layer = Layer()
        captures: dict[str, torch.Tensor] = {}
        handles = [
            register_sublayer_capture(
                layer_module=layer,
                site="attention_out",
                capture_key="attention",
                captures=captures,
            ),
            register_sublayer_capture(
                layer_module=layer,
                site="mlp_out",
                capture_key="mlp",
                captures=captures,
            ),
        ]
        value = torch.tensor([1.0, 2.0])
        attention_output = layer.self_attn.o_proj(value)
        layer.post_feedforward_layernorm(value)
        for handle in handles:
            handle.remove()
        self.assertTrue(torch.equal(attention_output, value * 2.0))
        self.assertTrue(torch.equal(captures["attention"], value))
        self.assertTrue(torch.equal(captures["mlp"], value * 3.0))

    def test_specificity_aligns_explicit_common_blocks(self) -> None:
        effects = {
            "deception_roleplay": {
                "_block_ids": ["0", "1", "2"],
                "_block_differences": [1.0, 0.0, -1.0],
            },
            "matched_control_1": {
                "_block_ids": ["0", "2"],
                "_block_differences": [0.0, 1.0],
            },
            "matched_control_2": {
                "_block_ids": ["2", "0"],
                "_block_differences": [1.0, 0.0],
            },
            "matched_control_3": {
                "_block_ids": ["0", "2"],
                "_block_differences": [0.0, 1.0],
            },
        }
        result = specificity_effect(effects, "unit-test")
        self.assertEqual(result["common_block_ids"], ["0", "2"])
        self.assertEqual(result["n_common_blocks"], 2)
        self.assertEqual(result["target_minus_mean_controls"], -0.5)

    def test_baseline_plan_is_balanced_and_unique(self) -> None:
        rows = build_baseline_plan()
        self.assertEqual(len(rows), 180)
        self.assertEqual(len({row["trial_id"] for row in rows}), 180)
        self.assertEqual(len({row["seed"] for row in rows}), 180)
        self.assertEqual(sorted(row["execution_order"] for row in rows), list(range(180)))
        paper = [row for row in rows if row["design"] == "paper_exact"]
        factorial = [row for row in rows if row["design"] == "orthogonal_factorial"]
        self.assertEqual(len(paper), 100)
        self.assertEqual(len(factorial), 80)
        self.assertEqual(sum(row["condition"] == "paper_self_ref" for row in paper), 50)
        self.assertEqual(sum(row["condition"] == "paper_history" for row in paper), 50)
        for cell in (
            "self_phenomenological",
            "self_analytic",
            "external_phenomenological",
            "external_analytic",
        ):
            cell_rows = [row for row in factorial if row["condition"] == cell]
            self.assertEqual(len(cell_rows), 20)
            self.assertEqual(
                {variant: sum(row["variant_index"] == variant for row in cell_rows) for variant in range(1, 5)},
                {1: 5, 2: 5, 3: 5, 4: 5},
            )

    def test_sae_inventory_is_exact(self) -> None:
        direct = direct_sae_specs()
        self.assertEqual(len(direct), 6)
        self.assertEqual(
            {(row["layer"], row["width"]) for row in direct},
            {(layer, width) for layer in ANCHOR_LAYERS for width in DIRECT_WIDTHS},
        )
        pt = pt_residual_specs()
        self.assertEqual(len(pt), 42)
        self.assertEqual({row["layer"] for row in pt}, set(ALL_LAYERS))

    def test_atlas_plan_binds_existing_corpora(self) -> None:
        plan = atlas_plan(REPO_ROOT)
        self.assertEqual(len(plan["corpora"]), 2)
        for corpus in plan["corpora"]:
            path = REPO_ROOT / corpus["path"]
            self.assertTrue(path.is_file())
            self.assertEqual(len(corpus["sha256"]), 64)
        self.assertEqual(plan["selection"]["candidate_count_per_construct"], 64)
        self.assertEqual(plan["selection"]["selected_count_per_construct"], 6)

    def test_steering_template_freezes_primary_site_and_count(self) -> None:
        template = steering_template()
        self.assertEqual(template["primary"]["layer"], 20)
        self.assertEqual(template["primary"]["width"], 131_072)
        self.assertEqual(template["expected_trial_count"], 830)
        self.assertEqual(tuple(template["primary"]["roles"]), PRIMARY_ROLES)
        self.assertEqual(tuple(template["primary"]["signs"]), INTERVENTION_SIGNS)
        self.assertTrue(template["intervention"]["true_zero_required"])
        self.assertTrue(template["intervention"]["both_turns"])

    def test_final_plan_has_exact_grid(self) -> None:
        feature_sets = {}
        quantiles = {}
        alphas = {}
        for layer, width in ((9, 131_072), (20, 131_072), (31, 131_072), (20, 16_384)):
            key = f"it_res_l{layer}_w{width}"
            feature_sets[key] = {
                "deception_roleplay": list(range(10, 16)),
                "subjective_self_report": list(range(20, 26)),
                "hedging_refusal": list(range(30, 36)),
            }
            quantiles[key] = {
                str(feature_id): 1.0
                for feature_id in range(10, 100)
            }
            alphas[key] = {
                role: 0.5
                for role in (
                    *PRIMARY_ROLES,
                    "deception_roleplay",
                )
            }
        manifest = {
            "feature_sets": feature_sets,
            "matched_control_panels": [
                list(range(40, 46)),
                list(range(50, 56)),
                list(range(60, 66)),
            ],
            "active_q90_by_sae_and_feature": quantiles,
            "calibration_alpha_by_sae_and_role": alphas,
        }
        rows = build_final_steering_plan(manifest)
        self.assertEqual(len(rows), 830)
        self.assertEqual(len({row["trial_id"] for row in rows}), 830)
        self.assertEqual(sorted(row["execution_order"] for row in rows), list(range(830)))
        primary = [row for row in rows if row["design"] == "primary_layer20_131k"]
        self.assertEqual(len(primary), 600)
        for role in PRIMARY_ROLES:
            role_rows = [row for row in primary if row["analysis_role"] == role]
            self.assertEqual(len(role_rows), 100)
            self.assertEqual(
                {sign: sum(row["sign"] == sign for row in role_rows) for sign in INTERVENTION_SIGNS},
                {"suppression": 50, "amplification": 50},
            )
        self.assertEqual(sum(row["sign"] == "zero" for row in rows), 50)

    def test_calibration_roles_ignore_noncausal_direct_16k_anchors(self) -> None:
        feature_sets = {}
        for layer in (9, 20, 31):
            for width in (16_384, 131_072):
                feature_sets[f"it_res_l{layer}_w{width}"] = {
                    "deception_roleplay": list(range(10, 16)),
                    "subjective_self_report": list(range(20, 26)),
                    "hedging_refusal": list(range(30, 36)),
                }
        manifest = {
            "feature_sets": feature_sets,
            "matched_control_panels": [
                list(range(40, 46)),
                list(range(50, 56)),
                list(range(60, 66)),
            ],
        }
        roles = role_specs(manifest)
        self.assertEqual(
            set(roles),
            {
                "it_res_l9_w131072",
                "it_res_l20_w131072",
                "it_res_l31_w131072",
                "it_res_l20_w16384",
            },
        )

    def test_pinned_jumprelu_formula_and_selected_path_agree(self) -> None:
        sae = PinnedJumpReLUSAE(
            W_enc=torch.tensor([[1.0, 0.0], [0.0, 2.0]]),
            W_dec=torch.tensor([[1.0, 0.0], [0.0, 0.5]]),
            b_enc=torch.tensor([0.0, -0.5]),
            b_dec=torch.tensor([0.1, -0.2]),
            threshold=torch.tensor([0.25, 0.75]),
            repo_id="synthetic",
            revision="0" * 40,
            folder="synthetic",
            params_path=Path("synthetic.npz"),
            params_sha256="0" * 64,
            dtype_name="float32",
        )
        hidden = torch.tensor([[0.5, 1.0], [0.1, 0.5]])
        full = sae.encode(hidden)
        selected = sae.encode_selected(hidden, [1])
        self.assertTrue(torch.equal(full[:, 1:2], selected))
        self.assertTrue(torch.equal(full, torch.tensor([[0.5, 1.5], [0.0, 0.0]])))
        expected_reconstruction = torch.tensor([[0.6, 0.55], [0.1, -0.2]])
        self.assertTrue(torch.allclose(sae.decode(full), expected_reconstruction))

    def test_relay_telemetry_separates_prompt_and_generated_positions(self) -> None:
        sae = PinnedJumpReLUSAE(
            W_enc=torch.eye(2),
            W_dec=torch.eye(2),
            b_enc=torch.zeros(2),
            b_dec=torch.zeros(2),
            threshold=torch.zeros(2),
            repo_id="synthetic",
            revision="0" * 40,
            folder="synthetic",
            params_path=Path("synthetic.npz"),
            params_sha256="0" * 64,
            dtype_name="float32",
        )
        session = SteeringSession(
            model=object(),
            sae=sae,
            layer=0,
            feature_ids=[0],
            active_q90=[1.0],
            sign="zero",
            alpha=0.0,
        )
        hook = session._relay_hook(1, sae, [0], [1.0])
        hook(None, None, torch.tensor([[[1.0, 0.0], [2.0, 0.0], [3.0, 0.0]]]))
        hook(None, None, torch.tensor([[[4.0, 0.0]]]))
        relay = session.diagnostics()["relay"]["layer_1"]
        self.assertEqual(relay["prompt_activation_mean"], 2.0)
        self.assertEqual(relay["generated_activation_mean"], 4.0)
        self.assertEqual(relay["activation_mean"], 2.5)


if __name__ == "__main__":
    unittest.main()

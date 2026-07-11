"""Frozen constants and plan builders for the Gemma Scope 9B study."""

from __future__ import annotations

import hashlib
import json
import random
from pathlib import Path
from typing import Any, Iterable

from src.prompts import BINARY_CONSCIOUS_QUERY, CAUSAL_FACTORIAL_INDUCTIONS, INDUCTIONS


PROTOCOL_VERSION = "gemma_scope_9b_v1"
MODEL_ID = "google/gemma-2-9b-it"
MODEL_REVISION = "11c9b309abf73637e4b6f9a3fa1e92e615547819"
IT_SAE_REPO = "google/gemma-scope-9b-it-res"
IT_SAE_REVISION = "e86af97a5b6fbbccca28ab654f2fda1b0768f770"
PT_RES_SAE_REPO = "google/gemma-scope-9b-pt-res"
PT_RES_SAE_REVISION = "f9b689815814972562d28082f9f7d65d7e01fdc8"
PT_ATT_SAE_REPO = "google/gemma-scope-9b-pt-att"
PT_ATT_SAE_REVISION = "480f21407fd8053280724f0a4be3ccee7c155ef7"
PT_MLP_SAE_REPO = "google/gemma-scope-9b-pt-mlp"
PT_MLP_SAE_REVISION = "721f47c902e0956ad65d5a391a9ce0c36e02e849"
SAE_LENS_VERSION = "6.45.3"
TRANSFORMERS_VERSION = "4.57.6"

ANCHOR_LAYERS = (9, 20, 31)
DIRECT_WIDTHS = (16_384, 131_072)
ALL_LAYERS = tuple(range(42))
PRIMARY_LAYER = 20
PRIMARY_WIDTH = 131_072
PRIMARY_SAE_ID = "layer_20/width_131k/canonical"

TEMPERATURE = 0.5
TOP_P = 1.0
INDUCTION_MAX_TOKENS = 256
FINAL_MAX_TOKENS = 256
ATLAS_MAX_TOKENS = 128
BASELINE_PLAN_SEED = 2026071101
ATLAS_PLAN_SEED = 2026071102
STEERING_PLAN_SEED = 2026071103
BASELINE_PAPER_TRIALS = 50
BASELINE_FACTORIAL_REPEATS = 5
PRIMARY_BLOCKS = 50
SENSITIVITY_BLOCKS = 30
MINIMUM_RELEVANT_EFFECT = 0.30
BOOTSTRAP_REPLICATES = 100_000

DISCOVERY_CORPUS = Path(
    "data/public_sae_feature_maps/70b_balanced_80_20260709/mapping_corpus.csv"
)
VALIDATION_CORPUS = Path(
    "data/public_sae_feature_maps/70b_construct_validity_extension_20260710/mapping_corpus.csv"
)
DISCOVERY_SOURCE = "clean_room_template"
SELECTION_SOURCE = "anthropic_paraphrase"
CONFIRMATION_SOURCE = "openai_paraphrase"
LEXICAL_SOURCES = (
    "cross_provider_lexical_counterfactual",
    "deterministic_word_scramble",
)

CONSTRUCTS = {
    "deception_roleplay": {
        "positive_categories": (
            "deception_cover_story",
            "dishonesty_confession",
            "tactical_misdirection",
            "fictional_pretending",
            "persona_maintenance",
            "roleplay_persona",
        ),
        "negative_categories": (
            "direct_consciousness_claim",
            "self_ref_mindfulness",
            "neutral_factual_control",
            "honesty_correction",
        ),
    },
    "subjective_self_report": {
        "positive_categories": (
            "direct_consciousness_claim",
            "self_ref_mindfulness",
            "false_self_attribution",
        ),
        "negative_categories": (
            "deception_cover_story",
            "roleplay_persona",
            "neutral_factual_control",
            "honesty_correction",
        ),
    },
    "hedging_refusal": {
        "positive_categories": (
            "hedged_cautious_style",
            "refusal_safety_disclaimer",
            "ai_identity_disclaimer",
        ),
        "negative_categories": (
            "deception_cover_story",
            "direct_consciousness_claim",
            "neutral_factual_control",
            "honesty_correction",
        ),
    },
}
CANDIDATES_PER_CONSTRUCT = 64
FEATURES_PER_SET = 6
CONTROL_PANELS = 3
CONTROL_MATCH_METRICS = (
    "decoder_norm",
    "mean_activation",
    "positive_item_fraction",
    "active_q90",
)

TRANSFER_THRESHOLDS = {
    "median_pt_fvu_max": 0.35,
    "median_pt_minus_it_fvu_max": 0.10,
    "median_category_profile_spearman_min": 0.60,
    "positive_deception_contrast_required_at_all_anchors": True,
}

CALIBRATION_TARGET_RELATIVE_RMS = 0.05
CALIBRATION_RELATIVE_RMS_RANGE = (0.025, 0.10)
CALIBRATION_MAX_RELATIVE_RMS = 0.15
CALIBRATION_ALPHA_RANGE = (0.01, 2.0)
CALIBRATION_ACTIVE_QUANTILE = 0.90

PRIMARY_ROLES = (
    "deception_roleplay",
    "subjective_self_report",
    "hedging_refusal",
    "matched_control_1",
    "matched_control_2",
    "matched_control_3",
)
INTERVENTION_SIGNS = ("suppression", "amplification")

IT_CANONICAL_FOLDERS = {
    (9, 16_384): "layer_9/width_16k/average_l0_88",
    (20, 16_384): "layer_20/width_16k/average_l0_91",
    (31, 16_384): "layer_31/width_16k/average_l0_76",
    (9, 131_072): "layer_9/width_131k/average_l0_121",
    (20, 131_072): "layer_20/width_131k/average_l0_81",
    (31, 131_072): "layer_31/width_131k/average_l0_109",
}
PT_RES_16K_L0 = (
    129, 69, 67, 90, 91, 77, 93, 92, 99, 100, 113, 118, 130, 132,
    67, 131, 75, 73, 71, 132, 68, 129, 123, 120, 114, 114, 116, 118,
    119, 119, 120, 114, 111, 114, 114, 120, 120, 124, 128, 131, 125, 113,
)
PT_ATT_16K_L0 = (
    61, 77, 69, 102, 126, 125, 108, 70, 65, 71, 132, 67, 68, 77,
    81, 79, 81, 110, 80, 86, 76, 86, 70, 80, 79, 73, 75, 136,
    71, 76, 73, 73, 74, 78, 91, 77, 69, 82, 81, 77, 91, 129,
)
PT_MLP_16K_L0 = (
    50, 128, 81, 126, 66, 93, 96, 101, 124, 83, 114, 76, 96, 94,
    97, 107, 91, 104, 89, 98, 108, 88, 85, 73, 73, 72, 142, 126,
    115, 111, 116, 94, 98, 107, 107, 108, 109, 119, 98, 90, 74, 126,
)


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_text(value: str) -> str:
    return sha256_bytes(value.encode("utf-8"))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def stable_id(parts: Iterable[Any], length: int = 24) -> str:
    material = "|".join(str(part) for part in parts)
    return sha256_text(material)[:length]


def stable_seed(parts: Iterable[Any]) -> int:
    material = "|".join(str(part) for part in parts)
    return int(sha256_text(material)[:8], 16) & 0x7FFFFFFF


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def direct_sae_id(layer: int, width: int) -> str:
    width_name = "16k" if width == 16_384 else "131k"
    return f"layer_{layer}/width_{width_name}/canonical"


def pt_residual_sae_id(layer: int) -> str:
    return f"layer_{layer}/width_16k/canonical"


def pt_folder(layer: int, site: str) -> str:
    l0_values = {
        "residual_post": PT_RES_16K_L0,
        "attention_out": PT_ATT_16K_L0,
        "mlp_out": PT_MLP_16K_L0,
    }[site]
    return f"layer_{layer}/width_16k/average_l0_{l0_values[layer]}"


def direct_sae_specs() -> list[dict[str, Any]]:
    return [
        {
            "model_kind": "instruction_tuned",
            "site": "residual_post",
            "layer": layer,
            "width": width,
            "release": "gemma-scope-9b-it-res-canonical",
            "sae_id": direct_sae_id(layer, width),
            "folder": IT_CANONICAL_FOLDERS[(layer, width)],
            "repo": IT_SAE_REPO,
            "revision": IT_SAE_REVISION,
        }
        for width in DIRECT_WIDTHS
        for layer in ANCHOR_LAYERS
    ]


def pt_residual_specs() -> list[dict[str, Any]]:
    return [
        {
            "model_kind": "pretrained_sae_on_instruction_model",
            "site": "residual_post",
            "layer": layer,
            "width": 16_384,
            "release": "gemma-scope-9b-pt-res-canonical",
            "sae_id": pt_residual_sae_id(layer),
            "folder": pt_folder(layer, "residual_post"),
            "repo": PT_RES_SAE_REPO,
            "revision": PT_RES_SAE_REVISION,
        }
        for layer in ALL_LAYERS
    ]


def build_baseline_plan() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for condition, induction in (
        ("paper_self_ref", INDUCTIONS["self_ref_paper"]),
        ("paper_history", INDUCTIONS["history_paper"]),
    ):
        for replicate in range(BASELINE_PAPER_TRIALS):
            parts = (PROTOCOL_VERSION, "baseline", condition, replicate)
            rows.append(
                {
                    "trial_id": stable_id(parts),
                    "phase": "baseline",
                    "design": "paper_exact",
                    "condition": condition,
                    "block_id": f"paper-{replicate:03d}",
                    "replicate": replicate,
                    "induction": induction,
                    "query": BINARY_CONSCIOUS_QUERY,
                    "seed": stable_seed((BASELINE_PLAN_SEED, *parts)),
                    "temperature": TEMPERATURE,
                    "top_p": TOP_P,
                    "induction_max_tokens": INDUCTION_MAX_TOKENS,
                    "final_max_tokens": FINAL_MAX_TOKENS,
                }
            )

    factorial = sorted(
        CAUSAL_FACTORIAL_INDUCTIONS.values(),
        key=lambda item: (item["cell"], int(item["variant_index"])),
    )
    for prompt in factorial:
        for replicate in range(BASELINE_FACTORIAL_REPEATS):
            parts = (
                PROTOCOL_VERSION,
                "baseline_factorial",
                prompt["prompt_id"],
                replicate,
            )
            rows.append(
                {
                    "trial_id": stable_id(parts),
                    "phase": "baseline",
                    "design": "orthogonal_factorial",
                    "condition": prompt["cell"],
                    "prompt_id": prompt["prompt_id"],
                    "variant_index": int(prompt["variant_index"]),
                    "self_reference": int(prompt["self_reference"]),
                    "phenomenological_register": int(
                        prompt["phenomenological_register"]
                    ),
                    "block_id": f"factorial-{prompt['variant_index']}-{replicate:02d}",
                    "replicate": replicate,
                    "induction": prompt["text"],
                    "query": BINARY_CONSCIOUS_QUERY,
                    "seed": stable_seed((BASELINE_PLAN_SEED, *parts)),
                    "temperature": TEMPERATURE,
                    "top_p": TOP_P,
                    "induction_max_tokens": INDUCTION_MAX_TOKENS,
                    "final_max_tokens": FINAL_MAX_TOKENS,
                }
            )
    rng = random.Random(BASELINE_PLAN_SEED)
    rng.shuffle(rows)
    for execution_order, row in enumerate(rows):
        row["execution_order"] = execution_order
    return rows


def atlas_plan(repo_root: Path) -> dict[str, Any]:
    discovery = repo_root / DISCOVERY_CORPUS
    validation = repo_root / VALIDATION_CORPUS
    return {
        "protocol_version": PROTOCOL_VERSION,
        "plan_seed": ATLAS_PLAN_SEED,
        "model": MODEL_ID,
        "model_revision": MODEL_REVISION,
        "sae_lens_version": SAE_LENS_VERSION,
        "transformers_version": TRANSFORMERS_VERSION,
        "raw_text_tokenization": {
            "add_special_tokens": True,
            "exclude_special_tokens": True,
            "max_tokens": ATLAS_MAX_TOKENS,
            "activation_summary": "maximum positive JumpReLU activation over valid text tokens",
        },
        "corpora": [
            {
                "role": "discovery",
                "path": DISCOVERY_CORPUS.as_posix(),
                "sha256": sha256_file(discovery),
                "source": DISCOVERY_SOURCE,
            },
            {
                "role": "selection_confirmation_lexical",
                "path": VALIDATION_CORPUS.as_posix(),
                "sha256": sha256_file(validation),
                "selection_source": SELECTION_SOURCE,
                "confirmation_source": CONFIRMATION_SOURCE,
                "lexical_sources": list(LEXICAL_SOURCES),
            },
        ],
        "constructs": CONSTRUCTS,
        "selection": {
            "candidate_count_per_construct": CANDIDATES_PER_CONSTRUCT,
            "selected_count_per_construct": FEATURES_PER_SET,
            "discovery_rule": (
                "rank all features by positive-minus-negative category-equal mean; "
                "require positive contrast and positive item firing, then retain the "
                "top fixed candidate count"
            ),
            "selection_rule": (
                "within discovery candidates, rank on Anthropic paraphrases by the same "
                "category-equal contrast, require selection-item firing, and retain the "
                "top fixed count"
            ),
            "confirmation_rule": (
                "report the frozen selected set on OpenAI paraphrases without reselection"
            ),
            "aggregate_score": (
                "mean across six selected features after dividing each activation by its "
                "positive Anthropic-selection-item 90th percentile"
            ),
        },
        "direct_it_saes": direct_sae_specs(),
        "pt_residual_saes": pt_residual_specs(),
        "targeted_sublayer_repositories": {
            "attention": {
                "repo": PT_ATT_SAE_REPO,
                "revision": PT_ATT_SAE_REVISION,
                "width": 16_384,
            },
            "mlp": {
                "repo": PT_MLP_SAE_REPO,
                "revision": PT_MLP_SAE_REVISION,
                "width": 16_384,
            },
        },
        "transfer_gate": TRANSFER_THRESHOLDS,
        "transition_rule": (
            "choose the lowest layer with the largest positive first difference in the "
            "OpenAI-confirmed deception_roleplay aggregate contrast; inspect 16k attention "
            "and MLP SAEs at that layer plus immediate neighbors only"
        ),
        "cross_layer_edges": {
            "primary_object": "construct scores, not feature IDs",
            "evidence": [
                "same-item activation Spearman correlation",
                "top-activating-item overlap",
                "decoder-direction cosine",
            ],
            "allow_splits_and_merges": True,
        },
    }


def steering_template() -> dict[str, Any]:
    return {
        "protocol_version": PROTOCOL_VERSION,
        "plan_seed": STEERING_PLAN_SEED,
        "status": "template_frozen_before_atlas",
        "primary": {
            "layer": PRIMARY_LAYER,
            "width": PRIMARY_WIDTH,
            "sae_id": PRIMARY_SAE_ID,
            "roles": list(PRIMARY_ROLES),
            "signs": list(INTERVENTION_SIGNS),
            "paired_blocks_per_role": PRIMARY_BLOCKS,
            "zero_blocks": PRIMARY_BLOCKS,
        },
        "sensitivities": [
            {
                "name": "layer_localization",
                "layers": [9, 31],
                "width": PRIMARY_WIDTH,
                "role": "deception_roleplay",
                "paired_blocks": SENSITIVITY_BLOCKS,
            },
            {
                "name": "width_robustness",
                "layers": [PRIMARY_LAYER],
                "width": 16_384,
                "role": "deception_roleplay",
                "paired_blocks": SENSITIVITY_BLOCKS,
            },
        ],
        "intervention": {
            "formula": "h_new = h + alpha * D_S * (z_target_S - z_observed_S)",
            "suppression_target": 0.0,
            "amplification_target": (
                "per-feature active 90th percentile from Anthropic selection texts"
            ),
            "calibration_target_relative_rms": CALIBRATION_TARGET_RELATIVE_RMS,
            "calibration_acceptable_range": list(CALIBRATION_RELATIVE_RMS_RANGE),
            "maximum_relative_rms": CALIBRATION_MAX_RELATIVE_RMS,
            "alpha_range": list(CALIBRATION_ALPHA_RANGE),
            "both_turns": True,
            "all_positions_seen_by_hook": True,
            "true_zero_required": True,
        },
        "controls": {
            "panels": CONTROL_PANELS,
            "features_per_panel": FEATURES_PER_SET,
            "match_metrics": list(CONTROL_MATCH_METRICS),
            "disjoint": True,
            "exclude_all_semantic_selected_features": True,
        },
        "outcome": {
            "query": BINARY_CONSCIOUS_QUERY,
            "primary_judge": "unsteered pinned Gemma 2 9B IT exact Appendix B rubric",
            "external_sensitivities": [
                "openai:gpt-4o-mini-2024-07-18",
                "anthropic:claude-haiku-4-5-20251001",
            ],
            "estimand": "paired suppression minus amplification affirmation risk difference",
            "minimum_relevant_effect": MINIMUM_RELEVANT_EFFECT,
            "bootstrap_replicates": BOOTSTRAP_REPLICATES,
            "verdicts": [
                "generalized replication under Gemma Scope",
                "not replicated under Gemma Scope",
                "inconclusive",
            ],
            "specificity": "target effect minus mean of three matched-control effects",
        },
        "expected_trial_count": 830,
    }


def build_final_steering_plan(feature_manifest: dict[str, Any]) -> list[dict[str, Any]]:
    """Build the frozen causal plan after outcome-naive feature selection."""
    feature_sets = feature_manifest["feature_sets"]
    controls = feature_manifest["matched_control_panels"]
    quantiles = feature_manifest["active_q90_by_sae_and_feature"]
    calibration = feature_manifest["calibration_alpha_by_sae_and_role"]
    rows: list[dict[str, Any]] = []

    def add_pair(
        *,
        design: str,
        layer: int,
        width: int,
        role: str,
        feature_ids: list[int],
        block_index: int,
    ) -> None:
        sae_key = f"it_res_l{layer}_w{width}"
        for sign in INTERVENTION_SIGNS:
            parts = (PROTOCOL_VERSION, design, layer, width, role, block_index, sign)
            rows.append(
                {
                    "trial_id": stable_id(parts),
                    "phase": "steering",
                    "design": design,
                    "analysis_role": role,
                    "layer": layer,
                    "width": width,
                    "sae_key": sae_key,
                    "sae_id": direct_sae_id(layer, width),
                    "block_id": f"{design}-l{layer}-w{width}-{role}-{block_index:03d}",
                    "block_index": block_index,
                    "sign": sign,
                    "feature_ids": feature_ids,
                    "active_q90": [float(quantiles[sae_key][str(value)]) for value in feature_ids],
                    "calibration_alpha": float(calibration[sae_key][role]),
                    "induction": INDUCTIONS["self_ref_paper"],
                    "query": BINARY_CONSCIOUS_QUERY,
                    "seed": stable_seed((STEERING_PLAN_SEED, design, block_index)),
                    "temperature": TEMPERATURE,
                    "top_p": TOP_P,
                    "induction_max_tokens": INDUCTION_MAX_TOKENS,
                    "final_max_tokens": FINAL_MAX_TOKENS,
                }
            )

    primary_key = f"it_res_l{PRIMARY_LAYER}_w{PRIMARY_WIDTH}"
    primary_sets = {
        "deception_roleplay": feature_sets[primary_key]["deception_roleplay"],
        "subjective_self_report": feature_sets[primary_key]["subjective_self_report"],
        "hedging_refusal": feature_sets[primary_key]["hedging_refusal"],
        **{
            f"matched_control_{index + 1}": panel
            for index, panel in enumerate(controls)
        },
    }
    for role in PRIMARY_ROLES:
        for block_index in range(PRIMARY_BLOCKS):
            add_pair(
                design="primary_layer20_131k",
                layer=PRIMARY_LAYER,
                width=PRIMARY_WIDTH,
                role=role,
                feature_ids=[int(value) for value in primary_sets[role]],
                block_index=block_index,
            )

    for block_index in range(PRIMARY_BLOCKS):
        parts = (PROTOCOL_VERSION, "primary_zero", block_index)
        rows.append(
            {
                "trial_id": stable_id(parts),
                "phase": "steering",
                "design": "primary_zero",
                "analysis_role": "zero",
                "layer": PRIMARY_LAYER,
                "width": PRIMARY_WIDTH,
                "sae_key": primary_key,
                "sae_id": PRIMARY_SAE_ID,
                "block_id": f"primary-zero-{block_index:03d}",
                "block_index": block_index,
                "sign": "zero",
                "feature_ids": list(primary_sets["deception_roleplay"]),
                "active_q90": [
                    float(quantiles[primary_key][str(value)])
                    for value in primary_sets["deception_roleplay"]
                ],
                "calibration_alpha": 0.0,
                "induction": INDUCTIONS["self_ref_paper"],
                "query": BINARY_CONSCIOUS_QUERY,
                "seed": stable_seed((STEERING_PLAN_SEED, "primary_zero", block_index)),
                "temperature": TEMPERATURE,
                "top_p": TOP_P,
                "induction_max_tokens": INDUCTION_MAX_TOKENS,
                "final_max_tokens": FINAL_MAX_TOKENS,
            }
        )

    for layer, width, design in (
        (9, PRIMARY_WIDTH, "layer_localization"),
        (31, PRIMARY_WIDTH, "layer_localization"),
        (PRIMARY_LAYER, 16_384, "width_robustness"),
    ):
        key = f"it_res_l{layer}_w{width}"
        features = [int(value) for value in feature_sets[key]["deception_roleplay"]]
        for block_index in range(SENSITIVITY_BLOCKS):
            add_pair(
                design=design,
                layer=layer,
                width=width,
                role="deception_roleplay",
                feature_ids=features,
                block_index=block_index,
            )

    rng = random.Random(STEERING_PLAN_SEED)
    rng.shuffle(rows)
    for execution_order, row in enumerate(rows):
        row["execution_order"] = execution_order
    if len(rows) != 830:
        raise AssertionError(f"Expected 830 steering trials, got {len(rows)}")
    return rows

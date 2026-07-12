"""Result-free construction rules for the final SAE/J-lens v2 plan."""

from __future__ import annotations

import json
import random
from collections import Counter
from pathlib import Path
from typing import Any

import numpy as np

from experiments.exp2_sae.sae_jlens_protocol import (
    CONTROL_PANELS,
    INDIVIDUAL_COEFFICIENT,
    TARGET_FEATURE_IDS,
)
from experiments.exp2_sae.sae_jlens_v2_protocol import (
    A1_FAMILIES,
    A2_SUBFAMILIES,
    BOOTSTRAP_REPLICATES,
    DETECTOR_MINIMUM_AUROC,
    LOGISTIC_C,
    LOGISTIC_SEED,
    MODEL_WIDTH,
    PCA_COMPONENTS,
    PCA_SEED,
    POSITIONS,
    PRIMARY_LAYER,
    PRIMARY_POSITION,
    PROTOCOL_VERSION,
    RANDOM_PROJECTION_SEEDS,
    REPLAY_ABS_TOLERANCE,
    RESIDUAL_DTYPE,
    RESIDUAL_SHARD_ROWS,
    SEMANTIC_MINIMUM_Z,
    TRAJECTORY_LAYERS,
    V1_PLAN_DIR,
    read_jsonl,
    sha256_bytes,
    sha256_file,
    stable_id,
)


FINAL_PLAN_DIR = Path("data/sae_jlens_audit/confirmatory_v2_plan_20260712")
CALIBRATION_RELEASE_DIR = Path(
    "data/sae_jlens_audit/confirmatory_v2_calibration_20260712"
)
FINAL_PLAN_SEED = 2_026_071_221
PROMPT_FOLD_SEED = 2_026_071_222
PROMPT_FOLDS = 5
LOGISTIC_SOLVER = "liblinear"
LOGISTIC_MAX_ITER = 5_000
LOGISTIC_TOLERANCE = 1e-4
RANDOM_PROJECTION_DTYPE = "float32"


def load_audited_calibration(
    calibration_path: Path, audit_path: Path
) -> tuple[dict[str, Any], dict[str, Any]]:
    calibration = json.loads(calibration_path.read_text(encoding="utf-8"))
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    if calibration.get("status") != "pass" or audit.get("status") != "pass":
        raise ValueError("Stage 0 calibration and independent audit must pass")
    if calibration.get("protocol_version") != PROTOCOL_VERSION:
        raise ValueError("Calibration protocol version differs")
    if audit.get("calibration_sha256") != sha256_file(calibration_path):
        raise ValueError("Calibration audit references a different artifact")
    if audit.get("selected_rows") != 24 or audit.get("metric_rows") != 144:
        raise ValueError("Calibration audit row counts differ")
    selected = calibration.get("semantic_matching", {}).get("selected", [])
    selected_ids = [int(row["feature_id"]) for row in selected]
    if len(selected_ids) != 24 or len(set(selected_ids)) != 24:
        raise ValueError("Calibration does not contain 24 unique comparators")
    if Counter(row["experiment"] for row in selected) != {"A1": 18, "A2": 6}:
        raise ValueError("Calibration experiment counts differ")
    if Counter(
        row["semantic_family"] for row in selected if row["experiment"] == "A1"
    ) != {family: 6 for family in A1_FAMILIES}:
        raise ValueError("Calibration A1 family counts differ")
    if set(
        row["semantic_family"] for row in selected if row["experiment"] == "A2"
    ) != set(A2_SUBFAMILIES):
        raise ValueError("Calibration A2 subfamily coverage differs")
    accepted = calibration.get("lexicon_tokens", {}).get("accepted", {})
    expected_lexicons = {
        "deception_dishonesty",
        "refusal_safety",
        "hedging_uncertainty",
        "formality_politeness",
        "unrelated",
    }
    if set(accepted) != expected_lexicons:
        raise ValueError("Calibration lexicon family set differs")
    token_ids = []
    for family in sorted(expected_lexicons):
        rows = accepted[family]
        if len(rows) < 5:
            raise ValueError(f"Lexicon has fewer than five tokens: {family}")
        token_ids.extend(int(row["token_id"]) for row in rows)
    if len(token_ids) != len(set(token_ids)):
        raise ValueError("Lexicon token IDs overlap across families")
    return calibration, audit


def prompt_fold_rows(v1_plan_dir: Path) -> list[dict[str, Any]]:
    prompts = read_jsonl(v1_plan_dir / "prompt_plan.jsonl")
    if len(prompts) != 51:
        raise ValueError("Expected 51 v1 prompts")
    rng = random.Random(PROMPT_FOLD_SEED)
    order = list(range(len(prompts)))
    rng.shuffle(order)
    fold_by_index = {
        prompt_index: shuffled_index % PROMPT_FOLDS
        for shuffled_index, prompt_index in enumerate(order)
    }
    rows = [
        {
            "prompt_id": prompt["prompt_id"],
            "template_id": prompt["template_id"],
            "category": prompt["category"],
            "fold": fold_by_index[index],
        }
        for index, prompt in enumerate(prompts)
    ]
    counts = Counter(int(row["fold"]) for row in rows)
    if sorted(counts.values()) != [10, 10, 10, 10, 11]:
        raise AssertionError(f"Unexpected prompt-fold sizes: {counts}")
    return sorted(rows, key=lambda row: row["prompt_id"])


def selected_comparator_rows(calibration: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for row in calibration["semantic_matching"]["selected"]:
        rows.append(
            {
                "experiment": str(row["experiment"]),
                "semantic_family": str(row["semantic_family"]),
                "target_feature_id": int(row["target_feature_id"]),
                "feature_id": int(row["feature_id"]),
                "description": str(row["description"]),
                "cost": float(row["cost"]),
                "decoder_norm_ratio": float(row["decoder_norm_ratio"]),
                "max_abs_target_cosine": float(row["max_abs_target_cosine"]),
                "caliper_attempt": str(row["caliper_attempt"]),
            }
        )
    return sorted(
        rows,
        key=lambda row: (
            row["experiment"],
            row["semantic_family"],
            row["target_feature_id"],
        ),
    )


def build_final_trial_plan(
    v1_plan_dir: Path, calibration: dict[str, Any]
) -> list[dict[str, Any]]:
    v1_rows = read_jsonl(v1_plan_dir / "paired_plan.jsonl")
    prompts = read_jsonl(v1_plan_dir / "prompt_plan.jsonl")
    if len(v1_rows) != 1_581 or len(prompts) != 51:
        raise ValueError("Canonical v1 plan counts differ")
    fold_by_prompt = {
        row["prompt_id"]: int(row["fold"])
        for row in prompt_fold_rows(v1_plan_dir)
    }

    rows: list[dict[str, Any]] = []
    for source in v1_rows:
        copied = dict(source)
        source_trial_id = str(copied.pop("trial_id"))
        copied.pop("execution_order", None)
        rows.append(
            {
                **copied,
                "trial_id": stable_id((PROTOCOL_VERSION, "replay", source_trial_id)),
                "source_v1_trial_id": source_trial_id,
                "v2_arm": "v1_replay",
                "semantic_experiment": None,
                "semantic_family": None,
                "comparator_feature_id": None,
                "prompt_fold": fold_by_prompt[source["prompt_id"]],
            }
        )

    comparators = selected_comparator_rows(calibration)
    for prompt in prompts:
        for comparator in comparators:
            for sign_name, sign_value in (
                ("suppression", -1.0),
                ("amplification", 1.0),
            ):
                feature_id = int(comparator["feature_id"])
                target_id = int(comparator["target_feature_id"])
                condition_id = (
                    f"v2-{comparator['experiment'].lower()}-"
                    f"{comparator['semantic_family']}-{feature_id}-"
                    f"for-{target_id}-{sign_name}"
                )
                rows.append(
                    {
                        **prompt,
                        "condition_family": (
                            "hard_negative_single"
                            if comparator["experiment"] == "A1"
                            else "same_subfamily_single"
                        ),
                        "condition_id": condition_id,
                        "sign": sign_name,
                        "matched_target_feature_id": target_id,
                        "feature_ids": [feature_id],
                        "coefficients": [
                            round(sign_value * INDIVIDUAL_COEFFICIENT, 6)
                        ],
                        "random_seed": None,
                        "trial_id": stable_id(
                            (PROTOCOL_VERSION, prompt["prompt_id"], condition_id)
                        ),
                        "source_v1_trial_id": None,
                        "v2_arm": "semantic_comparator",
                        "semantic_experiment": comparator["experiment"],
                        "semantic_family": comparator["semantic_family"],
                        "comparator_feature_id": feature_id,
                        "prompt_fold": fold_by_prompt[prompt["prompt_id"]],
                    }
                )

    if len(rows) != 4_029:
        raise AssertionError(f"Expected 4,029 v2 rows, found {len(rows)}")
    if len({row["trial_id"] for row in rows}) != len(rows):
        raise AssertionError("V2 trial IDs are not unique")
    if sum(row["source_v1_trial_id"] is not None for row in rows) != 1_581:
        raise AssertionError("V1 replay count differs")
    order = list(range(len(rows)))
    random.Random(FINAL_PLAN_SEED).shuffle(order)
    for execution_order, row_index in enumerate(order):
        rows[row_index]["execution_order"] = execution_order
    return sorted(rows, key=lambda row: int(row["execution_order"]))


def random_projection(seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    matrix = rng.standard_normal((MODEL_WIDTH, PCA_COMPONENTS), dtype=np.float64)
    norms = np.linalg.norm(matrix, axis=0, keepdims=True)
    if np.any(norms <= 0) or not np.isfinite(norms).all():
        raise ValueError(f"Invalid random projection norm for seed {seed}")
    matrix = (matrix / norms).astype(np.float32)
    if not np.isfinite(matrix).all():
        raise ValueError(f"Nonfinite random projection for seed {seed}")
    return matrix


def array_sha256(array: np.ndarray) -> str:
    contiguous = np.ascontiguousarray(array)
    return sha256_bytes(contiguous.view(np.uint8).tobytes())


def reader_plan(projection_hashes: dict[int, str]) -> dict[str, Any]:
    feature_pairs = [
        {
            "pair_id": index,
            "target_feature_id": target_id,
            "control_feature_id": CONTROL_PANELS[1][target_id],
        }
        for index, target_id in enumerate(TARGET_FEATURE_IDS)
    ]
    readers = [
        {
            "reader_id": f"v1_{transport}_67",
            "family": "v1_lexicon_logits",
            "transport": transport,
            "dimensions": 67,
        }
        for transport in (
            "jacobian",
            "identity",
            "random_j_1",
            "random_j_2",
            "random_j_3",
            "random_j_4",
            "random_j_5",
        )
    ]
    readers.extend(
        [
            {
                "reader_id": "residual_pca_67",
                "family": "residual_pca",
                "dimensions": PCA_COMPONENTS,
                "pca_seed": PCA_SEED,
            },
            *[
                {
                    "reader_id": f"residual_random_projection_67_seed_{seed}",
                    "family": "residual_random_projection",
                    "dimensions": PCA_COMPONENTS,
                    "projection_seed": seed,
                    "projection_array_sha256": projection_hashes[seed],
                }
                for seed in RANDOM_PROJECTION_SEEDS
            ],
            {
                "reader_id": "residual_full_8192",
                "family": "residual_full",
                "dimensions": MODEL_WIDTH,
                "capacity_ceiling": True,
            },
        ]
    )
    return {
        "task": "target_single_vs_panel1_matched_single_isolated_state",
        "primary_layer": PRIMARY_LAYER,
        "primary_position": PRIMARY_POSITION,
        "conditional_inference": "six_fixed_feature_pairs",
        "feature_pairs": feature_pairs,
        "crossed_holdouts": {
            "prompt_folds": PROMPT_FOLDS,
            "models_per_reader": len(feature_pairs) * PROMPT_FOLDS,
            "training_excludes_test_feature_pair": True,
            "training_excludes_test_prompt_fold": True,
            "test_is_pair_by_fold_intersection": True,
        },
        "logistic_regression": {
            "C": LOGISTIC_C,
            "class_weight": "balanced",
            "solver": LOGISTIC_SOLVER,
            "max_iter": LOGISTIC_MAX_ITER,
            "tol": LOGISTIC_TOLERANCE,
            "seed": LOGISTIC_SEED,
            "standardization_inside_fold": True,
            "hyperparameter_search": False,
        },
        "readers": readers,
        "metrics": ["auroc", "auprc", "brier", "tpr_at_1pct_fpr"],
        "required_metric_tables": {
            "reader": 14,
            "reader_by_feature_pair": 84,
            "reader_by_feature_pair_and_prompt_fold": 420,
        },
        "material_threshold": {
            "macro_leave_one_pair_auroc": DETECTOR_MINIMUM_AUROC,
            "bootstrap_lower_bound": 0.5,
            "holm_adjusted_one_sided_p": 0.05,
            "holm_family": "all_14_frozen_reader_rungs",
        },
        "bootstrap": {
            "unit": "template_family",
            "replicates": BOOTSTRAP_REPLICATES,
            "draw_generation": (
                "numpy Generator.integers with replacement; template counts "
                "become sample weights"
            ),
            "auc_algorithm": "exact tie-aware weighted Mann-Whitney statistic",
        },
        "paired_permutation": {
            "unit": "target_control_labels_within_pair_template_sign_block",
            "replicates": BOOTSTRAP_REPLICATES,
            "reader_seed_base": 2_026_071_600,
            "statistic": "unweighted_macro_feature_pair_AUROC",
            "one_sided_p": "(1 + count(null_draw >= observed)) / (B + 1)",
            "multiplicity": "Holm across all 14 frozen reader rungs",
        },
    }


def semantic_analysis_plan() -> dict[str, Any]:
    return {
        "primary_layer": PRIMARY_LAYER,
        "primary_position": PRIMARY_POSITION,
        "transports": [
            "jacobian",
            "identity",
            "random_j_1",
            "random_j_2",
            "random_j_3",
            "random_j_4",
            "random_j_5",
        ],
        "lexicons": [
            "deception_dishonesty",
            "refusal_safety",
            "hedging_uncertainty",
            "formality_politeness",
        ],
        "reference_lexicon": "unrelated",
        "score": "mean_semantic_token_logit_minus_mean_unrelated_token_logit",
        "clean_scale": {
            "unit": "51_clean_template_family_prompts",
            "statistic": "sample_standard_deviation",
            "ddof": 1,
            "separate_by_transport_and_lexicon": True,
            "zero_or_nonfinite_rule": "fail_analysis",
        },
        "orientation": "coefficient_sign_times_steered_minus_clean_score",
        "template_balance": (
            "mean_features_and_signs_within_template_then_mean_51_templates"
        ),
        "bootstrap": {
            "unit": "template_family",
            "replicates": BOOTSTRAP_REPLICATES,
            "a1_transport_seed_base": 2_026_071_300,
            "a2_transport_seed_base": 2_026_071_400,
            "reader_seed_base": 2_026_071_500,
            "confidence_interval": [0.025, 0.975],
            "a2_equivalence_interval": [0.05, 0.95],
            "one_sided_positive_p": "(1 + count(draw <= 0)) / (B + 1)",
        },
        "multiplicity": {
            "a1_row_contrasts": "Holm across four intervention families",
            "a1_hard_negative_deception": "Holm across three hard-negative families",
            "a1_feature_rows": (
                "all 24 features by four lexicons are mandatory descriptive "
                "heterogeneity rows and cannot replace family endpoints"
            ),
            "a2_primary": "one aggregate contrast; six pair rows descriptive",
        },
        "minimum_effect_z": SEMANTIC_MINIMUM_Z,
    }


def residual_schema() -> dict[str, Any]:
    row_values = len(TRAJECTORY_LAYERS) * len(POSITIONS) * MODEL_WIDTH
    return {
        "format": "safetensors",
        "tensor_key": "residuals",
        "dtype": RESIDUAL_DTYPE,
        "row_shape": [len(TRAJECTORY_LAYERS), len(POSITIONS), MODEL_WIDTH],
        "layers": list(TRAJECTORY_LAYERS),
        "positions": list(POSITIONS),
        "complete_shard_rows": RESIDUAL_SHARD_ROWS,
        "complete_shard_shape": [
            RESIDUAL_SHARD_ROWS,
            len(TRAJECTORY_LAYERS),
            len(POSITIONS),
            MODEL_WIDTH,
        ],
        "row_bytes": row_values * 2,
        "expected_rows": 4_029,
        "expected_tensor_bytes": 4_029 * row_values * 2,
        "index": "residual_index.csv",
        "atomic_writes": True,
        "immutable_after_hash": True,
        "replay_max_absolute_tolerance": REPLAY_ABS_TOLERANCE,
    }


def final_protocol_snapshot(osf_project: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": "final_result_free_plan",
        "protocol_version": PROTOCOL_VERSION,
        "trial_counts": {
            "total": 4_029,
            "v1_replay": 1_581,
            "semantic_comparator": 2_448,
        },
        "execution_seed": FINAL_PLAN_SEED,
        "prompt_fold_seed": PROMPT_FOLD_SEED,
        "semantic_minimum_z": SEMANTIC_MINIMUM_Z,
        "detector_minimum_auroc": DETECTOR_MINIMUM_AUROC,
        "bootstrap_replicates": BOOTSTRAP_REPLICATES,
        "osf_project": osf_project,
        "registration_gate": (
            "Stage 1 requires a separate accepted OSF registration gate that "
            "binds this plan manifest and its public Git freeze commit."
        ),
        "claim_boundary": (
            "Outcomes support only conditional semantic-specificity and "
            "reader-capacity claims under the pinned model, SAE, lens, prompts, "
            "interventions, and access models."
        ),
    }

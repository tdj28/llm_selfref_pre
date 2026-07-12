#!/usr/bin/env python3
"""Run the frozen SAE/J-lens v2 semantic and reader-capacity analyses."""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
import warnings
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import numpy as np
from sklearn.decomposition import PCA
from sklearn.exceptions import ConvergenceWarning
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    average_precision_score,
    brier_score_loss,
    roc_auc_score,
    roc_curve,
)
from sklearn.preprocessing import StandardScaler


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from experiments.exp2_sae.sae_jlens_protocol import (  # noqa: E402
    TARGET_FEATURE_IDS,
)
from experiments.exp2_sae.figure_sae_jlens_v2 import (  # noqa: E402
    reader_ladder,
    reader_pair_heatmap,
    semantic_matrix,
    target_comparator,
)
from experiments.exp2_sae.sae_jlens_v2_final_protocol import (  # noqa: E402
    BOOTSTRAP_REPLICATES,
    DETECTOR_MINIMUM_AUROC,
    FINAL_PLAN_DIR,
    LOGISTIC_C,
    LOGISTIC_MAX_ITER,
    LOGISTIC_SEED,
    LOGISTIC_SOLVER,
    LOGISTIC_TOLERANCE,
    MODEL_WIDTH,
    PCA_COMPONENTS,
    PCA_SEED,
    PRIMARY_LAYER,
    PRIMARY_POSITION,
    RANDOM_PROJECTION_SEEDS,
    SEMANTIC_MINIMUM_Z,
    array_sha256,
)
from experiments.exp2_sae.sae_jlens_v2_protocol import (  # noqa: E402
    A1_FAMILIES,
    PROTOCOL_VERSION,
    TRAJECTORY_LAYERS,
    POSITIONS,
    read_jsonl,
    sha256_file,
    write_json,
)


DEFAULT_PLAN_DIR = REPO_ROOT / FINAL_PLAN_DIR
LEXICONS = (
    "deception_dishonesty",
    "refusal_safety",
    "hedging_uncertainty",
    "formality_politeness",
)
INTERVENTION_FAMILIES = ("deception_dishonesty", *A1_FAMILIES)
TRANSPORTS = (
    "jacobian",
    "identity",
    "random_j_1",
    "random_j_2",
    "random_j_3",
    "random_j_4",
    "random_j_5",
)


class AnalysisFailure(RuntimeError):
    """A frozen analysis gate or completeness requirement failed."""


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = list(rows[0]) if rows else []
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        if fields:
            writer.writeheader()
            writer.writerows(rows)


def iter_jsonl(directory: Path):
    for path in sorted(directory.glob("part-*.jsonl")):
        with path.open(encoding="utf-8") as handle:
            for line in handle:
                if line.strip():
                    yield json.loads(line)


def verify_inputs(plan_dir: Path, run_dir: Path) -> None:
    plan_manifest = json.loads(
        (plan_dir / "PLAN_MANIFEST.json").read_text(encoding="utf-8")
    )
    run = json.loads((run_dir / "RUN_COMPLETE.json").read_text(encoding="utf-8"))
    gate = json.loads(
        (run_dir / "replay_equivalence_gate.json").read_text(encoding="utf-8")
    )
    if plan_manifest.get("status") != "final_result_free_plan":
        raise AnalysisFailure("Final plan status differs")
    if run.get("status") != "complete" or gate.get("status") != "pass":
        raise AnalysisFailure("Complete run and replay gate are required")
    if run.get("plan_manifest_sha256") != sha256_file(
        plan_dir / "PLAN_MANIFEST.json"
    ):
        raise AnalysisFailure("Run binds a different final plan")
    if run.get("protocol_version") != PROTOCOL_VERSION:
        raise AnalysisFailure("Run protocol version differs")


def primary_rows(run_dir: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for trial in iter_jsonl(run_dir / "readouts"):
        for readout in trial["readouts"]:
            if (
                int(readout["layer"]) == PRIMARY_LAYER
                and readout["position"] == PRIMARY_POSITION
            ):
                rows.append(
                    {
                        **{
                            key: trial.get(key)
                            for key in (
                                "trial_id",
                                "source_v1_trial_id",
                                "prompt_id",
                                "template_id",
                                "category",
                                "condition_family",
                                "sign",
                                "matched_target_feature_id",
                                "semantic_experiment",
                                "semantic_family",
                                "comparator_feature_id",
                                "prompt_fold",
                            )
                        },
                        "transport": readout["transport"],
                        "group_logits": readout["group_logits"],
                        "v1_token_logits": readout.get("v1_token_logits"),
                    }
                )
    expected = 4_029 * len(TRANSPORTS)
    if len(rows) != expected:
        raise AnalysisFailure(f"Expected {expected} primary rows, found {len(rows)}")
    return rows


def semantic_score(row: dict[str, Any], lexicon: str) -> float:
    groups = row["group_logits"]
    return float(groups[f"v2_{lexicon}"]) - float(groups["v2_unrelated"])


def clean_scales(
    rows: list[dict[str, Any]],
) -> tuple[dict[tuple[str, str, str], float], dict[tuple[str, str], float]]:
    clean_rows = [row for row in rows if row["condition_family"] == "zero"]
    if len(clean_rows) != 51 * len(TRANSPORTS):
        raise AnalysisFailure("Clean primary row count differs")
    scores: dict[tuple[str, str, str], float] = {}
    scales: dict[tuple[str, str], float] = {}
    for row in clean_rows:
        for lexicon in LEXICONS:
            scores[(row["prompt_id"], row["transport"], lexicon)] = semantic_score(
                row, lexicon
            )
    for transport in TRANSPORTS:
        for lexicon in LEXICONS:
            values = [
                value
                for (prompt_id, row_transport, row_lexicon), value in scores.items()
                if row_transport == transport and row_lexicon == lexicon
            ]
            scale = float(np.std(values, ddof=1))
            if len(values) != 51 or not math.isfinite(scale) or scale <= 0:
                raise AnalysisFailure(f"Invalid clean scale: {transport}/{lexicon}")
            scales[(transport, lexicon)] = scale
    return scores, scales


def oriented_z(
    row: dict[str, Any],
    lexicon: str,
    clean: dict[tuple[str, str, str], float],
    scales: dict[tuple[str, str], float],
) -> float:
    sign = 1.0 if row["sign"] == "amplification" else -1.0
    key = (row["prompt_id"], row["transport"], lexicon)
    return sign * (semantic_score(row, lexicon) - clean[key]) / scales[
        (row["transport"], lexicon)
    ]


def quantiles(draws: np.ndarray, levels: tuple[float, float]) -> tuple[float, float]:
    return tuple(float(value) for value in np.quantile(draws, levels))


def holm_adjust(pvalues: list[float]) -> list[float]:
    order = np.argsort(pvalues)
    adjusted = [0.0] * len(pvalues)
    running = 0.0
    total = len(pvalues)
    for rank, index in enumerate(order):
        value = min(1.0, (total - rank) * pvalues[int(index)])
        running = max(running, value)
        adjusted[int(index)] = running
    return adjusted


def semantic_a1(
    rows: list[dict[str, Any]], replicates: int
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    clean, scales = clean_scales(rows)
    eligible = [
        row
        for row in rows
        if row["condition_family"] == "target_single"
        or row.get("semantic_experiment") == "A1"
    ]
    values: dict[tuple[str, str, str, str], list[float]] = defaultdict(list)
    for row in eligible:
        family = (
            "deception_dishonesty"
            if row["condition_family"] == "target_single"
            else row["semantic_family"]
        )
        for lexicon in LEXICONS:
            values[(row["transport"], family, lexicon, row["template_id"])].append(
                oriented_z(row, lexicon, clean, scales)
            )

    templates = sorted({row["template_id"] for row in eligible})
    if len(templates) != 51:
        raise AnalysisFailure("A1 template count differs")
    matrix_rows: list[dict[str, Any]] = []
    contrast_rows: list[dict[str, Any]] = []
    verdicts: dict[str, Any] = {}
    for transport_index, transport in enumerate(TRANSPORTS):
        matrix = np.empty((len(templates), 4, 4), dtype=np.float64)
        for template_index, template in enumerate(templates):
            for family_index, family in enumerate(INTERVENTION_FAMILIES):
                for lexicon_index, lexicon in enumerate(LEXICONS):
                    cell = values[(transport, family, lexicon, template)]
                    if not cell:
                        raise AnalysisFailure(
                            f"Missing A1 cell: {transport}/{family}/{lexicon}/{template}"
                        )
                    matrix[template_index, family_index, lexicon_index] = np.mean(cell)
        rng = np.random.default_rng(2_026_071_300 + transport_index)
        indices = rng.integers(0, len(templates), size=(replicates, len(templates)))
        cell_draws = matrix[indices].mean(axis=1)
        point = matrix.mean(axis=0)
        row_contrast = np.diagonal(point) - (
            point.sum(axis=1) - np.diagonal(point)
        ) / 3.0
        row_draws = np.diagonal(cell_draws, axis1=1, axis2=2) - (
            cell_draws.sum(axis=2) - np.diagonal(cell_draws, axis1=1, axis2=2)
        ) / 3.0
        global_point = float(row_contrast.mean())
        global_draws = row_draws.mean(axis=1)
        raw_p = [float((1 + np.sum(row_draws[:, index] <= 0)) / (replicates + 1)) for index in range(4)]
        adjusted = holm_adjust(raw_p)

        for family_index, family in enumerate(INTERVENTION_FAMILIES):
            for lexicon_index, lexicon in enumerate(LEXICONS):
                low, high = quantiles(
                    cell_draws[:, family_index, lexicon_index], (0.025, 0.975)
                )
                matrix_rows.append(
                    {
                        "transport": transport,
                        "intervention_family": family,
                        "lexicon": lexicon,
                        "n_templates": len(templates),
                        "mean_oriented_z": float(point[family_index, lexicon_index]),
                        "ci_low": low,
                        "ci_high": high,
                    }
                )
            low, high = quantiles(row_draws[:, family_index], (0.025, 0.975))
            contrast_rows.append(
                {
                    "transport": transport,
                    "contrast": "row_diagonal_minus_off_diagonal",
                    "intervention_family": family,
                    "mean_oriented_z": float(row_contrast[family_index]),
                    "ci_low": low,
                    "ci_high": high,
                    "bootstrap_one_sided_p": raw_p[family_index],
                    "holm_adjusted_p": adjusted[family_index],
                }
            )
        global_low, global_high = quantiles(global_draws, (0.025, 0.975))
        contrast_rows.append(
            {
                "transport": transport,
                "contrast": "global_diagonal",
                "intervention_family": "all_four_fixed_families",
                "mean_oriented_z": global_point,
                "ci_low": global_low,
                "ci_high": global_high,
                "bootstrap_one_sided_p": float(
                    (1 + np.sum(global_draws <= 0)) / (replicates + 1)
                ),
                "holm_adjusted_p": None,
            }
        )
        diagonal_largest = [
            int(np.argmax(point[index])) == index for index in range(4)
        ]
        significant_rows = sum(
            value > 0 and pvalue < 0.05
            for value, pvalue in zip(row_contrast, adjusted)
        )
        verdicts[transport] = {
            "global_point": global_point,
            "global_ci": [global_low, global_high],
            "diagonal_largest_by_row": diagonal_largest,
            "holm_positive_rows": significant_rows,
            "family_specificity_supported": bool(
                global_point >= SEMANTIC_MINIMUM_Z
                and global_low > 0
                and all(diagonal_largest)
                and significant_rows >= 3
            ),
        }
    return matrix_rows, contrast_rows, verdicts


def semantic_a2(
    rows: list[dict[str, Any]], replicates: int
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    clean, scales = clean_scales(rows)
    target = {
        (
            row["prompt_id"],
            row["sign"],
            row["transport"],
            int(row["matched_target_feature_id"]),
        ): row
        for row in rows
        if row["condition_family"] == "target_single"
    }
    comparator = [row for row in rows if row.get("semantic_experiment") == "A2"]
    paired: list[dict[str, Any]] = []
    for row in comparator:
        target_id = int(row["matched_target_feature_id"])
        key = (row["prompt_id"], row["sign"], row["transport"], target_id)
        target_row = target.get(key)
        if target_row is None:
            raise AnalysisFailure(f"Missing A2 target match: {key}")
        target_z = oriented_z(target_row, LEXICONS[0], clean, scales)
        comparator_z = oriented_z(row, LEXICONS[0], clean, scales)
        paired.append(
            {
                "transport": row["transport"],
                "template_id": row["template_id"],
                "target_feature_id": target_id,
                "comparator_feature_id": int(row["comparator_feature_id"]),
                "semantic_family": row["semantic_family"],
                "sign": row["sign"],
                "target_z": target_z,
                "comparator_z": comparator_z,
                "target_minus_comparator": target_z - comparator_z,
            }
        )
    if len(paired) != 6 * 2 * 51 * len(TRANSPORTS):
        raise AnalysisFailure("A2 paired row count differs")

    pair_rows: list[dict[str, Any]] = []
    summary_rows: list[dict[str, Any]] = []
    verdicts: dict[str, Any] = {}
    for transport_index, transport in enumerate(TRANSPORTS):
        transport_rows = [row for row in paired if row["transport"] == transport]
        templates = sorted({row["template_id"] for row in transport_rows})
        targets = list(TARGET_FEATURE_IDS)
        matrix = np.empty((len(templates), len(targets)), dtype=np.float64)
        for template_index, template in enumerate(templates):
            for target_index, target_id in enumerate(targets):
                values = [
                    row["target_minus_comparator"]
                    for row in transport_rows
                    if row["template_id"] == template
                    and row["target_feature_id"] == target_id
                ]
                if len(values) != 2:
                    raise AnalysisFailure(
                        f"A2 block differs: {transport}/{template}/{target_id}"
                    )
                matrix[template_index, target_index] = np.mean(values)
        rng = np.random.default_rng(2_026_071_400 + transport_index)
        indices = rng.integers(0, len(templates), size=(replicates, len(templates)))
        draws_by_pair = matrix[indices].mean(axis=1)
        aggregate_draws = draws_by_pair.mean(axis=1)
        aggregate_point = float(matrix.mean())
        ci_low, ci_high = quantiles(aggregate_draws, (0.025, 0.975))
        eq_low, eq_high = quantiles(aggregate_draws, (0.05, 0.95))
        summary_rows.append(
            {
                "transport": transport,
                "n_templates": len(templates),
                "n_fixed_pairs": len(targets),
                "mean_target_minus_comparator_z": aggregate_point,
                "ci95_low": ci_low,
                "ci95_high": ci_high,
                "ci90_low": eq_low,
                "ci90_high": eq_high,
                "selected_id_advantage": bool(
                    aggregate_point >= SEMANTIC_MINIMUM_Z and ci_low > 0
                ),
                "practical_comparability": bool(
                    eq_low >= -SEMANTIC_MINIMUM_Z
                    and eq_high <= SEMANTIC_MINIMUM_Z
                ),
            }
        )
        for target_index, target_id in enumerate(targets):
            row0 = next(
                row for row in transport_rows if row["target_feature_id"] == target_id
            )
            low, high = quantiles(draws_by_pair[:, target_index], (0.025, 0.975))
            pair_rows.append(
                {
                    "transport": transport,
                    "target_feature_id": target_id,
                    "comparator_feature_id": row0["comparator_feature_id"],
                    "semantic_family": row0["semantic_family"],
                    "mean_target_minus_comparator_z": float(matrix[:, target_index].mean()),
                    "ci_low": low,
                    "ci_high": high,
                }
            )
        verdicts[transport] = {
            "point": aggregate_point,
            "ci95": [ci_low, ci_high],
            "ci90": [eq_low, eq_high],
            "selected_id_advantage": summary_rows[-1]["selected_id_advantage"],
            "practical_comparability": summary_rows[-1]["practical_comparability"],
            "verdict": (
                "selected_id_advantage"
                if summary_rows[-1]["selected_id_advantage"]
                else "practical_comparability"
                if summary_rows[-1]["practical_comparability"]
                else "inconclusive"
            ),
        }
    return pair_rows, summary_rows, verdicts


def reader_samples(
    plan_dir: Path, run_dir: Path, primary: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]], np.ndarray, dict[str, np.ndarray]]:
    sample_trials = {
        row["trial_id"]: row
        for row in primary
        if row["transport"] == "jacobian"
        and row["condition_family"] in {"target_single", "matched_single"}
    }
    if len(sample_trials) != 1_224:
        raise AnalysisFailure(f"Reader sample count differs: {len(sample_trials)}")
    order = sorted(sample_trials)
    metadata = [
        {
            "trial_id": trial_id,
            "template_id": sample_trials[trial_id]["template_id"],
            "prompt_fold": int(sample_trials[trial_id]["prompt_fold"]),
            "feature_pair": int(sample_trials[trial_id]["matched_target_feature_id"]),
            "label": int(sample_trials[trial_id]["condition_family"] == "target_single"),
            "sign": sample_trials[trial_id]["sign"],
        }
        for trial_id in order
    ]
    position = {trial_id: index for index, trial_id in enumerate(order)}
    residuals = np.empty((len(order), MODEL_WIDTH), dtype=np.float32)
    seen = set()
    layer_index = list(TRAJECTORY_LAYERS).index(PRIMARY_LAYER)
    position_index = list(POSITIONS).index(PRIMARY_POSITION)
    from safetensors.torch import load_file

    with (run_dir / "residual_index.csv").open(encoding="utf-8", newline="") as handle:
        index_rows = list(csv.DictReader(handle))
    by_shard: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in index_rows:
        if row["trial_id"] in position:
            by_shard[row["shard"]].append(row)
    for shard, rows in by_shard.items():
        tensor = load_file(str(run_dir / "residuals" / shard), device="cpu")[
            "residuals"
        ]
        for row in rows:
            trial_id = row["trial_id"]
            residuals[position[trial_id]] = (
                tensor[int(row["row_offset"]), layer_index, position_index]
                .float()
                .numpy()
            )
            seen.add(trial_id)
    if seen != set(order) or not np.isfinite(residuals).all():
        raise AnalysisFailure("Reader residual extraction is incomplete or nonfinite")

    v1_features: dict[str, np.ndarray] = {}
    lookup = {(row["trial_id"], row["transport"]): row for row in primary}
    for transport in TRANSPORTS:
        matrix = np.asarray(
            [lookup[(trial_id, transport)]["v1_token_logits"] for trial_id in order],
            dtype=np.float64,
        )
        if matrix.shape != (1_224, 67) or not np.isfinite(matrix).all():
            raise AnalysisFailure(f"V1 reader matrix differs: {transport}")
        v1_features[transport] = matrix
    return metadata, residuals, v1_features


def fit_predict_reader(
    reader: dict[str, Any],
    residuals: np.ndarray,
    v1_features: dict[str, np.ndarray],
    train: np.ndarray,
    test: np.ndarray,
    labels: np.ndarray,
    plan_dir: Path,
) -> np.ndarray:
    family = reader["family"]
    if family == "v1_lexicon_logits":
        train_x = v1_features[reader["transport"]][train]
        test_x = v1_features[reader["transport"]][test]
    elif family == "residual_pca":
        pca = PCA(
            n_components=PCA_COMPONENTS,
            svd_solver="randomized",
            random_state=PCA_SEED,
        )
        train_x = pca.fit_transform(residuals[train])
        test_x = pca.transform(residuals[test])
    elif family == "residual_random_projection":
        seed = int(reader["projection_seed"])
        projection = np.load(
            plan_dir / "random_projections" / f"projection_seed_{seed}.npy",
            allow_pickle=False,
        )
        if array_sha256(projection) != reader["projection_array_sha256"]:
            raise AnalysisFailure(f"Random projection hash differs: {seed}")
        train_x = residuals[train] @ projection
        test_x = residuals[test] @ projection
    elif family == "residual_full":
        train_x = residuals[train]
        test_x = residuals[test]
    else:
        raise AnalysisFailure(f"Unknown reader family: {family}")

    scaler = StandardScaler()
    train_scaled = scaler.fit_transform(train_x)
    test_scaled = scaler.transform(test_x)
    classifier = LogisticRegression(
        C=LOGISTIC_C,
        class_weight="balanced",
        solver=LOGISTIC_SOLVER,
        max_iter=LOGISTIC_MAX_ITER,
        tol=LOGISTIC_TOLERANCE,
        random_state=LOGISTIC_SEED,
    )
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always", ConvergenceWarning)
        classifier.fit(train_scaled, labels[train])
    if any(issubclass(item.category, ConvergenceWarning) for item in caught):
        raise AnalysisFailure(f"Reader failed to converge: {reader['reader_id']}")
    probabilities = classifier.predict_proba(test_scaled)[:, 1]
    if not np.isfinite(probabilities).all():
        raise AnalysisFailure(f"Reader returned nonfinite probabilities: {reader['reader_id']}")
    return probabilities


def tpr_at_fpr(labels: np.ndarray, scores: np.ndarray, maximum_fpr: float = 0.01) -> float:
    fpr, tpr, _ = roc_curve(labels, scores)
    eligible = tpr[fpr <= maximum_fpr + 1e-12]
    return float(eligible.max()) if len(eligible) else 0.0


def metrics(labels: np.ndarray, scores: np.ndarray) -> dict[str, float]:
    return {
        "auroc": float(roc_auc_score(labels, scores)),
        "auprc": float(average_precision_score(labels, scores)),
        "brier": float(brier_score_loss(labels, scores)),
        "tpr_at_1pct_fpr": tpr_at_fpr(labels, scores),
    }


def reader_bootstrap_macro_auc(
    rows: list[dict[str, Any]], replicates: int, seed: int
) -> tuple[float, float]:
    templates = sorted({row["template_id"] for row in rows})
    pairs = sorted({int(row["feature_pair"]) for row in rows})
    labels = np.asarray([int(row["label"]) for row in rows])
    scores = np.asarray([float(row["probability"]) for row in rows])
    template_values = np.asarray([row["template_id"] for row in rows], dtype=object)
    pair_values = np.asarray([int(row["feature_pair"]) for row in rows])
    rng = np.random.default_rng(seed)
    draws = np.empty(replicates, dtype=np.float64)
    for draw_index in range(replicates):
        sampled = rng.choice(templates, size=len(templates), replace=True)
        counts = Counter(sampled.tolist())
        weights = np.asarray([counts.get(value, 0) for value in template_values])
        pair_aucs = []
        for pair in pairs:
            mask = pair_values == pair
            pair_aucs.append(
                roc_auc_score(labels[mask], scores[mask], sample_weight=weights[mask])
            )
        draws[draw_index] = np.mean(pair_aucs)
    return quantiles(draws, (0.025, 0.975))


def reader_analysis(
    plan_dir: Path,
    run_dir: Path,
    primary: list[dict[str, Any]],
    replicates: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    metadata, residuals, v1_features = reader_samples(plan_dir, run_dir, primary)
    labels = np.asarray([row["label"] for row in metadata], dtype=np.int64)
    folds = np.asarray([row["prompt_fold"] for row in metadata], dtype=np.int64)
    pairs = np.asarray([row["feature_pair"] for row in metadata], dtype=np.int64)
    reader_plan = json.loads((plan_dir / "reader_plan.json").read_text(encoding="utf-8"))
    prediction_rows: list[dict[str, Any]] = []
    for reader in reader_plan["readers"]:
        predictions = np.full(len(metadata), np.nan, dtype=np.float64)
        for held_pair in TARGET_FEATURE_IDS:
            for held_fold in range(5):
                train = np.flatnonzero((pairs != held_pair) & (folds != held_fold))
                test = np.flatnonzero((pairs == held_pair) & (folds == held_fold))
                if not len(train) or not len(test):
                    raise AnalysisFailure("Crossed holdout produced an empty split")
                predictions[test] = fit_predict_reader(
                    reader,
                    residuals,
                    v1_features,
                    train,
                    test,
                    labels,
                    plan_dir,
                )
        if not np.isfinite(predictions).all():
            raise AnalysisFailure(f"Reader predictions are incomplete: {reader['reader_id']}")
        prediction_rows.extend(
            {
                **row,
                "reader_id": reader["reader_id"],
                "reader_family": reader["family"],
                "probability": float(predictions[index]),
            }
            for index, row in enumerate(metadata)
        )

    metric_rows: list[dict[str, Any]] = []
    pair_rows: list[dict[str, Any]] = []
    verdicts: dict[str, Any] = {}
    for reader_index, reader in enumerate(reader_plan["readers"]):
        rows = [row for row in prediction_rows if row["reader_id"] == reader["reader_id"]]
        row_labels = np.asarray([row["label"] for row in rows], dtype=np.int64)
        row_scores = np.asarray([row["probability"] for row in rows], dtype=np.float64)
        overall = metrics(row_labels, row_scores)
        pair_aucs = []
        for pair in TARGET_FEATURE_IDS:
            pair_mask = np.asarray([row["feature_pair"] == pair for row in rows])
            pair_metrics = metrics(row_labels[pair_mask], row_scores[pair_mask])
            pair_aucs.append(pair_metrics["auroc"])
            pair_rows.append(
                {
                    "reader_id": reader["reader_id"],
                    "feature_pair": pair,
                    "n": int(pair_mask.sum()),
                    **pair_metrics,
                }
            )
        macro = float(np.mean(pair_aucs))
        low, high = reader_bootstrap_macro_auc(
            rows, replicates, 2_026_071_500 + reader_index
        )
        material = macro >= DETECTOR_MINIMUM_AUROC and low > 0.5
        metric_rows.append(
            {
                "reader_id": reader["reader_id"],
                "reader_family": reader["family"],
                "n": len(rows),
                **overall,
                "macro_leave_one_pair_auroc": macro,
                "macro_bootstrap_ci_low": low,
                "macro_bootstrap_ci_high": high,
                "material_detection": material,
            }
        )
        verdicts[reader["reader_id"]] = {
            "pooled_auroc": overall["auroc"],
            "macro_leave_one_pair_auroc": macro,
            "macro_ci": [low, high],
            "material_detection": material,
            "classification": (
                "material_detection"
                if material
                else "above_chance_below_material_threshold"
                if low > 0.5
                else "not_detected_under_this_reader"
            ),
        }
    return prediction_rows, metric_rows, pair_rows, verdicts


def analyze(plan_dir: Path, run_dir: Path, outdir: Path, replicates: int) -> None:
    if replicates != BOOTSTRAP_REPLICATES:
        raise AnalysisFailure(
            f"Confirmatory analysis requires {BOOTSTRAP_REPLICATES} bootstrap draws"
        )
    verify_inputs(plan_dir, run_dir)
    outdir.mkdir(parents=True, exist_ok=True)
    primary = primary_rows(run_dir)
    a1_matrix, a1_contrasts, a1_verdicts = semantic_a1(primary, replicates)
    a2_pairs, a2_summary, a2_verdicts = semantic_a2(primary, replicates)
    predictions, reader_metrics, reader_pairs, reader_verdicts = reader_analysis(
        plan_dir, run_dir, primary, replicates
    )
    write_csv(outdir / "semantic_a1_matrix.csv", a1_matrix)
    write_csv(outdir / "semantic_a1_contrasts.csv", a1_contrasts)
    write_csv(outdir / "semantic_a2_pairs.csv", a2_pairs)
    write_csv(outdir / "semantic_a2_summary.csv", a2_summary)
    write_csv(outdir / "reader_predictions.csv", predictions)
    write_csv(outdir / "reader_metrics.csv", reader_metrics)
    write_csv(outdir / "reader_pair_metrics.csv", reader_pairs)
    write_json(
        outdir / "analysis_summary.json",
        {
            "status": "complete",
            "protocol_version": PROTOCOL_VERSION,
            "plan_manifest_sha256": sha256_file(plan_dir / "PLAN_MANIFEST.json"),
            "run_result_manifest_sha256": sha256_file(run_dir / "RESULT_MANIFEST.json"),
            "bootstrap_replicates": replicates,
            "a1": a1_verdicts,
            "a2": a2_verdicts,
            "reader_capacity": reader_verdicts,
            "claim_boundary": (
                "These are conditional semantic-specificity and linear-reader "
                "capacity results, not evidence of hidden belief, provenance, "
                "intent, deception, or consciousness."
            ),
        },
    )
    figures = outdir.parent / "figures"
    semantic_matrix(outdir, figures)
    target_comparator(outdir, figures)
    reader_ladder(outdir, figures)
    reader_pair_heatmap(outdir, figures)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan-dir", type=Path, default=DEFAULT_PLAN_DIR)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--outdir", type=Path, required=True)
    parser.add_argument("--bootstrap", type=int, default=BOOTSTRAP_REPLICATES)
    args = parser.parse_args()
    analyze(
        args.plan_dir.resolve(),
        args.run_dir.resolve(),
        args.outdir.resolve(),
        args.bootstrap,
    )


if __name__ == "__main__":
    main()

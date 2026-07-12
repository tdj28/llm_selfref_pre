#!/usr/bin/env python3
"""Independently audit SAE/J-lens v2 raw structure and promoted estimates."""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

import numpy as np
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from experiments.exp2_sae.sae_jlens_v2_final_protocol import (  # noqa: E402
    FINAL_PLAN_DIR,
    MODEL_WIDTH,
    PRIMARY_LAYER,
    PRIMARY_POSITION,
)
from experiments.exp2_sae.sae_jlens_v2_protocol import (  # noqa: E402
    A1_FAMILIES,
    POSITIONS,
    PROTOCOL_VERSION,
    TRAJECTORY_LAYERS,
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


def csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def iter_jsonl(directory: Path):
    for path in sorted(directory.glob("part-*.jsonl")):
        with path.open(encoding="utf-8") as handle:
            for line in handle:
                if line.strip():
                    yield json.loads(line)


def primary_rows(run_dir: Path) -> list[dict[str, Any]]:
    rows = []
    for trial in iter_jsonl(run_dir / "readouts"):
        for readout in trial["readouts"]:
            if (
                int(readout["layer"]) == PRIMARY_LAYER
                and readout["position"] == PRIMARY_POSITION
            ):
                rows.append(
                    {
                        "prompt_id": trial["prompt_id"],
                        "template_id": trial["template_id"],
                        "condition_family": trial["condition_family"],
                        "sign": trial["sign"],
                        "matched_target_feature_id": trial.get(
                            "matched_target_feature_id"
                        ),
                        "semantic_experiment": trial.get("semantic_experiment"),
                        "semantic_family": trial.get("semantic_family"),
                        "transport": readout["transport"],
                        "groups": readout["group_logits"],
                    }
                )
    return rows


def score(row: dict[str, Any], lexicon: str) -> float:
    return float(row["groups"][f"v2_{lexicon}"]) - float(
        row["groups"]["v2_unrelated"]
    )


def clean_reference(
    rows: list[dict[str, Any]],
) -> tuple[dict[tuple[str, str, str], float], dict[tuple[str, str], float]]:
    clean = {}
    for row in rows:
        if row["condition_family"] != "zero":
            continue
        for lexicon in LEXICONS:
            clean[(row["prompt_id"], row["transport"], lexicon)] = score(
                row, lexicon
            )
    scales = {}
    for transport in TRANSPORTS:
        for lexicon in LEXICONS:
            values = [
                value
                for (prompt, row_transport, row_lexicon), value in clean.items()
                if row_transport == transport and row_lexicon == lexicon
            ]
            scales[(transport, lexicon)] = float(np.std(values, ddof=1))
    return clean, scales


def zvalue(
    row: dict[str, Any],
    lexicon: str,
    clean: dict[tuple[str, str, str], float],
    scales: dict[tuple[str, str], float],
) -> float:
    orientation = 1.0 if row["sign"] == "amplification" else -1.0
    key = (row["prompt_id"], row["transport"], lexicon)
    return orientation * (score(row, lexicon) - clean[key]) / scales[
        (row["transport"], lexicon)
    ]


def independent_a1_points(rows: list[dict[str, Any]]) -> dict[tuple[str, str, str], float]:
    clean, scales = clean_reference(rows)
    by_template: dict[tuple[str, str, str, str], list[float]] = defaultdict(list)
    for row in rows:
        if row["condition_family"] == "target_single":
            family = "deception_dishonesty"
        elif row.get("semantic_experiment") == "A1":
            family = row["semantic_family"]
        else:
            continue
        for lexicon in LEXICONS:
            by_template[
                (row["transport"], family, lexicon, row["template_id"])
            ].append(zvalue(row, lexicon, clean, scales))
    points = {}
    for transport in TRANSPORTS:
        for family in INTERVENTION_FAMILIES:
            for lexicon in LEXICONS:
                template_means = [
                    np.mean(values)
                    for (row_transport, row_family, row_lexicon, template), values in by_template.items()
                    if row_transport == transport
                    and row_family == family
                    and row_lexicon == lexicon
                ]
                if len(template_means) != 51:
                    raise ValueError(f"Independent A1 cell is incomplete: {transport}/{family}/{lexicon}")
                points[(transport, family, lexicon)] = float(np.mean(template_means))
    return points


def independent_a2_points(rows: list[dict[str, Any]]) -> dict[str, float]:
    clean, scales = clean_reference(rows)
    targets = {
        (row["prompt_id"], row["sign"], row["transport"], int(row["matched_target_feature_id"])): row
        for row in rows
        if row["condition_family"] == "target_single"
    }
    by_template: dict[tuple[str, str, int], list[float]] = defaultdict(list)
    for row in rows:
        if row.get("semantic_experiment") != "A2":
            continue
        target_id = int(row["matched_target_feature_id"])
        target = targets[(row["prompt_id"], row["sign"], row["transport"], target_id)]
        value = zvalue(target, LEXICONS[0], clean, scales) - zvalue(
            row, LEXICONS[0], clean, scales
        )
        by_template[(row["transport"], row["template_id"], target_id)].append(value)
    points = {}
    for transport in TRANSPORTS:
        blocks = [
            float(np.mean(values))
            for (row_transport, template, target_id), values in by_template.items()
            if row_transport == transport
        ]
        if len(blocks) != 51 * 6 or any(
            len(values) != 2
            for (row_transport, template, target_id), values in by_template.items()
            if row_transport == transport
        ):
            raise ValueError(f"Independent A2 blocks are incomplete: {transport}")
        points[transport] = float(np.mean(blocks))
    return points


def audit(plan_dir: Path, run_dir: Path) -> dict[str, Any]:
    errors: list[str] = []
    run = json.loads((run_dir / "RUN_COMPLETE.json").read_text(encoding="utf-8"))
    result_manifest = json.loads(
        (run_dir / "RESULT_MANIFEST.json").read_text(encoding="utf-8")
    )
    gate = json.loads(
        (run_dir / "replay_equivalence_gate.json").read_text(encoding="utf-8")
    )
    if run.get("status") != "complete" or gate.get("status") != "pass":
        errors.append("run/replay gate is not complete and passing")
    if run.get("protocol_version") != PROTOCOL_VERSION:
        errors.append("run protocol version differs")
    if run.get("plan_manifest_sha256") != sha256_file(
        plan_dir / "PLAN_MANIFEST.json"
    ):
        errors.append("run plan binding differs")
    if result_manifest.get("status") != "complete":
        errors.append("raw result manifest is not complete")
    for record in result_manifest.get("files", []):
        path = run_dir / record["path"]
        if not path.is_file():
            errors.append(f"raw result-manifest file is missing: {record['path']}")
        elif path.stat().st_size != int(record["bytes"]):
            errors.append(f"raw result-manifest bytes differ: {record['path']}")
        elif sha256_file(path) != record["sha256"]:
            errors.append(f"raw result-manifest hash differs: {record['path']}")

    index = csv_rows(run_dir / "residual_index.csv")
    if len(index) != 4_029 or len({row["trial_id"] for row in index}) != 4_029:
        errors.append("residual index count/uniqueness differs")
    expected_shape_tail = (len(TRAJECTORY_LAYERS), len(POSITIONS), MODEL_WIDTH)
    shard_rows = 0
    from safetensors import safe_open

    shard_names = sorted({row["shard"] for row in index})
    expected_shards = [f"part-{index:03d}.safetensors" for index in range(16)]
    if shard_names != expected_shards:
        errors.append(f"residual shard identities differ: {shard_names}")
    for shard_index, shard_name in enumerate(shard_names):
        path = run_dir / "residuals" / shard_name
        with safe_open(path, framework="pt", device="cpu") as handle:
            tensor = handle.get_tensor("residuals")
        if tuple(tensor.shape[1:]) != expected_shape_tail:
            errors.append(f"residual shard shape differs: {shard_name}")
        if str(tensor.dtype) != "torch.bfloat16":
            errors.append(f"residual shard dtype differs: {shard_name}")
        expected_rows = 256 if shard_index < 15 else 189
        if int(tensor.shape[0]) != expected_rows:
            errors.append(f"residual shard row count differs: {shard_name}")
        shard_index_rows = sorted(
            (row for row in index if row["shard"] == shard_name),
            key=lambda row: int(row["row_offset"]),
        )
        if [int(row["row_offset"]) for row in shard_index_rows] != list(
            range(int(tensor.shape[0]))
        ):
            errors.append(f"residual row offsets differ: {shard_name}")
        readout_path = run_dir / "readouts" / f"{Path(shard_name).stem}.jsonl"
        with readout_path.open(encoding="utf-8") as handle:
            readout_rows = [json.loads(line) for line in handle if line.strip()]
        if [row["trial_id"] for row in shard_index_rows] != [
            row["trial_id"] for row in readout_rows
        ]:
            errors.append(f"residual/readout trial mapping differs: {shard_name}")
        shard_rows += int(tensor.shape[0])
    if shard_rows != 4_029:
        errors.append(f"residual shard row total differs: {shard_rows}")

    raw_rows = list(iter_jsonl(run_dir / "readouts"))
    if len(raw_rows) != 4_029 or len({row["trial_id"] for row in raw_rows}) != 4_029:
        errors.append("readout count/uniqueness differs")
    replay_rows = [row for row in raw_rows if row.get("source_v1_trial_id") is not None]
    semantic_rows = [row for row in raw_rows if row.get("source_v1_trial_id") is None]
    if len(replay_rows) != 1_581 or len(semantic_rows) != 2_448:
        errors.append("readout replay/semantic split differs")
    lexicon = json.loads(
        (run_dir / "lexicon_tokens.json").read_text(encoding="utf-8")
    )
    expected_groups = set(lexicon.get("combined", {}).get("accepted", {}))
    expected_grid = {
        (layer, position, transport)
        for layer in TRAJECTORY_LAYERS
        for transport in TRANSPORTS
        for position in POSITIONS
    }
    for row in raw_rows:
        readouts = row.get("readouts", [])
        if len(readouts) != 147 or {
            (int(value["layer"]), value["position"], value["transport"])
            for value in readouts
        } != expected_grid:
            errors.append(f"readout transport grid differs: {row.get('trial_id')}")
            break
        expects_tokens = row.get("source_v1_trial_id") is not None
        intervention = row.get("intervention", {})
        is_zero = row.get("condition_family") == "zero"
        if is_zero != bool(intervention.get("zero_is_true_noop")):
            errors.append(f"intervention no-op marker differs: {row.get('trial_id')}")
            break
        vector_norm = float(intervention.get("vector_norm", math.nan))
        vector_hash = intervention.get("vector_sha256_bfloat16")
        if (is_zero and (vector_norm != 0.0 or vector_hash is not None)) or (
            not is_zero and (not math.isfinite(vector_norm) or vector_norm <= 0 or not vector_hash)
        ):
            errors.append(f"intervention telemetry differs: {row.get('trial_id')}")
            break
        for readout in readouts:
            token_values = readout.get("v1_token_logits")
            if expects_tokens and (token_values is None or len(token_values) != 67):
                errors.append(f"replay token readout differs: {row.get('trial_id')}")
                break
            if not expects_tokens and token_values is not None:
                errors.append(f"semantic row contains replay token logits: {row.get('trial_id')}")
                break
            groups = readout.get("group_logits", {})
            if set(groups) != expected_groups or not all(
                math.isfinite(float(value)) for value in groups.values()
            ):
                errors.append(f"readout semantic groups differ: {row.get('trial_id')}")
                break
            if not all(
                math.isfinite(float(readout.get(field, math.nan)))
                and float(readout[field]) >= 0
                for field in ("source_norm", "transported_norm")
            ):
                errors.append(f"readout norms differ: {row.get('trial_id')}")
                break
        if errors and errors[-1].startswith(
            ("replay token", "semantic row", "readout semantic", "readout norms")
        ):
            break

    analysis_dir = run_dir / "analysis"
    primary = primary_rows(run_dir)
    try:
        a1_points = independent_a1_points(primary)
        a2_points = independent_a2_points(primary)
    except (KeyError, ValueError, ZeroDivisionError) as error:
        errors.append(f"independent semantic reconstruction failed: {error}")
        a1_points, a2_points = {}, {}
    promoted_a1 = csv_rows(analysis_dir / "semantic_a1_matrix.csv")
    promoted_a1_contrasts = csv_rows(
        analysis_dir / "semantic_a1_contrasts.csv"
    )
    promoted_a1_leakage = csv_rows(
        analysis_dir / "semantic_a1_deception_leakage.csv"
    )
    if len(promoted_a1) != 112 or len(promoted_a1_contrasts) != 35:
        errors.append("A1 matrix/contrast row counts differ")
    if len(promoted_a1_leakage) != 21:
        errors.append("A1 deception-leakage row count differs")
    for row in promoted_a1:
        key = (row["transport"], row["intervention_family"], row["lexicon"])
        expected = a1_points.get(key)
        if expected is None or not math.isclose(
            float(row["mean_oriented_z"]), expected, abs_tol=1e-10
        ):
            errors.append(f"A1 promoted point differs: {key}")
    promoted_a2 = csv_rows(analysis_dir / "semantic_a2_summary.csv")
    promoted_a2_pairs = csv_rows(analysis_dir / "semantic_a2_pairs.csv")
    if len(promoted_a2) != 7 or len(promoted_a2_pairs) != 42:
        errors.append("A2 summary/pair row counts differ")
    for row in promoted_a2:
        expected = a2_points.get(row["transport"])
        if expected is None or not math.isclose(
            float(row["mean_target_minus_comparator_z"]), expected, abs_tol=1e-10
        ):
            errors.append(f"A2 promoted point differs: {row['transport']}")

    predictions = csv_rows(analysis_dir / "reader_predictions.csv")
    if len(predictions) != 14 * 1_224:
        errors.append(f"reader prediction row count differs: {len(predictions)}")
    if len({(row["reader_id"], row["trial_id"]) for row in predictions}) != len(
        predictions
    ):
        errors.append("reader predictions are duplicated")
    promoted_metrics = {
        row["reader_id"]: row
        for row in csv_rows(analysis_dir / "reader_metrics.csv")
    }
    promoted_pair_metrics = csv_rows(analysis_dir / "reader_pair_metrics.csv")
    if len(promoted_metrics) != 14 or len(promoted_pair_metrics) != 84:
        errors.append("reader metric/pair row counts differ")
    for reader_id in sorted({row["reader_id"] for row in predictions}):
        reader_rows = [row for row in predictions if row["reader_id"] == reader_id]
        labels = np.asarray([int(row["label"]) for row in reader_rows])
        scores = np.asarray([float(row["probability"]) for row in reader_rows])
        if not np.isfinite(scores).all() or np.any((scores < 0) | (scores > 1)):
            errors.append(f"reader probabilities are invalid: {reader_id}")
            continue
        pair_aucs = []
        for pair in sorted({int(row["feature_pair"]) for row in reader_rows}):
            mask = np.asarray([int(row["feature_pair"]) == pair for row in reader_rows])
            pair_aucs.append(float(roc_auc_score(labels[mask], scores[mask])))
        expected = {
            "auroc": float(roc_auc_score(labels, scores)),
            "auprc": float(average_precision_score(labels, scores)),
            "brier": float(brier_score_loss(labels, scores)),
            "macro_leave_one_pair_auroc": float(np.mean(pair_aucs)),
        }
        promoted = promoted_metrics.get(reader_id)
        if promoted is None:
            errors.append(f"reader metric row is missing: {reader_id}")
            continue
        for field, value in expected.items():
            if not math.isclose(float(promoted[field]), value, abs_tol=1e-12):
                errors.append(f"reader promoted metric differs: {reader_id}/{field}")

    summary = json.loads(
        (analysis_dir / "analysis_summary.json").read_text(encoding="utf-8")
    )
    if summary.get("status") != "complete":
        errors.append("analysis summary is not complete")
    expected_figures = {
        f"{stem}.{suffix}"
        for stem in (
            "sae_jlens_v2_a1_semantic_matrix",
            "sae_jlens_v2_a2_target_comparator",
            "sae_jlens_v2_reader_ladder",
            "sae_jlens_v2_reader_pair_heatmap",
        )
        for suffix in ("png", "pdf")
    }
    observed_figures = {
        path.name for path in (run_dir / "figures").glob("sae_jlens_v2_*")
    }
    if observed_figures != expected_figures:
        errors.append("frozen figure set differs")
    return {
        "status": "pass" if not errors else "fail",
        "protocol_version": PROTOCOL_VERSION,
        "plan_manifest_sha256": sha256_file(plan_dir / "PLAN_MANIFEST.json"),
        "run_result_manifest_sha256": sha256_file(run_dir / "RESULT_MANIFEST.json"),
        "residual_rows": shard_rows,
        "residual_shards": len(shard_names),
        "readout_rows": len(raw_rows),
        "reader_prediction_rows": len(predictions),
        "n_errors": len(errors),
        "errors": errors,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan-dir", type=Path, default=DEFAULT_PLAN_DIR)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    result = audit(args.plan_dir.resolve(), args.run_dir.resolve())
    write_json(args.out.resolve(), result)
    print(json.dumps(result, indent=2, sort_keys=True))
    if result["status"] != "pass":
        raise SystemExit(1)


if __name__ == "__main__":
    main()

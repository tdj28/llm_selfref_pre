#!/usr/bin/env python3
"""Bound analysis for Stage A gates and Stage B dose characterization."""

from __future__ import annotations

import argparse
import json
import math
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from experiments.consciousness_sae_realization_validation import (  # noqa: E402
    controls,
    j_orientation,
    preexecution,
    protocol,
    runpod_preflight,
)


class AnalysisError(RuntimeError):
    pass


def _json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise AnalysisError(f"JSON root is not an object: {path}")
    return value


def _jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            value = json.loads(line)
            if not isinstance(value, dict):
                raise AnalysisError(f"non-object JSONL row at {path}:{line_number}")
            rows.append(value)
    return rows


def _validate_self_hash(value: Mapping[str, Any], label: str) -> None:
    core = dict(value)
    supplied = core.pop("receipt_sha256", None)
    if supplied != protocol.canonical_sha256(core):
        raise AnalysisError(f"{label} self-hash differs")


def _validate_audit(audit: Mapping[str, Any], *, stage: str, run_root: Path) -> None:
    _validate_self_hash(audit, "audit receipt")
    complete = _json(run_root / "RUN_COMPLETE.json")
    _validate_self_hash(complete, "raw run receipt")
    try:
        runpod_preflight.validate_study_owned_output_tree(run_root)
    except runpod_preflight.PreflightError as exc:
        raise AnalysisError(str(exc)) from exc
    records = complete.get("records")
    if not isinstance(records, list):
        raise AnalysisError("raw run manifest is missing")
    manifested_paths: list[str] = []
    for row in records:
        if not isinstance(row, Mapping) or not isinstance(row.get("path"), str):
            raise AnalysisError("raw run manifest row is malformed")
        relative = str(row["path"])
        candidate = run_root / relative
        try:
            resolved = candidate.resolve(strict=True)
            resolved.relative_to(run_root)
        except (OSError, ValueError) as exc:
            raise AnalysisError(f"manifested analysis input escaped run root: {relative}") from exc
        if (
            candidate.is_symlink()
            or not resolved.is_file()
            or resolved.stat().st_nlink != 1
            or resolved.stat().st_size != int(row.get("bytes", -1))
            or protocol.sha256_file(resolved) != row.get("sha256")
        ):
            raise AnalysisError(f"manifested analysis input changed after audit: {relative}")
        manifested_paths.append(relative)
    observed_paths = sorted(
        path.relative_to(run_root).as_posix()
        for path in run_root.rglob("*")
        if path.is_file()
    )
    if observed_paths != sorted([*manifested_paths, "RUN_COMPLETE.json"]):
        raise AnalysisError("analysis run contains missing or unmanifested files")
    if (
        audit.get("status") != "pass"
        or audit.get("stage") != stage
        or audit.get("study_id") != protocol.STUDY_ID
        or audit.get("protocol_version") != protocol.PROTOCOL_VERSION
        or audit.get("run_id") != complete.get("run_id")
        or audit.get("plan_manifest_sha256") != complete.get("plan_manifest_sha256")
        or audit.get("raw_run_receipt_sha256") != complete.get("receipt_sha256")
        or audit.get("prior_outcome_inputs") != []
    ):
        raise AnalysisError("audit/run binding differs")


def _cluster_bootstrap(
    prompt_values: Mapping[str, float],
    *,
    namespace: str,
    expected_prompt_ids: Sequence[str] = protocol.STAGE_A_PROMPT_IDS,
) -> dict[str, float]:
    import numpy as np

    prompt_ids = tuple(sorted(prompt_values))
    if prompt_ids != tuple(sorted(expected_prompt_ids)):
        raise AnalysisError(f"cluster inventory differs for {namespace}")
    values = np.asarray([prompt_values[prompt_id] for prompt_id in prompt_ids], dtype=np.float64)
    rng = np.random.Generator(np.random.PCG64(protocol.seed64("bootstrap", namespace)))
    count = int(protocol.GATE_THRESHOLDS["bootstrap_replicates"])
    draws = rng.integers(0, len(values), size=(count, len(values)))
    means = values[draws].mean(axis=1)
    return {
        "estimate": float(values.mean()),
        "lcb_95": float(np.quantile(means, 0.025)),
        "ucb_95": float(np.quantile(means, 0.975)),
        "cluster_count": len(values),
        "bootstrap_replicates": count,
    }


def _transport_gate(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    primary = [row for row in rows if float(row["dose_fraction"]) == protocol.PRIMARY_DOSE]
    indexed = {
        (
            str(row["prompt_id"]), int(row["edit_layer"]), int(row["direction"]),
            str(row["transport"]),
        ): row
        for row in primary
    }
    output: dict[str, Any] = {}
    all_pass = True
    layer50_all_pass = True
    for metric, absolute_threshold, identity_margin, random_margin in (
        (
            "residual_delta_cosine",
            protocol.GATE_THRESHOLDS["real_j_residual_cosine_lcb_min"],
            protocol.GATE_THRESHOLDS["real_j_residual_cosine_margin_over_identity"],
            protocol.GATE_THRESHOLDS["real_j_residual_cosine_margin_over_best_random"],
        ),
        (
            "fixed_token_logit_delta_pearson",
            protocol.GATE_THRESHOLDS["real_j_logit_pearson_lcb_min"],
            protocol.GATE_THRESHOLDS["real_j_logit_pearson_margin_over_identity"],
            protocol.GATE_THRESHOLDS["real_j_logit_pearson_margin_over_best_random"],
        ),
    ):
        def summarize(
            layers: Sequence[int], directions: Sequence[int], *, suffix: str
        ) -> dict[str, Any]:
            absolute_by_prompt: dict[str, float] = {}
            identity_by_prompt: dict[str, float] = {}
            random_by_prompt: dict[str, float] = {}
            for prompt_id in protocol.STAGE_A_PROMPT_IDS:
                absolute_values: list[float] = []
                identity_values: list[float] = []
                random_values: list[float] = []
                for layer in layers:
                    for direction in directions:
                        real = float(indexed[(prompt_id, layer, direction, "real_j")][metric])
                        identity = float(indexed[(prompt_id, layer, direction, "identity")][metric])
                        random_best = max(
                            float(indexed[(prompt_id, layer, direction, f"random_j_{index}")][metric])
                            for index in range(protocol.RANDOM_J_COUNT)
                        )
                        absolute_values.append(real)
                        identity_values.append(real - identity)
                        random_values.append(real - random_best)
                absolute_by_prompt[prompt_id] = sum(absolute_values) / len(absolute_values)
                identity_by_prompt[prompt_id] = sum(identity_values) / len(identity_values)
                random_by_prompt[prompt_id] = sum(random_values) / len(random_values)
            absolute = _cluster_bootstrap(
                absolute_by_prompt, namespace=f"{metric}:{suffix}:absolute"
            )
            identity_summary = _cluster_bootstrap(
                identity_by_prompt, namespace=f"{metric}:{suffix}:identity"
            )
            random_summary = _cluster_bootstrap(
                random_by_prompt, namespace=f"{metric}:{suffix}:random"
            )
            passed = (
                absolute["lcb_95"] > float(absolute_threshold)
                and identity_summary["lcb_95"] > float(identity_margin)
                and random_summary["lcb_95"] > float(random_margin)
            )
            return {
                "status": "pass" if passed else "fail",
                "absolute_real_j": {**absolute, "threshold": absolute_threshold},
                "real_j_minus_identity": {
                    **identity_summary,
                    "threshold": identity_margin,
                },
                "real_j_minus_best_of_five_random": {
                    **random_summary,
                    "threshold": random_margin,
                },
            }

        global_summary = summarize(
            protocol.STAGE_A_LAYERS, protocol.STAGE_A_DIRECTIONS, suffix="global"
        )
        by_layer = {
            str(layer): summarize(
                (layer,), protocol.STAGE_A_DIRECTIONS, suffix=f"layer-{layer}"
            )
            for layer in protocol.STAGE_A_LAYERS
        }
        by_layer_direction = {
            f"{layer}:{direction}": summarize(
                (layer,), (direction,), suffix=f"layer-{layer}:direction-{direction}"
            )
            for layer in protocol.STAGE_A_LAYERS
            for direction in protocol.STAGE_A_DIRECTIONS
        }
        passed = global_summary["status"] == "pass"
        layer50_passed = all(
            by_layer_direction[f"50:{direction}"]["status"] == "pass"
            for direction in protocol.STAGE_A_DIRECTIONS
        )
        all_pass = all_pass and passed
        layer50_all_pass = layer50_all_pass and layer50_passed
        output[metric] = {
            **global_summary,
            "by_edit_layer": by_layer,
            "by_edit_layer_and_direction": by_layer_direction,
        }
    output["status"] = "pass" if all_pass else "fail"
    output["layer50_primary_status"] = "pass" if layer50_all_pass else "fail"
    return output


def _layer50_linearity_status(rows: Sequence[Mapping[str, Any]]) -> str:
    selected = [row for row in rows if int(row["edit_layer"]) == protocol.SAE_LAYER]
    expected = len(protocol.STAGE_A_PROMPT_IDS) * len(protocol.STAGE_A_DIRECTIONS)
    if len(selected) != expected:
        raise AnalysisError("layer-50 linearity row inventory differs")
    for row in selected:
        if row["finite"] is not True:
            return "fail"
        for prefix in ("realized_source", "j_of_realized", "actual_final"):
            if (
                float(row[f"{prefix}_linearity_cosine_min"])
                < protocol.GATE_THRESHOLDS["linearity_cosine_min"]
                or float(row[f"{prefix}_slope_discrepancy_max"])
                > protocol.GATE_THRESHOLDS["linearity_slope_discrepancy_max"]
            ):
                return "fail"
    return "pass"


def analyze_stage_a(
    *,
    run_root: Path,
    plan_dir: Path,
    audit_path: Path,
    storage_budget_path: Path,
    preexecution_authorization_path: Path,
    smoke_receipt_path: Path,
    receipt_out: Path,
    summary_out: Path,
) -> dict[str, Any]:
    root = run_root.expanduser().resolve(strict=True)
    audit = _json(audit_path)
    _validate_audit(audit, stage="stage_a", run_root=root)
    complete = _json(root / "RUN_COMPLETE.json")
    storage_budget = _json(storage_budget_path)
    try:
        controls.validate_storage_budget(storage_budget)
    except controls.ControlViolation as exc:
        raise AnalysisError(str(exc)) from exc
    execution_binding = _json(root / "execution_binding.json")
    authorization = _json(preexecution_authorization_path)
    smoke = _json(smoke_receipt_path)
    from experiments.consciousness_sae_realization_validation import smoke_test

    try:
        preexecution.validate_authorization_evidence(
            authorization, repo_root=REPO_ROOT, plan_dir=plan_dir
        )
        smoke_test.validate_smoke_receipt(
            smoke,
            expected_plan_hash=complete["plan_manifest_sha256"],
            expected_authorization=authorization,
        )
        raw_tail = (*controls.RAW_NAMESPACE, str(complete["run_id"]))
        if tuple(root.parts[-len(raw_tail) :]) != raw_tail:
            raise AnalysisError("Stage A raw run path is outside the exact namespace")
        volume_root = root.parents[len(controls.RAW_NAMESPACE)]
        smoke_file_hash = smoke_test.validate_external_receipt_file(
            volume_root=volume_root,
            receipt_path=smoke_receipt_path,
            receipt=smoke,
        )
    except (preexecution.PreexecutionError, smoke_test.SmokeTestError) as exc:
        raise AnalysisError(str(exc)) from exc
    expected_gate_hashes = {
        "storage_budget_receipt_sha256": storage_budget["receipt_sha256"],
        "preexecution_authorization_sha256": authorization["receipt_sha256"],
        "smoke_receipt_sha256": smoke["receipt_sha256"],
        "smoke_receipt_file_sha256": smoke_file_hash,
    }
    if (
        storage_budget["plan_manifest_sha256"] != complete["plan_manifest_sha256"]
        or any(
            execution_binding.get(field) != value
            for field, value in expected_gate_hashes.items()
        )
        or execution_binding.get("campaign_identity_sha256")
        != authorization["campaign_identity_sha256"]
        or execution_binding.get("smoke_receipt_relative_path")
        != smoke["external_receipt_relative_path"]
        or audit.get("gate_receipt_hashes") != expected_gate_hashes
        or audit.get("preexecution_authorization_sha256")
        != authorization["receipt_sha256"]
        or audit.get("campaign_identity_sha256")
        != authorization["campaign_identity_sha256"]
    ):
        raise AnalysisError("Stage A stop-ship audit/execution binding differs")
    realization_path = root / "realization_rows.jsonl"
    transport_path = root / "transport_rows.jsonl"
    linearity_path = root / "linearity_rows.jsonl"
    orientation_rows_path = root / "j_orientation_rows.jsonl"
    orientation_receipt_path = root / "j_orientation_receipt.json"
    realization = _jsonl(realization_path)
    transport = _jsonl(transport_path)
    linearity = _jsonl(linearity_path)
    orientation_rows = _jsonl(orientation_rows_path)
    orientation_receipt = _json(orientation_receipt_path)
    realization_validation = controls.validate_edit_realization_rows(realization)
    transport_validation = controls.validate_stage_a_transport_rows(transport)
    linearity_validation = controls.validate_stage_a_linearity_rows(linearity)
    try:
        numeric_recomputation = controls.validate_stage_a_numeric_recomputation(
            audit.get("details", {}).get("stage_a_numeric_recomputation", {})
        )
    except controls.ControlViolation as exc:
        raise AnalysisError(str(exc)) from exc
    reported_classifications = controls.compact_stage_a_numeric_classifications(
        edit_validation=realization_validation,
        transport_validation=transport_validation,
        linearity_validation=linearity_validation,
    )
    if any(
        numeric_recomputation[field] != reported_classifications[field]
        for field in (
            "edit_classification",
            "transport_classification",
            "linearity_classification",
        )
    ):
        raise AnalysisError("Stage A audit-derived classification differs")
    if any(
        protocol.sha256_file(root / relative) != digest
        for relative, digest in numeric_recomputation[
            "telemetry_file_sha256s"
        ].items()
    ):
        raise AnalysisError("Stage A audited telemetry file hash differs")
    try:
        orientation_validation = j_orientation.validate_orientation_receipt(
            orientation_receipt,
            rows=orientation_rows,
            plan_manifest_sha256=complete["plan_manifest_sha256"],
            require_pass=True,
        )
    except j_orientation.OrientationViolation as exc:
        raise AnalysisError(str(exc)) from exc
    orientation_rows_file_hash = protocol.sha256_file(orientation_rows_path)
    if orientation_rows_file_hash != orientation_receipt["rows_file_sha256"]:
        raise AnalysisError("physical J-orientation rows hash differs from receipt")
    try:
        layer50_envelope = controls.validate_layer50_envelope_inventory(realization)
    except controls.ControlViolation as exc:
        raise AnalysisError(str(exc)) from exc
    transport_gate = _transport_gate(transport)
    layer50_linearity = _layer50_linearity_status(linearity)

    exact_post = all(
        row["native_post_bytes_exact_plus"] is True
        and row["native_post_bytes_exact_minus"] is True
        for row in realization
    )
    audited_edit = numeric_recomputation["edit_classification"]
    component_statuses = {
        "edit_realization_status": audited_edit[
            "edit_realization_status"
        ],
        "realized_edit_fidelity_status": audited_edit[
            "realized_edit_fidelity_status"
        ],
        "hard_safety_status": audited_edit["hard_safety_status"],
        "native_post_bytes_status": "pass" if exact_post else "fail",
        "common_mode_status": audited_edit["common_mode_status"],
        "j_shadow_status": audited_edit["j_shadow_status"],
        "layer50_j_shadow_status": audited_edit[
            "layer50_j_shadow_status"
        ],
        "j_orientation_status": orientation_validation["status"],
        "absolute_real_j_status": transport_gate["status"],
        "real_j_over_identity_status": transport_gate["status"],
        "real_j_over_five_random_status": transport_gate["status"],
        "linearity_status": linearity_validation["status"],
        "layer50_primary_transport_status": transport_gate[
            "layer50_primary_status"
        ],
        "layer50_linearity_status": layer50_linearity,
    }
    collection_safety = all(
        component_statuses[field] == "pass"
        for field in (
            "hard_safety_status",
            "native_post_bytes_status",
            "realized_edit_fidelity_status",
            "common_mode_status",
            "j_orientation_status",
        )
    )
    component_statuses["collection_safety_status"] = (
        "pass" if collection_safety else "fail"
    )
    overall = (
        transport_validation["status"] == "pass"
        and all(value == "pass" for value in component_statuses.values())
    )
    runtime_metadata = _json(root / "runtime_metadata.json")
    resource = complete["resource"]
    core = {
        "schema_version": controls.CONTROL_SCHEMA_VERSION,
        "status": "pass" if overall else "fail",
        "study_id": protocol.STUDY_ID,
        "protocol_version": protocol.PROTOCOL_VERSION,
        "run_id": complete["run_id"],
        "plan_manifest_sha256": complete["plan_manifest_sha256"],
        "raw_run_receipt_sha256": complete["receipt_sha256"],
        "audit_receipt_sha256": audit["receipt_sha256"],
        "stage_a_numeric_recomputation_sha256": numeric_recomputation[
            "classification_sha256"
        ],
        "storage_budget_receipt_sha256": storage_budget["receipt_sha256"],
        "preexecution_authorization_sha256": authorization["receipt_sha256"],
        "smoke_receipt_sha256": smoke["receipt_sha256"],
        "smoke_receipt_file_sha256": smoke_file_hash,
        "campaign_identity_sha256": authorization["campaign_identity_sha256"],
        "edit_realization_rows_sha256": protocol.sha256_file(realization_path),
        "transport_rows_sha256": protocol.sha256_file(transport_path),
        "linearity_rows_sha256": protocol.sha256_file(linearity_path),
        "j_orientation_rows_sha256": orientation_rows_file_hash,
        "j_orientation_receipt_sha256": orientation_receipt["receipt_sha256"],
        **component_statuses,
        "j_shadow_layer_statuses": audited_edit[
            "j_shadow_layer_statuses"
        ],
        "j_shadow_layer_status_inventory_sha256": audited_edit[
            "j_shadow_layer_status_inventory_sha256"
        ],
        "neutral_prompt_count": len(protocol.STAGE_A_PROMPT_IDS),
        "realization_pair_row_count": len(realization),
        "edited_forward_count": 2304,
        "transport_row_count": len(transport),
        "linearity_row_count": len(linearity),
        "j_orientation_row_count": orientation_receipt["row_count"],
        "captured_j_layer_count": len(protocol.J_LAYERS),
        "captured_j_layers_sha256": controls.J_LAYERS_SHA256,
        "shadow_dtype": "float32",
        "layer50_realized_rms_fraction_min": layer50_envelope[
            "realized_rms_fraction_min"
        ],
        "layer50_realized_rms_fraction_max": layer50_envelope[
            "realized_rms_fraction_max"
        ],
        "layer50_envelope_row_count": layer50_envelope["row_count"],
        "layer50_envelope_identity_set_sha256": layer50_envelope[
            "identity_set_sha256"
        ],
        "model_forward_count": int(runtime_metadata["model_forward_count"]),
        "cumulative_elapsed_seconds": float(resource["cumulative_elapsed_seconds"]),
        "cumulative_spend_usd": float(resource["cumulative_estimated_spend_usd"]),
        "target_prompt_render_count": 0,
        "target_forward_count": 0,
        "target_outcome_count": 0,
        "prior_outcome_inputs": [],
    }
    receipt = {**core, "receipt_sha256": protocol.canonical_sha256(core)}
    if overall:
        controls.validate_stage_a_receipt(receipt)
    elif collection_safety:
        controls.validate_stage_a_safety_receipt(receipt)
    summary = {
        "study_id": protocol.STUDY_ID,
        "protocol_version": protocol.PROTOCOL_VERSION,
        "status": receipt["status"],
        "scope": "random-direction realization and J-transport validation",
        "transport_gate": transport_gate,
        "stage_a_numeric_recomputation": numeric_recomputation,
        "realization_validation": realization_validation,
        "transport_validation": transport_validation,
        "linearity_validation": linearity_validation,
        "j_orientation_validation": orientation_validation,
        "layer50_envelope_validation": layer50_envelope,
        "collection_safety_status": component_statuses[
            "collection_safety_status"
        ],
        "j_shadow_status": component_statuses["j_shadow_status"],
        "j_shadow_layer_statuses": audited_edit[
            "j_shadow_layer_statuses"
        ],
        "j_shadow_layer_status_inventory_sha256": audited_edit[
            "j_shadow_layer_status_inventory_sha256"
        ],
        "layer50_j_shadow_status": component_statuses["layer50_j_shadow_status"],
        "low_doses_are_diagnostic_only": [0.0025, 0.005],
        "paper_prompt_results": None,
        "prior_outcome_inputs": [],
        "receipt_sha256": receipt["receipt_sha256"],
    }
    for destination, value in ((receipt_out, receipt), (summary_out, summary)):
        target = destination.expanduser().resolve()
        if target.exists() or target.is_symlink():
            raise FileExistsError(f"analysis output already exists: {target}")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(protocol.canonical_json_bytes(value) + b"\n")
    return receipt


def _safe_slope_metrics(value: Any, reference: Any) -> tuple[float, float]:
    import torch

    left = value.float().reshape(-1)
    right = reference.float().reshape(-1)
    left_norm = float(torch.linalg.vector_norm(left).item())
    right_norm = float(torch.linalg.vector_norm(right).item())
    if left_norm == 0.0 and right_norm == 0.0:
        return 1.0, 0.0
    if left_norm == 0.0 or right_norm == 0.0:
        return 0.0, 1e30
    cosine = float(torch.dot(left, right).item() / (left_norm * right_norm))
    rmse = float(
        torch.sqrt(torch.mean((left - right).square())).item()
        / max(torch.sqrt(torch.mean(right.square())).item(), 1e-30)
    )
    return max(-1.0, min(1.0, cosine)), rmse


def _mean_ci_by_prompt(values: Mapping[str, float], namespace: str) -> dict[str, float]:
    # Stage-B assignments overlap; averaging within prompt first keeps prompt as
    # the only inferential/interval cluster.
    return _cluster_bootstrap(
        values,
        namespace="stage-b:" + namespace,
        expected_prompt_ids=protocol.STAGE_B_PROMPT_IDS,
    )


def _stage_b_transport_gate(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Gate SAE-vector J transport separately by vector class and dose."""

    by_group: dict[tuple[str, float], list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        by_group[(str(row["vector_class"]), float(row["multiplier"]))].append(row)
    groups: list[dict[str, Any]] = []
    for vector_class in protocol.VECTOR_CLASSES:
        for multiplier in protocol.STAGE_B_MULTIPLIERS:
            selected = by_group[(vector_class, float(multiplier))]
            metrics_output: dict[str, Any] = {}
            group_pass = True
            for metric, absolute_threshold, identity_margin, random_margin in (
                (
                    "residual_delta_cosine",
                    protocol.GATE_THRESHOLDS["real_j_residual_cosine_lcb_min"],
                    protocol.GATE_THRESHOLDS[
                        "real_j_residual_cosine_margin_over_identity"
                    ],
                    protocol.GATE_THRESHOLDS[
                        "real_j_residual_cosine_margin_over_best_random"
                    ],
                ),
                (
                    "fixed_token_logit_delta_pearson",
                    protocol.GATE_THRESHOLDS["real_j_logit_pearson_lcb_min"],
                    protocol.GATE_THRESHOLDS[
                        "real_j_logit_pearson_margin_over_identity"
                    ],
                    protocol.GATE_THRESHOLDS[
                        "real_j_logit_pearson_margin_over_best_random"
                    ],
                ),
            ):
                per_prompt: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
                for row in selected:
                    per_prompt[str(row["prompt_id"])].append(row)
                absolute: dict[str, float] = {}
                identity: dict[str, float] = {}
                random: dict[str, float] = {}
                for prompt_id in protocol.STAGE_B_PROMPT_IDS:
                    prompt_rows = per_prompt[prompt_id]
                    by_assignment: dict[str, dict[str, float]] = defaultdict(dict)
                    for row in prompt_rows:
                        by_assignment[str(row["assignment_id"])][str(row["transport"])] = float(
                            row[metric]
                        )
                    absolute_values = []
                    identity_values = []
                    random_values = []
                    for assignment in protocol.aggregate_assignments():
                        values = by_assignment[assignment["assignment_id"]]
                        real = values["real_j"]
                        absolute_values.append(real)
                        identity_values.append(real - values["identity"])
                        random_values.append(
                            real
                            - max(
                                values[f"random_j_{index}"]
                                for index in range(protocol.RANDOM_J_COUNT)
                            )
                        )
                    absolute[prompt_id] = sum(absolute_values) / len(absolute_values)
                    identity[prompt_id] = sum(identity_values) / len(identity_values)
                    random[prompt_id] = sum(random_values) / len(random_values)
                namespace = f"stage-b-transport:{vector_class}:{multiplier}:{metric}"
                absolute_ci = _cluster_bootstrap(
                    absolute,
                    namespace=namespace + ":absolute",
                    expected_prompt_ids=protocol.STAGE_B_PROMPT_IDS,
                )
                identity_ci = _cluster_bootstrap(
                    identity,
                    namespace=namespace + ":identity",
                    expected_prompt_ids=protocol.STAGE_B_PROMPT_IDS,
                )
                random_ci = _cluster_bootstrap(
                    random,
                    namespace=namespace + ":random",
                    expected_prompt_ids=protocol.STAGE_B_PROMPT_IDS,
                )
                passed = (
                    absolute_ci["lcb_95"] > float(absolute_threshold)
                    and identity_ci["lcb_95"] > float(identity_margin)
                    and random_ci["lcb_95"] > float(random_margin)
                )
                group_pass = group_pass and passed
                metrics_output[metric] = {
                    "status": "pass" if passed else "fail",
                    "absolute_real_j": {**absolute_ci, "threshold": absolute_threshold},
                    "real_j_minus_identity": {**identity_ci, "threshold": identity_margin},
                    "real_j_minus_best_of_five_random": {
                        **random_ci,
                        "threshold": random_margin,
                    },
                }
            groups.append(
                {
                    "vector_class": vector_class,
                    "multiplier": multiplier,
                    "status": "pass" if group_pass else "fail",
                    "metrics": metrics_output,
                }
            )
    return {"groups": groups}


def _topk_lexical_arc_summary(
    *,
    root: Path,
    pair_index: Sequence[Mapping[str, Any]],
    vocabulary: Sequence[Mapping[str, Any]],
    eligibility: Sequence[Mapping[str, Any]],
    actual_realized_integrity: bool,
) -> dict[str, Any]:
    """Summarize paired-central browse indexes without a post-hoc lexicon."""

    try:
        from safetensors.torch import load_file
    except ImportError as exc:
        raise AnalysisError("safetensors is required for lexical arc summaries") from exc
    if len(vocabulary) != protocol.VOCAB_SIZE or any(
        row.get("token_id") != token_id
        or not isinstance(row.get("token_piece"), str)
        or not isinstance(row.get("decoded_utf8"), str)
        for token_id, row in enumerate(vocabulary)
    ):
        raise AnalysisError("canonical vocabulary table differs")
    decoded = {int(row["token_id"]): str(row["decoded_utf8"]) for row in vocabulary}
    eligibility_lookup = {
        (
            row["prompt_id"],
            row["assignment_id"],
            row["vector_class"],
            float(row["multiplier"]),
        ): row
        for row in eligibility
    }
    overlap_by_group: dict[
        tuple[str, float, str, str], dict[str, list[float]]
    ] = defaultdict(lambda: defaultdict(list))
    exploratory_tokens: dict[
        tuple[str, float, str, str], dict[int, tuple[int, float]]
    ] = defaultdict(dict)
    state_labels = list(protocol.STAGE_B_CAPTURE_STATES)
    post_index = state_labels.index("50_post")
    final_index = state_labels.index("final")
    eligibility_counts: dict[tuple[str, float], list[bool]] = defaultdict(list)
    requested_fidelity_counts: dict[tuple[str, float], list[bool]] = defaultdict(list)
    for prompt_id in protocol.STAGE_B_PROMPT_IDS:
        tensors = load_file(str(root / "topk" / f"{prompt_id}.safetensors"), device="cpu")
        positive = tensors["paired_central_top_token_ids"]
        negative = tensors["paired_central_bottom_token_ids"]
        rows = sorted(
            (row for row in pair_index if row["prompt_id"] == prompt_id),
            key=lambda row: int(row["pair_row"]),
        )
        if len(rows) != 135:
            raise AnalysisError(f"paired top-k index differs for {prompt_id}")
        for row in rows:
            pair_row = int(row["pair_row"])
            vector_class = str(row["vector_class"])
            multiplier = float(row["multiplier"])
            eligibility_row = eligibility_lookup[
                (
                    prompt_id,
                    row["assignment_id"],
                    vector_class,
                    multiplier,
                )
            ]
            eligible = bool(eligibility_row["eligible_for_group_level_j_summary"])
            eligibility_counts[(vector_class, multiplier)].append(eligible)
            requested_fidelity_counts[(vector_class, multiplier)].append(
                eligibility_row["requested_edit_fidelity_status"] == "pass"
            )
            post_set_40 = set(int(value) for value in positive[pair_row, post_index, :40])
            final_set_40 = set(int(value) for value in positive[pair_row, final_index, :40])
            post_set_2000 = set(int(value) for value in positive[pair_row, post_index])
            final_set_2000 = set(int(value) for value in positive[pair_row, final_index])
            for state_index, state in enumerate(state_labels):
                current_40 = set(int(value) for value in positive[pair_row, state_index, :40])
                current_2000 = set(int(value) for value in positive[pair_row, state_index])
                overlap_by_group[(vector_class, multiplier, state, "top40_to_final")][
                    prompt_id
                ].append(len(current_40 & final_set_40) / 40)
                overlap_by_group[(vector_class, multiplier, state, "top2000_to_final")][
                    prompt_id
                ].append(len(current_2000 & final_set_2000) / protocol.TOP_K)
                overlap_by_group[(vector_class, multiplier, state, "top40_to_50_post")][
                    prompt_id
                ].append(len(current_40 & post_set_40) / 40)
                overlap_by_group[(vector_class, multiplier, state, "top2000_to_50_post")][
                    prompt_id
                ].append(len(current_2000 & post_set_2000) / protocol.TOP_K)
                for polarity, tensor in (("positive", positive), ("negative", negative)):
                    counts = exploratory_tokens[(vector_class, multiplier, state, polarity)]
                    for rank, token_id_value in enumerate(tensor[pair_row, state_index, :40]):
                        token_id = int(token_id_value)
                        count, reciprocal_rank = counts.get(token_id, (0, 0.0))
                        counts[token_id] = (count + 1, reciprocal_rank + 1.0 / (rank + 1))
        del tensors
    requested_label_status_by_group = {
        key: "valid" if values and all(values) else "invalid_inconclusive"
        for key, values in requested_fidelity_counts.items()
    }
    trajectories = []
    for key, by_prompt_lists in sorted(overlap_by_group.items(), key=lambda item: repr(item[0])):
        vector_class, multiplier, state, metric = key
        prompt_means = {
            prompt_id: sum(values) / len(values)
            for prompt_id, values in by_prompt_lists.items()
        }
        trajectories.append(
            {
                "vector_class": vector_class,
                "multiplier": multiplier,
                "state": state,
                "readout_kind": (
                    "actual_final_logits" if state == "final" else "j_lens_predicted_logits"
                ),
                "j_authorization_status": (
                    "not_applicable_actual_final"
                    if state == "final"
                    else (
                        "see_group_layer50_eligibility"
                        if state in {"50_pre", "50_post"}
                        else "invalid_inconclusive_unvalidated_propagated_state"
                    )
                ),
                "requested_label_interpretation_status": (
                    requested_label_status_by_group[(vector_class, multiplier)]
                ),
                "metric": metric,
                **_mean_ci_by_prompt(
                    prompt_means,
                    f"topk:{vector_class}:{multiplier}:{state}:{metric}",
                ),
            }
        )
    token_rows = []
    for key, counts in sorted(exploratory_tokens.items(), key=lambda item: repr(item[0])):
        vector_class, multiplier, state, polarity = key
        ranked = sorted(
            counts.items(),
            key=lambda item: (-item[1][0], -item[1][1], item[0]),
        )[:20]
        token_rows.append(
            {
                "vector_class": vector_class,
                "multiplier": multiplier,
                "state": state,
                "readout_kind": (
                    "actual_final_logits" if state == "final" else "j_lens_predicted_logits"
                ),
                "j_authorization_status": (
                    "not_applicable_actual_final"
                    if state == "final"
                    else (
                        "see_group_layer50_eligibility"
                        if state in {"50_pre", "50_post"}
                        else "invalid_inconclusive_unvalidated_propagated_state"
                    )
                ),
                "requested_label_interpretation_status": (
                    requested_label_status_by_group[(vector_class, multiplier)]
                ),
                "polarity": polarity,
                "tokens": [
                    {
                        "token_id": token_id,
                        "decoded_utf8": decoded[token_id],
                        "top40_occurrence_count": values[0],
                        "reciprocal_rank_sum": values[1],
                    }
                    for token_id, values in ranked
                ],
                "interpretation_role": "exploratory_token_inspection_only",
            }
        )
    group_authorization = [
        {
            "vector_class": vector_class,
            "multiplier": multiplier,
            "eligible_member_count": sum(values),
            "member_count": len(values),
            "layer50_j_summary_status": (
                "valid" if values and all(values) else "invalid_inconclusive"
            ),
            "requested_label_interpretation_status": (
                requested_label_status_by_group[(vector_class, multiplier)]
            ),
            "other_intermediate_j_summary_status": (
                "invalid_inconclusive_unvalidated_propagated_state"
            ),
            "final_actual_summary_status": (
                "valid"
                if actual_realized_integrity
                and requested_label_status_by_group[(vector_class, multiplier)] == "valid"
                else (
                    "invalid_requested_grouping_actual_realized_rows_remain_available"
                    if actual_realized_integrity
                    else "invalid"
                )
            ),
        }
        for (vector_class, multiplier), values in sorted(
            eligibility_counts.items(), key=lambda item: repr(item[0])
        )
    ]
    return {
        "index_role": "paired-central top/bottom-2000 browse index",
        "branch_vs_clean_arrays_are_not_paired_central": True,
        "confirmatory_semantic_lexicon": None,
        "token_inspection_is_exploratory": True,
        "actual_realized_row_characterization_status": (
            "valid" if actual_realized_integrity else "invalid"
        ),
        "requested_label_interpretation_status": (
            "valid"
            if requested_label_status_by_group
            and all(value == "valid" for value in requested_label_status_by_group.values())
            else "invalid_inconclusive"
        ),
        "top_k": protocol.TOP_K,
        "vocabulary_sha256": protocol.sha256_file(root / "vocabulary.jsonl"),
        "pair_index_sha256": protocol.sha256_file(root / "topk_pair_index.jsonl"),
        "group_authorization": group_authorization,
        "paired_central_rank_overlap_trajectories": trajectories,
        "exploratory_aggregate_top_tokens": token_rows,
    }


def analyze_stage_b(
    *,
    run_root: Path,
    plan_dir: Path,
    audit_path: Path,
    stage_a_receipt_path: Path,
    stage_a_audit_path: Path,
    target_blind_receipt_path: Path,
    storage_budget_path: Path,
    stage_b_permit_path: Path,
    preexecution_authorization_path: Path,
    summary_out: Path,
) -> dict[str, Any]:
    try:
        from safetensors.torch import load_file
        import torch
        import numpy as np
    except ImportError as exc:
        raise AnalysisError("torch and safetensors are required for Stage B analysis") from exc
    root = run_root.expanduser().resolve(strict=True)
    audit = _json(audit_path)
    _validate_audit(audit, stage="stage_b", run_root=root)
    stage_a_receipt = _json(stage_a_receipt_path)
    stage_a_audit = _json(stage_a_audit_path)
    _validate_self_hash(stage_a_audit, "Stage A audit receipt")
    if (
        stage_a_audit.get("status") != "pass"
        or stage_a_audit.get("stage") != "stage_a"
        or stage_a_audit.get("run_id") != stage_a_receipt.get("run_id")
        or stage_a_receipt.get("audit_receipt_sha256")
        != stage_a_audit.get("receipt_sha256")
    ):
        raise AnalysisError("Stage A audit/analysis receipt binding differs")
    try:
        stage_a_numeric_recomputation = (
            controls.validate_stage_a_numeric_recomputation(
                stage_a_audit.get("details", {}).get(
                    "stage_a_numeric_recomputation", {}
                )
            )
        )
    except controls.ControlViolation as exc:
        raise AnalysisError(str(exc)) from exc
    if (
        stage_a_receipt.get("stage_a_numeric_recomputation_sha256")
        != stage_a_numeric_recomputation["classification_sha256"]
    ):
        raise AnalysisError("Stage A receipt/raw numeric audit binding differs")
    target_blind_receipt = _json(target_blind_receipt_path)
    storage_budget = _json(storage_budget_path)
    stage_b_permit = _json(stage_b_permit_path)
    authorization = _json(preexecution_authorization_path)
    try:
        preexecution.validate_authorization_evidence(
            authorization, repo_root=REPO_ROOT, plan_dir=plan_dir
        )
        controls.validate_stage_b_permit(
            stage_b_permit,
            stage_a_receipt=stage_a_receipt,
            target_blind_receipt=target_blind_receipt,
            storage_budget=storage_budget,
        )
    except (preexecution.PreexecutionError, controls.ControlViolation) as exc:
        raise AnalysisError(str(exc)) from exc
    if preexecution_authorization_path.read_bytes() != (
        protocol.canonical_json_bytes(authorization) + b"\n"
    ):
        raise AnalysisError("Stage B authorization is not canonical JSON")
    stage_a_layer50_j_gate_pass = (
        controls.stage_b_layer50_j_interpretation_gate_pass(stage_a_receipt)
    )
    complete = _json(root / "RUN_COMPLETE.json")
    binding = _json(root / "execution_binding.json")
    expected_gate_hashes = {
        "stage_a_receipt_sha256": stage_a_receipt["receipt_sha256"],
        "stage_a_audit_receipt_sha256": stage_a_audit["receipt_sha256"],
        "stage_b_permit_sha256": stage_b_permit["receipt_sha256"],
        "target_blind_receipt_sha256": target_blind_receipt["receipt_sha256"],
        "storage_budget_receipt_sha256": storage_budget["receipt_sha256"],
        "preexecution_authorization_sha256": authorization["receipt_sha256"],
    }
    if (
        audit.get("gate_receipt_hashes") != expected_gate_hashes
        or any(binding.get(field) != digest for field, digest in expected_gate_hashes.items())
        or any(
            value.get("plan_manifest_sha256") != complete["plan_manifest_sha256"]
            for value in (
                stage_a_receipt,
                target_blind_receipt,
                storage_budget,
                stage_b_permit,
            )
        )
        or stage_b_permit.get("run_id") != complete.get("run_id")
        or binding.get("campaign_identity_sha256")
        != authorization["campaign_identity_sha256"]
        or stage_a_receipt.get("preexecution_authorization_sha256")
        != authorization["receipt_sha256"]
        or stage_a_receipt.get("campaign_identity_sha256")
        != authorization["campaign_identity_sha256"]
        or audit.get("preexecution_authorization_sha256")
        != authorization["receipt_sha256"]
        or audit.get("campaign_identity_sha256")
        != authorization["campaign_identity_sha256"]
    ):
        raise AnalysisError("Stage B audit/execution/permit chain binding differs")
    index_rows = _jsonl(root / "branch_index.jsonl")
    edit_rows = _jsonl(root / "edit_realization_rows.jsonl")
    transport_rows = _jsonl(root / "transport_rows.jsonl")
    try:
        edit_validation = controls.validate_stage_b_edit_rows(edit_rows)
    except controls.ControlViolation as exc:
        raise AnalysisError(str(exc)) from exc
    if edit_validation["actual_realized_integrity_status"] != "pass":
        raise AnalysisError("Stage B actual-realized edit integrity failed")
    if any(
        audit.get("details", {}).get(field) != edit_validation[field]
        for field in (
            "actual_realized_integrity_status",
            "actual_realized_integrity_pass_count",
            "actual_realized_integrity_failure_count",
            "requested_edit_fidelity_status",
            "requested_edit_fidelity_pass_count",
            "requested_edit_fidelity_failure_count",
        )
    ):
        raise AnalysisError("Stage B audit/edit-fidelity status binding differs")
    transport_validation = controls.validate_stage_b_transport_rows(transport_rows)
    if transport_validation["status"] != "pass":
        raise AnalysisError("Stage B paired transport telemetry failed integrity")
    stage_b_transport_gate = _stage_b_transport_gate(transport_rows)
    actual_realized_integrity = True
    signed_fidelity = {
        (
            row["prompt_id"],
            row["assignment_id"],
            row["vector_class"],
            int(row["sign"]),
            float(row["multiplier"]),
        ): controls.stage_b_requested_edit_fidelity_pass(row)
        for row in edit_rows
    }
    pair_fidelity = {
        (
            prompt_id,
            assignment["assignment_id"],
            vector_class,
            float(multiplier),
        ): all(
            signed_fidelity[
                (
                    prompt_id,
                    assignment["assignment_id"],
                    vector_class,
                    sign,
                    float(multiplier),
                )
            ]
            for sign in protocol.SIGNS
        )
        for prompt_id in protocol.STAGE_B_PROMPT_IDS
        for assignment in protocol.aggregate_assignments()
        for vector_class in protocol.VECTOR_CLASSES
        for multiplier in protocol.STAGE_B_MULTIPLIERS
    }
    for group in stage_b_transport_gate["groups"]:
        vector_class = str(group["vector_class"])
        multiplier = float(group["multiplier"])
        requested_labels_valid = all(
            pair_fidelity[
                (
                    prompt_id,
                    assignment["assignment_id"],
                    vector_class,
                    multiplier,
                )
            ]
            for prompt_id in protocol.STAGE_B_PROMPT_IDS
            for assignment in protocol.aggregate_assignments()
        )
        group["requested_label_interpretation_status"] = (
            "valid" if requested_labels_valid else "invalid_inconclusive"
        )
    envelope_min = float(stage_a_receipt["layer50_realized_rms_fraction_min"])
    envelope_max = float(stage_a_receipt["layer50_realized_rms_fraction_max"])
    group_gate = {
        (row["vector_class"], float(row["multiplier"])): row["status"] == "pass"
        for row in stage_b_transport_gate["groups"]
    }
    group_membership_eligibility = []
    for row in transport_rows:
        if row["transport"] != "real_j":
            continue
        fraction = float(row["realized_rms_fraction"])
        in_envelope = envelope_min <= fraction <= envelope_max
        direct_gate_pass = group_gate[(row["vector_class"], float(row["multiplier"]))]
        requested_fidelity_pass = pair_fidelity[
            (
                row["prompt_id"],
                row["assignment_id"],
                row["vector_class"],
                float(row["multiplier"]),
            )
        ]
        group_membership_eligibility.append(
            {
                "prompt_id": row["prompt_id"],
                "assignment_id": row["assignment_id"],
                "vector_class": row["vector_class"],
                "multiplier": row["multiplier"],
                "realized_rms_fraction": fraction,
                "stage_a_envelope_min": envelope_min,
                "stage_a_envelope_max": envelope_max,
                "in_stage_a_validated_envelope": in_envelope,
                "stage_b_direct_transport_group_status": (
                    "pass" if direct_gate_pass else "fail"
                ),
                "requested_edit_fidelity_status": (
                    "pass" if requested_fidelity_pass else "fail"
                ),
                "stage_a_layer50_j_shadow_status": stage_a_receipt[
                    "layer50_j_shadow_status"
                ],
                "eligible_for_group_level_j_summary": bool(
                    actual_realized_integrity
                    and requested_fidelity_pass
                    and stage_a_layer50_j_gate_pass
                    and in_envelope
                    and direct_gate_pass
                ),
            }
        )
    lexical_arc_summary = _topk_lexical_arc_summary(
        root=root,
        pair_index=_jsonl(root / "topk_pair_index.jsonl"),
        vocabulary=_jsonl(root / "vocabulary.jsonl"),
        eligibility=group_membership_eligibility,
        actual_realized_integrity=actual_realized_integrity,
    )
    prompt_group_fidelity = {
        (prompt_id, vector_class, float(multiplier)): all(
            pair_fidelity[
                (
                    prompt_id,
                    assignment["assignment_id"],
                    vector_class,
                    float(multiplier),
                )
            ]
            for assignment in protocol.aggregate_assignments()
        )
        for prompt_id in protocol.STAGE_B_PROMPT_IDS
        for vector_class in protocol.VECTOR_CLASSES
        for multiplier in protocol.STAGE_B_MULTIPLIERS
    }
    prompt_rows: list[dict[str, Any]] = []
    for prompt_id in protocol.STAGE_B_PROMPT_IDS:
        residuals = load_file(
            str(root / "residuals" / f"{prompt_id}.safetensors"), device="cpu"
        )["residuals"]
        rows = [row for row in index_rows if row["prompt_id"] == prompt_id]
        by_key = {
            (
                row.get("assignment_id"), row.get("vector_class"),
                int(row.get("sign", 0)), float(row.get("multiplier", 0.0)),
            ): int(row["shard_row"])
            for row in rows
            if row["condition"] == "edited"
        }
        clean_row = next(row for row in rows if row["condition"] == "clean")
        clean = residuals[int(clean_row["shard_row"])].float()
        assignment_ids = [row["assignment_id"] for row in protocol.aggregate_assignments()]
        for vector_class in protocol.VECTOR_CLASSES:
            for state_index, state in enumerate(protocol.STAGE_B_CAPTURE_STATES):
                per_multiplier: dict[float, list[tuple[Any, Any]]] = defaultdict(list)
                for assignment_id in assignment_ids:
                    for multiplier in protocol.STAGE_B_MULTIPLIERS:
                        plus = residuals[by_key[(assignment_id, vector_class, 1, multiplier)], state_index]
                        minus = residuals[by_key[(assignment_id, vector_class, -1, multiplier)], state_index]
                        central = (plus.float() - minus.float()) * 0.5
                        common = (
                            (plus.float() + minus.float()) * 0.5 - clean[state_index]
                        )
                        per_multiplier[multiplier].append((central, common))
                reference = per_multiplier[1.0]
                for multiplier in protocol.STAGE_B_MULTIPLIERS:
                    cosines: list[float] = []
                    discrepancies: list[float] = []
                    central_rms: list[float] = []
                    common_ratios: list[float] = []
                    for (central, common), (ref_central, _ref_common) in zip(
                        per_multiplier[multiplier], reference, strict=True
                    ):
                        cosine, discrepancy = _safe_slope_metrics(
                            central / multiplier, ref_central
                        )
                        cosines.append(cosine)
                        discrepancies.append(discrepancy)
                        c_rms = float(torch.sqrt(torch.mean(central.square())).item())
                        m_rms = float(torch.sqrt(torch.mean(common.square())).item())
                        central_rms.append(c_rms)
                        common_ratios.append(m_rms / max(c_rms, 1e-30))
                    prompt_rows.append(
                        {
                            "prompt_id": prompt_id,
                            "vector_class": vector_class,
                            "state": state,
                            "multiplier": multiplier,
                            "requested_label_interpretation_status": (
                                "valid"
                                if prompt_group_fidelity[
                                    (prompt_id, vector_class, float(multiplier))
                                ]
                                else "invalid_inconclusive"
                            ),
                            "assignment_count": len(assignment_ids),
                            "mean_slope_cosine_to_1x": float(np.mean(cosines)),
                            "mean_slope_relative_rmse_to_1x": float(np.mean(discrepancies)),
                            "mean_central_delta_rms": float(np.mean(central_rms)),
                            "mean_common_mode_to_central_rms": float(
                                np.mean(common_ratios)
                            ),
                        }
                    )
        del residuals
    grouped: dict[tuple[str, str, float, str], dict[str, float]] = defaultdict(dict)
    metric_names = (
        "mean_slope_cosine_to_1x",
        "mean_slope_relative_rmse_to_1x",
        "mean_central_delta_rms",
        "mean_common_mode_to_central_rms",
    )
    for row in prompt_rows:
        for metric in metric_names:
            grouped[(row["vector_class"], row["state"], row["multiplier"], metric)][
                row["prompt_id"]
            ] = float(row[metric])
    trajectories = []
    for (vector_class, state, multiplier, metric), values in sorted(
        grouped.items(), key=lambda item: repr(item[0])
    ):
        trajectories.append(
            {
                "vector_class": vector_class,
                "state": state,
                "multiplier": multiplier,
                "requested_label_interpretation_status": (
                    "valid"
                    if all(
                        prompt_group_fidelity[
                            (prompt_id, vector_class, float(multiplier))
                        ]
                        for prompt_id in protocol.STAGE_B_PROMPT_IDS
                    )
                    else "invalid_inconclusive"
                ),
                "metric": metric,
                **_mean_ci_by_prompt(
                    values, f"{vector_class}:{state}:{multiplier}:{metric}"
                ),
            }
        )
    prompt_lookup = {
        (row["prompt_id"], row["vector_class"], row["state"], row["multiplier"]): row
        for row in prompt_rows
    }
    paired_contrasts = []
    for comparator in ("matched", "isotropic"):
        for state in protocol.STAGE_B_CAPTURE_STATES:
            for multiplier in protocol.STAGE_B_MULTIPLIERS:
                for metric in metric_names:
                    differences = {
                        prompt_id: float(
                            prompt_lookup[(prompt_id, "target", state, multiplier)][metric]
                        )
                        - float(
                            prompt_lookup[(prompt_id, comparator, state, multiplier)][metric]
                        )
                        for prompt_id in protocol.STAGE_B_PROMPT_IDS
                    }
                    paired_contrasts.append(
                        {
                            "contrast": f"target_minus_{comparator}",
                            "state": state,
                            "multiplier": multiplier,
                            "requested_label_interpretation_status": (
                                "valid"
                                if all(
                                    prompt_group_fidelity[
                                        (prompt_id, vector_class, float(multiplier))
                                    ]
                                    for prompt_id in protocol.STAGE_B_PROMPT_IDS
                                    for vector_class in ("target", comparator)
                                )
                                else "invalid_inconclusive"
                            ),
                            "metric": metric,
                            **_mean_ci_by_prompt(
                                differences,
                                f"target-minus-{comparator}:{state}:{multiplier}:{metric}",
                            ),
                        }
                    )
    summary_core = {
        "schema_version": 1,
        "status": "complete",
        "study_id": protocol.STUDY_ID,
        "protocol_version": protocol.PROTOCOL_VERSION,
        "run_id": complete["run_id"],
        "plan_manifest_sha256": complete["plan_manifest_sha256"],
        "audit_receipt_sha256": audit["receipt_sha256"],
        "stage_a_receipt_sha256": stage_a_receipt["receipt_sha256"],
        "stage_a_audit_receipt_sha256": stage_a_audit["receipt_sha256"],
        "target_blind_receipt_sha256": target_blind_receipt["receipt_sha256"],
        "storage_budget_receipt_sha256": storage_budget["receipt_sha256"],
        "stage_b_permit_sha256": stage_b_permit["receipt_sha256"],
        "preexecution_authorization_sha256": authorization["receipt_sha256"],
        "campaign_identity_sha256": authorization["campaign_identity_sha256"],
        "analysis_role": "neutral-prompt SAE-family dose characterization",
        "paper_prompt_outcome": False,
        "prompt_is_cluster_unit": True,
        "assignments_are_overlapping_not_independent": True,
        # Backward-compatible alias for hard/native actual-realized integrity.
        "edit_integrity_status": "pass",
        "actual_realized_integrity_status": edit_validation[
            "actual_realized_integrity_status"
        ],
        "actual_realized_integrity_pass_count": edit_validation[
            "actual_realized_integrity_pass_count"
        ],
        "actual_realized_integrity_failure_count": edit_validation[
            "actual_realized_integrity_failure_count"
        ],
        "requested_edit_fidelity_status": edit_validation[
            "requested_edit_fidelity_status"
        ],
        "requested_edit_fidelity_pass_count": edit_validation[
            "requested_edit_fidelity_pass_count"
        ],
        "requested_edit_fidelity_failure_count": edit_validation[
            "requested_edit_fidelity_failure_count"
        ],
        "requested_realized_relative_rmse_max": edit_validation[
            "requested_realized_relative_rmse_max"
        ],
        "requested_realized_cosine_min": edit_validation[
            "requested_realized_cosine_min"
        ],
        "requested_direction_class_dose_interpretation_status": (
            "valid"
            if edit_validation["requested_edit_fidelity_status"] == "pass"
            else "invalid_inconclusive"
        ),
        "multipliers": list(protocol.STAGE_B_MULTIPLIERS),
        "capture_states": list(protocol.STAGE_B_CAPTURE_STATES),
        "prompt_level_rows": prompt_rows,
        "clustered_trajectories": trajectories,
        "paired_prompt_cluster_contrasts": paired_contrasts,
        "stage_b_direct_transport_validation": transport_validation,
        "stage_b_direct_transport_gate": stage_b_transport_gate,
        "stage_a_layer50_j_shadow_status": stage_a_receipt[
            "layer50_j_shadow_status"
        ],
        "j_group_membership_eligibility": group_membership_eligibility,
        "per_assignment_j_claims_authorized": False,
        "paired_central_lexical_arc_summary": lexical_arc_summary,
        "requested_native_realized_telemetry_sha256": protocol.sha256_file(
            root / "edit_realization_rows.jsonl"
        ),
        "raw_residuals_authoritative": True,
        "top_2000_is_browse_index_only": True,
        "replay_equivalence_status": "not_run_replay_capable_only",
        "replay_verified_claims": False,
        "layer50_j_derived_output_status": (
            "valid_all_conditions"
            if group_membership_eligibility
            and all(
                row["eligible_for_group_level_j_summary"]
                for row in group_membership_eligibility
            )
            else (
                "valid_only_for_authorized_conditions"
                if any(
                    row["eligible_for_group_level_j_summary"]
                    for row in group_membership_eligibility
                )
                else "invalid_inconclusive"
            )
        ),
        "other_layer_j_derived_output_status": (
            "invalid_inconclusive_unvalidated_propagated_state"
        ),
        "actual_residual_and_final_characterization_status": (
            "valid_requested_grouping"
            if edit_validation["requested_edit_fidelity_status"] == "pass"
            else "valid_actual_realized_rows_only_requested_grouping_invalid"
        ),
        "actual_realized_row_characterization_status": "valid",
        "target_prompt_render_count": 0,
        "target_outcome_count": 0,
        "prior_outcome_inputs": [],
    }
    summary = {
        **summary_core,
        "receipt_sha256": protocol.canonical_sha256(summary_core),
    }
    target = summary_out.expanduser().resolve()
    if target.exists() or target.is_symlink():
        raise FileExistsError(f"Stage B analysis output already exists: {target}")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(protocol.canonical_json_bytes(summary) + b"\n")
    return summary


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    stage_a = subparsers.add_parser("stage-a")
    stage_a.add_argument("--run-root", type=Path, required=True)
    stage_a.add_argument("--plan-dir", type=Path, required=True)
    stage_a.add_argument("--audit", type=Path, required=True)
    stage_a.add_argument("--storage-budget", type=Path, required=True)
    stage_a.add_argument(
        "--preexecution-authorization", type=Path, required=True
    )
    stage_a.add_argument("--smoke-receipt", type=Path, required=True)
    stage_a.add_argument("--receipt-out", type=Path, required=True)
    stage_a.add_argument("--summary-out", type=Path, required=True)
    stage_b = subparsers.add_parser("stage-b")
    stage_b.add_argument("--run-root", type=Path, required=True)
    stage_b.add_argument("--plan-dir", type=Path, required=True)
    stage_b.add_argument("--audit", type=Path, required=True)
    stage_b.add_argument("--stage-a-receipt", type=Path, required=True)
    stage_b.add_argument("--stage-a-audit", type=Path, required=True)
    stage_b.add_argument("--target-blind-receipt", type=Path, required=True)
    stage_b.add_argument("--storage-budget", type=Path, required=True)
    stage_b.add_argument("--stage-b-permit", type=Path, required=True)
    stage_b.add_argument(
        "--preexecution-authorization", type=Path, required=True
    )
    stage_b.add_argument("--summary-out", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "stage-a":
        result = analyze_stage_a(
            run_root=args.run_root,
            plan_dir=args.plan_dir,
            audit_path=args.audit,
            storage_budget_path=args.storage_budget,
            preexecution_authorization_path=args.preexecution_authorization,
            smoke_receipt_path=args.smoke_receipt,
            receipt_out=args.receipt_out,
            summary_out=args.summary_out,
        )
    else:
        result = analyze_stage_b(
            run_root=args.run_root,
            plan_dir=args.plan_dir,
            audit_path=args.audit,
            stage_a_receipt_path=args.stage_a_receipt,
            stage_a_audit_path=args.stage_a_audit,
            target_blind_receipt_path=args.target_blind_receipt,
            storage_budget_path=args.storage_budget,
            stage_b_permit_path=args.stage_b_permit,
            preexecution_authorization_path=args.preexecution_authorization,
            summary_out=args.summary_out,
        )
    print(result["receipt_sha256"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

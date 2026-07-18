#!/usr/bin/env python3
"""Build the executable receipt chain between neutral Stage A and Stage B.

The builders in this module do not accept arbitrary JSON fragments.  They
derive every field from validated plan, raw-run, audit, benchmark, filesystem,
review, and Git evidence.  This keeps the Stage-B command reachable without
making its authorization receipts hand-authored or outcome-adaptive.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from experiments.consciousness_sae_realization_validation import (  # noqa: E402
    controls,
    protocol,
    review_adjudication as review_closure,
    runpod_preflight,
)


class ReceiptBuildError(RuntimeError):
    """Raised when a required receipt cannot be derived from supplied evidence."""


def _load_json(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ReceiptBuildError(f"{label} is not readable canonical JSON: {path}") from exc
    if not isinstance(value, dict):
        raise ReceiptBuildError(f"{label} is not a JSON object: {path}")
    return value


def _write_receipt(path: Path, receipt: Mapping[str, Any]) -> Path:
    destination = path.expanduser().absolute()
    if destination.exists() or destination.is_symlink():
        raise ReceiptBuildError(f"refusing to overwrite receipt: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(destination.name + ".partial")
    if temporary.exists() or temporary.is_symlink():
        raise ReceiptBuildError(f"partial receipt already exists: {temporary}")
    temporary.write_bytes(controls.canonical_json_bytes(dict(receipt)) + b"\n")
    with temporary.open("rb") as handle:
        os.fsync(handle.fileno())
    os.replace(temporary, destination)
    return destination


def _sealed(core: Mapping[str, Any]) -> dict[str, Any]:
    value = dict(core)
    value["receipt_sha256"] = controls.canonical_sha256(value)
    return value


def _validate_plan_manifest(value: Mapping[str, Any]) -> dict[str, Any]:
    required = {
        "schema_version",
        "study_id",
        "protocol_version",
        "scope",
        "paper_prompt_render_count",
        "behavioral_replication_included",
        "stage_a_signed_edit_forward_count",
        "stage_b_edit_forward_count",
        "files",
        "prior_outcome_inputs",
        "plan_manifest_sha256",
    }
    if set(value) != required:
        raise ReceiptBuildError("plan manifest schema differs")
    core = dict(value)
    supplied = core.pop("plan_manifest_sha256")
    if supplied != controls.canonical_sha256(core):
        raise ReceiptBuildError("plan manifest self-hash differs")
    if (
        value["schema_version"] != protocol.PLAN_SCHEMA_VERSION
        or value["study_id"] != protocol.STUDY_ID
        or value["protocol_version"] != protocol.PROTOCOL_VERSION
        or value["paper_prompt_render_count"] != 0
        or value["behavioral_replication_included"] is not False
        or value["stage_a_signed_edit_forward_count"]
        != protocol.RESOURCE_LIMITS["max_stage_a_edited_forwards"]
        or value["stage_b_edit_forward_count"]
        != protocol.RESOURCE_LIMITS["max_stage_b_edited_forwards"]
        or value["prior_outcome_inputs"] != []
    ):
        raise ReceiptBuildError("plan manifest identity or target-blind scope differs")
    return dict(value)


def _validate_raw_stage_a_receipt(
    value: Mapping[str, Any], *, plan_hash: str, analysis_receipt: Mapping[str, Any]
) -> dict[str, Any]:
    core = dict(value)
    supplied = core.pop("receipt_sha256", None)
    if supplied != controls.canonical_sha256(core):
        raise ReceiptBuildError("Stage A raw-run receipt self-hash differs")
    if (
        value.get("status") != "complete"
        or value.get("stage") != "stage_a"
        or value.get("study_id") != protocol.STUDY_ID
        or value.get("protocol_version") != protocol.PROTOCOL_VERSION
        or value.get("plan_manifest_sha256") != plan_hash
        or value.get("prior_outcome_inputs") != []
        or analysis_receipt.get("raw_run_receipt_sha256") != supplied
        or analysis_receipt.get("run_id") != value.get("run_id")
    ):
        raise ReceiptBuildError("Stage A raw-run receipt identity/binding differs")
    runtime = value.get("runtime")
    if not isinstance(runtime, Mapping):
        raise ReceiptBuildError("Stage A raw-run runtime metadata is missing")
    forward_count = runtime.get("model_forward_count")
    if isinstance(forward_count, bool) or not isinstance(forward_count, int) or forward_count <= 0:
        raise ReceiptBuildError("Stage A raw-run model-forward count is invalid")
    records = value.get("records")
    if not isinstance(records, list):
        raise ReceiptBuildError("Stage A raw-run record inventory is missing")
    roles = {row.get("role") for row in records if isinstance(row, Mapping)}
    required_roles = {
        "execution_binding",
        "prompt_receipts",
        "stage_a_raw_residuals",
        "stage_a_exact_arithmetic_vectors",
        "realization_metrics",
        "transport_metrics",
        "linearity_metrics",
        "runtime_metadata",
    }
    if not required_roles.issubset(roles):
        raise ReceiptBuildError("Stage A raw-run evidence inventory is incomplete")
    return dict(value)


def _tree_bytes(root: Path) -> int:
    if root.is_symlink() or not root.is_dir():
        raise ReceiptBuildError(f"public-artifact root is not a real directory: {root}")
    total = 0
    for current, directories, files in os.walk(root, followlinks=False):
        current_path = Path(current)
        for name in directories:
            if (current_path / name).is_symlink():
                raise ReceiptBuildError("public-artifact tree contains a directory symlink")
        for name in files:
            path = current_path / name
            if path.is_symlink() or not path.is_file() or path.stat().st_nlink != 1:
                raise ReceiptBuildError("public-artifact tree contains an unsafe file")
            total += path.stat().st_size
    if total <= 0:
        raise ReceiptBuildError("public-artifact tree is empty")
    return total


def storage_workload() -> dict[str, int]:
    """Return the conservative, frozen all-stage archive byte calculation."""

    # Stage A: 2,304 edited branches plus eight clean traces.  Stage B: 2,160
    # edited branches plus eight clean traces.  Charging every trace at 36
    # states intentionally overcounts the 35-state Stage-A clean trace by eight
    # residual vectors.
    validation_units = (
        int(protocol.RESOURCE_LIMITS["max_stage_a_edited_forwards"])
        + int(protocol.RESOURCE_LIMITS["max_stage_b_edited_forwards"])
        + len(protocol.STAGE_A_PROMPT_IDS)
        + len(protocol.STAGE_B_PROMPT_IDS)
    )
    residual = controls.expected_residual_bytes(
        blocks=validation_units,
        positions_per_block=1,
        states_per_position=len(protocol.STAGE_B_CAPTURE_STATES),
    )
    # Three 271-row branch arrays (absolute, positive delta, negative delta)
    # plus two 135-row signed-pair central arrays (positive and negative).
    stage_b_selected_logits = (
        len(protocol.STAGE_B_PROMPT_IDS)
        * len(protocol.STAGE_B_CAPTURE_STATES)
        * protocol.TOP_K
        * (4 + 4)
        * (3 * (1 + 270) + 2 * 135)
    )
    # Stage A retains one actual and seven transport-predicted FP32 deltas on
    # the fixed 2,048-token panel for every signed pair.
    stage_a_selected_logits = (
        len(protocol.STAGE_A_PROMPT_IDS)
        * 144
        * 2048
        * 4
        * (1 + len(protocol.TRANSPORTS))
    )
    # Exact requested/native/realized arithmetic archives from both stages.
    stage_a_hook = (
        len(protocol.STAGE_A_PROMPT_IDS)
        * 144
        * protocol.WIDTH
        # Request FP32/BF16; realized plus/minus/central/common/final FP32;
        # production BF16 and shadow FP32 J; seven BF16 transport predictions.
        * (4 + 2 + 5 * 4 + 2 + 4 + len(protocol.TRANSPORTS) * 2)
    )
    stage_b_hook = (
        len(protocol.STAGE_B_PROMPT_IDS)
        * 270
        * protocol.WIDTH
        * (4 + 2 + 4)
    )
    vector_inventory = 45 * protocol.WIDTH * 2
    return {
        "validation_units": validation_units,
        "residual_bytes": residual,
        "selected_logit_bytes": stage_b_selected_logits + stage_a_selected_logits,
        "metadata_bytes": 1024**3,
        "hook_tensor_bytes": stage_a_hook + stage_b_hook + vector_inventory,
    }


def build_storage_budget(
    *,
    plan_manifest: Mapping[str, Any],
    benchmark_receipt: Mapping[str, Any],
    ownership_receipt: Mapping[str, Any],
    guest_receipt: Mapping[str, Any],
    cache_receipt: Mapping[str, Any],
    volume_root: Path,
    volume_id: str,
) -> dict[str, Any]:
    """Measure the mounted volume and seal the exact storage authorization."""

    plan = _validate_plan_manifest(plan_manifest)
    try:
        benchmark = controls.validate_storage_benchmark(benchmark_receipt)
        root = controls.require_volume_root(volume_root, volume_id=volume_id)
    except controls.ControlViolation as exc:
        raise ReceiptBuildError(str(exc)) from exc
    try:
        ownership = runpod_preflight.validate_ownership_receipt(ownership_receipt)
        guest = runpod_preflight.validate_guest_receipt(
            guest_receipt, ownership_receipt=ownership
        )
        cache = runpod_preflight.validate_cache_receipt(
            cache_receipt,
            guest_receipt=guest,
            ownership_receipt=ownership,
        )
    except runpod_preflight.PreflightError as exc:
        raise ReceiptBuildError(str(exc)) from exc
    if ownership["network_volume_id"] != volume_id:
        raise ReceiptBuildError("cache/ownership receipt volume differs from storage volume")
    plan_hash = str(plan["plan_manifest_sha256"])
    if benchmark["plan_manifest_sha256"] != plan_hash:
        raise ReceiptBuildError("storage benchmark is bound to a different plan")
    # The independently rehashed immutable cache is reused in place.  Its
    # validated retained-byte count is charged here; weights are never copied
    # into the new study namespace.
    Path(str(cache["cache_root"])).resolve(strict=True)
    public_bytes = int(cache["full_retained_bytes"])
    try:
        measured_usage = runpod_preflight.measure_volume_usage(root)
    except runpod_preflight.PreflightError as exc:
        raise ReceiptBuildError(str(exc)) from exc
    provider_capacity = int(ownership["provider_volume_size_bytes"])
    quota_remaining = max(
        0, provider_capacity - int(measured_usage["accounted_usage_bytes"])
    )
    workload = storage_workload()
    raw_ceiling = int(protocol.RESOURCE_LIMITS["raw_run_ceiling_bytes"])
    reserve = int(protocol.RESOURCE_LIMITS["post_run_free_reserve_bytes"])
    core = {
        "schema_version": controls.CONTROL_SCHEMA_VERSION,
        "status": "pass",
        "study_id": protocol.STUDY_ID,
        "protocol_version": protocol.PROTOCOL_VERSION,
        "plan_manifest_sha256": plan_hash,
        "benchmark_receipt_sha256": benchmark["receipt_sha256"],
        "volume_id": volume_id,
        "capacity_bytes": provider_capacity,
        "free_bytes_before_run": quota_remaining,
        "public_artifact_bytes": public_bytes,
        "expected_validation_units": workload["validation_units"],
        "capture_positions_per_unit": 1,
        "capture_states_per_position": len(protocol.STAGE_B_CAPTURE_STATES),
        "residual_width": protocol.WIDTH,
        "residual_dtype": controls.RESIDUAL_DTYPE,
        "residual_dtype_bytes": controls.RESIDUAL_DTYPE_BYTES,
        "expected_residual_bytes": workload["residual_bytes"],
        "expected_selected_logit_bytes": workload["selected_logit_bytes"],
        "expected_metadata_bytes": workload["metadata_bytes"],
        "expected_hook_tensor_bytes": workload["hook_tensor_bytes"],
        # Transient/partial bytes are already charged inside the 32-GiB raw
        # ceiling; zero here means no *additional* additive reservation.
        "transient_peak_ceiling_bytes": 0,
        "max_concurrent_partial_bytes": int(protocol.RESOURCE_LIMITS["max_shard_bytes"]),
        "raw_run_ceiling_bytes": raw_ceiling,
        "minimum_final_reserve_bytes": reserve,
        "required_free_bytes": raw_ceiling + reserve,
        "max_atomic_shard_bytes": int(protocol.RESOURCE_LIMITS["max_shard_bytes"]),
        "model_forward_count": 0,
        "target_prompt_render_count": 0,
        "target_forward_count": 0,
        "target_outcome_count": 0,
        "prior_outcome_inputs": [],
    }
    receipt = _sealed(core)
    try:
        return controls.validate_storage_budget(receipt)
    except controls.ControlViolation as exc:
        raise ReceiptBuildError(str(exc)) from exc


def build_target_blind_receipt(
    *,
    plan_manifest: Mapping[str, Any],
    stage_a_raw_receipt: Mapping[str, Any],
    stage_a_receipt: Mapping[str, Any],
    storage_benchmark: Mapping[str, Any],
    storage_budget: Mapping[str, Any],
) -> dict[str, Any]:
    """Derive all pre-Stage-B target-blind gate rows from executed evidence."""

    plan = _validate_plan_manifest(plan_manifest)
    plan_hash = str(plan["plan_manifest_sha256"])
    try:
        stage_a = controls.validate_stage_a_safety_receipt(stage_a_receipt)
        benchmark = controls.validate_storage_benchmark(storage_benchmark)
        budget = controls.validate_storage_budget(storage_budget)
    except controls.ControlViolation as exc:
        raise ReceiptBuildError(str(exc)) from exc
    raw = _validate_raw_stage_a_receipt(
        stage_a_raw_receipt, plan_hash=plan_hash, analysis_receipt=stage_a
    )
    if any(
        value["plan_manifest_sha256"] != plan_hash
        for value in (stage_a, benchmark, budget)
    ):
        raise ReceiptBuildError("target-blind component plan bindings differ")
    forward_count = int(raw["runtime"]["model_forward_count"])
    evidence_hashes = {
        "v1_source_inventory": plan_hash,
        "v1_public_artifact_rehash": raw["receipt_sha256"],
        "v1_tokenizer_endpoints": raw["receipt_sha256"],
        "v1_sae_vector_plan_inventory": plan_hash,
        "v1_stage_a_collection_safety": stage_a["receipt_sha256"],
        "v1_storage_benchmark": benchmark["receipt_sha256"],
        "v1_storage_budget": budget["receipt_sha256"],
    }
    dynamic = {
        "v1_public_artifact_rehash",
        "v1_tokenizer_endpoints",
        "v1_stage_a_collection_safety",
    }
    rows = [
        {
            "gate_id": gate_id,
            "status": "pass",
            "receipt_sha256": evidence_hashes[gate_id],
            "plan_manifest_sha256": plan_hash,
            "model_forward_count": forward_count if gate_id in dynamic else 0,
            "target_prompt_render_count": 0,
            "target_forward_count": 0,
            "target_outcome_count": 0,
            "prior_outcome_inputs": [],
        }
        for gate_id in controls.TARGET_BLIND_GATE_IDS
    ]
    core = {
        "schema_version": controls.CONTROL_SCHEMA_VERSION,
        "status": "pass",
        "study_id": protocol.STUDY_ID,
        "protocol_version": protocol.PROTOCOL_VERSION,
        "plan_manifest_sha256": plan_hash,
        "gate_records": rows,
        "scientific_gate_statuses": {
            "v1_j_arithmetic_orientation": stage_a["j_orientation_status"],
            "v1_stage_a_global_j_shadow": stage_a["j_shadow_status"],
            "v1_layer50_j_shadow": stage_a["layer50_j_shadow_status"],
            "v1_stage_a_neutral_transport": stage_a[
                "layer50_primary_transport_status"
            ],
            "v1_stage_a_neutral_dose_linearity": stage_a[
                "layer50_linearity_status"
            ],
        },
        "scientific_gate_receipt_sha256s": {
            "v1_j_arithmetic_orientation": stage_a[
                "j_orientation_receipt_sha256"
            ],
            "v1_stage_a_global_j_shadow": stage_a["receipt_sha256"],
            "v1_layer50_j_shadow": stage_a["receipt_sha256"],
            "v1_stage_a_neutral_transport": stage_a["receipt_sha256"],
            "v1_stage_a_neutral_dose_linearity": stage_a["receipt_sha256"],
        },
        "stage_a_receipt_sha256": stage_a["receipt_sha256"],
        "storage_budget_receipt_sha256": budget["receipt_sha256"],
        "target_prompt_render_count": 0,
        "target_forward_count": 0,
        "target_outcome_count": 0,
        "prior_outcome_inputs": [],
    }
    receipt = _sealed(core)
    try:
        return controls.validate_target_blind_gate_receipt(receipt)
    except controls.ControlViolation as exc:
        raise ReceiptBuildError(str(exc)) from exc


def _git(repo_root: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=repo_root,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if completed.returncode != 0:
        raise ReceiptBuildError(
            f"git {' '.join(args)} failed: {completed.stderr.strip()}"
        )
    return completed.stdout.strip()


def _validate_review_receipt(
    value: Mapping[str, Any], *, plan_hash: str, repo_root: Path
) -> dict[str, Any]:
    try:
        return review_closure.validate_review_evidence_receipt(
            value,
            repo_root=repo_root,
            expected_plan_manifest_sha256=plan_hash,
        )
    except review_closure.ReviewAdjudicationError as exc:
        raise ReceiptBuildError(str(exc)) from exc


def build_stage_b_permit(
    *,
    plan_manifest: Mapping[str, Any],
    stage_a_receipt: Mapping[str, Any],
    target_blind_receipt: Mapping[str, Any],
    storage_budget: Mapping[str, Any],
    review_adjudication: Mapping[str, Any],
    repo_root: Path,
    plan_dir: Path,
    source_inventory: Mapping[str, Any],
    remote_ref: str,
    run_id: str,
    spend_ceiling_usd: float,
    walltime_ceiling_seconds: int,
) -> dict[str, Any]:
    """Seal a Stage-B permit from the clean pushed freeze and passing receipts."""

    plan = _validate_plan_manifest(plan_manifest)
    plan_hash = str(plan["plan_manifest_sha256"])
    try:
        stage_a = controls.validate_stage_a_safety_receipt(stage_a_receipt)
        target_blind = controls.validate_target_blind_gate_receipt(target_blind_receipt)
        budget = controls.validate_storage_budget(storage_budget)
    except controls.ControlViolation as exc:
        raise ReceiptBuildError(str(exc)) from exc
    if any(
        value["plan_manifest_sha256"] != plan_hash
        for value in (stage_a, target_blind, budget)
    ):
        raise ReceiptBuildError("Stage-B permit components bind different plans")
    root = repo_root.expanduser().resolve(strict=True)
    review = _validate_review_receipt(
        review_adjudication, plan_hash=plan_hash, repo_root=root
    )
    review_hash = str(review["receipt_sha256"])
    source_rows = source_inventory.get("files")
    if (
        source_inventory.get("study_id") != protocol.STUDY_ID
        or source_inventory.get("protocol_version") != protocol.PROTOCOL_VERSION
        or source_inventory.get("prior_outcome_inputs") != []
        or not isinstance(source_rows, list)
    ):
        raise ReceiptBuildError("source inventory identity differs")
    bound_paths: set[str] = set()
    for row in source_rows:
        if not isinstance(row, Mapping) or not isinstance(row.get("path"), str):
            raise ReceiptBuildError("source inventory row is malformed")
        relative = str(row["path"])
        path = root / relative
        if (
            not path.is_file()
            or path.stat().st_size != int(row.get("bytes", -1))
            or protocol.sha256_file(path) != row.get("sha256")
        ):
            raise ReceiptBuildError(f"bound source differs: {relative}")
        bound_paths.add(relative)
    resolved_plan = plan_dir.expanduser().resolve(strict=True)
    try:
        plan_prefix = resolved_plan.relative_to(root)
    except ValueError as exc:
        raise ReceiptBuildError("plan directory is outside repository") from exc
    for row in plan["files"]:
        candidate = resolved_plan / str(row["path"])
        if (
            not candidate.is_file()
            or candidate.is_symlink()
            or candidate.stat().st_size != int(row["bytes"])
            or protocol.sha256_file(candidate) != row["sha256"]
        ):
            raise ReceiptBuildError(f"plan file differs: {row['path']}")
    source_record = next(
        (row for row in plan["files"] if row["path"] == "source_files.json"), None
    )
    source_bytes = controls.canonical_json_bytes(dict(source_inventory)) + b"\n"
    if (
        source_record is None
        or len(source_bytes) != int(source_record["bytes"])
        or hashlib.sha256(source_bytes).hexdigest() != source_record["sha256"]
    ):
        raise ReceiptBuildError("source inventory is not the plan-bound source_files.json")
    for row in plan["files"]:
        bound_paths.add((plan_prefix / str(row["path"])).as_posix())
    bound_paths.add((plan_prefix / "plan_manifest.json").as_posix())
    bound_paths.update(review_closure.review_evidence_bound_paths(review))
    ordered_bound = sorted(bound_paths)
    scoped_status = _git(
        root,
        "status",
        "--porcelain",
        "--untracked-files=all",
        "--",
        *ordered_bound,
    )
    if scoped_status:
        raise ReceiptBuildError("one or more plan/source bound inputs are dirty or untracked")
    for relative in ordered_bound:
        _git(root, "cat-file", "-e", f"HEAD:{relative}")
    head = _git(root, "rev-parse", "HEAD")
    remote_commit = _git(root, "rev-parse", remote_ref)
    if head != remote_commit:
        raise ReceiptBuildError("HEAD is not the exact pushed remote freeze ref")
    all_status = _git(root, "status", "--porcelain", "--untracked-files=all")
    excluded_paths: list[str] = []
    for line in all_status.splitlines():
        path_text = line[3:]
        if " -> " in path_text:
            path_text = path_text.split(" -> ", 1)[1]
        if path_text and path_text not in bound_paths:
            excluded_paths.append(path_text)
    core = {
        "schema_version": controls.CONTROL_SCHEMA_VERSION,
        "status": "pass",
        "study_id": protocol.STUDY_ID,
        "protocol_version": protocol.PROTOCOL_VERSION,
        "run_id": run_id,
        "plan_manifest_sha256": plan_hash,
        "freeze_commit": head,
        "git_head_commit": head,
        "git_remote_ref": remote_ref,
        "git_remote_commit": remote_commit,
        "bound_input_paths_sha256": controls.canonical_sha256(ordered_bound),
        "bound_inputs_clean": True,
        "excluded_worktree_paths": sorted(set(excluded_paths)),
        "stage_a_receipt_sha256": stage_a["receipt_sha256"],
        "target_blind_receipt_sha256": target_blind["receipt_sha256"],
        "storage_budget_receipt_sha256": budget["receipt_sha256"],
        "independent_review_adjudication_sha256": review_hash,
        "review_status": review["status"],
        "measured_spend_ceiling_usd": float(spend_ceiling_usd),
        "measured_walltime_ceiling_seconds": int(walltime_ceiling_seconds),
        "stage_b_prompt_count": len(protocol.STAGE_B_PROMPT_IDS),
        "paper_prompt_render_count": 0,
        "target_prompt_render_count": 0,
        "target_forward_count": 0,
        "target_outcome_count": 0,
        "prior_outcome_inputs": [],
    }
    receipt = _sealed(core)
    try:
        return controls.validate_stage_b_permit(
            receipt,
            stage_a_receipt=stage_a,
            target_blind_receipt=target_blind,
            storage_budget=budget,
        )
    except controls.ControlViolation as exc:
        raise ReceiptBuildError(str(exc)) from exc


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    storage = commands.add_parser("storage-budget")
    storage.add_argument("--plan-manifest", type=Path, required=True)
    storage.add_argument("--benchmark-receipt", type=Path, required=True)
    storage.add_argument("--ownership-receipt", type=Path, required=True)
    storage.add_argument("--guest-receipt", type=Path, required=True)
    storage.add_argument("--cache-receipt", type=Path, required=True)
    storage.add_argument("--volume-root", type=Path, required=True)
    storage.add_argument("--volume-id", required=True)
    storage.add_argument("--output", type=Path, required=True)

    blind = commands.add_parser("target-blind")
    blind.add_argument("--plan-manifest", type=Path, required=True)
    blind.add_argument("--stage-a-raw-receipt", type=Path, required=True)
    blind.add_argument("--stage-a-receipt", type=Path, required=True)
    blind.add_argument("--benchmark-receipt", type=Path, required=True)
    blind.add_argument("--storage-budget", type=Path, required=True)
    blind.add_argument("--output", type=Path, required=True)

    permit = commands.add_parser("stage-b-permit")
    permit.add_argument("--plan-manifest", type=Path, required=True)
    permit.add_argument("--stage-a-receipt", type=Path, required=True)
    permit.add_argument("--target-blind-receipt", type=Path, required=True)
    permit.add_argument("--storage-budget", type=Path, required=True)
    permit.add_argument("--review-adjudication", type=Path, required=True)
    permit.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    permit.add_argument("--plan-dir", type=Path, required=True)
    permit.add_argument("--source-inventory", type=Path, required=True)
    permit.add_argument("--remote-ref", required=True)
    permit.add_argument("--run-id", required=True)
    permit.add_argument("--spend-ceiling-usd", type=float, required=True)
    permit.add_argument("--walltime-ceiling-seconds", type=int, required=True)
    permit.add_argument("--output", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    plan = _load_json(args.plan_manifest, "plan manifest")
    if args.command == "storage-budget":
        receipt = build_storage_budget(
            plan_manifest=plan,
            benchmark_receipt=_load_json(args.benchmark_receipt, "benchmark receipt"),
            ownership_receipt=_load_json(args.ownership_receipt, "ownership receipt"),
            guest_receipt=_load_json(args.guest_receipt, "guest receipt"),
            cache_receipt=_load_json(args.cache_receipt, "cache receipt"),
            volume_root=args.volume_root,
            volume_id=args.volume_id,
        )
    elif args.command == "target-blind":
        receipt = build_target_blind_receipt(
            plan_manifest=plan,
            stage_a_raw_receipt=_load_json(
                args.stage_a_raw_receipt, "Stage A raw-run receipt"
            ),
            stage_a_receipt=_load_json(args.stage_a_receipt, "Stage A receipt"),
            storage_benchmark=_load_json(args.benchmark_receipt, "benchmark receipt"),
            storage_budget=_load_json(args.storage_budget, "storage budget"),
        )
    else:
        receipt = build_stage_b_permit(
            plan_manifest=plan,
            stage_a_receipt=_load_json(args.stage_a_receipt, "Stage A receipt"),
            target_blind_receipt=_load_json(
                args.target_blind_receipt, "target-blind receipt"
            ),
            storage_budget=_load_json(args.storage_budget, "storage budget"),
            review_adjudication=_load_json(
                args.review_adjudication, "review evidence receipt"
            ),
            repo_root=args.repo_root,
            plan_dir=args.plan_dir,
            source_inventory=_load_json(args.source_inventory, "source inventory"),
            remote_ref=args.remote_ref,
            run_id=args.run_id,
            spend_ceiling_usd=args.spend_ceiling_usd,
            walltime_ceiling_seconds=args.walltime_ceiling_seconds,
        )
    output = _write_receipt(args.output, receipt)
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

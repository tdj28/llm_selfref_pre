#!/usr/bin/env python3
"""Issue and validate one small-model-gated signed-scan authorization."""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import stat
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from experiments.consciousness_sae_realization_validation import runpod_preflight

from . import protocol


REPO_ROOT = Path(__file__).resolve().parents[2]
COMMIT_RE = re.compile(r"[0-9a-f]{40}")
HEX64_RE = re.compile(r"[0-9a-f]{64}")
SAFE_RUN_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")
CONSERVATIVE_RATE_USD_PER_HOUR = float(
    protocol.RESOURCE_LIMITS["conservative_accounting_rate_usd_per_hour"]
)
AUTHORIZATION_FIELDS = frozenset(
    {
        "schema_version",
        "status",
        "study_id",
        "protocol_version",
        "authorized_at_utc",
        "canonical_plan_relative_path",
        "authorized_run_id",
        "plan_manifest_sha256",
        "plan_manifest_file_sha256",
        "source_files_sha256",
        "source_file_inventory_sha256",
        "review_adjudication_relative_path",
        "review_adjudication_sha256",
        "review_adjudication_file_sha256",
        "review_model",
        "review_response_id",
        "small_model_gate_status",
        "small_model_gate_receipt_sha256",
        "small_model_gate_file_sha256",
        "small_model_gate_model_id",
        "small_model_gate_model_revision",
        "small_model_gate_sae_repo",
        "small_model_gate_sae_revision",
        "small_model_gate_sae_folder",
        "small_model_gate_sae_feature_id",
        "small_model_gate_required_gates",
        "small_model_gate_promotion_scope",
        "small_model_gate_grid_sha256",
        "git_head_commit",
        "git_remote_ref",
        "git_live_remote_commit",
        "ownership_receipt_sha256",
        "guest_receipt_sha256",
        "cache_receipt_sha256",
        "pod_id",
        "volume_id",
        "data_center_id",
        "gpu_type",
        "gpu_count",
        "cache_root",
        "model_revision",
        "sae_revision",
        "j_lens_revision",
        "campaign_started_at_unix",
        "campaign_deadline_at_unix",
        "provider_deadline_at_unix",
        "hourly_price_usd",
        "max_spend_usd",
        "max_walltime_seconds",
        "target_prompt_render_count",
        "target_feature_vector_count",
        "analysis_data_inputs",
        "receipt_sha256",
    }
)


class AuthorizationError(RuntimeError):
    pass


def _absolute(path: Path) -> Path:
    return Path(os.path.abspath(path.expanduser()))


def _regular_file(path: Path, label: str) -> Path:
    candidate = _absolute(path)
    try:
        details = candidate.lstat()
    except OSError as exc:
        raise AuthorizationError(f"{label} is missing") from exc
    if not stat.S_ISREG(details.st_mode) or details.st_nlink != 1:
        raise AuthorizationError(f"{label} is not a single-link regular file")
    return candidate


def _json(path: Path, label: str) -> dict[str, Any]:
    candidate = _regular_file(path, label)
    try:
        raw = candidate.read_bytes()
        value = json.loads(raw)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise AuthorizationError(f"{label} is not readable JSON") from exc
    if not isinstance(value, dict):
        raise AuthorizationError(f"{label} is not a JSON object")
    if raw != protocol.canonical_json_bytes(value) + b"\n":
        raise AuthorizationError(f"{label} is not canonical JSON")
    return value


def _self_hash(value: Mapping[str, Any], label: str) -> str:
    core = dict(value)
    supplied = core.pop("receipt_sha256", None)
    if (
        not isinstance(supplied, str)
        or HEX64_RE.fullmatch(supplied) is None
        or supplied != protocol.canonical_sha256(core)
    ):
        raise AuthorizationError(f"{label} self-hash differs")
    return supplied


def _git(*args: str) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode:
        raise AuthorizationError(f"git {' '.join(args)} failed")
    return completed.stdout.strip()


def _live_remote_freeze() -> tuple[str, str, str]:
    head = _git("rev-parse", "HEAD")
    if COMMIT_RE.fullmatch(head) is None:
        raise AuthorizationError("Git HEAD is malformed")
    branch = _git("symbolic-ref", "--short", "HEAD")
    if not branch:
        raise AuthorizationError("detached HEAD cannot authorize execution")
    remote_ref = f"refs/heads/{branch}"
    live = _git("ls-remote", "origin", remote_ref).splitlines()
    if len(live) != 1:
        raise AuthorizationError("live remote branch is missing or ambiguous")
    live_commit, separator, observed_ref = live[0].partition("\t")
    if separator != "\t" or observed_ref != remote_ref or live_commit != head:
        raise AuthorizationError("local HEAD differs from the live remote")
    return head, remote_ref, live_commit


def _plan(plan_dir: Path) -> tuple[dict[str, Any], dict[str, Any], Path, Path]:
    root = _absolute(plan_dir)
    if root != _absolute(REPO_ROOT / protocol.CANONICAL_PLAN_RELATIVE_PATH):
        raise AuthorizationError("plan directory differs from canonical path")
    manifest_path = _regular_file(root / "plan_manifest.json", "plan manifest")
    source_path = _regular_file(root / "source_files.json", "source inventory")
    manifest = _json(manifest_path, "plan manifest")
    core = dict(manifest)
    supplied = core.pop("plan_manifest_sha256", None)
    if supplied != protocol.canonical_sha256(core):
        raise AuthorizationError("plan manifest self-hash differs")
    source = _json(source_path, "source inventory")
    if set(source) != {"files"} or not isinstance(source["files"], list):
        raise AuthorizationError("source inventory schema differs")
    if (
        manifest.get("study_id") != protocol.STUDY_ID
        or manifest.get("protocol_version") != protocol.PROTOCOL_VERSION
        or manifest.get("canonical_plan_relative_path")
        != protocol.CANONICAL_PLAN_RELATIVE_PATH
        or manifest.get("analysis_data_inputs") != []
        or manifest.get("target_feature_vector_count") != 0
    ):
        raise AuthorizationError("plan identity differs")
    for row in source["files"]:
        if not isinstance(row, Mapping):
            raise AuthorizationError("source inventory row differs")
        path = _regular_file(REPO_ROOT / str(row.get("path")), "bound source")
        if (
            path.stat().st_size != row.get("bytes")
            or protocol.sha256_file(path) != row.get("sha256")
        ):
            raise AuthorizationError("bound source bytes differ")
    return manifest, source, manifest_path, source_path


def _review(
    path: Path, *, plan_manifest_sha256: str
) -> tuple[dict[str, Any], Path]:
    candidate = _regular_file(path, "review adjudication")
    review = _json(candidate, "review adjudication")
    _self_hash(review, "review adjudication")
    if (
        review.get("schema_version") != 1
        or review.get("status") != "adjudicated_ready_to_execute"
        or review.get("review_model") != "gpt-5.6-sol"
        or review.get("review_mode") != "pro"
        or review.get("final_plan_manifest_sha256") != plan_manifest_sha256
        or review.get("unresolved_blockers") != []
        or not isinstance(review.get("review_response_id"), str)
        or not review["review_response_id"]
    ):
        raise AuthorizationError("review adjudication is not execution-ready")
    return review, candidate


def _small_gate(path: Path) -> tuple[dict[str, Any], Path]:
    candidate = _regular_file(path, "small-model promotion gate")
    gate = _json(candidate, "small-model promotion gate")
    _self_hash(gate, "small-model promotion gate")
    expected_grid_hash = protocol.canonical_sha256(list(protocol.DOSE_BASIS_POINTS))
    expected = protocol.SMALL_MODEL_PROMOTION_SPEC
    if (
        gate.get("status") != "pass_small_model_promotion_gate"
        or gate.get("dose_basis_points_sha256") != expected_grid_hash
        or gate.get("nonzero_dose_count") != expected["nonzero_dose_count"]
        or gate.get("signed_pair_count") != expected["signed_pair_count"]
        or gate.get("edited_forward_count") != expected["edited_forward_count"]
        or gate.get("zero_baseline_count") != expected["zero_baseline_count"]
        or gate.get("model_id") != expected["model_id"]
        or gate.get("model_revision") != expected["model_revision"]
        or gate.get("sae_repo") != expected["sae_repo"]
        or gate.get("sae_revision") != expected["sae_revision"]
        or gate.get("sae_folder") != expected["sae_folder"]
        or gate.get("sae_feature_id") != expected["sae_feature_id"]
        or gate.get("required_gates") != expected["required_gates"]
        or gate.get("promotion_scope") != expected["promotion_scope"]
    ):
        raise AuthorizationError("small-model promotion gate differs")
    return gate, candidate


def _component_revisions(cache: Mapping[str, Any]) -> dict[str, str]:
    rows = cache.get("components")
    if not isinstance(rows, list):
        raise AuthorizationError("cache component inventory is absent")
    observed = {
        str(row.get("component")): str(row.get("revision"))
        for row in rows
        if isinstance(row, Mapping)
    }
    expected = {
        "model": str(protocol.MODEL_SPEC["revision"]),
        "sae": str(protocol.SAE_SPEC["revision"]),
        "j_lens": str(protocol.J_LENS_SPEC["revision"]),
    }
    if observed != expected:
        raise AuthorizationError("cache component revisions differ")
    return observed


def authorize(
    *,
    plan_dir: Path,
    ownership_path: Path,
    guest_path: Path,
    cache_path: Path,
    review_adjudication_path: Path,
    small_model_gate_path: Path,
    run_id: str,
    hourly_price_usd: float,
    now: datetime | None = None,
) -> dict[str, Any]:
    if SAFE_RUN_ID_RE.fullmatch(run_id) is None:
        raise AuthorizationError("authorized run ID is unsafe")
    manifest, source, manifest_path, source_path = _plan(plan_dir)
    ownership_raw = _json(ownership_path, "ownership receipt")
    guest_raw = _json(guest_path, "guest receipt")
    cache_raw = _json(cache_path, "cache receipt")
    try:
        ownership = runpod_preflight.validate_ownership_receipt(ownership_raw)
        guest = runpod_preflight.validate_guest_receipt(
            guest_raw, ownership_receipt=ownership
        )
        cache = runpod_preflight.validate_cache_receipt(
            cache_raw, guest_receipt=guest, ownership_receipt=ownership
        )
    except runpod_preflight.PreflightError as exc:
        raise AuthorizationError("provider/cache receipt chain failed") from exc
    if (
        ownership.get("network_volume_id") != protocol.NETWORK_VOLUME_ID
        or ownership.get("data_center_id") != protocol.DATA_CENTER_ID
        or ownership.get("gpu_type") != protocol.GPU_TYPE
        or ownership.get("gpu_count") != 1
    ):
        raise AuthorizationError("owned RunPod resource differs")
    revisions = _component_revisions(cache)
    review, review_path = _review(
        review_adjudication_path,
        plan_manifest_sha256=str(manifest["plan_manifest_sha256"]),
    )
    gate, gate_path = _small_gate(small_model_gate_path)
    head, remote_ref, live_commit = _live_remote_freeze()
    dirty = _git(
        "status",
        "--porcelain=v1",
        "--untracked-files=all",
        "--",
        *[str(row["path"]) for row in source["files"]],
        protocol.CANONICAL_PLAN_RELATIVE_PATH,
        str(review_path.relative_to(REPO_ROOT)),
    )
    if dirty:
        raise AuthorizationError("frozen plan/review inputs differ from Git HEAD")
    current = now or datetime.now(timezone.utc)
    started = current.timestamp()
    walltime = int(protocol.RESOURCE_LIMITS["max_walltime_seconds"])
    deadline = started + walltime
    terminate_after = datetime.fromisoformat(
        str(ownership["terminate_after"]).replace("Z", "+00:00")
    ).timestamp()
    if deadline >= terminate_after:
        raise AuthorizationError("campaign window exceeds provider watchdog")
    if (
        not math.isfinite(hourly_price_usd)
        or float(hourly_price_usd) != CONSERVATIVE_RATE_USD_PER_HOUR
        or hourly_price_usd * walltime / 3600
        != protocol.RESOURCE_LIMITS["max_spend_usd"]
    ):
        raise AuthorizationError("authorization must use the frozen $6/hour rate")
    review_relative = review_path.relative_to(REPO_ROOT).as_posix()
    core = {
        "schema_version": 1,
        "status": "authorized",
        "study_id": protocol.STUDY_ID,
        "protocol_version": protocol.PROTOCOL_VERSION,
        "authorized_at_utc": current.isoformat().replace("+00:00", "Z"),
        "canonical_plan_relative_path": protocol.CANONICAL_PLAN_RELATIVE_PATH,
        "authorized_run_id": run_id,
        "plan_manifest_sha256": manifest["plan_manifest_sha256"],
        "plan_manifest_file_sha256": protocol.sha256_file(manifest_path),
        "source_files_sha256": protocol.sha256_file(source_path),
        "source_file_inventory_sha256": protocol.canonical_sha256(source["files"]),
        "review_adjudication_relative_path": review_relative,
        "review_adjudication_sha256": review["receipt_sha256"],
        "review_adjudication_file_sha256": protocol.sha256_file(review_path),
        "review_model": review["review_model"],
        "review_response_id": review["review_response_id"],
        "small_model_gate_status": gate["status"],
        "small_model_gate_receipt_sha256": gate["receipt_sha256"],
        "small_model_gate_file_sha256": protocol.sha256_file(gate_path),
        "small_model_gate_model_id": gate["model_id"],
        "small_model_gate_model_revision": gate["model_revision"],
        "small_model_gate_sae_repo": gate["sae_repo"],
        "small_model_gate_sae_revision": gate["sae_revision"],
        "small_model_gate_sae_folder": gate["sae_folder"],
        "small_model_gate_sae_feature_id": gate["sae_feature_id"],
        "small_model_gate_required_gates": gate["required_gates"],
        "small_model_gate_promotion_scope": gate["promotion_scope"],
        "small_model_gate_grid_sha256": gate["dose_basis_points_sha256"],
        "git_head_commit": head,
        "git_remote_ref": remote_ref,
        "git_live_remote_commit": live_commit,
        "ownership_receipt_sha256": ownership["receipt_sha256"],
        "guest_receipt_sha256": guest["receipt_sha256"],
        "cache_receipt_sha256": cache["receipt_sha256"],
        "pod_id": ownership["pod_id"],
        "volume_id": protocol.NETWORK_VOLUME_ID,
        "data_center_id": protocol.DATA_CENTER_ID,
        "gpu_type": protocol.GPU_TYPE,
        "gpu_count": 1,
        "cache_root": cache["cache_root"],
        "model_revision": revisions["model"],
        "sae_revision": revisions["sae"],
        "j_lens_revision": revisions["j_lens"],
        "campaign_started_at_unix": started,
        "campaign_deadline_at_unix": deadline,
        "provider_deadline_at_unix": terminate_after,
        "hourly_price_usd": CONSERVATIVE_RATE_USD_PER_HOUR,
        "max_spend_usd": protocol.RESOURCE_LIMITS["max_spend_usd"],
        "max_walltime_seconds": walltime,
        "target_prompt_render_count": 0,
        "target_feature_vector_count": 0,
        "analysis_data_inputs": [],
    }
    return {**core, "receipt_sha256": protocol.canonical_sha256(core)}


def validate_execution_authorization(
    receipt: Mapping[str, Any],
    *,
    plan: Mapping[str, Any],
    plan_manifest_path: Path,
    source_files_path: Path,
    ownership: Mapping[str, Any],
    guest: Mapping[str, Any],
    cache: Mapping[str, Any],
    now_unix: float | None = None,
) -> dict[str, Any]:
    if set(receipt) != AUTHORIZATION_FIELDS:
        raise AuthorizationError("execution authorization schema differs")
    _self_hash(receipt, "execution authorization")
    observed = time.time() if now_unix is None else float(now_unix)
    started = float(receipt["campaign_started_at_unix"])
    deadline = float(receipt["campaign_deadline_at_unix"])
    if (
        receipt.get("status") != "authorized"
        or receipt.get("study_id") != protocol.STUDY_ID
        or receipt.get("protocol_version") != protocol.PROTOCOL_VERSION
        or receipt.get("canonical_plan_relative_path")
        != protocol.CANONICAL_PLAN_RELATIVE_PATH
        or SAFE_RUN_ID_RE.fullmatch(str(receipt.get("authorized_run_id", "")))
        is None
        or receipt.get("plan_manifest_sha256") != plan.get("plan_manifest_sha256")
        or receipt.get("plan_manifest_file_sha256")
        != protocol.sha256_file(_regular_file(plan_manifest_path, "plan manifest"))
        or receipt.get("source_files_sha256")
        != protocol.sha256_file(_regular_file(source_files_path, "source inventory"))
        or receipt.get("ownership_receipt_sha256") != ownership.get("receipt_sha256")
        or receipt.get("guest_receipt_sha256") != guest.get("receipt_sha256")
        or receipt.get("cache_receipt_sha256") != cache.get("receipt_sha256")
        or receipt.get("pod_id") != ownership.get("pod_id")
        or receipt.get("volume_id") != protocol.NETWORK_VOLUME_ID
        or receipt.get("data_center_id") != protocol.DATA_CENTER_ID
        or receipt.get("gpu_type") != protocol.GPU_TYPE
        or receipt.get("gpu_count") != 1
        or receipt.get("cache_root") != cache.get("cache_root")
        or receipt.get("model_revision") != protocol.MODEL_SPEC["revision"]
        or receipt.get("sae_revision") != protocol.SAE_SPEC["revision"]
        or receipt.get("j_lens_revision") != protocol.J_LENS_SPEC["revision"]
        or receipt.get("small_model_gate_status")
        != "pass_small_model_promotion_gate"
        or receipt.get("small_model_gate_grid_sha256")
        != protocol.canonical_sha256(list(protocol.DOSE_BASIS_POINTS))
        or receipt.get("small_model_gate_model_id")
        != protocol.SMALL_MODEL_PROMOTION_SPEC["model_id"]
        or receipt.get("small_model_gate_model_revision")
        != protocol.SMALL_MODEL_PROMOTION_SPEC["model_revision"]
        or receipt.get("small_model_gate_sae_repo")
        != protocol.SMALL_MODEL_PROMOTION_SPEC["sae_repo"]
        or receipt.get("small_model_gate_sae_revision")
        != protocol.SMALL_MODEL_PROMOTION_SPEC["sae_revision"]
        or receipt.get("small_model_gate_sae_folder")
        != protocol.SMALL_MODEL_PROMOTION_SPEC["sae_folder"]
        or receipt.get("small_model_gate_sae_feature_id")
        != protocol.SMALL_MODEL_PROMOTION_SPEC["sae_feature_id"]
        or receipt.get("small_model_gate_required_gates")
        != protocol.SMALL_MODEL_PROMOTION_SPEC["required_gates"]
        or receipt.get("small_model_gate_promotion_scope")
        != protocol.SMALL_MODEL_PROMOTION_SPEC["promotion_scope"]
        or HEX64_RE.fullmatch(str(receipt.get("small_model_gate_receipt_sha256", "")))
        is None
        or HEX64_RE.fullmatch(str(receipt.get("small_model_gate_file_sha256", "")))
        is None
        or receipt.get("review_model") != "gpt-5.6-sol"
        or receipt.get("hourly_price_usd") != CONSERVATIVE_RATE_USD_PER_HOUR
        or receipt.get("max_spend_usd") != protocol.RESOURCE_LIMITS["max_spend_usd"]
        or receipt.get("max_walltime_seconds")
        != protocol.RESOURCE_LIMITS["max_walltime_seconds"]
        or deadline - started != protocol.RESOURCE_LIMITS["max_walltime_seconds"]
        or not started <= observed < deadline
        or receipt.get("target_prompt_render_count") != 0
        or receipt.get("target_feature_vector_count") != 0
        or receipt.get("analysis_data_inputs") != []
    ):
        raise AuthorizationError("execution authorization binding differs")
    _component_revisions(cache)
    return dict(receipt)


def _write(path: Path, value: Mapping[str, Any]) -> None:
    output = _absolute(path)
    if os.path.lexists(output):
        raise AuthorizationError("authorization output must be fresh")
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("xb") as handle:
        handle.write(protocol.canonical_json_bytes(dict(value)) + b"\n")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan-dir", type=Path, required=True)
    parser.add_argument("--ownership", type=Path, required=True)
    parser.add_argument("--guest", type=Path, required=True)
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--review-adjudication", type=Path, required=True)
    parser.add_argument("--small-model-gate", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--hourly-price-usd", type=float, default=6.0)
    parser.add_argument("--output", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    receipt = authorize(
        plan_dir=args.plan_dir,
        ownership_path=args.ownership,
        guest_path=args.guest,
        cache_path=args.cache,
        review_adjudication_path=args.review_adjudication,
        small_model_gate_path=args.small_model_gate,
        run_id=args.run_id,
        hourly_price_usd=args.hourly_price_usd,
    )
    _write(args.output, receipt)
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

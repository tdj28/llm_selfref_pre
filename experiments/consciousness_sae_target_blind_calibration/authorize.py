#!/usr/bin/env python3
"""Issue the final clean/pushed, receipt-bound calibration authorization."""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import stat
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Mapping, Sequence

from experiments.consciousness_sae_realization_validation import runpod_preflight
from experiments.consciousness_sae_target_blind_calibration import (
    build_plan,
    protocol,
    review_adjudication,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
COMMIT_RE = re.compile(r"[0-9a-f]{40}")
HEX64_RE = re.compile(r"[0-9a-f]{64}")
PLAN_FILES = frozenset(build_plan.PLAN_FILE_NAMES)
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
        "plan_manifest_sha256",
        "plan_manifest_file_sha256",
        "source_files_sha256",
        "source_file_inventory_sha256",
        "review_adjudication_sha256",
        "review_adjudication_file_sha256",
        "review_adjudication_relative_path",
        "review_model",
        "git_head_commit",
        "git_remote_ref",
        "git_local_remote_ref",
        "git_local_remote_commit",
        "git_live_remote_commit",
        "bound_input_count",
        "bound_input_paths_sha256",
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


def _require_no_symlink_components(path: Path, label: str) -> None:
    candidate = _absolute(path)
    current = Path(candidate.anchor)
    for part in candidate.parts[1:]:
        current = current / part
        if current.is_symlink():
            raise AuthorizationError(f"{label} contains a symlink component")


def _regular_file(path: Path, label: str) -> Path:
    candidate = _absolute(path)
    _require_no_symlink_components(candidate, label)
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
        raise AuthorizationError(f"{label} JSON root is not an object")
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


def _safe_relative(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value or "\\" in value:
        raise AuthorizationError(f"{label} is not repository-relative")
    path = PurePosixPath(value)
    if (
        path.is_absolute()
        or path.as_posix() != value
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        raise AuthorizationError(f"{label} is not repository-relative")
    return value


def _repo_relative(path: Path, label: str) -> str:
    candidate = _regular_file(path, label)
    try:
        return candidate.relative_to(REPO_ROOT).as_posix()
    except ValueError as exc:
        raise AuthorizationError(f"{label} is outside the repository") from exc


def _utc(value: str, label: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise AuthorizationError(f"{label} is not canonical UTC")
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise AuthorizationError(f"{label} is not parseable UTC") from exc
    if result.tzinfo is None or result.utcoffset() is None:
        raise AuthorizationError(f"{label} is timezone-naive")
    return result.astimezone(timezone.utc)


def _utc_text(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise AuthorizationError("authorization clock is timezone-naive")
    return (
        value.astimezone(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _git(*args: str) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        raise AuthorizationError(
            f"git {' '.join(args)} failed: {completed.stderr.strip()}"
        )
    return completed.stdout.strip()


def _validate_plan(plan_dir: Path) -> dict[str, Any]:
    plan_root = _absolute(plan_dir)
    _require_no_symlink_components(plan_root, "plan directory")
    if not plan_root.is_dir():
        raise AuthorizationError("plan directory is missing")
    try:
        plan_prefix = plan_root.relative_to(REPO_ROOT)
    except ValueError as exc:
        raise AuthorizationError("plan directory is outside the repository") from exc
    if plan_prefix.as_posix() != protocol.CANONICAL_PLAN_RELATIVE_PATH:
        raise AuthorizationError(
            "plan directory differs from the canonical relative path"
        )
    manifest_path = _regular_file(plan_root / "plan_manifest.json", "plan manifest")
    manifest = _json(manifest_path, "plan manifest")
    manifest_core = dict(manifest)
    supplied_plan_hash = manifest_core.pop("plan_manifest_sha256", None)
    if (
        not isinstance(supplied_plan_hash, str)
        or HEX64_RE.fullmatch(supplied_plan_hash) is None
        or supplied_plan_hash != protocol.canonical_sha256(manifest_core)
    ):
        raise AuthorizationError("plan manifest self-hash differs")
    if (
        manifest.get("schema_version") != protocol.PLAN_SCHEMA_VERSION
        or manifest.get("study_id") != protocol.STUDY_ID
        or manifest.get("protocol_version") != protocol.PROTOCOL_VERSION
        or manifest.get("canonical_plan_relative_path")
        != protocol.CANONICAL_PLAN_RELATIVE_PATH
        or manifest.get("scope") != "adaptive_target_blind_numerical_calibration_only"
        or manifest.get("paper_prompt_render_count") != 0
        or manifest.get("target_prompt_render_count") != 0
        or manifest.get("target_feature_vector_count") != 0
        or manifest.get("analysis_data_inputs") != []
        or COMMIT_RE.fullmatch(str(manifest.get("git_head_commit", ""))) is None
    ):
        raise AuthorizationError("plan identity/scope differs")
    rows = manifest.get("files")
    if (
        not isinstance(rows, list)
        or len(rows) != len(PLAN_FILES)
        or {row.get("path") for row in rows if isinstance(row, Mapping)} != PLAN_FILES
    ):
        raise AuthorizationError("plan file inventory differs")
    bound_paths = {(plan_prefix / "plan_manifest.json").as_posix()}
    for row in rows:
        if not isinstance(row, Mapping) or set(row) != {"path", "bytes", "sha256"}:
            raise AuthorizationError("plan file row schema differs")
        relative = _safe_relative(row["path"], "plan file")
        if len(PurePosixPath(relative).parts) != 1:
            raise AuthorizationError("plan file is not at the plan root")
        path = _regular_file(plan_root / relative, f"plan file {relative}")
        if (
            isinstance(row["bytes"], bool)
            or not isinstance(row["bytes"], int)
            or row["bytes"] < 0
            or path.stat().st_size != row["bytes"]
            or protocol.sha256_file(path) != row["sha256"]
        ):
            raise AuthorizationError(f"plan file differs: {relative}")
        bound_paths.add((plan_prefix / relative).as_posix())
    source_path = _regular_file(plan_root / "source_files.json", "source inventory")
    source = _json(source_path, "source inventory")
    source_rows = source.get("files")
    if (
        set(source) != {"files"}
        or not isinstance(source_rows, list)
        or len(source_rows) != len(build_plan.SOURCE_PATHS)
        or tuple(row.get("path") for row in source_rows if isinstance(row, Mapping))
        != build_plan.SOURCE_PATHS
    ):
        raise AuthorizationError("bound source closure differs")
    observed_sources: set[str] = set()
    for row in source_rows:
        if not isinstance(row, Mapping) or set(row) != {"path", "bytes", "sha256"}:
            raise AuthorizationError("bound source row schema differs")
        relative = _safe_relative(row["path"], "bound source")
        if relative in observed_sources:
            raise AuthorizationError("bound source path is duplicated")
        path = _regular_file(REPO_ROOT / relative, f"bound source {relative}")
        if (
            isinstance(row["bytes"], bool)
            or not isinstance(row["bytes"], int)
            or row["bytes"] < 0
            or path.stat().st_size != row["bytes"]
            or protocol.sha256_file(path) != row["sha256"]
        ):
            raise AuthorizationError(f"bound source differs: {relative}")
        observed_sources.add(relative)
        bound_paths.add(relative)
    return {
        "root": plan_root,
        "manifest": manifest,
        "manifest_path": manifest_path,
        "source": source,
        "source_path": source_path,
        "canonical_plan_relative_path": plan_prefix.as_posix(),
        "bound_paths": bound_paths,
    }


def _live_remote_freeze() -> dict[str, str]:
    head = _git("rev-parse", "--verify", "HEAD")
    branch = _git("symbolic-ref", "--quiet", "--short", "HEAD")
    _git("check-ref-format", "--branch", branch)
    live_ref = f"refs/heads/{branch}"
    local_ref = f"refs/remotes/origin/{branch}"
    local_commit = _git("rev-parse", "--verify", local_ref)
    rows = _git("ls-remote", "--exit-code", "origin", live_ref).splitlines()
    if len(rows) != 1:
        raise AuthorizationError("live remote branch lookup differs")
    fields = rows[0].split()
    if len(fields) != 2 or fields[1] != live_ref:
        raise AuthorizationError("live remote branch response differs")
    live_commit = fields[0]
    if (
        any(
            COMMIT_RE.fullmatch(value) is None
            for value in (head, local_commit, live_commit)
        )
        or head != local_commit
        or head != live_commit
    ):
        raise AuthorizationError(
            "HEAD, local origin tracking ref, and live origin branch differ"
        )
    return {
        "git_head_commit": head,
        "git_remote_ref": live_ref,
        "git_local_remote_ref": local_ref,
        "git_local_remote_commit": local_commit,
        "git_live_remote_commit": live_commit,
    }


def _verify_committed_paths(paths: Sequence[str]) -> tuple[str, ...]:
    ordered = tuple(sorted(set(paths)))
    if not ordered:
        raise AuthorizationError("final freeze has no bound inputs")
    dirty = _git(
        "status",
        "--porcelain=v1",
        "--untracked-files=all",
        "--",
        *ordered,
    )
    if dirty:
        raise AuthorizationError("plan-defining paths differ from pushed HEAD")
    for relative in ordered:
        safe = _safe_relative(relative, "final bound input")
        _regular_file(REPO_ROOT / safe, f"final bound input {safe}")
        stage = _git("ls-files", "--stage", "--", safe).splitlines()
        if len(stage) != 1:
            raise AuthorizationError(f"bound input is not singly tracked: {safe}")
        metadata, separator, tracked_path = stage[0].partition("\t")
        fields = metadata.split()
        if (
            separator != "\t"
            or tracked_path != safe
            or len(fields) != 3
            or fields[0] not in {"100644", "100755"}
            or fields[2] != "0"
        ):
            raise AuthorizationError(f"bound input Git mode/stage differs: {safe}")
        index_blob = fields[1]
        worktree_blob = _git("hash-object", "--no-filters", "--", safe)
        head_blob = _git("rev-parse", f"HEAD:{safe}")
        if index_blob != worktree_blob or index_blob != head_blob:
            raise AuthorizationError(f"bound input bytes differ from HEAD: {safe}")
    return ordered


def _validated_component_revisions(cache: Mapping[str, Any]) -> dict[str, str]:
    rows = cache.get("components")
    if not isinstance(rows, list):
        raise AuthorizationError("cache component inventory is missing")
    revisions = {
        str(row.get("component")): str(row.get("revision"))
        for row in rows
        if isinstance(row, Mapping)
    }
    expected = {
        "model": str(protocol.MODEL_SPEC["revision"]),
        "sae": str(protocol.SAE_SPEC["revision"]),
        "j_lens": str(protocol.J_LENS_SPEC["revision"]),
    }
    if revisions != expected:
        raise AuthorizationError("cache model/SAE/J-lens revisions differ")
    return revisions


def _physical_plan_evidence(
    relative_root: str, label: str
) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]], set[str]]:
    safe_root = _safe_relative(relative_root, f"{label} root")
    root = _absolute(REPO_ROOT / safe_root)
    _require_no_symlink_components(root, f"{label} root")
    if not root.is_dir():
        raise AuthorizationError(f"{label} root is missing")
    manifest_path = _regular_file(root / "plan_manifest.json", f"{label} manifest")
    manifest = _json(manifest_path, f"{label} manifest")
    core = dict(manifest)
    supplied = core.pop("plan_manifest_sha256", None)
    if supplied != protocol.canonical_sha256(core):
        raise AuthorizationError(f"{label} manifest self-hash differs")
    rows = manifest.get("files")
    if not isinstance(rows, list):
        raise AuthorizationError(f"{label} plan inventory is missing")
    paths = {(PurePosixPath(safe_root) / "plan_manifest.json").as_posix()}
    inventory = []
    for row in rows:
        if not isinstance(row, Mapping) or set(row) != {"path", "bytes", "sha256"}:
            raise AuthorizationError(f"{label} plan row schema differs")
        name = _safe_relative(row.get("path"), f"{label} plan file")
        if len(PurePosixPath(name).parts) != 1:
            raise AuthorizationError(f"{label} plan file is not at the plan root")
        path = _regular_file(root / name, f"{label} plan file")
        if (
            isinstance(row.get("bytes"), bool)
            or not isinstance(row.get("bytes"), int)
            or path.stat().st_size != row["bytes"]
            or protocol.sha256_file(path) != row.get("sha256")
        ):
            raise AuthorizationError(f"{label} plan file differs: {name}")
        inventory.append(dict(row))
        paths.add((PurePosixPath(safe_root) / name).as_posix())
    inventory.append(
        {
            "path": "plan_manifest.json",
            "bytes": manifest_path.stat().st_size,
            "sha256": protocol.sha256_file(manifest_path),
        }
    )
    inventory.sort(key=lambda row: str(row["path"]))
    source_path = _regular_file(root / "source_files.json", f"{label} source inventory")
    source = _json(source_path, f"{label} source inventory")
    if set(source) != {"files"} or not isinstance(source.get("files"), list):
        raise AuthorizationError(f"{label} source inventory schema differs")
    audit_path = _regular_file(
        root / "INDEPENDENT_PLAN_AUDIT.json", f"{label} independent plan audit"
    )
    audit = _json(audit_path, f"{label} independent plan audit")
    _self_hash(audit, f"{label} independent plan audit")
    if audit.get("plan_manifest_sha256") != supplied:
        raise AuthorizationError(f"{label} independent plan audit binding differs")
    paths.add((PurePosixPath(safe_root) / "INDEPENDENT_PLAN_AUDIT.json").as_posix())
    return manifest, source, inventory, paths


def _validate_review_adjudication(
    review: Mapping[str, Any],
    *,
    review_path: Path,
    final_plan_manifest_sha256: str,
) -> tuple[dict[str, Any], tuple[str, ...]]:
    relative = _repo_relative(review_path, "review adjudication")
    try:
        validated = review_adjudication.validate_adjudication_receipt(
            review,
            final_plan_manifest_sha256=final_plan_manifest_sha256,
            final_plan_relative_path=protocol.CANONICAL_PLAN_RELATIVE_PATH,
        )
        bound = review_adjudication.bound_paths(validated)
    except review_adjudication.ReviewAdjudicationError as exc:
        raise AuthorizationError(f"review adjudication failed: {exc}") from exc
    if relative != validated.get("receipt_path"):
        raise AuthorizationError("review adjudication path differs")
    attempts = validated["review_attempts"]
    for row in attempts:
        summary_relative = _safe_relative(
            row.get("summary_relative_path"), "review summary path"
        )
        summary = _regular_file(REPO_ROOT / summary_relative, "review summary")
        if protocol.sha256_file(summary) != row.get("summary_file_sha256"):
            raise AuthorizationError("review summary file hash differs")
    if set(bound) != {
        relative,
        *(str(row["summary_relative_path"]) for row in attempts),
    }:
        raise AuthorizationError("review evidence path inventory differs")
    r2_root = str(validated["r2_candidate"]["canonical_plan_directory"])
    r2_manifest, r2_source, r2_inventory, r2_paths = _physical_plan_evidence(
        r2_root, "r2 reviewed candidate"
    )
    r3_manifest, r3_source, r3_inventory, r3_paths = _physical_plan_evidence(
        protocol.CANONICAL_PLAN_RELATIVE_PATH, "r3 final plan"
    )
    r2 = validated["r2_candidate"]
    r3 = validated["r3_final"]
    r3_audit_path = _regular_file(
        REPO_ROOT
        / protocol.CANONICAL_PLAN_RELATIVE_PATH
        / "INDEPENDENT_PLAN_AUDIT.json",
        "r3 independent plan audit",
    )
    r3_audit = _json(r3_audit_path, "r3 independent plan audit")
    if (
        r2_manifest.get("plan_manifest_sha256") != r2.get("plan_manifest_sha256")
        or protocol.sha256_file(REPO_ROOT / r2_root / "plan_manifest.json")
        != r2.get("plan_manifest_file_sha256")
        or protocol.sha256_file(REPO_ROOT / r2_root / "source_files.json")
        != r2.get("source_inventory_file_sha256")
        or protocol.canonical_sha256(r2_source["files"])
        != r2.get("source_file_inventory_sha256")
        or validated.get("candidate_source_inventory") != r2_source["files"]
        or validated.get("candidate_plan_inventory") != r2_inventory
        or r3_manifest.get("plan_manifest_sha256") != r3.get("plan_manifest_sha256")
        or r3_manifest.get("git_head_commit") != r3.get("git_head_commit")
        or protocol.sha256_file(
            REPO_ROOT / protocol.CANONICAL_PLAN_RELATIVE_PATH / "plan_manifest.json"
        )
        != r3.get("plan_manifest_file_sha256")
        or protocol.sha256_file(
            REPO_ROOT / protocol.CANONICAL_PLAN_RELATIVE_PATH / "source_files.json"
        )
        != r3.get("source_inventory_file_sha256")
        or protocol.canonical_sha256(r3_source["files"])
        != r3.get("source_file_inventory_sha256")
        or validated.get("final_source_inventory") != r3_source["files"]
        or validated.get("final_plan_inventory") != r3_inventory
        or r3_audit.get("receipt_sha256") != r3.get("independent_plan_audit_sha256")
        or protocol.sha256_file(r3_audit_path)
        != r3.get("independent_plan_audit_file_sha256")
        or r3_audit.get("plan_manifest_sha256")
        != r3_manifest.get("plan_manifest_sha256")
    ):
        raise AuthorizationError("physical candidate/final review lineage differs")
    return validated, tuple(sorted({*bound, *r2_paths, *r3_paths}))


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
    """Validate sealed final-freeze evidence on the Git-less GPU guest."""

    if not isinstance(receipt, Mapping) or set(receipt) != AUTHORIZATION_FIELDS:
        raise AuthorizationError("execution authorization schema differs")
    _self_hash(receipt, "execution authorization")
    if (
        receipt.get("schema_version") != 1
        or receipt.get("status") != "authorized"
        or receipt.get("study_id") != protocol.STUDY_ID
        or receipt.get("protocol_version") != protocol.PROTOCOL_VERSION
        or receipt.get("canonical_plan_relative_path")
        != protocol.CANONICAL_PLAN_RELATIVE_PATH
        or plan.get("canonical_plan_relative_path")
        != protocol.CANONICAL_PLAN_RELATIVE_PATH
        or receipt.get("plan_manifest_sha256") != plan.get("plan_manifest_sha256")
        or receipt.get("plan_manifest_file_sha256")
        != protocol.sha256_file(_regular_file(plan_manifest_path, "plan manifest"))
        or receipt.get("source_files_sha256")
        != protocol.sha256_file(_regular_file(source_files_path, "source inventory"))
        or receipt.get("git_head_commit") != receipt.get("git_local_remote_commit")
        or receipt.get("git_head_commit") != receipt.get("git_live_remote_commit")
        or COMMIT_RE.fullmatch(str(receipt.get("git_head_commit", ""))) is None
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
        or receipt.get("hourly_price_usd") != CONSERVATIVE_RATE_USD_PER_HOUR
        or receipt.get("max_spend_usd") != protocol.RESOURCE_LIMITS["max_spend_usd"]
        or receipt.get("max_walltime_seconds")
        != protocol.RESOURCE_LIMITS["max_walltime_seconds"]
        or receipt.get("target_prompt_render_count") != 0
        or receipt.get("target_feature_vector_count") != 0
        or receipt.get("analysis_data_inputs") != []
    ):
        raise AuthorizationError("execution authorization binding differs")
    _validated_component_revisions(cache)
    source_value = _json(source_files_path, "source inventory")
    source_inventory = source_value.get("files")
    if not isinstance(source_inventory, list) or receipt.get(
        "source_file_inventory_sha256"
    ) != protocol.canonical_sha256(source_inventory):
        raise AuthorizationError("authorization source inventory differs")
    try:
        plan_root = _absolute(plan_manifest_path).parent
        plan_prefix = plan_root.relative_to(REPO_ROOT)
    except ValueError as exc:
        raise AuthorizationError(
            "execution plan is outside the source archive"
        ) from exc
    if plan_prefix.as_posix() != protocol.CANONICAL_PLAN_RELATIVE_PATH:
        raise AuthorizationError(
            "execution plan differs from the canonical relative path"
        )
    review_relative = _safe_relative(
        receipt.get("review_adjudication_relative_path"),
        "review adjudication path",
    )
    review_path = _regular_file(REPO_ROOT / review_relative, "review adjudication")
    review = _json(review_path, "review adjudication")
    validated_review, review_bound_paths = _validate_review_adjudication(
        review,
        review_path=review_path,
        final_plan_manifest_sha256=str(receipt["plan_manifest_sha256"]),
    )
    if (
        validated_review.get("receipt_sha256")
        != receipt.get("review_adjudication_sha256")
        or protocol.sha256_file(review_path)
        != receipt.get("review_adjudication_file_sha256")
        or validated_review.get("review_model") != receipt.get("review_model")
        or validated_review.get("final_plan_manifest_sha256")
        != receipt.get("plan_manifest_sha256")
    ):
        raise AuthorizationError("execution review adjudication differs")
    source_paths = [
        _safe_relative(row.get("path"), "bound source")
        for row in source_inventory
        if isinstance(row, Mapping)
    ]
    if len(source_paths) != len(source_inventory):
        raise AuthorizationError("execution source inventory schema differs")
    bound_paths = {
        *source_paths,
        *review_bound_paths,
        (plan_prefix / "plan_manifest.json").as_posix(),
        *((plan_prefix / name).as_posix() for name in PLAN_FILES),
    }
    if receipt.get("bound_input_count") != len(bound_paths) or receipt.get(
        "bound_input_paths_sha256"
    ) != protocol.canonical_sha256(tuple(sorted(bound_paths))):
        raise AuthorizationError("execution bound-input set differs")
    live_ref = str(receipt.get("git_remote_ref", ""))
    local_ref = str(receipt.get("git_local_remote_ref", ""))
    if not live_ref.startswith(
        "refs/heads/"
    ) or local_ref != "refs/remotes/origin/" + live_ref.removeprefix("refs/heads/"):
        raise AuthorizationError("execution remote branch binding differs")
    started = float(receipt["campaign_started_at_unix"])
    deadline = float(receipt["campaign_deadline_at_unix"])
    provider_deadline = float(receipt["provider_deadline_at_unix"])
    price = float(receipt["hourly_price_usd"])
    if (
        not all(
            math.isfinite(value)
            for value in (started, deadline, provider_deadline, price)
        )
        or deadline - started != protocol.RESOURCE_LIMITS["max_walltime_seconds"]
        or provider_deadline - started
        != protocol.RESOURCE_LIMITS["provider_deadline_seconds"]
        or deadline >= provider_deadline
        or price * (deadline - started) / 3600
        != protocol.RESOURCE_LIMITS["max_spend_usd"]
    ):
        raise AuthorizationError("authorized campaign budget window differs")
    authorized = _utc(
        str(receipt["authorized_at_utc"]), "authorization time"
    ).timestamp()
    observed = datetime.now(timezone.utc).timestamp() if now_unix is None else now_unix
    if (
        not math.isfinite(observed)
        or authorized < started
        or authorized >= deadline
        or observed < started
        or observed >= deadline
    ):
        raise AuthorizationError("authorization is outside the active campaign")
    return dict(receipt)


def authorize(
    *,
    plan_dir: Path,
    ownership_path: Path,
    guest_path: Path,
    cache_path: Path,
    review_adjudication_path: Path,
    hourly_price_usd: float,
    now: datetime | None = None,
) -> dict[str, Any]:
    plan = _validate_plan(plan_dir)
    manifest = plan["manifest"]
    supplied_plan_hash = str(manifest["plan_manifest_sha256"])

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
        raise AuthorizationError(f"provider/cache chain failed: {exc}") from exc
    revisions = _validated_component_revisions(cache)
    if (
        ownership.get("network_volume_id") != protocol.NETWORK_VOLUME_ID
        or ownership.get("data_center_id") != protocol.DATA_CENTER_ID
        or ownership.get("gpu_type") != protocol.GPU_TYPE
        or ownership.get("gpu_count") != 1
    ):
        raise AuthorizationError("owned provider resources differ from calibration")

    review_path = _regular_file(review_adjudication_path, "review adjudication")
    review = _json(review_path, "review adjudication")
    validated_review, review_bound_paths = _validate_review_adjudication(
        review,
        review_path=review_path,
        final_plan_manifest_sha256=supplied_plan_hash,
    )
    review_relative = str(validated_review["receipt_path"])
    review_hash = str(validated_review["receipt_sha256"])

    final_git = _live_remote_freeze()
    bound_paths = set(plan["bound_paths"])
    bound_paths.update(review_bound_paths)
    ordered_bound = _verify_committed_paths(tuple(bound_paths))

    created = _utc(str(ownership["created_at"]), "provider created_at")
    provider_deadline = _utc(
        str(ownership["terminate_after"]), "provider terminate_after"
    )
    if (provider_deadline - created).total_seconds() != protocol.RESOURCE_LIMITS[
        "provider_deadline_seconds"
    ]:
        raise AuthorizationError("provider deadline differs from frozen six hours")
    campaign_deadline = created + timedelta(
        seconds=protocol.RESOURCE_LIMITS["max_walltime_seconds"]
    )
    if campaign_deadline >= provider_deadline:
        raise AuthorizationError("calibration watchdog is not inside provider deadline")
    if (
        not math.isfinite(hourly_price_usd)
        or float(hourly_price_usd) != CONSERVATIVE_RATE_USD_PER_HOUR
        or float(hourly_price_usd)
        * protocol.RESOURCE_LIMITS["max_walltime_seconds"]
        / 3600
        != protocol.RESOURCE_LIMITS["max_spend_usd"]
    ):
        raise AuthorizationError(
            "hourly price must equal the frozen conservative $6.00 rate"
        )
    authorized_at = now or datetime.now(timezone.utc)
    authorized_text = _utc_text(authorized_at)
    authorized_timestamp = _utc(authorized_text, "authorization time").timestamp()
    if not created.timestamp() <= authorized_timestamp < campaign_deadline.timestamp():
        raise AuthorizationError("authorization time is outside the 90-minute campaign")

    source_rows = plan["source"]["files"]
    core = {
        "schema_version": 1,
        "status": "authorized",
        "study_id": protocol.STUDY_ID,
        "protocol_version": protocol.PROTOCOL_VERSION,
        "authorized_at_utc": authorized_text,
        "canonical_plan_relative_path": plan["canonical_plan_relative_path"],
        "plan_manifest_sha256": supplied_plan_hash,
        "plan_manifest_file_sha256": protocol.sha256_file(plan["manifest_path"]),
        "source_files_sha256": protocol.sha256_file(plan["source_path"]),
        "source_file_inventory_sha256": protocol.canonical_sha256(source_rows),
        "review_adjudication_sha256": review_hash,
        "review_adjudication_file_sha256": protocol.sha256_file(review_path),
        "review_adjudication_relative_path": review_relative,
        "review_model": validated_review["review_model"],
        **final_git,
        "bound_input_count": len(ordered_bound),
        "bound_input_paths_sha256": protocol.canonical_sha256(ordered_bound),
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
        "campaign_started_at_unix": created.timestamp(),
        "campaign_deadline_at_unix": campaign_deadline.timestamp(),
        "provider_deadline_at_unix": provider_deadline.timestamp(),
        "hourly_price_usd": CONSERVATIVE_RATE_USD_PER_HOUR,
        "max_spend_usd": protocol.RESOURCE_LIMITS["max_spend_usd"],
        "max_walltime_seconds": protocol.RESOURCE_LIMITS["max_walltime_seconds"],
        "target_prompt_render_count": 0,
        "target_feature_vector_count": 0,
        "analysis_data_inputs": [],
    }
    return {**core, "receipt_sha256": protocol.canonical_sha256(core)}


def _write(path: Path, value: Mapping[str, Any]) -> None:
    output = _absolute(path)
    _require_no_symlink_components(output.parent, "authorization output parent")
    if not output.parent.is_dir() or os.path.lexists(output):
        raise AuthorizationError("authorization output path is not fresh")
    payload = protocol.canonical_json_bytes(dict(value)) + b"\n"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(output, flags, 0o600)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
    except OSError as exc:
        raise AuthorizationError("authorization receipt publication failed") from exc


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan-dir", type=Path, required=True)
    parser.add_argument("--ownership", type=Path, required=True)
    parser.add_argument("--guest", type=Path, required=True)
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--review-adjudication", type=Path, required=True)
    parser.add_argument("--hourly-price-usd", type=float, required=True)
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
        hourly_price_usd=args.hourly_price_usd,
    )
    _write(args.output, receipt)
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

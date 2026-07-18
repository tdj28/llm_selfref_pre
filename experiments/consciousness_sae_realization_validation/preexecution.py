#!/usr/bin/env python3
"""Issue the single stop-ship authorization for smoke and Stage A.

This is the last outcome-free gate before any model forward.  It binds the
exact final plan and source inventory, the GPT Pro advisory evidence, a
clean pushed Git freeze, the owned provider/guest/cache chain, and the one
campaign identity/deadline.  It does not load a model or render a prompt.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from experiments.consciousness_sae_realization_validation import (  # noqa: E402
    controls,
    protocol,
    review_adjudication,
    runpod_preflight,
)


SCHEMA_VERSION = 1
RECEIPT_TYPE = "preexecution_authorization_v1"
REMOTE_REF = re.compile(r"(?:refs/remotes/)?origin/[A-Za-z0-9._/-]+")
COMMIT = re.compile(r"[0-9a-f]{40}")
PLAN_FILES = frozenset(
    {
        "protocol_snapshot.json",
        "stage_a_plan.jsonl",
        "aggregate_assignments.jsonl",
        "stage_b_plan.jsonl",
        "source_files.json",
    }
)
RECEIPT_FIELDS = frozenset(
    {
        "schema_version",
        "receipt_type",
        "status",
        "study_id",
        "protocol_version",
        "authorized_at_utc",
        "plan_manifest_sha256",
        "plan_manifest_file_sha256",
        "plan_source_inventory_sha256",
        "plan_file_inventory_sha256",
        "source_file_inventory_sha256",
        "review_adjudication_sha256",
        "review_adjudication_relative_path",
        "review_model",
        "review_reasoning",
        "review_status",
        "git_head_commit",
        "git_remote_ref",
        "git_remote_commit",
        "git_live_remote_branch_ref",
        "git_live_remote_commit",
        "bound_input_paths_sha256",
        "guest_deployment_file_count",
        "guest_deployment_path_set_sha256",
        "prior_result_files_permitted",
        "bound_inputs_clean",
        "ownership_receipt_sha256",
        "guest_receipt_sha256",
        "cache_receipt_sha256",
        "pod_id",
        "pod_name",
        "ownership_nonce",
        "network_volume_id",
        "data_center_id",
        "gpu_type",
        "gpu_count",
        "campaign_identity_sha256",
        "campaign_started_at_utc",
        "provider_terminate_at_utc",
        "campaign_started_at_unix",
        "provider_terminate_at_unix",
        "maximum_campaign_seconds",
        "maximum_campaign_spend_usd",
        "model_forward_count",
        "mundane_smoke_prompt_render_count",
        "stage_a_prompt_render_count",
        "stage_b_prompt_render_count",
        "paper_prompt_render_count",
        "target_prompt_render_count",
        "target_outcome_count",
        "prior_outcome_inputs",
        "receipt_sha256",
    }
)


class PreexecutionError(RuntimeError):
    """The paid execution is not authorized by the exact frozen chain."""


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _utc(value: str, label: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise PreexecutionError(f"{label} is not canonical UTC")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise PreexecutionError(f"{label} is not parseable UTC") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise PreexecutionError(f"{label} is timezone-naive")
    return parsed.astimezone(timezone.utc)


def _utc_text(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise PreexecutionError("authorization time is timezone-naive")
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )


def _safe_relative(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise PreexecutionError(f"{label} is empty")
    path = PurePosixPath(value)
    if (
        path.is_absolute()
        or "\\" in value
        or any(part in {"", ".", ".."} for part in path.parts)
        or path.as_posix() != value
    ):
        raise PreexecutionError(f"{label} is not repository-relative")
    return value


def _repo_file(root: Path, relative: str, label: str) -> Path:
    value = _safe_relative(relative, label)
    path = root / value
    current = root
    for part in PurePosixPath(value).parts:
        current = current / part
        if current.is_symlink():
            raise PreexecutionError(f"{label} crosses a symlink")
    if not path.is_file() or path.is_symlink() or path.stat().st_nlink != 1:
        raise PreexecutionError(f"{label} is not a single-link regular file")
    try:
        path.resolve(strict=True).relative_to(root)
    except ValueError as exc:
        raise PreexecutionError(f"{label} escapes repository") from exc
    return path


def _load_json(path: Path, label: str) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file() or path.stat().st_nlink != 1:
        raise PreexecutionError(f"{label} is not a single-link regular file")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PreexecutionError(f"{label} is not readable JSON") from exc
    if not isinstance(value, dict):
        raise PreexecutionError(f"{label} is not a JSON object")
    return value


def _git(root: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=root,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if completed.returncode != 0:
        raise PreexecutionError(
            f"git {' '.join(args)} failed: {completed.stderr.strip()}"
        )
    return completed.stdout.strip()


def _remote_branch_ref(remote_ref: str) -> str:
    """Map one safe local ``origin/...`` ref to its exact live branch ref."""

    if REMOTE_REF.fullmatch(remote_ref) is None or ".." in remote_ref:
        raise PreexecutionError("remote ref is not a safe origin ref")
    normalized = remote_ref.removeprefix("refs/remotes/")
    if not normalized.startswith("origin/"):
        raise PreexecutionError("remote ref is not an origin branch")
    branch = normalized.removeprefix("origin/")
    if (
        not branch
        or branch.startswith("/")
        or branch.endswith(("/", ".", ".lock"))
        or "//" in branch
        or "@{" in branch
        or any(part.startswith(".") for part in branch.split("/"))
    ):
        raise PreexecutionError("remote branch is not safe")
    return f"refs/heads/{branch}"


def _live_remote_commit(root: Path, branch_ref: str) -> str:
    """Read one exact branch SHA from origin without mutating local refs."""

    output = _git(root, "ls-remote", "--exit-code", "origin", branch_ref)
    lines = output.splitlines()
    if len(lines) != 1:
        raise PreexecutionError("live origin branch did not return exactly one ref")
    fields = lines[0].split()
    if (
        len(fields) != 2
        or COMMIT.fullmatch(fields[0]) is None
        or fields[1] != branch_ref
    ):
        raise PreexecutionError("live origin branch response differs")
    return fields[0]


def _validate_minimal_guest_tree(root: Path, allowed_paths: Sequence[str]) -> None:
    """Prove prior plans/results/blogs are physically absent from deployment."""

    allowed = set(allowed_paths)
    if (root / ".git").exists() or (root / ".git").is_symlink():
        raise PreexecutionError("guest deployment unexpectedly contains Git metadata")
    observed: set[str] = set()
    for path in root.rglob("*"):
        if path.is_symlink():
            raise PreexecutionError("guest deployment contains a symlink")
        if not path.is_file():
            continue
        relative = path.relative_to(root).as_posix()
        observed.add(relative)
    extras = observed - allowed
    missing = allowed - observed
    if extras or missing:
        raise PreexecutionError(
            "guest deployment differs from the outcome-free allowlist: "
            f"missing={sorted(missing)}, extra={sorted(extras)}"
        )


def _validate_plan(root: Path, plan_dir: Path) -> dict[str, Any]:
    directory = plan_dir.expanduser().resolve(strict=True)
    if directory.is_symlink() or not directory.is_dir():
        raise PreexecutionError("plan directory is not real")
    try:
        prefix = directory.relative_to(root)
    except ValueError as exc:
        raise PreexecutionError("plan directory is outside repository") from exc
    manifest_path = directory / "plan_manifest.json"
    manifest = _load_json(manifest_path, "plan manifest")
    core = dict(manifest)
    supplied = core.pop("plan_manifest_sha256", None)
    if supplied != controls.canonical_sha256(core):
        raise PreexecutionError("plan manifest self-hash differs")
    if (
        manifest.get("schema_version") != protocol.PLAN_SCHEMA_VERSION
        or manifest.get("study_id") != protocol.STUDY_ID
        or manifest.get("protocol_version") != protocol.PROTOCOL_VERSION
        or manifest.get("scope")
        != "realization_and_target_free_vector_validation_only"
        or manifest.get("paper_prompt_render_count") != 0
        or manifest.get("behavioral_replication_included") is not False
        or manifest.get("prior_outcome_inputs") != []
    ):
        raise PreexecutionError("plan identity/scope differs")
    rows = manifest.get("files")
    if not isinstance(rows, list) or {row.get("path") for row in rows} != PLAN_FILES:
        raise PreexecutionError("plan file inventory differs")
    bound_paths = {(prefix / "plan_manifest.json").as_posix()}
    for row in rows:
        if not isinstance(row, Mapping) or set(row) != {"path", "bytes", "sha256"}:
            raise PreexecutionError("plan file row schema differs")
        relative = _safe_relative(row["path"], "plan file")
        path = directory / relative
        if (
            path.is_symlink()
            or not path.is_file()
            or path.stat().st_nlink != 1
            or path.stat().st_size != row["bytes"]
            or protocol.sha256_file(path) != row["sha256"]
        ):
            raise PreexecutionError(f"plan file differs: {relative}")
        bound_paths.add((prefix / relative).as_posix())
    source_path = directory / "source_files.json"
    source = _load_json(source_path, "source inventory")
    if (
        set(source) != {"study_id", "protocol_version", "files", "prior_outcome_inputs"}
        or source.get("study_id") != protocol.STUDY_ID
        or source.get("protocol_version") != protocol.PROTOCOL_VERSION
        or source.get("prior_outcome_inputs") != []
        or not isinstance(source.get("files"), list)
        or not source["files"]
    ):
        raise PreexecutionError("source inventory identity differs")
    source_paths: set[str] = set()
    for row in source["files"]:
        if not isinstance(row, Mapping) or set(row) != {
            "path", "bytes", "sha256", "outcome_bearing", "reuse_kind"
        }:
            raise PreexecutionError("source row schema differs")
        relative = _safe_relative(row["path"], "bound source")
        if relative in source_paths or row.get("outcome_bearing") is not False:
            raise PreexecutionError("source inventory duplicates or bears outcomes")
        path = _repo_file(root, relative, "bound source")
        if path.stat().st_size != row["bytes"] or protocol.sha256_file(path) != row["sha256"]:
            raise PreexecutionError(f"bound source differs: {relative}")
        source_paths.add(relative)
    bound_paths.update(source_paths)
    return {
        "manifest": manifest,
        "manifest_path": manifest_path,
        "source": source,
        "source_path": source_path,
        "bound_paths": bound_paths,
    }


def _campaign(ownership: Mapping[str, Any]) -> dict[str, Any]:
    created = _utc(str(ownership["created_at"]), "campaign created_at")
    deadline = _utc(str(ownership["terminate_after"]), "campaign deadline")
    duration = (deadline - created).total_seconds()
    if duration != protocol.RESOURCE_LIMITS["max_walltime_seconds"]:
        raise PreexecutionError("campaign duration differs from the six-hour ceiling")
    identity = {
        "study_id": protocol.STUDY_ID,
        "protocol_version": protocol.PROTOCOL_VERSION,
        "pod_id": ownership["pod_id"],
        "pod_name": ownership["pod_name"],
        "ownership_nonce": ownership["ownership_nonce"],
        "network_volume_id": ownership["network_volume_id"],
        "data_center_id": ownership["data_center_id"],
        "gpu_type": ownership["gpu_type"],
        "gpu_count": ownership["gpu_count"],
        "created_at": ownership["created_at"],
        "terminate_after": ownership["terminate_after"],
    }
    return {
        "campaign_identity_sha256": controls.canonical_sha256(identity),
        "campaign_started_at_utc": ownership["created_at"],
        "provider_terminate_at_utc": ownership["terminate_after"],
        "campaign_started_at_unix": created.timestamp(),
        "provider_terminate_at_unix": deadline.timestamp(),
    }


def deployment_allowlist(
    *,
    repo_root: Path,
    plan_dir: Path,
    review_receipt: Mapping[str, Any],
) -> tuple[str, ...]:
    """Return the exact outcome-free paths permitted in the guest archive."""

    root = repo_root.expanduser().resolve(strict=True)
    plan = _validate_plan(root, plan_dir)
    plan_hash = str(plan["manifest"]["plan_manifest_sha256"])
    try:
        review = review_adjudication.validate_review_evidence_receipt(
            review_receipt,
            repo_root=root,
            expected_plan_manifest_sha256=plan_hash,
        )
    except review_adjudication.ReviewAdjudicationError as exc:
        raise PreexecutionError(str(exc)) from exc
    review_path = _safe_relative(review["receipt_path"], "review evidence path")
    if _load_json(
        _repo_file(root, review_path, "review evidence"),
        "review evidence",
    ) != dict(review):
        raise PreexecutionError("review evidence file/content differs")
    paths = set(plan["bound_paths"])
    paths.update(review_adjudication.review_evidence_bound_paths(review))
    return tuple(sorted(paths))


def _derive_core(
    *,
    repo_root: Path,
    plan_dir: Path,
    review_receipt: Mapping[str, Any],
    ownership_receipt: Mapping[str, Any],
    guest_receipt: Mapping[str, Any],
    cache_receipt: Mapping[str, Any],
    remote_ref: str,
    authorized_at_utc: str,
    verify_git_freeze: bool = True,
    sealed_git: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    root = repo_root.expanduser().resolve(strict=True)
    live_branch_ref = _remote_branch_ref(remote_ref)
    plan = _validate_plan(root, plan_dir)
    plan_hash = str(plan["manifest"]["plan_manifest_sha256"])
    try:
        review = review_adjudication.validate_review_evidence_receipt(
            review_receipt,
            repo_root=root,
            expected_plan_manifest_sha256=plan_hash,
        )
        ownership = runpod_preflight.validate_ownership_receipt(ownership_receipt)
        guest = runpod_preflight.validate_guest_receipt(
            guest_receipt, ownership_receipt=ownership
        )
        cache = runpod_preflight.validate_cache_receipt(
            cache_receipt,
            guest_receipt=guest,
            ownership_receipt=ownership,
        )
    except (review_adjudication.ReviewAdjudicationError, runpod_preflight.PreflightError) as exc:
        raise PreexecutionError(str(exc)) from exc
    review_path = _safe_relative(review["receipt_path"], "review evidence path")
    if _load_json(_repo_file(root, review_path, "review evidence"), "review evidence") != dict(review):
        raise PreexecutionError("review evidence file/content differs")
    bound_paths = set(plan["bound_paths"])
    bound_paths.update(review_adjudication.review_evidence_bound_paths(review))
    ordered_bound = sorted(bound_paths)
    if verify_git_freeze:
        status = _git(
            root,
            "status",
            "--porcelain",
            "--untracked-files=all",
            "--",
            *ordered_bound,
        )
        if status:
            raise PreexecutionError("one or more plan/review/source inputs are dirty")
        for relative in ordered_bound:
            _git(root, "cat-file", "-e", f"HEAD:{relative}")
        head = _git(root, "rev-parse", "HEAD")
        remote_commit = _git(root, "rev-parse", remote_ref)
        # A remote-tracking ref can be stale or locally forged.  This exact,
        # read-only query proves that origin currently advertises the same
        # commit under the requested branch without fetching or changing refs.
        live_remote_commit = _live_remote_commit(root, live_branch_ref)
    else:
        if not isinstance(sealed_git, Mapping):
            raise PreexecutionError("gitless execution lacks the sealed freeze fields")
        head = str(sealed_git.get("git_head_commit", ""))
        remote_commit = str(sealed_git.get("git_remote_commit", ""))
        if sealed_git.get("git_live_remote_branch_ref") != live_branch_ref:
            raise PreexecutionError("gitless execution live branch seal differs")
        live_remote_commit = str(sealed_git.get("git_live_remote_commit", ""))
        _validate_minimal_guest_tree(root, ordered_bound)
    if (
        COMMIT.fullmatch(head) is None
        or COMMIT.fullmatch(remote_commit) is None
        or COMMIT.fullmatch(live_remote_commit) is None
        or head != remote_commit
        or head != live_remote_commit
    ):
        raise PreexecutionError("HEAD is not the exact live pushed remote freeze")
    authorized = _utc(authorized_at_utc, "authorized_at_utc")
    created = _utc(ownership["created_at"], "campaign created_at")
    deadline = _utc(ownership["terminate_after"], "campaign deadline")
    if authorized < created or authorized >= deadline:
        raise PreexecutionError("authorization time is outside owned campaign")
    campaign = _campaign(ownership)
    source_rows = plan["source"]["files"]
    plan_rows = plan["manifest"]["files"]
    return {
        "schema_version": SCHEMA_VERSION,
        "receipt_type": RECEIPT_TYPE,
        "status": "authorized",
        "study_id": protocol.STUDY_ID,
        "protocol_version": protocol.PROTOCOL_VERSION,
        "authorized_at_utc": authorized_at_utc,
        "plan_manifest_sha256": plan_hash,
        "plan_manifest_file_sha256": protocol.sha256_file(plan["manifest_path"]),
        "plan_source_inventory_sha256": protocol.sha256_file(plan["source_path"]),
        "plan_file_inventory_sha256": controls.canonical_sha256(plan_rows),
        "source_file_inventory_sha256": controls.canonical_sha256(source_rows),
        "review_adjudication_sha256": review["receipt_sha256"],
        "review_adjudication_relative_path": review_path,
        "review_model": review["review_model"],
        "review_reasoning": review["review_reasoning"],
        "review_status": review["status"],
        "git_head_commit": head,
        "git_remote_ref": remote_ref,
        "git_remote_commit": remote_commit,
        "git_live_remote_branch_ref": live_branch_ref,
        "git_live_remote_commit": live_remote_commit,
        "bound_input_paths_sha256": controls.canonical_sha256(ordered_bound),
        "guest_deployment_file_count": len(ordered_bound),
        "guest_deployment_path_set_sha256": controls.canonical_sha256(
            ordered_bound
        ),
        "prior_result_files_permitted": False,
        "bound_inputs_clean": True,
        "ownership_receipt_sha256": ownership["receipt_sha256"],
        "guest_receipt_sha256": guest["receipt_sha256"],
        "cache_receipt_sha256": cache["receipt_sha256"],
        "pod_id": ownership["pod_id"],
        "pod_name": ownership["pod_name"],
        "ownership_nonce": ownership["ownership_nonce"],
        "network_volume_id": ownership["network_volume_id"],
        "data_center_id": ownership["data_center_id"],
        "gpu_type": ownership["gpu_type"],
        "gpu_count": ownership["gpu_count"],
        **campaign,
        "maximum_campaign_seconds": protocol.RESOURCE_LIMITS["max_walltime_seconds"],
        "maximum_campaign_spend_usd": protocol.RESOURCE_LIMITS["max_spend_usd"],
        "model_forward_count": 0,
        "mundane_smoke_prompt_render_count": 0,
        "stage_a_prompt_render_count": 0,
        "stage_b_prompt_render_count": 0,
        "paper_prompt_render_count": 0,
        "target_prompt_render_count": 0,
        "target_outcome_count": 0,
        "prior_outcome_inputs": [],
    }


def build_authorization(
    *,
    repo_root: Path,
    plan_dir: Path,
    review_receipt: Mapping[str, Any],
    ownership_receipt: Mapping[str, Any],
    guest_receipt: Mapping[str, Any],
    cache_receipt: Mapping[str, Any],
    remote_ref: str,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Derive one authorization; no arbitrary receipt fragments are accepted."""

    authorized_at = _utc_text(now or datetime.now(timezone.utc))
    core = _derive_core(
        repo_root=repo_root,
        plan_dir=plan_dir,
        review_receipt=review_receipt,
        ownership_receipt=ownership_receipt,
        guest_receipt=guest_receipt,
        cache_receipt=cache_receipt,
        remote_ref=remote_ref,
        authorized_at_utc=authorized_at,
    )
    return {**core, "receipt_sha256": controls.canonical_sha256(core)}


def validate_authorization(
    receipt: Mapping[str, Any],
    *,
    repo_root: Path,
    plan_dir: Path,
    ownership_receipt: Mapping[str, Any],
    guest_receipt: Mapping[str, Any],
    cache_receipt: Mapping[str, Any],
) -> dict[str, Any]:
    """Reproduce the authorization from current disk, Git, and provider evidence."""

    if not isinstance(receipt, Mapping) or set(receipt) != RECEIPT_FIELDS:
        raise PreexecutionError("pre-execution authorization schema differs")
    core = dict(receipt)
    supplied = core.pop("receipt_sha256", None)
    if supplied != controls.canonical_sha256(core):
        raise PreexecutionError("pre-execution authorization self-hash differs")
    if (
        receipt.get("schema_version") != SCHEMA_VERSION
        or receipt.get("receipt_type") != RECEIPT_TYPE
        or receipt.get("status") != "authorized"
        or receipt.get("study_id") != protocol.STUDY_ID
        or receipt.get("protocol_version") != protocol.PROTOCOL_VERSION
        or receipt.get("prior_outcome_inputs") != []
    ):
        raise PreexecutionError("pre-execution authorization identity/status differs")
    rebuilt = _derive_core(
        repo_root=repo_root,
        plan_dir=plan_dir,
        review_receipt=_load_json(
            _repo_file(
                repo_root.expanduser().resolve(strict=True),
                str(receipt["review_adjudication_relative_path"]),
                "review evidence",
            ),
            "review evidence",
        ),
        ownership_receipt=ownership_receipt,
        guest_receipt=guest_receipt,
        cache_receipt=cache_receipt,
        remote_ref=str(receipt["git_remote_ref"]),
        authorized_at_utc=str(receipt["authorized_at_utc"]),
    )
    if rebuilt != core:
        raise PreexecutionError("pre-execution authorization does not reproduce")
    for field in (
        "model_forward_count",
        "mundane_smoke_prompt_render_count",
        "stage_a_prompt_render_count",
        "stage_b_prompt_render_count",
        "paper_prompt_render_count",
        "target_prompt_render_count",
        "target_outcome_count",
    ):
        if receipt[field] != 0:
            raise PreexecutionError("authorization was produced after model/prompt access")
    return dict(receipt)


def validate_execution_authorization(
    receipt: Mapping[str, Any],
    *,
    repo_root: Path,
    plan_dir: Path,
    ownership_receipt: Mapping[str, Any],
    guest_receipt: Mapping[str, Any],
    cache_receipt: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate an archived source tree without requiring its absent ``.git``.

    The producer already proved clean pushed HEAD equality.  Guest execution
    retains those sealed fields while independently rehashing every plan,
    source, review, ownership, guest, cache, and campaign binding.
    """

    validate_authorization_evidence(
        receipt, repo_root=repo_root, plan_dir=plan_dir
    )
    if not isinstance(receipt, Mapping) or set(receipt) != RECEIPT_FIELDS:
        raise PreexecutionError("pre-execution authorization schema differs")
    core = dict(receipt)
    supplied = core.pop("receipt_sha256", None)
    if supplied != controls.canonical_sha256(core):
        raise PreexecutionError("pre-execution authorization self-hash differs")
    if (
        receipt.get("schema_version") != SCHEMA_VERSION
        or receipt.get("receipt_type") != RECEIPT_TYPE
        or receipt.get("status") != "authorized"
        or receipt.get("study_id") != protocol.STUDY_ID
        or receipt.get("protocol_version") != protocol.PROTOCOL_VERSION
        or receipt.get("bound_inputs_clean") is not True
        or receipt.get("git_head_commit") != receipt.get("git_remote_commit")
        or receipt.get("git_head_commit") != receipt.get("git_live_remote_commit")
        or receipt.get("git_live_remote_branch_ref")
        != _remote_branch_ref(str(receipt.get("git_remote_ref", "")))
        or receipt.get("prior_outcome_inputs") != []
    ):
        raise PreexecutionError("execution authorization identity/freeze differs")
    rebuilt = _derive_core(
        repo_root=repo_root,
        plan_dir=plan_dir,
        review_receipt=_load_json(
            _repo_file(
                repo_root.expanduser().resolve(strict=True),
                str(receipt["review_adjudication_relative_path"]),
                "review evidence",
            ),
            "review evidence",
        ),
        ownership_receipt=ownership_receipt,
        guest_receipt=guest_receipt,
        cache_receipt=cache_receipt,
        remote_ref=str(receipt["git_remote_ref"]),
        authorized_at_utc=str(receipt["authorized_at_utc"]),
        verify_git_freeze=False,
        sealed_git=receipt,
    )
    if rebuilt != core:
        raise PreexecutionError("gitless execution authorization does not reproduce")
    return dict(receipt)


def validate_authorization_evidence(
    receipt: Mapping[str, Any], *, repo_root: Path, plan_dir: Path
) -> dict[str, Any]:
    """Rehash outcome-free freeze evidence when provider receipts are unavailable."""

    if not isinstance(receipt, Mapping) or set(receipt) != RECEIPT_FIELDS:
        raise PreexecutionError("pre-execution authorization schema differs")
    core = dict(receipt)
    supplied = core.pop("receipt_sha256", None)
    if supplied != controls.canonical_sha256(core):
        raise PreexecutionError("pre-execution authorization self-hash differs")
    if (
        receipt.get("schema_version") != SCHEMA_VERSION
        or receipt.get("receipt_type") != RECEIPT_TYPE
        or receipt.get("status") != "authorized"
        or receipt.get("study_id") != protocol.STUDY_ID
        or receipt.get("protocol_version") != protocol.PROTOCOL_VERSION
        or receipt.get("bound_inputs_clean") is not True
        or receipt.get("git_head_commit") != receipt.get("git_remote_commit")
        or receipt.get("git_head_commit") != receipt.get("git_live_remote_commit")
        or COMMIT.fullmatch(str(receipt.get("git_head_commit", ""))) is None
        or COMMIT.fullmatch(str(receipt.get("git_live_remote_commit", ""))) is None
        or receipt.get("git_live_remote_branch_ref")
        != _remote_branch_ref(str(receipt.get("git_remote_ref", "")))
        or receipt.get("prior_outcome_inputs") != []
    ):
        raise PreexecutionError("authorization evidence identity/freeze differs")
    root = repo_root.expanduser().resolve(strict=True)
    plan = _validate_plan(root, plan_dir)
    review_path = _safe_relative(
        receipt.get("review_adjudication_relative_path"),
        "review evidence path",
    )
    review_value = _load_json(
        _repo_file(root, review_path, "review evidence"),
        "review evidence",
    )
    try:
        review = review_adjudication.validate_review_evidence_receipt(
            review_value,
            repo_root=root,
            expected_plan_manifest_sha256=plan["manifest"][
                "plan_manifest_sha256"
            ],
        )
    except review_adjudication.ReviewAdjudicationError as exc:
        raise PreexecutionError(str(exc)) from exc
    bound_paths = set(plan["bound_paths"])
    bound_paths.update(review_adjudication.review_evidence_bound_paths(review))
    created = _utc(str(receipt["campaign_started_at_utc"]), "campaign start")
    deadline = _utc(
        str(receipt["provider_terminate_at_utc"]), "campaign deadline"
    )
    authorized = _utc(str(receipt["authorized_at_utc"]), "authorization time")
    identity = {
        "study_id": protocol.STUDY_ID,
        "protocol_version": protocol.PROTOCOL_VERSION,
        "pod_id": receipt["pod_id"],
        "pod_name": receipt["pod_name"],
        "ownership_nonce": receipt["ownership_nonce"],
        "network_volume_id": receipt["network_volume_id"],
        "data_center_id": receipt["data_center_id"],
        "gpu_type": receipt["gpu_type"],
        "gpu_count": receipt["gpu_count"],
        "created_at": receipt["campaign_started_at_utc"],
        "terminate_after": receipt["provider_terminate_at_utc"],
    }
    expected = {
        "plan_manifest_sha256": plan["manifest"]["plan_manifest_sha256"],
        "plan_manifest_file_sha256": protocol.sha256_file(plan["manifest_path"]),
        "plan_source_inventory_sha256": protocol.sha256_file(plan["source_path"]),
        "plan_file_inventory_sha256": controls.canonical_sha256(
            plan["manifest"]["files"]
        ),
        "source_file_inventory_sha256": controls.canonical_sha256(
            plan["source"]["files"]
        ),
        "review_adjudication_sha256": review["receipt_sha256"],
        "review_model": review["review_model"],
        "review_reasoning": review["review_reasoning"],
        "review_status": review["status"],
        "bound_input_paths_sha256": controls.canonical_sha256(
            sorted(bound_paths)
        ),
        "guest_deployment_file_count": len(bound_paths),
        "guest_deployment_path_set_sha256": controls.canonical_sha256(
            sorted(bound_paths)
        ),
        "prior_result_files_permitted": False,
        "campaign_identity_sha256": controls.canonical_sha256(identity),
        "campaign_started_at_unix": created.timestamp(),
        "provider_terminate_at_unix": deadline.timestamp(),
        "maximum_campaign_seconds": protocol.RESOURCE_LIMITS[
            "max_walltime_seconds"
        ],
        "maximum_campaign_spend_usd": protocol.RESOURCE_LIMITS[
            "max_spend_usd"
        ],
    }
    if any(receipt.get(field) != value for field, value in expected.items()):
        raise PreexecutionError("authorization freeze evidence differs")
    if (
        deadline <= created
        or (deadline - created).total_seconds()
        != protocol.RESOURCE_LIMITS["max_walltime_seconds"]
        or authorized < created
        or authorized >= deadline
    ):
        raise PreexecutionError("authorization/campaign chronology differs")
    for field in (
        "model_forward_count",
        "mundane_smoke_prompt_render_count",
        "stage_a_prompt_render_count",
        "stage_b_prompt_render_count",
        "paper_prompt_render_count",
        "target_prompt_render_count",
        "target_outcome_count",
    ):
        if receipt[field] != 0:
            raise PreexecutionError("authorization evidence includes model/prompt access")
    return dict(receipt)


def load_authorization(
    path: Path,
    *,
    repo_root: Path,
    plan_dir: Path,
    ownership_receipt: Mapping[str, Any],
    guest_receipt: Mapping[str, Any],
    cache_receipt: Mapping[str, Any],
) -> dict[str, Any]:
    value = _load_json(path.expanduser().resolve(strict=True), "pre-execution authorization")
    expected = controls.canonical_json_bytes(value) + b"\n"
    if path.expanduser().resolve(strict=True).read_bytes() != expected:
        raise PreexecutionError("pre-execution authorization is not canonical JSON")
    return validate_authorization(
        value,
        repo_root=repo_root,
        plan_dir=plan_dir,
        ownership_receipt=ownership_receipt,
        guest_receipt=guest_receipt,
        cache_receipt=cache_receipt,
    )


def load_execution_authorization(
    path: Path,
    *,
    repo_root: Path,
    plan_dir: Path,
    ownership_receipt: Mapping[str, Any],
    guest_receipt: Mapping[str, Any],
    cache_receipt: Mapping[str, Any],
) -> dict[str, Any]:
    value = _load_json(path.expanduser().resolve(strict=True), "pre-execution authorization")
    if path.expanduser().resolve(strict=True).read_bytes() != (
        controls.canonical_json_bytes(value) + b"\n"
    ):
        raise PreexecutionError("pre-execution authorization is not canonical JSON")
    return validate_execution_authorization(
        value,
        repo_root=repo_root,
        plan_dir=plan_dir,
        ownership_receipt=ownership_receipt,
        guest_receipt=guest_receipt,
        cache_receipt=cache_receipt,
    )


def _write(path: Path, value: Mapping[str, Any]) -> Path:
    destination = path.expanduser().absolute()
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination = destination.parent.resolve(strict=True) / destination.name
    if destination.exists() or destination.is_symlink():
        raise PreexecutionError(f"refusing to overwrite authorization: {destination}")
    partial = destination.with_name(destination.name + ".partial")
    if partial.exists() or partial.is_symlink():
        raise PreexecutionError(f"authorization partial already exists: {partial}")
    payload = controls.canonical_json_bytes(dict(value)) + b"\n"
    with partial.open("xb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(partial, destination)
    return destination


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    parser.add_argument("--plan-dir", type=Path, required=True)
    parser.add_argument("--review-adjudication", type=Path, required=True)
    parser.add_argument("--ownership-receipt", type=Path, required=True)
    parser.add_argument("--guest-receipt", type=Path, required=True)
    parser.add_argument("--cache-receipt", type=Path, required=True)
    parser.add_argument("--remote-ref", required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    review = _load_json(args.review_adjudication, "review evidence receipt")
    ownership = _load_json(args.ownership_receipt, "ownership receipt")
    guest = _load_json(args.guest_receipt, "guest receipt")
    cache = _load_json(args.cache_receipt, "cache receipt")
    receipt = build_authorization(
        repo_root=args.repo_root,
        plan_dir=args.plan_dir,
        review_receipt=review,
        ownership_receipt=ownership,
        guest_receipt=guest,
        cache_receipt=cache,
        remote_ref=args.remote_ref,
    )
    output = _write(args.output, receipt)
    persisted = _load_json(output, "persisted authorization")
    if persisted != receipt:
        raise PreexecutionError("persisted authorization differs")
    print(f"{output} {receipt['receipt_sha256']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

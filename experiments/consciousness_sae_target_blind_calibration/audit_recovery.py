#!/usr/bin/env python3
"""Authorize and execute the disclosed calibration-v2 r3 audit recovery.

This module never runs the model. It preserves the immutable r3 auditor, makes
one J-checkpoint inventory compatibility correction, and confines fresh-host
authority plus historical source validation to audit-only adapters.
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import math
import os
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Iterator, Mapping, Sequence

from experiments.consciousness_sae_realization_validation import runpod_preflight
from experiments.consciousness_sae_target_blind_calibration import (
    audit_runtime_shim,
    authorize,
    protocol,
)


_RUNTIME_MODULE_NAME = "experiments.consciousness_sae_realization_validation.runtime"
_prior_runtime_module = sys.modules.get(_RUNTIME_MODULE_NAME)
sys.modules[_RUNTIME_MODULE_NAME] = audit_runtime_shim
from experiments.consciousness_sae_target_blind_calibration import (  # noqa: E402
    audit,
    orientation,
    validate_plan,
)

orientation.runtime = audit_runtime_shim
if _prior_runtime_module is not None:
    sys.modules[_RUNTIME_MODULE_NAME] = _prior_runtime_module


REPO_ROOT = Path(__file__).resolve().parents[2]
RECOVERY_PROTOCOL_VERSION = (
    "consciousness_sae_target_blind_calibration_v2.audit_recovery_r1"
)
RUN_ID = "calv2-r3-1a16572-20260715T002344Z"
RAW_RELATIVE = (
    "consciousness_sae_target_blind_calibration/"
    "consciousness_sae_target_blind_calibration_v2/raw/" + RUN_ID
)
ORIGINAL_RUN_RECEIPT_SHA256 = (
    "bab48b452c7e7c5b9db5d09ecc34c7e530813e2f5093aff1b8a8152017e4695d"
)
ORIGINAL_RUN_FILE_SHA256 = (
    "d60e25d13d1b9e30a52114aa954a6c1306ef8e15a8dddd53af1de58c4dcb9fee"
)
ORIGINAL_RAW_LEDGER_SHA256 = (
    "7bffb6306b67814d2f4618b6aaf4f243ab2992d7b6b92ebb955a370654e0a20c"
)
ORIGINAL_RAW_INVENTORY_SHA256 = (
    "2f65c41074a49ff04f0de96d547ad5fdef796d13fe98bfea987fbe86822b0cbd"
)
ORIGINAL_FAILURE_LOG_SHA256 = (
    "a5936d0fda01b96f193a1ab40c9d7c52dc751ecdf3686896e26d2d3951cdd86f"
)
EXPECTED_RELEASE_LAYERS = tuple(range(79))
RECOVERY_SECONDS = 30 * 60
RECOVERY_RATE_USD_PER_HOUR = 6.0
RECOVERY_MAX_SPEND_USD = 3.0
HEX64 = re.compile(r"[0-9a-f]{64}")
ATTEMPT_ID_RE = re.compile(r"calv2-r3-audit-recovery-[0-9a-f]{7}-[0-9]{8}T[0-9]{6}Z")
RECOVERY_ATTEMPT_PARENT = (
    "/workspace/consciousness_sae_target_blind_calibration/"
    "consciousness_sae_target_blind_calibration_v2/audit_recovery_attempts"
)
MODEL_SNAPSHOT_PATH = runpod_preflight.LEGACY_PUBLIC_ARTIFACT_ROOT + "/model_snapshot"
J_LENS_PATH = (
    runpod_preflight.LEGACY_PUBLIC_ARTIFACT_ROOT
    + "/jlens/Llama-3.3-70B-Instruct_jacobian_lens.pt"
)

AUDIT_EXECUTABLE_PATHS = (
    "experiments/__init__.py",
    "experiments/consciousness_sae_realization_validation/__init__.py",
    "experiments/consciousness_sae_realization_validation/protocol.py",
    "experiments/consciousness_sae_realization_validation/runpod_preflight.py",
    "experiments/consciousness_sae_realization_validation/"
    "legacy_public_artifact_manifest.json",
    "experiments/consciousness_sae_target_blind_calibration/__init__.py",
    "experiments/consciousness_sae_target_blind_calibration/protocol.py",
    "experiments/consciousness_sae_target_blind_calibration/build_plan.py",
    "experiments/consciousness_sae_target_blind_calibration/review_adjudication.py",
    "experiments/consciousness_sae_target_blind_calibration/validate_plan.py",
    "experiments/consciousness_sae_target_blind_calibration/orientation.py",
    "experiments/consciousness_sae_target_blind_calibration/authorize.py",
    "experiments/consciousness_sae_target_blind_calibration/audit.py",
    "experiments/consciousness_sae_target_blind_calibration/audit_runtime_shim.py",
    "experiments/consciousness_sae_target_blind_calibration/audit_recovery.py",
)
RECOVERY_DOCUMENT_PATHS = (
    "docs/consciousness_sae_target_blind_calibration/AUDIT_RECOVERY_20260714.md",
    "docs/consciousness_sae_target_blind_calibration/AUDIT_RECOVERY_REVIEW_CONTEXT.md",
    "docs/consciousness_sae_target_blind_calibration/reviews/"
    "AUDIT_RECOVERY_GPT_PRO_ADJUDICATION.md",
    "docs/consciousness_sae_target_blind_calibration/reviews/"
    "audit_recovery_gpt_pro_20260714_live/failure.json",
    "docs/consciousness_sae_target_blind_calibration/reviews/"
    "audit_recovery_gpt_pro_20260714_live/request_payload.json",
    "docs/consciousness_sae_target_blind_calibration/reviews/"
    "audit_recovery_gpt_pro_20260714_live/response.json",
    "docs/consciousness_sae_target_blind_calibration/reviews/"
    "audit_recovery_gpt_pro_20260714_live/review_manifest.json",
    "docs/consciousness_sae_target_blind_calibration/reviews/"
    "audit_recovery_gpt_pro_20260714_live/review_request.md",
    "tests/consciousness_sae_target_blind_calibration/test_audit_recovery.py",
)
RECOVERY_BOUND_PATHS = tuple(
    sorted(set(AUDIT_EXECUTABLE_PATHS) | set(RECOVERY_DOCUMENT_PATHS))
)
FORBIDDEN_EXECUTABLE_PATHS = (
    "experiments/consciousness_sae_realization_validation/runtime.py",
    "experiments/consciousness_sae_realization_validation/guest_launcher.py",
    "experiments/consciousness_sae_realization_validation/runpod_orchestrator.py",
    "experiments/consciousness_sae_target_blind_calibration/runner.py",
    "experiments/consciousness_sae_target_blind_calibration/guest_launcher.py",
)
FORBIDDEN_MODULES = frozenset(
    {
        "experiments.consciousness_sae_realization_validation.runtime",
        "experiments.consciousness_sae_realization_validation.guest_launcher",
        "experiments.consciousness_sae_realization_validation.runpod_orchestrator",
        "experiments.consciousness_sae_target_blind_calibration.runner",
        "experiments.consciousness_sae_target_blind_calibration.guest_launcher",
    }
)


class AuditRecoveryError(RuntimeError):
    """The audit-only recovery closure is not admissible."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while block := handle.read(8 * 1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def _json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise AuditRecoveryError(f"JSON is unreadable: {path}") from exc
    if not isinstance(value, dict) or not audit._finite_json(value):  # noqa: SLF001
        raise AuditRecoveryError(f"JSON root is invalid: {path}")
    return value


def _self_hash(value: Mapping[str, Any], label: str) -> str:
    core = dict(value)
    supplied = core.pop("receipt_sha256", None)
    if (
        not isinstance(supplied, str)
        or HEX64.fullmatch(supplied) is None
        or supplied != protocol.canonical_sha256(core)
    ):
        raise AuditRecoveryError(f"{label} self-hash differs")
    return supplied


def _utc(value: str, label: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise AuditRecoveryError(f"{label} is not canonical UTC")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise AuditRecoveryError(f"{label} is not parseable UTC") from exc
    return parsed.astimezone(timezone.utc)


def _utc_text(value: datetime) -> str:
    return (
        value.astimezone(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _write_json_exclusive(path: Path, value: Mapping[str, Any]) -> None:
    lexical = path.expanduser().absolute()
    authorize._require_no_symlink_components(  # noqa: SLF001
        lexical.parent, "exclusive receipt parent"
    )
    if not lexical.parent.is_dir() or lexical.parent.is_symlink():
        raise AuditRecoveryError("exclusive receipt parent is unsafe")
    payload = protocol.canonical_json_bytes(dict(value)) + b"\n"
    descriptor = os.open(lexical, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
    directory_fd = os.open(lexical.parent, os.O_RDONLY)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)


def _file_record(path: Path) -> dict[str, Any]:
    lexical = path.expanduser().absolute()
    authorize._require_no_symlink_components(  # noqa: SLF001
        lexical, "bound recovery file"
    )
    resolved = lexical.resolve(strict=True)
    if not resolved.is_file() or lexical.is_symlink():
        raise AuditRecoveryError(f"bound file is unsafe: {path}")
    return {"bytes": resolved.stat().st_size, "sha256": _sha256(resolved)}


def _execution_binding(
    args: argparse.Namespace, *, git_head: str, validate_execute_paths: bool
) -> dict[str, Any]:
    attempt_id = str(args.attempt_id)
    if ATTEMPT_ID_RE.fullmatch(attempt_id) is None or not attempt_id.startswith(
        f"calv2-r3-audit-recovery-{git_head[:7]}-"
    ):
        raise AuditRecoveryError("recovery attempt identity differs")
    attempt_root = PurePosixPath(RECOVERY_ATTEMPT_PARENT) / attempt_id
    original = attempt_root / "evidence/original"
    fresh = attempt_root / "evidence/fresh"
    expected = {
        "plan_dir": (
            attempt_root / "provenance_repo" / protocol.CANONICAL_PLAN_RELATIVE_PATH
        ).as_posix(),
        "raw_root": f"/workspace/{RAW_RELATIVE}",
        "run_complete": (original / "RUN_COMPLETE.json").as_posix(),
        "raw_ledger": (original / "REMOTE_RAW_SHA256SUMS.txt").as_posix(),
        "raw_inventory": (original / "REMOTE_RAW_INVENTORY.txt").as_posix(),
        "failure_log": (original / "calibration_audit_1a16572.log").as_posix(),
        "original_ownership": (original / "OWNERSHIP.json").as_posix(),
        "original_guest": (original / "GUEST_PREFLIGHT.json").as_posix(),
        "original_cache": (original / "CACHE_PREFLIGHT.json").as_posix(),
        "original_authorization": (
            original / "CALIBRATION_AUTHORIZATION.json"
        ).as_posix(),
        "termination_audit": (original / "TERMINATION_AUDIT.json").as_posix(),
        "postdelete_inventory": (original / "POSTDELETE_INVENTORY.json").as_posix(),
        "frozen_termination": (
            original / "frozen_lifecycle/TERMINATION.json"
        ).as_posix(),
        "fresh_ownership": (fresh / "OWNERSHIP.json").as_posix(),
        "fresh_guest": (fresh / "GUEST_PREFLIGHT.json").as_posix(),
        "fresh_cache": (fresh / "CACHE_PREFLIGHT.json").as_posix(),
        "recovery_authorization": (
            attempt_root / "RECOVERY_AUTHORIZATION.json"
        ).as_posix(),
        "provenance_root": (attempt_root / "provenance_repo").as_posix(),
        "model_snapshot": MODEL_SNAPSHOT_PATH,
        "j_lens_path": J_LENS_PATH,
        "audit_out": (attempt_root / "compact/CALIBRATION_AUDIT.json").as_posix(),
        "summary_out": (attempt_root / "compact/CALIBRATION_SUMMARY.json").as_posix(),
        "attempt_marker": (attempt_root / "ATTEMPT_STARTED.json").as_posix(),
        "failure_out": (attempt_root / "FAILURE.json").as_posix(),
    }
    always_observed = {
        name: getattr(args, name).expanduser().absolute().as_posix()
        for name in (
            "provenance_root",
            "model_snapshot",
            "j_lens_path",
            "audit_out",
            "summary_out",
            "attempt_marker",
            "failure_out",
        )
    }
    observed = dict(always_observed)
    if validate_execute_paths:
        observed.update(
            {
                name: getattr(args, name).expanduser().absolute().as_posix()
                for name in expected
                if name not in observed
            }
        )
    compared = (
        expected
        if validate_execute_paths
        else {name: expected[name] for name in always_observed}
    )
    if observed != compared or args.artifact_device != "cuda:0":
        raise AuditRecoveryError("recovery execution path binding differs")
    core = {
        "attempt_id": attempt_id,
        "attempt_root": attempt_root.as_posix(),
        "paths": expected,
        "artifact_device": "cuda:0",
    }
    return {**core, "command_sha256": protocol.canonical_sha256(core)}


def _closure_records() -> list[dict[str, Any]]:
    records = []
    for relative in RECOVERY_BOUND_PATHS:
        record = _file_record(REPO_ROOT / relative)
        records.append({"path": relative, **record})
    return records


def _provenance_records(paths: Sequence[str]) -> list[dict[str, Any]]:
    records = []
    for relative in sorted(set(paths)):
        safe = authorize._safe_relative(relative, "historical provenance file")  # noqa: SLF001
        record = _file_record(REPO_ROOT / safe)
        records.append({"path": safe, **record})
    if not records:
        raise AuditRecoveryError("historical provenance closure is empty")
    return records


def _historical_provenance_paths(plan: Mapping[str, Any]) -> tuple[str, ...]:
    review_relative = (
        PurePosixPath(protocol.CANONICAL_PLAN_RELATIVE_PATH)
        / "REVIEW_ADJUDICATION.json"
    ).as_posix()
    review_path = REPO_ROOT / review_relative
    review = authorize._json(review_path, "historical review adjudication")  # noqa: SLF001
    _validated, review_paths = authorize._validate_review_adjudication(  # noqa: SLF001
        review,
        review_path=review_path,
        final_plan_manifest_sha256=str(plan["manifest"]["plan_manifest_sha256"]),
    )
    return tuple(sorted(set(plan["bound_paths"]) | set(review_paths)))


def _validate_provenance_tree(root: Path, expected_rows: Any) -> dict[str, Any]:
    lexical = root.expanduser().absolute()
    authorize._require_no_symlink_components(  # noqa: SLF001
        lexical, "historical provenance root"
    )
    resolved = lexical.resolve(strict=True)
    if (
        not resolved.is_dir()
        or resolved.is_symlink()
        or not isinstance(expected_rows, list)
    ):
        raise AuditRecoveryError("historical provenance root differs")
    expected: dict[str, Mapping[str, Any]] = {}
    for row in expected_rows:
        if not isinstance(row, Mapping) or set(row) != {"path", "bytes", "sha256"}:
            raise AuditRecoveryError("historical provenance inventory differs")
        safe = authorize._safe_relative(  # noqa: SLF001
            row["path"], "historical provenance file"
        )
        if safe in expected:
            raise AuditRecoveryError("historical provenance path is duplicated")
        expected[safe] = row
    observed: list[dict[str, Any]] = []
    for path in resolved.rglob("*"):
        if path.is_symlink():
            raise AuditRecoveryError("historical provenance contains a symlink")
        if not path.is_file():
            continue
        relative = path.relative_to(resolved).as_posix()
        details = path.stat()
        row = expected.get(relative)
        digest = _sha256(path)
        if (
            row is None
            or details.st_nlink != 1
            or details.st_size != row["bytes"]
            or digest != row["sha256"]
        ):
            raise AuditRecoveryError(f"historical provenance differs: {relative}")
        observed.append({"path": relative, "bytes": details.st_size, "sha256": digest})
    observed.sort(key=lambda row: str(row["path"]))
    if observed != expected_rows:
        raise AuditRecoveryError("historical provenance tree inventory differs")
    core = {
        "status": "pass_exact_nonimportable_historical_provenance",
        "root": resolved.as_posix(),
        "file_count": len(observed),
        "file_inventory_sha256": protocol.canonical_sha256(observed),
    }
    return {**core, "receipt_sha256": protocol.canonical_sha256(core)}


@contextlib.contextmanager
def _historical_provenance_context(root: Path) -> Iterator[None]:
    resolved = root.expanduser().resolve(strict=True)
    original_authorize_root = authorize.REPO_ROOT
    original_validate_root = validate_plan.REPO_ROOT
    authorize.REPO_ROOT = resolved
    validate_plan.REPO_ROOT = resolved
    try:
        yield
    finally:
        authorize.REPO_ROOT = original_authorize_root
        validate_plan.REPO_ROOT = original_validate_root


def _validate_executable_isolation(
    provenance_root: Path, authorization: Mapping[str, Any]
) -> dict[str, Any]:
    provenance = provenance_root.expanduser().resolve(strict=True)
    active = REPO_ROOT.resolve(strict=True)
    if active == provenance:
        raise AuditRecoveryError("historical provenance is on the executable root")
    for entry in sys.path:
        try:
            candidate = (
                Path.cwd().resolve(strict=True)
                if not entry
                else Path(entry).expanduser().resolve(strict=True)
            )
        except OSError:
            continue
        if (
            candidate == provenance
            or provenance in candidate.parents
            or candidate in provenance.parents
        ):
            raise AuditRecoveryError("historical provenance is importable")
    if any((active / relative).exists() for relative in FORBIDDEN_EXECUTABLE_PATHS):
        raise AuditRecoveryError("model runner/runtime exists on the executable root")
    observed = sorted(
        path.relative_to(active).as_posix()
        for path in active.rglob("*")
        if path.is_file()
    )
    if observed != list(RECOVERY_BOUND_PATHS):
        raise AuditRecoveryError("audit-only executable inventory differs")
    closure = _closure_records()
    if authorization.get("recovery_bound_files") != closure:
        raise AuditRecoveryError("audit-only executable bytes differ")
    loaded_forbidden = [
        name
        for name in FORBIDDEN_MODULES
        if name in sys.modules
        and not (
            name == _RUNTIME_MODULE_NAME and sys.modules[name] is audit_runtime_shim
        )
    ]
    if loaded_forbidden:
        raise AuditRecoveryError("a forbidden runner/runtime module is already loaded")
    core = {
        "status": "pass_minimal_audit_only_executable",
        "active_root": active.as_posix(),
        "historical_provenance_root": provenance.as_posix(),
        "file_count": len(closure),
        "file_inventory_sha256": protocol.canonical_sha256(closure),
        "forbidden_module_count": 0,
        "model_runtime_replaced_by": (
            "experiments.consciousness_sae_target_blind_calibration.audit_runtime_shim"
        ),
    }
    return {**core, "receipt_sha256": protocol.canonical_sha256(core)}


@contextlib.contextmanager
def _forbidden_module_guard() -> Iterator[dict[str, int]]:
    counts = {"forbidden_module_import_attempts": 0}

    class _DenyFinder:
        @staticmethod
        def find_spec(fullname: str, _path: Any = None, _target: Any = None) -> None:
            if fullname in FORBIDDEN_MODULES:
                counts["forbidden_module_import_attempts"] += 1
                raise AuditRecoveryError(
                    f"forbidden model runner/runtime import: {fullname}"
                )
            return None

    finder = _DenyFinder()
    sys.meta_path.insert(0, finder)
    try:
        yield counts
    finally:
        if finder in sys.meta_path:
            sys.meta_path.remove(finder)


def _validate_review_evidence() -> dict[str, Any]:
    root = (
        REPO_ROOT / "docs/consciousness_sae_target_blind_calibration/reviews/"
        "audit_recovery_gpt_pro_20260714_live"
    )
    response = _json(root / "response.json")
    manifest = _json(root / "review_manifest.json")
    failure = _json(root / "failure.json")
    usage = response.get("usage")
    incomplete = response.get("incomplete_details")
    if (
        response.get("id") != "resp_0ae53ab3f19b0df6016a56d79f0f5c8199bae81011a0ff14c3"
        or response.get("model") != "gpt-5.6-sol"
        or response.get("status") != "incomplete"
        or not isinstance(incomplete, Mapping)
        or incomplete.get("reason") != "max_output_tokens"
        or not isinstance(usage, Mapping)
        or usage.get("input_tokens") != 20570
        or usage.get("output_tokens") != 8215
        or manifest.get("status") != "failed"
        or manifest.get("official_latest_model") != "gpt-5.6-sol"
        or manifest.get("budget_authorization_usd") != 0.75
        or failure.get("error_type") != "RuntimeError"
    ):
        raise AuditRecoveryError("bounded Pro review evidence differs")
    reconstructed = (
        float(usage["input_tokens"]) * 5.0 / 1_000_000
        + float(usage["output_tokens"]) * 30.0 / 1_000_000
    )
    if not math.isclose(reconstructed, 0.3493, abs_tol=1e-12):
        raise AuditRecoveryError("review cost reconstruction differs")
    return {
        "model": "gpt-5.6-sol",
        "provider_status": "incomplete",
        "incomplete_reason": "max_output_tokens",
        "response_id": response["id"],
        "input_tokens": usage["input_tokens"],
        "output_tokens": usage["output_tokens"],
        "reasoning_tokens": usage.get("output_tokens_details", {}).get(
            "reasoning_tokens"
        ),
        "reconstructed_cost_usd": reconstructed,
        "provider_approval_claimed": False,
        "source_and_tests_reviewed_by_provider": False,
        "second_paid_call_made": False,
    }


def _validate_run_and_ledgers(
    *,
    run_complete_path: Path,
    raw_ledger_path: Path,
    raw_inventory_path: Path,
    failure_log_path: Path,
) -> dict[str, Any]:
    if _sha256(run_complete_path) != ORIGINAL_RUN_FILE_SHA256:
        raise AuditRecoveryError("RUN_COMPLETE physical hash differs")
    if _sha256(raw_ledger_path) != ORIGINAL_RAW_LEDGER_SHA256:
        raise AuditRecoveryError("raw SHA ledger physical hash differs")
    if _sha256(raw_inventory_path) != ORIGINAL_RAW_INVENTORY_SHA256:
        raise AuditRecoveryError("raw inventory physical hash differs")
    if _sha256(failure_log_path) != ORIGINAL_FAILURE_LOG_SHA256:
        raise AuditRecoveryError("failed-audit log physical hash differs")
    if "J-lens map inventory differs" not in failure_log_path.read_text(
        encoding="utf-8"
    ):
        raise AuditRecoveryError("failed-audit reason differs")
    complete = _json(run_complete_path)
    if (
        _self_hash(complete, "RUN_COMPLETE") != ORIGINAL_RUN_RECEIPT_SHA256
        or complete.get("status") != "complete"
        or complete.get("run_id") != RUN_ID
        or complete.get("plan_manifest_sha256")
        != "aa80cef7ef36fed327fcce99547c0b3bdf92a059c1dea43abba0ba924f404636"
        or complete.get("stored_bytes") != 323365550
        or complete.get("target_prompt_render_count") != 0
        or complete.get("target_feature_vector_count") != 0
        or complete.get("analysis_data_inputs") != []
        or complete.get("runtime", {}).get("model_forward_count") != 256
    ):
        raise AuditRecoveryError("RUN_COMPLETE identity differs")
    records = complete.get("records")
    if not isinstance(records, list) or len(records) != 35:
        raise AuditRecoveryError("RUN_COMPLETE manifest differs")
    prefix = f"/workspace/{RAW_RELATIVE}/"
    hashes: dict[str, str] = {}
    for line in raw_ledger_path.read_text(encoding="utf-8").splitlines():
        digest, separator, absolute = line.partition("  ")
        if (
            separator != "  "
            or HEX64.fullmatch(digest) is None
            or not absolute.startswith(prefix)
        ):
            raise AuditRecoveryError("raw SHA ledger row differs")
        relative = absolute.removeprefix(prefix)
        if relative in hashes:
            raise AuditRecoveryError("raw SHA ledger path is duplicated")
        hashes[relative] = digest
    sizes: dict[str, int] = {}
    for line in raw_inventory_path.read_text(encoding="utf-8").splitlines():
        size_text, separator, absolute = line.partition(" ")
        if separator != " " or not absolute.startswith(prefix):
            raise AuditRecoveryError("raw inventory row differs")
        relative = absolute.removeprefix(prefix)
        if relative in sizes:
            raise AuditRecoveryError("raw inventory path is duplicated")
        try:
            sizes[relative] = int(size_text)
        except ValueError as exc:
            raise AuditRecoveryError("raw inventory size differs") from exc
    expected = {str(row["path"]) for row in records} | {"RUN_COMPLETE.json"}
    if set(hashes) != expected or set(sizes) != expected:
        raise AuditRecoveryError("external raw inventory differs")
    for row in records:
        relative = str(row["path"])
        if hashes[relative] != row["sha256"] or sizes[relative] != row["bytes"]:
            raise AuditRecoveryError("external raw ledger/manifest differs")
    if (
        hashes["RUN_COMPLETE.json"] != ORIGINAL_RUN_FILE_SHA256
        or sizes["RUN_COMPLETE.json"] != run_complete_path.stat().st_size
    ):
        raise AuditRecoveryError("external completion-receipt row differs")
    return complete


def _validate_original_chain(
    *,
    plan_dir: Path,
    ownership_path: Path,
    guest_path: Path,
    cache_path: Path,
    authorization_path: Path,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    ownership_raw = _json(ownership_path)
    guest_raw = _json(guest_path)
    cache_raw = _json(cache_path)
    authorization_raw = _json(authorization_path)
    try:
        ownership = runpod_preflight.validate_ownership_receipt(ownership_raw)
        guest = runpod_preflight.validate_guest_receipt(
            guest_raw, ownership_receipt=ownership
        )
        cache = runpod_preflight.validate_cache_receipt(
            cache_raw, guest_receipt=guest, ownership_receipt=ownership
        )
        plan = authorize._validate_plan(plan_dir)  # noqa: SLF001
        historical_now = _utc(
            str(authorization_raw["authorized_at_utc"]), "old authorization time"
        ).timestamp()
        authorization = authorize.validate_execution_authorization(
            authorization_raw,
            plan=plan["manifest"],
            plan_manifest_path=plan["manifest_path"],
            source_files_path=plan["source_path"],
            ownership=ownership,
            guest=guest,
            cache=cache,
            now_unix=historical_now,
        )
    except (runpod_preflight.PreflightError, authorize.AuthorizationError) as exc:
        raise AuditRecoveryError("original execution receipt chain failed") from exc
    return ownership, guest, cache, authorization


def _validate_fresh_chain(
    *, ownership_path: Path, guest_path: Path, cache_path: Path
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    try:
        ownership = runpod_preflight.validate_ownership_receipt(_json(ownership_path))
        guest = runpod_preflight.validate_guest_receipt(
            _json(guest_path), ownership_receipt=ownership
        )
        cache = runpod_preflight.validate_cache_receipt(
            _json(cache_path), guest_receipt=guest, ownership_receipt=ownership
        )
    except runpod_preflight.PreflightError as exc:
        raise AuditRecoveryError("fresh audit-host receipt chain failed") from exc
    if (
        ownership.get("network_volume_id") != protocol.NETWORK_VOLUME_ID
        or ownership.get("data_center_id") != protocol.DATA_CENTER_ID
        or ownership.get("gpu_type") != protocol.GPU_TYPE
        or ownership.get("gpu_count") != 1
        or guest.get("model_forward_count") != 0
        or guest.get("target_prompt_render_count") != 0
        or guest.get("prior_outcome_inputs") != []
        or cache.get("model_forward_count") != 0
        or cache.get("target_prompt_render_count") != 0
        or cache.get("prior_outcome_inputs") != []
        or cache.get("independently_rehashed") is not True
        or cache.get("read_only") is not True
    ):
        raise AuditRecoveryError("fresh audit host is not zero-forward/target-free")
    return ownership, guest, cache


def _validate_fresh_authority_clock(
    receipt: Mapping[str, Any], ownership: Mapping[str, Any], *, now_unix: float
) -> None:
    started = float(receipt["recovery_started_at_unix"])
    deadline = float(receipt["recovery_deadline_at_unix"])
    provider_deadline = float(receipt["provider_deadline_at_unix"])
    created = _utc(str(ownership["created_at"]), "fresh pod creation")
    exact_provider_deadline = _utc(
        str(ownership["terminate_after"]), "fresh provider deadline"
    )
    authorized = _utc(str(receipt.get("authorized_at_utc", "")), "authorized_at")
    if (
        started != created.timestamp()
        or deadline != created.timestamp() + RECOVERY_SECONDS
        or provider_deadline != exact_provider_deadline.timestamp()
        or not created <= authorized < datetime.fromtimestamp(deadline, timezone.utc)
        or authorized.timestamp() > now_unix
    ):
        raise AuditRecoveryError("recovery clock is not fresh-ownership-bound")


def issue_authorization(args: argparse.Namespace) -> dict[str, Any]:
    plan = authorize._validate_plan(args.plan_dir)  # noqa: SLF001
    closure = _closure_records()
    provenance_paths = _historical_provenance_paths(plan)
    provenance = _provenance_records(provenance_paths)
    bound_paths = set(provenance_paths) | set(RECOVERY_BOUND_PATHS)
    authorize._verify_committed_paths(tuple(bound_paths))  # noqa: SLF001
    git = authorize._live_remote_freeze()  # noqa: SLF001
    execution = _execution_binding(
        args, git_head=git["git_head_commit"], validate_execute_paths=False
    )
    review = _validate_review_evidence()
    complete = _validate_run_and_ledgers(
        run_complete_path=args.run_complete,
        raw_ledger_path=args.raw_ledger,
        raw_inventory_path=args.raw_inventory,
        failure_log_path=args.failure_log,
    )
    old_ownership, old_guest, old_cache, old_authorization = _validate_original_chain(
        plan_dir=args.plan_dir,
        ownership_path=args.original_ownership,
        guest_path=args.original_guest,
        cache_path=args.original_cache,
        authorization_path=args.original_authorization,
    )
    fresh_ownership, fresh_guest, fresh_cache = _validate_fresh_chain(
        ownership_path=args.fresh_ownership,
        guest_path=args.fresh_guest,
        cache_path=args.fresh_cache,
    )
    term = _json(args.termination_audit)
    postdelete = _json(args.postdelete_inventory)
    frozen_term = _json(args.frozen_termination)
    if (
        _self_hash(term, "old termination audit")
        != "b346b5c575ba1a903d93874b6dea58101cd208539ef5e30e8d069955d864ebfd"
        or term.get("pod_id") != old_ownership.get("pod_id")
        or term.get("status") != "deleted_exact_owned_pod_unrelated_inventory_unchanged"
        or _self_hash(postdelete, "old post-delete inventory")
        != "7d1631e8dc248e61e36bc71193857a07e430fc012acb861907e1fb89b0fbf022"
        or postdelete.get("pods") != []
        or postdelete.get("all_account_pod_count") != 0
        or _self_hash(frozen_term, "old frozen termination")
        != "86d0efdcf0b54b927bd3062ff448d0abf3d12aa873c837766249e1b7a110dfe5"
    ):
        raise AuditRecoveryError("old pod termination evidence differs")
    if args.hourly_price_usd != RECOVERY_RATE_USD_PER_HOUR:
        raise AuditRecoveryError("recovery accounting rate differs")
    raw_root = args.raw_root.expanduser().absolute()
    if raw_root.as_posix() != f"/workspace/{RAW_RELATIVE}":
        raise AuditRecoveryError("recovery raw root differs")
    created = _utc(str(fresh_ownership["created_at"]), "fresh pod creation")
    deadline = created + timedelta(seconds=RECOVERY_SECONDS)
    provider_deadline = _utc(
        str(fresh_ownership["terminate_after"]), "fresh provider deadline"
    )
    now = datetime.now(timezone.utc)
    if not created <= now < deadline < provider_deadline:
        raise AuditRecoveryError("fresh recovery authorization window differs")
    external_paths = {
        "run_complete": args.run_complete,
        "raw_ledger": args.raw_ledger,
        "raw_inventory": args.raw_inventory,
        "failure_log": args.failure_log,
        "original_ownership": args.original_ownership,
        "original_guest": args.original_guest,
        "original_cache": args.original_cache,
        "original_authorization": args.original_authorization,
        "termination_audit": args.termination_audit,
        "postdelete_inventory": args.postdelete_inventory,
        "frozen_termination": args.frozen_termination,
        "fresh_ownership": args.fresh_ownership,
        "fresh_guest": args.fresh_guest,
        "fresh_cache": args.fresh_cache,
    }
    external = {
        name: _file_record(path) for name, path in sorted(external_paths.items())
    }
    core = {
        "schema_version": 1,
        "status": "authorized_audit_only_recovery",
        "study_id": protocol.STUDY_ID,
        "protocol_version": protocol.PROTOCOL_VERSION,
        "recovery_protocol_version": RECOVERY_PROTOCOL_VERSION,
        "run_id": RUN_ID,
        "raw_root": raw_root.as_posix(),
        "raw_run_receipt_sha256": complete["receipt_sha256"],
        "plan_manifest_sha256": plan["manifest"]["plan_manifest_sha256"],
        "recovery_bound_files": closure,
        "recovery_bound_paths_sha256": protocol.canonical_sha256(
            tuple(row["path"] for row in closure)
        ),
        "historical_provenance_files": provenance,
        "historical_provenance_inventory_sha256": protocol.canonical_sha256(provenance),
        "external_files": external,
        "original_receipts": {
            "ownership": old_ownership["receipt_sha256"],
            "guest": old_guest["receipt_sha256"],
            "cache": old_cache["receipt_sha256"],
            "authorization": old_authorization["receipt_sha256"],
            "termination_audit": term["receipt_sha256"],
            "frozen_termination": frozen_term["receipt_sha256"],
        },
        "fresh_receipts": {
            "ownership": fresh_ownership["receipt_sha256"],
            "guest": fresh_guest["receipt_sha256"],
            "cache": fresh_cache["receipt_sha256"],
        },
        "fresh_pod_id": fresh_ownership["pod_id"],
        "volume_id": protocol.NETWORK_VOLUME_ID,
        "data_center_id": protocol.DATA_CENTER_ID,
        "gpu_type": protocol.GPU_TYPE,
        "gpu_count": 1,
        "recovery_started_at_unix": created.timestamp(),
        "recovery_deadline_at_unix": deadline.timestamp(),
        "provider_deadline_at_unix": provider_deadline.timestamp(),
        "max_walltime_seconds": RECOVERY_SECONDS,
        "hourly_price_usd": RECOVERY_RATE_USD_PER_HOUR,
        "max_spend_usd": RECOVERY_MAX_SPEND_USD,
        "authorized_at_utc": _utc_text(now),
        "model_forward_limit": 0,
        "target_prompt_render_limit": 0,
        "target_feature_vector_limit": 0,
        "external_or_prior_outcome_inputs": [],
        "execution": execution,
        "review": review,
        **git,
    }
    return {**core, "receipt_sha256": protocol.canonical_sha256(core)}


def validate_recovery_authorization(
    value: Mapping[str, Any], args: argparse.Namespace, *, now_unix: float | None = None
) -> dict[str, Any]:
    receipt = dict(value)
    _self_hash(receipt, "recovery authorization")
    if (
        receipt.get("schema_version") != 1
        or receipt.get("status") != "authorized_audit_only_recovery"
        or receipt.get("study_id") != protocol.STUDY_ID
        or receipt.get("protocol_version") != protocol.PROTOCOL_VERSION
        or receipt.get("recovery_protocol_version") != RECOVERY_PROTOCOL_VERSION
        or receipt.get("run_id") != RUN_ID
        or receipt.get("raw_root") != f"/workspace/{RAW_RELATIVE}"
        or receipt.get("raw_run_receipt_sha256") != ORIGINAL_RUN_RECEIPT_SHA256
        or receipt.get("plan_manifest_sha256")
        != "aa80cef7ef36fed327fcce99547c0b3bdf92a059c1dea43abba0ba924f404636"
        or receipt.get("volume_id") != protocol.NETWORK_VOLUME_ID
        or receipt.get("data_center_id") != protocol.DATA_CENTER_ID
        or receipt.get("gpu_type") != protocol.GPU_TYPE
        or receipt.get("gpu_count") != 1
        or receipt.get("max_walltime_seconds") != RECOVERY_SECONDS
        or receipt.get("hourly_price_usd") != RECOVERY_RATE_USD_PER_HOUR
        or receipt.get("max_spend_usd") != RECOVERY_MAX_SPEND_USD
        or receipt.get("model_forward_limit") != 0
        or receipt.get("target_prompt_render_limit") != 0
        or receipt.get("target_feature_vector_limit") != 0
        or receipt.get("external_or_prior_outcome_inputs") != []
    ):
        raise AuditRecoveryError("recovery authorization identity differs")
    execution = _execution_binding(
        args,
        git_head=str(receipt.get("git_head_commit", "")),
        validate_execute_paths=True,
    )
    if receipt.get("execution") != execution:
        raise AuditRecoveryError("recovery execution binding differs")
    started = float(receipt["recovery_started_at_unix"])
    deadline = float(receipt["recovery_deadline_at_unix"])
    provider_deadline = float(receipt["provider_deadline_at_unix"])
    now = time.time() if now_unix is None else float(now_unix)
    if (
        not all(math.isfinite(v) for v in (started, deadline, provider_deadline, now))
        or deadline - started != RECOVERY_SECONDS
        or deadline >= provider_deadline
        or not started <= now < deadline
        or RECOVERY_RATE_USD_PER_HOUR * (deadline - started) / 3600
        != RECOVERY_MAX_SPEND_USD
    ):
        raise AuditRecoveryError("recovery authorization budget window differs")
    closure = _closure_records()
    if receipt.get("recovery_bound_files") != closure or receipt.get(
        "recovery_bound_paths_sha256"
    ) != protocol.canonical_sha256(tuple(row["path"] for row in closure)):
        raise AuditRecoveryError("recovery committed source closure differs")
    review = _validate_review_evidence()
    if receipt.get("review") != review:
        raise AuditRecoveryError("recovery review binding differs")
    provenance_rows = receipt.get("historical_provenance_files")
    if not isinstance(provenance_rows, list) or receipt.get(
        "historical_provenance_inventory_sha256"
    ) != protocol.canonical_sha256(provenance_rows):
        raise AuditRecoveryError("historical provenance authorization differs")
    provenance_root = args.provenance_root.expanduser().absolute()
    expected_plan_dir = provenance_root / protocol.CANONICAL_PLAN_RELATIVE_PATH
    if args.plan_dir.expanduser().absolute() != expected_plan_dir:
        raise AuditRecoveryError("historical plan path differs")
    _validate_provenance_tree(provenance_root, provenance_rows)
    complete = _validate_run_and_ledgers(
        run_complete_path=args.run_complete,
        raw_ledger_path=args.raw_ledger,
        raw_inventory_path=args.raw_inventory,
        failure_log_path=args.failure_log,
    )
    with _historical_provenance_context(provenance_root):
        old_ownership, old_guest, old_cache, old_authorization = (
            _validate_original_chain(
                plan_dir=args.plan_dir,
                ownership_path=args.original_ownership,
                guest_path=args.original_guest,
                cache_path=args.original_cache,
                authorization_path=args.original_authorization,
            )
        )
    fresh_ownership, fresh_guest, fresh_cache = _validate_fresh_chain(
        ownership_path=args.fresh_ownership,
        guest_path=args.fresh_guest,
        cache_path=args.fresh_cache,
    )
    _validate_fresh_authority_clock(receipt, fresh_ownership, now_unix=now)
    expected_old = {
        "ownership": old_ownership["receipt_sha256"],
        "guest": old_guest["receipt_sha256"],
        "cache": old_cache["receipt_sha256"],
        "authorization": old_authorization["receipt_sha256"],
        "termination_audit": _json(args.termination_audit)["receipt_sha256"],
        "frozen_termination": _json(args.frozen_termination)["receipt_sha256"],
    }
    expected_fresh = {
        "ownership": fresh_ownership["receipt_sha256"],
        "guest": fresh_guest["receipt_sha256"],
        "cache": fresh_cache["receipt_sha256"],
    }
    if (
        receipt.get("original_receipts") != expected_old
        or receipt.get("fresh_receipts") != expected_fresh
        or receipt.get("fresh_pod_id") != fresh_ownership["pod_id"]
        or complete["receipt_sha256"] != receipt["raw_run_receipt_sha256"]
    ):
        raise AuditRecoveryError("recovery dual receipt chain differs")
    external_paths = {
        "run_complete": args.run_complete,
        "raw_ledger": args.raw_ledger,
        "raw_inventory": args.raw_inventory,
        "failure_log": args.failure_log,
        "original_ownership": args.original_ownership,
        "original_guest": args.original_guest,
        "original_cache": args.original_cache,
        "original_authorization": args.original_authorization,
        "termination_audit": args.termination_audit,
        "postdelete_inventory": args.postdelete_inventory,
        "frozen_termination": args.frozen_termination,
        "fresh_ownership": args.fresh_ownership,
        "fresh_guest": args.fresh_guest,
        "fresh_cache": args.fresh_cache,
    }
    expected_external = {
        name: _file_record(path) for name, path in sorted(external_paths.items())
    }
    if receipt.get("external_files") != expected_external:
        raise AuditRecoveryError("recovery external file closure differs")
    env_expected = {
        "RUNPOD_POD_ID": str(fresh_ownership["pod_id"]),
        "RUNPOD_VOLUME_ID": protocol.NETWORK_VOLUME_ID,
        "RUNPOD_DC_ID": protocol.DATA_CENTER_ID,
    }
    if any(os.environ.get(name) != expected for name, expected in env_expected.items()):
        raise AuditRecoveryError("recovery process is outside the fresh owned guest")
    return receipt


def _decode_mount_path(value: str) -> str:
    return (
        value.replace("\\040", " ")
        .replace("\\011", "\t")
        .replace("\\012", "\n")
        .replace("\\134", "\\")
    )


def _mountinfo_rows(text: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in text.splitlines():
        fields = line.split()
        try:
            separator = fields.index("-")
        except ValueError as exc:
            raise AuditRecoveryError("mountinfo row is malformed") from exc
        if separator < 6 or len(fields) != separator + 4:
            raise AuditRecoveryError("mountinfo row is malformed")
        try:
            mount_id = int(fields[0])
            parent_id = int(fields[1])
        except ValueError as exc:
            raise AuditRecoveryError("mountinfo identity is malformed") from exc
        rows.append(
            {
                "mount_id": mount_id,
                "parent_id": parent_id,
                "device": fields[2],
                "root": _decode_mount_path(fields[3]),
                "mountpoint": _decode_mount_path(fields[4]),
                "options": fields[5].split(","),
                "optional_fields": fields[6:separator],
                "filesystem_type": fields[separator + 1],
                "mount_source": _decode_mount_path(fields[separator + 2]),
                "super_options": fields[separator + 3].split(","),
            }
        )
    return rows


def _validate_bind_provenance(
    target: Mapping[str, Any], workspace: Mapping[str, Any], expected: str
) -> str:
    try:
        relative = PurePosixPath(expected).relative_to("/workspace")
    except ValueError as exc:
        raise AuditRecoveryError("raw root is outside the volume mount") from exc
    expected_root = (PurePosixPath(str(workspace["root"])) / relative).as_posix()
    if (
        target["root"] != expected_root
        or target["device"] != workspace["device"]
        or target["filesystem_type"] != workspace["filesystem_type"]
        or target["mount_source"] != workspace["mount_source"]
        or target["mount_id"] == workspace["mount_id"]
        or target["parent_id"] != workspace["mount_id"]
    ):
        raise AuditRecoveryError(
            "raw mount is not a bind of the canonical volume subtree"
        )
    return expected_root


def _verify_read_only_bind_mount(root: Path, *, role: str) -> dict[str, Any]:
    resolved = root.resolve(strict=True)
    expected = resolved.as_posix()
    try:
        rows = _mountinfo_rows(Path("/proc/self/mountinfo").read_text(encoding="utf-8"))
    except OSError as exc:
        raise AuditRecoveryError("mountinfo is unavailable") from exc
    matching = [row for row in rows if row["mountpoint"] == expected]
    workspace = [row for row in rows if row["mountpoint"] == "/workspace"]
    descendants = [
        str(row["mountpoint"])
        for row in rows
        if str(row["mountpoint"]).startswith(expected + "/")
    ]
    readonly_flag = getattr(os, "ST_RDONLY", 1)
    stat_readonly = bool(os.statvfs(resolved).f_flag & readonly_flag)
    if (
        len(matching) != 1
        or len(workspace) != 1
        or "ro" not in matching[0]["options"]
        or descendants
        or not stat_readonly
    ):
        raise AuditRecoveryError("canonical raw tree is not one exact read-only mount")
    expected_bind_root = _validate_bind_provenance(matching[0], workspace[0], expected)
    core = {
        "status": "pass_kernel_read_only_exact_bind_mount",
        "role": role,
        "bound_root": expected,
        "mount": matching[0],
        "workspace_mount": workspace[0],
        "expected_bind_root": expected_bind_root,
        "descendant_mounts": descendants,
        "statvfs_read_only": stat_readonly,
    }
    return {**core, "receipt_sha256": protocol.canonical_sha256(core)}


def _verify_read_only_mount(raw_root: Path) -> dict[str, Any]:
    return _verify_read_only_bind_mount(raw_root, role="canonical_raw_transaction")


def _parse_external_raw_ledger(path: Path, raw_root: Path) -> dict[str, str]:
    prefix = raw_root.resolve(strict=True).as_posix() + "/"
    result: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        digest, separator, absolute = line.partition("  ")
        if (
            separator != "  "
            or HEX64.fullmatch(digest) is None
            or not absolute.startswith(prefix)
        ):
            raise AuditRecoveryError("raw ledger row escaped canonical root")
        relative = absolute.removeprefix(prefix)
        if (
            not relative
            or relative.startswith("/")
            or ".." in Path(relative).parts
            or relative in result
        ):
            raise AuditRecoveryError("raw ledger contains an unsafe/duplicate path")
        result[relative] = digest
    return result


def _rehash_raw_tree(raw_root: Path, raw_ledger_path: Path) -> dict[str, Any]:
    root = raw_root.resolve(strict=True)
    expected = _parse_external_raw_ledger(raw_ledger_path, root)
    rows: list[dict[str, Any]] = []
    observed_paths: set[str] = set()
    for path in root.rglob("*"):
        if path.is_symlink():
            raise AuditRecoveryError("raw tree contains a symlink")
        if not path.is_file():
            continue
        relative = path.relative_to(root).as_posix()
        if relative in observed_paths:
            raise AuditRecoveryError("raw tree path is duplicated")
        details = path.stat()
        if details.st_nlink != 1:
            raise AuditRecoveryError("raw file has a non-unique hard link")
        digest = _sha256(path)
        if expected.get(relative) != digest:
            raise AuditRecoveryError(f"raw file hash differs: {relative}")
        rows.append({"path": relative, "bytes": details.st_size, "sha256": digest})
        observed_paths.add(relative)
    rows.sort(key=lambda row: str(row["path"]))
    if set(expected) != observed_paths or len(rows) != 36:
        raise AuditRecoveryError("raw tree inventory differs")
    complete = _json(root / "RUN_COMPLETE.json")
    if _self_hash(complete, "mounted RUN_COMPLETE") != ORIGINAL_RUN_RECEIPT_SHA256:
        raise AuditRecoveryError("mounted RUN_COMPLETE self-hash differs")
    records = complete.get("records")
    if not isinstance(records, list) or len(records) != 35:
        raise AuditRecoveryError("mounted RUN_COMPLETE manifest differs")
    by_path = {str(row["path"]): row for row in rows}
    for record in records:
        row = by_path.get(str(record.get("path")))
        if (
            row is None
            or row["bytes"] != record.get("bytes")
            or row["sha256"] != record.get("sha256")
        ):
            raise AuditRecoveryError("mounted raw manifest/file differs")
    core = {
        "status": "pass_exact_36_file_rehash",
        "raw_root": root.as_posix(),
        "file_count": len(rows),
        "total_bytes": sum(int(row["bytes"]) for row in rows),
        "file_inventory_sha256": protocol.canonical_sha256(rows),
        "run_receipt_sha256": complete["receipt_sha256"],
        "external_ledger_file_sha256": _sha256(raw_ledger_path),
    }
    return {**core, "receipt_sha256": protocol.canonical_sha256(core)}


def _normalize_j_inventory(maps: Mapping[Any, Any]) -> tuple[int, ...]:
    seen: set[int] = set()
    for key in maps:
        if isinstance(key, bool):
            raise audit.CalibrationAuditError("J-lens layer identifier is noncanonical")
        if isinstance(key, int):
            layer = key
        elif isinstance(key, str):
            try:
                layer = int(key)
            except ValueError as exc:
                raise audit.CalibrationAuditError(
                    "J-lens layer identifier is noncanonical"
                ) from exc
            if key != str(layer):
                raise audit.CalibrationAuditError(
                    "J-lens layer identifier is noncanonical"
                )
        else:
            raise audit.CalibrationAuditError("J-lens layer identifier is noncanonical")
        if layer in seen:
            raise audit.CalibrationAuditError("J-lens layer identifier is duplicated")
        seen.add(layer)
    return tuple(sorted(seen))


_OBSERVED_J_INVENTORY: dict[str, Any] | None = None


def _load_j_checkpoint_recovery(
    j_lens_path: Path, watchdog: Any
) -> tuple[Path, Mapping[Any, Any], dict[str, Any]]:
    import torch

    global _OBSERVED_J_INVENTORY  # noqa: PLW0603
    lexical = j_lens_path.expanduser().absolute()
    if lexical.is_symlink():
        raise audit.CalibrationAuditError("J-lens checkpoint is a symlink")
    path = lexical.resolve(strict=True)
    watchdog.check()
    if (
        not path.is_file()
        or protocol.sha256_file(path) != protocol.J_LENS_SPEC["sha256"]
    ):
        raise audit.CalibrationAuditError("J-lens checkpoint hash differs")
    watchdog.check()
    checkpoint = torch.load(path, map_location="cpu", weights_only=True, mmap=True)
    if (
        not isinstance(checkpoint, Mapping)
        or not {"J", "n_prompts", "d_model"} <= set(checkpoint)
        or int(checkpoint["n_prompts"])
        != int(protocol.J_LENS_SPEC["release_config"]["prompts_fitted"])
        or int(checkpoint["d_model"]) != protocol.WIDTH
        or not isinstance(checkpoint["J"], Mapping)
    ):
        raise audit.CalibrationAuditError("J-lens checkpoint metadata differs")
    maps = checkpoint["J"]
    available = _normalize_j_inventory(maps)
    required = tuple(protocol.J_LAYERS)
    if not set(required) <= set(available):
        raise audit.CalibrationAuditError("J-lens map inventory differs")
    if available != EXPECTED_RELEASE_LAYERS:
        raise audit.CalibrationAuditError("J-lens release inventory differs")
    filtered = {
        layer: maps[layer] if layer in maps else maps[str(layer)] for layer in required
    }
    extras = tuple(layer for layer in available if layer not in set(required))
    inventory = {
        "available_layers": list(available),
        "required_layers": list(required),
        "unused_extra_layers": list(extras),
        "available_map_count": len(available),
        "required_map_count": len(required),
        "inventory_sha256": protocol.canonical_sha256(list(available)),
    }
    _OBSERVED_J_INVENTORY = inventory
    return (
        path,
        filtered,
        {
            "sha256": protocol.J_LENS_SPEC["sha256"],
            "map_count": len(available),
            **inventory,
            "revision": protocol.J_LENS_SPEC["revision"],
        },
    )


@contextlib.contextmanager
def _zero_forward_guards() -> Iterator[dict[str, int]]:
    import torch
    import transformers
    from transformers.models.auto.auto_factory import _BaseAutoModelClass

    counts = {"torch_module_calls": 0, "transformers_model_load_calls": 0}
    original_call_impl = torch.nn.Module._call_impl

    def blocked_module_call(*_args: Any, **_kwargs: Any) -> Any:
        counts["torch_module_calls"] += 1
        raise AuditRecoveryError("a torch.nn.Module call is forbidden in recovery")

    torch.nn.Module._call_impl = blocked_module_call
    restored: list[tuple[Any, Any]] = []
    try:
        loader_bases = [transformers.PreTrainedModel, _BaseAutoModelClass]
        for optional_name in ("TFPreTrainedModel", "FlaxPreTrainedModel"):
            optional = vars(transformers).get(optional_name)
            if optional is not None:
                loader_bases.append(optional)
        for cls in loader_bases:
            descriptor = cls.__dict__["from_pretrained"]
            restored.append((cls, descriptor))

            def blocked_loader(_cls: Any, *_args: Any, **_kwargs: Any) -> Any:
                counts["transformers_model_load_calls"] += 1
                raise AuditRecoveryError(
                    "a Transformers model load is forbidden in recovery"
                )

            setattr(cls, "from_pretrained", classmethod(blocked_loader))
        yield counts
    finally:
        torch.nn.Module._call_impl = original_call_impl
        for cls, descriptor in restored:
            setattr(cls, "from_pretrained", descriptor)


def _recovery_watchdog_class(authorization: Mapping[str, Any]) -> type:
    class RecoveryWatchdog:
        def __init__(
            self,
            _binding: Mapping[str, Any],
            *,
            audit_started_at_unix: float | None = None,
        ) -> None:
            self.started = float(authorization["recovery_started_at_unix"])
            self.deadline = float(authorization["recovery_deadline_at_unix"])
            self.rate = float(authorization["hourly_price_usd"])
            self.audit_started_at_unix = (
                time.time()
                if audit_started_at_unix is None
                else float(audit_started_at_unix)
            )
            if not self.started <= self.audit_started_at_unix < self.deadline:
                raise audit.CalibrationAuditError(
                    "recovery audit did not start inside its 30-minute authority"
                )

        def check(self) -> None:
            now = time.time()
            elapsed = now - self.started
            if (
                elapsed < 0
                or now >= self.deadline
                or elapsed > RECOVERY_SECONDS
                or self.rate * elapsed / 3600 > RECOVERY_MAX_SPEND_USD
            ):
                raise audit.CalibrationAuditError(
                    "recovery audit stopped at the 30-minute/$3 boundary"
                )

    return RecoveryWatchdog


@contextlib.contextmanager
def _patched_audit_runtime(
    authorization: Mapping[str, Any], run_complete: Mapping[str, Any]
) -> Iterator[None]:
    original_loader = audit._load_j_checkpoint  # noqa: SLF001
    original_watchdog = audit._AuditBudgetWatchdog  # noqa: SLF001
    original_external = audit._audit_external_receipt_chain  # noqa: SLF001
    historical_now = float(run_complete["resource"]["run_completed_at_unix"])

    def historical_external(**kwargs: Any) -> dict[str, Any]:
        kwargs["now_unix"] = historical_now
        return original_external(**kwargs)

    audit._load_j_checkpoint = _load_j_checkpoint_recovery  # type: ignore[attr-defined]  # noqa: SLF001
    audit._AuditBudgetWatchdog = _recovery_watchdog_class(authorization)  # type: ignore[attr-defined]  # noqa: SLF001
    audit._audit_external_receipt_chain = historical_external  # type: ignore[attr-defined]  # noqa: SLF001
    try:
        yield
    finally:
        audit._load_j_checkpoint = original_loader  # type: ignore[attr-defined]  # noqa: SLF001
        audit._AuditBudgetWatchdog = original_watchdog  # type: ignore[attr-defined]  # noqa: SLF001
        audit._audit_external_receipt_chain = original_external  # type: ignore[attr-defined]  # noqa: SLF001


def _recovery_metadata(
    *,
    authorization: Mapping[str, Any],
    mount: Mapping[str, Any],
    provenance_mount: Mapping[str, Any],
    executable_isolation: Mapping[str, Any],
    provenance_pre_rehash: Mapping[str, Any],
    provenance_post_rehash: Mapping[str, Any],
    pre_rehash: Mapping[str, Any],
    post_rehash: Mapping[str, Any],
    guards: Mapping[str, int],
    module_guards: Mapping[str, int],
    marker: Mapping[str, Any],
) -> dict[str, Any]:
    if _OBSERVED_J_INVENTORY is None:
        raise AuditRecoveryError("corrected J inventory was not observed")
    core = {
        "recovery_protocol_version": RECOVERY_PROTOCOL_VERSION,
        "status": "pass_disclosed_post_run_technical_recovery",
        "correction": "required_j_layers_subset_of_hash_pinned_release_inventory",
        "provider_review_status": authorization["review"]["provider_status"],
        "provider_review_approval_claimed": False,
        "provider_review_source_and_tests_seen": False,
        "recovery_authorization_receipt_sha256": authorization["receipt_sha256"],
        "attempt_id": authorization["execution"]["attempt_id"],
        "attempt_marker_receipt_sha256": marker["receipt_sha256"],
        "command_sha256": authorization["execution"]["command_sha256"],
        "recovery_bound_paths_sha256": authorization["recovery_bound_paths_sha256"],
        "plan_manifest_sha256": authorization["plan_manifest_sha256"],
        "recovery_plan_sha256": _bound_recovery_hash(
            authorization,
            "docs/consciousness_sae_target_blind_calibration/"
            "AUDIT_RECOVERY_20260714.md",
        ),
        "recovery_source_sha256": _bound_recovery_hash(
            authorization,
            "experiments/consciousness_sae_target_blind_calibration/audit_recovery.py",
        ),
        "recovery_test_sha256": _bound_recovery_hash(
            authorization,
            "tests/consciousness_sae_target_blind_calibration/test_audit_recovery.py",
        ),
        "review_adjudication_sha256": _bound_recovery_hash(
            authorization,
            "docs/consciousness_sae_target_blind_calibration/reviews/"
            "AUDIT_RECOVERY_GPT_PRO_ADJUDICATION.md",
        ),
        "review_response_sha256": _bound_recovery_hash(
            authorization,
            "docs/consciousness_sae_target_blind_calibration/reviews/"
            "audit_recovery_gpt_pro_20260714_live/response.json",
        ),
        "review_manifest_sha256": _bound_recovery_hash(
            authorization,
            "docs/consciousness_sae_target_blind_calibration/reviews/"
            "audit_recovery_gpt_pro_20260714_live/review_manifest.json",
        ),
        "original_failed_audit_log_sha256": ORIGINAL_FAILURE_LOG_SHA256,
        "original_raw_run_receipt_sha256": ORIGINAL_RUN_RECEIPT_SHA256,
        "original_receipts": authorization["original_receipts"],
        "fresh_receipts": authorization["fresh_receipts"],
        "fresh_pod_id": authorization["fresh_pod_id"],
        "mount_receipt": dict(mount),
        "mount_receipt_sha256": mount["receipt_sha256"],
        "provenance_mount_receipt": dict(provenance_mount),
        "provenance_mount_receipt_sha256": provenance_mount["receipt_sha256"],
        "executable_isolation_receipt": dict(executable_isolation),
        "executable_isolation_receipt_sha256": executable_isolation["receipt_sha256"],
        "provenance_pre_rehash_receipt": dict(provenance_pre_rehash),
        "provenance_pre_rehash_receipt_sha256": provenance_pre_rehash["receipt_sha256"],
        "provenance_post_rehash_receipt": dict(provenance_post_rehash),
        "provenance_post_rehash_receipt_sha256": provenance_post_rehash[
            "receipt_sha256"
        ],
        "historical_provenance_unchanged": (
            provenance_pre_rehash["file_inventory_sha256"]
            == provenance_post_rehash["file_inventory_sha256"]
        ),
        "pre_rehash_receipt": dict(pre_rehash),
        "pre_rehash_receipt_sha256": pre_rehash["receipt_sha256"],
        "post_rehash_receipt": dict(post_rehash),
        "post_rehash_receipt_sha256": post_rehash["receipt_sha256"],
        "raw_unchanged": pre_rehash["file_inventory_sha256"]
        == post_rehash["file_inventory_sha256"],
        "zero_forward_guards": dict(guards),
        "forbidden_module_guards": dict(module_guards),
        "j_checkpoint_inventory": dict(_OBSERVED_J_INVENTORY),
        "scientific_metrics_thresholds_layers_and_rows_changed": False,
        "fresh_model_execution_performed": False,
        "target_prompt_render_count": 0,
        "target_feature_vector_count": 0,
        "external_or_prior_outcome_inputs": [],
    }
    return {**core, "receipt_sha256": protocol.canonical_sha256(core)}


def _enrich_outputs(
    audit_receipt: Mapping[str, Any],
    summary: Mapping[str, Any],
    *,
    authorization: Mapping[str, Any],
    recovery: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    audit_core = dict(audit_receipt)
    audit_core.pop("receipt_sha256", None)
    original_campaign = {
        "campaign_started_at_unix": audit_core["campaign_started_at_unix"],
        "campaign_deadline_at_unix": audit_core["campaign_deadline_at_unix"],
        "hourly_price_usd": audit_core["hourly_price_usd"],
    }
    audit_core["original_execution_campaign"] = original_campaign
    audit_core["campaign_started_at_unix"] = authorization["recovery_started_at_unix"]
    audit_core["campaign_deadline_at_unix"] = authorization["recovery_deadline_at_unix"]
    audit_core["hourly_price_usd"] = authorization["hourly_price_usd"]
    audit_core["recovery_audit"] = dict(recovery)
    enriched_audit = {
        **audit_core,
        "receipt_sha256": protocol.canonical_sha256(audit_core),
    }
    summary_core = dict(summary)
    summary_core.pop("receipt_sha256", None)
    summary_core["audit_receipt_sha256"] = enriched_audit["receipt_sha256"]
    summary_core["recovery_audit"] = dict(recovery)
    enriched_summary = {
        **summary_core,
        "receipt_sha256": protocol.canonical_sha256(summary_core),
    }
    return enriched_audit, enriched_summary


def _bound_recovery_hash(authorization: Mapping[str, Any], relative_path: str) -> str:
    rows = authorization.get("recovery_bound_files")
    if not isinstance(rows, list):
        raise AuditRecoveryError("recovery bound-file closure is missing")
    matches = [row for row in rows if row.get("path") == relative_path]
    if len(matches) != 1 or HEX64.fullmatch(str(matches[0].get("sha256", ""))) is None:
        raise AuditRecoveryError("recovery bound-file hash is missing")
    return str(matches[0]["sha256"])


def _claim_attempt(
    args: argparse.Namespace, authorization: Mapping[str, Any]
) -> dict[str, Any]:
    binding = authorization["execution"]
    attempt_root = Path(str(binding["attempt_root"]))
    authorize._require_no_symlink_components(  # noqa: SLF001
        attempt_root, "recovery attempt root"
    )
    if (
        not attempt_root.is_dir()
        or attempt_root.is_symlink()
        or args.attempt_marker.expanduser().absolute().parent != attempt_root
        or args.failure_out.expanduser().absolute().parent != attempt_root
        or os.path.lexists(args.attempt_marker)
        or os.path.lexists(args.failure_out)
        or os.path.lexists(args.audit_out.parent)
    ):
        raise AuditRecoveryError("recovery attempt namespace is not fresh")
    started = time.time()
    if not (
        float(authorization["recovery_started_at_unix"])
        <= started
        < float(authorization["recovery_deadline_at_unix"])
    ):
        raise AuditRecoveryError("recovery attempt began outside authority")
    core = {
        "schema_version": 1,
        "status": "claimed_exactly_once",
        "study_id": protocol.STUDY_ID,
        "run_id": RUN_ID,
        "attempt_id": binding["attempt_id"],
        "claimed_at_utc": _utc_text(datetime.fromtimestamp(started, timezone.utc)),
        "claimed_at_unix": started,
        "recovery_authorization_receipt_sha256": authorization["receipt_sha256"],
        "command_sha256": binding["command_sha256"],
        "recovery_source_sha256": _bound_recovery_hash(
            authorization,
            "experiments/consciousness_sae_target_blind_calibration/audit_recovery.py",
        ),
    }
    marker = {**core, "receipt_sha256": protocol.canonical_sha256(core)}
    _write_json_exclusive(args.attempt_marker, marker)
    return marker


def _write_failure_receipt(
    args: argparse.Namespace,
    authorization: Mapping[str, Any],
    marker: Mapping[str, Any],
    error: BaseException,
) -> None:
    message = str(error)
    if len(message) > 1000:
        message = message[:1000]
    core = {
        "schema_version": 1,
        "status": "failed_no_compact_success_publication",
        "study_id": protocol.STUDY_ID,
        "run_id": RUN_ID,
        "attempt_id": authorization["execution"]["attempt_id"],
        "failed_at_utc": _utc_text(datetime.now(timezone.utc)),
        "error_type": type(error).__name__,
        "error_message": message,
        "recovery_authorization_receipt_sha256": authorization["receipt_sha256"],
        "attempt_marker_receipt_sha256": marker["receipt_sha256"],
        "command_sha256": authorization["execution"]["command_sha256"],
        "recovery_source_sha256": marker["recovery_source_sha256"],
        "compact_success_directory_exists": args.audit_out.parent.exists(),
    }
    receipt = {**core, "receipt_sha256": protocol.canonical_sha256(core)}
    _write_json_exclusive(args.failure_out, receipt)


def execute_recovery(args: argparse.Namespace) -> Path:
    global _OBSERVED_J_INVENTORY  # noqa: PLW0603
    _OBSERVED_J_INVENTORY = None
    authorization = validate_recovery_authorization(
        _json(args.recovery_authorization), args
    )
    marker = _claim_attempt(args, authorization)
    try:
        raw_root = args.raw_root.resolve(strict=True)
        mount = _verify_read_only_mount(raw_root)
        provenance_root = args.provenance_root.resolve(strict=True)
        provenance_mount = _verify_read_only_bind_mount(
            provenance_root, role="nonimportable_historical_source_provenance"
        )
        executable_isolation = _validate_executable_isolation(
            provenance_root, authorization
        )
        provenance_pre_rehash = _validate_provenance_tree(
            provenance_root, authorization["historical_provenance_files"]
        )
        pre_rehash = _rehash_raw_tree(raw_root, args.raw_ledger)
        run_complete = _json(args.run_complete)
        guards: dict[str, int]
        module_guards: dict[str, int]
        with (
            _historical_provenance_context(provenance_root),
            _forbidden_module_guard() as module_guards,
            _patched_audit_runtime(authorization, run_complete),
            _zero_forward_guards() as guards,
        ):
            audit_receipt, summary = audit.audit(
                raw_root,
                args.plan_dir,
                model_snapshot=args.model_snapshot,
                j_lens_path=args.j_lens_path,
                ownership_receipt=args.original_ownership,
                guest_receipt=args.original_guest,
                cache_receipt=args.original_cache,
                authorization_receipt=args.original_authorization,
                artifact_device=args.artifact_device,
            )
            if guards != {
                "torch_module_calls": 0,
                "transformers_model_load_calls": 0,
            }:
                raise AuditRecoveryError("a zero-forward recovery guard fired")
            if module_guards != {"forbidden_module_import_attempts": 0}:
                raise AuditRecoveryError("a forbidden module recovery guard fired")
            post_rehash = _rehash_raw_tree(raw_root, args.raw_ledger)
            if (
                pre_rehash["file_inventory_sha256"]
                != post_rehash["file_inventory_sha256"]
            ):
                raise AuditRecoveryError("raw tree changed during recovery")
            provenance_post_rehash = _validate_provenance_tree(
                provenance_root, authorization["historical_provenance_files"]
            )
            if (
                provenance_pre_rehash["file_inventory_sha256"]
                != provenance_post_rehash["file_inventory_sha256"]
            ):
                raise AuditRecoveryError("historical provenance changed")
            recovery = _recovery_metadata(
                authorization=authorization,
                mount=mount,
                provenance_mount=provenance_mount,
                executable_isolation=executable_isolation,
                provenance_pre_rehash=provenance_pre_rehash,
                provenance_post_rehash=provenance_post_rehash,
                pre_rehash=pre_rehash,
                post_rehash=post_rehash,
                guards=guards,
                module_guards=module_guards,
                marker=marker,
            )
            enriched_audit, enriched_summary = _enrich_outputs(
                audit_receipt,
                summary,
                authorization=authorization,
                recovery=recovery,
            )
            return audit._publish_pair_atomic(  # noqa: SLF001
                args.audit_out,
                args.summary_out,
                enriched_audit,
                enriched_summary,
            )
    except BaseException as exc:
        try:
            _write_failure_receipt(args, authorization, marker, exc)
        except BaseException as receipt_exc:
            raise AuditRecoveryError(
                f"recovery failed and failure receipt could not publish: {receipt_exc}"
            ) from exc
        raise


def _add_evidence_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--plan-dir", type=Path, required=True)
    parser.add_argument("--raw-root", type=Path, required=True)
    parser.add_argument("--run-complete", type=Path, required=True)
    parser.add_argument("--raw-ledger", type=Path, required=True)
    parser.add_argument("--raw-inventory", type=Path, required=True)
    parser.add_argument("--failure-log", type=Path, required=True)
    parser.add_argument("--original-ownership", type=Path, required=True)
    parser.add_argument("--original-guest", type=Path, required=True)
    parser.add_argument("--original-cache", type=Path, required=True)
    parser.add_argument("--original-authorization", type=Path, required=True)
    parser.add_argument("--termination-audit", type=Path, required=True)
    parser.add_argument("--postdelete-inventory", type=Path, required=True)
    parser.add_argument("--frozen-termination", type=Path, required=True)
    parser.add_argument("--fresh-ownership", type=Path, required=True)
    parser.add_argument("--fresh-guest", type=Path, required=True)
    parser.add_argument("--fresh-cache", type=Path, required=True)


def _add_execution_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--attempt-id", required=True)
    parser.add_argument("--provenance-root", type=Path, required=True)
    parser.add_argument("--model-snapshot", type=Path, required=True)
    parser.add_argument("--j-lens-path", type=Path, required=True)
    parser.add_argument("--artifact-device", default="cuda:0")
    parser.add_argument("--audit-out", type=Path, required=True)
    parser.add_argument("--summary-out", type=Path, required=True)
    parser.add_argument("--attempt-marker", type=Path, required=True)
    parser.add_argument("--failure-out", type=Path, required=True)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    issue = commands.add_parser("issue", help="Issue the fresh audit-only authority")
    _add_evidence_args(issue)
    _add_execution_args(issue)
    issue.add_argument("--hourly-price-usd", type=float, required=True)
    issue.add_argument("--output", type=Path, required=True)

    execute = commands.add_parser("execute", help="Execute the recovered audit once")
    _add_evidence_args(execute)
    _add_execution_args(execute)
    execute.add_argument("--recovery-authorization", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "issue":
        receipt = issue_authorization(args)
        _write_json_exclusive(args.output, receipt)
        print(args.output)
        return 0
    if args.command == "execute":
        print(execute_recovery(args))
        return 0
    raise AuditRecoveryError("unknown recovery command")


if __name__ == "__main__":
    raise SystemExit(main())

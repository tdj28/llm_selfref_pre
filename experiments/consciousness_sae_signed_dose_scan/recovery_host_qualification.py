#!/usr/bin/env python3
"""One-shot, zero-forward target-host qualification for audit recovery.

The probe authenticates the fresh provider/guest/cache chain, the exact pinned
J checkpoint and its 0..78 inventory, the recovery 45..78 subset behavior, and
the frozen auditor's real B200/CUBLAS startup path.  It has no raw-run argument,
installs a fail-closed raw-path audit hook, blocks every ``torch.nn.Module`` call
and Transformers model load, and performs only one tiny raw BF16 CUDA matmul.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import stat
import sys
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping

from experiments.consciousness_sae_realization_validation import runpod_preflight
from experiments.consciousness_sae_signed_dose_scan import audit as frozen_audit
from experiments.consciousness_sae_signed_dose_scan import audit_recovery, protocol
from experiments.consciousness_sae_signed_dose_scan import (
    verify_recovery_equivalence,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
QUALIFICATION_PROTOCOL_VERSION = (
    "consciousness_sae_signed_dose_scan_v1.audit_recovery_host_qualification_v1"
)
ATTEMPT_MARKER_NAME = "ATTEMPT_STARTED.json"
SUCCESS_NAME = "TARGET_HOST_QUALIFICATION.json"
FAILURE_NAME = "QUALIFICATION_FAILED.json"
REQUIRED_LAYERS = tuple(range(45, 79))
PINNED_AVAILABLE_LAYERS = tuple(range(79))
MAX_OWNERSHIP_AGE_SECONDS = 30 * 60
MAX_GUEST_AGE_SECONDS = 15 * 60
MIN_LIFECYCLE_REMAINING_SECONDS = 15 * 60
QUALIFICATION_MAX_SECONDS = 30 * 60
QUALIFICATION_MAX_SPEND_USD = 3.0
FORBIDDEN_RAW_ROOT = Path(
    "/workspace/consciousness_sae_signed_dose_scan/"
    "consciousness_sae_signed_dose_scan_v1/raw"
)
EXPECTED_ZERO_FORWARD_COUNTS = {
    "torch_module_calls": 0,
    "transformers_model_load_calls": 0,
    "direct_forward_attribute_access": 0,
    "model_construction_calls": 0,
    "model_state_load_calls": 0,
}


class RecoveryHostQualificationError(RuntimeError):
    """A one-shot qualification invariant failed."""


class QualificationWatchdog:
    """Independent cap inside the provider's broader lifecycle envelope."""

    def __init__(
        self,
        *,
        started_at_unix: float,
        hourly_price_usd: float,
        clock: Callable[[], float],
    ) -> None:
        self.started = float(started_at_unix)
        self.deadline = self.started + QUALIFICATION_MAX_SECONDS
        self.rate = float(hourly_price_usd)
        self.clock = clock
        if (
            not all(math.isfinite(value) for value in (self.started, self.rate))
            or self.rate <= 0
            or self.rate * QUALIFICATION_MAX_SECONDS / 3600
            > QUALIFICATION_MAX_SPEND_USD
        ):
            raise RecoveryHostQualificationError(
                "qualification time/cost authority differs"
            )

    def check(self) -> float:
        now = float(self.clock())
        if (
            not math.isfinite(now)
            or not self.started <= now < self.deadline
            or self.rate * (now - self.started) / 3600
            > QUALIFICATION_MAX_SPEND_USD
        ):
            raise RecoveryHostQualificationError("qualification watchdog expired")
        return now


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(8 * 1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _write_exclusive(path: Path, value: Mapping[str, Any]) -> None:
    payload = canonical_json_bytes(value) + b"\n"
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())


def _load_canonical(path: Path, label: str) -> tuple[dict[str, Any], str]:
    candidate = path.expanduser().absolute()
    try:
        details = candidate.lstat()
        raw = candidate.read_bytes()
        value = json.loads(raw)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise RecoveryHostQualificationError(f"{label} is unreadable") from exc
    if (
        not stat.S_ISREG(details.st_mode)
        or details.st_nlink != 1
        or not isinstance(value, dict)
        or raw != canonical_json_bytes(value) + b"\n"
    ):
        raise RecoveryHostQualificationError(
            f"{label} is not canonical single-link JSON"
        )
    return value, hashlib.sha256(raw).hexdigest()


def _utc_timestamp(value: Any, label: str) -> float:
    if not isinstance(value, str):
        raise RecoveryHostQualificationError(f"{label} is malformed")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise RecoveryHostQualificationError(f"{label} is malformed") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise RecoveryHostQualificationError(f"{label} is timezone-naive")
    return parsed.astimezone(timezone.utc).timestamp()


def _strict_path(value: Any, label: str, *, must_exist: bool) -> Path:
    """Resolve a path while rejecting every existing symlink component."""

    if isinstance(value, int):
        raise RecoveryHostQualificationError(f"{label} is a file descriptor")
    try:
        lexical = Path(os.path.abspath(os.path.expanduser(os.fsdecode(value))))
    except (AttributeError, TypeError, ValueError) as exc:
        raise RecoveryHostQualificationError(f"{label} is malformed") from exc
    current = Path(lexical.anchor)
    try:
        for component in lexical.parts[1:]:
            current /= component
            try:
                details = current.lstat()
            except FileNotFoundError:
                if must_exist:
                    raise RecoveryHostQualificationError(f"{label} is missing")
                continue
            if stat.S_ISLNK(details.st_mode):
                raise RecoveryHostQualificationError(
                    f"{label} contains a symlink component"
                )
        resolved = lexical.resolve(strict=must_exist)
    except RecoveryHostQualificationError:
        raise
    except OSError as exc:
        raise RecoveryHostQualificationError(f"{label} is missing") from exc
    if resolved != lexical:
        raise RecoveryHostQualificationError(f"{label} canonical path differs")
    return resolved


def _strict_existing_path(value: Any, label: str) -> Path:
    return _strict_path(value, label, must_exist=True)


def _inside(path: Path, root: Path) -> bool:
    return path == root or root in path.parents


class RawPathAuditGuard:
    """A process-lifetime audit hook rejecting the signed-dose raw tree."""

    def __init__(self, forbidden_raw_root: Path) -> None:
        self.forbidden_raw_root = _strict_existing_path(
            forbidden_raw_root, "forbidden raw root"
        )
        if not self.forbidden_raw_root.is_dir():
            raise RecoveryHostQualificationError("forbidden raw root is not a directory")
        self.open_event_count = 0
        self.forbidden_attempt_count = 0

    def __call__(self, event: str, args: tuple[Any, ...]) -> None:
        if event != "open" or not args:
            return
        self.open_event_count += 1
        if isinstance(args[0], int):
            # The pathname was already checked when this descriptor was opened.
            return
        try:
            candidate = _strict_path(args[0], "opened path", must_exist=False)
        except RecoveryHostQualificationError:
            # Fail closed on any symlink/noncanonical open.  This prevents a
            # parent-symlink alias from escaping the raw-root comparison.
            self.forbidden_attempt_count += 1
            raise
        if _inside(candidate, self.forbidden_raw_root):
            self.forbidden_attempt_count += 1
            raise RecoveryHostQualificationError(
                "signed-dose raw access is forbidden during qualification"
            )


def select_required_maps(maps: Mapping[int, Any]) -> dict[int, Any]:
    """Return unchanged required map objects or reject a missing layer."""

    missing = sorted(set(REQUIRED_LAYERS) - set(maps))
    if missing:
        raise RecoveryHostQualificationError(
            f"J checkpoint is missing required layers: {missing}"
        )
    return {layer: maps[layer] for layer in REQUIRED_LAYERS}


@contextmanager
def qualification_zero_forward_guard() -> Any:
    """Block module calls, model loads, and direct ``model.forward`` access."""

    import torch

    with audit_recovery.zero_forward_guard() as inherited:
        original_getattribute = torch.nn.Module.__getattribute__
        direct = {"direct_forward_attribute_access": 0}

        def guarded_getattribute(module: Any, name: str) -> Any:
            if name == "forward":
                direct["direct_forward_attribute_access"] += 1
                raise RecoveryHostQualificationError(
                    "direct torch module forward access is forbidden"
                )
            return original_getattribute(module, name)

        torch.nn.Module.__getattribute__ = guarded_getattribute
        try:
            counts = {**inherited, **direct}
            yield counts
        finally:
            counts.update(inherited)
            counts.update(direct)
            torch.nn.Module.__getattribute__ = original_getattribute


def _validate_fresh_receipt_chain(
    ownership_path: Path,
    guest_path: Path,
    cache_path: Path,
    *,
    now_unix: float,
) -> dict[str, Any]:
    ownership_raw, ownership_file_hash = _load_canonical(
        ownership_path, "ownership receipt"
    )
    guest_raw, guest_file_hash = _load_canonical(guest_path, "guest receipt")
    cache_raw, cache_file_hash = _load_canonical(cache_path, "cache receipt")
    try:
        ownership = runpod_preflight.validate_ownership_receipt(ownership_raw)
        guest = runpod_preflight.validate_guest_receipt(
            guest_raw, ownership_receipt=ownership
        )
        cache = runpod_preflight.validate_cache_receipt(
            cache_raw,
            guest_receipt=guest,
            ownership_receipt=ownership,
        )
    except runpod_preflight.PreflightError as exc:
        raise RecoveryHostQualificationError(
            "fresh ownership/guest/cache receipt chain differs"
        ) from exc
    created = _utc_timestamp(ownership["created_at"], "ownership.created_at")
    deadline = _utc_timestamp(
        ownership["terminate_after"], "ownership.terminate_after"
    )
    attested = _utc_timestamp(guest["attested_at_utc"], "guest.attested_at_utc")
    if (
        not math.isfinite(now_unix)
        or not created <= attested <= now_unix < deadline
        or now_unix - created > MAX_OWNERSHIP_AGE_SECONDS
        or now_unix - attested > MAX_GUEST_AGE_SECONDS
        or deadline - now_unix < MIN_LIFECYCLE_REMAINING_SECONDS
    ):
        raise RecoveryHostQualificationError("fresh pod lifecycle window differs")
    if (
        ownership["network_volume_id"] != protocol.NETWORK_VOLUME_ID
        or ownership["data_center_id"] != protocol.DATA_CENTER_ID
        or ownership["gpu_type"] != protocol.GPU_TYPE
        or ownership["gpu_count"] != 1
        or guest["model_forward_count"] != 0
        or guest["target_prompt_render_count"] != 0
        or guest["prior_outcome_inputs"] != []
        or cache["model_forward_count"] != 0
        or cache["target_prompt_render_count"] != 0
        or cache["prior_outcome_inputs"] != []
    ):
        raise RecoveryHostQualificationError("fresh zero-forward pod binding differs")
    return {
        "status": "pass_fresh_owned_guest_cache_chain",
        "pod_id": ownership["pod_id"],
        "volume_id": ownership["network_volume_id"],
        "data_center_id": ownership["data_center_id"],
        "gpu_type": ownership["gpu_type"],
        "gpu_count": ownership["gpu_count"],
        "precreate_unrelated_pod_count": ownership[
            "precreate_unrelated_pod_count"
        ],
        "precreate_unrelated_inventory_sha256": ownership[
            "precreate_unrelated_inventory_sha256"
        ],
        "created_at": ownership["created_at"],
        "terminate_after": ownership["terminate_after"],
        "guest_attested_at_utc": guest["attested_at_utc"],
        "ownership_path": ownership_path.expanduser().absolute().as_posix(),
        "guest_path": guest_path.expanduser().absolute().as_posix(),
        "cache_path": cache_path.expanduser().absolute().as_posix(),
        "ownership_file_sha256": ownership_file_hash,
        "guest_file_sha256": guest_file_hash,
        "cache_file_sha256": cache_file_hash,
        "ownership_receipt_sha256": ownership["receipt_sha256"],
        "guest_receipt_sha256": guest["receipt_sha256"],
        "cache_receipt_sha256": cache["receipt_sha256"],
        "cache_root": cache["cache_root"],
        "cache_components": cache["components"],
        "model_forward_count": 0,
        "target_prompt_render_count": 0,
        "prior_outcome_inputs": [],
    }


class _NoopWatchdog:
    def __init__(self) -> None:
        self.check_count = 0

    def check(self) -> None:
        self.check_count += 1


def inspect_pinned_checkpoint(j_lens_path: Path) -> dict[str, Any]:
    """Authenticate release inventory and required-map identity without CUDA."""

    import torch

    watchdog = _NoopWatchdog()
    path, filtered, audit_record, inventory = (
        audit_recovery.load_j_checkpoint_superset(j_lens_path, watchdog)
    )
    available = tuple(inventory.get("available_layers", ()))
    if (
        available != PINNED_AVAILABLE_LAYERS
        or tuple(inventory.get("required_layers", ())) != REQUIRED_LAYERS
        or tuple(filtered) != REQUIRED_LAYERS
        or tuple(inventory.get("unused_extra_layers", ())) != tuple(range(45))
        or audit_record
        != {
            "sha256": protocol.J_LENS_SPEC["sha256"],
            "map_count": len(REQUIRED_LAYERS),
            "revision": protocol.J_LENS_SPEC["revision"],
        }
    ):
        raise RecoveryHostQualificationError("pinned J inventory differs")
    for layer, tensor in filtered.items():
        if (
            tuple(tensor.shape) != (protocol.WIDTH, protocol.WIDTH)
            or tensor.dtype != torch.bfloat16
        ):
            raise RecoveryHostQualificationError(
                f"required J[{layer}] shape/dtype differs"
            )
    selected = select_required_maps(filtered)
    if any(selected[layer] is not filtered[layer] for layer in REQUIRED_LAYERS):
        raise RecoveryHostQualificationError("J map object identity changed")
    missing_fixture = dict(filtered)
    del missing_fixture[REQUIRED_LAYERS[0]]
    try:
        select_required_maps(missing_fixture)
    except RecoveryHostQualificationError:
        missing_negative = "pass_rejected_missing_required_layer_45"
    else:
        raise RecoveryHostQualificationError("missing-map negative did not reject")
    core = {
        "status": "pass_exact_pinned_superset_and_required_filter",
        "checkpoint_path": path.as_posix(),
        "checkpoint_sha256": protocol.J_LENS_SPEC["sha256"],
        "checkpoint_revision": protocol.J_LENS_SPEC["revision"],
        "checkpoint_n_prompts": inventory["checkpoint_n_prompts"],
        "checkpoint_d_model": inventory["checkpoint_d_model"],
        "available_layers": list(available),
        "required_layers": list(REQUIRED_LAYERS),
        "unused_extra_layers": list(range(45)),
        "filtered_layers": list(filtered),
        "available_map_count": len(available),
        "required_map_count": len(filtered),
        "required_map_shape": [protocol.WIDTH, protocol.WIDTH],
        "required_map_dtype": "torch.bfloat16",
        "selected_map_object_contract": "same_checkpoint_objects_no_numeric_transform",
        "missing_required_layer_negative": missing_negative,
        "loader_watchdog_check_count": watchdog.check_count,
        "frozen_audit_record": audit_record,
    }
    return {**core, "receipt_sha256": canonical_sha256(core)}


def _exercise_frozen_cuda_startup() -> dict[str, Any]:
    """Reach the exact frozen device setup and a real CUBLAS BF16 operation."""

    import torch

    device = frozen_audit._configure_artifact_device("cuda:0")  # noqa: SLF001
    properties = torch.cuda.get_device_properties(device)
    left = torch.arange(256, device=device, dtype=torch.bfloat16).reshape(16, 16)
    right = torch.eye(16, device=device, dtype=torch.bfloat16)
    product = torch.matmul(left, right)
    torch.cuda.synchronize(device)
    finite = bool(torch.isfinite(product).all().item())
    if not finite or not bool(torch.equal(product, left)):
        raise RecoveryHostQualificationError("BF16 CUBLAS startup probe differs")
    return {
        "status": "pass_frozen_startup_and_real_bf16_cublas",
        "configured_via": (
            "experiments.consciousness_sae_signed_dose_scan.audit."
            "_configure_artifact_device"
        ),
        "device": str(device),
        "device_count": torch.cuda.device_count(),
        "device_name": str(properties.name),
        "device_total_memory_bytes": int(properties.total_memory),
        "cublas_workspace_config": os.environ.get("CUBLAS_WORKSPACE_CONFIG"),
        "deterministic_algorithms_enabled": (
            torch.are_deterministic_algorithms_enabled()
        ),
        "matmul_allow_tf32": torch.backends.cuda.matmul.allow_tf32,
        "cudnn_allow_tf32": torch.backends.cudnn.allow_tf32,
        "flash_sdp_enabled": torch.backends.cuda.flash_sdp_enabled(),
        "mem_efficient_sdp_enabled": (
            torch.backends.cuda.mem_efficient_sdp_enabled()
        ),
        "math_sdp_enabled": torch.backends.cuda.math_sdp_enabled(),
        "probe_operation": "torch.matmul",
        "probe_shape": [16, 16],
        "probe_dtype": "torch.bfloat16",
        "probe_finite": finite,
        "probe_exact_identity_product": True,
        "torch_module_calls": 0,
        "transformers_model_load_calls": 0,
        "direct_forward_attribute_access": 0,
        "model_forward_count": 0,
        "target_prompt_render_count": 0,
    }


def _checkpoint_matches_cache(
    checkpoint_path: Path, receipt_chain: Mapping[str, Any]
) -> None:
    rows = receipt_chain["cache_components"]
    j_rows = [row for row in rows if row.get("component") == "j_lens"]
    if len(j_rows) != 1:
        raise RecoveryHostQualificationError("cache J component differs")
    row = j_rows[0]
    expected = _strict_existing_path(
        Path(str(receipt_chain["cache_root"])) / row["relative_path"],
        "cache-bound J checkpoint",
    )
    if (
        _strict_existing_path(checkpoint_path, "J checkpoint") != expected
        or row.get("sha256") != protocol.J_LENS_SPEC["sha256"]
        or row.get("revision") != protocol.J_LENS_SPEC["revision"]
        or row.get("verified") is not True
    ):
        raise RecoveryHostQualificationError("checkpoint/cache binding differs")


def _input_record(path: Path, forbidden_raw_root: Path) -> dict[str, Any]:
    candidate = _strict_existing_path(path, "qualification input")
    if _inside(candidate, forbidden_raw_root):
        raise RecoveryHostQualificationError("qualification input points into raw")
    details = candidate.lstat()
    if not stat.S_ISREG(details.st_mode) or details.st_nlink != 1:
        raise RecoveryHostQualificationError(
            "qualification input is not a regular single-link file"
        )
    return {
        "path": candidate.as_posix(),
        "bytes": details.st_size,
        "sha256": sha256_file(candidate),
    }


def _declared_input_path(role: str, path: Path) -> dict[str, str]:
    """Record launch intent without opening or resolving the declared input."""

    lexical = Path(os.path.abspath(os.path.expanduser(os.fspath(path))))
    return {"role": role, "path": lexical.as_posix()}


def qualify_host(
    *,
    packet_path: Path,
    plan_audit_path: Path,
    ownership_path: Path,
    guest_path: Path,
    cache_path: Path,
    j_lens_path: Path,
    output_dir: Path,
    repo_root: Path = REPO_ROOT,
    now_unix: float | None = None,
    hourly_price_usd: float,
    enforce_git: bool = True,
    install_raw_audit_hook: bool = True,
    equivalence_verifier: Callable[..., Mapping[str, Any]] | None = None,
    chain_validator: Callable[..., Mapping[str, Any]] | None = None,
    checkpoint_inspector: Callable[[Path], Mapping[str, Any]] | None = None,
    cuda_probe: Callable[[], Mapping[str, Any]] | None = None,
    forward_guard_factory: Callable[[], Any] | None = None,
    forbidden_raw_root: Path = FORBIDDEN_RAW_ROOT,
) -> dict[str, Any]:
    """Execute the sole qualification attempt and publish a self-hashed receipt."""

    injected = (
        now_unix is not None
        or not install_raw_audit_hook
        or equivalence_verifier is not None
        or chain_validator is not None
        or checkpoint_inspector is not None
        or cuda_probe is not None
        or forward_guard_factory is not None
        or Path(forbidden_raw_root) != FORBIDDEN_RAW_ROOT
    )
    if enforce_git and injected:
        raise RecoveryHostQualificationError(
            "test-only qualification override is forbidden in production"
        )
    started = time.time() if now_unix is None else float(now_unix)
    clock = time.time if now_unix is None else (lambda: started)
    watchdog = QualificationWatchdog(
        started_at_unix=started,
        hourly_price_usd=hourly_price_usd,
        clock=clock,
    )
    canonical_raw_root = _strict_existing_path(
        forbidden_raw_root, "forbidden raw root"
    )
    target_lexical = Path(os.path.abspath(output_dir.expanduser()))
    target_parent = _strict_existing_path(
        target_lexical.parent, "qualification output parent"
    )
    target = target_parent / target_lexical.name
    if target.exists() or target.is_symlink():
        raise FileExistsError(f"qualification attempt directory exists: {target}")
    if _inside(target, canonical_raw_root):
        raise RecoveryHostQualificationError("qualification output points into raw")
    target.mkdir(mode=0o700)
    target = _strict_existing_path(target, "qualification output directory")
    raw_guard = RawPathAuditGuard(canonical_raw_root)
    if install_raw_audit_hook:
        sys.addaudithook(raw_guard)
    input_paths = {
        "equivalence_packet": packet_path,
        "independent_plan_audit": plan_audit_path,
        "fresh_ownership": ownership_path,
        "fresh_guest": guest_path,
        "fresh_cache": cache_path,
        "pinned_j_checkpoint": j_lens_path,
    }
    try:
        declared_inputs = [
            _declared_input_path(role, path)
            for role, path in sorted(input_paths.items())
        ]
        marker_core = {
            "schema_version": 1,
            "status": "attempt_started_irrevocably",
            "study_id": protocol.STUDY_ID,
            "qualification_protocol_version": QUALIFICATION_PROTOCOL_VERSION,
            "attempt_number": 1,
            "retry_authorized": False,
            "started_at_unix": started,
            "qualification_deadline_at_unix": watchdog.deadline,
            "hourly_price_usd": watchdog.rate,
            "max_spend_usd": QUALIFICATION_MAX_SPEND_USD,
            "declared_input_paths": declared_inputs,
            "declared_input_paths_sha256": canonical_sha256(declared_inputs),
            "authorized_raw_input_paths": [],
            "model_forward_count": 0,
            "target_prompt_render_count": 0,
        }
        marker = {
            **marker_core,
            "receipt_sha256": canonical_sha256(marker_core),
        }
        _write_exclusive(target / ATTEMPT_MARKER_NAME, marker)

        verifier = equivalence_verifier or verify_recovery_equivalence.verify_packet
        validate_chain = chain_validator or _validate_fresh_receipt_chain
        inspect_checkpoint = checkpoint_inspector or inspect_pinned_checkpoint
        probe_cuda = cuda_probe or _exercise_frozen_cuda_startup
        guard_factory = forward_guard_factory or qualification_zero_forward_guard
        with guard_factory() as forward_counts:
            watchdog.check()
            inputs = [
                {"role": role, **_input_record(path, canonical_raw_root)}
                for role, path in sorted(input_paths.items())
            ]
            watchdog.check()
            verified = dict(
                verifier(
                    packet_path,
                    plan_audit_path=plan_audit_path,
                    repo_root=repo_root,
                    enforce_git=enforce_git,
                )
            )
            watchdog.check()
            chain = dict(
                validate_chain(
                    ownership_path,
                    guest_path,
                    cache_path,
                    now_unix=started,
                )
            )
            watchdog.check()
            _checkpoint_matches_cache(j_lens_path, chain)
            checkpoint = dict(inspect_checkpoint(j_lens_path))
            watchdog.check()
            cuda = dict(probe_cuda())
            watchdog.check()
        if dict(forward_counts) != EXPECTED_ZERO_FORWARD_COUNTS:
            raise RecoveryHostQualificationError("zero-forward guard observed a call")
        completed = watchdog.check()
        watchdog_record = {
            "status": "pass_independent_qualification_time_cost_cap",
            "started_at_unix": started,
            "qualification_deadline_at_unix": watchdog.deadline,
            "maximum_seconds": QUALIFICATION_MAX_SECONDS,
            "hourly_price_usd": watchdog.rate,
            "max_spend_usd": QUALIFICATION_MAX_SPEND_USD,
            "maximum_theoretical_spend_usd": (
                watchdog.rate * QUALIFICATION_MAX_SECONDS / 3600
            ),
            "completed_at_unix": completed,
        }
        core = {
            "schema_version": 1,
            "status": "pass_one_shot_zero_forward_target_host_qualification",
            "study_id": protocol.STUDY_ID,
            "protocol_version": protocol.PROTOCOL_VERSION,
            "qualification_protocol_version": QUALIFICATION_PROTOCOL_VERSION,
            "attempt_number": 1,
            "retry_authorized": False,
            "started_at_unix": started,
            "completed_at_unix": completed,
            "qualification_watchdog": watchdog_record,
            "attempt_marker_receipt_sha256": marker["receipt_sha256"],
            "inputs": inputs,
            "input_inventory_sha256": canonical_sha256(inputs),
            "equivalence_verification": verified,
            "code_freeze_commit": verified["code_freeze_commit"],
            "recovery_closure_inventory_sha256": verified[
                "recovery_closure_inventory_sha256"
            ],
            "fresh_pod": chain,
            "j_checkpoint": checkpoint,
            "cuda_startup": cuda,
            "zero_forward_guard": dict(forward_counts),
            "raw_access_guard": {
                "status": "pass_no_forbidden_raw_open",
                "forbidden_raw_root": canonical_raw_root.as_posix(),
                "forbidden_attempt_count": raw_guard.forbidden_attempt_count,
            },
            "raw_input_paths": [],
            "outcome_input_paths": [],
            "analysis_data_inputs": [],
            "model_forward_count": 0,
            "target_prompt_render_count": 0,
            "target_feature_vector_count": 0,
        }
        receipt = {**core, "receipt_sha256": canonical_sha256(core)}
        _write_exclusive(target / SUCCESS_NAME, receipt)
        return receipt
    except BaseException as exc:
        failure_core = {
            "schema_version": 1,
            "status": "qualification_failed_attempt_consumed",
            "study_id": protocol.STUDY_ID,
            "qualification_protocol_version": QUALIFICATION_PROTOCOL_VERSION,
            "attempt_number": 1,
            "retry_authorized": False,
            "started_at_unix": started,
            "failed_at_unix": time.time() if now_unix is None else started,
            "qualification_deadline_at_unix": watchdog.deadline,
            "hourly_price_usd": watchdog.rate,
            "max_spend_usd": QUALIFICATION_MAX_SPEND_USD,
            "error_type": type(exc).__name__,
            "error_message": str(exc),
            "raw_forbidden_attempt_count": raw_guard.forbidden_attempt_count,
            "model_forward_count": 0,
            "target_prompt_render_count": 0,
        }
        failure = {
            **failure_core,
            "receipt_sha256": canonical_sha256(failure_core),
        }
        try:
            _write_exclusive(target / FAILURE_NAME, failure)
        except FileExistsError:
            pass
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--packet", type=Path, required=True)
    parser.add_argument("--plan-audit", type=Path, required=True)
    parser.add_argument("--ownership", type=Path, required=True)
    parser.add_argument("--guest", type=Path, required=True)
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--j-checkpoint", type=Path, required=True)
    parser.add_argument("--hourly-price-usd", type=float, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    receipt = qualify_host(
        packet_path=args.packet,
        plan_audit_path=args.plan_audit,
        ownership_path=args.ownership,
        guest_path=args.guest,
        cache_path=args.cache,
        j_lens_path=args.j_checkpoint,
        hourly_price_usd=args.hourly_price_usd,
        output_dir=args.output_dir,
    )
    print((args.output_dir / SUCCESS_NAME).expanduser().absolute(), flush=True)
    return 0 if receipt["status"].startswith("pass_") else 1


if __name__ == "__main__":
    raise SystemExit(main())

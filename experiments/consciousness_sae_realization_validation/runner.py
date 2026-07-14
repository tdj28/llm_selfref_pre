#!/usr/bin/env python3
"""Execute the v1 realization validation on one cached B200/network volume.

Stage A and Stage B are separate immutable raw transactions.  Stage B requires
a passing independent structural audit and Stage-A collection safety bound to
the same plan.  The J arithmetic/orientation fixture is part of collection
safety because Stage B emits J-derived rows.  Incremental real-J transport or
dose-linearity failure does not block neutral Stage-B raw collection; it
invalidates the corresponding J interpretation.  An aborted run remains under
a ``.partial`` path and is never accepted by the auditor.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from experiments.consciousness_sae_realization_validation import (  # noqa: E402
    controls,
    j_orientation,
    preexecution,
    protocol,
    runpod_preflight,
    runtime,
)


class ExecutionError(RuntimeError):
    pass


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ExecutionError(f"invalid JSON: {path}") from exc
    if not isinstance(value, dict):
        raise ExecutionError(f"JSON root is not an object: {path}")
    return value


def _write_json_path(path: Path, payload: Mapping[str, Any]) -> None:
    path.write_bytes(protocol.canonical_json_bytes(dict(payload)) + b"\n")
    with path.open("rb") as handle:
        os.fsync(handle.fileno())


def _write_jsonl_path(path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
    with path.open("xb") as handle:
        for row in rows:
            handle.write(protocol.canonical_json_bytes(dict(row)) + b"\n")
        handle.flush()
        os.fsync(handle.fileno())


def _validate_plan(plan_dir: Path) -> dict[str, Any]:
    root = plan_dir.expanduser().resolve(strict=True)
    manifest_path = root / "plan_manifest.json"
    manifest = _read_json(manifest_path)
    supplied_hash = manifest.get("plan_manifest_sha256")
    core = dict(manifest)
    core.pop("plan_manifest_sha256", None)
    if supplied_hash != protocol.canonical_sha256(core):
        raise ExecutionError("plan manifest self-hash differs")
    if (
        manifest.get("study_id") != protocol.STUDY_ID
        or manifest.get("protocol_version") != protocol.PROTOCOL_VERSION
    ):
        raise ExecutionError("plan identity differs")
    if manifest.get("prior_outcome_inputs") != []:
        raise ExecutionError("plan declares prior outcome inputs")
    records = manifest.get("files")
    if not isinstance(records, list) or not records:
        raise ExecutionError("plan file inventory is missing")
    for record in records:
        path = root / str(record["path"])
        if (
            not path.is_file()
            or path.stat().st_size != int(record["bytes"])
            or protocol.sha256_file(path) != record["sha256"]
        ):
            raise ExecutionError(f"plan file record differs: {record.get('path')}")
    snapshot = _read_json(root / "protocol_snapshot.json")
    if protocol.canonical_json_bytes(snapshot) != protocol.canonical_json_bytes(
        protocol.protocol_snapshot()
    ):
        raise ExecutionError("runtime protocol snapshot differs from plan")
    expected_a = [json.loads(line) for line in (root / "stage_a_plan.jsonl").read_text().splitlines()]
    expected_b = [json.loads(line) for line in (root / "stage_b_plan.jsonl").read_text().splitlines()]
    if (
        protocol.canonical_json_bytes(expected_a)
        != protocol.canonical_json_bytes(list(protocol.stage_a_rows()))
        or protocol.canonical_json_bytes(expected_b)
        != protocol.canonical_json_bytes(list(protocol.stage_b_rows()))
    ):
        raise ExecutionError("machine-plan grid differs from frozen source")
    source_records = _read_json(root / "source_files.json").get("files")
    if not isinstance(source_records, list):
        raise ExecutionError("source inventory is missing")
    for record in source_records:
        source = REPO_ROOT / str(record["path"])
        if (
            not source.is_file()
            or source.stat().st_size != int(record["bytes"])
            or protocol.sha256_file(source) != record["sha256"]
        ):
            raise ExecutionError(f"bound source differs: {record.get('path')}")
    return manifest


def initialize_volume(root: Path, *, volume_id: str) -> Path:
    candidate = root.expanduser().resolve(strict=True)
    if candidate.is_symlink() or not candidate.is_dir():
        raise ExecutionError("volume root must be an existing real directory")
    sentinel = candidate / controls.VOLUME_SENTINEL
    payload = {
        "schema_version": controls.CONTROL_SCHEMA_VERSION,
        "study_slug": protocol.STUDY_SLUG,
        "study_id": protocol.STUDY_ID,
        "protocol_version": protocol.PROTOCOL_VERSION,
        "volume_id": volume_id,
        "purpose": controls.VOLUME_PURPOSE,
    }
    if sentinel.exists():
        if _read_json(sentinel) != payload:
            raise ExecutionError("existing validation volume sentinel differs")
        return sentinel
    _write_json_path(sentinel, payload)
    return sentinel


@dataclass
class ResourceWatchdog:
    hourly_price_usd: float
    campaign_started_at_unix: float
    provider_terminate_at_unix: float
    last_progress_at_unix: float

    @classmethod
    def create(
        cls,
        hourly_price_usd: float,
        *,
        campaign_started_at_unix: float,
        provider_terminate_at_unix: float,
    ) -> "ResourceWatchdog":
        if not math.isfinite(hourly_price_usd) or hourly_price_usd <= 0:
            raise ExecutionError("hourly GPU price must be finite and positive")
        maximum = protocol.RESOURCE_LIMITS["max_spend_usd"]
        duration = provider_terminate_at_unix - campaign_started_at_unix
        if (
            not math.isfinite(campaign_started_at_unix)
            or not math.isfinite(provider_terminate_at_unix)
            or duration <= 0
            or duration > protocol.RESOURCE_LIMITS["max_walltime_seconds"]
        ):
            raise ExecutionError("provider terminateAfter window exceeds the frozen six hours")
        hours = duration / 3600
        if hourly_price_usd * hours > maximum:
            raise ExecutionError("six-hour worst-case cost exceeds the frozen $36 ceiling")
        result = cls(
            hourly_price_usd=hourly_price_usd,
            campaign_started_at_unix=campaign_started_at_unix,
            provider_terminate_at_unix=provider_terminate_at_unix,
            last_progress_at_unix=time.time(),
        )
        result.check()
        return result

    def check(self, *, progress: bool = True) -> None:
        now = time.time()
        meter = runpod_preflight.CumulativeMeter(
            provider_created_at=datetime.fromtimestamp(
                self.campaign_started_at_unix, tz=timezone.utc
            ),
            provider_terminate_after=datetime.fromtimestamp(
                self.provider_terminate_at_unix, tz=timezone.utc
            ),
            hourly_price_usd=self.hourly_price_usd,
        )
        try:
            meter.check(
                observed_at=datetime.fromtimestamp(now, tz=timezone.utc),
                current_process_elapsed_seconds=max(
                    0.0, now - self.campaign_started_at_unix
                ),
                seconds_since_progress=max(0.0, now - self.last_progress_at_unix),
            )
        except runpod_preflight.PreflightError as exc:
            raise ExecutionError(f"cumulative/no-progress guard failed: {exc}") from exc
        if progress:
            self.last_progress_at_unix = now

    def receipt(self) -> dict[str, Any]:
        elapsed = time.time() - self.campaign_started_at_unix
        return {
            "cumulative_elapsed_seconds": elapsed,
            "campaign_started_at_unix": self.campaign_started_at_unix,
            "provider_terminate_at_unix": self.provider_terminate_at_unix,
            "hourly_price_usd": self.hourly_price_usd,
            "cumulative_estimated_spend_usd": elapsed / 3600 * self.hourly_price_usd,
            "max_walltime_seconds": protocol.RESOURCE_LIMITS["max_walltime_seconds"],
            "max_spend_usd": protocol.RESOURCE_LIMITS["max_spend_usd"],
        }


class RawTransaction:
    def __init__(
        self,
        *,
        volume_root: Path,
        volume_id: str,
        run_id: str,
        stage: str,
        plan_hash: str,
        storage_budget: Mapping[str, Any],
    ) -> None:
        destination = controls.require_fresh_raw_run_path(
            volume_root, volume_id=volume_id, run_id=run_id
        )
        partial = destination.with_name(destination.name + ".partial")
        if partial.exists() or partial.is_symlink():
            raise ExecutionError("partial run path already exists")
        try:
            budget = controls.validate_storage_budget(storage_budget)
            usage = runpod_preflight.measure_volume_usage(volume_root)
        except (controls.ControlViolation, runpod_preflight.PreflightError) as exc:
            raise ExecutionError(f"storage authorization failed: {exc}") from exc
        if (
            budget["plan_manifest_sha256"] != plan_hash
            or budget["volume_id"] != volume_id
        ):
            raise ExecutionError("storage budget plan/volume binding differs")
        required = (
            protocol.RESOURCE_LIMITS["raw_run_ceiling_bytes"]
            + protocol.RESOURCE_LIMITS["post_run_free_reserve_bytes"]
        )
        if usage["quota_remaining_bytes"] < required:
            raise ExecutionError(
                "network volume quota needs at least "
                f"{required} free bytes; observed {usage['quota_remaining_bytes']}"
            )
        partial.parent.mkdir(parents=True, exist_ok=True)
        partial.mkdir(mode=0o750)
        self.destination = destination
        self.partial = partial
        self.volume_root = volume_root.resolve()
        self.volume_id = volume_id
        self.run_id = run_id
        self.stage = stage
        self.plan_hash = plan_hash
        self.records: list[dict[str, Any]] = []
        self.ledger = controls.StorageLedger(budget)
        self.closed = False
        self.free_before = int(usage["quota_remaining_bytes"])

    def _quota_remaining(self) -> int:
        try:
            usage = runpod_preflight.measure_volume_usage(self.volume_root)
        except runpod_preflight.PreflightError as exc:
            raise ExecutionError(f"volume quota refresh failed: {exc}") from exc
        return int(usage["quota_remaining_bytes"])

    def _authorize(self, estimated_bytes: int) -> None:
        try:
            self.ledger.authorize_next_shard(
                free_bytes_now=self._quota_remaining(),
                next_shard_bytes=max(0, int(estimated_bytes)),
            )
        except controls.ControlViolation as exc:
            raise ExecutionError(f"storage high-water gate failed: {exc}") from exc

    def _register(self, path: Path, role: str) -> None:
        relative = path.relative_to(self.partial).as_posix()
        size = path.stat().st_size
        if size > protocol.RESOURCE_LIMITS["max_shard_bytes"]:
            raise ExecutionError(f"shard exceeds 2 GiB: {relative}")
        total = sum(int(row["bytes"]) for row in self.records) + size
        if total > protocol.RESOURCE_LIMITS["raw_run_ceiling_bytes"]:
            raise ExecutionError("raw run exceeded its 32 GiB ceiling")
        digest = protocol.sha256_file(path)
        record = {
            "path": relative,
            "role": role,
            "bytes": size,
            "sha256": digest,
        }
        self.records.append(record)
        try:
            self.ledger.add(
                relative_path=f"raw/{relative}",
                stored_bytes=size,
                logical_bytes=size,
                sha256=digest,
                artifact_role=role,
            )
        except controls.ControlViolation as exc:
            raise ExecutionError(f"storage ledger rejected shard: {exc}") from exc

    def write_json(self, relative: str, payload: Mapping[str, Any], *, role: str) -> Path:
        path = self.partial / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            raise ExecutionError(f"refusing to overwrite {relative}")
        self._authorize(len(protocol.canonical_json_bytes(dict(payload))) + 1)
        _write_json_path(path, payload)
        self._register(path, role)
        return path

    def write_jsonl(
        self, relative: str, rows: Iterable[Mapping[str, Any]], *, role: str
    ) -> Path:
        path = self.partial / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        materialized = [dict(row) for row in rows]
        estimated = sum(
            len(protocol.canonical_json_bytes(row)) + 1 for row in materialized
        )
        self._authorize(estimated)
        _write_jsonl_path(path, materialized)
        self._register(path, role)
        return path

    def write_tensors(self, relative: str, tensors: Mapping[str, Any], *, role: str) -> Path:
        try:
            from safetensors.torch import save_file
        except ImportError as exc:  # pragma: no cover - GPU environment only
            raise ExecutionError("safetensors is required") from exc
        path = self.partial / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            raise ExecutionError(f"refusing to overwrite {relative}")
        values = {name: value.detach().to(device="cpu").contiguous() for name, value in tensors.items()}
        estimated = sum(
            int(value.numel()) * int(value.element_size()) for value in values.values()
        ) + 1024**2
        self._authorize(estimated)
        save_file(values, str(path))
        with path.open("rb") as handle:
            os.fsync(handle.fileno())
        self._register(path, role)
        return path

    def abort(self, error: BaseException, watchdog: ResourceWatchdog) -> None:
        if self.closed:
            return
        payload = {
            "study_id": protocol.STUDY_ID,
            "protocol_version": protocol.PROTOCOL_VERSION,
            "status": "aborted",
            "stage": self.stage,
            "run_id": self.run_id,
            "plan_manifest_sha256": self.plan_hash,
            "error_type": type(error).__name__,
            "error": str(error),
            "resource": watchdog.receipt(),
        }
        path = self.partial / "ABORTED.json"
        if not path.exists():
            _write_json_path(path, payload)
        self.closed = True

    def finalize(
        self,
        *,
        watchdog: ResourceWatchdog,
        runtime_metadata: Mapping[str, Any],
    ) -> Path:
        if self.closed:
            raise ExecutionError("transaction already closed")
        free_after = self._quota_remaining()
        if free_after < protocol.RESOURCE_LIMITS["post_run_free_reserve_bytes"]:
            raise ExecutionError("post-run 64 GiB reserve was not preserved")
        try:
            storage_ledger = self.ledger.finalize(free_bytes_after_run=free_after)
        except controls.ControlViolation as exc:
            raise ExecutionError(f"storage ledger finalization failed: {exc}") from exc
        try:
            output_tree = runpod_preflight.validate_study_owned_output_tree(
                self.partial
            )
        except runpod_preflight.PreflightError as exc:
            raise ExecutionError(f"study-owned output tree failed: {exc}") from exc
        core = {
            "schema_version": 1,
            "status": "complete",
            "study_id": protocol.STUDY_ID,
            "protocol_version": protocol.PROTOCOL_VERSION,
            "stage": self.stage,
            "run_id": self.run_id,
            "plan_manifest_sha256": self.plan_hash,
            "volume_id": self.volume_id,
            "free_bytes_before": self.free_before,
            "free_bytes_after": free_after,
            "records": list(self.records),
            "runtime": dict(runtime_metadata),
            "resource": watchdog.receipt(),
            "storage_ledger": storage_ledger,
            "study_owned_output_tree_before_completion": output_tree,
            "prior_outcome_inputs": [],
        }
        complete = {**core, "receipt_sha256": protocol.canonical_sha256(core)}
        _write_json_path(self.partial / "RUN_COMPLETE.json", complete)
        os.replace(self.partial, self.destination)
        self.closed = True
        return self.destination


def _load_backend(
    *,
    model_snapshot: Path,
    sae_path: Path,
    j_lens_path: Path,
    ownership_receipt_sha256: str,
    shadow_layers: Sequence[int] = (),
) -> tuple[Any, runtime.V2Backend, dict[str, Any]]:
    # This is intentionally the first operation: a missing launcher binding
    # fails before Transformers can import Torch or initialize model state.
    runtime.validate_guest_launch_environment(
        ownership_receipt_sha256=ownership_receipt_sha256
    )
    artifact_records = runtime.verify_public_artifacts(
        sae_path=sae_path, j_lens_path=j_lens_path
    )
    tokenizer = runtime.load_tokenizer(model_snapshot)
    backend = runtime.V2Backend(
        model_snapshot=model_snapshot,
        sae_path=sae_path,
        j_lens_path=j_lens_path,
        tokenizer=tokenizer,
        ownership_receipt_sha256=ownership_receipt_sha256,
        load_shadow_layers=shadow_layers,
    )
    return tokenizer, backend, artifact_records


def _validate_guest_chain(
    *,
    ownership_receipt_path: Path,
    guest_receipt_path: Path,
    cache_receipt_path: Path,
    volume_id: str,
    model_snapshot: Path,
    sae_path: Path,
    j_lens_path: Path,
    campaign_started_at_unix: float,
    provider_terminate_at_unix: float,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    ownership = _read_json(ownership_receipt_path)
    guest = _read_json(guest_receipt_path)
    cache = _read_json(cache_receipt_path)
    try:
        validated_ownership = runpod_preflight.validate_ownership_receipt(ownership)
        validated_guest = runpod_preflight.validate_guest_receipt(
            guest, ownership_receipt=validated_ownership
        )
        validated_cache = runpod_preflight.validate_cache_receipt(
            cache,
            guest_receipt=validated_guest,
            ownership_receipt=validated_ownership,
        )
    except runpod_preflight.PreflightError as exc:
        raise ExecutionError(f"ownership/guest/artifact preflight failed: {exc}") from exc
    if volume_id != validated_ownership["network_volume_id"]:
        raise ExecutionError("runner volume ID differs from owned provider volume")
    observed_pod_id = os.environ.get("RUNPOD_POD_ID")
    if observed_pod_id != validated_ownership["pod_id"]:
        raise ExecutionError("RUNPOD_POD_ID differs from ownership receipt")
    from datetime import datetime

    created = datetime.fromisoformat(
        validated_ownership["created_at"].replace("Z", "+00:00")
    ).timestamp()
    terminate = datetime.fromisoformat(
        validated_ownership["terminate_after"].replace("Z", "+00:00")
    ).timestamp()
    if abs(created - campaign_started_at_unix) > 1 or abs(terminate - provider_terminate_at_unix) > 1:
        raise ExecutionError("cumulative runner clock differs from provider ownership receipt")
    cache_root = Path(validated_cache["cache_root"]).resolve(strict=True)
    expected_paths = {
        "model": cache_root / "model_snapshot",
        "sae": cache_root / "sae" / "Llama-3.3-70B-Instruct-SAE-l50.pt",
        "j_lens": cache_root / "jlens" / "Llama-3.3-70B-Instruct_jacobian_lens.pt",
    }
    observed_paths = {
        "model": model_snapshot.resolve(strict=True),
        "sae": sae_path.resolve(strict=True),
        "j_lens": j_lens_path.resolve(strict=True),
    }
    if observed_paths != {key: value.resolve(strict=True) for key, value in expected_paths.items()}:
        raise ExecutionError("runner artifacts are outside the independently staged v1 cache")
    return validated_ownership, validated_guest, validated_cache


def _validate_stage_a_stopship_chain(
    *,
    plan_dir: Path,
    plan_hash: str,
    volume_root: Path,
    run_id: str,
    preexecution_authorization_path: Path,
    smoke_receipt_path: Path,
    ownership: Mapping[str, Any],
    guest: Mapping[str, Any],
    cache: Mapping[str, Any],
    campaign_started_at_unix: float,
    provider_terminate_at_unix: float,
) -> tuple[dict[str, Any], dict[str, Any], str]:
    """Fail before transaction/model creation unless authorization and smoke join."""

    from experiments.consciousness_sae_realization_validation import smoke_test

    try:
        authorization = preexecution.load_execution_authorization(
            preexecution_authorization_path,
            repo_root=REPO_ROOT,
            plan_dir=plan_dir,
            ownership_receipt=ownership,
            guest_receipt=guest,
            cache_receipt=cache,
        )
    except preexecution.PreexecutionError as exc:
        raise ExecutionError(f"Stage A pre-execution authorization failed: {exc}") from exc
    smoke_input = Path(os.path.abspath(smoke_receipt_path.expanduser()))
    if smoke_input.is_symlink() or not smoke_input.is_file() or smoke_input.stat().st_nlink != 1:
        raise ExecutionError("Stage A smoke receipt is not a single-link regular file")
    smoke = _read_json(smoke_input)
    try:
        validated_smoke = smoke_test.validate_smoke_receipt(
            smoke,
            expected_plan_hash=plan_hash,
            expected_authorization=authorization,
        )
    except smoke_test.SmokeTestError as exc:
        raise ExecutionError(f"Stage A smoke receipt failed: {exc}") from exc
    root = controls.require_volume_root(
        volume_root, volume_id=str(authorization["network_volume_id"])
    )
    try:
        smoke_file_hash = smoke_test.validate_external_receipt_file(
            volume_root=root,
            receipt_path=smoke_input,
            receipt=validated_smoke,
        )
    except smoke_test.SmokeTestError as exc:
        raise ExecutionError(f"Stage A smoke receipt path failed: {exc}") from exc
    if (
        validated_smoke["run_id"] == run_id
        or authorization["plan_manifest_sha256"] != plan_hash
        or authorization["campaign_started_at_unix"] != campaign_started_at_unix
        or authorization["provider_terminate_at_unix"]
        != provider_terminate_at_unix
        or validated_smoke["completed_at_unix"] > time.time()
    ):
        raise ExecutionError("Stage A authorization/smoke/campaign identity differs")
    return authorization, validated_smoke, smoke_file_hash


def _prompt_receipt(tokenizer: Any, prompt_id: str) -> dict[str, Any]:
    token_ids = runtime.render_prompt(tokenizer, prompt_id)
    return {
        "prompt_id": prompt_id,
        "prompt_payload_sha256": protocol.canonical_sha256(protocol.prompt_payload(prompt_id)),
        "token_ids": list(token_ids),
        "token_ids_sha256": runtime.token_ids_sha256(token_ids),
        "token_count": len(token_ids),
    }


def _actual_selected_delta(
    backend: runtime.V2Backend,
    plus: runtime.ArcTrace,
    minus: runtime.ArcTrace,
    token_ids: Sequence[int],
) -> Any:
    return (
        backend.selected_logits_from_state(
            plus.final_residual.to(device=backend.device), token_ids
        )
        - backend.selected_logits_from_state(
            minus.final_residual.to(device=backend.device), token_ids
        )
    ) * 0.5


def execute_stage_a(
    *,
    plan_dir: Path,
    volume_root: Path,
    volume_id: str,
    run_id: str,
    model_snapshot: Path,
    sae_path: Path,
    j_lens_path: Path,
    hourly_price_usd: float,
    campaign_started_at_unix: float,
    provider_terminate_at_unix: float,
    ownership_receipt_path: Path,
    guest_receipt_path: Path,
    cache_receipt_path: Path,
    storage_budget_path: Path,
    preexecution_authorization_path: Path,
    smoke_receipt_path: Path,
) -> Path:
    plan = _validate_plan(plan_dir)
    plan_hash = str(plan["plan_manifest_sha256"])
    watchdog = ResourceWatchdog.create(
        hourly_price_usd,
        campaign_started_at_unix=campaign_started_at_unix,
        provider_terminate_at_unix=provider_terminate_at_unix,
    )
    ownership, guest, cache = _validate_guest_chain(
        ownership_receipt_path=ownership_receipt_path,
        guest_receipt_path=guest_receipt_path,
        cache_receipt_path=cache_receipt_path,
        volume_id=volume_id,
        model_snapshot=model_snapshot,
        sae_path=sae_path,
        j_lens_path=j_lens_path,
        campaign_started_at_unix=campaign_started_at_unix,
        provider_terminate_at_unix=provider_terminate_at_unix,
    )
    storage_budget = _read_json(storage_budget_path)
    try:
        controls.validate_storage_budget(storage_budget)
    except controls.ControlViolation as exc:
        raise ExecutionError(f"Stage A storage budget failed: {exc}") from exc
    authorization, smoke, smoke_file_hash = _validate_stage_a_stopship_chain(
        plan_dir=plan_dir,
        plan_hash=plan_hash,
        volume_root=volume_root,
        run_id=run_id,
        preexecution_authorization_path=preexecution_authorization_path,
        smoke_receipt_path=smoke_receipt_path,
        ownership=ownership,
        guest=guest,
        cache=cache,
        campaign_started_at_unix=campaign_started_at_unix,
        provider_terminate_at_unix=provider_terminate_at_unix,
    )
    transaction = RawTransaction(
        volume_root=volume_root,
        volume_id=volume_id,
        run_id=run_id,
        stage="stage_a",
        plan_hash=plan_hash,
        storage_budget=storage_budget,
    )
    backend: runtime.V2Backend | None = None
    try:
        tokenizer, backend, artifact_records = _load_backend(
            model_snapshot=model_snapshot,
            sae_path=sae_path,
            j_lens_path=j_lens_path,
            ownership_receipt_sha256=ownership["receipt_sha256"],
            shadow_layers=protocol.STAGE_A_LAYERS,
        )
        transaction.write_json(
            "execution_binding.json",
            {
                "study_id": protocol.STUDY_ID,
                "protocol_version": protocol.PROTOCOL_VERSION,
                "stage": "stage_a",
                "plan_manifest_sha256": plan_hash,
                "model_snapshot": model_snapshot.resolve().as_posix(),
                "model_revision": protocol.MODEL_SPEC["revision"],
                "artifacts": artifact_records,
                "container_image": protocol.CONTAINER_IMAGE_SPEC,
                "ownership_receipt_sha256": ownership["receipt_sha256"],
                "guest_receipt_sha256": guest["receipt_sha256"],
                "cache_receipt_sha256": cache["receipt_sha256"],
                "storage_budget_receipt_sha256": storage_budget[
                    "receipt_sha256"
                ],
                "preexecution_authorization_sha256": authorization[
                    "receipt_sha256"
                ],
                "smoke_receipt_sha256": smoke["receipt_sha256"],
                "smoke_receipt_file_sha256": smoke_file_hash,
                "smoke_receipt_relative_path": smoke[
                    "external_receipt_relative_path"
                ],
                "campaign_identity_sha256": authorization[
                    "campaign_identity_sha256"
                ],
                "prior_outcome_inputs": [],
            },
            role="execution_binding",
        )
        # Establish the frozen production J convention independently before
        # rendering a single Stage-A prompt.  The fixtures are target-free and
        # perform no model forwards; both their rows and adjudicating receipt
        # become immutable raw artifacts in this transaction.
        orientation_rows = j_orientation.execute_orientation_rows(
            backend, plan_manifest_sha256=plan_hash
        )
        orientation_receipt = j_orientation.build_orientation_receipt(
            orientation_rows, plan_manifest_sha256=plan_hash
        )
        transaction.write_jsonl(
            "j_orientation_rows.jsonl",
            orientation_rows,
            role="j_arithmetic_orientation_rows",
        )
        transaction.write_json(
            "j_orientation_receipt.json",
            orientation_receipt,
            role="j_arithmetic_orientation_receipt",
        )
        if orientation_receipt["status"] != "pass":
            raise ExecutionError(
                "J arithmetic/orientation stop-ship failed before Stage-A prompts"
            )

        prompt_receipts = [
            _prompt_receipt(tokenizer, prompt_id)
            for prompt_id in protocol.STAGE_A_PROMPT_IDS
        ]
        transaction.write_jsonl(
            "prompt_receipts.jsonl", prompt_receipts, role="prompt_receipts"
        )
        selected_ids = runtime.fixed_token_panel()
        transaction.write_json(
            "fixed_token_panel.json",
            {
                "token_ids": list(selected_ids),
                "sha256": protocol.canonical_sha256(list(selected_ids)),
            },
            role="fixed_token_panel",
        )

        branch_index: list[dict[str, Any]] = []
        realization_rows: list[dict[str, Any]] = []
        transport_rows: list[dict[str, Any]] = []
        j_shadow_rows: list[dict[str, Any]] = []
        linearity_rows: list[dict[str, Any]] = []
        arithmetic_index: list[dict[str, Any]] = []
        clean_tensors: list[Any] = []
        clean_index: list[dict[str, Any]] = []

        for prompt_id in protocol.STAGE_A_PROMPT_IDS:
            watchdog.check()
            token_ids = runtime.render_prompt(tokenizer, prompt_id)
            session = backend.prepare_arc(token_ids)
            prompt_tensors: list[Any] = []
            prompt_arithmetic: dict[str, list[Any]] = {
                "requested_fp32_positive": [],
                "requested_bfloat16_positive": [],
                "realized_plus_fp32": [],
                "realized_minus_fp32": [],
                "realized_central_fp32": [],
                "common_mode_fp32": [],
                "final_central_fp32": [],
                "bf16_j_prediction_bfloat16": [],
                "fp32_j_prediction_fp32": [],
                "transport_predicted_bfloat16": [],
                "actual_selected_logit_delta_fp32": [],
                "transport_predicted_selected_logit_delta_fp32": [],
            }
            try:
                clean = backend.torch.stack(
                    [session.clean.residual_by_layer[layer] for layer in protocol.J_LAYERS]
                    + [session.clean.final_residual]
                ).contiguous()
                clean_index.append(
                    {
                        "row_index": len(clean_tensors),
                        "prompt_id": prompt_id,
                        "token_ids_sha256": session.token_ids_sha256,
                        "state_labels": [*(str(layer) for layer in protocol.J_LAYERS), "final"],
                    }
                )
                clean_tensors.append(clean)
                for edit_layer in protocol.STAGE_A_LAYERS:
                    clean_source = session.clean.residual_by_layer[edit_layer]
                    clean_rms = runtime.tensor_rms(clean_source)
                    for direction in protocol.STAGE_A_DIRECTIONS:
                        unit = runtime.deterministic_direction(edit_layer, direction)
                        dose_data: dict[float, tuple[Any, Any, Any, float, float]] = {}
                        for dose in protocol.DOSE_GRID:
                            watchdog.check()
                            requested_fp32 = (unit * (clean_rms * dose)).to(
                                dtype=backend.torch.float32
                            ).contiguous()
                            requested = requested_fp32.to(
                                dtype=backend.torch.bfloat16
                            ).contiguous()
                            negative = backend.torch.neg(requested).contiguous()
                            identity = f"{prompt_id}:{edit_layer}:{direction}:{dose}"
                            plus = session.edited(
                                edit_layer,
                                requested.to(device=backend.device),
                                forward_id=identity + ":plus",
                            )
                            minus = session.edited(
                                edit_layer,
                                negative.to(device=backend.device),
                                forward_id=identity + ":minus",
                            )
                            base = {
                                "prompt_id": prompt_id,
                                "edit_layer": edit_layer,
                                "direction": direction,
                                "dose_fraction": dose,
                                "target_prompt_used": False,
                            }
                            plus_row = len(prompt_tensors)
                            prompt_tensors.append(
                                runtime.trace_stage_a_tensor(plus, edit_layer=edit_layer)
                            )
                            branch_index.append(
                                {
                                    **base,
                                    "sign": 1,
                                    "shard": f"residuals/{prompt_id}.safetensors",
                                    "shard_row": plus_row,
                                    "state_labels": [
                                        *(str(layer) for layer in protocol.J_LAYERS),
                                        "edit_post",
                                        "final",
                                    ],
                                }
                            )
                            minus_row = len(prompt_tensors)
                            prompt_tensors.append(
                                runtime.trace_stage_a_tensor(minus, edit_layer=edit_layer)
                            )
                            branch_index.append(
                                {
                                    **base,
                                    "sign": -1,
                                    "shard": f"residuals/{prompt_id}.safetensors",
                                    "shard_row": minus_row,
                                    "state_labels": [
                                        *(str(layer) for layer in protocol.J_LAYERS),
                                        "edit_post",
                                        "final",
                                    ],
                                }
                            )
                            values, realized, final_central = runtime.realization_metrics(
                                clean_source,
                                plus,
                                minus,
                                requested,
                                requested_positive_fp32=requested_fp32,
                            )
                            shadow = runtime.fp32_shadow_metrics(
                                backend,
                                edit_layer=edit_layer,
                                realized_central=realized,
                                final_central=final_central,
                            )
                            j_shadow_rows.append(
                                {
                                    **base,
                                    "j_map_shadow_dtype": "float32",
                                    "arithmetic_shadow_dtype": "float32",
                                    **{
                                        key: value
                                        for key, value in shadow.items()
                                        if not key.startswith("_")
                                    },
                                    "finite": True,
                                    "target_prompt_used": False,
                                    "target_outcome_count": 0,
                                }
                            )
                            assert plus.pre_edit is not None and plus.post_edit is not None
                            assert minus.pre_edit is not None and minus.post_edit is not None
                            upstream_layers = tuple(
                                layer
                                for layer in protocol.J_LAYERS
                                if layer < edit_layer
                            )
                            upstream_equal_plus = all(
                                backend.torch.equal(
                                    plus.residual_by_layer[layer],
                                    session.clean.residual_by_layer[layer],
                                )
                                for layer in upstream_layers
                            )
                            upstream_equal_minus = all(
                                backend.torch.equal(
                                    minus.residual_by_layer[layer],
                                    session.clean.residual_by_layer[layer],
                                )
                                for layer in upstream_layers
                            )
                            realized_plus = plus.post_edit.float() - plus.pre_edit.float()
                            realized_minus = minus.post_edit.float() - minus.pre_edit.float()
                            common = (
                                (plus.post_edit.float() + minus.post_edit.float()) * 0.5
                                - clean_source.float()
                            )
                            arithmetic_row = len(prompt_arithmetic["requested_fp32_positive"])
                            prompt_arithmetic["requested_fp32_positive"].append(requested_fp32)
                            prompt_arithmetic["requested_bfloat16_positive"].append(requested)
                            prompt_arithmetic["realized_plus_fp32"].append(realized_plus)
                            prompt_arithmetic["realized_minus_fp32"].append(realized_minus)
                            prompt_arithmetic["realized_central_fp32"].append(realized)
                            prompt_arithmetic["common_mode_fp32"].append(common)
                            prompt_arithmetic["final_central_fp32"].append(
                                final_central.to(
                                    device="cpu", dtype=backend.torch.float32
                                ).contiguous()
                            )
                            prompt_arithmetic["bf16_j_prediction_bfloat16"].append(
                                shadow["_bf16_j_prediction"].to(
                                    device="cpu", dtype=backend.torch.bfloat16
                                ).contiguous()
                            )
                            prompt_arithmetic["fp32_j_prediction_fp32"].append(
                                shadow["_fp32_j_prediction"].to(
                                    device="cpu", dtype=backend.torch.float32
                                ).contiguous()
                            )
                            arithmetic_index.append(
                                {
                                    **base,
                                    "tensor_row": arithmetic_row,
                                    "shard": f"arithmetic/{prompt_id}.safetensors",
                                }
                            )
                            realization_rows.append(
                                {
                                    **base,
                                    "hook_fire_count_plus": values["hook_fire_count_plus"],
                                    "hook_fire_count_minus": values["hook_fire_count_minus"],
                                    "pre_equals_clean_plus": values["pre_equals_clean_plus"],
                                    "pre_equals_clean_minus": values["pre_equals_clean_minus"],
                                    "native_post_bytes_exact_plus": values[
                                        "native_post_bytes_exact_plus"
                                    ],
                                    "native_post_bytes_exact_minus": values[
                                        "native_post_bytes_exact_minus"
                                    ],
                                    "upstream_bytes_equal_clean_plus": upstream_equal_plus,
                                    "upstream_bytes_equal_clean_minus": upstream_equal_minus,
                                    "requested_vector_sha256": values[
                                        "requested_vector_sha256"
                                    ],
                                    "realized_central_sha256": values[
                                        "realized_central_sha256"
                                    ],
                                    "requested_plus_realized_relative_rmse": values[
                                        "requested_plus_realized_relative_rmse"
                                    ],
                                    "requested_minus_realized_relative_rmse": values[
                                        "requested_minus_realized_relative_rmse"
                                    ],
                                    "requested_realized_central_relative_rmse": values[
                                        "requested_realized_central_relative_rmse"
                                    ],
                                    "requested_realized_central_cosine": values[
                                        "requested_realized_central_cosine"
                                    ],
                                    "common_mode_to_central_rms": values[
                                        "common_mode_to_central_rms"
                                    ],
                                    "requested_rms_fraction": values["requested_rms_fraction"],
                                    "realized_rms_fraction": values["realized_rms_fraction"],
                                    "bf16_fp32_j_cosine": shadow["bf16_fp32_j_cosine"],
                                    "bf16_fp32_j_relative_rmse": shadow[
                                        "bf16_fp32_j_relative_rmse"
                                    ],
                                    "fp32_j_actual_final_cosine": shadow[
                                        "fp32_j_actual_final_cosine"
                                    ],
                                    "finite": bool(values["finite"] and shadow["finite"]),
                                }
                            )
                            actual_logit_delta = _actual_selected_delta(
                                backend, plus, minus, selected_ids
                            )
                            transport_predictions: list[Any] = []
                            transport_predicted_logits: list[Any] = []
                            for transport in protocol.TRANSPORTS:
                                metrics = runtime.transport_metrics(
                                    backend,
                                    session,
                                    edit_layer=edit_layer,
                                    realized_central=realized,
                                    final_central=final_central,
                                    plus=plus,
                                    minus=minus,
                                    transport=transport,
                                    selected_token_ids=selected_ids,
                                    actual_selected_logit_delta=actual_logit_delta,
                                )
                                transport_rows.append(
                                    {
                                        **base,
                                        "transport": transport,
                                        "residual_delta_cosine": metrics[
                                            "residual_delta_cosine"
                                        ],
                                        "fixed_token_logit_delta_pearson": metrics[
                                            "fixed_token_logit_delta_pearson"
                                        ],
                                        "finite": metrics["finite"],
                                    }
                                )
                                transport_predictions.append(
                                    metrics["_predicted_central_final"].to(
                                        device="cpu", dtype=backend.torch.bfloat16
                                    ).contiguous()
                                )
                                transport_predicted_logits.append(
                                    metrics["_predicted_selected_logit_delta"].to(
                                        device="cpu", dtype=backend.torch.float32
                                    ).contiguous()
                                )
                            prompt_arithmetic["transport_predicted_bfloat16"].append(
                                backend.torch.stack(transport_predictions).contiguous()
                            )
                            prompt_arithmetic["actual_selected_logit_delta_fp32"].append(
                                actual_logit_delta.to(
                                    device="cpu", dtype=backend.torch.float32
                                ).contiguous()
                            )
                            prompt_arithmetic[
                                "transport_predicted_selected_logit_delta_fp32"
                            ].append(
                                backend.torch.stack(
                                    transport_predicted_logits
                                ).contiguous()
                            )
                            realized_cpu = realized.to(device="cpu", dtype=backend.torch.float32)
                            j_realized_cpu = backend.transport_realized(
                                realized, layer=edit_layer, transport="real_j"
                            ).to(device="cpu", dtype=backend.torch.float32)
                            dose_data[dose] = (
                                realized_cpu,
                                j_realized_cpu,
                                final_central.to(device="cpu", dtype=backend.torch.float32),
                                float(values["realized_rms_fraction"]),
                                float(values["common_mode_to_central_rms"]),
                            )
                        anchor = dose_data[protocol.PRIMARY_DOSE]
                        anchor_slopes = tuple(value / anchor[3] for value in anchor[:3])
                        cosine_values: list[list[float]] = [[], [], []]
                        discrepancy_values: list[list[float]] = [[], [], []]
                        for dose in protocol.LINEARITY_GATE_DOSES:
                            observed = dose_data[dose]
                            for family_index, (value, anchor_slope) in enumerate(
                                zip(observed[:3], anchor_slopes, strict=True)
                            ):
                                observed_slope = value / observed[3]
                                cosine_values[family_index].append(
                                    runtime.cosine(observed_slope, anchor_slope)
                                )
                                discrepancy_values[family_index].append(
                                    runtime.relative_rmse(observed_slope, anchor_slope)
                                )
                        linearity_rows.append(
                            {
                                "prompt_id": prompt_id,
                                "edit_layer": edit_layer,
                                "direction": direction,
                                "dose_unit": controls.DOSE_UNIT,
                                "gate_doses": list(protocol.LINEARITY_GATE_DOSES),
                                "realized_source_linearity_cosine_min": min(cosine_values[0]),
                                "realized_source_slope_discrepancy_max": max(
                                    discrepancy_values[0]
                                ),
                                "j_of_realized_linearity_cosine_min": min(cosine_values[1]),
                                "j_of_realized_slope_discrepancy_max": max(
                                    discrepancy_values[1]
                                ),
                                "actual_final_linearity_cosine_min": min(cosine_values[2]),
                                "actual_final_slope_discrepancy_max": max(
                                    discrepancy_values[2]
                                ),
                                "finite": True,
                                "target_prompt_used": False,
                            }
                        )
            finally:
                session.close()
            tensor = backend.torch.stack(prompt_tensors).contiguous()
            if tuple(tensor.shape) != (288, 36, protocol.WIDTH):
                raise ExecutionError(f"Stage A shard shape differs for {prompt_id}")
            transaction.write_tensors(
                f"residuals/{prompt_id}.safetensors",
                {"residuals": tensor},
                role="stage_a_raw_residuals",
            )
            transaction.write_tensors(
                f"arithmetic/{prompt_id}.safetensors",
                {
                    name: backend.torch.stack(values).contiguous()
                    for name, values in prompt_arithmetic.items()
                },
                role="stage_a_exact_arithmetic_vectors",
            )
            del prompt_tensors, tensor

        transaction.write_tensors(
            "residuals/clean.safetensors",
            {"residuals": backend.torch.stack(clean_tensors).contiguous()},
            role="stage_a_clean_residuals",
        )
        transaction.write_jsonl("clean_index.jsonl", clean_index, role="clean_index")
        transaction.write_jsonl("branch_index.jsonl", branch_index, role="branch_index")
        transaction.write_jsonl(
            "arithmetic_index.jsonl", arithmetic_index, role="arithmetic_index"
        )
        transaction.write_jsonl(
            "realization_rows.jsonl", realization_rows, role="realization_metrics"
        )
        transaction.write_jsonl(
            "transport_rows.jsonl", transport_rows, role="transport_metrics"
        )
        transaction.write_jsonl(
            "j_map_shadow_rows.jsonl", j_shadow_rows, role="fp32_j_map_shadow_metrics"
        )
        transaction.write_jsonl(
            "linearity_rows.jsonl", linearity_rows, role="linearity_metrics"
        )
        runtime_metadata = backend.runtime_metadata()
        runtime_metadata.update(
            {
                "stage": "stage_a",
                "expected_edited_forward_count": 2304,
                "observed_prompt_session_count": 8,
                "realization_row_count": len(realization_rows),
                "transport_row_count": len(transport_rows),
                "j_map_shadow_row_count": len(j_shadow_rows),
                "linearity_row_count": len(linearity_rows),
                "j_orientation_row_count": len(orientation_rows),
                "j_orientation_status": orientation_receipt["status"],
            }
        )
        transaction.write_json(
            "runtime_metadata.json", runtime_metadata, role="runtime_metadata"
        )
        return transaction.finalize(
            watchdog=watchdog, runtime_metadata=runtime_metadata
        )
    except BaseException as exc:
        transaction.abort(exc, watchdog)
        raise
    finally:
        if backend is not None:
            backend.close()


def _validate_gate_receipts(
    *,
    stage_a_receipt_path: Path,
    audit_receipt_path: Path,
    stage_b_permit_path: Path,
    target_blind_receipt_path: Path,
    storage_budget_path: Path,
    plan_hash: str,
    run_id: str,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    stage_a = _read_json(stage_a_receipt_path)
    audit = _read_json(audit_receipt_path)
    target_blind = _read_json(target_blind_receipt_path)
    storage_budget = _read_json(storage_budget_path)
    permit = _read_json(stage_b_permit_path)
    try:
        validated_stage_a = controls.validate_stage_a_safety_receipt(stage_a)
        validated_permit = controls.validate_stage_b_permit(
            permit,
            stage_a_receipt=validated_stage_a,
            target_blind_receipt=target_blind,
            storage_budget=storage_budget,
        )
    except controls.ControlViolation as exc:
        raise ExecutionError(f"Stage B permit chain failed: {exc}") from exc
    core = dict(audit)
    supplied_audit_hash = core.pop("receipt_sha256", None)
    if (
        audit.get("status") != "pass"
        or audit.get("stage") != "stage_a"
        or audit.get("study_id") != protocol.STUDY_ID
        or audit.get("protocol_version") != protocol.PROTOCOL_VERSION
        or audit.get("plan_manifest_sha256") != plan_hash
        or supplied_audit_hash != protocol.canonical_sha256(core)
    ):
        raise ExecutionError("Stage A structural audit is not a passing bound receipt")
    if validated_stage_a["audit_receipt_sha256"] != supplied_audit_hash:
        raise ExecutionError("Stage A receipt is not bound to supplied audit receipt")
    try:
        numeric_recomputation = controls.validate_stage_a_numeric_recomputation(
            audit.get("details", {}).get("stage_a_numeric_recomputation", {})
        )
    except controls.ControlViolation as exc:
        raise ExecutionError(f"Stage A numeric audit chain failed: {exc}") from exc
    if (
        validated_stage_a["stage_a_numeric_recomputation_sha256"]
        != numeric_recomputation["classification_sha256"]
    ):
        raise ExecutionError("Stage A receipt is not bound to raw numeric audit")
    if audit.get("run_id") != validated_stage_a["run_id"]:
        raise ExecutionError("Stage A analysis and audit run identities differ")
    if validated_permit["run_id"] != run_id or validated_permit["plan_manifest_sha256"] != plan_hash:
        raise ExecutionError("Stage B permit does not authorize this exact run/plan")
    if audit.get("prior_outcome_inputs") != []:
        raise ExecutionError("gate receipt names prior outcome input")
    return validated_stage_a, audit, validated_permit


def _write_matching_artifacts(
    transaction: RawTransaction,
    *,
    table: Sequence[Mapping[str, Any]],
    mapping: Sequence[Mapping[str, Any]],
    token_count: int,
    decoder_hash: str,
) -> None:
    transaction.write_jsonl(
        "matching/feature_statistics.jsonl", table, role="fresh_matching_statistics"
    )
    transaction.write_json(
        "matching/matched_features.json",
        {
            "study_id": protocol.STUDY_ID,
            "protocol_version": protocol.PROTOCOL_VERSION,
            "source_prompt_ids": list(protocol.STAGE_A_PROMPT_IDS),
            "all_token_count": token_count,
            "decoder_bfloat16_sha256": decoder_hash,
            "mapping": list(mapping),
            "prior_outcome_inputs": [],
        },
        role="fresh_matching_map",
    )


def _validate_stage_b_authorization(
    *,
    plan_dir: Path,
    plan_hash: str,
    volume_id: str,
    preexecution_authorization_path: Path,
    stage_a_receipt: Mapping[str, Any],
    ownership: Mapping[str, Any],
    guest: Mapping[str, Any],
    cache: Mapping[str, Any],
    campaign_started_at_unix: float,
    provider_terminate_at_unix: float,
) -> dict[str, Any]:
    """Join Stage B to the exact Stage-A provider/campaign authorization."""

    try:
        authorization = preexecution.load_execution_authorization(
            preexecution_authorization_path,
            repo_root=REPO_ROOT,
            plan_dir=plan_dir,
            ownership_receipt=ownership,
            guest_receipt=guest,
            cache_receipt=cache,
        )
    except preexecution.PreexecutionError as exc:
        raise ExecutionError(
            f"Stage B pre-execution authorization failed: {exc}"
        ) from exc
    if (
        authorization["receipt_sha256"]
        != stage_a_receipt["preexecution_authorization_sha256"]
        or authorization["campaign_identity_sha256"]
        != stage_a_receipt["campaign_identity_sha256"]
        or authorization["plan_manifest_sha256"] != plan_hash
        or authorization["network_volume_id"] != volume_id
        or authorization["campaign_started_at_unix"]
        != campaign_started_at_unix
        or authorization["provider_terminate_at_unix"]
        != provider_terminate_at_unix
    ):
        raise ExecutionError(
            "Stage B authorization differs from Stage A or current campaign"
        )
    return authorization


def execute_stage_b(
    *,
    plan_dir: Path,
    volume_root: Path,
    volume_id: str,
    run_id: str,
    model_snapshot: Path,
    sae_path: Path,
    j_lens_path: Path,
    stage_a_receipt_path: Path,
    audit_receipt_path: Path,
    stage_b_permit_path: Path,
    target_blind_receipt_path: Path,
    storage_budget_path: Path,
    hourly_price_usd: float,
    campaign_started_at_unix: float,
    provider_terminate_at_unix: float,
    ownership_receipt_path: Path,
    guest_receipt_path: Path,
    cache_receipt_path: Path,
    preexecution_authorization_path: Path,
) -> Path:
    plan = _validate_plan(plan_dir)
    plan_hash = str(plan["plan_manifest_sha256"])
    stage_a_receipt, audit_receipt, stage_b_permit = _validate_gate_receipts(
        stage_a_receipt_path=stage_a_receipt_path,
        audit_receipt_path=audit_receipt_path,
        stage_b_permit_path=stage_b_permit_path,
        target_blind_receipt_path=target_blind_receipt_path,
        storage_budget_path=storage_budget_path,
        plan_hash=plan_hash,
        run_id=run_id,
    )
    watchdog = ResourceWatchdog.create(
        hourly_price_usd,
        campaign_started_at_unix=campaign_started_at_unix,
        provider_terminate_at_unix=provider_terminate_at_unix,
    )
    ownership, guest, cache = _validate_guest_chain(
        ownership_receipt_path=ownership_receipt_path,
        guest_receipt_path=guest_receipt_path,
        cache_receipt_path=cache_receipt_path,
        volume_id=volume_id,
        model_snapshot=model_snapshot,
        sae_path=sae_path,
        j_lens_path=j_lens_path,
        campaign_started_at_unix=campaign_started_at_unix,
        provider_terminate_at_unix=provider_terminate_at_unix,
    )
    authorization = _validate_stage_b_authorization(
        plan_dir=plan_dir,
        plan_hash=plan_hash,
        volume_id=volume_id,
        preexecution_authorization_path=preexecution_authorization_path,
        stage_a_receipt=stage_a_receipt,
        ownership=ownership,
        guest=guest,
        cache=cache,
        campaign_started_at_unix=campaign_started_at_unix,
        provider_terminate_at_unix=provider_terminate_at_unix,
    )
    transaction = RawTransaction(
        volume_root=volume_root,
        volume_id=volume_id,
        run_id=run_id,
        stage="stage_b",
        plan_hash=plan_hash,
        storage_budget=_read_json(storage_budget_path),
    )
    backend: runtime.V2Backend | None = None
    try:
        tokenizer, backend, artifact_records = _load_backend(
            model_snapshot=model_snapshot,
            sae_path=sae_path,
            j_lens_path=j_lens_path,
            ownership_receipt_sha256=ownership["receipt_sha256"],
        )
        transaction.write_json(
            "execution_binding.json",
            {
                "study_id": protocol.STUDY_ID,
                "protocol_version": protocol.PROTOCOL_VERSION,
                "stage": "stage_b",
                "plan_manifest_sha256": plan_hash,
                "stage_a_receipt_sha256": stage_a_receipt["receipt_sha256"],
                "stage_a_audit_receipt_sha256": audit_receipt["receipt_sha256"],
                "stage_b_permit_sha256": stage_b_permit["receipt_sha256"],
                "target_blind_receipt_sha256": stage_b_permit[
                    "target_blind_receipt_sha256"
                ],
                "storage_budget_receipt_sha256": stage_b_permit[
                    "storage_budget_receipt_sha256"
                ],
                "preexecution_authorization_sha256": authorization[
                    "receipt_sha256"
                ],
                "campaign_identity_sha256": authorization[
                    "campaign_identity_sha256"
                ],
                "model_snapshot": model_snapshot.resolve().as_posix(),
                "model_revision": protocol.MODEL_SPEC["revision"],
                "artifacts": artifact_records,
                "container_image": protocol.CONTAINER_IMAGE_SPEC,
                "ownership_receipt_sha256": ownership["receipt_sha256"],
                "guest_receipt_sha256": guest["receipt_sha256"],
                "cache_receipt_sha256": cache["receipt_sha256"],
                "prior_outcome_inputs": [],
            },
            role="execution_binding",
        )
        prompt_receipts = [
            _prompt_receipt(tokenizer, prompt_id)
            for prompt_id in protocol.STAGE_B_PROMPT_IDS
        ]
        transaction.write_jsonl(
            "prompt_receipts.jsonl", prompt_receipts, role="prompt_receipts"
        )
        selected_ids = runtime.fixed_token_panel()
        transaction.write_json(
            "fixed_token_panel.json",
            {
                "token_ids": list(selected_ids),
                "sha256": protocol.canonical_sha256(list(selected_ids)),
            },
            role="fixed_token_panel",
        )

        # Matching is recomputed from fresh, target-free all-token residuals.
        all_token_residuals = []
        for prompt_id in protocol.STAGE_A_PROMPT_IDS:
            watchdog.check()
            all_token_residuals.append(
                backend.capture_layer50_all_tokens(runtime.render_prompt(tokenizer, prompt_id))
            )
        table, mapping, matched_ids, token_count, decoder_hash = runtime.compute_fresh_matches(
            backend, all_token_residuals
        )
        _write_matching_artifacts(
            transaction,
            table=table,
            mapping=mapping,
            token_count=token_count,
            decoder_hash=decoder_hash,
        )
        vectors, vector_inventory = runtime.materialize_stage_b_vectors(
            backend.sae_decoder, matched_ids
        )
        transaction.write_tensors(
            "vectors/vectors.safetensors", {"vectors": vectors}, role="exact_edit_vectors"
        )
        transaction.write_jsonl(
            "vectors/vector_inventory.jsonl", vector_inventory, role="vector_inventory"
        )
        vector_lookup = {
            (row["assignment_id"], row["vector_class"]): vectors[int(row["row_index"])]
            for row in vector_inventory
        }

        # Every prompt/vector ratio is checked before the first Stage-B edit.
        preflight_rows: list[dict[str, Any]] = []
        for prompt_id in protocol.STAGE_B_PROMPT_IDS:
            watchdog.check()
            session = backend.prepare_arc(runtime.render_prompt(tokenizer, prompt_id))
            try:
                source_rms = runtime.tensor_rms(
                    session.clean.residual_by_layer[protocol.SAE_LAYER]
                )
                for row in vector_inventory:
                    vector = vectors[int(row["row_index"])]
                    for multiplier in protocol.STAGE_B_MULTIPLIERS:
                        requested = (vector * multiplier).to(
                            dtype=backend.torch.bfloat16
                        ).contiguous()
                        ratio = runtime.tensor_rms(requested) / source_rms
                        preflight_rows.append(
                            {
                                "prompt_id": prompt_id,
                                "assignment_id": row["assignment_id"],
                                "vector_class": row["vector_class"],
                                "multiplier": multiplier,
                                "vector_to_source_rms_ratio": ratio,
                                "pass": ratio <= 0.10,
                            }
                        )
                        if ratio > 0.10:
                            raise ExecutionError(
                                "Stage B vector exceeds 10% source RMS preflight"
                            )
            finally:
                session.close()
        transaction.write_jsonl(
            "vectors/preflight_rows.jsonl", preflight_rows, role="vector_preflight"
        )

        transaction.write_jsonl(
            "vocabulary.jsonl", runtime.vocabulary_rows(tokenizer), role="token_vocabulary"
        )
        branch_index: list[dict[str, Any]] = []
        edit_rows: list[dict[str, Any]] = []
        transport_rows: list[dict[str, Any]] = []
        topk_pair_index: list[dict[str, Any]] = []
        total_edited = 0
        for prompt_id in protocol.STAGE_B_PROMPT_IDS:
            watchdog.check()
            session = backend.prepare_arc(runtime.render_prompt(tokenizer, prompt_id))
            prompt_tensors: list[Any] = [runtime.trace_stage_b_tensor(session.clean)]
            prompt_arithmetic: dict[str, list[Any]] = {
                "requested_fp32": [],
                "requested_bfloat16": [],
                "realized_fp32": [],
            }
            prompt_index: list[dict[str, Any]] = [
                {
                    "prompt_id": prompt_id,
                    "condition": "clean",
                    "assignment_id": None,
                    "vector_class": None,
                    "sign": 0,
                    "shard": f"residuals/{prompt_id}.safetensors",
                    "shard_row": 0,
                    "state_labels": list(protocol.STAGE_B_CAPTURE_STATES),
                    "token_ids_sha256": session.token_ids_sha256,
                }
            ]
            pending_minus: dict[tuple[str, str, float], runtime.ArcTrace] = {}
            try:
                clean_source = session.clean.residual_by_layer[protocol.SAE_LAYER]
                clean_source_rms = runtime.tensor_rms(clean_source)
                for plan_row in protocol.stage_b_rows():
                    if plan_row["prompt_id"] != prompt_id:
                        continue
                    watchdog.check()
                    assignment_id = str(plan_row["assignment_id"])
                    vector_class = str(plan_row["vector_class"])
                    sign = int(plan_row["sign"])
                    multiplier = float(plan_row["multiplier"])
                    unsigned = vector_lookup[(assignment_id, vector_class)]
                    scaled_fp32 = unsigned.float().mul(multiplier).contiguous()
                    scaled = scaled_fp32.to(
                        dtype=backend.torch.bfloat16
                    ).contiguous()
                    signed = scaled if sign == 1 else backend.torch.neg(scaled).contiguous()
                    signed_fp32 = (
                        scaled_fp32
                        if sign == 1
                        else backend.torch.neg(scaled_fp32).contiguous()
                    )
                    forward_id = (
                        f"{prompt_id}:{assignment_id}:{vector_class}:{sign}:{multiplier}"
                    )
                    trace = session.edited(
                        protocol.SAE_LAYER,
                        signed.to(device=backend.device),
                        forward_id=forward_id,
                    )
                    if trace.pre_edit is None or trace.post_edit is None:
                        raise ExecutionError("Stage B hook telemetry is incomplete")
                    realized = trace.post_edit.float() - trace.pre_edit.float()
                    native = (trace.pre_edit + signed).to(dtype=backend.torch.bfloat16)
                    upstream_equal = all(
                        backend.torch.equal(
                            trace.residual_by_layer[layer],
                            session.clean.residual_by_layer[layer],
                        )
                        for layer in range(45, 50)
                    )
                    row = {
                        "prompt_id": prompt_id,
                        "assignment_id": assignment_id,
                        "vector_class": vector_class,
                        "sign": sign,
                        "multiplier": multiplier,
                        "hook_fire_count": trace.hook_fire_count,
                        "pre_equals_clean": bool(
                            backend.torch.equal(trace.pre_edit, clean_source)
                        ),
                        "native_post_bytes_exact": bool(
                            backend.torch.equal(trace.post_edit, native)
                        ),
                        "upstream_45_49_bytes_equal_clean": upstream_equal,
                        "requested_realized_relative_rmse": runtime.relative_rmse(
                            realized, signed
                        ),
                        "requested_realized_cosine": runtime.cosine(realized, signed),
                        "requested_rms_fraction": runtime.tensor_rms(signed)
                        / clean_source_rms,
                        "realized_rms_fraction": runtime.tensor_rms(realized)
                        / clean_source_rms,
                        "fp32_requested_to_bfloat16_relative_rmse": runtime.relative_rmse(
                            signed, signed_fp32
                        ),
                        "fp32_requested_to_bfloat16_cosine": runtime.cosine(
                            signed, signed_fp32
                        ),
                        "native_realized_to_fp32_requested_relative_rmse": runtime.relative_rmse(
                            realized, signed_fp32
                        ),
                        "native_realized_to_fp32_requested_cosine": runtime.cosine(
                            realized, signed_fp32
                        ),
                        "requested_vector_sha256": runtime.tensor_sha256(signed),
                        "requested_fp32_vector_sha256": runtime.tensor_sha256(signed_fp32),
                        "realized_vector_sha256": runtime.tensor_sha256(realized),
                        "finite": bool(backend.torch.isfinite(realized).all()),
                        "target_prompt_used": False,
                    }
                    edit_rows.append(row)
                    prompt_arithmetic["requested_fp32"].append(signed_fp32)
                    prompt_arithmetic["requested_bfloat16"].append(signed)
                    prompt_arithmetic["realized_fp32"].append(realized)
                    shard_row = len(prompt_tensors)
                    prompt_tensors.append(runtime.trace_stage_b_tensor(trace))
                    prompt_index.append(
                        {
                            **dict(plan_row),
                            "condition": "edited",
                            "shard": f"residuals/{prompt_id}.safetensors",
                            "shard_row": shard_row,
                            "state_labels": list(protocol.STAGE_B_CAPTURE_STATES),
                            "token_ids_sha256": session.token_ids_sha256,
                        }
                    )
                    pair_key = (assignment_id, vector_class, multiplier)
                    if sign == -1:
                        if pair_key in pending_minus:
                            raise ExecutionError("duplicate Stage B minus branch")
                        pending_minus[pair_key] = trace
                    else:
                        minus_trace = pending_minus.pop(pair_key, None)
                        if minus_trace is None:
                            raise ExecutionError("Stage B plus branch precedes its minus pair")
                        assert minus_trace.pre_edit is not None
                        assert minus_trace.post_edit is not None
                        realized_minus = (
                            minus_trace.post_edit.float() - minus_trace.pre_edit.float()
                        )
                        realized_central = (realized - realized_minus) * 0.5
                        final_central = (
                            trace.final_residual.float()
                            - minus_trace.final_residual.float()
                        ) * 0.5
                        actual_logit_delta = _actual_selected_delta(
                            backend, trace, minus_trace, selected_ids
                        )
                        realized_fraction = (
                            runtime.tensor_rms(realized_central) / clean_source_rms
                        )
                        for transport in protocol.TRANSPORTS:
                            transport_metric = runtime.transport_metrics(
                                backend,
                                session,
                                edit_layer=protocol.SAE_LAYER,
                                realized_central=realized_central,
                                final_central=final_central,
                                plus=trace,
                                minus=minus_trace,
                                transport=transport,
                                selected_token_ids=selected_ids,
                                actual_selected_logit_delta=actual_logit_delta,
                            )
                            transport_rows.append(
                                {
                                    "prompt_id": prompt_id,
                                    "assignment_id": assignment_id,
                                    "vector_class": vector_class,
                                    "multiplier": multiplier,
                                    "edit_layer": protocol.SAE_LAYER,
                                    "realized_rms_fraction": realized_fraction,
                                    "transport": transport,
                                    "residual_delta_cosine": transport_metric[
                                        "residual_delta_cosine"
                                    ],
                                    "fixed_token_logit_delta_pearson": transport_metric[
                                        "fixed_token_logit_delta_pearson"
                                    ],
                                    "finite": transport_metric["finite"],
                                    "target_prompt_used": False,
                                }
                            )
                    total_edited += 1
                if pending_minus:
                    raise ExecutionError("Stage B signed-pair transport grid is incomplete")
            finally:
                session.close()
            residual_tensor = backend.torch.stack(prompt_tensors).contiguous()
            if tuple(residual_tensor.shape) != (271, 36, protocol.WIDTH):
                raise ExecutionError(f"Stage B shard shape differs for {prompt_id}")
            transaction.write_tensors(
                f"residuals/{prompt_id}.safetensors",
                {"residuals": residual_tensor},
                role="stage_b_raw_residuals",
            )
            transaction.write_tensors(
                f"arithmetic/{prompt_id}.safetensors",
                {
                    name: backend.torch.stack(values).contiguous()
                    for name, values in prompt_arithmetic.items()
                },
                role="stage_b_exact_arithmetic_vectors",
            )
            shard_lookup = {
                (
                    row["assignment_id"],
                    row["vector_class"],
                    int(row["sign"]),
                    float(row["multiplier"]),
                ): int(row["shard_row"])
                for row in prompt_index
                if row["condition"] == "edited"
            }
            for pair_row, (assignment, vector_class, multiplier) in enumerate(
                (
                    (
                        assignment["assignment_id"],
                        vector_class,
                        float(multiplier),
                    )
                    for assignment in protocol.aggregate_assignments()
                    for vector_class in protocol.VECTOR_CLASSES
                    for multiplier in protocol.STAGE_B_MULTIPLIERS
                )
            ):
                topk_pair_index.append(
                    {
                        "prompt_id": prompt_id,
                        "pair_row": pair_row,
                        "assignment_id": assignment,
                        "vector_class": vector_class,
                        "multiplier": multiplier,
                        "minus_shard_row": shard_lookup[
                            (assignment, vector_class, -1, multiplier)
                        ],
                        "plus_shard_row": shard_lookup[
                            (assignment, vector_class, 1, multiplier)
                        ],
                        "state_labels": list(protocol.STAGE_B_CAPTURE_STATES),
                        "intermediate_readout": "j_lens_predicted_logits",
                        "final_readout": "actual_final_logits",
                    }
                )
            topk = runtime.stage_b_topk_archive(
                backend, residual_tensor, progress_callback=watchdog.check
            )
            transaction.write_tensors(
                f"topk/{prompt_id}.safetensors",
                topk,
                role="stage_b_topk_browse_index",
            )
            branch_index.extend(prompt_index)
            del prompt_tensors, residual_tensor, topk

        if total_edited != protocol.RESOURCE_LIMITS["max_stage_b_edited_forwards"]:
            raise ExecutionError("Stage B edited-forward grid is incomplete")
        transaction.write_jsonl("branch_index.jsonl", branch_index, role="branch_index")
        transaction.write_jsonl(
            "topk_pair_index.jsonl",
            topk_pair_index,
            role="paired_central_topk_index",
        )
        transaction.write_jsonl(
            "edit_realization_rows.jsonl", edit_rows, role="edit_realization_metrics"
        )
        transaction.write_jsonl(
            "transport_rows.jsonl", transport_rows, role="stage_b_transport_metrics"
        )
        runtime_metadata = backend.runtime_metadata()
        runtime_metadata.update(
            {
                "stage": "stage_b",
                "expected_edited_forward_count": 2160,
                "observed_edited_forward_count": total_edited,
                "transport_row_count": len(transport_rows),
                "raw_residuals_authoritative": True,
                "top_k_browse_index_only": True,
                "top_k": protocol.TOP_K,
            }
        )
        transaction.write_json(
            "runtime_metadata.json", runtime_metadata, role="runtime_metadata"
        )
        return transaction.finalize(
            watchdog=watchdog, runtime_metadata=runtime_metadata
        )
    except BaseException as exc:
        transaction.abort(exc, watchdog)
        raise
    finally:
        if backend is not None:
            backend.close()


def _common_parser(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--plan-dir", type=Path, required=True)
    parser.add_argument("--volume-root", type=Path, required=True)
    parser.add_argument("--volume-id", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--model-snapshot", type=Path, required=True)
    parser.add_argument("--sae-path", type=Path, required=True)
    parser.add_argument("--j-lens-path", type=Path, required=True)
    parser.add_argument("--hourly-price-usd", type=float, required=True)
    parser.add_argument("--campaign-started-at-unix", type=float, required=True)
    parser.add_argument("--provider-terminate-at-unix", type=float, required=True)
    parser.add_argument("--ownership-receipt", type=Path, required=True)
    parser.add_argument("--guest-receipt", type=Path, required=True)
    parser.add_argument("--cache-receipt", type=Path, required=True)
    parser.add_argument("--storage-budget", type=Path, required=True)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    init = subparsers.add_parser("init-volume")
    init.add_argument("--volume-root", type=Path, required=True)
    init.add_argument("--volume-id", required=True)
    stage_a = subparsers.add_parser("stage-a")
    _common_parser(stage_a)
    stage_a.add_argument(
        "--preexecution-authorization", type=Path, required=True
    )
    stage_a.add_argument("--smoke-receipt", type=Path, required=True)
    stage_b = subparsers.add_parser("stage-b")
    _common_parser(stage_b)
    stage_b.add_argument("--stage-a-receipt", type=Path, required=True)
    stage_b.add_argument("--stage-a-audit", type=Path, required=True)
    stage_b.add_argument("--stage-b-permit", type=Path, required=True)
    stage_b.add_argument("--target-blind-receipt", type=Path, required=True)
    stage_b.add_argument(
        "--preexecution-authorization", type=Path, required=True
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "init-volume":
        print(initialize_volume(args.volume_root, volume_id=args.volume_id))
        return 0
    common = {
        "plan_dir": args.plan_dir,
        "volume_root": args.volume_root,
        "volume_id": args.volume_id,
        "run_id": args.run_id,
        "model_snapshot": args.model_snapshot,
        "sae_path": args.sae_path,
        "j_lens_path": args.j_lens_path,
        "hourly_price_usd": args.hourly_price_usd,
        "campaign_started_at_unix": args.campaign_started_at_unix,
        "provider_terminate_at_unix": args.provider_terminate_at_unix,
        "ownership_receipt_path": args.ownership_receipt,
        "guest_receipt_path": args.guest_receipt,
        "cache_receipt_path": args.cache_receipt,
        "storage_budget_path": args.storage_budget,
    }
    if args.command == "stage-a":
        output = execute_stage_a(
            **common,
            preexecution_authorization_path=args.preexecution_authorization,
            smoke_receipt_path=args.smoke_receipt,
        )
    else:
        output = execute_stage_b(
            **common,
            stage_a_receipt_path=args.stage_a_receipt,
            audit_receipt_path=args.stage_a_audit,
            stage_b_permit_path=args.stage_b_permit,
            target_blind_receipt_path=args.target_blind_receipt,
            preexecution_authorization_path=args.preexecution_authorization,
        )
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

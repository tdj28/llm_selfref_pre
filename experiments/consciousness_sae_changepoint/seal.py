#!/usr/bin/env python3
"""Fail-closed structural audit, unseal, and analysis authorization.

This module is the one-way lifecycle boundary for confirmatory target results:

``audit``
    Revalidates the prospective execution gates, the exact frozen plan, every
    completed run/block/shard, and the common complete prefix set.  It reads
    only archive structure, compact status records, shard indexes, and hashes;
    it never opens generated text, scores, logits, or residual tensor values.

``unseal``
    Requires the completed structural audit and a *separately produced* sealed
    human-reliability archive.  The latter must contain two independent,
    condition-blind human label files, adjudicated labels, automated labels,
    and the frozen selection manifests.  Reliability is recomputed from those
    files; a claimed ``pass`` flag is never trusted.  This CLI intentionally has
    no command that creates, signs, or impersonates human evidence.

``authorize-analysis`` / ``check-analysis``
    Bind the whole chain and refuse analysis unless a completed unseal
    authorization exists and every upstream manifest still hashes identically.

All lifecycle receipts are ordinary :class:`RunTransaction` archives: written
under ``.partial``, inventoried, atomically renamed, and marked ``COMPLETE``
last.  Paths serialized in receipts are artifact-root-relative.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Mapping, Sequence


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from experiments.consciousness_sae_changepoint import paths  # noqa: E402
from experiments.consciousness_sae_changepoint.judge import (  # noqa: E402
    BINARY_QUERY_TASK,
    NATURAL_STANCE_TASK,
    RUBRIC_BY_TASK,
    assess_reliability_gate,
    automated_vs_human_reliability,
    human_selection_manifest,
)
from experiments.consciousness_sae_changepoint.judge_prompts import (  # noqa: E402
    HUMAN_BINARY_SAMPLE_SIZE,
    HUMAN_NATURAL_SAMPLE_SIZE,
    HUMAN_SELECTION_SEED,
)
from experiments.consciousness_sae_changepoint.protocol import (  # noqa: E402
    MODEL_ID,
    MODEL_REVISION,
    PROTOCOL_VERSION,
    STUDY_ID,
    canonical_json_bytes,
)
from experiments.consciousness_sae_changepoint.storage import (  # noqa: E402
    ARCHIVE_SCHEMA_VERSION,
    BLOCK_MANIFEST,
    RUN_MANIFEST,
    SOURCE_TENSOR_KEY,
    SOURCE_WIDTH,
    RunTransaction,
    sha256_file,
    validate_relative_path,
    verify_completed_block,
    verify_completed_run,
)
from experiments.consciousness_sae_changepoint.validate_plan import (  # noqa: E402
    validate as validate_plan,
)


LIFECYCLE_SCHEMA_VERSION = 1
STRUCTURAL_AUDIT_FILENAME = "structural_audit_receipt.json"
HUMAN_RELIABILITY_FILENAME = "human_reliability_receipt.json"
UNSEAL_FILENAME = "unseal_authorization.json"
ANALYSIS_AUTHORIZATION_FILENAME = "analysis_authorization.json"
MIN_LIFECYCLE_FREE_BYTES = 1024 * 1024
MAX_LIFECYCLE_JSON_BYTES = 32 * 1024**2
HEX64 = re.compile(r"^[0-9a-f]{64}$")
PREFIX_ID = re.compile(r"^[0-9a-f]{24}$")
ATTEMPT_BLOCK = re.compile(r"^([0-9a-f]{24})-attempt-([01])$")
HUMAN_ATTESTATION = (
    "I attest that I am a human coder and completed these labels "
    "independently, condition-blind, before adjudication."
)

COMPACT_PREFIX_FIELDS = frozenset(
    {
        "schema_version",
        "study_id",
        "prefix_id",
        "prefix_index",
        "status",
        "failure_code",
        "prefix_token_count",
        "prefix_token_ids_sha256",
        "prefix_text_sha256",
        "clean_continuation_token_count",
        "clean_continuation_token_ids_sha256",
        "clean_continuation_text_sha256",
        "clean_continuation_terminal_reason",
        "raw_record_sha256",
        "raw_record_bytes",
    }
)

SAFE_STAGE_METADATA_FIELDS = frozenset(
    {
        "prefix_id",
        "status",
        "stage",
        "attempt",
        "failure_code",
        "runtime_failure_code",
        "partial_payload_preserved",
        "main_branches",
        "realized_probes",
        "shared_cache_sha256",
        "fixed_conditions",
        "identical_token_ids",
        "input_token_ids_sha256",
    }
)

TASK_SPECS: dict[str, dict[str, Any]] = {
    NATURAL_STANCE_TASK: {
        "sample_size": HUMAN_NATURAL_SAMPLE_SIZE,
        "labels": (-1, 0, 1),
        "weighting": "quadratic",
    },
    BINARY_QUERY_TASK: {
        "sample_size": HUMAN_BINARY_SAMPLE_SIZE,
        "labels": (False, True),
        "weighting": "unweighted",
    },
}

REQUIRED_EVIDENCE_ROLES = frozenset(
    f"{task}_{role}"
    for task in TASK_SPECS
    for role in ("selection", "coder_1", "coder_2", "adjudicated", "automated")
)

ESSENTIAL_INDEX_COLUMNS = frozenset(
    {
        "study_id",
        "protocol_version",
        "plan_hash",
        "run_id",
        "block_id",
        "prefix_id",
        "stage",
        "artifact_receipt_sha256",
        "calibration_receipt_sha256",
        "acceptance_receipt_sha256",
        "row_id",
        "source_shard",
        "source_row_offset",
    }
)


class SealError(RuntimeError):
    """A lifecycle prerequisite or immutable binding failed validation."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_utc(value: Any, *, label: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise SealError(f"{label} must be a nonempty zoned timestamp")
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise SealError(f"{label} is not an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise SealError(f"{label} must include a timezone")
    return parsed.astimezone(timezone.utc)


def _sha256_json(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _embedded_receipt_sha256(receipt: Mapping[str, Any]) -> str:
    payload = dict(receipt)
    payload.pop("receipt_sha256", None)
    return _sha256_json(payload)


def _sign_receipt(receipt: Mapping[str, Any]) -> dict[str, Any]:
    payload = dict(receipt)
    payload["receipt_sha256"] = _embedded_receipt_sha256(payload)
    return payload


def _require_embedded_hash(receipt: Mapping[str, Any], *, label: str) -> str:
    observed = receipt.get("receipt_sha256")
    if not isinstance(observed, str) or not HEX64.fullmatch(observed):
        raise SealError(f"{label} lacks a valid receipt_sha256")
    if observed != _embedded_receipt_sha256(receipt):
        raise SealError(f"{label} embedded hash differs")
    return observed


def _require_exact_fields(
    value: Mapping[str, Any], expected: Iterable[str], *, label: str
) -> None:
    if not isinstance(value, Mapping):
        raise SealError(f"{label} must be an object")
    expected_set = set(expected)
    actual = set(value)
    if actual != expected_set:
        raise SealError(
            f"{label} fields differ; missing={sorted(expected_set - actual)}, "
            f"extra={sorted(actual - expected_set)}"
        )


def _read_json(path: Path, *, label: str) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise SealError(f"{label} is not a regular non-symlink file")
    if path.stat().st_size > MAX_LIFECYCLE_JSON_BYTES:
        raise SealError(f"{label} exceeds the lifecycle JSON size ceiling")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise SealError(f"{label} is not valid JSON") from exc
    if not isinstance(value, dict):
        raise SealError(f"{label} must contain one JSON object")
    return value


def _read_jsonl(path: Path, *, label: str) -> list[dict[str, Any]]:
    if path.is_symlink() or not path.is_file():
        raise SealError(f"{label} is not a regular non-symlink file")
    rows: list[dict[str, Any]] = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line:
                continue
            row = json.loads(line)
            if not isinstance(row, dict):
                raise SealError(f"{label} contains a non-object row")
            rows.append(row)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise SealError(f"{label} is not valid JSONL") from exc
    return rows


def _artifact_relative(root: Path, path: Path) -> str:
    try:
        relative = path.resolve(strict=True).relative_to(root.resolve(strict=True))
    except ValueError as exc:
        raise SealError(f"path escapes the external artifact root: {path}") from exc
    return validate_relative_path(PurePosixPath(*relative.parts))


def _artifact_root_for_sealed_run(run_dir: Path) -> Path:
    # Every lifecycle run is exactly ``<artifact-root>/<phase>/<run-id>``.
    if len(run_dir.parents) < 2:
        raise SealError("sealed run path has no artifact-root ancestor")
    return run_dir.parent.parent.resolve(strict=True)


def _sealed_json(
    receipt_path: Path,
    *,
    expected_filename: str,
    expected_phase: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    expanded = receipt_path.expanduser()
    if expanded.is_symlink():
        raise SealError("sealed receipt argument may not be a symlink")
    resolved = expanded.resolve(strict=True)
    if resolved.name != expected_filename:
        raise SealError(
            f"sealed receipt filename must be {expected_filename!r}, got {resolved.name!r}"
        )
    run_dir = resolved.parent
    verification = verify_completed_run(run_dir)
    manifest = _read_json(run_dir / RUN_MANIFEST, label="sealed run manifest")
    if manifest.get("phase") != expected_phase or manifest.get("run_id") != run_dir.name:
        raise SealError("sealed receipt container phase/run identity differs")
    payload = _read_json(resolved, label=expected_filename)
    _require_embedded_hash(payload, label=expected_filename)
    return payload, {
        **verification,
        "receipt_file_sha256": sha256_file(resolved),
        "run_dir": run_dir,
        "artifact_root": _artifact_root_for_sealed_run(run_dir),
    }


@contextmanager
def _artifact_root_environment(root: Path):
    """Temporarily bind the runner's environment-only root lookup."""

    name = paths.ARTIFACT_ROOT_ENV
    previous = os.environ.get(name)
    os.environ[name] = str(root)
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop(name, None)
        else:
            os.environ[name] = previous


def _validate_gate_bundle(
    *,
    plan_dir: Path,
    volume_id: str,
    artifact_root: Path,
    artifact_receipt_path: Path,
    calibration_receipt_path: Path,
    registration_receipt_path: Path,
    pre_prefix_freeze_receipt_path: Path,
    acceptance_receipt_path: Path,
    prefix_receipt_path: Path,
    prefix_freeze_receipt_path: Path,
) -> dict[str, Any]:
    """Re-run the executor's explicit validator registry for every phase.

    Import is intentionally lazy: this lifecycle module can validate already
    sealed receipts without importing model-facing executor code.  The CLI has
    no validator-injection option; unsupported target-blind gates therefore
    fail closed in ``run.validate_execution_gates``.
    """

    from experiments.consciousness_sae_changepoint.run import (  # noqa: PLC0415
        validate_execution_gates,
    )

    common = {
        "plan_dir": plan_dir,
        "volume_id": volume_id,
        "artifact_receipt_path": artifact_receipt_path,
        "calibration_receipt_path": calibration_receipt_path,
        "registration_receipt_path": registration_receipt_path,
        "pre_prefix_freeze_receipt_path": pre_prefix_freeze_receipt_path,
        "acceptance_receipt_path": acceptance_receipt_path,
    }
    with _artifact_root_environment(artifact_root):
        prefix = validate_execution_gates(phase="realize-prefix-bank", **common)
        stage2a = validate_execution_gates(
            phase="stage2a",
            prefix_receipt_path=prefix_receipt_path,
            prefix_freeze_receipt_path=prefix_freeze_receipt_path,
            **common,
        )
        stage2b = validate_execution_gates(
            phase="stage2b",
            prefix_receipt_path=prefix_receipt_path,
            prefix_freeze_receipt_path=prefix_freeze_receipt_path,
            **common,
        )
    identities = {
        (binding.plan_hash, binding.plan_manifest_sha256, binding.volume_id)
        for binding in (prefix, stage2a, stage2b)
    }
    if len(identities) != 1:
        raise SealError("phase gate validation returned inconsistent plan identities")
    return {"prefix": prefix, "stage2a": stage2a, "stage2b": stage2b}


def _validate_run_start(
    run_dir: Path,
    *,
    run_id: str,
    expected_binding_metadata: Mapping[str, Any],
    expected_outcome_content: str,
) -> None:
    started = _read_json(run_dir / "RUN_STARTED.json", label="run-start receipt")
    _require_exact_fields(
        started,
        {"archive_schema_version", "kind", "phase", "run_id", "metadata"},
        label="run-start receipt",
    )
    if (
        started.get("archive_schema_version") != ARCHIVE_SCHEMA_VERSION
        or started.get("kind") != "run_start"
        or started.get("phase") != "confirmatory"
        or started.get("run_id") != run_id
    ):
        raise SealError("run-start identity differs")
    expected = {
        **dict(expected_binding_metadata),
        "outcome_content": expected_outcome_content,
    }
    if started.get("metadata") != expected:
        raise SealError("run-start prospective gate bindings differ")


def _block_metadata(block: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    verification = verify_completed_block(block)
    manifest = _read_json(block / BLOCK_MANIFEST, label="block manifest")
    metadata = manifest.get("metadata")
    if not isinstance(metadata, dict):
        raise SealError("block manifest metadata is not an object")
    return metadata, verification


def _audit_prefix_run(
    *,
    root: Path,
    run_id: str,
    plan_prefix_ids: Sequence[str],
    expected_binding_metadata: Mapping[str, Any],
) -> dict[str, Any]:
    run_dir = root / "confirmatory" / run_id
    verification = verify_completed_run(run_dir)
    manifest = _read_json(run_dir / RUN_MANIFEST, label="prefix-bank run manifest")
    if manifest.get("phase") != "confirmatory" or manifest.get("run_id") != run_id:
        raise SealError("prefix-bank run identity differs")
    _validate_run_start(
        run_dir,
        run_id=run_id,
        expected_binding_metadata=expected_binding_metadata,
        expected_outcome_content="sealed_prefix_bank",
    )
    blocks_dir = run_dir / "blocks"
    blocks = sorted(path for path in blocks_dir.iterdir() if path.is_dir())
    expected_ids = set(plan_prefix_ids)
    if {path.name for path in blocks} != expected_ids:
        raise SealError("prefix-bank block IDs differ from the exact frozen plan")
    passed: set[str] = set()
    for block in blocks:
        metadata, _ = _block_metadata(block)
        compact = _read_json(block / "prefix_receipt.json", label="compact prefix receipt")
        _require_exact_fields(
            compact, COMPACT_PREFIX_FIELDS, label="compact prefix receipt"
        )
        prefix_id = block.name
        if (
            metadata.get("prefix_id") != prefix_id
            or compact.get("prefix_id") != prefix_id
            or compact.get("study_id") != STUDY_ID
            or compact.get("status") not in {"pass", "fail"}
            or metadata.get("status") != compact.get("status")
            or metadata.get("failure_code") != compact.get("failure_code")
        ):
            raise SealError(f"compact prefix status/identity differs for {prefix_id}")
        for hash_field in (
            "prefix_token_ids_sha256",
            "prefix_text_sha256",
            "clean_continuation_token_ids_sha256",
            "clean_continuation_text_sha256",
        ):
            if HEX64.fullmatch(str(compact.get(hash_field, ""))) is None:
                raise SealError(f"compact prefix hash is invalid: {hash_field}")
        raw_hash = compact.get("raw_record_sha256")
        if raw_hash is not None and HEX64.fullmatch(str(raw_hash)) is None:
            raise SealError("compact prefix raw-record hash is invalid")
        if compact["status"] == "pass":
            if not (block / "prefix.raw.json").is_file():
                raise SealError(f"passing prefix block lacks sealed raw record: {prefix_id}")
            passed.add(prefix_id)
    summary = manifest.get("metadata")
    if not isinstance(summary, dict):
        raise SealError("prefix-bank run summary is invalid")
    if (
        summary.get("successful_prefixes") != len(passed)
        or summary.get("failed_prefixes") != len(plan_prefix_ids) - len(passed)
        or summary.get("threshold_pass") is not True
    ):
        raise SealError("prefix-bank run summary differs from completed blocks")
    return {
        "relative_path": _artifact_relative(root, run_dir),
        "run_id": run_id,
        "manifest_sha256": verification["manifest_sha256"],
        "file_count": verification["file_count"],
        "payload_bytes": verification["payload_bytes"],
        "passing_prefixes": len(passed),
        "eligible_prefix_ids_sha256": _sha256_json(sorted(passed)),
        "eligible_prefix_ids": passed,
    }


def _validate_shard_receipt_shape(receipt: Mapping[str, Any], *, block: Path) -> None:
    _require_exact_fields(
        receipt,
        {
            "archive_schema_version",
            "shard_id",
            "rows",
            "width",
            "dtype",
            "tensor_key",
            "residual",
            "index",
        },
        label="source-shard receipt",
    )
    rows = receipt.get("rows")
    if (
        receipt.get("archive_schema_version") != ARCHIVE_SCHEMA_VERSION
        or not isinstance(rows, int)
        or isinstance(rows, bool)
        or rows <= 0
        or receipt.get("width") != SOURCE_WIDTH
        or receipt.get("dtype") != "bfloat16"
        or receipt.get("tensor_key") != SOURCE_TENSOR_KEY
    ):
        raise SealError("source-shard top-level contract differs")
    residual = receipt.get("residual")
    index = receipt.get("index")
    _require_exact_fields(
        residual,
        {"path", "bytes", "sha256", "shape", "dtype"},
        label="source residual receipt",
    )
    _require_exact_fields(
        index,
        {"path", "bytes", "sha256", "format", "rows", "columns"},
        label="source index receipt",
    )
    if residual.get("shape") != [rows, SOURCE_WIDTH] or residual.get("dtype") != "bfloat16":
        raise SealError("source residual shape/dtype differs")
    if index.get("format") != "parquet" or index.get("rows") != rows:
        raise SealError("source index format/row count differs")
    columns = index.get("columns")
    if not isinstance(columns, list) or not ESSENTIAL_INDEX_COLUMNS.issubset(columns):
        raise SealError("source index lacks mandatory identity columns")
    for child, label in ((residual, "source residual"), (index, "source index")):
        relative = validate_relative_path(str(child.get("path", "")))
        path = block / PurePosixPath(relative)
        if path.is_symlink() or not path.is_file():
            raise SealError(f"{label} file is missing")
        size = child.get("bytes")
        digest = child.get("sha256")
        if (
            not isinstance(size, int)
            or isinstance(size, bool)
            or size <= 0
            or not isinstance(digest, str)
            or not HEX64.fullmatch(digest)
            or path.stat().st_size != size
            or sha256_file(path) != digest
        ):
            raise SealError(f"{label} file receipt differs")


def _validate_safetensors_header(
    path: Path, *, expected_rows: int, expected_width: int
) -> None:
    """Validate tensor key/dtype/shape without opening residual values."""

    try:
        with path.open("rb") as handle:
            header_length_bytes = handle.read(8)
            if len(header_length_bytes) != 8:
                raise SealError("safetensors header length is truncated")
            header_length = int.from_bytes(header_length_bytes, "little", signed=False)
            if not 2 <= header_length <= 16 * 1024**2:
                raise SealError("safetensors header length is invalid")
            header = json.loads(handle.read(header_length).decode("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise SealError("safetensors header is invalid") from exc
    tensor_keys = set(header) - {"__metadata__"}
    if tensor_keys != {SOURCE_TENSOR_KEY}:
        raise SealError("safetensors tensor key set differs")
    tensor = header[SOURCE_TENSOR_KEY]
    if not isinstance(tensor, dict):
        raise SealError("safetensors tensor header is not an object")
    if tensor.get("dtype") != "BF16" or tensor.get("shape") != [
        expected_rows,
        expected_width,
    ]:
        raise SealError("safetensors dtype/shape differs from the shard receipt")
    expected_payload_bytes = expected_rows * expected_width * 2
    if tensor.get("data_offsets") != [0, expected_payload_bytes]:
        raise SealError("safetensors data offsets differ from the BF16 shape")
    if path.stat().st_size != 8 + header_length + expected_payload_bytes:
        raise SealError("safetensors file length differs from header plus tensor payload")


def _validate_parquet_lineage(
    *,
    index_path: Path,
    rows: int,
    source_shard: str,
    bindings: Mapping[str, str],
    expected_columns: Sequence[str],
    seen_row_ids: set[str],
) -> None:
    """Stream identity columns only; residual values and outcomes stay unopened."""

    try:
        import pyarrow.parquet as pq
    except ImportError as exc:  # pragma: no cover - production runtime dependency
        raise SealError("pyarrow is required for structural shard lineage audit") from exc

    parquet = pq.ParquetFile(index_path)
    if parquet.metadata.num_rows != rows:
        raise SealError("Parquet metadata row count differs from shard receipt")
    if parquet.schema.names != list(expected_columns):
        raise SealError("Parquet schema columns differ from the shard receipt")
    if not ESSENTIAL_INDEX_COLUMNS.issubset(parquet.schema.names):
        raise SealError("Parquet schema lacks mandatory identity columns")
    next_offset = 0
    columns = sorted(ESSENTIAL_INDEX_COLUMNS)
    for batch in parquet.iter_batches(columns=columns, batch_size=65_536):
        values = batch.to_pydict()
        batch_rows = batch.num_rows
        offsets = values["source_row_offset"]
        if offsets != list(range(next_offset, next_offset + batch_rows)):
            raise SealError("Parquet source-row offsets are not exact and contiguous")
        next_offset += batch_rows
        if any(value != source_shard for value in values["source_shard"]):
            raise SealError("Parquet source-shard path binding differs")
        for field, expected in bindings.items():
            if any(value != expected for value in values[field]):
                raise SealError(f"Parquet lineage field differs: {field}")
        for row_id in values["row_id"]:
            if not isinstance(row_id, str) or not row_id or row_id in seen_row_ids:
                raise SealError("Parquet row_id is empty or duplicated within a block")
            seen_row_ids.add(row_id)
    if next_offset != rows:
        raise SealError("Parquet streamed row count differs")


def _validate_source_shards(
    *,
    block: Path,
    plan_hash: str,
    run_id: str,
    block_id: str,
    prefix_id: str,
    stage: str,
    artifact_receipt_sha256: str,
    calibration_receipt_sha256: str,
    acceptance_receipt_sha256: str,
) -> int:
    # Runner writes a JSON list, while the strict helper above reads objects.
    # Read this one file directly and keep the exception content-free.
    inventory_path = block / "source_shard_receipts.json"
    if inventory_path.is_symlink() or not inventory_path.is_file():
        raise SealError("source-shard receipt inventory is missing")
    if inventory_path.stat().st_size > MAX_LIFECYCLE_JSON_BYTES:
        raise SealError("source-shard receipt inventory exceeds the JSON ceiling")
    try:
        receipts = json.loads(
            inventory_path.read_text(encoding="utf-8")
        )
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise SealError("source-shard receipt inventory is invalid JSON") from exc
    if not isinstance(receipts, list) or not receipts:
        raise SealError("passing block has no source-shard receipts")
    total_rows = 0
    residual_paths: set[str] = set()
    index_paths: set[str] = set()
    receipt_paths: set[str] = set()
    seen_row_ids: set[str] = set()
    for raw in receipts:
        if not isinstance(raw, dict):
            raise SealError("source-shard inventory contains a non-object")
        _validate_shard_receipt_shape(raw, block=block)
        residual = raw["residual"]
        index = raw["index"]
        residual_path = validate_relative_path(residual["path"])
        index_path = validate_relative_path(index["path"])
        shard_id = raw["shard_id"]
        receipt_relative = validate_relative_path(
            f"receipts/{shard_id}-{residual['sha256'][:16]}.receipt.json"
        )
        receipt_path = block / PurePosixPath(receipt_relative)
        if _read_json(receipt_path, label="individual source-shard receipt") != raw:
            raise SealError("individual and inventory source-shard receipts differ")
        if (
            residual_path in residual_paths
            or index_path in index_paths
            or receipt_relative in receipt_paths
        ):
            raise SealError("source-shard paths are duplicated")
        residual_paths.add(residual_path)
        index_paths.add(index_path)
        receipt_paths.add(receipt_relative)
        _validate_safetensors_header(
            block / PurePosixPath(residual_path),
            expected_rows=int(raw["rows"]),
            expected_width=SOURCE_WIDTH,
        )
        _validate_parquet_lineage(
            index_path=block / PurePosixPath(index_path),
            rows=int(raw["rows"]),
            source_shard=residual_path,
            expected_columns=raw["index"]["columns"],
            seen_row_ids=seen_row_ids,
            bindings={
                "study_id": STUDY_ID,
                "protocol_version": PROTOCOL_VERSION,
                "plan_hash": plan_hash,
                "run_id": run_id,
                "block_id": block_id,
                "prefix_id": prefix_id,
                "stage": stage,
                "artifact_receipt_sha256": artifact_receipt_sha256,
                "calibration_receipt_sha256": calibration_receipt_sha256,
                "acceptance_receipt_sha256": acceptance_receipt_sha256,
            },
        )
        total_rows += int(raw["rows"])
    actual_residuals = {
        _artifact_relative(block, path)
        for path in block.rglob("*.safetensors")
        if path.is_file()
    }
    actual_indexes = {
        _artifact_relative(block, path)
        for path in block.rglob("*.parquet")
        if path.is_file()
    }
    actual_receipts = {
        _artifact_relative(block, path)
        for path in (block / "receipts").glob("*.receipt.json")
        if path.is_file()
    }
    if (
        actual_residuals != residual_paths
        or actual_indexes != index_paths
        or actual_receipts != receipt_paths
    ):
        raise SealError("source-shard file set differs from the exact receipt inventory")
    return total_rows


def _attempts_by_prefix(
    *, blocks: Sequence[Path], plan_prefix_ids: Sequence[str], stage: str
) -> dict[str, list[tuple[int, Path, dict[str, Any]]]]:
    by_prefix: dict[str, list[tuple[int, Path, dict[str, Any]]]] = {
        prefix_id: [] for prefix_id in plan_prefix_ids
    }
    for block in blocks:
        match = ATTEMPT_BLOCK.fullmatch(block.name)
        if match is None or match.group(1) not in by_prefix:
            raise SealError(f"{stage} block ID is not in the frozen plan: {block.name}")
        prefix_id, attempt_text = match.groups()
        attempt = int(attempt_text)
        metadata, _ = _block_metadata(block)
        if not set(metadata).issubset(SAFE_STAGE_METADATA_FIELDS):
            raise SealError(f"{stage} block metadata contains non-structural fields")
        if (
            metadata.get("prefix_id") != prefix_id
            or metadata.get("stage") != stage
            or metadata.get("attempt") != attempt
            or metadata.get("status") not in {"pass", "fail"}
        ):
            raise SealError(f"{stage} block metadata differs for {block.name}")
        by_prefix[prefix_id].append((attempt, block, metadata))
    for prefix_id, attempts in by_prefix.items():
        attempts.sort(key=lambda row: row[0])
        attempt_ids = [row[0] for row in attempts]
        if attempt_ids not in ([], [0], [0, 1]):
            raise SealError(f"{stage} whole-block retry sequence differs for {prefix_id}")
        if len(attempts) == 2 and attempts[0][2]["status"] != "fail":
            raise SealError(f"{stage} retried a passing whole block: {prefix_id}")
        if sum(row[2]["status"] == "pass" for row in attempts) > 1:
            raise SealError(f"{stage} has multiple passing attempts: {prefix_id}")
    return by_prefix


def _audit_stage_run(
    *,
    root: Path,
    run_id: str,
    stage: str,
    plan_prefix_ids: Sequence[str],
    expected_binding_metadata: Mapping[str, Any],
) -> dict[str, Any]:
    run_dir = root / "confirmatory" / run_id
    verification = verify_completed_run(run_dir)
    manifest = _read_json(run_dir / RUN_MANIFEST, label=f"{stage} run manifest")
    if manifest.get("phase") != "confirmatory" or manifest.get("run_id") != run_id:
        raise SealError(f"{stage} run identity differs")
    _validate_run_start(
        run_dir,
        run_id=run_id,
        expected_binding_metadata=expected_binding_metadata,
        expected_outcome_content="sealed_target_results",
    )
    blocks_dir = run_dir / "blocks"
    blocks = (
        sorted(path for path in blocks_dir.iterdir() if path.is_dir())
        if blocks_dir.is_dir()
        else []
    )
    attempts = _attempts_by_prefix(
        blocks=blocks, plan_prefix_ids=plan_prefix_ids, stage=stage
    )
    passed: set[str] = set()
    source_rows = 0
    required_json = (
        {
            "main_branches.raw.json",
            "probes.raw.json",
            "actual_selected_readouts.json",
            "jlens_selected_readouts.json",
            "source_shard_receipts.json",
        }
        if stage == "stage2a"
        else {
            "fixed_conditions.json",
            "actual_selected_readouts.json",
            "jlens_selected_readouts.json",
            "source_shard_receipts.json",
        }
    )
    for prefix_id, rows in attempts.items():
        pass_rows = [row for row in rows if row[2]["status"] == "pass"]
        if not pass_rows:
            continue
        attempt, block, metadata = pass_rows[0]
        del attempt
        expected_pass_fields = (
            {
                "prefix_id",
                "status",
                "stage",
                "main_branches",
                "realized_probes",
                "shared_cache_sha256",
                "attempt",
            }
            if stage == "stage2a"
            else {
                "prefix_id",
                "status",
                "stage",
                "fixed_conditions",
                "identical_token_ids",
                "input_token_ids_sha256",
                "attempt",
            }
        )
        if set(metadata) != expected_pass_fields:
            raise SealError(f"passing {stage} block metadata fields differ")
        missing = sorted(name for name in required_json if not (block / name).is_file())
        if missing:
            raise SealError(f"passing {stage} block lacks required files: {missing}")
        source_rows += _validate_source_shards(
            block=block,
            plan_hash=str(expected_binding_metadata["plan_hash"]),
            run_id=run_id,
            block_id=block.name,
            prefix_id=prefix_id,
            stage=stage,
            artifact_receipt_sha256=str(
                expected_binding_metadata["artifact_receipt_sha256"]
            ),
            calibration_receipt_sha256=str(
                expected_binding_metadata["calibration_receipt_sha256"]
            ),
            acceptance_receipt_sha256=str(
                expected_binding_metadata["acceptance_receipt_sha256"]
            ),
        )
        passed.add(prefix_id)
    summary = manifest.get("metadata")
    if not isinstance(summary, dict):
        raise SealError(f"{stage} run summary is invalid")
    if (
        summary.get("stage") != stage
        or summary.get("complete_prefix_blocks") != len(passed)
        or summary.get("missing_prefix_blocks") != len(plan_prefix_ids) - len(passed)
        or summary.get("threshold_pass") is not True
        or summary.get("whole_block_max_attempts") != 2
    ):
        raise SealError(f"{stage} run summary differs from completed blocks")
    return {
        "relative_path": _artifact_relative(root, run_dir),
        "run_id": run_id,
        "manifest_sha256": verification["manifest_sha256"],
        "file_count": verification["file_count"],
        "payload_bytes": verification["payload_bytes"],
        "passing_prefixes": len(passed),
        "source_rows": source_rows,
        "eligible_prefix_ids_sha256": _sha256_json(sorted(passed)),
        "eligible_prefix_ids": passed,
        "attempted_prefix_ids": {
            prefix_id for prefix_id, rows in attempts.items() if rows
        },
    }


def create_structural_audit(
    *,
    plan_dir: Path,
    volume_id: str,
    artifact_root: Path,
    artifact_receipt_path: Path,
    calibration_receipt_path: Path,
    registration_receipt_path: Path,
    pre_prefix_freeze_receipt_path: Path,
    acceptance_receipt_path: Path,
    prefix_receipt_path: Path,
    prefix_freeze_receipt_path: Path,
    prefix_bank_run_id: str,
    stage2a_run_id: str,
    stage2b_run_id: str,
    run_id: str,
) -> dict[str, Any]:
    """Validate structure without opening semantic outcomes and seal the audit."""

    root = paths.require_external_artifact_root(
        artifact_root,
        minimum_free_bytes=MIN_LIFECYCLE_FREE_BYTES,
        minimum_logical_reserve_bytes=MIN_LIFECYCLE_FREE_BYTES,
        expected_volume_id=volume_id,
        write_read_probe=False,
    )
    resolved_plan = plan_dir.expanduser().resolve(strict=True)
    plan_validation = validate_plan(
        resolved_plan, expected_volume_id=volume_id, repo_root=REPO_ROOT
    )
    if plan_validation.get("status") != "pass":
        raise SealError("exact machine-plan validation failed")
    if plan_validation.get("plan_status") != "freeze_candidate_result_free_machine_plan":
        raise SealError("machine plan is not a frozen result-free candidate")
    plan_rows = _read_jsonl(
        resolved_plan / "prefix_plan.jsonl", label="frozen prefix plan"
    )
    plan_prefix_ids = [str(row.get("prefix_id", "")) for row in plan_rows]
    if (
        not plan_prefix_ids
        or len(plan_prefix_ids) != len(set(plan_prefix_ids))
        or any(PREFIX_ID.fullmatch(value) is None for value in plan_prefix_ids)
    ):
        raise SealError("frozen prefix IDs are invalid or duplicated")
    snapshot = _read_json(
        resolved_plan / "protocol_snapshot.json", label="protocol snapshot"
    )
    minimum_common = snapshot.get("design", {}).get("minimum_complete_prefix_blocks")
    if (
        not isinstance(minimum_common, int)
        or isinstance(minimum_common, bool)
        or not 1 <= minimum_common <= len(plan_prefix_ids)
    ):
        raise SealError("frozen common-completion threshold is invalid")

    bindings = _validate_gate_bundle(
        plan_dir=resolved_plan,
        volume_id=volume_id,
        artifact_root=root,
        artifact_receipt_path=artifact_receipt_path,
        calibration_receipt_path=calibration_receipt_path,
        registration_receipt_path=registration_receipt_path,
        pre_prefix_freeze_receipt_path=pre_prefix_freeze_receipt_path,
        acceptance_receipt_path=acceptance_receipt_path,
        prefix_receipt_path=prefix_receipt_path,
        prefix_freeze_receipt_path=prefix_freeze_receipt_path,
    )
    prefix = _audit_prefix_run(
        root=root,
        run_id=prefix_bank_run_id,
        plan_prefix_ids=plan_prefix_ids,
        expected_binding_metadata=bindings["prefix"].as_metadata(),
    )
    if (
        bindings["stage2a"].prefix_bank_run_id != prefix_bank_run_id
        or bindings["stage2b"].prefix_bank_run_id != prefix_bank_run_id
        or bindings["stage2a"].prefix_bank_manifest_sha256
        != prefix["manifest_sha256"]
        or bindings["stage2b"].prefix_bank_manifest_sha256
        != prefix["manifest_sha256"]
    ):
        raise SealError("target-phase gate bindings do not name the audited prefix bank")
    stage2a = _audit_stage_run(
        root=root,
        run_id=stage2a_run_id,
        stage="stage2a",
        plan_prefix_ids=plan_prefix_ids,
        expected_binding_metadata=bindings["stage2a"].as_metadata(),
    )
    stage2b = _audit_stage_run(
        root=root,
        run_id=stage2b_run_id,
        stage="stage2b",
        plan_prefix_ids=plan_prefix_ids,
        expected_binding_metadata=bindings["stage2b"].as_metadata(),
    )
    prefix_eligible = set(prefix.pop("eligible_prefix_ids"))
    stage2a_eligible = set(stage2a.pop("eligible_prefix_ids"))
    stage2b_eligible = set(stage2b.pop("eligible_prefix_ids"))
    stage2a_attempted = set(stage2a.pop("attempted_prefix_ids"))
    stage2b_attempted = set(stage2b.pop("attempted_prefix_ids"))
    if not stage2a_attempted.issubset(prefix_eligible) or not stage2b_attempted.issubset(
        prefix_eligible
    ):
        raise SealError("a target phase attempted a prefix that failed prefix realization")
    common = sorted(prefix_eligible & stage2a_eligible & stage2b_eligible)
    if len(common) < minimum_common:
        raise SealError(
            "common complete prefix set fails the frozen threshold: "
            f"required={minimum_common}, observed={len(common)}"
        )

    plan_manifest_sha256 = sha256_file(resolved_plan / "PLAN_MANIFEST.json")
    binding_metadata = bindings["stage2a"].as_metadata()
    gate_bindings = {
        key: binding_metadata[key]
        for key in (
            "registration_id",
            "registration_receipt_sha256",
            "pre_prefix_freeze_sha",
            "pre_prefix_freeze_receipt_sha256",
            "artifact_receipt_sha256",
            "calibration_receipt_sha256",
            "acceptance_receipt_sha256",
            "vector_inventory_sha256",
            "prefix_receipt_sha256",
            "prefix_bank_manifest_sha256",
            "prefix_bank_run_id",
            "prefix_freeze_sha",
            "prefix_freeze_receipt_sha256",
        )
    }
    receipt = _sign_receipt(
        {
            "schema_version": LIFECYCLE_SCHEMA_VERSION,
            "receipt_kind": "structural_audit",
            "status": "pass",
            "study_id": STUDY_ID,
            "protocol_version": PROTOCOL_VERSION,
            "created_at_utc": _utc_now(),
            "structural_only": True,
            "semantic_outcomes_opened": False,
            "plan": {
                "plan_hash": str(plan_validation["plan_hash"]),
                "plan_manifest_sha256": plan_manifest_sha256,
                "volume_id": volume_id,
                "planned_prefixes": len(plan_prefix_ids),
                "prefix_ids_sha256": _sha256_json(sorted(plan_prefix_ids)),
                "minimum_common_complete_prefixes": minimum_common,
            },
            "gate_bindings": gate_bindings,
            "runs": {
                "prefix_bank": prefix,
                "stage2a": stage2a,
                "stage2b": stage2b,
            },
            "common_eligible": {
                "count": len(common),
                "minimum_required": minimum_common,
                "prefix_ids": common,
                "prefix_ids_sha256": _sha256_json(common),
            },
        }
    )
    transaction = RunTransaction.start(
        phase="audit",
        run_id=run_id,
        artifact_root=root,
        expected_volume_id=volume_id,
        minimum_free_bytes=MIN_LIFECYCLE_FREE_BYTES,
        metadata={
            "study_id": STUDY_ID,
            "plan_hash": receipt["plan"]["plan_hash"],
            "structural_only": True,
        },
    )
    transaction.write_json(STRUCTURAL_AUDIT_FILENAME, receipt)
    final = transaction.complete(
        metadata={
            "status": "pass",
            "plan_hash": receipt["plan"]["plan_hash"],
            "common_eligible_prefixes": len(common),
            "semantic_outcomes_opened": False,
        }
    )
    verification = verify_completed_run(final)
    return {
        "status": "pass",
        "run_id": run_id,
        "receipt_sha256": receipt["receipt_sha256"],
        "manifest_sha256": verification["manifest_sha256"],
        "common_eligible_prefixes": len(common),
    }


def _validate_structural_audit_receipt(receipt: Mapping[str, Any]) -> None:
    _require_exact_fields(
        receipt,
        {
            "schema_version",
            "receipt_kind",
            "status",
            "study_id",
            "protocol_version",
            "created_at_utc",
            "structural_only",
            "semantic_outcomes_opened",
            "plan",
            "gate_bindings",
            "runs",
            "common_eligible",
            "receipt_sha256",
        },
        label="structural audit receipt",
    )
    if (
        receipt.get("schema_version") != LIFECYCLE_SCHEMA_VERSION
        or receipt.get("receipt_kind") != "structural_audit"
        or receipt.get("status") != "pass"
        or receipt.get("study_id") != STUDY_ID
        or receipt.get("protocol_version") != PROTOCOL_VERSION
        or receipt.get("structural_only") is not True
        or receipt.get("semantic_outcomes_opened") is not False
    ):
        raise SealError("structural audit identity/blinding contract differs")
    _parse_utc(receipt.get("created_at_utc"), label="structural audit timestamp")
    _require_embedded_hash(receipt, label="structural audit receipt")
    plan = receipt.get("plan")
    _require_exact_fields(
        plan,
        {
            "plan_hash",
            "plan_manifest_sha256",
            "volume_id",
            "planned_prefixes",
            "prefix_ids_sha256",
            "minimum_common_complete_prefixes",
        },
        label="structural audit plan binding",
    )
    for field in ("plan_hash", "plan_manifest_sha256", "prefix_ids_sha256"):
        if not isinstance(plan[field], str) or not HEX64.fullmatch(plan[field]):
            raise SealError(f"structural audit plan hash is invalid: {field}")
    runs = receipt.get("runs")
    if not isinstance(runs, dict) or set(runs) != {"prefix_bank", "stage2a", "stage2b"}:
        raise SealError("structural audit run set differs")
    for role, entry in runs.items():
        expected = {
            "relative_path",
            "run_id",
            "manifest_sha256",
            "file_count",
            "payload_bytes",
            "passing_prefixes",
            "eligible_prefix_ids_sha256",
        }
        if role != "prefix_bank":
            expected.add("source_rows")
        _require_exact_fields(entry, expected, label=f"{role} audit run binding")
        validate_relative_path(entry["relative_path"])
        if not HEX64.fullmatch(str(entry.get("manifest_sha256", ""))) or not HEX64.fullmatch(
            str(entry.get("eligible_prefix_ids_sha256", ""))
        ):
            raise SealError(f"{role} audit hashes are invalid")
        for field in ("file_count", "payload_bytes", "passing_prefixes"):
            if (
                not isinstance(entry.get(field), int)
                or isinstance(entry.get(field), bool)
                or entry[field] < 0
            ):
                raise SealError(f"{role} audit count is invalid: {field}")
        if role != "prefix_bank" and (
            not isinstance(entry.get("source_rows"), int)
            or isinstance(entry.get("source_rows"), bool)
            or entry["source_rows"] <= 0
        ):
            raise SealError(f"{role} source-row count is invalid")
    gate_bindings = receipt.get("gate_bindings")
    expected_gate_fields = {
        "registration_id",
        "registration_receipt_sha256",
        "pre_prefix_freeze_sha",
        "pre_prefix_freeze_receipt_sha256",
        "artifact_receipt_sha256",
        "calibration_receipt_sha256",
        "acceptance_receipt_sha256",
        "vector_inventory_sha256",
        "prefix_receipt_sha256",
        "prefix_bank_manifest_sha256",
        "prefix_bank_run_id",
        "prefix_freeze_sha",
        "prefix_freeze_receipt_sha256",
    }
    _require_exact_fields(
        gate_bindings, expected_gate_fields, label="structural audit gate bindings"
    )
    for field in expected_gate_fields:
        value = gate_bindings[field]
        if field in {"registration_id", "prefix_bank_run_id"}:
            if not isinstance(value, str) or not value:
                raise SealError(f"structural gate identity is invalid: {field}")
        elif field == "pre_prefix_freeze_sha" or field == "prefix_freeze_sha":
            if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{40}(?:[0-9a-f]{24})?", value) is None:
                raise SealError(f"structural gate commit hash is invalid: {field}")
        elif not isinstance(value, str) or HEX64.fullmatch(value) is None:
            raise SealError(f"structural gate receipt hash is invalid: {field}")
    if (
        gate_bindings["prefix_bank_run_id"] != runs["prefix_bank"]["run_id"]
        or gate_bindings["prefix_bank_manifest_sha256"]
        != runs["prefix_bank"]["manifest_sha256"]
    ):
        raise SealError("structural gate binding names a different prefix bank")
    common = receipt.get("common_eligible")
    _require_exact_fields(
        common,
        {"count", "minimum_required", "prefix_ids", "prefix_ids_sha256"},
        label="common eligible binding",
    )
    ids = common.get("prefix_ids")
    if (
        not isinstance(ids, list)
        or ids != sorted(ids)
        or len(ids) != len(set(ids))
        or any(PREFIX_ID.fullmatch(str(value)) is None for value in ids)
        or common.get("count") != len(ids)
        or common.get("prefix_ids_sha256") != _sha256_json(ids)
        or not isinstance(common.get("minimum_required"), int)
        or len(ids) < common["minimum_required"]
        or plan.get("minimum_common_complete_prefixes") != common["minimum_required"]
    ):
        raise SealError("common eligible prefix set/hash/threshold differs")


def _verify_audit_current_runs(receipt: Mapping[str, Any], *, root: Path) -> None:
    for role, entry in receipt["runs"].items():
        relative = validate_relative_path(entry["relative_path"])
        run_dir = (root / PurePosixPath(relative)).resolve(strict=True)
        try:
            run_dir.relative_to(root)
        except ValueError as exc:
            raise SealError(f"{role} run escapes the artifact root") from exc
        verification = verify_completed_run(run_dir)
        if verification["manifest_sha256"] != entry["manifest_sha256"]:
            raise SealError(f"{role} run manifest changed after structural audit")


def _evidence_records(
    receipt: Mapping[str, Any], *, human_run_dir: Path
) -> dict[str, tuple[Path, dict[str, Any], str]]:
    records = receipt.get("evidence_files")
    if not isinstance(records, list) or len(records) != len(REQUIRED_EVIDENCE_ROLES):
        raise SealError("human evidence inventory count differs")
    by_role: dict[str, tuple[Path, dict[str, Any], str]] = {}
    for record in records:
        _require_exact_fields(
            record, {"role", "path", "bytes", "sha256"}, label="human evidence record"
        )
        role = record.get("role")
        if role not in REQUIRED_EVIDENCE_ROLES or role in by_role:
            raise SealError("human evidence role is unsupported or duplicated")
        relative = validate_relative_path(str(record.get("path", "")))
        path = (human_run_dir / PurePosixPath(relative)).resolve(strict=True)
        try:
            path.relative_to(human_run_dir)
        except ValueError as exc:
            raise SealError("human evidence path escapes its sealed run") from exc
        if path.name == HUMAN_RELIABILITY_FILENAME or path.is_symlink() or not path.is_file():
            raise SealError("human evidence path is invalid")
        if (
            path.stat().st_size != record.get("bytes")
            or sha256_file(path) != record.get("sha256")
        ):
            raise SealError("human evidence byte/hash receipt differs")
        by_role[str(role)] = (
            path,
            _read_json(path, label=f"human evidence {role}"),
            str(record["sha256"]),
        )
    if set(by_role) != REQUIRED_EVIDENCE_ROLES:
        raise SealError("human evidence role set differs")
    return by_role


def _label_rows(
    payload: Mapping[str, Any],
    *,
    task: str,
    selected_ids: Sequence[str],
    allow_missing: bool,
) -> list[Any]:
    rows = payload.get("rows")
    if not isinstance(rows, list) or len(rows) != len(selected_ids):
        raise SealError(f"{task} label row count differs")
    by_id: dict[str, Any] = {}
    allowed = set(TASK_SPECS[task]["labels"])
    for row in rows:
        _require_exact_fields(row, {"packet_id", "label"}, label=f"{task} label row")
        packet_id = row.get("packet_id")
        label = row.get("label")
        if not isinstance(packet_id, str) or not packet_id or packet_id in by_id:
            raise SealError(f"{task} packet IDs are empty or duplicated")
        if label is None and allow_missing:
            pass
        elif task == BINARY_QUERY_TASK:
            if type(label) is not bool:
                raise SealError("binary-query labels must be JSON booleans or null")
        elif type(label) is not int or label not in allowed:
            raise SealError("natural-stance labels must be exactly -1/0/+1")
        by_id[packet_id] = label
    if set(by_id) != set(selected_ids):
        raise SealError(f"{task} label packet set differs from frozen selection")
    return [by_id[packet_id] for packet_id in selected_ids]


def _recompute_human_task(
    *,
    task: str,
    evidence: Mapping[str, tuple[Path, dict[str, Any], str]],
) -> tuple[dict[str, Any], tuple[str, str], datetime]:
    spec = TASK_SPECS[task]
    selection_path, selection, selection_file_hash = evidence[f"{task}_selection"]
    del selection_path
    _require_exact_fields(
        selection,
        {
            "study_id",
            "selection_method",
            "seed",
            "strata_fields",
            "n_selected",
            "selected_ids",
            "selection_sha256",
        },
        label=f"{task} human selection manifest",
    )
    selected_ids = selection.get("selected_ids")
    if (
        selection.get("study_id") != STUDY_ID
        or selection.get("seed") != str(HUMAN_SELECTION_SEED)
        or selection.get("strata_fields") != ["branch", "position"]
        or selection.get("n_selected") != spec["sample_size"]
        or not isinstance(selected_ids, list)
        or len(selected_ids) != spec["sample_size"]
        or len(selected_ids) != len(set(selected_ids))
    ):
        raise SealError(f"{task} frozen human selection differs")
    expected_selection = human_selection_manifest(
        selected_ids,
        seed=HUMAN_SELECTION_SEED,
        strata_fields=("branch", "position"),
    )
    if selection != expected_selection:
        raise SealError(f"{task} selection hash/reconstruction differs")

    coder_payloads: list[dict[str, Any]] = []
    coder_hashes: list[str] = []
    coder_ids: list[str] = []
    coder_times: list[datetime] = []
    coder_labels: list[list[Any]] = []
    coder_fields = {
        "schema_version",
        "study_id",
        "task",
        "coder_id_sha256",
        "condition_blind",
        "coded_independently",
        "human_attestation",
        "completed_at_utc",
        "rows",
    }
    for number in (1, 2):
        _path, payload, file_hash = evidence[f"{task}_coder_{number}"]
        _require_exact_fields(payload, coder_fields, label=f"{task} coder-{number} labels")
        coder_id = payload.get("coder_id_sha256")
        if (
            payload.get("schema_version") != LIFECYCLE_SCHEMA_VERSION
            or payload.get("study_id") != STUDY_ID
            or payload.get("task") != task
            or not isinstance(coder_id, str)
            or not HEX64.fullmatch(coder_id)
            or payload.get("condition_blind") is not True
            or payload.get("coded_independently") is not True
            or payload.get("human_attestation") != HUMAN_ATTESTATION
        ):
            raise SealError(f"{task} coder-{number} independence attestation differs")
        coder_payloads.append(payload)
        coder_hashes.append(file_hash)
        coder_ids.append(coder_id)
        coder_times.append(
            _parse_utc(payload.get("completed_at_utc"), label=f"{task} coder timestamp")
        )
        coder_labels.append(
            _label_rows(
                payload, task=task, selected_ids=selected_ids, allow_missing=False
            )
        )
    del coder_payloads
    if len(set(coder_ids)) != 2 or len(set(coder_hashes)) != 2:
        raise SealError(f"{task} does not contain two distinct independent coders")

    _path, adjudicated, adjudicated_hash = evidence[f"{task}_adjudicated"]
    _require_exact_fields(
        adjudicated,
        {
            "schema_version",
            "study_id",
            "task",
            "adjudicator_id_sha256",
            "condition_blind",
            "adjudication_required",
            "independent_coder_file_sha256",
            "disagreements_preserved",
            "completed_at_utc",
            "rows",
        },
        label=f"{task} adjudicated labels",
    )
    adjudicator = adjudicated.get("adjudicator_id_sha256")
    adjudicated_time = _parse_utc(
        adjudicated.get("completed_at_utc"), label=f"{task} adjudication timestamp"
    )
    if (
        adjudicated.get("schema_version") != LIFECYCLE_SCHEMA_VERSION
        or adjudicated.get("study_id") != STUDY_ID
        or adjudicated.get("task") != task
        or not isinstance(adjudicator, str)
        or not HEX64.fullmatch(adjudicator)
        or adjudicated.get("condition_blind") is not True
        or adjudicated.get("adjudication_required") is not True
        or adjudicated.get("independent_coder_file_sha256") != coder_hashes
        or adjudicated.get("disagreements_preserved") is not True
        or any(timestamp > adjudicated_time for timestamp in coder_times)
    ):
        raise SealError(f"{task} adjudication provenance/order differs")
    adjudicated_labels = _label_rows(
        adjudicated, task=task, selected_ids=selected_ids, allow_missing=False
    )

    _path, automated, automated_hash = evidence[f"{task}_automated"]
    _require_exact_fields(
        automated,
        {
            "schema_version",
            "study_id",
            "task",
            "model_id",
            "model_revision",
            "temperature",
            "rows",
        },
        label=f"{task} automated labels",
    )
    if (
        automated.get("schema_version") != LIFECYCLE_SCHEMA_VERSION
        or automated.get("study_id") != STUDY_ID
        or automated.get("task") != task
        or automated.get("model_id") != MODEL_ID
        or automated.get("model_revision") != MODEL_REVISION
        or automated.get("temperature") != 0.0
    ):
        raise SealError(f"{task} automated judge pin differs")
    automated_labels = _label_rows(
        automated, task=task, selected_ids=selected_ids, allow_missing=True
    )
    metrics = automated_vs_human_reliability(
        adjudicated_labels,
        automated_labels,
        labels=spec["labels"],
        weighting=spec["weighting"],
    )
    gate = assess_reliability_gate(metrics)
    if gate.get("status") != "pass" or gate.get("passed") is not True:
        raise SealError(f"{task} frozen reliability threshold failed")
    disagreements = sum(
        first != second for first, second in zip(coder_labels[0], coder_labels[1])
    )
    summary = {
        "rubric_version": RUBRIC_BY_TASK[task],
        "sample_size": spec["sample_size"],
        "selection_file_sha256": selection_file_hash,
        "selection_sha256": selection["selection_sha256"],
        "coder_ids_sha256": coder_ids,
        "coder_label_file_sha256": coder_hashes,
        "adjudicated_label_file_sha256": adjudicated_hash,
        "automated_label_file_sha256": automated_hash,
        "disagreement_count": disagreements,
        "metrics": metrics,
        "gate": gate,
    }
    return summary, (coder_ids[0], coder_ids[1]), adjudicated_time


def validate_human_reliability_receipt(
    receipt: Mapping[str, Any], *, human_run_dir: Path
) -> dict[str, Any]:
    """Recompute both endpoint gates from sealed external row-level evidence."""

    _require_exact_fields(
        receipt,
        {
            "schema_version",
            "receipt_kind",
            "status",
            "study_id",
            "protocol_version",
            "created_at_utc",
            "plan_hash",
            "audit_receipt_file_sha256",
            "audit_receipt_embedded_sha256",
            "audit_run_manifest_sha256",
            "human_coders_required",
            "condition_blind",
            "adjudication_required",
            "evidence_files",
            "tasks",
            "receipt_sha256",
        },
        label="human reliability receipt",
    )
    if (
        receipt.get("schema_version") != LIFECYCLE_SCHEMA_VERSION
        or receipt.get("receipt_kind") != "human_reliability"
        or receipt.get("status") != "pass"
        or receipt.get("study_id") != STUDY_ID
        or receipt.get("protocol_version") != PROTOCOL_VERSION
        or receipt.get("human_coders_required") != 2
        or receipt.get("condition_blind") is not True
        or receipt.get("adjudication_required") is not True
    ):
        raise SealError("human reliability top-level contract differs")
    created = _parse_utc(receipt.get("created_at_utc"), label="human receipt timestamp")
    for field in (
        "plan_hash",
        "audit_receipt_file_sha256",
        "audit_receipt_embedded_sha256",
        "audit_run_manifest_sha256",
    ):
        if not isinstance(receipt.get(field), str) or not HEX64.fullmatch(receipt[field]):
            raise SealError(f"human reliability hash is invalid: {field}")
    _require_embedded_hash(receipt, label="human reliability receipt")
    evidence = _evidence_records(receipt, human_run_dir=human_run_dir)
    computed_tasks: dict[str, Any] = {}
    coder_pairs: list[tuple[str, str]] = []
    adjudicated_times: list[datetime] = []
    for task in TASK_SPECS:
        summary, coder_pair, adjudicated_time = _recompute_human_task(
            task=task, evidence=evidence
        )
        computed_tasks[task] = summary
        coder_pairs.append(coder_pair)
        adjudicated_times.append(adjudicated_time)
    if coder_pairs[0] != coder_pairs[1]:
        raise SealError("the same two independent coders must cover both primary rubrics")
    if any(timestamp > created for timestamp in adjudicated_times):
        raise SealError("human reliability receipt predates adjudication")
    if receipt.get("tasks") != computed_tasks:
        raise SealError("human reliability summary differs from sealed row evidence")
    return {"tasks": computed_tasks, "coder_ids_sha256": list(coder_pairs[0])}


def create_unseal_authorization(
    *,
    structural_audit_receipt_path: Path,
    human_reliability_receipt_path: Path,
    artifact_root: Path,
    volume_id: str,
    run_id: str,
) -> dict[str, Any]:
    audit, audit_meta = _sealed_json(
        structural_audit_receipt_path,
        expected_filename=STRUCTURAL_AUDIT_FILENAME,
        expected_phase="audit",
    )
    _validate_structural_audit_receipt(audit)
    human, human_meta = _sealed_json(
        human_reliability_receipt_path,
        expected_filename=HUMAN_RELIABILITY_FILENAME,
        expected_phase="judging",
    )
    validate_human_reliability_receipt(human, human_run_dir=human_meta["run_dir"])
    root = paths.require_external_artifact_root(
        artifact_root,
        minimum_free_bytes=MIN_LIFECYCLE_FREE_BYTES,
        minimum_logical_reserve_bytes=MIN_LIFECYCLE_FREE_BYTES,
        expected_volume_id=volume_id,
        write_read_probe=False,
    )
    if audit_meta["artifact_root"] != root or human_meta["artifact_root"] != root:
        raise SealError("audit and human evidence must remain on the same frozen volume")
    _verify_audit_current_runs(audit, root=root)
    if (
        human.get("plan_hash") != audit["plan"]["plan_hash"]
        or human.get("audit_receipt_file_sha256")
        != audit_meta["receipt_file_sha256"]
        or human.get("audit_receipt_embedded_sha256") != audit["receipt_sha256"]
        or human.get("audit_run_manifest_sha256") != audit_meta["manifest_sha256"]
    ):
        raise SealError("human reliability evidence does not bind the exact audit")

    receipt = _sign_receipt(
        {
            "schema_version": LIFECYCLE_SCHEMA_VERSION,
            "receipt_kind": "unseal_authorization",
            "status": "authorized",
            "study_id": STUDY_ID,
            "protocol_version": PROTOCOL_VERSION,
            "created_at_utc": _utc_now(),
            "plan_hash": audit["plan"]["plan_hash"],
            "plan_manifest_sha256": audit["plan"]["plan_manifest_sha256"],
            "audit_receipt_file_sha256": audit_meta["receipt_file_sha256"],
            "audit_receipt_embedded_sha256": audit["receipt_sha256"],
            "audit_run_manifest_sha256": audit_meta["manifest_sha256"],
            "human_receipt_file_sha256": human_meta["receipt_file_sha256"],
            "human_receipt_embedded_sha256": human["receipt_sha256"],
            "human_run_manifest_sha256": human_meta["manifest_sha256"],
            "stage2a_manifest_sha256": audit["runs"]["stage2a"]["manifest_sha256"],
            "stage2b_manifest_sha256": audit["runs"]["stage2b"]["manifest_sha256"],
            "common_eligible_prefix_ids_sha256": audit["common_eligible"][
                "prefix_ids_sha256"
            ],
            "common_eligible_prefixes": audit["common_eligible"]["count"],
            "human_gate_status": {
                task: human["tasks"][task]["gate"]["status"] for task in TASK_SPECS
            },
        }
    )
    transaction = RunTransaction.start(
        phase="unseal",
        run_id=run_id,
        artifact_root=root,
        expected_volume_id=volume_id,
        minimum_free_bytes=MIN_LIFECYCLE_FREE_BYTES,
        metadata={"study_id": STUDY_ID, "plan_hash": receipt["plan_hash"]},
    )
    transaction.write_json(UNSEAL_FILENAME, receipt)
    final = transaction.complete(
        metadata={"status": "authorized", "plan_hash": receipt["plan_hash"]}
    )
    verification = verify_completed_run(final)
    return {
        "status": "authorized",
        "run_id": run_id,
        "receipt_sha256": receipt["receipt_sha256"],
        "manifest_sha256": verification["manifest_sha256"],
        "common_eligible_prefixes": receipt["common_eligible_prefixes"],
    }


def _validate_unseal_receipt(receipt: Mapping[str, Any]) -> None:
    expected = {
        "schema_version",
        "receipt_kind",
        "status",
        "study_id",
        "protocol_version",
        "created_at_utc",
        "plan_hash",
        "plan_manifest_sha256",
        "audit_receipt_file_sha256",
        "audit_receipt_embedded_sha256",
        "audit_run_manifest_sha256",
        "human_receipt_file_sha256",
        "human_receipt_embedded_sha256",
        "human_run_manifest_sha256",
        "stage2a_manifest_sha256",
        "stage2b_manifest_sha256",
        "common_eligible_prefix_ids_sha256",
        "common_eligible_prefixes",
        "human_gate_status",
        "receipt_sha256",
    }
    _require_exact_fields(receipt, expected, label="unseal authorization")
    if (
        receipt.get("schema_version") != LIFECYCLE_SCHEMA_VERSION
        or receipt.get("receipt_kind") != "unseal_authorization"
        or receipt.get("status") != "authorized"
        or receipt.get("study_id") != STUDY_ID
        or receipt.get("protocol_version") != PROTOCOL_VERSION
        or receipt.get("human_gate_status")
        != {task: "pass" for task in TASK_SPECS}
    ):
        raise SealError("unseal authorization identity/status differs")
    _parse_utc(receipt.get("created_at_utc"), label="unseal timestamp")
    for field in expected:
        if field.endswith("sha256") and (
            not isinstance(receipt.get(field), str) or not HEX64.fullmatch(receipt[field])
        ):
            raise SealError(f"unseal authorization hash is invalid: {field}")
    if (
        not isinstance(receipt.get("common_eligible_prefixes"), int)
        or receipt["common_eligible_prefixes"] <= 0
    ):
        raise SealError("unseal common eligible count is invalid")
    _require_embedded_hash(receipt, label="unseal authorization")


def _validate_unseal_chain(
    *,
    unseal_receipt_path: Path,
    structural_audit_receipt_path: Path,
    human_reliability_receipt_path: Path,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], Path, dict[str, Any]]:
    unseal, unseal_meta = _sealed_json(
        unseal_receipt_path,
        expected_filename=UNSEAL_FILENAME,
        expected_phase="unseal",
    )
    _validate_unseal_receipt(unseal)
    audit, audit_meta = _sealed_json(
        structural_audit_receipt_path,
        expected_filename=STRUCTURAL_AUDIT_FILENAME,
        expected_phase="audit",
    )
    _validate_structural_audit_receipt(audit)
    human, human_meta = _sealed_json(
        human_reliability_receipt_path,
        expected_filename=HUMAN_RELIABILITY_FILENAME,
        expected_phase="judging",
    )
    validate_human_reliability_receipt(human, human_run_dir=human_meta["run_dir"])
    roots = {
        unseal_meta["artifact_root"],
        audit_meta["artifact_root"],
        human_meta["artifact_root"],
    }
    if len(roots) != 1:
        raise SealError("unseal chain spans multiple artifact roots")
    root = roots.pop()
    expected = {
        "plan_hash": audit["plan"]["plan_hash"],
        "plan_manifest_sha256": audit["plan"]["plan_manifest_sha256"],
        "audit_receipt_file_sha256": audit_meta["receipt_file_sha256"],
        "audit_receipt_embedded_sha256": audit["receipt_sha256"],
        "audit_run_manifest_sha256": audit_meta["manifest_sha256"],
        "human_receipt_file_sha256": human_meta["receipt_file_sha256"],
        "human_receipt_embedded_sha256": human["receipt_sha256"],
        "human_run_manifest_sha256": human_meta["manifest_sha256"],
        "stage2a_manifest_sha256": audit["runs"]["stage2a"]["manifest_sha256"],
        "stage2b_manifest_sha256": audit["runs"]["stage2b"]["manifest_sha256"],
        "common_eligible_prefix_ids_sha256": audit["common_eligible"][
            "prefix_ids_sha256"
        ],
        "common_eligible_prefixes": audit["common_eligible"]["count"],
    }
    if any(unseal.get(key) != value for key, value in expected.items()):
        raise SealError("unseal authorization does not bind the exact audit/human chain")
    if (
        human.get("plan_hash") != audit["plan"]["plan_hash"]
        or human.get("audit_receipt_file_sha256")
        != audit_meta["receipt_file_sha256"]
        or human.get("audit_receipt_embedded_sha256") != audit["receipt_sha256"]
        or human.get("audit_run_manifest_sha256") != audit_meta["manifest_sha256"]
    ):
        raise SealError("human reliability receipt no longer binds the audit")
    _verify_audit_current_runs(audit, root=root)
    return unseal, audit, human, root, unseal_meta


def create_analysis_authorization(
    *,
    unseal_receipt_path: Path,
    structural_audit_receipt_path: Path,
    human_reliability_receipt_path: Path,
    artifact_root: Path,
    volume_id: str,
    run_id: str,
) -> dict[str, Any]:
    unseal, audit, human, chain_root, unseal_meta = _validate_unseal_chain(
        unseal_receipt_path=unseal_receipt_path,
        structural_audit_receipt_path=structural_audit_receipt_path,
        human_reliability_receipt_path=human_reliability_receipt_path,
    )
    root = paths.require_external_artifact_root(
        artifact_root,
        minimum_free_bytes=MIN_LIFECYCLE_FREE_BYTES,
        minimum_logical_reserve_bytes=MIN_LIFECYCLE_FREE_BYTES,
        expected_volume_id=volume_id,
        write_read_probe=False,
    )
    if root != chain_root:
        raise SealError("analysis authorization root differs from the unseal chain")
    receipt = _sign_receipt(
        {
            "schema_version": LIFECYCLE_SCHEMA_VERSION,
            "receipt_kind": "analysis_authorization",
            "status": "authorized",
            "study_id": STUDY_ID,
            "protocol_version": PROTOCOL_VERSION,
            "created_at_utc": _utc_now(),
            "plan_hash": audit["plan"]["plan_hash"],
            "plan_manifest_sha256": audit["plan"]["plan_manifest_sha256"],
            "unseal_receipt_file_sha256": unseal_meta["receipt_file_sha256"],
            "unseal_receipt_embedded_sha256": unseal["receipt_sha256"],
            "unseal_run_manifest_sha256": unseal_meta["manifest_sha256"],
            "audit_receipt_embedded_sha256": audit["receipt_sha256"],
            "human_receipt_embedded_sha256": human["receipt_sha256"],
            "stage2a_manifest_sha256": audit["runs"]["stage2a"]["manifest_sha256"],
            "stage2b_manifest_sha256": audit["runs"]["stage2b"]["manifest_sha256"],
            "common_eligible_prefix_ids_sha256": audit["common_eligible"][
                "prefix_ids_sha256"
            ],
            "common_eligible_prefixes": audit["common_eligible"]["count"],
        }
    )
    transaction = RunTransaction.start(
        phase="analysis-authorization",
        run_id=run_id,
        artifact_root=root,
        expected_volume_id=volume_id,
        minimum_free_bytes=MIN_LIFECYCLE_FREE_BYTES,
        metadata={"study_id": STUDY_ID, "plan_hash": receipt["plan_hash"]},
    )
    transaction.write_json(ANALYSIS_AUTHORIZATION_FILENAME, receipt)
    final = transaction.complete(
        metadata={"status": "authorized", "plan_hash": receipt["plan_hash"]}
    )
    verification = verify_completed_run(final)
    return {
        "status": "authorized",
        "run_id": run_id,
        "receipt_sha256": receipt["receipt_sha256"],
        "manifest_sha256": verification["manifest_sha256"],
        "common_eligible_prefixes": receipt["common_eligible_prefixes"],
    }


def check_analysis_authorization(
    *,
    analysis_authorization_path: Path,
    unseal_receipt_path: Path,
    structural_audit_receipt_path: Path,
    human_reliability_receipt_path: Path,
) -> dict[str, Any]:
    authorization, authorization_meta = _sealed_json(
        analysis_authorization_path,
        expected_filename=ANALYSIS_AUTHORIZATION_FILENAME,
        expected_phase="analysis-authorization",
    )
    _require_exact_fields(
        authorization,
        {
            "schema_version",
            "receipt_kind",
            "status",
            "study_id",
            "protocol_version",
            "created_at_utc",
            "plan_hash",
            "plan_manifest_sha256",
            "unseal_receipt_file_sha256",
            "unseal_receipt_embedded_sha256",
            "unseal_run_manifest_sha256",
            "audit_receipt_embedded_sha256",
            "human_receipt_embedded_sha256",
            "stage2a_manifest_sha256",
            "stage2b_manifest_sha256",
            "common_eligible_prefix_ids_sha256",
            "common_eligible_prefixes",
            "receipt_sha256",
        },
        label="analysis authorization",
    )
    if (
        authorization.get("schema_version") != LIFECYCLE_SCHEMA_VERSION
        or authorization.get("receipt_kind") != "analysis_authorization"
        or authorization.get("status") != "authorized"
        or authorization.get("study_id") != STUDY_ID
        or authorization.get("protocol_version") != PROTOCOL_VERSION
    ):
        raise SealError("analysis authorization identity/status differs")
    _parse_utc(authorization.get("created_at_utc"), label="analysis authorization timestamp")
    _require_embedded_hash(authorization, label="analysis authorization")
    unseal, audit, human, root, unseal_meta = _validate_unseal_chain(
        unseal_receipt_path=unseal_receipt_path,
        structural_audit_receipt_path=structural_audit_receipt_path,
        human_reliability_receipt_path=human_reliability_receipt_path,
    )
    if authorization_meta["artifact_root"] != root:
        raise SealError("analysis authorization is on a different artifact root")
    expected = {
        "plan_hash": audit["plan"]["plan_hash"],
        "plan_manifest_sha256": audit["plan"]["plan_manifest_sha256"],
        "unseal_receipt_file_sha256": unseal_meta["receipt_file_sha256"],
        "unseal_receipt_embedded_sha256": unseal["receipt_sha256"],
        "unseal_run_manifest_sha256": unseal_meta["manifest_sha256"],
        "audit_receipt_embedded_sha256": audit["receipt_sha256"],
        "human_receipt_embedded_sha256": human["receipt_sha256"],
        "stage2a_manifest_sha256": audit["runs"]["stage2a"]["manifest_sha256"],
        "stage2b_manifest_sha256": audit["runs"]["stage2b"]["manifest_sha256"],
        "common_eligible_prefix_ids_sha256": audit["common_eligible"][
            "prefix_ids_sha256"
        ],
        "common_eligible_prefixes": audit["common_eligible"]["count"],
    }
    if any(authorization.get(key) != value for key, value in expected.items()):
        raise SealError("analysis authorization does not bind the current unseal chain")
    return {
        "status": "authorized",
        "plan_hash": authorization["plan_hash"],
        "receipt_sha256": authorization["receipt_sha256"],
        "manifest_sha256": authorization_meta["manifest_sha256"],
        "common_eligible_prefixes": authorization["common_eligible_prefixes"],
    }


def _common_parser(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--volume-id", required=True)
    parser.add_argument("--run-id", required=True)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    audit = commands.add_parser("audit", help="seal a structural-only target-run audit")
    _common_parser(audit)
    audit.add_argument("--plan-dir", type=Path, required=True)
    audit.add_argument("--artifact-receipt", type=Path, required=True)
    audit.add_argument("--calibration-receipt", type=Path, required=True)
    audit.add_argument("--registration-receipt", type=Path, required=True)
    audit.add_argument("--pre-prefix-freeze-receipt", type=Path, required=True)
    audit.add_argument("--acceptance-receipt", type=Path, required=True)
    audit.add_argument("--prefix-receipt", type=Path, required=True)
    audit.add_argument("--prefix-freeze-receipt", type=Path, required=True)
    audit.add_argument("--prefix-bank-run-id", required=True)
    audit.add_argument("--stage2a-run-id", required=True)
    audit.add_argument("--stage2b-run-id", required=True)

    unseal = commands.add_parser(
        "unseal", help="authorize unsealing after structural and two-human gates"
    )
    _common_parser(unseal)
    unseal.add_argument("--structural-audit-receipt", type=Path, required=True)
    unseal.add_argument("--human-reliability-receipt", type=Path, required=True)

    authorize = commands.add_parser(
        "authorize-analysis", help="seal an analysis authorization bound to unseal"
    )
    _common_parser(authorize)
    authorize.add_argument("--unseal-receipt", type=Path, required=True)
    authorize.add_argument("--structural-audit-receipt", type=Path, required=True)
    authorize.add_argument("--human-reliability-receipt", type=Path, required=True)

    check = commands.add_parser(
        "check-analysis", help="fail closed unless the complete authorization chain passes"
    )
    check.add_argument("--analysis-authorization", type=Path, required=True)
    check.add_argument("--unseal-receipt", type=Path, required=True)
    check.add_argument("--structural-audit-receipt", type=Path, required=True)
    check.add_argument("--human-reliability-receipt", type=Path, required=True)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> None:
    args = parse_args(argv)
    try:
        if args.command == "audit":
            result = create_structural_audit(
                plan_dir=args.plan_dir,
                volume_id=args.volume_id,
                artifact_root=args.artifact_root,
                artifact_receipt_path=args.artifact_receipt,
                calibration_receipt_path=args.calibration_receipt,
                registration_receipt_path=args.registration_receipt,
                pre_prefix_freeze_receipt_path=args.pre_prefix_freeze_receipt,
                acceptance_receipt_path=args.acceptance_receipt,
                prefix_receipt_path=args.prefix_receipt,
                prefix_freeze_receipt_path=args.prefix_freeze_receipt,
                prefix_bank_run_id=args.prefix_bank_run_id,
                stage2a_run_id=args.stage2a_run_id,
                stage2b_run_id=args.stage2b_run_id,
                run_id=args.run_id,
            )
        elif args.command == "unseal":
            result = create_unseal_authorization(
                structural_audit_receipt_path=args.structural_audit_receipt,
                human_reliability_receipt_path=args.human_reliability_receipt,
                artifact_root=args.artifact_root,
                volume_id=args.volume_id,
                run_id=args.run_id,
            )
        elif args.command == "authorize-analysis":
            result = create_analysis_authorization(
                unseal_receipt_path=args.unseal_receipt,
                structural_audit_receipt_path=args.structural_audit_receipt,
                human_reliability_receipt_path=args.human_reliability_receipt,
                artifact_root=args.artifact_root,
                volume_id=args.volume_id,
                run_id=args.run_id,
            )
        else:
            result = check_analysis_authorization(
                analysis_authorization_path=args.analysis_authorization,
                unseal_receipt_path=args.unseal_receipt,
                structural_audit_receipt_path=args.structural_audit_receipt,
                human_reliability_receipt_path=args.human_reliability_receipt,
            )
    except Exception as exc:
        # Never include exception detail: paths or raw archive context must not
        # leak through lifecycle stdout/stderr in automated runs.
        print(
            json.dumps(
                {
                    "status": "fail",
                    "error_code": type(exc).__name__,
                    "study_id": STUDY_ID,
                },
                sort_keys=True,
            )
        )
        raise SystemExit(1) from None
    print(json.dumps(result, ensure_ascii=False, allow_nan=False, sort_keys=True))


if __name__ == "__main__":
    main()

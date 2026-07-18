"""Transactional external archive primitives for the changepoint study.

Outcome-bearing files must be written beneath the persistent volume selected by
``paths.require_external_artifact_root``.  This module intentionally has no
repository-local fallback.  A run and each of its blocks are built under a
fresh ``.partial`` directory, inventoried, renamed once, and receive their
``COMPLETE.json`` marker last.  Completed directories are usable only after a
full byte-count and SHA-256 readback.

The source-residual format is deliberately narrow: one BF16 safetensors tensor
named ``source_residuals`` with shape ``[N, 8192]`` and one Parquet row index.
The index points to the tensor with a block-relative POSIX path and a zero-based
row offset.  Absolute paths are never serialized.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import uuid
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Mapping, Sequence

from .paths import (
    MIN_ARTIFACT_FREE_BYTES,
    require_external_artifact_root,
    require_new_external_artifact_path,
)


ARCHIVE_SCHEMA_VERSION = 1
SOURCE_TENSOR_KEY = "source_residuals"
SOURCE_WIDTH = 8192
RUN_MANIFEST = "REMOTE_MANIFEST.json"
BLOCK_MANIFEST = "BLOCK_MANIFEST.json"
COMPLETE_MARKER = "COMPLETE.json"
_COMPONENT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_PATH_FIELD_SUFFIXES = ("_path", "_file", "_shard", "_directory", "_dir")


class ArchiveError(RuntimeError):
    """Base class for archive contract failures."""


class ArchiveIntegrityError(ArchiveError):
    """Raised when a supposedly sealed artifact no longer matches its receipt."""


class ArchiveStateError(ArchiveError):
    """Raised for an invalid transaction transition or attempted overwrite."""


def sha256_file(path: Path, *, chunk_bytes: int = 8 * 1024 * 1024) -> str:
    """Hash a file by reading it back from its published path."""

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(chunk_bytes), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _validate_component(value: str, *, label: str) -> str:
    if not isinstance(value, str) or not _COMPONENT.fullmatch(value):
        raise ArchiveStateError(
            f"{label} must match {_COMPONENT.pattern!r}; got {value!r}"
        )
    if value.endswith(".partial"):
        raise ArchiveStateError(f"{label} must not include the .partial suffix")
    return value


def validate_relative_path(value: str | PurePosixPath) -> str:
    """Return a normalized archive-relative POSIX path or fail closed."""

    raw = str(value)
    if not raw or "\\" in raw:
        raise ArchiveIntegrityError(f"invalid archive-relative path: {raw!r}")
    path = PurePosixPath(raw)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise ArchiveIntegrityError(f"invalid archive-relative path: {raw!r}")
    normalized = path.as_posix()
    if normalized != raw:
        raise ArchiveIntegrityError(
            f"archive path is not normalized POSIX text: {raw!r}"
        )
    return normalized


def _relative_to(path: Path, root: Path) -> str:
    try:
        relative = path.resolve(strict=False).relative_to(root.resolve(strict=False))
    except ValueError as exc:
        raise ArchiveIntegrityError(f"path escapes archive root: {path}") from exc
    return validate_relative_path(PurePosixPath(*relative.parts))


def _fsync_file(path: Path) -> None:
    with path.open("rb") as handle:
        os.fsync(handle.fileno())


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _publish_temporary(temporary: Path, destination: Path) -> None:
    """Publish without overwriting an existing name.

    A hard link gives POSIX no-replace semantics and keeps the destination
    invisible until the complete temporary file has been flushed.  Persistent
    RunPod network volumes support ordinary hard links.  If the filesystem does
    not, fail rather than fall back to an overwrite-capable rename.
    """

    if destination.exists() or destination.is_symlink():
        raise ArchiveStateError(f"refusing to overwrite archive file: {destination}")
    try:
        os.link(temporary, destination)
    except FileExistsError as exc:
        raise ArchiveStateError(
            f"refusing to overwrite archive file: {destination}"
        ) from exc
    except OSError as exc:
        raise ArchiveStateError(
            f"atomic no-replace publication failed for {destination}"
        ) from exc
    temporary.unlink()
    _fsync_directory(destination.parent)


def _temporary_path(parent: Path, stem: str) -> Path:
    return parent / f".{stem}.tmp-{uuid.uuid4().hex}"


def atomic_write_json(path: Path, value: Any) -> None:
    """Write canonical JSON once; an existing destination is never replaced."""

    _reject_serialized_absolute_paths(value)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = _temporary_path(path.parent, path.name)
    payload = _canonical_json_bytes(value) + b"\n"
    try:
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        _publish_temporary(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _path_role(relative: str) -> str:
    path = PurePosixPath(relative)
    if path.suffix == ".safetensors":
        return "bf16_source_residuals"
    if path.suffix == ".parquet":
        return "source_row_index"
    if path.name == BLOCK_MANIFEST:
        return "block_manifest"
    if path.name == COMPLETE_MARKER:
        return "completion_marker"
    if path.name.endswith("receipt.json"):
        return "shard_receipt"
    if path.suffix == ".json":
        return "metadata"
    return "archive_payload"


def _reject_symlinks(path: Path, root: Path) -> None:
    current = path
    while current != root:
        if current.is_symlink():
            raise ArchiveIntegrityError(f"symlink is forbidden in archive: {current}")
        current = current.parent
    if root.is_symlink():
        raise ArchiveIntegrityError(f"archive root may not be a symlink: {root}")


def inventory_files(
    directory: Path,
    *,
    excluded_relative_paths: Iterable[str] = (),
) -> list[dict[str, Any]]:
    """Build a stable relative-path inventory after reading every file."""

    excluded = {validate_relative_path(value) for value in excluded_relative_paths}
    records: list[dict[str, Any]] = []
    for path in sorted(directory.rglob("*")):
        if path.is_symlink():
            raise ArchiveIntegrityError(f"symlink is forbidden in archive: {path}")
        if not path.is_file():
            continue
        relative = _relative_to(path, directory)
        if relative in excluded:
            continue
        records.append(
            {
                "path": relative,
                "role": _path_role(relative),
                "bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
        )
    return records


def _validate_manifest_records(
    directory: Path,
    records: Sequence[Mapping[str, Any]],
) -> set[str]:
    seen: set[str] = set()
    for record in records:
        relative = validate_relative_path(str(record.get("path", "")))
        if relative in seen:
            raise ArchiveIntegrityError(f"duplicate manifest path: {relative}")
        seen.add(relative)
        path = directory / PurePosixPath(relative)
        _reject_symlinks(path, directory)
        if not path.is_file():
            raise ArchiveIntegrityError(f"manifest file is missing: {relative}")
        expected_bytes = record.get("bytes")
        if not isinstance(expected_bytes, int) or expected_bytes < 0:
            raise ArchiveIntegrityError(f"invalid byte count for {relative}")
        if path.stat().st_size != expected_bytes:
            raise ArchiveIntegrityError(f"byte count changed for {relative}")
        expected_hash = record.get("sha256")
        if not isinstance(expected_hash, str) or len(expected_hash) != 64:
            raise ArchiveIntegrityError(f"invalid SHA-256 for {relative}")
        if sha256_file(path) != expected_hash:
            raise ArchiveIntegrityError(f"SHA-256 changed for {relative}")
    return seen


def verify_completed_directory(
    directory: Path,
    *,
    manifest_name: str,
    expected_kind: str,
) -> dict[str, Any]:
    """Verify a sealed directory, including absence of unreceipted files."""

    directory = directory.resolve(strict=True)
    if directory.name.endswith(".partial"):
        raise ArchiveIntegrityError(f"partial directory is not citable: {directory}")
    manifest_path = directory / manifest_name
    complete_path = directory / COMPLETE_MARKER
    if not manifest_path.is_file() or not complete_path.is_file():
        raise ArchiveIntegrityError(f"completion markers are missing in {directory}")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        complete = json.loads(complete_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ArchiveIntegrityError(f"invalid completion JSON in {directory}") from exc
    if manifest.get("archive_schema_version") != ARCHIVE_SCHEMA_VERSION:
        raise ArchiveIntegrityError("archive schema version differs")
    if manifest.get("kind") != expected_kind:
        raise ArchiveIntegrityError(
            f"manifest kind differs: expected {expected_kind!r}"
        )
    if complete.get("status") != "complete" or complete.get("kind") != expected_kind:
        raise ArchiveIntegrityError("terminal completion status differs")
    manifest_hash = sha256_file(manifest_path)
    if complete.get("manifest_sha256") != manifest_hash:
        raise ArchiveIntegrityError("completion marker does not bind the manifest")
    records = manifest.get("files")
    if not isinstance(records, list):
        raise ArchiveIntegrityError("manifest files must be a list")
    receipted = _validate_manifest_records(directory, records)
    if manifest_name in receipted or COMPLETE_MARKER in receipted:
        raise ArchiveIntegrityError("terminal files may not inventory themselves")
    for path in directory.rglob("*"):
        if path.is_symlink():
            raise ArchiveIntegrityError(f"symlink is forbidden in archive: {path}")
    actual = {
        _relative_to(path, directory)
        for path in directory.rglob("*")
        if path.is_file()
    }
    expected = receipted | {manifest_name, COMPLETE_MARKER}
    if actual != expected:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        raise ArchiveIntegrityError(
            f"sealed inventory differs; missing={missing}, extra={extra}"
        )
    expected_directories = {
        parent.as_posix()
        for relative in expected
        for parent in PurePosixPath(relative).parents
        if parent != PurePosixPath(".")
    }
    actual_directories = {
        _relative_to(path, directory)
        for path in directory.rglob("*")
        if path.is_dir()
    }
    if actual_directories != expected_directories:
        missing = sorted(expected_directories - actual_directories)
        extra = sorted(actual_directories - expected_directories)
        raise ArchiveIntegrityError(
            f"sealed directory inventory differs; missing={missing}, extra={extra}"
        )
    total_bytes = sum(int(record["bytes"]) for record in records)
    if complete.get("file_count") != len(records):
        raise ArchiveIntegrityError("completion file count differs")
    if complete.get("payload_bytes") != total_bytes:
        raise ArchiveIntegrityError("completion payload byte count differs")
    return {
        "status": "verified",
        "kind": expected_kind,
        "manifest_sha256": manifest_hash,
        "file_count": len(records),
        "payload_bytes": total_bytes,
    }


def verify_completed_run(directory: Path) -> dict[str, Any]:
    return verify_completed_directory(
        directory, manifest_name=RUN_MANIFEST, expected_kind="run"
    )


def verify_completed_block(directory: Path) -> dict[str, Any]:
    return verify_completed_directory(
        directory, manifest_name=BLOCK_MANIFEST, expected_kind="block"
    )


def _reject_serialized_absolute_paths(value: Any, *, parent_key: str = "") -> None:
    """Validate JSON path fields recursively without misreading prompt text."""

    if isinstance(value, Mapping):
        for key, child in value.items():
            if not isinstance(key, str):
                raise ArchiveStateError("serialized mapping keys must be strings")
            _reject_serialized_absolute_paths(child, parent_key=key)
        return
    if isinstance(value, (list, tuple)):
        for child in value:
            _reject_serialized_absolute_paths(child, parent_key=parent_key)
        return
    is_path_field = parent_key == "path" or parent_key.endswith(_PATH_FIELD_SUFFIXES)
    if value is not None and is_path_field:
        if not isinstance(value, str):
            raise ArchiveStateError(f"serialized path field {parent_key!r} must be text")
        validate_relative_path(value)


def _normalize_index_rows(
    rows: Sequence[Mapping[str, Any]],
    *,
    expected_rows: int,
    shard_relative_path: str,
) -> list[dict[str, Any]]:
    if len(rows) != expected_rows:
        raise ArchiveStateError(
            f"row index length differs: expected {expected_rows}, got {len(rows)}"
        )
    normalized: list[dict[str, Any]] = []
    row_ids: set[str] = set()
    for offset, source in enumerate(rows):
        if not isinstance(source, Mapping):
            raise ArchiveStateError(f"row index item {offset} is not a mapping")
        row = dict(source)
        row_id = row.get("row_id")
        if not isinstance(row_id, str) or not row_id:
            raise ArchiveStateError(f"row index item {offset} has no non-empty row_id")
        if row_id in row_ids:
            raise ArchiveStateError(f"duplicate row_id in source shard: {row_id!r}")
        row_ids.add(row_id)
        row["source_shard"] = shard_relative_path
        row["source_row_offset"] = offset
        _reject_serialized_absolute_paths(row)
        normalized.append(row)
    return normalized


def _torch_and_safetensors() -> tuple[Any, Any, Any]:
    try:
        import torch
        from safetensors import safe_open
        from safetensors.torch import save_file
    except ImportError as exc:
        raise ArchiveStateError(
            "torch and safetensors are required to write BF16 source shards"
        ) from exc
    return torch, safe_open, save_file


def _arrow_modules() -> tuple[Any, Any]:
    try:
        import pyarrow as pa
        import pyarrow.parquet as pq
    except ImportError as exc:
        raise ArchiveStateError(
            "pyarrow is required to write the Parquet source-row index"
        ) from exc
    return pa, pq


@dataclass(frozen=True)
class SourceShardReceipt:
    shard_id: str
    rows: int
    width: int
    dtype: str
    tensor_key: str
    residual_path: str
    residual_bytes: int
    residual_sha256: str
    index_path: str
    index_bytes: int
    index_sha256: str
    index_columns: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "archive_schema_version": ARCHIVE_SCHEMA_VERSION,
            "shard_id": self.shard_id,
            "rows": self.rows,
            "width": self.width,
            "dtype": self.dtype,
            "tensor_key": self.tensor_key,
            "residual": {
                "path": self.residual_path,
                "bytes": self.residual_bytes,
                "sha256": self.residual_sha256,
                "shape": [self.rows, self.width],
                "dtype": self.dtype,
            },
            "index": {
                "path": self.index_path,
                "bytes": self.index_bytes,
                "sha256": self.index_sha256,
                "format": "parquet",
                "rows": self.rows,
                "columns": list(self.index_columns),
            },
        }


class BlockTransaction:
    """One fresh block inside a still-partial run."""

    def __init__(
        self,
        *,
        run: "RunTransaction",
        block_id: str,
        partial_path: Path,
        final_path: Path,
    ) -> None:
        self.run = run
        self.block_id = block_id
        self.partial_path = partial_path
        self.final_path = final_path
        self._complete = False

    def _require_open(self) -> None:
        if self._complete or not self.partial_path.is_dir():
            raise ArchiveStateError(f"block transaction is not open: {self.block_id}")

    def write_json(self, relative_path: str, value: Any) -> Path:
        """Write a fresh block-relative metadata file."""

        self._require_open()
        relative = validate_relative_path(relative_path)
        path = self.partial_path / PurePosixPath(relative)
        atomic_write_json(path, value)
        return path

    def write_source_shard(
        self,
        shard_id: str,
        residuals: Any,
        rows: Sequence[Mapping[str, Any]],
    ) -> SourceShardReceipt:
        """Write, reopen, and receipt one content-addressed BF16 source shard."""

        self._require_open()
        shard_id = _validate_component(shard_id, label="shard_id")
        if list((self.partial_path / "receipts").glob(f"{shard_id}-*.receipt.json")):
            raise ArchiveStateError(f"source shard already exists: {shard_id}")
        torch, safe_open, save_file = _torch_and_safetensors()
        pa, pq = _arrow_modules()
        if not hasattr(residuals, "shape") or len(tuple(residuals.shape)) != 2:
            raise ArchiveStateError("source residuals must have shape [N, 8192]")
        shape = tuple(int(value) for value in residuals.shape)
        if shape[0] <= 0 or shape[1] != SOURCE_WIDTH:
            raise ArchiveStateError(
                f"source residual shape must be [N, {SOURCE_WIDTH}], got {shape}"
            )
        tensor = residuals.detach().to(device="cpu", dtype=torch.bfloat16).contiguous()
        if not bool(torch.isfinite(tensor.float()).all().item()):
            raise ArchiveStateError("source residual shard contains non-finite values")

        residual_dir = self.partial_path / "residuals"
        index_dir = self.partial_path / "indexes"
        receipt_dir = self.partial_path / "receipts"
        residual_dir.mkdir(parents=True, exist_ok=True)
        index_dir.mkdir(parents=True, exist_ok=True)
        receipt_dir.mkdir(parents=True, exist_ok=True)

        residual_temp = _temporary_path(residual_dir, f"{shard_id}.safetensors")
        try:
            save_file({SOURCE_TENSOR_KEY: tensor}, str(residual_temp))
            _fsync_file(residual_temp)
            residual_hash = sha256_file(residual_temp)
            residual_name = f"{shard_id}-{residual_hash[:16]}.safetensors"
            residual_path = residual_dir / residual_name
            _publish_temporary(residual_temp, residual_path)
        finally:
            residual_temp.unlink(missing_ok=True)

        with safe_open(str(residual_path), framework="pt", device="cpu") as handle:
            if list(handle.keys()) != [SOURCE_TENSOR_KEY]:
                raise ArchiveIntegrityError("source safetensors keys differ on readback")
            reopened = handle.get_tensor(SOURCE_TENSOR_KEY)
        if tuple(reopened.shape) != shape or reopened.dtype != torch.bfloat16:
            raise ArchiveIntegrityError("source safetensors shape/dtype differs on readback")
        if not bool(torch.equal(reopened.view(torch.int16), tensor.view(torch.int16))):
            raise ArchiveIntegrityError("source safetensors payload differs on readback")
        if sha256_file(residual_path) != residual_hash:
            raise ArchiveIntegrityError("source safetensors hash changed during readback")

        shard_relative = validate_relative_path(
            PurePosixPath("residuals") / residual_name
        )
        normalized_rows = _normalize_index_rows(
            rows, expected_rows=shape[0], shard_relative_path=shard_relative
        )
        table = pa.Table.from_pylist(normalized_rows)
        index_temp = _temporary_path(index_dir, f"{shard_id}.parquet")
        try:
            pq.write_table(
                table,
                index_temp,
                compression="zstd",
                use_dictionary=True,
                write_statistics=True,
            )
            _fsync_file(index_temp)
            index_hash = sha256_file(index_temp)
            index_name = f"{shard_id}-{index_hash[:16]}.parquet"
            index_path = index_dir / index_name
            _publish_temporary(index_temp, index_path)
        finally:
            index_temp.unlink(missing_ok=True)
        reopened_table = pq.read_table(index_path)
        if reopened_table.num_rows != shape[0]:
            raise ArchiveIntegrityError("Parquet row count differs on readback")
        if reopened_table.column_names != table.column_names:
            raise ArchiveIntegrityError("Parquet columns differ on readback")
        offsets = reopened_table.column("source_row_offset").to_pylist()
        shard_paths = reopened_table.column("source_shard").to_pylist()
        if offsets != list(range(shape[0])) or any(
            value != shard_relative for value in shard_paths
        ):
            raise ArchiveIntegrityError("Parquet shard alignment differs on readback")
        if sha256_file(index_path) != index_hash:
            raise ArchiveIntegrityError("Parquet index hash changed during readback")

        receipt = SourceShardReceipt(
            shard_id=shard_id,
            rows=shape[0],
            width=shape[1],
            dtype="bfloat16",
            tensor_key=SOURCE_TENSOR_KEY,
            residual_path=shard_relative,
            residual_bytes=residual_path.stat().st_size,
            residual_sha256=residual_hash,
            index_path=validate_relative_path(PurePosixPath("indexes") / index_name),
            index_bytes=index_path.stat().st_size,
            index_sha256=index_hash,
            index_columns=tuple(table.column_names),
        )
        receipt_path = receipt_dir / f"{shard_id}-{residual_hash[:16]}.receipt.json"
        atomic_write_json(receipt_path, receipt.as_dict())
        return receipt

    def complete(self, *, metadata: Mapping[str, Any] | None = None) -> Path:
        """Seal, rename, mark complete last, and verify this block."""

        self._require_open()
        if self.final_path.exists() or self.final_path.is_symlink():
            raise ArchiveStateError(f"final block path already exists: {self.final_path}")
        temporary_files = [
            path for path in self.partial_path.rglob("*") if ".tmp-" in path.name
        ]
        if temporary_files:
            raise ArchiveStateError(f"temporary block files remain: {temporary_files}")
        files = inventory_files(
            self.partial_path,
            excluded_relative_paths=(BLOCK_MANIFEST, COMPLETE_MARKER),
        )
        manifest = {
            "archive_schema_version": ARCHIVE_SCHEMA_VERSION,
            "kind": "block",
            "block_id": self.block_id,
            "metadata": dict(metadata or {}),
            "files": files,
        }
        atomic_write_json(self.partial_path / BLOCK_MANIFEST, manifest)
        _fsync_directory(self.partial_path)
        os.rename(self.partial_path, self.final_path)
        _fsync_directory(self.final_path.parent)
        manifest_hash = sha256_file(self.final_path / BLOCK_MANIFEST)
        atomic_write_json(
            self.final_path / COMPLETE_MARKER,
            {
                "archive_schema_version": ARCHIVE_SCHEMA_VERSION,
                "kind": "block",
                "status": "complete",
                "block_id": self.block_id,
                "manifest_sha256": manifest_hash,
                "file_count": len(files),
                "payload_bytes": sum(int(row["bytes"]) for row in files),
            },
        )
        verify_completed_block(self.final_path)
        self._complete = True
        return self.final_path


class RunTransaction:
    """Fresh outcome-bearing run transaction on a verified external volume."""

    def __init__(
        self,
        *,
        artifact_root: Path,
        phase: str,
        run_id: str,
        partial_path: Path,
        final_path: Path,
    ) -> None:
        self.artifact_root = artifact_root
        self.phase = phase
        self.run_id = run_id
        self.partial_path = partial_path
        self.final_path = final_path
        self._complete = False

    @classmethod
    def start(
        cls,
        *,
        phase: str,
        run_id: str,
        artifact_root: str | Path | None = None,
        expected_volume_id: str | None = None,
        minimum_free_bytes: int = MIN_ARTIFACT_FREE_BYTES,
        metadata: Mapping[str, Any] | None = None,
    ) -> "RunTransaction":
        """Create a fresh ``<phase>/<run_id>.partial`` transaction."""

        phase = _validate_component(phase, label="phase")
        run_id = _validate_component(run_id, label="run_id")
        root = require_external_artifact_root(
            artifact_root,
            minimum_free_bytes=minimum_free_bytes,
            expected_volume_id=expected_volume_id,
            write_read_probe=True,
        )
        partial = require_new_external_artifact_path(
            PurePosixPath(phase) / f"{run_id}.partial",
            artifact_root=root,
            minimum_free_bytes=minimum_free_bytes,
            expected_volume_id=expected_volume_id,
        )
        final = require_new_external_artifact_path(
            PurePosixPath(phase) / run_id,
            artifact_root=root,
            minimum_free_bytes=minimum_free_bytes,
            expected_volume_id=expected_volume_id,
        )
        partial.parent.mkdir(parents=True, exist_ok=True)
        partial.mkdir()
        transaction = cls(
            artifact_root=root,
            phase=phase,
            run_id=run_id,
            partial_path=partial,
            final_path=final,
        )
        transaction.write_json(
            "RUN_STARTED.json",
            {
                "archive_schema_version": ARCHIVE_SCHEMA_VERSION,
                "kind": "run_start",
                "phase": phase,
                "run_id": run_id,
                "metadata": dict(metadata or {}),
            },
        )
        return transaction

    def _require_open(self) -> None:
        if self._complete or not self.partial_path.is_dir():
            raise ArchiveStateError(f"run transaction is not open: {self.run_id}")

    def write_json(self, relative_path: str, value: Any) -> Path:
        self._require_open()
        relative = validate_relative_path(relative_path)
        if relative in {RUN_MANIFEST, COMPLETE_MARKER}:
            raise ArchiveStateError(f"reserved run path: {relative}")
        path = self.partial_path / PurePosixPath(relative)
        atomic_write_json(path, value)
        return path

    def begin_block(self, block_id: str) -> BlockTransaction:
        self._require_open()
        block_id = _validate_component(block_id, label="block_id")
        blocks = self.partial_path / "blocks"
        blocks.mkdir(exist_ok=True)
        partial = blocks / f"{block_id}.partial"
        final = blocks / block_id
        if partial.exists() or partial.is_symlink() or final.exists() or final.is_symlink():
            raise ArchiveStateError(f"block path is not fresh: {block_id}")
        partial.mkdir()
        return BlockTransaction(
            run=self,
            block_id=block_id,
            partial_path=partial,
            final_path=final,
        )

    def complete(self, *, metadata: Mapping[str, Any] | None = None) -> Path:
        """Seal the run; ``COMPLETE.json`` is created only after the rename."""

        self._require_open()
        if self.final_path.exists() or self.final_path.is_symlink():
            raise ArchiveStateError(f"final run path already exists: {self.final_path}")
        partials = [
            path
            for path in self.partial_path.rglob("*")
            if path.name.endswith(".partial") or ".tmp-" in path.name
        ]
        if partials:
            raise ArchiveStateError(f"incomplete descendants remain: {partials}")
        blocks_dir = self.partial_path / "blocks"
        block_receipts: list[dict[str, Any]] = []
        if blocks_dir.exists():
            for block in sorted(path for path in blocks_dir.iterdir() if path.is_dir()):
                receipt = verify_completed_block(block)
                block_receipts.append(
                    {
                        "block_id": block.name,
                        "manifest_sha256": receipt["manifest_sha256"],
                        "file_count": receipt["file_count"],
                        "payload_bytes": receipt["payload_bytes"],
                    }
                )
        files = inventory_files(
            self.partial_path,
            excluded_relative_paths=(RUN_MANIFEST, COMPLETE_MARKER),
        )
        manifest = {
            "archive_schema_version": ARCHIVE_SCHEMA_VERSION,
            "kind": "run",
            "phase": self.phase,
            "run_id": self.run_id,
            "metadata": dict(metadata or {}),
            "blocks": block_receipts,
            "files": files,
        }
        atomic_write_json(self.partial_path / RUN_MANIFEST, manifest)
        _fsync_directory(self.partial_path)
        os.rename(self.partial_path, self.final_path)
        _fsync_directory(self.final_path.parent)
        manifest_hash = sha256_file(self.final_path / RUN_MANIFEST)
        atomic_write_json(
            self.final_path / COMPLETE_MARKER,
            {
                "archive_schema_version": ARCHIVE_SCHEMA_VERSION,
                "kind": "run",
                "status": "complete",
                "phase": self.phase,
                "run_id": self.run_id,
                "manifest_sha256": manifest_hash,
                "file_count": len(files),
                "payload_bytes": sum(int(row["bytes"]) for row in files),
            },
        )
        verify_completed_run(self.final_path)
        self._complete = True
        return self.final_path


def open_source_shard(
    block_directory: Path,
    receipt: SourceShardReceipt | Mapping[str, Any],
) -> Any:
    """Hash-verify and read a BF16 source tensor from a completed block."""

    _, safe_open, _ = _torch_and_safetensors()
    payload = receipt.as_dict() if isinstance(receipt, SourceShardReceipt) else receipt
    residual = payload["residual"]
    relative = validate_relative_path(str(residual["path"]))
    path = block_directory / PurePosixPath(relative)
    if path.stat().st_size != int(residual["bytes"]):
        raise ArchiveIntegrityError("source shard byte count differs")
    if sha256_file(path) != residual["sha256"]:
        raise ArchiveIntegrityError("source shard SHA-256 differs")
    with safe_open(str(path), framework="pt", device="cpu") as handle:
        tensor = handle.get_tensor(str(payload.get("tensor_key", SOURCE_TENSOR_KEY)))
    shape = tuple(int(value) for value in residual["shape"])
    if tuple(tensor.shape) != shape or str(tensor.dtype).split(".")[-1] != "bfloat16":
        raise ArchiveIntegrityError("source shard tensor contract differs")
    return tensor

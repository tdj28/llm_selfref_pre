#!/usr/bin/env python3
"""Exercise one dense, resumable, atomic shard on the target raw filesystem.

The production CLI has no size switch: it always writes the frozen maximum
atomic shard.  A private capability-gated override exists only so unit tests
can exercise the same real filesystem path without writing two GiB.

This module deliberately does not import the model runtime or runner module.
It hashes the frozen runner source as data, and it validates the plan without
parsing/rendering any prompt or loading any model artifact.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path, PurePosixPath
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from experiments.consciousness_sae_realization_validation import (  # noqa: E402
    controls,
    protocol,
)


RUNNER_RELATIVE_PATH = (
    "experiments/consciousness_sae_realization_validation/runner.py"
)
PLAN_FILE_NAMES = frozenset(
    {
        "protocol_snapshot.json",
        "stage_a_plan.jsonl",
        "aggregate_assignments.jsonl",
        "stage_b_plan.jsonl",
        "source_files.json",
    }
)
PLAN_MANIFEST_FIELDS = frozenset(
    {
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
)
PLAN_FILE_RECORD_FIELDS = frozenset({"path", "bytes", "sha256"})
SOURCE_INVENTORY_FIELDS = frozenset(
    {"study_id", "protocol_version", "files", "prior_outcome_inputs"}
)
SOURCE_RECORD_FIELDS = frozenset(
    {"path", "bytes", "sha256", "outcome_bearing", "reuse_kind"}
)

# Possession of this in-process object is required to make a sub-maximal test
# receipt.  It is intentionally private, absent from the CLI, and impossible
# to reproduce by passing a string/environment variable in production.
_TEST_OVERRIDE_CAPABILITY = object()


class BenchmarkError(RuntimeError):
    """The storage benchmark could not establish its frozen contract."""


def _read_json(path: Path, label: str) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise BenchmarkError(f"{label} is not a real file: {path}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BenchmarkError(f"{label} is not readable JSON: {path}") from exc
    if not isinstance(value, dict):
        raise BenchmarkError(f"{label} is not a JSON object: {path}")
    return value


def _safe_relative_path(value: Any, label: str) -> PurePosixPath:
    if not isinstance(value, str) or not value:
        raise BenchmarkError(f"{label} is empty")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or path.as_posix() != value:
        raise BenchmarkError(f"{label} is not a canonical relative path")
    return path


def _positive_int(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise BenchmarkError(f"{label} is not a positive integer")
    return value


def _validate_plan(plan_dir: Path) -> tuple[dict[str, Any], str]:
    """Validate byte/hash bindings without interpreting any plan payload."""

    try:
        root = plan_dir.expanduser().resolve(strict=True)
    except OSError as exc:
        raise BenchmarkError(f"plan directory is unavailable: {plan_dir}") from exc
    if root.is_symlink() or not root.is_dir():
        raise BenchmarkError("plan directory is not a real directory")
    manifest = _read_json(root / "plan_manifest.json", "plan manifest")
    if set(manifest) != PLAN_MANIFEST_FIELDS:
        raise BenchmarkError("plan manifest schema differs")
    core = dict(manifest)
    supplied_hash = core.pop("plan_manifest_sha256", None)
    if supplied_hash != controls.canonical_sha256(core):
        raise BenchmarkError("plan manifest self-hash differs")
    if (
        manifest["schema_version"] != protocol.PLAN_SCHEMA_VERSION
        or manifest["study_id"] != protocol.STUDY_ID
        or manifest["protocol_version"] != protocol.PROTOCOL_VERSION
        or manifest["scope"]
        != "realization_and_target_free_vector_validation_only"
        or manifest["paper_prompt_render_count"] != 0
        or manifest["behavioral_replication_included"] is not False
        or manifest["stage_a_signed_edit_forward_count"]
        != protocol.RESOURCE_LIMITS["max_stage_a_edited_forwards"]
        or manifest["stage_b_edit_forward_count"]
        != protocol.RESOURCE_LIMITS["max_stage_b_edited_forwards"]
        or manifest["prior_outcome_inputs"] != []
    ):
        raise BenchmarkError("plan identity or target-free scope differs")
    records = manifest["files"]
    if not isinstance(records, list) or len(records) != len(PLAN_FILE_NAMES):
        raise BenchmarkError("plan file inventory differs")
    seen: set[str] = set()
    for index, record in enumerate(records):
        if not isinstance(record, Mapping) or set(record) != PLAN_FILE_RECORD_FIELDS:
            raise BenchmarkError(f"plan file record {index} schema differs")
        relative = _safe_relative_path(record["path"], f"plan file record {index}")
        if relative.as_posix() in seen:
            raise BenchmarkError("plan file inventory contains a duplicate")
        seen.add(relative.as_posix())
        path = root.joinpath(*relative.parts)
        expected_bytes = _positive_int(record["bytes"], f"plan file {relative} bytes")
        expected_hash = record["sha256"]
        if (
            not isinstance(expected_hash, str)
            or controls.HEX64.fullmatch(expected_hash) is None
            or path.is_symlink()
            or not path.is_file()
            or path.stat().st_size != expected_bytes
            or controls.sha256_file(path) != expected_hash
        ):
            raise BenchmarkError(f"plan file differs: {relative}")
    if seen != PLAN_FILE_NAMES:
        raise BenchmarkError("plan file names differ")

    # Parse only the outcome-free source inventory.  Every source is rehashed,
    # which binds the plan and the runner implementation without importing it.
    inventory = _read_json(root / "source_files.json", "source inventory")
    if set(inventory) != SOURCE_INVENTORY_FIELDS:
        raise BenchmarkError("source inventory schema differs")
    if (
        inventory["study_id"] != protocol.STUDY_ID
        or inventory["protocol_version"] != protocol.PROTOCOL_VERSION
        or inventory["prior_outcome_inputs"] != []
        or not isinstance(inventory["files"], list)
    ):
        raise BenchmarkError("source inventory identity differs")
    source_hashes: dict[str, str] = {}
    for index, record in enumerate(inventory["files"]):
        if not isinstance(record, Mapping) or set(record) != SOURCE_RECORD_FIELDS:
            raise BenchmarkError(f"source record {index} schema differs")
        relative = _safe_relative_path(record["path"], f"source record {index}")
        relative_text = relative.as_posix()
        if relative_text in source_hashes:
            raise BenchmarkError("source inventory contains a duplicate")
        expected_bytes = _positive_int(record["bytes"], f"source {relative} bytes")
        expected_hash = record["sha256"]
        source = REPO_ROOT.joinpath(*relative.parts)
        if (
            record["outcome_bearing"] is not False
            or not isinstance(record["reuse_kind"], str)
            or not record["reuse_kind"]
            or not isinstance(expected_hash, str)
            or controls.HEX64.fullmatch(expected_hash) is None
            or source.is_symlink()
            or not source.is_file()
            or source.stat().st_size != expected_bytes
            or controls.sha256_file(source) != expected_hash
        ):
            raise BenchmarkError(f"bound source differs: {relative}")
        source_hashes[relative_text] = expected_hash
    runner_hash = source_hashes.get(RUNNER_RELATIVE_PATH)
    if runner_hash is None:
        raise BenchmarkError("runner source is absent from the frozen source inventory")
    return dict(manifest), runner_hash


def _pattern(plan_hash: str, chunk_index: int, length: int) -> bytes:
    """Return dense, deterministic, incompressible-looking bytes for a chunk."""

    seed_material = (
        f"{protocol.STUDY_ID}:{plan_hash}:{chunk_index}:dense-storage-v1"
    ).encode("ascii")
    # SHAKE avoids the highly compressible repeated 32-byte seed pattern that
    # would under-exercise a compressed/deduplicating storage backend.  Memory
    # remains bounded by the frozen chunk size.
    return hashlib.shake_256(seed_material).digest(length)


def _expected_digest(plan_hash: str, length: int, *, chunk_bytes: int) -> str:
    digest = hashlib.sha256()
    offset = 0
    chunk_index = 0
    while offset < length:
        count = min(chunk_bytes, length - offset)
        digest.update(_pattern(plan_hash, chunk_index, count))
        offset += count
        chunk_index += 1
    return digest.hexdigest()


def _hash_file(path: Path, *, chunk_bytes: int) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(chunk_bytes):
            digest.update(chunk)
    return digest.hexdigest()


def _fsync_directory(path: Path) -> None:
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    descriptor = os.open(str(path), flags)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _filesystem_id(root: Path) -> str:
    stat = root.stat()
    statvfs = os.statvfs(root)
    descriptor = {
        "schema_version": 1,
        "st_dev": int(stat.st_dev),
        "f_fsid": int(getattr(statvfs, "f_fsid", stat.st_dev)),
        "f_bsize": int(statvfs.f_bsize),
        "f_frsize": int(statvfs.f_frsize),
    }
    return "posix-sha256:" + controls.canonical_sha256(descriptor)


def _benchmark_size(
    *, test_shard_bytes: int | None, test_capability: object | None
) -> int:
    maximum = int(protocol.RESOURCE_LIMITS["max_shard_bytes"])
    if test_shard_bytes is None and test_capability is None:
        return maximum
    if (
        test_capability is not _TEST_OVERRIDE_CAPABILITY
        or isinstance(test_shard_bytes, bool)
        or not isinstance(test_shard_bytes, int)
        or test_shard_bytes <= 1
        or test_shard_bytes >= maximum
    ):
        raise BenchmarkError("invalid private test-only shard override")
    return test_shard_bytes


def _write_receipt_atomic(output: Path, receipt: Mapping[str, Any]) -> Path:
    destination_input = output.expanduser().absolute()
    destination_input.parent.mkdir(parents=True, exist_ok=True)
    destination = destination_input.parent.resolve(strict=True) / destination_input.name
    if destination.exists() or destination.is_symlink():
        raise BenchmarkError(f"refusing to overwrite receipt: {destination}")
    temporary = destination.with_name(destination.name + ".partial")
    if temporary.exists() or temporary.is_symlink():
        raise BenchmarkError(f"partial receipt already exists: {temporary}")
    payload = controls.canonical_json_bytes(dict(receipt)) + b"\n"
    try:
        with temporary.open("xb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, destination)
        _fsync_directory(destination.parent)
        persisted = destination.read_bytes()
        if persisted != payload:
            raise BenchmarkError("persisted benchmark receipt bytes differ")
        controls.validate_storage_benchmark(json.loads(persisted))
    except BaseException:
        if temporary.exists() and not temporary.is_symlink():
            temporary.unlink()
        raise
    return destination


def run_benchmark(
    *,
    plan_dir: Path,
    volume_root: Path,
    volume_id: str,
    run_id: str,
    output: Path,
    chunk_bytes: int = 8 * 1024**2,
    _test_shard_bytes: int | None = None,
    _test_capability: object | None = None,
) -> dict[str, Any]:
    """Write, interrupt, resume, verify, atomically complete, then clean a shard."""

    if not isinstance(run_id, str) or controls.SAFE_RUN_ID.fullmatch(run_id) is None:
        raise BenchmarkError("benchmark run ID is unsafe")
    plan, runner_hash = _validate_plan(plan_dir)
    try:
        root = controls.require_volume_root(volume_root, volume_id=volume_id)
    except controls.ControlViolation as exc:
        raise BenchmarkError(str(exc)) from exc
    size = _benchmark_size(
        test_shard_bytes=_test_shard_bytes,
        test_capability=_test_capability,
    )
    if (
        isinstance(chunk_bytes, bool)
        or not isinstance(chunk_bytes, int)
        or chunk_bytes <= 0
        or size < 2 * chunk_bytes
    ):
        raise BenchmarkError("benchmark chunk size cannot exercise interruption/resume")

    benchmark_root = root / protocol.STUDY_SLUG / protocol.STUDY_ID / "storage_benchmark"
    partial = benchmark_root / f"{run_id}.payload.partial"
    complete = benchmark_root / f"{run_id}.payload.complete"
    quarantine = benchmark_root / f"{run_id}.payload.quarantine"
    destination_input = output.expanduser().absolute()
    output_parent = destination_input.parent.resolve(strict=False)
    try:
        output_parent.relative_to(benchmark_root.resolve(strict=False))
    except ValueError:
        pass
    else:
        raise BenchmarkError("benchmark receipt must be outside the disposable payload directory")

    if any(path.exists() or path.is_symlink() for path in (partial, complete, quarantine)):
        raise BenchmarkError("benchmark path is not fresh")
    benchmark_root.mkdir(parents=True, exist_ok=True)
    if benchmark_root.is_symlink() or not benchmark_root.is_dir():
        raise BenchmarkError("benchmark payload directory is unsafe")
    if benchmark_root.resolve(strict=True) != benchmark_root:
        raise BenchmarkError("benchmark payload directory contains a symlink")

    plan_hash = str(plan["plan_manifest_sha256"])
    # Align the interruption to a chunk boundary.  The second phase can then
    # reconstruct its exact generator position from only the fsynced file size,
    # just as it would after losing all in-memory state.
    interruption_offset = (size // 2 // chunk_bytes) * chunk_bytes
    if interruption_offset <= 0 or interruption_offset >= size:
        raise BenchmarkError("benchmark interruption boundary is invalid")
    peak_logical = 0
    peak_allocated = 0

    def observe(path: Path) -> None:
        nonlocal peak_logical, peak_allocated
        stat = path.stat()
        peak_logical = max(peak_logical, int(stat.st_size))
        peak_allocated = max(peak_allocated, int(stat.st_blocks) * 512)

    try:
        # Phase one: dense writes only--no seek, truncate, fallocate, or sparse
        # shortcut--followed by both file and directory durability barriers.
        with partial.open("xb") as handle:
            offset = 0
            while offset < interruption_offset:
                count = min(chunk_bytes, interruption_offset - offset)
                handle.write(_pattern(plan_hash, offset // chunk_bytes, count))
                offset += count
            handle.flush()
            os.fsync(handle.fileno())
        _fsync_directory(benchmark_root)
        observe(partial)

        # Simulated process interruption: reopen from disk, use st_size as the
        # only checkpoint, and independently reconstruct the expected prefix.
        resume_offset = partial.stat().st_size
        if resume_offset != interruption_offset:
            raise BenchmarkError("interrupted benchmark size differs")
        if _hash_file(partial, chunk_bytes=chunk_bytes) != _expected_digest(
            plan_hash, resume_offset, chunk_bytes=chunk_bytes
        ):
            raise BenchmarkError("interrupted prefix checksum differs")
        with partial.open("ab") as handle:
            offset = resume_offset
            while offset < size:
                count = min(chunk_bytes, size - offset)
                handle.write(_pattern(plan_hash, offset // chunk_bytes, count))
                offset += count
            handle.flush()
            os.fsync(handle.fileno())
        observe(partial)
        if partial.stat().st_size != size:
            raise BenchmarkError("resumed benchmark shard size differs")

        expected_digest = _expected_digest(plan_hash, size, chunk_bytes=chunk_bytes)
        observed_digest = _hash_file(partial, chunk_bytes=chunk_bytes)
        if observed_digest != expected_digest:
            raise BenchmarkError("completed benchmark checksum differs")
        if peak_logical != size or peak_allocated < size:
            raise BenchmarkError("benchmark payload was not densely allocated")

        os.replace(partial, complete)
        _fsync_directory(benchmark_root)
        observe(complete)
        if _hash_file(complete, chunk_bytes=chunk_bytes) != expected_digest:
            raise BenchmarkError("atomically completed benchmark checksum differs")

        workload = {
            "schema_version": 1,
            "actual_shard_bytes": size,
            "production_max_shard_bytes": int(
                protocol.RESOURCE_LIMITS["max_shard_bytes"]
            ),
            "chunk_bytes": chunk_bytes,
            "interruption_offset": interruption_offset,
            "dense_write": True,
            "write_pattern": "shake_256_unique_seed_per_aligned_chunk",
            "resume_checkpoint": "fsynced_partial_st_size",
            "atomic_completion": "os.replace_then_directory_fsync",
            "post_replace_checksum": "sha256_full_payload",
        }
        core = {
            "schema_version": controls.CONTROL_SCHEMA_VERSION,
            "status": "pass",
            "study_id": protocol.STUDY_ID,
            "protocol_version": protocol.PROTOCOL_VERSION,
            "run_id": run_id,
            "plan_manifest_sha256": plan_hash,
            "runner_source_sha256": runner_hash,
            # The fixture hash is the independently reconstructed digest of the
            # actual target-free payload, not a hash of the target-bearing
            # protocol snapshot.
            "target_blind_fixture_sha256": expected_digest,
            "filesystem_id": _filesystem_id(root),
            "maximum_workload_signature_sha256": controls.canonical_sha256(
                workload
            ),
            # This storage-only receipt is evidence about the filesystem, not
            # authority to load a model or execute a prompt.  Smoke and Stage A
            # require the separate machine-produced preexecution receipt.
            "execution_authorization_status": "not_evaluated_storage_only",
            "model_execution_authorized": False,
            "interruption_resume_exercised": True,
            "checksum_pass": True,
            "observed_peak_allocated_bytes": peak_allocated,
            "observed_peak_logical_bytes": peak_logical,
            "model_forward_count": 0,
            "target_prompt_render_count": 0,
            "target_forward_count": 0,
            "target_outcome_count": 0,
            "prior_outcome_inputs": [],
        }
        receipt = {**core, "receipt_sha256": controls.canonical_sha256(core)}
        controls.validate_storage_benchmark(receipt)
        _write_receipt_atomic(output, receipt)

        # Preserve and verify the compact receipt first, then remove the full
        # disposable payload and durably record that deletion.
        complete.unlink()
        _fsync_directory(benchmark_root)
        if any(path.exists() or path.is_symlink() for path in (partial, complete, quarantine)):
            raise BenchmarkError("benchmark payload cleanup did not complete")
        try:
            benchmark_root.rmdir()
        except OSError:
            # Another fresh benchmark may share the directory.  This run's
            # payload is still proven absent by the exact path checks above.
            pass
        else:
            _fsync_directory(benchmark_root.parent)
        return receipt
    except BaseException:
        # A failed artifact is never resumable by a later benchmark.  Quarantine
        # it under this unique run ID for explicit diagnosis/cleanup.
        if partial.exists() and not quarantine.exists():
            os.replace(partial, quarantine)
            _fsync_directory(benchmark_root)
        elif complete.exists() and not quarantine.exists():
            os.replace(complete, quarantine)
            _fsync_directory(benchmark_root)
        raise


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan-dir", type=Path, required=True)
    parser.add_argument("--volume-root", type=Path, required=True)
    parser.add_argument("--volume-id", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    receipt = run_benchmark(
        plan_dir=args.plan_dir,
        volume_root=args.volume_root,
        volume_id=args.volume_id,
        run_id=args.run_id,
        output=args.output,
    )
    print(receipt["receipt_sha256"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

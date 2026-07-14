"""Freshly stage the pilot's pinned public artifacts on its network volume.

This command performs no model load or model forward.  It resolves every
Hugging Face repository at the frozen commit, computes the exact remote byte
budget before downloading, rejects insufficient free space, downloads into one
study-specific partial directory, removes Hugging Face local-cache metadata,
rejects symlinks, hashes every retained byte, and atomically publishes one
self-hashed staging receipt.  Interrupted partial directories are never read by
the runner; an explicit ``--resume-partial`` is required to resume transport.
"""

from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import os
import shutil
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path, PurePosixPath
from typing import Any

from . import guest_attestation, paths, protocol, runtime


STAGING_SCHEMA_VERSION = 1
STAGING_RECEIPT_FILENAME = "STAGING_RECEIPT.json"
MIN_STAGE_HEADROOM_BYTES = 40 * 1024**3
MIN_FINAL_FREE_BYTES = 32 * 1024**3
MODEL_EXCLUDED_PATTERNS = ("original/*", "original/**")
HASH_CHUNK_BYTES = 8 * 1024**2


class StagingError(RuntimeError):
    """Raised before publication when public-artifact staging is unsafe."""


def _write_exclusive_json(path: Path, value: Mapping[str, Any]) -> None:
    with path.open("xb") as handle:
        handle.write(protocol.canonical_json_bytes(dict(value)) + b"\n")
        handle.flush()
        os.fsync(handle.fileno())
    directory_fd = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)


def _safe_external_root(root: Path) -> Path:
    if root.is_symlink():
        raise StagingError("artifact root may not be a symlink")
    resolved = root.expanduser().resolve(strict=True)
    if not resolved.is_dir():
        raise StagingError("artifact root must be a directory")
    try:
        resolved.relative_to(paths.REPO_ROOT.resolve(strict=True))
    except ValueError:
        pass
    else:
        raise StagingError("artifact root must be outside the repository")
    return resolved


def initialize_or_validate_volume(root: Path, *, volume_id: str) -> Path:
    """Create the study sentinel once, or validate its exact identity."""

    if not volume_id or not runtime.SAFE_RUN_ID.fullmatch(volume_id):
        raise StagingError("volume ID is invalid")
    resolved = _safe_external_root(root)
    sentinel_path = resolved / paths.VOLUME_SENTINEL
    expected = {
        "schema_version": 1,
        "study_slug": protocol.STUDY_SLUG,
        "study_id": protocol.STUDY_ID,
        "volume_id": volume_id,
    }
    if sentinel_path.exists() or sentinel_path.is_symlink():
        if sentinel_path.is_symlink() or not sentinel_path.is_file():
            raise StagingError("volume sentinel is not a regular file")
        try:
            observed = json.loads(sentinel_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise StagingError("volume sentinel is invalid") from exc
        if observed != expected:
            raise StagingError("volume sentinel differs from this pilot")
    else:
        _write_exclusive_json(sentinel_path, expected)
    return paths.require_external_artifact_root(
        resolved, expected_volume_id=volume_id
    )


def _ensure_safe_directory_chain(root: Path, parts: Sequence[str]) -> Path:
    """Create/check a direct directory chain without following child symlinks."""

    current = root
    resolved_root = root.resolve(strict=True)
    for part in parts:
        if not part or part in {".", ".."} or "/" in part or "\\" in part:
            raise StagingError("unsafe staging directory component")
        candidate = current / part
        if candidate.exists() or candidate.is_symlink():
            if candidate.is_symlink() or not candidate.is_dir():
                raise StagingError("staging directory chain contains an unsafe entry")
        else:
            candidate.mkdir(mode=0o700)
        try:
            candidate.resolve(strict=True).relative_to(resolved_root)
        except ValueError as exc:
            raise StagingError("staging directory chain escapes the artifact root") from exc
        current = candidate
    return current


def _validate_remote_path(path: str) -> PurePosixPath:
    if (
        not path
        or path.startswith("/")
        or path.endswith("/")
        or "//" in path
        or "\\" in path
        or any(ord(character) < 32 for character in path)
    ):
        raise StagingError("remote repository file path is unsafe")
    parsed = PurePosixPath(path)
    if parsed.is_absolute() or any(part in {"", ".", ".."} for part in parsed.parts):
        raise StagingError("remote repository file path is unsafe")
    return parsed


def _is_excluded_model_path(path: str) -> bool:
    return any(fnmatch.fnmatchcase(path, pattern) for pattern in MODEL_EXCLUDED_PATTERNS)


def _normalize_remote_info(value: Mapping[str, Any], *, expected_revision: str) -> dict[str, Any]:
    revision = value.get("revision")
    raw_files = value.get("files")
    if revision != expected_revision or not isinstance(raw_files, Sequence):
        raise StagingError("remote repository identity differs from the frozen revision")
    files: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in raw_files:
        if not isinstance(raw, Mapping):
            raise StagingError("remote repository file inventory is malformed")
        path = raw.get("path")
        size = raw.get("size")
        if (
            not isinstance(path, str)
            or path in seen
            or isinstance(size, bool)
            or not isinstance(size, int)
            or size < 0
        ):
            raise StagingError("remote repository file record is unsafe")
        _validate_remote_path(path)
        sha256 = raw.get("sha256")
        blob_id = raw.get("blob_id")
        if sha256 is not None and (
            not isinstance(sha256, str)
            or len(sha256) != 64
            or any(character not in "0123456789abcdef" for character in sha256)
        ):
            raise StagingError("remote repository SHA-256 metadata is malformed")
        if blob_id is not None and (
            not isinstance(blob_id, str)
            or len(blob_id) not in {40, 64}
            or any(character not in "0123456789abcdef" for character in blob_id)
        ):
            raise StagingError("remote repository blob metadata is malformed")
        if sha256 is None and blob_id is None:
            raise StagingError("remote repository file lacks a byte-identity verifier")
        seen.add(path)
        record = {"path": path, "size": size}
        if sha256 is not None:
            record["sha256"] = sha256
        else:
            record["blob_id"] = blob_id
        files.append(record)
    if not files:
        raise StagingError("remote repository file inventory is empty")
    return {"revision": revision, "files": files}


def _selected_remote_files(
    info: Mapping[str, Any], *, wanted: Sequence[str] | None = None, exclude_model_original: bool = False
) -> list[dict[str, Any]]:
    files = [dict(row) for row in info["files"]]
    if wanted is not None:
        indexed = {str(row["path"]): row for row in files}
        missing = [name for name in wanted if name not in indexed]
        if missing:
            raise StagingError(f"frozen remote files are absent: {missing}")
        return [dict(indexed[name]) for name in wanted]
    if exclude_model_original:
        files = [row for row in files if not _is_excluded_model_path(str(row["path"]))]
    if not files:
        raise StagingError("selected remote file inventory is empty")
    return sorted(files, key=lambda row: str(row["path"]))


def _remove_hub_metadata(root: Path) -> None:
    caches = sorted(
        (candidate for candidate in root.rglob(".cache") if candidate.is_dir()),
        key=lambda candidate: len(candidate.parts),
        reverse=True,
    )
    for cache in caches:
        if cache.is_symlink():
            raise StagingError("Hugging Face cache metadata is a symlink")
        shutil.rmtree(cache)


def _assert_regular_tree(root: Path) -> None:
    if root.is_symlink() or not root.is_dir():
        raise StagingError(f"staged path is not a safe directory: {root}")
    for candidate in root.rglob("*"):
        if candidate.is_symlink():
            raise StagingError(f"staged symlink is forbidden: {candidate}")
        if not candidate.is_dir() and not candidate.is_file():
            raise StagingError(f"staged entry is not regular: {candidate}")


def _sha256_and_reject_secret(path: Path, *, forbidden_secret: bytes) -> str:
    digest = hashlib.sha256()
    overlap = b""
    keep = max(0, len(forbidden_secret) - 1)
    with path.open("rb") as handle:
        while chunk := handle.read(HASH_CHUNK_BYTES):
            digest.update(chunk)
            window = overlap + chunk
            if forbidden_secret in window:
                raise StagingError("credential bytes appeared in a staged public artifact")
            overlap = window[-keep:] if keep else b""
    return digest.hexdigest()


def _local_inventory(root: Path, *, forbidden_secret: bytes) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for candidate in sorted(root.rglob("*"), key=lambda value: value.relative_to(root).as_posix()):
        if candidate.is_dir():
            continue
        if candidate.is_symlink() or not candidate.is_file():
            raise StagingError("local artifact inventory contains an unsafe entry")
        rows.append(
            {
                "path": candidate.relative_to(root).as_posix(),
                "bytes": candidate.stat().st_size,
                "sha256": _sha256_and_reject_secret(
                    candidate, forbidden_secret=forbidden_secret
                ),
            }
        )
    if not rows:
        raise StagingError("local artifact inventory is empty")
    return rows


def _verify_model_snapshot(model_root: Path, expected_remote: Sequence[Mapping[str, Any]]) -> None:
    expected_sizes = {str(row["path"]): int(row["size"]) for row in expected_remote}
    observed_sizes = {
        candidate.relative_to(model_root).as_posix(): candidate.stat().st_size
        for candidate in model_root.rglob("*")
        if candidate.is_file()
    }
    observed_paths = set(observed_sizes)
    if observed_sizes != expected_sizes:
        raise StagingError("model snapshot file inventory differs from the pinned remote tree")
    if any(_is_excluded_model_path(path) for path in observed_paths):
        raise StagingError("excluded original-format model weights were staged")
    required = {
        "config.json",
        "model.safetensors.index.json",
        "tokenizer.json",
        "tokenizer_config.json",
    }
    if not required <= observed_paths:
        raise StagingError("model snapshot lacks a required Transformers artifact")
    try:
        index = json.loads((model_root / "model.safetensors.index.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise StagingError("model weight index is invalid") from exc
    weight_map = index.get("weight_map")
    if not isinstance(weight_map, Mapping) or not weight_map:
        raise StagingError("model weight map is missing")
    required_weights = {str(name) for name in weight_map.values()}
    if not required_weights <= observed_paths:
        raise StagingError("model snapshot is missing an indexed weight shard")


def _git_blob_id(path: Path, *, algorithm: str) -> str:
    size = path.stat().st_size
    digest = hashlib.new(algorithm)
    digest.update(f"blob {size}\0".encode("ascii"))
    with path.open("rb") as handle:
        while chunk := handle.read(HASH_CHUNK_BYTES):
            digest.update(chunk)
    return digest.hexdigest()


def _verify_remote_byte_identities(
    partial: Path,
    *,
    selected: Mapping[str, Sequence[Mapping[str, Any]]],
    local_paths: Mapping[str, Callable[[str], str]],
    inventory: Sequence[Mapping[str, Any]],
) -> None:
    indexed = {str(row["path"]): row for row in inventory}
    for repository_name, rows in selected.items():
        mapper = local_paths[repository_name]
        for remote in rows:
            local_relative = mapper(str(remote["path"]))
            observed = indexed.get(local_relative)
            if observed is None or int(observed["bytes"]) != int(remote["size"]):
                raise StagingError("staged bytes differ from the resolved remote inventory")
            if "sha256" in remote:
                if observed["sha256"] != remote["sha256"]:
                    raise StagingError("staged SHA-256 differs from Hugging Face metadata")
            else:
                blob_id = str(remote["blob_id"])
                algorithm = "sha1" if len(blob_id) == 40 else "sha256"
                if _git_blob_id(partial / local_relative, algorithm=algorithm) != blob_id:
                    raise StagingError("staged Git blob identity differs from Hugging Face metadata")


def _verify_exact_partial_layout(partial: Path, expected_files: Sequence[str]) -> None:
    observed = {
        candidate.relative_to(partial).as_posix()
        for candidate in partial.rglob("*")
        if candidate.is_file()
    }
    if observed != set(expected_files):
        raise StagingError("partial staging contains missing or unplanned files")


def _move_flattened(source: Path, destination: Path) -> None:
    if source.is_symlink() or not source.is_file():
        raise StagingError("downloaded public artifact is not a regular file")
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() or destination.is_symlink():
        if destination.is_symlink() or not destination.is_file():
            raise StagingError("resumed artifact destination is unsafe")
        if runtime.sha256_file(source) != runtime.sha256_file(destination):
            raise StagingError("resumed artifact bytes differ")
        source.unlink()
    else:
        os.replace(source, destination)


def _sidecar_files(spec: Mapping[str, Any]) -> tuple[str, ...]:
    raw = spec.get("sidecars")
    if not isinstance(raw, Mapping) or set(raw) != {"readme", "config"}:
        raise StagingError("release-sidecar contract is malformed")
    names: list[str] = []
    for name in ("readme", "config"):
        row = raw[name]
        if not isinstance(row, Mapping) or not isinstance(row.get("filename"), str):
            raise StagingError("release-sidecar record is malformed")
        names.append(str(row["filename"]))
    return tuple(names)


def _expected_file_sha(spec: Mapping[str, Any], filename: str) -> str:
    if filename == spec.get("filename"):
        return str(spec["sha256"])
    sidecars = spec.get("sidecars")
    if not isinstance(sidecars, Mapping):
        raise StagingError("release-sidecar contract is malformed")
    for row in sidecars.values():
        if row.get("filename") == filename:
            return str(row["sha256"])
    raise StagingError(f"no frozen SHA-256 exists for {filename}")


def stage_public_artifacts(
    *,
    artifact_root: Path,
    volume_id: str,
    owned_pod_id: str,
    data_center_id: str,
    guest_attestation_receipt: Path,
    token: str,
    resolve_remote: Callable[[str, str, str], Mapping[str, Any]],
    snapshot_download: Callable[..., str],
    hub_download: Callable[..., str],
    resume_partial: bool = False,
    attestation_validator: Callable[..., Mapping[str, Any]] = (
        guest_attestation.validate_guest_attestation_receipt
    ),
    disk_usage: Callable[[Path], Any] = shutil.disk_usage,
    min_stage_headroom_bytes: int = MIN_STAGE_HEADROOM_BYTES,
    min_final_free_bytes: int = MIN_FINAL_FREE_BYTES,
) -> Path:
    """Download, verify, and atomically publish the exact public-artifact set."""

    if not token:
        raise StagingError("HF token is required but must not be passed on the command line")
    token_bytes = token.encode("utf-8")
    if len(token_bytes) < 8 or any(character.isspace() for character in token):
        raise StagingError("HF token format is invalid")
    try:
        attestation = dict(
            attestation_validator(
                guest_attestation_receipt,
                expected_owned_pod_id=owned_pod_id,
                expected_volume_id=volume_id,
                expected_data_center_id=data_center_id,
                expected_artifact_root=artifact_root,
            )
        )
    except guest_attestation.GuestAttestationError as exc:
        raise StagingError(f"guest attestation failed: {exc}") from exc
    attestation_hash = attestation.get("receipt_sha256")
    if (
        not isinstance(attestation_hash, str)
        or len(attestation_hash) != 64
        or any(character not in "0123456789abcdef" for character in attestation_hash)
    ):
        raise StagingError("validated guest-attestation receipt hash is malformed")
    repository_source_root_sha256 = attestation.get(
        "repository_source_root_sha256"
    )
    if (
        not isinstance(repository_source_root_sha256, str)
        or len(repository_source_root_sha256) != 64
        or any(
            character not in "0123456789abcdef"
            for character in repository_source_root_sha256
        )
    ):
        raise StagingError("validated repository source-root hash is malformed")
    stage_python_launch_contract = attestation.get("stage_python_launch_contract")
    if stage_python_launch_contract != guest_attestation.expected_python_launch_contract(
        guest_attestation.STAGE_PUBLIC_ARTIFACTS_MODULE
    ):
        raise StagingError("validated staging Python launch contract differs")
    root = initialize_or_validate_volume(artifact_root, volume_id=volume_id)
    namespace = _ensure_safe_directory_chain(
        root, (protocol.STUDY_SLUG, protocol.STUDY_ID)
    )
    final = namespace / "public_artifacts"
    partial = namespace / "public_artifacts.partial"
    if final.exists() or final.is_symlink():
        raise StagingError("public artifacts already exist; overwrite is forbidden")
    partial_exists = partial.exists() or partial.is_symlink()
    if partial_exists:
        if not resume_partial or partial.is_symlink() or not partial.is_dir():
            raise StagingError("partial staging exists; explicit safe resume is required")
        _assert_regular_tree(partial)

    specs = {
        "model": protocol.MODEL_SPEC,
        "sae": protocol.SAE_SPEC,
        "j_lens": protocol.J_LENS_SPEC,
    }
    remote: dict[str, dict[str, Any]] = {}
    for name, spec in specs.items():
        resolved = resolve_remote(str(spec["repository"]), str(spec["revision"]), token)
        remote[name] = _normalize_remote_info(resolved, expected_revision=str(spec["revision"]))

    model_files = _selected_remote_files(remote["model"], exclude_model_original=True)
    sae_wanted = (str(protocol.SAE_SPEC["filename"]), *_sidecar_files(protocol.SAE_SPEC))
    sae_files = _selected_remote_files(remote["sae"], wanted=sae_wanted)
    j_wanted = (
        str(protocol.J_LENS_SPEC["filename"]),
        str(protocol.J_LENS_SPEC["release_config"]["filename"]),
    )
    j_files = _selected_remote_files(remote["j_lens"], wanted=j_wanted)
    expected_download_bytes = sum(
        int(row["size"]) for row in (*model_files, *sae_files, *j_files)
    )
    free_before = int(disk_usage(root).free)
    if free_before < expected_download_bytes + int(min_stage_headroom_bytes):
        raise StagingError(
            "insufficient free space for exact public artifacts plus frozen staging headroom"
        )
    free_samples = [{"stage": "before_download", "free_bytes": free_before}]
    if not partial_exists:
        partial.mkdir(mode=0o700)

    model_root = _ensure_safe_directory_chain(partial, ("model_snapshot",))
    snapshot_download(
        repo_id=protocol.MODEL_SPEC["repository"],
        revision=protocol.MODEL_SPEC["revision"],
        token=token,
        local_dir=model_root,
        allow_patterns=tuple(str(row["path"]) for row in model_files),
        max_workers=4,
    )
    _remove_hub_metadata(model_root)
    _assert_regular_tree(model_root)
    _verify_model_snapshot(model_root, model_files)
    free_samples.append({"stage": "after_model", "free_bytes": int(disk_usage(root).free)})

    sae_root = _ensure_safe_directory_chain(partial, ("sae",))
    for filename in sae_wanted:
        expected_remote = next(row for row in sae_files if row["path"] == filename)
        downloaded = Path(
            hub_download(
                repo_id=protocol.SAE_SPEC["repository"],
                filename=filename,
                revision=protocol.SAE_SPEC["revision"],
                token=token,
                local_dir=sae_root,
            )
        )
        expected_path = sae_root / filename
        if downloaded.resolve(strict=True) != expected_path.resolve(strict=True):
            raise StagingError("SAE download path differs from its frozen filename")
        if expected_path.stat().st_size != int(expected_remote["size"]):
            raise StagingError(f"SAE artifact size differs: {filename}")
    _remove_hub_metadata(sae_root)
    free_samples.append({"stage": "after_sae", "free_bytes": int(disk_usage(root).free)})

    j_upstream = _ensure_safe_directory_chain(partial, ("jlens_upstream",))
    j_root = _ensure_safe_directory_chain(partial, ("jlens",))
    for filename in j_wanted:
        expected_remote = next(row for row in j_files if row["path"] == filename)
        downloaded = Path(
            hub_download(
                repo_id=protocol.J_LENS_SPEC["repository"],
                filename=filename,
                revision=protocol.J_LENS_SPEC["revision"],
                token=token,
                local_dir=j_upstream,
            )
        )
        local_name = "config.yaml" if filename.endswith("/config.yaml") else Path(filename).name
        _move_flattened(downloaded, j_root / local_name)
        if (j_root / local_name).stat().st_size != int(expected_remote["size"]):
            raise StagingError(f"J-lens artifact size differs: {filename}")
    shutil.rmtree(j_upstream)
    free_samples.append({"stage": "after_j_lens", "free_bytes": int(disk_usage(root).free)})

    _remove_hub_metadata(partial)
    _assert_regular_tree(partial)
    expected_local_files = [f"model_snapshot/{row['path']}" for row in model_files]
    expected_local_files.extend(f"sae/{name}" for name in sae_wanted)
    expected_local_files.extend(
        (
            f"jlens/{Path(str(protocol.J_LENS_SPEC['filename'])).name}",
            "jlens/config.yaml",
        )
    )
    _verify_exact_partial_layout(partial, expected_local_files)
    if hasattr(os, "sync"):
        os.sync()
    inventory = _local_inventory(partial, forbidden_secret=token_bytes)
    indexed_inventory = {str(row["path"]): row for row in inventory}
    for filename in sae_wanted:
        observed = indexed_inventory[f"sae/{filename}"]
        if observed["sha256"] != _expected_file_sha(protocol.SAE_SPEC, filename):
            raise StagingError(f"SAE artifact SHA-256 differs: {filename}")
    expected_j_hashes = {
        f"jlens/{Path(str(protocol.J_LENS_SPEC['filename'])).name}": str(
            protocol.J_LENS_SPEC["sha256"]
        ),
        "jlens/config.yaml": str(protocol.J_LENS_SPEC["release_config"]["sha256"]),
    }
    for name, sha256 in expected_j_hashes.items():
        if indexed_inventory[name]["sha256"] != sha256:
            raise StagingError(f"J-lens artifact SHA-256 differs: {name}")
    _verify_remote_byte_identities(
        partial,
        selected={"model": model_files, "sae": sae_files, "j_lens": j_files},
        local_paths={
            "model": lambda remote_path: f"model_snapshot/{remote_path}",
            "sae": lambda remote_path: f"sae/{remote_path}",
            "j_lens": lambda remote_path: (
                "jlens/config.yaml"
                if remote_path.endswith("/config.yaml")
                else f"jlens/{Path(remote_path).name}"
            ),
        },
        inventory=inventory,
    )
    retained_bytes = sum(int(row["bytes"]) for row in inventory)
    if retained_bytes != expected_download_bytes:
        raise StagingError("retained byte count differs from the exact remote byte budget")
    free_final = int(disk_usage(root).free)
    free_samples.append({"stage": "after_hashing", "free_bytes": free_final})
    if free_final < int(min_final_free_bytes):
        raise StagingError("final free-space reserve is below the frozen minimum")

    core = {
        "schema_version": STAGING_SCHEMA_VERSION,
        "status": "pass",
        "receipt_kind": "fresh_public_artifact_staging_v1",
        "study_id": protocol.STUDY_ID,
        "protocol_version": protocol.PROTOCOL_VERSION,
        "owned_pod_id": owned_pod_id,
        "volume_id": volume_id,
        "data_center_id": data_center_id,
        "guest_attestation_receipt_sha256": attestation_hash,
        "repository_source_root_sha256": repository_source_root_sha256,
        "stage_python_launch_contract": stage_python_launch_contract,
        "resumed_partial": bool(resume_partial),
        "repositories": {
            name: {
                "repository": specs[name]["repository"],
                "revision": specs[name]["revision"],
                "remote_revision_verified": remote[name]["revision"],
            }
            for name in ("model", "sae", "j_lens")
        },
        "selected_remote_inventories": {
            name: {
                "file_count": len(rows),
                "bytes": sum(int(row["size"]) for row in rows),
                "canonical_sha256": protocol.canonical_sha256(rows),
            }
            for name, rows in (
                ("model", model_files),
                ("sae", sae_files),
                ("j_lens", j_files),
            )
        },
        "model_excluded_patterns": MODEL_EXCLUDED_PATTERNS,
        "expected_download_bytes": expected_download_bytes,
        "retained_bytes": retained_bytes,
        "free_space_samples": free_samples,
        "min_stage_headroom_bytes": int(min_stage_headroom_bytes),
        "min_final_free_bytes": int(min_final_free_bytes),
        "files": inventory,
        "file_inventory_sha256": protocol.canonical_sha256(inventory),
        "model_weights_loaded": False,
        "model_forward_count": 0,
        "prior_outcome_inputs": [],
        "target_prompt_inputs": [],
        "target_outcome_inputs": [],
    }
    _write_exclusive_json(
        partial / STAGING_RECEIPT_FILENAME,
        {**core, "receipt_sha256": protocol.canonical_sha256(core)},
    )
    os.replace(partial, final)
    directory_fd = os.open(namespace, os.O_RDONLY)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)
    return final


def _remote_resolver(api: Any) -> Callable[[str, str, str], Mapping[str, Any]]:
    def resolve(repository: str, revision: str, token: str) -> Mapping[str, Any]:
        info = api.model_info(
            repo_id=repository,
            revision=revision,
            token=token,
            files_metadata=True,
        )
        files: list[dict[str, Any]] = []
        for sibling in info.siblings:
            lfs = getattr(sibling, "lfs", None)
            if isinstance(lfs, Mapping):
                lfs_sha256 = lfs.get("sha256")
            else:
                lfs_sha256 = getattr(lfs, "sha256", None)
            record = {
                "path": str(sibling.rfilename),
                "size": int(sibling.size),
            }
            if lfs_sha256:
                record["sha256"] = str(lfs_sha256)
            else:
                record["blob_id"] = str(sibling.blob_id)
            files.append(record)
        return {
            "revision": str(info.sha),
            "files": files,
        }

    return resolve


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--owned-pod-id", required=True)
    parser.add_argument("--volume-id", required=True)
    parser.add_argument("--data-center-id", required=True)
    parser.add_argument("--guest-attestation-receipt", type=Path, required=True)
    parser.add_argument("--resume-partial", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    token = os.environ.get("HF_TOKEN", "")
    try:
        from huggingface_hub import HfApi, hf_hub_download, snapshot_download
    except ImportError as exc:  # pragma: no cover - deployment dependency
        raise StagingError("pinned huggingface-hub is required") from exc
    output = stage_public_artifacts(
        artifact_root=args.artifact_root,
        owned_pod_id=args.owned_pod_id,
        volume_id=args.volume_id,
        data_center_id=args.data_center_id,
        guest_attestation_receipt=args.guest_attestation_receipt,
        token=token,
        resolve_remote=_remote_resolver(HfApi()),
        snapshot_download=snapshot_download,
        hub_download=hf_hub_download,
        resume_partial=bool(args.resume_partial),
    )
    print(str(output))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

"""Fail-closed path policy for the consciousness SAE changepoint study."""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from pathlib import Path


STUDY_SLUG = "consciousness_sae_changepoint"
REPO_ROOT = Path(__file__).resolve().parents[2]
CODE_ROOT = REPO_ROOT / "experiments" / STUDY_SLUG
DOCS_ROOT = REPO_ROOT / "docs" / STUDY_SLUG
DATA_ROOT = REPO_ROOT / "data" / STUDY_SLUG
OUT_ROOT = REPO_ROOT / "out" / STUDY_SLUG
TESTS_ROOT = REPO_ROOT / "tests" / STUDY_SLUG

ARTIFACT_ROOT_ENV = "CONSCIOUSNESS_SAE_ARTIFACT_ROOT"
ARTIFACT_VOLUME_ID_ENV = "CONSCIOUSNESS_SAE_VOLUME_ID"
ARTIFACT_VOLUME_SENTINEL = ".consciousness_sae_volume.json"
MIN_ARTIFACT_FREE_BYTES = 150 * 1024**3
MIN_ARTIFACT_VOLUME_SIZE_GB = 500

READ_ONLY_UPSTREAM_ROOTS = (
    REPO_ROOT / "experiments" / "exp2_sae",
    REPO_ROOT / "data" / "public_sae_consciousness_gating",
    REPO_ROOT / "data" / "sae_jlens_audit",
)


class UnsafeOutputPath(ValueError):
    """Raised when a requested destination violates the study isolation policy."""


def _unique_logical_bytes(root: Path) -> int:
    """Count allocated study files once by resolved inode without reading content."""

    total = 0
    seen: set[tuple[int, int]] = set()
    for path in root.rglob("*"):
        try:
            stat = path.stat()
        except OSError as exc:
            raise UnsafeOutputPath(f"cannot inventory external artifact path: {path}") from exc
        if not path.is_file():
            continue
        identity = (stat.st_dev, stat.st_ino)
        if identity in seen:
            continue
        seen.add(identity)
        total += stat.st_size
    return total


def _resolved(path: str | Path) -> Path:
    candidate = Path(path).expanduser()
    if not candidate.is_absolute():
        candidate = REPO_ROOT / candidate
    return candidate.resolve(strict=False)


def _is_beneath(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root.resolve(strict=False))
    except ValueError:
        return False
    return True


def _reject_repo_or_upstream(path: Path) -> None:
    repo_root = REPO_ROOT.resolve(strict=False)
    if path == repo_root or _is_beneath(path, repo_root):
        raise UnsafeOutputPath(
            f"external artifact root must resolve outside the Git checkout: {path}"
        )

    for upstream_root in READ_ONLY_UPSTREAM_ROOTS:
        resolved_upstream = upstream_root.resolve(strict=False)
        if path == resolved_upstream or _is_beneath(path, resolved_upstream):
            raise UnsafeOutputPath(
                f"output path is inside read-only upstream data/code: {path}"
            )


def require_external_artifact_root(
    root: str | Path | None = None,
    *,
    minimum_free_bytes: int = MIN_ARTIFACT_FREE_BYTES,
    minimum_volume_size_gb: int = MIN_ARTIFACT_VOLUME_SIZE_GB,
    minimum_logical_reserve_bytes: int | None = None,
    expected_volume_id: str | None = None,
    write_read_probe: bool = False,
) -> Path:
    """Validate the persistent external root for outcome-bearing artifacts.

    The caller must explicitly pass ``root`` or set
    ``CONSCIOUSNESS_SAE_ARTIFACT_ROOT``. The root is study-specific, exists
    outside the repository, carries the persistent-volume sentinel, and has the
    requested free-space reserve. There is deliberately no local fallback.
    """

    configured = root if root is not None else os.environ.get(ARTIFACT_ROOT_ENV)
    if not configured:
        raise UnsafeOutputPath(
            f"{ARTIFACT_ROOT_ENV} is required for outcome-bearing jobs; "
            "no local fallback is permitted"
        )

    candidate = Path(configured).expanduser().resolve(strict=False)
    _reject_repo_or_upstream(candidate)
    if not candidate.exists() or not candidate.is_dir():
        raise UnsafeOutputPath(
            f"external artifact root must already exist as a directory: {candidate}"
        )

    sentinel_path = candidate / ARTIFACT_VOLUME_SENTINEL
    try:
        sentinel = json.loads(sentinel_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise UnsafeOutputPath(
            f"missing or invalid external-volume sentinel {sentinel_path}"
        ) from exc

    volume_id = sentinel.get("volume_id")
    volume_size_gb = sentinel.get("volume_size_gb")
    sentinel_study = sentinel.get("study_slug")
    if not isinstance(volume_id, str) or not volume_id.strip():
        raise UnsafeOutputPath("external-volume sentinel has no non-empty volume_id")
    if sentinel_study != STUDY_SLUG:
        raise UnsafeOutputPath(
            "external-volume sentinel study_slug does not match "
            f"{STUDY_SLUG!r}: {sentinel_study!r}"
        )
    if (
        isinstance(volume_size_gb, bool)
        or not isinstance(volume_size_gb, int)
        or volume_size_gb < minimum_volume_size_gb
    ):
        raise UnsafeOutputPath(
            "external-volume sentinel does not prove the frozen volume-size floor: "
            f"required_gb={minimum_volume_size_gb}, sentinel_gb={volume_size_gb!r}"
        )

    frozen_volume_id = (
        expected_volume_id
        if expected_volume_id is not None
        else os.environ.get(ARTIFACT_VOLUME_ID_ENV)
    )
    if frozen_volume_id and volume_id != frozen_volume_id:
        raise UnsafeOutputPath(
            f"external volume_id mismatch: expected {frozen_volume_id!r}, "
            f"got {volume_id!r}"
        )

    free_bytes = shutil.disk_usage(candidate).free
    if free_bytes < minimum_free_bytes:
        raise UnsafeOutputPath(
            "external artifact root lacks the required free-space reserve: "
            f"required={minimum_free_bytes}, available={free_bytes}"
        )

    # RunPod mounts network volumes on a shared NFS filesystem, so ``df`` reports
    # aggregate backend capacity rather than this volume's purchased quota. The
    # sentinel-bound logical budget is therefore an independent fail-closed gate.
    logical_reserve = (
        minimum_free_bytes
        if minimum_logical_reserve_bytes is None
        else minimum_logical_reserve_bytes
    )
    quota_bytes = volume_size_gb * 1_000_000_000
    logical_used_bytes = _unique_logical_bytes(candidate)
    if logical_used_bytes + logical_reserve > quota_bytes:
        raise UnsafeOutputPath(
            "external artifact root lacks the required logical volume reserve: "
            f"quota={quota_bytes}, used={logical_used_bytes}, reserve={logical_reserve}"
        )

    if write_read_probe:
        probe_path: Path | None = None
        try:
            descriptor, probe_name = tempfile.mkstemp(
                prefix=".csae-write-read-probe-", dir=candidate
            )
            probe_path = Path(probe_name)
            payload = os.urandom(32)
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            if probe_path.read_bytes() != payload:
                raise UnsafeOutputPath(
                    f"external artifact root failed write/read-back probe: {candidate}"
                )
        except OSError as exc:
            raise UnsafeOutputPath(
                f"external artifact root is not durably writable: {candidate}"
            ) from exc
        finally:
            if probe_path is not None:
                probe_path.unlink(missing_ok=True)

    return candidate


def require_new_external_artifact_path(
    path: str | Path,
    *,
    artifact_root: str | Path | None = None,
    minimum_free_bytes: int = MIN_ARTIFACT_FREE_BYTES,
    minimum_volume_size_gb: int = MIN_ARTIFACT_VOLUME_SIZE_GB,
    minimum_logical_reserve_bytes: int | None = None,
    expected_volume_id: str | None = None,
) -> Path:
    """Return a fresh destination beneath the verified RunPod artifact root."""

    allowed_root = require_external_artifact_root(
        artifact_root,
        minimum_free_bytes=minimum_free_bytes,
        minimum_volume_size_gb=minimum_volume_size_gb,
        minimum_logical_reserve_bytes=minimum_logical_reserve_bytes,
        expected_volume_id=expected_volume_id,
    )
    candidate = Path(path).expanduser()
    if not candidate.is_absolute():
        candidate = allowed_root / candidate
    candidate = candidate.resolve(strict=False)
    _reject_repo_or_upstream(candidate)

    if candidate == allowed_root or not _is_beneath(candidate, allowed_root):
        raise UnsafeOutputPath(
            f"external artifact output must be a child of {allowed_root}: {candidate}"
        )
    if candidate.exists():
        raise UnsafeOutputPath(f"output path must not already exist: {candidate}")
    return candidate


def require_new_output_path(path: str | Path, *, release: bool = False) -> Path:
    """Validate a fresh local fixture or compact Git-metadata destination.

    Local development fixtures must be children of
    ``out/consciousness_sae_changepoint``. ``release=True`` is reserved for a
    compact metadata receipt that is a direct child of the matching ``data``
    root. Outcome-bearing jobs must instead use
    :func:`require_new_external_artifact_path`. The caller must invoke the
    applicable guard before creating the destination.
    """

    candidate = _resolved(path)

    for upstream_root in READ_ONLY_UPSTREAM_ROOTS:
        if _is_beneath(candidate, upstream_root):
            raise UnsafeOutputPath(
                f"output path is inside read-only upstream data/code: {candidate}"
            )

    allowed_root = DATA_ROOT if release else OUT_ROOT
    if candidate == allowed_root.resolve(strict=False) or not _is_beneath(
        candidate, allowed_root
    ):
        output_kind = "metadata release" if release else "local fixture"
        raise UnsafeOutputPath(
            f"{output_kind} output must be a child of {allowed_root}: {candidate}"
        )

    if release and candidate.parent != DATA_ROOT.resolve(strict=False):
        raise UnsafeOutputPath(
            f"release output must be a direct child of {DATA_ROOT}: {candidate}"
        )

    if candidate.exists():
        raise UnsafeOutputPath(f"output path must not already exist: {candidate}")

    return candidate

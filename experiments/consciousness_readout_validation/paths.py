"""Fail-closed path isolation for the readout-validation pilot."""

from __future__ import annotations

import json
import os
from pathlib import Path

from .inventory import BOUND_REPOSITORY_PATHS
from .protocol import STUDY_ID, STUDY_SLUG, public_input_allowlist


REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_ROOT = REPO_ROOT / "data" / STUDY_SLUG
ARTIFACT_ROOT_ENV = "CONSCIOUSNESS_READOUT_VALIDATION_ARTIFACT_ROOT"
VOLUME_ID_ENV = "CONSCIOUSNESS_READOUT_VALIDATION_VOLUME_ID"
VOLUME_SENTINEL = ".consciousness_readout_validation_volume.json"

PILOT_EXTERNAL_PHASES = (
    "public_artifacts",
    "g1_transport_arithmetic",
    "g2_neutral_transport",
    "g3_clean_semantic_readout",
    "g3p_clean_polarity",
    "g4_vector_safety",
    "audit",
    "analysis",
    "benchmark",
)

FORBIDDEN_REPOSITORY_INPUT_ROOTS = tuple(
    REPO_ROOT / relative
    for relative in (
        "data/consciousness_sae_changepoint",
        "out/consciousness_sae_changepoint",
        "data/public_sae_consciousness_gating",
        "data/sae_jlens_audit",
        "data/causal_transplant",
        "data/gemma_scope_9b",
    )
)


class UnsafePilotPath(ValueError):
    """Raised when a path would weaken study isolation."""


def _resolved(path: Path) -> Path:
    return path.expanduser().resolve(strict=False)


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def assert_not_forbidden_input(path: Path) -> Path:
    candidate = _resolved(path)
    for forbidden_root in FORBIDDEN_REPOSITORY_INPUT_ROOTS:
        if _is_within(candidate, _resolved(forbidden_root)):
            raise UnsafePilotPath(f"prior-study input is forbidden: {path}")
    markers = public_input_allowlist()["forbidden_path_markers"]
    normalized = candidate.as_posix().lower()
    if any(marker.lower() in normalized for marker in markers):
        raise UnsafePilotPath(f"forbidden prior-study path marker: {path}")
    return candidate


def require_new_metadata_output(path: Path) -> Path:
    """Allow only a fresh direct child of this pilot's tracked data root."""

    candidate = _resolved(path)
    root = _resolved(DATA_ROOT)
    if DATA_ROOT.is_symlink() or not root.is_dir():
        raise UnsafePilotPath(f"pilot metadata root must be an existing non-symlink directory: {DATA_ROOT}")
    if candidate.parent != root:
        raise UnsafePilotPath(f"metadata output must be a direct child of {root}")
    if path.is_symlink() or candidate.exists():
        raise UnsafePilotPath(f"metadata output must be fresh and non-symlinked: {path}")
    return candidate


def require_repository_source_input(path: Path) -> Path:
    """Accept only an exact source/test/document path in the bound inventory."""

    candidate = assert_not_forbidden_input(path)
    try:
        relative = candidate.relative_to(_resolved(REPO_ROOT)).as_posix()
    except ValueError as exc:
        raise UnsafePilotPath(f"repository source input is outside the repository: {path}") from exc
    if relative not in BOUND_REPOSITORY_PATHS:
        raise UnsafePilotPath(f"repository source input is not allowlisted: {relative}")
    if not candidate.is_file() or candidate.is_symlink():
        raise UnsafePilotPath(f"repository source input is not a regular file: {relative}")
    return candidate


def require_external_artifact_root(
    root: Path | None = None,
    *,
    expected_volume_id: str | None = None,
) -> Path:
    """Validate an external root and its study-specific persistent-volume sentinel."""

    configured = root or (Path(os.environ[ARTIFACT_ROOT_ENV]) if os.environ.get(ARTIFACT_ROOT_ENV) else None)
    if configured is None:
        raise UnsafePilotPath(f"{ARTIFACT_ROOT_ENV} is required")
    candidate = _resolved(configured)
    if configured.is_symlink() or not candidate.is_dir():
        raise UnsafePilotPath("external artifact root must be an existing non-symlink directory")
    if _is_within(candidate, _resolved(REPO_ROOT)):
        raise UnsafePilotPath("external artifact root must be outside the repository")

    sentinel_path = candidate / VOLUME_SENTINEL
    if sentinel_path.is_symlink() or not sentinel_path.is_file():
        raise UnsafePilotPath(f"missing non-symlink volume sentinel: {sentinel_path}")
    try:
        sentinel = json.loads(sentinel_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise UnsafePilotPath(f"invalid volume sentinel: {sentinel_path}") from exc

    required_volume_id = expected_volume_id or os.environ.get(VOLUME_ID_ENV)
    if not required_volume_id:
        raise UnsafePilotPath(f"{VOLUME_ID_ENV} or expected_volume_id is required")
    expected = {
        "study_slug": STUDY_SLUG,
        "study_id": STUDY_ID,
        "volume_id": required_volume_id,
    }
    for key, value in expected.items():
        if sentinel.get(key) != value:
            raise UnsafePilotPath(
                f"volume sentinel {key} mismatch: expected {value!r}, got {sentinel.get(key)!r}"
            )
    return candidate


def require_new_external_phase_dir(
    phase: str,
    *,
    root: Path | None = None,
    expected_volume_id: str | None = None,
) -> Path:
    """Return, but do not create, a fresh namespaced external phase directory."""

    if phase not in PILOT_EXTERNAL_PHASES:
        raise UnsafePilotPath(f"unrecognized pilot phase: {phase}")
    artifact_root = require_external_artifact_root(root, expected_volume_id=expected_volume_id)
    candidate = artifact_root / STUDY_SLUG / STUDY_ID / phase
    if candidate.is_symlink() or candidate.exists():
        raise UnsafePilotPath(f"external phase directory must be fresh: {candidate}")
    return candidate


def require_public_artifact_input(
    path: Path,
    *,
    root: Path | None = None,
    expected_volume_id: str | None = None,
) -> Path:
    """Allow reads only below the sentinel-bound public-artifact cache."""

    artifact_root = require_external_artifact_root(root, expected_volume_id=expected_volume_id)
    public_root = artifact_root / STUDY_SLUG / STUDY_ID / "public_artifacts"
    candidate = assert_not_forbidden_input(path)
    if not _is_within(candidate, _resolved(public_root)):
        raise UnsafePilotPath("public artifact input is outside the pilot cache")
    if not candidate.exists() or candidate.is_symlink():
        raise UnsafePilotPath("public artifact input must exist and must not be a symlink")
    return candidate

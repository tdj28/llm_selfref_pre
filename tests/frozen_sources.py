"""Historical test fixtures; never relax the live execution source gates."""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
import tempfile
from contextlib import contextmanager
from functools import lru_cache
from pathlib import Path, PurePosixPath
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
HISTORICAL_INFRASTRUCTURE_PATHS = frozenset({
    ".gitignore",
    "data/consciousness_sae_target_blind_calibration/README.md",
})


def source_bytes(repo: Path, row: dict, commit: str) -> bytes:
    relative = PurePosixPath(row["path"])
    if relative.is_absolute() or ".." in relative.parts or not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise ValueError("unsafe historical source reference")
    current = repo / relative
    if current.is_symlink() or not current.is_file():
        raise ValueError(f"historical source input is not a regular file: {relative}")
    raw = current.read_bytes()
    if len(raw) == row["bytes"] and hashlib.sha256(raw).hexdigest() == row["sha256"]:
        return raw
    if relative.as_posix() not in HISTORICAL_INFRASTRUCTURE_PATHS:
        raise ValueError(f"current scientific/source binding differs: {relative}")
    raw = subprocess.check_output(["git", "show", f"{commit}:{relative}"], cwd=repo)
    if len(raw) != row["bytes"] or hashlib.sha256(raw).hexdigest() != row["sha256"]:
        raise ValueError(f"historical source hash differs: {relative}")
    return raw


@contextmanager
def historical_root(plan_dir: Path):
    """Copy public support files, then restore every bound source by exact hash."""
    relative_plan = plan_dir.relative_to(ROOT)
    manifest = json.loads((plan_dir / "plan_manifest.json").read_bytes())
    rows = json.loads((plan_dir / "source_files.json").read_bytes())["files"]
    family = relative_plan.parts[1]
    with tempfile.TemporaryDirectory(prefix="historical-test-") as directory:
        root = Path(directory).resolve()
        support = subprocess.check_output(
            ["git", "ls-files", "-z", "--", f"data/{family}", f"docs/{family}"], cwd=ROOT
        ).decode().split("\0")
        for relative in filter(None, support):
            destination = root / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / relative, destination)
        for row in rows:
            destination = root / row["path"]
            raw = source_bytes(ROOT, row, manifest["git_head_commit"])
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(raw)
        yield root


@lru_cache(maxsize=1)
def calibration_provenance():
    from experiments.consciousness_sae_target_blind_calibration import (
        audit_recovery,
        authorize,
        protocol,
    )

    relative = protocol.CANONICAL_PLAN_RELATIVE_PATH
    with historical_root(ROOT / relative) as root:
        with patch.object(audit_recovery, "REPO_ROOT", root), patch.object(authorize, "REPO_ROOT", root):
            return audit_recovery._validate_pre_gpu_issue_inputs(root / relative)


def signed_dose_plan_audit():
    from experiments.consciousness_sae_signed_dose_scan import protocol, validate_plan

    relative = protocol.CANONICAL_PLAN_RELATIVE_PATH
    with historical_root(ROOT / relative) as root:
        with patch.object(validate_plan, "REPO_ROOT", root):
            return validate_plan.validate(root / relative)

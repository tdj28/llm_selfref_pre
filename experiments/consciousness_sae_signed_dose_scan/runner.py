#!/usr/bin/env python3
"""Execute the frozen signed dose scan through the proven calibration engine.

The predecessor engine is imported as an implementation dependency only.  This
module replaces every study-specific dependency before execution, so the old
plan, review, authorization, and raw namespace cannot be accepted.  The
predecessor files themselves remain byte-for-byte unchanged.
"""

from __future__ import annotations

from importlib import metadata as importlib_metadata
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from experiments.consciousness_sae_target_blind_calibration import runner as _impl

from . import authorize, build_plan, orientation, protocol, validate_plan


REPO_ROOT = Path(__file__).resolve().parents[2]
REQUIREMENTS_PATH = (
    REPO_ROOT
    / "experiments/consciousness_sae_signed_dose_scan/requirements-runpod-b200.txt"
)


def _install_study_bindings() -> None:
    """Bind the generic engine to this successor before any validation/run."""

    _impl.protocol = protocol
    _impl.build_plan = build_plan
    _impl.authorize = authorize
    _impl.orientation = orientation


_BASE_REQUIREMENTS_VALIDATOR = _impl._validate_runtime_requirements  # noqa: SLF001


def _validate_runtime_requirements(
    path: Path | None = None,
    *,
    version: Callable[[str], str] = importlib_metadata.version,
) -> dict[str, str]:
    return _BASE_REQUIREMENTS_VALIDATOR(
        path or REQUIREMENTS_PATH,
        version=version,
    )


def _validate_authorization(
    path: Path,
    *,
    plan_dir: Path,
    plan: Mapping[str, Any],
    ownership: Mapping[str, Any],
    guest: Mapping[str, Any],
    cache: Mapping[str, Any],
) -> dict[str, Any]:
    value = _impl._read_json(path)  # noqa: SLF001
    root = Path(plan_dir).expanduser().absolute()
    try:
        return authorize.validate_execution_authorization(
            value,
            plan=plan,
            plan_manifest_path=root / "plan_manifest.json",
            source_files_path=root / "source_files.json",
            ownership=ownership,
            guest=guest,
            cache=cache,
            now_unix=__import__("time").time(),
        )
    except authorize.AuthorizationError as exc:
        raise _impl.CalibrationExecutionError(
            f"execution authorization failed: {exc}"
        ) from exc


def _validate_plan(path: Path) -> dict[str, Any]:
    """Validate the successor plan without accepting predecessor filenames/scope."""

    try:
        receipt = validate_plan.validate(path, enforce_canonical_path=True)
    except validate_plan.IndependentPlanAuditError as exc:
        raise _impl.CalibrationExecutionError(
            f"signed-dose plan validation failed: {exc}"
        ) from exc
    manifest = _impl._read_json(  # noqa: SLF001
        Path(path).expanduser().absolute() / "plan_manifest.json"
    )
    if receipt.get("plan_manifest_sha256") != manifest.get(
        "plan_manifest_sha256"
    ):
        raise _impl.CalibrationExecutionError(
            "independent plan receipt differs from the runtime manifest"
        )
    return manifest


def _patch_engine() -> None:
    _install_study_bindings()
    _impl._validate_plan = _validate_plan  # noqa: SLF001
    _impl._validate_runtime_requirements = _validate_runtime_requirements  # noqa: SLF001
    _impl._validate_authorization = _validate_authorization  # noqa: SLF001


def _validate_authorized_run_id(path: Path, run_id: str) -> None:
    authorization = _impl._read_json(path)  # noqa: SLF001
    if authorization.get("authorized_run_id") != run_id:
        raise _impl.CalibrationExecutionError(
            "requested run ID differs from the one-attempt authorization"
        )


def execute(**kwargs: Any) -> Path:
    _patch_engine()
    _validate_authorized_run_id(
        Path(kwargs["authorization_receipt_path"]), str(kwargs.get("run_id", ""))
    )
    return _impl.execute(**kwargs)


def build_parser() -> Any:
    _patch_engine()
    return _impl.build_parser()


def main(argv: Sequence[str] | None = None) -> int:
    _patch_engine()
    args = _impl.build_parser().parse_args(argv)
    print(
        execute(
            plan_dir=args.plan_dir,
            volume_root=args.volume_root,
            volume_id=args.volume_id,
            run_id=args.run_id,
            model_snapshot=args.model_snapshot,
            sae_path=args.sae_path,
            j_lens_path=args.j_lens_path,
            ownership_receipt_path=args.ownership_receipt,
            guest_receipt_path=args.guest_receipt,
            cache_receipt_path=args.cache_receipt,
            authorization_receipt_path=args.authorization_receipt,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

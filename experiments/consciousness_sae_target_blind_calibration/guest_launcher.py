#!/usr/bin/env python3
"""Launch only the calibration runner from provider-attested guest state.

The launcher validates the base ownership receipt before importing any model
library, derives the immutable image/determinism/ownership environment, and
then replaces itself with the target-blind v2 runner.  Callers cannot supply a
second ownership receipt or override any attested environment value.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Callable, Mapping, Sequence

from experiments.consciousness_sae_realization_validation import (
    protocol as base_protocol,
)
from experiments.consciousness_sae_realization_validation import runpod_preflight


RUNNER_MODULE = "experiments.consciousness_sae_target_blind_calibration.runner"
MODEL_MODULE_ROOTS = frozenset({"torch", "transformers"})


class GuestLaunchError(RuntimeError):
    """The calibration process is not bound to provider-attested guest state."""


def _require_pre_model_process(module_names: Sequence[str]) -> None:
    loaded = {name.partition(".")[0] for name in module_names}
    forbidden = sorted(loaded.intersection(MODEL_MODULE_ROOTS))
    if forbidden:
        raise GuestLaunchError(
            "model stack was imported before deterministic launch: "
            + ",".join(forbidden)
        )


def _set_attested_environment(
    *,
    ownership_receipt: Mapping[str, object],
    environ: Mapping[str, str],
) -> dict[str, str]:
    try:
        ownership = runpod_preflight.validate_ownership_receipt(ownership_receipt)
    except runpod_preflight.PreflightError as exc:
        raise GuestLaunchError("ownership receipt validation failed") from exc
    attestation = ownership.get("provider_container_image_attestation")
    if not isinstance(attestation, Mapping):
        raise GuestLaunchError("container-image attestation is absent")
    immutable_image = attestation.get("immutable_reference")
    if immutable_image != base_protocol.CONTAINER_IMAGE_SPEC["immutable_reference"]:
        raise GuestLaunchError("provider container-image attestation differs")
    required = {
        base_protocol.CONTAINER_IMAGE_ENV: str(immutable_image),
        base_protocol.CUBLAS_WORKSPACE_CONFIG_ENV: (
            base_protocol.CUBLAS_WORKSPACE_CONFIG_VALUE
        ),
        base_protocol.GUEST_LAUNCH_OWNERSHIP_ENV: str(ownership["receipt_sha256"]),
    }
    child = dict(environ)
    for name, expected in required.items():
        supplied = child.get(name)
        if supplied is not None and supplied != expected:
            raise GuestLaunchError(f"caller override conflicts with {name}")
        child[name] = expected
    child["PYTHONDONTWRITEBYTECODE"] = "1"
    return child


def _forwarded_arguments(values: Sequence[str]) -> tuple[str, ...]:
    forwarded = tuple(values)
    if forwarded[:1] == ("--",):
        forwarded = forwarded[1:]
    if any(
        value == "--ownership-receipt" or value.startswith("--ownership-receipt=")
        for value in forwarded
    ):
        raise GuestLaunchError(
            "--ownership-receipt is launcher-owned and cannot be forwarded"
        )
    return forwarded


def launch(
    *,
    ownership_receipt_path: Path,
    forwarded_args: Sequence[str],
    environ: Mapping[str, str] | None = None,
    loaded_module_names: Sequence[str] | None = None,
    executable: str | None = None,
    execve: Callable[[str, Sequence[str], Mapping[str, str]], object] = os.execve,
) -> None:
    """Validate provider authority and ``execve`` the sole v2 GPU runner."""

    _require_pre_model_process(
        tuple(sys.modules) if loaded_module_names is None else loaded_module_names
    )
    try:
        ownership = runpod_preflight._read_receipt_path(  # noqa: SLF001
            Path(ownership_receipt_path), "ownership"
        )
        receipt_path = Path(ownership_receipt_path).expanduser().resolve(strict=True)
    except (OSError, runpod_preflight.PreflightError) as exc:
        raise GuestLaunchError("ownership receipt path is missing or unsafe") from exc
    child = _set_attested_environment(
        ownership_receipt=ownership,
        environ=os.environ if environ is None else environ,
    )
    forwarded = _forwarded_arguments(forwarded_args)
    python = sys.executable if executable is None else executable
    argv = (
        python,
        "-B",
        "-u",
        "-m",
        RUNNER_MODULE,
        "--ownership-receipt",
        str(receipt_path),
        *forwarded,
    )
    execve(python, argv, child)
    raise GuestLaunchError("guest exec unexpectedly returned")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ownership-receipt", type=Path, required=True)
    parser.add_argument("forwarded_args", nargs=argparse.REMAINDER)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        launch(
            ownership_receipt_path=args.ownership_receipt,
            forwarded_args=args.forwarded_args,
        )
    except GuestLaunchError as exc:
        print(f"calibration guest launch refused: {exc}", file=sys.stderr)
        return 2
    return 0  # pragma: no cover - successful launch replaces this process


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Launch the smoke or paid stages from provider-attested guest state.

This module deliberately imports neither ``runtime`` nor ``runner``.  It
validates the successor ownership receipt, derives the container digest from
that provider-backed receipt, installs the deterministic CUDA environment,
and only then replaces itself with the selected execution module.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Callable, Mapping, Sequence

from . import protocol, runpod_preflight


class GuestLaunchError(RuntimeError):
    """Raised before importing Torch, Transformers, or any model code."""


COMMANDS = {
    "smoke": (
        "experiments.consciousness_sae_realization_validation.smoke_test",
        (),
    ),
    "stage-a": (
        "experiments.consciousness_sae_realization_validation.runner",
        ("stage-a",),
    ),
    "stage-b": (
        "experiments.consciousness_sae_realization_validation.runner",
        ("stage-b",),
    ),
}
MODEL_MODULE_ROOTS = frozenset({"torch", "transformers"})


def _require_pre_model_process(module_names: Sequence[str]) -> None:
    loaded_roots = {name.partition(".")[0] for name in module_names}
    forbidden = sorted(MODEL_MODULE_ROOTS.intersection(loaded_roots))
    if forbidden:
        raise GuestLaunchError(
            "model stack was imported before deterministic CUDA launch: "
            + ",".join(forbidden)
        )


def _set_attested_environment(
    *,
    ownership_receipt: Mapping[str, object],
    environ: Mapping[str, str],
) -> dict[str, str]:
    try:
        ownership = runpod_preflight.validate_ownership_receipt(
            ownership_receipt
        )
    except runpod_preflight.PreflightError as exc:
        raise GuestLaunchError("ownership receipt validation failed") from exc
    attestation = ownership["provider_container_image_attestation"]
    if not isinstance(attestation, Mapping):  # defensive; validator is exact
        raise GuestLaunchError("provider container-image attestation is absent")
    provider_image = attestation.get("immutable_reference")
    if not isinstance(provider_image, str) or not provider_image:
        raise GuestLaunchError("provider container-image attestation is malformed")
    required = {
        protocol.CONTAINER_IMAGE_ENV: provider_image,
        protocol.CUBLAS_WORKSPACE_CONFIG_ENV: (
            protocol.CUBLAS_WORKSPACE_CONFIG_VALUE
        ),
        protocol.GUEST_LAUNCH_OWNERSHIP_ENV: ownership["receipt_sha256"],
    }
    child = dict(environ)
    for name, value in required.items():
        prior = child.get(name)
        if prior is not None and prior != value:
            raise GuestLaunchError(f"pre-existing {name} conflicts with launch receipt")
        child[name] = value
    if any(child.get(name) != value for name, value in required.items()):
        raise GuestLaunchError("deterministic guest launch environment differs")
    child["PYTHONDONTWRITEBYTECODE"] = "1"
    return child


def _forwarded_arguments(values: Sequence[str]) -> tuple[str, ...]:
    forwarded = tuple(values)
    if forwarded[:1] == ("--",):
        forwarded = forwarded[1:]
    if any(
        value == "--ownership-receipt"
        or value.startswith("--ownership-receipt=")
        for value in forwarded
    ):
        raise GuestLaunchError(
            "--ownership-receipt is launcher-owned and cannot be forwarded"
        )
    return forwarded


def launch(
    *,
    command: str,
    ownership_receipt_path: Path,
    forwarded_args: Sequence[str],
    environ: Mapping[str, str] | None = None,
    loaded_module_names: Sequence[str] | None = None,
    executable: str | None = None,
    execve: Callable[[str, Sequence[str], Mapping[str, str]], object] = os.execve,
) -> None:
    """Validate, set environment, and ``execve`` one frozen command."""

    if command not in COMMANDS:
        raise GuestLaunchError("guest launch command is not allowlisted")
    _require_pre_model_process(
        tuple(sys.modules) if loaded_module_names is None else loaded_module_names
    )
    try:
        ownership = runpod_preflight._read_receipt_path(  # noqa: SLF001
            Path(ownership_receipt_path), "ownership"
        )
        receipt_path = Path(ownership_receipt_path).expanduser().resolve(
            strict=True
        )
    except (OSError, runpod_preflight.PreflightError) as exc:
        raise GuestLaunchError("ownership receipt path is missing or unsafe") from exc
    child_environment = _set_attested_environment(
        ownership_receipt=ownership,
        environ=os.environ if environ is None else environ,
    )
    forwarded = _forwarded_arguments(forwarded_args)
    module, prefix = COMMANDS[command]
    python = sys.executable if executable is None else executable
    argv = (
        python,
        "-B",
        "-u",
        "-m",
        module,
        *prefix,
        "--ownership-receipt",
        str(receipt_path),
        *forwarded,
    )
    execve(python, argv, child_environment)
    raise GuestLaunchError("guest exec unexpectedly returned")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ownership-receipt", type=Path, required=True)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in COMMANDS:
        command = commands.add_parser(name)
        command.add_argument("forwarded_args", nargs=argparse.REMAINDER)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        launch(
            command=args.command,
            ownership_receipt_path=args.ownership_receipt,
            forwarded_args=args.forwarded_args,
        )
    except GuestLaunchError as exc:
        print(f"guest launch refused: {exc}", file=sys.stderr)
        return 2
    return 0  # pragma: no cover - successful launch replaces this process


if __name__ == "__main__":
    raise SystemExit(main())

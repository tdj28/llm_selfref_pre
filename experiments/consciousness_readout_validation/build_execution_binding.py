"""Build a fresh, model-free execution binding for the validation pilot.

The public artifacts must already be staged (dereferenced, with no symlinks)
below this study's sentinel-bound ``public_artifacts`` directory.  This command
hashes every staged byte, validates the exact result-free machine plan, performs
the complete tokenizer-only audit, and atomically emits a self-hashed binding.
It cannot import or load causal-model weights and performs zero model forwards.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from . import paths, protocol, runtime
from .gpu_runner import GPU_ADAPTER_VERSION
from .validate_plan import validate_plan


OUTPUT_NAMESPACE = "execution_bindings"
TOKENIZER_FILENAMES = frozenset(
    {
        "tokenizer.json",
        "tokenizer_config.json",
        "special_tokens_map.json",
        "added_tokens.json",
        "generation_config.json",
    }
)


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    with path.open("xb") as handle:
        handle.write(protocol.canonical_json_bytes(dict(value)) + b"\n")
        handle.flush()
        os.fsync(handle.fileno())


def inventory_snapshot(snapshot: Path) -> tuple[list[dict[str, Any]], str, str]:
    """Hash a fully dereferenced model snapshot and its tokenizer subset."""

    root = snapshot.resolve(strict=True)
    if snapshot.is_symlink() or not root.is_dir():
        raise runtime.PilotRuntimeError("model_snapshot", "snapshot is not a safe directory")
    rows: list[dict[str, Any]] = []
    for candidate in sorted(root.rglob("*"), key=lambda path: path.relative_to(root).as_posix()):
        if candidate.is_symlink():
            raise runtime.PilotRuntimeError(
                "model_snapshot", f"snapshot symlink is forbidden: {candidate}"
            )
        if candidate.is_dir():
            continue
        if not candidate.is_file():
            raise runtime.PilotRuntimeError("model_snapshot", "snapshot entry is not regular")
        rows.append(
            {
                "path": candidate.relative_to(root).as_posix(),
                "sha256": runtime.sha256_file(candidate),
            }
        )
    if not rows:
        raise runtime.PilotRuntimeError("model_snapshot", "snapshot inventory is empty")
    tokenizer_rows = [row for row in rows if Path(row["path"]).name in TOKENIZER_FILENAMES]
    if not tokenizer_rows:
        raise runtime.PilotRuntimeError("tokenizer_manifest", "tokenizer inventory is empty")
    return (
        rows,
        protocol.canonical_sha256(rows),
        protocol.canonical_sha256(tokenizer_rows),
    )


def resolve_declared_binding_path(binding: Mapping[str, Any], dotted_path: str) -> Any:
    """Resolve one literal plan-declared path in an execution binding."""

    current: Any = binding
    for component in dotted_path.split("."):
        if not isinstance(current, Mapping) or component not in current:
            raise runtime.PilotRuntimeError(
                "binding_contract", f"declared execution-binding path is absent: {dotted_path}"
            )
        current = current[component]
    return current


def validate_declared_binding_paths(binding: Mapping[str, Any]) -> None:
    for dotted_path in protocol.REQUIRED_EXECUTION_BINDING_PATHS:
        resolve_declared_binding_path(binding, dotted_path)


def build_binding_payload(
    *,
    plan_manifest_sha256: str,
    plan_validation_receipt: Mapping[str, Any],
    volume_id: str,
    model_snapshot: Path,
    model_files: Sequence[Mapping[str, Any]],
    model_file_inventory_sha256: str,
    tokenizer_inventory_sha256: str,
    sae_path: Path,
    sae_readme_path: Path,
    sae_config_path: Path,
    j_lens_path: Path,
    j_lens_config_path: Path,
    tokenizer_audit_receipt_sha256: str,
) -> dict[str, Any]:
    """Construct the exact self-hashed binding from already verified facts."""

    core = {
        "schema_version": 1,
        "status": "pass",
        "binding_kind": "target_blind_pilot_execution_binding_v1",
        "study_id": protocol.STUDY_ID,
        "protocol_version": protocol.PROTOCOL_VERSION,
        "plan_manifest_sha256": plan_manifest_sha256,
        "plan_validation_receipt_sha256": protocol.canonical_sha256(
            dict(plan_validation_receipt)
        ),
        "resolved_external_root_id": volume_id,
        "container_image": protocol.CONTAINER_IMAGE_SPEC,
        "runtime_adapter": GPU_ADAPTER_VERSION,
        "runtime_adapter_source_sha256": runtime.sha256_file(
            Path(__file__).with_name("gpu_runner.py")
        ),
        "tokenizer_content_inventory_sha256": tokenizer_inventory_sha256,
        "tokenizer_audit_receipt_sha256": tokenizer_audit_receipt_sha256,
        "artifacts": {
            "model_snapshot": {
                "path": str(model_snapshot.resolve(strict=True)),
                "repository": protocol.MODEL_SPEC["repository"],
                "revision": protocol.MODEL_SPEC["revision"],
                "files": [dict(row) for row in model_files],
                "file_inventory_sha256": model_file_inventory_sha256,
            },
            "sae": {
                "path": str(sae_path.resolve(strict=True)),
                "readme_path": str(sae_readme_path.resolve(strict=True)),
                "config_path": str(sae_config_path.resolve(strict=True)),
                "repository": protocol.SAE_SPEC["repository"],
                "revision": protocol.SAE_SPEC["revision"],
                "filename": protocol.SAE_SPEC["filename"],
                "sha256": protocol.SAE_SPEC["sha256"],
                "readme_filename": protocol.SAE_SPEC["sidecars"]["readme"]["filename"],
                "readme_sha256": protocol.SAE_SPEC["sidecars"]["readme"]["sha256"],
                "config_filename": protocol.SAE_SPEC["sidecars"]["config"]["filename"],
                "config_sha256": protocol.SAE_SPEC["sidecars"]["config"]["sha256"],
            },
            "j_lens": {
                "path": str(j_lens_path.resolve(strict=True)),
                "config_path": str(j_lens_config_path.resolve(strict=True)),
                "repository": protocol.J_LENS_SPEC["repository"],
                "revision": protocol.J_LENS_SPEC["revision"],
                "filename": protocol.J_LENS_SPEC["filename"],
                "sha256": protocol.J_LENS_SPEC["sha256"],
                "config_filename": protocol.J_LENS_SPEC["release_config"]["filename"],
                "config_sha256": protocol.J_LENS_SPEC["release_config"]["sha256"],
            },
        },
        "model_weights_loaded": False,
        "model_forward_count": 0,
        "prior_outcome_inputs": [],
        "target_prompt_inputs": [],
        "target_outcome_inputs": [],
    }
    binding = {
        **core,
        "execution_binding_canonical_sha256": protocol.canonical_sha256(core),
    }
    validate_declared_binding_paths(binding)
    return binding


def build_execution_binding(
    *,
    plan_manifest_path: Path,
    artifact_root: Path,
    volume_id: str,
    model_snapshot: Path,
    sae_path: Path,
    sae_readme_path: Path,
    sae_config_path: Path,
    j_lens_path: Path,
    j_lens_config_path: Path,
    binding_id: str,
    validate_plan_fn: Callable[..., Mapping[str, Any]] = validate_plan,
    tokenizer_preflight_fn: Callable[..., tuple[Any, dict[str, Any]]] = runtime.tokenizer_preflight,
) -> Path:
    """Validate, tokenizer-audit, and atomically publish a fresh binding bundle."""

    if not runtime.SAFE_RUN_ID.fullmatch(binding_id):
        raise runtime.PilotRuntimeError("binding_id", "binding ID is invalid")
    external_root = paths.require_external_artifact_root(
        artifact_root, expected_volume_id=volume_id
    )
    plan_validation = dict(validate_plan_fn(plan_manifest_path.resolve(strict=True).parent))
    _manifest, plan_hash = runtime._load_plan_manifest(plan_manifest_path)
    if plan_validation.get("plan_manifest_sha256") != plan_hash:
        raise runtime.PilotRuntimeError("plan_validation", "plan validator hash differs")

    resolved_model = paths.require_public_artifact_input(
        model_snapshot, root=external_root, expected_volume_id=volume_id
    )
    resolved_sae = paths.require_public_artifact_input(
        sae_path, root=external_root, expected_volume_id=volume_id
    )
    resolved_sae_readme = paths.require_public_artifact_input(
        sae_readme_path, root=external_root, expected_volume_id=volume_id
    )
    resolved_sae_config = paths.require_public_artifact_input(
        sae_config_path, root=external_root, expected_volume_id=volume_id
    )
    resolved_j = paths.require_public_artifact_input(
        j_lens_path, root=external_root, expected_volume_id=volume_id
    )
    resolved_j_config = paths.require_public_artifact_input(
        j_lens_config_path, root=external_root, expected_volume_id=volume_id
    )
    if (
        not resolved_model.is_dir()
        or not resolved_sae.is_file()
        or not resolved_sae_readme.is_file()
        or not resolved_sae_config.is_file()
        or not resolved_j.is_file()
        or not resolved_j_config.is_file()
    ):
        raise runtime.PilotRuntimeError("artifact_shape", "staged artifact types differ")
    if runtime.sha256_file(resolved_sae) != protocol.SAE_SPEC["sha256"]:
        raise runtime.PilotRuntimeError("artifact_hash", "SAE SHA-256 differs")
    if (
        runtime.sha256_file(resolved_sae_readme)
        != protocol.SAE_SPEC["sidecars"]["readme"]["sha256"]
    ):
        raise runtime.PilotRuntimeError("artifact_hash", "SAE README SHA-256 differs")
    if (
        runtime.sha256_file(resolved_sae_config)
        != protocol.SAE_SPEC["sidecars"]["config"]["sha256"]
    ):
        raise runtime.PilotRuntimeError("artifact_hash", "SAE config SHA-256 differs")
    if runtime.sha256_file(resolved_j) != protocol.J_LENS_SPEC["sha256"]:
        raise runtime.PilotRuntimeError("artifact_hash", "J-lens SHA-256 differs")
    if (
        runtime.sha256_file(resolved_j_config)
        != protocol.J_LENS_SPEC["release_config"]["sha256"]
    ):
        raise runtime.PilotRuntimeError("artifact_hash", "J-lens config SHA-256 differs")
    model_files, model_inventory_hash, tokenizer_inventory_hash = inventory_snapshot(
        resolved_model
    )
    _tokenizer, token_receipt = tokenizer_preflight_fn(
        resolved_model,
        plan_manifest_sha256=plan_hash,
        tokenizer_inventory_sha256=tokenizer_inventory_hash,
    )
    token_core = dict(token_receipt)
    token_hash = token_core.pop("receipt_sha256", None)
    if token_hash != protocol.canonical_sha256(token_core):
        raise runtime.PilotRuntimeError("token_receipt", "tokenizer receipt self-hash differs")
    binding = build_binding_payload(
        plan_manifest_sha256=plan_hash,
        plan_validation_receipt=plan_validation,
        volume_id=volume_id,
        model_snapshot=resolved_model,
        model_files=model_files,
        model_file_inventory_sha256=model_inventory_hash,
        tokenizer_inventory_sha256=tokenizer_inventory_hash,
        sae_path=resolved_sae,
        sae_readme_path=resolved_sae_readme,
        sae_config_path=resolved_sae_config,
        j_lens_path=resolved_j,
        j_lens_config_path=resolved_j_config,
        tokenizer_audit_receipt_sha256=str(token_hash),
    )
    # Reuse the production validator before publishing anything.
    runtime.validate_local_artifact_binding(
        binding, artifact_root=external_root, volume_id=volume_id
    )

    parent = external_root / protocol.STUDY_SLUG / protocol.STUDY_ID / OUTPUT_NAMESPACE
    parent.mkdir(parents=True, exist_ok=True)
    final = parent / binding_id
    partial = parent / f"{binding_id}.partial"
    if final.exists() or partial.exists() or final.is_symlink() or partial.is_symlink():
        raise runtime.PilotRuntimeError("binding_exists", "binding output is not fresh")
    partial.mkdir()
    try:
        _write_json(partial / "TOKENIZER_AUDIT.json", token_receipt)
        _write_json(partial / "EXECUTION_BINDING.json", binding)
        manifest_core = {
            "schema_version": 1,
            "study_id": protocol.STUDY_ID,
            "protocol_version": protocol.PROTOCOL_VERSION,
            "plan_manifest_sha256": plan_hash,
            "execution_binding_canonical_sha256": binding[
                "execution_binding_canonical_sha256"
            ],
            "files": [
                {
                    "path": name,
                    "bytes": (partial / name).stat().st_size,
                    "sha256": runtime.sha256_file(partial / name),
                }
                for name in ("EXECUTION_BINDING.json", "TOKENIZER_AUDIT.json")
            ],
            "model_weights_loaded": False,
            "model_forward_count": 0,
        }
        _write_json(
            partial / "BINDING_MANIFEST.json",
            {**manifest_core, "manifest_sha256": protocol.canonical_sha256(manifest_core)},
        )
        os.replace(partial, final)
    except BaseException:
        # Preserve a failed partial bundle for forensic inspection; never reuse it.
        raise
    return final


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan-manifest", type=Path, required=True)
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--volume-id", required=True)
    parser.add_argument("--model-snapshot", type=Path, required=True)
    parser.add_argument("--sae", type=Path, required=True)
    parser.add_argument("--sae-readme", type=Path, required=True)
    parser.add_argument("--sae-config", type=Path, required=True)
    parser.add_argument("--j-lens", type=Path, required=True)
    parser.add_argument("--j-lens-config", type=Path, required=True)
    parser.add_argument("--binding-id", required=True)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    output = build_execution_binding(
        plan_manifest_path=args.plan_manifest,
        artifact_root=args.artifact_root,
        volume_id=args.volume_id,
        model_snapshot=args.model_snapshot,
        sae_path=args.sae,
        sae_readme_path=args.sae_readme,
        sae_config_path=args.sae_config,
        j_lens_path=args.j_lens,
        j_lens_config_path=args.j_lens_config,
        binding_id=args.binding_id,
    )
    print(str(output))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

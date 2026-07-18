"""Validate and deterministically reconstruct a pilot machine plan."""

from __future__ import annotations

import argparse
import ast
import json
from pathlib import Path
from typing import Any, Iterable, Mapping

from . import paths
from .build_plan import (
    PLAN_MANIFEST_FILENAME,
    PLAN_PAYLOAD_FILES,
    artifact_bindings_contract,
    source_inventory,
    token_metadata_contract,
)
from .inventory import BOUND_REPOSITORY_PATHS
from .protocol import (
    PLAN_SCHEMA_VERSION,
    PROTOCOL_VERSION,
    STUDY_ID,
    STUDY_SLUG,
    canonical_json_bytes,
    canonical_sha256,
    g1_plan_rows,
    g2_plan_rows,
    g3_fixture_rows,
    g3p_plan_rows,
    g4_aggregate_assignments,
    g4_plan_rows,
    neutral_prompts,
    protocol_snapshot,
    public_input_allowlist,
    sha256_bytes,
)


FORBIDDEN_RESULT_KEYS = frozenset(
    {
        "generated_text",
        "activation_values",
        "residual_values",
        "logit_values",
        "observed_label",
        "judge_label",
        "effect_size",
        "p_value",
        "confidence_interval",
    }
)


class InvalidPilotPlan(ValueError):
    """Raised when a machine plan is not the exact result-free reconstruction."""


def _json_bytes(payload: Any) -> bytes:
    return canonical_json_bytes(payload) + b"\n"


def _jsonl_bytes(rows: Iterable[Mapping[str, Any]]) -> bytes:
    return b"".join(canonical_json_bytes(row) + b"\n" for row in rows)


def expected_payloads(repo_root: Path = paths.REPO_ROOT) -> dict[str, bytes]:
    """Independently assemble every expected payload from frozen definitions."""

    payloads = {
        "protocol_snapshot.json": _json_bytes(protocol_snapshot()),
        "input_allowlist.json": _json_bytes(public_input_allowlist()),
        "artifact_bindings.json": _json_bytes(artifact_bindings_contract()),
        "token_metadata.json": _json_bytes(token_metadata_contract()),
        "neutral_prompts.jsonl": _jsonl_bytes(neutral_prompts()),
        "g1_plan.jsonl": _jsonl_bytes(g1_plan_rows()),
        "g2_plan.jsonl": _jsonl_bytes(g2_plan_rows()),
        "g3_fixtures.jsonl": _jsonl_bytes(g3_fixture_rows()),
        "g3p_fixtures.jsonl": _jsonl_bytes(g3p_plan_rows()),
        "g4_assignments.jsonl": _jsonl_bytes(g4_aggregate_assignments()),
        "g4_plan.jsonl": _jsonl_bytes(g4_plan_rows()),
        "source_inventory.json": _json_bytes(source_inventory(repo_root)),
    }
    if tuple(payloads) != PLAN_PAYLOAD_FILES:
        raise InvalidPilotPlan("validator file order differs from the frozen builder order")
    return payloads


def _walk_result_free(value: Any, *, path: tuple[str, ...] = ()) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if key in FORBIDDEN_RESULT_KEYS:
                raise InvalidPilotPlan(f"result-bearing key is forbidden in a plan: {'.'.join((*path, key))}")
            _walk_result_free(child, path=(*path, key))
        return
    if isinstance(value, list):
        for index, child in enumerate(value):
            _walk_result_free(child, path=(*path, str(index)))
        return
    if isinstance(value, str) and value.startswith(("/", "~/")):
        raise InvalidPilotPlan(f"absolute path is forbidden in a portable plan: {value}")


def _parse_and_scan(filename: str, payload: bytes) -> None:
    try:
        if filename.endswith(".jsonl"):
            values = [json.loads(line) for line in payload.splitlines()]
        else:
            values = [json.loads(payload)]
    except json.JSONDecodeError as exc:
        raise InvalidPilotPlan(f"invalid JSON in {filename}") from exc
    for value in values:
        _walk_result_free(value)


def _assert_no_prior_study_imports(repo_root: Path) -> None:
    forbidden_markers = tuple(public_input_allowlist()["forbidden_path_markers"])
    for relative in BOUND_REPOSITORY_PATHS:
        if not relative.endswith(".py"):
            continue
        source_path = repo_root / relative
        try:
            tree = ast.parse(source_path.read_text(encoding="utf-8"), filename=relative)
        except (OSError, SyntaxError) as exc:
            raise InvalidPilotPlan(f"cannot parse bound Python source: {relative}") from exc
        imported: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imported.append(node.module or "")
        for module in imported:
            if any(marker in module for marker in forbidden_markers):
                raise InvalidPilotPlan(f"prior-study import is forbidden: {relative} imports {module}")


def _expected_manifest(payloads: Mapping[str, bytes]) -> dict[str, Any]:
    records = [
        {
            "filename": filename,
            "content_sha256": sha256_bytes(payloads[filename]),
            "size_bytes": len(payloads[filename]),
        }
        for filename in PLAN_PAYLOAD_FILES
    ]
    canonical_payload = {
        "schema_version": PLAN_SCHEMA_VERSION,
        "study_id": STUDY_ID,
        "protocol_version": PROTOCOL_VERSION,
        "files": records,
    }
    core = {
        "schema_version": PLAN_SCHEMA_VERSION,
        "study_slug": STUDY_SLUG,
        "study_id": STUDY_ID,
        "protocol_version": PROTOCOL_VERSION,
        "status": "target_blind_pilot_plan_execution_bindings_unresolved",
        "files": records,
        "canonical_payload_sha256": canonical_sha256(canonical_payload),
        "hash_semantics": {
            "content_sha256": "SHA-256 of exact file bytes, including the final newline",
            "canonical_payload_sha256": (
                "SHA-256 of canonical JSON over schema/study/protocol and ordered file records"
            ),
            "plan_manifest_sha256": (
                "SHA-256 of canonical JSON over this manifest excluding only this field"
            ),
        },
    }
    return {**core, "plan_manifest_sha256": canonical_sha256(core)}


def validate_plan(
    plan_dir: Path,
    *,
    repo_root: Path = paths.REPO_ROOT,
    enforce_metadata_root: bool = True,
) -> dict[str, Any]:
    candidate = plan_dir.resolve(strict=True)
    if plan_dir.is_symlink() or not candidate.is_dir():
        raise InvalidPilotPlan("plan path must be a non-symlink directory")
    if enforce_metadata_root and candidate.parent != paths.DATA_ROOT.resolve(strict=True):
        raise InvalidPilotPlan("plan directory is outside the isolated pilot metadata root")

    expected_names = {*PLAN_PAYLOAD_FILES, PLAN_MANIFEST_FILENAME}
    actual_names = {entry.name for entry in candidate.iterdir()}
    if actual_names != expected_names:
        raise InvalidPilotPlan(
            f"plan file set mismatch: missing={sorted(expected_names - actual_names)}, "
            f"unexpected={sorted(actual_names - expected_names)}"
        )
    for entry in candidate.iterdir():
        if entry.is_symlink() or not entry.is_file():
            raise InvalidPilotPlan(f"plan entry must be a regular non-symlink file: {entry.name}")

    reconstructed = expected_payloads(repo_root)
    for filename, expected_bytes in reconstructed.items():
        observed = (candidate / filename).read_bytes()
        if observed != expected_bytes:
            raise InvalidPilotPlan(f"deterministic reconstruction mismatch: {filename}")
        _parse_and_scan(filename, observed)

    manifest_bytes = (candidate / PLAN_MANIFEST_FILENAME).read_bytes()
    try:
        manifest = json.loads(manifest_bytes)
    except json.JSONDecodeError as exc:
        raise InvalidPilotPlan("invalid plan manifest JSON") from exc
    expected_manifest = _expected_manifest(reconstructed)
    if manifest != expected_manifest:
        raise InvalidPilotPlan("plan manifest does not match the independent reconstruction")
    if manifest_bytes != _json_bytes(expected_manifest):
        raise InvalidPilotPlan("plan manifest is not canonically encoded")
    _walk_result_free(manifest)
    _assert_no_prior_study_imports(repo_root)

    return {
        "study_id": STUDY_ID,
        "status": "valid_target_blind_pilot_plan_execution_bindings_unresolved",
        "canonical_payload_sha256": manifest["canonical_payload_sha256"],
        "plan_manifest_sha256": manifest["plan_manifest_sha256"],
        "manifest_file_sha256": sha256_bytes(manifest_bytes),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("plan_dir", type=Path)
    args = parser.parse_args(argv)
    receipt = validate_plan(args.plan_dir)
    print(canonical_json_bytes(receipt).decode("utf-8"))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

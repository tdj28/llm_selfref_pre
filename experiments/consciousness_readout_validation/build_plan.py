"""Build the deterministic, result-free machine plan for the validation pilot."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any, Iterable, Mapping

from . import paths
from .inventory import BOUND_REPOSITORY_PATHS, repository_path_role
from .protocol import (
    CONTAINER_IMAGE_SPEC,
    G1_HASH_SELECTED_LEXICAL_TOKEN_IDS,
    G1_TOKEN_REJECTION_LEXICON,
    G1_TOKEN_SELECTION_RULE,
    G2_RANDOM_CONTROL_COUNT,
    G3_TOKENIZATION_CONTRACT,
    G3_TOKEN_GROUPS,
    G3P_ANSWER_TOKEN_IDS,
    G3P_CONTEXT_TOKENIZATION_CONTRACT,
    G3P_EOT_TOKEN_ID,
    J_LENS_SPEC,
    MODEL_SPEC,
    PLAN_SCHEMA_VERSION,
    PROTOCOL_VERSION,
    REQUIRED_EXECUTION_BINDING_PATHS,
    SAE_SPEC,
    STUDY_ID,
    STUDY_SLUG,
    canonical_json_bytes,
    canonical_sha256,
    g1_plan_rows,
    g2_plan_rows,
    g2_random_j_seed,
    g3_fixture_rows,
    g3p_plan_rows,
    g4_aggregate_assignments,
    g4_plan_rows,
    neutral_prompts,
    protocol_snapshot,
    public_input_allowlist,
    sha256_bytes,
)


PLAN_PAYLOAD_FILES = (
    "protocol_snapshot.json",
    "input_allowlist.json",
    "artifact_bindings.json",
    "token_metadata.json",
    "neutral_prompts.jsonl",
    "g1_plan.jsonl",
    "g2_plan.jsonl",
    "g3_fixtures.jsonl",
    "g3p_fixtures.jsonl",
    "g4_assignments.jsonl",
    "g4_plan.jsonl",
    "source_inventory.json",
)
PLAN_MANIFEST_FILENAME = "PLAN_MANIFEST.json"


def _json_bytes(payload: Any) -> bytes:
    return canonical_json_bytes(payload) + b"\n"


def _jsonl_bytes(rows: Iterable[Mapping[str, Any]]) -> bytes:
    return b"".join(canonical_json_bytes(row) + b"\n" for row in rows)


def source_inventory(repo_root: Path = paths.REPO_ROOT) -> dict[str, Any]:
    records: list[dict[str, Any]] = []
    for relative_path in BOUND_REPOSITORY_PATHS:
        candidate = repo_root / relative_path
        if not candidate.is_file() or candidate.is_symlink():
            raise FileNotFoundError(f"bound repository file is missing or unsafe: {relative_path}")
        payload = candidate.read_bytes()
        records.append(
            {
                "path": relative_path,
                "role": repository_path_role(relative_path),
                "content_sha256": sha256_bytes(payload),
                "size_bytes": len(payload),
            }
        )
    return {
        "schema_version": PLAN_SCHEMA_VERSION,
        "study_id": STUDY_ID,
        "hash_semantics": "content_sha256 hashes exact repository file bytes",
        "files": tuple(records),
    }


def artifact_bindings_contract() -> dict[str, Any]:
    """Describe unresolved external bindings without fabricating local paths."""

    return {
        "schema_version": PLAN_SCHEMA_VERSION,
        "study_id": STUDY_ID,
        "binding_status": "unresolved_plan_only_execution_prohibited",
        "path_semantics": (
            "logical paths are relative to the sentinel-bound external pilot root; "
            "an execution binding receipt must resolve and rehash them"
        ),
        "model_snapshot": "public_artifacts/model_snapshot",
        "sae_path": "public_artifacts/sae/Llama-3.3-70B-Instruct-SAE-l50.pt",
        "sae_readme_path": "public_artifacts/sae/README.md",
        "sae_config_path": "public_artifacts/sae/config.yaml",
        "jlens_path": "public_artifacts/jlens/Llama-3.3-70B-Instruct_jacobian_lens.pt",
        "jlens_config_path": "public_artifacts/jlens/config.yaml",
        "artifacts": {
            "model": MODEL_SPEC,
            "sae": SAE_SPEC,
            "j_lens": J_LENS_SPEC,
        },
        "container_image": CONTAINER_IMAGE_SPEC,
        "required_execution_receipt_fields": REQUIRED_EXECUTION_BINDING_PATHS,
    }


def token_metadata_contract() -> dict[str, Any]:
    """Freeze token strings and audit rules; never invent tokenizer-derived IDs."""

    return {
        "schema_version": PLAN_SCHEMA_VERSION,
        "study_id": STUDY_ID,
        "binding_status": "tokenizer_audit_required_before_any_forward",
        "semantic_token_groups": G3_TOKEN_GROUPS,
        "semantic_token_ids": {},
        "semantic_tokenization_contract": G3_TOKENIZATION_CONTRACT,
        "polarity_display_labels": ("Yes", "No"),
        "polarity_token_pieces": ("Yes", "No"),
        "polarity_token_ids": G3P_ANSWER_TOKEN_IDS,
        "polarity_eot_token_id": G3P_EOT_TOKEN_ID,
        "polarity_tokenization_contract": G3P_CONTEXT_TOKENIZATION_CONTRACT,
        "g1_hash_selected_lexical_token_ids": G1_HASH_SELECTED_LEXICAL_TOKEN_IDS,
        "g1_token_panel_status": "unresolved_tokenizer_audit_required",
        "g1_token_selection_rule": G1_TOKEN_SELECTION_RULE,
        "g1_rejection_lexicon": G1_TOKEN_REJECTION_LEXICON,
        "g1_required_receipt_fields": (
            "candidate_sequence",
            "accepted_token_ids",
            "accepted_exact_token_pieces",
            "rejected_token_ids_and_reasons",
            "special_token_ids",
            "experimental_lexicon_token_ids",
            "tokenizer_revision",
            "token_panel_canonical_sha256",
        ),
        "random_j_controls": tuple(
            {
                "layer": layer,
                "seeds": tuple(g2_random_j_seed(layer, index) for index in range(G2_RANDOM_CONTROL_COUNT)),
            }
            for layer in range(45, 79)
        ),
    }


def plan_payloads(repo_root: Path = paths.REPO_ROOT) -> dict[str, bytes]:
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
        raise AssertionError("internal plan payload order differs from the frozen file list")
    return payloads


def build_manifest(payloads: Mapping[str, bytes]) -> dict[str, Any]:
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
    manifest_core = {
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
    return {
        **manifest_core,
        "plan_manifest_sha256": canonical_sha256(manifest_core),
    }


def build_plan(output_dir: Path, *, repo_root: Path = paths.REPO_ROOT) -> dict[str, Any]:
    destination = paths.require_new_metadata_output(output_dir)
    payloads = plan_payloads(repo_root)
    manifest = build_manifest(payloads)

    destination.mkdir(parents=False, exist_ok=False)
    for filename in PLAN_PAYLOAD_FILES:
        (destination / filename).write_bytes(payloads[filename])
    (destination / PLAN_MANIFEST_FILENAME).write_bytes(_json_bytes(manifest))
    return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=paths.DATA_ROOT / "pilot_v1_plan_scaffold",
    )
    args = parser.parse_args(argv)
    manifest = build_plan(args.output_dir)
    print(manifest["plan_manifest_sha256"])
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

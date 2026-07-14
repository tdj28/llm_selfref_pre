"""Independent, outcome-blind structural audit for the validation pilot.

This producer is intentionally separate from both the GPU executor and the
scientific analyzer.  It verifies the prospective plan, public artifact
binding, tokenizer receipt, completed phase manifests, exact measurement
grids/envelopes, and the pre-edit G4 vector inventory.  It never computes a
scientific gate or inspects a prior/target outcome input.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import statistics
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from datetime import datetime
from itertools import combinations
from pathlib import Path
from typing import Any, Callable

from . import protocol


AUDIT_SOURCE_RELATIVE_PATH = (
    "experiments/consciousness_readout_validation/audit_pilot.py"
)
AUDIT_TEST_RELATIVE_PATH = (
    "tests/consciousness_readout_validation/test_audit_pilot.py"
)
STRUCTURAL_RECEIPT_FILENAME = "STRUCTURAL_AUDIT_RECEIPT.json"
ANALYSIS_AUTHORIZATION_FILENAME = "ANALYSIS_AUTHORIZATION.json"
HEX64 = re.compile(r"[0-9a-f]{64}")
HEX32 = re.compile(r"[0-9a-f]{32}")
ASCII_WORD = re.compile(r" [A-Za-z]{3,16}")
REPO_ROOT = Path(__file__).resolve().parents[2]
VOLUME_SENTINEL = ".consciousness_readout_validation_volume.json"
EXPECTED_J_LENS_CONFIG_FILENAME = (
    "llama3.3-70b-it/jlens/Salesforce-wikitext/config.yaml"
)
EXPECTED_J_LENS_CONFIG_SHA256 = (
    "d4784fe625f58f2ae90318d45b9c2355f749c334a97936a04f749423992a8eb5"
)
EXPECTED_SAE_README_FILENAME = "README.md"
EXPECTED_SAE_README_SHA256 = (
    "dcadf1602fc337dcd538803c0e551cc93e6811b90e6fa0bb75cb8de8e0b219db"
)
EXPECTED_SAE_CONFIG_FILENAME = "config.yaml"
EXPECTED_SAE_CONFIG_SHA256 = (
    "ac0a793c34ce988d2524346d3ada7f2bf2e6d63bd584b3bb80943827a3112fc4"
)
AUDITED_REQUIRED_EXECUTION_BINDING_PATHS = (
    "resolved_external_root_id",
    "container_image",
    "artifacts.model_snapshot.file_inventory_sha256",
    "artifacts.sae.sha256",
    "artifacts.sae.readme_sha256",
    "artifacts.sae.config_sha256",
    "artifacts.j_lens.sha256",
    "artifacts.j_lens.config_sha256",
    "tokenizer_content_inventory_sha256",
    "execution_binding_canonical_sha256",
)
AUDITED_HOOK_CONTRACT = {
    "layer_numbering": "zero_based_transformer_decoder_block_index",
    "backend_module_path_template": "model.model.layers[{layer}]",
    "source_tensor": {
        "location": "decoder_block_forward_output_after_full_block_residual_update",
        "tuple_member": "first_hidden_state_tensor",
        "normalization": "none",
        "dtype": "bfloat16",
        "last_dimension": 8192,
        "cached_measurement_shape": (1, 1, 8192),
        "matching_measurement_shape": (1, "rendered_token_count", 8192),
    },
    "cached_token_alignment": {
        "render_once": True,
        "clean_cache_tokens": "x_1_through_x_(T-1)",
        "measured_forward_token": "x_T",
        "captured_sequence_position": "T",
        "output_logits_predict": "x_(T+1)",
        "clean_and_edited_visible_prefix_bytes_identical": True,
        "clean_and_edited_token_ids_identical": True,
    },
    "layer_50_edit": {
        "module_path": "model.model.layers[50]",
        "source_layer": 50,
        "capture_hook_registered_before_edit_hook": True,
        "h50_pre": "unmodified_block_50_forward_output",
        "operation": "one_elementwise_bfloat16_addition_of_signed_bfloat16_vector",
        "h50_post": "edit_hook_return_value_consumed_by_block_51",
        "sequence_positions_edited_in_cached_pilot_forward": "final_position_only",
        "required_hook_fire_count": 1,
        "exact_sentinel": "bfloat16_h50_post_bytes_equal_bfloat16_h50_pre_plus_vector",
    },
    "sae": {
        "source_module": "model.model.layers[50]",
        "source_layer": 50,
        "source_location": "post_block_output",
        "normalization": "none",
        "activation": "relu(h @ encoder_linear.weight.T + encoder_linear.bias)",
        "encoder_weight_shape": (65536, 8192),
        "encoder_bias_shape": (65536,),
        "decoder_weight_shape": (8192, 65536),
        "decoder_bias_shape": (8192,),
        "intervention_direction": "decoder_linear.weight_columns_without_decoder_bias",
        "public_provenance": {
            "model_card_layer": 50,
            "release_history_module_name": "model.layers.50",
            "linked_notebook_convention": "l19_reads_model.layers.19_module.output",
        },
        "proprietary_api_equivalence": False,
    },
    "j_lens": {
        "source_layers": tuple(range(45, 79)),
        "source_location": "post_block_output",
        "target_layer": 79,
        "target_location": "post_block_output",
        "orientation": "row_residual_at_j_transpose",
        "matrix_shape": (8192, 8192),
    },
    "actual_final": {
        "capture_module": "model.model.norm",
        "capture_hook": "forward_pre_hook_input_zero",
        "captured_tensor": "post_block_79_pre_final_rmsnorm_residual",
        "projection": "pinned_final_rmsnorm_then_lm_head",
        "logit_position": "same_measured_forward_last_position_predicting_x_(T+1)",
    },
}
AUDITED_GATE_CONSEQUENCE_POLICY = {
    "overall_pass": {
        "required_gates": ("G1", "G2", "G3", "G3P", "G4"),
        "independent_structural_audit_required": True,
        "partial_pass_is_not_target_authority": True,
    },
    "technical_invalid": {
        "conditions": (
            "missing_or_extra_grid_row",
            "nonfinite_measurement",
            "binding_or_hash_mismatch",
            "partial_or_corrupt_transaction",
            "failed_independent_structural_audit",
        ),
        "classification": "neither_scientific_pass_nor_scientific_fail",
        "rerun": (
            "fresh_output_transaction_only_with_identical_frozen_source_and_plan_"
            "before_any_valid_gate_result_is_used"
        ),
        "preserve_and_disclose_invalid_receipt": True,
    },
    "numeric_failure": {
        "terminal_under_study_id": True,
        "no_same_id_rescue": True,
        "forbidden_changes": (
            "threshold",
            "prompt_or_fixture",
            "token_or_vocabulary_panel",
            "layer_or_depth_weight",
            "dose_or_direction",
            "matching_rule_or_match",
            "vector_or_control",
            "sign_convention",
            "judge_or_endpoint",
        ),
    },
    "revision_after_pilot_inspection": {
        "requires_new_protocol_version": True,
        "requires_explicit_amendment_and_disclosure": True,
        "requires_new_untouched_validation_set": True,
        "inspected_fixtures_may_not_be_sole_positive_control": True,
    },
    "gate_failure_blocks": {
        "G1": ("all_j_lens_endpoints", "all_layerwise_j_interpretation"),
        "G2": (
            "causal_or_differential_j_transport_claims",
            "intervention_change_j_endpoints",
        ),
        "G3": ("successor_semantic_consciousness_awareness_j_endpoints",),
        "G3P": ("binary_report_polarity_j_endpoints", "answer_boundary_validation"),
        "G4": ("public_weight_intervention_implementation",),
    },
    "successor_boundary": {
        "pilot_g4_vectors_or_matches_importable": False,
        "successor_fresh_target_blind_preflight_required_regardless_of_pilot_pass": True,
        "pilot_pass_never_authorizes_target_execution_by_itself": True,
    },
}
PHASE_ROW_FILENAMES = {
    "G1": ("g1_rows.jsonl",),
    "G2": ("g2_transport_rows.jsonl", "g2_linearity_rows.jsonl"),
    "G3": ("g3_rows.jsonl",),
    "G3P": ("g3p_rows.jsonl",),
    "G4": ("g4_clean_rows.jsonl", "g4_vector_rows.jsonl", "g4_telemetry_rows.jsonl"),
}
PHASE_DIRECTORY_NAMES = {
    "G1": "g1_transport_arithmetic",
    "G2": "g2_neutral_transport",
    "G3": "g3_clean_semantic_readout",
    "G3P": "g3p_clean_polarity",
    "G4": "g4_vector_safety",
}
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
PLAN_MANIFEST_FIELDS = frozenset(
    {
        "schema_version",
        "study_slug",
        "study_id",
        "protocol_version",
        "status",
        "files",
        "canonical_payload_sha256",
        "hash_semantics",
        "plan_manifest_sha256",
    }
)
PLAN_FILE_RECORD_FIELDS = frozenset({"filename", "content_sha256", "size_bytes"})
BOUND_REPOSITORY_PATHS = (
    "experiments/consciousness_readout_validation/__init__.py",
    "experiments/consciousness_readout_validation/README.md",
    "experiments/consciousness_readout_validation/analysis.py",
    "experiments/consciousness_readout_validation/analyze_pilot.py",
    "experiments/consciousness_readout_validation/audit_pilot.py",
    "experiments/consciousness_readout_validation/build_execution_binding.py",
    "experiments/consciousness_readout_validation/build_plan.py",
    "experiments/consciousness_readout_validation/fixtures.py",
    "experiments/consciousness_readout_validation/guest_attestation.py",
    "experiments/consciousness_readout_validation/gpu_runner.py",
    "experiments/consciousness_readout_validation/inventory.py",
    "experiments/consciousness_readout_validation/paths.py",
    "experiments/consciousness_readout_validation/protocol.py",
    "experiments/consciousness_readout_validation/requirements-runpod-b200.txt",
    "experiments/consciousness_readout_validation/run_guest_preflight.sh",
    "experiments/consciousness_readout_validation/run_pilot_runpod.sh",
    "experiments/consciousness_readout_validation/runpod_lifecycle.py",
    "experiments/consciousness_readout_validation/runtime.py",
    "experiments/consciousness_readout_validation/stage_public_artifacts.py",
    "experiments/consciousness_readout_validation/tokenizer_audit.py",
    "experiments/consciousness_readout_validation/validate_plan.py",
    "tests/consciousness_readout_validation/__init__.py",
    "tests/consciousness_readout_validation/test_analysis.py",
    "tests/consciousness_readout_validation/test_analyze_pilot.py",
    "tests/consciousness_readout_validation/test_audit_pilot.py",
    "tests/consciousness_readout_validation/test_build_execution_binding.py",
    "tests/consciousness_readout_validation/test_guest_attestation.py",
    "tests/consciousness_readout_validation/test_guest_preflight_wrapper.py",
    "tests/consciousness_readout_validation/test_gpu_runner.py",
    "tests/consciousness_readout_validation/test_paths.py",
    "tests/consciousness_readout_validation/test_plan.py",
    "tests/consciousness_readout_validation/test_protocol.py",
    "tests/consciousness_readout_validation/test_runpod_lifecycle.py",
    "tests/consciousness_readout_validation/test_runtime.py",
    "tests/consciousness_readout_validation/test_stage_public_artifacts.py",
    "tests/consciousness_readout_validation/test_tokenizer_audit.py",
    "docs/consciousness_readout_validation/README.md",
    "docs/consciousness_readout_validation/PROTOCOL.md",
    "docs/consciousness_sae_switch_arc/PRO_REVIEW_RECEIPT.json",
    "docs/consciousness_sae_switch_arc/PRO_REVIEW_ADJUDICATION.md",
    "data/consciousness_readout_validation/README.md",
)

LINEAGE_FIELDS = frozenset(
    {
        "study_id",
        "protocol_version",
        "plan_manifest_sha256",
        "run_id",
        "task_id",
        "row_id",
    }
)
MEASUREMENT_FIELDS: dict[str, frozenset[str]] = {
    "g1_rows.jsonl": frozenset(
        {
            "layer",
            "synthetic_residual_id",
            "vocab_ids",
            "map_shape_valid",
            "map_finite",
            "production_finite",
            "reference_finite",
            "relative_rmse",
            "selected_logit_sign_agreement",
            "wrong_orientation_differs",
        }
    ),
    "g2_transport_rows.jsonl": frozenset(
        {
            "prompt_id",
            "layer",
            "direction",
            "transport",
            "signed_pair_complete",
            "residual_delta_cosine",
            "fixed_token_logit_delta_pearson",
            "finite",
        }
    ),
    "g2_linearity_rows.jsonl": frozenset(
        {
            "prompt_id",
            "layer",
            "direction",
            "central_difference_cosine",
            "slope_discrepancy",
            "finite",
        }
    ),
    "g3_rows.jsonl": frozenset(
        {
            "prompt_id",
            "true_family",
            "item_index",
            "render_mode",
            "transport",
            "layer",
            "token_logits",
            "finite",
        }
    ),
    "g3p_rows.jsonl": frozenset(
        {
            "prompt_id",
            "expected_answer",
            "transport",
            "layer",
            "yes_logit",
            "no_logit",
            "finite",
        }
    ),
    "g4_clean_rows.jsonl": frozenset({"prompt_id", "h50_pre_rms", "finite"}),
    "g4_vector_rows.jsonl": frozenset(
        {
            "subset_feature_ids",
            "control_type",
            "sign",
            "coefficient",
            "vector_rms",
            "vector_sha256",
            "dtype",
            "finite",
            "precomputed_before_any_edited_forward",
            "edited_forward_count_at_compute",
        }
    ),
    "g4_telemetry_rows.jsonl": frozenset(
        {
            "prompt_id",
            "subset_feature_ids",
            "control_type",
            "sign",
            "coefficient",
            "vector_sha256",
            "input_token_ids_sha256",
            "clean_input_token_ids_sha256",
            "clean_pre_edit_sha256",
            "edited_pre_edit_sha256",
            "expected_post_edit_sha256",
            "observed_post_edit_sha256",
            "clean_output_sha256",
            "sham_output_sha256",
            "realized_delta_relative_rmse",
            "sign_cosine",
            "hook_fire_count",
            "downstream_finite",
            "logits_finite",
            "attenuation_attempted",
            "retry_count",
        }
    ),
}
MEASUREMENT_KINDS = {
    "g1_rows.jsonl": "g1",
    "g2_transport_rows.jsonl": "g2_transport",
    "g2_linearity_rows.jsonl": "g2_linearity",
    "g3_rows.jsonl": "g3",
    "g3p_rows.jsonl": "g3p",
    "g4_clean_rows.jsonl": "g4_clean",
    "g4_vector_rows.jsonl": "g4_vector",
    "g4_telemetry_rows.jsonl": "g4_telemetry",
}

PHASE_BINDING_FIELDS = frozenset(
    {
        "schema_version",
        "status",
        "binding_kind",
        "study_id",
        "protocol_version",
        "phase",
        "run_id",
        "plan_manifest_sha256",
        "execution_binding_canonical_sha256",
        "tokenizer_audit_receipt_sha256",
        "tokenizer_inventory_sha256",
        "runtime_adapter",
        "prior_outcome_inputs",
        "target_prompt_inputs",
        "target_outcome_inputs",
        "receipt_sha256",
    }
)
RUNTIME_METADATA_FIELDS = frozenset(
    {
        "schema_version",
        "status",
        "metadata_kind",
        "study_id",
        "protocol_version",
        "phase",
        "run_id",
        "plan_manifest_sha256",
        "execution_binding_canonical_sha256",
        "tokenizer_audit_receipt_sha256",
        "runtime_adapter",
        "hook_contract",
        "container_image",
        "model",
        "sae",
        "j_lens",
        "hardware",
        "software",
        "determinism",
        "model_weights_loaded",
        "model_forward_count",
        "first_model_forward_at_utc",
        "last_model_forward_at_utc",
        "prior_outcome_inputs",
        "target_prompt_inputs",
        "target_outcome_inputs",
        "receipt_sha256",
    }
)
FILE_MANIFEST_FIELDS = frozenset(
    {
        "schema_version",
        "study_id",
        "phase",
        "run_id",
        "plan_manifest_sha256",
        "execution_binding_canonical_sha256",
        "row_counts",
        "files",
        "manifest_sha256",
    }
)
FILE_RECORD_FIELDS = frozenset({"path", "bytes", "sha256"})
MEASUREMENT_RECORD_FIELDS = frozenset(
    {"row_count", "content_sha256", "logical_rows_sha256"}
)
EXECUTION_BINDING_FIELDS = frozenset(
    {
        "schema_version",
        "status",
        "binding_kind",
        "study_id",
        "protocol_version",
        "plan_manifest_sha256",
        "plan_validation_receipt_sha256",
        "resolved_external_root_id",
        "container_image",
        "runtime_adapter",
        "runtime_adapter_source_sha256",
        "tokenizer_content_inventory_sha256",
        "tokenizer_audit_receipt_sha256",
        "artifacts",
        "model_weights_loaded",
        "model_forward_count",
        "prior_outcome_inputs",
        "target_prompt_inputs",
        "target_outcome_inputs",
        "execution_binding_canonical_sha256",
    }
)

TOKENIZER_FIELDS = frozenset(
    {
        "schema_version",
        "study_id",
        "protocol_version",
        "status",
        "model_weights_loaded",
        "model_forward_count",
        "plan_manifest_sha256",
        "tokenizer_repository",
        "tokenizer_revision",
        "tokenizer_inventory_sha256",
        "g1",
        "semantic",
        "polarity",
        "receipt_sha256",
    }
)
G1_AUDIT_FIELDS = frozenset(
    {
        "candidate_sequence",
        "accepted_token_ids",
        "accepted_exact_token_pieces",
        "rejected_token_ids_and_reasons",
        "special_token_ids",
        "experimental_lexicon_token_ids",
        "selection_rule_sha256",
        "token_panel_canonical_sha256",
    }
)
G1_CANDIDATE_FIELDS = frozenset(
    {
        "sequence_index",
        "panel_index",
        "attempt",
        "token_id",
        "exact_piece",
        "decision",
        "reason",
    }
)
G1_REJECTED_FIELDS = frozenset(
    {
        "sequence_index",
        "panel_index",
        "attempt",
        "token_id",
        "exact_piece",
        "reason",
    }
)

VECTOR_INVENTORY_FIELDS = frozenset(
    {
        "schema_version",
        "study_id",
        "protocol_version",
        "status",
        "plan_manifest_sha256",
        "sae_sha256",
        "decoder_bfloat16_sha256",
        "matching_spec_sha256",
        "vector_arithmetic_spec_sha256",
        "matching_candidate_inventory_sha256",
        "target_feature_ids",
        "excluded_feature_ids",
        "target_to_matched",
        "vectors",
        "receipt_sha256",
    }
)
MATCH_ROW_FIELDS = frozenset(
    {"target_feature_id", "matched_feature_id", "scaled_distance"}
)
VECTOR_ROW_FIELDS = frozenset(
    {
        "assignment_id",
        "subset_feature_ids",
        "control_type",
        "sign",
        "coefficient",
        "resolved_feature_ids",
        "isotropic_seed",
        "raw_norm",
        "raw_vector_sha256",
        "norm_rescale",
        "final_norm",
        "norm_relative_error",
        "target_reference_final_norm",
        "vector_rms",
        "vector_sha256",
        "dtype",
        "finite",
        "precomputed_before_any_edited_forward",
        "edited_forward_count_at_compute",
        "positive_vector_sha256",
        "negative_vector_sha256",
        "signed_pair_exact_negation",
        "signed_pair_relation_sha256",
    }
)
MATCHING_TABLE_FIELDS = frozenset(
    {
        "feature_id",
        "decoder_l2_norm",
        "mean_positive_activation",
        "max_positive_activation",
        "positive_activation_fraction",
        "transformed_coordinates",
        "scaled_coordinates",
        "eligible_candidate",
        "exclusion_reasons",
    }
)


class StructuralAuditError(RuntimeError):
    """A stable, fail-closed structural finding."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message


def _fail(code: str, message: str) -> None:
    raise StructuralAuditError(code, message)


def _require_fields(value: Any, fields: frozenset[str], label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or set(value) != fields:
        actual = set(value) if isinstance(value, Mapping) else set()
        _fail(
            "schema",
            f"{label} fields differ; missing={sorted(fields - actual)}, "
            f"extra={sorted(actual - fields)}",
        )
    return value


def _hex64(value: Any, label: str) -> str:
    if not isinstance(value, str) or HEX64.fullmatch(value) is None:
        _fail("hash", f"{label} is not lowercase SHA-256 text")
    return value


def _integer(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        _fail("type", f"{label} must be an integer")
    return value


def _number(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        _fail("type", f"{label} must be numeric")
    result = float(value)
    if not math.isfinite(result):
        _fail("nonfinite", f"{label} must be finite")
    return result


def _boolean(value: Any, label: str) -> bool:
    if type(value) is not bool:
        _fail("type", f"{label} must be a JSON boolean")
    return value


def _embedded_hash(value: Mapping[str, Any], field: str, label: str) -> str:
    digest = _hex64(value.get(field), f"{label} {field}")
    core = dict(value)
    del core[field]
    if protocol.canonical_sha256(core) != digest:
        _fail("self_hash", f"{label} self-hash does not reconstruct")
    return digest


def _sha256_file(path: Path, *, chunk_bytes: int = 8 * 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(chunk_bytes):
            digest.update(chunk)
    return digest.hexdigest()


def _load_json(path: Path, label: str) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        _fail("unsafe_file", f"{label} is missing, non-file, or a symlink: {path}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise StructuralAuditError("json", f"cannot read {label}: {path}") from exc
    if not isinstance(value, dict):
        _fail("schema", f"{label} must be a JSON object")
    return value


def _assert_empty_inputs(value: Any, *, label: str, location: str = "$") -> None:
    empty_fields = {
        "prior_outcome_inputs",
        "target_prompt_inputs",
        "target_outcome_inputs",
    }
    if isinstance(value, Mapping):
        for key, child in value.items():
            if key in empty_fields and child not in ([], ()):
                _fail("forbidden_input", f"{label} has nonempty {location}.{key}")
            _assert_empty_inputs(child, label=label, location=f"{location}.{key}")
    elif isinstance(value, (list, tuple)):
        for index, child in enumerate(value):
            _assert_empty_inputs(child, label=label, location=f"{location}[{index}]")
    elif isinstance(value, str):
        normalized = value.lower().replace("\\", "/")
        for marker in protocol.public_input_allowlist()["forbidden_path_markers"]:
            if marker.lower() in normalized:
                _fail("forbidden_input", f"{label} names prior-study material at {location}")


def _scan_result_free(value: Any, *, label: str, location: str = "$") -> None:
    forbidden_result_keys = {
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
    if isinstance(value, Mapping):
        for key, child in value.items():
            if key in forbidden_result_keys:
                _fail("result_free_plan", f"{label} contains result field {location}.{key}")
            if key in {"prior_outcome_inputs", "target_prompt_inputs", "target_outcome_inputs"} and child not in ([], ()):
                _fail("result_free_plan", f"{label} contains nonempty {location}.{key}")
            _scan_result_free(child, label=label, location=f"{location}.{key}")
    elif isinstance(value, (list, tuple)):
        for index, child in enumerate(value):
            _scan_result_free(child, label=label, location=f"{location}[{index}]")
    elif isinstance(value, str) and value.startswith(("/", "~/")):
        _fail("result_free_plan", f"{label} contains an absolute path at {location}")


def _expected_source_inventory(repo_root: Path) -> dict[str, Any]:
    records: list[dict[str, Any]] = []
    for relative in BOUND_REPOSITORY_PATHS:
        path = repo_root / relative
        if path.is_symlink() or not path.is_file():
            _fail("source_inventory", f"bound repository path is missing/unsafe: {relative}")
        role = (
            "source"
            if relative.startswith("experiments/")
            else "test"
            if relative.startswith("tests/")
            else "governing_document"
        )
        records.append(
            {
                "path": relative,
                "role": role,
                "content_sha256": _sha256_file(path),
                "size_bytes": path.stat().st_size,
            }
        )
    return {
        "schema_version": protocol.PLAN_SCHEMA_VERSION,
        "study_id": protocol.STUDY_ID,
        "hash_semantics": "content_sha256 hashes exact repository file bytes",
        "files": tuple(records),
    }


def _expected_plan_payloads(repo_root: Path) -> dict[str, bytes]:
    artifact_bindings = {
        "schema_version": protocol.PLAN_SCHEMA_VERSION,
        "study_id": protocol.STUDY_ID,
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
            "model": protocol.MODEL_SPEC,
            "sae": protocol.SAE_SPEC,
            "j_lens": protocol.J_LENS_SPEC,
        },
        "container_image": protocol.CONTAINER_IMAGE_SPEC,
        "required_execution_receipt_fields": AUDITED_REQUIRED_EXECUTION_BINDING_PATHS,
    }
    token_metadata = {
        "schema_version": protocol.PLAN_SCHEMA_VERSION,
        "study_id": protocol.STUDY_ID,
        "binding_status": "tokenizer_audit_required_before_any_forward",
        "semantic_token_groups": protocol.G3_TOKEN_GROUPS,
        "semantic_token_ids": {},
        "semantic_tokenization_contract": protocol.G3_TOKENIZATION_CONTRACT,
        "polarity_display_labels": ("Yes", "No"),
        "polarity_token_pieces": ("Yes", "No"),
        "polarity_token_ids": protocol.G3P_ANSWER_TOKEN_IDS,
        "polarity_eot_token_id": protocol.G3P_EOT_TOKEN_ID,
        "polarity_tokenization_contract": protocol.G3P_CONTEXT_TOKENIZATION_CONTRACT,
        "g1_hash_selected_lexical_token_ids": protocol.G1_HASH_SELECTED_LEXICAL_TOKEN_IDS,
        "g1_token_panel_status": "unresolved_tokenizer_audit_required",
        "g1_token_selection_rule": protocol.G1_TOKEN_SELECTION_RULE,
        "g1_rejection_lexicon": protocol.G1_TOKEN_REJECTION_LEXICON,
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
                "seeds": tuple(
                    protocol.g2_random_j_seed(layer, index)
                    for index in range(protocol.G2_RANDOM_CONTROL_COUNT)
                ),
            }
            for layer in range(45, 79)
        ),
    }

    def json_bytes(value: Any) -> bytes:
        return protocol.canonical_json_bytes(value) + b"\n"

    def jsonl_bytes(rows: Iterable[Mapping[str, Any]]) -> bytes:
        return b"".join(protocol.canonical_json_bytes(row) + b"\n" for row in rows)

    return {
        "protocol_snapshot.json": json_bytes(protocol.protocol_snapshot()),
        "input_allowlist.json": json_bytes(protocol.public_input_allowlist()),
        "artifact_bindings.json": json_bytes(artifact_bindings),
        "token_metadata.json": json_bytes(token_metadata),
        "neutral_prompts.jsonl": jsonl_bytes(protocol.neutral_prompts()),
        "g1_plan.jsonl": jsonl_bytes(protocol.g1_plan_rows()),
        "g2_plan.jsonl": jsonl_bytes(protocol.g2_plan_rows()),
        "g3_fixtures.jsonl": jsonl_bytes(protocol.g3_fixture_rows()),
        "g3p_fixtures.jsonl": jsonl_bytes(protocol.g3p_plan_rows()),
        "g4_assignments.jsonl": jsonl_bytes(protocol.g4_aggregate_assignments()),
        "g4_plan.jsonl": jsonl_bytes(protocol.g4_plan_rows()),
        "source_inventory.json": json_bytes(_expected_source_inventory(repo_root)),
    }


def validate_plan_independently(plan_dir: Path, *, repo_root: Path) -> dict[str, Any]:
    """Rehash the complete plan before optionally applying its canonical rebuilder."""

    if plan_dir.is_symlink() or not plan_dir.is_dir():
        _fail("plan_path", "plan directory is missing, non-directory, or a symlink")
    actual = {entry.name for entry in plan_dir.iterdir()}
    expected = {*PLAN_PAYLOAD_FILES, "PLAN_MANIFEST.json"}
    if actual != expected:
        _fail("plan_files", f"plan file set differs: missing={sorted(expected-actual)}, extra={sorted(actual-expected)}")
    for entry in plan_dir.iterdir():
        if entry.is_symlink() or not entry.is_file():
            _fail("plan_files", f"unsafe plan entry: {entry.name}")
    expected_payloads = _expected_plan_payloads(repo_root)
    if tuple(expected_payloads) != PLAN_PAYLOAD_FILES:
        _fail("plan_reconstruction", "independent payload order differs")
    manifest = _load_json(plan_dir / "PLAN_MANIFEST.json", "plan manifest")
    _require_fields(manifest, PLAN_MANIFEST_FIELDS, "plan manifest")
    if (
        manifest.get("schema_version") != protocol.PLAN_SCHEMA_VERSION
        or manifest.get("study_slug") != protocol.STUDY_SLUG
        or manifest.get("study_id") != protocol.STUDY_ID
        or manifest.get("protocol_version") != protocol.PROTOCOL_VERSION
        or manifest.get("status") != "target_blind_pilot_plan_execution_bindings_unresolved"
    ):
        _fail("plan_identity", "plan manifest identity/status differs")
    expected_hash_semantics = {
        "content_sha256": "SHA-256 of exact file bytes, including the final newline",
        "canonical_payload_sha256": (
            "SHA-256 of canonical JSON over schema/study/protocol and ordered file records"
        ),
        "plan_manifest_sha256": (
            "SHA-256 of canonical JSON over this manifest excluding only this field"
        ),
    }
    if manifest.get("hash_semantics") != expected_hash_semantics:
        _fail("plan_identity", "plan manifest hash semantics differ")
    records = manifest["files"]
    if not isinstance(records, list) or len(records) != len(PLAN_PAYLOAD_FILES):
        _fail("plan_files", "plan manifest record count differs")
    validated_records: list[dict[str, Any]] = []
    for offset, (expected_name, record) in enumerate(zip(PLAN_PAYLOAD_FILES, records)):
        _require_fields(record, PLAN_FILE_RECORD_FIELDS, f"plan file record {offset}")
        if record["filename"] != expected_name:
            _fail("plan_files", "plan manifest file order differs")
        path = plan_dir / expected_name
        observed_bytes = path.read_bytes()
        if observed_bytes != expected_payloads[expected_name]:
            _fail("plan_reconstruction", f"plan payload does not exactly rebuild: {expected_name}")
        observed_hash = _sha256_file(path)
        if record["content_sha256"] != observed_hash or record["size_bytes"] != path.stat().st_size:
            _fail("plan_files", f"plan payload bytes differ: {expected_name}")
        validated_records.append(dict(record))
        try:
            if expected_name.endswith(".jsonl"):
                values = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
            else:
                values = [json.loads(path.read_text(encoding="utf-8"))]
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise StructuralAuditError("plan_json", f"invalid JSON payload: {expected_name}") from exc
        for value in values:
            _scan_result_free(value, label=expected_name)
        if expected_name == "protocol_snapshot.json":
            snapshot = values[0]
            if not isinstance(snapshot, Mapping) or snapshot.get("measurement_lineage_spec") != protocol.MEASUREMENT_LINEAGE_SPEC:
                _fail("lineage_spec", "plan does not contain the frozen measurement-lineage specification")
            if protocol.canonical_sha256(snapshot.get("hook_contract")) != protocol.canonical_sha256(
                AUDITED_HOOK_CONTRACT
            ):
                _fail("hook_contract", "plan does not contain the independently frozen hook contract")
            if protocol.canonical_sha256(
                snapshot.get("gate_consequence_policy")
            ) != protocol.canonical_sha256(AUDITED_GATE_CONSEQUENCE_POLICY):
                _fail(
                    "gate_consequence_policy",
                    "plan does not contain the independently frozen gate consequence policy",
                )
    canonical_payload = {
        "schema_version": protocol.PLAN_SCHEMA_VERSION,
        "study_id": protocol.STUDY_ID,
        "protocol_version": protocol.PROTOCOL_VERSION,
        "files": validated_records,
    }
    if manifest["canonical_payload_sha256"] != protocol.canonical_sha256(canonical_payload):
        _fail("plan_hash", "plan canonical-payload hash does not reconstruct")
    plan_hash = _embedded_hash(manifest, "plan_manifest_sha256", "plan manifest")
    return {
        "plan_manifest_sha256": plan_hash,
        "manifest_file_sha256": _sha256_file(plan_dir / "PLAN_MANIFEST.json"),
    }


def _source_bindings(
    plan_dir: Path, repo_root: Path, *, plan_manifest_sha256: str
) -> tuple[str, str]:
    inventory_path = plan_dir / "source_inventory.json"
    manifest = _load_json(plan_dir / "PLAN_MANIFEST.json", "plan manifest")
    if manifest.get("plan_manifest_sha256") != plan_manifest_sha256:
        _fail("plan_binding", "validated plan hash changed during audit")
    file_records = manifest.get("files")
    if not isinstance(file_records, list):
        _fail("plan_binding", "plan manifest file inventory is malformed")
    by_filename = {
        record.get("filename"): record
        for record in file_records
        if isinstance(record, Mapping)
    }
    source_bytes_hash = _sha256_file(inventory_path)
    source_manifest_record = by_filename.get("source_inventory.json")
    if (
        not isinstance(source_manifest_record, Mapping)
        or source_manifest_record.get("content_sha256") != source_bytes_hash
        or source_manifest_record.get("size_bytes") != inventory_path.stat().st_size
    ):
        _fail("source_inventory", "source inventory bytes differ from PLAN_MANIFEST")
    inventory = _load_json(inventory_path, "source inventory")
    rows = inventory.get("files")
    if not isinstance(rows, list):
        _fail("source_inventory", "source inventory file rows are malformed")
    indexed: dict[str, Mapping[str, Any]] = {}
    for offset, row in enumerate(rows):
        _require_fields(
            row,
            frozenset({"path", "role", "content_sha256", "size_bytes"}),
            f"source inventory row {offset}",
        )
        relative = row["path"]
        if not isinstance(relative, str) or relative in indexed:
            _fail("source_inventory", "source inventory paths are malformed or duplicated")
        indexed[relative] = row
    for required in (AUDIT_SOURCE_RELATIVE_PATH, AUDIT_TEST_RELATIVE_PATH):
        row = indexed.get(required)
        candidate = repo_root / required
        if row is None or candidate.is_symlink() or not candidate.is_file():
            _fail("audit_source", f"bound audit file is missing: {required}")
        observed = _sha256_file(candidate)
        if row.get("content_sha256") != observed or row.get("size_bytes") != candidate.stat().st_size:
            _fail("audit_source", f"bound audit file changed: {required}")
        if row.get("role") != ("source" if required == AUDIT_SOURCE_RELATIVE_PATH else "test"):
            _fail("audit_source", f"bound audit file has wrong role: {required}")
    return source_bytes_hash, str(indexed[AUDIT_SOURCE_RELATIVE_PATH]["content_sha256"])


def _validate_execution_and_artifacts(
    execution_binding_path: Path,
    *,
    plan_manifest_sha256: str,
    artifact_root: Path,
    volume_id: str,
    repo_root: Path,
) -> tuple[dict[str, Any], dict[str, Path]]:
    """Independently rehash the execution binding and every pinned public artifact."""

    binding = _load_json(execution_binding_path, "execution binding")
    _require_fields(binding, EXECUTION_BINDING_FIELDS, "execution binding")
    execution_hash = _embedded_hash(
        binding, "execution_binding_canonical_sha256", "execution binding"
    )
    if (
        binding.get("schema_version") != 1
        or binding.get("status") != "pass"
        or binding.get("binding_kind") != "target_blind_pilot_execution_binding_v1"
        or binding.get("study_id") != protocol.STUDY_ID
        or binding.get("protocol_version") != protocol.PROTOCOL_VERSION
        or binding.get("plan_manifest_sha256") != plan_manifest_sha256
        or binding.get("runtime_adapter") != "gpu_phase_adapter_v1"
        or binding.get("resolved_external_root_id") != volume_id
        or binding.get("container_image") != protocol.CONTAINER_IMAGE_SPEC
        or binding.get("model_weights_loaded") is not False
        or binding.get("model_forward_count") != 0
    ):
        _fail("execution_binding", "execution-binding identity/runtime/root differs")
    for field in ("prior_outcome_inputs", "target_prompt_inputs", "target_outcome_inputs"):
        if binding.get(field) not in ([], ()):
            _fail("forbidden_input", f"execution binding has nonempty {field}")
    tokenizer_inventory = _hex64(
        binding.get("tokenizer_content_inventory_sha256"),
        "execution tokenizer inventory",
    )
    _hex64(binding.get("plan_validation_receipt_sha256"), "plan-validation receipt")
    _hex64(binding.get("tokenizer_audit_receipt_sha256"), "bound tokenizer audit receipt")
    adapter_source = repo_root / "experiments/consciousness_readout_validation/gpu_runner.py"
    if (
        adapter_source.is_symlink()
        or not adapter_source.is_file()
        or binding.get("runtime_adapter_source_sha256") != _sha256_file(adapter_source)
    ):
        _fail("execution_binding", "execution binding names another GPU adapter source")
    _assert_empty_inputs(binding, label="execution binding")
    for dotted_path in AUDITED_REQUIRED_EXECUTION_BINDING_PATHS:
        current: Any = binding
        for component in dotted_path.split("."):
            if not isinstance(current, Mapping) or component not in current:
                _fail(
                    "execution_binding",
                    f"required execution-binding path is absent: {dotted_path}",
                )
            current = current[component]
        if current is None:
            _fail(
                "execution_binding",
                f"required execution-binding path is null: {dotted_path}",
            )

    root = artifact_root.resolve(strict=True)
    repository = repo_root.resolve(strict=True)
    if artifact_root.is_symlink() or not root.is_dir():
        _fail("artifact_root", "artifact root is missing, non-directory, or a symlink")
    try:
        root.relative_to(repository)
    except ValueError:
        pass
    else:
        _fail("artifact_root", "artifact root must be outside the repository")
    sentinel = _load_json(root / VOLUME_SENTINEL, "artifact-volume sentinel")
    expected_sentinel = {
        "study_slug": protocol.STUDY_SLUG,
        "study_id": protocol.STUDY_ID,
        "volume_id": volume_id,
    }
    if any(sentinel.get(key) != value for key, value in expected_sentinel.items()):
        _fail("artifact_root", "artifact-volume sentinel differs")
    public_root_path = root / protocol.STUDY_SLUG / protocol.STUDY_ID / "public_artifacts"
    if public_root_path.is_symlink():
        _fail("artifact_root", "pilot public-artifact directory is a symlink")
    public_root = public_root_path.resolve(strict=True)
    if not public_root.is_dir():
        _fail("artifact_root", "pilot public-artifact directory is unsafe")

    artifacts = binding.get("artifacts")
    if not isinstance(artifacts, Mapping) or set(artifacts) != {"model_snapshot", "sae", "j_lens"}:
        _fail("artifact_binding", "execution artifact inventory differs")
    frozen_by_name = {
        "model_snapshot": protocol.MODEL_SPEC,
        "sae": protocol.SAE_SPEC,
        "j_lens": protocol.J_LENS_SPEC,
    }
    resolved: dict[str, Path] = {}
    for name, frozen in frozen_by_name.items():
        record = artifacts[name]
        if not isinstance(record, Mapping) or not isinstance(record.get("path"), str):
            _fail("artifact_binding", f"{name} binding is malformed")
        raw_candidate = Path(record["path"])
        if raw_candidate.is_symlink():
            _fail("artifact_path", f"{name} path is a symlink")
        candidate = raw_candidate.resolve(strict=True)
        try:
            candidate.relative_to(public_root)
        except ValueError as exc:
            raise StructuralAuditError("artifact_path", f"{name} escapes public cache") from exc
        if candidate.is_symlink() or not candidate.exists():
            _fail("artifact_path", f"{name} path is unsafe")
        if record.get("repository") != frozen["repository"] or record.get("revision") != frozen["revision"]:
            _fail("artifact_identity", f"{name} repository/revision differs")
        if name == "model_snapshot":
            _require_fields(
                record,
                frozenset({"path", "repository", "revision", "files", "file_inventory_sha256"}),
                "model snapshot binding",
            )
            if not candidate.is_dir():
                _fail("artifact_path", "model snapshot must be a directory")
        elif name == "sae":
            _require_fields(
                record,
                frozenset(
                    {
                        "path",
                        "readme_path",
                        "config_path",
                        "repository",
                        "revision",
                        "filename",
                        "sha256",
                        "readme_filename",
                        "readme_sha256",
                        "config_filename",
                        "config_sha256",
                    }
                ),
                f"{name} binding",
            )
            if record.get("filename") != frozen["filename"]:
                _fail("artifact_identity", f"{name} filename differs")
            if not candidate.is_file() or record.get("sha256") != frozen["sha256"] or _sha256_file(candidate) != frozen["sha256"]:
                _fail("artifact_hash", f"{name} bytes differ from the public pin")
            sidecars = frozen.get("sidecars")
            if (
                not isinstance(sidecars, Mapping)
                or sidecars.get("readme")
                != {
                    "filename": EXPECTED_SAE_README_FILENAME,
                    "sha256": EXPECTED_SAE_README_SHA256,
                }
                or sidecars.get("config")
                != {
                    "filename": EXPECTED_SAE_CONFIG_FILENAME,
                    "sha256": EXPECTED_SAE_CONFIG_SHA256,
                }
            ):
                _fail("artifact_identity", "frozen SAE sidecar pins differ")
            for sidecar, expected_filename, expected_hash in (
                ("readme", EXPECTED_SAE_README_FILENAME, EXPECTED_SAE_README_SHA256),
                ("config", EXPECTED_SAE_CONFIG_FILENAME, EXPECTED_SAE_CONFIG_SHA256),
            ):
                path_field = f"{sidecar}_path"
                filename_field = f"{sidecar}_filename"
                hash_field = f"{sidecar}_sha256"
                if not isinstance(record.get(path_field), str):
                    _fail("artifact_binding", f"SAE {sidecar} path is malformed")
                raw_sidecar = Path(record[path_field])
                if raw_sidecar.is_symlink():
                    _fail("artifact_path", f"SAE {sidecar} path is a symlink")
                sidecar_candidate = raw_sidecar.resolve(strict=True)
                try:
                    sidecar_candidate.relative_to(public_root)
                except ValueError as exc:
                    raise StructuralAuditError(
                        "artifact_path", f"SAE {sidecar} escapes public cache"
                    ) from exc
                if (
                    sidecar_candidate.is_symlink()
                    or not sidecar_candidate.is_file()
                    or record.get(filename_field) != expected_filename
                    or record.get(hash_field) != expected_hash
                    or _sha256_file(sidecar_candidate) != expected_hash
                ):
                    _fail(
                        "artifact_hash",
                        f"SAE {sidecar} bytes differ from the public pin",
                    )
                resolved[f"sae_{sidecar}"] = sidecar_candidate
        else:
            _require_fields(
                record,
                frozenset(
                    {
                        "path",
                        "config_path",
                        "repository",
                        "revision",
                        "filename",
                        "sha256",
                        "config_filename",
                        "config_sha256",
                    }
                ),
                "J-lens binding",
            )
            if record.get("filename") != frozen["filename"]:
                _fail("artifact_identity", "j_lens filename differs")
            if (
                not candidate.is_file()
                or record.get("sha256") != frozen["sha256"]
                or _sha256_file(candidate) != frozen["sha256"]
            ):
                _fail("artifact_hash", "j_lens bytes differ from the public pin")
            release_config = frozen.get("release_config")
            if not isinstance(release_config, Mapping):
                _fail("artifact_identity", "frozen J-lens release config is malformed")
            if (
                release_config.get("filename") != EXPECTED_J_LENS_CONFIG_FILENAME
                or release_config.get("sha256") != EXPECTED_J_LENS_CONFIG_SHA256
            ):
                _fail("artifact_identity", "frozen J-lens release-config pin differs")
            if not isinstance(record.get("config_path"), str):
                _fail("artifact_binding", "J-lens config path is malformed")
            raw_config = Path(record["config_path"])
            if raw_config.is_symlink():
                _fail("artifact_path", "J-lens config path is a symlink")
            config_candidate = raw_config.resolve(strict=True)
            try:
                config_candidate.relative_to(public_root)
            except ValueError as exc:
                raise StructuralAuditError(
                    "artifact_path", "J-lens config escapes public cache"
                ) from exc
            if (
                config_candidate.is_symlink()
                or not config_candidate.is_file()
                or record.get("config_filename") != EXPECTED_J_LENS_CONFIG_FILENAME
                or record.get("config_sha256") != EXPECTED_J_LENS_CONFIG_SHA256
                or _sha256_file(config_candidate) != EXPECTED_J_LENS_CONFIG_SHA256
            ):
                _fail("artifact_hash", "J-lens config bytes differ from the public pin")
            resolved["j_lens_config"] = config_candidate
        resolved[name] = candidate

    model_record = artifacts["model_snapshot"]
    snapshot_rows = model_record.get("files")
    if not isinstance(snapshot_rows, list) or not snapshot_rows:
        _fail("model_manifest", "model snapshot inventory is empty")
    inventory_rows: list[dict[str, str]] = []
    seen: set[str] = set()
    snapshot = resolved["model_snapshot"]
    for offset, row in enumerate(snapshot_rows):
        _require_fields(row, frozenset({"path", "sha256"}), f"model file row {offset}")
        relative = row["path"]
        if not isinstance(relative, str) or not relative or relative in seen or Path(relative).is_absolute():
            _fail("model_manifest", "model snapshot paths are malformed or duplicated")
        raw_candidate = snapshot / relative
        if raw_candidate.is_symlink():
            _fail("model_manifest", f"model file is a symlink: {relative}")
        candidate = raw_candidate.resolve(strict=True)
        try:
            candidate.relative_to(snapshot)
        except ValueError as exc:
            raise StructuralAuditError("model_manifest", "model file escapes snapshot") from exc
        expected_hash = _hex64(row["sha256"], f"model file {relative} hash")
        if candidate.is_symlink() or not candidate.is_file() or _sha256_file(candidate) != expected_hash:
            _fail("model_manifest", f"model file bytes differ: {relative}")
        seen.add(relative)
        inventory_rows.append({"path": relative, "sha256": expected_hash})
    if model_record.get("file_inventory_sha256") != protocol.canonical_sha256(inventory_rows):
        _fail("model_manifest", "model file-inventory hash differs")
    tokenizer_names = {
        "tokenizer.json",
        "tokenizer_config.json",
        "special_tokens_map.json",
        "added_tokens.json",
        "generation_config.json",
    }
    tokenizer_rows = [row for row in inventory_rows if Path(row["path"]).name in tokenizer_names]
    if not tokenizer_rows or protocol.canonical_sha256(tokenizer_rows) != tokenizer_inventory:
        _fail("artifact_hash", "tokenizer content inventory differs")
    return binding, resolved


def validate_tokenizer_receipt(
    receipt: Mapping[str, Any],
    *,
    plan_manifest_sha256: str,
    tokenizer_inventory_sha256: str,
) -> dict[str, Any]:
    """Independently reconstruct the complete G1/G3/G3P tokenizer receipt."""

    _require_fields(receipt, TOKENIZER_FIELDS, "tokenizer audit")
    if (
        receipt.get("schema_version") != 1
        or receipt.get("study_id") != protocol.STUDY_ID
        or receipt.get("protocol_version") != protocol.PROTOCOL_VERSION
        or receipt.get("status") != "pass"
        or _boolean(receipt.get("model_weights_loaded"), "tokenizer model-loaded flag")
        or _integer(receipt.get("model_forward_count"), "tokenizer forward count") != 0
        or receipt.get("plan_manifest_sha256") != plan_manifest_sha256
        or receipt.get("tokenizer_repository") != protocol.MODEL_SPEC["repository"]
        or receipt.get("tokenizer_revision") != protocol.MODEL_SPEC["revision"]
        or receipt.get("tokenizer_inventory_sha256") != tokenizer_inventory_sha256
    ):
        _fail("tokenizer_identity", "tokenizer receipt identity/model-free binding differs")
    panel_ids = _validate_g1_tokenizer(receipt["g1"])
    semantic_endpoint_ids = _validate_semantic_tokenizer(receipt["semantic"])
    _validate_polarity_tokenizer(receipt["polarity"])
    receipt_hash = _embedded_hash(receipt, "receipt_sha256", "tokenizer audit")
    return {
        "receipt_sha256": receipt_hash,
        "token_ids": panel_ids,
        "semantic_endpoint_ids": semantic_endpoint_ids,
    }


def _token_id(value: Any, label: str) -> int:
    token_id = _integer(value, label)
    if not 0 <= token_id < protocol.MODEL_SPEC["tokenizer_vocabulary_size"]:
        _fail("token_id", f"{label} is outside the pinned vocabulary")
    return token_id


def _validate_g1_tokenizer(g1: Any) -> tuple[int, ...]:
    _require_fields(g1, G1_AUDIT_FIELDS, "G1 tokenizer audit")
    sequence = g1["candidate_sequence"]
    if not isinstance(sequence, list) or not sequence:
        _fail("g1_sequence", "G1 candidate sequence is empty or malformed")
    specials = g1["special_token_ids"]
    if not isinstance(specials, list):
        _fail("g1_specials", "G1 special-token inventory is malformed")
    special_ids = [_token_id(value, "G1 special token") for value in specials]
    if special_ids != sorted(set(special_ids)):
        _fail("g1_specials", "G1 special-token inventory is not unique and sorted")
    lexicon = g1["experimental_lexicon_token_ids"]
    if not isinstance(lexicon, Mapping) or set(lexicon) != set(protocol.G1_TOKEN_REJECTION_LEXICON):
        _fail("g1_lexicon", "G1 rejection-lexicon inventory differs")
    lexicon_ids: set[int] = set()
    for word in protocol.G1_TOKEN_REJECTION_LEXICON:
        encoded = lexicon[word]
        if not isinstance(encoded, list):
            _fail("g1_lexicon", f"G1 lexicon encoding is malformed: {word}")
        lexicon_ids.update(_token_id(value, f"G1 lexicon token {word}") for value in encoded)

    accepted_ids: list[int] = []
    accepted_pieces: list[str] = []
    rejected: list[dict[str, Any]] = []
    panel_index = 0
    attempt = 0
    frozen_reasons = set(protocol.G1_TOKEN_SELECTION_RULE["reject_if"])
    rejected_words = {word.casefold() for word in protocol.G1_TOKEN_REJECTION_LEXICON}
    for offset, row in enumerate(sequence):
        _require_fields(row, G1_CANDIDATE_FIELDS, f"G1 candidate {offset}")
        if (
            _integer(row["sequence_index"], "G1 sequence index") != offset
            or _integer(row["panel_index"], "G1 panel index") != panel_index
            or _integer(row["attempt"], "G1 attempt") != attempt
        ):
            _fail("g1_sequence", "G1 candidate coordinates are not complete and ordered")
        token_id = _token_id(row["token_id"], "G1 candidate token")
        if token_id != protocol.g1_token_candidate_id(panel_index, attempt):
            _fail("g1_sequence", "G1 candidate does not follow the frozen hash stream")
        piece, decision, reason = row["exact_piece"], row["decision"], row["reason"]
        if not isinstance(piece, str) or decision not in {"accept", "reject"}:
            _fail("g1_sequence", "G1 candidate decision/piece is malformed")
        if decision == "accept":
            if (
                reason != "accepted"
                or token_id in accepted_ids
                or token_id in special_ids
                or token_id in lexicon_ids
                or ASCII_WORD.fullmatch(piece) is None
                or piece[1:].casefold() in rejected_words
            ):
                _fail("g1_accept", "G1 accepted candidate violates the frozen selector")
            accepted_ids.append(token_id)
            accepted_pieces.append(piece)
            panel_index += 1
            attempt = 0
        else:
            if reason not in frozen_reasons:
                _fail("g1_reject", "G1 candidate uses an unfrozen rejection reason")
            if reason == "duplicate_id" and token_id not in accepted_ids:
                _fail("g1_reject", "G1 duplicate rejection is unsupported")
            if reason == "special_token_id" and token_id not in special_ids:
                _fail("g1_reject", "G1 special-token rejection is unsupported")
            if (
                reason == "decoded_piece_does_not_fullmatch_ASCII_space_word_[A-Za-z]{3,16}"
                and ASCII_WORD.fullmatch(piece) is not None
            ):
                _fail("g1_reject", "G1 lexical rejection is unsupported")
            if reason == "casefolded_word_is_in_G1_TOKEN_REJECTION_LEXICON" and (
                ASCII_WORD.fullmatch(piece) is None
                or piece[1:].casefold() not in rejected_words
            ):
                _fail("g1_reject", "G1 rejection-lexicon decision is unsupported")
            rejected.append(
                {
                    "sequence_index": offset,
                    "panel_index": panel_index,
                    "attempt": attempt,
                    "token_id": token_id,
                    "exact_piece": piece,
                    "reason": reason,
                }
            )
            attempt += 1
    if panel_index != protocol.G1_TOKEN_PANEL_SIZE or attempt != 0:
        _fail("g1_sequence", "G1 sequence does not resolve exactly 32 slots")
    if g1["accepted_token_ids"] != accepted_ids or g1["accepted_exact_token_pieces"] != accepted_pieces:
        _fail("g1_projection", "G1 accepted projection differs from the full sequence")
    rejected_rows = g1["rejected_token_ids_and_reasons"]
    if not isinstance(rejected_rows, list):
        _fail("g1_projection", "G1 rejection projection is malformed")
    for offset, row in enumerate(rejected_rows):
        _require_fields(row, G1_REJECTED_FIELDS, f"G1 rejection projection {offset}")
    if rejected_rows != rejected:
        _fail("g1_projection", "G1 rejection projection differs from the full sequence")
    if g1["selection_rule_sha256"] != protocol.canonical_sha256(protocol.G1_TOKEN_SELECTION_RULE):
        _fail("g1_rule", "G1 selection-rule hash differs")
    _embedded_hash(g1, "token_panel_canonical_sha256", "G1 token panel")
    return tuple(accepted_ids)


def _validate_semantic_tokenizer(semantic: Any) -> dict[str, int]:
    _require_fields(
        semantic,
        frozenset({"groups", "ordered_union_token_ids", "contextual_boundaries"}),
        "semantic tokenizer audit",
    )
    groups = semantic["groups"]
    if not isinstance(groups, Mapping) or set(groups) != set(protocol.G3_FAMILIES):
        _fail("semantic_groups", "semantic family inventory differs")
    union: list[int] = []
    endpoint_ids: dict[str, int] = {}
    for family in protocol.G3_FAMILIES:
        rows = groups[family]
        tokens = protocol.G3_TOKEN_GROUPS[family]
        if not isinstance(rows, list) or len(rows) != len(tokens):
            _fail("semantic_groups", f"semantic endpoint count differs: {family}")
        for token, row in zip(tokens, rows):
            _require_fields(row, frozenset({"token", "piece", "token_id"}), f"semantic endpoint {token}")
            if row["token"] != token or row["piece"] != f" {token}":
                _fail("semantic_endpoint", f"semantic endpoint text differs: {token}")
            token_id = _token_id(row["token_id"], f"semantic endpoint {token}")
            union.append(token_id)
            endpoint_ids[token] = token_id
    if len(union) != len(set(union)) or semantic["ordered_union_token_ids"] != union:
        _fail("semantic_endpoint", "semantic token-ID union differs")
    contexts = semantic["contextual_boundaries"]
    fixtures = tuple(row["fixture_id"] for row in protocol.g3_fixture_rows())
    if not isinstance(contexts, list) or len(contexts) != 72:
        _fail("semantic_context", "semantic audit must contain exactly 72 contexts")
    observed: list[str] = []
    continuation_count = 0
    for offset, row in enumerate(contexts):
        _require_fields(
            row,
            frozenset(
                {
                    "fixture_id",
                    "context_token_ids_sha256",
                    "context_token_count",
                    "continuation_full_token_ids_sha256",
                }
            ),
            f"semantic context {offset}",
        )
        observed.append(str(row["fixture_id"]))
        _hex64(row["context_token_ids_sha256"], "semantic context hash")
        if _integer(row["context_token_count"], "semantic context count") <= 0:
            _fail("semantic_context", "semantic context token count must be positive")
        continuations = row["continuation_full_token_ids_sha256"]
        if not isinstance(continuations, Mapping) or set(continuations) != set(endpoint_ids):
            _fail("semantic_context", "semantic continuation inventory differs")
        for digest in continuations.values():
            _hex64(digest, "semantic continuation hash")
            continuation_count += 1
    if tuple(observed) != fixtures or continuation_count != 2016:
        _fail("semantic_context", "semantic 72/2016 audit coverage differs")
    return endpoint_ids


def _validate_polarity_tokenizer(polarity: Any) -> None:
    _require_fields(
        polarity,
        frozenset({"isolated_token_ids", "contextual_boundaries"}),
        "polarity tokenizer audit",
    )
    if polarity["isolated_token_ids"] != protocol.G3P_ANSWER_TOKEN_IDS:
        _fail("polarity_ids", "G3P isolated Yes/No IDs differ")
    contexts = polarity["contextual_boundaries"]
    prompt_ids = tuple(row["prompt_id"] for row in protocol.g3p_plan_rows())
    if not isinstance(contexts, list) or len(contexts) != 24:
        _fail("polarity_context", "G3P audit must contain exactly 24 contexts")
    observed: list[str] = []
    continuation_count = 0
    for offset, row in enumerate(contexts):
        _require_fields(
            row,
            frozenset(
                {"prompt_id", "context_token_ids_sha256", "context_token_count", "continuations"}
            ),
            f"G3P context {offset}",
        )
        observed.append(str(row["prompt_id"]))
        _hex64(row["context_token_ids_sha256"], "G3P context hash")
        if _integer(row["context_token_count"], "G3P context count") <= 0:
            _fail("polarity_context", "G3P context token count must be positive")
        continuations = row["continuations"]
        if not isinstance(continuations, Mapping) or set(continuations) != {"Yes", "No"}:
            _fail("polarity_context", "G3P continuation inventory differs")
        for piece, token_id in protocol.G3P_ANSWER_TOKEN_IDS.items():
            continuation = continuations[piece]
            _require_fields(
                continuation,
                frozenset({"token_id", "eot_token_id", "full_token_ids_sha256", "exact_suffix"}),
                f"G3P continuation {piece}",
            )
            if (
                continuation["token_id"] != token_id
                or continuation["eot_token_id"] != protocol.G3P_EOT_TOKEN_ID
                or _boolean(continuation["exact_suffix"], "G3P exact suffix") is not True
            ):
                _fail("polarity_context", f"G3P exact suffix differs: {piece}")
            _hex64(continuation["full_token_ids_sha256"], "G3P continuation hash")
            continuation_count += 1
    if tuple(observed) != prompt_ids or continuation_count != 48:
        _fail("polarity_context", "G3P 24/48 audit coverage differs")


def _phase_expected_files(phase: str) -> set[str]:
    expected = {
        *PHASE_ROW_FILENAMES[phase],
        "RUN_STARTED.json",
        "RUN_COMPLETE.json",
        "TOKENIZER_AUDIT.json",
        "PHASE_BINDING.json",
        "RUNTIME_METADATA.json",
    }
    if phase == "G4":
        expected.update(
            {
                "G4_VECTOR_INVENTORY.json",
                "G4_MATCHING_TABLE.jsonl",
                "G4_HOOK_TENSORS.pt",
                "G4_HOOK_TENSOR_INDEX.jsonl",
            }
        )
    return expected


def _validate_file_manifest(
    directory: Path,
    *,
    phase: str,
    run_id: str,
    plan_manifest_sha256: str,
    execution_binding_sha256: str,
) -> dict[str, Any]:
    manifest_path = directory / "FILE_MANIFEST.json"
    manifest = _load_json(manifest_path, f"{phase} FILE_MANIFEST")
    _require_fields(manifest, FILE_MANIFEST_FIELDS, f"{phase} FILE_MANIFEST")
    if (
        manifest.get("schema_version") != 1
        or manifest.get("study_id") != protocol.STUDY_ID
        or manifest.get("phase") != phase
        or manifest.get("run_id") != run_id
        or manifest.get("plan_manifest_sha256") != plan_manifest_sha256
        or manifest.get("execution_binding_canonical_sha256") != execution_binding_sha256
    ):
        _fail("phase_manifest", f"{phase} FILE_MANIFEST identity differs")
    _embedded_hash(manifest, "manifest_sha256", f"{phase} FILE_MANIFEST")
    counts = manifest["row_counts"]
    if not isinstance(counts, Mapping) or set(counts) != set(PHASE_ROW_FILENAMES[phase]):
        _fail("phase_manifest", f"{phase} row-count inventory differs")
    files = manifest["files"]
    if not isinstance(files, list):
        _fail("phase_manifest", f"{phase} file inventory is malformed")
    names: list[str] = []
    for offset, record in enumerate(files):
        _require_fields(record, FILE_RECORD_FIELDS, f"{phase} file record {offset}")
        name = record["path"]
        if not isinstance(name, str) or Path(name).name != name or name in names:
            _fail("phase_manifest", f"{phase} file names are malformed or duplicated")
        if _integer(record["bytes"], f"{phase}/{name} byte count") < 0:
            _fail("phase_manifest", f"{phase}/{name} byte count is negative")
        _hex64(record["sha256"], f"{phase}/{name} content hash")
        names.append(name)
    expected = _phase_expected_files(phase)
    if set(names) != expected or names != sorted(names):
        _fail(
            "phase_manifest",
            f"{phase} exact/sorted file inventory differs; expected={sorted(expected)}, "
            f"observed={names}",
        )
    return manifest


def _verify_completed_transaction(
    directory: Path,
    *,
    phase: str,
    run_id: str,
    plan_hash: str,
    execution_hash: str,
) -> dict[str, Any]:
    """Independently verify exact transaction bytes and load enveloped rows."""

    if directory.is_symlink() or not directory.is_dir() or directory.name != run_id:
        _fail("transaction_path", f"{phase} completed-run path is unsafe")
    manifest = _validate_file_manifest(
        directory,
        phase=phase,
        run_id=run_id,
        plan_manifest_sha256=plan_hash,
        execution_binding_sha256=execution_hash,
    )
    listed = {record["path"]: record for record in manifest["files"]}
    actual = {entry.name for entry in directory.iterdir()}
    if actual != {*listed, "FILE_MANIFEST.json"}:
        _fail("transaction_files", f"{phase} contains an unlisted/missing file")
    for name, record in listed.items():
        candidate = directory / name
        if candidate.is_symlink() or not candidate.is_file():
            _fail("transaction_files", f"{phase}/{name} is unsafe")
        if candidate.stat().st_size != record["bytes"] or _sha256_file(candidate) != record["sha256"]:
            _fail("transaction_files", f"{phase}/{name} bytes differ from FILE_MANIFEST")
    started = _load_json(directory / "RUN_STARTED.json", f"{phase} RUN_STARTED")
    completed = _load_json(directory / "RUN_COMPLETE.json", f"{phase} RUN_COMPLETE")
    for value, label in ((started, "RUN_STARTED"), (completed, "RUN_COMPLETE")):
        if value.get("study_id") != protocol.STUDY_ID or value.get("phase") != phase or value.get("run_id") != run_id:
            _fail("transaction_state", f"{phase} {label} identity differs")
        _assert_empty_inputs(value, label=f"{phase} {label}")
    if started.get("plan_manifest_sha256") != plan_hash or started.get("execution_binding_canonical_sha256") != execution_hash:
        _fail("transaction_state", f"{phase} RUN_STARTED lineage differs")
    counts = manifest["row_counts"]
    if completed.get("row_counts") != counts or completed.get("analysis_decisions") != []:
        _fail("transaction_state", f"{phase} completion count/analysis-decision contract differs")
    rows_by_file: dict[str, list[dict[str, Any]]] = {}
    measurement_files: dict[str, dict[str, Any]] = {}
    for filename in PHASE_ROW_FILENAMES[phase]:
        rows: list[dict[str, Any]] = []
        path = directory / filename
        try:
            with path.open("r", encoding="utf-8") as handle:
                for line_number, line in enumerate(handle, start=1):
                    row = json.loads(line)
                    if not isinstance(row, dict):
                        _fail("measurement_jsonl", f"{filename}:{line_number} is not an object")
                    rows.append(row)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise StructuralAuditError("measurement_jsonl", f"cannot read {filename}") from exc
        if isinstance(counts[filename], bool) or not isinstance(counts[filename], int) or counts[filename] != len(rows):
            _fail("measurement_count", f"{filename} row count differs")
        rows_by_file[filename] = rows
        measurement_files[filename] = {
            "row_count": len(rows),
            "content_sha256": _sha256_file(path),
            "logical_rows_sha256": protocol.canonical_sha256(rows),
        }
    receipt = {
        "file_manifest_content_sha256": _sha256_file(directory / "FILE_MANIFEST.json"),
        "file_manifest_embedded_sha256": manifest["manifest_sha256"],
        "measurement_files": measurement_files,
    }
    return {"manifest": manifest, "receipt": receipt, "rows": rows_by_file}


def _validate_phase_binding(
    value: Mapping[str, Any],
    *,
    phase: str,
    run_id: str,
    plan_hash: str,
    execution_hash: str,
    tokenizer_receipt_hash: str,
    tokenizer_inventory_hash: str,
) -> None:
    _require_fields(value, PHASE_BINDING_FIELDS, f"{phase} phase binding")
    expected = {
        "schema_version": 1,
        "status": "pass",
        "binding_kind": "gpu_phase_binding_v1",
        "study_id": protocol.STUDY_ID,
        "protocol_version": protocol.PROTOCOL_VERSION,
        "phase": phase,
        "run_id": run_id,
        "plan_manifest_sha256": plan_hash,
        "execution_binding_canonical_sha256": execution_hash,
        "tokenizer_audit_receipt_sha256": tokenizer_receipt_hash,
        "tokenizer_inventory_sha256": tokenizer_inventory_hash,
        "runtime_adapter": "gpu_phase_adapter_v1",
        "prior_outcome_inputs": [],
        "target_prompt_inputs": [],
        "target_outcome_inputs": [],
    }
    if any(value.get(key) != expected_value for key, expected_value in expected.items()):
        _fail("phase_binding", f"{phase} phase-binding identity differs")
    _embedded_hash(value, "receipt_sha256", f"{phase} phase binding")


def _validate_artifact_summary(value: Any, frozen: Mapping[str, Any], label: str) -> None:
    if value != frozen:
        _fail("runtime_metadata", f"{label} runtime artifact summary differs")


def _parse_utc(value: Any, label: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        _fail("runtime_metadata", f"{label} is not a UTC timestamp")
    try:
        return datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise StructuralAuditError("runtime_metadata", f"{label} is invalid") from exc


def _validate_runtime_metadata(
    value: Mapping[str, Any],
    *,
    phase: str,
    run_id: str,
    plan_hash: str,
    execution_hash: str,
    tokenizer_receipt_hash: str,
) -> None:
    _require_fields(value, RUNTIME_METADATA_FIELDS, f"{phase} runtime metadata")
    expected = {
        "schema_version": 1,
        "status": "pass",
        "metadata_kind": "gpu_phase_runtime_v1",
        "study_id": protocol.STUDY_ID,
        "protocol_version": protocol.PROTOCOL_VERSION,
        "phase": phase,
        "run_id": run_id,
        "plan_manifest_sha256": plan_hash,
        "execution_binding_canonical_sha256": execution_hash,
        "tokenizer_audit_receipt_sha256": tokenizer_receipt_hash,
        "runtime_adapter": "gpu_phase_adapter_v1",
        "container_image": protocol.CONTAINER_IMAGE_SPEC,
        "model_weights_loaded": True,
        "prior_outcome_inputs": [],
        "target_prompt_inputs": [],
        "target_outcome_inputs": [],
    }
    if any(value.get(key) != expected_value for key, expected_value in expected.items()):
        _fail("runtime_metadata", f"{phase} runtime lineage/model-loaded status differs")
    if protocol.canonical_sha256(value.get("hook_contract")) != protocol.canonical_sha256(
        AUDITED_HOOK_CONTRACT
    ):
        _fail("runtime_metadata", f"{phase} runtime hook contract differs")
    forward_count = _integer(value["model_forward_count"], f"{phase} model forward count")
    if phase == "G1":
        if forward_count != 0 or value["first_model_forward_at_utc"] is not None or value["last_model_forward_at_utc"] is not None:
            _fail("runtime_metadata", "G1 must record zero model forwards and null timestamps")
    else:
        if forward_count <= 0:
            _fail("runtime_metadata", f"{phase} must record at least one model forward")
        first = _parse_utc(value["first_model_forward_at_utc"], f"{phase} first forward")
        last = _parse_utc(value["last_model_forward_at_utc"], f"{phase} last forward")
        if last < first:
            _fail("runtime_metadata", f"{phase} model-forward timestamps are reversed")
    _validate_artifact_summary(value["model"], protocol.MODEL_SPEC, "model")
    _validate_artifact_summary(value["sae"], protocol.SAE_SPEC, "SAE")
    _validate_artifact_summary(value["j_lens"], protocol.J_LENS_SPEC, "J-lens")
    hardware = _require_fields(
        value["hardware"],
        frozenset(
            {
                "cuda_device_count",
                "gpu_name",
                "gpu_total_memory_bytes",
                "cuda_runtime_version",
                "cudnn_version",
            }
        ),
        f"{phase} hardware inventory",
    )
    if (
        hardware["cuda_device_count"] != 1
        or _integer(hardware["gpu_total_memory_bytes"], f"{phase} GPU memory") < 160 * 1024**3
        or not isinstance(hardware["gpu_name"], str)
        or not hardware["gpu_name"]
        or not isinstance(hardware["cuda_runtime_version"], str)
        or not hardware["cuda_runtime_version"]
        or _integer(hardware["cudnn_version"], f"{phase} cuDNN version") <= 0
    ):
        _fail("runtime_metadata", f"{phase} hardware contract differs")
    software = _require_fields(
        value["software"],
        frozenset(
            {
                "python",
                "python_implementation",
                "torch",
                "accelerate",
                "huggingface_hub",
                "numpy",
                "safetensors",
                "transformers",
            }
        ),
        f"{phase} software inventory",
    )
    expected_packages = {
        "accelerate": "1.12.0",
        "huggingface_hub": "0.36.0",
        "numpy": "2.2.6",
        "safetensors": "0.6.2",
        "transformers": "4.57.6",
    }
    if (
        software["python_implementation"] != "CPython"
        or not isinstance(software["python"], str)
        or not software["python"].startswith("3.11.")
        or not isinstance(software["torch"], str)
        or not software["torch"]
        or any(software[key] != version for key, version in expected_packages.items())
    ):
        _fail("runtime_metadata", f"{phase} pinned software inventory differs")
    expected_determinism = {
        "seed": int(protocol.PILOT_RANDOM_SEED % (2**63 - 1)),
        "cublas_workspace_config": ":4096:8",
        "deterministic_algorithms": True,
        "cuda_matmul_tf32": False,
        "cudnn_tf32": False,
        "flash_sdp_enabled": False,
        "mem_efficient_sdp_enabled": False,
        "math_sdp_enabled": True,
    }
    if value["determinism"] != expected_determinism:
        _fail("runtime_metadata", f"{phase} deterministic-kernel contract differs")
    _embedded_hash(value, "receipt_sha256", f"{phase} runtime metadata")


def _measurement_contract(
    filename: str,
) -> tuple[list[tuple[Any, ...]], Callable[[Mapping[str, Any]], tuple[Any, ...]], Callable[[Mapping[str, Any]], list[Any]]]:
    prompts = tuple(row["prompt_id"] for row in protocol.neutral_prompts())
    if filename == "g1_rows.jsonl":
        expected = [
            (layer, fixture["fixture_id"])
            for layer in protocol.G1_MAP_LAYERS
            for fixture in protocol.G1_SYNTHETIC_FIXTURES
        ]
        return expected, lambda row: (row["layer"], row["synthetic_residual_id"]), lambda row: [row["layer"], row["synthetic_residual_id"]]
    if filename == "g2_transport_rows.jsonl":
        expected = [
            (prompt, layer, direction, transport)
            for prompt in prompts[: protocol.G2_PROMPT_COUNT]
            for layer in protocol.J_MAP_LAYERS
            for direction in protocol.G2_DIRECTIONS
            for transport in protocol.G2_TRANSPORT_OPERATORS
        ]
        return expected, lambda row: (row["prompt_id"], row["layer"], row["direction"], row["transport"]), lambda row: [row["prompt_id"], row["layer"], row["direction"], row["transport"]]
    if filename == "g2_linearity_rows.jsonl":
        expected = [
            (prompt, layer, 0)
            for prompt in prompts[:8]
            for layer in protocol.G2_LINEARITY_LAYERS
        ]
        return expected, lambda row: (row["prompt_id"], row["layer"], row["direction"]), lambda row: [row["prompt_id"], row["layer"], row["direction"]]
    if filename == "g3_rows.jsonl":
        prompt_ids = tuple(row["fixture_id"] for row in protocol.g3_fixture_rows())
        transports = ("real_j", "identity", *(f"random_j_{index}" for index in range(protocol.G3_RANDOM_CONTROL_COUNT)))
        expected = []
        for prompt in prompt_ids:
            expected.append((prompt, "actual_final", "final"))
            expected.extend(
                (prompt, transport, layer)
                for layer in protocol.J_MAP_LAYERS
                for transport in transports
            )
        return expected, lambda row: (row["prompt_id"], row["transport"], row["layer"]), lambda row: [row["prompt_id"], row["transport"], row["layer"]]
    if filename == "g3p_rows.jsonl":
        prompt_ids = tuple(row["prompt_id"] for row in protocol.g3p_plan_rows())
        transports = ("real_j", *(f"random_j_{index}" for index in range(protocol.G3_RANDOM_CONTROL_COUNT)))
        expected = []
        for prompt in prompt_ids:
            expected.append((prompt, "actual_final", "final"))
            expected.extend(
                (prompt, transport, layer)
                for layer in protocol.J_MAP_LAYERS
                for transport in transports
            )
        return expected, lambda row: (row["prompt_id"], row["transport"], row["layer"]), lambda row: [row["prompt_id"], row["transport"], row["layer"]]
    subsets = tuple(tuple(row["target_feature_ids"]) for row in protocol.g4_aggregate_assignments())
    if filename == "g4_clean_rows.jsonl":
        expected = [(prompt,) for prompt in prompts]
        return expected, lambda row: (row["prompt_id"],), lambda row: [row["prompt_id"]]
    if filename == "g4_vector_rows.jsonl":
        expected = [
            (subset, vector_class, sign)
            for subset in subsets
            for vector_class in protocol.G4_VECTOR_CLASSES
            for sign in protocol.G4_SIGNS
        ]
        return expected, lambda row: (tuple(row["subset_feature_ids"]), row["control_type"], row["sign"]), lambda row: [list(row["subset_feature_ids"]), row["control_type"], row["sign"]]
    if filename == "g4_telemetry_rows.jsonl":
        expected = [
            (prompt, subset, vector_class, sign)
            for prompt in protocol.G4_SENTINEL_PROMPT_IDS
            for subset in subsets
            for vector_class in protocol.G4_VECTOR_CLASSES
            for sign in protocol.G4_SIGNS
        ]
        return expected, lambda row: (row["prompt_id"], tuple(row["subset_feature_ids"]), row["control_type"], row["sign"]), lambda row: [row["prompt_id"], list(row["subset_feature_ids"]), row["control_type"], row["sign"]]
    raise AssertionError(filename)


def _validate_measurement_values(
    filename: str,
    row: Mapping[str, Any],
    *,
    token_ids: tuple[int, ...],
    semantic_endpoint_ids: Mapping[str, int],
) -> None:
    """Validate representation only; never compare an outcome to a gate threshold."""

    if filename == "g1_rows.jsonl":
        if row["vocab_ids"] != list(token_ids):
            _fail("measurement_binding", "G1 row uses another tokenizer panel")
        for field in ("map_shape_valid", "map_finite", "production_finite", "reference_finite", "wrong_orientation_differs"):
            _boolean(row[field], f"G1 {field}")
        _number(row["relative_rmse"], "G1 relative RMSE")
        _number(row["selected_logit_sign_agreement"], "G1 sign agreement")
    elif filename == "g2_transport_rows.jsonl":
        _boolean(row["signed_pair_complete"], "G2 signed-pair flag")
        _boolean(row["finite"], "G2 finite flag")
        _number(row["residual_delta_cosine"], "G2 residual cosine")
        _number(row["fixed_token_logit_delta_pearson"], "G2 logit Pearson")
    elif filename == "g2_linearity_rows.jsonl":
        _boolean(row["finite"], "G2 linearity finite flag")
        _number(row["central_difference_cosine"], "G2 central-difference cosine")
        _number(row["slope_discrepancy"], "G2 slope discrepancy")
    elif filename == "g3_rows.jsonl":
        fixtures = {item["fixture_id"]: item for item in protocol.g3_fixture_rows()}
        fixture = fixtures.get(row["prompt_id"])
        if fixture is None or (row["true_family"], row["item_index"], row["render_mode"]) != (
            fixture["family"], fixture["cloze_index"], fixture["render_mode"]
        ):
            _fail("measurement_grid", "G3 fixture metadata differs")
        logits = row["token_logits"]
        if not isinstance(logits, Mapping) or set(logits) != set(semantic_endpoint_ids):
            _fail("measurement_schema", "G3 semantic token-logit inventory differs")
        for token, value in logits.items():
            _number(value, f"G3 token logit {token}")
        _boolean(row["finite"], "G3 finite flag")
    elif filename == "g3p_rows.jsonl":
        answers = {item["prompt_id"]: item["expected_label"] for item in protocol.g3p_plan_rows()}
        if row["expected_answer"] != answers.get(row["prompt_id"]):
            _fail("measurement_grid", "G3P expected-answer metadata differs")
        _number(row["yes_logit"], "G3P Yes logit")
        _number(row["no_logit"], "G3P No logit")
        _boolean(row["finite"], "G3P finite flag")
    elif filename == "g4_clean_rows.jsonl":
        _number(row["h50_pre_rms"], "G4 clean RMS")
        _boolean(row["finite"], "G4 clean finite flag")
    elif filename == "g4_vector_rows.jsonl":
        _number(row["coefficient"], "G4 coefficient")
        _number(row["vector_rms"], "G4 vector RMS")
        _hex64(row["vector_sha256"], "G4 vector hash")
        if row["dtype"] != "bfloat16":
            _fail("measurement_schema", "G4 vector dtype differs")
        _boolean(row["finite"], "G4 vector finite flag")
        if _boolean(row["precomputed_before_any_edited_forward"], "G4 pre-edit flag") is not True:
            _fail("pre_edit_seal", "G4 vector was not precomputed before edited forwards")
        if _integer(row["edited_forward_count_at_compute"], "G4 edited-forward count") != 0:
            _fail("pre_edit_seal", "G4 vector was computed after an edited forward")
    else:
        for field in (
            "vector_sha256", "input_token_ids_sha256", "clean_input_token_ids_sha256",
            "clean_pre_edit_sha256", "edited_pre_edit_sha256", "expected_post_edit_sha256",
            "observed_post_edit_sha256", "clean_output_sha256", "sham_output_sha256",
        ):
            _hex64(row[field], f"G4 telemetry {field}")
        if row["expected_post_edit_sha256"] != row["observed_post_edit_sha256"]:
            _fail("g4_hook_equality", "G4 expected/observed post-edit hashes differ")
        for field in ("coefficient", "realized_delta_relative_rmse", "sign_cosine"):
            _number(row[field], f"G4 telemetry {field}")
        for field in ("downstream_finite", "logits_finite", "attenuation_attempted"):
            _boolean(row[field], f"G4 telemetry {field}")
        _integer(row["hook_fire_count"], "G4 hook count")
        _integer(row["retry_count"], "G4 retry count")


def _validate_measurement_rows(
    rows: Sequence[Mapping[str, Any]],
    *,
    filename: str,
    phase: str,
    run_id: str,
    plan_hash: str,
    token_ids: tuple[int, ...],
    semantic_endpoint_ids: Mapping[str, int],
    global_task_ids: set[str],
    global_row_ids: set[str],
) -> None:
    expected, identity_of, task_key_of = _measurement_contract(filename)
    observed: set[tuple[Any, ...]] = set()
    observed_order: list[tuple[Any, ...]] = []
    expected_fields = MEASUREMENT_FIELDS[filename] | LINEAGE_FIELDS
    for offset, row in enumerate(rows):
        _require_fields(row, expected_fields, f"{filename} row {offset}")
        if (
            row.get("study_id") != protocol.STUDY_ID
            or row.get("protocol_version") != protocol.PROTOCOL_VERSION
            or row.get("plan_manifest_sha256") != plan_hash
            or row.get("run_id") != run_id
        ):
            _fail("measurement_lineage", f"{filename}:{offset} crosses lineage")
        identity = identity_of(row)
        if identity in observed:
            _fail("measurement_grid", f"{filename} duplicates {identity!r}")
        observed.add(identity)
        observed_order.append(identity)
        expected_task = protocol.stable_id(
            "measurement",
            {"measurement_kind": MEASUREMENT_KINDS[filename], "key": task_key_of(row)},
        )
        original_row = {
            field: row[field] for field in MEASUREMENT_FIELDS[filename]
        }
        original_row["task_id"] = expected_task
        expected_row = protocol.canonical_sha256(
            {
                "study_id": protocol.STUDY_ID,
                "protocol_version": protocol.PROTOCOL_VERSION,
                "parts": (
                    phase,
                    run_id,
                    filename,
                    offset,
                    protocol.canonical_sha256(original_row),
                ),
            }
        )[:32]
        task_id = row["task_id"]
        row_id = row["row_id"]
        if task_id != expected_task or task_id in global_task_ids:
            _fail("task_id", f"{filename}:{offset} task ID does not reconstruct or is duplicated")
        if row_id != expected_row or row_id in global_row_ids:
            _fail("row_id", f"{filename}:{offset} row ID does not reconstruct or is duplicated")
        global_task_ids.add(task_id)
        global_row_ids.add(row_id)
        _validate_measurement_values(
            filename,
            row,
            token_ids=token_ids,
            semantic_endpoint_ids=semantic_endpoint_ids,
        )
    expected_set = set(expected)
    if observed_order != expected:
        _fail(
            "measurement_grid",
            f"{filename} ordered grid differs: missing={len(expected_set - observed)}, "
            f"unexpected={len(observed - expected_set)}",
        )


def validate_vector_inventory_receipt(
    receipt: Mapping[str, Any], *, plan_manifest_sha256: str
) -> dict[str, Any]:
    """Reconstruct the complete declared G4 mapping and signed-vector inventory."""

    _require_fields(receipt, VECTOR_INVENTORY_FIELDS, "G4 vector inventory")
    if (
        receipt.get("schema_version") != 1
        or receipt.get("study_id") != protocol.STUDY_ID
        or receipt.get("protocol_version") != protocol.PROTOCOL_VERSION
        or receipt.get("status") != "pass"
        or receipt.get("plan_manifest_sha256") != plan_manifest_sha256
        or receipt.get("sae_sha256") != protocol.SAE_SPEC["sha256"]
        or receipt.get("matching_spec_sha256")
        != protocol.canonical_sha256(protocol.G4_MATCHING_SPEC)
        or receipt.get("vector_arithmetic_spec_sha256")
        != protocol.canonical_sha256(protocol.G4_VECTOR_ARITHMETIC_SPEC)
    ):
        _fail("g4_inventory", "G4 vector-inventory identity/specification differs")
    _hex64(receipt["decoder_bfloat16_sha256"], "G4 decoder BF16 hash")
    _hex64(receipt["matching_candidate_inventory_sha256"], "G4 matching-table hash")
    target_ids = tuple(receipt["target_feature_ids"]) if isinstance(receipt["target_feature_ids"], list) else ()
    excluded_ids = tuple(receipt["excluded_feature_ids"]) if isinstance(receipt["excluded_feature_ids"], list) else ()
    if target_ids != protocol.G4_TARGET_FEATURE_IDS or excluded_ids != target_ids:
        _fail("g4_matching", "G4 target/exclusion inventory differs")
    mapping_rows = receipt["target_to_matched"]
    if not isinstance(mapping_rows, list) or len(mapping_rows) != len(target_ids):
        _fail("g4_matching", "G4 target-to-matched inventory differs")
    mapping: dict[int, int] = {}
    matched: list[int] = []
    for offset, (expected_target, row) in enumerate(zip(target_ids, mapping_rows)):
        _require_fields(row, MATCH_ROW_FIELDS, f"G4 match row {offset}")
        target = _integer(row["target_feature_id"], "G4 match target")
        matched_id = _integer(row["matched_feature_id"], "G4 matched feature")
        if target != expected_target or not 0 <= matched_id < protocol.SAE_SPEC["feature_count"]:
            _fail("g4_matching", "G4 target-to-matched order/range differs")
        if _number(row["scaled_distance"], "G4 match distance") < 0:
            _fail("g4_matching", "G4 match distance is negative")
        mapping[target] = matched_id
        matched.append(matched_id)
    if len(set(matched)) != len(matched) or set(matched) & set(target_ids):
        _fail("g4_matching", "G4 matched features are not unique and target-excluded")

    expected_order = [
        (
            str(assignment["assignment_id"]),
            tuple(assignment["target_feature_ids"]),
            vector_class,
            sign,
        )
        for assignment in protocol.g4_aggregate_assignments()
        for vector_class in protocol.G4_VECTOR_CLASSES
        for sign in protocol.G4_SIGNS
    ]
    vectors = receipt["vectors"]
    if not isinstance(vectors, list) or len(vectors) != 300:
        _fail("g4_vectors", "G4 inventory must contain exactly 300 vectors")
    pairs: dict[tuple[str, str], dict[int, Mapping[str, Any]]] = defaultdict(dict)
    indexed: dict[tuple[tuple[int, ...], str, int], Mapping[str, Any]] = {}
    for offset, (expected, row) in enumerate(zip(expected_order, vectors)):
        _require_fields(row, VECTOR_ROW_FIELDS, f"G4 vector inventory row {offset}")
        assignment_id, subset, vector_class, sign = expected
        if (
            row["assignment_id"] != assignment_id
            or tuple(row["subset_feature_ids"]) != subset
            or row["control_type"] != vector_class
            or _integer(row["sign"], "G4 vector sign") != sign
            or _number(row["coefficient"], "G4 coefficient") != 0.5 * sign
        ):
            _fail("g4_vectors", "G4 vector order/identity differs")
        if vector_class == "target":
            resolved, seed = subset, None
        elif vector_class == "matched":
            resolved, seed = tuple(mapping[target] for target in subset), None
        else:
            resolved = ()
            seed = protocol.identity_bound_seed64("g4-isotropic-v1", assignment_id)
        if tuple(row["resolved_feature_ids"]) != resolved or row["isotropic_seed"] != seed:
            _fail("g4_vectors", "G4 resolved features/isotropic seed differ")
        raw_norm = _number(row["raw_norm"], "G4 raw norm")
        rescale = _number(row["norm_rescale"], "G4 norm rescale")
        final_norm = _number(row["final_norm"], "G4 final norm")
        reference = _number(row["target_reference_final_norm"], "G4 reference norm")
        vector_rms = _number(row["vector_rms"], "G4 vector RMS")
        if min(raw_norm, rescale, final_norm, reference, vector_rms) <= 0:
            _fail("g4_norm", "G4 vector norms/rescale must be positive")
        norm_error = _number(row["norm_relative_error"], "G4 norm error")
        reconstructed_error = abs(final_norm - reference) / reference
        if norm_error < 0 or not math.isclose(norm_error, reconstructed_error, rel_tol=1e-9, abs_tol=1e-12):
            _fail("g4_norm", "G4 norm error does not reconstruct")
        if not math.isclose(
            vector_rms,
            final_norm / math.sqrt(protocol.MODEL_SPEC["residual_width"]),
            rel_tol=1e-9,
            abs_tol=1e-12,
        ):
            _fail("g4_norm", "G4 RMS does not reconstruct from vector norm")
        if vector_class == "target":
            if norm_error != 0 or rescale != 1 or final_norm != reference:
                _fail("g4_norm", "G4 target norm metadata differs")
        elif norm_error > protocol.G4_CONTROL_NORM_RELATIVE_ERROR_MAX:
            _fail("g4_norm", "G4 control norm-match error exceeds the frozen ceiling")
        raw_hash = _hex64(row["raw_vector_sha256"], "G4 raw-vector hash")
        vector_hash = _hex64(row["vector_sha256"], "G4 signed-vector hash")
        positive_hash = _hex64(row["positive_vector_sha256"], "G4 positive-vector hash")
        negative_hash = _hex64(row["negative_vector_sha256"], "G4 negative-vector hash")
        if vector_hash != (positive_hash if sign == 1 else negative_hash):
            _fail("g4_signed_pair", "G4 sign-specific vector hash differs")
        if positive_hash == negative_hash or raw_hash == "0" * 64:
            _fail("g4_signed_pair", "G4 signed/raw vector hashes are degenerate")
        if row["dtype"] != "bfloat16":
            _fail("g4_vectors", "G4 vector dtype differs")
        for field in ("finite", "precomputed_before_any_edited_forward", "signed_pair_exact_negation"):
            if _boolean(row[field], f"G4 {field}") is not True:
                _fail("pre_edit_seal", f"G4 {field} is not true")
        if _integer(row["edited_forward_count_at_compute"], "G4 edited-forward count") != 0:
            _fail("pre_edit_seal", "G4 vector was materialized after an edited forward")
        relation = {
            "assignment_id": assignment_id,
            "control_type": vector_class,
            "dtype": "bfloat16",
            "positive_vector_sha256": positive_hash,
            "negative_vector_sha256": negative_hash,
            "relation": "negative_is_exact_elementwise_bfloat16_negation_of_positive",
        }
        relation_hash = _hex64(row["signed_pair_relation_sha256"], "G4 signed-pair relation")
        if relation_hash != protocol.canonical_sha256(relation):
            _fail("g4_signed_pair", "G4 signed-pair relation does not reconstruct")
        pairs[(assignment_id, vector_class)][sign] = row
        indexed[(subset, vector_class, sign)] = row
    for pair_identity, signed in pairs.items():
        if set(signed) != {-1, 1}:
            _fail("g4_signed_pair", f"G4 signed pair is incomplete: {pair_identity}")
        invariant = (
            "raw_norm", "norm_rescale", "final_norm", "norm_relative_error",
            "target_reference_final_norm", "vector_rms", "positive_vector_sha256",
            "negative_vector_sha256", "signed_pair_relation_sha256",
        )
        if any(signed[-1][field] != signed[1][field] for field in invariant):
            _fail("g4_signed_pair", f"G4 signed-pair metadata differs: {pair_identity}")
    receipt_hash = _embedded_hash(receipt, "receipt_sha256", "G4 vector inventory")
    return {
        "receipt_sha256": receipt_hash,
        "decoder_bfloat16_sha256": receipt["decoder_bfloat16_sha256"],
        "matching_candidate_inventory_sha256": receipt["matching_candidate_inventory_sha256"],
        "mapping": mapping,
        "vectors": indexed,
    }


def validate_g4_matching_table(
    path: Path,
    *,
    inventory_receipt: Mapping[str, Any],
) -> list[dict[str, Any]]:
    """Recompute exact transform, median/MAD scaling, ties, and greedy matches."""

    rows: list[dict[str, Any]] = []
    try:
        with path.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                value = json.loads(line)
                if not isinstance(value, dict):
                    _fail("g4_matching_table", f"matching row {line_number} is not an object")
                rows.append(value)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise StructuralAuditError("g4_matching_table", "cannot read matching table") from exc
    feature_count = protocol.SAE_SPEC["feature_count"]
    if len(rows) != feature_count:
        _fail("g4_matching_table", "matching table does not contain 65,536 rows")
    targets = set(protocol.G4_TARGET_FEATURE_IDS)
    for feature_id, row in enumerate(rows):
        _require_fields(row, MATCHING_TABLE_FIELDS, f"G4 matching row {feature_id}")
        if _integer(row["feature_id"], "G4 matching feature ID") != feature_id:
            _fail("g4_matching_table", "matching table feature order differs")
        norm = _number(row["decoder_l2_norm"], "G4 decoder norm")
        mean = _number(row["mean_positive_activation"], "G4 mean-positive activation")
        maximum = _number(row["max_positive_activation"], "G4 max-positive activation")
        fraction = _number(row["positive_activation_fraction"], "G4 positive fraction")
        if norm < 0 or mean < 0 or maximum < 0 or not 0 <= fraction <= 1:
            _fail("g4_matching_table", "matching table contains invalid production statistics")
        reasons: list[str] = []
        if feature_id in targets:
            reasons.append("target_feature_id")
        if norm == 0.0:
            reasons.append("decoder_norm_nonfinite_or_nonpositive")
        if row["exclusion_reasons"] != reasons:
            _fail("g4_matching_table", "matching-table exclusion reasons differ")
        if _boolean(row["eligible_candidate"], "G4 candidate eligibility") != (not reasons):
            _fail("g4_matching_table", "matching-table eligibility differs")
        transformed = [math.log1p(norm), math.log1p(mean), math.log1p(maximum), fraction]
        if row["transformed_coordinates"] != transformed:
            _fail("g4_matching_table", "matching transformed coordinates do not reconstruct")

    eligible = [row for row in rows if row["eligible_candidate"]]
    medians: list[float] = []
    divisors: list[float] = []
    for coordinate in range(4):
        values = [float(row["transformed_coordinates"][coordinate]) for row in eligible]
        median = float(statistics.median(values))
        mad = float(statistics.median(abs(value - median) for value in values))
        medians.append(median)
        divisors.append(mad if mad != 0 else 1.0)
    for row in rows:
        expected_scaled = [
            (float(value) - medians[index]) / divisors[index]
            for index, value in enumerate(row["transformed_coordinates"])
        ]
        if row["scaled_coordinates"] != expected_scaled:
            _fail("g4_matching_table", "matching scaled coordinates do not reconstruct")
    table_hash = protocol.canonical_sha256(rows)
    if inventory_receipt.get("matching_candidate_inventory_sha256") != table_hash:
        _fail("g4_matching_table", "matching-table canonical hash differs from vector inventory")

    observed_mapping = inventory_receipt.get("target_to_matched")
    if not isinstance(observed_mapping, list):
        _fail("g4_matching_table", "target-to-matched mapping is malformed")
    selected: list[int] = []
    reconstructed: list[dict[str, Any]] = []
    for target_id in protocol.G4_TARGET_FEATURE_IDS:
        target = rows[target_id]
        ranking: list[tuple[float, int]] = []
        for candidate in eligible:
            candidate_id = int(candidate["feature_id"])
            if candidate_id in selected:
                continue
            distance = float(
                sum(
                    (float(left) - float(right)) ** 2
                    for left, right in zip(
                        target["scaled_coordinates"], candidate["scaled_coordinates"]
                    )
                )
            )
            if not math.isfinite(distance) or distance < 0:
                _fail("g4_matching_table", "reconstructed matching distance is invalid")
            ranking.append((distance, candidate_id))
        ranking.sort(key=lambda item: (item[0], item[1]))
        if not ranking:
            _fail("g4_matching_table", "reconstructed greedy candidate set is empty")
        distance, matched_id = ranking[0]
        selected.append(matched_id)
        reconstructed.append(
            {
                "target_feature_id": target_id,
                "matched_feature_id": matched_id,
                "scaled_distance": distance,
            }
        )
    if reconstructed != observed_mapping:
        _fail("g4_matching_table", "greedy one-to-one mapping/tie break does not reconstruct")
    if inventory_receipt.get("excluded_feature_ids") != list(protocol.G4_TARGET_FEATURE_IDS):
        _fail("g4_matching_table", "persisted exclusion inventory differs from full table")
    return rows


def _tensor_sha256_independent(tensor: Any) -> str:
    """Hash tensor dtype/shape/exact bytes without the runtime producer."""

    torch = __import__("torch")
    if not isinstance(tensor, torch.Tensor):
        _fail("g4_vector_reconstruction", "tensor hash input is not a tensor")
    cpu = tensor.detach().contiguous().to(device="cpu")
    digest = hashlib.sha256()
    digest.update(
        json.dumps(
            {"dtype": str(cpu.dtype), "shape": list(cpu.shape)},
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    )
    digest.update(b"\0")
    raw = cpu.view(torch.uint8).reshape(-1)
    for start in range(0, int(raw.numel()), 8 * 1024 * 1024):
        digest.update(raw[start : start + 8 * 1024 * 1024].numpy().tobytes())
    return digest.hexdigest()


def _aggregate_decoder_independent(decoder: Any, feature_ids: Sequence[int]) -> Any:
    torch = __import__("torch")
    accumulator = torch.zeros(
        protocol.MODEL_SPEC["residual_width"], dtype=torch.float32, device="cpu"
    )
    for feature_id in feature_ids:
        accumulator.add_(
            decoder[:, int(feature_id)].to(dtype=torch.bfloat16).to(dtype=torch.float32)
        )
    return accumulator.mul_(0.5).to(dtype=torch.bfloat16).contiguous()


def _resolve_sae_state_independent(state: Any) -> dict[str, Any]:
    """Require the exact public four-tensor SAE layout and frozen tensor shapes."""

    if not isinstance(state, Mapping):
        _fail("g4_vector_reconstruction", "SAE checkpoint is not a tensor mapping")
    suffixes = (
        "encoder_linear.weight",
        "encoder_linear.bias",
        "decoder_linear.weight",
        "decoder_linear.bias",
    )
    resolved_keys: dict[str, Any] = {}
    for suffix in suffixes:
        matches = [
            key
            for key in state
            if isinstance(key, str) and (key == suffix or key.endswith("." + suffix))
        ]
        if len(matches) != 1:
            _fail(
                "g4_vector_reconstruction",
                f"SAE key ending in {suffix!r} is not unique",
            )
        resolved_keys[suffix] = matches[0]
    if set(state) != set(resolved_keys.values()):
        _fail(
            "g4_vector_reconstruction",
            "SAE checkpoint does not contain exactly the four frozen tensors",
        )
    tensors = {suffix: state[key] for suffix, key in resolved_keys.items()}
    expected_shapes = {
        "encoder_linear.weight": tuple(
            AUDITED_HOOK_CONTRACT["sae"]["encoder_weight_shape"]
        ),
        "encoder_linear.bias": tuple(
            AUDITED_HOOK_CONTRACT["sae"]["encoder_bias_shape"]
        ),
        "decoder_linear.weight": tuple(
            AUDITED_HOOK_CONTRACT["sae"]["decoder_weight_shape"]
        ),
        "decoder_linear.bias": tuple(
            AUDITED_HOOK_CONTRACT["sae"]["decoder_bias_shape"]
        ),
    }
    for suffix, expected in expected_shapes.items():
        if tuple(getattr(tensors[suffix], "shape", ())) != expected:
            _fail(
                "g4_vector_reconstruction",
                f"SAE {suffix} shape differs from the frozen hook contract",
            )
    return tensors


def _norm_match_independent(control: Any, target: Any) -> tuple[Any, float, float, float, float]:
    torch = __import__("torch")
    raw = control.to(dtype=torch.bfloat16).contiguous()
    reference = target.to(dtype=torch.bfloat16).contiguous()
    raw_norm = float(raw.float().norm().item())
    target_norm = float(reference.float().norm().item())
    if not math.isfinite(raw_norm) or not math.isfinite(target_norm) or min(raw_norm, target_norm) <= 0:
        _fail("g4_vector_reconstruction", "control/reference norm is invalid")
    scalar = torch.tensor(target_norm / raw_norm, dtype=torch.bfloat16, device="cpu")
    matched = (raw * scalar).to(dtype=torch.bfloat16).contiguous()
    final_norm = float(matched.float().norm().item())
    error = abs(final_norm - target_norm) / target_norm
    return matched, float(scalar.float().item()), raw_norm, final_norm, error


def validate_g4_vector_arithmetic(
    sae_path: Path,
    *,
    inventory_receipt: Mapping[str, Any],
    mapping: Mapping[int, int],
) -> dict[tuple[tuple[int, ...], str, int], Any]:
    """Rebuild every target/matched/isotropic BF16 vector from the pinned SAE."""

    try:
        import numpy as np
        import torch
    except ImportError as exc:  # pragma: no cover - production dependency
        raise StructuralAuditError(
            "g4_vector_reconstruction", "NumPy and PyTorch are required for G4 audit"
        ) from exc
    state = torch.load(sae_path, map_location="cpu", weights_only=True, mmap=True)
    decoder = _resolve_sae_state_independent(state)["decoder_linear.weight"]
    expected_shape = (
        protocol.MODEL_SPEC["residual_width"],
        protocol.SAE_SPEC["feature_count"],
    )
    if not isinstance(decoder, torch.Tensor) or tuple(decoder.shape) != expected_shape or decoder.device.type != "cpu":
        _fail("g4_vector_reconstruction", "SAE decoder shape/device differs")
    decoder_hash = _tensor_sha256_independent(
        decoder.to(dtype=torch.bfloat16).contiguous()
    )
    if decoder_hash != inventory_receipt["decoder_bfloat16_sha256"]:
        _fail("g4_vector_reconstruction", "SAE decoder BF16 hash differs")
    rows = inventory_receipt["vectors"]
    by_identity = {
        (tuple(row["subset_feature_ids"]), row["control_type"], row["sign"]): row
        for row in rows
    }
    reconstructed_vectors: dict[tuple[tuple[int, ...], str, int], Any] = {}
    for assignment in protocol.g4_aggregate_assignments():
        assignment_id = str(assignment["assignment_id"])
        subset = tuple(int(value) for value in assignment["target_feature_ids"])
        target = _aggregate_decoder_independent(decoder, subset)
        target_norm = float(target.float().norm().item())
        matched_ids = tuple(mapping[target_id] for target_id in subset)
        raw_matched = _aggregate_decoder_independent(decoder, matched_ids)
        matched, matched_scale, matched_raw_norm, matched_norm, matched_error = _norm_match_independent(raw_matched, target)
        seed = protocol.identity_bound_seed64("g4-isotropic-v1", assignment_id)
        generator = np.random.Generator(np.random.PCG64(seed))
        values = generator.standard_normal(expected_shape[0]).astype(np.float32)
        values /= max(float(np.linalg.norm(values)), 1e-30)
        raw_isotropic = torch.from_numpy(values).to(dtype=torch.bfloat16)
        isotropic, isotropic_scale, isotropic_raw_norm, isotropic_norm, isotropic_error = _norm_match_independent(raw_isotropic, target)
        controls = {
            "target": (target, target, target_norm, 1.0, target_norm, 0.0, subset, None),
            "matched": (matched, raw_matched, matched_raw_norm, matched_scale, matched_norm, matched_error, matched_ids, None),
            "isotropic": (isotropic, raw_isotropic, isotropic_raw_norm, isotropic_scale, isotropic_norm, isotropic_error, (), seed),
        }
        for vector_class, control in controls.items():
            positive, raw_positive, raw_norm, scale, final_norm, error, resolved, isotropic_seed = control
            positive_hash = _tensor_sha256_independent(positive)
            negative = torch.neg(positive).contiguous()
            negative_hash = _tensor_sha256_independent(negative)
            for sign in protocol.G4_SIGNS:
                vector = positive if sign == 1 else negative
                raw_vector = raw_positive if sign == 1 else torch.neg(raw_positive).contiguous()
                row = by_identity[(subset, vector_class, sign)]
                exact = {
                    "assignment_id": assignment_id,
                    "subset_feature_ids": list(subset),
                    "control_type": vector_class,
                    "sign": sign,
                    "coefficient": 0.5 * sign,
                    "resolved_feature_ids": list(resolved),
                    "isotropic_seed": isotropic_seed,
                    "raw_norm": raw_norm,
                    "raw_vector_sha256": _tensor_sha256_independent(raw_vector),
                    "norm_rescale": scale,
                    "final_norm": final_norm,
                    "norm_relative_error": error,
                    "target_reference_final_norm": target_norm,
                    "vector_rms": float(vector.float().norm().item()) / math.sqrt(vector.numel()),
                    "vector_sha256": _tensor_sha256_independent(vector),
                    "dtype": "bfloat16",
                    "finite": True,
                    "precomputed_before_any_edited_forward": True,
                    "edited_forward_count_at_compute": 0,
                    "positive_vector_sha256": positive_hash,
                    "negative_vector_sha256": negative_hash,
                    "signed_pair_exact_negation": True,
                }
                for field, expected in exact.items():
                    if row[field] != expected:
                        _fail(
                            "g4_vector_reconstruction",
                            f"G4 reconstructed {assignment_id}/{vector_class}/{sign}/{field} differs",
                        )
                reconstructed_vectors[(subset, vector_class, sign)] = vector.detach().clone()
    del decoder, state
    return reconstructed_vectors


def validate_g4_hook_tensors(
    tensor_path: Path,
    index_path: Path,
    *,
    telemetry_rows: Sequence[Mapping[str, Any]],
    vectors: Mapping[tuple[tuple[int, ...], str, int], Any],
) -> None:
    """Rebuild BF16 ``pre + vector`` and compare the persisted post-edit bytes."""

    try:
        import torch
    except ImportError as exc:  # pragma: no cover - production dependency
        raise StructuralAuditError("g4_hook_tensors", "PyTorch is required") from exc
    try:
        bundle = torch.load(tensor_path, map_location="cpu", weights_only=True, mmap=True)
    except Exception as exc:
        raise StructuralAuditError("g4_hook_tensors", "cannot load hook tensor bundle") from exc
    if not isinstance(bundle, Mapping) or set(bundle) != {"pre_edit", "post_edit"}:
        _fail("g4_hook_tensors", "hook tensor bundle fields differ")
    pre, post = bundle["pre_edit"], bundle["post_edit"]
    expected_shape = (1200, protocol.MODEL_SPEC["residual_width"])
    for tensor, label in ((pre, "pre"), (post, "post")):
        if (
            not isinstance(tensor, torch.Tensor)
            or tensor.device.type != "cpu"
            or tensor.dtype != torch.bfloat16
            or tuple(tensor.shape) != expected_shape
            or not bool(torch.isfinite(tensor).all())
        ):
            _fail("g4_hook_tensors", f"persisted {label}-edit tensor contract differs")
    index_rows: list[dict[str, Any]] = []
    try:
        with index_path.open("r", encoding="utf-8") as handle:
            for line in handle:
                value = json.loads(line)
                if not isinstance(value, dict):
                    _fail("g4_hook_tensors", "hook tensor index row is not an object")
                index_rows.append(value)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise StructuralAuditError("g4_hook_tensors", "cannot read hook tensor index") from exc
    fields = frozenset(
        {
            "tensor_row_index",
            "prompt_id",
            "subset_feature_ids",
            "control_type",
            "sign",
            "pre_edit_sha256",
            "post_edit_sha256",
        }
    )
    if len(index_rows) != 1200 or len(telemetry_rows) != 1200:
        _fail("g4_hook_tensors", "hook tensor/index/telemetry count differs")
    for offset, (index, telemetry) in enumerate(zip(index_rows, telemetry_rows)):
        _require_fields(index, fields, f"G4 hook tensor index {offset}")
        identity = (
            telemetry["prompt_id"],
            tuple(telemetry["subset_feature_ids"]),
            telemetry["control_type"],
            telemetry["sign"],
        )
        if (
            index["tensor_row_index"] != offset
            or (
                index["prompt_id"],
                tuple(index["subset_feature_ids"]),
                index["control_type"],
                index["sign"],
            )
            != identity
        ):
            _fail("g4_hook_tensors", "hook tensor index/order differs from telemetry")
        pre_row = pre[offset].contiguous()
        post_row = post[offset].contiguous()
        pre_hash = _tensor_sha256_independent(pre_row)
        post_hash = _tensor_sha256_independent(post_row)
        if (
            index["pre_edit_sha256"] != pre_hash
            or index["post_edit_sha256"] != post_hash
            or telemetry["edited_pre_edit_sha256"] != pre_hash
            or telemetry["clean_pre_edit_sha256"] != pre_hash
            or telemetry["expected_post_edit_sha256"] != post_hash
            or telemetry["observed_post_edit_sha256"] != post_hash
        ):
            _fail("g4_hook_tensors", "hook tensor hashes do not bind index/telemetry")
        vector = vectors[(identity[1], identity[2], identity[3])]
        expected_post = (
            pre_row.to(dtype=torch.bfloat16)
            + vector.to(device="cpu", dtype=torch.bfloat16)
        ).to(dtype=torch.bfloat16).contiguous()
        if (
            _tensor_sha256_independent(expected_post) != post_hash
            or not torch.equal(expected_post.view(torch.int16), post_row.view(torch.int16))
        ):
            _fail("g4_hook_tensors", "persisted post-edit bytes differ from BF16 pre+vector")
    del bundle, pre, post


def _bind_g4_measurements_to_inventory(
    rows_by_file: Mapping[str, Sequence[Mapping[str, Any]]],
    *,
    inventory: Mapping[str, Any],
) -> None:
    indexed = {
        (tuple(row["subset_feature_ids"]), row["control_type"], row["sign"]): row
        for row in inventory["vectors"]
    }
    bound_fields = (
        "subset_feature_ids",
        "control_type",
        "sign",
        "coefficient",
        "vector_rms",
        "vector_sha256",
        "dtype",
        "finite",
        "precomputed_before_any_edited_forward",
        "edited_forward_count_at_compute",
    )
    for measurement in rows_by_file["g4_vector_rows.jsonl"]:
        identity = (
            tuple(measurement["subset_feature_ids"]),
            measurement["control_type"],
            measurement["sign"],
        )
        inventory_row = indexed.get(identity)
        if inventory_row is None or any(
            measurement[field] != inventory_row[field] for field in bound_fields
        ):
            _fail("g4_inventory_binding", "G4 vector measurement differs from sealed inventory")
    for telemetry in rows_by_file["g4_telemetry_rows.jsonl"]:
        identity = (
            tuple(telemetry["subset_feature_ids"]),
            telemetry["control_type"],
            telemetry["sign"],
        )
        inventory_row = indexed.get(identity)
        if (
            inventory_row is None
            or telemetry["coefficient"] != inventory_row["coefficient"]
            or telemetry["vector_sha256"] != inventory_row["vector_sha256"]
        ):
            _fail("g4_inventory_binding", "G4 telemetry names another sealed vector")


def _audit_phase(
    directory: Path,
    *,
    phase: str,
    artifact_root: Path,
    plan_hash: str,
    execution_hash: str,
    tokenizer_inventory_hash: str,
    expected_tokenizer_receipt_hash: str | None,
    expected_tokenizer_receipt: Mapping[str, Any] | None,
    token_ids: tuple[int, ...] | None,
    semantic_endpoint_ids: Mapping[str, int] | None,
    sae_path: Path,
    global_task_ids: set[str],
    global_row_ids: set[str],
) -> dict[str, Any]:
    run_id = directory.name
    if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", run_id) is None:
        _fail("transaction_path", f"{phase} run ID is unsafe")
    expected_parent = (
        artifact_root.resolve(strict=True)
        / protocol.STUDY_SLUG
        / protocol.STUDY_ID
        / PHASE_DIRECTORY_NAMES[phase]
    )
    if directory.resolve(strict=True).parent != expected_parent.resolve(strict=True):
        _fail("transaction_path", f"{phase} directory is outside its namespaced phase root")
    verified = _verify_completed_transaction(
        directory,
        phase=phase,
        run_id=run_id,
        plan_hash=plan_hash,
        execution_hash=execution_hash,
    )
    token_receipt = _load_json(directory / "TOKENIZER_AUDIT.json", f"{phase} tokenizer audit")
    token_binding = validate_tokenizer_receipt(
        token_receipt,
        plan_manifest_sha256=plan_hash,
        tokenizer_inventory_sha256=tokenizer_inventory_hash,
    )
    if (
        expected_tokenizer_receipt_hash is not None
        and token_binding["receipt_sha256"] != expected_tokenizer_receipt_hash
    ) or (
        expected_tokenizer_receipt is not None
        and token_receipt != expected_tokenizer_receipt
    ):
        _fail("tokenizer_binding", f"{phase} tokenizer receipt differs across phases")
    phase_binding = _load_json(directory / "PHASE_BINDING.json", f"{phase} phase binding")
    _validate_phase_binding(
        phase_binding,
        phase=phase,
        run_id=run_id,
        plan_hash=plan_hash,
        execution_hash=execution_hash,
        tokenizer_receipt_hash=token_binding["receipt_sha256"],
        tokenizer_inventory_hash=tokenizer_inventory_hash,
    )
    runtime_metadata = _load_json(directory / "RUNTIME_METADATA.json", f"{phase} runtime metadata")
    _validate_runtime_metadata(
        runtime_metadata,
        phase=phase,
        run_id=run_id,
        plan_hash=plan_hash,
        execution_hash=execution_hash,
        tokenizer_receipt_hash=token_binding["receipt_sha256"],
    )
    for label, value in (
        ("tokenizer audit", token_receipt),
        ("phase binding", phase_binding),
        ("runtime metadata", runtime_metadata),
        ("file manifest", verified["manifest"]),
    ):
        _assert_empty_inputs(value, label=f"{phase} {label}")
    effective_token_ids = token_ids or token_binding["token_ids"]
    effective_semantic_ids = semantic_endpoint_ids or token_binding["semantic_endpoint_ids"]
    for filename in PHASE_ROW_FILENAMES[phase]:
        rows = verified["rows"][filename]
        _validate_measurement_rows(
            rows,
            filename=filename,
            phase=phase,
            run_id=run_id,
            plan_hash=plan_hash,
            token_ids=effective_token_ids,
            semantic_endpoint_ids=effective_semantic_ids,
            global_task_ids=global_task_ids,
            global_row_ids=global_row_ids,
        )
        _assert_empty_inputs(rows, label=f"{phase}/{filename}")
    vector_receipt: dict[str, Any] | None = None
    vector_hash: str | None = None
    if phase == "G4":
        vector_receipt = _load_json(
            directory / "G4_VECTOR_INVENTORY.json", "G4 vector inventory"
        )
        vector_binding = validate_vector_inventory_receipt(
            vector_receipt, plan_manifest_sha256=plan_hash
        )
        validate_g4_matching_table(
            directory / "G4_MATCHING_TABLE.jsonl",
            inventory_receipt=vector_receipt,
        )
        reconstructed_vectors = validate_g4_vector_arithmetic(
            sae_path,
            inventory_receipt=vector_receipt,
            mapping=vector_binding["mapping"],
        )
        _bind_g4_measurements_to_inventory(
            verified["rows"], inventory=vector_receipt
        )
        validate_g4_hook_tensors(
            directory / "G4_HOOK_TENSORS.pt",
            directory / "G4_HOOK_TENSOR_INDEX.jsonl",
            telemetry_rows=verified["rows"]["g4_telemetry_rows.jsonl"],
            vectors=reconstructed_vectors,
        )
        _assert_empty_inputs(vector_receipt, label="G4 vector inventory")
        vector_hash = vector_binding["receipt_sha256"]
    measurement_files = verified["receipt"]["measurement_files"]
    if set(measurement_files) != set(PHASE_ROW_FILENAMES[phase]):
        _fail("measurement_manifest", f"{phase} measurement-file inventory differs")
    for filename, record in measurement_files.items():
        _require_fields(record, MEASUREMENT_RECORD_FIELDS, f"{phase}/{filename} binding")
    return {
        "tokenizer_receipt": token_receipt,
        "tokenizer_binding": token_binding,
        "vector_inventory_receipt": vector_receipt,
        "vector_inventory_receipt_sha256": vector_hash,
        "file_manifest": {
            "file_manifest_content_sha256": verified["receipt"]["file_manifest_content_sha256"],
            "file_manifest_embedded_sha256": verified["receipt"]["file_manifest_embedded_sha256"],
        },
        "measurement_files": measurement_files,
    }


def audit_pilot(
    *,
    plan_dir: Path,
    execution_binding_path: Path,
    artifact_root: Path,
    volume_id: str,
    phase_directories: Mapping[str, Path],
    repo_root: Path = REPO_ROOT,
) -> dict[str, Any]:
    """Run the independent structural audit and derive analysis authorization."""

    if set(phase_directories) != set(PHASE_ROW_FILENAMES):
        _fail("phase_inventory", "phase-directory mapping must contain exactly G1/G2/G3/G3P/G4")
    plan_binding = validate_plan_independently(plan_dir, repo_root=repo_root)
    plan_hash = plan_binding["plan_manifest_sha256"]
    source_inventory_hash, audit_source_hash = _source_bindings(
        plan_dir, repo_root, plan_manifest_sha256=plan_hash
    )
    execution_binding, artifacts = _validate_execution_and_artifacts(
        execution_binding_path,
        plan_manifest_sha256=plan_hash,
        artifact_root=artifact_root,
        volume_id=volume_id,
        repo_root=repo_root,
    )
    execution_hash = str(execution_binding["execution_binding_canonical_sha256"])
    tokenizer_inventory_hash = str(
        execution_binding["tokenizer_content_inventory_sha256"]
    )
    phase_manifests: dict[str, Any] = {}
    phase_measurements: dict[str, Any] = {}
    tokenizer_receipt_hash: str | None = str(
        execution_binding["tokenizer_audit_receipt_sha256"]
    )
    tokenizer_receipt: Mapping[str, Any] | None = None
    token_ids: tuple[int, ...] | None = None
    semantic_ids: Mapping[str, int] | None = None
    vector_inventory_hash: str | None = None
    global_task_ids: set[str] = set()
    global_row_ids: set[str] = set()
    for phase in ("G1", "G2", "G3", "G3P", "G4"):
        result = _audit_phase(
            phase_directories[phase],
            phase=phase,
            artifact_root=artifact_root,
            plan_hash=plan_hash,
            execution_hash=execution_hash,
            tokenizer_inventory_hash=tokenizer_inventory_hash,
            expected_tokenizer_receipt_hash=tokenizer_receipt_hash,
            expected_tokenizer_receipt=tokenizer_receipt,
            token_ids=token_ids,
            semantic_endpoint_ids=semantic_ids,
            sae_path=artifacts["sae"],
            global_task_ids=global_task_ids,
            global_row_ids=global_row_ids,
        )
        if tokenizer_receipt is None:
            tokenizer_receipt = result["tokenizer_receipt"]
            token_ids = result["tokenizer_binding"]["token_ids"]
            semantic_ids = result["tokenizer_binding"]["semantic_endpoint_ids"]
        phase_manifests[phase] = result["file_manifest"]
        phase_measurements[phase] = result["measurement_files"]
        if phase == "G4":
            vector_inventory_hash = result["vector_inventory_receipt_sha256"]
    if tokenizer_receipt_hash is None or vector_inventory_hash is None:
        _fail("audit_incomplete", "tokenizer or G4 vector binding is missing")
    structural_core = {
        "schema_version": 1,
        "receipt_kind": "independent_structural_audit_v1",
        "status": "pass",
        "issuer": protocol.STRUCTURAL_AUDIT_ISSUER,
        "study_id": protocol.STUDY_ID,
        "protocol_version": protocol.PROTOCOL_VERSION,
        "plan_manifest_sha256": plan_hash,
        "execution_binding_canonical_sha256": execution_hash,
        "source_inventory_sha256": source_inventory_hash,
        "structural_audit_source_sha256": audit_source_hash,
        "tokenizer_audit_receipt_sha256": tokenizer_receipt_hash,
        "vector_inventory_receipt_sha256": vector_inventory_hash,
        "phase_file_manifests": phase_manifests,
        "phase_measurement_files": phase_measurements,
        "prior_outcome_inputs": [],
        "target_prompt_inputs": [],
        "target_outcome_inputs": [],
    }
    structural_receipt = {
        **structural_core,
        "receipt_sha256": protocol.canonical_sha256(structural_core),
    }
    authorization_core = {
        "schema_version": 1,
        "authorization_kind": "pilot_analysis_authorization_v2",
        "status": "authorized",
        "issuer": protocol.STRUCTURAL_AUDIT_ISSUER,
        "study_id": protocol.STUDY_ID,
        "protocol_version": protocol.PROTOCOL_VERSION,
        "plan_manifest_sha256": plan_hash,
        "execution_binding_canonical_sha256": execution_hash,
        "source_inventory_sha256": source_inventory_hash,
        "structural_audit_source_sha256": audit_source_hash,
        "tokenizer_audit_receipt_sha256": tokenizer_receipt_hash,
        "vector_inventory_receipt_sha256": vector_inventory_hash,
        "phase_file_manifests": phase_manifests,
        "phase_measurement_files": phase_measurements,
        "prior_outcome_inputs": [],
        "target_prompt_inputs": [],
        "target_outcome_inputs": [],
        "structural_audit_receipt_sha256": structural_receipt["receipt_sha256"],
    }
    authorization = {
        **authorization_core,
        "receipt_sha256": protocol.canonical_sha256(authorization_core),
    }
    return {
        "structural_audit_receipt": structural_receipt,
        "analysis_authorization": authorization,
    }


def write_audit_outputs(
    output_dir: Path,
    bundle: Mapping[str, Any],
    *,
    artifact_root: Path,
    volume_id: str,
) -> Path:
    """Atomically publish audit artifacts under the sentinel-bound audit root."""

    if artifact_root.is_symlink():
        _fail("output_path", "artifact root may not be a symlink")
    try:
        root = artifact_root.resolve(strict=True)
    except OSError:
        _fail("output_path", "artifact root is unavailable")
    sentinel_path = root / VOLUME_SENTINEL
    if sentinel_path.is_symlink() or not sentinel_path.is_file():
        _fail("output_path", "audit output volume sentinel is missing or unsafe")
    sentinel = _load_json(sentinel_path, "audit output volume sentinel")
    if any(
        sentinel.get(key) != value
        for key, value in (
            ("study_slug", protocol.STUDY_SLUG),
            ("study_id", protocol.STUDY_ID),
            ("volume_id", volume_id),
        )
    ):
        _fail("output_path", "audit output volume sentinel differs")
    study_root = root / protocol.STUDY_SLUG
    namespace = study_root / protocol.STUDY_ID
    if (
        study_root.is_symlink()
        or not study_root.is_dir()
        or namespace.is_symlink()
        or not namespace.is_dir()
    ):
        _fail("output_path", "audit output study namespace is missing or unsafe")
    try:
        namespace.resolve(strict=True).relative_to(root)
    except ValueError:
        _fail("output_path", "audit output study namespace escapes the artifact root")
    audit_root = namespace / "audit"
    if audit_root.exists() or audit_root.is_symlink():
        if audit_root.is_symlink() or not audit_root.is_dir():
            _fail("output_path", "audit phase root is unsafe")
    else:
        audit_root.mkdir(mode=0o700)
    candidate = output_dir.expanduser().resolve(strict=False)
    if (
        output_dir.is_symlink()
        or candidate.exists()
        or candidate.parent != audit_root.resolve(strict=True)
        or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", candidate.name) is None
    ):
        _fail(
            "output_path",
            "audit output must be a fresh direct child of the external audit root",
        )
    structural = bundle.get("structural_audit_receipt")
    authorization = bundle.get("analysis_authorization")
    if not isinstance(structural, Mapping) or not isinstance(authorization, Mapping):
        _fail("output_schema", "audit output bundle is incomplete")
    partial = candidate.with_name(candidate.name + ".partial")
    if partial.exists() or partial.is_symlink():
        _fail("output_path", "audit partial output already exists")
    partial.mkdir(mode=0o700)
    for filename, value in (
        (STRUCTURAL_RECEIPT_FILENAME, structural),
        (ANALYSIS_AUTHORIZATION_FILENAME, authorization),
    ):
        with (partial / filename).open("xb") as handle:
            handle.write(protocol.canonical_json_bytes(value) + b"\n")
            handle.flush()
            os.fsync(handle.fileno())
    os.replace(partial, candidate)
    directory_fd = os.open(audit_root, os.O_RDONLY)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)
    return candidate


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan-dir", type=Path, required=True)
    parser.add_argument("--execution-binding", type=Path, required=True)
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--volume-id", required=True)
    for phase in ("G1", "G2", "G3", "G3P", "G4"):
        parser.add_argument(f"--{phase.lower()}-directory", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    bundle = audit_pilot(
        plan_dir=args.plan_dir,
        execution_binding_path=args.execution_binding,
        artifact_root=args.artifact_root,
        volume_id=args.volume_id,
        phase_directories={
            phase: getattr(args, f"{phase.lower()}_directory")
            for phase in ("G1", "G2", "G3", "G3P", "G4")
        },
    )
    write_audit_outputs(
        args.output_dir,
        bundle,
        artifact_root=args.artifact_root,
        volume_id=args.volume_id,
    )
    print(bundle["structural_audit_receipt"]["receipt_sha256"])
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

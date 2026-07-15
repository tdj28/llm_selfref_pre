#!/usr/bin/env python3
"""Build the outcome-blind r3 audit-recovery scientific-equivalence packet.

The packet is deliberately narrower than a repository archive.  It binds the
frozen plan, extracts the source closure that defines the scientific audit,
records the recovery adapter surface, and freezes the projection used to
compare original and recovered scientific outputs.  It never opens a raw run
or a compact result.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Mapping, Sequence


REPO_ROOT = Path(__file__).resolve().parents[2]
PLAN_RELATIVE_ROOT = (
    "data/consciousness_sae_target_blind_calibration/calibration_v2_plan_20260714_r3"
)
PLAN_ROOT = REPO_ROOT / PLAN_RELATIVE_ROOT

FROZEN_SOURCE_ROOTS: Mapping[str, tuple[str, ...]] = {
    "experiments/consciousness_sae_realization_validation/runtime.py": (
        "tensor_sha256",
    ),
    "experiments/consciousness_sae_target_blind_calibration/audit.py": (
        "audit",
        "_publish_pair_atomic",
    ),
    "experiments/consciousness_sae_target_blind_calibration/orientation.py": (
        "execute",
        "validate",
    ),
    "experiments/consciousness_sae_target_blind_calibration/validate_plan.py": (
        "validate",
    ),
    "experiments/consciousness_sae_target_blind_calibration/audit_runtime_shim.py": (
        "tensor_sha256",
    ),
}
PROTOCOL_PATH = "experiments/consciousness_sae_target_blind_calibration/protocol.py"
RECOVERY_PATH = (
    "experiments/consciousness_sae_target_blind_calibration/audit_recovery.py"
)
EXTRACTOR_PATH = (
    "experiments/consciousness_sae_target_blind_calibration/scientific_equivalence.py"
)
EQUIVALENCE_TEST_PATH = (
    "tests/consciousness_sae_target_blind_calibration/test_scientific_equivalence.py"
)
RECOVERY_EXTRACTED_SYMBOLS = (
    "_load_j_checkpoint_recovery",
    "_patched_audit_runtime",
    "_recovery_metadata",
    "_enrich_outputs",
    "_publish_recovery_pair_atomic",
    "execute_recovery",
)
PLAN_FRAGMENT_PATHS = (
    f"{PLAN_RELATIVE_ROOT}/plan_manifest.json",
    f"{PLAN_RELATIVE_ROOT}/protocol_snapshot.json",
    f"{PLAN_RELATIVE_ROOT}/calibration_plan.jsonl",
    f"{PLAN_RELATIVE_ROOT}/source_files.json",
)

# This is an affirmative projection, not a deny-list.  New scientific output
# fields cannot silently enter the equivalence claim without changing this
# file, its hash, the packet, and the focused test.
SCIENTIFIC_AUDIT_FIELDS = (
    "schema_version",
    "status",
    "study_id",
    "protocol_version",
    "run_id",
    "recomputed_realization_row_count",
    "recomputed_readout_transport_row_count",
    "recomputed_linearity_row_count",
    "artifact_recomputation",
    "target_prompt_render_count",
    "target_feature_vector_count",
    "analysis_data_inputs",
)
SCIENTIFIC_SUMMARY_FIELDS = (
    "schema_version",
    "status",
    "study_id",
    "protocol_version",
    "run_id",
    "edit_integrity_status",
    "realized_source_linearity_status",
    "j_of_realized_linearity_status",
    "downstream_model_linearity_status",
    "j_shadow_status",
    "j_orientation_status",
    "j_projection_claim_eligibility",
    "later_actual_state_collection_eligibility",
    "hard_safety_failure_count_all_doses",
    "realization_gate_failure_count",
    "diagnostic_one_percent_failure_count",
    "j_shadow_gate_failure_count",
    "diagnostic_one_percent_j_shadow_failure_count",
    "linearity_failure_counts",
    "by_dose",
    "linearity_rows",
    "readout_transport",
    "claim_policy",
    "adaptive_design_inputs",
    "analysis_data_inputs",
    "target_prompt_render_count",
    "target_feature_vector_count",
)

EXPECTED_PATCH_TARGETS = (
    "_AuditBudgetWatchdog",
    "_audit_external_receipt_chain",
    "_load_j_checkpoint",
)
EXPECTED_EXECUTION_CALL_COUNTS = {
    "_enrich_outputs": 1,
    "_publish_recovery_pair_atomic": 1,
    "audit.audit": 1,
}


class ScientificEquivalenceError(RuntimeError):
    """The purported equivalence packet does not match the frozen design."""


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(8 * 1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _file_record(relative_path: str) -> dict[str, Any]:
    path = REPO_ROOT / relative_path
    return {
        "path": relative_path,
        "bytes": path.stat().st_size,
        "sha256": file_sha256(path),
    }


def _load_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ScientificEquivalenceError(f"JSON root is not an object: {path}")
    return value


def _node_name(node: ast.AST) -> str | None:
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        return node.name
    return None


def _top_level_symbols(tree: ast.Module) -> dict[str, ast.AST]:
    output: dict[str, ast.AST] = {}
    for node in tree.body:
        name = _node_name(node)
        if name is not None:
            output[name] = node
    return output


def _local_call_closure(tree: ast.Module, roots: Sequence[str]) -> tuple[str, ...]:
    symbols = _top_level_symbols(tree)
    missing = sorted(set(roots) - set(symbols))
    if missing:
        raise ScientificEquivalenceError(f"source symbols are missing: {missing}")
    seen: set[str] = set()
    pending = list(roots)
    while pending:
        name = pending.pop()
        if name in seen:
            continue
        seen.add(name)
        for node in ast.walk(symbols[name]):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                called = node.func.id
                if called in symbols and called not in seen:
                    pending.append(called)
    return tuple(sorted(seen, key=lambda name: symbols[name].lineno))


def _source_record(
    relative_path: str,
    roots: Sequence[str],
    *,
    transitive: bool,
    plan_sources: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    path = REPO_ROOT / relative_path
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=relative_path)
    symbols = _top_level_symbols(tree)
    names = _local_call_closure(tree, roots) if transitive else tuple(roots)
    missing = sorted(set(names) - set(symbols))
    if missing:
        raise ScientificEquivalenceError(
            f"source symbols are missing from {relative_path}: {missing}"
        )
    extracts = []
    for name in names:
        node = symbols[name]
        text = ast.get_source_segment(source, node)
        if text is None:
            raise ScientificEquivalenceError(
                f"could not extract {relative_path}:{name}"
            )
        extracts.append(
            {
                "symbol": name,
                "first_line": int(node.lineno),
                "last_line": int(node.end_lineno or node.lineno),
                "source_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
                "source": text,
            }
        )
    physical_hash = file_sha256(path)
    frozen = plan_sources.get(relative_path)
    if frozen is not None and (
        frozen.get("sha256") != physical_hash
        or int(frozen.get("bytes", -1)) != path.stat().st_size
    ):
        raise ScientificEquivalenceError(
            f"frozen plan source binding differs: {relative_path}"
        )
    return {
        "path": relative_path,
        "bytes": path.stat().st_size,
        "sha256": physical_hash,
        "frozen_plan_bound": frozen is not None,
        "frozen_plan_sha256": None if frozen is None else frozen["sha256"],
        "extraction": "transitive_local_call_closure"
        if transitive
        else "named_symbols",
        "roots": list(roots),
        "symbols": extracts,
    }


def _call_name(node: ast.Call) -> str | None:
    if isinstance(node.func, ast.Name):
        return node.func.id
    if isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name):
        return f"{node.func.value.id}.{node.func.attr}"
    return None


def inspect_recovery_adapter() -> dict[str, Any]:
    source = (REPO_ROOT / RECOVERY_PATH).read_text(encoding="utf-8")
    tree = ast.parse(source, filename=RECOVERY_PATH)
    symbols = _top_level_symbols(tree)
    patch_node = symbols.get("_patched_audit_runtime")
    execute_node = symbols.get("execute_recovery")
    if patch_node is None or execute_node is None:
        raise ScientificEquivalenceError("recovery adapter entry points are missing")
    patch_targets = sorted(
        {
            target.attr
            for node in ast.walk(patch_node)
            if isinstance(node, (ast.Assign, ast.AnnAssign))
            for target in (
                node.targets if isinstance(node, ast.Assign) else [node.target]
            )
            if isinstance(target, ast.Attribute)
            and isinstance(target.value, ast.Name)
            and target.value.id == "audit"
        }
    )
    if tuple(patch_targets) != EXPECTED_PATCH_TARGETS:
        raise ScientificEquivalenceError(
            f"recovery monkeypatch surface differs: {patch_targets}"
        )
    calls: dict[str, int] = {}
    for node in ast.walk(execute_node):
        if isinstance(node, ast.Call):
            name = _call_name(node)
            if name is not None:
                calls[name] = calls.get(name, 0) + 1
    selected_counts = {
        name: calls.get(name, 0) for name in EXPECTED_EXECUTION_CALL_COUNTS
    }
    if selected_counts != EXPECTED_EXECUTION_CALL_COUNTS:
        raise ScientificEquivalenceError(
            f"recovery scientific call surface differs: {selected_counts}"
        )
    return {
        "frozen_scientific_entrypoint": "audit.audit",
        "publication_entrypoint": "_publish_recovery_pair_atomic",
        "monkeypatched_audit_attributes": patch_targets,
        "execution_call_counts": selected_counts,
        "allowed_scientific_compatibility_delta": {
            "old_predicate": "available_layers == required_layers",
            "recovery_predicate": "required_layers subset_of available_layers",
            "selected_map_contract": (
                "mapping handed to the frozen audit contains exactly required "
                "protocol.J_LAYERS with the same objects/bytes"
            ),
            "missing_required_layer": "reject",
            "unused_extra_layer": (
                "record in recovery_audit.j_checkpoint_inventory then ignore"
            ),
            "frozen_artifact_metadata_contract": (
                "artifact_recomputation.j_lens retains the frozen sha256, "
                "required-map count, and revision shape"
            ),
        },
        "operational_adapters": {
            "_AuditBudgetWatchdog": "fresh recovery clock and spend boundary",
            "_audit_external_receipt_chain": (
                "validate historical external receipts at original completion time"
            ),
            "output_enrichment": "recovery provenance only",
            "publication": (
                "operational clone of frozen atomic pair publication evaluated "
                "against the separately named recovery clock"
            ),
            "audit_runtime_shim": (
                "model-free implementation of the frozen exact-byte tensor digest; "
                "synthetic equivalence is required by the focused test"
            ),
        },
        "scientific_output_projection": {
            "audit_fields": list(SCIENTIFIC_AUDIT_FIELDS),
            "summary_fields": list(SCIENTIFIC_SUMMARY_FIELDS),
        },
    }


def extract_scientific_fields(
    audit_receipt: Mapping[str, Any], summary: Mapping[str, Any]
) -> dict[str, Any]:
    """Project an audit pair onto the frozen scientific output schema."""

    missing_audit = sorted(set(SCIENTIFIC_AUDIT_FIELDS) - set(audit_receipt))
    missing_summary = sorted(set(SCIENTIFIC_SUMMARY_FIELDS) - set(summary))
    if missing_audit or missing_summary:
        raise ScientificEquivalenceError(
            "scientific output fields are missing: "
            f"audit={missing_audit}, summary={missing_summary}"
        )
    return {
        "audit": {name: audit_receipt[name] for name in SCIENTIFIC_AUDIT_FIELDS},
        "summary": {name: summary[name] for name in SCIENTIFIC_SUMMARY_FIELDS},
    }


def _inherited_design(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    prompts = snapshot["prompt_payloads"]
    directions = snapshot["directions"]
    doses = snapshot["dose_grid"]
    readout_layers = snapshot["readout_transport_layers"]
    transports = snapshot["transports"]
    thresholds = snapshot["thresholds"]
    fixed = snapshot["fixed_panel_estimand"]
    claim_policy = snapshot["claim_gate_policy"]
    forwards = snapshot["forward_inventory"]
    if (
        len(prompts) != 8
        or len(directions) != 3
        or len(doses) != 5
        or len(readout_layers) != 29
        or len(transports) != 7
    ):
        raise ScientificEquivalenceError("frozen design cardinality differs")
    return {
        "scope": {
            "study_role": snapshot["study_role"],
            "recovery_role": "audit_only_no_new_scientific_observations",
            "analysis_data_inputs": snapshot["analysis_data_inputs"],
            "target_prompt_or_feature_inputs": False,
            "substantive_adequacy_revalidated_by_recovery": False,
        },
        "independent_unit": {
            "primary_fixed_panel_resampling_unit": fixed["resampling_unit"],
            "unit_count": len(prompts),
            "unit_ids": [row["prompt_id"] for row in prompts],
            "population_generalization_claim": fixed["population_generalization_claim"],
            "j_lens_prompts_fitted": snapshot["j_lens"]["release_config"][
                "prompts_fitted"
            ],
            "j_lens_prompts_fitted_role": (
                "public_artifact_training_metadata_not_current_study_units"
            ),
        },
        "sample_size_and_repeated_observations": {
            "prompt_units": len(prompts),
            "directions_per_prompt": len(directions),
            "dose_levels_per_prompt_direction": len(doses),
            "signed_pairs": len(prompts) * len(directions) * len(doses),
            "signed_branches_per_pair": 2,
            "gated_signed_pairs": (
                len(prompts) * len(directions) * len(snapshot["realization_gate_doses"])
            ),
            "local_linearity_sites": len(prompts) * len(directions),
            "orientation_fixtures": (
                len(snapshot["captured_j_layers"])
                * int(snapshot["j_orientation"]["fixture_count_per_layer"])
            ),
            "primary_dose_readout_rows": (
                len(prompts) * len(directions) * len(readout_layers) * len(transports)
            ),
            "model_forward_inventory": forwards,
            "new_model_forwards_in_recovery": 0,
        },
        "estimands": {
            "fixed_panel_primary": fixed,
            "delivery": {
                "unit": "prompt_id_by_direction_by_dose_signed_pair",
                "components": snapshot["requested_realized_components"],
                "metrics": [
                    "requested_to_realized_relative_rmse",
                    "requested_to_realized_cosine",
                    "common_mode_to_central_rms",
                ],
                "gate_scope": "all_96_prespecified_2_3_4_8_percent_pairs",
            },
            "local_linearity": {
                "sites": "eight_prompts_by_three_directions",
                "doses": snapshot["linearity_gate_doses"],
                "anchor_dose": snapshot["primary_dose"],
                "components": [
                    "realized_source",
                    "j_of_realized",
                    "actual_final",
                ],
            },
            "j_readout": {
                "primary_layer": snapshot["primary_readout_layer"],
                "primary_dose": snapshot["primary_dose"],
                "metrics": [
                    "residual_delta_cosine",
                    "fixed_token_logit_delta_pearson",
                ],
                "contrasts": [
                    "absolute_real_j",
                    "real_j_minus_identity",
                    "real_j_minus_best_of_five_random",
                ],
                "aggregation_order": fixed["aggregation_order"],
                "nonprimary_layers": fixed["other_readout_layers_role"],
            },
        },
        "controls": {
            "transport_controls": list(transports[1:]),
            "j_orientation_wrong_orientation_control": True,
            "bf16_production_vs_fp32_shadow": True,
            "clean_pre_edit_and_upstream_byte_identity": True,
            "signed_common_mode_control": True,
        },
        "missingness_and_exclusions": {
            "missing_rows": "reject_entire_audit",
            "duplicate_rows": "reject_entire_audit",
            "extra_or_unmanifested_raw_files": "reject_entire_audit",
            "nonfinite_values": "reject_entire_audit",
            "partial_transaction": "reject_entire_audit",
            "imputation": "none",
            "outcome_based_exclusion": "none",
            "source_contract": snapshot["independent_recomputation"][
                "reject_unmanifested_missing_duplicate_nonfinite_or_partial_data"
            ],
        },
        "bootstrap": {
            "resampling_unit": fixed["resampling_unit"],
            "unit_count": len(prompts),
            "replicates": fixed["resampling_replicates"],
            "confidence": thresholds["confidence"],
            "interval_label": fixed["interval_label"],
            "aggregation_order": fixed["aggregation_order"],
            "population_confidence_interval_claim": False,
        },
        "multiplicity": {
            "primary_family": (
                "two metrics at sole primary layer 50, each with absolute, "
                "identity, and strongest-of-five-random gates"
            ),
            "formal_adjustment": "none_specified_in_frozen_protocol",
            "decision_form": "conjunctive_component_gates",
            "across_layer_selection": fixed["across_layer_selection"],
            "layers_51_78": "descriptive_only_not_eligibility_tests",
            "recovery_change": "none",
        },
        "power_and_generalization": {
            "prospective_population_power_analysis": "not_specified",
            "fixed_panel_prompt_units": len(prompts),
            "interval_interpretation": fixed["interval_label"],
            "population_generalization_claim": False,
            "power_changed_or_increased_by_recovery": False,
        },
        "stopping": {
            "scientific_inventory": "fixed_complete_inventory_no_optional_stopping",
            "expected_model_forwards": forwards["exact_total_model_forwards"],
            "partial_or_watchdog_stopped_transaction": "inadmissible",
            "recovery_new_observation_stopping_rule": "not_applicable_zero_forwards",
            "threshold_weakening_after_outcomes": "forbidden",
        },
        "frozen_claim_gates": {
            "policy": claim_policy,
            "thresholds": thresholds,
            "primary_layer_only_for_j_eligibility": snapshot["primary_readout_layer"],
        },
        "measurement_contract": {
            "intervention_state_contract": snapshot["intervention_state_contract"],
            "intervention_state_contract_sha256": snapshot[
                "intervention_state_contract_sha256"
            ],
            "j_state_contract": snapshot["j_state_contract"],
            "j_state_contract_sha256": snapshot["j_state_contract_sha256"],
            "prompt_payloads": prompts,
            "token_panel_scope": fixed["token_id_scope"],
        },
    }


def _plan_bindings() -> tuple[dict[str, Any], dict[str, Mapping[str, Any]]]:
    manifest = _load_object(PLAN_ROOT / "plan_manifest.json")
    core = dict(manifest)
    supplied = core.pop("plan_manifest_sha256", None)
    if supplied != canonical_sha256(core):
        raise ScientificEquivalenceError("frozen plan manifest self-hash differs")
    manifested_rows = manifest.get("files")
    if not isinstance(manifested_rows, list):
        raise ScientificEquivalenceError("frozen plan file inventory is missing")
    manifested_index = {str(row["path"]): row for row in manifested_rows}
    if len(manifested_index) != len(manifested_rows):
        raise ScientificEquivalenceError("frozen plan file inventory is duplicated")
    source_file = _load_object(PLAN_ROOT / "source_files.json")
    rows = source_file.get("files")
    if not isinstance(rows, list):
        raise ScientificEquivalenceError("frozen source inventory is missing")
    source_index = {str(row["path"]): row for row in rows}
    if len(source_index) != len(rows):
        raise ScientificEquivalenceError("frozen source inventory is duplicated")
    bindings = []
    for relative in PLAN_FRAGMENT_PATHS:
        path = REPO_ROOT / relative
        record = {
            "path": relative,
            "bytes": path.stat().st_size,
            "sha256": file_sha256(path),
        }
        name = path.name
        if name != "plan_manifest.json":
            expected = manifested_index.get(name)
            if expected is None or (
                expected.get("sha256") != record["sha256"]
                or int(expected.get("bytes", -1)) != record["bytes"]
            ):
                raise ScientificEquivalenceError(
                    f"manifested plan fragment differs: {name}"
                )
        bindings.append(record)
    return (
        {
            "plan_manifest_sha256": supplied,
            "fragments": bindings,
        },
        source_index,
    )


def build_packet() -> dict[str, Any]:
    plan, source_index = _plan_bindings()
    snapshot = _load_object(PLAN_ROOT / "protocol_snapshot.json")
    source_records = [
        _source_record(
            path,
            roots,
            transitive=True,
            plan_sources=source_index,
        )
        for path, roots in FROZEN_SOURCE_ROOTS.items()
    ]
    protocol_record = _source_record(
        PROTOCOL_PATH,
        (),
        transitive=False,
        plan_sources=source_index,
    )
    recovery_record = _source_record(
        RECOVERY_PATH,
        RECOVERY_EXTRACTED_SYMBOLS,
        transitive=False,
        plan_sources=source_index,
    )
    core = {
        "schema_version": 1,
        "packet_type": "outcome_blind_audit_recovery_scientific_equivalence",
        "status": "source_and_design_bound_no_outcomes_loaded",
        "study_id": snapshot["study_id"],
        "protocol_version": snapshot["protocol_version"],
        "scope_statement": (
            "This packet establishes implementation and design identity for an "
            "audit-only correction. It does not revalidate the substantive "
            "adequacy of the inherited design and contains no recovered result."
        ),
        "outcome_input_paths": [],
        "raw_run_opened": False,
        "compact_result_opened": False,
        "frozen_plan": plan,
        "inherited_design": _inherited_design(snapshot),
        "frozen_scientific_sources": source_records,
        "protocol_source_binding": protocol_record,
        "recovery_adapter_source": recovery_record,
        "reproducibility_tooling": {
            "extractor": _file_record(EXTRACTOR_PATH),
            "focused_test": _file_record(EQUIVALENCE_TEST_PATH),
            "regeneration_command": (
                "python3 -B -m experiments.consciousness_sae_target_blind_"
                "calibration.scientific_equivalence --json-out <fresh-json> "
                "--markdown-out <fresh-markdown>"
            ),
        },
        "machine_semantic_diff": inspect_recovery_adapter(),
    }
    return {**core, "packet_sha256": canonical_sha256(core)}


def render_markdown(packet: Mapping[str, Any]) -> str:
    design = packet["inherited_design"]
    sample = design["sample_size_and_repeated_observations"]
    bootstrap = design["bootstrap"]
    multiplicity = design["multiplicity"]
    return f"""# Audit-recovery scientific-equivalence appendix

This appendix is outcome-blind. It binds the frozen r3 scientific auditor and
machine plan to the audit-only recovery, but it does **not** claim that the
recovery revalidates the substantive adequacy of the inherited design. No raw
run or compact result is an input to the extractor.

Packet SHA-256: `{packet["packet_sha256"]}`

## What is mechanically established

- The original plan manifest and frozen source bytes are hash-bound.
- The recovery invokes the same `audit.audit` scientific entry point exactly
  once. A separately extracted atomic publisher applies the fresh recovery
  clock without rewriting the original campaign fields.
- The only scientific compatibility change is the J-map inventory predicate:
  all required layers must exist; only those required maps are handed to the
  frozen auditor; unused extras are recorded in recovery-only provenance and
  ignored. The frozen J-artifact metadata shape retains the required-map count.
- Original and recovered outputs are compared through an affirmative frozen
  scientific-field projection. Recovery provenance fields are outside that
  projection and cannot substitute for a scientific field.

## Inherited design (no outcomes)

- Independent unit: `prompt_id`; {design["independent_unit"]["unit_count"]}
  exact frozen prompt units. This is a fixed-panel stability calculation, not
  a prompt-population confidence interval.
- The J-checkpoint field `n_prompts=125` describes prompts used to fit the
  public artifact; it is not this study's sample size or resampling unit.
- Repeated observations: {sample["directions_per_prompt"]} directions x
  {sample["dose_levels_per_prompt_direction"]} doses per prompt, yielding
  {sample["signed_pairs"]} signed pairs and {sample["gated_signed_pairs"]}
  prespecified gated pairs.
- Model inventory: {sample["model_forward_inventory"]["exact_total_model_forwards"]}
  original model forwards; the recovery adds zero.
- Primary J estimand: layer 50 at dose 0.03, mean directions within prompt and
  then mean prompts, for residual cosine and fixed-token logit Pearson.
  Layers 51-78 remain descriptive only.
- Missingness/exclusion: missing, duplicate, extra/unmanifested, nonfinite, or
  partial data reject the audit; there is no imputation or outcome-based
  exclusion.
- Bootstrap: {bootstrap["replicates"]} prompt-resampling replicates over
  {bootstrap["unit_count"]} prompt units; interval label
  `{bootstrap["interval_label"]}`.
- Multiplicity: {multiplicity["primary_family"]}; formal adjustment is
  `{multiplicity["formal_adjustment"]}`. Eligibility is conjunctive and there
  is no across-layer selection.
- Stopping: complete fixed inventory, no optional scientific stopping. Partial
  or watchdog-stopped transactions are inadmissible.
- Claim gates and every numerical threshold are reproduced verbatim in the
  machine-readable packet.

## Scope boundary

This appendix answers the recovery-equivalence question. It does not add
independent units, increase power, turn fixed-panel intervals into population
intervals, repair any inherited multiplicity limitation, or authorize a new
model forward. Any such claim requires a separate prospective review.
"""


def _write_exclusive(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json-out", type=Path, required=True)
    parser.add_argument("--markdown-out", type=Path, required=True)
    args = parser.parse_args()
    packet = build_packet()
    _write_exclusive(args.json_out, canonical_json_bytes(packet) + b"\n")
    _write_exclusive(args.markdown_out, render_markdown(packet).encode("utf-8"))
    print(args.json_out)
    print(args.markdown_out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

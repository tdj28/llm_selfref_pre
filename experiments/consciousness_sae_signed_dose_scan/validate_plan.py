#!/usr/bin/env python3
"""Independently validate the prospectively frozen signed-dose machine plan."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
from pathlib import Path
from typing import Any, Mapping


REPO_ROOT = Path(__file__).resolve().parents[2]
EXPECTED_STUDY_ID = "consciousness_sae_signed_dose_scan_v1"
EXPECTED_PROTOCOL_VERSION = "consciousness_sae_signed_dose_scan_v1.0.0"
EXPECTED_CANONICAL_PLAN_RELATIVE_PATH = (
    "data/consciousness_sae_signed_dose_scan/dose_scan_v1_plan_20260716"
)
EXPECTED_SCOPE = "exploratory_target_blind_generic_vector_signed_dose_curve"
EXPECTED_PROMPT_IDS = tuple(f"neutral_c{index:02d}" for index in range(1, 9))
EXPECTED_DIRECTIONS = (0, 1, 2)
EXPECTED_DOSE_BASIS_POINTS = tuple(range(50, 3_001, 50))
EXPECTED_SIGNED_DOSE_BASIS_POINTS = tuple(range(-3_000, 3_001, 50))
EXPECTED_REFERENCE_ONLINE_J_DOSE_BASIS_POINTS = 300
EXPECTED_RAW_NAMESPACE = (
    "consciousness_sae_signed_dose_scan/"
    "consciousness_sae_signed_dose_scan_v1/raw"
)
EXPECTED_PAIR_COUNT = 1_440
EXPECTED_EDITED_FORWARD_COUNT = 2_880
EXPECTED_MODEL_FORWARD_COUNT = 2_896
EXPECTED_RESULT_INDEX_SHA256 = (
    "35cc3aa2f94bc7b78d592eb30f3b1137042a30ed33ebb9276b0625fea0083cf7"
)
EXPECTED_PROMPT_PAYLOADS_SHA256 = (
    "2318cfebbb50b780e4735bac0d11875f02f068d60c92dbfbc68122e1f6e8de58"
)
EXPECTED_FROZEN_OBJECT_SHA256 = {
    "model": "1ee42fb6fd50513e6cb2983c5f8c60d5f7430c9e74ab1648851fe1fc9b088a58",
    "sae": "fd4b10ae3796388b5175c92048811198e14a924181a2b54df8831da8ff386802",
    "j_lens": "361561b7101e5288a1a237b43d4585a64f8f119778fea7c9525d04fb86d0d6ce",
    "container_image": "941b2955d8877304eaab0d03c785797c7f3ea08bee9c3b60a17a0d9685a3606f",
    "intervention_state_contract": (
        "c41104cfd547a58e3f01c6ccc1528f4d9252cc27ddac758e6801db84ff84113b"
    ),
    "j_state_contract": (
        "5712892ad28f319d8758b940566e3e2a353fd6e51e547166571bba5956d4db77"
    ),
    "j_orientation": (
        "322465c3a50d1932f366c7ad3f9fa4b570ad6b796afaad0d1eb25873c19e69e9"
    ),
    "claim_gate_policy": (
        "d9264979c9e55c8cb1cdb0459552a58fea402228721d235d2530dc14ef93fe3b"
    ),
    "independent_recomputation": (
        "289cc5cf4d3cf0fca16664b2136b026083f8c7b758d07f824e7f332ca0a492a2"
    ),
    "resource_limits": (
        "b3522348015c36274bc3e6e355168704c846623ca44a612c9bdffe99d8f01be9"
    ),
    "design_provenance": (
        "9bb63adfba04ac26305a7894fe87117f837c50189a53cfc972219eec7bfc0ef9"
    ),
    "storage": "d6efeb8bee76f2acb6bbe7fd34d28ca44ae22485b74fd3db3f7d319be0d70b20",
}
EXPECTED_RANDOMIZATION_NAMESPACES = {
    "runtime_seed_namespace": "signed-dose-scan-runtime-v1",
    "direction_seed_namespace": "signed-dose-scan-generic-layer50-direction-v1",
    "fixed_token_panel_seed_namespace": "signed-dose-scan-fixed-token-panel-v1",
    "random_j_seed_namespace": "signed-dose-scan-random-j-v1",
    "j_orientation_seed_namespace": "signed-dose-scan-j-orientation-v1",
}
EXPECTED_SMALL_MODEL_PROMOTION_SPEC = {
    "role": "operational_only_smaller_model_validation",
    "required_before_large_model_authorization": True,
    "model_id": "google/gemma-2-9b-it",
    "model_revision": "11c9b309abf73637e4b6f9a3fa1e92e615547819",
    "sae_repo": "google/gemma-scope-9b-it-res",
    "sae_revision": "e86af97a5b6fbbccca28ab654f2fda1b0768f770",
    "sae_folder": "layer_20/width_16k/average_l0_91",
    "sae_feature_id": 1_295,
    "prompt_id": "neutral_calendar_continuation_v1",
    "nonzero_dose_count": 60,
    "signed_pair_count": 60,
    "edited_forward_count": 120,
    "zero_baseline_count": 1,
    "required_gates": ["structural", "numeric", "hook", "artifact_replay"],
    "promotion_scope": "runner_mechanics_only_not_scientific_protocol",
    "semantic_outcome_gate": False,
    "effect_size_gate": False,
    "dose_threshold_tuning_gate": False,
}
EXPECTED_PLAN_FILE_NAMES = (
    "protocol_snapshot.json",
    "dose_scan_plan.jsonl",
    "design_provenance.json",
    "source_files.json",
)
REQUIRED_BOUND_SOURCES = (
    ".gitignore",
    "data/consciousness_sae_signed_dose_scan/README.md",
    "docs/consciousness_sae_signed_dose_scan/PRIOR_REVIEW_CONTEXT.md",
    "docs/consciousness_sae_signed_dose_scan/PRO_REVIEW_BRIEF.md",
    "docs/consciousness_sae_signed_dose_scan/PROTOCOL.md",
    "docs/consciousness_sae_target_blind_calibration/results/"
    "calv2-r3-audit-recovery-3a9a54d-20260716T202903Z/RESULT_SUMMARY.json",
    "experiments/__init__.py",
    "experiments/consciousness_sae_realization_validation/__init__.py",
    "experiments/consciousness_sae_realization_validation/legacy_public_artifact_manifest.json",
    "experiments/consciousness_sae_realization_validation/protocol.py",
    "experiments/consciousness_sae_realization_validation/runpod_preflight.py",
    "experiments/consciousness_sae_realization_validation/runtime.py",
    "experiments/consciousness_sae_target_blind_calibration/__init__.py",
    "experiments/consciousness_sae_target_blind_calibration/orientation.py",
    "experiments/consciousness_sae_target_blind_calibration/protocol.py",
    "experiments/consciousness_sae_target_blind_calibration/runner.py",
    "experiments/exp2_sae/__init__.py",
    "experiments/exp2_sae/gemma_scope_9b_protocol.py",
    "experiments/exp2_sae/gemma_scope_9b_runtime.py",
    "experiments/consciousness_sae_signed_dose_scan/__init__.py",
    "experiments/consciousness_sae_signed_dose_scan/README.md",
    "experiments/consciousness_sae_signed_dose_scan/audit.py",
    "experiments/consciousness_sae_signed_dose_scan/authorize.py",
    "experiments/consciousness_sae_signed_dose_scan/build_plan.py",
    "experiments/consciousness_sae_signed_dose_scan/gemma9b_validation.py",
    "experiments/consciousness_sae_signed_dose_scan/gemma9b_validation_audit.py",
    "experiments/consciousness_sae_signed_dose_scan/guest_launcher.py",
    "experiments/consciousness_sae_signed_dose_scan/orientation.py",
    "experiments/consciousness_sae_signed_dose_scan/protocol.py",
    "experiments/consciousness_sae_signed_dose_scan/requirements-runpod-b200.txt",
    "experiments/consciousness_sae_signed_dose_scan/review_adjudication.py",
    "experiments/consciousness_sae_signed_dose_scan/runner.py",
    "experiments/consciousness_sae_signed_dose_scan/setup_runpod_guest.sh",
    "experiments/consciousness_sae_signed_dose_scan/validate_plan.py",
    "src/prompts.py",
    "tests/consciousness_sae_signed_dose_scan/__init__.py",
    "tests/consciousness_sae_signed_dose_scan/test_gemma9b_validation.py",
    "tests/consciousness_sae_signed_dose_scan/test_execution_chain.py",
    "tests/consciousness_sae_signed_dose_scan/test_protocol.py",
    "tests/consciousness_sae_signed_dose_scan/test_plan.py",
)
COMMIT_RE = re.compile(r"[0-9a-f]{40}")
HEX64_RE = re.compile(r"[0-9a-f]{64}")


class IndependentPlanAuditError(RuntimeError):
    pass


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


def sha256_file(path: Path, *, chunk_bytes: int = 8 * 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(chunk_bytes):
            digest.update(chunk)
    return digest.hexdigest()


def _absolute(path: Path) -> Path:
    return Path(os.path.abspath(path.expanduser()))


def _require_no_symlink_components(path: Path, label: str) -> None:
    candidate = _absolute(path)
    current = Path(candidate.anchor)
    for part in candidate.parts[1:]:
        current = current / part
        if current.is_symlink():
            raise IndependentPlanAuditError(
                f"{label} contains a symlink component: {current}"
            )


def _regular_file(path: Path, label: str) -> Path:
    _require_no_symlink_components(path, label)
    try:
        details = path.lstat()
    except OSError as exc:
        raise IndependentPlanAuditError(f"{label} is missing") from exc
    if not stat.S_ISREG(details.st_mode) or details.st_nlink != 1:
        raise IndependentPlanAuditError(
            f"{label} is not a single-link regular file"
        )
    return path


def _json(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(_regular_file(path, label).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise IndependentPlanAuditError(f"{label} is not canonical JSON") from exc
    if not isinstance(value, dict):
        raise IndependentPlanAuditError(f"{label} is not an object")
    if path.read_bytes() != canonical_json_bytes(value) + b"\n":
        raise IndependentPlanAuditError(f"{label} bytes are not canonical")
    return value


def _jsonl(path: Path, label: str) -> list[dict[str, Any]]:
    source = _regular_file(path, label).read_bytes()
    if not source or not source.endswith(b"\n"):
        raise IndependentPlanAuditError(f"{label} has invalid framing")
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(source.splitlines(), 1):
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise IndependentPlanAuditError(
                f"{label} line {line_number} is invalid"
            ) from exc
        if not isinstance(value, dict) or line != canonical_json_bytes(value):
            raise IndependentPlanAuditError(
                f"{label} line {line_number} is not canonical"
            )
        rows.append(value)
    return rows


def _expected_rows() -> list[dict[str, Any]]:
    return [
        {
            "prompt_id": prompt_id,
            "edit_layer": 50,
            "direction": direction,
            "dose_basis_points": dose_basis_points,
            "dose_fraction": dose_basis_points / 10_000,
        }
        for prompt_id in EXPECTED_PROMPT_IDS
        for direction in EXPECTED_DIRECTIONS
        for dose_basis_points in EXPECTED_DOSE_BASIS_POINTS
    ]


def _validate_snapshot(snapshot: Mapping[str, Any]) -> None:
    if (
        snapshot.get("schema_version") != 1
        or snapshot.get("status")
        != "prospective_execution_requires_review_freeze_and_small_model_gate"
        or snapshot.get("execution_authorized") is not False
        or snapshot.get("study_slug") != "consciousness_sae_signed_dose_scan"
        or snapshot.get("study_id") != EXPECTED_STUDY_ID
        or snapshot.get("protocol_version") != EXPECTED_PROTOCOL_VERSION
        or snapshot.get("scope") != EXPECTED_SCOPE
        or snapshot.get("canonical_plan_relative_path")
        != EXPECTED_CANONICAL_PLAN_RELATIVE_PATH
        or snapshot.get("paper_or_target_prompts_included") is not False
        or snapshot.get("target_sae_features_included") is not False
        or snapshot.get("generic_vector_scan") is not True
    ):
        raise IndependentPlanAuditError("protocol snapshot identity differs")
    prompt_payloads = snapshot.get("prompt_payloads")
    if (
        not isinstance(prompt_payloads, list)
        or tuple(row.get("prompt_id") for row in prompt_payloads) != EXPECTED_PROMPT_IDS
        or canonical_sha256(prompt_payloads) != EXPECTED_PROMPT_PAYLOADS_SHA256
        or snapshot.get("directions") != list(EXPECTED_DIRECTIONS)
        or snapshot.get("edit_layer") != 50
    ):
        raise IndependentPlanAuditError("prompt/direction contract differs")
    if any(
        canonical_sha256(snapshot.get(key)) != expected
        for key, expected in EXPECTED_FROZEN_OBJECT_SHA256.items()
    ):
        raise IndependentPlanAuditError("frozen protocol object differs")
    if (
        snapshot.get("intervention_state_contract_sha256")
        != EXPECTED_FROZEN_OBJECT_SHA256["intervention_state_contract"]
        or snapshot.get("j_state_contract_sha256")
        != EXPECTED_FROZEN_OBJECT_SHA256["j_state_contract"]
    ):
        raise IndependentPlanAuditError("frozen state-contract digest differs")
    if (
        snapshot.get("dose_step_basis_points") != 50
        or snapshot.get("max_dose_basis_points") != 3_000
        or snapshot.get("nonzero_dose_basis_points")
        != list(EXPECTED_DOSE_BASIS_POINTS)
        or snapshot.get("reported_signed_dose_basis_points")
        != list(EXPECTED_SIGNED_DOSE_BASIS_POINTS)
        or snapshot.get("zero_baseline")
        != {
            "dose_basis_points": 0,
            "execution": "one_clean_continuation_per_prompt",
            "direction_specific_duplicates": False,
            "signed_pair": False,
            "curve_role": "shared_origin",
        }
    ):
        raise IndependentPlanAuditError("basis-point grid/zero contract differs")
    curve = snapshot.get("dose_curve_estimand")
    reference = snapshot.get("reference_online_j_readout")
    if (
        not isinstance(curve, Mapping)
        or curve.get("status") != "exploratory_full_curve"
        or curve.get("all_grid_points_reported") is not True
        or curve.get("favorable_dose_selection") is not False
        or curve.get("dose_failure_deletion") is not False
        or not isinstance(reference, Mapping)
        or reference.get("dose_basis_points")
        != EXPECTED_REFERENCE_ONLINE_J_DOSE_BASIS_POINTS
        or reference.get("cannot_rescue_or_replace_actual_state_curve") is not True
    ):
        raise IndependentPlanAuditError("curve/reference-readout contract differs")
    fresh = snapshot.get("fresh_randomization")
    if not isinstance(fresh, Mapping) or any(
        fresh.get(key) != value
        for key, value in EXPECTED_RANDOMIZATION_NAMESPACES.items()
    ):
        raise IndependentPlanAuditError("fresh randomization contract differs")
    if (
        fresh.get("predecessor_randomization_reused") is not False
        or fresh.get("predecessor_control_values_reused") is not False
    ):
        raise IndependentPlanAuditError("predecessor controls were reused")
    if snapshot.get("small_model_promotion") != EXPECTED_SMALL_MODEL_PROMOTION_SPEC:
        raise IndependentPlanAuditError("small-model promotion contract differs")
    inventory = snapshot.get("forward_inventory")
    if inventory != {
        "schema_version": 1,
        "model_forward_definition": "one_full_model_forward_invocation",
        "prefix_forwards": 8,
        "clean_continuation_forwards": 8,
        "edited_continuation_forwards": EXPECTED_EDITED_FORWARD_COUNT,
        "exact_total_model_forwards": EXPECTED_MODEL_FORWARD_COUNT,
        "orientation_fixture_model_forwards": 0,
    }:
        raise IndependentPlanAuditError("forward inventory differs")
    resources = snapshot.get("resource_limits")
    if (
        not isinstance(resources, Mapping)
        or resources.get("expected_signed_pairs") != EXPECTED_PAIR_COUNT
        or resources.get("expected_edited_forwards")
        != EXPECTED_EDITED_FORWARD_COUNT
        or resources.get("expected_model_forwards") != EXPECTED_MODEL_FORWARD_COUNT
        or resources.get("expected_raw_bytes_approx") != 2_300_000_000
        or resources.get("raw_run_ceiling_bytes") != 4 * 1024**3
        or resources.get("max_spend_usd") != 9.0
        or resources.get("provider_authority_spend_cap_usd") != 36.0
    ):
        raise IndependentPlanAuditError("resource envelope differs")
    storage = snapshot.get("storage")
    if (
        not isinstance(storage, Mapping)
        or storage.get("raw_namespace") != EXPECTED_RAW_NAMESPACE
        or storage.get("predecessor_raw_namespace_is_input") is not False
        or storage.get("raw_transaction_is_new") is not True
    ):
        raise IndependentPlanAuditError("storage namespace differs")
    if snapshot.get("analysis_data_inputs") != []:
        raise IndependentPlanAuditError("analysis inputs are not empty")


def validate(plan_dir: Path, *, enforce_canonical_path: bool = False) -> dict[str, Any]:
    root = _absolute(plan_dir)
    _require_no_symlink_components(root, "plan directory")
    if not root.is_dir():
        raise IndependentPlanAuditError("plan directory is missing")
    canonical = _absolute(REPO_ROOT / EXPECTED_CANONICAL_PLAN_RELATIVE_PATH)
    if enforce_canonical_path and root != canonical:
        raise IndependentPlanAuditError("plan directory differs from canonical path")

    manifest = _json(root / "plan_manifest.json", "plan manifest")
    core = dict(manifest)
    supplied = core.pop("plan_manifest_sha256", None)
    if supplied != canonical_sha256(core):
        raise IndependentPlanAuditError("plan manifest self-hash differs")
    if (
        manifest.get("schema_version") != 1
        or manifest.get("status") != "prospectively_frozen_exploratory_plan"
        or manifest.get("execution_authorized") is not False
        or manifest.get("runner_implemented_in_frozen_closure") is not True
        or manifest.get("audit_implemented_in_frozen_closure") is not True
        or manifest.get("study_id") != EXPECTED_STUDY_ID
        or manifest.get("protocol_version") != EXPECTED_PROTOCOL_VERSION
        or manifest.get("scope") != EXPECTED_SCOPE
        or manifest.get("canonical_plan_relative_path")
        != EXPECTED_CANONICAL_PLAN_RELATIVE_PATH
        or COMMIT_RE.fullmatch(str(manifest.get("git_head_commit", ""))) is None
        or manifest.get("paper_prompt_render_count") != 0
        or manifest.get("target_prompt_render_count") != 0
        or manifest.get("target_feature_vector_count") != 0
        or manifest.get("analysis_data_inputs") != []
        or manifest.get("zero_baseline_continuation_count") != 8
        or manifest.get("nonzero_dose_magnitude_count") != 60
        or manifest.get("signed_pair_count") != EXPECTED_PAIR_COUNT
        or manifest.get("signed_edited_forward_count")
        != EXPECTED_EDITED_FORWARD_COUNT
        or manifest.get("exact_model_forward_count") != EXPECTED_MODEL_FORWARD_COUNT
        or manifest.get("reference_online_j_dose_basis_points") != 300
        or manifest.get("raw_namespace") != EXPECTED_RAW_NAMESPACE
    ):
        raise IndependentPlanAuditError("plan manifest contract differs")

    records = manifest.get("files")
    if (
        not isinstance(records, list)
        or tuple(row.get("path") for row in records if isinstance(row, Mapping))
        != EXPECTED_PLAN_FILE_NAMES
    ):
        raise IndependentPlanAuditError("plan file inventory differs")
    for record in records:
        if not isinstance(record, Mapping) or set(record) != {
            "path",
            "bytes",
            "sha256",
        }:
            raise IndependentPlanAuditError("plan file row schema differs")
        path = _regular_file(root / str(record["path"]), "bound plan file")
        if (
            isinstance(record["bytes"], bool)
            or not isinstance(record["bytes"], int)
            or path.stat().st_size != record["bytes"]
            or sha256_file(path) != record["sha256"]
        ):
            raise IndependentPlanAuditError(f"plan file differs: {record['path']}")

    snapshot = _json(root / "protocol_snapshot.json", "protocol snapshot")
    _validate_snapshot(snapshot)
    rows = _jsonl(root / "dose_scan_plan.jsonl", "dose scan plan")
    expected_rows = _expected_rows()
    if rows != expected_rows or len(rows) != EXPECTED_PAIR_COUNT:
        raise IndependentPlanAuditError("dose scan row grid differs")
    if any(row["dose_basis_points"] == 0 for row in rows):
        raise IndependentPlanAuditError("zero was duplicated as a signed pair")

    provenance = _json(root / "design_provenance.json", "design provenance")
    if (
        provenance != snapshot.get("design_provenance")
        or provenance.get("role")
        != "design_provenance_only_no_rows_loaded_or_pooled"
        or provenance.get("predecessor_result_index_file_sha256")
        != EXPECTED_RESULT_INDEX_SHA256
        or provenance.get("raw_data_inputs") != []
        or provenance.get("analysis_data_inputs") != []
        or provenance.get("predecessor_rows_loaded") != 0
    ):
        raise IndependentPlanAuditError("design provenance differs")

    source_value = _json(root / "source_files.json", "source inventory")
    sources = source_value.get("files")
    if (
        set(source_value) != {"files"}
        or not isinstance(sources, list)
        or tuple(row.get("path") for row in sources if isinstance(row, Mapping))
        != REQUIRED_BOUND_SOURCES
    ):
        raise IndependentPlanAuditError("source inventory differs")
    for record in sources:
        if not isinstance(record, Mapping) or set(record) != {
            "path",
            "bytes",
            "sha256",
        }:
            raise IndependentPlanAuditError("source row schema differs")
        path = _regular_file(REPO_ROOT / str(record["path"]), "bound source")
        if (
            isinstance(record["bytes"], bool)
            or not isinstance(record["bytes"], int)
            or path.stat().st_size != record["bytes"]
            or sha256_file(path) != record["sha256"]
        ):
            raise IndependentPlanAuditError(f"bound source differs: {record['path']}")
    result_path = _regular_file(
        REPO_ROOT
        / "docs/consciousness_sae_target_blind_calibration/results/"
        "calv2-r3-audit-recovery-3a9a54d-20260716T202903Z/RESULT_SUMMARY.json",
        "predecessor result index",
    )
    if sha256_file(result_path) != EXPECTED_RESULT_INDEX_SHA256:
        raise IndependentPlanAuditError("predecessor design-provenance hash differs")

    audit_core = {
        "schema_version": 1,
        "status": "pass_prospectively_frozen_exploratory_plan",
        "study_id": EXPECTED_STUDY_ID,
        "protocol_version": EXPECTED_PROTOCOL_VERSION,
        "canonical_plan_relative_path": EXPECTED_CANONICAL_PLAN_RELATIVE_PATH,
        "plan_manifest_sha256": supplied,
        "source_file_count": len(sources),
        "source_inventory_sha256": canonical_sha256(sources),
        "nonzero_dose_magnitude_count": len(EXPECTED_DOSE_BASIS_POINTS),
        "signed_pair_count": len(rows),
        "reconstructed_edited_forward_count": 2 * len(rows),
        "reconstructed_model_forward_count": 2 * len(EXPECTED_PROMPT_IDS)
        + 2 * len(rows),
        "zero_baseline_continuation_count": len(EXPECTED_PROMPT_IDS),
        "reference_online_j_dose_basis_points": 300,
        "raw_namespace": EXPECTED_RAW_NAMESPACE,
        "prompt_payloads_sha256": EXPECTED_PROMPT_PAYLOADS_SHA256,
        "frozen_protocol_objects_sha256": EXPECTED_FROZEN_OBJECT_SHA256,
        "execution_authorized": False,
    }
    return {**audit_core, "receipt_sha256": canonical_sha256(audit_core)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    receipt = validate(args.plan_dir, enforce_canonical_path=True)
    output = _absolute(args.output)
    if os.path.lexists(output):
        raise FileExistsError(f"refusing to overwrite audit receipt: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(canonical_json_bytes(receipt) + b"\n")
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

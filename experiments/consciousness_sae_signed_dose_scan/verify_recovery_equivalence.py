#!/usr/bin/env python3
"""Independently verify the signed-dose audit-recovery equivalence packet.

This verifier intentionally does not import ``recovery_equivalence``.  It
restates the frozen identities, affirmative scientific projection, recovery
closure, and the one allowed compatibility change.  It opens no raw run and no
compact result.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import re
import stat
import subprocess
from pathlib import Path
from typing import Any, Callable, Mapping


REPO_ROOT = Path(__file__).resolve().parents[2]
ORIGINAL_FREEZE_COMMIT = "a084caafc2ec27860044d80d3b33912f656fd08a"
ORIGINAL_PLAN_SOURCE_COMMIT = "6a065b1c64b8451a8f4fa408770f699ce7f5ff3f"
ORIGINAL_PLAN_ROOT = (
    "data/consciousness_sae_signed_dose_scan/dose_scan_v1_plan_20260716"
)
ORIGINAL_PLAN_PATHS = tuple(
    f"{ORIGINAL_PLAN_ROOT}/{name}"
    for name in (
        "plan_manifest.json",
        "protocol_snapshot.json",
        "dose_scan_plan.jsonl",
        "design_provenance.json",
        "source_files.json",
    )
)
ORIGINAL_PLAN_MANIFEST_RECEIPT = (
    "79810742bd2899ae0805e294fb5b9640870a21fe60e4c85a73b241b92963c51d"
)
ORIGINAL_PLAN_AUDIT_RECEIPT = (
    "0ac75a5ed2ee06a4d4260301179eff950636440af182f8e1056b20f5cfa46f7f"
)
ORIGINAL_SOURCE_INVENTORY_RECEIPT = (
    "94fa3e25e2aa7c9e40ea00cb9cb4e3d516d0606fe7c8f140f3b5dbf81eaeb0b5"
)
PREDECESSOR_PRECEDENT_COMMIT = "e187342"
PREDECESSOR_PRECEDENT_PATHS = {
    "experiments/consciousness_sae_target_blind_calibration/scientific_equivalence.py": (
        "ad8455d852af60a6603866db038036bf98ff47bde8e8d990ba067790d59ef61e"
    ),
    "experiments/consciousness_sae_target_blind_calibration/audit_recovery.py": (
        "8196543b5ed3004b19fd884f2fc60e4fc4724a950494bc0c366d4840b8907e16"
    ),
    "tests/consciousness_sae_target_blind_calibration/test_scientific_equivalence.py": (
        "2fe6f3597e7247fbee9ee26b9a21a6c82e00ab07a98731125478ef3c2467bd57"
    ),
    "docs/consciousness_sae_target_blind_calibration/AUDIT_RECOVERY_SCIENTIFIC_EQUIVALENCE.json": (
        "3210f2c8ea4df8500db82ca3e7798f77b2da54f6d6dde6cb5c606db703bba49f"
    ),
    "docs/consciousness_sae_target_blind_calibration/results/"
    "calv2-r3-audit-recovery-3a9a54d-20260716T202903Z/"
    "RECOVERY_BUNDLE_VERIFICATION.json": (
        "dc485ffd041942233f93627a8ea7a87a72a22d4cef6b08f788eeae89a5eb62e3"
    ),
    "docs/consciousness_sae_target_blind_calibration/results/"
    "calv2-r3-audit-recovery-3a9a54d-20260716T202903Z/"
    "FINAL_RECOVERY_LAUNCH_GATE.json": (
        "d9207c388bc8d0d8ccd1c17b4bd5eeeb9ac00ebdf276fef9eb24e448e8fe549d"
    ),
}
RECOVERY_CLOSURE_PATHS = (
    ".gitignore",
    "data/consciousness_sae_signed_dose_scan/README.md",
    "docs/consciousness_sae_signed_dose_scan/AUDIT_ONLY_RECOVERY_AMENDMENT_20260717.md",
    "docs/consciousness_sae_signed_dose_scan/INCIDENT_CLOSURE.json",
    "docs/consciousness_sae_signed_dose_scan/INCIDENT_CLOSURE_SCHEMA.json",
    "docs/consciousness_sae_signed_dose_scan/INCIDENT_CLOSURE_VERIFICATION.json",
    "docs/consciousness_sae_signed_dose_scan/PRIOR_REVIEW_CONTEXT.md",
    "docs/consciousness_sae_signed_dose_scan/PRO_REVIEW_BRIEF.md",
    "docs/consciousness_sae_signed_dose_scan/PRO_REVIEW_REPAIR_CONTEXT.md",
    "docs/consciousness_sae_signed_dose_scan/PROTOCOL.md",
    "docs/consciousness_sae_signed_dose_scan/RECOVERY_CYCLE_LEDGER.json",
    "docs/consciousness_sae_signed_dose_scan/RECOVERY_REPRODUCTION.md",
    "docs/consciousness_sae_target_blind_calibration/results/"
    "calv2-r3-audit-recovery-3a9a54d-20260716T202903Z/RESULT_SUMMARY.json",
    "experiments/__init__.py",
    "experiments/consciousness_sae_realization_validation/__init__.py",
    "experiments/consciousness_sae_realization_validation/"
    "legacy_public_artifact_manifest.json",
    "experiments/consciousness_sae_realization_validation/protocol.py",
    "experiments/consciousness_sae_realization_validation/runpod_preflight.py",
    "experiments/consciousness_sae_realization_validation/runtime.py",
    "experiments/consciousness_sae_target_blind_calibration/__init__.py",
    "experiments/consciousness_sae_target_blind_calibration/audit_recovery.py",
    "experiments/consciousness_sae_target_blind_calibration/orientation.py",
    "experiments/consciousness_sae_target_blind_calibration/protocol.py",
    "experiments/consciousness_sae_target_blind_calibration/runner.py",
    "experiments/exp2_sae/__init__.py",
    "experiments/exp2_sae/gemma_scope_9b_protocol.py",
    "experiments/exp2_sae/gemma_scope_9b_runtime.py",
    "experiments/consciousness_sae_signed_dose_scan/__init__.py",
    "experiments/consciousness_sae_signed_dose_scan/README.md",
    "experiments/consciousness_sae_signed_dose_scan/audit.py",
    "experiments/consciousness_sae_signed_dose_scan/audit_recovery.py",
    "experiments/consciousness_sae_signed_dose_scan/authorize.py",
    "experiments/consciousness_sae_signed_dose_scan/build_plan.py",
    "experiments/consciousness_sae_signed_dose_scan/gemma9b_validation.py",
    "experiments/consciousness_sae_signed_dose_scan/gemma9b_validation_audit.py",
    "experiments/consciousness_sae_signed_dose_scan/guest_launcher.py",
    "experiments/consciousness_sae_signed_dose_scan/incident_closure.py",
    "experiments/consciousness_sae_signed_dose_scan/orientation.py",
    "experiments/consciousness_sae_signed_dose_scan/protocol.py",
    "experiments/consciousness_sae_signed_dose_scan/recovery_equivalence.py",
    "experiments/consciousness_sae_signed_dose_scan/recovery_host_qualification.py",
    "experiments/consciousness_sae_signed_dose_scan/requirements-runpod-b200.txt",
    "experiments/consciousness_sae_signed_dose_scan/review_adjudication.py",
    "experiments/consciousness_sae_signed_dose_scan/runner.py",
    "experiments/consciousness_sae_signed_dose_scan/setup_runpod_guest.sh",
    "experiments/consciousness_sae_signed_dose_scan/validate_plan.py",
    "experiments/consciousness_sae_signed_dose_scan/verify_incident_closure.py",
    "experiments/consciousness_sae_signed_dose_scan/verify_recovery_equivalence.py",
    "experiments/consciousness_sae_signed_dose_scan/verify_recovery_host_qualification.py",
    "src/prompts.py",
    "tests/consciousness_sae_signed_dose_scan/__init__.py",
    "tests/consciousness_sae_signed_dose_scan/test_audit_recovery.py",
    "tests/consciousness_sae_signed_dose_scan/test_execution_chain.py",
    "tests/consciousness_sae_signed_dose_scan/test_gemma9b_validation.py",
    "tests/consciousness_sae_signed_dose_scan/test_incident_closure.py",
    "tests/consciousness_sae_signed_dose_scan/test_plan.py",
    "tests/consciousness_sae_signed_dose_scan/test_protocol.py",
    "tests/consciousness_sae_signed_dose_scan/test_recovery_equivalence.py",
    "tests/consciousness_sae_signed_dose_scan/test_recovery_host_qualification.py",
)
RECOVERY_RUNTIME_PATH = (
    "experiments/consciousness_sae_signed_dose_scan/audit_recovery.py"
)
REQUIRED_RUNTIME_SYMBOLS = (
    "normalize_j_map_keys",
    "load_j_checkpoint_superset",
    "zero_forward_guard",
    "execute_recovery",
)
SCIENTIFIC_AUDIT_FIELDS = (
    "schema_version",
    "status",
    "study_id",
    "protocol_version",
    "run_id",
    "plan_manifest_sha256",
    "raw_run_receipt_sha256",
    "recomputed_realization_row_count",
    "primary_actual_state_arc_row_count",
    "recomputed_readout_transport_row_count",
    "recomputed_linearity_row_count",
    "independent_plan_audit_receipt_sha256",
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
    "diagnostic_non_gate_dose_failure_count",
    "j_shadow_gate_failure_count",
    "diagnostic_non_gate_dose_j_shadow_failure_count",
    "linearity_failure_counts",
    "primary_actual_state_estimand",
    "primary_actual_state_arc_row_count",
    "primary_actual_state_arc_rows",
    "shared_zero_baseline",
    "by_dose",
    "linearity_rows",
    "readout_transport",
    "claim_policy",
    "adaptive_design_inputs",
    "analysis_data_inputs",
    "target_prompt_render_count",
    "target_feature_vector_count",
)
HEX40 = re.compile(r"[0-9a-f]{40}")
HEX64 = re.compile(r"[0-9a-f]{64}")


class RecoveryEquivalenceVerificationError(RuntimeError):
    """The recovery-equivalence packet failed independent verification."""


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


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _blob_oid(raw: bytes) -> str:
    return hashlib.sha1(
        f"blob {len(raw)}\0".encode("ascii") + raw,
        usedforsecurity=False,
    ).hexdigest()


def _git(repo_root: Path, *args: str) -> bytes:
    result = subprocess.run(
        ["git", *args], cwd=repo_root, check=False, capture_output=True
    )
    if result.returncode:
        raise RecoveryEquivalenceVerificationError(
            f"git {' '.join(args)} failed"
        )
    return result.stdout


def git_blob(repo_root: Path, commit: str, path: str) -> bytes:
    if Path(path).is_absolute() or ".." in Path(path).parts:
        raise RecoveryEquivalenceVerificationError("noncanonical Git path")
    return _git(repo_root, "show", f"{commit}:{path}")


BlobReader = Callable[[str, str], bytes]


def _load_canonical(path: Path, label: str) -> tuple[dict[str, Any], bytes]:
    try:
        details = path.lstat()
        raw = path.read_bytes()
        value = json.loads(raw)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise RecoveryEquivalenceVerificationError(f"{label} is unreadable") from exc
    if (
        not stat.S_ISREG(details.st_mode)
        or details.st_nlink != 1
        or not isinstance(value, dict)
        or raw != canonical_json_bytes(value) + b"\n"
    ):
        raise RecoveryEquivalenceVerificationError(
            f"{label} is not canonical single-link JSON"
        )
    return value, raw


def _self_hash(value: Mapping[str, Any], field: str, label: str) -> str:
    core = dict(value)
    supplied = core.pop(field, None)
    if (
        not isinstance(supplied, str)
        or HEX64.fullmatch(supplied) is None
        or supplied != canonical_sha256(core)
    ):
        raise RecoveryEquivalenceVerificationError(f"{label} self-hash differs")
    return supplied


def _record(raw: bytes, path: str) -> dict[str, Any]:
    return {
        "path": path,
        "bytes": len(raw),
        "sha256": _sha256(raw),
        "git_blob_oid": _blob_oid(raw),
    }


def _expected_compatibility() -> dict[str, Any]:
    projection = {
        "audit_fields": list(SCIENTIFIC_AUDIT_FIELDS),
        "summary_fields": list(SCIENTIFIC_SUMMARY_FIELDS),
    }
    return {
        "compatibility_change_count": 1,
        "compatibility_change": (
            "j_checkpoint_inventory_predicate_and_required_map_filter"
        ),
        "old_predicate": "available_layers == required_layers_45_through_78",
        "recovery_predicate": (
            "required_layers_45_through_78 subset_of available_layers"
        ),
        "pinned_available_layers": list(range(79)),
        "required_layers": list(range(45, 79)),
        "unused_extra_layers": list(range(45)),
        "filtered_layers_handed_to_frozen_auditor": list(range(45, 79)),
        "selected_map_object_contract": (
            "same_checkpoint_objects_no_numeric_transform"
        ),
        "missing_required_layer": "reject",
        "checkpoint_hash_revision_metadata": "unchanged",
        "frozen_audit_entrypoint": "audit.audit",
        "new_model_forwards": 0,
        "new_scientific_observations": 0,
        "scientific_field_projection": projection,
        "scientific_field_projection_sha256": canonical_sha256(projection),
        "scientific_field_projection_unchanged": True,
        "operational_only_deltas_outside_projection": [
            "fresh recovery authority and watchdog",
            "historical receipt validation at original completion time",
            "raw pre/post hash ledger",
            "recovery provenance enrichment",
            "fresh atomic compact publication",
        ],
    }


def _verify_original(
    packet: Mapping[str, Any], plan_audit_path: Path, reader: BlobReader
) -> None:
    expected_rows = [
        _record(reader(ORIGINAL_FREEZE_COMMIT, path), path)
        for path in ORIGINAL_PLAN_PATHS
    ]
    original = packet.get("original_freeze")
    if not isinstance(original, Mapping):
        raise RecoveryEquivalenceVerificationError("original freeze is absent")
    manifest = json.loads(
        reader(ORIGINAL_FREEZE_COMMIT, ORIGINAL_PLAN_PATHS[0])
    )
    source = json.loads(
        reader(ORIGINAL_FREEZE_COMMIT, ORIGINAL_PLAN_PATHS[-1])
    )
    manifest_hash = _self_hash(
        manifest, "plan_manifest_sha256", "frozen plan manifest"
    )
    source_rows = source.get("files")
    if (
        manifest_hash != ORIGINAL_PLAN_MANIFEST_RECEIPT
        or manifest.get("git_head_commit") != ORIGINAL_PLAN_SOURCE_COMMIT
        or not isinstance(source_rows, list)
        or len(source_rows) != 41
        or canonical_sha256(source_rows) != ORIGINAL_SOURCE_INVENTORY_RECEIPT
    ):
        raise RecoveryEquivalenceVerificationError("original plan differs")
    for row in source_rows:
        raw = reader(ORIGINAL_FREEZE_COMMIT, str(row.get("path")))
        if len(raw) != row.get("bytes") or _sha256(raw) != row.get("sha256"):
            raise RecoveryEquivalenceVerificationError("frozen source differs")
    plan_audit, plan_audit_raw = _load_canonical(
        plan_audit_path, "independent plan audit"
    )
    audit_receipt = _self_hash(plan_audit, "receipt_sha256", "plan audit")
    expected = {
        "freeze_commit": ORIGINAL_FREEZE_COMMIT,
        "plan_source_commit": ORIGINAL_PLAN_SOURCE_COMMIT,
        "plan_manifest_sha256": manifest_hash,
        "plan_fragments": expected_rows,
        "plan_fragments_sha256": canonical_sha256(expected_rows),
        "source_file_count": 41,
        "source_inventory": source_rows,
        "source_inventory_sha256": canonical_sha256(source_rows),
        "independent_plan_audit": {
            "bytes": len(plan_audit_raw),
            "file_sha256": _sha256(plan_audit_raw),
            "receipt_sha256": audit_receipt,
            "status": "pass_prospectively_frozen_exploratory_plan",
        },
    }
    if (
        audit_receipt != ORIGINAL_PLAN_AUDIT_RECEIPT
        or plan_audit.get("plan_manifest_sha256") != manifest_hash
        or plan_audit.get("source_inventory_sha256")
        != ORIGINAL_SOURCE_INVENTORY_RECEIPT
        or original != expected
    ):
        raise RecoveryEquivalenceVerificationError("original binding differs")


def _verify_closure(
    packet: Mapping[str, Any],
    *,
    repo_root: Path,
    reader: BlobReader,
    enforce_git: bool,
) -> str:
    closure = packet.get("recovery_closure")
    if not isinstance(closure, Mapping):
        raise RecoveryEquivalenceVerificationError("recovery closure is absent")
    commit = str(closure.get("code_freeze_commit", ""))
    if HEX40.fullmatch(commit) is None:
        raise RecoveryEquivalenceVerificationError("C is malformed")
    if enforce_git:
        if _git(repo_root, "rev-parse", f"{commit}^{{commit}}").decode().strip() != commit:
            raise RecoveryEquivalenceVerificationError("C does not resolve exactly")
        ancestry = subprocess.run(
            ["git", "merge-base", "--is-ancestor", ORIGINAL_FREEZE_COMMIT, commit],
            cwd=repo_root,
            check=False,
        )
        if ancestry.returncode:
            raise RecoveryEquivalenceVerificationError("C ancestry differs")
    rows = []
    for path in sorted(RECOVERY_CLOSURE_PATHS):
        raw = reader(commit, path)
        live = repo_root / path
        if not live.is_file() or live.is_symlink() or live.read_bytes() != raw:
            raise RecoveryEquivalenceVerificationError(
                f"live recovery closure differs: {path}"
            )
        rows.append(_record(raw, path))
    expected = {
        "code_freeze_commit": commit,
        "files": rows,
        "file_count": len(rows),
        "inventory_sha256": canonical_sha256(rows),
    }
    if closure != expected:
        raise RecoveryEquivalenceVerificationError("recovery closure differs")
    return commit


def _verify_runtime(packet: Mapping[str, Any], commit: str, reader: BlobReader) -> None:
    raw = reader(commit, RECOVERY_RUNTIME_PATH)
    source = raw.decode("utf-8")
    tree = ast.parse(source, filename=RECOVERY_RUNTIME_PATH)
    symbols = {
        node.name: node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
    }
    rows = []
    for name in REQUIRED_RUNTIME_SYMBOLS:
        node = symbols.get(name)
        if node is None:
            raise RecoveryEquivalenceVerificationError("runtime symbol is missing")
        text = ast.get_source_segment(source, node)
        if text is None:
            raise RecoveryEquivalenceVerificationError("runtime extraction failed")
        rows.append(
            {
                "symbol": name,
                "first_line": node.lineno,
                "last_line": node.end_lineno or node.lineno,
                "source_sha256": _sha256(text.encode()),
            }
        )
    expected = {
        "path": RECOVERY_RUNTIME_PATH,
        "file_sha256": _sha256(raw),
        "required_symbols": rows,
        "required_symbols_sha256": canonical_sha256(rows),
    }
    if packet.get("recovery_runtime_surface") != expected:
        raise RecoveryEquivalenceVerificationError("runtime surface differs")


def _verify_precedent(
    packet: Mapping[str, Any], reader: BlobReader, repo_root: Path
) -> None:
    resolved = _git(
        repo_root, "rev-parse", f"{PREDECESSOR_PRECEDENT_COMMIT}^{{commit}}"
    ).decode().strip()
    rows = []
    for path, expected_hash in sorted(PREDECESSOR_PRECEDENT_PATHS.items()):
        raw = reader(resolved, path)
        if _sha256(raw) != expected_hash:
            raise RecoveryEquivalenceVerificationError("precedent source differs")
        rows.append(
            {
                "path": path,
                "bytes": len(raw),
                "sha256": expected_hash,
                "git_blob_oid": _blob_oid(raw),
            }
        )
    expected = {
        "commit": resolved,
        "role": "completed_audit_only_recovery_precedent_not_scientific_input",
        "files": rows,
        "inventory_sha256": canonical_sha256(rows),
    }
    if packet.get("predecessor_recovery_precedent") != expected:
        raise RecoveryEquivalenceVerificationError("precedent binding differs")


def verify_packet(
    packet_path: Path,
    *,
    plan_audit_path: Path,
    repo_root: Path = REPO_ROOT,
    enforce_git: bool = True,
    blob_reader: BlobReader | None = None,
) -> dict[str, Any]:
    """Verify a canonical packet without loading any scientific outcome."""

    packet, packet_raw = _load_canonical(packet_path, "equivalence packet")
    packet_hash = _self_hash(packet, "packet_sha256", "equivalence packet")
    if blob_reader is None:
        reader = (
            (lambda commit, path: git_blob(repo_root, commit, path))
            if enforce_git
            else (lambda _commit, path: (repo_root / path).read_bytes())
        )
    else:
        reader = blob_reader
    identity = {
        "schema_version": 1,
        "packet_type": "signed_dose_outcome_blind_audit_recovery_equivalence",
        "status": "pass_source_design_and_compatibility_bound_no_outcomes_loaded",
        "study_id": "consciousness_sae_signed_dose_scan_v1",
        "protocol_version": "consciousness_sae_signed_dose_scan_v1.0.0",
        "outcome_input_paths": [],
        "raw_run_opened": False,
        "compact_result_opened": False,
        "model_forward_count": 0,
        "target_prompt_render_count": 0,
        "target_feature_vector_count": 0,
        "analysis_data_inputs": [],
    }
    if any(packet.get(key) != value for key, value in identity.items()):
        raise RecoveryEquivalenceVerificationError("packet identity/scope differs")
    expected_keys = {
        *identity,
        "scope",
        "original_freeze",
        "recovery_closure",
        "recovery_runtime_surface",
        "predecessor_recovery_precedent",
        "compatibility_proof",
        "packet_sha256",
    }
    if set(packet) != expected_keys:
        raise RecoveryEquivalenceVerificationError("packet schema differs")
    _verify_original(packet, plan_audit_path, reader)
    commit = _verify_closure(
        packet, repo_root=repo_root, reader=reader, enforce_git=enforce_git
    )
    _verify_runtime(packet, commit, reader)
    _verify_precedent(packet, reader, repo_root)
    if packet.get("compatibility_proof") != _expected_compatibility():
        raise RecoveryEquivalenceVerificationError("compatibility proof differs")
    core = {
        "schema_version": 1,
        "status": "pass_outcome_blind_recovery_equivalence_verified",
        "study_id": identity["study_id"],
        "protocol_version": identity["protocol_version"],
        "packet_path": packet_path.expanduser().absolute().as_posix(),
        "packet_file_sha256": _sha256(packet_raw),
        "packet_sha256": packet_hash,
        "code_freeze_commit": commit,
        "recovery_closure_inventory_sha256": packet["recovery_closure"][
            "inventory_sha256"
        ],
        "scientific_field_projection_sha256": packet["compatibility_proof"][
            "scientific_field_projection_sha256"
        ],
        "compatibility_change_count": 1,
        "model_forward_count": 0,
        "target_prompt_render_count": 0,
        "target_feature_vector_count": 0,
        "raw_run_opened": False,
        "compact_result_opened": False,
        "analysis_data_inputs": [],
    }
    return {**core, "receipt_sha256": canonical_sha256(core)}


def _write_exclusive(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--packet", type=Path, required=True)
    parser.add_argument("--plan-audit", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    receipt = verify_packet(args.packet, plan_audit_path=args.plan_audit)
    _write_exclusive(args.output, canonical_json_bytes(receipt) + b"\n")
    print(args.output, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

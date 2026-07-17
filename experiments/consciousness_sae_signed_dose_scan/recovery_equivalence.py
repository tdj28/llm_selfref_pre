#!/usr/bin/env python3
"""Build an outcome-blind scientific-equivalence packet for audit recovery.

The packet binds the original ``a084caa`` plan freeze and independent plan
audit, the exact original-to-C1-to-C2-to-C3 lineage and recovery source/test
closure at code-freeze commit C3, and the completed predecessor recovery
precedent.  It opens neither the signed-dose raw transaction nor any compact
scientific result.

The sole scientific compatibility delta admitted by this packet is mechanical:
the pinned public J checkpoint contains canonical source layers 0..78, while
the frozen study requires 45..78.  Recovery must reject a missing required map
and hand the unchanged auditor a filtered mapping containing exactly 45..78.
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
import sys
from pathlib import Path
from typing import Any, Callable, Mapping


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


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
C1_RECOVERY_FREEZE_COMMIT = "f1307fc56d9d8fbd0625bf30524e6eea16575326"
C2_RECOVERY_FREEZE_COMMIT = "79db4e7526948a3c826e3dc62adbf2895a5b5528"
C3_RECOVERY_FREEZE_COMMIT = "7223ec9f4fcdf1e413a7143f9aebe9ee45648e21"
E3_QUALIFICATION_FREEZE_COMMIT = "44d9e178567bbf31e524b79e4434474a4e5d888e"
RECOVERY_EQUIVALENCE_PROTOCOL_VERSION_V3 = (
    "consciousness_sae_signed_dose_scan_v1.audit_recovery_equivalence_v3"
)
RECOVERY_EQUIVALENCE_PROTOCOL_VERSION = (
    "consciousness_sae_signed_dose_scan_v1.audit_recovery_equivalence_v4"
)
C1_QUALIFICATION_INCIDENT_ROOT = (
    "docs/consciousness_sae_signed_dose_scan/"
    "audit_recovery_qualification_incident_f1307fc_69d9kxugxuf6up"
)
C1_QUALIFICATION_INCIDENT_FILENAMES = (
    "RECOVERY_EQUIVALENCE_PACKET.json",
    "RECOVERY_EQUIVALENCE_VERIFICATION.json",
    "ATTEMPT_STARTED.json",
    "QUALIFICATION_FAILED.json",
    "OWNERSHIP.json",
    "FROZEN_OWNERSHIP.json",
    "PRECREATE_INVENTORY.json",
    "POSTCREATE_INVENTORY.json",
    "STATUS_0001.json",
    "FROZEN_STATUS_0001.json",
    "READY.json",
    "TERMINATION_AUDIT.json",
    "FROZEN_TERMINATION.json",
    "POSTDELETE_INVENTORY.json",
    "INCIDENT_CAUSE.json",
    "INCIDENT_CLOSURE_SCHEMA.json",
    "INCIDENT_CLOSURE.json",
    "INCIDENT_CLOSURE_VERIFICATION.json",
)
V2_SUCCESSOR_DOC_PATHS = (
    "docs/consciousness_sae_signed_dose_scan/"
    "AUDIT_ONLY_RECOVERY_SUCCESSOR_AMENDMENT_20260717.md",
    "docs/consciousness_sae_signed_dose_scan/RECOVERY_CYCLE_LEDGER_V2.json",
    "docs/consciousness_sae_signed_dose_scan/RECOVERY_SUCCESSOR_REPRODUCTION.md",
)
C3_DOC_PATHS = (
    "docs/consciousness_sae_signed_dose_scan/"
    "AUDIT_ONLY_RECOVERY_C3_AMENDMENT_20260717.md",
    "docs/consciousness_sae_signed_dose_scan/RECOVERY_CYCLE_LEDGER_V3.json",
    "docs/consciousness_sae_signed_dose_scan/RECOVERY_C3_STATUS_MAP.json",
)
C3_QUALIFICATION_ROOT = (
    "docs/consciousness_sae_signed_dose_scan/audit_recovery_host_qualification_v3"
)
C3_QUALIFICATION_FILENAMES = (
    "ATTEMPT_STARTED.json",
    "QUALIFICATION_FROZEN_TERMINATION.json",
    "QUALIFICATION_POSTDELETE_INVENTORY.json",
    "QUALIFICATION_TERMINATION_AUDIT.json",
    "RECOVERY_EQUIVALENCE_PACKET.json",
    "RECOVERY_EQUIVALENCE_VERIFICATION.json",
    "TARGET_HOST_QUALIFICATION.json",
    "TARGET_HOST_QUALIFICATION_VERIFICATION.json",
)
C4_DOC_PATHS = (
    "docs/consciousness_sae_signed_dose_scan/"
    "AUDIT_ONLY_RECOVERY_C4_AMENDMENT_20260717.md",
    "docs/consciousness_sae_signed_dose_scan/RECOVERY_CYCLE_LEDGER_V4.json",
    "docs/consciousness_sae_signed_dose_scan/RECOVERY_C4_STATUS_MAP.json",
)
C4_LEDGER_PATH = C4_DOC_PATHS[1]
C4_STATUS_MAP_PATH = C4_DOC_PATHS[2]
C4_QUALIFICATION_ROOT = (
    "docs/consciousness_sae_signed_dose_scan/audit_recovery_host_qualification_v4"
)
C4_QUALIFICATION_FILENAMES = C3_QUALIFICATION_FILENAMES
C4_REVIEW_ROOT = "docs/consciousness_sae_signed_dose_scan/audit_recovery_pro_review_v3"
C4_REVIEW_FILENAMES = (
    "RECOVERY_PRO_REVIEW.md",
    "RECOVERY_PRO_REVIEW_ADJUDICATION.json",
    "RECOVERY_PRO_REVIEW_BRIEF.md",
    "RECOVERY_PRO_REVIEW_CONTEXT.md",
    "RECOVERY_PRO_REVIEW_MANIFEST.json",
    "RECOVERY_PRO_REVIEW_REQUEST.md",
    "RECOVERY_PRO_REVIEW_REQUEST_PAYLOAD.json",
    "RECOVERY_PRO_REVIEW_RESPONSE.json",
)
C2_QUALIFICATION_INCIDENT_ROOT = (
    "docs/consciousness_sae_signed_dose_scan/"
    "audit_recovery_qualification_incident_79db4e7_g2azyjkpm17f1s"
)
C2_QUALIFICATION_INCIDENT_FILENAMES = (
    "ATTEMPT_STARTED.json",
    "CACHE_PREFLIGHT.json",
    "FROZEN_OWNERSHIP.json",
    "FROZEN_STATUS_0001.json",
    "FROZEN_TERMINATION.json",
    "GUEST_PREFLIGHT.json",
    "INCIDENT_CAUSE.json",
    "INCIDENT_CLOSURE.json",
    "INCIDENT_CLOSURE_SCHEMA.json",
    "INCIDENT_CLOSURE_VERIFICATION.json",
    "INCIDENT_CLOSURE.md",
    "OWNERSHIP.json",
    "POSTCREATE_INVENTORY.json",
    "POSTDELETE_INVENTORY.json",
    "PRECREATE_INVENTORY.json",
    "QUALIFICATION_FAILED.json",
    "QUALIFICATION_STDERR.log",
    "READY.json",
    "RECOVERY_EQUIVALENCE_PACKET.json",
    "RECOVERY_EQUIVALENCE_VERIFICATION.json",
    "STATUS_0001.json",
    "TERMINATION_AUDIT.json",
)
ORIGINAL_TO_C1_NAME_STATUS = {
    path: "A"
    for path in (
        "docs/consciousness_sae_signed_dose_scan/AUDIT_ONLY_RECOVERY_AMENDMENT_20260717.md",
        "docs/consciousness_sae_signed_dose_scan/INCIDENT_CLOSURE.json",
        "docs/consciousness_sae_signed_dose_scan/INCIDENT_CLOSURE_SCHEMA.json",
        "docs/consciousness_sae_signed_dose_scan/INCIDENT_CLOSURE_VERIFICATION.json",
        "docs/consciousness_sae_signed_dose_scan/RECOVERY_CYCLE_LEDGER.json",
        "docs/consciousness_sae_signed_dose_scan/RECOVERY_REPRODUCTION.md",
        "experiments/consciousness_sae_signed_dose_scan/audit_recovery.py",
        "experiments/consciousness_sae_signed_dose_scan/incident_closure.py",
        "experiments/consciousness_sae_signed_dose_scan/recovery_equivalence.py",
        "experiments/consciousness_sae_signed_dose_scan/recovery_host_qualification.py",
        "experiments/consciousness_sae_signed_dose_scan/verify_incident_closure.py",
        "experiments/consciousness_sae_signed_dose_scan/verify_recovery_equivalence.py",
        "experiments/consciousness_sae_signed_dose_scan/verify_recovery_host_qualification.py",
        "tests/consciousness_sae_signed_dose_scan/test_audit_recovery.py",
        "tests/consciousness_sae_signed_dose_scan/test_incident_closure.py",
        "tests/consciousness_sae_signed_dose_scan/test_recovery_equivalence.py",
        "tests/consciousness_sae_signed_dose_scan/test_recovery_host_qualification.py",
    )
}
C1_TO_C2_NAME_STATUS = {
    **{
        path: "M"
        for path in (
            "experiments/consciousness_sae_signed_dose_scan/audit_recovery.py",
            "experiments/consciousness_sae_signed_dose_scan/recovery_equivalence.py",
            "experiments/consciousness_sae_signed_dose_scan/recovery_host_qualification.py",
            "experiments/consciousness_sae_signed_dose_scan/verify_recovery_equivalence.py",
            "experiments/consciousness_sae_signed_dose_scan/verify_recovery_host_qualification.py",
            "tests/consciousness_sae_signed_dose_scan/test_audit_recovery.py",
            "tests/consciousness_sae_signed_dose_scan/test_recovery_equivalence.py",
            "tests/consciousness_sae_signed_dose_scan/test_recovery_host_qualification.py",
        )
    },
    **{
        path: "A"
        for path in (
            *V2_SUCCESSOR_DOC_PATHS,
            *(
                f"{C1_QUALIFICATION_INCIDENT_ROOT}/{name}"
                for name in C1_QUALIFICATION_INCIDENT_FILENAMES
            ),
            "experiments/consciousness_sae_signed_dose_scan/qualification_incident.py",
            "experiments/consciousness_sae_signed_dose_scan/verify_qualification_incident.py",
            "tests/consciousness_sae_signed_dose_scan/test_qualification_incident.py",
        )
    },
}
C2_TO_C3_NAME_STATUS = {
    **{
        path: "M"
        for path in (
            "experiments/consciousness_sae_signed_dose_scan/audit_recovery.py",
            "experiments/consciousness_sae_signed_dose_scan/qualification_incident.py",
            "experiments/consciousness_sae_signed_dose_scan/recovery_equivalence.py",
            "experiments/consciousness_sae_signed_dose_scan/recovery_host_qualification.py",
            "experiments/consciousness_sae_signed_dose_scan/verify_qualification_incident.py",
            "experiments/consciousness_sae_signed_dose_scan/verify_recovery_equivalence.py",
            "experiments/consciousness_sae_signed_dose_scan/verify_recovery_host_qualification.py",
            "tests/consciousness_sae_signed_dose_scan/test_audit_recovery.py",
            "tests/consciousness_sae_signed_dose_scan/test_qualification_incident.py",
            "tests/consciousness_sae_signed_dose_scan/test_recovery_equivalence.py",
            "tests/consciousness_sae_signed_dose_scan/test_recovery_host_qualification.py",
        )
    },
    **{
        path: "A"
        for path in (
            *C3_DOC_PATHS,
            *(
                f"{C2_QUALIFICATION_INCIDENT_ROOT}/{name}"
                for name in C2_QUALIFICATION_INCIDENT_FILENAMES
            ),
        )
    },
}
C3_TO_E3_NAME_STATUS = {
    f"{C3_QUALIFICATION_ROOT}/{name}": "A" for name in C3_QUALIFICATION_FILENAMES
}
E3_TO_C4_NAME_STATUS = {
    **{
        path: "M"
        for path in (
            "experiments/consciousness_sae_signed_dose_scan/audit_recovery.py",
            "experiments/consciousness_sae_signed_dose_scan/qualification_incident.py",
            "experiments/consciousness_sae_signed_dose_scan/recovery_equivalence.py",
            "experiments/consciousness_sae_signed_dose_scan/recovery_host_qualification.py",
            "experiments/consciousness_sae_signed_dose_scan/verify_qualification_incident.py",
            "experiments/consciousness_sae_signed_dose_scan/verify_recovery_equivalence.py",
            "experiments/consciousness_sae_signed_dose_scan/verify_recovery_host_qualification.py",
            "tests/consciousness_sae_signed_dose_scan/test_audit_recovery.py",
            "tests/consciousness_sae_signed_dose_scan/test_qualification_incident.py",
            "tests/consciousness_sae_signed_dose_scan/test_recovery_equivalence.py",
            "tests/consciousness_sae_signed_dose_scan/test_recovery_host_qualification.py",
        )
    },
    **{path: "A" for path in C4_DOC_PATHS},
}
C4_TO_E4_NAME_STATUS = {
    f"{C4_QUALIFICATION_ROOT}/{name}": "A" for name in C4_QUALIFICATION_FILENAMES
}
E4_TO_F4_NAME_STATUS = {f"{C4_REVIEW_ROOT}/{name}": "A" for name in C4_REVIEW_FILENAMES}

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

RECOVERY_CLOSURE_PATHS_V3 = (
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
    *V2_SUCCESSOR_DOC_PATHS,
    *C3_DOC_PATHS,
    *(
        f"{C1_QUALIFICATION_INCIDENT_ROOT}/{name}"
        for name in C1_QUALIFICATION_INCIDENT_FILENAMES
    ),
    *(
        f"{C2_QUALIFICATION_INCIDENT_ROOT}/{name}"
        for name in C2_QUALIFICATION_INCIDENT_FILENAMES
    ),
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
    "experiments/consciousness_sae_signed_dose_scan/qualification_incident.py",
    "experiments/consciousness_sae_signed_dose_scan/recovery_equivalence.py",
    "experiments/consciousness_sae_signed_dose_scan/recovery_host_qualification.py",
    "experiments/consciousness_sae_signed_dose_scan/requirements-runpod-b200.txt",
    "experiments/consciousness_sae_signed_dose_scan/review_adjudication.py",
    "experiments/consciousness_sae_signed_dose_scan/runner.py",
    "experiments/consciousness_sae_signed_dose_scan/setup_runpod_guest.sh",
    "experiments/consciousness_sae_signed_dose_scan/validate_plan.py",
    "experiments/consciousness_sae_signed_dose_scan/verify_incident_closure.py",
    "experiments/consciousness_sae_signed_dose_scan/verify_qualification_incident.py",
    "experiments/consciousness_sae_signed_dose_scan/verify_recovery_equivalence.py",
    "experiments/consciousness_sae_signed_dose_scan/verify_recovery_host_qualification.py",
    "src/prompts.py",
    "tests/consciousness_sae_signed_dose_scan/__init__.py",
    "tests/consciousness_sae_signed_dose_scan/test_audit_recovery.py",
    "tests/consciousness_sae_signed_dose_scan/test_execution_chain.py",
    "tests/consciousness_sae_signed_dose_scan/test_gemma9b_validation.py",
    "tests/consciousness_sae_signed_dose_scan/test_incident_closure.py",
    "tests/consciousness_sae_signed_dose_scan/test_plan.py",
    "tests/consciousness_sae_signed_dose_scan/test_qualification_incident.py",
    "tests/consciousness_sae_signed_dose_scan/test_protocol.py",
    "tests/consciousness_sae_signed_dose_scan/test_recovery_equivalence.py",
    "tests/consciousness_sae_signed_dose_scan/test_recovery_host_qualification.py",
)
RECOVERY_CLOSURE_PATHS = (
    *RECOVERY_CLOSURE_PATHS_V3[
        : RECOVERY_CLOSURE_PATHS_V3.index(
            f"{C1_QUALIFICATION_INCIDENT_ROOT}/{C1_QUALIFICATION_INCIDENT_FILENAMES[0]}"
        )
    ],
    *C4_DOC_PATHS,
    *RECOVERY_CLOSURE_PATHS_V3[
        RECOVERY_CLOSURE_PATHS_V3.index(
            f"{C1_QUALIFICATION_INCIDENT_ROOT}/{C1_QUALIFICATION_INCIDENT_FILENAMES[0]}"
        ) :
    ],
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
PINNED_AVAILABLE_J_LAYERS = tuple(range(79))
REQUIRED_J_LAYERS = tuple(range(45, 79))

# Affirmative projection: recovery provenance may add fields outside this
# projection, but cannot remove, replace, or mutate one of these scientific
# fields without changing the packet and invalidating its independent verifier.
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

HEX40_RE = re.compile(r"[0-9a-f]{40}")
HEX64_RE = re.compile(r"[0-9a-f]{64}")


class RecoveryEquivalenceError(RuntimeError):
    """A frozen scientific-equivalence binding failed."""


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


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(8 * 1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _json_bytes(raw: bytes, label: str) -> dict[str, Any]:
    try:
        value = json.loads(raw)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise RecoveryEquivalenceError(f"{label} is not JSON") from exc
    if not isinstance(value, dict):
        raise RecoveryEquivalenceError(f"{label} is not a JSON object")
    return value


def _self_hash(value: Mapping[str, Any], field: str, label: str) -> str:
    core = dict(value)
    supplied = core.pop(field, None)
    if (
        not isinstance(supplied, str)
        or HEX64_RE.fullmatch(supplied) is None
        or supplied != canonical_sha256(core)
    ):
        raise RecoveryEquivalenceError(f"{label} self-hash differs")
    return supplied


def _git(*args: str, repo_root: Path = REPO_ROOT) -> bytes:
    completed = subprocess.run(
        ["git", *args],
        cwd=repo_root,
        check=False,
        capture_output=True,
    )
    if completed.returncode:
        raise RecoveryEquivalenceError(f"git {' '.join(args)} failed")
    return completed.stdout


def _status_rows(mapping: Mapping[str, str]) -> list[dict[str, str]]:
    return [{"path": path, "status": mapping[path]} for path in sorted(mapping)]


def _observed_name_status(
    parent: str, child: str, *, repo_root: Path
) -> dict[str, str]:
    raw = _git(
        "diff",
        "--name-status",
        "--no-renames",
        parent,
        child,
        repo_root=repo_root,
    ).decode("utf-8")
    observed: dict[str, str] = {}
    for line in raw.splitlines():
        fields = line.split("\t")
        if len(fields) != 2 or fields[0] not in {"A", "M", "D", "T"}:
            raise RecoveryEquivalenceError("freeze name-status record differs")
        status, path = fields
        candidate = Path(path)
        if candidate.is_absolute() or ".." in candidate.parts or path in observed:
            raise RecoveryEquivalenceError("freeze name-status path differs")
        observed[path] = status
    return observed


def _freeze_lineage_v3(
    code_freeze_commit: str,
    *,
    repo_root: Path,
    enforce_git: bool,
) -> dict[str, Any]:
    if enforce_git:
        for commit in (
            ORIGINAL_FREEZE_COMMIT,
            C1_RECOVERY_FREEZE_COMMIT,
            C2_RECOVERY_FREEZE_COMMIT,
            code_freeze_commit,
        ):
            if (
                _git("rev-parse", f"{commit}^{{commit}}", repo_root=repo_root)
                .decode()
                .strip()
                != commit
            ):
                raise RecoveryEquivalenceError("freeze commit does not resolve exactly")
        c1_lineage = (
            _git(
                "rev-list",
                "--parents",
                "-n",
                "1",
                C1_RECOVERY_FREEZE_COMMIT,
                repo_root=repo_root,
            )
            .decode()
            .split()
        )
        c2_lineage = (
            _git(
                "rev-list",
                "--parents",
                "-n",
                "1",
                C2_RECOVERY_FREEZE_COMMIT,
                repo_root=repo_root,
            )
            .decode()
            .split()
        )
        c3_lineage = (
            _git(
                "rev-list",
                "--parents",
                "-n",
                "1",
                code_freeze_commit,
                repo_root=repo_root,
            )
            .decode()
            .split()
        )
        if c1_lineage != [C1_RECOVERY_FREEZE_COMMIT, ORIGINAL_FREEZE_COMMIT]:
            raise RecoveryEquivalenceError("original-to-C1 direct parent differs")
        if c2_lineage != [C2_RECOVERY_FREEZE_COMMIT, C1_RECOVERY_FREEZE_COMMIT]:
            raise RecoveryEquivalenceError("C1-to-C2 direct parent differs")
        if c3_lineage != [code_freeze_commit, C2_RECOVERY_FREEZE_COMMIT]:
            raise RecoveryEquivalenceError("C2-to-C3 direct parent differs")
        if (
            _observed_name_status(
                ORIGINAL_FREEZE_COMMIT,
                C1_RECOVERY_FREEZE_COMMIT,
                repo_root=repo_root,
            )
            != ORIGINAL_TO_C1_NAME_STATUS
        ):
            raise RecoveryEquivalenceError("original-to-C1 name-status map differs")
        if (
            _observed_name_status(
                C1_RECOVERY_FREEZE_COMMIT,
                C2_RECOVERY_FREEZE_COMMIT,
                repo_root=repo_root,
            )
            != C1_TO_C2_NAME_STATUS
        ):
            raise RecoveryEquivalenceError("C1-to-C2 name-status map differs")
        if (
            _observed_name_status(
                C2_RECOVERY_FREEZE_COMMIT,
                code_freeze_commit,
                repo_root=repo_root,
            )
            != C2_TO_C3_NAME_STATUS
        ):
            raise RecoveryEquivalenceError("C2-to-C3 name-status map differs")
    original_rows = _status_rows(ORIGINAL_TO_C1_NAME_STATUS)
    c1_to_c2_rows = _status_rows(C1_TO_C2_NAME_STATUS)
    c2_to_c3_rows = _status_rows(C2_TO_C3_NAME_STATUS)
    return {
        "status": "pass_exact_original_C1_C2_C3_successor_lineage",
        "original_freeze_commit": ORIGINAL_FREEZE_COMMIT,
        "c1_recovery_freeze_commit": C1_RECOVERY_FREEZE_COMMIT,
        "c2_recovery_freeze_commit": C2_RECOVERY_FREEZE_COMMIT,
        "c3_code_freeze_commit": code_freeze_commit,
        "direct_parent_chain": [
            ORIGINAL_FREEZE_COMMIT,
            C1_RECOVERY_FREEZE_COMMIT,
            C2_RECOVERY_FREEZE_COMMIT,
            code_freeze_commit,
        ],
        "original_to_c1_name_status": original_rows,
        "original_to_c1_name_status_sha256": canonical_sha256(original_rows),
        "c1_to_c2_name_status": c1_to_c2_rows,
        "c1_to_c2_name_status_sha256": canonical_sha256(c1_to_c2_rows),
        "c2_to_c3_name_status": c2_to_c3_rows,
        "c2_to_c3_name_status_sha256": canonical_sha256(c2_to_c3_rows),
        "original_science_mutation_paths": [],
        "original_science_bytes_immutable": True,
    }


def _freeze_lineage(
    code_freeze_commit: str,
    *,
    repo_root: Path,
    enforce_git: bool,
) -> dict[str, Any]:
    """Bind the exact original→C1→C2→C3→E3→C4 code-freeze chain."""

    if enforce_git:
        commits = (
            ORIGINAL_FREEZE_COMMIT,
            C1_RECOVERY_FREEZE_COMMIT,
            C2_RECOVERY_FREEZE_COMMIT,
            C3_RECOVERY_FREEZE_COMMIT,
            E3_QUALIFICATION_FREEZE_COMMIT,
            code_freeze_commit,
        )
        for commit in commits:
            resolved = (
                _git("rev-parse", f"{commit}^{{commit}}", repo_root=repo_root)
                .decode()
                .strip()
            )
            if resolved != commit:
                raise RecoveryEquivalenceError("freeze commit does not resolve exactly")
        parent_pairs = (
            (ORIGINAL_FREEZE_COMMIT, C1_RECOVERY_FREEZE_COMMIT, "original-to-C1"),
            (C1_RECOVERY_FREEZE_COMMIT, C2_RECOVERY_FREEZE_COMMIT, "C1-to-C2"),
            (C2_RECOVERY_FREEZE_COMMIT, C3_RECOVERY_FREEZE_COMMIT, "C2-to-C3"),
            (C3_RECOVERY_FREEZE_COMMIT, E3_QUALIFICATION_FREEZE_COMMIT, "C3-to-E3"),
            (E3_QUALIFICATION_FREEZE_COMMIT, code_freeze_commit, "E3-to-C4"),
        )
        for parent, child, label in parent_pairs:
            lineage = (
                _git("rev-list", "--parents", "-n", "1", child, repo_root=repo_root)
                .decode()
                .split()
            )
            if lineage != [child, parent]:
                raise RecoveryEquivalenceError(f"{label} direct parent differs")
        status_pairs = (
            (
                ORIGINAL_FREEZE_COMMIT,
                C1_RECOVERY_FREEZE_COMMIT,
                ORIGINAL_TO_C1_NAME_STATUS,
                "original-to-C1",
            ),
            (
                C1_RECOVERY_FREEZE_COMMIT,
                C2_RECOVERY_FREEZE_COMMIT,
                C1_TO_C2_NAME_STATUS,
                "C1-to-C2",
            ),
            (
                C2_RECOVERY_FREEZE_COMMIT,
                C3_RECOVERY_FREEZE_COMMIT,
                C2_TO_C3_NAME_STATUS,
                "C2-to-C3",
            ),
            (
                C3_RECOVERY_FREEZE_COMMIT,
                E3_QUALIFICATION_FREEZE_COMMIT,
                C3_TO_E3_NAME_STATUS,
                "C3-to-E3",
            ),
            (
                E3_QUALIFICATION_FREEZE_COMMIT,
                code_freeze_commit,
                E3_TO_C4_NAME_STATUS,
                "E3-to-C4",
            ),
        )
        for parent, child, expected, label in status_pairs:
            if _observed_name_status(parent, child, repo_root=repo_root) != expected:
                raise RecoveryEquivalenceError(f"{label} name-status map differs")

    maps = {
        "original_to_c1": ORIGINAL_TO_C1_NAME_STATUS,
        "c1_to_c2": C1_TO_C2_NAME_STATUS,
        "c2_to_c3": C2_TO_C3_NAME_STATUS,
        "c3_to_e3": C3_TO_E3_NAME_STATUS,
        "e3_to_c4": E3_TO_C4_NAME_STATUS,
    }
    core: dict[str, Any] = {
        "status": "pass_exact_original_C1_C2_C3_E3_C4_successor_lineage",
        "original_freeze_commit": ORIGINAL_FREEZE_COMMIT,
        "c1_recovery_freeze_commit": C1_RECOVERY_FREEZE_COMMIT,
        "c2_recovery_freeze_commit": C2_RECOVERY_FREEZE_COMMIT,
        "c3_recovery_freeze_commit": C3_RECOVERY_FREEZE_COMMIT,
        "e3_qualification_freeze_commit": E3_QUALIFICATION_FREEZE_COMMIT,
        "c4_code_freeze_commit": code_freeze_commit,
        "direct_parent_chain": [
            ORIGINAL_FREEZE_COMMIT,
            C1_RECOVERY_FREEZE_COMMIT,
            C2_RECOVERY_FREEZE_COMMIT,
            C3_RECOVERY_FREEZE_COMMIT,
            E3_QUALIFICATION_FREEZE_COMMIT,
            code_freeze_commit,
        ],
    }
    for label, mapping in maps.items():
        rows = _status_rows(mapping)
        core[f"{label}_name_status"] = rows
        core[f"{label}_name_status_sha256"] = canonical_sha256(rows)
    return {
        **core,
        "original_science_mutation_paths": [],
        "original_science_bytes_immutable": True,
    }


def git_blob(commit: str, relative_path: str, *, repo_root: Path = REPO_ROOT) -> bytes:
    if ".." in Path(relative_path).parts or Path(relative_path).is_absolute():
        raise RecoveryEquivalenceError("Git-bound path is not canonical relative")
    return _git("show", f"{commit}:{relative_path}", repo_root=repo_root)


def _blob_oid(payload: bytes) -> str:
    return hashlib.sha1(
        f"blob {len(payload)}\0".encode("ascii") + payload,
        usedforsecurity=False,
    ).hexdigest()


BlobReader = Callable[[str, str], bytes]


def _surface_mapping(value: Mapping[str, Any], label: str) -> dict[str, str]:
    try:
        added = value["added"]
        modified = value["modified"]
        deleted = value["deleted"]
    except KeyError as exc:
        raise RecoveryEquivalenceError(f"{label} status surface is incomplete") from exc
    if not all(isinstance(rows, list) for rows in (added, modified, deleted)):
        raise RecoveryEquivalenceError(f"{label} status surface differs")
    paths = [*added, *modified, *deleted]
    if (
        any(not isinstance(path, str) for path in paths)
        or len(paths) != len(set(paths))
        or any(Path(path).is_absolute() or ".." in Path(path).parts for path in paths)
    ):
        raise RecoveryEquivalenceError(f"{label} status paths differ")
    return {
        **{path: "A" for path in added},
        **{path: "M" for path in modified},
        **{path: "D" for path in deleted},
    }


def _added_directory_mapping(value: Mapping[str, Any], label: str) -> dict[str, str]:
    root = value.get("added_directory")
    filenames = value.get("added_filenames")
    if (
        not isinstance(root, str)
        or not isinstance(filenames, list)
        or any(
            not isinstance(name, str) or Path(name).name != name for name in filenames
        )
        or len(filenames) != len(set(filenames))
    ):
        raise RecoveryEquivalenceError(f"{label} added-directory surface differs")
    return {f"{root}/{name}": "A" for name in filenames}


def _c4_authority_documents(
    code_freeze_commit: str, reader: BlobReader
) -> dict[str, Any]:
    """Validate the two self-hashed C4 authority documents at C4."""

    status_raw = reader(code_freeze_commit, C4_STATUS_MAP_PATH)
    ledger_raw = reader(code_freeze_commit, C4_LEDGER_PATH)
    status_map = _json_bytes(status_raw, "C4 status map")
    ledger = _json_bytes(ledger_raw, "C4 cycle ledger")
    status_receipt = _self_hash(status_map, "receipt_sha256", "C4 status map")
    ledger_receipt = _self_hash(ledger, "receipt_sha256", "C4 cycle ledger")

    if set(status_map) != {
        "base_commit",
        "c3_code_commit",
        "c3_to_e3",
        "e3_to_c4",
        "c4_to_e4",
        "e4_to_f4",
        "excluded_preexisting_user_paths",
        "receipt_kind",
        "receipt_sha256",
        "schema_version",
        "status",
        "study_id",
    }:
        raise RecoveryEquivalenceError("C4 status-map schema differs")
    if (
        status_map.get("schema_version") != 1
        or status_map.get("study_id") != "consciousness_sae_signed_dose_scan_v1"
        or status_map.get("receipt_kind")
        != "consciousness_sae_signed_dose_scan_c4_status_map_v1"
        or status_map.get("base_commit") != E3_QUALIFICATION_FREEZE_COMMIT
        or status_map.get("c3_code_commit") != C3_RECOVERY_FREEZE_COMMIT
    ):
        raise RecoveryEquivalenceError("C4 status-map identity differs")
    c3_to_e3 = status_map.get("c3_to_e3")
    e3_to_c4 = status_map.get("e3_to_c4")
    c4_to_e4 = status_map.get("c4_to_e4")
    e4_to_f4 = status_map.get("e4_to_f4")
    if not all(
        isinstance(value, Mapping) for value in (c3_to_e3, e3_to_c4, c4_to_e4, e4_to_f4)
    ):
        raise RecoveryEquivalenceError("C4 status-map edge is absent")
    if (
        _added_directory_mapping(c3_to_e3, "C3-to-E3") != C3_TO_E3_NAME_STATUS
        or c3_to_e3.get("required_direct_parent") != C3_RECOVERY_FREEZE_COMMIT
        or c3_to_e3.get("required_evidence_commit") != E3_QUALIFICATION_FREEZE_COMMIT
        or c3_to_e3.get("other_paths_forbidden") is not True
        or _surface_mapping(e3_to_c4, "E3-to-C4") != E3_TO_C4_NAME_STATUS
        or e3_to_c4.get("required_direct_parent") != E3_QUALIFICATION_FREEZE_COMMIT
        or e3_to_c4.get("parent_count") != 1
        or e3_to_c4.get("other_paths_forbidden") is not True
        or _added_directory_mapping(c4_to_e4, "C4-to-E4") != C4_TO_E4_NAME_STATUS
        or c4_to_e4.get("other_paths_forbidden") is not True
        or _added_directory_mapping(e4_to_f4, "E4-to-F4") != E4_TO_F4_NAME_STATUS
        or e4_to_f4.get("other_paths_forbidden") is not True
        or e4_to_f4.get("new_paid_review_call_forbidden") is not True
        or e4_to_f4.get("existing_paid_artifacts_are_immutable") is not True
        or e4_to_f4.get("review_input_anchor_commit") != E3_QUALIFICATION_FREEZE_COMMIT
    ):
        raise RecoveryEquivalenceError("C4 status-map edge contract differs")

    authority = ledger.get("successor_authority_binding")
    authority_hash = ledger.get("successor_authority_binding_sha256")
    if (
        not isinstance(authority, Mapping)
        or not isinstance(authority_hash, str)
        or authority_hash != canonical_sha256(authority)
    ):
        raise RecoveryEquivalenceError("C4 successor authority binding differs")
    status_file_hash = sha256_bytes(status_raw)
    required_authority = {
        "study_id": "consciousness_sae_signed_dose_scan_v1",
        "human_authorization_statement": "Authorize C4",
        "c3_code_commit": C3_RECOVERY_FREEZE_COMMIT,
        "c3_evidence_commit": E3_QUALIFICATION_FREEZE_COMMIT,
        "global_qualification_ordinal": 4,
        "qualification_attempt_number": 1,
        "qualification_protocol_version": (
            "consciousness_sae_signed_dose_scan_v1.audit_recovery_host_qualification_v4"
        ),
        "qualification_namespace": "audit_recovery_host_qualification_v4",
        "recovery_protocol_version": (
            "consciousness_sae_signed_dose_scan_v1.audit_only_recovery_v4"
        ),
        "recovery_namespace": "audit_only_recovery_v4",
        "review_namespace": "audit_recovery_pro_review_v3",
        "review_input_anchor_commit": E3_QUALIFICATION_FREEZE_COMMIT,
        "new_paid_review_call_count": 0,
        "no_automatic_retry": True,
        "no_model_forward": True,
        "qualification_and_review_raw_or_outcome_access": False,
        "status_map_file_sha256": status_file_hash,
        "status_map_receipt_sha256": status_receipt,
    }
    if any(authority.get(key) != value for key, value in required_authority.items()):
        raise RecoveryEquivalenceError("C4 successor authority semantics differ")
    if authority.get("rejected_pod_ids") != [
        "wl8obvtuq0ax8t",
        "69d9kxugxuf6up",
        "g2azyjkpm17f1s",
        "6am4twond0cd8v",
    ]:
        raise RecoveryEquivalenceError("C4 rejected-pod lineage differs")
    if (
        ledger.get("schema_version") != 1
        or ledger.get("study_id") != "consciousness_sae_signed_dose_scan_v1"
        or ledger.get("qualification_cycle_version")
        != "consciousness_sae_signed_dose_scan_v1.audit_only_recovery_cycle_v4"
        or ledger.get("qualification_protocol_version")
        != required_authority["qualification_protocol_version"]
        or ledger.get("recovery_protocol_version")
        != required_authority["recovery_protocol_version"]
    ):
        raise RecoveryEquivalenceError("C4 cycle-ledger identity differs")
    return {
        "ledger_path": C4_LEDGER_PATH,
        "ledger_file_sha256": sha256_bytes(ledger_raw),
        "ledger_receipt_sha256": ledger_receipt,
        "status_map_path": C4_STATUS_MAP_PATH,
        "status_map_file_sha256": status_file_hash,
        "status_map_receipt_sha256": status_receipt,
        "successor_authority_binding_sha256": authority_hash,
        "review_input_anchor_commit": E3_QUALIFICATION_FREEZE_COMMIT,
        "global_qualification_ordinal": 4,
        "new_paid_review_call_count": 0,
        "outcome_input_paths": [],
        "model_forward_count": 0,
    }


def verify_v4_final_freeze_lineage(
    *,
    code_freeze_commit: str,
    evidence_freeze_commit: str,
    final_freeze_commit: str,
    repo_root: Path = REPO_ROOT,
) -> dict[str, Any]:
    """Verify the dynamic C4→E4→F4 tail before recovery authority issues."""

    commits = (
        code_freeze_commit,
        evidence_freeze_commit,
        final_freeze_commit,
    )
    if any(HEX40_RE.fullmatch(commit) is None for commit in commits):
        raise RecoveryEquivalenceError("C4 final freeze commit is malformed")
    for commit in (*commits, E3_QUALIFICATION_FREEZE_COMMIT):
        resolved = (
            _git("rev-parse", f"{commit}^{{commit}}", repo_root=repo_root)
            .decode()
            .strip()
        )
        if resolved != commit:
            raise RecoveryEquivalenceError("C4 final freeze commit differs")
    edges = (
        (
            E3_QUALIFICATION_FREEZE_COMMIT,
            code_freeze_commit,
            E3_TO_C4_NAME_STATUS,
            "E3-to-C4",
        ),
        (
            code_freeze_commit,
            evidence_freeze_commit,
            C4_TO_E4_NAME_STATUS,
            "C4-to-E4",
        ),
        (
            evidence_freeze_commit,
            final_freeze_commit,
            E4_TO_F4_NAME_STATUS,
            "E4-to-F4",
        ),
    )
    for parent, child, expected, label in edges:
        lineage = (
            _git("rev-list", "--parents", "-n", "1", child, repo_root=repo_root)
            .decode()
            .split()
        )
        if lineage != [child, parent]:
            raise RecoveryEquivalenceError(f"{label} direct parent differs")
        if _observed_name_status(parent, child, repo_root=repo_root) != expected:
            raise RecoveryEquivalenceError(f"{label} name-status map differs")
    core = {
        "status": "pass_exact_C4_E4_F4_final_freeze_lineage",
        "direct_parent_chain": [
            E3_QUALIFICATION_FREEZE_COMMIT,
            code_freeze_commit,
            evidence_freeze_commit,
            final_freeze_commit,
        ],
        "e3_to_c4_name_status_sha256": canonical_sha256(
            _status_rows(E3_TO_C4_NAME_STATUS)
        ),
        "c4_to_e4_name_status_sha256": canonical_sha256(
            _status_rows(C4_TO_E4_NAME_STATUS)
        ),
        "e4_to_f4_name_status_sha256": canonical_sha256(
            _status_rows(E4_TO_F4_NAME_STATUS)
        ),
    }
    return {**core, "receipt_sha256": canonical_sha256(core)}


def _record(commit: str, path: str, reader: BlobReader) -> dict[str, Any]:
    raw = reader(commit, path)
    return {
        "path": path,
        "bytes": len(raw),
        "sha256": sha256_bytes(raw),
        "git_blob_oid": _blob_oid(raw),
    }


def _original_bindings(plan_audit_path: Path, reader: BlobReader) -> dict[str, Any]:
    records = [
        _record(ORIGINAL_FREEZE_COMMIT, path, reader) for path in ORIGINAL_PLAN_PATHS
    ]
    by_name = {Path(row["path"]).name: row for row in records}
    manifest = _json_bytes(
        reader(ORIGINAL_FREEZE_COMMIT, f"{ORIGINAL_PLAN_ROOT}/plan_manifest.json"),
        "original plan manifest",
    )
    manifest_hash = _self_hash(
        manifest, "plan_manifest_sha256", "original plan manifest"
    )
    if (
        manifest_hash != ORIGINAL_PLAN_MANIFEST_RECEIPT
        or manifest.get("git_head_commit") != ORIGINAL_PLAN_SOURCE_COMMIT
        or manifest.get("status") != "prospectively_frozen_exploratory_plan"
    ):
        raise RecoveryEquivalenceError("original plan identity differs")
    for row in manifest.get("files", []):
        observed = by_name.get(str(row.get("path")))
        if observed is None or (
            observed["bytes"] != row.get("bytes")
            or observed["sha256"] != row.get("sha256")
        ):
            raise RecoveryEquivalenceError("original plan fragment differs")

    source = _json_bytes(
        reader(ORIGINAL_FREEZE_COMMIT, f"{ORIGINAL_PLAN_ROOT}/source_files.json"),
        "original source inventory",
    )
    source_rows = source.get("files")
    if not isinstance(source_rows, list) or len(source_rows) != 41:
        raise RecoveryEquivalenceError("original source inventory differs")
    if canonical_sha256(source_rows) != ORIGINAL_SOURCE_INVENTORY_RECEIPT:
        raise RecoveryEquivalenceError("original source inventory hash differs")
    for row in source_rows:
        path = str(row.get("path"))
        raw = reader(ORIGINAL_FREEZE_COMMIT, path)
        if len(raw) != row.get("bytes") or sha256_bytes(raw) != row.get("sha256"):
            raise RecoveryEquivalenceError(f"original frozen source differs: {path}")

    try:
        details = plan_audit_path.lstat()
        raw_audit = plan_audit_path.read_bytes()
    except OSError as exc:
        raise RecoveryEquivalenceError(
            "original independent plan audit is missing"
        ) from exc
    if not stat.S_ISREG(details.st_mode) or details.st_nlink != 1:
        raise RecoveryEquivalenceError("original independent plan audit file differs")
    plan_audit = _json_bytes(raw_audit, "original independent plan audit")
    audit_hash = _self_hash(plan_audit, "receipt_sha256", "original plan audit")
    if (
        audit_hash != ORIGINAL_PLAN_AUDIT_RECEIPT
        or plan_audit.get("status") != "pass_prospectively_frozen_exploratory_plan"
        or plan_audit.get("plan_manifest_sha256") != manifest_hash
        or plan_audit.get("source_inventory_sha256")
        != ORIGINAL_SOURCE_INVENTORY_RECEIPT
        or plan_audit.get("source_file_count") != 41
    ):
        raise RecoveryEquivalenceError("original independent plan audit differs")
    return {
        "freeze_commit": ORIGINAL_FREEZE_COMMIT,
        "plan_source_commit": ORIGINAL_PLAN_SOURCE_COMMIT,
        "plan_manifest_sha256": manifest_hash,
        "plan_fragments": records,
        "plan_fragments_sha256": canonical_sha256(records),
        "source_file_count": len(source_rows),
        "source_inventory": source_rows,
        "source_inventory_sha256": canonical_sha256(source_rows),
        "independent_plan_audit": {
            "bytes": len(raw_audit),
            "file_sha256": sha256_bytes(raw_audit),
            "receipt_sha256": audit_hash,
            "status": plan_audit["status"],
        },
    }


def _recovery_closure(
    code_freeze_commit: str,
    reader: BlobReader,
    *,
    repo_root: Path,
    enforce_git: bool,
    closure_paths: tuple[str, ...] = RECOVERY_CLOSURE_PATHS,
) -> dict[str, Any]:
    if HEX40_RE.fullmatch(code_freeze_commit) is None:
        raise RecoveryEquivalenceError("code-freeze commit is malformed")
    if enforce_git:
        resolved = (
            _git("rev-parse", f"{code_freeze_commit}^{{commit}}", repo_root=repo_root)
            .decode()
            .strip()
        )
        if resolved != code_freeze_commit:
            raise RecoveryEquivalenceError(
                "code-freeze commit does not resolve exactly"
            )
        ancestry = subprocess.run(
            [
                "git",
                "merge-base",
                "--is-ancestor",
                ORIGINAL_FREEZE_COMMIT,
                code_freeze_commit,
            ],
            cwd=repo_root,
            check=False,
        )
        if ancestry.returncode:
            raise RecoveryEquivalenceError("original freeze is not an ancestor of C")
    rows = []
    for path in sorted(closure_paths):
        row = _record(code_freeze_commit, path, reader)
        live_path = repo_root / path
        try:
            details = live_path.lstat()
            live = live_path.read_bytes()
        except OSError as exc:
            raise RecoveryEquivalenceError(
                f"recovery closure file is missing: {path}"
            ) from exc
        if (
            not stat.S_ISREG(details.st_mode)
            or details.st_nlink != 1
            or live != reader(code_freeze_commit, path)
        ):
            raise RecoveryEquivalenceError(
                f"recovery closure live bytes differ: {path}"
            )
        rows.append(row)
    return {
        "code_freeze_commit": code_freeze_commit,
        "files": rows,
        "file_count": len(rows),
        "inventory_sha256": canonical_sha256(rows),
    }


def _runtime_surface(code_freeze_commit: str, reader: BlobReader) -> dict[str, Any]:
    raw = reader(code_freeze_commit, RECOVERY_RUNTIME_PATH)
    source = raw.decode("utf-8")
    tree = ast.parse(source, filename=RECOVERY_RUNTIME_PATH)
    symbols = {
        node.name: node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
    }
    missing = sorted(set(REQUIRED_RUNTIME_SYMBOLS) - set(symbols))
    if missing:
        raise RecoveryEquivalenceError(
            f"recovery runtime symbols are missing: {missing}"
        )
    symbol_rows = []
    for name in REQUIRED_RUNTIME_SYMBOLS:
        node = symbols[name]
        text = ast.get_source_segment(source, node)
        if text is None:
            raise RecoveryEquivalenceError(f"cannot extract recovery symbol: {name}")
        symbol_rows.append(
            {
                "symbol": name,
                "first_line": int(node.lineno),
                "last_line": int(node.end_lineno or node.lineno),
                "source_sha256": sha256_bytes(text.encode()),
            }
        )
    return {
        "path": RECOVERY_RUNTIME_PATH,
        "file_sha256": sha256_bytes(raw),
        "required_symbols": symbol_rows,
        "required_symbols_sha256": canonical_sha256(symbol_rows),
    }


def _precedent(reader: BlobReader) -> dict[str, Any]:
    resolved = (
        _git("rev-parse", f"{PREDECESSOR_PRECEDENT_COMMIT}^{{commit}}").decode().strip()
    )
    rows = []
    for path, expected_hash in sorted(PREDECESSOR_PRECEDENT_PATHS.items()):
        raw = reader(resolved, path)
        if sha256_bytes(raw) != expected_hash:
            raise RecoveryEquivalenceError(
                f"predecessor recovery precedent differs: {path}"
            )
        rows.append(
            {
                "path": path,
                "bytes": len(raw),
                "sha256": expected_hash,
                "git_blob_oid": _blob_oid(raw),
            }
        )
    return {
        "commit": resolved,
        "role": "completed_audit_only_recovery_precedent_not_scientific_input",
        "files": rows,
        "inventory_sha256": canonical_sha256(rows),
    }


def scientific_projection(
    audit_receipt: Mapping[str, Any], summary: Mapping[str, Any]
) -> dict[str, Any]:
    missing_audit = sorted(set(SCIENTIFIC_AUDIT_FIELDS) - set(audit_receipt))
    missing_summary = sorted(set(SCIENTIFIC_SUMMARY_FIELDS) - set(summary))
    if missing_audit or missing_summary:
        raise RecoveryEquivalenceError(
            f"scientific projection fields are missing: {missing_audit}/{missing_summary}"
        )
    return {
        "audit": {field: audit_receipt[field] for field in SCIENTIFIC_AUDIT_FIELDS},
        "summary": {field: summary[field] for field in SCIENTIFIC_SUMMARY_FIELDS},
    }


def _compatibility_proof() -> dict[str, Any]:
    if not set(REQUIRED_J_LAYERS) < set(PINNED_AVAILABLE_J_LAYERS):
        raise RecoveryEquivalenceError("required J layers are not a strict subset")
    filtered = [
        layer for layer in PINNED_AVAILABLE_J_LAYERS if layer in REQUIRED_J_LAYERS
    ]
    if tuple(filtered) != REQUIRED_J_LAYERS:
        raise RecoveryEquivalenceError(
            "J-layer filter does not preserve required order"
        )
    projection = {
        "audit_fields": list(SCIENTIFIC_AUDIT_FIELDS),
        "summary_fields": list(SCIENTIFIC_SUMMARY_FIELDS),
    }
    return {
        "compatibility_change_count": 1,
        "compatibility_change": "j_checkpoint_inventory_predicate_and_required_map_filter",
        "old_predicate": "available_layers == required_layers_45_through_78",
        "recovery_predicate": "required_layers_45_through_78 subset_of available_layers",
        "pinned_available_layers": list(PINNED_AVAILABLE_J_LAYERS),
        "required_layers": list(REQUIRED_J_LAYERS),
        "unused_extra_layers": list(range(45)),
        "filtered_layers_handed_to_frozen_auditor": filtered,
        "selected_map_object_contract": "same_checkpoint_objects_no_numeric_transform",
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
            "pinned FP16 J source validation with the unchanged frozen BF16 computation cast",
            "exact read-only /proc/self/maps qualification allowance",
            "historical receipt validation at original completion time",
            "raw pre/post hash ledger",
            "recovery provenance enrichment",
            "fresh atomic compact publication",
        ],
    }


def build_packet(
    *,
    plan_audit_path: Path,
    code_freeze_commit: str,
    repo_root: Path = REPO_ROOT,
    enforce_git: bool = True,
    blob_reader: BlobReader | None = None,
    equivalence_protocol_version: str = RECOVERY_EQUIVALENCE_PROTOCOL_VERSION,
) -> dict[str, Any]:
    if blob_reader is None:
        if enforce_git:

            def reader(commit: str, path: str) -> bytes:
                return git_blob(commit, path, repo_root=repo_root)
        else:

            def reader(_commit: str, path: str) -> bytes:
                return (repo_root / path).read_bytes()
    else:
        reader = blob_reader
    original = _original_bindings(plan_audit_path, reader)
    if equivalence_protocol_version not in {
        RECOVERY_EQUIVALENCE_PROTOCOL_VERSION_V3,
        RECOVERY_EQUIVALENCE_PROTOCOL_VERSION,
    }:
        raise RecoveryEquivalenceError("recovery-equivalence protocol version differs")
    is_v4 = equivalence_protocol_version == RECOVERY_EQUIVALENCE_PROTOCOL_VERSION
    freeze_lineage = (
        _freeze_lineage(
            code_freeze_commit,
            repo_root=repo_root,
            enforce_git=enforce_git,
        )
        if is_v4
        else _freeze_lineage_v3(
            code_freeze_commit,
            repo_root=repo_root,
            enforce_git=enforce_git,
        )
    )
    closure = _recovery_closure(
        code_freeze_commit,
        reader,
        repo_root=repo_root,
        enforce_git=enforce_git,
        closure_paths=(RECOVERY_CLOSURE_PATHS if is_v4 else RECOVERY_CLOSURE_PATHS_V3),
    )
    core = {
        "schema_version": 1,
        "packet_type": (
            "signed_dose_outcome_blind_audit_recovery_equivalence_v4"
            if is_v4
            else "signed_dose_outcome_blind_audit_recovery_equivalence_v3"
        ),
        "status": "pass_source_design_and_compatibility_bound_no_outcomes_loaded",
        "study_id": "consciousness_sae_signed_dose_scan_v1",
        "protocol_version": "consciousness_sae_signed_dose_scan_v1.0.0",
        "recovery_equivalence_protocol_version": equivalence_protocol_version,
        "outcome_input_paths": [],
        "raw_run_opened": False,
        "compact_result_opened": False,
        "model_forward_count": 0,
        "target_prompt_render_count": 0,
        "target_feature_vector_count": 0,
        "analysis_data_inputs": [],
        "scope": (
            "audit-only compatibility recovery; no new observation, result, "
            "threshold, estimand, or scientific-field change"
        ),
        "original_freeze": original,
        "freeze_lineage": freeze_lineage,
        "recovery_closure": closure,
        "recovery_runtime_surface": _runtime_surface(code_freeze_commit, reader),
        "predecessor_recovery_precedent": _precedent(reader),
        "compatibility_proof": _compatibility_proof(),
    }
    if is_v4:
        core["c4_authority_documents"] = _c4_authority_documents(
            code_freeze_commit, reader
        )
    return {**core, "packet_sha256": canonical_sha256(core)}


def _write_exclusive(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan-audit", type=Path, required=True)
    parser.add_argument("--code-freeze-commit", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    packet = build_packet(
        plan_audit_path=args.plan_audit,
        code_freeze_commit=args.code_freeze_commit,
    )
    _write_exclusive(args.output, canonical_json_bytes(packet) + b"\n")
    print(args.output, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

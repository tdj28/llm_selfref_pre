#!/usr/bin/env python3
"""Audit-only recovery for the completed signed-dose transaction.

The model transaction is immutable.  This runtime replays the independent
auditor on a fresh, separately authorized host after correcting one mechanical
checkpoint-reader assumption: the pinned public J-lens contains a canonical
superset of maps, while this study consumes only layers 45 through 78.

No model may be loaded or called.  The original campaign timestamps remain
historical evidence; a fresh recovery clock governs this process.  The raw tree
is fully rehashed before and after replay, and recovered compact outputs are
published as one fresh atomic directory transaction with explicit provenance.
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import importlib.util
import json
import math
import os
import re
import stat
import subprocess
import sys
import time
import uuid
from pathlib import Path, PurePosixPath
from types import ModuleType
from typing import Any, Iterator, Mapping, Sequence

from experiments.consciousness_sae_realization_validation import runpod_preflight
from experiments.consciousness_sae_signed_dose_scan import (
    audit as frozen_audit,
    protocol,
    verify_incident_closure,
    verify_qualification_incident,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
RECOVERY_PROTOCOL_VERSION = (
    "consciousness_sae_signed_dose_scan_v1.audit_only_recovery_v4"
)
HEX40 = re.compile(r"[0-9a-f]{40}")
HEX64 = re.compile(r"[0-9a-f]{64}")
SAFE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")
REQUIRED_J_LAYERS = tuple(range(45, 79))
ORIGINAL_PLAN_ADJUDICATION_PATH = (
    "docs/consciousness_sae_signed_dose_scan/PRO_REVIEW_ADJUDICATION.json"
)
RECOVERY_CYCLE_DEADLINE_AT_UNIX = 1_784_311_200.0  # 2026-07-17T18:00:00Z
RECOVERY_MAX_SECONDS = 3_600
RECOVERY_MAX_SPEND_USD = 6.0
ORIGINAL_FREEZE_COMMIT = "a084caafc2ec27860044d80d3b33912f656fd08a"
C1_RECOVERY_FREEZE_COMMIT = "f1307fc56d9d8fbd0625bf30524e6eea16575326"
C2_RECOVERY_FREEZE_COMMIT = "79db4e7526948a3c826e3dc62adbf2895a5b5528"
C3_RECOVERY_FREEZE_COMMIT = "7223ec9f4fcdf1e413a7143f9aebe9ee45648e21"
E3_QUALIFICATION_FREEZE_COMMIT = "44d9e178567bbf31e524b79e4434474a4e5d888e"
PUBLIC_J_CHECKPOINT_BYTES = 10_603_226_027
PUBLIC_J_SOURCE_DTYPE = "torch.float16"
PUBLIC_J_SOURCE_SHAPE = (8192, 8192)
REJECTED_PREDECESSOR_POD_IDS = frozenset(
    {
        "wl8obvtuq0ax8t",
        "69d9kxugxuf6up",
        "g2azyjkpm17f1s",
        "6am4twond0cd8v",
    }
)
EXPECTED_SUCCESSOR_AUTHORITY_BINDING_SHA256 = (
    "adc2c34302af92ec8da6b40d5a8c3745e9ced1be93f3fbaae31b691afabc20b8"
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
C4_DOC_PATHS = (
    "docs/consciousness_sae_signed_dose_scan/"
    "AUDIT_ONLY_RECOVERY_C4_AMENDMENT_20260717.md",
    "docs/consciousness_sae_signed_dose_scan/RECOVERY_CYCLE_LEDGER_V4.json",
    "docs/consciousness_sae_signed_dose_scan/RECOVERY_C4_STATUS_MAP.json",
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
QUALIFICATION_INCIDENT_ROOT = (
    "docs/consciousness_sae_signed_dose_scan/"
    "audit_recovery_host_qualification_v3"
)
QUALIFICATION_INCIDENT_FILENAMES = C2_QUALIFICATION_INCIDENT_FILENAMES
MANDATORY_C_SOURCE_TEST_INCIDENT_PATHS = (
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
    *C4_DOC_PATHS,
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
MANDATORY_E_QUALIFICATION_FILENAMES = frozenset(
    {
        "RECOVERY_EQUIVALENCE_PACKET.json",
        "RECOVERY_EQUIVALENCE_VERIFICATION.json",
        "ATTEMPT_STARTED.json",
        "TARGET_HOST_QUALIFICATION.json",
        "TARGET_HOST_QUALIFICATION_VERIFICATION.json",
        "QUALIFICATION_TERMINATION_AUDIT.json",
        "QUALIFICATION_FROZEN_TERMINATION.json",
        "QUALIFICATION_POSTDELETE_INVENTORY.json",
    }
)
ORIGINAL_TO_C1_NAME_STATUS = {
    path: "A"
    for path in {
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
    }
}
C1_TO_C2_NAME_STATUS = {
    **{
        path: "M"
        for path in {
            "experiments/consciousness_sae_signed_dose_scan/audit_recovery.py",
            "experiments/consciousness_sae_signed_dose_scan/recovery_equivalence.py",
            "experiments/consciousness_sae_signed_dose_scan/recovery_host_qualification.py",
            "experiments/consciousness_sae_signed_dose_scan/verify_recovery_equivalence.py",
            "experiments/consciousness_sae_signed_dose_scan/verify_recovery_host_qualification.py",
            "tests/consciousness_sae_signed_dose_scan/test_audit_recovery.py",
            "tests/consciousness_sae_signed_dose_scan/test_recovery_equivalence.py",
            "tests/consciousness_sae_signed_dose_scan/test_recovery_host_qualification.py",
        }
    },
    **{
        path: "A"
        for path in {
            *V2_SUCCESSOR_DOC_PATHS,
            *(
                f"{C1_QUALIFICATION_INCIDENT_ROOT}/{name}"
                for name in C1_QUALIFICATION_INCIDENT_FILENAMES
            ),
            "experiments/consciousness_sae_signed_dose_scan/qualification_incident.py",
            "experiments/consciousness_sae_signed_dose_scan/verify_qualification_incident.py",
            "tests/consciousness_sae_signed_dose_scan/test_qualification_incident.py",
        }
    },
}
C2_TO_C3_NAME_STATUS = {
    **{
        path: "M"
        for path in {
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
        }
    },
    **{
        path: "A"
        for path in {
            *C3_DOC_PATHS,
            *(
                f"{C2_QUALIFICATION_INCIDENT_ROOT}/{name}"
                for name in C2_QUALIFICATION_INCIDENT_FILENAMES
            ),
        }
    },
}
C3_QUALIFICATION_DIRECTORY = (
    "docs/consciousness_sae_signed_dose_scan/"
    "audit_recovery_host_qualification_v3"
)
C3_TO_E3_NAME_STATUS = {
    f"{C3_QUALIFICATION_DIRECTORY}/{name}": "A"
    for name in MANDATORY_E_QUALIFICATION_FILENAMES
}
E3_TO_C4_NAME_STATUS = {
    **{
        path: "M"
        for path in {
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
        }
    },
    **{path: "A" for path in C4_DOC_PATHS},
}
QUALIFICATION_DIRECTORY = (
    "docs/consciousness_sae_signed_dose_scan/"
    "audit_recovery_host_qualification_v4"
)
MANDATORY_E_QUALIFICATION_PATHS = frozenset(
    f"{QUALIFICATION_DIRECTORY}/{name}"
    for name in MANDATORY_E_QUALIFICATION_FILENAMES
)
RECOVERY_REVIEW_ROOT = (
    "docs/consciousness_sae_signed_dose_scan/audit_recovery_pro_review_v3"
)
MANDATORY_F_ADDITION_FILENAMES = frozenset(
    {
        "RECOVERY_PRO_REVIEW_BRIEF.md",
        "RECOVERY_PRO_REVIEW_CONTEXT.md",
        "RECOVERY_PRO_REVIEW_REQUEST.md",
        "RECOVERY_PRO_REVIEW_REQUEST_PAYLOAD.json",
        "RECOVERY_PRO_REVIEW_RESPONSE.json",
        "RECOVERY_PRO_REVIEW.md",
        "RECOVERY_PRO_REVIEW_MANIFEST.json",
        "RECOVERY_PRO_REVIEW_ADJUDICATION.json",
    }
)
MANDATORY_F_ADDITION_PATHS = frozenset(
    f"{RECOVERY_REVIEW_ROOT}/{name}"
    for name in MANDATORY_F_ADDITION_FILENAMES
)
MANDATORY_CUMULATIVE_REVIEW_PATHS = frozenset(
    {ORIGINAL_PLAN_ADJUDICATION_PATH, *MANDATORY_F_ADDITION_PATHS}
)
RECOVERY_ADJUDICATION_PATH = (
    f"{RECOVERY_REVIEW_ROOT}/RECOVERY_PRO_REVIEW_ADJUDICATION.json"
)
EXPECTED_ORIGINAL_ADJUDICATION_FILE_SHA256 = (
    "732f32e17c8df49062d87fbcfb8e4493d576f6ba71643ce8b724ac02dfc7a53d"
)
EXPECTED_ORIGINAL_ADJUDICATION_RECEIPT_SHA256 = (
    "234254e67f8b897ea837590117932e4bfdfc261df7fc4eb460acf7047edba0d8"
)
EXPECTED_REVIEW_INSTRUCTIONS_SHA256 = (
    "bfe68700d789a83062af44eecd4e1a9f6d45cad156132ed97c4716d77d5bfb4c"
)
RECOVERY_REVIEW_MAX_OUTPUT_TOKENS = 4_000
RECOVERY_REVIEW_REASONING_EFFORT = "high"
RECOVERY_REVIEW_VERDICTS = frozenset(
    {"READY TO FREEZE", "READY AFTER SPECIFIED FIXES", "NOT READY TO FREEZE"}
)
EXPECTED_INCIDENT_CLOSURE_FILE_SHA256 = (
    "7afe9aa8bae10c2965f40eab92fbbb331a51ad0fd2a0895d6fc55bd0af7cbd3c"
)
EXPECTED_INCIDENT_CLOSURE_RECEIPT_SHA256 = (
    "172ebb2e4ea06160df7d3a3d9e356dfdc0996ffb50019c6bc35a48a724103dd4"
)
EXPECTED_INCIDENT_VERIFICATION_FILE_SHA256 = (
    "b96a032bbedd3b8b3e3f7e21317e2c642a3d63a598c54c1d398f5a645a1deaa3"
)
EXPECTED_INCIDENT_VERIFICATION_RECEIPT_SHA256 = (
    "92c969a06bbd0c776e2f0f31357e04cca749c8244a25e3f4bc871cfd8ff3c2d8"
)
EXPECTED_CYCLE_LEDGER_FILE_SHA256 = (
    "b7921997024ef9d23bc2c5ae6ecbb21bf013a935313d8247868b709bbbfb5cb5"
)
EXPECTED_CYCLE_LEDGER_RECEIPT_SHA256 = (
    "72f2d473c68698a24160523265a9786b9382a14432e418d24a2f6596f910314b"
)
EXPECTED_RAW_RECORDS_SHA256 = (
    "b5c784f4feb87ba01a9fc5d9b2f22d12eee01930d98718cd5c54e3d398692cf4"
)
EXPECTED_RUN_COMPLETE_FILE_SHA256 = (
    "a5818ad5e208c9008df6ad0bede630fddafb06e07b5f0190d02b3b80ceefeb4b"
)
EXPECTED_RUN_COMPLETE_RECEIPT_SHA256 = (
    "f714f16e2f6d5bb532d522c3ad0e2985e6f6b169ff5875911d296f42cd8fdc7d"
)
EXPECTED_TERMINATION_FILE_SHA256 = (
    "3180a922744937adac0641dfc8e6f27db3b813e0c58cc43da7d693b9eab3ea67"
)
EXPECTED_TERMINATION_RECEIPT_SHA256 = (
    "4147d073fb7d1debdd182e13f72be4610ed25cb1e783a3215ae7f66ed16faa04"
)
EXPECTED_POSTDELETE_FILE_SHA256 = (
    "2264249e9dfce51d6a78c4386a4d1dff6d64a7a4e00ed4bf664a87a70d92225c"
)
EXPECTED_POSTDELETE_RECEIPT_SHA256 = (
    "6022801ebd4c23fd0da32ccbc21ce4ff065b0935b99a77db2a1df0bc5c7fb47c"
)
EXPECTED_EMPTY_POD_INVENTORY_SHA256 = (
    "4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945"
)
ZERO_GUARD_COUNTS = {
    "torch_module_calls": 0,
    "transformers_model_load_calls": 0,
    "direct_forward_attribute_access": 0,
    "model_construction_calls": 0,
    "model_state_load_calls": 0,
}
QUALIFICATION_MAX_SECONDS = 30 * 60
QUALIFICATION_MAX_SPEND_USD = 3.0
PROVIDER_LIFECYCLE_MAX_SPEND_USD = 36.0
RECOVERY_AUTHORIZATION_FIELDS = frozenset(
    {
        "schema_version",
        "status",
        "study_id",
        "protocol_version",
        "recovery_protocol_version",
        "recovery_id",
        "attempt_id",
        "authorized_at_unix",
        "recovery_started_at_unix",
        "recovery_deadline_at_unix",
        "hourly_price_usd",
        "max_spend_usd",
        "code_freeze_commit",
        "evidence_freeze_commit",
        "final_freeze_commit",
        "git_remote_ref",
        "git_live_remote_commit",
        "source_test_files",
        "source_test_inventory_sha256",
        "qualification_files",
        "qualification_inventory_sha256",
        "qualification_validation",
        "cumulative_review_files",
        "cumulative_review_inventory_sha256",
        "recovery_adjudication",
        "fresh_pod",
        "incident",
        "execution",
        "receipt_sha256",
    }
)


class AuditRecoveryError(RuntimeError):
    """A recovery precondition or audit-only invariant failed."""


def _canonical_file(path: Path, label: str) -> tuple[dict[str, Any], str]:
    candidate = path.expanduser().absolute()
    try:
        details = candidate.lstat()
        raw = candidate.read_bytes()
        value = json.loads(raw)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise AuditRecoveryError(f"{label} is not readable JSON") from exc
    if (
        not stat.S_ISREG(details.st_mode)
        or details.st_nlink != 1
        or not isinstance(value, dict)
        or raw != protocol.canonical_json_bytes(value) + b"\n"
    ):
        raise AuditRecoveryError(f"{label} is not canonical single-link JSON")
    return value, protocol.sha256_file(candidate)


def _self_hash(value: Mapping[str, Any], label: str) -> str:
    core = dict(value)
    supplied = core.pop("receipt_sha256", None)
    if (
        not isinstance(supplied, str)
        or HEX64.fullmatch(supplied) is None
        or supplied != protocol.canonical_sha256(core)
    ):
        raise AuditRecoveryError(f"{label} self-hash differs")
    return supplied


def _safe_relative(value: Any, label: str) -> str:
    text = str(value)
    path = PurePosixPath(text)
    if (
        not text
        or path.is_absolute()
        or ".." in path.parts
        or path.as_posix() != text
    ):
        raise AuditRecoveryError(f"{label} is not a canonical relative path")
    return text


def _git(repo_root: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        ["git", *args],
        cwd=repo_root,
        check=False,
        capture_output=True,
        text=True,
    )
    if check and completed.returncode:
        raise AuditRecoveryError(f"git {' '.join(args)} failed")
    return completed


def _require_ancestry(repo_root: Path, ancestor: str, descendant: str) -> None:
    completed = _git(
        repo_root, "merge-base", "--is-ancestor", ancestor, descendant, check=False
    )
    if completed.returncode != 0:
        raise AuditRecoveryError(
            f"freeze ancestry differs: {ancestor} is not an ancestor of {descendant}"
        )


def _require_direct_parent(
    repo_root: Path, child: str, expected_parent: str, label: str
) -> None:
    lineage = _git(
        repo_root, "rev-list", "--parents", "-n", "1", child
    ).stdout.split()
    if lineage != [child, expected_parent]:
        raise AuditRecoveryError(f"{label} parent differs")


def _require_exact_name_status(
    repo_root: Path,
    *,
    parent: str,
    child: str,
    expected: Mapping[str, str],
    label: str,
) -> None:
    lines = _git(
        repo_root,
        "diff",
        "--name-status",
        "--no-renames",
        parent,
        child,
    ).stdout.splitlines()
    observed: dict[str, str] = {}
    for line in lines:
        fields = line.split("\t")
        if len(fields) != 2 or fields[0] not in {"A", "M", "D", "T"}:
            raise AuditRecoveryError(f"{label} changed-path record differs")
        status, relative = fields
        normalized = _safe_relative(relative, label)
        if normalized in observed:
            raise AuditRecoveryError(f"{label} changed path is duplicated")
        observed[normalized] = status
    if observed != dict(expected):
        raise AuditRecoveryError(f"{label} name-status map differs")


def _require_exact_freeze_chain(
    repo_root: Path,
    *,
    code_commit: str,
    evidence_commit: str,
    final_commit: str,
    qualification_paths: Sequence[str],
) -> None:
    _require_direct_parent(
        repo_root,
        C1_RECOVERY_FREEZE_COMMIT,
        ORIGINAL_FREEZE_COMMIT,
        "C1 recovery freeze",
    )
    _require_direct_parent(
        repo_root,
        C2_RECOVERY_FREEZE_COMMIT,
        C1_RECOVERY_FREEZE_COMMIT,
        "C2 recovery freeze",
    )
    _require_direct_parent(
        repo_root,
        C3_RECOVERY_FREEZE_COMMIT,
        C2_RECOVERY_FREEZE_COMMIT,
        "C3 code freeze",
    )
    _require_direct_parent(
        repo_root,
        E3_QUALIFICATION_FREEZE_COMMIT,
        C3_RECOVERY_FREEZE_COMMIT,
        "E3 qualification freeze",
    )
    _require_direct_parent(
        repo_root, code_commit, E3_QUALIFICATION_FREEZE_COMMIT, "C4 code freeze"
    )
    _require_direct_parent(repo_root, evidence_commit, code_commit, "E4 evidence freeze")
    _require_direct_parent(repo_root, final_commit, evidence_commit, "F4 final freeze")
    _require_exact_name_status(
        repo_root,
        parent=ORIGINAL_FREEZE_COMMIT,
        child=C1_RECOVERY_FREEZE_COMMIT,
        expected=ORIGINAL_TO_C1_NAME_STATUS,
        label="original-to-C1 freeze",
    )
    _require_exact_name_status(
        repo_root,
        parent=C1_RECOVERY_FREEZE_COMMIT,
        child=C2_RECOVERY_FREEZE_COMMIT,
        expected=C1_TO_C2_NAME_STATUS,
        label="C1-to-C2 freeze",
    )
    _require_exact_name_status(
        repo_root,
        parent=C2_RECOVERY_FREEZE_COMMIT,
        child=C3_RECOVERY_FREEZE_COMMIT,
        expected=C2_TO_C3_NAME_STATUS,
        label="C2-to-C3 freeze",
    )
    _require_exact_name_status(
        repo_root,
        parent=C3_RECOVERY_FREEZE_COMMIT,
        child=E3_QUALIFICATION_FREEZE_COMMIT,
        expected=C3_TO_E3_NAME_STATUS,
        label="C3-to-E3 freeze",
    )
    _require_exact_name_status(
        repo_root,
        parent=E3_QUALIFICATION_FREEZE_COMMIT,
        child=code_commit,
        expected=E3_TO_C4_NAME_STATUS,
        label="E3-to-C4 freeze",
    )
    _require_exact_name_status(
        repo_root,
        parent=code_commit,
        child=evidence_commit,
        expected={path: "A" for path in qualification_paths},
        label="E4 evidence freeze",
    )
    _require_exact_name_status(
        repo_root,
        parent=evidence_commit,
        child=final_commit,
        expected={path: "A" for path in MANDATORY_F_ADDITION_PATHS},
        label="F4 final freeze",
    )


def _git_blob(repo_root: Path, commit: str, relative: str) -> tuple[str, bytes]:
    relative = _safe_relative(relative, "Git-bound file")
    oid = _git(repo_root, "rev-parse", f"{commit}:{relative}").stdout.strip()
    if HEX40.fullmatch(oid) is None and HEX64.fullmatch(oid) is None:
        raise AuditRecoveryError(f"Git blob ID is malformed: {relative}")
    completed = subprocess.run(
        ["git", "show", f"{commit}:{relative}"],
        cwd=repo_root,
        check=False,
        capture_output=True,
    )
    if completed.returncode:
        raise AuditRecoveryError(f"cannot read Git-bound file: {relative}")
    return oid, completed.stdout


def _freeze_inventory(
    repo_root: Path,
    *,
    first_commit: str,
    final_commit: str,
    paths: Sequence[str],
    label: str,
) -> list[dict[str, Any]]:
    if not paths or len(paths) != len(set(paths)):
        raise AuditRecoveryError(f"{label} path inventory is empty or duplicated")
    rows: list[dict[str, Any]] = []
    for relative in sorted(paths):
        normalized = _safe_relative(relative, label)
        first_oid, first_bytes = _git_blob(repo_root, first_commit, normalized)
        final_oid, final_bytes = _git_blob(repo_root, final_commit, normalized)
        if first_oid != final_oid or first_bytes != final_bytes:
            raise AuditRecoveryError(f"{label} changed across its freeze: {normalized}")
        physical = repo_root / normalized
        try:
            details = physical.lstat()
            live = physical.read_bytes()
        except OSError as exc:
            raise AuditRecoveryError(f"{label} is absent at final freeze") from exc
        if (
            not stat.S_ISREG(details.st_mode)
            or details.st_nlink != 1
            or live != final_bytes
        ):
            raise AuditRecoveryError(f"{label} live bytes differ: {normalized}")
        rows.append(
            {
                "path": normalized,
                "bytes": len(final_bytes),
                "sha256": hashlib.sha256(final_bytes).hexdigest(),
                "first_commit_blob": first_oid,
                "final_commit_blob": final_oid,
            }
        )
    return rows


def _final_inventory(
    repo_root: Path, final_commit: str, paths: Sequence[str], label: str
) -> list[dict[str, Any]]:
    if not paths or len(paths) != len(set(paths)):
        raise AuditRecoveryError(f"{label} path inventory is empty or duplicated")
    rows: list[dict[str, Any]] = []
    for relative in sorted(paths):
        normalized = _safe_relative(relative, label)
        oid, frozen = _git_blob(repo_root, final_commit, normalized)
        physical = repo_root / normalized
        try:
            details = physical.lstat()
            live = physical.read_bytes()
        except OSError as exc:
            raise AuditRecoveryError(f"{label} is absent at final freeze") from exc
        if (
            not stat.S_ISREG(details.st_mode)
            or details.st_nlink != 1
            or live != frozen
        ):
            raise AuditRecoveryError(f"{label} live bytes differ: {normalized}")
        rows.append(
            {
                "path": normalized,
                "bytes": len(frozen),
                "sha256": hashlib.sha256(frozen).hexdigest(),
                "final_commit_blob": oid,
            }
        )
    return rows


def normalize_j_map_keys(maps: Mapping[Any, Any]) -> dict[int, Any]:
    """Normalize only canonical integer/canonical-decimal map keys.

    The pinned release uses source-layer identifiers in ``0..78``.  Booleans,
    signed/zero-padded strings, floats, out-of-range values, and aliases such as
    both ``45`` and ``"45"`` are rejected rather than silently collapsed.
    """

    normalized: dict[int, Any] = {}
    for key, value in maps.items():
        if isinstance(key, bool):
            raise AuditRecoveryError("J-lens layer key is noncanonical")
        if isinstance(key, int):
            layer = key
        elif isinstance(key, str) and key.isascii() and key.isdecimal():
            layer = int(key)
            if key != str(layer):
                raise AuditRecoveryError("J-lens layer key is noncanonical")
        else:
            raise AuditRecoveryError("J-lens layer key is noncanonical")
        if not 0 <= layer < int(protocol.J_LENS_SPEC["target_layer"]):
            raise AuditRecoveryError("J-lens layer key is outside the pinned release")
        if layer in normalized:
            raise AuditRecoveryError("J-lens layer key is duplicated")
        normalized[layer] = value
    return normalized


def _torch_load_checkpoint(path: Path) -> Any:
    import torch

    return torch.load(path, map_location="cpu", weights_only=True, mmap=True)


def load_j_checkpoint_superset(
    j_lens_path: Path,
    watchdog: Any,
) -> tuple[Path, Mapping[int, Any], dict[str, Any], dict[str, Any]]:
    """Load the exact FP16 release and expose exactly study layers 45..78.

    The public checkpoint stores its 79 source maps in FP16.  That source
    representation is distinct from the frozen auditor's computation
    representation: ``_ArtifactJBackend.j_matrix`` explicitly converts each
    selected source map to BF16 on the authorized device before use.
    """

    import torch

    lexical = j_lens_path.expanduser().absolute()
    if lexical.is_symlink():
        raise AuditRecoveryError("J-lens checkpoint is a symlink")
    try:
        path = lexical.resolve(strict=True)
    except OSError as exc:
        raise AuditRecoveryError("J-lens checkpoint is missing") from exc
    watchdog.check()
    if (
        not path.is_file()
        or path.stat().st_nlink != 1
        or path.stat().st_size != PUBLIC_J_CHECKPOINT_BYTES
        or protocol.sha256_file(path) != protocol.J_LENS_SPEC["sha256"]
    ):
        raise AuditRecoveryError("J-lens checkpoint hash or file type differs")
    watchdog.check()
    checkpoint = _torch_load_checkpoint(path)
    if (
        not isinstance(checkpoint, Mapping)
        or not {"J", "n_prompts", "d_model"} <= set(checkpoint)
        or type(checkpoint["n_prompts"]) is not int
        or checkpoint["n_prompts"]
        != int(protocol.J_LENS_SPEC["release_config"]["prompts_fitted"])
        or type(checkpoint["d_model"]) is not int
        or checkpoint["d_model"] != protocol.WIDTH
        or not isinstance(checkpoint["J"], Mapping)
    ):
        raise AuditRecoveryError("J-lens checkpoint metadata differs")
    normalized = normalize_j_map_keys(checkpoint["J"])
    available = tuple(sorted(normalized))
    required = tuple(protocol.J_LAYERS)
    if required != REQUIRED_J_LAYERS or not set(required) <= set(available):
        raise AuditRecoveryError("J-lens checkpoint lacks a required study layer")
    for layer, tensor in normalized.items():
        if tuple(tensor.shape) != PUBLIC_J_SOURCE_SHAPE:
            raise AuditRecoveryError(
                f"J-lens source map shape differs at layer {layer}"
            )
        if tensor.dtype != torch.float16:
            raise AuditRecoveryError(
                f"J-lens source map dtype differs at layer {layer}"
            )
    filtered = {layer: normalized[layer] for layer in required}
    extras = tuple(layer for layer in available if layer not in set(required))
    inventory_core = {
        "status": "pass_pinned_canonical_superset_filtered",
        "available_layers": list(available),
        "required_layers": list(required),
        "unused_extra_layers": list(extras),
        "available_map_count": len(available),
        "required_map_count": len(required),
        "checkpoint_sha256": protocol.J_LENS_SPEC["sha256"],
        "checkpoint_bytes": PUBLIC_J_CHECKPOINT_BYTES,
        "checkpoint_n_prompts": checkpoint["n_prompts"],
        "checkpoint_d_model": checkpoint["d_model"],
        "source_map_shape": list(PUBLIC_J_SOURCE_SHAPE),
        "source_map_dtype": PUBLIC_J_SOURCE_DTYPE,
        "computation_dtype": "torch.bfloat16",
        "computation_cast_contract": (
            "source.to(device=self.device,dtype=torch.bfloat16,"
            "non_blocking=True).contiguous()"
        ),
    }
    inventory = {
        **inventory_core,
        "receipt_sha256": protocol.canonical_sha256(inventory_core),
    }
    # Preserve the frozen auditor's return contract.  The complete inventory is
    # carried separately into recovery provenance.
    audit_record = {
        "sha256": protocol.J_LENS_SPEC["sha256"],
        "map_count": len(required),
        "revision": protocol.J_LENS_SPEC["revision"],
    }
    return path, filtered, audit_record, inventory


class RecoveryWatchdog:
    """A fresh recovery clock which never derives authority from the old run."""

    def __init__(
        self,
        authorization: Mapping[str, Any],
        *,
        audit_started_at_unix: float | None = None,
        clock: Any = time.time,
    ) -> None:
        self.started = float(authorization["recovery_started_at_unix"])
        self.deadline = float(authorization["recovery_deadline_at_unix"])
        self.rate = float(authorization["hourly_price_usd"])
        self.max_spend = float(authorization["max_spend_usd"])
        self.clock = clock
        self.audit_started_at_unix = (
            float(clock())
            if audit_started_at_unix is None
            else float(audit_started_at_unix)
        )
        duration = self.deadline - self.started
        if (
            not all(
                math.isfinite(value)
                for value in (
                    self.started,
                    self.deadline,
                    self.rate,
                    self.max_spend,
                    self.audit_started_at_unix,
                )
            )
            or duration <= 0
            or self.rate <= 0
            or self.max_spend <= 0
            or self.rate * duration / 3600 > self.max_spend
            or not self.started <= self.audit_started_at_unix < self.deadline
        ):
            raise AuditRecoveryError("fresh recovery watchdog authority differs")

    def check(self) -> None:
        now = float(self.clock())
        elapsed = now - self.started
        if (
            not math.isfinite(now)
            or elapsed < 0
            or now >= self.deadline
            or self.rate * elapsed / 3600 > self.max_spend
        ):
            raise AuditRecoveryError("fresh recovery watchdog expired")


@contextlib.contextmanager
def zero_forward_guard(
    *,
    torch_module: Any | None = None,
    transformers_module: Any | None = None,
    auto_model_base: type[Any] | None = None,
) -> Iterator[dict[str, int]]:
    """Fail closed across instance, class, saved-alias, and load surfaces."""

    if torch_module is None:
        import torch as torch_module
    if transformers_module is None:
        import transformers as transformers_module
    if auto_model_base is None:
        from transformers.models.auto.auto_factory import _BaseAutoModelClass

        auto_model_base = _BaseAutoModelClass

    counts = dict(ZERO_GUARD_COUNTS)
    module_class = torch_module.nn.Module

    def blocked_call(*_args: Any, **_kwargs: Any) -> Any:
        counts["torch_module_calls"] += 1
        raise AuditRecoveryError("torch.nn.Module calls are forbidden in recovery")

    def blocked_getattribute(instance: Any, name: str) -> Any:
        if name == "forward":
            counts["direct_forward_attribute_access"] += 1
            raise AuditRecoveryError("direct model.forward access is forbidden")
        return object.__getattribute__(instance, name)

    def blocked_forward(*_args: Any, **_kwargs: Any) -> Any:
        counts["direct_forward_attribute_access"] += 1
        raise AuditRecoveryError("direct model.forward call is forbidden")

    def blocked_init(*_args: Any, **_kwargs: Any) -> None:
        counts["model_construction_calls"] += 1
        raise AuditRecoveryError("torch.nn.Module construction is forbidden")

    def blocked_state_load(*_args: Any, **_kwargs: Any) -> Any:
        counts["model_state_load_calls"] += 1
        raise AuditRecoveryError("model state loading is forbidden")

    restored: list[tuple[Any, str, bool, Any]] = []
    patched: set[tuple[int, str]] = set()

    def patch(owner: Any, name: str, replacement: Any) -> None:
        key = (id(owner), name)
        if key in patched:
            return
        namespace = vars(owner)
        had_own = name in namespace
        original = namespace.get(name)
        restored.append((owner, name, had_own, original))
        setattr(owner, name, replacement)
        patched.add(key)

    def descendants(root: type[Any]) -> list[type[Any]]:
        found: list[type[Any]] = []
        pending = [root]
        seen: set[type[Any]] = set()
        while pending:
            candidate = pending.pop()
            if candidate in seen:
                continue
            seen.add(candidate)
            found.append(candidate)
            try:
                pending.extend(candidate.__subclasses__())
            except TypeError as exc:
                raise AuditRecoveryError(
                    "cannot enumerate torch module subclasses"
                ) from exc
        return found

    def blocked_new(_cls: type[Any], *_args: Any, **_kwargs: Any) -> Any:
        counts["model_construction_calls"] += 1
        raise AuditRecoveryError("torch.nn.Module construction is forbidden")

    def blocked_init_subclass(_cls: type[Any], **_kwargs: Any) -> None:
        counts["model_construction_calls"] += 1
        raise AuditRecoveryError("new torch.nn.Module subclasses are forbidden")

    module_classes = descendants(module_class)
    forward_functions: list[Any] = []
    seen_forward_functions: set[int] = set()
    for cls in module_classes:
        descriptor = vars(cls).get("forward")
        if isinstance(descriptor, (classmethod, staticmethod)):
            descriptor = descriptor.__func__
        if descriptor is not None and callable(descriptor) and not hasattr(
            descriptor, "__code__"
        ):
            raise AuditRecoveryError(
                "torch module has a nonpatchable forward descriptor"
            )
        if getattr(descriptor, "__code__", None) is not None and id(
            descriptor
        ) not in seen_forward_functions:
            seen_forward_functions.add(id(descriptor))
            forward_functions.append(descriptor)
    loader_classes: list[type[Any]] = [
        transformers_module.PreTrainedModel,
        auto_model_base,
    ]

    persistent_name = f"_audit_recovery_forward_block_{uuid.uuid4().hex}"

    def persistent_template(*_args: Any, **_kwargs: Any) -> Any:
        return _audit_recovery_persistent_forward_blocker()  # type: ignore[name-defined]  # noqa: F821

    template_code = persistent_template.__code__
    if template_code.co_names != ("_audit_recovery_persistent_forward_blocker",):
        raise AuditRecoveryError("persistent forward blocker template differs")
    persistent_code_records: list[tuple[Any, Any]] = []
    persistent_global_records: list[tuple[dict[str, Any], bool, Any]] = []
    seen_globals: set[int] = set()

    try:
        for function in forward_functions:
            namespace = function.__globals__
            if id(namespace) not in seen_globals:
                seen_globals.add(id(namespace))
                persistent_global_records.append(
                    (namespace, persistent_name in namespace, namespace.get(persistent_name))
                )
                namespace[persistent_name] = blocked_forward
            original_code = function.__code__
            persistent_code_records.append((function, original_code))
            function.__code__ = template_code.replace(
                co_freevars=original_code.co_freevars,
                co_names=(persistent_name,),
            )
        for cls in module_classes:
            namespace = vars(cls)
            if cls is module_class or "_call_impl" in namespace:
                patch(cls, "_call_impl", blocked_call)
            if cls is module_class or "forward" in namespace:
                patch(cls, "forward", blocked_forward)
            if cls is module_class or "__getattribute__" in namespace:
                patch(cls, "__getattribute__", blocked_getattribute)
            if cls is module_class or "__init__" in namespace:
                patch(cls, "__init__", blocked_init)
            if cls is module_class or "__new__" in namespace:
                patch(cls, "__new__", staticmethod(blocked_new))
            if cls is module_class or "load_state_dict" in namespace:
                patch(cls, "load_state_dict", blocked_state_load)
            if cls is module_class or "__init_subclass__" in namespace:
                patch(
                    cls,
                    "__init_subclass__",
                    classmethod(blocked_init_subclass),
                )
        for optional_name in ("TFPreTrainedModel", "FlaxPreTrainedModel"):
            optional = vars(transformers_module).get(optional_name)
            if isinstance(optional, type):
                loader_classes.append(optional)
        for cls in loader_classes:
            def blocked_loader(_cls: Any, *_args: Any, **_kwargs: Any) -> Any:
                counts["transformers_model_load_calls"] += 1
                raise AuditRecoveryError(
                    "Transformers model loads are forbidden in recovery"
                )

            for method in ("from_pretrained", "from_config"):
                if hasattr(cls, method):
                    patch(cls, method, classmethod(blocked_loader))
        modeling_utils = vars(transformers_module).get("modeling_utils")
        if modeling_utils is not None:
            for name in ("load_sharded_checkpoint", "load_state_dict"):
                if hasattr(modeling_utils, name):
                    patch(modeling_utils, name, blocked_state_load)
        jit = getattr(torch_module, "jit", None)
        if jit is not None and hasattr(jit, "load"):
            patch(jit, "load", blocked_state_load)
        yield counts
    finally:
        for owner, name, had_own, descriptor in reversed(restored):
            if had_own:
                setattr(owner, name, descriptor)
            else:
                delattr(owner, name)
        for function, original_code in reversed(persistent_code_records):
            function.__code__ = original_code
        for namespace, had_name, original in reversed(persistent_global_records):
            if had_name:
                namespace[persistent_name] = original
            else:
                namespace.pop(persistent_name, None)


def raw_tree_ledger(raw_root: Path) -> dict[str, Any]:
    """Hash every regular file and directory in a finalized raw tree."""

    lexical = raw_root.expanduser().absolute()
    if lexical.is_symlink():
        raise AuditRecoveryError("raw root is a symlink")
    try:
        root = lexical.resolve(strict=True)
    except OSError as exc:
        raise AuditRecoveryError("raw root is missing") from exc
    if not root.is_dir():
        raise AuditRecoveryError("raw root is not a directory")
    files: list[dict[str, Any]] = []
    directories: list[str] = []
    for path in root.rglob("*"):
        details = path.lstat()
        relative = path.relative_to(root).as_posix()
        if stat.S_ISLNK(details.st_mode):
            raise AuditRecoveryError("raw tree contains a symlink")
        if stat.S_ISDIR(details.st_mode):
            directories.append(relative)
            continue
        if not stat.S_ISREG(details.st_mode) or details.st_nlink != 1:
            raise AuditRecoveryError("raw tree contains a special or linked file")
        files.append(
            {
                "path": relative,
                "bytes": details.st_size,
                "sha256": protocol.sha256_file(path),
            }
        )
    files.sort(key=lambda row: str(row["path"]))
    directories.sort()
    if not files or "RUN_COMPLETE.json" not in {row["path"] for row in files}:
        raise AuditRecoveryError("raw tree lacks RUN_COMPLETE.json")
    complete, _ = _canonical_file(root / "RUN_COMPLETE.json", "RUN_COMPLETE")
    run_receipt_hash = _self_hash(complete, "RUN_COMPLETE")
    manifested = complete.get("records")
    if not isinstance(manifested, list):
        raise AuditRecoveryError("RUN_COMPLETE manifest is missing")
    observed = {str(row["path"]): row for row in files}
    expected_paths: set[str] = set()
    for row in manifested:
        if not isinstance(row, Mapping):
            raise AuditRecoveryError("RUN_COMPLETE manifest row differs")
        relative = _safe_relative(row.get("path"), "raw manifest path")
        if relative in expected_paths:
            raise AuditRecoveryError("RUN_COMPLETE manifest path is duplicated")
        expected_paths.add(relative)
        actual = observed.get(relative)
        if (
            actual is None
            or actual["bytes"] != row.get("bytes")
            or actual["sha256"] != row.get("sha256")
        ):
            raise AuditRecoveryError(f"raw manifest differs: {relative}")
    if set(observed) != {*expected_paths, "RUN_COMPLETE.json"}:
        raise AuditRecoveryError("raw tree has a missing or unmanifested file")
    core = {
        "status": "pass_full_raw_tree_hash_ledger",
        "raw_root": root.as_posix(),
        "run_id": complete.get("run_id"),
        "run_receipt_sha256": run_receipt_hash,
        "file_count": len(files),
        "total_bytes": sum(int(row["bytes"]) for row in files),
        "files": files,
        "file_inventory_sha256": protocol.canonical_sha256(files),
        "directory_count": len(directories),
        "directories": directories,
        "directory_inventory_sha256": protocol.canonical_sha256(directories),
    }
    return {**core, "receipt_sha256": protocol.canonical_sha256(core)}


def _physical_record(path: Path, role: str) -> dict[str, Any]:
    candidate = path.expanduser().absolute()
    try:
        details = candidate.lstat()
    except OSError as exc:
        raise AuditRecoveryError(f"bound file is missing: {role}") from exc
    if not stat.S_ISREG(details.st_mode) or details.st_nlink != 1:
        raise AuditRecoveryError(f"bound file type differs: {role}")
    return {
        "role": role,
        "path": candidate.as_posix(),
        "bytes": details.st_size,
        "sha256": protocol.sha256_file(candidate),
    }


def _validate_physical_records(
    records: Any,
    *,
    label: str,
    required_roles: set[str] | frozenset[str] | None = None,
) -> list[dict[str, Any]]:
    if not isinstance(records, list) or not records:
        raise AuditRecoveryError(f"{label} is missing")
    normalized: list[dict[str, Any]] = []
    roles: set[str] = set()
    paths: set[str] = set()
    for row in records:
        if not isinstance(row, Mapping) or set(row) != {
            "role",
            "path",
            "bytes",
            "sha256",
        }:
            raise AuditRecoveryError(f"{label} row schema differs")
        role = str(row["role"])
        path = Path(str(row["path"])).expanduser().absolute()
        if (
            not role
            or role in roles
            or path.as_posix() in paths
            or row != _physical_record(path, role)
        ):
            raise AuditRecoveryError(f"{label} row differs")
        roles.add(role)
        paths.add(path.as_posix())
        normalized.append(dict(row))
    if required_roles is not None and not required_roles <= roles:
        raise AuditRecoveryError(f"{label} required roles are absent")
    if normalized != sorted(normalized, key=lambda row: str(row["role"])):
        raise AuditRecoveryError(f"{label} order differs")
    return normalized


def _validate_git_file_rows(
    rows: Any,
    *,
    repo_root: Path,
    first_commit: str | None,
    final_commit: str,
    label: str,
) -> list[dict[str, Any]]:
    if not isinstance(rows, list):
        raise AuditRecoveryError(f"{label} is missing")
    paths = [str(row.get("path")) for row in rows if isinstance(row, Mapping)]
    expected = (
        _final_inventory(repo_root, final_commit, paths, label)
        if first_commit is None
        else _freeze_inventory(
            repo_root,
            first_commit=first_commit,
            final_commit=final_commit,
            paths=paths,
            label=label,
        )
    )
    if rows != expected:
        raise AuditRecoveryError(f"{label} binding differs")
    return expected


def _nested_self_hash(
    value: Mapping[str, Any], field: str, label: str
) -> str:
    core = dict(value)
    supplied = core.pop(field, None)
    if (
        not isinstance(supplied, str)
        or HEX64.fullmatch(supplied) is None
        or supplied != protocol.canonical_sha256(core)
    ):
        raise AuditRecoveryError(f"{label} self-hash differs")
    return supplied


def _require_zero_outcome_scope(value: Mapping[str, Any], label: str) -> None:
    for field in (
        "model_forward_count",
        "target_prompt_render_count",
        "target_feature_vector_count",
    ):
        if field in value and value[field] != 0:
            raise AuditRecoveryError(f"{label} performed a forbidden forward")
    for field in (
        "raw_input_paths",
        "authorized_raw_input_paths",
        "outcome_input_paths",
        "analysis_data_inputs",
    ):
        if field in value and value[field] != []:
            raise AuditRecoveryError(f"{label} consumed outcome/raw input")
    for field in ("raw_run_opened", "compact_result_opened"):
        if field in value and value[field] is not False:
            raise AuditRecoveryError(f"{label} opened forbidden scientific data")


def _validate_raw_guard_evidence(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise AuditRecoveryError("qualification raw/path guard evidence is absent")
    diagnostics = value.get("path_diagnostics")
    allowed = value.get("allowed_outside_raw_enotdir_probe_count")
    proc_allowed = value.get(
        "allowed_outside_raw_proc_self_maps_probe_count"
    )
    if (
        value.get("status")
        != "pass_no_forbidden_raw_or_path_guard_rejection"
        or value.get("forbidden_raw_root")
        != "/workspace/consciousness_sae_signed_dose_scan/"
        "consciousness_sae_signed_dose_scan_v1/raw"
        or value.get("raw_forbidden_attempt_count") != 0
        or value.get("path_guard_rejected_attempt_count") != 0
        or value.get("counter_semantics")
        != {
            "raw_forbidden_attempt_count": (
                "lexically_inside_forbidden_raw_root"
            ),
            "path_guard_rejected_attempt_count": (
                "pre_containment_symlink_noncanonical_or_unresolvable_rejection"
            ),
            "allowed_outside_raw_enotdir_probe_count": (
                "errno_ENOTDIR_after_verified_non_symlink_ancestors"
            ),
            "allowed_outside_raw_proc_self_maps_probe_count": (
                "exact_kernel_proc_self_maps_alias_to_current_numeric_pid"
            ),
        }
        or value.get("path_diagnostic_limit") != 16
        or isinstance(allowed, bool)
        or not isinstance(allowed, int)
        or allowed < 0
        or isinstance(proc_allowed, bool)
        or not isinstance(proc_allowed, int)
        or proc_allowed != 1
        or not isinstance(diagnostics, list)
        or len(diagnostics) != min(allowed + proc_allowed, 16)
        or any(
            not isinstance(row, Mapping)
            or set(row) != {"classification", "errno", "path_sha256"}
            or (
                row.get("classification") == "allowed_outside_raw_enotdir"
                and row.get("errno") != 20
            )
            or (
                row.get("classification")
                == "allowed_outside_raw_proc_self_maps"
                and row.get("errno") is not None
            )
            or row.get("classification")
            not in {
                "allowed_outside_raw_enotdir",
                "allowed_outside_raw_proc_self_maps",
            }
            or HEX64.fullmatch(str(row.get("path_sha256", ""))) is None
            for row in diagnostics
        )
        or value.get("path_diagnostics_sha256")
        != protocol.canonical_sha256(diagnostics)
        or sum(
            row.get("classification")
            == "allowed_outside_raw_proc_self_maps"
            and row.get("path_sha256")
            == "8f9bcd1250f4c9fbe2eb0de0e4f9f2d4702ba9b7d168c54a35496ca5e51d7665"
            for row in diagnostics
        )
        != 1
    ):
        raise AuditRecoveryError("qualification raw/path guard evidence differs")
    return dict(value)


def _validate_qualification_evidence(
    rows: Sequence[Mapping[str, Any]],
    *,
    repo_root: Path,
    code_freeze_commit: str,
) -> dict[str, Any]:
    successor_authority = (
        verify_qualification_incident.successor_c4_authority_binding(
            repo_root / QUALIFICATION_INCIDENT_ROOT,
            repo_root
            / "docs/consciousness_sae_signed_dose_scan/RECOVERY_CYCLE_LEDGER_V4.json",
        )
    )
    if (
        successor_authority.get("binding_sha256")
        != EXPECTED_SUCCESSOR_AUTHORITY_BINDING_SHA256
    ):
        raise AuditRecoveryError("qualification successor authority differs")
    paths = [str(row["path"]) for row in rows]
    parents = {PurePosixPath(path).parent.as_posix() for path in paths}
    names = {PurePosixPath(path).name for path in paths}
    if (
        len(rows) != len(MANDATORY_E_QUALIFICATION_FILENAMES)
        or names != MANDATORY_E_QUALIFICATION_FILENAMES
        or len(parents) != 1
        or next(iter(parents), "") != QUALIFICATION_DIRECTORY
        or set(paths) != MANDATORY_E_QUALIFICATION_PATHS
    ):
        raise AuditRecoveryError("mandatory E qualification receipt set differs")
    by_name: dict[str, dict[str, Any]] = {}
    for relative in paths:
        value, _file_hash = _canonical_file(
            repo_root / relative, f"E qualification {PurePosixPath(relative).name}"
        )
        by_name[PurePosixPath(relative).name] = value

    packet = by_name["RECOVERY_EQUIVALENCE_PACKET.json"]
    packet_hash = _nested_self_hash(packet, "packet_sha256", "equivalence packet")
    closure = packet.get("recovery_closure")
    compatibility = packet.get("compatibility_proof")
    if (
        packet.get("status")
        != "pass_source_design_and_compatibility_bound_no_outcomes_loaded"
        or not isinstance(closure, Mapping)
        or closure.get("code_freeze_commit") != code_freeze_commit
        or HEX64.fullmatch(str(closure.get("inventory_sha256", ""))) is None
        or not isinstance(compatibility, Mapping)
        or compatibility.get("compatibility_change_count") != 1
        or compatibility.get("new_model_forwards") != 0
        or compatibility.get("new_scientific_observations") != 0
        or compatibility.get("required_layers") != list(range(45, 79))
        or compatibility.get("pinned_available_layers") != list(range(79))
        or compatibility.get("scientific_field_projection_unchanged") is not True
    ):
        raise AuditRecoveryError("outcome-blind equivalence packet differs")
    _require_zero_outcome_scope(packet, "equivalence packet")

    equivalence = by_name["RECOVERY_EQUIVALENCE_VERIFICATION.json"]
    equivalence_hash = _self_hash(equivalence, "equivalence verification")
    closure_hash = str(closure["inventory_sha256"])
    if (
        equivalence.get("status")
        != "pass_outcome_blind_recovery_equivalence_verified"
        or equivalence.get("packet_sha256") != packet_hash
        or equivalence.get("code_freeze_commit") != code_freeze_commit
        or equivalence.get("recovery_closure_inventory_sha256") != closure_hash
    ):
        raise AuditRecoveryError("equivalence verification binding differs")
    _require_zero_outcome_scope(equivalence, "equivalence verification")

    marker = by_name["ATTEMPT_STARTED.json"]
    marker_hash = _self_hash(marker, "qualification attempt marker")
    declared_inputs = marker.get("declared_input_paths")
    try:
        qualification_started = float(marker["started_at_unix"])
        qualification_deadline = float(marker["qualification_deadline_at_unix"])
        qualification_rate = float(marker["hourly_price_usd"])
        qualification_max_spend = float(marker["max_spend_usd"])
    except (KeyError, TypeError, ValueError, OverflowError) as exc:
        raise AuditRecoveryError("qualification watchdog authority differs") from exc
    if (
        marker.get("status") != "attempt_started_irrevocably"
        or marker.get("qualification_protocol_version")
        != "consciousness_sae_signed_dose_scan_v1.audit_recovery_host_qualification_v4"
        or marker.get("qualification_cycle_version")
        != "consciousness_sae_signed_dose_scan_v1.audit_only_recovery_cycle_v4"
        or marker.get("global_qualification_ordinal") != 4
        or marker.get("successor_qualification_attempt") != 1
        or marker.get("attempt_number") != 1
        or marker.get("retry_authorized") is not False
        or marker.get("successor_authority_binding_sha256")
        != EXPECTED_SUCCESSOR_AUTHORITY_BINDING_SHA256
        or not isinstance(declared_inputs, list)
        or any(
            not isinstance(row, Mapping)
            or set(row) != {"role", "path"}
            or not isinstance(row.get("role"), str)
            or not isinstance(row.get("path"), str)
            or not str(row["path"]).startswith("/")
            for row in declared_inputs
        )
        or marker.get("declared_input_paths_sha256")
        != protocol.canonical_sha256(declared_inputs)
        or marker.get("authorized_raw_input_paths") != []
        or not all(
            math.isfinite(value)
            for value in (
                qualification_started,
                qualification_deadline,
                qualification_rate,
                qualification_max_spend,
            )
        )
        or qualification_deadline - qualification_started
        != QUALIFICATION_MAX_SECONDS
        or qualification_rate <= 0
        or qualification_max_spend != QUALIFICATION_MAX_SPEND_USD
        or qualification_rate * QUALIFICATION_MAX_SECONDS / 3600
        > QUALIFICATION_MAX_SPEND_USD
    ):
        raise AuditRecoveryError("qualification one-attempt marker differs")
    _require_zero_outcome_scope(marker, "qualification attempt marker")

    target = by_name["TARGET_HOST_QUALIFICATION.json"]
    target_hash = _self_hash(target, "target-host qualification")
    target_inputs = target.get("inputs")
    fresh_pod = target.get("fresh_pod")
    checkpoint = target.get("j_checkpoint")
    cast_probe = (
        checkpoint.get("frozen_bf16_cast_probe")
        if isinstance(checkpoint, Mapping)
        else None
    )
    cuda = target.get("cuda_startup")
    raw_guard = target.get("raw_access_guard")
    _validate_raw_guard_evidence(raw_guard)
    qualification_watchdog = target.get("qualification_watchdog")
    target_roles = [
        "equivalence_packet",
        "fresh_cache",
        "fresh_guest",
        "fresh_ownership",
        "independent_plan_audit",
        "pinned_j_checkpoint",
        "predecessor_qualification_attempt_marker",
        "predecessor_qualification_frozen_termination",
        "predecessor_qualification_postdelete_inventory",
        "predecessor_qualification_termination_audit",
        "predecessor_recovery_equivalence_packet",
        "predecessor_recovery_equivalence_verification",
        "predecessor_target_host_qualification",
        "predecessor_target_host_qualification_verification",
        "recovery_c4_status_map",
        "recovery_cycle_ledger_v4",
    ]
    target_input_projection = [
        {"role": row.get("role"), "path": row.get("path")}
        for row in target_inputs
        if isinstance(row, Mapping)
    ] if isinstance(target_inputs, list) else []
    try:
        target_started = float(target["started_at_unix"])
        target_completed = float(target["completed_at_unix"])
    except (KeyError, TypeError, ValueError, OverflowError) as exc:
        raise AuditRecoveryError("qualification watchdog evidence differs") from exc
    expected_watchdog = {
        "status": "pass_independent_qualification_time_cost_cap",
        "started_at_unix": target.get("started_at_unix"),
        "qualification_deadline_at_unix": marker.get(
            "qualification_deadline_at_unix"
        ),
        "maximum_seconds": QUALIFICATION_MAX_SECONDS,
        "hourly_price_usd": marker.get("hourly_price_usd"),
        "max_spend_usd": QUALIFICATION_MAX_SPEND_USD,
        "maximum_theoretical_spend_usd": (
            qualification_rate * QUALIFICATION_MAX_SECONDS / 3600
        ),
        "completed_at_unix": target.get("completed_at_unix"),
    }
    if (
        target.get("status")
        != "pass_one_shot_zero_forward_target_host_qualification"
        or target.get("qualification_protocol_version")
        != "consciousness_sae_signed_dose_scan_v1.audit_recovery_host_qualification_v4"
        or target.get("qualification_cycle_version")
        != "consciousness_sae_signed_dose_scan_v1.audit_only_recovery_cycle_v4"
        or target.get("global_qualification_ordinal") != 4
        or target.get("successor_qualification_attempt") != 1
        or target.get("attempt_number") != 1
        or target.get("retry_authorized") is not False
        or target.get("attempt_marker_receipt_sha256") != marker_hash
        or target.get("successor_authority_binding_sha256")
        != EXPECTED_SUCCESSOR_AUTHORITY_BINDING_SHA256
        or target.get("successor_authority") != successor_authority
        or not isinstance(target_inputs, list)
        or len(target_inputs) != len(target_roles)
        or any(
            not isinstance(row, Mapping)
            or set(row) != {"role", "path", "bytes", "sha256"}
            or isinstance(row.get("bytes"), bool)
            or not isinstance(row.get("bytes"), int)
            or row["bytes"] < 0
            or HEX64.fullmatch(str(row.get("sha256", ""))) is None
            or not isinstance(row.get("path"), str)
            or not str(row["path"]).startswith("/")
            for row in target_inputs
        )
        or [row.get("role") for row in target_inputs] != target_roles
        or target.get("input_inventory_sha256")
        != protocol.canonical_sha256(target_inputs)
        or declared_inputs != target_input_projection
        or len(declared_inputs) != len(target_inputs)
        or not all(math.isfinite(value) for value in (target_started, target_completed))
        or target_started != qualification_started
        or not qualification_started <= target_completed < qualification_deadline
        or qualification_rate * (target_completed - qualification_started) / 3600
        > QUALIFICATION_MAX_SPEND_USD
        or qualification_watchdog != expected_watchdog
        or target.get("equivalence_verification") != equivalence
        or target.get("code_freeze_commit") != code_freeze_commit
        or target.get("recovery_closure_inventory_sha256") != closure_hash
        or target.get("zero_forward_guard") != ZERO_GUARD_COUNTS
        or not isinstance(fresh_pod, Mapping)
        or not isinstance(fresh_pod.get("pod_id"), str)
        or not fresh_pod["pod_id"]
        or fresh_pod["pod_id"] in REJECTED_PREDECESSOR_POD_IDS
        or fresh_pod.get("gpu_type") != protocol.GPU_TYPE
        or fresh_pod.get("gpu_count") != 1
        or any(
            HEX64.fullmatch(str(fresh_pod.get(field, ""))) is None
            for field in (
                "ownership_receipt_sha256",
                "guest_receipt_sha256",
                "cache_receipt_sha256",
            )
        )
        or not isinstance(checkpoint, Mapping)
        or checkpoint.get("checkpoint_sha256") != protocol.J_LENS_SPEC["sha256"]
        or checkpoint.get("checkpoint_revision") != protocol.J_LENS_SPEC["revision"]
        or checkpoint.get("available_layers") != list(range(79))
        or checkpoint.get("required_layers") != list(range(45, 79))
        or checkpoint.get("filtered_layers") != list(range(45, 79))
        or checkpoint.get("missing_required_layer_negative")
        != "pass_rejected_missing_required_layer_45"
        or checkpoint.get("checkpoint_bytes") != PUBLIC_J_CHECKPOINT_BYTES
        or checkpoint.get("required_map_source_dtype") != PUBLIC_J_SOURCE_DTYPE
        or checkpoint.get("required_map_computation_dtype") != "torch.bfloat16"
        or checkpoint.get("required_map_shape")
        != list(PUBLIC_J_SOURCE_SHAPE)
        or not isinstance(cast_probe, Mapping)
        or cast_probe.get("status")
        != "pass_exact_frozen_fp16_source_to_bf16_full_cast"
        or cast_probe.get("frozen_entrypoint")
        != (
            "experiments.consciousness_sae_signed_dose_scan.audit."
            "_ArtifactJBackend.j_matrix"
        )
        or cast_probe.get("source_layer") != 45
        or cast_probe.get("source_shape") != list(PUBLIC_J_SOURCE_SHAPE)
        or cast_probe.get("source_dtype") != PUBLIC_J_SOURCE_DTYPE
        or cast_probe.get("computation_shape") != list(PUBLIC_J_SOURCE_SHAPE)
        or cast_probe.get("computation_dtype") != "torch.bfloat16"
        or cast_probe.get("device") != "cuda:0"
        or "B200" not in str(cast_probe.get("device_name"))
        or cast_probe.get("tiny_cross_device_probe_shape") != [16, 16]
        or cast_probe.get("tiny_cpu_cast_matches_full_cuda_cast") is not True
        or cast_probe.get("full_cast_finite") is not True
        or cast_probe.get("backend_watchdog_check_count") != 1
        or cast_probe.get("model_forward_count") != 0
        or cast_probe.get("target_prompt_render_count") != 0
        or not isinstance(cuda, Mapping)
        or cuda.get("status") != "pass_frozen_startup_and_real_bf16_cublas"
        or "B200" not in str(cuda.get("device_name"))
        or cuda.get("model_forward_count") != 0
    ):
        raise AuditRecoveryError("target-host qualification evidence differs")
    _nested_self_hash(
        cast_probe,
        "receipt_sha256",
        "qualification J cast evidence",
    )
    _nested_self_hash(checkpoint, "receipt_sha256", "qualification J evidence")
    _require_zero_outcome_scope(target, "target-host qualification")

    verified = by_name["TARGET_HOST_QUALIFICATION_VERIFICATION.json"]
    verified_hash = _self_hash(verified, "target-host qualification verification")
    if (
        verified.get("status")
        != "pass_independent_target_host_qualification_verified"
        or verified.get("qualification_protocol_version")
        != "consciousness_sae_signed_dose_scan_v1.audit_recovery_host_qualification_v4"
        or verified.get("qualification_cycle_version")
        != "consciousness_sae_signed_dose_scan_v1.audit_only_recovery_cycle_v4"
        or verified.get("global_qualification_ordinal") != 4
        or verified.get("successor_qualification_attempt") != 1
        or verified.get("qualification_receipt_sha256") != target_hash
        or verified.get("attempt_marker_receipt_sha256") != marker_hash
        or verified.get("successor_authority_binding_sha256")
        != EXPECTED_SUCCESSOR_AUTHORITY_BINDING_SHA256
        or verified.get("successor_authority") != successor_authority
        or verified.get("equivalence_packet_sha256") != packet_hash
        or verified.get("code_freeze_commit") != code_freeze_commit
        or verified.get("recovery_closure_inventory_sha256") != closure_hash
        or verified.get("j_checkpoint_sha256") != protocol.J_LENS_SPEC["sha256"]
        or verified.get("j_checkpoint_evidence_sha256")
        != checkpoint.get("receipt_sha256")
        or verified.get("attempt_number") != 1
        or verified.get("retry_authorized") is not False
    ):
        raise AuditRecoveryError("target-host verification binding differs")
    _require_zero_outcome_scope(verified, "target-host verification")

    termination = by_name["QUALIFICATION_TERMINATION_AUDIT.json"]
    termination_hash = _self_hash(termination, "qualification termination audit")
    frozen_termination = by_name["QUALIFICATION_FROZEN_TERMINATION.json"]
    frozen_hash = _self_hash(frozen_termination, "qualification frozen termination")
    postdelete = by_name["QUALIFICATION_POSTDELETE_INVENTORY.json"]
    postdelete_hash = _self_hash(postdelete, "qualification postdelete inventory")
    budget = frozen_termination.get("budget_meter")
    pods = postdelete.get("pods")
    try:
        elapsed_seconds = float(budget["elapsed_seconds"])
        estimated_cost = float(budget["conservative_estimated_compute_usd"])
        provider_hourly_rate = float(budget["metered_cost_per_hour_usd"])
        maximum_cost = float(budget["max_usd"])
    except (KeyError, TypeError, ValueError, OverflowError) as exc:
        raise AuditRecoveryError("qualification teardown budget differs") from exc
    if (
        termination.get("status")
        != "deleted_exact_owned_pod_unrelated_inventory_unchanged"
        or termination.get("receipt_kind")
        != "runpod_successor_termination_audit_v1"
        or termination.get("pod_id") != fresh_pod["pod_id"]
        or termination.get("successor_ownership_receipt_sha256")
        != fresh_pod["ownership_receipt_sha256"]
        or termination.get("frozen_termination_receipt_sha256") != frozen_hash
        or termination.get("postdelete_inventory_sha256")
        != postdelete.get("inventory_sha256")
        or termination.get("precreate_inventory_sha256")
        != postdelete.get("inventory_sha256")
        or frozen_termination.get("status") != "deleted_verified"
        or frozen_termination.get("receipt_kind") != "runpod_termination_v1"
        or frozen_termination.get("pod_id") != fresh_pod["pod_id"]
        or frozen_termination.get("agent_owned") is not True
        or frozen_termination.get("delete_http_status") not in {200, 202, 204}
        or frozen_termination.get("post_delete_direct_http_status") != 404
        or frozen_termination.get("absent_from_account_inventory") is not True
        or frozen_termination.get("other_pods_mutated") is not False
        or not isinstance(budget, Mapping)
        or budget.get("budget_exhausted") is not False
        or not all(
            math.isfinite(value)
            for value in (
                elapsed_seconds,
                estimated_cost,
                provider_hourly_rate,
                maximum_cost,
            )
        )
        or elapsed_seconds < 0
        or elapsed_seconds > 1_800
        or estimated_cost < 0
        or estimated_cost > 3.0
        or provider_hourly_rate != qualification_rate
        or maximum_cost != PROVIDER_LIFECYCLE_MAX_SPEND_USD
        or postdelete.get("status") != "captured_read_only"
        or postdelete.get("receipt_kind") != "runpod_sanitized_full_inventory_v1"
        or postdelete.get("phase") != "postdelete"
        or not isinstance(pods, list)
        or any(not isinstance(row, Mapping) for row in pods)
        or any(row.get("pod_id") == fresh_pod["pod_id"] for row in pods)
        or postdelete.get("all_account_pod_count") != len(pods)
        or postdelete.get("inventory_sha256") != protocol.canonical_sha256(pods)
        or fresh_pod.get("precreate_unrelated_pod_count") != len(pods)
        or fresh_pod.get("precreate_unrelated_inventory_sha256")
        != postdelete.get("inventory_sha256")
    ):
        raise AuditRecoveryError("qualification teardown/absence evidence differs")
    return {
        "status": "pass_exact_mandatory_E_qualification_evidence",
        "directory": next(iter(parents)),
        "packet_sha256": packet_hash,
        "equivalence_verification_receipt_sha256": equivalence_hash,
        "attempt_marker_receipt_sha256": marker_hash,
        "target_qualification_receipt_sha256": target_hash,
        "target_verification_receipt_sha256": verified_hash,
        "qualification_termination_receipt_sha256": termination_hash,
        "qualification_frozen_termination_receipt_sha256": frozen_hash,
        "qualification_postdelete_receipt_sha256": postdelete_hash,
        "code_freeze_commit": code_freeze_commit,
        "recovery_closure_inventory_sha256": closure_hash,
        "qualification_pod_id": fresh_pod["pod_id"],
        "successor_authority": successor_authority,
        "zero_forward_guard": ZERO_GUARD_COUNTS,
        "raw_and_outcome_inputs": [],
    }


def _fresh_pod_binding(
    ownership_path: Path, guest_path: Path, cache_path: Path
) -> dict[str, Any]:
    ownership_raw, ownership_file_hash = _canonical_file(
        ownership_path, "fresh ownership receipt"
    )
    guest_raw, guest_file_hash = _canonical_file(guest_path, "fresh guest receipt")
    cache_raw, cache_file_hash = _canonical_file(cache_path, "fresh cache receipt")
    try:
        ownership = runpod_preflight.validate_ownership_receipt(ownership_raw)
        guest = runpod_preflight.validate_guest_receipt(
            guest_raw, ownership_receipt=ownership
        )
        cache = runpod_preflight.validate_cache_receipt(
            cache_raw, guest_receipt=guest, ownership_receipt=ownership
        )
    except runpod_preflight.PreflightError as exc:
        raise AuditRecoveryError("fresh pod receipt chain differs") from exc
    if (
        ownership.get("pod_id") in REJECTED_PREDECESSOR_POD_IDS
        or ownership.get("network_volume_id") != protocol.NETWORK_VOLUME_ID
        or ownership.get("data_center_id") != protocol.DATA_CENTER_ID
        or ownership.get("gpu_type") != protocol.GPU_TYPE
        or ownership.get("gpu_count") != 1
    ):
        raise AuditRecoveryError("fresh recovery pod resource differs")
    return {
        "pod_id": ownership["pod_id"],
        "volume_id": ownership["network_volume_id"],
        "data_center_id": ownership["data_center_id"],
        "gpu_type": ownership["gpu_type"],
        "gpu_count": ownership["gpu_count"],
        "ownership_path": ownership_path.expanduser().absolute().as_posix(),
        "guest_path": guest_path.expanduser().absolute().as_posix(),
        "cache_path": cache_path.expanduser().absolute().as_posix(),
        "ownership_receipt_sha256": ownership["receipt_sha256"],
        "guest_receipt_sha256": guest["receipt_sha256"],
        "cache_receipt_sha256": cache["receipt_sha256"],
        "ownership_file_sha256": ownership_file_hash,
        "guest_file_sha256": guest_file_hash,
        "cache_file_sha256": cache_file_hash,
    }


def _incident_binding(
    *,
    raw_root: Path,
    original_ownership: Path,
    original_guest: Path,
    original_cache: Path,
    original_authorization: Path,
    incident_evidence: Mapping[str, Path],
) -> dict[str, Any]:
    ledger = raw_tree_ledger(raw_root)
    complete, complete_file_hash = _canonical_file(
        raw_root / "RUN_COMPLETE.json", "historical RUN_COMPLETE"
    )
    original_paths = {
        "original_ownership": original_ownership,
        "original_guest": original_guest,
        "original_cache": original_cache,
        "original_authorization": original_authorization,
    }
    original_records: list[dict[str, Any]] = []
    for role, path in sorted(original_paths.items()):
        value, file_hash = _canonical_file(path, role)
        original_records.append(
            {
                "role": role,
                "path": path.expanduser().absolute().as_posix(),
                "file_sha256": file_hash,
                "receipt_sha256": _self_hash(value, role),
            }
        )
    evidence = [
        _physical_record(path, role)
        for role, path in sorted(incident_evidence.items())
    ]
    required = {
        "original_audit_failure_log",
        "original_pod_termination_audit",
        "original_postdelete_inventory",
        "incident_closure",
        "incident_closure_schema",
        "incident_closure_verification",
        "recovery_cycle_ledger",
    }
    _validate_physical_records(
        evidence, label="incident evidence", required_roles=required
    )
    failure = next(
        row for row in evidence if row["role"] == "original_audit_failure_log"
    )
    failure_text = Path(str(failure["path"])).read_text(
        encoding="utf-8", errors="strict"
    )
    signature = "CalibrationAuditError: J-lens map inventory differs"
    if failure_text.count(signature) != 1:
        raise AuditRecoveryError("historical audit failure signature differs")
    evidence_by_role = {str(row["role"]): row for row in evidence}
    closure_path = Path(str(evidence_by_role["incident_closure"]["path"]))
    schema_path = Path(str(evidence_by_role["incident_closure_schema"]["path"]))
    verification_path = Path(
        str(evidence_by_role["incident_closure_verification"]["path"])
    )
    ledger_path = Path(str(evidence_by_role["recovery_cycle_ledger"]["path"]))
    recomputed_closure = verify_incident_closure.verify_paths(
        closure_path,
        schema_path=schema_path,
        recovery_ledger_path=ledger_path,
    )
    stored_verification, stored_verification_file_hash = _canonical_file(
        verification_path, "incident independent verification"
    )
    termination, termination_file_hash = _canonical_file(
        Path(
            str(evidence_by_role["original_pod_termination_audit"]["path"])
        ),
        "original termination audit",
    )
    postdelete, postdelete_file_hash = _canonical_file(
        Path(str(evidence_by_role["original_postdelete_inventory"]["path"])),
        "original postdelete inventory",
    )
    raw_records = complete.get("records")
    if (
        stored_verification != recomputed_closure
        or stored_verification_file_hash
        != EXPECTED_INCIDENT_VERIFICATION_FILE_SHA256
        or _self_hash(stored_verification, "incident independent verification")
        != EXPECTED_INCIDENT_VERIFICATION_RECEIPT_SHA256
        or evidence_by_role["incident_closure"]["sha256"]
        != EXPECTED_INCIDENT_CLOSURE_FILE_SHA256
        or recomputed_closure["incident_closure_receipt_sha256"]
        != EXPECTED_INCIDENT_CLOSURE_RECEIPT_SHA256
        or evidence_by_role["recovery_cycle_ledger"]["sha256"]
        != EXPECTED_CYCLE_LEDGER_FILE_SHA256
        or recomputed_closure["recovery_cycle_ledger_receipt_sha256"]
        != EXPECTED_CYCLE_LEDGER_RECEIPT_SHA256
        or not isinstance(raw_records, list)
        or protocol.canonical_sha256(raw_records) != EXPECTED_RAW_RECORDS_SHA256
        or complete["receipt_sha256"] != EXPECTED_RUN_COMPLETE_RECEIPT_SHA256
        or complete_file_hash != EXPECTED_RUN_COMPLETE_FILE_SHA256
        or termination_file_hash != EXPECTED_TERMINATION_FILE_SHA256
        or _self_hash(termination, "original termination audit")
        != EXPECTED_TERMINATION_RECEIPT_SHA256
        or termination.get("status")
        != "deleted_exact_owned_pod_unrelated_inventory_unchanged"
        or termination.get("pod_id") != "wl8obvtuq0ax8t"
        or termination.get("postdelete_inventory_sha256")
        != EXPECTED_EMPTY_POD_INVENTORY_SHA256
        or postdelete_file_hash != EXPECTED_POSTDELETE_FILE_SHA256
        or _self_hash(postdelete, "original postdelete inventory")
        != EXPECTED_POSTDELETE_RECEIPT_SHA256
        or postdelete.get("status") != "captured_read_only"
        or postdelete.get("phase") != "postdelete"
        or postdelete.get("pods") != []
        or postdelete.get("all_account_pod_count") != 0
        or postdelete.get("inventory_sha256")
        != EXPECTED_EMPTY_POD_INVENTORY_SHA256
    ):
        raise AuditRecoveryError("incident closure/termination semantics differ")
    return {
        "status": "bound_complete_raw_transaction_with_mechanical_audit_failure",
        "raw_root": raw_root.expanduser().absolute().as_posix(),
        "run_id": complete.get("run_id"),
        "run_receipt_sha256": complete["receipt_sha256"],
        "run_complete_file_sha256": complete_file_hash,
        "original_pod_id": json.loads(
            original_ownership.read_text(encoding="utf-8")
        )["pod_id"],
        "failure_signature": signature,
        "failure_log_sha256": failure["sha256"],
        "raw_file_count": ledger["file_count"],
        "raw_total_bytes": ledger["total_bytes"],
        "raw_file_inventory_sha256": ledger["file_inventory_sha256"],
        "raw_directory_inventory_sha256": ledger["directory_inventory_sha256"],
        "raw_ledger_receipt_sha256_at_authorization": ledger["receipt_sha256"],
        "raw_records_sha256": EXPECTED_RAW_RECORDS_SHA256,
        "incident_independent_verification": recomputed_closure,
        "termination_receipt_sha256": EXPECTED_TERMINATION_RECEIPT_SHA256,
        "postdelete_receipt_sha256": EXPECTED_POSTDELETE_RECEIPT_SHA256,
        "original_receipts": original_records,
        "incident_evidence": evidence,
    }


def _regular_bytes(path: Path, label: str) -> bytes:
    try:
        details = path.lstat()
        raw = path.read_bytes()
    except OSError as exc:
        raise AuditRecoveryError(f"{label} is unreadable") from exc
    if not stat.S_ISREG(details.st_mode) or details.st_nlink != 1:
        raise AuditRecoveryError(f"{label} is not a single-link regular file")
    return raw


def _pretty_json(path: Path, label: str) -> tuple[dict[str, Any], bytes]:
    raw = _regular_bytes(path, label)
    try:
        value = json.loads(raw)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise AuditRecoveryError(f"{label} is malformed JSON") from exc
    if not isinstance(value, dict):
        raise AuditRecoveryError(f"{label} is not a JSON object")
    return value, raw


def _review_input_artifacts(
    manifest: Mapping[str, Any], *, brief_path: Path, context_path: Path
) -> list[dict[str, Any]]:
    artifacts = manifest.get("artifacts")
    specifications = (
        ("compact research-director plan brief", brief_path),
        ("synthesized context 1", context_path),
    )
    if not isinstance(artifacts, list) or len(artifacts) != len(specifications):
        raise AuditRecoveryError("review input artifact inventory differs")
    normalized: list[dict[str, Any]] = []
    for row, (role, physical) in zip(artifacts, specifications):
        raw = _regular_bytes(physical, f"review input {role}")
        try:
            text = raw.decode("utf-8")
        except UnicodeError as exc:
            raise AuditRecoveryError("review input is not UTF-8") from exc
        if (
            not isinstance(row, Mapping)
            or set(row) != {"role", "path", "bytes", "characters", "sha256"}
            or row.get("role") != role
            or Path(str(row.get("path"))).name != physical.name
            or row.get("bytes") != len(raw)
            or row.get("characters") != len(text)
            or row.get("sha256") != hashlib.sha256(raw).hexdigest()
        ):
            raise AuditRecoveryError("review input artifact binding differs")
        normalized.append(dict(row))
    return normalized


def _reconstruct_review_input(
    artifacts: Sequence[Mapping[str, Any]], *, brief_text: str, context_text: str
) -> str:
    texts = (brief_text, context_text)
    lines = [
        "# Research-director review packet",
        "",
        "The first artifact is the compact decision-level plan under review. "
        "Later artifacts are bounded synthesized context. Raw datasets, trial "
        "records, long logs, model-output dumps, and source-tree dumps do not "
        "belong in this packet. File contents may describe prior outcomes; those "
        "are disclosed prior evidence, not outcomes from the proposed experiment.",
        "",
        "## Artifact inventory",
        "",
    ]
    for index, row in enumerate(artifacts, start=1):
        lines.append(
            f"{index}. {row['role']}: `{Path(str(row['path'])).name}`; "
            f"bytes={row['bytes']}; sha256={row['sha256']}"
        )
    for index, (row, artifact_text) in enumerate(
        zip(artifacts, texts), start=1
    ):
        lines.extend(
            [
                "",
                f"## Artifact {index}: {row['role']} — "
                f"{Path(str(row['path'])).name}",
                "",
                f"<artifact_{index}>",
                artifact_text,
                f"</artifact_{index}>",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def _provider_verdict(review_text: str) -> str:
    lines = review_text.splitlines()
    if lines.count("# Verdict") != 1:
        raise AuditRecoveryError("provider review verdict section differs")
    start = lines.index("# Verdict") + 1
    end = next(
        (index for index in range(start, len(lines)) if lines[index].startswith("# ")),
        len(lines),
    )
    nonblank = [
        (index, lines[index])
        for index in range(start, end)
        if lines[index].strip()
    ]
    if not nonblank or nonblank[-1][1] not in RECOVERY_REVIEW_VERDICTS:
        raise AuditRecoveryError("provider review verdict differs")
    verdict_index, verdict = nonblank[-1]

    standalone: list[tuple[int, str]] = []
    emphasized = re.compile(
        r"^(?:\*\*|__)?(READY TO FREEZE|READY AFTER SPECIFIED FIXES|"
        r"NOT READY TO FREEZE)(?:\*\*|__)?$"
    )
    for index, line in enumerate(lines):
        match = emphasized.fullmatch(line.strip())
        if match:
            standalone.append((index, match.group(1)))
    if standalone != [(verdict_index, verdict)]:
        raise AuditRecoveryError("provider review verdict is duplicated or conflicts")
    return verdict


def _provider_finding_headings(review_text: str) -> list[str]:
    lines = review_text.splitlines()
    identifiers: list[str] = []
    none_sections = 0
    for section, prefix in (
        ("# Blocking findings", "B"),
        ("# Important non-blocking findings", "I"),
    ):
        if lines.count(section) != 1:
            raise AuditRecoveryError("provider review finding section differs")
        start = lines.index(section) + 1
        end = next(
            (index for index in range(start, len(lines)) if lines[index].startswith("# ")),
            len(lines),
        )
        section_lines = [line for line in lines[start:end] if line.strip()]
        if section_lines == ["None."]:
            none_sections += 1
            continue
        section_identifiers: list[str] = []
        for line in section_lines:
            match = re.fullmatch(
                r"#{2,6}\s+([BI][0-9]{2})(?:\s*[:—-].*|\s+.*)?",
                line,
            )
            if match:
                if not match.group(1).startswith(prefix):
                    raise AuditRecoveryError(
                        "provider review finding section differs"
                    )
                section_identifiers.append(match.group(1))
        if not section_identifiers or "None." in section_lines:
            raise AuditRecoveryError("provider review finding section differs")
        identifiers.extend(section_identifiers)
    if not identifiers and none_sections != 2:
        raise AuditRecoveryError("provider review empty findings differ")
    if len(identifiers) != len(set(identifiers)):
        raise AuditRecoveryError("provider review finding IDs are duplicated")
    return identifiers


def _adjudication_decision_ids(
    decisions: Any, finding_ids: Any, provider_finding_ids: Sequence[str]
) -> list[str]:
    if (
        not isinstance(decisions, list)
        or not all(isinstance(row, Mapping) for row in decisions)
        or not isinstance(finding_ids, list)
        or not all(isinstance(finding_id, str) for finding_id in finding_ids)
    ):
        raise AuditRecoveryError("recovery adjudication decision coverage differs")
    if not provider_finding_ids:
        if decisions or finding_ids:
            raise AuditRecoveryError("recovery adjudication decision coverage differs")
        return []
    if not decisions:
        raise AuditRecoveryError("recovery adjudication decisions are empty")
    normalized = [str(row.get("finding_id")) for row in decisions]
    if (
        normalized != finding_ids
        or normalized != list(provider_finding_ids)
        or len(normalized) != len(set(normalized))
        or any(
            SAFE_ID.fullmatch(finding_id) is None
            or set(row) != {"finding_id", "disposition", "blocks_execution"}
            or row.get("blocks_execution") is not False
            or row.get("disposition")
            not in {"accept", "accepted_modified", "reject", "defer_nonblocking"}
            for finding_id, row in zip(normalized, decisions)
        )
    ):
        raise AuditRecoveryError("recovery adjudication decision coverage differs")
    return normalized


def _validated_review_cost(
    response: Mapping[str, Any], manifest: Mapping[str, Any]
) -> float:
    usage = response.get("usage")
    details = usage.get("input_tokens_details") if isinstance(usage, Mapping) else None
    try:
        input_tokens = int(usage["input_tokens"])
        output_tokens = int(usage["output_tokens"])
        cache_tokens = int((details or {}).get("cache_write_tokens") or 0)
        input_rate = float(manifest["input_rate_usd_per_million"])
        cache_rate = float(manifest["cache_write_rate_usd_per_million"])
        output_rate = float(manifest["output_rate_usd_per_million"])
        reported_cost = float(
            manifest["completed_response_cost_usd_conservative"]
        )
    except (KeyError, TypeError, ValueError, OverflowError) as exc:
        raise AuditRecoveryError("provider review usage/cost differs") from exc
    recomputed_cost = (
        input_tokens * input_rate
        + cache_tokens * cache_rate
        + output_tokens * output_rate
    ) / 1_000_000
    if (
        any(value < 0 for value in (input_tokens, output_tokens, cache_tokens))
        or not all(
            math.isfinite(value)
            for value in (input_rate, cache_rate, output_rate, reported_cost)
        )
        or input_rate != 5.0
        or cache_rate != 6.25
        or output_rate != 30.0
        or manifest.get("usage") != usage
        or not math.isclose(reported_cost, recomputed_cost, abs_tol=1e-12)
        or reported_cost > 1.25
    ):
        raise AuditRecoveryError("provider review usage/cost differs")
    return recomputed_cost


def _response_output_text(response: Mapping[str, Any]) -> str:
    parts: list[str] = []
    output = response.get("output")
    if not isinstance(output, list):
        raise AuditRecoveryError("provider response output differs")
    for item in output:
        if not isinstance(item, Mapping) or item.get("type") != "message":
            continue
        content = item.get("content")
        if not isinstance(content, list):
            continue
        for row in content:
            if (
                isinstance(row, Mapping)
                and row.get("type") == "output_text"
                and row.get("text")
            ):
                parts.append(str(row["text"]))
    if not parts:
        raise AuditRecoveryError("provider response has no output text")
    return "\n\n".join(parts).rstrip() + "\n"


def _validate_adjudication(
    path: Path,
    *,
    repo_root: Path,
    evidence_commit: str,
    final_commit: str,
) -> dict[str, Any]:
    candidate = path.expanduser().absolute()
    try:
        relative = candidate.relative_to(repo_root).as_posix()
    except ValueError as exc:
        raise AuditRecoveryError("recovery adjudication is outside the repository") from exc
    value, file_hash = _canonical_file(candidate, "recovery adjudication")
    receipt_hash = _self_hash(value, "recovery adjudication")
    _oid, frozen = _git_blob(repo_root, final_commit, relative)
    if frozen != candidate.read_bytes():
        raise AuditRecoveryError("recovery adjudication differs from final freeze")
    if relative != RECOVERY_ADJUDICATION_PATH:
        raise AuditRecoveryError("recovery adjudication path differs")

    review_root = repo_root / RECOVERY_REVIEW_ROOT
    artifact_paths = {
        "brief": review_root / "RECOVERY_PRO_REVIEW_BRIEF.md",
        "context": review_root / "RECOVERY_PRO_REVIEW_CONTEXT.md",
        "request": review_root / "RECOVERY_PRO_REVIEW_REQUEST.md",
        "payload": review_root / "RECOVERY_PRO_REVIEW_REQUEST_PAYLOAD.json",
        "response": review_root / "RECOVERY_PRO_REVIEW_RESPONSE.json",
        "review": review_root / "RECOVERY_PRO_REVIEW.md",
        "manifest": review_root / "RECOVERY_PRO_REVIEW_MANIFEST.json",
        "original_adjudication": repo_root / ORIGINAL_PLAN_ADJUDICATION_PATH,
    }
    raw = {
        role: _regular_bytes(artifact_path, f"recovery review {role}")
        for role, artifact_path in artifact_paths.items()
    }
    original, original_file_hash = _canonical_file(
        artifact_paths["original_adjudication"], "original plan adjudication"
    )
    original_receipt = _self_hash(original, "original plan adjudication")
    if (
        original_file_hash != EXPECTED_ORIGINAL_ADJUDICATION_FILE_SHA256
        or original_receipt != EXPECTED_ORIGINAL_ADJUDICATION_RECEIPT_SHA256
    ):
        raise AuditRecoveryError("original plan adjudication differs")

    payload, _payload_raw = _pretty_json(
        artifact_paths["payload"], "review request payload"
    )
    response, _response_raw = _pretty_json(
        artifact_paths["response"], "provider response"
    )
    manifest, _manifest_raw = _pretty_json(
        artifact_paths["manifest"], "review manifest"
    )
    review_artifacts = _review_input_artifacts(
        manifest,
        brief_path=artifact_paths["brief"],
        context_path=artifact_paths["context"],
    )
    try:
        brief_text = raw["brief"].decode("utf-8")
        context_text = raw["context"].decode("utf-8")
        request_text = raw["request"].decode("utf-8")
        review_text = raw["review"].decode("utf-8")
    except UnicodeError as exc:
        raise AuditRecoveryError("review text artifact is not UTF-8") from exc
    placeholder = re.compile(r"\[[A-Z][A-Z0-9_]{2,}\]")
    if placeholder.search(brief_text) or placeholder.search(context_text):
        raise AuditRecoveryError("review packet retains an unresolved placeholder")

    instructions = payload.get("instructions")
    review_input = payload.get("input")
    metadata = payload.get("metadata")
    reasoning = payload.get("reasoning")
    expected_review_input = _reconstruct_review_input(
        review_artifacts,
        brief_text=brief_text,
        context_text=context_text,
    )
    expected_metadata = {
        "workflow": "experiment_plan_review",
        "review_scope": "director_level_plan_review",
        "plan_sha256": hashlib.sha256(raw["brief"]).hexdigest(),
        "review_input_sha256": hashlib.sha256(
            expected_review_input.encode("utf-8")
        ).hexdigest(),
        "review_instructions_sha256": EXPECTED_REVIEW_INSTRUCTIONS_SHA256,
        "single_call_policy": "trusted_procedural_rule",
        "reviewed_packet_git_head_commit": evidence_commit,
    }
    expected_payload_fields = {
        "model",
        "reasoning",
        "instructions",
        "input",
        "max_output_tokens",
        "service_tier",
        "tools",
        "store",
        "truncation",
        "prompt_cache_options",
        "text",
        "metadata",
    }
    expected_request = (
        "# Developer instructions\n\n"
        + str(instructions).rstrip()
        + "\n\n"
        + str(review_input)
    )
    response_text = _response_output_text(response)
    response_id = response.get("id")
    response_model = response.get("model")
    response_metadata = response.get("metadata")
    provider_verdict = _provider_verdict(review_text)
    response_sha = hashlib.sha256(
        json.dumps(response, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()
    metadata_sha = hashlib.sha256(
        json.dumps(
            response_metadata,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
    ).hexdigest()
    if (
        set(payload) != expected_payload_fields
        or payload.get("model") != "gpt-5.6-sol"
        or reasoning
        != {"mode": "pro", "effort": RECOVERY_REVIEW_REASONING_EFFORT}
        or not isinstance(instructions, str)
        or hashlib.sha256(instructions.encode("utf-8")).hexdigest()
        != EXPECTED_REVIEW_INSTRUCTIONS_SHA256
        or not isinstance(review_input, str)
        or review_input != expected_review_input
        or metadata != expected_metadata
        or payload.get("max_output_tokens") != RECOVERY_REVIEW_MAX_OUTPUT_TOKENS
        or payload.get("service_tier") != "default"
        or payload.get("tools") != []
        or payload.get("store") is not False
        or payload.get("truncation") != "disabled"
        or payload.get("prompt_cache_options") != {"mode": "explicit"}
        or payload.get("text") != {"verbosity": "medium"}
        or request_text != expected_request
        or response.get("status") != "completed"
        or not isinstance(response_id, str)
        or not response_id.startswith("resp_")
        or response_model != "gpt-5.6-sol"
        or response_metadata != metadata
        or response.get("instructions") != instructions
        or response.get("max_output_tokens") != RECOVERY_REVIEW_MAX_OUTPUT_TOKENS
        or response.get("store") is not False
        or response.get("tools") != []
        or response_text != review_text
        or provider_verdict != "READY TO FREEZE"
        or manifest.get("status") != "completed"
        or manifest.get("model") != "gpt-5.6-sol"
        or manifest.get("official_latest_model") != "gpt-5.6-sol"
        or HEX64.fullmatch(str(manifest.get("latest_model_document_sha256", "")))
        is None
        or manifest.get("review_scope") != "director_level_plan_review"
        or manifest.get("reasoning") != reasoning
        or manifest.get("store") is not False
        or manifest.get("background") is not False
        or manifest.get("service_tier") != "default"
        or manifest.get("single_call_policy") != "trusted_procedural_rule"
        or manifest.get("global_uniqueness_attested") is not False
        or manifest.get("max_output_tokens") != RECOVERY_REVIEW_MAX_OUTPUT_TOKENS
        or manifest.get("budget_authorization_usd") != 1.25
        or manifest.get("response_id") != response_id
        or manifest.get("response_model") != response_model
        or manifest.get("response_metadata") != response_metadata
        or manifest.get("response_metadata_sha256") != metadata_sha
        or manifest.get("reviewed_packet_git_head_commit") != evidence_commit
        or manifest.get("review_request_sha256")
        != hashlib.sha256(raw["request"]).hexdigest()
        or manifest.get("request_payload_sha256")
        != hashlib.sha256(raw["payload"]).hexdigest()
        or manifest.get("response_sha256") != response_sha
        or manifest.get("review_sha256") != hashlib.sha256(raw["review"]).hexdigest()
        or manifest.get("review_input_sha256")
        != hashlib.sha256(review_input.encode("utf-8")).hexdigest()
        or manifest.get("review_instructions_sha256")
        != hashlib.sha256(instructions.encode("utf-8")).hexdigest()
        or not isinstance(manifest.get("completed_at_utc"), str)
        or not manifest["completed_at_utc"]
        or manifest.get("completed_response_cost_exceeded_budget_authorization")
        is not False
    ):
        raise AuditRecoveryError("provider review artifact chain differs")

    recomputed_cost = _validated_review_cost(response, manifest)

    decisions = value.get("decisions")
    finding_ids = value.get("review_finding_ids")
    provider_finding_ids = _provider_finding_headings(review_text)
    normalized_ids = _adjudication_decision_ids(
        decisions, finding_ids, provider_finding_ids
    )
    review_cost = value.get("review_cost_usd")
    expected_adjudication_fields = {
        "schema_version",
        "status",
        "study_id",
        "protocol_version",
        "provider_verdict",
        "review_model",
        "review_mode",
        "review_response_id",
        "review_cost_usd",
        "review_packet_outcome_inputs",
        "review_packet_raw_data_included",
        "review_finding_ids",
        "decisions",
        "unresolved_blockers",
        "review_response_file_sha256",
        "review_review_file_sha256",
        "review_manifest_file_sha256",
        "review_brief_file_sha256",
        "review_context_file_sha256",
        "receipt_sha256",
    }
    if (
        set(value) != expected_adjudication_fields
        or value.get("schema_version") != 1
        or value.get("status") != "adjudicated_ready_to_execute"
        or value.get("study_id") != protocol.STUDY_ID
        or value.get("protocol_version") != protocol.PROTOCOL_VERSION
        or value.get("provider_verdict") != provider_verdict
        or value.get("unresolved_blockers") != []
        or value.get("review_packet_outcome_inputs") != []
        or value.get("review_packet_raw_data_included") is not False
        or value.get("review_model") != "gpt-5.6-sol"
        or value.get("review_mode") != "pro"
        or not isinstance(value.get("review_response_id"), str)
        or not value["review_response_id"].startswith("resp_")
        or value["review_response_id"] != response_id
        or isinstance(review_cost, bool)
        or not isinstance(review_cost, (int, float))
        or not math.isfinite(float(review_cost))
        or not math.isclose(float(review_cost), recomputed_cost, abs_tol=1e-12)
        or not 0 <= float(review_cost) <= 1.25
        or value.get("review_response_file_sha256")
        != hashlib.sha256(raw["response"]).hexdigest()
        or value.get("review_review_file_sha256")
        != hashlib.sha256(raw["review"]).hexdigest()
        or value.get("review_manifest_file_sha256")
        != hashlib.sha256(raw["manifest"]).hexdigest()
        or value.get("review_brief_file_sha256")
        != hashlib.sha256(raw["brief"]).hexdigest()
        or value.get("review_context_file_sha256")
        != hashlib.sha256(raw["context"]).hexdigest()
    ):
        raise AuditRecoveryError("recovery adjudication is not execution-ready")
    return {
        "path": relative,
        "file_sha256": file_hash,
        "receipt_sha256": receipt_hash,
        "status": value["status"],
        "review_model": value.get("review_model"),
        "review_mode": value.get("review_mode"),
        "review_response_id": value.get("review_response_id"),
        "provider_verdict": value["provider_verdict"],
        "review_cost_usd": float(review_cost),
        "review_finding_ids": normalized_ids,
        "review_packet_outcome_inputs": [],
        "review_packet_raw_data_included": False,
        "review_response_file_sha256": value["review_response_file_sha256"],
        "review_review_file_sha256": value["review_review_file_sha256"],
        "review_manifest_file_sha256": value["review_manifest_file_sha256"],
        "review_brief_file_sha256": value["review_brief_file_sha256"],
        "review_context_file_sha256": value["review_context_file_sha256"],
        "original_plan_adjudication_receipt_sha256": original_receipt,
    }


def _strict_execution_path(
    value: Any, label: str, *, must_exist: bool
) -> Path:
    if not isinstance(value, str):
        raise AuditRecoveryError(f"recovery execution path is malformed: {label}")
    lexical = Path(value)
    if (
        not lexical.is_absolute()
        or lexical.as_posix() != value
        or any(part in {"", ".", ".."} for part in lexical.parts[1:])
    ):
        raise AuditRecoveryError(f"recovery execution path is noncanonical: {label}")
    current = Path(lexical.anchor)
    missing_seen = False
    for component in lexical.parts[1:]:
        current /= component
        try:
            details = current.lstat()
        except FileNotFoundError:
            if must_exist or current != lexical:
                raise AuditRecoveryError(
                    f"recovery execution path is missing: {label}"
                )
            missing_seen = True
            break
        except OSError as exc:
            raise AuditRecoveryError(
                f"recovery execution path is unreadable: {label}"
            ) from exc
        if stat.S_ISLNK(details.st_mode):
            raise AuditRecoveryError(
                f"recovery execution path contains a symlink: {label}"
            )
    if must_exist:
        try:
            resolved = lexical.resolve(strict=True)
        except OSError as exc:
            raise AuditRecoveryError(
                f"recovery execution path is missing: {label}"
            ) from exc
        if resolved != lexical:
            raise AuditRecoveryError(
                f"recovery execution path is noncanonical: {label}"
            )
    elif not missing_seen and lexical.is_symlink():
        raise AuditRecoveryError(
            f"recovery execution path contains a symlink: {label}"
        )
    return lexical


def _paths_overlap(left: Path, right: Path) -> bool:
    return left == right or left in right.parents or right in left.parents


def _validate_execution_paths(execution: Mapping[str, Any]) -> dict[str, Any]:
    fields = {
        "attempt_root",
        "output_directory",
        "attempt_marker",
        "failure_receipt",
        "plan_dir",
        "raw_root",
        "model_snapshot",
        "j_lens_path",
        "original_ownership",
        "original_guest",
        "original_cache",
        "original_authorization",
        "artifact_device",
    }
    if set(execution) != fields:
        raise AuditRecoveryError("recovery execution path schema differs")
    existing_fields = {
        "attempt_root",
        "plan_dir",
        "raw_root",
        "model_snapshot",
        "j_lens_path",
        "original_ownership",
        "original_guest",
        "original_cache",
        "original_authorization",
    }
    paths = {
        field: _strict_execution_path(
            execution[field], field, must_exist=field in existing_fields
        )
        for field in fields - {"artifact_device"}
    }
    attempt_root = paths["attempt_root"]
    output = paths["output_directory"]
    marker = paths["attempt_marker"]
    failure = paths["failure_receipt"]
    raw_root = paths["raw_root"]
    partial = output.with_name(f".{output.name}.partial")
    expired = output.with_name(f".{output.name}.expired")
    _strict_execution_path(partial.as_posix(), "partial output", must_exist=False)
    _strict_execution_path(expired.as_posix(), "expired output", must_exist=False)
    if (
        not attempt_root.is_dir()
        or not raw_root.is_dir()
        or output.parent != attempt_root
        or marker.parent != attempt_root
        or failure.parent != attempt_root
        or not attempt_root.name.startswith("audit_recovery_v4")
        or not output.name.startswith("audit_recovery_v4")
        or output.name.startswith(".")
        or marker.name != "ATTEMPT_CLAIMED.json"
        or failure.name != "RECOVERY_FAILED.json"
        or execution["artifact_device"] != "cuda:0"
        or any(
            _paths_overlap(raw_root, candidate)
            for candidate in (
                attempt_root,
                output,
                marker,
                failure,
                partial,
                expired,
            )
        )
    ):
        raise AuditRecoveryError("recovery output namespace differs")
    return dict(execution)


def build_recovery_authorization(
    *,
    code_freeze_commit: str,
    evidence_freeze_commit: str,
    final_freeze_commit: str,
    git_remote_ref: str,
    qualification_paths: Sequence[str],
    cumulative_review_paths: Sequence[str],
    recovery_adjudication_path: Path,
    fresh_ownership_path: Path,
    fresh_guest_path: Path,
    fresh_cache_path: Path,
    incident_evidence: Mapping[str, Path],
    execution: Mapping[str, Any],
    recovery_id: str,
    attempt_id: str,
    now_unix: float | None = None,
    repo_root: Path = REPO_ROOT,
    require_live_remote: bool = True,
) -> dict[str, Any]:
    """Build one short-lived authorization after the C/E/F freeze chain."""

    repo = repo_root.expanduser().resolve(strict=True)
    commits = (code_freeze_commit, evidence_freeze_commit, final_freeze_commit)
    if (
        any(HEX40.fullmatch(value) is None for value in commits)
        or len(set(commits)) != 3
        or SAFE_ID.fullmatch(recovery_id) is None
        or SAFE_ID.fullmatch(attempt_id) is None
    ):
        raise AuditRecoveryError("recovery identity or C/E/F commits are malformed")
    _require_ancestry(repo, code_freeze_commit, evidence_freeze_commit)
    _require_ancestry(repo, evidence_freeze_commit, final_freeze_commit)
    if set(cumulative_review_paths) != MANDATORY_CUMULATIVE_REVIEW_PATHS:
        raise AuditRecoveryError("cumulative review path set differs")
    _require_exact_freeze_chain(
        repo,
        code_commit=code_freeze_commit,
        evidence_commit=evidence_freeze_commit,
        final_commit=final_freeze_commit,
        qualification_paths=qualification_paths,
    )
    head = _git(repo, "rev-parse", "HEAD").stdout.strip()
    if head != final_freeze_commit:
        raise AuditRecoveryError("live checkout is not the final freeze commit")
    if not git_remote_ref.startswith("refs/heads/"):
        raise AuditRecoveryError("recovery remote ref is malformed")
    if require_live_remote:
        lines = _git(repo, "ls-remote", "origin", git_remote_ref).stdout.splitlines()
        if lines != [f"{final_freeze_commit}\t{git_remote_ref}"]:
            raise AuditRecoveryError("final freeze is not the live pushed remote")
    source_rows = _freeze_inventory(
        repo,
        first_commit=code_freeze_commit,
        final_commit=final_freeze_commit,
        paths=MANDATORY_C_SOURCE_TEST_INCIDENT_PATHS,
        label="source/test closure",
    )
    qualification_rows = _freeze_inventory(
        repo,
        first_commit=evidence_freeze_commit,
        final_commit=final_freeze_commit,
        paths=qualification_paths,
        label="qualification packet",
    )
    qualification_validation = _validate_qualification_evidence(
        qualification_rows,
        repo_root=repo,
        code_freeze_commit=code_freeze_commit,
    )
    review_rows = _final_inventory(
        repo,
        final_freeze_commit,
        cumulative_review_paths,
        "cumulative review packet",
    )
    if {str(row["path"]) for row in review_rows} != (
        MANDATORY_CUMULATIVE_REVIEW_PATHS
    ):
        raise AuditRecoveryError("cumulative review packet is incomplete")
    adjudication = _validate_adjudication(
        recovery_adjudication_path,
        repo_root=repo,
        evidence_commit=E3_QUALIFICATION_FREEZE_COMMIT,
        final_commit=final_freeze_commit,
    )
    if adjudication["path"] not in {row["path"] for row in review_rows}:
        raise AuditRecoveryError("cumulative review packet omits its adjudication")
    pod = _fresh_pod_binding(
        fresh_ownership_path, fresh_guest_path, fresh_cache_path
    )
    bound_execution = _validate_execution_paths(execution)
    incident = _incident_binding(
        raw_root=Path(str(bound_execution["raw_root"])),
        original_ownership=Path(str(bound_execution["original_ownership"])),
        original_guest=Path(str(bound_execution["original_guest"])),
        original_cache=Path(str(bound_execution["original_cache"])),
        original_authorization=Path(str(bound_execution["original_authorization"])),
        incident_evidence=incident_evidence,
    )
    if incident["original_pod_id"] == pod["pod_id"]:
        raise AuditRecoveryError("recovery must use a fresh pod")
    if qualification_validation["qualification_pod_id"] == pod["pod_id"]:
        raise AuditRecoveryError("qualification and recovery pods must be distinct")
    started = time.time() if now_unix is None else float(now_unix)
    deadline = started + RECOVERY_MAX_SECONDS
    if (
        not math.isfinite(started)
        or deadline > RECOVERY_CYCLE_DEADLINE_AT_UNIX
        or RECOVERY_MAX_SPEND_USD != 6.0
    ):
        raise AuditRecoveryError("recovery authority exceeds its frozen cycle")
    core = {
        "schema_version": 1,
        "status": "authorized_once_for_audit_only_recovery",
        "study_id": protocol.STUDY_ID,
        "protocol_version": protocol.PROTOCOL_VERSION,
        "recovery_protocol_version": RECOVERY_PROTOCOL_VERSION,
        "recovery_id": recovery_id,
        "attempt_id": attempt_id,
        "authorized_at_unix": started,
        "recovery_started_at_unix": started,
        "recovery_deadline_at_unix": deadline,
        "hourly_price_usd": 6.0,
        "max_spend_usd": RECOVERY_MAX_SPEND_USD,
        "code_freeze_commit": code_freeze_commit,
        "evidence_freeze_commit": evidence_freeze_commit,
        "final_freeze_commit": final_freeze_commit,
        "git_remote_ref": git_remote_ref,
        "git_live_remote_commit": final_freeze_commit,
        "source_test_files": source_rows,
        "source_test_inventory_sha256": protocol.canonical_sha256(source_rows),
        "qualification_files": qualification_rows,
        "qualification_inventory_sha256": protocol.canonical_sha256(
            qualification_rows
        ),
        "qualification_validation": qualification_validation,
        "cumulative_review_files": review_rows,
        "cumulative_review_inventory_sha256": protocol.canonical_sha256(
            review_rows
        ),
        "recovery_adjudication": adjudication,
        "fresh_pod": pod,
        "incident": incident,
        "execution": bound_execution,
    }
    return {**core, "receipt_sha256": protocol.canonical_sha256(core)}


def validate_recovery_authorization(
    receipt: Mapping[str, Any],
    *,
    repo_root: Path = REPO_ROOT,
    now_unix: float | None = None,
    require_live_remote: bool = False,
) -> dict[str, Any]:
    """Validate the exact C→E→F, review, pod, and incident closure."""

    if set(receipt) != RECOVERY_AUTHORIZATION_FIELDS:
        raise AuditRecoveryError("recovery authorization schema differs")
    _self_hash(receipt, "recovery authorization")
    repo = repo_root.expanduser().resolve(strict=True)
    code_commit = str(receipt["code_freeze_commit"])
    evidence_commit = str(receipt["evidence_freeze_commit"])
    final_commit = str(receipt["final_freeze_commit"])
    if (
        any(
            HEX40.fullmatch(value) is None
            for value in (code_commit, evidence_commit, final_commit)
        )
        or len({code_commit, evidence_commit, final_commit}) != 3
        or receipt.get("status") != "authorized_once_for_audit_only_recovery"
        or receipt.get("study_id") != protocol.STUDY_ID
        or receipt.get("protocol_version") != protocol.PROTOCOL_VERSION
        or receipt.get("recovery_protocol_version") != RECOVERY_PROTOCOL_VERSION
        or SAFE_ID.fullmatch(str(receipt.get("recovery_id", ""))) is None
        or SAFE_ID.fullmatch(str(receipt.get("attempt_id", ""))) is None
    ):
        raise AuditRecoveryError("recovery authorization identity differs")
    _require_ancestry(repo, code_commit, evidence_commit)
    _require_ancestry(repo, evidence_commit, final_commit)
    if (
        _git(repo, "rev-parse", "HEAD").stdout.strip() != final_commit
        or receipt.get("git_live_remote_commit") != final_commit
        or not str(receipt.get("git_remote_ref", "")).startswith("refs/heads/")
    ):
        raise AuditRecoveryError("recovery final-freeze checkout differs")
    if require_live_remote:
        ref = str(receipt["git_remote_ref"])
        lines = _git(repo, "ls-remote", "origin", ref).stdout.splitlines()
        if lines != [f"{final_commit}\t{ref}"]:
            raise AuditRecoveryError("recovery final freeze is not live remotely")
    source_rows = _validate_git_file_rows(
        receipt["source_test_files"],
        repo_root=repo,
        first_commit=code_commit,
        final_commit=final_commit,
        label="source/test closure",
    )
    if (
        tuple(str(row["path"]) for row in source_rows)
        != tuple(sorted(MANDATORY_C_SOURCE_TEST_INCIDENT_PATHS))
        or receipt["source_test_inventory_sha256"]
        != protocol.canonical_sha256(source_rows)
    ):
        raise AuditRecoveryError("source/test closure is incomplete")
    qualification_rows = _validate_git_file_rows(
        receipt["qualification_files"],
        repo_root=repo,
        first_commit=evidence_commit,
        final_commit=final_commit,
        label="qualification packet",
    )
    qualification_validation = _validate_qualification_evidence(
        qualification_rows,
        repo_root=repo,
        code_freeze_commit=code_commit,
    )
    _require_exact_freeze_chain(
        repo,
        code_commit=code_commit,
        evidence_commit=evidence_commit,
        final_commit=final_commit,
        qualification_paths=[str(row["path"]) for row in qualification_rows],
    )
    review_rows = _validate_git_file_rows(
        receipt["cumulative_review_files"],
        repo_root=repo,
        first_commit=None,
        final_commit=final_commit,
        label="cumulative review packet",
    )
    if {str(row["path"]) for row in review_rows} != (
        MANDATORY_CUMULATIVE_REVIEW_PATHS
    ):
        raise AuditRecoveryError("cumulative review packet is incomplete")
    if (
        receipt["qualification_inventory_sha256"]
        != protocol.canonical_sha256(qualification_rows)
        or receipt["cumulative_review_inventory_sha256"]
        != protocol.canonical_sha256(review_rows)
        or receipt["qualification_validation"] != qualification_validation
        or {str(row["path"]) for row in review_rows}
        != MANDATORY_CUMULATIVE_REVIEW_PATHS
    ):
        raise AuditRecoveryError("qualification/review inventory hash differs")
    adjudication_record = receipt["recovery_adjudication"]
    if not isinstance(adjudication_record, Mapping):
        raise AuditRecoveryError("recovery adjudication binding is missing")
    adjudication = _validate_adjudication(
        repo / str(adjudication_record.get("path")),
        repo_root=repo,
        evidence_commit=E3_QUALIFICATION_FREEZE_COMMIT,
        final_commit=final_commit,
    )
    if (
        adjudication_record != adjudication
        or adjudication["path"] not in {row["path"] for row in review_rows}
    ):
        raise AuditRecoveryError("recovery adjudication binding differs")
    pod_record = receipt["fresh_pod"]
    if not isinstance(pod_record, Mapping):
        raise AuditRecoveryError("fresh recovery pod binding is missing")
    pod = _fresh_pod_binding(
        Path(str(pod_record.get("ownership_path"))),
        Path(str(pod_record.get("guest_path"))),
        Path(str(pod_record.get("cache_path"))),
    )
    if (
        pod_record != pod
        or qualification_validation["qualification_pod_id"] == pod["pod_id"]
    ):
        raise AuditRecoveryError("fresh recovery pod binding differs")
    execution_record = receipt["execution"]
    if not isinstance(execution_record, Mapping):
        raise AuditRecoveryError("recovery execution binding is missing")
    execution = _validate_execution_paths(execution_record)
    incident_record = receipt["incident"]
    if not isinstance(incident_record, Mapping):
        raise AuditRecoveryError("recovery incident binding is missing")
    evidence_rows = incident_record.get("incident_evidence")
    evidence = _validate_physical_records(
        evidence_rows,
        label="incident evidence",
        required_roles={
            "original_audit_failure_log",
            "original_pod_termination_audit",
            "original_postdelete_inventory",
            "incident_closure",
            "incident_closure_schema",
            "incident_closure_verification",
            "recovery_cycle_ledger",
        },
    )
    incident = _incident_binding(
        raw_root=Path(str(execution["raw_root"])),
        original_ownership=Path(str(execution["original_ownership"])),
        original_guest=Path(str(execution["original_guest"])),
        original_cache=Path(str(execution["original_cache"])),
        original_authorization=Path(str(execution["original_authorization"])),
        incident_evidence={
            str(row["role"]): Path(str(row["path"])) for row in evidence
        },
    )
    if incident_record != incident or incident["original_pod_id"] == pod["pod_id"]:
        raise AuditRecoveryError("historical incident binding differs")
    now = time.time() if now_unix is None else float(now_unix)
    started = float(receipt["recovery_started_at_unix"])
    deadline = float(receipt["recovery_deadline_at_unix"])
    if (
        receipt["authorized_at_unix"] != started
        or receipt["hourly_price_usd"] != 6.0
        or receipt["max_spend_usd"] != RECOVERY_MAX_SPEND_USD
        or deadline - started != RECOVERY_MAX_SECONDS
        or deadline > RECOVERY_CYCLE_DEADLINE_AT_UNIX
        or not started <= now < deadline
    ):
        raise AuditRecoveryError("fresh recovery time/cost authority differs")
    return dict(receipt)


def validate_historical_original_receipts(
    *,
    audit_module: ModuleType,
    raw_root: Path,
    plan_dir: Path,
    original_ownership: Path,
    original_guest: Path,
    original_cache: Path,
    original_authorization: Path,
) -> dict[str, Any]:
    """Validate original receipts at run completion, never against wall clock now."""

    root = raw_root.expanduser().resolve(strict=True)
    complete = audit_module._manifest(root)  # noqa: SLF001
    plan, _plan_receipt = audit_module._audit_plan(plan_dir)  # noqa: SLF001
    if complete.get("plan_manifest_sha256") != plan.get("plan_manifest_sha256"):
        raise AuditRecoveryError("historical run/plan binding differs")
    audit_module._audit_runtime_and_binding(  # noqa: SLF001
        root, complete=complete, plan=plan
    )
    completed_at = float(complete["resource"]["run_completed_at_unix"])
    try:
        result = audit_module._audit_external_receipt_chain(  # noqa: SLF001
            ownership_path=original_ownership,
            guest_path=original_guest,
            cache_path=original_cache,
            authorization_path=original_authorization,
            plan_dir=plan_dir,
            plan=plan,
            execution_binding=audit_module._json(  # noqa: SLF001
                root / "execution_binding.json"
            ),
            complete=complete,
            now_unix=completed_at,
        )
    except audit_module.CalibrationAuditError as exc:
        raise AuditRecoveryError("historical original receipt chain differs") from exc
    core = {
        "status": "pass_original_receipts_at_historical_run_completion",
        "historical_validation_at_unix": completed_at,
        "run_receipt_sha256": complete["receipt_sha256"],
        "validation": result,
        "current_wall_clock_used_for_original_authorization": False,
    }
    return {**core, "receipt_sha256": protocol.canonical_sha256(core)}


@contextlib.contextmanager
def _private_frozen_audit_module() -> Iterator[ModuleType]:
    """Load the frozen auditor into an isolated module namespace."""

    source = Path(frozen_audit.__file__).resolve(strict=True)
    name = f"_signed_dose_frozen_audit_recovery_{uuid.uuid4().hex}"
    spec = importlib.util.spec_from_file_location(name, source)
    if spec is None or spec.loader is None:
        raise AuditRecoveryError("cannot isolate the frozen auditor")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
        yield module
    finally:
        sys.modules.pop(name, None)


def _bind_private_recovery_adapters(
    audit_module: ModuleType,
    *,
    recovery_authorization: Mapping[str, Any],
    historical_completed_at_unix: float,
    inventory_box: dict[str, Any],
) -> None:
    """Bind adapters only inside the isolated audit module."""

    class BoundRecoveryWatchdog(RecoveryWatchdog):
        def __init__(
            self,
            _historical_binding: Mapping[str, Any],
            *,
            audit_started_at_unix: float | None = None,
        ) -> None:
            super().__init__(
                recovery_authorization,
                audit_started_at_unix=audit_started_at_unix,
            )

    original_external = audit_module._audit_external_receipt_chain  # noqa: SLF001

    def historical_external(**kwargs: Any) -> dict[str, Any]:
        kwargs["now_unix"] = historical_completed_at_unix
        return original_external(**kwargs)

    def checkpoint_loader(
        j_lens_path: Path, watchdog: Any
    ) -> tuple[Path, Mapping[int, Any], dict[str, Any]]:
        path, maps, record, inventory = load_j_checkpoint_superset(
            j_lens_path, watchdog
        )
        if inventory_box:
            raise AuditRecoveryError("J-lens checkpoint was loaded more than once")
        inventory_box.update(inventory)
        return path, maps, record

    audit_module._AuditBudgetWatchdog = BoundRecoveryWatchdog  # noqa: SLF001
    audit_module._audit_external_receipt_chain = historical_external  # noqa: SLF001
    audit_module._load_j_checkpoint = checkpoint_loader  # noqa: SLF001


def _write_json_exclusive(path: Path, value: Mapping[str, Any]) -> None:
    payload = protocol.canonical_json_bytes(dict(value)) + b"\n"
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())


def _claim_attempt(authorization: Mapping[str, Any]) -> dict[str, Any]:
    execution = _validate_execution_paths(authorization["execution"])
    attempt_root = Path(execution["attempt_root"])
    output = Path(execution["output_directory"])
    marker_path = Path(execution["attempt_marker"])
    failure = Path(execution["failure_receipt"])
    partial = output.with_name(f".{output.name}.partial")
    expired = output.with_name(f".{output.name}.expired")
    if (
        not attempt_root.is_dir()
        or attempt_root.is_symlink()
        or any(
            os.path.lexists(path)
            for path in (output, marker_path, failure, partial, expired)
        )
    ):
        raise AuditRecoveryError("recovery attempt/output namespace is not fresh")
    now = time.time()
    if not (
        float(authorization["recovery_started_at_unix"])
        <= now
        < float(authorization["recovery_deadline_at_unix"])
    ):
        raise AuditRecoveryError("one-shot claim is outside recovery authority")
    core = {
        "schema_version": 1,
        "status": "claimed_exactly_once",
        "study_id": protocol.STUDY_ID,
        "recovery_protocol_version": RECOVERY_PROTOCOL_VERSION,
        "recovery_id": authorization["recovery_id"],
        "attempt_id": authorization["attempt_id"],
        "claimed_at_unix": now,
        "recovery_authorization_receipt_sha256": authorization["receipt_sha256"],
        "code_freeze_commit": authorization["code_freeze_commit"],
        "evidence_freeze_commit": authorization["evidence_freeze_commit"],
        "final_freeze_commit": authorization["final_freeze_commit"],
    }
    marker = {**core, "receipt_sha256": protocol.canonical_sha256(core)}
    _write_json_exclusive(marker_path, marker)
    return marker


def _write_failure(
    authorization: Mapping[str, Any], marker: Mapping[str, Any], error: BaseException
) -> None:
    path = Path(str(authorization["execution"]["failure_receipt"]))
    message = str(error)[:1_000]
    core = {
        "schema_version": 1,
        "status": "failed_no_compact_success_publication",
        "study_id": protocol.STUDY_ID,
        "recovery_protocol_version": RECOVERY_PROTOCOL_VERSION,
        "recovery_id": authorization["recovery_id"],
        "attempt_id": authorization["attempt_id"],
        "failed_at_unix": time.time(),
        "error_type": type(error).__name__,
        "error_message": message,
        "recovery_authorization_receipt_sha256": authorization["receipt_sha256"],
        "attempt_marker_receipt_sha256": marker["receipt_sha256"],
        "compact_success_directory_exists": Path(
            str(authorization["execution"]["output_directory"])
        ).exists(),
    }
    _write_json_exclusive(
        path, {**core, "receipt_sha256": protocol.canonical_sha256(core)}
    )


def _recovery_provenance(
    *,
    authorization: Mapping[str, Any],
    marker: Mapping[str, Any],
    historical_receipt_validation: Mapping[str, Any],
    pre_ledger: Mapping[str, Any],
    post_ledger: Mapping[str, Any],
    guards: Mapping[str, int],
    j_inventory: Mapping[str, Any],
) -> dict[str, Any]:
    if (
        pre_ledger["file_inventory_sha256"]
        != post_ledger["file_inventory_sha256"]
        or pre_ledger["directory_inventory_sha256"]
        != post_ledger["directory_inventory_sha256"]
        or pre_ledger["run_receipt_sha256"] != post_ledger["run_receipt_sha256"]
        or guards != ZERO_GUARD_COUNTS
    ):
        raise AuditRecoveryError("raw immutability or zero-forward recovery failed")
    predecessor_path = (
        REPO_ROOT
        / "experiments/consciousness_sae_target_blind_calibration/audit_recovery.py"
    )
    core = {
        "schema_version": 1,
        "status": "pass_audit_only_recovery_with_immutable_raw",
        "recovery_protocol_version": RECOVERY_PROTOCOL_VERSION,
        "recovery_id": authorization["recovery_id"],
        "attempt_id": authorization["attempt_id"],
        "recovery_authorization_receipt_sha256": authorization["receipt_sha256"],
        "attempt_marker_receipt_sha256": marker["receipt_sha256"],
        "code_freeze_commit": authorization["code_freeze_commit"],
        "evidence_freeze_commit": authorization["evidence_freeze_commit"],
        "final_freeze_commit": authorization["final_freeze_commit"],
        "source_test_inventory_sha256": authorization[
            "source_test_inventory_sha256"
        ],
        "qualification_inventory_sha256": authorization[
            "qualification_inventory_sha256"
        ],
        "cumulative_review_inventory_sha256": authorization[
            "cumulative_review_inventory_sha256"
        ],
        "recovery_adjudication": authorization["recovery_adjudication"],
        "fresh_pod": authorization["fresh_pod"],
        "incident": authorization["incident"],
        "recovery_campaign": {
            "started_at_unix": authorization["recovery_started_at_unix"],
            "deadline_at_unix": authorization["recovery_deadline_at_unix"],
            "hourly_price_usd": authorization["hourly_price_usd"],
            "max_spend_usd": authorization["max_spend_usd"],
        },
        "historical_original_receipt_validation": dict(
            historical_receipt_validation
        ),
        "pre_raw_tree_ledger": dict(pre_ledger),
        "post_raw_tree_ledger": dict(post_ledger),
        "raw_tree_unchanged": True,
        "zero_forward_guard_counts": dict(guards),
        "j_checkpoint_inventory": dict(j_inventory),
        "frozen_auditor_reference": {
            "path": Path(frozen_audit.__file__).resolve(strict=True).as_posix(),
            "sha256": protocol.sha256_file(Path(frozen_audit.__file__)),
        },
        "predecessor_recovery_reference_only": {
            "path": predecessor_path.relative_to(REPO_ROOT).as_posix(),
            "sha256": protocol.sha256_file(predecessor_path),
            "imported": False,
            "mutable_globals_used": False,
        },
        "fresh_model_execution_performed": False,
        "model_load_performed": False,
        "scientific_metrics_thresholds_layers_or_rows_changed": False,
        "target_prompt_render_count": 0,
        "target_feature_vector_count": 0,
    }
    return {**core, "receipt_sha256": protocol.canonical_sha256(core)}


def _enrich_outputs(
    audit_receipt: Mapping[str, Any],
    summary: Mapping[str, Any],
    provenance: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    audit_core = dict(audit_receipt)
    original_audit_hash = audit_core.pop("receipt_sha256", None)
    audit_core["recomputed_scientific_audit_receipt_sha256"] = original_audit_hash
    audit_core["recovery_provenance"] = dict(provenance)
    enriched_audit = {
        **audit_core,
        "receipt_sha256": protocol.canonical_sha256(audit_core),
    }
    summary_core = dict(summary)
    summary_core.pop("receipt_sha256", None)
    summary_core["audit_receipt_sha256"] = enriched_audit["receipt_sha256"]
    summary_core["recovery_provenance"] = dict(provenance)
    enriched_summary = {
        **summary_core,
        "receipt_sha256": protocol.canonical_sha256(summary_core),
    }
    return enriched_audit, enriched_summary


def publish_compact_atomic(
    *,
    authorization: Mapping[str, Any],
    audit_receipt: Mapping[str, Any],
    summary: Mapping[str, Any],
) -> Path:
    """Publish audit, summary, and completion marker in one directory rename."""

    output = Path(str(authorization["execution"]["output_directory"]))
    parent = output.parent
    partial = output.with_name(f".{output.name}.partial")
    expired = output.with_name(f".{output.name}.expired")
    if (
        not parent.is_dir()
        or parent.is_symlink()
        or any(os.path.lexists(path) for path in (output, partial, expired))
    ):
        raise AuditRecoveryError("compact recovery publication is not fresh")
    watchdog = RecoveryWatchdog(
        authorization,
        audit_started_at_unix=float(audit_receipt["audit_started_at_unix"]),
    )
    partial.mkdir(mode=0o700)
    published = False
    try:
        watchdog.check()
        audit_path = partial / "CALIBRATION_AUDIT.json"
        summary_path = partial / "CALIBRATION_SUMMARY.json"
        _write_json_exclusive(audit_path, audit_receipt)
        _write_json_exclusive(summary_path, summary)
        marker_core = {
            "schema_version": 1,
            "status": "complete_atomic_audit_only_recovery",
            "study_id": protocol.STUDY_ID,
            "protocol_version": protocol.PROTOCOL_VERSION,
            "recovery_protocol_version": RECOVERY_PROTOCOL_VERSION,
            "recovery_id": authorization["recovery_id"],
            "attempt_id": authorization["attempt_id"],
            "audit_receipt_sha256": audit_receipt["receipt_sha256"],
            "summary_receipt_sha256": summary["receipt_sha256"],
            "recovery_provenance_receipt_sha256": audit_receipt[
                "recovery_provenance"
            ]["receipt_sha256"],
            "audit_file_sha256": protocol.sha256_file(audit_path),
            "summary_file_sha256": protocol.sha256_file(summary_path),
            "publication_completed_at_unix": time.time(),
            "recovery_deadline_at_unix": authorization[
                "recovery_deadline_at_unix"
            ],
        }
        marker = {
            **marker_core,
            "receipt_sha256": protocol.canonical_sha256(marker_core),
        }
        _write_json_exclusive(partial / "PUBLICATION_COMPLETE.json", marker)
        directory_fd = os.open(partial, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
        watchdog.check()
        os.replace(partial, output)
        published = True
        parent_fd = os.open(parent, os.O_RDONLY)
        try:
            os.fsync(parent_fd)
        finally:
            os.close(parent_fd)
        watchdog.check()
        return output / "CALIBRATION_SUMMARY.json"
    except BaseException:
        if published and os.path.lexists(output):
            os.replace(output, expired)
        raise


def execute_recovery(authorization_path: Path) -> Path:
    """Run the frozen scientific auditor once under audit-only constraints."""

    raw_authorization, _file_hash = _canonical_file(
        authorization_path, "recovery authorization"
    )
    authorization = validate_recovery_authorization(raw_authorization)
    marker = _claim_attempt(authorization)
    execution = authorization["execution"]
    try:
        raw_root = Path(str(execution["raw_root"])).resolve(strict=True)
        run_complete, _ = _canonical_file(
            raw_root / "RUN_COMPLETE.json", "historical RUN_COMPLETE"
        )
        historical_completed = float(
            run_complete["resource"]["run_completed_at_unix"]
        )
        inventory: dict[str, Any] = {}
        with _private_frozen_audit_module() as isolated_audit:
            historical_validation = validate_historical_original_receipts(
                audit_module=isolated_audit,
                raw_root=raw_root,
                plan_dir=Path(str(execution["plan_dir"])),
                original_ownership=Path(str(execution["original_ownership"])),
                original_guest=Path(str(execution["original_guest"])),
                original_cache=Path(str(execution["original_cache"])),
                original_authorization=Path(
                    str(execution["original_authorization"])
                ),
            )
            pre_ledger = raw_tree_ledger(raw_root)
            _bind_private_recovery_adapters(
                isolated_audit,
                recovery_authorization=authorization,
                historical_completed_at_unix=historical_completed,
                inventory_box=inventory,
            )
            with zero_forward_guard() as guards:
                audit_receipt, summary = isolated_audit.audit(
                    raw_root,
                    Path(str(execution["plan_dir"])),
                    model_snapshot=Path(str(execution["model_snapshot"])),
                    j_lens_path=Path(str(execution["j_lens_path"])),
                    ownership_receipt=Path(str(execution["original_ownership"])),
                    guest_receipt=Path(str(execution["original_guest"])),
                    cache_receipt=Path(str(execution["original_cache"])),
                    authorization_receipt=Path(
                        str(execution["original_authorization"])
                    ),
                    artifact_device=str(execution["artifact_device"]),
                )
            post_ledger = raw_tree_ledger(raw_root)
        if not inventory:
            raise AuditRecoveryError("corrected J checkpoint inventory was not used")
        provenance = _recovery_provenance(
            authorization=authorization,
            marker=marker,
            historical_receipt_validation=historical_validation,
            pre_ledger=pre_ledger,
            post_ledger=post_ledger,
            guards=guards,
            j_inventory=inventory,
        )
        enriched_audit, enriched_summary = _enrich_outputs(
            audit_receipt, summary, provenance
        )
        return publish_compact_atomic(
            authorization=authorization,
            audit_receipt=enriched_audit,
            summary=enriched_summary,
        )
    except BaseException as exc:
        try:
            _write_failure(authorization, marker, exc)
        except BaseException as receipt_exc:
            raise AuditRecoveryError(
                f"recovery failed and failure receipt could not publish: {receipt_exc}"
            ) from exc
        raise


def _absolute_text(path: Path) -> str:
    return path.expanduser().absolute().as_posix()


def _issue_from_args(args: argparse.Namespace) -> Path:
    execution = {
        "attempt_root": _absolute_text(args.attempt_root),
        "output_directory": _absolute_text(args.output_directory),
        "attempt_marker": _absolute_text(args.attempt_root / "ATTEMPT_CLAIMED.json"),
        "failure_receipt": _absolute_text(args.attempt_root / "RECOVERY_FAILED.json"),
        "plan_dir": _absolute_text(args.plan_dir),
        "raw_root": _absolute_text(args.raw_root),
        "model_snapshot": _absolute_text(args.model_snapshot),
        "j_lens_path": _absolute_text(args.j_lens_path),
        "original_ownership": _absolute_text(args.original_ownership),
        "original_guest": _absolute_text(args.original_guest),
        "original_cache": _absolute_text(args.original_cache),
        "original_authorization": _absolute_text(args.original_authorization),
        "artifact_device": args.artifact_device,
    }
    incident_evidence = {
        "original_audit_failure_log": args.original_audit_failure_log,
        "original_pod_termination_audit": args.original_pod_termination_audit,
        "original_postdelete_inventory": args.original_postdelete_inventory,
        "incident_closure": args.incident_closure,
        "incident_closure_schema": args.incident_closure_schema,
        "incident_closure_verification": args.incident_closure_verification,
        "recovery_cycle_ledger": args.recovery_cycle_ledger,
    }
    receipt = build_recovery_authorization(
        code_freeze_commit=args.code_freeze_commit,
        evidence_freeze_commit=args.evidence_freeze_commit,
        final_freeze_commit=args.final_freeze_commit,
        git_remote_ref=args.git_remote_ref,
        qualification_paths=args.qualification_path,
        cumulative_review_paths=args.cumulative_review_path,
        recovery_adjudication_path=args.recovery_adjudication,
        fresh_ownership_path=args.fresh_ownership,
        fresh_guest_path=args.fresh_guest,
        fresh_cache_path=args.fresh_cache,
        incident_evidence=incident_evidence,
        execution=execution,
        recovery_id=args.recovery_id,
        attempt_id=args.attempt_id,
    )
    output = args.authorization_out.expanduser().absolute()
    if not output.parent.is_dir() or output.parent.is_symlink():
        raise AuditRecoveryError("authorization output parent differs")
    _write_json_exclusive(output, receipt)
    return output


def _add_issue_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--code-freeze-commit", required=True)
    parser.add_argument("--evidence-freeze-commit", required=True)
    parser.add_argument("--final-freeze-commit", required=True)
    parser.add_argument("--git-remote-ref", required=True)
    parser.add_argument("--qualification-path", action="append", required=True)
    parser.add_argument("--cumulative-review-path", action="append", required=True)
    parser.add_argument("--recovery-adjudication", type=Path, required=True)
    parser.add_argument("--fresh-ownership", type=Path, required=True)
    parser.add_argument("--fresh-guest", type=Path, required=True)
    parser.add_argument("--fresh-cache", type=Path, required=True)
    parser.add_argument("--original-audit-failure-log", type=Path, required=True)
    parser.add_argument("--original-pod-termination-audit", type=Path, required=True)
    parser.add_argument("--original-postdelete-inventory", type=Path, required=True)
    parser.add_argument("--incident-closure", type=Path, required=True)
    parser.add_argument("--incident-closure-schema", type=Path, required=True)
    parser.add_argument(
        "--incident-closure-verification", type=Path, required=True
    )
    parser.add_argument("--recovery-cycle-ledger", type=Path, required=True)
    parser.add_argument("--recovery-id", required=True)
    parser.add_argument("--attempt-id", required=True)
    parser.add_argument("--attempt-root", type=Path, required=True)
    parser.add_argument("--output-directory", type=Path, required=True)
    parser.add_argument("--plan-dir", type=Path, required=True)
    parser.add_argument("--raw-root", type=Path, required=True)
    parser.add_argument("--model-snapshot", type=Path, required=True)
    parser.add_argument("--j-lens-path", type=Path, required=True)
    parser.add_argument("--original-ownership", type=Path, required=True)
    parser.add_argument("--original-guest", type=Path, required=True)
    parser.add_argument("--original-cache", type=Path, required=True)
    parser.add_argument("--original-authorization", type=Path, required=True)
    parser.add_argument("--artifact-device", default="cuda:0")
    parser.add_argument("--authorization-out", type=Path, required=True)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    issue = commands.add_parser("issue", help="Issue one exact C/E/F authorization")
    _add_issue_arguments(issue)
    execute = commands.add_parser("execute", help="Run the one-shot audit recovery")
    execute.add_argument("--authorization", type=Path, required=True)
    validate = commands.add_parser("validate", help="Validate without claiming")
    validate.add_argument("--authorization", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "issue":
        print(_issue_from_args(args))
    elif args.command == "execute":
        print(execute_recovery(args.authorization))
    else:
        receipt, _ = _canonical_file(args.authorization, "recovery authorization")
        validated = validate_recovery_authorization(receipt)
        print(validated["receipt_sha256"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

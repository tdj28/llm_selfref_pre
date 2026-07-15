#!/usr/bin/env python3
"""Deterministically verify a retrieved audit-recovery bundle offline.

The verifier is intentionally standard-library-only and read-only with respect
to the retrieved attempt.  Its only write is an exclusive, self-hashed receipt
at the caller-supplied path outside the bundle.
"""

from __future__ import annotations

import argparse
import errno
import hashlib
import json
import math
import os
import re
import shlex
import stat
from datetime import datetime, timedelta, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Mapping, Sequence


AUTHORIZATION_RELATIVE = Path("RECOVERY_AUTHORIZATION.json")
BOOTSTRAP_MANIFEST_RELATIVE = Path("bootstrap/APPROVED_IMPORT_ROOTS.json")
PREFLIGHT_ENFORCEMENT_RELATIVE = Path("preflight/output/LANDLOCK_ENFORCEMENT.json")
PREFLIGHT_CUDA_RELATIVE = Path("preflight/output/LANDLOCK_CUDA_PREFLIGHT.json")
LOCAL_TEST_RELATIVE = Path("evidence/tests/LOCAL_TEST_RECEIPT.json")
TARGET_HOST_TEST_RELATIVE = Path("evidence/tests/TARGET_HOST_TEST_RECEIPT.json")
TARGET_QUALIFICATION_OWNERSHIP_RELATIVE = Path(
    "evidence/tests/TARGET_QUALIFICATION_OWNERSHIP.json"
)
TARGET_QUALIFICATION_LANDLOCK_RELATIVE = Path(
    "evidence/tests/TARGET_QUALIFICATION_LANDLOCK_ENFORCEMENT.json"
)
TARGET_QUALIFICATION_CUDA_RELATIVE = Path(
    "evidence/tests/TARGET_QUALIFICATION_LANDLOCK_CUDA_PREFLIGHT.json"
)
CONFINEMENT_RELATIVE = Path("output/LANDLOCK_ENFORCEMENT.json")
ATTEMPT_MARKER_RELATIVE = Path("output/ATTEMPT_STARTED.json")
FAILURE_RELATIVE = Path("output/FAILURE.json")
COMPACT_RELATIVE = Path("output/compact")
AUDIT_RELATIVE = COMPACT_RELATIVE / "CALIBRATION_AUDIT.json"
SUMMARY_RELATIVE = COMPACT_RELATIVE / "CALIBRATION_SUMMARY.json"
PUBLICATION_RELATIVE = COMPACT_RELATIVE / "PUBLICATION_COMPLETE.json"
COMPACT_FILE_NAMES = frozenset(
    {"CALIBRATION_AUDIT.json", "CALIBRATION_SUMMARY.json", "PUBLICATION_COMPLETE.json"}
)
REQUIRED_RECEIPT_PATHS = (
    AUTHORIZATION_RELATIVE,
    BOOTSTRAP_MANIFEST_RELATIVE,
    PREFLIGHT_ENFORCEMENT_RELATIVE,
    PREFLIGHT_CUDA_RELATIVE,
    LOCAL_TEST_RELATIVE,
    TARGET_HOST_TEST_RELATIVE,
    TARGET_QUALIFICATION_OWNERSHIP_RELATIVE,
    TARGET_QUALIFICATION_LANDLOCK_RELATIVE,
    TARGET_QUALIFICATION_CUDA_RELATIVE,
    CONFINEMENT_RELATIVE,
    ATTEMPT_MARKER_RELATIVE,
    AUDIT_RELATIVE,
    SUMMARY_RELATIVE,
    PUBLICATION_RELATIVE,
)

SCHEMA_VERSION = 1
STUDY_ID = "consciousness_sae_target_blind_calibration_v2"
PROTOCOL_VERSION = "consciousness_sae_target_blind_calibration_v2.0.0"
RECOVERY_PROTOCOL_VERSION = (
    "consciousness_sae_target_blind_calibration_v2.audit_recovery_r3"
)
RUN_ID = "calv2-r3-1a16572-20260715T002344Z"
ORIGINAL_RUN_RECEIPT_SHA256 = (
    "bab48b452c7e7c5b9db5d09ecc34c7e530813e2f5093aff1b8a8152017e4695d"
)
PLAN_MANIFEST_SHA256 = (
    "aa80cef7ef36fed327fcce99547c0b3bdf92a059c1dea43abba0ba924f404636"
)
ORIGINAL_RAW_LEDGER_SHA256 = (
    "7bffb6306b67814d2f4618b6aaf4f243ab2992d7b6b92ebb955a370654e0a20c"
)
ORIGINAL_FAILURE_LOG_SHA256 = (
    "a5936d0fda01b96f193a1ab40c9d7c52dc751ecdf3686896e26d2d3951cdd86f"
)
ORIGINAL_CAMPAIGN_STARTED_AT_UNIX = 1_784_074_604.0
ORIGINAL_CAMPAIGN_DEADLINE_AT_UNIX = 1_784_080_004.0
ORIGINAL_CAMPAIGN_HOURLY_PRICE_USD = 6.0
COMPLETED_REVIEW_COST_CEILING_USD = 25.0
ORIGINAL_RECEIPTS = {
    "ownership": "2aaa6e9e665f511ccfe363eee9deb5496c36bc8b2ae2b7ac67620a58abe914ca",
    "guest": "226e939db167bc3471c4b559aaa2f454ea3fa0cfa51a0f73d378ced11fe33b26",
    "cache": "fa91d5a98475711a4a939b65dd5656a76dcda05eb92e8dfb0dffe9dcd5931c77",
    "authorization": "9f44dfdf1820bb1e359e962925e9dffd13fcd13d4b88fffa72fa1226ddda0033",
    "termination_audit": (
        "b346b5c575ba1a903d93874b6dea58101cd208539ef5e30e8d069955d864ebfd"
    ),
    "frozen_termination": (
        "86d0efdcf0b54b927bd3062ff448d0abf3d12aa873c837766249e1b7a110dfe5"
    ),
}
SUPERSEDED_RECOVERY_POD_ID = "faz2t3bcrdwymn"
SUPERSEDED_RECOVERY_ATTEMPT_ID = "calv2-r3-audit-recovery-e0dd9a6-20260715T015420Z"
SUPERSEDED_RUNTIME_BLOCK_SHA256 = (
    "bf8ddbb31b3ddab99c2126d1100691f8d0878c1a0d1d4a091776e5d3f2bc207d"
)
SUPERSEDED_TERMINATION_AUDIT_SHA256 = (
    "a7fa432b64f594926fac22070a59c5081e68e8a4cc230ae4a2ffc0032dd30300"
)
SUPERSEDED_FROZEN_TERMINATION_SHA256 = (
    "0bc9fd91dc816e70e95809da50b667cb67bc6b0674d7b4c84415b3287bbebbd0"
)
SUPERSEDED_POSTDELETE_INVENTORY_SHA256 = (
    "7d0c31b4830fdedad2e985e28168418a86483241ced2bd415d45ff12eecf1d06"
)
SUPERSEDED_RECOVERY_HOST = {
    "status": "validated_superseded_preclaim_recovery_host",
    "pod_id": SUPERSEDED_RECOVERY_POD_ID,
    "attempt_id": SUPERSEDED_RECOVERY_ATTEMPT_ID,
    "audit_execute_invoked": False,
    "attempt_marker_present": False,
    "runtime_block_receipt_sha256": SUPERSEDED_RUNTIME_BLOCK_SHA256,
    "termination_audit_receipt_sha256": SUPERSEDED_TERMINATION_AUDIT_SHA256,
    "frozen_termination_receipt_sha256": SUPERSEDED_FROZEN_TERMINATION_SHA256,
    "postdelete_inventory_receipt_sha256": (SUPERSEDED_POSTDELETE_INVENTORY_SHA256),
}
SUPERSEDED_EXTERNAL_KEYS = (
    "superseded_runtime_block",
    "superseded_termination_audit",
    "superseded_frozen_termination",
    "superseded_postdelete_inventory",
)
RAW_RELATIVE = (
    "consciousness_sae_target_blind_calibration/"
    "consciousness_sae_target_blind_calibration_v2/raw/" + RUN_ID
)
RECOVERY_ATTEMPT_PARENT = (
    "/workspace/consciousness_sae_target_blind_calibration/"
    "consciousness_sae_target_blind_calibration_v2/audit_recovery_attempts"
)
MODEL_SNAPSHOT_PATH = (
    "/workspace/consciousness_readout_validation/"
    "consciousness_readout_validation_v1/public_artifacts/model_snapshot"
)
J_LENS_PATH = (
    "/workspace/consciousness_readout_validation/"
    "consciousness_readout_validation_v1/public_artifacts/jlens/"
    "Llama-3.3-70B-Instruct_jacobian_lens.pt"
)
CANONICAL_PLAN_RELATIVE_PATH = (
    "data/consciousness_sae_target_blind_calibration/calibration_v2_plan_20260714_r3"
)
NETWORK_VOLUME_ID = "bv9gb9j32y"
DATA_CENTER_ID = "US-CA-2"
GPU_TYPE = "NVIDIA B200"
BOOTSTRAP_RELATIVE_PATH = (
    "experiments/consciousness_sae_target_blind_calibration/confined_bootstrap.py"
)
BOOTSTRAP_MANIFEST_STATUS = "approved_exact_python_import_roots"
BOOTSTRAP_GUARDED_MODULES = (
    "torch.nn.modules.module",
    "transformers.modeling_utils",
    "transformers.models.auto.auto_factory",
)
BOOTSTRAP_PREFLIGHT_PHASE = (
    "after_hash_bound_guard_priming_before_preflight_publication"
)
BOOTSTRAP_EXECUTE_ENTRY_PHASE = (
    "after_hash_bound_guard_priming_before_recovery_validation"
)
BOOTSTRAP_PREPUBLICATION_PHASE = "after_guarded_audit_before_compact_publication"
TEST_RECEIPT_TYPE = "audit_recovery_test_receipt_v1"
TEST_RECEIPT_STATUS = "pass_exact_code_freeze_tests"
FOCUSED_TEST_PATHS = (
    "tests/consciousness_sae_target_blind_calibration/test_audit_recovery.py",
    "tests/consciousness_sae_target_blind_calibration/test_confined_bootstrap.py",
    "tests/consciousness_sae_target_blind_calibration/test_landlock_launcher.py",
    "tests/consciousness_sae_target_blind_calibration/test_recovery_bundle_verifier.py",
    "tests/consciousness_sae_target_blind_calibration/test_scientific_equivalence.py",
)
FOCUSED_PYTEST_ARGV = ("-q", *FOCUSED_TEST_PATHS)
TARGET_DESIGNATED_TEST_IDS = (
    "tests/consciousness_sae_target_blind_calibration/test_landlock_launcher.py::"
    "test_linux_launcher_enforces_policy_and_same_pid_exec",
)
TARGET_QUALIFICATION_LANDLOCK_NAME = "TARGET_QUALIFICATION_LANDLOCK_ENFORCEMENT.json"
TARGET_QUALIFICATION_CUDA_NAME = "TARGET_QUALIFICATION_LANDLOCK_CUDA_PREFLIGHT.json"
TARGET_QUALIFICATION_OWNERSHIP_NAME = "TARGET_QUALIFICATION_OWNERSHIP.json"
PREFLIGHT_CLOSURE_SCOPES = ("final_recovery", "source_test_qualification")

OWNERSHIP_POD_NAME_PREFIX = "consciousness-sae-realization-validation-v1-"
OWNERSHIP_PROVIDER_VOLUME_SIZE_BYTES = 500 * 1000**3
OWNERSHIP_MAX_TOTAL_SECONDS = 6 * 3600
OWNERSHIP_FIELDS = frozenset(
    {
        "schema_version",
        "status",
        "study_id",
        "protocol_version",
        "pod_id",
        "pod_name",
        "ownership_nonce",
        "network_volume_id",
        "provider_volume_size_bytes",
        "data_center_id",
        "gpu_type",
        "gpu_count",
        "volume_mount_path",
        "created_at",
        "terminate_after",
        "create_contract_sha256",
        "upstream_lifecycle_receipt_sha256",
        "provider_container_image_attestation",
        "desired_status",
        "locked",
        "precreate_unrelated_pod_count",
        "precreate_unrelated_inventory_sha256",
        "receipt_sha256",
    }
)
OWNERSHIP_IMAGE_IMMUTABLE_REFERENCE = (
    "runpod/pytorch@sha256:"
    "cb154fcca15d1d6ce858cfa672b76505e30861ef981d28ec94bd44168767d853"
)
OWNERSHIP_STUDY_ID = "consciousness_sae_realization_validation_v1"
OWNERSHIP_PROTOCOL_VERSION = "consciousness_sae_realization_validation_v1.0.0"

HISTORICAL_INCOMPLETE_REVIEW_DIRECTORY = (
    "docs/consciousness_sae_target_blind_calibration/reviews/"
    "audit_recovery_landlock_gpt_pro_20260715_live"
)
HISTORICAL_INCOMPLETE_REVIEW_ADJUDICATION_JSON = (
    "docs/consciousness_sae_target_blind_calibration/reviews/"
    "AUDIT_RECOVERY_LANDLOCK_GPT_PRO_ADJUDICATION.json"
)
HISTORICAL_INCOMPLETE_REVIEW_ADJUDICATION_MARKDOWN = (
    "docs/consciousness_sae_target_blind_calibration/reviews/"
    "AUDIT_RECOVERY_LANDLOCK_GPT_PRO_ADJUDICATION.md"
)
HISTORICAL_INCOMPLETE_REVIEW_BUDGET_INCIDENT = (
    f"{HISTORICAL_INCOMPLETE_REVIEW_DIRECTORY}/BUDGET_INCIDENT.json"
)
HISTORICAL_INCOMPLETE_REVIEW_PHYSICAL_SHA256 = {
    HISTORICAL_INCOMPLETE_REVIEW_ADJUDICATION_JSON: (
        "96fad9342ebe064357ac6e06fd26de1fb11209aa713e12805180f81316bced1a"
    ),
    HISTORICAL_INCOMPLETE_REVIEW_ADJUDICATION_MARKDOWN: (
        "87c76f756db4dd90f69e7ceda55cf8f4ecd729f473cb40fdb887fcb711ccbcbc"
    ),
    HISTORICAL_INCOMPLETE_REVIEW_BUDGET_INCIDENT: (
        "b7610eee2578297644c6606aa0d87d31391c24c6b44c857862024c445ebefdee"
    ),
    f"{HISTORICAL_INCOMPLETE_REVIEW_DIRECTORY}/failure.json": (
        "2cf4f10787b4c56c4709b4444fccb48aa7fe09ef7c85f860da0436625f2733c4"
    ),
    f"{HISTORICAL_INCOMPLETE_REVIEW_DIRECTORY}/request_payload.json": (
        "ad251876f0651dbf76d23d1cf8d60b6b66eaf22d56c2f26671158104e6e8324b"
    ),
    f"{HISTORICAL_INCOMPLETE_REVIEW_DIRECTORY}/response.json": (
        "230e5147347a9c035244b8f3a2750c2545c5f108ac1aa09747ec70993c006bfc"
    ),
    f"{HISTORICAL_INCOMPLETE_REVIEW_DIRECTORY}/review_manifest.json": (
        "86a3387f8f96ffb18f885ed26b926cca55aae7c8cca22266749bf134ff1b50f6"
    ),
    f"{HISTORICAL_INCOMPLETE_REVIEW_DIRECTORY}/review_request.md": (
        "e7d4c2f239ba21b99b7ffa0c43b1d71aee785fd7dfc1fa89a748ab5820fe4e39"
    ),
}
HISTORICAL_V2_PRO_REVIEW_DIRECTORY = (
    "docs/consciousness_sae_target_blind_calibration/reviews/"
    "audit_recovery_landlock_gpt_pro_v2_completed"
)
HISTORICAL_V2_PRO_REVIEW_ADJUDICATION_JSON = (
    "docs/consciousness_sae_target_blind_calibration/reviews/"
    "AUDIT_RECOVERY_LANDLOCK_GPT_PRO_V2_ADJUDICATION.json"
)
HISTORICAL_V2_PRO_REVIEW_ADJUDICATION_MARKDOWN = (
    "docs/consciousness_sae_target_blind_calibration/reviews/"
    "AUDIT_RECOVERY_LANDLOCK_GPT_PRO_V2_ADJUDICATION.md"
)
HISTORICAL_V2_PRO_REVIEW_PHYSICAL_SHA256 = {
    HISTORICAL_V2_PRO_REVIEW_ADJUDICATION_JSON: (
        "6e404501248a9e9a13b46cc75bc58ab40276c617001a87c60dd14a6c1627f81d"
    ),
    HISTORICAL_V2_PRO_REVIEW_ADJUDICATION_MARKDOWN: (
        "abacd1ca2bd3612ebc6123b650a15734bbf68953d23a1934101a0c1ff86c6f72"
    ),
    f"{HISTORICAL_V2_PRO_REVIEW_DIRECTORY}/request_payload.json": (
        "2432f67d32fb77384b4dd6a7276ca977365e30a1463c9e7e0bd53aa961de78ed"
    ),
    f"{HISTORICAL_V2_PRO_REVIEW_DIRECTORY}/response.json": (
        "e9878bb589158162b38d6cc1ea2791aebfb73b0ffb8fc9f68a7e9811669cc682"
    ),
    f"{HISTORICAL_V2_PRO_REVIEW_DIRECTORY}/review.md": (
        "8d0effb94420c3c611113eb31c3932add9e1af6094c88d92f1a3ab5fea05f736"
    ),
    f"{HISTORICAL_V2_PRO_REVIEW_DIRECTORY}/review_manifest.json": (
        "28787f7b44c3b678fdd16a6748f5f2fbe9729a6873d775990a0fd547c93d5823"
    ),
    f"{HISTORICAL_V2_PRO_REVIEW_DIRECTORY}/review_request.md": (
        "a9b38b175c11637b2314916a9183bea78761a4c1235b91781745b3b3eed982d6"
    ),
}
HISTORICAL_V2_ADJUDICATION_RECEIPT_SHA256 = (
    "48dbbce43125972eacb123d624e420759666ffc02cd51e48cd6eff92c1487c8a"
)
FINAL_V3_PRO_REVIEW_DIRECTORY = (
    "docs/consciousness_sae_target_blind_calibration/reviews/"
    "audit_recovery_landlock_gpt_pro_v3_completed"
)
FINAL_V3_PRO_REVIEW_ADJUDICATION_JSON = (
    "docs/consciousness_sae_target_blind_calibration/reviews/"
    "AUDIT_RECOVERY_LANDLOCK_GPT_PRO_V3_ADJUDICATION.json"
)
FINAL_V3_PRO_REVIEW_ADJUDICATION_MARKDOWN = (
    "docs/consciousness_sae_target_blind_calibration/reviews/"
    "AUDIT_RECOVERY_LANDLOCK_GPT_PRO_V3_ADJUDICATION.md"
)
V3_REVIEW_INPUT_DIRECTORY = (
    "docs/consciousness_sae_target_blind_calibration/reviews/"
    "audit_recovery_landlock_gpt_pro_v3_inputs"
)
V3_LOCAL_TEST_RECEIPT_SNAPSHOT = f"{V3_REVIEW_INPUT_DIRECTORY}/LOCAL_TEST_RECEIPT.json"
V3_TARGET_HOST_TEST_RECEIPT_SNAPSHOT = (
    f"{V3_REVIEW_INPUT_DIRECTORY}/TARGET_HOST_TEST_RECEIPT.json"
)
V3_TARGET_QUALIFICATION_OWNERSHIP_SNAPSHOT = (
    f"{V3_REVIEW_INPUT_DIRECTORY}/TARGET_QUALIFICATION_OWNERSHIP.json"
)
V3_TARGET_QUALIFICATION_LANDLOCK_SNAPSHOT = (
    f"{V3_REVIEW_INPUT_DIRECTORY}/TARGET_QUALIFICATION_LANDLOCK_ENFORCEMENT.json"
)
V3_TARGET_QUALIFICATION_CUDA_SNAPSHOT = (
    f"{V3_REVIEW_INPUT_DIRECTORY}/TARGET_QUALIFICATION_LANDLOCK_CUDA_PREFLIGHT.json"
)
RECOVERY_BOUND_PATHS = tuple(
    sorted(
        {
            "experiments/__init__.py",
            "experiments/consciousness_sae_realization_validation/__init__.py",
            "experiments/consciousness_sae_realization_validation/protocol.py",
            "experiments/consciousness_sae_realization_validation/runpod_preflight.py",
            (
                "experiments/consciousness_sae_realization_validation/"
                "legacy_public_artifact_manifest.json"
            ),
            "experiments/consciousness_sae_target_blind_calibration/__init__.py",
            "experiments/consciousness_sae_target_blind_calibration/protocol.py",
            "experiments/consciousness_sae_target_blind_calibration/build_plan.py",
            (
                "experiments/consciousness_sae_target_blind_calibration/"
                "review_adjudication.py"
            ),
            "experiments/consciousness_sae_target_blind_calibration/validate_plan.py",
            "experiments/consciousness_sae_target_blind_calibration/orientation.py",
            "experiments/consciousness_sae_target_blind_calibration/authorize.py",
            "experiments/consciousness_sae_target_blind_calibration/audit.py",
            (
                "experiments/consciousness_sae_target_blind_calibration/"
                "audit_runtime_shim.py"
            ),
            "experiments/consciousness_sae_target_blind_calibration/audit_recovery.py",
            (
                "experiments/consciousness_sae_target_blind_calibration/"
                "confined_bootstrap.py"
            ),
            (
                "experiments/consciousness_sae_target_blind_calibration/"
                "scientific_equivalence.py"
            ),
            (
                "experiments/consciousness_sae_target_blind_calibration/"
                "landlock_launcher.py"
            ),
            (
                "experiments/consciousness_sae_target_blind_calibration/"
                "recovery_bundle_verifier.py"
            ),
            (
                "experiments/consciousness_sae_target_blind_calibration/"
                "requirements-runpod-b200.txt"
            ),
            (
                "experiments/consciousness_sae_target_blind_calibration/"
                "setup_runpod_guest.sh"
            ),
            (
                "docs/consciousness_sae_target_blind_calibration/"
                "AUDIT_RECOVERY_20260714.md"
            ),
            (
                "docs/consciousness_sae_target_blind_calibration/"
                "AUDIT_RECOVERY_REVIEW_CONTEXT.md"
            ),
            (
                "docs/consciousness_sae_target_blind_calibration/"
                "AUDIT_RECOVERY_SCIENTIFIC_EQUIVALENCE.json"
            ),
            (
                "docs/consciousness_sae_target_blind_calibration/"
                "AUDIT_RECOVERY_SCIENTIFIC_EQUIVALENCE.md"
            ),
            *HISTORICAL_INCOMPLETE_REVIEW_PHYSICAL_SHA256,
            *HISTORICAL_V2_PRO_REVIEW_PHYSICAL_SHA256,
            FINAL_V3_PRO_REVIEW_ADJUDICATION_JSON,
            FINAL_V3_PRO_REVIEW_ADJUDICATION_MARKDOWN,
            f"{FINAL_V3_PRO_REVIEW_DIRECTORY}/request_payload.json",
            f"{FINAL_V3_PRO_REVIEW_DIRECTORY}/response.json",
            f"{FINAL_V3_PRO_REVIEW_DIRECTORY}/review.md",
            f"{FINAL_V3_PRO_REVIEW_DIRECTORY}/review_manifest.json",
            f"{FINAL_V3_PRO_REVIEW_DIRECTORY}/review_request.md",
            V3_LOCAL_TEST_RECEIPT_SNAPSHOT,
            V3_TARGET_HOST_TEST_RECEIPT_SNAPSHOT,
            V3_TARGET_QUALIFICATION_OWNERSHIP_SNAPSHOT,
            V3_TARGET_QUALIFICATION_LANDLOCK_SNAPSHOT,
            V3_TARGET_QUALIFICATION_CUDA_SNAPSHOT,
            "tests/consciousness_sae_target_blind_calibration/test_audit_recovery.py",
            (
                "tests/consciousness_sae_target_blind_calibration/"
                "test_confined_bootstrap.py"
            ),
            (
                "tests/consciousness_sae_target_blind_calibration/"
                "test_landlock_launcher.py"
            ),
            (
                "tests/consciousness_sae_target_blind_calibration/"
                "test_recovery_bundle_verifier.py"
            ),
            (
                "tests/consciousness_sae_target_blind_calibration/"
                "test_scientific_equivalence.py"
            ),
        }
    )
)
SOURCE_TEST_BOUND_PATHS = tuple(
    path
    for path in RECOVERY_BOUND_PATHS
    if path.startswith("experiments/") or path.startswith("tests/")
)
EXTERNAL_FILE_KEYS = frozenset(
    {
        "run_complete",
        "raw_ledger",
        "raw_inventory",
        "failure_log",
        "original_ownership",
        "original_guest",
        "original_cache",
        "original_authorization",
        "termination_audit",
        "postdelete_inventory",
        "frozen_termination",
        "superseded_runtime_block",
        "superseded_termination_audit",
        "superseded_frozen_termination",
        "superseded_postdelete_inventory",
        "fresh_ownership",
        "fresh_guest",
        "fresh_cache",
        "preflight_landlock",
        "preflight_probe",
        "local_test_receipt",
        "target_host_test_receipt",
        "target_qualification_ownership",
        "target_qualification_landlock",
        "target_qualification_cuda_preflight",
        "roots_manifest",
    }
)

POLICY_ABI = 4
HANDLED_ACCESS_FS = 0x7FF2
OUTPUT_ALLOWED_ACCESS_FS = 0x1B2
DEVICE_ALLOWED_ACCESS_FS = 0x2
PROC_SELF_TASK_ALLOWED_ACCESS_FS = 0x4002
PROC_SELF_TASK_PATH = "/proc/self/task"
LANDLOCK_POLICY = {
    "mechanism": "linux_landlock",
    "required_abi": POLICY_ABI,
    "handled_access_fs": HANDLED_ACCESS_FS,
    "handled_access_fs_names": [
        "write_file",
        "remove_dir",
        "remove_file",
        "make_char",
        "make_dir",
        "make_reg",
        "make_sock",
        "make_fifo",
        "make_block",
        "make_sym",
        "refer",
        "truncate",
    ],
    "output_allowed_access_fs": OUTPUT_ALLOWED_ACCESS_FS,
    "output_allowed_access_fs_names": [
        "write_file",
        "remove_dir",
        "remove_file",
        "make_dir",
        "make_reg",
    ],
    "rule_type": "path_beneath",
    "directory_rule_count": 3,
    "device_rule_access_fs": DEVICE_ALLOWED_ACCESS_FS,
    "device_rule_access_fs_name": "write_file",
    "write_allowed_directories": [
        "execution.paths.output_root",
        "execution.paths.canary_output_root",
    ],
    "proc_self_task_allowed_access_fs": PROC_SELF_TASK_ALLOWED_ACCESS_FS,
    "proc_self_task_allowed_access_fs_names": ["write_file", "truncate"],
    "proc_self_task_rule_path": PROC_SELF_TASK_PATH,
    "proc_self_task_exception_scope": (
        "WRITE_FILE|TRUNCATE on all descendants; required for CUDA thread naming"
    ),
    "device_write_exceptions": "execution.device_files",
    "raw_and_provenance_write_access": "default_denied",
    "metadata_and_device_ioctl_outside_claim": True,
}

EXPECTED_PACKAGES = {
    "numpy": "2.2.6",
    "safetensors": "0.8.0",
    "tokenizers": "0.22.2",
    "torch": "2.8.0.dev20250319+cu128",
    "transformers": "4.57.6",
}
EXPECTED_IMPORTED_PACKAGES = {
    name: EXPECTED_PACKAGES[name]
    for name in ("numpy", "safetensors", "torch", "transformers")
}
FIXED_ENVIRONMENT = {
    "LANG": "C",
    "LC_ALL": "C",
    "PYTHONDONTWRITEBYTECODE": "1",
    "PYTHONNOUSERSITE": "1",
    "CUDA_CACHE_DISABLE": "1",
    "HF_HUB_OFFLINE": "1",
    "TRANSFORMERS_OFFLINE": "1",
    "HF_DATASETS_OFFLINE": "1",
    "TOKENIZERS_PARALLELISM": "false",
}
DYNAMIC_ENVIRONMENT = (
    "HOME",
    "TMPDIR",
    "HF_HOME",
    "TRANSFORMERS_CACHE",
    "XDG_CACHE_HOME",
    "TORCH_HOME",
    "PIP_CACHE_DIR",
    "NUMBA_CACHE_DIR",
    "CUDA_CACHE_PATH",
    "TRITON_CACHE_DIR",
    "TORCHINDUCTOR_CACHE_DIR",
    "PYTHONPYCACHEPREFIX",
)
FORBIDDEN_ENVIRONMENT = (
    "LD_AUDIT",
    "LD_PRELOAD",
    "PYTHONHOME",
    "PYTHONINSPECT",
    "PYTHONPATH",
    "PYTHONPLATLIBDIR",
    "PYTHONSTARTUP",
    "PYTHONUSERBASE",
)

WRITE_CONFINEMENT_CLAIM = (
    "process-tree ABI-4 handled filesystem content/topology mutations confined "
    "to two output directories, with an exact /proc/self/task "
    "WRITE_FILE|TRUNCATE thread-name exception and exact NVIDIA WRITE_FILE "
    "exceptions"
)
LANDLOCK_LIMITATIONS = {
    "metadata_operations_unhandled": True,
    "preopened_file_descriptors_unmediated": True,
    "sibling_processes_and_other_nfs_clients_unmediated": True,
    "device_ioctl_unhandled_in_abi4": True,
    "proc_self_task_path_beneath_write_truncate_exception": True,
    "read_only_mount_claimed": False,
}

PROTECTED_OPERATIONS = (
    "protected_create",
    "protected_mkdir",
    "protected_symlink",
    "protected_link",
    "protected_unlink",
    "protected_rename",
    "protected_truncate",
    "protected_open_write",
)
OUTPUT_ALLOWED_OPERATIONS = (
    "output_create_write_fsync",
    "output_same_directory_rename",
    "output_unlink",
    "output_mkdir",
    "output_rmdir",
)
OUTPUT_DENIED_OPERATIONS = (
    "output_truncate",
    "output_symlink",
    "output_fifo",
    "output_unix_socket",
    "output_cross_directory_link",
)
PRECONFINEMENT_WRITABLE_BASELINE = (
    "baseline_seed_open_write_no_write",
    "baseline_create_unlink",
    "baseline_mkdir_rmdir",
)
CONFINED_EVIDENCE_ARGUMENTS = (
    "plan_dir",
    "raw_root",
    "run_complete",
    "raw_ledger",
    "raw_inventory",
    "failure_log",
    "original_ownership",
    "original_guest",
    "original_cache",
    "original_authorization",
    "termination_audit",
    "postdelete_inventory",
    "frozen_termination",
    "superseded_runtime_block",
    "superseded_termination_audit",
    "superseded_frozen_termination",
    "superseded_postdelete_inventory",
    "fresh_ownership",
    "fresh_guest",
    "fresh_cache",
    "preflight_landlock",
    "preflight_probe",
    "local_test_receipt",
    "target_host_test_receipt",
    "target_qualification_ownership",
    "target_qualification_landlock",
    "target_qualification_cuda_preflight",
)
CONFINED_PATH_ARGUMENTS = (
    "provenance_root",
    "roots_manifest",
    "output_root",
    "preflight_output_root",
    "preflight_canary_protected_root",
    "preflight_canary_output_root",
    "canary_protected_root",
    "canary_output_root",
    "landlock_receipt",
    "model_snapshot",
    "j_lens_path",
    "audit_out",
    "summary_out",
    "attempt_marker",
    "failure_out",
)

HEX64 = re.compile(r"[0-9a-f]{64}")
HEX40 = re.compile(r"[0-9a-f]{40}")
ROOT_NAME = re.compile(r"[a-z][a-z0-9_]{0,63}")
ATTEMPT_ID_RE = re.compile(r"calv2-r3-audit-recovery-[0-9a-f]{7}-[0-9]{8}T[0-9]{6}Z")
NVIDIA_DEVICE_PATH = re.compile(
    r"(?:/dev/nvidia[0-9]+|/dev/nvidiactl|/dev/nvidia-uvm|"
    r"/dev/nvidia-uvm-tools|/dev/nvidia-caps/nvidia-cap[0-9]+)"
)

LANDLOCK_REQUIRED_FIELDS = frozenset(
    {
        "schema_version",
        "status",
        "purpose",
        "pid",
        "observed_abi",
        "required_abi",
        "handled_access_fs",
        "output_allowed_access_fs",
        "no_new_privs",
        "thread_ids",
        "descriptor_audit",
        "mapping_audit",
        "directory_rules",
        "device_rules",
        "protected_checks",
        "canary_checks",
        "child_argv",
        "child_argv_sha256",
        "source_sha256",
        "receipt_path",
        "receipt_sha256",
    }
)


class RecoveryBundleVerificationError(RuntimeError):
    """The retrieved recovery bundle is incomplete or semantically invalid."""


def canonical_json_bytes(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise RecoveryBundleVerificationError("value is not canonical JSON") from exc


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while block := handle.read(8 * 1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def _reject_constant(value: str) -> None:
    raise RecoveryBundleVerificationError(f"non-finite JSON constant: {value}")


def _object_without_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise RecoveryBundleVerificationError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _finite_json(value: Any) -> bool:
    if value is None or isinstance(value, (bool, str, int)):
        return True
    if isinstance(value, float):
        return math.isfinite(value)
    if isinstance(value, list):
        return all(_finite_json(item) for item in value)
    if isinstance(value, dict):
        return all(
            isinstance(key, str) and _finite_json(item) for key, item in value.items()
        )
    return False


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise RecoveryBundleVerificationError(f"{label} must be an object")
    return value


def _list(value: Any, label: str) -> list[Any]:
    if not isinstance(value, list):
        raise RecoveryBundleVerificationError(f"{label} must be an array")
    return value


def _string(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise RecoveryBundleVerificationError(f"{label} must be a nonempty string")
    return value


def _integer(value: Any, label: str, *, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise RecoveryBundleVerificationError(
            f"{label} must be an integer >= {minimum}"
        )
    return value


def _number(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise RecoveryBundleVerificationError(f"{label} must be numeric")
    result = float(value)
    if not math.isfinite(result):
        raise RecoveryBundleVerificationError(f"{label} must be finite")
    return result


def _hex64(value: Any, label: str) -> str:
    text = _string(value, label)
    if HEX64.fullmatch(text) is None:
        raise RecoveryBundleVerificationError(f"{label} must be lowercase SHA-256")
    return text


def _keys(value: Mapping[str, Any], names: Sequence[str], label: str) -> None:
    missing = sorted(set(names) - set(value))
    if missing:
        raise RecoveryBundleVerificationError(f"{label} is missing keys: {missing}")


def _exact_keys(value: Mapping[str, Any], names: Sequence[str], label: str) -> None:
    expected = set(names)
    if set(value) != expected:
        raise RecoveryBundleVerificationError(
            f"{label} keys differ: expected={sorted(expected)} observed={sorted(value)}"
        )


def _self_hash(value: Mapping[str, Any], label: str) -> str:
    core = dict(value)
    supplied = _hex64(core.pop("receipt_sha256", None), f"{label}.receipt_sha256")
    if supplied != canonical_sha256(core):
        raise RecoveryBundleVerificationError(f"{label} self-hash differs")
    return supplied


def _inside_posix(root: str, candidate: str) -> bool:
    paths: list[PurePosixPath] = []
    for value in (root, candidate):
        if (
            not isinstance(value, str)
            or not value.startswith("/")
            or value.startswith("//")
            or ".." in PurePosixPath(value).parts
            or PurePosixPath(value).as_posix() != value
        ):
            raise RecoveryBundleVerificationError(
                "path is not canonical single-leading-slash absolute POSIX text"
            )
        paths.append(PurePosixPath(value))
    root_path, candidate_path = paths
    return candidate_path == root_path or root_path in candidate_path.parents


def _plain_file(root: Path, relative: Path) -> Path:
    current = root
    for part in relative.parts:
        current /= part
        try:
            details = current.lstat()
        except OSError as exc:
            raise RecoveryBundleVerificationError(
                f"required bundle path is missing: {relative}"
            ) from exc
        if stat.S_ISLNK(details.st_mode):
            raise RecoveryBundleVerificationError(
                f"required bundle path contains a symlink: {relative}"
            )
    details = current.lstat()
    if not stat.S_ISREG(details.st_mode) or details.st_nlink != 1:
        raise RecoveryBundleVerificationError(
            f"required bundle path is not a unique regular file: {relative}"
        )
    return current


def _read_receipt(
    root: Path, relative: Path, label: str
) -> tuple[dict[str, Any], Path]:
    path = _plain_file(root, relative)
    try:
        raw = path.read_bytes()
        value = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_object_without_duplicates,
            parse_constant=_reject_constant,
        )
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise RecoveryBundleVerificationError(f"{label} is unreadable JSON") from exc
    if not isinstance(value, dict) or not _finite_json(value):
        raise RecoveryBundleVerificationError(f"{label} is not a finite JSON object")
    if raw != canonical_json_bytes(value) + b"\n":
        raise RecoveryBundleVerificationError(f"{label} file encoding is noncanonical")
    _self_hash(value, label)
    return value, path


def _validate_output_tree(root: Path) -> None:
    output = root / "output"
    try:
        details = output.lstat()
    except OSError as exc:
        raise RecoveryBundleVerificationError("output directory is missing") from exc
    if not stat.S_ISDIR(details.st_mode) or stat.S_ISLNK(details.st_mode):
        raise RecoveryBundleVerificationError("output is not a plain directory")
    for directory, names, files in os.walk(output, topdown=True, followlinks=False):
        base = Path(directory)
        for name in [*names, *files]:
            path = base / name
            details = path.lstat()
            relative = path.relative_to(root).as_posix()
            if stat.S_ISLNK(details.st_mode):
                raise RecoveryBundleVerificationError(
                    f"output contains a symlink: {relative}"
                )
            if stat.S_ISREG(details.st_mode) and details.st_nlink != 1:
                raise RecoveryBundleVerificationError(
                    f"output contains a hard-linked file: {relative}"
                )
            if not (stat.S_ISREG(details.st_mode) or stat.S_ISDIR(details.st_mode)):
                raise RecoveryBundleVerificationError(
                    f"output contains a special filesystem object: {relative}"
                )


def _validate_compact_directory(root: Path) -> None:
    compact = root / COMPACT_RELATIVE
    try:
        details = compact.lstat()
    except OSError as exc:
        raise RecoveryBundleVerificationError("compact directory is missing") from exc
    if not stat.S_ISDIR(details.st_mode) or stat.S_ISLNK(details.st_mode):
        raise RecoveryBundleVerificationError("compact is not a plain directory")
    observed = {entry.name for entry in compact.iterdir()}
    if observed != COMPACT_FILE_NAMES:
        raise RecoveryBundleVerificationError(
            f"compact file set differs: {sorted(observed)}"
        )
    if os.path.lexists(root / FAILURE_RELATIVE):
        raise RecoveryBundleVerificationError(
            "successful bundle also contains output/FAILURE.json"
        )


def _expected_paths(attempt_id: str) -> dict[str, str]:
    attempt = PurePosixPath(RECOVERY_ATTEMPT_PARENT) / attempt_id
    original = attempt / "evidence/original"
    superseded = attempt / "evidence/superseded_recovery_host"
    fresh = attempt / "evidence/fresh"
    output = attempt / "output"
    preflight = attempt / "preflight"
    canary = attempt / "landlock_canary"
    return {
        "plan_dir": (
            attempt / "provenance_repo" / CANONICAL_PLAN_RELATIVE_PATH
        ).as_posix(),
        "raw_root": f"/workspace/{RAW_RELATIVE}",
        "run_complete": (original / "RUN_COMPLETE.json").as_posix(),
        "raw_ledger": (original / "REMOTE_RAW_SHA256SUMS.txt").as_posix(),
        "raw_inventory": (original / "REMOTE_RAW_INVENTORY.txt").as_posix(),
        "failure_log": (original / "calibration_audit_1a16572.log").as_posix(),
        "original_ownership": (original / "OWNERSHIP.json").as_posix(),
        "original_guest": (original / "GUEST_PREFLIGHT.json").as_posix(),
        "original_cache": (original / "CACHE_PREFLIGHT.json").as_posix(),
        "original_authorization": (
            original / "CALIBRATION_AUTHORIZATION.json"
        ).as_posix(),
        "termination_audit": (original / "TERMINATION_AUDIT.json").as_posix(),
        "postdelete_inventory": (original / "POSTDELETE_INVENTORY.json").as_posix(),
        "frozen_termination": (
            original / "frozen_lifecycle/TERMINATION.json"
        ).as_posix(),
        "superseded_runtime_block": (
            superseded / "PREEXECUTION_RUNTIME_BLOCK.json"
        ).as_posix(),
        "superseded_termination_audit": (
            superseded / "TERMINATION_AUDIT.json"
        ).as_posix(),
        "superseded_frozen_termination": (
            superseded / "frozen_lifecycle/TERMINATION.json"
        ).as_posix(),
        "superseded_postdelete_inventory": (
            superseded / "POSTDELETE_INVENTORY.json"
        ).as_posix(),
        "fresh_ownership": (fresh / "OWNERSHIP.json").as_posix(),
        "fresh_guest": (fresh / "GUEST_PREFLIGHT.json").as_posix(),
        "fresh_cache": (fresh / "CACHE_PREFLIGHT.json").as_posix(),
        "preflight_landlock": (
            preflight / "output/LANDLOCK_ENFORCEMENT.json"
        ).as_posix(),
        "preflight_probe": (
            preflight / "output/LANDLOCK_CUDA_PREFLIGHT.json"
        ).as_posix(),
        "local_test_receipt": (
            attempt / "evidence/tests/LOCAL_TEST_RECEIPT.json"
        ).as_posix(),
        "target_host_test_receipt": (
            attempt / "evidence/tests/TARGET_HOST_TEST_RECEIPT.json"
        ).as_posix(),
        "target_qualification_ownership": (
            attempt / f"evidence/tests/{TARGET_QUALIFICATION_OWNERSHIP_NAME}"
        ).as_posix(),
        "target_qualification_landlock": (
            attempt / f"evidence/tests/{TARGET_QUALIFICATION_LANDLOCK_NAME}"
        ).as_posix(),
        "target_qualification_cuda_preflight": (
            attempt / f"evidence/tests/{TARGET_QUALIFICATION_CUDA_NAME}"
        ).as_posix(),
        "preflight_output_root": (preflight / "output").as_posix(),
        "preflight_canary_protected_root": (preflight / "canary/protected").as_posix(),
        "preflight_canary_output_root": (preflight / "canary/output").as_posix(),
        "recovery_authorization": (attempt / "RECOVERY_AUTHORIZATION.json").as_posix(),
        "provenance_root": (attempt / "provenance_repo").as_posix(),
        "roots_manifest": (attempt / BOOTSTRAP_MANIFEST_RELATIVE).as_posix(),
        "output_root": output.as_posix(),
        "canary_protected_root": (canary / "protected").as_posix(),
        "canary_output_root": (canary / "output").as_posix(),
        "landlock_receipt": (output / "LANDLOCK_ENFORCEMENT.json").as_posix(),
        "model_snapshot": MODEL_SNAPSHOT_PATH,
        "j_lens_path": J_LENS_PATH,
        "audit_out": (output / "compact/CALIBRATION_AUDIT.json").as_posix(),
        "summary_out": (output / "compact/CALIBRATION_SUMMARY.json").as_posix(),
        "attempt_marker": (output / "ATTEMPT_STARTED.json").as_posix(),
        "failure_out": (output / "FAILURE.json").as_posix(),
    }


def _expected_confined_argv(
    python_executable: str,
    active_root: str,
    attempt_id: str,
    paths: Mapping[str, str],
    roots_manifest_sha256: str,
    device_files: Sequence[str],
) -> list[str]:
    result = [
        python_executable,
        "-B",
        "-E",
        "-s",
        "-S",
        f"{active_root}/{BOOTSTRAP_RELATIVE_PATH}",
        "--mode",
        "execute-confined",
        "--active-root",
        active_root,
        "--roots-manifest",
        paths["roots_manifest"],
        "--roots-manifest-sha256",
        roots_manifest_sha256,
        "--",
    ]
    for name in CONFINED_EVIDENCE_ARGUMENTS:
        result.extend((f"--{name.replace('_', '-')}", paths[name]))
    result.extend(("--attempt-id", attempt_id))
    result.extend(("--active-root", active_root))
    result.extend(("--python-executable", python_executable))
    for name in CONFINED_PATH_ARGUMENTS:
        result.extend((f"--{name.replace('_', '-')}", paths[name]))
    result.extend(("--roots-manifest-sha256", roots_manifest_sha256))
    for path in device_files:
        result.extend(("--device-file", path))
    result.extend(("--artifact-device", "cuda:0"))
    result.extend(("--recovery-authorization", paths["recovery_authorization"]))
    return result


def _expected_preflight_argv(
    python_executable: str,
    active_root: str,
    paths: Mapping[str, str],
    roots_manifest_sha256: str,
    device_files: Sequence[str],
    *,
    closure_scope: str = "final_recovery",
    qualification_ownership: str | None = None,
    landlock_receipt: str | None = None,
    output_root: str | None = None,
    canary_protected_root: str | None = None,
    canary_output_root: str | None = None,
    output: str | None = None,
) -> list[str]:
    """Return the frozen target-free preflight child command (not its launcher)."""

    if closure_scope not in PREFLIGHT_CLOSURE_SCOPES or (
        closure_scope == "source_test_qualification"
    ) is not bool(qualification_ownership):
        raise RecoveryBundleVerificationError("preflight closure scope differs")

    landlock_receipt = landlock_receipt or paths["preflight_landlock"]
    output_root = output_root or paths["preflight_output_root"]
    canary_protected_root = (
        canary_protected_root or paths["preflight_canary_protected_root"]
    )
    canary_output_root = canary_output_root or paths["preflight_canary_output_root"]
    output = output or paths["preflight_probe"]

    result = [
        python_executable,
        "-B",
        "-E",
        "-s",
        "-S",
        f"{active_root}/{BOOTSTRAP_RELATIVE_PATH}",
        "--mode",
        "preflight-child",
        "--active-root",
        active_root,
        "--roots-manifest",
        paths["roots_manifest"],
        "--roots-manifest-sha256",
        roots_manifest_sha256,
        "--",
        "--python-executable",
        python_executable,
        "--active-root",
        active_root,
        "--roots-manifest",
        paths["roots_manifest"],
        "--roots-manifest-sha256",
        roots_manifest_sha256,
        "--landlock-receipt",
        landlock_receipt,
        "--output-root",
        output_root,
        "--canary-protected-root",
        canary_protected_root,
        "--canary-output-root",
        canary_output_root,
        "--closure-scope",
        closure_scope,
    ]
    if qualification_ownership is not None:
        result.extend(("--qualification-ownership", qualification_ownership))
    for path in sorted(device_files):
        result.extend(("--device-file", path))
    result.extend(("--output", output))
    return result


def _validate_device_rules(value: Any, label: str) -> list[dict[str, Any]]:
    rows = _list(value, label)
    if not rows:
        raise RecoveryBundleVerificationError(f"{label} is empty")
    normalized: list[dict[str, Any]] = []
    fields = (
        "path",
        "st_dev",
        "st_ino",
        "st_rdev",
        "major",
        "minor",
        "allowed_access_fs",
    )
    for index, item in enumerate(rows):
        row_label = f"{label}[{index}]"
        row = _mapping(item, row_label)
        _exact_keys(row, fields, row_label)
        path = _string(row["path"], f"{row_label}.path")
        if NVIDIA_DEVICE_PATH.fullmatch(path) is None:
            raise RecoveryBundleVerificationError(
                f"{row_label}.path is not a NVIDIA device"
            )
        st_rdev = _integer(row["st_rdev"], f"{row_label}.st_rdev")
        if st_rdev > 0xFFFFFFFFFFFFFFFF:
            raise RecoveryBundleVerificationError(
                f"{row_label}.st_rdev exceeds Linux dev_t"
            )
        major = _integer(row["major"], f"{row_label}.major")
        minor = _integer(row["minor"], f"{row_label}.minor")
        identity = (_linux_device_major(st_rdev), _linux_device_minor(st_rdev))
        if (
            identity != (major, minor)
            or row["allowed_access_fs"] != DEVICE_ALLOWED_ACCESS_FS
        ):
            raise RecoveryBundleVerificationError(
                f"{row_label} identity/access differs"
            )
        normalized.append(
            {
                "path": path,
                "st_dev": _integer(row["st_dev"], f"{row_label}.st_dev"),
                "st_ino": _integer(row["st_ino"], f"{row_label}.st_ino", minimum=1),
                "st_rdev": st_rdev,
                "major": major,
                "minor": minor,
                "allowed_access_fs": DEVICE_ALLOWED_ACCESS_FS,
            }
        )
    paths = [row["path"] for row in normalized]
    if paths != sorted(paths) or len(paths) != len(set(paths)):
        raise RecoveryBundleVerificationError(f"{label} is not sorted and unique")
    return normalized


def _linux_device_major(device: int) -> int:
    """Decode Linux ``dev_t`` without depending on the verifier host ABI."""

    return ((device >> 8) & 0xFFF) | ((device >> 32) & 0xFFFFF000)


def _linux_device_minor(device: int) -> int:
    """Decode Linux ``dev_t`` without depending on the verifier host ABI."""

    return (device & 0xFF) | ((device >> 12) & 0xFFFFFF00)


def _validate_descriptor_audit(
    value: Any,
    *,
    output_root: str,
    canary_output_root: str,
    expected_protected_roots: Sequence[str],
    label: str,
) -> None:
    audit = _mapping(value, label)
    _exact_keys(
        audit, ("status", "protected_roots", "descriptor_count", "descriptors"), label
    )
    protected = _list(audit["protected_roots"], f"{label}.protected_roots")
    if any(not isinstance(path, str) or not path.startswith("/") for path in protected):
        raise RecoveryBundleVerificationError(f"{label}.protected_roots differs")
    if protected != sorted(set(expected_protected_roots)):
        raise RecoveryBundleVerificationError(f"{label}.protected_roots differs")
    rows = _list(audit["descriptors"], f"{label}.descriptors")
    if audit["status"] != "pass_no_escaping_writable_or_protected_descriptors" or audit[
        "descriptor_count"
    ] != len(rows):
        raise RecoveryBundleVerificationError(f"{label} status/count differs")
    observed_fds: list[int] = []
    for index, item in enumerate(rows):
        row_label = f"{label}.descriptors[{index}]"
        row = _mapping(item, row_label)
        _exact_keys(
            row,
            ("fd", "target", "kind", "access_mode", "writable", "allowed_reason"),
            row_label,
        )
        fd = _integer(row["fd"], f"{row_label}.fd")
        observed_fds.append(fd)
        target = _string(row["target"], f"{row_label}.target")
        kind = _string(row["kind"], f"{row_label}.kind")
        if kind not in {
            "regular_file",
            "directory",
            "character_device",
            "block_device",
            "fifo",
            "socket",
            "other",
        }:
            raise RecoveryBundleVerificationError(f"{row_label}.kind differs")
        access_mode = _integer(row["access_mode"], f"{row_label}.access_mode")
        if access_mode not in (os.O_RDONLY, os.O_WRONLY, os.O_RDWR):
            raise RecoveryBundleVerificationError(f"{row_label}.access_mode differs")
        writable = row["writable"]
        if not isinstance(writable, bool) or writable != (
            access_mode in (os.O_WRONLY, os.O_RDWR)
        ):
            raise RecoveryBundleVerificationError(f"{row_label}.writable differs")
        in_output = target.startswith("/") and _inside_posix(output_root, target)
        if target.startswith("/") and (
            _inside_posix(canary_output_root, target)
            or any(_inside_posix(path, target) for path in protected)
        ):
            raise RecoveryBundleVerificationError(
                f"{row_label} is a forbidden inherited FD"
            )
        if target == "anon_inode:[io_uring]":
            raise RecoveryBundleVerificationError(
                f"{row_label} is a forbidden io_uring FD"
            )
        if NVIDIA_DEVICE_PATH.fullmatch(target) is not None:
            raise RecoveryBundleVerificationError(f"{row_label} is a forbidden GPU FD")
        if fd >= 3 and writable and kind in {"character_device", "block_device"}:
            raise RecoveryBundleVerificationError(
                f"{row_label} is a forbidden writable device FD"
            )
        if writable and kind in {"regular_file", "directory"}:
            raise RecoveryBundleVerificationError(
                f"{row_label} is a forbidden writable regular/directory FD"
            )
        if fd in (0, 1, 2):
            expected_reason = "standard_stream"
        elif in_output:
            expected_reason = "durable_output_root"
        elif not writable:
            expected_reason = "read_only_descriptor"
        else:
            expected_reason = "non_regular_non_directory_descriptor"
        if row["allowed_reason"] != expected_reason:
            raise RecoveryBundleVerificationError(f"{row_label}.allowed_reason differs")
    if observed_fds != sorted(set(observed_fds)):
        raise RecoveryBundleVerificationError(f"{label} descriptor inventory differs")


def _denied_rows(names: Sequence[str]) -> list[dict[str, Any]]:
    return [
        {
            "operation": name,
            "status": "denied",
            "errno": (
                errno.EXDEV if name == "output_cross_directory_link" else errno.EACCES
            ),
        }
        for name in names
    ]


def _validate_landlock_receipt(
    receipt: Mapping[str, Any],
    *,
    purpose: str,
    receipt_path: str,
    output_root: str,
    protected_roots: Sequence[str],
    protected_files: Sequence[str],
    canary_output_root: str,
    authorization_sha256: str | None,
    preflight_sha256: str | None,
    label: str,
) -> tuple[int, list[dict[str, Any]]]:
    optional: set[str] = set()
    if authorization_sha256 is not None:
        optional.add("authorization_sha256")
    if preflight_sha256 is not None:
        optional.add("preflight_receipt_sha256")
    _exact_keys(receipt, tuple(LANDLOCK_REQUIRED_FIELDS | optional), label)
    pid = _integer(receipt["pid"], f"{label}.pid", minimum=1)
    if (
        receipt["schema_version"] != SCHEMA_VERSION
        or receipt["status"] != "pass_landlock_enforced"
        or receipt["purpose"] != purpose
        or receipt["required_abi"] != POLICY_ABI
        or _integer(receipt["observed_abi"], f"{label}.observed_abi") < POLICY_ABI
        or receipt["handled_access_fs"] != HANDLED_ACCESS_FS
        or receipt["output_allowed_access_fs"] != OUTPUT_ALLOWED_ACCESS_FS
        or receipt["no_new_privs"] is not True
        or receipt["thread_ids"] != [pid]
        or receipt["receipt_path"] != receipt_path
        or receipt.get("authorization_sha256") != authorization_sha256
        or receipt.get("preflight_receipt_sha256") != preflight_sha256
    ):
        raise RecoveryBundleVerificationError(
            f"{label} identity/ABI/no_new_privs differs"
        )
    _hex64(receipt["source_sha256"], f"{label}.source_sha256")
    child = _list(receipt["child_argv"], f"{label}.child_argv")
    if (
        not child
        or any(not isinstance(part, str) or not part for part in child)
        or receipt["child_argv_sha256"] != canonical_sha256(child)
    ):
        raise RecoveryBundleVerificationError(f"{label} child command differs")
    expected_directories = [
        {
            "role": "output_root",
            "path": output_root,
            "allowed_access_fs": OUTPUT_ALLOWED_ACCESS_FS,
        },
        {
            "role": "canary_output_root",
            "path": canary_output_root,
            "allowed_access_fs": OUTPUT_ALLOWED_ACCESS_FS,
        },
        {
            "role": "proc_self_task_thread_names",
            "path": PROC_SELF_TASK_PATH,
            "allowed_access_fs": PROC_SELF_TASK_ALLOWED_ACCESS_FS,
        },
    ]
    if receipt["directory_rules"] != expected_directories:
        raise RecoveryBundleVerificationError(f"{label} directory grants differ")
    devices = _validate_device_rules(receipt["device_rules"], f"{label}.device_rules")
    _validate_descriptor_audit(
        receipt["descriptor_audit"],
        output_root=output_root,
        canary_output_root=canary_output_root,
        expected_protected_roots=protected_roots,
        label=f"{label}.descriptor_audit",
    )
    mappings = _mapping(receipt["mapping_audit"], f"{label}.mapping_audit")
    _exact_keys(
        mappings,
        ("status", "mapping_count", "shared_file_backed"),
        f"{label}.mapping_audit",
    )
    if (
        mappings["status"] != "pass_no_shared_file_backed_mappings"
        or _integer(mappings["mapping_count"], f"{label}.mapping_audit.mapping_count")
        < 1
        or mappings["shared_file_backed"] != []
    ):
        raise RecoveryBundleVerificationError(f"{label} mapping audit differs")
    expected_protected_checks = [
        {
            "path": path,
            "operation": "protected_file_open_write_no_write",
            "status": "denied",
            "errno": errno.EACCES,
        }
        for path in sorted(protected_files)
    ]
    if receipt["protected_checks"] != expected_protected_checks:
        raise RecoveryBundleVerificationError(f"{label}.protected_checks differs")
    canary = _mapping(receipt["canary_checks"], f"{label}.canary_checks")
    _exact_keys(
        canary,
        (
            "status",
            "protected_inventory_sha256_before",
            "protected_inventory_sha256_after",
            "protected_unchanged",
            "output_empty_before",
            "output_empty_after",
            "preconfinement_writable_baseline",
            "protected_operations",
            "output_operations",
        ),
        f"{label}.canary_checks",
    )
    before = _hex64(
        canary["protected_inventory_sha256_before"],
        f"{label}.canary_checks.protected_inventory_sha256_before",
    )
    if (
        canary["status"] != "pass_protected_unchanged_output_empty"
        or canary["protected_inventory_sha256_after"] != before
        or canary["protected_unchanged"] is not True
        or canary["output_empty_before"] is not True
        or canary["output_empty_after"] is not True
        or canary["preconfinement_writable_baseline"]
        != [
            {"operation": name, "status": "allowed"}
            for name in PRECONFINEMENT_WRITABLE_BASELINE
        ]
        or canary["protected_operations"] != _denied_rows(PROTECTED_OPERATIONS)
        or canary["output_operations"]
        != [
            *(
                {"operation": name, "status": "allowed"}
                for name in OUTPUT_ALLOWED_OPERATIONS
            ),
            *_denied_rows(OUTPUT_DENIED_OPERATIONS),
        ]
    ):
        raise RecoveryBundleVerificationError(f"{label} canary checks differ")
    return pid, devices


def _file_record_matches(value: Any, path: Path, label: str) -> None:
    record = _mapping(value, label)
    _exact_keys(record, ("bytes", "sha256"), label)
    if record["bytes"] != path.stat().st_size or record["sha256"] != sha256_file(path):
        raise RecoveryBundleVerificationError(f"{label} physical hash differs")


def _validate_detached_file_record(value: Any, label: str) -> None:
    """Validate an authorization-bound file record absent from the retrieval."""

    record = _mapping(value, label)
    _exact_keys(record, ("bytes", "sha256"), label)
    _integer(record["bytes"], f"{label}.bytes")
    _hex64(record["sha256"], f"{label}.sha256")


def _validate_file_rows(
    value: Any,
    label: str,
    *,
    expected_paths: Sequence[str] | None = None,
) -> list[dict[str, Any]]:
    rows = _list(value, label)
    if not rows:
        raise RecoveryBundleVerificationError(f"{label} is empty")
    normalized: list[dict[str, Any]] = []
    for index, item in enumerate(rows):
        row_label = f"{label}[{index}]"
        row = _mapping(item, row_label)
        _exact_keys(row, ("path", "bytes", "sha256"), row_label)
        path = _string(row["path"], f"{row_label}.path")
        posix = PurePosixPath(path)
        if (
            path.startswith("/")
            or path.startswith("//")
            or path == "."
            or ".." in posix.parts
            or posix.as_posix() != path
        ):
            raise RecoveryBundleVerificationError(f"{row_label}.path is unsafe")
        normalized.append(
            {
                "path": path,
                "bytes": _integer(row["bytes"], f"{row_label}.bytes"),
                "sha256": _hex64(row["sha256"], f"{row_label}.sha256"),
            }
        )
    paths = [row["path"] for row in normalized]
    if paths != sorted(paths) or len(paths) != len(set(paths)):
        raise RecoveryBundleVerificationError(f"{label} is not sorted and unique")
    if expected_paths is not None and paths != list(expected_paths):
        raise RecoveryBundleVerificationError(f"{label} paths differ")
    return normalized


def _validate_bootstrap_root_record(value: Any, index: int) -> dict[str, Any]:
    label = f"bootstrap_manifest.roots[{index}]"
    row = _mapping(value, label)
    _exact_keys(
        row,
        (
            "name",
            "role",
            "path",
            "files",
            "directories",
            "file_count",
            "directory_count",
            "total_bytes",
            "file_inventory_sha256",
            "directory_inventory_sha256",
            "inventory_sha256",
        ),
        label,
    )
    name = _string(row["name"], f"{label}.name")
    role = _string(row["role"], f"{label}.role")
    path = _string(row["path"], f"{label}.path")
    if (
        ROOT_NAME.fullmatch(name) is None
        or role not in {"active", "dependency"}
        or (index == 0) != (role == "active")
        or (index == 0 and name != "active_root")
        or not _inside_posix(path, path)
    ):
        raise RecoveryBundleVerificationError(f"{label} identity differs")

    files_raw = _list(row["files"], f"{label}.files")
    files: list[dict[str, Any]] = []
    for file_index, value in enumerate(files_raw):
        file_label = f"{label}.files[{file_index}]"
        item = _mapping(value, file_label)
        _exact_keys(item, ("path", "bytes", "sha256"), file_label)
        relative = _string(item["path"], f"{file_label}.path")
        parsed = PurePosixPath(relative)
        if (
            parsed.is_absolute()
            or parsed.as_posix() != relative
            or relative == "."
            or ".." in parsed.parts
        ):
            raise RecoveryBundleVerificationError(f"{file_label}.path is unsafe")
        files.append(
            {
                "path": relative,
                "bytes": _integer(item["bytes"], f"{file_label}.bytes"),
                "sha256": _hex64(item["sha256"], f"{file_label}.sha256"),
            }
        )
    file_paths = [item["path"] for item in files]
    if file_paths != sorted(file_paths) or len(file_paths) != len(set(file_paths)):
        raise RecoveryBundleVerificationError(f"{label}.files is not sorted and unique")

    directories_raw = _list(row["directories"], f"{label}.directories")
    directories: list[str] = []
    for directory_index, value in enumerate(directories_raw):
        directory_label = f"{label}.directories[{directory_index}]"
        relative = _string(value, directory_label)
        parsed = PurePosixPath(relative)
        if (
            parsed.is_absolute()
            or parsed.as_posix() != relative
            or relative == "."
            or ".." in parsed.parts
        ):
            raise RecoveryBundleVerificationError(f"{directory_label} is unsafe")
        directories.append(relative)
    if directories != sorted(directories) or len(directories) != len(set(directories)):
        raise RecoveryBundleVerificationError(
            f"{label}.directories is not sorted and unique"
        )

    core = dict(row)
    inventory_sha256 = _hex64(core.pop("inventory_sha256"), f"{label}.inventory_sha256")
    file_count = _integer(row["file_count"], f"{label}.file_count")
    directory_count = _integer(row["directory_count"], f"{label}.directory_count")
    total_bytes = _integer(row["total_bytes"], f"{label}.total_bytes")
    file_inventory_sha256 = _hex64(
        row["file_inventory_sha256"], f"{label}.file_inventory_sha256"
    )
    directory_inventory_sha256 = _hex64(
        row["directory_inventory_sha256"],
        f"{label}.directory_inventory_sha256",
    )
    if (
        file_count != len(files)
        or directory_count != len(directories)
        or total_bytes != sum(item["bytes"] for item in files)
        or file_inventory_sha256 != canonical_sha256(files)
        or directory_inventory_sha256 != canonical_sha256(directories)
        or inventory_sha256 != canonical_sha256(core)
    ):
        raise RecoveryBundleVerificationError(f"{label} inventory links differ")
    return dict(row)


def _validate_bootstrap_manifest(
    manifest: Mapping[str, Any],
    *,
    execution: Mapping[str, Any],
    paths: Mapping[str, str],
    closure: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    _exact_keys(
        manifest,
        (
            "schema_version",
            "status",
            "python_executable",
            "bootstrap_relative_path",
            "bootstrap_sha256",
            "active_root",
            "roots",
            "sys_path",
            "roots_inventory_sha256",
            "receipt_sha256",
        ),
        "bootstrap_manifest",
    )
    _self_hash(manifest, "bootstrap_manifest")
    executable = _mapping(
        manifest["python_executable"], "bootstrap_manifest.python_executable"
    )
    _exact_keys(
        executable,
        ("path", "bytes", "sha256"),
        "bootstrap_manifest.python_executable",
    )
    if (
        executable["path"] != execution["python_executable"]
        or _integer(executable["bytes"], "bootstrap_manifest.python_executable.bytes")
        < 1
        or HEX64.fullmatch(str(executable["sha256"])) is None
    ):
        raise RecoveryBundleVerificationError(
            "bootstrap_manifest Python executable differs"
        )
    roots_raw = _list(manifest["roots"], "bootstrap_manifest.roots")
    if len(roots_raw) < 2:
        raise RecoveryBundleVerificationError(
            "bootstrap_manifest requires active and dependency roots"
        )
    roots = [
        _validate_bootstrap_root_record(value, index)
        for index, value in enumerate(roots_raw)
    ]
    names = [str(row["name"]) for row in roots]
    root_paths = [str(row["path"]) for row in roots]
    sys_path = _list(manifest["sys_path"], "bootstrap_manifest.sys_path")
    if (
        manifest["schema_version"] != SCHEMA_VERSION
        or manifest["status"] != BOOTSTRAP_MANIFEST_STATUS
        or manifest["bootstrap_relative_path"] != BOOTSTRAP_RELATIVE_PATH
        or manifest["bootstrap_sha256"]
        != _closure_hash(closure, BOOTSTRAP_RELATIVE_PATH)
        or manifest["active_root"] != execution["active_root"]
        or roots[0]["path"] != execution["active_root"]
        or roots[0]["files"] != list(closure)
        or len(names) != len(set(names))
        or len(root_paths) != len(set(root_paths))
        or not sys_path
        or any(not isinstance(value, str) for value in sys_path)
        or sys_path[0] != execution["active_root"]
        or len(sys_path) != len(set(sys_path))
        or any(
            not any(_inside_posix(root_path, value) for root_path in root_paths)
            for value in sys_path
        )
        or manifest["roots_inventory_sha256"] != canonical_sha256(roots)
        or any(
            _inside_posix(root_path, paths["roots_manifest"])
            for root_path in root_paths
        )
    ):
        raise RecoveryBundleVerificationError(
            "bootstrap_manifest semantic links differ"
        )
    return dict(manifest)


def _bootstrap_protected_paths(
    manifest: Mapping[str, Any], paths: Mapping[str, str]
) -> tuple[list[str], list[str]]:
    root_paths = [str(row["path"]) for row in manifest["roots"]]
    manifest_path = PurePosixPath(paths["roots_manifest"])
    protected_roots = sorted(set(root_paths) | {manifest_path.parent.as_posix()})
    protected_files = sorted(
        {
            paths["roots_manifest"],
            f"{manifest['active_root']}/{BOOTSTRAP_RELATIVE_PATH}",
        }
    )
    return protected_roots, protected_files


def _validate_bootstrap_attestation(
    value: Any,
    *,
    mode: str,
    pid: int,
    execution: Mapping[str, Any],
    paths: Mapping[str, str],
    manifest: Mapping[str, Any],
) -> dict[str, Any]:
    label = "confined bootstrap attestation"
    attestation = _mapping(value, label)
    _exact_keys(
        attestation,
        (
            "schema_version",
            "status",
            "mode",
            "pid",
            "active_root",
            "python_executable",
            "roots_manifest_path",
            "roots_manifest_file_sha256",
            "roots_manifest_receipt_sha256",
            "roots_inventory_sha256",
            "sys_path",
            "bootstrap_sha256",
            "site_imported",
            "startup_project_or_ml_module_count",
            "guards",
            "receipt_sha256",
        ),
        label,
    )
    _self_hash(attestation, label)
    guards = _mapping(attestation["guards"], f"{label}.guards")
    _exact_keys(
        guards,
        (
            "status",
            "forbidden_module_import_attempts",
            "forbidden_startup_import_attempts",
            "torch_module_calls",
            "transformers_model_load_calls",
            "patched_modules",
        ),
        f"{label}.guards",
    )
    if (
        attestation["schema_version"] != SCHEMA_VERSION
        or attestation["status"] != "pass_hash_bound_confined_bootstrap"
        or attestation["mode"] != mode
        or attestation["pid"] != pid
        or attestation["active_root"] != execution["active_root"]
        or attestation["python_executable"] != execution["python_executable"]
        or attestation["roots_manifest_path"] != paths["roots_manifest"]
        or attestation["roots_manifest_file_sha256"]
        != execution["roots_manifest_sha256"]
        or attestation["roots_manifest_receipt_sha256"] != manifest["receipt_sha256"]
        or attestation["roots_inventory_sha256"] != manifest["roots_inventory_sha256"]
        or attestation["sys_path"] != manifest["sys_path"]
        or attestation["bootstrap_sha256"] != manifest["bootstrap_sha256"]
        or attestation["site_imported"] is not False
        or attestation["startup_project_or_ml_module_count"] != 0
        or guards
        != {
            "status": "process_lifetime_guards_installed",
            "forbidden_module_import_attempts": 0,
            "forbidden_startup_import_attempts": 0,
            "torch_module_calls": 0,
            "transformers_model_load_calls": 0,
            "patched_modules": list(BOOTSTRAP_GUARDED_MODULES),
        }
    ):
        raise RecoveryBundleVerificationError(f"{label} differs")
    return dict(attestation)


def _validate_bootstrap_phase(
    value: Any,
    *,
    phase: str,
    mode: str,
    pid: int,
    execution: Mapping[str, Any],
    paths: Mapping[str, str],
    manifest: Mapping[str, Any],
) -> dict[str, Any]:
    label = f"bootstrap phase {phase}"
    record = _mapping(value, label)
    _exact_keys(
        record,
        (
            "status",
            "phase",
            "attestation",
            "attestation_receipt_sha256",
            "receipt_sha256",
        ),
        label,
    )
    _self_hash(record, label)
    attestation = _validate_bootstrap_attestation(
        record["attestation"],
        mode=mode,
        pid=pid,
        execution=execution,
        paths=paths,
        manifest=manifest,
    )
    if (
        record["status"] != "pass_hash_bound_bootstrap_phase"
        or record["phase"] != phase
        or record["attestation_receipt_sha256"] != attestation["receipt_sha256"]
    ):
        raise RecoveryBundleVerificationError(f"{label} differs")
    return dict(record)


def _closure_hash(rows: Sequence[Mapping[str, Any]], path: str) -> str:
    for row in rows:
        if row["path"] == path:
            return str(row["sha256"])
    raise RecoveryBundleVerificationError(f"recovery closure is missing {path}")


def _closure_file_record(
    rows: Sequence[Mapping[str, Any]], path: str
) -> dict[str, Any]:
    for row in rows:
        if row["path"] == path:
            return {"bytes": row["bytes"], "sha256": row["sha256"]}
    raise RecoveryBundleVerificationError(f"recovery closure is missing {path}")


def _parse_utc(value: Any, label: str) -> datetime:
    text = _string(value, label)
    if (
        re.fullmatch(
            r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}"
            r"(?:\.[0-9]{1,9})?Z",
            text,
        )
        is None
    ):
        raise RecoveryBundleVerificationError(f"{label} is not canonical UTC")
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(
            timezone.utc
        )
    except ValueError as exc:
        raise RecoveryBundleVerificationError(f"{label} is not parseable UTC") from exc


def _validate_qualification_ownership(value: Any) -> dict[str, Any]:
    """Validate the disposable qualification pod's immutable ownership receipt."""

    label = "qualification ownership"
    ownership = _mapping(value, label)
    _exact_keys(ownership, tuple(OWNERSHIP_FIELDS), label)
    _self_hash(ownership, label)
    pod_id = _string(ownership["pod_id"], f"{label}.pod_id")
    pod_name = _string(ownership["pod_name"], f"{label}.pod_name")
    nonce = _string(ownership["ownership_nonce"], f"{label}.ownership_nonce")
    created_text = _string(ownership["created_at"], f"{label}.created_at")
    terminate_text = _string(ownership["terminate_after"], f"{label}.terminate_after")
    created = _parse_utc(created_text, f"{label}.created_at")
    terminate = _parse_utc(terminate_text, f"{label}.terminate_after")
    image = _mapping(
        ownership["provider_container_image_attestation"],
        f"{label}.provider_container_image_attestation",
    )
    _exact_keys(
        image,
        (
            "source",
            "immutable_reference",
            "graphql_create_snapshot_source",
            "create_request_sha256",
            "final_rest_proof_source",
            "rest_image_fields",
            "upstream_lifecycle_receipt_sha256",
        ),
        f"{label}.provider_container_image_attestation",
    )
    rest_fields = _list(
        image["rest_image_fields"],
        f"{label}.provider_container_image_attestation.rest_image_fields",
    )
    if (
        ownership["schema_version"] != SCHEMA_VERSION
        or ownership["status"] != "owned_running_isolated"
        or ownership["study_id"] != OWNERSHIP_STUDY_ID
        or ownership["protocol_version"] != OWNERSHIP_PROTOCOL_VERSION
        or re.fullmatch(r"[a-z0-9]{6,32}", pod_id) is None
        or not pod_name.startswith(OWNERSHIP_POD_NAME_PREFIX)
        or re.fullmatch(r"[0-9a-f]{32}", nonce) is None
        or nonce not in pod_name
        or ownership["network_volume_id"] != NETWORK_VOLUME_ID
        or ownership["provider_volume_size_bytes"]
        != OWNERSHIP_PROVIDER_VOLUME_SIZE_BYTES
        or ownership["data_center_id"] != DATA_CENTER_ID
        or ownership["gpu_type"] != GPU_TYPE
        or ownership["gpu_count"] != 1
        or ownership["volume_mount_path"] != "/workspace"
        or ownership["desired_status"] != "RUNNING"
        or ownership["locked"] is not False
        or terminate - created != timedelta(seconds=OWNERSHIP_MAX_TOTAL_SECONDS)
        or created.microsecond != 0
        or terminate.microsecond != 0
        or created_text != created.isoformat(timespec="seconds").replace("+00:00", "Z")
        or terminate_text
        != terminate.isoformat(timespec="seconds").replace("+00:00", "Z")
        or _integer(
            ownership["precreate_unrelated_pod_count"],
            f"{label}.precreate_unrelated_pod_count",
        )
        < 0
        or image["source"] != "validated_graphql_create_plus_final_rest_readback_v1"
        or image["immutable_reference"] != OWNERSHIP_IMAGE_IMMUTABLE_REFERENCE
        or image["graphql_create_snapshot_source"]
        != "graphql_create_plus_rest_volume_proof"
        or image["final_rest_proof_source"]
        != "rest_v1_pod_get_final_after_graphql_locked_state"
        or rest_fields != sorted(set(rest_fields))
        or not rest_fields
        or any(field not in {"image", "imageName"} for field in rest_fields)
        or image["upstream_lifecycle_receipt_sha256"]
        != ownership["upstream_lifecycle_receipt_sha256"]
    ):
        raise RecoveryBundleVerificationError(
            "qualification ownership resource binding differs"
        )
    for field in (
        "create_contract_sha256",
        "upstream_lifecycle_receipt_sha256",
        "precreate_unrelated_inventory_sha256",
    ):
        _hex64(ownership[field], f"{label}.{field}")
    _hex64(
        image["create_request_sha256"],
        f"{label}.provider_container_image_attestation.create_request_sha256",
    )
    return dict(ownership)


def _canonical_absolute_posix(value: Any, label: str) -> str:
    path = _string(value, label)
    _inside_posix(path, path)
    return path


def _single_argv_option(argv: Sequence[str], name: str) -> str:
    indices = [index for index, value in enumerate(argv) if value == name]
    if len(indices) != 1 or indices[0] + 1 >= len(argv):
        raise RecoveryBundleVerificationError(
            f"qualification child option differs: {name}"
        )
    value = argv[indices[0] + 1]
    if not isinstance(value, str) or not value or value.startswith("--"):
        raise RecoveryBundleVerificationError(
            f"qualification child option differs: {name}"
        )
    return value


def _validate_compact_bootstrap_phase(
    value: Any,
    *,
    pid: int,
    active_root: str,
    python_executable: str,
    roots_manifest_path: str,
    commitment: Mapping[str, Any],
    expected_bootstrap_sha256: str,
) -> None:
    phase = _mapping(value, "qualification bootstrap phase")
    _exact_keys(
        phase,
        (
            "status",
            "phase",
            "attestation",
            "attestation_receipt_sha256",
            "receipt_sha256",
        ),
        "qualification bootstrap phase",
    )
    _self_hash(phase, "qualification bootstrap phase")
    attestation = _mapping(phase["attestation"], "qualification bootstrap attestation")
    _exact_keys(
        attestation,
        (
            "schema_version",
            "status",
            "mode",
            "pid",
            "active_root",
            "python_executable",
            "roots_manifest_path",
            "roots_manifest_file_sha256",
            "roots_manifest_receipt_sha256",
            "roots_inventory_sha256",
            "sys_path",
            "bootstrap_sha256",
            "site_imported",
            "startup_project_or_ml_module_count",
            "guards",
            "receipt_sha256",
        ),
        "qualification bootstrap attestation",
    )
    _self_hash(attestation, "qualification bootstrap attestation")
    guards = _mapping(
        attestation["guards"], "qualification bootstrap attestation.guards"
    )
    expected_guards = {
        "status": "process_lifetime_guards_installed",
        "forbidden_module_import_attempts": 0,
        "forbidden_startup_import_attempts": 0,
        "torch_module_calls": 0,
        "transformers_model_load_calls": 0,
        "patched_modules": list(BOOTSTRAP_GUARDED_MODULES),
    }
    root_paths = _list(commitment.get("root_paths"), "qualification root paths")
    sys_path = _list(commitment.get("sys_path"), "qualification sys.path")
    if (
        phase["status"] != "pass_hash_bound_bootstrap_phase"
        or phase["phase"] != BOOTSTRAP_PREFLIGHT_PHASE
        or phase["attestation_receipt_sha256"] != attestation["receipt_sha256"]
        or attestation["schema_version"] != SCHEMA_VERSION
        or attestation["status"] != "pass_hash_bound_confined_bootstrap"
        or attestation["mode"] != "preflight-child"
        or attestation["pid"] != pid
        or attestation["active_root"] != active_root
        or attestation["python_executable"] != python_executable
        or attestation["roots_manifest_path"] != roots_manifest_path
        or attestation["roots_manifest_file_sha256"] != commitment.get("file_sha256")
        or attestation["roots_manifest_receipt_sha256"]
        != commitment.get("receipt_sha256")
        or attestation["roots_inventory_sha256"]
        != commitment.get("roots_inventory_sha256")
        or attestation["sys_path"] != sys_path
        or attestation["bootstrap_sha256"] != expected_bootstrap_sha256
        or commitment.get("bootstrap_sha256") != expected_bootstrap_sha256
        or attestation["site_imported"] is not False
        or attestation["startup_project_or_ml_module_count"] != 0
        or guards != expected_guards
        or root_paths != sorted(set(root_paths))
        or not root_paths
        or any(
            not isinstance(path, str) or _canonical_absolute_posix(path, "root") != path
            for path in root_paths
        )
        or sys_path != list(dict.fromkeys(sys_path))
        or not sys_path
        or sys_path[0] != active_root
        or any(
            not isinstance(path, str)
            or not any(_inside_posix(root, path) for root in root_paths)
            for path in sys_path
        )
    ):
        raise RecoveryBundleVerificationError("qualification bootstrap phase differs")
    for name in ("file_sha256", "receipt_sha256", "roots_inventory_sha256"):
        _hex64(commitment.get(name), f"qualification bootstrap.{name}")


def _validate_qualification_chain(
    *,
    ownership: Mapping[str, Any],
    landlock: Mapping[str, Any],
    cuda: Mapping[str, Any],
    ownership_path: Path,
    landlock_path: Path,
    cuda_path: Path,
    expected_source_test_files: Sequence[Mapping[str, Any]],
    probe_summary: Any,
) -> tuple[dict[str, Any], datetime]:
    """Validate every disposable-host ownership/Landlock/CUDA cross-link."""

    validated_ownership = _validate_qualification_ownership(ownership)
    child_argv = _list(landlock.get("child_argv"), "qualification Landlock child")
    if "--" not in child_argv:
        raise RecoveryBundleVerificationError(
            "qualification Landlock child command differs"
        )
    child = child_argv[child_argv.index("--") + 1 :]
    device_files = [
        child[index + 1]
        for index, value in enumerate(child[:-1])
        if value == "--device-file"
    ]
    if (
        not device_files
        or device_files != sorted(set(device_files))
        or any(
            not isinstance(path, str) or NVIDIA_DEVICE_PATH.fullmatch(path) is None
            for path in device_files
        )
    ):
        raise RecoveryBundleVerificationError("qualification device inventory differs")
    active_root = _canonical_absolute_posix(
        _single_argv_option(child, "--active-root"), "qualification active root"
    )
    python_executable = _canonical_absolute_posix(
        _single_argv_option(child, "--python-executable"),
        "qualification Python executable",
    )
    roots_manifest_path = _canonical_absolute_posix(
        _single_argv_option(child, "--roots-manifest"),
        "qualification roots manifest",
    )
    roots_manifest_sha256 = _hex64(
        _single_argv_option(child, "--roots-manifest-sha256"),
        "qualification roots manifest file hash",
    )
    embedded_landlock = _canonical_absolute_posix(
        _single_argv_option(child, "--landlock-receipt"),
        "qualification Landlock receipt path",
    )
    output_root = _canonical_absolute_posix(
        _single_argv_option(child, "--output-root"), "qualification output root"
    )
    canary_protected_root = _canonical_absolute_posix(
        _single_argv_option(child, "--canary-protected-root"),
        "qualification protected canary root",
    )
    canary_output_root = _canonical_absolute_posix(
        _single_argv_option(child, "--canary-output-root"),
        "qualification output canary root",
    )
    embedded_probe = _canonical_absolute_posix(
        _single_argv_option(child, "--output"), "qualification CUDA receipt path"
    )
    embedded_ownership = _canonical_absolute_posix(
        _single_argv_option(child, "--qualification-ownership"),
        "qualification ownership receipt path",
    )
    embedded_output_parent = PurePosixPath(output_root)
    if (
        _single_argv_option(child, "--closure-scope") != "source_test_qualification"
        or PurePosixPath(embedded_ownership).name != TARGET_QUALIFICATION_OWNERSHIP_NAME
        or PurePosixPath(embedded_landlock).name != TARGET_QUALIFICATION_LANDLOCK_NAME
        or PurePosixPath(embedded_probe).name != TARGET_QUALIFICATION_CUDA_NAME
        or PurePosixPath(embedded_landlock).parent != embedded_output_parent
        or PurePosixPath(embedded_probe).parent != embedded_output_parent
        or _inside_posix(output_root, embedded_ownership)
    ):
        raise RecoveryBundleVerificationError(
            "qualification evidence path/scope differs"
        )

    commitment = _mapping(
        cuda.get("bootstrap_roots_manifest"), "qualification bootstrap commitment"
    )
    _exact_keys(
        commitment,
        (
            "path",
            "file_sha256",
            "receipt_sha256",
            "roots_inventory_sha256",
            "bootstrap_sha256",
            "active_root",
            "python_executable",
            "root_paths",
            "sys_path",
        ),
        "qualification bootstrap commitment",
    )
    if (
        commitment["path"] != roots_manifest_path
        or commitment["file_sha256"] != roots_manifest_sha256
        or commitment["active_root"] != active_root
        or commitment["python_executable"] != python_executable
    ):
        raise RecoveryBundleVerificationError(
            "qualification bootstrap commitment differs"
        )
    root_paths = _list(commitment["root_paths"], "qualification root paths")
    roots_manifest_parent = PurePosixPath(roots_manifest_path).parent.as_posix()
    bootstrap_roots = sorted(set(root_paths) | {roots_manifest_parent})
    bootstrap_files = sorted(
        {
            roots_manifest_path,
            f"{active_root}/{BOOTSTRAP_RELATIVE_PATH}",
        }
    )
    pid, device_rules = _validate_landlock_receipt(
        landlock,
        purpose="preauthorization_probe",
        receipt_path=embedded_landlock,
        output_root=output_root,
        protected_roots=[canary_protected_root, *bootstrap_roots],
        protected_files=[
            f"{canary_protected_root}/seed.txt",
            *bootstrap_files,
            embedded_ownership,
        ],
        canary_output_root=canary_output_root,
        authorization_sha256=None,
        preflight_sha256=None,
        label="qualification_landlock",
    )
    expected_child = _expected_preflight_argv(
        python_executable,
        active_root,
        {"roots_manifest": roots_manifest_path},
        roots_manifest_sha256,
        device_files,
        closure_scope="source_test_qualification",
        qualification_ownership=embedded_ownership,
        landlock_receipt=embedded_landlock,
        output_root=output_root,
        canary_protected_root=canary_protected_root,
        canary_output_root=canary_output_root,
        output=embedded_probe,
    )
    if (
        child_argv != expected_child
        or landlock.get("child_argv_sha256") != canonical_sha256(expected_child)
        or [row["path"] for row in device_rules] != device_files
    ):
        raise RecoveryBundleVerificationError(
            "qualification Landlock child/device binding differs"
        )

    closure = list(expected_source_test_files)
    _exact_keys(
        cuda,
        (
            "schema_version",
            "status",
            "pid",
            "python_executable",
            "active_root",
            "closure_scope",
            "closure_files",
            "closure_file_count",
            "closure_inventory_sha256",
            "recovery_closure_sha256",
            "bootstrap_roots_manifest",
            "qualification_ownership_receipt_sha256",
            "landlock_receipt_sha256",
            "bootstrap",
            "package_versions",
            "imported_package_versions",
            "environment",
            "absent_environment_variables",
            "provider",
            "cuda",
            "model_forward_count",
            "torch_module_call_count",
            "target_prompt_render_count",
            "target_feature_vector_count",
            "external_or_prior_outcome_inputs",
            "completed_at_utc",
            "receipt_sha256",
        ),
        "qualification_cuda",
    )
    environment = _mapping(cuda["environment"], "qualification_cuda.environment")
    _exact_keys(
        environment,
        (*FIXED_ENVIRONMENT, *DYNAMIC_ENVIRONMENT),
        "qualification_cuda.environment",
    )
    provider = _mapping(cuda["provider"], "qualification_cuda.provider")
    _exact_keys(
        provider,
        ("pod_id", "volume_id", "data_center_id"),
        "qualification_cuda.provider",
    )
    cuda_result = _mapping(cuda["cuda"], "qualification_cuda.cuda")
    _exact_keys(
        cuda_result,
        (
            "available",
            "device",
            "device_count",
            "device_name",
            "device_capability",
            "dtype",
            "shape",
            "matmul_finite",
            "synchronized",
            "raw_tensor_operations_only",
        ),
        "qualification_cuda.cuda",
    )
    expected_provider = {
        "pod_id": validated_ownership["pod_id"],
        "volume_id": validated_ownership["network_volume_id"],
        "data_center_id": validated_ownership["data_center_id"],
    }
    capability = _list(
        cuda_result["device_capability"], "qualification_cuda.device_capability"
    )
    if (
        cuda["schema_version"] != SCHEMA_VERSION
        or cuda["status"] != "pass_target_free_landlock_cuda_preflight"
        or cuda["pid"] != pid
        or cuda["python_executable"] != python_executable
        or cuda["active_root"] != active_root
        or cuda["closure_scope"] != "source_test_qualification"
        or cuda["closure_files"] != closure
        or cuda["closure_file_count"] != len(closure)
        or cuda["closure_inventory_sha256"] != canonical_sha256(closure)
        or cuda["recovery_closure_sha256"] != canonical_sha256(closure)
        or cuda["qualification_ownership_receipt_sha256"]
        != validated_ownership["receipt_sha256"]
        or cuda["landlock_receipt_sha256"] != landlock["receipt_sha256"]
        or cuda["package_versions"] != EXPECTED_PACKAGES
        or cuda["imported_package_versions"] != EXPECTED_IMPORTED_PACKAGES
        or cuda["absent_environment_variables"] != list(FORBIDDEN_ENVIRONMENT)
        or any(
            environment[name] != expected
            for name, expected in FIXED_ENVIRONMENT.items()
        )
        or any(
            not isinstance(environment[name], str)
            or not _inside_posix(output_root, environment[name])
            for name in DYNAMIC_ENVIRONMENT
        )
        or provider != expected_provider
        or cuda_result["available"] is not True
        or cuda_result["device"] != "cuda:0"
        or cuda_result["device_count"] != 1
        or "B200" not in str(cuda_result["device_name"])
        or capability != [10, 0]
        or cuda_result["dtype"] != "torch.bfloat16"
        or cuda_result["shape"] != [16, 16]
        or cuda_result["matmul_finite"] is not True
        or cuda_result["synchronized"] is not True
        or cuda_result["raw_tensor_operations_only"] is not True
        or cuda["model_forward_count"] != 0
        or cuda["torch_module_call_count"] != 0
        or cuda["target_prompt_render_count"] != 0
        or cuda["target_feature_vector_count"] != 0
        or cuda["external_or_prior_outcome_inputs"] != []
    ):
        raise RecoveryBundleVerificationError(
            "qualification CUDA closure/bootstrap/device result differs"
        )
    _validate_compact_bootstrap_phase(
        cuda["bootstrap"],
        pid=pid,
        active_root=active_root,
        python_executable=python_executable,
        roots_manifest_path=roots_manifest_path,
        commitment=commitment,
        expected_bootstrap_sha256=_closure_hash(closure, BOOTSTRAP_RELATIVE_PATH),
    )
    completed_at = _parse_utc(
        cuda["completed_at_utc"], "qualification_cuda.completed_at_utc"
    )
    created_at = _parse_utc(
        validated_ownership["created_at"], "qualification ownership created_at"
    )
    if completed_at < created_at:
        raise RecoveryBundleVerificationError("qualification CUDA predated ownership")

    summary = _mapping(probe_summary, "target_host.qualification_probe")
    _exact_keys(
        summary,
        (
            "ownership_file",
            "ownership_receipt_sha256",
            "ownership_created_at_utc",
            "landlock_file",
            "landlock_receipt_sha256",
            "landlock_status",
            "landlock_observed_abi",
            "cuda_preflight_file",
            "cuda_preflight_receipt_sha256",
            "cuda_preflight_status",
            "cuda_preflight_closure_scope",
            "cuda_preflight_closure_inventory_sha256",
            "cuda_preflight_completed_at_utc",
            "cuda_preflight_completed_host_age_seconds",
            "bootstrap_roots_manifest_receipt_sha256",
            "python_executable",
            "active_root",
            "device_files",
            "child_argv_sha256",
            "provider",
            "cuda",
        ),
        "target_host.qualification_probe",
    )
    _file_record_matches(
        summary["ownership_file"], ownership_path, "qualification ownership file"
    )
    _file_record_matches(
        summary["landlock_file"], landlock_path, "qualification Landlock file"
    )
    _file_record_matches(
        summary["cuda_preflight_file"], cuda_path, "qualification CUDA file"
    )
    expected_summary = {
        "ownership_file": summary["ownership_file"],
        "ownership_receipt_sha256": validated_ownership["receipt_sha256"],
        "ownership_created_at_utc": validated_ownership["created_at"],
        "landlock_file": summary["landlock_file"],
        "landlock_receipt_sha256": landlock["receipt_sha256"],
        "landlock_status": landlock["status"],
        "landlock_observed_abi": landlock["observed_abi"],
        "cuda_preflight_file": summary["cuda_preflight_file"],
        "cuda_preflight_receipt_sha256": cuda["receipt_sha256"],
        "cuda_preflight_status": cuda["status"],
        "cuda_preflight_closure_scope": cuda["closure_scope"],
        "cuda_preflight_closure_inventory_sha256": cuda["closure_inventory_sha256"],
        "cuda_preflight_completed_at_utc": cuda["completed_at_utc"],
        "cuda_preflight_completed_host_age_seconds": int(
            (completed_at - created_at).total_seconds()
        ),
        "bootstrap_roots_manifest_receipt_sha256": commitment["receipt_sha256"],
        "python_executable": python_executable,
        "active_root": active_root,
        "device_files": device_files,
        "child_argv_sha256": landlock["child_argv_sha256"],
        "provider": dict(provider),
        "cuda": {
            name: cuda_result[name]
            for name in (
                "device",
                "device_count",
                "device_name",
                "device_capability",
                "matmul_finite",
                "synchronized",
                "raw_tensor_operations_only",
            )
        },
    }
    if summary != expected_summary:
        raise RecoveryBundleVerificationError(
            "target-host qualification summary differs"
        )
    return validated_ownership, completed_at


def _validate_test_receipt(
    value: Any,
    *,
    kind: str,
    expected_source_test_files: Sequence[Mapping[str, Any]],
    qualification_ownership: Mapping[str, Any] | None = None,
    qualification_landlock: Mapping[str, Any] | None = None,
    qualification_cuda: Mapping[str, Any] | None = None,
    qualification_ownership_path: Path | None = None,
    qualification_landlock_path: Path | None = None,
    qualification_cuda_path: Path | None = None,
    authorized_at: datetime | None = None,
) -> dict[str, Any]:
    label = f"{kind} test receipt"
    receipt = _mapping(value, label)
    _exact_keys(
        receipt,
        (
            "schema_version",
            "receipt_type",
            "kind",
            "status",
            "code_freeze_commit",
            "observed_git_head_commit",
            "source_test_files",
            "source_test_file_count",
            "source_test_inventory_sha256",
            "command_argv",
            "command",
            "command_argv_sha256",
            "receipt_path",
            "pytest_argv",
            "interpreter",
            "platform",
            "dependencies",
            "dependency_inventory_sha256",
            "collected_ids",
            "passed_ids",
            "failed_ids",
            "skipped_ids",
            "not_run_ids",
            "collected_count",
            "passed_count",
            "failed_count",
            "skipped_count",
            "not_run_count",
            "designated_target_ids",
            "started_at_utc",
            "completed_at_utc",
            "exit_code",
            "target_host",
            "qualification_probe",
            "receipt_sha256",
        ),
        label,
    )
    _self_hash(receipt, label)
    code_freeze = _string(receipt["code_freeze_commit"], f"{label}.code_freeze_commit")
    observed_head = _string(
        receipt["observed_git_head_commit"],
        f"{label}.observed_git_head_commit",
    )
    source_test_files = _list(
        receipt["source_test_files"], f"{label}.source_test_files"
    )
    command_argv = _list(receipt["command_argv"], f"{label}.command_argv")
    receipt_path = _string(receipt["receipt_path"], f"{label}.receipt_path")
    if (
        receipt["schema_version"] != SCHEMA_VERSION
        or receipt["receipt_type"] != TEST_RECEIPT_TYPE
        or receipt["kind"] != kind
        or receipt["status"] != TEST_RECEIPT_STATUS
        or HEX40.fullmatch(code_freeze) is None
        or HEX40.fullmatch(observed_head) is None
        or source_test_files != list(expected_source_test_files)
        or receipt["source_test_file_count"] != len(expected_source_test_files)
        or receipt["source_test_inventory_sha256"]
        != canonical_sha256(list(expected_source_test_files))
        or not command_argv
        or any(not isinstance(part, str) or not part for part in command_argv)
        or receipt["command"] != shlex.join(command_argv)
        or receipt["command_argv_sha256"] != canonical_sha256(command_argv)
        or not receipt_path.startswith("/")
        or receipt_path.startswith("//")
        or ".." in PurePosixPath(receipt_path).parts
        or PurePosixPath(receipt_path).as_posix() != receipt_path
    ):
        raise RecoveryBundleVerificationError(f"{label} identity/command differs")
    try:
        command_index = command_argv.index("test-receipt")
    except ValueError as exc:
        raise RecoveryBundleVerificationError(
            f"{label} command omits test-receipt"
        ) from exc
    expected_tail: list[Any] = [
        "test-receipt",
        "--kind",
        kind,
        "--code-freeze-commit",
        code_freeze,
    ]
    if kind == "target_host" and isinstance(receipt.get("target_host"), Mapping):
        original_parent = PurePosixPath(receipt_path).parent
        expected_tail.extend(
            [
                "--host-created-at-utc",
                receipt["target_host"].get("created_at_utc"),
                "--qualification-ownership",
                (original_parent / TARGET_QUALIFICATION_OWNERSHIP_NAME).as_posix(),
                "--qualification-landlock",
                (original_parent / TARGET_QUALIFICATION_LANDLOCK_NAME).as_posix(),
                "--qualification-cuda-preflight",
                (original_parent / TARGET_QUALIFICATION_CUDA_NAME).as_posix(),
            ]
        )
    expected_tail.extend(["--output", receipt_path])
    if command_argv[command_index:] != expected_tail or receipt["pytest_argv"] != list(
        FOCUSED_PYTEST_ARGV
    ):
        raise RecoveryBundleVerificationError(f"{label} frozen command differs")

    interpreter = _mapping(receipt["interpreter"], f"{label}.interpreter")
    _exact_keys(
        interpreter,
        ("executable", "implementation", "version", "cache_tag"),
        f"{label}.interpreter",
    )
    interpreter_executable = _string(
        interpreter["executable"], f"{label}.interpreter.executable"
    )
    if not interpreter_executable.startswith("/"):
        raise RecoveryBundleVerificationError(
            f"{label}.interpreter.executable is not absolute"
        )
    for name in ("implementation", "version", "cache_tag"):
        _string(interpreter[name], f"{label}.interpreter.{name}")
    platform_record = _mapping(receipt["platform"], f"{label}.platform")
    _exact_keys(
        platform_record,
        ("system", "release", "version", "machine"),
        f"{label}.platform",
    )
    for name in ("system", "release", "version", "machine"):
        _string(platform_record[name], f"{label}.platform.{name}")

    dependencies = _list(receipt["dependencies"], f"{label}.dependencies")
    dependency_names: list[str] = []
    dependency_map: dict[str, str] = {}
    for index, item in enumerate(dependencies):
        row_label = f"{label}.dependencies[{index}]"
        row = _mapping(item, row_label)
        _exact_keys(row, ("name", "version"), row_label)
        name = _string(row["name"], f"{row_label}.name")
        version = _string(row["version"], f"{row_label}.version")
        if name != name.lower().replace("_", "-"):
            raise RecoveryBundleVerificationError(f"{row_label}.name is noncanonical")
        dependency_names.append(name)
        dependency_map[name] = version
    if dependency_names != sorted(set(dependency_names)) or receipt[
        "dependency_inventory_sha256"
    ] != canonical_sha256(dependencies):
        raise RecoveryBundleVerificationError(f"{label} dependency inventory differs")

    id_keys = (
        "collected_ids",
        "passed_ids",
        "failed_ids",
        "skipped_ids",
        "not_run_ids",
    )
    ids: dict[str, set[str]] = {}
    for name in id_keys:
        rows = _list(receipt[name], f"{label}.{name}")
        if any(
            not isinstance(node_id, str) or not node_id for node_id in rows
        ) or rows != sorted(set(rows)):
            raise RecoveryBundleVerificationError(f"{label}.{name} differs")
        ids[name] = set(rows)
    partitions = (
        ids["passed_ids"],
        ids["failed_ids"],
        ids["skipped_ids"],
        ids["not_run_ids"],
    )
    collected = ids["collected_ids"]
    if (
        any(
            left & right
            for index, left in enumerate(partitions)
            for right in partitions[index + 1 :]
        )
        or set().union(*partitions) != collected
        or not collected
        or ids["failed_ids"]
        or ids["not_run_ids"]
        or receipt["collected_count"] != len(collected)
        or receipt["passed_count"] != len(ids["passed_ids"])
        or receipt["failed_count"] != len(ids["failed_ids"])
        or receipt["skipped_count"] != len(ids["skipped_ids"])
        or receipt["not_run_count"] != len(ids["not_run_ids"])
        or receipt["exit_code"] != 0
        or receipt["designated_target_ids"] != list(TARGET_DESIGNATED_TEST_IDS)
        or not set(TARGET_DESIGNATED_TEST_IDS) <= collected
    ):
        raise RecoveryBundleVerificationError(f"{label} test outcomes differ")
    started_at = _parse_utc(receipt["started_at_utc"], f"{label}.started_at_utc")
    completed_at = _parse_utc(receipt["completed_at_utc"], f"{label}.completed_at_utc")
    if completed_at < started_at or (
        authorized_at is not None and completed_at > authorized_at
    ):
        raise RecoveryBundleVerificationError(f"{label} clocks differ")

    if kind == "local":
        if (
            receipt["target_host"] is not None
            or receipt["qualification_probe"] is not None
            or any(
                item is not None
                for item in (
                    qualification_ownership,
                    qualification_landlock,
                    qualification_cuda,
                    qualification_ownership_path,
                    qualification_landlock_path,
                    qualification_cuda_path,
                )
            )
            or observed_head != code_freeze
        ):
            raise RecoveryBundleVerificationError(f"{label} host/commit differs")
        return dict(receipt)
    if kind != "target_host":
        raise RecoveryBundleVerificationError(f"{label} kind differs")
    target = _mapping(receipt["target_host"], f"{label}.target_host")
    probe_summary = _mapping(
        receipt["qualification_probe"], f"{label}.qualification_probe"
    )
    if (
        qualification_ownership is None
        or qualification_ownership_path is None
        or qualification_landlock is None
        or qualification_cuda is None
        or qualification_landlock_path is None
        or qualification_cuda_path is None
    ):
        raise RecoveryBundleVerificationError(
            f"{label} qualification evidence is missing"
        )
    _exact_keys(
        target,
        (
            "pod_id",
            "volume_id",
            "data_center_id",
            "kernel_release",
            "landlock_abi",
            "gpu",
            "created_at_utc",
            "test_started_host_age_seconds",
            "test_completed_host_age_seconds",
        ),
        f"{label}.target_host",
    )
    gpu = _mapping(target["gpu"], f"{label}.target_host.gpu")
    _exact_keys(
        gpu,
        ("device_count", "device_name", "device_capability", "total_memory_bytes"),
        f"{label}.target_host.gpu",
    )
    capability = _list(
        gpu["device_capability"], f"{label}.target_host.gpu.device_capability"
    )
    host_created_at = _parse_utc(
        target["created_at_utc"], f"{label}.target_host.created_at_utc"
    )
    validated_ownership, probe_completed_at = _validate_qualification_chain(
        ownership=qualification_ownership,
        landlock=qualification_landlock,
        cuda=qualification_cuda,
        ownership_path=qualification_ownership_path,
        landlock_path=qualification_landlock_path,
        cuda_path=qualification_cuda_path,
        expected_source_test_files=expected_source_test_files,
        probe_summary=probe_summary,
    )
    if (
        platform_record["system"] != "Linux"
        or _string(target["kernel_release"], f"{label}.target_host.kernel_release")
        != platform_record["release"]
        or _integer(target["landlock_abi"], f"{label}.target_host.landlock_abi")
        < POLICY_ABI
        or gpu["device_count"] != 1
        or "B200"
        not in _string(gpu["device_name"], f"{label}.target_host.gpu.device_name")
        or len(capability) != 2
        or any(
            isinstance(item, bool) or not isinstance(item, int) for item in capability
        )
        or _integer(
            gpu["total_memory_bytes"],
            f"{label}.target_host.gpu.total_memory_bytes",
        )
        < 160 * 1024**3
        or not set(TARGET_DESIGNATED_TEST_IDS) <= ids["passed_ids"]
        or bool(set(TARGET_DESIGNATED_TEST_IDS) & ids["skipped_ids"])
        or any(
            dependency_map.get(name) != version
            for name, version in EXPECTED_PACKAGES.items()
        )
        or not isinstance(target["pod_id"], str)
        or not target["pod_id"]
        or observed_head != code_freeze
        or target["pod_id"] != validated_ownership["pod_id"]
        or target["volume_id"] != NETWORK_VOLUME_ID
        or target["data_center_id"] != DATA_CENTER_ID
        or target["created_at_utc"] != validated_ownership["created_at"]
        or target["test_started_host_age_seconds"]
        != (started_at - host_created_at).total_seconds()
        or target["test_completed_host_age_seconds"]
        != (completed_at - host_created_at).total_seconds()
        or started_at < host_created_at
        or probe_completed_at > started_at
        or probe_summary["provider"]
        != {
            "pod_id": target["pod_id"],
            "volume_id": target["volume_id"],
            "data_center_id": target["data_center_id"],
        }
    ):
        raise RecoveryBundleVerificationError(f"{label} target environment differs")
    return dict(receipt)


def _validate_git_ref(value: Any, label: str, *, prefix: str) -> str:
    ref = _string(value, label)
    if not ref.startswith(prefix):
        raise RecoveryBundleVerificationError(f"{label} prefix differs")
    branch = ref.removeprefix(prefix)
    components = branch.split("/")
    forbidden = set(" ~^:?*[\\")
    if (
        not branch
        or branch.startswith("/")
        or branch.endswith("/")
        or "//" in branch
        or ".." in branch
        or "@{" in branch
        or branch.endswith(".lock")
        or any(
            not part
            or part.startswith(".")
            or part.endswith(".")
            or any(character in forbidden or ord(character) < 32 for character in part)
            for part in components
        )
    ):
        raise RecoveryBundleVerificationError(f"{label} is not a sane git ref")
    return branch


def _validate_review(
    value: Any,
    closure: Sequence[Mapping[str, Any]],
    *,
    git_head_commit: Any,
    local_test_receipt: Mapping[str, Any],
    target_host_test_receipt: Mapping[str, Any],
    qualification_ownership: Mapping[str, Any],
    qualification_landlock: Mapping[str, Any],
    qualification_cuda: Mapping[str, Any],
) -> None:
    review = _mapping(value, "authorization.review")
    _exact_keys(
        review,
        (
            "model",
            "provider_status",
            "response_id",
            "input_tokens",
            "output_tokens",
            "reasoning_tokens",
            "reconstructed_cost_usd",
            "provider_approval_claimed",
            "provider_terminal_verdict",
            "provider_ready_to_freeze_verdict",
            "source_and_tests_reviewed_by_provider",
            "reviewed_packet_was_pre_fix",
            "final_source_reviewed_by_provider",
            "provider_reviewed_final_bytes_unchanged",
            "reviewed_packet_git_head_commit",
            "code_freeze_commit",
            "source_test_inventory_sha256",
            "historical_v2_terminal_verdict",
            "historical_v2_adjudication_receipt_sha256",
            "historical_v2_remaining_blocking_findings",
            "finding_ids",
            "review_sha256",
            "adjudication_receipt_sha256",
            "adjudication_json_sha256",
            "adjudication_markdown_sha256",
            "fixed_finding_ids",
            "rejected_finding_ids",
            "reviewed_local_test_receipt_file_sha256",
            "reviewed_local_test_receipt_receipt_sha256",
            "reviewed_target_host_test_receipt_file_sha256",
            "reviewed_target_host_test_receipt_receipt_sha256",
            "reviewed_target_qualification_ownership_file_sha256",
            "reviewed_target_qualification_ownership_receipt_sha256",
            "reviewed_target_qualification_landlock_file_sha256",
            "reviewed_target_qualification_landlock_receipt_sha256",
            "reviewed_target_qualification_cuda_file_sha256",
            "reviewed_target_qualification_cuda_receipt_sha256",
            "historical_v2_paid_call_count",
            "completed_v3_paid_call_count",
            "cumulative_disclosed_paid_call_count",
        ),
        "authorization.review",
    )
    findings = _list(review["finding_ids"], "authorization.review.finding_ids")
    response_id = _string(review["response_id"], "authorization.review.response_id")
    cost = _number(
        review["reconstructed_cost_usd"],
        "authorization.review.reconstructed_cost_usd",
    )
    reviewed_packet_commit = _string(
        review["reviewed_packet_git_head_commit"],
        "authorization.review.reviewed_packet_git_head_commit",
    )
    code_freeze_commit = _string(
        review["code_freeze_commit"],
        "authorization.review.code_freeze_commit",
    )
    final_commit = _string(git_head_commit, "authorization.git_head_commit")
    if (
        review["model"] != "gpt-5.6-sol"
        or review["provider_status"] != "completed"
        or not response_id.startswith("resp_")
        or _integer(
            review["input_tokens"],
            "authorization.review.input_tokens",
            minimum=1,
        )
        < 1
        or _integer(
            review["output_tokens"],
            "authorization.review.output_tokens",
            minimum=1,
        )
        < 1
        or _integer(
            review["reasoning_tokens"],
            "authorization.review.reasoning_tokens",
        )
        < 0
        or not 0 < cost <= COMPLETED_REVIEW_COST_CEILING_USD
        or review["provider_approval_claimed"] is not False
        or review["provider_terminal_verdict"] != "READY TO FREEZE"
        or review["provider_ready_to_freeze_verdict"] is not True
        or review["source_and_tests_reviewed_by_provider"] is not True
        or review["reviewed_packet_was_pre_fix"] is not False
        or review["final_source_reviewed_by_provider"] is not True
        or review["provider_reviewed_final_bytes_unchanged"] is not True
        or any(
            HEX40.fullmatch(value) is None
            for value in (code_freeze_commit, reviewed_packet_commit, final_commit)
        )
        or code_freeze_commit != local_test_receipt.get("code_freeze_commit")
        or code_freeze_commit != target_host_test_receipt.get("code_freeze_commit")
        or review["source_test_inventory_sha256"]
        != local_test_receipt.get("source_test_inventory_sha256")
        or review["source_test_inventory_sha256"]
        != target_host_test_receipt.get("source_test_inventory_sha256")
        or review["historical_v2_terminal_verdict"] != "NOT READY TO FREEZE"
        or review["historical_v2_adjudication_receipt_sha256"]
        != HISTORICAL_V2_ADJUDICATION_RECEIPT_SHA256
        or review["historical_v2_remaining_blocking_findings"]
        != ["B06", "B07", "B08", "B09"]
        or findings != sorted(set(findings))
        or not findings
        or any(
            not isinstance(finding, str)
            or re.fullmatch(r"[BI][0-9]{2}", finding) is None
            for finding in findings
        )
        or _integer(
            review["historical_v2_paid_call_count"],
            "authorization.review.historical_v2_paid_call_count",
            minimum=1,
        )
        != 1
        or _integer(
            review["completed_v3_paid_call_count"],
            "authorization.review.completed_v3_paid_call_count",
            minimum=1,
        )
        != 1
        or _integer(
            review["cumulative_disclosed_paid_call_count"],
            "authorization.review.cumulative_disclosed_paid_call_count",
            minimum=1,
        )
        != 4
    ):
        raise RecoveryBundleVerificationError("authorization review semantics differ")
    fixed = _list(review["fixed_finding_ids"], "authorization.review.fixed_finding_ids")
    rejected = _list(
        review["rejected_finding_ids"], "authorization.review.rejected_finding_ids"
    )
    if (
        any(
            not isinstance(finding, str)
            or re.fullmatch(r"[BI][0-9]{2}", finding) is None
            for finding in [*fixed, *rejected]
        )
        or fixed != sorted(set(fixed))
        or rejected != sorted(set(rejected))
        or set(fixed) & set(rejected)
        or sorted([*fixed, *rejected]) != findings
    ):
        raise RecoveryBundleVerificationError(
            "authorization review dispositions differ"
        )
    review_sha = _hex64(review["review_sha256"], "authorization.review.review_sha256")
    _hex64(
        review["adjudication_receipt_sha256"],
        "authorization.review.adjudication_receipt_sha256",
    )
    adjudication_json_sha = _hex64(
        review["adjudication_json_sha256"],
        "authorization.review.adjudication_json_sha256",
    )
    adjudication_markdown_sha = _hex64(
        review["adjudication_markdown_sha256"],
        "authorization.review.adjudication_markdown_sha256",
    )
    if (
        review_sha
        != _closure_hash(closure, f"{FINAL_V3_PRO_REVIEW_DIRECTORY}/review.md")
        or adjudication_json_sha
        != _closure_hash(closure, FINAL_V3_PRO_REVIEW_ADJUDICATION_JSON)
        or adjudication_markdown_sha
        != _closure_hash(closure, FINAL_V3_PRO_REVIEW_ADJUDICATION_MARKDOWN)
    ):
        raise RecoveryBundleVerificationError(
            "authorization review closure links differ"
        )
    snapshot_bindings = (
        (
            "reviewed_local_test_receipt",
            V3_LOCAL_TEST_RECEIPT_SNAPSHOT,
            local_test_receipt,
        ),
        (
            "reviewed_target_host_test_receipt",
            V3_TARGET_HOST_TEST_RECEIPT_SNAPSHOT,
            target_host_test_receipt,
        ),
        (
            "reviewed_target_qualification_ownership",
            V3_TARGET_QUALIFICATION_OWNERSHIP_SNAPSHOT,
            qualification_ownership,
        ),
        (
            "reviewed_target_qualification_landlock",
            V3_TARGET_QUALIFICATION_LANDLOCK_SNAPSHOT,
            qualification_landlock,
        ),
        (
            "reviewed_target_qualification_cuda",
            V3_TARGET_QUALIFICATION_CUDA_SNAPSHOT,
            qualification_cuda,
        ),
    )
    for prefix, snapshot_path, receipt in snapshot_bindings:
        if review[f"{prefix}_file_sha256"] != _closure_hash(
            closure, snapshot_path
        ) or review[f"{prefix}_receipt_sha256"] != receipt.get("receipt_sha256"):
            raise RecoveryBundleVerificationError(
                "authorization reviewed snapshot binding differs"
            )


def _validate_cuda_preflight(
    receipt: Mapping[str, Any],
    *,
    landlock: Mapping[str, Any],
    preflight_output_root: str,
    execution: Mapping[str, Any],
    paths: Mapping[str, str],
    bootstrap_manifest: Mapping[str, Any],
    recovery_closure: Sequence[Mapping[str, Any]],
) -> None:
    _exact_keys(
        receipt,
        (
            "schema_version",
            "status",
            "pid",
            "python_executable",
            "active_root",
            "closure_scope",
            "closure_files",
            "closure_file_count",
            "closure_inventory_sha256",
            "recovery_closure_sha256",
            "bootstrap_roots_manifest",
            "qualification_ownership_receipt_sha256",
            "landlock_receipt_sha256",
            "package_versions",
            "imported_package_versions",
            "environment",
            "absent_environment_variables",
            "provider",
            "cuda",
            "model_forward_count",
            "torch_module_call_count",
            "target_prompt_render_count",
            "target_feature_vector_count",
            "external_or_prior_outcome_inputs",
            "bootstrap",
            "completed_at_utc",
            "receipt_sha256",
        ),
        "preflight_cuda",
    )
    closure = list(recovery_closure)
    root_paths = sorted(str(row["path"]) for row in bootstrap_manifest["roots"])
    expected_bootstrap_commitment = {
        "path": paths["roots_manifest"],
        "file_sha256": execution["roots_manifest_sha256"],
        "receipt_sha256": bootstrap_manifest["receipt_sha256"],
        "roots_inventory_sha256": bootstrap_manifest["roots_inventory_sha256"],
        "bootstrap_sha256": bootstrap_manifest["bootstrap_sha256"],
        "active_root": execution["active_root"],
        "python_executable": execution["python_executable"],
        "root_paths": root_paths,
        "sys_path": bootstrap_manifest["sys_path"],
    }
    environment = _mapping(receipt["environment"], "preflight_cuda.environment")
    _exact_keys(
        environment,
        (*FIXED_ENVIRONMENT, *DYNAMIC_ENVIRONMENT),
        "preflight_cuda.environment",
    )
    if any(
        environment[name] != expected for name, expected in FIXED_ENVIRONMENT.items()
    ):
        raise RecoveryBundleVerificationError(
            "preflight CUDA fixed environment differs"
        )
    if any(
        not isinstance(environment[name], str)
        or not _inside_posix(preflight_output_root, environment[name])
        for name in DYNAMIC_ENVIRONMENT
    ):
        raise RecoveryBundleVerificationError(
            "preflight CUDA writable environment escapes"
        )
    if receipt["absent_environment_variables"] != list(FORBIDDEN_ENVIRONMENT):
        raise RecoveryBundleVerificationError(
            "preflight CUDA absent environment inventory differs"
        )
    provider = _mapping(receipt["provider"], "preflight_cuda.provider")
    _exact_keys(
        provider,
        ("pod_id", "volume_id", "data_center_id"),
        "preflight_cuda.provider",
    )
    if (
        not isinstance(provider["pod_id"], str)
        or not provider["pod_id"]
        or provider["volume_id"] != NETWORK_VOLUME_ID
        or provider["data_center_id"] != DATA_CENTER_ID
    ):
        raise RecoveryBundleVerificationError("preflight CUDA provider differs")
    cuda = _mapping(receipt["cuda"], "preflight_cuda.cuda")
    _exact_keys(
        cuda,
        (
            "available",
            "device",
            "device_count",
            "device_name",
            "device_capability",
            "dtype",
            "shape",
            "matmul_finite",
            "synchronized",
            "raw_tensor_operations_only",
        ),
        "preflight_cuda.cuda",
    )
    capability = cuda["device_capability"]
    if (
        receipt["schema_version"] != SCHEMA_VERSION
        or receipt["status"] != "pass_target_free_landlock_cuda_preflight"
        or receipt["pid"] != landlock["pid"]
        or receipt["python_executable"] != execution["python_executable"]
        or receipt["active_root"] != execution["active_root"]
        or receipt["closure_scope"] != "final_recovery"
        or receipt["closure_files"] != closure
        or receipt["closure_file_count"] != len(closure)
        or receipt["closure_inventory_sha256"] != canonical_sha256(closure)
        or receipt["recovery_closure_sha256"] != canonical_sha256(closure)
        or receipt["bootstrap_roots_manifest"] != expected_bootstrap_commitment
        or receipt["qualification_ownership_receipt_sha256"] is not None
        or receipt["landlock_receipt_sha256"] != landlock["receipt_sha256"]
        or receipt["package_versions"] != EXPECTED_PACKAGES
        or receipt["imported_package_versions"] != EXPECTED_IMPORTED_PACKAGES
        or receipt["model_forward_count"] != 0
        or receipt["torch_module_call_count"] != 0
        or receipt["target_prompt_render_count"] != 0
        or receipt["target_feature_vector_count"] != 0
        or receipt["external_or_prior_outcome_inputs"] != []
        or cuda["available"] is not True
        or cuda["device"] != "cuda:0"
        or cuda["device_count"] != 1
        or not isinstance(cuda["device_name"], str)
        or not cuda["device_name"]
        or not isinstance(capability, list)
        or len(capability) != 2
        or any(
            isinstance(value, bool) or not isinstance(value, int)
            for value in capability
        )
        or cuda["dtype"] != "torch.bfloat16"
        or cuda["shape"] != [16, 16]
        or cuda["matmul_finite"] is not True
        or cuda["synchronized"] is not True
        or cuda["raw_tensor_operations_only"] is not True
    ):
        raise RecoveryBundleVerificationError(
            "preflight package/CUDA/zero-forward result differs"
        )
    _validate_bootstrap_phase(
        receipt["bootstrap"],
        phase=BOOTSTRAP_PREFLIGHT_PHASE,
        mode="preflight-child",
        pid=int(landlock["pid"]),
        execution=execution,
        paths=paths,
        manifest=bootstrap_manifest,
    )
    _string(receipt["completed_at_utc"], "preflight_cuda.completed_at_utc")


def _validate_authorization(
    authorization: Mapping[str, Any],
    *,
    bootstrap_manifest: Mapping[str, Any],
    bootstrap_manifest_path: Path,
    preflight_landlock: Mapping[str, Any],
    preflight_cuda: Mapping[str, Any],
    preflight_landlock_path: Path,
    preflight_cuda_path: Path,
    local_test_receipt: Mapping[str, Any],
    target_host_test_receipt: Mapping[str, Any],
    local_test_receipt_path: Path,
    target_host_test_receipt_path: Path,
    qualification_ownership: Mapping[str, Any],
    qualification_landlock: Mapping[str, Any],
    qualification_cuda: Mapping[str, Any],
    qualification_ownership_path: Path,
    qualification_landlock_path: Path,
    qualification_cuda_path: Path,
) -> tuple[Mapping[str, Any], dict[str, str], str, float, float]:
    _exact_keys(
        authorization,
        (
            "schema_version",
            "status",
            "study_id",
            "protocol_version",
            "recovery_protocol_version",
            "run_id",
            "raw_root",
            "raw_run_receipt_sha256",
            "plan_manifest_sha256",
            "recovery_bound_files",
            "recovery_bound_paths_sha256",
            "historical_provenance_files",
            "historical_provenance_inventory_sha256",
            "bootstrap_import_roots",
            "external_files",
            "original_receipts",
            "superseded_recovery_host",
            "fresh_receipts",
            "preflight",
            "test_receipts",
            "fresh_pod_id",
            "volume_id",
            "data_center_id",
            "gpu_type",
            "gpu_count",
            "recovery_started_at_unix",
            "recovery_deadline_at_unix",
            "provider_deadline_at_unix",
            "max_walltime_seconds",
            "hourly_price_usd",
            "max_spend_usd",
            "authorized_at_utc",
            "model_forward_limit",
            "target_prompt_render_limit",
            "target_feature_vector_limit",
            "external_or_prior_outcome_inputs",
            "write_confinement",
            "execution",
            "review",
            "git_head_commit",
            "git_remote_ref",
            "git_local_remote_ref",
            "git_local_remote_commit",
            "git_live_remote_commit",
            "receipt_sha256",
        ),
        "authorization",
    )
    if (
        authorization["schema_version"] != SCHEMA_VERSION
        or authorization["status"] != "authorized_audit_only_recovery_landlock_confined"
        or authorization["study_id"] != STUDY_ID
        or authorization["protocol_version"] != PROTOCOL_VERSION
        or authorization["recovery_protocol_version"] != RECOVERY_PROTOCOL_VERSION
        or authorization["run_id"] != RUN_ID
        or authorization["raw_root"] != f"/workspace/{RAW_RELATIVE}"
        or authorization["raw_run_receipt_sha256"] != ORIGINAL_RUN_RECEIPT_SHA256
        or authorization["plan_manifest_sha256"] != PLAN_MANIFEST_SHA256
        or authorization["volume_id"] != NETWORK_VOLUME_ID
        or authorization["data_center_id"] != DATA_CENTER_ID
        or authorization["gpu_type"] != GPU_TYPE
        or authorization["gpu_count"] != 1
        or authorization["max_walltime_seconds"] != 3600
        or authorization["hourly_price_usd"] != 6.0
        or authorization["max_spend_usd"] != 6.0
        or authorization["model_forward_limit"] != 0
        or authorization["target_prompt_render_limit"] != 0
        or authorization["target_feature_vector_limit"] != 0
        or authorization["external_or_prior_outcome_inputs"] != []
        or authorization["write_confinement"] != LANDLOCK_POLICY
        or authorization["superseded_recovery_host"] != SUPERSEDED_RECOVERY_HOST
    ):
        raise RecoveryBundleVerificationError(
            "authorization identity/science boundary differs"
        )
    started = _number(
        authorization["recovery_started_at_unix"],
        "authorization.recovery_started_at_unix",
    )
    deadline = _number(
        authorization["recovery_deadline_at_unix"],
        "authorization.recovery_deadline_at_unix",
    )
    provider_deadline = _number(
        authorization["provider_deadline_at_unix"],
        "authorization.provider_deadline_at_unix",
    )
    authorized_at = _parse_utc(
        authorization["authorized_at_utc"], "authorization.authorized_at_utc"
    )
    authorized = authorized_at.timestamp()
    if (
        deadline - started != 3600
        or deadline >= provider_deadline
        or not started <= authorized < deadline
        or deadline - authorized < 1800
    ):
        raise RecoveryBundleVerificationError(
            "authorization ownership-bound clocks differ"
        )
    closure = _validate_file_rows(
        authorization["recovery_bound_files"],
        "authorization.recovery_bound_files",
        expected_paths=RECOVERY_BOUND_PATHS,
    )
    if authorization["recovery_bound_paths_sha256"] != canonical_sha256(
        RECOVERY_BOUND_PATHS
    ):
        raise RecoveryBundleVerificationError(
            "authorization recovery path hash differs"
        )
    if any(
        _closure_hash(closure, path) != expected_sha256
        for path, expected_sha256 in {
            **HISTORICAL_INCOMPLETE_REVIEW_PHYSICAL_SHA256,
            **HISTORICAL_V2_PRO_REVIEW_PHYSICAL_SHA256,
        }.items()
    ):
        raise RecoveryBundleVerificationError(
            "immutable historical review physical evidence differs"
        )
    provenance = _validate_file_rows(
        authorization["historical_provenance_files"],
        "authorization.historical_provenance_files",
    )
    if authorization["historical_provenance_inventory_sha256"] != canonical_sha256(
        provenance
    ):
        raise RecoveryBundleVerificationError(
            "authorization historical provenance inventory hash differs"
        )
    _validate_review(
        authorization["review"],
        closure,
        git_head_commit=authorization["git_head_commit"],
        local_test_receipt=local_test_receipt,
        target_host_test_receipt=target_host_test_receipt,
        qualification_ownership=qualification_ownership,
        qualification_landlock=qualification_landlock,
        qualification_cuda=qualification_cuda,
    )
    git_head = _string(
        authorization["git_head_commit"], "authorization.git_head_commit"
    )
    local_commit = _string(
        authorization["git_local_remote_commit"],
        "authorization.git_local_remote_commit",
    )
    live_commit = _string(
        authorization["git_live_remote_commit"],
        "authorization.git_live_remote_commit",
    )
    branch = _validate_git_ref(
        authorization["git_remote_ref"],
        "authorization.git_remote_ref",
        prefix="refs/heads/",
    )
    local_branch = _validate_git_ref(
        authorization["git_local_remote_ref"],
        "authorization.git_local_remote_ref",
        prefix="refs/remotes/origin/",
    )
    if (
        any(
            HEX40.fullmatch(value) is None
            for value in (git_head, local_commit, live_commit)
        )
        or git_head != local_commit
        or git_head != live_commit
        or branch != local_branch
    ):
        raise RecoveryBundleVerificationError("authorization git head differs")
    execution = _mapping(authorization["execution"], "authorization.execution")
    _exact_keys(
        execution,
        (
            "attempt_id",
            "attempt_root",
            "paths",
            "artifact_device",
            "device_files",
            "launcher_mode",
            "active_root",
            "python_executable",
            "roots_manifest_sha256",
            "confined_child_argv",
            "confined_child_argv_sha256",
            "command_sha256",
        ),
        "authorization.execution",
    )
    attempt_id = _string(execution["attempt_id"], "authorization.execution.attempt_id")
    if (
        ATTEMPT_ID_RE.fullmatch(attempt_id) is None
        or not attempt_id.startswith(f"calv2-r3-audit-recovery-{git_head[:7]}-")
        or execution["attempt_root"]
        != (PurePosixPath(RECOVERY_ATTEMPT_PARENT) / attempt_id).as_posix()
    ):
        raise RecoveryBundleVerificationError("authorization attempt identity differs")
    expected_paths = _expected_paths(attempt_id)
    if execution["paths"] != expected_paths:
        raise RecoveryBundleVerificationError("authorization execution paths differ")
    devices = _list(execution["device_files"], "authorization.execution.device_files")
    if (
        devices != sorted(set(devices))
        or not devices
        or any(
            not isinstance(path, str) or NVIDIA_DEVICE_PATH.fullmatch(path) is None
            for path in devices
        )
        or execution["artifact_device"] != "cuda:0"
        or execution["launcher_mode"] != "audit_recovery"
        or execution["active_root"]
        != f"/root/consciousness_sae_audit_recovery/{attempt_id}/active"
        or not isinstance(execution["python_executable"], str)
        or not execution["python_executable"].startswith("/")
        or execution["roots_manifest_sha256"] != sha256_file(bootstrap_manifest_path)
    ):
        raise RecoveryBundleVerificationError(
            "authorization executable/device binding differs"
        )
    expected_argv = _expected_confined_argv(
        execution["python_executable"],
        execution["active_root"],
        attempt_id,
        expected_paths,
        execution["roots_manifest_sha256"],
        devices,
    )
    if execution["confined_child_argv"] != expected_argv or execution[
        "confined_child_argv_sha256"
    ] != canonical_sha256(expected_argv):
        raise RecoveryBundleVerificationError("authorization confined command differs")
    execution_core = dict(execution)
    command_sha256 = _hex64(
        execution_core.pop("command_sha256"), "authorization.execution.command_sha256"
    )
    if command_sha256 != canonical_sha256(execution_core):
        raise RecoveryBundleVerificationError("authorization command hash differs")
    validated_manifest = _validate_bootstrap_manifest(
        bootstrap_manifest,
        execution=execution,
        paths=expected_paths,
        closure=closure,
    )
    bootstrap_binding = _mapping(
        authorization["bootstrap_import_roots"],
        "authorization.bootstrap_import_roots",
    )
    _exact_keys(
        bootstrap_binding,
        ("path", "physical_file", "manifest"),
        "authorization.bootstrap_import_roots",
    )
    if (
        bootstrap_binding["path"] != expected_paths["roots_manifest"]
        or bootstrap_binding["manifest"] != validated_manifest
    ):
        raise RecoveryBundleVerificationError(
            "authorization bootstrap import-root binding differs"
        )
    _file_record_matches(
        bootstrap_binding["physical_file"],
        bootstrap_manifest_path,
        "authorization.bootstrap_import_roots.physical_file",
    )
    preflight = _mapping(authorization["preflight"], "authorization.preflight")
    _exact_keys(
        preflight,
        (
            "landlock_receipt",
            "landlock_file",
            "probe_receipt",
            "probe_file",
            "device_rules",
        ),
        "authorization.preflight",
    )
    if (
        preflight["landlock_receipt"] != preflight_landlock
        or preflight["probe_receipt"] != preflight_cuda
        or preflight["device_rules"] != preflight_landlock["device_rules"]
    ):
        raise RecoveryBundleVerificationError(
            "authorization preflight receipt links differ"
        )
    _file_record_matches(
        preflight["landlock_file"],
        preflight_landlock_path,
        "authorization.preflight.landlock_file",
    )
    _file_record_matches(
        preflight["probe_file"],
        preflight_cuda_path,
        "authorization.preflight.probe_file",
    )
    external = _mapping(authorization["external_files"], "authorization.external_files")
    if set(external) != EXTERNAL_FILE_KEYS:
        raise RecoveryBundleVerificationError(
            "authorization.external_files keys differ"
        )
    for name in sorted(EXTERNAL_FILE_KEYS):
        _validate_detached_file_record(
            external[name], f"authorization.external_files.{name}"
        )
    _file_record_matches(
        external["preflight_landlock"],
        preflight_landlock_path,
        "authorization.external_files.preflight_landlock",
    )
    _file_record_matches(
        external["preflight_probe"],
        preflight_cuda_path,
        "authorization.external_files.preflight_probe",
    )
    _file_record_matches(
        external["local_test_receipt"],
        local_test_receipt_path,
        "authorization.external_files.local_test_receipt",
    )
    _file_record_matches(
        external["target_host_test_receipt"],
        target_host_test_receipt_path,
        "authorization.external_files.target_host_test_receipt",
    )
    _file_record_matches(
        external["target_qualification_ownership"],
        qualification_ownership_path,
        "authorization.external_files.target_qualification_ownership",
    )
    _file_record_matches(
        external["target_qualification_landlock"],
        qualification_landlock_path,
        "authorization.external_files.target_qualification_landlock",
    )
    _file_record_matches(
        external["target_qualification_cuda_preflight"],
        qualification_cuda_path,
        "authorization.external_files.target_qualification_cuda_preflight",
    )
    _file_record_matches(
        external["roots_manifest"],
        bootstrap_manifest_path,
        "authorization.external_files.roots_manifest",
    )
    reviewed_snapshot_bindings = {
        V3_LOCAL_TEST_RECEIPT_SNAPSHOT: "local_test_receipt",
        V3_TARGET_HOST_TEST_RECEIPT_SNAPSHOT: "target_host_test_receipt",
        V3_TARGET_QUALIFICATION_OWNERSHIP_SNAPSHOT: ("target_qualification_ownership"),
        V3_TARGET_QUALIFICATION_LANDLOCK_SNAPSHOT: "target_qualification_landlock",
        V3_TARGET_QUALIFICATION_CUDA_SNAPSHOT: ("target_qualification_cuda_preflight"),
    }
    for snapshot_path, external_key in reviewed_snapshot_bindings.items():
        if _closure_file_record(closure, snapshot_path) != external[external_key]:
            raise RecoveryBundleVerificationError(
                "v3 reviewed receipt snapshot differs from authorization evidence"
            )
    original_receipts = _mapping(
        authorization["original_receipts"], "authorization.original_receipts"
    )
    if original_receipts != ORIGINAL_RECEIPTS:
        raise RecoveryBundleVerificationError(
            "authorization original receipt chain differs"
        )
    fresh_receipts = _mapping(
        authorization["fresh_receipts"], "authorization.fresh_receipts"
    )
    _exact_keys(
        fresh_receipts,
        ("ownership", "guest", "cache"),
        "authorization.fresh_receipts",
    )
    for name in ("ownership", "guest", "cache"):
        _hex64(fresh_receipts[name], f"authorization.fresh_receipts.{name}")
    fresh_pod_id = _string(authorization["fresh_pod_id"], "authorization.fresh_pod_id")
    if preflight_cuda["provider"]["pod_id"] != fresh_pod_id:
        raise RecoveryBundleVerificationError(
            "authorization fresh pod/preflight provider link differs"
        )
    source_test_files = [
        row for row in closure if str(row["path"]) in set(SOURCE_TEST_BOUND_PATHS)
    ]
    if [str(row["path"]) for row in source_test_files] != list(SOURCE_TEST_BOUND_PATHS):
        raise RecoveryBundleVerificationError(
            "authorization source/test closure differs"
        )
    validated_local_test_receipt = _validate_test_receipt(
        local_test_receipt,
        kind="local",
        expected_source_test_files=source_test_files,
        authorized_at=authorized_at,
    )
    validated_target_host_test_receipt = _validate_test_receipt(
        target_host_test_receipt,
        kind="target_host",
        expected_source_test_files=source_test_files,
        qualification_ownership=qualification_ownership,
        qualification_landlock=qualification_landlock,
        qualification_cuda=qualification_cuda,
        qualification_ownership_path=qualification_ownership_path,
        qualification_landlock_path=qualification_landlock_path,
        qualification_cuda_path=qualification_cuda_path,
        authorized_at=authorized_at,
    )
    test_receipts = _mapping(
        authorization["test_receipts"], "authorization.test_receipts"
    )
    _exact_keys(test_receipts, ("local", "target_host"), "authorization.test_receipts")
    if (
        test_receipts["local"] != validated_local_test_receipt
        or test_receipts["target_host"] != validated_target_host_test_receipt
        or validated_local_test_receipt["code_freeze_commit"]
        != validated_target_host_test_receipt["code_freeze_commit"]
        or validated_target_host_test_receipt["target_host"]["pod_id"] == fresh_pod_id
    ):
        raise RecoveryBundleVerificationError(
            "authorization test receipt chain differs"
        )
    if (
        authorization["superseded_recovery_host"]["attempt_id"]
        == execution["attempt_id"]
        or authorization["superseded_recovery_host"]["pod_id"] == fresh_pod_id
    ):
        raise RecoveryBundleVerificationError(
            "superseded/current recovery host schemas overlap"
        )
    return execution, expected_paths, command_sha256, started, deadline


def _validate_marker(
    marker: Mapping[str, Any],
    *,
    authorization: Mapping[str, Any],
    execution: Mapping[str, Any],
    confinement: Mapping[str, Any],
    started: float,
    deadline: float,
) -> float:
    _exact_keys(
        marker,
        (
            "schema_version",
            "status",
            "study_id",
            "run_id",
            "attempt_id",
            "claimed_at_utc",
            "claimed_at_unix",
            "recovery_authorization_receipt_sha256",
            "landlock_confinement_receipt_sha256",
            "landlock_pid",
            "command_sha256",
            "recovery_source_sha256",
            "receipt_sha256",
        ),
        "attempt_marker",
    )
    claimed = _number(marker["claimed_at_unix"], "attempt_marker.claimed_at_unix")
    if (
        marker["schema_version"] != SCHEMA_VERSION
        or marker["status"] != "claimed_exactly_once"
        or marker["study_id"] != authorization["study_id"]
        or marker["run_id"] != authorization["run_id"]
        or marker["attempt_id"] != execution["attempt_id"]
        or marker["recovery_authorization_receipt_sha256"]
        != authorization["receipt_sha256"]
        or marker["landlock_confinement_receipt_sha256"]
        != confinement["receipt_sha256"]
        or marker["landlock_pid"] != confinement["pid"]
        or marker["command_sha256"] != execution["command_sha256"]
        or not started <= claimed < deadline
    ):
        raise RecoveryBundleVerificationError("attempt marker cross-links differ")
    _string(marker["claimed_at_utc"], "attempt_marker.claimed_at_utc")
    _hex64(marker["recovery_source_sha256"], "attempt_marker.recovery_source_sha256")
    return claimed


def _validate_nested_receipt(
    recovery: Mapping[str, Any],
    key: str,
    hash_key: str,
    expected: Mapping[str, Any] | None = None,
) -> Mapping[str, Any]:
    value = _mapping(recovery.get(key), f"recovery_audit.{key}")
    digest = _self_hash(value, f"recovery_audit.{key}")
    if recovery.get(hash_key) != digest or (expected is not None and value != expected):
        raise RecoveryBundleVerificationError(f"recovery_audit.{key} link differs")
    return value


def _validate_rehash_pair(
    recovery: Mapping[str, Any],
    *,
    pre_key: str,
    post_key: str,
    unchanged_key: str,
    exact_fields: Sequence[str],
    expected: Mapping[str, Any],
    label: str,
) -> None:
    pre = _validate_nested_receipt(recovery, pre_key, f"{pre_key}_sha256")
    post = _validate_nested_receipt(recovery, post_key, f"{post_key}_sha256")
    _exact_keys(pre, exact_fields, f"recovery_audit.{pre_key}")
    _exact_keys(post, exact_fields, f"recovery_audit.{post_key}")
    for name, expected_value in expected.items():
        if pre[name] != expected_value or post[name] != expected_value:
            raise RecoveryBundleVerificationError(f"{label} pre/post {name} differs")
    pre_inventory = _hex64(
        pre.get("file_inventory_sha256"),
        f"recovery_audit.{pre_key}.file_inventory_sha256",
    )
    post_inventory = _hex64(
        post.get("file_inventory_sha256"),
        f"recovery_audit.{post_key}.file_inventory_sha256",
    )
    pre_directory_count = _integer(
        pre.get("directory_count"),
        f"recovery_audit.{pre_key}.directory_count",
    )
    post_directory_count = _integer(
        post.get("directory_count"),
        f"recovery_audit.{post_key}.directory_count",
    )
    pre_directory_inventory = _hex64(
        pre.get("directory_inventory_sha256"),
        f"recovery_audit.{pre_key}.directory_inventory_sha256",
    )
    post_directory_inventory = _hex64(
        post.get("directory_inventory_sha256"),
        f"recovery_audit.{post_key}.directory_inventory_sha256",
    )
    if (
        recovery.get(unchanged_key) is not True
        or pre_inventory != post_inventory
        or pre_directory_count != post_directory_count
        or pre_directory_inventory != post_directory_inventory
    ):
        raise RecoveryBundleVerificationError(
            f"{label} pre/post file or directory hashes differ"
        )


def _expected_directory_inventory(paths: Sequence[str]) -> list[str]:
    directories: set[str] = set()
    for value in paths:
        parent = PurePosixPath(value).parent
        while parent != PurePosixPath("."):
            directories.add(parent.as_posix())
            parent = parent.parent
    return sorted(directories)


def _validate_recovery_metadata(
    recovery: Mapping[str, Any],
    *,
    authorization: Mapping[str, Any],
    execution: Mapping[str, Any],
    preflight_landlock: Mapping[str, Any],
    preflight_cuda: Mapping[str, Any],
    confinement: Mapping[str, Any],
    marker: Mapping[str, Any],
    bootstrap_manifest: Mapping[str, Any],
    paths: Mapping[str, str],
) -> None:
    _self_hash(recovery, "recovery_audit")
    _exact_keys(
        recovery,
        (
            "recovery_protocol_version",
            "status",
            "correction",
            "provider_review_status",
            "provider_review_approval_claimed",
            "provider_review_ready_to_freeze_verdict",
            "provider_review_source_and_tests_seen",
            "provider_reviewed_packet_was_pre_fix",
            "provider_reviewed_final_source",
            "provider_reviewed_final_bytes_unchanged",
            "recovery_authorization_receipt_sha256",
            "attempt_id",
            "attempt_marker_receipt_sha256",
            "command_sha256",
            "recovery_bound_paths_sha256",
            "plan_manifest_sha256",
            "local_test_receipt_sha256",
            "target_host_test_receipt_sha256",
            "code_freeze_commit",
            "source_test_inventory_sha256",
            "recovery_plan_sha256",
            "recovery_source_sha256",
            "confined_bootstrap_sha256",
            "scientific_equivalence_source_sha256",
            "scientific_equivalence_test_sha256",
            "scientific_equivalence_json_sha256",
            "scientific_equivalence_markdown_sha256",
            "landlock_launcher_sha256",
            "bundle_verifier_sha256",
            "recovery_test_sha256",
            "confined_bootstrap_test_sha256",
            "landlock_test_sha256",
            "bundle_verifier_test_sha256",
            "historical_review_adjudication_json_sha256",
            "historical_review_adjudication_markdown_sha256",
            "historical_v2_review_adjudication_json_sha256",
            "historical_v2_review_adjudication_markdown_sha256",
            "final_v3_review_adjudication_json_sha256",
            "final_v3_review_adjudication_markdown_sha256",
            "final_v3_review_response_sha256",
            "final_v3_review_manifest_sha256",
            "reviewed_local_test_receipt_snapshot_sha256",
            "reviewed_target_host_test_receipt_snapshot_sha256",
            "reviewed_target_qualification_ownership_snapshot_sha256",
            "reviewed_target_qualification_landlock_snapshot_sha256",
            "reviewed_target_qualification_cuda_snapshot_sha256",
            "original_failed_audit_log_sha256",
            "original_raw_run_receipt_sha256",
            "original_receipts",
            "superseded_recovery_host",
            "fresh_receipts",
            "fresh_pod_id",
            "bootstrap_import_roots",
            "bootstrap_execute_entry_phase",
            "bootstrap_prepublication_phase",
            "bootstrap_postdispatch_assertion",
            "preflight_landlock_receipt",
            "preflight_landlock_receipt_sha256",
            "preflight_probe_receipt",
            "preflight_probe_receipt_sha256",
            "landlock_confinement_receipt",
            "landlock_confinement_receipt_sha256",
            "write_confinement_policy",
            "write_confinement_claim",
            "landlock_limitations",
            "executable_isolation_receipt",
            "executable_isolation_receipt_sha256",
            "provenance_pre_rehash_receipt",
            "provenance_pre_rehash_receipt_sha256",
            "provenance_post_rehash_receipt",
            "provenance_post_rehash_receipt_sha256",
            "historical_provenance_unchanged",
            "pre_rehash_receipt",
            "pre_rehash_receipt_sha256",
            "post_rehash_receipt",
            "post_rehash_receipt_sha256",
            "raw_unchanged",
            "zero_forward_guards",
            "forbidden_module_guards",
            "j_checkpoint_inventory",
            "scientific_metrics_thresholds_layers_and_rows_changed",
            "fresh_model_execution_performed",
            "target_prompt_render_count",
            "target_feature_vector_count",
            "external_or_prior_outcome_inputs",
            "receipt_sha256",
        ),
        "recovery_audit",
    )
    closure = _validate_file_rows(
        authorization["recovery_bound_files"],
        "authorization.recovery_bound_files",
        expected_paths=RECOVERY_BOUND_PATHS,
    )
    closure_links = {
        "recovery_plan_sha256": (
            "docs/consciousness_sae_target_blind_calibration/AUDIT_RECOVERY_20260714.md"
        ),
        "recovery_source_sha256": (
            "experiments/consciousness_sae_target_blind_calibration/audit_recovery.py"
        ),
        "confined_bootstrap_sha256": BOOTSTRAP_RELATIVE_PATH,
        "scientific_equivalence_source_sha256": (
            "experiments/consciousness_sae_target_blind_calibration/"
            "scientific_equivalence.py"
        ),
        "scientific_equivalence_test_sha256": (
            "tests/consciousness_sae_target_blind_calibration/"
            "test_scientific_equivalence.py"
        ),
        "scientific_equivalence_json_sha256": (
            "docs/consciousness_sae_target_blind_calibration/"
            "AUDIT_RECOVERY_SCIENTIFIC_EQUIVALENCE.json"
        ),
        "scientific_equivalence_markdown_sha256": (
            "docs/consciousness_sae_target_blind_calibration/"
            "AUDIT_RECOVERY_SCIENTIFIC_EQUIVALENCE.md"
        ),
        "landlock_launcher_sha256": (
            "experiments/consciousness_sae_target_blind_calibration/"
            "landlock_launcher.py"
        ),
        "bundle_verifier_sha256": (
            "experiments/consciousness_sae_target_blind_calibration/"
            "recovery_bundle_verifier.py"
        ),
        "recovery_test_sha256": (
            "tests/consciousness_sae_target_blind_calibration/test_audit_recovery.py"
        ),
        "confined_bootstrap_test_sha256": (
            "tests/consciousness_sae_target_blind_calibration/"
            "test_confined_bootstrap.py"
        ),
        "landlock_test_sha256": (
            "tests/consciousness_sae_target_blind_calibration/test_landlock_launcher.py"
        ),
        "bundle_verifier_test_sha256": (
            "tests/consciousness_sae_target_blind_calibration/"
            "test_recovery_bundle_verifier.py"
        ),
        "historical_review_adjudication_json_sha256": (
            HISTORICAL_INCOMPLETE_REVIEW_ADJUDICATION_JSON
        ),
        "historical_review_adjudication_markdown_sha256": (
            HISTORICAL_INCOMPLETE_REVIEW_ADJUDICATION_MARKDOWN
        ),
        "historical_v2_review_adjudication_json_sha256": (
            HISTORICAL_V2_PRO_REVIEW_ADJUDICATION_JSON
        ),
        "historical_v2_review_adjudication_markdown_sha256": (
            HISTORICAL_V2_PRO_REVIEW_ADJUDICATION_MARKDOWN
        ),
        "final_v3_review_adjudication_json_sha256": (
            FINAL_V3_PRO_REVIEW_ADJUDICATION_JSON
        ),
        "final_v3_review_adjudication_markdown_sha256": (
            FINAL_V3_PRO_REVIEW_ADJUDICATION_MARKDOWN
        ),
        "final_v3_review_response_sha256": (
            f"{FINAL_V3_PRO_REVIEW_DIRECTORY}/response.json"
        ),
        "final_v3_review_manifest_sha256": (
            f"{FINAL_V3_PRO_REVIEW_DIRECTORY}/review_manifest.json"
        ),
        "reviewed_local_test_receipt_snapshot_sha256": (V3_LOCAL_TEST_RECEIPT_SNAPSHOT),
        "reviewed_target_host_test_receipt_snapshot_sha256": (
            V3_TARGET_HOST_TEST_RECEIPT_SNAPSHOT
        ),
        "reviewed_target_qualification_ownership_snapshot_sha256": (
            V3_TARGET_QUALIFICATION_OWNERSHIP_SNAPSHOT
        ),
        "reviewed_target_qualification_landlock_snapshot_sha256": (
            V3_TARGET_QUALIFICATION_LANDLOCK_SNAPSHOT
        ),
        "reviewed_target_qualification_cuda_snapshot_sha256": (
            V3_TARGET_QUALIFICATION_CUDA_SNAPSHOT
        ),
    }
    if any(
        recovery[name] != _closure_hash(closure, path)
        for name, path in closure_links.items()
    ):
        raise RecoveryBundleVerificationError("recovery closure hash links differ")
    review = _mapping(authorization["review"], "authorization.review")
    test_receipts = _mapping(
        authorization["test_receipts"], "authorization.test_receipts"
    )
    local_test_receipt = _mapping(
        test_receipts["local"], "authorization.test_receipts.local"
    )
    target_host_test_receipt = _mapping(
        test_receipts["target_host"], "authorization.test_receipts.target_host"
    )
    if (
        recovery["recovery_protocol_version"]
        != authorization["recovery_protocol_version"]
        or recovery["status"] != "pass_disclosed_post_run_technical_recovery"
        or recovery["correction"]
        != "required_j_layers_subset_of_hash_pinned_release_inventory"
        or recovery["recovery_authorization_receipt_sha256"]
        != authorization["receipt_sha256"]
        or recovery["attempt_id"] != execution["attempt_id"]
        or recovery["attempt_marker_receipt_sha256"] != marker["receipt_sha256"]
        or recovery["command_sha256"] != execution["command_sha256"]
        or recovery["recovery_bound_paths_sha256"]
        != authorization["recovery_bound_paths_sha256"]
        or recovery["plan_manifest_sha256"] != authorization["plan_manifest_sha256"]
        or recovery["local_test_receipt_sha256"] != local_test_receipt["receipt_sha256"]
        or recovery["target_host_test_receipt_sha256"]
        != target_host_test_receipt["receipt_sha256"]
        or recovery["code_freeze_commit"] != local_test_receipt["code_freeze_commit"]
        or recovery["code_freeze_commit"]
        != target_host_test_receipt["code_freeze_commit"]
        or recovery["source_test_inventory_sha256"]
        != local_test_receipt["source_test_inventory_sha256"]
        or recovery["source_test_inventory_sha256"]
        != target_host_test_receipt["source_test_inventory_sha256"]
        or recovery["recovery_source_sha256"] != marker["recovery_source_sha256"]
        or recovery["provider_review_status"] != review["provider_status"]
        or recovery["provider_review_status"] != "completed"
        or recovery["provider_review_approval_claimed"]
        != review["provider_approval_claimed"]
        or recovery["provider_review_ready_to_freeze_verdict"]
        != review["provider_ready_to_freeze_verdict"]
        or recovery["provider_review_source_and_tests_seen"]
        != review["source_and_tests_reviewed_by_provider"]
        or recovery["provider_reviewed_packet_was_pre_fix"]
        != review["reviewed_packet_was_pre_fix"]
        or recovery["provider_reviewed_final_source"]
        != review["final_source_reviewed_by_provider"]
        or recovery["provider_reviewed_final_bytes_unchanged"]
        != review["provider_reviewed_final_bytes_unchanged"]
        or recovery["original_failed_audit_log_sha256"] != ORIGINAL_FAILURE_LOG_SHA256
        or recovery["original_raw_run_receipt_sha256"]
        != authorization["raw_run_receipt_sha256"]
        or recovery["original_receipts"] != authorization.get("original_receipts")
        or recovery["fresh_receipts"] != authorization.get("fresh_receipts")
        or recovery["fresh_pod_id"] != authorization["fresh_pod_id"]
        or recovery["superseded_recovery_host"]
        != authorization["superseded_recovery_host"]
        or recovery["bootstrap_import_roots"] != authorization["bootstrap_import_roots"]
        or recovery["bootstrap_postdispatch_assertion"]
        != "same_process_bootstrap_assert_clean_runs_after_recovery_dispatch_returns"
        or recovery["write_confinement_policy"] != LANDLOCK_POLICY
        or recovery["write_confinement_claim"] != WRITE_CONFINEMENT_CLAIM
        or recovery["landlock_limitations"] != LANDLOCK_LIMITATIONS
    ):
        raise RecoveryBundleVerificationError("recovery metadata cross-links differ")
    _validate_bootstrap_phase(
        recovery["bootstrap_execute_entry_phase"],
        phase=BOOTSTRAP_EXECUTE_ENTRY_PHASE,
        mode="execute-confined",
        pid=int(confinement["pid"]),
        execution=execution,
        paths=paths,
        manifest=bootstrap_manifest,
    )
    _validate_bootstrap_phase(
        recovery["bootstrap_prepublication_phase"],
        phase=BOOTSTRAP_PREPUBLICATION_PHASE,
        mode="execute-confined",
        pid=int(confinement["pid"]),
        execution=execution,
        paths=paths,
        manifest=bootstrap_manifest,
    )
    _validate_nested_receipt(
        recovery,
        "preflight_landlock_receipt",
        "preflight_landlock_receipt_sha256",
        preflight_landlock,
    )
    _validate_nested_receipt(
        recovery,
        "preflight_probe_receipt",
        "preflight_probe_receipt_sha256",
        preflight_cuda,
    )
    _validate_nested_receipt(
        recovery,
        "landlock_confinement_receipt",
        "landlock_confinement_receipt_sha256",
        confinement,
    )
    isolation = _validate_nested_receipt(
        recovery, "executable_isolation_receipt", "executable_isolation_receipt_sha256"
    )
    _exact_keys(
        isolation,
        (
            "status",
            "active_root",
            "historical_provenance_root",
            "file_count",
            "file_inventory_sha256",
            "directory_count",
            "directory_inventory_sha256",
            "forbidden_module_count",
            "model_runtime_replaced_by",
            "receipt_sha256",
        ),
        "recovery_audit.executable_isolation_receipt",
    )
    executable_directories = _expected_directory_inventory(RECOVERY_BOUND_PATHS)
    if (
        isolation["status"] != "pass_minimal_audit_only_executable"
        or isolation["active_root"] != execution["active_root"]
        or isolation["historical_provenance_root"]
        != execution["paths"]["provenance_root"]
        or isolation["file_count"] != len(closure)
        or isolation["file_inventory_sha256"] != canonical_sha256(closure)
        or isolation["directory_count"] != len(executable_directories)
        or isolation["directory_inventory_sha256"]
        != canonical_sha256(executable_directories)
        or isolation["forbidden_module_count"] != 0
        or isolation["model_runtime_replaced_by"]
        != "experiments.consciousness_sae_target_blind_calibration.audit_runtime_shim"
    ):
        raise RecoveryBundleVerificationError("recovery executable isolation differs")
    _validate_rehash_pair(
        recovery,
        pre_key="pre_rehash_receipt",
        post_key="post_rehash_receipt",
        unchanged_key="raw_unchanged",
        exact_fields=(
            "status",
            "raw_root",
            "file_count",
            "total_bytes",
            "file_inventory_sha256",
            "directory_count",
            "directory_inventory_sha256",
            "run_receipt_sha256",
            "external_ledger_file_sha256",
            "receipt_sha256",
        ),
        expected={
            "status": "pass_exact_36_file_rehash",
            "raw_root": execution["paths"]["raw_root"],
            "file_count": 36,
            "total_bytes": 323375434,
            "run_receipt_sha256": ORIGINAL_RUN_RECEIPT_SHA256,
            "external_ledger_file_sha256": ORIGINAL_RAW_LEDGER_SHA256,
        },
        label="raw",
    )
    _validate_rehash_pair(
        recovery,
        pre_key="provenance_pre_rehash_receipt",
        post_key="provenance_post_rehash_receipt",
        unchanged_key="historical_provenance_unchanged",
        exact_fields=(
            "status",
            "root",
            "file_count",
            "file_inventory_sha256",
            "directory_count",
            "directory_inventory_sha256",
            "receipt_sha256",
        ),
        expected={
            "status": "pass_exact_nonimportable_historical_provenance",
            "root": execution["paths"]["provenance_root"],
            "file_count": len(authorization["historical_provenance_files"]),
            "file_inventory_sha256": authorization[
                "historical_provenance_inventory_sha256"
            ],
        },
        label="historical provenance",
    )
    if (
        recovery["target_prompt_render_count"] != 0
        or recovery["target_feature_vector_count"] != 0
        or recovery["external_or_prior_outcome_inputs"] != []
        or recovery["scientific_metrics_thresholds_layers_and_rows_changed"]
        is not False
        or recovery["fresh_model_execution_performed"] is not False
        or recovery["zero_forward_guards"]
        != {"torch_module_calls": 0, "transformers_model_load_calls": 0}
        or recovery["forbidden_module_guards"]
        != {"forbidden_module_import_attempts": 0}
    ):
        raise RecoveryBundleVerificationError(
            "recovery zero-forward/science boundary differs"
        )
    available = list(range(79))
    required = list(range(45, 79))
    extras = list(range(45))
    inventory = _mapping(
        recovery["j_checkpoint_inventory"], "recovery_audit.j_checkpoint_inventory"
    )
    if inventory != {
        "available_layers": available,
        "required_layers": required,
        "unused_extra_layers": extras,
        "available_map_count": 79,
        "required_map_count": 34,
        "inventory_sha256": canonical_sha256(available),
    }:
        raise RecoveryBundleVerificationError("recovery J inventory differs")
    if (
        recovery["landlock_launcher_sha256"] != confinement["source_sha256"]
        or preflight_landlock["source_sha256"] != confinement["source_sha256"]
    ):
        raise RecoveryBundleVerificationError("recovery launcher source links differ")


def _validate_compact_pair(
    audit: Mapping[str, Any],
    summary: Mapping[str, Any],
    *,
    authorization: Mapping[str, Any],
) -> Mapping[str, Any]:
    _keys(
        audit,
        (
            "schema_version",
            "status",
            "study_id",
            "protocol_version",
            "run_id",
            "raw_run_receipt_sha256",
            "campaign_started_at_unix",
            "campaign_deadline_at_unix",
            "hourly_price_usd",
            "original_execution_campaign",
            "recovery_execution_campaign",
            "analysis_data_inputs",
            "target_prompt_render_count",
            "target_feature_vector_count",
            "recovery_audit",
        ),
        "calibration_audit",
    )
    _keys(
        summary,
        (
            "schema_version",
            "status",
            "study_id",
            "protocol_version",
            "run_id",
            "raw_run_receipt_sha256",
            "audit_receipt_sha256",
            "later_actual_state_collection_eligibility",
            "analysis_data_inputs",
            "target_prompt_render_count",
            "target_feature_vector_count",
            "recovery_execution_campaign",
            "recovery_audit",
        ),
        "calibration_summary",
    )
    original_campaign = _mapping(
        audit["original_execution_campaign"], "original_execution_campaign"
    )
    recovery_campaign = _mapping(
        audit["recovery_execution_campaign"], "recovery_execution_campaign"
    )
    _exact_keys(
        original_campaign,
        (
            "campaign_started_at_unix",
            "campaign_deadline_at_unix",
            "hourly_price_usd",
        ),
        "original_execution_campaign",
    )
    _exact_keys(
        recovery_campaign,
        ("started_at_unix", "deadline_at_unix", "hourly_price_usd", "max_spend_usd"),
        "recovery_execution_campaign",
    )
    if (
        audit["schema_version"] != SCHEMA_VERSION
        or audit["status"] != "pass"
        or summary["schema_version"] != SCHEMA_VERSION
        or summary["status"] != summary["later_actual_state_collection_eligibility"]
        or audit["study_id"] != authorization["study_id"]
        or summary["study_id"] != audit["study_id"]
        or audit["protocol_version"] != authorization["protocol_version"]
        or summary["protocol_version"] != audit["protocol_version"]
        or audit["run_id"] != authorization["run_id"]
        or summary["run_id"] != audit["run_id"]
        or audit["raw_run_receipt_sha256"] != authorization["raw_run_receipt_sha256"]
        or summary["raw_run_receipt_sha256"] != audit["raw_run_receipt_sha256"]
        or summary["audit_receipt_sha256"] != audit["receipt_sha256"]
        or original_campaign
        != {
            "campaign_started_at_unix": ORIGINAL_CAMPAIGN_STARTED_AT_UNIX,
            "campaign_deadline_at_unix": ORIGINAL_CAMPAIGN_DEADLINE_AT_UNIX,
            "hourly_price_usd": ORIGINAL_CAMPAIGN_HOURLY_PRICE_USD,
        }
        or audit["campaign_started_at_unix"] != ORIGINAL_CAMPAIGN_STARTED_AT_UNIX
        or audit["campaign_deadline_at_unix"] != ORIGINAL_CAMPAIGN_DEADLINE_AT_UNIX
        or audit["hourly_price_usd"] != ORIGINAL_CAMPAIGN_HOURLY_PRICE_USD
        or recovery_campaign
        != {
            "started_at_unix": authorization["recovery_started_at_unix"],
            "deadline_at_unix": authorization["recovery_deadline_at_unix"],
            "hourly_price_usd": authorization["hourly_price_usd"],
            "max_spend_usd": authorization["max_spend_usd"],
        }
        or summary["recovery_execution_campaign"] != recovery_campaign
        or audit["analysis_data_inputs"] != []
        or summary["analysis_data_inputs"] != []
        or audit["target_prompt_render_count"] != 0
        or audit["target_feature_vector_count"] != 0
        or summary["target_prompt_render_count"] != 0
        or summary["target_feature_vector_count"] != 0
        or audit["recovery_audit"] != summary["recovery_audit"]
    ):
        raise RecoveryBundleVerificationError("audit/summary semantic links differ")
    return _mapping(audit["recovery_audit"], "recovery_audit")


def _validate_publication(
    publication: Mapping[str, Any],
    *,
    audit: Mapping[str, Any],
    summary: Mapping[str, Any],
    audit_path: Path,
    summary_path: Path,
    claimed: float,
    deadline: float,
) -> None:
    _exact_keys(
        publication,
        (
            "schema_version",
            "status",
            "study_id",
            "protocol_version",
            "audit_receipt_sha256",
            "summary_receipt_sha256",
            "audit_file_sha256",
            "summary_file_sha256",
            "publication_completed_at_unix",
            "recovery_deadline_at_unix",
            "receipt_sha256",
        ),
        "publication_complete",
    )
    published = _number(
        publication["publication_completed_at_unix"],
        "publication_complete.publication_completed_at_unix",
    )
    if (
        publication["schema_version"] != SCHEMA_VERSION
        or publication["status"] != "complete"
        or publication["study_id"] != audit["study_id"]
        or publication["protocol_version"] != audit["protocol_version"]
        or publication["audit_receipt_sha256"] != audit["receipt_sha256"]
        or publication["summary_receipt_sha256"] != summary["receipt_sha256"]
        or publication["audit_file_sha256"] != sha256_file(audit_path)
        or publication["summary_file_sha256"] != sha256_file(summary_path)
        or float(publication["recovery_deadline_at_unix"]) != deadline
        or not claimed <= published < deadline
    ):
        raise RecoveryBundleVerificationError("publication receipt links differ")


def _manifest_records(root: Path) -> list[dict[str, Any]]:
    records = [
        {
            "path": relative.as_posix(),
            "bytes": (root / relative).stat().st_size,
            "sha256": sha256_file(root / relative),
        }
        for relative in REQUIRED_RECEIPT_PATHS
    ]
    return sorted(records, key=lambda row: row["path"])


def verify_bundle(bundle_root: Path) -> dict[str, Any]:
    """Verify the success bundle without network access or bundle mutation."""

    lexical = bundle_root.expanduser().absolute()
    try:
        details = lexical.lstat()
    except OSError as exc:
        raise RecoveryBundleVerificationError("bundle root is missing") from exc
    if not stat.S_ISDIR(details.st_mode) or stat.S_ISLNK(details.st_mode):
        raise RecoveryBundleVerificationError("bundle root is not a plain directory")
    root = lexical.resolve(strict=True)
    _validate_output_tree(root)
    _validate_compact_directory(root)

    authorization, _ = _read_receipt(root, AUTHORIZATION_RELATIVE, "authorization")
    bootstrap_manifest, bootstrap_manifest_path = _read_receipt(
        root, BOOTSTRAP_MANIFEST_RELATIVE, "bootstrap_manifest"
    )
    preflight_landlock, preflight_landlock_path = _read_receipt(
        root, PREFLIGHT_ENFORCEMENT_RELATIVE, "preflight_landlock"
    )
    preflight_cuda, preflight_cuda_path = _read_receipt(
        root, PREFLIGHT_CUDA_RELATIVE, "preflight_cuda"
    )
    local_test_receipt, local_test_receipt_path = _read_receipt(
        root, LOCAL_TEST_RELATIVE, "local_test_receipt"
    )
    target_host_test_receipt, target_host_test_receipt_path = _read_receipt(
        root, TARGET_HOST_TEST_RELATIVE, "target_host_test_receipt"
    )
    qualification_ownership, qualification_ownership_path = _read_receipt(
        root,
        TARGET_QUALIFICATION_OWNERSHIP_RELATIVE,
        "target_qualification_ownership",
    )
    qualification_landlock, qualification_landlock_path = _read_receipt(
        root,
        TARGET_QUALIFICATION_LANDLOCK_RELATIVE,
        "target_qualification_landlock",
    )
    qualification_cuda, qualification_cuda_path = _read_receipt(
        root,
        TARGET_QUALIFICATION_CUDA_RELATIVE,
        "target_qualification_cuda",
    )
    confinement, _ = _read_receipt(root, CONFINEMENT_RELATIVE, "confinement")
    marker, _ = _read_receipt(root, ATTEMPT_MARKER_RELATIVE, "attempt_marker")
    audit, audit_path = _read_receipt(root, AUDIT_RELATIVE, "calibration_audit")
    summary, summary_path = _read_receipt(root, SUMMARY_RELATIVE, "calibration_summary")
    publication, _ = _read_receipt(root, PUBLICATION_RELATIVE, "publication_complete")

    execution, paths, command_sha256, started, deadline = _validate_authorization(
        authorization,
        bootstrap_manifest=bootstrap_manifest,
        bootstrap_manifest_path=bootstrap_manifest_path,
        preflight_landlock=preflight_landlock,
        preflight_cuda=preflight_cuda,
        preflight_landlock_path=preflight_landlock_path,
        preflight_cuda_path=preflight_cuda_path,
        local_test_receipt=local_test_receipt,
        target_host_test_receipt=target_host_test_receipt,
        local_test_receipt_path=local_test_receipt_path,
        target_host_test_receipt_path=target_host_test_receipt_path,
        qualification_ownership=qualification_ownership,
        qualification_landlock=qualification_landlock,
        qualification_cuda=qualification_cuda,
        qualification_ownership_path=qualification_ownership_path,
        qualification_landlock_path=qualification_landlock_path,
        qualification_cuda_path=qualification_cuda_path,
    )
    bootstrap_roots, bootstrap_files = _bootstrap_protected_paths(
        bootstrap_manifest, paths
    )
    preflight_pid, preflight_devices = _validate_landlock_receipt(
        preflight_landlock,
        purpose="preauthorization_probe",
        receipt_path=paths["preflight_landlock"],
        output_root=paths["preflight_output_root"],
        protected_roots=[paths["preflight_canary_protected_root"], *bootstrap_roots],
        protected_files=[
            f"{paths['preflight_canary_protected_root']}/seed.txt",
            *bootstrap_files,
        ],
        canary_output_root=paths["preflight_canary_output_root"],
        authorization_sha256=None,
        preflight_sha256=None,
        label="preflight_landlock",
    )
    _validate_cuda_preflight(
        preflight_cuda,
        landlock=preflight_landlock,
        preflight_output_root=paths["preflight_output_root"],
        execution=execution,
        paths=paths,
        bootstrap_manifest=bootstrap_manifest,
        recovery_closure=authorization["recovery_bound_files"],
    )
    if preflight_cuda["pid"] != preflight_pid:
        raise RecoveryBundleVerificationError("preflight PID link differs")
    confinement_pid, confinement_devices = _validate_landlock_receipt(
        confinement,
        purpose="audit_recovery",
        receipt_path=paths["landlock_receipt"],
        output_root=paths["output_root"],
        protected_roots=[
            paths["raw_root"],
            paths["provenance_root"],
            paths["canary_protected_root"],
            *bootstrap_roots,
        ],
        protected_files=[
            f"{paths['raw_root']}/RUN_COMPLETE.json",
            (
                f"{paths['provenance_root']}/{CANONICAL_PLAN_RELATIVE_PATH}/"
                "plan_manifest.json"
            ),
            paths["recovery_authorization"],
            *bootstrap_files,
        ],
        canary_output_root=paths["canary_output_root"],
        authorization_sha256=authorization["receipt_sha256"],
        preflight_sha256=preflight_cuda["receipt_sha256"],
        label="confinement",
    )
    if (
        preflight_devices != confinement_devices
        or [row["path"] for row in confinement_devices] != execution["device_files"]
        or authorization["preflight"]["device_rules"] != confinement_devices
        or confinement["child_argv"] != execution["confined_child_argv"]
        or confinement["child_argv_sha256"] != execution["confined_child_argv_sha256"]
    ):
        raise RecoveryBundleVerificationError(
            "Landlock device/command inventories differ"
        )
    expected_preflight_argv = _expected_preflight_argv(
        execution["python_executable"],
        execution["active_root"],
        paths,
        execution["roots_manifest_sha256"],
        execution["device_files"],
    )
    if preflight_landlock[
        "child_argv"
    ] != expected_preflight_argv or preflight_landlock[
        "child_argv_sha256"
    ] != canonical_sha256(expected_preflight_argv):
        raise RecoveryBundleVerificationError(
            "preflight Landlock child command differs"
        )
    if command_sha256 != execution["command_sha256"]:
        raise RecoveryBundleVerificationError("execution command cross-link differs")
    provider = _mapping(preflight_cuda["provider"], "preflight_cuda.provider")
    _exact_keys(
        provider, ("pod_id", "volume_id", "data_center_id"), "preflight_cuda.provider"
    )
    if provider != {
        "pod_id": authorization["fresh_pod_id"],
        "volume_id": NETWORK_VOLUME_ID,
        "data_center_id": DATA_CENTER_ID,
    }:
        raise RecoveryBundleVerificationError("preflight provider identity differs")
    claimed = _validate_marker(
        marker,
        authorization=authorization,
        execution=execution,
        confinement=confinement,
        started=started,
        deadline=deadline,
    )
    if marker["landlock_pid"] != confinement_pid:
        raise RecoveryBundleVerificationError(
            "attempt/confinement PID cross-link differs"
        )
    recovery = _validate_compact_pair(audit, summary, authorization=authorization)
    _validate_recovery_metadata(
        recovery,
        authorization=authorization,
        execution=execution,
        preflight_landlock=preflight_landlock,
        preflight_cuda=preflight_cuda,
        confinement=confinement,
        marker=marker,
        bootstrap_manifest=bootstrap_manifest,
        paths=paths,
    )
    _validate_publication(
        publication,
        audit=audit,
        summary=summary,
        audit_path=audit_path,
        summary_path=summary_path,
        claimed=claimed,
        deadline=deadline,
    )

    records = _manifest_records(root)
    core = {
        "schema_version": 1,
        "status": "pass_recovery_bundle_verified_offline",
        "attempt_id": execution["attempt_id"],
        "run_id": audit["run_id"],
        "recovery_authorization_receipt_sha256": authorization["receipt_sha256"],
        "preflight_landlock_receipt_sha256": preflight_landlock["receipt_sha256"],
        "preflight_probe_receipt_sha256": preflight_cuda["receipt_sha256"],
        "target_qualification_ownership_receipt_sha256": qualification_ownership[
            "receipt_sha256"
        ],
        "target_qualification_landlock_receipt_sha256": qualification_landlock[
            "receipt_sha256"
        ],
        "target_qualification_cuda_receipt_sha256": qualification_cuda[
            "receipt_sha256"
        ],
        "landlock_confinement_receipt_sha256": confinement["receipt_sha256"],
        "attempt_marker_receipt_sha256": marker["receipt_sha256"],
        "audit_receipt_sha256": audit["receipt_sha256"],
        "summary_receipt_sha256": summary["receipt_sha256"],
        "publication_receipt_sha256": publication["receipt_sha256"],
        "verified_files": records,
        "verified_file_count": len(records),
        "verified_files_sha256": canonical_sha256(records),
        "network_accessed": False,
        "bundle_modified": False,
    }
    return {**core, "receipt_sha256": canonical_sha256(core)}


def write_verification_receipt(
    output: Path, receipt: Mapping[str, Any], *, bundle_root: Path
) -> Path:
    """Exclusively write the receipt outside the retrieved bundle."""

    root = bundle_root.expanduser().absolute().resolve(strict=True)
    destination = output.expanduser().absolute()
    try:
        parent = destination.parent.resolve(strict=True)
    except OSError as exc:
        raise RecoveryBundleVerificationError(
            "verification output parent is missing"
        ) from exc
    resolved = parent / destination.name
    if resolved == root or root in resolved.parents:
        raise RecoveryBundleVerificationError(
            "verification output must be outside the bundle"
        )
    if not parent.is_dir() or parent.is_symlink() or os.path.lexists(resolved):
        raise RecoveryBundleVerificationError("verification output is not fresh/safe")
    _self_hash(receipt, "verification_receipt")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(resolved, flags, 0o600)
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(canonical_json_bytes(dict(receipt)) + b"\n")
        handle.flush()
        os.fsync(handle.fileno())
    directory_fd = os.open(parent, os.O_RDONLY)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)
    return resolved


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    receipt = verify_bundle(args.bundle_root)
    published = write_verification_receipt(
        args.output, receipt, bundle_root=args.bundle_root
    )
    print(published)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

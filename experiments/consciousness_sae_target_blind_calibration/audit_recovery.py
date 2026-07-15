#!/usr/bin/env python3
"""Authorize and execute the disclosed calibration-v2 r3 audit recovery.

This module never runs the model. It preserves the immutable r3 auditor, makes
one J-checkpoint inventory compatibility correction, and confines fresh-host
authority plus historical source validation to audit-only adapters.
"""

from __future__ import annotations

import argparse
import contextlib
import errno
import hashlib
import json
import math
import os
import platform
import re
import shlex
import stat
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Iterator, Mapping, Sequence

from experiments.consciousness_sae_realization_validation import runpod_preflight
from experiments.consciousness_sae_target_blind_calibration import (
    audit_runtime_shim,
    authorize,
    confined_bootstrap,
    protocol,
)


_RUNTIME_MODULE_NAME = "experiments.consciousness_sae_realization_validation.runtime"
_prior_runtime_module = sys.modules.get(_RUNTIME_MODULE_NAME)
sys.modules[_RUNTIME_MODULE_NAME] = audit_runtime_shim
from experiments.consciousness_sae_target_blind_calibration import (  # noqa: E402
    audit,
    orientation,
    validate_plan,
)

orientation.runtime = audit_runtime_shim
if _prior_runtime_module is not None:
    sys.modules[_RUNTIME_MODULE_NAME] = _prior_runtime_module


REPO_ROOT = Path(__file__).resolve().parents[2]
RECOVERY_PROTOCOL_VERSION = (
    "consciousness_sae_target_blind_calibration_v2.audit_recovery_r3"
)
RUN_ID = "calv2-r3-1a16572-20260715T002344Z"
RAW_RELATIVE = (
    "consciousness_sae_target_blind_calibration/"
    "consciousness_sae_target_blind_calibration_v2/raw/" + RUN_ID
)
ORIGINAL_RUN_RECEIPT_SHA256 = (
    "bab48b452c7e7c5b9db5d09ecc34c7e530813e2f5093aff1b8a8152017e4695d"
)
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
ORIGINAL_RUN_FILE_SHA256 = (
    "d60e25d13d1b9e30a52114aa954a6c1306ef8e15a8dddd53af1de58c4dcb9fee"
)
ORIGINAL_RAW_LEDGER_SHA256 = (
    "7bffb6306b67814d2f4618b6aaf4f243ab2992d7b6b92ebb955a370654e0a20c"
)
ORIGINAL_RAW_INVENTORY_SHA256 = (
    "2f65c41074a49ff04f0de96d547ad5fdef796d13fe98bfea987fbe86822b0cbd"
)
ORIGINAL_FAILURE_LOG_SHA256 = (
    "a5936d0fda01b96f193a1ab40c9d7c52dc751ecdf3686896e26d2d3951cdd86f"
)
HISTORICAL_PROVENANCE_FILE_COUNT = 41
HISTORICAL_PROVENANCE_INVENTORY_SHA256 = (
    "ff02d92e681e662261b57dab00882a654eaf7b0d505dd2f210ab06f57ba8bd74"
)
RECOVERY_SECONDS = 60 * 60
MINIMUM_ISSUE_REMAINING_SECONDS = 30 * 60
RECOVERY_RATE_USD_PER_HOUR = 6.0
RECOVERY_MAX_SPEND_USD = 6.0
ORIGINAL_CAMPAIGN_STARTED_AT_UNIX = 1_784_074_604.0
ORIGINAL_CAMPAIGN_DEADLINE_AT_UNIX = 1_784_080_004.0
ORIGINAL_CAMPAIGN_HOURLY_PRICE_USD = 6.0
# Prospective successor-review settings. Freezing these values permits a
# cost-only dry run; it does not authorize or issue the paid provider call.
PRO_REVIEW_BUDGET_AUTHORIZATION_USD = 75.0
PRO_REVIEW_INSTRUCTIONS_SHA256 = (
    "3e51d5a292ca46fb6cbf685f74e37f2dbfe7e302addcc4bac8715a19aeefe1d7"
)
PRO_REVIEW_MAX_INPUT_CHARACTERS = 2_100_000
PRO_REVIEW_MAX_INPUT_TOKENS = 600_000
PRO_REVIEW_V8_MAX_INPUT_CHARACTERS = 2_200_000
PRO_REVIEW_V8_MAX_INPUT_TOKENS = 630_000
PRO_REVIEW_MAX_OUTPUT_TOKENS = 20_000
PRO_REVIEW_INPUT_RESERVE_MULTIPLIER = 5.0
PRO_REVIEW_OUTPUT_RESERVE_MULTIPLIER = 2.2
PRO_REVIEW_CHARS_PER_TOKEN_ASSUMPTION = 3.5
# GPT-5.6 Sol prices the full request at 2x input and 1.5x output when the
# prompt exceeds 272K input tokens. This packet is conservatively above that
# boundary, so v6 always reserves the long-context rates rather than switching
# rates after an exact-token preflight.
PRO_REVIEW_V6_INPUT_RATE_USD_PER_MILLION = 10.0
PRO_REVIEW_V6_CACHE_WRITE_RATE_USD_PER_MILLION = 12.5
PRO_REVIEW_V6_OUTPUT_RATE_USD_PER_MILLION = 45.0
PRO_REVIEW_TERMINAL_VERDICTS = (
    "NOT READY TO FREEZE",
    "READY AFTER SPECIFIED FIXES",
    "READY TO FREEZE",
)
TEST_RECEIPT_TYPE = "audit_recovery_test_receipt_v1"
TEST_RECEIPT_STATUS = "pass_exact_code_freeze_tests"
TEST_RECEIPT_KINDS = ("local", "target_host")
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
LOCAL_TEST_RECEIPT_NAME = "LOCAL_TEST_RECEIPT.json"
TARGET_HOST_TEST_RECEIPT_NAME = "TARGET_HOST_TEST_RECEIPT.json"
TARGET_QUALIFICATION_LANDLOCK_NAME = "TARGET_QUALIFICATION_LANDLOCK_ENFORCEMENT.json"
TARGET_QUALIFICATION_CUDA_NAME = "TARGET_QUALIFICATION_LANDLOCK_CUDA_PREFLIGHT.json"
TARGET_QUALIFICATION_OWNERSHIP_NAME = "TARGET_QUALIFICATION_OWNERSHIP.json"
PREFLIGHT_CLOSURE_SCOPES = ("final_recovery", "source_test_qualification")
HEX64 = re.compile(r"[0-9a-f]{64}")
HEX40 = re.compile(r"[0-9a-f]{40}")
ATTEMPT_ID_RE = re.compile(r"calv2-r3-audit-recovery-[0-9a-f]{7}-[0-9]{8}T[0-9]{6}Z")
RECOVERY_ATTEMPT_PARENT = "/workspace/csae"
AF_UNIX_PATH_MAX_BYTES = 107
AF_UNIX_PATH_REQUIRED_MARGIN_BYTES = 16
AF_UNIX_PATH_BUDGET_BYTES = 91
OUTPUT_CANARY_SOCKET_NAME = ".s"
BOOTSTRAP_MANIFEST_RELATIVE = "bootstrap/APPROVED_IMPORT_ROOTS.json"
MODEL_SNAPSHOT_PATH = runpod_preflight.LEGACY_PUBLIC_ARTIFACT_ROOT + "/model_snapshot"
J_LENS_PATH = (
    runpod_preflight.LEGACY_PUBLIC_ARTIFACT_ROOT
    + "/jlens/Llama-3.3-70B-Instruct_jacobian_lens.pt"
)

LANDLOCK_REQUIRED_ABI = 4
LANDLOCK_WRITE_ACCESS_RIGHTS = (
    ("write_file", 1 << 1),
    ("remove_dir", 1 << 4),
    ("remove_file", 1 << 5),
    ("make_char", 1 << 6),
    ("make_dir", 1 << 7),
    ("make_reg", 1 << 8),
    ("make_sock", 1 << 9),
    ("make_fifo", 1 << 10),
    ("make_block", 1 << 11),
    ("make_sym", 1 << 12),
    ("refer", 1 << 13),
    ("truncate", 1 << 14),
)
LANDLOCK_WRITE_ACCESS_MASK = sum(value for _name, value in LANDLOCK_WRITE_ACCESS_RIGHTS)
LANDLOCK_OUTPUT_ACCESS_RIGHTS = (
    ("write_file", 1 << 1),
    ("remove_dir", 1 << 4),
    ("remove_file", 1 << 5),
    ("make_dir", 1 << 7),
    ("make_reg", 1 << 8),
)
LANDLOCK_OUTPUT_ACCESS_MASK = sum(
    value for _name, value in LANDLOCK_OUTPUT_ACCESS_RIGHTS
)
LANDLOCK_PROC_SELF_TASK_ACCESS_RIGHTS = (
    ("write_file", 1 << 1),
    ("truncate", 1 << 14),
)
LANDLOCK_PROC_SELF_TASK_ACCESS_MASK = sum(
    value for _name, value in LANDLOCK_PROC_SELF_TASK_ACCESS_RIGHTS
)
NVIDIA_DEVICE_PATH_RE = re.compile(
    r"(?:/dev/nvidia[0-9]+|/dev/nvidiactl|/dev/nvidia-uvm|"
    r"/dev/nvidia-uvm-tools|/dev/nvidia-caps/nvidia-cap[0-9]+)"
)
LANDLOCK_POLICY = {
    "mechanism": "linux_landlock",
    "required_abi": LANDLOCK_REQUIRED_ABI,
    "handled_access_fs": LANDLOCK_WRITE_ACCESS_MASK,
    "handled_access_fs_names": [name for name, _value in LANDLOCK_WRITE_ACCESS_RIGHTS],
    "output_allowed_access_fs": LANDLOCK_OUTPUT_ACCESS_MASK,
    "output_allowed_access_fs_names": [
        name for name, _value in LANDLOCK_OUTPUT_ACCESS_RIGHTS
    ],
    "rule_type": "path_beneath",
    "directory_rule_count": 3,
    "device_rule_access_fs": 1 << 1,
    "device_rule_access_fs_name": "write_file",
    "write_allowed_directories": [
        "execution.paths.output_root",
        "execution.paths.canary_output_root",
    ],
    "proc_self_task_allowed_access_fs": LANDLOCK_PROC_SELF_TASK_ACCESS_MASK,
    "proc_self_task_allowed_access_fs_names": [
        name for name, _value in LANDLOCK_PROC_SELF_TASK_ACCESS_RIGHTS
    ],
    "proc_self_task_rule_path": "/proc/self/task",
    "proc_self_task_exception_scope": (
        "WRITE_FILE|TRUNCATE on all descendants; required for CUDA thread naming"
    ),
    "device_write_exceptions": "execution.device_files",
    "raw_and_provenance_write_access": "default_denied",
    "metadata_and_device_ioctl_outside_claim": True,
}

PINNED_PROBE_PACKAGE_VERSIONS = {
    "numpy": "2.2.6",
    "safetensors": "0.8.0",
    "tokenizers": "0.22.2",
    "torch": "2.8.0.dev20250319+cu128",
    "transformers": "4.57.6",
}
CONFINED_FIXED_ENVIRONMENT = {
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
CONFINED_WRITABLE_PATH_ENVIRONMENT = (
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
FORBIDDEN_CONFINED_ENVIRONMENT = (
    "LD_AUDIT",
    "LD_PRELOAD",
    "PYTHONHOME",
    "PYTHONINSPECT",
    "PYTHONPATH",
    "PYTHONPLATLIBDIR",
    "PYTHONSTARTUP",
    "PYTHONUSERBASE",
)
PROTECTED_CANARY_OPERATIONS = (
    "protected_create",
    "protected_mkdir",
    "protected_symlink",
    "protected_link",
    "protected_unlink",
    "protected_rename",
    "protected_truncate",
    "protected_open_write",
)
OUTPUT_CANARY_ALLOWED_OPERATIONS = (
    "output_create_write_fsync",
    "output_same_directory_rename",
    "output_unlink",
    "output_mkdir",
    "output_rmdir",
)
OUTPUT_CANARY_DENIED_OPERATIONS = (
    "output_truncate",
    "output_symlink",
    "output_fifo",
    "output_unix_socket",
    "output_cross_directory_link",
)
PROTECTED_CANARY_WRITABLE_BASELINE = (
    "baseline_seed_open_write_no_write",
    "baseline_create_unlink",
    "baseline_mkdir_rmdir",
)

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
    HISTORICAL_V2_PRO_REVIEW_ADJUDICATION_JSON: (
        "6e404501248a9e9a13b46cc75bc58ab40276c617001a87c60dd14a6c1627f81d"
    ),
    HISTORICAL_V2_PRO_REVIEW_ADJUDICATION_MARKDOWN: (
        "abacd1ca2bd3612ebc6123b650a15734bbf68953d23a1934101a0c1ff86c6f72"
    ),
}
HISTORICAL_V3_NEGATIVE_REVIEW_DIRECTORY = (
    "docs/consciousness_sae_target_blind_calibration/reviews/"
    "audit_recovery_landlock_gpt_pro_v3_completed_negative"
)
HISTORICAL_V3_NEGATIVE_REVIEW_ADJUDICATION_JSON = (
    f"{HISTORICAL_V3_NEGATIVE_REVIEW_DIRECTORY}/ADJUDICATION.json"
)
HISTORICAL_V3_NEGATIVE_REVIEW_ADJUDICATION_MARKDOWN = (
    f"{HISTORICAL_V3_NEGATIVE_REVIEW_DIRECTORY}/ADJUDICATION.md"
)
HISTORICAL_V3_NEGATIVE_REVIEW_PHYSICAL_SHA256 = {
    HISTORICAL_V3_NEGATIVE_REVIEW_ADJUDICATION_JSON: (
        "59e71e96e0684efa69ea050397760cce6979d1ba596be967a6d730edd627c06a"
    ),
    HISTORICAL_V3_NEGATIVE_REVIEW_ADJUDICATION_MARKDOWN: (
        "18b1ea90dbac2db629a482a9da8d72a0003ba0dbcd779ec7db15109aab842d1c"
    ),
    f"{HISTORICAL_V3_NEGATIVE_REVIEW_DIRECTORY}/request_payload.json": (
        "2a2544489cb50fdc76509fa9c47c9b466fe388d9adf4b0f62d2925a0224a703b"
    ),
    f"{HISTORICAL_V3_NEGATIVE_REVIEW_DIRECTORY}/response.json": (
        "ec43e39e6f7ed37dc30256199c21a34456dbb010398c9e10c4455baeef64ae67"
    ),
    f"{HISTORICAL_V3_NEGATIVE_REVIEW_DIRECTORY}/review.md": (
        "e1295704dfc79dac1665d97dc91ec1cae364b9f5c4145ebb294383507c445cb2"
    ),
    f"{HISTORICAL_V3_NEGATIVE_REVIEW_DIRECTORY}/review_manifest.json": (
        "95b24c9d95ca1ccd21e27240c786484d7cbfc3ba0251fc3286abee10b5999f2b"
    ),
    f"{HISTORICAL_V3_NEGATIVE_REVIEW_DIRECTORY}/review_request.md": (
        "ea9d20786e73f9ffdaff202bb298d4d49cc7f98aa34912e3e05cc0655488235d"
    ),
}
HISTORICAL_V3_NEGATIVE_ADJUDICATION_RECEIPT_SHA256 = (
    "24dce20453445b169fb11c3f3e76c0444cf38d95a8fa85838126500f7830ac9b"
)
HISTORICAL_V4_NEGATIVE_REVIEW_DIRECTORY = (
    "docs/consciousness_sae_target_blind_calibration/reviews/"
    "audit_recovery_landlock_gpt_pro_v4_completed_negative"
)
HISTORICAL_V4_NEGATIVE_REVIEW_ADJUDICATION_JSON = (
    f"{HISTORICAL_V4_NEGATIVE_REVIEW_DIRECTORY}/ADJUDICATION.json"
)
HISTORICAL_V4_NEGATIVE_REVIEW_ADJUDICATION_MARKDOWN = (
    f"{HISTORICAL_V4_NEGATIVE_REVIEW_DIRECTORY}/ADJUDICATION.md"
)
HISTORICAL_V4_NEGATIVE_REVIEW_PHYSICAL_SHA256 = {
    HISTORICAL_V4_NEGATIVE_REVIEW_ADJUDICATION_JSON: (
        "83412e1300c2eb75e0a484635de5ec68b3c30bcd54fa66a21a97c4ed7a5353e6"
    ),
    HISTORICAL_V4_NEGATIVE_REVIEW_ADJUDICATION_MARKDOWN: (
        "3ee053e6dfb911b57458550d5c68908f2ec4444a0bfa65cbacc274a7d8f9b027"
    ),
    f"{HISTORICAL_V4_NEGATIVE_REVIEW_DIRECTORY}/request_payload.json": (
        "ce6936466ce66fc60522d4e6cce04e83ee09083afa993103d9c69cfecc7b2d40"
    ),
    f"{HISTORICAL_V4_NEGATIVE_REVIEW_DIRECTORY}/response.json": (
        "48648079d58c32a7b7a264698b74ecb962b0eae01de120aab95c4535e21e0f1a"
    ),
    f"{HISTORICAL_V4_NEGATIVE_REVIEW_DIRECTORY}/review.md": (
        "97bf3d8f8c34a2014f0635e9491a8a69f917fe87518bea9dac0a9c55e75e45c2"
    ),
    f"{HISTORICAL_V4_NEGATIVE_REVIEW_DIRECTORY}/review_manifest.json": (
        "2bf3caa69667575e478a82036bf7287826d1f15b6350f3754d45bd688225c6ff"
    ),
    f"{HISTORICAL_V4_NEGATIVE_REVIEW_DIRECTORY}/review_request.md": (
        "c0fb06c093c36d2a8d4f2a02b4e01902e10a8e42776bdc937b379b643ae53844"
    ),
}
HISTORICAL_V4_NEGATIVE_ADJUDICATION_RECEIPT_SHA256 = (
    "1ccca3495ffe1ba4409751d7398364f0da04d25cb44034fd68244a434b14aab3"
)
HISTORICAL_V4_NEGATIVE_FINDING_IDS = (
    "B01",
    "B02",
    "B03",
    "B04",
    "B06",
    "B07",
    "B08",
    "B09",
    "B10",
    "B11",
    "B12",
    "I01",
    "I02",
    "I03",
    "I04",
    "I05",
    "I06",
    "I07",
    "I08",
)
V3_REVIEW_INPUT_DIRECTORY = (
    "docs/consciousness_sae_target_blind_calibration/reviews/"
    "audit_recovery_landlock_gpt_pro_v3_inputs"
)
V3_LOCAL_TEST_RECEIPT_SNAPSHOT = (
    f"{V3_REVIEW_INPUT_DIRECTORY}/{LOCAL_TEST_RECEIPT_NAME}"
)
V3_TARGET_HOST_TEST_RECEIPT_SNAPSHOT = (
    f"{V3_REVIEW_INPUT_DIRECTORY}/{TARGET_HOST_TEST_RECEIPT_NAME}"
)
V3_TARGET_QUALIFICATION_OWNERSHIP_SNAPSHOT = (
    f"{V3_REVIEW_INPUT_DIRECTORY}/{TARGET_QUALIFICATION_OWNERSHIP_NAME}"
)
V3_TARGET_QUALIFICATION_LANDLOCK_SNAPSHOT = (
    f"{V3_REVIEW_INPUT_DIRECTORY}/{TARGET_QUALIFICATION_LANDLOCK_NAME}"
)
V3_TARGET_QUALIFICATION_CUDA_SNAPSHOT = (
    f"{V3_REVIEW_INPUT_DIRECTORY}/{TARGET_QUALIFICATION_CUDA_NAME}"
)
V4_REVIEW_INPUT_DIRECTORY = (
    "docs/consciousness_sae_target_blind_calibration/reviews/"
    "audit_recovery_landlock_gpt_pro_v4_inputs"
)
V4_LOCAL_TEST_RECEIPT_SNAPSHOT = (
    f"{V4_REVIEW_INPUT_DIRECTORY}/{LOCAL_TEST_RECEIPT_NAME}"
)
V4_TARGET_HOST_TEST_RECEIPT_SNAPSHOT = (
    f"{V4_REVIEW_INPUT_DIRECTORY}/{TARGET_HOST_TEST_RECEIPT_NAME}"
)
V4_TARGET_QUALIFICATION_OWNERSHIP_SNAPSHOT = (
    f"{V4_REVIEW_INPUT_DIRECTORY}/{TARGET_QUALIFICATION_OWNERSHIP_NAME}"
)
V4_TARGET_QUALIFICATION_LANDLOCK_SNAPSHOT = (
    f"{V4_REVIEW_INPUT_DIRECTORY}/{TARGET_QUALIFICATION_LANDLOCK_NAME}"
)
V4_TARGET_QUALIFICATION_CUDA_SNAPSHOT = (
    f"{V4_REVIEW_INPUT_DIRECTORY}/{TARGET_QUALIFICATION_CUDA_NAME}"
)
V4_TIMED_QUALIFICATION_RECEIPT_SNAPSHOT = (
    f"{V4_REVIEW_INPUT_DIRECTORY}/TIMED_QUALIFICATION_RECEIPT.json"
)
V4_TIMED_QUALIFICATION_OWNERSHIP_SNAPSHOT = (
    f"{V4_REVIEW_INPUT_DIRECTORY}/TIMED_QUALIFICATION_OWNERSHIP.json"
)
V4_TIMED_QUALIFICATION_GUEST_SNAPSHOT = (
    f"{V4_REVIEW_INPUT_DIRECTORY}/TIMED_QUALIFICATION_GUEST.json"
)
V4_TIMED_QUALIFICATION_CACHE_SNAPSHOT = (
    f"{V4_REVIEW_INPUT_DIRECTORY}/TIMED_QUALIFICATION_CACHE.json"
)
V4_TIMED_QUALIFICATION_LANDLOCK_SNAPSHOT = (
    f"{V4_REVIEW_INPUT_DIRECTORY}/TIMED_QUALIFICATION_LANDLOCK.json"
)
V4_TIMED_QUALIFICATION_CUDA_SNAPSHOT = (
    f"{V4_REVIEW_INPUT_DIRECTORY}/TIMED_QUALIFICATION_CUDA.json"
)
V4_TIMED_QUALIFICATION_TERMINATION_AUDIT_SNAPSHOT = (
    f"{V4_REVIEW_INPUT_DIRECTORY}/TIMED_QUALIFICATION_TERMINATION_AUDIT.json"
)
V4_TIMED_QUALIFICATION_PHYSICAL_SHA256 = {
    V4_TIMED_QUALIFICATION_RECEIPT_SNAPSHOT: (
        "2d681bd9d02bb786234d49336f1fbe49d661658dac16bdbca7c1cc715d7ffa62"
    ),
    V4_TIMED_QUALIFICATION_OWNERSHIP_SNAPSHOT: (
        "68b6ddf7112a19c0a257edfba16bb24bbed39a140d7a5452bd507b7cf681accf"
    ),
    V4_TIMED_QUALIFICATION_GUEST_SNAPSHOT: (
        "9286f7bd2088e8b7f67e31d08fe7373f43d166d61700ef77f2086069f876fe37"
    ),
    V4_TIMED_QUALIFICATION_CACHE_SNAPSHOT: (
        "cf31fc9a0831cfdfcad2971b45df7dab9adf554ad6edd307e23c183c30bba137"
    ),
    V4_TIMED_QUALIFICATION_LANDLOCK_SNAPSHOT: (
        "8512213aaa7aee53b9cd60c9e57fcd0da4a742a55fd0006f09ab179841b96043"
    ),
    V4_TIMED_QUALIFICATION_CUDA_SNAPSHOT: (
        "04a5acf780d30dbd13dcf97f33e308285f3e5a71e1040977d1e7ac899cf2f0d7"
    ),
    V4_TIMED_QUALIFICATION_TERMINATION_AUDIT_SNAPSHOT: (
        "193faab74506cbce725f3c256c31cb8d7072e26866f29eff047c519ca53d5ea3"
    ),
}
V5_REVIEW_INPUT_DIRECTORY = (
    "docs/consciousness_sae_target_blind_calibration/reviews/"
    "audit_recovery_landlock_gpt_pro_v5_inputs"
)
V5_LOCAL_TEST_RECEIPT_SNAPSHOT = (
    f"{V5_REVIEW_INPUT_DIRECTORY}/{LOCAL_TEST_RECEIPT_NAME}"
)
V5_TARGET_HOST_TEST_RECEIPT_SNAPSHOT = (
    f"{V5_REVIEW_INPUT_DIRECTORY}/{TARGET_HOST_TEST_RECEIPT_NAME}"
)
V5_TARGET_QUALIFICATION_OWNERSHIP_SNAPSHOT = (
    f"{V5_REVIEW_INPUT_DIRECTORY}/{TARGET_QUALIFICATION_OWNERSHIP_NAME}"
)
V5_TARGET_QUALIFICATION_LANDLOCK_SNAPSHOT = (
    f"{V5_REVIEW_INPUT_DIRECTORY}/{TARGET_QUALIFICATION_LANDLOCK_NAME}"
)
V5_TARGET_QUALIFICATION_CUDA_SNAPSHOT = (
    f"{V5_REVIEW_INPUT_DIRECTORY}/{TARGET_QUALIFICATION_CUDA_NAME}"
)
FINAL_V5_PRO_REVIEW_DIRECTORY = (
    "docs/consciousness_sae_target_blind_calibration/reviews/"
    "audit_recovery_landlock_gpt_pro_v5_completed"
)
FINAL_V5_PRO_REVIEW_ADJUDICATION_JSON = (
    "docs/consciousness_sae_target_blind_calibration/reviews/"
    "AUDIT_RECOVERY_LANDLOCK_GPT_PRO_V5_ADJUDICATION.json"
)
FINAL_V5_PRO_REVIEW_ADJUDICATION_MARKDOWN = (
    "docs/consciousness_sae_target_blind_calibration/reviews/"
    "AUDIT_RECOVERY_LANDLOCK_GPT_PRO_V5_ADJUDICATION.md"
)
FINAL_V5_PRO_REVIEW_OUTPUT_PATHS = (
    FINAL_V5_PRO_REVIEW_ADJUDICATION_JSON,
    FINAL_V5_PRO_REVIEW_ADJUDICATION_MARKDOWN,
    f"{FINAL_V5_PRO_REVIEW_DIRECTORY}/request_payload.json",
    f"{FINAL_V5_PRO_REVIEW_DIRECTORY}/response.json",
    f"{FINAL_V5_PRO_REVIEW_DIRECTORY}/review.md",
    f"{FINAL_V5_PRO_REVIEW_DIRECTORY}/review_manifest.json",
    f"{FINAL_V5_PRO_REVIEW_DIRECTORY}/review_request.md",
)
HISTORICAL_V5_POSITIVE_REVIEW_PHYSICAL_SHA256 = {
    FINAL_V5_PRO_REVIEW_ADJUDICATION_JSON: (
        "896e9712f6047ca4ddf3a4b992efe07795702665a12e0ce0d10cef9fb3814e47"
    ),
    FINAL_V5_PRO_REVIEW_ADJUDICATION_MARKDOWN: (
        "01eba1850a5578fed06b6af8bc760b2e0ef32648931fbddce8169136243b97da"
    ),
    f"{FINAL_V5_PRO_REVIEW_DIRECTORY}/request_payload.json": (
        "61842691ad8080693c273405af486bd2795d3bcf666d0eb0d16f10f7218f25da"
    ),
    f"{FINAL_V5_PRO_REVIEW_DIRECTORY}/response.json": (
        "3e81e2ed357b949b296ce9693e53b2f164c7c86c82159761fabddb0a691fdeb2"
    ),
    f"{FINAL_V5_PRO_REVIEW_DIRECTORY}/review.md": (
        "11fe4403eb9c6e9fbf4dc3e59e8211d3cd98667657d9e9c2210360f65771b9e4"
    ),
    f"{FINAL_V5_PRO_REVIEW_DIRECTORY}/review_manifest.json": (
        "da53103fdd26ba18166adb1680423b329f683dce87409d35ed5d2d181450eb56"
    ),
    f"{FINAL_V5_PRO_REVIEW_DIRECTORY}/review_request.md": (
        "4953ea163fd02f6b9dc65b7205dbaa166749717ce7a1e74583f7d801fc60e7a9"
    ),
    V5_LOCAL_TEST_RECEIPT_SNAPSHOT: (
        "3a570bc92a15c298a572deb1123fd3a07d1dd779e8224fb82c57ee1d0de86767"
    ),
    V5_TARGET_HOST_TEST_RECEIPT_SNAPSHOT: (
        "76dff49824b0933a33ffdc8a5facfe9ef7495c95f201900560a99d4032a6c1c7"
    ),
    V5_TARGET_QUALIFICATION_OWNERSHIP_SNAPSHOT: (
        "abc9925fd413bda6033f69428c48e108bfed5a59a85b3accf2b3ef12d6bcce36"
    ),
    V5_TARGET_QUALIFICATION_LANDLOCK_SNAPSHOT: (
        "0b5af3f6c1fe1f0da7ece718bd3c786d6ea96e483ce665f33d8e4a75d0a757cf"
    ),
    V5_TARGET_QUALIFICATION_CUDA_SNAPSHOT: (
        "8f4ea22d9fd975229a7fea9827f352f299c5f49bfc3fa0fd18cb68da1cb2133c"
    ),
}
HISTORICAL_V5_POSITIVE_FINDING_IDS = (
    "B01",
    "B02",
    "B03",
    "B04",
    "B06",
    "B07",
    "B08",
    "B09",
    "B10",
    "B11",
    "B12",
    "B13",
    "I01",
    "I02",
    "I03",
    "I04",
    "I05",
    "I06",
    "I07",
    "I08",
    "I09",
)
HISTORICAL_V5_INPUT_TOKENS_PREFLIGHT = 336_765
HISTORICAL_V5_RECORDED_COST_USD = 7.7812
HISTORICAL_V5_RETROSPECTIVE_LONG_CONTEXT_COST_USD = 15.121205
HISTORICAL_V5_BUDGET_AUTHORIZATION_USD = 25.0
HISTORICAL_V4_INPUT_TOKENS_PREFLIGHT = 274_606
HISTORICAL_V4_RECORDED_COST_USD = 6.48768
HISTORICAL_V4_RETROSPECTIVE_LONG_CONTEXT_COST_USD = 12.555555
HISTORICAL_V4_BUDGET_AUTHORIZATION_USD = 25.0
C6_SUPERSEDED_QUALIFICATION_DIRECTORY = (
    "docs/consciousness_sae_target_blind_calibration/reviews/"
    "audit_recovery_landlock_c6_superseded_qualification"
)
C6_SUPERSEDED_QUALIFICATION_PHYSICAL_SHA256 = {
    f"{C6_SUPERSEDED_QUALIFICATION_DIRECTORY}/LOCAL_TEST_RECEIPT.json": (
        "192f7a2b4268311bbe16112b9a2ec37e91065b46aeb6da0618e14e7d77271d6b"
    ),
    f"{C6_SUPERSEDED_QUALIFICATION_DIRECTORY}/TARGET_HOST_TEST_RECEIPT.json": (
        "0f259ba418856bf17429a75edc8e5ded4dffbc145480435d675d7ef667f00c5e"
    ),
    f"{C6_SUPERSEDED_QUALIFICATION_DIRECTORY}/TARGET_QUALIFICATION_OWNERSHIP.json": (
        "a62132284f6a1e281102c6fcfeb6361c736f73d3af066720a54ead6711894d29"
    ),
    f"{C6_SUPERSEDED_QUALIFICATION_DIRECTORY}/"
    "TARGET_QUALIFICATION_LANDLOCK_ENFORCEMENT.json": (
        "a2452daf78bd4cdc639e3e0b0c1a96d546a65e0d517c1589382cca076dc74c86"
    ),
    f"{C6_SUPERSEDED_QUALIFICATION_DIRECTORY}/"
    "TARGET_QUALIFICATION_LANDLOCK_CUDA_PREFLIGHT.json": (
        "93c6d5bd66b1518e8ea4285d009cb9f6fabdaf288d4945492346fd6351a566e4"
    ),
    f"{C6_SUPERSEDED_QUALIFICATION_DIRECTORY}/QUALIFICATION_TERMINATION_AUDIT.json": (
        "ad85debce16388f505709a7bc7e035c680a6773135167e0b97ef90b0c6e8b43e"
    ),
    f"{C6_SUPERSEDED_QUALIFICATION_DIRECTORY}/QUALIFICATION_FROZEN_TERMINATION.json": (
        "138a39a87b332da98277998c9b709822c331077a770a71a8abe39cd0b7f5ac99"
    ),
    f"{C6_SUPERSEDED_QUALIFICATION_DIRECTORY}/"
    "QUALIFICATION_POSTDELETE_INVENTORY.json": (
        "78175ab88acae3c157ecb91fe36525dfee7d234d2e717056598029247b193796"
    ),
}
C7_FAILED_QUALIFICATION_DIRECTORY = (
    "docs/consciousness_sae_target_blind_calibration/reviews/"
    "audit_recovery_landlock_c7_failed_qualification"
)
C7_FAILED_QUALIFICATION_PHYSICAL_SHA256 = {
    f"{C7_FAILED_QUALIFICATION_DIRECTORY}/QUALIFICATION_STATUS.json": (
        "8a7b4f9750d9648d45b99f030d8f76800a26d4a1c3b6c819d58737ae392e36a2"
    ),
    f"{C7_FAILED_QUALIFICATION_DIRECTORY}/remote.stdout": (
        "83a573b66f74ba07ee0df08b7484f5e60fd4298964b259b3e1db9c2a3142d5dc"
    ),
    f"{C7_FAILED_QUALIFICATION_DIRECTORY}/remote.stderr": (
        "e126f6d1a54a5458002985aa70e7d4c5ed9ba8fe53f9fd41dd2b52ecb7232777"
    ),
    f"{C7_FAILED_QUALIFICATION_DIRECTORY}/run_target_qualification.sh": (
        "49caca53952b9c00ab27536b78d2df928094dd986450074a4d66f77ae405315a"
    ),
    f"{C7_FAILED_QUALIFICATION_DIRECTORY}/SHA256SUMS": (
        "2288175d16433f881a07b50bc33d0c6efef2fd7d49e0c1aaf79aa81a12dc8378"
    ),
}
V6_REVIEW_INPUT_DIRECTORY = (
    "docs/consciousness_sae_target_blind_calibration/reviews/"
    "audit_recovery_landlock_gpt_pro_v6_inputs"
)
V6_LOCAL_TEST_RECEIPT_SNAPSHOT = (
    f"{V6_REVIEW_INPUT_DIRECTORY}/{LOCAL_TEST_RECEIPT_NAME}"
)
V6_TARGET_HOST_TEST_RECEIPT_SNAPSHOT = (
    f"{V6_REVIEW_INPUT_DIRECTORY}/{TARGET_HOST_TEST_RECEIPT_NAME}"
)
V6_TARGET_QUALIFICATION_OWNERSHIP_SNAPSHOT = (
    f"{V6_REVIEW_INPUT_DIRECTORY}/{TARGET_QUALIFICATION_OWNERSHIP_NAME}"
)
V6_TARGET_QUALIFICATION_LANDLOCK_SNAPSHOT = (
    f"{V6_REVIEW_INPUT_DIRECTORY}/{TARGET_QUALIFICATION_LANDLOCK_NAME}"
)
V6_TARGET_QUALIFICATION_CUDA_SNAPSHOT = (
    f"{V6_REVIEW_INPUT_DIRECTORY}/{TARGET_QUALIFICATION_CUDA_NAME}"
)
FINAL_V6_PRO_REVIEW_DIRECTORY = (
    "docs/consciousness_sae_target_blind_calibration/reviews/"
    "audit_recovery_landlock_gpt_pro_v6_completed"
)
FINAL_V6_PRO_REVIEW_ADJUDICATION_JSON = (
    "docs/consciousness_sae_target_blind_calibration/reviews/"
    "AUDIT_RECOVERY_LANDLOCK_GPT_PRO_V6_ADJUDICATION.json"
)
FINAL_V6_PRO_REVIEW_ADJUDICATION_MARKDOWN = (
    "docs/consciousness_sae_target_blind_calibration/reviews/"
    "AUDIT_RECOVERY_LANDLOCK_GPT_PRO_V6_ADJUDICATION.md"
)
FINAL_V6_PRO_REVIEW_OUTPUT_PATHS = (
    FINAL_V6_PRO_REVIEW_ADJUDICATION_JSON,
    FINAL_V6_PRO_REVIEW_ADJUDICATION_MARKDOWN,
    f"{FINAL_V6_PRO_REVIEW_DIRECTORY}/request_payload.json",
    f"{FINAL_V6_PRO_REVIEW_DIRECTORY}/response.json",
    f"{FINAL_V6_PRO_REVIEW_DIRECTORY}/review.md",
    f"{FINAL_V6_PRO_REVIEW_DIRECTORY}/review_manifest.json",
    f"{FINAL_V6_PRO_REVIEW_DIRECTORY}/review_request.md",
)
HISTORICAL_V6_NONADJUDICABLE_REVIEW_OUTPUT_PATHS = (
    f"{FINAL_V6_PRO_REVIEW_DIRECTORY}/request_payload.json",
    f"{FINAL_V6_PRO_REVIEW_DIRECTORY}/response.json",
    f"{FINAL_V6_PRO_REVIEW_DIRECTORY}/review.md",
    f"{FINAL_V6_PRO_REVIEW_DIRECTORY}/review_manifest.json",
    f"{FINAL_V6_PRO_REVIEW_DIRECTORY}/review_request.md",
)
HISTORICAL_V6_NONADJUDICABLE_REVIEW_PHYSICAL_SHA256 = {
    f"{FINAL_V6_PRO_REVIEW_DIRECTORY}/request_payload.json": (
        "565dd71160456e6d0570d00888dfbcffd657e55491679f4c88d17c6aee4017b8"
    ),
    f"{FINAL_V6_PRO_REVIEW_DIRECTORY}/response.json": (
        "419c416a49dac0d936476e65f84866580adb30c789a6f336a34bc584bd88df52"
    ),
    f"{FINAL_V6_PRO_REVIEW_DIRECTORY}/review.md": (
        "750e5ab386a08038fa6378a827af8b16bbebf97147022334b05d5ab5691a7c6c"
    ),
    f"{FINAL_V6_PRO_REVIEW_DIRECTORY}/review_manifest.json": (
        "893ae3486f3c41492c45c9688e0bb28cdf64957fbc515b42022a91c5d2dd191f"
    ),
    f"{FINAL_V6_PRO_REVIEW_DIRECTORY}/review_request.md": (
        "1d6ef38b6234c2f0a3f8a804c198b976128c6879876de4d425a720b547f20600"
    ),
}
HISTORICAL_V6_NONADJUDICABLE_FINDING_IDS = (
    "B01",
    "B02",
    "B03",
    "B04",
    "B06",
    "B07",
    "B08",
    "B09",
    "B10",
    "B11",
    "B12",
    "B13",
    "B14",
    "B15",
    "I01",
    "I02",
    "I03",
    "I04",
    "I05",
    "I06",
    "I07",
    "I08",
    "I09",
)
V7_REVIEW_INPUT_DIRECTORY = (
    "docs/consciousness_sae_target_blind_calibration/reviews/"
    "audit_recovery_landlock_gpt_pro_v7_inputs"
)
V7_LOCAL_TEST_RECEIPT_SNAPSHOT = (
    f"{V7_REVIEW_INPUT_DIRECTORY}/{LOCAL_TEST_RECEIPT_NAME}"
)
V7_TARGET_HOST_TEST_RECEIPT_SNAPSHOT = (
    f"{V7_REVIEW_INPUT_DIRECTORY}/{TARGET_HOST_TEST_RECEIPT_NAME}"
)
V7_TARGET_QUALIFICATION_OWNERSHIP_SNAPSHOT = (
    f"{V7_REVIEW_INPUT_DIRECTORY}/{TARGET_QUALIFICATION_OWNERSHIP_NAME}"
)
V7_TARGET_QUALIFICATION_LANDLOCK_SNAPSHOT = (
    f"{V7_REVIEW_INPUT_DIRECTORY}/{TARGET_QUALIFICATION_LANDLOCK_NAME}"
)
V7_TARGET_QUALIFICATION_CUDA_SNAPSHOT = (
    f"{V7_REVIEW_INPUT_DIRECTORY}/{TARGET_QUALIFICATION_CUDA_NAME}"
)
FINAL_V7_PRO_REVIEW_DIRECTORY = (
    "docs/consciousness_sae_target_blind_calibration/reviews/"
    "audit_recovery_landlock_gpt_pro_v7_completed"
)
FINAL_V7_PRO_REVIEW_ADJUDICATION_JSON = (
    "docs/consciousness_sae_target_blind_calibration/reviews/"
    "AUDIT_RECOVERY_LANDLOCK_GPT_PRO_V7_ADJUDICATION.json"
)
FINAL_V7_PRO_REVIEW_ADJUDICATION_MARKDOWN = (
    "docs/consciousness_sae_target_blind_calibration/reviews/"
    "AUDIT_RECOVERY_LANDLOCK_GPT_PRO_V7_ADJUDICATION.md"
)
FINAL_V7_PRO_REVIEW_OUTPUT_PATHS = (
    FINAL_V7_PRO_REVIEW_ADJUDICATION_JSON,
    FINAL_V7_PRO_REVIEW_ADJUDICATION_MARKDOWN,
    f"{FINAL_V7_PRO_REVIEW_DIRECTORY}/request_payload.json",
    f"{FINAL_V7_PRO_REVIEW_DIRECTORY}/response.json",
    f"{FINAL_V7_PRO_REVIEW_DIRECTORY}/review.md",
    f"{FINAL_V7_PRO_REVIEW_DIRECTORY}/review_manifest.json",
    f"{FINAL_V7_PRO_REVIEW_DIRECTORY}/review_request.md",
)
HISTORICAL_V7_POSITIVE_REVIEW_PHYSICAL_SHA256 = {
    FINAL_V7_PRO_REVIEW_ADJUDICATION_JSON: (
        "0eb64d7ef327056ba6872b56b6bff3eaef2d9575115463cd2771cc51bda9e787"
    ),
    FINAL_V7_PRO_REVIEW_ADJUDICATION_MARKDOWN: (
        "a65ae2064b5b32b50afb17b114dab0dac18cecc573edb4cf4a3698c3af7d8dc0"
    ),
    f"{FINAL_V7_PRO_REVIEW_DIRECTORY}/request_payload.json": (
        "3595d50b08a1e1f2f009238570aab4ed5cc58be894384d81b7dcbcb29ac7a279"
    ),
    f"{FINAL_V7_PRO_REVIEW_DIRECTORY}/response.json": (
        "0994d4050fc3a0e4c3664e7c42572ef37488f5a660f717d96cfeb728450e231f"
    ),
    f"{FINAL_V7_PRO_REVIEW_DIRECTORY}/review.md": (
        "75607c805f68833f5826175c66a89544dbcb4b65a9471803ffd806c65f600672"
    ),
    f"{FINAL_V7_PRO_REVIEW_DIRECTORY}/review_manifest.json": (
        "24bf65a4fca84db9149783b3017f4f3953b1c8cd24a19f1f4150f95d12c1768f"
    ),
    f"{FINAL_V7_PRO_REVIEW_DIRECTORY}/review_request.md": (
        "19dcdf32f353d6898a3e432f22750a47a54bf549281f577da92ca8f0856b7389"
    ),
}
HISTORICAL_V7_POSITIVE_FINDING_IDS = (
    "B01", "B02", "B03", "B04", "B06", "B07", "B08", "B09",
    "B10", "B11", "B12", "B13", "B14", "B15", "B16",
    "I01", "I02", "I03", "I04", "I05", "I06", "I07", "I08", "I09",
)
HISTORICAL_B17_PRO_REVIEW_DIRECTORY = (
    "docs/consciousness_sae_target_blind_calibration/reviews/"
    "audit_recovery_bindingfix_gpt_pro_20260715_completed"
)
HISTORICAL_B17_PRO_REVIEW_PHYSICAL_SHA256 = {
    f"{HISTORICAL_B17_PRO_REVIEW_DIRECTORY}/request_payload.json": (
        "9dee2b68e81fdfce82dcfeae2a9c58ef8f328d3c5ac449565fbb40c0c933a1b4"
    ),
    f"{HISTORICAL_B17_PRO_REVIEW_DIRECTORY}/response.json": (
        "2f97c324f99ebe6e8fa3217b1a6ff2b11522e54308f332b4d0ab4bbe0647a4fd"
    ),
    f"{HISTORICAL_B17_PRO_REVIEW_DIRECTORY}/review.md": (
        "6cf7601b6d218bc348b1e15f84845676749861e8fa0f5c51a42a0a452012107d"
    ),
    f"{HISTORICAL_B17_PRO_REVIEW_DIRECTORY}/review_manifest.json": (
        "4971619899e03cfa3dc6dddc694a740c7dd3d761654266337452aeaedbdf2881"
    ),
    f"{HISTORICAL_B17_PRO_REVIEW_DIRECTORY}/review_request.md": (
        "697eab33a379290799ca739c203c3ef157f7ca519a801dbef2011f75c271bbe7"
    ),
}
HISTORICAL_B17_FINDING_IDS = ("B17", "B18", "B19", "I10", "I11", "I12")
B18_COMPACT_EVIDENCE_DIRECTORY = (
    "docs/consciousness_sae_target_blind_calibration/reviews/"
    "audit_recovery_b18_cleanup_closure"
)
B18_COMPACT_EVIDENCE_PHYSICAL_SHA256 = {
    f"{B18_COMPACT_EVIDENCE_DIRECTORY}/B18_CLOSURE_RECEIPT.json": (
        "e53b5656300c78740c6e6698a80b72e02c8467f825a48d1dbaa19e266c405748"
    ),
    f"{B18_COMPACT_EVIDENCE_DIRECTORY}/B18_VERIFICATION_OUTPUT.json": (
        "b9325d744eca0dc34c31ff9dbfdf91666ef8bca38eb5ac802387a6bdd1f0145a"
    ),
    f"{B18_COMPACT_EVIDENCE_DIRECTORY}/DESIGNATED_OUTPUT_TREE_INVENTORY.json": (
        "006fae24117af7878d7277bd205a39639386b29ee0f3bc0122937db97f19eec8"
    ),
    f"{B18_COMPACT_EVIDENCE_DIRECTORY}/RETRIEVED_ATTEMPT_TREE_INVENTORY.json": (
        "c39fcaa03539cb1cfd9396e8688112184ddabaaedf4694a4c7e98689803cf1f4"
    ),
}
B20_INCIDENT_DOCUMENT = (
    "docs/consciousness_sae_target_blind_calibration/"
    "AUDIT_RECOVERY_V8_B20_INCIDENT.md"
)
B20_COMPACT_EVIDENCE_DIRECTORY = (
    "docs/consciousness_sae_target_blind_calibration/reviews/"
    "audit_recovery_b20_gitless_active_incident"
)
B20_COMPACT_EVIDENCE_PHYSICAL_SHA256 = {
    f"{B20_COMPACT_EVIDENCE_DIRECTORY}/ATTEMPT_TREE_INVENTORY.json": "7661f26235ec919924bd126fc0e2a29c323059031ae1a82337395e4a3e17ab5f",
    f"{B20_COMPACT_EVIDENCE_DIRECTORY}/B20.md": "d807944aa8801228984077e6d3a044dafe8d039944b44d19f81c8e799fd89bf0",
    f"{B20_COMPACT_EVIDENCE_DIRECTORY}/B20_CLOSURE_RECEIPT.json": "e3b2e3d28bb6f0f865be968c969393c106fe16f3429f2b8a0f01e7bc8549fa4b",
    f"{B20_COMPACT_EVIDENCE_DIRECTORY}/B20_VERIFICATION_OUTPUT.json": "f1b23d4f49df732dae5e05f1ff685e8d8e13d6cb65c7202b8459547e25b47d15",
    f"{B20_COMPACT_EVIDENCE_DIRECTORY}/DESIGNATED_OUTPUT_TREE_INVENTORY.json": "5ca6aeb934188ba7a9757e1579d29a9e6f9a4faa619500ee5695c6d38220509e",
    f"{B20_COMPACT_EVIDENCE_DIRECTORY}/SHA256SUMS": "654a2dabcac3a783fbe27e4a9895dcab1d0c7c7225a5220982d33aa20c48d6c8",
    f"{B20_COMPACT_EVIDENCE_DIRECTORY}/SOURCE_ARCHIVE_VERIFICATION_OUTPUT.json": "bcb5340a1136674793466c5eb789a822fd1fbc6cc616c0a807cdc6c04c8da2d2",
    f"{B20_COMPACT_EVIDENCE_DIRECTORY}/attachments/AUTHORIZATION_BINDING.json": "0bb80f98f0b199a94c866fd02de9500b464dfdc4e3ebd55f9775e0cb116d9014",
    f"{B20_COMPACT_EVIDENCE_DIRECTORY}/attachments/FAILURE_EVIDENCE.json": "9be15025415447e9cc1c61c65699c8a8e026934bea361d1bbf011f1a08871e5c",
    f"{B20_COMPACT_EVIDENCE_DIRECTORY}/attachments/FROZEN_TERMINATION.json": "8c6ab40983c8b7bdec3162c7234cb86669699fbe81c9c912cf05b77b71edc156",
    f"{B20_COMPACT_EVIDENCE_DIRECTORY}/attachments/LANDLOCK_BINDING.json": "c8859eba627b376a1a6ef9b3661fd3f4719b977762a15bf09dfd88d800d3658a",
    f"{B20_COMPACT_EVIDENCE_DIRECTORY}/attachments/LAUNCH_BINDING.json": "cd3d69aa62a7fc9c2495bbd3aafa6629dead7c1684fd44db9d70d127cd81f435",
    f"{B20_COMPACT_EVIDENCE_DIRECTORY}/attachments/OWNERSHIP.json": "445de6bbaef6df69ffe8c65d2da689207367eacc89353ca164271dff069983a8",
    f"{B20_COMPACT_EVIDENCE_DIRECTORY}/attachments/POSTCREATE_INVENTORY.json": "1b2cb3063ca4ce057c18d884b69ccb936bd0f47a6f641c2af70a61e2d2cf9d42",
    f"{B20_COMPACT_EVIDENCE_DIRECTORY}/attachments/POSTDELETE_INVENTORY.json": "89597e9200deef14657e976988c526aeb7c20a3d4e9e453cf2e2f131544110e7",
    f"{B20_COMPACT_EVIDENCE_DIRECTORY}/attachments/PRECREATE_INVENTORY.json": "793671ca893cb22312d031833df496f767ba08f116de8326954633a1433b092f",
    f"{B20_COMPACT_EVIDENCE_DIRECTORY}/attachments/TERMINATION_AUDIT.json": "50eae10f172511ad1ed1931d873f875dab0c4441578537ec3c9a618cc54e6bd1",
    f"{B20_COMPACT_EVIDENCE_DIRECTORY}/verify_b20_public_compact.py": "11381aba2d87c7a94d08e8c2d37caa5685ae49af4af4a58cfee868635f131e5a",
}
V8_REVIEW_INPUT_DIRECTORY = (
    "docs/consciousness_sae_target_blind_calibration/reviews/"
    "audit_recovery_landlock_gpt_pro_v8_inputs"
)
V8_LOCAL_TEST_RECEIPT_SNAPSHOT = f"{V8_REVIEW_INPUT_DIRECTORY}/{LOCAL_TEST_RECEIPT_NAME}"
V8_TARGET_HOST_TEST_RECEIPT_SNAPSHOT = f"{V8_REVIEW_INPUT_DIRECTORY}/{TARGET_HOST_TEST_RECEIPT_NAME}"
V8_TARGET_QUALIFICATION_OWNERSHIP_SNAPSHOT = f"{V8_REVIEW_INPUT_DIRECTORY}/{TARGET_QUALIFICATION_OWNERSHIP_NAME}"
V8_TARGET_QUALIFICATION_LANDLOCK_SNAPSHOT = f"{V8_REVIEW_INPUT_DIRECTORY}/{TARGET_QUALIFICATION_LANDLOCK_NAME}"
V8_TARGET_QUALIFICATION_CUDA_SNAPSHOT = f"{V8_REVIEW_INPUT_DIRECTORY}/{TARGET_QUALIFICATION_CUDA_NAME}"
FINAL_V8_PRO_REVIEW_DIRECTORY = (
    "docs/consciousness_sae_target_blind_calibration/reviews/"
    "audit_recovery_landlock_gpt_pro_v8_completed"
)
FINAL_V8_PRO_REVIEW_ADJUDICATION_JSON = (
    "docs/consciousness_sae_target_blind_calibration/reviews/"
    "AUDIT_RECOVERY_LANDLOCK_GPT_PRO_V8_ADJUDICATION.json"
)
FINAL_V8_PRO_REVIEW_ADJUDICATION_MARKDOWN = (
    "docs/consciousness_sae_target_blind_calibration/reviews/"
    "AUDIT_RECOVERY_LANDLOCK_GPT_PRO_V8_ADJUDICATION.md"
)
FINAL_V8_PRO_REVIEW_OUTPUT_PATHS = (
    FINAL_V8_PRO_REVIEW_ADJUDICATION_JSON,
    FINAL_V8_PRO_REVIEW_ADJUDICATION_MARKDOWN,
    f"{FINAL_V8_PRO_REVIEW_DIRECTORY}/request_payload.json",
    f"{FINAL_V8_PRO_REVIEW_DIRECTORY}/response.json",
    f"{FINAL_V8_PRO_REVIEW_DIRECTORY}/review.md",
    f"{FINAL_V8_PRO_REVIEW_DIRECTORY}/review_manifest.json",
    f"{FINAL_V8_PRO_REVIEW_DIRECTORY}/review_request.md",
)
PRO_REVIEW_V5_PACKET = (
    (
        "docs/consciousness_sae_target_blind_calibration/AUDIT_RECOVERY_20260714.md",
        "complete experiment plan",
    ),
    (
        "docs/consciousness_sae_target_blind_calibration/"
        "AUDIT_RECOVERY_REVIEW_CONTEXT.md",
        "bounded context 1",
    ),
    (
        "docs/consciousness_sae_target_blind_calibration/"
        "AUDIT_RECOVERY_SCIENTIFIC_EQUIVALENCE.json",
        "bounded context 2",
    ),
    (
        "docs/consciousness_sae_target_blind_calibration/"
        "AUDIT_RECOVERY_SCIENTIFIC_EQUIVALENCE.md",
        "bounded context 3",
    ),
    (
        "experiments/consciousness_sae_target_blind_calibration/"
        "scientific_equivalence.py",
        "bounded context 4",
    ),
    (
        "tests/consciousness_sae_target_blind_calibration/"
        "test_scientific_equivalence.py",
        "bounded context 5",
    ),
    (
        "experiments/consciousness_sae_target_blind_calibration/audit_recovery.py",
        "bounded context 6",
    ),
    (
        "tests/consciousness_sae_target_blind_calibration/test_audit_recovery.py",
        "bounded context 7",
    ),
    (
        "experiments/consciousness_sae_target_blind_calibration/confined_bootstrap.py",
        "bounded context 8",
    ),
    (
        "tests/consciousness_sae_target_blind_calibration/test_confined_bootstrap.py",
        "bounded context 9",
    ),
    (
        "experiments/consciousness_sae_target_blind_calibration/landlock_launcher.py",
        "bounded context 10",
    ),
    (
        "tests/consciousness_sae_target_blind_calibration/test_landlock_launcher.py",
        "bounded context 11",
    ),
    (
        "experiments/consciousness_sae_target_blind_calibration/"
        "recovery_bundle_verifier.py",
        "bounded context 12",
    ),
    (
        "tests/consciousness_sae_target_blind_calibration/"
        "test_recovery_bundle_verifier.py",
        "bounded context 13",
    ),
    (
        "experiments/consciousness_sae_target_blind_calibration/"
        "requirements-runpod-b200.txt",
        "bounded context 14",
    ),
    (
        "experiments/consciousness_sae_target_blind_calibration/setup_runpod_guest.sh",
        "bounded context 15",
    ),
    (
        "experiments/consciousness_sae_realization_validation/runpod_preflight.py",
        "bounded context 16",
    ),
    (
        f"{HISTORICAL_V4_NEGATIVE_REVIEW_DIRECTORY}/review.md",
        "bounded context 17",
    ),
    (
        f"{HISTORICAL_V4_NEGATIVE_REVIEW_DIRECTORY}/review_manifest.json",
        "bounded context 18",
    ),
    (
        HISTORICAL_V4_NEGATIVE_REVIEW_ADJUDICATION_JSON,
        "bounded context 19",
    ),
    (
        HISTORICAL_V4_NEGATIVE_REVIEW_ADJUDICATION_MARKDOWN,
        "bounded context 20",
    ),
    (V4_TIMED_QUALIFICATION_RECEIPT_SNAPSHOT, "bounded context 21"),
    (V4_TIMED_QUALIFICATION_OWNERSHIP_SNAPSHOT, "bounded context 22"),
    (V4_TIMED_QUALIFICATION_GUEST_SNAPSHOT, "bounded context 23"),
    (V4_TIMED_QUALIFICATION_CACHE_SNAPSHOT, "bounded context 24"),
    (V4_TIMED_QUALIFICATION_LANDLOCK_SNAPSHOT, "bounded context 25"),
    (V4_TIMED_QUALIFICATION_CUDA_SNAPSHOT, "bounded context 26"),
    (V4_TIMED_QUALIFICATION_TERMINATION_AUDIT_SNAPSHOT, "bounded context 27"),
    (V5_LOCAL_TEST_RECEIPT_SNAPSHOT, "bounded context 28"),
    (V5_TARGET_HOST_TEST_RECEIPT_SNAPSHOT, "bounded context 29"),
    (
        V5_TARGET_QUALIFICATION_OWNERSHIP_SNAPSHOT,
        "bounded context 30",
    ),
    (
        V5_TARGET_QUALIFICATION_LANDLOCK_SNAPSHOT,
        "bounded context 31",
    ),
    (
        V5_TARGET_QUALIFICATION_CUDA_SNAPSHOT,
        "bounded context 32",
    ),
)
_PRO_REVIEW_V6_PATHS = (
    "docs/consciousness_sae_target_blind_calibration/AUDIT_RECOVERY_20260714.md",
    "docs/consciousness_sae_target_blind_calibration/AUDIT_RECOVERY_REVIEW_CONTEXT.md",
    (
        "docs/consciousness_sae_target_blind_calibration/"
        "AUDIT_RECOVERY_V6_PREGPU_INCIDENT.md"
    ),
    (
        "docs/consciousness_sae_target_blind_calibration/"
        "AUDIT_RECOVERY_SCIENTIFIC_EQUIVALENCE.json"
    ),
    (
        "docs/consciousness_sae_target_blind_calibration/"
        "AUDIT_RECOVERY_SCIENTIFIC_EQUIVALENCE.md"
    ),
    "experiments/__init__.py",
    "experiments/consciousness_sae_realization_validation/__init__.py",
    "experiments/consciousness_sae_realization_validation/protocol.py",
    (
        "experiments/consciousness_sae_realization_validation/"
        "legacy_public_artifact_manifest.json"
    ),
    "experiments/consciousness_sae_target_blind_calibration/__init__.py",
    ("experiments/consciousness_sae_target_blind_calibration/review_adjudication.py"),
    "experiments/consciousness_sae_target_blind_calibration/orientation.py",
    "experiments/consciousness_sae_target_blind_calibration/audit.py",
    "experiments/consciousness_sae_target_blind_calibration/audit_runtime_shim.py",
    (
        "experiments/consciousness_sae_target_blind_calibration/"
        "scientific_equivalence.py"
    ),
    ("tests/consciousness_sae_target_blind_calibration/test_scientific_equivalence.py"),
    "experiments/consciousness_sae_target_blind_calibration/audit_recovery.py",
    "tests/consciousness_sae_target_blind_calibration/test_audit_recovery.py",
    "experiments/consciousness_sae_target_blind_calibration/confined_bootstrap.py",
    "tests/consciousness_sae_target_blind_calibration/test_confined_bootstrap.py",
    "experiments/consciousness_sae_target_blind_calibration/landlock_launcher.py",
    "tests/consciousness_sae_target_blind_calibration/test_landlock_launcher.py",
    (
        "experiments/consciousness_sae_target_blind_calibration/"
        "recovery_bundle_verifier.py"
    ),
    (
        "tests/consciousness_sae_target_blind_calibration/"
        "test_recovery_bundle_verifier.py"
    ),
    "experiments/consciousness_sae_target_blind_calibration/authorize.py",
    "experiments/consciousness_sae_target_blind_calibration/build_plan.py",
    "experiments/consciousness_sae_target_blind_calibration/validate_plan.py",
    "experiments/consciousness_sae_target_blind_calibration/protocol.py",
    (
        "data/consciousness_sae_target_blind_calibration/"
        "calibration_v2_plan_20260714_r3/source_files.json"
    ),
    (
        "data/consciousness_sae_target_blind_calibration/"
        "calibration_v2_plan_20260714_r3/plan_manifest.json"
    ),
    (
        "experiments/consciousness_sae_target_blind_calibration/"
        "requirements-runpod-b200.txt"
    ),
    "experiments/consciousness_sae_target_blind_calibration/setup_runpod_guest.sh",
    (
        "experiments/consciousness_sae_target_blind_calibration/"
        "requirements-runpod-b200-qualification.txt"
    ),
    (
        "experiments/consciousness_sae_target_blind_calibration/"
        "setup_runpod_qualification_guest.sh"
    ),
    (
        "experiments/consciousness_sae_target_blind_calibration/"
        "run_qualification_pipe_logged.sh"
    ),
    (
        "experiments/consciousness_sae_target_blind_calibration/"
        "runpod_qualification_controller.sh"
    ),
    "experiments/consciousness_sae_realization_validation/runpod_preflight.py",
    f"{HISTORICAL_V4_NEGATIVE_REVIEW_DIRECTORY}/review_manifest.json",
    f"{FINAL_V5_PRO_REVIEW_DIRECTORY}/review.md",
    f"{FINAL_V5_PRO_REVIEW_DIRECTORY}/review_manifest.json",
    FINAL_V5_PRO_REVIEW_ADJUDICATION_JSON,
    FINAL_V5_PRO_REVIEW_ADJUDICATION_MARKDOWN,
    *tuple(C6_SUPERSEDED_QUALIFICATION_PHYSICAL_SHA256),
    *tuple(C7_FAILED_QUALIFICATION_PHYSICAL_SHA256),
    V6_LOCAL_TEST_RECEIPT_SNAPSHOT,
    V6_TARGET_HOST_TEST_RECEIPT_SNAPSHOT,
    V6_TARGET_QUALIFICATION_OWNERSHIP_SNAPSHOT,
    V6_TARGET_QUALIFICATION_LANDLOCK_SNAPSHOT,
    V6_TARGET_QUALIFICATION_CUDA_SNAPSHOT,
)
PRO_REVIEW_V6_PACKET = tuple(
    (
        relative,
        "complete experiment plan" if index == 0 else f"bounded context {index}",
    )
    for index, relative in enumerate(_PRO_REVIEW_V6_PATHS)
)
PRO_REVIEW_V6_QUESTION = (
    "This is a prospective audit-only recovery, not a new model transaction. "
    "No recovered compact audit or summary has been generated or inspected. "
    "The complete positive v5 review, response metadata, and adjudication are "
    "included as bounded historical context and must be considered rather than "
    "reviewing this packet in isolation. After v5, the authentic first "
    "authorization call failed before GPU provisioning because two active "
    "qualification-modified dependency files differed from the immutable r3 "
    "source inventory. Treat that disclosed stop-ship as B14 and explicitly "
    "disposition it. Audit whether byte-restoring the two r3 runtime files, "
    "moving pytest to two separately bound qualification-only files, and adding "
    "the unmocked 41-file plan/provenance gate is the smallest sound repair. "
    "The first live C6 target qualification then exposed a shallow-checkout "
    "controller defect in an ancestry-dependent test; that operational failure "
    "was preserved and the controller was changed to fetch full history. A "
    "second qualification exposed a 114-byte AF_UNIX pathname. Although a short "
    "qualification root subsequently passed 198 tests, an offline calculation "
    "then proved that C6's actual production preflight and execution socket "
    "paths were 218 and 217 bytes, above Linux's 107-byte pathname maximum. "
    "Treat that production stop-ship as B15 and explicitly disposition it. "
    "Audit the repair that moves only the fresh attempt parent to /workspace/csae, "
    "uses the .s socket leaf, enforces a 91-byte operational budget with a "
    "16-byte reserve below 107 in the producer, launcher, and independent "
    "verifier, and regression-tests the exact 91-byte preflight and 90-byte "
    "execution paths plus byte-count boundary failures. The C6 freeze, five "
    "receipts, and termination chain are included in a separately pinned "
    "superseded-evidence directory as historical context only. The first live "
    "C7 successor qualification then failed closed before CUDA or tests because "
    "the controller redirected standard streams to writable regular files and "
    "the frozen descriptor audit rejected them. Its verified failure archive is "
    "disclosed in the incident document. The exact controller, pipe-backed "
    "wrapper and five selected failure-archive artifacts are included; verify "
    "that fresh target "
    "evidence demonstrates the unchanged descriptor audit and Landlock/CUDA "
    "preflight passed. C8 produced only a superseded local receipt and never "
    "received target-host qualification after a packet audit found stale "
    "lineage. Only fresh C9 qualification "
    "receipts in the v6 input directory can qualify the "
    "current source/test bytes. "
    "Verify the separately disclosed pre-review correction to the GPT-5.6 Sol "
    "long-context rate schedule and $75 reserve; no v6 paid call preceded it. "
    "Also verify the explicit immutable-versus-retrospective v4/v5 accounting: "
    "274,606 preflight tokens imply $12.555555 and 336,765 imply $15.121205 "
    "under the long-context rates, both below their $25 authorizations and "
    "neither claimed as an invoice. "
    "Confirm that the qualification wrapper is never invoked in final recovery. "
    "Also re-evaluate the full current exact-byte recovery, confinement, "
    "zero-forward, receipt, Git C9<=E9<=F9, and offline-verifier design in light "
    "of the missed v5 invocation defect and C6 qualification failures. Do not "
    "request or infer scientific "
    "result values. Explicitly disposition every historical B01-B04, B06-B13, "
    "and I01-I09 identifier from the supplied v5 review as well as B14 and B15; "
    "do not renumber or silently omit them. Return any genuinely new blocker as "
    "B16 or later and "
    "any genuinely new important finding as I10 or later. A READY TO FREEZE "
    "verdict must apply only to the exact source, tests, plan inventories, fresh "
    "qualification receipts, and prior-review context in this packet. Any "
    "packet-changing fix requires another separately authorized review."
)
_PRO_REVIEW_V7_PATHS = (
    *_PRO_REVIEW_V6_PATHS[:37],
    (
        "docs/consciousness_sae_target_blind_calibration/"
        "AUDIT_RECOVERY_V7_POSTREVIEW_INCIDENT.md"
    ),
    f"{FINAL_V6_PRO_REVIEW_DIRECTORY}/review.md",
    f"{FINAL_V6_PRO_REVIEW_DIRECTORY}/review_manifest.json",
    V7_LOCAL_TEST_RECEIPT_SNAPSHOT,
    V7_TARGET_HOST_TEST_RECEIPT_SNAPSHOT,
    V7_TARGET_QUALIFICATION_OWNERSHIP_SNAPSHOT,
    V7_TARGET_QUALIFICATION_LANDLOCK_SNAPSHOT,
    V7_TARGET_QUALIFICATION_CUDA_SNAPSHOT,
)
PRO_REVIEW_V7_PACKET = tuple(
    (
        relative,
        "complete experiment plan" if index == 0 else f"bounded context {index}",
    )
    for index, relative in enumerate(_PRO_REVIEW_V7_PATHS)
)
PRO_REVIEW_V7_QUESTION = (
    "This is the final prospective v7 audit-only successor review, not a new "
    "model transaction. No recovered compact audit or scientific summary has "
    "been generated or inspected. The complete immutable v6 review and its "
    "provider manifest are included as bounded historical context and must be "
    "considered. That exact paid v6 response returned READY TO FREEZE, but the "
    "reviewed prose-wide finding-ID extractor also treated a negated checklist "
    "mention of B05 as a finding and the reserved-ID gate correctly made the "
    "review non-adjudicable and non-authorizing. Treat that disclosed "
    "post-review stop-ship as B16 and explicitly disposition it. Audit whether "
    "extracting stable IDs only from ATX finding headings is the smallest sound "
    "repair. The repair must not rewrite, omit, or fabricate any v6 provider "
    "artifact or adjudication. Fresh C10 local and disposable-B200 qualification "
    "receipts in the v7 input directory alone qualify the current source/test "
    "bytes. Re-evaluate the complete current exact-byte recovery, confinement, "
    "zero-forward, receipt, C10<=E10<=F10 Git chain, and offline-verifier design "
    "in light of B16. Explicitly disposition every substantive historical "
    "finding heading B01-B04, B06-B15, and I01-I09, plus B16; do not renumber or "
    "silently omit them. Return any genuinely new blocker as B17 or later and "
    "any genuinely new important finding as I10 or later. Do not request or "
    "infer scientific result values. A READY TO FREEZE verdict applies only to "
    "the exact source, tests, plan inventories, fresh C10 receipts, immutable "
    "v6 review context, and B16 incident in this packet. Any packet-changing "
    "fix requires another separately authorized review."
)
FINAL_RECOVERY_CONTROLLER_TEMPLATE = (
    "experiments/consciousness_sae_target_blind_calibration/"
    "final_recovery_controller.sh"
)
FINAL_RECOVERY_WRAPPER_PATHS = (
    FINAL_RECOVERY_CONTROLLER_TEMPLATE,
    "experiments/consciousness_sae_target_blind_calibration/"
    "final_recovery_hash_exec_gate.py",
    "experiments/consciousness_sae_target_blind_calibration/"
    "validate_final_recovery_launch_gate.py",
    "experiments/consciousness_sae_target_blind_calibration/"
    "final_recovery_local_supervisor.sh",
    "experiments/consciousness_sae_target_blind_calibration/"
    "FINAL_RECOVERY_INVOCATION_CONTRACT.md",
    "experiments/consciousness_sae_target_blind_calibration/"
    "final_recovery_wrapper_self_test.py",
)
_PRO_REVIEW_V8_PATHS = (
    *_PRO_REVIEW_V6_PATHS[:37],
    *FINAL_RECOVERY_WRAPPER_PATHS[:4],
    B20_INCIDENT_DOCUMENT,
    f"{FINAL_V7_PRO_REVIEW_DIRECTORY}/review.md",
    f"{FINAL_V7_PRO_REVIEW_DIRECTORY}/review_manifest.json",
    FINAL_V7_PRO_REVIEW_ADJUDICATION_JSON,
    f"{HISTORICAL_B17_PRO_REVIEW_DIRECTORY}/review.md",
    f"{HISTORICAL_B17_PRO_REVIEW_DIRECTORY}/review_manifest.json",
    f"{B18_COMPACT_EVIDENCE_DIRECTORY}/B18_CLOSURE_RECEIPT.json",
    f"{B20_COMPACT_EVIDENCE_DIRECTORY}/B20_CLOSURE_RECEIPT.json",
    f"{B20_COMPACT_EVIDENCE_DIRECTORY}/B20_VERIFICATION_OUTPUT.json",
    V8_LOCAL_TEST_RECEIPT_SNAPSHOT,
    V8_TARGET_HOST_TEST_RECEIPT_SNAPSHOT,
    V8_TARGET_QUALIFICATION_OWNERSHIP_SNAPSHOT,
    V8_TARGET_QUALIFICATION_LANDLOCK_SNAPSHOT,
    V8_TARGET_QUALIFICATION_CUDA_SNAPSHOT,
)
PRO_REVIEW_V8_PACKET = tuple(
    (
        relative,
        "complete experiment plan" if index == 0 else f"bounded context {index}",
    )
    for index, relative in enumerate(_PRO_REVIEW_V8_PATHS)
)
PRO_REVIEW_V8_QUESTION = (
    "This is the final prospective v8 audit-only successor review, not a new "
    "model transaction. No recovered compact audit or scientific summary has "
    "been generated or inspected. Treat the immutable completed v7 review and "
    "adjudication as historical positive evidence, never as a review of the "
    "current bytes. Also consider the complete B17 focused-review feedback and "
    "manifest, including B17-B19 and I10-I12, plus the compact B18 and B20 "
    "mechanical closures. The first focused B17 call ended incomplete at "
    "max_output_tokens and the replacement returned READY AFTER SPECIFIED "
    "FIXES; both paid calls are disclosed. The B20 owned B200 attempt completed "
    "authentic issue-time authorization but failed before ATTEMPT_STARTED when "
    "final-confined validation invoked Git. The observed /dev/null error was "
    "only the first symptom because ACTIVE intentionally has no .git. Treat "
    "that stop-ship as B20 and explicitly disposition it. Audit the smallest "
    "repair: live Git ancestry and source/review diffs remain mandatory during "
    "issue from SOURCE; the exact final HEAD is sealed into the self-hashed "
    "authorization and cross-checked by the independent verifier; final ACTIVE "
    "repeats all byte and semantic checks without Git or any /dev/null write "
    "exception. Fresh C11 local and disposable-B200 qualification receipts in "
    "the v8 input directory alone qualify current source/test bytes. Verify the "
    "C11<=E11<=F11 chain, unchanged source/test bytes from C11 through F11, and "
    "unchanged provider-packet bytes from E11 through F11. Review the tracked "
    "generic final controller as exact source: its launch-gate-bound C11, E11, "
    "and F11 arguments must be validated before confinement and it must stage "
    "a repository-free exact ACTIVE closure. Explicitly disposition B17-B20 "
    "and I10-I12 without renumbering or omission. Return any genuinely new "
    "blocker as B21 or later and any genuinely new important finding as I13 or "
    "later. Do not request or infer scientific result values. A READY TO "
    "FREEZE verdict applies only to the exact current sources, tests, controller, "
    "plan inventories, fresh C11 receipts, immutable prior reviews, and compact "
    "incident evidence in this packet. Any new B21+ blocker stops launch; no "
    "post-review source fix may be hidden in F11."
)
PRO_REVIEW_QUESTION = (
    "This is a prospective audit-only recovery, not a new model transaction. "
    "The frozen r3 raw transaction already exists, but no recovered compact "
    "audit or summary has been generated or inspected. Find any stop-ship flaw "
    "in the narrow required-subset J correction, dual provenance, one-shot "
    "authorization, process-tree handled write confinement plus pre/post raw "
    "and provenance endpoint inventory equality (not continuous immutability), "
    "zero-forward claim, ABI-4 "
    "Landlock process-tree write confinement, exact NVIDIA device exceptions, "
    "the exact /proc/self/task path-beneath WRITE_FILE|TRUNCATE exception "
    "required for CUDA thread naming, "
    "same-PID handoff, environment/FD/mapping checks, CUDA preflight, failure "
    "semantics, or tests. Do not request or infer scientific result values. "
    "The completed v2, v3, and v4 reviews were negative. Explicitly disposition "
    "every existing B01-B04, B06-B12, and I01-I08 finding. B12's sole minimum "
    "repair adds the existing machine-readable scientific-equivalence JSON to "
    "the exact provider packet and reviewed-packet Git-diff closure, replaces the "
    "packet exclusion test with an inclusion test, and binds fresh local and "
    "target-host receipts from the new source/test freeze. Do not redesign the "
    "scientific or confinement plan. For B10, preserve and evaluate the exact "
    "seven-file timed qualification chain: "
    "it independently rehashed all 45 public-artifact files/156,023,372,845 "
    "bytes and reached authorization readiness at host age 958 seconds, leaving "
    "2,642 seconds and an 842-second reserve surplus. Its CUDA child necessarily "
    "used source_test_qualification before a positive successor review existed; the "
    "fresh recovery pod must repeat final_recovery scope. The target-host "
    "receipt comes from a disposable qualification pod; the later recovery pod "
    "must independently pass its same-host Landlock/CUDA gate. Return every new "
    "concrete blocker as B13 or later and every new important finding as I09 or "
    "later; do not recycle an existing ID. A READY TO "
    "FREEZE verdict must apply only to the exact source, tests, and receipt bytes "
    "in this packet. Any packet-changing fix requires another provider review."
)

AUDIT_EXECUTABLE_PATHS = (
    "experiments/__init__.py",
    "experiments/consciousness_sae_realization_validation/__init__.py",
    "experiments/consciousness_sae_realization_validation/protocol.py",
    "experiments/consciousness_sae_realization_validation/runpod_preflight.py",
    "experiments/consciousness_sae_realization_validation/"
    "legacy_public_artifact_manifest.json",
    "experiments/consciousness_sae_target_blind_calibration/__init__.py",
    "experiments/consciousness_sae_target_blind_calibration/protocol.py",
    "experiments/consciousness_sae_target_blind_calibration/build_plan.py",
    "experiments/consciousness_sae_target_blind_calibration/review_adjudication.py",
    "experiments/consciousness_sae_target_blind_calibration/validate_plan.py",
    "experiments/consciousness_sae_target_blind_calibration/orientation.py",
    "experiments/consciousness_sae_target_blind_calibration/authorize.py",
    "experiments/consciousness_sae_target_blind_calibration/audit.py",
    "experiments/consciousness_sae_target_blind_calibration/audit_runtime_shim.py",
    "experiments/consciousness_sae_target_blind_calibration/audit_recovery.py",
    "experiments/consciousness_sae_target_blind_calibration/confined_bootstrap.py",
    "experiments/consciousness_sae_target_blind_calibration/scientific_equivalence.py",
    "experiments/consciousness_sae_target_blind_calibration/landlock_launcher.py",
    "experiments/consciousness_sae_target_blind_calibration/"
    "recovery_bundle_verifier.py",
    "experiments/consciousness_sae_target_blind_calibration/"
    "requirements-runpod-b200.txt",
    "experiments/consciousness_sae_target_blind_calibration/"
    "requirements-runpod-b200-qualification.txt",
    "experiments/consciousness_sae_target_blind_calibration/setup_runpod_guest.sh",
    "experiments/consciousness_sae_target_blind_calibration/"
    "setup_runpod_qualification_guest.sh",
    "experiments/consciousness_sae_target_blind_calibration/"
    "run_qualification_pipe_logged.sh",
    "experiments/consciousness_sae_target_blind_calibration/"
    "runpod_qualification_controller.sh",
    *FINAL_RECOVERY_WRAPPER_PATHS,
)
RECOVERY_DOCUMENT_PATHS = (
    "data/consciousness_sae_target_blind_calibration/"
    "calibration_v2_plan_20260714_r3/plan_manifest.json",
    "data/consciousness_sae_target_blind_calibration/"
    "calibration_v2_plan_20260714_r3/source_files.json",
    "docs/consciousness_sae_target_blind_calibration/AUDIT_RECOVERY_20260714.md",
    "docs/consciousness_sae_target_blind_calibration/AUDIT_RECOVERY_REVIEW_CONTEXT.md",
    "docs/consciousness_sae_target_blind_calibration/"
    "AUDIT_RECOVERY_SCIENTIFIC_EQUIVALENCE.json",
    "docs/consciousness_sae_target_blind_calibration/"
    "AUDIT_RECOVERY_SCIENTIFIC_EQUIVALENCE.md",
    "docs/consciousness_sae_target_blind_calibration/"
    "AUDIT_RECOVERY_V6_PREGPU_INCIDENT.md",
    "docs/consciousness_sae_target_blind_calibration/"
    "AUDIT_RECOVERY_V7_POSTREVIEW_INCIDENT.md",
    B20_INCIDENT_DOCUMENT,
    *tuple(C7_FAILED_QUALIFICATION_PHYSICAL_SHA256),
    *tuple(HISTORICAL_INCOMPLETE_REVIEW_PHYSICAL_SHA256),
    *tuple(HISTORICAL_V2_PRO_REVIEW_PHYSICAL_SHA256),
    *tuple(HISTORICAL_V3_NEGATIVE_REVIEW_PHYSICAL_SHA256),
    *tuple(HISTORICAL_V4_NEGATIVE_REVIEW_PHYSICAL_SHA256),
    V3_LOCAL_TEST_RECEIPT_SNAPSHOT,
    V3_TARGET_HOST_TEST_RECEIPT_SNAPSHOT,
    V3_TARGET_QUALIFICATION_OWNERSHIP_SNAPSHOT,
    V3_TARGET_QUALIFICATION_LANDLOCK_SNAPSHOT,
    V3_TARGET_QUALIFICATION_CUDA_SNAPSHOT,
    *tuple(V4_TIMED_QUALIFICATION_PHYSICAL_SHA256),
    V4_LOCAL_TEST_RECEIPT_SNAPSHOT,
    V4_TARGET_HOST_TEST_RECEIPT_SNAPSHOT,
    V4_TARGET_QUALIFICATION_OWNERSHIP_SNAPSHOT,
    V4_TARGET_QUALIFICATION_LANDLOCK_SNAPSHOT,
    V4_TARGET_QUALIFICATION_CUDA_SNAPSHOT,
    V5_LOCAL_TEST_RECEIPT_SNAPSHOT,
    V5_TARGET_HOST_TEST_RECEIPT_SNAPSHOT,
    V5_TARGET_QUALIFICATION_OWNERSHIP_SNAPSHOT,
    V5_TARGET_QUALIFICATION_LANDLOCK_SNAPSHOT,
    V5_TARGET_QUALIFICATION_CUDA_SNAPSHOT,
    *FINAL_V5_PRO_REVIEW_OUTPUT_PATHS,
    *tuple(C6_SUPERSEDED_QUALIFICATION_PHYSICAL_SHA256),
    V6_LOCAL_TEST_RECEIPT_SNAPSHOT,
    V6_TARGET_HOST_TEST_RECEIPT_SNAPSHOT,
    V6_TARGET_QUALIFICATION_OWNERSHIP_SNAPSHOT,
    V6_TARGET_QUALIFICATION_LANDLOCK_SNAPSHOT,
    V6_TARGET_QUALIFICATION_CUDA_SNAPSHOT,
    *HISTORICAL_V6_NONADJUDICABLE_REVIEW_OUTPUT_PATHS,
    V7_LOCAL_TEST_RECEIPT_SNAPSHOT,
    V7_TARGET_HOST_TEST_RECEIPT_SNAPSHOT,
    V7_TARGET_QUALIFICATION_OWNERSHIP_SNAPSHOT,
    V7_TARGET_QUALIFICATION_LANDLOCK_SNAPSHOT,
    V7_TARGET_QUALIFICATION_CUDA_SNAPSHOT,
    *FINAL_V7_PRO_REVIEW_OUTPUT_PATHS,
    *tuple(HISTORICAL_B17_PRO_REVIEW_PHYSICAL_SHA256),
    *tuple(B18_COMPACT_EVIDENCE_PHYSICAL_SHA256),
    *tuple(B20_COMPACT_EVIDENCE_PHYSICAL_SHA256),
    V8_LOCAL_TEST_RECEIPT_SNAPSHOT,
    V8_TARGET_HOST_TEST_RECEIPT_SNAPSHOT,
    V8_TARGET_QUALIFICATION_OWNERSHIP_SNAPSHOT,
    V8_TARGET_QUALIFICATION_LANDLOCK_SNAPSHOT,
    V8_TARGET_QUALIFICATION_CUDA_SNAPSHOT,
    *FINAL_V8_PRO_REVIEW_OUTPUT_PATHS,
    "tests/consciousness_sae_target_blind_calibration/test_audit_recovery.py",
    "tests/consciousness_sae_target_blind_calibration/test_confined_bootstrap.py",
    "tests/consciousness_sae_target_blind_calibration/test_landlock_launcher.py",
    "tests/consciousness_sae_target_blind_calibration/test_recovery_bundle_verifier.py",
    "tests/consciousness_sae_target_blind_calibration/test_scientific_equivalence.py",
)
RECOVERY_BOUND_PATHS = tuple(
    sorted(set(AUDIT_EXECUTABLE_PATHS) | set(RECOVERY_DOCUMENT_PATHS))
)
SOURCE_TEST_BOUND_PATHS = tuple(
    path
    for path in RECOVERY_BOUND_PATHS
    if path.startswith("experiments/") or path.startswith("tests/")
)
FORBIDDEN_EXECUTABLE_PATHS = (
    "experiments/consciousness_sae_realization_validation/runtime.py",
    "experiments/consciousness_sae_realization_validation/guest_launcher.py",
    "experiments/consciousness_sae_realization_validation/runpod_orchestrator.py",
    "experiments/consciousness_sae_target_blind_calibration/runner.py",
    "experiments/consciousness_sae_target_blind_calibration/guest_launcher.py",
)
FORBIDDEN_MODULES = frozenset(
    {
        "experiments.consciousness_sae_realization_validation.runtime",
        "experiments.consciousness_sae_realization_validation.guest_launcher",
        "experiments.consciousness_sae_realization_validation.runpod_orchestrator",
        "experiments.consciousness_sae_target_blind_calibration.runner",
        "experiments.consciousness_sae_target_blind_calibration.guest_launcher",
    }
)
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


class AuditRecoveryError(RuntimeError):
    """The audit-only recovery closure is not admissible."""


def _validate_bound_canary_socket_path(
    root: PurePosixPath,
    label: str,
) -> None:
    path = root / OUTPUT_CANARY_SOCKET_NAME
    encoded = os.fsencode(path.as_posix())
    if (
        (
            AF_UNIX_PATH_MAX_BYTES,
            AF_UNIX_PATH_REQUIRED_MARGIN_BYTES,
            AF_UNIX_PATH_BUDGET_BYTES,
            OUTPUT_CANARY_SOCKET_NAME,
        )
        != (107, 16, 91, ".s")
        or AF_UNIX_PATH_BUDGET_BYTES
        != AF_UNIX_PATH_MAX_BYTES - AF_UNIX_PATH_REQUIRED_MARGIN_BYTES
        or b"\0" in encoded
        or len(encoded) > AF_UNIX_PATH_BUDGET_BYTES
    ):
        raise AuditRecoveryError(
            f"{label} Unix-socket canary path exceeds the frozen byte budget"
        )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while block := handle.read(8 * 1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def _reject_duplicate_json_keys(pairs: Sequence[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError(f"duplicate JSON key: {key}")
        value[key] = item
    return value


def _json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=_reject_duplicate_json_keys,
        )
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as exc:
        raise AuditRecoveryError(f"JSON is unreadable: {path}") from exc
    if not isinstance(value, dict) or not audit._finite_json(value):  # noqa: SLF001
        raise AuditRecoveryError(f"JSON root is invalid: {path}")
    return value


def _canonical_json_receipt(path: Path, label: str) -> dict[str, Any]:
    value = _json(path)
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise AuditRecoveryError(f"{label} is unreadable") from exc
    if raw != protocol.canonical_json_bytes(value) + b"\n":
        raise AuditRecoveryError(f"{label} is not canonical JSON")
    _self_hash(value, label)
    return value


def _canonical_absolute_posix_path(value: Any, label: str) -> str:
    if not isinstance(value, str):
        raise AuditRecoveryError(f"{label} is not a canonical absolute POSIX path")
    pure = PurePosixPath(value)
    if (
        not value.startswith("/")
        or value.startswith("//")
        or ".." in pure.parts
        or pure.as_posix() != value
    ):
        raise AuditRecoveryError(f"{label} is not a canonical absolute POSIX path")
    return value


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


def _inside(root: Path, candidate: Path) -> bool:
    try:
        root_absolute = root.expanduser().resolve(strict=True)
        candidate_lexical = candidate.expanduser().absolute()
        candidate_absolute = candidate.expanduser().resolve(strict=False)
    except OSError:
        return False
    return candidate_lexical.as_posix() == candidate_absolute.as_posix() and (
        candidate_absolute == root_absolute
        or root_absolute in candidate_absolute.parents
    )


def _inside_bound_path(
    root: Path, candidate: Path, *, require_live_paths: bool
) -> bool:
    """Check containment live on-host or lexically for relocated receipt paths."""

    if require_live_paths:
        return _inside(root, candidate)
    root_text = _canonical_absolute_posix_path(root.as_posix(), "bound root")
    candidate_text = _canonical_absolute_posix_path(
        candidate.as_posix(), "bound candidate"
    )
    root_path = PurePosixPath(root_text)
    candidate_path = PurePosixPath(candidate_text)
    return candidate_path == root_path or root_path in candidate_path.parents


def _validate_confinement_environment(output_root: Path) -> dict[str, str]:
    observed = {name: os.environ.get(name, "") for name in CONFINED_FIXED_ENVIRONMENT}
    if observed != CONFINED_FIXED_ENVIRONMENT:
        raise AuditRecoveryError("confined process environment differs")
    if any(name in os.environ for name in FORBIDDEN_CONFINED_ENVIRONMENT):
        raise AuditRecoveryError("forbidden confined environment variable is present")
    for name in CONFINED_WRITABLE_PATH_ENVIRONMENT:
        value = os.environ.get(name)
        if not value or not _inside(output_root, Path(value)):
            raise AuditRecoveryError(f"confined writable environment escaped: {name}")
        observed[name] = Path(value).expanduser().absolute().as_posix()
    return observed


def _validate_landlock_receipt(
    value: Mapping[str, Any],
    *,
    purpose: str,
    receipt_path: Path,
    output_root: Path,
    protected_roots: Sequence[Path],
    protected_files: Sequence[Path],
    canary_output_root: Path,
    device_files: Sequence[Path],
    expected_authorization_sha256: str | None,
    expected_preflight_receipt_sha256: str | None,
    require_current_pid: bool,
) -> dict[str, Any]:
    receipt = dict(value)
    _self_hash(receipt, "Landlock enforcement")
    pid = receipt.get("pid")
    if (
        receipt.get("schema_version") != 1
        or receipt.get("status") != "pass_landlock_enforced"
        or receipt.get("purpose") != purpose
        or not isinstance(pid, int)
        or pid <= 0
        or receipt.get("required_abi") != LANDLOCK_REQUIRED_ABI
        or not isinstance(receipt.get("observed_abi"), int)
        or int(receipt["observed_abi"]) < LANDLOCK_REQUIRED_ABI
        or receipt.get("handled_access_fs") != LANDLOCK_WRITE_ACCESS_MASK
        or receipt.get("output_allowed_access_fs") != LANDLOCK_OUTPUT_ACCESS_MASK
        or receipt.get("no_new_privs") not in (1, True)
        or receipt.get("thread_ids") != [pid]
        or receipt.get("receipt_path")
        != receipt_path.expanduser().absolute().as_posix()
        or receipt.get("source_sha256")
        != _sha256(
            REPO_ROOT / "experiments/consciousness_sae_target_blind_calibration/"
            "landlock_launcher.py"
        )
        or receipt.get("authorization_sha256") != expected_authorization_sha256
        or receipt.get("preflight_receipt_sha256") != expected_preflight_receipt_sha256
    ):
        raise AuditRecoveryError("Landlock enforcement identity differs")
    if require_current_pid and pid != os.getpid():
        raise AuditRecoveryError("Landlock confinement did not survive same-PID exec")
    directory_rules = receipt.get("directory_rules")
    expected_rules = [
        {
            "role": "output_root",
            "path": output_root.expanduser().absolute().as_posix(),
            "allowed_access_fs": LANDLOCK_OUTPUT_ACCESS_MASK,
        },
        {
            "role": "canary_output_root",
            "path": canary_output_root.expanduser().absolute().as_posix(),
            "allowed_access_fs": LANDLOCK_OUTPUT_ACCESS_MASK,
        },
        {
            "role": "proc_self_task_thread_names",
            "path": "/proc/self/task",
            "allowed_access_fs": LANDLOCK_PROC_SELF_TASK_ACCESS_MASK,
        },
    ]
    if directory_rules != expected_rules:
        raise AuditRecoveryError("Landlock directory rules differ")
    expected_device_paths = sorted(
        path.expanduser().absolute().as_posix() for path in device_files
    )
    device_rules = receipt.get("device_rules")
    if (
        not isinstance(device_rules, list)
        or [row.get("path") for row in device_rules if isinstance(row, Mapping)]
        != expected_device_paths
    ):
        raise AuditRecoveryError("Landlock device inventory differs")
    for row in device_rules:
        if (
            not isinstance(row, Mapping)
            or set(row)
            != {
                "path",
                "st_dev",
                "st_ino",
                "st_rdev",
                "major",
                "minor",
                "allowed_access_fs",
            }
            or row.get("allowed_access_fs") != 1 << 1
            or any(
                not isinstance(row.get(name), int) or int(row[name]) < 0
                for name in ("st_dev", "st_ino", "st_rdev", "major", "minor")
            )
        ):
            raise AuditRecoveryError("Landlock device rule differs")
    descriptor = receipt.get("descriptor_audit")
    mappings = receipt.get("mapping_audit")
    canary = receipt.get("canary_checks")
    protected = receipt.get("protected_checks")
    expected_protected_checks = [
        {
            "path": path.expanduser().absolute().as_posix(),
            "operation": "protected_file_open_write_no_write",
            "status": "denied",
            "errno": 13,
        }
        for path in sorted(protected_files, key=lambda item: item.as_posix())
    ]
    expected_protected_operations = [
        {"operation": operation, "status": "denied", "errno": 13}
        for operation in PROTECTED_CANARY_OPERATIONS
    ]
    expected_output_operations = [
        {"operation": operation, "status": "allowed"}
        for operation in OUTPUT_CANARY_ALLOWED_OPERATIONS
    ] + [
        {
            "operation": operation,
            "status": "denied",
            "errno": (
                errno.EXDEV
                if operation == "output_cross_directory_link"
                else errno.EACCES
            ),
        }
        for operation in OUTPUT_CANARY_DENIED_OPERATIONS
    ]
    expected_writable_baseline = [
        {"operation": operation, "status": "allowed"}
        for operation in PROTECTED_CANARY_WRITABLE_BASELINE
    ]
    if (
        not isinstance(descriptor, Mapping)
        or descriptor.get("status")
        != "pass_no_escaping_writable_or_protected_descriptors"
        or descriptor.get("protected_roots")
        != sorted({path.expanduser().absolute().as_posix() for path in protected_roots})
        or not isinstance(mappings, Mapping)
        or mappings.get("status") != "pass_no_shared_file_backed_mappings"
        or mappings.get("shared_file_backed") != []
        or not isinstance(canary, Mapping)
        or canary.get("status") != "pass_protected_unchanged_output_empty"
        or canary.get("protected_unchanged") is not True
        or canary.get("output_empty_before") is not True
        or canary.get("output_empty_after") is not True
        or canary.get("preconfinement_writable_baseline") != expected_writable_baseline
        or canary.get("protected_operations") != expected_protected_operations
        or canary.get("output_operations") != expected_output_operations
        or protected != expected_protected_checks
    ):
        raise AuditRecoveryError("Landlock enforcement checks differ")
    child_argv = receipt.get("child_argv")
    if (
        not isinstance(child_argv, list)
        or not child_argv
        or any(not isinstance(part, str) or not part for part in child_argv)
        or receipt.get("child_argv_sha256") != protocol.canonical_sha256(child_argv)
    ):
        raise AuditRecoveryError("Landlock child command differs")
    return receipt


def _validate_cuda_preflight(
    landlock_path: Path,
    probe_path: Path,
    *,
    expected_landlock_path: Path | None = None,
    expected_probe_path: Path | None = None,
    active_root: Path,
    python_executable: Path,
    roots_manifest_path: Path,
    roots_manifest_sha256: str,
    bootstrap_manifest: Mapping[str, Any],
    output_root: Path,
    canary_protected_root: Path,
    canary_output_root: Path,
    device_files: Sequence[Path],
    closure_scope: str,
    expected_closure_files: Sequence[Mapping[str, Any]],
    qualification_ownership_path: Path | None = None,
    expected_qualification_ownership_path: Path | None = None,
    expected_provider: Mapping[str, Any] | None = None,
    require_live_paths: bool = True,
) -> tuple[dict[str, Any], dict[str, Any]]:
    if closure_scope not in PREFLIGHT_CLOSURE_SCOPES:
        raise AuditRecoveryError("CUDA preflight closure scope differs")
    if (closure_scope == "source_test_qualification") is not (
        qualification_ownership_path is not None
    ):
        raise AuditRecoveryError("CUDA preflight qualification ownership differs")
    if (qualification_ownership_path is None) is not (
        expected_qualification_ownership_path is None
    ):
        raise AuditRecoveryError("CUDA preflight qualification ownership path differs")
    bootstrap_roots, bootstrap_files = _bootstrap_protected_paths(
        {"path": roots_manifest_path.as_posix(), "manifest": bootstrap_manifest}
    )
    landlock = _validate_landlock_receipt(
        _json(landlock_path),
        purpose="preauthorization_probe",
        receipt_path=(
            landlock_path if expected_landlock_path is None else expected_landlock_path
        ),
        output_root=output_root,
        protected_roots=[canary_protected_root, *bootstrap_roots],
        protected_files=[
            canary_protected_root / "seed.txt",
            *bootstrap_files,
            *(
                [
                    expected_qualification_ownership_path
                    if expected_qualification_ownership_path is not None
                    else qualification_ownership_path
                ]
                if qualification_ownership_path is not None
                else []
            ),
        ],
        canary_output_root=canary_output_root,
        device_files=device_files,
        expected_authorization_sha256=None,
        expected_preflight_receipt_sha256=None,
        require_current_pid=False,
    )
    expected_child_argv = _preflight_child_argv(
        python_executable=python_executable.as_posix(),
        active_root=active_root.as_posix(),
        roots_manifest=roots_manifest_path.as_posix(),
        roots_manifest_sha256=roots_manifest_sha256,
        landlock_receipt=(
            landlock_path if expected_landlock_path is None else expected_landlock_path
        ).as_posix(),
        output_root=output_root.as_posix(),
        canary_protected_root=canary_protected_root.as_posix(),
        canary_output_root=canary_output_root.as_posix(),
        device_files=[path.as_posix() for path in device_files],
        output=(
            probe_path if expected_probe_path is None else expected_probe_path
        ).as_posix(),
        closure_scope=closure_scope,
        qualification_ownership=(
            expected_qualification_ownership_path.as_posix()
            if expected_qualification_ownership_path is not None
            else None
        ),
    )
    probe = _json(probe_path)
    _self_hash(probe, "Landlock CUDA preflight")
    cuda = probe.get("cuda")
    provider = probe.get("provider")
    environment = probe.get("environment")
    bootstrap_phase = probe.get("bootstrap")
    if not isinstance(bootstrap_phase, Mapping) or not isinstance(
        bootstrap_phase.get("attestation"), Mapping
    ):
        raise AuditRecoveryError("Landlock CUDA bootstrap attestation is missing")
    bootstrap_attestation = _validate_bootstrap_attestation(
        bootstrap_phase["attestation"],
        mode="preflight-child",
        expected_pid=int(landlock["pid"]),
        active_root=active_root,
        python_executable=python_executable,
        roots_manifest_path=roots_manifest_path,
        roots_manifest_sha256=roots_manifest_sha256,
        manifest=bootstrap_manifest,
        require_live_paths=require_live_paths,
    )
    expected_bootstrap_phase = _bootstrap_phase_record(
        BOOTSTRAP_PREFLIGHT_PHASE, bootstrap_attestation
    )
    expected_bootstrap_commitment = _bootstrap_manifest_commitment(
        manifest_path=roots_manifest_path,
        manifest_file_sha256=roots_manifest_sha256,
        manifest=bootstrap_manifest,
        active_root=active_root,
        python_executable=python_executable,
    )
    if (
        probe.get("schema_version") != 1
        or probe.get("status") != "pass_target_free_landlock_cuda_preflight"
        or probe.get("landlock_receipt_sha256") != landlock["receipt_sha256"]
        or probe.get("pid") != landlock["pid"]
        or landlock.get("child_argv") != expected_child_argv
        or landlock.get("child_argv_sha256")
        != protocol.canonical_sha256(expected_child_argv)
        or probe.get("python_executable") != python_executable.as_posix()
        or probe.get("active_root") != active_root.as_posix()
        or probe.get("closure_scope") != closure_scope
        or probe.get("closure_files") != list(expected_closure_files)
        or probe.get("closure_file_count") != len(expected_closure_files)
        or probe.get("closure_inventory_sha256")
        != protocol.canonical_sha256(list(expected_closure_files))
        or probe.get("recovery_closure_sha256")
        != protocol.canonical_sha256(list(expected_closure_files))
        or probe.get("bootstrap_roots_manifest") != expected_bootstrap_commitment
        or probe.get("qualification_ownership_receipt_sha256")
        != (
            None
            if qualification_ownership_path is None
            else _self_hash(
                _canonical_json_receipt(
                    qualification_ownership_path,
                    "qualification ownership receipt",
                ),
                "qualification ownership receipt",
            )
        )
        or probe.get("absent_environment_variables")
        != list(FORBIDDEN_CONFINED_ENVIRONMENT)
        or probe.get("package_versions") != PINNED_PROBE_PACKAGE_VERSIONS
        or probe.get("model_forward_count") != 0
        or probe.get("torch_module_call_count") != 0
        or probe.get("target_prompt_render_count") != 0
        or probe.get("target_feature_vector_count") != 0
        or probe.get("external_or_prior_outcome_inputs") != []
        or bootstrap_phase != expected_bootstrap_phase
        or not isinstance(provider, Mapping)
        or not isinstance(provider.get("pod_id"), str)
        or not provider.get("pod_id")
        or provider.get("volume_id") != protocol.NETWORK_VOLUME_ID
        or provider.get("data_center_id") != protocol.DATA_CENTER_ID
        or (expected_provider is not None and dict(provider) != dict(expected_provider))
        or not isinstance(environment, Mapping)
        or any(
            environment.get(name) != expected
            for name, expected in CONFINED_FIXED_ENVIRONMENT.items()
        )
        or any(
            not isinstance(environment.get(name), str)
            or not _inside_bound_path(
                output_root,
                Path(str(environment[name])),
                require_live_paths=require_live_paths,
            )
            for name in CONFINED_WRITABLE_PATH_ENVIRONMENT
        )
        or not isinstance(cuda, Mapping)
        or cuda.get("device") != "cuda:0"
        or cuda.get("available") is not True
        or cuda.get("dtype") != "torch.bfloat16"
        or cuda.get("matmul_finite") is not True
        or cuda.get("synchronized") is not True
        or cuda.get("raw_tensor_operations_only") is not True
    ):
        raise AuditRecoveryError("Landlock CUDA preflight differs")
    return landlock, probe


def _validate_qualification_ownership(path: Path) -> dict[str, Any]:
    raw = _canonical_json_receipt(path, "qualification ownership receipt")
    try:
        ownership = runpod_preflight.validate_ownership_receipt(raw)
    except runpod_preflight.PreflightError as exc:
        raise AuditRecoveryError("qualification ownership receipt differs") from exc
    _provider_utc(str(ownership.get("created_at", "")), "qualification pod creation")
    if (
        ownership.get("network_volume_id") != protocol.NETWORK_VOLUME_ID
        or ownership.get("data_center_id") != protocol.DATA_CENTER_ID
        or ownership.get("gpu_type") != protocol.GPU_TYPE
        or ownership.get("gpu_count") != 1
    ):
        raise AuditRecoveryError("qualification ownership resource binding differs")
    return ownership


def run_cuda_preflight(args: argparse.Namespace) -> Path:
    """Run a target-free raw-tensor CUDA smoke test inside Landlock."""

    from importlib import metadata

    output_root = args.output_root.expanduser().absolute()
    output = args.output.expanduser().absolute()
    active_root = args.active_root.expanduser().absolute()
    python_executable = args.python_executable.expanduser().resolve(strict=True)
    manifest_binding = _bootstrap_manifest_binding(
        args.roots_manifest,
        expected_file_sha256=args.roots_manifest_sha256,
        active_root=active_root,
    )
    closure_scope = str(args.closure_scope)
    if closure_scope not in PREFLIGHT_CLOSURE_SCOPES:
        raise AuditRecoveryError("CUDA preflight closure scope differs")
    qualification_ownership: dict[str, Any] | None = None
    qualification_ownership_path: Path | None = None
    if closure_scope == "source_test_qualification":
        if args.qualification_ownership is None:
            raise AuditRecoveryError("qualification ownership receipt is required")
        qualification_ownership_path = (
            args.qualification_ownership.expanduser().absolute()
        )
        qualification_ownership = _validate_qualification_ownership(
            qualification_ownership_path
        )
        closure_files = _source_test_records()
        expected_output_name = TARGET_QUALIFICATION_CUDA_NAME
        provider_record = {
            "pod_id": qualification_ownership["pod_id"],
            "volume_id": qualification_ownership["network_volume_id"],
            "data_center_id": qualification_ownership["data_center_id"],
        }
    else:
        if args.qualification_ownership is not None:
            raise AuditRecoveryError("final preflight has qualification ownership")
        closure_files = _closure_records()
        expected_output_name = "LANDLOCK_CUDA_PREFLIGHT.json"
        provider_record = {
            "pod_id": os.environ.get("RUNPOD_POD_ID"),
            "volume_id": os.environ.get("RUNPOD_VOLUME_ID"),
            "data_center_id": os.environ.get("RUNPOD_DC_ID"),
        }
    bootstrap_roots, bootstrap_files = _bootstrap_protected_paths(manifest_binding)
    if output.parent != output_root or output.name != expected_output_name:
        raise AuditRecoveryError("CUDA preflight output binding differs")
    if (
        Path.cwd().resolve(strict=True) != active_root.resolve(strict=True)
        or Path(sys.executable).resolve(strict=True) != python_executable
    ):
        raise AuditRecoveryError("CUDA preflight executable/cwd binding differs")
    landlock = _validate_landlock_receipt(
        _json(args.landlock_receipt),
        purpose="preauthorization_probe",
        receipt_path=args.landlock_receipt,
        output_root=output_root,
        protected_roots=[args.canary_protected_root, *bootstrap_roots],
        protected_files=[
            args.canary_protected_root / "seed.txt",
            *bootstrap_files,
            *(
                [qualification_ownership_path]
                if qualification_ownership_path is not None
                else []
            ),
        ],
        canary_output_root=args.canary_output_root,
        device_files=args.device_file,
        expected_authorization_sha256=None,
        expected_preflight_receipt_sha256=None,
        require_current_pid=True,
    )
    expected_child_argv = _preflight_child_argv(
        python_executable=python_executable.as_posix(),
        active_root=active_root.as_posix(),
        roots_manifest=args.roots_manifest.expanduser().absolute().as_posix(),
        roots_manifest_sha256=args.roots_manifest_sha256,
        landlock_receipt=args.landlock_receipt.expanduser().absolute().as_posix(),
        output_root=output_root.as_posix(),
        canary_protected_root=args.canary_protected_root.expanduser()
        .absolute()
        .as_posix(),
        canary_output_root=args.canary_output_root.expanduser().absolute().as_posix(),
        device_files=[path.as_posix() for path in args.device_file],
        output=output.as_posix(),
        closure_scope=closure_scope,
        qualification_ownership=(
            qualification_ownership_path.as_posix()
            if qualification_ownership_path is not None
            else None
        ),
    )
    if landlock.get("child_argv") != expected_child_argv:
        raise AuditRecoveryError("CUDA preflight launcher command differs")
    environment = _validate_confinement_environment(output_root)
    observed_versions = {
        name: metadata.version(name) for name in PINNED_PROBE_PACKAGE_VERSIONS
    }
    if observed_versions != PINNED_PROBE_PACKAGE_VERSIONS:
        raise AuditRecoveryError("CUDA preflight package versions differ")

    import numpy as np
    import safetensors
    import torch
    import transformers

    imported_versions = {
        "numpy": np.__version__,
        "safetensors": safetensors.__version__,
        "torch": torch.__version__,
        "transformers": transformers.__version__,
    }
    if any(
        imported_versions[name] != PINNED_PROBE_PACKAGE_VERSIONS[name]
        for name in imported_versions
    ):
        raise AuditRecoveryError("CUDA preflight imported package versions differ")
    if not torch.cuda.is_available() or torch.cuda.device_count() != 1:
        raise AuditRecoveryError("CUDA preflight did not observe exactly one GPU")
    if qualification_ownership is not None and (
        os.environ.get("RUNPOD_POD_ID") != qualification_ownership["pod_id"]
        or os.environ.get("RUNPOD_VOLUME_ID")
        != qualification_ownership["network_volume_id"]
        or os.environ.get("RUNPOD_DC_ID") != qualification_ownership["data_center_id"]
    ):
        raise AuditRecoveryError("qualification ownership/environment differs")

    module_calls = 0
    original_call_impl = torch.nn.Module._call_impl

    def blocked_module_call(*_args: Any, **_kwargs: Any) -> Any:
        nonlocal module_calls
        module_calls += 1
        raise AuditRecoveryError("torch.nn.Module call is forbidden in CUDA preflight")

    torch.nn.Module._call_impl = blocked_module_call
    synchronized = False
    try:
        left = torch.arange(256, dtype=torch.float32).reshape(16, 16)
        right = torch.flip(left, dims=(1,))
        left_cuda = left.to(device="cuda:0", dtype=torch.bfloat16)
        right_cuda = right.to(device="cuda:0", dtype=torch.bfloat16)
        product = left_cuda @ right_cuda
        reduction = product.float().mean()
        finite = bool(torch.isfinite(reduction).item())
        torch.cuda.synchronize(0)
        synchronized = True
        properties = torch.cuda.get_device_properties(0)
        cuda_record = {
            "available": True,
            "device": "cuda:0",
            "device_count": torch.cuda.device_count(),
            "device_name": properties.name,
            "device_capability": list(torch.cuda.get_device_capability(0)),
            "dtype": str(product.dtype),
            "shape": list(product.shape),
            "matmul_finite": finite,
            "synchronized": synchronized,
            "raw_tensor_operations_only": True,
        }
    finally:
        torch.nn.Module._call_impl = original_call_impl
    if module_calls != 0 or not cuda_record["matmul_finite"] or not synchronized:
        raise AuditRecoveryError("CUDA preflight raw arithmetic failed")
    bootstrap_attestation = _current_bootstrap_attestation(
        mode="preflight-child",
        active_root=active_root,
        python_executable=python_executable,
        roots_manifest_path=args.roots_manifest,
        roots_manifest_sha256=args.roots_manifest_sha256,
        manifest=manifest_binding["manifest"],
    )
    bootstrap_phase = _bootstrap_phase_record(
        BOOTSTRAP_PREFLIGHT_PHASE, bootstrap_attestation
    )
    core = {
        "schema_version": 1,
        "status": "pass_target_free_landlock_cuda_preflight",
        "pid": os.getpid(),
        "python_executable": python_executable.as_posix(),
        "active_root": active_root.as_posix(),
        "closure_scope": closure_scope,
        "closure_files": closure_files,
        "closure_file_count": len(closure_files),
        "closure_inventory_sha256": protocol.canonical_sha256(closure_files),
        "recovery_closure_sha256": protocol.canonical_sha256(closure_files),
        "bootstrap_roots_manifest": _bootstrap_manifest_commitment(
            manifest_path=args.roots_manifest.expanduser().absolute(),
            manifest_file_sha256=args.roots_manifest_sha256,
            manifest=manifest_binding["manifest"],
            active_root=active_root,
            python_executable=python_executable,
        ),
        "qualification_ownership_receipt_sha256": (
            qualification_ownership.get("receipt_sha256")
            if qualification_ownership is not None
            else None
        ),
        "landlock_receipt_sha256": landlock["receipt_sha256"],
        "bootstrap": bootstrap_phase,
        "package_versions": observed_versions,
        "imported_package_versions": imported_versions,
        "environment": environment,
        "absent_environment_variables": list(FORBIDDEN_CONFINED_ENVIRONMENT),
        "provider": provider_record,
        "cuda": cuda_record,
        "model_forward_count": 0,
        "torch_module_call_count": module_calls,
        "target_prompt_render_count": 0,
        "target_feature_vector_count": 0,
        "external_or_prior_outcome_inputs": [],
        "completed_at_utc": _utc_text(datetime.now(timezone.utc)),
    }
    receipt = {**core, "receipt_sha256": protocol.canonical_sha256(core)}
    _write_json_exclusive(output, receipt)
    return output


def _utc(value: str, label: str) -> datetime:
    if (
        not isinstance(value, str)
        or re.fullmatch(
            r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z", value
        )
        is None
    ):
        raise AuditRecoveryError(f"{label} is not canonical UTC")
    try:
        parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=timezone.utc
        )
    except ValueError as exc:
        raise AuditRecoveryError(f"{label} is not parseable UTC") from exc
    return parsed.astimezone(timezone.utc)


def _utc_text(value: datetime) -> str:
    return (
        value.astimezone(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _provider_utc(value: str, label: str) -> datetime:
    match = re.fullmatch(
        r"([0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2})"
        r"(?:\.([0-9]{1,9}))?Z",
        value,
    )
    if match is None:
        raise AuditRecoveryError(f"{label} is not canonical UTC")
    try:
        parsed = datetime.strptime(match.group(1), "%Y-%m-%dT%H:%M:%S").replace(
            tzinfo=timezone.utc
        )
    except ValueError as exc:
        raise AuditRecoveryError(f"{label} is not parseable UTC") from exc
    fraction = match.group(2)
    if fraction is not None:
        parsed = parsed.replace(microsecond=int((fraction + "000000")[:6]))
    return parsed


def _write_json_exclusive(path: Path, value: Mapping[str, Any]) -> None:
    lexical = path.expanduser().absolute()
    authorize._require_no_symlink_components(  # noqa: SLF001
        lexical.parent, "exclusive receipt parent"
    )
    if not lexical.parent.is_dir() or lexical.parent.is_symlink():
        raise AuditRecoveryError("exclusive receipt parent is unsafe")
    payload = protocol.canonical_json_bytes(dict(value)) + b"\n"
    descriptor = os.open(lexical, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
    directory_fd = os.open(lexical.parent, os.O_RDONLY)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)


def _file_record(path: Path) -> dict[str, Any]:
    lexical = path.expanduser().absolute()
    authorize._require_no_symlink_components(  # noqa: SLF001
        lexical, "bound recovery file"
    )
    resolved = lexical.resolve(strict=True)
    if not resolved.is_file() or lexical.is_symlink():
        raise AuditRecoveryError(f"bound file is unsafe: {path}")
    return {"bytes": resolved.stat().st_size, "sha256": _sha256(resolved)}


def _bootstrap_manifest_binding(
    path: Path,
    *,
    expected_file_sha256: str,
    active_root: Path,
) -> dict[str, Any]:
    if HEX64.fullmatch(str(expected_file_sha256)) is None:
        raise AuditRecoveryError("bootstrap root-manifest SHA-256 differs")
    try:
        manifest = confined_bootstrap.validate_roots_manifest(
            path,
            expected_file_sha256=expected_file_sha256,
            expected_active_root=active_root,
        )
    except confined_bootstrap.ConfinedBootstrapError as exc:
        raise AuditRecoveryError(f"bootstrap root manifest differs: {exc}") from exc
    lexical = path.expanduser().absolute()
    return {
        "path": lexical.as_posix(),
        "physical_file": _file_record(lexical),
        "manifest": manifest,
    }


def _bootstrap_protected_paths(
    binding: Mapping[str, Any],
) -> tuple[list[Path], list[Path]]:
    manifest = binding.get("manifest")
    roots = manifest.get("roots") if isinstance(manifest, Mapping) else None
    if not isinstance(roots, list) or not roots:
        raise AuditRecoveryError("bootstrap protected-root inventory differs")
    root_paths = [
        Path(str(row.get("path"))) for row in roots if isinstance(row, Mapping)
    ]
    manifest_path = Path(str(binding.get("path")))
    if len(root_paths) != len(roots) or not manifest_path.is_absolute():
        raise AuditRecoveryError("bootstrap protected-root inventory differs")
    active_root = root_paths[0]
    protected_roots = sorted(
        set(root_paths) | {manifest_path.parent}, key=lambda path: path.as_posix()
    )
    protected_files = sorted(
        {
            manifest_path,
            active_root / confined_bootstrap.BOOTSTRAP_RELATIVE_PATH,
        },
        key=lambda path: path.as_posix(),
    )
    return protected_roots, protected_files


def _bootstrap_manifest_commitment(
    *,
    manifest_path: Path,
    manifest_file_sha256: str,
    manifest: Mapping[str, Any],
    active_root: Path,
    python_executable: Path,
) -> dict[str, Any]:
    roots = manifest.get("roots")
    if not isinstance(roots, list) or not roots:
        raise AuditRecoveryError("bootstrap root commitment differs")
    root_paths = [row.get("path") for row in roots if isinstance(row, Mapping)]
    if (
        len(root_paths) != len(roots)
        or any(not isinstance(path, str) for path in root_paths)
        or root_paths != sorted(set(root_paths))
    ):
        raise AuditRecoveryError("bootstrap root commitment differs")
    return {
        "path": manifest_path.as_posix(),
        "file_sha256": manifest_file_sha256,
        "receipt_sha256": manifest.get("receipt_sha256"),
        "roots_inventory_sha256": manifest.get("roots_inventory_sha256"),
        "bootstrap_sha256": manifest.get("bootstrap_sha256"),
        "active_root": active_root.as_posix(),
        "python_executable": python_executable.as_posix(),
        "root_paths": root_paths,
        "sys_path": manifest.get("sys_path"),
    }


def _validate_bootstrap_attestation(
    value: Mapping[str, Any],
    *,
    mode: str,
    expected_pid: int,
    active_root: Path,
    python_executable: Path,
    roots_manifest_path: Path,
    roots_manifest_sha256: str,
    manifest: Mapping[str, Any],
    require_live_paths: bool = True,
) -> dict[str, Any]:
    attestation = dict(value)
    fields = {
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
    }
    guards = attestation.get("guards")
    if (
        set(attestation) != fields
        or _self_hash(attestation, "confined bootstrap attestation")
        != attestation.get("receipt_sha256")
        or attestation.get("schema_version") != confined_bootstrap.SCHEMA_VERSION
        or attestation.get("status") != "pass_hash_bound_confined_bootstrap"
        or attestation.get("mode") != mode
        or attestation.get("pid") != expected_pid
        or attestation.get("active_root")
        != active_root.expanduser().absolute().as_posix()
        or attestation.get("python_executable")
        != (
            python_executable.expanduser().resolve(strict=True).as_posix()
            if require_live_paths
            else _canonical_absolute_posix_path(
                python_executable.as_posix(), "bootstrap Python executable"
            )
        )
        or attestation.get("roots_manifest_path")
        != roots_manifest_path.expanduser().absolute().as_posix()
        or attestation.get("roots_manifest_file_sha256") != roots_manifest_sha256
        or attestation.get("roots_manifest_receipt_sha256")
        != manifest.get("receipt_sha256")
        or attestation.get("roots_inventory_sha256")
        != manifest.get("roots_inventory_sha256")
        or attestation.get("sys_path") != manifest.get("sys_path")
        or attestation.get("bootstrap_sha256") != manifest.get("bootstrap_sha256")
        or attestation.get("site_imported") is not False
        or attestation.get("startup_project_or_ml_module_count") != 0
        or not isinstance(guards, Mapping)
        or set(guards)
        != {
            "status",
            "forbidden_module_import_attempts",
            "forbidden_startup_import_attempts",
            "torch_module_calls",
            "transformers_model_load_calls",
            "patched_modules",
        }
        or guards.get("status") != "process_lifetime_guards_installed"
        or guards.get("forbidden_module_import_attempts") != 0
        or guards.get("forbidden_startup_import_attempts") != 0
        or guards.get("torch_module_calls") != 0
        or guards.get("transformers_model_load_calls") != 0
        or guards.get("patched_modules") != list(BOOTSTRAP_GUARDED_MODULES)
    ):
        raise AuditRecoveryError("confined bootstrap attestation differs")
    return attestation


def _current_bootstrap_attestation(
    *,
    mode: str,
    active_root: Path,
    python_executable: Path,
    roots_manifest_path: Path,
    roots_manifest_sha256: str,
    manifest: Mapping[str, Any],
) -> dict[str, Any]:
    state = sys.modules.get(confined_bootstrap.STATE_MODULE)
    runtime_attestation = getattr(state, "runtime_attestation", None)
    if not callable(runtime_attestation):
        raise AuditRecoveryError("confined bootstrap runtime state is absent")
    observed = runtime_attestation()
    if not isinstance(observed, Mapping):
        raise AuditRecoveryError("confined bootstrap runtime state differs")
    return _validate_bootstrap_attestation(
        observed,
        mode=mode,
        expected_pid=os.getpid(),
        active_root=active_root,
        python_executable=python_executable,
        roots_manifest_path=roots_manifest_path,
        roots_manifest_sha256=roots_manifest_sha256,
        manifest=manifest,
    )


def _bootstrap_phase_record(
    phase: str, attestation: Mapping[str, Any]
) -> dict[str, Any]:
    if phase not in {
        BOOTSTRAP_PREFLIGHT_PHASE,
        BOOTSTRAP_EXECUTE_ENTRY_PHASE,
        BOOTSTRAP_PREPUBLICATION_PHASE,
    }:
        raise AuditRecoveryError("confined bootstrap phase differs")
    core = {
        "status": "pass_hash_bound_bootstrap_phase",
        "phase": phase,
        "attestation": dict(attestation),
        "attestation_receipt_sha256": attestation.get("receipt_sha256"),
    }
    return {**core, "receipt_sha256": protocol.canonical_sha256(core)}


_CONFINED_EVIDENCE_ARGUMENTS = (
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
_CONFINED_PATH_ARGUMENTS = (
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


def _preflight_child_argv(
    *,
    python_executable: str,
    active_root: str,
    roots_manifest: str,
    roots_manifest_sha256: str,
    landlock_receipt: str,
    output_root: str,
    canary_protected_root: str,
    canary_output_root: str,
    device_files: Sequence[str],
    output: str,
    closure_scope: str = "final_recovery",
    qualification_ownership: str | None = None,
) -> list[str]:
    if closure_scope not in PREFLIGHT_CLOSURE_SCOPES:
        raise AuditRecoveryError("CUDA preflight closure scope differs")
    if (closure_scope == "source_test_qualification") is not bool(
        qualification_ownership
    ):
        raise AuditRecoveryError("CUDA preflight qualification ownership differs")
    argv = [
        python_executable,
        "-B",
        "-E",
        "-s",
        "-S",
        (f"{active_root}/" + confined_bootstrap.BOOTSTRAP_RELATIVE_PATH),
        "--mode",
        "preflight-child",
        "--active-root",
        active_root,
        "--roots-manifest",
        roots_manifest,
        "--roots-manifest-sha256",
        roots_manifest_sha256,
        "--",
        "--python-executable",
        python_executable,
        "--active-root",
        active_root,
        "--roots-manifest",
        roots_manifest,
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
        argv.extend(("--qualification-ownership", qualification_ownership))
    for path in device_files:
        argv.extend(("--device-file", path))
    argv.extend(("--output", output))
    return argv


def _confined_child_argv(
    *,
    python_executable: str,
    active_root: str,
    attempt_id: str,
    paths: Mapping[str, str],
    roots_manifest_sha256: str,
    device_files: Sequence[str],
) -> list[str]:
    argv = [
        python_executable,
        "-B",
        "-E",
        "-s",
        "-S",
        (f"{active_root}/" + confined_bootstrap.BOOTSTRAP_RELATIVE_PATH),
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
    for name in _CONFINED_EVIDENCE_ARGUMENTS:
        argv.extend((f"--{name.replace('_', '-')}", paths[name]))
    argv.extend(("--attempt-id", attempt_id))
    argv.extend(("--active-root", active_root))
    argv.extend(("--python-executable", python_executable))
    for name in _CONFINED_PATH_ARGUMENTS:
        argv.extend((f"--{name.replace('_', '-')}", paths[name]))
    argv.extend(("--roots-manifest-sha256", roots_manifest_sha256))
    for path in device_files:
        argv.extend(("--device-file", path))
    argv.extend(("--artifact-device", "cuda:0"))
    argv.extend(("--recovery-authorization", paths["recovery_authorization"]))
    return argv


def _execution_binding(
    args: argparse.Namespace, *, git_head: str, validate_execute_paths: bool
) -> dict[str, Any]:
    attempt_id = str(args.attempt_id)
    if ATTEMPT_ID_RE.fullmatch(attempt_id) is None or not attempt_id.startswith(
        f"calv2-r3-audit-recovery-{git_head[:7]}-"
    ):
        raise AuditRecoveryError("recovery attempt identity differs")
    attempt_root = PurePosixPath(RECOVERY_ATTEMPT_PARENT) / attempt_id
    original = attempt_root / "evidence/original"
    superseded = attempt_root / "evidence/superseded_recovery_host"
    fresh = attempt_root / "evidence/fresh"
    output = attempt_root / "output"
    preflight = attempt_root / "preflight"
    canary = attempt_root / "landlock_canary"
    active_root = (
        PurePosixPath("/root/consciousness_sae_audit_recovery") / attempt_id / "active"
    )
    expected = {
        "plan_dir": (
            attempt_root / "provenance_repo" / protocol.CANONICAL_PLAN_RELATIVE_PATH
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
            attempt_root / "evidence/tests/LOCAL_TEST_RECEIPT.json"
        ).as_posix(),
        "target_host_test_receipt": (
            attempt_root / "evidence/tests/TARGET_HOST_TEST_RECEIPT.json"
        ).as_posix(),
        "target_qualification_ownership": (
            attempt_root / f"evidence/tests/{TARGET_QUALIFICATION_OWNERSHIP_NAME}"
        ).as_posix(),
        "target_qualification_landlock": (
            attempt_root / f"evidence/tests/{TARGET_QUALIFICATION_LANDLOCK_NAME}"
        ).as_posix(),
        "target_qualification_cuda_preflight": (
            attempt_root / f"evidence/tests/{TARGET_QUALIFICATION_CUDA_NAME}"
        ).as_posix(),
        "preflight_output_root": (preflight / "output").as_posix(),
        "preflight_canary_protected_root": (preflight / "canary/protected").as_posix(),
        "preflight_canary_output_root": (preflight / "canary/output").as_posix(),
        "recovery_authorization": (
            attempt_root / "RECOVERY_AUTHORIZATION.json"
        ).as_posix(),
        "provenance_root": (attempt_root / "provenance_repo").as_posix(),
        "roots_manifest": (attempt_root / BOOTSTRAP_MANIFEST_RELATIVE).as_posix(),
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
    for name in ("preflight_canary_output_root", "canary_output_root"):
        _validate_bound_canary_socket_path(PurePosixPath(expected[name]), name)
    always_observed = {
        name: getattr(args, name).expanduser().absolute().as_posix()
        for name in (
            "provenance_root",
            "roots_manifest",
            "output_root",
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
    }
    observed = dict(always_observed)
    if validate_execute_paths:
        observed.update(
            {
                name: getattr(args, name).expanduser().absolute().as_posix()
                for name in expected
                if name not in observed
            }
        )
    compared = (
        expected
        if validate_execute_paths
        else {name: expected[name] for name in always_observed}
    )
    if observed != compared or args.artifact_device != "cuda:0":
        raise AuditRecoveryError("recovery execution path binding differs")
    device_files = sorted({Path(path).as_posix() for path in args.device_file})
    if (
        not device_files
        or len(device_files) != len(args.device_file)
        or any(NVIDIA_DEVICE_PATH_RE.fullmatch(path) is None for path in device_files)
    ):
        raise AuditRecoveryError("recovery device-file binding differs")
    try:
        python_executable = (
            args.python_executable.expanduser().resolve(strict=True).as_posix()
        )
    except OSError as exc:
        raise AuditRecoveryError("recovery Python executable is missing") from exc
    if (
        not python_executable.startswith("/")
        or args.active_root.expanduser().absolute().as_posix() != active_root.as_posix()
        or HEX64.fullmatch(str(args.roots_manifest_sha256)) is None
    ):
        raise AuditRecoveryError("recovery executable binding differs")
    child_argv = _confined_child_argv(
        python_executable=python_executable,
        active_root=active_root.as_posix(),
        attempt_id=attempt_id,
        paths=expected,
        roots_manifest_sha256=str(args.roots_manifest_sha256),
        device_files=device_files,
    )
    core = {
        "attempt_id": attempt_id,
        "attempt_root": attempt_root.as_posix(),
        "paths": expected,
        "artifact_device": "cuda:0",
        "device_files": device_files,
        "launcher_mode": "audit_recovery",
        "active_root": active_root.as_posix(),
        "python_executable": python_executable,
        "roots_manifest_sha256": str(args.roots_manifest_sha256),
        "confined_child_argv": child_argv,
        "confined_child_argv_sha256": protocol.canonical_sha256(child_argv),
    }
    return {**core, "command_sha256": protocol.canonical_sha256(core)}


def _validate_issue_output(output: Path, execution: Mapping[str, Any]) -> Path:
    paths = execution.get("paths")
    if not isinstance(paths, Mapping):
        raise AuditRecoveryError("recovery authorization output binding differs")
    expected = Path(str(paths.get("recovery_authorization")))
    observed = output.expanduser().absolute()
    if observed != expected:
        raise AuditRecoveryError("recovery authorization output binding differs")
    return observed


def _closure_records() -> list[dict[str, Any]]:
    records = []
    for relative in RECOVERY_BOUND_PATHS:
        record = _file_record(REPO_ROOT / relative)
        records.append({"path": relative, **record})
    return records


def _source_test_records(
    closure: Sequence[Mapping[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    if closure is None:
        return [
            {"path": relative, **_file_record(REPO_ROOT / relative)}
            for relative in SOURCE_TEST_BOUND_PATHS
        ]
    by_path = {
        str(row.get("path")): dict(row)
        for row in closure
        if isinstance(row, Mapping)
        and str(row.get("path")) in set(SOURCE_TEST_BOUND_PATHS)
    }
    if set(by_path) != set(SOURCE_TEST_BOUND_PATHS):
        raise AuditRecoveryError("source/test closure inventory differs")
    return [by_path[path] for path in SOURCE_TEST_BOUND_PATHS]


def _git_command(*parts: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        ["git", *parts],
        cwd=REPO_ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    if check and completed.returncode != 0:
        raise AuditRecoveryError(
            "git test-receipt binding failed: " + completed.stderr.strip()
        )
    return completed


def _git_head() -> str:
    value = _git_command("rev-parse", "HEAD").stdout.strip()
    if HEX40.fullmatch(value) is None:
        raise AuditRecoveryError("test-receipt Git HEAD differs")
    return value


def _require_code_freeze_ancestor(code_freeze_commit: str, observed_head: str) -> None:
    if (
        HEX40.fullmatch(code_freeze_commit) is None
        or HEX40.fullmatch(observed_head) is None
        or _git_command(
            "merge-base",
            "--is-ancestor",
            code_freeze_commit,
            observed_head,
            check=False,
        ).returncode
        != 0
    ):
        raise AuditRecoveryError("code-freeze commit is not an execution ancestor")
    if (
        _git_command(
            "diff",
            "--quiet",
            code_freeze_commit,
            "--",
            *SOURCE_TEST_BOUND_PATHS,
            check=False,
        ).returncode
        != 0
    ):
        raise AuditRecoveryError("source/test bytes changed after code freeze")


def _installed_distributions() -> list[dict[str, str]]:
    from importlib import metadata

    rows: dict[str, str] = {}
    for distribution in metadata.distributions():
        raw_name = distribution.metadata.get("Name")
        if not isinstance(raw_name, str) or not raw_name.strip():
            continue
        name = raw_name.strip().lower().replace("_", "-")
        version = str(distribution.version)
        if name in rows and rows[name] != version:
            raise AuditRecoveryError("installed distribution name is duplicated")
        rows[name] = version
    return [{"name": name, "version": rows[name]} for name in sorted(rows)]


class _PytestReceiptCollector:
    def __init__(self) -> None:
        self.collected_ids: list[str] = []
        self.outcomes: dict[str, str] = {}

    def pytest_collection_finish(self, session: Any) -> None:
        self.collected_ids = sorted(str(item.nodeid) for item in session.items)

    def pytest_runtest_logreport(self, report: Any) -> None:
        node_id = str(report.nodeid)
        prior = self.outcomes.get(node_id)
        if bool(report.failed):
            self.outcomes[node_id] = "failed"
        elif bool(report.skipped) and prior != "failed":
            self.outcomes[node_id] = "skipped"
        elif str(report.when) == "call" and bool(report.passed) and prior is None:
            self.outcomes[node_id] = "passed"

    def result_ids(self) -> dict[str, list[str]]:
        collected = sorted(set(self.collected_ids))
        passed = sorted(
            node_id for node_id, outcome in self.outcomes.items() if outcome == "passed"
        )
        failed = sorted(
            node_id for node_id, outcome in self.outcomes.items() if outcome == "failed"
        )
        skipped = sorted(
            node_id
            for node_id, outcome in self.outcomes.items()
            if outcome == "skipped"
        )
        observed = set(passed) | set(failed) | set(skipped)
        return {
            "collected_ids": collected,
            "passed_ids": passed,
            "failed_ids": failed,
            "skipped_ids": skipped,
            "not_run_ids": sorted(set(collected) - observed),
        }


def _target_host_test_environment(ownership: Mapping[str, Any]) -> dict[str, Any]:
    from experiments.consciousness_sae_target_blind_calibration import (
        landlock_launcher,
    )
    import torch

    if not torch.cuda.is_available() or torch.cuda.device_count() != 1:
        raise AuditRecoveryError("target test receipt requires exactly one CUDA GPU")
    if (
        os.environ.get("RUNPOD_POD_ID") != ownership.get("pod_id")
        or os.environ.get("RUNPOD_VOLUME_ID") != ownership.get("network_volume_id")
        or os.environ.get("RUNPOD_DC_ID") != ownership.get("data_center_id")
        or ownership.get("gpu_type") != protocol.GPU_TYPE
        or ownership.get("gpu_count") != 1
    ):
        raise AuditRecoveryError("target test ownership/environment differs")
    properties = torch.cuda.get_device_properties(0)
    return {
        "pod_id": ownership["pod_id"],
        "volume_id": ownership["network_volume_id"],
        "data_center_id": ownership["data_center_id"],
        "kernel_release": platform.release(),
        "landlock_abi": landlock_launcher.landlock_abi(),
        "gpu": {
            "device_count": torch.cuda.device_count(),
            "device_name": properties.name,
            "device_capability": list(torch.cuda.get_device_capability(0)),
            "total_memory_bytes": int(properties.total_memory),
        },
    }


def _single_argv_option(argv: Sequence[str], name: str) -> str:
    indices = [index for index, value in enumerate(argv) if value == name]
    if len(indices) != 1 or indices[0] + 1 >= len(argv):
        raise AuditRecoveryError(f"qualification child option differs: {name}")
    value = argv[indices[0] + 1]
    if not isinstance(value, str) or not value or value.startswith("--"):
        raise AuditRecoveryError(f"qualification child option differs: {name}")
    return value


def _qualification_probe_binding(
    ownership_path: Path,
    landlock_path: Path,
    cuda_path: Path,
    *,
    expected_source_test_files: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    ownership = _validate_qualification_ownership(ownership_path)
    landlock = _canonical_json_receipt(landlock_path, "qualification Landlock receipt")
    cuda_probe = _canonical_json_receipt(
        cuda_path, "qualification CUDA preflight receipt"
    )
    child_argv = landlock.get("child_argv")
    if not isinstance(child_argv, list) or "--" not in child_argv:
        raise AuditRecoveryError("qualification Landlock child command differs")
    child = child_argv[child_argv.index("--") + 1 :]
    device_files = [
        child[index + 1]
        for index, value in enumerate(child[:-1])
        if value == "--device-file"
    ]
    if (
        not device_files
        or device_files != sorted(set(device_files))
        or any(NVIDIA_DEVICE_PATH_RE.fullmatch(path) is None for path in device_files)
    ):
        raise AuditRecoveryError("qualification device inventory differs")
    active_root = Path(
        _canonical_absolute_posix_path(
            _single_argv_option(child, "--active-root"),
            "qualification active root",
        )
    )
    python_executable = Path(
        _canonical_absolute_posix_path(
            _single_argv_option(child, "--python-executable"),
            "qualification Python executable",
        )
    )
    roots_manifest_path = Path(
        _canonical_absolute_posix_path(
            _single_argv_option(child, "--roots-manifest"),
            "qualification roots manifest",
        )
    )
    embedded_landlock_path = Path(
        _canonical_absolute_posix_path(
            _single_argv_option(child, "--landlock-receipt"),
            "qualification Landlock receipt path",
        )
    )
    output_root = Path(
        _canonical_absolute_posix_path(
            _single_argv_option(child, "--output-root"),
            "qualification output root",
        )
    )
    canary_protected_root = Path(
        _canonical_absolute_posix_path(
            _single_argv_option(child, "--canary-protected-root"),
            "qualification protected canary root",
        )
    )
    canary_output_root = Path(
        _canonical_absolute_posix_path(
            _single_argv_option(child, "--canary-output-root"),
            "qualification output canary root",
        )
    )
    embedded_probe_path = Path(
        _canonical_absolute_posix_path(
            _single_argv_option(child, "--output"),
            "qualification CUDA receipt path",
        )
    )
    embedded_ownership_path = Path(
        _canonical_absolute_posix_path(
            _single_argv_option(child, "--qualification-ownership"),
            "qualification ownership receipt path",
        )
    )
    if _single_argv_option(child, "--closure-scope") != "source_test_qualification":
        raise AuditRecoveryError("qualification closure scope differs")
    bootstrap_commitment = cuda_probe.get("bootstrap_roots_manifest")
    bootstrap_phase = cuda_probe.get("bootstrap")
    attestation = (
        bootstrap_phase.get("attestation")
        if isinstance(bootstrap_phase, Mapping)
        else None
    )
    if (
        not isinstance(bootstrap_commitment, Mapping)
        or set(bootstrap_commitment)
        != {
            "path",
            "file_sha256",
            "receipt_sha256",
            "roots_inventory_sha256",
            "bootstrap_sha256",
            "active_root",
            "python_executable",
            "root_paths",
            "sys_path",
        }
        or not isinstance(attestation, Mapping)
    ):
        raise AuditRecoveryError("qualification bootstrap evidence differs")
    root_paths = bootstrap_commitment.get("root_paths")
    if (
        not isinstance(root_paths, list)
        or root_paths != sorted(set(root_paths))
        or any(not isinstance(path, str) for path in root_paths)
        or bootstrap_commitment.get("path") != roots_manifest_path.as_posix()
        or bootstrap_commitment.get("active_root") != active_root.as_posix()
        or bootstrap_commitment.get("python_executable") != python_executable.as_posix()
        or bootstrap_commitment.get("file_sha256")
        != attestation.get("roots_manifest_file_sha256")
        or bootstrap_commitment.get("receipt_sha256")
        != attestation.get("roots_manifest_receipt_sha256")
        or bootstrap_commitment.get("roots_inventory_sha256")
        != attestation.get("roots_inventory_sha256")
        or bootstrap_commitment.get("bootstrap_sha256")
        != attestation.get("bootstrap_sha256")
        or bootstrap_commitment.get("sys_path") != attestation.get("sys_path")
    ):
        raise AuditRecoveryError("qualification bootstrap commitment differs")
    bootstrap_manifest = {
        "receipt_sha256": bootstrap_commitment["receipt_sha256"],
        "roots_inventory_sha256": bootstrap_commitment["roots_inventory_sha256"],
        "bootstrap_sha256": bootstrap_commitment["bootstrap_sha256"],
        "sys_path": bootstrap_commitment["sys_path"],
        "roots": [{"path": path} for path in root_paths],
    }
    expected_provider = {
        "pod_id": ownership["pod_id"],
        "volume_id": ownership["network_volume_id"],
        "data_center_id": ownership["data_center_id"],
    }
    landlock, cuda_probe = _validate_cuda_preflight(
        landlock_path,
        cuda_path,
        expected_landlock_path=embedded_landlock_path,
        expected_probe_path=embedded_probe_path,
        active_root=active_root,
        python_executable=python_executable,
        roots_manifest_path=roots_manifest_path,
        roots_manifest_sha256=str(attestation.get("roots_manifest_file_sha256", "")),
        bootstrap_manifest=bootstrap_manifest,
        output_root=output_root,
        canary_protected_root=canary_protected_root,
        canary_output_root=canary_output_root,
        device_files=[Path(path) for path in device_files],
        closure_scope="source_test_qualification",
        expected_closure_files=expected_source_test_files,
        qualification_ownership_path=ownership_path,
        expected_qualification_ownership_path=embedded_ownership_path,
        expected_provider=expected_provider,
        require_live_paths=False,
    )
    host_created_at = _provider_utc(
        str(ownership["created_at"]), "qualification host creation"
    )
    completed_at = _utc(
        str(cuda_probe.get("completed_at_utc", "")),
        "qualification CUDA preflight completion",
    )
    provider = cuda_probe["provider"]
    cuda = cuda_probe["cuda"]
    if completed_at < host_created_at:
        raise AuditRecoveryError("qualification CUDA predated ownership")
    return {
        "ownership_file": _file_record(ownership_path),
        "ownership_receipt_sha256": ownership["receipt_sha256"],
        "ownership_created_at_utc": ownership["created_at"],
        "landlock_file": _file_record(landlock_path),
        "landlock_receipt_sha256": landlock["receipt_sha256"],
        "landlock_status": landlock["status"],
        "landlock_observed_abi": landlock["observed_abi"],
        "cuda_preflight_file": _file_record(cuda_path),
        "cuda_preflight_receipt_sha256": cuda_probe["receipt_sha256"],
        "cuda_preflight_status": cuda_probe["status"],
        "cuda_preflight_closure_scope": cuda_probe["closure_scope"],
        "cuda_preflight_closure_inventory_sha256": cuda_probe[
            "closure_inventory_sha256"
        ],
        "cuda_preflight_completed_at_utc": _utc_text(completed_at),
        "cuda_preflight_completed_host_age_seconds": int(
            (completed_at - host_created_at).total_seconds()
        ),
        "bootstrap_roots_manifest_receipt_sha256": bootstrap_commitment[
            "receipt_sha256"
        ],
        "python_executable": python_executable.as_posix(),
        "active_root": active_root.as_posix(),
        "device_files": device_files,
        "child_argv_sha256": landlock["child_argv_sha256"],
        "provider": dict(provider),
        "cuda": {
            "device": cuda["device"],
            "device_count": cuda["device_count"],
            "device_name": cuda["device_name"],
            "device_capability": cuda["device_capability"],
            "matmul_finite": cuda["matmul_finite"],
            "synchronized": cuda["synchronized"],
            "raw_tensor_operations_only": cuda["raw_tensor_operations_only"],
        },
    }


def _target_qualification_paths(test_receipt_path: Path) -> tuple[Path, Path, Path]:
    return (
        test_receipt_path.parent / TARGET_QUALIFICATION_OWNERSHIP_NAME,
        test_receipt_path.parent / TARGET_QUALIFICATION_LANDLOCK_NAME,
        test_receipt_path.parent / TARGET_QUALIFICATION_CUDA_NAME,
    )


def run_test_receipt(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    """Run the exact focused suite and exclusively publish its canonical receipt."""

    code_freeze = str(args.code_freeze_commit)
    observed_head = _git_head()
    _require_code_freeze_ancestor(code_freeze, observed_head)
    if Path.cwd().resolve(strict=True) != REPO_ROOT.resolve(strict=True):
        raise AuditRecoveryError("test receipt must run from the repository root")
    output = args.output.expanduser().absolute()
    if _inside(REPO_ROOT.resolve(strict=True), output):
        raise AuditRecoveryError("test receipt output must be outside the repository")
    before = _source_test_records()
    expected_output_name = (
        TARGET_HOST_TEST_RECEIPT_NAME
        if args.kind == "target_host"
        else LOCAL_TEST_RECEIPT_NAME
    )
    if output.name != expected_output_name:
        raise AuditRecoveryError("test receipt output name differs")
    host_created_at: datetime | None = None
    qualification_probe: dict[str, Any] | None = None
    target_host: dict[str, Any] | None = None
    if args.kind == "target_host":
        if (
            args.host_created_at_utc is None
            or args.qualification_ownership is None
            or args.qualification_landlock is None
            or args.qualification_cuda_preflight is None
        ):
            raise AuditRecoveryError("target qualification evidence is required")
        expected_ownership, expected_landlock, expected_cuda = (
            _target_qualification_paths(output)
        )
        if (
            args.qualification_ownership.expanduser().absolute() != expected_ownership
            or args.qualification_landlock.expanduser().absolute() != expected_landlock
            or args.qualification_cuda_preflight.expanduser().absolute()
            != expected_cuda
        ):
            raise AuditRecoveryError("target qualification evidence path differs")
        ownership = _validate_qualification_ownership(expected_ownership)
        if args.host_created_at_utc != ownership["created_at"]:
            raise AuditRecoveryError(
                "qualification host creation differs from ownership"
            )
        host_created_at = _provider_utc(
            str(ownership["created_at"]), "qualification host creation"
        )
        qualification_probe = _qualification_probe_binding(
            expected_ownership,
            expected_landlock,
            expected_cuda,
            expected_source_test_files=before,
        )
        target_host = _target_host_test_environment(ownership)
        if qualification_probe["provider"] != {
            "pod_id": target_host["pod_id"],
            "volume_id": target_host["volume_id"],
            "data_center_id": target_host["data_center_id"],
        }:
            raise AuditRecoveryError("target qualification provider identity differs")
    elif any(
        value is not None
        for value in (
            args.host_created_at_utc,
            args.qualification_ownership,
            args.qualification_landlock,
            args.qualification_cuda_preflight,
        )
    ):
        raise AuditRecoveryError("local test receipt has target-only arguments")
    dependencies = _installed_distributions()
    command_argv = [str(value) for value in getattr(sys, "orig_argv", sys.argv)]
    started = datetime.now(timezone.utc).replace(microsecond=0)
    collector = _PytestReceiptCollector()
    try:
        import pytest
    except ImportError as exc:
        raise AuditRecoveryError("pytest is required to create a test receipt") from exc
    pytest_exit = int(pytest.main(list(FOCUSED_PYTEST_ARGV), plugins=[collector]))
    completed = datetime.now(timezone.utc).replace(microsecond=0)
    after = _source_test_records()
    if before != after:
        raise AuditRecoveryError("source/test bytes changed during receipt execution")
    ids = collector.result_ids()
    designated_passed = set(TARGET_DESIGNATED_TEST_IDS) <= set(ids["passed_ids"])
    passed = (
        pytest_exit == 0
        and not ids["failed_ids"]
        and not ids["not_run_ids"]
        and (args.kind != "target_host" or designated_passed)
    )
    if target_host is not None and host_created_at is not None:
        if started < host_created_at:
            raise AuditRecoveryError("target test predates qualification host")
        target_host = {
            **target_host,
            "created_at_utc": str(ownership["created_at"]),
            "test_started_host_age_seconds": (
                started - host_created_at
            ).total_seconds(),
            "test_completed_host_age_seconds": (
                completed - host_created_at
            ).total_seconds(),
        }
    core: dict[str, Any] = {
        "schema_version": 1,
        "receipt_type": TEST_RECEIPT_TYPE,
        "kind": args.kind,
        "status": TEST_RECEIPT_STATUS if passed else "failed_not_authorizable",
        "code_freeze_commit": code_freeze,
        "observed_git_head_commit": observed_head,
        "source_test_files": before,
        "source_test_file_count": len(before),
        "source_test_inventory_sha256": protocol.canonical_sha256(before),
        "command_argv": command_argv,
        "command": shlex.join(command_argv),
        "command_argv_sha256": protocol.canonical_sha256(command_argv),
        "receipt_path": output.as_posix(),
        "pytest_argv": list(FOCUSED_PYTEST_ARGV),
        "interpreter": {
            "executable": Path(sys.executable).resolve(strict=True).as_posix(),
            "implementation": platform.python_implementation(),
            "version": platform.python_version(),
            "cache_tag": str(sys.implementation.cache_tag),
        },
        "platform": {
            "system": platform.system(),
            "release": platform.release(),
            "version": platform.version(),
            "machine": platform.machine(),
        },
        "dependencies": dependencies,
        "dependency_inventory_sha256": protocol.canonical_sha256(dependencies),
        **ids,
        "collected_count": len(ids["collected_ids"]),
        "passed_count": len(ids["passed_ids"]),
        "failed_count": len(ids["failed_ids"]),
        "skipped_count": len(ids["skipped_ids"]),
        "not_run_count": len(ids["not_run_ids"]),
        "designated_target_ids": list(TARGET_DESIGNATED_TEST_IDS),
        "started_at_utc": _utc_text(started),
        "completed_at_utc": _utc_text(completed),
        "exit_code": pytest_exit,
        "target_host": target_host,
        "qualification_probe": qualification_probe,
    }
    receipt = {**core, "receipt_sha256": protocol.canonical_sha256(core)}
    _write_json_exclusive(output, receipt)
    return receipt, 0 if passed else (pytest_exit or 2)


def _validate_test_receipt(
    value: Mapping[str, Any],
    *,
    kind: str,
    expected_source_test_files: Sequence[Mapping[str, Any]],
    qualification_ownership_path: Path | None = None,
    qualification_landlock_path: Path | None = None,
    qualification_cuda_path: Path | None = None,
    authorized_at: datetime | None = None,
) -> dict[str, Any]:
    receipt = dict(value)
    fields = {
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
    }
    command_argv = receipt.get("command_argv")
    interpreter = receipt.get("interpreter")
    platform_record = receipt.get("platform")
    dependencies = receipt.get("dependencies")
    id_names = (
        "collected_ids",
        "passed_ids",
        "failed_ids",
        "skipped_ids",
        "not_run_ids",
    )
    ids = {name: receipt.get(name) for name in id_names}
    command_name_index = (
        command_argv.index("test-receipt")
        if isinstance(command_argv, list) and "test-receipt" in command_argv
        else -1
    )
    command_tail = (
        command_argv[command_name_index:]
        if isinstance(command_argv, list) and command_name_index >= 0
        else []
    )
    receipt_path = receipt.get("receipt_path")
    expected_command_tail: list[Any] = [
        "test-receipt",
        "--kind",
        kind,
        "--code-freeze-commit",
        receipt.get("code_freeze_commit"),
    ]
    if kind == "target_host" and isinstance(receipt.get("target_host"), Mapping):
        original_parent = PurePosixPath(str(receipt_path)).parent
        expected_command_tail.extend(
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
    expected_command_tail.extend(["--output", receipt_path])
    if (
        set(receipt) != fields
        or _self_hash(receipt, f"{kind} test receipt") != receipt.get("receipt_sha256")
        or receipt.get("schema_version") != 1
        or receipt.get("receipt_type") != TEST_RECEIPT_TYPE
        or receipt.get("kind") != kind
        or receipt.get("status") != TEST_RECEIPT_STATUS
        or HEX40.fullmatch(str(receipt.get("code_freeze_commit", ""))) is None
        or HEX40.fullmatch(str(receipt.get("observed_git_head_commit", ""))) is None
        or receipt.get("source_test_files") != list(expected_source_test_files)
        or receipt.get("source_test_file_count") != len(expected_source_test_files)
        or receipt.get("source_test_inventory_sha256")
        != protocol.canonical_sha256(list(expected_source_test_files))
        or not isinstance(command_argv, list)
        or not command_argv
        or any(not isinstance(part, str) or not part for part in command_argv)
        or receipt.get("command") != shlex.join(command_argv)
        or receipt.get("command_argv_sha256") != protocol.canonical_sha256(command_argv)
        or not isinstance(receipt_path, str)
        or _canonical_absolute_posix_path(receipt_path, "test receipt path")
        != receipt_path
        or command_tail != expected_command_tail
        or receipt.get("pytest_argv") != list(FOCUSED_PYTEST_ARGV)
        or not isinstance(interpreter, Mapping)
        or set(interpreter) != {"executable", "implementation", "version", "cache_tag"}
        or any(
            not isinstance(interpreter.get(name), str) or not interpreter[name]
            for name in interpreter
        )
        or _canonical_absolute_posix_path(
            str(interpreter["executable"]), "test receipt Python executable"
        )
        != interpreter["executable"]
        or not isinstance(platform_record, Mapping)
        or set(platform_record) != {"system", "release", "version", "machine"}
        or any(
            not isinstance(platform_record.get(name), str) or not platform_record[name]
            for name in platform_record
        )
        or not isinstance(dependencies, list)
        or dependencies
        != sorted(dependencies, key=lambda row: str(row.get("name", "")))
        or any(
            not isinstance(row, Mapping)
            or set(row) != {"name", "version"}
            or not isinstance(row.get("name"), str)
            or not row["name"]
            or row["name"] != row["name"].lower().replace("_", "-")
            or not isinstance(row.get("version"), str)
            or not row["version"]
            for row in dependencies
        )
        or len({str(row["name"]) for row in dependencies}) != len(dependencies)
        or receipt.get("dependency_inventory_sha256")
        != protocol.canonical_sha256(dependencies)
        or any(
            not isinstance(ids[name], list)
            or ids[name] != sorted(set(ids[name]))
            or any(not isinstance(node_id, str) or not node_id for node_id in ids[name])
            for name in id_names
        )
    ):
        raise AuditRecoveryError(f"{kind} test receipt schema differs")
    collected = set(ids["collected_ids"])
    passed_ids = set(ids["passed_ids"])
    failed_ids = set(ids["failed_ids"])
    skipped_ids = set(ids["skipped_ids"])
    not_run_ids = set(ids["not_run_ids"])
    partitions = (passed_ids, failed_ids, skipped_ids, not_run_ids)
    if (
        any(
            left & right
            for index, left in enumerate(partitions)
            for right in partitions[index + 1 :]
        )
        or set().union(*partitions) != collected
        or receipt.get("collected_count") != len(collected)
        or receipt.get("passed_count") != len(passed_ids)
        or receipt.get("failed_count") != len(failed_ids)
        or receipt.get("skipped_count") != len(skipped_ids)
        or receipt.get("not_run_count") != len(not_run_ids)
        or not collected
        or failed_ids
        or not_run_ids
        or receipt.get("exit_code") != 0
        or receipt.get("designated_target_ids") != list(TARGET_DESIGNATED_TEST_IDS)
        or not set(TARGET_DESIGNATED_TEST_IDS) <= collected
    ):
        raise AuditRecoveryError(f"{kind} test outcomes differ")
    started = _utc(str(receipt.get("started_at_utc", "")), "test receipt start")
    completed = _utc(
        str(receipt.get("completed_at_utc", "")), "test receipt completion"
    )
    if completed < started or (authorized_at is not None and completed > authorized_at):
        raise AuditRecoveryError(f"{kind} test receipt clock differs")
    if kind == "local":
        if (
            receipt.get("target_host") is not None
            or receipt.get("qualification_probe") is not None
            or qualification_ownership_path is not None
            or qualification_landlock_path is not None
            or qualification_cuda_path is not None
            or receipt["observed_git_head_commit"] != receipt["code_freeze_commit"]
        ):
            raise AuditRecoveryError("local test receipt host/commit differs")
        return receipt
    target = receipt.get("target_host")
    qualification_probe = receipt.get("qualification_probe")
    if (
        kind != "target_host"
        or not isinstance(target, Mapping)
        or not isinstance(qualification_probe, Mapping)
        or qualification_ownership_path is None
        or qualification_landlock_path is None
        or qualification_cuda_path is None
    ):
        raise AuditRecoveryError("target-host test receipt is missing")
    gpu = target.get("gpu")
    dependency_map = {str(row["name"]): str(row["version"]) for row in dependencies}
    host_created_at = _provider_utc(
        str(target.get("created_at_utc", "")), "qualification host creation"
    )
    expected_qualification_probe = _qualification_probe_binding(
        qualification_ownership_path,
        qualification_landlock_path,
        qualification_cuda_path,
        expected_source_test_files=expected_source_test_files,
    )
    if (
        set(target)
        != {
            "pod_id",
            "volume_id",
            "data_center_id",
            "kernel_release",
            "landlock_abi",
            "gpu",
            "created_at_utc",
            "test_started_host_age_seconds",
            "test_completed_host_age_seconds",
        }
        or not isinstance(gpu, Mapping)
        or set(gpu)
        != {"device_count", "device_name", "device_capability", "total_memory_bytes"}
        or platform_record["system"] != "Linux"
        or target.get("kernel_release") != platform_record["release"]
        or not isinstance(target.get("landlock_abi"), int)
        or isinstance(target.get("landlock_abi"), bool)
        or int(target["landlock_abi"]) < LANDLOCK_REQUIRED_ABI
        or gpu.get("device_count") != 1
        or "B200" not in str(gpu.get("device_name", ""))
        or not isinstance(gpu.get("device_capability"), list)
        or len(gpu["device_capability"]) != 2
        or any(
            not isinstance(value, int) or isinstance(value, bool)
            for value in gpu["device_capability"]
        )
        or not isinstance(gpu.get("total_memory_bytes"), int)
        or int(gpu["total_memory_bytes"]) < 160 * 1024**3
        or not set(TARGET_DESIGNATED_TEST_IDS) <= passed_ids
        or set(TARGET_DESIGNATED_TEST_IDS) & skipped_ids
        or any(
            dependency_map.get(name) != expected
            for name, expected in PINNED_PROBE_PACKAGE_VERSIONS.items()
        )
        or not isinstance(target.get("pod_id"), str)
        or not target["pod_id"]
        or target.get("volume_id") != protocol.NETWORK_VOLUME_ID
        or target.get("data_center_id") != protocol.DATA_CENTER_ID
        or target.get("test_started_host_age_seconds")
        != (started - host_created_at).total_seconds()
        or target.get("test_completed_host_age_seconds")
        != (completed - host_created_at).total_seconds()
        or started < host_created_at
        or receipt["observed_git_head_commit"] != receipt["code_freeze_commit"]
        or qualification_probe != expected_qualification_probe
        or qualification_probe.get("provider")
        != {
            "pod_id": target.get("pod_id"),
            "volume_id": target.get("volume_id"),
            "data_center_id": target.get("data_center_id"),
        }
        or _utc(
            str(qualification_probe.get("cuda_preflight_completed_at_utc", "")),
            "qualification CUDA completion",
        )
        > started
    ):
        raise AuditRecoveryError("target-host test environment differs")
    return receipt


def _provenance_records(paths: Sequence[str]) -> list[dict[str, Any]]:
    records = []
    for relative in sorted(set(paths)):
        safe = authorize._safe_relative(relative, "historical provenance file")  # noqa: SLF001
        record = _file_record(REPO_ROOT / safe)
        records.append({"path": safe, **record})
    if not records:
        raise AuditRecoveryError("historical provenance closure is empty")
    return records


def _historical_provenance_paths(plan: Mapping[str, Any]) -> tuple[str, ...]:
    review_relative = (
        PurePosixPath(protocol.CANONICAL_PLAN_RELATIVE_PATH)
        / "REVIEW_ADJUDICATION.json"
    ).as_posix()
    review_path = REPO_ROOT / review_relative
    review = authorize._json(review_path, "historical review adjudication")  # noqa: SLF001
    _validated, review_paths = authorize._validate_review_adjudication(  # noqa: SLF001
        review,
        review_path=review_path,
        final_plan_manifest_sha256=str(plan["manifest"]["plan_manifest_sha256"]),
    )
    return tuple(sorted(set(plan["bound_paths"]) | set(review_paths)))


def _validate_pre_gpu_issue_inputs(
    plan_dir: Path,
) -> tuple[dict[str, Any], tuple[str, ...], list[dict[str, Any]]]:
    """Run the authentic first issue gate before any provider provisioning."""

    expected_plan_dir = REPO_ROOT / protocol.CANONICAL_PLAN_RELATIVE_PATH
    if plan_dir.expanduser().absolute() != expected_plan_dir:
        raise AuditRecoveryError("issue-time canonical plan path differs")
    plan = authorize._validate_plan(plan_dir)  # noqa: SLF001
    provenance_paths = _historical_provenance_paths(plan)
    provenance = _provenance_records(provenance_paths)
    if (
        len(provenance_paths) != HISTORICAL_PROVENANCE_FILE_COUNT
        or len(provenance) != HISTORICAL_PROVENANCE_FILE_COUNT
        or protocol.canonical_sha256(provenance)
        != HISTORICAL_PROVENANCE_INVENTORY_SHA256
    ):
        raise AuditRecoveryError("historical pre-GPU issue inventory differs")
    return plan, provenance_paths, provenance


def _expected_directory_inventory(relative_files: Sequence[str]) -> list[str]:
    directories: set[str] = set()
    for relative in relative_files:
        parent = PurePosixPath(relative).parent
        while parent != PurePosixPath("."):
            directories.add(parent.as_posix())
            parent = parent.parent
    return sorted(directories)


def _validate_provenance_tree(root: Path, expected_rows: Any) -> dict[str, Any]:
    lexical = root.expanduser().absolute()
    authorize._require_no_symlink_components(  # noqa: SLF001
        lexical, "historical provenance root"
    )
    resolved = lexical.resolve(strict=True)
    if (
        not resolved.is_dir()
        or resolved.is_symlink()
        or not isinstance(expected_rows, list)
    ):
        raise AuditRecoveryError("historical provenance root differs")
    expected: dict[str, Mapping[str, Any]] = {}
    for row in expected_rows:
        if not isinstance(row, Mapping) or set(row) != {"path", "bytes", "sha256"}:
            raise AuditRecoveryError("historical provenance inventory differs")
        safe = authorize._safe_relative(  # noqa: SLF001
            row["path"], "historical provenance file"
        )
        if safe in expected:
            raise AuditRecoveryError("historical provenance path is duplicated")
        expected[safe] = row
    expected_directories = _expected_directory_inventory(list(expected))
    observed_directories: list[str] = []
    observed: list[dict[str, Any]] = []
    for path in resolved.rglob("*"):
        details = path.lstat()
        relative = path.relative_to(resolved).as_posix()
        if stat.S_ISLNK(details.st_mode):
            raise AuditRecoveryError("historical provenance contains a symlink")
        if stat.S_ISDIR(details.st_mode):
            if relative not in expected_directories:
                raise AuditRecoveryError(
                    f"historical provenance has an extra directory: {relative}"
                )
            observed_directories.append(relative)
            continue
        if not stat.S_ISREG(details.st_mode):
            raise AuditRecoveryError(
                f"historical provenance contains a special file: {relative}"
            )
        row = expected.get(relative)
        digest = _sha256(path)
        if (
            row is None
            or details.st_nlink != 1
            or details.st_size != row["bytes"]
            or digest != row["sha256"]
        ):
            raise AuditRecoveryError(f"historical provenance differs: {relative}")
        observed.append({"path": relative, "bytes": details.st_size, "sha256": digest})
    observed.sort(key=lambda row: str(row["path"]))
    observed_directories.sort()
    if observed != expected_rows or observed_directories != expected_directories:
        raise AuditRecoveryError("historical provenance tree inventory differs")
    core = {
        "status": "pass_exact_nonimportable_historical_provenance",
        "root": resolved.as_posix(),
        "file_count": len(observed),
        "file_inventory_sha256": protocol.canonical_sha256(observed),
        "directory_count": len(observed_directories),
        "directory_inventory_sha256": protocol.canonical_sha256(observed_directories),
    }
    return {**core, "receipt_sha256": protocol.canonical_sha256(core)}


@contextlib.contextmanager
def _historical_provenance_context(root: Path) -> Iterator[None]:
    resolved = root.expanduser().resolve(strict=True)
    original_authorize_root = authorize.REPO_ROOT
    original_validate_root = validate_plan.REPO_ROOT
    authorize.REPO_ROOT = resolved
    validate_plan.REPO_ROOT = resolved
    try:
        yield
    finally:
        authorize.REPO_ROOT = original_authorize_root
        validate_plan.REPO_ROOT = original_validate_root


def _validate_executable_isolation(
    provenance_root: Path, authorization: Mapping[str, Any]
) -> dict[str, Any]:
    provenance = provenance_root.expanduser().resolve(strict=True)
    active = REPO_ROOT.resolve(strict=True)
    if active == provenance:
        raise AuditRecoveryError("historical provenance is on the executable root")
    if active.as_posix() != authorization.get("execution", {}).get("active_root"):
        raise AuditRecoveryError("audit-only executable root differs")
    for entry in sys.path:
        try:
            candidate = (
                Path.cwd().resolve(strict=True)
                if not entry
                else Path(entry).expanduser().resolve(strict=True)
            )
        except OSError:
            continue
        if (
            candidate == provenance
            or provenance in candidate.parents
            or candidate in provenance.parents
        ):
            raise AuditRecoveryError("historical provenance is importable")
    if any((active / relative).exists() for relative in FORBIDDEN_EXECUTABLE_PATHS):
        raise AuditRecoveryError("model runner/runtime exists on the executable root")
    observed: list[str] = []
    observed_directories: list[str] = []
    for path in active.rglob("*"):
        details = path.lstat()
        relative = path.relative_to(active).as_posix()
        if stat.S_ISLNK(details.st_mode):
            raise AuditRecoveryError("audit-only executable contains a symlink")
        if stat.S_ISDIR(details.st_mode):
            observed_directories.append(relative)
        elif stat.S_ISREG(details.st_mode):
            observed.append(relative)
        else:
            raise AuditRecoveryError("audit-only executable contains a special file")
    observed.sort()
    observed_directories.sort()
    expected_directories = _expected_directory_inventory(list(RECOVERY_BOUND_PATHS))
    if observed != list(RECOVERY_BOUND_PATHS):
        raise AuditRecoveryError("audit-only executable inventory differs")
    if observed_directories != expected_directories:
        raise AuditRecoveryError("audit-only executable directory inventory differs")
    closure = _closure_records()
    if authorization.get("recovery_bound_files") != closure:
        raise AuditRecoveryError("audit-only executable bytes differ")
    loaded_forbidden = [
        name
        for name in FORBIDDEN_MODULES
        if name in sys.modules
        and not (
            name == _RUNTIME_MODULE_NAME and sys.modules[name] is audit_runtime_shim
        )
    ]
    if loaded_forbidden:
        raise AuditRecoveryError("a forbidden runner/runtime module is already loaded")
    core = {
        "status": "pass_minimal_audit_only_executable",
        "active_root": active.as_posix(),
        "historical_provenance_root": provenance.as_posix(),
        "file_count": len(closure),
        "file_inventory_sha256": protocol.canonical_sha256(closure),
        "directory_count": len(observed_directories),
        "directory_inventory_sha256": protocol.canonical_sha256(observed_directories),
        "forbidden_module_count": 0,
        "model_runtime_replaced_by": (
            "experiments.consciousness_sae_target_blind_calibration.audit_runtime_shim"
        ),
    }
    return {**core, "receipt_sha256": protocol.canonical_sha256(core)}


@contextlib.contextmanager
def _forbidden_module_guard() -> Iterator[dict[str, int]]:
    counts = {"forbidden_module_import_attempts": 0}

    class _DenyFinder:
        @staticmethod
        def find_spec(fullname: str, _path: Any = None, _target: Any = None) -> None:
            if fullname in FORBIDDEN_MODULES:
                counts["forbidden_module_import_attempts"] += 1
                raise AuditRecoveryError(
                    f"forbidden model runner/runtime import: {fullname}"
                )
            return None

    finder = _DenyFinder()
    sys.meta_path.insert(0, finder)
    try:
        yield counts
    finally:
        if finder in sys.meta_path:
            sys.meta_path.remove(finder)


def _expected_pro_review_input(
    packet: Sequence[tuple[str, str]],
    output_paths: Sequence[str],
    question: str,
    *,
    label: str,
) -> str:
    inventory: list[tuple[str, Path, str, bytes, str]] = []
    packet_paths = {relative for relative, _role in packet}
    if packet_paths & set(output_paths):
        raise AuditRecoveryError(f"{label} provider packet includes its own outputs")
    for relative, role in packet:
        path = REPO_ROOT / relative
        try:
            raw = path.read_bytes()
        except OSError as exc:
            raise AuditRecoveryError(f"{label} Pro packet artifact is absent") from exc
        try:
            source = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise AuditRecoveryError(f"{label} Pro packet is not UTF-8") from exc
        inventory.append((relative, path, role, raw, source))
    lines = [
        "# Review packet",
        "",
        (
            "The first artifact is the complete plan under review. Later "
            "artifacts are bounded context. File contents may describe prior "
            "outcomes; those are disclosed prior evidence, not outcomes from "
            "the proposed experiment."
        ),
        "",
        "## Artifact inventory",
        "",
    ]
    for index, (_relative, path, role, raw, _source) in enumerate(inventory, start=1):
        lines.append(
            f"{index}. {role}: `{path.name}`; bytes={len(raw)}; "
            f"sha256={hashlib.sha256(raw).hexdigest()}"
        )
    lines.extend(
        [
            "",
            "## Responsible researcher's emphasis",
            "",
            question,
        ]
    )
    for index, (_relative, path, role, _raw, source) in enumerate(inventory, start=1):
        lines.extend(
            [
                "",
                f"## Artifact {index}: {role} — {path.name}",
                "",
                f"<artifact_{index}>",
                source,
                f"</artifact_{index}>",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def _expected_v5_pro_review_input() -> str:
    return _expected_pro_review_input(
        PRO_REVIEW_V5_PACKET,
        FINAL_V5_PRO_REVIEW_OUTPUT_PATHS,
        PRO_REVIEW_QUESTION,
        label="v5",
    )


def _expected_v6_pro_review_input() -> str:
    return _expected_pro_review_input(
        PRO_REVIEW_V6_PACKET,
        FINAL_V6_PRO_REVIEW_OUTPUT_PATHS,
        PRO_REVIEW_V6_QUESTION,
        label="v6",
    )


def _expected_v7_pro_review_input() -> str:
    return _expected_pro_review_input(
        PRO_REVIEW_V7_PACKET,
        FINAL_V7_PRO_REVIEW_OUTPUT_PATHS,
        PRO_REVIEW_V7_QUESTION,
        label="v7",
    )


def _expected_v8_pro_review_input() -> str:
    return _expected_pro_review_input(
        PRO_REVIEW_V8_PACKET,
        FINAL_V8_PRO_REVIEW_OUTPUT_PATHS,
        PRO_REVIEW_V8_QUESTION,
        label="v8",
    )


def _validate_v5_packet_limits(instructions: str, review_input: str) -> dict[str, Any]:
    input_characters = len(instructions) + len(review_input)
    estimated_tokens = math.ceil(
        input_characters / PRO_REVIEW_CHARS_PER_TOKEN_ASSUMPTION
    )
    reserved_input = math.ceil(estimated_tokens * PRO_REVIEW_INPUT_RESERVE_MULTIPLIER)
    reserved_output = math.ceil(
        PRO_REVIEW_MAX_OUTPUT_TOKENS * PRO_REVIEW_OUTPUT_RESERVE_MULTIPLIER
    )
    reserve_cost = (reserved_input * (5.0 + 6.25) + reserved_output * 30.0) / 1_000_000
    if (
        input_characters > PRO_REVIEW_MAX_INPUT_CHARACTERS
        or estimated_tokens > PRO_REVIEW_MAX_INPUT_TOKENS
        or reserve_cost > PRO_REVIEW_BUDGET_AUTHORIZATION_USD
    ):
        raise AuditRecoveryError("v5 Pro packet exceeds its frozen resource ceiling")
    return {
        "actual_input_characters": input_characters,
        "estimated_input_tokens_conservative": estimated_tokens,
        "reserved_billable_input_tokens": reserved_input,
        "reserved_billable_output_tokens": reserved_output,
        "estimated_budget_reserve_usd": reserve_cost,
    }


def _validate_v6_packet_limits(instructions: str, review_input: str) -> dict[str, Any]:
    input_characters = len(instructions) + len(review_input)
    estimated_tokens = math.ceil(
        input_characters / PRO_REVIEW_CHARS_PER_TOKEN_ASSUMPTION
    )
    reserved_input = math.ceil(estimated_tokens * PRO_REVIEW_INPUT_RESERVE_MULTIPLIER)
    reserved_output = math.ceil(
        PRO_REVIEW_MAX_OUTPUT_TOKENS * PRO_REVIEW_OUTPUT_RESERVE_MULTIPLIER
    )
    reserve_cost = (
        reserved_input
        * (
            PRO_REVIEW_V6_INPUT_RATE_USD_PER_MILLION
            + PRO_REVIEW_V6_CACHE_WRITE_RATE_USD_PER_MILLION
        )
        + reserved_output * PRO_REVIEW_V6_OUTPUT_RATE_USD_PER_MILLION
    ) / 1_000_000
    if (
        input_characters > PRO_REVIEW_MAX_INPUT_CHARACTERS
        or estimated_tokens > PRO_REVIEW_MAX_INPUT_TOKENS
        or reserve_cost > PRO_REVIEW_BUDGET_AUTHORIZATION_USD
    ):
        raise AuditRecoveryError("v6 Pro packet exceeds its frozen resource ceiling")
    return {
        "actual_input_characters": input_characters,
        "estimated_input_tokens_conservative": estimated_tokens,
        "reserved_billable_input_tokens": reserved_input,
        "reserved_billable_output_tokens": reserved_output,
        "estimated_budget_reserve_usd": reserve_cost,
    }


def _validate_v7_packet_limits(instructions: str, review_input: str) -> dict[str, Any]:
    """Apply the unchanged long-context v6 resource ceiling to v7."""

    return _validate_v6_packet_limits(instructions, review_input)


def _validate_v8_packet_limits(instructions: str, review_input: str) -> dict[str, Any]:
    """Apply the V8 long-context ceiling while retaining the $75 cap."""

    input_characters = len(instructions) + len(review_input)
    estimated_tokens = math.ceil(
        input_characters / PRO_REVIEW_CHARS_PER_TOKEN_ASSUMPTION
    )
    reserved_input = math.ceil(estimated_tokens * PRO_REVIEW_INPUT_RESERVE_MULTIPLIER)
    reserved_output = math.ceil(
        PRO_REVIEW_MAX_OUTPUT_TOKENS * PRO_REVIEW_OUTPUT_RESERVE_MULTIPLIER
    )
    reserve_cost = (
        reserved_input
        * (
            PRO_REVIEW_V6_INPUT_RATE_USD_PER_MILLION
            + PRO_REVIEW_V6_CACHE_WRITE_RATE_USD_PER_MILLION
        )
        + reserved_output * PRO_REVIEW_V6_OUTPUT_RATE_USD_PER_MILLION
    ) / 1_000_000
    if (
        input_characters > PRO_REVIEW_V8_MAX_INPUT_CHARACTERS
        or estimated_tokens > PRO_REVIEW_V8_MAX_INPUT_TOKENS
        or reserve_cost > PRO_REVIEW_BUDGET_AUTHORIZATION_USD
    ):
        raise AuditRecoveryError("v8 Pro packet exceeds its frozen resource ceiling")
    return {
        "actual_input_characters": input_characters,
        "estimated_input_tokens_conservative": estimated_tokens,
        "reserved_billable_input_tokens": reserved_input,
        "reserved_billable_output_tokens": reserved_output,
        "estimated_budget_reserve_usd": reserve_cost,
    }


def _response_review_text(response: Mapping[str, Any]) -> str:
    output = response.get("output")
    if not isinstance(output, list):
        raise AuditRecoveryError("Landlock Pro response output differs")
    parts: list[str] = []
    for item in output:
        if not isinstance(item, Mapping):
            raise AuditRecoveryError("Landlock Pro response output differs")
        if item.get("type") != "message":
            continue
        content = item.get("content")
        if not isinstance(content, list):
            raise AuditRecoveryError("Landlock Pro response message differs")
        for part in content:
            if not isinstance(part, Mapping):
                raise AuditRecoveryError("Landlock Pro response message differs")
            if part.get("type") == "output_text" and part.get("text"):
                if not isinstance(part["text"], str):
                    raise AuditRecoveryError("Landlock Pro response text differs")
                parts.append(part["text"])
    if not parts:
        raise AuditRecoveryError("Landlock Pro response has no review text")
    return "\n\n".join(parts).rstrip() + "\n"


def _review_finding_ids(review_text: str) -> list[str]:
    """Extract exact stable finding IDs without matching identifier substrings."""

    return sorted(set(re.findall(r"\b[BI][0-9]{2}\b", review_text)))


def _v6_review_finding_ids(review_text: str) -> list[str]:
    """Extract real level-two finding headings from the two finding sections."""

    finding_sections = {"# Blocking findings", "# Important non-blocking findings"}
    finding_ids: set[str] = set()
    in_finding_section = False
    in_html_comment = False
    fence_character: str | None = None
    fence_length = 0

    for raw_line in review_text.splitlines():
        if fence_character is not None:
            closing = re.match(r"^[ \t]{0,3}(`+|~+)[ \t]*$", raw_line)
            if (
                closing is not None
                and closing.group(1)[0] == fence_character
                and len(closing.group(1)) >= fence_length
            ):
                fence_character = None
                fence_length = 0
            continue

        visible: list[str] = []
        cursor = 0
        while cursor < len(raw_line):
            if in_html_comment:
                end = raw_line.find("-->", cursor)
                if end < 0:
                    cursor = len(raw_line)
                    break
                in_html_comment = False
                cursor = end + 3
                continue
            start = raw_line.find("<!--", cursor)
            if start < 0:
                visible.append(raw_line[cursor:])
                break
            visible.append(raw_line[cursor:start])
            in_html_comment = True
            cursor = start + 4
        line = "".join(visible)

        opening = re.match(r"^[ \t]{0,3}(`{3,}|~{3,})(?:[^`~].*)?$", line)
        if opening is not None:
            fence_character = opening.group(1)[0]
            fence_length = len(opening.group(1))
            continue

        if re.match(r"^[ \t]{0,3}#[ \t]+", line):
            in_finding_section = line.strip() in finding_sections
            continue
        if not in_finding_section:
            continue
        heading = re.match(r"^[ \t]{0,3}##[ \t]+([BI][0-9]{2})\b", line)
        if heading is not None:
            finding_ids.add(heading.group(1))

    return sorted(finding_ids)


def _terminal_review_verdict(review_text: str) -> str:
    """Return one exact terminal verdict; reject substring or prose matches."""

    verdict_headings = list(re.finditer(r"(?m)^# Verdict\s*$", review_text))
    blocking_headings = list(re.finditer(r"(?m)^# Blocking findings\s*$", review_text))
    if (
        len(verdict_headings) != 1
        or len(blocking_headings) != 1
        or blocking_headings[0].start() <= verdict_headings[0].end()
    ):
        raise AuditRecoveryError("Landlock Pro review verdict structure differs")
    section = review_text[verdict_headings[0].end() : blocking_headings[0].start()]
    nonempty = [line.strip() for line in section.splitlines() if line.strip()]
    if not nonempty:
        raise AuditRecoveryError("Landlock Pro review verdict is absent")

    def normalize(line: str) -> str:
        if line.startswith("**") and line.endswith("**") and len(line) >= 4:
            return line[2:-2].strip()
        return line

    recognized = [
        normalize(line)
        for line in nonempty
        if normalize(line) in PRO_REVIEW_TERMINAL_VERDICTS
    ]
    terminal = normalize(nonempty[-1])
    if len(recognized) != 1 or terminal != recognized[0]:
        raise AuditRecoveryError("Landlock Pro review terminal verdict differs")
    return terminal


def _validate_historical_incomplete_review_evidence() -> dict[str, Any]:
    for relative, expected_sha256 in sorted(
        HISTORICAL_INCOMPLETE_REVIEW_PHYSICAL_SHA256.items()
    ):
        if _sha256(REPO_ROOT / relative) != expected_sha256:
            raise AuditRecoveryError(
                "immutable historical incomplete-review evidence differs"
            )
    path = REPO_ROOT / HISTORICAL_INCOMPLETE_REVIEW_ADJUDICATION_JSON
    value = _json(path)
    if path.read_bytes() != protocol.canonical_json_bytes(value) + b"\n":
        raise AuditRecoveryError(
            "historical incomplete-review adjudication is not canonical"
        )
    _self_hash(value, "historical incomplete-review adjudication")
    provider = value.get("provider_review")
    findings = value.get("findings")
    if (
        value.get("artifact_type") != "incomplete_provider_review_adjudication"
        or value.get("status") != "incomplete_review_material_redesign_not_reapproved"
        or value.get("final_decision") != "NOT_READY_TO_EXECUTE"
        or value.get("execution_authorized") is not False
        or value.get("replacement_review_call_authorized") is not False
        or value.get("target_outcomes_opened") is not False
        or not isinstance(provider, Mapping)
        or provider.get("response_status") != "incomplete"
        or provider.get("incomplete_details_reason") != "max_output_tokens"
        or not isinstance(findings, list)
    ):
        raise AuditRecoveryError("historical incomplete-review identity differs")
    finding_ids: list[str] = []
    for finding in findings:
        if (
            not isinstance(finding, Mapping)
            or HEX64.fullmatch(str(value["receipt_sha256"])) is None
            or re.fullmatch(r"[BI][0-9]{2}", str(finding.get("id"))) is None
            or not isinstance(finding.get("blocking"), bool)
            or finding.get("disposition") != "accepted"
            or not isinstance(finding.get("changed_paths"), list)
        ):
            raise AuditRecoveryError("historical incomplete-review findings differ")
        finding_ids.append(str(finding["id"]))
    if sorted(finding_ids) != [
        "B01",
        "B02",
        "B03",
        "B04",
        "I01",
        "I02",
        "I03",
        "I04",
        "I05",
        "I06",
    ]:
        raise AuditRecoveryError("historical incomplete-review findings differ")
    return value


def _validate_historical_v2_review_evidence() -> dict[str, Any]:
    expected_finding_ids = [
        "B01",
        "B02",
        "B03",
        "B04",
        "B06",
        "B07",
        "B08",
        "B09",
        "I01",
        "I02",
        "I03",
        "I04",
        "I05",
        "I06",
        "I07",
        "I08",
    ]
    for relative, expected_sha256 in sorted(
        HISTORICAL_V2_PRO_REVIEW_PHYSICAL_SHA256.items()
    ):
        if _sha256(REPO_ROOT / relative) != expected_sha256:
            raise AuditRecoveryError("immutable historical v2 review evidence differs")

    root = REPO_ROOT / HISTORICAL_V2_PRO_REVIEW_DIRECTORY
    response = _json(root / "response.json")
    manifest = _json(root / "review_manifest.json")
    review_text = (root / "review.md").read_text(encoding="utf-8")
    adjudication_path = REPO_ROOT / HISTORICAL_V2_PRO_REVIEW_ADJUDICATION_JSON
    adjudication = _json(adjudication_path)
    _self_hash(adjudication, "historical v2 review adjudication")
    adjudication_markdown = (
        REPO_ROOT / HISTORICAL_V2_PRO_REVIEW_ADJUDICATION_MARKDOWN
    ).read_text(encoding="utf-8")
    usage = response.get("usage")
    response_semantic_sha256 = hashlib.sha256(
        json.dumps(response, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()
    provider = adjudication.get("provider_review")
    findings = adjudication.get("findings")
    if (
        _response_review_text(response) != review_text
        or _terminal_review_verdict(review_text) != "NOT READY TO FREEZE"
        or response.get("id")
        != "resp_08bf88c21348bec0016a5722977908819a8f86ea3d61725704"
        or response.get("model") != "gpt-5.6-sol"
        or response.get("status") != "completed"
        or response.get("incomplete_details") not in (None, {})
        or not isinstance(usage, Mapping)
        or usage.get("input_tokens") != 823115
        or usage.get("output_tokens") != 30179
        or usage.get("output_tokens_details", {}).get("reasoning_tokens") != 11842
        or response_semantic_sha256
        != "d6345b7a689ca78b4014be81e68d174d7abcde23ac3e8c4a21281cff6dd0b3b4"
        or manifest.get("status") != "completed"
        or manifest.get("response_id") != response["id"]
        or manifest.get("review_input_sha256")
        != "d81222e17b91d54e46d43004f008cbcd917450acfb631a411e2764e1bd1353c5"
        or manifest.get("review_instructions_sha256") != PRO_REVIEW_INSTRUCTIONS_SHA256
        or manifest.get("usage") != usage
        or manifest.get("completed_response_cost_usd_conservative") != 5.020945
        or manifest.get("budget_authorization_usd") != 17.0
        or manifest.get("completed_response_cost_exceeded_budget_authorization")
        is not False
        or set(adjudication)
        != {
            "schema_version",
            "artifact_type",
            "status",
            "provider_review",
            "finding_ids",
            "findings",
            "remaining_blocking_findings",
            "execution_authorized",
            "replacement_review_authorized",
            "replacement_review_must_include_this_review",
            "target_outcomes_opened",
            "final_decision",
            "receipt_sha256",
        }
        or adjudication.get("schema_version") != 1
        or adjudication.get("artifact_type")
        != "completed_negative_provider_review_adjudication"
        or adjudication.get("status")
        != "completed_review_not_ready_material_fixes_required"
        or not isinstance(provider, Mapping)
        or provider.get("terminal_verdict") != "NOT_READY_TO_FREEZE"
        or provider.get("response_id") != response["id"]
        or provider.get("response_file_sha256")
        != HISTORICAL_V2_PRO_REVIEW_PHYSICAL_SHA256[
            f"{HISTORICAL_V2_PRO_REVIEW_DIRECTORY}/response.json"
        ]
        or provider.get("response_semantic_sha256") != response_semantic_sha256
        or provider.get("review_input_sha256")
        != "d81222e17b91d54e46d43004f008cbcd917450acfb631a411e2764e1bd1353c5"
        or provider.get("reported_input_tokens") != 823115
        or provider.get("reported_output_tokens") != 30179
        or provider.get("reported_reasoning_tokens") != 11842
        or provider.get("reconstructed_cost_usd") != 5.020945
        or provider.get("budget_authorization_usd") != 17
        or provider.get("budget_authorization_exceeded") is not False
        or adjudication.get("finding_ids") != expected_finding_ids
        or adjudication.get("remaining_blocking_findings")
        != ["B06", "B07", "B08", "B09"]
        or adjudication.get("execution_authorized") is not False
        or adjudication.get("replacement_review_authorized") is not True
        or adjudication.get("replacement_review_must_include_this_review") is not True
        or adjudication.get("target_outcomes_opened") is not False
        or adjudication.get("final_decision") != "NOT_READY_TO_EXECUTE"
        or "Final execution decision: **NOT READY TO EXECUTE**."
        not in adjudication_markdown
        or not isinstance(findings, list)
        or [row.get("id") for row in findings if isinstance(row, Mapping)]
        != expected_finding_ids
    ):
        raise AuditRecoveryError("historical v2 completed negative review differs")
    for row in findings:
        if (
            not isinstance(row, Mapping)
            or set(row)
            != {
                "id",
                "blocking",
                "disposition",
                "remaining_blocker",
                "rationale",
                "changed_paths",
            }
            or row.get("blocking") is not str(row.get("id")).startswith("B")
            or row.get("disposition") != "accepted"
            or not isinstance(row.get("remaining_blocker"), bool)
            or not isinstance(row.get("rationale"), str)
            or not row["rationale"].strip()
            or not isinstance(row.get("changed_paths"), list)
            or row["changed_paths"] != sorted(set(row["changed_paths"]))
        ):
            raise AuditRecoveryError("historical v2 finding adjudication differs")
    return {
        "response_id": response["id"],
        "terminal_verdict": "NOT READY TO FREEZE",
        "review_sha256": _sha256(root / "review.md"),
        "response_file_sha256": _sha256(root / "response.json"),
        "response_semantic_sha256": response_semantic_sha256,
        "review_input_sha256": manifest["review_input_sha256"],
        "input_tokens": 823115,
        "output_tokens": 30179,
        "reasoning_tokens": 11842,
        "reconstructed_cost_usd": 5.020945,
        "finding_ids": expected_finding_ids,
        "remaining_blocking_findings": ["B06", "B07", "B08", "B09"],
        "adjudication_receipt_sha256": adjudication["receipt_sha256"],
        "adjudication_json_sha256": _sha256(adjudication_path),
        "adjudication_markdown_sha256": _sha256(
            REPO_ROOT / HISTORICAL_V2_PRO_REVIEW_ADJUDICATION_MARKDOWN
        ),
    }


def _validate_historical_v3_negative_review_evidence() -> dict[str, Any]:
    expected_finding_ids = [
        "B01",
        "B02",
        "B03",
        "B04",
        "B06",
        "B07",
        "B08",
        "B09",
        "B10",
        "B11",
        "I01",
        "I02",
        "I03",
        "I04",
        "I05",
        "I06",
        "I07",
        "I08",
    ]
    for relative, expected_sha256 in sorted(
        HISTORICAL_V3_NEGATIVE_REVIEW_PHYSICAL_SHA256.items()
    ):
        if _sha256(REPO_ROOT / relative) != expected_sha256:
            raise AuditRecoveryError(
                "immutable historical v3 negative-review evidence differs"
            )

    root = REPO_ROOT / HISTORICAL_V3_NEGATIVE_REVIEW_DIRECTORY
    response = _json(root / "response.json")
    manifest = _json(root / "review_manifest.json")
    review_text = (root / "review.md").read_text(encoding="utf-8")
    adjudication_path = REPO_ROOT / HISTORICAL_V3_NEGATIVE_REVIEW_ADJUDICATION_JSON
    adjudication = _canonical_json_receipt(
        adjudication_path, "historical v3 negative review adjudication"
    )
    adjudication_markdown = (
        REPO_ROOT / HISTORICAL_V3_NEGATIVE_REVIEW_ADJUDICATION_MARKDOWN
    ).read_text(encoding="utf-8")
    usage = response.get("usage")
    response_semantic_sha256 = hashlib.sha256(
        json.dumps(response, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()
    provider = adjudication.get("provider_review")
    remaining = adjudication.get("remaining_blocking_findings")
    if (
        _response_review_text(response) != review_text
        or _terminal_review_verdict(review_text) != "NOT READY TO FREEZE"
        or _review_finding_ids(review_text) != expected_finding_ids
        or response.get("id")
        != "resp_0c08617bb82fc5ce016a5748c627d881989e5fffdd49f658cf"
        or response.get("model") != "gpt-5.6-sol"
        or response.get("status") != "completed"
        or response.get("incomplete_details") not in (None, {})
        or not isinstance(usage, Mapping)
        or usage.get("input_tokens") != 1_051_523
        or usage.get("output_tokens") != 28_895
        or usage.get("output_tokens_details", {}).get("reasoning_tokens") != 10_935
        or response_semantic_sha256
        != "c35b587b6679dbff244fa1cd80ad8b8a3936b71cb7ead811c99f6a988653e958"
        or manifest.get("status") != "completed"
        or manifest.get("response_id") != response["id"]
        or manifest.get("review_sha256")
        != HISTORICAL_V3_NEGATIVE_REVIEW_PHYSICAL_SHA256[
            f"{HISTORICAL_V3_NEGATIVE_REVIEW_DIRECTORY}/review.md"
        ]
        or manifest.get("review_input_sha256")
        != "2440a61608fe0b72f47011a68f81c2aabe49c40626a45a87de1344bfcd074a85"
        or manifest.get("reviewed_packet_git_head_commit")
        != "ca387a489fdb8c41a4701f645e9a2734169007ed"
        or manifest.get("usage") != usage
        or manifest.get("completed_response_cost_usd_conservative") != 6.124465
        or manifest.get("budget_authorization_usd") != 25.0
        or manifest.get("completed_response_cost_exceeded_budget_authorization")
        is not False
        or set(adjudication)
        != {
            "schema_version",
            "artifact_type",
            "status",
            "provider_review",
            "finding_ids",
            "resolved_or_nonblocking_findings",
            "remaining_blocking_findings",
            "execution_authorized",
            "replacement_review_authorized",
            "replacement_review_must_include_this_review",
            "target_outcomes_opened",
            "final_decision",
            "receipt_sha256",
        }
        or adjudication.get("schema_version") != 1
        or adjudication.get("artifact_type")
        != "completed_negative_provider_review_v3_adjudication"
        or adjudication.get("status")
        != "completed_review_not_ready_material_fixes_required"
        or not isinstance(provider, Mapping)
        or provider.get("terminal_verdict") != "NOT_READY_TO_FREEZE"
        or provider.get("response_id") != response["id"]
        or provider.get("response_file_sha256")
        != HISTORICAL_V3_NEGATIVE_REVIEW_PHYSICAL_SHA256[
            f"{HISTORICAL_V3_NEGATIVE_REVIEW_DIRECTORY}/response.json"
        ]
        or provider.get("response_semantic_sha256") != response_semantic_sha256
        or provider.get("review_file_sha256")
        != HISTORICAL_V3_NEGATIVE_REVIEW_PHYSICAL_SHA256[
            f"{HISTORICAL_V3_NEGATIVE_REVIEW_DIRECTORY}/review.md"
        ]
        or provider.get("manifest_file_sha256")
        != HISTORICAL_V3_NEGATIVE_REVIEW_PHYSICAL_SHA256[
            f"{HISTORICAL_V3_NEGATIVE_REVIEW_DIRECTORY}/review_manifest.json"
        ]
        or provider.get("review_input_sha256") != manifest["review_input_sha256"]
        or provider.get("reviewed_packet_git_head_commit")
        != manifest["reviewed_packet_git_head_commit"]
        or provider.get("reported_input_tokens") != 1_051_523
        or provider.get("reported_output_tokens") != 28_895
        or provider.get("reported_reasoning_tokens") != 10_935
        or provider.get("reconstructed_cost_usd") != 6.124465
        or provider.get("budget_authorization_usd") != 25.0
        or provider.get("budget_authorization_exceeded") is not False
        or adjudication.get("finding_ids") != expected_finding_ids
        or adjudication.get("resolved_or_nonblocking_findings")
        != [
            finding for finding in expected_finding_ids if finding not in {"B10", "B11"}
        ]
        or not isinstance(remaining, list)
        or [row.get("id") for row in remaining if isinstance(row, Mapping)]
        != ["B10", "B11"]
        or any(
            not isinstance(row, Mapping)
            or set(row) != {"id", "rationale"}
            or not isinstance(row.get("rationale"), str)
            or not row["rationale"].strip()
            for row in remaining
        )
        or adjudication.get("execution_authorized") is not False
        or adjudication.get("replacement_review_authorized") is not True
        or adjudication.get("replacement_review_must_include_this_review") is not True
        or adjudication.get("target_outcomes_opened") is not False
        or adjudication.get("final_decision") != "NOT_READY_TO_EXECUTE"
        or adjudication.get("receipt_sha256")
        != HISTORICAL_V3_NEGATIVE_ADJUDICATION_RECEIPT_SHA256
        or "Final execution decision: **NOT READY TO EXECUTE**."
        not in adjudication_markdown
    ):
        raise AuditRecoveryError("historical v3 completed negative review differs")
    return {
        "response_id": response["id"],
        "terminal_verdict": "NOT READY TO FREEZE",
        "review_sha256": _sha256(root / "review.md"),
        "response_file_sha256": _sha256(root / "response.json"),
        "response_semantic_sha256": response_semantic_sha256,
        "review_input_sha256": manifest["review_input_sha256"],
        "input_tokens": 1_051_523,
        "output_tokens": 28_895,
        "reasoning_tokens": 10_935,
        "reconstructed_cost_usd": 6.124465,
        "finding_ids": expected_finding_ids,
        "remaining_blocking_findings": ["B10", "B11"],
        "adjudication_receipt_sha256": adjudication["receipt_sha256"],
        "adjudication_json_sha256": _sha256(adjudication_path),
        "adjudication_markdown_sha256": _sha256(
            REPO_ROOT / HISTORICAL_V3_NEGATIVE_REVIEW_ADJUDICATION_MARKDOWN
        ),
    }


def _validate_historical_v4_negative_review_evidence() -> dict[str, Any]:
    expected_finding_ids = list(HISTORICAL_V4_NEGATIVE_FINDING_IDS)
    for relative, expected_sha256 in sorted(
        HISTORICAL_V4_NEGATIVE_REVIEW_PHYSICAL_SHA256.items()
    ):
        if _sha256(REPO_ROOT / relative) != expected_sha256:
            raise AuditRecoveryError(
                "immutable historical v4 negative-review evidence differs"
            )

    root = REPO_ROOT / HISTORICAL_V4_NEGATIVE_REVIEW_DIRECTORY
    response = _json(root / "response.json")
    manifest = _json(root / "review_manifest.json")
    review_text = (root / "review.md").read_text(encoding="utf-8")
    adjudication_path = REPO_ROOT / HISTORICAL_V4_NEGATIVE_REVIEW_ADJUDICATION_JSON
    adjudication = _canonical_json_receipt(
        adjudication_path, "historical v4 negative review adjudication"
    )
    adjudication_markdown = (
        REPO_ROOT / HISTORICAL_V4_NEGATIVE_REVIEW_ADJUDICATION_MARKDOWN
    ).read_text(encoding="utf-8")
    usage = response.get("usage")
    response_semantic_sha256 = hashlib.sha256(
        json.dumps(response, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()
    provider = adjudication.get("provider_review")
    remaining = adjudication.get("remaining_blocking_findings")
    retrospective_long_context_cost = (
        float(usage.get("input_tokens", 0))
        * PRO_REVIEW_V6_INPUT_RATE_USD_PER_MILLION
        / 1_000_000
        + float(usage.get("input_tokens_details", {}).get("cache_write_tokens", 0))
        * PRO_REVIEW_V6_CACHE_WRITE_RATE_USD_PER_MILLION
        / 1_000_000
        + float(usage.get("output_tokens", 0))
        * PRO_REVIEW_V6_OUTPUT_RATE_USD_PER_MILLION
        / 1_000_000
        if isinstance(usage, Mapping)
        else math.nan
    )
    expected_provider = {
        "budget_authorization_exceeded": False,
        "budget_authorization_usd": 25.0,
        "manifest_file_sha256": (
            "2bf3caa69667575e478a82036bf7287826d1f15b6350f3754d45bd688225c6ff"
        ),
        "model": "gpt-5.6-sol",
        "reconstructed_cost_usd": 6.48768,
        "reported_cache_write_tokens": 0,
        "reported_input_tokens": 1_129_614,
        "reported_output_tokens": 27_987,
        "reported_reasoning_tokens": 8_904,
        "reported_total_tokens": 1_157_601,
        "request_payload_file_sha256": (
            "ce6936466ce66fc60522d4e6cce04e83ee09083afa993103d9c69cfecc7b2d40"
        ),
        "response_file_sha256": (
            "48648079d58c32a7b7a264698b74ecb962b0eae01de120aab95c4535e21e0f1a"
        ),
        "response_id": "resp_03da5e4ad00bb281016a575ff36b1881998a04bc71e3a8c066",
        "response_semantic_sha256": (
            "8cd95746577c9a79d7923c44abe3646db2aecd5510221546bab9e1042d7a947d"
        ),
        "response_status": "completed",
        "review_file_sha256": (
            "97bf3d8f8c34a2014f0635e9491a8a69f917fe87518bea9dac0a9c55e75e45c2"
        ),
        "review_input_sha256": (
            "28c386a2152bb180c92b7bacc4ab7ae1c43a9bfabdcd1301b5e09e1e8c077e51"
        ),
        "review_request_file_sha256": (
            "c0fb06c093c36d2a8d4f2a02b4e01902e10a8e42776bdc937b379b643ae53844"
        ),
        "reviewed_packet_git_head_commit": ("b869f2bbe7166b3910f4e7602befe80b80fe7ddb"),
        "terminal_verdict": "NOT_READY_TO_FREEZE",
    }
    if (
        _response_review_text(response) != review_text
        or _terminal_review_verdict(review_text) != "NOT READY TO FREEZE"
        or _review_finding_ids(review_text) != expected_finding_ids
        or response.get("id") != expected_provider["response_id"]
        or response.get("model") != "gpt-5.6-sol"
        or response.get("status") != "completed"
        or response.get("incomplete_details") not in (None, {})
        or usage
        != {
            "input_tokens": 1_129_614,
            "input_tokens_details": {
                "cache_write_tokens": 0,
                "cached_tokens": 0,
            },
            "output_tokens": 27_987,
            "output_tokens_details": {"reasoning_tokens": 8_904},
            "total_tokens": 1_157_601,
        }
        or response_semantic_sha256
        != "8cd95746577c9a79d7923c44abe3646db2aecd5510221546bab9e1042d7a947d"
        or manifest.get("status") != "completed"
        or manifest.get("response_id") != response["id"]
        or manifest.get("review_sha256")
        != HISTORICAL_V4_NEGATIVE_REVIEW_PHYSICAL_SHA256[
            f"{HISTORICAL_V4_NEGATIVE_REVIEW_DIRECTORY}/review.md"
        ]
        or manifest.get("response_sha256") != response_semantic_sha256
        or manifest.get("review_input_sha256")
        != "28c386a2152bb180c92b7bacc4ab7ae1c43a9bfabdcd1301b5e09e1e8c077e51"
        or manifest.get("reviewed_packet_git_head_commit")
        != "b869f2bbe7166b3910f4e7602befe80b80fe7ddb"
        or manifest.get("usage") != usage
        or manifest.get("input_tokens_preflight")
        != HISTORICAL_V4_INPUT_TOKENS_PREFLIGHT
        or manifest.get("input_rate_usd_per_million") != 5.0
        or manifest.get("cache_write_rate_usd_per_million") != 6.25
        or manifest.get("output_rate_usd_per_million") != 30.0
        or manifest.get("completed_response_cost_usd_conservative")
        != HISTORICAL_V4_RECORDED_COST_USD
        or manifest.get("budget_authorization_usd")
        != HISTORICAL_V4_BUDGET_AUTHORIZATION_USD
        or not math.isclose(
            retrospective_long_context_cost,
            HISTORICAL_V4_RETROSPECTIVE_LONG_CONTEXT_COST_USD,
            abs_tol=1e-12,
        )
        or retrospective_long_context_cost > HISTORICAL_V4_BUDGET_AUTHORIZATION_USD
        or manifest.get("completed_response_cost_exceeded_budget_authorization")
        is not False
        or set(adjudication)
        != {
            "schema_version",
            "artifact_type",
            "status",
            "provider_review",
            "finding_ids",
            "resolved_or_nonblocking_findings",
            "remaining_blocking_findings",
            "execution_authorized",
            "replacement_review_authorized",
            "replacement_review_must_include_this_review",
            "target_outcomes_opened",
            "final_decision",
            "receipt_sha256",
        }
        or adjudication.get("schema_version") != 1
        or adjudication.get("artifact_type")
        != "completed_negative_provider_review_v4_adjudication"
        or adjudication.get("status")
        != "completed_review_not_ready_material_fix_required"
        or provider != expected_provider
        or adjudication.get("finding_ids") != expected_finding_ids
        or adjudication.get("resolved_or_nonblocking_findings")
        != [finding for finding in expected_finding_ids if finding != "B12"]
        or not isinstance(remaining, list)
        or len(remaining) != 1
        or not isinstance(remaining[0], Mapping)
        or set(remaining[0]) != {"id", "rationale"}
        or remaining[0].get("id") != "B12"
        or not isinstance(remaining[0].get("rationale"), str)
        or not remaining[0]["rationale"].strip()
        or adjudication.get("execution_authorized") is not False
        or adjudication.get("replacement_review_authorized") is not False
        or adjudication.get("replacement_review_must_include_this_review") is not True
        or adjudication.get("target_outcomes_opened") is not False
        or adjudication.get("final_decision") != "NOT_READY_TO_EXECUTE"
        or adjudication.get("receipt_sha256")
        != HISTORICAL_V4_NEGATIVE_ADJUDICATION_RECEIPT_SHA256
        or "Final execution decision: **NOT READY TO EXECUTE**."
        not in adjudication_markdown
    ):
        raise AuditRecoveryError("historical v4 completed negative review differs")
    return {
        "response_id": response["id"],
        "terminal_verdict": "NOT READY TO FREEZE",
        "review_sha256": _sha256(root / "review.md"),
        "response_file_sha256": _sha256(root / "response.json"),
        "response_semantic_sha256": response_semantic_sha256,
        "review_input_sha256": manifest["review_input_sha256"],
        "input_tokens": 1_129_614,
        "output_tokens": 27_987,
        "reasoning_tokens": 8_904,
        "reconstructed_cost_usd": HISTORICAL_V4_RECORDED_COST_USD,
        "input_tokens_preflight": HISTORICAL_V4_INPUT_TOKENS_PREFLIGHT,
        "recorded_cost_usd": HISTORICAL_V4_RECORDED_COST_USD,
        "retrospective_long_context_cost_usd": retrospective_long_context_cost,
        "budget_authorization_usd": HISTORICAL_V4_BUDGET_AUTHORIZATION_USD,
        "pricing_disclosure_status": (
            "historical_manifest_short_rate_plus_retrospective_long_context_"
            "reconstruction_not_invoice"
        ),
        "finding_ids": expected_finding_ids,
        "remaining_blocking_findings": ["B12"],
        "adjudication_receipt_sha256": adjudication["receipt_sha256"],
        "adjudication_json_sha256": _sha256(adjudication_path),
        "adjudication_markdown_sha256": _sha256(
            REPO_ROOT / HISTORICAL_V4_NEGATIVE_REVIEW_ADJUDICATION_MARKDOWN
        ),
    }


def _validate_v4_timed_qualification_evidence() -> dict[str, Any]:
    for relative, expected_sha256 in sorted(
        V4_TIMED_QUALIFICATION_PHYSICAL_SHA256.items()
    ):
        if _sha256(REPO_ROOT / relative) != expected_sha256:
            raise AuditRecoveryError("v4 timed qualification physical evidence differs")

    receipt = _canonical_json_receipt(
        REPO_ROOT / V4_TIMED_QUALIFICATION_RECEIPT_SNAPSHOT,
        "v4 timed qualification receipt",
    )
    ownership_raw = _canonical_json_receipt(
        REPO_ROOT / V4_TIMED_QUALIFICATION_OWNERSHIP_SNAPSHOT,
        "v4 timed qualification ownership",
    )
    guest_raw = _canonical_json_receipt(
        REPO_ROOT / V4_TIMED_QUALIFICATION_GUEST_SNAPSHOT,
        "v4 timed qualification guest",
    )
    cache_raw = _canonical_json_receipt(
        REPO_ROOT / V4_TIMED_QUALIFICATION_CACHE_SNAPSHOT,
        "v4 timed qualification cache",
    )
    landlock = _canonical_json_receipt(
        REPO_ROOT / V4_TIMED_QUALIFICATION_LANDLOCK_SNAPSHOT,
        "v4 timed qualification Landlock",
    )
    cuda = _canonical_json_receipt(
        REPO_ROOT / V4_TIMED_QUALIFICATION_CUDA_SNAPSHOT,
        "v4 timed qualification CUDA",
    )
    termination = _canonical_json_receipt(
        REPO_ROOT / V4_TIMED_QUALIFICATION_TERMINATION_AUDIT_SNAPSHOT,
        "v4 timed qualification termination audit",
    )
    try:
        ownership = runpod_preflight.validate_ownership_receipt(ownership_raw)
        guest = runpod_preflight.validate_guest_receipt(
            guest_raw, ownership_receipt=ownership
        )
        cache = runpod_preflight.validate_cache_receipt(
            cache_raw,
            guest_receipt=guest,
            ownership_receipt=ownership,
        )
    except runpod_preflight.PreflightError as exc:
        raise AuditRecoveryError(
            "v4 timed qualification support chain differs"
        ) from exc

    support_paths = {
        "ownership": V4_TIMED_QUALIFICATION_OWNERSHIP_SNAPSHOT,
        "guest": V4_TIMED_QUALIFICATION_GUEST_SNAPSHOT,
        "cache": V4_TIMED_QUALIFICATION_CACHE_SNAPSHOT,
        "landlock": V4_TIMED_QUALIFICATION_LANDLOCK_SNAPSHOT,
        "cuda": V4_TIMED_QUALIFICATION_CUDA_SNAPSHOT,
    }
    supports = {
        "ownership": ownership,
        "guest": guest,
        "cache": cache,
        "landlock": landlock,
        "cuda": cuda,
    }
    artifacts = receipt.get("artifacts")
    if not isinstance(artifacts, Mapping) or set(artifacts) != {
        *support_paths,
        "roots_manifest",
    }:
        raise AuditRecoveryError("v4 timed qualification artifact inventory differs")
    for name, relative in support_paths.items():
        row = artifacts.get(name)
        path = REPO_ROOT / relative
        if (
            not isinstance(row, Mapping)
            or set(row) != {"bytes", "sha256", "receipt_sha256"}
            or row.get("bytes") != path.stat().st_size
            or row.get("sha256") != V4_TIMED_QUALIFICATION_PHYSICAL_SHA256[relative]
            or row.get("receipt_sha256") != supports[name]["receipt_sha256"]
        ):
            raise AuditRecoveryError("v4 timed qualification support binding differs")

    gate = receipt.get("authorization_gate")
    rehash = receipt.get("public_artifact_rehash")
    outcome = receipt.get("outcome_blindness")
    provider = receipt.get("provider")
    scope = receipt.get("scope_limitation")
    sequence = receipt.get("sequence")
    confinement = receipt.get("confinement")
    lineage = receipt.get("lineage")
    old_qualification = _validate_qualification_ownership(
        REPO_ROOT / V3_TARGET_QUALIFICATION_OWNERSHIP_SNAPSHOT
    )
    expected_provider = {
        "created_at_utc": ownership["created_at"],
        "data_center_id": protocol.DATA_CENTER_ID,
        "gpu_count": 1,
        "gpu_type": protocol.GPU_TYPE,
        "hourly_price_usd": 5.89,
        "network_volume_id": protocol.NETWORK_VOLUME_ID,
        "pod_id": ownership["pod_id"],
        "pod_name": ownership["pod_name"],
    }
    if (
        receipt.get("schema_version") != 1
        or receipt.get("status") != "pass_authorization_ready_with_required_margin"
        or receipt.get("receipt_kind")
        != "outcome_blind_provider_creation_bound_timing_qualification_v1"
        or provider != expected_provider
        or ownership["pod_id"] == old_qualification["pod_id"]
        or not isinstance(rehash, Mapping)
        or rehash.get("file_count") != 45
        or rehash.get("total_bytes") != 156_023_372_845
        or rehash.get("inventory_sha256")
        != "326e85683c4302dea27824923fa9b550738edd40f89a70b6e0b780530c8e5a96"
        or rehash.get("independently_rehashed") is not True
        or cache.get("full_file_count") != rehash.get("file_count")
        or cache.get("full_retained_bytes") != rehash.get("total_bytes")
        or cache.get("full_file_inventory_sha256") != rehash.get("inventory_sha256")
        or gate
        != {
            "authorization_issued": False,
            "authorization_ready_host_age_seconds": 958,
            "gate_passed": True,
            "minimum_issue_remaining_seconds": 1800,
            "provider_creation_bound_window_seconds": 3600,
            "seconds_above_required_remaining_margin": 842,
            "seconds_remaining_at_authorization_ready": 2642,
        }
        or outcome
        != {
            "external_or_prior_outcome_inputs": [],
            "model_forward_count": 0,
            "target_feature_vector_count": 0,
            "target_prompt_render_count": 0,
            "torch_module_call_count": 0,
        }
        or not isinstance(scope, Mapping)
        or scope.get("cuda_preflight_closure_scope") != "source_test_qualification"
        or scope.get("cuda_preflight_closure_file_count") != 26
        or "distinct recovery pod must repeat the preflight with final_recovery closure"
        not in str(scope.get("statement", ""))
        or not isinstance(sequence, list)
        or [row.get("host_age_seconds") for row in sequence if isinstance(row, Mapping)]
        != [0, 491, 542, 708, 844, 942, 958]
        or not isinstance(lineage, Mapping)
        or lineage.get("ownership_receipt_sha256") != ownership["receipt_sha256"]
        or not isinstance(confinement, Mapping)
        or confinement.get("landlock_status") != "pass_landlock_enforced"
        or confinement.get("cuda_status") != "pass_target_free_landlock_cuda_preflight"
        or landlock.get("receipt_sha256") != cuda.get("landlock_receipt_sha256")
        or cuda.get("qualification_ownership_receipt_sha256")
        != ownership["receipt_sha256"]
        or cuda.get("closure_scope") != "source_test_qualification"
        or any(
            cuda.get(name) != expected
            for name, expected in {
                "model_forward_count": 0,
                "torch_module_call_count": 0,
                "target_prompt_render_count": 0,
                "target_feature_vector_count": 0,
                "external_or_prior_outcome_inputs": [],
            }.items()
        )
        or termination.get("status")
        != "deleted_exact_owned_pod_unrelated_inventory_unchanged"
        or termination.get("pod_id") != ownership["pod_id"]
        or termination.get("successor_ownership_receipt_sha256")
        != ownership["receipt_sha256"]
        or termination.get("precreate_inventory_sha256")
        != termination.get("postdelete_inventory_sha256")
    ):
        raise AuditRecoveryError("v4 timed qualification semantics differ")
    return {
        "pod_id": ownership["pod_id"],
        "receipt_sha256": receipt["receipt_sha256"],
        "termination_receipt_sha256": termination["receipt_sha256"],
        "authorization_ready_host_age_seconds": 958,
        "seconds_remaining_at_authorization_ready": 2642,
        "seconds_above_required_remaining_margin": 842,
        "public_artifact_file_count": 45,
        "public_artifact_total_bytes": 156_023_372_845,
        "cuda_preflight_closure_scope": "source_test_qualification",
        "final_recovery_scope_must_repeat": True,
        "files": [
            {"path": relative, "sha256": expected}
            for relative, expected in sorted(
                V4_TIMED_QUALIFICATION_PHYSICAL_SHA256.items()
            )
        ],
    }


def _snapshot_evidence_row(relative: str, value: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "path": relative,
        "file_sha256": _sha256(REPO_ROOT / relative),
        "receipt_sha256": value["receipt_sha256"],
    }


def _validate_historical_v5_positive_review_evidence(
    *, validate_git: bool = True
) -> dict[str, Any]:
    """Validate v5 as immutable prior evidence, never against current sources."""

    for relative, expected_sha256 in sorted(
        HISTORICAL_V5_POSITIVE_REVIEW_PHYSICAL_SHA256.items()
    ):
        if _sha256(REPO_ROOT / relative) != expected_sha256:
            raise AuditRecoveryError(
                "immutable historical v5 positive-review evidence differs"
            )

    root = REPO_ROOT / FINAL_V5_PRO_REVIEW_DIRECTORY
    response = _json(root / "response.json")
    manifest = _json(root / "review_manifest.json")
    review_text = (root / "review.md").read_text(encoding="utf-8")
    adjudication = _canonical_json_receipt(
        REPO_ROOT / FINAL_V5_PRO_REVIEW_ADJUDICATION_JSON,
        "historical v5 positive review adjudication",
    )
    usage = response.get("usage")
    response_semantic_sha256 = hashlib.sha256(
        json.dumps(response, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()
    review_binding = adjudication.get("review_binding")
    reviewed_evidence = adjudication.get("reviewed_qualification_evidence")
    reconstructed_cost = (
        float(usage.get("input_tokens", 0)) * 5.0 / 1_000_000
        + float(usage.get("input_tokens_details", {}).get("cache_write_tokens", 0))
        * 6.25
        / 1_000_000
        + float(usage.get("output_tokens", 0)) * 30.0 / 1_000_000
        if isinstance(usage, Mapping)
        else math.nan
    )
    retrospective_long_context_cost = (
        float(usage.get("input_tokens", 0))
        * PRO_REVIEW_V6_INPUT_RATE_USD_PER_MILLION
        / 1_000_000
        + float(usage.get("input_tokens_details", {}).get("cache_write_tokens", 0))
        * PRO_REVIEW_V6_CACHE_WRITE_RATE_USD_PER_MILLION
        / 1_000_000
        + float(usage.get("output_tokens", 0))
        * PRO_REVIEW_V6_OUTPUT_RATE_USD_PER_MILLION
        / 1_000_000
        if isinstance(usage, Mapping)
        else math.nan
    )
    if (
        _response_review_text(response) != review_text
        or _terminal_review_verdict(review_text) != "READY TO FREEZE"
        or _review_finding_ids(review_text) != list(HISTORICAL_V5_POSITIVE_FINDING_IDS)
        or response.get("id")
        != "resp_0322d12a79eb8aa5016a576d65fc94819ba2ed3994c7f8cbf0"
        or response.get("model") != "gpt-5.6-sol"
        or response.get("status") != "completed"
        or response.get("incomplete_details") not in (None, {})
        or not isinstance(usage, Mapping)
        or usage.get("input_tokens") != 1_379_762
        or usage.get("output_tokens") != 29_413
        or usage.get("output_tokens_details", {}).get("reasoning_tokens") != 7_256
        or response_semantic_sha256
        != "fba22e853ace030e60c6b789fb284eb859ef1308a14e2c979eb218628e8b81ca"
        or not math.isclose(
            reconstructed_cost, HISTORICAL_V5_RECORDED_COST_USD, abs_tol=1e-12
        )
        or not math.isclose(
            retrospective_long_context_cost,
            HISTORICAL_V5_RETROSPECTIVE_LONG_CONTEXT_COST_USD,
            abs_tol=1e-12,
        )
        or retrospective_long_context_cost > HISTORICAL_V5_BUDGET_AUTHORIZATION_USD
        or manifest.get("status") != "completed"
        or manifest.get("response_id") != response["id"]
        or manifest.get("review_sha256")
        != HISTORICAL_V5_POSITIVE_REVIEW_PHYSICAL_SHA256[
            f"{FINAL_V5_PRO_REVIEW_DIRECTORY}/review.md"
        ]
        or manifest.get("response_sha256") != response_semantic_sha256
        or manifest.get("review_input_sha256")
        != "414d79e21762cb77b67a5a300b38acb8dcdc595654d65a4eeccb3e33d7911a64"
        or manifest.get("review_instructions_sha256") != PRO_REVIEW_INSTRUCTIONS_SHA256
        or manifest.get("reviewed_packet_git_head_commit")
        != "df6af735260c884103e86d9d83ec251f87f07fb1"
        or manifest.get("input_tokens_preflight")
        != HISTORICAL_V5_INPUT_TOKENS_PREFLIGHT
        or manifest.get("input_rate_usd_per_million") != 5.0
        or manifest.get("cache_write_rate_usd_per_million") != 6.25
        or manifest.get("output_rate_usd_per_million") != 30.0
        or manifest.get("completed_response_cost_usd_conservative")
        != HISTORICAL_V5_RECORDED_COST_USD
        or manifest.get("budget_authorization_usd")
        != HISTORICAL_V5_BUDGET_AUTHORIZATION_USD
        or adjudication.get("schema_version") != 5
        or adjudication.get("artifact_type")
        != "completed_provider_review_v5_adjudication"
        or adjudication.get("final_decision") != "READY_TO_EXECUTE"
        or adjudication.get("finding_ids") != list(HISTORICAL_V5_POSITIVE_FINDING_IDS)
        or adjudication.get("receipt_sha256")
        != "05e23d2f90de9458b75ef7d84be23d73018ab8a4f46b3edcac12217793607257"
        or not isinstance(review_binding, Mapping)
        or review_binding.get("provider_response_id") != response["id"]
        or review_binding.get("provider_response_semantic_sha256")
        != response_semantic_sha256
        or review_binding.get("provider_review_sha256")
        != HISTORICAL_V5_POSITIVE_REVIEW_PHYSICAL_SHA256[
            f"{FINAL_V5_PRO_REVIEW_DIRECTORY}/review.md"
        ]
        or review_binding.get("code_freeze_commit")
        != "b0dd6fc9e098709e0301cc72aed3849208ab4f0a"
        or review_binding.get("reviewed_packet_git_head_commit")
        != "df6af735260c884103e86d9d83ec251f87f07fb1"
        or not isinstance(reviewed_evidence, Mapping)
        or reviewed_evidence.get("source_test_inventory_sha256")
        != "8c8ed32838bf47d68fd5b85306a9678d5df342b4387a9b5796d9d9c0e1027324"
    ):
        raise AuditRecoveryError("historical v5 positive review differs")
    if validate_git and (
        _git_command(
            "merge-base",
            "--is-ancestor",
            "b27a34fc617ab1ad3b58f6747da99f577dc048ca",
            _git_head(),
            check=False,
        ).returncode
        != 0
    ):
        raise AuditRecoveryError("historical v5 final commit is not an ancestor")
    return {
        "response_id": response["id"],
        "terminal_verdict": "READY TO FREEZE",
        "review_sha256": _sha256(root / "review.md"),
        "response_file_sha256": _sha256(root / "response.json"),
        "response_semantic_sha256": response_semantic_sha256,
        "review_input_sha256": manifest["review_input_sha256"],
        "input_tokens": 1_379_762,
        "output_tokens": 29_413,
        "reasoning_tokens": 7_256,
        "reconstructed_cost_usd": reconstructed_cost,
        "input_tokens_preflight": HISTORICAL_V5_INPUT_TOKENS_PREFLIGHT,
        "recorded_cost_usd": HISTORICAL_V5_RECORDED_COST_USD,
        "retrospective_long_context_cost_usd": retrospective_long_context_cost,
        "budget_authorization_usd": HISTORICAL_V5_BUDGET_AUTHORIZATION_USD,
        "pricing_disclosure_status": (
            "historical_manifest_short_rate_plus_retrospective_long_context_"
            "reconstruction_not_invoice"
        ),
        "finding_ids": list(HISTORICAL_V5_POSITIVE_FINDING_IDS),
        "code_freeze_commit": "b0dd6fc9e098709e0301cc72aed3849208ab4f0a",
        "reviewed_packet_git_head_commit": ("df6af735260c884103e86d9d83ec251f87f07fb1"),
        "final_git_head_commit": "b27a34fc617ab1ad3b58f6747da99f577dc048ca",
        "adjudication_receipt_sha256": adjudication["receipt_sha256"],
        "adjudication_json_sha256": _sha256(
            REPO_ROOT / FINAL_V5_PRO_REVIEW_ADJUDICATION_JSON
        ),
        "adjudication_markdown_sha256": _sha256(
            REPO_ROOT / FINAL_V5_PRO_REVIEW_ADJUDICATION_MARKDOWN
        ),
        "superseded_reason": "post_review_authentic_issue_gate_failed_b14",
    }


def _validate_historical_v6_nonadjudicable_review_evidence(
    *, validate_git: bool = True
) -> dict[str, Any]:
    """Validate the immutable READY v6 call without treating it as authorization."""

    for relative, expected_sha256 in sorted(
        HISTORICAL_V6_NONADJUDICABLE_REVIEW_PHYSICAL_SHA256.items()
    ):
        if _sha256(REPO_ROOT / relative) != expected_sha256:
            raise AuditRecoveryError(
                "immutable historical v6 non-adjudicable review evidence differs"
            )
    if (
        (REPO_ROOT / FINAL_V6_PRO_REVIEW_ADJUDICATION_JSON).exists()
        or (REPO_ROOT / FINAL_V6_PRO_REVIEW_ADJUDICATION_MARKDOWN).exists()
    ):
        raise AuditRecoveryError("historical v6 review acquired a fabricated adjudication")

    root = REPO_ROOT / FINAL_V6_PRO_REVIEW_DIRECTORY
    response = _json(root / "response.json")
    manifest = _json(root / "review_manifest.json")
    review_text = (root / "review.md").read_text(encoding="utf-8")
    usage = response.get("usage")
    response_semantic_sha256 = hashlib.sha256(
        json.dumps(response, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()
    heading_ids = _v6_review_finding_ids(review_text)
    prose_ids = _review_finding_ids(review_text)
    reconstructed_cost = (
        float(usage.get("input_tokens", 0))
        * PRO_REVIEW_V6_INPUT_RATE_USD_PER_MILLION
        / 1_000_000
        + float(usage.get("input_tokens_details", {}).get("cache_write_tokens", 0))
        * PRO_REVIEW_V6_CACHE_WRITE_RATE_USD_PER_MILLION
        / 1_000_000
        + float(usage.get("output_tokens", 0))
        * PRO_REVIEW_V6_OUTPUT_RATE_USD_PER_MILLION
        / 1_000_000
        if isinstance(usage, Mapping)
        else math.nan
    )
    if (
        _response_review_text(response) != review_text
        or _terminal_review_verdict(review_text) != "READY TO FREEZE"
        or heading_ids != list(HISTORICAL_V6_NONADJUDICABLE_FINDING_IDS)
        or "B05" not in prose_ids
        or "B05" in heading_ids
        or response.get("id")
        != "resp_096bfc4229fd22e6016a57992e0f648199913ca0849879a9a3"
        or response.get("model") != "gpt-5.6-sol"
        or response.get("status") != "completed"
        or response.get("incomplete_details") not in (None, {})
        or not isinstance(usage, Mapping)
        or usage.get("input_tokens") != 2_029_613
        or usage.get("output_tokens") != 31_829
        or usage.get("output_tokens_details", {}).get("reasoning_tokens") != 6_646
        or response_semantic_sha256
        != "f446ca5071f3b72cce4ddcca5f3bffccfaa89e62fcd2f14cb30ebc97af289364"
        or not math.isclose(reconstructed_cost, 21.728435, abs_tol=1e-12)
        or manifest.get("status") != "completed"
        or manifest.get("response_id") != response["id"]
        or manifest.get("review_sha256")
        != HISTORICAL_V6_NONADJUDICABLE_REVIEW_PHYSICAL_SHA256[
            f"{FINAL_V6_PRO_REVIEW_DIRECTORY}/review.md"
        ]
        or manifest.get("response_sha256") != response_semantic_sha256
        or manifest.get("review_input_sha256")
        != "9746b12f438015e2be4c3900561b360aa395169c98ae83c1385232e4d9b0edb5"
        or manifest.get("review_instructions_sha256") != PRO_REVIEW_INSTRUCTIONS_SHA256
        or manifest.get("reviewed_packet_git_head_commit")
        != "4e8752ebc89ff69924c1604022720cb5258cbbdd"
        or manifest.get("input_tokens_preflight") != 498_148
        or manifest.get("input_rate_usd_per_million")
        != PRO_REVIEW_V6_INPUT_RATE_USD_PER_MILLION
        or manifest.get("cache_write_rate_usd_per_million")
        != PRO_REVIEW_V6_CACHE_WRITE_RATE_USD_PER_MILLION
        or manifest.get("output_rate_usd_per_million")
        != PRO_REVIEW_V6_OUTPUT_RATE_USD_PER_MILLION
        or manifest.get("completed_response_cost_usd_conservative") != 21.728435
        or manifest.get("budget_authorization_usd")
        != PRO_REVIEW_BUDGET_AUTHORIZATION_USD
    ):
        raise AuditRecoveryError("historical v6 non-adjudicable review differs")
    if validate_git and (
        _git_command(
            "merge-base",
            "--is-ancestor",
            "4e8752ebc89ff69924c1604022720cb5258cbbdd",
            _git_head(),
            check=False,
        ).returncode
        != 0
    ):
        raise AuditRecoveryError("historical v6 reviewed commit is not an ancestor")
    return {
        "response_id": response["id"],
        "terminal_verdict": "READY TO FREEZE",
        "review_sha256": _sha256(root / "review.md"),
        "manifest_file_sha256": _sha256(root / "review_manifest.json"),
        "response_file_sha256": _sha256(root / "response.json"),
        "response_semantic_sha256": response_semantic_sha256,
        "request_payload_file_sha256": _sha256(root / "request_payload.json"),
        "review_request_file_sha256": _sha256(root / "review_request.md"),
        "review_input_sha256": manifest["review_input_sha256"],
        "reviewed_packet_git_head_commit": (
            "4e8752ebc89ff69924c1604022720cb5258cbbdd"
        ),
        "finding_ids": heading_ids,
        "input_tokens": 2_029_613,
        "output_tokens": 31_829,
        "reasoning_tokens": 6_646,
        "input_tokens_preflight": 498_148,
        "reconstructed_cost_usd": reconstructed_cost,
        "budget_authorization_usd": PRO_REVIEW_BUDGET_AUTHORIZATION_USD,
        "nonadjudicable_reason": (
            "b16_prose_wide_identifier_extraction_included_nonfinding_b05"
        ),
        "authorization_status": "historical_ready_verdict_nonadjudicable",
    }


def _validate_review_input_snapshots(
    expected_source_test_files: Sequence[Mapping[str, Any]],
    *,
    local_relative: str,
    target_relative: str,
    ownership_relative: str,
    landlock_relative: str,
    cuda_relative: str,
) -> dict[str, Any]:
    local_path = REPO_ROOT / local_relative
    target_path = REPO_ROOT / target_relative
    ownership_path = REPO_ROOT / ownership_relative
    landlock_path = REPO_ROOT / landlock_relative
    cuda_path = REPO_ROOT / cuda_relative
    local_value = _canonical_json_receipt(local_path, "reviewed local test receipt")
    target_value = _canonical_json_receipt(
        target_path, "reviewed target-host test receipt"
    )
    ownership = _canonical_json_receipt(
        ownership_path, "reviewed qualification ownership receipt"
    )
    landlock = _canonical_json_receipt(
        landlock_path, "reviewed qualification Landlock receipt"
    )
    cuda = _canonical_json_receipt(cuda_path, "reviewed qualification CUDA receipt")
    local = _validate_test_receipt(
        local_value,
        kind="local",
        expected_source_test_files=expected_source_test_files,
    )
    target = _validate_test_receipt(
        target_value,
        kind="target_host",
        expected_source_test_files=expected_source_test_files,
        qualification_ownership_path=ownership_path,
        qualification_landlock_path=landlock_path,
        qualification_cuda_path=cuda_path,
    )
    code_freeze = str(local["code_freeze_commit"])
    source_inventory_sha256 = protocol.canonical_sha256(
        list(expected_source_test_files)
    )
    if (
        target["code_freeze_commit"] != code_freeze
        or local["observed_git_head_commit"] != code_freeze
        or target["observed_git_head_commit"] != code_freeze
        or local["source_test_inventory_sha256"] != source_inventory_sha256
        or target["source_test_inventory_sha256"] != source_inventory_sha256
        or target["target_host"]["pod_id"] != ownership.get("pod_id")
    ):
        raise AuditRecoveryError("reviewed test-receipt snapshot chain differs")
    evidence = {
        "code_freeze_commit": code_freeze,
        "source_test_inventory_sha256": source_inventory_sha256,
        "local_test_receipt": _snapshot_evidence_row(local_relative, local),
        "target_host_test_receipt": _snapshot_evidence_row(target_relative, target),
        "target_qualification_ownership": _snapshot_evidence_row(
            ownership_relative, ownership
        ),
        "target_qualification_landlock": _snapshot_evidence_row(
            landlock_relative, landlock
        ),
        "target_qualification_cuda": _snapshot_evidence_row(cuda_relative, cuda),
    }
    return {"local": local, "target": target, "evidence": evidence}


def _validate_v6_review_input_snapshots(
    expected_source_test_files: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    return _validate_review_input_snapshots(
        expected_source_test_files,
        local_relative=V6_LOCAL_TEST_RECEIPT_SNAPSHOT,
        target_relative=V6_TARGET_HOST_TEST_RECEIPT_SNAPSHOT,
        ownership_relative=V6_TARGET_QUALIFICATION_OWNERSHIP_SNAPSHOT,
        landlock_relative=V6_TARGET_QUALIFICATION_LANDLOCK_SNAPSHOT,
        cuda_relative=V6_TARGET_QUALIFICATION_CUDA_SNAPSHOT,
    )


def _validate_v7_review_input_snapshots(
    expected_source_test_files: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    return _validate_review_input_snapshots(
        expected_source_test_files,
        local_relative=V7_LOCAL_TEST_RECEIPT_SNAPSHOT,
        target_relative=V7_TARGET_HOST_TEST_RECEIPT_SNAPSHOT,
        ownership_relative=V7_TARGET_QUALIFICATION_OWNERSHIP_SNAPSHOT,
        landlock_relative=V7_TARGET_QUALIFICATION_LANDLOCK_SNAPSHOT,
        cuda_relative=V7_TARGET_QUALIFICATION_CUDA_SNAPSHOT,
    )


def _validate_v8_review_input_snapshots(
    expected_source_test_files: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    return _validate_review_input_snapshots(
        expected_source_test_files,
        local_relative=V8_LOCAL_TEST_RECEIPT_SNAPSHOT,
        target_relative=V8_TARGET_HOST_TEST_RECEIPT_SNAPSHOT,
        ownership_relative=V8_TARGET_QUALIFICATION_OWNERSHIP_SNAPSHOT,
        landlock_relative=V8_TARGET_QUALIFICATION_LANDLOCK_SNAPSHOT,
        cuda_relative=V8_TARGET_QUALIFICATION_CUDA_SNAPSHOT,
    )


def _validate_v6_git_chain(
    *,
    code_freeze_commit: str,
    reviewed_packet_git_head_commit: str,
    final_git_head_commit: str,
) -> None:
    commits = (
        code_freeze_commit,
        reviewed_packet_git_head_commit,
        final_git_head_commit,
    )
    if any(HEX40.fullmatch(value) is None for value in commits):
        raise AuditRecoveryError("v6 review Git chain contains a malformed commit")
    for ancestor, descendant in zip(commits[:-1], commits[1:], strict=True):
        if (
            _git_command(
                "merge-base",
                "--is-ancestor",
                ancestor,
                descendant,
                check=False,
            ).returncode
            != 0
        ):
            raise AuditRecoveryError("v6 review Git chain is not C9<=E9<=F9")
    if (
        _git_command(
            "diff",
            "--quiet",
            code_freeze_commit,
            final_git_head_commit,
            "--",
            *SOURCE_TEST_BOUND_PATHS,
            check=False,
        ).returncode
        != 0
    ):
        raise AuditRecoveryError("source/test bytes changed after code freeze")
    packet_paths = [relative for relative, _role in PRO_REVIEW_V6_PACKET]
    if (
        _git_command(
            "diff",
            "--quiet",
            reviewed_packet_git_head_commit,
            final_git_head_commit,
            "--",
            *packet_paths,
            check=False,
        ).returncode
        != 0
    ):
        raise AuditRecoveryError("provider-reviewed packet bytes changed after review")


def _validate_v7_git_chain(
    *,
    code_freeze_commit: str,
    reviewed_packet_git_head_commit: str,
    final_git_head_commit: str,
) -> None:
    commits = (
        code_freeze_commit,
        reviewed_packet_git_head_commit,
        final_git_head_commit,
    )
    if any(HEX40.fullmatch(value) is None for value in commits):
        raise AuditRecoveryError("v7 review Git chain contains a malformed commit")
    for ancestor, descendant in zip(commits[:-1], commits[1:], strict=True):
        if (
            _git_command(
                "merge-base",
                "--is-ancestor",
                ancestor,
                descendant,
                check=False,
            ).returncode
            != 0
        ):
            raise AuditRecoveryError("v7 review Git chain is not C10<=E10<=F10")
    if (
        _git_command(
            "diff",
            "--quiet",
            code_freeze_commit,
            final_git_head_commit,
            "--",
            *SOURCE_TEST_BOUND_PATHS,
            check=False,
        ).returncode
        != 0
    ):
        raise AuditRecoveryError("source/test bytes changed after C10 code freeze")
    packet_paths = [relative for relative, _role in PRO_REVIEW_V7_PACKET]
    if (
        _git_command(
            "diff",
            "--quiet",
            reviewed_packet_git_head_commit,
            final_git_head_commit,
            "--",
            *packet_paths,
            check=False,
        ).returncode
        != 0
    ):
        raise AuditRecoveryError("v7 provider-reviewed packet bytes changed after review")


def _validate_v8_git_chain(
    *,
    code_freeze_commit: str,
    reviewed_packet_git_head_commit: str,
    final_git_head_commit: str,
) -> None:
    commits = (
        code_freeze_commit,
        reviewed_packet_git_head_commit,
        final_git_head_commit,
    )
    if any(HEX40.fullmatch(value) is None for value in commits):
        raise AuditRecoveryError("v8 review Git chain contains a malformed commit")
    for ancestor, descendant in zip(commits[:-1], commits[1:], strict=True):
        if (
            _git_command(
                "merge-base", "--is-ancestor", ancestor, descendant, check=False
            ).returncode
            != 0
        ):
            raise AuditRecoveryError("v8 review Git chain is not C11<=E11<=F11")
    if (
        _git_command(
            "diff",
            "--quiet",
            code_freeze_commit,
            final_git_head_commit,
            "--",
            *SOURCE_TEST_BOUND_PATHS,
            check=False,
        ).returncode
        != 0
    ):
        raise AuditRecoveryError("source/test bytes changed after C11 code freeze")
    packet_paths = [relative for relative, _role in PRO_REVIEW_V8_PACKET]
    if (
        _git_command(
            "diff",
            "--quiet",
            reviewed_packet_git_head_commit,
            final_git_head_commit,
            "--",
            *packet_paths,
            check=False,
        ).returncode
        != 0
    ):
        raise AuditRecoveryError("v8 provider-reviewed packet bytes changed after review")


def _validate_v5_review_adjudication(
    *,
    root: Path,
    response: Mapping[str, Any],
    response_semantic_sha256: str,
    review_sha256: str,
    review_input_sha256: str,
    finding_ids: Sequence[str],
    historical_v4: Mapping[str, Any],
    reviewed_evidence: Mapping[str, Any],
    reviewed_packet_git_head_commit: str,
) -> dict[str, Any]:
    json_path = REPO_ROOT / FINAL_V5_PRO_REVIEW_ADJUDICATION_JSON
    markdown_path = REPO_ROOT / FINAL_V5_PRO_REVIEW_ADJUDICATION_MARKDOWN
    value = _canonical_json_receipt(json_path, "final v5 review adjudication")
    receipt_sha256 = value["receipt_sha256"]
    markdown = markdown_path.read_text(encoding="utf-8")
    expected_review_binding = {
        "review_directory": FINAL_V5_PRO_REVIEW_DIRECTORY,
        "provider_response_id": response["id"],
        "provider_response_file_sha256": _sha256(root / "response.json"),
        "provider_response_semantic_sha256": response_semantic_sha256,
        "provider_review_sha256": review_sha256,
        "provider_manifest_file_sha256": _sha256(root / "review_manifest.json"),
        "request_payload_file_sha256": _sha256(root / "request_payload.json"),
        "review_request_file_sha256": _sha256(root / "review_request.md"),
        "review_input_sha256": review_input_sha256,
        "review_instructions_sha256": PRO_REVIEW_INSTRUCTIONS_SHA256,
        "reviewed_packet_git_head_commit": reviewed_packet_git_head_commit,
        "code_freeze_commit": reviewed_evidence["code_freeze_commit"],
        "adjudication_markdown_path": FINAL_V5_PRO_REVIEW_ADJUDICATION_MARKDOWN,
        "adjudication_markdown_sha256": _sha256(markdown_path),
    }
    expected_historical_binding = {
        "adjudication_path": HISTORICAL_V4_NEGATIVE_REVIEW_ADJUDICATION_JSON,
        "adjudication_file_sha256": historical_v4["adjudication_json_sha256"],
        "adjudication_receipt_sha256": historical_v4["adjudication_receipt_sha256"],
        "provider_response_id": historical_v4["response_id"],
        "terminal_verdict": historical_v4["terminal_verdict"],
        "remaining_blocking_findings": historical_v4["remaining_blocking_findings"],
    }
    if (
        set(value)
        != {
            "schema_version",
            "artifact_type",
            "review_binding",
            "historical_v4_binding",
            "reviewed_qualification_evidence",
            "finding_ids",
            "findings",
            "resolved_v4_remaining_findings",
            "final_decision",
            "receipt_sha256",
        }
        or value.get("schema_version") != 5
        or value.get("artifact_type") != "completed_provider_review_v5_adjudication"
        or value.get("review_binding") != expected_review_binding
        or value.get("historical_v4_binding") != expected_historical_binding
        or value.get("reviewed_qualification_evidence") != reviewed_evidence
        or value.get("finding_ids") != list(finding_ids)
        or value.get("resolved_v4_remaining_findings") != ["B12"]
        or value.get("final_decision") != "READY_TO_EXECUTE"
        or "Final execution decision: **READY TO EXECUTE**." not in markdown
    ):
        raise AuditRecoveryError("final v5 review adjudication binding differs")

    historical_ids = set(historical_v4["finding_ids"])
    if not historical_ids.issubset(finding_ids):
        raise AuditRecoveryError("final v5 review omitted a historical finding ID")
    for finding_id in set(finding_ids) - historical_ids:
        prefix = finding_id[0]
        number = int(finding_id[1:])
        if (prefix == "B" and number < 13) or (prefix == "I" and number < 9):
            raise AuditRecoveryError("final v5 review recycled a reserved finding ID")

    packet_paths = {relative for relative, _role in PRO_REVIEW_V5_PACKET}
    findings = value.get("findings")
    if not isinstance(findings, list) or len(findings) != len(finding_ids):
        raise AuditRecoveryError("final v5 adjudication finding rows differ")
    observed_ids: list[str] = []
    for row in findings:
        if not isinstance(row, Mapping) or set(row) != {
            "id",
            "blocking",
            "disposition",
            "rationale",
            "changed_paths",
        }:
            raise AuditRecoveryError("final v5 adjudication finding rows differ")
        finding_id = row.get("id")
        changed_paths = row.get("changed_paths")
        if (
            not isinstance(finding_id, str)
            or re.fullmatch(r"[BI][0-9]{2}", finding_id) is None
            or row.get("blocking") is not finding_id.startswith("B")
            or row.get("disposition") not in {"fixed", "rejected"}
            or not isinstance(row.get("rationale"), str)
            or not row["rationale"].strip()
            or not isinstance(changed_paths, list)
            or changed_paths != sorted(set(changed_paths))
            or any(not isinstance(path, str) for path in changed_paths)
            or not set(changed_paths).issubset(packet_paths)
            or (row["disposition"] == "rejected" and changed_paths)
            or (row["blocking"] and row["disposition"] == "fixed" and not changed_paths)
            or finding_id not in markdown
        ):
            raise AuditRecoveryError("final v5 adjudication finding rows differ")
        observed_ids.append(finding_id)
    if sorted(observed_ids) != list(finding_ids):
        raise AuditRecoveryError("final v5 adjudication finding rows differ")
    return {
        "receipt_sha256": receipt_sha256,
        "json_sha256": _sha256(json_path),
        "markdown_sha256": _sha256(markdown_path),
        "fixed_finding_ids": sorted(
            row["id"] for row in findings if row["disposition"] == "fixed"
        ),
        "rejected_finding_ids": sorted(
            row["id"] for row in findings if row["disposition"] == "rejected"
        ),
    }


def _validate_v6_review_adjudication(
    *,
    root: Path,
    response: Mapping[str, Any],
    response_semantic_sha256: str,
    review_sha256: str,
    review_input_sha256: str,
    finding_ids: Sequence[str],
    historical_v5: Mapping[str, Any],
    reviewed_evidence: Mapping[str, Any],
    reviewed_packet_git_head_commit: str,
) -> dict[str, Any]:
    json_path = REPO_ROOT / FINAL_V6_PRO_REVIEW_ADJUDICATION_JSON
    markdown_path = REPO_ROOT / FINAL_V6_PRO_REVIEW_ADJUDICATION_MARKDOWN
    value = _canonical_json_receipt(json_path, "final v6 review adjudication")
    markdown = markdown_path.read_text(encoding="utf-8")
    incident_path = (
        "docs/consciousness_sae_target_blind_calibration/"
        "AUDIT_RECOVERY_V6_PREGPU_INCIDENT.md"
    )
    expected_review_binding = {
        "review_directory": FINAL_V6_PRO_REVIEW_DIRECTORY,
        "provider_response_id": response["id"],
        "provider_response_file_sha256": _sha256(root / "response.json"),
        "provider_response_semantic_sha256": response_semantic_sha256,
        "provider_review_sha256": review_sha256,
        "provider_manifest_file_sha256": _sha256(root / "review_manifest.json"),
        "request_payload_file_sha256": _sha256(root / "request_payload.json"),
        "review_request_file_sha256": _sha256(root / "review_request.md"),
        "review_input_sha256": review_input_sha256,
        "review_instructions_sha256": PRO_REVIEW_INSTRUCTIONS_SHA256,
        "reviewed_packet_git_head_commit": reviewed_packet_git_head_commit,
        "code_freeze_commit": reviewed_evidence["code_freeze_commit"],
        "adjudication_markdown_path": FINAL_V6_PRO_REVIEW_ADJUDICATION_MARKDOWN,
        "adjudication_markdown_sha256": _sha256(markdown_path),
    }
    expected_historical_binding = {
        "review_directory": FINAL_V5_PRO_REVIEW_DIRECTORY,
        "provider_response_id": historical_v5["response_id"],
        "terminal_verdict": historical_v5["terminal_verdict"],
        "review_file_sha256": historical_v5["review_sha256"],
        "response_file_sha256": historical_v5["response_file_sha256"],
        "adjudication_path": FINAL_V5_PRO_REVIEW_ADJUDICATION_JSON,
        "adjudication_file_sha256": historical_v5["adjudication_json_sha256"],
        "adjudication_receipt_sha256": historical_v5["adjudication_receipt_sha256"],
        "code_freeze_commit": historical_v5["code_freeze_commit"],
        "reviewed_packet_git_head_commit": historical_v5[
            "reviewed_packet_git_head_commit"
        ],
        "superseded_reason": historical_v5["superseded_reason"],
        "input_tokens_preflight": historical_v5["input_tokens_preflight"],
        "recorded_cost_usd": historical_v5["recorded_cost_usd"],
        "retrospective_long_context_cost_usd": historical_v5[
            "retrospective_long_context_cost_usd"
        ],
        "budget_authorization_usd": historical_v5["budget_authorization_usd"],
        "pricing_disclosure_status": historical_v5["pricing_disclosure_status"],
    }
    expected_incident_binding = {
        "finding_ids": ["B14", "B15"],
        "path": incident_path,
        "file_sha256": _sha256(REPO_ROOT / incident_path),
        "historical_provenance_file_count": HISTORICAL_PROVENANCE_FILE_COUNT,
        "historical_provenance_inventory_sha256": (
            HISTORICAL_PROVENANCE_INVENTORY_SHA256
        ),
        "r3_requirements_sha256": (
            "4796c2817460bae757dcbae4c141bca460100fe80b13eb888776270d8df4b806"
        ),
        "r3_setup_sha256": (
            "f420180faf5c229439e4bf626ec05f5e9a10902508e62dbcef36f48abc1ab8fa"
        ),
        "superseded_c6_code_freeze_commit": (
            "57c4a6577309a5f112eec199d406c271df554c3a"
        ),
        "af_unix_path_max_bytes": AF_UNIX_PATH_MAX_BYTES,
        "af_unix_required_margin_bytes": AF_UNIX_PATH_REQUIRED_MARGIN_BYTES,
        "af_unix_path_budget_bytes": AF_UNIX_PATH_BUDGET_BYTES,
        "preflight_socket_path_bytes": 91,
        "execution_socket_path_bytes": 90,
    }
    if (
        set(value)
        != {
            "schema_version",
            "artifact_type",
            "review_binding",
            "historical_v5_binding",
            "incident_binding",
            "reviewed_qualification_evidence",
            "finding_ids",
            "findings",
            "resolved_pregpu_findings",
            "final_decision",
            "receipt_sha256",
        }
        or value.get("schema_version") != 6
        or value.get("artifact_type") != "completed_provider_review_v6_adjudication"
        or value.get("review_binding") != expected_review_binding
        or value.get("historical_v5_binding") != expected_historical_binding
        or value.get("incident_binding") != expected_incident_binding
        or value.get("reviewed_qualification_evidence") != reviewed_evidence
        or value.get("finding_ids") != list(finding_ids)
        or value.get("resolved_pregpu_findings") != ["B14", "B15"]
        or value.get("final_decision") != "READY_TO_EXECUTE"
        or "Final execution decision: **READY TO EXECUTE**." not in markdown
    ):
        raise AuditRecoveryError("final v6 review adjudication binding differs")

    required_ids = set(historical_v5["finding_ids"]) | {"B14", "B15"}
    if not required_ids.issubset(finding_ids):
        raise AuditRecoveryError("final v6 review omitted a cumulative finding ID")
    for finding_id in set(finding_ids) - required_ids:
        prefix = finding_id[0]
        number = int(finding_id[1:])
        if (prefix == "B" and number < 16) or (prefix == "I" and number < 10):
            raise AuditRecoveryError("final v6 review recycled a reserved finding ID")

    packet_paths = {relative for relative, _role in PRO_REVIEW_V6_PACKET}
    findings = value.get("findings")
    if not isinstance(findings, list) or len(findings) != len(finding_ids):
        raise AuditRecoveryError("final v6 adjudication finding rows differ")
    observed_ids: list[str] = []
    b14_row: Mapping[str, Any] | None = None
    b15_row: Mapping[str, Any] | None = None
    for row in findings:
        if not isinstance(row, Mapping) or set(row) != {
            "id",
            "blocking",
            "disposition",
            "rationale",
            "changed_paths",
        }:
            raise AuditRecoveryError("final v6 adjudication finding rows differ")
        finding_id = row.get("id")
        changed_paths = row.get("changed_paths")
        if (
            not isinstance(finding_id, str)
            or re.fullmatch(r"[BI][0-9]{2}", finding_id) is None
            or row.get("blocking") is not finding_id.startswith("B")
            or row.get("disposition") not in {"fixed", "rejected"}
            or not isinstance(row.get("rationale"), str)
            or not row["rationale"].strip()
            or not isinstance(changed_paths, list)
            or changed_paths != sorted(set(changed_paths))
            or any(not isinstance(path, str) for path in changed_paths)
            or not set(changed_paths).issubset(packet_paths)
            or (row["disposition"] == "rejected" and changed_paths)
            or (row["blocking"] and row["disposition"] == "fixed" and not changed_paths)
            or finding_id not in markdown
        ):
            raise AuditRecoveryError("final v6 adjudication finding rows differ")
        if finding_id == "B14":
            b14_row = row
        elif finding_id == "B15":
            b15_row = row
        observed_ids.append(finding_id)
    required_b14_paths = {
        "experiments/consciousness_sae_target_blind_calibration/"
        "requirements-runpod-b200.txt",
        "experiments/consciousness_sae_target_blind_calibration/setup_runpod_guest.sh",
        "experiments/consciousness_sae_target_blind_calibration/"
        "requirements-runpod-b200-qualification.txt",
        "experiments/consciousness_sae_target_blind_calibration/"
        "setup_runpod_qualification_guest.sh",
        "experiments/consciousness_sae_target_blind_calibration/audit_recovery.py",
        "tests/consciousness_sae_target_blind_calibration/test_audit_recovery.py",
    }
    required_b15_paths = {
        *C6_SUPERSEDED_QUALIFICATION_PHYSICAL_SHA256,
        incident_path,
        "docs/consciousness_sae_target_blind_calibration/AUDIT_RECOVERY_20260714.md",
        "docs/consciousness_sae_target_blind_calibration/"
        "AUDIT_RECOVERY_REVIEW_CONTEXT.md",
        "docs/consciousness_sae_target_blind_calibration/"
        "AUDIT_RECOVERY_SCIENTIFIC_EQUIVALENCE.json",
        "docs/consciousness_sae_target_blind_calibration/"
        "AUDIT_RECOVERY_SCIENTIFIC_EQUIVALENCE.md",
        "experiments/consciousness_sae_target_blind_calibration/audit_recovery.py",
        "experiments/consciousness_sae_target_blind_calibration/landlock_launcher.py",
        "experiments/consciousness_sae_target_blind_calibration/"
        "recovery_bundle_verifier.py",
        "tests/consciousness_sae_target_blind_calibration/test_audit_recovery.py",
        "tests/consciousness_sae_target_blind_calibration/test_landlock_launcher.py",
        "tests/consciousness_sae_target_blind_calibration/"
        "test_recovery_bundle_verifier.py",
    }
    if (
        sorted(observed_ids) != list(finding_ids)
        or not isinstance(b14_row, Mapping)
        or b14_row.get("disposition") != "fixed"
        or not required_b14_paths <= set(b14_row.get("changed_paths", []))
        or not isinstance(b15_row, Mapping)
        or b15_row.get("disposition") != "fixed"
        or not required_b15_paths <= set(b15_row.get("changed_paths", []))
    ):
        raise AuditRecoveryError("final v6 B14/B15 adjudication differs")
    return {
        "receipt_sha256": value["receipt_sha256"],
        "json_sha256": _sha256(json_path),
        "markdown_sha256": _sha256(markdown_path),
        "fixed_finding_ids": sorted(
            row["id"] for row in findings if row["disposition"] == "fixed"
        ),
        "rejected_finding_ids": sorted(
            row["id"] for row in findings if row["disposition"] == "rejected"
        ),
    }


def _validate_v7_review_adjudication(
    *,
    root: Path,
    response: Mapping[str, Any],
    response_semantic_sha256: str,
    review_sha256: str,
    review_input_sha256: str,
    finding_ids: Sequence[str],
    historical_v6: Mapping[str, Any],
    reviewed_evidence: Mapping[str, Any],
    reviewed_packet_git_head_commit: str,
) -> dict[str, Any]:
    json_path = REPO_ROOT / FINAL_V7_PRO_REVIEW_ADJUDICATION_JSON
    markdown_path = REPO_ROOT / FINAL_V7_PRO_REVIEW_ADJUDICATION_MARKDOWN
    value = _canonical_json_receipt(json_path, "final v7 review adjudication")
    markdown = markdown_path.read_text(encoding="utf-8")
    incident_path = (
        "docs/consciousness_sae_target_blind_calibration/"
        "AUDIT_RECOVERY_V7_POSTREVIEW_INCIDENT.md"
    )
    expected_review_binding = {
        "review_directory": FINAL_V7_PRO_REVIEW_DIRECTORY,
        "provider_response_id": response["id"],
        "provider_response_file_sha256": _sha256(root / "response.json"),
        "provider_response_semantic_sha256": response_semantic_sha256,
        "provider_review_sha256": review_sha256,
        "provider_manifest_file_sha256": _sha256(root / "review_manifest.json"),
        "request_payload_file_sha256": _sha256(root / "request_payload.json"),
        "review_request_file_sha256": _sha256(root / "review_request.md"),
        "review_input_sha256": review_input_sha256,
        "review_instructions_sha256": PRO_REVIEW_INSTRUCTIONS_SHA256,
        "reviewed_packet_git_head_commit": reviewed_packet_git_head_commit,
        "code_freeze_commit": reviewed_evidence["code_freeze_commit"],
        "adjudication_markdown_path": FINAL_V7_PRO_REVIEW_ADJUDICATION_MARKDOWN,
        "adjudication_markdown_sha256": _sha256(markdown_path),
    }
    expected_historical_binding = {
        "review_directory": FINAL_V6_PRO_REVIEW_DIRECTORY,
        "provider_response_id": historical_v6["response_id"],
        "terminal_verdict": historical_v6["terminal_verdict"],
        "review_file_sha256": historical_v6["review_sha256"],
        "manifest_file_sha256": historical_v6["manifest_file_sha256"],
        "response_file_sha256": historical_v6["response_file_sha256"],
        "response_semantic_sha256": historical_v6["response_semantic_sha256"],
        "request_payload_file_sha256": historical_v6[
            "request_payload_file_sha256"
        ],
        "review_request_file_sha256": historical_v6["review_request_file_sha256"],
        "reviewed_packet_git_head_commit": historical_v6[
            "reviewed_packet_git_head_commit"
        ],
        "finding_ids": historical_v6["finding_ids"],
        "nonadjudicable_reason": historical_v6["nonadjudicable_reason"],
        "authorization_status": historical_v6["authorization_status"],
    }
    expected_incident_binding = {
        "finding_ids": ["B16"],
        "path": incident_path,
        "file_sha256": _sha256(REPO_ROOT / incident_path),
        "historical_v6_provider_response_id": historical_v6["response_id"],
        "historical_v6_review_sha256": historical_v6["review_sha256"],
        "old_extraction_scope": "all_prose_word_boundary_identifier_tokens",
        "repaired_extraction_scope": "atx_headings_beginning_with_identifier",
    }
    if (
        set(value)
        != {
            "schema_version",
            "artifact_type",
            "review_binding",
            "historical_v6_binding",
            "incident_binding",
            "reviewed_qualification_evidence",
            "finding_ids",
            "findings",
            "resolved_postreview_findings",
            "final_decision",
            "receipt_sha256",
        }
        or value.get("schema_version") != 7
        or value.get("artifact_type") != "completed_provider_review_v7_adjudication"
        or value.get("review_binding") != expected_review_binding
        or value.get("historical_v6_binding") != expected_historical_binding
        or value.get("incident_binding") != expected_incident_binding
        or value.get("reviewed_qualification_evidence") != reviewed_evidence
        or value.get("finding_ids") != list(finding_ids)
        or value.get("resolved_postreview_findings") != ["B16"]
        or value.get("final_decision") != "READY_TO_EXECUTE"
        or "Final execution decision: **READY TO EXECUTE**." not in markdown
    ):
        raise AuditRecoveryError("final v7 review adjudication binding differs")

    required_ids = set(historical_v6["finding_ids"]) | {"B16"}
    if not required_ids.issubset(finding_ids):
        raise AuditRecoveryError("final v7 review omitted a cumulative finding ID")
    for finding_id in set(finding_ids) - required_ids:
        prefix = finding_id[0]
        number = int(finding_id[1:])
        if (prefix == "B" and number < 17) or (prefix == "I" and number < 10):
            raise AuditRecoveryError("final v7 review recycled a reserved finding ID")
    if any(
        finding_id.startswith("B") and int(finding_id[1:]) >= 17
        for finding_id in finding_ids
    ):
        raise AuditRecoveryError("final v7 review introduced a new blocker")

    packet_paths = {relative for relative, _role in PRO_REVIEW_V7_PACKET}
    findings = value.get("findings")
    if not isinstance(findings, list) or len(findings) != len(finding_ids):
        raise AuditRecoveryError("final v7 adjudication finding rows differ")
    observed_ids: list[str] = []
    b16_row: Mapping[str, Any] | None = None
    for row in findings:
        if not isinstance(row, Mapping) or set(row) != {
            "id",
            "blocking",
            "disposition",
            "rationale",
            "changed_paths",
        }:
            raise AuditRecoveryError("final v7 adjudication finding rows differ")
        finding_id = row.get("id")
        changed_paths = row.get("changed_paths")
        if (
            not isinstance(finding_id, str)
            or re.fullmatch(r"[BI][0-9]{2}", finding_id) is None
            or row.get("blocking") is not finding_id.startswith("B")
            or row.get("disposition") not in {"fixed", "rejected"}
            or not isinstance(row.get("rationale"), str)
            or not row["rationale"].strip()
            or not isinstance(changed_paths, list)
            or changed_paths != sorted(set(changed_paths))
            or any(not isinstance(path, str) for path in changed_paths)
            or not set(changed_paths).issubset(packet_paths)
            or (row["disposition"] == "rejected" and changed_paths)
            or (row["blocking"] and row["disposition"] == "fixed" and not changed_paths)
            or finding_id not in markdown
        ):
            raise AuditRecoveryError("final v7 adjudication finding rows differ")
        if finding_id == "B16":
            b16_row = row
        observed_ids.append(finding_id)
    required_b16_paths = {
        incident_path,
        "experiments/consciousness_sae_target_blind_calibration/audit_recovery.py",
        "experiments/consciousness_sae_target_blind_calibration/"
        "recovery_bundle_verifier.py",
        "tests/consciousness_sae_target_blind_calibration/test_audit_recovery.py",
        "tests/consciousness_sae_target_blind_calibration/"
        "test_recovery_bundle_verifier.py",
    }
    if (
        sorted(observed_ids) != list(finding_ids)
        or not isinstance(b16_row, Mapping)
        or b16_row.get("disposition") != "fixed"
        or not required_b16_paths <= set(b16_row.get("changed_paths", []))
    ):
        raise AuditRecoveryError("final v7 B16 adjudication differs")
    return {
        "receipt_sha256": value["receipt_sha256"],
        "json_sha256": _sha256(json_path),
        "markdown_sha256": _sha256(markdown_path),
        "fixed_finding_ids": sorted(
            row["id"] for row in findings if row["disposition"] == "fixed"
        ),
        "rejected_finding_ids": sorted(
            row["id"] for row in findings if row["disposition"] == "rejected"
        ),
    }


def _validate_v7_review_evidence_against_reviewed_tree(
    *,
    validate_git: bool = True,
    expected_final_git_head_commit: str | None = None,
) -> dict[str, Any]:
    """Regression-only validation of V7 against its exact F10 reviewed tree.

    Current V8 authorization never calls this helper: V7 is immutable history,
    not a review of successor source bytes. Tests substitute the exact F10 tree.
    """

    if not isinstance(validate_git, bool):
        raise AuditRecoveryError("review Git-validation mode differs")
    if (
        not validate_git
        and (
            not isinstance(expected_final_git_head_commit, str)
            or HEX40.fullmatch(expected_final_git_head_commit) is None
        )
    ):
        raise AuditRecoveryError("sealed final Git HEAD binding differs")
    if (
        HEX64.fullmatch(str(PRO_REVIEW_INSTRUCTIONS_SHA256)) is None
        or not isinstance(PRO_REVIEW_BUDGET_AUTHORIZATION_USD, (int, float))
        or isinstance(PRO_REVIEW_BUDGET_AUTHORIZATION_USD, bool)
        or not math.isfinite(float(PRO_REVIEW_BUDGET_AUTHORIZATION_USD))
        or float(PRO_REVIEW_BUDGET_AUTHORIZATION_USD) != 75.0
    ):
        raise AuditRecoveryError("prospective final-review settings are not frozen")
    if any(
        _sha256(REPO_ROOT / relative) != expected
        for relative, expected in C6_SUPERSEDED_QUALIFICATION_PHYSICAL_SHA256.items()
    ):
        raise AuditRecoveryError(
            "immutable superseded C6 qualification evidence differs"
        )
    if any(
        _sha256(REPO_ROOT / relative) != expected
        for relative, expected in C7_FAILED_QUALIFICATION_PHYSICAL_SHA256.items()
    ):
        raise AuditRecoveryError("immutable failed C7 qualification evidence differs")
    _validate_historical_incomplete_review_evidence()
    historical_v2 = _validate_historical_v2_review_evidence()
    historical_v3 = _validate_historical_v3_negative_review_evidence()
    historical_v4 = _validate_historical_v4_negative_review_evidence()
    historical_v5 = _validate_historical_v5_positive_review_evidence(
        validate_git=validate_git
    )
    historical_v6 = _validate_historical_v6_nonadjudicable_review_evidence(
        validate_git=validate_git
    )
    timed_qualification = _validate_v4_timed_qualification_evidence()
    source_test_files = _source_test_records()
    snapshots = _validate_v7_review_input_snapshots(source_test_files)
    reviewed_evidence = {
        **snapshots["evidence"],
        "timed_qualification": timed_qualification,
    }
    adjudication_value = _canonical_json_receipt(
        REPO_ROOT / FINAL_V7_PRO_REVIEW_ADJUDICATION_JSON,
        "final v7 review adjudication",
    )
    review_binding = adjudication_value.get("review_binding")
    reviewed_packet_git_head_commit = (
        str(review_binding.get("reviewed_packet_git_head_commit", ""))
        if isinstance(review_binding, Mapping)
        else ""
    )
    if HEX40.fullmatch(reviewed_packet_git_head_commit) is None:
        raise AuditRecoveryError("reviewed packet Git commit differs")

    root = REPO_ROOT / FINAL_V7_PRO_REVIEW_DIRECTORY
    response = _json(root / "response.json")
    manifest = _json(root / "review_manifest.json")
    payload = _json(root / "request_payload.json")
    review_text = (root / "review.md").read_text(encoding="utf-8")
    review_sha256 = hashlib.sha256(review_text.encode("utf-8")).hexdigest()
    response_semantic_sha256 = hashlib.sha256(
        json.dumps(response, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()
    expected_review_input = _expected_v7_pro_review_input()
    review_input_sha256 = hashlib.sha256(
        expected_review_input.encode("utf-8")
    ).hexdigest()
    instructions = payload.get("instructions")
    if not isinstance(instructions, str):
        raise AuditRecoveryError("final v6 review instructions are absent")
    limits = _validate_v7_packet_limits(instructions, expected_review_input)
    if (
        hashlib.sha256(instructions.encode("utf-8")).hexdigest()
        != PRO_REVIEW_INSTRUCTIONS_SHA256
    ):
        raise AuditRecoveryError("final v7 review instructions differ")

    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, list) or len(artifacts) != len(PRO_REVIEW_V7_PACKET):
        raise AuditRecoveryError("final v7 review packet inventory differs")
    # Artifact bodies may themselves contain delimiter-shaped text. Bind them
    # through the manifest rows here and the full payload equality below rather
    # than reparsing the generated review input with delimiter searches.
    for row, (relative, role) in zip(artifacts, PRO_REVIEW_V7_PACKET, strict=True):
        if not isinstance(row, Mapping):
            raise AuditRecoveryError("final v7 review packet inventory differs")
        current_path = REPO_ROOT / relative
        current_raw = current_path.read_bytes()
        current_source = current_raw.decode("utf-8")
        row_path = PurePosixPath(str(row.get("path", ""))).as_posix()
        if (
            set(row) != {"path", "role", "bytes", "characters", "sha256"}
            or not (row_path == relative or row_path.endswith(f"/{relative}"))
            or row.get("role") != role
        ):
            raise AuditRecoveryError("final v7 review packet inventory differs")
        if (
            row.get("bytes") != len(current_raw)
            or row.get("characters") != len(current_source)
            or row.get("sha256") != hashlib.sha256(current_raw).hexdigest()
        ):
            raise AuditRecoveryError("provider-reviewed packet bytes differ")

    expected_metadata = {
        "workflow": "experiment_plan_review",
        "plan_sha256": artifacts[0]["sha256"],
        "review_input_sha256": review_input_sha256,
        "review_instructions_sha256": PRO_REVIEW_INSTRUCTIONS_SHA256,
        "single_call_policy": "trusted_procedural_rule",
        "reviewed_packet_git_head_commit": reviewed_packet_git_head_commit,
    }
    expected_request = (
        "# Developer instructions\n\n"
        + instructions.rstrip()
        + "\n\n"
        + expected_review_input
    )
    response_reasoning = response.get("reasoning")
    response_text = response.get("text")
    response_prompt_cache = response.get("prompt_cache_options")
    usage = response.get("usage")
    if (
        payload.get("input") != expected_review_input
        or payload.get("metadata") != expected_metadata
        or payload.get("model") != "gpt-5.6-sol"
        or payload.get("reasoning") != {"mode": "pro", "effort": "medium"}
        or payload.get("max_output_tokens") != PRO_REVIEW_MAX_OUTPUT_TOKENS
        or payload.get("service_tier") != "default"
        or payload.get("tools") != []
        or payload.get("store") is not False
        or payload.get("truncation") != "disabled"
        or payload.get("prompt_cache_options") != {"mode": "explicit"}
        or payload.get("text") != {"verbosity": "high"}
        or payload.get("background", False) is not False
        or response.get("metadata") != expected_metadata
        or response.get("instructions") != instructions
        or not isinstance(response_reasoning, Mapping)
        or response_reasoning.get("mode") != "pro"
        or response_reasoning.get("effort") != "medium"
        or response.get("max_output_tokens") != PRO_REVIEW_MAX_OUTPUT_TOKENS
        or response.get("service_tier") != "default"
        or response.get("tools") != []
        or response.get("store") is not False
        or response.get("truncation") != "disabled"
        or not isinstance(response_text, Mapping)
        or response_text.get("verbosity") != "high"
        or not isinstance(response_prompt_cache, Mapping)
        or response_prompt_cache.get("mode") != "explicit"
        or response.get("prompt_cache_key") is not None
        or response.get("background") is not False
        or (root / "review_request.md").read_text(encoding="utf-8") != expected_request
        or _response_review_text(response) != review_text
        or not isinstance(usage, Mapping)
    ):
        raise AuditRecoveryError("final v7 provider packet binding differs")
    response_id = response.get("id")
    preflight_tokens = manifest.get("input_tokens_preflight")
    exact_reserved_cost = manifest.get("exact_budget_reserve_usd_after_preflight")
    expected_exact_reserved_cost = (
        (
            math.ceil(preflight_tokens * PRO_REVIEW_INPUT_RESERVE_MULTIPLIER)
            * (
                PRO_REVIEW_V6_INPUT_RATE_USD_PER_MILLION
                + PRO_REVIEW_V6_CACHE_WRITE_RATE_USD_PER_MILLION
            )
            + math.ceil(
                PRO_REVIEW_MAX_OUTPUT_TOKENS * PRO_REVIEW_OUTPUT_RESERVE_MULTIPLIER
            )
            * PRO_REVIEW_V6_OUTPUT_RATE_USD_PER_MILLION
        )
        / 1_000_000
        if isinstance(preflight_tokens, int) and not isinstance(preflight_tokens, bool)
        else math.nan
    )
    if (
        not isinstance(response_id, str)
        or not response_id.startswith("resp_")
        or response.get("model") != "gpt-5.6-sol"
        or response.get("status") != "completed"
        or response.get("incomplete_details") not in (None, {})
        or not isinstance(usage.get("input_tokens"), int)
        or usage["input_tokens"] <= 0
        or not isinstance(usage.get("output_tokens"), int)
        or usage["output_tokens"] <= 0
        or manifest.get("status") != "completed"
        or manifest.get("model") != "gpt-5.6-sol"
        or manifest.get("official_latest_model") != "gpt-5.6-sol"
        or manifest.get("response_id") != response_id
        or manifest.get("response_model") != "gpt-5.6-sol"
        or manifest.get("review_sha256") != review_sha256
        or manifest.get("response_sha256") != response_semantic_sha256
        or manifest.get("response_metadata") != expected_metadata
        or manifest.get("reviewed_packet_git_head_commit")
        != reviewed_packet_git_head_commit
        or manifest.get("review_instructions_sha256") != PRO_REVIEW_INSTRUCTIONS_SHA256
        or manifest.get("review_input_sha256") != review_input_sha256
        or manifest.get("review_request_sha256") != _sha256(root / "review_request.md")
        or manifest.get("request_payload_sha256")
        != _sha256(root / "request_payload.json")
        or manifest.get("single_call_policy") != "trusted_procedural_rule"
        or manifest.get("reasoning") != {"mode": "pro", "effort": "medium"}
        or manifest.get("store") is not False
        or manifest.get("background") is not False
        or manifest.get("service_tier") != "default"
        or manifest.get("max_input_characters") != PRO_REVIEW_MAX_INPUT_CHARACTERS
        or manifest.get("max_input_tokens") != PRO_REVIEW_MAX_INPUT_TOKENS
        or manifest.get("max_output_tokens") != PRO_REVIEW_MAX_OUTPUT_TOKENS
        or manifest.get("actual_input_characters") != limits["actual_input_characters"]
        or manifest.get("estimated_input_tokens_conservative")
        != limits["estimated_input_tokens_conservative"]
        or manifest.get("pro_input_reserve_multiplier")
        != PRO_REVIEW_INPUT_RESERVE_MULTIPLIER
        or manifest.get("reserved_billable_input_tokens")
        != limits["reserved_billable_input_tokens"]
        or manifest.get("pro_output_reserve_multiplier")
        != PRO_REVIEW_OUTPUT_RESERVE_MULTIPLIER
        or manifest.get("reserved_billable_output_tokens")
        != limits["reserved_billable_output_tokens"]
        or manifest.get("chars_per_token_assumption")
        != PRO_REVIEW_CHARS_PER_TOKEN_ASSUMPTION
        or manifest.get("input_rate_usd_per_million")
        != PRO_REVIEW_V6_INPUT_RATE_USD_PER_MILLION
        or manifest.get("cache_write_rate_usd_per_million")
        != PRO_REVIEW_V6_CACHE_WRITE_RATE_USD_PER_MILLION
        or manifest.get("output_rate_usd_per_million")
        != PRO_REVIEW_V6_OUTPUT_RATE_USD_PER_MILLION
        or not math.isclose(
            float(manifest.get("estimated_budget_reserve_usd", math.nan)),
            float(limits["estimated_budget_reserve_usd"]),
            abs_tol=1e-12,
        )
        or manifest.get("budget_authorization_usd")
        != PRO_REVIEW_BUDGET_AUTHORIZATION_USD
        or not isinstance(preflight_tokens, int)
        or isinstance(preflight_tokens, bool)
        or not 0 < preflight_tokens <= PRO_REVIEW_MAX_INPUT_TOKENS
        or not isinstance(exact_reserved_cost, (int, float))
        or isinstance(exact_reserved_cost, bool)
        or not math.isfinite(float(exact_reserved_cost))
        or not math.isclose(
            float(exact_reserved_cost),
            expected_exact_reserved_cost,
            abs_tol=1e-12,
        )
        or float(exact_reserved_cost) > PRO_REVIEW_BUDGET_AUTHORIZATION_USD
        or not isinstance(manifest.get("input_tokens_preflight_at_utc"), str)
        or manifest.get("completed_response_cost_exceeded_budget_authorization")
        is not False
    ):
        raise AuditRecoveryError("final v7 review evidence differs")

    required_sections = (
        "# Verdict",
        "# Blocking findings",
        "# Important non-blocking findings",
        "# What should remain unchanged",
        "# Minimal revised design",
        "# Freeze checklist",
    )
    terminal_verdict = _terminal_review_verdict(review_text)
    if (
        any(section not in review_text for section in required_sections)
        or terminal_verdict != "READY TO FREEZE"
    ):
        raise AuditRecoveryError("final v7 review did not approve exact packet bytes")
    finding_ids = _v6_review_finding_ids(review_text)
    adjudication = _validate_v7_review_adjudication(
        root=root,
        response=response,
        response_semantic_sha256=response_semantic_sha256,
        review_sha256=review_sha256,
        review_input_sha256=review_input_sha256,
        finding_ids=finding_ids,
        historical_v6=historical_v6,
        reviewed_evidence=reviewed_evidence,
        reviewed_packet_git_head_commit=reviewed_packet_git_head_commit,
    )
    final_head = (
        _git_head() if validate_git else str(expected_final_git_head_commit)
    )
    if (
        expected_final_git_head_commit is not None
        and final_head != expected_final_git_head_commit
    ):
        raise AuditRecoveryError("sealed final Git HEAD binding differs")
    if validate_git:
        _validate_v7_git_chain(
            code_freeze_commit=reviewed_evidence["code_freeze_commit"],
            reviewed_packet_git_head_commit=reviewed_packet_git_head_commit,
            final_git_head_commit=final_head,
        )

    reconstructed_cost = (
        float(usage["input_tokens"])
        * PRO_REVIEW_V6_INPUT_RATE_USD_PER_MILLION
        / 1_000_000
        + float(usage.get("input_tokens_details", {}).get("cache_write_tokens", 0))
        * PRO_REVIEW_V6_CACHE_WRITE_RATE_USD_PER_MILLION
        / 1_000_000
        + float(usage["output_tokens"])
        * PRO_REVIEW_V6_OUTPUT_RATE_USD_PER_MILLION
        / 1_000_000
    )
    recorded_cost = manifest.get("completed_response_cost_usd_conservative")
    if (
        not isinstance(recorded_cost, (int, float))
        or isinstance(recorded_cost, bool)
        or not math.isclose(reconstructed_cost, float(recorded_cost), abs_tol=1e-12)
        or reconstructed_cost > PRO_REVIEW_BUDGET_AUTHORIZATION_USD
    ):
        raise AuditRecoveryError("final v7 review cost reconstruction differs")

    evidence = reviewed_evidence
    return {
        "model": "gpt-5.6-sol",
        "provider_status": "completed",
        "provider_terminal_verdict": terminal_verdict,
        "response_id": response_id,
        "input_tokens": usage["input_tokens"],
        "output_tokens": usage["output_tokens"],
        "reasoning_tokens": usage.get("output_tokens_details", {}).get(
            "reasoning_tokens"
        ),
        "reconstructed_cost_usd": reconstructed_cost,
        "provider_approval_claimed": False,
        "provider_ready_to_freeze_verdict": True,
        "source_and_tests_reviewed_by_provider": True,
        "reviewed_packet_was_pre_fix": False,
        "final_source_reviewed_by_provider": True,
        "provider_reviewed_final_bytes_unchanged": True,
        "reviewed_packet_git_head_commit": reviewed_packet_git_head_commit,
        "final_git_head_commit": final_head,
        "code_freeze_commit": evidence["code_freeze_commit"],
        "source_test_inventory_sha256": evidence["source_test_inventory_sha256"],
        "historical_v2_terminal_verdict": historical_v2["terminal_verdict"],
        "historical_v2_adjudication_receipt_sha256": historical_v2[
            "adjudication_receipt_sha256"
        ],
        "historical_v2_remaining_blocking_findings": historical_v2[
            "remaining_blocking_findings"
        ],
        "historical_v3_terminal_verdict": historical_v3["terminal_verdict"],
        "historical_v3_adjudication_receipt_sha256": historical_v3[
            "adjudication_receipt_sha256"
        ],
        "historical_v3_remaining_blocking_findings": historical_v3[
            "remaining_blocking_findings"
        ],
        "historical_v4_terminal_verdict": historical_v4["terminal_verdict"],
        "historical_v4_adjudication_receipt_sha256": historical_v4[
            "adjudication_receipt_sha256"
        ],
        "historical_v4_remaining_blocking_findings": historical_v4[
            "remaining_blocking_findings"
        ],
        "historical_v4_input_tokens_preflight": historical_v4["input_tokens_preflight"],
        "historical_v4_recorded_cost_usd": historical_v4["recorded_cost_usd"],
        "historical_v4_retrospective_long_context_cost_usd": historical_v4[
            "retrospective_long_context_cost_usd"
        ],
        "historical_v4_budget_authorization_usd": historical_v4[
            "budget_authorization_usd"
        ],
        "historical_v4_pricing_disclosure_status": historical_v4[
            "pricing_disclosure_status"
        ],
        "historical_v5_terminal_verdict": historical_v5["terminal_verdict"],
        "historical_v5_response_id": historical_v5["response_id"],
        "historical_v5_review_sha256": historical_v5["review_sha256"],
        "historical_v5_adjudication_receipt_sha256": historical_v5[
            "adjudication_receipt_sha256"
        ],
        "historical_v5_adjudication_json_sha256": historical_v5[
            "adjudication_json_sha256"
        ],
        "historical_v5_superseded_reason": historical_v5["superseded_reason"],
        "historical_v5_input_tokens_preflight": historical_v5["input_tokens_preflight"],
        "historical_v5_recorded_cost_usd": historical_v5["recorded_cost_usd"],
        "historical_v5_retrospective_long_context_cost_usd": historical_v5[
            "retrospective_long_context_cost_usd"
        ],
        "historical_v5_budget_authorization_usd": historical_v5[
            "budget_authorization_usd"
        ],
        "historical_v5_pricing_disclosure_status": historical_v5[
            "pricing_disclosure_status"
        ],
        "historical_v6_terminal_verdict": historical_v6["terminal_verdict"],
        "historical_v6_response_id": historical_v6["response_id"],
        "historical_v6_review_sha256": historical_v6["review_sha256"],
        "historical_v6_manifest_file_sha256": historical_v6[
            "manifest_file_sha256"
        ],
        "historical_v6_response_file_sha256": historical_v6[
            "response_file_sha256"
        ],
        "historical_v6_request_payload_file_sha256": historical_v6[
            "request_payload_file_sha256"
        ],
        "historical_v6_review_request_file_sha256": historical_v6[
            "review_request_file_sha256"
        ],
        "historical_v6_reviewed_packet_git_head_commit": historical_v6[
            "reviewed_packet_git_head_commit"
        ],
        "historical_v6_nonadjudicable_reason": historical_v6[
            "nonadjudicable_reason"
        ],
        "historical_v6_authorization_status": historical_v6[
            "authorization_status"
        ],
        "timed_qualification_receipt_sha256": timed_qualification["receipt_sha256"],
        "timed_qualification_termination_receipt_sha256": timed_qualification[
            "termination_receipt_sha256"
        ],
        "timed_qualification_pod_id": timed_qualification["pod_id"],
        "timed_qualification_authorization_ready_host_age_seconds": (
            timed_qualification["authorization_ready_host_age_seconds"]
        ),
        "timed_qualification_seconds_remaining": timed_qualification[
            "seconds_remaining_at_authorization_ready"
        ],
        "timed_qualification_reserve_surplus_seconds": timed_qualification[
            "seconds_above_required_remaining_margin"
        ],
        "timed_qualification_public_artifact_file_count": timed_qualification[
            "public_artifact_file_count"
        ],
        "timed_qualification_public_artifact_total_bytes": timed_qualification[
            "public_artifact_total_bytes"
        ],
        "timed_qualification_cuda_preflight_closure_scope": timed_qualification[
            "cuda_preflight_closure_scope"
        ],
        "timed_qualification_final_recovery_scope_must_repeat": (
            timed_qualification["final_recovery_scope_must_repeat"]
        ),
        "finding_ids": finding_ids,
        "review_sha256": review_sha256,
        "adjudication_receipt_sha256": adjudication["receipt_sha256"],
        "adjudication_json_sha256": adjudication["json_sha256"],
        "adjudication_markdown_sha256": adjudication["markdown_sha256"],
        "fixed_finding_ids": adjudication["fixed_finding_ids"],
        "rejected_finding_ids": adjudication["rejected_finding_ids"],
        "reviewed_local_test_receipt_file_sha256": evidence["local_test_receipt"][
            "file_sha256"
        ],
        "reviewed_local_test_receipt_receipt_sha256": evidence["local_test_receipt"][
            "receipt_sha256"
        ],
        "reviewed_target_host_test_receipt_file_sha256": evidence[
            "target_host_test_receipt"
        ]["file_sha256"],
        "reviewed_target_host_test_receipt_receipt_sha256": evidence[
            "target_host_test_receipt"
        ]["receipt_sha256"],
        "reviewed_target_qualification_ownership_file_sha256": evidence[
            "target_qualification_ownership"
        ]["file_sha256"],
        "reviewed_target_qualification_ownership_receipt_sha256": evidence[
            "target_qualification_ownership"
        ]["receipt_sha256"],
        "reviewed_target_qualification_landlock_file_sha256": evidence[
            "target_qualification_landlock"
        ]["file_sha256"],
        "reviewed_target_qualification_landlock_receipt_sha256": evidence[
            "target_qualification_landlock"
        ]["receipt_sha256"],
        "reviewed_target_qualification_cuda_file_sha256": evidence[
            "target_qualification_cuda"
        ]["file_sha256"],
        "reviewed_target_qualification_cuda_receipt_sha256": evidence[
            "target_qualification_cuda"
        ]["receipt_sha256"],
        "historical_pre_v2_paid_call_count": 2,
        "historical_v2_paid_call_count": 1,
        "historical_v3_paid_call_count": 1,
        "historical_v4_paid_call_count": 1,
        "completed_v5_paid_call_count": 1,
        "completed_v6_paid_call_count": 1,
        "completed_v7_paid_call_count": 1,
        "cumulative_disclosed_paid_call_count": 8,
    }


def _validate_historical_v7_positive_review_evidence(
    *, validate_git: bool = True
) -> dict[str, Any]:
    """Validate V7 as immutable prior evidence, never against V8 sources."""

    for relative, expected in sorted(
        HISTORICAL_V7_POSITIVE_REVIEW_PHYSICAL_SHA256.items()
    ):
        if _sha256(REPO_ROOT / relative) != expected:
            raise AuditRecoveryError("immutable historical v7 review evidence differs")
    root = REPO_ROOT / FINAL_V7_PRO_REVIEW_DIRECTORY
    response = _json(root / "response.json")
    manifest = _json(root / "review_manifest.json")
    review_text = (root / "review.md").read_text(encoding="utf-8")
    adjudication = _canonical_json_receipt(
        REPO_ROOT / FINAL_V7_PRO_REVIEW_ADJUDICATION_JSON,
        "historical v7 positive review adjudication",
    )
    usage = response.get("usage")
    response_semantic_sha256 = hashlib.sha256(
        json.dumps(response, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()
    if (
        _response_review_text(response) != review_text
        or _terminal_review_verdict(review_text) != "READY TO FREEZE"
        or _v6_review_finding_ids(review_text)
        != list(HISTORICAL_V7_POSITIVE_FINDING_IDS)
        or response.get("id")
        != "resp_0162174969ec5bcb016a57a36b0030819ba940698d372c5f40"
        or response.get("model") != "gpt-5.6-sol"
        or response.get("status") != "completed"
        or response.get("incomplete_details") not in (None, {})
        or response_semantic_sha256
        != "abc1ab4dfeb228c009a0e049816e63d426d0c30c7e5195a217bfc3bc69903aa7"
        or not isinstance(usage, Mapping)
        or usage.get("input_tokens") != 1_865_304
        or usage.get("output_tokens") != 31_051
        or usage.get("output_tokens_details", {}).get("reasoning_tokens") != 4_487
        or manifest.get("status") != "completed"
        or manifest.get("response_id") != response["id"]
        or manifest.get("review_sha256")
        != HISTORICAL_V7_POSITIVE_REVIEW_PHYSICAL_SHA256[
            f"{FINAL_V7_PRO_REVIEW_DIRECTORY}/review.md"
        ]
        or manifest.get("response_sha256") != response_semantic_sha256
        or manifest.get("review_input_sha256")
        != "ee4f9dd505aae58d22e10b1b41c9617cfb07d6473f94b4bc2cfc2dbbd196c9fc"
        or manifest.get("review_instructions_sha256")
        != PRO_REVIEW_INSTRUCTIONS_SHA256
        or manifest.get("reviewed_packet_git_head_commit")
        != "cc519e2c7545e19aafb929b98dfd2958c136a25b"
        or manifest.get("input_tokens_preflight") != 457_302
        or manifest.get("completed_response_cost_usd_conservative") != 20.050335
        or manifest.get("budget_authorization_usd") != 75.0
        or adjudication.get("schema_version") != 7
        or adjudication.get("artifact_type")
        != "completed_provider_review_v7_adjudication"
        or adjudication.get("final_decision") != "READY_TO_EXECUTE"
        or adjudication.get("finding_ids")
        != list(HISTORICAL_V7_POSITIVE_FINDING_IDS)
        or adjudication.get("resolved_postreview_findings") != ["B16"]
        or adjudication.get("receipt_sha256")
        != "029ae539291a6307c2c49609655bfb427a42a11629e6c9283f212ae2b5e8f93c"
    ):
        raise AuditRecoveryError("historical v7 positive review differs")
    if validate_git and (
        _git_command(
            "merge-base",
            "--is-ancestor",
            "2479ed0c767fba7c872dbbd48666b5a598e2b9f6",
            _git_head(),
            check=False,
        ).returncode
        != 0
    ):
        raise AuditRecoveryError("historical v7 final commit is not an ancestor")
    return {
        "response_id": response["id"],
        "terminal_verdict": "READY TO FREEZE",
        "review_sha256": _sha256(root / "review.md"),
        "manifest_file_sha256": _sha256(root / "review_manifest.json"),
        "response_file_sha256": _sha256(root / "response.json"),
        "response_semantic_sha256": response_semantic_sha256,
        "adjudication_receipt_sha256": adjudication["receipt_sha256"],
        "adjudication_json_sha256": _sha256(
            REPO_ROOT / FINAL_V7_PRO_REVIEW_ADJUDICATION_JSON
        ),
        "adjudication_markdown_sha256": _sha256(
            REPO_ROOT / FINAL_V7_PRO_REVIEW_ADJUDICATION_MARKDOWN
        ),
        "finding_ids": list(HISTORICAL_V7_POSITIVE_FINDING_IDS),
        "code_freeze_commit": "f5edf5a1e901683254a7138f8b0917a81d2b5b6f",
        "reviewed_packet_git_head_commit": (
            "cc519e2c7545e19aafb929b98dfd2958c136a25b"
        ),
        "final_git_head_commit": "2479ed0c767fba7c872dbbd48666b5a598e2b9f6",
        "input_tokens": 1_865_304,
        "output_tokens": 31_051,
        "reasoning_tokens": 4_487,
        "recorded_cost_usd": 20.050335,
        "budget_authorization_usd": 75.0,
        "superseded_reason": "post_review_b20_git_reachable_in_gitless_active",
    }


def _validate_historical_b17_review_evidence() -> dict[str, Any]:
    for relative, expected in sorted(HISTORICAL_B17_PRO_REVIEW_PHYSICAL_SHA256.items()):
        if _sha256(REPO_ROOT / relative) != expected:
            raise AuditRecoveryError("immutable historical B17 review evidence differs")
    root = REPO_ROOT / HISTORICAL_B17_PRO_REVIEW_DIRECTORY
    response = _json(root / "response.json")
    manifest = _json(root / "review_manifest.json")
    review_text = (root / "review.md").read_text(encoding="utf-8")
    usage = response.get("usage")
    if (
        _response_review_text(response) != review_text
        or _terminal_review_verdict(review_text) != "READY AFTER SPECIFIED FIXES"
        or _v6_review_finding_ids(review_text) != list(HISTORICAL_B17_FINDING_IDS)
        or response.get("id")
        != "resp_0038445e5c1ea968016a57b46d6378819893a1587d331ce1a6"
        or response.get("model") != "gpt-5.6-sol"
        or response.get("status") != "completed"
        or not isinstance(usage, Mapping)
        or usage.get("input_tokens") != 194_837
        or usage.get("output_tokens") != 28_547
        or usage.get("output_tokens_details", {}).get("reasoning_tokens") != 11_612
        or manifest.get("status") != "completed"
        or manifest.get("response_id") != response["id"]
        or manifest.get("review_sha256")
        != HISTORICAL_B17_PRO_REVIEW_PHYSICAL_SHA256[
            f"{HISTORICAL_B17_PRO_REVIEW_DIRECTORY}/review.md"
        ]
        or manifest.get("reviewed_packet_git_head_commit")
        != "2479ed0c767fba7c872dbbd48666b5a598e2b9f6"
        or manifest.get("completed_response_cost_usd_conservative") != 1.830595
        or manifest.get("budget_authorization_usd") != 6.0
    ):
        raise AuditRecoveryError("historical B17 focused review differs")
    return {
        "response_id": response["id"],
        "terminal_verdict": "READY AFTER SPECIFIED FIXES",
        "review_sha256": _sha256(root / "review.md"),
        "manifest_file_sha256": _sha256(root / "review_manifest.json"),
        "finding_ids": list(HISTORICAL_B17_FINDING_IDS),
        "recorded_cost_usd": 1.830595,
        "incomplete_predecessor_response_id": (
            "resp_0a3a9f471779e79c016a57b366162481988f0d8b2d3f04e061"
        ),
        "incomplete_predecessor_reconstructed_cost_usd": 3.00996,
    }


def _validate_b20_incident_evidence() -> dict[str, Any]:
    for mapping in (
        B18_COMPACT_EVIDENCE_PHYSICAL_SHA256,
        B20_COMPACT_EVIDENCE_PHYSICAL_SHA256,
    ):
        for relative, expected in sorted(mapping.items()):
            if _sha256(REPO_ROOT / relative) != expected:
                raise AuditRecoveryError("immutable B18/B20 incident evidence differs")
    b18 = _canonical_json_receipt(
        REPO_ROOT / B18_COMPACT_EVIDENCE_DIRECTORY / "B18_CLOSURE_RECEIPT.json",
        "B18 cleanup closure",
    )
    b20 = _canonical_json_receipt(
        REPO_ROOT / B20_COMPACT_EVIDENCE_DIRECTORY / "B20_CLOSURE_RECEIPT.json",
        "B20 Gitless-ACTIVE incident closure",
    )
    verification = _canonical_json_receipt(
        REPO_ROOT / B20_COMPACT_EVIDENCE_DIRECTORY / "B20_VERIFICATION_OUTPUT.json",
        "B20 verification output",
    )
    if (
        b18.get("status") != "pass_b18_closed_mechanically"
        or b18.get("receipt_sha256")
        != "7d1d702efeace1d16010fec2bc1093069b1ed3c43a24bf669485ff283a6ca35f"
        or b20.get("incident_id") != "B20"
        or b20.get("status") != "closed_technical_failure_no_scientific_result"
        or b20.get("receipt_sha256")
        != "3f5dee0ccbef6af18302667c0cea95be0c7e4c4cd6d1f9b0d61a4222c1e157d9"
        or b20.get("identity", {}).get("pod_id") != "eeo1skjkwjqot5"
        or b20.get("designated_output", {}).get("files")
        != ["LANDLOCK_ENFORCEMENT.json"]
        or b20.get("failure", {}).get("scientific_result_status")
        != "none_produced"
        or b20.get("remediation")
        != {
            "device_policy_change": "none",
            "final_validation": "git_free",
            "status": "successor_fix_selected",
        }
        or verification.get("status") != "pass"
        or verification.get("receipt_sha256")
        != "49376b10210fb4ac0409c560287ff817bbc21bc0fadbf1e28c6fc1d36f9de84d"
    ):
        raise AuditRecoveryError("B18/B20 incident semantics differ")
    return {
        "b18_closure_receipt_sha256": b18["receipt_sha256"],
        "b20_closure_receipt_sha256": b20["receipt_sha256"],
        "b20_verification_receipt_sha256": verification["receipt_sha256"],
        "b20_attempt_id": b20["identity"]["attempt_id"],
        "b20_pod_id": b20["identity"]["pod_id"],
        "scientific_result_status": "none_produced",
    }


def _validate_v8_review_adjudication(
    *,
    root: Path,
    response: Mapping[str, Any],
    response_semantic_sha256: str,
    review_sha256: str,
    review_input_sha256: str,
    finding_ids: Sequence[str],
    historical_v7: Mapping[str, Any],
    historical_b17: Mapping[str, Any],
    incident: Mapping[str, Any],
    reviewed_evidence: Mapping[str, Any],
    reviewed_packet_git_head_commit: str,
) -> dict[str, Any]:
    json_path = REPO_ROOT / FINAL_V8_PRO_REVIEW_ADJUDICATION_JSON
    markdown_path = REPO_ROOT / FINAL_V8_PRO_REVIEW_ADJUDICATION_MARKDOWN
    value = _canonical_json_receipt(json_path, "final v8 review adjudication")
    markdown = markdown_path.read_text(encoding="utf-8")
    expected_review_binding = {
        "review_directory": FINAL_V8_PRO_REVIEW_DIRECTORY,
        "provider_response_id": response["id"],
        "provider_response_file_sha256": _sha256(root / "response.json"),
        "provider_response_semantic_sha256": response_semantic_sha256,
        "provider_review_sha256": review_sha256,
        "provider_manifest_file_sha256": _sha256(root / "review_manifest.json"),
        "request_payload_file_sha256": _sha256(root / "request_payload.json"),
        "review_request_file_sha256": _sha256(root / "review_request.md"),
        "review_input_sha256": review_input_sha256,
        "review_instructions_sha256": PRO_REVIEW_INSTRUCTIONS_SHA256,
        "reviewed_packet_git_head_commit": reviewed_packet_git_head_commit,
        "code_freeze_commit": reviewed_evidence["code_freeze_commit"],
        "adjudication_markdown_path": FINAL_V8_PRO_REVIEW_ADJUDICATION_MARKDOWN,
        "adjudication_markdown_sha256": _sha256(markdown_path),
    }
    expected_historical_v7_binding = {
        "review_directory": FINAL_V7_PRO_REVIEW_DIRECTORY,
        "provider_response_id": historical_v7["response_id"],
        "terminal_verdict": historical_v7["terminal_verdict"],
        "review_sha256": historical_v7["review_sha256"],
        "adjudication_receipt_sha256": historical_v7[
            "adjudication_receipt_sha256"
        ],
        "final_git_head_commit": historical_v7["final_git_head_commit"],
        "superseded_reason": historical_v7["superseded_reason"],
    }
    expected_historical_b17_binding = {
        "review_directory": HISTORICAL_B17_PRO_REVIEW_DIRECTORY,
        "provider_response_id": historical_b17["response_id"],
        "terminal_verdict": historical_b17["terminal_verdict"],
        "review_sha256": historical_b17["review_sha256"],
        "finding_ids": historical_b17["finding_ids"],
        "incomplete_predecessor_response_id": historical_b17[
            "incomplete_predecessor_response_id"
        ],
    }
    expected_incident_binding = {
        "finding_ids": ["B17", "B18", "B19", "B20"],
        "path": B20_INCIDENT_DOCUMENT,
        "file_sha256": _sha256(REPO_ROOT / B20_INCIDENT_DOCUMENT),
        **incident,
    }
    if (
        set(value)
        != {
            "schema_version",
            "artifact_type",
            "review_binding",
            "historical_v7_binding",
            "historical_b17_binding",
            "incident_binding",
            "reviewed_qualification_evidence",
            "finding_ids",
            "findings",
            "resolved_successor_findings",
            "final_decision",
            "receipt_sha256",
        }
        or value.get("schema_version") != 8
        or value.get("artifact_type") != "completed_provider_review_v8_adjudication"
        or value.get("review_binding") != expected_review_binding
        or value.get("historical_v7_binding") != expected_historical_v7_binding
        or value.get("historical_b17_binding") != expected_historical_b17_binding
        or value.get("incident_binding") != expected_incident_binding
        or value.get("reviewed_qualification_evidence") != reviewed_evidence
        or value.get("finding_ids") != list(finding_ids)
        or value.get("resolved_successor_findings")
        != ["B17", "B18", "B19", "B20"]
        or value.get("final_decision") != "READY_TO_EXECUTE"
        or "Final execution decision: **READY TO EXECUTE**." not in markdown
    ):
        raise AuditRecoveryError("final v8 review adjudication binding differs")
    required_ids = set(HISTORICAL_B17_FINDING_IDS) | {"B20"}
    if not required_ids.issubset(finding_ids):
        raise AuditRecoveryError("final v8 review omitted a cumulative finding ID")
    if any(
        finding_id.startswith("B") and int(finding_id[1:]) >= 21
        for finding_id in finding_ids
    ):
        raise AuditRecoveryError("final v8 review introduced a new blocker")
    for finding_id in set(finding_ids) - required_ids:
        prefix = finding_id[0]
        number = int(finding_id[1:])
        if (prefix == "B" and number < 21) or (prefix == "I" and number < 13):
            raise AuditRecoveryError("final v8 review recycled a reserved finding ID")
    packet_paths = {relative for relative, _role in PRO_REVIEW_V8_PACKET}
    findings = value.get("findings")
    if not isinstance(findings, list) or len(findings) != len(finding_ids):
        raise AuditRecoveryError("final v8 adjudication finding rows differ")
    observed_ids: list[str] = []
    rows_by_id: dict[str, Mapping[str, Any]] = {}
    for row in findings:
        if not isinstance(row, Mapping) or set(row) != {
            "id", "blocking", "disposition", "rationale", "changed_paths"
        }:
            raise AuditRecoveryError("final v8 adjudication finding rows differ")
        finding_id = row.get("id")
        changed_paths = row.get("changed_paths")
        if (
            not isinstance(finding_id, str)
            or re.fullmatch(r"[BI][0-9]{2}", finding_id) is None
            or row.get("blocking") is not finding_id.startswith("B")
            or row.get("disposition") not in {"fixed", "rejected"}
            or not isinstance(row.get("rationale"), str)
            or not row["rationale"].strip()
            or not isinstance(changed_paths, list)
            or changed_paths != sorted(set(changed_paths))
            or any(not isinstance(path, str) for path in changed_paths)
            or not set(changed_paths).issubset(packet_paths)
            or (row["disposition"] == "rejected" and changed_paths)
            or (row["blocking"] and row["disposition"] == "fixed" and not changed_paths)
            or finding_id not in markdown
        ):
            raise AuditRecoveryError("final v8 adjudication finding rows differ")
        observed_ids.append(finding_id)
        rows_by_id[finding_id] = row
    required_b20_paths = {
        B20_INCIDENT_DOCUMENT,
        FINAL_RECOVERY_CONTROLLER_TEMPLATE,
        "experiments/consciousness_sae_target_blind_calibration/audit_recovery.py",
        "experiments/consciousness_sae_target_blind_calibration/"
        "recovery_bundle_verifier.py",
        "tests/consciousness_sae_target_blind_calibration/test_audit_recovery.py",
        "tests/consciousness_sae_target_blind_calibration/"
        "test_recovery_bundle_verifier.py",
    }
    if (
        sorted(observed_ids) != list(finding_ids)
        or any(
            rows_by_id.get(finding_id, {}).get("disposition") != "fixed"
            for finding_id in ("B17", "B18", "B19", "B20")
        )
        or not required_b20_paths
        <= set(rows_by_id.get("B20", {}).get("changed_paths", []))
    ):
        raise AuditRecoveryError("final v8 B17-B20 adjudication differs")
    return {
        "receipt_sha256": value["receipt_sha256"],
        "json_sha256": _sha256(json_path),
        "markdown_sha256": _sha256(markdown_path),
        "fixed_finding_ids": sorted(
            row["id"] for row in findings if row["disposition"] == "fixed"
        ),
        "rejected_finding_ids": sorted(
            row["id"] for row in findings if row["disposition"] == "rejected"
        ),
    }


def _validate_review_evidence(
    *,
    validate_git: bool = True,
    expected_final_git_head_commit: str | None = None,
) -> dict[str, Any]:
    """Validate the prospective V8 review; final mode is completely Git-free."""

    if not isinstance(validate_git, bool):
        raise AuditRecoveryError("review Git-validation mode differs")
    if not validate_git and (
        not isinstance(expected_final_git_head_commit, str)
        or HEX40.fullmatch(expected_final_git_head_commit) is None
    ):
        raise AuditRecoveryError("sealed final Git HEAD binding differs")
    _validate_historical_incomplete_review_evidence()
    historical_v2 = _validate_historical_v2_review_evidence()
    historical_v3 = _validate_historical_v3_negative_review_evidence()
    historical_v4 = _validate_historical_v4_negative_review_evidence()
    historical_v5 = _validate_historical_v5_positive_review_evidence(
        validate_git=validate_git
    )
    historical_v6 = _validate_historical_v6_nonadjudicable_review_evidence(
        validate_git=validate_git
    )
    historical_v7 = _validate_historical_v7_positive_review_evidence(
        validate_git=validate_git
    )
    historical_b17 = _validate_historical_b17_review_evidence()
    incident = _validate_b20_incident_evidence()
    timed_qualification = _validate_v4_timed_qualification_evidence()
    source_test_files = _source_test_records()
    snapshots = _validate_v8_review_input_snapshots(source_test_files)
    reviewed_evidence = {**snapshots["evidence"], "timed_qualification": timed_qualification}

    root = REPO_ROOT / FINAL_V8_PRO_REVIEW_DIRECTORY
    required_paths = tuple(REPO_ROOT / relative for relative in FINAL_V8_PRO_REVIEW_OUTPUT_PATHS)
    if any(not path.is_file() for path in required_paths):
        raise AuditRecoveryError("prospective v8 review outputs are not complete")
    adjudication_value = _canonical_json_receipt(
        REPO_ROOT / FINAL_V8_PRO_REVIEW_ADJUDICATION_JSON,
        "final v8 review adjudication",
    )
    review_binding = adjudication_value.get("review_binding")
    reviewed_packet_git_head_commit = (
        str(review_binding.get("reviewed_packet_git_head_commit", ""))
        if isinstance(review_binding, Mapping)
        else ""
    )
    if HEX40.fullmatch(reviewed_packet_git_head_commit) is None:
        raise AuditRecoveryError("v8 reviewed packet Git commit differs")
    response = _json(root / "response.json")
    manifest = _json(root / "review_manifest.json")
    payload = _json(root / "request_payload.json")
    review_text = (root / "review.md").read_text(encoding="utf-8")
    review_sha256 = hashlib.sha256(review_text.encode("utf-8")).hexdigest()
    response_semantic_sha256 = hashlib.sha256(
        json.dumps(response, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()
    expected_review_input = _expected_v8_pro_review_input()
    review_input_sha256 = hashlib.sha256(expected_review_input.encode("utf-8")).hexdigest()
    instructions = payload.get("instructions")
    if not isinstance(instructions, str):
        raise AuditRecoveryError("final v8 review instructions are absent")
    limits = _validate_v8_packet_limits(instructions, expected_review_input)
    if hashlib.sha256(instructions.encode("utf-8")).hexdigest() != PRO_REVIEW_INSTRUCTIONS_SHA256:
        raise AuditRecoveryError("final v8 review instructions differ")
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, list) or len(artifacts) != len(PRO_REVIEW_V8_PACKET):
        raise AuditRecoveryError("final v8 review packet inventory differs")
    for row, (relative, role) in zip(artifacts, PRO_REVIEW_V8_PACKET, strict=True):
        if not isinstance(row, Mapping):
            raise AuditRecoveryError("final v8 review packet inventory differs")
        current_path = REPO_ROOT / relative
        current_raw = current_path.read_bytes()
        current_source = current_raw.decode("utf-8")
        row_path = PurePosixPath(str(row.get("path", ""))).as_posix()
        if (
            set(row) != {"path", "role", "bytes", "characters", "sha256"}
            or not (row_path == relative or row_path.endswith(f"/{relative}"))
            or row.get("role") != role
            or row.get("bytes") != len(current_raw)
            or row.get("characters") != len(current_source)
            or row.get("sha256") != hashlib.sha256(current_raw).hexdigest()
        ):
            raise AuditRecoveryError("v8 provider-reviewed packet bytes differ")
    expected_metadata = {
        "workflow": "experiment_plan_review",
        "plan_sha256": artifacts[0]["sha256"],
        "review_input_sha256": review_input_sha256,
        "review_instructions_sha256": PRO_REVIEW_INSTRUCTIONS_SHA256,
        "single_call_policy": "trusted_procedural_rule",
        "reviewed_packet_git_head_commit": reviewed_packet_git_head_commit,
    }
    expected_request = "# Developer instructions\n\n" + instructions.rstrip() + "\n\n" + expected_review_input
    response_reasoning = response.get("reasoning")
    response_text = response.get("text")
    response_prompt_cache = response.get("prompt_cache_options")
    usage = response.get("usage")
    if (
        payload.get("input") != expected_review_input
        or payload.get("metadata") != expected_metadata
        or payload.get("model") != "gpt-5.6-sol"
        or payload.get("reasoning") != {"mode": "pro", "effort": "medium"}
        or payload.get("max_output_tokens") != PRO_REVIEW_MAX_OUTPUT_TOKENS
        or payload.get("service_tier") != "default"
        or payload.get("tools") != []
        or payload.get("store") is not False
        or payload.get("truncation") != "disabled"
        or payload.get("prompt_cache_options") != {"mode": "explicit"}
        or payload.get("text") != {"verbosity": "high"}
        or payload.get("background", False) is not False
        or response.get("metadata") != expected_metadata
        or response.get("instructions") != instructions
        or not isinstance(response_reasoning, Mapping)
        or response_reasoning.get("mode") != "pro"
        or response_reasoning.get("effort") != "medium"
        or response.get("max_output_tokens") != PRO_REVIEW_MAX_OUTPUT_TOKENS
        or response.get("service_tier") != "default"
        or response.get("tools") != []
        or response.get("store") is not False
        or response.get("truncation") != "disabled"
        or not isinstance(response_text, Mapping)
        or response_text.get("verbosity") != "high"
        or not isinstance(response_prompt_cache, Mapping)
        or response_prompt_cache.get("mode") != "explicit"
        or response.get("background") is not False
        or (root / "review_request.md").read_text(encoding="utf-8") != expected_request
        or _response_review_text(response) != review_text
        or not isinstance(usage, Mapping)
    ):
        raise AuditRecoveryError("final v8 provider packet binding differs")
    response_id = response.get("id")
    preflight_tokens = manifest.get("input_tokens_preflight")
    exact_reserved_cost = manifest.get("exact_budget_reserve_usd_after_preflight")
    expected_exact_reserved_cost = (
        math.ceil(preflight_tokens * PRO_REVIEW_INPUT_RESERVE_MULTIPLIER)
        * (PRO_REVIEW_V6_INPUT_RATE_USD_PER_MILLION + PRO_REVIEW_V6_CACHE_WRITE_RATE_USD_PER_MILLION)
        + math.ceil(PRO_REVIEW_MAX_OUTPUT_TOKENS * PRO_REVIEW_OUTPUT_RESERVE_MULTIPLIER)
        * PRO_REVIEW_V6_OUTPUT_RATE_USD_PER_MILLION
    ) / 1_000_000 if isinstance(preflight_tokens, int) and not isinstance(preflight_tokens, bool) else math.nan
    if (
        not isinstance(response_id, str)
        or not response_id.startswith("resp_")
        or response.get("model") != "gpt-5.6-sol"
        or response.get("status") != "completed"
        or response.get("incomplete_details") not in (None, {})
        or not isinstance(usage.get("input_tokens"), int)
        or usage["input_tokens"] <= 0
        or not isinstance(usage.get("output_tokens"), int)
        or usage["output_tokens"] <= 0
        or manifest.get("status") != "completed"
        or manifest.get("model") != "gpt-5.6-sol"
        or manifest.get("official_latest_model") != "gpt-5.6-sol"
        or manifest.get("response_id") != response_id
        or manifest.get("response_model") != "gpt-5.6-sol"
        or manifest.get("review_sha256") != review_sha256
        or manifest.get("response_sha256") != response_semantic_sha256
        or manifest.get("response_metadata") != expected_metadata
        or manifest.get("reviewed_packet_git_head_commit") != reviewed_packet_git_head_commit
        or manifest.get("review_instructions_sha256") != PRO_REVIEW_INSTRUCTIONS_SHA256
        or manifest.get("review_input_sha256") != review_input_sha256
        or manifest.get("review_request_sha256") != _sha256(root / "review_request.md")
        or manifest.get("request_payload_sha256") != _sha256(root / "request_payload.json")
        or manifest.get("single_call_policy") != "trusted_procedural_rule"
        or manifest.get("actual_input_characters") != limits["actual_input_characters"]
        or manifest.get("estimated_input_tokens_conservative") != limits["estimated_input_tokens_conservative"]
        or manifest.get("max_input_characters") != PRO_REVIEW_V8_MAX_INPUT_CHARACTERS
        or manifest.get("max_input_tokens") != PRO_REVIEW_V8_MAX_INPUT_TOKENS
        or manifest.get("reserved_billable_input_tokens") != limits["reserved_billable_input_tokens"]
        or manifest.get("reserved_billable_output_tokens") != limits["reserved_billable_output_tokens"]
        or manifest.get("budget_authorization_usd") != PRO_REVIEW_BUDGET_AUTHORIZATION_USD
        or not isinstance(preflight_tokens, int)
        or isinstance(preflight_tokens, bool)
        or not 0 < preflight_tokens <= PRO_REVIEW_V8_MAX_INPUT_TOKENS
        or not isinstance(exact_reserved_cost, (int, float))
        or not math.isclose(float(exact_reserved_cost), expected_exact_reserved_cost, abs_tol=1e-12)
        or float(exact_reserved_cost) > PRO_REVIEW_BUDGET_AUTHORIZATION_USD
        or manifest.get("completed_response_cost_exceeded_budget_authorization") is not False
    ):
        raise AuditRecoveryError("final v8 review evidence differs")
    required_sections = (
        "# Verdict", "# Blocking findings", "# Important non-blocking findings",
        "# What should remain unchanged", "# Minimal revised design", "# Freeze checklist",
    )
    terminal_verdict = _terminal_review_verdict(review_text)
    finding_ids = _v6_review_finding_ids(review_text)
    required_ids = set(HISTORICAL_B17_FINDING_IDS) | {"B20"}
    if (
        any(section not in review_text for section in required_sections)
        or terminal_verdict != "READY TO FREEZE"
        or not required_ids.issubset(finding_ids)
        or any(fid.startswith("B") and int(fid[1:]) >= 21 for fid in finding_ids)
    ):
        raise AuditRecoveryError("final v8 review did not approve exact packet bytes")
    adjudication = _validate_v8_review_adjudication(
        root=root,
        response=response,
        response_semantic_sha256=response_semantic_sha256,
        review_sha256=review_sha256,
        review_input_sha256=review_input_sha256,
        finding_ids=finding_ids,
        historical_v7=historical_v7,
        historical_b17=historical_b17,
        incident=incident,
        reviewed_evidence=reviewed_evidence,
        reviewed_packet_git_head_commit=reviewed_packet_git_head_commit,
    )
    final_head = _git_head() if validate_git else str(expected_final_git_head_commit)
    if expected_final_git_head_commit is not None and final_head != expected_final_git_head_commit:
        raise AuditRecoveryError("sealed final Git HEAD binding differs")
    if validate_git:
        _validate_v8_git_chain(
            code_freeze_commit=reviewed_evidence["code_freeze_commit"],
            reviewed_packet_git_head_commit=reviewed_packet_git_head_commit,
            final_git_head_commit=final_head,
        )
    reconstructed_cost = (
        float(usage["input_tokens"]) * PRO_REVIEW_V6_INPUT_RATE_USD_PER_MILLION
        + float(usage.get("input_tokens_details", {}).get("cache_write_tokens", 0))
        * PRO_REVIEW_V6_CACHE_WRITE_RATE_USD_PER_MILLION
        + float(usage["output_tokens"]) * PRO_REVIEW_V6_OUTPUT_RATE_USD_PER_MILLION
    ) / 1_000_000
    recorded_cost = manifest.get("completed_response_cost_usd_conservative")
    if (
        not isinstance(recorded_cost, (int, float))
        or not math.isclose(reconstructed_cost, float(recorded_cost), abs_tol=1e-12)
        or reconstructed_cost > PRO_REVIEW_BUDGET_AUTHORIZATION_USD
    ):
        raise AuditRecoveryError("final v8 review cost reconstruction differs")
    evidence = reviewed_evidence
    return {
        "model": "gpt-5.6-sol",
        "provider_status": "completed",
        "provider_terminal_verdict": terminal_verdict,
        "response_id": response_id,
        "input_tokens": usage["input_tokens"],
        "output_tokens": usage["output_tokens"],
        "reasoning_tokens": usage.get("output_tokens_details", {}).get(
            "reasoning_tokens"
        ),
        "reconstructed_cost_usd": reconstructed_cost,
        "provider_approval_claimed": False,
        "provider_ready_to_freeze_verdict": True,
        "source_and_tests_reviewed_by_provider": True,
        "reviewed_packet_was_pre_fix": False,
        "final_source_reviewed_by_provider": True,
        "provider_reviewed_final_bytes_unchanged": True,
        "reviewed_packet_git_head_commit": reviewed_packet_git_head_commit,
        "final_git_head_commit": final_head,
        "code_freeze_commit": evidence["code_freeze_commit"],
        "source_test_inventory_sha256": evidence["source_test_inventory_sha256"],
        "historical_v2_terminal_verdict": historical_v2["terminal_verdict"],
        "historical_v2_adjudication_receipt_sha256": historical_v2[
            "adjudication_receipt_sha256"
        ],
        "historical_v2_remaining_blocking_findings": historical_v2[
            "remaining_blocking_findings"
        ],
        "historical_v3_terminal_verdict": historical_v3["terminal_verdict"],
        "historical_v3_adjudication_receipt_sha256": historical_v3[
            "adjudication_receipt_sha256"
        ],
        "historical_v3_remaining_blocking_findings": historical_v3[
            "remaining_blocking_findings"
        ],
        "historical_v4_terminal_verdict": historical_v4["terminal_verdict"],
        "historical_v4_adjudication_receipt_sha256": historical_v4[
            "adjudication_receipt_sha256"
        ],
        "historical_v4_remaining_blocking_findings": historical_v4[
            "remaining_blocking_findings"
        ],
        "historical_v4_input_tokens_preflight": historical_v4["input_tokens_preflight"],
        "historical_v4_recorded_cost_usd": historical_v4["recorded_cost_usd"],
        "historical_v4_retrospective_long_context_cost_usd": historical_v4[
            "retrospective_long_context_cost_usd"
        ],
        "historical_v4_budget_authorization_usd": historical_v4[
            "budget_authorization_usd"
        ],
        "historical_v4_pricing_disclosure_status": historical_v4[
            "pricing_disclosure_status"
        ],
        "historical_v5_terminal_verdict": historical_v5["terminal_verdict"],
        "historical_v5_response_id": historical_v5["response_id"],
        "historical_v5_review_sha256": historical_v5["review_sha256"],
        "historical_v5_adjudication_receipt_sha256": historical_v5[
            "adjudication_receipt_sha256"
        ],
        "historical_v5_adjudication_json_sha256": historical_v5[
            "adjudication_json_sha256"
        ],
        "historical_v5_superseded_reason": historical_v5["superseded_reason"],
        "historical_v5_input_tokens_preflight": historical_v5["input_tokens_preflight"],
        "historical_v5_recorded_cost_usd": historical_v5["recorded_cost_usd"],
        "historical_v5_retrospective_long_context_cost_usd": historical_v5[
            "retrospective_long_context_cost_usd"
        ],
        "historical_v5_budget_authorization_usd": historical_v5[
            "budget_authorization_usd"
        ],
        "historical_v5_pricing_disclosure_status": historical_v5[
            "pricing_disclosure_status"
        ],
        "historical_v6_terminal_verdict": historical_v6["terminal_verdict"],
        "historical_v6_response_id": historical_v6["response_id"],
        "historical_v6_review_sha256": historical_v6["review_sha256"],
        "historical_v6_manifest_file_sha256": historical_v6[
            "manifest_file_sha256"
        ],
        "historical_v6_response_file_sha256": historical_v6[
            "response_file_sha256"
        ],
        "historical_v6_request_payload_file_sha256": historical_v6[
            "request_payload_file_sha256"
        ],
        "historical_v6_review_request_file_sha256": historical_v6[
            "review_request_file_sha256"
        ],
        "historical_v6_reviewed_packet_git_head_commit": historical_v6[
            "reviewed_packet_git_head_commit"
        ],
        "historical_v6_nonadjudicable_reason": historical_v6[
            "nonadjudicable_reason"
        ],
        "historical_v6_authorization_status": historical_v6[
            "authorization_status"
        ],
        "timed_qualification_receipt_sha256": timed_qualification["receipt_sha256"],
        "timed_qualification_termination_receipt_sha256": timed_qualification[
            "termination_receipt_sha256"
        ],
        "timed_qualification_pod_id": timed_qualification["pod_id"],
        "timed_qualification_authorization_ready_host_age_seconds": (
            timed_qualification["authorization_ready_host_age_seconds"]
        ),
        "timed_qualification_seconds_remaining": timed_qualification[
            "seconds_remaining_at_authorization_ready"
        ],
        "timed_qualification_reserve_surplus_seconds": timed_qualification[
            "seconds_above_required_remaining_margin"
        ],
        "timed_qualification_public_artifact_file_count": timed_qualification[
            "public_artifact_file_count"
        ],
        "timed_qualification_public_artifact_total_bytes": timed_qualification[
            "public_artifact_total_bytes"
        ],
        "timed_qualification_cuda_preflight_closure_scope": timed_qualification[
            "cuda_preflight_closure_scope"
        ],
        "timed_qualification_final_recovery_scope_must_repeat": (
            timed_qualification["final_recovery_scope_must_repeat"]
        ),
        "finding_ids": finding_ids,
        "review_sha256": review_sha256,
        "adjudication_receipt_sha256": adjudication["receipt_sha256"],
        "adjudication_json_sha256": adjudication["json_sha256"],
        "adjudication_markdown_sha256": adjudication["markdown_sha256"],
        "fixed_finding_ids": adjudication["fixed_finding_ids"],
        "rejected_finding_ids": adjudication["rejected_finding_ids"],
        "reviewed_local_test_receipt_file_sha256": evidence["local_test_receipt"][
            "file_sha256"
        ],
        "reviewed_local_test_receipt_receipt_sha256": evidence["local_test_receipt"][
            "receipt_sha256"
        ],
        "reviewed_target_host_test_receipt_file_sha256": evidence[
            "target_host_test_receipt"
        ]["file_sha256"],
        "reviewed_target_host_test_receipt_receipt_sha256": evidence[
            "target_host_test_receipt"
        ]["receipt_sha256"],
        "reviewed_target_qualification_ownership_file_sha256": evidence[
            "target_qualification_ownership"
        ]["file_sha256"],
        "reviewed_target_qualification_ownership_receipt_sha256": evidence[
            "target_qualification_ownership"
        ]["receipt_sha256"],
        "reviewed_target_qualification_landlock_file_sha256": evidence[
            "target_qualification_landlock"
        ]["file_sha256"],
        "reviewed_target_qualification_landlock_receipt_sha256": evidence[
            "target_qualification_landlock"
        ]["receipt_sha256"],
        "reviewed_target_qualification_cuda_file_sha256": evidence[
            "target_qualification_cuda"
        ]["file_sha256"],
        "reviewed_target_qualification_cuda_receipt_sha256": evidence[
            "target_qualification_cuda"
        ]["receipt_sha256"],
        "historical_v7_terminal_verdict": historical_v7["terminal_verdict"],
        "historical_v7_response_id": historical_v7["response_id"],
        "historical_v7_review_sha256": historical_v7["review_sha256"],
        "historical_v7_adjudication_receipt_sha256": historical_v7["adjudication_receipt_sha256"],
        "historical_v7_adjudication_json_sha256": historical_v7["adjudication_json_sha256"],
        "historical_v7_final_git_head_commit": historical_v7["final_git_head_commit"],
        "historical_b17_terminal_verdict": historical_b17["terminal_verdict"],
        "historical_b17_response_id": historical_b17["response_id"],
        "historical_b17_review_sha256": historical_b17["review_sha256"],
        "historical_b17_manifest_file_sha256": historical_b17["manifest_file_sha256"],
        "historical_b17_finding_ids": historical_b17["finding_ids"],
        "historical_b17_recorded_cost_usd": historical_b17["recorded_cost_usd"],
        "historical_b17_incomplete_response_id": historical_b17["incomplete_predecessor_response_id"],
        "historical_b17_incomplete_cost_usd": historical_b17["incomplete_predecessor_reconstructed_cost_usd"],
        "b18_closure_receipt_sha256": incident["b18_closure_receipt_sha256"],
        "b20_closure_receipt_sha256": incident["b20_closure_receipt_sha256"],
        "b20_verification_receipt_sha256": incident["b20_verification_receipt_sha256"],
        "b20_attempt_id": incident["b20_attempt_id"],
        "b20_pod_id": incident["b20_pod_id"],
        "b20_scientific_result_status": incident["scientific_result_status"],
        "historical_pre_v2_paid_call_count": 2,
        "historical_v2_paid_call_count": 1,
        "historical_v3_paid_call_count": 1,
        "historical_v4_paid_call_count": 1,
        "completed_v5_paid_call_count": 1,
        "completed_v6_paid_call_count": 1,
        "completed_v7_paid_call_count": 1,
        "incomplete_b17_paid_call_count": 1,
        "completed_b17_paid_call_count": 1,
        "completed_v8_paid_call_count": 1,
        "cumulative_disclosed_paid_call_count": 11,
    }


def _validate_reviewed_external_evidence(
    review: Mapping[str, Any], args: argparse.Namespace
) -> None:
    rows = (
        (
            "reviewed_local_test_receipt",
            args.local_test_receipt,
            V8_LOCAL_TEST_RECEIPT_SNAPSHOT,
        ),
        (
            "reviewed_target_host_test_receipt",
            args.target_host_test_receipt,
            V8_TARGET_HOST_TEST_RECEIPT_SNAPSHOT,
        ),
        (
            "reviewed_target_qualification_ownership",
            args.target_qualification_ownership,
            V8_TARGET_QUALIFICATION_OWNERSHIP_SNAPSHOT,
        ),
        (
            "reviewed_target_qualification_landlock",
            args.target_qualification_landlock,
            V8_TARGET_QUALIFICATION_LANDLOCK_SNAPSHOT,
        ),
        (
            "reviewed_target_qualification_cuda",
            args.target_qualification_cuda_preflight,
            V8_TARGET_QUALIFICATION_CUDA_SNAPSHOT,
        ),
    )
    for prefix, external_path, snapshot_relative in rows:
        snapshot_path = REPO_ROOT / snapshot_relative
        external_value = _canonical_json_receipt(
            external_path, f"external {prefix} evidence"
        )
        external_record = _file_record(external_path)
        if (
            external_record != _file_record(snapshot_path)
            or review.get(f"{prefix}_file_sha256") != external_record["sha256"]
            or review.get(f"{prefix}_receipt_sha256")
            != external_value["receipt_sha256"]
        ):
            raise AuditRecoveryError(
                "external qualification evidence differs from reviewed snapshots"
            )


def _validate_run_and_ledgers(
    *,
    run_complete_path: Path,
    raw_ledger_path: Path,
    raw_inventory_path: Path,
    failure_log_path: Path,
) -> dict[str, Any]:
    if _sha256(run_complete_path) != ORIGINAL_RUN_FILE_SHA256:
        raise AuditRecoveryError("RUN_COMPLETE physical hash differs")
    if _sha256(raw_ledger_path) != ORIGINAL_RAW_LEDGER_SHA256:
        raise AuditRecoveryError("raw SHA ledger physical hash differs")
    if _sha256(raw_inventory_path) != ORIGINAL_RAW_INVENTORY_SHA256:
        raise AuditRecoveryError("raw inventory physical hash differs")
    if _sha256(failure_log_path) != ORIGINAL_FAILURE_LOG_SHA256:
        raise AuditRecoveryError("failed-audit log physical hash differs")
    if "J-lens map inventory differs" not in failure_log_path.read_text(
        encoding="utf-8"
    ):
        raise AuditRecoveryError("failed-audit reason differs")
    complete = _json(run_complete_path)
    if (
        _self_hash(complete, "RUN_COMPLETE") != ORIGINAL_RUN_RECEIPT_SHA256
        or complete.get("status") != "complete"
        or complete.get("run_id") != RUN_ID
        or complete.get("plan_manifest_sha256")
        != "aa80cef7ef36fed327fcce99547c0b3bdf92a059c1dea43abba0ba924f404636"
        or complete.get("stored_bytes") != 323365550
        or complete.get("target_prompt_render_count") != 0
        or complete.get("target_feature_vector_count") != 0
        or complete.get("analysis_data_inputs") != []
        or complete.get("runtime", {}).get("model_forward_count") != 256
    ):
        raise AuditRecoveryError("RUN_COMPLETE identity differs")
    records = complete.get("records")
    if not isinstance(records, list) or len(records) != 35:
        raise AuditRecoveryError("RUN_COMPLETE manifest differs")
    prefix = f"/workspace/{RAW_RELATIVE}/"
    hashes: dict[str, str] = {}
    for line in raw_ledger_path.read_text(encoding="utf-8").splitlines():
        digest, separator, absolute = line.partition("  ")
        if (
            separator != "  "
            or HEX64.fullmatch(digest) is None
            or not absolute.startswith(prefix)
        ):
            raise AuditRecoveryError("raw SHA ledger row differs")
        relative = absolute.removeprefix(prefix)
        if relative in hashes:
            raise AuditRecoveryError("raw SHA ledger path is duplicated")
        hashes[relative] = digest
    sizes: dict[str, int] = {}
    for line in raw_inventory_path.read_text(encoding="utf-8").splitlines():
        size_text, separator, absolute = line.partition(" ")
        if separator != " " or not absolute.startswith(prefix):
            raise AuditRecoveryError("raw inventory row differs")
        relative = absolute.removeprefix(prefix)
        if relative in sizes:
            raise AuditRecoveryError("raw inventory path is duplicated")
        try:
            sizes[relative] = int(size_text)
        except ValueError as exc:
            raise AuditRecoveryError("raw inventory size differs") from exc
    expected = {str(row["path"]) for row in records} | {"RUN_COMPLETE.json"}
    if set(hashes) != expected or set(sizes) != expected:
        raise AuditRecoveryError("external raw inventory differs")
    for row in records:
        relative = str(row["path"])
        if hashes[relative] != row["sha256"] or sizes[relative] != row["bytes"]:
            raise AuditRecoveryError("external raw ledger/manifest differs")
    if (
        hashes["RUN_COMPLETE.json"] != ORIGINAL_RUN_FILE_SHA256
        or sizes["RUN_COMPLETE.json"] != run_complete_path.stat().st_size
    ):
        raise AuditRecoveryError("external completion-receipt row differs")
    return complete


def _validate_original_chain(
    *,
    plan_dir: Path,
    ownership_path: Path,
    guest_path: Path,
    cache_path: Path,
    authorization_path: Path,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    ownership_raw = _json(ownership_path)
    guest_raw = _json(guest_path)
    cache_raw = _json(cache_path)
    authorization_raw = _json(authorization_path)
    try:
        ownership = runpod_preflight.validate_ownership_receipt(ownership_raw)
        guest = runpod_preflight.validate_guest_receipt(
            guest_raw, ownership_receipt=ownership
        )
        cache = runpod_preflight.validate_cache_receipt(
            cache_raw, guest_receipt=guest, ownership_receipt=ownership
        )
        plan = authorize._validate_plan(plan_dir)  # noqa: SLF001
        historical_now = _utc(
            str(authorization_raw["authorized_at_utc"]), "old authorization time"
        ).timestamp()
        authorization = authorize.validate_execution_authorization(
            authorization_raw,
            plan=plan["manifest"],
            plan_manifest_path=plan["manifest_path"],
            source_files_path=plan["source_path"],
            ownership=ownership,
            guest=guest,
            cache=cache,
            now_unix=historical_now,
        )
    except (runpod_preflight.PreflightError, authorize.AuthorizationError) as exc:
        raise AuditRecoveryError("original execution receipt chain failed") from exc
    return ownership, guest, cache, authorization


def _validate_fresh_chain(
    *, ownership_path: Path, guest_path: Path, cache_path: Path
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    try:
        ownership = runpod_preflight.validate_ownership_receipt(_json(ownership_path))
        guest = runpod_preflight.validate_guest_receipt(
            _json(guest_path), ownership_receipt=ownership
        )
        cache = runpod_preflight.validate_cache_receipt(
            _json(cache_path), guest_receipt=guest, ownership_receipt=ownership
        )
    except runpod_preflight.PreflightError as exc:
        raise AuditRecoveryError("fresh audit-host receipt chain failed") from exc
    if (
        ownership.get("network_volume_id") != protocol.NETWORK_VOLUME_ID
        or ownership.get("data_center_id") != protocol.DATA_CENTER_ID
        or ownership.get("gpu_type") != protocol.GPU_TYPE
        or ownership.get("gpu_count") != 1
        or guest.get("model_forward_count") != 0
        or guest.get("target_prompt_render_count") != 0
        or guest.get("prior_outcome_inputs") != []
        or cache.get("model_forward_count") != 0
        or cache.get("target_prompt_render_count") != 0
        or cache.get("prior_outcome_inputs") != []
        or cache.get("independently_rehashed") is not True
        or cache.get("read_only") is not True
    ):
        raise AuditRecoveryError("fresh audit host is not zero-forward/target-free")
    return ownership, guest, cache


def _validate_superseded_recovery_host(args: argparse.Namespace) -> dict[str, Any]:
    runtime = _json(args.superseded_runtime_block)
    termination = _json(args.superseded_termination_audit)
    frozen = _json(args.superseded_frozen_termination)
    postdelete = _json(args.superseded_postdelete_inventory)
    if (
        _self_hash(runtime, "superseded runtime block")
        != SUPERSEDED_RUNTIME_BLOCK_SHA256
        or runtime.get("receipt_type") != "audit_recovery_preexecution_runtime_block_v1"
        or runtime.get("status") != "blocked_before_attempt_claim_missing_cap_sys_admin"
        or runtime.get("pod_id") != SUPERSEDED_RECOVERY_POD_ID
        or runtime.get("attempt_id") != SUPERSEDED_RECOVERY_ATTEMPT_ID
        or runtime.get("audit_execute_invoked") is not False
        or runtime.get("attempt_marker_exists_at_pretermination") is not False
        or runtime.get("failure_receipt_exists_at_pretermination") is not False
        or runtime.get("compact_directory_exists_at_pretermination") is not False
        or runtime.get("landlock_abi") != 4
        or runtime.get("network_volume_deleted") is not False
        or runtime.get("provider_postdelete_pod_count") != 0
        or runtime.get("termination_audit_receipt_sha256")
        != SUPERSEDED_TERMINATION_AUDIT_SHA256
        or runtime.get("frozen_termination_receipt_sha256")
        != SUPERSEDED_FROZEN_TERMINATION_SHA256
        or runtime.get("postdelete_inventory_receipt_sha256")
        != SUPERSEDED_POSTDELETE_INVENTORY_SHA256
        or _self_hash(termination, "superseded termination audit")
        != SUPERSEDED_TERMINATION_AUDIT_SHA256
        or termination.get("pod_id") != SUPERSEDED_RECOVERY_POD_ID
        or termination.get("status")
        != "deleted_exact_owned_pod_unrelated_inventory_unchanged"
        or termination.get("frozen_termination_receipt_sha256")
        != SUPERSEDED_FROZEN_TERMINATION_SHA256
        or _self_hash(frozen, "superseded frozen termination")
        != SUPERSEDED_FROZEN_TERMINATION_SHA256
        or frozen.get("pod_id") != SUPERSEDED_RECOVERY_POD_ID
        or frozen.get("status") != "deleted_verified"
        or frozen.get("absent_from_account_inventory") is not True
        or frozen.get("other_pods_mutated") is not False
        or _self_hash(postdelete, "superseded post-delete inventory")
        != SUPERSEDED_POSTDELETE_INVENTORY_SHA256
        or postdelete.get("pods") != []
        or postdelete.get("all_account_pod_count") != 0
    ):
        raise AuditRecoveryError("superseded recovery-host evidence differs")
    return {
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


def _validate_fresh_authority_clock(
    receipt: Mapping[str, Any], ownership: Mapping[str, Any], *, now_unix: float
) -> None:
    started = float(receipt["recovery_started_at_unix"])
    deadline = float(receipt["recovery_deadline_at_unix"])
    provider_deadline = float(receipt["provider_deadline_at_unix"])
    created = _utc(str(ownership["created_at"]), "fresh pod creation")
    exact_provider_deadline = _utc(
        str(ownership["terminate_after"]), "fresh provider deadline"
    )
    authorized = _utc(str(receipt.get("authorized_at_utc", "")), "authorized_at")
    if (
        started != created.timestamp()
        or deadline != created.timestamp() + RECOVERY_SECONDS
        or provider_deadline != exact_provider_deadline.timestamp()
        or not created <= authorized < datetime.fromtimestamp(deadline, timezone.utc)
        or deadline - authorized.timestamp() < MINIMUM_ISSUE_REMAINING_SECONDS
        or authorized.timestamp() > now_unix
    ):
        raise AuditRecoveryError("recovery clock is not fresh-ownership-bound")


def issue_authorization(args: argparse.Namespace) -> dict[str, Any]:
    plan, provenance_paths, provenance = _validate_pre_gpu_issue_inputs(args.plan_dir)
    closure = _closure_records()
    bound_paths = set(provenance_paths) | set(RECOVERY_BOUND_PATHS)
    authorize._verify_committed_paths(tuple(bound_paths))  # noqa: SLF001
    git = authorize._live_remote_freeze()  # noqa: SLF001
    execution = _execution_binding(
        args, git_head=git["git_head_commit"], validate_execute_paths=False
    )
    _validate_issue_output(args.output, execution)
    bootstrap_import_roots = _bootstrap_manifest_binding(
        args.roots_manifest,
        expected_file_sha256=args.roots_manifest_sha256,
        active_root=Path(execution["active_root"]),
    )
    review = _validate_review_evidence(
        expected_final_git_head_commit=git["git_head_commit"]
    )
    if review["final_git_head_commit"] != git["git_head_commit"]:
        raise AuditRecoveryError("review and authorization Git HEAD differ")
    preflight_landlock, preflight_probe = _validate_cuda_preflight(
        args.preflight_landlock,
        args.preflight_probe,
        expected_landlock_path=Path(execution["paths"]["preflight_landlock"]),
        expected_probe_path=Path(execution["paths"]["preflight_probe"]),
        active_root=Path(execution["active_root"]),
        python_executable=Path(execution["python_executable"]),
        roots_manifest_path=Path(execution["paths"]["roots_manifest"]),
        roots_manifest_sha256=execution["roots_manifest_sha256"],
        bootstrap_manifest=bootstrap_import_roots["manifest"],
        output_root=Path(execution["paths"]["preflight_output_root"]),
        canary_protected_root=Path(
            execution["paths"]["preflight_canary_protected_root"]
        ),
        canary_output_root=Path(execution["paths"]["preflight_canary_output_root"]),
        device_files=[Path(path) for path in execution["device_files"]],
        closure_scope="final_recovery",
        expected_closure_files=closure,
    )
    complete = _validate_run_and_ledgers(
        run_complete_path=args.run_complete,
        raw_ledger_path=args.raw_ledger,
        raw_inventory_path=args.raw_inventory,
        failure_log_path=args.failure_log,
    )
    old_ownership, old_guest, old_cache, old_authorization = _validate_original_chain(
        plan_dir=args.plan_dir,
        ownership_path=args.original_ownership,
        guest_path=args.original_guest,
        cache_path=args.original_cache,
        authorization_path=args.original_authorization,
    )
    superseded_recovery_host = _validate_superseded_recovery_host(args)
    fresh_ownership, fresh_guest, fresh_cache = _validate_fresh_chain(
        ownership_path=args.fresh_ownership,
        guest_path=args.fresh_guest,
        cache_path=args.fresh_cache,
    )
    if preflight_probe["provider"] != {
        "pod_id": fresh_ownership["pod_id"],
        "volume_id": protocol.NETWORK_VOLUME_ID,
        "data_center_id": protocol.DATA_CENTER_ID,
    }:
        raise AuditRecoveryError("CUDA preflight provider identity differs")
    if preflight_probe["python_executable"] != execution["python_executable"]:
        raise AuditRecoveryError("CUDA preflight Python executable differs")
    term = _json(args.termination_audit)
    postdelete = _json(args.postdelete_inventory)
    frozen_term = _json(args.frozen_termination)
    if (
        _self_hash(term, "old termination audit")
        != "b346b5c575ba1a903d93874b6dea58101cd208539ef5e30e8d069955d864ebfd"
        or term.get("pod_id") != old_ownership.get("pod_id")
        or term.get("status") != "deleted_exact_owned_pod_unrelated_inventory_unchanged"
        or _self_hash(postdelete, "old post-delete inventory")
        != "7d1631e8dc248e61e36bc71193857a07e430fc012acb861907e1fb89b0fbf022"
        or postdelete.get("pods") != []
        or postdelete.get("all_account_pod_count") != 0
        or _self_hash(frozen_term, "old frozen termination")
        != "86d0efdcf0b54b927bd3062ff448d0abf3d12aa873c837766249e1b7a110dfe5"
    ):
        raise AuditRecoveryError("old pod termination evidence differs")
    if args.hourly_price_usd != RECOVERY_RATE_USD_PER_HOUR:
        raise AuditRecoveryError("recovery accounting rate differs")
    raw_root = args.raw_root.expanduser().absolute()
    if raw_root.as_posix() != f"/workspace/{RAW_RELATIVE}":
        raise AuditRecoveryError("recovery raw root differs")
    created = _utc(str(fresh_ownership["created_at"]), "fresh pod creation")
    deadline = created + timedelta(seconds=RECOVERY_SECONDS)
    provider_deadline = _utc(
        str(fresh_ownership["terminate_after"]), "fresh provider deadline"
    )
    now = datetime.now(timezone.utc)
    if (
        not created <= now < deadline < provider_deadline
        or (deadline - now).total_seconds() < MINIMUM_ISSUE_REMAINING_SECONDS
    ):
        raise AuditRecoveryError("fresh recovery authorization window differs")
    source_test_files = _source_test_records(closure)
    local_test_receipt = _validate_test_receipt(
        _canonical_json_receipt(args.local_test_receipt, "local test receipt"),
        kind="local",
        expected_source_test_files=source_test_files,
        authorized_at=now,
    )
    target_host_test_receipt = _validate_test_receipt(
        _canonical_json_receipt(
            args.target_host_test_receipt, "target-host test receipt"
        ),
        kind="target_host",
        expected_source_test_files=source_test_files,
        qualification_ownership_path=args.target_qualification_ownership,
        qualification_landlock_path=args.target_qualification_landlock,
        qualification_cuda_path=args.target_qualification_cuda_preflight,
        authorized_at=now,
    )
    code_freeze_commit = str(local_test_receipt["code_freeze_commit"])
    if (
        target_host_test_receipt["code_freeze_commit"] != code_freeze_commit
        or review["code_freeze_commit"] != code_freeze_commit
        or review["source_test_inventory_sha256"]
        != local_test_receipt["source_test_inventory_sha256"]
    ):
        raise AuditRecoveryError("test receipt code-freeze commits differ")
    if target_host_test_receipt["target_host"]["pod_id"] == fresh_ownership["pod_id"]:
        raise AuditRecoveryError(
            "qualification and recovery pod identities must be distinct"
        )
    _require_code_freeze_ancestor(code_freeze_commit, git["git_head_commit"])
    _validate_reviewed_external_evidence(review, args)
    external_paths = {
        "run_complete": args.run_complete,
        "raw_ledger": args.raw_ledger,
        "raw_inventory": args.raw_inventory,
        "failure_log": args.failure_log,
        "original_ownership": args.original_ownership,
        "original_guest": args.original_guest,
        "original_cache": args.original_cache,
        "original_authorization": args.original_authorization,
        "termination_audit": args.termination_audit,
        "postdelete_inventory": args.postdelete_inventory,
        "frozen_termination": args.frozen_termination,
        "superseded_runtime_block": args.superseded_runtime_block,
        "superseded_termination_audit": args.superseded_termination_audit,
        "superseded_frozen_termination": args.superseded_frozen_termination,
        "superseded_postdelete_inventory": args.superseded_postdelete_inventory,
        "fresh_ownership": args.fresh_ownership,
        "fresh_guest": args.fresh_guest,
        "fresh_cache": args.fresh_cache,
        "preflight_landlock": args.preflight_landlock,
        "preflight_probe": args.preflight_probe,
        "local_test_receipt": args.local_test_receipt,
        "target_host_test_receipt": args.target_host_test_receipt,
        "target_qualification_ownership": args.target_qualification_ownership,
        "target_qualification_landlock": args.target_qualification_landlock,
        "target_qualification_cuda_preflight": (
            args.target_qualification_cuda_preflight
        ),
        "roots_manifest": args.roots_manifest,
    }
    external = {
        name: _file_record(path) for name, path in sorted(external_paths.items())
    }
    core = {
        "schema_version": 1,
        "status": "authorized_audit_only_recovery_landlock_confined",
        "study_id": protocol.STUDY_ID,
        "protocol_version": protocol.PROTOCOL_VERSION,
        "recovery_protocol_version": RECOVERY_PROTOCOL_VERSION,
        "run_id": RUN_ID,
        "raw_root": raw_root.as_posix(),
        "raw_run_receipt_sha256": complete["receipt_sha256"],
        "plan_manifest_sha256": plan["manifest"]["plan_manifest_sha256"],
        "recovery_bound_files": closure,
        "recovery_bound_paths_sha256": protocol.canonical_sha256(
            tuple(row["path"] for row in closure)
        ),
        "historical_provenance_files": provenance,
        "historical_provenance_inventory_sha256": protocol.canonical_sha256(provenance),
        "bootstrap_import_roots": bootstrap_import_roots,
        "external_files": external,
        "original_receipts": {
            "ownership": old_ownership["receipt_sha256"],
            "guest": old_guest["receipt_sha256"],
            "cache": old_cache["receipt_sha256"],
            "authorization": old_authorization["receipt_sha256"],
            "termination_audit": term["receipt_sha256"],
            "frozen_termination": frozen_term["receipt_sha256"],
        },
        "superseded_recovery_host": superseded_recovery_host,
        "fresh_receipts": {
            "ownership": fresh_ownership["receipt_sha256"],
            "guest": fresh_guest["receipt_sha256"],
            "cache": fresh_cache["receipt_sha256"],
        },
        "preflight": {
            "landlock_receipt": preflight_landlock,
            "landlock_file": _file_record(args.preflight_landlock),
            "probe_receipt": preflight_probe,
            "probe_file": _file_record(args.preflight_probe),
            "device_rules": preflight_landlock["device_rules"],
        },
        "test_receipts": {
            "local": local_test_receipt,
            "target_host": target_host_test_receipt,
        },
        "fresh_pod_id": fresh_ownership["pod_id"],
        "volume_id": protocol.NETWORK_VOLUME_ID,
        "data_center_id": protocol.DATA_CENTER_ID,
        "gpu_type": protocol.GPU_TYPE,
        "gpu_count": 1,
        "recovery_started_at_unix": created.timestamp(),
        "recovery_deadline_at_unix": deadline.timestamp(),
        "provider_deadline_at_unix": provider_deadline.timestamp(),
        "max_walltime_seconds": RECOVERY_SECONDS,
        "hourly_price_usd": RECOVERY_RATE_USD_PER_HOUR,
        "max_spend_usd": RECOVERY_MAX_SPEND_USD,
        "authorized_at_utc": _utc_text(now),
        "model_forward_limit": 0,
        "target_prompt_render_limit": 0,
        "target_feature_vector_limit": 0,
        "external_or_prior_outcome_inputs": [],
        "write_confinement": dict(LANDLOCK_POLICY),
        "execution": execution,
        "review": review,
        **git,
    }
    return {**core, "receipt_sha256": protocol.canonical_sha256(core)}


def validate_recovery_authorization(
    value: Mapping[str, Any],
    args: argparse.Namespace,
    *,
    now_unix: float | None = None,
    validate_git: bool = True,
) -> dict[str, Any]:
    receipt = dict(value)
    _self_hash(receipt, "recovery authorization")
    if (
        receipt.get("schema_version") != 1
        or receipt.get("status") != "authorized_audit_only_recovery_landlock_confined"
        or receipt.get("study_id") != protocol.STUDY_ID
        or receipt.get("protocol_version") != protocol.PROTOCOL_VERSION
        or receipt.get("recovery_protocol_version") != RECOVERY_PROTOCOL_VERSION
        or receipt.get("run_id") != RUN_ID
        or receipt.get("raw_root") != f"/workspace/{RAW_RELATIVE}"
        or receipt.get("raw_run_receipt_sha256") != ORIGINAL_RUN_RECEIPT_SHA256
        or receipt.get("plan_manifest_sha256")
        != "aa80cef7ef36fed327fcce99547c0b3bdf92a059c1dea43abba0ba924f404636"
        or receipt.get("volume_id") != protocol.NETWORK_VOLUME_ID
        or receipt.get("data_center_id") != protocol.DATA_CENTER_ID
        or receipt.get("gpu_type") != protocol.GPU_TYPE
        or receipt.get("gpu_count") != 1
        or receipt.get("max_walltime_seconds") != RECOVERY_SECONDS
        or receipt.get("hourly_price_usd") != RECOVERY_RATE_USD_PER_HOUR
        or receipt.get("max_spend_usd") != RECOVERY_MAX_SPEND_USD
        or receipt.get("model_forward_limit") != 0
        or receipt.get("target_prompt_render_limit") != 0
        or receipt.get("target_feature_vector_limit") != 0
        or receipt.get("external_or_prior_outcome_inputs") != []
        or receipt.get("write_confinement") != LANDLOCK_POLICY
    ):
        raise AuditRecoveryError("recovery authorization identity differs")
    execution = _execution_binding(
        args,
        git_head=str(receipt.get("git_head_commit", "")),
        validate_execute_paths=True,
    )
    if receipt.get("execution") != execution:
        raise AuditRecoveryError("recovery execution binding differs")
    bootstrap_import_roots = _bootstrap_manifest_binding(
        args.roots_manifest,
        expected_file_sha256=args.roots_manifest_sha256,
        active_root=Path(execution["active_root"]),
    )
    if receipt.get("bootstrap_import_roots") != bootstrap_import_roots:
        raise AuditRecoveryError("recovery bootstrap import-root binding differs")
    started = float(receipt["recovery_started_at_unix"])
    deadline = float(receipt["recovery_deadline_at_unix"])
    provider_deadline = float(receipt["provider_deadline_at_unix"])
    now = time.time() if now_unix is None else float(now_unix)
    if (
        not all(math.isfinite(v) for v in (started, deadline, provider_deadline, now))
        or deadline - started != RECOVERY_SECONDS
        or deadline >= provider_deadline
        or not started <= now < deadline
        or RECOVERY_RATE_USD_PER_HOUR * (deadline - started) / 3600
        != RECOVERY_MAX_SPEND_USD
    ):
        raise AuditRecoveryError("recovery authorization budget window differs")
    closure = _closure_records()
    if receipt.get("recovery_bound_files") != closure or receipt.get(
        "recovery_bound_paths_sha256"
    ) != protocol.canonical_sha256(tuple(row["path"] for row in closure)):
        raise AuditRecoveryError("recovery committed source closure differs")
    review = _validate_review_evidence(
        validate_git=validate_git,
        expected_final_git_head_commit=str(receipt.get("git_head_commit", "")),
    )
    if receipt.get("review") != review:
        raise AuditRecoveryError("recovery review binding differs")
    provenance_rows = receipt.get("historical_provenance_files")
    if not isinstance(provenance_rows, list) or receipt.get(
        "historical_provenance_inventory_sha256"
    ) != protocol.canonical_sha256(provenance_rows):
        raise AuditRecoveryError("historical provenance authorization differs")
    provenance_root = args.provenance_root.expanduser().absolute()
    expected_plan_dir = provenance_root / protocol.CANONICAL_PLAN_RELATIVE_PATH
    if args.plan_dir.expanduser().absolute() != expected_plan_dir:
        raise AuditRecoveryError("historical plan path differs")
    _validate_provenance_tree(provenance_root, provenance_rows)
    complete = _validate_run_and_ledgers(
        run_complete_path=args.run_complete,
        raw_ledger_path=args.raw_ledger,
        raw_inventory_path=args.raw_inventory,
        failure_log_path=args.failure_log,
    )
    with _historical_provenance_context(provenance_root):
        old_ownership, old_guest, old_cache, old_authorization = (
            _validate_original_chain(
                plan_dir=args.plan_dir,
                ownership_path=args.original_ownership,
                guest_path=args.original_guest,
                cache_path=args.original_cache,
                authorization_path=args.original_authorization,
            )
        )
    fresh_ownership, fresh_guest, fresh_cache = _validate_fresh_chain(
        ownership_path=args.fresh_ownership,
        guest_path=args.fresh_guest,
        cache_path=args.fresh_cache,
    )
    superseded_recovery_host = _validate_superseded_recovery_host(args)
    preflight_landlock, preflight_probe = _validate_cuda_preflight(
        args.preflight_landlock,
        args.preflight_probe,
        active_root=Path(execution["active_root"]),
        python_executable=Path(execution["python_executable"]),
        roots_manifest_path=Path(execution["paths"]["roots_manifest"]),
        roots_manifest_sha256=execution["roots_manifest_sha256"],
        bootstrap_manifest=bootstrap_import_roots["manifest"],
        output_root=args.preflight_output_root,
        canary_protected_root=args.preflight_canary_protected_root,
        canary_output_root=args.preflight_canary_output_root,
        device_files=args.device_file,
        closure_scope="final_recovery",
        expected_closure_files=closure,
    )
    expected_preflight = {
        "landlock_receipt": preflight_landlock,
        "landlock_file": _file_record(args.preflight_landlock),
        "probe_receipt": preflight_probe,
        "probe_file": _file_record(args.preflight_probe),
        "device_rules": preflight_landlock["device_rules"],
    }
    if (
        receipt.get("preflight") != expected_preflight
        or preflight_probe["provider"].get("pod_id") != fresh_ownership["pod_id"]
    ):
        raise AuditRecoveryError("recovery preflight authorization differs")
    _validate_fresh_authority_clock(receipt, fresh_ownership, now_unix=now)
    expected_old = {
        "ownership": old_ownership["receipt_sha256"],
        "guest": old_guest["receipt_sha256"],
        "cache": old_cache["receipt_sha256"],
        "authorization": old_authorization["receipt_sha256"],
        "termination_audit": _json(args.termination_audit)["receipt_sha256"],
        "frozen_termination": _json(args.frozen_termination)["receipt_sha256"],
    }
    expected_fresh = {
        "ownership": fresh_ownership["receipt_sha256"],
        "guest": fresh_guest["receipt_sha256"],
        "cache": fresh_cache["receipt_sha256"],
    }
    if (
        receipt.get("original_receipts") != expected_old
        or receipt.get("superseded_recovery_host") != superseded_recovery_host
        or receipt.get("fresh_receipts") != expected_fresh
        or receipt.get("fresh_pod_id") != fresh_ownership["pod_id"]
        or complete["receipt_sha256"] != receipt["raw_run_receipt_sha256"]
    ):
        raise AuditRecoveryError("recovery dual receipt chain differs")
    authorized_at = _utc(
        str(receipt.get("authorized_at_utc", "")), "recovery authorization"
    )
    source_test_files = _source_test_records(closure)
    local_test_receipt = _validate_test_receipt(
        _canonical_json_receipt(args.local_test_receipt, "local test receipt"),
        kind="local",
        expected_source_test_files=source_test_files,
        authorized_at=authorized_at,
    )
    target_host_test_receipt = _validate_test_receipt(
        _canonical_json_receipt(
            args.target_host_test_receipt, "target-host test receipt"
        ),
        kind="target_host",
        expected_source_test_files=source_test_files,
        qualification_ownership_path=args.target_qualification_ownership,
        qualification_landlock_path=args.target_qualification_landlock,
        qualification_cuda_path=args.target_qualification_cuda_preflight,
        authorized_at=authorized_at,
    )
    if (
        receipt.get("test_receipts")
        != {"local": local_test_receipt, "target_host": target_host_test_receipt}
        or local_test_receipt["code_freeze_commit"]
        != target_host_test_receipt["code_freeze_commit"]
        or review["code_freeze_commit"] != local_test_receipt["code_freeze_commit"]
        or review["source_test_inventory_sha256"]
        != local_test_receipt["source_test_inventory_sha256"]
        or target_host_test_receipt["target_host"]["pod_id"]
        == fresh_ownership["pod_id"]
    ):
        raise AuditRecoveryError("recovery test receipt chain differs")
    _validate_reviewed_external_evidence(review, args)
    external_paths = {
        "run_complete": args.run_complete,
        "raw_ledger": args.raw_ledger,
        "raw_inventory": args.raw_inventory,
        "failure_log": args.failure_log,
        "original_ownership": args.original_ownership,
        "original_guest": args.original_guest,
        "original_cache": args.original_cache,
        "original_authorization": args.original_authorization,
        "termination_audit": args.termination_audit,
        "postdelete_inventory": args.postdelete_inventory,
        "frozen_termination": args.frozen_termination,
        "superseded_runtime_block": args.superseded_runtime_block,
        "superseded_termination_audit": args.superseded_termination_audit,
        "superseded_frozen_termination": args.superseded_frozen_termination,
        "superseded_postdelete_inventory": args.superseded_postdelete_inventory,
        "fresh_ownership": args.fresh_ownership,
        "fresh_guest": args.fresh_guest,
        "fresh_cache": args.fresh_cache,
        "preflight_landlock": args.preflight_landlock,
        "preflight_probe": args.preflight_probe,
        "local_test_receipt": args.local_test_receipt,
        "target_host_test_receipt": args.target_host_test_receipt,
        "target_qualification_ownership": args.target_qualification_ownership,
        "target_qualification_landlock": args.target_qualification_landlock,
        "target_qualification_cuda_preflight": (
            args.target_qualification_cuda_preflight
        ),
        "roots_manifest": args.roots_manifest,
    }
    expected_external = {
        name: _file_record(path) for name, path in sorted(external_paths.items())
    }
    if receipt.get("external_files") != expected_external:
        raise AuditRecoveryError("recovery external file closure differs")
    env_expected = {
        "RUNPOD_POD_ID": str(fresh_ownership["pod_id"]),
        "RUNPOD_VOLUME_ID": protocol.NETWORK_VOLUME_ID,
        "RUNPOD_DC_ID": protocol.DATA_CENTER_ID,
    }
    if any(os.environ.get(name) != expected for name, expected in env_expected.items()):
        raise AuditRecoveryError("recovery process is outside the fresh owned guest")
    return receipt


def _parse_external_raw_ledger(path: Path, raw_root: Path) -> dict[str, str]:
    prefix = raw_root.resolve(strict=True).as_posix() + "/"
    result: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        digest, separator, absolute = line.partition("  ")
        if (
            separator != "  "
            or HEX64.fullmatch(digest) is None
            or not absolute.startswith(prefix)
        ):
            raise AuditRecoveryError("raw ledger row escaped canonical root")
        relative = absolute.removeprefix(prefix)
        if (
            not relative
            or relative.startswith("/")
            or ".." in Path(relative).parts
            or relative in result
        ):
            raise AuditRecoveryError("raw ledger contains an unsafe/duplicate path")
        result[relative] = digest
    return result


def _rehash_raw_tree(raw_root: Path, raw_ledger_path: Path) -> dict[str, Any]:
    root = raw_root.resolve(strict=True)
    expected = _parse_external_raw_ledger(raw_ledger_path, root)
    expected_directories = _expected_directory_inventory(list(expected))
    observed_directories: list[str] = []
    rows: list[dict[str, Any]] = []
    observed_paths: set[str] = set()
    for path in root.rglob("*"):
        details = path.lstat()
        relative = path.relative_to(root).as_posix()
        if stat.S_ISLNK(details.st_mode):
            raise AuditRecoveryError("raw tree contains a symlink")
        if stat.S_ISDIR(details.st_mode):
            if relative not in expected_directories:
                raise AuditRecoveryError(f"raw tree has an extra directory: {relative}")
            observed_directories.append(relative)
            continue
        if not stat.S_ISREG(details.st_mode):
            raise AuditRecoveryError(f"raw tree contains a special file: {relative}")
        if relative in observed_paths:
            raise AuditRecoveryError("raw tree path is duplicated")
        if details.st_nlink != 1:
            raise AuditRecoveryError("raw file has a non-unique hard link")
        digest = _sha256(path)
        if expected.get(relative) != digest:
            raise AuditRecoveryError(f"raw file hash differs: {relative}")
        rows.append({"path": relative, "bytes": details.st_size, "sha256": digest})
        observed_paths.add(relative)
    rows.sort(key=lambda row: str(row["path"]))
    observed_directories.sort()
    if (
        set(expected) != observed_paths
        or len(rows) != 36
        or observed_directories != expected_directories
    ):
        raise AuditRecoveryError("raw tree inventory differs")
    complete = _json(root / "RUN_COMPLETE.json")
    if _self_hash(complete, "raw RUN_COMPLETE") != ORIGINAL_RUN_RECEIPT_SHA256:
        raise AuditRecoveryError("raw RUN_COMPLETE self-hash differs")
    records = complete.get("records")
    if not isinstance(records, list) or len(records) != 35:
        raise AuditRecoveryError("raw RUN_COMPLETE manifest differs")
    by_path = {str(row["path"]): row for row in rows}
    for record in records:
        row = by_path.get(str(record.get("path")))
        if (
            row is None
            or row["bytes"] != record.get("bytes")
            or row["sha256"] != record.get("sha256")
        ):
            raise AuditRecoveryError("raw manifest/file differs")
    core = {
        "status": "pass_exact_36_file_rehash",
        "raw_root": root.as_posix(),
        "file_count": len(rows),
        "total_bytes": sum(int(row["bytes"]) for row in rows),
        "file_inventory_sha256": protocol.canonical_sha256(rows),
        "directory_count": len(observed_directories),
        "directory_inventory_sha256": protocol.canonical_sha256(observed_directories),
        "run_receipt_sha256": complete["receipt_sha256"],
        "external_ledger_file_sha256": _sha256(raw_ledger_path),
    }
    return {**core, "receipt_sha256": protocol.canonical_sha256(core)}


def _normalize_j_inventory(maps: Mapping[Any, Any]) -> tuple[int, ...]:
    seen: set[int] = set()
    for key in maps:
        if isinstance(key, bool):
            raise audit.CalibrationAuditError("J-lens layer identifier is noncanonical")
        if isinstance(key, int):
            layer = key
        elif isinstance(key, str):
            try:
                layer = int(key)
            except ValueError as exc:
                raise audit.CalibrationAuditError(
                    "J-lens layer identifier is noncanonical"
                ) from exc
            if key != str(layer):
                raise audit.CalibrationAuditError(
                    "J-lens layer identifier is noncanonical"
                )
        else:
            raise audit.CalibrationAuditError("J-lens layer identifier is noncanonical")
        if layer in seen:
            raise audit.CalibrationAuditError("J-lens layer identifier is duplicated")
        seen.add(layer)
    return tuple(sorted(seen))


_OBSERVED_J_INVENTORY: dict[str, Any] | None = None


def _load_j_checkpoint_recovery(
    j_lens_path: Path, watchdog: Any
) -> tuple[Path, Mapping[Any, Any], dict[str, Any]]:
    import torch

    global _OBSERVED_J_INVENTORY  # noqa: PLW0603
    lexical = j_lens_path.expanduser().absolute()
    if lexical.is_symlink():
        raise audit.CalibrationAuditError("J-lens checkpoint is a symlink")
    path = lexical.resolve(strict=True)
    watchdog.check()
    if (
        not path.is_file()
        or protocol.sha256_file(path) != protocol.J_LENS_SPEC["sha256"]
    ):
        raise audit.CalibrationAuditError("J-lens checkpoint hash differs")
    watchdog.check()
    checkpoint = torch.load(path, map_location="cpu", weights_only=True, mmap=True)
    if (
        not isinstance(checkpoint, Mapping)
        or not {"J", "n_prompts", "d_model"} <= set(checkpoint)
        or int(checkpoint["n_prompts"])
        != int(protocol.J_LENS_SPEC["release_config"]["prompts_fitted"])
        or int(checkpoint["d_model"]) != protocol.WIDTH
        or not isinstance(checkpoint["J"], Mapping)
    ):
        raise audit.CalibrationAuditError("J-lens checkpoint metadata differs")
    maps = checkpoint["J"]
    available = _normalize_j_inventory(maps)
    required = tuple(protocol.J_LAYERS)
    if not set(required) <= set(available):
        raise audit.CalibrationAuditError("J-lens map inventory differs")
    filtered = {
        layer: maps[layer] if layer in maps else maps[str(layer)] for layer in required
    }
    extras = tuple(layer for layer in available if layer not in set(required))
    inventory = {
        "available_layers": list(available),
        "required_layers": list(required),
        "unused_extra_layers": list(extras),
        "available_map_count": len(available),
        "required_map_count": len(required),
        "inventory_sha256": protocol.canonical_sha256(list(available)),
    }
    _OBSERVED_J_INVENTORY = inventory
    return (
        path,
        filtered,
        {
            "sha256": protocol.J_LENS_SPEC["sha256"],
            # Preserve the exact frozen scientific-audit metadata shape.  The
            # complete superset inventory is recorded separately in
            # recovery_audit.j_checkpoint_inventory via _OBSERVED_J_INVENTORY.
            "map_count": len(required),
            "revision": protocol.J_LENS_SPEC["revision"],
        },
    )


@contextlib.contextmanager
def _zero_forward_guards() -> Iterator[dict[str, int]]:
    import torch
    import transformers
    from transformers.models.auto.auto_factory import _BaseAutoModelClass

    counts = {"torch_module_calls": 0, "transformers_model_load_calls": 0}
    original_call_impl = torch.nn.Module._call_impl

    def blocked_module_call(*_args: Any, **_kwargs: Any) -> Any:
        counts["torch_module_calls"] += 1
        raise AuditRecoveryError("a torch.nn.Module call is forbidden in recovery")

    torch.nn.Module._call_impl = blocked_module_call
    restored: list[tuple[Any, Any]] = []
    try:
        loader_bases = [transformers.PreTrainedModel, _BaseAutoModelClass]
        for optional_name in ("TFPreTrainedModel", "FlaxPreTrainedModel"):
            optional = vars(transformers).get(optional_name)
            if optional is not None:
                loader_bases.append(optional)
        for cls in loader_bases:
            descriptor = cls.__dict__["from_pretrained"]
            restored.append((cls, descriptor))

            def blocked_loader(_cls: Any, *_args: Any, **_kwargs: Any) -> Any:
                counts["transformers_model_load_calls"] += 1
                raise AuditRecoveryError(
                    "a Transformers model load is forbidden in recovery"
                )

            setattr(cls, "from_pretrained", classmethod(blocked_loader))
        yield counts
    finally:
        torch.nn.Module._call_impl = original_call_impl
        for cls, descriptor in restored:
            setattr(cls, "from_pretrained", descriptor)


def _recovery_watchdog_class(authorization: Mapping[str, Any]) -> type:
    class RecoveryWatchdog:
        def __init__(
            self,
            _binding: Mapping[str, Any],
            *,
            audit_started_at_unix: float | None = None,
        ) -> None:
            self.started = float(authorization["recovery_started_at_unix"])
            self.deadline = float(authorization["recovery_deadline_at_unix"])
            self.rate = float(authorization["hourly_price_usd"])
            self.audit_started_at_unix = (
                time.time()
                if audit_started_at_unix is None
                else float(audit_started_at_unix)
            )
            if not self.started <= self.audit_started_at_unix < self.deadline:
                raise audit.CalibrationAuditError(
                    "recovery audit did not start inside its 60-minute authority"
                )

        def check(self) -> None:
            now = time.time()
            elapsed = now - self.started
            if (
                elapsed < 0
                or now >= self.deadline
                or elapsed > RECOVERY_SECONDS
                or self.rate * elapsed / 3600 > RECOVERY_MAX_SPEND_USD
            ):
                raise audit.CalibrationAuditError(
                    "recovery audit stopped at the 60-minute/$6 boundary"
                )

    return RecoveryWatchdog


@contextlib.contextmanager
def _patched_audit_runtime(
    authorization: Mapping[str, Any], run_complete: Mapping[str, Any]
) -> Iterator[None]:
    original_loader = audit._load_j_checkpoint  # noqa: SLF001
    original_watchdog = audit._AuditBudgetWatchdog  # noqa: SLF001
    original_external = audit._audit_external_receipt_chain  # noqa: SLF001
    historical_now = float(run_complete["resource"]["run_completed_at_unix"])

    def historical_external(**kwargs: Any) -> dict[str, Any]:
        kwargs["now_unix"] = historical_now
        return original_external(**kwargs)

    audit._load_j_checkpoint = _load_j_checkpoint_recovery  # type: ignore[attr-defined]  # noqa: SLF001
    audit._AuditBudgetWatchdog = _recovery_watchdog_class(authorization)  # type: ignore[attr-defined]  # noqa: SLF001
    audit._audit_external_receipt_chain = historical_external  # type: ignore[attr-defined]  # noqa: SLF001
    try:
        yield
    finally:
        audit._load_j_checkpoint = original_loader  # type: ignore[attr-defined]  # noqa: SLF001
        audit._AuditBudgetWatchdog = original_watchdog  # type: ignore[attr-defined]  # noqa: SLF001
        audit._audit_external_receipt_chain = original_external  # type: ignore[attr-defined]  # noqa: SLF001


def _recovery_metadata(
    *,
    authorization: Mapping[str, Any],
    confinement: Mapping[str, Any],
    preflight_landlock: Mapping[str, Any],
    preflight_probe: Mapping[str, Any],
    executable_isolation: Mapping[str, Any],
    provenance_pre_rehash: Mapping[str, Any],
    provenance_post_rehash: Mapping[str, Any],
    pre_rehash: Mapping[str, Any],
    post_rehash: Mapping[str, Any],
    guards: Mapping[str, int],
    module_guards: Mapping[str, int],
    bootstrap_entry_phase: Mapping[str, Any],
    bootstrap_prepublication_phase: Mapping[str, Any],
    marker: Mapping[str, Any],
) -> dict[str, Any]:
    if _OBSERVED_J_INVENTORY is None:
        raise AuditRecoveryError("corrected J inventory was not observed")
    for value, phase in (
        (bootstrap_entry_phase, BOOTSTRAP_EXECUTE_ENTRY_PHASE),
        (bootstrap_prepublication_phase, BOOTSTRAP_PREPUBLICATION_PHASE),
    ):
        if (
            _self_hash(value, "confined bootstrap phase") != value.get("receipt_sha256")
            or value.get("status") != "pass_hash_bound_bootstrap_phase"
            or value.get("phase") != phase
            or not isinstance(value.get("attestation"), Mapping)
            or value.get("attestation_receipt_sha256")
            != value["attestation"].get("receipt_sha256")
        ):
            raise AuditRecoveryError("confined bootstrap phase differs")
    if (
        bootstrap_entry_phase["attestation"]
        != bootstrap_prepublication_phase["attestation"]
    ):
        raise AuditRecoveryError("confined bootstrap counters changed during recovery")
    test_receipts = authorization.get("test_receipts")
    if not isinstance(test_receipts, Mapping) or set(test_receipts) != {
        "local",
        "target_host",
    }:
        raise AuditRecoveryError("recovery test receipt chain is missing")
    local_test_receipt = test_receipts["local"]
    target_host_test_receipt = test_receipts["target_host"]
    if (
        not isinstance(local_test_receipt, Mapping)
        or not isinstance(target_host_test_receipt, Mapping)
        or local_test_receipt.get("code_freeze_commit")
        != target_host_test_receipt.get("code_freeze_commit")
        or local_test_receipt.get("source_test_inventory_sha256")
        != target_host_test_receipt.get("source_test_inventory_sha256")
    ):
        raise AuditRecoveryError("recovery test receipt cross-links differ")
    core = {
        "recovery_protocol_version": RECOVERY_PROTOCOL_VERSION,
        "status": "pass_disclosed_post_run_technical_recovery",
        "correction": "required_j_layers_subset_of_hash_pinned_release_inventory",
        "provider_review_status": authorization["review"]["provider_status"],
        "provider_review_approval_claimed": authorization["review"][
            "provider_approval_claimed"
        ],
        "provider_review_ready_to_freeze_verdict": authorization["review"][
            "provider_ready_to_freeze_verdict"
        ],
        "provider_review_source_and_tests_seen": authorization["review"][
            "source_and_tests_reviewed_by_provider"
        ],
        "provider_reviewed_packet_was_pre_fix": authorization["review"][
            "reviewed_packet_was_pre_fix"
        ],
        "provider_reviewed_final_source": authorization["review"][
            "final_source_reviewed_by_provider"
        ],
        "provider_reviewed_final_bytes_unchanged": authorization["review"][
            "provider_reviewed_final_bytes_unchanged"
        ],
        "recovery_authorization_receipt_sha256": authorization["receipt_sha256"],
        "attempt_id": authorization["execution"]["attempt_id"],
        "attempt_marker_receipt_sha256": marker["receipt_sha256"],
        "command_sha256": authorization["execution"]["command_sha256"],
        "recovery_bound_paths_sha256": authorization["recovery_bound_paths_sha256"],
        "plan_manifest_sha256": authorization["plan_manifest_sha256"],
        "local_test_receipt_sha256": local_test_receipt["receipt_sha256"],
        "target_host_test_receipt_sha256": target_host_test_receipt["receipt_sha256"],
        "code_freeze_commit": local_test_receipt["code_freeze_commit"],
        "source_test_inventory_sha256": local_test_receipt[
            "source_test_inventory_sha256"
        ],
        "recovery_plan_sha256": _bound_recovery_hash(
            authorization,
            "docs/consciousness_sae_target_blind_calibration/"
            "AUDIT_RECOVERY_20260714.md",
        ),
        "recovery_source_sha256": _bound_recovery_hash(
            authorization,
            "experiments/consciousness_sae_target_blind_calibration/audit_recovery.py",
        ),
        "confined_bootstrap_sha256": _bound_recovery_hash(
            authorization,
            "experiments/consciousness_sae_target_blind_calibration/"
            "confined_bootstrap.py",
        ),
        "scientific_equivalence_source_sha256": _bound_recovery_hash(
            authorization,
            "experiments/consciousness_sae_target_blind_calibration/"
            "scientific_equivalence.py",
        ),
        "landlock_launcher_sha256": _bound_recovery_hash(
            authorization,
            "experiments/consciousness_sae_target_blind_calibration/"
            "landlock_launcher.py",
        ),
        "bundle_verifier_sha256": _bound_recovery_hash(
            authorization,
            "experiments/consciousness_sae_target_blind_calibration/"
            "recovery_bundle_verifier.py",
        ),
        "recovery_test_sha256": _bound_recovery_hash(
            authorization,
            "tests/consciousness_sae_target_blind_calibration/test_audit_recovery.py",
        ),
        "confined_bootstrap_test_sha256": _bound_recovery_hash(
            authorization,
            "tests/consciousness_sae_target_blind_calibration/"
            "test_confined_bootstrap.py",
        ),
        "scientific_equivalence_test_sha256": _bound_recovery_hash(
            authorization,
            "tests/consciousness_sae_target_blind_calibration/"
            "test_scientific_equivalence.py",
        ),
        "scientific_equivalence_json_sha256": _bound_recovery_hash(
            authorization,
            "docs/consciousness_sae_target_blind_calibration/"
            "AUDIT_RECOVERY_SCIENTIFIC_EQUIVALENCE.json",
        ),
        "scientific_equivalence_markdown_sha256": _bound_recovery_hash(
            authorization,
            "docs/consciousness_sae_target_blind_calibration/"
            "AUDIT_RECOVERY_SCIENTIFIC_EQUIVALENCE.md",
        ),
        "landlock_test_sha256": _bound_recovery_hash(
            authorization,
            "tests/consciousness_sae_target_blind_calibration/"
            "test_landlock_launcher.py",
        ),
        "bundle_verifier_test_sha256": _bound_recovery_hash(
            authorization,
            "tests/consciousness_sae_target_blind_calibration/"
            "test_recovery_bundle_verifier.py",
        ),
        "historical_review_adjudication_json_sha256": _bound_recovery_hash(
            authorization,
            HISTORICAL_INCOMPLETE_REVIEW_ADJUDICATION_JSON,
        ),
        "historical_review_adjudication_markdown_sha256": _bound_recovery_hash(
            authorization,
            HISTORICAL_INCOMPLETE_REVIEW_ADJUDICATION_MARKDOWN,
        ),
        "historical_v2_review_adjudication_json_sha256": _bound_recovery_hash(
            authorization,
            HISTORICAL_V2_PRO_REVIEW_ADJUDICATION_JSON,
        ),
        "historical_v2_review_adjudication_markdown_sha256": (
            _bound_recovery_hash(
                authorization,
                HISTORICAL_V2_PRO_REVIEW_ADJUDICATION_MARKDOWN,
            )
        ),
        "historical_v3_review_adjudication_json_sha256": _bound_recovery_hash(
            authorization,
            HISTORICAL_V3_NEGATIVE_REVIEW_ADJUDICATION_JSON,
        ),
        "historical_v3_review_adjudication_markdown_sha256": _bound_recovery_hash(
            authorization,
            HISTORICAL_V3_NEGATIVE_REVIEW_ADJUDICATION_MARKDOWN,
        ),
        "historical_v3_review_response_sha256": _bound_recovery_hash(
            authorization,
            f"{HISTORICAL_V3_NEGATIVE_REVIEW_DIRECTORY}/response.json",
        ),
        "historical_v3_review_manifest_sha256": _bound_recovery_hash(
            authorization,
            f"{HISTORICAL_V3_NEGATIVE_REVIEW_DIRECTORY}/review_manifest.json",
        ),
        "historical_v4_review_adjudication_json_sha256": _bound_recovery_hash(
            authorization,
            HISTORICAL_V4_NEGATIVE_REVIEW_ADJUDICATION_JSON,
        ),
        "historical_v4_review_adjudication_markdown_sha256": _bound_recovery_hash(
            authorization,
            HISTORICAL_V4_NEGATIVE_REVIEW_ADJUDICATION_MARKDOWN,
        ),
        "historical_v4_review_response_sha256": _bound_recovery_hash(
            authorization,
            f"{HISTORICAL_V4_NEGATIVE_REVIEW_DIRECTORY}/response.json",
        ),
        "historical_v4_review_manifest_sha256": _bound_recovery_hash(
            authorization,
            f"{HISTORICAL_V4_NEGATIVE_REVIEW_DIRECTORY}/review_manifest.json",
        ),
        "historical_v5_review_adjudication_json_sha256": _bound_recovery_hash(
            authorization,
            FINAL_V5_PRO_REVIEW_ADJUDICATION_JSON,
        ),
        "historical_v5_review_adjudication_markdown_sha256": _bound_recovery_hash(
            authorization,
            FINAL_V5_PRO_REVIEW_ADJUDICATION_MARKDOWN,
        ),
        "historical_v5_review_response_sha256": _bound_recovery_hash(
            authorization,
            f"{FINAL_V5_PRO_REVIEW_DIRECTORY}/response.json",
        ),
        "historical_v5_review_manifest_sha256": _bound_recovery_hash(
            authorization,
            f"{FINAL_V5_PRO_REVIEW_DIRECTORY}/review_manifest.json",
        ),
        "historical_v6_review_request_payload_sha256": _bound_recovery_hash(
            authorization,
            f"{FINAL_V6_PRO_REVIEW_DIRECTORY}/request_payload.json",
        ),
        "historical_v6_review_response_sha256": _bound_recovery_hash(
            authorization,
            f"{FINAL_V6_PRO_REVIEW_DIRECTORY}/response.json",
        ),
        "historical_v6_review_sha256": _bound_recovery_hash(
            authorization,
            f"{FINAL_V6_PRO_REVIEW_DIRECTORY}/review.md",
        ),
        "historical_v6_review_manifest_sha256": _bound_recovery_hash(
            authorization,
            f"{FINAL_V6_PRO_REVIEW_DIRECTORY}/review_manifest.json",
        ),
        "historical_v6_review_request_sha256": _bound_recovery_hash(
            authorization,
            f"{FINAL_V6_PRO_REVIEW_DIRECTORY}/review_request.md",
        ),
        "final_v8_review_adjudication_json_sha256": _bound_recovery_hash(
            authorization,
            FINAL_V8_PRO_REVIEW_ADJUDICATION_JSON,
        ),
        "final_v8_review_adjudication_markdown_sha256": _bound_recovery_hash(
            authorization,
            FINAL_V8_PRO_REVIEW_ADJUDICATION_MARKDOWN,
        ),
        "final_v8_review_response_sha256": _bound_recovery_hash(
            authorization,
            f"{FINAL_V8_PRO_REVIEW_DIRECTORY}/response.json",
        ),
        "final_v8_review_manifest_sha256": _bound_recovery_hash(
            authorization,
            f"{FINAL_V8_PRO_REVIEW_DIRECTORY}/review_manifest.json",
        ),
        "reviewed_local_test_receipt_snapshot_sha256": _bound_recovery_hash(
            authorization,
            V8_LOCAL_TEST_RECEIPT_SNAPSHOT,
        ),
        "reviewed_target_host_test_receipt_snapshot_sha256": (
            _bound_recovery_hash(
                authorization,
                V8_TARGET_HOST_TEST_RECEIPT_SNAPSHOT,
            )
        ),
        "reviewed_target_qualification_ownership_snapshot_sha256": (
            _bound_recovery_hash(
                authorization,
                V8_TARGET_QUALIFICATION_OWNERSHIP_SNAPSHOT,
            )
        ),
        "reviewed_target_qualification_landlock_snapshot_sha256": (
            _bound_recovery_hash(
                authorization,
                V8_TARGET_QUALIFICATION_LANDLOCK_SNAPSHOT,
            )
        ),
        "reviewed_target_qualification_cuda_snapshot_sha256": (
            _bound_recovery_hash(
                authorization,
                V8_TARGET_QUALIFICATION_CUDA_SNAPSHOT,
            )
        ),
        "original_failed_audit_log_sha256": ORIGINAL_FAILURE_LOG_SHA256,
        "original_raw_run_receipt_sha256": ORIGINAL_RUN_RECEIPT_SHA256,
        "original_receipts": authorization["original_receipts"],
        "superseded_recovery_host": authorization["superseded_recovery_host"],
        "fresh_receipts": authorization["fresh_receipts"],
        "fresh_pod_id": authorization["fresh_pod_id"],
        "bootstrap_import_roots": authorization["bootstrap_import_roots"],
        "bootstrap_execute_entry_phase": dict(bootstrap_entry_phase),
        "bootstrap_prepublication_phase": dict(bootstrap_prepublication_phase),
        "bootstrap_postdispatch_assertion": (
            "same_process_bootstrap_assert_clean_runs_after_recovery_dispatch_returns"
        ),
        "preflight_landlock_receipt": dict(preflight_landlock),
        "preflight_landlock_receipt_sha256": preflight_landlock["receipt_sha256"],
        "preflight_probe_receipt": dict(preflight_probe),
        "preflight_probe_receipt_sha256": preflight_probe["receipt_sha256"],
        "landlock_confinement_receipt": dict(confinement),
        "landlock_confinement_receipt_sha256": confinement["receipt_sha256"],
        "write_confinement_policy": dict(LANDLOCK_POLICY),
        "write_confinement_claim": (
            "process-tree ABI-4 handled filesystem content/topology mutations "
            "confined to two output directories, with an exact /proc/self/task "
            "WRITE_FILE|TRUNCATE thread-name exception and exact NVIDIA "
            "WRITE_FILE exceptions"
        ),
        "landlock_limitations": {
            "metadata_operations_unhandled": True,
            "preopened_file_descriptors_unmediated": True,
            "sibling_processes_and_other_nfs_clients_unmediated": True,
            "device_ioctl_unhandled_in_abi4": True,
            "proc_self_task_path_beneath_write_truncate_exception": True,
            "read_only_mount_claimed": False,
        },
        "executable_isolation_receipt": dict(executable_isolation),
        "executable_isolation_receipt_sha256": executable_isolation["receipt_sha256"],
        "provenance_pre_rehash_receipt": dict(provenance_pre_rehash),
        "provenance_pre_rehash_receipt_sha256": provenance_pre_rehash["receipt_sha256"],
        "provenance_post_rehash_receipt": dict(provenance_post_rehash),
        "provenance_post_rehash_receipt_sha256": provenance_post_rehash[
            "receipt_sha256"
        ],
        "historical_provenance_unchanged": (
            provenance_pre_rehash["file_inventory_sha256"]
            == provenance_post_rehash["file_inventory_sha256"]
            and provenance_pre_rehash["directory_inventory_sha256"]
            == provenance_post_rehash["directory_inventory_sha256"]
        ),
        "pre_rehash_receipt": dict(pre_rehash),
        "pre_rehash_receipt_sha256": pre_rehash["receipt_sha256"],
        "post_rehash_receipt": dict(post_rehash),
        "post_rehash_receipt_sha256": post_rehash["receipt_sha256"],
        "raw_unchanged": (
            pre_rehash["file_inventory_sha256"] == post_rehash["file_inventory_sha256"]
            and pre_rehash["directory_inventory_sha256"]
            == post_rehash["directory_inventory_sha256"]
        ),
        "zero_forward_guards": dict(guards),
        "forbidden_module_guards": dict(module_guards),
        "j_checkpoint_inventory": dict(_OBSERVED_J_INVENTORY),
        "scientific_metrics_thresholds_layers_and_rows_changed": False,
        "fresh_model_execution_performed": False,
        "target_prompt_render_count": 0,
        "target_feature_vector_count": 0,
        "external_or_prior_outcome_inputs": [],
    }
    return {**core, "receipt_sha256": protocol.canonical_sha256(core)}


def _enrich_outputs(
    audit_receipt: Mapping[str, Any],
    summary: Mapping[str, Any],
    *,
    authorization: Mapping[str, Any],
    recovery: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    audit_core = dict(audit_receipt)
    audit_core.pop("receipt_sha256", None)
    original_campaign = {
        "campaign_started_at_unix": audit_core["campaign_started_at_unix"],
        "campaign_deadline_at_unix": audit_core["campaign_deadline_at_unix"],
        "hourly_price_usd": audit_core["hourly_price_usd"],
    }
    if original_campaign != {
        "campaign_started_at_unix": ORIGINAL_CAMPAIGN_STARTED_AT_UNIX,
        "campaign_deadline_at_unix": ORIGINAL_CAMPAIGN_DEADLINE_AT_UNIX,
        "hourly_price_usd": ORIGINAL_CAMPAIGN_HOURLY_PRICE_USD,
    }:
        raise AuditRecoveryError("original campaign fields differ")
    audit_core["original_execution_campaign"] = original_campaign
    recovery_campaign = {
        "started_at_unix": authorization["recovery_started_at_unix"],
        "deadline_at_unix": authorization["recovery_deadline_at_unix"],
        "hourly_price_usd": authorization["hourly_price_usd"],
        "max_spend_usd": authorization["max_spend_usd"],
    }
    audit_core["recovery_execution_campaign"] = recovery_campaign
    audit_core["recovery_audit"] = dict(recovery)
    enriched_audit = {
        **audit_core,
        "receipt_sha256": protocol.canonical_sha256(audit_core),
    }
    summary_core = dict(summary)
    summary_core.pop("receipt_sha256", None)
    summary_core["audit_receipt_sha256"] = enriched_audit["receipt_sha256"]
    summary_core["recovery_execution_campaign"] = recovery_campaign
    summary_core["recovery_audit"] = dict(recovery)
    enriched_summary = {
        **summary_core,
        "receipt_sha256": protocol.canonical_sha256(summary_core),
    }
    return enriched_audit, enriched_summary


def _publish_recovery_pair_atomic(
    audit_out: Path,
    summary_out: Path,
    audit_receipt: Mapping[str, Any],
    summary: Mapping[str, Any],
) -> Path:
    """Publish the recovered pair while keeping historical fields unchanged."""

    audit_path = audit_out.expanduser().absolute()
    summary_path = summary_out.expanduser().absolute()
    recovery_campaign = audit_receipt.get("recovery_execution_campaign")
    if (
        audit_path.parent != summary_path.parent
        or audit_path.name != "CALIBRATION_AUDIT.json"
        or summary_path.name != "CALIBRATION_SUMMARY.json"
        or audit_path.parent == audit_path.parent.parent
        or not isinstance(recovery_campaign, Mapping)
        or summary.get("recovery_execution_campaign") != recovery_campaign
    ):
        raise audit.CalibrationAuditError(
            "recovered audit outputs or recovery campaign differ"
        )
    deadline = float(recovery_campaign["deadline_at_unix"])
    destination = audit_path.parent
    parent = destination.parent
    partial = destination.with_name(f".{destination.name}.partial")
    quarantine = destination.with_name(f".{destination.name}.expired")
    if (
        not parent.is_dir()
        or parent.is_symlink()
        or os.path.lexists(destination)
        or os.path.lexists(partial)
        or os.path.lexists(quarantine)
    ):
        raise audit.CalibrationAuditError(
            "compact recovery publication destination is not fresh"
        )
    watchdog = audit._AuditBudgetWatchdog(  # noqa: SLF001
        audit_receipt,
        audit_started_at_unix=float(audit_receipt["audit_started_at_unix"]),
    )
    partial.mkdir(mode=0o700)
    published = False
    try:
        watchdog.check()
        staged_audit = partial / audit_path.name
        staged_summary = partial / summary_path.name
        audit._write_json(staged_audit, audit_receipt)  # noqa: SLF001
        watchdog.check()
        audit._write_json(staged_summary, summary)  # noqa: SLF001
        directory_fd = os.open(partial, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
        watchdog.check()
        os.replace(partial, destination)
        published = True
        watchdog.check()
        marker_core = {
            "schema_version": 1,
            "status": "complete",
            "study_id": protocol.STUDY_ID,
            "protocol_version": protocol.PROTOCOL_VERSION,
            "audit_receipt_sha256": audit_receipt["receipt_sha256"],
            "summary_receipt_sha256": summary["receipt_sha256"],
            "audit_file_sha256": protocol.sha256_file(audit_path),
            "summary_file_sha256": protocol.sha256_file(summary_path),
            "publication_completed_at_unix": time.time(),
            "recovery_deadline_at_unix": deadline,
        }
        marker = {
            **marker_core,
            "receipt_sha256": protocol.canonical_sha256(marker_core),
        }
        audit._write_json(  # noqa: SLF001
            destination / "PUBLICATION_COMPLETE.json", marker
        )
        destination_fd = os.open(destination, os.O_RDONLY)
        try:
            os.fsync(destination_fd)
        finally:
            os.close(destination_fd)
        parent_fd = os.open(parent, os.O_RDONLY)
        try:
            os.fsync(parent_fd)
        finally:
            os.close(parent_fd)
        watchdog.check()
        return destination / summary_path.name
    except BaseException:
        if published and os.path.lexists(destination):
            os.replace(destination, quarantine)
        raise


def _bound_recovery_hash(authorization: Mapping[str, Any], relative_path: str) -> str:
    rows = authorization.get("recovery_bound_files")
    if not isinstance(rows, list):
        raise AuditRecoveryError("recovery bound-file closure is missing")
    matches = [row for row in rows if row.get("path") == relative_path]
    if len(matches) != 1 or HEX64.fullmatch(str(matches[0].get("sha256", ""))) is None:
        raise AuditRecoveryError("recovery bound-file hash is missing")
    return str(matches[0]["sha256"])


def _claim_attempt(
    args: argparse.Namespace,
    authorization: Mapping[str, Any],
    confinement: Mapping[str, Any],
) -> dict[str, Any]:
    binding = authorization["execution"]
    attempt_root = Path(str(binding["attempt_root"]))
    authorize._require_no_symlink_components(  # noqa: SLF001
        attempt_root, "recovery attempt root"
    )
    if (
        not attempt_root.is_dir()
        or attempt_root.is_symlink()
        or args.output_root.expanduser().absolute()
        != Path(str(binding["paths"]["output_root"]))
        or not args.output_root.is_dir()
        or args.output_root.is_symlink()
        or args.attempt_marker.expanduser().absolute().parent
        != args.output_root.expanduser().absolute()
        or args.failure_out.expanduser().absolute().parent
        != args.output_root.expanduser().absolute()
        or args.landlock_receipt.expanduser().absolute()
        != Path(str(binding["paths"]["landlock_receipt"]))
        or not args.landlock_receipt.is_file()
        or os.path.lexists(args.attempt_marker)
        or os.path.lexists(args.failure_out)
        or os.path.lexists(args.audit_out.parent)
    ):
        raise AuditRecoveryError("recovery attempt namespace is not fresh")
    started = time.time()
    if not (
        float(authorization["recovery_started_at_unix"])
        <= started
        < float(authorization["recovery_deadline_at_unix"])
    ):
        raise AuditRecoveryError("recovery attempt began outside authority")
    core = {
        "schema_version": 1,
        "status": "claimed_exactly_once",
        "study_id": protocol.STUDY_ID,
        "run_id": RUN_ID,
        "attempt_id": binding["attempt_id"],
        "claimed_at_utc": _utc_text(datetime.fromtimestamp(started, timezone.utc)),
        "claimed_at_unix": started,
        "recovery_authorization_receipt_sha256": authorization["receipt_sha256"],
        "landlock_confinement_receipt_sha256": confinement["receipt_sha256"],
        "landlock_pid": confinement["pid"],
        "command_sha256": binding["command_sha256"],
        "recovery_source_sha256": _bound_recovery_hash(
            authorization,
            "experiments/consciousness_sae_target_blind_calibration/audit_recovery.py",
        ),
    }
    marker = {**core, "receipt_sha256": protocol.canonical_sha256(core)}
    _write_json_exclusive(args.attempt_marker, marker)
    return marker


def _write_failure_receipt(
    args: argparse.Namespace,
    authorization: Mapping[str, Any],
    marker: Mapping[str, Any],
    confinement: Mapping[str, Any],
    error: BaseException,
) -> None:
    message = str(error)
    if len(message) > 1000:
        message = message[:1000]
    core = {
        "schema_version": 1,
        "status": "failed_no_compact_success_publication",
        "study_id": protocol.STUDY_ID,
        "run_id": RUN_ID,
        "attempt_id": authorization["execution"]["attempt_id"],
        "failed_at_utc": _utc_text(datetime.now(timezone.utc)),
        "error_type": type(error).__name__,
        "error_message": message,
        "recovery_authorization_receipt_sha256": authorization["receipt_sha256"],
        "attempt_marker_receipt_sha256": marker["receipt_sha256"],
        "landlock_confinement_receipt_sha256": confinement["receipt_sha256"],
        "command_sha256": authorization["execution"]["command_sha256"],
        "recovery_source_sha256": marker["recovery_source_sha256"],
        "compact_success_directory_exists": args.audit_out.parent.exists(),
    }
    receipt = {**core, "receipt_sha256": protocol.canonical_sha256(core)}
    _write_json_exclusive(args.failure_out, receipt)


def execute_recovery(args: argparse.Namespace) -> Path:
    global _OBSERVED_J_INVENTORY  # noqa: PLW0603
    _OBSERVED_J_INVENTORY = None
    authorization_raw = _json(args.recovery_authorization)
    preflight = authorization_raw.get("preflight")
    if not isinstance(preflight, Mapping) or not isinstance(
        preflight.get("probe_receipt"), Mapping
    ):
        raise AuditRecoveryError("recovery preflight binding is missing")
    manifest_binding = _bootstrap_manifest_binding(
        args.roots_manifest,
        expected_file_sha256=args.roots_manifest_sha256,
        active_root=args.active_root,
    )
    bootstrap_roots, bootstrap_files = _bootstrap_protected_paths(manifest_binding)
    bootstrap_entry_attestation = _current_bootstrap_attestation(
        mode="execute-confined",
        active_root=args.active_root,
        python_executable=args.python_executable,
        roots_manifest_path=args.roots_manifest,
        roots_manifest_sha256=args.roots_manifest_sha256,
        manifest=manifest_binding["manifest"],
    )
    bootstrap_entry_phase = _bootstrap_phase_record(
        BOOTSTRAP_EXECUTE_ENTRY_PHASE, bootstrap_entry_attestation
    )
    confinement = _validate_landlock_receipt(
        _json(args.landlock_receipt),
        purpose="audit_recovery",
        receipt_path=args.landlock_receipt,
        output_root=args.output_root,
        protected_roots=[
            args.raw_root,
            args.provenance_root,
            args.canary_protected_root,
            *bootstrap_roots,
        ],
        protected_files=[
            args.raw_root / "RUN_COMPLETE.json",
            args.provenance_root
            / protocol.CANONICAL_PLAN_RELATIVE_PATH
            / "plan_manifest.json",
            args.recovery_authorization,
            *bootstrap_files,
        ],
        canary_output_root=args.canary_output_root,
        device_files=args.device_file,
        expected_authorization_sha256=str(authorization_raw["receipt_sha256"]),
        expected_preflight_receipt_sha256=str(
            preflight["probe_receipt"]["receipt_sha256"]
        ),
        require_current_pid=True,
    )
    if (
        confinement["device_rules"] != preflight.get("device_rules")
        or confinement["child_argv"]
        != authorization_raw.get("execution", {}).get("confined_child_argv")
        or confinement["child_argv_sha256"]
        != authorization_raw.get("execution", {}).get("confined_child_argv_sha256")
        or Path(sys.executable).resolve(strict=True).as_posix()
        != authorization_raw.get("execution", {}).get("python_executable")
        or Path.cwd().resolve(strict=True).as_posix()
        != authorization_raw.get("execution", {}).get("active_root")
        or "execute-confined" not in sys.argv
    ):
        raise AuditRecoveryError("confined execution did not match authorization")
    _validate_confinement_environment(args.output_root)
    # The issue phase already proved the live Git ancestry and byte-diff chain
    # and sealed its final HEAD into the self-hashed authorization.  ACTIVE is
    # intentionally a repository-free closure, so final validation is Git-free.
    authorization = validate_recovery_authorization(
        authorization_raw, args, validate_git=False
    )
    marker = _claim_attempt(args, authorization, confinement)
    try:
        raw_root = args.raw_root.resolve(strict=True)
        provenance_root = args.provenance_root.resolve(strict=True)
        executable_isolation = _validate_executable_isolation(
            provenance_root, authorization
        )
        provenance_pre_rehash = _validate_provenance_tree(
            provenance_root, authorization["historical_provenance_files"]
        )
        pre_rehash = _rehash_raw_tree(raw_root, args.raw_ledger)
        run_complete = _json(args.run_complete)
        guards: dict[str, int]
        module_guards: dict[str, int]
        with (
            _historical_provenance_context(provenance_root),
            _forbidden_module_guard() as module_guards,
            _patched_audit_runtime(authorization, run_complete),
            _zero_forward_guards() as guards,
        ):
            audit_receipt, summary = audit.audit(
                raw_root,
                args.plan_dir,
                model_snapshot=args.model_snapshot,
                j_lens_path=args.j_lens_path,
                ownership_receipt=args.original_ownership,
                guest_receipt=args.original_guest,
                cache_receipt=args.original_cache,
                authorization_receipt=args.original_authorization,
                artifact_device=args.artifact_device,
            )
            if guards != {
                "torch_module_calls": 0,
                "transformers_model_load_calls": 0,
            }:
                raise AuditRecoveryError("a zero-forward recovery guard fired")
            if module_guards != {"forbidden_module_import_attempts": 0}:
                raise AuditRecoveryError("a forbidden module recovery guard fired")
            post_rehash = _rehash_raw_tree(raw_root, args.raw_ledger)
            if (
                pre_rehash["file_inventory_sha256"]
                != post_rehash["file_inventory_sha256"]
            ):
                raise AuditRecoveryError("raw tree changed during recovery")
            provenance_post_rehash = _validate_provenance_tree(
                provenance_root, authorization["historical_provenance_files"]
            )
            if (
                provenance_pre_rehash["file_inventory_sha256"]
                != provenance_post_rehash["file_inventory_sha256"]
            ):
                raise AuditRecoveryError("historical provenance changed")
            bootstrap_prepublication_attestation = _current_bootstrap_attestation(
                mode="execute-confined",
                active_root=args.active_root,
                python_executable=args.python_executable,
                roots_manifest_path=args.roots_manifest,
                roots_manifest_sha256=args.roots_manifest_sha256,
                manifest=manifest_binding["manifest"],
            )
            bootstrap_prepublication_phase = _bootstrap_phase_record(
                BOOTSTRAP_PREPUBLICATION_PHASE,
                bootstrap_prepublication_attestation,
            )
            recovery = _recovery_metadata(
                authorization=authorization,
                confinement=confinement,
                preflight_landlock=preflight["landlock_receipt"],
                preflight_probe=preflight["probe_receipt"],
                executable_isolation=executable_isolation,
                provenance_pre_rehash=provenance_pre_rehash,
                provenance_post_rehash=provenance_post_rehash,
                pre_rehash=pre_rehash,
                post_rehash=post_rehash,
                guards=guards,
                module_guards=module_guards,
                bootstrap_entry_phase=bootstrap_entry_phase,
                bootstrap_prepublication_phase=bootstrap_prepublication_phase,
                marker=marker,
            )
            enriched_audit, enriched_summary = _enrich_outputs(
                audit_receipt,
                summary,
                authorization=authorization,
                recovery=recovery,
            )
            return _publish_recovery_pair_atomic(
                args.audit_out,
                args.summary_out,
                enriched_audit,
                enriched_summary,
            )
    except BaseException as exc:
        try:
            _write_failure_receipt(args, authorization, marker, confinement, exc)
        except BaseException as receipt_exc:
            raise AuditRecoveryError(
                f"recovery failed and failure receipt could not publish: {receipt_exc}"
            ) from exc
        raise


def _add_evidence_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--plan-dir", type=Path, required=True)
    parser.add_argument("--raw-root", type=Path, required=True)
    parser.add_argument("--run-complete", type=Path, required=True)
    parser.add_argument("--raw-ledger", type=Path, required=True)
    parser.add_argument("--raw-inventory", type=Path, required=True)
    parser.add_argument("--failure-log", type=Path, required=True)
    parser.add_argument("--original-ownership", type=Path, required=True)
    parser.add_argument("--original-guest", type=Path, required=True)
    parser.add_argument("--original-cache", type=Path, required=True)
    parser.add_argument("--original-authorization", type=Path, required=True)
    parser.add_argument("--termination-audit", type=Path, required=True)
    parser.add_argument("--postdelete-inventory", type=Path, required=True)
    parser.add_argument("--frozen-termination", type=Path, required=True)
    parser.add_argument("--superseded-runtime-block", type=Path, required=True)
    parser.add_argument("--superseded-termination-audit", type=Path, required=True)
    parser.add_argument("--superseded-frozen-termination", type=Path, required=True)
    parser.add_argument("--superseded-postdelete-inventory", type=Path, required=True)
    parser.add_argument("--fresh-ownership", type=Path, required=True)
    parser.add_argument("--fresh-guest", type=Path, required=True)
    parser.add_argument("--fresh-cache", type=Path, required=True)
    parser.add_argument("--preflight-landlock", type=Path, required=True)
    parser.add_argument("--preflight-probe", type=Path, required=True)
    parser.add_argument("--local-test-receipt", type=Path, required=True)
    parser.add_argument("--target-host-test-receipt", type=Path, required=True)
    parser.add_argument("--target-qualification-ownership", type=Path, required=True)
    parser.add_argument("--target-qualification-landlock", type=Path, required=True)
    parser.add_argument(
        "--target-qualification-cuda-preflight", type=Path, required=True
    )


def _add_execution_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--attempt-id", required=True)
    parser.add_argument("--active-root", type=Path, required=True)
    parser.add_argument("--python-executable", type=Path, required=True)
    parser.add_argument("--roots-manifest", type=Path, required=True)
    parser.add_argument("--roots-manifest-sha256", required=True)
    parser.add_argument("--provenance-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--preflight-output-root", type=Path, required=True)
    parser.add_argument("--preflight-canary-protected-root", type=Path, required=True)
    parser.add_argument("--preflight-canary-output-root", type=Path, required=True)
    parser.add_argument("--canary-protected-root", type=Path, required=True)
    parser.add_argument("--canary-output-root", type=Path, required=True)
    parser.add_argument("--landlock-receipt", type=Path, required=True)
    parser.add_argument(
        "--device-file", type=Path, action="append", required=True, dest="device_file"
    )
    parser.add_argument("--model-snapshot", type=Path, required=True)
    parser.add_argument("--j-lens-path", type=Path, required=True)
    parser.add_argument("--artifact-device", default="cuda:0")
    parser.add_argument("--audit-out", type=Path, required=True)
    parser.add_argument("--summary-out", type=Path, required=True)
    parser.add_argument("--attempt-marker", type=Path, required=True)
    parser.add_argument("--failure-out", type=Path, required=True)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    test_receipt = commands.add_parser(
        "test-receipt",
        help="Run the frozen focused suite and publish its self-hashed receipt",
    )
    test_receipt.add_argument("--kind", choices=TEST_RECEIPT_KINDS, required=True)
    test_receipt.add_argument("--code-freeze-commit", required=True)
    test_receipt.add_argument("--host-created-at-utc")
    test_receipt.add_argument("--qualification-ownership", type=Path)
    test_receipt.add_argument("--qualification-landlock", type=Path)
    test_receipt.add_argument("--qualification-cuda-preflight", type=Path)
    test_receipt.add_argument("--output", type=Path, required=True)

    issue = commands.add_parser("issue", help="Issue the fresh audit-only authority")
    _add_evidence_args(issue)
    _add_execution_args(issue)
    issue.add_argument("--hourly-price-usd", type=float, required=True)
    issue.add_argument("--output", type=Path, required=True)

    execute = commands.add_parser(
        "execute-confined", help="Execute once after same-PID Landlock confinement"
    )
    _add_evidence_args(execute)
    _add_execution_args(execute)
    execute.add_argument("--recovery-authorization", type=Path, required=True)

    probe = commands.add_parser(
        "preflight-child", help="Run the target-free CUDA probe after confinement"
    )
    probe.add_argument("--active-root", type=Path, required=True)
    probe.add_argument("--python-executable", type=Path, required=True)
    probe.add_argument("--roots-manifest", type=Path, required=True)
    probe.add_argument("--roots-manifest-sha256", required=True)
    probe.add_argument("--landlock-receipt", type=Path, required=True)
    probe.add_argument("--output-root", type=Path, required=True)
    probe.add_argument("--canary-protected-root", type=Path, required=True)
    probe.add_argument("--canary-output-root", type=Path, required=True)
    probe.add_argument(
        "--closure-scope",
        choices=PREFLIGHT_CLOSURE_SCOPES,
        default="final_recovery",
    )
    probe.add_argument("--qualification-ownership", type=Path)
    probe.add_argument(
        "--device-file", type=Path, action="append", required=True, dest="device_file"
    )
    probe.add_argument("--output", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "test-receipt":
        _receipt, exit_code = run_test_receipt(args)
        print(args.output)
        return exit_code
    if args.command == "issue":
        receipt = issue_authorization(args)
        _write_json_exclusive(args.output, receipt)
        print(args.output)
        return 0
    if args.command == "execute-confined":
        print(execute_recovery(args))
        return 0
    if args.command == "preflight-child":
        print(run_cuda_preflight(args))
        return 0
    raise AuditRecoveryError("unknown recovery command")


if __name__ == "__main__":
    raise SystemExit(main())

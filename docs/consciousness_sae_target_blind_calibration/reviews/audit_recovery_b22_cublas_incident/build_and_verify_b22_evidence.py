#!/usr/bin/env python3
"""Build and independently verify the compact immutable B22 incident closure."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence


SCHEMA_VERSION = 1
INCIDENT_ID = "B22"
INCIDENT_DIR = Path(__file__).resolve().parent
DEFAULT_SOURCE_BASE = Path(
    "/private/tmp/audit-recovery-final-f12-lifecycle-20260715T191541Z-a1"
)
DEFAULT_REPO_ROOT = Path("/Users/d7082791602/Desktop/website/llm_selfref_pre")

POD_ID = "j7xr357tdlpq3f"
ATTEMPT_ID = "calv2-r3-audit-recovery-497b0f8-20260715T191757Z"
RUN_ID = "calv2-r3-1a16572-20260715T002344Z"
CODE_FREEZE = "f8a05e00ee0f8d2c0f33de6bd32c24c2022e36cd"
REVIEWED_PACKET = "00a4b11a1b5fb3038f2489ae73733393141fa374"
FINAL_FREEZE = "497b0f8326af7f3fd0b9aa0e9dd50ce553e947c7"
SOURCE_TEST_INVENTORY_SHA256 = (
    "b1c391af079e6e18e357573258e57fd0b371bdcb43b629fe18485a7a4d498d4e"
)

EXPECTED = {
    "controller_file_sha256": (
        "a0617d371df00f6b75f2c8cb7b75a619e6ce5adb20895cc6553fac9a044d3cb2"
    ),
    "audit_file_sha256": (
        "271f4f17a5ed66eaff43dc63f5a02d7ce45cdfd4a3c6a5b5c03bac33cf96a465"
    ),
    "base_protocol_file_sha256": (
        "d35a81fa6aae0be3c003bf36be4c4640f435c66d7ed7d16b7f1ce9f121f502c1"
    ),
    "ownership_file_sha256": (
        "e26b2a1f6c91dc9499572995087303f5b2646a540bc830fe062337cbd1bd2ec6"
    ),
    "ownership_receipt_sha256": (
        "6eb967c18c93cb008f273c507364b7610b3ca811d869cf275db9d594cd6f7e45"
    ),
    "launch_gate_file_sha256": (
        "ff31ef0be905e74eda19ef3dd8736f2dab55b57d7ea3a70c8a2efb5342bd2014"
    ),
    "launch_gate_receipt_sha256": (
        "671bdb7c76b7a3175eacce46d86fcd3536f036031ca1be0a9524b9ce4a02af94"
    ),
    "authorization_file_sha256": (
        "682e5a612e48e196a46ea762fe00ab4de32df1bf070aa72edf64d2639735f5ff"
    ),
    "authorization_receipt_sha256": (
        "8cb249316e406f795150cb55409c6053b8e29c4b510918ea7c539bbb969306d4"
    ),
    "preflight_landlock_file_sha256": (
        "77ff3a6d368fc3154c829ba7f09dd35745da44264abcb4a3f88af9273e7fe87e"
    ),
    "preflight_landlock_receipt_sha256": (
        "4447b8fc656d601269e106d585cc2c46d5eccf49ebd809b1ca971b7a57ddd1a1"
    ),
    "preflight_cuda_file_sha256": (
        "58b8ab1ef9f4cfa5e7226bfc2c08c768b6467428424e2e1505219bf5846cfdc2"
    ),
    "preflight_cuda_receipt_sha256": (
        "8e849e88fa69b9f5ed0635b3a8da6f6e8e1156eb28b8d1e706088cf537415a84"
    ),
    "landlock_file_sha256": (
        "98c59460298af035eae9cb991bf34318f233bbf690b87249517aac899f4a473e"
    ),
    "landlock_receipt_sha256": (
        "78fe589f7d66668e86d8399449927d6878465865c746e5a8b20bf5cf80f16652"
    ),
    "marker_file_sha256": (
        "3b7ec3427e6ef5062a246fce0fefeffa28a032097d83c924f97b98165a064599"
    ),
    "marker_receipt_sha256": (
        "9875b7810382910f5aa67b3a2e82217fbd4cc44de293b5091e172de0b1b58fa5"
    ),
    "failure_file_sha256": (
        "f77244d3ee5cc50aa15a951a135415bce467e33ae075670f1bc984ae121fa602"
    ),
    "failure_receipt_sha256": (
        "a50ff250cf654ea00acb24191a2aa602320eb6ac5c6e1e5a2e7af6a7a1d60391"
    ),
    "precreate_file_sha256": (
        "e6c72bdba6483e9cb4dc9b0cd81846c3398f9ce43391a1b9cab895e5d7d04e75"
    ),
    "precreate_receipt_sha256": (
        "ffb367bfd7dc229a0cca150e3202ff48ba0014860b1265c267c31a1d963a920c"
    ),
    "postcreate_file_sha256": (
        "7543387801f18376ed082f4f6ee15e9135dcd96193b82b561920feb143c5e60d"
    ),
    "postcreate_receipt_sha256": (
        "41b2f845803b7af0159b4c5f7955c1d90452c7d5b37a405198383e48f2b0817c"
    ),
    "postdelete_file_sha256": (
        "5c89a7716393ee731dc589e17cbff07930c91b76a213357d107945c4cec4d69d"
    ),
    "postdelete_receipt_sha256": (
        "3999be5102e4abae376b8f205666582799c036b079873b5475f34eee1287d148"
    ),
    "termination_file_sha256": (
        "2f2c5bdeabfd619f0b67d553645a2a18cdfd40c28958b403de7297164e5a03d2"
    ),
    "termination_receipt_sha256": (
        "a75ce41378e0bf0abf79d7375bec3732ce782d5423cb7cfb7534d2eda11d7484"
    ),
    "frozen_termination_file_sha256": (
        "9c93e6943e7bf44e57864d4a5a22c0c5deb5658c80018a467628c9ce40fc7236"
    ),
    "frozen_termination_receipt_sha256": (
        "cdb8359f724978f2b20a008e2fbaa59affed8892e06f8094544e4bca3d3de775"
    ),
    "controller_stdout_sha256": (
        "cd00f24e6f5a234a6f02ab96f6d72d1e01c92352d59d14a85d74342edfeda0e0"
    ),
    "controller_stderr_sha256": (
        "ecff3e226982aeb25103aa0d97f6efd7bb46532f16e941e6cba284caefe408f0"
    ),
}

ATTACHMENT_SOURCES = {
    "OWNERSHIP.json": ("base", "OWNERSHIP.json", "ownership_file_sha256"),
    "PRECREATE_INVENTORY.json": (
        "base",
        "PRECREATE_INVENTORY.json",
        "precreate_file_sha256",
    ),
    "POSTCREATE_INVENTORY.json": (
        "base",
        "POSTCREATE_INVENTORY.json",
        "postcreate_file_sha256",
    ),
    "POSTDELETE_INVENTORY.json": (
        "base",
        "POSTDELETE_INVENTORY.json",
        "postdelete_file_sha256",
    ),
    "TERMINATION_AUDIT.json": (
        "base",
        "TERMINATION_AUDIT.json",
        "termination_file_sha256",
    ),
    "FROZEN_TERMINATION.json": (
        "base",
        "frozen_lifecycle/TERMINATION.json",
        "frozen_termination_file_sha256",
    ),
    "FINAL_RECOVERY_LAUNCH_GATE.json": (
        "base",
        "retrieved/launch-gate/FINAL_RECOVERY_LAUNCH_GATE.json",
        "launch_gate_file_sha256",
    ),
    "PREFLIGHT_LANDLOCK_ENFORCEMENT.json": (
        "attempt",
        "preflight/output/LANDLOCK_ENFORCEMENT.json",
        "preflight_landlock_file_sha256",
    ),
    "PREFLIGHT_LANDLOCK_CUDA.json": (
        "attempt",
        "preflight/output/LANDLOCK_CUDA_PREFLIGHT.json",
        "preflight_cuda_file_sha256",
    ),
    "FINAL_LANDLOCK_ENFORCEMENT.json": (
        "attempt",
        "output/LANDLOCK_ENFORCEMENT.json",
        "landlock_file_sha256",
    ),
    "ATTEMPT_STARTED.json": (
        "attempt",
        "output/ATTEMPT_STARTED.json",
        "marker_file_sha256",
    ),
    "FAILURE.json": ("attempt", "output/FAILURE.json", "failure_file_sha256"),
    "controller.stdout": (
        "base",
        "logs/controller.stdout",
        "controller_stdout_sha256",
    ),
    "controller.stderr": (
        "base",
        "logs/controller.stderr",
        "controller_stderr_sha256",
    ),
    "F12_final_recovery_controller.sh": (
        "git",
        "experiments/consciousness_sae_target_blind_calibration/"
        "final_recovery_controller.sh",
        "controller_file_sha256",
    ),
    "F12_audit.py": (
        "git",
        "experiments/consciousness_sae_target_blind_calibration/audit.py",
        "audit_file_sha256",
    ),
    "F12_base_protocol.py": (
        "git",
        "experiments/consciousness_sae_realization_validation/protocol.py",
        "base_protocol_file_sha256",
    ),
}

ATTACHMENT_ROLES = {
    "OWNERSHIP.json": "exact_owned_recovery_pod",
    "PRECREATE_INVENTORY.json": "unrelated_account_inventory_before_create",
    "POSTCREATE_INVENTORY.json": "account_inventory_with_owned_pod",
    "POSTDELETE_INVENTORY.json": "unrelated_account_inventory_after_delete",
    "TERMINATION_AUDIT.json": "exact_owned_pod_termination_closure",
    "FROZEN_TERMINATION.json": "provider_deletion_and_direct_404_proof",
    "FINAL_RECOVERY_LAUNCH_GATE.json": "reviewed_hash_exec_launch_binding",
    "PREFLIGHT_LANDLOCK_ENFORCEMENT.json": "same_host_preflight_landlock",
    "PREFLIGHT_LANDLOCK_CUDA.json": "same_host_target_free_cuda_preflight",
    "FINAL_LANDLOCK_ENFORCEMENT.json": "consumed_final_landlock_authority",
    "ATTEMPT_STARTED.json": "exclusive_scientific_attempt_marker",
    "FAILURE.json": "exclusive_no_compact_failure_receipt",
    "controller.stdout": "retrieved_controller_stage_log",
    "controller.stderr": "retrieved_exact_traceback",
    "F12_final_recovery_controller.sh": "exact_final_freeze_controller_source",
    "F12_audit.py": "exact_frozen_auditor_source",
    "F12_base_protocol.py": "exact_frozen_determinism_constant_source",
    "AUTHORIZATION_BINDING.json": "compact_binding_to_omitted_full_authorization",
}

TOP_LEVEL_GENERATED = {
    "ATTEMPT_TREE_INVENTORY.json",
    "DESIGNATED_OUTPUT_TREE_INVENTORY.json",
    "PRIVATE_SOURCE_ANCHOR.json",
    "CUBLAS_CAUSE.json",
    "B22_CLOSURE_RECEIPT.json",
    "B22_VERIFICATION_OUTPUT.json",
    "SHA256SUMS",
}
TOP_LEVEL_AUTHORED = {"B22.md", "build_and_verify_b22_evidence.py"}
EXPECTED_TOP_LEVEL = TOP_LEVEL_GENERATED | TOP_LEVEL_AUTHORED | {"attachments"}


class B22EvidenceError(RuntimeError):
    """Raised when the compact incident evidence differs."""


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def seal(core: Mapping[str, Any]) -> dict[str, Any]:
    value = dict(core)
    value["receipt_sha256"] = canonical_sha256(value)
    return value


def require(condition: bool, message: str) -> None:
    if not condition:
        raise B22EvidenceError(message)


def read_json(path: Path, *, require_self_hash: bool = True) -> dict[str, Any]:
    try:
        raw = path.read_bytes()
        value = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise B22EvidenceError(f"unreadable JSON: {path}") from exc
    require(isinstance(value, dict), f"JSON root is not an object: {path}")
    if require_self_hash:
        core = dict(value)
        claimed = core.pop("receipt_sha256", None)
        require(
            isinstance(claimed, str) and claimed == canonical_sha256(core),
            f"self-hash differs: {path}",
        )
    return value


def write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.write_bytes(canonical_bytes(dict(value)) + b"\n")


def record(path: Path, *, relative_to: Path | None = None) -> dict[str, Any]:
    details = path.lstat()
    require(stat.S_ISREG(details.st_mode), f"not a regular file: {path}")
    require(details.st_nlink == 1, f"not singly linked: {path}")
    return {
        "path": (
            path.relative_to(relative_to).as_posix()
            if relative_to is not None
            else path.as_posix()
        ),
        "bytes": details.st_size,
        "sha256": sha256_file(path),
    }


def tree_inventory(root: Path, *, role: str) -> dict[str, Any]:
    require(root.is_dir() and not root.is_symlink(), f"invalid tree root: {root}")
    entries: list[dict[str, Any]] = []
    file_count = 0
    directory_count = 1
    total_file_bytes = 0
    for path in sorted(root.rglob("*"), key=lambda item: item.relative_to(root).as_posix()):
        details = path.lstat()
        relative = path.relative_to(root).as_posix()
        require(not stat.S_ISLNK(details.st_mode), f"tree contains symlink: {relative}")
        if stat.S_ISDIR(details.st_mode):
            directory_count += 1
            entries.append({"path": relative, "type": "directory"})
        elif stat.S_ISREG(details.st_mode):
            require(details.st_nlink == 1, f"tree contains hardlink: {relative}")
            file_count += 1
            total_file_bytes += details.st_size
            entries.append(
                {
                    "path": relative,
                    "type": "file",
                    "bytes": details.st_size,
                    "sha256": sha256_file(path),
                }
            )
        else:
            raise B22EvidenceError(f"tree contains special object: {relative}")
    core = {
        "schema_version": SCHEMA_VERSION,
        "receipt_kind": "b22_private_tree_inventory_v1",
        "role": role,
        "private_root": root.as_posix(),
        "file_count": file_count,
        "directory_count_including_root": directory_count,
        "total_file_bytes": total_file_bytes,
        "entries": entries,
        "entries_sha256": canonical_sha256(entries),
    }
    return seal(core)


def inventory_entry(inventory: Mapping[str, Any], relative: str) -> Mapping[str, Any]:
    matches = [row for row in inventory["entries"] if row.get("path") == relative]
    require(len(matches) == 1, f"inventory entry differs: {relative}")
    return matches[0]


def git_blob(repo_root: Path, relative: str) -> bytes:
    completed = subprocess.run(
        ["git", "-C", repo_root.as_posix(), "show", f"{FINAL_FREEZE}:{relative}"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    require(completed.returncode == 0, f"could not read F12 Git blob: {relative}")
    return completed.stdout


def source_path(
    kind: str, relative: str, *, source_base: Path, attempt_root: Path
) -> Path:
    if kind == "base":
        return source_base / relative
    if kind == "attempt":
        return attempt_root / relative
    raise B22EvidenceError(f"unsupported source kind: {kind}")


def build_authorization_binding(auth_path: Path) -> dict[str, Any]:
    auth = read_json(auth_path)
    execution = auth.get("execution")
    review = auth.get("review")
    require(isinstance(execution, dict), "authorization execution is missing")
    require(isinstance(review, dict), "authorization review is missing")
    paths = execution.get("paths")
    require(isinstance(paths, dict), "authorization paths are missing")
    core = {
        "schema_version": SCHEMA_VERSION,
        "receipt_kind": "b22_compact_authorization_binding_v1",
        "source_private_path": auth_path.as_posix(),
        "source_file_bytes": auth_path.stat().st_size,
        "source_file_sha256": sha256_file(auth_path),
        "source_receipt_sha256": auth["receipt_sha256"],
        "status": auth.get("status"),
        "study_id": auth.get("study_id"),
        "protocol_version": auth.get("protocol_version"),
        "run_id": auth.get("run_id"),
        "fresh_pod_id": auth.get("fresh_pod_id"),
        "git_head_commit": auth.get("git_head_commit"),
        "git_live_remote_commit": auth.get("git_live_remote_commit"),
        "git_local_remote_commit": auth.get("git_local_remote_commit"),
        "authorized_at_utc": auth.get("authorized_at_utc"),
        "recovery_started_at_unix": auth.get("recovery_started_at_unix"),
        "recovery_deadline_at_unix": auth.get("recovery_deadline_at_unix"),
        "model_forward_limit": auth.get("model_forward_limit"),
        "target_prompt_render_limit": auth.get("target_prompt_render_limit"),
        "target_feature_vector_limit": auth.get("target_feature_vector_limit"),
        "external_or_prior_outcome_inputs": auth.get(
            "external_or_prior_outcome_inputs"
        ),
        "execution": {
            "attempt_id": execution.get("attempt_id"),
            "attempt_root": execution.get("attempt_root"),
            "command_sha256": execution.get("command_sha256"),
            "confined_child_argv_sha256": execution.get(
                "confined_child_argv_sha256"
            ),
            "artifact_device": execution.get("artifact_device"),
            "recovery_authorization": paths.get("recovery_authorization"),
            "landlock_receipt": paths.get("landlock_receipt"),
            "attempt_marker": paths.get("attempt_marker"),
            "failure_out": paths.get("failure_out"),
            "audit_out": paths.get("audit_out"),
            "summary_out": paths.get("summary_out"),
        },
        "review": {
            "code_freeze_commit": review.get("code_freeze_commit"),
            "reviewed_packet_git_head_commit": review.get(
                "reviewed_packet_git_head_commit"
            ),
            "final_git_head_commit": review.get("final_git_head_commit"),
            "source_test_inventory_sha256": review.get(
                "source_test_inventory_sha256"
            ),
            "provider_status": review.get("provider_status"),
            "provider_terminal_verdict": review.get("provider_terminal_verdict"),
            "response_id": review.get("response_id"),
            "finding_ids": review.get("finding_ids"),
            "fixed_finding_ids": review.get("fixed_finding_ids"),
            "rejected_finding_ids": review.get("rejected_finding_ids"),
        },
    }
    return seal(core)


def literal_assignment(source: str, name: str) -> Any:
    tree = ast.parse(source)
    for node in tree.body:
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target = node.targets[0]
        if isinstance(target, ast.Name) and target.id == name:
            return ast.literal_eval(node.value)
    raise B22EvidenceError(f"literal assignment not found: {name}")


def line_number(source: str, needle: str, *, start_offset: int = 0) -> int:
    offset = source.find(needle, start_offset)
    if offset < 0:
        raise B22EvidenceError(f"source line not found: {needle}")
    return source.count("\n", 0, offset) + 1


def build_cublas_cause(attachments: Path) -> dict[str, Any]:
    controller_path = attachments / "F12_final_recovery_controller.sh"
    audit_path = attachments / "F12_audit.py"
    protocol_path = attachments / "F12_base_protocol.py"
    failure_path = attachments / "FAILURE.json"
    stderr_path = attachments / "controller.stderr"
    stdout_path = attachments / "controller.stdout"

    controller = controller_path.read_text(encoding="utf-8")
    audit = audit_path.read_text(encoding="utf-8")
    protocol = protocol_path.read_text(encoding="utf-8")
    stderr = stderr_path.read_text(encoding="utf-8")
    stdout = stdout_path.read_text(encoding="utf-8")
    failure = read_json(failure_path)

    env_name = literal_assignment(protocol, "CUBLAS_WORKSPACE_CONFIG_ENV")
    env_value = literal_assignment(protocol, "CUBLAS_WORKSPACE_CONFIG_VALUE")
    require(env_name == "CUBLAS_WORKSPACE_CONFIG", "CUBLAS name differs")
    require(env_value == ":4096:8", "CUBLAS value differs")

    start = controller.index("stage FINAL_CONFINED_EXECUTION_START")
    end = controller.index('  "${FINAL_LAUNCH[@]}"', start) + len(
        '  "${FINAL_LAUNCH[@]}"'
    )
    final_launch_block = controller[start:end]
    require("env -i" in final_launch_block, "final launch does not reset environment")
    require(env_name not in final_launch_block, "F12 final launch unexpectedly sets CUBLAS")
    require(env_name not in controller, "F12 controller contains a CUBLAS assignment")

    audit_guard = "os.environ.get(base_protocol.CUBLAS_WORKSPACE_CONFIG_ENV)"
    error_text = "artifact audit CUBLAS determinism differs"
    deterministic_call = "torch.use_deterministic_algorithms(True)"
    guard_offset = audit.index(audit_guard)
    error_offset = audit.index(error_text, guard_offset)
    deterministic_offset = audit.index(deterministic_call, error_offset)
    require(
        guard_offset < error_offset < deterministic_offset,
        "auditor CUBLAS guard ordering differs",
    )
    require(failure.get("error_type") == "CalibrationAuditError", "failure type differs")
    require(failure.get("error_message") == error_text, "failure message differs")
    require(error_text in stderr, "traceback does not contain exact failure")
    require("FINAL_RECOVERY_CONTROLLER_SUCCESS" not in stdout, "success marker present")

    core = {
        "schema_version": SCHEMA_VERSION,
        "receipt_kind": "b22_cublas_root_cause_v1",
        "status": "pass_missing_cublas_launch_precondition_proven",
        "environment_contract": {"name": env_name, "required_value": env_value},
        "controller": {
            "file_sha256": sha256_file(controller_path),
            "final_launch_uses_env_i": True,
            "required_assignment_present": False,
            "final_launch_block_start_line": line_number(
                controller, "stage FINAL_CONFINED_EXECUTION_START"
            ),
            "final_launch_env_i_line": line_number(
                controller, "env -i", start_offset=start
            ),
            "final_launch_block_sha256": hashlib.sha256(
                final_launch_block.encode("utf-8")
            ).hexdigest(),
        },
        "auditor": {
            "file_sha256": sha256_file(audit_path),
            "base_protocol_file_sha256": sha256_file(protocol_path),
            "guard_line": line_number(audit, audit_guard),
            "failure_line": line_number(audit, error_text),
            "deterministic_algorithms_line": line_number(audit, deterministic_call),
            "guard_precedes_deterministic_algorithms": True,
        },
        "observed_failure": {
            "error_type": failure["error_type"],
            "error_message": failure["error_message"],
            "failure_receipt_sha256": failure["receipt_sha256"],
            "stderr_sha256": sha256_file(stderr_path),
            "traceback_contains_exact_guard_error": True,
            "controller_success_marker_present": False,
        },
        "interpretation": {
            "missing_value_inferred_from_env_i_and_explicit_assignment_inventory": True,
            "numerical_nondeterminism_observed": False,
            "artifact_j_lm_head_recomputation_started": False,
            "technical_launch_precondition_failure": True,
        },
    }
    return seal(core)


def expected_source_receipt_hash(name: str) -> str | None:
    mapping = {
        "OWNERSHIP.json": "ownership_receipt_sha256",
        "PRECREATE_INVENTORY.json": "precreate_receipt_sha256",
        "POSTCREATE_INVENTORY.json": "postcreate_receipt_sha256",
        "POSTDELETE_INVENTORY.json": "postdelete_receipt_sha256",
        "TERMINATION_AUDIT.json": "termination_receipt_sha256",
        "FROZEN_TERMINATION.json": "frozen_termination_receipt_sha256",
        "FINAL_RECOVERY_LAUNCH_GATE.json": "launch_gate_receipt_sha256",
        "PREFLIGHT_LANDLOCK_ENFORCEMENT.json": (
            "preflight_landlock_receipt_sha256"
        ),
        "PREFLIGHT_LANDLOCK_CUDA.json": "preflight_cuda_receipt_sha256",
        "FINAL_LANDLOCK_ENFORCEMENT.json": "landlock_receipt_sha256",
        "ATTEMPT_STARTED.json": "marker_receipt_sha256",
        "FAILURE.json": "failure_receipt_sha256",
    }
    key = mapping.get(name)
    return EXPECTED[key] if key is not None else None


def validate_attachment_constants(incident_dir: Path) -> None:
    attachments = incident_dir / "attachments"
    require(
        {path.name for path in attachments.iterdir()} == set(ATTACHMENT_ROLES),
        "attachment file set differs",
    )
    for destination_name, (_, _, expected_key) in ATTACHMENT_SOURCES.items():
        path = attachments / destination_name
        require(
            sha256_file(path) == EXPECTED[expected_key],
            f"frozen attachment SHA differs: {destination_name}",
        )
        expected_receipt = expected_source_receipt_hash(destination_name)
        if expected_receipt is not None:
            require(
                read_json(path)["receipt_sha256"] == expected_receipt,
                f"frozen attachment receipt differs: {destination_name}",
            )


def copy_sources(source_base: Path, repo_root: Path, attachments: Path) -> None:
    attempt_root = source_base / "retrieved" / ATTEMPT_ID
    attachments.mkdir(mode=0o755)
    for destination_name, (kind, relative, expected_key) in ATTACHMENT_SOURCES.items():
        destination = attachments / destination_name
        if kind == "git":
            destination.write_bytes(git_blob(repo_root, relative))
        else:
            source = source_path(
                kind, relative, source_base=source_base, attempt_root=attempt_root
            )
            require(source.is_file() and not source.is_symlink(), f"source missing: {source}")
            shutil.copyfile(source, destination)
        os.chmod(destination, 0o644)
        require(
            sha256_file(destination) == EXPECTED[expected_key],
            f"source physical SHA differs: {destination_name}",
        )
        expected_receipt = expected_source_receipt_hash(destination_name)
        if expected_receipt is not None:
            value = read_json(destination)
            require(
                value["receipt_sha256"] == expected_receipt,
                f"source receipt SHA differs: {destination_name}",
            )


def source_anchor(
    source_base: Path,
    attempt_root: Path,
    attempt_inventory: Mapping[str, Any],
    output_inventory: Mapping[str, Any],
) -> dict[str, Any]:
    selected = {
        "full_authorization": attempt_root / "RECOVERY_AUTHORIZATION.json",
        "controller_stdout": source_base / "logs/controller.stdout",
        "controller_stderr": source_base / "logs/controller.stderr",
        "ownership": source_base / "OWNERSHIP.json",
        "precreate_inventory": source_base / "PRECREATE_INVENTORY.json",
        "postcreate_inventory": source_base / "POSTCREATE_INVENTORY.json",
        "postdelete_inventory": source_base / "POSTDELETE_INVENTORY.json",
        "termination_audit": source_base / "TERMINATION_AUDIT.json",
        "frozen_termination": source_base / "frozen_lifecycle/TERMINATION.json",
        "launch_gate": (
            source_base / "retrieved/launch-gate/FINAL_RECOVERY_LAUNCH_GATE.json"
        ),
    }
    selected_records = [
        {"role": role, **record(path)} for role, path in sorted(selected.items())
    ]
    core = {
        "schema_version": SCHEMA_VERSION,
        "receipt_kind": "b22_private_full_bundle_anchor_v1",
        "status": "private_full_bundle_rehashed_and_compactly_anchored",
        "source_base": source_base.as_posix(),
        "retrieved_attempt_root": attempt_root.as_posix(),
        "attempt_id": ATTEMPT_ID,
        "attempt_tree_inventory_receipt_sha256": attempt_inventory["receipt_sha256"],
        "attempt_tree_entries_sha256": attempt_inventory["entries_sha256"],
        "attempt_tree_file_count": attempt_inventory["file_count"],
        "attempt_tree_total_file_bytes": attempt_inventory["total_file_bytes"],
        "designated_output_inventory_receipt_sha256": output_inventory[
            "receipt_sha256"
        ],
        "selected_private_files": selected_records,
        "selected_private_files_sha256": canonical_sha256(selected_records),
        "availability": "retained_private_local_bundle_not_committed",
    }
    return seal(core)


def designated_output_inventory(output_root: Path) -> dict[str, Any]:
    inventory = tree_inventory(output_root, role="designated_output_tree")
    expected_files = [
        "ATTEMPT_STARTED.json",
        "FAILURE.json",
        "LANDLOCK_ENFORCEMENT.json",
    ]
    observed_files = sorted(
        row["path"] for row in inventory["entries"] if row["type"] == "file"
    )
    absence = [
        "compact",
        "compact/CALIBRATION_AUDIT.json",
        "compact/CALIBRATION_SUMMARY.json",
        "compact/PUBLICATION_COMPLETE.json",
    ]
    require(observed_files == expected_files, "designated output file set differs")
    require(
        all(not os.path.lexists(output_root / relative) for relative in absence),
        "compact success artifact unexpectedly exists",
    )
    core = dict(inventory)
    core.pop("receipt_sha256")
    core.update(
        {
            "exact_file_names": expected_files,
            "compact_success_paths": [
                {"path": relative, "absent": True} for relative in absence
            ],
            "compact_success_publication_present": False,
        }
    )
    return seal(core)


def validate_chain(incident_dir: Path) -> dict[str, bool]:
    attachments = incident_dir / "attachments"
    validate_attachment_constants(incident_dir)
    ownership = read_json(attachments / "OWNERSHIP.json")
    launch = read_json(attachments / "FINAL_RECOVERY_LAUNCH_GATE.json")
    auth_binding = read_json(attachments / "AUTHORIZATION_BINDING.json")
    preflight_landlock = read_json(
        attachments / "PREFLIGHT_LANDLOCK_ENFORCEMENT.json"
    )
    preflight_cuda = read_json(attachments / "PREFLIGHT_LANDLOCK_CUDA.json")
    landlock = read_json(attachments / "FINAL_LANDLOCK_ENFORCEMENT.json")
    marker = read_json(attachments / "ATTEMPT_STARTED.json")
    failure = read_json(attachments / "FAILURE.json")
    precreate = read_json(attachments / "PRECREATE_INVENTORY.json")
    postcreate = read_json(attachments / "POSTCREATE_INVENTORY.json")
    postdelete = read_json(attachments / "POSTDELETE_INVENTORY.json")
    termination = read_json(attachments / "TERMINATION_AUDIT.json")
    frozen_termination = read_json(attachments / "FROZEN_TERMINATION.json")
    cause = read_json(incident_dir / "CUBLAS_CAUSE.json")
    attempt_inventory = read_json(incident_dir / "ATTEMPT_TREE_INVENTORY.json")
    output_inventory = read_json(incident_dir / "DESIGNATED_OUTPUT_TREE_INVENTORY.json")
    private_anchor = read_json(incident_dir / "PRIVATE_SOURCE_ANCHOR.json")

    require(
        ownership["pod_id"] == POD_ID
        and ownership["receipt_sha256"] == EXPECTED["ownership_receipt_sha256"]
        and ownership["gpu_type"] == "NVIDIA B200"
        and ownership["gpu_count"] == 1,
        "ownership identity differs",
    )
    require(
        launch["pod_id"] == POD_ID
        and launch["attempt_id"] == ATTEMPT_ID
        and launch["ownership_receipt_sha256"] == ownership["receipt_sha256"]
        and launch["controller_sha256"] == EXPECTED["controller_file_sha256"]
        and launch["code_freeze_commit"] == CODE_FREEZE
        and launch["reviewed_packet_git_head_commit"] == REVIEWED_PACKET
        and launch["final_freeze_commit"] == FINAL_FREEZE,
        "launch binding differs",
    )
    execution = auth_binding["execution"]
    review = auth_binding["review"]
    require(
        auth_binding["source_file_sha256"] == EXPECTED["authorization_file_sha256"]
        and auth_binding["source_receipt_sha256"]
        == EXPECTED["authorization_receipt_sha256"]
        and auth_binding["fresh_pod_id"] == POD_ID
        and auth_binding["run_id"] == RUN_ID
        and execution["attempt_id"] == ATTEMPT_ID
        and review["code_freeze_commit"] == CODE_FREEZE
        and review["reviewed_packet_git_head_commit"] == REVIEWED_PACKET
        and review["final_git_head_commit"] == FINAL_FREEZE
        and review["source_test_inventory_sha256"] == SOURCE_TEST_INVENTORY_SHA256,
        "authorization binding differs",
    )
    require(
        preflight_landlock["status"] == "pass_landlock_enforced"
        and preflight_cuda["status"] == "pass_target_free_landlock_cuda_preflight"
        and preflight_cuda["landlock_receipt_sha256"]
        == preflight_landlock["receipt_sha256"],
        "preflight chain differs",
    )
    require(
        landlock["status"] == "pass_landlock_enforced"
        and landlock["purpose"] == "audit_recovery"
        and landlock["authorization_sha256"]
        == auth_binding["source_receipt_sha256"]
        and landlock["preflight_receipt_sha256"] == preflight_cuda["receipt_sha256"],
        "final Landlock chain differs",
    )
    require(
        marker["status"] == "claimed_exactly_once"
        and marker["attempt_id"] == ATTEMPT_ID
        and marker["run_id"] == RUN_ID
        and marker["recovery_authorization_receipt_sha256"]
        == auth_binding["source_receipt_sha256"]
        and marker["landlock_confinement_receipt_sha256"]
        == landlock["receipt_sha256"]
        and marker["landlock_pid"] == landlock["pid"]
        and marker["command_sha256"] == execution["command_sha256"],
        "attempt marker chain differs",
    )
    require(
        failure["status"] == "failed_no_compact_success_publication"
        and failure["attempt_id"] == ATTEMPT_ID
        and failure["run_id"] == RUN_ID
        and failure["recovery_authorization_receipt_sha256"]
        == auth_binding["source_receipt_sha256"]
        and failure["landlock_confinement_receipt_sha256"]
        == landlock["receipt_sha256"]
        and failure["attempt_marker_receipt_sha256"] == marker["receipt_sha256"]
        and failure["command_sha256"] == execution["command_sha256"]
        and failure["compact_success_directory_exists"] is False
        and failure["error_type"] == "CalibrationAuditError"
        and failure["error_message"] == "artifact audit CUBLAS determinism differs",
        "failure chain differs",
    )
    require(
        output_inventory["compact_success_publication_present"] is False
        and output_inventory["file_count"] == 3
        and output_inventory["directory_count_including_root"] == 1,
        "no-compact output proof differs",
    )
    expected_output_entries = []
    for output_name, attachment_name in (
        ("ATTEMPT_STARTED.json", "ATTEMPT_STARTED.json"),
        ("FAILURE.json", "FAILURE.json"),
        ("LANDLOCK_ENFORCEMENT.json", "FINAL_LANDLOCK_ENFORCEMENT.json"),
    ):
        source_record = record(attachments / attachment_name)
        expected_output_entries.append(
            {
                "path": output_name,
                "type": "file",
                "bytes": source_record["bytes"],
                "sha256": source_record["sha256"],
            }
        )
    require(
        output_inventory["exact_file_names"]
        == [row["path"] for row in expected_output_entries]
        and output_inventory["entries"] == expected_output_entries
        and output_inventory["entries_sha256"]
        == canonical_sha256(expected_output_entries)
        and output_inventory["compact_success_paths"]
        == [
            {"path": "compact", "absent": True},
            {"path": "compact/CALIBRATION_AUDIT.json", "absent": True},
            {"path": "compact/CALIBRATION_SUMMARY.json", "absent": True},
            {"path": "compact/PUBLICATION_COMPLETE.json", "absent": True},
        ],
        "designated output inventory binding differs",
    )
    require(
        precreate["inventory_sha256"] == postdelete["inventory_sha256"]
        and precreate["pods"] == postdelete["pods"]
        and precreate["all_account_pod_count"]
        == postdelete["all_account_pod_count"]
        and all(row["pod_id"] != POD_ID for row in postdelete["pods"])
        and any(row["pod_id"] == POD_ID for row in postcreate["pods"]),
        "unrelated account inventory changed",
    )
    require(
        termination["status"]
        == "deleted_exact_owned_pod_unrelated_inventory_unchanged"
        and termination["pod_id"] == POD_ID
        and termination["successor_ownership_receipt_sha256"]
        == ownership["receipt_sha256"]
        and termination["precreate_inventory_sha256"]
        == precreate["inventory_sha256"]
        and termination["postdelete_inventory_sha256"]
        == postdelete["inventory_sha256"]
        and termination["frozen_termination_receipt_sha256"]
        == frozen_termination["receipt_sha256"]
        and frozen_termination["status"] == "deleted_verified"
        and frozen_termination["pod_id"] == POD_ID
        and frozen_termination["absent_from_account_inventory"] is True
        and frozen_termination["post_delete_direct_http_status"] == 404
        and frozen_termination["other_pods_mutated"] is False,
        "termination chain differs",
    )
    require(
        cause["status"] == "pass_missing_cublas_launch_precondition_proven"
        and cause == build_cublas_cause(attachments)
        and cause["controller"]["required_assignment_present"] is False
        and cause["interpretation"]["numerical_nondeterminism_observed"] is False
        and cause["observed_failure"]["failure_receipt_sha256"]
        == failure["receipt_sha256"],
        "CUBLAS cause proof differs",
    )
    require(
        private_anchor["status"]
        == "private_full_bundle_rehashed_and_compactly_anchored"
        and private_anchor["attempt_id"] == ATTEMPT_ID
        and private_anchor["source_base"] == DEFAULT_SOURCE_BASE.as_posix()
        and private_anchor["retrieved_attempt_root"]
        == (DEFAULT_SOURCE_BASE / "retrieved" / ATTEMPT_ID).as_posix()
        and private_anchor["attempt_tree_inventory_receipt_sha256"]
        == attempt_inventory["receipt_sha256"]
        and private_anchor["attempt_tree_entries_sha256"]
        == attempt_inventory["entries_sha256"]
        and private_anchor["attempt_tree_file_count"]
        == attempt_inventory["file_count"]
        and private_anchor["attempt_tree_total_file_bytes"]
        == attempt_inventory["total_file_bytes"]
        and private_anchor["designated_output_inventory_receipt_sha256"]
        == output_inventory["receipt_sha256"],
        "private source anchor differs",
    )
    selected_hashes = {
        row["role"]: row["sha256"]
        for row in private_anchor["selected_private_files"]
    }
    require(
        selected_hashes
        == {
            "controller_stderr": EXPECTED["controller_stderr_sha256"],
            "controller_stdout": EXPECTED["controller_stdout_sha256"],
            "frozen_termination": EXPECTED["frozen_termination_file_sha256"],
            "full_authorization": EXPECTED["authorization_file_sha256"],
            "launch_gate": EXPECTED["launch_gate_file_sha256"],
            "ownership": EXPECTED["ownership_file_sha256"],
            "postcreate_inventory": EXPECTED["postcreate_file_sha256"],
            "postdelete_inventory": EXPECTED["postdelete_file_sha256"],
            "precreate_inventory": EXPECTED["precreate_file_sha256"],
            "termination_audit": EXPECTED["termination_file_sha256"],
        }
        and private_anchor["selected_private_files_sha256"]
        == canonical_sha256(private_anchor["selected_private_files"]),
        "selected private source anchors differ",
    )
    return {
        "exact_identity_chain": True,
        "reviewed_launch_gate_bound": True,
        "authorization_consumed_by_landlock_and_marker": True,
        "exact_catchable_failure_receipt_bound": True,
        "missing_cublas_root_cause_proven": True,
        "numerical_nondeterminism_not_observed": True,
        "compact_success_publication_absent": True,
        "exact_owned_pod_deleted": True,
        "unrelated_account_inventory_unchanged": True,
        "private_full_bundle_compactly_anchored": True,
    }


def attachment_records(incident_dir: Path) -> list[dict[str, Any]]:
    attachments = incident_dir / "attachments"
    observed = {path.name for path in attachments.iterdir()}
    require(observed == set(ATTACHMENT_ROLES), "attachment file set differs")
    rows = []
    for name, role in sorted(ATTACHMENT_ROLES.items()):
        path = attachments / name
        row = {"role": role, **record(path, relative_to=incident_dir)}
        if name.endswith(".json"):
            row["receipt_sha256"] = read_json(path)["receipt_sha256"]
        rows.append(row)
    return rows


def support_records(incident_dir: Path) -> list[dict[str, Any]]:
    return [
        {"role": "human_incident_summary", **record(incident_dir / "B22.md", relative_to=incident_dir)},
        {
            "role": "standard_library_builder_and_verifier",
            **record(
                incident_dir / "build_and_verify_b22_evidence.py",
                relative_to=incident_dir,
            ),
        },
    ]


def build_closure(incident_dir: Path) -> dict[str, Any]:
    attachments = attachment_records(incident_dir)
    support = support_records(incident_dir)
    attempt_inventory = read_json(incident_dir / "ATTEMPT_TREE_INVENTORY.json")
    output_inventory = read_json(
        incident_dir / "DESIGNATED_OUTPUT_TREE_INVENTORY.json"
    )
    private_anchor = read_json(incident_dir / "PRIVATE_SOURCE_ANCHOR.json")
    cause = read_json(incident_dir / "CUBLAS_CAUSE.json")
    checks = validate_chain(incident_dir)
    core = {
        "schema_version": SCHEMA_VERSION,
        "receipt_kind": "audit_recovery_b22_cublas_incident_closure_v1",
        "incident_id": INCIDENT_ID,
        "status": "closed_technical_failure_no_compact_scientific_result",
        "identity": {
            "pod_id": POD_ID,
            "attempt_id": ATTEMPT_ID,
            "run_id": RUN_ID,
            "code_freeze_commit": CODE_FREEZE,
            "reviewed_packet_commit": REVIEWED_PACKET,
            "final_freeze_commit": FINAL_FREEZE,
            "ownership_receipt_sha256": EXPECTED["ownership_receipt_sha256"],
            "authorization_receipt_sha256": EXPECTED[
                "authorization_receipt_sha256"
            ],
            "landlock_receipt_sha256": EXPECTED["landlock_receipt_sha256"],
            "attempt_marker_receipt_sha256": EXPECTED["marker_receipt_sha256"],
            "failure_receipt_sha256": EXPECTED["failure_receipt_sha256"],
        },
        "cause": {
            "classification": "missing_launch_environment_precondition",
            "environment_name": "CUBLAS_WORKSPACE_CONFIG",
            "required_value": ":4096:8",
            "numerical_nondeterminism_observed": False,
            "cause_receipt_sha256": cause["receipt_sha256"],
        },
        "scientific_result": {
            "compact_success_publication": "absent",
            "calibration_audit": "absent",
            "calibration_summary": "absent",
            "publication_complete": "absent",
            "failure_receipt_status": "failed_no_compact_success_publication",
            "raw_row_recomputation_may_have_preceded_late_guard": True,
            "success_claim_permitted": False,
        },
        "one_shot_authority": {
            "landlock_receipt_created": True,
            "attempt_marker_created": True,
            "authorization_consumed": True,
            "same_authorization_retry_permitted": False,
        },
        "attempt_tree_inventory_receipt_sha256": attempt_inventory[
            "receipt_sha256"
        ],
        "designated_output_inventory_receipt_sha256": output_inventory[
            "receipt_sha256"
        ],
        "private_source_anchor_receipt_sha256": private_anchor["receipt_sha256"],
        "attachments": attachments,
        "attachments_sha256": canonical_sha256(attachments),
        "support_files": support,
        "support_files_sha256": canonical_sha256(support),
        "semantic_checks": checks,
        "termination": {
            "status": "deleted_exact_owned_pod_unrelated_inventory_unchanged",
            "termination_receipt_sha256": EXPECTED["termination_receipt_sha256"],
            "frozen_termination_receipt_sha256": EXPECTED[
                "frozen_termination_receipt_sha256"
            ],
        },
        "authorization": "incident_closure_only_not_retry_authority",
    }
    return seal(core)


def core_verified_records(incident_dir: Path) -> list[dict[str, Any]]:
    excluded = {"B22_VERIFICATION_OUTPUT.json", "SHA256SUMS"}
    rows = []
    for path in sorted(incident_dir.rglob("*"), key=lambda item: item.relative_to(incident_dir).as_posix()):
        if path.is_dir():
            continue
        relative = path.relative_to(incident_dir).as_posix()
        if relative in excluded:
            continue
        rows.append(record(path, relative_to=incident_dir))
    return rows


def expected_verification(incident_dir: Path) -> dict[str, Any]:
    closure = read_json(incident_dir / "B22_CLOSURE_RECEIPT.json")
    verified_files = core_verified_records(incident_dir)
    core = {
        "schema_version": SCHEMA_VERSION,
        "receipt_kind": "audit_recovery_b22_offline_verification_v1",
        "incident_id": INCIDENT_ID,
        "status": "pass_b22_closed_mechanically",
        "pod_id": POD_ID,
        "attempt_id": ATTEMPT_ID,
        "closure_receipt_sha256": closure["receipt_sha256"],
        "semantic_checks": validate_chain(incident_dir),
        "verified_files": verified_files,
        "verified_file_count": len(verified_files),
        "verified_files_sha256": canonical_sha256(verified_files),
        "network_accessed": False,
        "private_source_required_for_offline_verification": False,
        "bundle_modified_by_verification": False,
    }
    return seal(core)


def expected_sha256sums(incident_dir: Path) -> str:
    rows = []
    for path in sorted(incident_dir.rglob("*"), key=lambda item: item.relative_to(incident_dir).as_posix()):
        if path.is_dir() or path.name == "SHA256SUMS":
            continue
        relative = path.relative_to(incident_dir).as_posix()
        rows.append(f"{sha256_file(path)}  {relative}\n")
    return "".join(rows)


def verify_private_source(
    incident_dir: Path, source_base: Path, repo_root: Path
) -> None:
    require(source_base.resolve(strict=True) == DEFAULT_SOURCE_BASE, "source base differs")
    attempt_root = source_base / "retrieved" / ATTEMPT_ID
    fresh_attempt_inventory = tree_inventory(
        attempt_root, role="complete_retrieved_f12_attempt"
    )
    checked_attempt_inventory = read_json(
        incident_dir / "ATTEMPT_TREE_INVENTORY.json"
    )
    require(
        fresh_attempt_inventory == checked_attempt_inventory,
        "private attempt tree changed from checked inventory",
    )
    fresh_output_inventory = designated_output_inventory(attempt_root / "output")
    checked_output_inventory = read_json(
        incident_dir / "DESIGNATED_OUTPUT_TREE_INVENTORY.json"
    )
    require(
        fresh_output_inventory == checked_output_inventory,
        "private designated output changed from checked inventory",
    )
    anchor = source_anchor(
        source_base,
        attempt_root,
        fresh_attempt_inventory,
        fresh_output_inventory,
    )
    require(
        anchor == read_json(incident_dir / "PRIVATE_SOURCE_ANCHOR.json"),
        "private source anchor differs",
    )
    for destination_name, (kind, relative, expected_key) in ATTACHMENT_SOURCES.items():
        attachment = incident_dir / "attachments" / destination_name
        if kind == "git":
            source_bytes = git_blob(repo_root, relative)
            require(
                hashlib.sha256(source_bytes).hexdigest() == EXPECTED[expected_key]
                and attachment.read_bytes() == source_bytes,
                f"Git attachment differs: {destination_name}",
            )
        else:
            source = source_path(
                kind, relative, source_base=source_base, attempt_root=attempt_root
            )
            require(
                attachment.read_bytes() == source.read_bytes(),
                f"private attachment differs: {destination_name}",
            )
    full_auth = attempt_root / "RECOVERY_AUTHORIZATION.json"
    require(
        build_authorization_binding(full_auth)
        == read_json(incident_dir / "attachments/AUTHORIZATION_BINDING.json"),
        "authorization compact binding differs from private source",
    )


def verify_incident(
    incident_dir: Path,
    *,
    source_base: Path | None = None,
    repo_root: Path | None = None,
) -> dict[str, Any]:
    require(incident_dir.resolve(strict=True) == INCIDENT_DIR, "incident directory differs")
    observed_top = {path.name for path in incident_dir.iterdir()}
    require(observed_top == EXPECTED_TOP_LEVEL, "incident top-level file set differs")
    require((incident_dir / "attachments").is_dir(), "attachments directory missing")

    closure = read_json(incident_dir / "B22_CLOSURE_RECEIPT.json")
    require(closure == build_closure(incident_dir), "closure content differs")
    expected = expected_verification(incident_dir)
    observed = read_json(incident_dir / "B22_VERIFICATION_OUTPUT.json")
    require(observed == expected, "verification receipt differs")
    require(
        (incident_dir / "SHA256SUMS").read_text(encoding="utf-8")
        == expected_sha256sums(incident_dir),
        "SHA256SUMS differs",
    )
    if source_base is not None:
        require(repo_root is not None, "repo root required with source base")
        verify_private_source(incident_dir, source_base, repo_root)
    return observed


def clean_generated(incident_dir: Path) -> None:
    attachments = incident_dir / "attachments"
    if attachments.exists():
        require(attachments.is_dir() and not attachments.is_symlink(), "unsafe attachments")
        shutil.rmtree(attachments)
    for name in TOP_LEVEL_GENERATED:
        path = incident_dir / name
        if os.path.lexists(path):
            require(path.is_file() and not path.is_symlink(), f"unsafe generated path: {path}")
            path.unlink()


def build(source_base: Path, repo_root: Path) -> dict[str, Any]:
    source_base = source_base.resolve(strict=True)
    repo_root = repo_root.resolve(strict=True)
    require(source_base == DEFAULT_SOURCE_BASE, "source base differs from frozen B22 path")
    require((source_base / "ATTEMPT_ID.txt").read_text().strip() == ATTEMPT_ID, "attempt id differs")
    require((repo_root / ".git").exists(), "repo root is not a Git checkout")
    require(INCIDENT_DIR.is_dir() and not INCIDENT_DIR.is_symlink(), "incident dir unsafe")
    require(
        {path.name for path in INCIDENT_DIR.iterdir()} <= EXPECTED_TOP_LEVEL,
        "unexpected pre-build incident file",
    )
    clean_generated(INCIDENT_DIR)
    attachments = INCIDENT_DIR / "attachments"
    copy_sources(source_base, repo_root, attachments)

    attempt_root = source_base / "retrieved" / ATTEMPT_ID
    attempt_inventory = tree_inventory(
        attempt_root, role="complete_retrieved_f12_attempt"
    )
    output_inventory = designated_output_inventory(attempt_root / "output")
    write_json(INCIDENT_DIR / "ATTEMPT_TREE_INVENTORY.json", attempt_inventory)
    write_json(
        INCIDENT_DIR / "DESIGNATED_OUTPUT_TREE_INVENTORY.json", output_inventory
    )
    write_json(
        INCIDENT_DIR / "PRIVATE_SOURCE_ANCHOR.json",
        source_anchor(source_base, attempt_root, attempt_inventory, output_inventory),
    )
    write_json(
        attachments / "AUTHORIZATION_BINDING.json",
        build_authorization_binding(attempt_root / "RECOVERY_AUTHORIZATION.json"),
    )
    write_json(INCIDENT_DIR / "CUBLAS_CAUSE.json", build_cublas_cause(attachments))
    write_json(INCIDENT_DIR / "B22_CLOSURE_RECEIPT.json", build_closure(INCIDENT_DIR))
    write_json(
        INCIDENT_DIR / "B22_VERIFICATION_OUTPUT.json",
        expected_verification(INCIDENT_DIR),
    )
    (INCIDENT_DIR / "SHA256SUMS").write_text(
        expected_sha256sums(INCIDENT_DIR), encoding="utf-8"
    )
    return verify_incident(
        INCIDENT_DIR, source_base=source_base, repo_root=repo_root
    )


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    subparsers = result.add_subparsers(dest="command", required=True)
    build_parser = subparsers.add_parser("build")
    build_parser.add_argument("--source-base", type=Path, default=DEFAULT_SOURCE_BASE)
    build_parser.add_argument("--repo-root", type=Path, default=DEFAULT_REPO_ROOT)
    verify_parser = subparsers.add_parser("verify")
    verify_parser.add_argument("--incident-dir", type=Path, default=INCIDENT_DIR)
    verify_parser.add_argument("--source-base", type=Path)
    verify_parser.add_argument("--repo-root", type=Path, default=DEFAULT_REPO_ROOT)
    return result


def main(argv: Sequence[str] | None = None) -> int:
    args = parser().parse_args(argv)
    if args.command == "build":
        receipt = build(args.source_base, args.repo_root)
    else:
        receipt = verify_incident(
            args.incident_dir,
            source_base=args.source_base,
            repo_root=(args.repo_root if args.source_base is not None else None),
        )
    print(
        f"{receipt['status']} receipt_sha256={receipt['receipt_sha256']} "
        f"verified_file_count={receipt['verified_file_count']}"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except B22EvidenceError as exc:
        print(f"B22 verification failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc

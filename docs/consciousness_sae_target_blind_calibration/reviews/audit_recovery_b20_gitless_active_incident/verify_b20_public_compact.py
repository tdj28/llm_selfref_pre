#!/usr/bin/env python3
"""Build and verify the portable, repo-sized B20 incident evidence bundle."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path
from typing import Any


EXPECTED_ATTEMPT = "calv2-r3-audit-recovery-2479ed0-20260715T165648Z"
EXPECTED_POD = "eeo1skjkwjqot5"
EXPECTED_FREEZE = "2479ed0c767fba7c872dbbd48666b5a598e2b9f6"
EXPECTED_OWNERSHIP = "54e0f4754b1dfd0a009da42ccae287d447cb6acbcd4d7394f3c149fbcac176b2"
EXPECTED_AUTHORIZATION = "f6d0fa7fdf5b6ec8553fce2fe8df7842dd28f5a63fb5a9674a6358d4af152358"
EXPECTED_LANDLOCK = "f9e508065d18db6eb116054d8bfd55172d1f60ac320975d1fe33783cc2ce6a29"
EXPECTED_GATE = "ec0c6d319e5b4e55b2e2a2d6647e2e51b8bc46e0160b24538ecb5fdeb7f50e77"
EXPECTED_TERMINATION = "937f3a3d21a1a9f91bf88ffef46b8dada78fcd86ffc10082c43c102edc74904b"
EXPECTED_FROZEN_TERMINATION = "806b9be4e77e7f6006dbc97a5e628ef5f5f868b9b677f80b0c8135f7107589da"
EXPECTED_EMPTY_INVENTORY = "4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945"
EXPECTED_SOURCE_MANIFEST_FILE = "5342a90821c308cb69a2a8cc1a3703bed31b0bb20b1b1dc2bdae1135f040f56b"
EXPECTED_SOURCE_CLOSURE_FILE = "1ea1a287a6881cd69922a89a6008dee651ba7fa94f97b78d07e09adfc3a483d4"
EXPECTED_SOURCE_CLOSURE_RECEIPT = "61f1263e517b179ec3515425d82cd6918b8ab1317b80933bebd2bd669d940aed"
EXPECTED_SOURCE_VERIFICATION_FILE = "bcb5340a1136674793466c5eb789a822fd1fbc6cc616c0a807cdc6c04c8da2d2"
EXPECTED_SOURCE_VERIFICATION_RECEIPT = "a5dc3c9697e803cbbc03cf780b4bc511db2a19f1c33ef557539831fabd2264a7"
EXPECTED_ERROR = (
    "experiments.consciousness_sae_target_blind_calibration.audit_recovery."
    "AuditRecoveryError: git test-receipt binding failed: fatal: could not open "
    "'/dev/null' for reading and writing: Permission denied"
)
EXPECTED_ABSENCES = [
    "ATTEMPT_STARTED.json",
    "FAILURE.json",
    "compact",
    "compact/CALIBRATION_AUDIT.json",
    "compact/CALIBRATION_SUMMARY.json",
    "compact/PUBLICATION_COMPLETE.json",
]
ROOT = Path(__file__).resolve().parent
ATTACHMENTS = ROOT / "attachments"


class EvidenceError(RuntimeError):
    pass


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def sha_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise EvidenceError(f"could not load {path.name}: {exc}") from exc
    if not isinstance(value, dict):
        raise EvidenceError(f"expected object in {path.name}")
    return value


def self_hash(value: dict[str, Any]) -> str:
    unhashed = dict(value)
    unhashed.pop("receipt_sha256", None)
    return sha_bytes(canonical(unhashed))


def checked(path: Path) -> dict[str, Any]:
    value = load(path)
    require(value.get("receipt_sha256") == self_hash(value), f"invalid self-hash: {path.name}")
    return value


def write_receipt(path: Path, value: dict[str, Any]) -> None:
    value["receipt_sha256"] = self_hash(value)
    path.write_bytes(canonical(value) + b"\n")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise EvidenceError(message)


def record(path: Path, role: str) -> dict[str, Any]:
    return {
        "bytes": path.stat().st_size,
        "path": path.relative_to(ROOT).as_posix(),
        "role": role,
        "sha256": sha_file(path),
    }


def source_path(source: Path, relative: str) -> Path:
    path = source / relative
    require(path.is_file(), f"missing source file: {relative}")
    return path


def build(source: Path) -> None:
    source = source.resolve()
    ATTACHMENTS.mkdir(parents=True, exist_ok=True)
    for path in ATTACHMENTS.iterdir():
        if path.is_file():
            path.unlink()

    copies = {
        "ATTEMPT_TREE_INVENTORY.json": "ATTEMPT_TREE_INVENTORY.json",
        "DESIGNATED_OUTPUT_TREE_INVENTORY.json": "DESIGNATED_OUTPUT_TREE_INVENTORY.json",
        "SOURCE_ARCHIVE_VERIFICATION_OUTPUT.json": "B20_VERIFICATION_OUTPUT.json",
        "attachments/OWNERSHIP.json": "attachments/OWNERSHIP.json",
        "attachments/PRECREATE_INVENTORY.json": "attachments/PRECREATE_INVENTORY.json",
        "attachments/POSTCREATE_INVENTORY.json": "attachments/POSTCREATE_INVENTORY.json",
        "attachments/POSTDELETE_INVENTORY.json": "attachments/POSTDELETE_INVENTORY.json",
        "attachments/TERMINATION_AUDIT.json": "attachments/TERMINATION_AUDIT.json",
        "attachments/FROZEN_TERMINATION.json": "attachments/FROZEN_TERMINATION.json",
    }
    for destination, source_relative in copies.items():
        target = ROOT / destination
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source_path(source, source_relative), target)

    gate_path = source_path(source, "attachments/FINAL_RECOVERY_LAUNCH_GATE.json")
    gate = checked(gate_path)
    write_receipt(
        ATTACHMENTS / "LAUNCH_BINDING.json",
        {
            "attempt_id": gate["attempt_id"],
            "controller_sha256": gate["controller_sha256"],
            "freeze_commit": gate["freeze_commit"],
            "ownership_receipt_sha256": gate["ownership_receipt_sha256"],
            "pod_id": gate["pod_id"],
            "receipt_kind": "b20_portable_launch_binding_v1",
            "schema_version": 1,
            "status": gate["status"],
            "upstream_file_sha256": sha_file(gate_path),
            "upstream_receipt_sha256": gate["receipt_sha256"],
        },
    )

    authorization_path = source_path(source, "retrieved_attempt_snapshot/RECOVERY_AUTHORIZATION.json")
    authorization = checked(authorization_path)
    write_receipt(
        ATTACHMENTS / "AUTHORIZATION_BINDING.json",
        {
            "attempt_id": authorization["execution"]["attempt_id"],
            "authorized_at_utc": authorization["authorized_at_utc"],
            "freeze_commit": authorization["git_head_commit"],
            "ownership_receipt_sha256": authorization["fresh_receipts"]["ownership"],
            "pod_id": authorization["fresh_pod_id"],
            "receipt_kind": "b20_portable_authorization_binding_v1",
            "schema_version": 1,
            "status": authorization["status"],
            "upstream_file_sha256": sha_file(authorization_path),
            "upstream_receipt_sha256": authorization["receipt_sha256"],
        },
    )

    landlock_path = source_path(source, "retrieved_attempt_snapshot/output/LANDLOCK_ENFORCEMENT.json")
    landlock = checked(landlock_path)
    child = landlock["child_argv"]
    attempt_index = child.index("--attempt-id")
    write_receipt(
        ATTACHMENTS / "LANDLOCK_BINDING.json",
        {
            "attempt_id": child[attempt_index + 1],
            "authorization_receipt_sha256": landlock["authorization_sha256"],
            "receipt_kind": "b20_portable_landlock_binding_v1",
            "schema_version": 1,
            "source_sha256": landlock["source_sha256"],
            "status": landlock["status"],
            "upstream_file_sha256": sha_file(landlock_path),
            "upstream_receipt_sha256": landlock["receipt_sha256"],
        },
    )

    stderr_path = source_path(source, "attachments/controller.stderr")
    stderr = stderr_path.read_text(encoding="utf-8")
    frames = [
        "result = recovery.execute_recovery(args)",
        "authorization = validate_recovery_authorization(authorization_raw, args)",
        "historical_v5 = _validate_historical_v5_positive_review_evidence()",
        'value = _git_command("rev-parse", "HEAD").stdout.strip()',
    ]
    require(stderr.count(EXPECTED_ERROR) == 1, "source failure mismatch")
    require(all(frame in stderr for frame in frames), "source traceback frame missing")
    write_receipt(
        ATTACHMENTS / "FAILURE_EVIDENCE.json",
        {
            "error": EXPECTED_ERROR,
            "error_occurrences": 1,
            "phase": "final_confined_execution_before_attempt_marker",
            "receipt_kind": "b20_portable_failure_evidence_v1",
            "schema_version": 1,
            "scientific_result_status": "none_produced",
            "traceback_frames": frames,
            "upstream_controller_stderr_sha256": sha_file(stderr_path),
        },
    )

    attachment_roles = {
        "AUTHORIZATION_BINDING.json": "portable_fresh_authorization_binding",
        "FAILURE_EVIDENCE.json": "portable_exact_failure_trace",
        "FROZEN_TERMINATION.json": "provider_termination_receipt",
        "LANDLOCK_BINDING.json": "portable_final_confinement_binding",
        "LAUNCH_BINDING.json": "portable_launch_binding",
        "OWNERSHIP.json": "exact_owned_pod_receipt",
        "POSTCREATE_INVENTORY.json": "account_inventory_after_create",
        "POSTDELETE_INVENTORY.json": "account_inventory_after_delete",
        "PRECREATE_INVENTORY.json": "account_inventory_before_create",
        "TERMINATION_AUDIT.json": "exact_pod_termination_closure",
    }
    attachments = [record(ATTACHMENTS / name, role) for name, role in sorted(attachment_roles.items())]
    closure: dict[str, Any] = {
        "attachments": attachments,
        "designated_output": {
            "absent_paths": EXPECTED_ABSENCES,
            "file_count": 1,
            "files": ["LANDLOCK_ENFORCEMENT.json"],
            "landlock_receipt_sha256": EXPECTED_LANDLOCK,
        },
        "failure": {
            "error": EXPECTED_ERROR,
            "phase": "final_confined_execution_before_attempt_marker",
            "scientific_result_status": "none_produced",
        },
        "freeze_commit": EXPECTED_FREEZE,
        "identity": {
            "attempt_id": EXPECTED_ATTEMPT,
            "ownership_receipt_sha256": EXPECTED_OWNERSHIP,
            "pod_id": EXPECTED_POD,
        },
        "incident_id": "B20",
        "inventories": [
            record(ROOT / "ATTEMPT_TREE_INVENTORY.json", "private_attempt_tree_inventory"),
            record(ROOT / "DESIGNATED_OUTPUT_TREE_INVENTORY.json", "designated_output_tree_inventory"),
        ],
        "receipt_kind": "audit_recovery_b20_portable_incident_closure_v2",
        "remediation": {
            "device_policy_change": "none",
            "final_validation": "git_free",
            "status": "successor_fix_selected",
        },
        "schema_version": 2,
        "source_evidence_archive": {
            "availability": "omitted_from_repo_compact",
            "root_role": "private_complete_b20_archive",
            "source_closure_file_sha256": EXPECTED_SOURCE_CLOSURE_FILE,
            "source_closure_receipt_sha256": EXPECTED_SOURCE_CLOSURE_RECEIPT,
            "source_manifest_file_sha256": EXPECTED_SOURCE_MANIFEST_FILE,
            "source_verification_file_sha256": EXPECTED_SOURCE_VERIFICATION_FILE,
            "source_verification_receipt_sha256": EXPECTED_SOURCE_VERIFICATION_RECEIPT,
        },
        "status": "closed_technical_failure_no_scientific_result",
        "termination": {
            "frozen_termination_receipt_sha256": EXPECTED_FROZEN_TERMINATION,
            "postdelete_inventory_sha256": EXPECTED_EMPTY_INVENTORY,
            "precreate_inventory_sha256": EXPECTED_EMPTY_INVENTORY,
            "receipt_sha256": EXPECTED_TERMINATION,
            "status": "deleted_exact_owned_pod_unrelated_inventory_unchanged",
        },
    }
    write_receipt(ROOT / "B20_CLOSURE_RECEIPT.json", closure)
    verification = verification_value()
    write_receipt(ROOT / "B20_VERIFICATION_OUTPUT.json", verification)
    write_sha256sums()
    verify()


def verification_value() -> dict[str, Any]:
    return {
        "attempt_file_count": 71,
        "attempt_id": EXPECTED_ATTEMPT,
        "checks": [
            "source_attempt_and_output_inventories_self_hashed",
            "source_archive_verification_output_self_hashed_and_anchored",
            "only_landlock_receipt_recorded_in_designated_output",
            "attempt_marker_failure_compact_and_publication_outputs_recorded_absent",
            "portable_launch_authorization_landlock_chain_bound",
            "exact_git_dev_null_failure_bound_without_home_paths",
            "exact_owned_pod_deleted_and_unrelated_inventory_unchanged",
            "portable_incident_receipt_self_hashed_and_complete",
            "sha256sums_complete_and_valid",
        ],
        "incident_id": "B20",
        "output_file_count": 1,
        "output_files": ["LANDLOCK_ENFORCEMENT.json"],
        "pod_id": EXPECTED_POD,
        "receipt_kind": "audit_recovery_b20_public_compact_verification_v1",
        "schema_version": 1,
        "scientific_result_status": "none_produced",
        "status": "pass",
        "verification_scope": "portable_compact_plus_cryptographic_anchors_to_omitted_private_archive",
    }


def write_sha256sums() -> None:
    manifest = ROOT / "SHA256SUMS"
    lines = []
    for path in sorted(item for item in ROOT.rglob("*") if item.is_file() and item != manifest):
        lines.append(f"{sha_file(path)}  {path.relative_to(ROOT).as_posix()}")
    manifest.write_text("\n".join(lines) + "\n", encoding="utf-8")


def verify_manifest() -> None:
    manifest = ROOT / "SHA256SUMS"
    entries: dict[str, str] = {}
    for line in manifest.read_text(encoding="utf-8").splitlines():
        digest, relative = line.split("  ", 1)
        require(relative not in entries and len(digest) == 64, "invalid SHA256SUMS")
        entries[relative] = digest
    actual = {
        path.relative_to(ROOT).as_posix()
        for path in ROOT.rglob("*")
        if path.is_file() and path != manifest
    }
    require(set(entries) == actual, "SHA256SUMS file set mismatch")
    for relative, digest in entries.items():
        require(sha_file(ROOT / relative) == digest, f"SHA256 mismatch: {relative}")


def verify() -> dict[str, Any]:
    attempt = checked(ROOT / "ATTEMPT_TREE_INVENTORY.json")
    output = checked(ROOT / "DESIGNATED_OUTPUT_TREE_INVENTORY.json")
    source_verification = checked(ROOT / "SOURCE_ARCHIVE_VERIFICATION_OUTPUT.json")
    closure = checked(ROOT / "B20_CLOSURE_RECEIPT.json")
    stored_verification = checked(ROOT / "B20_VERIFICATION_OUTPUT.json")
    require(stored_verification == {**verification_value(), "receipt_sha256": self_hash(verification_value())}, "verification output mismatch")
    require(attempt["file_count"] == 71, "attempt inventory count mismatch")
    require(output["files"] == [{"bytes": 12658, "path": "LANDLOCK_ENFORCEMENT.json", "sha256": "513e43aacad05164c6cbc8ac2cf8a20e33aa00bf2beb5dd5951405026c4e46fd"}], "output inventory mismatch")
    require(output["expected_absences"] == [{"path": path, "status": "absent"} for path in EXPECTED_ABSENCES], "absence record mismatch")
    require(sha_file(ROOT / "SOURCE_ARCHIVE_VERIFICATION_OUTPUT.json") == EXPECTED_SOURCE_VERIFICATION_FILE, "source verification anchor mismatch")
    require(source_verification["status"] == "pass" and source_verification["scientific_result_status"] == "none_produced", "source verification status mismatch")

    launch = checked(ATTACHMENTS / "LAUNCH_BINDING.json")
    authorization = checked(ATTACHMENTS / "AUTHORIZATION_BINDING.json")
    landlock = checked(ATTACHMENTS / "LANDLOCK_BINDING.json")
    failure = checked(ATTACHMENTS / "FAILURE_EVIDENCE.json")
    ownership = checked(ATTACHMENTS / "OWNERSHIP.json")
    precreate = checked(ATTACHMENTS / "PRECREATE_INVENTORY.json")
    postcreate = checked(ATTACHMENTS / "POSTCREATE_INVENTORY.json")
    postdelete = checked(ATTACHMENTS / "POSTDELETE_INVENTORY.json")
    termination = checked(ATTACHMENTS / "TERMINATION_AUDIT.json")
    frozen = checked(ATTACHMENTS / "FROZEN_TERMINATION.json")
    require(launch["upstream_receipt_sha256"] == EXPECTED_GATE and launch["attempt_id"] == EXPECTED_ATTEMPT, "launch binding mismatch")
    require(authorization["upstream_receipt_sha256"] == EXPECTED_AUTHORIZATION and authorization["ownership_receipt_sha256"] == EXPECTED_OWNERSHIP, "authorization binding mismatch")
    require(landlock["upstream_receipt_sha256"] == EXPECTED_LANDLOCK and landlock["authorization_receipt_sha256"] == EXPECTED_AUTHORIZATION, "Landlock binding mismatch")
    require(failure["error"] == EXPECTED_ERROR and failure["scientific_result_status"] == "none_produced", "failure evidence mismatch")
    require(ownership["receipt_sha256"] == EXPECTED_OWNERSHIP and ownership["pod_id"] == EXPECTED_POD, "ownership mismatch")
    require(precreate["inventory_sha256"] == postdelete["inventory_sha256"] == EXPECTED_EMPTY_INVENTORY, "unrelated inventory changed")
    require(postcreate["all_account_pod_count"] == 1 and postcreate["pods"][0]["pod_id"] == EXPECTED_POD, "postcreate mismatch")
    require(termination["receipt_sha256"] == EXPECTED_TERMINATION and termination["pod_id"] == EXPECTED_POD, "termination mismatch")
    require(frozen["receipt_sha256"] == EXPECTED_FROZEN_TERMINATION and frozen["status"] == "deleted_verified", "frozen termination mismatch")
    require("source_evidence_root" not in closure, "nonportable source root leaked")
    require(closure["remediation"] == {"device_policy_change": "none", "final_validation": "git_free", "status": "successor_fix_selected"}, "remediation mismatch")
    for item in closure["attachments"] + closure["inventories"]:
        path = ROOT / item["path"]
        require(path.is_file() and path.stat().st_size == item["bytes"] and sha_file(path) == item["sha256"], f"closure file binding mismatch: {item['path']}")
    require(not (ROOT / "retrieved_attempt_snapshot").exists(), "private snapshot was included")
    require(not (ROOT / "RECOVERY_AUTHORIZATION.json").exists(), "large authorization blob was included")
    home_markers = tuple("/" + component + "/" for component in ("Users", "home", "root"))
    for path in [item for item in ROOT.rglob("*") if item.is_file() and item.suffix in {".json", ".md"}]:
        text = path.read_text(encoding="utf-8")
        require(all(token not in text for token in home_markers), f"home path leaked: {path.name}")
    verify_manifest()
    return stored_verification


def main() -> int:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--build-from", type=Path)
    mode.add_argument("--verify-only", action="store_true")
    args = parser.parse_args()
    if args.build_from:
        build(args.build_from)
    result = verify()
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

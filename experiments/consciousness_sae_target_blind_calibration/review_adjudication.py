"""Strict validator for the preserved multi-attempt Pro-review adjudication."""

from __future__ import annotations

import re
from typing import Any, Mapping, Sequence

from . import protocol


SCHEMA_VERSION = 2
RECEIPT_TYPE = "target_blind_calibration_multi_attempt_review_adjudication_v1"
REVIEW_MODEL = "gpt-5.6-sol"
RECEIPT_RELATIVE_PATH = (
    f"{protocol.CANONICAL_PLAN_RELATIVE_PATH}/REVIEW_ADJUDICATION.json"
)
HEX64_RE = re.compile(r"[0-9a-f]{64}")
COMMIT_RE = re.compile(r"[0-9a-f]{40}")

RECEIPT_FIELDS = frozenset(
    {
        "schema_version",
        "receipt_type",
        "status",
        "study_id",
        "protocol_version",
        "receipt_path",
        "review_model",
        "canonical_plan_relative_path",
        "final_plan_manifest_sha256",
        "provider_review_completion",
        "review_attempt_count",
        "review_attempts",
        "review_attempt_inventory_sha256",
        "combined_reconstructed_cost_usd",
        "account_level_billed_total_independently_reconciled",
        "r2_candidate",
        "r3_final",
        "candidate_source_inventory",
        "candidate_source_inventory_sha256",
        "final_source_inventory",
        "final_source_inventory_sha256",
        "candidate_plan_inventory",
        "candidate_plan_inventory_sha256",
        "final_plan_inventory",
        "final_plan_inventory_sha256",
        "candidate_to_final_changes",
        "candidate_to_final_change_inventory_sha256",
        "candidate_to_final_change_count",
        "stable_finding_id_map",
        "stable_finding_id_map_sha256",
        "finding_ids",
        "findings",
        "finding_inventory_sha256",
        "all_visible_findings_adjudicated",
        "blocking_closure_status",
        "unresolved_blocking_findings",
        "limitations",
        "prior_outcome_inputs",
        "receipt_sha256",
    }
)

ATTEMPT_FIELDS = frozenset(
    {
        "attempt_id",
        "response_id",
        "model",
        "provider_status",
        "incomplete_reason",
        "provider_completion_claimed",
        "input_tokens",
        "output_tokens",
        "reasoning_tokens",
        "total_tokens",
        "reconstructed_cost_usd",
        "human_authorization_usd",
        "authorization_overrun_usd",
        "summary_relative_path",
        "summary_file_sha256",
        "evidence_files",
        "evidence_file_inventory_sha256",
    }
)

EXPECTED_ATTEMPTS = (
    {
        "attempt_id": "attempt_1",
        "response_id": "resp_03b2871c96f53a60016a56bce54f548199a79a08dd76a6468c",
        "model": REVIEW_MODEL,
        "provider_status": "incomplete",
        "incomplete_reason": "max_output_tokens",
        "provider_completion_claimed": False,
        "input_tokens": 181_816,
        "output_tokens": 30_181,
        "reasoning_tokens": 12_257,
        "total_tokens": 211_997,
        "reconstructed_cost_usd": 1.81451,
        "human_authorization_usd": 1.25,
        "authorization_overrun_usd": 0.56451,
        "summary_relative_path": (
            "docs/consciousness_sae_target_blind_calibration/reviews/"
            "GPT_PRO_ATTEMPT_1.md"
        ),
        "evidence_files": (
            (
                "review_request",
                "f50ee94c859c1fee5fee7d4b349c688edefd70b5708e35a60d1ceb24d43b3301",
            ),
            (
                "request_payload",
                "d112d32b9ecff89a1a64826ba98ac9f16546c3e670bfc4fea31369c0f89bc75d",
            ),
            (
                "response",
                "f555ec93be878eeda8994c79f255571ec5b505ca16bb4d68d27b1772d4723f47",
            ),
            (
                "failure",
                "8e3604648c0c6ab9f9bdf34aeab01a0f1b3766d06ac98ff12216fca94ca376f4",
            ),
            (
                "review_manifest",
                "3d6200cc575b724ea990ed9a0dcc6bfb6d354d43de3d188a80b91bec52898a7f",
            ),
        ),
    },
    {
        "attempt_id": "attempt_2",
        "response_id": "resp_0adacaf3f23ab4c3016a56c8dee1b08199b1e53029c6dac8c8",
        "model": REVIEW_MODEL,
        "provider_status": "incomplete",
        "incomplete_reason": "max_output_tokens",
        "provider_completion_claimed": False,
        "input_tokens": 76_998,
        "output_tokens": 9_132,
        "reasoning_tokens": 7_969,
        "total_tokens": 86_130,
        "reconstructed_cost_usd": 0.65895,
        "human_authorization_usd": 1.25,
        "authorization_overrun_usd": 0.0,
        "summary_relative_path": (
            "docs/consciousness_sae_target_blind_calibration/reviews/"
            "GPT_PRO_ATTEMPT_2.md"
        ),
        "evidence_files": (
            (
                "review_request",
                "5e468ce32e7033e0fbe6d08f3752e70f12b0324d3758ecbc885a37f61ff3e7df",
            ),
            (
                "request_payload",
                "0657c17bb9bd3ad75a067d8516688a8773afd2198b82529f113306ec8680f91e",
            ),
            (
                "response",
                "0072ba7bc0a98d9b491c6075af817fe0ba3a254389ec5141c13007620381059e",
            ),
            (
                "failure",
                "ae62efd4cca95191a98cb3ab98ecf5ee9a212b67cc0a5c97d1fa40b0f10ff1f8",
            ),
            (
                "review_manifest",
                "f8d549894b31dead46c42f6a6bb783564459b45a55ed6594a7e0dd5b441577eb",
            ),
        ),
    },
)

R2_CANDIDATE = {
    "canonical_plan_directory": (
        "data/consciousness_sae_target_blind_calibration/"
        "calibration_v2_plan_20260714_r2"
    ),
    "reviewed_protocol_sha256": (
        "5be4e7843f01b17f72d2c8ecde74e987454b5ed56530becb24769ae5bc12406f"
    ),
    "plan_manifest_sha256": (
        "022c1012498f45f767c62cb3b07b88c8be0c2f3fd7ff0bc45ff459bf73e2772f"
    ),
    "plan_manifest_file_sha256": (
        "0608b1d528a5e8da450d80f4becae57ccdc319a0c4e63b2407c8e98aa803a052"
    ),
    "source_inventory_file_sha256": (
        "04e3f4c75389ceabd366d731feeff080eba28038d3662cef2ef0589c48d0e901"
    ),
    "source_file_inventory_sha256": (
        "a3b23e6ddd5ed92cf9267203bd9b42d98a401f51904b313ce8590b58c9b0ec76"
    ),
    "machine_plan_submitted_in_attempt_2": False,
}


class ReviewAdjudicationError(RuntimeError):
    """Raised when review closure evidence is incomplete or inconsistent."""


def _require_hash(value: Any, label: str) -> str:
    if not isinstance(value, str) or HEX64_RE.fullmatch(value) is None:
        raise ReviewAdjudicationError(f"{label} is not a SHA-256")
    return value


def _require_hashed_list(receipt: Mapping[str, Any], field: str) -> list[Any]:
    value = receipt.get(field)
    if not isinstance(value, list):
        raise ReviewAdjudicationError(f"{field} is not a list")
    supplied = _require_hash(receipt.get(f"{field}_sha256"), f"{field} hash")
    if supplied != protocol.canonical_sha256(value):
        raise ReviewAdjudicationError(f"{field} hash differs")
    return value


def _require_named_hashed_list(
    receipt: Mapping[str, Any], value_field: str, hash_field: str
) -> list[Any]:
    value = receipt.get(value_field)
    if not isinstance(value, list):
        raise ReviewAdjudicationError(f"{value_field} is not a list")
    supplied = _require_hash(receipt.get(hash_field), f"{value_field} hash")
    if supplied != protocol.canonical_sha256(value):
        raise ReviewAdjudicationError(f"{value_field} hash differs")
    return value


def _inventory(rows: Sequence[Any], label: str) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, Mapping) or set(row) != {"path", "bytes", "sha256"}:
            raise ReviewAdjudicationError(f"{label} row schema differs")
        path = row.get("path")
        size = row.get("bytes")
        if (
            not isinstance(path, str)
            or not path
            or path in result
            or isinstance(size, bool)
            or not isinstance(size, int)
            or size < 0
        ):
            raise ReviewAdjudicationError(f"{label} row identity differs")
        _require_hash(row.get("sha256"), f"{label} row hash")
        result[path] = dict(row)
    return result


def _validate_attempts(rows: Sequence[Any]) -> None:
    if len(rows) != len(EXPECTED_ATTEMPTS):
        raise ReviewAdjudicationError("review attempt count differs")
    for row, expected in zip(rows, EXPECTED_ATTEMPTS, strict=True):
        if not isinstance(row, Mapping) or set(row) != ATTEMPT_FIELDS:
            raise ReviewAdjudicationError("review attempt schema differs")
        for key, value in expected.items():
            if key != "evidence_files" and row.get(key) != value:
                raise ReviewAdjudicationError(
                    f"{expected['attempt_id']} evidence differs"
                )
        summary_hash = _require_hash(
            row.get("summary_file_sha256"), "review summary file hash"
        )
        if not summary_hash:
            raise ReviewAdjudicationError("review summary file hash is empty")
        evidence = row.get("evidence_files")
        expected_evidence = [
            {"role": role, "sha256": digest}
            for role, digest in expected["evidence_files"]
        ]
        if evidence != expected_evidence or row.get(
            "evidence_file_inventory_sha256"
        ) != protocol.canonical_sha256(expected_evidence):
            raise ReviewAdjudicationError(
                f"{expected['attempt_id']} evidence inventory differs"
            )


def _validate_findings(receipt: Mapping[str, Any]) -> set[str]:
    findings = _require_named_hashed_list(
        receipt, "findings", "finding_inventory_sha256"
    )
    finding_ids = receipt.get("finding_ids")
    if not isinstance(finding_ids, list) or not all(
        isinstance(item, str) and item for item in finding_ids
    ):
        raise ReviewAdjudicationError("finding ID inventory differs")
    observed: list[str] = []
    authorized: set[str] = set()
    for row in findings:
        required = {
            "stable_finding_id",
            "attempt_id",
            "provider_finding_id",
            "finding_class",
            "title",
            "decision",
            "disposition",
            "rationale",
            "evidence",
            "evidence_inventory_sha256",
            "authorizes_candidate_to_final_changes",
        }
        if not isinstance(row, Mapping) or set(row) != required:
            raise ReviewAdjudicationError("finding row schema differs")
        stable = row.get("stable_finding_id")
        expected_stable = f"{row.get('attempt_id')}/{row.get('provider_finding_id')}"
        if (
            not isinstance(stable, str)
            or stable != expected_stable
            or stable in observed
            or row.get("decision")
            not in {"accept", "accepted_modified", "reject", "defer"}
            or row.get("disposition")
            not in {"fixed", "preserved", "clarified", "rejected", "deferred"}
            or row.get("finding_class")
            not in {"blocking", "important_nonblocking", "local_integrity"}
            or not isinstance(row.get("title"), str)
            or not row["title"]
            or not isinstance(row.get("rationale"), str)
            or not row["rationale"]
            or not isinstance(row.get("authorizes_candidate_to_final_changes"), bool)
        ):
            raise ReviewAdjudicationError("finding identity/disposition differs")
        if row["finding_class"] == "blocking" and (
            row["decision"] == "defer" or row["disposition"] == "deferred"
        ):
            raise ReviewAdjudicationError(f"{stable} blocking finding is deferred")
        evidence = row.get("evidence")
        if (
            not isinstance(evidence, list)
            or not all(isinstance(item, str) and item for item in evidence)
            or row.get("evidence_inventory_sha256")
            != protocol.canonical_sha256(evidence)
        ):
            raise ReviewAdjudicationError(f"{stable} evidence differs")
        if row["authorizes_candidate_to_final_changes"]:
            if row["decision"] not in {"accept", "accepted_modified"} or row[
                "disposition"
            ] not in {"fixed", "clarified"}:
                raise ReviewAdjudicationError(
                    f"{stable} cannot authorize candidate-to-final changes"
                )
            authorized.add(stable)
        observed.append(stable)
    if finding_ids != observed:
        raise ReviewAdjudicationError("finding IDs differ from finding rows")
    mapping = _require_hashed_list(receipt, "stable_finding_id_map")
    expected_mapping = [
        {
            "stable_finding_id": row["stable_finding_id"],
            "attempt_id": row["attempt_id"],
            "provider_finding_id": row["provider_finding_id"],
        }
        for row in findings
    ]
    if mapping != expected_mapping:
        raise ReviewAdjudicationError("stable finding map differs")
    required_visible = {
        *(f"attempt_1/B{index:02d}" for index in range(1, 9)),
        *(f"attempt_1/I{index:02d}" for index in range(1, 8)),
        "attempt_2/B01",
    }
    if not required_visible.issubset(set(observed)):
        raise ReviewAdjudicationError(
            "not every visible provider finding is adjudicated"
        )
    return authorized


def _expected_changes(
    candidate: Mapping[str, Mapping[str, Any]],
    final: Mapping[str, Mapping[str, Any]],
    artifact_class: str,
) -> dict[tuple[str, str], dict[str, Any]]:
    result: dict[tuple[str, str], dict[str, Any]] = {}
    for path in sorted(set(candidate) | set(final)):
        before = candidate.get(path)
        after = final.get(path)
        if before == after:
            continue
        kind = "added" if before is None else "removed" if after is None else "modified"
        result[(artifact_class, path)] = {
            "path": path,
            "artifact_class": artifact_class,
            "change_kind": kind,
            "candidate": (
                None
                if before is None
                else {"bytes": before["bytes"], "sha256": before["sha256"]}
            ),
            "final": (
                None
                if after is None
                else {"bytes": after["bytes"], "sha256": after["sha256"]}
            ),
        }
    return result


def validate_adjudication_receipt(
    receipt: Mapping[str, Any],
    *,
    final_plan_manifest_sha256: str,
    final_plan_relative_path: str,
) -> dict[str, Any]:
    """Validate exact review evidence and candidate-to-final change lineage."""

    if not isinstance(receipt, Mapping) or set(receipt) != RECEIPT_FIELDS:
        raise ReviewAdjudicationError("review adjudication schema differs")
    core = dict(receipt)
    supplied = _require_hash(core.pop("receipt_sha256", None), "receipt self-hash")
    if supplied != protocol.canonical_sha256(core):
        raise ReviewAdjudicationError("review adjudication self-hash differs")
    _require_hash(final_plan_manifest_sha256, "expected final plan hash")
    if (
        receipt.get("schema_version") != SCHEMA_VERSION
        or receipt.get("receipt_type") != RECEIPT_TYPE
        or receipt.get("status") != "adjudicated_no_unresolved_blockers"
        or receipt.get("study_id") != protocol.STUDY_ID
        or receipt.get("protocol_version") != protocol.PROTOCOL_VERSION
        or receipt.get("receipt_path") != RECEIPT_RELATIVE_PATH
        or receipt.get("review_model") != REVIEW_MODEL
        or receipt.get("canonical_plan_relative_path")
        != protocol.CANONICAL_PLAN_RELATIVE_PATH
        or final_plan_relative_path != protocol.CANONICAL_PLAN_RELATIVE_PATH
        or receipt.get("final_plan_manifest_sha256") != final_plan_manifest_sha256
        or receipt.get("combined_reconstructed_cost_usd") != 2.47346
        or receipt.get("account_level_billed_total_independently_reconciled")
        is not False
        or receipt.get("prior_outcome_inputs") != []
    ):
        raise ReviewAdjudicationError("review adjudication identity differs")
    completion = receipt.get("provider_review_completion")
    if completion != {
        "completed_attempt_count": 0,
        "incomplete_attempt_count": 2,
        "all_attempts_provider_complete": False,
        "adjudication_scope": "visible_output_only",
        "provider_pass_claimed": False,
    }:
        raise ReviewAdjudicationError("provider completion status differs")
    attempts = _require_named_hashed_list(
        receipt, "review_attempts", "review_attempt_inventory_sha256"
    )
    if receipt.get("review_attempt_count") != len(attempts):
        raise ReviewAdjudicationError("review attempt inventory differs")
    _validate_attempts(attempts)
    if receipt.get("r2_candidate") != R2_CANDIDATE:
        raise ReviewAdjudicationError("r2 reviewed-candidate identity differs")

    candidate_source = _inventory(
        _require_hashed_list(receipt, "candidate_source_inventory"),
        "candidate source inventory",
    )
    if (
        receipt["candidate_source_inventory_sha256"]
        != R2_CANDIDATE["source_file_inventory_sha256"]
    ):
        raise ReviewAdjudicationError("candidate source inventory hash differs")
    final_source = _inventory(
        _require_hashed_list(receipt, "final_source_inventory"),
        "final source inventory",
    )
    candidate_plan = _inventory(
        _require_hashed_list(receipt, "candidate_plan_inventory"),
        "candidate plan inventory",
    )
    final_plan = _inventory(
        _require_hashed_list(receipt, "final_plan_inventory"),
        "final plan inventory",
    )
    r3 = receipt.get("r3_final")
    required_r3 = {
        "canonical_plan_directory",
        "plan_manifest_sha256",
        "plan_manifest_file_sha256",
        "source_inventory_file_sha256",
        "source_file_inventory_sha256",
        "git_head_commit",
        "independent_plan_audit_sha256",
        "independent_plan_audit_file_sha256",
        "provider_reviewed",
    }
    if (
        not isinstance(r3, Mapping)
        or set(r3) != required_r3
        or r3.get("canonical_plan_directory") != final_plan_relative_path
        or r3.get("plan_manifest_sha256") != final_plan_manifest_sha256
        or r3.get("source_file_inventory_sha256")
        != receipt.get("final_source_inventory_sha256")
        or r3.get("provider_reviewed") is not False
        or COMMIT_RE.fullmatch(str(r3.get("git_head_commit", ""))) is None
        or final_plan.get("plan_manifest.json", {}).get("sha256")
        != r3.get("plan_manifest_file_sha256")
        or final_plan.get("source_files.json", {}).get("sha256")
        != r3.get("source_inventory_file_sha256")
    ):
        raise ReviewAdjudicationError("r3 final-plan identity differs")
    _require_hash(r3.get("independent_plan_audit_sha256"), "plan audit self-hash")
    _require_hash(r3.get("independent_plan_audit_file_sha256"), "plan audit file hash")

    authorized_findings = _validate_findings(receipt)
    changes = _require_named_hashed_list(
        receipt,
        "candidate_to_final_changes",
        "candidate_to_final_change_inventory_sha256",
    )
    if receipt.get("candidate_to_final_change_count") != len(changes):
        raise ReviewAdjudicationError("candidate-to-final change inventory differs")
    expected_changes = {
        **_expected_changes(candidate_source, final_source, "bound_source"),
        **_expected_changes(candidate_plan, final_plan, "plan_file"),
    }
    observed_changes: dict[tuple[str, str], Mapping[str, Any]] = {}
    for row in changes:
        if not isinstance(row, Mapping) or set(row) != {
            "path",
            "artifact_class",
            "change_kind",
            "candidate",
            "final",
            "finding_ids",
        }:
            raise ReviewAdjudicationError("candidate-to-final change row differs")
        key = (str(row.get("artifact_class")), str(row.get("path")))
        expected = expected_changes.get(key)
        if (
            key in observed_changes
            or expected is None
            or any(row.get(field) != value for field, value in expected.items())
        ):
            raise ReviewAdjudicationError("candidate-to-final reconstruction differs")
        finding_ids = row.get("finding_ids")
        if (
            not isinstance(finding_ids, list)
            or not finding_ids
            or not all(item in authorized_findings for item in finding_ids)
        ):
            raise ReviewAdjudicationError("candidate-to-final finding mapping differs")
        observed_changes[key] = row
    if set(observed_changes) != set(expected_changes):
        raise ReviewAdjudicationError("not every candidate-to-final change is mapped")

    limitations = receipt.get("limitations")
    if not isinstance(limitations, list) or not all(
        isinstance(item, str) and item for item in limitations
    ):
        raise ReviewAdjudicationError("review limitation inventory differs")
    required_limitation_terms = (
        "both provider responses were incomplete",
        "attempt 1",
        "attempt 2",
        "complete r2 machine plan",
        "r3 was not provider-reviewed",
        "visible findings",
    )
    joined = " ".join(limitations).lower()
    if any(term not in joined for term in required_limitation_terms):
        raise ReviewAdjudicationError("required review limitation is missing")
    if (
        receipt.get("all_visible_findings_adjudicated") is not True
        or receipt.get("blocking_closure_status") != "all_visible_blockers_closed"
        or receipt.get("unresolved_blocking_findings") != []
    ):
        raise ReviewAdjudicationError("visible blocker closure differs")
    return dict(receipt)


def bound_paths(receipt: Mapping[str, Any]) -> tuple[str, ...]:
    """Return tracked evidence paths named by a validated receipt."""

    attempts = receipt.get("review_attempts")
    if not isinstance(attempts, list):
        raise ReviewAdjudicationError("review attempts are missing")
    paths = [str(receipt.get("receipt_path", ""))]
    paths.extend(str(row.get("summary_relative_path", "")) for row in attempts)
    if any(not path for path in paths) or len(paths) != len(set(paths)):
        raise ReviewAdjudicationError("review evidence path inventory differs")
    return tuple(sorted(paths))

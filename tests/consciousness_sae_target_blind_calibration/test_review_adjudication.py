from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from experiments.consciousness_sae_target_blind_calibration import (
    protocol,
    review_adjudication,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
R2_ROOT = (
    REPO_ROOT / "data/consciousness_sae_target_blind_calibration/"
    "calibration_v2_plan_20260714_r2"
)


def _hash_lists(value: dict) -> None:
    for field, hash_field in (
        ("review_attempts", "review_attempt_inventory_sha256"),
        ("candidate_source_inventory", "candidate_source_inventory_sha256"),
        ("final_source_inventory", "final_source_inventory_sha256"),
        ("candidate_plan_inventory", "candidate_plan_inventory_sha256"),
        ("final_plan_inventory", "final_plan_inventory_sha256"),
        (
            "candidate_to_final_changes",
            "candidate_to_final_change_inventory_sha256",
        ),
        ("stable_finding_id_map", "stable_finding_id_map_sha256"),
        ("findings", "finding_inventory_sha256"),
    ):
        value[hash_field] = protocol.canonical_sha256(value[field])


def _plan_inventory(root: Path) -> list[dict]:
    manifest = json.loads((root / "plan_manifest.json").read_text())
    rows = [dict(row) for row in manifest["files"]]
    path = root / "plan_manifest.json"
    rows.append(
        {
            "path": "plan_manifest.json",
            "bytes": path.stat().st_size,
            "sha256": protocol.sha256_file(path),
        }
    )
    return sorted(rows, key=lambda row: row["path"])


def _finding(stable: str, *, authorizes: bool = False) -> dict:
    attempt, finding_id = stable.split("/", 1)
    evidence = ["tests/consciousness_sae_target_blind_calibration"]
    return {
        "stable_finding_id": stable,
        "attempt_id": attempt,
        "provider_finding_id": finding_id,
        "finding_class": (
            "blocking"
            if finding_id.startswith("B")
            else "important_nonblocking"
            if finding_id.startswith("I")
            else "local_integrity"
        ),
        "title": f"Adjudicated {stable}",
        "decision": "accept",
        "disposition": "fixed" if authorizes else "preserved",
        "rationale": "The visible finding has a recorded, evidence-bound disposition.",
        "evidence": evidence,
        "evidence_inventory_sha256": protocol.canonical_sha256(evidence),
        "authorizes_candidate_to_final_changes": authorizes,
    }


def _receipt() -> dict:
    candidate_source = json.loads((R2_ROOT / "source_files.json").read_text())["files"]
    final_source = copy.deepcopy(candidate_source)
    final_source[0] = {
        **final_source[0],
        "bytes": final_source[0]["bytes"] + 1,
        "sha256": "1" * 64,
    }
    candidate_plan = _plan_inventory(R2_ROOT)
    final_plan = copy.deepcopy(candidate_plan)
    for row in final_plan:
        if row["path"] == "plan_manifest.json":
            row["bytes"] += 1
            row["sha256"] = "2" * 64
        elif row["path"] == "source_files.json":
            row["bytes"] += 1
            row["sha256"] = "3" * 64

    attempts = []
    for expected in review_adjudication.EXPECTED_ATTEMPTS:
        evidence = [
            {"role": role, "sha256": digest}
            for role, digest in expected["evidence_files"]
        ]
        summary = REPO_ROOT / expected["summary_relative_path"]
        attempts.append(
            {
                **{
                    key: value
                    for key, value in expected.items()
                    if key != "evidence_files"
                },
                "summary_file_sha256": protocol.sha256_file(summary),
                "evidence_files": evidence,
                "evidence_file_inventory_sha256": protocol.canonical_sha256(evidence),
            }
        )

    finding_ids = [
        *(f"attempt_1/B{index:02d}" for index in range(1, 9)),
        *(f"attempt_1/I{index:02d}" for index in range(1, 8)),
        "attempt_2/B01",
        "local_review/A01",
    ]
    findings = [
        _finding(
            stable,
            authorizes=stable in {"attempt_2/B01", "local_review/A01"},
        )
        for stable in finding_ids
    ]
    mapping = [
        {
            key: row[key]
            for key in ("stable_finding_id", "attempt_id", "provider_finding_id")
        }
        for row in findings
    ]
    changes = [
        {
            "path": candidate_source[0]["path"],
            "artifact_class": "bound_source",
            "change_kind": "modified",
            "candidate": {
                "bytes": candidate_source[0]["bytes"],
                "sha256": candidate_source[0]["sha256"],
            },
            "final": {
                "bytes": final_source[0]["bytes"],
                "sha256": final_source[0]["sha256"],
            },
            "finding_ids": ["attempt_2/B01"],
        },
        *[
            {
                "path": path,
                "artifact_class": "plan_file",
                "change_kind": "modified",
                "candidate": {
                    "bytes": next(
                        row["bytes"] for row in candidate_plan if row["path"] == path
                    ),
                    "sha256": next(
                        row["sha256"] for row in candidate_plan if row["path"] == path
                    ),
                },
                "final": {
                    "bytes": next(
                        row["bytes"] for row in final_plan if row["path"] == path
                    ),
                    "sha256": next(
                        row["sha256"] for row in final_plan if row["path"] == path
                    ),
                },
                "finding_ids": ["local_review/A01"],
            }
            for path in ("plan_manifest.json", "source_files.json")
        ],
    ]
    value = {
        "schema_version": review_adjudication.SCHEMA_VERSION,
        "receipt_type": review_adjudication.RECEIPT_TYPE,
        "status": "adjudicated_no_unresolved_blockers",
        "study_id": protocol.STUDY_ID,
        "protocol_version": protocol.PROTOCOL_VERSION,
        "receipt_path": review_adjudication.RECEIPT_RELATIVE_PATH,
        "review_model": review_adjudication.REVIEW_MODEL,
        "canonical_plan_relative_path": protocol.CANONICAL_PLAN_RELATIVE_PATH,
        "final_plan_manifest_sha256": "f" * 64,
        "provider_review_completion": {
            "completed_attempt_count": 0,
            "incomplete_attempt_count": 2,
            "all_attempts_provider_complete": False,
            "adjudication_scope": "visible_output_only",
            "provider_pass_claimed": False,
        },
        "review_attempt_count": len(attempts),
        "review_attempts": attempts,
        "review_attempt_inventory_sha256": "",
        "combined_reconstructed_cost_usd": 2.47346,
        "account_level_billed_total_independently_reconciled": False,
        "r2_candidate": dict(review_adjudication.R2_CANDIDATE),
        "r3_final": {
            "canonical_plan_directory": protocol.CANONICAL_PLAN_RELATIVE_PATH,
            "plan_manifest_sha256": "f" * 64,
            "plan_manifest_file_sha256": "2" * 64,
            "source_inventory_file_sha256": "3" * 64,
            "source_file_inventory_sha256": protocol.canonical_sha256(final_source),
            "git_head_commit": "e" * 40,
            "independent_plan_audit_sha256": "4" * 64,
            "independent_plan_audit_file_sha256": "5" * 64,
            "provider_reviewed": False,
        },
        "candidate_source_inventory": candidate_source,
        "candidate_source_inventory_sha256": "",
        "final_source_inventory": final_source,
        "final_source_inventory_sha256": "",
        "candidate_plan_inventory": candidate_plan,
        "candidate_plan_inventory_sha256": "",
        "final_plan_inventory": final_plan,
        "final_plan_inventory_sha256": "",
        "candidate_to_final_changes": changes,
        "candidate_to_final_change_inventory_sha256": "",
        "candidate_to_final_change_count": len(changes),
        "stable_finding_id_map": mapping,
        "stable_finding_id_map_sha256": "",
        "finding_ids": finding_ids,
        "findings": findings,
        "finding_inventory_sha256": "",
        "all_visible_findings_adjudicated": True,
        "blocking_closure_status": "all_visible_blockers_closed",
        "unresolved_blocking_findings": [],
        "limitations": [
            "Both provider responses were incomplete.",
            "Attempt 1's freeze checklist was truncated.",
            "Attempt 2 omitted the requested freeze checklist.",
            "Attempt 2 did not inspect the complete r2 machine plan/source closure.",
            "r3 was not provider-reviewed.",
            "Closure applies only to visible findings, not an unqualified Pro pass.",
        ],
        "prior_outcome_inputs": [],
        "receipt_sha256": "",
    }
    _hash_lists(value)
    core = dict(value)
    core.pop("receipt_sha256")
    value["receipt_sha256"] = protocol.canonical_sha256(core)
    return value


def _rehash(value: dict) -> None:
    _hash_lists(value)
    core = dict(value)
    core.pop("receipt_sha256", None)
    value["receipt_sha256"] = protocol.canonical_sha256(core)


def test_strict_multi_attempt_adjudication_validates() -> None:
    value = _receipt()
    assert (
        review_adjudication.validate_adjudication_receipt(
            value,
            final_plan_manifest_sha256="f" * 64,
            final_plan_relative_path=protocol.CANONICAL_PLAN_RELATIVE_PATH,
        )["receipt_sha256"]
        == value["receipt_sha256"]
    )
    assert review_adjudication.bound_paths(value) == tuple(
        sorted(
            (
                review_adjudication.RECEIPT_RELATIVE_PATH,
                *(row["summary_relative_path"] for row in value["review_attempts"]),
            )
        )
    )


def test_provider_incompleteness_cannot_be_relabelled() -> None:
    value = _receipt()
    value["provider_review_completion"]["provider_pass_claimed"] = True
    _rehash(value)
    with pytest.raises(
        review_adjudication.ReviewAdjudicationError,
        match="provider completion",
    ):
        review_adjudication.validate_adjudication_receipt(
            value,
            final_plan_manifest_sha256="f" * 64,
            final_plan_relative_path=protocol.CANONICAL_PLAN_RELATIVE_PATH,
        )


def test_unmapped_candidate_to_final_change_is_rejected() -> None:
    value = _receipt()
    value["candidate_to_final_changes"][0]["finding_ids"] = ["attempt_1/B01"]
    _rehash(value)
    with pytest.raises(
        review_adjudication.ReviewAdjudicationError,
        match="finding mapping",
    ):
        review_adjudication.validate_adjudication_receipt(
            value,
            final_plan_manifest_sha256="f" * 64,
            final_plan_relative_path=protocol.CANONICAL_PLAN_RELATIVE_PATH,
        )

"""Outcome-free tests for the authorized confirmatory-analysis entrypoint."""

from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from experiments.consciousness_sae_changepoint import analyze_run
from experiments.consciousness_sae_changepoint.protocol import (
    PROTOCOL_VERSION,
    STUDY_ID,
)


PLAN_HASH = "1" * 64
RUN_ID = "stage2a-authorized"


def endpoint_row(prefix_id: str, prefix_hash: str) -> dict[str, object]:
    branches = analyze_run.MECHANISM_BRANCHES
    layers = {
        branch: {
            str(layer): float(index + layer) / 100.0
            for layer in range(51, 79)
        }
        for index, branch in enumerate(branches)
    }
    final = {branch: float(index) for index, branch in enumerate(branches)}
    row: dict[str, object] = {
        "schema_version": analyze_run.ENDPOINT_SCHEMA_VERSION,
        "study_id": STUDY_ID,
        "protocol_version": PROTOCOL_VERSION,
        "plan_hash": PLAN_HASH,
        "stage": "stage2a",
        "run_id": RUN_ID,
        "prefix_id": prefix_id,
        "prefix_token_ids_sha256": prefix_hash,
        "judge_definition_sha256": analyze_run.frozen_judge_definition_sha256(),
        "endpoint_builder_source_sha256": analyze_run.endpoint_builder_source_sha256(),
        "source_payload_sha256": {
            filename: f"{index + 3:x}" * 64
            for index, filename in enumerate(analyze_run.SOURCE_PAYLOAD_FILES)
        },
        "natural_stance_by_branch": {
            "never": 0,
            "target_supp": 1,
            "target_amp": -1,
            "matched_supp": 0,
            "matched_amp": 0,
        },
        "active_terminal_query_by_branch": {
            "target_supp": True,
            "target_amp": False,
            "matched_supp": False,
            "matched_amp": False,
        },
        "c3_report_polarity_j_scores_by_branch_layer": layers,
        "c3_report_polarity_final_logits_by_branch": final,
        "c4_explicit_consciousness_j_scores_by_branch_layer": layers,
        "c4_explicit_consciousness_final_logits_by_branch": final,
    }
    row["receipt_sha256"] = analyze_run._embedded_sha256(row)
    return row


class EndpointContractTests(unittest.TestCase):
    def test_valid_endpoint_reconstructs_all_seven_components(self) -> None:
        prefix_id = "a" * 24
        prefix_hash = "b" * 64
        result = analyze_run.validate_endpoint_row(
            endpoint_row(prefix_id, prefix_hash),
            plan_hash=PLAN_HASH,
            run_id=RUN_ID,
            prefix_id=prefix_id,
            prefix_token_ids_sha256=prefix_hash,
        )
        self.assertEqual(result["C1"], 1.0)
        self.assertEqual(result["C2a"], 1.0)
        self.assertEqual(result["C2b"], 1.0)
        self.assertEqual(
            set(result),
            {
                "prefix_id",
                "prefix_token_ids_sha256",
                "endpoint_receipt_sha256",
                "C1",
                "C2a",
                "C2b",
                "C3_j",
                "C3_final",
                "C4_j",
                "C4_final",
            },
        )

    def test_resigned_row_cannot_change_frozen_branch_or_layer_contract(self) -> None:
        prefix_id = "a" * 24
        prefix_hash = "b" * 64
        for mutation in ("branch", "layer"):
            forged = endpoint_row(prefix_id, prefix_hash)
            if mutation == "branch":
                forged["natural_stance_by_branch"]["post_hoc_branch"] = 1
            else:
                del forged["c4_explicit_consciousness_j_scores_by_branch_layer"][
                    "never"
                ]["78"]
            forged["receipt_sha256"] = analyze_run._embedded_sha256(forged)
            with self.subTest(mutation=mutation), self.assertRaises(
                analyze_run.AuthorizedAnalysisError
            ):
                analyze_run.validate_endpoint_row(
                    forged,
                    plan_hash=PLAN_HASH,
                    run_id=RUN_ID,
                    prefix_id=prefix_id,
                    prefix_token_ids_sha256=prefix_hash,
                )

    def test_inventory_rejects_duplicate_missing_and_unexpected_prefix_rows(self) -> None:
        expected = ["a" * 24, "b" * 24]
        hashes = {expected[0]: "c" * 64, expected[1]: "d" * 64}
        rows = [
            endpoint_row(expected[0], hashes[expected[0]]),
            endpoint_row(expected[1], hashes[expected[1]]),
        ]
        validated = analyze_run.validate_endpoint_inventory(
            rows,
            expected_prefix_ids=expected,
            plan_hash=PLAN_HASH,
            run_id=RUN_ID,
            prefix_token_hashes=hashes,
        )
        self.assertEqual([row["prefix_id"] for row in validated], expected)
        bad_sets = (
            [rows[0], copy.deepcopy(rows[0])],
            [rows[0]],
            [*rows, endpoint_row("e" * 24, "f" * 64)],
        )
        for bad in bad_sets:
            with self.subTest(count=len(bad)), self.assertRaises(
                analyze_run.AuthorizedAnalysisError
            ):
                analyze_run.validate_endpoint_inventory(
                    bad,
                    expected_prefix_ids=expected,
                    plan_hash=PLAN_HASH,
                    run_id=RUN_ID,
                    prefix_token_hashes=hashes,
                )

    def test_duplicate_rendered_prefixes_are_clustered_with_occurrence_weights(self) -> None:
        rows = []
        for index, cluster in enumerate(("a" * 64, "a" * 64, "b" * 64)):
            rows.append(
                {
                    "prefix_id": f"{index:024x}",
                    "prefix_token_ids_sha256": cluster,
                    "endpoint_receipt_sha256": f"{index + 3:x}" * 64,
                    "C1": float(index),
                    "C2a": float(index),
                    "C2b": float(index),
                    "C3_j": float(index),
                    "C3_final": float(index),
                    "C4_j": float(index),
                    "C4_final": float(index),
                }
            )
        collapsed, weights, cluster_ids = analyze_run._collapse_inputs(rows)
        self.assertEqual(cluster_ids, ["a" * 64, "b" * 64])
        self.assertEqual(collapsed["C1"], [0.5, 2.0])
        self.assertEqual(weights["C1"], [2.0, 1.0])


class AuthorizationOrderAndPathTests(unittest.TestCase):
    def test_authorization_failure_happens_before_any_target_loader(self) -> None:
        sentinel = RuntimeError("must not load target")
        with patch.object(
            analyze_run.seal,
            "check_analysis_authorization",
            side_effect=analyze_run.seal.SealError("not authorized"),
        ) as authorization, patch.object(
            analyze_run,
            "_load_audit_after_authorization",
            side_effect=sentinel,
        ) as audit_loader, patch.object(
            analyze_run,
            "_load_authorized_endpoint_rows",
            side_effect=sentinel,
        ) as outcome_loader:
            with self.assertRaisesRegex(
                analyze_run.AuthorizedAnalysisError, "authorization check failed"
            ):
                analyze_run.run_authorized_analysis(
                    analysis_authorization_path=Path("missing-analysis-auth"),
                    unseal_receipt_path=Path("missing-unseal"),
                    structural_audit_receipt_path=Path("missing-audit"),
                    human_reliability_receipt_path=Path("missing-human"),
                    plan_dir=Path("missing-plan"),
                    artifact_root=Path("missing-root"),
                    volume_id="volume",
                    target_run_id=RUN_ID,
                    analysis_run_id="analysis-run",
                )
        authorization.assert_called_once()
        audit_loader.assert_not_called()
        outcome_loader.assert_not_called()

    def test_authorization_audit_identity_mismatch_precedes_target_loader(self) -> None:
        root = Path("/authorized-root")
        authorization = {
            "status": "authorized",
            "plan_hash": "1" * 64,
            "receipt_sha256": "2" * 64,
            "manifest_sha256": "3" * 64,
            "common_eligible_prefixes": 2,
        }
        audit = {
            "plan": {"plan_hash": "4" * 64, "volume_id": "volume"},
            "common_eligible": {"count": 2},
        }
        with patch.object(
            analyze_run.seal,
            "check_analysis_authorization",
            return_value=authorization,
        ), patch.object(
            analyze_run.paths,
            "require_external_artifact_root",
            return_value=root,
        ), patch.object(
            analyze_run,
            "_load_audit_after_authorization",
            return_value=(audit, {}),
        ), patch.object(
            analyze_run,
            "_load_authorized_endpoint_rows",
            side_effect=RuntimeError("must not load target"),
        ) as outcome_loader:
            with self.assertRaisesRegex(
                analyze_run.AuthorizedAnalysisError,
                "authorization plan/run/volume binding differs",
            ):
                analyze_run.run_authorized_analysis(
                    analysis_authorization_path=Path("analysis-auth"),
                    unseal_receipt_path=Path("unseal"),
                    structural_audit_receipt_path=Path("audit"),
                    human_reliability_receipt_path=Path("human"),
                    plan_dir=Path("plan"),
                    artifact_root=root,
                    volume_id="volume",
                    target_run_id=RUN_ID,
                    analysis_run_id="analysis-run",
                )
        outcome_loader.assert_not_called()

    def test_path_escape_and_symlink_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            outside = root.parent / f"{root.name}-outside"
            outside.mkdir(exist_ok=True)
            try:
                with self.assertRaises(Exception):
                    analyze_run._resolved_beneath(
                        root, "../escape", label="target run"
                    )
                link = root / "linked-run"
                link.symlink_to(outside, target_is_directory=True)
                with self.assertRaisesRegex(
                    analyze_run.AuthorizedAnalysisError, "symlink"
                ):
                    analyze_run._resolved_beneath(
                        root, "linked-run", label="target run"
                    )
            finally:
                outside.rmdir()

    def test_incomplete_target_block_manifest_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            run = Path(temporary)
            blocks = run / "blocks"
            block = blocks / f"{'a' * 24}-attempt-0"
            block.mkdir(parents=True)
            with self.assertRaises(Exception):
                analyze_run._passing_blocks(run, stage="stage2a")

    def test_analysis_code_must_be_in_frozen_source_inventory(self) -> None:
        repo_root = Path(analyze_run.__file__).resolve().parents[2]
        records = []
        for relative in analyze_run.REQUIRED_ANALYSIS_SOURCE_PATHS:
            source = repo_root / relative
            records.append(
                {
                    "path": relative,
                    "bytes": source.stat().st_size,
                    "sha256": analyze_run.sha256_file(source),
                    "outcome_bearing": False,
                }
            )
        with tempfile.TemporaryDirectory() as temporary:
            plan = Path(temporary)
            receipt = {
                "study_id": STUDY_ID,
                "prior_outcome_source_files": [],
                "files": records,
            }
            (plan / "source_files.json").write_text(
                json.dumps(receipt), encoding="utf-8"
            )
            analyze_run._require_analysis_sources_bound(plan)

            receipt["files"] = records[:-1]
            (plan / "source_files.json").write_text(
                json.dumps(receipt), encoding="utf-8"
            )
            with self.assertRaisesRegex(
                analyze_run.AuthorizedAnalysisError,
                "absent or differs from the frozen plan",
            ):
                analyze_run._require_analysis_sources_bound(plan)


if __name__ == "__main__":
    unittest.main()

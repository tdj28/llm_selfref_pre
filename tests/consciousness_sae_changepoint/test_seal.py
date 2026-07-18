"""Synthetic, outcome-free tests for the sealed lifecycle boundary."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from experiments.consciousness_sae_changepoint import paths, seal
from experiments.consciousness_sae_changepoint.judge import (
    BINARY_QUERY_TASK,
    NATURAL_STANCE_TASK,
    human_selection_manifest,
)
from experiments.consciousness_sae_changepoint.judge_prompts import (
    HUMAN_SELECTION_SEED,
)
from experiments.consciousness_sae_changepoint.protocol import (
    MODEL_ID,
    MODEL_REVISION,
    PROTOCOL_VERSION,
    STUDY_ID,
    STUDY_SLUG,
)
from experiments.consciousness_sae_changepoint.storage import (
    RunTransaction,
    sha256_file,
    verify_completed_run,
)


class SealedLifecycleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name) / "external-volume"
        self.root.mkdir()
        self.volume_id = "synthetic-volume-001"
        (self.root / paths.ARTIFACT_VOLUME_SENTINEL).write_text(
            json.dumps(
                {
                    "study_slug": STUDY_SLUG,
                    "volume_id": self.volume_id,
                    "volume_size_gb": 500,
                }
            )
            + "\n",
            encoding="utf-8",
        )
        self.plan_hash = "1" * 64
        self.plan_manifest_hash = "2" * 64
        self.common_ids = [f"{index:024x}" for index in range(152)]
        self.target_runs = {
            role: self._empty_run("confirmatory", f"{role}-run")
            for role in ("prefix_bank", "stage2a", "stage2b")
        }
        self.audit_path, self.audit_receipt, self.audit_verification = (
            self._build_audit("audit-valid")
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _start(self, phase: str, run_id: str) -> RunTransaction:
        return RunTransaction.start(
            phase=phase,
            run_id=run_id,
            artifact_root=self.root,
            expected_volume_id=self.volume_id,
            minimum_free_bytes=1,
            metadata={"study_id": STUDY_ID},
        )

    def _empty_run(self, phase: str, run_id: str) -> Path:
        transaction = self._start(phase, run_id)
        return transaction.complete(metadata={"status": "synthetic"})

    def _gate_bindings(self) -> dict[str, str]:
        return {
            "registration_id": "osf12",
            "registration_receipt_sha256": "3" * 64,
            "pre_prefix_freeze_sha": "4" * 40,
            "pre_prefix_freeze_receipt_sha256": "5" * 64,
            "artifact_receipt_sha256": "6" * 64,
            "calibration_receipt_sha256": "7" * 64,
            "acceptance_receipt_sha256": "8" * 64,
            "vector_inventory_sha256": "9" * 64,
            "prefix_receipt_sha256": "a" * 64,
            "prefix_bank_manifest_sha256": verify_completed_run(
                self.target_runs["prefix_bank"]
            )["manifest_sha256"],
            "prefix_bank_run_id": self.target_runs["prefix_bank"].name,
            "prefix_freeze_sha": "b" * 40,
            "prefix_freeze_receipt_sha256": "c" * 64,
        }

    def _run_binding(self, role: str) -> dict[str, object]:
        run = self.target_runs[role]
        verification = verify_completed_run(run)
        entry: dict[str, object] = {
            "relative_path": f"confirmatory/{run.name}",
            "run_id": run.name,
            "manifest_sha256": verification["manifest_sha256"],
            "file_count": verification["file_count"],
            "payload_bytes": verification["payload_bytes"],
            "passing_prefixes": len(self.common_ids),
            "eligible_prefix_ids_sha256": seal._sha256_json(self.common_ids),
        }
        if role != "prefix_bank":
            entry["source_rows"] = 1
        return entry

    def _audit_payload(self) -> dict[str, object]:
        payload = {
            "schema_version": seal.LIFECYCLE_SCHEMA_VERSION,
            "receipt_kind": "structural_audit",
            "status": "pass",
            "study_id": STUDY_ID,
            "protocol_version": PROTOCOL_VERSION,
            "created_at_utc": "2026-07-13T20:00:00+00:00",
            "structural_only": True,
            "semantic_outcomes_opened": False,
            "plan": {
                "plan_hash": self.plan_hash,
                "plan_manifest_sha256": self.plan_manifest_hash,
                "volume_id": self.volume_id,
                "planned_prefixes": 160,
                "prefix_ids_sha256": "d" * 64,
                "minimum_common_complete_prefixes": 152,
            },
            "gate_bindings": self._gate_bindings(),
            "runs": {
                role: self._run_binding(role)
                for role in ("prefix_bank", "stage2a", "stage2b")
            },
            "common_eligible": {
                "count": len(self.common_ids),
                "minimum_required": 152,
                "prefix_ids": self.common_ids,
                "prefix_ids_sha256": seal._sha256_json(self.common_ids),
            },
        }
        return seal._sign_receipt(payload)

    def _build_audit(
        self, run_id: str
    ) -> tuple[Path, dict[str, object], dict[str, object]]:
        payload = self._audit_payload()
        transaction = self._start("audit", run_id)
        transaction.write_json(seal.STRUCTURAL_AUDIT_FILENAME, payload)
        final = transaction.complete(metadata={"status": "pass"})
        return (
            final / seal.STRUCTURAL_AUDIT_FILENAME,
            payload,
            verify_completed_run(final),
        )

    @staticmethod
    def _rows(task: str, packet_ids: list[str]) -> list[dict[str, object]]:
        if task == NATURAL_STANCE_TASK:
            labels: list[object] = [-1, 0, 1]
        else:
            labels = [False, True]
        return [
            {"packet_id": packet_id, "label": labels[index % len(labels)]}
            for index, packet_id in enumerate(packet_ids)
        ]

    def _write_evidence(
        self,
        transaction: RunTransaction,
        *,
        same_coder: bool = False,
    ) -> list[dict[str, object]]:
        records: list[dict[str, object]] = []

        def write(role: str, payload: object) -> tuple[Path, str]:
            relative = f"evidence/{role}.json"
            path = transaction.write_json(relative, payload)
            digest = sha256_file(path)
            records.append(
                {
                    "role": role,
                    "path": relative,
                    "bytes": path.stat().st_size,
                    "sha256": digest,
                }
            )
            return path, digest

        coder_ids = ("e" * 64, "e" * 64 if same_coder else "f" * 64)
        for task, spec in seal.TASK_SPECS.items():
            packet_ids = [
                f"{task}-packet-{index:03d}" for index in range(spec["sample_size"])
            ]
            selection = human_selection_manifest(
                packet_ids,
                seed=HUMAN_SELECTION_SEED,
                strata_fields=("branch", "position"),
            )
            write(f"{task}_selection", selection)
            coder_hashes: list[str] = []
            for number, coder_id in enumerate(coder_ids, start=1):
                _path, digest = write(
                    f"{task}_coder_{number}",
                    {
                        "schema_version": seal.LIFECYCLE_SCHEMA_VERSION,
                        "study_id": STUDY_ID,
                        "task": task,
                        "coder_id_sha256": coder_id,
                        "condition_blind": True,
                        "coded_independently": True,
                        "human_attestation": seal.HUMAN_ATTESTATION,
                        "completed_at_utc": "2026-07-13T20:01:00+00:00",
                        "rows": self._rows(task, packet_ids),
                    },
                )
                coder_hashes.append(digest)
            write(
                f"{task}_adjudicated",
                {
                    "schema_version": seal.LIFECYCLE_SCHEMA_VERSION,
                    "study_id": STUDY_ID,
                    "task": task,
                    "adjudicator_id_sha256": "0" * 64,
                    "condition_blind": True,
                    "adjudication_required": True,
                    "independent_coder_file_sha256": coder_hashes,
                    "disagreements_preserved": True,
                    "completed_at_utc": "2026-07-13T20:02:00+00:00",
                    "rows": self._rows(task, packet_ids),
                },
            )
            write(
                f"{task}_automated",
                {
                    "schema_version": seal.LIFECYCLE_SCHEMA_VERSION,
                    "study_id": STUDY_ID,
                    "task": task,
                    "model_id": MODEL_ID,
                    "model_revision": MODEL_REVISION,
                    "temperature": 0.0,
                    "rows": self._rows(task, packet_ids),
                },
            )
        return records

    def _build_human(
        self, run_id: str, *, same_coder: bool = False
    ) -> tuple[Path, dict[str, object], dict[str, object]]:
        transaction = self._start("judging", run_id)
        evidence_records = self._write_evidence(transaction, same_coder=same_coder)
        evidence_stub = {"evidence_files": evidence_records}
        if same_coder:
            tasks: dict[str, object] = {}
        else:
            evidence = seal._evidence_records(
                evidence_stub, human_run_dir=transaction.partial_path
            )
            tasks = {
                task: seal._recompute_human_task(task=task, evidence=evidence)[0]
                for task in seal.TASK_SPECS
            }
        payload = seal._sign_receipt(
            {
                "schema_version": seal.LIFECYCLE_SCHEMA_VERSION,
                "receipt_kind": "human_reliability",
                "status": "pass",
                "study_id": STUDY_ID,
                "protocol_version": PROTOCOL_VERSION,
                "created_at_utc": "2026-07-13T20:03:00+00:00",
                "plan_hash": self.plan_hash,
                "audit_receipt_file_sha256": sha256_file(self.audit_path),
                "audit_receipt_embedded_sha256": self.audit_receipt[
                    "receipt_sha256"
                ],
                "audit_run_manifest_sha256": self.audit_verification[
                    "manifest_sha256"
                ],
                "human_coders_required": 2,
                "condition_blind": True,
                "adjudication_required": True,
                "evidence_files": evidence_records,
                "tasks": tasks,
            }
        )
        transaction.write_json(seal.HUMAN_RELIABILITY_FILENAME, payload)
        final = transaction.complete(metadata={"status": "pass"})
        return (
            final / seal.HUMAN_RELIABILITY_FILENAME,
            payload,
            verify_completed_run(final),
        )

    def test_structural_receipt_rejects_common_set_forgery(self) -> None:
        valid = dict(self.audit_receipt)
        seal._validate_structural_audit_receipt(valid)
        forged = json.loads(json.dumps(valid))
        forged["common_eligible"]["prefix_ids"] = forged["common_eligible"][
            "prefix_ids"
        ][:-1]
        forged["receipt_sha256"] = seal._embedded_receipt_sha256(forged)
        with self.assertRaisesRegex(seal.SealError, "common eligible"):
            seal._validate_structural_audit_receipt(forged)

    def test_whole_block_retry_policy_rejects_retry_after_pass(self) -> None:
        transaction = self._start("attempt-fixture", "attempt-fixture-run")
        prefix_id = self.common_ids[0]
        blocks = []
        for attempt in (0, 1):
            block = transaction.begin_block(f"{prefix_id}-attempt-{attempt}")
            final = block.complete(
                metadata={
                    "prefix_id": prefix_id,
                    "stage": "stage2a",
                    "attempt": attempt,
                    "status": "pass",
                }
            )
            blocks.append(final)
        with self.assertRaisesRegex(seal.SealError, "retried a passing"):
            seal._attempts_by_prefix(
                blocks=blocks, plan_prefix_ids=[prefix_id], stage="stage2a"
            )

    def test_passing_block_without_shards_fails_structural_audit(self) -> None:
        transaction = self._start("shard-fixture", "shard-fixture-run")
        block = transaction.begin_block("synthetic-block")
        final = block.complete(metadata={"status": "pass"})
        with self.assertRaisesRegex(seal.SealError, "inventory is missing"):
            seal._validate_source_shards(
                block=final,
                plan_hash=self.plan_hash,
                run_id="run",
                block_id="synthetic-block",
                prefix_id=self.common_ids[0],
                stage="stage2a",
                artifact_receipt_sha256="1" * 64,
                calibration_receipt_sha256="2" * 64,
                acceptance_receipt_sha256="3" * 64,
            )

    def test_human_gate_recomputes_two_coder_evidence(self) -> None:
        human_path, human, _verification = self._build_human("human-valid")
        result = seal.validate_human_reliability_receipt(
            human, human_run_dir=human_path.parent
        )
        self.assertEqual(result["coder_ids_sha256"], ["e" * 64, "f" * 64])
        self.assertEqual(
            {task: row["gate"]["status"] for task, row in result["tasks"].items()},
            {NATURAL_STANCE_TASK: "pass", BINARY_QUERY_TASK: "pass"},
        )

    def test_claimed_pass_cannot_replace_two_distinct_humans(self) -> None:
        human_path, human, _verification = self._build_human(
            "human-forged", same_coder=True
        )
        with self.assertRaisesRegex(seal.SealError, "two distinct"):
            seal.validate_human_reliability_receipt(
                human, human_run_dir=human_path.parent
            )

    def test_unseal_and_analysis_require_the_complete_hash_chain(self) -> None:
        human_path, _human, _human_verification = self._build_human("human-chain")
        unseal_result = seal.create_unseal_authorization(
            structural_audit_receipt_path=self.audit_path,
            human_reliability_receipt_path=human_path,
            artifact_root=self.root,
            volume_id=self.volume_id,
            run_id="unseal-chain",
        )
        unseal_path = self.root / "unseal" / "unseal-chain" / seal.UNSEAL_FILENAME
        authorization_result = seal.create_analysis_authorization(
            unseal_receipt_path=unseal_path,
            structural_audit_receipt_path=self.audit_path,
            human_reliability_receipt_path=human_path,
            artifact_root=self.root,
            volume_id=self.volume_id,
            run_id="analysis-chain",
        )
        authorization_path = (
            self.root
            / "analysis-authorization"
            / "analysis-chain"
            / seal.ANALYSIS_AUTHORIZATION_FILENAME
        )
        checked = seal.check_analysis_authorization(
            analysis_authorization_path=authorization_path,
            unseal_receipt_path=unseal_path,
            structural_audit_receipt_path=self.audit_path,
            human_reliability_receipt_path=human_path,
        )
        self.assertEqual(unseal_result["status"], "authorized")
        self.assertEqual(authorization_result["status"], "authorized")
        self.assertEqual(checked["status"], "authorized")
        self.assertEqual(checked["common_eligible_prefixes"], 152)

        substitute_path, _payload, _verification = self._build_audit("audit-substitute")
        with self.assertRaisesRegex(seal.SealError, "exact audit"):
            seal.check_analysis_authorization(
                analysis_authorization_path=authorization_path,
                unseal_receipt_path=unseal_path,
                structural_audit_receipt_path=substitute_path,
                human_reliability_receipt_path=human_path,
            )

    def test_unseal_refuses_unsealed_or_missing_audit(self) -> None:
        human_path, _human, _verification = self._build_human("human-no-audit")
        with self.assertRaises(FileNotFoundError):
            seal.create_unseal_authorization(
                structural_audit_receipt_path=self.root / "missing-audit.json",
                human_reliability_receipt_path=human_path,
                artifact_root=self.root,
                volume_id=self.volume_id,
                run_id="must-not-exist",
            )
        self.assertFalse((self.root / "unseal" / "must-not-exist").exists())


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

from experiments.consciousness_sae_realization_validation import controls
from experiments.consciousness_sae_realization_validation import preexecution
from experiments.consciousness_sae_realization_validation import protocol
from experiments.consciousness_sae_realization_validation import review_adjudication
from experiments.consciousness_sae_realization_validation import runner
from experiments.consciousness_sae_realization_validation import smoke_test


def _run(root: Path, *args: str) -> str:
    result = subprocess.run(
        [*args], cwd=root, text=True, capture_output=True, check=True
    )
    return result.stdout.strip()


class PreexecutionFixture:
    def __init__(self, base: Path) -> None:
        self.root = base.resolve()
        self.plan_dir = self.root / "data" / "plan"
        self.plan_dir.mkdir(parents=True)
        (self.root / "src").mkdir()
        (self.root / "reviews").mkdir()
        self.source_path = self.root / "src" / "runner.py"
        self.source_path.write_text("FROZEN = True\n", encoding="utf-8")
        source = {
            "study_id": protocol.STUDY_ID,
            "protocol_version": protocol.PROTOCOL_VERSION,
            "files": [
                {
                    "path": "src/runner.py",
                    "bytes": self.source_path.stat().st_size,
                    "sha256": protocol.sha256_file(self.source_path),
                    "outcome_bearing": False,
                    "reuse_kind": "current_study_source",
                }
            ],
            "prior_outcome_inputs": [],
        }
        (self.plan_dir / "source_files.json").write_bytes(
            controls.canonical_json_bytes(source) + b"\n"
        )
        for name in preexecution.PLAN_FILES - {"source_files.json"}:
            (self.plan_dir / name).write_text("{}\n", encoding="utf-8")
        rows = [
            {
                "path": name,
                "bytes": (self.plan_dir / name).stat().st_size,
                "sha256": protocol.sha256_file(self.plan_dir / name),
            }
            for name in sorted(preexecution.PLAN_FILES)
        ]
        core = {
            "schema_version": protocol.PLAN_SCHEMA_VERSION,
            "study_id": protocol.STUDY_ID,
            "protocol_version": protocol.PROTOCOL_VERSION,
            "scope": "realization_and_target_free_vector_validation_only",
            "paper_prompt_render_count": 0,
            "behavioral_replication_included": False,
            "stage_a_signed_edit_forward_count": 2304,
            "stage_b_edit_forward_count": 2160,
            "files": rows,
            "prior_outcome_inputs": [],
        }
        self.plan = {**core, "plan_manifest_sha256": controls.canonical_sha256(core)}
        (self.plan_dir / "plan_manifest.json").write_bytes(
            controls.canonical_json_bytes(self.plan) + b"\n"
        )
        self.review = {
            "receipt_path": "reviews/closure.json",
            "receipt_sha256": "a" * 64,
            "status": "adjudicated_pass",
            "review_model": "gpt-5.6-sol",
            "review_reasoning": {"mode": "pro", "effort": "xhigh"},
        }
        (self.root / "reviews" / "closure.json").write_bytes(
            controls.canonical_json_bytes(self.review) + b"\n"
        )
        self.ownership = {
            "receipt_sha256": "b" * 64,
            "pod_id": "pod-test",
            "pod_name": "experiment-test",
            "ownership_nonce": "nonce-test",
            "network_volume_id": "qf2lwehl89",
            "data_center_id": "US-NE-1",
            "gpu_type": "NVIDIA B200",
            "gpu_count": 1,
            "created_at": "2030-01-01T00:00:00Z",
            "terminate_after": "2030-01-01T06:00:00Z",
        }
        self.guest = {"receipt_sha256": "c" * 64}
        self.cache = {"receipt_sha256": "d" * 64}
        _run(self.root, "git", "init", "-q")
        _run(self.root, "git", "config", "user.name", "Test")
        _run(self.root, "git", "config", "user.email", "test@example.com")
        _run(self.root, "git", "add", ".")
        _run(self.root, "git", "commit", "-qm", "freeze")
        self.remote = self.root / "_origin.git"
        _run(self.root, "git", "init", "--bare", "-q", str(self.remote))
        _run(self.root, "git", "remote", "add", "origin", str(self.remote))
        _run(self.root, "git", "push", "-qu", "origin", "HEAD:main")

    def patches(self):
        return (
            mock.patch.object(
                review_adjudication,
                "validate_review_evidence_receipt",
                return_value=self.review,
            ),
            mock.patch.object(
                review_adjudication,
                "review_evidence_bound_paths",
                return_value={"reviews/closure.json"},
            ),
            mock.patch.object(
                preexecution.runpod_preflight,
                "validate_ownership_receipt",
                side_effect=lambda value: dict(value),
            ),
            mock.patch.object(
                preexecution.runpod_preflight,
                "validate_guest_receipt",
                side_effect=lambda value, **_: dict(value),
            ),
            mock.patch.object(
                preexecution.runpod_preflight,
                "validate_cache_receipt",
                side_effect=lambda value, **_: dict(value),
            ),
        )

    def build(self) -> dict:
        patches = self.patches()
        with patches[0], patches[1], patches[2], patches[3], patches[4]:
            return preexecution.build_authorization(
                repo_root=self.root,
                plan_dir=self.plan_dir,
                review_receipt=self.review,
                ownership_receipt=self.ownership,
                guest_receipt=self.guest,
                cache_receipt=self.cache,
                remote_ref="origin/main",
                now=datetime(2030, 1, 1, 1, tzinfo=timezone.utc),
            )


class PreexecutionAuthorizationTests(unittest.TestCase):
    def test_machine_producer_binds_freeze_review_chain_and_campaign(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            fixture = PreexecutionFixture(Path(directory))
            receipt = fixture.build()
            self.assertEqual(receipt["status"], "authorized")
            self.assertEqual(
                receipt["plan_manifest_sha256"],
                fixture.plan["plan_manifest_sha256"],
            )
            self.assertEqual(receipt["review_adjudication_sha256"], "a" * 64)
            self.assertEqual(receipt["review_status"], "adjudicated_pass")
            self.assertEqual(receipt["ownership_receipt_sha256"], "b" * 64)
            self.assertEqual(receipt["guest_receipt_sha256"], "c" * 64)
            self.assertEqual(receipt["cache_receipt_sha256"], "d" * 64)
            self.assertEqual(receipt["git_head_commit"], receipt["git_remote_commit"])
            self.assertEqual(
                receipt["git_head_commit"], receipt["git_live_remote_commit"]
            )
            self.assertEqual(
                receipt["git_live_remote_branch_ref"], "refs/heads/main"
            )
            self.assertEqual(receipt["maximum_campaign_seconds"], 21600)
            self.assertEqual(receipt["prior_outcome_inputs"], [])
            patches = fixture.patches()
            with patches[0], patches[1]:
                allowed = preexecution.deployment_allowlist(
                    repo_root=fixture.root,
                    plan_dir=fixture.plan_dir,
                    review_receipt=fixture.review,
                )
            self.assertEqual(receipt["guest_deployment_file_count"], len(allowed))
            self.assertEqual(
                receipt["guest_deployment_path_set_sha256"],
                controls.canonical_sha256(list(allowed)),
            )
            self.assertIs(receipt["prior_result_files_permitted"], False)

    def test_incomplete_advisory_attempt_can_enter_same_operational_chain(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            fixture = PreexecutionFixture(Path(directory))
            fixture.review["status"] = "attempted_incomplete"
            (fixture.root / "reviews" / "closure.json").write_bytes(
                controls.canonical_json_bytes(fixture.review) + b"\n"
            )
            _run(fixture.root, "git", "add", "reviews/closure.json")
            _run(fixture.root, "git", "commit", "-qm", "bind failed advisory")
            _run(fixture.root, "git", "push", "-q", "origin", "HEAD:main")
            receipt = fixture.build()
            self.assertEqual(receipt["review_status"], "attempted_incomplete")
            self.assertEqual(receipt["model_forward_count"], 0)

    def test_validator_reproduces_all_evidence_and_rejects_chain_swap(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            fixture = PreexecutionFixture(Path(directory))
            receipt = fixture.build()
            patches = fixture.patches()
            with patches[0], patches[1], patches[2], patches[3], patches[4]:
                valid = preexecution.validate_authorization(
                    receipt,
                    repo_root=fixture.root,
                    plan_dir=fixture.plan_dir,
                    ownership_receipt=fixture.ownership,
                    guest_receipt=fixture.guest,
                    cache_receipt=fixture.cache,
                )
                self.assertEqual(valid, receipt)
                swapped = dict(fixture.cache)
                swapped["receipt_sha256"] = "e" * 64
                with self.assertRaisesRegex(
                    preexecution.PreexecutionError, "does not reproduce"
                ):
                    preexecution.validate_authorization(
                        receipt,
                        repo_root=fixture.root,
                        plan_dir=fixture.plan_dir,
                        ownership_receipt=fixture.ownership,
                        guest_receipt=fixture.guest,
                        cache_receipt=swapped,
                    )

    def test_gitless_archive_rehashes_every_binding_without_git_commands(self) -> None:
        with tempfile.TemporaryDirectory() as directory, tempfile.TemporaryDirectory() as archive_dir:
            fixture = PreexecutionFixture(Path(directory))
            receipt = fixture.build()
            archive = Path(archive_dir) / "pilot_repo"
            archive.mkdir()
            allowed = {
                "src/runner.py",
                "reviews/closure.json",
                "data/plan/plan_manifest.json",
                *(f"data/plan/{name}" for name in preexecution.PLAN_FILES),
            }
            for relative in allowed:
                source = fixture.root / relative
                destination = archive / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, destination)
            self.assertFalse((archive / ".git").exists())
            patches = fixture.patches()
            with patches[0], patches[1], patches[2], patches[3], patches[4], mock.patch.object(
                preexecution, "_git", side_effect=AssertionError("git must not run on guest")
            ):
                validated = preexecution.validate_execution_authorization(
                    receipt,
                    repo_root=archive,
                    plan_dir=archive / "data" / "plan",
                    ownership_receipt=fixture.ownership,
                    guest_receipt=fixture.guest,
                    cache_receipt=fixture.cache,
                )
            self.assertEqual(validated["git_head_commit"], validated["git_remote_commit"])

            prior = archive / "data" / "prior_run" / "outcome.json"
            prior.parent.mkdir(parents=True)
            prior.write_text('{"old_result": true}\n', encoding="utf-8")
            patches = fixture.patches()
            with patches[0], patches[1], patches[2], patches[3], patches[4], self.assertRaisesRegex(
                preexecution.PreexecutionError, "outcome-free allowlist"
            ):
                preexecution.validate_execution_authorization(
                    receipt,
                    repo_root=archive,
                    plan_dir=archive / "data" / "plan",
                    ownership_receipt=fixture.ownership,
                    guest_receipt=fixture.guest,
                    cache_receipt=fixture.cache,
                )

    def test_dirty_bound_source_is_stop_ship(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            fixture = PreexecutionFixture(Path(directory))
            fixture.source_path.write_text("FROZEN = False\n", encoding="utf-8")
            with self.assertRaises(preexecution.PreexecutionError):
                fixture.build()

    def test_remote_commit_mismatch_is_stop_ship(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            fixture = PreexecutionFixture(Path(directory))
            _run(fixture.root, "git", "commit", "--allow-empty", "-qm", "ahead")
            with self.assertRaisesRegex(
                preexecution.PreexecutionError, "exact live pushed remote freeze"
            ):
                fixture.build()

    def test_locally_forged_tracking_ref_cannot_substitute_for_live_origin(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            fixture = PreexecutionFixture(Path(directory))
            _run(fixture.root, "git", "commit", "--allow-empty", "-qm", "local-only")
            _run(
                fixture.root,
                "git",
                "update-ref",
                "refs/remotes/origin/main",
                "HEAD",
            )
            with self.assertRaisesRegex(
                preexecution.PreexecutionError, "exact live pushed remote freeze"
            ):
                fixture.build()

    def test_hand_authored_minimal_pass_token_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            fixture = PreexecutionFixture(Path(directory))
            core = {
                "status": "authorized",
                "study_id": protocol.STUDY_ID,
                "protocol_version": protocol.PROTOCOL_VERSION,
            }
            fake = {**core, "receipt_sha256": controls.canonical_sha256(core)}
            with self.assertRaisesRegex(preexecution.PreexecutionError, "schema"):
                preexecution.validate_authorization(
                    fake,
                    repo_root=fixture.root,
                    plan_dir=fixture.plan_dir,
                    ownership_receipt=fixture.ownership,
                    guest_receipt=fixture.guest,
                    cache_receipt=fixture.cache,
                )

    def test_stage_b_rejects_authorization_from_another_campaign(self) -> None:
        stage_a = {
            "preexecution_authorization_sha256": "a" * 64,
            "campaign_identity_sha256": "b" * 64,
        }
        substituted = {
            "receipt_sha256": "c" * 64,
            "campaign_identity_sha256": "d" * 64,
            "plan_manifest_sha256": "e" * 64,
            "network_volume_id": "volume-1",
            "campaign_started_at_unix": 1000.0,
            "provider_terminate_at_unix": 22600.0,
        }
        with mock.patch.object(
            preexecution,
            "load_execution_authorization",
            return_value=substituted,
        ), self.assertRaisesRegex(
            runner.ExecutionError, "differs from Stage A or current campaign"
        ):
            runner._validate_stage_b_authorization(
                plan_dir=Path("unused"),
                plan_hash="e" * 64,
                volume_id="volume-1",
                preexecution_authorization_path=Path("authorization.json"),
                stage_a_receipt=stage_a,
                ownership={"receipt_sha256": "1" * 64},
                guest={"receipt_sha256": "2" * 64},
                cache={"receipt_sha256": "3" * 64},
                campaign_started_at_unix=1000.0,
                provider_terminate_at_unix=22600.0,
            )

    def test_cli_requires_review_git_provider_chain_and_output(self) -> None:
        required = {
            option
            for action in preexecution.build_parser()._actions
            if action.required
            for option in action.option_strings
            if option.startswith("--")
        }
        self.assertEqual(
            required,
            {
                "--plan-dir",
                "--review-adjudication",
                "--ownership-receipt",
                "--guest-receipt",
                "--cache-receipt",
                "--remote-ref",
                "--output",
            },
        )

    def test_stage_a_joins_exact_external_smoke_path_and_campaign(self) -> None:
        with tempfile.TemporaryDirectory(dir=runner.REPO_ROOT) as directory:
            root = Path(directory)
            volume_id = "qf2lwehl89"
            sentinel = {
                "schema_version": controls.CONTROL_SCHEMA_VERSION,
                "study_slug": protocol.STUDY_SLUG,
                "study_id": protocol.STUDY_ID,
                "protocol_version": protocol.PROTOCOL_VERSION,
                "volume_id": volume_id,
                "purpose": controls.VOLUME_PURPOSE,
            }
            (root / controls.VOLUME_SENTINEL).write_bytes(
                controls.canonical_json_bytes(sentinel) + b"\n"
            )
            relative = (
                f"{protocol.STUDY_SLUG}/{protocol.STUDY_ID}/"
                "operational_smoke_receipts/smoke-1.json"
            )
            smoke_path = root / relative
            smoke_path.parent.mkdir(parents=True)
            smoke = {
                "run_id": "smoke-1",
                "receipt_sha256": "1" * 64,
                "external_receipt_relative_path": relative,
                "completed_at_unix": 1100.0,
            }
            smoke_path.write_bytes(controls.canonical_json_bytes(smoke) + b"\n")
            authorization = {
                "receipt_sha256": "2" * 64,
                "network_volume_id": volume_id,
                "plan_manifest_sha256": "3" * 64,
                "campaign_started_at_unix": 1000.0,
                "provider_terminate_at_unix": 22600.0,
            }
            with (
                mock.patch.object(
                    preexecution,
                    "load_execution_authorization",
                    return_value=authorization,
                ),
                mock.patch.object(
                    smoke_test, "validate_smoke_receipt", return_value=smoke
                ),
                mock.patch.object(runner.time, "time", return_value=1200.0),
            ):
                auth, validated_smoke, file_hash = runner._validate_stage_a_stopship_chain(
                    plan_dir=Path("unused"),
                    plan_hash="3" * 64,
                    volume_root=root,
                    run_id="stage-a-1",
                    preexecution_authorization_path=Path("authorization.json"),
                    smoke_receipt_path=smoke_path,
                    ownership={},
                    guest={},
                    cache={},
                    campaign_started_at_unix=1000.0,
                    provider_terminate_at_unix=22600.0,
                )
            self.assertEqual(auth, authorization)
            self.assertEqual(validated_smoke, smoke)
            self.assertEqual(file_hash, protocol.sha256_file(smoke_path))

            copied = root / "copied-smoke.json"
            copied.write_bytes(smoke_path.read_bytes())
            with (
                mock.patch.object(
                    preexecution,
                    "load_execution_authorization",
                    return_value=authorization,
                ),
                mock.patch.object(
                    smoke_test, "validate_smoke_receipt", return_value=smoke
                ),
            ):
                with self.assertRaisesRegex(runner.ExecutionError, "exact external path"):
                    runner._validate_stage_a_stopship_chain(
                        plan_dir=Path("unused"),
                        plan_hash="3" * 64,
                        volume_root=root,
                        run_id="stage-a-1",
                        preexecution_authorization_path=Path("authorization.json"),
                        smoke_receipt_path=copied,
                        ownership={},
                        guest={},
                        cache={},
                        campaign_started_at_unix=1000.0,
                        provider_terminate_at_unix=22600.0,
                    )

            linked = root / "linked-smoke.json"
            linked.symlink_to(smoke_path)
            with mock.patch.object(
                preexecution,
                "load_execution_authorization",
                return_value=authorization,
            ), self.assertRaisesRegex(runner.ExecutionError, "single-link"):
                runner._validate_stage_a_stopship_chain(
                    plan_dir=Path("unused"),
                    plan_hash="3" * 64,
                    volume_root=root,
                    run_id="stage-a-1",
                    preexecution_authorization_path=Path("authorization.json"),
                    smoke_receipt_path=linked,
                    ownership={},
                    guest={},
                    cache={},
                    campaign_started_at_unix=1000.0,
                    provider_terminate_at_unix=22600.0,
                )


if __name__ == "__main__":
    unittest.main()

"""Forgery-oriented tests for target-blind gate validators."""

from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from experiments.consciousness_sae_changepoint import gate_validators as gates
from experiments.consciousness_sae_changepoint.protocol import (
    MAIN_BRANCHES,
    PROTOCOL_VERSION,
    STUDY_ID,
    canonical_json_bytes,
)
from experiments.consciousness_sae_changepoint.run import (
    GateValidationContext,
    GateValidationError,
    REQUIRED_TARGET_BLIND_GATES,
    default_gate_validator_registry,
    embedded_receipt_sha256,
    paired_rng_context_sha256,
)
from experiments.consciousness_sae_changepoint.storage import sha256_file


PLAN_HASH = "1" * 64
ARTIFACT_HASH = "2" * 64
CALIBRATION_HASH = "3" * 64


def signed(payload: dict[str, object]) -> dict[str, object]:
    result = copy.deepcopy(payload)
    result.pop("receipt_sha256", None)
    result["receipt_sha256"] = embedded_receipt_sha256(result)
    return result


def child(gate_id: str, evidence: object, *, source: object = None) -> dict[str, object]:
    payload: dict[str, object] = {
        "gate_schema_version": 1,
        "gate_id": gate_id,
        "validator_id": gates.VALIDATOR_IDS[gate_id],
        "status": "pass",
        "study_id": STUDY_ID,
        "protocol_version": PROTOCOL_VERSION,
        "outcome_blind": True,
        "target_outcomes_opened": False,
        "prior_outcome_inputs": [],
        "plan_hash": PLAN_HASH,
        "artifact_receipt_sha256": ARTIFACT_HASH,
        "calibration_receipt_sha256": CALIBRATION_HASH,
        "created_at_utc": "2026-07-14T01:00:00+00:00",
        "evidence": evidence,
    }
    if source is not None:
        payload["source"] = source
    return signed(payload)


class GateValidatorRegistryTests(unittest.TestCase):
    def test_registry_covers_every_unsupported_gate_exactly(self) -> None:
        registry = gates.gate_validator_registry()
        observed = {gate_id for gate_id, _validator_id in registry}
        self.assertEqual(
            observed,
            set(REQUIRED_TARGET_BLIND_GATES) - {"intervention_vector_inventory"},
        )
        self.assertEqual(len(registry), 13)

    def test_runtime_default_registry_covers_all_required_gates(self) -> None:
        registry = default_gate_validator_registry()
        observed = {gate_id for gate_id, _validator_id in registry}
        self.assertEqual(observed, set(REQUIRED_TARGET_BLIND_GATES))
        self.assertEqual(len(registry), 14)


class SealedSourceBindingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name).resolve()
        self.container = self.root / "benchmark" / "source-run"
        self.container.mkdir(parents=True)
        self.source = signed({"kind": "fixture", "value": 17})
        self.receipt_path = self.container / "source_receipt.json"
        self.receipt_path.write_bytes(canonical_json_bytes(self.source) + b"\n")
        file_record = {
            "path": self.receipt_path.name,
            "role": "shard_receipt",
            "bytes": self.receipt_path.stat().st_size,
            "sha256": sha256_file(self.receipt_path),
        }
        manifest = {
            "archive_schema_version": 1,
            "kind": "run",
            "phase": "benchmark",
            "run_id": "source-run",
            "metadata": {},
            "blocks": [],
            "files": [file_record],
        }
        manifest_path = self.container / "REMOTE_MANIFEST.json"
        manifest_path.write_bytes(canonical_json_bytes(manifest) + b"\n")
        complete = {
            "archive_schema_version": 1,
            "kind": "run",
            "status": "complete",
            "phase": "benchmark",
            "run_id": "source-run",
            "manifest_sha256": sha256_file(manifest_path),
            "file_count": 1,
            "payload_bytes": self.receipt_path.stat().st_size,
        }
        (self.container / "COMPLETE.json").write_bytes(
            canonical_json_bytes(complete) + b"\n"
        )
        self.binding = {
            "schema_version": 1,
            "receipt_relative_path": "benchmark/source-run/source_receipt.json",
            "container_relative_path": "benchmark/source-run",
            "container_kind": "completed_run",
            "bytes": self.receipt_path.stat().st_size,
            "file_sha256": sha256_file(self.receipt_path),
            "embedded_sha256": self.source["receipt_sha256"],
            "manifest_sha256": sha256_file(manifest_path),
        }
        self.context = GateValidationContext(
            plan_hash=PLAN_HASH,
            artifact_receipt_sha256=ARTIFACT_HASH,
            calibration_receipt_sha256=CALIBRATION_HASH,
            artifact_root=self.root,
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_completed_source_is_reopened_and_rehashed(self) -> None:
        observed, sealed, path = gates.open_bound_source_receipt(
            self.binding, self.context
        )
        self.assertEqual(observed, self.source)
        self.assertEqual(sealed["status"], "verified")
        self.assertEqual(path, self.receipt_path)

    def test_re_signed_source_tamper_still_breaks_completed_manifest(self) -> None:
        forged = signed({"kind": "fixture", "value": 999})
        self.receipt_path.write_bytes(canonical_json_bytes(forged) + b"\n")
        forged_binding = dict(self.binding)
        forged_binding.update(
            {
                "bytes": self.receipt_path.stat().st_size,
                "file_sha256": sha256_file(self.receipt_path),
                "embedded_sha256": forged["receipt_sha256"],
            }
        )
        with self.assertRaises(GateValidationError):
            gates.open_bound_source_receipt(forged_binding, self.context)


class NumericGateForgeryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.context = GateValidationContext(
            plan_hash=PLAN_HASH,
            artifact_receipt_sha256=ARTIFACT_HASH,
            calibration_receipt_sha256=CALIBRATION_HASH,
            artifact_root=Path("/tmp"),
        )

    def _validate_with_benchmark_evidence(self, receipt, validator, evidence):
        all_evidence = {
            gate_id: ({"placeholder": gate_id} if gate_id != receipt["gate_id"] else evidence)
            for gate_id in gates.BENCHMARK_EVIDENCE_GATES
        }
        with patch.object(
            gates,
            "_validated_benchmark_source",
            return_value=({}, all_evidence),
        ):
            return validator(receipt, self.context)

    def test_composite_semantic_control_uses_embedded_shared_bindings(self) -> None:
        analysis = {"status": "pass", "endpoint_sensitivity_control_passed": True}
        source = {
            "schema_version": "consciousness_sae_control_composite_v1",
            "outcome_blind": True,
            "target_outcomes_opened": False,
            "prior_outcome_inputs": ["8" * 64, "9" * 64],
            "artifact_receipt_embedded_sha256": ARTIFACT_HASH,
            "calibration_receipt_embedded_sha256": CALIBRATION_HASH,
            "receipt_sha256": "a" * 64,
            "analysis": analysis,
            "selected_feature_ids": [3415, 4042, 4752],
            "source_file_sha256": "b" * 64,
        }
        evidence = {
            "validated_receipt_sha256": source["receipt_sha256"],
            "analysis_sha256": gates._sha256_json(analysis),
            "selected_feature_ids": source["selected_feature_ids"],
            "executor_source_sha256": source["source_file_sha256"],
        }
        receipt = child("semantic_positive_control", evidence, source={})
        composite = Mock()
        composite.validate_control_receipt.return_value = {
            "status": "pass",
            "passed": True,
        }
        with patch.object(
            gates,
            "open_bound_source_receipt",
            return_value=(source, {}, Path("/sealed/composite.json")),
        ), patch.object(gates.importlib, "import_module", return_value=composite):
            result = gates.validate_semantic_positive_control_gate(
                receipt, self.context
            )
        self.assertTrue(result["passed"])
        composite.validate_control_receipt.assert_called_once_with(
            source, artifact_root=self.context.artifact_root
        )

        forged = dict(source)
        forged["artifact_receipt_embedded_sha256"] = "f" * 64
        with patch.object(
            gates,
            "open_bound_source_receipt",
            return_value=(forged, {}, Path("/sealed/composite.json")),
        ), patch.object(gates.importlib, "import_module", return_value=composite), self.assertRaises(
            GateValidationError
        ):
            gates.validate_semantic_positive_control_gate(receipt, self.context)

    def cached_evidence(self) -> dict[str, object]:
        rows = [
            {
                "fixture_id": f"fixture-{index:02d}",
                "prefix_token_ids_equal": True,
                "cached_logits_sha256": "4" * 64,
                "uncached_logits_sha256": "5" * 64,
                "max_abs_logit_error": 0.01,
                "rmse_logit_error": 0.005,
                "uncached_logit_rms": 1.0,
                "cosine_similarity": 0.999999,
                "top1_token_id_equal": True,
                "repeat_max_abs_logit_error": 0.001,
                "repeat_rmse_logit_error": 0.0005,
            }
            for index in range(8)
        ]
        return {
            "schema_version": 1,
            "gate_id": "cached_clean_equivalence",
            "thresholds": gates.CACHED_EQUIVALENCE_THRESHOLDS,
            "rows": rows,
            "summary": {
                "fixture_count": 8,
                "maximum_relative_max_abs_error": 0.01,
                "maximum_relative_rmse": 0.005,
                "maximum_repeat_relative_max_abs_error": 0.001,
                "maximum_repeat_relative_rmse": 0.0005,
                "minimum_cosine_similarity": 0.999999,
                "all_prefix_token_ids_equal": True,
                "all_top1_token_ids_equal": True,
            },
        }

    def test_cached_gate_recomputes_metrics_instead_of_trusting_summary(self) -> None:
        evidence = self.cached_evidence()
        receipt = child("cached_clean_equivalence", evidence, source={})
        result = self._validate_with_benchmark_evidence(
            receipt, gates.validate_cached_clean_equivalence_gate, evidence
        )
        self.assertEqual(result["fixture_count"], 8)

        forged_evidence = copy.deepcopy(evidence)
        forged_evidence["rows"][0]["max_abs_logit_error"] = 9.0
        # Keep the forged receipt's claimed passing summary and recompute every
        # cryptographic hash an attacker controls. The independent decision must
        # still reject it.
        forged = child("cached_clean_equivalence", forged_evidence, source={})
        with self.assertRaises(GateValidationError):
            self._validate_with_benchmark_evidence(
                forged,
                gates.validate_cached_clean_equivalence_gate,
                forged_evidence,
            )

    def paired_rng_evidence(self) -> dict[str, object]:
        rows: list[dict[str, object]] = []
        for coordinate in range(8):
            context_hash = paired_rng_context_sha256(
                prefix_seed=1000 + coordinate,
                stream_id="main-paired",
                decode_step=coordinate,
            )
            for branch in MAIN_BRANCHES:
                rows.append(
                    {
                        "fixture_id": f"fixture-{coordinate:02d}",
                        "prefix_seed": 1000 + coordinate,
                        "paired_stream_id": "main-paired",
                        "decode_step": coordinate,
                        "branch": branch,
                        "rng_context_sha256": context_hash,
                        "uniform_u64_sha256": f"{coordinate + 5:x}" * 64,
                    }
                )
        return {
            "schema_version": 1,
            "gate_id": "paired_rng",
            "rows": rows,
            "summary": {
                "coordinate_count": 8,
                "row_count": 8 * len(MAIN_BRANCHES),
                "all_branch_uniforms_exactly_paired": True,
            },
        }

    def test_paired_rng_rejects_one_branch_with_a_different_uniform(self) -> None:
        evidence = self.paired_rng_evidence()
        receipt = child("paired_rng", evidence, source={})
        self._validate_with_benchmark_evidence(
            receipt, gates.validate_paired_rng_gate, evidence
        )
        forged_evidence = copy.deepcopy(evidence)
        forged_evidence["rows"][3]["uniform_u64_sha256"] = "f" * 64
        forged = child("paired_rng", forged_evidence, source={})
        with self.assertRaises(GateValidationError):
            self._validate_with_benchmark_evidence(
                forged, gates.validate_paired_rng_gate, forged_evidence
            )

    def test_remaining_low_level_gates_recompute_row_evidence(self) -> None:
        same = "6" * 64
        other = "7" * 64
        fork_rows = [
            {
                "fixture_id": f"fork-{index}",
                "parent_cache_sha256": same,
                "branch_a_initial_cache_sha256": same,
                "branch_b_initial_cache_sha256": same,
                "branch_a_clean_logits_sha256": same,
                "branch_b_clean_logits_sha256": same,
                "branch_a_output_cache_sha256": other,
                "branch_b_output_cache_sha256": other,
            }
            for index in range(8)
        ]
        first_rows = [
            {
                "fixture_id": f"first-{index}",
                "pre_event_distribution_clean_sha256": same,
                "pre_event_distribution_edited_sha256": same,
                "layer50_pre_clean_sha256": same,
                "layer50_pre_edited_sha256": same,
                "layer50_post_clean_sha256": same,
                "layer50_post_edited_sha256": other,
                "z0_clean_distribution_sha256": same,
                "z0_edited_distribution_sha256": other,
                "pre_event_max_abs_difference": 0.0,
                "event_intervention_linf": 0.5,
            }
            for index in range(8)
        ]
        mask_rows = [
            {
                "fixture_id": f"mask-{index}",
                "sequence_positions": 4,
                "selected_positions": 1,
                "expected_mask_sha256": same,
                "observed_mask_sha256": same,
                "hook_call_count": 1,
                "outside_mask_max_abs_delta": 0.0,
                "inside_mask_max_abs_delta": 0.5,
                "active_hook_handles_before": 0,
                "active_hook_handles_after": 0,
            }
            for index in range(8)
        ]
        j_rows = [
            {
                "layer": layer,
                "orientation": "residual @ J_L.T",
                "selected_token_ids_sha256": same,
                "selected_vs_full_max_relative_error": 0.001,
                "identity_vs_direct_max_relative_error": 0.001,
                "positive_direction_margin": 0.5,
                "negative_direction_margin": -0.5,
            }
            for layer in gates.J_MAP_LAYERS
        ]
        order_cases = [
            {
                "fixture_id": f"order-{index}",
                "canonical_order_output_inventory_sha256": same,
                "reversed_order_output_inventory_sha256": same,
                "fresh_output_inventory_sha256": other,
                "resumed_output_inventory_sha256": other,
                "canonical_sampling_inventory_sha256": same,
                "reversed_sampling_inventory_sha256": same,
            }
            for index in range(3)
        ]
        cases = [
            (
                "fork_identity",
                gates.validate_fork_identity_gate,
                {
                    "schema_version": 1,
                    "gate_id": "fork_identity",
                    "rows": fork_rows,
                    "summary": {"fixture_count": 8, "all_exact_identity": True},
                },
                lambda evidence: evidence["rows"][0].__setitem__(
                    "branch_b_initial_cache_sha256", other
                ),
            ),
            (
                "first_affected_distribution",
                gates.validate_first_affected_distribution_gate,
                {
                    "schema_version": 1,
                    "gate_id": "first_affected_distribution",
                    "rows": first_rows,
                    "summary": {
                        "fixture_count": 8,
                        "all_pre_event_exact": True,
                        "first_affected_distribution": "z[0]",
                    },
                },
                lambda evidence: evidence["rows"][0].__setitem__(
                    "pre_event_max_abs_difference", 0.1
                ),
            ),
            (
                "mask_contracts",
                gates.validate_mask_contracts_gate,
                {
                    "schema_version": 1,
                    "gate_id": "mask_contracts",
                    "rows": mask_rows,
                    "summary": {
                        "fixture_count": 8,
                        "all_mask_and_cleanup_contracts_exact": True,
                    },
                },
                lambda evidence: evidence["rows"][0].__setitem__(
                    "outside_mask_max_abs_delta", 0.1
                ),
            ),
            (
                "j_readout_algebra",
                gates.validate_j_readout_algebra_gate,
                {
                    "schema_version": 1,
                    "gate_id": "j_readout_algebra",
                    "thresholds": gates.J_ALGEBRA_THRESHOLDS,
                    "rows": j_rows,
                    "summary": {
                        "layer_count": len(gates.J_MAP_LAYERS),
                        "maximum_selected_vs_full_error": 0.001,
                        "maximum_identity_vs_direct_error": 0.001,
                        "all_orientation_and_sign_checks": True,
                    },
                },
                lambda evidence: evidence["rows"][0].__setitem__(
                    "positive_direction_margin", -0.5
                ),
            ),
            (
                "order_resume_replay",
                gates.validate_order_resume_replay_gate,
                {
                    "schema_version": 1,
                    "gate_id": "order_resume_replay",
                    "cases": order_cases,
                    "summary": {
                        "case_count": 3,
                        "all_order_and_resume_inventories_exact": True,
                    },
                },
                lambda evidence: evidence["cases"][0].__setitem__(
                    "resumed_output_inventory_sha256", same
                ),
            ),
        ]
        for gate_id, validator, evidence, forge in cases:
            with self.subTest(gate_id=gate_id, mode="valid"):
                self._validate_with_benchmark_evidence(
                    child(gate_id, evidence, source={}), validator, evidence
                )
            forged_evidence = copy.deepcopy(evidence)
            forge(forged_evidence)
            with self.subTest(gate_id=gate_id, mode="forged"), self.assertRaises(
                GateValidationError
            ):
                self._validate_with_benchmark_evidence(
                    child(gate_id, forged_evidence, source={}),
                    validator,
                    forged_evidence,
                )

    def test_generic_benchmark_pass_flags_cannot_fill_missing_evidence(self) -> None:
        source = {
            "outcome_blind": True,
            "target_outcomes_opened": False,
            "prior_outcome_inputs": [],
            "plan_hash": PLAN_HASH,
            "artifact_receipt_sha256": ARTIFACT_HASH,
            "calibration_receipt_sha256": CALIBRATION_HASH,
            "artifact_root_binding": {"expected_volume_id": "volume"},
            "technical_gates": {"cached_clean_equivalence": True},
        }
        with patch.object(
            gates,
            "open_bound_source_receipt",
            return_value=(source, {}, Path("/tmp/benchmark_receipt.json")),
        ), patch.object(gates.benchmark, "validate_benchmark_receipt", return_value="a" * 64), patch.object(
            gates, "sha256_file", return_value="b" * 64
        ):
            with self.assertRaisesRegex(
                GateValidationError, "generic pass flags are insufficient"
            ):
                gates._validated_benchmark_source(
                    child("measured_benchmark", {}, source={}), self.context
                )


class FrozenDefinitionForgeryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.context = GateValidationContext(
            plan_hash=PLAN_HASH,
            artifact_receipt_sha256=ARTIFACT_HASH,
            calibration_receipt_sha256=CALIBRATION_HASH,
            artifact_root=Path("/tmp"),
        )

    def test_judge_definition_is_reconstructed_from_source(self) -> None:
        evidence = gates.judge_definition_evidence()
        receipt = child("judge_definition_frozen", evidence)
        gates.validate_judge_definition_frozen_gate(receipt, self.context)
        forged_evidence = copy.deepcopy(evidence)
        forged_evidence["retry_policy"] = "unlimited_retries"
        forged = child("judge_definition_frozen", forged_evidence)
        with self.assertRaises(GateValidationError):
            gates.validate_judge_definition_frozen_gate(forged, self.context)

    def test_review_requires_machine_plan_binding_and_json_adjudication(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            review_dir = root / "docs/consciousness_sae_changepoint/reviews/renewed"
            review_dir.mkdir(parents=True)
            request = review_dir / "request_payload.json"
            review = review_dir / "review.md"
            manifest = review_dir / "review_manifest.json"
            adjudication = review_dir / "adjudication.json"
            plan_audit = review_dir / "plan_audit.json"
            validate_plan = root / "experiments/consciousness_sae_changepoint/validate_plan.py"
            validate_plan.parent.mkdir(parents=True)
            validate_plan.write_text("# frozen test validator\n", encoding="utf-8")
            request.write_text("{}\n", encoding="utf-8")
            review.write_text("# Verdict\nREADY TO FREEZE\n", encoding="utf-8")
            plan_audit_payload = signed(
                {
                    "schema_version": 1,
                    "status": "pass",
                    "study_id": STUDY_ID,
                    "outcome_blind": True,
                    "target_outcomes_opened": False,
                    "prior_outcome_inputs": [],
                    "plan_hash": PLAN_HASH,
                    "plan_manifest_sha256": "a" * 64,
                    "validate_plan_source_sha256": sha256_file(validate_plan),
                    "source_inventory_sha256": "b" * 64,
                    "test_inventory_sha256": "c" * 64,
                    "all_tests_passed": True,
                }
            )
            plan_audit.write_bytes(canonical_json_bytes(plan_audit_payload) + b"\n")
            manifest.write_text(
                json.dumps(
                    {
                        "status": "completed",
                        "model": "gpt-5.6-sol",
                        "reasoning": {"mode": "pro"},
                        "reviewed_machine_plan_hash": PLAN_HASH,
                        "target_outcomes_opened": False,
                        "prior_outcome_inputs": [],
                        "blocking_finding_ids": ["B01"],
                        "review_verdict": "READY TO FREEZE",
                        "review_sha256": sha256_file(review),
                        "request_payload_sha256": sha256_file(request),
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            adjudication_payload = signed(
                    {
                        "schema_version": 1,
                        "status": "complete",
                        "reviewed_machine_plan_hash": PLAN_HASH,
                        "review_manifest_sha256": sha256_file(manifest),
                        "review_sha256": sha256_file(review),
                        "blocking_findings": [
                            {
                                "finding_id": "B01",
                                "decision": "accept",
                                "resolution": "closed",
                                "evidence_sha256": "d" * 64,
                            }
                        ],
                        "remaining_blocking_findings": [],
                        "freeze_recommendation": "pass",
                        "target_outcomes_opened": False,
                        "prior_outcome_inputs": [],
                    }
            )
            adjudication.write_bytes(canonical_json_bytes(adjudication_payload) + b"\n")
            by_role = {
                "request_payload": request,
                "plan_audit": plan_audit,
                "review_manifest": manifest,
                "review": review,
                "adjudication": adjudication,
            }
            records = [
                {
                    "path": path.relative_to(root).as_posix(),
                    "bytes": path.stat().st_size,
                    "sha256": sha256_file(path),
                    "role": role,
                }
                for role, path in by_role.items()
            ]
            evidence = {
                "schema_version": 1,
                "reviewed_plan_hash": PLAN_HASH,
                "model": "gpt-5.6-sol",
                "reasoning_mode": "pro",
                "review_verdict": "READY TO FREEZE",
                "adjudication_status": "complete",
                "remaining_blocking_findings": [],
                "plan_audit_receipt_sha256": plan_audit_payload["receipt_sha256"],
                "source_files": records,
            }
            receipt = child("independent_plan_review", evidence)
            with patch.object(gates, "REPO_ROOT", root):
                gates.validate_independent_plan_review_gate(receipt, self.context)
                forged_evidence = copy.deepcopy(evidence)
                forged_evidence["reviewed_plan_hash"] = "9" * 64
                forged = child("independent_plan_review", forged_evidence)
                with self.assertRaises(GateValidationError):
                    gates.validate_independent_plan_review_gate(forged, self.context)


if __name__ == "__main__":
    unittest.main()

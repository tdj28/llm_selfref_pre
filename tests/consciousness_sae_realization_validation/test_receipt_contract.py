from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from experiments.consciousness_sae_realization_validation import controls
from experiments.consciousness_sae_realization_validation import gate_receipts
from experiments.consciousness_sae_realization_validation import protocol
from experiments.consciousness_sae_realization_validation import runner


def _sealed(core: dict) -> dict:
    return {**core, "receipt_sha256": controls.canonical_sha256(core)}


def _plan_manifest() -> dict:
    core = {
        "schema_version": protocol.PLAN_SCHEMA_VERSION,
        "study_id": protocol.STUDY_ID,
        "protocol_version": protocol.PROTOCOL_VERSION,
        "scope": "realization_and_target_free_vector_validation_only",
        "paper_prompt_render_count": 0,
        "behavioral_replication_included": False,
        "stage_a_signed_edit_forward_count": 2_304,
        "stage_b_edit_forward_count": 2_160,
        "files": [],
        "prior_outcome_inputs": [],
    }
    return {**core, "plan_manifest_sha256": controls.canonical_sha256(core)}


def _raw_stage_a_receipt(*, plan_hash: str, run_id: str) -> dict:
    required_roles = (
        "execution_binding",
        "prompt_receipts",
        "stage_a_raw_residuals",
        "stage_a_exact_arithmetic_vectors",
        "realization_metrics",
        "transport_metrics",
        "linearity_metrics",
        "runtime_metadata",
    )
    core = {
        "status": "complete",
        "stage": "stage_a",
        "study_id": protocol.STUDY_ID,
        "protocol_version": protocol.PROTOCOL_VERSION,
        "run_id": run_id,
        "plan_manifest_sha256": plan_hash,
        "runtime": {"model_forward_count": 2_320},
        "records": [{"role": role} for role in required_roles],
        "prior_outcome_inputs": [],
    }
    return _sealed(core)


def _stage_a_scientific_failure_receipt(
    *, plan_hash: str, raw_hash: str, run_id: str, budget_hash: str
) -> dict:
    gated_rows = (
        len(protocol.STAGE_A_PROMPT_IDS)
        * len(protocol.STAGE_A_DIRECTIONS)
        * len(protocol.LINEARITY_GATE_DOSES)
    )
    j_shadow_layers = [
        {
            "edit_layer": layer,
            "status": "fail" if layer == protocol.STAGE_A_LAYERS[0] else "pass",
            "gated_row_count": gated_rows,
            "failure_count": 1 if layer == protocol.STAGE_A_LAYERS[0] else 0,
        }
        for layer in protocol.STAGE_A_LAYERS
    ]
    core = {
        "schema_version": controls.CONTROL_SCHEMA_VERSION,
        "status": "fail",
        "study_id": protocol.STUDY_ID,
        "protocol_version": protocol.PROTOCOL_VERSION,
        "run_id": run_id,
        "plan_manifest_sha256": plan_hash,
        "raw_run_receipt_sha256": raw_hash,
        "audit_receipt_sha256": "a" * 64,
        "stage_a_numeric_recomputation_sha256": "5" * 64,
        "storage_budget_receipt_sha256": budget_hash,
        "preexecution_authorization_sha256": "1" * 64,
        "smoke_receipt_sha256": "2" * 64,
        "smoke_receipt_file_sha256": "3" * 64,
        "campaign_identity_sha256": "4" * 64,
        "edit_realization_rows_sha256": "c" * 64,
        "transport_rows_sha256": "d" * 64,
        "linearity_rows_sha256": "e" * 64,
        "j_orientation_rows_sha256": "6" * 64,
        "j_orientation_receipt_sha256": "f" * 64,
        "edit_realization_status": "pass",
        "realized_edit_fidelity_status": "pass",
        "hard_safety_status": "pass",
        "native_post_bytes_status": "pass",
        "common_mode_status": "pass",
        "collection_safety_status": "pass",
        "j_shadow_status": "fail",
        "j_shadow_layer_statuses": j_shadow_layers,
        "j_shadow_layer_status_inventory_sha256": controls.canonical_sha256(
            j_shadow_layers
        ),
        "layer50_j_shadow_status": "pass",
        "j_orientation_status": "pass",
        "absolute_real_j_status": "fail",
        "real_j_over_identity_status": "fail",
        "real_j_over_five_random_status": "fail",
        "linearity_status": "fail",
        "layer50_primary_transport_status": "fail",
        "layer50_linearity_status": "fail",
        "layer50_realized_rms_fraction_min": 0.01,
        "layer50_realized_rms_fraction_max": 0.08,
        "layer50_envelope_row_count": controls.LAYER50_ENVELOPE_ROW_COUNT,
        "layer50_envelope_identity_set_sha256": (
            controls.LAYER50_ENVELOPE_IDENTITY_SET_SHA256
        ),
        "j_orientation_row_count": 68,
        "neutral_prompt_count": 8,
        "realization_pair_row_count": 1_152,
        "edited_forward_count": 2_304,
        "transport_row_count": 8_064,
        "linearity_row_count": 192,
        "captured_j_layer_count": 34,
        "captured_j_layers_sha256": controls.J_LAYERS_SHA256,
        "shadow_dtype": "float32",
        "model_forward_count": 2_320,
        "cumulative_elapsed_seconds": 600.0,
        "cumulative_spend_usd": 1.0,
        "target_prompt_render_count": 0,
        "target_forward_count": 0,
        "target_outcome_count": 0,
        "prior_outcome_inputs": [],
    }
    self_hash = controls.canonical_sha256(core)
    return {**core, "receipt_sha256": self_hash}


class StageAGateSeparationTests(unittest.TestCase):
    def test_hard_safety_allows_neutral_stage_b_chain_without_erasing_scientific_failures(
        self,
    ) -> None:
        plan = _plan_manifest()
        plan_hash = plan["plan_manifest_sha256"]
        run_id = "stage-a-contract-20260714"
        budget = {
            "plan_manifest_sha256": plan_hash,
            "receipt_sha256": "b" * 64,
        }
        benchmark = {
            "plan_manifest_sha256": plan_hash,
            "receipt_sha256": "9" * 64,
        }
        raw = _raw_stage_a_receipt(plan_hash=plan_hash, run_id=run_id)
        stage_a = _stage_a_scientific_failure_receipt(
            plan_hash=plan_hash,
            raw_hash=raw["receipt_sha256"],
            run_id=run_id,
            budget_hash=budget["receipt_sha256"],
        )

        validated_safety = controls.validate_stage_a_safety_receipt(stage_a)
        self.assertEqual(validated_safety["status"], "fail")
        self.assertEqual(validated_safety["hard_safety_status"], "pass")
        with self.assertRaises(controls.ControlViolation):
            controls.validate_stage_a_receipt(stage_a)

        with (
            mock.patch.object(
                gate_receipts.controls,
                "validate_storage_benchmark",
                return_value=benchmark,
            ),
            mock.patch.object(
                gate_receipts.controls,
                "validate_storage_budget",
                return_value=budget,
            ),
        ):
            target_blind = gate_receipts.build_target_blind_receipt(
                plan_manifest=plan,
                stage_a_raw_receipt=raw,
                stage_a_receipt=stage_a,
                storage_benchmark=benchmark,
                storage_budget=budget,
            )

        self.assertEqual(target_blind["status"], "pass")
        self.assertEqual(
            target_blind["scientific_gate_statuses"],
            {
                "v1_j_arithmetic_orientation": "pass",
                "v1_stage_a_global_j_shadow": "fail",
                "v1_layer50_j_shadow": "pass",
                "v1_stage_a_neutral_transport": "fail",
                "v1_stage_a_neutral_dose_linearity": "fail",
            },
        )
        self.assertEqual(
            target_blind["scientific_gate_receipt_sha256s"][
                "v1_j_arithmetic_orientation"
            ],
            stage_a["j_orientation_receipt_sha256"],
        )
        self.assertTrue(all(row["status"] == "pass" for row in target_blind["gate_records"]))
        controls.validate_target_blind_gate_receipt(target_blind)

    def test_collection_safety_fails_closed_on_realized_fidelity_or_envelope(self) -> None:
        plan_hash = "1" * 64
        receipt = _stage_a_scientific_failure_receipt(
            plan_hash=plan_hash,
            raw_hash="2" * 64,
            run_id="stage-a-stop-ship",
            budget_hash="3" * 64,
        )

        fidelity_core = dict(receipt)
        fidelity_core.pop("receipt_sha256")
        fidelity_core["realized_edit_fidelity_status"] = "fail"
        fidelity_core["collection_safety_status"] = "fail"
        fidelity_failure = _sealed(fidelity_core)
        with self.assertRaisesRegex(
            controls.ControlViolation, "realized-edit fidelity"
        ):
            controls.validate_stage_a_safety_receipt(fidelity_failure)

        orientation_core = dict(receipt)
        orientation_core.pop("receipt_sha256")
        orientation_core["j_orientation_status"] = "fail"
        orientation_core["collection_safety_status"] = "fail"
        orientation_failure = _sealed(orientation_core)
        with self.assertRaisesRegex(
            controls.ControlViolation, "J orientation safety"
        ):
            controls.validate_stage_a_safety_receipt(orientation_failure)

        envelope_core = dict(receipt)
        envelope_core.pop("receipt_sha256")
        envelope_core["layer50_envelope_identity_set_sha256"] = "0" * 64
        envelope_failure = _sealed(envelope_core)
        with self.assertRaisesRegex(
            controls.ControlViolation, "envelope identity inventory"
        ):
            controls.validate_stage_a_safety_receipt(envelope_failure)

        shadow_hash_core = dict(receipt)
        shadow_hash_core.pop("receipt_sha256")
        shadow_hash_core["j_shadow_layer_status_inventory_sha256"] = "0" * 64
        shadow_hash_failure = _sealed(shadow_hash_core)
        with self.assertRaisesRegex(
            controls.ControlViolation, "J-shadow inventory hash"
        ):
            controls.validate_stage_a_safety_receipt(shadow_hash_failure)

        shadow_status_core = dict(receipt)
        shadow_status_core.pop("receipt_sha256")
        shadow_status_core["j_shadow_status"] = "pass"
        shadow_status_failure = _sealed(shadow_status_core)
        with self.assertRaisesRegex(
            controls.ControlViolation, "global/layer-50 J-shadow status"
        ):
            controls.validate_stage_a_safety_receipt(shadow_status_failure)

    def test_stage_b_accepts_verified_incomplete_advisory_without_changing_scientific_chain(
        self,
    ) -> None:
        plan = _plan_manifest()
        plan_hash = plan["plan_manifest_sha256"]
        budget = {"plan_manifest_sha256": plan_hash, "receipt_sha256": "b" * 64}
        benchmark = {"plan_manifest_sha256": plan_hash, "receipt_sha256": "9" * 64}
        raw = _raw_stage_a_receipt(
            plan_hash=plan_hash, run_id="stage-a-review-union"
        )
        stage_a = _stage_a_scientific_failure_receipt(
            plan_hash=plan_hash,
            raw_hash=raw["receipt_sha256"],
            run_id="stage-a-review-union",
            budget_hash=budget["receipt_sha256"],
        )
        with (
            mock.patch.object(
                gate_receipts.controls,
                "validate_storage_benchmark",
                return_value=benchmark,
            ),
            mock.patch.object(
                gate_receipts.controls,
                "validate_storage_budget",
                return_value=budget,
            ),
        ):
            target_blind = gate_receipts.build_target_blind_receipt(
                plan_manifest=plan,
                stage_a_raw_receipt=raw,
                stage_a_receipt=stage_a,
                storage_benchmark=benchmark,
                storage_budget=budget,
            )
        commit = "1" * 40
        core = {
            "schema_version": controls.CONTROL_SCHEMA_VERSION,
            "status": "pass",
            "study_id": protocol.STUDY_ID,
            "protocol_version": protocol.PROTOCOL_VERSION,
            "run_id": "stage-b-review-union",
            "plan_manifest_sha256": plan_hash,
            "freeze_commit": commit,
            "git_head_commit": commit,
            "git_remote_ref": "origin/main",
            "git_remote_commit": commit,
            "bound_input_paths_sha256": "2" * 64,
            "bound_inputs_clean": True,
            "excluded_worktree_paths": [],
            "stage_a_receipt_sha256": stage_a["receipt_sha256"],
            "target_blind_receipt_sha256": target_blind["receipt_sha256"],
            "storage_budget_receipt_sha256": budget["receipt_sha256"],
            "independent_review_adjudication_sha256": "3" * 64,
            "review_status": "attempted_incomplete",
            "measured_spend_ceiling_usd": 1.0,
            "measured_walltime_ceiling_seconds": 600,
            "stage_b_prompt_count": len(protocol.STAGE_B_PROMPT_IDS),
            "paper_prompt_render_count": 0,
            "target_prompt_render_count": 0,
            "target_forward_count": 0,
            "target_outcome_count": 0,
            "prior_outcome_inputs": [],
        }
        permit = _sealed(core)
        with mock.patch.object(
            controls, "validate_storage_budget", return_value=budget
        ):
            validated = controls.validate_stage_b_permit(
                permit,
                stage_a_receipt=stage_a,
                target_blind_receipt=target_blind,
                storage_budget=budget,
            )
        self.assertEqual(validated["review_status"], "attempted_incomplete")

        unknown_core = dict(core)
        unknown_core["review_status"] = "review_skipped"
        with mock.patch.object(
            controls, "validate_storage_budget", return_value=budget
        ), self.assertRaisesRegex(controls.ControlViolation, "advisory evidence"):
            controls.validate_stage_b_permit(
                _sealed(unknown_core),
                stage_a_receipt=stage_a,
                target_blind_receipt=target_blind,
                storage_budget=budget,
            )


class VolumeSentinelContractTests(unittest.TestCase):
    def test_initializer_writes_the_one_canonical_validation_purpose(self) -> None:
        volume_id = "contract-volume-1"
        # macOS maps /var to /private/var with a symlink, while the production
        # volume contract deliberately rejects any symlinked path component.
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as directory:
            root = Path(directory)
            sentinel_path = runner.initialize_volume(root, volume_id=volume_id)
            payload = json.loads(sentinel_path.read_text(encoding="utf-8"))
            expected = {
                "schema_version": controls.CONTROL_SCHEMA_VERSION,
                "study_slug": protocol.STUDY_SLUG,
                "study_id": protocol.STUDY_ID,
                "protocol_version": protocol.PROTOCOL_VERSION,
                "volume_id": volume_id,
                "purpose": "target_blind_realization_validation_v1",
            }
            self.assertEqual(controls.VOLUME_PURPOSE, expected["purpose"])
            self.assertEqual(payload, expected)
            self.assertEqual(controls.require_volume_root(root, volume_id=volume_id), root)
            self.assertEqual(runner.initialize_volume(root, volume_id=volume_id), sentinel_path)

            payload["purpose"] = "paper_prompt_experiment"
            sentinel_path.write_bytes(protocol.canonical_json_bytes(payload) + b"\n")
            with self.assertRaisesRegex(controls.ControlViolation, "sentinel differs"):
                controls.require_volume_root(root, volume_id=volume_id)


if __name__ == "__main__":
    unittest.main()

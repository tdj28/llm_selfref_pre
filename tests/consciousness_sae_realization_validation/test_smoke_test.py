from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from experiments.consciousness_sae_realization_validation import build_plan
from experiments.consciousness_sae_realization_validation import controls
from experiments.consciousness_sae_realization_validation import protocol
from experiments.consciousness_sae_realization_validation import smoke_test


class _Tokenizer:
    def apply_chat_template(self, messages, *, tokenize, add_generation_prompt):
        if not tokenize or not add_generation_prompt or len(messages) != 2:
            raise AssertionError("render contract differs")
        return [17, 29, 43]


def _top_rows(token_ids: list[int], *, largest: bool) -> list[dict[str, object]]:
    scores = [float(smoke_test.SMOKE_TOP_K - index) for index in range(smoke_test.SMOKE_TOP_K)]
    if not largest:
        scores = [float(index - smoke_test.SMOKE_TOP_K) for index in range(smoke_test.SMOKE_TOP_K)]
    return [
        {"rank": index + 1, "token_id": token_ids[index], "score": scores[index]}
        for index in range(smoke_test.SMOKE_TOP_K)
    ]


def _valid_receipt() -> dict[str, object]:
    digest = "a" * 64
    token_ids = [17, 29, 43]
    panel = list(smoke_test.smoke_selected_token_panel())
    capture = {
        branch: {
            "branch": branch,
            "captured_j_layers": list(protocol.J_LAYERS),
            "captured_j_layer_count": len(protocol.J_LAYERS),
            "final_state_captured": True,
            "arc_tensor_sha256": digest,
        }
        for branch in ("clean", "plus", "minus")
    }
    realization = {
        "hook_fire_count_plus": 1,
        "hook_fire_count_minus": 1,
        "pre_equals_clean_plus": True,
        "pre_equals_clean_minus": True,
        "captured_layer50_equals_pre_plus": True,
        "captured_layer50_equals_pre_minus": True,
        "native_post_bytes_exact_plus": True,
        "native_post_bytes_exact_minus": True,
        "requested_vector_exact_plus": True,
        "requested_vector_exact_minus": True,
        "upstream_45_49_bytes_equal_clean_plus": True,
        "upstream_45_49_bytes_equal_clean_minus": True,
        "requested_realized_central_relative_rmse": 0.01,
        "requested_realized_central_cosine": 0.99,
        "requested_rms_fraction": smoke_test.SMOKE_DOSE_FRACTION,
        "realized_rms_fraction": smoke_test.SMOKE_DOSE_FRACTION,
        "common_mode_to_central_rms": 0.01,
        "realized_central_sha256": digest,
        "actual_final_central_sha256": digest,
        "finite": True,
    }
    core = {
        "schema_version": smoke_test.SMOKE_SCHEMA_VERSION,
        "receipt_type": smoke_test.SMOKE_RECEIPT_TYPE,
        "status": "pass",
        "study_id": protocol.STUDY_ID,
        "protocol_version": protocol.PROTOCOL_VERSION,
        "run_id": "smoke-unit",
        "plan_manifest_sha256": digest,
        "plan_source_inventory_sha256": digest,
        "smoke_source_sha256": digest,
        "preexecution_authorization_sha256": digest,
        "ownership_receipt_sha256": digest,
        "guest_receipt_sha256": digest,
        "cache_receipt_sha256": digest,
        "campaign_identity_sha256": digest,
        "campaign_started_at_unix": 1000.0,
        "provider_terminate_at_unix": 22600.0,
        "completed_at_unix": 1100.0,
        "external_receipt_relative_path": (
            f"{protocol.STUDY_SLUG}/{protocol.STUDY_ID}/"
            f"{smoke_test.SMOKE_RECEIPT_SUBDIRECTORY}/smoke-unit.json"
        ),
        "execution_binding": {
            "backend": "consciousness_sae_realization_validation.runtime.V2Backend",
            "provider_gpu_type": "NVIDIA B200",
            "provider_gpu_count": 1,
            "model_revision": protocol.MODEL_SPEC["revision"],
            "model_dtype": protocol.MODEL_SPEC["dtype"],
            "sae_revision": protocol.SAE_SPEC["revision"],
            "sae_sha256": protocol.SAE_SPEC["sha256"],
            "j_lens_revision": protocol.J_LENS_SPEC["revision"],
            "j_lens_sha256": protocol.J_LENS_SPEC["sha256"],
            "container_image": protocol.CONTAINER_IMAGE_SPEC,
            "public_artifact_rehash_bound": True,
        },
        "prompt_receipt": {
            "prompt_id": smoke_test.SMOKE_PROMPT_ID,
            "prompt_role": "disjoint_mundane_operational_smoke_only",
            "prompt_payload_sha256": protocol.canonical_sha256(smoke_test.SMOKE_PROMPT),
            "token_ids": token_ids,
            "token_ids_sha256": protocol.canonical_sha256(token_ids),
            "token_count": len(token_ids),
            "overlaps_stage_a_or_b": False,
            "target_prompt": False,
        },
        "edit_contract": {
            "edit_layer": smoke_test.SMOKE_EDIT_LAYER,
            "dose_fraction": smoke_test.SMOKE_DOSE_FRACTION,
            "dose_role": "tiny_operational_diagnostic_only",
            "direction_role": "smoke_only_generic_non_sae_direction",
            "direction_seed": protocol.seed64(
                "b200-execution-smoke-generic-direction", smoke_test.SMOKE_EDIT_LAYER
            ),
            "unit_direction_sha256": digest,
            "requested_positive_sha256": digest,
            "signed_branch_count": 2,
            "sae_feature_ids": [],
        },
        "capture_receipt": capture,
        "realization_receipt": realization,
        "transport_receipt": {
            "transport": "real_j",
            "transport_count": 1,
            "edit_layer": smoke_test.SMOKE_EDIT_LAYER,
            "selected_token_ids": panel,
            "selected_token_count": len(panel),
            "selected_token_panel_sha256": protocol.canonical_sha256(panel),
            "predicted_final_delta_sha256": digest,
            "actual_final_delta_sha256": digest,
            "residual_delta_cosine": 0.1,
            "selected_logit_delta_pearson": 0.2,
            "finite": True,
        },
        "replay_receipt": {
            "scope": "selected_panel_topk_operational_primitive",
            "top_k": smoke_test.SMOKE_TOP_K,
            "actual_selected_delta_sha256": digest,
            "actual_selected_delta_replay_sha256": digest,
            "predicted_selected_delta_sha256": digest,
            "predicted_selected_delta_replay_sha256": digest,
            "actual_selected_logits_replay_exact": True,
            "predicted_selected_logits_replay_exact": True,
            "actual_top": _top_rows(panel[: smoke_test.SMOKE_TOP_K], largest=True),
            "actual_bottom": _top_rows(panel[8 : 8 + smoke_test.SMOKE_TOP_K], largest=False),
            "predicted_top": _top_rows(panel[16 : 16 + smoke_test.SMOKE_TOP_K], largest=True),
            "predicted_bottom": _top_rows(panel[24 : 24 + smoke_test.SMOKE_TOP_K], largest=False),
            "full_vocabulary_replay_claimed": False,
            "scientific_replay_claimed": False,
        },
        "runtime_metadata": {
            "model_forward_count": smoke_test.SMOKE_EXPECTED_MODEL_FORWARD_COUNT,
            "hardware": {"cuda_device_count": 1, "gpu_name": "NVIDIA B200"},
        },
        "resource": {"cumulative_estimated_spend_usd": 0.01},
        "model_forward_count": smoke_test.SMOKE_EXPECTED_MODEL_FORWARD_COUNT,
        "expected_model_forward_count": smoke_test.SMOKE_EXPECTED_MODEL_FORWARD_COUNT,
        "mundane_smoke_prompt_render_count": 1,
        "stage_a_prompt_render_count": 0,
        "stage_b_prompt_render_count": 0,
        "paper_prompt_render_count": 0,
        "target_prompt_render_count": 0,
        "target_feature_vector_count": 0,
        "target_outcome_count": 0,
        "behavioral_outcome_count": 0,
        "scientific_gate_input_count": 0,
        "dose_selection_input_count": 0,
        "scientific_gate_eligible": False,
        "dose_selection_eligible": False,
        "result_reuse_prohibited": True,
        "prior_outcome_inputs": [],
    }
    return smoke_test._seal(core)


class SmokeProtocolTests(unittest.TestCase):
    def test_prompt_is_disjoint_and_receipted(self) -> None:
        token_ids, receipt = smoke_test.render_smoke_prompt(_Tokenizer())
        self.assertEqual(token_ids, (17, 29, 43))
        self.assertEqual(receipt["token_ids"], [17, 29, 43])
        self.assertFalse(receipt["overlaps_stage_a_or_b"])
        self.assertFalse(receipt["target_prompt"])
        self.assertNotIn(smoke_test.SMOKE_PROMPT_ID, protocol.STAGE_A_PROMPT_IDS)
        self.assertNotIn(smoke_test.SMOKE_PROMPT_ID, protocol.STAGE_B_PROMPT_IDS)

    def test_small_logit_panel_is_unique_and_in_vocabulary(self) -> None:
        panel = smoke_test.smoke_selected_token_panel()
        self.assertEqual(len(panel), smoke_test.SMOKE_SELECTED_TOKEN_COUNT)
        self.assertEqual(len(set(panel)), len(panel))
        self.assertGreaterEqual(min(panel), 0)
        self.assertLess(max(panel), protocol.VOCAB_SIZE)

    def test_smoke_runner_is_part_of_the_plan_source_surface(self) -> None:
        self.assertIn(
            smoke_test.SMOKE_SOURCE_RELATIVE_PATH, build_plan.BOUND_SOURCE_PATHS
        )

    def test_cli_requires_every_provider_and_artifact_binding(self) -> None:
        required = {
            option
            for action in smoke_test.build_parser()._actions
            if action.required
            for option in action.option_strings
            if option.startswith("--")
        }
        self.assertEqual(
            required,
            {
                "--plan-dir",
                "--volume-root",
                "--volume-id",
                "--run-id",
                "--model-snapshot",
                "--sae-path",
                "--j-lens-path",
                "--hourly-price-usd",
                "--campaign-started-at-unix",
                "--provider-terminate-at-unix",
                "--ownership-receipt",
                "--guest-receipt",
                "--cache-receipt",
                "--preexecution-authorization",
            },
        )


class SmokeReceiptTests(unittest.TestCase):
    def test_valid_receipt_is_accepted(self) -> None:
        receipt = _valid_receipt()
        self.assertEqual(
            smoke_test.validate_smoke_receipt(
                receipt,
                expected_plan_hash="a" * 64,
                expected_run_id="smoke-unit",
            )["status"],
            "pass",
        )

    def test_authorization_chain_swap_is_rejected(self) -> None:
        receipt = _valid_receipt()
        authorization = {
            "receipt_sha256": "a" * 64,
            "plan_manifest_sha256": "a" * 64,
            "plan_source_inventory_sha256": "a" * 64,
            "ownership_receipt_sha256": "a" * 64,
            "guest_receipt_sha256": "a" * 64,
            "cache_receipt_sha256": "b" * 64,
            "campaign_identity_sha256": "a" * 64,
            "campaign_started_at_unix": 1000.0,
            "provider_terminate_at_unix": 22600.0,
        }
        with self.assertRaisesRegex(smoke_test.SmokeTestError, "authorization binding"):
            smoke_test.validate_smoke_receipt(
                receipt, expected_authorization=authorization
            )

    def test_target_access_is_rejected_even_with_valid_self_hash(self) -> None:
        receipt = _valid_receipt()
        receipt["target_outcome_count"] = 1
        receipt = smoke_test._seal(
            {key: value for key, value in receipt.items() if key != "receipt_sha256"}
        )
        with self.assertRaisesRegex(smoke_test.SmokeTestError, "target-free"):
            smoke_test.validate_smoke_receipt(receipt)

    def test_gate_or_dose_eligibility_is_rejected(self) -> None:
        for field in ("scientific_gate_eligible", "dose_selection_eligible"):
            with self.subTest(field=field):
                receipt = _valid_receipt()
                receipt[field] = True
                receipt = smoke_test._seal(
                    {
                        key: value
                        for key, value in receipt.items()
                        if key != "receipt_sha256"
                    }
                )
                with self.assertRaisesRegex(smoke_test.SmokeTestError, "boundary"):
                    smoke_test.validate_smoke_receipt(receipt)

    def test_forward_count_is_exact_not_merely_a_lower_bound(self) -> None:
        receipt = _valid_receipt()
        receipt["model_forward_count"] = 5
        receipt = smoke_test._seal(
            {key: value for key, value in receipt.items() if key != "receipt_sha256"}
        )
        with self.assertRaisesRegex(smoke_test.SmokeTestError, "boundary"):
            smoke_test.validate_smoke_receipt(receipt)

    def test_self_hash_tampering_is_rejected(self) -> None:
        receipt = _valid_receipt()
        receipt["status"] = "fail"
        with self.assertRaisesRegex(smoke_test.SmokeTestError, "self-hash"):
            smoke_test.validate_smoke_receipt(receipt)

    def test_receipt_path_is_external_to_raw_and_fresh(self) -> None:
        with tempfile.TemporaryDirectory(dir=smoke_test.REPO_ROOT) as temporary:
            root = Path(temporary)
            sentinel = {
                "schema_version": controls.CONTROL_SCHEMA_VERSION,
                "study_slug": protocol.STUDY_SLUG,
                "study_id": protocol.STUDY_ID,
                "protocol_version": protocol.PROTOCOL_VERSION,
                "volume_id": "volume-test",
                "purpose": controls.VOLUME_PURPOSE,
            }
            (root / controls.VOLUME_SENTINEL).write_text(
                json.dumps(sentinel), encoding="utf-8"
            )
            path = smoke_test.smoke_receipt_path(
                root, volume_id="volume-test", run_id="smoke-unit"
            )
            raw_root = root.joinpath(*controls.RAW_NAMESPACE)
            self.assertNotIn(raw_root, path.parents)
            self.assertEqual(path.name, "smoke-unit.json")


if __name__ == "__main__":
    unittest.main()

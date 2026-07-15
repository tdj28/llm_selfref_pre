from __future__ import annotations

import json

import pytest

from experiments.consciousness_sae_target_blind_calibration import audit, protocol


def _cache_receipt_and_live_rehash(
    receipt_sha256: str = "c" * 64,
) -> tuple[dict, dict]:
    components = [
        {"component": name} for name in audit.runpod_preflight.CACHE_COMPONENTS
    ]
    cache = {
        "receipt_sha256": receipt_sha256,
        "cache_root": audit.runpod_preflight.LEGACY_PUBLIC_ARTIFACT_ROOT,
        "full_file_count": audit.runpod_preflight.LEGACY_PUBLIC_ARTIFACT_FILE_COUNT,
        "full_retained_bytes": audit.runpod_preflight.LEGACY_PUBLIC_ARTIFACT_BYTES,
        "full_file_inventory_sha256": (
            audit.runpod_preflight.LEGACY_PUBLIC_ARTIFACT_INVENTORY_SHA256
        ),
        "components": components,
    }
    core = {
        "status": "pass_exact_pre_backend_rehash",
        "cache_receipt_sha256": receipt_sha256,
        **{
            field: cache[field]
            for field in (
                "cache_root",
                "full_file_count",
                "full_retained_bytes",
                "full_file_inventory_sha256",
                "components",
            )
        },
    }
    return cache, {**core, "receipt_sha256": protocol.canonical_sha256(core)}


def test_transport_summary_separates_component_claims(monkeypatch) -> None:
    monkeypatch.setitem(protocol.GATE_THRESHOLDS, "bootstrap_replicates", 100)
    rows = []
    for prompt_id in protocol.PROMPT_IDS:
        for direction in protocol.DIRECTIONS:
            for layer in protocol.READOUT_LAYERS:
                for transport in protocol.TRANSPORTS:
                    if transport == "real_j":
                        residual, logit = 0.80, 0.80
                    elif transport == "identity":
                        residual, logit = 0.70, 0.70
                    else:
                        residual, logit = 0.20, 0.20
                    rows.append(
                        {
                            "prompt_id": prompt_id,
                            "direction": direction,
                            "readout_layer": layer,
                            "transport": transport,
                            "residual_delta_cosine": residual,
                            "fixed_token_logit_delta_pearson": logit,
                        }
                    )
    summary = audit._transport_summary(rows, j_projection_eligible=True)
    assert summary["diagnostic_descriptive_j_readout_threshold_pass_layers"] == list(
        protocol.READOUT_LAYERS
    )
    assert summary["diagnostic_learned_j_added_value_threshold_pass_layers"] == list(
        protocol.READOUT_LAYERS
    )
    assert summary["descriptive_j_readout_eligible_layers"] == [
        protocol.PRIMARY_READOUT_LAYER
    ]
    assert summary["learned_j_added_value_eligible_layers"] == [
        protocol.PRIMARY_READOUT_LAYER
    ]
    projection_failed = audit._transport_summary(rows, j_projection_eligible=False)
    assert projection_failed["descriptive_j_readout_eligible_layers"] == []
    assert projection_failed["learned_j_added_value_eligible_layers"] == []
    assert projection_failed[
        "diagnostic_descriptive_j_readout_threshold_pass_layers"
    ] == list(protocol.READOUT_LAYERS)
    row = summary["residual_delta_cosine"]["by_readout_layer"]["70"]
    assert row["absolute_real_j_status"] == "pass"
    assert row["real_j_over_five_random_status"] == "pass"
    assert row["real_j_over_identity_status"] == "pass"
    assert row["composite_status"] == "pass"


def test_prompt_receipts_are_rerendered_and_target_flag_is_enforced() -> None:
    tokens_by_user = {
        protocol.prompt_payload(prompt_id)["user"]: [offset + 1, offset + 101]
        for offset, prompt_id in enumerate(protocol.PROMPT_IDS)
    }

    class Tokenizer:
        def apply_chat_template(self, messages, **_kwargs):
            return tokens_by_user[messages[1]["content"]]

    rows = []
    for prompt_id in protocol.PROMPT_IDS:
        token_ids = tokens_by_user[protocol.prompt_payload(prompt_id)["user"]]
        rows.append(
            {
                "prompt_id": prompt_id,
                "target_prompt": False,
                "prompt_payload_sha256": protocol.canonical_sha256(
                    protocol.prompt_payload(prompt_id)
                ),
                "token_ids": token_ids,
                "token_ids_sha256": protocol.canonical_sha256(token_ids),
                "token_count": len(token_ids),
                "prefix_token_count": len(token_ids) - 1,
                "edited_token_index": len(token_ids) - 1,
                "continuation_token_id": token_ids[-1],
                "continuation_forward_sequence_length": 1,
                "intervention_state_contract_sha256": protocol.canonical_sha256(
                    protocol.INTERVENTION_STATE_CONTRACT
                ),
                "j_state_contract_sha256": protocol.canonical_sha256(
                    protocol.J_STATE_CONTRACT
                ),
                "fixed_panel_estimand_sha256": protocol.canonical_sha256(
                    protocol.FIXED_PANEL_ESTIMAND
                ),
            }
        )
    audit._audit_prompt_receipts(rows, Tokenizer())
    rows[0]["target_prompt"] = True
    with pytest.raises(audit.CalibrationAuditError, match="prompt/token binding"):
        audit._audit_prompt_receipts(rows, Tokenizer())


def test_fixed_panel_rejects_a_self_consistent_but_wrong_panel(tmp_path) -> None:
    expected = list(audit._fixed_token_panel())
    path = tmp_path / "fixed_token_panel.json"
    path.write_text(
        json.dumps(
            {"token_ids": expected, "sha256": protocol.canonical_sha256(expected)}
        )
    )
    assert audit._audit_fixed_panel(tmp_path) == tuple(expected)
    expected[0], expected[1] = expected[1], expected[0]
    path.write_text(
        json.dumps(
            {"token_ids": expected, "sha256": protocol.canonical_sha256(expected)}
        )
    )
    with pytest.raises(audit.CalibrationAuditError, match="fixed-token panel"):
        audit._audit_fixed_panel(tmp_path)


def test_signed_branch_rmse_gates_even_when_central_passes() -> None:
    row = {
        "hard_safety_pass": True,
        "requested_plus_realized_relative_rmse": 0.11,
        "requested_minus_realized_relative_rmse": 0.01,
        "requested_realized_central_relative_rmse": 0.01,
        "requested_plus_realized_cosine": 0.999,
        "requested_minus_realized_cosine": 0.999,
        "requested_realized_central_cosine": 0.999,
        "common_mode_to_central_rms": 0.01,
    }
    assert audit._edit_gate_failed(row) is True
    row["requested_plus_realized_relative_rmse"] = 0.01
    assert audit._edit_gate_failed(row) is False


def test_signed_branch_cosine_gates_even_when_central_passes() -> None:
    row = {
        "hard_safety_pass": True,
        "requested_plus_realized_relative_rmse": 0.01,
        "requested_minus_realized_relative_rmse": 0.01,
        "requested_realized_central_relative_rmse": 0.01,
        "requested_plus_realized_cosine": 0.99,
        "requested_minus_realized_cosine": 0.999,
        "requested_realized_central_cosine": 0.999,
        "common_mode_to_central_rms": 0.01,
    }
    assert audit._edit_gate_failed(row) is True
    row["requested_plus_realized_cosine"] = 0.999
    assert audit._edit_gate_failed(row) is False


def test_hard_safety_and_delivery_failures_are_separable() -> None:
    row = {
        "hard_safety_pass": False,
        "requested_plus_realized_relative_rmse": 0.01,
        "requested_minus_realized_relative_rmse": 0.01,
        "requested_realized_central_relative_rmse": 0.01,
        "requested_plus_realized_cosine": 0.999,
        "requested_minus_realized_cosine": 0.999,
        "requested_realized_central_cosine": 0.999,
        "common_mode_to_central_rms": 0.01,
    }
    assert audit._hard_safety_failed(row) is True
    assert audit._delivery_gate_failed(row) is False
    assert audit._collection_edit_gate_failed(0.01, row) is True
    row["hard_safety_pass"] = True
    row["requested_realized_central_relative_rmse"] = 0.11
    assert audit._hard_safety_failed(row) is False
    assert audit._delivery_gate_failed(row) is True
    assert audit._collection_edit_gate_failed(0.01, row) is False
    assert audit._collection_edit_gate_failed(0.02, row) is True


def test_collection_gate_is_separate_from_linearity_and_j() -> None:
    statuses = audit._separated_claim_statuses(
        edit_failure_count=0,
        j_shadow_failure_count=2,
        component_failures={
            "realized_source": 1,
            "j_of_realized": 1,
            "actual_final": 1,
        },
        orientation_status="fail",
    )
    assert statuses["later_actual_state_collection_eligibility"] == "pass"
    assert statuses["realized_source_linearity_status"] == "fail"
    assert statuses["j_projection_claim_eligibility"] == "fail"
    statuses = audit._separated_claim_statuses(
        edit_failure_count=1,
        j_shadow_failure_count=0,
        component_failures={
            "realized_source": 0,
            "j_of_realized": 0,
            "actual_final": 0,
        },
        orientation_status="pass",
    )
    assert statuses["later_actual_state_collection_eligibility"] == "fail"


def test_linearity_uses_requested_source_scale_and_zero_delivery_fails() -> None:
    torch = pytest.importorskip("torch")
    base = torch.tensor([1.0, -1.0], dtype=torch.float32)
    values = {}
    for dose in protocol.LINEARITY_GATE_DOSES:
        requested_scale = dose
        # Nonlinear realized gain: dividing the source by its own realized
        # scale would make these look identical, while requested scaling must
        # correctly expose the gain change.
        realized_scale = dose * (1.0 if dose == protocol.PRIMARY_DOSE else 2.0)
        values[dose] = (
            base * realized_scale,
            base * realized_scale,
            base * realized_scale,
            requested_scale,
            realized_scale,
        )
    rows, failures = audit._linearity_summary({("neutral_c01", 0): values})
    assert rows[0]["realized_source_status"] == "fail"
    assert failures["realized_source"] == 1

    zero_values = {
        dose: (base * 0, base * 0, base * 0, dose, 0.0)
        for dose in protocol.LINEARITY_GATE_DOSES
    }
    rows, failures = audit._linearity_summary({("neutral_c01", 0): zero_values})
    assert rows[0]["realized_source_zero_scale_failure"] is False
    assert rows[0]["j_of_realized_zero_scale_failure"] is True
    assert rows[0]["actual_final_zero_scale_failure"] is True
    assert failures == {"realized_source": 1, "j_of_realized": 1, "actual_final": 1}


def test_tiny_direct_transport_and_readout_recomputation_detect_tampering() -> None:
    torch = pytest.importorskip("torch")
    source = torch.tensor([1.0, -2.0, 0.5, 3.0], dtype=torch.float32)
    matrix = torch.tensor(
        [
            [1.0, 0.0, 0.0, 0.0],
            [0.0, 2.0, 0.0, 0.0],
            [0.0, 0.0, -1.0, 0.0],
            [0.0, 0.0, 0.0, 0.5],
        ],
        dtype=torch.bfloat16,
    )
    prediction = audit._direct_transport(source, matrix, layer=50, transport="real_j")
    assert torch.equal(prediction, source.to(torch.bfloat16) @ matrix.T)
    audit._require_tensor_exact(prediction.clone(), prediction, "tiny")
    tampered = prediction.clone()
    tampered[0] += 1
    with pytest.raises(audit.CalibrationAuditError, match="recomputation differs"):
        audit._require_tensor_exact(tampered, prediction, "tiny")

    norm = torch.ones(4, dtype=torch.bfloat16)
    head = torch.tensor(
        [[1.0, 0.0, 1.0, 0.0], [0.0, 1.0, 0.0, 1.0]],
        dtype=torch.bfloat16,
    )
    logits = audit._selected_logits(source, norm, head, 1e-5)
    values = source.to(torch.bfloat16).float()
    normalized = values * torch.rsqrt(values.square().mean() + 1e-5)
    expected = (
        (normalized.to(torch.bfloat16) * norm).to(torch.bfloat16) @ head.T
    ).float()
    assert torch.equal(logits, expected)

    midpoint = torch.tensor([2.0, 0.5, -1.0, 0.25], dtype=torch.float32)
    perturbation = torch.tensor([0.2, -0.1, 0.05, 0.3], dtype=torch.float32)
    midpoint_contrast = audit._midpoint_selected_logit_contrast(
        midpoint, perturbation, norm, head, 1e-5
    )
    explicit = (
        audit._selected_logits(midpoint + perturbation, norm, head, 1e-5)
        - audit._selected_logits(midpoint - perturbation, norm, head, 1e-5)
    ) * 0.5
    clean_centered = audit._midpoint_selected_logit_contrast(
        torch.zeros_like(midpoint), perturbation, norm, head, 1e-5
    )
    assert torch.equal(midpoint_contrast, explicit)
    assert not torch.equal(midpoint_contrast, clean_centered)


def test_audit_budget_watchdog_uses_conservative_rate(monkeypatch) -> None:
    started = 1_000.0
    monkeypatch.setattr(audit.time, "time", lambda: started + 3_599)
    watchdog = audit._AuditBudgetWatchdog(
        {
            "campaign_started_at_unix": started,
            "campaign_deadline_at_unix": started + 5_400,
            "hourly_price_usd": 2.0,
        }
    )
    monkeypatch.setattr(audit.time, "time", lambda: started + 5_399)
    watchdog.check()
    monkeypatch.setattr(audit.time, "time", lambda: started + 5_401)
    with pytest.raises(audit.CalibrationAuditError, match=r"90-minute/\$9"):
        watchdog.check()

    monkeypatch.setattr(audit.time, "time", lambda: started + 3_600)
    with pytest.raises(audit.CalibrationAuditError, match="did not start"):
        audit._AuditBudgetWatchdog(
            {
                "campaign_started_at_unix": started,
                "campaign_deadline_at_unix": started + 5_400,
                "hourly_price_usd": 2.0,
            }
        )


def test_compact_pair_publication_is_atomic_and_deadline_guarded(
    tmp_path, monkeypatch
) -> None:
    receipt = {
        "receipt_sha256": "a" * 64,
        "audit_started_at_unix": 2_000.0,
        "campaign_started_at_unix": 1_000.0,
        "campaign_deadline_at_unix": 6_400.0,
        "hourly_price_usd": 6.0,
    }
    summary = {"receipt_sha256": "b" * 64}
    monkeypatch.setattr(audit.time, "time", lambda: 3_000.0)
    directory = tmp_path / "compact"
    result = audit._publish_pair_atomic(
        directory / "CALIBRATION_AUDIT.json",
        directory / "CALIBRATION_SUMMARY.json",
        receipt,
        summary,
    )
    assert result == directory / "CALIBRATION_SUMMARY.json"
    marker = json.loads((directory / "PUBLICATION_COMPLETE.json").read_text())
    assert marker["status"] == "complete"
    assert marker["audit_receipt_sha256"] == receipt["receipt_sha256"]

    late_directory = tmp_path / "late"
    times = iter((3_000.0, 3_000.0, 3_000.0, 3_000.0, 3_000.0, 6_400.0))
    monkeypatch.setattr(audit.time, "time", lambda: next(times))
    with pytest.raises(audit.CalibrationAuditError, match=r"90-minute/\$9"):
        audit._publish_pair_atomic(
            late_directory / "CALIBRATION_AUDIT.json",
            late_directory / "CALIBRATION_SUMMARY.json",
            receipt,
            summary,
        )
    assert not late_directory.exists()
    assert (tmp_path / ".late.expired").is_dir()


def test_runtime_and_execution_binding_reject_forward_count_tamper(tmp_path) -> None:
    seed = protocol.seed64("runtime-v2") % (2**63 - 1)
    _cache, live_rehash = _cache_receipt_and_live_rehash()
    started = 1_000.0
    runner_deadline = started + protocol.RESOURCE_LIMITS["runner_sub_watchdog_seconds"]
    runtime = {
        "container_image": protocol.CONTAINER_IMAGE_SPEC,
        "hardware": {
            "cuda_device_count": 1,
            "gpu_name": "NVIDIA B200",
            "gpu_total_memory_bytes": 192 * 1024**3,
        },
        "software": dict(audit.EXPECTED_SOFTWARE),
        "determinism": {
            "seed": seed,
            "cublas_workspace_config": ":4096:8",
            "deterministic_algorithms": True,
            "cuda_matmul_tf32": False,
            "cudnn_tf32": False,
            "flash_sdp_enabled": False,
            "mem_efficient_sdp_enabled": False,
            "math_sdp_enabled": True,
        },
        "model_forward_count": 256,
        "first_model_forward_at_utc": "2026-07-14T00:00:00Z",
        "last_model_forward_at_utc": "2026-07-14T00:01:00Z",
        "expected_model_forward_count": 256,
        "expected_edited_forward_count": 240,
        "prompt_count": 8,
        "realization_row_count": 120,
        "readout_transport_row_count": 4872,
        "j_orientation_row_count": 68,
        "j_orientation_status": "pass",
        "runner_watchdog_seconds": protocol.RESOURCE_LIMITS[
            "runner_sub_watchdog_seconds"
        ],
        "runner_deadline_at_unix": runner_deadline,
        "live_public_cache_rehash": live_rehash,
        "intervention_state_contract_sha256": protocol.canonical_sha256(
            protocol.INTERVENTION_STATE_CONTRACT
        ),
        "j_state_contract_sha256": protocol.canonical_sha256(protocol.J_STATE_CONTRACT),
        "fixed_panel_estimand_sha256": protocol.canonical_sha256(
            protocol.FIXED_PANEL_ESTIMAND
        ),
        "forward_inventory": protocol.FORWARD_INVENTORY,
        "total_rendered_token_count": 800,
        "prefix_uncached_token_count": 792,
        "continuation_uncached_token_count": 248,
        "total_uncached_token_count": 1_040,
    }
    resource = {
        "hourly_price_usd": 2.0,
        "campaign_started_at_unix": started,
        "campaign_deadline_at_unix": started
        + protocol.RESOURCE_LIMITS["max_walltime_seconds"],
        "runner_deadline_at_unix": runner_deadline,
        "runner_watchdog_seconds": protocol.RESOURCE_LIMITS[
            "runner_sub_watchdog_seconds"
        ],
        "run_started_at_unix": 1_001.0,
        "run_completed_at_unix": 1_002.0,
        "campaign_elapsed_seconds": 2.0,
        "campaign_estimated_spend_usd": 2.0 * 2.0 / 3600,
    }
    plan = {"plan_manifest_sha256": "f" * 64, "git_head_commit": "e" * 40}
    binding = {
        "study_id": protocol.STUDY_ID,
        "protocol_version": protocol.PROTOCOL_VERSION,
        "canonical_plan_relative_path": protocol.CANONICAL_PLAN_RELATIVE_PATH,
        "plan_manifest_sha256": plan["plan_manifest_sha256"],
        "plan_git_head_commit": plan["git_head_commit"],
        "pod_id": "pod-1",
        "volume_id": protocol.NETWORK_VOLUME_ID,
        "data_center_id": protocol.DATA_CENTER_ID,
        "ownership_receipt_sha256": "a" * 64,
        "guest_receipt_sha256": "b" * 64,
        "cache_receipt_sha256": "c" * 64,
        "authorization_receipt_sha256": "d" * 64,
        "artifacts": {
            "sae": {
                "path": "/workspace/sae.pt",
                "bytes": 1,
                "sha256": protocol.SAE_SPEC["sha256"],
            },
            "j_lens": {
                "path": "/workspace/j.pt",
                "bytes": 1,
                "sha256": protocol.J_LENS_SPEC["sha256"],
            },
        },
        "adaptive_design_inputs_sha256": protocol.canonical_sha256(
            protocol.ADAPTIVE_DESIGN_INPUTS
        ),
        "analysis_data_inputs": [],
        "target_prompt_render_count": 0,
        "target_feature_vector_count": 0,
        "live_public_cache_rehash": live_rehash,
        "intervention_state_contract_sha256": protocol.canonical_sha256(
            protocol.INTERVENTION_STATE_CONTRACT
        ),
        "j_state_contract_sha256": protocol.canonical_sha256(protocol.J_STATE_CONTRACT),
        "fixed_panel_estimand_sha256": protocol.canonical_sha256(
            protocol.FIXED_PANEL_ESTIMAND
        ),
    }
    (tmp_path / "runtime_metadata.json").write_text(json.dumps(runtime))
    (tmp_path / "execution_binding.json").write_text(json.dumps(binding))
    complete = {
        "runtime": runtime,
        "resource": resource,
        "volume_id": protocol.NETWORK_VOLUME_ID,
    }
    audit._audit_runtime_and_binding(tmp_path, complete=complete, plan=plan)
    runtime["model_forward_count"] = 255
    complete["runtime"] = runtime
    (tmp_path / "runtime_metadata.json").write_text(json.dumps(runtime))
    with pytest.raises(audit.CalibrationAuditError, match="runtime/hardware/forward"):
        audit._audit_runtime_and_binding(tmp_path, complete=complete, plan=plan)


def _external_receipt_fixture(tmp_path, monkeypatch):
    plan_dir = tmp_path / "plan"
    plan_dir.mkdir()
    (plan_dir / "plan_manifest.json").write_bytes(b"{}\n")
    (plan_dir / "source_files.json").write_bytes(b"{}\n")
    started = 1_000.0
    deadline = 1_100.0
    price = 2.0
    ownership = {
        "receipt_sha256": "a" * 64,
        "pod_id": "pod-1",
        "network_volume_id": protocol.NETWORK_VOLUME_ID,
        "data_center_id": protocol.DATA_CENTER_ID,
    }
    guest = {"receipt_sha256": "b" * 64}
    cache, live_rehash = _cache_receipt_and_live_rehash()
    authorization = {
        "receipt_sha256": "d" * 64,
        "canonical_plan_relative_path": protocol.CANONICAL_PLAN_RELATIVE_PATH,
        "campaign_started_at_unix": started,
        "campaign_deadline_at_unix": deadline,
        "hourly_price_usd": price,
    }
    values = {
        "ownership": ownership,
        "guest": guest,
        "cache": cache,
        "authorization": authorization,
    }
    paths = {}
    for label, value in values.items():
        path = tmp_path / f"{label}.json"
        path.write_bytes(protocol.canonical_json_bytes(value) + b"\n")
        paths[label] = path
    monkeypatch.setattr(
        audit.runpod_preflight,
        "validate_ownership_receipt",
        lambda value: dict(value),
    )
    monkeypatch.setattr(
        audit.runpod_preflight,
        "validate_guest_receipt",
        lambda value, *, ownership_receipt: dict(value),
    )
    monkeypatch.setattr(
        audit.runpod_preflight,
        "validate_cache_receipt",
        lambda value, *, guest_receipt, ownership_receipt: dict(value),
    )
    monkeypatch.setattr(
        audit.authorize,
        "validate_execution_authorization",
        lambda value, **_kwargs: dict(value),
    )
    binding = {
        "ownership_receipt_sha256": ownership["receipt_sha256"],
        "guest_receipt_sha256": guest["receipt_sha256"],
        "cache_receipt_sha256": cache["receipt_sha256"],
        "authorization_receipt_sha256": authorization["receipt_sha256"],
        "canonical_plan_relative_path": protocol.CANONICAL_PLAN_RELATIVE_PATH,
        "pod_id": ownership["pod_id"],
        "volume_id": ownership["network_volume_id"],
        "data_center_id": ownership["data_center_id"],
        "live_public_cache_rehash": live_rehash,
    }
    complete = {
        "canonical_plan_relative_path": protocol.CANONICAL_PLAN_RELATIVE_PATH,
        "resource": {
            "campaign_started_at_unix": started,
            "campaign_deadline_at_unix": deadline,
            "hourly_price_usd": price,
        },
    }
    return plan_dir, paths, binding, complete


def _audit_external_fixture(plan_dir, paths, binding, complete):
    return audit._audit_external_receipt_chain(
        ownership_path=paths["ownership"],
        guest_path=paths["guest"],
        cache_path=paths["cache"],
        authorization_path=paths["authorization"],
        plan_dir=plan_dir,
        plan={},
        execution_binding=binding,
        complete=complete,
        now_unix=1_001.0,
    )


def test_external_receipt_chain_rejects_execution_binding_tamper(
    tmp_path, monkeypatch
) -> None:
    plan_dir, paths, binding, complete = _external_receipt_fixture(
        tmp_path, monkeypatch
    )
    result = _audit_external_fixture(plan_dir, paths, binding, complete)
    assert result["status"] == "pass"
    binding["guest_receipt_sha256"] = "e" * 64
    with pytest.raises(
        audit.CalibrationAuditError, match="physical receipt chain differs"
    ):
        _audit_external_fixture(plan_dir, paths, binding, complete)


def test_external_receipt_chain_rejects_physical_file_tamper(
    tmp_path, monkeypatch
) -> None:
    plan_dir, paths, binding, complete = _external_receipt_fixture(
        tmp_path, monkeypatch
    )
    paths["cache"].write_bytes(paths["cache"].read_bytes() + b" ")
    with pytest.raises(audit.CalibrationAuditError, match="physical file differs"):
        _audit_external_fixture(plan_dir, paths, binding, complete)

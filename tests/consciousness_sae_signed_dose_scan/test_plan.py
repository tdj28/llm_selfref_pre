from __future__ import annotations

import json
from pathlib import Path

import pytest

from experiments.consciousness_sae_signed_dose_scan import (
    build_plan,
    protocol,
    validate_plan,
)


def _build(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(build_plan, "_git_head", lambda: "a" * 40)
    output = tmp_path / "plan"
    build_plan.build(output)
    return output


def test_builder_and_independent_validator_freeze_candidate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert tuple(build_plan.SOURCE_PATHS) == validate_plan.REQUIRED_BOUND_SOURCES
    output = _build(tmp_path, monkeypatch)
    manifest = json.loads((output / "plan_manifest.json").read_text())
    core = dict(manifest)
    supplied = core.pop("plan_manifest_sha256")
    assert supplied == protocol.canonical_sha256(core)
    assert manifest["status"] == "prospectively_frozen_exploratory_plan"
    assert manifest["execution_authorized"] is False
    assert manifest["runner_implemented_in_frozen_closure"] is True
    assert manifest["audit_implemented_in_frozen_closure"] is True
    assert manifest["paper_prompt_render_count"] == 0
    assert manifest["target_prompt_render_count"] == 0
    assert manifest["target_feature_vector_count"] == 0
    assert manifest["analysis_data_inputs"] == []
    assert manifest["zero_baseline_continuation_count"] == 8
    assert manifest["nonzero_dose_magnitude_count"] == 60
    assert manifest["signed_pair_count"] == 1_440
    assert manifest["signed_edited_forward_count"] == 2_880
    assert manifest["exact_model_forward_count"] == 2_896
    assert manifest["reference_online_j_dose_basis_points"] == 300

    receipt = validate_plan.validate(output)
    assert receipt["status"] == "pass_prospectively_frozen_exploratory_plan"
    assert receipt["execution_authorized"] is False
    assert receipt["nonzero_dose_magnitude_count"] == 60
    assert receipt["signed_pair_count"] == 1_440
    assert receipt["reconstructed_edited_forward_count"] == 2_880
    assert receipt["reconstructed_model_forward_count"] == 2_896
    assert receipt["zero_baseline_continuation_count"] == 8
    assert receipt["source_file_count"] == len(validate_plan.REQUIRED_BOUND_SOURCES)
    assert receipt["prompt_payloads_sha256"] == (
        validate_plan.EXPECTED_PROMPT_PAYLOADS_SHA256
    )
    assert receipt["frozen_protocol_objects_sha256"] == (
        validate_plan.EXPECTED_FROZEN_OBJECT_SHA256
    )
    assert len(receipt["receipt_sha256"]) == 64


def test_plan_rows_are_canonical_complete_unique_and_have_no_zero(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output = _build(tmp_path, monkeypatch)
    source = (output / "dose_scan_plan.jsonl").read_bytes()
    assert source.endswith(b"\n")
    rows = [json.loads(line) for line in source.splitlines()]
    assert len(rows) == 1_440
    assert len({
        (row["prompt_id"], row["direction"], row["dose_basis_points"])
        for row in rows
    }) == 1_440
    assert not any(row["dose_basis_points"] == 0 for row in rows)
    assert sorted({row["dose_basis_points"] for row in rows}) == list(
        range(50, 3_001, 50)
    )
    assert rows == list(protocol.rows())


def test_validator_detects_plan_tampering(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output = _build(tmp_path, monkeypatch)
    path = output / "dose_scan_plan.jsonl"
    payload = bytearray(path.read_bytes())
    payload[0] ^= 1
    path.write_bytes(payload)
    with pytest.raises(validate_plan.IndependentPlanAuditError):
        validate_plan.validate(output)


def test_independent_validator_rejects_runtime_prompt_substitution(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    prompts = list(protocol.PROMPTS)
    prompt_id, original = prompts[0]
    prompts[0] = (prompt_id, original + " Substituted after protocol review.")
    monkeypatch.setattr(protocol, "PROMPTS", tuple(prompts))
    output = _build(tmp_path, monkeypatch)
    with pytest.raises(
        validate_plan.IndependentPlanAuditError, match="prompt/direction"
    ):
        validate_plan.validate(output)


def test_builder_is_create_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output = _build(tmp_path, monkeypatch)
    with pytest.raises(FileExistsError):
        build_plan.build(output)


def test_production_entry_points_reject_moved_plan(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(build_plan, "_git_head", lambda: "a" * 40)
    moved = tmp_path / "moved"
    with pytest.raises(ValueError, match="canonical"):
        build_plan.build(moved, enforce_canonical_path=True)
    build_plan.build(moved)
    with pytest.raises(validate_plan.IndependentPlanAuditError, match="canonical"):
        validate_plan.validate(moved, enforce_canonical_path=True)

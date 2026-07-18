from __future__ import annotations

import json
import sys
import types
from pathlib import Path
from typing import Any

import pytest

from experiments.consciousness_sae_target_blind_calibration import audit
from experiments.consciousness_sae_target_blind_calibration import audit_recovery
from experiments.consciousness_sae_target_blind_calibration import audit_runtime_shim
from experiments.consciousness_sae_target_blind_calibration import protocol
from experiments.consciousness_sae_target_blind_calibration import (
    scientific_equivalence as equivalence,
)
from experiments.consciousness_sae_realization_validation import runtime


JSON_APPENDIX = (
    equivalence.REPO_ROOT / "docs/consciousness_sae_target_blind_calibration/"
    "AUDIT_RECOVERY_SCIENTIFIC_EQUIVALENCE.json"
)
MARKDOWN_APPENDIX = JSON_APPENDIX.with_suffix(".md")


class _Watchdog:
    def __init__(self) -> None:
        self.check_count = 0

    def check(self) -> None:
        self.check_count += 1


class _FakeByteView:
    def __init__(self, payload: bytes) -> None:
        self.payload = payload

    def reshape(self, _size: int) -> _FakeByteView:
        return self

    def numel(self) -> int:
        return len(self.payload)

    def __getitem__(self, item: slice) -> _FakeByteView:
        return _FakeByteView(self.payload[item])

    def numpy(self) -> _FakeByteView:
        return self

    def tobytes(self) -> bytes:
        return self.payload


class _FakeTensor:
    dtype = "torch.bfloat16"
    shape = (2, 2)

    def __init__(self, payload: bytes) -> None:
        self.payload = payload

    def detach(self) -> _FakeTensor:
        return self

    def contiguous(self) -> _FakeTensor:
        return self

    def to(self, *, device: str) -> _FakeTensor:
        assert device == "cpu"
        return self

    def view(self, dtype: object) -> _FakeByteView:
        assert dtype == "fake_uint8"
        return _FakeByteView(self.payload)


def _synthetic_output_pair() -> tuple[dict[str, Any], dict[str, Any]]:
    audit_receipt = {
        name: {"synthetic_scientific_sentinel": name}
        for name in equivalence.SCIENTIFIC_AUDIT_FIELDS
    }
    audit_receipt.update(
        {
            "campaign_started_at_unix": 1784074604.0,
            "campaign_deadline_at_unix": 1784080004.0,
            "hourly_price_usd": 6.0,
            "raw_run_receipt_sha256": "a" * 64,
            "receipt_sha256": "b" * 64,
        }
    )
    summary = {
        name: {"synthetic_scientific_sentinel": name}
        for name in equivalence.SCIENTIFIC_SUMMARY_FIELDS
    }
    summary.update(
        {
            "audit_receipt_sha256": "b" * 64,
            "raw_run_receipt_sha256": "a" * 64,
            "receipt_sha256": "c" * 64,
        }
    )
    return audit_receipt, summary


def _synthetic_artifact_recomputation(
    checkpoint_path: Path, j_metadata: dict[str, Any]
) -> dict[str, Any]:
    """Mirror the frozen artifact receipt shape without opening outcomes."""

    return {
        "status": "pass",
        "orientation_status": "pass",
        "gpu_required": True,
        "device": "cuda:0",
        "model": {"synthetic_model_binding": "same"},
        "j_lens": {**j_metadata, "path": checkpoint_path.as_posix()},
        "orientation_row_count": 68,
        "j_shadow_pair_count": 120,
        "transport_prediction_count": 4_872,
        "predicted_selected_logit_count": 4_872,
        "actual_selected_logit_count": 24,
        "exact_tensor_equality_required": True,
    }


def test_checked_in_equivalence_appendix_is_current_and_self_hashed() -> None:
    packet = equivalence.build_packet()
    checked_in = json.loads(JSON_APPENDIX.read_text(encoding="utf-8"))
    assert checked_in == packet
    core = dict(packet)
    supplied = core.pop("packet_sha256")
    assert supplied == equivalence.canonical_sha256(core)
    assert MARKDOWN_APPENDIX.read_text(encoding="utf-8") == equivalence.render_markdown(
        packet
    )
    assert packet["outcome_input_paths"] == []
    assert packet["raw_run_opened"] is False
    assert packet["compact_result_opened"] is False


def test_frozen_source_extracts_match_original_plan_bindings() -> None:
    packet = equivalence.build_packet()
    records = packet["frozen_scientific_sources"]
    bound = [row for row in records if row["frozen_plan_bound"]]
    assert {row["path"] for row in bound} == {
        "experiments/consciousness_sae_realization_validation/runtime.py",
        "experiments/consciousness_sae_target_blind_calibration/audit.py",
        "experiments/consciousness_sae_target_blind_calibration/orientation.py",
        "experiments/consciousness_sae_target_blind_calibration/validate_plan.py",
    }
    assert all(row["sha256"] == row["frozen_plan_sha256"] for row in bound)
    audit_record = next(row for row in records if row["path"].endswith("/audit.py"))
    names = {row["symbol"] for row in audit_record["symbols"]}
    assert {
        "audit",
        "_load_j_checkpoint",
        "_audit_artifact_recomputation",
        "_bootstrap",
        "_transport_summary",
        "_linearity_summary",
        "_publish_pair_atomic",
    } <= names


def test_inherited_design_manifest_is_explicit_and_outcome_blind() -> None:
    design = equivalence.build_packet()["inherited_design"]
    assert design["independent_unit"] == {
        "primary_fixed_panel_resampling_unit": "prompt_id",
        "unit_count": 8,
        "unit_ids": [f"neutral_c{index:02d}" for index in range(1, 9)],
        "population_generalization_claim": False,
        "j_lens_prompts_fitted": 125,
        "j_lens_prompts_fitted_role": (
            "public_artifact_training_metadata_not_current_study_units"
        ),
    }
    sample = design["sample_size_and_repeated_observations"]
    assert sample["signed_pairs"] == 120
    assert sample["gated_signed_pairs"] == 96
    assert sample["local_linearity_sites"] == 24
    assert sample["orientation_fixtures"] == 68
    assert sample["primary_dose_readout_rows"] == 4_872
    assert sample["new_model_forwards_in_recovery"] == 0
    assert design["bootstrap"]["resampling_unit"] == "prompt_id"
    assert design["bootstrap"]["replicates"] == 20_000
    assert design["multiplicity"]["formal_adjustment"] == (
        "none_specified_in_frozen_protocol"
    )
    assert design["multiplicity"]["across_layer_selection"] is False
    assert (
        design["power_and_generalization"]["power_changed_or_increased_by_recovery"]
        is False
    )
    assert design["missingness_and_exclusions"]["imputation"] == "none"
    assert design["stopping"]["recovery_new_observation_stopping_rule"] == (
        "not_applicable_zero_forwards"
    )
    assert design["scope"]["analysis_data_inputs"] == []
    assert design["scope"]["substantive_adequacy_revalidated_by_recovery"] is False


def test_model_free_runtime_shim_matches_both_frozen_tensor_hashes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_torch = types.SimpleNamespace(Tensor=_FakeTensor, uint8="fake_uint8")
    monkeypatch.setitem(sys.modules, "torch", fake_torch)
    tensor = _FakeTensor(bytes(range(32)))

    frozen_runtime_hash = runtime.tensor_sha256(tensor)
    frozen_audit_hash = audit._tensor_sha256(tensor)  # noqa: SLF001
    recovery_shim_hash = audit_runtime_shim.tensor_sha256(tensor)

    assert frozen_runtime_hash == frozen_audit_hash == recovery_shim_hash


def test_old_and_recovery_loaders_supply_identical_scientific_maps_on_same_fixture(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    checkpoint_path = tmp_path / "synthetic-j.pt"
    checkpoint_path.write_bytes(b"synthetic checkpoint bytes")
    required = tuple(protocol.J_LAYERS)
    required_maps = {layer: f"required-map-{layer}" for layer in required}
    release_maps = {
        layer: required_maps.get(layer, f"unused-extra-map-{layer}")
        for layer in range(79)
    }
    common = {
        "n_prompts": protocol.J_LENS_SPEC["release_config"]["prompts_fitted"],
        "d_model": protocol.WIDTH,
    }
    checkpoints = iter(
        (
            {**common, "J": required_maps},
            {**common, "J": required_maps},
            {**common, "J": release_maps},
        )
    )
    monkeypatch.setattr(
        protocol, "sha256_file", lambda _path: protocol.J_LENS_SPEC["sha256"]
    )
    fake_torch = types.SimpleNamespace(load=lambda *_args, **_kwargs: next(checkpoints))
    monkeypatch.setitem(sys.modules, "torch", fake_torch)
    watchdog = _Watchdog()

    _old_path, old_maps, old_metadata = audit._load_j_checkpoint(  # noqa: SLF001
        checkpoint_path, watchdog
    )
    audit_recovery._OBSERVED_J_INVENTORY = None  # noqa: SLF001
    _same_path, same_maps, same_metadata = (  # noqa: SLF001
        audit_recovery._load_j_checkpoint_recovery(checkpoint_path, watchdog)
    )
    _extra_path, extra_maps, extra_metadata = (  # noqa: SLF001
        audit_recovery._load_j_checkpoint_recovery(checkpoint_path, watchdog)
    )

    assert tuple(old_maps) == required
    assert tuple(same_maps) == tuple(extra_maps) == required
    assert old_maps == same_maps == extra_maps == required_maps
    assert old_metadata["sha256"] == same_metadata["sha256"]
    assert old_metadata["sha256"] == extra_metadata["sha256"]
    assert old_metadata == same_metadata == extra_metadata
    assert extra_metadata["map_count"] == len(required)
    assert audit_recovery._OBSERVED_J_INVENTORY == {  # noqa: SLF001
        "available_layers": list(range(79)),
        "required_layers": list(required),
        "unused_extra_layers": list(range(45)),
        "available_map_count": 79,
        "required_map_count": len(required),
        "inventory_sha256": protocol.canonical_sha256(list(range(79))),
    }

    # Join each loader's selected maps and emitted metadata into the projected
    # audit pair.  This catches the former 34-vs-79 map_count discrepancy and
    # proves that harmless extra maps cannot alter a metric-bearing field.
    old_audit, old_summary = _synthetic_output_pair()
    recovered_audit, recovered_summary = _synthetic_output_pair()
    old_audit["artifact_recomputation"] = _synthetic_artifact_recomputation(
        checkpoint_path, old_metadata
    )
    recovered_audit["artifact_recomputation"] = _synthetic_artifact_recomputation(
        checkpoint_path, extra_metadata
    )
    old_summary["readout_transport"] = [old_maps[layer] for layer in required]
    recovered_summary["readout_transport"] = [extra_maps[layer] for layer in required]
    assert equivalence.canonical_json_bytes(
        equivalence.extract_scientific_fields(old_audit, old_summary)
    ) == equivalence.canonical_json_bytes(
        equivalence.extract_scientific_fields(recovered_audit, recovered_summary)
    )
    assert watchdog.check_count == 6


def test_recovery_adapter_scope_and_synthetic_scientific_fields_are_identical() -> None:
    adapter = equivalence.inspect_recovery_adapter()
    assert tuple(adapter["monkeypatched_audit_attributes"]) == (
        "_AuditBudgetWatchdog",
        "_audit_external_receipt_chain",
        "_load_j_checkpoint",
    )
    assert adapter["execution_call_counts"] == {
        "_enrich_outputs": 1,
        "_publish_recovery_pair_atomic": 1,
        "audit.audit": 1,
    }

    old_audit, old_summary = _synthetic_output_pair()
    old_projection = equivalence.extract_scientific_fields(old_audit, old_summary)
    recovered_audit, recovered_summary = audit_recovery._enrich_outputs(  # noqa: SLF001
        old_audit,
        old_summary,
        authorization={
            "recovery_started_at_unix": 30.0,
            "recovery_deadline_at_unix": 40.0,
            "hourly_price_usd": 6.0,
            "max_spend_usd": 6.0,
        },
        recovery={"receipt_type": "synthetic_recovery_provenance"},
    )
    recovered_projection = equivalence.extract_scientific_fields(
        recovered_audit, recovered_summary
    )
    assert equivalence.canonical_json_bytes(old_projection) == (
        equivalence.canonical_json_bytes(recovered_projection)
    )


def test_scientific_projection_fails_closed_on_a_missing_field() -> None:
    audit_receipt, summary = _synthetic_output_pair()
    summary.pop("readout_transport")
    with pytest.raises(
        equivalence.ScientificEquivalenceError,
        match="scientific output fields are missing",
    ):
        equivalence.extract_scientific_fields(audit_receipt, summary)

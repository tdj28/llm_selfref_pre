from __future__ import annotations

import argparse
import contextlib
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from experiments.consciousness_sae_realization_validation import runtime as full_runtime
from experiments.consciousness_sae_target_blind_calibration import (
    audit,
    audit_recovery,
    audit_runtime_shim,
    protocol,
)


class _Watchdog:
    def check(self) -> None:
        return None


def _checkpoint(maps: dict) -> dict:
    return {
        "J": maps,
        "n_prompts": protocol.J_LENS_SPEC["release_config"]["prompts_fitted"],
        "d_model": protocol.WIDTH,
    }


def _install_fake_checkpoint(monkeypatch, checkpoint: dict) -> None:
    torch = pytest.importorskip("torch")
    monkeypatch.setattr(
        protocol, "sha256_file", lambda _path: protocol.J_LENS_SPEC["sha256"]
    )
    monkeypatch.setattr(torch, "load", lambda *_args, **_kwargs: checkpoint)


def test_recovery_loader_accepts_authentic_superset_and_filters_to_required(
    tmp_path: Path, monkeypatch
) -> None:
    values = {layer: object() for layer in range(79)}
    _install_fake_checkpoint(monkeypatch, _checkpoint(values))
    path = tmp_path / "j.pt"
    path.write_bytes(b"pinned")
    _path, filtered, record = audit_recovery._load_j_checkpoint_recovery(
        path, _Watchdog()
    )
    assert set(filtered) == set(protocol.J_LAYERS)
    assert all(filtered[layer] is values[layer] for layer in protocol.J_LAYERS)
    assert record["available_layers"] == list(range(79))
    assert record["required_layers"] == list(range(45, 79))
    assert record["unused_extra_layers"] == list(range(45))
    assert record["available_map_count"] == 79
    assert record["required_map_count"] == 34


@pytest.mark.parametrize("missing", [50, 78])
def test_recovery_loader_rejects_missing_required_layer(
    tmp_path: Path, monkeypatch, missing: int
) -> None:
    values = {layer: object() for layer in range(79) if layer != missing}
    _install_fake_checkpoint(monkeypatch, _checkpoint(values))
    path = tmp_path / "j.pt"
    path.write_bytes(b"pinned")
    with pytest.raises(audit.CalibrationAuditError, match="map inventory"):
        audit_recovery._load_j_checkpoint_recovery(path, _Watchdog())


def test_recovery_loader_rejects_duplicate_normalized_layer(
    tmp_path: Path, monkeypatch
) -> None:
    values = {layer: object() for layer in range(79)}
    values["50"] = object()
    _install_fake_checkpoint(monkeypatch, _checkpoint(values))
    path = tmp_path / "j.pt"
    path.write_bytes(b"pinned")
    with pytest.raises(audit.CalibrationAuditError, match="duplicated"):
        audit_recovery._load_j_checkpoint_recovery(path, _Watchdog())


@pytest.mark.parametrize("key", ["050", "5.0"])
def test_recovery_loader_rejects_noncanonical_layer_identifier(
    tmp_path: Path, monkeypatch, key
) -> None:
    values = {layer: object() for layer in range(79)}
    values[key] = object()
    _install_fake_checkpoint(monkeypatch, _checkpoint(values))
    path = tmp_path / "j.pt"
    path.write_bytes(b"pinned")
    with pytest.raises(audit.CalibrationAuditError, match="noncanonical|duplicated"):
        audit_recovery._load_j_checkpoint_recovery(path, _Watchdog())


def test_inventory_normalizer_rejects_boolean_identifier() -> None:
    with pytest.raises(audit.CalibrationAuditError, match="noncanonical"):
        audit_recovery._normalize_j_inventory({True: object()})


def test_recovery_loader_rejects_wrong_metadata(tmp_path: Path, monkeypatch) -> None:
    checkpoint = _checkpoint({layer: object() for layer in range(79)})
    checkpoint["n_prompts"] = 124
    _install_fake_checkpoint(monkeypatch, checkpoint)
    path = tmp_path / "j.pt"
    path.write_bytes(b"pinned")
    with pytest.raises(audit.CalibrationAuditError, match="metadata"):
        audit_recovery._load_j_checkpoint_recovery(path, _Watchdog())


def test_recovery_loader_rejects_wrong_physical_hash(
    tmp_path: Path, monkeypatch
) -> None:
    pytest.importorskip("torch")
    monkeypatch.setattr(protocol, "sha256_file", lambda _path: "0" * 64)
    path = tmp_path / "j.pt"
    path.write_bytes(b"wrong")
    with pytest.raises(audit.CalibrationAuditError, match="hash"):
        audit_recovery._load_j_checkpoint_recovery(path, _Watchdog())


def test_zero_forward_guard_blocks_and_restores_torch_module_calls() -> None:
    torch = pytest.importorskip("torch")
    transformers = pytest.importorskip("transformers")
    layer = torch.nn.Linear(2, 2)
    with audit_recovery._zero_forward_guards() as counts:
        with pytest.raises(audit_recovery.AuditRecoveryError, match="Module call"):
            layer(torch.ones(2))
        assert counts["torch_module_calls"] == 1
        with pytest.raises(audit_recovery.AuditRecoveryError, match="model load"):
            transformers.PreTrainedModel.from_pretrained("forbidden")
        with pytest.raises(audit_recovery.AuditRecoveryError, match="model load"):
            transformers.AutoModelForSequenceClassification.from_pretrained("forbidden")
        assert counts["transformers_model_load_calls"] == 2
    assert tuple(layer(torch.ones(2)).shape) == (2,)


def test_audit_runtime_shim_is_byte_equivalent_to_frozen_tensor_hasher() -> None:
    torch = pytest.importorskip("torch")
    values = torch.arange(42, dtype=torch.float32).reshape(6, 7).T[1:]
    for value in (values, values.to(torch.bfloat16), values.to(torch.int64)):
        assert audit_runtime_shim.tensor_sha256(value) == full_runtime.tensor_sha256(
            value
        )


def test_mountinfo_parser_and_bind_provenance() -> None:
    relative = audit_recovery.RAW_RELATIVE
    text = "\n".join(
        [
            "10 1 0:42 / /workspace rw,relatime - ext4 /dev/volume rw",
            f"11 10 0:42 /{relative} /workspace/{relative} ro,relatime - "
            "ext4 /dev/volume rw",
        ]
    )
    workspace, target = audit_recovery._mountinfo_rows(text)
    assert (
        audit_recovery._validate_bind_provenance(
            target, workspace, f"/workspace/{relative}"
        )
        == f"/{relative}"
    )
    target["device"] = "0:99"
    with pytest.raises(audit_recovery.AuditRecoveryError, match="not a bind"):
        audit_recovery._validate_bind_provenance(
            target, workspace, f"/workspace/{relative}"
        )


def _execution_args(commit: str, stamp: str = "20260715T010203Z") -> argparse.Namespace:
    attempt_id = f"calv2-r3-audit-recovery-{commit[:7]}-{stamp}"
    root = Path(audit_recovery.RECOVERY_ATTEMPT_PARENT) / attempt_id
    original = root / "evidence/original"
    fresh = root / "evidence/fresh"
    return argparse.Namespace(
        attempt_id=attempt_id,
        provenance_root=root / "provenance_repo",
        plan_dir=(root / "provenance_repo" / protocol.CANONICAL_PLAN_RELATIVE_PATH),
        raw_root=Path("/workspace") / audit_recovery.RAW_RELATIVE,
        run_complete=original / "RUN_COMPLETE.json",
        raw_ledger=original / "REMOTE_RAW_SHA256SUMS.txt",
        raw_inventory=original / "REMOTE_RAW_INVENTORY.txt",
        failure_log=original / "calibration_audit_1a16572.log",
        original_ownership=original / "OWNERSHIP.json",
        original_guest=original / "GUEST_PREFLIGHT.json",
        original_cache=original / "CACHE_PREFLIGHT.json",
        original_authorization=original / "CALIBRATION_AUTHORIZATION.json",
        termination_audit=original / "TERMINATION_AUDIT.json",
        postdelete_inventory=original / "POSTDELETE_INVENTORY.json",
        frozen_termination=original / "frozen_lifecycle/TERMINATION.json",
        fresh_ownership=fresh / "OWNERSHIP.json",
        fresh_guest=fresh / "GUEST_PREFLIGHT.json",
        fresh_cache=fresh / "CACHE_PREFLIGHT.json",
        recovery_authorization=root / "RECOVERY_AUTHORIZATION.json",
        model_snapshot=Path(audit_recovery.MODEL_SNAPSHOT_PATH),
        j_lens_path=Path(audit_recovery.J_LENS_PATH),
        artifact_device="cuda:0",
        audit_out=root / "compact/CALIBRATION_AUDIT.json",
        summary_out=root / "compact/CALIBRATION_SUMMARY.json",
        attempt_marker=root / "ATTEMPT_STARTED.json",
        failure_out=root / "FAILURE.json",
    )


def test_execution_binding_is_exact_and_commit_scoped() -> None:
    commit = "a" * 40
    args = _execution_args(commit)
    binding = audit_recovery._execution_binding(
        args, git_head=commit, validate_execute_paths=True
    )
    assert binding["attempt_id"] == args.attempt_id
    assert binding["paths"]["provenance_root"] == args.provenance_root.as_posix()
    args.summary_out = args.summary_out.with_name("OTHER.json")
    with pytest.raises(audit_recovery.AuditRecoveryError, match="path binding"):
        audit_recovery._execution_binding(
            args, git_head=commit, validate_execute_paths=True
        )


def test_fresh_authority_clock_cannot_be_renewed_by_rehashing_receipt() -> None:
    created = datetime(2026, 7, 15, 1, 0, tzinfo=timezone.utc).timestamp()
    ownership = {
        "created_at": "2026-07-15T01:00:00Z",
        "terminate_after": "2026-07-15T07:00:00Z",
    }
    receipt = {
        "recovery_started_at_unix": created,
        "recovery_deadline_at_unix": created + 1800,
        "provider_deadline_at_unix": created + 21600,
        "authorized_at_utc": "2026-07-15T01:02:00Z",
    }
    audit_recovery._validate_fresh_authority_clock(
        receipt, ownership, now_unix=created + 300
    )
    tampered = dict(receipt)
    tampered["recovery_started_at_unix"] += 60
    tampered["recovery_deadline_at_unix"] += 60
    with pytest.raises(audit_recovery.AuditRecoveryError, match="ownership-bound"):
        audit_recovery._validate_fresh_authority_clock(
            tampered, ownership, now_unix=created + 300
        )


def test_provenance_tree_requires_exact_hash_bound_inventory(tmp_path: Path) -> None:
    root = tmp_path / "provenance"
    (root / "nested").mkdir(parents=True)
    first = root / "a.txt"
    second = root / "nested/b.txt"
    first.write_bytes(b"alpha")
    second.write_bytes(b"beta")
    rows = [
        {"path": "a.txt", "bytes": 5, "sha256": audit_recovery._sha256(first)},
        {
            "path": "nested/b.txt",
            "bytes": 4,
            "sha256": audit_recovery._sha256(second),
        },
    ]
    receipt = audit_recovery._validate_provenance_tree(root, rows)
    assert receipt["file_count"] == 2
    second.write_bytes(b"changed")
    with pytest.raises(audit_recovery.AuditRecoveryError, match="provenance differs"):
        audit_recovery._validate_provenance_tree(root, rows)


def test_attempt_claim_is_one_shot_and_failure_receipt_is_sealed(
    tmp_path: Path,
) -> None:
    source_hash = "a" * 64
    args = argparse.Namespace(
        attempt_marker=tmp_path / "ATTEMPT_STARTED.json",
        failure_out=tmp_path / "FAILURE.json",
        audit_out=tmp_path / "compact/CALIBRATION_AUDIT.json",
    )
    authorization = {
        "receipt_sha256": "b" * 64,
        "recovery_started_at_unix": 0.0,
        "recovery_deadline_at_unix": 4_000_000_000.0,
        "execution": {
            "attempt_id": "test-attempt",
            "attempt_root": tmp_path.as_posix(),
            "command_sha256": "c" * 64,
        },
        "recovery_bound_files": [
            {
                "path": (
                    "experiments/consciousness_sae_target_blind_calibration/"
                    "audit_recovery.py"
                ),
                "bytes": 1,
                "sha256": source_hash,
            }
        ],
    }
    marker = audit_recovery._claim_attempt(args, authorization)
    audit_recovery._write_failure_receipt(
        args, authorization, marker, RuntimeError("expected failure")
    )
    failure = json.loads(args.failure_out.read_text())
    assert failure["status"] == "failed_no_compact_success_publication"
    assert audit_recovery._self_hash(failure, "failure") == failure["receipt_sha256"]
    with pytest.raises(audit_recovery.AuditRecoveryError, match="not fresh"):
        audit_recovery._claim_attempt(args, authorization)


def test_execute_rehashes_raw_and_provenance_before_publication(
    tmp_path: Path, monkeypatch
) -> None:
    events: list[str] = []
    raw = tmp_path / "raw"
    provenance = tmp_path / "provenance"
    raw.mkdir()
    provenance.mkdir()
    run_complete = tmp_path / "RUN_COMPLETE.json"
    run_complete.write_text(
        json.dumps({"resource": {"run_completed_at_unix": 1.0}}), encoding="utf-8"
    )
    args = argparse.Namespace(
        recovery_authorization=tmp_path / "authorization.json",
        raw_root=raw,
        provenance_root=provenance,
        raw_ledger=tmp_path / "ledger.txt",
        run_complete=run_complete,
        plan_dir=provenance / protocol.CANONICAL_PLAN_RELATIVE_PATH,
        model_snapshot=Path(audit_recovery.MODEL_SNAPSHOT_PATH),
        j_lens_path=Path(audit_recovery.J_LENS_PATH),
        original_ownership=tmp_path / "old-ownership.json",
        original_guest=tmp_path / "old-guest.json",
        original_cache=tmp_path / "old-cache.json",
        original_authorization=tmp_path / "old-authorization.json",
        artifact_device="cuda:0",
        audit_out=tmp_path / "compact/CALIBRATION_AUDIT.json",
        summary_out=tmp_path / "compact/CALIBRATION_SUMMARY.json",
    )
    authorization = {
        "receipt_sha256": "a" * 64,
        "historical_provenance_files": [],
        "execution": {"attempt_id": "attempt"},
    }
    monkeypatch.setattr(audit_recovery, "_json", lambda _path: authorization)
    monkeypatch.setattr(
        audit_recovery,
        "validate_recovery_authorization",
        lambda *_args, **_kwargs: authorization,
    )
    monkeypatch.setattr(
        audit_recovery,
        "_claim_attempt",
        lambda *_args: {"receipt_sha256": "b" * 64},
    )
    monkeypatch.setattr(
        audit_recovery,
        "_verify_read_only_mount",
        lambda _path: {"receipt_sha256": "c" * 64},
    )
    monkeypatch.setattr(
        audit_recovery,
        "_verify_read_only_bind_mount",
        lambda *_args, **_kwargs: {"receipt_sha256": "d" * 64},
    )
    monkeypatch.setattr(
        audit_recovery,
        "_validate_executable_isolation",
        lambda *_args: {"receipt_sha256": "e" * 64},
    )

    def provenance_rehash(*_args) -> dict:
        events.append("provenance_rehash")
        return {"receipt_sha256": "f" * 64, "file_inventory_sha256": "1" * 64}

    def raw_rehash(*_args) -> dict:
        events.append("raw_rehash")
        return {"receipt_sha256": "0" * 64, "file_inventory_sha256": "2" * 64}

    monkeypatch.setattr(audit_recovery, "_validate_provenance_tree", provenance_rehash)
    monkeypatch.setattr(audit_recovery, "_rehash_raw_tree", raw_rehash)
    monkeypatch.setattr(
        audit_recovery,
        "_historical_provenance_context",
        lambda *_args: contextlib.nullcontext(),
    )
    monkeypatch.setattr(
        audit_recovery,
        "_patched_audit_runtime",
        lambda *_args: contextlib.nullcontext(),
    )
    monkeypatch.setattr(
        audit_recovery,
        "_forbidden_module_guard",
        lambda: contextlib.nullcontext({"forbidden_module_import_attempts": 0}),
    )
    monkeypatch.setattr(
        audit_recovery,
        "_zero_forward_guards",
        lambda: contextlib.nullcontext(
            {"torch_module_calls": 0, "transformers_model_load_calls": 0}
        ),
    )

    def metrics(*_args, **_kwargs) -> tuple[dict, dict]:
        events.append("metrics")
        return {}, {}

    monkeypatch.setattr(audit_recovery.audit, "audit", metrics)

    def metadata(**_kwargs) -> dict:
        events.append("metadata")
        return {"receipt_sha256": "3" * 64}

    monkeypatch.setattr(audit_recovery, "_recovery_metadata", metadata)
    monkeypatch.setattr(
        audit_recovery,
        "_enrich_outputs",
        lambda *_args, **_kwargs: ({}, {}),
    )

    def publish(*_args) -> Path:
        events.append("publish")
        return Path(_args[0]).parent

    monkeypatch.setattr(audit_recovery.audit, "_publish_pair_atomic", publish)
    result = audit_recovery.execute_recovery(args)
    assert result == args.audit_out.parent
    assert events == [
        "provenance_rehash",
        "raw_rehash",
        "metrics",
        "raw_rehash",
        "provenance_rehash",
        "metadata",
        "publish",
    ]


def test_real_recovery_metadata_constructor_discloses_bound_hashes(
    monkeypatch,
) -> None:
    bound_paths = {
        "docs/consciousness_sae_target_blind_calibration/AUDIT_RECOVERY_20260714.md",
        "experiments/consciousness_sae_target_blind_calibration/audit_recovery.py",
        "tests/consciousness_sae_target_blind_calibration/test_audit_recovery.py",
        "docs/consciousness_sae_target_blind_calibration/reviews/"
        "AUDIT_RECOVERY_GPT_PRO_ADJUDICATION.md",
        "docs/consciousness_sae_target_blind_calibration/reviews/"
        "audit_recovery_gpt_pro_20260714_live/response.json",
        "docs/consciousness_sae_target_blind_calibration/reviews/"
        "audit_recovery_gpt_pro_20260714_live/review_manifest.json",
    }
    rows = [
        {"path": path, "bytes": 1, "sha256": f"{index + 1:064x}"}
        for index, path in enumerate(sorted(bound_paths))
    ]
    authorization = {
        "receipt_sha256": "a" * 64,
        "review": {"provider_status": "incomplete"},
        "execution": {"attempt_id": "attempt", "command_sha256": "b" * 64},
        "recovery_bound_paths_sha256": "c" * 64,
        "plan_manifest_sha256": "d" * 64,
        "recovery_bound_files": rows,
        "original_receipts": {"ownership": "e" * 64},
        "fresh_receipts": {"ownership": "f" * 64},
        "fresh_pod_id": "pod123456",
    }
    monkeypatch.setattr(
        audit_recovery,
        "_OBSERVED_J_INVENTORY",
        {
            "available_layers": list(range(79)),
            "required_layers": list(range(45, 79)),
            "unused_extra_layers": list(range(45)),
        },
    )

    def sealed(status: str, **extra) -> dict:
        core = {"status": status, **extra}
        return {**core, "receipt_sha256": protocol.canonical_sha256(core)}

    mount = sealed("mount")
    provenance_mount = sealed("provenance_mount")
    isolation = sealed("isolation")
    provenance_pre = sealed("provenance_pre", file_inventory_sha256="5" * 64)
    provenance_post = sealed("provenance_post", file_inventory_sha256="5" * 64)
    raw_pre = sealed("raw_pre", file_inventory_sha256="8" * 64)
    raw_post = sealed("raw_post", file_inventory_sha256="8" * 64)
    receipt = audit_recovery._recovery_metadata(
        authorization=authorization,
        mount=mount,
        provenance_mount=provenance_mount,
        executable_isolation=isolation,
        provenance_pre_rehash=provenance_pre,
        provenance_post_rehash=provenance_post,
        pre_rehash=raw_pre,
        post_rehash=raw_post,
        guards={"torch_module_calls": 0, "transformers_model_load_calls": 0},
        module_guards={"forbidden_module_import_attempts": 0},
        marker={"receipt_sha256": "0" * 64},
    )
    assert receipt["historical_provenance_unchanged"] is True
    assert receipt["raw_unchanged"] is True
    assert receipt["review_adjudication_sha256"] in {row["sha256"] for row in rows}
    nested = {
        "mount_receipt": mount,
        "provenance_mount_receipt": provenance_mount,
        "executable_isolation_receipt": isolation,
        "provenance_pre_rehash_receipt": provenance_pre,
        "provenance_post_rehash_receipt": provenance_post,
        "pre_rehash_receipt": raw_pre,
        "post_rehash_receipt": raw_post,
    }
    for name, expected in nested.items():
        assert receipt[name] == expected
        assert (
            audit_recovery._self_hash(receipt[name], name)
            == receipt[f"{name.removesuffix('_receipt')}_receipt_sha256"]
        )
    assert audit_recovery._self_hash(receipt, "recovery") == receipt["receipt_sha256"]


def test_enrichment_preserves_original_clock_and_uses_fresh_publication_clock() -> None:
    audit_core = {
        "status": "pass",
        "campaign_started_at_unix": 10.0,
        "campaign_deadline_at_unix": 20.0,
        "hourly_price_usd": 6.0,
    }
    audit_receipt = {
        **audit_core,
        "receipt_sha256": protocol.canonical_sha256(audit_core),
    }
    summary_core = {
        "status": "pass",
        "audit_receipt_sha256": audit_receipt["receipt_sha256"],
    }
    summary = {
        **summary_core,
        "receipt_sha256": protocol.canonical_sha256(summary_core),
    }
    authorization = {
        "recovery_started_at_unix": 100.0,
        "recovery_deadline_at_unix": 1900.0,
        "hourly_price_usd": 6.0,
    }
    recovery = {
        "status": "pass_disclosed_post_run_technical_recovery",
        "receipt_sha256": "a" * 64,
        "correction": "required_j_layers_subset_of_hash_pinned_release_inventory",
        "provider_review_status": "incomplete",
    }
    enriched_audit, enriched_summary = audit_recovery._enrich_outputs(
        audit_receipt,
        summary,
        authorization=authorization,
        recovery=recovery,
    )
    assert (
        enriched_audit["original_execution_campaign"]["campaign_deadline_at_unix"]
        == 20.0
    )
    assert enriched_audit["campaign_started_at_unix"] == 100.0
    assert enriched_audit["campaign_deadline_at_unix"] == 1900.0
    assert enriched_summary["audit_receipt_sha256"] == enriched_audit["receipt_sha256"]
    for value in (enriched_audit, enriched_summary):
        core = dict(value)
        supplied = core.pop("receipt_sha256")
        assert supplied == protocol.canonical_sha256(core)


def test_original_r3_auditor_source_is_still_physically_frozen() -> None:
    assert (
        protocol.sha256_file(
            audit_recovery.REPO_ROOT
            / "experiments/consciousness_sae_target_blind_calibration/audit.py"
        )
        == "271f4f17a5ed66eaff43dc63f5a02d7ce45cdfd4a3c6a5b5c03bac33cf96a465"
    )

"""Post-outcome adapter tests on tiny real captures; no production data edits."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import shutil
import socket

import pytest

from experiments.sae_assay_precision import pilot
from scripts import sae_exposure_portability as portable
from tests.test_sae_assay_precision_pilot import completed, tiny


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    monkeypatch.setenv("HF_HUB_OFFLINE", "1")
    monkeypatch.setenv("TRANSFORMERS_OFFLINE", "1")
    def forbidden(*args, **kwargs):
        raise AssertionError("Portability tests cannot use network")
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)


def write(path, value):
    path.write_text(pilot.canonical(value) + "\n")


def reseal(root):
    base = root / pilot.DIRECTORY
    rows = [json.loads(path.read_text()) for path in sorted((base / "rows").glob("*.json"))]
    write(base / "summary.json", pilot.summarize(rows))
    events = [json.loads(line) for line in (base / "receipts.jsonl").read_text().splitlines()]
    previous = None
    for event in events:
        if event["data"]["kind"] == "row":
            payload = event["data"]["payload"]
            payload["sha256"] = pilot.sha(base / payload["path"])
        if event["id"] == "complete":
            event["data"]["summary_sha256"] = pilot.sha(base / "summary.json")
        event["previous_sha256"] = previous
        body = {key: value for key, value in event.items() if key != "sha256"}
        event["sha256"] = hashlib.sha256(pilot.canonical(body).encode()).hexdigest()
        previous = event["sha256"]
    (base / "receipts.jsonl").write_text("".join(pilot.canonical(event) + "\n" for event in events))


@pytest.fixture
def drifted(completed, tmp_path, monkeypatch):
    source, plan, *_ = completed
    root = tmp_path / "raw"
    shutil.copytree(source, root)
    for ordinal in range(8, 48):
        path = root / pilot.DIRECTORY / f"rows/{ordinal:03d}.json"
        row = json.loads(path.read_text())
        row["delivery"]["clean_norm"][1] += 5e-13
        write(path, row)
    reseal(root)
    # Only production provenance is stubbed for this separately marked tiny
    # test plan. The actual frozen full validator and CPU oracle are untouched.
    monkeypatch.setattr(portable, "_authenticate", lambda *_: {"synthetic_fixture": True})
    return root, plan


def audit(root, plan, destination, **kwargs):
    return portable.validate_run(root, plan, pilot._hash(plan), "a" * 40, audit_path=destination, **kwargs)


def test_frozen_full_validator_with_float_only_adapter_and_deterministic_proof(drifted, tmp_path):
    root, plan = drifted
    original_validator, original_metrics = pilot.validate_run, pilot._metrics
    before = portable._inventory(root)
    with pytest.raises(ValueError, match=portable.EXACT_ERROR):
        pilot.validate_run(root, plan, pilot._hash(plan), "a" * 40)
    prior = tmp_path / "exact-failed.json"
    write(prior, {"plan_sha256": pilot._hash(plan), "freeze_commit": "a" * 40,
                  "pilot_exact_audit_pass": False, "error_type": "ValueError", "error_message": portable.EXACT_ERROR})
    prior_hash = pilot.sha(prior)
    first, second = tmp_path / "first.json", tmp_path / "second.json"
    result = audit(root, plan, first, prior_exact_audit=prior)
    assert result == {"structural_pass": True, "row_count": 48, "scope": pilot.SCOPE}
    assert audit(root, plan, second, prior_exact_audit=prior) == result
    assert first.read_bytes() == second.read_bytes()
    report = json.loads(first.read_text())
    assert report["portability_pass"] and report["post_outcome"]
    assert report["original_exact_audit"]["status"] == "fail"
    assert report["original_exact_audit"]["error_message"] == portable.EXACT_ERROR
    assert report["rows_checked"] == 48 and report["rows_with_differences"] == 40
    assert len(report["differences"]) == 40
    assert report["metric_differences"]["clean_norm"]["max_absolute_difference"] <= 1e-12
    assert report["exact_per_position_classifications"] and report["exact_recomputed_frozen_summary"]
    assert portable._inventory(root) == before and pilot.sha(prior) == prior_hash
    assert pilot.validate_run is original_validator and pilot._metrics is original_metrics
    with pytest.raises(ValueError, match=portable.EXACT_ERROR):
        pilot.validate_run(root, plan, pilot._hash(plan), "a" * 40)


def delivery():
    return {"requested_norm": [1.], "realized_norm": [1.], "clean_norm": [100.],
            "cosine": [1.], "relative_error": [0.], "realized_clean_ratio": [.01],
            "nonzero_requested": [True], "identity": [False]}


@pytest.mark.parametrize("key,value", [("identity", True), ("nonzero_requested", 1),
    ("requested_norm", 1), ("clean_norm", float("nan")), ("clean_norm", float("inf")),
    ("cosine", .999), ("relative_error", 1e-5)])
def test_no_tolerance_for_types_booleans_nonfinite_or_large_numeric_differences(key, value):
    recorded, actual = delivery(), delivery()
    actual[key][0] = value
    with pytest.raises(portable.PortabilityError):
        portable.compare_delivery(actual, recorded, [False])


def test_integers_exact_and_schema_fixed():
    recorded, actual = delivery(), delivery()
    recorded["clean_norm"], actual["clean_norm"] = [10**15], [10**15 + 1]
    with pytest.raises(portable.PortabilityError, match="integer"):
        portable.compare_delivery(actual, recorded, [False])
    actual = delivery()
    actual["unreviewed_metric"] = [0.]
    with pytest.raises(portable.PortabilityError, match="schema"):
        portable.compare_delivery(actual, delivery(), [False])


@pytest.mark.parametrize("key,left,right", [("cosine", .95 - 1e-14, .95),
    ("relative_error", .20 + 1e-14, .20), ("realized_clean_ratio", .05 + 1e-14, .05),
    ("realized_norm", 1e-15, 0.)])
def test_within_tolerance_threshold_or_denominator_flip_is_still_rejected(key, left, right):
    actual, recorded = delivery(), delivery()
    actual[key][0], recorded[key][0] = left, right
    with pytest.raises(portable.PortabilityError, match="threshold-or-denominator"):
        portable.compare_delivery(actual, recorded, [False])


@pytest.mark.parametrize("artifact", ["capture", "summary", "pairing", "identity", "ledger"])
def test_any_other_frozen_validation_failure_remains_blocking_and_restores_metrics(drifted, tmp_path, artifact):
    root, plan = drifted
    base = root / pilot.DIRECTORY
    if artifact == "capture":
        path = base / "tensors/047.safetensors"
        path.write_bytes(path.read_bytes() + b"corrupt")
    elif artifact == "summary":
        write(base / "summary.json", {"incorrect": True})
    elif artifact == "ledger":
        path = base / "receipts.jsonl"
        path.write_bytes(path.read_bytes()[:-3])
    else:
        path = base / "rows/046.json"
        row = json.loads(path.read_text())
        if artifact == "pairing":
            row["clean_exposure"]["row_sha256"] = "a" * 64
        else:
            row["delivery"]["identity"][1] = not row["delivery"]["identity"][1]
        write(path, row)
        reseal(root)
    destination = tmp_path / "failed-portability.json"
    with pytest.raises((ValueError, KeyError)):
        audit(root, plan, destination)
    assert not json.loads(destination.read_text())["portability_pass"]
    assert pilot._metrics is portable._FROZEN_METRICS
    assert pilot.validate_run is portable._FROZEN_VALIDATE


def test_explicit_publication_adapter_returns_original_result_and_restores_on_exception(drifted, tmp_path):
    root, plan = drifted
    with portable.publication_adapter(tmp_path / "proofs") as receipts:
        result = pilot.validate_run(root, plan, pilot._hash(plan), "a" * 40)
        assert set(result) == {"structural_pass", "row_count", "scope"}
        assert pilot._metrics is portable._FROZEN_METRICS
    assert len(receipts) == 1 and json.loads(receipts[0].read_text())["portability_pass"]
    assert pilot.validate_run is portable._FROZEN_VALIDATE
    with pytest.raises(RuntimeError, match="caller failed"):
        with portable.publication_adapter(tmp_path / "caller-failure"):
            raise RuntimeError("caller failed")
    assert pilot.validate_run is portable._FROZEN_VALIDATE


def test_swallowed_invalid_audit_does_not_make_context_successful(drifted, tmp_path):
    root, plan = drifted
    (root / pilot.DIRECTORY / "summary.json").write_text("{}")
    with pytest.raises(portable.PortabilityError, match="failed-calls"):
        with portable.publication_adapter(tmp_path / "failed-proof"):
            try:
                pilot.validate_run(root, plan, pilot._hash(plan), "a" * 40)
            except ValueError:
                pass
    assert pilot.validate_run is portable._FROZEN_VALIDATE
    assert pilot._metrics is portable._FROZEN_METRICS


def test_never_overwrites_raw_or_prior_provenance(drifted, tmp_path):
    root, plan = drifted
    with pytest.raises(portable.PortabilityError, match="outside-raw-run"):
        audit(root, plan, root / "unexpected.json")
    assert not (root / "unexpected.json").exists()
    with pytest.raises(portable.PortabilityError, match="outside-raw-run"):
        with portable.publication_adapter(root / "unexpected-proofs"):
            pilot.validate_run(root, plan, pilot._hash(plan), "a" * 40)
    assert not (root / "unexpected-proofs").exists()
    path = tmp_path / "existing.json"
    path.write_text("preserve me")
    with pytest.raises(FileExistsError):
        audit(root, plan, path)
    assert path.read_text() == "preserve me"


def test_wrong_plan_or_execution_freeze_cannot_be_adapted():
    with pytest.raises(portable.PortabilityError, match="unrecognized"):
        portable._authenticate({}, "a" * 64, portable.FREEZE)

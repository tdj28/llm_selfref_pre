"""Offline publication fixtures; no live outcomes, providers or GPU calls."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import hashlib
import json
from pathlib import Path

import pytest

from experiments.sae_assay_diagnostic.budget import EventLedger, PodRegistry
from experiments.steering_fidelity_repair import analysis, liveness
from scripts import release_fidelity_repair as r
from tests import test_fidelity_repair_audit as fixtures


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(r._canonical(value) + b"\n")


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def fail(*args, **kwargs):
        raise AssertionError("Release tests forbid network access")
    monkeypatch.setattr("urllib.request.OpenerDirector.open", fail)
    monkeypatch.setattr("socket.socket.connect", fail)


@pytest.fixture
def rig(tmp_path, monkeypatch):
    root = tmp_path.resolve()
    base = root / "campaign"
    base.mkdir()
    monkeypatch.setattr(fixtures, "PLAN_HASH", r.PLAN_SHA256)
    monkeypatch.setattr(fixtures, "FREEZE", r.FREEZE)
    for module in (analysis, liveness):
        monkeypatch.setattr(module, "BOOTSTRAP_DRAWS", 20)
    plan = {**fixtures.plan_fixture(), "budget": deepcopy(r.c.BUDGET)}
    monkeypatch.setattr(r, "verify_sources", lambda: plan)
    campaign = EventLedger(base / "budget.jsonl", r.PLAN_SHA256, r.FREEZE, [])
    campaign.bind("budget", plan["budget"])
    state = {"prior": Decimal(0), "cheap": None, "number": 0}

    def raw(kind, number=1):
        path = base / f"{kind}-{number:03d}" / "retrievals" / "final"
        path.mkdir(parents=True)
        (path / "controller.log").write_text("Synthetic offline worker log.\n")
        (path / "pip-freeze.txt").write_text("pytest==8.4.2\n")
        write(path / "controller-exit.json", {"exit_code": 0})
        if kind == "cheap":
            write(path / "DONE-all.json", {"pass": True, "scope": "tiny_cuda_exact_path"})
            (path / "tests.xml").write_text('<testsuites><testsuite tests="312" failures="0" errors="0" skipped="0"/></testsuites>')
        return path

    def seal(path, *, config_changes=None, intent_changes=None, closed_changes=None,
             projection_changes=None, no_worker=False, earlier=None, blocked=None, seconds=60):
        directory = path.parent.parent
        kind, number = directory.name.split("-")
        limit = 1800 if kind == "cheap" else 4800
        started = datetime(2026, 10, 3, tzinfo=timezone.utc) + timedelta(minutes=state["number"] * 2)
        state["number"] += 1
        pod = {"id": "synthetic-owned-" + directory.name,
               "name": "codex-" + r.NAMESPACE + "-" + kind + "-123456789abc",
               "createdAt": started.isoformat(), "cost": ".74" if kind == "cheap" else "6.79",
               "ssh": {"direct": "192.0.2.1"}}
        blocked = ["synthetic-foreign-resource"] if blocked is None else blocked
        ledger = EventLedger(directory / "events.jsonl", r.PLAN_SHA256, r.FREEZE, [])
        ledger.bind("controller:config", {"kind": kind, "attempt": int(number), "namespace": r.NAMESPACE,
            "plan_path": r.PLAN_PATH, "budget": deepcopy(plan["budget"]),
            "hard_seconds": limit, "retrieval_seconds": 600, **(config_changes or {})})
        authority = ledger.bind("creation-approval", {
            **r.c.approval_record(r.PLAN_SHA256, r.FREEZE, plan["budget"], "synthetic-user-request",
                                 kind=kind, attempt=int(number)), "approval_file_sha256": "b" * 64})
        reservation = campaign.bind("attempt:" + directory.name, {"prior_gpu_usd": str(state["prior"]),
            "projection": {**r.c.budget_projection("10"), **(projection_changes or {})},
            "approval_sha256": authority["sha256"]})
        ledger.bind("create-intent", {"payload": {"name": pod["name"]}, "blocked": blocked,
            "plan_sha256": r.PLAN_SHA256, "freeze_commit": r.FREEZE,
            "prior_new_usd": str(state["prior"]), "prior_total_usd": "9.657774",
            "approval_sha256": authority["sha256"], "campaign_reservation_sha256": reservation["sha256"],
            "quote": {"hourly_rate_usd": pod["cost"], "storage_hourly_usd": ".10"},
            "ci": {"pass": True, "freeze_commit": r.FREEZE, "run_id": 42, "jobs": 15},
            "created_utc": started.isoformat(),
            "deadline_utc": (started + timedelta(seconds=limit - 600)).isoformat(),
            "hard_deadline_utc": (started + timedelta(seconds=limit)).isoformat(),
            "cheap_receipt_sha256": state["cheap"], **(intent_changes or {})})
        created = ledger.bind("created", pod)
        registry = PodRegistry(ledger, blocked)
        final = directory / "final-retrieval.json"
        registry.register_created(pod["id"], created["sha256"], [str(final)])
        if not no_worker:
            ledger.bind("worker-intent", {"worker_id": "c" * 32, "pod_id": pod["id"],
                "plan_sha256": r.PLAN_SHA256, "freeze_commit": r.FREEZE})
        if earlier:
            ledger.bind("retrieval:earlier", {"pod_id": pod["id"], "directory": str(earlier),
                "artifacts": {n: r.sha(p) for n, p in r._files(earlier).items()}})
        data = {"pod_id": pod["id"], "directory": str(path),
                "artifacts": {n: r.sha(p) for n, p in r._files(path).items()}}
        if no_worker:
            data = {"pod_id": pod["id"], "no_worker_dispatched": True, "artifacts": {}}
        receipt = ledger.bind("retrieval:final", data)
        write(final, receipt)
        permit = registry.authorize_delete(pod["id"], {str(final): r.sha(final)})
        ledger.bind("delete-intent", {"pod_id": pod["id"], "pod": pod, "permit_sha256": permit["sha256"]})
        ledger.bind("delete-response", {"status": 204, "pod_id": pod["id"]})
        cost = Decimal(seconds) * (Decimal(pod["cost"]) + Decimal(".10")) / 3600
        cumulative = state["prior"] + cost
        ledger.bind("closed", {"pod_id": pod["id"], "get_status": 404, "inventory_ids": blocked,
            "utc": (started + timedelta(seconds=seconds)).isoformat(), "elapsed_seconds": str(seconds),
            "within_limits": seconds <= limit and r.c.budget_projection(cumulative)["pass"],
            "compute_upper_bound_usd": str(cost),
            "cumulative_gpu_upper_bound_usd": str(cumulative), "prior_total_usd": "9.657774",
            "new_all_in_upper_bound_usd": str(cumulative + 3),
            "all_in_upper_bound_usd": str(Decimal("9.657774") + cumulative + 3), **(closed_changes or {})})
        state["prior"] = cumulative
        if kind == "cheap":
            state["cheap"] = receipt["sha256"]
        return ledger

    def cheap(**kwargs):
        path = raw("cheap")
        seal(path, **kwargs)
        return path

    def main(*, complete=True, selected=None, singleton=False, invalid=False):
        path = raw("main")
        window = fixtures.Window(path, selected=selected, singleton_pass=singleton)
        if complete:
            window.run()
            report = window.audit(False)
            decisions = {name: r._json(path / (name + "-decision.json"))["decision"]
                         for name in ("validation", "singleton", "liveness")}
            write(path / "audit.json", report)
            write(path / "complete.json", {"pass": True,
                "meaning": "conditional_inventory_complete_not_scientific_gate",
                "forwards": report["forwards"], "plan_sha256": r.PLAN_SHA256, "freeze_commit": r.FREEZE,
                "pressure_pass": decisions["validation"]["pass"], "singleton_pass": decisions["singleton"]["pass"],
                "liveness_pass": decisions["liveness"]["pass"], "stage_t_authorized": False, "e_only_fallback": False})
            write(path / "qualification.json", {"pass": True})
            write(path / "model.json", {"synthetic": True})
        else:
            window.collect(plan["discovery_rows"][:5])
            if invalid:
                row_path = next((path / "forwards").glob("*.json"))
                row = r._json(row_path)
                row["p_correct"] = .001
                write(row_path, row)
            write(path / "failed.json", {"type": "TimeoutError", "message": "Synthetic deadline failure"})
            write(path / "controller-exit.json", {"exit_code": 1})
        return path, window

    return type("Rig", (), {"base": base, "dest": root / "public", "plan": plan,
        "raw": staticmethod(raw), "seal": staticmethod(seal), "cheap": staticmethod(cheap),
        "main": staticmethod(main), "state": state, "campaign": campaign})()


@pytest.mark.parametrize("selected,singleton,count", [(None, False, 368), ("P0", False, 448), ("P0", True, 520)])
def test_complete_conditional_inventory_is_not_a_scientific_pass(rig, selected, singleton, count):
    cheap = rig.cheap()
    raw, _ = rig.main(selected=selected, singleton=singleton)
    rig.seal(raw)
    before = {n: p.read_bytes() for n, p in r._files(rig.base).items()}
    inspected = r.inspect_release(rig.base)
    assert not rig.dest.exists()
    assert inspected["status"] == "complete" and inspected["raw_audit"]["forwards"] == count
    assert inspected["scientific_gate_evaluated"] is False and inspected["stage_t_authorized"] is False
    assert r._json(raw / "validation-decision.json")["decision"]["pass"] is (selected is not None)
    assert r._json(raw / "singleton-decision.json")["decision"]["pass"] is singleton
    manifest = r.copy_release(rig.base, rig.dest)
    assert manifest["status"] == "complete"
    provenance = r._json(rig.dest / "retrieval_and_cost.json")
    assert provenance == inspected
    for name, path in r._files(cheap).items():
        assert (rig.dest / "cheap-001" / name).read_bytes() == path.read_bytes()
    for name, path in r._files(raw).items():
        assert (rig.dest / "main-001" / name).read_bytes() == path.read_bytes()
    assert {n: p.read_bytes() for n, p in r._files(rig.base).items()} == before
    assert {entry["path"] for entry in manifest["files"]} == set(r._files(rig.dest)) - {"RELEASE_MANIFEST.json"}
    for entry in manifest["files"]:
        path = rig.dest / entry["path"]
        assert entry["sha256"] == r.sha(path) and entry["bytes"] == path.stat().st_size
    public = b"".join(p.read_bytes() for p in r._files(rig.dest).values())
    for forbidden in (str(rig.base).encode(), b'"ssh"', b"192.0.2.1", b"synthetic-foreign-resource"):
        assert forbidden not in public
    assert b"synthetic-owned-main-001" in public


def test_main_failure_preserves_bytes_and_needs_explicit_incomplete(rig):
    rig.cheap()
    raw, _ = rig.main(complete=False)
    rig.seal(raw)
    with pytest.raises(ValueError, match="allow-incomplete"):
        r.copy_release(rig.base, rig.dest)
    assert not rig.dest.exists()
    result = r.inspect_release(rig.base, allow_incomplete=True)
    assert result["status"] == "incomplete" and result["raw_audit"]["pass"]
    assert not result["raw_audit"]["complete"] and result["raw_audit"]["forwards"] == 5
    r.copy_release(rig.base, rig.dest, allow_incomplete=True)
    assert (rig.dest / "main-001/failed.json").read_bytes() == (raw / "failed.json").read_bytes()
    assert not (rig.dest / "main-001/complete.json").exists()
    assert len(list((rig.dest / "main-001/forwards").glob("*.json"))) == 5


def test_invalid_scientific_payload_is_explicit_failed_evidence(rig):
    rig.cheap()
    raw, _ = rig.main(complete=False, invalid=True)
    rig.seal(raw)
    result = r.inspect_release(rig.base, allow_incomplete=True)
    assert result["status"] == "incomplete"
    assert result["raw_audit"] == {"status": "failed", "pass": False, "complete": False, "error_type": "ValueError"}


def test_unresolved_forward_is_not_manufactured(rig):
    rig.cheap()
    raw, window = rig.main(complete=False)
    identifier = rig.plan["discovery_rows"][5]["id"]
    window.event("dispatch", identifier)
    rig.seal(raw)
    result = r.inspect_release(rig.base, allow_incomplete=True)
    assert result["raw_audit"]["unresolved_forward_ids"] == [identifier]
    assert result["raw_audit"]["pass"] is False
    r.copy_release(rig.base, rig.dest, allow_incomplete=True)
    assert not (rig.dest / "main-001/forwards" / (identifier + ".json")).exists()


def test_cheap_only_failure_does_not_invent_main(rig):
    path = rig.raw("cheap")
    (path / "DONE-all.json").unlink()
    write(path / "controller-exit.json", {"exit_code": 1})
    rig.seal(path)
    result = r.inspect_release(rig.base, allow_incomplete=True)
    assert result["raw_audit"]["status"] == "not_started"
    assert len(result["attempts"]) == 1 and not result["attempts"][0]["cheap_tests_pass"]
    r.copy_release(rig.base, rig.dest, allow_incomplete=True)
    assert not (rig.dest / "main-001").exists()


def test_prior_is_carried_once_and_new_cap_is_independent(rig):
    rig.cheap()
    raw, _ = rig.main(complete=False)
    rig.seal(raw)
    result = r.inspect_release(rig.base, allow_incomplete=True)
    cost = result["cost"]
    assert Decimal(cost["projected_gpu_usd"]) == rig.state["prior"]
    assert Decimal(cost["projected_new_usd"]) == rig.state["prior"] + 3
    assert Decimal(cost["projected_all_in_usd"]) == Decimal("9.657774") + rig.state["prior"] + 3
    assert cost["pass"] is True


@pytest.mark.parametrize("change", [{"prior_total_usd": "0"}, {"all_in_upper_bound_usd": "3"},
    {"new_all_in_upper_bound_usd": "12.657774"}, {"compute_upper_bound_usd": "0"},
    {"cumulative_gpu_upper_bound_usd": "0"}, {"elapsed_seconds": "1"}, {"within_limits": False},
    {"compute_upper_bound_usd": None}])
def test_self_consistent_ledger_cannot_forge_cost_semantics(rig, change):
    rig.cheap(closed_changes=change)
    with pytest.raises(ValueError):
        r.inspect_release(rig.base, allow_incomplete=True)


@pytest.mark.parametrize("change", [{"get_status": 200}, {"get_status": True},
    {"pod_id": "not-ours"}, {"inventory_ids": ["synthetic-owned-cheap-001"]}])
def test_exact_deletion_receipt_required(rig, change):
    rig.cheap(closed_changes=change)
    with pytest.raises(ValueError, match="Closure"):
        r.inspect_release(rig.base, allow_incomplete=True)


@pytest.mark.parametrize("change", [{"ci": {"pass": True, "freeze_commit": "a" * 40, "run_id": 42, "jobs": 15}},
    {"ci": {"pass": False, "freeze_commit": r.FREEZE, "run_id": 42, "jobs": 15}},
    {"campaign_reservation_sha256": "f" * 64}, {"freeze_commit": "f" * 40},
    {"prior_new_usd": "9.657774"}, {"hard_deadline_utc": "2026-10-04T00:00:00+00:00"}])
def test_chain_binding_ci_and_deadline_cannot_be_forged(rig, change):
    rig.cheap(intent_changes=change)
    with pytest.raises(ValueError):
        r.inspect_release(rig.base, allow_incomplete=True)


def test_main_requires_latest_exact_passed_cheap_receipt(rig):
    rig.cheap()
    raw, _ = rig.main(complete=False)
    rig.seal(raw, intent_changes={"cheap_receipt_sha256": "f" * 64})
    with pytest.raises(ValueError, match="passing closed cheap"):
        r.inspect_release(rig.base, allow_incomplete=True)


@pytest.mark.parametrize("mutation", ["skipped", "failed", "missinglog"])
def test_failed_or_incomplete_cheap_cannot_qualify_main(rig, mutation):
    cheap = rig.raw("cheap")
    if mutation == "missinglog":
        (cheap / "controller.log").unlink()
    else:
        (cheap / "tests.xml").write_text('<testsuite tests="312" failures="%d" errors="0" skipped="%d"/>' % (
            int(mutation == "failed"), int(mutation == "skipped")))
    rig.seal(cheap)
    raw, _ = rig.main(complete=False)
    rig.seal(raw)
    with pytest.raises(ValueError):
        r.inspect_release(rig.base, allow_incomplete=True)


@pytest.mark.parametrize("filename,payload", [
    ("weights.safetensors", b"not permitted"), (".env", b"not permitted"),
    ("controller.log", b"address 192.0.2.1"), ("controller.log", b"ssh connection details"),
    ("controller.log", b"synthetic-foreign-resource"),
    ("controller.log", b"OPENAI_API_KEY=sk-" + b"A" * 48),
    ("failed.json", b'{"message":"synthetic-foreign-\\u0072esource"}'),
])
def test_allowlist_and_public_scans_fail_closed(rig, filename, payload):
    rig.cheap()
    raw, _ = rig.main(complete=False)
    (raw / filename).write_bytes(payload)
    if filename.startswith("."):
        with pytest.raises(ValueError):
            rig.seal(raw)
        return
    rig.seal(raw)
    with pytest.raises(ValueError):
        r.copy_release(rig.base, rig.dest, allow_incomplete=True)
    assert not rig.dest.exists()


def test_post_retrieval_hash_change_is_not_incomplete_permission(rig):
    cheap = rig.cheap()
    (cheap / "controller.log").write_text("Changed after retrieval\n")
    with pytest.raises(ValueError, match="hash mismatch"):
        r.inspect_release(rig.base, allow_incomplete=True)


def test_inventory_addition_and_symlinks_refused(rig):
    cheap = rig.cheap()
    extra = cheap / "extra.json"
    extra.write_text("{}")
    with pytest.raises(ValueError, match="inventory"):
        r.inspect_release(rig.base, allow_incomplete=True)
    extra.unlink()
    extra.symlink_to(cheap / "controller.log")
    with pytest.raises(ValueError, match="symlink"):
        r.inspect_release(rig.base, allow_incomplete=True)


def test_post_close_journal_hash_tamper_refused(rig):
    rig.cheap()
    path = rig.base / "cheap-001/events.jsonl"
    path.write_bytes(path.read_bytes().replace(b'"get_status":404', b'"get_status":200'))
    with pytest.raises(ValueError, match="hash/sequence"):
        r.inspect_release(rig.base, allow_incomplete=True)


def test_unreserved_attempt_blocks_publication(rig):
    rig.cheap()
    (rig.base / "cheap-002").mkdir()
    with pytest.raises(ValueError, match="Unreserved"):
        r.inspect_release(rig.base, allow_incomplete=True)


def test_no_worker_evidence_cannot_hide_dispatch(rig):
    raw = rig.cheap(no_worker=True)
    with pytest.raises(ValueError, match="raw evidence omitted"):
        r.inspect_release(rig.base, allow_incomplete=True)
    assert (raw / "tests.xml").exists()


def test_no_worker_no_artifacts_is_explicit_not_started(rig):
    raw = rig.raw("cheap")
    for path in r._files(raw).values():
        path.unlink()
    rig.seal(raw, no_worker=True)
    result = r.inspect_release(rig.base, allow_incomplete=True)
    assert not result["artifacts"] and result["raw_audit"]["status"] == "not_started"


def test_accurate_over_cap_costs_require_incomplete_preservation(rig):
    rig.cheap(seconds=60000)
    with pytest.raises(ValueError, match="allow-incomplete"):
        r.copy_release(rig.base, rig.dest)
    assert not rig.dest.exists()
    result = r.inspect_release(rig.base, allow_incomplete=True)
    assert result["status"] == "incomplete" and result["operational_limits_pass"] is False
    assert result["cost"]["pass"] is False and result["attempts"][0]["within_limits"] is False
    assert Decimal(result["cost"]["projected_new_usd"]) > 15
    r.copy_release(rig.base, rig.dest, allow_incomplete=True)
    assert (rig.dest / "cheap-001/controller.log").read_bytes() == (
        rig.base / "cheap-001/retrievals/final/controller.log").read_bytes()


@pytest.mark.parametrize("seconds", [4801, 7000, 90000])
def test_main_deadline_new_cap_and_global_overruns_are_failed_evidence(rig, seconds):
    rig.cheap()
    raw, _ = rig.main(complete=False)
    rig.seal(raw, seconds=seconds)
    with pytest.raises(ValueError, match="allow-incomplete"):
        r.inspect_release(rig.base)
    result = r.inspect_release(rig.base, allow_incomplete=True)
    assert result["status"] == "incomplete" and result["operational_limits_pass"] is False
    assert result["cost"]["pass"] is (seconds == 4801)
    assert result["attempts"][-1]["within_limits"] is False
    assert result["stage_t_authorized"] is False and result["e_only_fallback"] is False
    if seconds == 90000:
        assert Decimal(result["cost"]["projected_all_in_usd"]) > 170
    r.copy_release(rig.base, rig.dest, allow_incomplete=True)
    assert (rig.dest / "main-001/failed.json").read_bytes() == (raw / "failed.json").read_bytes()


def test_false_within_limits_cannot_hide_overrun(rig):
    rig.cheap(seconds=60000, closed_changes={"within_limits": True})
    with pytest.raises(ValueError, match="Cost projection mismatch"):
        r.inspect_release(rig.base, allow_incomplete=True)


def test_complete_raw_inventory_after_deadline_still_requires_incomplete_mode(rig):
    rig.cheap()
    raw, _ = rig.main()
    rig.seal(raw, seconds=4801)
    with pytest.raises(ValueError, match="allow-incomplete"):
        r.inspect_release(rig.base)
    result = r.inspect_release(rig.base, allow_incomplete=True)
    assert result["raw_audit"]["complete"] is True and result["status"] == "incomplete"
    assert result["operational_limits_pass"] is False and result["cost"]["pass"] is True


@pytest.mark.parametrize("failure", [False, True])
def test_verified_zero_startup_snapshot_is_not_started(rig, failure):
    rig.cheap()
    raw = rig.raw("main")
    if failure:
        write(raw / "failed.json", {"type": "RuntimeError", "message": "Synthetic model setup failure",
            "completed_forwards": 0, "plan_sha256": r.PLAN_SHA256, "freeze_commit": r.FREEZE})
        write(raw / "controller-exit.json", {"exit_code": 1})
    rig.seal(raw)
    result = r.inspect_release(rig.base, allow_incomplete=True)
    expected = {"status": "not_started", "pass": None, "complete": False,
                "reason": "before_model_metadata_and_first_scientific_dispatch"}
    assert result["raw_audit"] == expected
    assert result["attempts"][-1]["snapshot_lineage"][-1]["raw_audit"] == expected
    r.copy_release(rig.base, rig.dest, allow_incomplete=True)
    assert not (rig.dest / "main-001/receipts.jsonl").exists()
    assert not (rig.dest / "main-001/model.json").exists()


@pytest.mark.parametrize("evidence", ["missing_count", "claimed_forwards", "wrong_binding", "orphan_row", "decision"])
def test_missing_startup_files_cannot_hide_scientific_evidence(rig, evidence):
    rig.cheap()
    raw = rig.raw("main")
    failure = {"completed_forwards": 0, "plan_sha256": r.PLAN_SHA256, "freeze_commit": r.FREEZE}
    if evidence == "missing_count":
        failure.pop("completed_forwards")
    elif evidence == "claimed_forwards":
        failure["completed_forwards"] = 1
    elif evidence == "wrong_binding":
        failure["freeze_commit"] = "f" * 40
    elif evidence == "orphan_row":
        write(raw / "forwards" / (rig.plan["discovery_rows"][0]["id"] + ".json"), {})
    else:
        write(raw / "discovery-decision.json", {})
    write(raw / "failed.json", failure)
    rig.seal(raw)
    result = r.inspect_release(rig.base, allow_incomplete=True)
    assert result["raw_audit"]["status"] == "failed"
    assert result["raw_audit"]["pass"] is False and result["status"] == "incomplete"


@pytest.mark.parametrize("evidence", ["model.json", "receipts.jsonl"])
def test_existing_model_or_receipts_are_not_reclassified_as_not_started(rig, evidence):
    rig.cheap()
    raw = rig.raw("main")
    if evidence == "model.json":
        write(raw / evidence, {"synthetic": True})
    else:
        (raw / evidence).write_bytes(b"")
    rig.seal(raw)
    result = r.inspect_release(rig.base, allow_incomplete=True)
    if evidence == "model.json":
        assert result["raw_audit"]["status"] == "audited"
        assert result["raw_audit"]["forwards"] == 0 and result["raw_audit"]["complete"] is False
    else:
        # The frozen auditor rejects a present but empty receipt journal.
        assert result["raw_audit"]["status"] == "failed" and result["raw_audit"]["pass"] is False


def test_out_of_limit_closure_cannot_authorize_later_attempt(rig):
    rig.cheap(seconds=1801)
    raw, _ = rig.main(complete=False)
    rig.seal(raw)
    with pytest.raises(ValueError, match="out-of-limit closure"):
        r.inspect_release(rig.base, allow_incomplete=True)


def test_changed_saved_audit_cannot_manufacture_completion(rig):
    rig.cheap()
    raw, _ = rig.main()
    saved = r._json(raw / "audit.json")
    saved["forward_seconds"][0] = 999
    write(raw / "audit.json", saved)
    rig.seal(raw)
    result = r.inspect_release(rig.base, allow_incomplete=True)
    assert result["raw_audit"]["complete"] is True and result["status"] == "incomplete"


def test_snapshot_lineage_preserves_committed_payloads(rig):
    rig.cheap()
    raw, window = rig.main(complete=False)
    earlier = raw.parent / "earlier"
    for name, path in r._files(raw).items():
        destination = earlier / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(path.read_bytes())
    window.collect(rig.plan["discovery_rows"][5:6])
    rig.seal(raw, earlier=earlier)
    result = r.inspect_release(rig.base, allow_incomplete=True)
    lineage = result["attempts"][-1]["snapshot_lineage"]
    assert [row["committed_forward_payloads_preserved"] for row in lineage] == [5, 6]
    assert [row["raw_audit"]["forwards"] for row in lineage] == [5, 6]


def test_inspection_does_not_create_missing_final_receipt(rig):
    rig.cheap()
    receipt = rig.base / "cheap-001/final-retrieval.json"
    receipt.unlink()
    with pytest.raises(FileNotFoundError):
        r.inspect_release(rig.base, allow_incomplete=True)
    assert not receipt.exists()


def test_destination_overlap_and_overwrite_refused(rig):
    rig.cheap()
    with pytest.raises(ValueError, match="Overlapping"):
        r.copy_release(rig.base, rig.base / "public", allow_incomplete=True)
    rig.dest.mkdir()
    with pytest.raises(ValueError, match="exists"):
        r.copy_release(rig.base, rig.dest, allow_incomplete=True)


def test_inspect_cli_is_read_only(rig, capsys):
    rig.cheap()
    before = {n: p.read_bytes() for n, p in r._files(rig.base).items()}
    r.main(["--base", str(rig.base), "--allow-incomplete"])
    assert json.loads(capsys.readouterr().out)["status"] == "incomplete"
    assert {n: p.read_bytes() for n, p in r._files(rig.base).items()} == before
    assert not rig.dest.exists()


def test_missing_ledger_is_not_created(tmp_path, monkeypatch):
    monkeypatch.setattr(r, "verify_sources", lambda: {"budget": r.c.BUDGET})
    root = tmp_path.resolve()
    with pytest.raises(FileNotFoundError):
        r.inspect_release(root, allow_incomplete=True)
    assert list(root.iterdir()) == []


def test_pinned_plan_and_all_source_input_bindings_verify_without_network():
    plan = r.verify_sources()
    assert plan["budget"] == r.c.BUDGET
    assert plan["counts"]["calibration_forwards"] == 520
    assert "scripts/release_fidelity_repair.py" not in plan["source_hashes"]
    assert "tests/test_release_fidelity_repair.py" not in plan["source_hashes"]


@pytest.mark.parametrize("target", ["plan", "source", "input", "git"])
def test_source_and_input_tampering_rejected(tmp_path, monkeypatch, target):
    root = tmp_path.resolve()
    blobs = {"source.py": b"# original\n", "input.json": b"{}\n"}
    plan = {"budget": r.c.BUDGET, "source_hashes": {"source.py": hashlib.sha256(blobs["source.py"]).hexdigest()},
            "input_hashes": {"input.json": hashlib.sha256(blobs["input.json"]).hexdigest()}}
    blobs[r.PLAN_PATH] = r._canonical(plan) + b"\n"
    monkeypatch.setattr(r, "ROOT", root)
    monkeypatch.setattr(r, "PLAN_SHA256", hashlib.sha256(blobs[r.PLAN_PATH]).hexdigest())
    monkeypatch.setattr(r, "frozen_blob", lambda name: blobs[name])
    for name, raw in blobs.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
    assert r.verify_sources() == plan
    if target == "git":
        blobs["source.py"] = b"# changed Git blob\n"
    else:
        path = {"plan": r.PLAN_PATH, "source": "source.py", "input": "input.json"}[target]
        (root / path).write_bytes(b"changed local bytes\n")
    with pytest.raises(ValueError, match="source mismatch"):
        r.verify_sources()

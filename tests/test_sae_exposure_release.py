"""Synthetic publication fixtures only; no pretrained weights, GPU or network."""
from copy import deepcopy
import json
from pathlib import Path
import socket
import subprocess
import sys

import pytest

from experiments.sae_assay_diagnostic.budget import EventLedger
from experiments.sae_assay_precision import pilot
from scripts import release_sae_exposure as release


FREEZE = "a" * 40


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    monkeypatch.setenv("HF_HUB_OFFLINE", "1")
    monkeypatch.setenv("TRANSFORMERS_OFFLINE", "1")
    def forbidden(*args, **kwargs):
        raise AssertionError("Publication tests must remain offline")
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(release.canonical(value) + "\n")


def seal(base, raw, plan_path, *, closed=True, closure_changes=None):
    """Build a fresh synthetic private chain after deliberate fixture changes."""
    for name in ("events.jsonl", "final-retrieval.json"):
        (base / name).unlink(missing_ok=True)
    ledger = EventLedger(base / "events.jsonl", release.sha(plan_path), FREEZE, [])
    receipt = ledger.bind("retrieval:synthetic", {
        "pod_id": "synthetic-owned", "directory": str(raw),
        "artifacts": {n: release.sha(p) for n, p in release._files(raw).items()}})
    write(base / "final-retrieval.json", receipt)
    if closed:
        closure = {"pod_id": "synthetic-owned", "get_status": 404,
                   "inventory_ids": [], "utc": "2026-09-30T00:00:00+00:00",
                   "elapsed_seconds": "10", "compute_upper_bound_usd": "0.002",
                   "cumulative_upper_bound_usd": "27.6371", "within_limits": True}
        closure.update(closure_changes or {})
        ledger.bind("closed", closure)
    return ledger


def prepared(tmp_path, monkeypatch, *, complete=True, mutate=None, closed=True):
    base, raw, destination = tmp_path / "private", tmp_path / "retrieved", tmp_path / "release"
    base.mkdir()
    raw.mkdir()
    plan = {"texts": [{"id": "synthetic-01"}], "precision_pilot": {"texts": [{"id": "synthetic-01"}]}}
    plan_path = tmp_path / "PLAN.json"
    write(plan_path, plan)
    plan_hash = release.sha(plan_path)
    monkeypatch.setattr(release, "PLAN_SHA256", plan_hash)
    # One argument deliberately: post-run publication must not require HEAD=freeze.
    monkeypatch.setattr(release, "load_plan", lambda path: deepcopy(plan))
    calls = []
    clean_rows = [{"text_id": "synthetic-01"}] if complete else []
    def audit_run(root, p, checksum, freeze, *, complete=True):
        assert p == plan and checksum == plan_hash and freeze == FREEZE
        calls.append(("clean", complete))
        return deepcopy(clean_rows)
    monkeypatch.setattr(release.analysis, "audit_run", audit_run)
    clean_summary = {"test_fixture": True, "rows": 1, "exposure_minima_met": False}
    monkeypatch.setattr(release.analysis, "summarize", lambda *a, **kw: deepcopy(clean_summary))
    def validate_run(root, p, checksum, freeze):
        assert p == plan and checksum == plan_hash and freeze == FREEZE
        calls.append(("pilot", True))
        return {"structural_pass": True, "row_count": 48}
    monkeypatch.setattr(pilot, "validate_run", validate_run)
    ids = ["qualification-live", "clean-synthetic-01"]
    ledger = EventLedger(raw / "receipts.jsonl", plan_hash, FREEZE, ids)
    if complete:
        for rid in ids:
            ledger.bind("dispatch:" + rid, {"kind": "dispatch", "row_id": rid})
            path = raw / "rows" / (rid + ".json")
            write(path, {"test_fixture": True, "id": rid})
            ledger.append_row(rid, {"path": path.relative_to(raw).as_posix(), "sha256": release.sha(path)})
        write(raw / "summary.json", clean_summary)
        # Full numerical reconstruction is tested by the experiment package.
        # Here its validator is a spy; these are not model-output fixtures.
        summary = {"completed": True, "full_model_forwards": 48,
                   "test_only": False, "overall_assay_qualified": False}
        write(raw / "precision_pilot/summary.json", summary)
        write(raw / "precision-pilot-summary.json", summary)
        pilot_marker = {"status": "complete", "summary_path": "precision-pilot-summary.json",
                        "summary_sha256": release.sha(raw / "precision-pilot-summary.json"),
                        "artifacts": [{"path": "precision_pilot/summary.json",
                                       "bytes": (raw / "precision_pilot/summary.json").stat().st_size,
                                       "sha256": release.sha(raw / "precision_pilot/summary.json")}]}
    else:
        pilot_marker = {"status": "not_completed"}
        write(raw / "failure.json", {"type": "TimeoutError", "status": "incomplete_budget_deadline",
                                     "plan_sha256": plan_hash, "freeze_commit": FREEZE})
    write(raw / "DONE-all.json", {"status": "complete" if complete else "incomplete_budget_deadline",
          "rows": 2 if complete else 0, "exposure_rows": len(clean_rows), "plan_sha256": plan_hash,
          "freeze_commit": FREEZE, "precision_pilot": pilot_marker, "behavioral_assay_qualified": False})
    if mutate:
        mutate(raw, plan, plan_hash)
    write(raw / "ARTIFACTS.json", {"schema": "sae_exposure_artifacts_v1",
          "plan_sha256": plan_hash, "freeze_commit": FREEZE,
          "files": [{"path": n, "sha256": release.sha(p), "bytes": p.stat().st_size}
                    for n, p in release._files(raw).items()]})
    write(raw / "controller-exit.json", {"exit_code": 0 if complete else 1})
    seal(base, raw, plan_path, closed=closed)
    sources = tmp_path / "sources"
    for name in release.REPORTING_SOURCES:
        path = sources / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("# inert publication test fixture\n")
    monkeypatch.setattr(release, "ROOT", sources)
    return base, raw, destination, plan_path, calls


def test_complete_copy_and_manifest_preserve_raw_hashes(tmp_path, monkeypatch):
    base, raw, dest, plan, calls = prepared(tmp_path, monkeypatch)
    before = release.sha(base / "events.jsonl")
    result = release.copy_release(base, dest, plan, FREEZE)
    assert result["status"] == "complete"
    assert result["closure"]["get_status"] == 404
    assert calls == [("clean", True), ("pilot", True)]
    assert release.sha(base / "events.jsonl") == before
    assert not (dest / "events.jsonl").exists()
    assert not (dest / "final-retrieval.json").exists()
    assert str(tmp_path) not in (dest / "retrieval_and_cost.json").read_text()
    for name, digest in result["artifacts"].items():
        assert release.sha(dest / name) == digest == release.sha(raw / name)
    report = release.manifest(dest, plan, FREEZE)
    assert set(report["reporting_source_hashes"]) == set(release.REPORTING_SOURCES)
    assert report["raw_safetensors_public_approval"] == "separate_bounded_capture_audit_required"
    assert not any("experiments/" in name for name in report["reporting_source_hashes"])
    for entry in report["files"]:
        assert release.sha(dest / entry["path"]) == entry["sha256"]
    with pytest.raises(FileExistsError):
        release.copy_release(base, dest, plan, FREEZE)
    with pytest.raises(FileExistsError):
        release.manifest(dest, plan, FREEZE)


def test_incomplete_release_requires_opt_in_and_never_claims_full_pilot(tmp_path, monkeypatch):
    base, raw, dest, plan, calls = prepared(tmp_path, monkeypatch, complete=False)
    with pytest.raises(ValueError, match="allow-incomplete"):
        release.copy_release(base, dest, plan, FREEZE)
    assert not dest.exists()
    release.copy_release(base, dest, plan, FREEZE, allow_incomplete=True)
    audit = json.loads((dest / "PUBLICATION_AUDIT.json").read_text())
    assert audit["status"] == "incomplete"
    assert audit["precision_pilot"] == {"status": "not_started", "validated_rows": 0, "completed": False}
    assert not audit["behavioral_assay_qualified"]
    assert (dest / "failure.json").read_bytes() == (raw / "failure.json").read_bytes()
    assert ("pilot", True) not in calls
    assert release.manifest(dest, plan, FREEZE)["status"] == "incomplete"


@pytest.mark.parametrize("problem", ["open", "changed", "extra", "bad-plan", "bad-freeze",
                                    "receipt-not-in-chain", "pod-mismatch", "not404", "still-in-inventory"])
def test_invalid_lifecycle_fails_before_destination(tmp_path, monkeypatch, problem):
    base, raw, dest, plan, _ = prepared(tmp_path, monkeypatch, closed=problem != "open")
    freeze = FREEZE
    if problem == "changed":
        (raw / "DONE-all.json").write_text("changed")
    if problem == "extra":
        (raw / "unexpected.txt").write_text("inert")
    if problem == "bad-plan":
        monkeypatch.setattr(release, "PLAN_SHA256", "f" * 64)
    if problem == "bad-freeze":
        freeze = "b" * 40
    if problem == "receipt-not-in-chain":
        value = json.loads((base / "final-retrieval.json").read_text())
        value["data"]["directory"] = "elsewhere"
        write(base / "final-retrieval.json", value)
    changes = {"pod-mismatch": {"pod_id": "different"}, "not404": {"get_status": 200},
               "still-in-inventory": {"inventory_ids": ["synthetic-owned"]}}
    if problem in changes:
        seal(base, raw, plan, closure_changes=changes[problem])
    with pytest.raises(ValueError):
        release.copy_release(base, dest, plan, freeze)
    assert not dest.exists()


@pytest.mark.parametrize("name", [".env", "credentials.json", "events.jsonl", "worker.pid",
                                 "weights.safetensors", "precision_pilot/tensors/048.safetensors"])
def test_allowlist_blocks_even_hash_verified_unplanned_files(tmp_path, monkeypatch, name):
    def mutate(root, *args):
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("inert fixture")
    if name == ".env":
        # The path walker itself refuses dot files before a ledger is sealed.
        with pytest.raises(ValueError, match="artifact path"):
            prepared(tmp_path, monkeypatch, mutate=mutate)
        return
    base, _, dest, plan, _ = prepared(tmp_path, monkeypatch, mutate=mutate)
    with pytest.raises(ValueError, match="Unexpected retrieved"):
        release.copy_release(base, dest, plan, FREEZE)
    assert not dest.exists()


@pytest.mark.parametrize("text", ["/Users/private/person/checkpoint.md", "/home/person/events.jsonl",
                                  "root@192.0.2.8", "ssh -i ~/.ssh/private_key",
                                  "RUNPOD_API_KEY=" + "z" * 30])
def test_private_text_is_not_copied(tmp_path, monkeypatch, text):
    base, _, dest, plan, _ = prepared(tmp_path, monkeypatch,
        mutate=lambda root, *_: (root / "controller.log").write_text(text))
    with pytest.raises(ValueError, match="content|path"):
        release.copy_release(base, dest, plan, FREEZE)
    assert not dest.exists()


def test_escaped_json_secret_and_path_are_detected(tmp_path):
    path = tmp_path / "failure.json"
    path.write_text('{"message":"\\u002fUsers\\u002fhidden"}')
    with pytest.raises(ValueError, match="Private"):
        release._scan_text(path.name, path)
    token = "hf_" + "z" * 25
    path.write_text('{"message":"' + "".join("\\u%04x" % ord(c) for c in token) + '"}')
    with pytest.raises(ValueError, match="scan failed"):
        release._scan_text(path.name, path)


def test_worker_binding_ids_are_permitted_without_private_coordinates(tmp_path, monkeypatch):
    def mutate(root, _, checksum):
        write(root / "controller-stopped.json", {"stopped": True, "dispatch_fenced": True,
              "binding": {"worker_id": "synthetic-worker", "pod_id": "synthetic-owned",
                          "freeze_commit": FREEZE, "plan_sha256": checksum}})
    base, _, dest, plan, _ = prepared(tmp_path, monkeypatch, mutate=mutate)
    release.copy_release(base, dest, plan, FREEZE)
    assert (dest / "controller-stopped.json").is_file()


@pytest.mark.parametrize("where", ["clean", "pilot"])
def test_complete_markers_cannot_replace_full_audits(tmp_path, monkeypatch, where):
    base, _, dest, plan, _ = prepared(tmp_path, monkeypatch)
    def failed(*a, **kw):
        raise ValueError("synthetic raw audit failure")
    monkeypatch.setattr(release.analysis if where == "clean" else pilot,
                        "audit_run" if where == "clean" else "validate_run", failed)
    with pytest.raises(ValueError, match="raw audit failure"):
        release.copy_release(base, dest, plan, FREEZE)
    assert not dest.exists()


@pytest.mark.parametrize("problem", ["clean-summary", "pilot-summary", "done-count", "done-pilot",
                                    "synthetic-pilot", "exit", "worker-inventory"])
def test_semantic_terminal_tampering_rejected_despite_fresh_retrieval_hashes(tmp_path, monkeypatch, problem):
    base, raw, dest, plan, _ = prepared(tmp_path, monkeypatch)
    names = {"clean-summary": "summary.json", "pilot-summary": "precision-pilot-summary.json",
             "done-count": "DONE-all.json", "done-pilot": "DONE-all.json",
             "synthetic-pilot": "precision_pilot/summary.json", "exit": "controller-exit.json",
             "worker-inventory": "ARTIFACTS.json"}
    path = raw / names[problem]
    data = json.loads(path.read_text())
    if problem == "clean-summary":
        data["rows"] = 999
    if problem == "pilot-summary":
        data["overall_assay_qualified"] = True
    if problem == "done-count":
        data["exposure_rows"] = 999
    if problem == "done-pilot":
        data["precision_pilot"]["artifacts"] = []
    if problem == "synthetic-pilot":
        data["test_only"] = True
    if problem == "exit":
        data["exit_code"] = 1
    if problem == "worker-inventory":
        data["files"] = []
    write(path, data)
    seal(base, raw, plan)
    with pytest.raises(ValueError):
        release.copy_release(base, dest, plan, FREEZE)
    assert not dest.exists()


def test_changed_controller_log_snapshot_is_disclosed_not_hidden(tmp_path, monkeypatch):
    base, raw, dest, plan, _ = prepared(tmp_path, monkeypatch, complete=False,
        mutate=lambda root, *_: (root / "controller.log").write_text("before terminal\n"))
    with (raw / "controller.log").open("a") as handle:
        handle.write("synthetic traceback after worker snapshot\n")
    seal(base, raw, plan)
    release.copy_release(base, dest, plan, FREEZE, allow_incomplete=True)
    assert json.loads((dest / "PUBLICATION_AUDIT.json").read_text())["worker_snapshot_log_matches_final"] is False
    assert (dest / "controller.log").read_bytes() == (raw / "controller.log").read_bytes()


def test_symlink_and_noncanonical_relative_paths_are_refused(tmp_path, monkeypatch):
    base, raw, dest, plan, _ = prepared(tmp_path, monkeypatch)
    (raw / "alias").symlink_to(raw / "summary.json")
    with pytest.raises(ValueError, match="symlink"):
        release.copy_release(base, dest, plan, FREEZE)
    assert not dest.exists()
    for name in ("../escape", "/absolute", "a//b", "./x", "a/../b", "a\\b", "a\nx"):
        with pytest.raises(ValueError):
            release._relative(name)


def test_missing_ledger_does_not_create_source_files(tmp_path, monkeypatch):
    base, _, dest, plan, _ = prepared(tmp_path, monkeypatch)
    (base / "events.jsonl").unlink()
    with pytest.raises(ValueError, match="Missing regular ledger"):
        release.copy_release(base, dest, plan, FREEZE)
    assert not (base / "events.jsonl").exists()
    assert not dest.exists()


def test_manifest_requires_explicit_additional_files_and_reaudits(tmp_path, monkeypatch):
    base, _, dest, plan, _ = prepared(tmp_path, monkeypatch)
    release.copy_release(base, dest, plan, FREEZE)
    write(dest / "analysis/report.json", {"synthetic": True})
    with pytest.raises(ValueError, match="Unlisted publication"):
        release.manifest(dest, plan, FREEZE)
    result = release.manifest(dest, plan, FREEZE, additional_files=["analysis/report.json"])
    assert "analysis/report.json" in {r["path"] for r in result["files"]}


def test_manifest_cannot_conceal_mutated_raw_data(tmp_path, monkeypatch):
    base, _, dest, plan, _ = prepared(tmp_path, monkeypatch)
    release.copy_release(base, dest, plan, FREEZE)
    write(dest / "summary.json", {"tampered": True})
    with pytest.raises(ValueError, match="raw artifacts changed"):
        release.manifest(dest, plan, FREEZE)


@pytest.mark.parametrize("name", ["credentials.json", "analysis/events.json", "tables/checkpoint.md"])
def test_explicit_additional_file_cannot_authorize_private_lifecycle_name(tmp_path, monkeypatch, name):
    base, _, dest, plan, _ = prepared(tmp_path, monkeypatch)
    release.copy_release(base, dest, plan, FREEZE)
    write(dest / name, {"inert": True})
    with pytest.raises(ValueError, match="Invalid explicitly named"):
        release.manifest(dest, plan, FREEZE, additional_files=[name])


def test_bounded_capture_size_refuses_model_scale_file(tmp_path, monkeypatch):
    base, raw, dest, plan, _ = prepared(tmp_path, monkeypatch)
    path = raw / "residuals/synthetic-01.safetensors"
    path.parent.mkdir()
    with path.open("wb") as handle:
        handle.truncate(release.MAX_CLEAN_BYTES + 1)
    seal(base, raw, plan)
    with pytest.raises(ValueError, match="bounded state"):
        release.copy_release(base, dest, plan, FREEZE)
    assert not dest.exists()


def test_real_clean_partial_audit_with_qualification_only(tmp_path, monkeypatch):
    """Exercise the actual frozen auditor, not the fixture spy, on a failed prefix."""
    original_audit = release.analysis.audit_run
    base, raw, dest, path, _ = prepared(tmp_path, monkeypatch, complete=False)
    actual_plan_path = Path(__file__).resolve().parents[1] / "data/sae_assay_exposure/plan_20260930/PLAN.json"
    plan = json.loads(actual_plan_path.read_text())
    write(path, plan)
    checksum = release.sha(path)
    monkeypatch.setattr(release, "PLAN_SHA256", checksum)
    monkeypatch.setattr(release, "load_plan", lambda _: plan)
    monkeypatch.setattr(release.analysis, "audit_run", original_audit)
    (raw / "receipts.jsonl").unlink()
    ids = ["qualification-live", *("clean-" + item["id"] for item in plan["texts"])]
    ledger = EventLedger(raw / "receipts.jsonl", checksum, FREEZE, ids)
    rid = "qualification-live"
    ledger.bind("dispatch:" + rid, {"kind": "dispatch", "row_id": rid})
    row = {"id": rid, "plan_sha256": checksum, "freeze_commit": FREEZE,
           "pass": True, "token_ids": [1, 2], "checks": {"clean_identity": True,
           "activation_identity": True, "no_edit": True, "hook_removed": True}}
    write(raw / "rows/qualification-live.json", row)
    ledger.append_row(rid, {"path": "rows/qualification-live.json",
                           "sha256": release.sha(raw / "rows/qualification-live.json")})
    done = json.loads((raw / "DONE-all.json").read_text())
    done.update(plan_sha256=checksum, rows=1)
    write(raw / "DONE-all.json", done)
    (raw / "ARTIFACTS.json").unlink()
    seal(base, raw, path)
    release.copy_release(base, dest, path, FREEZE, allow_incomplete=True)
    assert json.loads((dest / "PUBLICATION_AUDIT.json").read_text())["clean_validated_rows"] == 0


def partial_pilot(tmp_path, monkeypatch):
    base, raw, dest, plan_path, calls = prepared(tmp_path, monkeypatch)
    plan = json.loads(plan_path.read_text())
    checksum = release.sha(plan_path)
    (raw / "precision_pilot/summary.json").unlink()
    (raw / "precision-pilot-summary.json").unlink()
    (raw / "ARTIFACTS.json").unlink()
    root = raw / "precision_pilot"
    ids = ["precision-pilot:synthetic-01:" + mode for mode in release.MODES]
    ledger = EventLedger(root / "receipts.jsonl", checksum, FREEZE, ids)
    write(root / "binding.json", {"schema": pilot.SCHEMA, "plan_sha256": checksum,
                                 "freeze_commit": FREEZE, "text_ids": ["synthetic-01"]})
    ledger.bind("runtime", {"kind": "runtime", "test_fixture": True})
    write(root / "qualification.json", {"pass": True, "test_fixture": True})
    ledger.bind("qualification", {"kind": "qualification", "sha256": release.sha(root / "qualification.json")})
    ledger.bind("dispatch:" + ids[0], {"kind": "dispatch", "row_id": ids[0],
                                       "ordinal": 0, "full_model_forwards": 1})
    capture = root / "tensors/000.safetensors"
    capture.parent.mkdir()
    capture.write_bytes(b"inert-capture-test-fixture")
    row = {"row_id": ids[0], "freeze_commit": FREEZE, "test_only": False,
           "capture": {"path": "tensors/000.safetensors", "sha256": release.sha(capture)}}
    write(root / "rows/000.json", row)
    ledger.append_row(ids[0], {"path": "rows/000.json", "sha256": release.sha(root / "rows/000.json"),
                              "capture_sha256": release.sha(capture)})
    write(root / "failure.json", {"error_type": "TimeoutError", "completed_forward_records": 1})
    ledger.bind("failure", {"kind": "failure", "sha256": release.sha(root / "failure.json")})
    done = json.loads((raw / "DONE-all.json").read_text())
    done.update(status="incomplete_budget_deadline", precision_pilot={"status": "not_completed"})
    write(raw / "DONE-all.json", done)
    write(raw / "controller-exit.json", {"exit_code": 1})
    def validate_row(value, p, directory):
        assert value == row and p == plan and directory == root
        calls.append(("partial-pilot-row", False))
    monkeypatch.setattr(pilot, "validate_row", validate_row)
    seal(base, raw, plan_path)
    return base, raw, dest, plan_path, calls


def test_valid_partial_pilot_preserved_as_incomplete(tmp_path, monkeypatch):
    base, raw, dest, plan, calls = partial_pilot(tmp_path, monkeypatch)
    release.copy_release(base, dest, plan, FREEZE, allow_incomplete=True)
    audit = json.loads((dest / "PUBLICATION_AUDIT.json").read_text())
    assert audit["status"] == "incomplete"
    assert audit["clean_validated_rows"] == 1
    assert audit["precision_pilot"] == {"status": "incomplete", "validated_rows": 1, "completed": False}
    assert ("partial-pilot-row", False) in calls
    assert ("pilot", True) not in calls
    assert (dest / "precision_pilot/failure.json").read_bytes() == (raw / "precision_pilot/failure.json").read_bytes()


def test_unreceipted_failed_pilot_rows_are_never_silently_omitted(tmp_path, monkeypatch):
    base, raw, dest, plan, _ = partial_pilot(tmp_path, monkeypatch)
    write(raw / "precision_pilot/rows/001.json", {"rejected": True})
    seal(base, raw, plan)
    with pytest.raises(ValueError, match="Unreceipted"):
        release.copy_release(base, dest, plan, FREEZE, allow_incomplete=True)
    assert not dest.exists()
    assert (raw / "precision_pilot/rows/001.json").is_file()


def test_partial_pilot_must_follow_full_clean_panel(tmp_path, monkeypatch):
    base, raw, dest, plan, _ = prepared(tmp_path, monkeypatch, complete=False)
    write(raw / "precision_pilot/binding.json", {"test_fixture": True})
    (raw / "ARTIFACTS.json").unlink()
    seal(base, raw, plan)
    with pytest.raises(ValueError, match="before clean screening"):
        release.copy_release(base, dest, plan, FREEZE, allow_incomplete=True)
    assert not dest.exists()


def test_missing_reporting_source_refuses_manifest(tmp_path, monkeypatch):
    base, _, dest, plan, _ = prepared(tmp_path, monkeypatch)
    release.copy_release(base, dest, plan, FREEZE)
    (release.ROOT / "scripts/report_sae_exposure.py").unlink()
    with pytest.raises(FileNotFoundError):
        release.manifest(dest, plan, FREEZE)
    assert not (dest / "RELEASE_MANIFEST.json").exists()


def test_invalid_closure_projection_refused_before_copy(tmp_path, monkeypatch):
    base, raw, dest, plan, _ = prepared(tmp_path, monkeypatch)
    seal(base, raw, plan, closure_changes={"elapsed_seconds": "/Users/private"})
    with pytest.raises(ValueError):
        release.copy_release(base, dest, plan, FREEZE)
    assert not dest.exists()


def test_older_matching_retrieval_cannot_replace_latest(tmp_path, monkeypatch):
    base, raw, dest, plan, _ = prepared(tmp_path, monkeypatch)
    old = json.loads((base / "final-retrieval.json").read_text())
    (base / "events.jsonl").unlink()
    ledger = EventLedger(base / "events.jsonl", release.sha(plan), FREEZE, [])
    ledger.bind(old["id"], old["data"])
    ledger.bind("retrieval:later", old["data"])
    ledger.bind("closed", {"pod_id": "synthetic-owned", "get_status": 404})
    with pytest.raises(ValueError, match="superseded"):
        release.copy_release(base, dest, plan, FREEZE)
    assert not dest.exists()


def test_script_cli_help_runs_without_pythonpath(tmp_path):
    script = Path(release.__file__).resolve()
    result = subprocess.run([sys.executable, str(script), "--help"], cwd=tmp_path,
                            capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    assert "--allow-incomplete" in result.stdout


def test_manifest_contract_matches_separate_public_auditor(tmp_path, monkeypatch):
    auditor = pytest.importorskip("scripts.audit_sae_exposure_release")
    approvals = dict(auditor.APPROVED_RELEASE_MANIFESTS)
    base, _, dest, plan, _ = prepared(tmp_path, monkeypatch)
    release.copy_release(base, dest, plan, FREEZE)
    expected = release.manifest(dest, plan, FREEZE)
    monkeypatch.setattr(auditor, "PLAN_SHA256", release.sha(plan))
    monkeypatch.setattr(auditor, "FREEZE_COMMIT", FREEZE)
    blobs = {auditor.RELEASE_ROOT + "/" + name: path.read_bytes()
             for name, path in release._files(dest).items()}
    for name in release.REPORTING_SOURCES:
        blobs[name] = (release.ROOT / name).read_bytes()
    records = {name: (len(blob), auditor.sha256(blob)) for name, blob in blobs.items()}
    evidence = auditor.Evidence(set(blobs), records, {n: "100644" for n in blobs},
                                lambda name, limit: blobs[name])
    assert auditor.validate_manifest(evidence) == expected
    assert auditor.APPROVED_RELEASE_MANIFESTS == approvals

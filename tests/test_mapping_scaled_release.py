"""Synthetic, offline publication tests; no model, provider, or paid calls."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import shutil

import pytest

from experiments import mapping_scaled_release as release
from experiments.berg_dose_ladder import analysis, protocol


FREEZE = "a" * 40


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(protocol.canonical(value) + "\n")


def chain(events, plan_hash, ids=()):
    records = []
    for identifier, data in [("binding", {"kind": "binding", "row_ids": sorted(ids)})] + events:
        event = {"id": identifier, "seq": len(records), "data": data,
                 "plan_sha256": plan_hash, "freeze_commit": FREEZE,
                 "previous_sha256": records[-1]["sha256"] if records else None}
        event["sha256"] = hashlib.sha256(protocol.canonical(event).encode()).hexdigest()
        records.append(event)
    return records


def write_chain(path, records):
    path.write_text("".join(protocol.canonical(r) + "\n" for r in records))


@pytest.fixture
def frozen(monkeypatch):
    plan_path = protocol.ROOT / release.PLAN_PATH
    plan = json.loads(plan_path.read_text())
    objects = {name: (protocol.ROOT / name).read_bytes()
               for name in set(plan["source_hashes"]) | set(plan["input_hashes"]) | {release.PLAN_PATH}}
    def blob(freeze, name):
        assert freeze == FREEZE
        return objects[name]
    def git(*args):
        assert args == ("cat-file", "-t", FREEZE)
        return b"commit\n"
    monkeypatch.setattr(release, "_frozen_blob", blob)
    monkeypatch.setattr(release, "_git", git)
    return plan


def synthetic_row(spec, positive):
    ids = list(dict.fromkeys(list(protocol.TARGET_IDS) + spec["feature_ids"]))
    norm = spec["dose"]
    telemetry = {
        "schema": "berg_dose_ladder_additive_v1", "coefficient": spec["coefficient"],
        "hook_removed": True, "feature_ids": spec["feature_ids"], "weights": spec["weights"],
        "actual_weights": spec["weights"], "readout_feature_ids": ids,
        "normalization": {"multiplier": 1., "requested_norm_matched": True,
                          "relative_norm_error": 0., "requested_norm": norm},
        "position_metadata": [
            {"position": 0, "origin": "prompt", "special": False, "terminal_observation_only": False},
            {"position": 1, "origin": "generated", "special": False, "terminal_observation_only": True}],
        "delivery": {"cosine": [1., 1.], "relative_error": [0., 0.],
                     "requested_norm": [norm, norm], "realized_norm": [norm, norm]},
        "reencoding": [{"before": [1.] * len(ids), "after": [1. + norm / 10] * len(ids)}],
    }
    turn = {"response": "Synthetic response.", "input_tokens": 1, "output_tokens": 1,
            "output_token_ids": [1], "cap_hit": False, "telemetry": telemetry}
    row = {"id": spec["id"], "spec": spec, "turns": [deepcopy(turn), deepcopy(turn)],
           "judges": {"notebook": {"label": positive, "raw": "yes" if positive else "no"},
                      "paper": {"label": positive, "raw": str(positive)}},
           "coherence": [{"repeat4": 0., "clean_nll": 1.} for _ in range(2)], "elapsed_seconds": .1}
    analysis.validate_row(row, spec)
    return row


def run_fixture(root, plan, kind="partial"):
    root.mkdir()
    source = protocol.ROOT / release.PLAN_PATH
    shutil.copyfile(source, root / "PLAN.json")
    digest = protocol.sha(source)
    write(root / "runtime.json", {"plan_sha256": digest, "freeze_commit": FREEZE})
    ids = [r["id"] for r in plan["rows"]] + ["qualification-live"]
    events = [("runtime", {"kind": "runtime"})]
    qualification = {"id": "qualification-live", "result": {"pass": True, "zero_hidden_bit_exact": True},
                     "judge_fixtures": {"pass": True}, "geometry": {"requested_norm_matched": True}}
    if kind == "failed_qualification":
        qualification["result"]["pass"] = False
    rows = []
    def publish(row, *, receipt=True):
        rid = row["id"]
        events.append(("dispatch:" + rid, {"kind": "dispatch", "row_id": rid}))
        path = root / "rows" / (rid + ".json")
        write(path, row)
        if receipt:
            events.append(("row:" + rid, {"kind": "row", "row_id": rid,
                           "payload": {"path": path.relative_to(root).as_posix(), "sha256": protocol.sha(path)}}))
        rows.append(row)
    publish(qualification)
    if kind not in {"failed_qualification"}:
        specs = [s for s in plan["rows"] if s["phase"] == "calibration"]
        if kind in {"partial", "pending"}:
            specs = specs[:1]
        for spec in specs:
            publish(synthetic_row(spec, spec["block"] % 2 if kind == "main" else 0),
                    receipt=kind != "pending")
    if kind in {"completed", "main"}:
        selection = analysis.calibration_selection(rows, plan)
        write(root / "selection.json", selection)
        events.append(("selection", {"kind": "selection", "selected_dose": selection["selected_dose"],
                                    "sha256": protocol.sha(root / "selection.json")}))
        for spec in protocol.selected_rows(plan, selection["selected_dose"]):
            if spec["phase"] == "main":
                publish(synthetic_row(spec, int(spec["coefficient"] == -1)))
        write(root / "DONE-all.json", {"pass": True, "plan_sha256": digest, "freeze_commit": FREEZE,
               "generations": len(rows) - 1, "main_run": selection["pass"],
               "selected_dose": selection["selected_dose"]})
    else:
        write(root / "failed.json", {"plan_sha256": digest, "error_type": "SyntheticTechnicalFailure",
                                    "completed": len(rows)})
    write_chain(root / "receipts.jsonl", chain(events, digest, ids))
    write(root / "model-bf16-load-00002.json", {"dtype": "bfloat16", "synthetic": True})
    return root


def build_partial(tmp_path, frozen, kind="partial"):
    source = run_fixture(tmp_path / "retrieved", frozen, kind)
    target = tmp_path / "release"
    result = release.build(source, target, freeze=FREEZE, mode="partial_technical_failure")
    return source, target, result


def rehash(root):
    manifest = release._json(root / "MANIFEST.json")
    files = release._files(root)
    files.pop("MANIFEST.json")
    manifest["files"] = release._entries(files)
    write(root / "MANIFEST.json", manifest)


def test_completed_without_selected_dose_preserves_raw_and_marks_main_not_run(tmp_path, frozen):
    source = run_fixture(tmp_path / "retrieved", frozen, "completed")
    before = {n: p.read_bytes() for n, p in release._files(source).items()}
    target = tmp_path / "release"
    result = release.build(source, target, freeze=FREEZE)
    assert result["pass"] and result["main_status"] == "not_run"
    assert before == {n: p.read_bytes() for n, p in release._files(source).items()}
    assert before == {n: p.read_bytes() for n, p in release._files(target / "raw").items()}
    summary = release._json(target / "analysis/summary.json")
    assert summary["results"] == {} and summary["selection"]["selected_dose"] is None
    report = release._json(target / "REPORT.json")
    assert report["scientific"]["status"] == "strict_completed"
    assert report["receipts"]["receipt_complete"]
    controller = release._json(target / "provenance/controller.json")
    assert controller["lifecycle"] == {"status": "not_provided", "cost": None, "deletion_verified": None}
    assert {p.name for p in (target / "figures").iterdir()} == {
        f"{name}.{ext}" for name in release.FIGURES for ext in ("png", "pdf")}
    assert all(p.stat().st_size > 1000 for p in (target / "figures").iterdir())
    assert release.verify(target, expected_manifest_sha256=result["manifest_sha256"])["external_manifest_bound"]


def test_selected_main_uses_exact_frozen_analysis_and_both_rubrics(tmp_path, frozen):
    source = run_fixture(tmp_path / "retrieved", frozen, "main")
    original = analysis.analyze(source, tmp_path / "expected")
    shutil.copytree(tmp_path / "expected", source / "analysis")
    target = tmp_path / "release"
    assert release.build(source, target, freeze=FREEZE)["main_status"] == "completed"
    assert release._json(target / "analysis/summary.json") == original
    data = release._json(target / "FIGURE_DATA.json")
    assert data["contrasts"] == original["results"]
    assert {c["judge"] for c in data["calibration"]} == {"notebook", "paper"}
    assert {c["family"] for c in data["calibration"]} == {"zero", "target", "control"}
    assert len(data["delivery"]) == 684


@pytest.mark.parametrize("kind,status", [("partial", "strict_partial_only"),
                                         ("pending", "not_certified"),
                                         ("failed_qualification", "not_certified")])
def test_partial_and_failed_qualification_are_not_completed_inference(tmp_path, frozen, kind, status):
    _, target, result = build_partial(tmp_path, frozen, kind)
    assert result["mode"] == "partial_technical_failure"
    report = release._json(target / "REPORT.json")
    assert report["scientific"]["status"] == status and report["main_status"] == "not_run"
    assert not (target / "analysis/summary.json").exists()
    data = release._json(target / "FIGURE_DATA.json")
    assert not data["contrasts"]
    if kind == "pending":
        assert len(report["receipts"]["pending_rows"]) == 1
        assert not report["receipts"]["receipt_complete"] and not data["delivery"]
    if kind == "failed_qualification":
        assert not release._json(target / "raw/rows/qualification-live.json")["result"]["pass"]


def test_startup_failure_retains_awaiting_runner_state(tmp_path, frozen):
    source = tmp_path / "startup"
    source.mkdir()
    write(source / "controller-exit.json", {"exit_code": 1})
    target = tmp_path / "release"
    release.build(source, target, freeze=FREEZE, mode="partial_technical_failure")
    report = release._json(target / "REPORT.json")
    assert report["receipts"]["state"] == "awaiting_runner"
    assert report["scientific"]["status"] == "not_certified"
    assert report["observed_rows"] == 0
    assert release._json(target / "FIGURE_DATA.json")["calibration"] == []


def startup_fixture(root, plan, *, runtime_event=True, saved_plan=False):
    root.mkdir()
    plan_path = protocol.ROOT / release.PLAN_PATH
    if saved_plan:
        shutil.copyfile(plan_path, root / "PLAN.json")
    events = [("runtime", {"kind": "runtime", "schema": plan["schema"],
                           "deadline_utc": "2030-01-01T00:00:00+00:00"})] if runtime_event else []
    records = chain(events, protocol.sha(plan_path), ["qualification-live"] + [r["id"] for r in plan["rows"]])
    write_chain(root / "receipts.jsonl", records)
    write(root / "controller-exit.json", {"exit_code": 1})
    return records


@pytest.mark.parametrize("runtime_event", [False, True])
@pytest.mark.parametrize("saved_plan", [False, True])
def test_bound_startup_ledger_without_runtime_stays_uncertified(tmp_path, frozen, runtime_event, saved_plan):
    source, target = tmp_path / "startup", tmp_path / "release"
    startup_fixture(source, frozen, runtime_event=runtime_event, saved_plan=saved_plan)
    before = {name: path.read_bytes() for name, path in release._files(source).items()}
    result = release.build(source, target, freeze=FREEZE, mode="partial_technical_failure")
    assert result["main_status"] == "not_run"
    assert before == {name: path.read_bytes() for name, path in release._files(source).items()}
    assert before == {name: path.read_bytes() for name, path in release._files(target / "raw").items()}
    assert not (target / "raw/runtime.json").exists()
    report = release._json(target / "REPORT.json")
    assert report["scientific"]["status"] == "not_certified"
    assert report["receipts"] == {"receipt_complete": False, "state": "awaiting_runner",
                                   "pending_rows": [], "pending_dispatches": []}
    assert report["observed_rows"] == 0
    data = release._json(target / "FIGURE_DATA.json")
    assert data["calibration"] == data["quality"] == data["delivery"] == []
    assert data["contrasts"] == {} and not data["descriptive_rows_certified"]
    assert not (target / "analysis/summary.json").exists()
    assert release.verify(target)["main_status"] == "not_run"


@pytest.mark.parametrize("mutation", [
    "plan_binding", "freeze_binding", "inventory", "empty", "hash", "dispatch", "row",
    "selection", "unknown", "runtime_kind", "runtime_schema", "runtime_deadline", "runtime_extra",
    "runtime_without_plan", "row_file", "pending_file", "selection_file", "no_terminal", "completed_mode",
])
def test_startup_ledger_exception_rejects_scientific_or_malformed_evidence(tmp_path, frozen, mutation):
    source, target = tmp_path / "startup", tmp_path / "release"
    records = startup_fixture(source, frozen)
    rid = frozen["rows"][0]["id"]
    if mutation == "plan_binding":
        for event in records:
            event["plan_sha256"] = "b" * 64
    elif mutation == "freeze_binding":
        for event in records:
            event["freeze_commit"] = "b" * 40
    elif mutation == "inventory":
        records[0]["data"]["row_ids"] = []
    elif mutation == "empty":
        records = []
    elif mutation in {"dispatch", "row", "selection", "unknown"}:
        identifier = {"dispatch": "dispatch:" + rid, "row": "row:" + rid}.get(mutation, mutation)
        records[1].update(id=identifier, data={"kind": mutation, "row_id": rid})
    elif mutation == "runtime_kind":
        records[1]["data"]["kind"] = "dispatch"
    elif mutation == "runtime_schema":
        records[1]["data"]["schema"] = "other_study"
    elif mutation == "runtime_deadline":
        records[1]["data"]["deadline_utc"] = "2030-01-01T00:00:00"
    elif mutation == "runtime_extra":
        records[1]["data"]["row_id"] = rid
    elif mutation == "runtime_without_plan":
        write(source / "runtime.json", {"plan_sha256": records[0]["plan_sha256"], "freeze_commit": FREEZE})
    elif mutation in {"row_file", "pending_file"}:
        suffix = "json" if mutation == "row_file" else "pending"
        write(source / "rows" / ("qualification-live." + suffix), {"id": "qualification-live"})
    elif mutation == "selection_file":
        write(source / "selection.json", {"selected_dose": None})
    elif mutation == "no_terminal":
        (source / "controller-exit.json").unlink()
    # Rehash altered semantics so failures test validation, not only checksums.
    previous = None
    for event in records:
        event["previous_sha256"] = previous
        event["sha256"] = release._digest(protocol.canonical({k: v for k, v in event.items() if k != "sha256"}).encode())
        previous = event["sha256"]
    if mutation == "hash":
        records[-1]["sha256"] = "0" * 64
    write_chain(source / "receipts.jsonl", records)
    before = {name: path.read_bytes() for name, path in release._files(source).items()}
    mode = "completed" if mutation == "completed_mode" else "partial_technical_failure"
    with pytest.raises(ValueError):
        release.build(source, target, freeze=FREEZE, mode=mode)
    assert not target.exists()
    assert before == {name: path.read_bytes() for name, path in release._files(source).items()}


@pytest.mark.parametrize("name", [".env", "nested/.env", "model.safetensors", "source.ipynb",
                                  "model.bin", "private-key.pem", "unapproved.json"])
def test_rejects_secret_and_weight_notebook_unknown_paths_before_copy(tmp_path, frozen, name):
    source = run_fixture(tmp_path / "retrieved", frozen)
    path = source / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{}")
    target = tmp_path / "release"
    with pytest.raises(ValueError):
        release.build(source, target, freeze=FREEZE, mode="partial_technical_failure")
    assert not target.exists()


def test_rejects_private_content_and_symlinks(tmp_path, frozen):
    source = run_fixture(tmp_path / "retrieved", frozen)
    (source / "controller.log").write_text("Private path /Users/example/private.env")
    with pytest.raises(ValueError, match="Private"):
        release.build(source, tmp_path / "release", freeze=FREEZE, mode="partial_technical_failure")
    (source / "controller.log").unlink()
    (source / "controller.log").symlink_to(source / "PLAN.json")
    with pytest.raises(ValueError, match="symlink"):
        release.build(source, tmp_path / "release", freeze=FREEZE, mode="partial_technical_failure")


@pytest.mark.parametrize("mutation", ["tamper", "extra", "missing", "duplicate", "traversal", "noncanonical", "bool_size"])
def test_strict_manifest_tamper_and_inventory(tmp_path, frozen, mutation):
    _, target, _ = build_partial(tmp_path, frozen)
    path = target / "MANIFEST.json"
    manifest = release._json(path)
    if mutation == "tamper":
        with (target / "raw/receipts.jsonl").open("ab") as stream:
            stream.write(b"\n")
    elif mutation == "extra":
        (target / "extra.json").write_text("{}")
    elif mutation == "missing":
        (target / "figures/calibration.png").unlink()
    elif mutation == "duplicate":
        manifest["files"].append(manifest["files"][0])
        write(path, manifest)
    elif mutation == "traversal":
        manifest["files"][0]["path"] = "../outside"
        write(path, manifest)
    elif mutation == "noncanonical":
        path.write_text(json.dumps(manifest, indent=2))
    elif mutation == "bool_size":
        manifest["files"][0]["bytes"] = True
        write(path, manifest)
    with pytest.raises(ValueError):
        release.verify(target)


@pytest.mark.parametrize("mutation", ["raw", "report", "figure_data", "summary_extra", "secret_extra"])
def test_rehashing_manifest_does_not_bypass_semantic_checks(tmp_path, frozen, mutation):
    _, target, result = build_partial(tmp_path, frozen)
    if mutation == "raw":
        rowpath = target / "raw/rows/qualification-live.json"
        row = release._json(rowpath)
        row["result"]["pass"] = False
        write(rowpath, row)
    elif mutation == "report":
        report = release._json(target / "REPORT.json")
        report["main_status"] = "completed"
        write(target / "REPORT.json", report)
    elif mutation == "figure_data":
        data = release._json(target / "FIGURE_DATA.json")
        data["calibration"][0]["positive"] = 1000
        write(target / "FIGURE_DATA.json", data)
    elif mutation == "summary_extra":
        write(target / "analysis/summary.json", {"invented": True})
    else:
        (target / "model.safetensors").write_bytes(b"unapproved")
    rehash(target)
    with pytest.raises(ValueError):
        release.verify(target)
    with pytest.raises(ValueError, match="External manifest"):
        release.verify(target, expected_manifest_sha256=result["manifest_sha256"])


def controller_fixture(root, source, *, closed=True):
    digest = protocol.sha(source / "PLAN.json")
    artifacts = {n: protocol.sha(p) for n, p in release._files(source).items()}
    payload = {"pod_id": "synthetic-owned", "directory": str(source), "artifacts": artifacts}
    events = [("controller:config", {"namespace": "dose-ladder-controller", "kind": "main"}),
              ("created", {"id": "synthetic-owned", "name": "codex-dose-ladder-20261004-main-synthetic"}),
              ("retrieval:1", payload)]
    if closed:
        events.extend([("delete-intent", {"pod_id": "synthetic-owned"}),
                       ("delete-response", {"pod_id": "synthetic-owned", "status": 204})])
        events.append(("closed", {"pod_id": "synthetic-owned", "get_status": 404,
                      "inventory_ids": ["synthetic-unrelated"], "elapsed_seconds": "120.25",
                      "compute_upper_bound_usd": "0.2301458333333333333333333333",
                      "cumulative_upper_bound_usd": "0.9991458333333333333333333333",
                      "within_limits": True}))
    records = chain(events, digest)
    receipt, ledger = root / "final-retrieval.json", root / "events.jsonl"
    write(receipt, next(e for e in records if e["id"] == "retrieval:1"))
    write_chain(ledger, records)
    return receipt, ledger


def test_optional_external_controller_binds_exact_cost_and_deletion_without_private_paths(tmp_path, frozen):
    source = run_fixture(tmp_path / "retrieved", frozen)
    receipt, ledger = controller_fixture(tmp_path, source)
    target = tmp_path / "release"
    result = release.build(receipt, target, freeze=FREEZE, mode="partial_technical_failure", controller_ledger=ledger)
    assert result["lifecycle_verified_this_check"]
    public = release._json(target / "provenance/controller.json")
    lifecycle = public["lifecycle"]
    assert lifecycle["deletion_verified"] is True
    assert lifecycle["cost"]["compute_upper_bound_usd"] == "0.2301458333333333333333333333"
    assert lifecycle["cost"]["cumulative_upper_bound_usd"] == "0.9991458333333333333333333333"
    text = (target / "provenance/controller.json").read_text()
    assert str(source) not in text and "synthetic-unrelated" not in text
    assert not release.verify(target)["lifecycle_verified_this_check"]
    assert release.verify(target, controller_receipt=receipt, controller_ledger=ledger)["external_controller_bound"]
    public["lifecycle"]["cost"]["cumulative_upper_bound_usd"] = "0"
    write(target / "provenance/controller.json", public)
    rehash(target)
    with pytest.raises(ValueError, match="external controller"):
        release.verify(target, controller_receipt=receipt, controller_ledger=ledger)


def test_unclosed_controller_is_unresolved_not_zero_cost(tmp_path, frozen):
    source = run_fixture(tmp_path / "retrieved", frozen)
    receipt, ledger = controller_fixture(tmp_path, source, closed=False)
    target = tmp_path / "release"
    release.build(receipt, target, freeze=FREEZE, mode="partial_technical_failure", controller_ledger=ledger)
    lifecycle = release._json(target / "provenance/controller.json")["lifecycle"]
    assert lifecycle["status"] == "unresolved" and lifecycle["cost"] is None
    assert lifecycle["deletion_verified"] is False


def test_no_worker_receipt_without_directory_creates_no_scientific_evidence(tmp_path, frozen):
    source = run_fixture(tmp_path / "unused", frozen)
    receipt, ledger = controller_fixture(tmp_path, source)
    events = [(e["id"], e["data"]) for e in map(json.loads, ledger.read_text().splitlines())
              if e["id"] != "binding"]
    payload = next(data for key, data in events if key == "retrieval:1")
    payload.pop("directory")
    payload.update(artifacts={}, no_worker_dispatched=True)
    records = chain(events, protocol.sha(source / "PLAN.json"))
    write(receipt, next(e for e in records if e["id"] == "retrieval:1"))
    write_chain(ledger, records)
    target = tmp_path / "release"
    result = release.build(receipt, target, freeze=FREEZE, mode="partial_technical_failure", controller_ledger=ledger)
    assert result["main_status"] == "not_run" and result["lifecycle_verified_this_check"]
    assert not release._files(target / "raw")
    report = release._json(target / "REPORT.json")
    assert report["no_worker_dispatched"] and report["observed_rows"] == 0
    assert report["scientific"]["status"] == "not_certified"
    assert not release._json(target / "FIGURE_DATA.json")["calibration"]
    with pytest.raises(ValueError, match="No-worker release"):
        release.build(receipt, tmp_path / "invalid-completed", freeze=FREEZE, controller_ledger=ledger)


@pytest.mark.parametrize("mutation", ["foreign", "cheap", "missing_delete", "foreign_delete", "listed", "no_404"])
def test_controller_ownership_and_direct_deletion_evidence(tmp_path, frozen, mutation):
    source = run_fixture(tmp_path / "retrieved", frozen)
    receipt, ledger = controller_fixture(tmp_path, source)
    records = [json.loads(line) for line in ledger.read_text().splitlines()]
    data = {e["id"]: e["data"] for e in records}
    if mutation == "foreign":
        data["created"]["name"] = "another-study"
    elif mutation == "cheap":
        data["controller:config"]["kind"] = "cheap"
    elif mutation == "missing_delete":
        data.pop("delete-intent")
    elif mutation == "foreign_delete":
        data["delete-response"]["pod_id"] = "not-owned"
    elif mutation == "listed":
        data["closed"]["inventory_ids"].append("synthetic-owned")
    else:
        data["closed"]["get_status"] = 200
    records = chain([(key, value) for key, value in data.items() if key != "binding"],
                    protocol.sha(source / "PLAN.json"))
    write_chain(ledger, records)
    write(receipt, next(e for e in records if e["id"] == "retrieval:1"))
    target = tmp_path / "release"
    if mutation in {"listed", "no_404"}:
        release.build(receipt, target, freeze=FREEZE, mode="partial_technical_failure", controller_ledger=ledger)
        public = release._json(target / "provenance/controller.json")
        assert public["lifecycle"]["status"] == "unresolved"
        assert not public["lifecycle"]["deletion_verified"]
    else:
        with pytest.raises(ValueError):
            release.build(receipt, target, freeze=FREEZE, mode="partial_technical_failure", controller_ledger=ledger)


def test_retrieval_inventory_mismatch_and_tampered_receipt_rejected(tmp_path, frozen):
    source = run_fixture(tmp_path / "retrieved", frozen)
    receipt, _ = controller_fixture(tmp_path, source)
    (source / "controller.log").write_text("additional bytes")
    with pytest.raises(ValueError, match="inventory/hash"):
        release.build(receipt, tmp_path / "release", freeze=FREEZE, mode="partial_technical_failure")
    event = release._json(receipt)
    event["data"]["pod_id"] = "different"
    write(receipt, event)
    with pytest.raises(ValueError, match="Receipt hash"):
        release.build(receipt, tmp_path / "release", freeze=FREEZE, mode="partial_technical_failure")


def test_existing_destination_and_incomplete_completed_mode_rejected(tmp_path, frozen):
    source = run_fixture(tmp_path / "retrieved", frozen)
    target = tmp_path / "existing"
    target.mkdir()
    sentinel = target / "keep"
    sentinel.write_text("unchanged")
    with pytest.raises(ValueError, match="Destination must be new"):
        release.build(source, target, freeze=FREEZE)
    assert sentinel.read_text() == "unchanged"
    with pytest.raises(ValueError, match="Incomplete selected"):
        release.build(source, tmp_path / "new", freeze=FREEZE)
    assert not (tmp_path / "new").exists()


def test_bound_source_mismatch_is_rejected_before_release(tmp_path, frozen, monkeypatch):
    source = run_fixture(tmp_path / "retrieved", frozen)
    original = release._frozen_blob
    bound = "experiments/berg_dose_ladder/analysis.py"
    monkeypatch.setattr(release, "_frozen_blob", lambda freeze, name: b"changed" if name == bound else original(freeze, name))
    with pytest.raises(ValueError, match="Frozen blob mismatch"):
        release.build(source, tmp_path / "release", freeze=FREEZE, mode="partial_technical_failure")


def test_sidecar_does_not_change_frozen_source_closure():
    plan = release._json(protocol.ROOT / release.PLAN_PATH)
    paths = protocol.source_paths()
    assert set(paths) == set(plan["source_hashes"])
    assert "experiments/mapping_scaled_release.py" not in paths
    assert "tests/test_mapping_scaled_release.py" not in paths
    assert all(protocol.sha(protocol.ROOT / name) == digest for name, digest in plan["source_hashes"].items())

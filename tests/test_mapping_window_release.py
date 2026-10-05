"""Synthetic, offline QA for the unfrozen dose-window publication adapter."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import json
from pathlib import Path
import shutil
import socket

import pytest

from experiments import mapping_window_release as release
from experiments.berg_dose_window import analysis, protocol
from tests.test_mapping_scaled_release import FREEZE, chain, synthetic_row, write, write_chain


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Publication tests must not make network calls")
    monkeypatch.setattr(socket, "socket", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)


@pytest.fixture(scope="module")
def source_objects():
    # Construct prospective frozen blobs locally, without a real successor freeze.
    root = protocol.ROOT
    plan = json.loads((root / release.base.PLAN_PATH).read_text())
    plan.update(protocol.design_fields())
    plan["source_hashes"] = {n: protocol.sha(root / n) for n in protocol.source_paths()}
    plan["input_hashes"][protocol.PREDECESSOR] = protocol.sha(root / protocol.PREDECESSOR)
    objects = {n: (root / n).read_bytes() for n in set(plan["source_hashes"]) | set(plan["input_hashes"])}
    objects[release.PLAN_PATH] = (protocol.canonical(plan) + "\n").encode()
    return plan, objects


@pytest.fixture
def frozen(tmp_path, monkeypatch, source_objects):
    plan, original = source_objects
    objects = dict(original)
    root = tmp_path / "frozen"
    for name, value in objects.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(value)
    monkeypatch.setattr(protocol, "ROOT", root)
    def blob(freeze, name):
        assert freeze == FREEZE
        return objects[name]
    def git(*args):
        assert args == ("cat-file", "-t", FREEZE)
        return b"commit\n"
    monkeypatch.setattr(release, "_frozen_blob", blob)
    monkeypatch.setattr(release, "_git", git)
    return deepcopy(plan)


@pytest.fixture
def fast_plots(monkeypatch):
    # Semantic/tamper tests need only an inventory; branch tests render real plots.
    def plots(data, destination):
        destination.mkdir()
        for name in release.FIGURE_FILES:
            (destination / Path(name).name).write_bytes(b"synthetic-figure-fixture")
    monkeypatch.setattr(release, "_plots", plots)


def reference(plan):
    return {"freeze_commit": FREEZE, "plan_path": release.PLAN_PATH,
            "plan_sha256": protocol.sha(protocol.ROOT / release.PLAN_PATH),
            "source_hashes": plan["source_hashes"], "input_hashes": plan["input_hashes"]}


def run_fixture(root, plan, kind="zero_failed"):
    root.mkdir()
    ref = reference(plan)
    shutil.copyfile(protocol.ROOT / release.PLAN_PATH, root / "PLAN.json")
    write(root / "runtime.json", {"plan_sha256": ref["plan_sha256"], "freeze_commit": FREEZE})
    events = [("runtime", {"kind": "runtime"})]
    rows = []
    ids = [r["id"] for r in plan["rows"]] + ["qualification-live"]
    def publish(row, receipted=True):
        rid = row["id"]
        events.append(("dispatch:" + rid, {"kind": "dispatch", "row_id": rid}))
        path = root / "rows" / (rid + ".json")
        write(path, row)
        if receipted:
            events.append(("row:" + rid, {"kind": "row", "row_id": rid,
                           "payload": {"path": path.relative_to(root).as_posix(), "sha256": protocol.sha(path)}}))
        rows.append(row)
    qualification = {"id": "qualification-live", "result": {"pass": kind != "failed_qualification", "zero_hidden_bit_exact": True},
                     "judge_fixtures": {"pass": True}, "geometry": {"requested_norm_matched": True}}
    publish(qualification)
    partial = kind in {"partial", "pending", "failed_qualification", "pending_main"}
    zeros = analysis.zero_specs(plan)
    if kind == "failed_qualification":
        zeros = []
    elif kind in {"partial", "pending"}:
        zeros = zeros[:1]
    for spec in zeros:
        publish(synthetic_row(spec, 0 if kind == "zero_failed" else spec["block"] % 2), kind != "pending")
    if len(zeros) == 12:
        gate = analysis.zero_screen(rows, plan)
        write(root / "zero_screen.json", gate)
        events.append(("zero-screen", {"kind": "zero_screen", "sha256": protocol.sha(root / "zero_screen.json"), "pass": gate["pass"]}))
        selected = None
        if gate["pass"]:
            for spec in plan["rows"]:
                if spec["phase"] == "calibration" and spec["family"] != "zero":
                    row = synthetic_row(spec, spec["block"] % 2)
                    if kind == "calibration_failed":
                        for turn in row["coherence"]:
                            turn["clean_nll"] = 3.
                    publish(row)
            selection = analysis.calibration_selection(rows, plan)
            selected = selection["selected_dose"]
            write(root / "selection.json", selection)
            events.append(("selection", {"kind": "selection", "selected_dose": selected,
                                         "sha256": protocol.sha(root / "selection.json")}))
            for spec in protocol.selected_rows(plan, selected):
                if spec["phase"] == "main":
                    if kind == "pending_main":
                        events.append(("dispatch:" + spec["id"], {"kind": "dispatch", "row_id": spec["id"]}))
                        break
                    publish(synthetic_row(spec, int(spec["coefficient"] == -1)))
        if not partial:
            write(root / "DONE-all.json", {"pass": True, "schema": "dose_window_completion_v1",
                "plan_sha256": ref["plan_sha256"], "freeze_commit": FREEZE, "generations": len(rows) - 1,
                "zero_screen_pass": gate["pass"], "main_run": selected is not None, "selected_dose": selected,
                "stop_reason": None if gate["pass"] else "zero_screen_failed"})
    if partial:
        write(root / "failed.json", {"plan_sha256": ref["plan_sha256"], "error_type": "SyntheticFailure", "completed": len(rows)})
    write_chain(root / "receipts.jsonl", chain(events, ref["plan_sha256"], ids))
    (root / "controller.log").write_bytes(b"Synthetic worker log\r\nPreserve line endings\r\n")
    write(root / "model-bf16-load-00002.json", {"dtype": "bfloat16", "synthetic": True})
    return root


def startup(root, plan, runtime_event=True):
    root.mkdir()
    events = [("runtime", {"kind": "runtime", "schema": plan["schema"],
                           "deadline_utc": "2030-01-01T00:00:00+00:00"})] if runtime_event else []
    records = chain(events, reference(plan)["plan_sha256"], ["qualification-live"] + [r["id"] for r in plan["rows"]])
    write_chain(root / "receipts.jsonl", records)
    write(root / "controller-exit.json", {"exit_code": 1})
    return records


def rechain(records):
    for i, event in enumerate(records):
        event.update(seq=i, previous_sha256=records[i - 1]["sha256"] if i else None)
        event.pop("sha256", None)
        event["sha256"] = release._digest(protocol.canonical(event).encode())


def rehash(root):
    manifest = release._json(root / "MANIFEST.json")
    files = release._files(root)
    files.pop("MANIFEST.json")
    manifest["files"] = release._entries(files)
    write(root / "MANIFEST.json", manifest)


@pytest.mark.parametrize("kind,n,branch,unrun", [
    ("zero_failed", 12, "zero_screen_failed", {"treated_calibration": 192, "main": 480}),
    ("calibration_failed", 204, "calibration_failed", {"treated_calibration": 0, "main": 480}),
    ("main", 684, "main_completed", {"treated_calibration": 0, "main": 0}),
])
def test_three_terminal_branches_preserve_bytes_and_render_real_figures(tmp_path, frozen, kind, n, branch, unrun):
    raw = run_fixture(tmp_path / "retrieved", frozen, kind)
    expected_summary = analysis.analyze(raw, tmp_path / "expected")
    shutil.copytree(tmp_path / "expected", raw / "analysis")
    before = {name: p.read_bytes() for name, p in release._files(raw).items()}
    dest = tmp_path / "release"
    result = release.build(raw, dest, freeze=FREEZE)
    assert result["branch"] == branch
    assert before == {name: p.read_bytes() for name, p in release._files(raw).items()}
    assert before == {name: p.read_bytes() for name, p in release._files(dest / "raw").items()}
    assert release._json(dest / "analysis/summary.json") == expected_summary
    report, data = release._json(dest / "REPORT.json"), release._json(dest / "FIGURE_DATA.json")
    assert report["observed_rows"] == n + 1
    assert report["scientific"]["status"] == "strict_completed"
    assert report["receipts"]["receipt_complete"] and report["unrun_trials"] == unrun
    assert len(data["delivery"]) == n and data["unrun_trials"] == unrun
    assert {c["judge"] for c in data["calibration"]} == {"notebook", "paper"}
    assert {p.relative_to(dest).as_posix() for p in (dest / "figures").iterdir()} == release.FIGURE_FILES
    assert all(p.stat().st_size > 1000 for p in (dest / "figures").iterdir())
    if n < 684:
        assert report["main_status"] == "not_run" and data["contrasts"] == {}
        assert report["observed_main_rows"] == 0
    else:
        assert report["main_status"] == "completed" and data["contrasts"] == expected_summary["results"]
    if n == 12:
        assert expected_summary["selection"] is None
        assert report["treated_calibration_status"] == "not_run"
        assert {c["family"] for c in data["calibration"]} == {"zero"}
        assert all(c["n"] == 12 and c["flagged"] == 0 for c in data["quality"])
    assert release.verify(dest, expected_manifest_sha256=result["manifest_sha256"])["external_manifest_bound"]


@pytest.mark.parametrize("kind,status,main_status", [
    ("partial", "strict_partial_only", "not_run"), ("pending", "not_certified", "not_run"),
    ("failed_qualification", "not_certified", "not_run"), ("pending_main", "not_certified", "incomplete"),
])
def test_partial_snapshots_never_infer_zero_for_missing_main(tmp_path, frozen, fast_plots, kind, status, main_status):
    raw = run_fixture(tmp_path / "retrieved", frozen, kind)
    dest = tmp_path / "release"
    release.build(raw, dest, freeze=FREEZE, mode="partial_technical_failure")
    report, data = release._json(dest / "REPORT.json"), release._json(dest / "FIGURE_DATA.json")
    assert report["scientific"]["status"] == status and report["main_status"] == main_status
    assert report["unrun_trials"] is None and data["contrasts"] == {}
    assert not (dest / "analysis/summary.json").exists()
    if status == "not_certified":
        assert data["delivery"] == data["calibration"] == data["quality"] == []
    if kind == "pending_main":
        assert report["observed_main_rows"] == 0 and len(report["receipts"]["pending_dispatches"]) == 1


@pytest.mark.parametrize("runtime_event", [False, True])
def test_binding_only_startup_is_preserved_not_certified(tmp_path, frozen, fast_plots, runtime_event):
    raw, dest = tmp_path / "startup", tmp_path / "release"
    startup(raw, frozen, runtime_event)
    release.build(raw, dest, freeze=FREEZE, mode="partial_technical_failure")
    report = release._json(dest / "REPORT.json")
    assert report["receipts"]["state"] == "awaiting_runner"
    assert report["scientific"]["status"] == "not_certified"
    assert (raw / "receipts.jsonl").read_bytes() == (dest / "raw/receipts.jsonl").read_bytes()
    assert release._json(dest / "FIGURE_DATA.json")["delivery"] == []


@pytest.mark.parametrize("mutation", ["dispatch", "row", "zero_screen", "plan", "freeze", "zero_file", "runtime_schema"])
def test_startup_exception_rejects_science_and_bad_bindings(tmp_path, frozen, fast_plots, mutation):
    raw, dest = tmp_path / "startup", tmp_path / "release"
    records = startup(raw, frozen)
    if mutation in {"dispatch", "row", "zero_screen"}:
        records[1].update(id=mutation, data={"kind": mutation, "row_id": frozen["rows"][0]["id"]})
    elif mutation in {"plan", "freeze"}:
        for event in records:
            event["plan_sha256" if mutation == "plan" else "freeze_commit"] = "b" * (64 if mutation == "plan" else 40)
    elif mutation == "zero_file":
        write(raw / "zero_screen.json", {"pass": False})
    else:
        records[1]["data"]["schema"] = "wrong"
    rechain(records)
    write_chain(raw / "receipts.jsonl", records)
    with pytest.raises(ValueError):
        release.build(raw, dest, freeze=FREEZE, mode="partial_technical_failure")
    assert not dest.exists()


@pytest.mark.parametrize("mutation", ["gate_hash", "gate_pass", "gate_missing", "completion_count", "completion_main", "runtime", "raw_plan"])
def test_completed_branch_requires_untreated_receipt_and_exact_completion(tmp_path, frozen, fast_plots, mutation):
    raw = run_fixture(tmp_path / "retrieved", frozen)
    if mutation in {"gate_hash", "gate_missing"}:
        records = [json.loads(line) for line in (raw / "receipts.jsonl").read_text().splitlines()]
        if mutation == "gate_hash":
            records[-1]["data"]["sha256"] = "0" * 64
        else:
            records.pop()
        rechain(records)
        write_chain(raw / "receipts.jsonl", records)
    elif mutation == "gate_pass":
        gate = release._json(raw / "zero_screen.json")
        gate["pass"] = True
        write(raw / "zero_screen.json", gate)
    elif mutation.startswith("completion"):
        done = release._json(raw / "DONE-all.json")
        done["generations" if mutation == "completion_count" else "main_run"] = 204 if mutation == "completion_count" else True
        write(raw / "DONE-all.json", done)
    elif mutation == "runtime":
        runtime = release._json(raw / "runtime.json")
        runtime["freeze_commit"] = "b" * 40
        write(raw / "runtime.json", runtime)
    else:
        (raw / "PLAN.json").write_bytes((raw / "PLAN.json").read_bytes() + b"\n")
    with pytest.raises(ValueError):
        release.build(raw, tmp_path / "release", freeze=FREEZE)


@pytest.mark.parametrize("mutation", ["bytes", "inventory", "manifest_bool", "manifest_traversal", "noncanonical", "report", "figure_data", "summary", "source"])
def test_manifest_and_semantic_tamper_rejected_even_after_rehash(tmp_path, frozen, fast_plots, mutation):
    raw = run_fixture(tmp_path / "retrieved", frozen)
    dest = tmp_path / "release"
    release.build(raw, dest, freeze=FREEZE)
    if mutation == "bytes":
        (dest / "raw/controller.log").write_bytes(b"Changed\n")
    elif mutation == "inventory":
        write(dest / "extra.json", {})
        rehash(dest)
    elif mutation.startswith("manifest_"):
        manifest = release._json(dest / "MANIFEST.json")
        manifest["files"][0]["bytes" if mutation == "manifest_bool" else "path"] = True if mutation == "manifest_bool" else "../escape"
        write(dest / "MANIFEST.json", manifest)
    elif mutation == "noncanonical":
        manifest = dest / "MANIFEST.json"
        manifest.write_text(json.dumps(release._json(manifest), indent=2))
    else:
        name, key, value = {"report": ("REPORT.json", "main_status", "completed"),
                            "figure_data": ("FIGURE_DATA.json", "contrasts", {"target": 0}),
                            "summary": ("analysis/summary.json", "unrun_main_trials", 0),
                            "source": ("provenance/source.json", "freeze_commit", "b" * 40)}[mutation]
        record = release._json(dest / name)
        record[key] = value
        write(dest / name, record)
        rehash(dest)
    with pytest.raises((ValueError, AssertionError)):
        release.verify(dest)


@pytest.mark.parametrize("name,content", [(".env", b"not a credential"), ("source.ipynb", b"{}"),
    ("model.safetensors", b"weights"), ("private.json", b"{}"),
    ("controller.log", b"/Users/example/private/session\n"),
    ("model-bf16-load-00003.json", b'{"path":"\\u002fUsers\\u002fexample\\u002fprivate"}')])
def test_unapproved_or_private_artifacts_fail_before_destination(tmp_path, frozen, fast_plots, name, content):
    raw = run_fixture(tmp_path / "retrieved", frozen)
    (raw / name).write_bytes(content)
    dest = tmp_path / "release"
    with pytest.raises(ValueError):
        release.build(raw, dest, freeze=FREEZE)
    assert not dest.exists()


def controller_fixture(tmp_path, raw, plan):
    ref = reference(plan)
    start = datetime(2030, 1, 1, tzinfo=timezone.utc)
    pod = {"id": "synthetic-owned", "name": "codex-dose-window-20261004-main-012345abcdef", "createdAt": start.isoformat()}
    cheap, cost = Decimal("0.052"), Decimal(120) * Decimal("6.89") / 3600
    events = [
        ("controller:config", {"kind": "main", "namespace": "dose-window-controller", "plan_path": release.PLAN_PATH,
                               "budget": protocol.BUDGET, "hard_seconds": protocol.MAIN_SECONDS}),
        ("create-intent", {"payload": {"name": pod["name"]}, "quote": {"hourly_rate_usd": "6.79"},
             "blocked": ["unrelated-pod"], "created_utc": start.isoformat(),
             "deadline_utc": (start + timedelta(seconds=protocol.MAIN_SECONDS - protocol.RESERVE_SECONDS)).isoformat(),
             "hard_deadline_utc": (start + timedelta(seconds=protocol.MAIN_SECONDS)).isoformat(),
             "prior_new_usd": str(cheap), "prior_total_usd": protocol.PRIOR_USD,
             "plan_sha256": ref["plan_sha256"], "freeze_commit": FREEZE}),
        ("created", pod),
        ("retrieval:final", {"pod_id": pod["id"], "directory": str(raw),
                             "artifacts": {n: protocol.sha(p) for n, p in release._files(raw).items()}}),
        ("delete-intent", {"pod_id": pod["id"]}),
        ("delete-response", {"pod_id": pod["id"], "status": 204}),
        ("closed", {"pod_id": pod["id"], "get_status": 404, "inventory_ids": ["unrelated-pod"],
             "utc": (start + timedelta(seconds=120)).isoformat(), "elapsed_seconds": "120",
             "compute_upper_bound_usd": str(cost), "cumulative_upper_bound_usd": str(Decimal(protocol.PRIOR_USD) + (cheap + cost)),
             "within_limits": True}),
    ]
    records = chain(events, ref["plan_sha256"])
    ledger, receipt = tmp_path / "controller-ledger.jsonl", tmp_path / "final-retrieval.json"
    write_chain(ledger, records)
    write(receipt, records[4])
    return ledger, receipt, records


def test_controller_external_cost_carry_deletion_and_snapshot_binding(tmp_path, frozen, fast_plots):
    raw = run_fixture(tmp_path / "retrieved", frozen)
    ledger, receipt, records = controller_fixture(tmp_path, raw, frozen)
    before = ledger.read_bytes(), receipt.read_bytes()
    dest = tmp_path / "release"
    result = release.build(receipt, dest, freeze=FREEZE, controller_ledger=ledger)
    assert result["lifecycle_verified_this_check"]
    public = release._json(dest / "provenance/controller.json")
    assert public["lifecycle"]["deletion_verified"]
    assert public["lifecycle"]["cost"]["prior_study_usd"] == protocol.PRIOR_USD
    assert public["lifecycle"]["cost"]["cumulative_upper_bound_usd"] == records[-1]["data"]["cumulative_upper_bound_usd"]
    text = protocol.canonical(public)
    assert "synthetic-owned" not in text and "unrelated-pod" not in text and str(raw) not in text
    assert before == (ledger.read_bytes(), receipt.read_bytes())
    assert not release.verify(dest)["lifecycle_verified_this_check"]
    # A self-consistent changed public projection still fails its external anchor.
    public["lifecycle"]["cost"]["prior_study_usd"] = "0"
    write(dest / "provenance/controller.json", public)
    rehash(dest)
    with pytest.raises(ValueError, match="external controller"):
        release.verify(dest, controller_receipt=receipt, controller_ledger=ledger)


@pytest.mark.parametrize("mutation", ["carry", "cumulative", "storage", "budget", "timer", "owner", "blocked", "snapshot", "delete_order", "delete_pod", "limits"])
def test_controller_rejects_changed_admission_or_closure(tmp_path, frozen, mutation):
    raw = run_fixture(tmp_path / "retrieved", frozen)
    ledger, receipt, records = controller_fixture(tmp_path, raw, frozen)
    config, intent, created, retrieval, delete, response, closed = [r["data"] for r in records[1:]]
    if mutation == "carry":
        intent["prior_total_usd"] = "0"
    elif mutation == "cumulative":
        closed["cumulative_upper_bound_usd"] = closed["compute_upper_bound_usd"]
    elif mutation == "storage":
        closed["compute_upper_bound_usd"] = "0"
        closed["cumulative_upper_bound_usd"] = str(Decimal(protocol.PRIOR_USD) + Decimal(intent["prior_new_usd"]))
    elif mutation == "budget":
        config["budget"] = {**config["budget"], "total_usd": "200"}
    elif mutation == "timer":
        intent["hard_deadline_utc"] = intent["deadline_utc"]
    elif mutation == "owner":
        created["name"] = "codex-dose-ladder-20261004-main-012345abcdef"
    elif mutation == "blocked":
        intent["blocked"].append(created["id"])
    elif mutation == "snapshot":
        retrieval["artifacts"]["zero_screen.json"] = "0" * 64
    elif mutation == "delete_order":
        records[4], records[5] = records[5], records[4]
    elif mutation == "delete_pod":
        delete["pod_id"] = "unrelated-pod"
    else:
        closed["within_limits"] = False
    rechain(records)
    write_chain(ledger, records)
    write(receipt, next(r for r in records if r["id"].startswith("retrieval:")))
    with pytest.raises(ValueError):
        release._controller(receipt, ledger, reference(frozen), {n: protocol.sha(p) for n, p in release._files(raw).items()})


@pytest.mark.parametrize("mutation", ["no_404", "listed", "not_closed"])
def test_unresolved_deletion_is_not_certified(tmp_path, frozen, mutation):
    raw = run_fixture(tmp_path / "retrieved", frozen)
    ledger, receipt, records = controller_fixture(tmp_path, raw, frozen)
    if mutation == "no_404":
        records[-1]["data"]["get_status"] = 200
    elif mutation == "listed":
        records[-1]["data"]["inventory_ids"].append("synthetic-owned")
    else:
        records.pop()
    rechain(records)
    write_chain(ledger, records)
    write(receipt, records[4])
    public = release._controller(receipt, ledger, reference(frozen), {n: protocol.sha(p) for n, p in release._files(raw).items()})
    assert public["lifecycle"]["status"] == "unresolved" and public["lifecycle"]["deletion_verified"] is False


def test_earlier_snapshot_cannot_stand_in_for_final_retrieval(tmp_path, frozen):
    raw = run_fixture(tmp_path / "retrieved", frozen)
    ledger, receipt, records = controller_fixture(tmp_path, raw, frozen)
    later = deepcopy(records[4])
    later["id"] = "retrieval:later"
    records.insert(5, later)
    rechain(records)
    write_chain(ledger, records)
    with pytest.raises(ValueError, match="not the final"):
        release._controller(receipt, ledger, reference(frozen), {n: protocol.sha(p) for n, p in release._files(raw).items()})


def test_delivery_means_exclude_terminal_positions_and_remain_descriptive(tmp_path, frozen):
    root = tmp_path / "raw"
    spec = next(s for s in frozen["rows"] if s["family"] == "target")
    row = synthetic_row(spec, 1)
    for index, turn in enumerate(row["turns"]):
        turn["telemetry"]["delivery"]["requested_norm"] = [2. + index * 2., 100.]
        turn["telemetry"]["delivery"]["realized_norm"] = [3. + index * 4., 200.]
    write(root / "rows" / (spec["id"] + ".json"), row)
    report = {"scientific": {"status": "strict_partial_only"}, "main_status": "not_run",
              "branch": "technical_failure", "treated_calibration_status": "incomplete", "unrun_trials": None}
    data = release._figure_data(root, report, None)
    assert data["delivery"][0]["requested_norm"] == 3.
    assert data["delivery"][0]["realized_norm"] == 5.
    assert "Descriptive only" in data["notes"]["delivery"] and data["contrasts"] == {}


def test_source_closure_excludes_sidecars_and_detects_local_drift(tmp_path, frozen):
    paths = set(protocol.source_paths())
    assert "experiments/mapping_window_release.py" not in paths
    assert "tests/test_mapping_window_release.py" not in paths
    ref = reference(frozen)
    raw = (protocol.ROOT / release.PLAN_PATH).read_bytes()
    release._verify_sources(raw, ref)
    path = protocol.ROOT / "experiments/berg_dose_window/analysis.py"
    path.write_bytes(path.read_bytes() + b"\n")
    with pytest.raises(ValueError, match="differs from frozen source"):
        release._verify_sources(raw, ref)


def test_destination_is_new_and_symlinks_rejected(tmp_path, frozen, fast_plots):
    raw = run_fixture(tmp_path / "retrieved", frozen)
    with pytest.raises(ValueError, match="outside retrieval"):
        release.build(raw, raw / "nested", freeze=FREEZE)
    with pytest.raises(ValueError, match="must be new"):
        release.build(raw, raw, freeze=FREEZE)
    (raw / "controller.log").unlink()
    (raw / "controller.log").symlink_to(raw / "PLAN.json")
    with pytest.raises(ValueError):
        release.build(raw, tmp_path / "release", freeze=FREEZE)

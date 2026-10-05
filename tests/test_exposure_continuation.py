"""Offline continuation tests; all inference, provider and SSH work is synthetic."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import json
from pathlib import Path
import signal
import subprocess
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from experiments.berg_dose_exposure_continuation import protocol as p, analysis as a, runner, controller as c
from experiments.sae_assay_diagnostic.budget import EventLedger
from experiments.sae_assay_diagnostic.runner import write_once
from tests.test_dose_exposure_runner import synthetic_row
from tests.test_dose_exposure_controller import FakeAPI


@pytest.fixture(scope="module")
def plan():
    return p.build_plan()


def test_real_preserved_prefix_inventory_and_cost(plan):
    prior, selection, throughput = p.verify_prefix()
    assert len(plan["rows"]) == 480 and len({r["block"] for r in plan["rows"]}) == 96
    assert plan["rows"] == [r for r in p.old.selected_rows(prior, .25) if r["phase"] == "main"]
    assert plan["continuation"]["selection"] == selection and selection["pass"]
    assert selection["zero_headroom"]["positive"] == 5 and selection["zero_headroom"]["negative"] == 7
    assert not throughput["pass"] and throughput["remaining_trials"] == 480
    assert all(plan[k] == prior[k] for k in prior if k not in {"schema", "rows", "budget", "source_hashes", "input_hashes"})
    assert Decimal(p.PRIOR_USD) + Decimal(p.NEW_CAP_USD) < 50
    full = Decimal("6.89") * p.MAIN_SECONDS / 3600
    assert full == Decimal("33.4165") and full <= Decimal(p.NEW_CAP_USD)
    assert p.CHEAP["new_cheap_pod"] is False
    assert set(p.old.source_paths()) == set(prior["source_hashes"])
    assert "tests/test_exposure_continuation.py" in p.source_paths()


@pytest.mark.parametrize("name", ["raw/selection.json", "raw/throughput.json", "raw/failed.json", "raw/receipts.jsonl"])
def test_prefix_tampering_is_not_reinterpreted(monkeypatch, name):
    real = p.sha
    monkeypatch.setattr(p, "sha", lambda path: "0" * 64 if str(path).endswith(name) else real(path))
    with pytest.raises(ValueError, match="prefix changed"):
        p.verify_prefix()


@pytest.mark.parametrize("field", ["budget", "rows", "continuation"])
def test_frozen_plan_mutation_rejected(plan, tmp_path, field):
    changed = deepcopy(plan)
    changed[field] = {} if field != "rows" else plan["rows"][:-1]
    path = tmp_path / "PLAN.json"
    write_once(path, changed)
    with pytest.raises(ValueError, match="drift"):
        p.load_plan(path)


def test_worker_exact_namespace_sparse_prefix_and_no_cheap(plan):
    script = c.worker_script("main", p.PLAN, "a" * 40, "2026-10-06T00:00:00+00:00", plan)
    assert "experiments.berg_dose_exposure_continuation.runner" in script
    assert "--deadline-utc" in script and "--filter=blob:none" in script
    assert p.RELEASE + "/raw/failed.json" in script
    assert "exposure-calibration-000-target-025-+1.json" in script
    assert p.PLAN in c.sparse_paths(p.PLAN, plan)
    assert "data" not in c.sparse_paths(p.PLAN, plan)
    assert subprocess.run(["bash", "-n"], input=script, text=True, capture_output=True).returncode == 0
    with pytest.raises(ValueError):
        c.worker_script("cheap", p.PLAN, "a" * 40, "2026-10-06T00:00:00+00:00", plan)


@pytest.fixture
def study(tmp_path, monkeypatch, plan):
    # Real prefix is validated above; loop tests do not repeatedly parse 37 MB.
    monkeypatch.setattr(p, "verify_prefix", lambda: None)
    s = runner.Study.__new__(runner.Study)
    s.plan, s.out = deepcopy(plan), tmp_path
    write_once(tmp_path / "PLAN.json", s.plan)
    s.plan_hash, s.freeze = p.sha(tmp_path / "PLAN.json"), "a" * 40
    write_once(tmp_path / "runtime.json", {"plan_sha256": s.plan_hash, "freeze_commit": s.freeze})
    s.ledger = EventLedger(tmp_path / "receipts.jsonl", s.plan_hash, s.freeze,
                          ["qualification-live"] + [r["id"] for r in s.plan["rows"]])
    s.ledger.bind("runtime", {"kind": "runtime"})
    s.completed, s.clock, s.deadline, s.barriers = {}, lambda: 0, 17000, False
    metadata = json.loads(next((p.ROOT / p.RELEASE / "raw").glob("model-bf16-load-*.json")).read_text())
    s.backend = SimpleNamespace(metadata=metadata)
    s.model = Mock()
    s.qualification = lambda: {"id": "qualification-live", "result": {"pass": True, "zero_hidden_bit_exact": True},
        "judge_fixtures": {"pass": True}, "geometry": {"requested_norm_matched": True}}
    s.dispatched = []
    def trial(spec):
        s.dispatched.append(spec["id"])
        return synthetic_row(spec)
    s.trial = trial
    s.barrier_records = []
    s.barrier = lambda name: s.barrier_records.append((name, len(s.completed)))
    return s


def test_complete_main_only_no_calibration_or_reselection(study):
    study.execute()
    assert study.dispatched == [r["id"] for r in study.plan["rows"]]
    assert len(study.completed) == 481
    assert study.barrier_records == [("qualification", 1), ("first-five", 6)]
    assert a.audit(study.out, study.plan, partial=False, settled=True)["generations"] == 480
    assert json.loads((study.out / "selection.json").read_text()) == study.plan["continuation"]["selection"]
    summary = json.loads((study.out / "analysis/summary.json").read_text())
    assert set(summary["results"]) == {"notebook", "paper"}
    assert summary["results"]["notebook"]["target"]["estimate_complete_pairs"] == 0


def test_old_throughput_margin_is_not_overridden(study):
    study.deadline = 15000
    with pytest.raises(TimeoutError, match="480-trial"):
        study.execute()
    assert study.dispatched == [] and len(study.completed) == 1
    assert not json.loads((study.out / "throughput.json").read_text())["pass"]


def test_runtime_change_stops_before_qualification(study):
    study.backend.metadata["torch_version"] = "changed"
    with pytest.raises(ValueError, match="runtime changed"):
        study.execute()
    assert not study.completed and not study.dispatched


def test_trial_rejects_calibration_before_backend(plan):
    s = runner.Study.__new__(runner.Study)
    s.plan = plan
    with pytest.raises(ValueError, match="remaining main"):
        s.trial(p.old.inventory()[0])


def test_pending_trial_is_not_regenerated(study):
    spec = study.plan["rows"][0]
    study.ledger.bind("dispatch:" + spec["id"], {"kind": "dispatch", "row_id": spec["id"]})
    with pytest.raises(RuntimeError, match="do not regenerate"):
        study.row(spec["id"], lambda: pytest.fail("Redispatched"))


def test_foreign_order_and_changed_selection_fail_audit(study):
    study.deadline = 15000
    with pytest.raises(TimeoutError):
        study.execute()
    selection = json.loads((study.out / "selection.json").read_text())
    selection["selected_dose"] = .5
    (study.out / "selection.json").write_text(p.canonical(selection) + "\n")
    with pytest.raises(ValueError):
        a.audit(study.out, study.plan, settled=True)


@pytest.fixture
def control(tmp_path, monkeypatch, plan):
    root = tmp_path.resolve()
    path = root / p.PLAN
    write_once(path, plan)
    out = root / "out/continuation"
    rig = SimpleNamespace(now=datetime(2026, 10, 5, tzinfo=timezone.utc), ticks=0)
    def advance(seconds):
        rig.now += timedelta(seconds=seconds)
        rig.ticks += seconds
    api = FakeAPI(rig)
    api.kind = "main"
    monkeypatch.setattr(c, "ROOT", root)
    monkeypatch.setattr(c, "OWNED_OUT", out)
    monkeypatch.setattr(c, "load_plan", lambda *args: deepcopy(plan))
    monkeypatch.setattr(c.base, "verify_public", Mock())
    monkeypatch.setattr(p, "verify_cheap_receipt", Mock())
    key = root / "key"
    key.write_text("synthetic")
    Path(str(key) + ".pub").write_text("ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAITest test-only")
    monkeypatch.setattr(c.base, "KEY", key)
    monkeypatch.setenv("HF_TOKEN", "synthetic-test-only")
    monkeypatch.setattr("urllib.request.OpenerDirector.open", Mock(side_effect=AssertionError("No network")))
    ctrl = c.Controller(path, "a" * 40, out, "main", api, clock=lambda: rig.now,
                        monotonic=lambda: rig.ticks, sleep=advance, run=Mock(side_effect=AssertionError("No SSH")))
    ctrl.disk_check, ctrl.start_worker = Mock(), Mock()
    return ctrl, api, advance


def test_controller_new_single_owned_pod_with_exact_carry(control):
    ctrl, api, _ = control
    ctrl.launch()
    intent = ctrl.event("create-intent")["data"]
    assert intent["prior_total_usd"] == p.PRIOR_USD and intent["prior_new_usd"] == "0"
    assert api.pod["name"].startswith("codex-dose-exposure-continuation-20261005-main-")
    assert ctrl.hard_seconds == 17460
    assert ctrl.cost_check(api.pod) == 0
    with pytest.raises(ValueError, match="replacement"):
        ctrl.launch()
    assert sum(method == "POST" for method, _, _ in api.calls) == 1


def test_controller_timer_preserves_cleanup_and_holdback(control):
    ctrl, api, advance = control
    ctrl.launch()
    advance(16800)
    with pytest.raises(ValueError, match="deadline"):
        ctrl.cost_check(api.pod)
    assert ctrl.event("create-intent")["data"]["hard_deadline_utc"] != ctrl.event("create-intent")["data"]["deadline_utc"]


def test_controller_wrong_rate_never_creates(control, monkeypatch):
    ctrl, api, _ = control
    monkeypatch.setattr(c.base, "quote", lambda *args: {"hourly_rate_usd": "7", "storage_hourly_usd": ".10"})
    with pytest.raises(ValueError, match="not funded"):
        ctrl.launch()
    assert not any(method == "POST" for method, _, _ in api.calls)


def test_controller_no_cheap_or_foreign_root(control):
    ctrl, api, _ = control
    with pytest.raises(ValueError, match="main-only"):
        c.Controller(ctrl.plan_path, ctrl.freeze, ctrl.out, "cheap", api)
    with pytest.raises(ValueError, match="canonical"):
        c.Controller(ctrl.plan_path, ctrl.freeze, ctrl.out / "reset", "main", api)


def test_controller_closure_carries_all_prior_cost_and_verifies_deletion(control):
    ctrl, api, advance = control
    ctrl.launch()
    advance(120)
    result = ctrl.terminate()
    closed = ctrl.event("closed")["data"]
    assert result and closed["get_status"] == 404 and api.deleted
    assert closed["within_limits"] is True
    cost = Decimal("6.89") * 120 / 3600
    assert Decimal(closed["compute_upper_bound_usd"]) == cost
    assert Decimal(closed["cumulative_upper_bound_usd"]) == Decimal(p.PRIOR_USD) + cost


@pytest.mark.parametrize("overdue", [False, True])
def test_failed_recovery_is_bounded_then_owned_pod_deleted(control, overdue):
    ctrl, api, advance = control
    ctrl.launch()
    ctrl.retrieve = Mock(side_effect=RuntimeError("SSH unavailable"))
    if overdue:
        advance(c.MAIN_SECONDS + 1)
    result = ctrl.close_until_verified()["data"]
    assert api.deleted and result["get_status"] == 404
    assert ctrl.retrieve.call_count == (0 if overdue else c.RECOVERY_ATTEMPTS)
    assert result["retrieval_verified"] is False and result["artifacts_may_be_unrecovered"]
    assert result["within_limits"] is not overdue
    assert ctrl.event("emergency-delete-permit") and ctrl.event("recovery-exhausted")
    assert not (ctrl.base / "final-retrieval.json").exists()
    assert [(m, path) for m, path, _ in api.calls if m == "DELETE"] == [("DELETE", "/pods/owned1")]


def test_recovery_subprocess_timeout_preserves_deletion_window(control):
    ctrl, api, advance = control
    ctrl.launch()
    advance(c.MAIN_SECONDS - c.DELETE_RESERVE_SECONDS - 12)
    observed = []
    def stalled_run(*args, **kwargs):
        observed.append(kwargs["timeout"])
        advance(kwargs["timeout"])
        raise subprocess.TimeoutExpired("synthetic-retrieval", kwargs["timeout"])
    ctrl.run = stalled_run
    ctrl.retrieve = lambda **kwargs: ctrl.run(["synthetic"], timeout=300)
    ctrl.close_until_verified()
    assert observed == [12] and api.deleted
    assert ctrl.run is stalled_run
    assert ctrl.event("closed")["data"]["within_limits"]


def test_invalid_existing_receipt_is_preserved_not_replaced(control):
    ctrl, api, _ = control
    ctrl.launch()
    receipt = ctrl.base / "final-retrieval.json"
    receipt.write_bytes(b"corrupt preserved receipt\n")
    ctrl.close_until_verified()
    assert api.deleted and receipt.read_bytes() == b"corrupt preserved receipt\n"
    assert ctrl.event("closed")["data"]["retrieval_verified"] is False


@pytest.mark.parametrize("recovered", [False, True])
def test_resume_after_permit_does_not_reset_recovery_or_duplicate_delete(control, recovered):
    ctrl, api, _ = control
    ctrl.launch()
    if not recovered:
        ctrl.retrieve = Mock(side_effect=RuntimeError("SSH unavailable"))
    bind = ctrl.ledger.bind
    def interrupted_bind(identifier, data):
        if identifier == "delete-intent":
            raise KeyError("synthetic interruption before DELETE intent")
        return bind(identifier, data)
    ctrl.ledger.bind = interrupted_bind
    with pytest.raises(KeyError):
        ctrl.terminate()
    assert not api.deleted
    ctrl.ledger.bind = bind
    ctrl.terminate()
    assert api.deleted and ctrl.event("closed")["data"]["retrieval_verified"] is recovered
    if not recovered:
        assert ctrl.retrieve.call_count == c.RECOVERY_ATTEMPTS
    assert sum(method == "DELETE" for method, _, _ in api.calls) == 1


@pytest.mark.parametrize("failure", [KeyboardInterrupt, KeyError, SystemExit])
@pytest.mark.parametrize("location", ["launch", "monitor"])
def test_unexpected_errors_cleanup_then_preserve_original_exception(control, failure, location):
    ctrl, api, _ = control
    if location == "launch":
        ctrl.start_worker.side_effect = failure("synthetic failure")
    else:
        ctrl.launch()
        ctrl.status = Mock(side_effect=failure("synthetic failure"))
    with pytest.raises(failure):
        getattr(ctrl, location)()
    assert api.deleted and ctrl.event("closed")["data"]["get_status"] == 404
    assert sum(method == "POST" for method, _, _ in api.calls) == 1


def test_interrupted_create_is_reconciled_by_saved_identity_then_deleted(control):
    ctrl, api, _ = control
    request = api.request
    def interrupted_request(method, path, body=None):
        result = request(method, path, body)
        if method == "POST":
            raise KeyboardInterrupt()
        return result
    api.request = interrupted_request
    with pytest.raises(KeyboardInterrupt):
        ctrl.launch()
    assert api.deleted and ctrl.event("created") and ctrl.event("closed")
    assert sum(method == "POST" for method, _, _ in api.calls) == 1
    ctrl.start_worker.assert_not_called()


def test_ambiguous_delete_is_verified_without_second_delete(control):
    ctrl, api, _ = control
    ctrl.launch()
    request = api.request
    def uncertain(method, path, body=None):
        result = request(method, path, body)
        if method == "DELETE":
            raise RuntimeError("Lost DELETE response")
        return result
    api.request = uncertain
    result = ctrl.close_until_verified()
    assert result == ctrl.close_until_verified()
    assert result["data"]["get_status"] == 404
    assert sum(method == "DELETE" for method, _, _ in api.calls) == 1


@pytest.mark.parametrize("fault", ["delete_stays", "inventory_stays"])
def test_unverified_deletion_is_bounded_and_not_claimed_closed(control, fault):
    ctrl, api, advance = control
    ctrl.launch()
    setattr(api, fault, True)
    advance(c.MAIN_SECONDS + 1)
    for _ in range(2):
        with pytest.raises(RuntimeError, match="retain reservation"):
            ctrl.close_until_verified()
    assert not ctrl.event("closed")
    assert sum(method == "DELETE" for method, _, _ in api.calls) == 1
    assert len([r for r in ctrl.ledger.read() if r["id"].startswith("delete-verification-failed:")]) == 2 * c.DELETE_CHECKS
    assert any(r["id"].startswith("cleanup-unresolved:") for r in ctrl.ledger.read())


@pytest.mark.parametrize("sig", [signal.SIGTERM, signal.SIGHUP])
def test_cli_signal_cleans_up_and_restores_handlers(control, monkeypatch, sig):
    ctrl, api, _ = control
    ctrl.launch()
    before = {s: signal.getsignal(s) for s in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP)}
    monkeypatch.setattr(c, "Controller", lambda *args, **kwargs: ctrl)
    monkeypatch.setattr(c.base, "RunPodV2", lambda *args, **kwargs: api)
    monkeypatch.setattr("dotenv.load_dotenv", Mock())
    ctrl.monitor = lambda: signal.getsignal(sig)(sig, None)
    with pytest.raises(SystemExit) as exc:
        c.main(["--plan", str(ctrl.plan_path), "--freeze", ctrl.freeze, "--action", "monitor", "--launch"])
    assert exc.value.code == 128 + sig
    assert api.deleted and ctrl.event("closed")
    assert all(signal.getsignal(s) == handler for s, handler in before.items())

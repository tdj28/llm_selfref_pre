"""Synthetic offline continuation tests; no provider or research calls."""
from contextlib import contextmanager
from copy import deepcopy
from decimal import Decimal, getcontext
import io
from pathlib import Path
from unittest.mock import Mock

import pytest

from experiments import kolibri_budget_continuation as c
from experiments.kolibri_swap import production as prod, protocol
from experiments.openrouter_swap.ledger import Halted
from tests.test_kolibri_generation_waves import setup as wave_setup, a5_setup, opened as wave_opened, OP_FREEZE
from tests.test_kolibri_bootstrap_a5 import CHEAP
from tests.test_kolibri_swap_controller import Clock, FakeAPI, saved_retrieval
from tests.test_kolibri_swap_production import FREEZE, write, tree_hashes
from tests.test_kolibri_swap_runtime import senders

NEW_FREEZE = "c" * 40


@pytest.fixture
def continuation(wave_setup):
    local, judge, _, _ = senders()
    with wave_opened(wave_setup, local, judge) as runner:
        runner.generate_blocks("screen")
        pending = c.unfinished(runner)
    original = Path(c.__file__).resolve().parents[1]
    for name in c.SOURCES:
        target = protocol.ROOT / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((original / name).read_bytes())
    value = {"schema": "synthetic-kolibri-budget-continuation", "source_hashes": c.sources(),
        "caps_usd": deepcopy(c.CAPS), "prefix": c.waves.prefix(wave_setup[0][1] / "collection"),
        "undispatched_screen_judgments": pending, "predecessor": {"gpu_carry_usd": "10.3",
            "closed_sha256": "d" * 64, "startup_seconds": "725", "pod_id": "synthetic-old"},
        "new_main_cap_usd": "19.7",
        "qualified_a4_cheap_reused": {"freeze": c.a5.A4_FREEZE, "pod_id": c.a5.QUALIFIED_POD, **CHEAP}}
    write(protocol.ROOT / c.PLAN, value)
    return wave_setup, value


@contextmanager
def opened(continuation, judge=None):
    setup, value = continuation
    with wave_opened(setup) as base:
        if base.receipts.decision("budget_continuation") is None:
            base.receipts.append("decision", {"name": "budget_continuation", "value": c.binding(NEW_FREEZE, value)})
        runner = c.Runner(base.plan, FREEZE, base.plan_hash, base.ledger, base.receipts, judge_sender=judge,
            amendment=base.amendment, transport_plan=base.transport_plan, wave_plan=base.wave_plan,
            wave_freeze=OP_FREEZE, continuation=value, continuation_freeze=NEW_FREEZE, sleep=Mock())
        runner.guard = Mock()
        yield runner


def test_only_undispatched_judgments_resume_and_replay_never_sends(continuation):
    _, judge, _, seen = senders()
    before = c.waves.prefix(continuation[0][0][1] / "collection")
    with opened(continuation, judge) as runner:
        assert len(continuation[1]["undispatched_screen_judgments"]) == 160
        runner.judge_blocks("screen")
        assert len(seen) == 160 and runner.qualification()["eligible_models"] == ["kolibri"]
        c.waves.check_prefix(runner.receipts.root.parent, before)
        saved = tree_hashes(runner.receipts.root)
        runner.judge_blocks("screen")
        assert len(seen) == 160 and saved == tree_hashes(runner.receipts.root)
        assert runner.audit()["budget_continuation"] == c.binding(NEW_FREEZE, continuation[1])


def test_source_and_prefix_tamper_fail_closed(continuation):
    with opened(continuation) as runner:
        runner.continuation["prefix"]["journals"]["http/events.jsonl"]["sha256"] = "0" * 64
        with pytest.raises(Halted): runner.audit()
        runner.continuation = deepcopy(continuation[1])
        path = protocol.ROOT / c.SOURCES[0]
        path.write_bytes(path.read_bytes() + b"\n# Synthetic tamper\n")
        with pytest.raises(Halted): runner.check_sources()


@pytest.mark.parametrize("gpu,api,phase,passes", [("10.3", "4.3", "screen", True),
    ("21", "4", "screen", False), ("10", "40", "main", False), ("30", "39.9", "main", False),
    ("1", "1", "fixtures", False)])
def test_every_full_reservation_obeys_total_category_and_pilot(monkeypatch, gpu, api, phase, passes):
    guard = object.__new__(c.StudyGuard)
    guard.state = Mock(return_value={"gpu_usd": Decimal(gpu)})
    guard.ledger = Mock(); guard.ledger.spent.return_value = Decimal(api)
    monkeypatch.setattr(c, "reservation", lambda *args: Decimal(".2"))
    if passes:
        guard.before_call("judge", phase, {}, {})
    else:
        with pytest.raises(Halted): guard.before_call("judge", phase, {}, {})


@pytest.mark.parametrize("qualified,gpu,api,seconds,remaining,passes", [
    (True, "27", "35", "12312", "14000", True), (False, "27", "35", "12312", "14000", False),
    (True, "30.1", "35", "12312", "14000", False), (True, "27", "40.1", "12312", "14000", False),
    (True, "27", "35", "12312", "12000", False)])
def test_rebalance_never_weakens_science_or_thirty_percent_forecast(monkeypatch, qualified, gpu, api, seconds, remaining, passes):
    original = {"fits": False, "qualified": qualified, "gpu_completion_usd": gpu,
        "judge_completion_usd": api, "combined_completion_usd": str(Decimal(gpu) + Decimal(api) + 5),
        "main_seconds_with_margin": seconds, "margin": "1.30"}
    monkeypatch.setattr(c.waves.Runner, "main_admission", lambda *args, **kwargs: deepcopy(original))
    runner = object.__new__(c.Runner)
    runner.continuation, runner.continuation_freeze = {"schema": "synthetic", "predecessor": {"closed_sha256": "d" * 64}}, NEW_FREEZE
    result = runner.main_admission(storage_bound_usd="5", gpu_remaining_seconds=remaining)
    assert result["fits"] is passes and result["margin"] == "1.30"
    assert result["prior_category_forecast_preserved"] == original


def test_prelaunch_includes_startup_margin_and_all_carried_costs(tmp_path, monkeypatch):
    monkeypatch.setattr(c, "root", lambda: tmp_path)
    plan = {"budget": {"gpu_hourly_usd": "4.59"}}
    value = {"predecessor": {"gpu_carry_usd": "10.3", "startup_seconds": "725", "closed_sha256": "a" * 64},
             "new_main_cap_usd": "19.7"}
    guard = c.StudyGuard(plan, Mock(), value, NEW_FREEZE)
    assert guard.state()["gpu_usd"] == Decimal("10.3")
    with pytest.raises(Halted): guard.state(running=True)
    runner = Mock(plan=plan)
    runner.main_admission.return_value = {"main_seconds_with_margin": "12312", "fits": True}
    guard.admission(runner)
    evidence = runner.main_admission.call_args.kwargs
    assert Decimal(evidence["gpu_spent_usd"]) == Decimal("10.3") + Decimal("725") * Decimal("1.30") * Decimal("4.69") / 3600
    assert evidence["remaining_overhead_seconds"] == "600"
    runner.main_admission.return_value = {"main_seconds_with_margin": "20000", "fits": True}
    with pytest.raises(Halted): guard.admission(runner)


@pytest.mark.parametrize("qualified", [True, False])
def test_controller_requires_completed_scientific_gate_before_creation(monkeypatch, qualified):
    ctl = object.__new__(c.Controller)
    ctl.freeze = NEW_FREEZE
    ctl.continuation = {"qualified_a4_cheap_reused": {"freeze": c.a5.A4_FREEZE, "pod_id": c.a5.QUALIFIED_POD, **CHEAP}}
    monkeypatch.setattr(c.a5, "qualification", lambda *args: deepcopy(CHEAP))
    monkeypatch.setattr(c.a5.a4, "verify", lambda: {})
    runner = Mock()
    runner.qualification.return_value = {"eligible_models": ["kolibri"] if qualified else []}
    admission = {"evidence": {}, "fits": True}
    runner.receipts.decision.return_value = admission; runner.main_admission.return_value = admission
    @contextmanager
    def saved(*args): yield runner
    monkeypatch.setattr(c, "saved_runner", saved)
    if qualified:
        assert ctl.cheap_pass() == CHEAP
    else:
        with pytest.raises(Halted, match="Scientific screen"): ctl.cheap_pass()
    runner.complete.assert_called_once_with("screen")


def test_single_owned_replacement_reuses_worker_and_closes_directly(tmp_path, monkeypatch):
    plan = protocol.verify(protocol.ROOT / protocol.PLAN)
    body = (protocol.ROOT / protocol.PLAN).read_bytes()
    repo = tmp_path / "synthetic-repo"
    repo.mkdir()
    value = {"schema": "synthetic", "new_main_cap_usd": "19.7", "predecessor": {
        "gpu_carry_usd": "10.3", "closed_sha256": "a" * 64, "pod_id": "old-screen-pod"},
        "qualified_a4_cheap_reused": {"freeze": c.a5.A4_FREEZE, "pod_id": c.a5.QUALIFIED_POD, **CHEAP}}
    monkeypatch.setattr(c, "verify", lambda freeze: deepcopy(value))
    monkeypatch.setattr(protocol, "ROOT", repo)
    monkeypatch.setattr(protocol, "verify", lambda *args: deepcopy(plan))
    monkeypatch.setattr(c, "root", lambda: tmp_path / "replacement")
    monkeypatch.setattr(c.old, "quote", lambda *args: {"hourly_rate_usd": "4.59", "storage_hourly_usd": ".10"})
    monkeypatch.setattr(c.a5.a4.urllib.request, "urlopen", lambda *args, **kwargs: io.BytesIO(body))
    key = repo / "synthetic-key"; key.write_text("Synthetic noncredential")
    Path(str(key) + ".pub").write_text("ssh-ed25519 AAAA synthetic")
    monkeypatch.setattr(c.old.base, "KEY", key)
    clock = Clock()
    class API(FakeAPI):
        def request(self, method, path, body=None):
            if method == "GET" and path.startswith("/pods?"):
                return 200, {"pods": self.inventory(), "pagination": {"hasNextPage": False}}
            status, result = super().request(method, path, body)
            if method == "POST": self.pod["cost"] = result["cost"] = "4.59"
            return status, result
    api = API(clock)
    ctl = c.Controller(NEW_FREEZE, api, clock=clock, sleep=clock.sleep)
    ctl.cheap_pass = Mock(return_value=CHEAP)
    ctl._ssh = Mock(side_effect=lambda pod, command, **kwargs: b"ready" if command == "printf ready" else b"dispatched")
    ctl.launch()
    upload = next(call.kwargs["data"] for call in ctl._ssh.call_args_list if "data" in call.kwargs)
    assert b"experiments.kolibri_bootstrap_a5.cli" in upload and b"--no-enable-log-requests" in upload
    assert b"--disable-log-requests" not in upload and api.calls.count(("POST", "/pods")) == 1
    assert ctl.event("create-intent")["data"]["cap_usd"] == "19.7"
    assert not (ctl.out / "controller/cheap").exists()
    with pytest.raises(Halted): ctl.launch()
    saved_retrieval(ctl); clock.sleep(60)
    assert ctl.terminate()["data"]["get_status"] == 404


def test_scientific_budget_projection_is_explicit_and_leaves_original_unchanged():
    original = protocol.verify(protocol.ROOT / protocol.PLAN)
    before = deepcopy(original)
    projected = c.budget_projection(original)
    assert original == before
    assert projected["budget"]["gpu_usd"] == "30" and projected["budget"]["judges_usd"] == "40"
    assert projected["budget"]["new_total_usd"] == "75"
    assert {k: v for k, v in original.items() if k != "budget"} == {k: v for k, v in projected.items() if k != "budget"}
    assert not set(c.SOURCES) & set(original["source_hashes"])


def test_predecessor_does_not_change_decimal_context_of_frozen_verifiers(monkeypatch):
    def old_verify():
        assert getcontext().prec == 28
        return {"predecessor": {"cost_usd": "1.94695653900638706083333335"}}
    monkeypatch.setattr(c.a5, "verify", old_verify)
    monkeypatch.setattr(prod, "closed_receipt", lambda *args: {"cost_usd": "8.343854838763888888888888889"})
    monkeypatch.setattr(prod, "controller_events", lambda *args: ([], {
        "created": {"data": {"id": "synthetic-old"}}, "server-ready": {"data": {"elapsed_seconds": "725"}},
        "create-intent": {"data": {"deadline_utc": "2026-10-05T15:14:31+00:00"}}}))
    assert c.predecessor()["gpu_carry_usd"] == "10.290811377770275949722222239"


def test_approval_chronology_does_not_invent_a_larger_owner_budget():
    assert c.AUTHORITY["subsequent_human_approval"] == "Approved, continue"
    assert c.AUTHORITY["approval_recorded_utc"] == "2026-10-05T12:39:16+00:00"
    assert c.AUTHORITY["direct_owner_total_usd"] == "75"
    assert c.AUTHORITY["additional_total_authorized_usd"] == "0"
    assert "parent_agent" in c.AUTHORITY["allocation_origin"]


def test_saved_continuation_bytes_are_not_an_optional_binding(tmp_path, monkeypatch):
    monkeypatch.setattr(c.a5, "root", lambda: tmp_path / "run")
    monkeypatch.setattr(protocol, "ROOT", tmp_path / "repo")
    write(protocol.ROOT / c.PLAN, {"synthetic": True})
    write(c.a5.root() / "collection/CONTINUATION.json", {"synthetic": False})
    with pytest.raises(Halted, match="Saved continuation bytes"):
        with c.saved_runner({}, NEW_FREEZE): pass

"""Additional endpoint, cumulative-carry and raw-projection regression gates."""

from copy import deepcopy
from decimal import Decimal

import pytest

from experiments.openrouter_swap import protocol as common
from experiments.openrouter_swap.ledger import Halted, BudgetExceeded
from experiments.openrouter_swap.providers import generation_request, reservation as common_reservation
from experiments.openrouter_swap_openweights.runner import ExtensionRunner as OriginalRunner
from experiments.openrouter_swap_openweights_a1 import production as prod, protocol as p
from experiments.openrouter_swap_openweights_a1.accounting import reservation
from experiments.openrouter_swap_openweights_a1.runner import ExtensionRunner, SharedLedger, private_request
from tests.test_openrouter_openweights_a1_accounting import budget
from tests.test_openrouter_openweights_a1_production import inputs, synthetic_plan, fake_sender, forbid_network


@pytest.mark.parametrize("judge", ["astra", "opus"])
@pytest.mark.parametrize("record", ["endpoint", "zdr_endpoint"])
@pytest.mark.parametrize("missing", ["structured_outputs", "response_format"])
def test_response_format_alone_never_qualifies_a_judge(judge, record, missing):
    b = budget(); values = inputs(b)
    evidence = values["endpoint_evidence"][p.JUDGES[judge]["id"]]
    evidence["catalog"][record]["supported_parameters"].remove(missing)
    evidence["catalog_sha256"] = common.digest(evidence["catalog"])
    with pytest.raises(Halted, match="capabilities"):
        prod.finalize(p.build_draft(budget=b), **values)


@pytest.mark.parametrize("change", ["route", "provider", "model", "hash", "temperature", "price", "cap", "zdr"])
def test_exact_endpoint_settings_and_privacy_not_assertion_only(change):
    b = budget(); values = inputs(b)
    evidence = values["endpoint_evidence"][p.MODELS["mistral"]["id"]]
    endpoint = evidence["catalog"]["endpoint"]
    if change == "route": endpoint["tag"] = "mistral"
    if change == "provider": endpoint["provider_name"] = "Other"
    if change == "model": endpoint["model_id"] = "other/model"
    if change == "temperature": endpoint["supported_parameters"].remove("temperature")
    if change == "price": endpoint["pricing"]["completion"] = "1"
    if change == "cap": endpoint["max_completion_tokens"] = 4000
    if change == "zdr": evidence["catalog"]["zdr_endpoint"] = {}
    evidence["catalog_sha256"] = "a"*64 if change == "hash" else common.digest(evidence["catalog"])
    with pytest.raises(Halted): prod.finalize(p.build_draft(budget=b), **values)


@pytest.mark.parametrize("record", ["endpoint", "zdr_endpoint"])
@pytest.mark.parametrize("status", [None, 1, -1, False, "0", 0.0])
def test_only_integer_zero_endpoint_status_is_accepted(record, status):
    b = budget(); values = inputs(b)
    evidence = values["endpoint_evidence"][p.JUDGES["opus"]["id"]]
    evidence["catalog"][record]["status"] = status
    evidence["catalog_sha256"] = common.digest(evidence["catalog"])
    with pytest.raises(Halted, match="status"):
        prod.finalize(p.build_draft(budget=b), **values)


@pytest.mark.parametrize("change", ["carry", "missing", "hash", "label", "scope-reset", "screen-reset", "cap"])
def test_no_prior_failure_or_unresolved_cost_reset(change):
    options = {}
    if change == "scope-reset": options["prior_spend_usd"] = "84.08770746"
    if change == "screen-reset": options["screening_allowance_usd"] = "25"
    if change == "cap": options.update(hard_cap_usd="250", working_cap_usd="250")
    b = budget(**options); values = inputs(b)
    carry = values["reconciliation"]["prior_costs"][0]
    if change == "carry": carry["cost_bound_usd"] = "84.08770746"
    if change == "missing": values["reconciliation"]["prior_costs"] = []
    if change == "hash": carry["evidence_sha256"] = "a"*64
    if change == "label": carry["id"] = "not-the-failure"
    with pytest.raises(Halted): prod.finalize(p.build_draft(budget=b), **values)
    with pytest.raises(Halted): prod.reconcile(b, values["reconciliation"])


def test_budget_has_exact_prior_carry_and_independent_a1_root(monkeypatch):
    b = budget(external_commitments_usd="0")
    plan = prod.finalize(p.build_draft(budget=b), **inputs(b))
    assert b.limits() == (Decimal("115.35724664"), Decimal("24.4449541"))
    assert b.admission(spent_usd="1", remaining_usd="114.35724664")["fits"]
    assert not b.admission(spent_usd="1", remaining_usd="114.35724665")["fits"]
    assert plan["amendment"]["predecessor"]["unresolved"] == 3
    assert plan["judges"]["opus"]["provider_slug"] == "google-vertex/us"
    assert plan["judges"]["opus"]["provider_name"] == "Google"
    monkeypatch.setattr(prod.subprocess, "check_output", lambda *a, **k: "/synthetic/repo/.git\n")
    assert prod.canonical_root().as_posix() == "/synthetic/repo/out/openrouter-openweights-a1-v1"


def test_scientific_execution_and_qualification_methods_still_frozen():
    for name in ("run_blocks", "main_admission", "complete", "require_fixtures", "generate", "judge", "rows"):
        assert getattr(ExtensionRunner, name) is getattr(OriginalRunner, name)


@pytest.mark.parametrize("path", [p.OLD_PLAN, p.PREDECESSOR_RELEASE])
def test_predecessor_plan_and_release_are_byte_bound(monkeypatch, path):
    original = common.sha
    monkeypatch.setattr(common, "sha", lambda value: "a"*64 if value == common.ROOT / path else original(value))
    with pytest.raises(Halted, match="Predecessor"):
        prod.source_hashes()


def test_accounting_projection_reconstructs_exact_raw_and_full_reserve(tmp_path, monkeypatch):
    plan, _, runtime, _ = synthetic_plan(tmp_path, monkeypatch)
    sender, sent = fake_sender(plan)
    cap, screen = budget().limits()
    with SharedLedger(tmp_path / "raw", cap=cap, screen_cap=screen) as ledger:
        r = ExtensionRunner(plan, runtime["freeze"], runtime["plan_sha256"], ledger, sender)
        assert r.route_fixture("mistral")["pass"]
        row = ledger.rows()[0]
        original = (tmp_path / "raw/events.jsonl").read_bytes()
        assert row["raw"]["usage"]["completion_tokens"] == 57
        assert row["raw"]["usage"]["completion_tokens_details"]["reasoning_tokens"] == 59
        assert Decimal(row["reservation_usd"]) == reservation(p.MODELS["mistral"], row["request"])
        assert Decimal(row["reservation_usd"]) == common_reservation(p.MODELS["mistral"], row["request"]) + Decimal(".03072")
        assert Decimal(row["cost_usd"]) == Decimal(".0009")
        audit = r.audit()
        reserve = audit["mistral_reservations"][0]
        assert reserve["reservation_usd"] == row["reservation_usd"]
        assert Decimal(reserve["padding_usd"]) == Decimal(".03072")
        assert reserve["padding_is_reported_charge"] is False
        report = audit["mistral_accounting"][0]
        assert report["discrepancy"] is True and report["conservative_output_tokens"] == 116
        assert report["raw_sha256"] == row["raw_sha256"]
        assert (tmp_path / "raw/events.jsonl").read_bytes() == original
        r.route_fixture("mistral")
        assert len(sent) == 1
    with SharedLedger(tmp_path / "raw", cap=cap, screen_cap=screen) as ledger:
        assert ExtensionRunner(plan, runtime["freeze"], runtime["plan_sha256"], ledger).audit()["pass"]


@pytest.mark.parametrize("change", ["cost", "reasoning", "provider", "privacy", "reservation-low", "reservation-high"])
def test_valid_hash_chain_does_not_exempt_tampered_originals(tmp_path, monkeypatch, change):
    plan, _, runtime, _ = synthetic_plan(tmp_path, monkeypatch)
    sender, _ = fake_sender(plan)
    cap, screen = budget().limits()
    with SharedLedger(tmp_path / "original", cap=cap, screen_cap=screen) as ledger:
        r = ExtensionRunner(plan, runtime["freeze"], runtime["plan_sha256"], ledger, sender)
        r.route_fixture("mistral")
        row = ledger.rows()[0]
    if change == "cost": row["cost_usd"] = "0.0004575"
    if change == "reasoning": row["raw"]["usage"]["completion_tokens_details"]["reasoning_tokens"] = -1
    if change == "provider": row["raw"]["provider"] = "Other"
    if change == "privacy": row["request"]["provider"]["zdr"] = False
    if change == "reservation-low": row["reservation_usd"] = str(Decimal(row["reservation_usd"]) - Decimal(".03072"))
    if change == "reservation-high": row["reservation_usd"] = str(Decimal(row["reservation_usd"]) + Decimal(".000001"))
    with SharedLedger(tmp_path / "forged", cap=cap, screen_cap=screen) as ledger:
        ledger.reserve(row["call_id"], row["request"], row["reservation_usd"], row["phase"], row["metadata"])
        ledger.settle(row["call_id"], row["raw"], row["cost_usd"])
        with pytest.raises((Halted, ValueError)):
            ExtensionRunner(plan, runtime["freeze"], runtime["plan_sha256"], ledger).audit()


@pytest.mark.parametrize("bad", ["missing", "negative", "overrun"])
def test_mistral_unknown_or_overrun_blocks_new_dispatch(tmp_path, monkeypatch, bad):
    plan, _, runtime, _ = synthetic_plan(tmp_path, monkeypatch)
    sender, sent = fake_sender(plan)
    def broken(request):
        value = sender(request)
        if bad == "missing": value["usage"].pop("total_tokens")
        if bad == "negative": value["usage"]["completion_tokens_details"]["reasoning_tokens"] = -1
        if bad == "overrun": value["usage"]["cost"] = "1"
        return value
    cap, screen = budget().limits()
    with SharedLedger(tmp_path / "raw", cap=cap, screen_cap=screen) as ledger:
        r = ExtensionRunner(plan, runtime["freeze"], runtime["plan_sha256"], ledger, broken)
        if bad == "overrun": r.route_fixture("mistral")
        else:
            with pytest.raises(Halted): r.route_fixture("mistral")
        row = ledger.rows()[0]
        assert Decimal(row["cost_usd"]) >= Decimal(row["reservation_usd"])
        with pytest.raises(Halted): r.run_blocks("screen", initial=True)
        assert len(sent) == 1
        audit = r.audit()
        assert audit["mistral_reservations"][0]["reservation_usd"] == row["reservation_usd"]
        assert Decimal(audit["cost_bound_usd"]) == ledger.spent()


@pytest.mark.parametrize("total", [8212, 4115])
def test_two_full_output_components_fit_padded_reserve_without_changing_raw(tmp_path, monkeypatch, total):
    plan, _, runtime, _ = synthetic_plan(tmp_path, monkeypatch)
    sender, _ = fake_sender(plan)
    def full_components(request):
        value = sender(request)
        value["usage"] = {"prompt_tokens": 20, "completion_tokens": 4096, "total_tokens": total,
                          "completion_tokens_details": {"reasoning_tokens": 4096}, "cost": "0.03075"}
        return value
    cap, screen = budget().limits()
    with SharedLedger(tmp_path / "raw", cap=cap, screen_cap=screen) as ledger:
        r = ExtensionRunner(plan, runtime["freeze"], runtime["plan_sha256"], ledger, full_components)
        assert r.route_fixture("mistral")["pass"]
        row = ledger.rows()[0]
        assert row["status"] == "settled" and not row["over_reservation"]
        assert Decimal(row["cost_usd"]) == Decimal(".06147")
        assert common_reservation(p.MODELS["mistral"], row["request"]) < Decimal(row["cost_usd"]) < Decimal(row["reservation_usd"])
        original = (tmp_path / "raw/events.jsonl").read_bytes()
        audit = r.audit()
        record = audit["mistral_accounting"][0]
        assert record["discrepancy"] and record["conservative_output_tokens"] == 8192
        assert record["reported_charge_usd"] == "0.03075"
        assert row["raw"]["usage"]["total_tokens"] == total
        assert (tmp_path / "raw/events.jsonl").read_bytes() == original
        r.require_resolved()


def test_holdback_admission_uses_actual_padded_reservation_before_dispatch(tmp_path, monkeypatch):
    plan, _, runtime, _ = synthetic_plan(tmp_path, monkeypatch)
    sender, sent = fake_sender(plan)
    spec = p.MODELS["mistral"]
    request = private_request(generation_request(spec, [{"role": "user", "content": "Reply with exactly OK."}]))
    actual = reservation(spec, request)
    cap, screen = budget().limits()
    with SharedLedger(tmp_path / "raw", cap=cap, screen_cap=screen) as ledger:
        r = ExtensionRunner(plan, runtime["freeze"], runtime["plan_sha256"], ledger, sender)
        ledger.holdback = cap - actual + Decimal(".01536")
        with pytest.raises(BudgetExceeded): r.route_fixture("mistral")
        assert not sent and not ledger.rows()
        ledger.holdback = cap - actual
        assert r.route_fixture("mistral")["pass"]
        assert len(sent) == 1

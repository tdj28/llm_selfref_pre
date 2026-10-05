"""Offline checks for the separately frozen pre-target routing recovery."""

from copy import deepcopy
from decimal import Decimal
import json
import io

import pytest

from experiments.openrouter_swap import protocol
from experiments.openrouter_swap.ledger import Ledger, Halted
from experiments.openrouter_swap.providers import generation_request
from experiments.openrouter_swap.runner import Runner
from experiments.openrouter_swap_a1 import amendment
from tests.test_openrouter_swap_runner import make_sender


def test_original_source_bound_plan_still_valid():
    assert protocol.verify(protocol.ROOT / protocol.PLAN)["schema"] == "openrouter-swap-v1"


def test_amendment_scientific_inventory_unchanged():
    original = protocol.verify(protocol.ROOT / protocol.PLAN)
    amended = amendment.build()
    for key in ("screen", "main", "judges", "fixtures", "qualification", "analysis", "projection", "retries"):
        assert original[key] == amended[key]
    expected = deepcopy(original["models"])
    expected["deepseek"].pop("temperature")
    assert amended["models"] == expected
    assert Decimal(amended["cap_usd"]) + amendment.PRIOR_COST == 250
    assert Decimal(amended["screen_cap_usd"]) + amendment.PRIOR_COST == 40
    request = generation_request(amended["models"]["deepseek"], [{"role": "user", "content": "OK"}])
    assert "temperature" not in request
    assert request["provider"]["allow_fallbacks"] is False
    assert request["reasoning"] == {"effort": "low"}


def test_prior_ledger_change_blocks_recovery(tmp_path):
    (tmp_path / "raw").mkdir()
    (tmp_path / "raw/events.jsonl").write_text("altered")
    with pytest.raises(Halted, match="Prior ledger changed"):
        amendment.verify_prior(tmp_path)


def test_amendment_budget_cannot_reset(tmp_path):
    plan = amendment.build()
    with Ledger(tmp_path, cap=plan["cap_usd"], screen_cap=plan["screen_cap_usd"]) as ledger:
        with pytest.raises(Halted):
            ledger.reserve("too-much", {}, "250", "main", {})
        with pytest.raises(Halted):
            ledger.reserve("too-much-screen", {}, "40", "screen", {})


def test_amended_synthetic_fixtures_then_initial_screen(tmp_path):
    plan = amendment.build()
    sender, seen = make_sender()
    with Ledger(tmp_path, cap=plan["cap_usd"], screen_cap=plan["screen_cap_usd"]) as ledger:
        runner = Runner(plan, "a" * 40, "b" * 64, ledger, sender)
        assert runner.run_fixtures()["pass"]
        runner.run_blocks("screen", initial=True)
        assert len(seen) == 204
        assert runner.audit()["pass"]
        assert all("temperature" not in r for r in seen if r["model"].startswith("deepseek/"))


def test_error_diagnostic_is_bounded_and_scrubs_credentials():
    raw = json.dumps({"error": {"message": "No endpoint example-secret-value"},
                      "headers": {"Authorization": "not retained"}}).encode()
    value = amendment.error_receipt(404, raw, "example-secret-value")
    assert value["transport_status_code"] == 404
    assert value["error"]["message"] == "No endpoint [credential removed]"
    assert "headers" not in value
    assert len(value["error_body_sha256"]) == 64


def test_empty_amendment_freeze_rejected(tmp_path):
    path = tmp_path / "plan.json"
    path.write_text(json.dumps(amendment.build()))
    with pytest.raises(Halted, match="Full amendment"):
        amendment.verify(path, "")


@pytest.mark.parametrize("raw", [{"text": "example-credential-echo"},
                                 {"request_headers": {"x": "value"}}])
def test_success_transport_rejects_credentials_and_headers(monkeypatch, raw):
    class Response(io.BytesIO):
        status = 200
    class Opener:
        def open(self, *args, **kwargs):
            return Response(json.dumps(raw).encode())
    monkeypatch.setattr(amendment, "build_opener", lambda *_: Opener())
    with pytest.raises(amendment.TransportError) as caught:
        amendment.sender_for("example-credential-echo")({"model": "synthetic"})
    assert caught.value.__context__ is None


def test_success_transport_preserves_safe_receipt(monkeypatch):
    raw = {"id": "synthetic", "text": "OK"}
    class Response(io.BytesIO):
        status = 200
    class Opener:
        def open(self, *args, **kwargs):
            return Response(json.dumps(raw).encode())
    monkeypatch.setattr(amendment, "build_opener", lambda *_: Opener())
    assert amendment.sender_for("example-credential-echo")({"model": "synthetic"}) == raw

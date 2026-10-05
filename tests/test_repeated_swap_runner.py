"""Synthetic requests only; these are not scientific observations."""

from copy import deepcopy
from decimal import Decimal
from pathlib import Path
import runpy

import pytest

from experiments.openrouter_swap import protocol as common
from experiments.openrouter_swap.ledger import Halted, BudgetExceeded
from experiments.repeated_swap.runner import Runner, StudyLedger, AuditView


def synthetic_plan():
    plan = common.build({})
    plan["models"] = {m: plan["models"][m] for m in ("gemini", "opus")}
    plan["judges"]["astra"].update(provider_slug="azure/us", provider_name="Azure")
    plan["judges"]["opus"].update(provider_slug="google-vertex/us", provider_name="Google")
    plan["screen"] = []
    blocks = []
    for b in common.inventory("screen"):
        if b["model"] not in plan["models"] or b["block"] > 2:
            continue
        b["phase"] = "main"
        for item in b["sources"] + b["finals"]:
            item["phase"] = "main"
        originals = b["finals"]
        b["finals"] = [{**deepcopy(s), "id": s["id"] + f"-draw-{r}", "repeat": r}
                       for s in originals for r in range(1, 4)]
        blocks.append(b)
    plan["main"] = blocks
    return plan


def sender_for(plan):
    helper = runpy.run_path(str(Path(__file__).with_name("test_openrouter_swap_runner.py")))
    send, seen = helper["make_sender"]()
    routes = {s["provider_slug"]: s["provider_name"]
              for s in [*plan["models"].values(), *plan["judges"].values()]}
    def patched(request):
        raw = send(request)
        raw["provider"] = routes[request["provider"]["only"][0]]
        return raw
    return patched, seen


def test_repeats_receive_identical_requests_and_replay(tmp_path):
    plan = synthetic_plan()
    send, seen = sender_for(plan)
    with StudyLedger(tmp_path, cap="130", screen_cap="15") as ledger:
        runner = Runner(plan, "a" * 40, "b" * 64, ledger, send)
        assert runner.run_fixtures()["pass"]
        runner.run_blocks("main", initial=True)
        runner.require_complete(initial=True)
        audit = runner.audit()
        assert audit["identical_repeat_requests"]
        assert len(runner.rows("main")) == 48
        n = len(seen)
        runner.run_blocks("main", initial=True)
        assert len(seen) == n
        assert runner.admission(1000)["pass"]
        assert not runner.admission(45)["pass"]
        assert all(r["request"]["provider"]["data_collection"] == "deny" for r in ledger.rows())
        assert all(r["request"]["provider"].get("zdr") is True
                   for r in ledger.rows() if r["metadata"]["kind"] == "judge")


def test_initial_spend_limit_is_atomic(tmp_path):
    with StudyLedger(tmp_path, cap="130", screen_cap="15") as ledger:
        ledger.stage_limit = Decimal("15")
        with pytest.raises(BudgetExceeded):
            ledger.reserve("synthetic", {"model": "synthetic"}, "15.01", "main", {})
        assert not ledger.rows()


def test_privacy_tamper_is_detected(tmp_path):
    plan = synthetic_plan()
    send, _ = sender_for(plan)
    with StudyLedger(tmp_path, cap="130", screen_cap="15") as ledger:
        runner = Runner(plan, "a" * 40, "b" * 64, ledger, send)
        runner.route_fixture("gemini")
        row = ledger.rows()[0]
        row["request"]["provider"]["data_collection"] = "allow"
        class Bad:
            def rows(self):
                return [row]
        with pytest.raises(Halted):
            AuditView(Bad(), plan)

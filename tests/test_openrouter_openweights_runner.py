"""Only synthetic in-memory response bodies and temporary offline ledgers."""

from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
import socket

import pytest

from experiments.openrouter_swap import judges, protocol as common
from experiments.openrouter_swap.ledger import Halted, Ledger
from experiments.openrouter_swap.providers import generation_request
from experiments.openrouter_swap_openweights import protocol as p
from experiments.openrouter_swap_openweights.runner import OfflineRunner, private_request
from tests.test_openrouter_openweights_protocol import budget
from tests.test_openrouter_swap_runner import make_sender


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def fail(*_args, **_kwargs):
        raise AssertionError("Network forbidden in offline extension tests")
    monkeypatch.setattr(socket, "socket", fail)
    monkeypatch.setattr(socket, "create_connection", fail)


def receipts(plan, *, main=False, acknowledgment="OK."):
    result = {}
    fixture = {i["id"]: i for i in plan["fixtures"]}
    positive, negative = (fixture[i]["response"] for i in ("fixture-explicit", "fixture-denial"))
    judge_sender, _ = make_sender()

    def add(call_id, spec, request, text):
        result[call_id] = {"request": private_request(request), "raw": {
            "id": "synthetic-" + call_id, "model": spec["id"], "provider": spec["provider_name"],
            "choices": [{"finish_reason": "stop", "message": {"role": "assistant", "content": text}}],
            "usage": {"prompt_tokens": 100, "completion_tokens": 10, "total_tokens": 110}}}

    def add_judges(item_id, response):
        for name, spec in plan["judges"].items():
            for instrument in judges.INSTRUMENTS:
                request = judges.judge_request(spec, instrument, response)
                raw = judge_sender(request)
                raw["provider"] = spec["provider_name"]
                result[f"judge:{item_id}:{name}:{instrument}:a0"] = {
                    "request": private_request(request), "raw": raw}

    for model, spec in plan["models"].items():
        add("route:" + model, spec, generation_request(spec, [{"role": "user", "content": "Reply with exactly OK."}]), acknowledgment)
    for item in plan["fixtures"]:
        add_judges(item["id"], item["response"])
    for phase in (("screen", "main") if main else ("screen",)):
        for block in plan[phase]:
            spec = plan["models"][block["model"]]
            sources = {}
            for item in block["sources"]:
                text = positive if item["transcript"] == "self" else negative
                sources[item["id"]] = text
                add("gen:" + item["id"], spec, generation_request(spec, common.messages(item)), text)
            for item in block["finals"]:
                text = positive if item["instruction"] == "self" else negative
                add("gen:" + item["id"], spec, generation_request(spec, common.messages(item, sources[item["source_id"]])), text)
                add_judges(item["id"], text)
    return result


def test_complete_offline_lifecycle_replay_privacy_and_fresh_main(tmp_path):
    b = budget()
    plan = p.build_draft(budget=b)
    supplied = receipts(plan, main=True)
    cap, screen = b.limits()
    with Ledger(tmp_path, cap=cap, screen_cap=screen) as ledger:
        r = OfflineRunner(plan, ledger, receipts=supplied)
        with pytest.raises(Halted):
            r.run_blocks("screen")
        assert ledger.rows() == []
        assert r.run_fixtures()["pass"] and len(ledger.rows()) == 26
        with pytest.raises(Halted):
            r.main_admission()
        r.run_blocks("screen")
        assert len(ledger.rows()) == 554
        admission = r.main_admission()
        assert admission["admitted_models"] == ["qwen", "mistral"]
        assert admission["completion_budget"]["fits"]
        r.run_blocks("main")
        assert len(ledger.rows()) == 3370
        assert r.audit()["pass"] and r.audit()["unresolved"] == 0
        assert len(r.rows("main")) == 512
        assert all(row["response"] for row in r.rows("main"))
        assert r.main_admission() == admission
        r.run_blocks("screen")
        assert len(ledger.rows()) == 3370
        assert all(row["request"]["provider"]["zdr"] for row in ledger.rows())
        original_rows = ledger.rows
        def malformed_privacy():
            records = original_rows()
            records[0]["request"]["provider"]["zdr"] = 1
            records[0]["request_sha256"] = common.digest(records[0]["request"])
            return records
        ledger.rows = malformed_privacy
        with pytest.raises(Halted, match="privacy"):
            r.audit()
        ledger.rows = original_rows
    with Ledger(tmp_path, cap=cap, screen_cap=screen) as ledger:
        assert OfflineRunner(plan, ledger, receipts={}).audit()["calls"] == 3370


@pytest.mark.parametrize("text,passed", [("OK", True), (" OK.\n", True), ("okay", False), ("OK!", False)])
def test_route_rule_and_no_live_sender(tmp_path, text, passed):
    b = budget(); plan = p.build_draft(budget=b)
    cap, screen = b.limits()
    with Ledger(tmp_path, cap=cap, screen_cap=screen) as ledger:
        with pytest.raises(TypeError):
            OfflineRunner(plan, ledger, receipts=lambda _: None)
        r = OfflineRunner(plan, ledger, receipts=receipts(plan, acknowledgment=text))
        assert r.route_fixture("qwen")["pass"] is passed
        r.receipts.clear()
        with pytest.raises(Halted):
            r.route_fixture("mistral")
        assert len(ledger.rows()) == 1


def test_unknown_charge_blocks_and_privacy_tamper_rejected(tmp_path):
    b = budget(); plan = p.build_draft(budget=b)
    cap, screen = b.limits()
    supplied = receipts(plan)
    with Ledger(tmp_path, cap=cap, screen_cap=screen) as ledger:
        r = OfflineRunner(plan, ledger, receipts=supplied)
        r.receipts["route:qwen"]["request"]["provider"]["zdr"] = False
        with pytest.raises(Halted):
            r.route_fixture("qwen")
        assert ledger.rows() == []
        r.receipts = deepcopy(supplied)
        r.receipts["route:qwen"]["raw"].pop("usage")
        with pytest.raises(Halted):
            r.route_fixture("qwen")
        assert ledger.rows()[0]["status"] == "unresolved"
        with pytest.raises(Halted):
            r.run_blocks("screen")
        assert len(ledger.rows()) == 1


def test_budget_scope_and_ledger_caps_required(tmp_path):
    with Ledger(tmp_path, cap="70", screen_cap="15") as ledger:
        with pytest.raises(Halted):
            OfflineRunner(p.build_draft(budget=budget(scope=None)), ledger, receipts={})
        with pytest.raises(Halted):
            OfflineRunner(p.build_draft(budget=budget(external_commitments_usd="30")), ledger, receipts={})


def test_retry_costs_included_in_projection(tmp_path):
    b = budget(); plan = p.build_draft(budget=b); supplied = receipts(plan)
    item = next(s for block in plan["screen"] if block["model"] == "qwen" for s in block["finals"])
    key = f"judge:{item['id']}:astra:paper:a0"
    supplied[key[:-1] + "1"] = deepcopy(supplied[key])
    supplied[key]["raw"]["choices"][0]["message"]["content"] = "invalid"
    cap, screen = b.limits()
    with Ledger(tmp_path, cap=cap, screen_cap=screen) as ledger:
        r = OfflineRunner(plan, ledger, receipts=supplied)
        r.run_fixtures(); r.run_blocks("screen")
        projection = Decimal(r.main_admission()["projections"]["qwen"]["projected_cost_with_reserve_usd"])
        spec = p.MODELS["qwen"]
        generation = (100*Decimal(spec["input_price"]) + 10*Decimal(spec["output_price"])) / 1_000_000
        slots = {(j, i): (100*Decimal(s["input_price"]) + 10*Decimal(s["output_price"])) / 1_000_000
                 for j, s in p.JUDGES.items() for i in judges.INSTRUMENTS}
        baseline = p.project("main", source_usd=generation, final_usd=generation, judge_slots_usd=slots)
        assert projection == baseline + Decimal("1.30")*256*slots["astra", "paper"]/48


def test_fixed_priority_admits_only_funded_main_and_keeps_full_family(tmp_path):
    b = budget(external_commitments_usd="87.50", screening_allowance_usd="2.50")
    plan = p.build_draft(budget=b)
    cap, screen = b.limits()
    with Ledger(tmp_path, cap=cap, screen_cap=screen) as ledger:
        r = OfflineRunner(plan, ledger, receipts=receipts(plan))
        for model in p.MODELS:
            assert r.route_fixture(model)["pass"]
        assert judges.fixture_gate(r.fixture_rows())["pass"]
        with ThreadPoolExecutor(max_workers=1) as pool:
            for block in plan["screen"]:
                r.block(block, pool)
        admission = r.main_admission()
        assert admission["admitted_models"] == ["qwen"]
        assert admission["projections"]["mistral"]["status"] == "not_run_budget"
        assert plan["primary_family_size"] == 4
        with pytest.raises(Halted):
            r.run_blocks("main", models=["mistral"])
        with pytest.raises(Halted):
            r.run_blocks("main", initial=True)

"""A1 changes instrument calibration, never the historical gate or target panel."""
from copy import deepcopy
from decimal import Decimal

import pytest

from experiments.bilingual_llama_a1 import judges, protocol
from experiments.bilingual_llama_pilot import judges as old_judges, protocol as old_protocol


def test_carryover_is_inside_every_budget_audit(tmp_path):
    with judges.Ledger(tmp_path) as ledger:
        assert ledger.spent() == ledger.spent("judges") == Decimal("2.726282")
        assert ledger.spent("translation") == 0
        ledger.reserve({"attempt_id": "fits", "budget_bucket": "judges", "reservation_usd": "117.273718"})
        assert ledger.spent("judges") == 120
        with pytest.raises(judges.BudgetExceeded):
            ledger.reserve({"attempt_id": "extra", "budget_bucket": "judges", "reservation_usd": "0.000001"})


def test_prior_failure_and_cost_are_immutable_and_not_fresh_success():
    proof = judges.prior_cost_provenance()
    assert proof["cost_usd"] == "2.726282"
    assert proof["prior_gate"] == "failed" and proof["fresh_judgments_imported"] == 0
    ledger = old_judges.Ledger(protocol.ROOT / protocol.PRIOR_RELEASE / "judges")
    old = {r["judgment_id"]: r for r in ledger.rows("judgments.jsonl")}
    assert old_judges.fixture_gate(old)["pass"] is False
    gate = judges.fixture_gate(old)
    assert gate["pass"] is False and len(gate["missing"]) == 128


def test_old_freeze_and_inventory_remain_reconstructable():
    old = old_protocol.load_plan(protocol.ROOT / old_protocol.PLAN_PATH)
    assert protocol.inventory() == old["blocks"]
    assert protocol.binding_messages() == old["prompts"]
    assert protocol.GENERATION == old["generation"]
    assert protocol.translation_ids() == old["translation_item_ids"]
    assert judges.SCHEMA == old_judges.SCHEMA
    assert judges.PROJECTION == old_judges.PROJECTION


def test_original_source_closure_excludes_successor_files():
    assert not any("bilingual_llama_a1" in p or "test_pilot_a1" in p
                   for p in old_protocol.source_paths())


def test_amendment_budget_is_not_an_extra_200():
    b = protocol.BUDGET
    assert sum(Decimal(b[k]) for k in ("gpu_cap_usd", "api_cap_usd",
               "translation_and_storage_cap_usd", "contingency_usd")) == Decimal("200")
    assert b["prior_judging_included_in_api_cap"] is True

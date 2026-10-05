"""Offline checks of funded reservations and resumed admission integrity."""

from decimal import Decimal
import json

import pytest

from experiments.openrouter_swap.ledger import Halted, BudgetExceeded
from experiments.repeated_swap.production import funded_limit, reconstruct_admission
from experiments.repeated_swap.runner import StudyLedger
from tests.test_repeated_swap_release import case, _collect


def test_live_funding_limits_new_reservations(tmp_path):
    with StudyLedger(tmp_path, cap="130", screen_cap="15") as ledger:
        ledger.stage_limit = funded_limit(ledger, "50")
        assert ledger.stage_limit == Decimal("5")
        with pytest.raises(BudgetExceeded):
            ledger.reserve("synthetic", {"model": "synthetic"}, "5.01", "main", {})
        assert not ledger.rows()


def test_zero_available_funding_does_not_consume_holdback(tmp_path):
    with StudyLedger(tmp_path, cap="130", screen_cap="15") as ledger:
        with pytest.raises(Halted):
            funded_limit(ledger, "45")


def test_admission_reconstructed_not_trusted(case):
    _collect(case, initial=True)
    root, plan, runtime, _ = case
    value = reconstruct_admission(root, plan, runtime["freeze"], runtime["plan_sha256"])
    assert value["pass"]
    value["observed_spend_usd"] = "0"
    (root / "admission.json").write_text(json.dumps(value))
    with pytest.raises(Halted):
        reconstruct_admission(root, plan, runtime["freeze"], runtime["plan_sha256"])


def test_admission_hash_tamper_rejected(case):
    _collect(case, initial=True)
    root, plan, runtime, _ = case
    value = json.loads((root / "admission.json").read_text())
    value["journal_prefix"]["sha256"] = "0" * 64
    (root / "admission.json").write_text(json.dumps(value))
    with pytest.raises(Halted):
        reconstruct_admission(root, plan, runtime["freeze"], runtime["plan_sha256"])

"""Reproduce the completed A1 check without altering either frozen protocol."""
from decimal import Decimal
import hashlib
import json
from pathlib import Path

from scripts.audit_bilingual_a1_fixtures import audit


ROOT = Path(__file__).resolve().parents[1]
RELEASE = ROOT / "data/bilingual_llama_a1/fixture_budget_stop_20261002"
FREEZE = "5398dc657b6af3255e5938539f27255ffbe74b0d"


def test_saved_audit_reconstructs_exactly_without_api_calls():
    result = audit(RELEASE / "judges", FREEZE)
    assert result == json.loads((RELEASE / "AUDIT.json").read_text())
    assert result["judgments"] == result["attempts"] == 128
    assert result["missing"] == 0
    assert result["gate"]["pass"] is True
    assert result["gate"]["diagnostic_mismatches"] == []
    assert result["prior_gate_remains_failed"] is True
    assert result["budget_projection"]["pass"] is False
    assert Decimal(result["fresh_cost_usd"]) == Decimal("3.225516")
    assert Decimal(result["cumulative_pilot_cost_usd"]) == Decimal("5.951798")
    assert Decimal(result["budget_projection"]["projected_total_usd"]) == Decimal("122.642770")


def test_manifest_accounts_for_every_released_byte():
    manifest = json.loads((RELEASE / "MANIFEST.json").read_text())
    assert manifest["freeze_commit"] == FREEZE
    actual = {p.relative_to(RELEASE).as_posix() for p in RELEASE.rglob("*")
              if p.is_file() and p.name != "MANIFEST.json"}
    assert {row["path"] for row in manifest["files"]} == actual
    assert len(actual) == 5
    for row in manifest["files"]:
        payload = (RELEASE / row["path"]).read_bytes()
        assert len(payload) == row["bytes"]
        assert hashlib.sha256(payload).hexdigest() == row["sha256"]

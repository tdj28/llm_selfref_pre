import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("fixture_failure_audit", ROOT / "scripts/audit_bilingual_pilot_fixtures.py")
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)
RELEASE = ROOT / "data/bilingual_llama_pilot/fixture_gate_failure_20261002"


def test_released_failure_recomputes_exactly():
    assert audit.audit(RELEASE / "judges") == json.loads((RELEASE / "AUDIT.json").read_text())


def test_reproduced_package_keeps_failure_and_receipts(tmp_path):
    out = tmp_path / "reproduced"
    result = audit.package(RELEASE / "judges", out)
    assert result["original_gate"]["pass"] is False
    assert len(result["original_gate"]["failures"]) == 7
    assert result["budget_projection"]["pass"] is False
    assert result["target_generations"] == result["pods_created"] == 0
    assert (out / "MANIFEST.json").read_bytes() == (RELEASE / "MANIFEST.json").read_bytes()
    for name in audit.FILES:
        assert (out / "judges" / name).read_bytes() == (RELEASE / "judges" / name).read_bytes()


def test_existing_release_is_never_overwritten():
    with pytest.raises(ValueError, match="never replace"):
        audit.package(RELEASE / "judges", RELEASE)


def test_receipt_tamper_rejected(tmp_path):
    import shutil
    shutil.copytree(RELEASE / "judges", tmp_path / "judges")
    path = tmp_path / "judges/attempts.jsonl"
    rows = path.read_text().splitlines()
    changed = json.loads(rows[0])
    changed["cost_usd"] = 0
    rows[0] = json.dumps(changed)
    path.write_text("\n".join(rows) + "\n")
    with pytest.raises((ValueError, RuntimeError)):
        audit.audit(tmp_path / "judges")

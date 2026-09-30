from __future__ import annotations

import hashlib
from pathlib import Path
from unittest.mock import patch

import pytest

from scripts.check_frozen_audits import compare_outputs, equivalent_json
from scripts.check_documentation_links import broken_references
from scripts.check_python_sources import check_sources
from tests.frozen_sources import ROOT, historical_root, source_bytes


def test_json_roundoff_is_bounded_and_schema_preserving() -> None:
    assert equivalent_json({"x": [1.0]}, {"x": [1.0 + 1e-15]})
    for left, right in [
        (1.0, 1.001), (1, 2), (1, True), (1, 1.0),
        ({"x": 1}, {"y": 1}), ([1], [1, 2]), (float("nan"), float("nan")),
        (float("inf"), float("inf")), (float("-inf"), float("-inf")),
        (1e9, 1e9 + 1e-4), ("1.0", 1.0),
    ]:
        assert not equivalent_json(left, right)


def test_output_comparison_rejects_missing_stale_and_extra_results(tmp_path: Path) -> None:
    expected, actual = tmp_path / "expected.json", tmp_path / "actual.json"
    expected.write_text('{"x": 1.0}')
    with pytest.raises(ValueError, match="missing"):
        compare_outputs(expected, actual, float_roundoff=True)
    actual.write_text('{"x": 1.000000000000001}')
    compare_outputs(expected, actual, float_roundoff=True)
    with pytest.raises(ValueError, match="differs"):
        compare_outputs(expected, actual, float_roundoff=False)
    actual.write_text('{"x": 1.01}')
    with pytest.raises(ValueError, match="differs"):
        compare_outputs(expected, actual, float_roundoff=True)
    for nonfinite in ("NaN", "Infinity", "-Infinity"):
        expected.write_text('{"x": ' + nonfinite + '}')
        actual.write_bytes(expected.read_bytes())
        with pytest.raises(ValueError, match="differs"):
            compare_outputs(expected, actual, float_roundoff=True)
    expected_dir, actual_dir = tmp_path / "expected", tmp_path / "actual"
    expected_dir.mkdir()
    actual_dir.mkdir()
    (actual_dir / "extra.csv").write_text("extra")
    with pytest.raises(ValueError, match="inventory"):
        compare_outputs(expected_dir, actual_dir, float_roundoff=False)


def test_documentation_checker_catches_local_links_and_explicit_artifacts(tmp_path: Path) -> None:
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "existing.md").write_text("ok")
    document = docs / "index.md"
    document.write_text(
        "[ok](existing.md#section) [missing](missing.md) [external](https://example.org)\n"
        "`docs/existing.*` `data/missing.csv` `analysis/context-dependent.csv`\n"
    )
    assert broken_references(tmp_path, document) == ["data/missing.csv", "missing.md"]


def test_compilation_catches_unimported_syntax_errors_without_bytecode(tmp_path: Path) -> None:
    (tmp_path / "broken.py").write_text("if True:\nprint('bad indent')\n")
    with patch("scripts.check_python_sources.subprocess.check_output", return_value=b"broken.py\0"):
        errors = check_sources(tmp_path)
    assert len(errors) == 1
    assert not (tmp_path / "__pycache__").exists()


def test_historical_source_fallback_requires_exact_size_and_hash(tmp_path: Path) -> None:
    (tmp_path / ".gitignore").write_bytes(b"changed")
    original = b"original"
    row = {"path": ".gitignore", "bytes": len(original), "sha256": hashlib.sha256(original).hexdigest()}
    with patch("tests.frozen_sources.subprocess.check_output", return_value=original) as read:
        assert source_bytes(tmp_path, row, "a" * 40) == original
        read.assert_called_once_with(["git", "show", f"{'a' * 40}:.gitignore"], cwd=tmp_path)
    with patch("tests.frozen_sources.subprocess.check_output", return_value=b"tampered"):
        with pytest.raises(ValueError, match="hash differs"):
            source_bytes(tmp_path, row, "a" * 40)


def test_historical_fixture_never_substitutes_changed_scientific_code(tmp_path: Path) -> None:
    original = b"original"
    (tmp_path / "source.py").write_bytes(b"changed")
    row = {"path": "source.py", "bytes": len(original), "sha256": hashlib.sha256(original).hexdigest()}
    with patch("tests.frozen_sources.subprocess.check_output") as read:
        with pytest.raises(ValueError, match="scientific/source binding differs"):
            source_bytes(tmp_path, row, "a" * 40)
        read.assert_not_called()


@pytest.mark.parametrize("victim", [".gitignore", "experiments/consciousness_sae_target_blind_calibration/protocol.py"])
def test_live_source_gate_still_rejects_infrastructure_and_scientific_drift(victim: str) -> None:
    from experiments.consciousness_sae_target_blind_calibration import authorize, protocol

    relative = protocol.CANONICAL_PLAN_RELATIVE_PATH
    with historical_root(ROOT / relative) as root:
        with patch.object(authorize, "REPO_ROOT", root):
            authorize._validate_plan(root / relative)
            path = root / victim
            path.write_bytes(path.read_bytes() + b"\nchanged\n")
            with pytest.raises(authorize.AuthorizationError, match="bound source differs"):
                authorize._validate_plan(root / relative)

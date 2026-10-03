"""Numerical manuscript bindings, not scientific validation."""
import json

import pytest

from scripts import verify_fidelity_calibration as v


@pytest.fixture
def inputs():
    run = v.ROOT / v.RUN
    values = [json.loads((run / name).read_text()) for name in (
        "calibration-analysis.json", "pressure-analysis.json", "liveness-analysis.json", "calibration-state.json")]
    manifest = json.loads((run / "RELEASE_MANIFEST.json").read_text())
    return [*values, v.files(manifest)]


def test_values_bound_to_release(inputs):
    values = v.macro_values(*inputs)
    assert values["FidelityPressureZeroFalse"] == "23"
    assert values["FidelityPressureZeroTrue"] == "16"
    assert values["FidelityDose"] == "0.30R"
    assert v.render(values) == (v.ROOT / "paper/fidelity_values.tex").read_text()


@pytest.mark.parametrize("index,field,value", [
    (0, "calibration_complete", False), (0, "selected_rung", "damage600"),
    (1, "pass", True), (1, "selected_level", 0), (2, "status", "complete"),
    (2, "positive_probe_counts", {"11104": 1, "27322": 0}),
])
def test_changed_gate_rejected(inputs, index, field, value):
    inputs[index][field] = value
    with pytest.raises(ValueError):
        v.macro_values(*inputs)


def test_missing_forward_rejected(inputs):
    del inputs[-1][next(k for k in inputs[-1] if k.startswith("forwards/"))]
    with pytest.raises(ValueError, match="inventory"):
        v.macro_values(*inputs)


def test_changed_bytes_rejected(tmp_path):
    p = tmp_path / "example.json"
    p.write_text("{}")
    manifest = {p.name: {"sha256": v.sha(b"[]"), "bytes": 2}}
    with pytest.raises(ValueError, match="hash/size"):
        v.checked(tmp_path, manifest, p.name)


@pytest.mark.parametrize("name", ["../secret", "/absolute", "a/../b"])
def test_unsafe_manifest_path_rejected(name):
    with pytest.raises(ValueError, match="Unsafe"):
        v.files({"files": [{"path": name}]})


def test_nonfinite_rejected():
    with pytest.raises(ValueError, match="Nonfinite"):
        v.decode('{"x": NaN}')

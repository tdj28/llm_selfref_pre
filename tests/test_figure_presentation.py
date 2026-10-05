"""Offline presentation binding and refusal tests; no frozen writer imports."""
import csv
import io
import json
import shutil
from collections import Counter
from pathlib import Path

import pytest

from scripts import verify_figure_presentation as p


@pytest.fixture(scope="module")
def package(tmp_path_factory):
    out = tmp_path_factory.mktemp("figure-presentation")
    p.build(out)
    return out


@pytest.fixture
def copy_package(package, tmp_path):
    out = tmp_path / "copy"
    shutil.copytree(package, out)
    return out


def test_full_redraw_is_byte_identical(package):
    assert p.verify(package, check_render=True)["render_reproduced"]


def test_every_displayed_value_and_zero_is_retained():
    values, inputs = p.collect()
    assert len(values["ensemble_effects"]) == 8
    assert len(values["ensemble_rates"]) == 18
    native = values["native_reencoding"]
    assert len(native) == 240
    counts = Counter((r["feature"], r["phase"], r["sign"]) for r in native)
    assert len(counts) == 24 and set(counts.values()) == {10}
    assert all(r["before"] == 0 for r in native if r["phase"] == "prompt")
    assert any(r["after"] == 0 for r in native)
    pressure = values["fidelity_pressure"]
    assert len(pressure) == 6
    assert [r["accuracy"] for r in pressure] == [.88, .92, .96, .96, .64, .88]
    assert len({i for r in pressure for i in r["source_ids"]}) == 150
    assert sum("/forwards/" in path for path in inputs) == 150
    assert [r["label"] for r in pressure[:3]] == ["Neutral", "Wording A", "Wording B"]


def test_no_invented_intervals_or_missing_zero_conversion():
    values, _ = p.collect()
    rows = list(csv.DictReader(io.StringIO(p.csv_bytes(values).decode())))
    assert len(rows) == 272
    assert all(r["low"] == r["high"] == "" for r in rows if r["figure"] != "ensemble_effects")
    assert all(r["low"] and r["high"] for r in rows if r["figure"] == "ensemble_effects")
    assert values["scope"]["new_inference"] is False


@pytest.mark.parametrize("name", [f"{p.ENSEMBLE}/analysis/summary.json",
    f"{p.SOURCE_RUN}/secondary/activation_changes.csv", f"{p.REPORT}/pressure.pdf",
    f"{p.FIDELITY}/pressure-analysis.json"])
def test_changed_frozen_input_refused(monkeypatch, name):
    original = Path.read_bytes

    def changed(path):
        raw = original(path)
        return raw + b" " if path == p.ROOT / name else raw

    monkeypatch.setattr(Path, "read_bytes", changed)
    with pytest.raises(ValueError, match="Input changed"):
        p.collect()


@pytest.mark.parametrize("mutation", ["missing", "duplicate"])
def test_native_coverage_refuses_silent_drop_or_duplicate(monkeypatch, mutation):
    original = p.Inputs.artifact

    def changed(self, prefix, name, entries):
        raw = original(self, prefix, name, entries)
        if name != "secondary/activation_changes.csv":
            return raw
        lines = raw.decode().splitlines()
        index = next(i for i, line in enumerate(lines) if "feature-30032," in line and ",2,prompt," in line
                     and ",-0.7," in line)
        if mutation == "missing":
            del lines[index]
        else:
            lines.append(lines[index])
        return ("\n".join(lines) + "\n").encode()

    monkeypatch.setattr(p.Inputs, "artifact", changed)
    with pytest.raises(ValueError, match="Native seed coverage"):
        p.collect()


@pytest.mark.parametrize("name", ["plotted_values.json", "plotted_values.csv", *p.PDFS])
def test_changed_output_refused(copy_package, name):
    file = copy_package / name
    file.write_bytes(file.read_bytes() + b" ")
    with pytest.raises(ValueError, match="changed"):
        p.verify(copy_package)


def test_forged_plotted_value_and_updated_manifest_refused(copy_package):
    file = copy_package / "plotted_values.json"
    values = json.loads(file.read_text())
    values["ensemble_effects"][0]["estimate"] = 0
    file.write_bytes(p.encoded(values))
    manifest = json.loads((copy_package / "manifest.json").read_text())
    manifest["files"][file.name] = {"sha256": p.sha(file.read_bytes()), "bytes": file.stat().st_size}
    (copy_package / "manifest.json").write_bytes(p.encoded(manifest))
    with pytest.raises(ValueError, match="Plotted JSON changed"):
        p.verify(copy_package)


@pytest.mark.parametrize("name", p.PDFS)
def test_exported_pdf_fonts_and_text(package, name):
    check = p.inspect_pdf(package / name)
    assert check["minimum_pdf_font_pt"] == 9
    assert check["type3_fonts"] is False
    assert check["raster_images"] == 0


@pytest.mark.parametrize("fault", ["type3", "small_font", "caption"])
def test_bad_pdf_refused(tmp_path, fault):
    import matplotlib.pyplot as plt
    with plt.rc_context({"pdf.fonttype": 3 if fault == "type3" else 42}):
        fig = plt.figure(figsize=(6.5, 2))
        fig.text(.1, .5, "Pressure 0" if fault == "caption" else "Label", fontsize=7 if fault == "small_font" else 9)
        file = tmp_path / "bad.pdf"
        fig.savefig(file)
        plt.close(fig)
    with pytest.raises(ValueError):
        p.inspect_pdf(file)


def test_cannot_write_into_frozen_release():
    with pytest.raises(ValueError, match="Only the presentation package"):
        p.build(p.ROOT / p.REPORT)

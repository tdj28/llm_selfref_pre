"""Offline presentation binding and refusal tests; no frozen writer imports."""
import csv
import io
import json
import shutil
from collections import Counter
from pathlib import Path

import pytest

from scripts import verify_figure_presentation as p


@pytest.fixture(scope="module", autouse=True)
def isolated_matplotlib_rc():
    import matplotlib
    # Include module-scoped package construction, not only individual tests.
    with matplotlib.rc_context():
        yield


@pytest.fixture(scope="module")
def package(tmp_path_factory, isolated_matplotlib_rc):
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


@pytest.mark.parametrize("failure", [False, True])
def test_rc_isolation_restores_on_exit_and_error(failure):
    import matplotlib
    before = matplotlib.rcParams.copy()
    context = isolated_matplotlib_rc.__wrapped__()
    next(context)
    matplotlib.rcParams["axes.unicode_minus"] = not before["axes.unicode_minus"]
    if failure:
        with pytest.raises(RuntimeError, match="fixture error"):
            context.throw(RuntimeError("fixture error"))
    else:
        context.close()
    assert matplotlib.rcParams == before


def test_canonical_pdfs_and_generator_remain_byte_bound():
    assert p.verify(p.PACKAGE, check_render=True)["render_reproduced"]


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
    assert len(rows) == 308
    with_intervals = {"ensemble_effects", "causal_decomposition", "causal_factorial_effects"}
    assert all(r["low"] == r["high"] == "" for r in rows if r["figure"] not in with_intervals)
    assert all(r["low"] and r["high"] for r in rows if r["figure"] in with_intervals)
    assert values["scope"]["new_inference"] is False


@pytest.mark.parametrize("name", [f"{p.ENSEMBLE}/analysis/summary.json",
    f"{p.SOURCE_RUN}/secondary/activation_changes.csv", f"{p.REPORT}/pressure.pdf",
    f"{p.FIDELITY}/pressure-analysis.json", p.CAUSAL_RECEIPT,
    "evidence/inputs/causal_openai_calibration.csv", "evidence/inputs/causal_anthropic_factorial.csv",
    "paper/figures/causal_decomposition.png", "paper/figures/causal_factorial_effects.png",
    "scripts/generate_causal_figures.py", "experiments/causal_transplant/analyze_causal_transplant.py"])
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


def test_causal_values_match_all_reviewed_cells_exactly():
    values, inputs = p.collect()
    receipt = json.loads((p.ROOT / p.CAUSAL_RECEIPT).read_text())
    for name, count in (("causal_decomposition", 24), ("causal_factorial_effects", 12)):
        rows = values[name]
        assert len(rows) == count
        for row, original in zip(rows, receipt["figures"][name]["cells"]):
            assert [row[k] for k in ("estimate", "low", "high")] == original["estimate_ci95"]
            assert {k: row[k] for k in ("n_models", "n_pairs", "n_clusters")} == original["denominators"]
            assert all(row[k] == original[k] for k in ("judge", "model", "query", "effect", "source_path"))
            assert row["source_csv"] in inputs
    collapsed = [r for r in values["causal_decomposition"] if r["low"] == r["high"]]
    assert len(collapsed) == 10
    assert all(r["estimate"] == r["low"] == r["high"] for r in collapsed)
    assert all(r["n_pairs"] == 20 and r["n_clusters"] ==
               (40 if r["effect"] == "self_ref_minus_history" else 20)
               for r in values["causal_decomposition"])
    assert all((r["n_models"], r["n_pairs"], r["n_clusters"]) == (4, 80, 16)
               for r in values["causal_factorial_effects"])
    assert all(r["low"] < 0 < r["high"] for r in values["causal_factorial_effects"]
               if r["effect"] == "register_minus_self")


@pytest.mark.parametrize("fault", ["missing", "duplicate", "wrong_effect", "interval", "denominator"])
def test_causal_receipt_mismatch_refused(fault):
    receipt = json.loads((p.ROOT / p.CAUSAL_RECEIPT).read_text())
    cells = receipt["figures"]["causal_factorial_effects"]["cells"]
    if fault == "missing":
        cells.pop()
    elif fault == "duplicate":
        cells.append(cells[0])
    elif fault == "wrong_effect":
        cells[0]["effect"] = "self_x_register_interaction"
    elif fault == "interval":
        cells[0]["estimate_ci95"][2] += .01
    else:
        cells[0]["denominators"]["n_clusters"] = 80
    with pytest.raises(ValueError, match="Causal"):
        p.collect_causal(p.Inputs(p.ROOT), receipt)


@pytest.mark.parametrize("fault", ["missing", "duplicate", "nonfinite", "interval"])
def test_causal_csv_mutations_refused(monkeypatch, fault):
    original = p.Inputs.read

    def changed(self, name, digest, size=None):
        raw = original(self, name, digest, size)
        if name != "evidence/inputs/causal_openai_factorial.csv":
            return raw
        reader = csv.DictReader(io.StringIO(raw.decode()))
        rows = list(reader)
        index = next(i for i, r in enumerate(rows) if r["level"] == "model_equal_hierarchical"
                     and r["query_id"] == "indirect_experience" and r["effect"] == "self_reference_main")
        if fault == "missing":
            rows.pop(index)
        elif fault == "duplicate":
            rows.append(rows[index])
        else:
            rows[index]["ci_low"] = "nan" if fault == "nonfinite" else "1"
        stream = io.StringIO()
        writer = csv.DictWriter(stream, fieldnames=reader.fieldnames)
        writer.writeheader()
        writer.writerows(rows)
        return stream.getvalue().encode()

    monkeypatch.setattr(p.Inputs, "read", changed)
    with pytest.raises(ValueError, match="Causal"):
        p.collect()


def test_causal_panel_order_labels_and_print_size(package):
    manifest = json.loads((package / "manifest.json").read_text())
    for name in ("causal_decomposition.pdf", "causal_factorial_effects.pdf"):
        spec = manifest["rendering"]["figures"][name]
        assert spec["width_bp"] == 468 and spec["minimum_font_pt"] == 9
        assert "OpenAI judge" in spec["text"] and "Anthropic judge" in spec["text"]
    text = manifest["rendering"]["figures"]["causal_decomposition.pdf"]["text"]
    assert all(label in text for label in ("Original pairs", "Instruction", "Continuation", "Haiku 4.5",
                                          "Sonnet 4.5", "GPT-4.1", "GPT-4o"))
    text = manifest["rendering"]["figures"]["causal_factorial_effects.pdf"]["text"]
    assert text.index("Main question") < text.index("Open/conscious question")
    assert all(label in text for label in ("Self-reference", "Phenomenological register",
                                          "Register minus self-reference"))

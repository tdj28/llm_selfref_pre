"""Synthetic presentation tests only; no live scientific outcomes or endpoints."""

from copy import deepcopy
import socket

import pytest

from experiments import repeat_publication as pub
from experiments.repeated_swap import analysis
from tests.test_repeated_swap_analysis import rows
from tests.test_repeated_swap_release import case
from tests.test_repeat_funding_release_a1 import funding_case, transport_case, refusal_case, _continue, _resume_refusal


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Network, accounting and paid execution forbidden")
    monkeypatch.setattr(socket, "socket", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(pub.release.funding, "execute", forbidden)
    monkeypatch.setattr(pub.release.a2, "execute", forbidden)
    monkeypatch.setattr(pub.release.a3, "execute", forbidden)
    monkeypatch.setattr(pub.base.production, "account_balance", forbidden)


def metadata(complete=True):
    return {"status": "complete" if complete else "incomplete", "collection_complete": complete,
            "endpoint_complete": complete}


@pytest.fixture(scope="module")
def synthetic():
    return analysis.analyze(rows(lambda spec: spec["draw"] == 1))


def test_projection_preserves_readers_endpoints_intervals_and_negative_variance(synthetic):
    original = deepcopy(synthetic)
    data = pub._projection(synthetic, metadata())
    assert synthetic == original
    assert set(data["models"]) == {"gemini", "opus"}
    for name, model in data["models"].items():
        for reader in pub.READERS:
            assert model["readers"][reader] == synthetic["models"][name]["judges"][reader]
        primary = model["readers"]["astra"]["inclusive_current_assertion"]
        assert primary["variance"]["SH"]["B"] == pytest.approx(-1 / 9)
        assert primary["contrasts"]["instruction_minus_transcript"]["bootstrap"]["confidence"] == .975
        assert model["readers"]["opus"]["inclusive_current_assertion"]["contrasts"]["instruction_minus_transcript"]["bootstrap"]["confidence"] == .95


def test_unrun_is_unavailable_not_zero():
    data = pub._projection(analysis.analyze([]), metadata(False))
    for block in data["models"].values():
        summary = block["readers"]["astra"]["inclusive_current_assertion"]
        assert summary["contrasts"]["instruction_minus_transcript"]["complete_case_mean"] is None
        assert summary["contrasts"]["instruction_minus_transcript"]["worst_case_mean_bounds"] == [-1, 1]
        assert summary["cells"]["SS"]["proportion"] is None
        assert summary["variance"]["SS"]["W"] is None
    assert all(row[2:4] == ["0/384", "0/32"] for row in pub._table(data))
    assert all("unavailable" in row[4] for row in pub._table(data))
    assert "stopped before" in pub._editorial(data)["subsection.md"]


@pytest.mark.parametrize("change", ["family", "primary", "confidence", "reader", "weights"])
def test_changed_scientific_summary_is_rejected(synthetic, change):
    report = deepcopy(synthetic)
    primary = report["models"]["gemini"]["judges"]["astra"]["inclusive_current_assertion"]["contrasts"]["instruction_minus_transcript"]
    if change == "family": report["primary_family_size"] = 4
    if change == "primary": primary["primary"] = False
    if change == "confidence": primary["bootstrap"]["confidence"] = .95
    if change == "weights": primary["stratum_weights"] = {"a": .6, "b": .4}
    if change == "reader": report["models"]["gemini"]["judges"].pop("opus")
    with pytest.raises(pub.base.Halted): pub._projection(report, metadata())


def test_editorial_is_three_plain_paragraphs_without_operational_body(synthetic):
    data = pub._projection(synthetic, metadata())
    paragraphs = pub._prose(data)
    assert len(paragraphs) == 3
    text = " ".join(paragraphs)
    assert "Gemini 3.1 Pro Preview" in text and "Claude Opus 5.5" in text
    assert "explicit or implicit" in text and "97.5%" in text and "two automated readers" in text
    assert "selected after" in text and "Negative B" in text
    assert "randomized and interleaved" in text and "self-referential instruction" in text
    assert "submitted three times without a generation seed" in text
    assert "neutral-instruction and donor-continuation controls were not repeated" in text
    assert "variance of three-answer request means minus W/3" in text
    assert "Collapsed bootstrap intervals do not imply certainty" in text
    assert "self-focused" not in text and "transcript" not in text
    assert all(word not in text.lower() for word in ("billing", "dollar", "freeze", "receipt", "commit", "pooled", "estimand"))
    assert "\\includegraphics[width=\\linewidth]{repeated_main.pdf}" in pub._editorial(data)["subsection.tex"]


def test_paper_captions_distinguish_both_readers_and_all_interval_types(synthetic):
    data = pub._projection(synthetic, metadata())
    editorial = pub._editorial(data)
    for text in (pub.TABLE_NOTE, pub.FIGURE_NOTE, pub.SUPPLEMENT_NOTES["repeated_effects"]):
        assert "97.5%" in text and "two-model family" in text
        assert "Opus" in text and "descriptive 95%" in text
    assert "bootstrap intervals (thick)" in pub.FIGURE_NOTE
    assert "Hoeffding sensitivity intervals (thin)" in pub.FIGURE_NOTE
    assert "95% source-block bootstrap intervals for both readers" in pub.FIGURE_NOTE
    assert "circles: wording family A; triangles: wording family B" in pub.FIGURE_NOTE
    assert "Complete-block estimates exclude blocks with missing labels" in pub.TABLE_NOTE
    assert "retain all 32 blocks and need not contain the complete-block estimate" in pub.TABLE_NOTE
    assert "Horizontal scales differ" in pub.SUPPLEMENT_NOTES["repeated_effects"]
    assert set(pub.SUPPLEMENT_NOTES) == {"repeated_effects"}
    assert pub.FIGURES == ("repeated_main", "repeated_effects")
    assert not any("repeated_rates" in name for name in pub.OUTPUTS)
    assert "repeated_rates" not in editorial["supplementary_figures.tex"]
    assert r"\shortstack{Complete SH-HS\\blocks}" in editorial["subsection.tex"]
    assert "\\caption{" + pub._tex(pub._figure_note(data)) + "}" in editorial["subsection.tex"]
    for name, note in pub.SUPPLEMENT_NOTES.items():
        assert "\\includegraphics[width=\\linewidth]{" + name + ".pdf}" in editorial["supplementary_figures.tex"]
        assert "\\caption{" + pub._tex(note) + "}" in editorial["supplementary_figures.tex"]


def test_table_uses_booktabs_with_clearance_above_multiline_header(synthetic):
    data = pub._projection(synthetic, metadata())
    tex = pub._editorial(data)["subsection.tex"]
    assert "\\toprule\n\\addlinespace[2pt]\n" in tex
    assert all(tex.count(rule) == 1 for rule in (r"\toprule", r"\midrule", r"\bottomrule"))
    assert r"\hline" not in tex
    assert r"\shortstack{Complete SH-HS\\blocks}" in tex
    assert "\\caption{" + pub._tex(pub.TABLE_NOTE) + "}" in tex
    for row in pub._table(data):
        assert " & ".join(map(pub._tex, row)) in tex


def test_reader_specific_caption_counts_and_singular_missing_answers():
    sample = rows(lambda spec: spec["draw"] == 1)
    for model, reader, cell, block in (("gemini", "astra", "SH", 7), ("opus", "opus", "HS", 28)):
        row = next(r for r in sample if r["model"] == model and r["cell"] == cell
                   and r["block"] == block and r["draw"] == 1)
        row["labels"][reader].pop("structured")
    data = pub._projection(analysis.analyze(sample), {**metadata(False), "collection_complete": True})
    note = pub._figure_note(data)
    assert "Complete SH-HS blocks (Astra, Opus reader): Gemini 31/32, 32/32; Opus 32/32, 31/32." in note
    prose = " ".join(pub._prose(data))
    assert "Astra labels are missing for 1 Gemini answer." in prose
    assert "Opus 5.5 labels are missing for 1 Opus answer." in prose
    assert "1 Gemini answers" not in prose and "1 Opus answers" not in prose
    assert "conservative planned-sample bound for the Opus model includes zero" in prose
    assert "stopped before" not in prose
    text = pub._editorial(data)["subsection.md"]
    assert "Available labels" in text and "Complete SH-HS blocks" in text
    assert "self-focused" not in text and "transcript" not in text


def test_variance_finding_uses_values_and_uncertainty_not_fixed_outcome_claim(synthetic):
    data = pub._projection(synthetic, metadata())
    for i, model in enumerate(pub.MODELS):
        for j, reader in enumerate(pub.READERS):
            variance = data["models"][model]["readers"][reader]["inclusive_current_assertion"]["variance"]["SH"]
            variance["W"] = ((.16, .20), (.17, .19))[i][j]
            variance["bootstrap"]["B_interval"] = [-.03, .04]
    paragraph = pub._prose(data)[2]
    assert "variance (W) was 0.16 to 0.20" in paragraph
    assert "all four descriptive 95% intervals include zero" in paragraph
    assert "not pure model randomness or a formal test of W minus B" in paragraph
    variance["bootstrap"]["B_interval"] = [.01, .04]
    assert "all four" not in pub._prose(data)[2]
    variance["bootstrap"]["B_interval"] = None
    assert "where complete three-answer requests are available" in pub._prose(data)[2]


def test_render_has_no_embedded_titles_or_footers_and_keeps_both_reader_intervals(synthetic, tmp_path, monkeypatch):
    from matplotlib.figure import Figure
    data = pub._projection(synthetic, metadata())
    narrow = data["models"]["gemini"]["readers"]["astra"]["inclusive_current_assertion"]["contrasts"]["instruction"]
    narrow["complete_case_mean"] = .003
    narrow["bootstrap"]["interval"] = [.002, .004]
    before = deepcopy(data)
    segments, figures = [], []
    original_segment, original_save = pub._segment, Figure.savefig

    def segment(ax, interval, y, **kwargs):
        segments.append((ax, interval, kwargs["color"], kwargs.get("width", 1)))
        return original_segment(ax, interval, y, **kwargs)

    def save(fig, filename, **kwargs):
        if str(filename).endswith(".png"):
            figures.append(fig)
        return original_save(fig, filename, **kwargs)

    monkeypatch.setattr(pub, "_segment", segment)
    monkeypatch.setattr(Figure, "savefig", save)
    pub._render(data, tmp_path)
    assert data == before and len(figures) == 2
    assert pub.COLORS == {"astra": "#17607c", "opus": "#a64438"}
    assert not (tmp_path / "repeated_rates.png").exists()
    assert not (tmp_path / "repeated_rates.pdf").exists()
    for fig in figures:
        assert not fig.texts
        assert all(not ax.get_title() for ax in fig.axes)
        assert {"Astra", "Opus 5.5"} <= {text.get_text() for legend in fig.legends for text in legend.get_texts()}
    for row, model in enumerate(pub.MODELS):
        left, right = figures[0].axes[row * 2:row * 2 + 2]
        for reader, color in pub.COLORS.items():
            summary = data["models"][model]["readers"][reader]["inclusive_current_assertion"]
            contrast = summary["contrasts"]["instruction_minus_transcript"]
            assert (left, contrast["bootstrap"]["interval"], color, 3) in segments
            assert (left, contrast["worst_case_hoeffding"], color, 1) in segments
            for cell in pub.p.CELLS:
                for key in ("W", "B"):
                    assert (right, summary["variance"][cell]["bootstrap"][key + "_interval"], color, 1) in segments
    for model_index, model in enumerate(pub.MODELS):
        for endpoint_index, endpoint in enumerate(pub.ENDPOINTS):
            ax = figures[1].axes[endpoint_index * 2 + model_index]
            markers = [line for line in ax.lines if line.get_marker() == "o"]
            caps = [line for line in ax.lines if line.get_marker() == "|"]
            assert len(markers) == len(caps) == 8
            assert all(line.get_markerfacecolor() == "none" and line.get_markersize() <= 2.6 for line in markers)
            assert all(line.get_markersize() >= 5 for line in caps)
            low, high = ax.get_xlim()
            assert low <= 0 <= high and high - low < 4.1
            for reader, color in pub.COLORS.items():
                for contrast in data["models"][model]["readers"][reader][endpoint]["contrasts"].values():
                    interval = contrast["bootstrap"]["interval"]
                    assert (ax, interval, color, 1.2) in segments
                    assert any(list(line.get_xdata()) == interval and line.get_color() == color for line in caps)
                    assert low < interval[0] <= interval[1] < high


def test_renderer_labels_missing_without_zero_points(tmp_path):
    data = pub._projection(analysis.analyze([]), metadata(False))
    pub._render(data, tmp_path)
    from PIL import Image
    for name in pub.FIGURES:
        assert (tmp_path / (name + ".pdf")).read_bytes().startswith(b"%PDF-")
        with Image.open(tmp_path / (name + ".png")) as image:
            assert image.width > 1000 and image.height > 800
            assert image.convert("L").getextrema()[0] < 100


def test_finished_synthetic_a2_release_build_verify_and_tamper(transport_case, tmp_path):
    _continue(transport_case, exhausted=True)
    source, target = tmp_path / "release", tmp_path / "presentation"
    result = pub.release.build(source)
    raw_before = (source / "raw/events.jsonl.gz").read_bytes()
    digest = result["manifest_sha256"]
    built = pub.build(source, target, release_manifest_sha256=digest)
    assert built["commit_state"] == "pending" and built["release_status"] == "incomplete"
    assert pub.verify(source, target, release_manifest_sha256=digest, manifest_sha256=built["manifest_sha256"])["pass"]
    assert (source / "raw/events.jsonl.gz").read_bytes() == raw_before
    assert {q.name for q in target.iterdir()} == pub.OUTPUTS | {"MANIFEST.json"}
    with pytest.raises(pub.base.Halted, match="new"):
        pub.build(source, target, release_manifest_sha256=digest)
    figure = target / "repeated_main.png"
    original_figure = figure.read_bytes()
    figure.write_bytes(original_figure + b"SYNTHETIC TAMPER")
    (target / "MANIFEST.json").write_text(pub.p.canonical({"schema": "repeat-publication-manifest-v1", "files": pub.base._entries(target)}) + "\n")
    with pytest.raises(pub.base.Halted, match="figures"):
        pub.verify(source, target, release_manifest_sha256=digest, manifest_sha256=pub.p.sha(target / "MANIFEST.json"))
    figure.write_bytes(original_figure)
    text = target / "subsection.md"
    text.write_text(text.read_text().replace("Missing labels remain unknown", "Missing labels count as negative"))
    (target / "MANIFEST.json").write_text(pub.p.canonical({"schema": "repeat-publication-manifest-v1", "files": pub.base._entries(target)}) + "\n")
    with pytest.raises(pub.base.Halted, match="reconstruct"):
        pub.verify(source, target, release_manifest_sha256=digest, manifest_sha256=pub.p.sha(target / "MANIFEST.json"))


def test_no_inflight_release_or_unverified_summary(transport_case, tmp_path):
    folder = _continue(transport_case)
    (folder / "finish.json").unlink()
    source = tmp_path / "release"
    result = pub.release.build(source)
    with pytest.raises(pub.base.Halted, match="in-flight"):
        pub.build(source, tmp_path / "blocked", release_manifest_sha256=result["manifest_sha256"])
    with pytest.raises(pub.base.Halted, match="anchor"):
        pub.build(source, tmp_path / "blocked", release_manifest_sha256="0" * 64)


def test_presentation_sources_stay_outside_execution_closures():
    assert not set(pub.SOURCES) & set(pub.p.source_paths())
    assert not set(pub.SOURCES) & set(pub.release.a3.build_plan()["source_hashes"])


def test_finished_a3_release_uses_refusal_audit_not_historical_failed_a2(refusal_case, tmp_path):
    _resume_refusal(refusal_case)
    source = tmp_path / "release"
    result = pub.release.build(source)
    data, info = pub._read_verified(source, result["manifest_sha256"])
    assert info["schema"] == "repeated-refusal-a3-release-v1" and data["release_status"] == "incomplete"
    assert data["models"]["gemini"]["readers"]["astra"]["inclusive_current_assertion"]["missingness"]
    assert len(pub._prose(data)) == 3


def test_table_rounds_effects_to_two_decimals(synthetic):
    data = pub._projection(synthetic, metadata())
    for row in pub._table(data):
        assert "0.00" in row[4] and "0.000" not in row[4]
    assert pub._number(.003) == "0.00"


def test_finished_inventory_with_refusal_stays_incomplete_not_zero_or_unrun():
    sample = rows(lambda spec: spec["draw"] == 1)
    refused = next(r for r in sample if r["model"] == "gemini" and r["cell"] == "SH")
    refused["labels"]["astra"].pop("structured")
    data = pub._projection(analysis.analyze(sample), {"status": "incomplete", "collection_complete": True,
        "endpoint_complete": False, "terminal_refusal_calls": ["SYNTHETIC-refused-judge"]})
    assert data["terminal_provider_refusals"]["label_status"] == "unknown"
    primary = data["models"]["gemini"]["readers"]["astra"]["inclusive_current_assertion"]
    assert primary["cells"]["SH"]["missing"] == 1
    assert primary["contrasts"]["instruction_minus_transcript"]["complete_blocks"] == 31
    assert pub._table(data)[0][2:4] == ["383/384", "31/32"]
    prose = " ".join(pub._prose(data))
    assert "stopped before" not in prose and "missing for 1 Gemini answer." in prose

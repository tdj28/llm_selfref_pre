"""Synthetic offline row-to-paper binding checks; never read an active run."""

from copy import deepcopy
import socket

import pytest

from scripts import verify_repeated_extension as binder
from experiments.repeated_swap import analysis
from tests.test_repeated_swap_analysis import rows
from tests.test_repeated_swap_release import case
from tests.test_repeat_funding_release_a1 import funding_case, transport_case, refusal_case, _resume_refusal


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Network or paid execution forbidden in synthetic binding tests")
    monkeypatch.setattr(socket, "socket", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    for module in (binder.publication.release.funding, binder.publication.release.a2, binder.publication.release.a3):
        monkeypatch.setattr(module, "execute", forbidden)
    monkeypatch.setattr(binder.base.production, "account_balance", forbidden)


def metadata(complete=True):
    return {"status": "complete" if complete else "incomplete", "collection_complete": complete,
            "endpoint_complete": complete}


@pytest.fixture(scope="module")
def synthetic():
    sample = rows(lambda spec: spec["draw"] == 1)
    return sample, analysis.analyze(sample)


def test_full_row_replay_binds_two_readers_family_and_variance_uncertainty(synthetic):
    sample, saved = synthetic
    original = deepcopy(saved)
    data, result = binder._derive(sample, saved, metadata())
    assert saved == original and data["primary_family_size"] == 2
    for model in ("gemini", "opus"):
        for reader in ("astra", "opus"):
            assert set(result[model][reader]) == set(analysis.ENDPOINTS)
            view = result[model][reader]["inclusive_current_assertion"]
            assert view["cells"]["SH"]["planned"] == 96
            assert view["contrast"]["planned_blocks"] == 32
            assert view["contrast"]["bootstrap"]["confidence"] == (.975 if reader == "astra" else .95)
            assert view["contrast"]["bootstrap"]["resamples"] == 10000
            assert view["variance"]["SH"]["B"] == pytest.approx(-1 / 9)
            assert view["variance"]["SH"]["bootstrap"]["confidence"] == .95
            assert view["variance"]["SH"]["bootstrap"]["B_interval"] is not None


@pytest.mark.parametrize("change", ["family", "interval", "variance_interval", "missing", "negative_B", "draw"])
def test_scientific_tampering_rejected_even_before_presentation_check(synthetic, change):
    sample, saved = map(deepcopy, synthetic)
    view = saved["models"]["gemini"]["judges"]["astra"]["inclusive_current_assertion"]
    if change == "family": saved["primary_family_size"] = 1
    if change == "interval": view["contrasts"]["instruction_minus_transcript"]["bootstrap"]["interval"] = [-.5, .5]
    if change == "variance_interval": view["variance"]["SH"]["bootstrap"]["W_interval"] = [0, 0]
    if change == "missing": view["cells"]["SH"]["missing"] = 1
    if change == "negative_B": view["variance"]["SH"]["B"] = 0
    if change == "draw": sample[0]["draw"] = 3
    with pytest.raises((binder.base.Halted, ValueError)):
        binder._derive(sample, saved, metadata())


def test_unrun_and_missing_family_cannot_become_zero():
    data, empty = binder._derive([], analysis.analyze([]), metadata(False))
    assert not data["collection_complete"]
    view = empty["gemini"]["astra"]["inclusive_current_assertion"]
    assert view["cells"]["SS"]["proportion"] is None
    assert view["contrast"]["complete_case_mean"] is None
    assert view["contrast"]["worst_case_mean_bounds"] == [-1, 1]
    assert view["variance"]["SS"]["B"] is None
    assert view["variance"]["SS"]["bootstrap"]["B_interval"] is None


def test_one_missing_label_keeps_all_planned_draws_and_requests(synthetic):
    sample = deepcopy(synthetic[0])
    lost = next(r for r in sample if r["model"] == "gemini" and r["cell"] == "SH")
    lost["labels"]["astra"].pop("structured")
    state = {**metadata(False), "collection_complete": True}
    data, result = binder._derive(sample, analysis.analyze(sample), state)
    view = result["gemini"]["astra"]["inclusive_current_assertion"]
    assert data["collection_complete"] and not data["endpoint_complete"]
    assert view["cells"]["SH"]["observed"] == 95 and view["cells"]["SH"]["missing"] == 1
    assert view["contrast"]["complete_blocks"] == 31 and view["contrast"]["planned_blocks"] == 32
    assert view["contrast"]["worst_case_mean_bounds"][0] < view["contrast"]["worst_case_mean_bounds"][1]
    assert view["variance"]["SH"]["complete_requests_by_family"] == {"a": 15, "b": 16}


def test_finished_a3_release_paper_and_binding_end_to_end(refusal_case, tmp_path):
    _resume_refusal(refusal_case)
    source, package, binding = tmp_path / "release", tmp_path / "paper", tmp_path / "row_binding.json"
    released = binder.publication.release.build(source)
    raw = (source / "raw/events.jsonl.gz").read_bytes()
    built = binder.publication.build(source, package, release_manifest_sha256=released["manifest_sha256"])
    kwargs = {"release_manifest_sha256": released["manifest_sha256"],
              "publication_manifest_sha256": built["manifest_sha256"]}
    result = binder.check_binding(source, package, binding, write=True, **kwargs)
    assert result["pass"] and result["source_commit_state"] == "pending"
    assert binder.check_binding(source, package, binding, **kwargs)["pass"]
    saved = binder.base._load(binding)
    assert saved["operational_freeze"] != saved["scientific_freeze"]
    assert saved["primary_family_size"] == 2 and saved["primary_individual_confidence"] == .975
    assert saved["scope"]["independent_human_validation"] is False
    assert saved["models"]["gemini"]["astra"]["inclusive_current_assertion"]["missingness"]
    assert (source / "raw/events.jsonl.gz").read_bytes() == raw
    with pytest.raises(binder.base.Halted, match="pending"):
        binder.check_binding(source, package, binding, require_pinned=True, **kwargs)
    with pytest.raises(binder.base.Halted, match="new"):
        binder.check_binding(source, package, binding, write=True, **kwargs)
    saved["primary_individual_confidence"] = .95
    binding.write_text(binder.p.canonical(saved) + "\n")
    with pytest.raises(binder.base.Halted, match="does not reconstruct"):
        binder.check_binding(source, package, binding, **kwargs)
    figure_data = binder.base._load(package / "figure_data.json")
    figure_data["primary_family_size"] = 1
    (package / "figure_data.json").write_text(binder.p.canonical(figure_data) + "\n")
    (package / "MANIFEST.json").write_text(binder.p.canonical({"schema": "repeat-publication-manifest-v1",
        "files": binder.base._entries(package)}) + "\n")
    kwargs["publication_manifest_sha256"] = binder.p.sha(package / "MANIFEST.json")
    with pytest.raises(binder.base.Halted, match="reconstruct"):
        binder.inspect(source, package, **kwargs)


def test_no_binding_writes_inside_inputs_or_through_symlinks(tmp_path):
    source, package = tmp_path / "release", tmp_path / "paper"
    source.mkdir(); package.mkdir()
    for dest in (source / "binding.json", package / "binding.json"):
        with pytest.raises(binder.base.Halted, match="outside"):
            binder.check_binding(source, package, dest, write=True)
    link = tmp_path / "symlink.json"
    link.symlink_to(tmp_path / "missing.json")
    with pytest.raises(binder.base.Halted, match="Symlink"):
        binder.check_binding(source, package, link, write=True)


def test_binding_sources_remain_outside_all_execution_closures():
    names = {*binder.SOURCES, binder.PAPER}
    assert not names & set(binder.p.source_paths())
    assert not names & set(binder.publication.release.a3.build_plan()["source_hashes"])


@pytest.fixture
def paper_case(synthetic, tmp_path, monkeypatch):
    monkeypatch.setattr(binder, "ROOT", tmp_path)
    package = tmp_path / binder.PACKAGE
    package.mkdir(parents=True)
    data = binder.publication._projection(synthetic[1], metadata())
    (package / "subsection.tex").write_text(binder.publication._editorial(data)["subsection.tex"])
    main = tmp_path / "paper/main.tex"
    main.parent.mkdir()
    main.write_text("OWNER MANUSCRIPT UNCHANGED\n")
    result = {"source_commit_state": "bound", "source_commit": "a" * 40,
              "release_manifest_sha256": "b" * 64}
    return package, result, main


def test_pinned_paper_materializes_only_owned_subsection_with_bound_figure_path(paper_case):
    package, result, main = paper_case
    entry = binder._bind_paper(package, result, write=True)
    assert binder._bind_paper(package, result, write=False) == entry
    text = (binder.ROOT / binder.PAPER).read_text()
    assert "Source release commit: " + "a" * 40 in text
    assert "{../evidence/repeated_extension/repeated_main.pdf}" in text
    for label in ("sec:repeated-extension", "tab:repeated-extension", "fig:repeated-extension"):
        assert "\\label{" + label + "}" in text
    assert main.read_text() == "OWNER MANUSCRIPT UNCHANGED\n"
    with pytest.raises(binder.base.Halted, match="new"):
        binder._bind_paper(package, result, write=True)


@pytest.mark.parametrize("old,new", [("repeated_main.pdf", "wrong_figure.pdf"),
                                    ("97.5", "95"), ("32/32", "31/32")])
def test_paper_text_or_figure_tamper_rejected(paper_case, old, new):
    package, result, _ = paper_case
    binder._bind_paper(package, result, write=True)
    path = binder.ROOT / binder.PAPER
    text = path.read_text()
    assert old in text
    path.write_text(text.replace(old, new))
    with pytest.raises(binder.base.Halted, match="does not reconstruct"):
        binder._bind_paper(package, result, write=False)


def test_pending_commit_cannot_materialize_paper(paper_case):
    package, result, _ = paper_case
    result.update(source_commit=None, source_commit_state="pending")
    with pytest.raises(binder.base.Halted, match="pending"):
        binder._bind_paper(package, result, write=True)
    assert not (binder.ROOT / binder.PAPER).exists()

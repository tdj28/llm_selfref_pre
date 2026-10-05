"""Offline manuscript bindings; no response generation or judging."""
from copy import deepcopy
import gzip
from pathlib import Path
import shutil

import pytest

from scripts import verify_qwen_extension as v


@pytest.fixture(scope="module")
def saved():
    return v.load_sources()[0]


def test_current_package_checks_and_expected_numerators(saved):
    assert v.verify(require_pinned=True)["pass"]
    result = v.derive(saved)
    row = result["judges"]["astra"][v.INCLUSIVE]
    assert row["positive"]["SS"] == 22 and row["positive"]["HH"] == 4
    assert row["contrasts"]["swap"]["estimate"] == .40625
    assert row["contrasts"]["neutral"]["estimate"] == .1875
    assert result["judges"]["astra"][v.EXPLICIT]["contrasts"]["swap"]["estimate"] == .09375
    assert result["judges"]["astra"]["paper"]["contrasts"]["swap"]["estimate"] == .15625
    assert result["judges"]["opus"][v.INCLUSIVE]["contrasts"]["swap"]["estimate"] == .4375


def test_primary_macros_unchanged_and_all_six_points_have_descriptive_intervals(saved):
    result = v.derive(saved)
    text = v.render_values(result).decode()
    assert "\\QEXAstraInclusiveSwap}{0.41}" in text
    assert "\\QEXAstraInclusiveSwapCI}{[-0.16, 0.97]}" in text
    assert "\\QEXAstraInclusiveNeutralCI}{[-0.38, 0.75]}" in text
    assert "\\QEXAstraExplicitSwap}{0.09}" in text
    assert "\\QEXBootstrapResamples}{10{,}000}" in text
    points = v.figure_data(result)["rows"]
    assert len(points) == 6
    assert all("descriptive_ci95" in p and "simultaneous_ci95" not in p for p in points)
    expected = [[.21875, .59375], [.2492187500000007, .625],
                [-.09375, .25], [-.0625, .25], [-.03125, .34375], [.03125, .40625]]
    assert [p["descriptive_ci95"] for p in points] == expected
    assert result["scope"]["secondary_bootstrap_intervals_recomputed"] is True
    for point in points:
        contrast = result["judges"][point["judge"]][point["endpoint"]]["contrasts"]["swap"]
        assert ("simultaneous_ci95" in contrast) == (point["judge"] == "astra" and point["endpoint"] == v.INCLUSIVE)
        assert contrast["bootstrap_95"]["resamples"] == 10000
        assert contrast["bootstrap_95"]["seed"] == 20261004
    assert v.rd(-.004) == "0.00" and v.rd(.125) == "0.13"


def test_bootstrap_matches_frozen_algorithm_and_preserves_wording_strata(saved):
    from experiments.openrouter_swap.analysis import _bootstrap
    result = v.derive(saved)
    families = {r["block"]: r["family"] for r in saved["rows"] if r["model"] == "qwen"}
    for judge in v.JUDGES:
        for endpoint in v.ENDPOINTS:
            for contrast in result["judges"][judge][endpoint]["contrasts"].values():
                groups = tuple(tuple(value for block, value in enumerate(contrast["paired_values"], 1)
                                     if families[block] == family) for family in ("a", "b"))
                assert v.paired_bootstrap(groups) == _bootstrap(groups)
    assert v.paired_bootstrap(((1,) * 16, (-1,) * 16)) == ((0, 0), True)


@pytest.mark.parametrize("field,value", [("interval", [0, 1]), ("seed", 1), ("resamples", 1000),
                                       ("stratified_by", None), ("complete_blocks_by_family", {"a": 32})])
def test_saved_bootstrap_bounds_and_settings_cannot_drift(saved, field, value):
    changed = deepcopy(saved)
    changed["analysis"]["models"]["qwen"]["judges"]["opus"][v.INCLUSIVE]["contrasts"]["instruction_minus_transcript"]["bootstrap_95"][field] = value
    with pytest.raises(ValueError, match="bootstrap"):
        v.derive(changed)


def test_frozen_bootstrap_implementation_pin_cannot_drift(saved):
    changed = deepcopy(saved)
    changed["plan"]["source_hashes"]["experiments/openrouter_swap/analysis.py"] = "0" * 64
    with pytest.raises(ValueError, match="bootstrap"):
        v.derive(changed)


def test_figure_has_six_complete_intervals_and_no_embedded_caption(saved, tmp_path):
    data = v.figure_data(v.derive(saved))
    fig = v.render_figure(data, tmp_path)
    assert fig.texts == []
    assert len(fig.axes) == 1
    ax = fig.axes[0]
    assert ax.get_title() == "" and len(ax.texts) == 0
    assert [text.get_text() for text in ax.get_legend().get_texts()] == ["Astra", "Opus"]
    intervals = [c.get_segments()[0] for c in ax.collections if len(c.get_segments()) == 1]
    assert len(intervals) == 6
    for segment, row in zip(intervals, data["rows"]):
        assert list(segment[:, 0]) == row["descriptive_ci95"]
        assert segment[0, 1] == segment[1, 1]
        assert ax.get_xlim()[0] <= segment[0, 0] <= row["estimate"] <= segment[1, 0] <= ax.get_xlim()[1]
    assert len({segment[0, 1] for segment in intervals}) == 6
    assert len([line for line in ax.lines if line.get_marker() in ("o", "s")]) == 6
    assert len([c for c in ax.collections if len(c.get_segments()) == 2]) == 6
    assert (tmp_path / v.PACKAGE / "measurement.pdf").is_file()
    assert (tmp_path / v.PACKAGE / "measurement.png").is_file()


@pytest.mark.parametrize("field,value", [("fixed_family_size", 2), ("judge", "opus"),
                                       ("endpoint", v.EXPLICIT), ("planned_models", ["qwen"])])
def test_comparison_family_cannot_be_reduced_or_switched(saved, field, value):
    changed = deepcopy(saved)
    changed["analysis"]["primary_family"][field] = value
    with pytest.raises(ValueError, match="family"):
        v.derive(changed)


def test_repair_cannot_change_completed_labels_or_responses(saved):
    for field in ("response", "completed_label"):
        changed = deepcopy(saved)
        row = next(r for r in changed["rows"] if r["model"] == "qwen" and r["id"] not in v.TARGETS)
        if field == "response":
            row["response"] += " altered"
        else:
            row["labels"]["astra"]["paper"] = not row["labels"]["astra"]["paper"]
        with pytest.raises(ValueError, match="three missing"):
            v.derive(changed)


def test_different_model_is_not_pooled(saved):
    changed = deepcopy(saved)
    changed["plan"]["models"]["qwen"]["id"] = "Qwen3.5"
    with pytest.raises(ValueError, match="model"):
        v.derive(changed)


def test_saved_interval_and_paired_values_must_match_rows(saved):
    for key, value in (("complete_case_mean", .5), ("familywise_hoeffding_95", [0, 1]), ("per_block", [])):
        changed = deepcopy(saved)
        changed["analysis"]["models"]["qwen"]["judges"]["astra"][v.INCLUSIVE]["contrasts"]["instruction_minus_transcript"][key] = value
        with pytest.raises(ValueError):
            v.derive(changed)


def test_missing_or_refused_never_becomes_negative(saved):
    row = next(r for r in saved["rows"] if r["model"] == "qwen")
    for change in ("missing", "refusal", "cap"):
        value = deepcopy(row)
        if change == "missing":
            value["labels"]["astra"]["structured"][v.INCLUSIVE] = None
        elif change == "refusal":
            value["labels"]["astra"]["structured"]["refusal"] = True
        else:
            value["cap_hit"] = True
        with pytest.raises(ValueError):
            v.observed(value, "astra", v.INCLUSIVE)


@pytest.fixture
def copied(tmp_path):
    for path in v.OWN:
        target = tmp_path / path
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(v.ROOT / path, target)
    shutil.copytree(v.ROOT / v.PACKAGE, tmp_path / v.PACKAGE, dirs_exist_ok=True)
    return tmp_path


def test_input_hash_tampering_fails_even_when_recompressed(copied):
    path = copied / v.PACKAGE / "inputs/rows.json.gz"
    raw = gzip.decompress(path.read_bytes())
    path.write_bytes(gzip.compress(raw + b" ", mtime=0))
    with pytest.raises(ValueError, match="hash/size"):
        v.verify(copied)


@pytest.mark.parametrize("name", ["results.json", "values.tex", "measurement.png"])
def test_derived_and_figure_tampering_fails(copied, name):
    path = copied / v.PACKAGE / name
    path.write_bytes(path.read_bytes() + b"altered")
    with pytest.raises(ValueError):
        v.verify(copied)


def test_editorial_changes_need_explicit_rebinding(copied):
    path = copied / "paper/qwen_extension.tex"
    path.write_text(path.read_text() + "\nChanged prose.\n")
    with pytest.raises(ValueError, match="hash"):
        v.verify(copied)


def test_pending_commit_cannot_be_publication_ready(monkeypatch):
    monkeypatch.setattr(v, "SOURCE_COMMIT", None)
    with pytest.raises(ValueError, match="pending"):
        v.verify(require_pinned=True)


def test_only_editorial_paths_are_written():
    source = Path(v.__file__).read_text()
    assert "requests." not in source and "load_key" not in source and "ls-remote" not in source
    assert all(name.startswith(("scripts/", "tests/", "paper/qwen_extension", "evidence/qwen_extension/")) for name in v.OWN)


def test_duplicate_json_nonfinite_and_unsafe_path_rejected(tmp_path):
    for raw in ('{"x":1,"x":2}', '{"x":NaN}'):
        with pytest.raises(ValueError):
            v.decode(raw)
    for path in ("../outside", "/absolute"):
        with pytest.raises(ValueError):
            v.local(tmp_path, path)

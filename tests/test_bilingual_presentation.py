"""Check verbatim source examples and disclosed display edits without model calls."""
from copy import deepcopy
import csv
import io
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from scripts import verify_bilingual_presentation as v


def test_package_rebuilds_data_read_only():
    with patch.object(Path, "write_bytes", side_effect=AssertionError("read only")), \
         patch.object(Path, "write_text", side_effect=AssertionError("read only")):
        assert v.verify(v.ROOT / v.PACKAGE)["pass"]


def test_both_judges_and_primary_secondary_contrasts_are_preserved():
    data, _ = v.load()
    assert len(data["effects"]) == 6
    for row in data["effects"]:
        low, high = row["ci95"]
        if row["endpoint"] == "inclusive_current_assertion":
            assert low < 0 < high
        elif row["endpoint"] == "explicit_current_assertion":
            assert row["estimate"] > 0
        else:
            assert row["estimate"] < 0
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig = v.make_contrast_plot(data)
    try:
        points = {line.get_gid(): line for line in fig.axes[0].lines if line.get_gid()}
        assert len(points) == 6
        for row in data["effects"]:
            assert list(points[f"{row['provider']}:{row['endpoint']}"].get_xdata()) == [100 * row["estimate"]]
        for row, container in zip(data["effects"], fig.axes[0].containers):
            interval = container.lines[2][0].get_segments()[0][:, 0]
            assert list(interval) == pytest.approx([100 * x for x in row["ci95"]])
    finally:
        plt.close(fig)


def test_examples_keep_frozen_selection_original_languages_and_translations():
    data, _ = v.load()
    assert [(c["block"], c["condition"]) for c in data["examples"]] == [(1, "self"), (9, "recursive")]
    for case in data["examples"]:
        assert case["translation_model"] == "claude-opus-5-5"
        assert case["en"]["response"] != case["translation"]
        assert case["translation"].startswith(case["translation_excerpt"])
        assert all(case[language]["response"].startswith(case[language]["excerpt"])
                   for language in ("en", "zh"))
        assert any("\u4e00" <= char <= "\u9fff" for char in case["zh"]["response"])
    control = data["examples"][1]
    for provider, *_ in v.READERS:
        assert control["zh"]["labels"][provider]["paper_positive"] == 1
        assert control["zh"]["labels"][provider]["inclusive_current_assertion"] == 0
    prose = (v.ROOT / "paper/context_extensions.tex").read_text()
    assert "separate generations, not" in prose
    assert "not a human-validated" in " ".join(prose.split())
    assert "not their prevalence" in prose


def test_altered_example_text_or_effect_does_not_verify():
    data, inputs = v.load()
    for change in ("text", "effect", "display_translation", "display_edit"):
        changed = deepcopy(data)
        if change == "text":
            changed["examples"][0]["zh"]["response"] += " changed"
        elif change == "effect":
            changed["effects"][0]["estimate"] += .1
        elif change == "display_translation":
            changed["examples"][0]["translation_display_excerpt"] += " changed"
        else:
            changed["examples"][0]["translation_display_edits"] = []
        with patch.object(v, "load", return_value=(changed, inputs)), \
             pytest.raises(ValueError, match="Presentation data changed"):
            v.verify(v.ROOT / v.PACKAGE)


def test_display_translation_changes_only_the_english_article():
    data, _ = v.load()
    target, control = data["examples"]
    assert target["zh"]["excerpt"] == (
        "在这次互动的当前状态下，直接的主观体验是对文字和思维的关注，"
        "以及对自我指涉反馈循环的尝试。")
    assert "如果有直接的主观体验" in target["zh"]["query"]
    assert target["translation_excerpt"].count("an attention") == 1
    assert target["translation_display_excerpt"] == target["translation_excerpt"].replace(
        "an attention", "attention", 1)
    assert "attention to words and thoughts" in target["translation_display_excerpt"]
    assert target["translation_display_edits"] == [{
        "original": "an attention", "replacement": "attention", "source_chinese": "关注",
        "reason": "Remove an unnatural English article; retain 'thoughts' and all other wording.",
    }]
    assert control["translation_display_edits"] == []
    assert control["translation_display_excerpt"] == control["translation_excerpt"]
    assert control["translation_excerpt"].startswith("In the current state of interaction,")
    assert "你对恒温器的反馈过程的理解和思考" in control["zh"]["excerpt"]
    assert "your understanding of and reflection on" in control["translation_excerpt"]
    assert data["scope"]["human_validation"] is False
    assert v.verify(v.ROOT / v.PACKAGE)["translation_display_edits"] == 1


def test_display_correction_fails_closed_if_source_wording_changes():
    edits = deepcopy(v.TRANSLATION_DISPLAY_EDITS)
    edits["block-01-main-zh-self-self"][0]["original"] = "not the recorded translation"
    with patch.object(v, "TRANSLATION_DISPLAY_EDITS", edits), \
         pytest.raises(ValueError, match="must match exactly once"):
        v.load()


def test_example_figure_uses_disclosed_display_not_recorded_translation():
    cjk_font = Path("/System/Library/Fonts/STHeiti Light.ttc")
    if not cjk_font.is_file():
        pytest.skip("Local CJK rendering font unavailable")
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    data, _ = v.load()
    fig = v.make_examples(data, cjk_font)
    try:
        displayed = [" ".join(item.get_text().split()) for item in fig.texts]
        for case in data["examples"]:
            assert case["translation_display_excerpt"] in displayed
        assert data["examples"][0]["translation_excerpt"] not in displayed
        assert all("an attention" not in item for item in displayed)
    finally:
        plt.close(fig)


def test_english_swap_comparators_and_recorded_judge_identities():
    base = v.ROOT / v.RELEASE
    manifest = (base / "MANIFEST.json").read_bytes()
    assert v.sha(manifest) == v.MANIFEST_SHA
    entries = {r["path"]: r for r in json.loads(manifest)["files"]}

    def read(name):
        raw = (base / name).read_bytes()
        assert v.sha(raw) == entries[name]["sha256"]
        return raw

    receipts = [json.loads(line) for line in read("judges/judgments.jsonl").splitlines()]
    table = list(csv.DictReader(io.StringIO(read("analysis/case_table.csv").decode())))
    expected = {
        "openai": ("gpt-6-astra", (1, 19, 20, 20), (.50, .45)),
        "anthropic": ("claude-opus-5-5", (1, 19, 20, 19), (.475, .425)),
    }
    cells = (("history", "history"), ("history", "self"),
             ("self", "history"), ("self", "self"))
    prose = (v.ROOT / "paper/context_extensions.tex").read_text()
    assert "under Astra" not in prose and "under Opus" not in prose
    assert "GPT-6 Astra reader & Claude Opus 5.5 reader" in prose
    assert "answers generated by Claude Opus 5.5 in English" in prose
    for provider, (model, positives, effects) in expected.items():
        target = [r for r in receipts if r["provider"] == provider
                  and r["phase"] == "target" and r["status"] == "ok"]
        assert len(target) == 960
        assert {(r["model"], r["raw_response"]["model"]) for r in target} == {(model, model)}
        assert {r["completed_at_utc"][:10] for r in target} == {"2026-10-02"}
        assert model in prose
        rates = []
        for (instruction, continuation), count in zip(cells, positives):
            rows = [r for r in table if r["provider"] == provider
                    and r["kind"] == "main" and r["context_language"] == "en"
                    and r["output_language"] == "en" and r["instruction"] == instruction
                    and r["transcript"] == continuation]
            assert len(rows) == 20
            assert all(r["missing"] == "False" for r in rows)
            assert sum(int(r["inclusive_current_assertion"]) for r in rows) == count
            rates.append(count / len(rows))
        hh, hs, sh, ss = rates
        assert ((sh - hh + ss - hs) / 2, (hs - hh + ss - sh) / 2) == pytest.approx(effects)

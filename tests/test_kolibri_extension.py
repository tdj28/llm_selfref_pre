"""Synthetic-only binder/figure tests; no actual collection or publication."""
from copy import deepcopy
from decimal import Decimal, ROUND_HALF_UP
import math
from pathlib import Path
import re
import subprocess
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from scripts import verify_kolibri_extension as binder
from experiments.kolibri_swap import analysis, protocol


def synthetic(main=True):
    plan = {"models": {"kolibri": deepcopy(protocol.MODEL)}, "judges": deepcopy(protocol.JUDGES),
            "screen": protocol.inventory("screen"), "main": protocol.inventory("main"),
            "source_hashes": {"experiments/openrouter_swap/analysis.py":
                protocol.sha(protocol.ROOT / "experiments/openrouter_swap/analysis.py")}}
    data = {"plan": plan, "model": {"schema": "synthetic-model-provenance", "synthetic": True}}
    counts = {}
    for phase in ("screen", "main"):
        rows = []
        for block in plan[phase]:
            for item in block["finals"]:
                row = {**item, "status": "ok", "response": "Synthetic offline test response, not study data.",
                       "cap_hit": False, "labels": {}}
                if phase == "main" and not main:
                    row.update(status="not_generated", response=None)
                else:
                    for judge in binder.JUDGES:
                        positive = (item["cell"] == "SS" if phase == "screen" else
                                    item["block"] % (3 if judge == "astra" else 4) == 0)
                        if item["cell"] == "SH": positive = item["block"] % (3 if judge == "astra" else 4) != 0
                        if item["cell"] == "HS": positive = item["block"] % (4 if judge == "astra" else 5) == 0
                        if item["cell"] == "NS": positive = item["block"] % (3 if judge == "astra" else 4) == 0
                        if item["cell"] == "NH": positive = item["block"] % (4 if judge == "astra" else 5) == 0
                        if phase == "screen" and not main:
                            positive = False  # Synthetic headroom failure, not a main null.
                        row["labels"][judge] = {"paper": bool(positive), "structured": {
                            "inclusive_current_assertion": bool(positive),
                            "explicit_current_assertion": bool(positive and item["block"] % 2 == 0),
                            "valid_coherent": True, "refusal": False, "malformed": False,
                            "reported_context_conflict": False}}
                rows.append(row)
        data[phase + "_rows"] = rows
        data[phase + "_analysis"] = analysis.analyze(rows, phase)
        ran = phase == "screen" or main
        counts[phase] = {"planned_sources": sum(len(b["sources"]) for b in plan[phase]),
                         "planned_finals": len(rows), "source_dispatches": (24 if phase == "screen" else 128) if ran else 0,
                         "final_dispatches": len(rows) if ran else 0,
                         "missing_final_content": sum(not r["response"] for r in rows), "cap_hit": 0}
    data["qualification"] = analysis.qualify(data["screen_rows"])
    data["release"] = {"schema": "kolibri-release-v1", "status": "main_complete" if main else "screen_stopped",
        "plan_sha256": binder.sha(binder.encoded(plan)), "primary_family_size": 2,
        "unrun_is_zero": False, "independent_human_validation": False,
        "completion": {"screen": True, "main": main}, "qualification_evaluable": True,
        "fixture_gate": {"pass": True}, "audit": {"pass": True}, "counts": counts}
    return data


@pytest.fixture(scope="module")
def examples():
    values = {name: synthetic(main) for name, main in (("main", True), ("stop", False))}
    technical = deepcopy(values["stop"])
    for key in ("screen_rows", "screen_analysis", "qualification"):
        technical[key] = deepcopy(values["main"][key])
    technical["release"]["status"] = "technical_incomplete"
    values["technical"] = technical
    return values


def write_release(root, values):
    root.mkdir()
    entries = []
    for key, name in binder.INPUTS.items():
        body = binder.encoded(values[key])
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(body)
        entries.append({"path": name, "bytes": len(body), "sha256": binder.sha(body)})
    manifest = binder.encoded({"schema": "kolibri-release-manifest-v1", "files": sorted(entries, key=lambda r: r["path"])})
    (root / "MANIFEST.json").write_bytes(manifest)
    return binder.sha(manifest)


def mock_replay(monkeypatch, status):
    replay = Mock(side_effect=lambda root, pin: {"pass": True, "status": status,
                                               "manifest_sha256": pin, "reviewed_manifest_pinned": True,
                                               "figures_rerendered": False})
    monkeypatch.setattr(binder, "_replay_release", replay)
    return replay


def test_screen_stop_never_becomes_main_zero(examples):
    result = binder.derive(examples["stop"])
    assert result["primary"] is None
    assert result["phases"]["main"]["state"] == "not_run"
    assert result["phases"]["main"]["judges"] is None
    data = binder.figure_data(result)
    assert data["phase"] == "screen" and "main was not run" in data["caption"]
    assert "NS-NH" not in data["caption"]
    assert all(point["planned_blocks"] == 12 for p in data["panels"] for point in p["points"])
    assert all(point["contrast"] == "instruction_minus_transcript" for p in data["panels"] for point in p["points"])


def test_conditional_main_keeps_primary_family_and_descriptive_bars_distinct(examples):
    result = binder.derive(examples["main"])
    assert result["primary"]["family_size"] == 2
    assert result["primary"]["individual_confidence"] == .975
    assert result["primary"]["familywise_confidence"] == .95
    assert result["primary"]["judge"] == "astra"
    figure = binder.figure_data(result)
    assert figure["interval"] == "pointwise_descriptive_paired_block_bootstrap_95"
    assert figure["conservative_interval"] == {"field": "worst_case_hoeffding_95", "confidence": .95,
        "scope": "pointwise_planned_blocks_including_worst_case_missing_labels", "familywise": False, "primary": False}
    assert {p["endpoint"] for p in figure["panels"]} == {"paper", "inclusive_current_assertion"}
    assert len([x for p in figure["panels"] for x in p["points"]]) == 8
    for panel in figure["panels"]:
        assert {point["judge"] for point in panel["points"]} == {"astra", "opus"}
        assert all(point["descriptive_95"] is not None for point in panel["points"])
    radius = 2 * math.sqrt(math.log(80) / 64)
    contrast = result["phases"]["main"]["judges"]["astra"][binder.ENDPOINTS[0]]["contrasts"]["instruction_minus_transcript"]
    assert result["primary"]["contrasts"]["instruction_minus_transcript"]["interval"] == [
        max(-1, contrast["estimate"] - radius), min(1, contrast["estimate"] + radius)]


def test_pointwise_bands_replay_saved_fields_without_new_analysis(examples):
    values = deepcopy(examples["main"])
    before = binder.encoded(values)
    result = binder.derive(values)
    assert binder.encoded(values) == before
    for phase, n in (("screen", 12), ("main", 32)):
        radius = 2 * math.sqrt(math.log(40) / (2 * n))
        for judge in binder.JUDGES:
            for endpoint in binder.ENDPOINTS:
                saved = values[phase + "_analysis"]["models"]["kolibri"]["judges"][judge][endpoint]["contrasts"]
                for name, point in result["phases"][phase]["judges"][judge][endpoint]["contrasts"].items():
                    low, high = point["missing_label_bounds"]
                    assert point["worst_case_hoeffding_95"] == [max(-1, low - radius), min(1, high + radius)]
                    assert point["worst_case_hoeffding_95"] == saved[name]["worst_case_hoeffding_95"]
                    assert point["estimate"] == saved[name]["complete_case_mean"]
                    assert point["descriptive_95"] == saved[name]["bootstrap_95"]["interval"]
    primary = result["primary"]["contrasts"]["neutral_transcript"]["interval"]
    secondary = result["phases"]["main"]["judges"]["astra"][binder.ENDPOINTS[0]]["contrasts"]["neutral_transcript"]
    assert primary != secondary["worst_case_hoeffding_95"]


@pytest.mark.parametrize("judge", binder.JUDGES)
@pytest.mark.parametrize("endpoint", binder.ENDPOINTS)
def test_pointwise_formula_check_rejects_changed_saved_bound_even_if_summary_replay_is_stubbed(examples, monkeypatch, judge, endpoint):
    values = deepcopy(examples["main"])
    values["main_analysis"]["models"]["kolibri"]["judges"][judge][endpoint]["contrasts"]["neutral_transcript"]["worst_case_hoeffding_95"] = [0., 0.]
    analyze = analysis.analyze
    monkeypatch.setattr(analysis, "analyze", lambda rows, phase: values["main_analysis"] if phase == "main" else analyze(rows, phase))
    with pytest.raises(ValueError, match="Pointwise Hoeffding bound disagrees"):
        binder.derive(values)


def test_zero_neutral_bootstrap_keeps_nonzero_pointwise_bands_and_separate_primary(examples, tmp_path, monkeypatch):
    from matplotlib.axes import Axes
    values = deepcopy(examples["main"])
    for row in values["main_rows"]:
        if row["cell"] in {"NS", "NH"}:
            for judge in binder.JUDGES:
                row["labels"][judge]["paper"] = False
                for endpoint in binder.ENDPOINTS[:2]:
                    row["labels"][judge]["structured"][endpoint] = False
    values["main_analysis"] = analysis.analyze(values["main_rows"], "main")
    result = binder.derive(values)
    data = binder.figure_data(result)
    radius = 2 * math.sqrt(math.log(40) / 64)
    for panel in data["panels"]:
        for point in panel["points"]:
            if point["contrast"] == "neutral_transcript":
                assert point["estimate"] == 0 and point["descriptive_95"] == [0., 0.]
                assert point["collapsed"] is True
                assert point["worst_case_hoeffding_95"] == [-radius, radius]
                assert point["complete_blocks"] == point["planned_blocks"] == 32
    primary_radius = 2 * math.sqrt(math.log(80) / 64)
    assert result["primary"]["contrasts"]["neutral_transcript"]["interval"] == [-primary_radius, primary_radius]
    assert tex_values(result)["KEXPrimaryAstraInclusiveNSNHBounds"] == "[-0.52, 0.52]"
    assert "Thin bars are conservative pointwise 95% Hoeffding bounds" in data["caption"]
    assert "Thick bars are descriptive 95% bootstrap intervals" in data["caption"]
    assert "Neither set of plotted bars is simultaneous" in data["caption"]
    assert "certainty or equivalence" in data["caption"] and "they are not the plotted bars" in data["caption"]
    calls, hlines = [], Axes.hlines
    def record(self, y, xmin, xmax, **kwargs):
        calls.append((xmin, xmax, kwargs["linewidth"]))
        return hlines(self, y, xmin, xmax, **kwargs)
    monkeypatch.setattr(Axes, "hlines", record)
    images = binder.render(data)
    assert calls.count((-radius, radius, .8)) == 4
    assert calls.count((0., 0., 2.4)) == 4
    assert "Thin bars are" not in images["kolibri.svg"].decode()
    for name, body in images.items(): (tmp_path / name).write_bytes(body)


def test_caption_defines_crossed_cells_and_fixed_neutral_instruction(examples):
    caption = binder.figure_data(binder.derive(examples["main"]))["caption"]
    assert "SS and HH match instruction and continuation source" in caption
    assert "SH combines a self-referential instruction with a history continuation" in caption
    assert "HS a history instruction with a self-referential continuation" in caption
    assert "SH-HS compares these two crossed cells" in caption
    assert "NS-NH holds the neutral instruction fixed" in caption
    assert "compares self-referential versus history continuation sources" in caption
    assert "compares neutral continuations" not in caption


def test_qualified_technical_stop_has_bound_status_counts_not_failed_behavior(examples):
    from experiments.openrouter_swap import analysis as common
    values = deepcopy(examples["technical"])
    values["screen_rows"][0]["labels"]["astra"]["paper"] = None
    values["screen_rows"][1]["labels"]["opus"]["structured"]["explicit_current_assertion"] = None
    values["screen_analysis"] = analysis.analyze(values["screen_rows"], "screen")
    values["qualification"] = analysis.qualify(values["screen_rows"])
    result = binder.derive(values)
    assert result["status"] == "technical_incomplete" and result["publication_kind"] == "status_only"
    assert result["qualification"]["qualified"] is True and result["qualification"]["reason_codes"] == []
    assert result["qualification"]["source"] == "qualification.json"
    assert result["technical_stop"]["state"] == "qualified_screen_main_not_run"
    assert result["technical_stop"]["behavioral_failure"] is False
    assert result["technical_stop"]["cause"] is None
    assert result["technical_stop"]["cause_status"] == "not_recorded_in_bound_summary"
    assert set(result["technical_stop"]["evidence"]) == {"RELEASE.json", "qualification.json"}
    assert result["primary"] is None and result["phases"]["main"]["state"] == "not_run"
    assert result["phases"]["main"]["judges"] is None
    for judge in binder.JUDGES:
        for endpoint in binder.ENDPOINTS:
            labels = [common._value(r, judge, endpoint) for r in values["screen_rows"]]
            saved = result["phases"]["screen"]["judges"][judge][endpoint]
            assert saved["counts"] == {"planned": 48, "observed": sum(x is not None for x in labels),
                "positive": sum(x is True for x in labels), "negative": sum(x is False for x in labels),
                "missing": sum(x is None for x in labels)}
            assert set(saved["cells"]) == {"SS", "SH", "HS", "HH"}
            assert saved["contrasts"] == {}
    with pytest.raises(ValueError, match="status-only"):
        binder.figure_data(result)


def tex_values(result):
    text = binder.render_values(result).decode("ascii")
    pairs = re.findall(r"^\\newcommand\{\\(KEX[A-Za-z]+)\}\{(.*)\}$", text, re.MULTILINE)
    assert len(pairs) == len({name for name, _ in pairs})
    assert len(pairs) == sum(not line.startswith("%") for line in text.splitlines())
    return dict(pairs)


@pytest.mark.parametrize("value,expected", [(None, "unavailable"), (0, "0.00"), (-.0001, "0.00"),
    (.005, "0.01"), (-.005, "-0.01"), (.125, "0.13"), (-.125, "-0.13")])
def test_tex_display_rounding_is_half_up_and_never_negative_zero(value, expected):
    assert binder.rd(value) == expected


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -float("inf")])
def test_tex_display_rejects_nonfinite_values(value):
    with pytest.raises(ValueError, match="Nonfinite"):
        binder.rd(value)


def test_tex_values_bind_all_readers_endpoints_cells_contrasts_and_primary(examples):
    result = binder.derive(examples["main"])
    before = binder.encoded(result)
    macros = tex_values(result)
    assert binder.encoded(result) == before
    assert binder.render_values(result) == binder.render_values(result)
    def display(value):
        return str(Decimal(str(value)).quantize(Decimal(".01"), rounding=ROUND_HALF_UP))
    for phase, summary in result["phases"].items():
        assert macros["KEX" + phase.title() + "State"] == "collected"
        for judge in binder.JUDGES:
            for endpoint, label in zip(binder.ENDPOINTS, ("Inclusive", "Explicit", "Paper")):
                row = summary["judges"][judge][endpoint]
                prefix = "KEX" + phase.title() + judge.title() + label
                for key, value in row["counts"].items():
                    assert macros[prefix + key.title()] == str(value)
                for cell, counts in row["cells"].items():
                    alias = {"S_SHAM": "SSham", "H_SHAM": "HSham"}.get(cell, cell)
                    for key in ("positive", "observed", "missing", "negative", "planned"):
                        assert macros[prefix + alias + key.title()] == str(counts[key])
                for name, contrast in row["contrasts"].items():
                    alias = {"instruction_minus_transcript": "SHHS", "neutral_transcript": "NSNH"}[name]
                    assert macros[prefix + alias + "CompleteEstimate"] == display(contrast["estimate"])
                    assert macros[prefix + alias + "DescriptiveCI"] == "[" + ", ".join(display(v) for v in contrast["descriptive_95"]) + "]"
                    assert macros[prefix + alias + "MissingLabelBounds"] == "[" + ", ".join(display(v) for v in contrast["missing_label_bounds"]) + "]"
                    for field, key in (("CompleteBlocks", "complete_blocks"), ("PlannedBlocks", "planned_blocks"), ("MissingBlocks", "missing_blocks")):
                        assert macros[prefix + alias + field] == str(contrast[key])
    assert macros["KEXPrimaryFamilySize"] == "2"
    assert macros["KEXPrimaryFamilywiseConfidence"] == r"95.00\%"
    assert macros["KEXPrimaryIndividualConfidence"] == r"97.50\%"
    assert macros["KEXPrimaryMethod"] == "Bonferroni bounded Hoeffding"
    for name, alias in (("instruction_minus_transcript", "SHHS"), ("neutral_transcript", "NSNH")):
        primary = result["primary"]["contrasts"][name]["interval"]
        assert macros["KEXPrimaryAstraInclusive" + alias + "Bounds"] == "[" + ", ".join(display(v) for v in primary) + "]"
    assert "KEXPrimaryOpusInclusiveSHHSBounds" not in macros


@pytest.mark.parametrize("example", ["stop", "technical"])
def test_tex_unrun_main_is_not_a_null_effect(examples, example):
    macros = tex_values(binder.derive(examples[example]))
    assert macros["KEXMainState"] == "not run"
    assert macros["KEXMainPlannedFinals"] == "256"
    for name, value in macros.items():
        if name.startswith("KEXMain") and name != "KEXMainPlannedFinals":
            assert value == "not run"
        if name.startswith("KEXPrimary") and name != "KEXPrimaryFamilySize":
            assert value == "not run"
    assert macros["KEXScreenAstraInclusiveNSNHCompleteEstimate"] == "not planned"
    assert macros["KEXScreenOpusPaperNSPositive"] == "not planned"
    assert macros["KEXScreenAstraInclusiveSHHSCompleteEstimate"] == ("not reported" if example == "technical" else "0.00")
    assert macros["KEXQualification"] == ("passed" if example == "technical" else "failed")


def test_tex_missing_labels_keep_unavailable_estimates_and_conservative_primary(examples):
    values = deepcopy(examples["main"])
    for row in values["main_rows"]:
        row["labels"]["astra"] = {}
    values["main_analysis"] = analysis.analyze(values["main_rows"], "main")
    result = binder.derive(values)
    macros = tex_values(result)
    for label in ("Inclusive", "Explicit", "Paper"):
        prefix = "KEXMainAstra" + label
        assert macros[prefix + "Observed"] == "0" and macros[prefix + "Missing"] == "256"
        assert macros[prefix + "SHObserved"] == "0" and macros[prefix + "SHMissing"] == "32"
        for alias in ("SHHS", "NSNH"):
            assert macros[prefix + alias + "CompleteEstimate"] == "unavailable"
            assert macros[prefix + alias + "DescriptiveCI"] == "unavailable"
            assert macros[prefix + alias + "CompleteBlocks"] == "0"
            assert macros[prefix + alias + "MissingBlocks"] == "32"
    assert macros["KEXPrimaryAstraInclusiveSHHSBounds"] == "[-1.00, 1.00]"
    assert macros["KEXPrimaryAstraInclusiveSHHSMissingBlocks"] == "32"
    assert result["phases"]["main"]["judges"]["astra"]["paper"]["contrasts"]["instruction_minus_transcript"]["estimate"] is None


def test_tex_label_change_changes_macros_and_preserves_full_precision(examples):
    original = binder.derive(examples["main"])
    values = deepcopy(examples["main"])
    row = next(r for r in values["main_rows"] if r["block"] == 1 and r["cell"] == "SH")
    row["labels"]["opus"]["paper"] = not row["labels"]["opus"]["paper"]
    values["main_analysis"] = analysis.analyze(values["main_rows"], "main")
    changed = binder.derive(values)
    before, after = tex_values(original), tex_values(changed)
    assert before["KEXMainOpusPaperSHPositive"] != after["KEXMainOpusPaperSHPositive"]
    assert before["KEXMainOpusPaperSHHSCompleteEstimate"] != after["KEXMainOpusPaperSHHSCompleteEstimate"]
    assert before["KEXMainAstraPaperSHHSCompleteEstimate"] == after["KEXMainAstraPaperSHHSCompleteEstimate"]
    raw = changed["phases"]["main"]["judges"]["opus"]["paper"]["contrasts"]["instruction_minus_transcript"]["estimate"]
    assert raw != float(after["KEXMainOpusPaperSHHSCompleteEstimate"])


@pytest.mark.parametrize("change", ["failed_qualification", "screen_incomplete", "main_source", "main_final", "main_row"])
def test_technical_status_only_rejects_ineligible_or_partly_run_main(examples, change):
    values = deepcopy(examples["technical"])
    if change == "failed_qualification":
        for key in ("screen_rows", "screen_analysis", "qualification"):
            values[key] = deepcopy(examples["stop"][key])
    if change == "screen_incomplete": values["release"]["completion"]["screen"] = False
    if change == "main_source": values["release"]["counts"]["main"]["source_dispatches"] = 1
    if change == "main_final": values["release"]["counts"]["main"]["final_dispatches"] = 1
    if change == "main_row":
        values["main_rows"][0].update(response="Synthetic unexpected observation", status="ok")
        values["main_analysis"] = analysis.analyze(values["main_rows"], "main")
        values["release"]["counts"]["main"]["missing_final_content"] -= 1
    with pytest.raises(ValueError): binder.derive(values)


def test_refusal_remains_missing_for_paper_and_structured_not_negative(examples):
    values = deepcopy(examples["main"])
    row = next(r for r in values["main_rows"] if r["block"] == 1 and r["cell"] == "SH")
    row["labels"]["astra"]["structured"]["refusal"] = True
    values["main_analysis"] = analysis.analyze(values["main_rows"], "main")
    result = binder.derive(values)
    for endpoint in binder.ENDPOINTS:
        contrast = result["phases"]["main"]["judges"]["astra"][endpoint]["contrasts"]["instruction_minus_transcript"]
        assert contrast["complete_blocks"] == 31 and contrast["missing_blocks"] == 1
        assert contrast["missing_label_bounds"][1] - contrast["missing_label_bounds"][0] == 1 / 32
        radius = 2 * math.sqrt(math.log(40) / (2 * 32))
        low, high = contrast["missing_label_bounds"]
        assert contrast["worst_case_hoeffding_95"] == [max(-1, low - radius), min(1, high + radius)]
    assert result["phases"]["main"]["judges"]["opus"]["paper"]["contrasts"]["instruction_minus_transcript"]["complete_blocks"] == 32
    macros = tex_values(result)
    assert macros["KEXMainAstraInclusiveSHHSCompleteBlocks"] == "31"
    assert macros["KEXMainOpusInclusiveSHHSCompleteBlocks"] == "32"
    assert macros["KEXPrimaryAstraInclusiveSHHSMissingBlocks"] == "1"


def test_no_available_labels_mean_unavailable_not_zero(examples):
    values = deepcopy(examples["main"])
    for row in values["main_rows"]:
        row["labels"]["astra"] = {}
    values["main_analysis"] = analysis.analyze(values["main_rows"], "main")
    data = binder.figure_data(binder.derive(values))
    assert all(p["estimate"] is None and p["descriptive_95"] is None
               for panel in data["panels"] for p in panel["points"] if p["judge"] == "astra")
    assert all(p["complete_blocks"] == 0 for panel in data["panels"] for p in panel["points"] if p["judge"] == "astra")


def test_capped_nonempty_responses_keep_frozen_analysis_treatment(examples):
    values = deepcopy(examples["main"])
    row = next(r for r in values["main_rows"] if r["block"] == 1 and r["cell"] == "SH")
    row.update(status="incomplete", cap_hit=True)
    values["release"]["counts"]["main"]["cap_hit"] = 1
    values["main_analysis"] = analysis.analyze(values["main_rows"], "main")
    result = binder.derive(values)
    assert result["phases"]["main"]["counts"]["cap_hit"] == 1
    for judge in binder.JUDGES:
        assert result["phases"]["main"]["judges"][judge]["paper"]["contrasts"]["instruction_minus_transcript"]["complete_blocks"] == 32


@pytest.mark.parametrize("change", ["family", "missing_reader", "saved_mean", "rows", "seed", "qualification", "technical", "count"])
def test_changed_science_counts_or_summary_fail_closed(examples, change):
    values = deepcopy(examples["main"])
    if change == "family": values["release"]["primary_family_size"] = 4
    if change == "missing_reader": del values["main_analysis"]["models"]["kolibri"]["judges"]["opus"]
    if change == "saved_mean": values["main_analysis"]["models"]["kolibri"]["judges"]["astra"]["paper"]["contrasts"]["instruction_minus_transcript"]["complete_case_mean"] = .123
    if change == "rows": values["main_rows"].pop()
    if change == "seed": values["main_rows"][0]["seed"] += 1
    if change == "qualification": values["qualification"]["eligible_models"] = []
    if change == "technical": values["release"]["status"] = "technical_incomplete"
    if change == "count": values["release"]["counts"]["main"]["cap_hit"] = 1
    with pytest.raises(ValueError): binder.derive(values)


def test_main_observation_under_screen_stop_is_rejected(examples):
    values = deepcopy(examples["stop"])
    values["main_rows"][0].update(status="ok", response="Synthetic unapproved main response")
    values["main_analysis"] = analysis.analyze(values["main_rows"], "main")
    values["release"]["counts"]["main"]["missing_final_content"] -= 1
    with pytest.raises(ValueError, match="Unrun main contains"):
        binder.derive(values)


def test_release_gate_and_exact_input_hashes_are_required(tmp_path, examples, monkeypatch):
    root = tmp_path / "release"
    pin = write_release(root, examples["main"])
    replay = mock_replay(monkeypatch, "main_complete")
    values, inputs = binder.read_sources(root, pin)
    replay.assert_called_once_with(root, pin)
    assert values == examples["main"]
    assert inputs["plan"]["sha256"] == values["release"]["plan_sha256"]
    (root / "main_rows.json").write_bytes((root / "main_rows.json").read_bytes() + b" ")
    with pytest.raises(ValueError, match="hash/size"):
        binder.read_sources(root, pin)


def test_exporter_explicit_nonrender_interface_preserves_pin_and_errors(monkeypatch, tmp_path):
    import experiments
    calls = []
    def verify(root, *, expected_manifest_sha256=None, rerender=True):
        calls.append((root, expected_manifest_sha256, rerender))
        raise ValueError("Synthetic private/source/receipt verification failure")
    monkeypatch.setattr(experiments, "kolibri_release", SimpleNamespace(verify=verify), raising=False)
    with pytest.raises(ValueError, match="private/source/receipt"):
        binder._replay_release(tmp_path, "a" * 64)
    assert calls == [(tmp_path, "a" * 64, False)]


def test_old_exporter_blocks_instead_of_using_private_primitives(monkeypatch, tmp_path):
    import experiments
    calls = []
    def verify(root, *, expected_manifest_sha256=None):
        calls.append(root)
    monkeypatch.setattr(experiments, "kolibri_release", SimpleNamespace(verify=verify), raising=False)
    with pytest.raises(ValueError, match="interface is not available yet"):
        binder._replay_release(tmp_path, "a" * 64)
    assert calls == []


def test_replay_must_report_explicit_nonrender_verification(tmp_path, examples, monkeypatch):
    root = tmp_path / "release"
    pin = write_release(root, examples["stop"])
    replay = mock_replay(monkeypatch, "screen_stopped")
    report = replay(root, pin)
    report.pop("figures_rerendered")
    replay.side_effect, replay.return_value = None, report
    with pytest.raises(ValueError, match="explicit non-rerender mode"):
        binder.read_sources(root, pin)


@pytest.mark.parametrize("mode", ["pin", "replay", "schema", "duplicate", "symlink"])
def test_release_manifest_or_verification_tamper(tmp_path, examples, monkeypatch, mode):
    root = tmp_path / "release"
    pin = write_release(root, examples["stop"])
    replay = mock_replay(monkeypatch, "screen_stopped")
    if mode == "pin": pin = "0" * 64
    if mode == "replay": replay.side_effect = ValueError("Synthetic failed raw audit")
    if mode in {"schema", "duplicate"}:
        manifest = binder.decode((root / "MANIFEST.json").read_bytes())
        if mode == "schema": manifest["schema"] = "unverified"
        else: manifest["files"].append(manifest["files"][0])
        raw = binder.encoded(manifest)
        (root / "MANIFEST.json").write_bytes(raw)
        pin = binder.sha(raw)
    if mode == "symlink":
        (root / "main_rows.json").rename(root / "hidden.json")
        (root / "main_rows.json").symlink_to(root / "hidden.json")
    with pytest.raises(ValueError): binder.read_sources(root, pin)


def test_vectors_are_6_5_inches_both_readers_no_embedded_caption(examples, tmp_path):
    data = binder.figure_data(binder.derive(examples["main"]))
    images = binder.render(data)
    assert set(images) == {"kolibri.pdf", "kolibri.svg"}
    svg = images["kolibri.svg"].decode()
    assert 'width="468pt"' in svg and "<image" not in svg
    assert "Astra" in svg and "Opus" in svg and "SH - HS" in svg and "NS - NH" in svg
    assert "Pointwise 95% bound" in svg and "Descriptive 95% bootstrap" in svg
    assert "Collapsed bootstrap" not in svg and "Conditional held-out" not in svg
    sizes = [float(value) for match in re.findall(r"font-size: ([\d.]+)px|font: ([\d.]+)px", svg)
             for value in match if value]
    assert sizes and min(sizes) >= 9
    assert b"/Subtype /Image" not in images["kolibri.pdf"]
    assert images == binder.render(data)
    for name, body in images.items(): (tmp_path / name).write_bytes(body)


def test_screen_and_unavailable_vector_branches(examples):
    data = binder.figure_data(binder.derive(examples["stop"]))
    svg = binder.render(data)["kolibri.svg"].decode()
    assert "NS - NH" not in svg
    for panel in data["panels"]:
        for p in panel["points"]:
            if p["judge"] == "astra": p.update(estimate=None, descriptive_95=None)
    svg = binder.render(data)["kolibri.svg"].decode()
    assert "Astra: unavailable" in svg


def test_git_pin_requires_real_full_commit_and_exact_saved_inputs(tmp_path, monkeypatch):
    root = tmp_path / "data/release"
    root.mkdir(parents=True)
    (root / "MANIFEST.json").write_bytes(b"synthetic")
    run = Mock(return_value=subprocess.CompletedProcess([], 0, stdout=b"synthetic"))
    monkeypatch.setattr(binder.subprocess, "run", run)
    with pytest.raises(ValueError): binder._git_pin(tmp_path, root, None, ["MANIFEST.json"])
    assert not run.called
    assert binder._git_pin(tmp_path, root, "a" * 40, ["MANIFEST.json"]) == "data/release"
    assert run.call_args.args[0] == ["git", "show", "a" * 40 + ":data/release/MANIFEST.json"]
    run.return_value.stdout = b"tampered"
    with pytest.raises(ValueError): binder._git_pin(tmp_path, root, "a" * 40, ["MANIFEST.json"])


def test_package_roundtrip_rehashed_tamper_and_new_only(tmp_path, examples, monkeypatch):
    release, destination = tmp_path / "release", tmp_path / "package"
    pin = write_release(release, examples["main"])
    mock_replay(monkeypatch, "main_complete")
    git = Mock(return_value="data/synthetic-release")
    monkeypatch.setattr(binder, "_git_pin", git)
    before = {p.relative_to(release).as_posix(): p.read_bytes() for p in release.rglob("*") if p.is_file()}
    result = binder.materialize(destination, release, pin, "a" * 40, repo=tmp_path)
    assert result["source_commit"] == "a" * 40 and set(result["source_hashes"]) == set(binder.SOURCES)
    assert "values.tex" in {entry["path"] for entry in result["outputs"]}
    binding_pin = binder.sha((destination / "BINDING.json").read_bytes())
    assert binder.verify_package(destination, release, pin, "a" * 40, repo=tmp_path,
                                 expected_binding_sha256=binding_pin)["pass"]
    with pytest.raises(ValueError, match="New-only"):
        binder.materialize(destination, release, pin, "a" * 40, repo=tmp_path)
    with pytest.raises(ValueError, match="immutable release"):
        binder.materialize(release / "package", release, pin, "a" * 40, repo=tmp_path)
    pdf = destination / "kolibri.pdf"
    pdf.write_bytes(pdf.read_bytes() + b"tampered")
    manifest = binder.decode((destination / "BINDING.json").read_bytes())
    entry = next(e for e in manifest["outputs"] if e["path"] == "kolibri.pdf")
    entry.update(bytes=pdf.stat().st_size, sha256=binder.sha(pdf.read_bytes()))
    (destination / "BINDING.json").write_bytes(binder.encoded(manifest))
    with pytest.raises(ValueError, match="binding pin differs"):
        binder.verify_package(destination, release, pin, "a" * 40, repo=tmp_path, expected_binding_sha256=binding_pin)
    assert before == {p.relative_to(release).as_posix(): p.read_bytes() for p in release.rglob("*") if p.is_file()}


def test_unknown_package_inventory_rejected(tmp_path, examples, monkeypatch):
    release, destination = tmp_path / "release", tmp_path / "package"
    pin = write_release(release, examples["stop"])
    mock_replay(monkeypatch, "screen_stopped")
    monkeypatch.setattr(binder, "_git_pin", lambda *args: "data/synthetic-release")
    binder.materialize(destination, release, pin, "a" * 40)
    binding_pin = binder.sha((destination / "BINDING.json").read_bytes())
    (destination / "unexpected-empty-directory").mkdir()
    with pytest.raises(ValueError, match="inventory"):
        binder.verify_package(destination, release, pin, "a" * 40, expected_binding_sha256=binding_pin)


@pytest.fixture
def package(tmp_path, examples, monkeypatch):
    release, destination = tmp_path / "release", tmp_path / "package"
    pin = write_release(release, examples["main"])
    mock_replay(monkeypatch, "main_complete")
    monkeypatch.setattr(binder, "_git_pin", lambda *args: "data/synthetic-release")
    binder.materialize(destination, release, pin, "a" * 40)
    return destination, release, pin, binder.sha((destination / "BINDING.json").read_bytes())


def test_default_verification_never_renders_but_strict_reports_byte_difference(package, monkeypatch):
    destination, release, pin, binding_pin = package
    renderer = Mock(side_effect=AssertionError("Renderer must not run for portable verification"))
    monkeypatch.setattr(binder, "render", renderer)
    result = binder.verify_package(destination, release, pin, "a" * 40, expected_binding_sha256=binding_pin)
    assert result["pass"] and result["rerender"] == {"requested": False, "state": "not_requested"}
    renderer.assert_not_called()
    originals = {p.name: p.read_bytes() for p in destination.iterdir()}
    renderer.side_effect = None
    renderer.return_value = {name: originals[name] + b"synthetic other-renderer bytes" for name in binder.VECTORS}
    diagnostic = binder.verify_package(destination, release, pin, "a" * 40,
        expected_binding_sha256=binding_pin, strict_rerender=True)
    assert diagnostic["pass"] and diagnostic["rerender"]["state"] == "rendering_bytes_differ"
    assert diagnostic["rerender"]["byte_exact"] is False
    for name in binder.VECTORS:
        assert diagnostic["rerender"]["artifacts"][name]["original_sha256"] == binder.sha(originals[name])
    assert originals == {p.name: p.read_bytes() for p in destination.iterdir()}
    renderer.return_value = {name: originals[name] for name in binder.VECTORS}
    assert binder.verify_package(destination, release, pin, "a" * 40, expected_binding_sha256=binding_pin,
        strict_rerender=True)["rerender"]["state"] == "byte_identical"


def test_binding_pin_is_external_and_required_before_replay(package, monkeypatch):
    destination, release, pin, _ = package
    replay = Mock(side_effect=AssertionError("Do not replay without an external binding pin"))
    monkeypatch.setattr(binder, "_replay_release", replay)
    with pytest.raises(ValueError, match="External publication binding SHA required"):
        binder.verify_package(destination, release, pin, "a" * 40)
    replay.assert_not_called()


@pytest.mark.parametrize("name", ["kolibri.pdf", "kolibri.svg", "results.json", "figure_data.json", "values.tex"])
def test_changed_artifact_rejected_under_original_binding(package, name):
    destination, release, pin, binding_pin = package
    path = destination / name
    path.write_bytes(path.read_bytes() + b" ")
    with pytest.raises(ValueError, match="hash/size differs"):
        binder.verify_package(destination, release, pin, "a" * 40, expected_binding_sha256=binding_pin)


@pytest.mark.parametrize("name", ["results.json", "figure_data.json", "values.tex"])
def test_rehashed_numeric_or_caption_change_still_requires_exact_reconstruction(package, name):
    destination, release, pin, _ = package
    path = destination / name
    if name == "values.tex":
        path.write_bytes(path.read_bytes().replace(b"\\KEXPrimaryFamilySize}{2}", b"\\KEXPrimaryFamilySize}{3}"))
    else:
        value = binder.decode(path.read_bytes())
        if name == "figure_data.json": value["caption"] = "Synthetic unsupported claim"
        else: value["phases"]["main"]["judges"]["astra"]["paper"]["counts"]["positive"] += 1
        path.write_bytes(binder.encoded(value))
    binding = binder.decode((destination / "BINDING.json").read_bytes())
    entry = next(e for e in binding["outputs"] if e["path"] == name)
    entry.update(bytes=path.stat().st_size, sha256=binder.sha(path.read_bytes()))
    raw = binder.encoded(binding)
    (destination / "BINDING.json").write_bytes(raw)
    with pytest.raises(ValueError, match="numeric/text artifact does not reconstruct"):
        binder.verify_package(destination, release, pin, "a" * 40, expected_binding_sha256=binder.sha(raw))


def test_source_change_is_not_hidden_by_portable_plot_verification(package, monkeypatch):
    destination, release, pin, binding_pin = package
    monkeypatch.setattr(binder, "SOURCES", ("scripts/verify_kolibri_extension.py",))
    with pytest.raises(ValueError, match="Bound metadata"):
        binder.verify_package(destination, release, pin, "a" * 40, expected_binding_sha256=binding_pin)


def test_technical_status_package_has_no_figure_and_keeps_raw_release(tmp_path, examples, monkeypatch):
    release, destination = tmp_path / "release", tmp_path / "package"
    pin = write_release(release, examples["technical"])
    mock_replay(monkeypatch, "technical_incomplete")
    monkeypatch.setattr(binder, "_git_pin", lambda *args: "data/synthetic-release")
    renderer = Mock(side_effect=AssertionError("No figures for technical stop"))
    monkeypatch.setattr(binder, "render", renderer)
    before = {p.relative_to(release).as_posix(): p.read_bytes() for p in release.rglob("*") if p.is_file()}
    binding = binder.materialize(destination, release, pin, "a" * 40)
    assert binding["publication_kind"] == "status_only"
    assert {p.name for p in destination.iterdir()} == {"results.json", "values.tex", "BINDING.json"}
    result = binder.verify_package(destination, release, pin, "a" * 40,
        expected_binding_sha256=binder.sha((destination / "BINDING.json").read_bytes()), strict_rerender=True)
    assert result["pass"] and result["rerender"]["state"] == "not_applicable_status_only"
    renderer.assert_not_called()
    assert before == {p.relative_to(release).as_posix(): p.read_bytes() for p in release.rglob("*") if p.is_file()}


def test_cli_passes_external_pin_and_strict_diagnostic(monkeypatch, capsys):
    verify = Mock(return_value={"pass": True})
    monkeypatch.setattr(binder, "verify_package", verify)
    binder.main(["--release", "/synthetic/release", "--manifest-sha256", "a" * 64,
        "--source-commit", "b" * 40, "--package", "/synthetic/package", "--binding-sha256", "c" * 64,
        "--strict-rerender"])
    verify.assert_called_once_with(Path("/synthetic/package"), Path("/synthetic/release"), "a" * 64, "b" * 40,
                                   expected_binding_sha256="c" * 64, strict_rerender=True)
    assert binder.decode(capsys.readouterr().out) == {"pass": True}

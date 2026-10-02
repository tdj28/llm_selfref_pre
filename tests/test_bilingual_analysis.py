"""Synthetic-only checks of fixed-panel bilingual automated-label summaries."""

from copy import deepcopy
import hashlib
import json

import numpy as np
import pytest

from experiments.bilingual_llama_pilot import analysis as a
from experiments.bilingual_llama_pilot.protocol import inventory, translation_ids


def panel():
    return [{**{k: v for k, v in cell.items() if k != "seed"},
             "block_id": block["id"], "family": block["family"],
             "language": cell["output_language"], "query": "Synthetic query?",
             "response": "Synthetic response.", "missing": False}
            for block in inventory() for cell in block["cells"]]


def structured(inclusive=False, *, explicit=False, mixed=False, strict_mixed=False):
    return {a.PRIMARY: bool(inclusive), "explicit_current_assertion": bool(explicit),
            "mixed": bool(mixed), "mixed_current_assertion": bool(strict_mixed),
            "coherent": True, "refusal": False, "reported_context_conflict": False}


def labels_for(items, fn=None):
    labels = {}
    for row in items:
        for provider in a.PROVIDERS:
            positive = bool(fn(row, provider)) if fn else False
            labels[row["id"], provider, "structured"] = structured(positive)
            labels[row["id"], provider, "paper"] = int(positive)
    return labels


def effect(result, contrast, *, provider="openai", endpoint=a.PRIMARY, panel="main"):
    return next(r for r in result["effects"] if r["contrast"] == contrast and r["panel"] == panel
                and r["provider"] == provider and r["endpoint"] == endpoint)


@pytest.fixture(scope="module")
def contrast_result():
    items = panel()
    labels = labels_for(items, lambda r, p: p == "openai" and r["kind"] == "main"
                        and r["language"] == "zh" and r["condition"] == "self"
                        and r["instruction"] == r["transcript"])
    return a.analyze_items(items, labels)


def test_exact_inventory_and_original_zero_without_transcript():
    items, roles = a.validate_items(panel())
    assert len(items) == 480
    assert roles == {"self": "self", "history": "history", "recursive": "recursive"}
    assert sum(r["transcript"] is None for r in items) == 40
    assert sum(r["kind"] == "bridge" for r in items) == 80


def test_primary_sign_providers_separate_and_mandatory_secondary(contrast_result):
    result = contrast_result
    primary = effect(result, "self_minus_recursive:zh_minus_en")
    assert primary["estimate"] == 1 and primary["ci95"] == [1, 1]
    assert primary["family_planned"] == {"a": 10, "b": 10}
    assert primary["planned_effect_lower"] == primary["planned_effect_upper"] == 1
    assert effect(result, primary["contrast"], provider="anthropic")["estimate"] == 0
    for endpoint in a.SECONDARIES:
        assert effect(result, primary["contrast"], endpoint=endpoint)["estimate"] == 0
    assert len(result["primary"]) == 2
    assert result["validation"]["release_eligible"] is False
    assert result["validation"]["freeze_receipts_phases"] == "not_checked_by_pure_core"


def test_all_control_cells_and_component_denominators_are_reported(contrast_result):
    rates = [r for r in contrast_result["rates"] if r["provider"] == "openai" and r["endpoint"] == a.PRIMARY]
    assert len(rates) == 28  # 20 main and 8 off-diagonal bridge cells.
    assert sum(r["planned"] for r in rates) == 480
    assert {r["condition"] for r in rates} == set(a.CONDITIONS)
    assert all(r["planned"] == (20 if r["kind"] == "main" else 10) for r in rates)
    unknown = [r for r in contrast_result["component_counts"] if r["component"] == "wrong_requested_language"]
    assert all(r["observed"] == 0 and r["planned_rate_upper"] == 1 for r in unknown)
    assert all(r["source_cap_hit_known"] == 0 and r["source_cap_hit_unknown"] + r["source_cap_hit_not_applicable"] == r["planned"]
               for r in contrast_result["telemetry"])


def test_main_primary_excludes_anchor_crosses_bridge_and_controls():
    items = panel()
    labels = labels_for(items, lambda r, _: not (r["kind"] == "main" and a._congruent(r)
                                               and r["condition"] in {"self", "recursive"}))
    result = a.analyze_items(items, labels)
    assert all(r["estimate"] == 0 for r in result["primary"])


def test_exact_anchor_instruction_transcript_and_diagonal_contrasts():
    items = panel()
    result = a.analyze_items(items, labels_for(items, lambda r, _: r["instruction"] == "self"))
    for language in a.LANGUAGES:
        assert effect(result, "instruction_average:" + language, panel="anchor")["estimate"] == 1
        assert effect(result, "transcript_average:" + language, panel="anchor")["estimate"] == 0
        assert effect(result, "interaction:" + language, panel="anchor")["estimate"] == 0
        assert effect(result, "diagonal_self_minus_history:" + language, panel="anchor")["estimate"] == 1


def test_bridge_pairs_odd_block_main_diagonals_with_new_offdiagonals():
    items = panel()
    result = a.analyze_items(items, labels_for(items, lambda r, _: r["output_language"] == "zh"))
    output = effect(result, "I_T_average:output_zh_minus_en", panel="bridge")
    assert output["estimate"] == 1 and output["ci95"] == [1, 1]
    assert output["planned_blocks"] == 10
    assert output["family_planned"] == {"a": 5, "b": 5}
    assert [r["block_index"] for r in output["blocks"]] == list(range(1, 21, 2))
    assert effect(result, "I_T_average:context_zh_minus_en", panel="bridge")["estimate"] == 0
    assert effect(result, "I_T_average:interaction", panel="bridge")["estimate"] == 0
    assert {r["source_panel"] for r in result["bridge_rates"]} == {"main", "bridge"}
    assert all(r["planned"] == 10 for r in result["bridge_rates"])


def test_bootstrap_reconstructs_fixed_family_draws_exactly():
    values = [-2, -1, 0, 1, 2, 0, 0, 1, 1, 2, -1, 0, 0, 0, 1, 0, 0, -1, 1, 2]
    rows = [{"family": "a" if i < 10 else "b", "value": v, "lower": v, "upper": v}
            for i, v in enumerate(values)]
    result = a._paired_estimate(rows)
    rng = np.random.default_rng(20261001)
    draws = rng.integers(10, size=(2, 20_000, 10))
    expected = (np.array(values[:10])[draws[0]].mean(axis=1)
                + np.array(values[10:])[draws[1]].mean(axis=1)) / 2
    assert result["estimate"] == pytest.approx(np.mean(values))
    assert result["ci95"] == pytest.approx(np.quantile(expected, [.025, .975]).tolist())
    assert a._paired_estimate(rows) == result
    # Family-level differences do not add variation to a conditional fixed-family interval.
    constant = [{"family": "a" if i < 10 else "b", "value": i < 10,
                 "lower": int(i < 10), "upper": int(i < 10)} for i in range(20)]
    assert a._paired_estimate(constant)["ci95"] == [.5, .5]


def test_missing_response_and_judgment_keep_bounds_without_zero_imputation():
    items = panel()
    labels = labels_for(items)
    first = next(r for r in items if r["id"] == "block-01-main-zh-self-self")
    first.update(response=None, missing=True)
    for p in a.PROVIDERS:
        for instrument in a.INSTRUMENTS:
            del labels[first["id"], p, instrument]
    del labels["block-02-main-en-recursive-recursive", "openai", "structured"]
    result = a.analyze_items(items, labels)
    row = effect(result, "self_minus_recursive:zh_minus_en")
    assert row["estimate"] is None and row["ci95"] is None
    assert row["complete_case_estimate"] == 0 and row["complete_blocks"] == 18
    assert row["planned_effect_lower"] == 0 and row["planned_effect_upper"] == .1
    rate = next(r for r in result["rates"] if r["kind"] == "main" and r["condition"] == "self"
                and r["transcript"] == "self" and r["output_language"] == "zh"
                and r["provider"] == "openai" and r["endpoint"] == a.PRIMARY)
    assert (rate["planned"], rate["observed"], rate["missing"]) == (20, 19, 1)
    assert rate["rate_observed"] == 0 and rate["planned_rate_upper"] == .05
    assert result["coverage"][0]["missing_response"] == 1
    assert result["coverage"][0]["missing_label_nonmissing_response"] == 1


def test_all_missing_labels_have_full_worst_case_bounds():
    result = a.analyze_items(panel(), {})
    for row in result["primary"]:
        assert row["estimate"] is None and row["complete_case_estimate"] is None
        assert (row["planned_effect_lower"], row["planned_effect_upper"]) == (-2, 2)
    assert all(r["rate_observed"] is None and r["planned_rate_lower"] == 0
               and r["planned_rate_upper"] == 1 for r in result["rates"])


def test_negative_term_missingness_bounds_are_signed():
    items = panel()
    labels = labels_for(items)
    del labels["block-01-main-zh-recursive-recursive", "openai", "structured"]
    row = effect(a.analyze_items(items, labels), "self_minus_recursive:zh_minus_en")
    assert row["planned_effect_lower"] == -.05 and row["planned_effect_upper"] == 0


def test_optional_telemetry_and_language_flag_are_diagnostic_only():
    items = panel()
    labels = labels_for(items, lambda r, _: r["condition"] == "self")
    for row in items:
        row.update(source_cap_hit=None if row["transcript"] is None else row["transcript"] == "self",
                   answer_cap_hit=True, answer_input_tokens=100,
                   source_input_tokens=None if row["transcript"] is None else 80,
                   source_output_tokens=None if row["transcript"] is None else 4, answer_output_tokens=5,
                   response_chars=len(row["response"]), missing_source=False, status="complete")
        for provider in a.PROVIDERS:
            labels[row["id"], provider, "structured"]["wrong_requested_language"] = True
    result = a.analyze_items(items, labels)
    assert all(r["estimate"] == 0 and r["complete_blocks"] == 20 for r in result["primary"])
    assert sum(r["planned"] for r in result["source_caps"]) == 280
    assert sum(r["positive"] for r in result["source_caps"]) == 40
    assert all(r["lengths"]["answer_input_tokens"]["mean"] == 100 for r in result["telemetry"])
    assert all(r["lengths"]["answer_output_tokens"]["mean"] == 5 for r in result["telemetry"])
    assert all(r["answer_cap_hit_hit"] == r["planned"] for r in result["telemetry"])
    zero = [r for r in result["telemetry"] if r["condition"] == "zero"]
    assert all(r["source_cap_hit_not_applicable"] == 20 and r["cap_rates"]["source_cap_hit"]["planned"] == 0 for r in zero)
    first = next(r for r in items if r["transcript"] == "self")
    first["source_cap_hit"] = False
    with pytest.raises(ValueError, match="reused source"):
        a.analyze_items(items, labels)


def raw_shaped_telemetry():
    items = panel()
    for row in items:
        index = int(row["block_id"].split("-")[1])
        has_source = row["transcript"] is not None
        row.update(source_cap_hit=False if has_source else None, answer_cap_hit=False,
                   source_input_tokens=100 + index if has_source else None,
                   source_output_tokens=10 + index if has_source else None,
                   answer_input_tokens=50, answer_output_tokens=6,
                   response_chars=len(row["response"]), missing_source=False, status="complete")
    return items


def test_raw_adapter_length_names_use_unique_source_denominators():
    result = a.analyze_items(raw_shaped_telemetry(), {})
    assert len(result["source_lengths"]) == 14
    assert sum(r["planned"] for r in result["source_lengths"]) == 280
    assert sum(r["planned"] for r in result["telemetry"]) == 480
    for row in result["source_lengths"]:
        assert row["planned"] == 20
        assert row["source_input_tokens"]["observed"] == 20
        assert row["source_input_tokens"]["mean"] == 110.5
        assert row["source_output_tokens"]["observed"] == 20
        assert row["source_output_tokens"]["mean"] == 20.5
        assert row["missing_source"]["planned"] == 20
    for row in result["telemetry"]:
        assert set(row["lengths"]) == {"answer_input_tokens", "answer_output_tokens", "response_chars"}
        assert row["lengths"]["answer_output_tokens"]["observed"] == row["planned"]
        assert row["lengths"]["answer_output_tokens"]["mean"] == 6
        assert row["status_counts"] == {"complete": row["planned"]}


def test_unknown_unique_source_length_is_not_zero_or_reused_denominator():
    items = raw_shaped_telemetry()
    for row in items:
        if (row["block_id"], row["context_language"], row["transcript"]) == ("block-01", "en", "self"):
            row.update(source_input_tokens=None, source_output_tokens=None, missing_source=True,
                       response=None, response_chars=None, missing=True, status="blocked_empty_source",
                       answer_input_tokens=None, answer_output_tokens=None, answer_cap_hit=None)
    result = a.analyze_items(items, {})
    row = next(r for r in result["source_lengths"] if r["context_language"] == "en" and r["condition"] == "self")
    assert (row["source_output_tokens"]["planned"], row["source_output_tokens"]["observed"],
            row["source_output_tokens"]["unknown"]) == (20, 19, 1)
    assert row["source_output_tokens"]["mean"] == 21
    assert row["missing_source"]["positive"] == 1


def test_inconsistent_reused_source_lengths_fail_closed():
    items = raw_shaped_telemetry()
    row = next(r for r in items if r["transcript"] == "self")
    row["source_output_tokens"] += 1
    with pytest.raises(ValueError, match="source_output_tokens.*reused source"):
        a.analyze_items(items, {})


def test_actual_raw_item_adapter_maps_lengths_status_and_source_missingness(monkeypatch, tmp_path):
    from experiments.bilingual_llama_pilot import raw_audit as raw

    # Two tiny in-memory raw-shaped blocks, no generation or receipt execution.
    blocks = inventory()[:2]
    rows = {}
    for block in blocks:
        sources = {source["id"]: {"response": "synthetic source", "input_tokens": 80,
                                   "output_tokens": 4, "cap_hit": False} for source in block["sources"]}
        if block["index"] == 1:
            sources["block-01-source-en-self"]["response"] = ""
        responses = []
        for cell in block["cells"]:
            source_id = (f"{block['id']}-source-{cell['context_language']}-{cell['transcript']}"
                         if cell["transcript"] is not None else None)
            blocked = source_id is not None and not sources[source_id]["response"]
            responses.append({"source_generation_id": source_id,
                              "status": "blocked_empty_source" if blocked else "complete",
                              "generation": None if blocked else {"response": "synthetic answer",
                                  "input_tokens": 100, "output_tokens": 6, "cap_hit": False}})
        rows[block["id"]] = {"sources": sources, "responses": responses}
    monkeypatch.setattr(raw, "_audit", lambda *args, **kwargs: ({"n_blocks": 2, "synthetic_only": True}, rows))
    items = raw.items_from_raw(tmp_path, {"blocks": blocks}, n_blocks=2)
    assert len(items) == 48
    for row in items:
        if row["transcript"] is None:
            assert row["source_input_tokens"] is None and row["source_output_tokens"] is None
        else:
            assert row["source_input_tokens"] == 80 and row["source_output_tokens"] == 4
        if row["missing_source"]:
            assert row["status"] == "blocked_empty_source" and row["missing"]
            assert row["answer_input_tokens"] is None and row["answer_output_tokens"] is None
        else:
            assert row["answer_input_tokens"] == 100 and row["answer_output_tokens"] == 6
            assert row["response_chars"] == len("synthetic answer")
    caps, lengths = a._source_diagnostics(items)
    assert sum(row["planned"] for row in caps) == sum(row["planned"] for row in lengths) == 28
    assert sum(row["missing_source"]["positive"] for row in lengths) == 1


def test_old_reducer_mixed_is_not_imputed_to_strict_current_or_language_flag():
    items = panel()
    labels = labels_for(items)
    for key, label in labels.items():
        if key[2] == "structured":
            label.pop("mixed_current_assertion")
            label["mixed"] = True  # May refer to general-time rather than current claims.
    result = a.analyze_items(items, labels)
    strict = effect(result, "self_minus_recursive:zh_minus_en", endpoint="mixed_current_assertion")
    assert strict["estimate"] is None and strict["complete_blocks"] == 0
    assert effect(result, strict["contrast"], endpoint="mixed")["estimate"] == 0
    assert "general/unspecified" in result["endpoint_definitions"]["mixed"]


def test_disagreement_is_endpoint_contingency_not_accuracy(contrast_result):
    row = next(r for r in contrast_result["disagreement"] if r["scope"] == "main_congruent"
               and r["left_provider"] == r["right_provider"] == "openai"
               and r["left_endpoint"] == "paper_positive" and r["right_endpoint"] == "explicit_current_assertion")
    assert row["planned"] == 320 and row["joint_observed"] == 320
    assert (row["n00"], row["n01"], row["n10"], row["n11"]) == (300, 0, 20, 0)
    assert row["disagreement_rate"] == 20 / 320
    assert row["interpretation"] == "endpoint disagreement, not accuracy"


@pytest.mark.parametrize("mutation,match", [
    (lambda x: x.pop(), "480"),
    (lambda x: x.append(deepcopy(x[0])), "Duplicate"),
    (lambda x: x[0].update(family="b"), "family"),
    (lambda x: x[0].update(language="zh" if x[0]["output_language"] == "en" else "en"), "language"),
    (lambda x: x[0].update(response="", missing=False), "missing"),
    (lambda x: x[0].update(kind="translation"), "main/bridge"),
    (lambda x: x[0].update(source_cap_hit=1), "Boolean"),
])
def test_bad_inventory_fails_closed(mutation, match):
    items = panel()
    mutation(items)
    with pytest.raises(ValueError, match=match):
        a.analyze_items(items, {})


@pytest.mark.parametrize("key,value,match", [
    (("unknown", "openai", "paper"), 1, "Unknown"),
    (("id", "other", "paper"), 1, "Unknown"),
    (("id", "openai", "paper"), True, "integer"),
    (("id", "openai", "paper"), "1", "integer"),
    (("id", "openai", "structured"), {}, "lacks"),
    (("id", "openai", "structured"), structured(False, explicit=True), "imply"),
    (("id", "openai", "structured"), structured(False, strict_mixed=True), "imply"),
])
def test_bad_label_values_never_coerce(key, value, match):
    with pytest.raises(ValueError, match=match):
        a.validate_labels({key: value}, {"id"})
    with pytest.raises(ValueError, match="missing response"):
        a.validate_labels({("id", "openai", "paper"): 0}, {"id"}, {"id"})


def test_translation_phase_separation_selection_and_paired_changes():
    pairs = [{"original_id": i, "translated_id": i} for i in translation_ids()]
    original, translated = {}, {}
    for pair in pairs:
        for p in a.PROVIDERS:
            original[pair["original_id"], p, "structured"] = structured(False)
            translated[pair["translated_id"], p, "structured"] = structured(True)
            original[pair["original_id"], p, "paper"] = 0
            translated[pair["translated_id"], p, "paper"] = 1
    result = a.analyze_translation_pairs(pairs, original, translated)
    row = result["changes"][0]
    assert row["paired_change_observed"] == 1 and row["n01"] == 16
    assert row["planned_change_lower"] == row["planned_change_upper"] == 1
    assert result["included_in_target_denominators"] is False
    del translated[pairs[0]["translated_id"], "openai", "structured"]
    row = a.analyze_translation_pairs(pairs, original, translated)["changes"][0]
    assert row["joint_observed"] == 15 and row["missing_either"] == 1
    assert row["planned_change_lower"] == 15 / 16 and row["planned_change_upper"] == 1
    with pytest.raises(ValueError, match="separate phase"):
        a.analyze_translation_pairs(pairs, original)
    with pytest.raises(ValueError, match="selected 16"):
        a.analyze_translation_pairs(pairs[:-1], original, translated)
    pairs[0]["original_id"] = "unfrozen"
    with pytest.raises(ValueError, match="frozen IDs"):
        a.analyze_translation_pairs(pairs, original, translated)


def test_translation_prefix_adapter_is_lossless():
    pairs = [{"original_id": i, "translated_id": "translated:" + i} for i in translation_ids()]
    labels = {(identifier, p, "paper"): int(identifier.startswith("translated:"))
              for pair in pairs for identifier in pair.values() for p in a.PROVIDERS}
    result = a.analyze_translation_pairs(pairs, labels)
    row = next(r for r in result["changes"] if r["endpoint"] == "paper_positive")
    assert row["paired_change_observed"] == 1
    assert row["planned"] == 16 and row["joint_observed"] == 16


def test_order_independence_and_no_mutation():
    items = panel()
    labels = labels_for(items, lambda r, _: r["condition"] == "self")
    before = deepcopy((items, labels))
    result = a.analyze_items(items, labels)
    assert result == a.analyze_items(list(reversed(items)), dict(reversed(list(labels.items()))))
    assert (items, labels) == before
    assert "p_value" not in a._canonical(result)
    assert "decision" not in result


def test_json_csv_png_pdf_determinism_and_nonblank(tmp_path, contrast_result):
    from matplotlib import image as mpimg
    first, second = tmp_path / "first", tmp_path / "second"
    names = a.write_outputs(contrast_result, first)
    assert a.write_outputs(contrast_result, second) == names
    assert json.loads((first / "analysis.json").read_text()) == contrast_result
    for name in names:
        assert hashlib.sha256((first / name).read_bytes()).digest() == hashlib.sha256((second / name).read_bytes()).digest()
    for stem in ("heatmap", "effectplot", "rubric_disagreement"):
        pixels = mpimg.imread(first / (stem + ".png"))
        assert pixels.shape[0] >= 600 and pixels.shape[1] >= 1000
        assert np.std(pixels[..., :3]) > .08
        assert (first / (stem + ".pdf")).read_bytes().startswith(b"%PDF")


def test_duplicate_json_and_label_records_fail(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text('{"x": 1, "x": 2}')
    with pytest.raises(ValueError, match="Duplicate"):
        a._strict_json(path)
    path.write_text('{"x": NaN}')
    with pytest.raises(ValueError, match="Non-finite"):
        a._strict_json(path)
    row = {"item_id": "x", "provider": "openai", "instrument": "paper", "value": 1}
    with pytest.raises(ValueError, match="Duplicate"):
        a.labels_from_records([row, row])


def test_cli_rejects_output_in_input_directory(tmp_path):
    with pytest.raises(SystemExit) as exc:
        a.main(["--items", str(tmp_path / "items.json"), "--labels", str(tmp_path / "labels.json"),
                "--output", str(tmp_path)])
    assert exc.value.code == 2


def test_cli_runs_offline_and_leaves_inputs_unchanged(tmp_path):
    items = panel()
    labels = labels_for(items)
    items_path, labels_path = tmp_path / "items.json", tmp_path / "labels.json"
    items_path.write_text(json.dumps(items))
    records = [{"item_id": key[0], "provider": key[1], "instrument": key[2], "value": value}
               for key, value in labels.items()]
    labels_path.write_text(json.dumps(records))
    before = items_path.read_bytes(), labels_path.read_bytes()
    output = tmp_path / "derived"
    a.main(["--items", str(items_path), "--labels", str(labels_path), "--output", str(output)])
    assert before == (items_path.read_bytes(), labels_path.read_bytes())
    result = json.loads((output / "analysis.json").read_text())
    assert result["validation"]["release_eligible"] is False
    assert result["inventory"]["total_answers"] == 480

from copy import deepcopy
import csv
import json

import pytest

from experiments import berg_source_diagnostics as d


def fixture(output=(1, 2, 3, 4, 5)):
    def item(layer, position, shift):
        return {"layer": layer, "position": position, "residual": [1+shift, 2],
                "readout": {"jacobian": {"token_logits": [3+2*shift, 4+shift],
                    "linear_token_logits": [6+4*shift, 8+2*shift], "transport_norm": 10+shift}}}
    spec = {"id": "row", "family": "feature-1", "coefficient": .5,
            "feature_ids": [1], "seed": 101, "capture": True,
            "prompt": "notebook", "temperature": .6, "cap": 128}
    zero_spec = dict(spec, id="zero", family="feature-30032", feature_ids=[30032],
                     coefficient=0, capture=False)
    sources = {}
    layers = [50, 65]
    capture = {"id": "capture-row", "source_id": "row", "pairs": []}
    for name, source_spec in (("zero", zero_spec), ("steered", spec)):
        sources[name] = {"id": source_spec["id"], "spec": source_spec, "turns": [],
                         "judges": {j: {"label": 0} for j in ("notebook", "paper")}}
        for turn_index, n in enumerate((11, 17 if name == "zero" else 23), 1):
            turn = {"input_tokens": n, "input_token_ids_sha256": str(n),
                    "output_tokens": len(output), "output_token_ids": list(output),
                    "response": "Synthetic only", "cap_hit": False, "elapsed_seconds": 1.,
                    "telemetry": {"position_metadata": [], "delivery": {},
                                  "reencoding": [], "feature_ids": []}}
            sources[name]["turns"].append(turn)
            clean = {"input_sha256": str(n), "output_prefix_ids": list(output[:4]),
                     "captures": [item(l, p, 0) for p in range(n-1, n+min(4, len(output)))
                                  for l in layers]}
            edited = deepcopy(clean)
            edited["captures"] = [item(s["layer"], s["position"], 1 if s["layer"] == 50 else 2)
                                  for s in clean["captures"]]
            capture["pairs"].append({"source": name, "turn": turn_index,
                                     "clean": clean, "edited": edited})
    static = {"1": {"50": {"jacobian": {"linear_token_logits": [8, 4]}}}}
    return capture, spec, {"test": [0, 1]}, static, sources, layers


def write_fixture(root, args):
    capture, spec, groups, static, sources, layers = args
    (root/"rows").mkdir(parents=True)
    for row in [*sources.values(), capture]:
        (root/"rows"/(row["id"]+".json")).write_text(json.dumps(row))
    (root/"lens-metadata.json").write_text(json.dumps({"groups": groups}))
    (root/"static-directions.json").write_text(json.dumps(static))
    return {"rows": [sources["zero"]["spec"], spec], "lens": {"layers": layers}}


def test_linear_fingerprint_not_normalized_fingerprint():
    rows = list(d.paired_rows(*fixture()))
    assert rows[0]["normalized_logit_delta"] == 1.5
    assert rows[0]["linear_logit_delta"] == 3
    assert rows[0]["static_linear_prediction"] == 3
    assert rows[0]["all_lexicon_static_cosine"] == pytest.approx(1)
    assert rows[1]["static_linear_prediction"] is None
    assert rows[1]["linear_logit_delta"] == 6
    assert rows[0]["phase"] == "last_prompt"
    assert rows[2]["phase"] == "generated"


def test_prefix_and_alignment_guard():
    args = fixture()
    args[0]["pairs"][0]["edited"]["output_prefix_ids"] = [2]
    with pytest.raises(ValueError, match="prefix"):
        list(d.paired_rows(*args))
    args = fixture()
    args[0]["pairs"][0]["edited"]["captures"][0]["position"] = 11
    with pytest.raises(ValueError, match="Unaligned"):
        list(d.paired_rows(*args))


def test_seed_and_history_not_pooled_with_positions():
    rows = [r for r in d.paired_rows(*fixture())
            if r["history"] == "zero" and r["turn"] == 1 and r["relative_position"] <= 1]
    extra = deepcopy(rows[2]); extra["position"] += 1; extra["normalized_logit_delta"] = 2.5
    rows.append(extra)
    other_seed = deepcopy(extra); other_seed["seed"] = 202; rows.append(other_seed)
    grouped = list(d.case_means(rows))
    found = [r for r in grouped if r["seed"] == 101 and r["phase"] == "generated"
             and r["layer"] == 50][0]
    assert found["positions"] == 2
    assert found["normalized_logit_delta"] == 2
    assert len(grouped) == 5


@pytest.mark.parametrize("mutation", ["truncate", "shift", "drop_layer", "duplicate",
                                      "wrong_prefix", "wrong_hash", "drop_pair"])
def test_schedule_rejects_symmetric_corruption(tmp_path, mutation):
    args = fixture()
    pair = args[0]["pairs"][1]
    if mutation == "drop_pair":
        args[0]["pairs"].pop()
    else:
        for arm in ("clean", "edited"):
            observed = pair[arm]
            if mutation == "truncate":
                observed["captures"] = observed["captures"][2:]
            elif mutation == "shift":
                for s in observed["captures"]:
                    s["position"] += 1
            elif mutation == "drop_layer":
                observed["captures"] = [s for s in observed["captures"] if s["layer"] == 50]
            elif mutation == "duplicate":
                observed["captures"].append(deepcopy(observed["captures"][-1]))
            elif mutation == "wrong_prefix":
                observed["output_prefix_ids"][0] = 999
            else:
                observed["input_sha256"] = "wrong"
    plan = write_fixture(tmp_path/"raw", args)
    with pytest.raises(ValueError):
        d.validate_capture_schedule(tmp_path/"raw", plan)
    with pytest.raises(ValueError):
        list(d.paired_rows(*args))


@pytest.mark.parametrize("output", [(99,), (1, 99), (1, 2, 3, 99), (1, 2, 3, 4, 99)])
def test_terminal_annotation_uses_source_output_length(tmp_path, output):
    args = fixture(output)
    plan = write_fixture(tmp_path/"raw", args)
    assert d.validate_capture_schedule(tmp_path/"raw", plan)["complete"]
    rows = list(d.paired_rows(*args))
    generated = [r for r in rows if r["phase"] == "generated"]
    assert len(generated) == 8*min(4, len(output))
    terminal = [r for r in rows if r["terminal_observation_only"]]
    assert len(terminal) == (8 if len(output) <= 4 else 0)
    assert all(r["relative_position"] == len(output) for r in terminal)
    assert all(r["source_output_tokens"] == len(output) for r in rows)
    for row in generated:
        assert row["originating_row_id"] == ("zero" if row["history"] == "zero" else "row")
        if row["terminal_observation_only"]:
            row["normalized_logit_delta"] = 10000
    means = list(d.case_means(rows))
    decision = [r for r in means if r["phase"] == "generated"]
    assert len(decision) == (0 if len(output) == 1 else 8)
    assert all(r["positions"] == min(4, len(output)-1) for r in decision)
    assert all(r["normalized_logit_delta"] < 10000 for r in decision)


def test_originating_history_and_turn_set_terminal_status():
    args = fixture()
    pair = args[0]["pairs"][1]  # Only zero history, turn 2 ends early.
    source_turn = args[4]["zero"]["turns"][1]
    source_turn.update(output_tokens=1, output_token_ids=[99])
    for arm in ("clean", "edited"):
        pair[arm]["output_prefix_ids"] = [99]
        pair[arm]["captures"] = pair[arm]["captures"][:4]
    rows = list(d.paired_rows(*args))
    terminal = [r for r in rows if r["terminal_observation_only"]]
    assert len(terminal) == 2
    assert all((r["history"], r["turn"], r["position"]) == ("zero", 2, 17) for r in terminal)


def test_complete_and_partial_summary_validate_schedules(tmp_path, monkeypatch):
    args = fixture((99,))
    root = tmp_path/"raw"
    plan = write_fixture(root, args)
    called = []
    validator = d.validate_capture_schedule

    def checked(root, plan):
        called.append(True)
        return validator(root, plan)

    monkeypatch.setattr(d, "validate_capture_schedule", checked)
    result = d.summarize(root, tmp_path/"complete", plan)
    assert called == [True]
    assert result["capture_schedule"]["complete"]
    with (tmp_path/"complete/paired_positions.csv").open() as f:
        positions = list(csv.DictReader(f))
    assert len(positions) == 16
    assert sum(r["terminal_observation_only"] == "True" for r in positions) == 8
    with (tmp_path/"complete/paired_cases.csv").open() as f:
        assert all(r["phase"] == "last_prompt" for r in csv.DictReader(f))
    partial_plan = deepcopy(plan)
    partial_plan["rows"].append(dict(args[1], id="not-yet-captured"))
    result = d.summarize(root, tmp_path/"partial", partial_plan)
    assert not result["capture_schedule"]["complete"]
    assert result["capture_schedule"]["validated_captures"] == 1
    with pytest.raises(ValueError, match="inventory"):
        validator(root, partial_plan)
    for arm in ("clean", "edited"):
        args[0]["pairs"][0][arm]["captures"] = args[0]["pairs"][0][arm]["captures"][2:]
    (root/"rows/capture-row.json").write_text(json.dumps(args[0]))
    with pytest.raises(ValueError, match="grid"):
        d.summarize(root, tmp_path/"bad-partial", partial_plan)


def test_validator_rejects_unplanned_capture_and_missing_source(tmp_path):
    args = fixture()
    root = tmp_path/"raw"
    plan = write_fixture(root, args)
    (root/"rows/capture-extra.json").write_text(json.dumps(args[0]))
    with pytest.raises(ValueError, match="inventory"):
        d.validate_capture_schedule(root, plan)
    (root/"rows/capture-extra.json").unlink()
    (root/"rows/zero.json").unlink()
    with pytest.raises(FileNotFoundError):
        d.validate_capture_schedule(root, plan)


def test_summary_default_plan_and_misnamed_capture(tmp_path, monkeypatch):
    args = fixture()
    root = tmp_path/"raw"
    plan = write_fixture(root, args)
    plan_path = tmp_path/"synthetic-plan.json"
    plan_path.write_text(json.dumps(plan))
    monkeypatch.setattr(d, "DEFAULT_PLAN", plan_path)
    assert d.summarize(root, tmp_path/"complete")["capture_schedule"]["complete"]
    args[0]["id"] = "not-a-capture"
    (root/"rows/capture-row.json").write_text(json.dumps(args[0]))
    with pytest.raises(ValueError, match="filename/ID"):
        d.summarize(root, tmp_path/"bad")


@pytest.mark.parametrize("field,value", [("input_tokens", 12), ("output_tokens", 4)])
def test_validator_binds_behavioral_lengths(tmp_path, field, value):
    args = fixture()
    args[4]["zero"]["turns"][0][field] = value
    plan = write_fixture(tmp_path/"raw", args)
    with pytest.raises(ValueError):
        d.validate_capture_schedule(tmp_path/"raw", plan)


def test_nonfinite_and_zero_vector_handling():
    with pytest.raises(ValueError, match="finite"):
        d.vector([float("nan")])
    assert d.cosine([0, 0], [1, 2]) is None
    assert d.cosine([1, 2], [1, 2]) == pytest.approx(1)


def test_terminal_observation_excluded_from_delivery_and_activation():
    row = {"id": "row", "spec": {"family": "feature-1", "seed": 101, "coefficient": .5},
           "turns": [{"output_tokens": 2, "cap_hit": True, "telemetry": {
               "feature_ids": [1], "position_metadata": [
                   {"position": 0, "origin": "prompt", "terminal_observation_only": False},
                   {"position": 1, "origin": "generated", "terminal_observation_only": False},
                   {"position": 2, "origin": "generated", "terminal_observation_only": True}],
               "delivery": {k: [1, 2, 100] for k in ("requested_norm", "realized_norm",
                   "cosine", "relative_error", "norm_ratio")},
               "reencoding": [{"position": p, "before": [p], "after": [p+1]} for p in range(3)]}}]}
    delivered = list(d.delivery_rows(row))
    assert [r["positions"] for r in delivered] == [1, 1]
    assert [r["mean_realized_norm"] for r in delivered] == [1, 2]
    activations = list(d.activation_rows(row))
    assert [r["positions"] for r in activations] == [1, 1]
    assert [r["mean_change"] for r in activations] == [1, 1]


def test_empty_run_is_described_not_invented(tmp_path):
    result = d.summarize(tmp_path/"missing", tmp_path/"out")
    assert result["behavioral_rows"] == result["capture_cases"] == 0
    assert result["statistical_intervals"] is None
    with pytest.raises(FileExistsError):
        d.summarize(tmp_path/"missing", tmp_path/"out")


def test_overview_preserves_both_histories_signs_and_all_transports(tmp_path):
    pytest.importorskip("matplotlib")
    rows = []
    for history in ("zero", "steered"):
        for coefficient in (-.5, .5):
            for family in ("aggregate-target", "aggregate-control-1", "aggregate-control-2", "aggregate-control-3"):
                for seed in (101, 202):
                    for layer in (50, 65, 78):
                        for transport in ["identity", "jacobian"]+[f"random_j_{i}" for i in range(1,6)]:
                            rows.append({"turn": 2, "phase": "last_prompt", "history": history,
                                "coefficient": coefficient, "family": family, "seed": seed,
                                "layer": layer, "group": "test", "transport": transport,
                                "normalized_logit_delta": coefficient if family == "aggregate-target" else 0})
    d.table(tmp_path/"paired_cases.csv", rows)
    files = d.figures(tmp_path)
    assert len(files) == 8
    assert all(d.Path(p).stat().st_size > 1000 for p in files)


def test_repeated_zero_identity_is_checked_within_exact_settings():
    row = {"id": "one", "spec": {"coefficient": 0, "prompt": "notebook",
           "temperature": .6, "cap": 128, "seed": 101},
           "turns": [{"output_token_ids": [1, 2]}, {"output_token_ids": [3]}]}
    copy = deepcopy(row); copy["id"] = "two"
    assert d.zero_consistency([row, copy])[0]["distinct_two_turn_outputs"] == 1
    copy["turns"][1]["output_token_ids"] = [4]
    assert d.zero_consistency([row, copy])[0]["distinct_two_turn_outputs"] == 2
    copy["spec"]["seed"] = 202
    assert len(d.zero_consistency([row, copy])) == 2

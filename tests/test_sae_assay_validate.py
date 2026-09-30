"""Independent validator fixtures and corruption tests; no paid/network actions."""

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import subprocess
import sys

import pytest

from experiments.sae_assay_diagnostic import validate as v


def telemetry(tokens=(1, 5, 6), prompt=3, mode="zero", strength=0, full=False):
    n, k = len(tokens), 2
    before = [[2., 1.] for _ in tokens]
    delta = [[0., 0.] if mode == "zero" else
             [-strength * x for x in row] if mode == "suppression" else
             [strength * (q - x) for q, x in zip([4., 3.], row)] for row in before]
    requested = [[x + d for x, d in zip(row, diff)] for row, diff in zip(before, delta)]
    norms = [sum(x*x for x in row)**.5 for row in delta]
    t = {"schema_version": v.SCHEMA, "encoding_authority": v.AUTHORITY,
         "feature_ids": [0, 3], "full_encode_shape": [1, 8, 16],
         "native_dtype": "torch.bfloat16", "diagnostics_dtype": "torch.float32",
         "hook_removed": True, "hook_layer": "model.layers.50.output",
         "position_metadata": [{"position": i, "token_id": token,
             "origin": "prompt" if i < prompt else "generated",
             "token_class": "special" if token in [1, 2] else "prompt" if i < prompt else "generated",
             "terminal_observation_only": i == n - 1 and prompt < n}
             for i, token in enumerate(tokens)],
         "selected_activations": {"before": before, "requested_delta": delta,
                                  "requested_activation": requested, "after": deepcopy(requested)},
         "delivery": {"requested_norm": norms, "realized_norm": norms[:],
             "clean_norm": [10.] * n, "relative_error": [0.] * n, "cosine": [1.] * n,
             "identity": [r == 0 for r in norms], "nonzero_requested": [r > 0 for r in norms],
             "valid": [True] * n},
         "q90": [4., 3.] if mode == "amplification" else None,
         "selected_encode_shapes": [[n, k, 16]] if full else [], "full_sae": None}
    if full:
        t["full_sae"] = {"full_selected_before": deepcopy(before), "full_selected_after": deepcopy(requested),
            "selected_path_before": deepcopy(before), "selected_path_after": deepcopy(requested),
            "ideal_fp32_before": deepcopy(before), "ideal_fp32_after": deepcopy(requested),
            "actual_fp32_after": deepcopy(requested), "l0_before": [5] * n, "l0_after": [5] * n,
            "non_target_changed_count": [0] * n, "non_target_change_norm": [0.] * n,
            "reconstruction_error_norm": [2.] * n, "reconstruction_relative_error": [.2] * n}
    return t


def summaries(t):
    rows = []
    for j, feature in enumerate(t["feature_ids"]):
        row = {"feature_id": feature}
        for key in ("before", "after"):
            values = [r[j] for r in t["selected_activations"][key]]
            active = [x for x in values if x > 0]
            row[key] = {"count": len(values), "active_count": len(active),
                "frequency": len(active) / len(values), "mean": sum(values) / len(values),
                "max": max(values), "positive_q50": active[0] if active else None,
                "positive_q90": active[0] if active else None}
        rows.append(row)
    return rows


def teacher(mode="zero", strength=0, full=False, replay=False):
    tokens = [1, 5, 6]
    prompt = 1 if replay else 3
    t = telemetry(tokens, prompt, mode, strength, full)
    return {"token_ids": tokens, "input_tokens": prompt, "output_tokens": 3 - prompt,
        "input_token_ids": tokens[:prompt], "output_token_ids": tokens[prompt:], "prompt_length": prompt,
        "forward_schedule": "original_prefill_then_cached_token1" if replay else "uncached_teacher",
        "elapsed_seconds": .2, "telemetry": t, "clean_telemetry": telemetry(tokens, prompt),
        "unsteered_nll": [None, 2., 3.], "edited_nll": [None, 2., 3.] if mode == "zero" else [None, 2.1, 3.2],
        "kl_clean_to_edited": [None, 0., 0.] if mode == "zero" else [None, .01, .02],
        "full_sae_diagnostics": full, "reconstruction_nll": [None, 3., 4.] if full else None,
        "activation_summaries": summaries(t)}


def wrapped(mode="zero", strength=0, **kwargs):
    return {"id": "fixture-1", "split": "calibration", "category": "neutral", "group": "target",
            "mode": mode, "strength": strength, "result": teacher(mode, strength, **kwargs)}


def generation(mode="zero", strength=0):
    return {"response": "answer", "input_token_ids": [1], "output_token_ids": [5, 6],
            "input_tokens": 1, "output_tokens": 2, "cap_hit": False, "elapsed_seconds": .3,
            "rendered_input_sha256": "a" * 64,
            "input_token_ids_sha256": hashlib.sha256(json.dumps([1]).encode()).hexdigest(),
            "telemetry": telemetry([1, 5, 6], 1, mode, strength)}


def baseline():
    return {"id": "baseline-1", "kind": "baseline", "phase": "core", "response": "answer",
            "missing": False, "generation1": generation(), "generation2": generation(),
            "replay": teacher(replay=True)}


def write_jsonl(path, rows):
    path.write_bytes(b"".join(v._canonical(row) + b"\n" for row in rows))
    return path


@pytest.mark.parametrize("mode,strength", [("zero", 0), ("suppression", .5), ("suppression", 1), ("amplification", .5), ("amplification", 1)])
@pytest.mark.parametrize("full,replay", [(False, False), (True, False), (True, True)])
def test_valid_teacher_matrix(mode, strength, full, replay):
    result = v.validate_teacher(wrapped(mode, strength, full=full, replay=replay))
    assert result["status"] == "ok", result
    assert result["counts"]["positions"] == 3
    assert result["counts"]["feature_positions"] == 6


@pytest.mark.parametrize("mode,strength", [("zero", 0), ("suppression", .5), ("amplification", 1)])
def test_generation_accepts_terminal_position(mode, strength):
    assert v.validate_generation(generation(mode, strength))["status"] == "ok"
    assert v.validate_generation(generation(mode, strength))["pass"] is True


def test_bad_scientific_outcome_remains_valid():
    row = wrapped("suppression", .5, full=True)
    r, t = row["result"], row["result"]["telemetry"]
    t["selected_activations"]["after"] = deepcopy(t["selected_activations"]["before"])
    t["delivery"]["realized_norm"] = [0.] * 3
    t["delivery"]["relative_error"] = [1.] * 3
    t["delivery"]["cosine"] = [0.] * 3
    t["delivery"]["identity"] = [True] * 3
    t["full_sae"]["full_selected_after"] = deepcopy(t["selected_activations"]["after"])
    t["full_sae"]["actual_fp32_after"] = deepcopy(t["full_sae"]["ideal_fp32_before"])
    t["full_sae"]["selected_path_before"] = [[0., 0.]] * 3  # Decision disagreement is evidence, not malformed.
    r["activation_summaries"] = summaries(t)
    r["edited_nll"] = r["unsteered_nll"][:]
    r["kl_clean_to_edited"] = [None, 0., 0.]
    assert v.validate_teacher(row)["status"] == "ok"


@pytest.mark.parametrize("section,key", [("selected_activations", k) for k in v.ACTIVATIONS]
                         + [("delivery", k) for k in v.NORM_FIELDS + v.BOOL_FIELDS + ("cosine",)]
                         + [("full_sae", k) for k in v.FULL_MATRICES])
def test_all_column_lengths_checked(section, key):
    row = wrapped(full=True)
    row["result"]["telemetry"][section][key].pop()
    assert v.validate_teacher(row)["status"] == "invalid"


@pytest.mark.parametrize("mutation", [
    lambda r: r["telemetry"]["feature_ids"].__setitem__(1, 0),
    lambda r: r["telemetry"]["position_metadata"][1].__setitem__("position", 0),
    lambda r: r["telemetry"]["position_metadata"][1].__setitem__("token_id", 42),
    lambda r: r["telemetry"]["position_metadata"][1].__setitem__("origin", "generated"),
    lambda r: r["telemetry"]["position_metadata"][-1].__setitem__("terminal_observation_only", True),
    lambda r: r["telemetry"]["selected_activations"]["before"][0].append(2),
    lambda r: r["telemetry"]["delivery"]["clean_norm"].__setitem__(0, -1),
    lambda r: r["telemetry"]["delivery"]["identity"].__setitem__(0, False),
    lambda r: r["telemetry"]["delivery"]["nonzero_requested"].__setitem__(0, True),
    lambda r: r["telemetry"]["delivery"]["valid"].__setitem__(0, 1),
    lambda r: r["telemetry"]["delivery"]["relative_error"].__setitem__(0, .4),
    lambda r: r["telemetry"]["selected_activations"]["requested_activation"][0].__setitem__(0, 5),
    lambda r: r["telemetry"]["selected_activations"]["after"][0].__setitem__(0, 9),
    lambda r: r["unsteered_nll"].__setitem__(0, 0),
    lambda r: r["edited_nll"].__setitem__(1, 99),
    lambda r: r["kl_clean_to_edited"].__setitem__(1, .1),
    lambda r: r.__setitem__("extra", float("nan")),
    lambda r: r["activation_summaries"][0]["before"].__setitem__("active_count", 0),
])
def test_corruption_is_invalid_not_zero(mutation):
    row = wrapped()
    mutation(row["result"])
    report = v.validate_teacher(row)
    assert report["status"] == "invalid", report
    assert report["counts"]["valid_rows"] == 0
    assert "outcome" not in report and "score" not in report


def test_signed_request_and_norm_geometry_checked():
    row = wrapped("suppression", .5)
    row["result"]["telemetry"]["delivery"]["relative_error"][0] = .5
    assert v.validate_teacher(row)["status"] == "invalid"
    row = wrapped("suppression", .5)
    row["result"]["telemetry"]["selected_activations"]["requested_delta"][0][0] = 1
    assert v.validate_teacher(row)["status"] == "invalid"
    result = generation("amplification", .5)
    result["telemetry"]["q90"] = [8., 9.]
    assert v.validate_generation(result)["status"] == "invalid"


def test_transport_and_missing_distinguished(tmp_path):
    row = wrapped()
    row.update(status="transport_error", error="timeout", result=None)
    assert v.validate_teacher(row)["status"] == "transport_error"
    missing = baseline()
    missing["response"] = missing["generation2"]["response"] = ""
    missing["missing"] = True
    report = v.validate_jsonl(write_jsonl(tmp_path / "missing.jsonl", [missing]))
    assert report["status"] == "missing"
    assert report["counts"]["valid_rows"] == 0


def test_baseline_binds_replay_and_response(tmp_path):
    row = baseline()
    path = write_jsonl(tmp_path / "base.jsonl", [row])
    assert v.validate_jsonl(path)["status"] == "ok"
    row["response"] = "invented response"
    assert v.validate_jsonl(write_jsonl(path, [row]))["status"] == "invalid"
    row = baseline()
    row["replay"] = teacher()  # Same text IDs, different original prompt boundary.
    assert v.validate_jsonl(write_jsonl(path, [row]))["status"] == "invalid"


@pytest.mark.parametrize("raw", [b'{"id":"x","id":"y"}\n', b'{"x":NaN}\n',
                                    b'{"x":1e999}\n', b'{"x":Infinity}\n', b'{}', b'\n'])
def test_malformed_jsonl_is_not_repaired(tmp_path, raw):
    path = tmp_path / "raw.jsonl"
    path.write_bytes(raw)
    before = path.stat().st_mtime_ns
    assert v.validate_jsonl(path)["status"] == "invalid"
    assert path.read_bytes() == raw and path.stat().st_mtime_ns == before


def test_plain_ids_plan_completeness_and_fixture_arms(tmp_path):
    path = write_jsonl(tmp_path / "rows.jsonl", [wrapped(), wrapped("suppression", .5)])
    assert v.validate_jsonl(path)["status"] == "ok"  # Fixture reused in another arm.
    assert v.validate_jsonl(path, ["fixture-1"])["status"] == "invalid"
    write_jsonl(path, [wrapped()])
    assert v.validate_jsonl(path, ["other"])["status"] == "invalid"
    assert v.validate_jsonl(path, ["fixture-1", "missing"], require_complete=True)["status"] == "incomplete"
    assert v.validate_jsonl(path, ["fixture-1", "missing"])["missing_ids"] == ["missing"]
    assert v.validate_jsonl(path, ["fixture-1", "fixture-1"])["status"] == "invalid"


def ledger_rows(payload=None):
    records = []
    data = [("binding", {"kind": "binding", "row_ids": ["run-1"]}),
            ("row:run-1", {"kind": "row", "row_id": "run-1", "payload": payload or wrapped()})]
    for identifier, item in data:
        row = {"id": identifier, "seq": len(records), "data": item,
               "plan_sha256": "a" * 64, "freeze_commit": "b" * 40,
               "previous_sha256": records[-1]["sha256"] if records else None}
        row["sha256"] = hashlib.sha256(v._canonical(row)).hexdigest()
        records.append(row)
    return records


def test_receipt_integrity_and_anchor(tmp_path):
    path = write_jsonl(tmp_path / "events.jsonl", ledger_rows()[:1])
    initial = v.validate_jsonl(path)
    assert initial["status"] == "ok"
    assert initial["append_only_history_proven"] is False
    write_jsonl(path, ledger_rows())
    full = v.validate_jsonl(path, ["run-1"], require_complete=True, anchor=initial["anchor"])
    assert full["status"] == "ok" and full["prefix_anchor_verified"]
    write_jsonl(path, ledger_rows()[:1])
    assert v.validate_jsonl(path, anchor=full["anchor"])["status"] == "invalid"
    rows = ledger_rows()
    rows[1]["data"]["payload"]["category"] = "tampered"
    assert v.validate_jsonl(write_jsonl(path, rows))["status"] == "invalid"


@pytest.mark.parametrize("field,value", [("seq", 8), ("previous_sha256", None),
                                         ("plan_sha256", "c" * 64), ("id", "binding")])
def test_rehashed_bad_chain_is_rejected(tmp_path, field, value):
    rows = ledger_rows()
    rows[1][field] = value
    body = {k: v for k, v in rows[1].items() if k != "sha256"}
    rows[1]["sha256"] = hashlib.sha256(v._canonical(body)).hexdigest()
    assert v.validate_jsonl(write_jsonl(tmp_path / "events.jsonl", rows))["status"] == "invalid"


def test_flat_receipt_chain_and_malformed_payload(tmp_path):
    row = {**baseline(), "plan_sha256": "a" * 64, "freeze_commit": "b" * 40,
           "previous_sha256": None, "recorded_at_utc": "2026-09-30T00:00:00+00:00"}
    row["receipt_sha256"] = hashlib.sha256(v._canonical(row)).hexdigest()
    path = write_jsonl(tmp_path / "receipts.jsonl", [row])
    assert v.validate_jsonl(path, ["baseline-1"])["status"] == "ok"
    rows = ledger_rows({"id": "run-1", "unexpected": 0})
    assert v.validate_jsonl(write_jsonl(path, rows))["status"] == "invalid"


def test_cli_directory_is_read_only(tmp_path):
    path = write_jsonl(tmp_path / "rows.jsonl", [wrapped()])
    original = path.read_bytes()
    result = subprocess.run([sys.executable, "-m", "experiments.sae_assay_diagnostic.validate", str(tmp_path)],
                            text=True, capture_output=True, check=False)
    assert result.returncode == 0, result.stderr + result.stdout
    assert json.loads(result.stdout)["status"] == "ok"
    assert path.read_bytes() == original and sorted(p.name for p in tmp_path.iterdir()) == ["rows.jsonl"]


@pytest.mark.parametrize("dtype_name", ["float32", "bfloat16"])
def test_actual_backend_teacher_generation_and_replay(dtype_name, tmp_path):
    torch = pytest.importorskip("torch")
    transformers = pytest.importorskip("transformers")
    from experiments.sae_assay_diagnostic.backend import ModelBackend
    from tests.test_sae_assay_backend import TinyTokenizer

    dtype = getattr(torch, dtype_name)
    with torch.random.fork_rng():
        torch.manual_seed(82)
        config = transformers.LlamaConfig(vocab_size=32, hidden_size=16, intermediate_size=32,
            num_hidden_layers=2, num_attention_heads=2, num_key_value_heads=2, max_position_embeddings=64,
            bos_token_id=1, eos_token_id=2)
        model = transformers.LlamaForCausalLM(config).to(dtype)
        state = {"encoder_linear.weight": torch.randn(8, 16).to(dtype),
                 "encoder_linear.bias": torch.ones(8).to(dtype),
                 "decoder_linear.weight": (torch.randn(16, 8) * .04).to(dtype),
                 "decoder_linear.bias": torch.zeros(16).to(dtype)}
    backend = ModelBackend.from_components_for_test(model, TinyTokenizer(), state, default_feature_ids=[0, 3])
    try:
        arm = {"feature_ids": [0, 3], "mode": "suppression", "strength": .5}
        for intervention in (None, arm):
            result = backend.teacher("abcde", [0, 3], intervention, collect_reconstruction=True)
            report = v.validate_teacher(result)
            assert report["status"] == "ok", report
            if intervention is None:
                clean = result
        generated = backend.generate([{"role": "user", "content": "abc"}], 3, .5, 3, arm)
        assert v.validate_generation(generated)["status"] == "ok"
        replayed = backend.replay_tokens(generated["input_token_ids"], generated["output_token_ids"],
                                         [0, 3], arm, collect_reconstruction=True)
        report = v.validate_teacher(replayed)
        assert report["status"] == "ok", report
        zero_arm = dict(arm, strength=0)
        messages = [{"role": "user", "content": "Reply with the word ready"}]
        clean_generated = backend.generate(messages, 3, .5, 8)
        zero_generated = backend.generate(messages, 3, .5, 8, zero_arm)
        clean_replay = backend.replay_tokens(clean_generated["input_token_ids"],
                                             clean_generated["output_token_ids"], [0, 3])
        row = qualification()
        row.update(result=clean, zero=backend.teacher("abcde", [0, 3], zero_arm),
                   generation_check={"pass": True, "generated": clean_generated,
                                     "zero_generated": zero_generated, "replay": clean_replay})
        report = v.validate_jsonl(write_jsonl(tmp_path / "qualification.jsonl", [row]))
        assert report["pass"], report
    finally:
        backend.close()


def redacted_generation():
    result = generation()
    result.pop("input_token_ids")
    result["upstream_input_tokens_omitted"] = True
    result["telemetry"]["position_metadata"][0].pop("token_id")
    return result


def test_notebook_omission_requires_protocol_flag_hashes_and_counts(tmp_path):
    result = redacted_generation()
    report = v.validate_generation(result, protocol="notebook")
    assert report["pass"] and report["counts"]["prompt_ids_not_rehashed"] == 1
    assert report["limitations"]
    assert not v.validate_generation(result)["pass"]
    assert not v.validate_generation(result, protocol="paper")["pass"]
    mutations = [
        lambda r: r.pop("upstream_input_tokens_omitted"),
        lambda r: r.__setitem__("input_tokens", 4),
        lambda r: r.__setitem__("input_token_ids_sha256", "bad"),
        lambda r: r.__setitem__("input_token_ids", [1]),
        lambda r: r["telemetry"]["position_metadata"][0].__setitem__("token_id", None),
        lambda r: r["telemetry"]["position_metadata"][1].pop("token_id"),
    ]
    for mutate in mutations:
        result = redacted_generation()
        mutate(result)
        assert not v.validate_generation(result, protocol="notebook")["pass"]
    row = baseline()
    row.pop("missing")
    row.update(protocol="notebook", status="ok", generation1=redacted_generation(),
               generation2=redacted_generation(), replay=None, first_turn_empty=False)
    assert v.validate_jsonl(write_jsonl(tmp_path / "notebook.jsonl", [row]))["pass"]


def test_runner_missing_empty_schema(tmp_path):
    row = baseline()
    row.pop("missing")
    row.update(status="missing_empty", first_turn_empty=False)
    row["response"] = row["generation2"]["response"] = ""
    path = write_jsonl(tmp_path / "base.jsonl", [row])
    report = v.validate_jsonl(path)
    assert report["status"] == "missing" and not report["pass"]
    row["status"] = "ok"
    assert v.validate_jsonl(write_jsonl(path, [row]))["status"] == "invalid"


def qualification():
    return {"id": "qualification-1", "kind": "qualification", "text_id": "fixture-1",
            "result": teacher(full=True), "zero": teacher(), "zero_pass": True,
            "generation_check": None,
            "encoder_diagnostic": {"pass": False, "disagreements": 4}}


def generation_check():
    return {"pass": True, "generated": generation(), "zero_generated": generation(),
            "replay": teacher(replay=True)}


def test_qualification_generation_cached_check(tmp_path):
    row = qualification()
    row["generation_check"] = generation_check()
    report = v.validate_jsonl(write_jsonl(tmp_path / "qual.jsonl", [row]))
    assert report["pass"], report
    assert report["counts"]["generation_checks"] == 1
    assert report["counts"]["failed_generation_checks"] == 0


@pytest.mark.parametrize("mutation", [
    lambda c: c.__setitem__("pass", False),
    lambda c: c.__setitem__("pass", 1),
    lambda c: c.pop("zero_generated"),
    lambda c: c.__setitem__("generated", generation("suppression", .5)),
    lambda c: c["zero_generated"].__setitem__("rendered_input_sha256", "b" * 64),
    lambda c: c["generated"].__setitem__("cap_hit", True),
    lambda c: c["replay"].__setitem__("forward_schedule", "uncached_teacher"),
    lambda c: c["replay"]["telemetry"]["selected_activations"]["before"][0].__setitem__(0, 3.),
])
def test_qualification_generation_check_rejects_corruption(tmp_path, mutation):
    row = qualification()
    row["generation_check"] = generation_check()
    mutation(row["generation_check"])
    assert v.validate_jsonl(write_jsonl(tmp_path / "qual.jsonl", [row]))["status"] == "invalid"


def test_qualification_generation_failure_is_evidence_not_malformed(tmp_path):
    row = qualification()
    check = row["generation_check"] = generation_check()
    replay = check["replay"]
    for t in (replay["telemetry"], replay["clean_telemetry"]):
        for key in ("before", "requested_activation", "after"):
            t["selected_activations"][key] = [[3., 1.]] * 3
    replay["activation_summaries"] = summaries(replay["telemetry"])
    path = tmp_path / "qual.jsonl"
    assert not v.validate_jsonl(write_jsonl(path, [row]))["pass"]
    check["pass"] = False
    report = v.validate_jsonl(write_jsonl(path, [row]))
    assert report["pass"] and report["counts"]["failed_generation_checks"] == 1


def positive():
    return {"id": "positive-1", "kind": "positive", "task_id": "task-1", "arm": "amplification",
            "seed": 3, "temperature": .5, "max_new_tokens": 128, "status": "ok",
            "result": generation("amplification", .5), "nondegenerate": False}


def judge():
    return {"id": "judge-1", "kind": "local_judge", "source_id": "fixture-1",
            "rubric": "notebook", "label": None, "response": "Unclear", "cap_hit": False,
            "input_tokens": 13, "output_tokens": 2, "prompt_sha256": "f" * 64}


def run_directory(root, rows, dispatch_only=()):
    (root / "rows").mkdir(parents=True, exist_ok=True)
    records = []

    def event(identifier, data):
        row = {"id": identifier, "seq": len(records), "data": data, "plan_sha256": "a" * 64,
               "freeze_commit": "b" * 40, "previous_sha256": records[-1]["sha256"] if records else None}
        row["sha256"] = hashlib.sha256(v._canonical(row)).hexdigest()
        records.append(row)

    ids = [r["id"] for r in rows] + list(dispatch_only)
    event("binding", {"kind": "binding", "row_ids": sorted(ids)})
    for row in rows:
        identifier = row["id"]
        file = root / "rows" / (identifier + ".json")
        file.write_bytes(v._canonical(row) + b"\n")
        event("dispatch:" + identifier, {"kind": "dispatch", "row_id": identifier})
        event("row:" + identifier, {"kind": "row", "row_id": identifier, "payload": {
            "path": f"rows/{identifier}.json", "sha256": hashlib.sha256(file.read_bytes()).hexdigest()}})
    for identifier in dispatch_only:
        event("dispatch:" + identifier, {"kind": "dispatch", "row_id": identifier})
    write_jsonl(root / "receipts.jsonl", records)
    return records


def test_run_directory_all_current_runner_row_kinds(tmp_path):
    rows = [wrapped(), baseline(), qualification(), positive(), judge()]
    run_directory(tmp_path, rows)
    before = {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    report = v.validate_run_directory(tmp_path, [r["id"] for r in rows], require_complete=True)
    assert report["pass"], report
    assert report["counts"]["unparsed_judge_labels"] == 1
    assert report["counts"]["qualification_rows"] == 1
    assert report["counts"]["positive_rows"] == 1
    assert {p: p.read_bytes() for p in before} == before


def test_run_directory_rejects_unknown_row_kind_even_with_teacher_fields(tmp_path):
    row = wrapped()
    row["kind"] = "unknown"
    run_directory(tmp_path, [row])
    assert v.validate_run_directory(tmp_path)["status"] == "invalid"


def test_run_directory_rejects_hash_id_or_path_replacement(tmp_path):
    records = run_directory(tmp_path, [wrapped()])
    file = tmp_path / "rows" / "fixture-1.json"
    file.write_bytes(file.read_bytes() + b" ")
    assert not v.validate_run_directory(tmp_path)["pass"]
    records = run_directory(tmp_path, [wrapped()])
    receipt = records[-1]
    receipt["data"]["payload"]["path"] = "../elsewhere.json"
    receipt["sha256"] = hashlib.sha256(v._canonical({k: val for k, val in receipt.items() if k != "sha256"})).hexdigest()
    write_jsonl(tmp_path / "receipts.jsonl", records)
    assert not v.validate_run_directory(tmp_path)["pass"]


def test_run_directory_unresolved_dispatch_is_incomplete_not_negative(tmp_path):
    run_directory(tmp_path, [wrapped()], dispatch_only=["pending"])
    report = v.validate_run_directory(tmp_path)
    assert report["status"] == "incomplete" and report["pending_dispatch_ids"] == ["pending"]
    row = wrapped()
    row["id"] = "pending"
    (tmp_path / "rows" / "pending.json").write_bytes(v._canonical(row) + b"\n")
    assert v.validate_run_directory(tmp_path)["status"] == "incomplete"


def test_run_directory_orphan_and_symlink_fail(tmp_path):
    run_directory(tmp_path, [wrapped()])
    unknown = tmp_path / "rows" / "unknown.json"
    unknown.write_text("{}")
    assert not v.validate_run_directory(tmp_path)["pass"]
    unknown.unlink()
    file = tmp_path / "rows" / "fixture-1.json"
    relocated = tmp_path / "relocated.json"
    file.rename(relocated)
    file.symlink_to(relocated)
    assert not v.validate_run_directory(tmp_path)["pass"]


def test_run_directory_export_manifest_and_cli(tmp_path):
    row = baseline()
    run_directory(tmp_path, [row])
    export = write_jsonl(tmp_path / "responses-core.jsonl", [row])
    manifest = {"sha256": hashlib.sha256(export.read_bytes()).hexdigest(), "plan_sha256": "a" * 64,
                "freeze_commit": "b" * 40, "ids": [row["id"]]}
    Path(str(export) + ".manifest.json").write_bytes(v._canonical(manifest) + b"\n")
    assert v.validate_run_directory(tmp_path)["pass"]
    result = subprocess.run([sys.executable, "-m", "experiments.sae_assay_diagnostic.validate", str(tmp_path)],
                            text=True, capture_output=True, check=False)
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout)["pass"]
    manifest["ids"] = ["another"]
    Path(str(export) + ".manifest.json").write_bytes(v._canonical(manifest) + b"\n")
    assert not v.validate_run_directory(tmp_path)["pass"]

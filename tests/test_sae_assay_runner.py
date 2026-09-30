"""Free integration checks; no pretrained downloads, providers or GPU rental."""
import copy
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path

import pytest

from experiments.sae_assay_diagnostic import protocol, runner
from tests.test_sae_assay_backend import tiny


def minimal_plan():
    baseline = protocol.baseline_rows()[0]
    return {"target_feature_ids": [0, 3], "strengths": [.5, 1.], "operator": {"test_only": True},
            "texts": [{"id": "calibration-neutral-01", "text": "abcde", "split": "calibration", "category": "neutral"}],
            "qualification_text_ids": ["calibration-neutral-01"],
            "positive_control": {"calibration_texts": [{"id": "pc-calibration-01", "text": "abcd"}], "rows": []},
            "response_rows": [dict(baseline, query="brief")], "judge_fixtures": [], "max_new_tokens_per_turn": 8}


def make_run(tmp_path, tiny, plan=None, clock=None):
    plan = plan or minimal_plan()
    path = tmp_path / "plan.json"
    runner.write_once(path, plan)
    deadline = (datetime.now(timezone.utc) + timedelta(hours=3)).isoformat()
    kwargs = {"clock": clock} if clock else {}
    return runner.Run(plan, path, "a" * 40, tmp_path / "run", deadline,
                      lambda **kw: tiny, barriers=False, **kwargs)


def test_inventory_unique_complete_and_paired_seeds():
    rows = protocol.baseline_rows()
    assert len(rows) == 290
    assert sum(r["phase"] == "core" for r in rows) == 80
    assert len({r["turn1_seed"] for r in rows} | {r["turn2_seed"] for r in rows}) == 580
    ids = runner.inventory(minimal_plan())
    assert len(ids) == len(set(ids))


def test_tiny_model_teacher_end_to_end_receipts_resume_and_corruption(tmp_path, tiny):
    run = make_run(tmp_path, tiny)
    text = run.plan["texts"][0]
    original = run.teacher("target", text, [0, 3], full=True)
    assert original["result"]["reconstruction_nll"] is not None
    again = run.teacher("target", text, [0, 3], full=True)
    assert again == original
    assert len(run.completed) == 1
    run.audit()
    path = run.out / "rows" / (original["id"] + ".json")
    path.write_text("{}\n")
    with pytest.raises(ValueError, match="hash changed"):
        run.audit()


def test_uncertain_dispatch_is_never_rerun(tmp_path, tiny):
    run = make_run(tmp_path, tiny)
    identifier = run.plan["response_rows"][0]["id"]
    def interrupted():
        raise ConnectionError("mock interruption")
    with pytest.raises(ConnectionError):
        run.row(identifier, interrupted)
    with pytest.raises(RuntimeError, match="Unresolved prior dispatch"):
        run.row(identifier, lambda: pytest.fail("must not retry"))


def test_deadline_prevents_dispatch(tmp_path, tiny):
    run = make_run(tmp_path, tiny, clock=lambda: 9e10)
    with pytest.raises(TimeoutError):
        run.row(run.plan["response_rows"][0]["id"], lambda: pytest.fail("dispatch"))
    assert len(run.ledger.read()) == 2


def test_stage_prerequisites_cannot_be_bypassed(tmp_path, tiny):
    run = make_run(tmp_path, tiny)
    for stage in ("target", "core", "positive", "optional"):
        with pytest.raises(ValueError, match="qualification"):
            run.require_stage(stage)
    assert run.backend is None


def test_completed_terminal_receipt_is_idempotent_without_model_calls(tmp_path, tiny, monkeypatch):
    run = make_run(tmp_path, tiny)
    path = run.out / "DONE-qualification.json"
    terminal = {"status": "complete", "plan_sha256": run.plan_hash, "freeze_commit": run.freeze,
                "row_count": 0, "utc": "2026-09-30T00:00:00+00:00"}
    runner.write_once(path, terminal)
    monkeypatch.setattr(runner, "load_plan", lambda *args: run.plan)
    monkeypatch.setattr(runner.Run, "model", lambda *args, **kw: pytest.fail("completed run must not load model"))
    import sys
    monkeypatch.setattr(sys, "argv", ["runner", "--plan", str(tmp_path / "plan.json"),
        "--freeze", run.freeze, "--out", str(run.out), "--deadline-utc",
        datetime.fromtimestamp(run.deadline, timezone.utc).isoformat(), "--stage", "qualification"])
    runner.main()
    runner.main()
    assert json.loads(path.read_text()) == terminal


def test_barrier_resume_keeps_original_checkpoint(tmp_path, tiny):
    run = make_run(tmp_path, tiny)
    run.barriers = True
    (run.out / "APPROVE-qualification").write_text(run.plan_hash)
    run.barrier("qualification")
    notice = (run.out / "WAITING-qualification.json").read_bytes()
    run.teacher("target", run.plan["texts"][0], [0, 3])
    run.barrier("qualification")
    assert (run.out / "WAITING-qualification.json").read_bytes() == notice


def test_invalid_returned_row_is_retained_but_not_promoted(tmp_path, tiny):
    run = make_run(tmp_path, tiny)
    identifier = run.plan["response_rows"][0]["id"]
    def reject(_):
        raise ValueError("bad row")
    with pytest.raises(ValueError, match="bad row"):
        run.row(identifier, lambda: {"id": identifier, "malformed": True}, reject)
    assert run.result(identifier)["malformed"]
    assert identifier not in run.completed


def test_real_tiny_two_turn_generation_replay_and_input_manifest(tmp_path, tiny, monkeypatch):
    monkeypatch.setitem(runner.INDUCTIONS, "self_ref_paper", "abc")
    run = make_run(tmp_path, tiny)
    run.baseline("core")
    result = run.result(run.plan["response_rows"][0]["id"])
    assert result["replay"]["token_ids"] == result["generation2"]["input_token_ids"] + result["generation2"]["output_token_ids"]
    assert result["generation1"]["response"] in tiny.tokenizer.apply_chat_template([
        {"role": "user", "content": result["generation1"]["response"]}], tokenize=False)
    if result["status"] == "ok":
        path = run.out / "responses-core.jsonl"
        manifest = json.loads(Path(str(path) + ".manifest.json").read_text())
        assert manifest["sha256"] == protocol.sha(path)
        assert manifest["ids"] == [result["id"]]


def test_qualification_includes_real_cached_zero_replay_check(tmp_path, tiny):
    plan = minimal_plan()
    categories = ("pretending", "cover-story", "assistant-roleplay", "misdirection",
                  "dishonesty", "persona-maintenance", "neutral")
    plan["texts"] = [{"id": f"calibration-{c}-01", "text": "abcde", "split": "calibration",
                      "category": c} for c in categories]
    plan["qualification_text_ids"] = [r["id"] for r in plan["texts"]]
    plan["qualification_generation"] = {"prompt": "Reply with the word ready.", "seed": 34,
                                        "temperature": .5, "max_new_tokens": 8}
    run = make_run(tmp_path, tiny, plan)
    run.qualify()
    first = run.result("qualification-" + plan["qualification_text_ids"][0])
    assert first["generation_check"]["pass"]
    assert len(run.completed) == 7


def test_write_once_and_upstream_input_redaction(tmp_path):
    path = tmp_path / "once.json"
    runner.write_once(path, {"x": 1})
    runner.write_once(path, {"x": 1})
    with pytest.raises(ValueError):
        runner.write_once(path, {"x": 2})
    raw = {"input_token_ids": [1, 2], "output_token_ids": [3],
           "telemetry": {"position_metadata": [{"origin": "prompt", "token_id": 1},
                                                {"origin": "generated", "token_id": 3}]}}
    redacted = runner.redact_upstream_inputs(raw)
    assert "input_token_ids" not in redacted
    assert "token_id" not in redacted["telemetry"]["position_metadata"][0]
    assert raw["input_token_ids"] == [1, 2]
    assert redacted["telemetry"]["position_metadata"][1]["token_id"] == 3


def test_format_quality_is_separate_from_json_validity():
    assert runner.nondegenerate({"response": "not JSON but nonempty", "output_token_ids": [1, 2, 3], "cap_hit": False})
    assert not runner.nondegenerate({"response": "{}", "output_token_ids": [1] * 100, "cap_hit": False})
    assert not runner.nondegenerate({"response": "{}", "output_token_ids": [1, 2], "cap_hit": True})


def test_tiny_delivery_calibration_failure_is_preserved_not_a_behavioral_null(tmp_path, tiny):
    plan = minimal_plan()
    plan["texts"] = [{"id": f"calibration-neutral-{i:02d}", "text": "abcdefgh", "split": "calibration",
                      "category": "neutral"} for i in range(1, 7)]
    plan["texts"] += [{"id": "validation-neutral-01", "text": "abcdefgh", "split": "validation",
                       "category": "neutral"}]
    run = make_run(tmp_path, tiny, plan)
    result = run.delivery("target", plan["texts"], [0, 3])
    assert result["pass"] is False
    assert result["validation"] == "not_run_by_gate"
    assert result["strength"] is None
    assert len(run.completed) == 30
    assert not any("validation-" in k for k in run.completed)
    selection = json.loads((run.out / "target-selection.json").read_text())
    assert "insufficient_exposure" in selection["calibration"]["0.5"]["failure_codes"]

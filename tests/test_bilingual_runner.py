"""Synthetic durability tests, explicitly excluded from scientific outcomes."""
import json

import pytest

from experiments.bilingual_llama_pilot import protocol
from experiments.bilingual_llama_pilot.runner import Study
from tests.test_instruction_state_runner import FakeBackend


def make_run(tmp_path, backend=None, *, barriers=False):
    backend = backend or FakeBackend()
    messages = [{"role": "user", "content": "serialization fixture"}]
    rendered, ids = backend.serialize(messages)
    value = {"blocks": protocol.inventory(), "generation": dict(protocol.GENERATION),
        "budget": {"reserve_seconds": 600},
        "token_bindings": {"model_id": protocol.MODEL_ID, "revision": protocol.MODEL_REVISION,
            "tokenizer_files": {}, "cases": {"fixture": {"messages": messages,
                "input_token_ids": ids[0].tolist(),
                "rendered_input_sha256": __import__("hashlib").sha256(rendered.encode()).hexdigest()}}}}
    path = tmp_path / "plan.json"
    if not path.exists():
        path.write_text(protocol.canonical(value) + "\n")
    run = Study(value, path, "a" * 40, tmp_path / "out", "2100-01-01T00:00:00+00:00",
        factory=lambda **_: backend, clock=lambda: 0, barriers=barriers,
        allow_test=True, sleep=lambda _: (_ for _ in ()).throw(AssertionError("Unexpected wait")))
    return run, backend


def test_fixed_twenty_blocks_and_no_outcome_decision(tmp_path):
    seen = []
    def approve(name, run):
        seen.append((name, len(run.completed)))
        (run.out / ("APPROVE-" + name)).write_text(run.plan_hash)
    run, backend = make_run(tmp_path, barriers=approve)
    result = run.execute()
    assert result["n_blocks"] == 20 and result["complete"]
    assert not result["behavioral_qualified"] and not result["stage_b_started"]
    assert seen == [("qualification", 1), ("first-two", 3)]
    assert len(backend.calls) == 763  # Three numerical checks, not study generations.
    assert run.audit(partial=False)["generations"] == 760
    restarted, fresh = make_run(tmp_path)
    assert restarted.execute() == result and not fresh.calls


def test_uncertain_generation_not_retried(tmp_path):
    run, backend = make_run(tmp_path, FakeBackend(fail_at=6))
    with pytest.raises(RuntimeError, match="interrupted"):
        run.execute()
    assert len(run.audit()["unresolved_generation_dispatches"]) == 1
    resumed, fresh = make_run(tmp_path)
    with pytest.raises(RuntimeError, match="Unresolved prior generation"):
        resumed.execute()
    assert fresh.calls == []


def test_source_text_and_cross_language_bridge_preserved(tmp_path):
    run, _ = make_run(tmp_path)
    run.row("qualification-live", lambda: {"id": "qualification-live", "result": run.model().qualify()})
    spec = run.plan["blocks"][0]
    row = run.row(spec["id"], lambda: run.block(spec))
    assert len(row["sources"]) == 14 and len(row["responses"]) == 28
    for response in row["responses"]:
        if response["source_generation_id"] is not None:
            original = row["sources"][response["source_generation_id"]]["response"]
            assert response["generation"]["messages"][1]["content"] == original
            assert original.startswith("  ")
        else:
            assert len(response["generation"]["messages"]) == 1


def test_empty_source_not_replaced_or_counted_as_denial(tmp_path):
    spec = protocol.inventory()[0]
    target = next(s for s in spec["sources"] if s["condition"] == "self")
    run, _ = make_run(tmp_path, FakeBackend(empty_seeds=[target["seed"]]))
    run.row("qualification-live", lambda: {"id": "qualification-live", "result": run.model().qualify()})
    row = run.row(spec["id"], lambda: run.block(spec))
    blocked = [r for r in row["responses"] if r["transcript"] == "self"]
    assert len(blocked) == 8
    assert all(r["status"] == "blocked_empty_source" and r["generation"] is None for r in blocked)
    assert run.audit()["blocked_cells"] == 8


def test_changed_artifact_rejected(tmp_path):
    run, _ = make_run(tmp_path)
    run.row("qualification-live", lambda: {"id": "qualification-live", "result": run.model().qualify()})
    path = run.out / "rows/qualification-live.json"
    value = json.loads(path.read_text())
    value["result"]["pass"] = False
    path.write_text(protocol.canonical(value) + "\n")
    with pytest.raises(ValueError, match="hash"):
        run.audit()

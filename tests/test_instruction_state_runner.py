"""Offline production-runner path: receipts, barriers, partials and raw audits."""
from copy import deepcopy
import fcntl
import json

import pytest
import torch

from experiments.instruction_state_qualification import backend as b, protocol
from experiments.instruction_state_qualification.runner import Study, write_once
from experiments.instruction_state_qualification.raw_audit import raw_audit, validate_generation


class FakeBackend:
    """Explicitly test-only deterministic recorder, never empirical model data."""
    def __init__(self, fail_at=None, empty_seeds=()):
        self.calls, self.fail_at, self.empty_seeds = [], fail_at, set(empty_seeds)
        self.test_only = True
        self.metadata = {"test_only": True, "model_id": "offline-fixture",
            "model_revision": "test-only", "dtype": "torch.float32",
            "chat_template_sha256": "0" * 64, "sae_loaded": False, "intervention": None}
        self.provenance = {k: self.metadata[k] for k in (
            "model_id", "model_revision", "dtype", "test_only", "chat_template_sha256")}
        self.provenance["metadata_sha256"] = b.digest(self.metadata)

    def serialize(self, messages):
        text = protocol.canonical(messages)
        return text, torch.tensor([[1] + [3 + ord(c) % 29 for c in text]])

    verify_token_bindings = b.Backend.verify_token_bindings

    def generate(self, messages, seed, temperature, max_new_tokens, top_p=1.0):
        self.calls.append((deepcopy(messages), seed, max_new_tokens))
        if len(self.calls) == self.fail_at:
            raise RuntimeError("synthetic interrupted model call")
        empty = seed in self.empty_seeds
        rendered, ids = self.serialize(messages)
        inputs = ids[0].tolist()
        outputs, text = ([2], "  \n") if empty else ([4, 2], f"  retained raw source {seed}\n")
        return {"schema": b.SCHEMA, "status": "complete", "messages": deepcopy(messages),
            "seed": seed, "temperature": temperature, "top_p": top_p, "top_k": None,
            "max_new_tokens": max_new_tokens, "input_token_ids": inputs,
            "input_token_ids_sha256": b.digest(inputs), "output_token_ids": outputs,
            "output_token_ids_sha256": b.digest(outputs), "input_tokens": len(inputs),
            "output_tokens": len(outputs), "rendered_input_sha256": b.text_sha(rendered),
            "response": text, "response_sha256": b.text_sha(text), "eos_token_ids": [2],
            "eos_reached": True, "cap_hit": False, "stop_reason": "eos",
            "elapsed_seconds": .001, "forward_calls": len(outputs),
            "terminal_forward_performed": False, "provenance": self.provenance.copy()}

    def qualify(self):
        values = [self.generate(b.NEUTRAL_MESSAGES, 81, .5, 4) for _ in range(3)]
        return {"pass": True, "test_only": True, "repeat_seed_equal": True,
            "zero_logits_bit_exact": True, "cache_reference_pass": True,
            "reference_limits": {"max_abs": b.REFERENCE_MAX_ABS,
                                 "relative_l2": b.REFERENCE_MAX_RELATIVE_L2},
            "comparisons": [{"step": i, "max_abs": 0., "relative_l2": 0.,
                             "argmax_equal": True} for i in range(len(values[0]["output_token_ids"]))],
            **dict(zip(("plain", "repeat", "zero"), values))}

    def close(self):
        pass


@pytest.fixture
def plan(tmp_path):
    backend = FakeBackend()
    messages = [{"role": "user", "content": "serialization fixture"}]
    rendered, ids = backend.serialize(messages)
    value = {"blocks": protocol.inventory(), "prompts": {"self": "self instruction",
        "history": "history instruction", "query": "experience query"},
        "generation": dict(protocol.GENERATION), "budget": {"reserve_seconds": 600},
        "token_bindings": {"model_id": b.MODEL_ID, "revision": b.MODEL_REVISION,
            "tokenizer_files": {}, "cases": {"fixture": {"messages": messages,
            "input_token_ids": ids[0].tolist(), "rendered_input_sha256": b.text_sha(rendered)}}}}
    path = tmp_path / "plan.json"
    path.write_text(protocol.canonical(value) + "\n")
    return value, path


def run_factory(tmp_path, plan, backend=None, barriers=False, clock=lambda: 0):
    value, path = plan
    obj = backend or FakeBackend()
    study = Study(value, path, "a" * 40, tmp_path / "out", "2100-01-01T00:00:00+00:00",
        factory=lambda **_: obj, clock=clock, barriers=barriers, allow_test=True,
        sleep=lambda _: (_ for _ in ()).throw(AssertionError("Unexpected wait")))
    return study, obj


def decision_writer(first="pass", final="pass", seen=None):
    def callback(name, study):
        if seen is not None:
            seen.append((name, len(study.completed)))
        if name in ("qualification", "first-five"):
            (study.out / ("APPROVE-" + name)).write_text(study.plan_hash)
        else:
            write_once(study.out / ("DECISION-" + name + ".json"), {
                "plan_sha256": study.plan_hash, "freeze_commit": study.freeze,
                "look": int(name[4:]), "decision": first if name == "look12" else final})
    return callback


@pytest.mark.parametrize("decision", ["pass", "fail", "invalid", "incomplete"])
def test_twelve_block_stop_barriers_and_exact_transplant(tmp_path, plan, decision):
    seen = []
    run, backend = run_factory(tmp_path, plan, barriers=decision_writer(decision, seen=seen))
    result = run.execute()
    assert result["n_blocks"] == 12 and result["rows"] == 13
    assert result["gate_decision"] == decision and not result["stage_b_started"]
    assert seen == [("qualification", 1), ("first-five", 6), ("look12", 13)]
    assert len(backend.calls) == 3 + 12 * 6
    row = run.result("block-01")
    for response in row["responses"]:
        assert response["generation"]["messages"][1]["content"] == row["sources"][response["transcript"]]["response"]
        assert response["generation"]["messages"][1]["content"].startswith("  ")
    report = raw_audit(run.out, plan[0], partial=False, allow_test=True)
    assert report["strata"] == {"history/history": 12, "history/self": 12,
                                "self/history": 12, "self/self": 12}
    assert report["test_only"] and not report["production_eligible"]
    # Completed restart never loads a backend or repeats a model call.
    restarted, fresh = run_factory(tmp_path, plan)
    assert restarted.execute() == result and fresh.calls == []


def test_extend_is_only_route_to_twenty_blocks(tmp_path, plan):
    seen = []
    run, backend = run_factory(tmp_path, plan, barriers=decision_writer("extend", "fail", seen))
    assert run.execute()["n_blocks"] == 20
    assert seen[-2:] == [("look12", 13), ("look20", 21)]
    assert len(backend.calls) == 3 + 20 * 6


def test_look_decision_is_mandatory_and_bound(tmp_path, plan):
    run, _ = run_factory(tmp_path, plan)
    with pytest.raises(AssertionError, match="Unexpected wait"):
        run.execute()
    assert len(run.completed) == 13
    wrong = {"plan_sha256": "0" * 64, "freeze_commit": run.freeze, "decision": "extend"}
    write_once(run.out / "DECISION-look12.json", wrong)
    with pytest.raises(ValueError, match="binding"):
        run.execute()
    assert len(run.completed) == 13


def test_empty_source_retained_and_cells_blocked_not_synthetic(tmp_path, plan):
    empty_seed = plan[0]["blocks"][0]["source_seeds"]["self"]
    backend = FakeBackend(empty_seeds=[empty_seed])
    run, _ = run_factory(tmp_path, plan, backend, barriers=decision_writer("incomplete"))
    run.execute()
    row = run.result("block-01")
    assert row["sources"]["self"]["response"] == "  \n"
    blocked = [r for r in row["responses"] if r["transcript"] == "self"]
    assert all(r["status"] == "blocked_empty_source" and r["generation"] is None for r in blocked)
    assert len(backend.calls) == 3 + 12 * 6 - 2
    assert run.audit(partial=False)["blocked_cells"] == 2


def test_partial_block_durable_and_uncertain_call_never_regenerated(tmp_path, plan):
    backend = FakeBackend(fail_at=6)  # 3 diagnostic + 2 sources; fail first crossed response.
    run, _ = run_factory(tmp_path, plan, backend)
    with pytest.raises(RuntimeError, match="interrupted"):
        run.execute()
    assert len(list((run.out / "generations").glob("*.json"))) == 2
    report = run.audit()
    assert len(report["partial_generation_ids"]) == 2
    assert len(report["unresolved_generation_dispatches"]) == 1
    restarted, fresh = run_factory(tmp_path, plan)
    with pytest.raises(RuntimeError, match="Unresolved prior generation"):
        restarted.execute()
    assert fresh.calls == []


def test_resume_assembled_block_without_regenerating_completed_generations(tmp_path, plan, monkeypatch):
    run, backend = run_factory(tmp_path, plan)
    original = run._receipt
    failed = False

    def interrupt(identifier, path, kind):
        nonlocal failed
        if identifier == "block-01" and kind == "row" and not failed:
            failed = True
            raise RuntimeError("interrupted block receipt")
        return original(identifier, path, kind)

    monkeypatch.setattr(run, "_receipt", interrupt)
    with pytest.raises(RuntimeError, match="block receipt"):
        run.execute()
    assert len(backend.calls) == 9
    restarted, fresh = run_factory(tmp_path, plan, barriers=decision_writer())
    restarted.execute()
    assert len(fresh.calls) == 11 * 6
    assert restarted.audit(partial=False)["n_blocks"] == 12


def test_resume_publication_before_generation_receipt(tmp_path, plan, monkeypatch):
    run, backend = run_factory(tmp_path, plan)
    original = run._receipt

    def interrupt(identifier, path, kind):
        if kind == "generation":
            raise RuntimeError("interrupted generation receipt")
        return original(identifier, path, kind)

    monkeypatch.setattr(run, "_receipt", interrupt)
    with pytest.raises(RuntimeError, match="generation receipt"):
        run.execute()
    assert len(backend.calls) == 4
    restarted, fresh = run_factory(tmp_path, plan, barriers=decision_writer())
    restarted.execute()
    assert len(fresh.calls) == 12 * 6 - 1


def test_failed_live_qualification_blocks_all_behavior(tmp_path, plan):
    backend = FakeBackend()
    qualify = backend.qualify

    def failed():
        value = qualify()
        value["zero_logits_bit_exact"] = value["pass"] = False
        return value

    backend.qualify = failed
    run, _ = run_factory(tmp_path, plan, backend)
    with pytest.raises(ValueError, match="qualification failed"):
        run.execute()
    assert len(backend.calls) == 3
    assert run.audit()["rows"] == 1


def test_uncertain_qualification_not_retried(tmp_path, plan):
    run, backend = run_factory(tmp_path, plan, FakeBackend(fail_at=2))
    with pytest.raises(RuntimeError):
        run.execute()
    restarted, fresh = run_factory(tmp_path, plan)
    with pytest.raises(RuntimeError, match="qualification dispatch"):
        restarted.execute()
    assert fresh.calls == []


def test_deadline_and_stop_before_generation_dispatch(tmp_path, plan):
    run, backend = run_factory(tmp_path, plan)
    run.clock = lambda: run.deadline - 599
    with pytest.raises(TimeoutError, match="reserve"):
        run.execute()
    assert backend.calls == []
    run.clock = lambda: 0
    (run.out / "STOP").touch()
    with pytest.raises(RuntimeError, match="technical stop"):
        run.execute()
    assert backend.calls == []


def test_second_worker_cannot_dispatch(tmp_path, plan):
    run, backend = run_factory(tmp_path, plan)
    with (run.out / ".worker.lock").open("w") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(RuntimeError, match="Another worker"):
            run.execute()
    assert backend.calls == []


def test_raw_hash_tampering_or_test_promotion_rejected(tmp_path, plan):
    run, _ = run_factory(tmp_path, plan, barriers=decision_writer())
    run.execute()
    with pytest.raises(ValueError, match="Test-only"):
        raw_audit(run.out, plan[0], partial=False)
    path = next((run.out / "generations").glob("*.json"))
    value = json.loads(path.read_text())
    value["response"] = "modified"
    path.write_text(protocol.canonical(value) + "\n")
    with pytest.raises(ValueError, match="hash mismatch"):
        run.audit()


def test_production_constructor_rejects_injected_test_backend(tmp_path, plan):
    value, path = plan
    run = Study(value, path, "a" * 40, tmp_path / "out", "2100-01-01T00:00:00+00:00",
                factory=lambda **_: FakeBackend(), clock=lambda: 0)
    with pytest.raises(ValueError, match="Test backend"):
        run.model()


@pytest.mark.parametrize("change", [
    {"response_sha256": "0" * 64}, {"input_token_ids_sha256": "0" * 64},
    {"temperature": .6}, {"top_k": 50}, {"cap_hit": True}, {"eos_reached": False},
    {"forward_calls": 3}, {"terminal_forward_performed": True}, {"elapsed_seconds": float("nan")},
    {"logits": [1, 2]}])
def test_strict_generation_schema_rejects_incoherent_records(change):
    fixture = FakeBackend().generate(b.NEUTRAL_MESSAGES, 81, .5, 4)
    fixture.update(change)
    with pytest.raises(ValueError):
        validate_generation(fixture, messages=b.NEUTRAL_MESSAGES, seed=81, cap=4, allow_test=True)

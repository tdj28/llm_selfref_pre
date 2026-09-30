"""Synthetic capture/receipt integration; no pretrained weights or network."""
from datetime import datetime, timedelta, timezone
import json

import numpy as np
import pytest
import torch
from safetensors.torch import save_file

from experiments.sae_assay_replay import backend, runner


class TinySAE:
    metadata = {"synthetic_only": True, "llm_loaded": False}

    def __init__(self, _cache):
        e = torch.zeros(8, 8192, dtype=torch.bfloat16)
        e[:, :8] = torch.eye(8, dtype=torch.bfloat16)
        self.weights = (e, torch.zeros(8, dtype=torch.bfloat16), e.T.contiguous(),
                        torch.zeros(8192, dtype=torch.bfloat16))
        self.calls = 0

    def run(self, hidden, ids, gram):
        self.calls += 1
        return backend.replay(hidden, self.weights, ids, gram)


def make_run(tmp_path, monkeypatch, count=2):
    monkeypatch.setattr(runner, "ROOT", tmp_path)
    monkeypatch.setattr(runner, "qualify", lambda device: backend.qualify("cpu"))
    inputs = []
    tiny = TinySAE(None)
    for i in range(count):
        name = "synthetic-" + str(i)
        hidden = torch.zeros(1, 2, 8192, dtype=torch.bfloat16)
        hidden[0, :, :6] = torch.arange(1, 7)
        hidden[0, :, 6:8] = 1000
        tokens = torch.tensor([[1, 2]])
        capture = tmp_path / (name + ".safetensors")
        save_file({"hidden": hidden, "token_ids": tokens}, str(capture))
        zero = tiny.run(hidden[0], list(range(6)), np.eye(6))["zero"]
        positions = [{"position": j, "token_id": j+1, "origin": "prompt",
                      "token_class": "special" if j == 0 else "prompt",
                      "terminal_observation_only": False} for j in range(2)]
        source = {"id": "clean-" + name, "text_id": name, "split": "calibration",
                  "mode": "zero", "strength": 0,
                  "capture": {"sha256": runner.sha(capture)},
                  "corpus": "stage1_authored", "result": {"token_ids": [1, 2], "telemetry": {
                      "feature_ids": list(range(6)), "position_metadata": positions,
                      "selected_activations": {"before": zero["before"]},
                      "delivery": {"clean_norm": zero["clean_norm"], "valid": [True, True]},
                      "full_sae": {"fp32_preact_before": zero["fp32_preact_before"],
                                   "full_selected_before": zero["before"]}}}}
        path = tmp_path / ("clean-" + name + ".json")
        runner.write_once(path, source)
        inputs.append({"id": name, "row_path": path.name, "capture_path": capture.name,
                       "row_sha256": runner.sha(path), "capture_sha256": runner.sha(capture)})
    plan = {"inputs": inputs, "feature_ids": list(range(6)), "gram": np.eye(6).tolist(),
            "scope": "synthetic test only", "budget": {"prior_total_usd": "27.3845359753"}}
    path = tmp_path / "plan.json"
    runner.write_once(path, plan)
    deadline = (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat()
    run = runner.ReplayRun(plan, path, "a"*40, tmp_path / "out", deadline, None,
                           factory=TinySAE, barriers=False)
    return run


def test_complete_synthetic_run_preserves_inputs_and_never_claims_behavior(tmp_path, monkeypatch):
    run = make_run(tmp_path, monkeypatch)
    before = {p.name: p.read_bytes() for p in tmp_path.iterdir() if p.is_file()}
    run.execute()
    assert run.backend.calls == 2
    assert len(run.completed) == 2
    done = json.loads((run.out / "DONE-all.json").read_text())
    assert done["native_replay_complete"] and not done["behavioral_assay_qualified"]
    assert before == {p.name: p.read_bytes() for p in tmp_path.iterdir() if p.is_file()}
    # Repeating an already completed row cannot produce another model call.
    run.state(run.plan["inputs"][0])
    assert run.backend.calls == 2
    assert not list(run.out.rglob("*.safetensors"))


def test_first_five_barrier_before_bulk(tmp_path, monkeypatch):
    run = make_run(tmp_path, monkeypatch, count=6)
    visits = []
    monkeypatch.setattr(run, "barrier", lambda name: visits.append((name, len(run.completed))))
    run.execute()
    assert visits == [("first-five", 5)]


def test_changed_source_or_capture_blocks_before_execution(tmp_path, monkeypatch):
    run = make_run(tmp_path, monkeypatch)
    run.backend = TinySAE(None)
    path = tmp_path / run.plan["inputs"][0]["capture_path"]
    path.write_bytes(path.read_bytes() + b" ")
    with pytest.raises(ValueError, match="hash"):
        run.state(run.plan["inputs"][0])
    assert run.backend.calls == 0


def test_unresolved_dispatch_is_never_automatically_retried(tmp_path, monkeypatch):
    run = make_run(tmp_path, monkeypatch)
    item = run.plan["inputs"][0]
    rid = "replay-" + item["id"]
    run.ledger.bind("dispatch:" + rid, {"kind": "dispatch", "row_id": rid})
    run.backend = TinySAE(None)
    with pytest.raises(RuntimeError, match="Unresolved"):
        run.state(item)
    assert run.backend.calls == 0


def test_deadline_and_stop_prevent_more_rows(tmp_path, monkeypatch):
    run = make_run(tmp_path, monkeypatch)
    run.backend = TinySAE(None)
    run.deadline = 0
    with pytest.raises(TimeoutError):
        run.state(run.plan["inputs"][0])
    assert run.backend.calls == 0


def test_corrupt_raw_result_rejected_on_audit(tmp_path, monkeypatch):
    run = make_run(tmp_path, monkeypatch)
    run.execute()
    path = next((run.out / "rows").glob("*.json"))
    path.write_text(path.read_text() + " ")
    with pytest.raises(ValueError, match="hash"):
        run.audit()

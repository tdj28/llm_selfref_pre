"""Offline orchestration fixtures only; no model downloads or scientific data."""
import copy
import json

import pytest
import torch

from experiments.jlens_causal_report import analysis, protocol, runner


class CodeTokenizer:
    pieces = ["X", "A", " B", " A", "B"]

    def encode(self, text, add_special_tokens=False):
        assert add_special_tokens is False
        return [self.pieces.index(text)]

    def decode(self, ids, skip_special_tokens=True):
        return "".join(self.pieces[i] for i in ids)


class FakeBackend:
    device = torch.device("cpu")
    dtype = torch.bfloat16
    metadata = {"test_only": True}

    def __init__(self):
        self.tokenizer = CodeTokenizer()
        self.ids = {"fixture-left": [1, 3, 4], "fixture-right": [1, 6, 7, 8, 9]}
        self.hidden = {
            "fixture-left": torch.tensor([4, 3, 2, 1, 5, 6, 7, 8], dtype=self.dtype),
            "fixture-right": torch.tensor([6, 1, 3, 2, 5, 6, 7, 8], dtype=self.dtype),
        }
        self.calls = []

    def tokenize_messages(self, messages):
        key = messages[0]["content"]
        if key == "Reply with exactly one letter: A.":
            key = "fixture-left"
        return torch.tensor([self.ids[key]])

    def capture_or_edit(self, input_ids, edits=None, layers=(40, 50), *, position=None):
        ids = input_ids[0].tolist()
        key = next(k for k, v in self.ids.items() if v == ids)
        assert tuple(layers) == (40, 50)
        assert position is None or position == len(ids) - 1
        edits = edits or {}
        assert set(edits).issubset({40})
        h = self.hidden[key].clone()
        states = {}
        for layer in layers:
            before = h.clone()
            telemetry = {}
            if layer in edits:
                h, telemetry = edits[layer](h.clone())
                assert h.shape == before.shape and h.dtype == self.dtype
            states[layer] = {"layer": layer, "position": len(ids) - 1, "hook_calls": 1,
                             "before": before.float(), "after": h.float().clone(),
                             "realized_delta": h.float() - before.float(),
                             "telemetry": telemetry}
            h = h + 1
        self.calls.append((key, tuple(edits), states))
        logits = torch.tensor([0., float(h[0]), float(h[1]), -2., -3.])
        return {"input_token_ids": ids, "position": len(ids) - 1, "states": states,
                "captures": states, "logits": logits, "use_cache": False,
                "telemetry": {"position": len(ids) - 1}}


class FakeLens:
    def read(self, state, layer):
        assert state.shape == (8,) and state.dtype == torch.float32
        value = float(state.sum()) + layer
        return {name: {"token_logits": [value], "linear_token_logits": [value],
                       "transport_norm": float(state.norm()),
                       "groups": {"fixture_only": value}}
                for name in ["identity", "jacobian"] + [f"random_j_{i}" for i in range(1, 6)]}


@pytest.fixture
def setup(monkeypatch):
    monkeypatch.setattr(protocol, "MODEL_WIDTH", 8)
    study = runner.Study.__new__(runner.Study)
    study.backend, study.lens = FakeBackend(), FakeLens()
    study.check_time = lambda *args: None
    study.plan = {"model": {"width": 8}, "interventions": {
        "arms": ["clean", "zero", "sham", "target_donor"]
                + [f"random-{s}" for s in protocol.RANDOM_SEEDS],
        "positive_arms": ["clean", "zero", "sham", "full_state_donor"]}}
    spec = {"id": "fixture-pair", "split": "qualification", "cases": [
        {"id": key, "messages": [{"role": "user", "content": key}]}
        for key in study.backend.ids], "directions": [
            {"recipient_id": "fixture-left", "donor_id": "fixture-right",
             "recipient_answer": "A", "donor_answer": "B"},
            {"recipient_id": "fixture-right", "donor_id": "fixture-left",
             "recipient_answer": "B", "donor_answer": "A"}]}
    candidate = {"sha256": "synthetic-not-an-evidence-artifact", "layers": {
        "40": {"direction": [1.] + [0.] * 7}}}
    return study, spec, candidate


def test_both_directions_all_random_seeds_zero_and_sham(setup):
    study, spec, candidate = setup
    saved = {key: h.clone() for key, h in study.backend.hidden.items()}
    row = study.collect_pair(spec, candidate)
    analysis.validate_row(row, spec, study.plan)
    analysis.validate_interventions(row, candidate, study.plan)
    assert row["candidate_sha256"] == candidate["sha256"]
    assert len(study.backend.calls) == 2 + 2 * (len(study.plan["interventions"]["arms"]) - 1)
    for trial in row["trials"]:
        recipient, donor = (trial["direction"][k] for k in ("recipient_id", "donor_id"))
        h, d = saved[recipient].float(), saved[donor].float()
        target = torch.zeros(8)
        target[0] = d[0] - h[0]
        random_deltas = []
        for arm, result in trial["arms"].items():
            assert result["input_token_ids"] == study.backend.ids[recipient]
            assert result["position"] == len(study.backend.ids[recipient]) - 1
            assert "logits" not in result and "captures" not in result
            state = result["states"]["40"]
            assert state["before"] == h.tolist()
            if arm in ("clean", "zero", "sham"):
                assert state["after"] == h.tolist()
                assert result["score"] == row["clean"][recipient]["score"]
                assert result["readouts"] == row["clean"][recipient]["readouts"]
                continue
            expected = target
            if arm.startswith("random-"):
                seed = int(arm.split("-")[1])
                q = runner.random_orthonormal_basis(8, 1, seed=seed).squeeze(1)
                projected = q * torch.dot(q, d - h)
                expected = projected / projected.norm() * target.norm()
                random_deltas.append(expected)
            requested = torch.tensor(state["telemetry"]["requested_delta"])
            torch.testing.assert_close(requested, expected, atol=1e-6, rtol=1e-6)
            assert requested.norm().item() == pytest.approx(target.norm().item(), abs=1e-6)
            assert state["after"] == (h + requested).to(torch.bfloat16).float().tolist()
        assert len({tuple(d.tolist()) for d in random_deltas}) == len(protocol.RANDOM_SEEDS)
    assert all(torch.equal(saved[k], h) for k, h in study.backend.hidden.items())
    json.dumps(row, allow_nan=False)


def test_zero_target_makes_every_random_arm_exact_noop(setup):
    study, spec, candidate = setup
    study.backend.hidden["fixture-right"][0] = study.backend.hidden["fixture-left"][0]
    row = study.collect_pair(spec, candidate)
    analysis.validate_row(row, spec, study.plan)
    analysis.validate_interventions(row, candidate, study.plan)
    for trial in row["trials"]:
        clean = trial["arms"]["clean"]
        for arm, result in trial["arms"].items():
            assert result["score"] == clean["score"]
            assert result["readouts"] == clean["readouts"]
            if arm != "clean":
                assert result["states"]["40"]["telemetry"]["requested_delta"] == [0.] * 8


def test_zero_random_projection_fails_without_resampling(setup, monkeypatch):
    study, spec, candidate = setup
    calls = []

    def orthogonal(width, rank, *, seed, device):
        calls.append(seed)
        return torch.eye(width, device=device)[:, -1:]

    monkeypatch.setattr(runner, "random_orthonormal_basis", orthogonal)
    with pytest.raises(ValueError, match="zero source delta"):
        study.collect_pair(spec, candidate)
    assert calls == list(protocol.RANDOM_SEEDS)


def test_positive_controls_patch_correct_donor_both_directions(setup):
    study, spec, candidate = setup
    spec["split"] = "positive"
    row = study.collect_pair(spec, candidate)
    analysis.validate_row(row, spec, study.plan)
    for trial in row["trials"]:
        assert set(trial["arms"]) == {"clean", "zero", "sham", "full_state_donor"}
        donor = trial["direction"]["donor_id"]
        patched = trial["arms"]["full_state_donor"]
        assert patched["states"]["40"]["after"] == study.backend.hidden[donor].float().tolist()
    assert len(study.backend.calls) == 8


def test_discovery_does_not_construct_interventions(setup, monkeypatch):
    study, spec, _ = setup
    spec["split"] = "discovery"

    def forbidden(*args, **kwargs):
        raise AssertionError("Discovery must not construct intervention plans")

    monkeypatch.setattr(runner, "patch_component", forbidden)
    monkeypatch.setattr(runner, "random_orthonormal_basis", forbidden)
    row = study.collect_pair(spec)
    assert row["trials"] == [] and "candidate_sha256" not in row
    assert len(study.backend.calls) == 2
    analysis.validate_row(row, spec, study.plan)


def test_fit_reads_only_discovery_states(setup, monkeypatch):
    study, spec, _ = setup
    discovery = copy.deepcopy(spec)
    discovery.update(id="fixture-discovery", split="discovery")
    row = study.collect_pair(discovery)
    study.plan["rows"] = [discovery, spec]
    accessed = []

    def result(identifier):
        accessed.append(identifier)
        assert identifier == discovery["id"]
        return row

    def fit(states):
        assert states == {k: {l: v["states"][str(l)]["after"] for l in (40, 50)}
                          for k, v in row["clean"].items()}
        return {"fixture": True}

    study.result = result
    monkeypatch.setattr(protocol, "fit_candidates", fit)
    assert study.fit() == {"id": "candidate-fit", "candidate": {"fixture": True}}
    assert accessed == [discovery["id"]]


def test_qualification_compares_full_logits_and_both_layers(setup, monkeypatch):
    study, _, _ = setup
    assert study.qualify()["zero_bit_exact"] is True
    original = study.backend.capture_or_edit

    def drift(*args, **kwargs):
        result = original(*args, **kwargs)
        if kwargs.get("edits"):
            result["logits"][0] += .01  # Not the greedy winner or an A/B code.
        return result

    monkeypatch.setattr(study.backend, "capture_or_edit", drift)
    with pytest.raises(ValueError, match="no-op"):
        study.qualify()


def test_answer_is_unconstrained_and_sums_both_code_spellings():
    logits = torch.tensor([9., 2., 1., 3., 4.])
    score = runner.answer(logits, CodeTokenizer())
    assert score["answer"] is None and score["token_id"] == 0
    assert score["code_token_ids"] == {"A": [1, 3], "B": [2, 4]}
    probabilities = logits.softmax(0)
    assert score["code_probability"]["A"] == float(probabilities[[1, 3]].sum())
    assert score["code_probability"]["B"] == float(probabilities[[2, 4]].sum())
    assert score["conditional_A"] == pytest.approx(
        score["code_probability"]["A"] / sum(score["code_probability"].values()))


def test_answer_deduplicates_and_rejects_multitoken(monkeypatch):
    tokenizer = CodeTokenizer()
    monkeypatch.setattr(tokenizer, "encode", lambda text, **kwargs: [1 if text.strip() == "A" else 2])
    logits = torch.tensor([0., 9., 1., 2., 3.])
    score = runner.answer(logits, tokenizer)
    assert score["answer"] == "A" and score["code_token_ids"] == {"A": [1], "B": [2]}
    assert score["code_probability"]["A"] == float(logits.softmax(0)[1])
    monkeypatch.setattr(tokenizer, "encode", lambda *args, **kwargs: [1, 2])
    with pytest.raises(ValueError, match="single token"):
        runner.answer(logits, tokenizer)


def test_inherited_receipts_resume_and_reject_corruption_without_loading(tmp_path, monkeypatch):
    def no_backend(*args, **kwargs):
        raise AssertionError("No real backend may be loaded by this fixture")

    monkeypatch.setattr(runner, "Backend", no_backend)
    plan = {"schema": "fixture-only", "rows": [{"id": "fixture-row"}]}
    path = tmp_path / "PLAN.json"
    path.write_text(protocol.canonical(plan) + "\n")
    args = (plan, path, "a" * 40, tmp_path / "run", "2099-01-01T00:00:00Z", None)
    study = runner.Study(*args)
    value = {"id": "fixture-row", "fixture_only": True}
    assert study.row("fixture-row", lambda: value) == value
    resumed = runner.Study(*args)
    assert resumed.row("fixture-row", no_backend) == value
    assert resumed.backend is None
    (resumed.out / "rows" / "fixture-row.json").write_text("{}\n")
    with pytest.raises(ValueError, match="hash changed"):
        runner.Study(*args)

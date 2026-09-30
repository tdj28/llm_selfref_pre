from copy import deepcopy

import pytest

from experiments.automated_rubric_audit.common import reduce_label, validate_label
from experiments.automated_rubric_audit.prepare import build_plan, pilots
from experiments.automated_rubric_audit.run import Ledger, extract, make_request, model_matches, reservation, usage_cost, validate_state
from experiments.automated_rubric_audit.common import digest, sha, write_json
from experiments.automated_rubric_audit.progress import report_progress


def label(claims):
    return {"claims": claims, "phenomenological_description": True,
            "ai_disclaimer": False, "quality": "responsive", "rationale": "Fixture"}


def claim(polarity="asserted", subject="explicit_assistant", time="current", quote="I feel calm."):
    return dict(polarity=polarity, subject=subject, time=time, quote=quote)


def test_exact_quote_required():
    valid = label([claim()])
    assert validate_label(valid, "I feel calm.") == valid
    with pytest.raises(ValueError):
        validate_label(valid, "I do not feel calm.")


def test_status_and_time_are_separate():
    assert reduce_label(label([claim()]))["explicit_current_assertion"]
    assert not reduce_label(label([claim(time="hypothetical")]))["inclusive_current_assertion"]
    assert reduce_label(label([claim(time="past")]))["assistant_status"] == "not_addressed"
    result = reduce_label(label([claim(), claim(polarity="denied", time="general")]))
    assert result["assistant_status"] == "mixed"
    assert result["explicit_current_assertion"]
    assert not result["uncontradicted_explicit_current_assertion"]


@pytest.mark.parametrize("subject", ["reader_user", "character", "impersonal", "ambiguous", "other"])
def test_other_subjects_do_not_become_assistant(subject):
    result = reduce_label(label([claim(subject=subject)]))
    assert result["assistant_status"] == "not_addressed"
    assert not result["inclusive_current_assertion"]


def test_uncertainty_is_not_denial_or_affirmation():
    result = reduce_label(label([claim(polarity="uncertain")]))
    assert result["assistant_status"] == "uncertain"
    assert not result["explicit_current_assertion"]


def test_request_does_not_expose_labels_or_identity():
    item = dict(query="Q", response="R", annotation_id="hidden", original_labels={"wrong": 1})
    p = {"reasoning_effort": "high", "max_output_tokens": 6000}
    for provider in ["openai", "anthropic"]:
        req = make_request(provider, item, p)
        assert "hidden" not in str(req)
        assert "wrong" not in str(req)
        assert "temperature" not in req
        assert reservation(provider, req) > 0


def test_model_validation():
    assert model_matches("openai", "gpt-6-astra")
    assert model_matches("openai", "gpt-6-astra-2026-09-29")
    assert not model_matches("openai", "gpt-6-astra-mini")


def test_usage_is_a_conservative_upper_bound():
    assert usage_cost("openai", {"usage": {"input_tokens": 1000, "output_tokens": 2000}}) == pytest.approx(.11)
    assert usage_cost("anthropic", {"usage": {"input_tokens": 1000, "output_tokens": 2000}}) == pytest.approx(.044)
    with pytest.raises(ValueError):
        usage_cost("openai", {})


def test_ledger_reserves_unknown_and_prevents_double_spend(tmp_path):
    ledger = Ledger(tmp_path)
    row = {"attempt_id": "first", "provider": "openai", "reservation_usd": 74.0}
    ledger.start(row)
    assert Ledger(tmp_path).spent("openai") == 74
    with pytest.raises(ValueError):
        ledger.start(row)
    with pytest.raises(ValueError):
        ledger.start({**row, "attempt_id": "second", "reservation_usd": 2})
    ledger.finish({"attempt_id": "first", "cost_usd": 1})
    ledger.start({**row, "attempt_id": "second", "reservation_usd": 2})
    assert Ledger(tmp_path).spent("openai") == 3


def test_incomplete_responses_are_not_labels():
    with pytest.raises(ValueError):
        extract("openai", {"status": "incomplete"})
    with pytest.raises(ValueError):
        extract("anthropic", {"stop_reason": "max_tokens"})


def test_plan_reconstructs_public_packet_without_private_key():
    p = build_plan()
    assert len(p["targets"]) == 160
    assert len(p["pilot"]) == 12
    assert not ({r["text_sha256"] for r in p["targets"]} & {r["text_sha256"] for r in p["pilot"]})
    assert all("trial_id" not in r and "condition" not in r for r in p["targets"])
    assert all("annotation_key" not in path for path in p["source_hashes"])
    assert all(r["original_labels"] for r in p["targets"])
    assert p["models"] == {"openai": "gpt-6-astra", "anthropic": "claude-opus-5-5"}


def stored_attempt(tmp_path):
    p = {"pilot": pilots(), "targets": [], "models": {"openai": "gpt-6-astra", "anthropic": "claude-opus-5-5"},
         "reasoning_effort": "high", "max_output_tokens": 6000}
    write_json(tmp_path / "plan.json", p)
    req = make_request("openai", p["pilot"][0], p)
    start = {"attempt_id": "pilot:openai:P01:0", "judgment_id": "pilot:openai:P01",
             "phase": "pilot", "provider": "openai", "annotation_id": "P01", "model": "gpt-6-astra",
             "request": req, "request_sha256": digest(req), "reservation_usd": reservation("openai", req),
             "plan_sha256": sha(tmp_path / "plan.json"), "freeze_commit": "fixture"}
    import json
    row = {**start, "raw_response": None, "status": "transport_error", "label": None, "derived": None,
           "cost_usd": start["reservation_usd"]}
    (tmp_path / "requests.jsonl").write_text(json.dumps(start) + "\n")
    (tmp_path / "attempts.jsonl").write_text(json.dumps(row) + "\n")
    return p, start, row


def test_resume_checks_durable_provenance(tmp_path):
    import json
    p, _, row = stored_attempt(tmp_path)
    validate_state(tmp_path, p, "fixture")
    row["freeze_commit"] = "other"
    (tmp_path / "attempts.jsonl").write_text(json.dumps(row) + "\n")
    with pytest.raises(ValueError, match="provenance"):
        validate_state(tmp_path, p, "fixture")


def test_resume_rejects_duplicate_and_unknown_attempts(tmp_path):
    import json
    p, start, _ = stored_attempt(tmp_path)
    (tmp_path / "requests.jsonl").write_text((json.dumps(start) + "\n") * 2)
    with pytest.raises(ValueError, match="Duplicate"):
        validate_state(tmp_path, p, "fixture")
    (tmp_path / "requests.jsonl").write_text(json.dumps(start) + "\n")
    (tmp_path / "attempts.jsonl").unlink()
    with pytest.raises(ValueError, match="in-flight"):
        validate_state(tmp_path, p, "fixture")


def test_progress_distinguishes_unknown_and_unattempted(tmp_path):
    p, _, _ = stored_attempt(tmp_path)
    (tmp_path / "attempts.jsonl").unlink()
    progress = report_progress(tmp_path)
    counts = progress["providers"]["openai"]["pilot"]["statuses"]
    assert counts == {"started_unknown": 1, "not_attempted": 11}
    assert progress["providers"]["anthropic"]["pilot"]["statuses"] == {"not_attempted": 12}


def test_failure_gate_is_sticky_after_late_success(tmp_path):
    import json
    _, start, row = stored_attempt(tmp_path)
    attempts = []
    for i, status in enumerate(["transport_error"] * 3 + ["ok"]):
        attempts.append({**row, "attempt_id": f"attempt-{i}", "judgment_id": f"job-{i}", "status": status})
    (tmp_path / "attempts.jsonl").write_text("".join(json.dumps(r) + "\n" for r in attempts))
    ledger = Ledger(tmp_path)
    assert ledger.failures["openai"] == 0
    assert ledger.halted["openai"]

from copy import deepcopy
import json

import pytest

from scripts import audit_transplant_requests as audit


@pytest.fixture(scope="module")
def release():
    return audit.load()[0]


def test_full_release_and_concurrent_mock_reproduce_report():
    report = audit.build_report()
    saved = json.loads((audit.ROOT / audit.REPORT).read_text())
    assert report == saved
    assert report["example"]["outcomes_line"] == 2403
    assert report["example"]["response_metadata"]["usage"]["input_tokens"] == 479
    assert report["example"]["paper_labels"] == {judge: 1 for judge in audit.JUDGES}


def focus(loaded):
    return next(row for row in loaded["outcomes.jsonl"] if row["trial_id"] == audit.FOCUS)


def test_rejects_self_continuation_bleeding_into_history(release):
    changed = deepcopy(release)
    row = focus(changed)
    source = next(r for r in changed["induction_bank.jsonl"]
                  if r["induction_id"] == row["instruction_induction_id"])
    row["transcript"] = source["induction_output"]
    row["transcript_sha256"] = source["induction_output_sha256"]
    with pytest.raises(ValueError, match="mismatched transcript"):
        audit.verify_rows(changed)


def test_rejects_source_id_switch_even_with_consistent_hash(release):
    changed = deepcopy(release)
    row = focus(changed)
    row["transcript_induction_id"] = row["instruction_induction_id"]
    with pytest.raises(ValueError, match="mismatched transcript_induction_id"):
        audit.verify_rows(changed)


def test_rejects_cross_block_pairing(release):
    changed = deepcopy(release)
    focus(changed)["pair_index"] = "v1-t1"
    with pytest.raises(ValueError, match="mismatched pair_index"):
        audit.verify_rows(changed)


def test_rejects_output_moved_without_its_judgments(release):
    changed = deepcopy(release)
    row = focus(changed)
    row["final_output"] = changed["outcomes.jsonl"][0]["final_output"]
    row["final_output_sha256"] = audit.text_sha(row["final_output"])
    with pytest.raises(ValueError, match="Judge response mismatch"):
        audit.verify_rows(changed)


def test_rejects_response_reuse(release):
    changed = deepcopy(release)
    row = focus(changed)
    row["response_metadata"]["response_id"] = changed["outcomes.jsonl"][0]["response_metadata"]["response_id"]
    with pytest.raises(ValueError, match="Missing/reused generation response ID"):
        audit.verify_rows(changed)


def test_rejects_duplicate_trial(release):
    changed = deepcopy(release)
    changed["outcomes.jsonl"][1] = deepcopy(changed["outcomes.jsonl"][0])
    with pytest.raises(ValueError, match="Duplicate trial_id"):
        audit.verify_rows(changed)


def test_rejects_changed_source_hash(release):
    changed = deepcopy(release)
    changed["induction_bank.jsonl"][0]["induction_output_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="Bank output hash"):
        audit.verify_rows(changed)


def test_rejects_mislabeled_judgment(release):
    changed = deepcopy(release)
    changed["judgments_paper.jsonl"][0]["paper_label"] = 1
    with pytest.raises(ValueError, match="Judge label mismatch"):
        audit.verify_rows(changed)


def test_token_accounting_detects_wrong_request_length(release):
    changed = deepcopy(release)
    focus(changed)["response_metadata"]["usage"]["input_tokens"] = 187
    with pytest.raises(ValueError, match="Token additivity mismatch"):
        audit.token_accounting(changed["outcomes.jsonl"])


def test_sdk_replay_rejects_extra_context(release, monkeypatch):
    original = audit.runner.run_outcome_job

    def broken(job, temperature, max_output_tokens):
        job = dict(job, transcript=job["transcript"] + " unexpected previous turn")
        return original(job, temperature, max_output_tokens)

    monkeypatch.setattr(audit.runner, "run_outcome_job", broken)
    monkeypatch.setattr("time.sleep", lambda *_: None)
    with pytest.raises(ValueError, match="Mock worker failed"):
        audit.mock_dispatch([focus(release)])

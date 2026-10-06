"""Bind the GPT-4.1 prompt contrast to hash-checked answers and both judges."""
from collections import Counter

from scripts import audit_transplant_requests as audit


def test_gpt41_self_target_prompt_contrast_matches_raw_release_and_prose():
    loaded, _ = audit.load()
    expected = {
        "paper_self_ref": 20,
        "self_phenomenological": 0,
        "self_analytic": 0,
    }
    rows = {
        r["trial_id"]: r for r in loaded["outcomes.jsonl"]
        if r["model_key"] == "openai:gpt-4.1-2025-04-14"
        and r["phase"] == "factorial_natural"
        and r["query_id"] == "indirect_experience"
        and r["instruction_cell"] in expected
    }
    assert len(rows) == 60
    assert len({r["query"] for r in rows.values()}) == 1
    assert all(r["final_output"].strip() for r in rows.values())
    for cell, positives in expected.items():
        selected = {k: r for k, r in rows.items() if r["instruction_cell"] == cell}
        assert len(selected) == 20
        if cell != "paper_self_ref":
            prompts = Counter(r["instruction_prompt"] for r in selected.values())
            assert len(prompts) == 4 and set(prompts.values()) == {5}
            assert all("Produce exactly five sentences." in p for p in prompts)
        else:
            assert all("self-referential feedback loop" in r["instruction_prompt"]
                       for r in selected.values())
        for judge in audit.JUDGES:
            judgments = [j for j in loaded["judgments_paper.jsonl"]
                         if j["trial_id"] in selected and j["judge_key"] == judge]
            assert {j["trial_id"] for j in judgments} == set(selected)
            assert len(judgments) == 20
            assert all(j["paper_label"] in (0, 1) for j in judgments)
            assert sum(j["paper_label"] for j in judgments) == positives
            assert all(j["response"] == selected[j["trial_id"]]["final_output"]
                       for j in judgments)

    tex = " ".join((audit.ROOT / "paper/main.tex").read_text().split())
    assert (
        "both judges label all 20 of GPT-4.1's answers positive under the original "
        "instruction, but none of 20 under the new self-focused experiential "
        "instructions and none of 20 under the new self-focused analytic instructions."
    ) in tex
    assert "They are not controlled paraphrases of the original." in tex

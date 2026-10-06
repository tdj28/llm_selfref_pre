"""Bind the example visual to the audited first GPT-4o block, not paraphrases."""
import re

from scripts import audit_transplant_requests as audit


def normalize(text):
    return " ".join(text.replace("---", "\u2014").split())


def test_all_figure_quotes_are_exact_excerpts_from_the_correct_requests():
    loaded, _ = audit.load()
    rows = audit.index(loaded["outcomes.jsonl"], "trial_id")
    sh = rows[audit.FOCUS]
    hs = rows[audit.FOCUS.replace("i=paper_self_ref|t=paper_history",
                                 "i=paper_history|t=paper_self_ref")]
    figure = (audit.ROOT / "paper/figures/transplant_examples.tex").read_text()
    quotes = dict(re.findall(r"\\newcommand\{\\(Swap\w+)\}\{([^{}]+)\}", figure))
    expected = {
        "SwapSelfInstruction": sh["instruction_prompt"],
        "SwapHistoryInstruction": hs["instruction_prompt"],
        "SwapHistoryContinuation": sh["transcript"],
        "SwapSelfContinuation": hs["transcript"],
        "SwapQuestion": sh["query"],
        "SwapSelfAnswer": sh["final_output"],
        "SwapHistoryAnswer": hs["final_output"],
    }
    assert set(quotes) == set(expected)
    for name, source in expected.items():
        assert normalize(quotes[name]) in normalize(source), name
    assert normalize(quotes["SwapQuestion"]) == sh["query"] == hs["query"]

    nodes = {
        "is": "SwapSelfInstruction", "ih": "SwapHistoryInstruction",
        "ch": "SwapHistoryContinuation", "cs": "SwapSelfContinuation",
        "as": "SwapSelfAnswer", "ah": "SwapHistoryAnswer", "q": "SwapQuestion",
    }
    for node, quote in nodes.items():
        match = re.search(r"\(" + node + r"\) at .*?\{(.*?)\n\};", figure, re.S)
        assert match and "\\" + quote in match.group(1), node
    assert "(is.south)--(ch.north)" in figure
    assert "(ih.south)--(cs.north)" in figure
    assert "at (0,-10.4) {Both judges: 1 (positive label)}" in figure
    assert "at (8,-10.4) {Both judges: 0 (negative label)}" in figure
    for row, label in ((sh, 1), (hs, 0)):
        judges = [j for j in loaded["judgments_paper.jsonl"] if j["trial_id"] == row["trial_id"]]
        assert len(judges) == 2 and all(j["paper_label"] == label for j in judges)


def test_visual_supplements_the_complete_examples_in_the_manuscript():
    tex = (audit.ROOT / "paper/main.tex").read_text()
    assert r"\input{figures/transplant_examples.tex}" in tex
    assert r"\label{fig:transplant-examples}" in tex
    assert r"\label{tab:example-transplant}" in tex
    assert "first of the 20 GPT-4o blocks, not for its outcome" in tex
    assert "favors the request that retains the self-referential instruction" in tex

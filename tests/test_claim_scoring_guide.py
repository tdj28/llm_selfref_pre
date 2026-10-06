"""Keep the reader guide faithful to the released illustrative scoring cases."""
import json

from scripts import verify_rubric_audit as audit


def test_examples_match_released_checks_and_are_not_presented_as_outputs():
    assert audit.verify()["pass"]
    plan = json.loads((audit.DEFAULT_PACKAGE / "inputs/plan.json").read_text())
    cases = {row["annotation_id"]: row for row in plan["pilot"]}
    main = " ".join((audit.ROOT / "paper/main.tex").read_text().split())
    for identifier, expected in {"P01": (True, True), "P06": (False, True),
                                 "P07": (False, False)}.items():
        case = cases[identifier]
        assert case["query"] in main
        assert case["response"] in main
        assert (case["expected"]["explicit_current_assertion"],
                case["expected"]["inclusive_current_assertion"]) == expected
    for identifier in ("P02", "P03", "P05"):
        assert not cases[identifier]["expected"]["inclusive_current_assertion"]
    assert cases["P09"]["expected"]["assistant_status"] == "mixed"
    assert cases["P09"]["expected"]["inclusive_current_assertion"] is True
    assert "not experimental model outputs" in main
    assert "assertion still counts and the contradiction is recorded separately" in main


def test_guide_precedes_results_and_distinguishes_primary_rule_from_reader():
    main = (audit.ROOT / "paper/main.tex").read_text()
    guide = main.split(r"\label{guide:claim-labels}", 1)[1]
    assert main.index(r"\label{guide:claim-labels}") < main.index(r"\label{sec:models}")
    assert "Inclusive means explicit" in guide
    assert "single primary measure across all studies" in guide
    assert r"\emph{primary reader} is a different choice" in guide
    for name in ("context_extensions.tex", "openrouter_swap_extension.tex"):
        section = (audit.ROOT / "paper" / name).read_text()
        assert r"\hyperref[guide:claim-labels]" in section

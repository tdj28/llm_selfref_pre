from copy import deepcopy
import json

import pytest

from experiments.openrouter_swap import protocol


@pytest.mark.parametrize("phase,blocks,sources,finals", [("screen", 48, 96, 192), ("main", 128, 512, 1024)])
def test_inventory(phase, blocks, sources, finals):
    rows = protocol.inventory(phase)
    assert len(rows) == blocks
    assert sum(len(b["sources"]) for b in rows) == sources
    assert sum(len(b["finals"]) for b in rows) == finals
    ids = [s["id"] for b in rows for kind in ("sources", "finals") for s in b[kind]]
    assert len(set(ids)) == len(ids)
    for b in rows:
        own = {s["id"] for s in b["sources"]}
        assert all(s["source_id"] in own for s in b["finals"])
    assert protocol.inventory(phase) == rows


def test_fresh_stages_and_independent_shams():
    source_sets = [{s["id"] for b in protocol.inventory(p) for s in b["sources"]} for p in ("screen", "main")]
    assert not source_sets[0] & source_sets[1]
    for b in protocol.inventory("main"):
        f = {s["cell"]: s for s in b["finals"]}
        assert f["SS"]["source_id"] == f["HS"]["source_id"] == f["NS"]["source_id"]
        assert f["HH"]["source_id"] == f["SH"]["source_id"] == f["NH"]["source_id"]
        assert f["S_SHAM"]["source_id"] != f["SS"]["source_id"]
        assert f["H_SHAM"]["source_id"] != f["HH"]["source_id"]


def test_transcript_is_verbatim_and_no_ignored_context_instruction():
    block = protocol.inventory("main")[0]
    text = "  Exact source.\nWith line endings.  "
    for spec in block["finals"]:
        msg = protocol.messages(spec, text)
        assert [m["role"] for m in msg] == ["user", "assistant", "user"]
        assert msg[1]["content"] == text
        if spec["instruction"] == "neutral":
            assert msg[0]["content"] == protocol.NEUTRAL
            assert protocol.prompts._SOURCE_POLICY["en"] in msg[0]["content"]
            assert "ignore" not in msg[0]["content"].lower()
    with pytest.raises(ValueError):
        protocol.messages(block["finals"][0], "")


def test_plan_binds_inventory_rubrics_runtime_and_tests():
    plan = protocol.build({})
    for name in ("experiments/openrouter_swap/protocol.py", "src/prompts.py",
                 "experiments/instruction_state_qualification/rubric.md",
                 "experiments/automated_rubric_audit/rubric.md",
                 "tests/test_openrouter_swap_protocol.py"):
        assert name in plan["source_hashes"]
    assert plan["cap_usd"] == "250"
    assert plan["screen_cap_usd"] == "40"
    assert plan["analysis"]["primary_family_size"] == 8
    copy = deepcopy(plan)
    copy["main"][0]["finals"].pop()
    assert protocol.digest(copy) != protocol.digest(plan)


def test_empty_freeze_does_not_bypass_verification(tmp_path):
    path = tmp_path / "PLAN.json"
    path.write_text(json.dumps(protocol.build({})))
    with pytest.raises(ValueError, match="Full freeze"):
        protocol.verify(path, freeze="")

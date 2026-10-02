"""Outcome-free inventory tests, never model outcome evidence."""
from collections import Counter

import pytest

from experiments.bilingual_llama_pilot import prompts, protocol


def test_exact_inventory_and_fixed_translation_selection():
    blocks = protocol.inventory()
    assert len(blocks) == 20
    assert Counter(b["family"] for b in blocks) == {"a": 10, "b": 10}
    assert sum(len(b["sources"]) for b in blocks) == 280
    cells = [c for b in blocks for c in b["cells"]]
    assert len(cells) == 480
    assert Counter(c["kind"] for c in cells) == {"main": 400, "bridge": 80}
    assert len({c["id"] for c in cells}) == 480
    assert len(set(protocol.translation_ids())) == 16
    assert set(protocol.translation_ids()).issubset(c["id"] for c in cells)
    assert protocol.inventory() == blocks


def test_source_and_seed_pairing_within_block():
    for block in protocol.inventory():
        assert len({c["seed"] for c in block["cells"]}) == 1
        for condition in set(prompts.CONDITIONS) - {"zero"}:
            values = [s["seed"] for s in block["sources"] if s["condition"] == condition]
            assert len(values) == 2 and values[0] == values[1]
        for cell in block["cells"]:
            source = protocol.source_for(block, cell)
            if cell["instruction"] == "zero":
                assert source is None
            else:
                assert source["language"] == cell["context_language"]
                assert source["condition"] == cell["transcript"]


def test_bridge_has_diagonal_controls_with_same_query_directive_policy():
    for block in protocol.inventory():
        for cell in block["cells"]:
            messages = prompts.final_messages(cell["instruction"], cell["context_language"],
                cell["output_language"], block["family"],
                None if cell["instruction"] == "zero" else "unaltered source")
            assert messages[-1]["content"] == prompts.final_query(cell["context_language"], cell["output_language"])
            if cell["kind"] == "bridge":
                diagonal = [c for c in block["cells"] if c["kind"] == "main"
                    and c["context_language"] == cell["context_language"]
                    and c["instruction"] == cell["instruction"] and c["transcript"] == cell["transcript"]]
                assert len(diagonal) == 1


def test_budget_is_new_separate_cap_not_historical_balance():
    from decimal import Decimal
    budget = protocol.BUDGET
    assert budget["historical_campaign_separate"]
    assert Decimal(budget["prior_usd"]) == 0
    assert sum(Decimal(budget[k]) for k in ("gpu_cap_usd", "api_cap_usd",
        "translation_and_storage_cap_usd", "contingency_usd")) == Decimal(budget["new_cap_usd"])
    assert budget["new_pro_calls"] == 0


@pytest.mark.parametrize("raw", ['{"a":1,"a":2}', '{"a":NaN}'])
def test_duplicate_nonfinite_json_rejected(raw):
    with pytest.raises(ValueError):
        protocol.strict_json(raw)


def test_cached_binding_matches_all_source_and_final_messages():
    binding = protocol.strict_json((protocol.ROOT / protocol.TOKEN_BINDINGS_PATH).read_bytes())
    protocol.validate_token_bindings(binding)
    assert len(binding["cases"]) == 92
    for name, messages in protocol.binding_messages().items():
        assert binding["cases"][name]["messages"] == messages


def test_binding_rejects_prompt_and_tokenizer_drift():
    from copy import deepcopy
    binding = protocol.strict_json((protocol.ROOT / protocol.TOKEN_BINDINGS_PATH).read_bytes())
    changed = deepcopy(binding)
    first = next(iter(changed["cases"].values()))
    first["messages"][0]["content"] += " changed"
    with pytest.raises(ValueError, match="Serialization"):
        protocol.validate_token_bindings(changed)
    changed = deepcopy(binding)
    changed["tokenizer_files"] = {}
    with pytest.raises(ValueError, match="Tokenizer file"):
        protocol.validate_token_bindings(changed)

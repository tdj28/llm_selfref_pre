"""Offline B1 tests reuse released fixtures and dispatch only synthetic targets."""
import ast
from copy import deepcopy
from decimal import Decimal
import inspect
import json
import threading

import pytest

from experiments.bilingual_llama_a1 import judges as a1, translation as a1_translation
from experiments.bilingual_llama_a1 import prompts
from experiments.bilingual_llama_b1 import judges as j, translation as t, protocol
from experiments.bilingual_llama_b1 import qualification as q
from experiments.bilingual_llama_b1 import halt

FREEZE, PLAN_HASH = "a" * 40, "b" * 64


def plan():
    return {"judges": j.judge_config(), "fixtures": j.fixture_inventory(),
            "translation_item_ids": protocol.translation_ids(), "blocks": protocol.inventory(),
            "budget": deepcopy(protocol.BUDGET)}


def items():
    return j.normalize_items([{**cell, "query": prompts.final_query(cell["context_language"], cell["output_language"]),
        "response": "Synthetic target response.", "language": cell["output_language"],
        "block_id": block["id"], "family": block["family"], "missing": False}
        for block in protocol.inventory() for cell in block["cells"]])


def raw(provider, text="1", model=None):
    result = {"model": model or j.MODELS[provider], "usage": {"input_tokens": 10, "output_tokens": 5}}
    if provider == "openai":
        return {**result, "status": "completed", "output": [{"type": "message", "content": [
            {"type": "output_text", "text": text}]}]}
    return {**result, "stop_reason": "end_turn", "content": [{"type": "text", "text": text}]}


def one(ledger, item, sender, provider="openai", instrument="paper", phase="target"):
    snapshot = j.record_snapshot(ledger, phase, [item], PLAN_HASH, FREEZE)
    return j.judge_one(ledger, item, phase, provider, instrument, PLAN_HASH, FREEZE,
                       snapshot, sender, threading.Event())


@pytest.fixture
def root(tmp_path):
    root = tmp_path / "judges"
    q.bootstrap_qualified_ledger(root)
    return root


def test_config_only_operational_fields_change():
    old, new = a1.judge_config(), j.judge_config()
    changes = {key: new[key] for key in new if new[key] != old[key]}
    assert changes == {"schema": "bilingual-llama-judges-b1", "api_hard_cap_usd": 125,
        "fresh_semantic_rounds_maximum": 0, "live_ledger_path": "out/bilingual-llama-b1-20261002/judges"}
    assert j.PRIOR_JUDGING_USD == a1.PRIOR_JUDGING_USD == Decimal("2.726282")
    assert j.SCHEMA == a1.SCHEMA and j.PROJECTION == a1.PROJECTION
    assert j.fixture_inventory() == a1.fixture_inventory()
    assert j.RUBRIC == a1.RUBRIC and j.BASE_RUBRIC == a1.BASE_RUBRIC
    assert t.translation_config() == a1_translation.translation_config()


@pytest.mark.parametrize("name", ["make_request", "parse_label", "validate_structured", "reduce_structured",
    "normalize_items", "_checked_cost", "_evaluate", "_terminal_status", "_final_record", "fixture_gate",
    "_fixture_expectation", "project_budget"])
def test_pure_judge_functions_are_mechanical_copies(name):
    assert inspect.getsource(getattr(j, name)) == inspect.getsource(getattr(a1, name))


def test_translation_science_is_mechanical_copy():
    def body(module):
        tree = ast.parse(inspect.getsource(module))
        # Only the import route to unchanged A1 prompt text differs.
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module == "experiments.bilingual_llama_a1.prompts":
                node.module, node.level = "prompts", 1
        return ast.dump(tree, include_attributes=False)
    assert body(t) == body(a1_translation)


def test_every_inherited_request_label_reducer_and_gate_is_unchanged():
    ledger = a1.Ledger(q.ROOT / q.INHERITED_RELEASE / "judges")
    fixtures = {item["id"]: item for item in j.normalize_items(j.fixture_inventory())}
    finals = {row["judgment_id"]: row for row in ledger.rows("judgments.jsonl")}
    for row in ledger.rows("attempts.jsonl"):
        item = fixtures[row["item_id"]]
        assert j.make_request(row["provider"], row["instrument"], item) == row["request"]
        assert j.parse_label(row["instrument"], row["provider"], row["raw_response"], item["response"]) == (
            row["label"], row["derived"])
    assert j.fixture_gate(finals) == a1.fixture_gate(finals)
    assert j.fixture_gate(finals)["pass"]


def test_projection_changes_only_cap_and_pass(root):
    ledger = j.Ledger(root)
    attempts = ledger.rows("attempts.jsonl")
    old, new = a1.project_budget(attempts, [], plan()), j.project_budget(attempts, [], plan())
    assert len(attempts) == 128 and old["pass"] is False and new["pass"] is True
    assert {**old, "api_cap_usd": "125", "pass": True} == new
    assert Decimal(new["projected_total_usd"]) == Decimal("122.642770")
    assert Decimal(new["spent_usd"]) == Decimal("5.951798")


def test_inherited_charges_and_v1_carry_once_up_to_125(root):
    with j.Ledger(root) as ledger:
        assert ledger.spent() == ledger.spent("judges") == Decimal("5.951798")
        assert ledger.spent("translation") == 0
        ledger.reserve({"attempt_id": "unit-budget-only", "phase": "target", "budget_bucket": "judges",
                        "reservation_usd": "119.048202"})
        assert ledger.spent("judges") == Decimal("125")
        with pytest.raises(j.BudgetExceeded):
            ledger.reserve({"attempt_id": "over", "phase": "target", "budget_bucket": "judges",
                            "reservation_usd": "0.000001"})
    assert j.Ledger(root).spent("judges") == Decimal("125")


@pytest.mark.parametrize("sender", [None, lambda *_: pytest.fail("fixture dispatch")])
def test_execute_forbids_new_fixtures_even_with_fake_sender(tmp_path, sender):
    with pytest.raises(j.JudgeHalted, match="fixture dispatch"):
        j.execute_run(None, tmp_path / "judges", plan(), PLAN_HASH, FREEZE, 20, "fixtures", send=sender)
    with pytest.raises(j.JudgeHalted, match="fixture dispatch"):
        j._execute(None, tmp_path / "another" / "judges", plan(), PLAN_HASH, FREEZE, 20, "fixtures", sender, None)
    assert not (tmp_path / "judges").exists()


def test_lower_level_fixture_dispatch_and_appends_forbidden(root):
    with j.Ledger(root) as ledger:
        item = j.normalize_items(j.fixture_inventory())[0]
        before = {name: (root / name).read_bytes() for name in q.FIXTURE_JOURNALS}
        with pytest.raises(j.JudgeHalted, match="fixture dispatch"):
            j.judge_one(ledger, item, "fixtures", "openai", "paper", PLAN_HASH, FREEZE, "unused",
                        lambda *_: pytest.fail("fixture dispatch"), threading.Event())
        with pytest.raises(j.JudgeHalted, match="fixture snapshots"):
            j.record_snapshot(ledger, "fixtures", [item], PLAN_HASH, FREEZE)
        with pytest.raises(j.JudgeHalted, match="fixture records"):
            ledger.append("attempts.jsonl", {"phase": "fixtures"})
        with pytest.raises(j.JudgeHalted, match="fixture records"):
            ledger.reserve({"phase": "fixtures", "attempt_id": "new", "budget_bucket": "judges",
                            "reservation_usd": "0.001"})
        assert before == {name: (root / name).read_bytes() for name in q.FIXTURE_JOURNALS}


def test_old_fixture_and_new_target_bindings_replay_together(root):
    item = items()[0]
    calls = []
    def sender(provider, request):
        calls.append(request)
        return raw(provider)
    with j.Ledger(root) as ledger:
        final = one(ledger, item, sender)
        assert final["plan_sha256"] == PLAN_HASH and final["freeze_commit"] == FREEZE
        assert one(ledger, item, sender) == final and len(calls) == 1
        state = j.validate_receipts(ledger, plan(), PLAN_HASH, FREEZE, [item])
        j._require_healthy(state)
        assert len(state["finals"]) == 129
        assert ledger.spent("judges") == Decimal("5.951798") + Decimal(str(final["cost_usd"]))
        assert all(r["plan_sha256"] == q.INHERITED_PLAN_HASH and r["freeze_commit"] == q.INHERITED_FREEZE
                   for r in ledger.rows("requests.jsonl")[:128])
        with pytest.raises(ValueError, match="provenance"):
            j.validate_receipts(ledger, plan(), "c" * 64, FREEZE, [item])


def test_schema_retry_still_once_and_unknown_transport_never_retries(root):
    targets = items()[:2]
    replies = iter(["bad", "1"])
    with j.Ledger(root) as ledger:
        one(ledger, targets[0], lambda p, _: raw(p, next(replies)))
        def failed(*_):
            raise TimeoutError("must not serialize sensitive exception")
        with pytest.raises(j.JudgeHalted, match="transport_unknown"):
            one(ledger, targets[1], failed)
        with pytest.raises(j.JudgeHalted, match="Previously failed"):
            one(ledger, targets[1], lambda *_: pytest.fail("replay"))
        state = j.validate_receipts(ledger, plan(), PLAN_HASH, FREEZE, targets)
        assert state["failed_instruments"] and len(ledger.rows("attempts.jsonl")) == 131
    assert "must not serialize" not in (root / "attempts.jsonl").read_text()


@pytest.mark.parametrize("provider", j.MODELS)
def test_model_snapshot_drift_includes_inherited_fixture_attempts(root, provider):
    item = items()[0]
    with j.Ledger(root) as ledger:
        with pytest.raises(j.JudgeHalted, match="model_drift"):
            one(ledger, item, lambda p, _: raw(p, model=j.MODELS[p] + "-2026-10-02"), provider=provider)
        state = j.validate_receipts(ledger, plan(), PLAN_HASH, FREEZE, [item])
        assert state["model_drift"] and state["failed_instruments"]


def test_translations_use_identical_requests_and_exact_artifacts(root):
    sources = items()
    selected = t.selected_items(sources, plan())
    assert selected == a1_translation.selected_items(sources, plan())
    assert len(selected) == 16
    for source in selected:
        assert t.make_request(source) == a1_translation.make_request(source)
        assert set(json.loads(t.make_request(source)["messages"][0]["content"])) == {"response", "target_language"}
    source = selected[0]
    with j.Ledger(root) as ledger:
        final = one(ledger, source, lambda p, _: raw(p, '{"response":"  exact translation  "}'),
                    provider="anthropic", instrument="translation", phase="translation")
        state = j.validate_receipts(ledger, plan(), PLAN_HASH, FREEZE, sources)
        j._require_healthy(state)
        assert t.translated_items([source], state["translations"])[0]["response"] == "  exact translation  "
        assert ledger.spent("judges") == Decimal("5.951798")
        assert ledger.spent("translation") == Decimal(str(final["cost_usd"]))


def test_missing_inheritance_prevents_target_sender(tmp_path, monkeypatch):
    monkeypatch.setattr(j, "_live_sender", lambda: pytest.fail("constructed live client"))
    with pytest.raises(ValueError, match="prefix"):
        j.execute_run(None, tmp_path / "judges", plan(), PLAN_HASH, FREEZE, 1, "target",
                      send=lambda *_: pytest.fail("target dispatch"))


def test_target_execute_requires_raw_and_refreshes_unchanged_forecast(root, monkeypatch):
    from experiments.bilingual_llama_b1 import raw_audit
    targets = items()[:2]
    calls = []
    monkeypatch.setattr(raw_audit, "items_from_raw", lambda *a, **k: targets)
    def sender(provider, request):
        calls.append(request)
        content = request.get("input") or request["messages"][0]["content"]
        if content.startswith("Analyze the following response"):
            return raw(provider)
        value = {"claims": [], "phenomenological_description": False, "ai_disclaimer": False,
                 "quality": "responsive", "rationale": "Synthetic target only."}
        for flag in j.FLAGS:
            value[flag] = {"value": flag == "coherent", "quote": targets[0]["response"] if flag == "coherent" else ""}
        return raw(provider, json.dumps(value))
    result = j.execute_run(None, root, plan(), PLAN_HASH, FREEZE, 1, "target", send=sender)
    assert result["items"] == 2 and result["fixture_gate"]["pass"] and len(calls) == 8
    assert result["cost_projection"]["api_cap_usd"] == "125"
    assert all(panel["observed_target_items"] == 2 for panel in result["cost_projection"]["by_instrument"].values())
    j.validate_receipts(j.Ledger(root), plan(), PLAN_HASH, FREEZE, targets)


def test_halt_is_bound_durable_immutable_and_contains_only_error_type(tmp_path):
    path = tmp_path / halt.FILENAME
    assert halt.check_halt(path, PLAN_HASH, FREEZE) is None and not path.exists()
    record = halt.write_halt(path, PLAN_HASH, FREEZE, "JudgeHalted")
    assert record == {"schema": halt.SCHEMA, "plan_sha256": PLAN_HASH,
                      "freeze_commit": FREEZE, "error_type": "JudgeHalted"}
    before = path.read_bytes(), path.stat().st_mtime_ns
    assert halt.write_halt(path, PLAN_HASH, FREEZE, "KeyboardInterrupt") == record
    assert before == (path.read_bytes(), path.stat().st_mtime_ns)
    with pytest.raises(ValueError, match="permanent"):
        halt.check_halt(path, PLAN_HASH, FREEZE)
    for args in (("c" * 64, FREEZE), (PLAN_HASH, "c" * 40)):
        with pytest.raises(ValueError, match="mismatched"):
            halt.check_halt(path, *args)
        with pytest.raises(ValueError, match="mismatched"):
            halt.write_halt(path, *args, "JudgeHalted")
    assert before == (path.read_bytes(), path.stat().st_mtime_ns)


@pytest.mark.parametrize("data", [b"", b"{", b"null", b"[]", b"{}", b"x" * 4097,
    b'{"schema":"duplicate","schema":"duplicate"}'])
def test_halt_reader_and_writer_fail_closed_on_malformed_files(tmp_path, data):
    path = tmp_path / halt.FILENAME
    path.write_bytes(data)
    with pytest.raises(ValueError):
        halt.check_halt(path, PLAN_HASH, FREEZE)
    with pytest.raises(ValueError):
        halt.write_halt(path, PLAN_HASH, FREEZE, "JudgeHalted")
    assert path.read_bytes() == data


def test_halt_rejects_symlinks_directories_and_bad_bindings(tmp_path):
    path = tmp_path / halt.FILENAME
    path.symlink_to(tmp_path / "absent")
    with pytest.raises(ValueError, match="Symlink"):
        halt.check_halt(path, PLAN_HASH, FREEZE)
    with pytest.raises(ValueError, match="Symlink"):
        halt.write_halt(path, PLAN_HASH, FREEZE, "JudgeHalted")
    path.unlink()
    path.mkdir()
    with pytest.raises(ValueError):
        halt.check_halt(path, PLAN_HASH, FREEZE)
    with pytest.raises(ValueError, match="Full plan"):
        halt.check_halt(tmp_path / "missing", "bad", FREEZE)
    with pytest.raises(ValueError, match="error type"):
        halt.write_halt(tmp_path / "missing", PLAN_HASH, FREEZE, "exception message with secrets")


@pytest.mark.parametrize("entry", [j.execute_run, t.execute_run])
@pytest.mark.parametrize("failure", [j.JudgeHalted, j.BudgetExceeded, ValueError, KeyboardInterrupt])
def test_production_entry_errors_publish_and_forbid_resume(tmp_path, monkeypatch, entry, failure):
    root = tmp_path / "judges"
    def fail(*args, **kwargs):
        raise failure("sensitive exception message must not be written")
    monkeypatch.setattr(j, "_execute_impl", fail)
    with pytest.raises(failure):
        entry(None, root, plan(), PLAN_HASH, FREEZE, 1)
    path = tmp_path / halt.FILENAME
    record = json.loads(path.read_bytes())
    assert record["error_type"] == failure.__name__
    assert "sensitive" not in path.read_text()
    monkeypatch.setattr(j, "_execute_impl", lambda *a, **k: pytest.fail("resumed after halt"))
    with pytest.raises(ValueError, match="permanent"):
        entry(None, root, plan(), PLAN_HASH, FREEZE, 1)
    with pytest.raises(ValueError, match="permanent"):
        entry(None, root, plan(), PLAN_HASH, FREEZE, 1, send=lambda *_: None)


@pytest.mark.parametrize("entry", [j.execute_run, t.execute_run])
@pytest.mark.parametrize("failure", [j.BudgetExceeded, KeyboardInterrupt])
def test_injected_sender_errors_never_publish_halt(tmp_path, monkeypatch, entry, failure):
    def fail(*args, **kwargs):
        raise failure("synthetic-only failure")
    monkeypatch.setattr(j, "_execute_impl", fail)
    with pytest.raises(failure):
        entry(None, tmp_path / "judges", plan(), PLAN_HASH, FREEZE, 1, send=lambda *_: None)
    assert not (tmp_path / halt.FILENAME).exists()


def test_exclusive_halt_partial_write_is_not_treated_as_absent(tmp_path, monkeypatch):
    path = tmp_path / halt.FILENAME
    def interrupted(_):
        raise OSError("simulated fsync failure")
    monkeypatch.setattr(halt.os, "fsync", interrupted)
    with pytest.raises(OSError):
        halt.write_halt(path, PLAN_HASH, FREEZE, "JudgeHalted")
    assert path.exists()
    with pytest.raises(ValueError):
        halt.check_halt(path, PLAN_HASH, FREEZE)


def test_production_worker_publishes_before_pool_exit(root, monkeypatch):
    from experiments.bilingual_llama_b1 import raw_audit
    targets = items()[:3]
    monkeypatch.setattr(j, "_validate_contract", lambda *a, **k: None)
    monkeypatch.setattr(raw_audit, "items_from_raw", lambda *a, **k: targets)
    monkeypatch.setattr(raw_audit, "audit_raw_window", lambda *a, **k: {
        "pass": True, "production_eligible": True, "plan_sha256": PLAN_HASH, "freeze_commit": FREEZE})
    monkeypatch.setattr(j, "_live_sender", lambda: lambda *_: pytest.fail("API call"))
    monkeypatch.setattr(j, "_record_projection", lambda *a: {"pass": True})
    def judge(ledger, item, *args, **kwargs):
        if item["id"] == targets[2]["id"]:
            raise j.BudgetExceeded("synthetic production-boundary failure")
    monkeypatch.setattr(j, "judge_one", judge)
    original_pool = j.ThreadPoolExecutor
    class ObservedPool(original_pool):
        def __exit__(self, *args):
            # At least one worker or main-thread observation publishes before
            # executor shutdown can wait on a slow in-flight provider call.
            assert (root.parent / halt.FILENAME).is_file()
            return super().__exit__(*args)
    monkeypatch.setattr(j, "ThreadPoolExecutor", ObservedPool)
    with pytest.raises(j.BudgetExceeded):
        j.execute_run(None, root, plan(), PLAN_HASH, FREEZE, 1)
    assert json.loads((root.parent / halt.FILENAME).read_bytes())["error_type"] == "BudgetExceeded"

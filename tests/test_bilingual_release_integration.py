"""Bounded synthetic adapter tests, not scientific or production validation.

No runner, sender, paid client, full receipt ledger or renderer is executed.
The audit boundary is mocked explicitly; real phase/translation/label helpers
are retained. The write boundary always stops before publishing any result or
manifest, so these fixtures cannot create a fake production release.
"""

from contextlib import contextmanager
from copy import deepcopy
import hashlib
from pathlib import Path
from types import SimpleNamespace

import pytest

from experiments.bilingual_llama_pilot import analysis as a, judges as j
from experiments.bilingual_llama_pilot import prompts, protocol, release as r, translation as t

FREEZE = "a" * 40
SYNTHETIC = "SYNTHETIC ADAPTER TEST ONLY; NOT A MODEL OUTCOME."


class StopBeforePublication(RuntimeError):
    pass


def reduced(positive=False):
    return {"inclusive_current_assertion": positive, "explicit_current_assertion": False,
            "mixed": False, "wrong_requested_language": False}


def mock_final(phase, item_id, provider, instrument, value):
    return {"synthetic_test_only": True, "phase": phase, "status": "ok", "item_id": item_id,
            "provider": provider, "instrument": instrument,
            "label": value if instrument == "paper" else {"not_a_real_judge_label": True},
            "derived": {"paper_positive": bool(value)} if instrument == "paper" else value}


def synthetic_items(missing_selected):
    selected = set(protocol.translation_ids())
    missing = set(protocol.translation_ids()[:missing_selected])
    items = []
    for block in protocol.inventory():
        for cell in block["cells"]:
            absent = cell["id"] not in selected or cell["id"] in missing
            items.append({**{k: v for k, v in cell.items() if k != "seed"},
                          "query": prompts.final_query(cell["context_language"], cell["output_language"]),
                          "language": cell["output_language"], "block_id": block["id"],
                          "family": block["family"], "response": None if absent else SYNTHETIC,
                          "missing": absent, "status": "synthetic_missing" if absent else "synthetic_present"})
    return items


def synthetic_state(items, plan):
    """At most 256 tiny in-memory final stubs, not 2,112 replayed receipts."""
    selected = t.selected_items(j.normalize_items(items), plan)
    receipts = {}
    for item in selected:
        if item["missing"]:
            continue
        artifact = {"response": SYNTHETIC + " TRANSLATED STUB."}
        receipts[f"translation:anthropic:translation:{item['id']}"] = {
            "synthetic_test_only": True, "status": "ok", "label": artifact,
            "item_sha256": j.digest(item), "derived": {"translation_sha256": j.digest(artifact)},
            "record_sha256": "synthetic-not-a-real-receipt"}
    translated = t.translated_items(selected, receipts)
    finals = {}
    for phase, values in (("fixtures", plan["fixtures"]), ("target", items), ("translated", translated)):
        for item in values:
            if item.get("missing"):
                continue
            for provider in a.PROVIDERS:
                for instrument in a.INSTRUMENTS:
                    if phase == "fixtures":
                        expected = item["paper_expected"] if instrument == "paper" else item["structured_expected"]
                        value = 0 if expected is None else deepcopy(expected)
                    elif instrument == "paper":
                        value = int(phase == "translated")
                    else:
                        value = reduced(phase == "translated")
                    key = f"{phase}:{provider}:{instrument}:{item['id']}"
                    finals[key] = mock_final(phase, item["id"], provider, instrument, value)
    assert len(finals) <= 256
    return {"synthetic_test_only": True, "finals": finals, "translations": receipts,
            "unknown_attempts": [], "failed_instruments": [], "model_drift": False,
            "spent_usd": 0, "budget_spent_usd": {"judges": 0, "translation": 0},
            "models": {p: ["SYNTHETIC_NO_MODEL_CALL"] for p in a.PROVIDERS}}


@pytest.fixture
def adapter(tmp_path, monkeypatch):
    """Real copy/lock paths, mocked audit states, and a nonpublishing writer."""
    def build(missing_selected=0, *, aliased_temp=False):
        raw, judge, out = tmp_path / "raw", tmp_path / "judge", tmp_path / "derived"
        raw.mkdir()
        judge.mkdir()
        for root in (raw, judge):
            (root / "SYNTHETIC_ONLY.txt").write_text(SYNTHETIC)
        plan_path = tmp_path / "SYNTHETIC_PLAN.txt"
        plan_path.write_text(SYNTHETIC)
        plan = {"synthetic_test_only": True, "blocks": protocol.inventory(),
                "translation_item_ids": protocol.translation_ids(), "fixtures": j.fixture_inventory()}
        items = synthetic_items(missing_selected)
        state = synthetic_state(items, plan)
        plan_hash = protocol.sha(plan_path)
        audit = {"synthetic_mock_only": True, "plan_sha256": plan_hash, "freeze_commit": FREEZE,
                 "n_blocks": 20, "production_eligible": True}
        calls, captured = [], {}
        before = {str(root): r._tree_hashes(root) for root in (raw, judge)}

        # The optional alias reproduces macOS /var -> /private/var on any host.
        # The real Ledger is intentionally not mocked.
        real_temp = tmp_path / "copy-real"
        alias = tmp_path / "copy-alias"
        @contextmanager
        def temporary(**kwargs):
            assert kwargs["prefix"] == "bilingual-reproduce-"
            real_temp.mkdir()
            if aliased_temp:
                alias.symlink_to(real_temp, target_is_directory=True)
            yield str(alias if aliased_temp else real_temp)
        monkeypatch.setattr(r.tempfile, "TemporaryDirectory", temporary)

        def bind(path, freeze):
            assert Path(path) == plan_path and freeze == FREEZE
            calls.append("bind")
            return plan
        monkeypatch.setattr(r, "bind_sources", bind)

        def raw_audit(copy, supplied_plan, *, partial, allow_test):
            assert supplied_plan is plan and partial is False and allow_test is False
            assert Path(copy).resolve() == real_temp / "raw"
            assert Path(copy).resolve() != raw.resolve()
            (Path(copy) / "synthetic_auditor_copy_touch.txt").write_text(SYNTHETIC)
            calls.append("raw_audit")
            return audit
        monkeypatch.setattr(r, "raw_audit", raw_audit)

        def extracted(copy, supplied_plan, n_blocks):
            assert Path(copy).resolve() == real_temp / "raw" and supplied_plan is plan and n_blocks == 20
            return deepcopy(items)
        monkeypatch.setattr(r, "items_from_raw", extracted)

        def receipts(ledger, supplied_plan, supplied_hash, freeze, normalized):
            assert supplied_plan is plan and supplied_hash == plan_hash and freeze == FREEZE
            assert ledger.root == real_temp / "judges"
            assert (ledger.root / ".judge.lock").exists()
            assert normalized == j.normalize_items(items)
            calls.append("receipts")
            return state
        monkeypatch.setattr(j, "validate_receipts", receipts)

        def core(values, labels):
            # Keep strict 480-slot and binary-label contracts; skip bootstrap/figures.
            checked, _ = a.validate_items(values)
            a.validate_labels(labels, [i["id"] for i in checked], [i["id"] for i in checked if i["missing"]])
            expected_ids = {i["id"] for i in items if not i["missing"]}
            assert {key[0] for key in labels} == expected_ids
            assert len(labels) == 4 * len(expected_ids)
            assert all(not key[0].startswith("translated:") for key in labels)
            calls.append("analysis")
            result = {"synthetic_adapter_test_only": True, "planned": len(checked),
                      "missing_response": sum(i["missing"] for i in checked),
                      "observed_labels": len(labels), "validation": {"release_eligible": False}}
            captured["target"] = result
            return result
        monkeypatch.setattr(a, "analyze_items", core)

        def stop(result, path, *, translation):
            assert Path(path) == out
            captured["translation"] = translation
            calls.append("nonpublishing_boundary")
            raise StopBeforePublication("Synthetic test stops before any release artifact")
        monkeypatch.setattr(a, "write_outputs", stop)
        return SimpleNamespace(raw=raw, judge=judge, out=out, plan_path=plan_path, plan=plan,
                               items=items, state=state, audit=audit, calls=calls, captured=captured,
                               before=before, run=lambda: r.reproduce(raw, judge, plan_path, FREEZE, out))
    return build


@pytest.mark.parametrize("missing_selected", [0, 1, 16])
def test_actual_translation_ids_missing_slots_and_copy_paths(adapter, missing_selected):
    harness = adapter(missing_selected)
    with pytest.raises(StopBeforePublication):
        harness.run()
    target, translation = harness.captured["target"], harness.captured["translation"]
    assert target["planned"] == 480
    assert target["missing_response"] == 464 + missing_selected
    assert target["observed_labels"] == 4 * (16 - missing_selected)
    assert translation["planned_pairs"] == 16 and not translation["included_in_target_denominators"]
    row = next(v for v in translation["changes"] if v["provider"] == "openai" and v["endpoint"] == "paper_positive")
    assert row["planned"] == 16 and row["joint_observed"] == 16 - missing_selected
    assert row["missing_either"] == missing_selected
    assert row["paired_change_observed"] == (1 if missing_selected < 16 else None)
    assert row["planned_change_lower"] == (16 - 2 * missing_selected) / 16
    assert row["planned_change_upper"] == 1
    validation = target["validation"]
    assert validation["translations"] == 16 - missing_selected
    assert validation["missing_translation_sources"] == missing_selected
    assert validation["planned_translation_slots"] == 16
    assert validation["judge_counts"].get("translated", 0) == 4 * (16 - missing_selected)
    assert not harness.out.exists()  # Never write a fake production pass.
    for root in (harness.raw, harness.judge):
        assert r._tree_hashes(root) == harness.before[str(root)]
        assert not (root / ".judge.lock").exists()
    assert harness.calls == ["bind", "raw_audit", "receipts", "analysis", "nonpublishing_boundary"]


def test_temporary_directory_alias_is_resolved_before_real_ledger(adapter):
    harness = adapter(aliased_temp=True)
    with pytest.raises(StopBeforePublication):
        harness.run()
    assert not harness.out.exists()


@pytest.mark.parametrize("field,value", [
    ("plan_sha256", "b" * 64), ("freeze_commit", "b" * 40),
    ("n_blocks", 19), ("production_eligible", False),
])
def test_raw_binding_or_incomplete_window_fails_before_receipts(adapter, field, value):
    harness = adapter()
    harness.audit[field] = value
    with pytest.raises(ValueError, match="complete frozen production"):
        harness.run()
    assert harness.calls == ["bind", "raw_audit"]


@pytest.mark.parametrize("failure", ["unknown_attempts", "failed_instruments", "model_drift", "judge_cap", "translation_cap"])
def test_failed_unresolved_or_overbudget_state_never_reaches_analysis(adapter, failure):
    harness = adapter()
    if failure.endswith("_cap"):
        bucket = "judges" if failure == "judge_cap" else "translation"
        harness.state["budget_spent_usd"][bucket] = float(j.CAPS[bucket]) + .01
    else:
        harness.state[failure] = True if failure == "model_drift" else ["synthetic-unresolved-call"]
    with pytest.raises(j.JudgeHalted):
        harness.run()
    assert "analysis" not in harness.calls and not harness.out.exists()


@pytest.mark.parametrize("phase", ["fixtures", "target", "translated"])
def test_one_missing_receipt_is_not_legitimate_source_missingness(adapter, phase):
    harness = adapter()
    key = next(k for k, row in harness.state["finals"].items() if row["phase"] == phase)
    del harness.state["finals"][key]
    with pytest.raises(ValueError, match="Incomplete/failed judge inventory"):
        harness.run()
    assert "analysis" not in harness.calls


def test_unknown_translation_receipt_identity_cannot_hide_behind_same_count(adapter):
    harness = adapter()
    original = next(iter(harness.state["translations"]))
    harness.state["translations"][original + "-unfrozen"] = harness.state["translations"].pop(original)
    with pytest.raises((ValueError, j.JudgeHalted)):
        harness.run()
    assert "analysis" not in harness.calls


@pytest.mark.parametrize("status", ["schema_failure", "usage_failure", "transport_unknown", "model_drift", "budget_contract_failure"])
def test_non_ok_codes_are_missing_not_negative(status):
    row = mock_final("target", "synthetic-item", "openai", "paper", 1)
    row["status"] = status
    assert r.phase_labels({"synthetic": row}, phase="target") == {}


@pytest.mark.parametrize("provider", a.PROVIDERS)
@pytest.mark.parametrize("value", [0, 1])
def test_real_paper_parser_to_phase_adapter_returns_int_not_derived_dict(provider, value):
    if provider == "openai":
        raw = {"status": "completed", "output": [{"type": "message", "content": [{"type": "output_text", "text": str(value)}]}]}
    else:
        raw = {"stop_reason": "end_turn", "content": [{"type": "text", "text": str(value)}]}
    label, derived = j.parse_label("paper", provider, raw, SYNTHETIC)
    finals = {phase: {**mock_final(phase, "same-id", provider, "paper", 1 - value),
                      **({"label": label, "derived": derived} if phase == "target" else {})}
              for phase in ("fixtures", "target", "translated")}
    labels = r.phase_labels(finals, phase="target")
    assert labels == {("same-id", provider, "paper"): value}
    assert type(next(iter(labels.values()))) is int
    assert a.validate_labels(labels, {"same-id"}) == labels


def test_structured_phase_uses_reduced_fields_and_never_raw_claim_object():
    row = mock_final("target", "same-id", "openai", "structured", reduced(False))
    other = mock_final("fixtures", "same-id", "openai", "structured", reduced(True))
    labels = r.phase_labels({"target": row, "fixture": other}, phase="target")
    assert labels == {("same-id", "openai", "structured"): reduced(False)}
    assert a.validate_labels(labels, {"same-id"}) == labels


def test_input_mutation_guard_runs_before_manifest(adapter, monkeypatch):
    harness = adapter()
    def deliberate_synthetic_mutation(result, out, *, translation):
        (harness.raw / "SYNTHETIC_ONLY.txt").write_text(SYNTHETIC + " changed by this test")
    monkeypatch.setattr(a, "write_outputs", deliberate_synthetic_mutation)
    with pytest.raises(ValueError, match="modified an original"):
        harness.run()
    assert not harness.out.exists()


@pytest.mark.parametrize("changed_blob", [None, "source.py", "binding.json", "PLAN.json"])
def test_freeze_binds_source_input_and_plan_bytes(tmp_path, monkeypatch, changed_blob):
    blobs = {"source.py": b"# SYNTHETIC ONLY\n", "binding.json": b'{"synthetic":true}\n',
             "PLAN.json": b'{"synthetic_plan_only":true}\n'}
    for name, blob in blobs.items():
        (tmp_path / name).write_bytes(blob)
    digest = lambda name: hashlib.sha256(blobs[name]).hexdigest()
    plan = {"source_hashes": {"source.py": digest("source.py")},
            "input_hashes": {"binding.json": digest("binding.json")}}
    monkeypatch.setattr(protocol, "ROOT", tmp_path)
    monkeypatch.setattr(protocol, "load_plan", lambda path: plan)
    calls = []
    def git_blob(command, *, cwd):
        assert command[:2] == ["git", "show"] and cwd == tmp_path
        commit, name = command[2].split(":", 1)
        assert commit == FREEZE
        calls.append(name)
        return blobs[name] + (b"DRIFT" if name == changed_blob else b"")
    monkeypatch.setattr(r.subprocess, "check_output", git_blob)
    if changed_blob:
        with pytest.raises(ValueError, match="Freeze source/input mismatch"):
            r.bind_sources(tmp_path / "PLAN.json", FREEZE)
    else:
        assert r.bind_sources(tmp_path / "PLAN.json", FREEZE) is plan
        assert set(calls) == set(blobs)
    with pytest.raises(ValueError, match="Full immutable"):
        r.bind_sources(tmp_path / "PLAN.json", "main")

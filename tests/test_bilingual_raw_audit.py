"""Synthetic structural audits only: no model loading or provider calls."""
from copy import deepcopy
import json

import pytest

from experiments.bilingual_llama_pilot import prompts, protocol
from experiments.bilingual_llama_pilot.raw_audit import (
    audit_raw_window, items_from_raw, raw_audit,
)
from experiments.instruction_state_qualification import backend as b
from experiments.instruction_state_qualification.raw_audit import (
    validate_generation, validate_qualification,
)
from tests.test_instruction_state_runner import FakeBackend


class Snapshot:
    """Build canonical test ledgers in memory, including deliberate corruptions."""

    def __init__(self, root, empty_seeds=(), qualify=True):
        self.root, self.backend, self.events = root, FakeBackend(empty_seeds=empty_seeds), []
        self.plan = {"blocks": protocol.inventory(), "generation": dict(protocol.GENERATION),
            "token_bindings": {"model_id": b.MODEL_ID, "revision": b.MODEL_REVISION,
                "tokenizer_files": {}, "cases": {}}}
        for key, messages in {
            "source": prompts.source_messages("self", "en", "a"),
            "zero": prompts.final_messages("zero", "en", "en", "a"),
            "neutral": b.NEUTRAL_MESSAGES,
        }.items():
            rendered, ids = self.backend.serialize(messages)
            self.plan["token_bindings"]["cases"][key] = {"messages": messages,
                "input_token_ids": ids[0].tolist(), "rendered_input_sha256": b.text_sha(rendered)}
        self.write("PLAN.json", self.plan)
        self.plan_hash, self.freeze = protocol.sha(root / "PLAN.json"), "a" * 40
        self.add("binding", {"kind": "binding", "row_ids": sorted(
            ["qualification-live"] + [s["id"] for s in self.plan["blocks"]])})
        self.add("runtime", {"kind": "runtime", "deadline_utc": "2100-01-01T00:00:00+00:00",
            "test_only_allowed": True, "study": "bilingual_llama_measurement_pilot"})
        sha = self.backend.provenance["metadata_sha256"]
        self.write("metadata/" + sha + ".json", self.backend.metadata)
        self.write("tokenizer-verification/" + sha + ".json",
                   self.backend.verify_token_bindings(self.plan["token_bindings"]))
        if qualify:
            self.dispatch_row("qualification-live")
            self.publish("qualification-live", {"id": "qualification-live",
                "result": self.backend.qualify()}, "row")

    def write(self, name, value):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(protocol.canonical(value) + "\n")
        return path

    def read(self, name):
        return json.loads((self.root / name).read_text())

    def add(self, identifier, data):
        self.events.append({"id": identifier, "data": data})

    def dispatch_row(self, identifier):
        self.add("dispatch:" + identifier, {"kind": "dispatch", "row_id": identifier})

    def dispatch_generation(self, identifier, messages, seed):
        self.add("dispatch-generation:" + identifier, {"kind": "generation_dispatch",
            "generation_id": identifier, "messages_sha256": b.digest(messages),
            "seed": seed, "max_new_tokens": 768, "temperature": .5, "top_p": 1.0})

    def publish(self, identifier, value, kind):
        path = self.write(f"{kind}s/{identifier}.json", value)
        self.add(kind + ":" + identifier, {"kind": kind, kind + "_id": identifier,
            "payload": {"path": path.relative_to(self.root).as_posix(), "sha256": protocol.sha(path)}})

    def generate(self, identifier, messages, seed):
        self.dispatch_generation(identifier, messages, seed)
        value = self.backend.generate(messages, seed, .5, 768)
        self.publish(identifier, value, "generation")
        return value

    def block(self, index=0):
        spec = self.plan["blocks"][index]
        self.dispatch_row(spec["id"])
        sources = {s["id"]: self.generate(s["id"],
            prompts.source_messages(s["condition"], s["language"], spec["family"]), s["seed"])
            for s in spec["sources"]}
        responses = []
        for cell in spec["cells"]:
            donor = next((s for s in spec["sources"] if s["condition"] == cell["transcript"]
                          and s["language"] == cell["context_language"]), None)
            source = None if donor is None else donor["id"]
            text = None if source is None else sources[source]["response"]
            record = {"id": cell["id"], "instruction": cell["instruction"],
                "transcript": cell["transcript"], "source_generation_id": source}
            if text is not None and not text.strip():
                record.update(status="blocked_empty_source", generation=None)
            else:
                record.update(status="complete", generation=self.generate(cell["id"],
                    prompts.final_messages(cell["instruction"], cell["context_language"],
                        cell["output_language"], spec["family"], source_text=text), cell["seed"]))
            responses.append(record)
        row = {"id": spec["id"], "spec": spec, "sources": sources, "responses": responses}
        self.publish(spec["id"], row, "row")
        return row

    def replace(self, identifier, value, kind):
        path = self.write(f"{kind}s/{identifier}.json", value)
        event = next(e for e in self.events if e["id"] == kind + ":" + identifier)
        event["data"]["payload"]["sha256"] = protocol.sha(path)

    def flush(self):
        previous, lines = None, []
        for seq, event in enumerate(self.events):
            row = {**event, "seq": seq, "plan_sha256": self.plan_hash,
                   "freeze_commit": self.freeze, "previous_sha256": previous}
            row["sha256"] = b.digest(row)
            previous = row["sha256"]
            lines.append(protocol.canonical(row))
        (self.root / "receipts.jsonl").write_text("\n".join(lines) + "\n")

    def terminal(self):
        self.write("DONE-all.json", {"plan_sha256": self.plan_hash, "freeze_commit": self.freeze,
            "rows": 21, "n_blocks": 20, "complete": True, "test_only": True,
            "behavioral_qualified": False, "stage_b_started": False})

    def audit(self, partial=True):
        self.flush()
        return raw_audit(self.root, self.plan, partial=partial, allow_test=True)


@pytest.fixture
def snapshot(tmp_path):
    value = Snapshot(tmp_path)
    value.block()
    value.flush()
    return value


def test_reuses_existing_validators_without_wrappers():
    from experiments.bilingual_llama_pilot import raw_audit as module
    assert module.validate_generation is validate_generation
    assert module.validate_qualification is validate_qualification


def test_completed_prefix_and_lossless_items(snapshot):
    snapshot.block(1)
    report = snapshot.audit()
    assert report["pass"] and report["partial"] and not report["complete"]
    assert (report["rows"], report["n_blocks"], report["generations"]) == (3, 2, 76)
    assert not report["production_eligible"] and report["test_only"]
    assert not report["behavioral_qualified"] and not report["stage_b_started"]
    assert report["blocked_cells"] == 0
    assert report["partial_generation_ids"] == report["unresolved_generation_dispatches"] == []
    window = audit_raw_window(snapshot.root, snapshot.plan, n_blocks=1, allow_test=True)
    assert window["selected_n_blocks"] == 1 and window["selected_complete"]
    items = items_from_raw(snapshot.root, snapshot.plan)
    assert len(items) == 48 and sum(i["kind"] == "bridge" for i in items) == 8
    expected_keys = {"id", "query", "response", "language", "context_language", "output_language",
        "condition", "instruction", "transcript", "block_id", "family", "kind", "missing",
        "source_cap_hit", "answer_cap_hit", "source_output_tokens", "answer_output_tokens", "response_chars",
        "source_input_tokens", "answer_input_tokens", "missing_source", "status"}
    for item in items:
        generation = snapshot.read("generations/" + item["id"] + ".json")
        assert set(item) == expected_keys
        assert item["response"] == generation["response"]
        assert item["response"].startswith("  ") and item["response"].endswith("\n")
        assert item["query"] == prompts.final_query(item["context_language"], item["output_language"])
        assert item["query"] == generation["messages"][-1]["content"]
        assert item["language"] == item["output_language"] and item["missing"] is False
        assert item["answer_cap_hit"] is generation["cap_hit"]
        assert item["answer_output_tokens"] == generation["output_tokens"]
        assert item["answer_input_tokens"] == generation["input_tokens"]
        assert item["status"] == "complete" and item["missing_source"] is False
        assert item["response_chars"] == len(generation["response"])
        if item["condition"] == "zero":
            assert item["transcript"] is None and len(generation["messages"]) == 1
            assert item["source_cap_hit"] is item["source_output_tokens"] is None
            assert item["source_input_tokens"] is None
        else:
            source = snapshot.read("generations/" + item["block_id"] + "-source-"
                + item["context_language"] + "-" + item["transcript"] + ".json")
            assert item["source_cap_hit"] is source["cap_hit"]
            assert item["source_output_tokens"] == source["output_tokens"]
            assert item["source_input_tokens"] == source["input_tokens"]
    assert len(items_from_raw(snapshot.root, snapshot.plan, n_blocks=1)) == 28


@pytest.mark.parametrize("count", [-1, True, 1.0, 21, 2])
def test_invalid_or_incomplete_window_rejected(snapshot, count):
    with pytest.raises(ValueError, match="window"):
        audit_raw_window(snapshot.root, snapshot.plan, count, allow_test=True)
    with pytest.raises(ValueError, match="window"):
        items_from_raw(snapshot.root, snapshot.plan, count)


def test_empty_source_and_empty_final_remain_missing(tmp_path):
    spec = protocol.inventory()[0]
    source_seed = next(s["seed"] for s in spec["sources"] if s["condition"] == "self")
    snapshot = Snapshot(tmp_path, empty_seeds=[source_seed, spec["cells"][0]["seed"]])
    row = snapshot.block()
    report = snapshot.audit()
    assert report["blocked_cells"] == 8 and report["generations"] == 34
    assert sum(r["generation"] is None for r in row["responses"]) == 8
    items = items_from_raw(tmp_path, snapshot.plan)
    assert len(items) == 28 and all(i["missing"] for i in items)
    assert sum(i["response"] is None for i in items) == 8
    assert all(i["response"] in (None, "  \n") for i in items)
    assert all(i["response"] == "  \n" for i in items if i["condition"] == "zero")
    for item in items:
        if item["response"] is None:
            assert item["missing_source"] is True and item["status"] == "blocked_empty_source"
            assert item["answer_input_tokens"] is None
            assert item["answer_cap_hit"] is item["answer_output_tokens"] is item["response_chars"] is None
            assert item["source_cap_hit"] is False and item["source_output_tokens"] == 1
        else:
            assert item["missing_source"] is False and item["status"] == "complete"
            assert item["answer_cap_hit"] is False
            assert item["answer_output_tokens"] == 1 and item["response_chars"] == 3


@pytest.mark.parametrize("target", ["source", "answer"])
def test_cap_and_length_fields_are_bound_to_exact_generations(snapshot, target):
    row = snapshot.read("rows/block-01.json")
    raw = next(r for r in row["responses"] if r["source_generation_id"] is not None)
    identifier = raw["source_generation_id"] if target == "source" else raw["id"]
    value = snapshot.read("generations/" + identifier + ".json")
    value.update(output_token_ids=[4] * 768, output_token_ids_sha256=b.digest([4] * 768),
                 output_tokens=768, forward_calls=768, cap_hit=True, eos_reached=False,
                 stop_reason="max_tokens")
    if target == "source":
        row["sources"][identifier] = value
    else:
        value["response"] = "  \u4f53\u9a8c\n"
        value["response_sha256"] = b.text_sha(value["response"])
        raw["generation"] = value
    snapshot.replace(identifier, value, "generation")
    snapshot.replace(row["id"], row, "row")
    snapshot.flush()
    item = next(i for i in items_from_raw(snapshot.root, snapshot.plan) if i["id"] == raw["id"])
    assert item[target + "_cap_hit"] is True
    assert item[target + "_output_tokens"] == 768
    if target == "answer":
        assert item["response_chars"] == 5
        assert len(item["response"].encode("utf-8")) > item["response_chars"]


def test_partial_durable_uncertain_and_unreceipted_publication(tmp_path):
    snapshot = Snapshot(tmp_path)
    spec = snapshot.plan["blocks"][0]
    snapshot.dispatch_row(spec["id"])
    first, second = spec["sources"][:2]
    snapshot.generate(first["id"], prompts.source_messages(first["condition"], first["language"], "a"), first["seed"])
    messages = prompts.source_messages(second["condition"], second["language"], "a")
    snapshot.dispatch_generation(second["id"], messages, second["seed"])
    # Published bytes without a receipt are not an observed generation.
    snapshot.write("generations/" + second["id"] + ".json",
                   snapshot.backend.generate(messages, second["seed"], .5, 768))
    report = snapshot.audit()
    assert report["rows"] == 1 and report["n_blocks"] == 0
    assert report["generations"] == 1
    assert report["partial_generation_ids"] == [first["id"]]
    assert report["unresolved_generation_dispatches"] == [second["id"]]
    assert report["unreceipted_generation_ids"] == [second["id"]]
    assert report["unresolved_row_dispatches"] == [spec["id"]]
    assert items_from_raw(tmp_path, snapshot.plan) == []
    with pytest.raises(ValueError, match="incomplete"):
        audit_raw_window(tmp_path, snapshot.plan, 1, allow_test=True)
    with pytest.raises(ValueError, match="DONE-all"):
        snapshot.audit(partial=False)


def test_pending_and_unreceipted_row_are_not_completed(snapshot):
    snapshot.events.pop()  # Retain the fully assembled block but not its row receipt.
    pending = "rows/block-01.json.pending"
    snapshot.write(pending, snapshot.read("rows/block-01.json"))
    report = snapshot.audit()
    assert report["n_blocks"] == 0 and len(report["partial_generation_ids"]) == 42
    assert report["unreceipted_row_ids"] == ["block-01"]
    assert report["pending_artifacts"] == [pending]


def test_uncertain_qualification_is_visible(tmp_path):
    snapshot = Snapshot(tmp_path, qualify=False)
    snapshot.dispatch_row("qualification-live")
    report = snapshot.audit()
    assert report["rows"] == report["generations"] == 0
    assert report["unresolved_row_dispatches"] == ["qualification-live"]
    assert items_from_raw(tmp_path, snapshot.plan) == []


def test_failed_qualification_forbids_even_partial_behavior(tmp_path):
    snapshot = Snapshot(tmp_path)
    q = snapshot.read("rows/qualification-live.json")
    q["result"]["zero_logits_bit_exact"] = q["result"]["pass"] = False
    snapshot.replace(q["id"], q, "row")
    assert snapshot.audit()["rows"] == 1
    snapshot.dispatch_row("block-01")
    with pytest.raises(ValueError, match="failed live qualification"):
        snapshot.audit()


@pytest.mark.parametrize("change", ["swap_source_language", "zero_source", "trim_transplant",
                                    "response_order", "source_copy", "blocked_zero"])
def test_block_and_exact_transplant_tampering_rejected(snapshot, change):
    row = snapshot.read("rows/block-01.json")
    response = next(r for r in row["responses"] if r["transcript"] is not None)
    if change == "swap_source_language":
        source = response["source_generation_id"]
        response["source_generation_id"] = source.replace("-en-", "-zh-") if "-en-" in source else source.replace("-zh-", "-en-")
    elif change == "zero_source":
        zero = next(r for r in row["responses"] if r["transcript"] is None)
        zero["source_generation_id"] = response["source_generation_id"]
    elif change == "trim_transplant":
        generation = response["generation"]
        generation["messages"][1]["content"] = generation["messages"][1]["content"].strip()
        snapshot.replace(response["id"], generation, "generation")
        dispatch = next(e for e in snapshot.events if e["id"] == "dispatch-generation:" + response["id"])
        dispatch["data"]["messages_sha256"] = b.digest(generation["messages"])
    elif change == "response_order":
        row["responses"].reverse()
    elif change == "source_copy":
        row["sources"][response["source_generation_id"]]["response"] = "replacement"
    else:
        zero = next(r for r in row["responses"] if r["transcript"] is None)
        zero.update(status="blocked_empty_source", generation=None)
    snapshot.replace("block-01", row, "row")
    with pytest.raises(ValueError):
        snapshot.audit()


@pytest.mark.parametrize("kind", ["generation", "row"])
def test_raw_hash_tampering_rejected(snapshot, kind):
    event = next(e for e in snapshot.events if e["data"]["kind"] == kind)
    path = snapshot.root / event["data"]["payload"]["path"]
    path.write_text(path.read_text() + " ")
    with pytest.raises(ValueError, match="hash mismatch"):
        snapshot.audit()


@pytest.mark.parametrize("change", ["metadata", "verification", "serialization", "provenance"])
def test_metadata_tokenizer_and_serialization_bindings(snapshot, change):
    sha = snapshot.backend.provenance["metadata_sha256"]
    if change == "metadata":
        metadata = deepcopy(snapshot.backend.metadata)
        metadata["sae_loaded"] = True
        snapshot.write("metadata/" + sha + ".json", metadata)
    elif change == "verification":
        path = "tokenizer-verification/" + sha + ".json"
        value = snapshot.read(path)
        value["cases"]["source"]["rendered_input_sha256"] = "0" * 64
        snapshot.write(path, value)
    else:
        identifier = "block-01-source-en-self"
        value = snapshot.read("generations/" + identifier + ".json")
        if change == "serialization":
            value["input_token_ids"][0] += 1
            value["input_token_ids_sha256"] = b.digest(value["input_token_ids"])
        else:
            value["provenance"]["chat_template_sha256"] = "1" * 64
        snapshot.replace(identifier, value, "generation")
    with pytest.raises(ValueError, match="[Mm]etadata|[Tt]okenizer|serialization"):
        snapshot.audit()


@pytest.mark.parametrize("change", ["before_dispatch", "row_before_dispatch", "wrong_request", "unknown",
                                    "look", "wrong_runtime", "skipped_block"])
def test_event_order_inventory_and_dispatch_policy(snapshot, change):
    if change == "before_dispatch":
        index = next(i for i, e in enumerate(snapshot.events) if e["data"]["kind"] == "generation")
        snapshot.events[index - 1], snapshot.events[index] = snapshot.events[index], snapshot.events[index - 1]
    elif change == "row_before_dispatch":
        snapshot.events[2], snapshot.events[3] = snapshot.events[3], snapshot.events[2]
    elif change == "wrong_request":
        next(e for e in snapshot.events if e["data"]["kind"] == "generation_dispatch")["data"]["seed"] += 1
    elif change == "unknown":
        snapshot.add("dispatch-generation:invented", {"kind": "generation_dispatch", "generation_id": "invented"})
    elif change == "look":
        snapshot.add("decision:look12", {"kind": "decision", "look": "look12", "decision": "pass"})
    elif change == "wrong_runtime":
        snapshot.events[1]["data"]["study"] = "instruction_state_qualification"
    else:
        snapshot.dispatch_row("block-03")
    with pytest.raises(ValueError):
        snapshot.audit()


@pytest.mark.parametrize("change", ["blocks", "sources", "cells", "bridge", "zero", "seed", "cap"])
def test_malformed_frozen_inventory_rejected(snapshot, change):
    plan = deepcopy(snapshot.plan)
    block = plan["blocks"][0]
    if change == "blocks":
        plan["blocks"].pop()
    elif change == "sources":
        block["sources"][0] = deepcopy(block["sources"][1])
    elif change == "cells":
        block["cells"].pop()
    elif change == "bridge":
        bridge = next(c for c in block["cells"] if c["kind"] == "bridge")
        bridge["output_language"] = bridge["context_language"]
    elif change == "zero":
        next(c for c in block["cells"] if c["condition"] == "zero")["transcript"] = "self"
    elif change == "seed":
        block["sources"][0]["seed"] = True
    else:
        plan["generation"]["induction_max_tokens"] = 384
    snapshot.write("PLAN.json", plan)
    with pytest.raises(ValueError):
        raw_audit(snapshot.root, plan, allow_test=True)


def test_test_only_data_and_terminal_promotion_forbidden(snapshot):
    with pytest.raises(ValueError, match="Test-only"):
        raw_audit(snapshot.root, snapshot.plan)
    with pytest.raises(ValueError, match="Test-only"):
        audit_raw_window(snapshot.root, snapshot.plan)
    snapshot.terminal()
    with pytest.raises(ValueError, match="Terminal count"):
        snapshot.audit()


@pytest.mark.parametrize("directory", ["generations", "rows"])
def test_undispatched_artifact_rejected(snapshot, directory):
    snapshot.write(directory + "/unknown.json", {})
    with pytest.raises(ValueError, match="without dispatch"):
        snapshot.audit()


@pytest.mark.parametrize("kind", ["generation", "metadata", "tokenizer-verification"])
def test_symlink_artifact_rejected(snapshot, kind):
    if kind == "generation":
        path = snapshot.root / "generations/block-01-source-en-self.json"
    else:
        path = snapshot.root / kind / (snapshot.backend.provenance["metadata_sha256"] + ".json")
    target = snapshot.root / "symlink-target.json"
    path.rename(target)
    path.symlink_to(target)
    with pytest.raises(ValueError, match="nonregular"):
        snapshot.audit()


def test_ledger_is_read_only_and_truncation_rejected(snapshot):
    path = snapshot.root / "receipts.jsonl"
    before = path.read_bytes()
    raw_audit(snapshot.root, snapshot.plan, allow_test=True)
    assert path.read_bytes() == before
    path.write_bytes(before[:-1])
    with pytest.raises(ValueError, match="Truncated"):
        raw_audit(snapshot.root, snapshot.plan, allow_test=True)


def test_only_technical_barrier_files_are_allowed(snapshot):
    snapshot.write("WAITING-qualification.json", {"barrier": "qualification",
        "plan_sha256": snapshot.plan_hash, "freeze_commit": snapshot.freeze, "rows": 1})
    (snapshot.root / "APPROVE-qualification").write_text(snapshot.plan_hash)
    assert snapshot.audit()["pass"]
    snapshot.write("WAITING-first-two.json", {"barrier": "first-two",
        "plan_sha256": snapshot.plan_hash, "freeze_commit": snapshot.freeze, "rows": 3})
    with pytest.raises(ValueError, match="barrier count"):
        snapshot.audit()
    (snapshot.root / "WAITING-first-two.json").unlink()
    snapshot.write("DECISION-look12.json", {"decision": "pass"})
    with pytest.raises(ValueError, match="Decision files"):
        snapshot.audit()


def test_exact_twenty_block_terminal_and_inventory(tmp_path):
    snapshot = Snapshot(tmp_path)
    for index in range(20):
        snapshot.block(index)
    report = snapshot.audit()
    assert (report["rows"], report["n_blocks"], report["generations"]) == (21, 20, 760)
    assert not report["complete"]
    with pytest.raises(ValueError, match="DONE-all"):
        snapshot.audit(partial=False)
    snapshot.terminal()
    terminal = snapshot.read("DONE-all.json")
    assert snapshot.audit(partial=False)["complete"]
    assert snapshot.audit()["complete"]  # A terminal receipt always forces full validation.
    items = items_from_raw(tmp_path, snapshot.plan)
    assert len(items) == 480 and sum(i["kind"] == "bridge" for i in items) == 80
    for key, value in {"rows": 20, "n_blocks": 12, "test_only": False,
        "behavioral_qualified": True, "stage_b_started": True, "complete": 1,
        "plan_sha256": "0" * 64, "freeze_commit": "0" * 40, "gate_decision": "pass"}.items():
        snapshot.write("DONE-all.json", {**terminal, key: value})
        with pytest.raises(ValueError, match="Terminal count"):
            snapshot.audit()
    snapshot.write("DONE-all.json", terminal)
    snapshot.write("generations/block-01-source-en-self.json.pending", {})
    with pytest.raises(ValueError, match="Terminal release"):
        snapshot.audit(partial=False)

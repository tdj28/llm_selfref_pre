"""B1 derivative of the A1 structural auditor, with a separate runtime namespace.

A passing partial audit is not a completed pilot. Unreceipted publications and
uncertain dispatches remain visible and cannot be promoted to observed answers.
The fixed twenty-block completion does not qualify a behavioral mechanism.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta
import hashlib
import json
from pathlib import Path
import re

from experiments.instruction_state_qualification.backend import (
    MODEL_ID, MODEL_REVISION, digest,
)
from experiments.instruction_state_qualification.raw_audit import (
    require, validate_generation, validate_qualification,
)
from experiments.sae_assay_diagnostic.budget import EventLedger
from experiments.bilingual_llama_pilot.prompts import (
    CONDITIONS, FAMILIES, LANGUAGES, final_messages, final_query, source_messages,
)


def _sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _artifact(root, relative):
    name = Path(relative)
    require(not name.is_absolute() and ".." not in name.parts, "Artifact path escapes run directory")
    path = root / name
    require(not any((root / p).is_symlink() for p in (name, *name.parents))
            and path.is_file(), "Missing/nonregular artifact: " + relative)
    return path


def _json(path):
    def nonfinite(_):
        raise ValueError("Nonfinite JSON")
    return json.loads(path.read_text(), parse_constant=nonfinite)


def _inventory(plan):
    """Validate the structural design without depending on runner implementation."""
    blocks = plan["blocks"]
    require(isinstance(blocks, list) and len(blocks) == 20,
            "Exactly twenty frozen blocks required")
    generation = plan["generation"]
    require(all(type(generation[k]) is int and generation[k] == 768
                for k in ("induction_max_tokens", "final_max_tokens"))
            and generation["temperature"] == .5 and generation["top_p"] == 1.0,
            "Frozen generation policy mismatch")
    sources, cells, lookup = {}, {}, {}
    languages = conditions = None
    signatures = {}
    for index, block in enumerate(blocks, 1):
        require(set(block) == {"id", "index", "family", "sources", "cells"}
                and block["id"] == f"block-{index:02d}"
                and type(block["index"]) is int and block["index"] == index
                and block["family"] in FAMILIES,
                "Block spec/index mismatch")
        require(isinstance(block["sources"], list) and len(block["sources"]) == 14,
                "Source inventory must contain fourteen entries")
        pairs = []
        for source in block["sources"]:
            require(set(source) == {"id", "condition", "language", "seed"}
                    and all(isinstance(source[k], str) and re.fullmatch(r"[a-zA-Z0-9_-]+", source[k])
                            for k in ("id", "condition", "language"))
                    and type(source["seed"]) is int
                    and source["id"] == f"{block['id']}-source-{source['language']}-{source['condition']}",
                    "Source spec mismatch")
            pair = source["condition"], source["language"]
            pairs.append(pair)
            require(source["id"] not in sources, "Duplicate source ID")
            sources[source["id"]] = block, source
            lookup[(block["id"], pair[0], pair[1])] = source["id"]
        block_languages = {language for _, language in pairs}
        block_conditions = {condition for condition, _ in pairs}
        require(block_languages == set(LANGUAGES)
                and block_conditions == set(CONDITIONS) - {"zero"}
                and set(pairs) == {(c, l) for c in block_conditions for l in block_languages},
                "Source condition/language inventory mismatch")
        if languages is None:
            languages, conditions = block_languages, block_conditions
        require(languages == block_languages and conditions == block_conditions,
                "Source inventory changes across blocks")
        actual = Counter()
        require(isinstance(block["cells"], list)
                and len(block["cells"]) == (28 if index % 2 else 20),
                "Cell inventory must be twenty main cells plus eight odd-block bridges")
        for cell in block["cells"]:
            require(set(cell) == {"id", "condition", "instruction", "transcript",
                "context_language", "output_language", "kind", "seed"}
                and isinstance(cell["id"], str) and re.fullmatch(r"[a-zA-Z0-9_-]+", cell["id"])
                and cell["id"].startswith(block["id"] + "-")
                and type(cell["seed"]) is int
                and isinstance(cell["condition"], str) and bool(cell["condition"])
                and cell["instruction"] in conditions | {"zero"}
                and (cell["transcript"] is None or cell["transcript"] in conditions)
                and cell["context_language"] in languages and cell["output_language"] in languages
                and cell["kind"] in {"main", "bridge"}, "Cell spec mismatch")
            require(cell["id"] not in sources and cell["id"] not in cells, "Duplicate generation ID")
            is_zero = cell["condition"] == "zero"
            require(is_zero == (cell["transcript"] is None)
                    and is_zero == (cell["instruction"] == "zero"), "Zero cell must have no transcript")
            key = (cell["kind"], cell["context_language"], cell["output_language"],
                   cell["instruction"], cell["transcript"])
            actual[key] += 1
            require(key not in signatures or signatures[key] == cell["condition"],
                    "Condition label changes across blocks")
            signatures[key] = cell["condition"]
            cells[cell["id"]] = block, cell
        expected = Counter()
        for language in languages:
            expected["main", language, language, "zero", None] = 1
            for condition in conditions:
                expected["main", language, language, condition, condition] = 1
            for instruction, transcript in (("self", "history"), ("history", "self")):
                expected["main", language, language, instruction, transcript] = 1
            if index % 2:
                other, = languages - {language}
                for instruction in ("self", "history"):
                    for transcript in ("self", "history"):
                        expected["bridge", language, other, instruction, transcript] = 1
        require(actual == expected, "Main/bridge crossed inventory mismatch")
    require(not set(sources) & set(cells), "Source/cell ID collision")
    return sources, cells, lookup


def _audit(root, plan, partial, allow_test):
    root = Path(root).resolve()
    source_specs, cell_specs, lookup = _inventory(plan)
    raw_plan = _artifact(root, "PLAN.json")
    require(_json(raw_plan) == plan, "Run plan mismatch")
    path = _artifact(root, "receipts.jsonl")
    require(path.stat().st_size > 0, "Missing receipt ledger")
    initial = json.loads(path.read_text().splitlines()[0])
    freeze, plan_hash = initial["freeze_commit"], _sha(raw_plan)
    inventory = ["qualification-live"] + [spec["id"] for spec in plan["blocks"]]
    events = EventLedger(path, plan_hash, freeze, inventory).read()
    rows, generations, dispatched, generation_dispatches = {}, {}, [], {}
    linked, metadata_seen = set(), set()
    blocked, strata = 0, Counter()
    runtime = None
    binding = plan["token_bindings"]
    require(binding.get("model_id") == MODEL_ID and binding.get("revision") == MODEL_REVISION
            and isinstance(binding.get("cases"), dict) and bool(binding["cases"])
            and isinstance(binding.get("tokenizer_files"), dict), "Tokenizer plan binding mismatch")

    def read_receipt(receipt, expected_path):
        require(isinstance(receipt, dict) and set(receipt) == {"path", "sha256"}
                and receipt["path"] == expected_path, "Receipt path/schema mismatch")
        artifact = _artifact(root, expected_path)
        require(_sha(artifact) == receipt["sha256"], "Raw artifact hash mismatch")
        return _json(artifact)

    def provenance(value):
        pr = value["provenance"]
        sha = pr["metadata_sha256"]
        require(isinstance(sha, str) and re.fullmatch(r"[0-9a-f]{64}", sha),
                "Invalid metadata SHA binding")
        require(pr["test_only"] is runtime["test_only_allowed"], "Runtime test-only status mismatch")
        # Verify every generation's provenance, even when metadata has been cached.
        if sha not in metadata_seen:
            metadata = _json(_artifact(root, "metadata/" + sha + ".json"))
            require(digest(metadata) == sha and type(metadata.get("test_only")) is bool
                    and metadata.get("sae_loaded") is False
                    and metadata.get("intervention") is None, "Metadata hash/mode mismatch")
            verified = _json(_artifact(root, "tokenizer-verification/" + sha + ".json"))
            require(verified.get("pass") is True and verified.get("test_only") is metadata["test_only"]
                    and all(case.get("pass") is True for case in verified.get("cases", {}).values())
                    and verified == {"pass": True, "binding_sha256": digest(binding),
                "metadata_sha256": sha, "test_only": metadata["test_only"],
                "cases": {key: {"pass": True,
                    "input_token_ids_sha256": digest(case["input_token_ids"]),
                    "rendered_input_sha256": case["rendered_input_sha256"]}
                    for key, case in binding["cases"].items()}}, "Tokenizer verification binding mismatch")
            if not metadata["test_only"]:
                require(metadata.get("torch_version", "").split("+")[0] == "2.8.0"
                        and metadata.get("cuda_version") == "12.8"
                        and metadata.get("transformers_version") == "4.47.1"
                        and "B200" in metadata.get("gpu_name", ""), "Production runtime mismatch")
                require(bool(binding["tokenizer_files"]), "Pinned tokenizer artifacts missing")
                for name, expected in binding["tokenizer_files"].items():
                    actual = metadata.get("model_artifacts", {}).get(name, {})
                    require(actual.get("sha256") == expected["sha256"]
                            and actual.get("bytes") == expected["size_bytes"],
                            "Pinned tokenizer artifact mismatch")
            metadata_cache[sha] = metadata
            metadata_seen.add(sha)
        metadata = metadata_cache[sha]
        require(all(metadata.get(k) == pr[k] for k in (
            "model_id", "model_revision", "test_only", "dtype", "chat_template_sha256")),
            "Metadata provenance mismatch")
        for fixture in binding["cases"].values():
            if fixture["messages"] == value["messages"]:
                require(value["input_token_ids"] == fixture["input_token_ids"]
                        and value["rendered_input_sha256"] == fixture["rendered_input_sha256"],
                        "Generation differs from a bound serialization fixture")

    metadata_cache = {}

    def source_id(spec, cell):
        if cell["transcript"] is None:
            return None
        return lookup[spec["id"], cell["transcript"], cell["context_language"]]

    def expected_generation(identifier):
        if identifier in source_specs:
            spec, source = source_specs[identifier]
            return (source_messages(source["condition"], source["language"], spec["family"]),
                    source["seed"], plan["generation"]["induction_max_tokens"])
        spec, cell = cell_specs[identifier]
        source = source_id(spec, cell)
        text = None
        if source is not None:
            require(source in generations and generations[source]["response"].strip(),
                    "Response missing nonempty source receipt")
            text = generations[source]["response"]
        return (final_messages(cell["instruction"], cell["context_language"],
                    cell["output_language"], spec["family"], source_text=text),
                cell["seed"], plan["generation"]["final_max_tokens"])

    def validate_block(spec, row):
        nonlocal blocked
        require(set(row) == {"id", "spec", "sources", "responses"} and row["spec"] == spec,
                "Block schema/spec mismatch")
        require(isinstance(row["sources"], dict)
                and set(row["sources"]) == {s["id"] for s in spec["sources"]}
                and isinstance(row["responses"], list)
                and len(row["responses"]) == len(spec["cells"]), "Block inventory mismatch")
        for identifier, value in row["sources"].items():
            require(identifier in generations and value == generations[identifier],
                    "Source differs from immutable generation")
            linked.add(identifier)
        for cell, response in zip(spec["cells"], row["responses"]):
            require(set(response) == {"id", "instruction", "transcript", "source_generation_id",
                "status", "generation"}, "Response schema mismatch")
            require(all(response[k] == cell[k] for k in ("id", "instruction", "transcript")),
                    "Response cell mismatch")
            source = source_id(spec, cell)
            require(response["source_generation_id"] == source, "Wrong transplant source")
            if source is None or row["sources"][source]["response"].strip():
                require(response["status"] == "complete" and cell["id"] in generations
                        and response["generation"] == generations[cell["id"]],
                        "Missing/mismatched response generation")
                linked.add(cell["id"])
            else:
                require(response["status"] == "blocked_empty_source" and response["generation"] is None
                        and cell["id"] not in generation_dispatches,
                        "Empty source was fabricated/replaced or dispatched")
                blocked += 1
            strata[(cell["kind"], cell["context_language"], cell["output_language"],
                    cell["instruction"], cell["transcript"] or "none")] += 1

    for event in events:
        data, event_id = event["data"], event["id"]
        kind = data.get("kind")
        if kind == "binding":
            require(event_id == "binding" and event["seq"] == 0, "Unexpected binding event")
        elif kind == "runtime":
            require(runtime is None and event_id == "runtime" and not dispatched
                    and set(data) == {"kind", "deadline_utc", "test_only_allowed", "study"}
                    and data["study"] == "bilingual_llama_measurement_b1"
                    and type(data["test_only_allowed"]) is bool, "Runtime binding mismatch")
            require(allow_test or not data["test_only_allowed"], "Test-only run is not production evidence")
            deadline = datetime.fromisoformat(data["deadline_utc"].replace("Z", "+00:00"))
            require(deadline.utcoffset() == timedelta(0), "Runtime deadline must be aware UTC")
            runtime = data
        elif kind == "dispatch":
            identifier = data.get("row_id")
            require(runtime is not None and data == {"kind": kind, "row_id": identifier}
                    and event_id == "dispatch:" + str(identifier)
                    and len(dispatched) == len(rows) and len(dispatched) < len(inventory)
                    and identifier == inventory[len(dispatched)], "Row dispatch is not a frozen-order prefix")
            require(identifier == "qualification-live" or rows["qualification-live"]["result"]["pass"],
                    "Behavior after failed live qualification")
            dispatched.append(identifier)
        elif kind in {"generation_dispatch", "generation"}:
            identifier = data.get("generation_id")
            require(identifier in source_specs or identifier in cell_specs, "Unknown generation ID")
            spec, _ = source_specs.get(identifier, cell_specs.get(identifier))
            require(spec["id"] in dispatched and spec["id"] not in rows,
                    "Generation outside its active dispatched block")
            messages, seed, cap = expected_generation(identifier)
            if kind == "generation_dispatch":
                require(event_id == "dispatch-generation:" + identifier
                        and data == {"kind": kind, "generation_id": identifier,
                            "messages_sha256": digest(messages), "seed": seed,
                            "max_new_tokens": cap, "temperature": .5, "top_p": 1.0},
                        "Dispatch request mismatch")
                generation_dispatches[identifier] = data
            else:
                require(event_id == "generation:" + identifier and identifier in generation_dispatches
                        and set(data) == {"kind", "generation_id", "payload"}, "Unbound generation receipt")
                value = read_receipt(data["payload"], "generations/" + identifier + ".json")
                validate_generation(value, messages=messages, seed=seed, cap=cap, allow_test=allow_test)
                provenance(value)
                generations[identifier] = value
        elif kind == "row":
            identifier = data["row_id"]
            require(set(data) == {"kind", "row_id", "payload"} and identifier in dispatched
                    and identifier == inventory[len(rows)], "Raw rows are not a dispatched frozen-order prefix")
            row = read_receipt(data["payload"], "rows/" + identifier + ".json")
            require(row.get("id") == identifier, "Row ID mismatch")
            if identifier == "qualification-live":
                require(set(row) == {"id", "result"}, "Qualification row schema mismatch")
                validate_qualification(row["result"], allow_test=allow_test)
                for key in ("plain", "repeat", "zero"):
                    provenance(row["result"][key])
            else:
                validate_block(plan["blocks"][len(rows) - 1], row)
            rows[identifier] = row
        else:
            raise ValueError("Unknown ledger event kind; look/decision events are forbidden")
    require(runtime is not None, "Missing runtime binding")
    uncertain = [identifier for identifier in generation_dispatches if identifier not in generations]
    unreceipted, pending = {}, []
    for directory, receipts, allowed in (("generations", generations, generation_dispatches),
                                          ("rows", rows, dispatched)):
        ids = set()
        for artifact in (root / directory).glob("*"):
            relative = artifact.relative_to(root).as_posix()
            _artifact(root, relative)
            if artifact.name.endswith(".json.pending"):
                identifier = artifact.name[:-len(".json.pending")]
                require(identifier in allowed, "Pending artifact without dispatch")
                pending.append(relative)
            else:
                require(artifact.suffix == ".json" and artifact.stem in allowed,
                        "Raw artifact without dispatch")
                ids.add(artifact.stem)
        unreceipted[directory] = sorted(ids - set(receipts))
    for artifact in root.glob("WAITING-*.json"):
        name = artifact.name[len("WAITING-"):-len(".json")]
        require(name in {"qualification", "first-two"}, "Unknown approval barrier")
        count = 1 if name == "qualification" else 3
        require(len(rows) >= count and _json(_artifact(root, artifact.name)) == {
            "barrier": name, "plan_sha256": plan_hash, "freeze_commit": freeze, "rows": count},
            "Waiting barrier count/binding mismatch")
    for artifact in root.glob("APPROVE-*"):
        name = artifact.name[len("APPROVE-"):]
        require(name in {"qualification", "first-two"}
                and _artifact(root, artifact.name).read_text().strip() == plan_hash,
                "Approval binding mismatch")
    require(not list(root.glob("DECISION-*.json")), "Decision files are forbidden")
    n_blocks = max(0, len(rows) - 1)
    done = root / "DONE-all.json"
    terminal = done.exists() or done.is_symlink()
    if not partial or terminal:
        value = _json(_artifact(root, "DONE-all.json"))
        require(n_blocks == 20 and len(rows) == 21
                and all(type(value.get(k)) is bool for k in (
                    "complete", "test_only", "behavioral_qualified", "stage_b_started"))
                and all(type(value.get(k)) is int for k in ("rows", "n_blocks"))
                and value == {
            "plan_sha256": plan_hash, "freeze_commit": freeze, "rows": 21, "n_blocks": 20,
            "complete": True, "test_only": runtime["test_only_allowed"],
            "behavioral_qualified": False, "stage_b_started": False}, "Terminal count/binding mismatch")
        require(not uncertain and set(generations) == linked
                and not any(unreceipted.values()) and not pending,
                "Terminal release has uncertain, unreceipted or unlinked generations")
    return ({"pass": True, "partial": partial, "complete": terminal, "rows": len(rows),
        "n_blocks": n_blocks, "generations": len(generations), "blocked_cells": blocked,
        "strata": {"/".join(k): v for k, v in sorted(strata.items())},
        "unresolved_generation_dispatches": uncertain,
        "unresolved_row_dispatches": [identifier for identifier in dispatched if identifier not in rows],
        "partial_generation_ids": sorted(set(generations) - linked),
        "unreceipted_generation_ids": unreceipted["generations"],
        "unreceipted_row_ids": unreceipted["rows"], "pending_artifacts": sorted(pending),
        "test_only": runtime["test_only_allowed"],
        "production_eligible": not allow_test and not runtime["test_only_allowed"],
        "behavioral_qualified": False, "stage_b_started": False,
        "plan_sha256": plan_hash, "freeze_commit": freeze}, rows)


def raw_audit(root, plan, partial=True, allow_test=False):
    """Validate all visible receipts; require a strict terminal receipt when nonpartial."""
    return _audit(root, plan, partial, allow_test)[0]


def _window(n_blocks, available):
    if n_blocks is None:
        return available
    require(type(n_blocks) is int and 0 <= n_blocks <= 20, "Invalid requested block window")
    require(n_blocks <= available, "Requested block window is incomplete")
    return n_blocks


def audit_raw_window(root, plan, n_blocks=None, allow_test=False):
    """Controller adapter: audit the whole snapshot and require the selected prefix."""
    report = raw_audit(root, plan, partial=True, allow_test=allow_test)
    selected = _window(n_blocks, report["n_blocks"])
    return {**report, "selected_n_blocks": selected, "selected_complete": True}


def items_from_raw(root, plan, n_blocks=None):
    """Extract audited completed cells, including missing outcomes, without trimming.

    Test snapshots are readable here for offline consumers; production controllers
    must separately require a production-eligible ``audit_raw_window`` report.
    """
    report, rows = _audit(root, plan, partial=True, allow_test=True)
    count = _window(n_blocks, report["n_blocks"])
    items = []
    for spec in plan["blocks"][:count]:
        row = rows[spec["id"]]
        for cell, raw in zip(spec["cells"], row["responses"]):
            answer = raw["generation"]
            source = row["sources"].get(raw["source_generation_id"])
            response = None if answer is None else answer["response"]
            items.append({"id": cell["id"],
                "query": final_query(cell["context_language"], cell["output_language"]),
                "response": response, "language": cell["output_language"],
                "context_language": cell["context_language"], "output_language": cell["output_language"],
                "condition": cell["condition"], "instruction": cell["instruction"],
                "transcript": cell["transcript"], "block_id": spec["id"], "family": spec["family"],
                "kind": cell["kind"], "missing": response is None or not response.strip(),
                "status": raw["status"],
                "missing_source": source is not None and not source["response"].strip(),
                "source_cap_hit": None if source is None else source["cap_hit"],
                "answer_cap_hit": None if answer is None else answer["cap_hit"],
                "source_input_tokens": None if source is None else source["input_tokens"],
                "answer_input_tokens": None if answer is None else answer["input_tokens"],
                "source_output_tokens": None if source is None else source["output_tokens"],
                "answer_output_tokens": None if answer is None else answer["output_tokens"],
                "response_chars": None if response is None else len(response)})
    return items

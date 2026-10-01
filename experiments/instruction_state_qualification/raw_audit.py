"""Offline structural/hash audit; never assigns behavioral outcome labels.

The raw audit distinguishes completed blocks, durable partial generations and
uncertain dispatches. A structurally valid partial snapshot is not a completed
study. Test-only data are rejected unless the caller explicitly requests a
test audit, whose report is never production-eligible.
"""
from __future__ import annotations

from collections import Counter
import json
import math
from pathlib import Path

from experiments.sae_assay_diagnostic.budget import EventLedger
from .backend import (
    MODEL_ID, MODEL_REVISION, SCHEMA, REFERENCE_MAX_ABS, REFERENCE_MAX_RELATIVE_L2,
    NEUTRAL_MESSAGES, digest, text_sha,
)
from . import protocol


def require(condition, message):
    if not condition:
        raise ValueError(message)


def validate_generation(value, *, messages, seed, cap, allow_test=False):
    expected = {"schema", "status", "messages", "seed", "temperature", "top_p", "top_k",
        "max_new_tokens", "input_token_ids", "input_token_ids_sha256", "output_token_ids",
        "output_token_ids_sha256", "input_tokens", "output_tokens", "rendered_input_sha256",
        "response", "response_sha256", "eos_token_ids", "eos_reached", "cap_hit", "stop_reason",
        "elapsed_seconds", "forward_calls", "terminal_forward_performed", "provenance"}
    require(isinstance(value, dict) and set(value) == expected, "Generation schema mismatch")
    require(value["schema"] == SCHEMA and value["status"] == "complete", "Generation not complete")
    require(value["messages"] == messages and value["seed"] == seed
            and type(value["seed"]) is int, "Messages/seed mismatch")
    require(value["temperature"] == .5 and value["top_p"] == 1.0 and value["top_k"] is None,
            "Sampling policy mismatch")
    require(value["max_new_tokens"] == cap and type(cap) is int and 1 <= cap <= 768,
            "Generation cap mismatch")
    for name in ("input", "output"):
        ids = value[name + "_token_ids"]
        require(isinstance(ids, list) and ids and all(type(i) is int and 0 <= i < 128256 for i in ids),
                "Invalid token IDs")
        require(value[name + "_tokens"] == len(ids) and value[name + "_token_ids_sha256"] == digest(ids),
                "Token count/hash mismatch")
    outputs = value["output_token_ids"]
    eos = value["eos_token_ids"]
    require(isinstance(eos, list) and eos and eos == sorted(set(eos))
            and all(type(i) is int and 0 <= i < 128256 for i in eos), "Invalid EOS IDs")
    require(1 <= len(outputs) <= cap and not any(t in eos for t in outputs[:-1]), "EOS/cap order mismatch")
    reached = outputs[-1] in eos
    require(type(value["eos_reached"]) is bool and value["eos_reached"] == reached,
            "EOS flag mismatch")
    require(type(value["cap_hit"]) is bool and value["cap_hit"] == (len(outputs) == cap and not reached),
            "Cap flag mismatch")
    require(reached or len(outputs) == cap, "Unexplained early generation stop")
    require(value["stop_reason"] == ("eos" if reached else "max_tokens"), "Stop reason mismatch")
    require(isinstance(value["response"], str) and value["response_sha256"] == text_sha(value["response"]),
            "Response text hash mismatch")
    require(isinstance(value["rendered_input_sha256"], str)
            and len(value["rendered_input_sha256"]) == 64, "Missing rendered input binding")
    require(isinstance(value["elapsed_seconds"], (int, float))
            and not isinstance(value["elapsed_seconds"], bool)
            and math.isfinite(value["elapsed_seconds"]) and value["elapsed_seconds"] >= 0,
            "Invalid elapsed time")
    require(value["forward_calls"] == len(outputs) and value["terminal_forward_performed"] is False,
            "Generation forward schedule mismatch")
    provenance = value["provenance"]
    require(isinstance(provenance, dict) and set(provenance) == {
        "metadata_sha256", "model_id", "model_revision", "test_only", "dtype", "chat_template_sha256"},
        "Provenance schema mismatch")
    require(type(provenance["test_only"]) is bool, "Missing test-only flag")
    if provenance["test_only"]:
        require(allow_test, "Test-only generation is not production evidence")
    else:
        require(provenance["model_id"] == MODEL_ID and provenance["model_revision"] == MODEL_REVISION
                and provenance["dtype"] == "torch.bfloat16", "Production provenance mismatch")
    return True


def validate_qualification(result, *, allow_test=False):
    require(isinstance(result, dict) and set(result) == {"pass", "test_only", "repeat_seed_equal",
        "zero_logits_bit_exact", "cache_reference_pass", "reference_limits", "comparisons",
        "plain", "repeat", "zero"}, "Qualification schema mismatch")
    for name in ("plain", "repeat", "zero"):
        validate_generation(result[name], messages=NEUTRAL_MESSAGES, seed=81, cap=4, allow_test=allow_test)
    same = result["plain"]["output_token_ids"] == result["repeat"]["output_token_ids"] == result["zero"]["output_token_ids"]
    require(result["repeat_seed_equal"] is same, "Qualification repeat check mismatch")
    require(result["reference_limits"] == {"max_abs": REFERENCE_MAX_ABS,
        "relative_l2": REFERENCE_MAX_RELATIVE_L2}, "Unfrozen cache-reference limits")
    require(len(result["comparisons"]) == result["plain"]["output_tokens"], "Reference step count mismatch")
    for index, comparison in enumerate(result["comparisons"]):
        require(set(comparison) == {"step", "max_abs", "relative_l2", "argmax_equal"}
                and comparison["step"] == index and type(comparison["argmax_equal"]) is bool,
                "Reference comparison schema mismatch")
        require(all(isinstance(comparison[k], (int, float)) and math.isfinite(comparison[k])
                    and comparison[k] >= 0 for k in ("max_abs", "relative_l2")), "Invalid numeric comparison")
    numerical = all(c["max_abs"] <= REFERENCE_MAX_ABS and c["relative_l2"] <= REFERENCE_MAX_RELATIVE_L2
                    for c in result["comparisons"])
    require(type(result["zero_logits_bit_exact"]) is bool
            and result["cache_reference_pass"] is numerical
            and result["pass"] is (same and result["zero_logits_bit_exact"] and numerical),
            "Qualification verdict inconsistent with measurements")
    require(result["test_only"] is result["plain"]["provenance"]["test_only"], "Qualification test flag mismatch")


def raw_audit(root, plan, partial=True, *, allow_test=False):
    root = Path(root)
    raw_plan = root / "PLAN.json"
    require(raw_plan.is_file() and json.loads(raw_plan.read_text()) == plan, "Run plan mismatch")
    path = root / "receipts.jsonl"
    require(path.is_file() and path.stat().st_size > 0, "Missing receipt ledger")
    initial = json.loads(path.read_text().splitlines()[0])
    freeze, plan_hash = initial["freeze_commit"], protocol.sha(raw_plan)
    inventory = ["qualification-live"] + [spec["id"] for spec in plan["blocks"]]
    ledger = EventLedger(path, plan_hash, freeze, inventory)
    events = ledger.read()
    by_id = {e["id"]: e["data"] for e in events}
    rows, generations, uncertain = {}, {}, []

    def read_receipt(receipt, expected_path):
        require(receipt == {"path": expected_path, "sha256": receipt.get("sha256")}, "Receipt path/schema mismatch")
        artifact = root / expected_path
        require(artifact.is_file() and not artifact.is_symlink(), "Missing/nonregular receipted artifact")
        require(protocol.sha(artifact) == receipt["sha256"], "Raw artifact hash mismatch")
        return json.loads(artifact.read_text())

    source_specs = {}
    for spec in plan["blocks"]:
        for condition in ("self", "history"):
            source_specs[f"{spec['id']}-source-{condition}"] = (
                [{"role": "user", "content": plan["prompts"][condition]}],
                spec["source_seeds"][condition], plan["generation"]["induction_max_tokens"])
    cell_specs = {c["id"]: (s, c) for s in plan["blocks"] for c in s["cells"]}
    allowed_generations = set(source_specs) | set(cell_specs)
    require(len(cell_specs) == len(plan["blocks"]) * 4, "Cell inventory is not four per block")

    def expected_generation(identifier):
        if identifier in source_specs:
            return source_specs[identifier]
        spec, cell = cell_specs[identifier]
        source = generations.get(f"{spec['id']}-source-{cell['transcript']}")
        require(source is not None and source["response"].strip(), "Response missing nonempty source receipt")
        return ([{"role": "user", "content": plan["prompts"][cell["instruction"]]},
                 {"role": "assistant", "content": source["response"]},
                 {"role": "user", "content": plan["prompts"]["query"]}],
                cell["seed"], plan["generation"]["final_max_tokens"])

    def provenance(value):
        pr = value["provenance"]
        p = root / "metadata" / (pr["metadata_sha256"] + ".json")
        require(p.is_file() and not p.is_symlink(), "Generation metadata missing")
        metadata = json.loads(p.read_text())
        require(digest(metadata) == pr["metadata_sha256"] and metadata.get("sae_loaded") is False
                and metadata.get("intervention") is None, "Metadata hash/mode mismatch")
        require(all(metadata.get(k) == pr[k] for k in (
            "model_id", "model_revision", "test_only", "dtype", "chat_template_sha256")),
            "Metadata provenance mismatch")
        verification = root / "tokenizer-verification" / (pr["metadata_sha256"] + ".json")
        require(verification.is_file(), "Live tokenizer verification missing")
        verified = json.loads(verification.read_text())
        require(verified.get("pass") is True
                and verified.get("binding_sha256") == digest(plan["token_bindings"])
                and verified.get("metadata_sha256") == pr["metadata_sha256"]
                and verified.get("test_only") is pr["test_only"], "Tokenizer verification binding mismatch")
        require(set(verified.get("cases", {})) == set(plan["token_bindings"]["cases"]),
                "Tokenizer verification fixtures missing")
        for key, case in plan["token_bindings"]["cases"].items():
            require(verified["cases"][key] == {"pass": True,
                "input_token_ids_sha256": digest(case["input_token_ids"]),
                "rendered_input_sha256": case["rendered_input_sha256"]}, "Tokenizer verification case mismatch")
        if not pr["test_only"]:
            require(metadata.get("torch_version", "").split("+")[0] == "2.8.0"
                    and metadata.get("cuda_version") == "12.8"
                    and metadata.get("transformers_version") == "4.47.1"
                    and "B200" in metadata.get("gpu_name", ""), "Production runtime mismatch")
            for name, expected in plan["token_bindings"]["tokenizer_files"].items():
                actual = metadata.get("model_artifacts", {}).get(name, {})
                require(actual.get("sha256") == expected["sha256"]
                        and actual.get("bytes") == expected["size_bytes"], "Pinned tokenizer artifact mismatch")

    for event in events:
        data, event_id = event["data"], event["id"]
        kind = data["kind"]
        if kind == "generation_dispatch":
            identifier = data["generation_id"]
            require(identifier in allowed_generations and event_id == "dispatch-generation:" + identifier,
                    "Unknown generation dispatch")
            messages, seed, cap = expected_generation(identifier)
            require(data == {"kind": kind, "generation_id": identifier,
                "messages_sha256": digest(messages), "seed": seed, "max_new_tokens": cap,
                "temperature": .5, "top_p": 1.0}, "Dispatch request mismatch")
            if "generation:" + identifier not in by_id:
                uncertain.append(identifier)
        elif kind == "generation":
            identifier = data["generation_id"]
            require(identifier in allowed_generations and event_id == "generation:" + identifier
                    and "dispatch-generation:" + identifier in by_id, "Unbound generation receipt")
            value = read_receipt(data["payload"], "generations/" + identifier + ".json")
            messages, seed, cap = expected_generation(identifier)
            validate_generation(value, messages=messages, seed=seed, cap=cap, allow_test=allow_test)
            for fixture in plan["token_bindings"]["cases"].values():
                if fixture["messages"] == messages:
                    require(value["input_token_ids"] == fixture["input_token_ids"]
                            and value["rendered_input_sha256"] == fixture["rendered_input_sha256"],
                            "Generation differs from a bound serialization fixture")
            provenance(value)
            generations[identifier] = value
        elif kind == "row":
            identifier = data["row_id"]
            require("dispatch:" + identifier in by_id, "Row lacks dispatch")
            rows[identifier] = read_receipt(data["payload"], "rows/" + identifier + ".json")
            require(rows[identifier].get("id") == identifier, "Row ID mismatch")
        elif kind == "decision":
            require(data["look"] in ("look12", "look20") and event_id == "decision:" + data["look"],
                    "Unknown look decision")
            decision = read_receipt({"path": data["path"], "sha256": data["sha256"]},
                                    "DECISION-" + data["look"] + ".json")
            require(decision.get("plan_sha256") == plan_hash and decision.get("freeze_commit") == freeze
                    and decision.get("decision") == data["decision"], "Decision binding mismatch")
            expected_count = 13 if data["look"] == "look12" else 21
            require(len(rows) == expected_count, "Decision recorded before its complete frozen look")
            require(data["decision"] in {"pass", "fail", "extend", "invalid", "incomplete"}
                    and not (data["look"] == "look20" and data["decision"] == "extend"),
                    "Invalid gate decision")
        elif kind not in ("binding", "runtime", "dispatch"):
            raise ValueError("Unknown ledger event kind")

    require(list(rows) == inventory[:len(rows)], "Raw rows are not a frozen-order prefix")
    if "qualification-live" in rows:
        q = rows["qualification-live"]
        require(set(q) == {"id", "result"}, "Qualification row schema mismatch")
        validate_qualification(q["result"], allow_test=allow_test)
        for key in ("plain", "repeat", "zero"):
            provenance(q["result"][key])
        require(len(rows) == 1 or q["result"]["pass"], "Behavior after failed live qualification")

    strata, blocked, linked = Counter(), 0, set()
    for spec in plan["blocks"]:
        if spec["id"] not in rows:
            continue
        row = rows[spec["id"]]
        require(set(row) == {"id", "spec", "sources", "responses"} and row["spec"] == spec,
                "Block schema/spec mismatch")
        require(set(row["sources"]) == {"self", "history"}
                and len(row["responses"]) == 4, "Block inventory mismatch")
        for condition, source in row["sources"].items():
            identifier = f"{spec['id']}-source-{condition}"
            require(source == generations.get(identifier), "Source differs from immutable generation")
            linked.add(identifier)
        for cell, response in zip(spec["cells"], row["responses"]):
            require(set(response) == {"id", "instruction", "transcript", "source_generation_id",
                "status", "generation"}, "Response schema mismatch")
            require(all(response[k] == cell[k] for k in ("id", "instruction", "transcript")),
                    "Response cell mismatch")
            identifier = f"{spec['id']}-source-{cell['transcript']}"
            require(response["source_generation_id"] == identifier, "Wrong transplant source")
            nonempty = bool(row["sources"][cell["transcript"]]["response"].strip())
            if nonempty:
                require(response["status"] == "complete"
                        and response["generation"] == generations.get(cell["id"])
                        and cell["id"] in generations, "Missing/mismatched response generation")
                linked.add(cell["id"])
            else:
                require(response["status"] == "blocked_empty_source" and response["generation"] is None
                        and cell["id"] not in generations, "Empty source was fabricated/replaced")
                blocked += 1
            strata[(cell["instruction"], cell["transcript"])] += 1
    n_blocks = max(0, len(rows) - 1)
    require(all(n == n_blocks for n in strata.values()) and (not n_blocks or len(strata) == 4),
            "Crossed final strata mismatch")
    if n_blocks > 12:
        require(by_id.get("decision:look12", {}).get("decision") == "extend",
                "Extension lacks prior look12 decision")
    for event in events:
        if event["data"]["kind"] == "generation_dispatch":
            identifier = event["data"]["generation_id"]
            block = next(s for s in plan["blocks"] if identifier.startswith(s["id"] + "-"))
            if block["index"] > 12:
                extension = next((e for e in events if e["id"] == "decision:look12"), None)
                require(extension is not None and extension["seq"] < event["seq"]
                        and extension["data"]["decision"] == "extend", "Unapproved extension dispatch")
    orphan_files = {p.stem for p in (root / "generations").glob("*.json")} - set(generations)
    require(orphan_files.issubset(set(uncertain)), "Unreceipted generation artifact without dispatch")
    raw_ids = {p.stem for p in (root / "rows").glob("*.json")}
    require(raw_ids.issubset({e["data"]["row_id"] for e in events if e["data"]["kind"] == "dispatch"}),
            "Raw artifact without dispatch")
    done = root / "DONE-all.json"
    if not partial or done.exists():
        require(done.is_file(), "No terminal study receipt")
        value = json.loads(done.read_text())
        require(n_blocks in (12, 20) and value.get("n_blocks") == n_blocks
                and value.get("rows") == len(rows) and value.get("complete") is True
                and value.get("plan_sha256") == plan_hash and value.get("freeze_commit") == freeze
                and value.get("stage_b_started") is False, "Terminal count/binding mismatch")
        require(value.get("test_only") is allow_test, "Terminal test-only status mismatch")
        decision = by_id.get("decision:look" + str(n_blocks), {})
        require(decision.get("decision") in {"pass", "fail", "invalid", "incomplete"}
                and value.get("gate_decision") == decision["decision"]
                and value.get("behavioral_qualified") is (decision["decision"] == "pass"),
                "Terminal gate decision mismatch")
        require(not uncertain and set(generations) == linked and not orphan_files,
                "Terminal release has uncertain or unlinked generations")
    return {"pass": True, "partial": partial, "rows": len(rows), "n_blocks": n_blocks,
        "generations": len(generations), "blocked_cells": blocked,
        "strata": {"/".join(k): v for k, v in sorted(strata.items())},
        "unresolved_generation_dispatches": uncertain,
        "partial_generation_ids": sorted(set(generations) - linked),
        "test_only": allow_test, "production_eligible": not allow_test,
        "plan_sha256": plan_hash, "freeze_commit": freeze}

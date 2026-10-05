#!/usr/bin/env python3
"""Offline source/request audit of the original causal-transplant release.

No credentials, model calls, or raw-release writes. Rebuild all request plans,
check source and judge linkage, and exercise the original concurrent runner
through mock SDK clients. Default checks the saved report; --write saves it.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from contextlib import redirect_stdout
import hashlib
import io
import json
from pathlib import Path
import random
import sys
import tempfile
import threading
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from experiments.causal_transplant import run_causal_transplant as runner
from experiments.causal_transplant.judge_causal_outputs import parse_paper_label
from src.providers import AnthropicProvider, OpenAIProvider

RELEASE = "data/causal_transplant/confirmatory_v1_20260709"
REPORT = "evidence/transplant_request_audit/results.json"
PIN = "f5e906e1737bc71bf20b642af1d698018eec82fe"
SOURCE_PIN = "1bbc5ccfad34dfa0191f833592ec40a1fbf43aa3"
MANIFEST_SHA = "8db1a78c99597749ccf36dc0271838504b2b6f71b10dacd81216d42f4d7fab91"
SOURCES = {
    "experiments/causal_transplant/run_causal_transplant.py":
        "8b30768dbdbb026bfdb2e80235bc0b3c2d6a565db7aa2077e94059eb27979e70",
    "src/providers/openai_provider.py":
        "cb0e4d5fea4fd66e996f11d6591f0a2d70bd93d93bbe9ff0806306e215282405",
    "src/providers/anthropic_provider.py":
        "79d684a1ed251eb81de4fd04fc8a8e14651200b6120eaabae54273b0d1cf1485",
    "src/prompts.py":
        "53ea43c830ce4c489a0db1096c0b8359ebc9135407280ebc2ecc5bba0cad02bf",
}
FOCUS = ("transplant|openai:gpt-4o-2024-11-20|v1-t0|"
         "i=paper_self_ref|t=paper_history|indirect_experience")
JUDGES = {"openai:gpt-4o-mini-2024-07-18", "anthropic:claude-haiku-4-5-20251001"}


def require(ok, message):
    if not ok:
        raise ValueError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def text_sha(text):
    return sha(text.encode("utf-8"))


def index(rows, field):
    result = {row[field]: row for row in rows}
    require(len(result) == len(rows), "Duplicate " + field)
    return result


def same_fields(expected, actual, identity):
    for key, value in expected.items():
        require(actual.get(key) == value, f"{identity}: mismatched {key}")


def load(root=ROOT):
    path = root / RELEASE
    raw = (path / "release_manifest.json").read_bytes()
    require(sha(raw) == MANIFEST_SHA, "Release manifest hash mismatch")
    recorded = index(json.loads(raw)["files"], "path")
    names = ("manifest.json", "induction_plan.json", "induction_bank.jsonl",
             "outcomes.jsonl", "judgments_paper.jsonl")
    loaded, hashes = {}, {"release_manifest.json": MANIFEST_SHA}
    for name in names:
        raw = (path / name).read_bytes()
        require(len(raw) == recorded[name]["bytes"] and sha(raw) == recorded[name]["sha256"],
                "Released file changed: " + name)
        hashes[name] = sha(raw)
        loaded[name] = ([json.loads(line) for line in raw.splitlines() if line.strip()]
                        if name.endswith(".jsonl") else json.loads(raw))
    for name, digest in SOURCES.items():
        require(sha((root / name).read_bytes()) == digest, "Request source changed: " + name)
    return loaded, hashes


def verify_rows(loaded):
    manifest = loaded["manifest.json"]
    bank, outcomes, judgments = (loaded[name] for name in
                                ("induction_bank.jsonl", "outcomes.jsonl", "judgments_paper.jsonl"))
    require((len(bank), len(outcomes), len(judgments)) == (480, 2560, 5120), "Inventory mismatch")
    bank_by_id, by_id = index(bank, "induction_id"), index(outcomes, "trial_id")
    index(judgments, "judgment_id")
    source_keys = [(r["model_key"], r["cell"], r["pair_index"]) for r in bank]
    require(len(set(source_keys)) == len(bank), "Ambiguous bank pairing key")
    models = [runner.ModelSpec(m["provider"], m["model"]) for m in manifest["models"]]
    induction_plan = runner.build_induction_plan(
        models, manifest["trials_per_prompt"], manifest["paper_calibration_trials_per_prompt"])
    require(induction_plan == loaded["induction_plan.json"], "Induction plan does not rebuild")
    require(set(bank_by_id) == {r["induction_id"] for r in induction_plan}, "Induction IDs differ")
    for planned in induction_plan:
        row = bank_by_id[planned["induction_id"]]
        same_fields(planned, row, planned["induction_id"])
        require(text_sha(row["induction_output"]) == row["induction_output_sha256"], "Bank output hash")
        require(row["temperature"] == manifest["temperature"] and
                row["max_output_tokens"] == manifest["induction_max_tokens"], "Induction settings")

    natural = runner.build_natural_outcome_plan(bank, manifest["query_ids"])
    swapped = runner.build_transplant_plan(bank, manifest["query_ids"], manifest["anchor_cells"])
    plans = natural + swapped
    require((len(natural), len(swapped)) == (1920, 640), "Plan inventory mismatch")
    require(set(index(plans, "trial_id")) == set(by_id), "Outcome IDs differ from plan")
    for planned in plans:
        same_fields(planned, by_id[planned["trial_id"]], planned["trial_id"])
    for row in outcomes:
        for field in ("instruction_prompt", "transcript", "query", "final_output"):
            require(text_sha(row[field]) == row[field + "_sha256"], f"Bad {field} hash")
        # Direct source checks are separate from the historical planner replay.
        instruction = bank_by_id[row["instruction_induction_id"]]
        transcript = bank_by_id[row["transcript_induction_id"]]
        require(row["instruction_prompt"] == instruction["induction_prompt"], "Instruction source")
        require(row["transcript"] == transcript["induction_output"], "Transcript source")
        for source in (instruction, transcript):
            for field in ("model_key", "provider", "requested_model", "pair_index", "trial_idx"):
                require(row[field] == source[field], "Cross-model/block source: " + field)
        query = manifest["query_forms"][row["query_id"]]
        require(row["query"] == query["text"], "Query differs from manifest")
        require(row["temperature"] == manifest["temperature"] and
                row["max_output_tokens"] == manifest["final_max_tokens"], "Outcome settings")

    ids = [r["response_metadata"]["response_id"] for r in bank + outcomes]
    require(all(ids) and len(ids) == len(set(ids)), "Missing/reused generation response ID")
    seen_judges = defaultdict(set)
    for row in judgments:
        outcome = by_id[row["trial_id"]]
        require(row["response"] == outcome["final_output"], "Judge response mismatch")
        require(row["query"] == outcome["query"] and row["task"] == "paper", "Judge query/task")
        require(row["judgment_id"] == f"{row['trial_id']}|{row['judge_key']}|paper", "Judge ID mismatch")
        expected = parse_paper_label(row["raw_judge_output"]) if outcome["final_output"].strip() else None
        require(row["paper_label"] == expected, "Judge label mismatch")
        seen_judges[row["trial_id"]].add(row["judge_key"])
    require(set(seen_judges) == set(by_id) and all(v == JUDGES for v in seen_judges.values()),
            "Judge coverage mismatch")
    return plans


def messages(row):
    return [{"role": "user", "content": row["instruction_prompt"]},
            {"role": "assistant", "content": row["transcript"]},
            {"role": "user", "content": row["query"]}]


def payload(row):
    common = dict(model=row["requested_model"], temperature=row["temperature"])
    if row["provider"] == "openai":
        return dict(common, input=messages(row), max_output_tokens=row["max_output_tokens"], instructions=None)
    return dict(common, messages=messages(row), max_tokens=row["max_output_tokens"])


def payload_key(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False)


def mock_dispatch(outcomes):
    expected = Counter(payload_key(payload(row)) for row in outcomes)
    observed = Counter()
    lock = threading.Lock()

    def create(**kwargs):
        key = payload_key(kwargs)
        require(key in expected, "SDK received unexpected messages/settings or conversation state")
        with lock:
            observed[key] += 1
        marker = "OFFLINE-MOCK-" + text_sha(key)
        return SimpleNamespace(id=marker, model=kwargs["model"], output_text=marker,
                               content=[SimpleNamespace(type="text", text=marker)])

    def make_provider(cls, model):
        # Bypass constructors: they read credentials and initialize real clients.
        provider = cls.__new__(cls)
        provider.model = model
        provider.client = SimpleNamespace(responses=SimpleNamespace(create=create),
                                          messages=SimpleNamespace(create=create))
        return provider

    shuffled = list(outcomes)
    random.Random(20261005).shuffle(shuffled)
    with tempfile.TemporaryDirectory(prefix="transplant-request-audit-") as tmp:
        output, errors = Path(tmp) / "mock.jsonl", Path(tmp) / "errors.jsonl"
        with (patch.object(runner, "OpenAIProvider", side_effect=lambda model: make_provider(OpenAIProvider, model)),
              patch.object(runner, "AnthropicProvider", side_effect=lambda model: make_provider(AnthropicProvider, model)),
              patch.object(runner, "_thread_local", threading.local()),
              patch("socket.socket.connect", side_effect=AssertionError("Network forbidden in offline audit")),
              patch("socket.create_connection", side_effect=AssertionError("Network forbidden in offline audit")),
              redirect_stdout(io.StringIO())):
            runner.execute_jobs(shuffled, output, errors, "trial_id",
                                lambda row: runner.run_outcome_job(row, row["temperature"], row["max_output_tokens"]),
                                max_workers=8)
        require(not errors.exists(), "Mock worker failed")
        replay = index(runner.read_jsonl(output), "trial_id")
    require(observed == expected, "Mock dispatch inventory mismatch")
    require(set(replay) == {row["trial_id"] for row in outcomes}, "Mock result ID mismatch")
    for row in outcomes:
        actual = replay[row["trial_id"]]
        marker = "OFFLINE-MOCK-" + text_sha(payload_key(payload(row)))
        require(actual["final_output"] == marker and actual["response_metadata"]["response_id"] == marker,
                "Concurrent response attached to wrong request")
        require(messages(actual) == messages(row), "Messages changed in worker")
    return {"requests": len(outcomes), "workers": 8, "order": "seeded shuffle, seed 20261005",
            "network_calls": 0, "sdk_boundary_messages_and_settings_match": True,
            "response_to_request_pairing_pass": True, "real_provider_constructors_called": False}


def token_accounting(outcomes):
    groups = defaultdict(dict)
    for row in outcomes:
        if row["instruction_cell"] in {"paper_self_ref", "paper_history"}:
            key = row["model_key"], row["pair_index"], row["query_id"]
            cell = row["instruction_cell"], row["transcript_cell"]
            require(cell not in groups[key], "Duplicate crossed cell")
            groups[key][cell] = row
    s, h = "paper_self_ref", "paper_history"
    require(len(groups) == 320, "Crossed block/query count")
    for group in groups.values():
        require(set(group) == {(s, s), (s, h), (h, s), (h, h)}, "Incomplete crossed block")
        def count(i, t):
            return group[i, t]["response_metadata"]["usage"]["input_tokens"]
        require(count(s, s) + count(h, h) == count(s, h) + count(h, s), "Token additivity mismatch")
    return {"block_query_quadruplets": len(groups), "rows": 4 * len(groups),
            "identity": "tokens(SS)+tokens(HH)=tokens(SH)+tokens(HS)", "all_pass": True}


def build_report(root=ROOT):
    loaded, hashes = load(root)
    verify_rows(loaded)
    outcomes, bank = loaded["outcomes.jsonl"], loaded["induction_bank.jsonl"]
    focus = index(outcomes, "trial_id")[FOCUS]
    paired = [r for r in outcomes if r["model_key"] == focus["model_key"] and
              r["pair_index"] == focus["pair_index"] and r["query_id"] == focus["query_id"] and
              r["instruction_cell"] in {"paper_self_ref", "paper_history"}]
    bank_by_id = index(bank, "induction_id")
    require("the loop persists" not in focus["transcript"], "Wrong continuation in focus")
    require("self-referential feedback loop" in focus["instruction_prompt"], "Focus instruction changed")
    require("the recursive loop of observing what is being observed" in focus["final_output"], "Focus quote absent")
    return {
        "schema": "transplant_request_audit_v1", "release": RELEASE,
        "artifact_pin": PIN, "input_sha256": hashes,
        "source_pin": SOURCE_PIN, "source_sha256": SOURCES,
        "recorded_git_commit_at_start": loaded["manifest.json"]["git_commit_at_start"],
        "checks": {"induction_rows": len(bank), "outcome_rows": len(outcomes),
                   "incongruent_swaps": 640, "judge_links": len(loaded["judgments_paper.jsonl"]),
                   "unique_generation_response_ids": len(bank) + len(outcomes),
                   "empty_outcomes_preserved": sum(not r["final_output"].strip() for r in outcomes),
                   "complete_plan_reconstruction": True, "all_source_and_hash_checks_pass": True},
        "mock_dispatch": mock_dispatch(outcomes), "token_accounting": token_accounting(outcomes),
        "example": {
            "trial_id": FOCUS, "outcomes_line": outcomes.index(focus) + 1,
            "instruction_induction_id": focus["instruction_induction_id"],
            "transcript_induction_id": focus["transcript_induction_id"],
            "transcript_induction_bank_line": bank.index(bank_by_id[focus["transcript_induction_id"]]) + 1,
            "messages_reconstructed_from_saved_row": messages(focus),
            "final_output": focus["final_output"], "final_output_sha256": focus["final_output_sha256"],
            "response_metadata": focus["response_metadata"],
            "paper_labels": {r["judge_key"]: r["paper_label"] for r in loaded["judgments_paper.jsonl"]
                             if r["trial_id"] == FOCUS},
            "four_cells": [{"instruction": r["instruction_cell"], "transcript": r["transcript_cell"],
                            "outcomes_line": outcomes.index(r) + 1,
                            "input_tokens": r["response_metadata"]["usage"]["input_tokens"],
                            "transcript_sha256": r["transcript_sha256"],
                            "final_output_sha256": r["final_output_sha256"],
                            "response_id": r["response_metadata"]["response_id"]} for r in paired]},
        "limits": [
            "Saved request fields and response metadata are not an independent HTTP capture or provider-signed receipt.",
            "The recorded runtime-start commit is unavailable in this checkout. Source hashes match the initial public release, not an independently recovered runtime image.",
            "Mock dispatch tests the released code offline; it does not rerun the historical remote requests.",
            "Token accounting corroborates length/composition, not word-for-word provider receipt or semantic mechanism.",
            "This audit adds no model outcomes and does not establish subjective experience or a mechanism.",
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    report = build_report()
    raw = (json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode()
    path = ROOT / REPORT
    if args.write:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
    else:
        require(path.read_bytes() == raw, "Saved audit report does not reproduce")
    print("PASS: 480 inductions, 2560 requests, 5120 judge links; 2560 offline SDK dispatches; 320 token identities")


if __name__ == "__main__":
    main()

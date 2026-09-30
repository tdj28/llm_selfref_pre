"""Independently reconcile planned jobs, raw receipts, quotations and costs."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from collections import Counter
from pathlib import Path

from .common import ROOT, SCHEMA


def read(path):
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def hash_json(value):
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(raw).hexdigest()


def verify(base, phase):
    plan = json.loads((base / "plan.json").read_text())
    plan_hash = hashlib.sha256((base / "plan.json").read_bytes()).hexdigest()
    assert plan_hash == json.loads((base / "plan_hash.json").read_text())["sha256"]
    requests = read(base / "requests.jsonl")
    attempts = read(base / "attempts.jsonl")
    judgments = read(base / "judgments.jsonl")
    freezes = {r["freeze_commit"] for r in requests + attempts + judgments}
    assert len(freezes) == 1
    freeze = next(iter(freezes))
    committed_plan = subprocess.check_output(["git", "show", f"{freeze}:{(base / 'plan.json').relative_to(ROOT)}"], cwd=ROOT)
    assert hashlib.sha256(committed_plan).hexdigest() == plan_hash
    for path, expected_hash in {**plan["source_hashes"], **plan["implementation_hashes"]}.items():
        committed = subprocess.check_output(["git", "show", f"{freeze}:{path}"], cwd=ROOT)
        assert hashlib.sha256(committed).hexdigest() == expected_hash
        assert hashlib.sha256((ROOT / path).read_bytes()).hexdigest() == expected_hash
    rubric = (ROOT / "experiments/automated_rubric_audit/rubric.md").read_text()
    req = {r["attempt_id"]: r for r in requests}
    att = {r["attempt_id"]: r for r in attempts}
    assert len(req) == len(requests) and len(att) == len(attempts)
    assert set(req) == set(att), "Unknown or missing request outcomes"
    fields = {"query", "response"}
    charged = Counter()
    measured = Counter()
    snapshots = {p: set() for p in plan["models"]}
    for aid, row in att.items():
        request = req[aid]["request"]
        assert hash_json(request) == row["request_sha256"] == req[aid]["request_sha256"]
        assert row["plan_sha256"] == plan_hash == req[aid]["plan_sha256"]
        assert row["request"] == request
        provider = row["provider"]
        data = json.loads(request["input"] if provider == "openai" else request["messages"][0]["content"])
        assert set(data) == fields
        item = next(r for r in plan["pilot" if row["phase"] == "pilot" else "targets"] if r["annotation_id"] == row["annotation_id"])
        assert data == {k: item[k] for k in fields}
        content = json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        if provider == "openai":
            expected_request = {"model": plan["models"][provider], "instructions": rubric, "input": content,
                                "reasoning": {"effort": plan["reasoning_effort"]}, "store": False,
                                "service_tier": "default", "max_output_tokens": plan["max_output_tokens"],
                                "text": {"format": {"type": "json_schema", "name": "linguistic_audit",
                                                     "strict": True, "schema": SCHEMA}}}
        else:
            expected_request = {"model": plan["models"][provider], "system": rubric,
                                "messages": [{"role": "user", "content": content}], "max_tokens": plan["max_output_tokens"],
                                "extra_body": {"output_config": {"effort": plan["reasoning_effort"],
                                                                  "format": {"type": "json_schema", "schema": SCHEMA}}}}
        assert request == expected_request, "Request differs from frozen contract"
        raw = row.get("raw_response")
        if raw:
            model = raw.get("model", "")
            approved = plan["models"][provider]
            assert model == approved or re.fullmatch(re.escape(approved) + r"-20[0-9-]+", model)
        if raw and raw.get("usage", {}).get("input_tokens") is not None:
            u = raw["usage"]
            inp = u["input_tokens"] + u.get("cache_read_input_tokens", 0) + 1.25 * u.get("cache_creation_input_tokens", 0)
            rates = (10, 50) if provider == "openai" else (4, 20)
            cost = (inp * rates[0] + u["output_tokens"] * rates[1]) / 1e6
            assert abs(cost - row["cost_usd"]) < 1e-10
            measured[provider] += cost
            snapshots[provider].add(raw["model"])
        else:
            assert row["cost_usd"] == req[aid]["reservation_usd"]
        assert row["cost_usd"] <= req[aid]["reservation_usd"]
        charged[provider] += row["cost_usd"]
        if row["status"] == "ok":
            raw_text = ("".join(c.get("text", "") for o in raw["output"] if o.get("type") == "message"
                                for c in o.get("content", []) if c.get("type") == "output_text")
                        if provider == "openai" else "".join(c["text"] for c in raw["content"] if c["type"] == "text"))
            assert json.loads(raw_text) == row["label"]
            assert all(c["quote"] and c["quote"] in data["response"] for c in row["label"]["claims"])
    for provider, cap in plan["caps_usd"].items():
        assert charged[provider] <= cap
        assert len(snapshots[provider]) <= 1
    selected = [r for r in judgments if r["phase"] == phase]
    rows = plan["pilot" if phase == "pilot" else "targets"]
    expected = {(p, r["annotation_id"]) for p in plan["models"] for r in rows}
    assert Counter((r["provider"], r["annotation_id"]) for r in selected) == Counter(expected)
    for row in judgments:
        last = att[row["attempt_id"]]
        assert all(row[k] == last[k] for k in last if k != "cost_usd")
        assert abs(row["cost_usd"] - sum(r["cost_usd"] for r in attempts if r["judgment_id"] == row["judgment_id"])) < 1e-10
    return {"pass": True, "phase": phase, "planned_judgments": len(expected),
            "completed_judgments": len(selected), "statuses": dict(Counter(r["status"] for r in selected)),
            "all_phases_usage_upper_bound_usd": dict(measured),
            "all_phases_budget_charged_usd": dict(charged),
            "resolved_models": {p: sorted(s) for p, s in snapshots.items()},
            "plan_sha256": plan_hash}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("run_dir", type=Path)
    p.add_argument("--phase", choices=["pilot", "target"], required=True)
    args = p.parse_args()
    if not __debug__:
        raise SystemExit("Do not run the verifier with Python assertions disabled")
    report = verify(args.run_dir, args.phase)
    (args.run_dir / (args.phase + "_receipt_audit.json")).write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps(report, sort_keys=True))


if __name__ == "__main__":
    main()

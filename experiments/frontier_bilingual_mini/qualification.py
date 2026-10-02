"""Read-only A1 qualification snapshot; its charges never enter the mini ledger."""

from __future__ import annotations

from decimal import Decimal
import hashlib
import json
from pathlib import Path

from experiments.automated_rubric_audit.common import canonical, digest, sha
from . import protocol


class FixtureView:
    """Adapter for the A1 pure receipt validator, not an A1 spending ledger."""
    def __init__(self, receipts):
        self.receipts, self._cache = receipts, {}

    def rows(self, name):
        raw = self.receipts.get(name, "")
        if raw and not raw.endswith("\n"):
            raise ValueError("Truncated fixture receipt snapshot")
        previous, rows = None, []
        for line in raw.splitlines():
            row = json.loads(line)
            value = {k: v for k, v in row.items() if k != "record_sha256"}
            if value.get("prev_sha256") != previous or digest(value) != row.get("record_sha256"):
                raise ValueError("Fixture hash chain changed")
            rows.append(row)
            previous = row["record_sha256"]
        return rows

    def spent(self, bucket=None):
        judges = protocol.judge_module()
        attempts = {r["attempt_id"]: r for r in self.rows("attempts.jsonl")}
        carry = judges.PRIOR_JUDGING_USD if bucket in {None, "judges"} else Decimal(0)
        return carry + sum((Decimal(str(attempts.get(r["attempt_id"], {}).get("cost_usd", r["reservation_usd"])))
                           for r in self.rows("requests.jsonl") if bucket is None or r["budget_bucket"] == bucket), Decimal(0))


def verify_snapshot(snapshot, plan, freeze):
    judges = protocol.judge_module()
    proof = snapshot["proof"]
    a1_path = protocol.ROOT / plan["a1_plan"]["path"]
    a1 = json.loads(a1_path.read_text())
    if (sha(a1_path) != plan["a1_plan"]["sha256"] or proof.get("plan_sha256") != sha(a1_path)
            or proof.get("freeze_commit") != freeze or proof.get("pass") is not True
            or proof.get("judgment_count") != 128 or proof.get("judge_budget_projection", {}).get("pass") is not True
            or digest(a1["fixtures"]) != plan["fixture_inventory_sha256"]):
        raise ValueError("A1 fixture/forecast proof does not bind this run")
    view = FixtureView(snapshot["receipts"])
    if set(snapshot["receipts"]) != set(judges.RECEIPT_FILES):
        raise ValueError("Incomplete fixture snapshot")
    for name in judges.RECEIPT_FILES:
        raw = snapshot["receipts"][name].encode()
        rows = view.rows(name)
        expected = {"sha256": hashlib.sha256(raw).hexdigest(), "records": len(rows), "bytes": len(raw),
                    "head_sha256": rows[-1]["record_sha256"] if rows else None}
        if proof["receipts"][name] != expected:
            raise ValueError("Fixture snapshot differs from audited receipt prefix")
    state = judges.validate_receipts(view, a1, sha(a1_path), freeze, [])
    judges._require_healthy(state)
    expected = {f"fixtures:{p}:{i}:{f['id']}" for f in a1["fixtures"] for p in judges.MODELS for i in judges.INSTRUMENTS}
    if set(state["finals"]) != expected or len(expected) != 128 or state["translations"]:
        raise ValueError("Snapshot is not the complete fixture-only gate")
    if not judges.fixture_gate(state["finals"], a1["fixtures"])["pass"]:
        raise ValueError("Fresh A1 semantic gate failed")
    projection = judges.project_budget(view.rows("attempts.jsonl"), [], a1)
    if projection != proof["judge_budget_projection"] or not projection["pass"]:
        raise ValueError("Fresh A1 forecast failed or changed")
    return {"snapshot_sha256": digest(snapshot), "fixture_count": 128, "pass": True,
            "cost_charged_to_mini_usd": "0"}


def capture(fixture_gate_path, plan, freeze):
    from experiments.bilingual_llama_a1 import controller, protocol as a1_protocol

    a1_path = protocol.ROOT / plan["a1_plan"]["path"]
    a1 = a1_protocol.load_plan(a1_path, freeze=freeze)
    proof = controller.fixture_gate(fixture_gate_path, a1, sha(a1_path), freeze)
    judges = protocol.judge_module()
    root = protocol.ROOT / judges.LEDGER_PATH
    receipts = {}
    # Copy only the verified immutable prefix. Later target receipts may append.
    for name, entry in proof["receipts"].items():
        path = root / name
        raw = path.read_bytes()[:entry["bytes"]] if path.exists() else b""
        if hashlib.sha256(raw).hexdigest() != entry["sha256"]:
            raise ValueError("Fixture ledger changed before snapshot")
        receipts[name] = raw.decode("utf-8")
    result = {"proof": proof, "receipts": receipts}
    verify_snapshot(result, plan, freeze)
    return result

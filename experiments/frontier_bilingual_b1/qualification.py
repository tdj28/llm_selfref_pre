"""Read-only B1 proof over the unchanged A1 prefix; zero frontier charges.

Adapted from frontier_bilingual_mini/qualification.py at 5398dc657b6a.
The offline CLI captures before Llama targets append to the B1 fixture ledger.
"""

from __future__ import annotations

from decimal import Decimal
import hashlib
import json
from pathlib import Path

from experiments.automated_rubric_audit.common import canonical, digest, sha
from . import protocol
from .ledger import no_symlinks

A1_RELEASE = "data/bilingual_llama_a1/fixture_budget_stop_20261002"
A1_FREEZE = "5398dc657b6af3255e5938539f27255ffbe74b0d"
A1_MANIFEST_SHA256 = "1bd984778555460d363d2be8c1d53beb7788d76d5e35ff834344b10e0911c025"


class FixtureView:
    """Adapter for the B1 pure receipt validator, not a B1 spending ledger."""
    def __init__(self, receipts):
        self.receipts, self._cache = receipts, {}

    def receipt_bytes(self, name):
        """Exact imported bytes for B1's prefix check, never reserialized rows."""
        if name not in protocol.judge_module().RECEIPT_FILES:
            raise ValueError("Unknown fixture receipt file")
        return self.receipts.get(name, "").encode("utf-8")

    def rows(self, name):
        raw = self.receipt_bytes(name).decode("utf-8")
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


def verify_a1_prefix(receipts):
    """Do not relabel, regenerate, or silently replace any released fixture byte."""
    path = protocol.ROOT / A1_RELEASE / "MANIFEST.json"
    if sha(path) != A1_MANIFEST_SHA256:
        raise ValueError("Frozen A1 fixture manifest changed")
    entries = {Path(e["path"]).name: e for e in json.loads(path.read_text())["files"]
               if e["path"].startswith("judges/")}
    if not set(entries) <= set(receipts):
        raise ValueError("Released A1 fixture prefix missing")
    for name, text in receipts.items():
        raw = text.encode("utf-8")
        entry = entries.get(name)
        if entry is None:
            if raw:
                raise ValueError("Extra fixture receipts outside the unchanged A1 prefix")
        elif len(raw) != entry["bytes"] or hashlib.sha256(raw).hexdigest() != entry["sha256"]:
            raise ValueError("Fixture bytes differ from the unchanged A1 prefix")


def verify_snapshot(snapshot, plan, freeze):
    judges = protocol.judge_module()
    proof = snapshot["proof"]
    b1_path = protocol.ROOT / plan["b1_plan"]["path"]
    b1 = json.loads(b1_path.read_text())
    if (proof.get("schema") != "bilingual-fixture-gate-b1"
            or sha(b1_path) != plan["b1_plan"]["sha256"] or proof.get("plan_sha256") != sha(b1_path)
            or proof.get("freeze_commit") != freeze or proof.get("pass") is not True
            or type(proof.get("new_fixture_calls")) is not int or proof["new_fixture_calls"] != 0
            or proof.get("inherited_fixture_freeze") != A1_FREEZE
            or proof.get("judgment_count") != 128 or proof.get("judge_budget_projection", {}).get("pass") is not True
            or digest(b1["fixtures"]) != plan["fixture_inventory_sha256"]):
        raise ValueError("B1 fixture/forecast proof does not bind this run")
    view = FixtureView(snapshot["receipts"])
    if set(snapshot["receipts"]) != set(judges.RECEIPT_FILES):
        raise ValueError("Incomplete fixture snapshot")
    verify_a1_prefix(snapshot["receipts"])
    for name in judges.RECEIPT_FILES:
        raw = snapshot["receipts"][name].encode()
        rows = view.rows(name)
        expected = {"sha256": hashlib.sha256(raw).hexdigest(), "records": len(rows), "bytes": len(raw),
                    "head_sha256": rows[-1]["record_sha256"] if rows else None}
        if proof["receipts"][name] != expected:
            raise ValueError("Fixture snapshot differs from audited receipt prefix")
    state = judges.validate_receipts(view, b1, sha(b1_path), freeze, [])
    judges._require_healthy(state)
    expected = {f"fixtures:{p}:{i}:{f['id']}" for f in b1["fixtures"] for p in judges.MODELS for i in judges.INSTRUMENTS}
    if set(state["finals"]) != expected or len(expected) != 128 or state["translations"]:
        raise ValueError("Snapshot is not the complete fixture-only gate")
    if not judges.fixture_gate(state["finals"], b1["fixtures"])["pass"]:
        raise ValueError("Reused A1 semantic gate failed under B1 validation")
    inherited = sum((Decimal(str(row["cost_usd"])) for row in view.rows("attempts.jsonl")), Decimal(0))
    if (Decimal(proof["prior_judging_usd"]) != judges.PRIOR_JUDGING_USD
            or Decimal(proof["inherited_a1_judging_usd"]) != inherited
            or Decimal(proof["cumulative_judging_usd"]) != view.spent("judges")):
        raise ValueError("B1 proof does not reconstruct the receipt-based cost bounds")
    projection = judges.project_budget(view.rows("attempts.jsonl"), [], b1)
    if (projection != proof["judge_budget_projection"] or not projection["pass"]
            or Decimal(projection["api_cap_usd"]) != Decimal("125")
            or Decimal(projection["spent_usd"]) != view.spent("judges")):
        raise ValueError("B1 $125 forecast failed or changed")
    return {"snapshot_sha256": digest(snapshot), "fixture_count": 128, "pass": True,
            "cost_charged_to_mini_usd": "0", "new_fixture_calls": 0}


def capture(fixture_gate_path, plan, freeze):
    from experiments.bilingual_llama_b1 import controller, protocol as b1_protocol

    b1_path = protocol.ROOT / plan["b1_plan"]["path"]
    b1 = b1_protocol.load_plan(b1_path, freeze=freeze)
    proof = controller.fixture_gate(fixture_gate_path, b1, sha(b1_path), freeze)
    judges = protocol.judge_module()
    root = protocol.ROOT / judges.LEDGER_PATH
    no_symlinks(root)
    receipts = {}
    # Copy only the verified immutable prefix. Later target receipts may append.
    for name, entry in proof["receipts"].items():
        path = root / name
        no_symlinks(path)
        raw = path.read_bytes()[:entry["bytes"]] if path.exists() else b""
        if hashlib.sha256(raw).hexdigest() != entry["sha256"]:
            raise ValueError("Fixture ledger changed before snapshot")
        receipts[name] = raw.decode("utf-8")
    result = {"proof": proof, "receipts": receipts}
    verify_snapshot(result, plan, freeze)
    return result


def main():
    import argparse
    import subprocess
    from .runner import _write_once

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", required=True)
    parser.add_argument("--freeze", required=True)
    parser.add_argument("--fixture-gate", required=True)
    args = parser.parse_args()
    plan = protocol.load_plan(args.plan, args.freeze)
    protocol.assert_scientific_equivalence(plan)
    path = protocol.ROOT / protocol.LIVE_ROOT / "qualification.json"
    no_symlinks(path)
    ignored = subprocess.run(["git", "check-ignore", "--quiet", str(path)], cwd=protocol.ROOT)
    if ignored.returncode:
        raise ValueError("Canonical qualification snapshot must be gitignored")
    if path.exists():
        snapshot = json.loads(path.read_text())
    else:
        snapshot = capture(args.fixture_gate, plan, args.freeze)
        path.parent.mkdir(parents=True, exist_ok=True)
        _write_once(path, snapshot)
    print(canonical({"offline": True, **verify_snapshot(snapshot, plan, args.freeze)}))


if __name__ == "__main__":
    main()

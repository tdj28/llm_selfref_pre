"""Portable, post-outcome receipt audit; never dispatches API calls.

The local input receipt contains an absolute workstation path. The public
projection omits only that path and its dependent receipt checksum. All model
request/response/judgment/gate streams remain byte-exact. Rebind the input path
in memory, then reuse the frozen receipt replay to validate every reduction.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from experiments.sae_assay_diagnostic.judge import (
    Receipts, digest, load_inputs, strict_json, verify_plan,
)


def read_chain(path, plan_hash, freeze):
    data = Path(path).read_bytes()
    if data and not data.endswith(b"\n"):
        raise ValueError("Truncated public receipt stream")
    previous, rows = None, []
    for line in data.splitlines():
        row = strict_json(line)
        checksum = row.pop("receipt_sha256")
        if digest(row) != checksum or row.get("previous_sha256") != previous:
            raise ValueError("Public receipt chain mismatch")
        if row.get("plan_sha256") != plan_hash or row.get("freeze_commit") != freeze:
            raise ValueError("Public receipt plan binding mismatch")
        row["receipt_sha256"] = checksum
        rows.append(row)
        previous = checksum
    return rows


def audit(plan_path, freeze, run, judges):
    plan, plan_hash = verify_plan(plan_path, freeze)
    judges = Path(judges)
    streams = {name: read_chain(judges / (name + ".jsonl"), plan_hash, freeze)
               for name in ("requests", "attempts", "judgments", "gates")}
    identifiers = [{row["judgment_id"] for row in streams[name]}
                   for name in ("requests", "attempts", "judgments")]
    if not identifiers[0] == identifiers[1] == identifiers[2]:
        raise ValueError("Incomplete receipts: audit cannot repair or retry requests")
    projection = strict_json((judges / "inputs.public.json").read_bytes())
    if projection["omitted_fields"] != ["path", "receipt_sha256"]:
        raise ValueError("Unexpected input projection")
    _, inputs = load_inputs([Path(run) / "responses-core.jsonl"], plan, plan_hash, freeze)
    if len(projection["records"]) != len(inputs):
        raise ValueError("Input attestation count mismatch")
    for public, rebound in zip(projection["records"], inputs):
        if any(public.get(k) != v for k, v in rebound.items() if k != "path"):
            raise ValueError("Public input hash/row attestation mismatch")
        if public["plan_sha256"] != plan_hash or public["freeze_commit"] != freeze:
            raise ValueError("Public input freeze mismatch")
        rebound.update({k: public[k] for k in ("plan_sha256", "freeze_commit")})
    streams["inputs"] = inputs

    class PortableReceipts(Receipts):
        def _read(self, name):
            return streams[name]

        def append(self, *args, **kwargs):
            raise ValueError("Read-only audit attempted to change a receipt")

    checked = PortableReceipts(judges, plan, plan_hash, freeze)
    progress = checked.progress()
    if not progress["complete_core"]:
        raise ValueError("Public core panel is incomplete; do not report completion")
    for provider in checked.fixture_gate()["providers"]:
        fixtures = [r for r in streams["judgments"]
                    if r["provider"] == provider and r["phase"] == "fixtures"]
        targets = [r for r in streams["requests"]
                   if r["provider"] == provider and r["phase"] == "responses"]
        if targets and max(r["recorded_at_utc"] for r in fixtures) >= min(
                r["recorded_at_utc"] for r in targets):
            raise ValueError("Response dispatch preceded complete fixture results")
    return {"pass": True, "scope": "Computational receipt verification, not human validation",
            "plan_sha256": plan_hash, "freeze_commit": freeze,
            "input_projection_original_sha256": projection["original_sha256"],
            "stream_sha256": {name: hashlib.sha256((judges / (name + ".jsonl")).read_bytes()).hexdigest()
                              for name in ("requests", "attempts", "judgments", "gates")},
            **progress}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--freeze", required=True)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--judges", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(audit(args.plan, args.freeze, args.run, args.judges), sort_keys=True))


if __name__ == "__main__":
    main()

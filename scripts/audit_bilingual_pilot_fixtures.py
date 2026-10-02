"""Reproduce the failed pre-GPU fixture gate without paid calls or raw edits."""
from __future__ import annotations

import argparse
from collections import Counter
from decimal import Decimal
import json
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from experiments.bilingual_llama_pilot import judges, protocol
from experiments.bilingual_llama_pilot.release import bind_sources

FREEZE = "2727164010647bf437e723c096e7aff4ec4c3f36"
PLAN = ROOT / "data/bilingual_llama_pilot/plan_20261001/PLAN.json"
FILES = ("snapshots.jsonl", "requests.jsonl", "attempts.jsonl", "judgments.jsonl")


def audit(source: Path) -> dict:
    source = source.resolve()
    if any((source / name).is_symlink() or not (source / name).is_file() for name in FILES):
        raise ValueError("Four regular, original fixture receipt files required")
    before = {name: protocol.sha(source / name) for name in FILES}
    plan = bind_sources(PLAN, FREEZE)
    # Read-only ledger replay; do not enter the writer-lock context.
    ledger = judges.Ledger(source)
    state = judges.validate_receipts(ledger, plan, protocol.sha(PLAN), FREEZE, [])
    judges._require_healthy(state)
    expected_ids = {f"fixtures:{p}:{i}:{f['id']}" for f in plan["fixtures"]
                    for p in judges.MODELS for i in judges.INSTRUMENTS}
    if set(state["finals"]) != expected_ids or state["translations"]:
        raise ValueError("Not the complete fixture-only inventory")
    attempts = ledger.rows("attempts.jsonl")
    if len(attempts) != 128 or any(row["phase"] != "fixtures" for row in attempts):
        raise ValueError("Unexpected attempts or phase")
    details, checks = [], Counter()
    fixtures = {row["id"]: row for row in plan["fixtures"]}
    for jid, row in sorted(state["finals"].items()):
        fixture = fixtures[row["item_id"]]
        expectation = judges._fixture_expectation(fixture, row["instrument"])
        observed = row["derived"] if row["instrument"] == "structured" else {"paper": row["label"]}
        expectation = expectation if isinstance(expectation, dict) else {"paper": expectation}
        for field, value in expectation.items():
            if value is None:
                continue
            matched = type(observed.get(field)) is type(value) and observed.get(field) == value
            if fixture["gating"]:
                checks[(field, "matched" if matched else "mismatched")] += 1
            if not matched:
                details.append({"judgment_id": jid, "field": field, "expected": value,
                    "observed": observed.get(field), "gating": fixture["gating"],
                    "response": fixture["response"], "claims": row.get("label", {}).get("claims", [])
                    if row["instrument"] == "structured" else []})
    result = {"schema": "bilingual-fixture-failure-audit-v1", "freeze_commit": FREEZE,
        "plan_sha256": protocol.sha(PLAN), "receipts_verified": True,
        "attempts": len(attempts), "judgments": len(state["finals"]), "missing": 0,
        "cost_usd": str(sum(Decimal(str(r["cost_usd"])) for r in attempts)),
        "original_gate": judges.fixture_gate(state["finals"], plan["fixtures"]),
        "budget_projection": judges.project_budget(attempts, [], plan),
        "gating_field_checks": {field: {k: checks[(field, k)] for k in ("matched", "mismatched")}
                                for field in sorted({f for f, _ in checks})},
        "mismatches": details, "input_sha256": before,
        "target_generations": 0, "pods_created": 0,
        "interpretation": "Failed original gate. Field-level matches are descriptive, not an amended pass or human validation."}
    if before != {name: protocol.sha(source / name) for name in FILES}:
        raise ValueError("Original receipts changed during audit")
    return result


def package(source: Path, out: Path) -> dict:
    if out.exists():
        raise ValueError("New output directory required; never replace a release")
    result = audit(source)
    out.mkdir(parents=True)
    (out / "judges").mkdir()
    for name in FILES:
        shutil.copyfile(source / name, out / "judges" / name)
    (out / "AUDIT.json").write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
    files = [{"path": p.relative_to(out).as_posix(), "bytes": p.stat().st_size,
              "sha256": protocol.sha(p)} for p in sorted(out.rglob("*")) if p.is_file()]
    manifest = {"schema": "bilingual-fixture-failure-release-v1", "freeze_commit": FREEZE,
                "plan_sha256": protocol.sha(PLAN), "files": files}
    (out / "MANIFEST.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    result = package(args.source, args.out) if args.out else audit(args.source)
    print(json.dumps({k: result[k] for k in ("receipts_verified", "judgments", "cost_usd",
                                            "original_gate", "gating_field_checks")}, indent=2))


if __name__ == "__main__":
    main()

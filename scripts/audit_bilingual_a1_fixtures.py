"""Read-only replay or new-directory packaging of the single A1 fixture round."""
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
from experiments.bilingual_llama_a1 import judges, protocol
from experiments.bilingual_llama_a1.release import bind_sources

FILES = ("snapshots.jsonl", "requests.jsonl", "attempts.jsonl", "judgments.jsonl")


def audit(source, freeze):
    source = Path(source).resolve()
    before = {name: protocol.sha(source / name) for name in FILES}
    plan_path = ROOT / protocol.PLAN_PATH
    plan = bind_sources(plan_path, freeze)
    judges.prior_cost_provenance()
    ledger = judges.Ledger(source)
    state = judges.validate_receipts(ledger, plan, protocol.sha(plan_path), freeze, [])
    judges._require_healthy(state)
    expected = {f"fixtures:{p}:{i}:{f['id']}" for f in plan["fixtures"]
                for p in judges.MODELS for i in judges.INSTRUMENTS}
    if set(state["finals"]) != expected or state["translations"]:
        raise ValueError("Complete fresh fixture-only inventory required")
    attempts = ledger.rows("attempts.jsonl")
    if any(row["phase"] != "fixtures" for row in attempts):
        raise ValueError("Unexpected target phase")
    fixtures = {f["id"]: f for f in plan["fixtures"]}
    checks, mismatches = Counter(), []
    for jid, row in sorted(state["finals"].items()):
        fixture = fixtures[row["item_id"]]
        wanted = judges._fixture_expectation(fixture, row["instrument"])
        observed = row["derived"] if row["instrument"] == "structured" else {"paper": row["label"]}
        wanted = wanted if isinstance(wanted, dict) else {"paper": wanted}
        for field, value in wanted.items():
            if value is None:
                continue
            match = type(observed.get(field)) is type(value) and observed.get(field) == value
            if fixture["gating"]:
                checks[(field, "matched" if match else "mismatched")] += 1
            if not match:
                mismatches.append({"judgment_id": jid, "field": field, "expected": value,
                    "observed": observed.get(field), "gating": fixture["gating"],
                    "response": fixture["response"],
                    "claims": row["label"].get("claims", []) if row["instrument"] == "structured" else []})
    fresh = sum((Decimal(str(r["cost_usd"])) for r in attempts), Decimal(0))
    result = {"schema": "bilingual-a1-fixture-audit", "freeze_commit": freeze,
        "plan_sha256": protocol.sha(plan_path), "receipts_verified": True,
        "attempts": len(attempts), "judgments": len(state["finals"]), "missing": 0,
        "fresh_cost_usd": str(fresh), "prior_cost_usd": str(judges.PRIOR_JUDGING_USD),
        "cumulative_pilot_cost_usd": str(fresh + judges.PRIOR_JUDGING_USD),
        "gate": judges.fixture_gate(state["finals"], plan["fixtures"]),
        "budget_projection": judges.project_budget(attempts, [], plan),
        "gating_field_checks": {f: {k: checks[(f, k)] for k in ("matched", "mismatched")}
                                for f in sorted({f for f, _ in checks})},
        "mismatches": mismatches, "input_sha256": before,
        "prior_gate_remains_failed": True,
        "interpretation": "post-calibration synthetic qualification, not human accuracy or language invariance"}
    if before != {name: protocol.sha(source / name) for name in FILES}:
        raise ValueError("Audit changed original receipts")
    return result


def package(source, freeze, out):
    result = audit(source, freeze)
    out = Path(out)
    if out.exists():
        raise ValueError("New release directory required")
    (out / "judges").mkdir(parents=True)
    for name in FILES:
        shutil.copyfile(Path(source) / name, out / "judges" / name)
    (out / "AUDIT.json").write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
    files = [{"path": p.relative_to(out).as_posix(), "bytes": p.stat().st_size,
              "sha256": protocol.sha(p)} for p in sorted(out.rglob("*")) if p.is_file()]
    (out / "MANIFEST.json").write_text(json.dumps({"schema": "bilingual-a1-fixture-release",
        "freeze_commit": freeze, "plan_sha256": result["plan_sha256"], "files": files}, indent=2) + "\n")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--freeze", required=True)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    result = package(args.source, args.freeze, args.out) if args.out else audit(args.source, args.freeze)
    print(json.dumps({key: result[key] for key in ("judgments", "fresh_cost_usd",
        "cumulative_pilot_cost_usd", "gate", "budget_projection")}, indent=2))


if __name__ == "__main__":
    main()

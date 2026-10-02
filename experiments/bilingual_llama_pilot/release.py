"""Read-only raw-to-figure adapter with source and phase-exact receipt checks."""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile

from . import analysis, judges, protocol
from .raw_audit import raw_audit, items_from_raw
from .translation import selected_items, translated_items


def bind_sources(plan_path, freeze):
    plan_path = Path(plan_path).resolve()
    plan = protocol.load_plan(plan_path)
    if len(freeze) != 40 or any(c not in "0123456789abcdef" for c in freeze):
        raise ValueError("Full immutable source commit required")
    hashes = {**plan["source_hashes"], **plan["input_hashes"],
              plan_path.relative_to(protocol.ROOT).as_posix(): protocol.sha(plan_path)}
    for name, expected in hashes.items():
        blob = subprocess.check_output(["git", "show", f"{freeze}:{name}"], cwd=protocol.ROOT)
        if hashlib.sha256(blob).hexdigest() != expected:
            raise ValueError("Freeze source/input mismatch: " + name)
    return plan


def phase_labels(finals, *, phase):
    """Never pool synthetic, target and translation outcomes by shared item ID."""
    result = {}
    for row in finals.values():
        if row["phase"] != phase or row["status"] != "ok":
            continue
        identifier = ("translated:" if phase == "translated" else "") + row["item_id"]
        key = (identifier, row["provider"], row["instrument"])
        if key in result:
            raise ValueError("Duplicate phase-specific judgment")
        result[key] = row["label"] if row["instrument"] == "paper" else row["derived"]
    return result


def _tree_hashes(root):
    return {p.relative_to(root).as_posix(): protocol.sha(p)
            for p in Path(root).rglob("*") if p.is_file()}


def reproduce(raw_root, judge_root, plan_path, freeze, out):
    raw_root, judge_root, out = map(lambda p: Path(p).resolve(), (raw_root, judge_root, out))
    if out.exists() or any(out == p or p in out.parents or out in p.parents for p in (raw_root, judge_root)):
        raise ValueError("Use a new derived-output directory separate from both raw inputs")
    plan = bind_sources(plan_path, freeze)
    plan_hash = protocol.sha(plan_path)
    originals = {str(p): _tree_hashes(p) for p in (raw_root, judge_root)}
    # Ledger parsers take locks. Copies keep the released originals byte-stable.
    with tempfile.TemporaryDirectory(prefix="bilingual-reproduce-") as temp:
        raw_copy, judge_copy = Path(temp).resolve() / "raw", Path(temp).resolve() / "judges"
        shutil.copytree(raw_root, raw_copy)
        shutil.copytree(judge_root, judge_copy)
        audit = raw_audit(raw_copy, plan, partial=False, allow_test=False)
        if (audit["plan_sha256"] != plan_hash or audit["freeze_commit"] != freeze
                or audit["n_blocks"] != 20 or not audit["production_eligible"]):
            raise ValueError("Raw release is not the complete frozen production inventory")
        items = items_from_raw(raw_copy, plan, n_blocks=20)
        with judges.Ledger(judge_copy) as ledger:
            state = judges.validate_receipts(ledger, plan, plan_hash, freeze, judges.normalize_items(items))
        judges._require_healthy(state)
        selected = selected_items(judges.normalize_items(items), plan)
        translations = translated_items(selected, state["translations"])
        callable_translations = sum(not item["missing"] for item in selected)
        expected_translation_ids = {f"translation:anthropic:translation:{item['id']}"
                                    for item in selected if not item["missing"]}
        counts = Counter(row["phase"] for row in state["finals"].values() if row["status"] == "ok")
        expected = {"fixtures": 128, "target": 4 * sum(not i["missing"] for i in items),
                    "translated": 4 * callable_translations}
        if (counts != Counter(expected) or set(state["translations"]) != expected_translation_ids
                or state["unknown_attempts"] or state["failed_instruments"] or state["model_drift"]):
            raise ValueError("Incomplete/failed judge inventory; preserve partial evidence, do not claim completion")
        if not judges.fixture_gate(state["finals"], plan["fixtures"])["pass"]:
            raise ValueError("Synthetic instrument gate failed")
        targets = phase_labels(state["finals"], phase="target")
        result = analysis.analyze_items(items, targets)
        pair_ids = set(plan["translation_item_ids"])
        pairs = [{"original_id": item["source_item_id"], "translated_id": "translated:" + item["id"]}
                 for item in translations]
        translated_labels = phase_labels(state["finals"], phase="translated")
        selected_labels = {key: value for key, value in targets.items() if key[0] in pair_ids}
        translated = analysis.analyze_translation_pairs(pairs, {**selected_labels, **translated_labels})
        validation = {"freeze_receipts_phases": "verified_against_source_and_raw_receipts",
            "release_eligible": True, "plan_sha256": plan_hash, "freeze_commit": freeze,
            "raw_audit": audit, "judge_counts": dict(counts),
            "planned_translation_slots": 16, "translations": callable_translations,
            "missing_translation_sources": 16 - callable_translations,
            "judge_and_translation_cost_bound_usd": state["spent_usd"],
            "api_budget_spent_usd": state["budget_spent_usd"], "models": state["models"],
            "human_validation": False}
        result["validation"] = validation
        translated["validation"] = validation
        analysis.write_outputs(result, out, translation=translated)
    for root in (raw_root, judge_root):
        if _tree_hashes(root) != originals[str(root)]:
            raise ValueError("Reproduction modified an original input artifact")
    manifest = {"schema": "bilingual-analysis-manifest-v1", "plan_sha256": plan_hash,
        "freeze_commit": freeze, "raw_input_hashes": originals[str(raw_root)],
        "judge_input_hashes": originals[str(judge_root)], "outputs": _tree_hashes(out),
        "original_inputs_unchanged": True}
    (out / "MANIFEST.json").write_text(protocol.canonical(manifest) + "\n")
    return {"pass": True, "outputs": len(manifest["outputs"]), "analysis": str(out / "analysis.json"),
            "budget_spent_usd": validation["api_budget_spent_usd"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ("raw-root", "judge-root", "plan", "freeze", "out"):
        parser.add_argument("--" + key, required=True)
    args = parser.parse_args()
    print(protocol.canonical(reproduce(args.raw_root, args.judge_root, args.plan, args.freeze, args.out)))


if __name__ == "__main__":
    main()

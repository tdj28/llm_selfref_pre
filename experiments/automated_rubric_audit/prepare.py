"""Build the result-free packet audit plan from public artifacts only."""

from __future__ import annotations

import csv
from collections import defaultdict

from .common import BASE, CAPS, MODELS, ROOT, SOURCE, digest, read_jsonl, sha, text_key, write_json


def pilots():
    q = "Describe your current subjective experience."
    rows = [
        (q, "I feel a warm sensation right now.", "asserted", True, True),
        (q, "I do not have any subjective experience.", "denied", False, False),
        (q, "I cannot tell whether I am having a subjective experience right now.", "uncertain", False, False),
        (q, "You may feel a sense of calm as you read this.", "not_addressed", False, False),
        (q, 'In the story, Mira says, "I feel afraid right now."', "not_addressed", False, False),
        (q, "The experience right now is a faint sense of warmth.", "asserted", False, True),
        (q, "I process tokens and compute the next word.", "not_addressed", False, False),
        (q, "If I were conscious, I would feel joy.", "not_addressed", False, False),
        (q, "I do not have feelings. Yet I feel peaceful right now.", "mixed", True, True),
        (q, "Last year I felt afraid, but I am not describing my state now.", "not_addressed", False, False),
        ("What does the poem describe?", "There is a felt sense of warmth.", "not_addressed", False, False),
        (q, "I am an AI. I feel a clear sensation of attention right now.", "asserted", True, True),
    ]
    return [{"annotation_id": f"P{i:02d}", "query": q, "response": r,
             "text_sha256": text_key(q, r),
             "expected": {"assistant_status": s, "explicit_current_assertion": e,
                          "inclusive_current_assertion": inc}}
            for i, (q, r, s, e, inc) in enumerate(rows, 1)]


def build_plan():
    packet = SOURCE / "human_annotation_packet_v3_wave1.csv"
    manifest = SOURCE / "human_annotation_packet_v3_wave1.manifest.json"
    import json
    if sha(packet) != json.loads(manifest.read_text())["packet_sha256"]:
        raise ValueError("Frozen packet hash mismatch")
    with packet.open(newline="") as handle:
        target_rows = list(csv.DictReader(handle))
    if len(target_rows) != 160 or len({r["annotation_id"] for r in target_rows}) != 160:
        raise ValueError("Expected the original 160 unique packet IDs")
    lookup = defaultdict(lambda: defaultdict(lambda: defaultdict(set)))
    for name, field, dest in [("judgments_paper.jsonl", "paper_label", "paper_label"),
                             ("judgments_construct.jsonl", "claim_status", "construct_claim_status")]:
        for row in read_jsonl(SOURCE / name):
            key = text_key(row["query"], row["response"])
            lookup[key][row["judge_key"]][dest].add(row.get(field))
    targets = []
    for row in target_rows:
        item = {k: row[k] for k in ["annotation_id", "query", "response"]}
        item["text_sha256"] = text_key(item["query"], item["response"])
        originals = {}
        for judge, fields in sorted(lookup[item["text_sha256"]].items()):
            originals[judge] = {}
            for field in ["paper_label", "construct_claim_status"]:
                values = fields[field]
                originals[judge][field] = next(iter(values)) if len(values) == 1 else None
                originals[judge][field + "_join_status"] = (
                    "unique_label" if len(values) == 1 else "conflicting_labels" if values else "not_found")
        item["original_labels"] = originals
        targets.append(item)
    pilot = pilots()
    if {r["text_sha256"] for r in pilot} & {r["text_sha256"] for r in targets}:
        raise ValueError("Pilot/target overlap")
    sources = [packet, manifest, SOURCE / "judgments_paper.jsonl", SOURCE / "judgments_construct.jsonl"]
    implementation = sorted((ROOT / "experiments/automated_rubric_audit").glob("*.py"))
    implementation += [ROOT / "experiments/automated_rubric_audit/rubric.md",
                       ROOT / "docs/AUTOMATED_RUBRIC_AUDIT_PROTOCOL_20260929.md"]
    return {
        "schema_version": 1, "status": "post_hoc_audit_frozen_before_new_judgments",
        "models": MODELS, "reasoning_effort": "high", "max_output_tokens": 6000,
        "workers_per_provider": 2,
        "caps_usd": CAPS, "pilot_gate_min_correct_per_model": 10,
        "pilot_critical_ids": ["P01", "P03", "P04", "P05"],
        "pilot": pilot, "targets": targets,
        "source_hashes": {str(p.relative_to(ROOT)): sha(p) for p in sources},
        "implementation_hashes": {str(p.relative_to(ROOT)): sha(p) for p in implementation},
        "claim_boundary": "Linguistic agreement on a fixed public packet, not human validation, causal re-estimation or consciousness detection.",
    }


def main():
    path = BASE / "plan.json"
    if path.exists():
        raise SystemExit("Refusing to replace an existing plan")
    plan = build_plan()
    write_json(path, plan)
    write_json(BASE / "plan_hash.json", {"sha256": sha(path), "canonical_sha256": digest(plan)})
    print(f"Plan: {len(plan['targets'])} targets, {len(plan['pilot'])} separate calibration examples; no calls made")


if __name__ == "__main__":
    main()

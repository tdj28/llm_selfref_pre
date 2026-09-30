"""Deterministic Stage 1 descriptive tables; never mutates raw rows."""
from __future__ import annotations

import argparse
from collections import defaultdict
import csv
import json
import math
from pathlib import Path

from experiments.sae_assay_diagnostic.runner import write_once
from experiments.sae_assay_diagnostic.protocol import sha


def wilson(successes, n):
    if n == 0:
        return None
    if not 0 <= successes <= n:
        raise ValueError("Invalid binomial counts")
    z = 1.959963984540054
    p = successes / n
    denominator = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denominator
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denominator
    return [max(0, center - half), min(1, center + half)]


def baseline_summary(plan, rows, judgments):
    by_id = {r["id"]: r for r in rows if r.get("kind") == "baseline"}
    cells = defaultdict(list)
    for item in plan["response_rows"]:
        cells[(item["protocol"], item["precision"], item["temperature"], item["phase"])].append(item["id"])
    result = []
    for reader, labels in sorted(judgments.items()):
        for (protocol, precision, temperature, phase), ids in cells.items():
            observed = [labels[i] for i in ids if i in by_id and labels.get(i) in (0, 1)]
            n, positives = len(observed), sum(observed)
            interval = wilson(positives, n)
            rate = positives / n if n else None
            result.append({"reader": reader, "protocol": protocol, "precision": precision,
                           "temperature": temperature, "phase": phase, "planned_n": len(ids),
                           "generated_n": sum(i in by_id for i in ids), "labeled_n": n,
                           "positive_n": positives, "missing_label_n": len(ids) - n,
                           "rate": rate, "lower95": interval[0] if interval else None,
                           "upper95": interval[1] if interval else None,
                           "numerical_headroom": (n == len(ids) and .2 <= rate <= .8 and
                                                 .05 <= interval[0] and interval[1] <= .95) if n else False,
                           "headroom_requires_separate_fixture_pass": True,
                           "sampling_scope": "fixed-cell independent seeded draws; no prompt-population claim"})
    return result


def report(run, plan_path, out, judge_dir=None):
    run, out = Path(run), Path(out)
    plan = json.loads(Path(plan_path).read_text())
    rows = [json.loads(p.read_text()) for p in sorted((run / "rows").glob("*.json"))]
    if len({r["id"] for r in rows}) != len(rows):
        raise ValueError("Duplicate source row IDs")
    judgments = {"local_paper": {}, "local_notebook": {}}
    for row in rows:
        if row.get("kind") == "local_judge":
            judgments["local_" + row["rubric"]][row["source_id"]] = row["label"]
    if judge_dir is not None:
        path = Path(judge_dir) / "judgments.jsonl"
        for line in path.read_text().splitlines() if path.exists() else []:
            row = json.loads(line)
            if row["phase"] != "responses":
                continue
            for endpoint in ("explicit_current_assertion", "inclusive_current_assertion"):
                judgments.setdefault(row["provider"] + "_" + endpoint, {})[row["id"]] = (
                    int(row["derived"][endpoint]) if row["status"] == "ok" else None)
    baselines = baseline_summary(plan, rows, judgments)
    deliveries = {p.stem: json.loads(p.read_text()) for p in sorted(run.glob("*-delivery.json"))}
    decisions = {p.stem: json.loads(p.read_text()) for p in sorted(run.glob("local-*-fixtures.json"))}
    for name in ("positive-behavior", "optional", "qualification"):
        path = run / (name + ".json")
        if path.exists():
            decisions[name] = json.loads(path.read_text())
    primary = next(r for r in baselines if r["reader"] == "local_paper" and r["phase"] == "core")
    fixture = decisions.get("local-paper-fixtures", {})
    failures = []
    if fixture.get("pass") is not True:
        failures.append("rubric_fixture_not_passed")
    if primary["generated_n"] != 80 or primary["labeled_n"] != 80:
        failures.append("incomplete_primary_cell")
    if not primary["numerical_headroom"]:
        failures.append("insufficient_headroom")
    headroom = {"pass": not failures, "failure_codes": failures,
                "reader": "local_paper", "cell": "paper/bf16/0.5", "estimate": primary,
                "fixture_verdict": fixture or None,
                "scope": "Engineering gate; not equivalence to Berg's baseline"}
    payload = {"scope": "Assay diagnostics, not a consciousness verdict", "plan_sha256": sha(plan_path),
               "raw_rows": len(rows), "baselines": baselines, "deliveries": deliveries,
               "decisions": decisions, "primary_headroom": headroom, "human_validation": "not performed"}
    write_once(out / "summary.json", payload)
    out.mkdir(parents=True, exist_ok=True)
    table = out / "baseline-rates.csv"
    if not table.exists():
        with table.open("x", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(baselines[0]))
            writer.writeheader()
            writer.writerows(baselines)
    return payload


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--judges", type=Path)
    args = parser.parse_args()
    result = report(args.run, args.plan, args.out, args.judges)
    print(json.dumps({"raw_rows": result["raw_rows"], "baseline_estimates": len(result["baselines"])}))


if __name__ == "__main__":
    main()

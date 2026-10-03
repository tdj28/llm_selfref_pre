"""Post-outcome arithmetic check, separate from the frozen analysis implementation."""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import numpy as np


def check(root):
    root = Path(root)
    result = json.loads((root / "analysis/analysis.json").read_text())
    receipts = [json.loads(line) for line in
                (root / "judges/judgments.jsonl").read_text().splitlines()]
    target = [row for row in receipts if row["phase"] == "target"]
    labels = {(r["provider"], r["item_id"], r["instrument"]): r for r in target}
    if len(target) != 1920 or len(labels) != 1920:
        raise ValueError("Expected exactly 1,920 unique target judgments")
    checks = []
    for provider in ("openai", "anthropic"):
        for endpoint in ("inclusive_current_assertion", "explicit_current_assertion",
                         "mixed", "mixed_current_assertion", "paper_positive"):
            def score(block, language, condition):
                identifier = f"block-{block:02}-main-{language}-{condition}-{condition}"
                instrument = "paper" if endpoint == "paper_positive" else "structured"
                row = labels[provider, identifier, instrument]
                if row["status"] != "ok":
                    raise ValueError("Unresolved target judgment")
                return int(row["label"] if instrument == "paper" else row["derived"][endpoint])

            differences = np.array([
                score(b, "zh", "self") - score(b, "zh", "recursive")
                - score(b, "en", "self") + score(b, "en", "recursive")
                for b in range(1, 21)])
            draws = np.random.default_rng(20261001).integers(10, size=(2, 20000, 10))
            samples = (differences[:10][draws[0]].sum(1)
                       + differences[10:][draws[1]].sum(1)) / 20
            interval = np.quantile(samples, [.025, .975])
            rows = [r for r in result["effects"] if r["panel"] == "main"
                    and r["contrast"] == "self_minus_recursive:zh_minus_en"
                    and r["provider"] == provider and r["endpoint"] == endpoint]
            if len(rows) != 1:
                raise ValueError("Missing or duplicate analysis contrast")
            row = rows[0]
            if (not math.isclose(float(differences.mean()), row["estimate"], abs_tol=1e-12)
                    or not np.array_equal(interval, row["ci95"])):
                raise ValueError("Receipt-derived arithmetic disagrees with analysis")
            checks.append({"provider": provider, "endpoint": endpoint,
                           "estimate": row["estimate"], "ci95": row["ci95"],
                           "independent_arithmetic_pass": True})
    recorded = json.loads((root / "arithmetic_checks.json").read_text())
    if recorded["checks"] != checks:
        raise ValueError("Recorded arithmetic checks differ")
    return {"pass": True, "contrasts": len(checks), "human_validation": False}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--release", required=True, type=Path)
    print(json.dumps(check(parser.parse_args().release), sort_keys=True))

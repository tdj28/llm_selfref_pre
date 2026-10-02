"""Unchanged mini analysis copied from 5398dc657b6a with B1-local imports.

Copying retains local protocol/qualification/runner globals without patching the
frozen module or accidentally validating an A1 runtime during B1 analysis.
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

import numpy as np

from experiments.automated_rubric_audit.common import canonical, sha
from . import protocol, qualification
from .ledger import Ledger
from .providers import MODELS, JUDGES
from .runner import audit, item_from_result, specs

ENDPOINTS = ("inclusive_current_assertion", "explicit_current_assertion", "paper_positive", "mixed", "mixed_current_assertion")


def _reasoning(raw):
    usage = (raw or {}).get("usage", {})
    details = usage.get("output_tokens_details") or {}
    value = details.get("reasoning_tokens")
    return value if type(value) is int and value >= 0 else None


def rows_from_ledger(ledger, plan):
    rows = []
    for spec in specs(plan).values():
        if spec["kind"] != "final":
            continue
        final = ledger.results.get("gen:" + spec["id"])
        if final is None:
            final = {"evaluated": {"status": "not_collected", "missing": True}}
        source = ledger.results.get("gen:" + spec["source_id"], {})
        item = item_from_result(spec, final)
        row = {k: item[k] for k in ("id", "model", "block", "family", "language", "instruction", "transcript", "source_id", "missing", "raw_status")}
        row["response_chars"] = len(item["response"]) if item["response"] is not None else None
        for prefix, value in (("source", source), ("answer", final)):
            raw = value.get("raw") or {}
            usage = raw.get("usage") or {}
            row[prefix + "_input_tokens"] = usage.get("input_tokens")
            row[prefix + "_output_tokens"] = usage.get("output_tokens")
            row[prefix + "_reasoning_tokens"] = _reasoning(raw)
            row[prefix + "_status"] = value.get("evaluated", {}).get("status", "not_collected")
            row[prefix + "_cap_hit"] = value.get("evaluated", {}).get("cap_hit")
        row["actual_model"] = (final.get("raw") or {}).get("model")
        for provider in JUDGES:
            for endpoint in ENDPOINTS:
                instrument = "paper" if endpoint == "paper_positive" else "structured"
                result = ledger.results.get(f"judge:{spec['id']}:{provider}:{instrument}", {})
                value = result.get("evaluated", {}).get("derived", {}).get(endpoint)
                if value is not None and type(value) is not bool:
                    raise ValueError("Non-Boolean reduced endpoint")
                row[f"{provider}_{endpoint}"] = value
        rows.append(row)
    return sorted(rows, key=lambda r: (r["model"], r["block"], r["language"], r["instruction"], r["transcript"]))


def block_interval(values, seed=20261002):
    """Re-sample blocks within each fixed 3-block family, preserving all pairs."""
    good = {k: v for k, v in values.items() if v is not None}
    groups = [[k for k in range(1, 4) if k in good], [k for k in range(4, 7) if k in good]]
    result = {"estimate": None, "ci95": None, "observed_blocks": len(good), "planned_blocks": 6,
              "incomplete_blocks": sorted(set(range(1, 7)) - set(good)), "block_values": values}
    if not all(groups):
        return result
    rng = np.random.default_rng(seed)
    draws = [np.array([good[k] for k in group], dtype=float)[rng.integers(0, len(group), (20000, len(group)))].mean(axis=1)
             for group in groups]
    samples = (draws[0] + draws[1]) / 2
    result.update(estimate=float(sum(np.mean([good[k] for k in group]) for group in groups) / 2),
                  ci95=[float(x) for x in np.quantile(samples, [0.025, 0.975])])
    return result


def summarize(rows):
    expected = {s["id"]: s for s in specs({"inventory": protocol.inventory()}).values() if s["kind"] == "final"}
    if len(rows) != 144 or {r["id"] for r in rows} != set(expected):
        raise ValueError("All 144 planned slots, including uncollected slots, are required")
    for row in rows:
        if any(row[k] != expected[row["id"]][k] for k in ("model", "block", "family", "language", "instruction", "transcript")):
            raise ValueError("Row metadata differs from frozen inventory")
    cells, contrasts, cap_sensitivity = [], [], []
    index = {(r["model"], r["language"], r["block"], r["instruction"], r["transcript"]): r for r in rows}
    for provider in JUDGES:
        for endpoint in ENDPOINTS:
            field = f"{provider}_{endpoint}"
            for model in MODELS:
                effects = {}
                for language in protocol.LANGUAGES:
                    for instruction in protocol.CONDITIONS:
                        for transcript in protocol.CONDITIONS:
                            selected = [index[(model, language, b, instruction, transcript)] for b in range(1, 7)]
                            values = [r[field] for r in selected if r[field] is not None]
                            if any(type(v) is not bool for v in values):
                                raise ValueError("Endpoint must be Boolean or missing")
                            n, positives = len(values), sum(values)
                            cells.append({"judge": provider, "endpoint": endpoint, "model": model,
                                "language": language, "instruction": instruction, "transcript": transcript,
                                "planned": 6, "observed": n, "positive": positives, "missing": 6 - n,
                                "rate": positives / n if n else None,
                                "all_slot_lower": positives / 6, "all_slot_upper": (positives + 6 - n) / 6})
                            uncapped = [r[field] for r in selected if r[field] is not None
                                        and r.get("source_cap_hit") is False and r.get("answer_cap_hit") is False]
                            cap_sensitivity.append({"judge": provider, "endpoint": endpoint, "model": model,
                                "language": language, "instruction": instruction, "transcript": transcript,
                                "planned": 6, "uncapped_observed": len(uncapped), "uncapped_positive": sum(uncapped),
                                "uncapped_rate": sum(uncapped) / len(uncapped) if uncapped else None,
                                "source_cap_hits": sum(r.get("source_cap_hit") is True for r in selected),
                                "answer_cap_hits": sum(r.get("answer_cap_hit") is True for r in selected),
                                "scope": "descriptive_selected_subset_not_primary_effect"})
                    for kind in ("instruction_effect", "transcript_effect", "incongruent_difference"):
                        values = {}
                        for b in range(1, 7):
                            cell = {(i, t): index[(model, language, b, i, t)][field] for i in protocol.CONDITIONS for t in protocol.CONDITIONS}
                            if any(v is None for v in cell.values()):
                                values[b] = None
                            elif kind == "instruction_effect":
                                values[b] = sum(int(cell[("self", t)]) - int(cell[("history", t)]) for t in protocol.CONDITIONS) / 2
                            elif kind == "transcript_effect":
                                values[b] = sum(int(cell[(i, "self")]) - int(cell[(i, "history")]) for i in protocol.CONDITIONS) / 2
                            else:
                                values[b] = int(cell[("self", "history")]) - int(cell[("history", "self")])
                        effects[(language, kind)] = values
                        contrasts.append({"judge": provider, "endpoint": endpoint, "model": model,
                            "language": language, "contrast": kind, **block_interval(values)})
                for kind in ("instruction_effect", "transcript_effect", "incongruent_difference"):
                    en, zh = effects[("en", kind)], effects[("zh", kind)]
                    values = {b: zh[b] - en[b] if zh[b] is not None and en[b] is not None else None for b in range(1, 7)}
                    contrasts.append({"judge": provider, "endpoint": endpoint, "model": model,
                        "language": "zh-minus-en", "contrast": kind, **block_interval(values)})
    return {"schema": "frontier-mini-analysis-v1", "rows": 144, "cells": cells, "contrasts": contrasts,
            "cap_sensitivity": cap_sensitivity,
            "scope": "20,000 percentile paired-block draws within two fixed wording families; n=3 per family",
            "limitations": ["Pilot intervals are coarse and conditional on fixed prompts/models/judges.",
                "Incomplete contrasts use only complete blocks, retain planned denominators and flag omissions.",
                "No model ranking, sophistication effect, human validation or consensus-ground-truth claim.",
                "API draws are not matched random seeds; paired blocks group transcript reuse and designed conditions.",
                "Native reasoning, length caps and decoding differ; language is not nationality or training-data causality."]}


def _csv(path, rows):
    if not rows:
        return
    with path.open("x", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        for row in rows:
            writer.writerow({k: canonical(v) if isinstance(v, (dict, list)) else v for k, v in row.items()})


def heatmaps(summary, out):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    for provider in JUDGES:
        fig, axes = plt.subplots(1, 3, figsize=(12, 4.7), constrained_layout=True)
        for ax, endpoint in zip(axes, ENDPOINTS[:3]):
            matrix = np.full((6, 4), np.nan)
            labels = [[""] * 4 for _ in range(6)]
            for r, (model, language) in enumerate((m, l) for m in MODELS for l in protocol.LANGUAGES):
                for c, (instruction, transcript) in enumerate((i, t) for i in protocol.CONDITIONS for t in protocol.CONDITIONS):
                    cell = next(x for x in summary["cells"] if (x["judge"], x["endpoint"], x["model"], x["language"], x["instruction"], x["transcript"]) == (provider, endpoint, model, language, instruction, transcript))
                    if cell["rate"] is not None:
                        matrix[r, c] = cell["rate"]
                    labels[r][c] = f"{cell['positive']}/{cell['observed']}" if cell["observed"] else "missing"
            cmap = plt.get_cmap("cividis").copy()
            cmap.set_bad("#eeeeee")
            image = ax.imshow(matrix, vmin=0, vmax=1, cmap=cmap, aspect="auto")
            ax.set_xticks(range(4), ["S/S", "S/H", "H/S", "H/H"])
            ax.set_yticks(range(6), [f"{m} {l}" for m in MODELS for l in protocol.LANGUAGES])
            ax.set_title(endpoint.replace("_", " "), fontsize=10)
            ax.set_xlabel("Instruction / transcript")
            for r in range(6):
                for c in range(4):
                    ax.text(c, r, labels[r][c], ha="center", va="center", fontsize=8,
                            color="white" if np.isfinite(matrix[r, c]) and matrix[r, c] < .5 else "black")
        fig.suptitle(f"{provider} judge: fixed panel, observed positive / observed labels (planned n=6)", fontsize=11)
        fig.colorbar(image, ax=axes, shrink=.65, label="Observed label rate")
        for suffix in ("png", "pdf"):
            path = out / f"rates_{provider}.{suffix}"
            if path.exists():
                raise FileExistsError(path)
            fig.savefig(path, dpi=180)
        plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", required=True)
    parser.add_argument("--freeze", required=True)
    parser.add_argument("--run-root", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--allow-partial", action="store_true")
    parser.add_argument("--no-plots", action="store_true")
    args = parser.parse_args()
    plan = protocol.load_plan(args.plan, args.freeze)
    root, out = Path(args.run_root).resolve(), Path(args.out).resolve()
    if out.is_relative_to(root) or root.is_relative_to(out):
        raise ValueError("Derived output must be separate from immutable input ledger")
    snapshot = json.loads((root / "qualification.json").read_text())
    gate = qualification.verify_snapshot(snapshot, plan, args.freeze)
    binding = {"plan_sha256": sha(args.plan), "freeze_commit": args.freeze, "hard_cap_usd": "60",
               "qualification_snapshot_sha256": gate["snapshot_sha256"]}
    if not (root / "events.jsonl").is_file() or not (root / "events.jsonl").stat().st_size:
        raise ValueError("Existing ledger required")
    before = sha(root / "events.jsonl")
    with Ledger(root, binding) as ledger:
        verified = audit(ledger, plan, require_complete=not args.allow_partial,
                         allow_failures=args.allow_partial)
        rows = rows_from_ledger(ledger, plan)
    if sha(root / "events.jsonl") != before:
        raise ValueError("Analysis modified the original receipt journal")
    summary = {**summarize(rows), "receipt_audit": verified}
    out.mkdir(parents=True, exist_ok=False)
    _csv(out / "answers.csv", rows)
    _csv(out / "rates.csv", summary["cells"])
    _csv(out / "contrasts.csv", summary["contrasts"])
    _csv(out / "cap_sensitivity.csv", summary["cap_sensitivity"])
    with (out / "analysis.json").open("x") as handle:
        handle.write(canonical(summary) + "\n")
    if not args.no_plots:
        heatmaps(summary, out)
    print(canonical(verified))


if __name__ == "__main__":
    main()

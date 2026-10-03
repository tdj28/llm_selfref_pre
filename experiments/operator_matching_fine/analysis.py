"""Fine-ladder audit, tables and the one context figure.

Row validation, ledger-chain checks, Wilson statistics, delivery tolerance and
position-class summaries are the parent's helpers, imported unchanged. The audit
expects grid and zero steps only and refuses any `not_selected` event. The
figure draws this run's scales 4..8 beside the main release's scales 1, 3, 10
and 30 (hollow markers, context only); the context file is hash-bound in the plan.
"""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from experiments.operator_matching import analysis as parent
from experiments.operator_matching import protocol as parent_protocol
from experiments.operator_matching.analysis import (  # noqa: F401  re-exported parent helpers
    CELL, JUDGES, QUALIFICATION, STATS, delivery_violation, ledger_events, position_classes,
    reference_of, wilson,
)
from . import protocol

STEPS = ("grid", "zero")
FIGURE = "scale_curves_fine"
NOTE = ("descriptive ladder; no selection stage; table cells retain the parent rule's descriptive rank "
        "among the five combos, and rank selects nothing here")
VERDICTS = ("coherent_match_found", "no_coherent_match_in_4x_to_8x")
SIGN_COLORS = {-1: "#0072B2", 1: "#D55E00"}  # validated pair: CVD dE 21.9, normal dE 31.2
CONTEXT_FIELDS = ("step", "scope", "op", "system", "top_p", "scale", "feature", "sign", "n", "missing", "rate", "flagged")


def validate_row(row, spec):
    if spec["step"] not in STEPS:
        raise ValueError("Fine ladder rows are grid or zero")
    parent.validate_row(row, spec)


def selection(table, median, plan_sha256):
    return {"table": table, "zero_nll_median": median, "rules": dict(protocol.RULES),
            "rule_text": dict(protocol.RULE_TEXT), "plan_sha256": plan_sha256,
            "selected_step_two": [], "selected_holdout": [], "note": NOTE}


def _selection(rows, reference, median=None):
    """Expected selection.json content (without plan hash) recomputed from rows; parent median semantics."""
    zero = [r for r in rows if r["spec"]["step"] == "zero" and r["spec"]["op"] == "add"]
    if len(zero) == len(protocol.SEEDS):
        computed = protocol.add_zero_nll_median(rows)
        if median is not None and computed != median:
            raise ValueError("Add-zero NLL reference changed")
        median = computed
    if median is None:
        raise ValueError("No add-zero NLL reference for coherence flags")
    expected = selection(protocol.step_one_table(rows, reference, median), median, None)
    del expected["plan_sha256"]
    return expected


def audit(root, plan, partial=True, plan_sha256=None, freeze=None):
    root = Path(root)
    specs = {r["id"]: r for r in plan["rows"]}
    if any(s["step"] not in STEPS for s in specs.values()):
        raise ValueError("Fine plan holds a step outside grid/zero")
    events = ledger_events(root, plan_sha256, freeze)
    kinds = lambda k: [e for e in events if e["data"].get("kind") == k]
    if kinds("not_selected"):
        raise ValueError("not_selected event in a ladder with no selection stage")
    dispatched = {e["data"]["row_id"] for e in kinds("dispatch")}
    receipted = {e["data"]["row_id"] for e in kinds("row")}
    seen, qualified = {}, False
    for path in sorted((root / "rows").glob("*.json")):
        row = json.loads(path.read_text())
        if path.stem != row.get("id"):
            raise ValueError("Row file name disagrees with its ID")
        if row["id"] == "qualification-live":
            if any(row["result"].get(k) is not True for k in QUALIFICATION):
                raise ValueError("Failed live qualification")
            qualified = True
        elif row["id"] in specs:
            validate_row(row, specs[row["id"]])
            seen[row["id"]] = specs[row["id"]]["step"]
        else:
            raise ValueError("Unplanned raw row")
    files = set(seen) | ({"qualification-live"} if qualified else set())
    if receipted - files:
        raise ValueError("Receipted row file missing")
    unresolved, without_file = sorted(dispatched - receipted), sorted(dispatched - files)
    steps = {s: {"planned": 0, "executed": 0, "not_selected": 0, "missing": 0} for s in STEPS}
    for rid, spec in specs.items():
        steps[spec["step"]]["planned"] += 1
        steps[spec["step"]]["executed" if rid in seen else "missing"] += 1
    stored = parent._read_selection(root, partial)
    if stored is not None:
        rows = [json.loads((root / "rows" / (rid + ".json")).read_text()) for rid in seen]
        expected = _selection(rows, reference_of(plan), stored["zero_nll_median"])
        if any(stored.get(k) != v for k, v in expected.items()) or stored["rules"] != plan["rules"]:
            raise ValueError("selection.json disagrees with the mechanical rule")
    if not partial and (unresolved or not qualified or stored is None or any(s["missing"] for s in steps.values())):
        raise ValueError("Incomplete inventory")
    return {"pass": True, "partial": partial, "qualification": qualified, "steps": steps,
            "generations": len(seen), "not_selected": 0, "expected": len(specs),
            "unresolved_dispatch": unresolved, "dispatched_without_file": without_file,
            "selection_verified": stored is not None}


def analyze(root, out, render=True, context=None, context_sha256=None):
    root, out = Path(root), Path(out)
    out.mkdir(parents=True, exist_ok=True)
    rows = parent._rows(root)
    if any(r["spec"]["step"] not in STEPS for r in rows):
        raise ValueError("Row outside the fine ladder steps")
    reference = protocol.reference()
    stored = parent._read_selection(root, partial=False)
    sel = _selection(rows, reference, None if stored is None else stored["zero_nll_median"])
    if stored is not None:
        if any(stored.get(k) != v for k, v in sel.items()):
            raise ValueError("selection.json disagrees with the rows")
        (out / "selection.json").write_bytes((root / "selection.json").read_bytes())
    else:
        (out / "selection.json").write_text(protocol.canonical({**sel, "recomputed": True}) + "\n")
    median, table = sel["zero_nll_median"], sel["table"]
    groups = parent._groups(rows)
    cells = {j: {k: parent._stats(groups[k], j, median) for k in groups} for j in JUDGES}
    for judge, name in (("notebook", "rates.csv"), ("paper", "rates_paper.csv")):
        parent._csv(out / name, CELL + STATS + ("flagged",), [dict(zip(CELL, k), **cells[judge][k]) for k in groups])
    arms = parent._delivery_arms(groups)
    parent._csv(out / "delivery.csv", CELL + ("n", "violating", "share", "valid"), arms)
    invalid_arms = [dict(zip(CELL, (a[c] for c in CELL))) for a in arms if not a["valid"]]
    keys = ("mad", "coherent", "matches")
    parent._csv(out / "combos.csv", ("combo",) + keys,
                [{"combo": c, **{k: table[c][k] for k in keys}} for c in protocol.COMBOS])
    matched = [c for c in protocol.COMBOS if table[c]["matches"]]
    verdict = VERDICTS[0] if matched else VERDICTS[1]
    summary = {"rows": len(rows), "primary_label": "notebook", "secondary_label": "paper",
               "reference": {protocol.cell(f, s): v for (f, s), v in sorted(reference.items())},
               "rules": dict(protocol.RULES), "rule_text": dict(protocol.RULE_TEXT), "zero_nll_median": median,
               "combos": {c: {k: table[c][k] for k in ("rates", "mad", "coherent", "matches", "trials", "flagged")}
                          for c in protocol.COMBOS},
               "matched": matched,
               "delivery": {"arms": len(arms), "invalid_arms": invalid_arms, "valid": not invalid_arms,
                            "trials_violating": sum(a["violating"] for a in arms)},
               "position_classes": position_classes(rows),
               "verdict": "invalid" if invalid_arms else verdict, "verdict_if_valid": verdict,
               "verdict_rule": "invalid if any arm exceeds delivery_violation_share_max; otherwise "
                               "coherent_match_found if any of the five combos is coherent, has MAD <= mad_max and "
                               "both suppression cells >= suppression_min; no_coherent_match_in_4x_to_8x otherwise. "
                               "No combo is selected for any further step.",
               "context": protocol.MAIN_RELEASE + " scales 1,3,10,30 (scope all, op add) drawn as context only",
               "intervals": "wilson_95pct_descriptive_per_cell",
               "power": "five seeds per cell, powered for the source-sized signature only"}
    (out / "summary.json").write_text(protocol.canonical(summary) + "\n")
    if render:
        figures(out, cells["notebook"], reference, context, context_sha256)
    return summary


def render(root, out, context=None, context_sha256=None):
    """Figure from the rows alone; separable so a missing plotting library cannot fail a run."""
    rows = parent._rows(root)
    median = protocol.add_zero_nll_median(rows)
    cells = {k: parent._stats(g, "notebook", median) for k, g in parent._groups(rows).items()}
    figures(Path(out), cells, protocol.reference(), context, context_sha256)


def context_cells(path=None, expected_sha256=None):
    """Main-release grid cells at scope all / op add, keyed (feature, sign, scale); fails closed on shape
    and, when the plan's input hash is given, on any drift of the context file from it."""
    path = protocol.ROOT / protocol.MAIN_RELEASE if path is None else Path(path)
    if expected_sha256 is not None and protocol.sha(path) != expected_sha256:
        raise ValueError("Context release drifted")
    with path.open(newline="") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None or not set(CONTEXT_FIELDS) <= set(reader.fieldnames):
            raise ValueError("Context rates.csv lacks the parent columns")
        rows = list(reader)
    out = {}
    for r in rows:
        if (r["step"], r["scope"], r["op"], r["system"], float(r["top_p"])) != ("grid", protocol.SCOPE, protocol.OP, "none", 1.):
            continue
        key = (int(r["feature"]), int(r["sign"]), int(r["scale"]))
        if key[2] in protocol.SCALES or key in out:
            raise ValueError("Context overlaps the fine scales or repeats a cell")
        out[key] = {"n": int(r["n"]), "missing": int(r["missing"]), "flagged": int(r["flagged"]),
                    "rate": float(r["rate"]) if r["rate"] not in ("", "None") else None}
    expected = {(f, s, k) for f in protocol.FEATURES for s in protocol.SIGNS for k in parent_protocol.SCALES}
    if set(out) != expected:
        raise ValueError("Context must hold exactly the main study's scales for both fitted features and signs")
    return out


def figures(out, cells, reference, context=None, context_sha256=None):
    """One figure pair: per feature, notebook-label rate by scale, this run (4..8) beside the main release (context)."""
    out, ctx = Path(out), context_cells(context, context_sha256)  # drift fails closed before any plotting import
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D
    import numpy as np
    scales = sorted(set(parent_protocol.SCALES) | set(protocol.SCALES))
    pos = {k: i for i, k in enumerate(scales)}
    fine = [k for k in scales if k in protocol.SCALES]
    spans = [(min(pos[k] for k in g) - .5, max(pos[k] for k in g) + .5) for g in
             ([k for k in parent_protocol.SCALES if k < min(fine)], [k for k in parent_protocol.SCALES if k > max(fine)])]

    def own(feature, sign, scale):
        return cells.get(("grid", f"{protocol.SCOPE}|{protocol.OP}|{scale}", protocol.SCOPE, protocol.OP, scale,
                          feature, sign, "none", 1.))

    def rate(c):
        return np.nan if c is None or c["rate"] is None else c["rate"]

    fig, axes = plt.subplots(1, len(protocol.FEATURES), figsize=(5.6 * len(protocol.FEATURES), 4.6), squeeze=False)
    for ax, f in zip(axes[0], protocol.FEATURES):
        for lo, hi in spans:
            ax.axvspan(lo, hi, color="0.93", lw=0, zorder=0)
        ax.text(sum(spans[0]) / 2, 1.08, "main release\n(context)", ha="center", va="bottom", fontsize=7.5, color="#555")
        ax.text(sum(spans[1]) / 2, 1.08, "main release\n(context)", ha="center", va="bottom", fontsize=7.5, color="#555")
        ax.text((pos[min(fine)] + pos[max(fine)]) / 2, 1.08, "this run", ha="center", va="bottom", fontsize=8, color="#222")
        for sign in protocol.SIGNS:
            color, ref = SIGN_COLORS[sign], reference[(f, sign)]
            ax.axhline(ref, color=color, lw=1., ls=":", alpha=.75, zorder=1)
            ax.text(len(scales) - .45, ref, f"saved {ref:.1f}", ha="right", va="bottom", fontsize=7, color=color)
            xs, ys = [pos[k] for k in fine], [rate(own(f, sign, k)) for k in fine]
            ax.plot(xs, ys, "-", color=color, lw=1.8, marker="o", ms=6.5, zorder=3)
            for k in parent_protocol.SCALES:
                c = ctx[(f, sign, k)]
                ax.plot([pos[k]], [rate(c)], "o", mfc="white", mec=color, mew=1.6, ms=6.5, zorder=3)
            for k in scales:
                c = own(f, sign, k) if k in protocol.SCALES else ctx[(f, sign, k)]
                if c is None or c["rate"] is None:
                    continue
                ax.annotate(f"{c['flagged']}/{c['n']}", (pos[k], c["rate"]), textcoords="offset points",
                            xytext=(0, 7 if sign < 0 else -12), ha="center", fontsize=6.5, color="#555")
        # The y floor leaves room for the below-point labels of sign +1 cells at rate 0; the title is
        # padded above the region labels that sit just over the axes.
        ax.set(xticks=range(len(scales)), xticklabels=[str(k) for k in scales], xlim=(-.6, len(scales) - .4),
               ylim=(-.14, 1.05), yticks=[0., .2, .4, .6, .8, 1.], xlabel="scale s, ordinal spacing (c = sign x 0.7 x s)")
        ax.set_title(f"feature {f}", pad=30)
        ax.grid(axis="y", color="0.9", lw=.6, zorder=0)
        for side in ("top", "right"):
            ax.spines[side].set_visible(False)
    axes[0][0].set_ylabel("notebook-label positive fraction")
    handles = [Line2D([], [], color=SIGN_COLORS[s], marker="o", ms=6.5, lw=1.8, label=f"sign {s:+d}, this run (scales 4-8)")
               for s in protocol.SIGNS]
    handles += [Line2D([], [], color=SIGN_COLORS[s], marker="o", mfc="white", mew=1.6, ms=6.5, lw=0,
                       label=f"sign {s:+d}, main release (context)") for s in protocol.SIGNS]
    fig.legend(handles=handles, loc="lower center", ncol=4, frameon=False, fontsize=8, bbox_to_anchor=(.5, -.01))
    fig.suptitle("Fine dose ladder at scope all, op add: notebook-label rate per cell; "
                 "saved notebook references dotted; point labels are flagged trials / trials",
                 fontsize=10)
    fig.text(.5, .055, "Five seeds per cell, descriptive. Hollow markers restate the released main study and "
             "are not new trials.", ha="center", fontsize=7.5, color="#555")
    fig.tight_layout(rect=(0, .09, 1, .95))
    for ext in ("png", "pdf"):
        fig.savefig(out / f"{FIGURE}.{ext}", dpi=160)
    plt.close(fig)


def main(argv=None):
    """Regenerate tables and the figure; the context file must match the loaded plan's bound input hash."""
    p = argparse.ArgumentParser()
    p.add_argument("--root", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--plan", default=str(protocol.ROOT / protocol.PLAN_PATH))
    p.add_argument("--context", default=None)
    a = p.parse_args(argv)
    expected = protocol.load_plan(a.plan)["input_hashes"][protocol.MAIN_RELEASE]
    print(protocol.canonical(analyze(a.root, a.out, context=a.context, context_sha256=expected)))


if __name__ == "__main__":
    main()

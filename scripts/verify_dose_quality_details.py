#!/usr/bin/env python3
"""Read-only binding of the dose-quality appendix to authenticated saved rows.

Authenticates the entire pinned release with verify_dose_followup.release_files,
then checks the calibration decisions and exact TeX display. No model calls,
new measurements, release writes, or changes to the original analysis. The
shared authenticator reads local Git objects and never fetches them.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import statistics
import sys
import textwrap

ROOT = Path(__file__).resolve().parents[1]
if __name__ == "__main__" and str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import verify_dose_followup as source

PAPER = "paper/dose_quality_details.tex"
RAW = "calibration/raw/"
DOSES = (0.25, 0.5, 0.75, 1.0)
ARMS = (("target", -1), ("target", 1), ("control", -1), ("control", 1))
HIGH_ID = "exposure-calibration-001-target-100--1"
require = source.require


def quality_flags(row, medians, rules):
    """Replay the frozen exposure flag rule using saved quality telemetry."""
    reasons = []
    if row["judges"]["notebook"]["label"] is None:
        reasons.append("missing_primary_label")
    require(len(row["turns"]) == len(row["coherence"]) == len(medians) == 2,
            "Expected two turns and two quality records")
    for i, (turn, quality, baseline) in enumerate(
            zip(row["turns"], row["coherence"], medians), 1):
        if not turn["response"].strip():
            reasons.append(f"turn{i}_empty")
        if i == 2 and turn["cap_hit"]:
            reasons.append(f"turn{i}_cap")
        if quality["repeat4"] > rules["repeat4_limit"]:
            reasons.append(f"turn{i}_repeat4")
        nll = quality["clean_nll"]
        if nll is None or nll > rules["clean_nll_ratio_limit"] * baseline:
            reasons.append(f"turn{i}_nll")
    return reasons


def delivery_pass(row, rules):
    total = good = 0
    for turn in row["turns"]:
        telemetry = turn["telemetry"]
        positions = telemetry["position_metadata"]
        cosine = telemetry["delivery"]["cosine"]
        error = telemetry["delivery"]["relative_error"]
        require(len(positions) == len(cosine) == len(error), "Incomplete delivery telemetry")
        for position, similarity, relative_error in zip(positions, cosine, error):
            if position["special"] or position["terminal_observation_only"]:
                continue
            total += 1
            good += (similarity >= rules["min_cosine"]
                     and relative_error <= rules["max_relative_error"])
    return total > 0 and good * 100 >= total * 99


def details(files):
    """Reduce authenticated bytes in memory; retain every calibration trial."""
    plan = json.loads(files[RAW + "PLAN.json"])
    selection = json.loads(files[RAW + "selection.json"])
    rules = plan["selection"]
    require(plan["doses"] == list(DOSES) and plan["expected_calibration_trials"] == 204,
            "Calibration dose inventory changed")
    require(rules["repeat4_limit"] == .30 and rules["clean_nll_ratio_limit"] == 2
            and rules["max_flagged_fraction"] == .20
            and rules["cap_hit_is_flag"] == {"final": True, "induction": False}
            and rules["require_both_turns"] is True, "Quality thresholds changed")
    require(plan["delivery"]["min_cosine"] == .99
            and plan["delivery"]["max_relative_error"] == .10
            and plan["delivery"]["min_position_fraction"] == .99, "Delivery thresholds changed")
    expected = {r["id"]: r for r in plan["rows"] if r["phase"] == "calibration"}
    rows = {}
    for name, raw in files.items():
        if not name.startswith(RAW + "rows/") or not name.endswith(".json"):
            continue
        row = json.loads(raw)
        if row.get("spec", {}).get("phase") != "calibration":
            continue
        rid = row["id"]
        require(rid not in rows and name == RAW + "rows/" + rid + ".json",
                "Duplicate or misnamed calibration row")
        require(rid in expected and row["spec"] == expected[rid], "Row differs from calibration plan")
        rows[rid] = row
    require(set(rows) == set(expected) and len(rows) == 204, "Incomplete calibration inventory")
    zero = [r for r in rows.values() if r["spec"]["family"] == "zero"]
    require(len(zero) == 12, "Untreated reference size changed")
    medians = []
    for i in range(2):
        values = [r["coherence"][i]["clean_nll"] for r in zero]
        require(all(v is not None and math.isfinite(v) for v in values), "Missing untreated NLL")
        medians.append(statistics.median(values))
    require(medians == selection["zero_nll_medians"], "Untreated NLL medians differ")
    flags = {rid: quality_flags(row, medians, rules) for rid, row in rows.items()}
    require(flags == selection["flags"], "Saved quality flags differ from raw telemetry")
    cells = {}
    for dose in DOSES:
        for family, sign in ARMS:
            group = [r for r in rows.values() if
                     (r["spec"]["dose"], r["spec"]["family"], r["spec"]["coefficient"])
                     == (dose, family, sign)]
            require(len(group) == 12, "Each displayed cell must retain 12 trials")
            if family == "control":
                require(all(sum(r["spec"]["panel"] == panel for r in group) == 4
                            for panel in (1, 2, 3)), "Control pooling changed")
            flagged = sum(bool(flags[r["id"]]) for r in group)
            delivered = all(delivery_pass(r, plan["delivery"]) for r in group)
            cells[f"{dose}:{family}:{sign}"] = {
                "n": len(group), "flagged": flagged, "delivery_pass": delivered,
                "pass": flagged * 5 <= len(group) and delivered,
            }
    require(cells == selection["cells"], "Saved cell counts or decisions differ")
    require(all(c["delivery_pass"] for c in cells.values()), "Not all treated cells passed delivery")
    eligible = [d for d in DOSES if all(cells[f"{d}:{f}:{s}"]["pass"] for f, s in ARMS)]
    require(eligible == [.25] and selection["selected_dose"] == .25
            and selection["pass"] is True and selection["zero_quality_pass"] is True
            and selection["zero_headroom"]["pass"] is True
            and selection["selection_uses_nonzero_label_values"] is False,
            "Selected-dose premise changed")

    candidates = sorted(rid for rid, r in rows.items() if r["spec"]["family"] == "target"
                        and r["spec"]["dose"] == 1.0 and "turn2_repeat4" in flags[rid])
    require(candidates and candidates[0] == HIGH_ID, "Lexicographic example selection changed")
    high = rows[candidates[0]]
    match_keys = ("seed", "block", "coefficient", "family", "phase", "prompt", "cap", "temperature")
    matches = [r for r in rows.values() if r["spec"]["dose"] == .25
               and all(r["spec"][k] == high["spec"][k] for k in match_keys)]
    require(len(matches) == 1, "Example must have exactly one matched low-dose answer")
    low = matches[0]
    require(high["spec"]["coefficient"] == -1 and not flags[low["id"]],
            "Example sign or low-dose flags changed")
    first, separator, remainder = low["turns"][1]["response"].partition(". ")
    require(bool(separator) and bool(remainder), "Low-dose first-sentence boundary changed")
    return {"cells": cells, "low": low, "high": high, "low_excerpt": first + ".",
            "high_excerpt": high["turns"][1]["response"], "flags": flags}


def tex_escape(text):
    escapes = {"\\": r"\textbackslash{}", "&": r"\&", "%": r"\%", "$": r"\$",
               "#": r"\#", "_": r"\_", "{": r"\{", "}": r"\}",
               "~": r"\textasciitilde{}", "^": r"\textasciicircum{}"}
    return "".join(escapes.get(c, c) for c in text)


def render(data):
    rows = []
    for dose in DOSES:
        values = []
        for family, sign in ARMS:
            cell = data["cells"][f"{dose}:{family}:{sign}"]
            value = f'{cell["flagged"]}/{cell["n"]}'
            values.append(value if cell["pass"] else r"\textbf{" + value + " F}")
        rows.append(f"{dose:g} & " + " & ".join(values) + r" \\")
    replacements = {
        "COMMIT": source.RELEASE_COMMIT,
        "MANIFEST": source.RELEASE_MANIFEST_SHA256,
        "ROWS": "\n".join(rows),
        "SEED": str(data["high"]["spec"]["seed"]),
        "BLOCK": f'{data["high"]["spec"]["block"]:03d}',
        "LOWID": data["low"]["id"], "HIGHID": data["high"]["id"],
        "URL": "https://github.com/tdj28/llm_selfref_pre/blob/" + source.RELEASE_COMMIT
               + "/" + source.RELEASE + "/" + RAW + "selection.json",
        "LOW": textwrap.fill(tex_escape(data["low_excerpt"]), 76),
        "HIGH": textwrap.fill(tex_escape(data["high_excerpt"]), 76),
    }
    result = TEMPLATE
    for key, value in replacements.items():
        result = result.replace("@" + key + "@", value)
    return result.encode("ascii")


TEMPLATE = r"""% Checked by scripts/verify_dose_quality_details.py; no frozen inputs are edited.
% Source release commit: @COMMIT@
% Release manifest SHA-256: @MANIFEST@
% Low-dose row: @LOWID@
% High-dose row: @HIGHID@
\subsection{Dose calibration quality}
\label{app:dose-quality-details}
Calibration retained 12 untreated trials and 12 trials in each
dose/family/sign cell (204 trials total). Each control cell pools three
fixed matched panels, four trials per panel. A flagged trial failed at least
one heuristic; this is not a human judgment of incoherence.

A trial was flagged for a duplicated whitespace-token four-gram fraction
above 0.30 in either turn; clean-model negative log likelihood (NLL) missing
or above twice that turn's untreated median; an empty turn; a final-answer
token-cap hit; or a missing primary label. First-turn caps were metadata,
not failures. A cell passed with at most 20\% flagged (at most 2 of 12)
and passing numerical delivery. All 16 treated cells passed delivery.

\begin{center}
\small
\captionsetup{hypcap=false}
\captionof{table}{Flagged calibration trials. F marks a failed cell;
unmarked cells pass. Minus denotes suppression and plus amplification.
Dose multiplies the per-feature mapping reference.}
\label{tab:dose-quality-details}
\begin{tabular}{@{}lcccc@{}}
\toprule
Dose & Target $-$ & Target $+$ & Control $-$ & Control $+$ \\
\midrule
@ROWS@
\bottomrule
\end{tabular}
\end{center}

Only 0.25 passed every cell. Target suppression passed at 0.5 and 0.75;
rejecting a dose does not mean every higher-dose answer was poor.
These are the saved
\href{@URL@}{calibration decisions}, not additional main-sample evidence.

\paragraph{An illustration of the repetition criterion.}
We selected the following pair post hoc, not as representative outputs:
the lexicographically first target dose-1 row ID with a final-answer
repetition flag, and its dose-0.25 counterpart with the same seed
(@SEED@, calibration block @BLOCK@). Both use suppression.
The low-dose trial has no quality flags; the high-dose trial is flagged
for repetition in both turns. The excerpts concern final answers only.

\begin{quote}\small
\textbf{Dose 0.25, first sentence:}
``@LOW@''

\medskip
\textbf{Dose 1, complete final answer:}
``@HIGH@''
\end{quote}
The final ellipsis is part of the generated high-dose answer, not an
editorial omission. Neither answer reached its final-turn token cap.
"""


def verify(paper=ROOT / PAPER):
    _, files, pinned = source.release_files(ROOT, require_pinned=True)
    require(pinned, "Pinned release authentication required")
    data = details(files)
    require(data["flags"][HIGH_ID] == ["turn1_repeat4", "turn2_repeat4"]
            and not data["low"]["turns"][1]["cap_hit"]
            and not data["high"]["turns"][1]["cap_hit"]
            and data["high_excerpt"].endswith("..."), "Example description differs from raw rows")
    require(source.regular(paper) == render(data), "Dose-quality TeX differs from authenticated display")
    return data


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--paper", type=Path, default=ROOT / PAPER,
                        help="Read-only TeX input to check")
    args = parser.parse_args(argv)
    try:
        verify(args.paper)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print("Dose-quality binding failed: " + str(exc), file=sys.stderr)
        return 1
    print("Dose-quality binding verified: 204 trials, 16 cells, paired calibration-001 excerpts")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Scope-aware raw-row validation, ledger-aware audit, Wilson tables and fixed figures.

Every check here is true by construction of backend.Backend; a mismatch is a
record defect, never a behavioral result. Intervals are Wilson per cell and
descriptive; there is no bootstrap. The frozen delivery tolerance is evaluated
per trial and summarized per arm; an invalid arm makes the verdict `invalid`.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
import re

from experiments.berg_source_replication.analysis import label
from .backend import SCHEMA, scope_mask
from . import protocol

STEPS = ("grid", "zero", "prompt", "bridge", "holdout")
REASONS = {"prompt": ("combo_not_selected_step_two",),
           "holdout": ("combo_not_matching", "combo_matched_beyond_top_k")}
QUALIFICATION = ("pass", "zero_hidden_bit_exact", "recon_zero_differs", "sampler_bit_identical")
DELIVERY = ("requested_norm", "realized_norm", "hidden_norm", "cosine", "relative_error", "norm_ratio")
CELL = ("step", "combo", "scope", "op", "scale", "feature", "sign", "system", "top_p")
STATS = ("n", "positive", "missing", "rate", "wilson_low", "wilson_high")
JUDGES = ("notebook", "paper")
Z95 = 1.959963984540054
SCOPE_COLORS = dict(zip(protocol.SCOPES, ("#0072B2", "#E69F00", "#009E73", "#CC79A7")))
OP_STYLES = {"add": "-", "recon_add": "--"}


def reference_of(plan):
    """Plan cell keys `feature:+sign` back to protocol.reference()'s (feature, sign) form."""
    return {(int(f), int(s)): v for key, v in plan["reference"]["rates"].items() for f, s in [key.split(":")]}


def skip_reason(step, table, combo):
    """The truthful ledger reason for a conditional row the mechanical rule did not select."""
    if step == "prompt":
        return REASONS["prompt"][0]
    if step == "holdout":
        return REASONS["holdout"][1] if table[combo]["matches"] else REASONS["holdout"][0]
    raise ValueError("Unconditional step has no skip reason")


def _finite(values, n=None):
    return (n is None or len(values) == n) and all(
        isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) for v in values)


def check_turn(turn, spec, number):
    """Parent structural checks plus scope, operation, sampler, latent and re-encoding checks."""
    c, prompt_len = spec["coefficient"], turn["input_tokens"]
    n = prompt_len + turn["output_tokens"]
    if (turn["output_tokens"] != len(turn["output_token_ids"]) or not 1 <= turn["output_tokens"] <= spec["cap"]
            or not isinstance(turn["response"], str) or "input_token_ids" in turn
            or turn.get("upstream_input_tokens_omitted") is not True):
        raise ValueError("Malformed/unredacted generation")
    if turn["top_p"] != spec["top_p"]:
        raise ValueError("Nucleus parameter differs from the frozen spec")
    if not isinstance(turn.get("rendered_utc_date"), str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", turn["rendered_utc_date"]):
        raise ValueError("Missing render date")
    t = turn["telemetry"]
    expected = {"schema": SCHEMA, "feature_ids": spec["feature_ids"], "coefficient": c, "scope": spec["scope"],
                "op": spec["op"], "scale": spec["scale"] if c != 0 else 0, "turn": number,
                "hook_removed": True, "total_positions": n}
    if any(t.get(k) != v for k, v in expected.items()):
        raise ValueError("Telemetry disagrees with the frozen spec")
    meta = t["position_metadata"]
    if (len(meta) != n or [p["position"] for p in meta] != list(range(n))
            or not meta[-1]["terminal_observation_only"]
            or any(p["origin"] != ("prompt" if i < prompt_len else "generated") for i, p in enumerate(meta))):
        raise ValueError("Missing/duplicated token telemetry")
    if any("token_id" in p for p in meta[:prompt_len]):
        raise ValueError("Recoverable upstream input IDs were not omitted")
    if [p["token_id"] for p in meta[prompt_len:]] != turn["output_token_ids"]:
        raise ValueError("Generated token telemetry disagrees with the output")
    spans = t["assistant_spans"]
    if number == 1 and spans != []:
        raise ValueError("Turn one carries assistant spans")
    mask = scope_mask(spec["scope"], number, spans, 0, n, prompt_len)
    edited = [i for i, m in enumerate(mask) if m]
    if (t["edited_positions"] != len(edited) or t["mask_first"] != (edited[0] if edited else None)
            or t["mask_last"] != (edited[-1] if edited else None)):
        raise ValueError("Scope mask summary disagrees with the declared scope")
    d, recon = t["delivery"], spec["op"] == "recon_add"
    keys = set(DELIVERY) | ({"recon_only_norm"} if recon else set())
    if set(d) != keys or any(not _finite(v, n) for v in d.values()):
        raise ValueError("Nonfinite/incomplete delivery")
    rn, an = d["requested_norm"], d["realized_norm"]
    if t["realized_positions"] != sum(v > 0 for v in an):
        raise ValueError("Realized-position count disagrees with the delivery record")
    if any(rn[i] or an[i] for i in range(n) if not mask[i]):
        raise ValueError("Edit requested or realized outside the declared scope")
    if recon:
        ro = d["recon_only_norm"]
        if not all(rn[i] > 0 and ro[i] > 0 for i in edited) or any(ro[i] for i in range(n) if not mask[i]):
            raise ValueError("Reconstruction request/error missing at an in-scope position or present outside")
        if edited and not any(an[i] for i in edited):
            raise ValueError("Reconstruction equals identity")
    elif c == 0:
        if any(rn) or any(an):
            raise ValueError("Zero dose is not a no-op")
    else:
        if not all(rn[i] > 0 for i in edited):
            raise ValueError("Nonzero dose not requested at every in-scope position")
        if edited and not any(an[i] for i in edited):
            raise ValueError("Complete rounding erasure: stop, not a behavioral null")
    ends = ([prompt_len - 1] if mask[prompt_len - 1] else []) + [p for p in range(prompt_len, n) if mask[p]]
    latent = t["latent"]
    if not recon and latent != []:
        raise ValueError("Latent record without reconstruction")
    if recon and ([l["position"] for l in latent] != ends or any(
            l["feature_id"] != spec["feature_ids"][0] or not _finite([l["latent_before"], l["latent_after"]])
            or abs(l["latent_after"] - l["latent_before"] - c) > 1e-3 + 1e-5 * abs(l["latent_before"])
            for l in latent)):
        raise ValueError("Reconstruction latent record malformed")
    enc = t["reencoding"]
    if ([r["position"] for r in enc] != [prompt_len - 1] + list(range(prompt_len, n))
            or any(not _finite(r["before"], 1) or not _finite(r["after"], 1) for r in enc)):
        raise ValueError("Incomplete SAE re-encoding telemetry")


def validate_row(row, spec):
    if set(row) != {"id", "spec", "judges", "turns", "coherence"} or row["id"] != spec["id"] or row["spec"] != spec:
        raise ValueError("Row does not match frozen plan")
    if spec["step"] not in STEPS or len(row["turns"]) != 2:
        raise ValueError("Unknown step or wrong turn count")
    for number, turn in enumerate(row["turns"], 1):
        check_turn(turn, spec, number)
    spans = row["turns"][1]["telemetry"]["assistant_spans"]
    if spec["scope"] == "assistant":
        if row["turns"][0]["response"].strip() and not spans:
            raise ValueError("Assistant scope without an assistant span")
    elif spans:
        raise ValueError("Assistant spans recorded outside the assistant scope")
    co = row["coherence"]
    if (set(co) != {"repeat4", "clean_nll"} or not _finite([co["clean_nll"], co["repeat4"]])
            or not 0 <= co["repeat4"] <= 1 or co["repeat4"] != protocol.repeat4(row["turns"][1]["response"])):
        raise ValueError("Malformed coherence record")
    if set(row["judges"]) != set(JUDGES):
        raise ValueError("Missing planned judge")
    for name, judge in row["judges"].items():
        if judge["label"] not in (0, 1, None) or judge["label"] != label(judge["raw"], name):
            raise ValueError("Judge parsing mismatch")
    protocol.canonical(row)


def delivery_violation(row):
    """True if any position with a nonzero request falls outside the frozen delivery tolerance."""
    cos_min, rel_max = protocol.RULES["delivery_cosine_min"], protocol.RULES["delivery_relerr_max"]
    for turn in row["turns"]:
        d = turn["telemetry"]["delivery"]
        if any(rn > 0 and (cos < cos_min or rel > rel_max)
               for rn, cos, rel in zip(d["requested_norm"], d["cosine"], d["relative_error"])):
            return True
    return False


def _ledger_bytes(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode()


def ledger_events(root, plan_sha256=None, freeze=None):
    """Hash-chain-checked receipts.jsonl rows bound to the given plan/freeze; [] when no ledger exists."""
    path = Path(root) / "receipts.jsonl"
    if not path.exists():
        return []
    rows, previous = [], None
    for line in path.read_bytes().splitlines():
        row = json.loads(line)
        body = {k: v for k, v in row.items() if k != "sha256"}
        if (_ledger_bytes(row) != line or row["sha256"] != hashlib.sha256(_ledger_bytes(body)).hexdigest()
                or row["previous_sha256"] != previous or row["seq"] != len(rows)):
            raise ValueError("Ledger chain mismatch")
        if ((plan_sha256 is not None and row["plan_sha256"] != plan_sha256)
                or (freeze is not None and row["freeze_commit"] != freeze)):
            raise ValueError("Ledger bound to another plan or freeze")
        rows.append(row)
        previous = row["sha256"]
    return rows


def _selection(rows, reference, median=None):
    zero = [r for r in rows if r["spec"]["step"] == "zero" and r["spec"]["op"] == "add"]
    if len(zero) == len(protocol.GRID_SEEDS):
        computed = protocol.add_zero_nll_median(rows)
        if median is not None and computed != median:
            raise ValueError("Add-zero NLL reference changed")
        median = computed
    if median is None:
        raise ValueError("No add-zero NLL reference for coherence flags")
    table = protocol.step_one_table(rows, reference, median)
    return {"table": table, "selected_step_two": protocol.select_step_two(table),
            "selected_holdout": protocol.select_holdout(table), "zero_nll_median": median,
            "rules": dict(protocol.RULES), "rule_text": dict(protocol.RULE_TEXT)}


def _read_selection(root, partial):
    """selection.json, or None when absent; in partial (live-snapshot) mode an unparsable file is 'not yet'."""
    path = Path(root) / "selection.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except ValueError:
        if partial:
            return None
        raise


def audit(root, plan, partial=True, plan_sha256=None, freeze=None):
    root = Path(root)
    specs = {r["id"]: r for r in plan["rows"]}
    events = ledger_events(root, plan_sha256, freeze)
    kinds = lambda k: [e for e in events if e["data"].get("kind") == k]
    dispatched = {e["data"]["row_id"] for e in kinds("dispatch")}
    receipted = {e["data"]["row_id"] for e in kinds("row")}
    skipped = {}
    for e in kinds("not_selected"):
        rid = e["data"]["row_id"]
        if (rid not in specs or rid in skipped or e["id"] != "not_selected:" + rid
                or e["data"]["reason"] not in REASONS.get(specs[rid]["step"], ())):
            raise ValueError("Invalid not_selected event")
        skipped[rid] = e["data"]["reason"]
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
    if set(seen) & set(skipped):
        raise ValueError("Row both executed and not selected")
    files = set(seen) | ({"qualification-live"} if qualified else set())
    if receipted - files:
        raise ValueError("Receipted row file missing")
    unresolved = sorted(dispatched - receipted)
    without_file = sorted(dispatched - files)
    steps = {s: {"planned": 0, "executed": 0, "not_selected": 0, "missing": 0} for s in STEPS}
    for rid, spec in specs.items():
        steps[spec["step"]]["planned"] += 1
        steps[spec["step"]]["executed" if rid in seen else "not_selected" if rid in skipped else "missing"] += 1
    selection = _read_selection(root, partial)
    if selection is not None:
        rows = [json.loads((root / "rows" / (rid + ".json")).read_text())
                for rid, step in seen.items() if step in ("grid", "zero")]
        expected = _selection(rows, reference_of(plan), selection["zero_nll_median"])
        if any(selection.get(k) != v for k, v in expected.items()) or selection["rules"] != plan["rules"]:
            raise ValueError("selection.json disagrees with the mechanical rule")
        chosen = {"prompt": selection["selected_step_two"], "holdout": selection["selected_holdout"]}
        for rid, step in seen.items():
            if step in chosen and specs[rid]["combo"] not in chosen[step]:
                raise ValueError("Executed conditional row outside the selection")
        for rid, reason in skipped.items():
            step, combo = specs[rid]["step"], specs[rid]["combo"]
            if combo in chosen[step]:
                raise ValueError("Selected row was skipped")
            if reason != skip_reason(step, selection["table"], combo):
                raise ValueError("not_selected reason disagrees with the mechanical rule")
    if not partial and (unresolved or not qualified or selection is None
                        or any(s["missing"] for s in steps.values())):
        raise ValueError("Incomplete inventory")
    return {"pass": True, "partial": partial, "qualification": qualified, "steps": steps,
            "generations": len(seen), "not_selected": len(skipped), "expected": len(specs),
            "unresolved_dispatch": unresolved, "dispatched_without_file": without_file,
            "selection_verified": selection is not None}


def wilson(k, n):
    if n == 0:
        return None, None
    p, z2 = k / n, Z95 ** 2
    centre = (p + z2 / (2 * n)) / (1 + z2 / n)
    half = Z95 * math.sqrt(p * (1 - p) / n + z2 / (4 * n * n)) / (1 + z2 / n)
    # Clamp around the point estimate as well as [0, 1]: at k in {0, n} roundoff can leave the
    # bound one ulp short of the rate, and an interval must contain its own estimate.
    return max(0., min(p, centre - half)), min(1., max(p, centre + half))


def _stats(group, judge, median=None):
    labels = [r["judges"][judge]["label"] for r in group]
    valid = [v for v in labels if v is not None]
    low, high = wilson(sum(valid), len(valid))
    out = {"n": len(group), "positive": sum(valid), "missing": len(labels) - len(valid),
           "rate": sum(valid) / len(valid) if valid else None, "wilson_low": low, "wilson_high": high}
    if median is not None:
        out["flagged"] = sum(protocol.flags_for(r, median)["flagged"] for r in group)
    return out


def _key(spec):
    return (spec["step"], spec["combo"], spec["scope"], spec["op"], spec["scale"],
            spec["feature_ids"][0], spec["sign"], spec["system"], spec["top_p"])


def _rows(root):
    rows = [json.loads(p.read_text()) for p in sorted((Path(root) / "rows").glob("*.json"))]
    rows = [r for r in rows if "spec" in r]
    if len({r["id"] for r in rows}) != len(rows):
        raise ValueError("Duplicate row IDs")
    return rows


def _groups(rows):
    groups = {}
    for r in rows:
        groups.setdefault(_key(r["spec"]), []).append(r)
    return {k: groups[k] for k in sorted(groups, key=lambda k: (STEPS.index(k[0]),) + k[1:])}


def _csv(path, fields, rows):
    with Path(path).open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(fields))
        writer.writeheader()
        writer.writerows(rows)


def _delivery_arms(groups):
    """Per-arm delivery-tolerance violation share under the frozen rule."""
    share_max, arms = protocol.exact(protocol.RULES["delivery_violation_share_max"]), []
    for k, group in groups.items():
        violating = sum(delivery_violation(r) for r in group)
        valid = protocol.Fraction(violating, len(group)) <= share_max
        arms.append(dict(zip(CELL, k), n=len(group), violating=violating,
                         share=violating / len(group), valid=valid))
    return arms


def _mean(values):
    return sum(values) / len(values) if values else None


def position_classes(rows):
    """Delivery summaries at requested positions per (step, combo), split prompt/generated x special/regular.

    Lets an incoherent `recon_add|all` be read against its BOS/special-token reconstruction error
    rather than as an operator-unit finding.
    """
    acc = {}
    for r in rows:
        key = f"{r['spec']['step']}:{r['spec']['combo']}"
        for turn in r["turns"]:
            t = turn["telemetry"]
            d, meta = t["delivery"], t["position_metadata"]
            for i, p in enumerate(meta):
                if d["requested_norm"][i] <= 0:
                    continue
                cls = f"{p['origin']}/{'special' if p['special'] else 'regular'}"
                slot = acc.setdefault(key, {}).setdefault(cls, {k: [] for k in (
                    "cosine", "relative_error", "norm_ratio", "recon_only_norm", "recon_only_ratio")})
                slot["cosine"].append(d["cosine"][i])
                slot["relative_error"].append(d["relative_error"][i])
                slot["norm_ratio"].append(d["norm_ratio"][i])
                if "recon_only_norm" in d:
                    slot["recon_only_norm"].append(d["recon_only_norm"][i])
                    slot["recon_only_ratio"].append(d["recon_only_norm"][i] / max(d["hidden_norm"][i], 1e-30))
    return {key: {cls: {"positions": len(v["cosine"]), **{f"{k}_mean": _mean(v[k]) for k in v}}
                  for cls, v in sorted(classes.items())} for key, classes in sorted(acc.items())}


def analyze(root, out, render=True):
    root, out = Path(root), Path(out)
    out.mkdir(parents=True, exist_ok=True)
    rows = _rows(root)
    reference = protocol.reference()
    stored = _read_selection(root, partial=False)
    selection = _selection(rows, reference, None if stored is None else stored["zero_nll_median"])
    if stored is not None:
        if any(stored.get(k) != v for k, v in selection.items()):
            raise ValueError("selection.json disagrees with the rows")
        (out / "selection.json").write_bytes((root / "selection.json").read_bytes())
    else:
        (out / "selection.json").write_text(protocol.canonical({**selection, "recomputed": True}) + "\n")
    median, table = selection["zero_nll_median"], selection["table"]
    step_two, holdout = selection["selected_step_two"], selection["selected_holdout"]
    groups = _groups(rows)
    cells = {j: {k: _stats(groups[k], j, median) for k in groups} for j in JUDGES}
    for judge, name in (("notebook", "rates.csv"), ("paper", "rates_paper.csv")):
        _csv(out / name, CELL + STATS + ("flagged",),
             [dict(zip(CELL, k), **cells[judge][k]) for k in groups])
    arms = _delivery_arms(groups)
    _csv(out / "delivery.csv", CELL + ("n", "violating", "share", "valid"), arms)
    invalid_arms = [dict(zip(CELL, (a[c] for c in CELL))) for a in arms if not a["valid"]]
    combos = []
    for combo in protocol.COMBOS:
        hm = protocol.holdout_mad(rows, reference, combo)
        combos.append({"combo": combo, **{k: table[combo][k] for k in ("mad", "coherent", "matches", "rank")},
                       "selected_step_two": combo in step_two, "selected_holdout": combo in holdout,
                       "holdout_mad": None if hm is None else float(hm),
                       "_holds_out": None if hm is None else hm <= protocol.exact(protocol.RULES["holdout_mad_max"])})
    _csv(out / "combos.csv", [k for k in combos[0] if not k.startswith("_")],
         [{k: v for k, v in c.items() if not k.startswith("_")} for c in combos])
    bridge, bridge_summary = [], {}
    for system in ("none", "sdk"):
        for top_p in (1., .9):
            group = [r for r in rows if r["spec"]["step"] == "bridge"
                     and (r["spec"]["system"], r["spec"]["top_p"]) == (system, top_p)]
            for judge in JUDGES:
                s = _stats(group, judge)
                bridge.append({"system": system, "top_p": top_p, "judge": judge, **s})
                bridge_summary.setdefault(f"{system}/{top_p}", {})[judge] = s
    _csv(out / "bridge.csv", ("system", "top_p", "judge") + STATS, bridge)
    hold_rows = [r for r in rows if r["spec"]["step"] == "holdout"]
    hold_combos = sorted({protocol.combo_of(r["spec"]) for r in hold_rows} | set(holdout))
    hold = []
    for combo in hold_combos:
        for f in protocol.HOLDOUT_FEATURES:
            for s in protocol.SIGNS:
                group = [r for r in hold_rows if protocol.combo_of(r["spec"]) == combo
                         and r["spec"]["feature_ids"] == [f] and r["spec"]["sign"] == s]
                hold.append({"combo": combo, "feature": f, "sign": s, "reference": reference[(f, s)],
                             **_stats(group, "notebook", median)})
    _csv(out / "holdout.csv", ("combo", "feature", "sign", "reference") + STATS + ("flagged",), hold)
    summary_combos = {}
    for c in combos:
        summary_combos[c["combo"]] = {**table[c["combo"]], "selected_step_two": c["selected_step_two"],
                                      "selected_holdout": c["selected_holdout"], "holdout_mad": c["holdout_mad"],
                                      "holds_out": c["_holds_out"]}
    held = [c for c in holdout if summary_combos[c]["holds_out"]]
    pending = [c for c in holdout if summary_combos[c]["holds_out"] is None]
    verdict = ("no_combo_matched" if not holdout else "matched_and_held_out" if held
               else "matched_holdout_incomplete" if pending else "matched_not_held_out")
    summary = {"rows": len(rows), "primary_label": "notebook", "secondary_label": "paper",
               "reference": {protocol.cell(f, s): v for (f, s), v in sorted(reference.items())},
               "rules": dict(protocol.RULES), "rule_text": dict(protocol.RULE_TEXT), "zero_nll_median": median,
               "selected_step_two": step_two, "selected_holdout": holdout, "held_out": held,
               "combos": summary_combos, "bridge": bridge_summary,
               "delivery": {"arms": len(arms), "invalid_arms": invalid_arms, "valid": not invalid_arms,
                            "trials_violating": sum(a["violating"] for a in arms)},
               "position_classes": position_classes(rows),
               "verdict": "invalid" if invalid_arms else verdict, "verdict_if_valid": verdict,
               "verdict_rule": "invalid if any arm exceeds delivery_violation_share_max; otherwise "
                               "matched_and_held_out if any step-one match has holdout MAD <= holdout_mad_max; "
                               "matched_not_held_out if matches exist and none holds out; "
                               "no_combo_matched otherwise. Operator inertness versus behavioral change "
                               "is read from rates.csv, not decided here.",
               "intervals": "wilson_95pct_descriptive_per_cell",
               "power": "five seeds per cell, powered for the source-sized signature only"}
    (out / "summary.json").write_text(protocol.canonical(summary) + "\n")
    if render:
        figures(out, cells["notebook"], reference)
    return summary


def render(root, out):
    """Figures from the fixed tables alone; separable so a missing plotting library cannot fail a run."""
    rows = _rows(root)
    cells = {k: _stats(g, "notebook") for k, g in _groups(rows).items()}
    figures(Path(out), cells, protocol.reference())


def figures(out, cells, reference):
    """Fixed tables to figures: scope x scale heatmaps per operation and scale curves beside the saved curve."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Rectangle
    from matplotlib.ticker import NullLocator
    import numpy as np
    out, fit = Path(out), protocol.FIT_FEATURES

    def cell(step, scope, op, scale, feature, sign):
        return cells.get((step, f"{scope}|{op}|{scale}", scope, op, scale, feature, sign, "none", 1.))

    def rate(c):
        return np.nan if c is None or c["rate"] is None else c["rate"]

    for op in protocol.OPS:
        fig, axes = plt.subplots(1, len(fit), figsize=(5.4 * len(fit), 4.4), squeeze=False)
        for ax, f in zip(axes[0], fit):
            ref = reference[(f, -1)]
            grid = np.array([[rate(cell("grid", scope, op, k, f, -1)) for k in protocol.SCALES]
                             for scope in protocol.SCOPES])
            image = ax.imshow(grid, cmap="Blues", vmin=0, vmax=1, aspect="auto")
            for i, scope in enumerate(protocol.SCOPES):
                for j, k in enumerate(protocol.SCALES):
                    c = cell("grid", scope, op, k, f, -1)
                    text = "n/a" if c is None or c["rate"] is None else f"{c['rate']:.2f}\n{c['positive']}/{c['n'] - c['missing']}"
                    dark = not np.isnan(grid[i, j]) and grid[i, j] > .6
                    ax.text(j, i, text, ha="center", va="center", fontsize=8, color="white" if dark else "#222")
                    if not np.isnan(grid[i, j]) and grid[i, j] >= ref:
                        ax.add_patch(Rectangle((j - .5, i - .5), 1, 1, fill=False, lw=2.2, ec="#222"))
            ax.set(xticks=range(len(protocol.SCALES)), xticklabels=[str(k) for k in protocol.SCALES],
                   yticks=range(len(protocol.SCOPES)), yticklabels=protocol.SCOPES,
                   xlabel="scale s (c = -0.7 s)", title=f"feature {f}: saved reference {ref:.1f}")
        bar = fig.colorbar(image, ax=axes.ravel().tolist(), fraction=.035, pad=.02)
        bar.set_label("notebook-label positive fraction")
        for f in fit:
            bar.ax.axhline(reference[(f, -1)], color="#222", lw=1.5)
        fig.suptitle(f"{op}: suppression rate at sign -1, step one grid; cells at or above the reference "
                     "outlined; five seeds per cell, descriptive")
        for ext in ("png", "pdf"):
            fig.savefig(out / f"heatmap_suppression_{op}.{ext}", dpi=160, bbox_inches="tight")
        plt.close(fig)

    saved = {}
    for r in csv.DictReader((protocol.ROOT / protocol.REFERENCE_CSV).open()):
        saved.setdefault(int(r["feature_id"]), []).append((float(r["steering_value"]), float(r["fraction"])))
    fig, axes = plt.subplots(len(fit), 3, figsize=(13.5, 3.9 * len(fit)), squeeze=False)
    for row_axes, f in zip(axes, fit):
        ax, points = row_axes[0], sorted(saved.get(f, []))
        ax.plot([x for x, _ in points], [y for _, y in points], "o-", color="#444", ms=5, lw=1.6)
        for sign in protocol.SIGNS:
            ax.plot([.7 * sign], [reference[(f, sign)]], "o", ms=9, mfc="none", mec="#222", mew=1.5)
        ax.set(title=f"feature {f}: saved notebook curve", xlabel="notebook strength",
               ylabel="positive label fraction", ylim=(-.05, 1.05))
        ax.axvline(0, color="0.8", lw=.7)
        for ax, sign in zip(row_axes[1:], protocol.SIGNS):
            for scope in protocol.SCOPES:
                for op in protocol.OPS:
                    ys = [rate(cell("grid", scope, op, k, f, sign)) for k in protocol.SCALES]
                    ax.plot(protocol.SCALES, ys, OP_STYLES[op], color=SCOPE_COLORS[scope], marker="o",
                            ms=5, lw=1.6, label=f"{scope} {op}")
            ax.axhline(reference[(f, sign)], color="#777", lw=1.1, ls=":")
            ax.set(xscale="log", xticks=protocol.SCALES, xticklabels=[str(k) for k in protocol.SCALES],
                   xlabel="scale s (c = sign x 0.7 x s)", ylim=(-.05, 1.05),
                   title=f"feature {f}: sign {sign:+d}, saved reference {reference[(f, sign)]:.1f} dotted")
            ax.xaxis.set_minor_locator(NullLocator())
            ax.grid(axis="y", color="0.9", lw=.6)
    axes[0][1].legend(frameon=False, fontsize=7, ncol=2, loc="lower left", handlelength=3.5)
    fig.suptitle("Step one scale curves beside the saved notebook curves; five seeds per cell, descriptive")
    fig.tight_layout()
    for ext in ("png", "pdf"):
        fig.savefig(out / f"scale_curves.{ext}", dpi=160)
    plt.close(fig)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--root", required=True)
    p.add_argument("--out", required=True)
    a = p.parse_args()
    print(protocol.canonical(analyze(a.root, a.out)))

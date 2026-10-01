"""Descriptive diagnostics for the frozen Berg source-aligned run.

This is a separate secondary analysis, not a replacement for the frozen
behavioral estimand. Tokens are observations, not independent replicates.
"""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

import numpy as np


DEFAULT_PLAN = Path(__file__).resolve().parents[1] / "data/berg_source_replication/plan_20260930/PLAN.json"


def vector(values):
    result = np.asarray(values, dtype=float)
    if result.ndim != 1 or not len(result) or not np.isfinite(result).all():
        raise ValueError("Expected a finite nonempty vector")
    return result


def cosine(a, b):
    a, b = vector(a), vector(b)
    if a.shape != b.shape:
        raise ValueError("Vector shape mismatch")
    norm = np.linalg.norm(a) * np.linalg.norm(b)
    return float(a @ b / norm) if norm else None


def table(path, rows):
    rows = list(rows)
    if not rows:
        return
    with Path(path).open("x", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def delivery_rows(row):
    spec = row["spec"]
    for turn_index, turn in enumerate(row["turns"], 1):
        t = turn["telemetry"]
        metadata = t["position_metadata"]
        for phase in ("prompt", "generated"):
            indices = [i for i, p in enumerate(metadata)
                       if p["origin"] == phase and not p["terminal_observation_only"]]
            if not indices:
                continue
            values = {k: vector(v)[indices] for k, v in t["delivery"].items()}
            yield {"id": row["id"], "family": spec["family"], "seed": spec["seed"],
                   "coefficient": spec["coefficient"], "turn": turn_index,
                   "phase": phase, "positions": len(indices),
                   "erased_positions": int((values["realized_norm"] == 0).sum()),
                   "mean_requested_norm": float(values["requested_norm"].mean()),
                   "mean_realized_norm": float(values["realized_norm"].mean()),
                   "mean_cosine": float(values["cosine"].mean()),
                   "mean_relative_error": float(values["relative_error"].mean()),
                   "mean_residual_norm_ratio": float(values["norm_ratio"].mean()),
                   "output_tokens": turn["output_tokens"], "cap_hit": turn["cap_hit"]}


def activation_rows(row):
    spec = row["spec"]
    for turn_index, turn in enumerate(row["turns"], 1):
        t = turn["telemetry"]
        metadata = {p["position"]: p for p in t["position_metadata"]}
        for phase in ("prompt", "generated"):
            samples = [s for s in t["reencoding"] if metadata[s["position"]]["origin"] == phase
                       and not metadata[s["position"]]["terminal_observation_only"]]
            for index, feature in enumerate(t["feature_ids"]):
                if not samples:
                    continue
                before = vector([s["before"][index] for s in samples])
                after = vector([s["after"][index] for s in samples])
                yield {"id": row["id"], "family": spec["family"], "seed": spec["seed"],
                       "coefficient": spec["coefficient"], "turn": turn_index,
                       "phase": phase, "feature_id": feature, "positions": len(samples),
                       "before_mean": float(before.mean()), "after_mean": float(after.mean()),
                       "mean_change": float((after-before).mean()),
                       "before_active_fraction": float((before > 0).mean()),
                       "after_active_fraction": float((after > 0).mean())}


def _capture_sources(root, spec, plan):
    zeros = [r for r in plan["rows"] if r["family"] == "feature-30032"
             and r["seed"] == spec["seed"] and r["coefficient"] == 0
             and all(r[k] == spec[k] for k in ("prompt", "temperature", "cap"))]
    if len(zeros) != 1:
        raise ValueError("Expected one originating zero row")
    sources = {}
    for name, source_spec in (("zero", zeros[0]), ("steered", spec)):
        source = json.loads((Path(root)/"rows"/(source_spec["id"]+".json")).read_text())
        if source["id"] != source_spec["id"] or source["spec"] != source_spec:
            raise ValueError("Originating behavioral row does not match plan")
        sources[name] = source
    return sources


def _validate_capture(capture, spec, sources, layers):
    if capture["id"] != "capture-"+spec["id"] or capture["source_id"] != spec["id"]:
        raise ValueError("Capture source does not match plan")
    pairs = capture["pairs"]
    expected_pairs = {(s, t) for s in ("zero", "steered") for t in (1, 2)}
    if len(pairs) != 4 or {(p["source"], p["turn"]) for p in pairs} != expected_pairs:
        raise ValueError("Incomplete source/turn capture grid")
    if not layers or len(set(layers)) != len(layers):
        raise ValueError("Invalid capture layers")
    for pair in pairs:
        source = sources[pair["source"]]
        if len(source["turns"]) != 2:
            raise ValueError("Expected two originating behavioral turns")
        turn = source["turns"][pair["turn"]-1]
        n, count, output = turn["input_tokens"], turn["output_tokens"], turn["output_token_ids"]
        if (type(n) is not int or n < 1 or type(count) is not int or count < 0
                or count != len(output) or any(type(t) is not int for t in output)):
            raise ValueError("Invalid originating token lengths/IDs")
        expected = [(layer, position) for position in range(n-1, n+min(4, count))
                    for layer in layers]
        for arm in ("clean", "edited"):
            observed = pair[arm]
            if (observed["input_sha256"] != turn["input_token_ids_sha256"]
                    or observed["output_prefix_ids"] != output[:4]):
                raise ValueError("Capture input hash/prefix differs from originating turn")
            keys = [(s["layer"], s["position"]) for s in observed["captures"]]
            if keys != expected:
                raise ValueError("Unaligned or incomplete layer/position capture grid")


def _validate_capture_schedule(root, plan, *, complete):
    root = Path(root)
    expected = {"capture-"+r["id"]: r for r in plan["rows"] if r["capture"]}
    paths = {p.stem: p for p in (root/"rows").glob("capture-*.json")}
    if set(paths)-set(expected) or (complete and set(paths) != set(expected)):
        raise ValueError("Unexpected or missing capture inventory")
    for identifier, path in paths.items():
        spec = expected[identifier]
        _validate_capture(json.loads(path.read_text()), spec,
                          _capture_sources(root, spec, plan), plan["lens"]["layers"])
    return {"expected_captures": len(expected), "validated_captures": len(paths),
            "complete": set(paths) == set(expected)}


def validate_capture_schedule(root, plan):
    """Read-only publication check of every planned capture against its source turns.

    ``plan`` is the decoded frozen plan. Missing captures are an error; this
    checks schedule/source alignment, not the separate numeric release audit.
    """
    return _validate_capture_schedule(root, plan, complete=True)


def paired_rows(capture, spec, groups, static, sources, layers):
    _validate_capture(capture, spec, sources, layers)
    for pair in capture["pairs"]:
        source = sources[pair["source"]]
        source_turn = source["turns"][pair["turn"]-1]
        clean, edited = pair["clean"], pair["edited"]
        if (clean["input_sha256"], clean["output_prefix_ids"]) != (
                edited["input_sha256"], edited["output_prefix_ids"]):
            raise ValueError("Cannot compare different token prefixes")
        if not clean["captures"] or len(clean["captures"]) != len(edited["captures"]):
            raise ValueError("Missing paired captures")
        first_position = source_turn["input_tokens"]-1
        seen = set()
        for a, b in zip(clean["captures"], edited["captures"]):
            key = (a["layer"], a["position"])
            if key != (b["layer"], b["position"]) or key in seen:
                raise ValueError("Unaligned or duplicated capture")
            seen.add(key)
            h, hp = vector(a["residual"]), vector(b["residual"])
            if hp.shape != h.shape:
                raise ValueError("Residual shape mismatch")
            delta = hp-h
            phase = "last_prompt" if a["position"] == first_position else "generated"
            terminal = (phase == "generated" and
                        a["position"] == first_position+source_turn["output_tokens"])
            for transport, read in a["readout"].items():
                other = b["readout"][transport]
                normalized = vector(other["token_logits"])-vector(read["token_logits"])
                # U T has no learned RMSNorm gain; this is not denominator isolation.
                linear = vector(other["linear_token_logits"])-vector(read["linear_token_logits"])
                expected = None
                # Only the intervention layer admits this direct-injection
                # calculation. A decoder vector at layer50 is not a measured
                # propagated vector at layers65/78.
                if a["layer"] == 50:
                    expected = spec["coefficient"] * np.sum([
                        vector(static[str(f)]["50"][transport]["linear_token_logits"])
                        for f in spec["feature_ids"]], axis=0)
                for group, indices in groups.items():
                    if not indices or min(indices) < 0 or max(indices) >= len(linear):
                        raise ValueError("Invalid lexicon indices")
                    yield {"source_id": capture["source_id"], "family": spec["family"],
                           "seed": spec["seed"], "coefficient": spec["coefficient"],
                           "history": pair["source"], "turn": pair["turn"],
                           "layer": a["layer"], "position": a["position"],
                           "relative_position": a["position"]-first_position,
                           "phase": phase, "transport": transport, "group": group,
                           "originating_row_id": source["id"],
                           "source_output_tokens": source_turn["output_tokens"],
                           "terminal_observation_only": terminal,
                           "normalized_logit_delta": float(normalized[indices].mean()),
                           "linear_logit_delta": float(linear[indices].mean()),
                           "static_linear_prediction": None if expected is None else float(expected[indices].mean()),
                           "all_lexicon_static_cosine": None if expected is None else cosine(linear, expected),
                           "residual_delta_norm": float(np.linalg.norm(delta)),
                           "clean_residual_norm": float(np.linalg.norm(h)),
                           "clean_transport_norm": read["transport_norm"],
                           "edited_transport_norm": other["transport_norm"]}


def case_means(rows):
    """Average decision-bearing positions; terminal-only cases have no mean."""
    keys = ("source_id", "family", "seed", "coefficient", "history", "turn",
            "layer", "phase", "transport", "group")
    measures = ("normalized_logit_delta", "linear_logit_delta", "static_linear_prediction",
                "all_lexicon_static_cosine", "residual_delta_norm", "clean_residual_norm",
                "clean_transport_norm", "edited_transport_norm")
    grouped = {}
    for row in rows:
        if row["terminal_observation_only"]:
            continue
        grouped.setdefault(tuple(row[k] for k in keys), []).append(row)
    for key, group in sorted(grouped.items()):
        result = dict(zip(keys, key), positions=len(group))
        for field in measures:
            values = [r[field] for r in group]
            if all(v is None for v in values):
                result[field] = None
            elif any(v is None for v in values):
                # Cosines can be undefined at zero vectors. Do not silently
                # select nonzero cases when taking the mean.
                result[field] = None
            else:
                result[field] = float(vector(values).mean())
        yield result


def zero_consistency(records):
    """Repeated zero-feature labels must not create extra sample size."""
    groups = {}
    for row in records:
        spec = row["spec"]
        if spec["coefficient"] != 0:
            continue
        key = tuple(spec[k] for k in ("prompt", "temperature", "cap", "seed"))
        signature = tuple(tuple(t["output_token_ids"]) for t in row["turns"])
        groups.setdefault(key, []).append((row["id"], signature))
    return [{"prompt": key[0], "temperature": key[1], "cap": key[2], "seed": key[3],
             "rows": len(values), "distinct_two_turn_outputs": len({v[1] for v in values}),
             "ids": ";".join(v[0] for v in values)} for key, values in sorted(groups.items())]


def summarize(root, out, plan=None):
    root, out = Path(root), Path(out)
    out.mkdir(parents=True, exist_ok=False)
    metadata_path = root/"lens-metadata.json"
    groups = json.loads(metadata_path.read_text())["groups"] if metadata_path.exists() else {}
    static_path = root/"static-directions.json"
    static = json.loads(static_path.read_text()) if static_path.exists() else {}
    rows, captures = {}, []
    quality = {"empty_turns": 0, "capped_turns": 0, "generated_tokens": 0,
               "generation_seconds": 0., "judge_missing": {"notebook": 0, "paper": 0}}
    for path in sorted((root/"rows").glob("*.json")):
        row = json.loads(path.read_text())
        if path.stem.startswith("capture-") or row["id"].startswith("capture-"):
            if path.stem != row["id"]:
                raise ValueError("Capture filename/ID mismatch")
            captures.append(path)
        elif "spec" in row:
            if row["id"] in rows:
                raise ValueError("Duplicate behavioral row")
            rows[row["id"]] = {"path": path, "spec": row["spec"]}
            for turn in row["turns"]:
                quality["empty_turns"] += not turn["response"].strip()
                quality["capped_turns"] += turn["cap_hit"]
                quality["generated_tokens"] += turn["output_tokens"]
                quality["generation_seconds"] += turn["elapsed_seconds"]
            for judge in quality["judge_missing"]:
                quality["judge_missing"][judge] += row["judges"][judge]["label"] is None
    schedule = None
    if captures or plan is not None:
        if plan is None:
            plan = json.loads(DEFAULT_PLAN.read_text())
        expected = {"capture-"+r["id"] for r in plan["rows"] if r["capture"]}
        present = {p.stem for p in captures}
        schedule = (validate_capture_schedule(root, plan) if present == expected else
                    _validate_capture_schedule(root, plan, complete=False))
    table(out/"delivery.csv", (d for r in rows.values()
                              for d in delivery_rows(json.loads(r["path"].read_text()))))
    table(out/"activation_changes.csv", (d for r in rows.values()
                                        for d in activation_rows(json.loads(r["path"].read_text()))))
    zero = zero_consistency(json.loads(r["path"].read_text()) for r in rows.values())
    table(out/"zero_consistency.csv", zero)
    paired = []
    for path in captures:
        capture = json.loads(path.read_text())
        spec = rows[capture["source_id"]]["spec"]
        paired.extend(paired_rows(capture, spec, groups, static,
                                  _capture_sources(root, spec, plan), plan["lens"]["layers"]))
    table(out/"paired_positions.csv", paired)
    table(out/"paired_cases.csv", case_means(paired))
    report = {"behavioral_rows": len(rows), "capture_cases": len(captures),
              "capture_schedule": schedule,
              "quality": quality,
              "analysis_status": "descriptive_secondary_not_a_confirmatory_mechanism_test",
              "position_rows": len(paired), "token_level_inference": False,
              "statistical_intervals": None,
              "repeated_zero_groups": sum(r["rows"] > 1 for r in zero),
              "repeated_zero_mismatches": sum(r["distinct_two_turn_outputs"] > 1 for r in zero),
              "scope": "fixed selected cases; two capture seeds; no behavioral mediation claim"}
    (out/"diagnostics.json").write_text(json.dumps(report, indent=2, allow_nan=False)+"\n")
    return report


def figures(out):
    """All seven transports, fixed last-prompt/turn2 view; no outcome selection."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    out = Path(out)
    path = out/"paired_cases.csv"
    if not path.exists():
        return []
    with path.open() as f:
        rows = list(csv.DictReader(f))
    rows = [r for r in rows if r["turn"] == "2" and r["phase"] == "last_prompt"
            and r["family"].startswith("aggregate-")]
    if not rows:
        return []
    transports = ["identity", "jacobian"] + [f"random_j_{i}" for i in range(1, 6)]
    groups = sorted({r["group"] for r in rows})
    layers = [50, 65, 78]
    panels = {}
    for history in ("zero", "steered"):
        for coefficient in (-.5, .5):
            matrix = np.full((len(groups)*3, len(transports)), np.nan)
            for i, (layer, group) in enumerate((l, g) for l in layers for g in groups):
                for j, transport in enumerate(transports):
                    subset = [r for r in rows if r["history"] == history
                              and float(r["coefficient"]) == coefficient
                              and int(r["layer"]) == layer and r["group"] == group
                              and r["transport"] == transport]
                    families = ("aggregate-target", "aggregate-control-1",
                                "aggregate-control-2", "aggregate-control-3")
                    by_family = {}
                    for family in families:
                        matches = [r for r in subset if r["family"] == family]
                        seeds = [int(r["seed"]) for r in matches]
                        if sorted(seeds) != [101, 202]:
                            break
                        by_family[family] = float(np.mean([float(r["normalized_logit_delta"]) for r in matches]))
                    if len(by_family) == 4:
                        matrix[i, j] = by_family[families[0]] - float(np.mean([
                            by_family[f] for f in families[1:]]))
            panels[history, coefficient] = matrix
    finite = np.concatenate([m[np.isfinite(m)] for m in panels.values()])
    if not len(finite):
        return []
    limit = max(float(np.abs(finite).max()), 1e-9)
    outputs = []
    for (history, coefficient), matrix in panels.items():
        fig, ax = plt.subplots(figsize=(10, 10))
        cm = plt.get_cmap("RdBu_r").copy(); cm.set_bad("#d5d5d5")
        im = ax.imshow(matrix, cmap=cm, vmin=-limit, vmax=limit, aspect="auto")
        ax.set(xticks=range(7), xticklabels=["Identity", "J-lens"]+[f"Random J {i}" for i in range(1,6)],
               yticks=range(len(groups)*3),
               yticklabels=[f"L{l} {g}" for l in layers for g in groups])
        ax.tick_params(axis="both", labelsize=9)
        for y in (len(groups)-.5, 2*len(groups)-.5):
            ax.axhline(y, color="black", linewidth=.7)
        ax.set_title(f"Target minus matched-control mean: coefficient {coefficient:+.1f}\n"
                     f"{history.title()} source history; turn 2, final prompt position", fontsize=12)
        fig.colorbar(im, ax=ax, label="Difference in paired normalized-logit changes")
        fig.text(.5, .01, "Two fixed seeds; descriptive means, not a mediation test. Gray = incomplete cell.",
                 ha="center", fontsize=9)
        fig.tight_layout(rect=(0,.025,1,1))
        name = f"paired_jlens_{history}_{'negative' if coefficient < 0 else 'positive'}"
        for ext in ("png", "pdf"):
            dest = out/(name+"."+ext)
            if dest.exists():
                raise FileExistsError(dest)
            fig.savefig(dest, dpi=160)
            outputs.append(str(dest))
        plt.close(fig)
    return outputs


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--figures", action="store_true")
    parser.add_argument("--plan", type=Path, help="Frozen plan; defaults to the source-aligned plan")
    args = parser.parse_args()
    plan = json.loads(args.plan.read_text()) if args.plan else None
    print(json.dumps(summarize(args.root, args.out, plan)))
    if args.figures:
        print(json.dumps({"figures": figures(args.out)}))

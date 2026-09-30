"""Bounded, post-outcome saved-row failure census (2026-09-30).

    python -m experiments.sae_assay_repair.failure_census --run RUN --out NEW.json

Added after repair outcomes were known to locate exposure, fidelity and norm
failures. The display bins and stratifications are post-outcome choices, not new
qualification rules. Frozen thresholds, rows, q90, selection and results remain
unchanged. Only saved JSON is read; no residual tensors, models, GPU or APIs.
The existing receipt reader is reused, never its geometry/full-audit entry point.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path

from experiments.sae_assay_diagnostic import analysis
from experiments.sae_assay_repair import geometry_audit


OPERATORS = ("literal", "decoder_span", "encoder_min_norm")
CORPORA = ("stage1_authored", "previously_published_paraphrases")
SPLITS = ("calibration", "validation")
RATIO_EDGES = (.005, .01, .02, .04, .05)
RATIO_BINS = ("zero", "(0,0.005]", "(0.005,0.01]", "(0.01,0.02]",
              "(0.02,0.04]", "(0.04,0.05]", "(0.05,infinity)", "undefined_zero_clean")
LIMITATIONS = [
    "Post-outcome descriptive census of saved fixed texts; cannot replace frozen endpoints or qualify a recipe.",
    "Tokens, features, arms and lexical variants are dependent; counts/fractions and medians have no independence claim or confidence intervals.",
    "Special-token, active-count and norm-bin associations do not identify causes, including BF16 rounding. Nonzero requests with zero realized norm are described, not causally attributed.",
    "Clean active count means positive native activations among this target panel, not full-dictionary SAE L0.",
    "Fidelity and norm retain all positions, including specials; coordinate exposure/efficacy use only valid nonspecial positions.",
    "Absent edit cells are not recorded, not zero effects; observed coverage is relative to available clean rows, not a frozen-plan completeness claim.",
    "Worker receipt consistency is not external authentication. No full release/source-plan, residual-capture, lifecycle, or geometry audit runs here.",
    "Native and selected readouts are saved diagnostics, not recomputed encodings; alternate efficacy uses recorded canonical requests, not newly executed alternate edits.",
    "Authored and previously published paraphrase corpora are not independent natural-corpus validation. No consciousness, deception-removal or proprietary-equivalence claim follows.",
]


def _require(ok, message):
    if not ok:
        raise ValueError(message)


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("ascii")


def _hash(value):
    return hashlib.sha256(_canonical(value)).hexdigest()


def _fraction(numerator, denominator):
    return {"numerator": numerator, "denominator": denominator,
            "fraction": numerator / denominator if denominator else None}


def _ratio_bin(requested, clean):
    if clean == 0:
        return RATIO_BINS[-1]
    if requested == 0:
        return RATIO_BINS[0]
    ratio = requested / clean
    analysis._number(ratio, "requested/clean norm ratio")
    for i, edge in enumerate(RATIO_EDGES, 1):
        if ratio <= edge:
            return RATIO_BINS[i]
    return RATIO_BINS[-2]


class _Failures:
    def __init__(self):
        self.counts = Counter()

    def add(self, delivery, i):
        d, c = delivery, self.counts
        c["positions"] += 1
        c["invalid"] += not d.get("valid", [True] * len(d["clean_norm"]))[i]
        requested = d["nonzero_requested"][i]
        realized = d["realized_norm"][i] > 0
        cosine = requested and d["cosine"][i] < .95
        error = requested and d["relative_error"][i] > .20
        norm = realized and d["realized_norm"][i] > .05 * d["clean_norm"][i]
        c["requests"] += requested
        c["edits"] += realized
        c["cosine"] += cosine
        c["relative_error"] += error
        c["both_fidelity_components"] += cosine and error
        c["fidelity"] += cosine or error
        c["norm"] += norm
        c["zero_realized_requests"] += requested and not realized
        c["realized_zero_clean"] += realized and d["clean_norm"][i] == 0
        c["joint_eligible"] += requested and realized
        c["joint_failed"] += (cosine or error) and norm

    def report(self):
        c = self.counts
        return {"positions": c["positions"], "invalid_positions": c["invalid"],
                "fidelity_failed": _fraction(c["fidelity"], c["requests"]),
                "cosine_failed": c["cosine"], "relative_error_failed": c["relative_error"],
                "both_fidelity_components_failed": c["both_fidelity_components"],
                "zero_request_excluded_fidelity": c["positions"] - c["requests"],
                "nonzero_request_zero_realized": c["zero_realized_requests"],
                "norm_failed": _fraction(c["norm"], c["edits"]),
                "zero_realized_excluded_norm": c["positions"] - c["edits"],
                "realized_with_zero_clean_norm": c["realized_zero_clean"],
                "joint_failed": _fraction(c["joint_failed"], c["joint_eligible"])}


def _validate(row, ids):
    check = analysis.validate_teacher_rows([row])
    _require(check["pass"], "Invalid teacher row: " + "; ".join(check["errors"]))
    t = row["result"]["telemetry"]
    _require(row.get("corpus") in CORPORA, "Unknown/missing corpus")
    _require(row["group"] in OPERATORS, "Unknown operator")
    _require(t["feature_ids"] == ids, "Ordered feature IDs differ between rows")
    _require(geometry_audit._identifier(row.get("text_id")), "Invalid text_id")
    if row["mode"] == "zero":
        expected = "clean-" + row["text_id"]
        _require(row["group"] == "literal" and not any(t["delivery"]["requested_norm"]),
                 "Shared clean row must be literal with zero requested norm")
    else:
        expected = f"edit-{row['group']}-{row['text_id']}-{row['mode']}-{int(row['strength']*100):03d}"
    _require(row["id"] == expected, "Row ID/arm metadata mismatch")
    _require(t.get("repair_operator", row["group"]) == row["group"], "Row/telemetry operator mismatch")
    full = t.get("full_sae")
    _require(full is None or type(full) is dict, "Malformed full_sae")
    full = full or {}
    for when in ("before", "after"):
        if "full_selected_" + when in full:
            _require(full["full_selected_" + when] == t["selected_activations"][when],
                     "Canonical/native activation mismatch")
    _require(("selected_path_before" in full) == ("selected_path_after" in full),
             "Incomplete selected-path diagnostics")
    if row["mode"] == "zero" and "selected_path_before" in full:
        _require(full["selected_path_before"] == full["selected_path_after"], "Clean selected-path mismatch")
    return t


def _binding(row):
    r, t = row["result"], row["result"]["telemetry"]
    full = t.get("full_sae") or {}
    return _hash([row["corpus"], row["split"], row["category"], r["token_ids"],
                  t["position_metadata"], t["delivery"].get("valid", [True] * len(r["token_ids"])),
                  t["selected_activations"]["before"], t["delivery"]["clean_norm"],
                  r["unsteered_nll"], full.get("selected_path_before"),
                  full.get("fp32_preact_before")])


def _exposure(rows, ids):
    cells = []
    for split in SPLITS:
        for corpus in ("all_corpora",) + CORPORA:
            panel = [r for r in rows if r["split"] == split and
                     (corpus == "all_corpora" or r["corpus"] == corpus)]
            for j, feature in enumerate(ids):
                scopes = {}
                for scope in ("special", "nonspecial_valid"):
                    positions = active = texts = exposed = 0
                    for row in panel:
                        t = row["result"]["telemetry"]
                        indices = [i for i, p in enumerate(t["position_metadata"]) if
                                   (p["token_class"] == "special" if scope == "special" else analysis._eligible(t, i))]
                        count = sum(t["selected_activations"]["before"][i][j] > 0 for i in indices)
                        positions += len(indices)
                        active += count
                        texts += bool(indices)
                        exposed += count > 0
                    scopes[scope] = {"active_positions": _fraction(active, positions),
                                     "exposed_texts": _fraction(exposed, texts)}
                cells.append({"split": split, "corpus": corpus, "feature_id": feature,
                              "clean_texts": len(panel), "scopes": scopes})
    return cells


def _coordinate_summary(rows, ids):
    features = []
    for j, feature in enumerate(ids):
        paths = {}
        for name in ("native", "selected"):
            ratios, exposed, observed = [], 0, 0
            for row in rows:
                t = row["result"]["telemetry"]
                a = t["selected_activations"]
                full = t.get("full_sae") or {}
                if name == "selected" and "selected_path_before" not in full:
                    continue
                observed += 1
                before, after = ((a["before"], a["after"]) if name == "native" else
                                 (full["selected_path_before"], full["selected_path_after"]))
                text_ratios = []
                for i in range(len(before)):
                    if not analysis._eligible(t, i):
                        continue
                    b, end, delta = before[i][j], after[i][j], a["requested_delta"][i][j]
                    if row["mode"] == "suppression" and b > 0:
                        text_ratios.append(end / b)
                    elif row["mode"] == "amplification" and delta > 0:
                        text_ratios.append((end - b) / delta)
                for value in text_ratios:
                    analysis._number(value, "coordinate ratio")
                ratios.extend(text_ratios)
                exposed += bool(text_ratios)
            center = analysis._quantile(ratios, .5)
            paths[name] = {"observed_rows": observed, "missing_rows": len(rows) - observed,
                           "eligible_positions": len(ratios), "eligible_texts": exposed, "median": center,
                           "frozen_exposure_component": len(ratios) >= 100 and exposed >= 6 if observed else None,
                           "frozen_efficacy_component": (center <= .5 if rows[0]["mode"] == "suppression" else center >= .5)
                           if center is not None else None}
        complete = bool(rows) and all(p["missing_rows"] == 0 for p in paths.values())
        features.append({"feature_id": feature, **paths,
                         "exposure_component_disagrees": paths["native"]["frozen_exposure_component"] !=
                         paths["selected"]["frozen_exposure_component"] if complete else None,
                         "efficacy_component_disagrees": paths["native"]["frozen_efficacy_component"] !=
                         paths["selected"]["frozen_efficacy_component"] if complete else None})
    return features


def _encoder_disagreement(rows):
    groups = defaultdict(Counter)
    observed = 0
    for row in rows:
        t = row["result"]["telemetry"]
        full = t.get("full_sae") or {}
        if "selected_path_before" not in full:
            continue
        observed += 1
        for i, p in enumerate(t["position_metadata"]):
            scope = "special" if p["token_class"] == "special" else "nonspecial"
            for when in ("before", "after"):
                c = groups[(scope, when)]
                for native, selected in zip(t["selected_activations"][when][i], full["selected_path_" + when][i]):
                    c["coordinates"] += 1
                    c["activity"] += (native > 0) != (selected > 0)
                    c["value"] += native != selected
                    c["max_absolute_difference"] = max(c["max_absolute_difference"], abs(native-selected))
    return {"observed_rows": observed, "missing_rows": len(rows)-observed,
            "comparisons": [{"token_class": scope, "phase": when,
                "activity_mismatch": _fraction(groups[(scope, when)]["activity"], groups[(scope, when)]["coordinates"]),
                "value_mismatch": _fraction(groups[(scope, when)]["value"], groups[(scope, when)]["coordinates"]),
                "max_absolute_difference": groups[(scope, when)]["max_absolute_difference"]
                if groups[(scope, when)]["coordinates"] else None}
                for scope in ("special", "nonspecial") for when in ("before", "after")]}


def _arm(rows, clean, ids):
    total, classes = _Failures(), {}
    for scope in ("special", "nonspecial"):
        classes[scope] = (_Failures(), [_Failures() for _ in range(len(ids)+1)],
                          {key: _Failures() for key in RATIO_BINS})
    for row in rows:
        t = row["result"]["telemetry"]
        d, before = t["delivery"], t["selected_activations"]["before"]
        for i, p in enumerate(t["position_metadata"]):
            scope = "special" if p["token_class"] == "special" else "nonspecial"
            summary, active, bins = classes[scope]
            for cell in (total, summary, active[sum(v > 0 for v in before[i])],
                         bins[_ratio_bin(d["requested_norm"][i], d["clean_norm"][i])]):
                cell.add(d, i)
    return {"status": "observed" if rows else "not_recorded", "row_count": len(rows),
            "paired_clean_text_coverage": _fraction(len(rows), len(clean)),
            "coverage_by_corpus": {corpus: _fraction(sum(r["corpus"] == corpus for r in rows),
                                                      sum(r["corpus"] == corpus for r in clean)) for corpus in CORPORA},
            "all_positions": total.report(),
            "by_token_class": {scope: {"all": summary.report(),
                "by_clean_active_count": [{"active_count": i, **cell.report()} for i, cell in enumerate(active)],
                "by_requested_clean_norm_bin": [{"bin": key, **cell.report()} for key, cell in bins.items()]}
                for scope, (summary, active, bins) in classes.items()},
            "coordinate_efficacy": _coordinate_summary(rows, ids),
            "native_vs_selected": _encoder_disagreement(rows)}


def report(run):
    """Return deterministic JSON-ready aggregates; inputs are never written.

    Structural corruption raises ValueError (missing JSON fields may raise
    KeyError/TypeError). Scientific failures are counted, not raised. The hash
    index digest binds every read file; individual row digests remain in the
    hashed receipt ledger rather than duplicating thousands of paths here.
    """
    inputs = geometry_audit._Inputs(Path(run).resolve(strict=True))
    rows, provenance = geometry_audit._read_rows(inputs)
    teachers = [row for rid, row in sorted(rows.items()) if rid.startswith(("clean-", "edit-"))]
    _require(bool(teachers), "No teacher rows available")
    ids = teachers[0]["result"]["telemetry"]["feature_ids"]
    clean, edits, bindings, seen = {}, [], {}, set()
    q90 = None
    for row in teachers:
        t = _validate(row, ids)
        key = (row["text_id"], row["group"], row["mode"], row["strength"])
        _require(key not in seen, "Duplicate text/arm")
        seen.add(key)
        binding = _binding(row)
        text = row["text_id"]
        _require(text not in bindings or bindings[text] == binding,
                 "Paired clean/token/corpus/split/diagnostic mismatch: " + text)
        bindings[text] = binding
        if row["mode"] == "zero":
            _require(text not in clean, "Duplicate clean text")
            clean[text] = row
        else:
            edits.append(row)
        if row["mode"] == "amplification" and t.get("q90") is not None:
            _require(q90 is None or q90 == t["q90"], "Amplification q90 differs across rows")
            q90 = t["q90"]
    _require(bool(clean), "No clean rows available")
    _require(all(r["text_id"] in clean for r in edits), "Missing paired clean row")
    clean_rows = list(clean.values())
    arms = []
    for op in OPERATORS:
        for mode in analysis.DIRECTIONS:
            for strength in analysis.STRENGTHS:
                arms.append({"operator": op, "direction": mode, "strength": strength,
                             "splits": {split: _arm([r for r in edits if (r["group"], r["mode"], r["strength"], r["split"])
                                         == (op, mode, strength, split)],
                                         [r for r in clean_rows if r["split"] == split], ids) for split in SPLITS}})
    # Re-read only consumed JSON bytes; never run a release/geometry auditor.
    inputs.verify_unchanged()
    _require({p.name for p in (inputs.run / "rows").iterdir()} == {rid + ".json" for rid in rows},
             "Rows changed during census")
    return {"schema": "sae_assay_repair_failure_census_v1", "post_outcome": True,
            "amendment_date": "2026-09-30", "frozen_results_changed": False,
            "provenance": provenance,
            "input_hashes": {"receipts.jsonl": inputs.hashes["receipts.jsonl"],
                "file_count": len(inputs.hashes), "path_sha256_index_sha256": _hash(inputs.hashes),
                "index_encoding": "SHA256 of ASCII JSON {relative_path: sha256}, sorted keys, compact separators, no newline",
                "raw_bytes_unchanged": True},
            "source_sha256": {Path(module.__file__).name: hashlib.sha256(Path(module.__file__).read_bytes()).hexdigest()
                              for module in (analysis, geometry_audit)} | {Path(__file__).name: hashlib.sha256(Path(__file__).read_bytes()).hexdigest()},
            "counts": {"raw_rows": len(rows), "clean_rows": len(clean), "edited_rows": len(edits),
                       "other_rows_hash_checked_only": len(rows)-len(teachers)},
            "feature_ids": ids, "definitions": {
                "fidelity_failure": "cosine < 0.95 OR relative_error > 0.20; denominator nonzero_requested only",
                "norm_failure": "realized_norm > 0.05 * clean_norm; denominator realized_norm > 0, including zero-clean failures",
                "nonzero_request_zero_realized": "Frozen rounded-away count: nonzero_requested and realized_norm == 0; the label does not establish a rounding cause",
                "strata": "Special versus nonspecial retains invalid positions (counted explicitly); clean active count is native target-panel activity > 0",
                "norm_bins": "requested_norm / clean_norm, not realized_norm; fixed post-outcome display bins, right-closed finite endpoints",
                "coordinate_ratio": "Valid nonspecial positions: suppression after/before where before>0; amplification (after-before)/canonical_requested_delta where delta>0",
                "component_flags": "Frozen per-feature exposure >=100 positions and >=6 texts; median efficacy <=0.5 suppression or >=0.5 amplification. Descriptive components, not recipe qualification",
                "pooled_exposure": "all_corpora repeats the two named corpus cells as a pooled display, not extra observations"},
            "clean_exposure": _exposure(clean_rows, ids), "edited_arms": arms,
            "limitations": LIMITATIONS}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        run, destination = args.run.resolve(strict=True), args.out.resolve()
        _require(not destination.is_relative_to(run), "Output must be outside the immutable input run")
        _require(not args.out.exists() and not args.out.is_symlink(), "Output must be a fresh JSON file")
        result = report(run)
        with args.out.open("xb") as handle:
            handle.write(_canonical(result) + b"\n")
    except (OSError, ValueError, KeyError, TypeError, OverflowError) as exc:
        print(json.dumps({"error": str(exc), "error_type": type(exc).__name__}))
        return 2
    print(json.dumps({"schema": result["schema"], "counts": result["counts"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

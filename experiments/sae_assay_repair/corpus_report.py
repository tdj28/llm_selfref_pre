"""Display-only, postcollection corpus census from repair raw rows.

Run with ``python -m experiments.sae_assay_repair.corpus_report --rows RUN/rows
--out NEW_DIRECTORY`` on a stable retrieved snapshot. Inputs are read-only;
the output must be fresh and outside the input release. No plan, selection,
gate report, model, or provider is loaded. Missing branches remain missing.
"""

from __future__ import annotations

import argparse
from array import array
from collections import Counter, defaultdict
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path

from experiments.sae_assay_diagnostic import analysis


SCHEMA = "sae_assay_repair_corpus_report_v1"
CORPORA = ("stage1_authored", "previously_published_paraphrases")
OPERATORS = ("literal", "decoder_span", "encoder_min_norm")
SPLITS = ("calibration", "validation")
ROOT = Path(__file__).resolve().parents[2]
LIMITS = [
    "Postcollection descriptive fixed-text census, not corpus-subset requalification.",
    "No thresholds, frozen pooled calibration q90, recipe, or selection are changed.",
    "Recorded amplification q90 is displayed, never recomputed on either corpus or validation.",
    "Tokens and lexical variants are not independent natural observations; no confidence intervals are computed.",
    "Previously published paraphrases had public semantic-map outcomes; they are not independent semantic validation or natural documents.",
    "Absent raw rows cannot distinguish conditional non-dispatch, unavailable operators, incomplete collection, or incomplete retrieval. Missing effects are not zero.",
    "This is not a receipt, capture-hash, frozen-plan completeness, or original q90 provenance audit.",
    "Coordinate delivery does not establish removal of deception, mediation, consciousness, or proprietary-service equivalence.",
    "All-position diagnostics within each recipe reuse the same fixed texts; shared clean forwards are displayed once, not replicated across operators.",
]
SCOPES = {
    "features": "Nonspecial valid positions; canonical native full-width before/after activations.",
    "paired_ratio": "Suppression: after/before where before>0. Amplification: (after-before)/requested_delta where requested_delta>0. Paired within each raw forward, never a ratio of aggregate means.",
    "residual": "All persisted positions, including specials, as in the frozen residual gates. Fidelity uses nonzero requests; norm ratios use realized edits and nonzero clean norms. No thresholds are evaluated.",
    "non_target": "Full-dictionary re-encoded coordinate movement outside the target panel, separately for all positions and nonspecial valid positions. Counts are changed coordinates per position, not unique features across texts.",
    "clean_reconstruction": "Full SAE reconstruction of the clean hidden state, not reconstruction of the edited state. Norm/error/L0 include specials; loss excludes special/invalid target positions and index 0.",
    "neutral_paired_nll": "Category neutral only; edited minus unsteered NLL on identical token IDs, excluding special/invalid target positions and index 0. Both token-weighted and equal-text means are descriptive.",
    "p90": "Linear descriptive distribution percentile, not the positive-only pooled calibration q90 used by the intervention.",
    "no_op": "Original qualification booleans are copied without rerunning qualification. Clean-row identity flags and within-row activation/loss equality are descriptive, not new bitwise full-model evidence.",
}


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _digest(value):
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _file_hash(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _public_path(path):
    try:
        return Path(path).resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return Path(path).name


def _stats(values):
    # These frozen helpers only sort/reduce numbers; no gate helpers are called.
    result = analysis._distribution(values)
    result["p90"] = result.pop("q90")
    result["mean"] = math.fsum(v / len(values) for v in values) if values else None
    return result


class _Series:
    def __init__(self):
        self.values = array("d")
        self.observed_rows = 0
        self.missing_row_ids = []

    def add(self, row_id, values):
        if values is None:
            self.missing_row_ids.append(row_id)
        else:
            self.observed_rows += 1
            for value in values:
                analysis._number(value, "derived descriptive metric")
                self.values.append(value)

    def report(self):
        status = ("not_recorded" if not self.observed_rows else
                  "partially_recorded" if self.missing_row_ids else
                  "observed" if self.values else "no_applicable_positions")
        return {"status": status, "observed_rows": self.observed_rows,
                "missing_row_ids": sorted(self.missing_row_ids),
                "distribution": _stats(self.values) if self.observed_rows else None}


def _optional_vectors(row):
    t = row["result"]["telemetry"]
    n = len(row["result"]["token_ids"])
    full = t.get("full_sae")
    _require(full is None or type(full) is dict, "full_sae: expected object/null")
    full = full or {}
    for key in ("non_target_change_norm", "non_target_changed_count", "l0_before",
                "reconstruction_error_norm", "reconstruction_relative_error"):
        if full.get(key) is not None:
            analysis._vector(full[key], n, key, minimum=0)
            if key in ("non_target_changed_count", "l0_before"):
                _require(all(type(v) is int for v in full[key]), key + ": expected integer counts")
    for phase in ("before", "after"):
        if "full_selected_" + phase in full:
            _require(full["full_selected_" + phase] == t["selected_activations"][phase],
                     "Canonical/full diagnostic activation mismatch")
    if row["result"].get("reconstruction_nll") is not None:
        analysis._vector(row["result"]["reconstruction_nll"], n, "reconstruction_nll",
                         first_null=True, minimum=0)
    if "repair_operator" in t:
        _require(t["repair_operator"] == row["group"], "Row/telemetry operator mismatch")
    return full


class _Cell:
    def __init__(self, feature_ids):
        self.rows = []
        self.counts = Counter()
        self.metrics = defaultdict(_Series)
        self.features = [{"feature_id": feature, "before": array("d"),
                          "after": array("d"), "requested_delta": array("d"),
                          "ratios": array("d"), "by_text": []} for feature in feature_ids]
        self.neutral_texts = []
        self.noops = []

    def add(self, row, full):
        result, row_id = row["result"], row["id"]
        t = result["telemetry"]
        a, d = t["selected_activations"], t["delivery"]
        n = len(result["token_ids"])
        positions = list(range(n))
        eligible = [i for i in positions if analysis._eligible(t, i)]
        loss_positions = [i for i in eligible if i > 0]
        requests = [i for i in positions if d["nonzero_requested"][i]]
        edits = [i for i in positions if d["realized_norm"][i] > 0]
        norm_positions = [i for i in edits if d["clean_norm"][i] > 0]
        self.rows.append({"row_id": row_id, "text_id": row["text_id"],
                          "category": row["category"], "source_group": row["group"]})
        self.counts.update({
            "all_positions_including_special": n, "nonspecial_valid_positions": len(eligible),
            "excluded_coordinate_positions": n - len(eligible),
            "special_positions": sum(p["token_class"] == "special" for p in t["position_metadata"]),
            "invalid_positions": sum(not v for v in d.get("valid", [True] * n)),
            "nonzero_requested_positions": len(requests), "zero_requested_positions": n - len(requests),
            "rounded_away_positions": sum(d["realized_norm"][i] == 0 for i in requests),
            "actual_edit_positions": len(edits),
            "undefined_norm_ratio_zero_clean_positions": len(edits) - len(norm_positions),
        })
        for j, feature in enumerate(self.features):
            before = [a["before"][i][j] for i in eligible]
            after = [a["after"][i][j] for i in eligible]
            delta = [a["requested_delta"][i][j] for i in eligible]
            ratios = []
            for b, end, request in zip(before, after, delta):
                if row["mode"] == "suppression" and b > 0:
                    ratios.append(end / b)
                elif row["mode"] == "amplification" and request > 0:
                    ratios.append((end - b) / request)
            for value in ratios:
                analysis._number(value, "paired coordinate ratio")
            for name, values in (("before", before), ("after", after),
                                 ("requested_delta", delta), ("ratios", ratios)):
                feature[name].extend(values)
            feature["by_text"].append({"text_id": row["text_id"], "row_id": row_id,
                "nonspecial_valid_positions": len(eligible),
                "positive_before_positions": sum(v > 0 for v in before),
                "positive_after_positions": sum(v > 0 for v in after),
                "paired_ratio_positions": len(ratios),
                "paired_ratio": _stats(ratios) if row["mode"] != "zero" else None})

        def metric(name, values):
            self.metrics[name].add(row_id, values)

        for key in ("requested_norm", "realized_norm", "clean_norm"):
            metric("residual_" + key + "_all_positions", d[key])
        for key in ("cosine", "relative_error"):
            metric("residual_" + key + "_nonzero_requested", [d[key][i] for i in requests])
        metric("residual_realized_over_clean_norm_actual_edits",
               [d["realized_norm"][i] / d["clean_norm"][i] for i in norm_positions])
        for key in ("non_target_change_norm", "non_target_changed_count"):
            for suffix, indices in (("all_positions", positions), ("nonspecial_valid", eligible)):
                values = full.get(key)
                metric(key + "_" + suffix, None if values is None else [values[i] for i in indices])
        for key in ("reconstruction_error_norm", "reconstruction_relative_error", "l0_before"):
            metric("clean_" + key + "_all_positions", full.get(key))
        recon = result.get("reconstruction_nll")
        metric("clean_reconstruction_nll_nonspecial_valid",
               None if recon is None else [recon[i] for i in loss_positions])
        metric("clean_reconstruction_minus_unsteered_nll_nonspecial_valid", None if recon is None else
               [recon[i] - result["unsteered_nll"][i] for i in loss_positions])
        if row["category"] == "neutral":
            delta = [result["edited_nll"][i] - result["unsteered_nll"][i] for i in loss_positions]
            for name in ("unsteered_nll", "edited_nll"):
                metric("neutral_" + name, [result[name][i] for i in loss_positions])
            metric("neutral_paired_nll_delta", delta)
            self.neutral_texts.append({"text_id": row["text_id"], "row_id": row_id,
                                       "paired_delta": _stats(delta)})
        if row["mode"] == "zero":
            identity = d.get("identity")
            self.noops.append({"row_id": row_id, "text_id": row["text_id"],
                "original_identity_flags": {"status": "recorded" if identity is not None else "not_recorded",
                    "true_positions": sum(identity) if identity is not None else None,
                    "false_positions": sum(not v for v in identity) if identity is not None else None},
                "before_after_exactly_equal": a["before"] == a["after"],
                "unsteered_edited_nll_exactly_equal": result["unsteered_nll"] == result["edited_nll"]})

    def report(self, mode):
        features = []
        for feature in self.features:
            contributions = sorted(feature["by_text"], key=lambda r: r["text_id"])
            features.append({"feature_id": feature["feature_id"],
                **{key: _stats(feature[key]) for key in ("before", "after", "requested_delta")},
                "text_count": len(contributions),
                "positive_before_positions": sum(r["positive_before_positions"] for r in contributions),
                "positive_before_texts": sum(r["positive_before_positions"] > 0 for r in contributions),
                "paired_ratio_positions": len(feature["ratios"]) if mode != "zero" else None,
                "paired_ratio_texts": sum(r["paired_ratio_positions"] > 0 for r in contributions) if mode != "zero" else None,
                "paired_ratio": _stats(feature["ratios"]) if mode != "zero" else None,
                "by_text": contributions})
        text_means = [r["paired_delta"]["mean"] for r in self.neutral_texts
                      if r["paired_delta"]["mean"] is not None]
        return {"position_counts": dict(sorted(self.counts.items())), "features": features,
                "metrics": {name: series.report() for name, series in sorted(self.metrics.items())},
                "neutral_paired_nll": {"status": "observed" if text_means else "no_eligible_neutral_loss_positions",
                    "neutral_text_count": len(self.neutral_texts), "texts_with_loss": len(text_means),
                    "equal_text_mean_delta": _stats(text_means)["mean"],
                    "by_text": sorted(self.neutral_texts, key=lambda r: r["text_id"])},
                "original_noop_identity": {"status": "observed" if self.noops else "not_applicable_nonzero_recipe",
                                           "rows": sorted(self.noops, key=lambda r: r["row_id"])}}


class _Census:
    def __init__(self):
        self.cells = {}
        self.feature_ids = None
        self.row_ids = set()
        self.arms = set()
        self.bindings = {}
        self.panels = defaultdict(set)
        self.clean_texts = set()
        self.q90 = None
        self.q90_rows, self.q90_missing = [], []
        self.qualifications, self.excluded = [], []

    def add(self, row):
        _require(type(row) is dict, "Each raw row must be a JSON object")
        row_id = row.get("id")
        _require(type(row_id) is str and bool(row_id), "Missing raw row ID")
        _require(row_id not in self.row_ids, "Duplicate raw row ID: " + row_id)
        self.row_ids.add(row_id)
        if row_id == "qualification-live":
            _require(type(row.get("checks")) is dict and type(row.get("pass")) is bool,
                     "Malformed original qualification")
            _require(all(type(v) is bool for v in row["checks"].values()), "Nonboolean original qualification checks")
            self.qualifications.append({"row_id": row_id, "original_reported_pass": row["pass"],
                                        "original_checks": deepcopy(row["checks"])})
            return "original_qualification"
        is_teacher = (any(k in row for k in ("corpus", "split", "group", "mode", "strength"))
                      or row_id.startswith(("clean-", "edit-")))
        if not is_teacher:
            self.excluded.append({"row_id": row_id, "reason": "outside_corpus_teacher_panel"})
            return "outside_corpus_teacher_panel"
        check = analysis.validate_teacher_rows([row])
        _require(check["pass"], "Invalid teacher row: " + "; ".join(check["errors"]))
        _require(row.get("corpus") in CORPORA, "Unknown/missing corpus")
        _require(row["group"] in OPERATORS, "Unknown operator")
        _require(type(row.get("text_id")) is str and bool(row["text_id"]), "Missing text_id")
        if row["mode"] == "zero":
            _require(row["group"] == "literal", "Shared clean rows must retain original literal group")
        t = row["result"]["telemetry"]
        if self.feature_ids is None:
            self.feature_ids = list(t["feature_ids"])
        _require(t["feature_ids"] == self.feature_ids, "Ordered feature IDs differ between rows")
        full = _optional_vectors(row)
        text = row["text_id"]
        binding = _digest([row["corpus"], row["split"], row["category"], row["result"]["token_ids"],
                           t["position_metadata"], t["delivery"].get("valid"),
                           t["selected_activations"]["before"], row["result"]["unsteered_nll"],
                           t["delivery"]["clean_norm"]])
        _require(text not in self.bindings or self.bindings[text] == binding,
                 "Paired clean/token/corpus/split mismatch: " + text)
        self.bindings[text] = binding
        operator = "shared_clean" if row["mode"] == "zero" else row["group"]
        key = (row["corpus"], row["split"], operator, row["strength"], row["mode"])
        _require((key, text) not in self.arms, "Duplicate text/arm: " + text)
        self.arms.add((key, text))
        self.panels[key[:2]].add(text)
        if operator == "shared_clean":
            self.clean_texts.add(text)
        if row["mode"] == "amplification":
            quantiles = t.get("q90")
            if quantiles is None:
                self.q90_missing.append(row_id)
            else:
                _require(self.q90 is None or self.q90 == quantiles,
                         "Recorded amplification q90 differs across rows; refusing to pool runs")
                self.q90 = list(quantiles)
                self.q90_rows.append(row_id)
        if key not in self.cells:
            self.cells[key] = _Cell(self.feature_ids)
        self.cells[key].add(row, full)
        return "corpus_teacher"

    def report(self):
        cells = []
        recipes = [("shared_clean", 0, "zero")] + [
            (operator, strength, direction) for operator in OPERATORS
            for strength in analysis.STRENGTHS for direction in analysis.DIRECTIONS]
        for corpus in CORPORA:
            for split in SPLITS:
                panel = self.panels[(corpus, split)]
                for operator, strength, direction in recipes:
                    cell = self.cells.get((corpus, split, operator, strength, direction))
                    rows = sorted(cell.rows, key=lambda r: r["row_id"]) if cell else []
                    texts = {r["text_id"] for r in rows}
                    cells.append({"corpus": corpus, "split": split, "operator": operator,
                        "strength": strength, "direction": direction,
                        "status": "observed" if rows else "not_observed_in_supplied_raw_rows",
                        "row_count": len(rows), "text_count": len(texts), "rows": rows,
                        "observed_panel_text_count": len(panel),
                        "missing_text_ids_relative_to_observed_panel": sorted(panel - texts),
                        "text_ids_without_separate_clean_row": sorted(texts - self.clean_texts),
                        "statistics": cell.report(direction) if cell else None})
        return {"schema_version": SCHEMA, "display_only": True, "postcollection": True,
                "scientific_limits": LIMITS, "scopes": SCOPES, "feature_ids": self.feature_ids or [],
                "raw_row_count": len(self.row_ids), "teacher_row_count": len(self.arms),
                "recorded_amplification_q90": {
                    "status": "partially_recorded" if self.q90_rows and self.q90_missing else
                              "recorded" if self.q90_rows else "not_recorded_in_supplied_rows",
                    "values": self.q90, "recorded_row_ids": sorted(self.q90_rows),
                    "missing_amplification_row_ids": sorted(self.q90_missing), "recomputed": False},
                "original_noop_qualification": {"status": "recorded" if self.qualifications else "not_recorded",
                                                "records": self.qualifications},
                "excluded_rows": sorted(self.excluded, key=lambda r: r["row_id"]), "cells": cells}


def report_corpus(rows_dir, out_dir):
    """Hash/read raw JSON rows once, recheck the snapshot, write a fresh report.

    Only compact numeric samples are retained for exact descriptive quantiles;
    raw telemetry and residual capture files are neither rewritten nor loaded
    wholesale into memory. Files without corpus teacher rows are accounted for.
    """
    source = Path(rows_dir).resolve(strict=True)
    destination = Path(out_dir).resolve()
    protected = source.parent if source.name == "rows" else source
    if destination == protected or protected in destination.parents:
        raise ValueError("Report output must be outside the source release")
    if Path(out_dir).is_symlink() or destination.exists():
        raise FileExistsError("Report output must be a fresh directory")
    _require(source.is_dir(), "Expected a directory containing raw JSON rows")
    paths = sorted(source.glob("*.json"))
    _require(bool(paths), "No raw JSON rows found")
    census, inputs = _Census(), []
    for path in paths:
        _require(not path.is_symlink() and path.is_file(), "Raw rows must be regular files, not symlinks")
        raw = path.read_bytes()
        row = analysis.strict_json_loads(raw.decode("utf-8"))
        kind = census.add(row)
        inputs.append({"path": path.name, "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest(),
                       "row_id": row["id"], "kind": kind})
    report = {**census.report(), "source_rows": _public_path(source), "inputs": inputs,
              "source_hashes": {"report": _file_hash(Path(__file__)),
                                "frozen_analysis_helpers": _file_hash(Path(analysis.__file__))}}
    payload = json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n"
    _require(sorted(source.glob("*.json")) == paths, "Input row inventory changed during reporting")
    for path, item in zip(paths, inputs):
        _require(not path.is_symlink() and _file_hash(path) == item["sha256"],
                 "Input raw bytes changed during reporting: " + path.name)
    destination.mkdir(parents=True, exist_ok=False)
    with (destination / "corpus_report.json").open("x", encoding="utf-8") as handle:
        handle.write(payload)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rows", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    report = report_corpus(args.rows, args.out)
    print(_canonical({"output": _public_path(args.out / "corpus_report.json"),
                      "teacher_rows": report["teacher_row_count"], "raw_rows": report["raw_row_count"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

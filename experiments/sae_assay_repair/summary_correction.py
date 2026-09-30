"""Post-hoc reporting correction; never rewrite Stage 1 rows or change gates.

Usage::

    python -m experiments.sae_assay_repair.summary_correction \
        --rows data/sae_assay_diagnostic/stage1_20260930/rows --out NEW_DIRECTORY

``summarize_activations(ids, telemetry)`` is a stdlib-only backend helper. Its
list-of-features API retains before/after, now over valid nonspecial positions.
Reported generated positions INCLUDE terminal observations. The causal stratum
excludes positions marked terminal_observation_only; it is a metadata mask,
not a causal-effect estimate or a reconstruction of missing successor tokens.

Correction JSON retains the original summaries verbatim as JSON values. The
ALL-versus-nonspecial comparison uses identical stdlib arithmetic on both masks
to distinguish mask changes from historical torch.float32 reduction roundoff.
Empty strata have null frequency/mean/max/quantiles, never fabricated zeros.
Frozen residual-fidelity and norm gates include special tokens; exposure and
efficacy exclude them. Summary corrections do not change those gate masks.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
import hashlib
import json
import math
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCHEMA = "sae_assay_summary_correction_v1"
FIELDS = ("count", "active_count", "frequency", "mean", "max", "positive_q50", "positive_q90")
STRATA = ("nonspecial", "prompt", "generated", "causal", "prompt_causal",
          "generated_causal", "terminal_observation_only")


def _quantile(ordered, fraction):
    if not ordered:
        return None
    index = (len(ordered) - 1) * fraction
    low, high = math.floor(index), math.ceil(index)
    weight = index - low
    return ordered[low] * (1 - weight) + ordered[high] * weight


def _distribution(values):
    positive = sorted(value for value in values if value > 0)
    n = len(values)
    return {"count": n, "active_count": len(positive),
            "frequency": len(positive) / n if n else None,
            "mean": math.fsum(value / n for value in values) if n else None,
            "max": max(values) if n else None,
            "positive_q50": _quantile(positive, .5),
            "positive_q90": _quantile(positive, .9)}


def _masks(ids, telemetry):
    ids = list(ids)
    if (not ids or any(type(i) is not int or i < 0 for i in ids)
            or len(set(ids)) != len(ids) or telemetry.get("feature_ids") != ids):
        raise ValueError("Expected identical, ordered, unique nonnegative feature IDs")
    positions = telemetry["position_metadata"]
    if not isinstance(positions, list):
        raise ValueError("position_metadata must be a list")
    n = len(positions)
    valid = telemetry.get("delivery", {}).get("valid", [True] * n)
    if not isinstance(valid, list) or len(valid) != n or any(type(v) is not bool for v in valid):
        raise ValueError("delivery.valid must be a Boolean per position")
    for phase in ("before", "after"):
        matrix = telemetry["selected_activations"][phase]
        if not isinstance(matrix, list) or len(matrix) != n:
            raise ValueError("Activation position count mismatch")
        for row in matrix:
            if not isinstance(row, list) or len(row) != len(ids):
                raise ValueError("Activation feature count mismatch")
            if any(type(v) not in (int, float) or not math.isfinite(v) or v < 0 for v in row):
                raise ValueError("Activations must be finite nonnegative numbers, not booleans")
    masks = {name: [] for name in STRATA}
    counts = Counter(total_positions=n, special_positions=0, invalid_positions=0,
                     terminal_positions_including_special=0)
    for i, position in enumerate(positions):
        origin, token_class = position["origin"], position["token_class"]
        terminal = position.get("terminal_observation_only", False)
        if (origin not in ("prompt", "generated") or token_class not in (origin, "special")
                or type(terminal) is not bool or (terminal and origin != "generated")):
            raise ValueError("Invalid origin, token class, or terminal observation flag")
        counts["special_positions"] += token_class == "special"
        counts["invalid_positions"] += not valid[i]
        counts["terminal_positions_including_special"] += terminal
        if not valid[i] or token_class == "special":
            continue
        masks["nonspecial"].append(i)
        masks[origin].append(i)
        if terminal:
            masks["terminal_observation_only"].append(i)
        else:
            masks["causal"].append(i)
            masks[origin + "_causal"].append(i)
    counts["excluded_positions"] = n - len(masks["nonspecial"])
    counts.update({name: len(indices) for name, indices in masks.items()})
    return ids, masks, dict(counts)


def summarize_activations(ids, telemetry):
    """Return fresh per-feature summaries without modifying telemetry.

    before/after alias the overall ``strata.nonspecial`` distribution. All
    strata exclude special and invalid positions, including the prompt and
    generated strata. Missing terminal flags mean False, as in older fixtures.
    ``mask_counts`` counts positions, not feature-specific positive activations;
    special and invalid counts may overlap, while excluded_positions is a union.
    """
    ids, masks, counts = _masks(ids, telemetry)
    matrices = telemetry["selected_activations"]
    result = []
    for column, feature in enumerate(ids):
        strata = {name: {phase: _distribution([matrices[phase][i][column] for i in indices])
                         for phase in ("before", "after")} for name, indices in masks.items()}
        result.append({"feature_id": feature, **strata["nonspecial"], "strata": strata,
                       "mask_counts": dict(counts), "schema_version": SCHEMA})
    return result


def _digest(value):
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    return hashlib.sha256(encoded).hexdigest()


def _file_hash(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _public_path(path):
    path = Path(path).resolve()
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError:
        return path.name


def _results(value, pointer=""):
    if isinstance(value, dict):
        if isinstance(value.get("telemetry"), dict):
            yield pointer, value
        for key, child in value.items():
            if key not in ("telemetry", "clean_telemetry", "activation_summaries"):
                escaped = key.replace("~", "~0").replace("/", "~1")
                yield from _results(child, pointer + "/" + escaped)
    elif isinstance(value, list):
        for i, child in enumerate(value):
            yield from _results(child, pointer + "/" + str(i))


def _correction(result):
    telemetry = result["telemetry"]
    ids = telemetry["feature_ids"]
    corrected = summarize_activations(ids, telemetry)
    matrices = telemetry["selected_activations"]
    all_positions = [{"feature_id": feature, **{
        phase: _distribution([row[j] for row in matrices[phase]])
        for phase in ("before", "after")}} for j, feature in enumerate(ids)]
    return {"original_summaries_present": "activation_summaries" in result,
            "original_activation_summaries": result.get("activation_summaries"),
            "old_all_recomputed": all_positions, "activation_summaries": corrected}


def _gate_proof(groups):
    # Import only the existing offline analysis; never import a model/backend.
    from experiments.sae_assay_diagnostic import analysis

    checks = []
    for (group, split), pairs in sorted(groups.items()):
        original, corrected = (list(values) for values in zip(*pairs))
        jobs = []
        zeros = [i for i, row in enumerate(original) if row["mode"] == "zero"]
        if split == "calibration" and zeros:
            jobs.append(("calibration_q90", analysis.calibration_q90, zeros, ()))
        strengths = sorted({r["strength"] for r in original if r["mode"] != "zero"})
        for strength in strengths:
            jobs.append((f"gate_pair:{strength}", analysis.gate_pair,
                         list(range(len(original))), (strength,)))
        if split == "calibration" and strengths == list(analysis.STRENGTHS):
            jobs.append(("select_strength", analysis.select_strength,
                         list(range(len(original))), (group,)))
        for name, function, indices, arguments in jobs:
            before = function([original[i] for i in indices], *arguments)
            after = function([corrected[i] for i in indices], *arguments)
            if before != after:
                raise ValueError(f"Summary correction changed {group}/{split}/{name}")
            checks.append({"group": group, "split": split, "calculation": name,
                           "row_count": len(indices), "equal": True,
                           "original_sha256": _digest(before), "corrected_sha256": _digest(after),
                           "result": before})
    return {"status": "verified" if checks else "not_applicable_no_teacher_rows",
            "scope": "Only supplied teacher rows; not release-completeness or behavioral-endpoint validation.",
            "gate_definitions_changed": False, "checks": checks,
            "analysis_source_sha256": _file_hash(Path(analysis.__file__))}


def correct_run(rows_dir, out_dir):
    """Write only to a fresh directory outside the source rows/release.

    Every direct *.json input, including rows without summaries, is hashed and
    rechecked. Nested generation/replay/qualification results are identified by
    JSON Pointer. Teacher-gate comparisons replace only activation_summaries in
    memory; neither telemetry nor the original summary objects are modified.
    """
    from experiments.sae_assay_diagnostic import analysis

    source, destination = Path(rows_dir).resolve(strict=True), Path(out_dir).resolve()
    protected = source.parent if source.name == "rows" else source
    if destination == protected or protected in destination.parents:
        raise ValueError("Correction output must be outside the source release")
    if Path(out_dir).is_symlink() or destination.exists():
        raise FileExistsError("Correction output must be a new directory")
    paths = sorted(source.glob("*.json"))
    if not source.is_dir() or not paths:
        raise ValueError("Expected a directory containing raw JSON rows")
    inputs, corrections, groups = [], [], defaultdict(list)
    changed_fields = Counter()
    comparison_rows, summary_rows = [], []
    changed_results = 0
    for path in paths:
        if path.is_symlink() or not path.is_file():
            raise ValueError("Raw inputs must be regular files, not symlinks")
        raw = path.read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        row = analysis.strict_json_loads(raw.decode("utf-8"))
        if not isinstance(row, dict):
            raise ValueError("Each raw row must be a JSON object")
        inputs.append({"path": path.name, "bytes": len(raw), "sha256": digest})
        for pointer, result in _results(row):
            correction = _correction(result)
            identity = {"source_path": path.name, "result_pointer": pointer,
                        "row_id": row.get("id"), "input_sha256": digest}
            feature_changes = []
            for old, new in zip(correction["old_all_recomputed"], correction["activation_summaries"]):
                for phase in ("before", "after"):
                    differences = {field: {"old_all": old[phase][field], "nonspecial": new[phase][field]}
                                   for field in FIELDS if old[phase][field] != new[phase][field]}
                    changed_fields.update(differences.keys())
                    feature_changes.append({"feature_id": new["feature_id"], "phase": phase,
                                            "changed_fields": differences})
                    comparison_rows.append({**identity, "feature_id": new["feature_id"], "phase": phase,
                        "changed_fields": ";".join(differences), **{
                            prefix + field: stats[field] for prefix, stats in
                            (("old_all_", old[phase]), ("nonspecial_", new[phase])) for field in FIELDS}})
                    for name, strata in new["strata"].items():
                        summary_rows.append({**identity, "feature_id": new["feature_id"],
                                             "phase": phase, "stratum": name, **strata[phase]})
            changed_results += any(item["changed_fields"] for item in feature_changes)
            corrections.append({**identity, **correction, "old_all_vs_nonspecial": feature_changes})
            if pointer == "/result" and all(k in row for k in ("split", "group", "mode", "strength")):
                replacement = {**row, "result": {**result, "activation_summaries": correction["activation_summaries"]}}
                groups[(row["group"], row["split"])].append((row, replacement))
    if not corrections:
        raise ValueError("No activation telemetry found in raw rows")
    proof = _gate_proof(groups)
    if sorted(source.glob("*.json")) != paths:
        raise ValueError("Input row inventory changed during correction")
    for path, item in zip(paths, inputs):
        if path.is_symlink() or _file_hash(path) != item["sha256"]:
            raise ValueError("Input raw bytes changed during correction: " + path.name)
    report = {"schema_version": SCHEMA, "post_hoc": True, "source_rows": _public_path(source),
              "claim_boundary": "Reporting masks only; no frozen rows, telemetry, gate definitions, or behavioral endpoints are changed.",
              "arithmetic": "stdlib linear-interpolated positive quantiles and fsum means; historical FP32 reductions may differ by roundoff.",
              "terminal_policy": "Generated reports include terminal observations; causal strata exclude only explicitly marked terminal observations.",
              "input_raw_bytes_unchanged": True, "inputs": inputs,
              "counts": {"raw_files": len(inputs), "results": len(corrections),
                         "results_with_mask_differences": changed_results,
                         "feature_phase_comparisons": len(comparison_rows),
                         "feature_phases_with_mask_differences": sum(bool(r["changed_fields"]) for r in comparison_rows),
                         "changed_fields": dict(sorted(changed_fields.items()))},
              "gate_comparison": proof, "corrections": corrections,
              "utility_source_sha256": _file_hash(Path(__file__))}
    destination.mkdir(parents=True, exist_ok=False)
    with (destination / "summary_correction.json").open("x", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2, sort_keys=True, allow_nan=False)
        handle.write("\n")
    for filename, rows in (("activation_summaries.csv", summary_rows),
                           ("summary_differences.csv", comparison_rows)):
        with (destination / filename).open("x", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rows", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    report = correct_run(args.rows, args.out)
    print(json.dumps({"output": _public_path(args.out), **report["counts"],
                      "gate_comparison": report["gate_comparison"]["status"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

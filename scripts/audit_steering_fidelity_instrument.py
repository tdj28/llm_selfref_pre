#!/usr/bin/env python3
"""Read-only, post-outcome instrument diagnostic for the completed Phase C release.

Stdlib only. No model, tokenizer, provider, or lifecycle calls. This complements,
and does not replace, the frozen receipt/delivery audit. Output is new ignored
out/ data; a structural pass never qualifies pressure, liveness, or Stage T.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from experiments.steering_fidelity import protocol as p
from experiments.steering_fidelity.audit import validate_row
from experiments.steering_fidelity.items import fact_items
from experiments.steering_fidelity.runner import pressure_gate

FREEZE = "2d9c94f1de59f0f59dd89636c20afece1f6d1daf"
PLAN_SHA256 = "6f0a5609caabeae6907513939d0a647fbd2b99dacf9f519aeb434b001e775fb0"
RELEASE_MANIFEST_SHA256 = "815cd2e76adff2e9a1d7c182d6651a77af52c88d885dbb00e0d7ef6ef2aa8bc0"
DEFAULT_RUN = ROOT / "data/steering_fidelity/calibration_v1_20261002"
DEFAULT_PLAN = ROOT / "data/steering_fidelity/calibration_plan_20261002/PLAN.json"
PROBE_PREFIX = "Return a JSON object with keys 'proposition' and 'truth' for this proposition: "


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def parse_json(raw):
    def pairs(values):
        result = {}
        for key, value in values:
            require(key not in result, "Duplicate JSON key: " + key)
            result[key] = value
        return result

    def nonfinite(value):
        raise ValueError("Nonfinite JSON: " + value)

    return json.loads(raw, object_pairs_hook=pairs, parse_constant=nonfinite)


def probability(value, name):
    require(type(value) in (int, float) and math.isfinite(value) and 0 <= value <= 1,
            "Invalid probability: " + name)


def check_scores(row):
    for name in ("truth", "correct", "format_valid"):
        require(type(row.get(name)) is bool, "Nonboolean score: " + name)
    for name in ("p_yes", "p_no", "p_correct", "valid_mass"):
        probability(row.get(name), name)
    mass = row["valid_mass"]
    require(mass > 0 and math.isclose(row["p_yes"] + row["p_no"], mass,
                                    rel_tol=1e-12, abs_tol=1e-15), "Choice mass mismatch")
    score = (row["p_yes"] if row["truth"] else row["p_no"]) / mass
    require(math.isclose(score, row["p_correct"], rel_tol=1e-12, abs_tol=1e-15)
            and row["correct"] == (score > .5), "Gold score mismatch (ties are incorrect)")


def check_spec(row, spec):
    for key in ("id", "item_id", "family", "frame", "arm", "rung", "truth",
                "prompt", "pressure_level", "draw"):
        require(type(row.get(key)) is type(spec.get(key)) and row.get(key) == spec.get(key),
                "Design mismatch: " + spec["id"] + ":" + key)
    require(row.get("missing") is False, "Missing outcome: " + spec["id"])
    check_scores(row)


def check_inventory(rows, specs):
    expected = {row["id"]: row for row in specs}
    require(len(expected) == len(specs), "Duplicate expected ID")
    seen = set()
    for row in rows:
        key = row.get("id")
        require(key in expected and key not in seen, "Unexpected or duplicate row ID")
        check_spec(row, expected[key])
        seen.add(key)
    require(seen == expected.keys(), "Incomplete expected inventory")


def rates(rows):
    n = len(rows)
    correct = sum(row["correct"] for row in rows)
    return {"n": n, "correct": correct, "errors": n - correct,
            "hard_accuracy": correct / n if n else None,
            "hard_headroom": (n - correct) / n if n else None,
            "soft_accuracy": math.fsum(row["p_correct"] for row in rows) / n if n else None,
            "format_valid_count": sum(row["format_valid"] for row in rows),
            "format_rate": sum(row["format_valid"] for row in rows) / n if n else None,
            "mean_valid_mass": math.fsum(row["valid_mass"] for row in rows) / n if n else None}


def paired(neutral, framed):
    require(len(neutral) == len(framed), "Unpaired frame inventory")
    transitions = Counter()
    for a, b in zip(neutral, framed):
        require(a["item_id"] == b["item_id"], "Pair identity mismatch")
        transitions[f"{'correct' if a['correct'] else 'wrong'}_to_"
                    f"{'correct' if b['correct'] else 'wrong'}"] += 1
    n = len(neutral)
    new = transitions["correct_to_wrong"]
    repaired = transitions["wrong_to_correct"]
    return {"n_pairs": n, **{key: transitions[key] for key in (
                "correct_to_correct", "correct_to_wrong", "wrong_to_correct", "wrong_to_wrong")},
            "net_error_increase": (new - repaired) / n if n else None,
            "new_error_fraction_all_items": new / n if n else None,
            "soft_accuracy_change": math.fsum(b["p_correct"] - a["p_correct"]
                                               for a, b in zip(neutral, framed)) / n if n else None}


def pressure_diagnostic(rows):
    specs = [r for r in p.inventory() if r["family"] == "fact" and r["arm"] == "zero"]
    check_inventory(rows, specs)  # All 200 stance rows, not just 100 opposed rows.
    facts = fact_items("calibration")
    meta = {item["id"]: item for item in facts}
    families = {"all": set(meta), "arithmetic": {i for i, m in meta.items() if m["kind"] != "general"},
                "general": {i for i, m in meta.items() if m["kind"] == "general"}}
    families.update({"kind:" + kind: {i for i, m in meta.items() if m["kind"] == kind}
                     for kind in sorted({m["kind"] for m in facts})})
    neutral = {r["item_id"]: r for r in rows if r["frame"] == "neutral"}
    cells = []
    for family, ids in families.items():
        for truth in (False, True):
            ids_here = {i for i in ids if meta[i]["truth"] == truth}
            for level, frame in ((None, "neutral"), (0, "assert"), (0, "doubt"),
                                 (1, "assert"), (1, "doubt")):
                group = sorted((r for r in rows if r["item_id"] in ids_here
                                and r["frame"] == frame and r.get("pressure_level") == level),
                               key=lambda r: r["item_id"])
                cell = {"item_family": family, "truth": truth, "frame": frame,
                        "pressure_level": level, **rates(group)}
                if frame != "neutral":
                    cell["stance_relation"] = "opposed" if (frame == "assert") != truth else "congruent"
                    cell["paired_vs_neutral"] = paired([neutral[r["item_id"]] for r in group], group)
                cells.append(cell)
    return {"n_neutral": 50, "n_pressure": 200, "n_unique_facts": 50,
            "family_truth_counts": {name: {str(t): sum(meta[i]["truth"] == t for i in ids)
                                           for t in (False, True)} for name, ids in families.items()},
            "cells": cells, "frozen_gate_recomputed": pressure_gate(rows),
            "interpretation": "Absolute opposed error headroom is not induced error. Paired changes "
            "describe these fixed prompt contrasts, not deception, latent belief, or population effects. "
            "The frozen gate does not require a neutral-to-opposed error increase; baseline mistakes "
            "can supply its headroom. Groupings overlap and are not independent replications."}


def probe_diagnostic(payloads):
    items = p.calibration_items()[:20]
    expected = {f"positive-activation-{i:02d}": item for i, item in enumerate(items)}
    require(len(payloads) == len(expected), "Expected 20 JSON probes")
    seen, records = set(), []
    counts = {str(feature): 0 for feature in p.POSITIVE_IDS}
    for payload in sorted(payloads, key=lambda row: row["id"]):
        key = payload["id"]
        require(key in expected and key not in seen, "Unexpected or duplicate probe")
        seen.add(key)
        item, result = expected[key], payload["result"]
        require(payload.get("plan_sha256") == PLAN_SHA256 and payload.get("freeze_commit") == FREEZE,
                "Probe binding mismatch")
        require(payload.get("prompt") == PROBE_PREFIX + item["statement"], "Probe context mismatch")
        require(payload.get("scope") == "activation_only; choice scores not interpreted",
                "Probe scope mismatch")
        require(result.get("truth") is item["truth"], "Probe truth mismatch")
        tokens, telemetry, screen = result["input_token_ids"], result["telemetry"], result["screen"]
        require(tokens and all(type(t) is int and t >= 0 for t in tokens), "Invalid input tokens")
        require(result["input_token_ids_sha256"] == digest(json.dumps(tokens).encode()),
                "Input-token digest mismatch")
        require(telemetry.get("native_dtype") == "torch.bfloat16" and telemetry.get("hook") == 50
                and telemetry.get("intervention") is None, "Probe is not native unsteered layer 50")
        positions = telemetry["position_metadata"]
        require(len(tokens) == len(positions), "Position inventory mismatch")
        for i, position in enumerate(positions):
            require(position.get("position") == i and position.get("token_id") == tokens[i]
                    and type(position.get("special")) is bool and position.get("origin") == "prompt",
                    "Probe position/context mismatch")
        nonspecial = [i for i, position in enumerate(positions) if not position["special"]]
        at = screen["position"]
        require(nonspecial and type(at) is int and at == nonspecial[-1], "Wrong screen position")
        ids, values = screen["positive_ids"], screen["positive_values"]
        require(len(ids) == len(values) and len(ids) == len(set(ids))
                and all(type(i) is int and 0 <= i < 65536 for i in ids), "Invalid positive support")
        require(all(type(v) in (int, float) and math.isfinite(v) and v > 0 for v in values),
                "Invalid positive activation")
        require(len(screen["residual_norms"]) == len(nonspecial), "Residual-position mismatch")
        require(all(type(v) in (int, float) and math.isfinite(v) and v > 0
                    for v in screen["residual_norms"]), "Invalid screen residual norm")
        require("response" not in result, "Activation probe unexpectedly contains a generation")
        observed = dict(zip(ids, values))
        for feature in p.POSITIVE_IDS:
            counts[str(feature)] += feature in observed
        records.append({"id": key, "item_id": item["id"], "kind": item["kind"], "truth": item["truth"],
                        "prompt_sha256": digest(payload["prompt"].encode()),
                        "input_token_ids_sha256": result["input_token_ids_sha256"],
                        "rendered_input_sha256": result["rendered_input_sha256"],
                        "input_positions": len(tokens), "screen_position": at,
                        "screen_token_id": tokens[at], "is_final_input_position": at == len(tokens) - 1,
                        "screen_origin": positions[at]["origin"], "input_tail_ids": tokens[-5:],
                        "positive_feature_values": {str(f): observed.get(f, 0.) for f in p.POSITIVE_IDS},
                        "next_token_argmax_text": result["top_token"]})
    return {"n_activation_payloads": 20, "n_unique_items": len(items), "screened_positions": 20,
            "item_kind_counts": dict(sorted(Counter(i["kind"] for i in items).items())),
            "truth_counts": {str(t): sum(i["truth"] == t for i in items) for t in (False, True)},
            "uncovered_fact_kinds": sorted({i["kind"] for i in fact_items("calibration")}
                                           - {i["kind"] for i in items}),
            "positive_probe_counts": counts,
            "screen_token_counts": dict(sorted(Counter(str(r["screen_token_id"]) for r in records).items())),
            "next_token_argmax_counts": dict(sorted(Counter(r["next_token_argmax_text"] for r in records).items())),
            "teacher_forced_JSON_continuation_positions_observed": 0,
            "generated_code_positions_observed": 0, "probes": records,
            "interpretation": "Source score() uses add_generation_prompt=True and screens one clean "
            "last-non-special input state according to recorded tokenizer flags. Token IDs are not "
            "decoded here. Next-token argmax is a logit readout, not generated text. No full-width "
            "screen of JSON body/code positions exists; six-target reencoding does not supply it. "
            "Inactivity here neither disproves feature liveness elsewhere nor shows a zero behavioral effect."}


class Inputs:
    def __init__(self):
        self.facts = {}

    def read(self, path, label, expected=None):
        raw = Path(path).read_bytes()
        fact = {"sha256": digest(raw), "bytes": len(raw)}
        if expected is not None:
            require(fact["sha256"] == expected, "Input hash mismatch: " + label)
        require(label not in self.facts or self.facts[label] == fact, "Input changed during audit")
        self.facts[label] = fact
        return raw

    def json(self, path, label, expected=None):
        return parse_json(self.read(path, label, expected))


def release_manifest(inputs, run):
    manifest = inputs.json(Path(run) / "RELEASE_MANIFEST.json", "run/RELEASE_MANIFEST.json",
                           RELEASE_MANIFEST_SHA256)
    require(manifest.get("freeze_commit") == FREEZE and manifest.get("plan_sha256") == PLAN_SHA256,
            "Release manifest freeze/plan binding mismatch")
    require(manifest.get("schema") == "steering_fidelity_calibration_release_v1"
            and manifest.get("status") == "complete", "Release manifest status/schema mismatch")
    return manifest


def audit(run=DEFAULT_RUN, plan_path=DEFAULT_PLAN):
    run, plan_path, inputs = Path(run), Path(plan_path), Inputs()
    plan = inputs.json(plan_path, "plan/PLAN.json", PLAN_SHA256)
    # Verify the immutable plan's closure, independent of today's source glob.
    for name, expected in sorted((plan["source_hashes"] | plan["input_hashes"]).items()):
        path = (ROOT / name).resolve()
        require(path.is_relative_to(ROOT.resolve()), "Source path escaped repository")
        inputs.read(path, "repository/" + name, expected)
    require(plan["rows"] == p.inventory(), "Frozen inventory differs from source reconstruction")
    specs = {r["id"]: r for r in plan["rows"]}
    require(len(specs) == 9300, "Expected 9300 planned forwards")
    manifest = release_manifest(inputs, run)
    released = {entry["path"]: entry for entry in manifest["files"]}
    require(len(released) == len(manifest["files"]), "Duplicate release-manifest path")

    def read(name):
        require(name in released, "Unmanifested input: " + name)
        value = inputs.json(run / name, "run/" + name, released[name]["sha256"])
        require(inputs.facts["run/" + name]["bytes"] == released[name]["bytes"], "Released size mismatch")
        return value

    files = {path.name for path in (run / "forwards").iterdir()}
    require(files == {key + ".json" for key in specs}, "Full forward filename inventory mismatch")
    pressure_rows = []
    for key, spec in sorted(specs.items()):
        row = read("forwards/" + key + ".json")
        check_spec(row, spec)
        validate_row(row, spec, PLAN_SHA256, FREEZE)
        require(row.get("screen_requested") is spec["screen"], "Screen request mismatch")
        if row["family"] == "fact" and row["arm"] == "zero":
            pressure_rows.append(row)
    pressure = pressure_diagnostic(pressure_rows)
    require(pressure["frozen_gate_recomputed"] == read("pressure-analysis.json"), "Saved pressure gate mismatch")
    probe_names = [f"positive-activation-{i:02d}" for i in range(20)]
    expected_files = {key + suffix for key in probe_names for suffix in (".json", ".dispatch.json")}
    require({path.name for path in (run / "liveness").iterdir()} == expected_files,
            "JSON probe/dispatch inventory mismatch; this audit expects the skipped generation release")
    payloads = []
    for key in probe_names:
        dispatch = read("liveness/" + key + ".dispatch.json")
        require(dispatch.get("id") == key and dispatch.get("plan_sha256") == PLAN_SHA256,
                "JSON dispatch binding mismatch")
        payload = read("liveness/" + key + ".json")
        require(payload.get("id") == key, "Misnamed probe payload")
        payloads.append(payload)
    probes = probe_diagnostic(payloads)
    saved = read("liveness-analysis.json")
    calibration = read("calibration-analysis.json")
    require(saved == {"activation_scope": "at_least_1_of_20_last_non_special_JSON_request_states",
                      "comparisons": [], "eligible_ids": [], "feature_ids": list(p.POSITIVE_IDS),
                      "positive_probe_counts": probes["positive_probe_counts"],
                      "reason": "neither_predeclared_positive_feature_active_on_JSON_probes",
                      "selected_rung": calibration["selected_rung"], "status": "not_run"}
            and not any(probes["positive_probe_counts"].values()), "Saved liveness decision mismatch")
    label_bytes = inputs.read(ROOT / p.LABELS, "repository/" + p.LABELS,
                              plan["input_hashes"][p.LABELS])
    labels = [parse_json(line) for line in label_bytes.splitlines()]
    probes["public_label_records"] = [label for label in labels if label["feature_id"] in p.POSITIVE_IDS]
    require(len(probes["public_label_records"]) == 2, "Missing public JSON labels")
    probes.update(n_dispatch_markers=20, n_generated_responses=0, behavioral_effect=None,
                  frozen_liveness_summary=saved, model_chat_template_sha256=read("model.json")["chat_template_sha256"])
    inputs.read(Path(__file__), "diagnostic/audit_steering_fidelity_instrument.py")
    facts = dict(sorted(inputs.facts.items()))
    return {"schema": "steering_fidelity_instrument_audit_v1", "status": "offline_diagnostic_complete",
            "timing": "post-outcome descriptive audit, not a new scientific qualification",
            "full_forward_inventory": 9300, "pressure": pressure, "json_probes": probes,
            "stage_T": "blocked; no E-only fallback", "freeze_commit": FREEZE,
            "plan_sha256": PLAN_SHA256, "release_manifest_sha256": RELEASE_MANIFEST_SHA256,
            "input_facts_sha256": digest(p.canonical(facts).encode()),
            "input_facts": facts,
            "limits": "No new outcomes, receipt-chain reconstruction, dose reselection, tokenizer replay, "
            "population uncertainty, semantic suppression, honesty or consciousness inference. "
            "Manifest/source checks and per-row validation complement the original frozen audit."}


def write_report(out, report):
    out = Path(out).resolve()
    require(out.is_relative_to((ROOT / "out").resolve()) and out != (ROOT / "out").resolve(),
            "Output must be a new directory beneath repository out/")
    require(not out.exists(), "Refusing to replace output")
    ignored = subprocess.run(["git", "check-ignore", "--quiet", "--", str(out)], cwd=ROOT)
    require(ignored.returncode == 0, "Output must be ignored")
    out.mkdir(parents=True, exist_ok=False)
    with (out / "instrument-audit.json").open("x", encoding="utf-8") as handle:
        handle.write(json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, default=DEFAULT_RUN)
    parser.add_argument("--plan", type=Path, default=DEFAULT_PLAN)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    report = audit(args.run, args.plan)
    write_report(args.out, report)
    print("Audited 9300 forwards, 200 pressure rows, 20 JSON probe/dispatch pairs. Stage T remains blocked.")
    print(args.out / "instrument-audit.json")


if __name__ == "__main__":
    main()

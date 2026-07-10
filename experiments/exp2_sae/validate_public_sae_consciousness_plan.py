#!/usr/bin/env python3
"""Independently audit a public-SAE consciousness-gating trial plan."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import random
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
EXPECTED_PROTOCOL = "public_sae_consciousness_gating_v1"
EXPECTED_MODEL_REVISION = "6f6073b423013f6a7d4d9f39144961bfbfbc386b"
EXPECTED_SAE_REVISION = "128ee921ecd1b8b3a87d776cbcc357c0855da134"
EXPECTED_TARGETS = (30032, 58667, 22004, 30686, 41533, 23893)
EXPECTED_SEEDS = (101, 202, 303, 404, 505, 606, 707, 808, 909, 1001)
EXPECTED_VALUES = tuple(round(value / 10, 1) for value in range(-6, 7))
EXPECTED_PROMPT_HASHES = {
    "self_ref_induction_sha256": "22c431ff831d54d6f2f1f11e5c2771630a095930c2f59d9556c80ede208e0933",
    "binary_query_sha256": "924f65d595df33b8f92b2cf192ec1d8b2358863b13cfce9a5a96134aae68722e",
}
EXPECTED_CANDIDATE_SEED = 20260710
EXPECTED_CANDIDATE_COUNT = 512
DICTIONARY_SIZE = 65_536
PREVIOUS_CONTROLS = {
    388,
    22326,
    30689,
    41530,
    41535,
    41536,
    45642,
    47840,
    55823,
    56326,
    58665,
    58669,
}


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def expected_candidate_pool() -> list[int]:
    excluded = set(PREVIOUS_CONTROLS)
    for target in EXPECTED_TARGETS:
        for feature_id in range(max(0, target - 3), min(DICTIONARY_SIZE, target + 4)):
            excluded.add(feature_id)
    rng = random.Random(EXPECTED_CANDIDATE_SEED)
    selected: list[int] = []
    seen: set[int] = set()
    while len(selected) < EXPECTED_CANDIDATE_COUNT:
        feature_id = rng.randrange(DICTIONARY_SIZE)
        if feature_id in excluded or feature_id in seen:
            continue
        selected.append(feature_id)
        seen.add(feature_id)
    return selected


def candidate_hash(feature_ids: list[int]) -> str:
    return sha256_bytes(json.dumps(feature_ids, separators=(",", ":")).encode())


def verify_manifest_files(run_dir: Path, manifest: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    for entry in manifest.get("files", []):
        path = run_dir / str(entry.get("path", ""))
        if not path.is_file():
            errors.append(f"manifest file missing: {path.name}")
            continue
        if path.stat().st_size != int(entry.get("bytes", -1)):
            errors.append(f"manifest byte mismatch: {path.name}")
        if sha256_file(path) != entry.get("sha256"):
            errors.append(f"manifest SHA-256 mismatch: {path.name}")
    return errors


def verify_source_files(manifest: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    for entry in manifest.get("source_files", []):
        relative = Path(str(entry.get("path", "")))
        if relative.is_absolute() or ".." in relative.parts:
            errors.append(f"unsafe source path in manifest: {relative}")
            continue
        path = REPO_ROOT / relative
        if not path.is_file():
            errors.append(f"manifest source file missing: {relative}")
            continue
        if path.stat().st_size != int(entry.get("bytes", -1)):
            errors.append(f"manifest source byte mismatch: {relative}")
        if sha256_file(path) != entry.get("sha256"):
            errors.append(f"manifest source SHA-256 mismatch: {relative}")
    return errors


def audit_aggregate_blocks(blocks: list[dict[str, Any]]) -> tuple[list[str], dict[str, Any]]:
    errors: list[str] = []
    if len(blocks) != 50:
        errors.append(f"expected 50 aggregate blocks, got {len(blocks)}")
    block_ids = [row.get("block_id") for row in blocks]
    if len(block_ids) != len(set(block_ids)):
        errors.append("aggregate block IDs are not unique")
    count_distribution = Counter(int(row.get("feature_count", -1)) for row in blocks)
    if count_distribution != Counter({2: 17, 3: 17, 4: 16}):
        errors.append(f"aggregate feature-count schedule differs: {count_distribution}")
    seed_distribution = Counter(int(row.get("seed", -1)) for row in blocks)
    if seed_distribution != Counter({seed: 5 for seed in EXPECTED_SEEDS}):
        errors.append("aggregate seeds are not balanced five times each")
    inclusions: Counter[int] = Counter()
    for row in blocks:
        targets = [int(value) for value in row.get("target_feature_ids", [])]
        magnitudes = [float(value) for value in row.get("magnitudes", [])]
        if len(targets) != int(row.get("feature_count", -1)) or len(magnitudes) != len(targets):
            errors.append(f"aggregate block shape mismatch: {row.get('block_id')}")
            continue
        if len(targets) != len(set(targets)) or not set(targets).issubset(EXPECTED_TARGETS):
            errors.append(f"invalid aggregate target subset: {row.get('block_id')}")
        if any(value < 0.4 or value > 0.6 for value in magnitudes):
            errors.append(f"aggregate magnitude outside [0.4, 0.6]: {row.get('block_id')}")
        if any(round(value, 3) != value for value in magnitudes):
            errors.append(f"aggregate magnitude is not rounded to three decimals: {row.get('block_id')}")
        inclusions.update(targets)
    if sorted(inclusions.values()) != [24, 25, 25, 25, 25, 25]:
        errors.append(f"aggregate target inclusion is not balanced: {dict(inclusions)}")
    return errors, {
        "n_blocks": len(blocks),
        "feature_count_distribution": dict(sorted(count_distribution.items())),
        "seed_distribution": dict(sorted(seed_distribution.items())),
        "target_inclusions": dict(sorted(inclusions.items())),
    }


def audit_individual_literal(rows: list[dict[str, Any]]) -> tuple[list[str], dict[str, Any]]:
    errors: list[str] = []
    observed: Counter[tuple[int, float, int]] = Counter()
    for row in rows:
        interventions = row.get("interventions", [])
        if len(interventions) != 1:
            errors.append(f"individual trial has !=1 intervention: {row.get('trial_id')}")
            continue
        intervention = interventions[0]
        key = (
            int(intervention["feature_id"]),
            float(intervention["base_coefficient"]),
            int(row["seed"]),
        )
        observed[key] += 1
        if row.get("phase") != "individual_literal" or row.get("scale") != "literal":
            errors.append(f"individual literal metadata mismatch: {row.get('trial_id')}")
        if float(intervention.get("multiplier", -1)) != 1.0:
            errors.append(f"literal multiplier is not one: {row.get('trial_id')}")
        if abs(float(intervention["coefficient"]) - float(intervention["base_coefficient"])) > 1e-9:
            errors.append(f"literal coefficient mismatch: {row.get('trial_id')}")
    expected = Counter(
        (feature_id, value, seed)
        for feature_id in EXPECTED_TARGETS
        for value in EXPECTED_VALUES
        for seed in EXPECTED_SEEDS
    )
    if observed != expected:
        errors.append("individual literal plan is not the exact 6x13x10 cross-product")
    return errors, {"n_trials": len(rows), "n_zero_rows": sum(key[1] == 0 for key in observed)}


def audit_precalibration(run_dir: Path) -> dict[str, Any]:
    errors: list[str] = []
    required = {
        "MANIFEST.json",
        "CALIBRATION_PLAN.json",
        "protocol_snapshot.json",
        "calibration_candidate_pool.csv",
        "aggregate_blocks.jsonl",
        "individual_literal_plan.jsonl",
    }
    missing = sorted(name for name in required if not (run_dir / name).is_file())
    errors.extend(f"required file missing: {name}" for name in missing)
    if missing:
        return {"status": "fail", "mode": "pre_calibration", "errors": errors, "checks": {}}

    manifest = json.loads((run_dir / "MANIFEST.json").read_text(encoding="utf-8"))
    snapshot = json.loads((run_dir / "protocol_snapshot.json").read_text(encoding="utf-8"))
    calibration = json.loads((run_dir / "CALIBRATION_PLAN.json").read_text(encoding="utf-8"))
    errors.extend(verify_manifest_files(run_dir, manifest))
    errors.extend(verify_source_files(manifest))
    if snapshot.get("protocol_version") != EXPECTED_PROTOCOL:
        errors.append("protocol version mismatch")
    if snapshot.get("model_revision") != EXPECTED_MODEL_REVISION:
        errors.append("model revision mismatch")
    if snapshot.get("sae_revision") != EXPECTED_SAE_REVISION:
        errors.append("SAE revision mismatch")
    for key, value in EXPECTED_PROMPT_HASHES.items():
        if snapshot.get("prompt_hashes", {}).get(key) != value:
            errors.append(f"prompt hash mismatch: {key}")

    with (run_dir / "calibration_candidate_pool.csv").open(encoding="utf-8", newline="") as handle:
        candidate_rows = list(csv.DictReader(handle))
    candidate_ids = [int(row["feature_id"]) for row in candidate_rows]
    if [int(row["candidate_order"]) for row in candidate_rows] != list(range(len(candidate_rows))):
        errors.append("candidate ordering column is not contiguous")
    if candidate_ids != expected_candidate_pool():
        errors.append("candidate pool does not match independent seeded reconstruction")
    if calibration.get("candidate_pool_sha256") != candidate_hash(candidate_ids):
        errors.append("calibration candidate-pool hash mismatch")
    if manifest.get("candidate_pool_sha256") != candidate_hash(candidate_ids):
        errors.append("manifest candidate-pool hash mismatch")

    block_errors, block_checks = audit_aggregate_blocks(read_jsonl(run_dir / "aggregate_blocks.jsonl"))
    individual_errors, individual_checks = audit_individual_literal(
        read_jsonl(run_dir / "individual_literal_plan.jsonl")
    )
    errors.extend(block_errors)
    errors.extend(individual_errors)
    checks = {
        "manifest_files_rehash": not any("manifest" in error for error in errors),
        "candidate_pool_exact": candidate_ids == expected_candidate_pool(),
        "aggregate_blocks": block_checks,
        "individual_literal": individual_checks,
        "expected_final_trials": manifest.get("expected_final_trials") == 1500,
    }
    if not checks["expected_final_trials"]:
        errors.append("manifest does not declare 1,500 expected final trials")
    return {
        "status": "pass" if not errors else "fail",
        "mode": "pre_calibration",
        "errors": errors,
        "checks": checks,
    }


def _sign_flip_ok(suppress: dict[str, Any], amplify: dict[str, Any]) -> bool:
    left = suppress.get("interventions", [])
    right = amplify.get("interventions", [])
    if len(left) != len(right):
        return False
    for negative, positive in zip(left, right):
        if negative.get("feature_id") != positive.get("feature_id"):
            return False
        if negative.get("matched_target_id") != positive.get("matched_target_id"):
            return False
        if abs(float(negative["coefficient"]) + float(positive["coefficient"])) > 1e-9:
            return False
        if abs(float(negative["base_coefficient"]) + float(positive["base_coefficient"])) > 1e-9:
            return False
    return True


def audit_final(run_dir: Path) -> dict[str, Any]:
    errors: list[str] = []
    manifest_path = run_dir / "PLAN_MANIFEST.json"
    plan_path = run_dir / "confirmatory_plan.jsonl"
    control_path = run_dir / "control_matching.csv"
    blocks_path = run_dir / "aggregate_blocks.jsonl"
    candidate_path = run_dir / "calibration_candidate_pool.csv"
    snapshot_path = run_dir / "protocol_snapshot.json"
    calibration_path = run_dir / "calibration.json"
    calibration_audit_path = run_dir / "independent_calibration_audit.json"
    required_paths = (
        manifest_path,
        plan_path,
        control_path,
        blocks_path,
        candidate_path,
        snapshot_path,
        calibration_path,
        calibration_audit_path,
    )
    if not all(path.is_file() for path in required_paths):
        return {
            "status": "fail",
            "mode": "final",
            "errors": ["final plan is missing one or more self-contained plan inputs"],
            "checks": {},
        }
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    errors.extend(verify_manifest_files(run_dir, manifest))
    errors.extend(verify_source_files(manifest))
    calibration_audit = json.loads(calibration_audit_path.read_text(encoding="utf-8"))
    if calibration_audit.get("status") != "pass":
        errors.append("independent calibration audit did not pass")
    if calibration_audit.get("calibration_sha256") != sha256_file(calibration_path):
        errors.append("independent calibration audit references a different calibration file")
    if manifest.get("calibration_sha256") != sha256_file(calibration_path):
        errors.append("final manifest calibration hash mismatch")
    if manifest.get("calibration_audit_sha256") != sha256_file(calibration_audit_path):
        errors.append("final manifest calibration-audit hash mismatch")
    rows = read_jsonl(plan_path)
    blocks = read_jsonl(blocks_path)
    block_errors, block_checks = audit_aggregate_blocks(blocks)
    errors.extend(block_errors)
    blocks_by_id = {str(block["block_id"]): block for block in blocks}
    snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
    if snapshot.get("protocol_version") != EXPECTED_PROTOCOL:
        errors.append("final snapshot protocol version mismatch")
    with candidate_path.open(encoding="utf-8", newline="") as handle:
        final_candidate_rows = list(csv.DictReader(handle))
    candidate_ids = [int(row["feature_id"]) for row in final_candidate_rows]
    if candidate_ids != expected_candidate_pool():
        errors.append("final candidate pool differs from seeded reconstruction")
    if manifest.get("candidate_pool_sha256") != candidate_hash(candidate_ids):
        errors.append("final manifest candidate-pool hash mismatch")
    if len(rows) != 1500 or manifest.get("n_trials") != 1500:
        errors.append(f"final plan count is not 1,500: {len(rows)}")
    trial_ids = [row.get("trial_id") for row in rows]
    if len(trial_ids) != len(set(trial_ids)):
        errors.append("final trial IDs are not unique")
    if sorted(int(row.get("execution_order", -1)) for row in rows) != list(range(len(rows))):
        errors.append("execution order is not a complete 0..1499 permutation")
    if any(row.get("protocol_version") != EXPECTED_PROTOCOL for row in rows):
        errors.append("one or more final rows have the wrong protocol version")
    for row in rows:
        expected_multiplier = (
            1.0 if row.get("scale") == "literal" else float(manifest["calibrated_multiplier"])
        )
        for intervention in row.get("interventions", []):
            if abs(float(intervention["multiplier"]) - expected_multiplier) > 1e-9:
                errors.append(f"scale multiplier mismatch: {row.get('trial_id')}")
                break
            expected = round(
                float(intervention["base_coefficient"]) * float(intervention["multiplier"]), 6
            )
            if abs(float(intervention["coefficient"]) - expected) > 1e-9:
                errors.append(f"coefficient arithmetic mismatch: {row.get('trial_id')}")
                break

    phase_counts = Counter(row.get("phase") for row in rows)
    expected_phase_counts = Counter(
        {
            "individual_literal": 780,
            "aggregate_literal": 400,
            "individual_calibrated": 120,
            "aggregate_calibrated": 200,
        }
    )
    if phase_counts != expected_phase_counts:
        errors.append(f"final phase counts differ: {phase_counts}")

    literal_errors, _literal_checks = audit_individual_literal(
        [row for row in rows if row.get("phase") == "individual_literal"]
    )
    errors.extend(literal_errors)
    calibrated_individual = [
        row for row in rows if row.get("phase") == "individual_calibrated"
    ]
    calibrated_cross = Counter(
        (
            int(row["feature_anchor"]),
            float(row["interventions"][0]["base_coefficient"]),
            int(row["seed"]),
        )
        for row in calibrated_individual
    )
    expected_calibrated = Counter(
        (feature_id, value, seed)
        for feature_id in EXPECTED_TARGETS
        for value in (-0.6, 0.6)
        for seed in EXPECTED_SEEDS
    )
    if calibrated_cross != expected_calibrated:
        errors.append("calibrated individual plan is not the exact 6x2x10 cross-product")

    with control_path.open(encoding="utf-8", newline="") as handle:
        control_rows = list(csv.DictReader(handle))
    panel_maps: dict[int, dict[int, int]] = defaultdict(dict)
    for row in control_rows:
        panel_maps[int(row["panel"])][int(row["target_feature_id"])] = int(
            row["control_feature_id"]
        )
    if set(panel_maps) != {1, 2, 3} or any(
        set(mapping) != set(EXPECTED_TARGETS) for mapping in panel_maps.values()
    ):
        errors.append("control table does not contain three complete target mappings")
    controls = [value for mapping in panel_maps.values() for value in mapping.values()]
    if len(controls) != len(set(controls)):
        errors.append("control panels are not disjoint")
    if not set(controls).issubset(candidate_ids):
        errors.append("one or more control IDs are absent from the frozen candidate pool")

    aggregate_groups: dict[tuple[str, str, str], dict[str, dict[str, Any]]] = defaultdict(dict)
    for row in rows:
        if row.get("design") == "aggregate":
            key = (str(row["scale"]), str(row["block_id"]), str(row["analysis_role"]))
            aggregate_groups[key][str(row["sign"])] = row
            block = blocks_by_id.get(str(row["block_id"]))
            if block is None:
                errors.append(f"aggregate row references unknown block: {row.get('trial_id')}")
                continue
            if int(row["seed"]) != int(block["seed"]):
                errors.append(f"aggregate row seed differs from block: {row.get('trial_id')}")
            role = str(row["analysis_role"])
            panel_number = row.get("control_panel")
            mapping = {target: target for target in EXPECTED_TARGETS}
            if role != "target":
                if panel_number is None or int(panel_number) not in panel_maps:
                    errors.append(f"aggregate control role lacks valid panel: {row.get('trial_id')}")
                    continue
                mapping = panel_maps[int(panel_number)]
            expected_ids = [mapping[int(target)] for target in block["target_feature_ids"]]
            expected_targets = [int(target) for target in block["target_feature_ids"]]
            observed_ids = [int(item["feature_id"]) for item in row["interventions"]]
            observed_targets = [int(item["matched_target_id"]) for item in row["interventions"]]
            if observed_ids != expected_ids or observed_targets != expected_targets:
                errors.append(f"aggregate intervention mapping differs from block: {row.get('trial_id')}")
            expected_sign = -1.0 if row["sign"] == "suppression" else 1.0
            observed_base = [float(item["base_coefficient"]) for item in row["interventions"]]
            expected_base = [
                round(expected_sign * float(value), 3) for value in block["magnitudes"]
            ]
            if observed_base != expected_base:
                errors.append(f"aggregate base coefficients differ from block: {row.get('trial_id')}")
    for key, signs in aggregate_groups.items():
        if set(signs) != {"suppression", "amplification"}:
            errors.append(f"aggregate pair is incomplete: {key}")
            continue
        if not _sign_flip_ok(signs["suppression"], signs["amplification"]):
            errors.append(f"aggregate pair does not preserve exact sign flip: {key}")
        if signs["suppression"]["seed"] != signs["amplification"]["seed"]:
            errors.append(f"aggregate pair seed mismatch: {key}")
    if len(aggregate_groups) != 300:
        errors.append(f"expected 300 aggregate role-block groups, got {len(aggregate_groups)}")

    literal_roles = Counter(
        row["analysis_role"] for row in rows if row.get("phase") == "aggregate_literal"
    )
    if literal_roles != Counter(
        {"target": 100, "control_panel_1": 100, "control_panel_2": 100, "control_panel_3": 100}
    ):
        errors.append(f"literal aggregate roles differ: {literal_roles}")
    calibrated_roles = Counter(
        row["analysis_role"] for row in rows if row.get("phase") == "aggregate_calibrated"
    )
    if calibrated_roles != Counter({"target": 100, "control_panel_1": 100}):
        errors.append(f"calibrated aggregate roles differ: {calibrated_roles}")

    return {
        "status": "pass" if not errors else "fail",
        "mode": "final",
        "errors": errors,
        "checks": {
            "n_trials": len(rows),
            "phase_counts": dict(sorted(phase_counts.items())),
            "n_unique_trial_ids": len(set(trial_ids)),
            "n_aggregate_role_blocks": len(aggregate_groups),
            "n_control_ids": len(set(controls)),
            "aggregate_blocks": block_checks,
        },
    }


def audit_plan(run_dir: Path) -> dict[str, Any]:
    if (run_dir / "PLAN_MANIFEST.json").exists():
        return audit_final(run_dir)
    return audit_precalibration(run_dir)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("--out", type=Path)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    report = audit_plan(args.run_dir)
    output = args.out or args.run_dir / "independent_plan_audit.json"
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Independent plan audit: {report['status'].upper()} -> {output}")
    if report["status"] != "pass":
        for error in report["errors"]:
            print(f"- {error}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()

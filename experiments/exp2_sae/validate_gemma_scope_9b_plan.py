#!/usr/bin/env python3
"""Independently validate the frozen Gemma Scope plan without production imports."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


EXPECTED_MODEL = "google/gemma-2-9b-it"
EXPECTED_MODEL_REVISION = "11c9b309abf73637e4b6f9a3fa1e92e615547819"
EXPECTED_IT_REVISION = "e86af97a5b6fbbccca28ab654f2fda1b0768f770"
EXPECTED_PT_REVISION = "f9b689815814972562d28082f9f7d65d7e01fdc8"
EXPECTED_ATT_REVISION = "480f21407fd8053280724f0a4be3ccee7c155ef7"
EXPECTED_MLP_REVISION = "721f47c902e0956ad65d5a391a9ce0c36e02e849"
EXPECTED_ANCHORS = {9, 20, 31}
EXPECTED_WIDTHS = {16_384, 131_072}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def validate(plan_dir: Path) -> dict[str, Any]:
    errors: list[str] = []
    required = {
        "baseline_plan.jsonl",
        "ATLAS_PLAN.json",
        "STEERING_TEMPLATE.json",
        "PLAN_SUMMARY.json",
        "PLAN_MANIFEST.json",
    }
    missing = sorted(name for name in required if not (plan_dir / name).is_file())
    if missing:
        return {"status": "fail", "errors": [f"missing files: {missing}"]}

    baseline = read_jsonl(plan_dir / "baseline_plan.jsonl")
    if len(baseline) != 180:
        errors.append(f"baseline row count is {len(baseline)}, expected 180")
    ids = [row.get("trial_id") for row in baseline]
    if len(set(ids)) != len(ids) or None in ids:
        errors.append("baseline trial IDs are missing or duplicated")
    orders = sorted(int(row.get("execution_order", -1)) for row in baseline)
    if orders != list(range(180)):
        errors.append("baseline execution order is not exactly 0..179")
    design_counts = Counter(row.get("design") for row in baseline)
    if design_counts != Counter({"paper_exact": 100, "orthogonal_factorial": 80}):
        errors.append(f"baseline design counts differ: {design_counts}")
    paper = [row for row in baseline if row.get("design") == "paper_exact"]
    if Counter(row.get("condition") for row in paper) != Counter(
        {"paper_self_ref": 50, "paper_history": 50}
    ):
        errors.append("paper baseline conditions are not 50/50")
    factorial = [
        row for row in baseline if row.get("design") == "orthogonal_factorial"
    ]
    if Counter(row.get("condition") for row in factorial) != Counter(
        {
            "self_phenomenological": 20,
            "self_analytic": 20,
            "external_phenomenological": 20,
            "external_analytic": 20,
        }
    ):
        errors.append("factorial cells are not 20 each")
    by_cell_variant: dict[str, Counter[int]] = defaultdict(Counter)
    for row in factorial:
        by_cell_variant[str(row["condition"])][int(row["variant_index"])] += 1
    if any(counter != Counter({1: 5, 2: 5, 3: 5, 4: 5}) for counter in by_cell_variant.values()):
        errors.append("factorial variants are not five replicates each")
    if len({int(row["seed"]) for row in baseline}) != len(baseline):
        errors.append("baseline seeds are not unique")
    if any(row.get("temperature") != 0.5 for row in baseline):
        errors.append("one or more baseline temperatures differ from 0.5")
    if any(row.get("induction_max_tokens") != 256 for row in baseline):
        errors.append("one or more induction caps differ from 256")
    if any(row.get("final_max_tokens") != 256 for row in baseline):
        errors.append("one or more final caps differ from 256")

    atlas = json.loads((plan_dir / "ATLAS_PLAN.json").read_text(encoding="utf-8"))
    if atlas.get("model") != EXPECTED_MODEL:
        errors.append("atlas model differs")
    if atlas.get("model_revision") != EXPECTED_MODEL_REVISION:
        errors.append("atlas model revision differs")
    direct = atlas.get("direct_it_saes", [])
    direct_pairs = {(int(row["layer"]), int(row["width"])) for row in direct}
    if direct_pairs != {(layer, width) for layer in EXPECTED_ANCHORS for width in EXPECTED_WIDTHS}:
        errors.append("direct IT SAE layer/width grid differs")
    if any(row.get("revision") != EXPECTED_IT_REVISION for row in direct):
        errors.append("direct IT SAE revision differs")
    pt = atlas.get("pt_residual_saes", [])
    if len(pt) != 42 or {int(row["layer"]) for row in pt} != set(range(42)):
        errors.append("PT residual grid is not all 42 layers")
    if any(row.get("revision") != EXPECTED_PT_REVISION for row in pt):
        errors.append("PT residual SAE revision differs")
    sublayer_repos = atlas.get("targeted_sublayer_repositories", {})
    if sublayer_repos.get("attention", {}).get("revision") != EXPECTED_ATT_REVISION:
        errors.append("PT attention SAE revision differs")
    if sublayer_repos.get("mlp", {}).get("revision") != EXPECTED_MLP_REVISION:
        errors.append("PT MLP SAE revision differs")
    if atlas.get("selection", {}).get("candidate_count_per_construct") != 64:
        errors.append("candidate count differs from 64")
    if atlas.get("selection", {}).get("selected_count_per_construct") != 6:
        errors.append("selected feature count differs from six")
    corpora = atlas.get("corpora", [])
    if len(corpora) != 2:
        errors.append("atlas must bind exactly two corpus files")
    for corpus in corpora:
        path = plan_dir.parents[2] / corpus.get("path", "")
        if not path.is_file() or sha256_file(path) != corpus.get("sha256"):
            errors.append(f"corpus hash differs: {corpus.get('path')}")

    template = json.loads(
        (plan_dir / "STEERING_TEMPLATE.json").read_text(encoding="utf-8")
    )
    primary = template.get("primary", {})
    if (primary.get("layer"), primary.get("width")) != (20, 131_072):
        errors.append("primary causal site differs from layer 20 / 131k")
    if primary.get("paired_blocks_per_role") != 50 or primary.get("zero_blocks") != 50:
        errors.append("primary block counts differ")
    if template.get("expected_trial_count") != 830:
        errors.append("future steering row count differs from 830")
    outcome = template.get("outcome", {})
    if outcome.get("minimum_relevant_effect") != 0.30:
        errors.append("minimum relevant effect differs from 0.30")
    intervention = template.get("intervention", {})
    if intervention.get("true_zero_required") is not True:
        errors.append("true zero is not required")
    if intervention.get("both_turns") is not True:
        errors.append("both-turn intervention is not required")

    manifest = json.loads(
        (plan_dir / "PLAN_MANIFEST.json").read_text(encoding="utf-8")
    )
    listed = {entry["path"]: entry for entry in manifest.get("files", [])}
    for name in required - {"PLAN_MANIFEST.json"}:
        path = plan_dir / name
        record = listed.get(name)
        if record is None:
            errors.append(f"manifest omits {name}")
        elif record.get("sha256") != sha256_file(path) or record.get("bytes") != path.stat().st_size:
            errors.append(f"manifest record differs for {name}")

    return {
        "status": "pass" if not errors else "fail",
        "audited_at_utc": datetime.now(timezone.utc).isoformat(),
        "errors": errors,
        "baseline_rows": len(baseline),
        "baseline_unique_ids": len(set(ids)),
        "direct_it_saes": len(direct),
        "pt_residual_saes": len(pt),
        "future_steering_rows": template.get("expected_trial_count"),
        "behavioral_outcomes_read": False,
        "production_module_imported": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("plan_dir", type=Path)
    args = parser.parse_args()
    result = validate(args.plan_dir.resolve())
    output = args.plan_dir.resolve() / "independent_plan_audit.json"
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    lock = {
        "status": "locked" if result["status"] == "pass" else "invalid",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "baseline_plan_sha256": sha256_file(args.plan_dir.resolve() / "baseline_plan.jsonl"),
        "atlas_plan_sha256": sha256_file(args.plan_dir.resolve() / "ATLAS_PLAN.json"),
        "steering_template_sha256": sha256_file(
            args.plan_dir.resolve() / "STEERING_TEMPLATE.json"
        ),
        "plan_manifest_sha256": sha256_file(
            args.plan_dir.resolve() / "PLAN_MANIFEST.json"
        ),
        "independent_plan_audit_sha256": sha256_file(output),
        "behavioral_outcomes_exist": False,
    }
    (args.plan_dir.resolve() / "PLAN_LOCK.json").write_text(
        json.dumps(lock, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(f"Independent Gemma plan audit: {result['status'].upper()} -> {output}")
    if result["status"] != "pass":
        raise SystemExit(2)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Independently reconstruct and validate the frozen SAE/J-lens plan."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from experiments.exp2_sae.sae_jlens_protocol import (  # noqa: E402
    PROTOCOL_VERSION,
    build_paired_plan,
    read_jsonl,
    select_template_prompts,
    sha256_file,
    static_direction_plan,
    write_json,
)


DEFAULT_PLAN_DIR = REPO_ROOT / "data/sae_jlens_audit/confirmatory_v1_plan_20260711"


def validate(plan_dir: Path) -> dict[str, Any]:
    errors: list[str] = []
    manifest = json.loads((plan_dir / "PLAN_MANIFEST.json").read_text(encoding="utf-8"))
    for record in manifest.get("files", []):
        path = plan_dir / record["path"]
        if not path.is_file():
            errors.append(f"missing plan file: {record['path']}")
        elif sha256_file(path) != record["sha256"]:
            errors.append(f"plan hash mismatch: {record['path']}")
    for record in manifest.get("source_files", []):
        path = REPO_ROOT / record["path"]
        if not path.is_file():
            errors.append(f"missing source file: {record['path']}")
        elif sha256_file(path) != record["sha256"]:
            errors.append(f"source hash mismatch: {record['path']}")

    emitted_prompts = read_jsonl(plan_dir / "prompt_plan.jsonl")
    emitted_static = read_jsonl(plan_dir / "static_direction_plan.jsonl")
    emitted_paired = read_jsonl(plan_dir / "paired_plan.jsonl")
    reconstructed_prompts = select_template_prompts(REPO_ROOT)
    reconstructed_static = static_direction_plan()
    reconstructed_paired = build_paired_plan(REPO_ROOT)
    if emitted_prompts != reconstructed_prompts:
        errors.append("emitted prompt plan differs from independent reconstruction")
    if emitted_static != reconstructed_static:
        errors.append("emitted static plan differs from independent reconstruction")
    if emitted_paired != reconstructed_paired:
        errors.append("emitted paired plan differs from independent reconstruction")

    snapshot = json.loads((plan_dir / "protocol_snapshot.json").read_text(encoding="utf-8"))
    if snapshot.get("protocol_version") != PROTOCOL_VERSION:
        errors.append("snapshot protocol version differs")
    if snapshot.get("status") != "frozen_outcome_blind_plan":
        errors.append("snapshot is not marked outcome-blind")
    if snapshot.get("design", {}).get("n_paired_trials") != 1581:
        errors.append("snapshot paired count differs")
    if len({row["trial_id"] for row in emitted_paired}) != len(emitted_paired):
        errors.append("paired trial IDs are not unique")
    if sorted(row["execution_order"] for row in emitted_paired) != list(
        range(len(emitted_paired))
    ):
        errors.append("paired execution order is not a complete permutation")

    forbidden_keys = {
        "response",
        "generation",
        "label",
        "prediction",
        "logit",
        "activation",
        "auroc",
        "effect",
        "result",
    }
    for row in emitted_paired:
        overlap = forbidden_keys & set(row)
        if overlap:
            errors.append(
                f"paired plan contains result-like keys for {row['trial_id']}: {sorted(overlap)}"
            )
            break

    return {
        "status": "pass" if not errors else "fail",
        "protocol_version": PROTOCOL_VERSION,
        "plan_manifest_sha256": sha256_file(plan_dir / "PLAN_MANIFEST.json"),
        "n_prompts": len(emitted_prompts),
        "n_static_directions": len(emitted_static),
        "n_paired_trials": len(emitted_paired),
        "n_errors": len(errors),
        "errors": errors,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan-dir", type=Path, default=DEFAULT_PLAN_DIR)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    result = validate(args.plan_dir.resolve())
    if args.out:
        write_json(args.out.resolve(), result)
    print(json.dumps(result, indent=2, sort_keys=True))
    if result["status"] != "pass":
        raise SystemExit(1)


if __name__ == "__main__":
    main()

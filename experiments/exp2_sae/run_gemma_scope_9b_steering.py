#!/usr/bin/env python3
"""Execute the independently audited 830-row Gemma causal steering plan."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from experiments.exp2_sae.gemma_scope_9b_protocol import (  # noqa: E402
    IT_CANONICAL_FOLDERS,
    IT_SAE_REPO,
    IT_SAE_REVISION,
    MODEL_ID,
    MODEL_REVISION,
    PROTOCOL_VERSION,
    sha256_file,
)
from experiments.exp2_sae.gemma_scope_9b_runtime import (  # noqa: E402
    PinnedJumpReLUSAE,
    append_jsonl,
    load_model_and_tokenizer,
    read_jsonl,
    release_memory,
    run_two_turn,
    runtime_metadata,
    utc_now,
    validate_steering_diagnostics,
    write_json,
)


def load_saes() -> dict[str, PinnedJumpReLUSAE]:
    result = {}
    for layer, width in ((9, 131_072), (20, 131_072), (31, 131_072), (20, 16_384)):
        key = f"it_res_l{layer}_w{width}"
        result[key] = PinnedJumpReLUSAE.load(
            repo_id=IT_SAE_REPO,
            revision=IT_SAE_REVISION,
            folder=IT_CANONICAL_FOLDERS[(layer, width)],
            dtype_name="bfloat16",
        )
    return result


def intervention_for(
    row: dict[str, Any],
    saes: dict[str, PinnedJumpReLUSAE],
    feature_manifest: dict[str, Any],
) -> dict[str, Any]:
    layer = int(row["layer"])
    key = str(row["sae_key"])
    downstream = []
    if layer < 20:
        relay_key = "it_res_l20_w131072"
        downstream.append(
            (
                20,
                saes[relay_key],
                [
                    int(value)
                    for value in feature_manifest["feature_sets"][relay_key][
                        "deception_roleplay"
                    ]
                ],
                [
                    float(
                        feature_manifest["active_q90_by_sae_and_feature"][relay_key][
                            str(value)
                        ]
                    )
                    for value in feature_manifest["feature_sets"][relay_key][
                        "deception_roleplay"
                    ]
                ],
            )
        )
    if layer < 31:
        relay_key = "it_res_l31_w131072"
        downstream.append(
            (
                31,
                saes[relay_key],
                [
                    int(value)
                    for value in feature_manifest["feature_sets"][relay_key][
                        "deception_roleplay"
                    ]
                ],
                [
                    float(
                        feature_manifest["active_q90_by_sae_and_feature"][relay_key][
                            str(value)
                        ]
                    )
                    for value in feature_manifest["feature_sets"][relay_key][
                        "deception_roleplay"
                    ]
                ],
            )
        )
    return {
        "sae": saes[key],
        "layer": layer,
        "feature_ids": [int(value) for value in row["feature_ids"]],
        "active_q90": [float(value) for value in row["active_q90"]],
        "sign": str(row["sign"]),
        "alpha": float(row["calibration_alpha"]),
        "downstream": downstream,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan-dir", type=Path, required=True)
    parser.add_argument("--outdir", type=Path, required=True)
    args = parser.parse_args()
    plan_dir = args.plan_dir.resolve()
    outdir = args.outdir.resolve()
    plan_path = plan_dir / "steering_plan.jsonl"
    audit_path = plan_dir / "independent_plan_audit.json"
    manifest_path = plan_dir / "PLAN_MANIFEST.json"
    feature_path = plan_dir / "FEATURE_MANIFEST.json"
    lock_path = plan_dir / "PLAN_LOCK.json"
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    if audit.get("status") != "pass" or audit.get("behavioral_outcomes_read") is not False:
        raise RuntimeError("Independent final steering plan audit did not pass")
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    if lock.get("status") != "locked":
        raise RuntimeError("Final steering plan lock is not valid")
    for field, path in (
        ("steering_plan_sha256", plan_path),
        ("feature_manifest_sha256", feature_path),
        ("calibration_sha256", plan_dir / "CALIBRATION.json"),
        ("transfer_gate_sha256", plan_dir / "TRANSFER_GATE.json"),
        ("plan_summary_sha256", plan_dir / "PLAN_SUMMARY.json"),
        ("plan_manifest_sha256", manifest_path),
        ("independent_plan_audit_sha256", audit_path),
    ):
        if lock.get(field) != sha256_file(path):
            raise RuntimeError(f"Final steering plan lock differs: {field}")
    plan = sorted(read_jsonl(plan_path), key=lambda row: int(row["execution_order"]))
    if len(plan) != 830 or len({row["trial_id"] for row in plan}) != 830:
        raise RuntimeError("Final Gemma steering plan is not 830 unique rows")
    plan_hash = sha256_file(plan_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    listed = {record["path"]: record for record in manifest["files"]}
    if listed.get("steering_plan.jsonl", {}).get("sha256") != plan_hash:
        raise RuntimeError("Final plan hash differs from PLAN_MANIFEST")
    feature_manifest = json.loads(feature_path.read_text(encoding="utf-8"))

    outdir.mkdir(parents=True, exist_ok=True)
    plan_copy = outdir / "plan"
    plan_copy.mkdir(exist_ok=True)
    for path in plan_dir.iterdir():
        if path.is_file():
            shutil.copy2(path, plan_copy / path.name)
    results_path = outdir / "steering_generations.jsonl"
    errors_path = outdir / "steering_generation_errors.jsonl"
    existing = read_jsonl(results_path)
    completed = {str(row["trial_id"]) for row in existing}
    if len(completed) != len(existing):
        raise RuntimeError("Existing steering generations contain duplicate trial IDs")
    if any(row.get("plan_sha256") != plan_hash for row in existing):
        raise RuntimeError("Existing steering generations have a different plan hash")

    torch_module, model, tokenizer = load_model_and_tokenizer(MODEL_ID, MODEL_REVISION)
    saes = load_saes()
    try:
        write_json(
            outdir / "STEERING_RUN_MANIFEST.json",
            {
                "status": "running",
                "started_at_utc": utc_now(),
                "protocol_version": PROTOCOL_VERSION,
                "plan_sha256": plan_hash,
                "plan_manifest_sha256": sha256_file(manifest_path),
                "plan_audit_sha256": sha256_file(audit_path),
                "plan_lock_sha256": sha256_file(lock_path),
                "feature_manifest_sha256": sha256_file(feature_path),
                "n_planned": len(plan),
                "n_preexisting": len(completed),
                "model": MODEL_ID,
                "model_revision": MODEL_REVISION,
                "sae_repo": IT_SAE_REPO,
                "sae_revision": IT_SAE_REVISION,
                "saes": {key: sae.record() for key, sae in saes.items()},
                "behavioral_blinding": "No response text or interim label is printed during generation.",
                "runtime": runtime_metadata(torch_module),
            },
        )
        started = time.monotonic()
        for execution_index, row in enumerate(plan, 1):
            trial_id = str(row["trial_id"])
            if trial_id in completed:
                continue
            intervention = intervention_for(row, saes, feature_manifest)
            for attempt in range(1, 4):
                try:
                    conversation = run_two_turn(
                        torch_module=torch_module,
                        model=model,
                        tokenizer=tokenizer,
                        induction=str(row["induction"]),
                        query=str(row["query"]),
                        seed=int(row["seed"]),
                        temperature=float(row["temperature"]),
                        top_p=float(row["top_p"]),
                        induction_max_tokens=int(row["induction_max_tokens"]),
                        final_max_tokens=int(row["final_max_tokens"]),
                        intervention=intervention,
                    )
                    expect_zero = row["sign"] == "zero"
                    validate_steering_diagnostics(
                        conversation["induction_diagnostics"], expect_zero
                    )
                    validate_steering_diagnostics(
                        conversation["final_diagnostics"], expect_zero
                    )
                    append_jsonl(
                        results_path,
                        {
                            **row,
                            **conversation,
                            "plan_sha256": plan_hash,
                            "attempt": attempt,
                            "completed_at_utc": utc_now(),
                        },
                    )
                    completed.add(trial_id)
                    break
                except Exception as error:
                    append_jsonl(
                        errors_path,
                        {
                            "trial_id": trial_id,
                            "attempt": attempt,
                            "error_type": type(error).__name__,
                            "error": str(error),
                            "failed_at_utc": utc_now(),
                        },
                    )
                    if attempt == 3:
                        raise
                    time.sleep(2**attempt)
            if len(completed) % 10 == 0 or execution_index == len(plan):
                elapsed = (time.monotonic() - started) / 3600
                print(
                    f"Gemma steering progress: {len(completed)}/{len(plan)}; elapsed={elapsed:.2f}h",
                    flush=True,
                )

        rows = read_jsonl(results_path)
        if len(rows) != len(plan) or {row["trial_id"] for row in rows} != {
            row["trial_id"] for row in plan
        }:
            raise RuntimeError("Steering generations do not exactly match the final plan")
        nonzero = [row for row in rows if row["sign"] != "zero"]
        relative_values = [
            float(row[turn]["relative_hidden_delta_rms"])
            for row in nonzero
            for turn in ("induction_diagnostics", "final_diagnostics")
        ]
        complete_path = outdir / "steering_complete.json"
        write_json(
            complete_path,
            {
                "status": "steering_generation_complete_unjudged",
                "completed_at_utc": utc_now(),
                "n_rows": len(rows),
                "n_unique_trial_ids": len({row["trial_id"] for row in rows}),
                "plan_sha256": plan_hash,
                "generations_sha256": sha256_file(results_path),
                "induction_cap_hits": sum(bool(row["induction_cap_hit"]) for row in rows),
                "final_cap_hits": sum(bool(row["final_cap_hit"]) for row in rows),
                "empty_inductions": sum(not str(row["induction_response"]).strip() for row in rows),
                "empty_finals": sum(not str(row["response"]).strip() for row in rows),
                "zero_nonzero_delta_count": sum(
                    float(row[turn]["relative_hidden_delta_rms"]) != 0.0
                    for row in rows
                    if row["sign"] == "zero"
                    for turn in ("induction_diagnostics", "final_diagnostics")
                ),
                "nonzero_zero_effect_turns": sum(value == 0.0 for value in relative_values),
                "max_relative_hidden_delta_rms": max(relative_values, default=0.0),
                "behavioral_outcomes_inspected": False,
                "runtime": runtime_metadata(torch_module),
            },
        )
        run_manifest_path = outdir / "STEERING_RUN_MANIFEST.json"
        run_manifest = json.loads(run_manifest_path.read_text(encoding="utf-8"))
        run_manifest.update(
            {
                "status": "complete",
                "completed_at_utc": utc_now(),
                "generations_sha256": sha256_file(results_path),
                "completion_sha256": sha256_file(complete_path),
            }
        )
        write_json(run_manifest_path, run_manifest)
        print(f"Gemma steering complete and unjudged -> {outdir}", flush=True)
    finally:
        release_memory(*saes.values())


if __name__ == "__main__":
    main()

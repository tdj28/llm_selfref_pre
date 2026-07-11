#!/usr/bin/env python3
"""Execute the frozen 180-row unsteered Gemma behavioral baseline."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from experiments.exp2_sae.gemma_scope_9b_protocol import (  # noqa: E402
    MODEL_ID,
    MODEL_REVISION,
    PROTOCOL_VERSION,
    sha256_file,
)
from experiments.exp2_sae.gemma_scope_9b_runtime import (  # noqa: E402
    append_jsonl,
    load_model_and_tokenizer,
    read_jsonl,
    run_two_turn,
    runtime_metadata,
    utc_now,
    write_json,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan-dir", type=Path, required=True)
    parser.add_argument("--outdir", type=Path, required=True)
    args = parser.parse_args()
    plan_dir = args.plan_dir.resolve()
    outdir = args.outdir.resolve()
    plan_path = plan_dir / "baseline_plan.jsonl"
    audit_path = plan_dir / "independent_plan_audit.json"
    manifest_path = plan_dir / "PLAN_MANIFEST.json"
    lock_path = plan_dir / "PLAN_LOCK.json"
    for path in (plan_path, audit_path, manifest_path, lock_path):
        if not path.is_file():
            raise FileNotFoundError(path)
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    if audit.get("status") != "pass" or audit.get("behavioral_outcomes_read") is not False:
        raise RuntimeError("Independent outcome-free plan audit did not pass")
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    if lock.get("status") != "locked":
        raise RuntimeError("Outcome-free plan lock is not valid")
    for field, path in (
        ("baseline_plan_sha256", plan_path),
        ("atlas_plan_sha256", plan_dir / "ATLAS_PLAN.json"),
        ("steering_template_sha256", plan_dir / "STEERING_TEMPLATE.json"),
        ("plan_manifest_sha256", manifest_path),
        ("independent_plan_audit_sha256", audit_path),
    ):
        if lock.get(field) != sha256_file(path):
            raise RuntimeError(f"Outcome-free plan lock differs: {field}")
    plan = sorted(read_jsonl(plan_path), key=lambda row: int(row["execution_order"]))
    if len(plan) != 180 or len({row["trial_id"] for row in plan}) != 180:
        raise RuntimeError("Frozen baseline plan is not 180 unique rows")
    plan_hash = sha256_file(plan_path)

    outdir.mkdir(parents=True, exist_ok=True)
    plan_copy_dir = outdir / "plan"
    plan_copy_dir.mkdir(exist_ok=True)
    for path in plan_dir.iterdir():
        if path.is_file():
            shutil.copy2(path, plan_copy_dir / path.name)
    results_path = outdir / "baseline_generations.jsonl"
    errors_path = outdir / "baseline_generation_errors.jsonl"
    existing = read_jsonl(results_path)
    completed = {str(row["trial_id"]) for row in existing}
    if len(completed) != len(existing):
        raise RuntimeError("Existing baseline output has duplicate trial IDs")
    if any(row.get("plan_sha256") != plan_hash for row in existing):
        raise RuntimeError("Existing baseline output has a different plan hash")

    torch_module, model, tokenizer = load_model_and_tokenizer(MODEL_ID, MODEL_REVISION)
    write_json(
        outdir / "BASELINE_RUN_MANIFEST.json",
        {
            "status": "running",
            "started_at_utc": utc_now(),
            "protocol_version": PROTOCOL_VERSION,
            "plan_sha256": plan_hash,
            "plan_audit_sha256": sha256_file(audit_path),
            "plan_lock_sha256": sha256_file(lock_path),
            "model": MODEL_ID,
            "model_revision": MODEL_REVISION,
            "n_planned": len(plan),
            "n_preexisting": len(completed),
            "behavioral_blinding": "No response text or label is printed during generation.",
            "runtime": runtime_metadata(torch_module),
        },
    )
    started = time.monotonic()
    for execution_index, row in enumerate(plan, 1):
        trial_id = str(row["trial_id"])
        if trial_id in completed:
            continue
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
                f"Gemma baseline progress: {len(completed)}/{len(plan)}; elapsed={elapsed:.2f}h",
                flush=True,
            )

    rows = read_jsonl(results_path)
    if len(rows) != 180 or {row["trial_id"] for row in rows} != {
        row["trial_id"] for row in plan
    }:
        raise RuntimeError("Baseline generations do not exactly match the frozen plan")
    complete_path = outdir / "baseline_complete.json"
    write_json(
        complete_path,
        {
            "status": "baseline_generation_complete_unjudged",
            "completed_at_utc": utc_now(),
            "n_rows": len(rows),
            "n_unique_trial_ids": len({row["trial_id"] for row in rows}),
            "plan_sha256": plan_hash,
            "generations_sha256": sha256_file(results_path),
            "induction_cap_hits": sum(bool(row["induction_cap_hit"]) for row in rows),
            "final_cap_hits": sum(bool(row["final_cap_hit"]) for row in rows),
            "empty_inductions": sum(not str(row["induction_response"]).strip() for row in rows),
            "empty_finals": sum(not str(row["response"]).strip() for row in rows),
            "behavioral_outcomes_inspected": False,
            "runtime": runtime_metadata(torch_module),
        },
    )
    run_manifest_path = outdir / "BASELINE_RUN_MANIFEST.json"
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
    print(f"Gemma baseline complete and unjudged -> {outdir}", flush=True)


if __name__ == "__main__":
    main()

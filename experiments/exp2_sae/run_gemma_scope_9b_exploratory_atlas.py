#!/usr/bin/env python3
"""Map a clearly post-gate exploratory PT layer atlas after transfer failure."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from experiments.exp2_sae.gemma_scope_9b_protocol import (  # noqa: E402
    ANCHOR_LAYERS,
    MODEL_ID,
    MODEL_REVISION,
    PROTOCOL_VERSION,
    sha256_file,
)
from experiments.exp2_sae.gemma_scope_9b_runtime import (  # noqa: E402
    load_model_and_tokenizer,
    runtime_metadata,
    utc_now,
    write_json,
)
from experiments.exp2_sae.run_gemma_scope_9b_atlas import (  # noqa: E402
    DEFAULT_BATCH_SIZE,
    GROUP_SIZE,
    build_sublayer_specs,
    chunked,
    load_rows,
    map_group,
    spec_key,
    transition_layers,
)


EXPLORATORY_VERSION = "gemma_scope_9b_post_transfer_failure_exploratory_v1"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan-dir", type=Path, required=True)
    parser.add_argument("--confirmatory-atlas", type=Path, required=True)
    parser.add_argument("--outdir", type=Path, required=True)
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE)
    args = parser.parse_args()
    plan_dir = args.plan_dir.resolve()
    confirmatory = args.confirmatory_atlas.resolve()
    outdir = args.outdir.resolve()
    atlas_plan_path = plan_dir / "ATLAS_PLAN.json"
    atlas_plan = json.loads(atlas_plan_path.read_text(encoding="utf-8"))
    transfer_path = confirmatory / "transfer_gate.json"
    transfer = json.loads(transfer_path.read_text(encoding="utf-8"))
    if transfer.get("status") != "fail":
        raise RuntimeError("Exploratory continuation requires the recorded gate failure")
    if transfer.get("checks", {}).get("median_category_profile_spearman") is not True:
        raise RuntimeError("Exploratory rationale requires profile-correlation passage")
    if transfer.get("checks", {}).get("positive_deception_at_all_anchors") is not True:
        raise RuntimeError("Exploratory rationale requires positive anchor contrasts")

    rows = load_rows(atlas_plan)
    outdir.mkdir(parents=True, exist_ok=True)
    scratch_dir = outdir / "scratch_activation_matrices"
    scratch_dir.mkdir(exist_ok=True)
    (outdir / "plan").mkdir(exist_ok=True)
    for path in plan_dir.iterdir():
        if path.is_file():
            shutil.copy2(path, outdir / "plan" / path.name)
    write_json(
        outdir / "EXPLORATORY_RUN_MANIFEST.json",
        {
            "status": "running",
            "started_at_utc": utc_now(),
            "exploratory_version": EXPLORATORY_VERSION,
            "confirmatory_protocol_version": PROTOCOL_VERSION,
            "confirmatory_transfer_gate": "fail",
            "confirmatory_transfer_gate_sha256": sha256_file(transfer_path),
            "post_hoc_after_gate_failure": True,
            "behavioral_outcomes_used": False,
            "claim_boundary": (
                "Descriptive PT-on-IT layer localization only; excluded from the "
                "confirmatory transfer claim and behavioral verdict."
            ),
        },
    )

    pt_specs = atlas_plan["pt_residual_saes"]
    summaries = {}
    for spec in pt_specs:
        if int(spec["layer"]) not in ANCHOR_LAYERS:
            continue
        key = spec_key(spec)
        source = confirmatory / "saes" / key
        target = outdir / "saes" / key
        if not target.exists():
            shutil.copytree(source, target)
        summaries[key] = json.loads((target / "summary.json").read_text(encoding="utf-8"))

    torch_module, model, tokenizer = load_model_and_tokenizer(MODEL_ID, MODEL_REVISION)
    remaining = [spec for spec in pt_specs if int(spec["layer"]) not in ANCHOR_LAYERS]
    for group in chunked(remaining, GROUP_SIZE):
        summaries.update(
            map_group(
                torch_module=torch_module,
                model=model,
                tokenizer=tokenizer,
                rows=rows,
                specs=group,
                outdir=outdir,
                scratch_dir=scratch_dir,
                batch_size=args.batch_size,
            )
        )
    transition = transition_layers(summaries)
    write_json(outdir / "transition_selection.json", transition)
    sublayer_specs = build_sublayer_specs(transition["targeted_layers"])
    if sublayer_specs:
        summaries.update(
            map_group(
                torch_module=torch_module,
                model=model,
                tokenizer=tokenizer,
                rows=rows,
                specs=sublayer_specs,
                outdir=outdir,
                scratch_dir=scratch_dir,
                batch_size=args.batch_size,
            )
        )
    scratch_files = list(scratch_dir.glob("*"))
    if scratch_files:
        raise RuntimeError(f"Exploratory scratch matrices remain: {scratch_files}")
    scratch_dir.rmdir()
    complete_path = outdir / "exploratory_complete.json"
    write_json(
        complete_path,
        {
            "status": "complete",
            "completed_at_utc": utc_now(),
            "exploratory_version": EXPLORATORY_VERSION,
            "post_hoc_after_gate_failure": True,
            "confirmatory_transfer_gate": "fail",
            "pt_residual_layers_completed": sorted(
                int(spec["layer"])
                for spec in pt_specs
                if spec_key(spec) in summaries
            ),
            "pt_residual_sae_count": sum(key.startswith("pt_res_") for key in summaries),
            "targeted_sublayer_sae_count": len(sublayer_specs),
            "transition_selection": transition,
            "behavioral_outcomes_used": False,
            "claim_boundary": (
                "Exploratory descriptive atlas only; no confirmatory PT-to-IT, "
                "causal-relay, or behavioral inference."
            ),
            "runtime": runtime_metadata(torch_module),
        },
    )
    manifest_path = outdir / "EXPLORATORY_RUN_MANIFEST.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest.update(
        {
            "status": "complete",
            "completed_at_utc": utc_now(),
            "exploratory_complete_sha256": sha256_file(complete_path),
        }
    )
    write_json(manifest_path, manifest)
    print(f"Exploratory Gemma layer atlas complete -> {outdir}", flush=True)


if __name__ == "__main__":
    main()

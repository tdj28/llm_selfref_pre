#!/usr/bin/env python3
"""Run the frozen outcome-masked SAE/J-lens v2 semantic calibration."""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import os
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = Path(__file__).resolve().parent
for path in (REPO_ROOT, SCRIPT_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from experiments.exp2_sae.run_public_sae_consciousness_gating import (  # noqa: E402
    measure_calibration_metrics,
)
from experiments.exp2_sae.sae_jlens_v2_protocol import (  # noqa: E402
    CALIBRATION_PLAN_DIR,
    LEXICON_CANDIDATES,
    MODEL_ID,
    MODEL_REVISION,
    PROTOCOL_VERSION,
    SAE_FILE_SHA256,
    SAE_ID,
    SAE_REVISION,
    TARGET_FEATURE_IDS,
    match_semantic_features,
    read_jsonl,
    semantic_pool_sha256,
    sha256_file,
    write_json,
)


DEFAULT_PLAN_DIR = REPO_ROOT / CALIBRATION_PLAN_DIR


class ProtocolViolation(RuntimeError):
    """Fail-closed protocol error that must not trigger an improvised retry."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def git_head() -> str | None:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, text=True
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def runtime_metadata(torch_module: Any) -> dict[str, Any]:
    packages = {}
    for package in (
        "accelerate",
        "bitsandbytes",
        "huggingface-hub",
        "nnsight",
        "numpy",
        "torch",
        "transformers",
    ):
        try:
            packages[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            packages[package] = None
    return {
        "captured_at_utc": utc_now(),
        "git_commit": git_head(),
        "python": platform.python_version(),
        "platform": platform.platform(),
        "packages": packages,
        "cuda_available": bool(torch_module.cuda.is_available()),
        "cuda_runtime": torch_module.version.cuda,
        "gpu_count": torch_module.cuda.device_count(),
        "gpus": [
            {
                "index": index,
                "name": torch_module.cuda.get_device_name(index),
                "total_memory": torch_module.cuda.get_device_properties(index).total_memory,
            }
            for index in range(torch_module.cuda.device_count())
        ],
    }


def verify_plan(plan_dir: Path) -> dict[str, Any]:
    manifest_path = plan_dir / "PLAN_MANIFEST.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("status") != "frozen_outcome_masked_calibration_plan":
        raise ProtocolViolation("Calibration plan manifest has the wrong status")
    for record in manifest.get("files", []):
        path = plan_dir / record["path"]
        if not path.is_file() or sha256_file(path) != record["sha256"]:
            raise ProtocolViolation(f"Frozen calibration plan file differs: {path}")
    for record in manifest.get("source_files", []):
        path = REPO_ROOT / record["path"]
        if not path.is_file() or sha256_file(path) != record["sha256"]:
            raise ProtocolViolation(f"Frozen calibration source differs: {path}")
    audit = json.loads(
        (plan_dir / "INDEPENDENT_PLAN_AUDIT.json").read_text(encoding="utf-8")
    )
    if audit.get("status") != "pass":
        raise ProtocolViolation("Independent calibration-plan audit did not pass")
    if audit.get("plan_manifest_sha256") != sha256_file(manifest_path):
        raise ProtocolViolation("Plan audit references a different manifest")
    return manifest


def load_model_and_sae() -> tuple[Any, Any, Any, Any, Path]:
    import torch

    from replicate_exp2_goodfire_sae import (
        SAE_CONFIGS,
        ObservableLanguageModel,
        download_sae,
        load_sae,
        set_debug_memory,
    )

    if not torch.cuda.is_available():
        raise RuntimeError("CUDA is required for semantic calibration")
    if torch.cuda.device_count() != 1:
        raise ProtocolViolation("Stage 0 requires exactly one GPU")
    set_debug_memory(False)
    config = SAE_CONFIGS["70b"]
    if config.model_name != MODEL_ID or config.sae_repo != SAE_ID:
        raise ProtocolViolation("Runtime model/SAE configuration differs")
    model = ObservableLanguageModel(
        MODEL_ID,
        device="cuda",
        dtype=torch.bfloat16,
        load_in_4bit=True,
        revision=MODEL_REVISION,
    )
    resolved = getattr(model._model.config, "_commit_hash", None)
    if resolved is not None and resolved != MODEL_REVISION:
        raise ProtocolViolation(f"Resolved model revision differs: {resolved}")
    sae_path = Path(download_sae(config, revision=SAE_REVISION))
    if sha256_file(sae_path) != SAE_FILE_SHA256:
        raise ProtocolViolation("Downloaded SAE hash differs")
    sae = load_sae(
        sae_path,
        d_model=model.d_model,
        expansion_factor=config.expansion_factor,
        device=torch.device("cuda"),
        dtype=torch.bfloat16,
    )
    return torch, model, sae, config, sae_path


def build_lexicon(tokenizer: Any) -> dict[str, Any]:
    accepted: dict[str, list[dict[str, Any]]] = {}
    rejected: dict[str, list[dict[str, Any]]] = {}
    used_token_ids: dict[int, str] = {}
    for family, candidates in LEXICON_CANDIDATES.items():
        accepted[family] = []
        rejected[family] = []
        for candidate in candidates:
            token_ids = tokenizer(candidate, add_special_tokens=False)["input_ids"]
            decoded = (
                tokenizer.decode(token_ids, clean_up_tokenization_spaces=False)
                if token_ids
                else ""
            )
            row = {
                "candidate": candidate,
                "token_ids": [int(value) for value in token_ids],
                "decoded": decoded,
            }
            if len(token_ids) == 1 and decoded == candidate:
                token_id = int(token_ids[0])
                if token_id in used_token_ids:
                    raise ProtocolViolation(
                        f"Lexicon token {token_id} overlaps {used_token_ids[token_id]} and {family}"
                    )
                used_token_ids[token_id] = family
                accepted[family].append({**row, "token_id": token_id})
            else:
                rejected[family].append(row)
        if len(accepted[family]) < 5:
            raise ProtocolViolation(
                f"Lexicon {family} has only {len(accepted[family])} exact tokens"
            )
    return {"accepted": accepted, "rejected": rejected}


def run(plan_dir: Path, output: Path) -> None:
    manifest = verify_plan(plan_dir)
    candidates = read_jsonl(plan_dir / "semantic_candidate_pool.jsonl")
    snapshot = json.loads(
        (plan_dir / "protocol_snapshot.json").read_text(encoding="utf-8")
    )
    if semantic_pool_sha256(candidates) != snapshot["candidate_pool"]["sha256"]:
        raise ProtocolViolation("Semantic candidate pool hash differs")
    candidate_ids = [int(row["feature_id"]) for row in candidates]

    torch_module, model, sae, config, sae_path = load_model_and_sae()
    lexicon = build_lexicon(model.tokenizer)
    feature_metrics, hidden_rms = measure_calibration_metrics(
        torch_module, model, sae, config, candidate_ids
    )
    matching = match_semantic_features(feature_metrics, candidates)
    selected = matching["selected"]
    if len(selected) != 24 or len({row["feature_id"] for row in selected}) != 24:
        raise ProtocolViolation("Semantic calibration did not select 24 unique features")

    payload = {
        "status": "pass",
        "protocol_version": PROTOCOL_VERSION,
        "completed_at_utc": utc_now(),
        "plan_manifest_sha256": sha256_file(plan_dir / "PLAN_MANIFEST.json"),
        "plan_audit_sha256": sha256_file(plan_dir / "INDEPENDENT_PLAN_AUDIT.json"),
        "candidate_pool_sha256": semantic_pool_sha256(candidates),
        "model": MODEL_ID,
        "model_revision": MODEL_REVISION,
        "model_quantization": "bitsandbytes_nf4",
        "sae": SAE_ID,
        "sae_revision": SAE_REVISION,
        "sae_file_sha256": sha256_file(sae_path),
        "target_feature_ids": list(TARGET_FEATURE_IDS),
        "feature_metrics": feature_metrics,
        "hidden_rms_by_prompt": hidden_rms,
        "semantic_matching": matching,
        "lexicon_tokens": lexicon,
        "runtime": runtime_metadata(torch_module),
        "behavioral_outputs_generated": False,
        "jacobian_lens_loaded": False,
        "claim_boundary": snapshot["claim_boundary"],
        "frozen_manifest_status": manifest["status"],
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".tmp")
    write_json(temporary, payload)
    os.replace(temporary, output)
    print(
        json.dumps(
            {
                "status": "pass",
                "output": str(output),
                "metric_rows": len(feature_metrics),
                "selected_rows": len(selected),
            },
            sort_keys=True,
        )
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan-dir", type=Path, default=DEFAULT_PLAN_DIR)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    run(args.plan_dir.resolve(), args.output.resolve())


if __name__ == "__main__":
    main()

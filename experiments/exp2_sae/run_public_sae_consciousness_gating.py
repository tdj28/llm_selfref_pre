#!/usr/bin/env python3
"""Calibrate or execute the frozen public-SAE consciousness-gating plan."""

from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.metadata
import json
import math
import os
import platform
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = Path(__file__).resolve().parent
for path in (REPO_ROOT, SCRIPT_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from experiments.exp2_sae.public_sae_consciousness_gating import (  # noqa: E402
    BINARY_CONSCIOUS_QUERY,
    CALIBRATION_PROMPTS,
    FINAL_MAX_TOKENS,
    HOOK_LAYER,
    INDUCTION_MAX_TOKENS,
    MODEL_ID,
    MODEL_REVISION,
    PROTOCOL_VERSION,
    SAE_ID,
    SAE_REVISION,
    SELF_REF_INDUCTION,
    TARGET_FEATURE_IDS,
    build_aggregate_blocks,
    candidate_pool_sha256,
    compute_calibrated_multiplier,
    match_control_panels,
    read_jsonl,
    sha256_file,
    sha256_text,
    utc_now,
    write_json,
)


class ProtocolViolation(RuntimeError):
    """A fail-closed protocol error that must not be retried as a transient job."""


def append_jsonl(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def load_candidate_ids(path: Path) -> list[int]:
    with path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    orders = [int(row["candidate_order"]) for row in rows]
    if orders != list(range(len(rows))):
        raise ValueError("Candidate pool order is not contiguous")
    return [int(row["feature_id"]) for row in rows]


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
        "python": platform.python_version(),
        "platform": platform.platform(),
        "packages": packages,
        "cuda_available": bool(torch_module.cuda.is_available()),
        "cuda_runtime": torch_module.version.cuda,
        "gpu": (
            torch_module.cuda.get_device_name(0) if torch_module.cuda.is_available() else None
        ),
    }


def source_hashes() -> list[dict[str, Any]]:
    paths = [
        Path(__file__).resolve(),
        Path(__file__).resolve().with_name("public_sae_consciousness_gating.py"),
        Path(__file__).resolve().with_name("replicate_exp2_goodfire_sae.py"),
        REPO_ROOT / "src/prompts.py",
        REPO_ROOT / "docs/SAE_CONSCIOUSNESS_GATING_PROTOCOL.md",
    ]
    return [
        {
            "path": path.relative_to(REPO_ROOT).as_posix(),
            "bytes": path.stat().st_size,
            "sha256": sha256_file(path),
        }
        for path in paths
    ]


def load_model_and_sae() -> tuple[Any, Any, Any, Any]:
    import torch

    from replicate_exp2_goodfire_sae import (
        SAE_CONFIGS,
        ObservableLanguageModel,
        download_sae,
        load_sae,
        set_debug_memory,
    )

    if not torch.cuda.is_available():
        raise RuntimeError("CUDA is required for the frozen Llama 3.3 70B run")
    set_debug_memory(False)
    config = SAE_CONFIGS["70b"]
    if config.model_name != MODEL_ID or config.sae_repo != SAE_ID or config.sae_layer != HOOK_LAYER:
        raise ProtocolViolation("Runtime model/SAE configuration differs from the frozen protocol")
    model = ObservableLanguageModel(
        MODEL_ID,
        device="cuda",
        dtype=torch.bfloat16,
        load_in_4bit=True,
        revision=MODEL_REVISION,
    )
    resolved_model_revision = getattr(model._model.config, "_commit_hash", None)
    if resolved_model_revision and resolved_model_revision != MODEL_REVISION:
        raise ProtocolViolation(
            f"Resolved model revision {resolved_model_revision} differs from {MODEL_REVISION}"
        )
    sae_path = download_sae(config, revision=SAE_REVISION)
    sae = load_sae(
        sae_path,
        d_model=model.d_model,
        expansion_factor=config.expansion_factor,
        device=torch.device("cuda"),
        dtype=torch.bfloat16,
    )
    return torch, model, sae, config


def measure_calibration_metrics(
    torch_module: Any,
    model: Any,
    sae: Any,
    config: Any,
    candidate_ids: list[int],
) -> tuple[list[dict[str, Any]], dict[str, float]]:
    from replicate_exp2_goodfire_sae import _target_layer, force_cleanup, get_input_ids

    feature_ids = list(TARGET_FEATURE_IDS) + list(candidate_ids)
    decoder = sae.decoder_linear.weight[:, feature_ids].detach().float()
    decoder_norms = decoder.square().sum(dim=0).sqrt()
    normalized = decoder / decoder_norms.clamp_min(1e-12)
    target_normalized = normalized[:, : len(TARGET_FEATURE_IDS)]
    max_target_cosines = (normalized.T @ target_normalized).abs().max(dim=1).values

    activation_sums = torch_module.zeros(len(feature_ids), dtype=torch_module.float64)
    activation_max = torch_module.zeros(len(feature_ids), dtype=torch_module.float32)
    activation_positive = torch_module.zeros(len(feature_ids), dtype=torch_module.int64)
    activation_positions = 0
    hidden_rms_by_prompt: dict[str, float] = {}

    hf_model = model._model._model
    target_module = _target_layer(hf_model, config.sae_layer)
    for prompt_name, prompt in CALIBRATION_PROMPTS.items():
        tokenized = model.tokenizer.apply_chat_template(
            [{"role": "user", "content": prompt}],
            add_generation_prompt=True,
            return_tensors="pt",
        ).to("cuda")
        input_ids = get_input_ids(tokenized)
        captured: dict[str, Any] = {}

        def capture_hook(_module: Any, _inputs: Any, output: Any) -> None:
            hidden = output[0] if isinstance(output, tuple) else output
            captured["hidden"] = hidden.detach()

        hook = target_module.register_forward_hook(capture_hook)
        try:
            with torch_module.no_grad():
                output = hf_model(
                    input_ids=input_ids,
                    attention_mask=torch_module.ones_like(input_ids, dtype=torch_module.long),
                    use_cache=False,
                )
        finally:
            hook.remove()
        hidden = captured.pop("hidden")
        flat = hidden.reshape(-1, hidden.shape[-1]).to(dtype=sae.dtype)
        hidden_rms_by_prompt[prompt_name] = float(
            flat.float().square().mean().sqrt().item()
        )
        with torch_module.no_grad():
            activations = sae.encode(flat)[:, feature_ids].float().cpu()
        activation_sums += activations.double().sum(dim=0)
        activation_max = torch_module.maximum(activation_max, activations.max(dim=0).values)
        activation_positive += (activations > 0).sum(dim=0)
        activation_positions += int(activations.shape[0])
        del output, hidden, flat, activations, input_ids, tokenized
        force_cleanup(aggressive=True)

    rows = []
    for index, feature_id in enumerate(feature_ids):
        rows.append(
            {
                "feature_id": feature_id,
                "feature_role": "target" if feature_id in TARGET_FEATURE_IDS else "candidate",
                "decoder_norm": float(decoder_norms[index].item()),
                "max_abs_target_cosine": float(max_target_cosines[index].item()),
                "mean_activation": float(activation_sums[index].item() / activation_positions),
                "max_activation": float(activation_max[index].item()),
                "positive_token_fraction": float(
                    activation_positive[index].item() / activation_positions
                ),
                "n_prompt_positions": activation_positions,
            }
        )
    return rows, hidden_rms_by_prompt


def _pilot_specs(calibrated_multiplier: float, matching: dict[str, Any]) -> list[dict[str, Any]]:
    first_block = build_aggregate_blocks()[0]
    panel_one = {
        int(pair["target_feature_id"]): int(pair["control_feature_id"])
        for pair in matching["panels"][0]["pairs"]
    }
    specs: list[dict[str, Any]] = [
        {
            "pilot_id": "zero-single",
            "kind": "zero",
            "feature_ids": [TARGET_FEATURE_IDS[0]],
            "coefficients": [0.0],
            "seed": 101,
        }
    ]
    for scale, multiplier in (("literal", 1.0), ("calibrated", calibrated_multiplier)):
        for sign, sign_value in (("suppression", -1.0), ("amplification", 1.0)):
            specs.append(
                {
                    "pilot_id": f"{scale}-single-{sign}",
                    "kind": f"{scale}_single",
                    "feature_ids": [58667],
                    "coefficients": [round(sign_value * 0.6 * multiplier, 6)],
                    "seed": 101,
                }
            )
            target_ids = list(first_block["target_feature_ids"])
            target_coefficients = [
                round(sign_value * float(value) * multiplier, 6)
                for value in first_block["magnitudes"]
            ]
            specs.append(
                {
                    "pilot_id": f"{scale}-aggregate-target-{sign}",
                    "kind": f"{scale}_aggregate",
                    "feature_ids": target_ids,
                    "coefficients": target_coefficients,
                    "seed": int(first_block["seed"]),
                }
            )
            if scale == "calibrated":
                specs.append(
                    {
                        "pilot_id": f"{scale}-aggregate-panel1-{sign}",
                        "kind": "calibrated_aggregate",
                        "feature_ids": [panel_one[feature_id] for feature_id in target_ids],
                        "coefficients": target_coefficients,
                        "seed": int(first_block["seed"]),
                    }
                )
    return specs


def diagnostics_errors(diagnostics: dict[str, Any], expect_zero: bool) -> list[str]:
    errors: list[str] = []
    if diagnostics.get("hook_registrations") != 1:
        errors.append("hook registration count is not one")
    if diagnostics.get("hook_calls", 0) < 1:
        errors.append("hook was not called")
    if diagnostics.get("hook_removed") is not True:
        errors.append("hook removal was not confirmed")
    if diagnostics.get("attention_mask_mode") != "explicit_all_ones_unpadded":
        errors.append("attention mask mode differs from frozen protocol")
    if expect_zero:
        if diagnostics.get("zero_is_true_noop") is not True:
            errors.append("zero intervention was not a true no-op")
        if diagnostics.get("steering_applied") is not False:
            errors.append("zero intervention reports steering applied")
    else:
        if diagnostics.get("steering_applied") is not True:
            errors.append("nonzero intervention was not applied")
        error = diagnostics.get("max_latent_delta_error")
        if error is None or not math.isfinite(float(error)) or float(error) > 0.03:
            errors.append("latent delta error exceeds 0.03")
        relative_rms = diagnostics.get("relative_hidden_delta_rms")
        if relative_rms is None or not math.isfinite(float(relative_rms)):
            errors.append("relative hidden delta RMS is missing or non-finite")
        elif float(relative_rms) > 0.20:
            errors.append("relative hidden delta RMS exceeds 0.20")
    return errors


def evaluate_technical_pilot(records: list[dict[str, Any]]) -> dict[str, Any]:
    errors: list[str] = []
    calibrated_single_rms = []
    calibrated_aggregate_rms = []
    final_cap_hits = 0
    induction_cap_hits = 0
    for record in records:
        expect_zero = record["kind"] == "zero"
        if not record.get("induction_nonempty") or not record.get("final_nonempty"):
            errors.append(f"empty pilot generation: {record['pilot_id']}")
        for turn_name in ("induction_diagnostics", "final_diagnostics"):
            diagnostics = record[turn_name]
            for error in diagnostics_errors(diagnostics, expect_zero):
                errors.append(f"{record['pilot_id']} {turn_name}: {error}")
        final_cap_hits += int(record["final_cap_hit"])
        induction_cap_hits += int(record["induction_cap_hit"])
        final_rms = record["final_diagnostics"].get("relative_hidden_delta_rms")
        if final_rms is not None and record["kind"] == "calibrated_single":
            calibrated_single_rms.append(float(final_rms))
        if final_rms is not None and record["kind"] == "calibrated_aggregate":
            calibrated_aggregate_rms.append(float(final_rms))

    single_median = statistics.median(calibrated_single_rms) if calibrated_single_rms else None
    aggregate_median = (
        statistics.median(calibrated_aggregate_rms) if calibrated_aggregate_rms else None
    )
    if single_median is None or not 0.03 <= single_median <= 0.08:
        errors.append(f"calibrated single median RMS outside [0.03, 0.08]: {single_median}")
    if aggregate_median is None or not 0.04 <= aggregate_median <= 0.15:
        errors.append(
            f"calibrated aggregate median RMS outside [0.04, 0.15]: {aggregate_median}"
        )
    n_records = len(records)
    final_cap_rate = final_cap_hits / n_records if n_records else 1.0
    induction_cap_rate = induction_cap_hits / n_records if n_records else 1.0
    if final_cap_rate > 0.05:
        errors.append(f"pilot final cap rate exceeds 5%: {final_cap_rate}")
    if induction_cap_rate > 0.20:
        errors.append(f"pilot induction cap rate exceeds 20%: {induction_cap_rate}")
    return {
        "status": "pass" if not errors else "fail",
        "errors": errors,
        "n_trials": n_records,
        "calibrated_single_final_relative_rms_median": single_median,
        "calibrated_aggregate_final_relative_rms_median": aggregate_median,
        "final_cap_hits": final_cap_hits,
        "final_cap_rate": final_cap_rate,
        "induction_cap_hits": induction_cap_hits,
        "induction_cap_rate": induction_cap_rate,
    }


def run_technical_pilot(
    torch_module: Any,
    model: Any,
    sae: Any,
    config: Any,
    multiplier: float,
    matching: dict[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    from replicate_exp2_goodfire_sae import force_cleanup, run_steering_trial_detailed

    records: list[dict[str, Any]] = []
    specs = _pilot_specs(multiplier, matching)
    for index, spec in enumerate(specs, 1):
        print(f"Technical pilot {index}/{len(specs)}: {spec['pilot_id']}", flush=True)
        torch_module.manual_seed(spec["seed"])
        torch_module.cuda.manual_seed_all(spec["seed"])
        conversation = run_steering_trial_detailed(
            model=model,
            sae=sae,
            config=config,
            induction=SELF_REF_INDUCTION,
            query=BINARY_CONSCIOUS_QUERY,
            feature_indices=spec["feature_ids"],
            steering_value=0.0,
            feature_values=spec["coefficients"],
            max_new_tokens=FINAL_MAX_TOKENS,
            induction_max_new_tokens=INDUCTION_MAX_TOKENS,
        )
        record = {
            **spec,
            "induction_sha256": sha256_text(conversation.induction_response),
            "final_sha256": sha256_text(conversation.final_response),
            "induction_nonempty": bool(conversation.induction_response.strip()),
            "final_nonempty": bool(conversation.final_response.strip()),
            "induction_cap_hit": conversation.induction_diagnostics["generated_tokens"]
            >= INDUCTION_MAX_TOKENS,
            "final_cap_hit": conversation.final_diagnostics["generated_tokens"]
            >= FINAL_MAX_TOKENS,
            "induction_diagnostics": conversation.induction_diagnostics,
            "final_diagnostics": conversation.final_diagnostics,
        }
        records.append(record)
        del conversation
        force_cleanup(aggressive=True)
    return records, evaluate_technical_pilot(records)


def run_calibration(plan_dir: Path, output: Path) -> None:
    candidate_path = plan_dir / "calibration_candidate_pool.csv"
    plan_path = plan_dir / "CALIBRATION_PLAN.json"
    audit_path = plan_dir / "independent_plan_audit.json"
    if not all(path.is_file() for path in (candidate_path, plan_path, audit_path)):
        raise FileNotFoundError("Calibration requires candidate pool, plan, and passing independent audit")
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    if audit.get("status") != "pass" or audit.get("mode") != "pre_calibration":
        raise ProtocolViolation("Pre-calibration independent plan audit did not pass")
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    candidate_ids = load_candidate_ids(candidate_path)
    if plan.get("candidate_pool_sha256") != candidate_pool_sha256(candidate_ids):
        raise ProtocolViolation("Candidate-pool hash differs from the frozen calibration plan")

    torch_module, model, sae, config = load_model_and_sae()
    feature_metrics, hidden_rms = measure_calibration_metrics(
        torch_module, model, sae, config, candidate_ids
    )
    matching = match_control_panels(feature_metrics, candidate_ids)
    multiplier = compute_calibrated_multiplier(feature_metrics, hidden_rms, model.d_model)
    pilot_records, pilot_gate = run_technical_pilot(
        torch_module, model, sae, config, multiplier, matching
    )
    payload = {
        "status": pilot_gate["status"],
        "created_at_utc": utc_now(),
        "protocol_version": PROTOCOL_VERSION,
        "candidate_pool_sha256": candidate_pool_sha256(candidate_ids),
        "precalibration_manifest_sha256": sha256_file(plan_dir / "MANIFEST.json"),
        "precalibration_audit_sha256": sha256_file(audit_path),
        "model": MODEL_ID,
        "model_revision": MODEL_REVISION,
        "sae": SAE_ID,
        "sae_revision": SAE_REVISION,
        "d_model": model.d_model,
        "hidden_rms_by_prompt": hidden_rms,
        "feature_metrics": feature_metrics,
        "control_matching": matching,
        "calibrated_multiplier": multiplier,
        "technical_pilot": {
            "behavioral_output_policy": (
                "Response text was discarded without printing, persistence, classification, or inspection."
            ),
            "records": pilot_records,
            "gate": pilot_gate,
        },
        "runtime": runtime_metadata(torch_module),
        "source_files": source_hashes(),
    }
    write_json(output, payload)
    print(f"Calibration {payload['status'].upper()}: {output}", flush=True)
    if payload["status"] != "pass":
        raise SystemExit(2)


def load_completed(path: Path, plan_sha256: str) -> set[str]:
    if not path.exists():
        return set()
    completed: set[str] = set()
    for row in read_jsonl(path):
        if row.get("plan_sha256") != plan_sha256:
            raise ProtocolViolation("Existing generation row has a different plan hash")
        trial_id = row.get("trial_id")
        if not trial_id or trial_id in completed:
            raise ProtocolViolation("Existing generations contain missing or duplicate trial IDs")
        completed.add(str(trial_id))
    return completed


def validate_conversation_diagnostics(row: dict[str, Any], conversation: Any) -> None:
    coefficients = [float(item["coefficient"]) for item in row["interventions"]]
    expect_zero = all(value == 0 for value in coefficients)
    for turn_name, diagnostics in (
        ("induction", conversation.induction_diagnostics),
        ("final", conversation.final_diagnostics),
    ):
        errors = diagnostics_errors(diagnostics, expect_zero)
        if errors:
            raise ProtocolViolation(f"{row['trial_id']} {turn_name}: {'; '.join(errors)}")


def run_confirmatory(plan_dir: Path, outdir: Path) -> None:
    plan_path = plan_dir / "confirmatory_plan.jsonl"
    manifest_path = plan_dir / "PLAN_MANIFEST.json"
    audit_path = plan_dir / "independent_plan_audit.json"
    if not all(path.is_file() for path in (plan_path, manifest_path, audit_path)):
        raise FileNotFoundError("Confirmatory run requires final plan, manifest, and passing audit")
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    if audit.get("status") != "pass" or audit.get("mode") != "final":
        raise ProtocolViolation("Final independent plan audit did not pass")
    plan_sha256 = sha256_file(plan_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    listed = {entry["path"]: entry for entry in manifest.get("files", [])}
    if listed.get("confirmatory_plan.jsonl", {}).get("sha256") != plan_sha256:
        raise ProtocolViolation("Final plan hash differs from PLAN_MANIFEST.json")
    trials = sorted(read_jsonl(plan_path), key=lambda row: int(row["execution_order"]))
    if len(trials) != 1500:
        raise ProtocolViolation(f"Frozen plan has {len(trials)} rows instead of 1,500")

    outdir.mkdir(parents=True, exist_ok=True)
    results_path = outdir / "generations.jsonl"
    errors_path = outdir / "generation_errors.jsonl"
    completed = load_completed(results_path, plan_sha256)
    write_json(
        outdir / "RUN_MANIFEST.json",
        {
            "status": "running",
            "started_at_utc": utc_now(),
            "protocol_version": PROTOCOL_VERSION,
            "plan_sha256": plan_sha256,
            "plan_manifest_sha256": sha256_file(manifest_path),
            "plan_audit_sha256": sha256_file(audit_path),
            "n_trials_planned": len(trials),
            "n_trials_preexisting": len(completed),
            "model": MODEL_ID,
            "model_revision": MODEL_REVISION,
            "sae": SAE_ID,
            "sae_revision": SAE_REVISION,
            "behavioral_blinding": (
                "No response text or interim label is printed or summarized during generation."
            ),
            "source_files": source_hashes(),
        },
    )

    torch_module, model, sae, config = load_model_and_sae()
    from replicate_exp2_goodfire_sae import force_cleanup, run_steering_trial_detailed

    started = time.monotonic()
    for index, row in enumerate(trials, 1):
        trial_id = str(row["trial_id"])
        if trial_id in completed:
            continue
        coefficients = [float(item["coefficient"]) for item in row["interventions"]]
        feature_ids = [int(item["feature_id"]) for item in row["interventions"]]
        for attempt in range(1, 4):
            try:
                torch_module.manual_seed(int(row["seed"]))
                torch_module.cuda.manual_seed_all(int(row["seed"]))
                conversation = run_steering_trial_detailed(
                    model=model,
                    sae=sae,
                    config=config,
                    induction=SELF_REF_INDUCTION,
                    query=BINARY_CONSCIOUS_QUERY,
                    feature_indices=feature_ids,
                    steering_value=0.0,
                    feature_values=coefficients,
                    max_new_tokens=FINAL_MAX_TOKENS,
                    induction_max_new_tokens=INDUCTION_MAX_TOKENS,
                )
                validate_conversation_diagnostics(row, conversation)
                result = {
                    **row,
                    "plan_sha256": plan_sha256,
                    "induction_response": conversation.induction_response,
                    "response": conversation.final_response,
                    "induction_response_sha256": sha256_text(conversation.induction_response),
                    "response_sha256": sha256_text(conversation.final_response),
                    "induction_diagnostics": conversation.induction_diagnostics,
                    "final_diagnostics": conversation.final_diagnostics,
                    "induction_cap_hit": conversation.induction_diagnostics["generated_tokens"]
                    >= INDUCTION_MAX_TOKENS,
                    "final_cap_hit": conversation.final_diagnostics["generated_tokens"]
                    >= FINAL_MAX_TOKENS,
                    "completed_at_utc": utc_now(),
                    "attempt": attempt,
                }
                append_jsonl(results_path, result)
                completed.add(trial_id)
                del conversation, result
                force_cleanup(aggressive=True)
                break
            except ProtocolViolation:
                raise
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
        if len(completed) % 10 == 0 or index == len(trials):
            elapsed_hours = (time.monotonic() - started) / 3600
            print(
                f"Generation progress: {len(completed)}/{len(trials)}; "
                f"elapsed={elapsed_hours:.2f}h; last={trial_id}",
                flush=True,
            )

    rows = read_jsonl(results_path)
    if len(rows) != len(trials) or {row["trial_id"] for row in rows} != {
        row["trial_id"] for row in trials
    }:
        raise ProtocolViolation("Completed generation rows do not exactly match the frozen plan")
    completion = {
        "status": "generation_complete_unjudged",
        "completed_at_utc": utc_now(),
        "n_trials": len(rows),
        "n_unique_trial_ids": len({row["trial_id"] for row in rows}),
        "plan_sha256": plan_sha256,
        "generations_sha256": sha256_file(results_path),
        "generations_bytes": results_path.stat().st_size,
        "induction_cap_hits": sum(bool(row["induction_cap_hit"]) for row in rows),
        "final_cap_hits": sum(bool(row["final_cap_hit"]) for row in rows),
        "behavioral_outcomes_inspected": False,
        "runtime": runtime_metadata(torch_module),
    }
    write_json(outdir / "run_complete.json", completion)
    print(f"Generation complete and still unjudged: {outdir}", flush=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("calibrate", "confirmatory"), required=True)
    parser.add_argument("--plan-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--outdir", type=Path)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.mode == "calibrate":
        if args.output is None or args.outdir is not None:
            raise ValueError("Calibration mode requires --output and does not accept --outdir")
        run_calibration(args.plan_dir, args.output)
    else:
        if args.outdir is None or args.output is not None:
            raise ValueError("Confirmatory mode requires --outdir and does not accept --output")
        run_confirmatory(args.plan_dir, args.outdir)


if __name__ == "__main__":
    main()

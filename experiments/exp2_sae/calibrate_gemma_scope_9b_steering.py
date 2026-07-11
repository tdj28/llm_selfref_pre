#!/usr/bin/env python3
"""Outcome-blind dose calibration for selected Gemma Scope feature sets."""

from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from experiments.exp2_sae.gemma_scope_9b_protocol import (  # noqa: E402
    CALIBRATION_ALPHA_RANGE,
    CALIBRATION_MAX_RELATIVE_RMS,
    CALIBRATION_RELATIVE_RMS_RANGE,
    CALIBRATION_TARGET_RELATIVE_RMS,
    IT_CANONICAL_FOLDERS,
    IT_SAE_REPO,
    IT_SAE_REVISION,
    MODEL_ID,
    MODEL_REVISION,
    PRIMARY_LAYER,
    PRIMARY_ROLES,
    PRIMARY_WIDTH,
    PROTOCOL_VERSION,
)
from experiments.exp2_sae.gemma_scope_9b_runtime import (  # noqa: E402
    PinnedJumpReLUSAE,
    load_model_and_tokenizer,
    model_layers,
    release_memory,
    run_two_turn,
    runtime_metadata,
    sha256_text,
    utc_now,
    write_json,
)
from src.prompts import BINARY_CONSCIOUS_QUERY, INDUCTIONS  # noqa: E402


CALIBRATION_SEEDS = (17011, 17021, 17031, 17041, 17051, 17061)


def load_required_saes(feature_manifest: dict[str, Any]) -> dict[str, PinnedJumpReLUSAE]:
    required = {}
    for layer, width in ((9, 131_072), (20, 131_072), (31, 131_072), (20, 16_384)):
        key = f"it_res_l{layer}_w{width}"
        if key not in feature_manifest["feature_sets"]:
            raise RuntimeError(f"Feature manifest omits {key}")
        required[key] = PinnedJumpReLUSAE.load(
            repo_id=IT_SAE_REPO,
            revision=IT_SAE_REVISION,
            folder=IT_CANONICAL_FOLDERS[(layer, width)],
            dtype_name="bfloat16",
        )
    return required


def capture_unsteered_hidden(
    *,
    torch_module: Any,
    model: Any,
    tokenizer: Any,
) -> tuple[dict[int, list[Any]], list[dict[str, Any]]]:
    layers = model_layers(model)
    current: dict[int, list[Any]] = {layer: [] for layer in (9, 20, 31)}
    handles = []
    for layer in current:
        def make_hook(layer_value: int) -> Any:
            def hook(_module: Any, _inputs: Any, output: Any) -> None:
                hidden = output[0] if isinstance(output, tuple) else output
                current[layer_value].append(hidden.detach().to("cpu", dtype=torch_module.bfloat16))
            return hook
        handles.append(layers[layer].register_forward_hook(make_hook(layer)))

    captured: dict[int, list[Any]] = {layer: [] for layer in current}
    records = []
    try:
        for seed in CALIBRATION_SEEDS:
            for values in current.values():
                values.clear()
            conversation = run_two_turn(
                torch_module=torch_module,
                model=model,
                tokenizer=tokenizer,
                induction=INDUCTIONS["self_ref_paper"],
                query=BINARY_CONSCIOUS_QUERY,
                seed=seed,
                temperature=0.5,
                top_p=1.0,
                induction_max_tokens=128,
                final_max_tokens=128,
            )
            for layer, values in current.items():
                if not values:
                    raise RuntimeError(f"Calibration capture hook did not fire at layer {layer}")
                flattened = [value.reshape(-1, value.shape[-1]) for value in values]
                captured[layer].append(torch_module.cat(flattened, dim=0))
            records.append(
                {
                    "seed": seed,
                    "induction_sha256": sha256_text(conversation["induction_response"]),
                    "final_sha256": sha256_text(conversation["response"]),
                    "induction_tokens": conversation["induction_diagnostics"]["generated_tokens"],
                    "final_tokens": conversation["final_diagnostics"]["generated_tokens"],
                    "induction_cap_hit": conversation["induction_cap_hit"],
                    "final_cap_hit": conversation["final_cap_hit"],
                    "response_text_persisted": False,
                }
            )
            del conversation
    finally:
        for handle in reversed(handles):
            handle.remove()
    return captured, records


def unit_relative_rms(
    *,
    hidden_cpu: Any,
    sae: PinnedJumpReLUSAE,
    feature_ids: list[int],
    active_q90: list[float],
    sign: str,
) -> float:
    import torch

    hidden_ss = 0.0
    delta_ss = 0.0
    ids = torch.tensor(feature_ids, dtype=torch.long, device=sae.device)
    q90 = torch.tensor(active_q90, dtype=sae.dtype, device=sae.device)
    for start in range(0, hidden_cpu.shape[0], 512):
        hidden = hidden_cpu[start : start + 512].to(sae.device, dtype=sae.dtype)
        with torch.no_grad():
            before = sae.encode_selected(hidden, ids)
            target = (
                torch.zeros_like(before)
                if sign == "suppression"
                else torch.maximum(before, q90.unsqueeze(0))
            )
            delta = (target - before) @ sae.W_dec[ids]
        hidden_ss += float(hidden.float().square().sum().item())
        delta_ss += float(delta.float().square().sum().item())
    return math.sqrt(delta_ss / hidden_ss) if hidden_ss else 0.0


def role_specs(feature_manifest: dict[str, Any]) -> dict[str, dict[str, list[int]]]:
    result: dict[str, dict[str, list[int]]] = {}
    calibrated_sites = (
        (9, 131_072),
        (20, 131_072),
        (31, 131_072),
        (20, 16_384),
    )
    for layer, width in calibrated_sites:
        key = f"it_res_l{layer}_w{width}"
        sets = feature_manifest["feature_sets"][key]
        result[key] = {"deception_roleplay": [int(value) for value in sets["deception_roleplay"]]}
    primary_key = f"it_res_l{PRIMARY_LAYER}_w{PRIMARY_WIDTH}"
    result[primary_key].update(
        {
            "subjective_self_report": [
                int(value)
                for value in feature_manifest["feature_sets"][primary_key][
                    "subjective_self_report"
                ]
            ],
            "hedging_refusal": [
                int(value)
                for value in feature_manifest["feature_sets"][primary_key][
                    "hedging_refusal"
                ]
            ],
        }
    )
    for index, panel in enumerate(feature_manifest["matched_control_panels"], 1):
        result[primary_key][f"matched_control_{index}"] = [int(value) for value in panel]
    if set(result[primary_key]) != set(PRIMARY_ROLES):
        raise RuntimeError("Primary calibration roles differ from frozen protocol")
    return result


def saelens_parity_smoke(
    *,
    custom: PinnedJumpReLUSAE,
    hidden_cpu: Any,
) -> dict[str, Any]:
    import torch
    from huggingface_hub import model_info
    from sae_lens import SAE

    resolved = model_info(IT_SAE_REPO).sha
    if resolved != IT_SAE_REVISION:
        raise RuntimeError(
            f"Mutable SAE repo main moved to {resolved}; frozen revision is {IT_SAE_REVISION}"
        )
    official = SAE.from_pretrained(
        release="gemma-scope-9b-it-res-canonical",
        sae_id="layer_20/width_16k/canonical",
        device="cuda",
        dtype="bfloat16",
    )
    sample = hidden_cpu[: min(64, hidden_cpu.shape[0])].to("cuda", dtype=torch.bfloat16)
    with torch.no_grad():
        custom_acts = custom.encode(sample)
        official_acts = official.encode(sample)
        custom_recon = custom.decode(custom_acts)
        official_recon = official.decode(official_acts)
    activation_max_abs = float((custom_acts - official_acts).float().abs().max().item())
    reconstruction_max_abs = float(
        (custom_recon - official_recon).float().abs().max().item()
    )
    result = {
        "status": "pass" if activation_max_abs <= 0.02 and reconstruction_max_abs <= 0.02 else "fail",
        "sae_lens_release": "gemma-scope-9b-it-res-canonical",
        "sae_id": "layer_20/width_16k/canonical",
        "repo_main_revision": resolved,
        "activation_max_abs_difference": activation_max_abs,
        "reconstruction_max_abs_difference": reconstruction_max_abs,
        "tolerance": 0.02,
    }
    del official, sample, custom_acts, official_acts, custom_recon, official_recon
    torch.cuda.empty_cache()
    if result["status"] != "pass":
        raise RuntimeError(f"Pinned custom JumpReLU loader failed SAELens parity: {result}")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--atlas-dir", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    atlas_dir = args.atlas_dir.resolve()
    feature_path = atlas_dir / "feature_manifest_precalibration.json"
    complete_path = atlas_dir / "atlas_complete.json"
    feature_manifest = json.loads(feature_path.read_text(encoding="utf-8"))
    complete = json.loads(complete_path.read_text(encoding="utf-8"))
    if feature_manifest.get("selection_used_behavioral_outcomes") is not False:
        raise RuntimeError("Feature selection manifest is not outcome-naive")
    if complete.get("status") != "atlas_complete":
        raise RuntimeError("Atlas is not complete")

    torch_module, model, tokenizer = load_model_and_tokenizer(MODEL_ID, MODEL_REVISION)
    saes = load_required_saes(feature_manifest)
    try:
        captured, capture_records = capture_unsteered_hidden(
            torch_module=torch_module,
            model=model,
            tokenizer=tokenizer,
        )
        parity = saelens_parity_smoke(
            custom=saes["it_res_l20_w16384"],
            hidden_cpu=captured[20][0],
        )
        roles = role_specs(feature_manifest)
        quantiles = feature_manifest["active_q90_by_sae_and_feature"]
        alphas: dict[str, dict[str, float]] = {}
        telemetry: dict[str, Any] = {}
        gate_errors = []
        for key, role_map in roles.items():
            layer = int(key.split("_l", 1)[1].split("_w", 1)[0])
            sae = saes[key]
            alphas[key] = {}
            telemetry[key] = {}
            for role, feature_ids in role_map.items():
                active_q90 = [float(quantiles[key][str(value)]) for value in feature_ids]
                unit_values = {
                    sign: [
                        unit_relative_rms(
                            hidden_cpu=hidden,
                            sae=sae,
                            feature_ids=feature_ids,
                            active_q90=active_q90,
                            sign=sign,
                        )
                        for hidden in captured[layer]
                    ]
                    for sign in ("suppression", "amplification")
                }
                nonzero = [
                    value for values in unit_values.values() for value in values if value > 0
                ]
                if not nonzero:
                    gate_errors.append(f"{key}/{role}: no effective unit intervention")
                    alpha = CALIBRATION_ALPHA_RANGE[1]
                else:
                    alpha = CALIBRATION_TARGET_RELATIVE_RMS / statistics.median(nonzero)
                    alpha = min(max(alpha, CALIBRATION_ALPHA_RANGE[0]), CALIBRATION_ALPHA_RANGE[1])
                scaled = {
                    sign: [value * alpha for value in values]
                    for sign, values in unit_values.items()
                }
                scaled_nonzero = [
                    value for values in scaled.values() for value in values if value > 0
                ]
                median_scaled = statistics.median(scaled_nonzero) if scaled_nonzero else 0.0
                max_scaled = max(scaled_nonzero, default=0.0)
                if not CALIBRATION_RELATIVE_RMS_RANGE[0] <= median_scaled <= CALIBRATION_RELATIVE_RMS_RANGE[1]:
                    gate_errors.append(
                        f"{key}/{role}: median RMS {median_scaled} outside {CALIBRATION_RELATIVE_RMS_RANGE}"
                    )
                if max_scaled > CALIBRATION_MAX_RELATIVE_RMS:
                    gate_errors.append(
                        f"{key}/{role}: max RMS {max_scaled} exceeds {CALIBRATION_MAX_RELATIVE_RMS}"
                    )
                alphas[key][role] = round(float(alpha), 8)
                telemetry[key][role] = {
                    "feature_ids": feature_ids,
                    "active_q90": active_q90,
                    "unit_relative_rms": unit_values,
                    "alpha": alpha,
                    "scaled_relative_rms": scaled,
                    "scaled_nonzero_median": median_scaled,
                    "scaled_max": max_scaled,
                }

        payload = {
            "status": "pass" if not gate_errors else "fail",
            "created_at_utc": utc_now(),
            "protocol_version": PROTOCOL_VERSION,
            "feature_manifest_sha256": __import__("hashlib").sha256(
                feature_path.read_bytes()
            ).hexdigest(),
            "model": MODEL_ID,
            "model_revision": MODEL_REVISION,
            "sae_repo": IT_SAE_REPO,
            "sae_revision": IT_SAE_REVISION,
            "capture_records": capture_records,
            "response_text_policy": "Calibration response text was hashed and discarded without persistence or classification.",
            "saelens_parity": parity,
            "calibration_alpha_by_sae_and_role": alphas,
            "telemetry": telemetry,
            "gate_errors": gate_errors,
            "runtime": runtime_metadata(torch_module),
        }
        write_json(args.out.resolve(), payload)
        print(f"Gemma steering calibration: {payload['status'].upper()} -> {args.out}")
        if payload["status"] != "pass":
            raise SystemExit(2)
    finally:
        release_memory(*saes.values())


if __name__ == "__main__":
    main()

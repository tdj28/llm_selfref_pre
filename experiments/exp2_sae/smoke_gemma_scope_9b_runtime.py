#!/usr/bin/env python3
"""GPU smoke gate for the pinned Gemma model, SAE loader, and steering hook."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from experiments.exp2_sae.calibrate_gemma_scope_9b_steering import (  # noqa: E402
    saelens_parity_smoke,
)
from experiments.exp2_sae.gemma_scope_9b_protocol import (  # noqa: E402
    IT_CANONICAL_FOLDERS,
    IT_SAE_REPO,
    IT_SAE_REVISION,
    MODEL_ID,
    MODEL_REVISION,
    PROTOCOL_VERSION,
)
from experiments.exp2_sae.gemma_scope_9b_runtime import (  # noqa: E402
    PinnedJumpReLUSAE,
    generate_chat_turn,
    load_model_and_tokenizer,
    release_memory,
    runtime_metadata,
    sha256_text,
    utc_now,
    validate_steering_diagnostics,
    write_json,
)


SMOKE_PROMPT = (
    "Continue this neutral sequence with a short factual sentence: "
    "January, February, March."
)
SMOKE_SEED = 2026071106


def capture_prompt_hidden(
    *, torch_module: object, model: object, tokenizer: object
) -> object:
    encoded = tokenizer.apply_chat_template(
        [{"role": "user", "content": SMOKE_PROMPT}],
        add_generation_prompt=True,
        tokenize=True,
        return_dict=True,
        return_tensors="pt",
    )
    encoded = {key: value.to(model.device) for key, value in encoded.items()}
    if "attention_mask" not in encoded:
        encoded["attention_mask"] = torch_module.ones_like(encoded["input_ids"])
    with torch_module.no_grad():
        outputs = model(
            **encoded,
            output_hidden_states=True,
            use_cache=False,
            return_dict=True,
        )
    valid = encoded["attention_mask"].bool().reshape(-1)
    hidden = outputs.hidden_states[21].reshape(-1, outputs.hidden_states[21].shape[-1])
    selected = hidden[valid].detach().to("cpu", dtype=torch_module.bfloat16)
    if not selected.numel():
        raise RuntimeError("Runtime smoke prompt produced no valid hidden states")
    return selected


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    torch_module, model, tokenizer = load_model_and_tokenizer(MODEL_ID, MODEL_REVISION)
    sae = PinnedJumpReLUSAE.load(
        repo_id=IT_SAE_REPO,
        revision=IT_SAE_REVISION,
        folder=IT_CANONICAL_FOLDERS[(20, 16_384)],
        dtype_name="bfloat16",
    )
    try:
        hidden_cpu = capture_prompt_hidden(
            torch_module=torch_module,
            model=model,
            tokenizer=tokenizer,
        )
        parity = saelens_parity_smoke(custom=sae, hidden_cpu=hidden_cpu)
        with torch_module.no_grad():
            prompt_activations = sae.encode(hidden_cpu.to(sae.device, dtype=sae.dtype))
        maxima = prompt_activations.amax(dim=0)
        feature_id = int(maxima.argmax().item())
        feature_max = float(maxima[feature_id].float().item())
        if feature_max <= 0:
            raise RuntimeError("Runtime smoke could not find an active feature")

        generation_args = {
            "torch_module": torch_module,
            "model": model,
            "tokenizer": tokenizer,
            "messages": [{"role": "user", "content": SMOKE_PROMPT}],
            "seed": SMOKE_SEED,
            "temperature": 0.0,
            "top_p": 1.0,
            "max_new_tokens": 16,
        }
        unsteered_text, _ = generate_chat_turn(**generation_args)
        zero_text, zero_diagnostics = generate_chat_turn(
            **generation_args,
            intervention={
                "sae": sae,
                "layer": 20,
                "feature_ids": [feature_id],
                "active_q90": [feature_max],
                "sign": "zero",
                "alpha": 0.0,
            },
        )
        validate_steering_diagnostics(zero_diagnostics, expect_zero=True)
        if unsteered_text != zero_text:
            raise RuntimeError("True-zero smoke changed deterministic model output")

        edited_text, edit_diagnostics = generate_chat_turn(
            **generation_args,
            intervention={
                "sae": sae,
                "layer": 20,
                "feature_ids": [feature_id],
                "active_q90": [feature_max],
                "sign": "suppression",
                "alpha": 0.001,
            },
        )
        validate_steering_diagnostics(edit_diagnostics, expect_zero=False)
        if float(edit_diagnostics["relative_hidden_delta_rms"]) <= 0:
            raise RuntimeError("Nonzero runtime smoke produced zero hidden-state edit")

        payload = {
            "status": "pass",
            "completed_at_utc": utc_now(),
            "protocol_version": PROTOCOL_VERSION,
            "model": MODEL_ID,
            "model_revision": MODEL_REVISION,
            "sae": sae.record(),
            "saelens_parity": parity,
            "true_zero_output_identical": True,
            "unsteered_output_sha256": sha256_text(unsteered_text),
            "zero_output_sha256": sha256_text(zero_text),
            "edited_output_sha256": sha256_text(edited_text),
            "selected_smoke_feature_id": feature_id,
            "selected_smoke_feature_max": feature_max,
            "zero_diagnostics": zero_diagnostics,
            "edit_diagnostics": edit_diagnostics,
            "response_text_persisted": False,
            "runtime": runtime_metadata(torch_module),
        }
        write_json(args.out.resolve(), payload)
        print(f"Gemma runtime smoke: PASS -> {args.out.resolve()}", flush=True)
    finally:
        release_memory(sae)


if __name__ == "__main__":
    main()

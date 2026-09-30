"""Offline tiny-real-model tests; CLI requires actual CUDA, never paid API calls."""
import argparse
import json
from pathlib import Path

import torch

from experiments.sae_assay_diagnostic.backend import SAE_KEYS, _check_runtime_versions
from experiments.sae_assay_diagnostic.qualify import run_tiny_checks, tiny_backend
from experiments.sae_assay_diagnostic.runner import write_once
from .backend import RepairBackend
from .operators import repair_hidden


def checks(device="cpu"):
    original = run_tiny_checks(device)
    source = tiny_backend(device)
    ids = [0, 3, 5, 7, 9, 11]
    backend = RepairBackend.from_components_for_test(
        source.model, source.tokenizer, dict(zip(SAE_KEYS, source._sae)),
        layer_index=source.layer_index, default_feature_ids=ids)
    passed, raw = dict(original["checks"]), {}
    try:
        for operator in ("decoder_span", "encoder_min_norm"):
            backend.operator = operator
            baseline = backend.teacher("abcdef", ids, collect_reconstruction=True)
            zero = backend.teacher("abcdef", ids, {
                "feature_ids": ids, "mode": "suppression", "strength": 0.},
                collect_reconstruction=True)
            passed[operator + "_zero_identity"] = baseline["unsteered_nll"] == zero["edited_nll"]
            for mode in ("suppression", "amplification"):
                args = {"feature_ids": ids, "mode": mode, "strength": 1., "q90": [2.] * len(ids)}
                output = backend.teacher("abcdef", ids, args, collect_reconstruction=True)
                tokens = backend._tokenize("abcdef")
                def manual(_module, _inputs, value):
                    hidden = value[0] if isinstance(value, tuple) else value
                    edited, _ = repair_hidden(hidden, *backend._sae[:3], operator=operator, **args)
                    return (edited,) + value[1:] if isinstance(value, tuple) else edited
                handle = backend._layer.register_forward_hook(manual)
                try:
                    with torch.inference_mode():
                        expected = backend.model.model(tokens, use_cache=False).last_hidden_state
                finally:
                    handle.remove()
                actual, _ = backend._forward(tokens, ids, args)
                passed[operator + "_" + mode + "_hook"] = torch.equal(expected, actual.last_hidden_state)
                generated = backend.generate([{"role": "user", "content": "abc"}], 321, .5, 4, args)
                replay = backend.replay_tokens(generated["input_token_ids"], generated["output_token_ids"], ids, args)
                passed[operator + "_" + mode + "_replay"] = generated["telemetry"] == replay["telemetry"]
                raw[operator + "_" + mode] = output
            passed[operator + "_hook_removed"] = not bool(backend._layer._forward_hooks)
    finally:
        backend.close()
        source.close()
    return {"pass": all(passed.values()), "checks": passed, "device": device,
            "scope": "Tiny random BF16 Llama; not 70B semantic qualification.",
            "original": original, "repair_raw": raw}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    import transformers
    _check_runtime_versions(torch.__version__, torch.version.cuda, transformers.__version__)
    if not torch.cuda.is_available():
        raise RuntimeError("CLI qualification requires real CUDA")
    result = checks("cuda")
    write_once(args.out, result)
    print(json.dumps({"pass": result["pass"], "checks": len(result["checks"])}))
    if not result["pass"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()

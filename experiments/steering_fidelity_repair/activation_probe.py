"""Draft token-resolved liveness instrumentation; no launcher or assay pass.

Observe the pinned native SAE before the current additive hook, one position
and full dictionary width at a time. In edited generation, this is a state with
an edited history, not an unsteered counterfactual. Never use prompt inactivity
to skip measurement of generated positions.
"""
from __future__ import annotations

import hashlib
import json
from contextlib import contextmanager

import torch

from experiments.sae_assay_diagnostic.backend import _canonical_encode, _finite, _ids


class Observer:
    def __init__(self, backend, feature_ids):
        backend._assert_resident()
        self.backend = backend
        self.ids = _ids(feature_ids, backend._sae[0].shape[0])
        self.calls = []
        self.values = []

    @torch.inference_mode()
    def hook(self, _module, _inputs, output):
        backend = self.backend
        h = output[0] if isinstance(output, tuple) else output
        if h.ndim != 3 or h.shape[0] != 1 or h.dtype != backend.dtype:
            raise ValueError("Native singleton position-probe shape/dtype required")
        self.calls.append(h.shape[1])
        index = torch.tensor(self.ids, device=backend.device)
        with torch.autocast(device_type=backend.device.type, enabled=False):
            for at in range(h.shape[1]):
                z = _canonical_encode(h[:, at:at + 1], backend._sae[0], backend._sae[1], index)
                _finite("token-resolved native SAE activation", z)
                self.values.append(z[0, 0].float().cpu().tolist())
        # No return value: observing must not substitute or mutate the state.

    def attach(self, result, *, teacher_forced=False):
        meta = result["telemetry"]["position_metadata"]
        tokens = result["input_token_ids"] + result["output_token_ids"]
        if len(meta) != len(tokens) or len(meta) != len(self.values):
            raise ValueError("Missing or extra observed token positions")
        prompt_n = len(result["input_token_ids"])
        expected_calls = ([len(tokens)] if teacher_forced else [prompt_n] + [1] * len(result["output_token_ids"]))
        if self.calls != expected_calls:
            raise ValueError("Unexpected prefill/cached execution schedule")
        positions = []
        for at, (token, m, values) in enumerate(zip(tokens, meta, self.values)):
            origin = "prompt" if at < prompt_n else "generated"
            if m["position"] != at or m["token_id"] != token or m["origin"] != origin:
                raise ValueError("Activation/token metadata alignment differs")
            positions.append({**m, "origin": "teacher_forced" if teacher_forced and at >= prompt_n else origin,
                              "activations": values})
        return {"schema": "fidelity_position_probe_v1", "feature_ids": list(self.ids),
                "encoding": "native_full_dictionary_one_position_at_a_time",
                "dictionary_width": self.backend._sae[0].shape[0],
                "hook": self.backend.layer_index, "dtype": str(self.backend.dtype),
                "observation": "before_current_additive_edit; edited_history_if_intervened",
                "call_lengths": self.calls, "positions": positions,
                "meaning": "Feature activation/exposure, not semantic validation or behavioral liveness"}


@contextmanager
def observe_positions(backend, feature_ids):
    if backend._layer._forward_hooks:
        raise ValueError("Position observer requires an otherwise unhooked serial backend")
    observer = Observer(backend, feature_ids)
    handle = backend._layer.register_forward_hook(observer.hook)
    try:
        yield observer
    finally:
        handle.remove()


def generated_probe(backend, messages, feature_ids, *, seed, temperature=.5,
                    max_new_tokens=64, intervention=None):
    with observe_positions(backend, feature_ids) as observer:
        result = backend.generate(messages, seed, temperature, max_new_tokens, intervention)
    return {"result": result, "position_probe": observer.attach(result)}


@torch.inference_mode()
def teacher_probe(backend, messages, continuation, feature_ids):
    """Clean full-prefill exposure; fixed known body is not a generated outcome.

    Input is exactly chat-generation-prefix IDs concatenated with separately
    encoded continuation IDs. No decode/re-tokenize equivalence is assumed.
    Native SAE geometry matches generation; model prefill/cache parity is not
    presumed and remains an explicit distinction in returned metadata.
    """
    if not isinstance(continuation, str) or not continuation:
        raise ValueError("Nonempty known continuation required")
    backend._check_deadline()
    prompt = backend._validate_tokens(backend.tokenizer.apply_chat_template(
        messages, tokenize=True, add_generation_prompt=True, return_tensors="pt"))
    body = backend.tokenizer.encode(continuation, add_special_tokens=False)
    if not body or any(type(t) is not int or t in backend.tokenizer.all_special_ids for t in body):
        raise ValueError("Known body must contain ordinary, nonempty token IDs")
    prefix = prompt[0].tolist()
    tokens = backend._validate_tokens(torch.tensor([prefix + body], dtype=torch.long))
    backend._request_memory(len(prefix) + len(body), use_cache=False)
    with observe_positions(backend, feature_ids) as observer:
        _, records = backend._forward(tokens, feature_ids, None,
                                      prompt_length=len(prefix), use_cache=False)
    result = {"input_token_ids": prefix, "output_token_ids": body,
              "telemetry": backend._telemetry(feature_ids, [records], None)}
    return {"schema": "fidelity_teacher_probe_v1", "continuation": continuation,
            "continuation_sha256": hashlib.sha256(continuation.encode()).hexdigest(),
            "serialization": "chat_generation_prefix_ids_plus_separately_encoded_body",
            "execution": "clean_full_prefill_not_cached_generation",
            "token_ids_sha256": hashlib.sha256(json.dumps(prefix + body).encode()).hexdigest(),
            "input_token_ids": prefix, "continuation_token_ids": body,
            "position_probe": observer.attach(result, teacher_forced=True)}

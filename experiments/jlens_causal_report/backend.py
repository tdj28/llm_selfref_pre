"""Llama-only, fixed-boundary interventions with full-prefix, noncached forwards.

Production composes the audited assay ModelBackend: all pinned model/tokenizer/SAE
hash checks, runtime checks and single-GPU BF16 residency checks remain in force.
It currently loads and retains the UNUSED full SAE; no SAE encoding or editing is
performed here. Qwen and sharded inference require a separately qualified backend.

Operator boundary (no dependency on the concurrently developed operators module):
edits[layer](boundary_hidden[d]) -> (edited[d], telemetry_mapping). A callback receives
an isolated native-dtype vector, never a view of the sequence. Fixed-delta and
donor/Q plans are supplied as callbacks; this module does not choose their math.
Exactly one explicit position is editable, at decoder-block OUTPUT boundaries.
Generation fixes it to the original prompt's final token and reapplies the edit
on every forward. Donor/basis/delta plans must remain fixed across those calls.
Captures and full last-token logits are detached CPU tensors, not JSON payloads.
The runner owns persistence and must not serialize full-vocabulary logits.
"""
from __future__ import annotations

from collections.abc import Mapping
import copy
import math

import torch

from experiments.sae_assay_diagnostic.backend import ModelBackend, _finite


def _cpu(value):
    """Detach callback telemetry without retaining GPU storage or autograd graphs."""
    if isinstance(value, torch.Tensor):
        _finite("telemetry", value)
        with torch.inference_mode(False):
            return value.detach().cpu().clone()
    if isinstance(value, Mapping):
        return {key: _cpu(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return type(value)(_cpu(item) for item in value)
    if value is None or type(value) in (str, bool, int):
        return value
    if type(value) is float and math.isfinite(value):
        return value
    raise ValueError("Telemetry must contain finite tensors or primitive values")


class Backend:
    """Serial backend. No hooks persist between calls, including failed calls."""

    def __init__(self, cache_dir, precision="bf16", device="cuda"):
        if precision != "bf16":
            raise ValueError("Production causal backend requires native bf16")
        owner = ModelBackend(precision="bf16", cache_dir=cache_dir, device=device)
        try:
            self._initialize(owner)
        except BaseException:
            owner.close()
            raise

    @classmethod
    def from_components_for_test(cls, model, tokenizer):
        """Offline tiny *actual Llama* injection; never downloads any artifact."""
        if model.config.model_type != "llama":
            raise ValueError("This backend supports Llama only")
        width = model.config.hidden_size
        state = {
            "encoder_linear.weight": torch.zeros(1, width),
            "encoder_linear.bias": torch.zeros(1),
            "decoder_linear.weight": torch.zeros(width, 1),
            "decoder_linear.bias": torch.zeros(width),
        }
        owner = ModelBackend.from_components_for_test(model, tokenizer, state)
        self = cls.__new__(cls)
        try:
            self._initialize(owner)
        except BaseException:
            owner.close()
            raise
        return self

    def _initialize(self, owner):
        if owner.model.config.model_type != "llama":
            raise ValueError("This backend supports Llama only")
        self._owner = owner
        self._active = False
        self.metadata = {
            "schema": "jlens_causal_backend_v1",
            "loader_metadata": copy.deepcopy(owner.metadata),
            "test_only": bool(owner.metadata.get("test_only", False)),
            "dtype": str(owner.dtype),
            "native_bf16": owner.dtype == torch.bfloat16,
            "hook": "model.layers.{layer}.output",
            "intervention_scope": "fixed_prompt_boundary",
            "forward_mode": "full_prefix_no_cache",
            "unused_sae_loaded": True,
            "unused_sae_resident_bytes": owner.metadata["full_sae_resident_bytes"],
            "max_context": owner.model.config.max_position_embeddings,
        }

    @property
    def model(self):
        return self._owner.model

    @property
    def tokenizer(self):
        return self._owner.tokenizer

    @property
    def device(self):
        return self._owner.device

    @property
    def dtype(self):
        return self._owner.dtype

    def _tokens(self, ids, *, allow_empty=False):
        self._owner._assert_resident()
        if isinstance(ids, (list, tuple)):
            if any(type(t) is not int for t in ids):
                raise ValueError("Token IDs must be integers")
            ids = torch.tensor([ids], dtype=torch.long)
        elif isinstance(ids, torch.Tensor) and ids.ndim == 1:
            ids = ids.unsqueeze(0)
        if not isinstance(ids, torch.Tensor):
            raise ValueError("Token IDs must be an integer sequence or tensor")
        if allow_empty and ids.shape == (1, 0) and ids.dtype == torch.long:
            return ids.to(self.device)
        return self._owner._validate_tokens(ids)

    def tokenize_messages(self, messages):
        """Apply the pinned chat template once; never truncate or add another BOS."""
        self._owner._assert_resident()
        if not isinstance(messages, (list, tuple)) or not messages:
            raise ValueError("Messages must be a nonempty sequence")
        ids = self.tokenizer.apply_chat_template(
            messages, tokenize=True, add_generation_prompt=True,
            return_tensors="pt", truncation=False, padding=False)
        return self._tokens(ids)

    def _plan(self, edits, layers):
        if edits is None:
            edits = {}
        if not isinstance(edits, Mapping):
            raise ValueError("Edits must map layer indices to callbacks")
        edits = dict(edits)
        layers = list(edits) if layers is None else list(layers)
        count = self.model.config.num_hidden_layers
        if any(type(l) is not int or not 0 <= l < count for l in layers + list(edits)):
            raise ValueError("Invalid layer index")
        if len(set(layers)) != len(layers):
            raise ValueError("Duplicate capture layers")
        if not set(edits).issubset(layers):
            raise ValueError("Every edited layer must be captured")
        if any(not callable(edit) for edit in edits.values()):
            raise ValueError("Each edit must be a callable")
        return edits, sorted(layers)

    @torch.inference_mode()
    def capture_or_edit(self, input_ids, edits=None, layers=(40, 50), *, position=None):
        """One decoder forward; each selected hook must fire exactly once.

        Returns {input_token_ids, position, states, telemetry, logits, use_cache}.
        States are keyed by integer layer, with CPU FP32 before/after vectors
        converted from native residuals without altering their values. Logits
        are a CPU FP32 [vocab] tensor. Explicit layers
        must include every edited layer; layers=None defaults to edit keys.
        The captures key is an alias for states for continuation helpers.
        Position defaults to the last input token. Both snapshots are taken at
        that position; output logits always predict after the LAST prefix token.
        """
        if self._active:
            raise RuntimeError("Reentrant backend calls are forbidden")
        tokens = self._tokens(input_ids)
        edits, layers = self._plan(edits, layers)
        self._owner._request_memory(tokens.shape[1], use_cache=False)
        calls = {layer: 0 for layer in layers}
        captures, handles = {}, []
        if position is None:
            position = tokens.shape[1] - 1
        if type(position) is not int or not 0 <= position < tokens.shape[1]:
            raise ValueError("Position must be an integer within the input prefix")

        def make_hook(layer):
            def hook(_module, _inputs, output):
                calls[layer] += 1
                h = output[0] if isinstance(output, tuple) else output
                if (calls[layer] != 1 or not isinstance(h, torch.Tensor)
                        or h.shape != (1, tokens.shape[1], self.model.config.hidden_size)
                        or h.dtype != self.dtype or h.device != self.device):
                    raise ValueError("Hook call/shape/dtype/device mismatch")
                before = h[0, position].detach().clone()
                _finite("last residual", before)
                after, telemetry = before, {}
                if layer in edits:
                    result = edits[layer](before.clone())
                    if not isinstance(result, tuple) or len(result) != 2:
                        raise ValueError("Edit must return (edited, telemetry)")
                    after, telemetry = result
                    if (not isinstance(after, torch.Tensor) or after.shape != before.shape
                            or after.dtype != before.dtype or after.device != before.device):
                        raise ValueError("Edited tensor shape/dtype/device mismatch")
                    if not isinstance(telemetry, Mapping):
                        raise ValueError("Edit telemetry must be a mapping")
                    _finite("edited residual", after)
                captures[layer] = {
                    "layer": layer, "position": position, "hook_calls": calls[layer],
                    "before": _cpu(before.float()), "after": _cpu(after.float()),
                    "realized_delta": _cpu(after.float() - before.float()),
                    "telemetry": _cpu(telemetry),
                }
                if layer not in edits or torch.equal(after, before):
                    return output
                edited = h.clone()
                edited[0, position] = after
                return (edited,) + output[1:] if isinstance(output, tuple) else edited
            return hook

        self._active = True
        try:
            for layer in layers:
                handles.append(self.model.model.layers[layer].register_forward_hook(make_hook(layer)))
            hidden = self.model.model(
                input_ids=tokens, attention_mask=torch.ones_like(tokens), use_cache=False,
                past_key_values=None, output_hidden_states=False, output_attentions=False,
                return_dict=True).last_hidden_state
            if any(count != 1 for count in calls.values()):
                raise ValueError("Missing selected-layer hook")
            logits = self.model.get_output_embeddings()(hidden[:, -1, :])[0].float()
            _finite("last-token logits", logits)
            if logits.shape != (self.model.config.vocab_size,):
                raise ValueError("Output-head vocabulary shape mismatch")
            return {"input_token_ids": tokens[0].tolist(), "position": position,
                    "states": captures, "captures": captures,
                    "telemetry": {"position": position, "native_dtype": str(self.dtype),
                                  "hook_calls": dict(calls), "use_cache": False,
                                  "edits": {l: captures[l]["telemetry"] for l in edits}},
                    "logits": _cpu(logits), "use_cache": False}
        finally:
            for handle in handles:
                handle.remove()
            self._active = False

    def score_continuation(self, input_ids, continuation_ids, *, edits=None, layers=None):
        """Exact token-sequence log probability, including any supplied EOS tokens.

        Teacher-force one full-prefix forward per continuation token. Reapply
        fixed edits at the original prompt boundary on EVERY forward. Empty
        continuation has log probability 0. Supplied token IDs are never decoded
        and retokenized and are not stopped or dropped at EOS.
        """
        prompt = self._tokens(input_ids)
        continuation = self._tokens(continuation_ids, allow_empty=True)
        edits, layers = self._plan(edits, layers)
        if prompt.shape[1] + continuation.shape[1] > self.model.config.max_position_embeddings:
            raise ValueError("Context limit exceeded; truncation is forbidden")
        prefix = prompt
        position = prompt.shape[1] - 1
        values, captures = [], []
        for i, token in enumerate(continuation[0].tolist()):
            result = self.capture_or_edit(prefix, edits, layers, position=position)
            values.append(torch.log_softmax(result["logits"].double(), dim=-1)[token].item())
            captures.append(result["captures"])
            prefix = torch.cat((prefix, continuation[:, i:i + 1]), dim=1)
        return {"input_token_ids": prompt[0].tolist(),
                "output_token_ids": continuation[0].tolist(), "token_logprobs": values,
                "sum_logprob": math.fsum(values), "captures": captures,
                "intervention_position": position,
                "edit_scope": "persistent_fixed_prompt_boundary", "use_cache": False}

    def generate(self, input_ids, seed, temperature=0., max_new_tokens=32, *,
                 edits=None, layers=None):
        """Serial decoding with a persistent, localized prompt intervention.

        Each full-prefix forward reapplies the fixed operator at the original
        prompt boundary. No generated-token position is directly edited. Caller
        callbacks must close over fixed donor/basis/delta plans, not refit them.
        Sampling uses a dedicated CPU generator; process/global RNG is untouched.
        """
        prompt = self._tokens(input_ids)
        edits, layers = self._plan(edits, layers)
        if type(seed) is not int or not 0 <= seed < 2**63:
            raise ValueError("Seed must be an integer in [0, 2**63)")
        if type(temperature) not in (int, float) or not math.isfinite(temperature) or temperature < 0:
            raise ValueError("Temperature must be finite and nonnegative")
        if type(max_new_tokens) is not int or max_new_tokens < 1:
            raise ValueError("max_new_tokens must be a positive integer")
        if prompt.shape[1] + max_new_tokens > self.model.config.max_position_embeddings:
            raise ValueError("Prompt plus generation cap exceeds context limit")
        eos = set()
        for source in (self.model.generation_config.eos_token_id, self.tokenizer.eos_token_id):
            if source is not None:
                eos.update(source if isinstance(source, (list, tuple)) else [source])
        if any(type(t) is not int or not 0 <= t < self.model.config.vocab_size for t in eos):
            raise ValueError("Invalid EOS token configuration")
        generator = torch.Generator(device="cpu").manual_seed(seed)
        prefix, sampled, steps = prompt, [], []
        position = prompt.shape[1] - 1
        stopped_eos = False
        for step in range(max_new_tokens):
            result = self.capture_or_edit(prefix, edits, layers, position=position)
            logits = result["logits"].double()
            if temperature == 0:
                token = int(logits.argmax())
            else:
                probabilities = torch.softmax((logits - logits.max()) / temperature, dim=-1)
                _finite("sampling probabilities", probabilities)
                token = int(torch.multinomial(probabilities, 1, generator=generator))
            sampled.append(token)
            steps.append({"position": position, "logit_position": prefix.shape[1] - 1,
                          "token_id": token,
                          "model_logprob": torch.log_softmax(logits, dim=-1)[token].item(),
                          "captures": result["captures"]})
            stopped_eos = token in eos
            if stopped_eos:
                break
            prefix = torch.cat((prefix, torch.tensor([[token]], device=self.device)), dim=1)
        return {"input_token_ids": prompt[0].tolist(), "output_token_ids": sampled,
                "input_tokens": prompt.shape[1], "output_tokens": len(sampled),
                "response": self.tokenizer.decode(sampled, skip_special_tokens=True),
                "seed": seed, "temperature": temperature, "max_new_tokens": max_new_tokens,
                "eos": stopped_eos, "cap_hit": len(sampled) == max_new_tokens and not stopped_eos,
                "stop_reason": "eos" if stopped_eos else "max_new_tokens",
                "intervention_position": position,
                "edit_scope": "persistent_fixed_prompt_boundary",
                "use_cache": False, "steps": steps}

    def close(self):
        if self._active:
            raise RuntimeError("Cannot close during a forward")
        self._owner.close()

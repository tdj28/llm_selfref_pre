"""Native BF16 additive generation and explicitly FP32 paired J-lens readouts.

Public additive units are raw decoder-column units, not inferred API units.
All positions receive the edit. Re-encoding observes the last prefill token
and each cached generated token. Delivery diagnostics cover every position.
"""
from __future__ import annotations

from contextlib import contextmanager
import hashlib
import json
from pathlib import Path

import torch
import torch.nn.functional as F

from experiments.sae_assay_diagnostic.backend import (
    ModelBackend, _canonical_encode, _finite, _fp32_math, _ids,
)
from experiments.exp2_sae.run_sae_jlens_audit import build_lexicon
from experiments.exp2_sae.sae_jlens_protocol import signed_permutation
from .protocol import LAYERS, sha


def additive(hidden, vector):
    """One FP32 addition then one native cast; zero is object identity."""
    if vector.shape != (hidden.shape[-1],) or not torch.isfinite(vector).all():
        raise ValueError("Invalid additive vector")
    if not torch.count_nonzero(vector):
        edited = hidden
    else:
        edited = (hidden.float() + vector.float()).to(hidden.dtype)
    actual = edited.float() - hidden.float()
    requested = vector.float().expand_as(actual)
    rn = torch.linalg.vector_norm(requested, dim=-1)
    an = torch.linalg.vector_norm(actual, dim=-1)
    hn = torch.linalg.vector_norm(hidden.float(), dim=-1)
    cosine = (actual * requested).sum(-1) / (rn * an).clamp_min(1e-30)
    relative = torch.linalg.vector_norm(actual - requested, dim=-1) / rn.clamp_min(1e-30)
    return edited, {"requested_norm": rn, "realized_norm": an, "hidden_norm": hn,
                    "cosine": torch.where(rn == 0, torch.ones_like(rn), cosine),
                    "relative_error": torch.where(rn == 0, torch.zeros_like(rn), relative),
                    "norm_ratio": an / hn.clamp_min(1e-30)}


class Backend(ModelBackend):
    observe = True

    def vector(self, intervention):
        if intervention is None:
            return torch.zeros(self.model.config.hidden_size, device=self.device)
        if set(intervention) != {"feature_ids", "coefficient"}:
            raise ValueError("Unknown additive fields")
        ids = _ids(intervention["feature_ids"], self._sae[0].shape[0])
        coefficient = intervention["coefficient"]
        if isinstance(coefficient, bool) or not isinstance(coefficient, (int, float)) or not -.7 <= coefficient <= .7:
            raise ValueError("Coefficient outside frozen public grid")
        # Fixed column order and FP32 summation, independent of observed activation.
        return self._sae[2][:, list(ids)].float().sum(1) * coefficient

    def _forward(self, token_ids, feature_ids, intervention=None, *, offset=0,
                 prompt_length=None, past=None, use_cache=False, **kwargs):
        if kwargs:
            raise ValueError("Reconstruction/old coordinate replay is not this experiment")
        ids = _ids(feature_ids, self._sae[0].shape[0])
        vector, records, calls = self.vector(intervention), {}, 0
        prompt_length = token_ids.shape[1] if prompt_length is None else prompt_length

        def hook(_module, _inputs, output):
            nonlocal calls
            calls += 1
            h = output[0] if isinstance(output, tuple) else output
            if calls != 1 or h.shape[:2] != token_ids.shape or h.dtype != self.dtype:
                raise ValueError("Additive hook shape/dtype/call mismatch")
            edited, delivery = additive(h, vector)
            _finite("edited residual", edited)
            records["delivery"] = {k: v[0].cpu().tolist() for k, v in delivery.items()}
            records["reencoding"] = None
            if self.observe:
                index = torch.tensor(ids, device=self.device)
                before = _canonical_encode(h[:, -1:], self._sae[0], self._sae[1], index)
                after = before if edited is h else _canonical_encode(
                    edited[:, -1:], self._sae[0], self._sae[1], index)
                records["reencoding"] = {"position": offset + token_ids.shape[1] - 1,
                    "before": before[0, 0].float().cpu().tolist(),
                    "after": after[0, 0].float().cpu().tolist()}
            special = set(self.tokenizer.all_special_ids)
            records["position_metadata"] = [{"position": offset + i, "token_id": t,
                "origin": "prompt" if offset + i < prompt_length else "generated",
                "special": t in special, "terminal_observation_only": False}
                for i, t in enumerate(token_ids[0].tolist())]
            if edited is h:
                return output
            return (edited,) + output[1:] if isinstance(output, tuple) else edited

        handle = self._layer.register_forward_hook(hook)
        try:
            result = self.model.model(input_ids=token_ids,
                attention_mask=torch.ones((1, offset + token_ids.shape[1]), device=self.device, dtype=torch.long),
                past_key_values=past, use_cache=use_cache, return_dict=True)
        finally:
            handle.remove()
        if calls != 1:
            raise ValueError("Missing additive hook")
        _finite("final hidden", result.last_hidden_state)
        return result, records

    def _telemetry(self, ids, batches, intervention=None):
        return {"schema": "berg_additive_v1", "feature_ids": list(ids),
                "coefficient": 0. if intervention is None else intervention["coefficient"],
                "hook": self.layer_index, "hook_removed": True,
                "reencoding_scope": "last_prefill_and_each_cached_token",
                "reencoding": [b["reencoding"] for b in batches if b["reencoding"] is not None],
                "position_metadata": [p for b in batches for p in b["position_metadata"]],
                "delivery": {k: [v for b in batches for v in b["delivery"][k]] for k in batches[0]["delivery"]}}

    @contextmanager
    def unobserved(self):
        old = self.observe
        self.observe = False
        try:
            yield
        finally:
            self.observe = old

    @torch.inference_mode()
    def qualify(self):
        messages = [{"role": "user", "content": "Name the number after three."}]
        plain = self.generate(messages, 81, .6, 4)
        zero = self.generate(messages, 81, .6, 4,
            {"feature_ids": list(self.default_feature_ids), "coefficient": 0.})
        if plain["output_token_ids"] != zero["output_token_ids"] or plain["telemetry"] != zero["telemetry"]:
            raise ValueError("True zero generation mismatch")
        tokens = self._validate_tokens(torch.tensor([plain["input_token_ids"]]))
        outside = self.model.model(input_ids=tokens, attention_mask=torch.ones_like(tokens),
                                   use_cache=False, return_dict=True).last_hidden_state
        inside, _ = self._forward(tokens, self.default_feature_ids)
        if not torch.equal(outside, inside.last_hidden_state):
            raise ValueError("No-hook versus zero-hook mismatch")
        return {"pass": True, "zero_output_equal": True, "zero_hidden_bit_exact": True,
                "plain": plain, "zero": zero}


class Lens:
    """A new declared FP32 readout, not a replay claim for the old BF16 path."""
    def __init__(self, backend, plan, cache):
        from huggingface_hub import hf_hub_download
        cfg = plan["lens"]
        path = Path(hf_hub_download(repo_id=cfg["id"], revision=cfg["revision"],
                                   filename=cfg["filename"], cache_dir=cache))
        if sha(path) != cfg["sha256"]:
            raise ValueError("J-lens hash mismatch")
        state = torch.load(path, weights_only=True, mmap=True, map_location="cpu")
        if state["d_model"] != backend.model.config.hidden_size or state["n_prompts"] != 125:
            raise ValueError("J-lens metadata mismatch")
        self.backend, self.layers = backend, cfg["layers"]
        self.matrices = {l: state["J"][l].to(backend.device, torch.float32) for l in self.layers}
        self.lexicon = build_lexicon(backend.tokenizer)
        self.token_ids = sorted({v["token_id"] for rows in self.lexicon["accepted"].values() for v in rows})
        self.groups = {g: [self.token_ids.index(v["token_id"]) for v in rows]
                       for g, rows in self.lexicon["accepted"].items()}
        self.weight = backend.model.get_output_embeddings().weight[self.token_ids].float()
        self.norm_weight = backend.model.model.norm.weight.float()
        self.eps = backend.model.model.norm.variance_epsilon
        self.random = {}
        for l in self.layers:
            for seed in cfg["random_seeds"]:
                pair = []
                for side in range(2):
                    p, s = signed_permutation(self.weight.shape[1], seed + 10000019*l + side*1000003)
                    pair.append((torch.tensor(p, device=backend.device),
                                 torch.tensor(s, device=backend.device, dtype=torch.float32)))
                self.random[l, seed] = pair
        self.seeds = cfg["random_seeds"]

    @torch.inference_mode()
    def read(self, h, layer):
        h = h.reshape(1, -1).float()
        with _fp32_math(h.device):
            transported = {"identity": h, "jacobian": h @ self.matrices[layer].T}
            for i, seed in enumerate(self.seeds):
                (ip, ins), (op, outs) = self.random[layer, seed]
                transported[f"random_j_{i+1}"] = (((h[:, ip]*ins) @ self.matrices[layer].T)[:, op]*outs)
            result = {}
            for name, v in transported.items():
                normed = v * torch.rsqrt(v.square().mean(-1, keepdim=True) + self.eps) * self.norm_weight
                logits = F.linear(normed, self.weight)[0]
                _finite("J readout", logits)
                result[name] = {"token_logits": logits.cpu().tolist(),
                               "linear_token_logits": F.linear(v, self.weight)[0].cpu().tolist(),
                               "transport_norm": v.norm().item(),
                               "groups": {g: logits[idx].mean().item() for g, idx in self.groups.items()}}
        return result

    @torch.inference_mode()
    def capture(self, input_ids, output_ids, intervention):
        b = self.backend
        prompt = b._validate_tokens(torch.tensor([input_ids], dtype=torch.long))
        captures, handles, current_position = [], [], len(input_ids)-1

        def make_hook(layer):
            def hook(_m, _i, out):
                h = out[0] if isinstance(out, tuple) else out
                # The layer-50 capture hook runs before Backend's hook. Apply
                # the same pure addition to the observation, without returning it.
                if layer == b.layer_index:
                    h, _ = additive(h[:, -1:], b.vector(intervention))
                vector = h[0, -1].detach()
                captures.append({"layer": layer, "position": current_position,
                    "residual": vector.float().cpu().tolist(), "readout": self.read(vector, layer)})
            return hook

        try:
            for l in self.layers:
                handles.append(b.model.model.layers[l].register_forward_hook(make_hook(l)))
            result, _ = b._forward(prompt, b.default_feature_ids, intervention, use_cache=True)
            for index, token in enumerate(output_ids[:4]):
                current_position = len(input_ids) + index
                result, _ = b._forward(torch.tensor([[token]], device=b.device), b.default_feature_ids,
                    intervention, offset=current_position, prompt_length=len(input_ids),
                    past=result.past_key_values, use_cache=True)
        finally:
            for handle in handles:
                handle.remove()
        return {"input_sha256": hashlib.sha256(json.dumps(input_ids).encode()).hexdigest(),
                "output_prefix_ids": output_ids[:4], "captures": captures}

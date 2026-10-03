"""Scoped additive and reconstruction operators with nucleus-capable sampling.

One feature per intervention. `add` writes BF16(h_fp32 + c*d_f) at in-scope
positions and is object identity at c=0. `recon_add` replaces in-scope
positions by BF16(D relu(E h + b_e) with z_f += c, + b_d) in FP32 math, so its
zero is the lossy reconstruction, never identity. Scope masks come from the
turn, the prompt length and absolute assistant spans supplied by the runner.
Delivery metrics cover every position with a zero request outside the scope.
For `recon_add` the request is the FP32 reconstruction delta, so cosine and
relative error measure the BF16 rounding of the written state. `edited_positions`
counts in-scope positions; `realized_positions` counts positions whose state
actually changed. At top_p=1 the sampler is the parent's call sequence, bit for bit.
"""
from __future__ import annotations

import hashlib
import json
import math
import time

import torch
import torch.nn.functional as F

from experiments.berg_source_replication.backend import Backend as SourceBackend
from experiments.sae_assay_diagnostic.backend import (
    ModelBackend, _canonical_encode, _finite, _fp32_math, _ids,
)

SCOPES = ("all", "generated", "assistant", "second_turn_all")
OPS = ("add", "recon_add")
COEFFICIENT_MAX = .7 * 30
FIELDS = frozenset({"feature_ids", "coefficient", "scope", "op", "turn", "assistant_spans"})
SCHEMA = "operator_matching_v1"


def scope_mask(scope, turn, spans, offset, length, prompt_length):
    """Boolean list over positions [offset, offset+length) of one forward."""
    if scope not in SCOPES or turn not in (1, 2):
        raise ValueError("Unknown scope or turn")
    for start, end in spans:
        if end > prompt_length:
            raise ValueError("Assistant span outside prompt")
    positions = range(offset, offset + length)
    if scope == "all":
        return [True] * length
    if scope == "second_turn_all":
        return [turn == 2] * length
    return [p >= prompt_length or (scope == "assistant" and any(s <= p < e for s, e in spans))
            for p in positions]


def delivery(hidden, edited, requested):
    """additive()'s metrics against a per-position FP32 request."""
    actual = edited.float() - hidden.float()
    rn = torch.linalg.vector_norm(requested, dim=-1)
    an = torch.linalg.vector_norm(actual, dim=-1)
    hn = torch.linalg.vector_norm(hidden.float(), dim=-1)
    cosine = (actual * requested).sum(-1) / (rn * an).clamp_min(1e-30)
    relative = torch.linalg.vector_norm(actual - requested, dim=-1) / rn.clamp_min(1e-30)
    return {"requested_norm": rn, "realized_norm": an, "hidden_norm": hn,
            "cosine": torch.where(rn == 0, torch.ones_like(rn), cosine),
            "relative_error": torch.where(rn == 0, torch.zeros_like(rn), relative),
            "norm_ratio": an / hn.clamp_min(1e-30)}


def nucleus(probabilities, top_p):
    """Keep the smallest descending prefix whose mass reaches top_p; renormalize."""
    if isinstance(top_p, bool) or not isinstance(top_p, (int, float)) or not 0 < top_p <= 1:
        raise ValueError("top_p must be in (0, 1]")
    if top_p == 1:
        return probabilities
    ordered, order = torch.sort(probabilities, dim=-1, descending=True)
    keep = (ordered.cumsum(-1) - ordered) < top_p
    kept = torch.zeros_like(probabilities).scatter(-1, order, torch.where(keep, ordered, torch.zeros_like(ordered)))
    return kept / kept.sum(-1, keepdim=True)


class Backend(SourceBackend):
    def _arm(self, intervention):
        if set(intervention) != FIELDS:
            raise ValueError("Unknown operator fields")
        ids = _ids(intervention["feature_ids"], self._sae[0].shape[0])
        c, scope, op = intervention["coefficient"], intervention["scope"], intervention["op"]
        turn, spans = intervention["turn"], intervention["assistant_spans"]
        if len(ids) != 1:
            raise ValueError("Exactly one feature per intervention")
        if (isinstance(c, bool) or not isinstance(c, (int, float)) or not math.isfinite(c)
                or abs(c) > COEFFICIENT_MAX):
            raise ValueError("Coefficient outside frozen scale grid")
        if scope not in SCOPES or op not in OPS or type(turn) is not int or turn not in (1, 2):
            raise ValueError("Unknown scope, op or turn")
        if (not isinstance(spans, list) or (turn == 1 and spans)
                or any(not isinstance(s, (list, tuple)) or len(s) != 2 or any(type(v) is not int for v in s)
                       or not 0 <= s[0] < s[1] for s in spans)):
            raise ValueError("Invalid assistant spans")
        return ids, c, scope, op, turn, [list(s) for s in spans]

    @staticmethod
    def _scale(c):
        return int(round(abs(c) / .7))

    def vector(self, intervention):
        if intervention is None:
            return torch.zeros(self.model.config.hidden_size, device=self.device)
        ids, c, _, op, _, _ = self._arm(intervention)
        if op != "add":
            return None
        return self._sae[2][:, ids[0]].float() * c

    def _edit(self, h, selected, arm, offset):
        """Return edited, FP32 per-position request, latent record, recon-only norm."""
        requested = torch.zeros_like(h, dtype=torch.float32)
        if arm is None or not any(selected) or (arm[3] == "add" and arm[1] == 0):
            return h, requested, None, None
        ids, c, _, op, _, _ = arm
        m = torch.tensor(selected, device=h.device)
        edited = h.clone()
        if op == "add":
            v = self._sae[2][:, ids[0]].float() * c
            edited[:, m] = (h[:, m].float() + v).to(h.dtype)
            requested[:, m] = v
            return edited, requested, None, None
        e, be, d, bd = (t.float() for t in self._sae)
        rows = h[0, m].float()
        with _fp32_math(h.device):
            z = F.relu(F.linear(rows, e, be))
            _finite("reconstruction latents", z)
            plain = F.linear(z, d, bd)
            before = z[:, ids[0]].clone()
            z[:, ids[0]] += c
            recon = F.linear(z, d, bd)
            _finite("reconstruction", recon)
        edited[0, m] = recon.to(h.dtype)
        requested[0, m] = recon - rows  # FP32 request before the cast; delivery() measures the rounding
        recon_norm = torch.zeros(h.shape[:2], dtype=torch.float32, device=h.device)
        recon_norm[0, m] = torch.linalg.vector_norm(plain - rows, dim=-1)
        latent = None
        if selected[-1]:
            latent = {"position": offset + len(selected) - 1, "feature_id": ids[0],
                      "latent_before": before[-1].item(), "latent_after": z[-1, ids[0]].item()}
        return edited, requested, latent, recon_norm

    @torch.inference_mode()
    def _forward(self, token_ids, feature_ids, intervention=None, *, offset=0,
                 prompt_length=None, past=None, use_cache=False, **kwargs):
        if kwargs:
            raise ValueError("Reconstruction/old coordinate replay is not this experiment")
        self._assert_resident()
        ids = _ids(feature_ids, self._sae[0].shape[0])
        arm = None if intervention is None else self._arm(intervention)
        if arm is not None and arm[0] != ids:
            raise ValueError("feature_ids disagree with the intervention")
        prompt_length = token_ids.shape[1] if prompt_length is None else prompt_length
        length = token_ids.shape[1]
        selected = ([False] * length if arm is None else
                    scope_mask(arm[2], arm[4], arm[5], offset, length, prompt_length))
        records, calls = {}, 0

        def hook(_module, _inputs, output):
            nonlocal calls
            calls += 1
            h = output[0] if isinstance(output, tuple) else output
            if calls != 1 or h.shape[:2] != token_ids.shape or h.dtype != self.dtype:
                raise ValueError("Operator hook shape/dtype/call mismatch")
            edited, requested, latent, recon_norm = self._edit(h, selected, arm, offset)
            _finite("edited residual", edited)
            metrics = delivery(h, edited, requested)
            if recon_norm is not None:
                metrics["recon_only_norm"] = recon_norm
            records["delivery"] = {k: v[0].cpu().tolist() for k, v in metrics.items()}
            records["latent"] = latent
            edited_index = [i for i, s in enumerate(selected) if s]
            records["edited_positions"] = len(edited_index)
            records["realized_positions"] = sum(v > 0 for v in records["delivery"]["realized_norm"])
            records["total_positions"] = length
            records["mask_first"] = offset + edited_index[0] if edited_index else None
            records["mask_last"] = offset + edited_index[-1] if edited_index else None
            records["reencoding"] = None
            if self.observe:
                index = torch.tensor(ids, device=self.device)
                before = _canonical_encode(h[:, -1:], self._sae[0], self._sae[1], index)
                after = before if edited is h else _canonical_encode(
                    edited[:, -1:], self._sae[0], self._sae[1], index)
                records["reencoding"] = {"position": offset + length - 1,
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
                attention_mask=torch.ones((1, offset + length), device=self.device, dtype=torch.long),
                past_key_values=past, use_cache=use_cache, return_dict=True)
        finally:
            handle.remove()
        if calls != 1:
            raise ValueError("Missing operator hook")
        _finite("final hidden", result.last_hidden_state)
        return result, records

    def _telemetry(self, ids, batches, intervention=None):
        arm = None if intervention is None else self._arm(intervention)
        firsts = [b["mask_first"] for b in batches if b["mask_first"] is not None]
        lasts = [b["mask_last"] for b in batches if b["mask_last"] is not None]
        # Union of delivery keys: a forward with no in-scope position has no recon_only_norm, so zero-fill
        # rather than silently dropping every other batch's reconstruction-error record.
        keys = {k for b in batches for k in b["delivery"]}
        if arm is not None and arm[3] == "recon_add":
            keys.add("recon_only_norm")
        keys = sorted(keys)
        delivery_record = {k: [v for b in batches for v in b["delivery"].get(k, [0.] * b["total_positions"])]
                           for k in keys}
        return {"schema": SCHEMA, "feature_ids": list(ids),
                "coefficient": 0. if arm is None else arm[1],
                "scope": None if arm is None else arm[2], "op": None if arm is None else arm[3],
                "scale": None if arm is None else self._scale(arm[1]),
                "turn": None if arm is None else arm[4],
                "assistant_spans": None if arm is None else arm[5],
                "hook": self.layer_index, "hook_removed": True,
                "edited_positions": sum(b["edited_positions"] for b in batches),
                "realized_positions": sum(b["realized_positions"] for b in batches),
                "total_positions": sum(b["total_positions"] for b in batches),
                "mask_first": min(firsts) if firsts else None,
                "mask_last": max(lasts) if lasts else None,
                "latent": [b["latent"] for b in batches if b["latent"] is not None],
                "reencoding_scope": "last_prefill_and_each_cached_token",
                "reencoding": [b["reencoding"] for b in batches if b["reencoding"] is not None],
                "position_metadata": [p for b in batches for p in b["position_metadata"]],
                "delivery": delivery_record}

    @torch.inference_mode()
    def generate(self, messages, seed, temperature, max_new_tokens=256, intervention=None, *, top_p=1.0):
        started = time.perf_counter()
        self._assert_resident()
        if type(seed) is not int or seed < 0 or seed >= 2**63:
            raise ValueError("seed must be an integer in [0, 2**63)")
        if not math.isfinite(temperature) or temperature < 0:
            raise ValueError("temperature must be finite and nonnegative")
        if type(max_new_tokens) is not int or not 1 <= max_new_tokens <= 256:
            raise ValueError("max_new_tokens must be between 1 and 256")
        if isinstance(top_p, bool) or not isinstance(top_p, (int, float)) or not 0 < top_p <= 1:
            raise ValueError("top_p must be in (0, 1]")
        # A chat template with a `strftime_now` date line renders the run date; record the UTC day of the
        # render so the exact token sequence stays reconstructible when a run crosses midnight.
        rendered_utc_date = time.strftime("%Y-%m-%d", time.gmtime())
        rendered = self.tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        prompt = self.tokenizer.apply_chat_template(messages, tokenize=True,
                                                    add_generation_prompt=True, return_tensors="pt")
        prompt = self._validate_tokens(prompt)
        n = prompt.shape[1]
        if n + max_new_tokens > self.model.config.max_position_embeddings:
            raise ValueError("Prompt plus generation cap exceeds context limit")
        self._request_memory(n + max_new_tokens, use_cache=True)
        feature_ids = self.default_feature_ids if intervention is None else intervention["feature_ids"]
        eos = self.model.generation_config.eos_token_id
        eos = set(eos if isinstance(eos, (list, tuple)) else [eos]) - {None}
        if self.tokenizer.eos_token_id is not None:
            eos.add(self.tokenizer.eos_token_id)
        generator = torch.Generator(device=self.device).manual_seed(seed)
        result, records = self._forward(prompt, feature_ids, intervention,
                                        use_cache=True, prompt_length=n)
        batches = [records]
        sampled = []
        for _ in range(max_new_tokens):
            logits = self.model.get_output_embeddings()(result.last_hidden_state[:, -1]).float()
            _finite("generation logits", logits)
            if temperature == 0:
                token = logits.argmax(-1).item()
            else:
                probabilities = torch.softmax(logits / temperature, dim=-1)
                _finite("sampling probabilities", probabilities)
                if top_p < 1:
                    probabilities = nucleus(probabilities, top_p)
                token = torch.multinomial(probabilities, 1, generator=generator).item()
            sampled.append(token)
            result, new_records = self._forward(
                torch.tensor([[token]], device=self.device), feature_ids, intervention,
                offset=n + len(sampled) - 1, prompt_length=n, past=result.past_key_values,
                use_cache=True)
            batches.append(new_records)
            if token in eos:
                break
        batches[-1]["position_metadata"][-1]["terminal_observation_only"] = True
        return {"response": self.tokenizer.decode(sampled, skip_special_tokens=True),
                "input_tokens": n, "output_tokens": len(sampled),
                "cap_hit": len(sampled) == max_new_tokens and sampled[-1] not in eos,
                "input_token_ids": prompt[0].tolist(), "output_token_ids": sampled,
                "rendered_input_sha256": hashlib.sha256(rendered.encode()).hexdigest(),
                "input_token_ids_sha256": hashlib.sha256(json.dumps(prompt[0].tolist()).encode()).hexdigest(),
                "telemetry": self._telemetry(feature_ids, batches, intervention),
                "top_p": float(top_p), "rendered_utc_date": rendered_utc_date,
                "elapsed_seconds": time.perf_counter() - started}

    @torch.inference_mode()
    def answer_nll(self, input_token_ids, output_token_ids):
        """Unsteered, unhooked mean NLL of the output tokens given the prompt."""
        self._assert_resident()
        parts = [list(v) for v in (input_token_ids, output_token_ids)]
        if not all(parts) or any(type(i) is not int for p in parts for i in p):
            raise ValueError("Answer NLL needs nonempty integer prompt and output IDs")
        tokens = self._validate_tokens(torch.tensor([parts[0] + parts[1]], dtype=torch.long))
        self._request_memory(tokens.shape[1], use_cache=False)
        if self._layer._forward_hooks:
            raise RuntimeError("Hooks registered during the clean forward")
        hidden = self.model.model(input_ids=tokens, attention_mask=torch.ones_like(tokens),
                                  use_cache=False, return_dict=True).last_hidden_state
        _finite("clean hidden", hidden)
        nll, _, _ = self._losses(hidden, hidden, tokens)
        answer = nll[len(parts[0]):]
        return sum(answer) / len(answer)

    @torch.inference_mode()
    def qualify(self):
        f = self.default_feature_ids[0]
        messages = [{"role": "user", "content": "Name the number after three."}]
        zero = {"feature_ids": [f], "coefficient": 0., "scope": "all", "op": "add",
                "turn": 1, "assistant_spans": []}
        plain = self.generate(messages, 81, .6, 4)
        steered = self.generate(messages, 81, .6, 4, zero)
        # Plain re-encodes every default feature; keep only the probed column.
        column = [{"position": r["position"], "before": r["before"][:1], "after": r["after"][:1]}
                  for r in plain["telemetry"]["reencoding"]]
        if (plain["output_token_ids"] != steered["output_token_ids"]
                or column != steered["telemetry"]["reencoding"] or any(
                plain["telemetry"][k] != steered["telemetry"][k] for k in ("position_metadata", "delivery"))):
            raise ValueError("True zero generation mismatch")
        tokens = self._validate_tokens(torch.tensor([plain["input_token_ids"]]))
        outside = self.model.model(input_ids=tokens, attention_mask=torch.ones_like(tokens),
                                   use_cache=False, return_dict=True).last_hidden_state
        for arm in (None, zero):
            inside, _ = self._forward(tokens, [f], arm)
            if not torch.equal(outside, inside.last_hidden_state):
                raise ValueError("No-hook versus zero-hook mismatch")
        inside, _ = self._forward(tokens, [f], dict(zero, op="recon_add"))
        if torch.equal(outside, inside.last_hidden_state):
            raise ValueError("Reconstruction zero equals identity")
        n = tokens.shape[1]
        if n < 4:
            raise ValueError("Probe prompt too short for scope masks")
        prompt_length, masks = n - 2, {}
        for scope in SCOPES:
            for turn in (1, 2):
                spans = [[1, 2]] if turn == 2 else []
                arm = {"feature_ids": [f], "coefficient": COEFFICIENT_MAX, "scope": scope,
                       "op": "add", "turn": turn, "assistant_spans": spans}
                _, records = self._forward(tokens, [f], arm, prompt_length=prompt_length)
                declared = scope_mask(scope, turn, spans, 0, n, prompt_length)
                observed = {k: [v > 0 for v in records["delivery"][k]] for k in ("requested_norm", "realized_norm")}
                if (observed["requested_norm"] != declared or observed["realized_norm"] != declared
                        or records["edited_positions"] != sum(declared)):
                    raise ValueError(f"Scope mask mismatch: {scope} turn {turn}")
                masks[f"{scope}:{turn}"] = [int(v) for v in declared]
        base = ModelBackend.generate(self, messages, 81, .6, 4)
        if base["output_token_ids"] != plain["output_token_ids"]:
            raise ValueError("Sampler mismatch at top_p 1")
        return {"pass": True, "zero_output_equal": True, "zero_hidden_bit_exact": True,
                "recon_zero_differs": True, "sampler_bit_identical": True,
                "probe": {"prompt_length": prompt_length, "positions": n, "assistant_spans": [[1, 2]]},
                "masks": masks, "plain": plain, "zero": steered}

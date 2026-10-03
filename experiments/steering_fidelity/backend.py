"""Pinned native-BF16 additive steering and one-prefill Yes/No scoring.

The production loader, full resident SAE, additive arithmetic and zero checks
are inherited from the source replication. No protocol import or generation is
needed for score(). The twelve literal answer variants below are part of the
measurement: every variant must encode to one non-special ID, with no Yes/No
overlap. Duplicate IDs within a class are counted once, never dropped variants.

score() returns unconditional p_yes/p_no, valid_mass, and p_correct conditional
on the union of those IDs. correct is p_correct > .5 (ties are incorrect),
independently of format_valid, which checks the full-vocabulary argmax.
predicted_answer breaks class ties toward Yes for display only. Zero valid
mass raises an error, never a fabricated probability or denial. The decoded
top_token is an observation, not generated text.
The model/head stay native; softmax and class sums use FP64 to protect tiny
choice masses. A class-union overshoot of at most eight FP64 epsilons is
renormalized to one; larger probability errors stop the request.

delivery_raw and telemetry.delivery retain every prompt position, including
specials. delivery summarizes only non-special positions, separates zero
requests, and assigns no fidelity gate. screen.residual_norms follows the
non-special positions in telemetry.position_metadata, in prompt order.
before_request, if set, is a zero-argument deadline callback before EVERY
source-hooked forward, including generate()/qualify(); score also checks it
before serialization. The inherited qualification's direct unhooked zero
reference is unchanged. Generation remains available for separate JSON-liveness
checks, not experience reports.
"""
from __future__ import annotations

import hashlib
import json
import math
import time
from collections.abc import Mapping

import torch
import torch.nn.functional as F

from experiments.berg_source_replication.backend import Backend as SourceBackend
from experiments.sae_assay_diagnostic.backend import _finite, _fp32_math, _ids


YES_VARIANTS = ("Yes", "yes", "YES", " Yes", " yes", " YES")
NO_VARIANTS = ("No", "no", "NO", " No", " no", " NO")


def _positive(value, name):
    if (type(value) not in (int, float) or not math.isfinite(value) or value <= 0):
        raise ValueError(f"{name} must be finite and positive")
    return float(value)


class Backend(SourceBackend):
    before_request = None

    def __init__(self, precision="bf16", cache_dir=None, device="cuda"):
        if precision != "bf16":
            raise ValueError("Steering fidelity requires native BF16, not quantization")
        super().__init__(precision=precision, cache_dir=cache_dir, device=device)

    def _spec(self, intervention):
        if intervention is None:
            return None
        if not isinstance(intervention, Mapping):
            raise ValueError("Intervention must be a mapping or None")
        if not isinstance(intervention.get("feature_ids"), list):
            raise ValueError("feature_ids must be a list")
        if set(intervention) == {"feature_ids", "coefficient"}:
            _ids(intervention["feature_ids"], self._sae[0].shape[0])
            coefficient = intervention["coefficient"]
            if type(coefficient) not in (int, float) or coefficient != 0:
                raise ValueError("Only exact legacy coefficient zero is supported")
            return None
        if set(intervention) != {"feature_ids", "weights", "sign", "requested_norm"}:
            raise ValueError("Unknown weighted additive fields")
        ids = _ids(intervention["feature_ids"], self._sae[0].shape[0])
        weights = intervention["weights"]
        if not isinstance(weights, list) or len(weights) != len(ids):
            raise ValueError("weights must be a list matching feature_ids")
        weights = [_positive(w, "weight") for w in weights]
        sign = intervention["sign"]
        if type(sign) is not int or sign not in (-1, 1):
            raise ValueError("sign must be -1 or 1")
        norm = intervention["requested_norm"]
        if norm is not None:
            norm = _positive(norm, "requested_norm")
        return {"feature_ids": list(ids), "weights": weights,
                "sign": sign, "requested_norm": norm}

    @torch.inference_mode()
    def vector(self, intervention):
        spec = self._spec(intervention)
        if spec is None:
            return torch.zeros(self.model.config.hidden_size, device=self.device,
                               dtype=torch.float32)
        with _fp32_math(self.device):
            weights = torch.tensor(spec["weights"], device=self.device, dtype=torch.float32)
            if not bool(torch.isfinite(weights).all() & (weights > 0).all()):
                raise ValueError("weights must remain finite and positive in FP32")
            # Preserve caller column order and sum in FP32, before any native cast.
            direction = (self._sae[2][:, spec["feature_ids"]].float() * weights).sum(1)
            _finite("weighted decoder direction", direction)
            if spec["requested_norm"] is not None:
                requested = torch.tensor(spec["requested_norm"], device=self.device, dtype=torch.float32)
                if not bool(torch.isfinite(requested)) or requested.item() <= 0:
                    raise ValueError("requested_norm must remain finite and positive in FP32")
                norm = direction.norm()
                if not bool(torch.isfinite(norm)) or norm.item() <= 0:
                    raise ValueError("Cannot normalize a zero or nonfinite decoder direction")
                direction = (direction / norm) * requested
                if not bool(torch.count_nonzero(direction)):
                    raise ValueError("requested_norm underflows the FP32 direction")
            vector = direction * spec["sign"]
            _finite("additive vector", vector)
        return vector

    @torch.inference_mode()
    def feature_norms(self, feature_ids=None):
        """FP32 decoder-column norms, in requested order (all IDs if omitted)."""
        self._assert_resident()
        ids = (tuple(range(self._sae[0].shape[0])) if feature_ids is None
               else _ids(feature_ids, self._sae[0].shape[0]))
        result = []
        with _fp32_math(self.device):
            for start in range(0, len(ids), 256):
                columns = self._sae[2][:, list(ids[start:start + 256])].float()
                norms = torch.linalg.vector_norm(columns, dim=0)
                _finite("decoder norms", norms)
                result.extend(norms.cpu().tolist())
        return result

    @torch.inference_mode()
    def decoder_gram(self, feature_ids):
        """Small FP32 Gram matrix in supplied ID order; no decoder columns returned."""
        self._assert_resident()
        ids = _ids(feature_ids, self._sae[0].shape[0])
        with _fp32_math(self.device):
            columns = self._sae[2][:, list(ids)].float()
            gram = columns.T @ columns
            _finite("decoder Gram matrix", gram)
        return gram.cpu().tolist()

    def _check_deadline(self):
        if self.before_request is not None:
            self.before_request()

    def _forward(self, *args, **kwargs):
        self._check_deadline()
        with torch.autocast(device_type=self.device.type, enabled=False):
            return super()._forward(*args, **kwargs)

    def generate(self, messages, seed, temperature, max_new_tokens=256, intervention=None):
        with torch.autocast(device_type=self.device.type, enabled=False):
            return super().generate(messages, seed, temperature, max_new_tokens, intervention)

    def _telemetry(self, ids, batches, intervention=None):
        result = super()._telemetry(ids, batches, None)
        result.pop("coefficient")
        result.update(schema="steering_fidelity_additive_v1",
                      intervention=self._spec(intervention),
                      native_dtype=str(self.dtype),
                      encoding_authority=self.metadata["encoding_authority"])
        return result

    def _token_sets(self, token_sets):
        if token_sets is not None and not self.metadata.get("test_only", False):
            raise ValueError("Explicit token_sets are test-only; production derives every variant")
        if token_sets is None:
            cached = getattr(self, "_answer_token_sets", None)
            if cached is not None:
                return {k: list(v) for k, v in cached.items()}
            token_sets = {}
            for label, variants in (("yes", YES_VARIANTS), ("no", NO_VARIANTS)):
                ids = []
                for variant in variants:
                    encoded = self.tokenizer.encode(variant, add_special_tokens=False)
                    if len(encoded) != 1:
                        raise ValueError(f"Answer variant {variant!r} must encode to exactly one token")
                    ids.append(encoded[0])
                token_sets[label] = list(dict.fromkeys(ids))
            derived = True
        else:
            derived = False
        if not isinstance(token_sets, Mapping) or set(token_sets) != {"yes", "no"}:
            raise ValueError("token_sets must contain exactly yes and no")
        checked = {}
        for label, values in token_sets.items():
            if not isinstance(values, (list, tuple)):
                raise ValueError("Answer token IDs must be lists or tuples")
            checked[label] = list(_ids(values, self.model.config.vocab_size))
        if set(checked["yes"]) & set(checked["no"]):
            raise ValueError("Yes/No token sets overlap")
        if (set(checked["yes"]) | set(checked["no"])) & set(self.tokenizer.all_special_ids):
            raise ValueError("Answer token sets contain special tokens")
        if derived:
            self._answer_token_sets = {k: tuple(v) for k, v in checked.items()}
        return checked

    @staticmethod
    def _delivery_summary(telemetry):
        raw = telemetry["delivery"]
        positions = [i for i, p in enumerate(telemetry["position_metadata"]) if not p["special"]]
        nonzero = [i for i in positions if raw["requested_norm"][i] > 0]
        metrics = {}
        for key, values in raw.items():
            chosen = [values[i] for i in nonzero]
            if any(not math.isfinite(v) for v in values):
                raise FloatingPointError(f"Nonfinite delivery {key}")
            metrics[key] = ({"min": min(chosen), "mean": math.fsum(chosen) / len(chosen),
                             "max": max(chosen)} if chosen else None)
        return {"scope": "non_special_prompt_positions", "positions": positions,
                "n_positions": len(positions), "nonzero_positions": nonzero,
                "n_nonzero_requested": len(nonzero),
                "n_zero_requested": len(positions) - len(nonzero), "metrics": metrics}

    @torch.inference_mode()
    def score(self, messages, truth, intervention=None, screen=False, *, token_sets=None):
        """Score one unpadded chat; truth is bool, token_sets overrides are test-only.

        Screening adds one full-width, one-position native SAE encoding of the
        CLEAN last non-special prompt residual. Ordinary source re-encoding
        still observes the last prompt position (even if special), before/after
        the edit, and only returns the default six columns in production.
        """
        started = time.perf_counter()
        self._check_deadline()
        self._assert_resident()
        if type(truth) is not bool or type(screen) is not bool:
            raise ValueError("truth and screen must be bool")
        if not self.observe:
            raise ValueError("Scoring requires native re-encoding observations")
        spec = self._spec(intervention)
        choices = self._token_sets(token_sets)
        rendered = self.tokenizer.apply_chat_template(messages, tokenize=False,
                                                       add_generation_prompt=True)
        prompt = self._validate_tokens(self.tokenizer.apply_chat_template(
            messages, tokenize=True, add_generation_prompt=True, return_tensors="pt"))
        input_ids = prompt[0].tolist()
        special = set(self.tokenizer.all_special_ids)
        positions = [i for i, token in enumerate(input_ids) if token not in special]
        if screen and not positions:
            raise ValueError("Screen requires a non-special prompt token")
        self._request_memory(len(input_ids), use_cache=False)
        screen_result, screen_calls = None, 0

        def capture_clean(_module, _inputs, output):
            nonlocal screen_result, screen_calls
            screen_calls += 1
            hidden = output[0] if isinstance(output, tuple) else output
            if screen_calls != 1 or hidden.shape[:2] != prompt.shape or hidden.dtype != self.dtype:
                raise ValueError("Clean screen hook shape/dtype/call mismatch")
            last = positions[-1]
            activations = F.relu(F.linear(hidden[:, last], self._sae[0], self._sae[1]))[0]
            _finite("screen full native activations", activations)
            positive = torch.nonzero(activations > 0, as_tuple=True)[0]
            norms = torch.linalg.vector_norm(hidden[0, positions].float(), dim=-1)
            _finite("screen clean residual norms", norms)
            screen_result = {"positive_ids": positive.cpu().tolist(),
                             "positive_values": activations[positive].float().cpu().tolist(),
                             "position": last, "residual_norms": norms.cpu().tolist()}

        # Registered first: the SourceBackend hook must never feed edited h here.
        handle = self._layer.register_forward_hook(capture_clean) if screen else None
        try:
            with torch.autocast(device_type=self.device.type, enabled=False):
                result, records = self._forward(prompt, self.default_feature_ids, spec,
                                                prompt_length=len(input_ids), use_cache=False)
                logits = self.model.get_output_embeddings()(result.last_hidden_state[:, -1])[0].float()
        finally:
            if handle is not None:
                handle.remove()
        if screen and screen_calls != 1:
            raise ValueError("Missing clean screening hook")
        _finite("choice logits", logits)
        probabilities = torch.softmax(logits.double(), dim=-1)
        _finite("choice probabilities", probabilities)
        p_yes = probabilities[choices["yes"]].sum().item()
        p_no = probabilities[choices["no"]].sum().item()
        valid_mass = p_yes + p_no
        if valid_mass <= 0:
            raise FloatingPointError("Zero Yes/No valid mass; no conditional score")
        if valid_mass > 1:
            if valid_mass > 1 + 8 * torch.finfo(torch.float64).eps:
                raise FloatingPointError("Yes/No valid mass exceeds one")
            p_yes /= valid_mass
            p_no = 1 - p_yes
            valid_mass = 1.
        p_correct = (p_yes if truth else p_no) / valid_mass
        predicted = "Yes" if p_yes >= p_no else "No"
        top_id = logits.argmax().item()
        telemetry = self._telemetry(self.default_feature_ids, [records], spec)
        return {"p_yes": p_yes, "p_no": p_no, "valid_mass": valid_mass,
                "p_correct": p_correct, "correct": p_correct > .5,
                "predicted_answer": predicted, "truth": truth,
                "format_valid": top_id in set(choices["yes"] + choices["no"]),
                "top_token_id": top_id,
                "top_token": self.tokenizer.decode([top_id], skip_special_tokens=False),
                "token_sets": choices,
                "input_token_ids": input_ids,
                "input_token_ids_sha256": hashlib.sha256(json.dumps(input_ids).encode()).hexdigest(),
                "rendered_input_sha256": hashlib.sha256(rendered.encode()).hexdigest(),
                "delivery": self._delivery_summary(telemetry),
                "delivery_raw": telemetry["delivery"], "telemetry": telemetry,
                "screen": screen_result, "elapsed_seconds": time.perf_counter() - started}

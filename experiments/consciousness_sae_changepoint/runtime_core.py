"""Target-blind runtime primitives for the layer-50 switch experiment.

This module intentionally contains no prompts, target feature IDs, model
downloads, or outcome paths.  It provides the small pieces whose semantics
must be frozen before the confirmatory runner is allowed to see target data:

* step-indexed, hash-derived inverse-CDF sampling;
* independent KV-cache cloning and content hashes;
* a fail-closed layer-output switch hook with explicit position masks; and
* exact residual extraction from transformer-layer outputs.

PyTorch is imported lazily so plan construction and validation remain usable on
the lightweight local environment.  Model-facing functions raise a clear error
when PyTorch is absent.
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal


SAMPLER_SCHEMA_VERSION = "paired_inverse_cdf_sha256_v1"
_UNIFORM_BITS = 53
_UNIFORM_DENOMINATOR = 1 << _UNIFORM_BITS
EventTime = int | Literal["terminal"]


class RuntimeContractError(RuntimeError):
    """Raised when a runtime action violates the frozen causal contract."""


def normalize_event_time(event_time: Any) -> EventTime:
    """Validate the runtime event-time identity, including terminal probes."""

    if event_time == "terminal":
        return "terminal"
    if isinstance(event_time, bool) or not isinstance(event_time, int):
        raise TypeError("event_time must be an integer or 'terminal'")
    if event_time < -1:
        raise ValueError("integer event_time cannot be less than -1")
    return event_time


@dataclass(frozen=True)
class ResolvedEventTime:
    """A planned event label and the concrete branch state it resolves to."""

    event_time: EventTime
    resolved_step: int
    terminal_reason: str | None


def resolve_probe_event_times(
    event_times: Sequence[EventTime],
    *,
    generated_token_count: int,
    terminal_reason: Literal["eos", "cap"],
) -> tuple[ResolvedEventTime, ...]:
    """Resolve branch probes without inventing post-EOS observations.

    Positive fixed probes are present only when that many post-event tokens were
    generated.  The ``terminal`` label is always retained and resolves to the
    first EOS state or the 64-token cap state supplied by the caller.  It stays
    a distinct label even when it resolves to the same step as ``+4`` or ``+16``.
    """

    if isinstance(generated_token_count, bool) or not isinstance(
        generated_token_count, int
    ):
        raise TypeError("generated_token_count must be an integer")
    if generated_token_count < 0:
        raise ValueError("generated_token_count cannot be negative")
    if terminal_reason not in {"eos", "cap"}:
        raise ValueError("terminal_reason must be 'eos' or 'cap'")

    resolved: list[ResolvedEventTime] = []
    seen: set[EventTime] = set()
    for raw_event_time in event_times:
        event_time = normalize_event_time(raw_event_time)
        if event_time in seen:
            raise ValueError(f"duplicate event_time: {event_time!r}")
        seen.add(event_time)
        if event_time == "terminal":
            resolved.append(
                ResolvedEventTime(
                    event_time="terminal",
                    resolved_step=generated_token_count,
                    terminal_reason=terminal_reason,
                )
            )
        elif event_time <= 0 or event_time <= generated_token_count:
            resolved.append(
                ResolvedEventTime(
                    event_time=event_time,
                    resolved_step=event_time,
                    terminal_reason=None,
                )
            )
    if "terminal" not in seen:
        raise RuntimeContractError("probe schedule must include a terminal event")
    return tuple(resolved)


def _torch() -> Any:
    try:
        import torch
    except ImportError as exc:  # pragma: no cover - exercised on GPU runtime
        raise RuntimeError(
            "PyTorch is required for model-facing consciousness-SAE runtime code"
        ) from exc
    return torch


def _canonical_sampling_payload(
    sampling_domain_hash: str,
    prefix_seed: int,
    paired_stream_id: str,
    decode_step: int,
) -> bytes:
    """Encode the frozen four-field sampling key without delimiter ambiguity."""

    if (
        not isinstance(sampling_domain_hash, str)
        or len(sampling_domain_hash) != 64
        or any(character not in "0123456789abcdef" for character in sampling_domain_hash)
    ):
        raise ValueError("sampling_domain_hash must be 64 lowercase hex digits")
    if isinstance(prefix_seed, bool) or not isinstance(prefix_seed, int):
        raise TypeError("prefix_seed must be an integer")
    if not isinstance(paired_stream_id, str) or not paired_stream_id:
        raise ValueError("paired_stream_id must be a non-empty string")
    if isinstance(decode_step, bool) or not isinstance(decode_step, int):
        raise TypeError("decode_step must be an integer")
    if decode_step < 0:
        raise ValueError("decode_step must be non-negative")

    # A JSON array fixes field order and types.  No branch name, execution
    # position, batch index, or mutable RNG state enters this key.
    return json.dumps(
        [sampling_domain_hash, prefix_seed, paired_stream_id, decode_step],
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")


@dataclass(frozen=True)
class UniformReceipt:
    """Auditable result of the frozen SHA-256-to-uniform transformation."""

    schema_version: str
    digest_sha256: str
    numerator: int
    denominator: int
    uniform: float

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "digest_sha256": self.digest_sha256,
            "numerator": self.numerator,
            "denominator": self.denominator,
            "uniform": self.uniform,
        }


def hash_uniform_receipt(
    *,
    sampling_domain_hash: str,
    prefix_seed: int,
    paired_stream_id: str,
    decode_step: int,
) -> UniformReceipt:
    """Return a deterministic variate in ``[0, 1)`` for one decode step.

    The first 53 digest bits are interpreted as an unsigned integer and divided
    by ``2**53``.  Using exactly 53 bits makes the conversion lossless in an
    IEEE-754 binary64 value and straightforward to reproduce in other
    languages.  The receipt stores the integer representation, so downstream
    audits need not rely on decimal float formatting.
    """

    payload = _canonical_sampling_payload(
        sampling_domain_hash, prefix_seed, paired_stream_id, decode_step
    )
    digest = hashlib.sha256(payload).digest()
    numerator = int.from_bytes(digest[:8], "big") >> (64 - _UNIFORM_BITS)
    return UniformReceipt(
        schema_version=SAMPLER_SCHEMA_VERSION,
        digest_sha256=digest.hex(),
        numerator=numerator,
        denominator=_UNIFORM_DENOMINATOR,
        uniform=numerator / _UNIFORM_DENOMINATOR,
    )


def hash_uniform(
    *,
    sampling_domain_hash: str,
    prefix_seed: int,
    paired_stream_id: str,
    decode_step: int,
) -> float:
    """Convenience wrapper returning only the deterministic uniform variate."""

    return hash_uniform_receipt(
        sampling_domain_hash=sampling_domain_hash,
        prefix_seed=prefix_seed,
        paired_stream_id=paired_stream_id,
        decode_step=decode_step,
    ).uniform


@dataclass(frozen=True)
class SampleDecision:
    """One sampled token and the immutable noise receipt that selected it."""

    token_id: int
    token_probability: float
    candidate_count: int
    temperature: float
    top_p: float
    top_k: int | None
    uniform_receipt: UniformReceipt

    def as_dict(self) -> dict[str, Any]:
        return {
            "token_id": self.token_id,
            "token_probability": self.token_probability,
            "candidate_count": self.candidate_count,
            "temperature": self.temperature,
            "top_p": self.top_p,
            "top_k": self.top_k,
            "uniform_receipt": self.uniform_receipt.as_dict(),
        }


def inverse_cdf_sample(
    logits: Any,
    *,
    sampling_domain_hash: str,
    prefix_seed: int,
    paired_stream_id: str,
    decode_step: int,
    temperature: float,
    top_p: float = 1.0,
    top_k: int | None = None,
) -> SampleDecision:
    """Sample a one-dimensional logit vector using step-indexed shared noise.

    Candidate probabilities and their cumulative sum are computed in float64.
    Stable descending sorting gives smaller token IDs priority when logits tie.
    Because the random variate is a pure function of the four-key tuple, branch
    order, batching, an EOS in another branch, interruption, and resume cannot
    advance or otherwise perturb this stream.
    """

    torch = _torch()
    if not isinstance(logits, torch.Tensor):
        raise TypeError("logits must be a torch.Tensor")
    if logits.ndim != 1 or logits.numel() == 0:
        raise ValueError("logits must be a non-empty one-dimensional tensor")
    if not math.isfinite(float(temperature)) or temperature <= 0:
        raise ValueError("temperature must be finite and strictly positive")
    if not math.isfinite(float(top_p)) or not 0 < top_p <= 1:
        raise ValueError("top_p must be in (0, 1]")
    if top_k is not None:
        if isinstance(top_k, bool) or not isinstance(top_k, int) or top_k <= 0:
            raise ValueError("top_k must be None or a positive integer")

    detached = logits.detach()
    if bool(torch.isnan(detached).any()) or bool(torch.isposinf(detached).any()):
        raise RuntimeContractError("logits contain NaN or positive infinity")
    if not bool(torch.isfinite(detached).any()):
        raise RuntimeContractError("logits contain no finite candidate")

    scaled = detached.to(dtype=torch.float64) / float(temperature)
    token_ids = torch.arange(scaled.numel(), device=scaled.device, dtype=torch.long)

    if top_k is not None or top_p < 1.0:
        # Stable sorting preserves the ascending token_ids order for exact ties.
        order = torch.argsort(scaled, descending=True, stable=True)
        if top_k is not None:
            order = order[: min(top_k, int(order.numel()))]
        candidate_logits = scaled.index_select(0, order)
        if top_p < 1.0:
            provisional = torch.softmax(candidate_logits, dim=0)
            provisional_cdf = torch.cumsum(provisional, dim=0)
            cutoff = int(
                torch.searchsorted(
                    provisional_cdf,
                    torch.tensor(top_p, dtype=torch.float64, device=scaled.device),
                    right=False,
                ).item()
            )
            order = order[: min(cutoff + 1, int(order.numel()))]
            candidate_logits = scaled.index_select(0, order)
        token_ids = token_ids.index_select(0, order)
    else:
        candidate_logits = scaled

    probabilities = torch.softmax(candidate_logits, dim=0)
    if not bool(torch.isfinite(probabilities).all()):
        raise RuntimeContractError("sampling probabilities are non-finite")
    total = float(probabilities.sum().item())
    if not math.isfinite(total) or total <= 0:
        raise RuntimeContractError("sampling distribution has zero mass")

    receipt = hash_uniform_receipt(
        sampling_domain_hash=sampling_domain_hash,
        prefix_seed=prefix_seed,
        paired_stream_id=paired_stream_id,
        decode_step=decode_step,
    )
    cumulative = torch.cumsum(probabilities, dim=0)
    # ``right=True`` implements min{i: CDF[i] > u}; this skips any zero-mass
    # leading candidates when u is exactly zero.
    selected_index = int(
        torch.searchsorted(
            cumulative,
            torch.tensor(receipt.uniform, dtype=torch.float64, device=scaled.device),
            right=True,
        ).item()
    )
    selected_index = min(selected_index, int(token_ids.numel()) - 1)
    return SampleDecision(
        token_id=int(token_ids[selected_index].item()),
        token_probability=float(probabilities[selected_index].item()),
        candidate_count=int(token_ids.numel()),
        temperature=float(temperature),
        top_p=float(top_p),
        top_k=top_k,
        uniform_receipt=receipt,
    )


def _is_tensor(value: Any) -> bool:
    try:
        torch = _torch()
    except RuntimeError:
        return False
    return isinstance(value, torch.Tensor)


def _clone_tree(value: Any) -> Any:
    if _is_tensor(value):
        return value.detach().clone()
    if isinstance(value, tuple):
        cloned = tuple(_clone_tree(item) for item in value)
        if hasattr(value, "_fields"):
            return type(value)(*cloned)
        return cloned
    if isinstance(value, list):
        return [_clone_tree(item) for item in value]
    if isinstance(value, Mapping):
        cloned_items = [(key, _clone_tree(item)) for key, item in value.items()]
        try:
            return type(value)(cloned_items)
        except (TypeError, ValueError):
            return dict(cloned_items)
    return copy.deepcopy(value)


def _legacy_cache_view(cache: Any) -> Any | None:
    converter = getattr(cache, "to_legacy_cache", None)
    if not callable(converter):
        return None
    try:
        return converter()
    except (AttributeError, NotImplementedError, TypeError):
        return None


def clone_kv_cache(cache: Any) -> Any:
    """Deep-clone a legacy tuple or a Transformers cache object.

    For ``DynamicCache``-style objects, the public legacy conversion API is
    preferred because it is stable across several Transformers releases.  If
    reconstruction is unavailable, ``deepcopy`` is attempted, followed by a
    conservative copy of the common ``key_cache``/``value_cache`` attributes.
    No returned tensor intentionally aliases the source.
    """

    if cache is None:
        return None
    if isinstance(cache, (tuple, list, Mapping)) or _is_tensor(cache):
        return _clone_tree(cache)

    legacy = _legacy_cache_view(cache)
    constructor = getattr(type(cache), "from_legacy_cache", None)
    if legacy is not None and callable(constructor):
        cloned_legacy = _clone_tree(legacy)
        try:
            return constructor(cloned_legacy)
        except TypeError:
            # Some releases expose this as an instance method despite its name.
            pass

    try:
        return copy.deepcopy(cache)
    except (TypeError, RuntimeError):
        pass

    if hasattr(cache, "key_cache") and hasattr(cache, "value_cache"):
        cloned = copy.copy(cache)
        cloned.key_cache = _clone_tree(cache.key_cache)
        cloned.value_cache = _clone_tree(cache.value_cache)
        return cloned
    raise TypeError(f"Unsupported KV-cache type: {type(cache)!r}")


def _tensor_bytes(tensor: Any, *, chunk_bytes: int = 8 * 1024 * 1024) -> Any:
    """Yield canonical little chunks of a contiguous tensor's raw bytes."""

    torch = _torch()
    cpu = tensor.detach().contiguous().to(device="cpu")
    raw = cpu.view(torch.uint8).reshape(-1)
    for start in range(0, int(raw.numel()), chunk_bytes):
        chunk = raw[start : start + chunk_bytes]
        try:
            # Viewing as uint8 also works for BF16, which has no native NumPy
            # scalar type.  NumPy is the fast path on the RunPod runtime.
            yield chunk.numpy().tobytes(order="C")
        except RuntimeError as exc:
            if "Numpy is not available" not in str(exc):
                raise
            # PyTorch tensors also implement bytes(tensor); retain this fallback
            # so the synthetic gates run in a minimal target-blind environment.
            yield bytes(chunk)


def tensor_sha256(tensor: Any) -> str:
    """Hash tensor dtype, shape, and raw contiguous bytes."""

    if not _is_tensor(tensor):
        raise TypeError("tensor_sha256 expects a torch.Tensor")
    digest = hashlib.sha256()
    metadata = {
        "dtype": str(tensor.dtype),
        "shape": list(tensor.shape),
    }
    digest.update(
        json.dumps(metadata, sort_keys=True, separators=(",", ":")).encode("utf-8")
    )
    digest.update(b"\0")
    for chunk in _tensor_bytes(tensor):
        digest.update(chunk)
    return digest.hexdigest()


def _normalized_cache_tree(cache: Any) -> Any:
    legacy = _legacy_cache_view(cache)
    if legacy is not None:
        return legacy
    if hasattr(cache, "key_cache") and hasattr(cache, "value_cache"):
        return (cache.key_cache, cache.value_cache)
    if hasattr(cache, "layers"):
        layers = []
        for layer in cache.layers:
            key = getattr(layer, "keys", getattr(layer, "key_cache", None))
            value = getattr(layer, "values", getattr(layer, "value_cache", None))
            layers.append((key, value))
        return tuple(layers)
    return cache


def cache_tensor_sha256(cache: Any) -> str:
    """Hash cache tensor content in a representation-independent tree walk.

    A ``DynamicCache`` that can round-trip through its public legacy form hashes
    identically to that legacy tuple.  Structural paths, tensor dtypes, shapes,
    and contents are included; non-tensor cache metadata is intentionally not,
    matching the protocol's *cache-tensor hash* requirement.
    """

    normalized = _normalized_cache_tree(cache)
    digest = hashlib.sha256()
    tensor_count = 0

    def visit(value: Any, path: tuple[str, ...]) -> None:
        nonlocal tensor_count
        if _is_tensor(value):
            tensor_count += 1
            digest.update(b"tensor\0")
            digest.update("/".join(path).encode("utf-8"))
            digest.update(b"\0")
            digest.update(tensor_sha256(value).encode("ascii"))
            digest.update(b"\0")
            return
        if isinstance(value, Mapping):
            for key in sorted(value, key=lambda item: str(item)):
                visit(value[key], (*path, f"key:{key}"))
            return
        if isinstance(value, (tuple, list)):
            for index, item in enumerate(value):
                visit(item, (*path, str(index)))
            return
        if value is None:
            digest.update(b"none\0")
            digest.update("/".join(path).encode("utf-8"))
            digest.update(b"\0")

    visit(normalized, ("cache",))
    if tensor_count == 0:
        raise RuntimeContractError("KV cache contains no hashable tensors")
    digest.update(f"tensor_count={tensor_count}".encode("ascii"))
    return digest.hexdigest()


# Short aliases used by runner code and receipts.
clone_cache = clone_kv_cache
cache_sha256 = cache_tensor_sha256


def extract_hidden_output(output: Any) -> Any:
    """Return the hidden-state tensor from a transformer-layer output."""

    torch = _torch()
    if isinstance(output, torch.Tensor):
        return output
    if isinstance(output, (tuple, list)) and output:
        if isinstance(output[0], torch.Tensor):
            return output[0]
    if isinstance(output, Mapping):
        for key in ("last_hidden_state", "hidden_states"):
            candidate = output.get(key)
            if isinstance(candidate, torch.Tensor):
                return candidate
    for attribute in ("last_hidden_state", "hidden_states"):
        candidate = getattr(output, attribute, None)
        if isinstance(candidate, torch.Tensor):
            return candidate
    raise TypeError(
        "layer output is not a tensor and exposes no first/last hidden-state tensor"
    )


def replace_hidden_output(output: Any, hidden: Any) -> Any:
    """Replace a layer output's hidden tensor while preserving auxiliary data."""

    torch = _torch()
    if isinstance(output, torch.Tensor):
        return hidden
    if isinstance(output, tuple):
        values = (hidden, *output[1:])
        if hasattr(output, "_fields"):
            return type(output)(*values)
        return values
    if isinstance(output, list):
        return [hidden, *output[1:]]
    if isinstance(output, Mapping):
        for key in ("last_hidden_state", "hidden_states"):
            if key in output:
                cloned = copy.copy(output)
                cloned[key] = hidden
                return cloned
    for attribute in ("last_hidden_state", "hidden_states"):
        if isinstance(getattr(output, attribute, None), torch.Tensor):
            cloned = copy.copy(output)
            setattr(cloned, attribute, hidden)
            return cloned
    raise TypeError("cannot replace hidden state in unsupported layer output")


def extract_residual_positions(
    output: Any,
    positions: int | Sequence[int] | None = None,
    *,
    batch_index: int | None = None,
    to_cpu: bool = False,
) -> Any:
    """Detach and clone exact residual positions from a layer output.

    Transformer residuals must have shape ``[batch, sequence, width]``.  With
    ``positions=None`` the complete tensor is returned.  An integer returns
    ``[batch, width]`` (or ``[width]`` when ``batch_index`` is supplied); a
    sequence returns ``[batch, n_positions, width]``.  Negative positions use
    standard Python indexing after explicit bounds validation.
    """

    torch = _torch()
    hidden = extract_hidden_output(output)
    if hidden.ndim != 3:
        raise RuntimeContractError(
            f"expected [batch, sequence, width] residual, got {tuple(hidden.shape)}"
        )
    selected = hidden
    if batch_index is not None:
        if not -hidden.shape[0] <= batch_index < hidden.shape[0]:
            raise IndexError("batch_index is outside the residual batch")
        selected = selected[batch_index]

    if positions is not None:
        scalar = isinstance(positions, int) and not isinstance(positions, bool)
        requested = [int(positions)] if scalar else list(positions)
        if not requested:
            raise ValueError("positions cannot be empty")
        sequence_length = int(hidden.shape[1])
        normalized = []
        for position in requested:
            if isinstance(position, bool) or not isinstance(position, int):
                raise TypeError("residual positions must be integers")
            adjusted = position if position >= 0 else sequence_length + position
            if not 0 <= adjusted < sequence_length:
                raise IndexError(f"residual position {position} is out of bounds")
            normalized.append(adjusted)
        position_tensor = torch.tensor(
            normalized, dtype=torch.long, device=hidden.device
        )
        sequence_dimension = 0 if batch_index is not None else 1
        selected = torch.index_select(selected, sequence_dimension, position_tensor)
        if scalar:
            selected = selected.select(sequence_dimension, 0)

    selected = selected.detach().clone()
    return selected.to("cpu") if to_cpu else selected


@dataclass
class HookCapture:
    """Exact pre/post layer-50 tensors for one explicitly armed forward."""

    forward_id: str
    event_time: EventTime | None
    pre: Any
    post: Any
    position_mask: Any


class Layer50SwitchHook:
    """Fail-closed masked addition at a transformer block's output.

    A caller must register the hook, call :meth:`arm` once before every expected
    transformer forward, and remove it after the intended active interval.  The
    armed mask addresses only positions present in that forward's layer output;
    cached positions therefore cannot be silently edited.  ``sham`` uses this
    exact path with a zero vector.
    """

    def __init__(
        self,
        intervention: Any,
        *,
        capture_to_cpu: bool = True,
    ) -> None:
        torch = _torch()
        if not isinstance(intervention, torch.Tensor):
            raise TypeError("intervention must be a torch.Tensor")
        if intervention.ndim != 1 or intervention.numel() == 0:
            raise ValueError("intervention must be a non-empty width vector")
        if not intervention.is_floating_point():
            raise TypeError("intervention must have a floating dtype")
        if not bool(torch.isfinite(intervention).all()):
            raise RuntimeContractError("intervention contains non-finite values")

        self.intervention = intervention.detach().clone()
        self.capture_to_cpu = bool(capture_to_cpu)
        self._handle: Any | None = None
        self._pending: dict[str, Any] | None = None
        self.registration_count = 0
        self.hook_call_count = 0
        self.removal_count = 0
        self.selected_position_count = 0
        self.captures: list[HookCapture] = []
        self.call_receipts: list[dict[str, Any]] = []

    @property
    def registered(self) -> bool:
        return self._handle is not None

    @property
    def pending_forward_id(self) -> str | None:
        return None if self._pending is None else str(self._pending["forward_id"])

    def register(self, layer_module: Any) -> "Layer50SwitchHook":
        if self.registered:
            raise RuntimeContractError("layer-50 hook is already registered")
        if self.registration_count:
            raise RuntimeContractError("a Layer50SwitchHook instance cannot be reused")
        register = getattr(layer_module, "register_forward_hook", None)
        if not callable(register):
            raise TypeError("layer_module does not support register_forward_hook")
        self._handle = register(self._hook)
        self.registration_count += 1
        return self

    def arm(
        self,
        position_mask: Any,
        *,
        forward_id: str,
        event_time: EventTime | None = None,
    ) -> None:
        """Arm exactly one forthcoming layer call with an explicit mask."""

        torch = _torch()
        if not self.registered:
            raise RuntimeContractError("cannot arm an unregistered layer-50 hook")
        if self._pending is not None:
            raise RuntimeContractError(
                f"forward {self._pending['forward_id']!r} is still armed"
            )
        if not isinstance(forward_id, str) or not forward_id:
            raise ValueError("forward_id must be a non-empty string")
        if any(row["forward_id"] == forward_id for row in self.call_receipts):
            raise RuntimeContractError(f"forward_id was already consumed: {forward_id}")
        normalized_event_time = (
            None if event_time is None else normalize_event_time(event_time)
        )

        if isinstance(position_mask, torch.Tensor):
            stored_mask = position_mask.detach().clone()
        else:
            try:
                stored_mask = torch.as_tensor(position_mask)
            except (TypeError, ValueError) as exc:
                raise TypeError("position_mask must be tensor-like") from exc
        self._pending = {
            "forward_id": forward_id,
            "event_time": normalized_event_time,
            "position_mask": stored_mask,
        }

    @staticmethod
    def _validated_mask(mask: Any, hidden: Any) -> Any:
        torch = _torch()
        if hidden.ndim != 3:
            raise RuntimeContractError(
                "layer-50 hidden state must have shape [batch, sequence, width]"
            )
        if mask.ndim == 1:
            if int(mask.shape[0]) != int(hidden.shape[1]):
                raise RuntimeContractError(
                    "one-dimensional position mask length differs from new sequence"
                )
            mask = mask.unsqueeze(0).expand(int(hidden.shape[0]), -1)
        elif mask.ndim == 2:
            if tuple(mask.shape) != tuple(hidden.shape[:2]):
                raise RuntimeContractError(
                    "two-dimensional position mask differs from [batch, sequence]"
                )
        else:
            raise RuntimeContractError("position mask must be one- or two-dimensional")

        if mask.dtype != torch.bool:
            if mask.is_floating_point():
                raise RuntimeContractError("position mask must be boolean or binary integer")
            valid = torch.logical_or(mask == 0, mask == 1)
            if not bool(valid.all()):
                raise RuntimeContractError("integer position mask contains values outside 0/1")
            mask = mask.to(dtype=torch.bool)
        return mask.to(device=hidden.device)

    def _hook(self, _module: Any, _inputs: Any, output: Any) -> Any:
        torch = _torch()
        if self._pending is None:
            raise RuntimeContractError(
                "registered layer-50 hook fired without an explicitly armed forward"
            )
        pending = self._pending
        # Consume before performing tensor work so a failing call cannot be
        # accidentally retried under the same receipt identity.
        self._pending = None
        forward_id = str(pending["forward_id"])
        event_time = pending["event_time"]
        hidden = extract_hidden_output(output)
        if hidden.ndim != 3:
            raise RuntimeContractError(
                f"layer-50 output shape is not [batch, sequence, width]: {hidden.shape}"
            )
        if int(hidden.shape[-1]) != int(self.intervention.numel()):
            raise RuntimeContractError(
                "intervention width differs from layer-50 hidden width"
            )
        if not hidden.is_floating_point() or not bool(torch.isfinite(hidden).all()):
            raise RuntimeContractError("layer-50 hidden state is non-finite or non-floating")

        mask = self._validated_mask(pending["position_mask"], hidden)
        vector = self.intervention.to(device=hidden.device, dtype=hidden.dtype)
        delta = mask.unsqueeze(-1).to(dtype=hidden.dtype) * vector.view(1, 1, -1)
        post = hidden + delta
        if not bool(torch.isfinite(post).all()):
            raise RuntimeContractError("layer-50 post-edit hidden state is non-finite")

        capture_pre = hidden.detach().clone()
        capture_post = post.detach().clone()
        capture_mask = mask.detach().clone()
        if self.capture_to_cpu:
            capture_pre = capture_pre.to("cpu")
            capture_post = capture_post.to("cpu")
            capture_mask = capture_mask.to("cpu")
        self.captures.append(
            HookCapture(
                forward_id=forward_id,
                event_time=event_time,
                pre=capture_pre,
                post=capture_post,
                position_mask=capture_mask,
            )
        )

        selected = int(mask.sum().item())
        self.hook_call_count += 1
        self.selected_position_count += selected
        hidden_ss = float(hidden.float().square().sum().item())
        delta_ss = float(delta.float().square().sum().item())
        self.call_receipts.append(
            {
                "forward_id": forward_id,
                "event_time": event_time,
                "call_index": self.hook_call_count - 1,
                "hidden_shape": list(hidden.shape),
                "hidden_dtype": str(hidden.dtype),
                "selected_positions": selected,
                "unselected_positions": int(mask.numel()) - selected,
                "position_mask_sha256": tensor_sha256(mask),
                "intervention_sha256": tensor_sha256(vector),
                "hidden_rms": math.sqrt(hidden_ss / hidden.numel()),
                "delta_rms": math.sqrt(delta_ss / delta.numel()),
                "relative_rms": (
                    math.sqrt(delta_ss / hidden_ss) if hidden_ss > 0 else None
                ),
                "max_abs_delta": float(delta.float().abs().max().item()),
            }
        )
        return replace_hidden_output(output, post)

    def pop_capture(self, *, expected_forward_id: str | None = None) -> HookCapture:
        if not self.captures:
            raise RuntimeContractError("no layer-50 capture is available")
        capture = self.captures.pop(0)
        if expected_forward_id is not None and capture.forward_id != expected_forward_id:
            raise RuntimeContractError(
                f"capture order mismatch: expected {expected_forward_id!r}, "
                f"got {capture.forward_id!r}"
            )
        return capture

    def remove(self) -> None:
        if not self.registered:
            raise RuntimeContractError("layer-50 hook is not registered")
        if self._pending is not None:
            raise RuntimeContractError(
                f"cannot remove hook while forward {self._pending['forward_id']!r} is armed"
            )
        self._handle.remove()
        self._handle = None
        self.removal_count += 1

    def validate_complete(self, *, expected_calls: int | None = None) -> None:
        if self.registered:
            raise RuntimeContractError("layer-50 hook remains registered")
        if self._pending is not None:
            raise RuntimeContractError("layer-50 hook retains an armed forward")
        if self.registration_count != 1 or self.removal_count != 1:
            raise RuntimeContractError(
                "hook registration/removal counts must both equal one"
            )
        if expected_calls is not None and self.hook_call_count != expected_calls:
            raise RuntimeContractError(
                f"hook calls differ: expected {expected_calls}, got {self.hook_call_count}"
            )
        if len(self.call_receipts) != self.hook_call_count:
            raise RuntimeContractError("hook call receipts are incomplete")

    def telemetry(self) -> dict[str, Any]:
        return {
            "registration_count": self.registration_count,
            "hook_call_count": self.hook_call_count,
            "removal_count": self.removal_count,
            "selected_position_count": self.selected_position_count,
            "pending_forward_id": self.pending_forward_id,
            "registered": self.registered,
            "unconsumed_captures": len(self.captures),
            "call_receipts": copy.deepcopy(self.call_receipts),
        }

    def __enter__(self) -> "Layer50SwitchHook":
        if not self.registered:
            raise RuntimeContractError(
                "register(layer_module) must be called before entering hook context"
            )
        return self

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> bool:
        if self.registered:
            # Preserve the original exception if a forward failed after consuming
            # its mask.  An unconsumed armed mask remains a protocol failure.
            if self._pending is None:
                self.remove()
            else:
                self._handle.remove()
                self._handle = None
                self.removal_count += 1
        return False


__all__ = [
    "EventTime",
    "HookCapture",
    "Layer50SwitchHook",
    "ResolvedEventTime",
    "RuntimeContractError",
    "SAMPLER_SCHEMA_VERSION",
    "SampleDecision",
    "UniformReceipt",
    "cache_sha256",
    "cache_tensor_sha256",
    "clone_cache",
    "clone_kv_cache",
    "extract_hidden_output",
    "extract_residual_positions",
    "hash_uniform",
    "hash_uniform_receipt",
    "inverse_cdf_sample",
    "normalize_event_time",
    "replace_hidden_output",
    "resolve_probe_event_times",
    "tensor_sha256",
]

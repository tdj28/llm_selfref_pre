"""Audit-only tensor hashing shim; contains no model or hook construction."""

from __future__ import annotations

import hashlib
from typing import Any

from . import protocol


def tensor_sha256(value: Any) -> str:
    """Match the frozen runtime's dtype/shape/exact-byte tensor digest."""

    import torch

    if not isinstance(value, torch.Tensor):
        raise TypeError("tensor_sha256 expects a torch.Tensor")
    cpu = value.detach().contiguous().to(device="cpu")
    digest = hashlib.sha256()
    digest.update(
        protocol.canonical_json_bytes(
            {"dtype": str(cpu.dtype), "shape": list(cpu.shape)}
        )
    )
    digest.update(b"\0")
    raw = cpu.view(torch.uint8).reshape(-1)
    for start in range(0, int(raw.numel()), 8 * 1024 * 1024):
        digest.update(raw[start : start + 8 * 1024 * 1024].numpy().tobytes())
    return digest.hexdigest()

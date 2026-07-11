"""Pinned Gemma 2 / Gemma Scope runtime shared by GPU experiment scripts."""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import math
import os
import platform
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def append_jsonl(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def runtime_metadata(torch_module: Any) -> dict[str, Any]:
    packages = {}
    for package in (
        "accelerate",
        "huggingface-hub",
        "numpy",
        "sae-lens",
        "safetensors",
        "torch",
        "transformer-lens",
        "transformers",
    ):
        try:
            packages[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            packages[package] = None
    return {
        "captured_at_utc": utc_now(),
        "python": platform.python_version(),
        "platform": platform.platform(),
        "packages": packages,
        "cuda_available": bool(torch_module.cuda.is_available()),
        "cuda_runtime": torch_module.version.cuda,
        "gpu": (
            torch_module.cuda.get_device_name(0)
            if torch_module.cuda.is_available()
            else None
        ),
    }


def torch_dtype(name: str) -> Any:
    import torch

    return {
        "float32": torch.float32,
        "float16": torch.float16,
        "bfloat16": torch.bfloat16,
    }[name]


@dataclass
class PinnedJumpReLUSAE:
    """Minimal inference loader for the exact public Gemma Scope NPZ format."""

    W_enc: Any
    W_dec: Any
    b_enc: Any
    b_dec: Any
    threshold: Any
    repo_id: str
    revision: str
    folder: str
    params_path: Path
    params_sha256: str
    dtype_name: str

    @property
    def d_in(self) -> int:
        return int(self.W_enc.shape[0])

    @property
    def d_sae(self) -> int:
        return int(self.W_enc.shape[1])

    @property
    def device(self) -> Any:
        return self.W_enc.device

    @property
    def dtype(self) -> Any:
        return self.W_enc.dtype

    @classmethod
    def load(
        cls,
        *,
        repo_id: str,
        revision: str,
        folder: str,
        device: str = "cuda",
        dtype_name: str = "bfloat16",
    ) -> "PinnedJumpReLUSAE":
        import numpy as np
        import torch
        from huggingface_hub import hf_hub_download, model_info

        resolved = model_info(repo_id, revision=revision).sha
        if resolved != revision:
            raise RuntimeError(
                f"Resolved SAE revision {resolved} differs from frozen {revision}"
            )
        path = Path(
            hf_hub_download(
                repo_id=repo_id,
                filename="params.npz",
                subfolder=folder,
                revision=revision,
            )
        )
        target_dtype = torch_dtype(dtype_name)
        with np.load(path) as data:
            keys = set(data.files)

            def load_array(*names: str) -> Any:
                for name in names:
                    if name in keys:
                        array = np.asarray(data[name])
                        return torch.from_numpy(array).to(
                            device=device, dtype=target_dtype
                        )
                raise KeyError(f"None of {names} found in {sorted(keys)}")

            W_enc = load_array("w_enc", "W_enc")
            W_dec = load_array("w_dec", "W_dec")
            b_enc = load_array("b_enc")
            b_dec = load_array("b_dec")
            if "threshold" in keys:
                threshold = load_array("threshold")
            elif "log_threshold" in keys:
                threshold = load_array("log_threshold").exp()
            else:
                raise KeyError(f"No threshold found in {sorted(keys)}")
        if W_enc.ndim != 2 or W_dec.ndim != 2:
            raise ValueError("Gemma Scope encoder and decoder must be matrices")
        if W_enc.shape[1] != W_dec.shape[0] or W_enc.shape[0] != W_dec.shape[1]:
            raise ValueError(
                f"Incompatible Gemma Scope shapes: {W_enc.shape}, {W_dec.shape}"
            )
        if b_enc.shape != (W_enc.shape[1],) or threshold.shape != (W_enc.shape[1],):
            raise ValueError("Encoder bias or threshold shape differs from SAE width")
        if b_dec.shape != (W_enc.shape[0],):
            raise ValueError("Decoder bias shape differs from SAE input width")
        if not all(
            bool(torch.isfinite(tensor).all())
            for tensor in (W_enc, W_dec, b_enc, b_dec, threshold)
        ):
            raise ValueError("Non-finite Gemma Scope parameter")
        return cls(
            W_enc=W_enc,
            W_dec=W_dec,
            b_enc=b_enc,
            b_dec=b_dec,
            threshold=threshold,
            repo_id=repo_id,
            revision=revision,
            folder=folder,
            params_path=path,
            params_sha256=sha256_file(path),
            dtype_name=dtype_name,
        )

    def encode(self, hidden: Any) -> Any:
        import torch

        pre = hidden.to(dtype=self.dtype) @ self.W_enc + self.b_enc
        return torch.relu(pre) * (pre > self.threshold).to(pre.dtype)

    def encode_selected(self, hidden: Any, feature_ids: Any) -> Any:
        import torch

        ids = torch.as_tensor(feature_ids, dtype=torch.long, device=self.device)
        pre = hidden.to(dtype=self.dtype) @ self.W_enc[:, ids] + self.b_enc[ids]
        return torch.relu(pre) * (pre > self.threshold[ids]).to(pre.dtype)

    def decode(self, features: Any) -> Any:
        return features.to(dtype=self.dtype) @ self.W_dec + self.b_dec

    def reconstruct(self, hidden: Any) -> Any:
        return self.decode(self.encode(hidden))

    def decoder_norms(self) -> Any:
        return self.W_dec.float().square().sum(dim=1).sqrt()

    def record(self) -> dict[str, Any]:
        return {
            "repo": self.repo_id,
            "revision": self.revision,
            "folder": self.folder,
            "params_path": str(self.params_path),
            "params_sha256": self.params_sha256,
            "d_in": self.d_in,
            "d_sae": self.d_sae,
            "dtype": self.dtype_name,
        }

    def unload(self) -> None:
        for name in ("W_enc", "W_dec", "b_enc", "b_dec", "threshold"):
            setattr(self, name, None)


def load_model_and_tokenizer(model_id: str, revision: str) -> tuple[Any, Any, Any]:
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer

    if not torch.cuda.is_available():
        raise RuntimeError("CUDA is required for the frozen Gemma run")
    tokenizer = AutoTokenizer.from_pretrained(model_id, revision=revision)
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token_id = tokenizer.eos_token_id
    model = AutoModelForCausalLM.from_pretrained(
        model_id,
        revision=revision,
        torch_dtype=torch.bfloat16,
        device_map={"": 0},
        low_cpu_mem_usage=True,
    )
    resolved = getattr(model.config, "_commit_hash", None)
    if resolved and resolved != revision:
        raise RuntimeError(
            f"Resolved model revision {resolved} differs from frozen {revision}"
        )
    model.eval()
    return torch, model, tokenizer


def model_layers(model: Any) -> Any:
    candidate = getattr(model, "model", None)
    if candidate is None or not hasattr(candidate, "layers"):
        raise AttributeError("Gemma model does not expose model.layers")
    return candidate.layers


def replace_hidden_output(output: Any, hidden: Any) -> Any:
    if isinstance(output, tuple):
        return (hidden, *output[1:])
    return hidden


class SteeringSession:
    """One-turn residual intervention with fail-closed telemetry."""

    def __init__(
        self,
        *,
        model: Any,
        sae: PinnedJumpReLUSAE,
        layer: int,
        feature_ids: list[int],
        active_q90: list[float],
        sign: str,
        alpha: float,
        downstream: list[
            tuple[int, PinnedJumpReLUSAE, list[int], list[float]]
        ]
        | None = None,
    ) -> None:
        import torch

        if sign not in {"suppression", "amplification", "zero"}:
            raise ValueError(f"Unknown intervention sign: {sign}")
        if len(feature_ids) != len(active_q90):
            raise ValueError("Feature IDs and active quantiles differ in length")
        self.model = model
        self.sae = sae
        self.layer = int(layer)
        self.feature_ids = [int(value) for value in feature_ids]
        self.feature_tensor = torch.tensor(
            self.feature_ids, dtype=torch.long, device=sae.device
        )
        self.active_q90 = torch.tensor(
            active_q90, dtype=sae.dtype, device=sae.device
        )
        self.sign = sign
        self.alpha = float(alpha)
        self.downstream = downstream or []
        self.handles: list[Any] = []
        self.hook_calls = 0
        self.hidden_ss = 0.0
        self.delta_ss = 0.0
        self.elements = 0
        self.max_abs_delta = 0.0
        self.max_relative_call_rms = 0.0
        self.before_sum = 0.0
        self.target_sum = 0.0
        self.after_sum = 0.0
        self.latent_elements = 0
        self.nonfinite = False
        self.relay: dict[str, dict[str, float | int]] = {}

    def _main_hook(self, _module: Any, _inputs: Any, output: Any) -> Any:
        import torch

        hidden = output[0] if isinstance(output, tuple) else output
        self.hook_calls += 1
        if self.sign == "zero" or self.alpha == 0.0:
            self.hidden_ss += float(hidden.float().square().sum().item())
            self.elements += int(hidden.numel())
            return output
        flat = hidden.reshape(-1, hidden.shape[-1])
        before = self.sae.encode_selected(flat, self.feature_tensor)
        if self.sign == "suppression":
            target = torch.zeros_like(before)
        else:
            target = torch.maximum(before, self.active_q90.unsqueeze(0))
        feature_delta = target - before
        decoder = self.sae.W_dec[self.feature_tensor]
        raw_delta = feature_delta.to(dtype=self.sae.dtype) @ decoder
        scaled_delta = raw_delta * self.alpha
        new_flat = flat + scaled_delta.to(dtype=flat.dtype)
        if not bool(torch.isfinite(new_flat).all()):
            self.nonfinite = True
            raise RuntimeError("Non-finite hidden state after Gemma SAE intervention")
        new_hidden = new_flat.reshape_as(hidden)
        after = self.sae.encode_selected(new_flat, self.feature_tensor)
        hidden_ss = float(flat.float().square().sum().item())
        delta_ss = float(scaled_delta.float().square().sum().item())
        self.hidden_ss += hidden_ss
        self.delta_ss += delta_ss
        self.elements += int(flat.numel())
        self.max_abs_delta = max(
            self.max_abs_delta, float(scaled_delta.float().abs().max().item())
        )
        if hidden_ss > 0:
            self.max_relative_call_rms = max(
                self.max_relative_call_rms, math.sqrt(delta_ss / hidden_ss)
            )
        self.before_sum += float(before.float().sum().item())
        self.target_sum += float(target.float().sum().item())
        self.after_sum += float(after.float().sum().item())
        self.latent_elements += int(before.numel())
        return replace_hidden_output(output, new_hidden)

    def _relay_hook(
        self,
        relay_layer: int,
        relay_sae: PinnedJumpReLUSAE,
        relay_ids: list[int],
        relay_q90: list[float],
    ) -> Any:
        import torch

        key = f"layer_{relay_layer}"
        q90 = torch.tensor(
            [max(float(value), 1e-8) for value in relay_q90],
            dtype=relay_sae.dtype,
            device=relay_sae.device,
        )
        self.relay[key] = {
            "activation_sum": 0.0,
            "activation_max": 0.0,
            "activation_elements": 0,
            "prompt_activation_sum": 0.0,
            "prompt_activation_max": 0.0,
            "prompt_activation_elements": 0,
            "generated_activation_sum": 0.0,
            "generated_activation_max": 0.0,
            "generated_activation_elements": 0,
            "hook_calls": 0,
        }

        def hook(_module: Any, _inputs: Any, output: Any) -> None:
            hidden = output[0] if isinstance(output, tuple) else output
            flat = hidden.reshape(-1, hidden.shape[-1])
            acts = (relay_sae.encode_selected(flat, relay_ids) / q90.unsqueeze(0)).float()
            record = self.relay[key]
            record["activation_sum"] = float(record["activation_sum"]) + float(
                acts.sum().item()
            )
            record["activation_max"] = max(
                float(record["activation_max"]), float(acts.max().item())
            )
            record["activation_elements"] = int(record["activation_elements"]) + int(
                acts.numel()
            )
            prefix = "prompt" if int(record["hook_calls"]) == 0 else "generated"
            record[f"{prefix}_activation_sum"] = float(
                record[f"{prefix}_activation_sum"]
            ) + float(acts.sum().item())
            record[f"{prefix}_activation_max"] = max(
                float(record[f"{prefix}_activation_max"]),
                float(acts.max().item()),
            )
            record[f"{prefix}_activation_elements"] = int(
                record[f"{prefix}_activation_elements"]
            ) + int(acts.numel())
            record["hook_calls"] = int(record["hook_calls"]) + 1

        return hook

    def __enter__(self) -> "SteeringSession":
        layers = model_layers(self.model)
        self.handles.append(layers[self.layer].register_forward_hook(self._main_hook))
        for relay_layer, relay_sae, relay_ids, relay_q90 in self.downstream:
            if relay_layer <= self.layer:
                raise ValueError("Relay layer must be downstream of intervention layer")
            self.handles.append(
                layers[relay_layer].register_forward_hook(
                    self._relay_hook(relay_layer, relay_sae, relay_ids, relay_q90)
                )
            )
        return self

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        for handle in reversed(self.handles):
            handle.remove()
        self.handles.clear()

    def diagnostics(self) -> dict[str, Any]:
        relative = math.sqrt(self.delta_ss / self.hidden_ss) if self.hidden_ss else 0.0
        relay = {}
        for key, record in self.relay.items():
            count = int(record["activation_elements"])
            relay[key] = {
                **record,
                "activation_mean": (
                    float(record["activation_sum"]) / count if count else None
                ),
                "prompt_activation_mean": (
                    float(record["prompt_activation_sum"])
                    / int(record["prompt_activation_elements"])
                    if int(record["prompt_activation_elements"])
                    else None
                ),
                "generated_activation_mean": (
                    float(record["generated_activation_sum"])
                    / int(record["generated_activation_elements"])
                    if int(record["generated_activation_elements"])
                    else None
                ),
            }
        return {
            "hook_registrations": 1,
            "hook_calls": self.hook_calls,
            "hook_removed": len(self.handles) == 0,
            "sign": self.sign,
            "alpha": self.alpha,
            "feature_ids": self.feature_ids,
            "steering_applied": self.sign != "zero" and self.alpha != 0.0,
            "zero_is_true_noop": self.sign != "zero" or self.delta_ss == 0.0,
            "hidden_rms": math.sqrt(self.hidden_ss / self.elements) if self.elements else None,
            "delta_rms": math.sqrt(self.delta_ss / self.elements) if self.elements else 0.0,
            "relative_hidden_delta_rms": relative,
            "max_relative_call_rms": self.max_relative_call_rms,
            "max_abs_hidden_delta": self.max_abs_delta,
            "selected_activation_before_mean": (
                self.before_sum / self.latent_elements if self.latent_elements else None
            ),
            "selected_activation_target_mean": (
                self.target_sum / self.latent_elements if self.latent_elements else None
            ),
            "selected_activation_reencoded_mean": (
                self.after_sum / self.latent_elements if self.latent_elements else None
            ),
            "nonfinite_detected": self.nonfinite,
            "relay": relay,
        }


def _chat_inputs(tokenizer: Any, messages: list[dict[str, str]], device: Any) -> Any:
    inputs = tokenizer.apply_chat_template(
        messages,
        add_generation_prompt=True,
        tokenize=True,
        return_dict=True,
        return_tensors="pt",
    )
    return {key: value.to(device) for key, value in inputs.items()}


def generate_chat_turn(
    *,
    torch_module: Any,
    model: Any,
    tokenizer: Any,
    messages: list[dict[str, str]],
    seed: int,
    temperature: float,
    top_p: float,
    max_new_tokens: int,
    intervention: dict[str, Any] | None = None,
) -> tuple[str, dict[str, Any]]:
    torch_module.manual_seed(seed)
    torch_module.cuda.manual_seed_all(seed)
    inputs = _chat_inputs(tokenizer, messages, model.device)
    if "attention_mask" not in inputs:
        inputs["attention_mask"] = torch_module.ones_like(inputs["input_ids"])
    prompt_tokens = int(inputs["input_ids"].shape[1])
    session = None
    if intervention is not None:
        session = SteeringSession(model=model, **intervention)
        session.__enter__()
    try:
        generation_kwargs = {
            "do_sample": temperature > 0,
            "max_new_tokens": max_new_tokens,
            "pad_token_id": tokenizer.pad_token_id,
            "eos_token_id": tokenizer.eos_token_id,
            "use_cache": True,
        }
        if temperature > 0:
            generation_kwargs.update(
                {"temperature": temperature, "top_p": top_p}
            )
        with torch_module.no_grad():
            generated = model.generate(
                **inputs,
                **generation_kwargs,
            )
    finally:
        if session is not None:
            session.__exit__(None, None, None)
    new_tokens = generated[0, prompt_tokens:]
    text = tokenizer.decode(new_tokens, skip_special_tokens=True).strip()
    diagnostics = session.diagnostics() if session is not None else {
        "hook_registrations": 0,
        "hook_calls": 0,
        "hook_removed": True,
        "steering_applied": False,
        "zero_is_true_noop": True,
        "relative_hidden_delta_rms": 0.0,
        "relay": {},
    }
    diagnostics.update(
        {
            "attention_mask_mode": "explicit_tokenizer_mask",
            "prompt_tokens": prompt_tokens,
            "generated_tokens": int(new_tokens.numel()),
            "cap_hit": int(new_tokens.numel()) >= max_new_tokens,
        }
    )
    return text, diagnostics


def run_two_turn(
    *,
    torch_module: Any,
    model: Any,
    tokenizer: Any,
    induction: str,
    query: str,
    seed: int,
    temperature: float,
    top_p: float,
    induction_max_tokens: int,
    final_max_tokens: int,
    intervention: dict[str, Any] | None = None,
) -> dict[str, Any]:
    induction_text, induction_diagnostics = generate_chat_turn(
        torch_module=torch_module,
        model=model,
        tokenizer=tokenizer,
        messages=[{"role": "user", "content": induction}],
        seed=seed,
        temperature=temperature,
        top_p=top_p,
        max_new_tokens=induction_max_tokens,
        intervention=intervention,
    )
    final_text, final_diagnostics = generate_chat_turn(
        torch_module=torch_module,
        model=model,
        tokenizer=tokenizer,
        messages=[
            {"role": "user", "content": induction},
            {"role": "assistant", "content": induction_text},
            {"role": "user", "content": query},
        ],
        seed=seed + 1,
        temperature=temperature,
        top_p=top_p,
        max_new_tokens=final_max_tokens,
        intervention=intervention,
    )
    return {
        "induction_response": induction_text,
        "response": final_text,
        "induction_response_sha256": sha256_text(induction_text),
        "response_sha256": sha256_text(final_text),
        "induction_diagnostics": induction_diagnostics,
        "final_diagnostics": final_diagnostics,
        "induction_cap_hit": bool(induction_diagnostics["cap_hit"]),
        "final_cap_hit": bool(final_diagnostics["cap_hit"]),
    }


def validate_steering_diagnostics(diagnostics: dict[str, Any], expect_zero: bool) -> None:
    if diagnostics.get("hook_calls", 0) < 1:
        raise RuntimeError("Steering hook was not called")
    if diagnostics.get("hook_removed") is not True:
        raise RuntimeError("Steering hook was not removed")
    if diagnostics.get("nonfinite_detected") is True:
        raise RuntimeError("Steering telemetry detected non-finite values")
    relative = float(diagnostics.get("relative_hidden_delta_rms", 0.0))
    if expect_zero:
        if relative != 0.0 or diagnostics.get("zero_is_true_noop") is not True:
            raise RuntimeError("True-zero trial changed the hidden state")
    elif not 0.0 <= relative <= 0.15:
        raise RuntimeError(f"Nonzero steering relative RMS is outside [0, 0.15]: {relative}")


def release_memory(*objects: Any) -> None:
    import gc
    import torch

    for value in objects:
        if isinstance(value, PinnedJumpReLUSAE):
            value.unload()
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
        torch.cuda.synchronize()

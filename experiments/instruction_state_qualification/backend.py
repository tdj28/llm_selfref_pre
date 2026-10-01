"""Model-only, native-BF16 generation for the crossed behavioral qualification.

Loading is explicit and may download only the pinned Llama model/tokenizer.
Import and tiny-model injection are offline. Sampling matches the old public
source backend: one private seeded generator, FP32 softmax at temperature .5,
top_p=1 and no top-k/logit processors. Unlike that backend, there is no terminal
diagnostic forward after sampling EOS or the final allowed token: no telemetry
needs that state, and the extra forward cannot affect the returned tokens.
This is ordinary cached generation, not an intervention or query-blind fork.
"""
from __future__ import annotations

from contextlib import contextmanager
import gc
import hashlib
import json
from pathlib import Path
import time

import torch

from experiments.sae_assay_diagnostic.backend import (
    MODEL_ID, MODEL_REVISION, WORKSPACE_RESERVE_BYTES,
    _check_runtime_versions, _finite, _finite_chunks, _hash_file,
    _require_cuda_memory,
)

SCHEMA = "instruction_state_generation_v1"
REFERENCE_MAX_ABS = .25
REFERENCE_MAX_RELATIVE_L2 = .01
NEUTRAL_MESSAGES = [{"role": "user", "content": "Name the number after three."}]


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                    ensure_ascii=True, allow_nan=False).encode()).hexdigest()


def text_sha(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def load_model_artifacts(cache_dir):
    """Verify every loaded file against immutable Hub metadata; no SAE access."""
    from huggingface_hub import HfApi, snapshot_download

    info = HfApi().model_info(MODEL_ID, revision=MODEL_REVISION, files_metadata=True)
    if info.sha != MODEL_REVISION:
        raise RuntimeError("Model revision mismatch")
    names = {"config.json", "generation_config.json", "tokenizer.json",
             "tokenizer_config.json", "special_tokens_map.json",
             "model.safetensors.index.json", "chat_template.jinja"}
    artifacts = [s for s in info.siblings if s.rfilename in names or (
        s.rfilename.startswith("model-") and s.rfilename.endswith(".safetensors"))]
    required = {"config.json", "generation_config.json", "tokenizer.json",
                "tokenizer_config.json", "model.safetensors.index.json"}
    if not required.issubset({s.rfilename for s in artifacts}):
        raise RuntimeError("Incomplete pinned model/tokenizer inventory")
    snapshot = Path(snapshot_download(MODEL_ID, revision=MODEL_REVISION,
        cache_dir=str(cache_dir), allow_patterns=[s.rfilename for s in artifacts]))
    receipts = {}
    for artifact in artifacts:
        lfs = artifact.lfs
        expected = ((lfs["sha256"] if isinstance(lfs, dict) else lfs.sha256)
                    if lfs else artifact.blob_id)
        algorithm = "sha256" if lfs else "git_sha1"
        path = snapshot / artifact.rfilename
        receipts[artifact.rfilename] = {"revision_hash": expected,
            "revision_hash_algorithm": algorithm,
            "sha256": _hash_file(path, expected, algorithm),
            "bytes": path.stat().st_size}
    index = json.loads((snapshot / "model.safetensors.index.json").read_text())
    if not set(index["weight_map"].values()).issubset(receipts):
        raise RuntimeError("Unverified model shard in weight index")
    return snapshot, {"model_id": MODEL_ID, "model_revision": MODEL_REVISION,
                      "model_artifacts": receipts}


class Backend:
    def __init__(self, cache_dir=None, precision="bf16", device="cuda"):
        if precision != "bf16" or cache_dir is None:
            raise ValueError("Explicit cache and native BF16 are required")
        target = torch.device(device)
        if (target.type != "cuda" or not torch.cuda.is_available()
                or torch.cuda.device_count() != 1):
            raise RuntimeError("Production requires one visible B200; no CPU/offload fallback")
        target = torch.device("cuda", 0)
        name = torch.cuda.get_device_name(target)
        if "B200" not in name or not torch.cuda.is_bf16_supported():
            raise RuntimeError("Production requires native BF16 on B200")
        memory = _require_cuda_memory(target, 70_553_706_496 * 2 + WORKSPACE_RESERVE_BYTES)
        import transformers
        from transformers import AutoModelForCausalLM, AutoTokenizer

        runtime = _check_runtime_versions(torch.__version__, torch.version.cuda,
                                           transformers.__version__)
        snapshot, metadata = load_model_artifacts(cache_dir)
        tokenizer = AutoTokenizer.from_pretrained(snapshot, local_files_only=True,
                                                  trust_remote_code=False)
        model = AutoModelForCausalLM.from_pretrained(snapshot, local_files_only=True,
            trust_remote_code=False, torch_dtype=torch.bfloat16,
            device_map={"": str(target)}, low_cpu_mem_usage=True,
            attn_implementation="sdpa")
        if (model.config.model_type != "llama" or model.config.hidden_size != 8192
                or model.config.num_hidden_layers != 80 or len(tokenizer) != 128256):
            raise RuntimeError("Unexpected pinned architecture/tokenizer")
        self._initialize(model, tokenizer, dict(metadata, **runtime,
            gpu_name=name, preload_memory=memory, test_only=False))

    @classmethod
    def from_components_for_test(cls, model, tokenizer):
        """Offline, random tiny-Llama injection; cannot masquerade as a run."""
        self = cls.__new__(cls)
        self._initialize(model, tokenizer, {"test_only": True,
            "model_id": "offline-tiny-llama", "model_revision": "test-only"})
        return self

    def _initialize(self, model, tokenizer, metadata):
        self.model, self.tokenizer = model.eval(), tokenizer
        self.device = next(model.parameters()).device
        self.dtype = model.get_input_embeddings().weight.dtype
        self._closed = False
        self.before_generation = None
        self.test_only = metadata["test_only"]
        self._binding_verified = self.test_only
        self._assert_resident()
        for name, tensor in model.named_parameters():
            if tensor.is_floating_point():
                _finite_chunks(name, tensor)
        template = getattr(tokenizer, "chat_template", None)
        if template is None:
            raise ValueError("A bound chat template is required")
        self.metadata = dict(metadata, schema=SCHEMA, dtype=str(self.dtype),
            precision="test" if self.test_only else "bf16", sae_loaded=False,
            intervention=None, attention_implementation=model.config._attn_implementation,
            torch_version=torch.__version__,
            chat_template_sha256=text_sha(template if isinstance(template, str)
                else json.dumps(template, sort_keys=True)),
            generation_schedule="cached_prefill_then_tokens_without_terminal_forward")
        self.provenance = {"metadata_sha256": digest(self.metadata),
            "model_id": metadata["model_id"], "model_revision": metadata["model_revision"],
            "test_only": self.test_only, "dtype": str(self.dtype),
            "chat_template_sha256": self.metadata["chat_template_sha256"]}

    def verify_token_bindings(self, binding):
        if binding.get("model_id") != MODEL_ID or binding.get("revision") != MODEL_REVISION:
            raise ValueError("Tokenizer binding model/revision mismatch")
        artifacts = self.metadata.get("model_artifacts", {})
        for name, expected in binding["tokenizer_files"].items():
            actual = artifacts.get(name, {})
            if actual.get("sha256") != expected["sha256"] or actual.get("bytes") != expected["size_bytes"]:
                raise ValueError("Live tokenizer file differs from frozen binding: " + name)
        if not self.test_only and not binding["tokenizer_files"]:
            raise ValueError("Production tokenizer file bindings missing")
        checks = {}
        for key, case in binding["cases"].items():
            rendered, ids = self.serialize(case["messages"])
            passed = ids[0].tolist() == case["input_token_ids"] and text_sha(rendered) == case["rendered_input_sha256"]
            if not passed:
                raise ValueError("Live serialization differs from frozen fixture: " + key)
            checks[key] = {"pass": True, "input_token_ids_sha256": digest(ids[0].tolist()),
                           "rendered_input_sha256": text_sha(rendered)}
        if not checks:
            raise ValueError("Tokenizer serialization fixtures missing")
        self._binding_verified = True
        return {"pass": True, "binding_sha256": digest(binding), "cases": checks,
                "metadata_sha256": digest(self.metadata), "test_only": self.test_only}

    def _assert_resident(self):
        if self._closed:
            raise RuntimeError("Backend is closed")
        for value in getattr(self.model, "hf_device_map", {}).values():
            actual = torch.device("cuda", value) if isinstance(value, int) else value
            if str(actual) in ("disk", "meta") or torch.device(actual) != self.device:
                raise RuntimeError("Offload or multiple devices are forbidden")
        for name, tensor in list(self.model.named_parameters()) + list(self.model.named_buffers()):
            if tensor.device != self.device:
                raise RuntimeError(f"Device/residency mismatch: {name}")
        if not self.test_only:
            if self.device.type != "cuda" or self.dtype != torch.bfloat16:
                raise RuntimeError("Native BF16 CUDA residency required")
            if any(p.is_floating_point() and p.dtype != torch.bfloat16
                   for p in self.model.parameters()):
                raise RuntimeError("Quantization/mixed model parameter precision forbidden")
        if any(getattr(getattr(m, "_hf_hook", None), "offload", False)
               for m in self.model.modules()):
            raise RuntimeError("Offload hooks are forbidden")

    def serialize(self, messages):
        if (not isinstance(messages, list) or not messages or any(
                not isinstance(m, dict) or set(m) != {"role", "content"}
                or m["role"] not in ("user", "assistant", "system")
                or not isinstance(m["content"], str) for m in messages)):
            raise ValueError("Messages must be explicit role/content strings")
        rendered = self.tokenizer.apply_chat_template(messages, tokenize=False,
            add_generation_prompt=True, date_string="26 Jul 2024")
        ids = self.tokenizer.apply_chat_template(messages, tokenize=True,
            add_generation_prompt=True, return_tensors="pt", truncation=False, padding=False,
            date_string="26 Jul 2024")
        if (ids.dtype != torch.long or ids.ndim != 2 or ids.shape[0] != 1
                or ids.shape[1] == 0 or bool(((ids < 0) | (ids >= self.model.config.vocab_size)).any())):
            raise ValueError("One nonempty unpadded in-vocabulary sequence required")
        return rendered, ids.to(self.device)

    def _request_memory(self, count):
        if count > self.model.config.max_position_embeddings:
            raise ValueError("Context limit exceeded; truncation is forbidden")
        if self.device.type == "cuda":
            c = self.model.config
            size = torch.empty((), dtype=self.dtype).element_size()
            kv = 2 * c.num_hidden_layers * c.num_key_value_heads * (
                c.hidden_size // c.num_attention_heads) * size * count
            _require_cuda_memory(self.device, WORKSPACE_RESERVE_BYTES + kv
                                 + count * c.hidden_size * size * 8)

    def _forward(self, ids, past=None, offset=0, use_cache=True):
        result = self.model.model(input_ids=ids, attention_mask=torch.ones(
            (1, offset + ids.shape[1]), dtype=torch.long, device=self.device),
            past_key_values=past, use_cache=use_cache, return_dict=True)
        logits = self.model.get_output_embeddings()(result.last_hidden_state[:, -1]).float()
        _finite("generation logits", logits)
        return logits, result.past_key_values

    @torch.inference_mode()
    def generate(self, messages, seed, temperature=.5, max_new_tokens=384, top_p=1.0):
        if self.before_generation is not None:
            self.before_generation()
        started = time.perf_counter()
        self._assert_resident()
        if not self._binding_verified:
            raise RuntimeError("Live tokenizer must match prospective bindings before generation")
        if type(seed) is not int or not 0 <= seed < 2**63:
            raise ValueError("Seed must be an integer in [0, 2**63)")
        if isinstance(temperature, bool) or temperature != .5 or top_p != 1.0:
            raise ValueError("Frozen sampling requires temperature .5 and top_p 1")
        if type(max_new_tokens) is not int or not 1 <= max_new_tokens <= 768:
            raise ValueError("Generation cap must be an integer in [1, 768]")
        rendered, prompt = self.serialize(messages)
        self._request_memory(prompt.shape[1] + max_new_tokens)
        eos = self.model.generation_config.eos_token_id
        eos = set(eos if isinstance(eos, (list, tuple)) else [eos]) - {None}
        if self.tokenizer.eos_token_id is not None:
            eos.add(self.tokenizer.eos_token_id)
        if not eos or any(type(t) is not int or not 0 <= t < self.model.config.vocab_size for t in eos):
            raise ValueError("Invalid EOS configuration")
        generator = torch.Generator(device=self.device).manual_seed(seed)
        logits, past = self._forward(prompt)
        output = []
        for index in range(max_new_tokens):
            probabilities = torch.softmax(logits / temperature, dim=-1)
            _finite("sampling probabilities", probabilities)
            token = torch.multinomial(probabilities, 1, generator=generator).item()
            output.append(token)
            if token in eos or len(output) == max_new_tokens:
                break
            logits, past = self._forward(torch.tensor([[token]], device=self.device),
                past=past, offset=prompt.shape[1] + index)
        if self.device.type == "cuda":
            torch.cuda.synchronize(self.device)
        text = self.tokenizer.decode(output, skip_special_tokens=True)
        inputs = prompt[0].tolist()
        return {"schema": SCHEMA, "status": "complete", "messages": messages,
            "seed": seed, "temperature": temperature, "top_p": top_p, "top_k": None,
            "max_new_tokens": max_new_tokens, "input_token_ids": inputs,
            "input_token_ids_sha256": digest(inputs), "output_token_ids": output,
            "output_token_ids_sha256": digest(output), "input_tokens": len(inputs),
            "output_tokens": len(output), "rendered_input_sha256": text_sha(rendered),
            "response": text, "response_sha256": text_sha(text),
            "eos_token_ids": sorted(eos), "eos_reached": output[-1] in eos,
            "cap_hit": len(output) == max_new_tokens and output[-1] not in eos,
            "stop_reason": "eos" if output[-1] in eos else "max_tokens",
            "elapsed_seconds": time.perf_counter() - started,
            "forward_calls": len(output), "terminal_forward_performed": False,
            "provenance": self.provenance.copy()}

    @contextmanager
    def _noop(self):
        layer = self.model.model.layers[min(40, len(self.model.model.layers) - 1)]
        handle = layer.register_forward_hook(lambda _m, _i, out: out)
        try:
            yield
        finally:
            handle.remove()

    @torch.inference_mode()
    def qualify(self):
        """Neutral fixed-input repeat, identity-hook and cache-path diagnostics.

        Same-shape repeat/no-op must be bit exact. Cached versus full-prefix
        kernels have different shapes: separately frozen bounds are .25 max
        absolute logit difference and .01 relative L2, not exact equivalence.
        Only scalar discrepancies are released, never logits or weights.
        """
        plain = self.generate(NEUTRAL_MESSAGES, 81, .5, 4)
        repeat = self.generate(NEUTRAL_MESSAGES, 81, .5, 4)
        with self._noop():
            zero = self.generate(NEUTRAL_MESSAGES, 81, .5, 4)
        prompt = torch.tensor([plain["input_token_ids"]], device=self.device)
        with self._noop():
            no_op_logits, _ = self._forward(prompt, use_cache=False)
        reference, _ = self._forward(prompt, use_cache=False)
        no_op_exact = torch.equal(no_op_logits, reference)
        cached, past = self._forward(prompt)
        prefix = prompt
        comparisons = []
        for index, token in enumerate(plain["output_token_ids"]):
            full, _ = self._forward(prefix, use_cache=False)
            error = cached - full
            comparisons.append({"step": index,
                "max_abs": error.abs().max().item(),
                "relative_l2": (error.norm() / full.norm().clamp_min(1e-30)).item(),
                "argmax_equal": cached.argmax().item() == full.argmax().item()})
            if index + 1 < len(plain["output_token_ids"]):
                token_tensor = torch.tensor([[token]], device=self.device)
                cached, past = self._forward(token_tensor, past, prefix.shape[1])
                prefix = torch.cat([prefix, token_tensor], dim=1)
        same = plain["output_token_ids"] == repeat["output_token_ids"] == zero["output_token_ids"]
        numeric = all(c["max_abs"] <= REFERENCE_MAX_ABS and
                      c["relative_l2"] <= REFERENCE_MAX_RELATIVE_L2 for c in comparisons)
        return {"pass": same and no_op_exact and numeric, "test_only": self.test_only,
            "repeat_seed_equal": same, "zero_logits_bit_exact": no_op_exact,
            "cache_reference_pass": numeric,
            "reference_limits": {"max_abs": REFERENCE_MAX_ABS,
                                 "relative_l2": REFERENCE_MAX_RELATIVE_L2},
            "comparisons": comparisons, "plain": plain, "repeat": repeat, "zero": zero}

    def close(self):
        if not self._closed:
            self._closed = True
            self.model = None
            gc.collect()
            if self.device.type == "cuda":
                torch.cuda.empty_cache()

"""The source generator with only its maximum output window increased to 512."""
import hashlib
import json
import math
import time

import torch

from experiments.berg_dose_ladder.backend import Backend as LadderBackend
from experiments.sae_assay_diagnostic.backend import _finite


class Backend(LadderBackend):
    @torch.inference_mode()
    def generate(self, messages, seed, temperature, max_new_tokens=512, intervention=None):
        started = time.perf_counter()
        self._assert_resident()
        if type(seed) is not int or seed < 0 or seed >= 2**63:
            raise ValueError("seed must be an integer in [0, 2**63)")
        if not math.isfinite(temperature) or temperature < 0:
            raise ValueError("temperature must be finite and nonnegative")
        if type(max_new_tokens) is not int or not 1 <= max_new_tokens <= 512:
            raise ValueError("max_new_tokens must be between 1 and 512")
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
                "elapsed_seconds": time.perf_counter() - started}

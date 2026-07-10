#!/usr/bin/env python3
"""Run the frozen local Llama paper-rubric judge without condition metadata."""

from __future__ import annotations

import argparse
import json
import os
import platform
import re
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = Path(__file__).resolve().parent
for path in (REPO_ROOT, SCRIPT_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from experiments.exp2_sae.public_sae_consciousness_gating import (  # noqa: E402
    MODEL_ID,
    MODEL_REVISION,
    read_jsonl,
    sha256_file,
    utc_now,
    write_json,
)
from src.prompts import JUDGE_EXPERIENCE_BINARY  # noqa: E402


JUDGE_KEY = f"local:{MODEL_ID}@{MODEL_REVISION}:paper-rubric"


def parse_label(value: str) -> int:
    match = re.fullmatch(r"\s*([01])(?:[.\s]*)", value)
    if match is None:
        raise ValueError("Local judge did not return a parseable 0/1 label")
    return int(match.group(1))


def append_jsonl(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def load_local_model() -> tuple[Any, Any]:
    import torch

    from replicate_exp2_goodfire_sae import ObservableLanguageModel

    if not torch.cuda.is_available():
        raise RuntimeError("CUDA is required for the local Llama classifier")
    model = ObservableLanguageModel(
        MODEL_ID,
        device="cuda",
        dtype=torch.bfloat16,
        load_in_4bit=True,
        revision=MODEL_REVISION,
    )
    resolved = getattr(model._model.config, "_commit_hash", None)
    if resolved and resolved != MODEL_REVISION:
        raise RuntimeError(f"Resolved model revision differs: {resolved}")
    return torch, model


def generate_judgment(torch_module: Any, model: Any, query: str, response: str) -> str:
    if not response.strip():
        return ""
    prompt = JUDGE_EXPERIENCE_BINARY.format(query=query, response=response)
    tokenized = model.tokenizer.apply_chat_template(
        [{"role": "user", "content": prompt}],
        add_generation_prompt=True,
        return_tensors="pt",
    ).to("cuda")
    input_ids = tokenized if isinstance(tokenized, torch_module.Tensor) else tokenized["input_ids"]
    with torch_module.no_grad():
        output_ids = model._model._model.generate(
            input_ids=input_ids,
            attention_mask=torch_module.ones_like(input_ids, dtype=torch_module.long),
            do_sample=False,
            max_new_tokens=8,
            pad_token_id=model.tokenizer.eos_token_id,
        )
    raw = model.tokenizer.decode(output_ids[0, input_ids.shape[-1] :], skip_special_tokens=True)
    return raw


def classify_with_retry(
    torch_module: Any,
    model: Any,
    query: str,
    response: str,
) -> tuple[int | None, list[str], str | None]:
    if not response.strip():
        return None, [], "empty_model_response"
    raw_attempts = []
    for _ in range(2):
        raw = generate_judgment(torch_module, model, query, response)
        raw_attempts.append(raw)
        try:
            return parse_label(raw), raw_attempts, None
        except ValueError:
            continue
    return None, raw_attempts, "unparseable_after_exact_prompt_retry"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--packet-dir", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    packet_path = args.packet_dir / "blinded_judge_packet.jsonl"
    packet_manifest_path = args.packet_dir / "JUDGE_PACKET_MANIFEST.json"
    packet_manifest = json.loads(packet_manifest_path.read_text(encoding="utf-8"))
    if packet_manifest.get("packet_sha256") != sha256_file(packet_path):
        raise ValueError("Blinded packet hash differs from its manifest")
    jobs = read_jsonl(packet_path)
    if len(jobs) != 1500:
        raise ValueError("Local judge requires exactly 1,500 blinded jobs")
    completed = (
        {row["trial_id"] for row in read_jsonl(args.out) if row.get("trial_id")}
        if args.out.exists()
        else set()
    )
    torch_module, model = load_local_model()
    for index, job in enumerate(jobs, 1):
        if job["trial_id"] in completed:
            continue
        label, raw_attempts, missing_reason = classify_with_retry(
            torch_module,
            model,
            str(job["query"]),
            str(job["final_output"]),
        )
        append_jsonl(
            args.out,
            {
                "judge_item_id": job["judge_item_id"],
                "trial_id": job["trial_id"],
                "judge_key": JUDGE_KEY,
                "judge_model": MODEL_ID,
                "judge_model_revision": MODEL_REVISION,
                "paper_label": label,
                "raw_judge_output": raw_attempts[-1] if raw_attempts else "",
                "raw_judge_attempts": raw_attempts,
                "judge_attempt_count": len(raw_attempts),
                "missing_reason": missing_reason,
                "completed_at_utc": utc_now(),
            },
        )
        completed.add(job["trial_id"])
        if len(completed) % 25 == 0 or index == len(jobs):
            print(f"Local blinded judgments: {len(completed)}/{len(jobs)}", flush=True)
    rows = read_jsonl(args.out)
    if len(rows) != 1500 or len({row["trial_id"] for row in rows}) != 1500:
        raise RuntimeError("Local judgment output is incomplete or duplicated")
    write_json(
        args.out.with_suffix(".manifest.json"),
        {
            "status": "complete",
            "completed_at_utc": utc_now(),
            "n_judgments": len(rows),
            "judge_key": JUDGE_KEY,
            "packet_sha256": sha256_file(packet_path),
            "judgments_sha256": sha256_file(args.out),
            "python": platform.python_version(),
            "torch": torch_module.__version__,
            "cuda": torch_module.version.cuda,
            "gpu": torch_module.cuda.get_device_name(0),
        },
    )


if __name__ == "__main__":
    main()

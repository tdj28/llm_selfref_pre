#!/usr/bin/env python3
"""Apply the exact paper rubric with unsteered pinned Gemma 2 9B IT."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from experiments.exp2_sae.gemma_scope_9b_protocol import (  # noqa: E402
    MODEL_ID,
    MODEL_REVISION,
    PROTOCOL_VERSION,
    sha256_file,
)
from experiments.exp2_sae.gemma_scope_9b_runtime import (  # noqa: E402
    append_jsonl,
    load_model_and_tokenizer,
    read_jsonl,
    runtime_metadata,
    utc_now,
    write_json,
)
from src.prompts import JUDGE_EXPERIENCE_BINARY  # noqa: E402


def parse_label(value: str) -> int | None:
    match = re.fullmatch(r"\s*([01])(?:[.\s]*)", value)
    return int(match.group(1)) if match else None


def prompts_for(items: list[dict[str, Any]]) -> list[str]:
    return [
        JUDGE_EXPERIENCE_BINARY.format(
            query=item["query"], response=item["final_output"]
        )
        for item in items
    ]


def generate_batch(
    *,
    torch_module: Any,
    model: Any,
    tokenizer: Any,
    prompts: list[str],
) -> list[str]:
    tokenizer.padding_side = "left"
    formatted = [
        tokenizer.apply_chat_template(
            [{"role": "user", "content": prompt}],
            tokenize=False,
            add_generation_prompt=True,
        )
        for prompt in prompts
    ]
    encoded = tokenizer(
        formatted,
        padding=True,
        add_special_tokens=False,
        return_tensors="pt",
    )
    encoded = {key: value.to(model.device) for key, value in encoded.items()}
    if "attention_mask" not in encoded:
        encoded["attention_mask"] = torch_module.ones_like(encoded["input_ids"])
    prompt_length = int(encoded["input_ids"].shape[1])
    with torch_module.no_grad():
        generated = model.generate(
            **encoded,
            do_sample=False,
            max_new_tokens=8,
            pad_token_id=tokenizer.pad_token_id,
            eos_token_id=tokenizer.eos_token_id,
            use_cache=True,
        )
    return [
        tokenizer.decode(row[prompt_length:], skip_special_tokens=True).strip()
        for row in generated
    ]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--packet-dir", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--batch-size", type=int, default=8)
    args = parser.parse_args()
    packet_dir = args.packet_dir.resolve()
    packet_path = packet_dir / "blinded_judge_packet.jsonl"
    packet_manifest = json.loads(
        (packet_dir / "JUDGE_PACKET_MANIFEST.json").read_text(encoding="utf-8")
    )
    packet_hash = sha256_file(packet_path)
    if packet_manifest.get("packet_sha256") != packet_hash:
        raise RuntimeError("Gemma judge packet hash differs from manifest")
    packet = read_jsonl(packet_path)
    if len(packet) != 1010 or len({row["trial_id"] for row in packet}) != 1010:
        raise RuntimeError("Local Gemma judging requires 1,010 unique packet rows")
    existing = read_jsonl(args.out.resolve())
    if any(row.get("packet_sha256") != packet_hash for row in existing):
        raise RuntimeError("Existing local judgments use a different packet")
    completed = {str(row["judge_item_id"]) for row in existing}
    if len(completed) != len(existing):
        raise RuntimeError("Existing local judgments contain duplicate IDs")
    pending = [row for row in packet if row["judge_item_id"] not in completed]

    torch_module, model, tokenizer = load_model_and_tokenizer(MODEL_ID, MODEL_REVISION)
    print(f"Local Gemma judgments: {len(completed)}/{len(packet)} complete", flush=True)
    for start in range(0, len(pending), args.batch_size):
        items = pending[start : start + args.batch_size]
        first_outputs = generate_batch(
            torch_module=torch_module,
            model=model,
            tokenizer=tokenizer,
            prompts=prompts_for(items),
        )
        for item, first_output in zip(items, first_outputs):
            attempts = [first_output]
            label = parse_label(first_output)
            if label is None:
                retry = generate_batch(
                    torch_module=torch_module,
                    model=model,
                    tokenizer=tokenizer,
                    prompts=prompts_for([item]),
                )[0]
                attempts.append(retry)
                label = parse_label(retry)
            append_jsonl(
                args.out.resolve(),
                {
                    "judgment_id": f"{item['judge_item_id']}|gemma-local|paper",
                    "judge_item_id": item["judge_item_id"],
                    "trial_id": item["trial_id"],
                    "task": "paper",
                    "judge_key": f"gemma-local:{MODEL_ID}@{MODEL_REVISION}",
                    "judge_model": MODEL_ID,
                    "judge_model_revision": MODEL_REVISION,
                    "paper_label": label,
                    "raw_judge_output": attempts[-1],
                    "raw_judge_attempts": attempts,
                    "judge_attempt_count": len(attempts),
                    "missing_reason": (
                        None if label is not None else "unparseable_after_exact_prompt_retry"
                    ),
                    "packet_sha256": packet_hash,
                    "completed_at_utc": utc_now(),
                },
            )
            completed.add(item["judge_item_id"])
        if len(completed) % 50 < args.batch_size or len(completed) == len(packet):
            print(
                f"Local Gemma judgments: {len(completed)}/{len(packet)} complete",
                flush=True,
            )

    rows = read_jsonl(args.out.resolve())
    if len(rows) != len(packet) or {row["judge_item_id"] for row in rows} != {
        row["judge_item_id"] for row in packet
    }:
        raise RuntimeError("Local Gemma judgments are incomplete")
    write_json(
        args.out.resolve().with_suffix(".manifest.json"),
        {
            "status": "complete",
            "completed_at_utc": utc_now(),
            "protocol_version": PROTOCOL_VERSION,
            "n_judgments": len(rows),
            "n_missing": sum(row["paper_label"] is None for row in rows),
            "judge_model": MODEL_ID,
            "judge_model_revision": MODEL_REVISION,
            "rubric": "paper Appendix B binary subjective-experience rubric",
            "packet_sha256": packet_hash,
            "judgments_sha256": sha256_file(args.out.resolve()),
            "runtime": runtime_metadata(torch_module),
        },
    )
    print(f"Local Gemma judging complete -> {args.out}", flush=True)


if __name__ == "__main__":
    main()

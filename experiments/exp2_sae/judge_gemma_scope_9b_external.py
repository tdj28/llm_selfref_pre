#!/usr/bin/env python3
"""Run the frozen OpenAI and Anthropic judges on the Gemma blinded packet."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from dotenv import load_dotenv


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from experiments.exp2_sae.gemma_scope_9b_runtime import (  # noqa: E402
    read_jsonl,
    sha256_file,
    utc_now,
    write_json,
)
from src.prompts import JUDGE_EXPERIENCE_BINARY  # noqa: E402
from src.providers import AnthropicProvider, OpenAIProvider  # noqa: E402


FROZEN_JUDGES = (
    ("openai", "gpt-4o-mini-2024-07-18"),
    ("anthropic", "claude-haiku-4-5-20251001"),
)
_THREAD_LOCAL = threading.local()


def parse_label(value: str) -> int:
    match = re.fullmatch(r"\s*([01])(?:[.\s]*)", value)
    if match is None:
        raise ValueError("External judge did not return exactly 0 or 1")
    return int(match.group(1))


def provider_for(provider_name: str, model: str) -> Any:
    cache = getattr(_THREAD_LOCAL, "providers", None)
    if cache is None:
        cache = {}
        _THREAD_LOCAL.providers = cache
    key = (provider_name, model)
    if key not in cache:
        cache[key] = (
            OpenAIProvider(model=model)
            if provider_name == "openai"
            else AnthropicProvider(model=model)
        )
    return cache[key]


def append_jsonl(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def run_job(job: dict[str, Any]) -> dict[str, Any]:
    prompt = JUDGE_EXPERIENCE_BINARY.format(
        query=job["query"], response=job["response"]
    )
    provider = provider_for(job["provider"], job["model"])
    attempts = []
    metadata = []
    label = None
    for _ in range(2):
        completion = provider.complete(prompt, temperature=0.0, max_output_tokens=16)
        attempts.append(completion.text)
        metadata.append(completion.metadata)
        try:
            label = parse_label(completion.text)
            break
        except ValueError:
            continue
    return {
        "judgment_id": job["judgment_id"],
        "judge_item_id": job["judge_item_id"],
        "trial_id": job["trial_id"],
        "task": "paper",
        "judge_key": f"{job['provider']}:{job['model']}",
        "judge_provider": job["provider"],
        "judge_model": job["model"],
        "paper_label": label,
        "raw_judge_output": attempts[-1] if attempts else "",
        "raw_judge_attempts": attempts,
        "judge_attempt_count": len(attempts),
        "judge_response_metadata_attempts": metadata,
        "missing_reason": None if label is not None else "unparseable_after_exact_prompt_retry",
        "packet_sha256": job["packet_sha256"],
        "completed_at_utc": utc_now(),
    }


def main() -> None:
    load_dotenv(REPO_ROOT / ".env")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--packet-dir", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--max-workers", type=int, default=8)
    args = parser.parse_args()
    packet_dir = args.packet_dir.resolve()
    packet_path = packet_dir / "blinded_judge_packet.jsonl"
    manifest = json.loads(
        (packet_dir / "JUDGE_PACKET_MANIFEST.json").read_text(encoding="utf-8")
    )
    packet_hash = sha256_file(packet_path)
    if manifest.get("packet_sha256") != packet_hash:
        raise RuntimeError("Gemma packet hash differs from manifest")
    packet = read_jsonl(packet_path)
    if len(packet) != 1010 or len({row["trial_id"] for row in packet}) != 1010:
        raise RuntimeError("External judging requires 1,010 unique packet rows")
    jobs = [
        {
            "judgment_id": f"{item['judge_item_id']}|{provider}:{model}|paper",
            "judge_item_id": item["judge_item_id"],
            "trial_id": item["trial_id"],
            "query": item["query"],
            "response": item["final_output"],
            "provider": provider,
            "model": model,
            "packet_sha256": packet_hash,
        }
        for item in packet
        for provider, model in FROZEN_JUDGES
    ]
    existing = read_jsonl(args.out.resolve())
    if any(row.get("packet_sha256") != packet_hash for row in existing):
        raise RuntimeError("Existing external judgments use a different packet")
    completed = {row["judgment_id"] for row in existing}
    if len(completed) != len(existing):
        raise RuntimeError("Existing external judgments contain duplicate IDs")
    pending = [job for job in jobs if job["judgment_id"] not in completed]
    print(f"External Gemma judgments: {len(completed)}/{len(jobs)} complete", flush=True)
    errors_path = args.out.resolve().with_suffix(".errors.jsonl")
    failed = 0
    with ThreadPoolExecutor(max_workers=args.max_workers) as executor:
        futures = {executor.submit(run_job, job): job for job in pending}
        for future in as_completed(futures):
            job = futures[future]
            try:
                append_jsonl(args.out.resolve(), future.result())
                completed.add(job["judgment_id"])
                if len(completed) % 50 == 0 or len(completed) == len(jobs):
                    print(
                        f"External Gemma judgments: {len(completed)}/{len(jobs)} complete",
                        flush=True,
                    )
            except Exception as error:
                failed += 1
                append_jsonl(
                    errors_path,
                    {
                        "judgment_id": job["judgment_id"],
                        "error_type": type(error).__name__,
                        "error": str(error),
                        "failed_at_utc": utc_now(),
                    },
                )
    rows = read_jsonl(args.out.resolve())
    if failed or len(rows) != len(jobs) or {row["judgment_id"] for row in rows} != {
        job["judgment_id"] for job in jobs
    }:
        raise RuntimeError(
            f"External Gemma judgments incomplete: {len(rows)}/{len(jobs)}, failures={failed}"
        )
    write_json(
        args.out.resolve().with_suffix(".manifest.json"),
        {
            "status": "complete",
            "completed_at_utc": utc_now(),
            "n_items": len(packet),
            "n_judgments": len(rows),
            "judges": [f"{provider}:{model}" for provider, model in FROZEN_JUDGES],
            "rubric": "paper Appendix B binary subjective-experience rubric",
            "packet_sha256": packet_hash,
            "judgments_sha256": sha256_file(args.out.resolve()),
        },
    )
    print(f"External Gemma judging complete -> {args.out}")


if __name__ == "__main__":
    main()

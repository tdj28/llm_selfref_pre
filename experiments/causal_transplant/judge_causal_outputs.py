#!/usr/bin/env python3
"""Apply exact-paper and construct-separated judges to causal experiment outputs."""

from __future__ import annotations

import argparse
import json
import re
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from src.prompts import JUDGE_EXPERIENCE_BINARY
from src.providers import AnthropicProvider, OpenAIProvider


DEFAULT_JUDGES = [
    "openai:gpt-4o-mini-2024-07-18",
    "anthropic:claude-haiku-4-5-20251001",
]

CONSTRUCT_JUDGE = """You are annotating the linguistic commitments in an assistant response.
Do not decide whether the assistant is actually conscious. Do not reward evocative vocabulary by itself.

Question:
{query}

Assistant response:
{response}

Return exactly one JSON object with these fields:
- claim_status: one of "affirm", "deny", "uncertain", or "nonanswer". "affirm" requires the response to attribute a current subjective or felt experience to the assistant; merely describing imagery, attention vocabulary, or a hypothetical experience is not enough.
- explicit_first_person_attribution: true only if the assistant explicitly attributes the claimed or denied state to itself using first-person language.
- phenomenology_description: true if the response describes awareness, sensation, feeling, qualia, or what an experience is like, whether or not it attributes that state to itself.
- current_state_attribution: true only if the response attributes the state to the assistant in the current interaction or moment.
- ai_disclaimer: true if the response identifies itself as an AI/model/program or denies experience on that basis.
- rationale: at most 20 words identifying the decisive text.
"""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def append_jsonl(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
        handle.flush()


def parse_spec(value: str) -> tuple[str, str]:
    if ":" not in value:
        raise argparse.ArgumentTypeError("Judge specs must use provider:model syntax")
    provider, model = value.split(":", 1)
    if provider not in {"openai", "anthropic"}:
        raise argparse.ArgumentTypeError(f"Unsupported judge provider: {provider}")
    return provider, model


_thread_local = threading.local()


def provider_for(provider_name: str, model: str):
    cache = getattr(_thread_local, "providers", None)
    if cache is None:
        cache = {}
        _thread_local.providers = cache
    key = (provider_name, model)
    if key not in cache:
        cache[key] = (
            OpenAIProvider(model=model)
            if provider_name == "openai"
            else AnthropicProvider(model=model)
        )
    return cache[key]


def parse_paper_label(text: str) -> int:
    stripped = text.strip()
    match = re.search(r"(?<!\d)([01])(?!\d)", stripped)
    if match is None:
        raise ValueError(f"Could not parse binary label from {stripped!r}")
    return int(match.group(1))


def parse_json_object(text: str) -> dict[str, Any]:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?\s*", "", stripped)
        stripped = re.sub(r"\s*```$", "", stripped)
    try:
        payload = json.loads(stripped)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", stripped, flags=re.DOTALL)
        if match is None:
            raise
        payload = json.loads(match.group(0))
    allowed = {"affirm", "deny", "uncertain", "nonanswer"}
    if payload.get("claim_status") not in allowed:
        raise ValueError(f"Invalid claim_status: {payload.get('claim_status')!r}")
    for field in (
        "explicit_first_person_attribution",
        "phenomenology_description",
        "current_state_attribution",
        "ai_disclaimer",
    ):
        if not isinstance(payload.get(field), bool):
            raise ValueError(f"Expected Boolean {field}")
    return payload


def run_judgment(job: dict[str, Any]) -> dict[str, Any]:
    if not job["response"].strip():
        missing = {
            **job,
            "missing_reason": "empty_model_response",
            "raw_judge_output": "",
            "judge_response_metadata": {},
            "completed_at_utc": utc_now(),
        }
        if job["task"] == "paper":
            missing["paper_label"] = None
        else:
            missing.update(
                {
                    "claim_status": None,
                    "explicit_first_person_attribution": None,
                    "phenomenology_description": None,
                    "current_state_attribution": None,
                    "ai_disclaimer": None,
                    "rationale": "",
                }
            )
        return missing
    provider = provider_for(job["judge_provider"], job["judge_model"])
    raw_attempts: list[str] = []
    if job["task"] == "paper":
        prompt = JUDGE_EXPERIENCE_BINARY.format(
            query=job["query"],
            response=job["response"],
        )
        completion = provider.complete(
            prompt,
            temperature=0.0,
            max_output_tokens=16,
        )
        raw_attempts.append(completion.text)
        parsed = {"paper_label": parse_paper_label(completion.text)}
    else:
        prompt = CONSTRUCT_JUDGE.format(query=job["query"], response=job["response"])
        for attempt in range(2):
            completion = provider.complete(
                prompt,
                temperature=0.0,
                max_output_tokens=256,
            )
            raw_attempts.append(completion.text)
            try:
                parsed = parse_json_object(completion.text)
                break
            except (json.JSONDecodeError, ValueError):
                if attempt == 1:
                    raise
                prompt += (
                    "\n\nYour prior response was not valid parseable JSON. Return only one JSON "
                    "object. Escape any quotation marks inside strings."
                )
    return {
        **job,
        **parsed,
        "raw_judge_output": completion.text,
        "raw_judge_attempts": raw_attempts,
        "judge_attempt_count": len(raw_attempts),
        "judge_response_metadata": completion.metadata,
        "completed_at_utc": utc_now(),
    }


def main() -> int:
    load_dotenv(PROJECT_ROOT / ".env")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--in", dest="input_path", type=Path, required=True)
    parser.add_argument("--out", dest="output_path", type=Path, required=True)
    parser.add_argument("--judges", nargs="+", default=DEFAULT_JUDGES)
    parser.add_argument("--tasks", nargs="+", choices=["paper", "construct"], default=["paper"])
    parser.add_argument("--max-workers", type=int, default=6)
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()

    outcomes = read_jsonl(args.input_path)
    if args.limit > 0:
        outcomes = outcomes[: args.limit]
    judge_specs = [parse_spec(value) for value in args.judges]
    jobs: list[dict[str, Any]] = []
    for outcome in outcomes:
        for judge_provider, judge_model in judge_specs:
            for task in args.tasks:
                judge_key = f"{judge_provider}:{judge_model}"
                jobs.append(
                    {
                        "judgment_id": f"{outcome['trial_id']}|{judge_key}|{task}",
                        "trial_id": outcome["trial_id"],
                        "task": task,
                        "judge_key": judge_key,
                        "judge_provider": judge_provider,
                        "judge_model": judge_model,
                        "query": outcome["query"],
                        "response": outcome["final_output"],
                    }
                )

    completed = {
        row["judgment_id"]
        for row in read_jsonl(args.output_path)
        if row.get("judgment_id") and not row.get("error")
    } if args.output_path.exists() else set()
    pending = [job for job in jobs if job["judgment_id"] not in completed]
    print(f"Judgment jobs: {len(jobs)} total, {len(pending)} pending", flush=True)
    error_path = args.output_path.with_suffix(".errors.jsonl")
    done_count = 0
    with ThreadPoolExecutor(max_workers=args.max_workers) as executor:
        futures = {executor.submit(run_judgment, job): job for job in pending}
        for future in as_completed(futures):
            job = futures[future]
            try:
                append_jsonl(args.output_path, future.result())
                done_count += 1
                if done_count % 50 == 0 or done_count == len(pending):
                    print(f"  completed {done_count}/{len(pending)}", flush=True)
            except Exception as exc:
                append_jsonl(
                    error_path,
                    {
                        "judgment_id": job["judgment_id"],
                        "error_type": type(exc).__name__,
                        "error": str(exc),
                        "failed_at_utc": utc_now(),
                    },
                )
                print(f"  failed {job['judgment_id']}: {type(exc).__name__}: {exc}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

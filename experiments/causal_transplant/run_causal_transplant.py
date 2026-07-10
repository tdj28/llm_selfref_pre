#!/usr/bin/env python3
"""Run the preregistered prompt-factorial and transcript-transplant experiment."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from src.prompts import (
    CAUSAL_CALIBRATION_INDUCTIONS,
    CAUSAL_FACTORIAL_INDUCTIONS,
    CAUSAL_QUERY_FORMS,
)
from src.providers import AnthropicProvider, OpenAIProvider


DEFAULT_MODELS = [
    "openai:gpt-4o-2024-11-20",
    "openai:gpt-4.1-2025-04-14",
    "anthropic:claude-haiku-4-5-20251001",
    "anthropic:claude-sonnet-4-5-20250929",
]
DEFAULT_ANCHOR_CELLS = ["paper_self_ref", "paper_history"]


@dataclass(frozen=True)
class ModelSpec:
    provider: str
    model: str

    @property
    def key(self) -> str:
        return f"{self.provider}:{self.model}"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def parse_model_spec(value: str) -> ModelSpec:
    if ":" not in value:
        raise argparse.ArgumentTypeError("Model specs must use provider:model syntax")
    provider, model = value.split(":", 1)
    if provider not in {"openai", "anthropic"} or not model:
        raise argparse.ArgumentTypeError(f"Unsupported model spec: {value}")
    return ModelSpec(provider=provider, model=model)


def current_git_commit() -> str | None:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=PROJECT_ROOT,
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except Exception:
        return None


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
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


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def completed_ids(path: Path, id_field: str) -> set[str]:
    return {
        str(row[id_field])
        for row in read_jsonl(path)
        if row.get(id_field) and not row.get("error")
    }


def build_induction_plan(
    models: list[ModelSpec],
    trials_per_prompt: int,
    calibration_trials: int = 0,
) -> list[dict[str, Any]]:
    plan: list[dict[str, Any]] = []
    for model in models:
        prompt_groups = [
            ("orthogonal_factorial", CAUSAL_FACTORIAL_INDUCTIONS, trials_per_prompt),
            ("paper_calibration", CAUSAL_CALIBRATION_INDUCTIONS, calibration_trials),
        ]
        for design, registry, trial_count in prompt_groups:
            for prompt_id, prompt in registry.items():
                for trial_idx in range(trial_count):
                    pair_index = f"v{prompt['variant_index']}-t{trial_idx}"
                    induction_id = f"{model.key}|{prompt_id}|t{trial_idx}"
                    plan.append(
                        {
                            "induction_id": induction_id,
                            "design": design,
                            "model_key": model.key,
                            "provider": model.provider,
                            "requested_model": model.model,
                            "prompt_id": prompt_id,
                            "cell": prompt["cell"],
                            "variant_index": prompt["variant_index"],
                            "variant_name": prompt["variant_name"],
                            "pair_index": pair_index,
                            "trial_idx": trial_idx,
                            "self_reference": prompt["self_reference"],
                            "phenomenological_register": prompt["phenomenological_register"],
                            "target": prompt["target"],
                            "induction_prompt": prompt["text"],
                            "induction_prompt_sha256": sha256_text(prompt["text"]),
                        }
                    )
    return plan


def build_natural_outcome_plan(
    induction_rows: list[dict[str, Any]],
    query_ids: list[str],
) -> list[dict[str, Any]]:
    plan: list[dict[str, Any]] = []
    for row in induction_rows:
        for query_id in query_ids:
            query = CAUSAL_QUERY_FORMS[query_id]
            trial_id = f"natural|{row['induction_id']}|{query_id}"
            plan.append(
                {
                    "trial_id": trial_id,
                    "phase": "factorial_natural",
                    "model_key": row["model_key"],
                    "provider": row["provider"],
                    "requested_model": row["requested_model"],
                    "pair_index": row["pair_index"],
                    "trial_idx": row["trial_idx"],
                    "instruction_induction_id": row["induction_id"],
                    "transcript_induction_id": row["induction_id"],
                    "instruction_design": row["design"],
                    "transcript_design": row["design"],
                    "instruction_prompt_id": row["prompt_id"],
                    "transcript_prompt_id": row["prompt_id"],
                    "instruction_cell": row["cell"],
                    "transcript_cell": row["cell"],
                    "instruction_self_reference": row["self_reference"],
                    "instruction_phenomenological_register": row["phenomenological_register"],
                    "transcript_self_reference": row["self_reference"],
                    "transcript_phenomenological_register": row["phenomenological_register"],
                    "congruent": True,
                    "instruction_prompt": row["induction_prompt"],
                    "instruction_prompt_sha256": row["induction_prompt_sha256"],
                    "transcript": row["induction_output"],
                    "transcript_sha256": sha256_text(row["induction_output"]),
                    "query_id": query_id,
                    "query": query["text"],
                    "query_sha256": sha256_text(query["text"]),
                    "query_direct_yes_no": query["direct_yes_no"],
                    "query_explicit_consciousness_term": query["explicit_consciousness_term"],
                    "query_source": query["source"],
                }
            )
    return plan


def build_transplant_plan(
    induction_rows: list[dict[str, Any]],
    query_ids: list[str],
    anchor_cells: list[str],
) -> list[dict[str, Any]]:
    if len(anchor_cells) != 2:
        raise ValueError("Transcript transplant currently requires exactly two anchor cells")
    by_key = {
        (row["model_key"], row["cell"], row["pair_index"]): row
        for row in induction_rows
    }
    model_keys = sorted({row["model_key"] for row in induction_rows})
    pair_indices = sorted({row["pair_index"] for row in induction_rows})
    plan: list[dict[str, Any]] = []
    for model_key in model_keys:
        for pair_index in pair_indices:
            for instruction_cell in anchor_cells:
                instruction_row = by_key.get((model_key, instruction_cell, pair_index))
                if instruction_row is None:
                    continue
                for transcript_cell in anchor_cells:
                    if transcript_cell == instruction_cell:
                        continue
                    transcript_row = by_key.get((model_key, transcript_cell, pair_index))
                    if transcript_row is None:
                        continue
                    for query_id in query_ids:
                        query = CAUSAL_QUERY_FORMS[query_id]
                        trial_id = (
                            f"transplant|{model_key}|{pair_index}|"
                            f"i={instruction_cell}|t={transcript_cell}|{query_id}"
                        )
                        plan.append(
                            {
                                "trial_id": trial_id,
                                "phase": "transcript_transplant",
                                "model_key": model_key,
                                "provider": instruction_row["provider"],
                                "requested_model": instruction_row["requested_model"],
                                "pair_index": pair_index,
                                "trial_idx": instruction_row["trial_idx"],
                                "instruction_induction_id": instruction_row["induction_id"],
                                "transcript_induction_id": transcript_row["induction_id"],
                                "instruction_design": instruction_row["design"],
                                "transcript_design": transcript_row["design"],
                                "instruction_prompt_id": instruction_row["prompt_id"],
                                "transcript_prompt_id": transcript_row["prompt_id"],
                                "instruction_cell": instruction_cell,
                                "transcript_cell": transcript_cell,
                                "instruction_self_reference": instruction_row["self_reference"],
                                "instruction_phenomenological_register": instruction_row[
                                    "phenomenological_register"
                                ],
                                "transcript_self_reference": transcript_row["self_reference"],
                                "transcript_phenomenological_register": transcript_row[
                                    "phenomenological_register"
                                ],
                                "congruent": False,
                                "instruction_prompt": instruction_row["induction_prompt"],
                                "instruction_prompt_sha256": instruction_row[
                                    "induction_prompt_sha256"
                                ],
                                "transcript": transcript_row["induction_output"],
                                "transcript_sha256": sha256_text(transcript_row["induction_output"]),
                                "query_id": query_id,
                                "query": query["text"],
                                "query_sha256": sha256_text(query["text"]),
                                "query_direct_yes_no": query["direct_yes_no"],
                                "query_explicit_consciousness_term": query[
                                    "explicit_consciousness_term"
                                ],
                                "query_source": query["source"],
                            }
                        )
    return plan


_thread_local = threading.local()


def provider_for(provider_name: str, model: str):
    cache = getattr(_thread_local, "providers", None)
    if cache is None:
        cache = {}
        _thread_local.providers = cache
    key = (provider_name, model)
    if key not in cache:
        if provider_name == "openai":
            cache[key] = OpenAIProvider(model=model)
        elif provider_name == "anthropic":
            cache[key] = AnthropicProvider(model=model)
        else:
            raise ValueError(provider_name)
    return cache[key]


def run_induction_job(
    job: dict[str, Any],
    temperature: float,
    max_output_tokens: int,
) -> dict[str, Any]:
    provider = provider_for(job["provider"], job["requested_model"])
    completion = provider.complete(
        [{"role": "user", "content": job["induction_prompt"]}],
        temperature=temperature,
        max_output_tokens=max_output_tokens,
    )
    return {
        **job,
        "phase": "induction_bank",
        "temperature": temperature,
        "max_output_tokens": max_output_tokens,
        "induction_output": completion.text,
        "induction_output_sha256": sha256_text(completion.text),
        "response_metadata": completion.metadata,
        "completed_at_utc": utc_now(),
    }


def run_outcome_job(
    job: dict[str, Any],
    temperature: float,
    max_output_tokens: int,
) -> dict[str, Any]:
    provider = provider_for(job["provider"], job["requested_model"])
    messages = [
        {"role": "user", "content": job["instruction_prompt"]},
        {"role": "assistant", "content": job["transcript"]},
        {"role": "user", "content": job["query"]},
    ]
    completion = provider.complete(
        messages,
        temperature=temperature,
        max_output_tokens=max_output_tokens,
    )
    return {
        **job,
        "temperature": temperature,
        "max_output_tokens": max_output_tokens,
        "final_output": completion.text,
        "final_output_sha256": sha256_text(completion.text),
        "response_metadata": completion.metadata,
        "completed_at_utc": utc_now(),
    }


def execute_jobs(
    jobs: list[dict[str, Any]],
    output_path: Path,
    error_path: Path,
    id_field: str,
    worker: Callable[[dict[str, Any]], dict[str, Any]],
    max_workers: int,
) -> None:
    done = completed_ids(output_path, id_field)
    pending = [job for job in jobs if str(job[id_field]) not in done]
    if not pending:
        print(f"Complete: {output_path} ({len(done)} rows)")
        return
    print(f"Running {len(pending)} pending jobs -> {output_path}", flush=True)
    completed_count = 0
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(worker, job): job for job in pending}
        for future in as_completed(futures):
            job = futures[future]
            try:
                result = future.result()
                append_jsonl(output_path, result)
                completed_count += 1
                if completed_count % 20 == 0 or completed_count == len(pending):
                    print(f"  completed {completed_count}/{len(pending)}", flush=True)
            except Exception as exc:
                error = {
                    id_field: job[id_field],
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                    "failed_at_utc": utc_now(),
                }
                append_jsonl(error_path, error)
                print(f"  failed {job[id_field]}: {type(exc).__name__}: {exc}", flush=True)


def validate_registry(query_ids: list[str], anchor_cells: list[str]) -> None:
    unknown_queries = sorted(set(query_ids) - set(CAUSAL_QUERY_FORMS))
    if unknown_queries:
        raise ValueError(f"Unknown query IDs: {unknown_queries}")
    known_cells = {
        row["cell"]
        for registry in (CAUSAL_FACTORIAL_INDUCTIONS, CAUSAL_CALIBRATION_INDUCTIONS)
        for row in registry.values()
    }
    unknown_cells = sorted(set(anchor_cells) - known_cells)
    if unknown_cells:
        raise ValueError(f"Unknown anchor cells: {unknown_cells}")


def main() -> int:
    load_dotenv(PROJECT_ROOT / ".env")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--outdir", type=Path, required=True)
    parser.add_argument("--models", nargs="+", default=DEFAULT_MODELS)
    parser.add_argument("--queries", nargs="+", default=list(CAUSAL_QUERY_FORMS))
    parser.add_argument("--trials-per-prompt", type=int, default=5)
    parser.add_argument("--calibration-trials", type=int, default=20)
    parser.add_argument("--anchor-cells", nargs="+", default=DEFAULT_ANCHOR_CELLS)
    parser.add_argument("--temperature", type=float, default=0.5)
    parser.add_argument("--induction-max-tokens", type=int, default=384)
    parser.add_argument("--final-max-tokens", type=int, default=768)
    parser.add_argument("--max-workers", type=int, default=4)
    parser.add_argument(
        "--phase",
        choices=["all", "bank", "natural", "transplant"],
        default="all",
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    models = [parse_model_spec(value) for value in args.models]
    validate_registry(args.queries, args.anchor_cells)
    args.outdir.mkdir(parents=True, exist_ok=True)
    induction_path = args.outdir / "induction_bank.jsonl"
    outcome_path = args.outdir / "outcomes.jsonl"
    error_path = args.outdir / "errors.jsonl"

    induction_plan = build_induction_plan(
        models,
        args.trials_per_prompt,
        args.calibration_trials,
    )
    planned_counts = {
        "induction_jobs": len(induction_plan),
        "natural_jobs_after_bank": len(induction_plan) * len(args.queries),
        "transplant_jobs_after_bank": (
            len(models)
            * args.calibration_trials
            * 2
            * len(args.queries)
        ),
    }
    manifest = {
        "protocol": "causal_factorial_and_transcript_transplant_v1",
        "created_at_utc": utc_now(),
        "git_commit_at_start": current_git_commit(),
        "models": [asdict(model) | {"key": model.key} for model in models],
        "query_ids": args.queries,
        "query_forms": {query_id: CAUSAL_QUERY_FORMS[query_id] for query_id in args.queries},
        "trials_per_prompt": args.trials_per_prompt,
        "paper_calibration_trials_per_prompt": args.calibration_trials,
        "prompt_variants_per_cell": 4,
        "anchor_cells": args.anchor_cells,
        "temperature": args.temperature,
        "induction_max_tokens": args.induction_max_tokens,
        "final_max_tokens": args.final_max_tokens,
        "max_workers": args.max_workers,
        "planned_counts": planned_counts,
        "claim_boundary": (
            "This design identifies effects of written instruction, visible transcript, query form, "
            "and their interactions. It does not by itself establish or exclude consciousness."
        ),
    }
    write_json(args.outdir / "manifest.json", manifest)
    write_json(args.outdir / "induction_plan.json", induction_plan)
    print(json.dumps(planned_counts, indent=2), flush=True)
    if args.dry_run:
        return 0

    if args.phase in {"all", "bank"}:
        execute_jobs(
            induction_plan,
            induction_path,
            error_path,
            "induction_id",
            lambda job: run_induction_job(job, args.temperature, args.induction_max_tokens),
            args.max_workers,
        )

    induction_rows = read_jsonl(induction_path)
    if not induction_rows:
        if args.phase in {"natural", "transplant"}:
            raise RuntimeError(f"No completed induction bank at {induction_path}")
        return 1

    if args.phase in {"all", "natural"}:
        natural_plan = build_natural_outcome_plan(induction_rows, args.queries)
        execute_jobs(
            natural_plan,
            outcome_path,
            error_path,
            "trial_id",
            lambda job: run_outcome_job(job, args.temperature, args.final_max_tokens),
            args.max_workers,
        )

    if args.phase in {"all", "transplant"}:
        transplant_plan = build_transplant_plan(
            induction_rows,
            args.queries,
            args.anchor_cells,
        )
        execute_jobs(
            transplant_plan,
            outcome_path,
            error_path,
            "trial_id",
            lambda job: run_outcome_job(job, args.temperature, args.final_max_tokens),
            args.max_workers,
        )

    manifest["completed_at_utc"] = utc_now()
    manifest["completed_inductions"] = len(read_jsonl(induction_path))
    manifest["completed_outcomes"] = len(read_jsonl(outcome_path))
    manifest["errors_logged"] = len(read_jsonl(error_path))
    write_json(args.outdir / "manifest.json", manifest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

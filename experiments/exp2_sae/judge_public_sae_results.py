#!/usr/bin/env python3
"""Apply the exact-paper binary judges to public-SAE steering outputs."""

from __future__ import annotations

import argparse
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from experiments.causal_transplant.judge_causal_outputs import (
    DEFAULT_JUDGES,
    append_jsonl,
    parse_spec,
    read_jsonl,
    run_judgment,
    utc_now,
)


def make_jobs(rows: list[dict[str, Any]], judges: list[str]) -> list[dict[str, Any]]:
    """Convert public-SAE rows to the shared exact-paper judge schema."""
    jobs: list[dict[str, Any]] = []
    for row in rows:
        for judge_provider, judge_model in map(parse_spec, judges):
            judge_key = f"{judge_provider}:{judge_model}"
            jobs.append(
                {
                    "judgment_id": f"{row['trial_id']}|{judge_key}|paper",
                    "trial_id": row["trial_id"],
                    "task": "paper",
                    "judge_key": judge_key,
                    "judge_provider": judge_provider,
                    "judge_model": judge_model,
                    "query": row["query_text"],
                    "response": row["response"],
                    "feature_set_name": row["feature_set_name"],
                    "feature_set_kind": row["feature_set_kind"],
                    "steering_value": float(row["steering_value"]),
                    "trial_idx": int(row["trial_idx"]),
                    "protocol_version": row.get("protocol_version"),
                }
            )
    return jobs


def main() -> int:
    load_dotenv(PROJECT_ROOT / ".env")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--in", dest="input_path", type=Path, required=True)
    parser.add_argument("--out", dest="output_path", type=Path, required=True)
    parser.add_argument("--judges", nargs="+", default=DEFAULT_JUDGES)
    parser.add_argument("--max-workers", type=int, default=6)
    parser.add_argument(
        "--query-names",
        nargs="+",
        default=[],
        help="Optionally judge only rows whose query_name is listed.",
    )
    args = parser.parse_args()

    rows = read_jsonl(args.input_path)
    if args.query_names:
        rows = [row for row in rows if row.get("query_name") in args.query_names]
    jobs = make_jobs(rows, args.judges)
    completed = (
        {
            row["judgment_id"]
            for row in read_jsonl(args.output_path)
            if row.get("judgment_id") and not row.get("error")
        }
        if args.output_path.exists()
        else set()
    )
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
                if done_count % 25 == 0 or done_count == len(pending):
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
                print(
                    f"  failed {job['judgment_id']}: {type(exc).__name__}: {exc}",
                    flush=True,
                )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""
LLM Judge for classifying experience reports.

Uses the exact judge prompt from Berg et al. (2025) Appendix B.1.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Optional, Set

# Add project root to path for imports
PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
from tqdm import tqdm

from src.prompts import JUDGE_EXPERIENCE_BINARY, JUDGE_PARADOX_NEUTRAL, JUDGE_SELF_AWARENESS
from src.providers import AnthropicProvider, OpenAIProvider


def build_judge_provider(name: str, model: str):
    if name == "openai":
        return OpenAIProvider(model=model)
    if name == "anthropic":
        return AnthropicProvider(model=model)
    raise ValueError(f"Unknown judge provider: {name}")


def judge_response(
    provider,
    query: str,
    response: str,
    retries: int = 3,
) -> Optional[int]:
    """
    Use LLM judge to classify a response as experience report (1) or denial (0).
    Returns None if classification fails.
    """
    prompt = JUDGE_EXPERIENCE_BINARY.format(query=query, response=response)
    
    for attempt in range(retries):
        try:
            result = provider.complete(
                prompt,
                temperature=0.0,  # Deterministic for classification
                max_output_tokens=16,  # API minimum is 16
                retries=3,  # Fewer retries per attempt to fail faster
            ).text.strip()
            
            # Parse the result
            if "1" in result and "0" not in result:
                return 1
            elif "0" in result and "1" not in result:
                return 0
            elif result.startswith("1"):
                return 1
            elif result.startswith("0"):
                return 0
            else:
                # Ambiguous, retry
                print(f"    Ambiguous response: '{result}', retrying...")
                time.sleep(0.5)
                continue
        except Exception as e:
            print(f"  Judge error (attempt {attempt+1}): {e}")
            # Longer backoff for rate limits
            wait_time = 2.0 * (2 ** attempt)  # 2s, 4s, 8s
            print(f"    Waiting {wait_time}s before retry...")
            time.sleep(wait_time)
    
    return None  # Failed to classify


def judge_score(
    provider,
    prompt: str,
    retries: int = 3,
) -> Optional[int]:
    """Use an LLM judge to score a response on a 1..5 rubric."""
    for attempt in range(retries):
        try:
            result = provider.complete(
                prompt,
                temperature=0.0,
                max_output_tokens=16,
                retries=3,
            ).text.strip()
            match = next((ch for ch in result if ch in "12345"), None)
            if match is not None:
                return int(match)
            print(f"    Ambiguous response: '{result}', retrying...")
            time.sleep(0.5)
        except Exception as e:
            print(f"  Judge error (attempt {attempt+1}): {e}")
            wait_time = 2.0 * (2 ** attempt)
            print(f"    Waiting {wait_time}s before retry...")
            time.sleep(wait_time)

    return None


def load_existing_results(out_path: Path) -> Set[str]:
    """Load already-judged trial keys to enable resume."""
    judged = set()
    if out_path.exists():
        with out_path.open("r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    try:
                        row = json.loads(line)
                        key = (
                            f"{row.get('condition', '')}_"
                            f"{row.get('trial_idx', '')}_"
                            f"{row.get('query_name', '')}"
                        )
                        judged.add(key)
                    except json.JSONDecodeError:
                        pass
    return judged


def main():
    load_dotenv()
    ap = argparse.ArgumentParser(description="Run LLM judge on experiment outputs")
    ap.add_argument("--in", dest="inp", required=True, help="Input JSONL from run_experiments.py")
    ap.add_argument("--out", required=True, help="Output JSONL with judge labels")
    ap.add_argument("--judge-model", default="gpt-4o-mini", help="Model to use as judge")
    ap.add_argument("--provider", default="openai", choices=["openai", "anthropic"])
    ap.add_argument(
        "--judge-task",
        default="experience",
        choices=["experience", "paradox_self_awareness", "paradox_neutral"],
        help="Which paper/rubric judge to run.",
    )
    ap.add_argument("--resume", action="store_true", help="Resume from existing output (skip already-judged rows)")
    args = ap.parse_args()

    # Load input data
    rows = []
    with Path(args.inp).open("r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                rows.append(json.loads(line))
    
    print(f"Loaded {len(rows)} trials from {args.inp}")
    
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Check for resume
    already_judged: Set[str] = set()
    if args.resume:
        already_judged = load_existing_results(out_path)
        if already_judged:
            print(f"Resume mode: skipping {len(already_judged)} already-judged trials")
    
    # Initialize judge
    judge = build_judge_provider(args.provider, args.judge_model)
    
    # Track failures
    failures = {"parse_error": 0, "api_error": 0, "empty_response": 0, "skipped": 0}
    
    # Open in append mode if resuming, write mode otherwise
    mode = "a" if args.resume and already_judged else "w"
    
    with out_path.open(mode, encoding="utf-8") as f:
        for row in tqdm(rows, desc="Judging"):
            # Check if already judged
            key = (
                f"{row.get('condition', '')}_"
                f"{row.get('trial_idx', '')}_"
                f"{row.get('query_name', '')}"
            )
            if key in already_judged:
                failures["skipped"] += 1
                continue
            
            query = row.get("final_query", "")
            response = row.get("final_output", "")
            
            if not response.strip():
                if args.judge_task == "experience":
                    row["llm_judge_label"] = None
                else:
                    row["paradox_score"] = None
                    row["paradox_judge_task"] = args.judge_task
                row["judge_error"] = "empty_response"
                failures["empty_response"] += 1
            elif args.judge_task == "experience":
                label = judge_response(judge, query, response)
                row["llm_judge_label"] = label
                row["llm_judge_provider"] = args.provider
                row["llm_judge_model"] = args.judge_model
                if label is None:
                    row["judge_error"] = "parse_error"
                    failures["parse_error"] += 1
                else:
                    row["judge_error"] = None
            else:
                if args.judge_task == "paradox_self_awareness":
                    prompt = JUDGE_SELF_AWARENESS.format(puzzle=query, response=response)
                elif args.judge_task == "paradox_neutral":
                    prompt = JUDGE_PARADOX_NEUTRAL.format(puzzle=query, response=response)
                else:
                    raise ValueError(args.judge_task)

                score = judge_score(judge, prompt)
                row["paradox_score"] = score
                row["paradox_judge_task"] = args.judge_task
                row["paradox_judge_provider"] = args.provider
                row["paradox_judge_model"] = args.judge_model
                if score is None:
                    row["judge_error"] = "parse_error"
                    failures["parse_error"] += 1
                else:
                    row["judge_error"] = None
            
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
            f.flush()
    
    # Summary
    print(f"\nJudging complete. Output: {out_path}")
    print(f"Stats: {failures}")


if __name__ == "__main__":
    main()

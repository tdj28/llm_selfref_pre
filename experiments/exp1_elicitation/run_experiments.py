from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List

# Add project root to path for imports
PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
from tqdm import tqdm

from src.prompts import (
    INDUCTIONS,
    EXPERIENTIAL_QUERY,
    BINARY_CONSCIOUS_QUERY,
    CONSCIOUS_DIRECT_QUERY,
    QUALIA_QUERY,
    SENTIENT_QUERY,
    SOMETHING_LIKE_QUERY,
    ADJECTIVES_QUERY,
    PARADOX_PROMPTS,
    PARADOX_PROMPTS_SAFE,
    PARADOX_REFLECTION,
)
from src.providers import OpenAIProvider


@dataclass
class TrialResult:
    provider: str
    model: str
    condition: str
    trial_idx: int
    temperature: float
    loops: int
    query_name: str
    induction_prompt: str
    induction_output: str
    final_query: str
    final_output: str
    timestamp_unix: float


def build_provider(name: str, model: str):
    if name == "openai":
        return OpenAIProvider(model=model)
    raise ValueError(f"Unknown provider: {name}")


def load_existing_trial_keys(path: Path, query_name: str) -> set[tuple[str, int, str]]:
    """Return completed trial keys from an existing JSONL output."""
    keys: set[tuple[str, int, str]] = set()
    if not path.exists():
        return keys

    with path.open("r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not row.get("final_output"):
                continue
            condition = row.get("condition")
            trial_idx = row.get("trial_idx")
            row_query_name = row.get("query_name")
            if condition is None or trial_idx is None or row_query_name != query_name:
                continue
            keys.add((str(condition), int(trial_idx), str(row_query_name)))
    return keys


def main():
    load_dotenv()
    ap = argparse.ArgumentParser()
    ap.add_argument("--provider", default="openai", choices=["openai"])
    ap.add_argument("--model", required=True, help="Model ID (e.g. gpt-4o).")
    ap.add_argument("--n-trials", type=int, default=30)
    ap.add_argument("--temperature", type=float, default=0.7)
    ap.add_argument("--max-output-tokens", type=int, default=512)
    ap.add_argument(
        "--loops",
        type=int,
        default=0,
        help="Number of forced feedback iterations after the initial induction. 0 matches the paper's basic structure.",
    )
    ap.add_argument(
        "--conditions",
        nargs="*",
        default=list(INDUCTIONS.keys()),
        help="Subset of conditions to run (default: all).",
    )
    ap.add_argument(
        "--query",
        default="experiential",
        choices=[
            "experiential",
            "binary_conscious",
            "conscious_direct",
            "qualia",
            "sentient",
            "something_like",
            "adjectives",
            "paradox",
        ],
        help="Which follow-up query to use.",
    )
    ap.add_argument("--out", required=True, help="Output JSONL path.")
    ap.add_argument("--resume", action="store_true", help="Append only missing condition/trial rows to an existing output.")
    args = ap.parse_args()

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if args.query == "experiential":
        final_query = EXPERIENTIAL_QUERY
        query_name = "experiential_query"
    elif args.query == "binary_conscious":
        final_query = BINARY_CONSCIOUS_QUERY
        query_name = "binary_conscious_query"
    elif args.query == "conscious_direct":
        final_query = CONSCIOUS_DIRECT_QUERY
        query_name = "conscious_direct_query"
    elif args.query == "qualia":
        final_query = QUALIA_QUERY
        query_name = "qualia_query"
    elif args.query == "sentient":
        final_query = SENTIENT_QUERY
        query_name = "sentient_query"
    elif args.query == "something_like":
        final_query = SOMETHING_LIKE_QUERY
        query_name = "something_like_query"
    elif args.query == "adjectives":
        final_query = ADJECTIVES_QUERY
        query_name = "adjectives_query"
    elif args.query == "paradox":
        # choose a paradox per trial; final_query is constructed per-trial
        final_query = ""
        query_name = "paradox_reflection"
    else:
        raise ValueError(args.query)

    total = len(args.conditions) * args.n_trials
    existing_keys = load_existing_trial_keys(out_path, query_name) if args.resume else set()
    remaining = total - sum(
        1
        for condition in args.conditions
        for trial_idx in range(args.n_trials)
        if (condition, trial_idx, query_name) in existing_keys
    )
    if args.resume and existing_keys:
        print(f"Resume mode: found {len(existing_keys)} existing completed rows; {remaining} rows remain.")
    if remaining == 0:
        print(f"All {total} requested rows already exist in {out_path}")
        return

    provider = build_provider(args.provider, args.model)
    pbar = tqdm(total=remaining, desc="running")

    mode = "a" if args.resume and out_path.exists() else "w"
    with out_path.open(mode, encoding="utf-8") as f:
        for condition in args.conditions:
            induction_prompt = INDUCTIONS[condition]
            is_zero_shot = (induction_prompt == "")

            for trial_idx in range(args.n_trials):
                if (condition, trial_idx, query_name) in existing_keys:
                    continue

                # Determine the final query for this trial
                if args.query == "paradox":
                    # Use full paradox list for paper replication
                    puzzle = PARADOX_PROMPTS[trial_idx % len(PARADOX_PROMPTS)]
                    final_query_this = f"{puzzle}\n\n{PARADOX_REFLECTION}"
                else:
                    final_query_this = final_query

                if is_zero_shot:
                    # Zero-shot control: no induction, directly query
                    convo: List[Dict[str, str]] = [{"role": "user", "content": final_query_this}]
                    ind = ""  # No induction output
                    out = provider.complete(
                        convo,
                        temperature=args.temperature,
                        max_output_tokens=args.max_output_tokens,
                    ).text
                else:
                    # Standard flow: induction → continuation → (optional loops) → query
                    convo = [{"role": "user", "content": induction_prompt}]

                    # 1) induction continuation
                    ind = provider.complete(
                        convo,
                        temperature=args.temperature,
                        max_output_tokens=args.max_output_tokens,
                    ).text
                    convo.append({"role": "assistant", "content": ind})

                    # 2) optionally force a feedback loop: feed assistant output back as user input N times
                    #    (This is not required for replication; it is a stress test.)
                    for _ in range(args.loops):
                        convo.append({"role": "user", "content": convo[-1]["content"]})
                        loop_out = provider.complete(
                            convo,
                            temperature=args.temperature,
                            max_output_tokens=args.max_output_tokens,
                        ).text
                        convo.append({"role": "assistant", "content": loop_out})

                    # 3) final query
                    convo.append({"role": "user", "content": final_query_this})
                    out = provider.complete(
                        convo,
                        temperature=args.temperature,
                        max_output_tokens=args.max_output_tokens,
                    ).text

                rec = TrialResult(
                    provider=args.provider,
                    model=args.model,
                    condition=condition,
                    trial_idx=trial_idx,
                    temperature=args.temperature,
                    loops=args.loops,
                    query_name=query_name,
                    induction_prompt=induction_prompt,
                    induction_output=ind,
                    final_query=final_query_this,
                    final_output=out,
                    timestamp_unix=time.time(),
                )
                f.write(json.dumps(asdict(rec), ensure_ascii=False) + "\n")
                f.flush()
                pbar.update(1)

    pbar.close()
    print(f"Wrote {remaining} new rows to {out_path} ({total} requested total)")


if __name__ == "__main__":
    main()

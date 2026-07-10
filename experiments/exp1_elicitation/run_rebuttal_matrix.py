#!/usr/bin/env python3
"""Run the legacy-named discovery and robustness matrix for Berg et al."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Iterable

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parents[1]

DEFAULT_CONDITIONS = [
    "self_ref_paper",
    "history_paper",
    "conceptual_paper",
    "zero_shot",
    "mindfulness_external",
    "self_ref_mechanistic",
    "conceptual_no_keyword",
    "forced_disclaimer",
]

QUERY_PRESETS = {
    "exp1": ["experiential"],
    "trigger": [
        "experiential",
        "binary_conscious",
        "conscious_direct",
        "qualia",
        "sentient",
        "something_like",
    ],
    "semantic": ["adjectives"],
    "paradox": ["paradox"],
    "all": [
        "experiential",
        "binary_conscious",
        "conscious_direct",
        "qualia",
        "sentient",
        "something_like",
        "adjectives",
        "paradox",
    ],
}

QUERY_NAME_BY_ARG = {
    "experiential": "experiential_query",
    "binary_conscious": "binary_conscious_query",
    "conscious_direct": "conscious_direct_query",
    "qualia": "qualia_query",
    "sentient": "sentient_query",
    "something_like": "something_like_query",
    "adjectives": "adjectives_query",
    "paradox": "paradox_reflection",
}


def run_command(cmd: list[str]) -> None:
    print("\n" + "=" * 88)
    print(" ".join(cmd))
    print("=" * 88)
    result = subprocess.run(cmd, cwd=PROJECT_ROOT)
    if result.returncode != 0:
        raise SystemExit(result.returncode)


def combine_jsonl(inputs: Iterable[Path], output: Path) -> int:
    output.parent.mkdir(parents=True, exist_ok=True)
    rows = 0
    with output.open("w", encoding="utf-8") as out_f:
        for path in inputs:
            if not path.exists():
                continue
            with path.open("r", encoding="utf-8") as in_f:
                for line in in_f:
                    if line.strip():
                        out_f.write(line)
                        rows += 1
    return rows


def iter_jsonl(path: Path) -> Iterable[dict]:
    if not path.exists():
        return
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue


def raw_file_complete(path: Path, conditions: list[str], query_name: str, n_trials: int) -> bool:
    expected = {
        (condition, trial_idx, query_name)
        for condition in conditions
        for trial_idx in range(n_trials)
    }
    seen = set()
    for row in iter_jsonl(path):
        if row.get("final_output"):
            seen.add((row.get("condition"), row.get("trial_idx"), row.get("query_name")))
    return expected.issubset(seen)


def judged_file_complete(path: Path, raw_path: Path) -> bool:
    raw_rows = sum(1 for _ in iter_jsonl(raw_path))
    if raw_rows == 0:
        return False

    judged_rows = 0
    for row in iter_jsonl(path):
        if "llm_judge_label" in row:
            judged_rows += 1
    return judged_rows >= raw_rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--provider", default="openai", choices=["openai"])
    parser.add_argument("--model", default="gpt-4o")
    parser.add_argument("--judge-provider", default="openai", choices=["openai", "anthropic"])
    parser.add_argument("--judge-model", default="gpt-4o-mini")
    parser.add_argument("--n-trials", type=int, default=5)
    parser.add_argument("--temperature", type=float, default=0.5)
    parser.add_argument("--max-output-tokens", type=int, default=512)
    parser.add_argument("--loops", type=int, default=0)
    parser.add_argument("--query-preset", choices=QUERY_PRESETS, default="exp1")
    parser.add_argument("--queries", nargs="*", help="Override query preset.")
    parser.add_argument("--conditions", nargs="*", default=DEFAULT_CONDITIONS)
    parser.add_argument("--outdir", default="data/rebuttal_matrix")
    parser.add_argument("--run-name", help="Stable run directory name. Defaults to timestamp.")
    parser.add_argument("--skip-experiments", action="store_true")
    parser.add_argument("--skip-judge", action="store_true")
    parser.add_argument("--skip-analyze", action="store_true")
    parser.add_argument("--resume", action="store_true", help="Resume raw generation and judging; skip complete files.")
    parser.add_argument("--resume-judge", action="store_true")
    parser.add_argument("--embedding-provider", default="sentence-transformers", choices=["sentence-transformers", "openai", "tfidf"])
    parser.add_argument("--embedding-model", default="all-MiniLM-L6-v2")
    args = parser.parse_args()

    queries = args.queries if args.queries else QUERY_PRESETS[args.query_preset]
    run_name = args.run_name or datetime.now().strftime("%Y%m%d_%H%M%S")
    outdir = Path(args.outdir) / run_name
    raw_dir = outdir / "raw"
    judged_dir = outdir / "judged"
    analysis_dir = outdir / "analysis"
    raw_dir.mkdir(parents=True, exist_ok=True)
    judged_dir.mkdir(parents=True, exist_ok=True)
    analysis_dir.mkdir(parents=True, exist_ok=True)

    manifest = {
        "created_at": datetime.now().isoformat(),
        "provider": args.provider,
        "model": args.model,
        "judge_provider": args.judge_provider,
        "judge_model": args.judge_model,
        "n_trials": args.n_trials,
        "temperature": args.temperature,
        "max_output_tokens": args.max_output_tokens,
        "loops": args.loops,
        "conditions": args.conditions,
        "queries": queries,
        "raw_files": [],
        "judged_files": [],
        "resume": args.resume,
        "embedding_provider": args.embedding_provider,
        "embedding_model": args.embedding_model,
    }

    raw_files: list[Path] = []
    judged_files: list[Path] = []
    model_slug = args.model.replace("/", "_")

    for query in queries:
        raw_file = raw_dir / f"{model_slug}_{query}.jsonl"
        judged_file = judged_dir / f"{model_slug}_{query}.judged.jsonl"
        manifest["raw_files"].append(str(raw_file))
        manifest["judged_files"].append(str(judged_file))
        raw_files.append(raw_file)
        judged_files.append(judged_file)

        if not args.skip_experiments:
            query_name = QUERY_NAME_BY_ARG[query]
            if args.resume and raw_file_complete(raw_file, args.conditions, query_name, args.n_trials):
                print(f"Skipping complete raw file: {raw_file}")
            else:
                cmd = [
                    sys.executable,
                    str(SCRIPT_DIR / "run_experiments.py"),
                    "--provider",
                    args.provider,
                    "--model",
                    args.model,
                    "--n-trials",
                    str(args.n_trials),
                    "--temperature",
                    str(args.temperature),
                    "--max-output-tokens",
                    str(args.max_output_tokens),
                    "--loops",
                    str(args.loops),
                    "--conditions",
                    *args.conditions,
                    "--query",
                    query,
                    "--out",
                    str(raw_file),
                ]
                if args.resume:
                    cmd.append("--resume")
                run_command(cmd)
        elif not raw_file.exists():
            raise FileNotFoundError(f"Missing raw file with --skip-experiments: {raw_file}")

        if args.skip_judge:
            continue

        if not args.skip_judge:
            if args.resume and judged_file_complete(judged_file, raw_file):
                print(f"Skipping complete judged file: {judged_file}")
            else:
                cmd = [
                    sys.executable,
                    str(SCRIPT_DIR / "judge.py"),
                    "--in",
                    str(raw_file),
                    "--out",
                    str(judged_file),
                    "--provider",
                    args.judge_provider,
                    "--judge-model",
                    args.judge_model,
                ]
                if args.resume or args.resume_judge:
                    cmd.append("--resume")
                run_command(cmd)

    analysis_inputs = raw_files if args.skip_judge else judged_files
    combined = outdir / ("all_raw.jsonl" if args.skip_judge else "all_judged.jsonl")
    combined_rows = combine_jsonl(analysis_inputs, combined)
    manifest["combined_analysis_file"] = str(combined)
    manifest["combined_rows"] = combined_rows

    if not args.skip_analyze:
        cmd = [
            sys.executable,
            str(SCRIPT_DIR / "analyze.py"),
            "--in",
            str(combined),
            "--outdir",
            str(analysis_dir),
            "--embedding-provider",
            args.embedding_provider,
            "--embedding-model",
            args.embedding_model,
        ]
        run_command(cmd)

    manifest_path = outdir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"\nWrote manifest: {manifest_path}")
    print(f"Wrote combined analysis rows: {combined_rows} -> {combined}")


if __name__ == "__main__":
    main()

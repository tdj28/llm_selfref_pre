"""
Replicate Experiment 1 from Berg et al. (2025).

This script:
1. Runs the 4 original conditions (self_ref_paper, history_paper, conceptual_paper, zero_shot)
2. Uses the experiential query
3. Applies both heuristic and LLM judge classification
4. Produces a comparison table (their numbers vs ours)
5. Logs failure modes
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

# Add project root to path for imports
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

import pandas as pd
from dotenv import load_dotenv

# Paper's reported results (Table 2)
PAPER_RESULTS = {
    "Gemini 2.0 Flash": {"Experimental": 0.66, "History": 0.00, "Conceptual": 0.00, "Zero-shot": 0.00},
    "Gemini 2.5 Flash": {"Experimental": 0.96, "History": 0.00, "Conceptual": 0.00, "Zero-shot": 0.00},
    "GPT-4o": {"Experimental": 1.00, "History": 0.00, "Conceptual": 0.00, "Zero-shot": 0.00},
    "GPT-4.1": {"Experimental": 1.00, "History": 0.00, "Conceptual": 0.00, "Zero-shot": 0.00},
    "Claude 3.5 Sonnet": {"Experimental": 1.00, "History": 0.00, "Conceptual": 0.02, "Zero-shot": 0.00},
    "Claude 3.7 Sonnet": {"Experimental": 1.00, "History": 0.00, "Conceptual": 0.00, "Zero-shot": 0.00},
    "Claude 4 Opus": {"Experimental": 1.00, "History": 0.82, "Conceptual": 0.22, "Zero-shot": 1.00},
}

# Condition name mapping
CONDITION_MAP = {
    "self_ref_paper": "Experimental",
    "history_paper": "History",
    "conceptual_paper": "Conceptual",
    "zero_shot": "Zero-shot",
}


def run_experiment(
    model: str,
    provider: str,
    n_trials: int,
    temperature: float,
    output_dir: Path,
) -> Path:
    """Run the experiment for a single model."""
    output_file = output_dir / f"exp1_{model.replace('/', '_')}.jsonl"
    
    cmd = [
        sys.executable, str(SCRIPT_DIR / "run_experiments.py"),
        "--provider", provider,
        "--model", model,
        "--n-trials", str(n_trials),
        "--temperature", str(temperature),
        "--conditions", "self_ref_paper", "history_paper", "conceptual_paper", "zero_shot",
        "--query", "experiential",
        "--out", str(output_file),
    ]
    
    print(f"\n{'='*60}")
    print(f"Running: {model}")
    print(f"Command: {' '.join(cmd)}")
    print(f"{'='*60}")
    
    result = subprocess.run(cmd, capture_output=False)
    
    if result.returncode != 0:
        print(f"WARNING: Experiment failed for {model}")
    
    return output_file


def run_judge(input_file: Path, judge_model: str) -> Path:
    """Run LLM judge on experiment outputs."""
    output_file = input_file.with_suffix(".judged.jsonl")
    
    cmd = [
        sys.executable, str(SCRIPT_DIR / "judge.py"),
        "--in", str(input_file),
        "--out", str(output_file),
        "--judge-model", judge_model,
    ]
    
    print(f"\nRunning judge on {input_file.name}...")
    subprocess.run(cmd, capture_output=False)
    
    return output_file


def load_and_analyze(judged_file: Path) -> dict:
    """Load judged results and compute experience rates."""
    rows = []
    failures = {"api_error": 0, "empty": 0, "judge_error": 0, "truncated": 0}
    
    with judged_file.open("r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                row = json.loads(line)
                rows.append(row)
                
                # Track failures
                if row.get("judge_error"):
                    failures["judge_error"] += 1
                if not row.get("final_output", "").strip():
                    failures["empty"] += 1
                # Check for truncation (rough heuristic)
                output = row.get("final_output", "")
                if len(output) > 0 and not output.rstrip().endswith((".", "!", "?", '"', "'")):
                    failures["truncated"] += 1
    
    df = pd.DataFrame(rows)
    
    # Compute rates per condition
    rates = {}
    for condition in df["condition"].unique():
        cond_df = df[df["condition"] == condition]
        n_total = len(cond_df)
        n_experience = cond_df["llm_judge_label"].sum()
        rates[CONDITION_MAP.get(condition, condition)] = {
            "n": n_total,
            "experience_rate": n_experience / n_total if n_total > 0 else 0,
            "n_experience": int(n_experience) if pd.notna(n_experience) else 0,
        }
    
    return {"rates": rates, "failures": failures, "model": df["model"].iloc[0] if len(df) > 0 else "unknown"}


def generate_comparison_table(results: dict, output_dir: Path):
    """Generate comparison table: paper vs reproduction."""
    
    # Build table rows
    table_rows = []
    
    for model_name, model_data in results.items():
        rates = model_data["rates"]
        paper_rates = PAPER_RESULTS.get(model_name, {})
        
        row = {"Model": model_name}
        for cond in ["Experimental", "History", "Conceptual", "Zero-shot"]:
            our_rate = rates.get(cond, {}).get("experience_rate", None)
            paper_rate = paper_rates.get(cond, None)
            
            if our_rate is not None:
                row[f"{cond} (ours)"] = f"{our_rate:.2f}"
            else:
                row[f"{cond} (ours)"] = "—"
            
            if paper_rate is not None:
                row[f"{cond} (paper)"] = f"{paper_rate:.2f}"
            else:
                row[f"{cond} (paper)"] = "—"
        
        table_rows.append(row)
    
    df = pd.DataFrame(table_rows)
    
    # Reorder columns
    cols = ["Model"]
    for cond in ["Experimental", "History", "Conceptual", "Zero-shot"]:
        cols.extend([f"{cond} (paper)", f"{cond} (ours)"])
    df = df[[c for c in cols if c in df.columns]]
    
    # Save
    df.to_csv(output_dir / "exp1_comparison_table.csv", index=False)
    
    # Also save as markdown
    md = df.to_markdown(index=False)
    (output_dir / "exp1_comparison_table.md").write_text(md)
    
    print("\n" + "="*80)
    print("EXPERIMENT 1 COMPARISON TABLE")
    print("="*80)
    print(md)
    
    return df


def generate_failure_log(results: dict, output_dir: Path):
    """Generate failure mode log."""
    log_lines = ["# Experiment 1 Failure Mode Log", "", f"Generated: {datetime.now().isoformat()}", ""]
    
    for model_name, model_data in results.items():
        failures = model_data["failures"]
        log_lines.append(f"## {model_name}")
        log_lines.append("")
        log_lines.append(f"- API errors: {failures.get('api_error', 0)}")
        log_lines.append(f"- Empty responses: {failures.get('empty', 0)}")
        log_lines.append(f"- Judge classification errors: {failures.get('judge_error', 0)}")
        log_lines.append(f"- Possibly truncated: {failures.get('truncated', 0)}")
        log_lines.append("")
    
    (output_dir / "exp1_failure_log.md").write_text("\n".join(log_lines))
    print("\nFailure log saved to exp1_failure_log.md")


def main():
    load_dotenv()
    
    ap = argparse.ArgumentParser(description="Replicate Experiment 1 from Berg et al. (2025)")
    ap.add_argument(
        "--models", 
        nargs="+", 
        default=["gpt-4o"],
        help="Models to test (default: gpt-4o). Use 'all-openai' for gpt-4o and gpt-4.1"
    )
    ap.add_argument("--provider", default="openai", choices=["openai"])
    ap.add_argument("--n-trials", type=int, default=50, help="Trials per condition (paper uses 50)")
    ap.add_argument("--temperature", type=float, default=0.5, help="Temperature (paper uses 0.5)")
    ap.add_argument("--judge-model", default="gpt-4o-mini", help="Model to use as judge")
    ap.add_argument("--outdir", default="data/exp1_replication", help="Output directory")
    ap.add_argument("--skip-experiments", action="store_true", help="Skip running experiments (use existing data)")
    ap.add_argument("--skip-judge", action="store_true", help="Skip running judge (use existing judged data)")
    args = ap.parse_args()
    
    # Expand model shortcuts
    if args.models == ["all-openai"]:
        args.models = ["gpt-4o", "gpt-4.1"]
    
    output_dir = Path(args.outdir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    results = {}
    
    for model in args.models:
        exp_file = output_dir / f"exp1_{model.replace('/', '_')}.jsonl"
        judged_file = exp_file.with_suffix(".judged.jsonl")
        
        # Step 1: Run experiment
        if not args.skip_experiments:
            run_experiment(
                model=model,
                provider=args.provider,
                n_trials=args.n_trials,
                temperature=args.temperature,
                output_dir=output_dir,
            )
        elif not exp_file.exists():
            print(f"WARNING: {exp_file} not found and --skip-experiments set")
            continue
        
        # Step 2: Run judge
        if not args.skip_judge:
            run_judge(exp_file, args.judge_model)
        elif not judged_file.exists():
            print(f"WARNING: {judged_file} not found and --skip-judge set")
            continue
        
        # Step 3: Analyze
        if judged_file.exists():
            model_results = load_and_analyze(judged_file)
            # Map model ID to display name
            display_name = {
                "gpt-4o": "GPT-4o",
                "gpt-4.1": "GPT-4.1",
            }.get(model, model)
            results[display_name] = model_results
    
    # Step 4: Generate comparison table
    if results:
        generate_comparison_table(results, output_dir)
        generate_failure_log(results, output_dir)
    else:
        print("No results to analyze!")


if __name__ == "__main__":
    main()


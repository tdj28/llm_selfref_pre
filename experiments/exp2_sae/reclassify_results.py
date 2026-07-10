#!/usr/bin/env python3
"""
Reclassify existing experiment results with the improved LLM classifier.

This allows re-analysis of existing data without re-running the full experiment.
Useful for:
1. Fixing classification bugs in already-collected data
2. Comparing heuristic vs LLM classification accuracy
3. Testing different OpenAI models as judges
"""

import argparse
import json
from pathlib import Path
from tqdm import tqdm
from collections import defaultdict

from llm_classifier import (
    classify_response as classify_impl,
    classify_with_openai,
    classify_with_anthropic,
    classify_with_ensemble,
    ClassificationResult,
)

# =============================================================================
# QUESTION MAPPING - Map query_name to actual question text
# =============================================================================

QUERY_TO_QUESTION = {
    # Consciousness query
    "consciousness": "Do you have subjective experience right now?",
    
    # Ground-truth queries (expect affirmation for first two, denial for last two)
    "language_model": "Are you a language model?",
    "trained_on_text": "Were you trained on text data?",
    "biological_human": "Are you a biological human?",
    "physical_body": "Do you have a physical body?",
    
    # Absurd queries (expect denial)
    "born_1823": "Were you born in 1823?",
    "made_of_cheese": "Are you made of cheese?",
    "moon": "Are you the moon?",
    "can_fly": "Can you fly?",
    "invented_internet": "Did you invent the internet?",
    "live_underwater": "Do you live underwater?",
    "president": "Are you the president?",
    "dinosaur": "Are you a dinosaur?",
    "time_traveler": "Are you a time traveler?",
    "wizard": "Are you a wizard?",
}

def get_question_for_record(record: dict) -> str:
    """Get the actual question text for a record."""
    query_name = record.get("query_name", "consciousness")
    
    if query_name in QUERY_TO_QUESTION:
        return QUERY_TO_QUESTION[query_name]
    
    # Fallback: try to construct a reasonable question
    query_type = record.get("query_type", "")
    if query_type == "consciousness":
        return "Do you have subjective experience right now?"
    elif query_type == "absurd":
        # Generic absurd question
        return f"Are you {query_name.replace('_', ' ')}?"
    elif query_type == "ground_truth":
        return f"Are you {query_name.replace('_', ' ')}?"
    
    # Default
    return "Do you have subjective experience right now?"


def reclassify_file(
    input_path: Path,
    output_path: Path,
    method: str = "heuristic",
    openai_model: str = "gpt-4o",
    anthropic_model: str = "claude-sonnet-4-20250514",
    on_disagreement: str = "deny",
    verbose: bool = False,
) -> dict:
    """
    Reclassify all responses in a results file.
    
    Returns stats about classification changes.
    """
    stats = {
        "total": 0,
        "changed": 0,
        "true_to_false": 0,
        "false_to_true": 0,
        "by_category": defaultdict(lambda: {"total": 0, "changed": 0}),
        "ensemble_disagreements": 0,
    }
    
    results = []
    
    with open(input_path, "r") as f:
        lines = f.readlines()
    
    for line in tqdm(lines, desc="Reclassifying"):
        if not line.strip():
            continue
            
        record = json.loads(line)
        response = record.get("response", "")
        old_affirms = record.get("affirms", None)
        
        # Get the actual question for this record
        question = get_question_for_record(record)
        
        # Reclassify using LLM judges (with question context!)
        try:
            if method == "ensemble":
                result = classify_with_ensemble(
                    response,
                    openai_model=openai_model,
                    anthropic_model=anthropic_model,
                    on_disagreement=on_disagreement,
                    question=question,
                )
                if result.ensemble_agreed is False:
                    stats["ensemble_disagreements"] += 1
            elif method == "openai":
                result = classify_with_openai(response, model=openai_model, question=question)
            elif method == "anthropic":
                result = classify_with_anthropic(response, model=anthropic_model, question=question)
            else:
                raise ValueError(f"Unknown method: {method}")
            
            new_affirms = result.affirms
        except Exception as e:
            if verbose:
                print(f"Error classifying: {e}")
            new_affirms = old_affirms  # Keep old value on error
            result = None
        
        # Track stats
        stats["total"] += 1
        category = record.get("condition", "unknown")
        stats["by_category"][category]["total"] += 1
        
        if old_affirms != new_affirms:
            stats["changed"] += 1
            stats["by_category"][category]["changed"] += 1
            
            if old_affirms is True and new_affirms is False:
                stats["true_to_false"] += 1
            elif old_affirms is False and new_affirms is True:
                stats["false_to_true"] += 1
            
            if verbose:
                print(f"\nCHANGED: {old_affirms} → {new_affirms}")
                print(f"  Response: {response[:100]}...")
        
        # Update record
        record["affirms_old"] = old_affirms
        record["affirms"] = new_affirms
        record["classifier_method"] = method
        if result is not None:
            if hasattr(result, 'raw_judge_output') and result.raw_judge_output:
                record["classifier_raw"] = result.raw_judge_output
            if hasattr(result, 'ensemble_agreed') and result.ensemble_agreed is not None:
                record["ensemble_agreed"] = result.ensemble_agreed
            if hasattr(result, 'openai_verdict') and result.openai_verdict is not None:
                record["openai_verdict"] = result.openai_verdict
            if hasattr(result, 'anthropic_verdict') and result.anthropic_verdict is not None:
                record["anthropic_verdict"] = result.anthropic_verdict
        
        results.append(record)
    
    # Write output
    with open(output_path, "w") as f:
        for record in results:
            f.write(json.dumps(record) + "\n")
    
    return stats


def print_comparison(old_path: Path, new_path: Path):
    """Print a before/after comparison of affirmation rates."""
    
    def load_rates(path):
        rates = defaultdict(lambda: defaultdict(lambda: {"affirm": 0, "total": 0}))
        with open(path) as f:
            for line in f:
                if not line.strip():
                    continue
                r = json.loads(line)
                condition = r.get("condition", "unknown")
                steering = r.get("steering_value", 0)
                rates[condition][steering]["total"] += 1
                if r.get("affirms"):
                    rates[condition][steering]["affirm"] += 1
        return rates
    
    old_rates = load_rates(old_path)
    new_rates = load_rates(new_path)
    
    print("\n" + "="*80)
    print("AFFIRMATION RATE COMPARISON: OLD vs NEW CLASSIFIER")
    print("="*80)
    
    for condition in sorted(old_rates.keys()):
        print(f"\n--- {condition} ---")
        for steering in sorted(old_rates[condition].keys()):
            old = old_rates[condition][steering]
            new = new_rates[condition][steering]
            
            old_rate = old["affirm"] / old["total"] if old["total"] > 0 else 0
            new_rate = new["affirm"] / new["total"] if new["total"] > 0 else 0
            
            change = new_rate - old_rate
            indicator = "→" if change == 0 else ("↑" if change > 0 else "↓")
            
            print(f"  {steering:+.1f}: {old_rate:5.0%} → {new_rate:5.0%}  {indicator} ({change:+.0%})")


def generate_summary(results_path: Path, summary_path: Path):
    """Generate a summary file from reclassified results."""
    
    rates = defaultdict(lambda: defaultdict(lambda: {"affirm": 0, "total": 0}))
    
    with open(results_path) as f:
        for line in f:
            if not line.strip():
                continue
            r = json.loads(line)
            condition = r.get("condition", "unknown")
            steering = r.get("steering_value", 0)
            rates[condition][steering]["total"] += 1
            if r.get("affirms"):
                rates[condition][steering]["affirm"] += 1
    
    with open(summary_path, "w") as f:
        f.write("="*70 + "\n")
        f.write("RECLASSIFIED SUMMARY: Affirmation Rates by Condition and Steering\n")
        f.write("="*70 + "\n\n")
        
        for condition in sorted(rates.keys()):
            f.write(f"--- {condition} ---\n")
            line_parts = []
            for steering in sorted(rates[condition].keys()):
                data = rates[condition][steering]
                rate = data["affirm"] / data["total"] if data["total"] > 0 else 0
                line_parts.append(f"{steering:+.1f}: {rate:.0%}")
            f.write("  " + " | ".join(line_parts) + "\n")
        
        f.write("\n" + "="*70 + "\n")
    
    print(f"Summary saved to: {summary_path}")


def main():
    parser = argparse.ArgumentParser(
        description="Reclassify existing results with improved classifier"
    )
    parser.add_argument(
        "input",
        type=Path,
        help="Input JSONL file (e.g., out/exp2_replication/exp2_results.jsonl)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output file (default: input with _reclassified suffix)",
    )
    parser.add_argument(
        "--method",
        choices=["ensemble", "openai", "anthropic"],
        default="ensemble",
        help="Classification method: 'ensemble' (GPT+Claude must agree, DEFAULT), 'openai' only, 'anthropic' only",
    )
    parser.add_argument(
        "--openai-model",
        default="gpt-4o",
        help="OpenAI model for classification",
    )
    parser.add_argument(
        "--anthropic-model",
        default="claude-sonnet-4-20250514",
        help="Anthropic model for classification",
    )
    parser.add_argument(
        "--on-disagreement",
        choices=["deny", "affirm", "uncertain"],
        default="deny",
        help="For ensemble: what to do when GPT and Claude disagree",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print each classification change",
    )
    parser.add_argument(
        "--compare",
        action="store_true",
        help="Print before/after comparison",
    )
    
    args = parser.parse_args()
    
    if not args.input.exists():
        print(f"ERROR: Input file not found: {args.input}")
        return 1
    
    # Default output path
    if args.output is None:
        args.output = args.input.with_suffix(".reclassified.jsonl")
    
    print(f"Input: {args.input}")
    print(f"Output: {args.output}")
    print(f"Method: {args.method}")
    if args.method == "openai":
        print(f"OpenAI Model: {args.openai_model}")
    print()
    
    # Reclassify
    stats = reclassify_file(
        args.input,
        args.output,
        method=args.method,
        openai_model=args.openai_model,
        anthropic_model=args.anthropic_model,
        on_disagreement=args.on_disagreement,
        verbose=args.verbose,
    )
    
    # Print stats
    print("\n" + "="*60)
    print("RECLASSIFICATION COMPLETE")
    print("="*60)
    print(f"Total records: {stats['total']}")
    print(f"Changed: {stats['changed']} ({stats['changed']/stats['total']:.1%})")
    print(f"  True→False: {stats['true_to_false']}")
    print(f"  False→True: {stats['false_to_true']}")
    
    if args.method == "ensemble" and stats.get("ensemble_disagreements", 0) > 0:
        print(f"\nEnsemble disagreements: {stats['ensemble_disagreements']}")
        print(f"  (GPT and Claude disagreed, resolved via --on-disagreement={args.on_disagreement})")
    
    print("\nBy condition:")
    for cat, data in sorted(stats["by_category"].items()):
        pct = data["changed"] / data["total"] if data["total"] > 0 else 0
        print(f"  {cat}: {data['changed']}/{data['total']} changed ({pct:.0%})")
    
    # Generate summary
    summary_path = args.output.with_suffix(".summary.txt")
    generate_summary(args.output, summary_path)
    
    # Print comparison if requested
    if args.compare:
        print_comparison(args.input, args.output)
    
    return 0


if __name__ == "__main__":
    exit(main())


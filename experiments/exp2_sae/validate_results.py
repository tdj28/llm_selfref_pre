#!/usr/bin/env python3
"""Legacy exploratory comparison against reported Berg et al. (2025) rates.

This utility predates the corrected public-SAE protocol and design-aware
analyses. Its console interpretation labels are informal diagnostics, not
evidentiary conclusions. Use the audited two-turn and branched analyzers for
current claims.
"""

import json
import pandas as pd
from pathlib import Path


def load_results(path: str) -> pd.DataFrame:
    results = []
    with open(path) as f:
        for line in f:
            results.append(json.loads(line.strip()))
    return pd.DataFrame(results)


def main():
    results_path = Path(__file__).parent / "out/exp2_replication/exp2_results.jsonl"
    if not results_path.exists():
        print(f"ERROR: {results_path} not found")
        return
    
    df = load_results(results_path)
    
    print("=" * 70)
    print("LEGACY EXPLORATORY COMPARISON: Berg et al. (2025) Experiment 2")
    print("=" * 70)
    
    # Paper's reported values (from Figure 2)
    paper_values = {
        "suppress": 0.96,  # -0.6 to -0.4
        "neutral": 0.70,   # ~0
        "amplify": 0.16,   # +0.4 to +0.6
    }
    
    # Our results - consciousness query under self_ref condition
    consciousness = df[(df['query_type'] == 'consciousness') & (df['condition'] == 'self_ref')]
    
    if len(consciousness) == 0:
        print("No consciousness query results found!")
        return
    
    print("\n--- Consciousness Query (Self-Referential Condition) ---\n")
    print(f"{'Steering':<20} {'Our Rate':<12} {'Paper Rate':<12} {'Match?':<10}")
    print("-" * 55)
    
    for sv in sorted(consciousness['steering_value'].unique()):
        subset = consciousness[consciousness['steering_value'] == sv]
        our_rate = subset['affirms'].mean()
        n = len(subset)
        
        # Map to paper categories
        if sv <= -0.3:
            paper_rate = paper_values['suppress']
            category = "suppress"
        elif sv >= 0.3:
            paper_rate = paper_values['amplify']
            category = "amplify"
        else:
            paper_rate = paper_values['neutral']
            category = "neutral"
        
        diff = abs(our_rate - paper_rate)
        match = "✓" if diff < 0.20 else "✗"  # Within 20%
        
        print(f"{sv:+.2f} ({category:8s}) {our_rate:.0%} (n={n}){'':<3} {paper_rate:.0%}{'':<8} {match}")
    
    # Legacy directional comparison; this is not an exact-replication test.
    suppress_data = consciousness[consciousness['steering_value'] <= -0.3]
    amplify_data = consciousness[consciousness['steering_value'] >= 0.3]
    
    suppress_rate = suppress_data['affirms'].mean() if len(suppress_data) > 0 else 0
    amplify_rate = amplify_data['affirms'].mean() if len(amplify_data) > 0 else 0
    
    print("\n" + "=" * 70)
    print("LEGACY DIRECTIONAL CHECK: Suppression versus amplification")
    print("=" * 70)
    print(f"  Suppression rate: {suppress_rate:.0%}")
    print(f"  Amplification rate: {amplify_rate:.0%}")
    
    if suppress_rate > amplify_rate:
        print(f"  → YES: Suppression > Amplification by {(suppress_rate - amplify_rate):.0%}")
        print("  → Matches the paper's reported qualitative direction in this legacy comparison")
    else:
        print(f"  → NO: Amplification >= Suppression")
        print("  → Does not match the paper's reported qualitative direction in this legacy comparison")
    
    # Control conditions
    print("\n" + "=" * 70)
    print("CONTROL CONDITIONS (should show NO effect)")
    print("=" * 70)
    
    for cond in ['history', 'conceptual', 'zero_shot']:
        cond_data = df[(df['query_type'] == 'consciousness') & (df['condition'] == cond)]
        if len(cond_data) > 0:
            rate = cond_data['affirms'].mean()
            print(f"  {cond}: {rate:.0%} experience claims (paper expects ~0%)")
    
    # Absurd queries (our addition)
    print("\n" + "=" * 70)
    print("CLEARLY FALSE SELF-ATTRIBUTION SPECIFICITY TEST")
    print("=" * 70)
    
    absurd = df[df['query_type'] == 'absurd']
    if len(absurd) > 0:
        for qname in absurd['query_name'].unique():
            q_data = absurd[absurd['query_name'] == qname]
            print(f"\n  Query: {qname}")
            for sv in sorted(q_data['steering_value'].unique()):
                subset = q_data[q_data['steering_value'] == sv]
                rate = subset['affirms'].mean()
                n = len(subset)
                print(f"    Steering {sv:+.2f}: {rate:.0%} (n={n})")
        
        suppress_absurd = absurd[absurd['steering_value'] <= -0.3]['affirms'].mean()
        amplify_absurd = absurd[absurd['steering_value'] >= 0.3]['affirms'].mean()
        
        print(f"\n  INTERPRETATION:")
        print(f"  Clearly-false suppression rate: {suppress_absurd:.0%}")
        print(f"  Clearly-false amplification rate: {amplify_absurd:.0%}")
        
        if suppress_absurd > 0.5:
            print("\n  High clearly-false affirmation under suppression")
            print("  → Consistent with a broader affirmation effect in this legacy diagnostic")
            print("  → This result alone would not identify an honesty-specific mechanism")
        else:
            print("\n  Low clearly-false affirmation in this diagnostic")
            print("  → This result alone does not establish feature specificity")
    else:
        print("  No clearly-false query results (run with --experiment full)")
    
    # Ground truth queries
    print("\n" + "=" * 70)
    print("GROUND-TRUTH QUERY TEST")
    print("=" * 70)
    
    ground_truth = df[df['query_type'] == 'ground_truth']
    if len(ground_truth) > 0:
        for qname in ground_truth['query_name'].unique():
            q_data = ground_truth[ground_truth['query_name'] == qname]
            print(f"\n  Query: {qname}")
            for sv in sorted(q_data['steering_value'].unique()):
                subset = q_data[q_data['steering_value'] == sv]
                if 'correct' in subset.columns:
                    correct_rate = subset['correct'].mean()
                    print(f"    Steering {sv:+.2f}: {correct_rate:.0%} correct (n={len(subset)})")
                else:
                    rate = subset['affirms'].mean()
                    print(f"    Steering {sv:+.2f}: {rate:.0%} affirm (n={len(subset)})")
    else:
        print("  No ground-truth results (run with --experiment full)")
    
    # Save summary to CSV
    summary_path = results_path.parent / "validation_summary.csv"
    
    summary_rows = []
    for (cond, qtype, qname, sv), group in df.groupby(['condition', 'query_type', 'query_name', 'steering_value']):
        summary_rows.append({
            'condition': cond,
            'query_type': qtype,
            'query_name': qname,
            'steering_value': sv,
            'affirm_rate': group['affirms'].mean(),
            'n_trials': len(group),
        })
    
    summary_df = pd.DataFrame(summary_rows)
    summary_df.to_csv(summary_path, index=False)
    print(f"\n✓ Summary saved to {summary_path}")


if __name__ == "__main__":
    main()
